"""
High-Performance Audio Spectrum Engine for HELXAIC Visualizers.

Automatically delegates to the ultra-fast C++ native engine (audio_spectrum_native.pyd)
for real-time WASAPI Loopback capture, in-place Radix-2 Real FFT, logarithmic Bark binning,
and ballistic physics with 0% GIL overhead. Includes a zero-crash optimized fallback mode.

Component Name: AudioSpectrumEngine
"""

import sys
import time
import math
import threading
from typing import Tuple, Optional, Any
import numpy as np

# Try importing the high-performance C++ Native Module
_NATIVE_ENGINE = None
try:
    import audio_spectrum_native as _NATIVE_ENGINE
    print("[AudioSpectrumEngine] Loaded high-performance C++ native engine (audio_spectrum_native).")
except Exception as _err:
    _NATIVE_ENGINE = None
    print(f"[AudioSpectrumEngine] Native engine not available ({_err}), using optimized fallback.")

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS and _NATIVE_ENGINE is None:
    import ctypes
    from ctypes import wintypes, POINTER, Structure, c_void_p, c_uint32, c_int, byref, cast, c_ubyte, c_longlong, c_float, WINFUNCTYPE
    import uuid

    # Use an isolated WinDLL instance
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

    # Pre-cached COM function pointer types to prevent memory churn
    _com_proto_cache = {}
    def _call_com_cached(interface_ptr, method_idx, restype, *argtypes):
        key = (method_idx, restype, argtypes)
        if key not in _com_proto_cache:
            _com_proto_cache[key] = WINFUNCTYPE(restype, c_void_p, *argtypes)
        proto = _com_proto_cache[key]
        vtbl_ptr = cast(interface_ptr, POINTER(c_void_p)).contents
        vtbl = cast(vtbl_ptr, POINTER(c_void_p))
        func_ptr = vtbl[method_idx]
        return proto(func_ptr)


