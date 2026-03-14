"""
Native C++ Extension Wrapper for HELXAID
=========================================

Provides high-performance C++ extensions with automatic fallback to pure Python.
This wrapper ensures the application works even if the native module is not compiled.

Usage:
    from native_wrapper import get_icon_extractor, get_file_scanner
    
    # Extract single icon
    extractor = get_icon_extractor()
    result = extractor.extract("path/to/file.exe")
    if result.success:
        pixmap = result.to_qpixmap()
    
    # Extract multiple icons in parallel
    icons = extractor.extract_batch(["file1.exe", "file2.exe"], num_threads=4)
"""

import os
import sys
from typing import List, Optional, Callable
from dataclasses import dataclass

# Try to import native module
NATIVE_AVAILABLE = False
_native_module = None

try:
    import helxaid_native as _native_module
    NATIVE_AVAILABLE = True
    print(f"[Native] C++ extensions loaded (v{_native_module.__version__})")
except ImportError as e:
    print(f"[Native] C++ extensions not available: {e}")
    print("[Native] Using pure Python fallback (slower performance)")


@dataclass
class IconData:
    """
    Icon extraction result.
    Contains raw RGBA pixel data that can be converted to QPixmap.
    """
    data: bytes
    width: int
    height: int
    success: bool
    error: str = ""
    
    def to_qpixmap(self):
        """Convert raw RGBA data to QPixmap for Qt display."""
        if not self.success or not self.data or self.width <= 0 or self.height <= 0:
            return None
        
        try:
            from PySide6.QtGui import QImage, QPixmap
            
            # Create QImage from raw RGBA data
            image = QImage(
                self.data,
                self.width,
                self.height,
                self.width * 4,  # Bytes per line (RGBA = 4 bytes per pixel)
                QImage.Format.Format_RGBA8888
            )
            
            # Convert to QPixmap
            return QPixmap.fromImage(image)
        except Exception as e:
            print(f"[Native] Error converting to QPixmap: {e}")
            return None
    
    def to_qimage(self):
        """Convert raw RGBA data to QImage."""
        if not self.success or not self.data or self.width <= 0 or self.height <= 0:
            return None
        
        try:
            from PySide6.QtGui import QImage
            return QImage(
                self.data,
                self.width,
                self.height,
                self.width * 4,
                QImage.Format.Format_RGBA8888
            )
        except Exception as e:
            print(f"[Native] Error converting to QImage: {e}")
            return None


@dataclass  
class FileData:
    """File information from scanner."""
    path: str
    name: str
    extension: str
    size: int
    modified_time: int
    is_directory: bool


