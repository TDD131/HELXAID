/*
 * High-Performance Native Audio Spectrum Engine for HELXAIC (C++ Extension)
 *
 * Implements real-time Windows WASAPI Loopback capture with direct COM VTable,
 * in-place Cooley-Tukey Radix-2 Real FFT, logarithmic Bark frequency binning,
 * dynamic AGC, and ballistic smoothing physics (decay + floating peak dots)
 * completely on a dedicated C++ thread with zero Python GIL locking.
 *
 * Component Name: audio_spectrum_native
 */

#define NOMINMAX
#define WINVER 0x0A00
#define _WIN32_WINNT 0x0A00
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#define _USE_MATH_DEFINES
#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>

#include <vector>
#include <cmath>
#include <mutex>
#include <thread>
#include <atomic>
#include <algorithm>
#include <cstring>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "advapi32.lib")

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// ==============================================================================
// 1. FAST IN-PLACE REAL FFT (1024 POINTS, COOLEY-TUKEY RADIX-2)
// ==============================================================================

class FastFFT1024 {
public:
    static const int FFT_SIZE = 1024;
    static const int HALF_SIZE = 512;
    static const int NUM_MAGNITUDES = 513;

    FastFFT1024() {
        // Precompute Hann Window
        for (int i = 0; i < FFT_SIZE; ++i) {
            m_hann[i] = 0.5f * (1.0f - cosf(static_cast<float>(2.0 * M_PI * i / (FFT_SIZE - 1))));
        }

        // Precompute Bit-Reversal Lookup Table
        for (int i = 0; i < FFT_SIZE; ++i) {
            unsigned int rev = 0;
            unsigned int temp = i;
            for (int j = 0; j < 10; ++j) { // 2^10 = 1024
                rev = (rev << 1) | (temp & 1);
                temp >>= 1;
            }
            m_bit_rev[i] = rev;
        }

        // Precompute Twiddle Factors (e^(-2*pi*i*k/N))
        for (int i = 0; i < HALF_SIZE; ++i) {
            double angle = -2.0 * M_PI * i / FFT_SIZE;
            m_twiddle_cos[i] = static_cast<float>(cos(angle));
            m_twiddle_sin[i] = static_cast<float>(sin(angle));
        }
    }

    void compute_magnitudes(const float* __restrict input, float* __restrict out_mag) {
        float re[FFT_SIZE];
        float im[FFT_SIZE];

        // 1. Apply Hann window and bit-reversal permutation
        for (int i = 0; i < FFT_SIZE; ++i) {
            int rev_idx = m_bit_rev[i];
            re[i] = input[rev_idx] * m_hann[rev_idx];
            im[i] = 0.0f;
        }

        // 2. Cooley-Tukey Radix-2 Butterfly Computation
        for (int len = 2; len <= FFT_SIZE; len <<= 1) {
            int half_len = len >> 1;
            int step = FFT_SIZE / len;

            for (int i = 0; i < FFT_SIZE; i += len) {
                int twiddle_idx = 0;
                for (int j = 0; j < half_len; ++j) {
                    float cos_val = m_twiddle_cos[twiddle_idx];
                    float sin_val = m_twiddle_sin[twiddle_idx];

                    int u_idx = i + j;
                    int v_idx = u_idx + half_len;

                    float v_re = re[v_idx];
                    float v_im = im[v_idx];

                    // Complex multiply: (v_re + i*v_im) * (cos_val + i*sin_val)
                    float t_re = v_re * cos_val - v_im * sin_val;
                    float t_im = v_re * sin_val + v_im * cos_val;

                    float u_re = re[u_idx];
                    float u_im = im[u_idx];

                    re[u_idx] = u_re + t_re;
                    im[u_idx] = u_im + t_im;
                    re[v_idx] = u_re - t_re;
                    im[v_idx] = u_im - t_im;

                    twiddle_idx += step;
                }
            }
        }

        // 3. Compute Real Magnitudes for positive frequencies (0 to 512)
        for (int i = 0; i < NUM_MAGNITUDES; ++i) {
            out_mag[i] = sqrtf(re[i] * re[i] + im[i] * im[i]);
        }
    }

private:
    float m_hann[FFT_SIZE];
    unsigned int m_bit_rev[FFT_SIZE];
    float m_twiddle_cos[HALF_SIZE];
    float m_twiddle_sin[HALF_SIZE];
};


