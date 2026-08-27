"""
High-Performance Audio Spectrum Engine for HELXAIC Visualizers.

Captures real-time audio from Windows default playback device via WASAPI Loopback,
computes FFT frequency bins using NumPy, applies logarithmic/Bark scaling,
and performs ballistic temporal smoothing with gravity-accelerated peak dots.

Component Name: AudioSpectrumEngine
"""

import sys
import time
import math
import threading
import sys
import time
import math
import threading
from typing import Tuple, Optional
import numpy as np

# Windows COM / WASAPI ctypes setup
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes, POINTER, Structure, c_void_p, c_uint32, c_int, byref, cast, c_ubyte, c_longlong, c_float, WINFUNCTYPE
    import uuid

    # Use an isolated WinDLL instance so mutated argtypes from launcher.py do not collide
    ole32 = ctypes.WinDLL("ole32.dll")
    ole32.CoCreateInstance.argtypes = [c_void_p, c_void_p, wintypes.DWORD, c_void_p, POINTER(c_void_p)]
    ole32.CoCreateInstance.restype = wintypes.HRESULT

    class GUID(Structure):
        _fields_ = [
            ("Data1", c_uint32),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", c_ubyte * 8)
        ]
        def __init__(self, s):
            u = uuid.UUID(s)
            super().__init__()
            self.Data1 = u.time_low
            self.Data2 = u.time_mid
            self.Data3 = u.time_hi_version
            self.Data4 = (c_ubyte * 8)(*u.bytes[8:])

    CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
    IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
    IID_IAudioClient = GUID("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
    IID_IAudioCaptureClient = GUID("C8ADBD64-E71E-48a0-A4DE-185C395CD317")

    class WAVEFORMATEX(Structure):
        _fields_ = [
            ("wFormatTag", wintypes.WORD),
            ("nChannels", wintypes.WORD),
            ("nSamplesPerSec", wintypes.DWORD),
            ("nAvgBytesPerSec", wintypes.DWORD),
            ("nBlockAlign", wintypes.WORD),
            ("wBitsPerSample", wintypes.WORD),
            ("cbSize", wintypes.WORD)
        ]

    def _call_com(interface_ptr, method_idx, restype, *argtypes):
        vtbl_ptr = cast(interface_ptr, POINTER(c_void_p)).contents
        vtbl = cast(vtbl_ptr, POINTER(c_void_p))
        func_ptr = vtbl[method_idx]
        func = WINFUNCTYPE(restype, c_void_p, *argtypes)(func_ptr)
        return func


class AudioSpectrumEngine:
    """
    Thread-safe real-time audio spectrum & peak analysis engine.
    
    Component Name: AudioSpectrumEngine
    """
    _INSTANCE: Optional['AudioSpectrumEngine'] = None

    @classmethod
    def get_instance(cls) -> 'AudioSpectrumEngine':
        if cls._INSTANCE is None:
            cls._INSTANCE = AudioSpectrumEngine()
        return cls._INSTANCE

    def __init__(self, fft_size: int = 1024, sample_rate: int = 48000, num_bins: int = 64):
        self.fft_size = fft_size
        self.sample_rate = sample_rate
        self.num_bins = num_bins
        
        # Audio buffers (mono) - 4x FFT buffer for ultra-smooth sliding window
        self._raw_pcm_buffer = np.zeros(fft_size * 4, dtype=np.float32)
        
        # Spectrum state (64 frequency bands)
        self._spectrum = np.zeros(64, dtype=np.float32)
        self._peaks = np.zeros(64, dtype=np.float32)
        self._peak_velocities = np.zeros(64, dtype=np.float32)
        
        # AGC (Automatic Gain Control)
        self._agc_max = 0.08
        self._sensitivity = 1.0
        
        # Thread control
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_playing = False
        self._wasapi_active = False  # Diagnostic flag readable from main thread
        self._playback_just_started = False  # Trigger immediate WASAPI reconnect
        
        # Procedural synthesizer phase trackers for fallback
        self._phase = 0.0
        
        # Precompute window & band indices
        self._hann_window = np.hanning(self.fft_size).astype(np.float32)
        self._band_indices_64 = self._compute_log_bands(64, self.fft_size, self.sample_rate)

    def _compute_log_bands(self, num_bins: int, fft_size: int, sample_rate: int) -> np.ndarray:
        """Compute logarithmic bin edges tuned for musical frequencies (28Hz to 16kHz)."""
        min_freq = 28.0
        max_freq = 16000.0
        freqs = np.logspace(np.log10(min_freq), np.log10(max_freq), num_bins + 1)
        fft_freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
        indices = np.searchsorted(fft_freqs, freqs)
        indices[0] = 1  # Skip DC offset (0 Hz)
        for i in range(1, len(indices)):
            if indices[i] <= indices[i-1]:
                indices[i] = indices[i-1] + 1
        indices[-1] = min(len(fft_freqs), indices[-1])
        return indices

    def set_playback_state(self, is_playing: bool):
        """Notify the engine of player state for render gating."""
        was_playing = self._is_playing
        self._is_playing = bool(is_playing)
        # Trigger immediate WASAPI reconnection when playback starts
        if self._is_playing and not was_playing:
            self._playback_just_started = True

    def set_sensitivity(self, sens: float):
        """Set visualizer gain sensitivity multiplier (0.5x to 3.0x)."""
        self._sensitivity = max(0.2, min(5.0, float(sens)))

    def start(self):
        """Start the background audio analysis thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="HELXAID_AudioSpectrumEngine")
        self._thread.start()

    def stop(self):
        """Stop background capture and reset state."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.3)
        self._thread = None

    def _release_com_safe(self, ptr):
        """Safely release a COM interface pointer via IUnknown::Release (VTable Index 2)."""
        if ptr and ptr.value:
            try:
                _call_com(ptr, 2, c_int)(ptr)
            except Exception:
                pass

    def _worker_loop(self):
        """Main background worker: Attempts WASAPI Loopback, falls back to harmonic engine."""
        if IS_WINDOWS:
            try:
                # Use MTA (COINIT_MULTITHREADED=0) for reliable WASAPI on background threads
                ole32.CoInitializeEx(None, 0)
            except Exception:
                try:
                    ole32.CoInitialize(None)
                except Exception:
                    pass

        wasapi_active = False
        pEnumerator = None
        pDevice = None
        pAudioClient = None
        pCaptureClient = None
        pFormat = None
        _wasapi_logged = False

        last_wasapi_init_time = 0.0

        while self._running:
            now = time.time()

            # Trigger immediate WASAPI reconnect when playback starts
            if self._playback_just_started and not wasapi_active:
                self._playback_just_started = False
                last_wasapi_init_time = 0.0  # Force immediate retry

            # Attempt to initialize WASAPI loopback if on Windows and not yet connected
            if IS_WINDOWS and not wasapi_active and (now - last_wasapi_init_time > 2.0):
                last_wasapi_init_time = now
                _wasapi_logged = False

                # Clean up any stale COM objects from previous attempts
                if pCaptureClient:
                    self._release_com_safe(pCaptureClient)
                    pCaptureClient = None
                if pAudioClient:
                    self._release_com_safe(pAudioClient)
                    pAudioClient = None
                if pDevice:
                    self._release_com_safe(pDevice)
                    pDevice = None
                if pEnumerator:
                    self._release_com_safe(pEnumerator)
                    pEnumerator = None
                pFormat = None

                try:
                    pEnumerator = c_void_p()
                    hr = ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, 1, byref(IID_IMMDeviceEnumerator), byref(pEnumerator))
                    if hr != 0 or not pEnumerator.value:
                        print(f"[Visualizer] WASAPI: CoCreateInstance failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    pDevice = c_void_p()
                    hr = _call_com(pEnumerator, 4, c_int, c_int, c_int, POINTER(c_void_p))(pEnumerator, 0, 0, byref(pDevice))
                    if hr != 0 or not pDevice.value:
                        print(f"[Visualizer] WASAPI: GetDefaultAudioEndpoint failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    pAudioClient = c_void_p()
                    hr = _call_com(pDevice, 3, c_int, c_void_p, wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                        pDevice, byref(IID_IAudioClient), 7, None, byref(pAudioClient)
                    )
                    if hr != 0 or not pAudioClient.value:
                        print(f"[Visualizer] WASAPI: Activate IAudioClient failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    pFormat = POINTER(WAVEFORMATEX)()
                    hr = _call_com(pAudioClient, 8, c_int, POINTER(POINTER(WAVEFORMATEX)))(pAudioClient, byref(pFormat))
                    if hr != 0 or not pFormat:
                        print(f"[Visualizer] WASAPI: GetMixFormat failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    # Adapt sample rate dynamically if changed
                    if pFormat.contents.nSamplesPerSec > 0 and pFormat.contents.nSamplesPerSec != self.sample_rate:
                        self.sample_rate = int(pFormat.contents.nSamplesPerSec)
                        self._band_indices_64 = self._compute_log_bands(64, self.fft_size, self.sample_rate)

                    # Request low-latency 20ms buffer with LOOPBACK flag (0x00020000)
                    hnsBuffer = 200000  # 20ms in 100ns units
                    hr = _call_com(pAudioClient, 3, c_int, c_int, wintypes.DWORD, c_longlong, c_longlong, c_void_p, c_void_p)(
                        pAudioClient, 0, 0x00020000, hnsBuffer, 0, pFormat, None
                    )
                    if hr != 0:
                        # 20ms failed - release and re-activate IAudioClient for fallback
                        self._release_com_safe(pAudioClient)
                        pAudioClient = c_void_p()
                        hr2 = _call_com(pDevice, 3, c_int, c_void_p, wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                            pDevice, byref(IID_IAudioClient), 7, None, byref(pAudioClient)
                        )
                        if hr2 == 0 and pAudioClient.value:
                            pFormat = POINTER(WAVEFORMATEX)()
                            _call_com(pAudioClient, 8, c_int, POINTER(POINTER(WAVEFORMATEX)))(pAudioClient, byref(pFormat))
                            hnsBuffer = 500000  # 50ms buffer fallback
                            hr = _call_com(pAudioClient, 3, c_int, c_int, wintypes.DWORD, c_longlong, c_longlong, c_void_p, c_void_p)(
                                pAudioClient, 0, 0x00020000, hnsBuffer, 0, pFormat, None
                            )
                        else:
                            continue

                    if hr != 0:
                        print(f"[Visualizer] WASAPI: Initialize failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    pCaptureClient = c_void_p()
                    hr = _call_com(pAudioClient, 14, c_int, c_void_p, POINTER(c_void_p))(
                        pAudioClient, byref(IID_IAudioCaptureClient), byref(pCaptureClient)
                    )
                    if hr != 0 or not pCaptureClient.value:
                        print(f"[Visualizer] WASAPI: GetService CaptureClient failed (hr=0x{hr & 0xFFFFFFFF:08X})")
                        continue

                    # IAudioClient::Start (VTable Index 10)
                    hr_start = _call_com(pAudioClient, 10, c_int)(pAudioClient)
                    if hr_start == 0:
                        wasapi_active = True
                        self._wasapi_active = True
                        sr = pFormat.contents.nSamplesPerSec if pFormat else 0
                        ch = pFormat.contents.nChannels if pFormat else 0
                        print(f"[Visualizer] WASAPI Loopback: Active (SR={sr}Hz, CH={ch}, buf={hnsBuffer // 10000}ms)")
                    else:
                        print(f"[Visualizer] WASAPI: Start failed (hr=0x{hr_start & 0xFFFFFFFF:08X})")
                except Exception as e:
                    wasapi_active = False
                    self._wasapi_active = False
                    print(f"[Visualizer] WASAPI init exception: {e}")

            # Read audio data from WASAPI if active (drain all available packets)
            got_real_audio = False
            if wasapi_active and pCaptureClient and pCaptureClient.value:
                try:
                    while True:
                        packetSize = wintypes.DWORD()
                        hr = _call_com(pCaptureClient, 5, c_int, POINTER(wintypes.DWORD))(pCaptureClient, byref(packetSize))
                        if hr != 0 or packetSize.value == 0:
                            break

                        pData = POINTER(c_float)()
                        numFrames = wintypes.DWORD()
                        flags = wintypes.DWORD()
                        pos = c_longlong()
                        qpc = c_longlong()
                        
                        hr_buf = _call_com(
                            pCaptureClient, 3, c_int,
                            POINTER(POINTER(c_float)), POINTER(wintypes.DWORD), POINTER(wintypes.DWORD),
                            POINTER(c_longlong), POINTER(c_longlong)
                        )(pCaptureClient, byref(pData), byref(numFrames), byref(flags), byref(pos), byref(qpc))
                        
                        if hr_buf == 0 and numFrames.value > 0:
                            n_channels = pFormat.contents.nChannels if pFormat else 2
                            total_samples = numFrames.value * n_channels
                            
                            # Check for silence flag (0x02 = AUDCLNT_BUFFERFLAGS_SILENT)
                            if flags.value & 2:
                                mono = np.zeros(numFrames.value, dtype=np.float32)
                            else:
                                arr = np.ctypeslib.as_array(pData, shape=(total_samples,))
                                if n_channels >= 2:
                                    mono = (arr[0::n_channels] + arr[1::n_channels]) * 0.5
                                else:
                                    mono = arr.copy()
                            
                            # Sliding window buffer fill
                            n = len(mono)
                            buf_len = len(self._raw_pcm_buffer)
                            if n > 0:
                                if n >= buf_len:
                                    self._raw_pcm_buffer[:] = mono[-buf_len:]
                                else:
                                    self._raw_pcm_buffer[:-n] = self._raw_pcm_buffer[n:]
                                    self._raw_pcm_buffer[-n:] = mono
                                got_real_audio = True

                            _call_com(pCaptureClient, 4, c_int, wintypes.DWORD)(pCaptureClient, numFrames.value)
                        else:
                            break
                except Exception as e:
                    if not _wasapi_logged:
                        print(f"[Visualizer] WASAPI capture error: {e}, reconnecting...")
                        _wasapi_logged = True
                    wasapi_active = False
                    self._wasapi_active = False
                    self._release_com_safe(pCaptureClient)
                    pCaptureClient = None
                    if pAudioClient:
                        try:
                            _call_com(pAudioClient, 11, c_int)(pAudioClient)
                        except Exception:
                            pass
                        self._release_com_safe(pAudioClient)
                        pAudioClient = None
                    self._release_com_safe(pDevice)
                    pDevice = None
                    self._release_com_safe(pEnumerator)
                    pEnumerator = None
                    pFormat = None

            # Process FFT or Procedural fallback ONLY when HELXAIC is actively playing
            if self._is_playing:
                if got_real_audio:
                    self._process_real_fft()
                else:
                    self._process_procedural_fallback()
            else:
                self._decay_to_zero()

            time.sleep(0.010)  # Ultra-responsive 100 Hz processing rate (10ms)

        # Cleanup COM on exit
        if wasapi_active and pAudioClient:
            try:
                _call_com(pAudioClient, 11, c_int)(pAudioClient)
            except Exception:
                pass
        if IS_WINDOWS:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass

    def _process_real_fft(self):
        """Compute FFT, band aggregation, equal-loudness weighting, and ballistic physics."""
        buf = self._raw_pcm_buffer[-self.fft_size:]
        windowed = buf * self._hann_window
        fft_complex = np.fft.rfft(windowed)
        magnitudes = np.abs(fft_complex)

        indices = self._band_indices_64
        n_bins = len(indices) - 1
        raw_bands = np.zeros(n_bins, dtype=np.float32)

        # Pink noise tilt compensation (+3dB per octave for high frequencies)
        freq_tilt = 1.0 + (np.arange(n_bins, dtype=np.float32) / float(n_bins)) * 2.2

        for i in range(n_bins):
            start = indices[i]
            end = max(start + 1, indices[i+1])
            if start < len(magnitudes):
                chunk = magnitudes[start:min(end, len(magnitudes))]
                raw_bands[i] = np.mean(chunk) * freq_tilt[i]

        # Convert to perceptual power curve (sqrt compression for punchy dynamic range)
        power_bands = np.sqrt(np.maximum(0.0, raw_bands))

        # Dynamic AGC normalization
        current_peak = float(np.max(power_bands)) if len(power_bands) > 0 else 0.01
        if current_peak > self._agc_max:
            self._agc_max = self._agc_max * 0.85 + current_peak * 0.15
        else:
            self._agc_max = max(0.05, self._agc_max * 0.992)

        norm_bands = np.clip((power_bands / (self._agc_max + 1e-4)) * self._sensitivity, 0.0, 1.0)

        # High-speed vectorized ballistic physics smoothing with adaptive transient snap
        with self._lock:
            cur = self._spectrum[:n_bins]
            target = norm_bands[:n_bins]
            diff = target - cur
            attack_mask = diff > 0
            
            # Instant transient snap (0.88) on beats, smooth rise (0.60) on subtle melodies
            attack_rate = np.where(diff > 0.08, 0.88, 0.60)
            cur[attack_mask] += diff[attack_mask] * attack_rate[attack_mask]
            # Smooth exponential decay (0.22) for punchy bounce
            cur[~attack_mask] += diff[~attack_mask] * 0.22
            self._spectrum[:n_bins] = cur

            # Vectorized floating peak dots physics with gravity
            p = self._peaks[:n_bins]
            v = self._peak_velocities[:n_bins]
            peak_hit = cur >= p
            p[peak_hit] = cur[peak_hit]
            v[peak_hit] = 0.0

            falling_mask = ~peak_hit
            v[falling_mask] += 0.008
            p[falling_mask] = np.maximum(cur[falling_mask], p[falling_mask] - v[falling_mask])
            self._peaks[:n_bins] = p
            self._peak_velocities[:n_bins] = v

    def _process_procedural_fallback(self):
        """High-grade organic procedural audio wave simulation when playing without hardware audio tap."""
        self._phase += 0.08
        n_bins = 64
        
        i_arr = np.arange(n_bins, dtype=np.float32)
        ratio = i_arr / float(n_bins)
        
        kick = (math.sin(self._phase * 1.5) ** 4) * 0.85
        mid = (math.sin(self._phase * 0.8 + 1.2) * 0.5 + 0.5) * 0.65
        high = (math.sin(self._phase * 2.2 + 2.5) * 0.5 + 0.5) * 0.45
        
        low_part = (1.0 - ratio * 2.5) * kick + np.sin(self._phase * 2.0 + i_arr * 0.5) * 0.15
        mid_part = mid * np.cos((ratio - 0.4) * 5.0) + np.sin(self._phase * 1.2 + i_arr * 0.2) * 0.12
        high_part = high * (1.0 - (ratio - 0.65) * 2.0) + np.sin(self._phase * 3.0 + i_arr * 0.4) * 0.1
        
        shape = np.where(ratio < 0.25, low_part, np.where(ratio < 0.65, mid_part, high_part))
        noise = (np.sin(self._phase * 5.0 + i_arr * 1.7) * 0.5 + 0.5) * 0.1
        bands = np.clip((shape + noise) * self._sensitivity, 0.05, 0.95)

        with self._lock:
            cur = self._spectrum[:n_bins]
            target = bands[:n_bins]
            diff = target - cur
            attack_mask = diff > 0
            cur[attack_mask] += diff[attack_mask] * 0.70
            cur[~attack_mask] += diff[~attack_mask] * 0.15
            self._spectrum[:n_bins] = cur

            p = self._peaks[:n_bins]
            v = self._peak_velocities[:n_bins]
            peak_hit = cur >= p
            p[peak_hit] = cur[peak_hit]
            v[peak_hit] = 0.0

            falling_mask = ~peak_hit
            v[falling_mask] += 0.006
            p[falling_mask] = np.maximum(cur[falling_mask], p[falling_mask] - v[falling_mask])
            self._peaks[:n_bins] = p
            self._peak_velocities[:n_bins] = v

    def _decay_to_zero(self):
        """Smoothly drop all bars to zero when paused or stopped."""
        with self._lock:
            self._spectrum *= 0.85
            self._peaks = np.maximum(0.0, self._peaks - 0.02)
            self._peak_velocities *= 0.85

    def get_spectrum_snapshot(self, num_bars: int = 32) -> Tuple[np.ndarray, np.ndarray]:
        """
        Thread-safe fetch of current normalized spectrum values [0.0..1.0] and peak dots [0.0..1.0].
        Downsamples full 64-band spectrum cleanly across the requested number of bars.
        """
        with self._lock:
            if num_bars == 64 or num_bars >= len(self._spectrum):
                return self._spectrum[:num_bars].copy(), self._peaks[:num_bars].copy()
            elif num_bars == 32:
                # Pairwise max pooling (64 -> 32) so every frequency band is represented!
                spec_32 = np.maximum(self._spectrum[0::2], self._spectrum[1::2])
                peaks_32 = np.maximum(self._peaks[0::2], self._peaks[1::2])
                return spec_32.copy(), peaks_32.copy()
            elif num_bars == 48:
                # Resample 64 -> 48 with interpolation
                indices = np.linspace(0, len(self._spectrum) - 1, 48).astype(int)
                return self._spectrum[indices].copy(), self._peaks[indices].copy()
            else:
                n = min(num_bars, len(self._spectrum))
                return self._spectrum[:n].copy(), self._peaks[:n].copy()

    def get_band_energies(self) -> Tuple[float, float, float, float]:
        """
        Thread-safe fetch of normalized audio energy bands for fluid waves:
        Returns: (bass_energy, mid_energy, treble_energy, total_rms) in range [0.0..1.0].
        """
        with self._lock:
            spec = self._spectrum
            n = len(spec)
            if n == 0:
                return (0.0, 0.0, 0.0, 0.0)
            
            idx_bass = max(1, int(n * 0.22))
            idx_mid = max(idx_bass + 1, int(n * 0.65))
            
            def _calc_punchy(sub):
                if len(sub) == 0:
                    return 0.0
                mx = float(np.max(sub))
                mn = float(np.mean(sub))
                # 70% peak transient + 30% sustained energy
                val = 0.70 * mx + 0.30 * mn
                return min(1.0, max(0.0, float(val)))

            bass = _calc_punchy(spec[:idx_bass])
            mid = _calc_punchy(spec[idx_bass:idx_mid])
            treble = _calc_punchy(spec[idx_mid:])
            total_rms = min(1.0, max(0.0, float(np.mean(spec) * 1.2)))
            
            return (bass, mid, treble, total_rms)

    # Alias for convenience
    get_spectrum_data = get_spectrum_snapshot