class IconExtractor:
    """
    High-performance icon extractor.
    Uses C++ extension if available, falls back to Python implementation.
    """
    
    def __init__(self):
        if NATIVE_AVAILABLE:
            self._native = _native_module.IconExtractor()
        else:
            self._native = None
    
    def extract(self, path: str, size: int = 256) -> IconData:
        """
        Extract icon from file.
        
        Args:
            path: Path to file (exe, lnk, dll, etc.)
            size: Desired icon size (default 256)
            
        Returns:
            IconData with raw RGBA pixel data
        """
        if self._native:
            try:
                result = self._native.extract(path, size)
                if result.success:
                    return IconData(
                        data=result.to_bytes(),
                        width=result.width,
                        height=result.height,
                        success=True,
                        error=""
                    )
                else:
                    return IconData(
                        data=b"",
                        width=0,
                        height=0,
                        success=False,
                        error=result.error
                    )
            except Exception as e:
                print(f"[Native] Extraction error: {e}")
                return self._python_fallback(path, size)
        else:
            return self._python_fallback(path, size)
    
    def extract_batch(
        self,
        paths: List[str],
        size: int = 256,
        num_threads: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[IconData]:
        """
        Extract icons from multiple files in parallel.
        
        Args:
            paths: List of file paths
            size: Desired icon size
            num_threads: Number of worker threads
            progress_callback: Optional callback(current, total)
            
        Returns:
            List of IconData results
        """
        if self._native:
            try:
                results = self._native.extract_batch(paths, size, num_threads)
                return [
                    IconData(
                        data=r.to_bytes() if r.success else b"",
                        width=r.width,
                        height=r.height,
                        success=r.success,
                        error=r.error
                    )
                    for r in results
                ]
            except Exception as e:
                print(f"[Native] Batch extraction error: {e}")
                # Fall through to Python fallback
        
        # Python fallback (sequential)
        results = []
        for i, path in enumerate(paths):
            results.append(self._python_fallback(path, size))
            if progress_callback:
                progress_callback(i + 1, len(paths))
        return results
    
    def get_video_thumbnail(self, path: str, size: int = 512) -> IconData:
        """Extract video thumbnail."""
        if self._native:
            try:
                result = self._native.get_video_thumbnail(path, size)
                return IconData(
                    data=result.to_bytes() if result.success else b"",
                    width=result.width,
                    height=result.height,
                    success=result.success,
                    error=result.error
                )
            except Exception as e:
                print(f"[Native] Video thumbnail error: {e}")
        
        return self._python_fallback(path, size)
    
    def _python_fallback(self, path: str, size: int) -> IconData:
        """
        Pure Python fallback using existing launcher code.
        This is slower but works without the C++ extension.
        """
        try:
            # Try system icon extraction
            from PySide6.QtGui import QIcon, QPixmap
            from PySide6.QtCore import QSize, QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(path))
            
            if not icon.isNull():
                pixmap = icon.pixmap(QSize(size, size))
                if not pixmap.isNull():
                    # We don't have raw data, but we can indicate success
                    return IconData(
                        data=b"",  # No raw data in fallback
                        width=pixmap.width(),
                        height=pixmap.height(),
                        success=True,
                        error=""
                    )
        except Exception as e:
            pass
        
        return IconData(
            data=b"",
            width=0,
            height=0,
            success=False,
            error="Python fallback failed"
        )


class FileScanner:
    """
    High-performance file scanner.
    Uses C++ extension if available, falls back to Python os.walk.
    """
    
    def __init__(self):
        if NATIVE_AVAILABLE:
            self._native = _native_module.FileScanner()
        else:
            self._native = None
    
    def scan(
        self,
        directory: str,
        recursive: bool = True,
        filter_func: Optional[Callable[[FileData], bool]] = None
    ) -> List[FileData]:
        """
        Scan directory for files.
        
        Args:
            directory: Path to scan
            recursive: Include subdirectories
            filter_func: Optional filter function
            
        Returns:
            List of FileData results
        """
        if self._native:
            try:
                # Native module doesn't support Python filter directly
                results = self._native.scan(directory, recursive, None)
                files = [
                    FileData(
                        path=f.path,
                        name=f.name,
                        extension=f.extension,
                        size=f.size,
                        modified_time=f.modified_time,
                        is_directory=f.is_directory
                    )
                    for f in results
                ]
                if filter_func:
                    files = [f for f in files if filter_func(f)]
                return files
            except Exception as e:
                print(f"[Native] Scan error: {e}")
        
        return self._python_scan(directory, recursive, filter_func)
    
    def find_executables(self, directory: str) -> List[FileData]:
        """Find executable files."""
        if self._native:
            try:
                results = self._native.find_executables(directory)
                return [
                    FileData(
                        path=f.path,
                        name=f.name,
                        extension=f.extension,
                        size=f.size,
                        modified_time=f.modified_time,
                        is_directory=f.is_directory
                    )
                    for f in results
                ]
            except Exception as e:
                print(f"[Native] Find executables error: {e}")
        
        return self._python_find_executables(directory)
    
    def find_media_files(self, directory: str) -> List[FileData]:
        """Find audio and video files."""
        if self._native:
            try:
                results = self._native.find_media_files(directory)
                return [
                    FileData(
                        path=f.path,
                        name=f.name,
                        extension=f.extension,
                        size=f.size,
                        modified_time=f.modified_time,
                        is_directory=f.is_directory
                    )
                    for f in results
                ]
            except Exception as e:
                print(f"[Native] Find media files error: {e}")
        
        return self._python_find_media(directory)
    
    def _python_scan(
        self,
        directory: str,
        recursive: bool,
        filter_func: Optional[Callable]
    ) -> List[FileData]:
        """Pure Python fallback using os.walk."""
        results = []
        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    for name in files:
                        path = os.path.join(root, name)
                        info = self._get_file_data(path, name)
                        if filter_func is None or filter_func(info):
                            results.append(info)
            else:
                for name in os.listdir(directory):
                    path = os.path.join(directory, name)
                    if os.path.isfile(path):
                        info = self._get_file_data(path, name)
                        if filter_func is None or filter_func(info):
                            results.append(info)
        except Exception as e:
            print(f"[Native] Python scan error: {e}")
        return results
    
    def _get_file_data(self, path: str, name: str) -> FileData:
        """Get file info for Python fallback."""
        ext = os.path.splitext(name)[1].lower()
        try:
            stat = os.stat(path)
            size = stat.st_size
            mtime = int(stat.st_mtime)
        except:
            size = 0
            mtime = 0
        
        return FileData(
            path=path,
            name=name,
            extension=ext,
            size=size,
            modified_time=mtime,
            is_directory=False
        )
    
    def _python_find_executables(self, directory: str) -> List[FileData]:
        """Python fallback for finding executables."""
        exe_extensions = {'.exe', '.lnk', '.url', '.bat', '.cmd'}
        return self._python_scan(
            directory, True,
            lambda f: f.extension in exe_extensions
        )
    
    def _python_find_media(self, directory: str) -> List[FileData]:
        """Python fallback for finding media files."""
        media_extensions = {
            '.mp3', '.wav', '.flac', '.ogg', '.opus', '.m4a', '.aac', '.wma',
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.flv', '.m4v'
        }
        return self._python_scan(
            directory, True,
            lambda f: f.extension in media_extensions
        )