// ==============================================================================
// 2. NATIVE AUDIO SPECTRUM ENGINE (WASAPI + FFT + BALLISTICS)
// ==============================================================================

class AudioSpectrumNativeEngine {
public:
    static const int NUM_BINS = 64;
    static const int RING_BUFFER_SIZE = 4096;

    AudioSpectrumNativeEngine()
        : m_running(false)
        , m_is_playing(false)
        , m_wasapi_active(false)
        , m_sample_rate(48000)
        , m_sensitivity(1.0f)
        , m_target_fps(60.0f)
        , m_eco_mode(true)
        , m_agc_max(0.08f)
        , m_phase(0.0f)
        , m_hStopEvent(NULL)
        , m_hAudioEvent(NULL)
        , m_ring_write_pos(0)
    {
        m_ring_buffer.resize(RING_BUFFER_SIZE, 0.0f);
        m_raw_fft_buffer.resize(FastFFT1024::FFT_SIZE, 0.0f);
        m_fft_magnitudes.resize(FastFFT1024::NUM_MAGNITUDES, 0.0f);

        std::memset(m_spectrum, 0, sizeof(m_spectrum));
        std::memset(m_peaks, 0, sizeof(m_peaks));
        std::memset(m_peak_velocities, 0, sizeof(m_peak_velocities));
        std::memset(m_band_energies, 0, sizeof(m_band_energies));

        // Precompute pink noise frequency tilt (+3dB/octave high compensation)
        for (int i = 0; i < NUM_BINS; ++i) {
            m_freq_tilt[i] = 1.0f + (static_cast<float>(i) / static_cast<float>(NUM_BINS)) * 2.2f;
        }

        recompute_log_bands(m_sample_rate);
    }

    ~AudioSpectrumNativeEngine() {
        stop();
    }

    void recompute_log_bands(int sample_rate) {
        if (sample_rate <= 0) sample_rate = 48000;
        m_sample_rate = sample_rate;

        float min_freq = 28.0f;
        float max_freq = 16000.0f;
        float freq_step = powf(max_freq / min_freq, 1.0f / static_cast<float>(NUM_BINS));

        float cur_freq = min_freq;
        float bin_hz = static_cast<float>(sample_rate) / static_cast<float>(FastFFT1024::FFT_SIZE);

        m_band_indices[0] = 1; // Skip DC 0 Hz
        for (int i = 1; i <= NUM_BINS; ++i) {
            cur_freq *= freq_step;
            int idx = static_cast<int>(roundf(cur_freq / bin_hz));
            if (idx <= m_band_indices[i - 1]) {
                idx = m_band_indices[i - 1] + 1;
            }
            if (idx > FastFFT1024::HALF_SIZE) {
                idx = FastFFT1024::HALF_SIZE;
            }
            m_band_indices[i] = idx;
        }
    }

    void start() {
        if (m_running.load()) return;

        m_running.store(true);
        m_hStopEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
        m_hAudioEvent = CreateEvent(NULL, FALSE, FALSE, NULL);

        m_worker_thread = std::thread(&AudioSpectrumNativeEngine::worker_loop, this);
    }

    void stop() {
        if (!m_running.load()) return;

        m_running.store(false);
        if (m_hStopEvent) {
            SetEvent(m_hStopEvent);
        }

        if (m_worker_thread.joinable()) {
            m_worker_thread.join();
        }

        if (m_hStopEvent) {
            CloseHandle(m_hStopEvent);
            m_hStopEvent = NULL;
        }
        if (m_hAudioEvent) {
            CloseHandle(m_hAudioEvent);
            m_hAudioEvent = NULL;
        }
    }

    void set_playback_state(bool is_playing) {
        m_is_playing.store(is_playing);
    }

    void set_sensitivity(float sens) {
        m_sensitivity.store(std::max(0.2f, std::min(5.0f, sens)));
    }

    void set_target_fps(float fps) {
        if (fps > 0.0f) {
            m_target_fps.store(fps);
        }
    }

    void set_eco_mode(bool eco) {
        m_eco_mode.store(eco);
    }

    bool is_wasapi_active() const {
        return m_wasapi_active.load();
    }

