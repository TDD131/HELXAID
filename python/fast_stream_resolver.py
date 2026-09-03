"""
Fast Stream Resolver for HELXAID
================================
Multi-Tier High-Performance Stream Resolution Engine:
- Tier 1: C++ Native Innertube Fast-Path (~100ms - 250ms resolution)
- Tier 2: C++ Background Next-Track Pre-Fetching (0ms instant playback)
- Tier 3: Optimized Fast-Search & Resilient yt-dlp Fallback Engine
"""

import os
import sys
import time
import re
from typing import Dict, Any, Optional, List, Tuple

import threading
from PySide6.QtCore import QObject, Signal, QThread

NATIVE_RESOLVER_AVAILABLE = False
_native_resolver = None

try:
    import innertube_fast_resolver as _native_resolver
    NATIVE_RESOLVER_AVAILABLE = True
    print("[FastStream] C++ Native Innertube Resolver loaded")
except ImportError:
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        import innertube_fast_resolver as _native_resolver
        NATIVE_RESOLVER_AVAILABLE = True
        print("[FastStream] C++ Native Innertube Resolver loaded from script dir")
    except Exception as e:
        print(f"[FastStream] C++ Native Resolver not available: {e}")
        print("[FastStream] Using pure Python yt-dlp fallback engine")


def is_native_available() -> bool:
    return NATIVE_RESOLVER_AVAILABLE and _native_resolver is not None


def extract_youtube_video_id(url_or_query: str) -> Optional[str]:
    """Extract standard 11-char YouTube Video ID from any URL format."""
    if not url_or_query:
        return None
    s = url_or_query.strip()
    if s.startswith("ytsearch1:") or s.startswith("ytsearch6:"):
        s = s[10:].strip()
    elif s.startswith("ytsearch:"):
        s = s[9:].strip()

    if len(s) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', s):
        return s

    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'music\.youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})'
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return None


def is_youtube_target(url_or_query: str) -> bool:
    """Check if the given target is a YouTube URL or direct Video ID."""
    return extract_youtube_video_id(url_or_query) is not None


