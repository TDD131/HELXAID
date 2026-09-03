"""
ImageCacheEngine for HELXAID
============================
Multi-Tier High-Performance Preview Thumbnail & Cover Art Caching Engine:
- Tier 0: Native C++ Hardware-Accelerated Resizer & LRU Cache (WIC + WinHTTP, <0.01ms hit)
- Tier 0b: Python In-Memory Decoded QPixmap Cache (Pre-downscaled ≤ 360px)
- Tier 1: Persistent Local Disk Cache (<1ms read, SHA256 hashed)
- Tier 2: Resilient Asynchronous Worker Queue (Single Serial Writer)
"""

import os
import sys
import hashlib
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from typing import Optional, Dict

from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt

# ==============================================================================
# NATIVE C++ EXTENSION INTEGRATION (WIC + WinHTTP)
# ==============================================================================
NATIVE_IMAGE_CACHE_AVAILABLE = False
_native_image_cache = None

try:
    import image_cache_native as _native_image_cache
    NATIVE_IMAGE_CACHE_AVAILABLE = True
    print("[ImageCache] C++ Native WIC Image Resizer & LRU Cache loaded")
except ImportError:
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        import image_cache_native as _native_image_cache
        NATIVE_IMAGE_CACHE_AVAILABLE = True
        print("[ImageCache] C++ Native WIC Image Resizer loaded from script dir")
    except Exception:
        print("[ImageCache] C++ Native Image Resizer not available, using PySide6 fallback")


