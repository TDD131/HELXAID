"""
StreamFileEngine.py - HELXAIC Direct Stream File Pointer Engine
==============================================================
Centralized engine for creating, reading, and managing lightweight stream descriptor files:
- .hxstream : Rich JSON stream metadata pointer (~400 Bytes)
- .strm     : Kodi/Jellyfin compatible single-line stream pointer (~50 Bytes)

Enables organizing online streams in Windows Explorer folders with 0 MB audio download,
microsecond local scanning in MediaLibraryPage, and on-demand live streaming in MusicPanelWidget.
"""

import os
import json
import re
import time
from typing import Dict, Any, Optional

STREAM_FILE_EXTENSION = ".hxstream"
STREAM_LEGACY_EXTENSION = ".strm"
VALID_STREAM_EXTENSIONS = {STREAM_FILE_EXTENSION, STREAM_LEGACY_EXTENSION}


def sanitize_stream_filename(title: str) -> str:
    """Sanitize title for safe Windows filename creation."""
    if not title:
        return "stream_track"
    # Replace illegal Windows characters: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", str(title))
    # Strip leading/trailing spaces and dots which Windows disallows
    cleaned = cleaned.strip(" .")
    return cleaned or "stream_track"


def is_stream_file(file_path: str) -> bool:
    """Check if a path is a stream pointer file based on its extension."""
    if not file_path:
        return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VALID_STREAM_EXTENSIONS


def write_stream_file(
    output_dir: str,
    metadata: Dict[str, Any],
    format_ext: str = STREAM_FILE_EXTENSION,
    preferred_filename: Optional[str] = None
) -> Optional[str]:
    """
    Write an ultra-lightweight stream descriptor file to disk.
    
    Args:
        output_dir: Directory where the file should be created.
        metadata: Dictionary containing title, artist, album, duration, original_url, etc.
        format_ext: Extension to use (default .hxstream).
        preferred_filename: Optional explicit filename base.
        
    Returns:
        The absolute path of the created file, or None on failure.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        raw_title = preferred_filename or metadata.get('title') or "Unknown Stream"
        base_name = sanitize_stream_filename(raw_title)
        format_ext = format_ext.lower()
        if not format_ext.startswith('.'):
            format_ext = f".{format_ext}"
            
        if format_ext not in VALID_STREAM_EXTENSIONS:
            format_ext = STREAM_FILE_EXTENSION

        filepath = os.path.join(output_dir, f"{base_name}{format_ext}")
        
        # Avoid overwriting identical filenames with different URLs
        counter = 1
        canonical_url = metadata.get('original_url') or metadata.get('path', '')
        while os.path.exists(filepath):
            # If existing file already points to the same canonical URL, return it
            existing = read_stream_file(filepath)
            if existing and existing.get('original_url') == canonical_url:
                return filepath
            filepath = os.path.join(output_dir, f"{base_name} ({counter}){format_ext}")
            counter += 1

        if format_ext == STREAM_FILE_EXTENSION:
            payload = {
                "format": "helxaic_stream_v1",
                "version": 1,
                "title": metadata.get('title') or "Unknown Stream",
                "artist": metadata.get('artist') or "Unknown Artist",
                "album": metadata.get('album') or "Online Stream",
                "duration": float(metadata.get('duration') or 0.0),
                "original_url": canonical_url,
                "source": metadata.get('source') or "online",
                "thumbnail_url": metadata.get('thumbnail_url', ''),
                "is_stream": True,
                "is_online": True,
                "created_at": int(time.time())
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        else:
            # Plaintext .strm format (Kodi / Jellyfin standard)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(canonical_url.strip() + "\n")

        return filepath
    except Exception as e:
        print(f"[StreamFileEngine] Error writing stream file: {e}")
        return None


def read_stream_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Read and parse a .hxstream or .strm file with microsecond latency.
    
    Args:
        file_path: Absolute path to the stream file.
        
    Returns:
        Normalized track metadata dictionary compatible with HELXAIC, or None.
    """
    if not file_path or not os.path.isfile(file_path):
        return None

    ext = os.path.splitext(file_path)[1].lower()
    base_title = os.path.splitext(os.path.basename(file_path))[0]

    try:
        mtime = os.path.getmtime(file_path)
    except Exception:
        mtime = 0

    try:
        if ext == STREAM_FILE_EXTENSION:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            orig_url = data.get('original_url') or data.get('url', '')
            title = data.get('title') or base_title
            artist = data.get('artist') or "Unknown Artist"
            album = data.get('album') or "Online Stream"
            duration = float(data.get('duration') or 0.0)

            return {
                'path': file_path,
                'original_url': orig_url,
                'stream_url': None,
                'title': title,
                'artist': artist,
                'album': album,
                'duration': duration,
                'is_online': True,
                'is_stream': True,
                'is_stream_file': True,
                'source': data.get('source', 'online'),
                'thumbnail_url': data.get('thumbnail_url', ''),
                'mtime': mtime,
                'date_added': "Stream File"
            }
            
        elif ext == STREAM_LEGACY_EXTENSION:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
                
            # If single line or first non-comment line is URL
            url = ""
            for line in raw.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    url = line
                    break
                    
            if not url:
                url = raw

            return {
                'path': file_path,
                'original_url': url,
                'stream_url': None,
                'title': base_title,
                'artist': "Stream",
                'album': "Online Stream",
                'duration': 0.0,
                'is_online': True,
                'is_stream': True,
                'is_stream_file': True,
                'source': "online",
                'thumbnail_url': '',
                'mtime': mtime,
                'date_added': "Stream File"
            }
    except Exception as e:
        print(f"[StreamFileEngine] Error reading {file_path}: {e}")
        # Return graceful fallback
        return {
            'path': file_path,
            'original_url': '',
            'stream_url': None,
            'title': base_title,
            'artist': "Corrupted Stream",
            'album': "Online Stream",
            'duration': 0.0,
            'is_online': True,
            'is_stream': True,
            'is_stream_file': True,
            'source': "online",
            'mtime': mtime,
            'date_added': "Stream File"
        }
    return None