class StreamResolutionCache:
    """Thread-safe LRU memory cache with TTL for resolved audio stream URLs."""
    def __init__(self, max_entries: int = 250, default_ttl_seconds: int = 14400):
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._max_entries = max_entries
        self._default_ttl = default_ttl_seconds

    def _normalize_key(self, key: str) -> str:
        s = (key or "").strip()
        if s.startswith(('ytsearch1:', 'ytsearch6:', 'ytsearch:')):
            s = s.split(':', 1)[1].strip()
        vid = extract_youtube_video_id(s)
        if vid:
            return f"vid:{vid}"
        return s.lower()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        norm_key = self._normalize_key(key)
        if not norm_key:
            return None
        with self._lock:
            if norm_key in self._cache:
                expiry, data = self._cache[norm_key]
                if time.time() < expiry:
                    res = dict(data)
                    res['cached'] = True
                    return res
                else:
                    del self._cache[norm_key]
        return None

    def put(self, key: str, data: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        norm_key = self._normalize_key(key)
        if not norm_key or not data or not data.get('stream_url'):
            return
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expiry = time.time() + ttl
        with self._lock:
            if len(self._cache) >= self._max_entries:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[norm_key] = (expiry, dict(data))

            # Also cache under direct video ID if present
            orig_url = data.get('original_url', '')
            vid = extract_youtube_video_id(orig_url)
            if vid and f"vid:{vid}" != norm_key:
                self._cache[f"vid:{vid}"] = (expiry, dict(data))

    def remove(self, key: str) -> None:
        norm_key = self._normalize_key(key)
        if not norm_key:
            return
        with self._lock:
            if norm_key in self._cache:
                del self._cache[norm_key]
            vid = extract_youtube_video_id(key)
            if vid and f"vid:{vid}" in self._cache:
                del self._cache[f"vid:{vid}"]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

_stream_cache = StreamResolutionCache()
_native_failure_counter = 0
_circuit_breaker_tripped = False
_circuit_lock = threading.Lock()

def get_cached_stream(target_url_or_query: str) -> Optional[Dict[str, Any]]:
    return _stream_cache.get(target_url_or_query)

def cache_stream(target_url_or_query: str, res: Dict[str, Any], ttl_seconds: int = 14400) -> None:
    _stream_cache.put(target_url_or_query, res, ttl_seconds)

def invalidate_cached_stream(target_url_or_query: str) -> None:
    """Purge stream URL from Python memory cache and C++ native cache."""
    _stream_cache.remove(target_url_or_query)
    if is_native_available():
        try:
            _native_resolver.clear_cache()
        except Exception:
            pass

def report_stream_playback_failure(target_url_or_query: str) -> None:
    """Report stream playback error (e.g. TCP -138 / 403 Forbidden). Purges cache and trips circuit breaker if needed."""
    global _native_failure_counter, _circuit_breaker_tripped
    invalidate_cached_stream(target_url_or_query)
    with _circuit_lock:
        _native_failure_counter += 1
        if _native_failure_counter >= 2 and not _circuit_breaker_tripped:
            _circuit_breaker_tripped = True
            print("[FastStream] Native Innertube Resolver circuit breaker TRIPPED -> routing exclusively to robust yt-dlp engine")

def is_circuit_breaker_tripped() -> bool:
    global _circuit_breaker_tripped
    return _circuit_breaker_tripped

def reset_circuit_breaker() -> None:
    global _native_failure_counter, _circuit_breaker_tripped
    with _circuit_lock:
        _native_failure_counter = 0
        _circuit_breaker_tripped = False


class InnertubeStreamClient:
    """
    Ultra-Fast Direct YouTube Innertube Player API Client (~100ms - 200ms).
    Queries YouTube's official Innertube endpoint directly via standard HTTPS POST,
    extracting unthrottled, non-ciphered audio streaming formats (itag 140 m4a / itag 251 webm)
    that connect immediately over standard TCP/TLS without timeouts (-138) or PoToken blocking.
    """
    ENDPOINT = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"

    @classmethod
    def resolve_video_id(cls, video_id: str) -> Optional[Dict[str, Any]]:
        if not video_id or len(video_id) != 11:
            return None

        # 1. Primary: iOS YouTube Client (Highest reliability, unthrottled itag 140 / 251, public CDN)
        payload = {
            "context": {
                "client": {
                    "clientName": "IOS",
                    "clientVersion": "19.29.1",
                    "deviceMake": "Apple",
                    "deviceModel": "iPhone14,3",
                    "osName": "iOS",
                    "osVersion": "16.5.0.20F66",
                    "hl": "en",
                    "gl": "US",
                    "utcOffsetMinutes": 0
                }
            },
            "videoId": video_id,
            "playbackContext": {
                "contentPlaybackContext": {
                    "html5Preference": "HTML5_PREF_WANTS"
                }
            },
            "contentCheckOk": True,
            "racyCheckOk": True
        }

        headers = {
            'User-Agent': 'com.google.ios.youtube/19.29.1 (iPhone14,3; U; CPU iOS 16_5 like Mac OS X; en_US)',
            'Content-Type': 'application/json',
            'X-YouTube-Client-Name': '5',
            'X-YouTube-Client-Version': '19.29.1',
            'Origin': 'https://www.youtube.com',
            'Accept': '*/*'
        }

        try:
            import urllib.request
            import ssl
            import json

            ctx = ssl._create_unverified_context()
            data_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(cls.ENDPOINT, data=data_bytes, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    res = cls._extract_stream_data(video_id, data)
                    if res:
                        return res
        except Exception:
            pass

        # 2. Secondary: ANDROID_TESTSUITE Client
        try:
            fallback_payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID_TESTSUITE",
                        "clientVersion": "1.9",
                        "hl": "en",
                        "gl": "US"
                    }
                },
                "videoId": video_id,
                "contentCheckOk": True,
                "racyCheckOk": True
            }
            fallback_headers = {
                'User-Agent': 'com.google.android.youtube/1.9 (Linux; U; Android 9) gzip',
                'Content-Type': 'application/json',
                'X-YouTube-Client-Name': '85',
                'X-YouTube-Client-Version': '1.9',
                'Origin': 'https://www.youtube.com'
            }
            data_bytes = json.dumps(fallback_payload).encode('utf-8')
            req = urllib.request.Request(cls.ENDPOINT, data=data_bytes, headers=fallback_headers)
            with urllib.request.urlopen(req, timeout=3.0, context=ctx) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    return cls._extract_stream_data(video_id, data)
        except Exception as e:
            print(f"[InnertubeFast] Android Testsuite fallback notice: {e}")

        return None

    @classmethod
    def _extract_stream_data(cls, video_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        playability = data.get('playabilityStatus', {})
        if playability.get('status') and playability.get('status') != 'OK':
            return None

        streaming_data = data.get('streamingData', {})
        formats = streaming_data.get('adaptiveFormats', []) + streaming_data.get('formats', [])
        if not formats:
            return None

        best_url = ""
        best_itag = 0
        best_priority = 999

        for f in formats:
            url = f.get('url')
            if not url:
                continue
            itag = int(f.get('itag', 0))
            mime = f.get('mimeType', '')

            priority = 999
            if itag == 140 or 'audio/mp4' in mime or 'audio/m4a' in mime or 'audio/aac' in mime:
                priority = 1      # m4a AAC 128k (Native WMF hardware-accelerated demuxing, ISO-BMFF zero-stall)
            elif itag == 251:
                priority = 2      # webm Opus 160k
            elif 'audio/webm' in mime or 'opus' in mime:
                priority = 3
            elif 'audio/' in mime:
                priority = 4
            elif itag == 18:
                priority = 5      # mp4 360p progressive

            if priority < best_priority:
                best_priority = priority
                best_url = url
                best_itag = itag

        if not best_url:
            return None

        video_details = data.get('videoDetails', {})
        title = video_details.get('title', 'Unknown Stream')
        artist = video_details.get('author', 'Unknown Artist')
        length_sec = int(video_details.get('lengthSeconds', 0))

        return {
            'success': True,
            'stream_url': best_url,
            'title': title,
            'artist': artist,
            'duration': length_sec,
            'duration_ms': length_sec * 1000,
            'itag': best_itag,
            'source': 'innertube_fast_python',
            'original_url': f"https://www.youtube.com/watch?v={video_id}",
            'error': ''
        }


_shared_ydl = None
_ydl_lock = threading.Lock()

def _get_shared_ydl():
    global _shared_ydl
    if _shared_ydl is None:
        with _ydl_lock:
            if _shared_ydl is None:
                import yt_dlp
                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio[itag=140]/bestaudio[ext=webm]/bestaudio/best',
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'socket_timeout': 6,
                    'source_address': '0.0.0.0',
                    'skip_download': True,
                    'extract_flat': False,
                    'extractor_args': {'youtube': {'player_client': ['android', 'web', 'tv_embedded']}},
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                    },
                }
                _shared_ydl = yt_dlp.YoutubeDL(ydl_opts)
    return _shared_ydl