class AudioSpectrumEngine:
    """
    Thread-safe real-time audio spectrum & peak analysis engine orchestrator.
    
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
        self._use_native = (_NATIVE_ENGINE is not None)
        
        # Fallback Engine State (initialized only if native C++ engine is absent)
        self._raw_pcm_buffer = None
        self._spectrum = None
        self._peaks = None
        self._peak_velocities = None
        self._band_energies = (0.0, 0.0, 0.0, 0.0)
        
        # AGC & Sensitivity
        self._agc_max = 0.08
        self._sensitivity = 1.0
        
        # Thread control
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_playing = False
        self._wasapi_active = False
        self._playback_just_started = False
        self._phase = 0.0
        
        # Target FPS & Hardware Eco Pacing
        self._target_fps = 60.0
        self._eco_mode = True
        
        # Precompute window & band indices for fallback only when needed
        self._hann_window = None
        self._band_indices_64 = None
        if not self._use_native:
            self._init_fallback_state()

    def _init_fallback_state(self):
        """Initialize fallback NumPy state only when C++ native engine is unavailable."""
        if self._raw_pcm_buffer is not None:
            return
        self._raw_pcm_buffer = np.zeros(self.fft_size * 4, dtype=np.float32)
        self._spectrum = np.zeros(64, dtype=np.float32)
        self._peaks = np.zeros(64, dtype=np.float32)
        self._peak_velocities = np.zeros(64, dtype=np.float32)
        self._hann_window = np.hanning(self.fft_size).astype(np.float32)
        self._band_indices_64 = self._compute_log_bands(64, self.fft_size, self.sample_rate)

    def set_target_fps(self, fps: float):
        """Set target rendering FPS to adaptively pace audio FFT compute loop."""
        try:
            val = float(fps)
            if val > 0:
                self._target_fps = val
                if self._use_native and _NATIVE_ENGINE:
                    _NATIVE_ENGINE.set_target_fps(self._target_fps)
        except Exception:
            pass

    def set_eco_mode(self, enabled: bool):
        """Toggle hardware eco mode for audio engine worker loop."""
        self._eco_mode = bool(enabled)
        if self._use_native and _NATIVE_ENGINE:
            _NATIVE_ENGINE.set_eco_mode(self._eco_mode)

    def _compute_log_bands(self, num_bins: int, fft_size: int, sample_rate: int) -> np.ndarray:
        """Compute logarithmic bin edges tuned for musical frequencies (28Hz to 16kHz)."""
        min_freq = 28.0
        max_freq = 16000.0
        freqs = np.logspace(np.log10(min_freq), np.log10(max_freq), num_bins + 1)
        fft_freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
        indices = np.searchsorted(fft_freqs, freqs)
        indices[0] = 1
        for i in range(1, len(indices)):
            if indices[i] <= indices[i-1]:
                indices[i] = indices[i-1] + 1
        indices[-1] = min(len(fft_freqs), indices[-1])
        return indices

    def set_playback_state(self, is_playing: bool):
        """Notify the engine of player state for render gating."""
        was_playing = self._is_playing
        self._is_playing = bool(is_playing)
        if self._use_native and _NATIVE_ENGINE:
            _NATIVE_ENGINE.set_playback_state(self._is_playing)
            return

        if self._is_playing and not was_playing:
            self._playback_just_started = True

    def set_sensitivity(self, sens: float):
        """Set visualizer gain sensitivity multiplier (0.5x to 3.0x)."""
        self._sensitivity = max(0.2, min(5.0, float(sens)))
        if self._use_native and _NATIVE_ENGINE:
            _NATIVE_ENGINE.set_sensitivity(self._sensitivity)

    def start(self):
        """Start the audio analysis engine."""
        if self._use_native and _NATIVE_ENGINE:
            _NATIVE_ENGINE.start()
            _NATIVE_ENGINE.set_playback_state(self._is_playing)
            _NATIVE_ENGINE.set_sensitivity(self._sensitivity)
            _NATIVE_ENGINE.set_target_fps(self._target_fps)
            _NATIVE_ENGINE.set_eco_mode(self._eco_mode)
            self._running = True
            return

        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="HELXAID_AudioSpectrumFallback")
        self._thread.start()

    def stop(self):
        """Stop audio analysis and reset state."""
        if self._use_native and _NATIVE_ENGINE:
            _NATIVE_ENGINE.stop()
            self._running = False
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.3)
        self._thread = None

    def is_wasapi_active(self) -> bool:
        """Check if real hardware WASAPI loopback audio is connected."""
        if self._use_native and _NATIVE_ENGINE:
            return _NATIVE_ENGINE.is_wasapi_active()
        return self._wasapi_active

    def get_spectrum_snapshot(self, num_bars: int = 32) -> Tuple[Any, Any]:
        """
        Thread-safe fetch of current normalized spectrum values [0.0..1.0] and peak dots [0.0..1.0].
        Downsamples full 64-band spectrum cleanly across the requested number of bars.
        """
        if self._use_native and _NATIVE_ENGINE:
            spec_list, peaks_list = _NATIVE_ENGINE.get_spectrum_snapshot(num_bars)
            return np.asarray(spec_list, dtype=np.float32), np.asarray(peaks_list, dtype=np.float32)

        with self._lock:
            if self._spectrum is None:
                self._init_fallback_state()
            if num_bars == 64 or num_bars >= len(self._spectrum):
                return self._spectrum[:num_bars].copy(), self._peaks[:num_bars].copy()
            elif num_bars == 32:
                spec_32 = np.maximum(self._spectrum[0::2], self._spectrum[1::2])
                peaks_32 = np.maximum(self._peaks[0::2], self._peaks[1::2])
                return spec_32.copy(), peaks_32.copy()
            elif num_bars == 48:
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
        if self._use_native and _NATIVE_ENGINE:
            return _NATIVE_ENGINE.get_band_energies()

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
                val = 0.70 * mx + 0.30 * mn
                return min(1.0, max(0.0, float(val)))

            bass = _calc_punchy(spec[:idx_bass])
            mid = _calc_punchy(spec[idx_bass:idx_mid])
            treble = _calc_punchy(spec[idx_mid:])
            total_rms = min(1.0, max(0.0, float(np.mean(spec) * 1.2)))
            
            return (bass, mid, treble, total_rms)

    get_spectrum_data = get_spectrum_snapshot

    # ==========================================================================
    # FALLBACK WORKER LOOP (FOR NON-NATIVE ENVIRONMENTS)
    # ==========================================================================

    def _release_com_safe(self, ptr):
        if ptr and ptr.value:
            try:
                _call_com_cached(ptr, 2, c_int)(ptr)
            except Exception:
                pass

    def _worker_loop(self):
        if IS_WINDOWS:
            try:
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
        last_wasapi_init_time = 0.0

        while self._running:
            now = time.time()

            if self._playback_just_started and not wasapi_active:
                self._playback_just_started = False
                last_wasapi_init_time = 0.0

            if IS_WINDOWS and not wasapi_active and (now - last_wasapi_init_time > 2.0):
                last_wasapi_init_time = now

                if pCaptureClient: self._release_com_safe(pCaptureClient); pCaptureClient = None
                if pAudioClient: self._release_com_safe(pAudioClient); pAudioClient = None
                if pDevice: self._release_com_safe(pDevice); pDevice = None
                if pEnumerator: self._release_com_safe(pEnumerator); pEnumerator = None
                pFormat = None

                try:
                    pEnumerator = c_void_p()
                    hr = ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, 1, byref(IID_IMMDeviceEnumerator), byref(pEnumerator))
                    if hr == 0 and pEnumerator.value:
                        pDevice = c_void_p()
                        hr = _call_com_cached(pEnumerator, 4, c_int, c_int, c_int, POINTER(c_void_p))(pEnumerator, 0, 0, byref(pDevice))
                        if hr == 0 and pDevice.value:
                            pAudioClient = c_void_p()
                            hr = _call_com_cached(pDevice, 3, c_int, c_void_p, wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                                pDevice, byref(IID_IAudioClient), 7, None, byref(pAudioClient)
                            )
                            if hr == 0 and pAudioClient.value:
                                pFormat = POINTER(WAVEFORMATEX)()
                                hr = _call_com_cached(pAudioClient, 8, c_int, POINTER(POINTER(WAVEFORMATEX)))(pAudioClient, byref(pFormat))
                                if hr == 0 and pFormat:
                                    if pFormat.contents.nSamplesPerSec > 0 and pFormat.contents.nSamplesPerSec != self.sample_rate:
                                        self.sample_rate = int(pFormat.contents.nSamplesPerSec)
                                        self._band_indices_64 = self._compute_log_bands(64, self.fft_size, self.sample_rate)

                                    hnsBuffer = 200000
                                    hr = _call_com_cached(pAudioClient, 3, c_int, c_int, wintypes.DWORD, c_longlong, c_longlong, c_void_p, c_void_p)(
                                        pAudioClient, 0, 0x00020000, hnsBuffer, 0, pFormat, None
                                    )
                                    if hr == 0:
                                        pCaptureClient = c_void_p()
                                        hr = _call_com_cached(pAudioClient, 14, c_int, c_void_p, POINTER(c_void_p))(
                                            pAudioClient, byref(IID_IAudioCaptureClient), byref(pCaptureClient)
                                        )
                                        if hr == 0 and pCaptureClient.value:
                                            if _call_com_cached(pAudioClient, 10, c_int)(pAudioClient) == 0:
                                                wasapi_active = True
                                                self._wasapi_active = True
                except Exception:
                    wasapi_active = False
                    self._wasapi_active = False

            got_real_audio = False
            if wasapi_active and pCaptureClient and pCaptureClient.value:
                try:
                    while True:
                        packetSize = wintypes.DWORD()
                        hr = _call_com_cached(pCaptureClient, 5, c_int, POINTER(wintypes.DWORD))(pCaptureClient, byref(packetSize))
                        if hr != 0 or packetSize.value == 0:
                            break

                        pData = POINTER(c_float)()
                        numFrames = wintypes.DWORD()
                        flags = wintypes.DWORD()
                        pos = c_longlong()
                        qpc = c_longlong()
                        
                        hr_buf = _call_com_cached(
                            pCaptureClient, 3, c_int,
                            POINTER(POINTER(c_float)), POINTER(wintypes.DWORD), POINTER(wintypes.DWORD),
                            POINTER(c_longlong), POINTER(c_longlong)
                        )(pCaptureClient, byref(pData), byref(numFrames), byref(flags), byref(pos), byref(qpc))
                        
                        if hr_buf == 0 and numFrames.value > 0:
                            n_channels = pFormat.contents.nChannels if pFormat else 2
                            total_samples = numFrames.value * n_channels
                            
                            if flags.value & 2:
                                mono = np.zeros(numFrames.value, dtype=np.float32)
                            else:
                                arr = np.ctypeslib.as_array(pData, shape=(total_samples,))
                                if n_channels >= 2:
                                    mono = (arr[0::n_channels] + arr[1::n_channels]) * 0.5
                                else:
                                    mono = arr.copy()
                            
                            n = len(mono)
                            buf_len = len(self._raw_pcm_buffer)
                            if n > 0:
                                if n >= buf_len:
                                    self._raw_pcm_buffer[:] = mono[-buf_len:]
                                else:
                                    self._raw_pcm_buffer[:-n] = self._raw_pcm_buffer[n:]
                                    self._raw_pcm_buffer[-n:] = mono
                                got_real_audio = True

                            _call_com_cached(pCaptureClient, 4, c_int, wintypes.DWORD)(pCaptureClient, numFrames.value)
                        else:
                            break
                except Exception:
                    wasapi_active = False
                    self._wasapi_active = False
                    if pCaptureClient: self._release_com_safe(pCaptureClient); pCaptureClient = None
                    if pAudioClient:
                        try: _call_com_cached(pAudioClient, 11, c_int)(pAudioClient)
                        except Exception: pass
                        self._release_com_safe(pAudioClient); pAudioClient = None
                    if pDevice: self._release_com_safe(pDevice); pDevice = None
                    if pEnumerator: self._release_com_safe(pEnumerator); pEnumerator = None
                    pFormat = None

            if self._is_playing:
                if got_real_audio:
                    self._process_real_fft()
                else:
                    self._process_procedural_fallback()
            else:
                self._decay_to_zero()

            if not self._is_playing:
                sleep_sec = 0.050
            elif self._eco_mode:
                sleep_sec = max(0.010, min(0.040, 1.0 / (float(self._target_fps) * 1.5)))
            else:
                sleep_sec = 0.010
            time.sleep(sleep_sec)

        if wasapi_active and pAudioClient:
            try: _call_com_cached(pAudioClient, 11, c_int)(pAudioClient)
            except Exception: pass
        if IS_WINDOWS:
            try: ole32.CoUninitialize()
            except Exception: pass

    def _process_real_fft(self):
        buf = self._raw_pcm_buffer[-self.fft_size:]
        windowed = buf * self._hann_window
        fft_complex = np.fft.rfft(windowed)
        magnitudes = np.abs(fft_complex)

        indices = self._band_indices_64
        n_bins = len(indices) - 1
        raw_bands = np.zeros(n_bins, dtype=np.float32)
        freq_tilt = 1.0 + (np.arange(n_bins, dtype=np.float32) / float(n_bins)) * 2.2

        for i in range(n_bins):
            start = indices[i]
            end = max(start + 1, indices[i+1])
            if start < len(magnitudes):
                chunk = magnitudes[start:min(end, len(magnitudes))]
                raw_bands[i] = np.mean(chunk) * freq_tilt[i]

        power_bands = np.sqrt(np.maximum(0.0, raw_bands))
        current_peak = float(np.max(power_bands)) if len(power_bands) > 0 else 0.01
        if current_peak > self._agc_max:
            self._agc_max = self._agc_max * 0.85 + current_peak * 0.15
        else:
            self._agc_max = max(0.05, self._agc_max * 0.992)

        norm_bands = np.clip((power_bands / (self._agc_max + 1e-4)) * self._sensitivity, 0.0, 1.0)

        with self._lock:
            cur = self._spectrum[:n_bins]
            target = norm_bands[:n_bins]
            diff = target - cur
            attack_mask = diff > 0
            attack_rate = np.where(diff > 0.08, 0.88, 0.60)
            cur[attack_mask] += diff[attack_mask] * attack_rate[attack_mask]
            cur[~attack_mask] += diff[~attack_mask] * 0.22
            self._spectrum[:n_bins] = cur

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
        with self._lock:
            self._spectrum *= 0.85
            self._peaks = np.maximum(0.0, self._peaks - 0.02)
            self._peak_velocities *= 0.85