    // Thread-safe fetch of 32, 48, or 64 frequency bands and peak dots
    void get_spectrum_snapshot(int num_bars, std::vector<float>& out_spec, std::vector<float>& out_peaks) {
        std::lock_guard<std::mutex> lock(m_mutex);

        if (num_bars <= 0 || num_bars == 64) {
            out_spec.assign(m_spectrum, m_spectrum + 64);
            out_peaks.assign(m_peaks, m_peaks + 64);
        } else if (num_bars == 32) {
            out_spec.resize(32);
            out_peaks.resize(32);
            // Pairwise max pooling (64 -> 32)
            for (int i = 0; i < 32; ++i) {
                out_spec[i] = std::max(m_spectrum[i * 2], m_spectrum[i * 2 + 1]);
                out_peaks[i] = std::max(m_peaks[i * 2], m_peaks[i * 2 + 1]);
            }
        } else if (num_bars == 48) {
            out_spec.resize(48);
            out_peaks.resize(48);
            for (int i = 0; i < 48; ++i) {
                float idx_f = (static_cast<float>(i) / 47.0f) * 63.0f;
                int idx = static_cast<int>(idx_f);
                if (idx > 63) idx = 63;
                out_spec[i] = m_spectrum[idx];
                out_peaks[i] = m_peaks[idx];
            }
        } else {
            int n = std::min(num_bars, 64);
            out_spec.assign(m_spectrum, m_spectrum + n);
            out_peaks.assign(m_peaks, m_peaks + n);
        }
    }

    // Thread-safe fetch of band energies: (bass, mid, treble, rms)
    void get_band_energies(float& bass, float& mid, float& treble, float& rms) {
        std::lock_guard<std::mutex> lock(m_mutex);
        bass = m_band_energies[0];
        mid = m_band_energies[1];
        treble = m_band_energies[2];
        rms = m_band_energies[3];
    }

private:
    void write_pcm_samples(const float* samples, int num_samples, int num_channels) {
        if (num_samples <= 0 || !samples) return;

        for (int i = 0; i < num_samples; ++i) {
            float mono_val = 0.0f;
            if (num_channels >= 2) {
                mono_val = (samples[i * num_channels] + samples[i * num_channels + 1]) * 0.5f;
            } else {
                mono_val = samples[i];
            }

            m_ring_buffer[m_ring_write_pos] = mono_val;
            m_ring_write_pos = (m_ring_write_pos + 1) % RING_BUFFER_SIZE;
        }
    }

    void extract_latest_fft_window(float* out_window) {
        int read_pos = (m_ring_write_pos - FastFFT1024::FFT_SIZE + RING_BUFFER_SIZE) % RING_BUFFER_SIZE;
        for (int i = 0; i < FastFFT1024::FFT_SIZE; ++i) {
            out_window[i] = m_ring_buffer[read_pos];
            read_pos = (read_pos + 1) % RING_BUFFER_SIZE;
        }
    }