class ETWNetworkMonitor:
    def __init__(self):
        self._native = None
        if NATIVE_AVAILABLE:
            try:
                self._native = _native_module.ETWNetworkMonitor()
            except Exception as e:
                print(f"[ETW] Failed to create native ETWNetworkMonitor: {e}")

    def is_available(self) -> bool:
        return self._native is not None

    def start(self, config: Optional[dict] = None) -> bool:
        if not self._native:
            return False

        try:
            cfg = _native_module.ETWConfig()
            if config:
                if 'buffer_size_kb' in config:
                    cfg.buffer_size_kb = int(config['buffer_size_kb'])
                if 'buffer_count' in config:
                    cfg.buffer_count = int(config['buffer_count'])
                if 'flush_interval_ms' in config:
                    cfg.flush_interval_ms = int(config['flush_interval_ms'])

            def resolve_name(pid: int) -> str:
                try:
                    import psutil
                    return psutil.Process(pid).name()
                except Exception:
                    return f"PID {pid}"

            def resolve_path(pid: int) -> str:
                try:
                    import psutil
                    return psutil.Process(pid).exe()
                except Exception:
                    return ""

            self._native.set_process_name_resolver(resolve_name)
            self._native.set_process_path_resolver(resolve_path)

            ok = bool(self._native.start(cfg))
            if not ok:
                try:
                    print(f"[ETW] start() failed: {self._native.get_last_error()}")
                except Exception:
                    pass
            return ok
        except Exception as e:
            print(f"[ETW] start() error: {e}")
            return False

    def get_last_error(self) -> str:
        if not self._native:
            return ""
        try:
            return str(self._native.get_last_error())
        except Exception:
            return ""

    def stop(self):
        if not self._native:
            return
        try:
            self._native.stop()
        except Exception as e:
            print(f"[ETW] stop() error: {e}")

    def is_running(self) -> bool:
        if not self._native:
            return False
        try:
            return bool(self._native.is_running())
        except Exception:
            return False

    def reset(self):
        if not self._native:
            return
        try:
            self._native.reset()
        except Exception as e:
            print(f"[ETW] reset() error: {e}")

    def get_process_stats(self) -> list[dict]:
        if not self._native:
            return []
        try:
            stats = self._native.get_process_stats()
            out = []
            for s in stats:
                out.append({
                    'pid': int(s.pid),
                    'name': str(s.process_name or ''),
                    'exe_path': str(s.exe_path or ''),
                    'bytes_sent': int(s.bytes_sent),
                    'bytes_recv': int(s.bytes_recv),
                    'bytes_total': int(s.bytes_total),
                    'last_update': int(s.last_update),
                })
            return out
        except Exception as e:
            print(f"[ETW] get_process_stats() error: {e}")
            return []


