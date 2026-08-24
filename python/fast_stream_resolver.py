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
from typing import Dict, Any, Optional

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
    if s.startswith("ytsearch1:"):
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


def prefetch_track(track: Dict[str, Any]) -> None:
    """Pre-fetch next track in background C++ thread for 0ms instant playback."""
    if not is_native_available():
        return
    url = track.get('original_url') or track.get('path', '')
    vid = extract_youtube_video_id(url)
    if vid:
        try:
            _native_resolver.prefetch(vid)
        except Exception as e:
            print(f"[FastStream] Pre-fetch error: {e}")


def resolve_stream(target_url_or_query: str, logger: Any = None) -> Dict[str, Any]:
    """
    Resolve a stream URL using C++ Fast-Path first with automatic optimized fallback.
    """
    t0 = time.time()
    raw_target = (target_url_or_query or "").strip()
    
    # Clean ytsearch prefix
    clean_target = raw_target
    if clean_target.startswith("ytsearch1:"):
        clean_target = clean_target[10:].strip()
    elif clean_target.startswith("ytsearch:"):
        clean_target = clean_target[9:].strip()

    direct_vid = extract_youtube_video_id(clean_target)

    # -------------------------------------------------------------
    # TIER 1: Direct YouTube Video ID / URL via C++ (~100ms - 250ms)
    # -------------------------------------------------------------
    if direct_vid and is_native_available():
        try:
            native_res = _native_resolver.resolve(direct_vid)
            if native_res.get('success') and native_res.get('stream_url'):
                elapsed_ms = round((time.time() - t0) * 1000, 1)
                title = native_res.get('title', 'Unknown Stream')
                print(f"[FastStream] C++ Native resolved in {elapsed_ms}ms: {title[:30]}")
                
                return {
                    'success': True,
                    'stream_url': native_res.get('stream_url'),
                    'title': title,
                    'artist': native_res.get('artist', 'Unknown Artist'),
                    'duration': int(native_res.get('duration', 0)),
                    'duration_ms': int(native_res.get('duration_ms', 0)),
                    'itag': int(native_res.get('itag', 140)),
                    'source': 'native_cpp',
                    'original_url': f"https://www.youtube.com/watch?v={direct_vid}",
                    'error': ''
                }
            else:
                fallback_reason = native_res.get('error', 'unknown')
                print(f"[FastStream] C++ Fast-Path ({fallback_reason}), routing to optimized fallback...")
        except Exception as e:
            print(f"[FastStream] Native C++ resolver exception: {e}")

    # -------------------------------------------------------------
    # TIER 2: Keyword Search -> Fast Flat Search -> C++ Engine
    # -------------------------------------------------------------
    if not direct_vid and not clean_target.startswith(('http://', 'https://', 'www.')):
        try:
            import yt_dlp
            # Fast lightweight search to extract videoId only (~800ms)
            flat_opts = {
                'quiet': True,
                'extract_flat': True,
                'no_warnings': True,
                'socket_timeout': 5,
            }
            with yt_dlp.YoutubeDL(flat_opts) as ydl:
                search_res = ydl.extract_info(f"ytsearch1:{clean_target}", download=False)
                if search_res and 'entries' in search_res and search_res['entries']:
                    found_entry = search_res['entries'][0]
                    found_vid = found_entry.get('id')
                    found_title = found_entry.get('title')
                    
                    if found_vid and is_native_available():
                        native_res = _native_resolver.resolve(found_vid)
                        if native_res.get('success') and native_res.get('stream_url'):
                            elapsed_ms = round((time.time() - t0) * 1000, 1)
                            print(f"[FastStream] Fast-Search + C++ resolved in {elapsed_ms}ms: {found_title[:30] if found_title else ''}")
                            return {
                                'success': True,
                                'stream_url': native_res.get('stream_url'),
                                'title': found_title or native_res.get('title', 'Unknown Stream'),
                                'artist': native_res.get('artist', found_entry.get('uploader', 'Unknown Artist')),
                                'duration': int(native_res.get('duration', found_entry.get('duration') or 0)),
                                'duration_ms': int(native_res.get('duration_ms', 0)),
                                'itag': int(native_res.get('itag', 140)),
                                'source': 'native_cpp_search',
                                'original_url': f"https://www.youtube.com/watch?v={found_vid}",
                                'error': ''
                            }
                    # Set clean_target to the direct URL for fallback
                    if found_vid:
                        clean_target = f"https://www.youtube.com/watch?v={found_vid}"
        except Exception as e:
            print(f"[FastStream] Fast-search error: {e}")

    # -------------------------------------------------------------
    # TIER 3: Optimized yt-dlp Resilient Engine
    # -------------------------------------------------------------
    try:
        import yt_dlp
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
            'quiet': False if logger else True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'retries': 2,
            'fragment_retries': 2,
            'socket_timeout': 8,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
        }
        
        if logger:
            ydl_opts['logger'] = logger
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target, download=False)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
                
            stream_url = info.get('url')
            title = info.get('title', 'Unknown Stream')
            artist = info.get('uploader', info.get('channel', 'Unknown Artist'))
            duration = int(info.get('duration') or 0)
            webpage_url = info.get('webpage_url') or clean_target
            
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            print(f"[FastStream] yt-dlp resolved in {elapsed_ms}ms: {title[:30]}")
            
            if stream_url:
                return {
                    'success': True,
                    'stream_url': stream_url,
                    'title': title,
                    'artist': artist,
                    'duration': duration,
                    'duration_ms': duration * 1000,
                    'itag': 140,
                    'source': 'ytdlp',
                    'original_url': webpage_url,
                    'error': ''
                }
            else:
                return {
                    'success': False,
                    'stream_url': '',
                    'title': title,
                    'artist': artist,
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