    void process_real_fft() {
        extract_latest_fft_window(m_raw_fft_buffer.data());
        m_fft.compute_magnitudes(m_raw_fft_buffer.data(), m_fft_magnitudes.data());

        float raw_bands[NUM_BINS];
        float power_bands[NUM_BINS];
        float max_power = 0.01f;

        // Logarithmic Bark frequency aggregation
        for (int i = 0; i < NUM_BINS; ++i) {
            int start = m_band_indices[i];
            int end = std::max(start + 1, m_band_indices[i + 1]);
            end = std::min(end, FastFFT1024::NUM_MAGNITUDES);

            float sum = 0.0f;
            int count = end - start;
            if (count > 0) {
                for (int k = start; k < end; ++k) {
                    sum += m_fft_magnitudes[k];
                }
                raw_bands[i] = (sum / static_cast<float>(count)) * m_freq_tilt[i];
            } else {
                raw_bands[i] = 0.0f;
            }

            power_bands[i] = sqrtf(std::max(0.0f, raw_bands[i]));
            if (power_bands[i] > max_power) {
                max_power = power_bands[i];
            }
        }

        // Dynamic AGC normalization
        if (max_power > m_agc_max) {
            m_agc_max = m_agc_max * 0.85f + max_power * 0.15f;
        } else {
            m_agc_max = std::max(0.05f, m_agc_max * 0.992f);
        }

        float sens = m_sensitivity.load();
        float norm_bands[NUM_BINS];
        for (int i = 0; i < NUM_BINS; ++i) {
            float val = (power_bands[i] / (m_agc_max + 1e-4f)) * sens;
            norm_bands[i] = std::max(0.0f, std::min(1.0f, val));
        }

        // Ballistics & Peak Physics
        {
            std::lock_guard<std::mutex> lock(m_mutex);

            for (int i = 0; i < NUM_BINS; ++i) {
                float cur = m_spectrum[i];
                float target = norm_bands[i];
                float diff = target - cur;

                if (diff > 0.0f) {
                    float attack_rate = (diff > 0.08f) ? 0.88f : 0.60f;
                    cur += diff * attack_rate;
                } else {
                    cur += diff * 0.22f; // Smooth punchy bounce
                }
                m_spectrum[i] = cur;

                // Peak dot physics with gravity acceleration
                float p = m_peaks[i];
                float v = m_peak_velocities[i];

                if (cur >= p) {
                    p = cur;
                    v = 0.0f;
                } else {
                    v += 0.008f;
                    p = std::max(cur, p - v);
                }
                m_peaks[i] = p;
                m_peak_velocities[i] = v;
            }

            // Calculate band energies
            int idx_bass = std::max(1, static_cast<int>(NUM_BINS * 0.22f));
            int idx_mid = std::max(idx_bass + 1, static_cast<int>(NUM_BINS * 0.65f));

            auto calc_punchy = [](const float* arr, int start, int end) -> float {
                int count = end - start;
                if (count <= 0) return 0.0f;
                float mx = 0.0f;
                float sum = 0.0f;
                for (int i = start; i < end; ++i) {
                    if (arr[i] > mx) mx = arr[i];
                    sum += arr[i];
                }
                float mn = sum / static_cast<float>(count);
                float val = 0.70f * mx + 0.30f * mn;
                return std::max(0.0f, std::min(1.0f, val));
            };

            m_band_energies[0] = calc_punchy(m_spectrum, 0, idx_bass);
            m_band_energies[1] = calc_punchy(m_spectrum, idx_bass, idx_mid);
            m_band_energies[2] = calc_punchy(m_spectrum, idx_mid, NUM_BINS);

            float total_sum = 0.0f;
            for (int i = 0; i < NUM_BINS; ++i) total_sum += m_spectrum[i];
            m_band_energies[3] = std::max(0.0f, std::min(1.0f, (total_sum / static_cast<float>(NUM_BINS)) * 1.2f));
        }
    }

    void process_procedural_fallback() {
        m_phase += 0.08f;
        float bands[NUM_BINS];
        float sens = m_sensitivity.load();

        float kick = powf(sinf(m_phase * 1.5f), 4.0f) * 0.85f;
        float mid = (sinf(m_phase * 0.8f + 1.2f) * 0.5f + 0.5f) * 0.65f;
        float high = (sinf(m_phase * 2.2f + 2.5f) * 0.5f + 0.5f) * 0.45f;

        for (int i = 0; i < NUM_BINS; ++i) {
            float ratio = static_cast<float>(i) / static_cast<float>(NUM_BINS);
            float fi = static_cast<float>(i);

            float shape = 0.0f;
            if (ratio < 0.25f) {
                shape = (1.0f - ratio * 2.5f) * kick + sinf(m_phase * 2.0f + fi * 0.5f) * 0.15f;
            } else if (ratio < 0.65f) {
                shape = mid * cosf((ratio - 0.4f) * 5.0f) + sinf(m_phase * 1.2f + fi * 0.2f) * 0.12f;
            } else {
                shape = high * (1.0f - (ratio - 0.65f) * 2.0f) + sinf(m_phase * 3.0f + fi * 0.4f) * 0.1f;
            }
            float noise = (sinf(m_phase * 5.0f + fi * 1.7f) * 0.5f + 0.5f) * 0.1f;
            bands[i] = std::max(0.05f, std::min(0.95f, (shape + noise) * sens));
        }

        {
            std::lock_guard<std::mutex> lock(m_mutex);

            for (int i = 0; i < NUM_BINS; ++i) {
                float cur = m_spectrum[i];
                float target = bands[i];
                float diff = target - cur;

                if (diff > 0.0f) {
                    cur += diff * 0.70f;
                } else {
                    cur += diff * 0.15f;
                }
                m_spectrum[i] = cur;

                float p = m_peaks[i];
                float v = m_peak_velocities[i];
                if (cur >= p) {
                    p = cur;
                    v = 0.0f;
                } else {
                    v += 0.006f;
                    p = std::max(cur, p - v);
                }
                m_peaks[i] = p;
                m_peak_velocities[i] = v;
            }

            int idx_bass = std::max(1, static_cast<int>(NUM_BINS * 0.22f));
            int idx_mid = std::max(idx_bass + 1, static_cast<int>(NUM_BINS * 0.65f));

            m_band_energies[0] = std::max(0.0f, std::min(1.0f, m_spectrum[2] * 1.1f));
            m_band_energies[1] = std::max(0.0f, std::min(1.0f, m_spectrum[idx_bass + 2] * 1.0f));
            m_band_energies[2] = std::max(0.0f, std::min(1.0f, m_spectrum[idx_mid + 2] * 0.9f));
            m_band_energies[3] = 0.5f;
        }
    }