def get_etw_network_monitor() -> Optional[ETWNetworkMonitor]:
    m = ETWNetworkMonitor()
    if m.is_available():
        return m
    return None


# =============================================================================
# Singleton instances for easy access
# =============================================================================

_icon_extractor: Optional[IconExtractor] = None
_file_scanner: Optional[FileScanner] = None


def get_icon_extractor() -> IconExtractor:
    """Get the singleton IconExtractor instance."""
    global _icon_extractor
    if _icon_extractor is None:
        _icon_extractor = IconExtractor()
    return _icon_extractor


def get_file_scanner() -> FileScanner:
    """Get the singleton FileScanner instance."""
    global _file_scanner
    if _file_scanner is None:
        _file_scanner = FileScanner()
    return _file_scanner

_boost_engine = None

def get_boost_engine():
    """Get the singleton BoostEngine instance."""
    global _boost_engine
    if _boost_engine is None and NATIVE_AVAILABLE:
        _boost_engine = _native_module.BoostEngine()
    return _boost_engine


# =============================================================================
# Convenience functions
# =============================================================================

def extract_icon(path: str, size: int = 256) -> Optional['QPixmap']:
    """
    Extract icon from file (convenience function).
    
    Returns QPixmap directly for easy Qt integration.
    """
    result = get_icon_extractor().extract(path, size)
    return result.to_qpixmap()


def extract_icons_batch(
    paths: List[str],
    size: int = 256,
    num_threads: int = 4
) -> List[Optional['QPixmap']]:
    """
    Extract icons from multiple files (convenience function).
    
    Returns list of QPixmaps.
    """
    results = get_icon_extractor().extract_batch(paths, size, num_threads)
    return [r.to_qpixmap() for r in results]


def find_executables(directory: str) -> List[dict]:
    """
    Find executables in directory (convenience function).
    
    Returns list of dicts for easy JSON serialization.
    """
    files = get_file_scanner().find_executables(directory)
    return [
        {
            "path": f.path,
            "name": f.name,
            "extension": f.extension,
            "size": f.size,
            "modified_time": f.modified_time
        }
        for f in files
    ]


def find_media_files(directory: str) -> List[dict]:
    """
    Find media files in directory (convenience function).
    
    Returns list of dicts for easy JSON serialization.
    """
    files = get_file_scanner().find_media_files(directory)
    return [
        {
            "path": f.path,
            "name": f.name,
            "extension": f.extension,
            "size": f.size,
            "modified_time": f.modified_time
        }
        for f in files
    ]


# =============================================================================
# Status check
# =============================================================================

def is_native_available() -> bool:
    """Check if native C++ extensions are available."""
    return NATIVE_AVAILABLE


def get_native_version() -> str:
    """Get native module version or 'N/A' if not available."""
    if NATIVE_AVAILABLE and _native_module:
        return _native_module.__version__
    return "N/A"


if __name__ == "__main__":
    # Self-test
    print(f"Native available: {is_native_available()}")
    print(f"Native version: {get_native_version()}")
    
    if is_native_available():
        print("\nTesting icon extraction...")
        result = get_icon_extractor().extract(r"C:\Windows\explorer.exe")
        print(f"Result: {result.width}x{result.height}, success={result.success}")
        
        print("\nTesting file scanner...")
        exes = find_executables(r"C:\Windows")[:5]
        print(f"Found {len(exes)} executables")
        for exe in exes:
            print(f"  - {exe['name']}")