class ImageCacheEngine:
    """Thread-safe Multi-Tier Image & Cover Art Cache for HELXAID."""
    _instance = None
    _lock = threading.Lock()

    MAX_RAM_ITEMS = 60          # Reduced from 250 (compact footprint)
    MAX_PIXMAP_ITEMS = 30       # Reduced from 120 (pre-downscaled only)
    MAX_THUMB_WIDTH = 360       # Never store full-resolution 1280x720 in memory
    MAX_THUMB_HEIGHT = 360
    MAX_DISK_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB max disk usage

    def __init__(self):
        base_dir = os.environ.get('LOCALAPPDATA') or os.path.expanduser("~")
        self.disk_cache_dir = os.path.join(base_dir, "HELXAID", "cache", "images")
        try:
            os.makedirs(self.disk_cache_dir, exist_ok=True)
        except Exception:
            pass

        self._ram_bytes: OrderedDict[str, bytes] = OrderedDict()
        self._ram_pixmaps: OrderedDict[str, QPixmap] = OrderedDict()
        self._cache_lock = threading.Lock()
        # Single background worker for serialized disk writes (prevents 44 OS thread explosion)
        self._disk_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ImageDiskWriter")

    @classmethod
    def get_instance(cls) -> 'ImageCacheEngine':
        with cls._lock:
            if cls._instance is None:
                cls._instance = ImageCacheEngine()
            return cls._instance

    @classmethod
    def is_native_available(cls) -> bool:
        return NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache is not None

    def _url_to_hash(self, url: str) -> str:
        clean = (url or "").strip()
        return hashlib.sha256(clean.encode('utf-8')).hexdigest()

    def _get_disk_path(self, url: str) -> str:
        h = self._url_to_hash(url)
        return os.path.join(self.disk_cache_dir, f"{h}.img")

    def downscale_image_bytes(self, data: bytes, max_w: int = MAX_THUMB_WIDTH, max_h: int = MAX_THUMB_HEIGHT) -> bytes:
        """Fast image downscaling via C++ WIC hardware scaler or PySide6 fallback."""
        if not data or len(data) < 20:
            return data

        # 1. Tier 0: Fast C++ WIC Resizer (<0.5ms, 0% GIL)
        if NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache:
            try:
                res = _native_image_cache.downscale_image(data, max_w, max_h)
                if res and len(res) > 20:
                    return res
            except Exception:
                pass

        # 2. Tier 1 Fallback: PySide6 QImage Scaling
        try:
            img = QImage()
            if img.loadFromData(data):
                if img.width() > max_w or img.height() > max_h:
                    scaled = img.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    ba = QByteArray()
                    buf = QBuffer(ba)
                    buf.open(QIODevice.WriteOnly)
                    scaled.save(buf, "JPEG", 85)
                    buf.close()
                    return bytes(ba.data())
        except Exception:
            pass

        return data

    def get_bytes(self, url: str) -> Optional[bytes]:
        """Retrieve image raw bytes from Tier 0 (Native/RAM) or Tier 1 (Disk)."""
        if not url:
            return None

        # 1. Tier 0a: Native C++ LRU Cache
        if NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache:
            try:
                native_cached = _native_image_cache.cache_get(url)
                if native_cached:
                    return native_cached
            except Exception:
                pass

        # 2. Tier 0b: Python RAM Cache
        with self._cache_lock:
            if url in self._ram_bytes:
                self._ram_bytes.move_to_end(url)
                return self._ram_bytes[url]

        # 3. Tier 1: Disk Cache
        disk_path = self._get_disk_path(url)
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "rb") as f:
                    data = f.read()
                if data and len(data) > 200:
                    # Automatically downscale before storing in RAM if oversized
                    downscaled = self.downscale_image_bytes(data, self.MAX_THUMB_WIDTH, self.MAX_THUMB_HEIGHT)
                    
                    if NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache:
                        try:
                            _native_image_cache.cache_put(url, downscaled, self.MAX_THUMB_WIDTH, self.MAX_THUMB_HEIGHT)
                        except Exception:
                            pass

                    with self._cache_lock:
                        self._ram_bytes[url] = downscaled
                        if len(self._ram_bytes) > self.MAX_RAM_ITEMS:
                            self._ram_bytes.popitem(last=False)
                    return downscaled
            except Exception:
                pass

        return None

    def get_pixmap(self, url: str, max_w: int = MAX_THUMB_WIDTH, max_h: int = MAX_THUMB_HEIGHT) -> Optional[QPixmap]:
        """Retrieve pre-decoded downscaled QPixmap from Tier 0b (RAM Pixmap) or Tier 0/1 bytes."""
        if not url:
            return None

        # 1. Check RAM Pixmap Cache
        with self._cache_lock:
            if url in self._ram_pixmaps:
                self._ram_pixmaps.move_to_end(url)
                return self._ram_pixmaps[url]

        # 2. Retrieve downscaled bytes and decode
        data = self.get_bytes(url)
        if data:
            pix = QPixmap()
            if pix.loadFromData(data):
                if pix.width() > max_w or pix.height() > max_h:
                    pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                with self._cache_lock:
                    self._ram_pixmaps[url] = pix
                    if len(self._ram_pixmaps) > self.MAX_PIXMAP_ITEMS:
                        self._ram_pixmaps.popitem(last=False)
                return pix

        return None

    def put_bytes(self, url: str, data: bytes, max_w: int = MAX_THUMB_WIDTH, max_h: int = MAX_THUMB_HEIGHT) -> None:
        """Store downscaled image bytes into Tier 0 (RAM/C++) and Tier 1 (Disk) atomically."""
        if not url or not data or len(data) < 200:
            return

        # Pre-downscale immediately so raw 1280x720 is never kept in RAM
        downscaled = self.downscale_image_bytes(data, max_w, max_h)

        if NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache:
            try:
                _native_image_cache.cache_put(url, downscaled, max_w, max_h)
            except Exception:
                pass

        with self._cache_lock:
            self._ram_bytes[url] = downscaled
            if len(self._ram_bytes) > self.MAX_RAM_ITEMS:
                self._ram_bytes.popitem(last=False)

        # Write to disk via reusable single background worker (Zero raw thread spawns)
        disk_path = self._get_disk_path(url)
        def _write_task(path, payload):
            try:
                tmp_path = path + f".{os.getpid()}_{int(time.time()*1000)}.tmp"
                with open(tmp_path, "wb") as f:
                    f.write(payload)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                os.replace(tmp_path, path)
            except Exception:
                pass

        try:
            self._disk_writer.submit(_write_task, disk_path, downscaled)
        except Exception:
            pass

    def put_pixmap(self, url: str, pixmap: QPixmap) -> None:
        """Cache pre-rendered or scaled QPixmap in RAM (capped to MAX_THUMB_WIDTH)."""
        if not url or not pixmap or pixmap.isNull():
            return
        if pixmap.width() > self.MAX_THUMB_WIDTH:
            pixmap = pixmap.scaledToWidth(self.MAX_THUMB_WIDTH, Qt.SmoothTransformation)

        with self._cache_lock:
            self._ram_pixmaps[url] = pixmap
            if len(self._ram_pixmaps) > self.MAX_PIXMAP_ITEMS:
                self._ram_pixmaps.popitem(last=False)

    def clear_ram_cache(self) -> None:
        """Purge all in-memory RAM pixmaps, byte buffers, and native C++ cache."""
        with self._cache_lock:
            self._ram_bytes.clear()
            self._ram_pixmaps.clear()

        if NATIVE_IMAGE_CACHE_AVAILABLE and _native_image_cache:
            try:
                _native_image_cache.cache_clear()
            except Exception:
                pass

        import gc
        gc.collect()

    def prune_disk_cache(self) -> None:
        """Clean up oldest cached files if exceeding max threshold."""
        try:
            files = [os.path.join(self.disk_cache_dir, f) for f in os.listdir(self.disk_cache_dir) if f.endswith(".img")]
            total_size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
            if total_size > self.MAX_DISK_SIZE_BYTES or len(files) > 1500:
                files.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0)
                purge_count = len(files) // 4
                for f in files[:purge_count]:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
        except Exception:
            pass