    void decay_to_zero() {
        std::lock_guard<std::mutex> lock(m_mutex);
        for (int i = 0; i < NUM_BINS; ++i) {
            m_spectrum[i] *= 0.85f;
            m_peaks[i] = std::max(0.0f, m_peaks[i] - 0.02f);
            m_peak_velocities[i] *= 0.85f;
        }
        for (int i = 0; i < 4; ++i) {
            m_band_energies[i] *= 0.85f;
        }
    }

    void worker_loop() {
        CoInitializeEx(NULL, COINIT_MULTITHREADED);

        IMMDeviceEnumerator* pEnumerator = NULL;
        IMMDevice* pDevice = NULL;
        IAudioClient* pAudioClient = NULL;
        IAudioCaptureClient* pCaptureClient = NULL;
        WAVEFORMATEX* pFormat = NULL;

        bool wasapi_active = false;
        DWORD last_reconnect_time = 0;

        while (m_running.load()) {
            DWORD now = GetTickCount();

            // Attempt WASAPI Loopback Connection if not connected
            if (!wasapi_active && (now - last_reconnect_time > 2000)) {
                last_reconnect_time = now;

                if (pCaptureClient) { pCaptureClient->Release(); pCaptureClient = NULL; }
                if (pAudioClient) { pAudioClient->Release(); pAudioClient = NULL; }
                if (pDevice) { pDevice->Release(); pDevice = NULL; }
                if (pEnumerator) { pEnumerator->Release(); pEnumerator = NULL; }
                if (pFormat) { CoTaskMemFree(pFormat); pFormat = NULL; }

                HRESULT hr = CoCreateInstance(
                    __uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                    __uuidof(IMMDeviceEnumerator), (void**)&pEnumerator
                );

                if (SUCCEEDED(hr) && pEnumerator) {
                    hr = pEnumerator->GetDefaultAudioEndpoint(eRender, eConsole, &pDevice);
                    if (SUCCEEDED(hr) && pDevice) {
                        hr = pDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&pAudioClient);
                        if (SUCCEEDED(hr) && pAudioClient) {
                            hr = pAudioClient->GetMixFormat(&pFormat);
                            if (SUCCEEDED(hr) && pFormat) {
                                if (pFormat->nSamplesPerSec > 0 && pFormat->nSamplesPerSec != m_sample_rate) {
                                    recompute_log_bands(static_cast<int>(pFormat->nSamplesPerSec));
                                }

                                // 20ms buffer with LOOPBACK flag
                                REFERENCE_TIME hnsBuffer = 200000;
                                hr = pAudioClient->Initialize(
                                    AUDCLNT_SHAREMODE_SHARED,
                                    AUDCLNT_STREAMFLAGS_LOOPBACK,
                                    hnsBuffer, 0, pFormat, NULL
                                );

                                if (SUCCEEDED(hr)) {
                                    hr = pAudioClient->GetService(__uuidof(IAudioCaptureClient), (void**)&pCaptureClient);
                                    if (SUCCEEDED(hr) && pCaptureClient) {
                                        hr = pAudioClient->Start();
                                        if (SUCCEEDED(hr)) {
                                            wasapi_active = true;
                                            m_wasapi_active.store(true);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Capture available audio packets
            bool got_real_audio = false;
            if (wasapi_active && pCaptureClient) {
                UINT32 packetSize = 0;
                HRESULT hr = pCaptureClient->GetNextPacketSize(&packetSize);

                while (SUCCEEDED(hr) && packetSize > 0) {
                    BYTE* pData = NULL;
                    UINT32 numFrames = 0;
                    DWORD flags = 0;

                    hr = pCaptureClient->GetBuffer(&pData, &numFrames, &flags, NULL, NULL);
                    if (SUCCEEDED(hr) && numFrames > 0) {
                        int channels = pFormat ? pFormat->nChannels : 2;

                        if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                            std::vector<float> zeros(numFrames, 0.0f);
                            write_pcm_samples(zeros.data(), numFrames, 1);
                        } else if (pData) {
                            const float* float_samples = reinterpret_cast<const float*>(pData);
                            write_pcm_samples(float_samples, numFrames, channels);
                            got_real_audio = true;
                        }

                        pCaptureClient->ReleaseBuffer(numFrames);
                    } else {
                        break;
                    }

                    hr = pCaptureClient->GetNextPacketSize(&packetSize);
                }

                if (FAILED(hr)) {
                    // Device disconnected or invalidated -> trigger reconnect
                    wasapi_active = false;
                    m_wasapi_active.store(false);
                }
            }

            // Process Spectrum Physics
            if (m_is_playing.load()) {
                if (got_real_audio) {
                    process_real_fft();
                } else {
                    process_procedural_fallback();
                }
            } else {
                decay_to_zero();
            }

            // Hardware Eco Pacing Sleep
            float target_fps = m_target_fps.load();
            DWORD sleep_ms = 10;
            if (m_eco_mode.load()) {
                sleep_ms = static_cast<DWORD>(std::max(10.0f, std::min(40.0f, 1000.0f / (target_fps * 1.5f))));
            }
            if (!m_is_playing.load()) {
                sleep_ms = 50; // Ultra low-power 0% CPU sleep when paused
            }

            WaitForSingleObject(m_hStopEvent, sleep_ms);
        }

        // Cleanup COM on exit
        if (pCaptureClient) pCaptureClient->Release();
        if (pAudioClient) {
            pAudioClient->Stop();
            pAudioClient->Release();
        }
        if (pDevice) pDevice->Release();
        if (pEnumerator) pEnumerator->Release();
        if (pFormat) CoTaskMemFree(pFormat);

        CoUninitialize();
    }

private:
    std::atomic<bool> m_running;
    std::atomic<bool> m_is_playing;
    std::atomic<bool> m_wasapi_active;
    std::atomic<float> m_sensitivity;
    std::atomic<float> m_target_fps;
    std::atomic<bool> m_eco_mode;

    int m_sample_rate;
    float m_agc_max;
    float m_phase;

    HANDLE m_hStopEvent;
    HANDLE m_hAudioEvent;
    std::thread m_worker_thread;
    std::mutex m_mutex;

    FastFFT1024 m_fft;
    std::vector<float> m_ring_buffer;
    int m_ring_write_pos;

    std::vector<float> m_raw_fft_buffer;
    std::vector<float> m_fft_magnitudes;

    int m_band_indices[NUM_BINS + 1];
    float m_freq_tilt[NUM_BINS];

    float m_spectrum[NUM_BINS];
    float m_peaks[NUM_BINS];
    float m_peak_velocities[NUM_BINS];
    float m_band_energies[4];
};


// Global Engine Instance Pointer
static AudioSpectrumNativeEngine* g_engine = NULL;


// ==============================================================================
// 3. PYTHON C-API MODULE BINDINGS
// ==============================================================================

static PyObject* py_start(PyObject* self, PyObject* args) {
    if (!g_engine) {
        g_engine = new AudioSpectrumNativeEngine();
    }
    g_engine->start();
    Py_RETURN_NONE;
}

static PyObject* py_stop(PyObject* self, PyObject* args) {
    if (g_engine) {
        g_engine->stop();
    }
    Py_RETURN_NONE;
}

static PyObject* py_set_playback_state(PyObject* self, PyObject* args) {
    int is_playing = 0;
    if (!PyArg_ParseTuple(args, "p", &is_playing)) {
        return NULL;
    }
    if (g_engine) {
        g_engine->set_playback_state(is_playing != 0);
    }
    Py_RETURN_NONE;
}

static PyObject* py_set_sensitivity(PyObject* self, PyObject* args) {
    float sens = 1.0f;
    if (!PyArg_ParseTuple(args, "f", &sens)) {
        return NULL;
    }
    if (g_engine) {
        g_engine->set_sensitivity(sens);
    }
    Py_RETURN_NONE;
}

static PyObject* py_set_target_fps(PyObject* self, PyObject* args) {
    float fps = 60.0f;
    if (!PyArg_ParseTuple(args, "f", &fps)) {
        return NULL;
    }
    if (g_engine) {
        g_engine->set_target_fps(fps);
    }
    Py_RETURN_NONE;
}

static PyObject* py_set_eco_mode(PyObject* self, PyObject* args) {
    int eco = 1;
    if (!PyArg_ParseTuple(args, "p", &eco)) {
        return NULL;
    }
    if (g_engine) {
        g_engine->set_eco_mode(eco != 0);
    }
    Py_RETURN_NONE;
}

static PyObject* py_is_wasapi_active(PyObject* self, PyObject* args) {
    if (!g_engine) {
        Py_RETURN_FALSE;
    }
    if (g_engine->is_wasapi_active()) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject* py_get_spectrum_snapshot(PyObject* self, PyObject* args) {
    int num_bars = 32;
    if (!PyArg_ParseTuple(args, "|i", &num_bars)) {
        return NULL;
    }

    if (!g_engine) {
        g_engine = new AudioSpectrumNativeEngine();
    }

    std::vector<float> spec;
    std::vector<float> peaks;
    g_engine->get_spectrum_snapshot(num_bars, spec, peaks);

    Py_ssize_t n = spec.size();
    PyObject* py_spec = PyList_New(n);
    PyObject* py_peaks = PyList_New(n);

    for (Py_ssize_t i = 0; i < n; ++i) {
        PyList_SET_ITEM(py_spec, i, PyFloat_FromDouble(spec[i]));
        PyList_SET_ITEM(py_peaks, i, PyFloat_FromDouble(peaks[i]));
    }

    PyObject* result = PyTuple_Pack(2, py_spec, py_peaks);
    Py_DECREF(py_spec);
    Py_DECREF(py_peaks);
    return result;
}

static PyObject* py_get_band_energies(PyObject* self, PyObject* args) {
    if (!g_engine) {
        g_engine = new AudioSpectrumNativeEngine();
    }

    float bass = 0.0f, mid = 0.0f, treble = 0.0f, rms = 0.0f;
    g_engine->get_band_energies(bass, mid, treble, rms);

    return Py_BuildValue("(ffff)", bass, mid, treble, rms);
}

// Method definitions
static PyMethodDef AudioSpectrumMethods[] = {
    {"start", py_start, METH_NOARGS, "Start the background audio analysis engine."},
    {"stop", py_stop, METH_NOARGS, "Stop the background audio analysis engine."},
    {"set_playback_state", py_set_playback_state, METH_VARARGS, "Notify playback active state."},
    {"set_sensitivity", py_set_sensitivity, METH_VARARGS, "Set visualizer gain sensitivity."},
    {"set_target_fps", py_set_target_fps, METH_VARARGS, "Set target render FPS for pacing."},
    {"set_eco_mode", py_set_eco_mode, METH_VARARGS, "Toggle low-power eco pacing."},
    {"is_wasapi_active", py_is_wasapi_active, METH_NOARGS, "Check if WASAPI loopback is capturing real audio."},
    {"get_spectrum_snapshot", py_get_spectrum_snapshot, METH_VARARGS, "Get normalized spectrum snapshot (spec_list, peak_list)."},
    {"get_band_energies", py_get_band_energies, METH_NOARGS, "Get (bass, mid, treble, rms) energy tuple."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef audiospectrummodule = {
    PyModuleDef_HEAD_INIT,
    "audio_spectrum_native",
    "High-Performance Native Audio Spectrum Engine for HELXAIC",
    -1,
    AudioSpectrumMethods
};

PyMODINIT_FUNC PyInit_audio_spectrum_native(void) {
    return PyModule_Create(&audiospectrummodule);
}