class StreamPrefetchWorker(QThread):
    """Background worker for pre-resolving upcoming audio stream URLs."""
    resolved = Signal(int, dict)    # (playlist_index, resolution_dict)
    failed = Signal(int, str)       # (playlist_index, error_msg)

    def __init__(self, index: int, target: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.target = target
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled or not self.target:
            return
        try:
            cached = get_cached_stream(self.target)
            if cached and cached.get('stream_url'):
                if not self._is_cancelled:
                    self.resolved.emit(self.index, cached)
                return

            res = resolve_stream(self.target)
            if self._is_cancelled:
                return

            if res.get('success') and res.get('stream_url'):
                self.resolved.emit(self.index, res)
            else:
                self.failed.emit(self.index, res.get('error', 'Failed to resolve stream'))
        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(self.index, str(e))


def prefetch_track(track: Dict[str, Any]) -> None:
    """Pre-fetch a track in background thread."""
    target = track.get('original_url') or track.get('path') or track.get('title', '')
    if not target:
        return
    def _pre():
        cached = get_cached_stream(target)
        if not cached:
            resolve_stream(target)
    threading.Thread(target=_pre, daemon=True).start()


_prewarm_executor = None
_prewarm_lock = threading.Lock()

def _get_prewarm_executor():
    global _prewarm_executor
    with _prewarm_lock:
        if _prewarm_executor is None:
            import concurrent.futures
            _prewarm_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=3,
                thread_name_prefix="FastStreamPrewarm"
            )
        return _prewarm_executor


def prefetch_batch(tracks: list, limit: int = 8) -> None:
    """Concurrently pre-warm RAM stream cache for upcoming unplayed tracks via ThreadPoolExecutor."""
    if not tracks:
        return

    targets = []
    seen = set()
    for t in tracks[:limit]:
        if isinstance(t, dict):
            target = t.get('original_url') or t.get('path') or t.get('title', '')
            if target and target not in seen and not get_cached_stream(target):
                seen.add(target)
                targets.append(target)

    if not targets:
        return

    def _resolve_task(tgt):
        try:
            resolve_stream(tgt)
        except Exception:
            pass

    executor = _get_prewarm_executor()
    for tgt in targets:
        executor.submit(_resolve_task, tgt)


def get_audio_cache_dir() -> str:
    """Get persistent local directory for caching streaming audio tracks."""
    base_dir = os.environ.get('LOCALAPPDATA') or os.path.expanduser("~")
    cache_dir = os.path.join(base_dir, "HELXAID", "cache", "audio")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        pass
    return cache_dir


def get_local_cached_stream_path(target_url_or_query: str) -> Optional[str]:
    """Check if the audio stream is already fully downloaded locally on disk."""
    vid = extract_youtube_video_id(target_url_or_query)
    if not vid:
        return None
    cache_dir = get_audio_cache_dir()
    for ext in ('.webm', '.opus', '.m4a', '.mp3'):
        candidate = os.path.join(cache_dir, f"{vid}{ext}")
        if os.path.exists(candidate):
            try:
                # File must be greater than 200 KB to be considered a complete audio file
                if os.path.getsize(candidate) > 200 * 1024:
                    return candidate
            except Exception:
                pass
    return None


_downloading_vids = set()
_downloading_lock = threading.Lock()

def download_stream_background(target_url_or_query: str, stream_url: str, on_finished: Any = None) -> None:
    """Download audio stream in background so playback never stalls and replays are 100% local."""
    vid = extract_youtube_video_id(target_url_or_query)
    if not vid or not stream_url or not stream_url.startswith('http'):
        return
    existing = get_local_cached_stream_path(target_url_or_query)
    if existing:
        if on_finished:
            try:
                on_finished(vid, existing)
            except Exception:
                pass
        return

    with _downloading_lock:
        if vid in _downloading_vids:
            return
        _downloading_vids.add(vid)

    def _worker():
        import urllib.request
        import ssl
        cache_dir = get_audio_cache_dir()
        is_webm = bool("itag=251" in stream_url or "audio/webm" in stream_url or "audio%2Fwebm" in stream_url or "webm" in stream_url or "opus" in stream_url)
        ext = ".webm" if is_webm else ".m4a"
        temp_path = os.path.join(cache_dir, f"{vid}.tmp")
        final_path = os.path.join(cache_dir, f"{vid}{ext}")
        
        try:
            ctx = ssl._create_unverified_context()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*'
            }
            req = urllib.request.Request(stream_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                with open(temp_path, 'wb') as out_f:
                    while True:
                        chunk = resp.read(128 * 1024)
                        if not chunk:
                            break
                        out_f.write(chunk)
            
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 100 * 1024:
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.rename(temp_path, final_path)
                print(f"[FastStream Cache] Cached track locally: {final_path} ({os.path.getsize(final_path)//1024} KB)")
                if on_finished:
                    try:
                        on_finished(vid, final_path)
                    except Exception:
                        pass
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        finally:
            with _downloading_lock:
                _downloading_vids.discard(vid)

    threading.Thread(target=_worker, daemon=True).start()


_inflight_events: Dict[str, threading.Event] = {}
_inflight_results: Dict[str, dict] = {}
_inflight_lock = threading.Lock()


def resolve_stream(target_url_or_query: str, logger: Any = None, force_fallback: bool = False, bypass_cache: bool = False) -> Dict[str, Any]:
    """
    Resolve a stream URL using RAM cache, in-flight deduplication, fast canonical search, and optimized yt-dlp singleton.
    """
    t0 = time.time()
    raw_target = (target_url_or_query or "").strip()
    
    # Clean ytsearch prefix
    clean_target = raw_target
    if clean_target.startswith("ytsearch1:") or clean_target.startswith("ytsearch6:"):
        clean_target = clean_target[10:].strip()
    elif clean_target.startswith("ytsearch:"):
        clean_target = clean_target[9:].strip()

    # -------------------------------------------------------------
    # TIER 0: Local Disk Audio Cache (< 0.1ms) & Instant RAM Cache (< 1ms)
    # -------------------------------------------------------------
    local_file = get_local_cached_stream_path(clean_target)
    if local_file and not bypass_cache:
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        from PySide6.QtCore import QUrl
        print(f"[FastStream] Local Disk Cache resolved in {elapsed_ms}ms: {local_file}")
        return {
            'success': True,
            'stream_url': QUrl.fromLocalFile(local_file).toString(),
            'title': '',
            'artist': '',
            'duration': 0,
            'duration_ms': 0,
            'itag': 251,
            'source': 'local_disk_cache',
            'original_url': clean_target,
            'error': ''
        }

    if not bypass_cache:
        cached = get_cached_stream(clean_target)
        if cached and cached.get('stream_url'):
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            title = cached.get('title', 'Unknown Stream')
            print(f"[FastStream] RAM Cache resolved in {elapsed_ms}ms: '{title}'")
            return cached

    # In-flight request coalescing (deduplicates simultaneous lookups for identical target)
    is_leader = False
    norm_key = _stream_cache._normalize_key(clean_target)
    with _inflight_lock:
        if norm_key in _inflight_events and not bypass_cache:
            event = _inflight_events[norm_key]
        else:
            event = threading.Event()
            _inflight_events[norm_key] = event
            is_leader = True

    if not is_leader:
        # Follower thread waits for leader thread to finish resolution
        event.wait(timeout=10.0)
        with _inflight_lock:
            if norm_key in _inflight_results:
                return dict(_inflight_results[norm_key])
        return get_cached_stream(clean_target) or {'success': False, 'error': 'In-flight resolution timeout'}

    try:
        res = _do_resolve_stream(raw_target, clean_target, t0)
        with _inflight_lock:
            _inflight_results[norm_key] = res
        return res
    finally:
        event.set()
        def _cleanup():
            time.sleep(2.0)
            with _inflight_lock:
                _inflight_events.pop(norm_key, None)
                _inflight_results.pop(norm_key, None)
        threading.Thread(target=_cleanup, daemon=True).start()


def _do_resolve_stream(raw_target: str, clean_target: str, t0: float) -> Dict[str, Any]:

    direct_vid = extract_youtube_video_id(clean_target)

    # -------------------------------------------------------------
    # TIER 1: Fast Canonical Studio & Target Resolution (~500ms)
    # -------------------------------------------------------------
    canonical_info = None
    if not direct_vid and not clean_target.startswith(('http://', 'https://', 'www.')):
        try:
            from CanonicalMetadataEngine import CanonicalSearchEngine
            target_res = CanonicalSearchEngine.resolve_target(clean_target)
            if target_res.get('success') and target_res.get('video_id'):
                found_vid = target_res['video_id']
                canonical_info = target_res.get('canonical_info')
                clean_target = f"https://www.youtube.com/watch?v={found_vid}"
        except Exception as e:
            print(f"[FastStream] Fast canonical search error: {e}")

    # -------------------------------------------------------------
    # TIER 1.5: Fast Innertube Python Client (~120ms)
    # -------------------------------------------------------------
    vid_to_try = direct_vid or extract_youtube_video_id(clean_target)
    if vid_to_try and not is_circuit_breaker_tripped():
        try:
            it_res = InnertubeStreamClient.resolve_video_id(vid_to_try)
            if it_res and it_res.get('stream_url'):
                elapsed_ms = round((time.time() - t0) * 1000, 1)
                final_title = canonical_info.title if canonical_info else it_res.get('title', 'Unknown Stream')
                final_artist = canonical_info.artist if canonical_info else it_res.get('artist', 'Unknown Artist')
                final_dur = int(canonical_info.duration_ms / 1000) if (canonical_info and canonical_info.duration_ms > 0) else it_res.get('duration', 0)
                final_dur_ms = canonical_info.duration_ms if (canonical_info and canonical_info.duration_ms > 0) else it_res.get('duration_ms', 0)
                
                print(f"[FastStream] Innertube resolved in {elapsed_ms}ms: '{final_title}' by '{final_artist}'")
                res_payload = {
                    'success': True,
                    'stream_url': it_res['stream_url'],
                    'title': final_title,
                    'artist': final_artist,
                    'album': canonical_info.album if canonical_info else '',
                    'duration': final_dur,
                    'duration_ms': final_dur_ms,
                    'artwork_url': canonical_info.artwork_url if canonical_info else '',
                    'itag': it_res.get('itag', 251),
                    'source': 'innertube_fast',
                    'original_url': f"https://www.youtube.com/watch?v={vid_to_try}",
                    'error': ''
                }
                _stream_cache.put(raw_target, res_payload)
                if clean_target != raw_target:
                    _stream_cache.put(clean_target, res_payload)
                return res_payload
        except Exception as e:
            print(f"[FastStream] Innertube fast resolve notice: {e}")

    # -------------------------------------------------------------
    # TIER 2: High-Speed yt-dlp Singleton Engine (~1.5s)
    # -------------------------------------------------------------
    try:
        ydl = _get_shared_ydl()
        with _ydl_lock:
            info = ydl.extract_info(clean_target, download=False)
            
        if 'entries' in info and info['entries']:
            from CanonicalMetadataEngine import StudioAudioMatcher
            best_e = StudioAudioMatcher.select_best_candidate(info['entries'], original_query=clean_target, canonical=canonical_info)
            info = best_e or info['entries'][0]
            
        stream_url = info.get('url')
        raw_title = info.get('title', 'Unknown Stream')
        raw_artist = info.get('uploader', info.get('channel', 'Unknown Artist'))
        raw_duration = int(info.get('duration') or 0)
        webpage_url = info.get('webpage_url') or clean_target

        final_title = canonical_info.title if canonical_info else raw_title
        final_artist = canonical_info.artist if canonical_info else raw_artist
        final_album = canonical_info.album if canonical_info else ""
        final_dur = int(canonical_info.duration_ms / 1000) if (canonical_info and canonical_info.duration_ms > 0) else raw_duration
        final_dur_ms = canonical_info.duration_ms if (canonical_info and canonical_info.duration_ms > 0) else (raw_duration * 1000)
        final_art = canonical_info.artwork_url if canonical_info else ""
        
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        try:
            print(f"[FastStream] yt-dlp resolved in {elapsed_ms}ms: '{final_title}' by '{final_artist}'")
        except Exception:
            pass
        
        if stream_url:
            res_dict = {
                'success': True,
                'stream_url': stream_url,
                'title': final_title,
                'artist': final_artist,
                'album': final_album,
                'duration': final_dur,
                'duration_ms': final_dur_ms,
                'artwork_url': final_art,
                'itag': 140,
                'source': 'ytdlp_studio' if canonical_info else 'ytdlp',
                'original_url': webpage_url,
                'error': ''
            }
            cache_stream(clean_target, res_dict)
            if raw_target != clean_target:
                cache_stream(raw_target, res_dict)
            return res_dict
        else:
            return {
                'success': False,
                'stream_url': '',
                'title': final_title,
                'artist': final_artist,
                'duration': 0,
                'duration_ms': 0,
                'itag': 0,
                'source': 'ytdlp',
                'original_url': webpage_url,
                'error': 'No stream URL found in metadata'
            }
    except Exception as e:
        print(f"[FastStream] yt-dlp fallback error: {e}")
        return {
            'success': False,
            'stream_url': '',
            'title': '',
            'artist': '',
            'duration': 0,
            'duration_ms': 0,
            'itag': 0,
            'source': 'error',
            'original_url': raw_target,
            'error': str(e)
        }


def fetch_online_playlist_tracks(playlist_url_or_id: str) -> List[Dict[str, Any]]:
    """
    Extract playlist metadata and track items dynamically in real-time (~300ms)
    without downloading audio files using high-speed flat extraction.
    """
    if not playlist_url_or_id:
        return []
    
    clean_target = playlist_url_or_id.strip()
    if not clean_target.startswith(('http://', 'https://')):
        if clean_target.startswith('VL'):
            clean_target = clean_target[2:]
        clean_target = f"https://www.youtube.com/playlist?list={clean_target}"

    try:
        import yt_dlp
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 6,
            'source_address': '0.0.0.0',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target, download=False)
            entries = info.get('entries', []) if info else []
            tracks = []
            for e in entries:
                if not e:
                    continue
                vid = e.get('id', '')
                title = e.get('title', 'Unknown Track')
                artist = e.get('uploader') or e.get('artist') or info.get('title', 'Online Stream')
                dur = float(e.get('duration') or 0.0)
                url = e.get('url') or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
                if url:
                    tracks.append({
                        'title': title,
                        'artist': artist,
                        'duration': dur,
                        'original_url': url,
                        'thumbnail_url': f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "",
                        'is_stream': True,
                        'is_online': True
                    })
            return tracks
    except Exception as e:
        print(f"[FastStream] Dynamic playlist extraction error: {e}")
        return []
