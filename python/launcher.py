import sys
import gc  # For memory cleanup
import json
import os
import random
import subprocess
import ctypes
import re
import time
import threading
import urllib.request
import psutil  # For background game detection
import urllib.parse
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QSlider, QMessageBox, QScrollArea, QMenu, QInputDialog,
    QSizePolicy, QHBoxLayout, QDialog, QDialogButtonBox,
    QTextEdit, QLineEdit, QSpinBox, QAbstractSpinBox, QCheckBox, QGraphicsOpacityEffect,
    QProgressBar, QComboBox, QGroupBox, QSystemTrayIcon, QFormLayout, QStackedWidget, QFrame, QToolTip,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPainterPath, QColor, QDesktopServices, QLinearGradient, QImage, QFont, QFontMetrics
from PySide6.QtCore import Qt, QSize, QSizeF, QTimer, QPropertyAnimation, QEasingCurve, QUrl, Signal, Slot, QEvent, QThread
# Qt Multimedia is lazy-loaded when music panel is opened to reduce startup RAM
# from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QMediaMetaData
from PlaylistWidget import PlaylistWidget
from integrations.cpu_controller import is_uxtu_installed, is_ryzenadj_available, CPUControlSettings, SAFETY_LIMITS, get_default_profile, validate_value, DEFAULT_UXTU_PATH, apply_settings_direct
from AnimatedButton import AnimatedButton
from CrosshairWidget import CrosshairWidget
from HardwarePanelWidget import HardwarePanelWidget
from macro_system.integration.hardware_manager import get_hardware_manager

# Native C++ extensions for performance (with Python fallback)
try:
    from native_wrapper import (
        get_icon_extractor, 
        get_file_scanner,
        NATIVE_AVAILABLE as NATIVE_CPP_AVAILABLE
    )
except ImportError:
    NATIVE_CPP_AVAILABLE = False
    get_icon_extractor = None
    get_file_scanner = None
    print("[Native] C++ extensions not available, using pure Python")

class NoScrollSlider(QSlider):
    def wheelEvent(self, event):
        event.ignore()

# Windows API modules - lazy loaded for faster startup
WINDOWS_API_AVAILABLE = True  # Assume available, will be set False if import fails on first use
_win32_modules_loaded = False
win32com_client = None
win32con = None
win32ui = None
win32gui = None
Image = None

def _ensure_win32_loaded():
    """Lazy load win32 modules on first use."""
    global _win32_modules_loaded, win32com_client, win32con, win32ui, win32gui, Image, WINDOWS_API_AVAILABLE
    if _win32_modules_loaded:
        return WINDOWS_API_AVAILABLE
    try:
        import win32com.client as _win32com_client
        import win32con as _win32con
        import win32ui as _win32ui
        import win32gui as _win32gui
        from PIL import Image as _Image
        win32com_client = _win32com_client
        win32con = _win32con
        win32ui = _win32ui
        win32gui = _win32gui
        Image = _Image
        WINDOWS_API_AVAILABLE = True
    except ImportError:
        print("Warning: Some Windows API modules are not available. Icon extraction may not work.")
        WINDOWS_API_AVAILABLE = False
    _win32_modules_loaded = True
    return WINDOWS_API_AVAILABLE



# Get the directory where resources are located
# For PyInstaller bundle: use temp extraction folder (_MEIPASS)
# For development: use script directory
if hasattr(sys, '_MEIPASS'):
    SCRIPT_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Use AppData for persistent data storage (config.json, icons, etc.)
# This prevents data loss when PyInstaller extracts to different temp folders
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
os.makedirs(APPDATA_DIR, exist_ok=True)

# Set the absolute path to game_library.json in persistent location
JSON_PATH = os.path.join(APPDATA_DIR, "game_library.json")

# Cleanup leftover temp files from previous runs
def _cleanup_old_temp_files():
    """Remove leftover helxaid_icon_* temp folders and old temp ICO files."""
    try:
        import tempfile
        import shutil
        temp_dir = tempfile.gettempdir()
        
        # Remove old helxaid_icon_* folders
        for item in os.listdir(temp_dir):
            if item.startswith("helxaid_icon_"):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                        print(f"[Cleanup] Removed: {item_path}")
                except:
                    pass
        
        # Remove old tmp*.ico files (older than 1 day)
        import time
        now = time.time()
        for item in os.listdir(temp_dir):
            if item.startswith("tmp") and item.endswith(".ico"):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path):
                        # Only delete if older than 24 hours
                        if now - os.path.getmtime(item_path) > 86400:
                            os.remove(item_path)
                except:
                    pass
    except Exception as e:
        print(f"[Cleanup] Error: {e}")

# Run cleanup at startup (in background thread to not block)
def _run_startup_cleanup():
    """Run cleanup tasks in background thread."""
    _cleanup_old_temp_files()

# Refresh Windows icon cache at startup (fixes taskbar icon issues)
def _refresh_icon_cache():
    """Refresh Windows icon cache to ensure taskbar icons display correctly."""
    try:
        import subprocess
        subprocess.run(
            ['ie4uinit.exe', '-show'],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
    except Exception:
        pass  # Silently ignore if fails

# Start background cleanup thread (non-blocking startup optimization)
_startup_cleanup_thread = threading.Thread(target=_run_startup_cleanup, daemon=True)
_startup_cleanup_thread.start()

# Icon cache refresh also in background (non-blocking)
_icon_cache_thread = threading.Thread(target=_refresh_icon_cache, daemon=True)
_icon_cache_thread.start()

# ----------------------------------------------------------
# Windows Thumbnail Extraction (IShellItemImageFactory)
# ----------------------------------------------------------
try:
    from ctypes import POINTER, Structure, c_int, c_void_p, c_ulong, byref, cast, windll, HRESULT, WinError, c_wchar_p
    from ctypes.wintypes import POINT, RECT, SIZE
    
    # GUID for IShellItemImageFactory
    class GUID(Structure):
        _fields_ = [("Data1", c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    
    IID_IShellItemImageFactory = GUID(0xbcc18b79, 0xba16, 0x442f, (ctypes.c_ubyte * 8)(0x80, 0xc4, 0x8a, 0x59, 0xc3, 0x0c, 0x46, 0x3b))
    
    class IShellItemImageFactory(Structure):
        _fields_ = [("lpVtbl", c_void_p)]
        
    # VTable definition handled dynamically or via simple offsetting if we are careful
    # GetImage is the 4th method (Index 3): QueryInterface, AddRef, Release, GetImage
    
    # SHCreateItemFromParsingName
    SHCreateItemFromParsingName = windll.shell32.SHCreateItemFromParsingName
    SHCreateItemFromParsingName.argtypes = [c_wchar_p, c_void_p, POINTER(GUID), POINTER(POINTER(IShellItemImageFactory))]
    SHCreateItemFromParsingName.restype = HRESULT

    def get_video_thumbnail(file_path):
        """Extract high-res thumbnail from video file using Windows Shell API."""
        if not os.path.exists(file_path): return None
        
        try:
            # Initialize COM if needed (usually handled by Qt, but safe to try)
            ctypes.windll.ole32.CoInitialize(None)
            
            pFactory = POINTER(IShellItemImageFactory)()
            hr = SHCreateItemFromParsingName(file_path, None, byref(IID_IShellItemImageFactory), byref(pFactory))
            
            if hr != 0 or not pFactory:
                return None
                
            # GetImage method def: HRESULT GetImage(SIZE size, int flags, HBITMAP *phbm)
            # VTable index 3
            # We need to access the function pointer
            
            # Helper to call VTable method
            # prototype: HRESULT (STDMETHODCALLTYPE *GetImage)(IShellItemImageFactory *This, SIZE size, SIIGBF flags, HBITMAP *phbm);
            GetImage_Proto = ctypes.WINFUNCTYPE(HRESULT, POINTER(IShellItemImageFactory), SIZE, c_int, POINTER(c_void_p))
            
            # Access VTable
            vtable = cast(pFactory.contents.lpVtbl, POINTER(c_void_p))
            GetImage_Func = GetImage_Proto(vtable[3])
            
            size = SIZE(600, 600) # Request 600x600 or similar
            flags = 0x0 # SIIGBF_RESIZETOFIT
            hbitmap = c_void_p()
            
            hr = GetImage_Func(pFactory, size, flags, byref(hbitmap))
            
            # Release factory
            # Release is index 2
            Release_Proto = ctypes.WINFUNCTYPE(c_ulong, POINTER(IShellItemImageFactory))
            Release_Func = Release_Proto(vtable[2])
            Release_Func(pFactory)
            

                
            # GDI definitions
            GetDC = windll.user32.GetDC
            ReleaseDC = windll.user32.ReleaseDC
            CreateCompatibleDC = windll.gdi32.CreateCompatibleDC
            DeleteDC = windll.gdi32.DeleteDC
            SelectObject = windll.gdi32.SelectObject
            GetObjectW = windll.gdi32.GetObjectW
            GetDIBits = windll.gdi32.GetDIBits
            DeleteObject = windll.gdi32.DeleteObject

            class BITMAP(Structure):
                _fields_ = [
                    ("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                    ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort),
                    ("bmBitsPixel", ctypes.c_ushort), ("bmBits", c_void_p)
                ]

            class BITMAPINFOHEADER(Structure):
                _fields_ = [
                    ("biSize", c_ulong), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort),
                    ("biCompression", c_ulong), ("biSizeImage", c_ulong),
                    ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", c_ulong), ("biClrImportant", c_ulong)
                ]
                
            class BITMAPINFO(Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", c_ulong * 3)]

            def hbitmap_to_qpixmap(hbitmap):
                hdc = GetDC(None)
                cdc = CreateCompatibleDC(hdc)
                SelectObject(cdc, hbitmap)
                
                bmp = BITMAP()
                GetObjectW(hbitmap, ctypes.sizeof(bmp), byref(bmp))
                
                w, h = bmp.bmWidth, bmp.bmHeight
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = w
                bmi.bmiHeader.biHeight = -h  # Top-down
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0 # BI_RGB
                
                buffer_len = w * h * 4
                buffer = ctypes.create_string_buffer(buffer_len)
                
                GetDIBits(cdc, hbitmap, 0, h, buffer, byref(bmi), 0) # DIB_RGB_COLORS
                
                DeleteDC(cdc)
                ReleaseDC(None, hdc)
                
                img = QImage(buffer, w, h, QImage.Format_ARGB32)
                return QPixmap.fromImage(img.copy())

            if hr == 0 and hbitmap:
                try:
                    return hbitmap_to_qpixmap(hbitmap)
                finally:
                    DeleteObject(hbitmap)
                    
            return None
                
        except Exception as e:
            print(f"Thumbnail error: {e}")
            
        return None

except Exception:
    def get_video_thumbnail(file_path): return None


# ----------------------------------------------------------
# Windows Taskbar Thumbnail Toolbar (Media Buttons)
# ----------------------------------------------------------
TASKBAR_TOOLBAR_AVAILABLE = False

# Button IDs (used for WM_COMMAND identification)
BUTTON_PREV = 100
BUTTON_PLAYPAUSE = 101
BUTTON_NEXT = 102

try:
    import ctypes
    from ctypes import Structure, c_int, c_uint, c_wchar, POINTER, byref, windll, c_void_p, WINFUNCTYPE, HRESULT
    from ctypes.wintypes import HWND, HICON, DWORD, UINT, BOOL
    
    # GUID structure
    class GUID(Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8)
        ]
    
    # THUMBBUTTON structure for Windows 7+ taskbar
    class THUMBBUTTON(Structure):
        _fields_ = [
            ("dwMask", DWORD),
            ("iId", UINT),
            ("iBitmap", UINT),
            ("hIcon", HICON),
            ("szTip", c_wchar * 260),
            ("dwFlags", DWORD),
        ]
    
    # Constants
    THB_BITMAP = 0x1
    THB_ICON = 0x2
    THB_TOOLTIP = 0x4
    THB_FLAGS = 0x8
    THBF_ENABLED = 0x0
    THBF_DISABLED = 0x1
    THBF_DISMISSONCLICK = 0x2
    THBF_NOBACKGROUND = 0x4
    THBF_HIDDEN = 0x8
    
    # GUIDs
    CLSID_TaskbarList = GUID(0x56FDF344, 0xFD6D, 0x11d0, (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90))
    IID_ITaskbarList3 = GUID(0xEA1AFB91, 0x9E28, 0x4B86, (ctypes.c_ubyte * 8)(0x90, 0xE9, 0x9E, 0x9F, 0x8A, 0x5E, 0xEF, 0xAF))
    
    # COM function prototypes
    CoCreateInstance = windll.ole32.CoCreateInstance
    CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, DWORD, POINTER(GUID), POINTER(c_void_p)]
    CoCreateInstance.restype = HRESULT
    
    CLSCTX_INPROC_SERVER = 0x1
    
    class TaskbarThumbnailToolbar:
        """Helper class to manage Windows 7+ taskbar thumbnail toolbar buttons using pure ctypes."""
        
        def __init__(self, hwnd, on_prev=None, on_playpause=None, on_next=None):
            self.hwnd = hwnd
            self.on_prev = on_prev
            self.on_playpause = on_playpause
            self.on_next = on_next
            self.taskbar = None
            self.buttons_added = False
            self._is_playing = False
            
            # Load icons
            self._load_icons()
            
            # Initialize taskbar interface
            self._init_taskbar()
        
        def _load_icons(self):
            """Load media control icons from PNG files."""
            try:
                from PIL import Image
                import os
                
                user32 = windll.user32
                CreateIconFromResourceEx = user32.CreateIconFromResourceEx
                
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                def load_icon_from_png(filename):
                    """Load a PNG file and convert to HICON."""
                    path = os.path.join(script_dir, filename)
                    if not os.path.exists(path):
                        print(f"Icon not found: {path}")
                        return 0
                    
                    try:
                        # Open image and resize to 16x16 for taskbar
                        img = Image.open(path)
                        img = img.convert("RGBA")
                        img = img.resize((16, 16), Image.Resampling.LANCZOS)
                        
                        # Convert to ICO format bytes in memory
                        import io
                        ico_buffer = io.BytesIO()
                        img.save(ico_buffer, format='ICO', sizes=[(16, 16)])
                        ico_buffer.seek(0)
                        ico_data = ico_buffer.read()
                        
                        # Skip ICO header (22 bytes for single-image ICO)
                        # ICO header: 6 bytes
                        # Directory entry: 16 bytes
                        # Then the PNG/BMP data
                        header_size = 22
                        image_data = ico_data[header_size:]
                        
                        # Create icon using CreateIconFromResourceEx
                        LR_DEFAULTCOLOR = 0x0000
                        icon = CreateIconFromResourceEx(
                            image_data,
                            len(image_data),
                            True,  # fIcon
                            0x00030000,  # Version
                            16, 16,
                            LR_DEFAULTCOLOR
                        )
                        return icon if icon else 0
                    except Exception as e:
                        print(f"Failed to load icon {filename}: {e}")
                        return 0
                
                self.icon_prev = load_icon_from_png("UI Taskbar Icons/taskbar-previous-icon.png")
                self.icon_play = load_icon_from_png("UI Taskbar Icons/taskbar-play-icon.png")
                self.icon_pause = load_icon_from_png("UI Taskbar Icons/taskbar-pause-icon.png")
                self.icon_next = load_icon_from_png("UI Taskbar Icons/taskbar-next-icon.png")
                
                print(f"Loaded media icons: prev={self.icon_prev}, play={self.icon_play}, pause={self.icon_pause}, next={self.icon_next}")
                
                # If any icons failed, use simple fallback
                if not all([self.icon_prev, self.icon_play, self.icon_pause, self.icon_next]):
                    print("Some icons failed to load, using fallback")
                    self._load_fallback_icons()
                    
            except Exception as e:
                print(f"Could not load media icons: {e}")
                self._load_fallback_icons()
        
        def _load_fallback_icons(self):
            """Use system icons as fallback."""
            try:
                shell32 = windll.shell32
                ExtractIconExW = shell32.ExtractIconExW
                
                hicons_large = (HICON * 1)()
                hicons_small = (HICON * 1)()
                
                shell32_path = r"C:\Windows\System32\shell32.dll"
                
                # Use generic arrow icons as fallback
                ExtractIconExW(shell32_path, 137, hicons_large, hicons_small, 1)
                self.icon_prev = hicons_small[0] if hicons_small[0] else 0
                
                ExtractIconExW(shell32_path, 131, hicons_large, hicons_small, 1)
                self.icon_play = hicons_small[0] if hicons_small[0] else 0
                
                ExtractIconExW(shell32_path, 132, hicons_large, hicons_small, 1)
                self.icon_pause = hicons_small[0] if hicons_small[0] else 0
                
                ExtractIconExW(shell32_path, 138, hicons_large, hicons_small, 1)
                self.icon_next = hicons_small[0] if hicons_small[0] else 0
            except:
                self.icon_prev = self.icon_play = self.icon_pause = self.icon_next = 0
        
        def _init_taskbar(self):
            """Initialize the ITaskbarList3 COM interface using pure ctypes."""
            try:
                # Initialize COM
                windll.ole32.CoInitialize(None)
                
                # Create TaskbarList COM object
                taskbar_ptr = c_void_p()
                hr = CoCreateInstance(
                    byref(CLSID_TaskbarList),
                    None,
                    CLSCTX_INPROC_SERVER,
                    byref(IID_ITaskbarList3),
                    byref(taskbar_ptr)
                )
                
                if hr != 0 or not taskbar_ptr:
                    print(f"CoCreateInstance failed: {hr}")
                    self.taskbar = None
                    return
                
                self.taskbar = taskbar_ptr.value
                
                # Call HrInit (VTable index 3)
                # VTable: QueryInterface(0), AddRef(1), Release(2), HrInit(3)
                vtable = ctypes.cast(self.taskbar, POINTER(c_void_p)).contents
                vtable_ptr = ctypes.cast(vtable, POINTER(c_void_p * 20)).contents
                
                HrInit_proto = WINFUNCTYPE(HRESULT, c_void_p)
                HrInit = HrInit_proto(vtable_ptr[3])
                hr = HrInit(self.taskbar)
                
                if hr != 0:
                    print(f"HrInit failed: {hr}")
                    self.taskbar = None
                else:
                    print("ITaskbarList3 initialized successfully")
                    
            except Exception as e:
                print(f"Could not create ITaskbarList3: {e}")
                self.taskbar = None
        
        def add_buttons(self):
            """Add the thumbnail toolbar buttons."""
            if not self.taskbar or self.buttons_added:
                return False
            
            try:
                buttons = (THUMBBUTTON * 3)()
                
                # Previous button
                buttons[0].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
                buttons[0].iId = BUTTON_PREV
                buttons[0].hIcon = self.icon_prev
                buttons[0].szTip = "Previous"
                buttons[0].dwFlags = THBF_ENABLED
                
                # Play/Pause toggle button
                buttons[1].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
                buttons[1].iId = BUTTON_PLAYPAUSE
                buttons[1].hIcon = self.icon_play
                buttons[1].szTip = "Play"
                buttons[1].dwFlags = THBF_ENABLED
                
                # Next button
                buttons[2].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
                buttons[2].iId = BUTTON_NEXT
                buttons[2].hIcon = self.icon_next
                buttons[2].szTip = "Next"
                buttons[2].dwFlags = THBF_ENABLED
                
                # ThumbBarAddButtons is VTable index 18
                # ITaskbarList: HrInit(3), AddTab(4), DeleteTab(5), ActivateTab(6), SetActiveAlt(7)
                # ITaskbarList2: MarkFullscreenWindow(8)
                # ITaskbarList3: SetProgressValue(9), SetProgressState(10), RegisterTab(11), UnregisterTab(12),
                #                SetTabOrder(13), SetTabActive(14), ThumbBarAddButtons(15), ThumbBarUpdateButtons(16),
                #                ThumbBarSetImageList(17), SetOverlayIcon(18), SetThumbnailTooltip(19), SetThumbnailClip(20)
                vtable = ctypes.cast(self.taskbar, POINTER(c_void_p)).contents
                vtable_ptr = ctypes.cast(vtable, POINTER(c_void_p * 25)).contents
                
                # ThumbBarAddButtons(HWND hwnd, UINT cButtons, LPTHUMBBUTTON pButton)
                ThumbBarAddButtons_proto = WINFUNCTYPE(HRESULT, c_void_p, HWND, UINT, POINTER(THUMBBUTTON))
                ThumbBarAddButtons = ThumbBarAddButtons_proto(vtable_ptr[15])
                
                hr = ThumbBarAddButtons(self.taskbar, self.hwnd, 3, buttons)
                
                if hr == 0:
                    self.buttons_added = True
                    print("Taskbar buttons added successfully")
                    return True
                else:
                    print(f"ThumbBarAddButtons failed: {hr}")
                    return False
                    
            except Exception as e:
                print(f"Could not add taskbar buttons: {e}")
                return False
        
        def update_play_state(self, is_playing):
            """Update the play/pause button icon based on playback state."""
            if not self.taskbar or not self.buttons_added:
                return
            
            self._is_playing = is_playing
            
            try:
                buttons = (THUMBBUTTON * 1)()
                buttons[0].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
                buttons[0].iId = BUTTON_PLAYPAUSE
                buttons[0].hIcon = self.icon_pause if is_playing else self.icon_play
                buttons[0].szTip = "Pause" if is_playing else "Play"
                buttons[0].dwFlags = THBF_ENABLED
                
                vtable = ctypes.cast(self.taskbar, POINTER(c_void_p)).contents
                vtable_ptr = ctypes.cast(vtable, POINTER(c_void_p * 25)).contents
                
                # ThumbBarUpdateButtons is VTable index 16
                ThumbBarUpdateButtons_proto = WINFUNCTYPE(HRESULT, c_void_p, HWND, UINT, POINTER(THUMBBUTTON))
                ThumbBarUpdateButtons = ThumbBarUpdateButtons_proto(vtable_ptr[16])
                
                ThumbBarUpdateButtons(self.taskbar, self.hwnd, 1, buttons)
            except Exception as e:
                print(f"Could not update taskbar button: {e}")
        
        def handle_button_click(self, button_id):
            """Handle a button click from WM_COMMAND."""
            if button_id == BUTTON_PREV and self.on_prev:
                self.on_prev()
            elif button_id == BUTTON_PLAYPAUSE and self.on_playpause:
                self.on_playpause()
            elif button_id == BUTTON_NEXT and self.on_next:
                self.on_next()
    
    TASKBAR_TOOLBAR_AVAILABLE = True
    
except Exception as e:
    print(f"Taskbar toolbar not available: {e}")
    TaskbarThumbnailToolbar = None


# ----------------------------------------------------------
# Generic icon detection + text icon replacement
# ----------------------------------------------------------

# Known generic engine/store/launcher exe name patterns.
# If the icon was extracted from an exe matching any of these,
# the icon is likely a generic placeholder (Unity cube, Unreal
# shield, Epic store logo, etc.) and should be replaced with
# a text-based icon showing the game's actual title.
_GENERIC_EXE_PATTERNS = [
    # Engine defaults — these ship the engine logo as their icon
    "unityplayer", "unitycrashandler", "unity",
    "ue4", "ue5", "unrealengine", "unreal",
    "win64-shipping", "win64_client",  # Unreal-built games with no custom icon
    "win32-shipping",
    "godot",
    # Store defaults
    "epicgameslauncher", "epic games",
    # Runtime stubs
    "javaw", "java",
    "python", "pythonw",
    "electron",
]

# Known generic icon FILENAME patterns (the cached PNG name).
# These catch cases where the icon was already extracted and
# cached but the filename reveals it came from a generic source.
_GENERIC_ICON_NAME_PATTERNS = [
    "unityplayer", "unity_",
    "ue4", "ue5", "unrealengine",
    "epicgameslauncher",
    "godot",

]


def _is_generic_icon(icon_path, exe_path=""):
    """Check if an icon is a generic engine/store placeholder.
    
    Uses two detection methods:
    1. Pattern matching: check exe name against known engine/store patterns
    2. Perceptual hash: compute an 8x8 average hash of the icon and compare
       against a set of known generic icon hashes (Unreal logo, Epic logo, etc.)
    
    Args:
        icon_path (str): Path to the cached icon PNG.
        exe_path  (str): Path to the source executable (optional).
    
    Returns:
        bool: True if the icon is likely a generic placeholder.
    """
    # --- Method 1: Icon filename pattern matching ---
    if icon_path:
        icon_name = os.path.basename(icon_path).lower()
        for pattern in _GENERIC_ICON_NAME_PATTERNS:
            if pattern in icon_name:
                return True
    
    # --- Method 2: Exe name pattern matching ---
    if exe_path:
        exe_name = os.path.splitext(os.path.basename(exe_path))[0].lower()
        exe_clean = exe_name.replace("-", "").replace("_", "").replace(" ", "")
        for pattern in _GENERIC_EXE_PATTERNS:
            clean_pat = pattern.replace("-", "").replace("_", "").replace(" ", "")
            if clean_pat in exe_clean:
                return True
    
    # --- Method 3: Perceptual hash comparison ---
    # Compute an 8x8 average hash of the icon and compare against known
    # generic icon hashes.  This catches cases where the exe name is custom
    # but the icon is a stock engine/store logo (e.g. ReadyOrNot.exe using
    # the Epic Games Store logo, or Ride.exe using the Unreal Engine logo).
    if icon_path and os.path.exists(icon_path):
        icon_hash = _compute_icon_hash(icon_path)
        if icon_hash is not None:
            for known_hash in _KNOWN_GENERIC_HASHES:
                if _hamming_distance(icon_hash, known_hash) <= 5:
                    return True
    
    return False


def _compute_icon_hash(icon_path, size=8):
    """Compute an 8x8 perceptual average hash of an icon image.
    
    Scales the image to 8x8, converts to grayscale, then generates a
    64-bit hash where each bit is 1 if the pixel brightness exceeds
    the image average, 0 otherwise.
    
    Args:
        icon_path (str): Path to the icon file.
        size      (int): Hash grid size (8 = 64-bit hash).
    
    Returns:
        int: The 64-bit perceptual hash, or None if loading fails.
    """
    try:
        img = QImage(icon_path)
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        small = img.scaled(size, size)
        raw = bytes(small.constBits())
        bpl = small.bytesPerLine()
        
        vals = []
        for y in range(size):
            for x in range(size):
                off = y * bpl + x * 4
                b, g, r = raw[off], raw[off + 1], raw[off + 2]
                vals.append(int(0.299 * r + 0.587 * g + 0.114 * b))
        
        avg = sum(vals) / len(vals)
        bits = 0
        for v in vals:
            bits = (bits << 1) | (1 if v > avg else 0)
        return bits
    except Exception:
        return None


def _hamming_distance(a, b):
    """Count the number of differing bits between two integers.
    
    Used for fuzzy matching of perceptual hashes. A distance of 0 means
    identical images; distances <= 5 are considered near-identical.
    """
    xor = a ^ b
    count = 0
    while xor:
        count += xor & 1
        xor >>= 1
    return count


# Known perceptual hashes of generic engine/store icons.
# These were computed from actual icon files using _compute_icon_hash().
# Hamming distance <= 5 is used for fuzzy matching to handle minor
# variations (anti-aliasing, compression artifacts, slight resizes).
_KNOWN_GENERIC_HASHES = [
    0x2400a51818bd0024,  # Unreal Engine logo (stylized "U" in circle)
    0x2c2c0c00080000,    # Epic Games Store logo (dark shield with "EPIC GAMES")
]


def _create_text_icon(game_name, size):
    """Generate a text-based icon pixmap for games with generic icons.
    
    Creates a dark-gradient rounded-rect background with the game's
    title rendered in large Orbitron font.  Long titles are word-wrapped
    to fit within the icon bounds.
    
    Args:
        game_name (str): The game title to display.
        size      (int): Width and height of the output pixmap.
    
    Returns:
        QPixmap: The generated text icon.
    """
    
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    
    # --- Dark gradient background with rounded corners ---
    margin = 4
    rect = pixmap.rect().adjusted(margin, margin, -margin, -margin)
    radius = size * 0.12  # 12% corner radius
    
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor(45, 45, 55))
    grad.setColorAt(1.0, QColor(25, 25, 35))
    
    path = QPainterPath()
    path.addRoundedRect(float(rect.x()), float(rect.y()),
                        float(rect.width()), float(rect.height()),
                        radius, radius)
    p.fillPath(path, grad)
    
    # Subtle border
    p.setPen(QColor(80, 80, 100, 120))
    p.drawRoundedRect(rect, radius, radius)
    
    # --- Render game title text ---
    # Use Orbitron if available (loaded by the app), else fallback
    font = QFont("Orbitron", 1)
    font.setWeight(QFont.Weight.Bold)
    
    # Auto-size font to fit within the icon.
    # Start with a large size and shrink until text fits.
    text_area = rect.adjusted(8, 8, -8, -8)
    max_font_size = size // 3  # Start large
    
    # Word-wrap the title if it's long
    words = game_name.split()
    
    for font_size in range(max_font_size, 6, -1):
        font.setPixelSize(font_size)
        fm = QFontMetrics(font)
        
        # Try wrapping into lines that fit the width
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            if fm.horizontalAdvance(test_line) <= text_area.width():
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Check if all lines fit vertically
        total_height = len(lines) * fm.height()
        if total_height <= text_area.height() and len(lines) <= 4:
            break
    else:
        # Absolute minimum — truncate to 2 lines if needed
        font.setPixelSize(7)
        fm = QFontMetrics(font)
        lines = [game_name[:12], game_name[12:24]] if len(game_name) > 12 else [game_name]
    
    # Draw each line centered
    p.setFont(font)
    p.setPen(QColor(220, 220, 230))
    
    total_text_h = len(lines) * fm.height()
    y_start = text_area.y() + (text_area.height() - total_text_h) // 2
    
    for i, line in enumerate(lines):
        line_w = fm.horizontalAdvance(line)
        x = text_area.x() + (text_area.width() - line_w) // 2
        y = y_start + i * fm.height() + fm.ascent()
        p.drawText(x, y, line)
    
    p.end()
    return pixmap


# ----------------------------------------------------------
# Shape-matching icon background
# ----------------------------------------------------------

# Bump this string whenever the background-generation logic changes.
# It is appended to every icon cache key so stale cached icons from a
# previous version of the logic are never reused.
_BG_ICON_VERSION = "bgv3"

def _create_shaped_bg_icon(pixmap):
    """Create a pixmap with a dark shaped background behind the icon.
    
    Uses a 3-phase geometric analysis to decide whether the icon needs a
    shaped background at all.  Simple shapes (square, circle, triangle)
    are returned unchanged; complex shapes (characters, multi-part icons,
    icons with interior holes) get a semi-transparent black background
    that matches the icon's filled silhouette.
    
    Phase 1 - Quick transparency check:
        < 2% transparent pixels  ->  solid/near-solid square  ->  SKIP
    Phase 2 - Structural analysis (BFS flood-fill):
        Interior holes > 0      ->  complex (e.g. REPO eyes)  ->  APPLY
        Opaque components > 1   ->  multi-part icon            ->  APPLY
    Phase 3 - Isoperimetric ratio (shape regularity):
        perimeter^2 / (4*pi*area) >= 1.8  ->  irregular boundary  ->  APPLY
        Otherwise                         ->  smooth simple shape  ->  SKIP
    
    When a background IS applied:
        - Background = BFS-filled silhouette (holes filled in) at full icon size
        - Icon = scaled to 95% and centered on top, so 2.5% of background
          peeks out on each side
    
    Args:
        pixmap (QPixmap): The already-scaled icon pixmap.
    
    Returns:
        QPixmap: Icon with shaped background, or the original unchanged.
    """
    try:
        import math
        from collections import deque
        
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, h = img.width(), img.height()
        
        if w < 4 or h < 4:
            return pixmap
        
        n_total = w * h
        
        # ============================================================
        # PHASE 1: Fast transparency mask + early exit for solid icons
        # ============================================================
        # ARGB32 on little-endian (x86): pixel bytes are [B, G, R, A].
        # Alpha lives at byte offset 3 within each 4-byte pixel.
        # Reading raw bytes is 10-50x faster than per-pixel img.pixel().
        raw = bytes(img.constBits())
        bpl = img.bytesPerLine()
        ALPHA_THRESHOLD = 30
        
        is_transp = bytearray(n_total)
        for y in range(h):
            rb = y * bpl
            ob = y * w
            for x in range(w):
                if raw[rb + x * 4 + 3] < ALPHA_THRESHOLD:
                    is_transp[ob + x] = 1
        
        n_transp = sum(is_transp)
        
        # < 2% transparent = solid square or nearly-solid rounded square.
        # No visual benefit from adding a dark background ring.
        if n_transp < n_total * 0.02:
            return pixmap
        
        # ============================================================
        # PHASE 2: BFS exterior flood-fill + structural analysis
        # ============================================================
        # Flood-fill from the canvas edges to mark all exterior-transparent
        # pixels.  Transparent pixels NOT reached = interior holes (enclosed
        # by the icon shape).  Examples: REPO's eye whites, Schedule I's
        # dollar-sign cutouts.
        exterior = bytearray(n_total)
        queue = deque()
        
        # Seed from all four canvas edges
        for x in range(w):
            for sy in (0, h - 1):
                idx = sy * w + x
                if is_transp[idx] and not exterior[idx]:
                    exterior[idx] = 1
                    queue.append(idx)
        for y in range(1, h - 1):
            for sx in (0, w - 1):
                idx = y * w + sx
                if is_transp[idx] and not exterior[idx]:
                    exterior[idx] = 1
                    queue.append(idx)
        
        # 4-connected BFS
        while queue:
            idx = queue.popleft()
            cy, cx = divmod(idx, w)
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w:
                    ni = ny * w + nx
                    if is_transp[ni] and not exterior[ni]:
                        exterior[ni] = 1
                        queue.append(ni)
        
        # --- 2a: Interior hole count ---
        # Any enclosed transparent pixel means the icon is complex.
        needs_bg = False
        n_holes = 0
        for i in range(n_total):
            if is_transp[i] and not exterior[i]:
                n_holes += 1
        if n_holes > 0:
            needs_bg = True
        
        # --- 2b: Connected component count (opaque regions) ---
        # Only computed when no holes found.  Multiple disconnected opaque
        # parts (e.g. REPO head + body, PVZ plant + pot) → complex icon.
        if not needs_bg:
            visited = bytearray(n_total)
            n_comp = 0
            for i in range(n_total):
                if not is_transp[i] and not visited[i]:
                    n_comp += 1
                    bfs_q = deque([i])
                    visited[i] = 1
                    while bfs_q:
                        ci = bfs_q.popleft()
                        cy2, cx2 = divmod(ci, w)
                        for ny2, nx2 in ((cy2 - 1, cx2), (cy2 + 1, cx2),
                                         (cy2, cx2 - 1), (cy2, cx2 + 1)):
                            if 0 <= ny2 < h and 0 <= nx2 < w:
                                ni2 = ny2 * w + nx2
                                if not is_transp[ni2] and not visited[ni2]:
                                    visited[ni2] = 1
                                    bfs_q.append(ni2)
            if n_comp > 1:
                needs_bg = True
        
        # ============================================================
        # PHASE 3: Isoperimetric ratio (boundary irregularity)
        # ============================================================
        # Only reached for single-component, hole-free icons with >= 2%
        # transparency (e.g. circles, triangles, organic silhouettes).
        #
        # The isoperimetric ratio  =  perimeter^2 / (4 * pi * area)
        # measures how "compact" a shape is relative to a circle:
        #   Circle   = 1.0   (most compact)
        #   Square   ~ 1.27
        #   Triangle ~ 1.65
        #   Complex character silhouettes   > 2.0
        #
        # Threshold 1.8 cleanly separates simple geometric shapes from
        # irregular character outlines.  Validated against 36 game icons.
        if not needs_bg:
            boundary_count = 0
            opaque_area = n_total - n_transp
            for y in range(h):
                for x in range(w):
                    idx = y * w + x
                    if not is_transp[idx]:
                        # A pixel is on the boundary if any 4-neighbor is
                        # transparent or out-of-bounds
                        for ny, nx in ((y - 1, x), (y + 1, x),
                                       (y, x - 1), (y, x + 1)):
                            if (ny < 0 or ny >= h or nx < 0 or nx >= w
                                    or is_transp[ny * w + nx]):
                                boundary_count += 1
                                break
            
            if opaque_area > 0:
                iso_ratio = boundary_count ** 2 / (4.0 * math.pi * opaque_area)
            else:
                iso_ratio = 0.0
            
            if iso_ratio >= 1.8:
                needs_bg = True
        
        # --- Decision: skip if simple shape ---
        if not needs_bg:
            return pixmap
        
        # ============================================================
        # BUILD BACKGROUND + COMPOSITE
        # ============================================================
        
        # --- Build filled-silhouette mask (holes filled in) ---
        bg_mask = QImage(w, h, QImage.Format.Format_ARGB32)
        bg_mask.fill(QColor(0, 0, 0, 0))
        OPAQUE_BLACK = QColor(0, 0, 0, 255).rgba()
        for y in range(h):
            base = y * w
            for x in range(w):
                if not exterior[base + x]:
                    bg_mask.setPixel(x, y, OPAQUE_BLACK)
        
        # --- Apply semi-transparent black tint via DestinationIn ---
        bg_img = QImage(w, h, QImage.Format.Format_ARGB32)
        bg_img.fill(QColor(0, 0, 0, 120))
        p = QPainter(bg_img)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, bg_mask)
        p.end()
        
        # --- Shrink icon to 95%, center on background ---
        ICON_SCALE = 0.95
        icon_w = max(1, int(w * ICON_SCALE))
        icon_h = max(1, int(h * ICON_SCALE))
        icon_small = img.scaled(icon_w, icon_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        dx = (w - icon_w) // 2
        dy = (h - icon_h) // 2
        
        # --- Final composite: dark bg + 95% icon centered on top ---
        result = QImage(w, h, QImage.Format.Format_ARGB32)
        result.fill(QColor(0, 0, 0, 0))
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawImage(0, 0, bg_img)
        p.drawImage(dx, dy, icon_small)
        p.end()
        
        return QPixmap.fromImage(result)
    
    except Exception as e:
        print(f"[IconBg] Error: {e}")
        return pixmap



# ----------------------------------------------------------
# Extract high-resolution icon from EXE
# ----------------------------------------------------------
def extract_icon_from_exe(exe_path, size=0):
    """Extract the highest resolution icon from an exe file using multiple methods."""
    
    # Use APPDATA_DIR for persistent icon storage
    icons_dir = os.path.join(APPDATA_DIR, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    
    # Generate unique cache key using parent folder + exe name to prevent collision
    # e.g. "HoYoPlay/launcher.exe" vs "Wuthering Waves/launcher.exe" will have different icons
    exe_name = os.path.splitext(os.path.basename(exe_path))[0]
    parent_folder = os.path.basename(os.path.dirname(exe_path))
    # Sanitize folder name for filename (remove invalid chars)
    safe_parent = "".join(c for c in parent_folder if c.isalnum() or c in "._- ")
    # Create unique cache name: ParentFolder_ExeName.png
    if safe_parent and safe_parent.lower() != exe_name.lower():
        cache_name = f"{safe_parent}_{exe_name}"
    else:
        cache_name = exe_name
    icon_path = os.path.join(icons_dir, f"{cache_name}.png")
    
    # Check if path is on a network/shared drive (VirtualBox, UNC, etc.)
    # Network paths often fail with Windows Shell API
    temp_copy = None
    actual_exe_path = exe_path
    
    # Helper to detect special paths that need temp copy
    def needs_temp_copy(path):
        if path.startswith("\\\\"):  # UNC path
            return True
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].upper() + ":"
            try:
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
                # DRIVE_REMOTE = 4 (network), DRIVE_CDROM = 5, DRIVE_RAMDISK = 6
                if drive_type in (4, 5, 6):
                    return True
            except:
                pass
        # VirtualBox/VMware shared folders sometimes appear as special paths
        # Also check for VBOX, VMware, or shared folder patterns
        path_lower = path.lower()
        if any(x in path_lower for x in ['vbox', 'vmware', 'shared', '\\\\vboxsvr', '\\\\vmware-host']):
            return True
        return False
    
    def try_extract(exe_to_use):
        """Try all extraction methods on given exe path."""
        print(f"[Icon] Trying extraction: {exe_to_use}")
        
        # Method 0: Native C++ extension (FASTEST - 10-20x faster)
        # Only use if result is large enough (>= 128px), otherwise try Python methods
        native_icon_result = None
        if NATIVE_CPP_AVAILABLE and get_icon_extractor:
            print(f"[Icon] Method 0: Native C++ extraction...")
            try:
                extractor = get_icon_extractor()
                result = extractor.extract(exe_to_use, size=256)
                if result.success and result.data:
                    # Check if icon is large enough
                    if result.width >= 128 and result.height >= 128:
                        pixmap = result.to_qpixmap()
                        if pixmap and not pixmap.isNull():
                            pixmap.save(icon_path, "PNG")
                            print(f"[Icon] SUCCESS: Native C++ -> {result.width}x{result.height}")
                            return icon_path
                    else:
                        # Save for later fallback if Python methods fail
                        native_icon_result = result
                        print(f"[Icon] Method 0: Icon too small ({result.width}x{result.height}), trying other methods...")
                else:
                    print(f"[Icon] Method 0: Native extraction failed - {result.error if hasattr(result, 'error') else 'unknown'}")
            except Exception as e:
                print(f"[Icon] Method 0 ERROR: {e}")
        
        # Method 1: Try to get Steam library image (high quality artwork)
        print(f"[Icon] Method 1: Steam library image...")
        try:
            steam_icon = try_get_steam_icon(exe_to_use, icon_path)
            if steam_icon:
                print(f"[Icon] SUCCESS: Steam icon -> {steam_icon}")
                return steam_icon
            print("[Icon] Method 1: No Steam icon found")
        except Exception as e:
            print(f"[Icon] Method 1 ERROR: {e}")
        
        # Method 2: Try Windows Shell jumbo icons (256x256)
        print(f"[Icon] Method 2: Windows Shell jumbo icon...")
        try:
            jumbo_icon = try_get_jumbo_icon(exe_to_use, icon_path)
            if jumbo_icon:
                print(f"[Icon] SUCCESS: Jumbo icon -> {jumbo_icon}")
                return jumbo_icon
            print("[Icon] Method 2: No jumbo icon")
        except Exception as e:
            print(f"[Icon] Method 2 ERROR: {e}")
        
        # Method 3: Try icoextract library
        print(f"[Icon] Method 3: icoextract library...")
        try:
            ico_icon = try_icoextract(exe_to_use, icon_path)
            if ico_icon:
                print(f"[Icon] SUCCESS: icoextract -> {ico_icon}")
                return ico_icon
            print("[Icon] Method 3: icoextract failed")
        except Exception as e:
            print(f"[Icon] Method 3 ERROR: {e}")
        
        # Method 4: Fallback to basic Windows API
        print(f"[Icon] Method 4: Basic Windows API fallback...")
        try:
            result = extract_icon_fallback(exe_to_use, icon_path)
            if result:
                print(f"[Icon] SUCCESS: Fallback -> {result}")
                return result
            else:
                print("[Icon] Method 4: Fallback returned None")
        except Exception as e:
            print(f"[Icon] Method 4 ERROR: {e}")
        
        # Method 5: Use small native C++ icon as last resort (better than nothing)
        if native_icon_result and native_icon_result.success and native_icon_result.data:
            print(f"[Icon] Method 5: Using small native icon ({native_icon_result.width}x{native_icon_result.height}) as last resort...")
            try:
                pixmap = native_icon_result.to_qpixmap()
                if pixmap and not pixmap.isNull():
                    pixmap.save(icon_path, "PNG")
                    print(f"[Icon] SUCCESS: Small native C++ -> {native_icon_result.width}x{native_icon_result.height}")
                    return icon_path
            except Exception as e:
                print(f"[Icon] Method 5 ERROR: {e}")
        
        return None
    
    try:
        # First attempt: try direct extraction
        result = try_extract(exe_path)
        if result:
            return result
        
        # If direct extraction failed and path might be problematic, try temp copy
        if needs_temp_copy(exe_path) or True:  # Always try temp copy as fallback
            if os.path.exists(exe_path):
                import tempfile
                import shutil
                temp_dir = tempfile.mkdtemp(prefix="helxaid_icon_")
                temp_copy = os.path.join(temp_dir, os.path.basename(exe_path))
                print(f"[Icon] Trying temp copy fallback: {exe_path}")
                try:
                    shutil.copy2(exe_path, temp_copy)
                    result = try_extract(temp_copy)
                    if result:
                        return result
                except Exception as e:
                    print(f"[Icon] Temp copy failed: {e}")
        
        return None
    finally:
        # Cleanup temp copy and folder
        if temp_copy:
            try:
                temp_dir = os.path.dirname(temp_copy)
                import shutil
                if os.path.exists(temp_dir) and temp_dir.startswith(tempfile.gettempdir()):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    print(f"[Icon] Cleaned up temp folder: {temp_dir}")
            except Exception as e:
                print(f"[Icon] Cleanup failed: {e}")

def try_get_steam_icon(exe_path, icon_path):
    """Try to find Steam library artwork for the game."""
    try:
        # Check if this is a Steam game
        if "steamapps" not in exe_path.lower():
            return None
        
        # Find the game's folder name from the path
        # Steam games are in steamapps/common/GameName/
        parts = exe_path.replace("\\", "/").split("/")
        try:
            common_idx = [p.lower() for p in parts].index("common")
            game_folder = parts[common_idx + 1]
        except (ValueError, IndexError):
            return None
        
        # Main Steam installation (where appcache is stored)
        steam_main = "C:/Program Files (x86)/Steam"
        
        # Find steamapps that contains this game
        steamapps_idx = exe_path.lower().find("steamapps")
        if steamapps_idx > 0:
            library_root = exe_path[:steamapps_idx].rstrip("\\/")
            steamapps = os.path.join(library_root, "steamapps")
        else:
            steamapps = os.path.join(steam_main, "steamapps")
        
        if not os.path.exists(steamapps):
            return None
        
        # Look for appmanifest files to get appid
        for f in os.listdir(steamapps):
            if f.startswith("appmanifest_") and f.endswith(".acf"):
                manifest_path = os.path.join(steamapps, f)
                try:
                    with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as mf:
                        content = mf.read()
                        if f'"{game_folder}"' in content or game_folder.lower() in content.lower():
                            # Found the manifest, extract appid
                            appid = f.replace("appmanifest_", "").replace(".acf", "")
                            print(f"Found Steam appid: {appid} for {game_folder}")
                            
                            # Look for library artwork in Steam's main appcache
                            # Structure: appcache/librarycache/{appid}/library_600x900.jpg
                            cache_paths = [
                                os.path.join(steam_main, "appcache", "librarycache", appid, "library_600x900.jpg"),
                                os.path.join(steam_main, "appcache", "librarycache", appid, "library_hero.jpg"),
                                os.path.join(steam_main, "appcache", "librarycache", appid, "logo.png"),
                                os.path.join(steam_main, "appcache", "librarycache", appid, "icon.jpg"),
                            ]
                            
                            for cache_path in cache_paths:
                                if os.path.exists(cache_path):
                                    img = Image.open(cache_path)
                                    img = img.convert('RGBA')
                                    img.save(icon_path, 'PNG')
                                    print(f"Steam artwork: {img.width}x{img.height} from {cache_path}")
                                    return icon_path
                            
                            print(f"No Steam cache found for appid {appid}")
                except Exception as e:
                    continue
        
        return None
    except Exception as e:
        print(f"Steam icon search failed: {e}")
        return None

def try_get_jumbo_icon(exe_path, icon_path):
    """Try to get Windows Shell jumbo icon (256x256)."""
    _ensure_win32_loaded()
    if not WINDOWS_API_AVAILABLE:
        return None
    
    try:
        import ctypes
        from ctypes import wintypes
        
        # Windows Shell API constants
        SHGFI_SYSICONINDEX = 0x4000
        SHGFI_ICON = 0x100
        SHGFI_LARGEICON = 0x0
        SHIL_JUMBO = 4  # 256x256 icons
        SHIL_EXTRALARGE = 2  # 48x48 icons
        
        # SHFILEINFO structure
        class SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HANDLE),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)
            ]
        
        shell32 = ctypes.windll.shell32
        
        # Get icon index
        shinfo = SHFILEINFO()
        result = shell32.SHGetFileInfoW(
            exe_path, 0, ctypes.byref(shinfo),
            ctypes.sizeof(shinfo),
            SHGFI_SYSICONINDEX
        )
        
        if not result:
            return None
        
        # Try to get IImageList for jumbo icons
        IID_IImageList = ctypes.c_char * 16
        iid = IID_IImageList(b'\x2c\x73\xda\x46\x99\x4d\x00\x00\x00\x00\x00\x00\xc0\x00\x00\x46')
        
        try:
            # SHGetImageList
            image_list = ctypes.c_void_p()
            hr = shell32.SHGetImageList(SHIL_JUMBO, iid, ctypes.byref(image_list))
            
            if hr == 0 and image_list:
                # Got jumbo image list, extract icon
                comctl32 = ctypes.windll.comctl32
                hicon = comctl32.ImageList_GetIcon(image_list, shinfo.iIcon, 0)
                
                if hicon:
                    # Convert to image
                    icon_info = win32gui.GetIconInfo(hicon)
                    hbm = icon_info[3] or icon_info[4]
                    
                    if hbm:
                        bmp = win32ui.CreateBitmapFromHandle(hbm)
                        bmp_info = bmp.GetInfo()
                        
                        width = bmp_info['bmWidth']
                        height = bmp_info['bmHeight']
                        
                        if width >= 48:  # Only use if reasonably large
                            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                            hbmp = win32ui.CreateBitmap()
                            hbmp.CreateCompatibleBitmap(hdc, width, height)
                            hdc_obj = hdc.CreateCompatibleDC()
                            hdc_obj.SelectObject(hbmp)
                            
                            win32gui.DrawIconEx(
                                hdc_obj.GetHandleOutput(),
                                0, 0, hicon,
                                width, height,
                                0, None, win32con.DI_NORMAL
                            )
                            
                            bmp_str = hbmp.GetBitmapBits(True)
                            img = Image.frombuffer(
                                'RGBA', (width, height),
                                bmp_str, 'raw', 'BGRA', 0, 1
                            )
                            
                            img.save(icon_path, 'PNG')
                            print(f"Jumbo icon: {width}x{height}")
                            
                            win32gui.DeleteObject(hbmp.GetHandle())
                            hdc.DeleteDC()
                            win32gui.DestroyIcon(hicon)
                            return icon_path
                    
                    win32gui.DestroyIcon(hicon)
        except Exception as e:
            print(f"Jumbo icon failed: {e}")
        
        return None
    except Exception as e:
        print(f"Shell icon failed: {e}")
        return None

def try_icoextract(exe_path, icon_path):
    """Try icoextract library."""
    try:
        from icoextract import IconExtractor
        import tempfile
        
        extractor = IconExtractor(exe_path)
        
        # Create temp file and export icon
        with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as tmp:
            tmp_path = tmp.name
        
        extractor.export_icon(tmp_path, num=0)
        
        try:
            # PIL opens ICO at the largest available size by default
            ico = Image.open(tmp_path)
            img = ico.convert('RGBA')
            
            # Save as PNG
            img.save(icon_path, 'PNG')
            print(f"icoextract: {img.width}x{img.height}")
            return icon_path
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        print(f"icoextract failed: {e}")
        return None

def extract_icon_fallback(exe_path, icon_path):
    """Fallback icon extraction using Windows API."""
    # Ensure win32 modules are loaded
    _ensure_win32_loaded()
    
    if not WINDOWS_API_AVAILABLE:
        print("Windows API not available - cannot extract icon")
        return None

    try:
        # Get the number of icons in the file first
        num_icons = win32gui.ExtractIconEx(exe_path, -1)
        if not num_icons:
            print(f"No icons found in {exe_path}")
            return None
        
        # Extract all icons (large and small)
        ico_x = win32gui.ExtractIconEx(exe_path, 0, num_icons)
        if not ico_x or (not ico_x[0] and not ico_x[1]):
            print(f"No icons found in {exe_path}")
            return None

        # Find the highest quality icon
        best_icon = None
        best_size = 0
        best_icon_info = None
        all_icons = list(ico_x[0] or []) + list(ico_x[1] or [])
        
        try:
            for hicon in all_icons:
                try:
                    icon_info = win32gui.GetIconInfo(hicon)
                    hbm = icon_info[3] or icon_info[4]
                    if not hbm:
                        win32gui.DestroyIcon(hicon)
                        continue
                        
                    bmp = win32ui.CreateBitmapFromHandle(hbm)
                    bmp_info = bmp.GetInfo()
                    current_size = max(bmp_info['bmWidth'], bmp_info['bmHeight'])
                    
                    if current_size > best_size:
                        if best_icon is not None:
                            win32gui.DestroyIcon(best_icon)
                            if best_icon_info:
                                if best_icon_info[3]: win32gui.DeleteObject(best_icon_info[3])
                                if best_icon_info[4]: win32gui.DeleteObject(best_icon_info[4])
                        
                        best_size = current_size
                        best_icon = hicon
                        best_icon_info = icon_info
                    else:
                        win32gui.DestroyIcon(hicon)
                        if icon_info[3]: win32gui.DeleteObject(icon_info[3])
                        if icon_info[4]: win32gui.DeleteObject(icon_info[4])
                            
                except Exception as e:
                    print(f"Error processing icon: {e}")
                    continue
                    
            if not best_icon:
                return None
                
            hbm = best_icon_info[3] or best_icon_info[4]
            if not hbm:
                return None
                
            bmp = win32ui.CreateBitmapFromHandle(hbm)
            bmp_info = bmp.GetInfo()
            
            target_size = max(bmp_info['bmWidth'], bmp_info['bmHeight'])
            
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, target_size, target_size)
            hdc_obj = hdc.CreateCompatibleDC()
            hdc_obj.SelectObject(hbmp)
            
            hdc_obj.FillRect((0, 0, target_size, target_size), win32ui.CreateBrush(win32con.BS_NULL, 0, 0))
            
            win32gui.DrawIconEx(
                hdc_obj.GetHandleOutput(),
                0, 0, best_icon,
                target_size, target_size,
                0, None, win32con.DI_NORMAL
            )
            
            bmp_info = hbmp.GetInfo()
            bmp_str = hbmp.GetBitmapBits(True)
            
            img = Image.frombuffer(
                'RGBA',
                (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_str, 'raw', 'BGRA', 0, 1
            )
            
            win32gui.DeleteObject(hbmp.GetHandle())
            hdc.DeleteDC()
            
            img.save(icon_path, 'PNG')
            print(f"Fallback: extracted {img.width}x{img.height} icon to {icon_path}")
            return icon_path
            
        finally:
            if best_icon is not None:
                win32gui.DestroyIcon(best_icon)
            if best_icon_info:
                if best_icon_info[3]: win32gui.DeleteObject(best_icon_info[3])
                if best_icon_info[4]: win32gui.DeleteObject(best_icon_info[4])
            for hicon in all_icons:
                try:
                    if hicon != best_icon:
                        win32gui.DestroyIcon(hicon)
                except:
                    pass
                    
    except Exception as e:
        print(f"Error extracting icon from {exe_path}: {str(e)}")
        return None

# ----------------------------------------------------------
# ----------------------------------------------------------
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")

# Well-known game platform launcher executables (lowercase basenames).
# If a library entry's 'exe' field matches one of these, the process is a
# platform launcher rather than the game itself.  Used by the background
# detection system to distinguish "Launcher" from "Playing" status.
KNOWN_LAUNCHERS = {
    # Valve / Steam
    "steam.exe", "steamwebhelper.exe",
    # Epic Games
    "epicgameslauncher.exe", "epicwebhelper.exe",
    # Riot Games
    "riotclientservices.exe", "riotclientux.exe", "riotclientcrashhandler.exe",
    # miHoYo / HoYoverse / Kuro
    "hoyoplay.exe", "launcher.exe", "kurolauncher.exe",
    # GOG Galaxy
    "galaxyclient.exe", "galaxyclienthelper.exe",
    # EA
    "ea.exe", "eadesktop.exe", "origin.exe", "easteamproxy.exe",
    # Ubisoft
    "ubisoftconnect.exe", "ubisoftgamelauncher.exe", "upc.exe",
    # Bethesda
    "bethesdalauncher.exe",
    # Battle.net (Blizzard)
    "battle.net.exe", "agent.exe",
    # Xbox / Microsoft Store
    "xboxapp.exe", "gamingservices.exe",
    # Amazon Games
    "amazon games.exe",
    # itch.io
    "itch.exe",
    # TLauncher (Minecraft)
    "tlauncher.exe",
    # Overwolf
    "overwolf.exe",
}

# Generic Unreal Engine process names that many games share.
# If a library entry uses one of these, we fall back to directory-name
# matching to distinguish which game it is.
GENERIC_UE_EXES = {
    "client-win64-shipping.exe",
    "unrealengine.exe",
    "gameoverlayui.exe",
    "crashreportclient.exe",
}

# Window-title keywords that indicate a launcher / updater rather than
# the actual game being played.  Case-insensitive comparison.
LAUNCHER_TITLE_KEYWORDS = {
    "launcher", "updater", "patcher", "installer", "setup",
    "update manager", "download", "login", "sign in",
    "riot client", "hoyoplay", "kuro launcher",
}

# Windows system/service executables that must NEVER be treated as game processes.
# If these end up in a game's 'game_exe' field (e.g. from bad auto-detection),
# they will be silently ignored to prevent constant false-positive detection.
SYSTEM_PROCESS_BLACKLIST = {
    # Core Windows services and hosts
    "svchost.exe", "csrss.exe", "smss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "lsaiso.exe", "spoolsv.exe",
    "conhost.exe", "sihost.exe", "taskhostw.exe", "dwm.exe",
    "ctfmon.exe", "fontdrvhost.exe", "dllhost.exe", "wmiprvse.exe",
    # Windows Update / Telemetry / Servicing
    "dismhost.exe", "compattelrunner.exe", "comppkgsrv.exe",
    "sihclient.exe", "musnotification.exe", "tiworker.exe",
    "wuauclt.exe", "trustedinstaller.exe", "msiexec.exe",
    # Shell / Explorer
    "explorer.exe", "shellexperiencehost.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "searchui.exe", "cortana.exe",
    "runtimebroker.exe", "applicationframehost.exe",
    # Common runtime hosts (too generic to be a game)
    "java.exe", "javaw.exe", "python.exe", "pythonw.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
    "rundll32.exe", "regsvr32.exe", "mmc.exe", "notepad.exe",
    # Network / Security
    "lsm.exe", "wlanext.exe", "dashost.exe",
    # Kuro launcher helpers (not the game itself)
    "krinstallexternal.exe",
}

DEFAULT_SETTINGS = {
    "background_image": "",
    "background_mode": "fill",  # fill, fit, stretch, tile, center, span
    "auto_palette": True,
    "show_hidden_games": False,
    "watch_folders": [],
    "icon_scale": 1,
    "theme_colors": {
        "primary": "#FF5B06",
        "secondary": "#FDA903", 
        "background_dark": "#010101",
        "background_light": "#1D1D1C",
        "text": "#e0e0e0"
    },
    "google_api_key": "",
    "google_cx": "",
    "resizable_window": True,
    "window_fullscreen": False,
    "window_opacity": 1.0,
    "window_geometry": None,
    "start_minimised": False,
    "minimize_to_tray": True,
    "confirm_on_exit": True
}

def load_settings():
    """Load app settings from settings.json"""
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
                # Merge with defaults to add any new keys
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = value
                return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save app settings to settings.json"""
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

def _exclude_from_rtss():
    """Exclude this process from RivaTuner Statistics Server / MSI Afterburner OSD.
    
    RTSS (used by MSI Afterburner) hooks into processes that use Direct3D/OpenGL
    and renders an overlay showing FPS, CPU temp, GPU temp, etc. This is unwanted
    in a media player/launcher context.
    
    RTSS supports per-application opt-out via profile files stored in its Profiles
    directory. Writing a profile with EnableHooking=0 tells RTSS not to inject
    its D3D hook DLL into this process.
    
    Steps:
    1. Find RTSS installation path from Windows registry
    2. Determine our executable filename (works for both dev and bundled exe)
    3. Write a profile file disabling hooking for this exe
    4. Signal RTSS to reload its profiles via SendMessage to its hidden window
    
    If RTSS is not installed, this function does nothing silently.
    """
    try:
        import winreg
        
        # Find RTSS installation path from registry
        # RTSS registers itself at this key on installation
        rtss_path = None
        registry_keys = [
            r"SOFTWARE\WOW6432Node\Unwinder\RTSS",   # 64-bit Windows (RTSS is 32-bit)
            r"SOFTWARE\Unwinder\RTSS",                # 32-bit Windows fallback
        ]
        
        for reg_key in registry_keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
                    rtss_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    break
            except (FileNotFoundError, OSError):
                continue
        
        if not rtss_path:
            # RTSS not installed - nothing to do
            return
        
        # Profiles directory where per-app settings are stored
        profiles_dir = os.path.join(rtss_path, "Profiles")
        if not os.path.isdir(profiles_dir):
            return
        
        # Determine our executable name.
        # For bundled PyInstaller exe: e.g. "HELXAID.exe"
        # For development (python.exe): e.g. "python.exe"
        exe_name = os.path.basename(sys.executable)
        if hasattr(sys, '_MEIPASS'):
            # Running as PyInstaller bundle - get the actual exe name
            exe_name = os.path.basename(sys.argv[0])
            if not exe_name.lower().endswith('.exe'):
                exe_name += '.exe'
        
        profile_path = os.path.join(profiles_dir, exe_name)
        
        # RTSS profile format (INI file, no section headers for top-level keys).
        # EnableHooking=0: Do not inject D3D/OpenGL hook DLL into this process.
        # DetectionLevel=0: Corresponds to "None" in RTSS app detection settings.
        profile_content = (
            "[Hooking]\r\n"
            "EnableHooking=0\r\n"
            "DetectionLevel=0\r\n"
        )
        
        # Always (re)write the profile so that a fresh reload signal carries
        # current content. The file is tiny so the overhead is negligible.
        try:
            with open(profile_path, 'w') as f:
                f.write(profile_content)
            print(f"[RTSS] Wrote exclusion profile: {profile_path}")
        except OSError as e:
            print(f"[RTSS] Could not write profile file: {e}")
        
        # Signal RTSS to reload its profiles immediately.
        # WM_USER+100 (0x464) is the documented RTSS profile-reload command.
        # Different RTSS versions use different window class names — enumerate
        # all known classes so we hit the right one regardless of version.
        try:
            WM_RTSS_RELOAD = 0x464  # WM_USER + 100
            user32 = ctypes.windll.user32

            # Window class names used by RTSS across versions
            rtss_classes = ["RTSS", "RTSSWnd", "RivaTuner Statistics Server"]
            reloaded = False

            for cls in rtss_classes:
                hwnd = user32.FindWindowW(cls, None)
                if hwnd:
                    # SendMessageW blocks until RTSS processes the reload —
                    # this guarantees the profile is applied before we return.
                    user32.SendMessageW(hwnd, WM_RTSS_RELOAD, 0, 0)
                    print(f"[RTSS] Signaled profile reload to class '{cls}' (hwnd={hwnd})")
                    reloaded = True

            if not reloaded:
                print("[RTSS] RTSS not running — profile queued for next start")
        except Exception:
            pass  # Non-critical
        
        print(f"[RTSS] Process excluded from D3D overlay: {exe_name}")
        
    except ImportError:
        pass  # winreg not available (non-Windows) - silently skip
    except Exception as e:
        # Non-critical: RTSS exclusion failing should not affect app startup
        print(f"[RTSS] Could not write exclusion profile: {e}")




# Windows Startup helpers - uses Registry for proper Task Manager display
STARTUP_APP_NAME = "HELXAID"
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def is_startup_enabled():
    """Check if the launcher is set to run on Windows startup via Registry."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, STARTUP_APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception as e:
        print(f"Error checking startup registry: {e}")
        return False

def set_startup_enabled(enabled):
    """Enable or disable the launcher running on Windows startup via Registry."""
    try:
        import winreg
        
        if enabled:
            # Get the executable path
            if getattr(sys, 'frozen', False):
                # Running as compiled .exe
                exe_path = sys.executable
            else:
                # Running as script
                python_exe = sys.executable
                script_path = os.path.abspath(__file__)
                exe_path = f'"{python_exe}" "{script_path}"'
            
            # Open registry key for writing
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            print(f"[Startup] Registry entry created: {STARTUP_APP_NAME} -> {exe_path}")
            
            # Also remove old shortcut if exists
            _cleanup_old_shortcut()
        else:
            # Remove registry entry
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, STARTUP_APP_NAME)
                print(f"[Startup] Registry entry removed: {STARTUP_APP_NAME}")
            except FileNotFoundError:
                pass  # Already doesn't exist
            winreg.CloseKey(key)
            
            # Also remove old shortcut if exists
            _cleanup_old_shortcut()
    except Exception as e:
        print(f"Error setting startup registry: {e}")

def _cleanup_old_shortcut():
    """Remove old startup shortcut if it exists (migration from shortcut to registry)."""
    try:
        startup_folder = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        old_shortcut = os.path.join(startup_folder, f"{STARTUP_APP_NAME}.lnk")
        if os.path.exists(old_shortcut):
            os.remove(old_shortcut)
            print(f"[Startup] Cleaned up old shortcut: {old_shortcut}")
    except Exception as e:
        print(f"Error cleaning up old shortcut: {e}")

def load_json():
    print(f"[Config] Loading from: {JSON_PATH}")
    # Create empty config.json if it doesn't exist (first launch)
    if not os.path.exists(JSON_PATH):
        print(f"[Config] File not found, creating new empty config")
        try:
            with open(JSON_PATH, "w") as f:
                json.dump([], f)
            return []
        except Exception as e:
            print(f"Error creating config.json: {e}")
            return []
    
    try:
        with open(JSON_PATH, "r") as f:
            data = json.load(f)
            # Check if data is a list (direct array of games) or a dict with "games" key
            if isinstance(data, list):
                games = data
            else:
                games = data.get("games", [])
            
            # Migrate: rename 'description' to 'notes' if needed
            for game in games:
                if "description" in game and "notes" not in game:
                    game["notes"] = game.pop("description")
                # Ensure new fields exist with defaults
                game.setdefault("notes", "")
                game.setdefault("category", "")
                game.setdefault("tags", [])
                game.setdefault("favorite", False)
                game.setdefault("hidden", False)
                game.setdefault("launch_options", "")
                game.setdefault("play_time_seconds", 0)
                game.setdefault("last_played", "")
                game.setdefault("first_played", "")  # Track when game was first played
                game.setdefault("date_added", "")
                game.setdefault("session_history", [])  # List of {duration, date} for avg/longest
                game.setdefault("genre", "")  # User-editable genre
                game.setdefault("developer", "")  # User-editable developer
            
            return games
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return []


def validate_and_fix_corrupt_icons(games):
    """Detect corrupt icons and attempt to reimport from .exe.
    
    A corrupt icon is detected by:
    - File doesn't exist
    - File size < 500 bytes (too small for valid PNG)
    - File cannot be opened as image
    
    Returns: Number of icons fixed
    """
    from PySide6.QtGui import QImage
    
    fixed_count = 0
    
    for game in games:
        icon_path = game.get("icon", "")
        exe_path = game.get("exe", "")
        
        if not icon_path:
            continue
        
        needs_fix = False
        reason = ""
        
        # Check 1: File exists
        if not os.path.exists(icon_path):
            needs_fix = True
            reason = "file not found"
        else:
            # Check 2: File size (< 500 bytes is suspicious)
            try:
                file_size = os.path.getsize(icon_path)
                if file_size < 500:
                    needs_fix = True
                    reason = f"file too small ({file_size} bytes)"
            except:
                needs_fix = True
                reason = "cannot read file size"
            
            # Check 3: Can be loaded as image
            if not needs_fix:
                try:
                    img = QImage(icon_path)
                    if img.isNull() or img.width() < 16 or img.height() < 16:
                        needs_fix = True
                        reason = "invalid or too small image"
                except:
                    needs_fix = True
                    reason = "cannot load as image"
        
        if needs_fix and exe_path and os.path.exists(exe_path):
            print(f"[IconFix] Corrupt icon for '{game.get('name', 'Unknown')}': {reason}")
            print(f"[IconFix] Attempting to reimport from: {exe_path}")
            
            # Delete corrupt file first
            try:
                if os.path.exists(icon_path):
                    os.remove(icon_path)
            except:
                pass
            
            # Try to extract new icon
            try:
                new_icon = extract_icon_from_exe(exe_path)
                if new_icon and os.path.exists(new_icon):
                    game["icon"] = new_icon
                    fixed_count += 1
                    print(f"[IconFix] SUCCESS: New icon saved to {new_icon}")
                else:
                    print(f"[IconFix] FAILED: Could not extract icon from exe")
            except Exception as e:
                print(f"[IconFix] ERROR: {e}")
    
    if fixed_count > 0:
        print(f"[IconFix] Fixed {fixed_count} corrupt icon(s)")
        # Save the updated game data
        save_json(games)
    
    return fixed_count


def save_json(data, force_save=False):
    print(f"[Config] Saving to: {JSON_PATH}")
    
    # Guard: Don't overwrite existing games with empty data (prevent accidental data loss)
    # Use force_save=True when user intentionally deletes all games
    if len(data) == 0 and os.path.exists(JSON_PATH) and not force_save:
        try:
            with open(JSON_PATH, "r") as f:
                existing = json.load(f)
                if isinstance(existing, list) and len(existing) > 0:
                    print(f"[Config] WARNING: Blocking save of 0 games (would overwrite {len(existing)} games)")
                    print(f"[Config] Use force_save=True if intentional deletion")
                    return  # Don't overwrite!
        except:
            pass
    
    if force_save and len(data) == 0:
        print(f"[Config] Force saving 0 games (user deleted all games)")
    
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=4)
    print(f"[Config] Saved {len(data)} games")


# ----------------------------------------------------------
# Custom FadeToolTip class
# ----------------------------------------------------------
class FadeToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacityEffect)
        self.opacityEffect.setOpacity(0)
        self.animation = QPropertyAnimation(self.opacityEffect, b'opacity')
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

    def show(self, text, pos):
        self.setText(text)
        self.move(pos)
        self.animation.start()
        super().show()

    def hide(self):
        self.animation.setDirection(QPropertyAnimation.Backward)
        self.animation.start()
        QTimer.singleShot(200, super().hide)


# ----------------------------------------------------------
# Animated Game Button for hover effects
# ----------------------------------------------------------
class AnimatedGameButton(QPushButton):
    # Signal emitted on double-click for launching games
    doubleClicked = Signal()
    
    # Class-level reference to currently selected button
    _selected_button = None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 1.0
        self._glow = 0.0
        self.base_size = None
        self._original_style = ""
        self._is_selected = False
    
    def _is_valid(self):
        """Check if this Qt object is still valid (not deleted)."""
        try:
            from shiboken6 import isValid
            return isValid(self)
        except:
            return True  # Assume valid if we can't check
    
    def setSelected(self, selected):
        """Set the selected state of the button."""
        # Safety check: don't operate on deleted objects
        if not self._is_valid():
            return
            
        self._is_selected = selected
        if selected:
            # Deselect previous button (with safety check for deleted objects)
            prev_btn = AnimatedGameButton._selected_button
            if prev_btn and prev_btn != self:
                AnimatedGameButton._selected_button = None  # Clear first to prevent recursion issues
                try:
                    if prev_btn._is_valid():
                        prev_btn._is_selected = False  # Direct set to avoid recursion
                        prev_btn.setStyleSheet("")
                except RuntimeError:
                    pass  # Button was deleted
                    
            AnimatedGameButton._selected_button = self
            # Selected: stronger black-to-orange gradient
            self.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 0, 0, 0.55), stop:1 rgba(255, 91, 6, 0.70));
                }
            """)
        else:
            if AnimatedGameButton._selected_button == self:
                AnimatedGameButton._selected_button = None
            self.setStyleSheet("")
    
    # Simple hover animation using opacity effect instead of scale
    # (scale animation causes layout issues)
    def enterEvent(self, event):
        # Black-to-orange gradient on hover (top=black, bottom=orange)
        if not self._is_selected:
            self.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 0, 0, 0.45), stop:1 rgba(255, 91, 6, 0.55));
                }
            """)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        # Reset to default style or bg image style (unless selected)
        if not self._is_selected:
            # Restore background image style if set, otherwise clear
            if hasattr(self, '_bg_image_style') and self._bg_image_style:
                self.setStyleSheet(self._bg_image_style)
            else:
                self.setStyleSheet("")
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Select this button on single-click."""
        if event.button() == Qt.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Emit doubleClicked signal on double-click."""
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)



# ----------------------------------------------------------
# Custom Slider for Click-to-Seek
# ----------------------------------------------------------
class SeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.pos().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            event.accept()
        super().mousePressEvent(event)

# ----------------------------------------------------------
# Audio Player Sidebar Class (Merged from player.py)
# ----------------------------------------------------------
class AudioPlayerSidebar(QWidget):
    """
    Compact vertical audio player sidebar (80px width).
    Features: Play/Pause, Next/Prev, Volume, Progress, Playlist.
    """
    
    # Signals
    playbackStarted = Signal()
    playbackStopped = Signal()
    trackChanged = Signal(str)
    playlistChanged = Signal()
    coverChanged = Signal(QPixmap)
    
    def __init__(self, settings_path: str = None, parent=None):
        # Lazy import Qt Multimedia to reduce startup RAM
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QMediaMetaData
        
        super().__init__(parent)
        self.setObjectName("audioPlayerSidebar")
        self.setMinimumHeight(90)
        
        # Settings path for saving last track
        self.settings_path = settings_path
        
        # Initialize media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Default volume
        self.audio_output.setVolume(1.0)
        
        # Playlist
        self.playlist = []
        self.current_index = 0
        self.is_playing = False

        self.loop_mode = 1  # 0: Off, 1: Loop All, 2: Loop One
        self.shuffle_enabled = False
        self.stereo_mode = 0
        self.is_seeking = False
        
        # Setup UI
        self._setup_ui()
        
        # Connect signals
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)
        self.player.metaDataChanged.connect(self._on_metadata_changed)
        
        # Load last track from settings
        self._load_last_track()
    
    def _setup_ui(self):
        """Setup the vertical sidebar UI."""
        # Enable background painting for semi-transparent effect
        self.setAutoFillBackground(True)
        
        # Semi-transparent background for glassmorphism effect
        self.setStyleSheet("""
            QWidget#audioPlayerSidebar {
                background-color: rgba(30, 30, 30, 190);
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)

        layout.setContentsMargins(20, 4, 20, 8)
        layout.setSpacing(2)

        # Top row: time labels + progress slider (Spotify-style)
        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(8)

        self.current_time_label = QLabel("0:00")
        self.current_time_label.setFixedWidth(40)
        self.current_time_label.setAlignment(Qt.AlignCenter)
        self.current_time_label.setStyleSheet("color: #b3b3b3; font-size: 9px; background: transparent;")

        self.progress_slider = SeekSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderMoved.connect(self._seek)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 3px;
                background: #404040;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #FFFFFF;
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: #404040;
                border-radius: 2px;
            }
        """)

        self.total_time_label = QLabel("0:00")
        self.total_time_label.setFixedWidth(40)
        self.total_time_label.setAlignment(Qt.AlignCenter)
        self.total_time_label.setStyleSheet("color: #b3b3b3; font-size: 9px; background: transparent;")

        time_row.addWidget(self.current_time_label)
        time_row.addWidget(self.progress_slider, 1)
        time_row.addWidget(self.total_time_label)

        layout.addLayout(time_row)

        # Bottom row: left (track info), center (controls), right (volume/folder)
        # Use a 3-column grid so the center column is always at the true center.
        bar_row = QGridLayout()
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setHorizontalSpacing(16)
        bar_row.setVerticalSpacing(0)

        # Left section: cover art + track info
        left_box = QHBoxLayout()
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(8)

        self.cover_art = QLabel()
        self.cover_art.setFixedSize(40, 40)
        self.cover_art.setAlignment(Qt.AlignCenter)
        self.cover_art.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FF5B06, stop:1 #FDA903);
            }
        """)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.track_name_label = QLabel("No track")
        self.track_name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.track_name_label.setWordWrap(True)
        self.track_name_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #FFFFFF;
                background: transparent;
            }
        """)

        self.track_label = QLabel("Local file")
        self.track_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.track_label.setStyleSheet("""
            QLabel {
                color: #b3b3b3;
                font-size: 10px;
                background: transparent;
            }
        """)

        text_col.addWidget(self.track_name_label)
        text_col.addWidget(self.track_label)

        left_box.addWidget(self.cover_art)
        left_box.addLayout(text_col)

        # Left section in column 0
        bar_row.addLayout(left_box, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # Center section: playback controls (column 1)
        center_box = QHBoxLayout()
        center_box.setContentsMargins(0, 0, 0, 0)
        center_box.setSpacing(16)

        # Left spacer so play button can sit in the true center of this region
        center_box.addStretch(1)

        # Shuffle button (icon-only, no border)
        self.shuffle_btn = self._create_button("", "Toggle Shuffle", size=22)
        shuffle_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "shuffle-icon.png")
        if os.path.exists(shuffle_icon_path):
            self.shuffle_btn.setIcon(QIcon(shuffle_icon_path))
            self.shuffle_btn.setIconSize(QSize(32, 32))
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        self._update_shuffle_button()
        center_box.addWidget(self.shuffle_btn, 0, Qt.AlignVCenter)

        # Previous button (icon-only)
        self.prev_btn = self._create_button("", "Previous track", size=24)
        prev_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "previous-button-icon.png")
        if os.path.exists(prev_icon_path):
            self.prev_btn.setIcon(QIcon(prev_icon_path))
            self.prev_btn.setIconSize(QSize(24, 24))
        self.prev_btn.clicked.connect(self.prev_track)
        center_box.addWidget(self.prev_btn, 0, Qt.AlignVCenter)

        # Play / Pause button (icon-only, swaps icon with playback state)
        self.play_btn = self._create_button("", "Play/Pause", size=32)
        play_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "play-button-icon.png")
        pause_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "pause-button-icon.png")
        self.play_icon = QIcon(play_icon_path) if os.path.exists(play_icon_path) else QIcon()
        self.pause_icon = QIcon(pause_icon_path) if os.path.exists(pause_icon_path) else QIcon()
        if not self.play_icon.isNull():
            self.play_btn.setIcon(self.play_icon)
            self.play_btn.setIconSize(QSize(48, 48))
        self.play_btn.clicked.connect(self.toggle_play)
        center_box.addWidget(self.play_btn, 0, Qt.AlignVCenter)

        # Next button (icon-only)
        self.next_btn = self._create_button("", "Next track", size=24)
        next_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "forward-button-icon.png")
        if os.path.exists(next_icon_path):
            self.next_btn.setIcon(QIcon(next_icon_path))
            self.next_btn.setIconSize(QSize(24, 24))
        self.next_btn.clicked.connect(self.next_track)
        center_box.addWidget(self.next_btn, 0, Qt.AlignVCenter)

        # Loop button (icon-only)
        self.loop_btn = self._create_button("", "Toggle loop", size=22)
        
        loop_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "loop-button-icon.png")
        loop_one_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "loop-one-button-icon.png")
        
        self.loop_icon_all = QIcon(loop_icon_path) if os.path.exists(loop_icon_path) else QIcon()
        self.loop_icon_one = QIcon(loop_one_icon_path) if os.path.exists(loop_one_icon_path) else QIcon()
        
        if not self.loop_icon_all.isNull():
            self.loop_btn.setIcon(self.loop_icon_all)
            self.loop_btn.setIconSize(QSize(32, 32))
            
        self.loop_btn.clicked.connect(self.toggle_loop)
        self._update_loop_button()
        center_box.addWidget(self.loop_btn, 0, Qt.AlignVCenter)
        
        # Right spacer to balance the left spacer
        center_box.addStretch(1)

        # Center section (controls) in middle column
        bar_row.addLayout(center_box, 0, 1, Qt.AlignHCenter | Qt.AlignVCenter)

        # Right section: volume + open-folder (column 2)
        right_box = QHBoxLayout()
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(8)

        # Inner layout so speaker icon and slider sit very close together
        volume_box = QHBoxLayout()
        # Slight negative left margin pulls the slider under the icon a bit
        volume_box.setContentsMargins(-4, 0, 0, 0)
        volume_box.setSpacing(0)

        vol_label = QLabel()
        vol_label.setFixedSize(32, 32)
        vol_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        vol_label.setContentsMargins(0, 0, 0, 0)
        vol_label.setMargin(0)
        speaker_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "speaker-icon.png")
        if os.path.exists(speaker_icon_path):
            speaker_pix = QPixmap(speaker_icon_path)
            if not speaker_pix.isNull():
                # Trim a few pixels from the right to remove internal padding in the PNG
                if speaker_pix.width() > 4:
                    speaker_pix = speaker_pix.copy(0, 0, speaker_pix.width() - 4, speaker_pix.height())
                vol_label.setPixmap(speaker_pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 125)  # Support up to 125% volume boost
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setStyleSheet("""
            QSlider {
                background: transparent;
            }
            QSlider::groove:horizontal {
                height: 3px;
                background: rgba(64, 64, 64, 100);
                border-radius: 2px;
                margin: 0px;  /* make the track start at the very left edge */
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #FFFFFF;
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: rgba(64, 64, 64, 100);
                border-radius: 2px;
            }
        """)
        
        # Volume percentage input (editable)
        self.volume_label = QLineEdit("100%")
        self.volume_label.setFixedWidth(42)
        self.volume_label.setAlignment(Qt.AlignCenter)
        self.volume_label.setStyleSheet("""
            QLineEdit {
                color: #b3b3b3;
                font-size: 10px;
                background: transparent;
                border: none;
                padding: 0px;
            }
            QLineEdit:focus {
                color: #FFFFFF;
                border-bottom: 1px solid #FFFFFF;
            }
        """)
        self.volume_label.returnPressed.connect(self._on_volume_input)
        self.volume_label.editingFinished.connect(self._on_volume_input)

        self.open_btn = self._create_button("📁", "Load music folder", size=22)
        self.open_btn.clicked.connect(self.open_folder)

        # Add icon + slider group first, then folder button
        volume_box.addWidget(vol_label, 0, Qt.AlignVCenter)
        volume_box.addWidget(self.volume_slider, 0, Qt.AlignVCenter)
        volume_box.addWidget(self.volume_label, 0, Qt.AlignVCenter)

        right_box.addLayout(volume_box)
        right_box.addWidget(self.open_btn, 0, Qt.AlignVCenter)

        bar_row.addLayout(right_box, 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        # Make all three columns share the width equally so column 1 stays centered
        bar_row.setColumnStretch(0, 1)
        bar_row.setColumnStretch(1, 1)
        bar_row.setColumnStretch(2, 1)

        layout.addLayout(bar_row)

        # Apply bottom player style (flat dark bar like Spotify)
        self.setStyleSheet("""
            QWidget#audioPlayerSidebar {
                background-color: #000000;
                border-top: 1px solid #282828;
            }
        """)
    
    def _create_button(self, text: str, tooltip: str, size: int = 40) -> AnimatedButton:
        """Create a styled animated button."""
        btn = AnimatedButton(text)
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: """ + str(size // 2) + """px;
                color: #FFFFFF;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
            }
        """)
        return btn
    
    def open_folder(self):
        """Open folder dialog to load playlist."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Music Folder",
            ""
        )
        if folder:
            self.load_folder(folder)
    
    def load_folder(self, folder_path: str, auto_play: bool = True):
        """Load all audio files from folder."""
        self.playlist = []
        extensions = ('.mp3', '.wav', '.ogg', '.opus', '.flac', '.m4a', '.wma', '.mp4')
        
        for file in sorted(os.listdir(folder_path)):
            if file.lower().endswith(extensions):
                self.playlist.append(os.path.join(folder_path, file))
        
        if self.playlist:
            self.playlistChanged.emit()
            self.current_index = 0
            self._load_current_track()
            self._update_track_label()
            
            if auto_play:
                self.play()
                self._save_last_track()
    
    def _load_current_track(self):
        """Load the current track from playlist."""
        if 0 <= self.current_index < len(self.playlist):
            file_path = self.playlist[self.current_index]
            
            # Apply stereo processing if needed
            playback_path = self._apply_stereo_processing(file_path)
            
            self.player.setSource(QUrl.fromLocalFile(playback_path))
            self.trackChanged.emit(file_path)  # Emit original path for display
            
            # Show track name
            track_name = os.path.basename(file_path)
            self.play_btn.setToolTip(f"Now: {track_name}")
            if hasattr(self, "track_name_label"):
                # Strip extension for a cleaner display
                self.track_name_label.setText(os.path.splitext(track_name)[0])
    
    def _apply_stereo_processing(self, file_path):
        """Apply stereo mode processing to audio file.
        
        Returns path to processed file (temp) or original if no processing needed.
        """
        # Mode 0 = Stereo (no processing needed)
        if self.stereo_mode == 0:
            return file_path
        
        try:
            from pydub import AudioSegment
            import tempfile
            
            # Load audio file
            audio = AudioSegment.from_file(file_path)
            
            # Skip if already mono for some modes
            if audio.channels == 1 and self.stereo_mode in [1, 2, 3]:
                return file_path
            
            processed = None
            
            if self.stereo_mode == 1:  # Mono
                processed = audio.set_channels(1).set_channels(2)  # Convert to mono then back to stereo
            elif self.stereo_mode == 2:  # Left Channel Only
                left = audio.split_to_mono()[0]
                processed = AudioSegment.from_mono_audiosegments(left, left)
            elif self.stereo_mode == 3:  # Right Channel Only
                if audio.channels >= 2:
                    right = audio.split_to_mono()[1]
                    processed = AudioSegment.from_mono_audiosegments(right, right)
                else:
                    return file_path
            elif self.stereo_mode == 4:  # Reverse Stereo
                if audio.channels >= 2:
                    channels = audio.split_to_mono()
                    processed = AudioSegment.from_mono_audiosegments(channels[1], channels[0])
                else:
                    return file_path
            
            if processed:
                # Save to temp file
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, "helxaid_audio_processed.wav")
                processed.export(temp_path, format="wav")
                print(f"[Audio] Processed audio saved to temp file")
                return temp_path
            
        except Exception as e:
            print(f"[Audio] Stereo processing error: {e}")
        
        return file_path
    
    def _update_track_label(self):
        """Update track count label."""
        if self.playlist:
            self.track_label.setText(f"{self.current_index + 1}/{len(self.playlist)}")
        else:
            self.track_label.setText("0/0")
    
    def play(self):
        """Start playback."""
        if self.playlist:
            self.player.play()
            self.is_playing = True
            if hasattr(self, "pause_icon") and not self.pause_icon.isNull():
                self.play_btn.setIcon(self.pause_icon)
            self.playbackStarted.emit()
    
    def set_stereo_mode(self, mode):
        """Set stereo mode and reprocess current track if needed.
        
        0: Stereo (Default)
        1: Mono
        2: Left Channel Only
        3: Right Channel Only
        4: Reverse Stereo
        """
        if self.stereo_mode == mode:
            return  # No change
        
        self.stereo_mode = mode
        print(f"[Audio] Stereo mode changed to: {['Stereo', 'Mono', 'Left Only', 'Right Only', 'Reverse'][mode]}")
        
        # If a track is loaded, reprocess it with new stereo mode
        if self.playlist and 0 <= self.current_index < len(self.playlist):
            was_playing = self.is_playing
            current_pos = self.player.position()
            
            # Reload track with new stereo processing
            self._load_current_track()
            
            # Restore position and playback state
            if current_pos > 0:
                self.player.setPosition(current_pos)
            if was_playing:
                self.play()
    
    def pause(self):
        """Pause playback."""
        self.player.pause()
        self.is_playing = False
        if hasattr(self, "play_icon") and not self.play_icon.isNull():
            self.play_btn.setIcon(self.play_icon)
        
    def toggle_play(self):
        """Toggle play/pause."""
        if self.is_playing:
            self.pause()
        else:
            self.play()
    
    def stop(self):
        """Stop playback."""
        self.player.stop()
        self.is_playing = False
        if hasattr(self, "play_icon") and not self.play_icon.isNull():
            self.play_btn.setIcon(self.play_icon)
        self.progress_slider.setValue(0)
        if hasattr(self, "current_time_label"):
            self.current_time_label.setText("0:00")
        if hasattr(self, "total_time_label"):
            self.total_time_label.setText("0:00")
        self.playbackStopped.emit()
    
    def next_track(self):
        """Play next track in playlist."""
        if self.playlist:
            if self.shuffle_enabled and len(self.playlist) > 1:
                # Pick a random index different from current if possible
                new_index = self.current_index
                while new_index == self.current_index:
                    new_index = random.randint(0, len(self.playlist) - 1)
                self.current_index = new_index
            else:
                self.current_index = (self.current_index + 1) % len(self.playlist)
            
            self._load_current_track()
            self._update_track_label()
            self.play()
            self._save_last_track()
    
    def prev_track(self):
        """Play previous track in playlist."""
        if self.playlist:
            self.current_index = (self.current_index - 1) % len(self.playlist)
            self._load_current_track()
            self._update_track_label()
            self.play()
            self._save_last_track()
            
    def play_at_index(self, index: int):
        """Play specific track index and save state."""
        if self.playlist and 0 <= index < len(self.playlist):
            self.current_index = index
            self._load_current_track()
            self._update_track_label()
            self.play()
            self._save_last_track()
    
    def toggle_loop(self):
        """Toggle loop mode: Off -> All -> One -> Off"""
        self.loop_mode = (self.loop_mode + 1) % 3
        self._update_loop_button()
    
    def _update_loop_button(self):
        """Update loop button style and tooltip."""
        # Update Icon based on mode
        if self.loop_mode == 2 and not self.loop_icon_one.isNull():
            self.loop_btn.setIcon(self.loop_icon_one)
            # Revert size in case we change it, though 32x32 is standard
            self.loop_btn.setIconSize(QSize(32, 32))
        elif not self.loop_icon_all.isNull():
            self.loop_btn.setIcon(self.loop_icon_all)
            self.loop_btn.setIconSize(QSize(32, 32))

        if self.loop_mode == 1:  # Loop All
            self.loop_btn.setToolTip("Loop All")
            self.loop_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.3);
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 91, 6, 0.5);
                }
            """)
        elif self.loop_mode == 2:  # Loop One
            self.loop_btn.setToolTip("Loop One")
            # Loop One can utilize the icon difference primarily, 
            # maybe keep the active background too or make it slightly different
            self.loop_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.3); 
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 91, 6, 0.5);
                }
            """)
        else:  # Off
            self.loop_btn.setToolTip("Loop Off")
            self.loop_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.08);
                }
            """)


    def toggle_shuffle(self):
        """Toggle shuffle mode."""
        self.shuffle_enabled = not self.shuffle_enabled
        self._update_shuffle_button()

    def _update_shuffle_button(self):
        """Update shuffle button style."""
        if self.shuffle_enabled:
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.3);
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 91, 6, 0.5);
                }
            """)
        else:
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.08);
                }
            """)
    
    def _set_volume(self, value: int):
        """Set volume (0-125). Values above 100 provide volume boost."""
        self.audio_output.setVolume(value / 100.0)
        # Update volume percentage input
        if hasattr(self, 'volume_label'):
            self.volume_label.setText(f"{value}%")
            # Highlight when boosted (orange color for > 100%)
            if value > 100:
                self.volume_label.setStyleSheet("""
                    QLineEdit {
                        color: #FF9500;
                        font-size: 10px;
                        font-weight: bold;
                        background: transparent;
                        border: none;
                        padding: 0px;
                    }
                    QLineEdit:focus {
                        color: #FF9500;
                        border-bottom: 1px solid #FF9500;
                    }
                """)
            else:
                self.volume_label.setStyleSheet("""
                    QLineEdit {
                        color: #b3b3b3;
                        font-size: 10px;
                        background: transparent;
                        border: none;
                        padding: 0px;
                    }
                    QLineEdit:focus {
                        color: #FFFFFF;
                        border-bottom: 1px solid #FFFFFF;
                    }
                """)
    
    def _on_volume_input(self):
        """Handle manual volume input from the text field."""
        text = self.volume_label.text().strip().replace('%', '')
        try:
            value = int(text)
            # Clamp to valid range
            value = max(0, min(125, value))
            self.volume_slider.setValue(value)
        except ValueError:
            # Invalid input, reset to current slider value
            self.volume_label.setText(f"{self.volume_slider.value()}%")
    
    def _seek(self, position: int):
        """Seek to position (inverted for vertical)."""
        duration = self.player.duration()
        if duration > 0:
            self.player.setPosition(int(duration * position / 100))
            
    def _on_slider_pressed(self):
        self.is_seeking = True

    def _on_slider_released(self):
        self.is_seeking = False
        self._seek(self.progress_slider.value())

    def _on_position_changed(self, position: int):
        """Update progress slider."""
        if not self.is_seeking:
            duration = self.player.duration()
            if duration > 0:
                self.progress_slider.setValue(int(position * 100 / duration))
                
        if hasattr(self, "current_time_label"):
            self.current_time_label.setText(self._format_time(position))

    def _on_duration_changed(self, duration: int):
        """Handle duration change."""
        if hasattr(self, "total_time_label"):
            self.total_time_label.setText(self._format_time(duration))

    def _format_time(self, ms: int) -> str:
        """Format milliseconds to M:SS."""
        seconds = max(0, ms // 1000)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def _on_state_changed(self, state):
        """Handle playback state changes."""
        from PySide6.QtMultimedia import QMediaPlayer  # Lazy import
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.is_playing = False
            if hasattr(self, "play_icon") and not self.play_icon.isNull():
                self.play_btn.setIcon(self.play_icon)
        elif state == QMediaPlayer.PlaybackState.PlayingState:
            self.is_playing = True
            if hasattr(self, "pause_icon") and not self.pause_icon.isNull():
                self.play_btn.setIcon(self.pause_icon)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.is_playing = False
            if hasattr(self, "play_icon") and not self.play_icon.isNull():
                self.play_btn.setIcon(self.play_icon)
    
    def _on_media_status_changed(self, status):
        """Handle media status changes (for auto next track)."""
        from PySide6.QtMultimedia import QMediaPlayer  # Lazy import
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.playlist:
                if self.loop_mode == 2:  # Loop One
                    # Replay current track
                    self.player.setPosition(0)
                    self.player.play()
                elif self.loop_mode == 1:  # Loop All
                    self.next_track()

    def _on_metadata_changed(self):
        """Handle metadata changes to extract cover art."""
        from PySide6.QtMultimedia import QMediaMetaData  # Lazy import
        metadata = self.player.metaData()
        cover_pixmap = QPixmap()
        
        # 1. Try Metadata (Local)
        thumbnail = metadata.value(QMediaMetaData.ThumbnailImage)
        cover_art = metadata.value(QMediaMetaData.CoverArtImage)
        
        image_obj = thumbnail or cover_art
        
        if image_obj:
            if isinstance(image_obj, QImage):
                cover_pixmap = QPixmap.fromImage(image_obj)
            elif isinstance(image_obj, QPixmap):
                cover_pixmap = image_obj
        
        # 2. Try Windows Thumbnail (if local file)
        # Prioritize local extraction as requested by user
        if (cover_pixmap.isNull() or cover_pixmap.width() == 0) and self.playlist:
            if 0 <= self.current_index < len(self.playlist):
                file_path = self.playlist[self.current_index]
                # Check extensions common for video files
                if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.m4v', '.webm')):
                    try:
                        # Extract from Windows Shell
                        thumb = get_video_thumbnail(file_path)
                        if thumb and not thumb.isNull():
                            cover_pixmap = thumb
                    except Exception as e:
                        print(f"Local thumbnail extraction warning: {e}")

        self.coverChanged.emit(cover_pixmap)
        
        # 3. If no local cover, try online fallback
        if (cover_pixmap.isNull() or cover_pixmap.width() == 0) and self.playlist:
            if 0 <= self.current_index < len(self.playlist):
                try:
                    # Determine search term
                    artist = metadata.value(QMediaMetaData.ContributingArtist)
                    title = metadata.value(QMediaMetaData.Title)
                    
                    if isinstance(artist, list): artist = artist[0] if artist else ""
                    if isinstance(title, list): title = title[0] if title else ""
                    
                    search_term = ""
                    if artist and title:
                        search_term = f"{artist} {title}"
                    else:
                        # Fallback to filename
                        file_path = self.playlist[self.current_index]
                        basename = os.path.basename(file_path)
                        search_term = os.path.splitext(basename)[0]
                        
                        # Cleanup common junk in filenames for better search
                        search_term = re.sub(r'[\(\[\{].*?[\)\]\}]', '', search_term) # Remove content in brackets
                        search_term = search_term.replace("_", " ").strip()
                    
                    if search_term:
                        # Fetch in background
                        threading.Thread(target=self._fetch_online_cover, args=(search_term,), daemon=True).start()
                except Exception as e:
                    print(f"Error preparing online fetch: {e}")

    def _fetch_online_cover(self, search_term):
        """Fetch cover art from iTunes API in background thread."""
        try:
            print(f"[DEBUG] Fetching online cover for: {search_term}")
            query = urllib.parse.quote(search_term)
            url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
            
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status != 200:
                    return
                data = json.loads(response.read().decode())
                
            if data.get("resultCount", 0) > 0:
                result = data["results"][0]
                art_url = result.get("artworkUrl100", "")
                
                if art_url:
                    # Get higher res (600x600)
                    art_url = art_url.replace("100x100bb", "600x600bb")
                    
                    with urllib.request.urlopen(art_url, timeout=5) as img_resp:
                        if img_resp.status == 200:
                            img_data = img_resp.read()
                            pixmap = QPixmap()
                            if pixmap.loadFromData(img_data):
                                self.coverChanged.emit(pixmap)
                                print(f"[DEBUG] Found online cover for {search_term}")
        except Exception as e:
            print(f"[DEBUG] Online fetch failed: {e}")

    def _on_error(self, error, error_string):
        """Handle player errors."""
        print(f"Audio player error: {error_string}")
    
    def _save_last_track(self):
        """Save current track to settings."""
        if self.settings_path and self.playlist:
            try:
                print(f"[DEBUG] Saving last track: Index {self.current_index}")
                settings = {}
                if os.path.exists(self.settings_path):
                    with open(self.settings_path, 'r') as f:
                        settings = json.load(f)
                
                # Merge with any existing audio_player settings to preserve other keys
                audio_settings = settings.get('audio_player', {})
                audio_settings.update({
                    'folder': os.path.dirname(self.playlist[0]) if self.playlist else '',
                    'index': self.current_index,
                    'volume': self.volume_slider.value(),
                    'stereo_mode': self.stereo_mode,
                    'loop_mode': self.loop_mode,
                    'shuffle_enabled': self.shuffle_enabled,
                    # Persist the currently selected audio output device by description
                    'device': self.audio_output.device().description() if self.audio_output.device() else "",
                })
                settings['audio_player'] = audio_settings
                
                with open(self.settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
            except Exception as e:
                print(f"Error saving audio settings: {e}")
    
    def set_stereo_mode(self, mode: int):
        """Set stereo mode and save settings."""
        self.stereo_mode = mode
        self._save_last_track()

    def _load_last_track(self):
        """Load last track from settings."""
        from PySide6.QtMultimedia import QMediaDevices  # Lazy import
        if self.settings_path and os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                
                audio_settings = settings.get('audio_player', {})
                # Restore previously selected output device if available
                saved_device_desc = audio_settings.get('device', '')
                device_restored = False
                if saved_device_desc:
                    try:
                        for dev in QMediaDevices.audioOutputs():
                            if dev.description() == saved_device_desc:
                                self.audio_output.setDevice(dev)
                                device_restored = True
                                print(f"[DEBUG] Restored audio device: {saved_device_desc}")
                                break
                    except Exception as e:
                        print(f"Warning: could not restore audio device '{saved_device_desc}': {e}")
                
                if not device_restored:
                    # Fallback to system default
                    default_dev = QMediaDevices.defaultAudioOutput()
                    self.audio_output.setDevice(default_dev)
                    print(f"[DEBUG] Using default audio device: {default_dev.description()}")
                
                folder = audio_settings.get('folder', '')
                index = audio_settings.get('index', 0)
                volume = audio_settings.get('volume', 100)
                self.stereo_mode = audio_settings.get('stereo_mode', 0)
                self.loop_mode = audio_settings.get('loop_mode', 1)
                self.shuffle_enabled = audio_settings.get('shuffle_enabled', False)
                
                # Update UI state for loop/shuffle
                self._update_loop_button()
                self._update_shuffle_button()
                
                if folder and os.path.exists(folder):
                    self.load_folder(folder, auto_play=False)
                    if 0 <= index < len(self.playlist):
                        self.current_index = index
                        self._load_current_track()
                        self._update_track_label()
                    # State is restored, but pause by default (or resume if we want auto-resume?)
                    # User requested "remember what user turned on", implying shuffle/loop.
                    # Does user want auto-RESUME playback? "what last music they play"
                    # Usually players start paused.
                    self.pause()
                
                self.volume_slider.setValue(volume)
                self._set_volume(volume)
            except Exception as e:
                print(f"Error loading audio settings: {e}")
    
    def paintEvent(self, event):
        """Draw semi-transparent background for glassmorphism effect."""
        from PySide6.QtGui import QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Semi-transparent dark background with rounded corners
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        painter.fillPath(path, QColor(30, 30, 30, 190))
        painter.end()

# ----------------------------------------------------------
# Main Launcher UI
# ----------------------------------------------------------
class GameLauncher(QWidget):
    # Class-level icon cache to avoid reloading same icons
    _icon_cache = {}
    _icon_cache_max_size = 67 # Limit cache to prevent RAM growth
    
    def _cleanup_memory(self):
        """Periodic memory cleanup to prevent RAM growth."""
        # Limit icon cache size
        if len(self._icon_cache) > self._icon_cache_max_size:
            # Remove oldest entries (first 25% of cache)
            keys = list(self._icon_cache.keys())
            for key in keys[:len(keys) // 4]:
                del self._icon_cache[key]
        
        # Run garbage collection
        gc.collect()
    
    def _apply_initial_size(self):
        """Apply window size after layout is complete."""
        # Don't apply default centering if user has saved geometry
        if hasattr(self, 'settings') and self.settings.get("window_geometry"):
            return
            
        if hasattr(self, '_target_size'):
            target_w, target_h, screen_w, screen_h = self._target_size
            self.resize(target_w, target_h)
            # Center on screen
            x = (screen_w - target_w) // 2
            y = (screen_h - target_h) // 2
            self.move(x, y)
            print(f"[Window] Applied default size: {target_w}x{target_h} at ({x}, {y})")
    
    def __init__(self):
        super().__init__()
        self.current_edit_game = None  # Store the game being edited
        self._game_text_color = "#e0e0e0"  # Default light text, updated by apply_theme
        self._has_bg_image = False  # Track if custom background is set
        
        # Load settings
        self.settings = load_settings()
        
        # Set window size based on PHYSICAL screen resolution (ignore DPI scaling)
        screen = QApplication.primaryScreen()
        if screen:
            # Get physical screen resolution using Windows API (ignores DPI scaling)
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # SM_CXSCREEN = 0, SM_CYSCREEN = 1 (physical pixels)
                physical_w = user32.GetSystemMetrics(0)
                physical_h = user32.GetSystemMetrics(1)
                print(f"[Window] Physical Screen: {physical_w}x{physical_h}")
            except:
                # Fallback to Qt (may be affected by scaling)
                physical_w = screen.size().width()
                physical_h = screen.size().height()
                print(f"[Window] Screen (Qt): {physical_w}x{physical_h}")
            
            # Always use 50% of physical screen (no minimum, proportional to screen)
            target_w = physical_w // 2
            target_h = physical_h // 2
            
            # Store for delayed resize
            self._target_size = (target_w, target_h, physical_w, physical_h)
            print(f"[Window] Target size: {target_w}x{target_h}")
            
            # Apply immediately AND delayed (belt and suspenders)
            self.resize(target_w, target_h)
            QTimer.singleShot(200, self._apply_initial_size)
            
        # Set AppUserModelID FIRST (needed for taskbar icon on Windows)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            if os.name == 'nt':  # Only for Windows
                import ctypes
                myappid = 'HELXAID'  # Arbitrary string
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f"Warning: Could not set app user model ID: {e}")
            
        # Initialize Hardware Manager (starts background thread)
        try:
            self.hw_manager = get_hardware_manager()
            self.hw_manager.start_manager()
        except Exception as e:
            print(f"[Launcher] Failed to start HardwareManager: {e}")
            
        # Set window icon using both Qt and win32gui for proper taskbar display
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, "UI Icons", "launcher-icon.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
                QApplication.instance().setWindowIcon(icon)
            
            if _ensure_win32_loaded():
                try:
                    icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
                    hicon = win32gui.LoadImage(None, icon_path, win32con.IMAGE_ICON, 0, 0, icon_flags)
                    if hicon:
                        self._hicon = hicon
                        QTimer.singleShot(100, self._apply_taskbar_icon)
                        
                        # Setup periodic memory cleanup (every 60 seconds)
                        self._memory_timer = QTimer(self)
                        self._memory_timer.timeout.connect(self._cleanup_memory)
                        self._memory_timer.start(60000)  # 60 seconds
                except:
                    pass
        
        # Apply resizable window setting from settings
        is_resizable = self.settings.get("resizable_window", True)
        if not is_resizable:
            # Lock window size to a default if not resizable
            self.setFixedSize(1360, 720)
        else:
            # Set minimum size if resizable
            self.setMinimumSize(1380, 790)
            
        # Load saved window geometry and state
        self.setWindowTitle("HELXAID")
        if self.settings.get("window_fullscreen", False):
            self.showFullScreen()
        else:
            # Try to restore geometry
            geometry = self.settings.get("window_geometry")
            if geometry and len(geometry) == 4:
                # geometry is a list [x, y, w, h]
                self.move(geometry[0], geometry[1])
                self.resize(geometry[2], geometry[3])
                
        # Window opacity
        self.setWindowOpacity(self.settings.get("window_opacity", 1.0))
        
        # Enable drag-drop from non-elevated Explorer to elevated app (UAC bypass for drag-drop)
        self._enable_drag_drop_for_elevated()
        
        # Apply theme (will use background image and auto-palette if set)
        self.apply_theme()
        # Re-apply after layout settles so background scales to final window size
        # (at this point the window geometry may not be restored yet)
        QTimer.singleShot(500, self.apply_theme)

        self.data = load_json()
        
        # Auto-fix corrupt icons at startup
        validate_and_fix_corrupt_icons(self.data)
        
        # Clean corrupted game_exe fields (remove system processes, etc.)
        self._sanitize_game_exes()
        
        self.icon_scale = self.settings.get("icon_scale", 1)
        self.confirm_on_exit = self.settings.get("confirm_on_exit", True)
        self.grid_size = 100
        self.search_query = ""
        self.selected_game_index = -1  # For keyboard navigation
        self.game_buttons = []  # Store game buttons for keyboard nav
        self.current_session = None  # Track currently playing game: {"game": game, "start_time": time, "from_launcher": bool}
        
        # Background game detection timer (checks every 2 seconds for real-time detection)
        # IMPORTANT: The actual psutil scanning runs in a background thread (_process_scan_thread)
        # to avoid blocking the UI. This timer only reads from cached results.
        self._process_cache = set()  # Cached set of running process names (lowercase)
        self._process_path_cache = {}  # name.lower() -> set of full exe paths
        self._process_ppid_cache = {}  # pid -> ppid for child-process tracking
        self._process_cache_lock = threading.Lock()
        self._start_process_scan_thread()
        
        self.game_detection_timer = QTimer()
        self.game_detection_timer.timeout.connect(self._scan_for_running_games)
        self.game_detection_timer.start(2000)  # 2 seconds for real-time detection
        
        # Setup local server to listen for restore signals from second instance
        self._setup_single_instance_server()
        
        # Setup system tray icon
        self.setup_system_tray()

        # =============================================
        # MAIN LAYOUT: Sidebar + Content Panel
        # =============================================
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ---- SIDEBAR (80px) ----
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebarNav")
        self.sidebar.setFixedWidth(80)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 15, 0, 15)
        sidebar_layout.setSpacing(15)
        # Force horizontal centering for all items (vertical centering handled by stretches)
        sidebar_layout.setAlignment(Qt.AlignHCenter)

        # Add stretch at the top so items can sit in the vertical center between top and bottom stretches
        sidebar_layout.addStretch()

        # Logo/Home button
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.home_btn = AnimatedButton()
        self.home_btn.setObjectName("NavHomeButton")
        self.home_btn.setFixedSize(60, 60)
        self.home_btn.setToolTip("Home")
        self.home_btn.setCursor(Qt.PointingHandCursor)
        icon_path = os.path.join(script_dir, "UI Icons", "game-icon.png")
        if os.path.exists(icon_path):
            self.home_btn.setIcon(QIcon(icon_path))
            self.home_btn.setIconSize(QSize(48, 48))
        else:
            self.home_btn.setText("")
        self.home_btn.clicked.connect(lambda: self.switch_panel(0))
        self.home_btn.setClickAnimation(False)
        # Remove individual alignment args since layout is centered globally, but keeping it is safer
        sidebar_layout.addWidget(self.home_btn, 0, Qt.AlignHCenter)
        
        # Music button
        self.music_nav_btn = AnimatedButton()
        self.music_nav_btn.setObjectName("NavMusicButton")
        self.music_nav_btn.setFixedSize(64, 64)
        self.music_nav_btn.setToolTip("HELXAIC - Music Player")
        self.music_nav_btn.setCursor(Qt.PointingHandCursor)

        music_icon_path = os.path.join(script_dir, "UI Icons", "player-icon.png")
        if os.path.exists(music_icon_path):
            music_pixmap = QPixmap(music_icon_path)
            music_scaled = music_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.music_nav_btn.setIcon(QIcon(music_scaled))
            self.music_nav_btn.setIconSize(QSize(64, 64))
        else:
             pass

        self.music_nav_btn.clicked.connect(lambda: self.switch_panel(1))
        self.music_nav_btn.setClickAnimation(False)
        sidebar_layout.addWidget(self.music_nav_btn, 0, Qt.AlignHCenter)

        # CPU Control button
        self.cpu_nav_btn = AnimatedButton()
        self.cpu_nav_btn.setObjectName("NavCPUButton")
        self.cpu_nav_btn.setFixedSize(64, 64)
        self.cpu_nav_btn.setToolTip("HELXAIL - CPU Control")
        self.cpu_nav_btn.setCursor(Qt.PointingHandCursor)
        
        # Load UXTU icon
        uxtu_icon_path = os.path.join(script_dir, "UI Icons", "uxtu_icon.png")
        if os.path.exists(uxtu_icon_path):
            uxtu_pixmap = QPixmap(uxtu_icon_path)
            uxtu_scaled = uxtu_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cpu_nav_btn.setIcon(QIcon(uxtu_scaled))
            self.cpu_nav_btn.setIconSize(QSize(64, 64))
        else:
            self.cpu_nav_btn.setText("")
        
        self.cpu_nav_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QPushButton:disabled {
                opacity: 0.3;
            }
        """)
        
        # Check if UXTU is installed
        self.uxtu_installed = is_uxtu_installed()
        
        # CPU button always enabled - shows download prompt if RyzenAdj not available
        if not is_ryzenadj_available():
            self.cpu_nav_btn.setToolTip("HELXAIL - CPU Control (Click to install RyzenAdj)")
        else:
            self.cpu_nav_btn.setToolTip("HELXAIL - CPU Control")
        
        self.cpu_nav_btn.clicked.connect(self._on_cpu_nav_clicked)
        self.cpu_nav_btn.setClickAnimation(False)
        
        sidebar_layout.addWidget(self.cpu_nav_btn, 0, Qt.AlignHCenter)
        
        # Crosshair button
        self.crosshair_nav_btn = AnimatedButton()
        self.crosshair_nav_btn.setObjectName("NavCrosshairButton")
        self.crosshair_nav_btn.setFixedSize(64, 64)
        self.crosshair_nav_btn.setToolTip("HELXAIR - Crosshair Overlay")
        self.crosshair_nav_btn.setCursor(Qt.PointingHandCursor)
        
        # Load crosshair icon
        crosshair_icon_path = os.path.join(script_dir, "UI Icons", "crosshair_icon.png")
        if os.path.exists(crosshair_icon_path):
            crosshair_pixmap = QPixmap(crosshair_icon_path)
            crosshair_scaled = crosshair_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.crosshair_nav_btn.setIcon(QIcon(crosshair_scaled))
            self.crosshair_nav_btn.setIconSize(QSize(64, 64))
        else:
            self.crosshair_nav_btn.setText("")
        
        self.crosshair_nav_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                font-size: 28px;
            }
        """)
        self.crosshair_nav_btn.clicked.connect(lambda: self.switch_panel(3))
        self.crosshair_nav_btn.setClickAnimation(False)
        sidebar_layout.addWidget(self.crosshair_nav_btn, 0, Qt.AlignHCenter)

        # Macro button (opens settings dialog)
        self.macro_nav_btn = AnimatedButton()
        self.macro_nav_btn.setObjectName("NavMacroButton")
        self.macro_nav_btn.setFixedSize(64, 64)
        self.macro_nav_btn.setToolTip("HELXAIRO")
        self.macro_nav_btn.setCursor(Qt.PointingHandCursor)
        
        # Load macro icon or use emoji fallback
        macro_icon_path = os.path.join(script_dir, "UI Icons", "macro-icon.png")
        if os.path.exists(macro_icon_path):
            macro_pixmap = QPixmap(macro_icon_path)
            macro_scaled = macro_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.macro_nav_btn.setIcon(QIcon(macro_scaled))
            self.macro_nav_btn.setIconSize(QSize(64, 64))
        else:
            self.macro_nav_btn.setText("")
        
        self.macro_nav_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                font-size: 28px;
            }
        """)
        self.macro_nav_btn.clicked.connect(lambda: self.switch_panel(4))
        self.macro_nav_btn.setClickAnimation(False)
        sidebar_layout.addWidget(self.macro_nav_btn, 0, Qt.AlignHCenter)

        # Hardware button
        self.hardware_nav_btn = AnimatedButton()
        self.hardware_nav_btn.setObjectName("NavHardwareButton")
        self.hardware_nav_btn.setFixedSize(64, 64)
        self.hardware_nav_btn.setToolTip("HELXTATS - Hardware Stats")
        self.hardware_nav_btn.setCursor(Qt.PointingHandCursor)
        
        # Load hardware icon or use emoji fallback
        hardware_icon_path = os.path.join(script_dir, "UI Icons", "hardware-icon.png")
        if os.path.exists(hardware_icon_path):
            hardware_pixmap = QPixmap(hardware_icon_path)
            hardware_scaled = hardware_pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.hardware_nav_btn.setIcon(QIcon(hardware_scaled))
            self.hardware_nav_btn.setIconSize(QSize(40, 40))
        else:
            self.hardware_nav_btn.setText("")
        
        self.hardware_nav_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                font-size: 28px;
            }
        """)
        self.hardware_nav_btn.clicked.connect(lambda: self.switch_panel(5))
        self.hardware_nav_btn.setClickAnimation(False)
        sidebar_layout.addWidget(self.hardware_nav_btn, 0, Qt.AlignHCenter)

        # Bottom stretch pushes nav icons toward center; settings pin stays at very bottom
        sidebar_layout.addStretch()
        
        # ===== SETTINGS BUTTON (bottom-pinned) =====
        # Thin separator dividing nav icons from the settings button at the bottom
        settings_sep = QFrame()
        settings_sep.setFrameShape(QFrame.HLine)
        settings_sep.setFixedWidth(44)
        settings_sep.setStyleSheet("background: rgba(255,91,6,0.25); border: none; max-height: 1px;")
        sidebar_layout.addWidget(settings_sep, 0, Qt.AlignHCenter)
        sidebar_layout.addSpacing(6)
        
        self.settings_nav_btn = AnimatedButton()
        self.settings_nav_btn.setObjectName("NavSettingsButton")
        self.settings_nav_btn.setFixedSize(64, 64)
        self.settings_nav_btn.setToolTip("Settings")
        self.settings_nav_btn.setCursor(Qt.PointingHandCursor)
        
        settings_nav_icon_path = os.path.join(script_dir, "UI Icons", "setting-icon.png")
        if os.path.exists(settings_nav_icon_path):
            _s_pix = QPixmap(settings_nav_icon_path)
            _s_scaled = _s_pix.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.settings_nav_btn.setIcon(QIcon(_s_scaled))
            self.settings_nav_btn.setIconSize(QSize(40, 40))
            
            # Spin-on-hover animation — same logic as top-bar settings button
            from PySide6.QtGui import QTransform, QPainter
            _anim_size = 80
            _anim_pix = _s_pix.scaled(_anim_size, _anim_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _frames = []
            for _i in range(60):
                _angle = -6 * _i
                _rot = _anim_pix.transformed(QTransform().rotate(_angle), Qt.SmoothTransformation)
                _canvas = QPixmap(_anim_size, _anim_size)
                _canvas.fill(Qt.transparent)
                _p = QPainter(_canvas)
                _p.drawPixmap((_anim_size - _rot.width()) // 2, (_anim_size - _rot.height()) // 2, _rot)
                _p.end()
                _frames.append(QIcon(_canvas))
            
            self.settings_nav_btn._rot_frames = _frames
            self.settings_nav_btn._rot_index = 0
            self.settings_nav_btn._rot_timer = QTimer()
            self.settings_nav_btn._rot_timer.setInterval(80)
            self.settings_nav_btn._rot_current_interval = 80
            self.settings_nav_btn._rot_hovering = False
            
            def _nav_settings_tick():
                self.settings_nav_btn._rot_index = (self.settings_nav_btn._rot_index + 1) % len(_frames)
                self.settings_nav_btn.setIcon(_frames[self.settings_nav_btn._rot_index])
                if self.settings_nav_btn._rot_hovering:
                    self.settings_nav_btn._rot_current_interval = max(1, self.settings_nav_btn._rot_current_interval * 0.995)
                    self.settings_nav_btn._rot_timer.setInterval(int(self.settings_nav_btn._rot_current_interval))
                else:
                    self.settings_nav_btn._rot_current_interval *= 1.05
                    if self.settings_nav_btn._rot_current_interval > 200:
                        self.settings_nav_btn._rot_timer.stop()
                        self.settings_nav_btn._rot_current_interval = 80
                    else:
                        self.settings_nav_btn._rot_timer.setInterval(int(self.settings_nav_btn._rot_current_interval))
            
            self.settings_nav_btn._rot_timer.timeout.connect(_nav_settings_tick)
            
            _orig_enter = self.settings_nav_btn.enterEvent
            _orig_leave = self.settings_nav_btn.leaveEvent
            
            def _nav_settings_enter(ev):
                self.settings_nav_btn._rot_hovering = True
                if not self.settings_nav_btn._rot_timer.isActive():
                    self.settings_nav_btn._rot_current_interval = 80
                    self.settings_nav_btn._rot_timer.setInterval(80)
                    self.settings_nav_btn._rot_timer.start()
                _orig_enter(ev)
            
            def _nav_settings_leave(ev):
                self.settings_nav_btn._rot_hovering = False
                _orig_leave(ev)
            
            self.settings_nav_btn.enterEvent = _nav_settings_enter
            self.settings_nav_btn.leaveEvent = _nav_settings_leave
        else:
            self.settings_nav_btn.setText("")
        
        self.settings_nav_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                font-size: 28px;
            }
        """)
        self.settings_nav_btn.clicked.connect(self.open_quick_settings)
        self.settings_nav_btn.setClickAnimation(False)
        sidebar_layout.addWidget(self.settings_nav_btn, 0, Qt.AlignHCenter)
        sidebar_layout.addSpacing(8)
        
        # Initialize macro system bridge (lazy initialization)
        self._macro_bridge = None
        
        # Apply sidebar style (no borders on nav buttons)
        self.sidebar.setStyleSheet("""
            QFrame#sidebarNav {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1a, stop:0.5 #252525, stop:1 #1a1a1a);
                border-right: 2px solid rgba(255, 91, 6, 0.4);
                padding: 0px;
                margin: 0px;
            }
            QFrame#sidebarNav QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: #e0e0e0;
                font-size: 24px;
                padding: 0px;
                margin: 0px;
                text-align: center;
                qproperty-iconSize: 48px 48px;
            }
        """)
        
        root_layout.addWidget(self.sidebar)
        
        # ---- CONTENT STACK ----
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ContentStack")
        root_layout.addWidget(self.content_stack, 1)
        
        # Panel 0: Home (Game Grid) - wrap existing content
        self.home_panel = QWidget()
        self.home_panel.setObjectName("HomePanel")
        main_layout = QVBoxLayout(self.home_panel)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        self.content_stack.addWidget(self.home_panel)


        # Create a container widget for the top bar with fixed height
        top_bar_container = QWidget()
        top_bar_container.setFixedHeight(80)  # Fixed height for top bar
        top_bar = QHBoxLayout(top_bar_container)
        top_bar.setContentsMargins(0, 0, 0, 0)
        
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow_path = os.path.join(script_dir, 'UI Icons', 'up-arrow.png').replace('\\', '/')
        down_arrow_path = os.path.join(script_dir, 'UI Icons', 'down-arrow.png').replace('\\', '/')

        # Spin box for icon size
        self.size_spin = QSpinBox()
        self.size_spin.setMinimum(1)
        self.size_spin.setMaximum(10)
        self.size_spin.setValue(1)  # Default value
        self.size_spin.setFixedWidth(200)  # Slightly wider to accommodate buttons
        self.size_spin.setStyleSheet(f"""
        QSpinBox {{
            padding: 5px 30px 5px 8px;  /* Added right padding for arrow buttons */
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            background: #3a3a3a;
            color: #e0e0e0;
        }}
        QSpinBox:focus {{
            border: 1px solid #FF5B06;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 30px;
            border-left: 1px solid #4a4a4a;
            background: #3a3a3a;
            subcontrol-origin: padding;
            subcontrol-position: center;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background: #4a4a4a;
        }}
        QSpinBox::up-arrow {{
            image: url({up_arrow_path});
            width: 16px;
            height: 16px;
        }}
        QSpinBox::down-arrow {{
            image: url({down_arrow_path});
            width: 16px;
            height: 16px;
        }}
        QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled {{
            image: none;
        }}
    """)
        self.size_spin.valueChanged.connect(self.change_grid_size)
        
        # Layout for left-aligned controls with app title
        left_controls = QHBoxLayout()

        # Create a horizontal layout for the title with icon
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        
        # Add the launcher icon with larger size and better quality
        icon_label = QLabel()
        icon_label.setObjectName("HeaderIconLabel")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "UI Icons", "launcher-icon.png")
        if os.path.exists(icon_path):
            # Load the icon from the file
            icon = QIcon(icon_path)
            
            # Create a pixmap with a larger size (64x64 for better visibility)
            pixmap = icon.pixmap(48, 48)
            
            # Set the pixmap to the label with proper scaling
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(64, 64)  # Fixed size for the label
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setCursor(Qt.PointingHandCursor)
            icon_label.mousePressEvent = lambda event: self.open_launcher_youtube()
        
        # Add the text label
        self.title_label = QLabel("HELXAID")
        self.title_label.setObjectName("HeaderTitleLabel")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 25px;
                font-weight: bold;
                color: #FF5B06;
                padding: 5px 15px 5px 0;
                margin: 0;
                background: transparent;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        
        # Add widgets to the layout with compact spacing
        title_layout.addWidget(icon_label, 0, Qt.AlignVCenter)
        title_layout.addWidget(self.title_label, 0, Qt.AlignVCenter)
        title_layout.addStretch(1)  # Push everything to the left
        
        # Create a container widget for the title with some left margin
        title_widget = QWidget()
        title_widget.setLayout(title_layout)
        title_widget.setStyleSheet("margin-left: 10px;")  # Add some left margin
        
        # Add title widget to left controls
        left_controls.addWidget(title_widget)
        left_controls.addStretch()
        
        # Right side controls container
        right_controls = QHBoxLayout()
        right_controls.setSpacing(10)

        # Search box (to the left of the + button)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Search Games...")
        self.search_input.setFixedWidth(400)
        self.search_input.setFixedHeight(50)
        self.search_input.textChanged.connect(self.on_search_text_changed)

        # Settings button (icon-based)
        self.settings_btn = AnimatedButton()
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setFixedSize(64, 64)

        settings_icon_path = os.path.join(script_dir, "UI Icons", "setting-icon.png")
        if os.path.exists(settings_icon_path):
            settings_pixmap = QPixmap(settings_icon_path)
            settings_scaled = settings_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.settings_btn.setIcon(QIcon(settings_scaled))
            self.settings_btn.setIconSize(QSize(48, 48))
        else:
            self.settings_btn.setText("Settings")

        # Override global button border so this icon button has no orange outline
        self.settings_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 8px;
                background: transparent;
            }
            QPushButton:hover {
            }
        """)
        
        # Setup continuous rotation animation while hovering
        if os.path.exists(settings_icon_path):
            from PySide6.QtGui import QTransform, QPainter
            
            # Pre-scale pixmap for smooth animation
            anim_size = 96
            settings_anim_pixmap = QPixmap(settings_icon_path).scaled(anim_size, anim_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Create 360 degree frames for continuous rotation
            num_frames = 60  # 60 frames = 6° per frame
            settings_frames = []
            for i in range(num_frames):
                angle = -6 * i  # Rotate left (counter-clockwise)
                transform = QTransform().rotate(angle)
                rotated = settings_anim_pixmap.transformed(transform, Qt.SmoothTransformation)
                
                canvas = QPixmap(anim_size, anim_size)
                canvas.fill(Qt.transparent)
                painter = QPainter(canvas)
                x = (anim_size - rotated.width()) // 2
                y = (anim_size - rotated.height()) // 2
                painter.drawPixmap(x, y, rotated)
                painter.end()
                
                settings_frames.append(QIcon(canvas))
            
            self.settings_btn._rot_frames = settings_frames
            self.settings_btn._rot_index = 0
            self.settings_btn._rot_timer = QTimer()
            self.settings_btn._rot_current_interval = 80  # Start slow
            self.settings_btn._rot_timer.setInterval(80)
            self.settings_btn._rot_hovering = False
            
            def _animate_settings_continuous():
                # Loop continuously through frames
                self.settings_btn._rot_index = (self.settings_btn._rot_index + 1) % len(settings_frames)
                self.settings_btn.setIcon(settings_frames[self.settings_btn._rot_index])
                
                if self.settings_btn._rot_hovering:
                    # Speed up gradually while hovering (decrease interval slowly, no limit)
                    self.settings_btn._rot_current_interval = max(1, self.settings_btn._rot_current_interval * 0.995)
                    self.settings_btn._rot_timer.setInterval(int(self.settings_btn._rot_current_interval))
                else:
                    # Slow down when not hovering
                    self.settings_btn._rot_current_interval *= 1.05
                    if self.settings_btn._rot_current_interval > 200:
                        self.settings_btn._rot_timer.stop()
                        self.settings_btn._rot_current_interval = 80  # Reset for next hover
                    else:
                        self.settings_btn._rot_timer.setInterval(int(self.settings_btn._rot_current_interval))
            
            self.settings_btn._rot_timer.timeout.connect(_animate_settings_continuous)
            
            original_enter = self.settings_btn.enterEvent
            original_leave = self.settings_btn.leaveEvent
            
            def new_enter(event):
                self.settings_btn._rot_hovering = True
                if not self.settings_btn._rot_timer.isActive():
                    self.settings_btn._rot_current_interval = 80  # Start slow
                    self.settings_btn._rot_timer.setInterval(80)
                    self.settings_btn._rot_timer.start()
                original_enter(event)
            
            def new_leave(event):
                self.settings_btn._rot_hovering = False
                # Don't stop timer - let it slow down gradually
                original_leave(event)
            
            self.settings_btn.enterEvent = new_enter
            self.settings_btn.leaveEvent = new_leave

        self.settings_btn.clicked.connect(self.open_settings)
        
        # Add Game menu with two options: manual add and automatic Universal Scan
        self.add_menu = QMenu(self)
        manual_action = self.add_menu.addAction("Add Game Manually")
        universal_scan_action = self.add_menu.addAction("Universal Scan")
        
        self.add_menu.addSeparator()
        
        folders_action = self.add_menu.addAction("Manage Game Folders")
        scan_local_action = self.add_menu.addAction("Scan Local Folders")
        
        manual_action.triggered.connect(self.add_game_manual)
        universal_scan_action.triggered.connect(self.universal_scan)
        folders_action.triggered.connect(self.manage_game_folders)
        scan_local_action.triggered.connect(self.scan_local_folders)
        
        # Add Game button (icon-based) with same behavior
        self.add_btn = AnimatedButton()
        self.add_btn.setObjectName("AddGameButton")
        self.add_btn.setFixedSize(64, 64)

        add_icon_path = os.path.join(script_dir, "UI Icons", "add-icon.png")
        if os.path.exists(add_icon_path):
            add_pixmap = QPixmap(add_icon_path)
            add_scaled = add_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.add_btn.setIcon(QIcon(add_scaled))
            self.add_btn.setIconSize(QSize(48, 48))
        else:
            self.add_btn.setText("Add Game")

        # Override global button border so this icon button has no orange outline
        self.add_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 8px;
                background: transparent;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 12px 0px 12px;  /* Slightly more horizontal padding when text is used */
            }
            QPushButton::menu-indicator {
                image: none;   /* Hide the default dropdown arrow */
                width: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)
        self.add_btn.setMenu(self.add_menu)

        # Refresh button with circular arrow symbol
        self.refresh_btn = AnimatedButton()
        self.refresh_btn.setObjectName("RefreshButton")
        self.refresh_btn.setFixedSize(64, 64)

        refresh_icon_path = os.path.join(script_dir, "UI Icons", "refresh.png")
        if os.path.exists(refresh_icon_path):
            refresh_pixmap = QPixmap(refresh_icon_path)
            refresh_scaled = refresh_pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.refresh_btn.setIcon(QIcon(refresh_scaled))
            self.refresh_btn.setIconSize(QSize(48, 48))
        else:
            self.refresh_btn.setText("⟳")

        self.refresh_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 5px;
                background: transparent;
            }
            QPushButton:hover {
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton:disabled {
                color: #888888;
            }
        """)
        self.refresh_btn.setToolTip("Refresh Library")
        self.refresh_btn.clicked.connect(self.refresh)
        
        # Setup 360-degree rotation animation with ease-out on hover
        if os.path.exists(refresh_icon_path):
            from PySide6.QtGui import QTransform, QPainter
            
            # Pre-scale pixmap to reasonable size for smooth animation
            anim_size = 96
            refresh_anim_pixmap = QPixmap(refresh_icon_path).scaled(anim_size, anim_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Create frames with ease-out timing (fast start, slow end)
            # Using cubic ease-out: 1 - (1 - t)^3
            num_frames = 60  # 60 frames for smooth 60fps animation
            refresh_frames = []
            for i in range(num_frames + 1):
                t = i / num_frames  # 0 to 1
                # Cubic ease-out
                eased_t = 1 - pow(1 - t, 3)
                angle = 360 * eased_t
                
                transform = QTransform().rotate(angle)
                rotated = refresh_anim_pixmap.transformed(transform, Qt.SmoothTransformation)
                
                # Create canvas with fixed size and center the rotated icon
                canvas = QPixmap(anim_size, anim_size)
                canvas.fill(Qt.transparent)
                painter = QPainter(canvas)
                x = (anim_size - rotated.width()) // 2
                y = (anim_size - rotated.height()) // 2
                painter.drawPixmap(x, y, rotated)
                painter.end()
                
                refresh_frames.append(QIcon(canvas))
            
            self.refresh_btn._rot_frames = refresh_frames
            self.refresh_btn._rot_index = 0
            self.refresh_btn._rot_timer = QTimer()
            self.refresh_btn._rot_timer.setInterval(17)  # ~1000ms / 60 frames = 17ms per frame (60fps)
            self.refresh_btn._rot_animating = False
            
            def _animate_refresh_frame():
                if self.refresh_btn._rot_index < len(refresh_frames) - 1:
                    self.refresh_btn._rot_index += 1
                    self.refresh_btn.setIcon(refresh_frames[self.refresh_btn._rot_index])
                else:
                    self.refresh_btn._rot_timer.stop()
                    self.refresh_btn._rot_animating = False
                    self.refresh_btn._rot_index = 0
                    self.refresh_btn.setIcon(refresh_frames[0])  # Reset to original
            
            self.refresh_btn._rot_timer.timeout.connect(_animate_refresh_frame)
            
            original_enter = self.refresh_btn.enterEvent
            
            def new_enter(event):
                if not self.refresh_btn._rot_animating:
                    self.refresh_btn._rot_animating = True
                    self.refresh_btn._rot_index = 0
                    self.refresh_btn._rot_timer.start()
                original_enter(event)
            
            self.refresh_btn.enterEvent = new_enter

        # Add OMEN Command Center button
        self.omen_btn = QPushButton()
        self.omen_btn.setFixedSize(60, 60)  # Larger button size
        self.omen_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 5px;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)

        # Set the OMEN icon (supports both source run and PyInstaller EXE)
        omen_icon_path = None
        # 1) Directory of this script (when running from source)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths = [
            os.path.join(script_dir, "UI Icons", "omen.png"),
            # 2) Current working directory (when running packaged EXE from its folder)
            os.path.join(os.getcwd(), "omen.png"),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                omen_icon_path = path
                break

        if omen_icon_path and os.path.exists(omen_icon_path):
            # Create pixmap and scale it smoothly to 48x48
            pixmap = QPixmap(omen_icon_path)
            scaled_pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.omen_btn.setIcon(QIcon(scaled_pixmap))
            self.omen_btn.setIconSize(QSize(48, 48))  # Larger 48x48 icon
        else:
            self.omen_btn.setText("")
            self.omen_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                    color: #FFFFFF;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                    border-radius: 5px;
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.15);
                }
            """)

        self.omen_btn.setToolTip("OMEN Command Center")
        # Launch OMEN Gaming Hub via its app ID using PowerShell
        self.omen_btn.clicked.connect(self.launch_omen_hub)

        # Add widgets to right controls (search, settings, add, refresh, omen)
        right_controls.addWidget(self.search_input)
        right_controls.addWidget(self.settings_btn)
        right_controls.addWidget(self.add_btn)
        right_controls.addWidget(self.refresh_btn)
        right_controls.addWidget(self.omen_btn)

        # Add layouts to top bar
        top_bar.addLayout(left_controls)
        top_bar.addStretch()
        top_bar.addLayout(right_controls)
        
        # Add top bar container to main layout
        main_layout.addWidget(top_bar_container)
        
        # Scroll area for the grid of icons
        self.games_scroll = SmoothScrollArea()
        self.games_scroll.setObjectName("gamesScrollArea")
        self.games_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.games_scroll.setWidgetResizable(True)
        self.games_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.games_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Enable drag & drop for .exe files
        self.games_scroll.setAcceptDrops(True)
        self.games_scroll.dragEnterEvent = self._on_drag_enter
        self.games_scroll.dropEvent = self._on_drop
        
        # Apply message filter to games_scroll widget for UAC drag-drop
        self._enable_drag_drop_for_widget(self.games_scroll)
        
        # Container widget that will hold the grid
        self.games_container = QWidget()
        self.games_container.setObjectName("gamesContainer")
        self.games_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Main layout for the container
        container_layout = QVBoxLayout(self.games_container)
        container_layout.setContentsMargins(10, 5, 10, 0)
        container_layout.setSpacing(10)
        
        # Sort controls bar (inside scroll area, above grid)
        self.sort_bar = QWidget()
        self.sort_bar.setObjectName("sortBar")
        self.sort_bar.setFixedHeight(60)  # Taller to prevent button cutoff
        sort_bar_layout = QHBoxLayout(self.sort_bar)
        sort_bar_layout.setContentsMargins(15, 10, 15, 10)  # Extra top/bottom margin to center buttons vertically
        sort_bar_layout.setSpacing(15)
        sort_bar_layout.setAlignment(Qt.AlignVCenter)
        
        # Sort label
        self.sort_label = QLabel("Sort:")
        self.sort_label.setObjectName("sortBarLabel")
        self.sort_label.setStyleSheet("font-size: 13px; color: #888888;")
        
        # Sort dropdown
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("SortComboBox")
        self.sort_combo.addItems(["Name (A-Z)", "Name (Z-A)", "Last Played", "Play Time", "Date Added"])
        self.sort_combo.setFixedWidth(140)
        self.sort_combo.setFixedHeight(30)
        self.sort_combo.currentTextChanged.connect(self.on_sort_changed)
        self.sort_combo.setStyleSheet("""
            QComboBox {
                background: rgba(30, 30, 30, 0.9);
                border: 1px solid #FF5B06;
                border-radius: 5px;
                padding: 3px 10px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e;
                border: 1px solid #FF5B06;
                selection-background-color: #FF5B06;
                font-size: 12px;
            }
        """)
        
        # Filter dropdown (All / Games / Utilities)
        self.filter_label = QLabel("Filter:")
        self.filter_label.setObjectName("sortBarLabel")
        self.filter_label.setStyleSheet("font-size: 13px; color: #888888;")
        
        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("FilterComboBox")
        self.filter_combo.addItems(["All", "Games", "Utilities"])
        self.filter_combo.setFixedWidth(100)
        self.filter_combo.setFixedHeight(30)
        self.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background: rgba(30, 30, 30, 0.9);
                border: 1px solid #FF5B06;
                border-radius: 5px;
                padding: 3px 10px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e;
                border: 1px solid #FF5B06;
                selection-background-color: #FF5B06;
                font-size: 12px;
            }
        """)
        
        # Game counter label
        self.game_counter = QLabel("0 Application")
        self.game_counter.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #888888;
                padding: 0 10px;
                background: transparent;
            }
        """)
        
        sort_bar_layout.addWidget(self.sort_label)
        sort_bar_layout.addWidget(self.sort_combo)
        sort_bar_layout.addWidget(self.filter_label)
        sort_bar_layout.addWidget(self.filter_combo)
        sort_bar_layout.addWidget(self.game_counter)
        sort_bar_layout.addStretch()
        
        # Discord Rich Presence toggle - TOP PRIORITY, placed first with prominent styling
        self.discord_enabled = self.settings.get("discord_rpc", False)
        self.discord_rpc = None  # Will be set when connected
        self.discord_btn = QPushButton()
        self.discord_btn.setObjectName("DiscordButton")
        self.discord_btn.setFixedSize(130, 30)  # Match other button heights
        
        # Check if Discord is installed on the system
        self._discord_installed = self._check_discord_installed()
        
        if self._discord_installed:
            self.update_discord_button_text()
            self.discord_btn.clicked.connect(self.toggle_discord_rpc)
            
            # Auto-connect to Discord IMMEDIATELY if enabled (top priority)
            if self.discord_enabled:
                QTimer.singleShot(100, self.connect_and_check_running_games)  # Faster connection
            self.discord_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5865F2, stop:1 #7289DA);
                    border: 2px solid #5865F2;
                    border-radius: 6px;
                    padding: 3px 12px 1px 12px;
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7289DA, stop:1 #99AAF2);
                    border: 2px solid #7289DA;
                }
                QPushButton:pressed {
                    background: #4752C4;
                }
            """)
        else:
            # Discord not installed - disable button
            self.discord_btn.setText("Discord: N/A")
            self.discord_btn.setEnabled(False)
            self.discord_btn.setToolTip("Discord is not installed on this system")
            self.discord_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(50, 50, 50, 0.5);
                    border: 2px solid #555;
                    border-radius: 6px;
                    padding: 3px 12px 1px 12px;
                    color: #666;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        sort_bar_layout.addWidget(self.discord_btn, 0, Qt.AlignVCenter)
        
        # Statistics button (on the right)
        stats_btn = AnimatedButton("Stats")
        stats_btn.setObjectName("StatsBtn")
        stats_btn.setFixedSize(80, 30)
        stats_btn.setHoverGradient(['#F443A2', '#FE5500', '#FE0800', '#FFAB00'])  # Game panel gradient
        stats_btn.clicked.connect(lambda: self.show_statistics_dashboard())
        stats_btn.setStyleSheet("""
            QPushButton {
                background: rgba(30, 30, 30, 0.9);
                border: 1px solid #FF5B06;
                border-radius: 5px;
                padding: 3px 10px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.3);
            }
        """)
        sort_bar_layout.addWidget(stats_btn, 0, Qt.AlignVCenter)
        
        # End Game button (for force-killing currently running game)
        self.end_game_btn = AnimatedButton("End Game")
        self.end_game_btn.setFixedSize(100, 30)
        self.end_game_btn.setHoverGradient(['#FF3333', '#FF6666'])  # Red theme for end game
        self.end_game_btn.clicked.connect(self.force_end_game)
        self.end_game_btn.setStyleSheet("""
            QPushButton {
                background: rgba(30, 30, 30, 0.9);
                border: 1px solid #FF3333;
                border-radius: 5px;
                padding: 3px 10px;
                color: #FF6666;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 51, 51, 0.3);
            }
        """)
        self.end_game_btn.hide()  # Hidden by default, shown when a game is running
        sort_bar_layout.addWidget(self.end_game_btn, 0, Qt.AlignVCenter)
        
        # Add sort bar to container
        container_layout.addWidget(self.sort_bar)
        
        # Recently Played section (horizontal row of last 5 played games)
        self.recently_played_widget = QWidget()
        self.recently_played_widget.setObjectName("recentlyPlayedWidget")
        self.recently_played_layout = QHBoxLayout(self.recently_played_widget)
        self.recently_played_layout.setContentsMargins(15, 8, 15, 10)  # Left/right/top/bottom margins
        self.recently_played_layout.setSpacing(15)
        self.recently_played_layout.setAlignment(Qt.AlignLeft)
        container_layout.addWidget(self.recently_played_widget)
        
        # Grid layout for icons
        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.grid.setContentsMargins(0, 0, 0, 0)
        
        # Add grid to container layout
        container_layout.addLayout(self.grid)
        container_layout.addStretch()  # Push everything to the top
        
        # Set container as the scroll area's widget
        self.games_scroll.setWidget(self.games_container)
        self.games_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Add scroll area to main layout with stretch factor to take remaining space
        main_layout.addWidget(self.games_scroll, 1)
        
        # Set stretch factors to ensure top bar stays fixed and scroll area takes remaining space
        main_layout.setStretch(0, 0)  # Top bar (fixed height)
        main_layout.setStretch(1, 1)  # Scroll area (takes remaining space)

        self.update_grid_size()
        self.refresh()
        
        # Re-apply theme now that games_container exists (for background image)
        self.apply_theme()
        
        # Setup music panel after all other UI is initialized
        self._setup_music_panel()
        
        # Setup CPU control panel (panel 2)
        self._setup_cpu_panel()
        
        # Setup Crosshair panel (panel 3)
        self._setup_crosshair_panel()
        
        # Setup Macro panel (panel 4)
        import time as _t; _macro_t = _t.perf_counter()
        self._setup_macro_panel()
        print(f"[TIMING] _setup_macro_panel TOTAL: {(_t.perf_counter()-_macro_t)*1000:.0f}ms")
        
        # Setup background game detection (scans every 5 seconds)
        self.game_scanner_timer = QTimer(self)
        self.game_scanner_timer.timeout.connect(self._scan_for_running_games)
        self.game_scanner_timer.start(5000)  # 5 seconds
        
        # Install event filter for music panel keyboard shortcuts
        QApplication.instance().installEventFilter(self)
        print(f"[TIMING] GameLauncher.__init__ DONE")

    def open_launcher_youtube(self):
        QDesktopServices.openUrl(QUrl("https://rickrolled.com/"))

    def apply_theme(self):
        """Apply theme colors and background image"""
        # Use default theme colors
        colors = DEFAULT_SETTINGS["theme_colors"]
        
        bg_image = self.settings.get("background_image", "")
        
        primary = colors.get("primary", "#FF5B06")
        secondary = colors.get("secondary", "#FDA903")
        bg_dark = colors.get("background_dark", "#010101")
        bg_light = colors.get("background_light", "#1D1D1C")
        text = colors.get("text", "#e0e0e0")
        
        # If no background image, use white font for better visibility on dark theme
        if not bg_image or not bg_image.strip():
            self._game_text_color = "#FFFFFF"
            self._sortbar_label_color = "#FFFFFF"
        else:
            self._game_text_color = text
            self._sortbar_label_color = "#888888"
        
        # Convert hex to rgba for transparency effects
        def hex_to_rgba(hex_color, alpha=1.0):
            hex_color = hex_color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return f"rgba({r}, {g}, {b}, {alpha})"
        
        # Use simple gradient background (no image in stylesheet - causes memory issues)
        # Background image will be handled separately via paintEvent if needed
        bg_style = f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bg_dark}, stop:0.5 {bg_light}, stop:1 {bg_dark});
        """
        
        # Generate full stylesheet
        stylesheet = f"""
            QWidget {{
                {bg_style}
                color: {text};
                font-family: 'Orbitron', 'Segoe UI', Arial;
            }}
            QPushButton {{
                border: 2px solid {hex_to_rgba(primary, 0.4)};
                padding: 8px 16px;
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {hex_to_rgba(bg_light, 0.9)}, stop:1 {hex_to_rgba(bg_dark, 0.95)});
                color: {text};
                min-width: 32px;
                min-height: 32px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {hex_to_rgba(primary, 0.3)}, stop:1 {hex_to_rgba(secondary, 0.4)});
                border: 2px solid {hex_to_rgba(secondary, 0.8)};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {hex_to_rgba(secondary, 0.5)}, stop:1 {hex_to_rgba(primary, 0.6)});
                border: 2px solid {hex_to_rgba(secondary, 0.9)};
            }}
            QPushButton#gameBtn {{
                border: none;
                padding: 0;
                background: transparent;
            }}
            QPushButton#gameBtn:hover {{
                border: none;
            }}
            QPushButton#gameBtn:pressed {{
                border: none;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {hex_to_rgba(bg_dark, 0.8)};
                width: 16px;
                border-radius: 8px;
                margin: 4px;
                border: 1px solid {hex_to_rgba(primary, 0.3)};
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {primary}, stop:0.5 {secondary}, stop:1 {primary});
                border-radius: 7px;
                min-height: 40px;
                border: 2px solid {hex_to_rgba(secondary, 0.8)};
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {secondary}, stop:0.5 #FFFF00, stop:1 {secondary});
                border: 2px solid #FFFF00;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background: {hex_to_rgba(bg_dark, 0.8)};
                height: 16px;
                border-radius: 8px;
                margin: 4px;
                border: 1px solid {hex_to_rgba(primary, 0.3)};
            }}
            QScrollBar::handle:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {primary}, stop:0.5 {secondary}, stop:1 {primary});
                border-radius: 7px;
                min-width: 40px;
                border: 2px solid {hex_to_rgba(secondary, 0.8)};
            }}
            QScrollBar::handle:horizontal:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {secondary}, stop:0.5 #FFFF00, stop:1 {secondary});
                border: 2px solid #FFFF00;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {hex_to_rgba(bg_light, 0.7)};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {primary}, stop:1 {secondary});
                width: 20px;
                margin: -7px 0;
                border-radius: 10px;
                border: 2px solid {hex_to_rgba(secondary, 0.5)};
            }}
            QSlider::handle:horizontal:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {secondary}, stop:1 {primary});
            }}
            QLabel {{
                background: transparent;
            }}
            QLineEdit {{
                background: {hex_to_rgba(bg_light, 0.8)};
                border: 1px solid {hex_to_rgba(primary, 0.5)};
                border-radius: 8px;
                padding: 8px;
                color: {text};
            }}
            QLineEdit:focus {{
                border: 2px solid {primary};
            }}
        """
        
        self.setStyleSheet(stylesheet)
        
        # Apply background image to games container only
        bg_image = self.settings.get("background_image", "")
        if bg_image and os.path.exists(bg_image):
            # Get the background mode
            mode = self.settings.get("background_mode", "fill")
            print(f"[Background] Using mode: {mode}, image: {os.path.basename(bg_image)}")
            
            # Pre-scale image to fit container properly (Qt CSS doesn't support background-size)
            try:
                # Get container size - use window size as fallback for reliable sizing
                container_width = 1200  # Larger default
                container_height = 800
                if hasattr(self, 'games_scroll') and self.games_scroll.width() > 100:
                    container_width = self.games_scroll.width()
                    container_height = self.games_scroll.height()
                else:
                    # Use window size as fallback
                    container_width = max(self.width(), 1200)
                    container_height = max(self.height(), 800)
                
                print(f"[Background] Container size: {container_width}x{container_height}")
                
                # Load and scale the image
                pixmap = QPixmap(bg_image)
                if not pixmap.isNull():
                    orig_width = pixmap.width()
                    orig_height = pixmap.height()
                    
                    if mode == "fill":
                        # Cover: scale to fill, may crop
                        scaled = pixmap.scaled(
                            container_width, container_height,
                            Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation
                        )
                    elif mode == "fit":
                        # Contain: scale to fit, may have letterbox
                        scaled = pixmap.scaled(
                            container_width, container_height,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                    elif mode == "stretch":
                        # Stretch: ignore aspect ratio
                        scaled = pixmap.scaled(
                            container_width, container_height,
                            Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation
                        )
                    elif mode == "tile":
                        # Tile: use original size
                        scaled = pixmap
                    elif mode == "center":
                        # Center: use original but limit to reasonable size
                        if orig_width > container_width * 1.5 or orig_height > container_height * 1.5:
                            scaled = pixmap.scaled(
                                container_width, container_height,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                        else:
                            scaled = pixmap
                    else:  # span
                        scaled = pixmap.scaled(
                            container_width, container_height,
                            Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation
                        )
                    
                    # Save scaled image to temp file
                    temp_dir = os.path.join(os.environ.get('TEMP', '/tmp'), 'helxaid_bg')
                    os.makedirs(temp_dir, exist_ok=True)
                    scaled_path = os.path.join(temp_dir, 'background_scaled.png')
                    scaled.save(scaled_path, 'PNG')
                    
                    # Calculate average brightness for adaptive text color
                    try:
                        img = scaled.toImage()
                        if not img.isNull():
                            # More sophisticated brightness detection
                            # Focus on upper portion where game names appear
                            brightness_values = []
                            step = max(1, min(img.width(), img.height()) // 30)  # More samples
                            
                            # Sample upper half more heavily (weight 2x)
                            for x in range(0, img.width(), step):
                                # Upper 40% (where text typically is)
                                for y in range(0, int(img.height() * 0.4), step):
                                    color = img.pixelColor(x, y)
                                    lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                                    brightness_values.append(lum)
                                    brightness_values.append(lum)  # Double weight for upper area
                                
                                # Lower 60% (less important)
                                for y in range(int(img.height() * 0.4), img.height(), step):
                                    color = img.pixelColor(x, y)
                                    lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                                    brightness_values.append(lum)
                            
                            if brightness_values:
                                avg_brightness = sum(brightness_values) / len(brightness_values)
                                # Always use white text — adjust the dark shadow behind title instead
                                self._game_text_color = "#FFFFFF"
                                if avg_brightness > 140:
                                    # Bright wallpaper: use more opaque dark bg so white text stays readable
                                    self._title_bg_opacity = 0.25
                                else:
                                    # Dark wallpaper: lighter shadow is enough
                                    self._title_bg_opacity = 0.50
                                self._has_bg_image = True  # Flag for bold text
                                print(f"[Background] Brightness: {avg_brightness:.0f} (samples: {len(brightness_values)}), text color: {self._game_text_color}")
                    except Exception as e:
                        self._game_text_color = "#e0e0e0"  # Default light
                        print(f"[Background] Brightness calc error: {e}")
                    
                    bg_image_css = bg_image.replace("\\", "/")
                    scaled_image_css = scaled_path.replace("\\", "/")
                    
                    # Different CSS for different modes
                    if mode == "fill" or mode == "stretch":
                        # Fill/Stretch: use border-image to fill container completely
                        # border-image stretches to fill the entire container
                        container_style = f"""
                            QWidget#gamesContainer {{
                                border-image: url("{bg_image_css}") 0 0 0 0 stretch stretch;
                                border-radius: 10px;
                            }}
                        """
                    elif mode == "tile":
                        # Use scaled image with repeat
                        container_style = f"""
                            QWidget#gamesContainer {{
                                background-image: url("{bg_image_css}");
                                background-repeat: repeat;
                                border-radius: 10px;
                            }}
                        """
                    elif mode == "center":
                        # Use scaled image centered, no repeat
                        container_style = f"""
                            QWidget#gamesContainer {{
                                background-image: url("{scaled_image_css}");
                                background-position: center;
                                background-repeat: no-repeat;
                                border-radius: 10px;
                            }}
                        """
                    else:  # fit - use pre-scaled image
                        container_style = f"""
                            QWidget#gamesContainer {{
                                background-image: url("{scaled_image_css}");
                                background-position: center;
                                background-repeat: no-repeat;
                                border-radius: 10px;
                            }}
                        """
                    
                    # Style for recently played section - semi-transparent, no border
                    recently_played_style = """
                        QWidget#recentlyPlayedWidget {
                            background: rgba(0, 0, 0, 0.5);
                            border: none;
                            border-radius: 12px;
                            padding: 8px;
                        }
                    """
                    
                    # Style for sort bar - semi-transparent, no border
                    sort_bar_style = """
                        QWidget#sortBar {
                            background: rgba(0, 0, 0, 0.5);
                            border: none;
                            border-radius: 12px;
                            padding: 0 8px;
                        }
                    """
                    
                    # Apply to games container
                    if hasattr(self, 'games_container'):
                        self.games_container.setStyleSheet(container_style)
                    
                    # Apply to recently played
                    if hasattr(self, 'recently_played_widget'):
                        self.recently_played_widget.setStyleSheet(recently_played_style)
                    
                    # Apply to sort bar
                    if hasattr(self, 'sort_bar'):
                        self.sort_bar.setStyleSheet(sort_bar_style)
                    
                    # Apply adaptive text color to sort bar labels
                    label_style = f"font-size: 13px; color: {self._game_text_color}; background: transparent;"
                    if hasattr(self, 'sort_label'):
                        self.sort_label.setStyleSheet(label_style)
                    if hasattr(self, 'filter_label'):
                        self.filter_label.setStyleSheet(label_style)
                    if hasattr(self, 'game_counter'):
                        self.game_counter.setStyleSheet(f"font-size: 13px; color: {self._game_text_color}; padding: 0 10px; background: transparent;")
                        
            except Exception as e:
                print(f"[Background] Error scaling image: {e}")
        else:
            # Clear background styles when no image
            self._has_bg_image = False  # Reset flag so title backgrounds are removed
            self._title_bg_opacity = 0  # No opacity needed
            
            if hasattr(self, 'games_container'):
                self.games_container.setStyleSheet("")
            if hasattr(self, 'recently_played_widget'):
                self.recently_played_widget.setStyleSheet("")
            if hasattr(self, 'sort_bar'):
                self.sort_bar.setStyleSheet("")
            
            # Apply white text color to sortBar labels when no background image
            label_style = f"font-size: 13px; color: {self._sortbar_label_color}; background: transparent;"
            if hasattr(self, 'sort_label'):
                self.sort_label.setStyleSheet(label_style)
            if hasattr(self, 'filter_label'):
                self.filter_label.setStyleSheet(label_style)
            if hasattr(self, 'game_counter'):
                self.game_counter.setStyleSheet(f"font-size: 13px; color: {self._sortbar_label_color}; padding: 0 10px; background: transparent;")


    # =============================================
    # TASKBAR ICON HELPER
    # =============================================
    def _apply_taskbar_icon(self):
        """Apply taskbar icon using win32gui WM_SETICON message."""
        print("[Icon] _apply_taskbar_icon called")
        if not WINDOWS_API_AVAILABLE:
            print("[Icon] WINDOWS_API not available")
            return
        if not hasattr(self, '_hicon') or not self._hicon:
            print("[Icon] No _hicon available")
            return
        
        try:
            # Get window handle
            hwnd = int(self.winId())
            print(f"[Icon] Window handle: {hwnd}, hicon: {self._hicon}")
            
            # Send WM_SETICON message
            WM_SETICON = 0x0080
            ICON_BIG = 1
            ICON_SMALL = 0
            
            result1 = win32gui.SendMessage(hwnd, WM_SETICON, ICON_BIG, self._hicon)
            result2 = win32gui.SendMessage(hwnd, WM_SETICON, ICON_SMALL, self._hicon)
            print(f"[Icon] WM_SETICON results: big={result1}, small={result2}")
        except Exception as e:
            print(f"[Icon] WM_SETICON failed: {e}")

    # =============================================
    # SIDEBAR NAVIGATION METHODS
    # =============================================
    def switch_panel(self, index: int):
        """Switch content panel based on sidebar selection with iOS-style animation."""
        # Lazy-load Hardware panel at index 5
        if index == 5 and not hasattr(self, 'hardware_panel'):
            self._setup_hardware_panel()
        
        self.content_stack.setCurrentIndex(index)
        
        # Clear focus from sidebar buttons so keyboard shortcuts work
        if index == 1:  # Music panel (index 1)
            self.setFocus()  # Set focus to main window
        
        # Check for RyzenAdj when switching to CPU panel
        if index == 2:  # CPU Controller panel
            try:
                from integrations.cpu_controller import is_ryzenadj_available
                from integrations.tools_downloader import ensure_ryzenadj
                
                # Check if RyzenAdj is available now
                ryzenadj_available = is_ryzenadj_available()
                
                # If RyzenAdj not available, prompt download
                if not ryzenadj_available:
                    # Show download prompt
                    if ensure_ryzenadj(self):
                        # Download successful, reload panel
                        self._reload_cpu_panel()
                        self._cpu_panel_has_ryzenadj = True
                        return
                
                # Check if panel needs reload (status changed)
                panel_needs_reload = hasattr(self, '_cpu_panel_has_ryzenadj') and self._cpu_panel_has_ryzenadj != ryzenadj_available
                
                if panel_needs_reload:
                    # Reload the panel with updated RyzenAdj status
                    self._reload_cpu_panel()
                    self._cpu_panel_has_ryzenadj = ryzenadj_available
                    return  # Already switched in _reload_cpu_panel
                
                # Track current panel state
                self._cpu_panel_has_ryzenadj = ryzenadj_available
                
            except ImportError:
                pass
        
        # Update sidebar button styles to show active state
        buttons = [self.home_btn, self.music_nav_btn, self.cpu_nav_btn, self.crosshair_nav_btn, self.macro_nav_btn, self.hardware_nav_btn]
        
        # Stop existing gradient animation timer if any
        if hasattr(self, '_nav_gradient_timer') and self._nav_gradient_timer:
            self._nav_gradient_timer.stop()
            self._nav_gradient_timer = None
        
        for i, btn in enumerate(buttons):
            if i == index:
                # Start animated gradient for active button
                self._active_nav_btn = btn
                self._nav_gradient_offset = 0.0
                
                # Create timer for gradient animation
                self._nav_gradient_timer = QTimer(self)
                self._nav_gradient_timer.timeout.connect(self._update_nav_gradient)
                self._nav_gradient_timer.start(80)  # 80ms = 12.5fps, less CPU overhead
                
                # Apply initial gradient
                self._update_nav_gradient()
            else:
                btn.setStyleSheet("")

    def keyPressEvent(self, event):
        """Handle global keyboard shortcuts."""
        from PySide6.QtCore import Qt
        
        # F11 or Alt+Return: Toggle Fullscreen
        if (event.key() == Qt.Key_F11 and event.modifiers() == Qt.NoModifier) or \
           (event.key() == Qt.Key_Return and event.modifiers() == Qt.AltModifier):
            self.toggle_fullscreen()
            return
        
        # Ctrl+F11: Toggle Debug Console (prevent conflict with Fullscreen)
        if event.key() == Qt.Key_F11 and event.modifiers() == Qt.ControlModifier:
            try:
                from DebugConsoleWidget import toggle_debug_console
                toggle_debug_console()
            except Exception as e:
                print(f"[Debug] Error toggling console: {e}")
            return
        
        # NOTE: Hardware media keys (Play/Pause, Next, Previous, Stop)
        # are handled exclusively by MediaKeyService's global keyboard
        # hook. Do NOT handle them here to avoid double-fire since the
        # non-exclusive hook forwards events to Qt as well.
        
        # Music panel shortcuts (when on music page - panel index 2)
        if hasattr(self, 'content_stack') and self.content_stack.currentIndex() == 2:
            if hasattr(self, 'audio_player') and self.audio_player:
                # Check if a button/input has focus (don't override their behavior)
                from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit, QComboBox, QSpinBox
                focus_widget = QApplication.focusWidget()
                is_interactive = isinstance(focus_widget, (QPushButton, QLineEdit, QComboBox, QSpinBox))
                
                # Space: Toggle play/pause (only if no button focused)
                if event.key() == Qt.Key_Space and not is_interactive:
                    self.audio_player.toggle_play()
                    return
                # P: Previous track (only if not typing in input)
                elif event.key() == Qt.Key_P and not isinstance(focus_widget, (QLineEdit,)):
                    self.audio_player.prev_track()
                    return
                # N: Next track (only if not typing in input)
                elif event.key() == Qt.Key_N and not isinstance(focus_widget, (QLineEdit,)):
                    self.audio_player.next_track()
                    return
        
        # Ctrl+F: Focus search
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_F:
            self.search_input.setFocus()
            self.search_input.selectAll()
            return
        
        # Only handle navigation if we have games
        if not self.game_buttons:
            super().keyPressEvent(event)
            return
        
        # Calculate columns for navigation
        tile_size = self.grid_size + 80
        grid_spacing = 20
        scrollbar_width = 20
        available_width = self.width() - scrollbar_width - grid_spacing
        num_columns = max(1, int((available_width + grid_spacing) / (tile_size + grid_spacing)))
        
        # Arrow key navigation
        if event.key() == Qt.Key_Left:
            if self.selected_game_index > 0:
                self.select_game(self.selected_game_index - 1)
        elif event.key() == Qt.Key_Right:
            if self.selected_game_index < len(self.game_buttons) - 1:
                self.select_game(self.selected_game_index + 1)
        elif event.key() == Qt.Key_Up:
            new_idx = self.selected_game_index - num_columns
            if new_idx >= 0:
                self.select_game(new_idx)
        elif event.key() == Qt.Key_Down:
            new_idx = self.selected_game_index + num_columns
            if new_idx < len(self.game_buttons):
                self.select_game(new_idx)
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Launch selected game
            if 0 <= self.selected_game_index < len(self.game_buttons):
                btn, game = self.game_buttons[self.selected_game_index]
                self.launch_game(game.get("exe", ""))
        elif event.key() == Qt.Key_Delete:
            # Delete hovered game (priority) or selected game
            hovered = getattr(self, '_hovered_game', None)
            if hovered:
                self.delete_game(hovered)
            elif 0 <= self.selected_game_index < len(self.game_buttons):
                btn, game = self.game_buttons[self.selected_game_index]
                self.delete_game(game)
        elif event.key() == Qt.Key_F12:
            # Component Inspector - show info about widget under cursor
            pos = self.mapFromGlobal(self.cursor().pos())
            widget = self.childAt(pos)
            if widget:
                # Build parent hierarchy
                hierarchy = []
                w = widget
                while w:
                    name = w.objectName() or "(no name)"
                    hierarchy.append(f"{w.__class__.__name__}#{name}")
                    w = w.parent()
                
                # Detect component type
                component_name = "Unknown"
                code_ref = ""
                widget_type = widget.__class__.__name__
                
                # Check for game buttons
                if widget_type == "AnimatedGameButton":
                    for idx, (btn, game) in enumerate(self.game_buttons):
                        if btn == widget:
                            component_name = f"🎮 Game Button: \"{game.get('name', 'Unknown')}\""
                            code_ref = f"self.game_buttons[{idx}]"
                            break
                elif widget_type == "QPushButton":
                    btn_text = widget.text() if hasattr(widget, 'text') else ""
                    if btn_text:
                        component_name = f"Button: \"{btn_text}\""
                    if widget == getattr(self, 'settings_btn', None):
                        code_ref = "self.settings_btn"
                    elif widget == getattr(self, 'add_btn', None):
                        code_ref = "self.add_btn"
                    elif widget == getattr(self, 'refresh_btn', None):
                        code_ref = "self.refresh_btn"
                    elif widget == getattr(self, 'discord_btn', None):
                        code_ref = "self.discord_btn"
                elif widget_type == "QLineEdit":
                    if widget == getattr(self, 'search_input', None):
                        component_name = "Search Input"
                        code_ref = "self.search_input"
                elif widget_type == "QComboBox":
                    if widget == getattr(self, 'sort_combo', None):
                        component_name = "Sort Dropdown"
                        code_ref = "self.sort_combo"
                    elif widget == getattr(self, 'filter_combo', None):
                        component_name = "Filter Dropdown"
                        code_ref = "self.filter_combo"
                elif widget_type == "QLabel":
                    label_text = widget.text() if hasattr(widget, 'text') else ""
                    if label_text:
                        component_name = f"Label: \"{label_text[:30]}...\""
                elif widget.objectName() == "gamesContainer":
                    component_name = "Games Container (Grid Background)"
                    code_ref = "self.games_container"
                elif widget.objectName() == "gamesScrollArea":
                    component_name = "Games Scroll Area"
                    code_ref = "self.games_scroll"
                
                info = f"""Component Inspector

Component: {component_name}
Widget Type: {widget_type}
Object Name: {widget.objectName() or '(not set)'}
Size: {widget.width()} x {widget.height()}
{f'Code Reference: {code_ref}' if code_ref else ''}

Hierarchy (child → parent):
{chr(10).join(f"  {i}. {h}" for i, h in enumerate(hierarchy[:5]))}

Stylesheet Selector:
  {widget_type}#{widget.objectName() if widget.objectName() else '<set objectName first>'}
"""
                QMessageBox.information(self, "Component Inspector (F12)", info)
            else:
                QMessageBox.information(self, "Component Inspector", "No widget under cursor")
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
            self.settings["window_fullscreen"] = False
            # Restore previous geometry if available
            geometry = self.settings.get("window_geometry")
            if geometry and len(geometry) == 4:
                self.move(geometry[0], geometry[1])
                self.resize(geometry[2], geometry[3])
        else:
            # Save normal geometry if available so we don't save maximized size
            geom = self.normalGeometry()
            if geom.width() > 0 and geom.height() > 0:
                self.settings["window_geometry"] = [geom.x(), geom.y(), geom.width(), geom.height()]
            else:
                self.settings["window_geometry"] = [self.x(), self.y(), self.width(), self.height()]
            self.showFullScreen()
            self.settings["window_fullscreen"] = True
        save_settings(self.settings)
    
    def _update_nav_gradient(self):
        """Update the gradient offset for animated nav button."""
        if not hasattr(self, '_active_nav_btn') or not self._active_nav_btn:
            return
        
        # OMEN gradient colors (extended for seamless loop)
        colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']
        
        # Shift offset (0.0 to 1.0) - slower step for smoother animation
        self._nav_gradient_offset += 0.04
        if self._nav_gradient_offset >= 1.0:
            self._nav_gradient_offset = 0.0
        
        offset = self._nav_gradient_offset
        
        # Build gradient with offset positions
        stops = []
        num_colors = len(colors)
        for i, color in enumerate(colors):
            base_pos = i / (num_colors - 1)
            shifted_pos = (base_pos + offset) % 1.0
            stops.append((shifted_pos, color))
        
        # Sort by position for valid gradient
        stops.sort(key=lambda x: x[0])
        
        # Build gradient string
        gradient_stops = ', '.join([f"stop:{pos:.3f} {color}" for pos, color in stops])
        
        self._active_nav_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-left: 4px solid qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    {gradient_stops});
                border-radius: 0px;
                padding-left: 4px;
                font-size: 24px;
            }}
        """)
    
    def _start_pending_video(self):
        """Start the pending video background after panel switch animation."""
        if hasattr(self, '_pending_video_path') and self._pending_video_path:
            if hasattr(self, 'music_panel') and hasattr(self, 'content_stack'):
                # Only start if still on music panel
                if self.content_stack.currentWidget() == self.music_panel:
                    self.music_panel.set_video(self._pending_video_path)
                    print(f"[Music] Started queued VIDEO: {os.path.basename(self._pending_video_path)}")
    
    def _setup_music_panel(self):
        """Setup the music player panel using native Qt MusicPanelWidget."""
        from MusicPanelWidget import MusicPanelWidget
        
        # Create native Qt music panel
        self.music_panel = MusicPanelWidget()
        self.music_panel.setObjectName("musicPanel")
        
        # Store reference to the internal player for taskbar controls
        self._music_player = self.music_panel._player
        self._audio_output = self.music_panel._audio_output
        
        # Connect player signals for taskbar integration
        # Use music_panel's signal instead of internal player (handles crossfade correctly)
        self.music_panel.playbackStateChanged.connect(self._update_taskbar_play_state)
        
        # Add to content stack (index 1 = music panel)
        self.content_stack.addWidget(self.music_panel)
        
        # Initialize taskbar thumbnail toolbar reference (actual setup in showEvent)
        self.taskbar_toolbar = None
        
        # For backward compatibility with existing code that references audio_player
        self.audio_player = None  # Deprecated - use music_panel directly
        
        print("[Music] Native Qt MusicPanelWidget initialized")
    
    def _taskbar_prev(self):
        """Taskbar button: Previous track."""
        if hasattr(self, 'music_panel'):
            self.music_panel._prev_track()
    
    def _taskbar_playpause(self):
        """Taskbar button: Play/Pause."""
        if hasattr(self, 'music_panel'):
            self.music_panel._toggle_play()
    
    def _taskbar_next(self):
        """Taskbar button: Next track."""
        if hasattr(self, 'music_panel'):
            self.music_panel._next_track()
    
    def _update_taskbar_play_state(self, state):
        """Update taskbar button icon based on playback state."""
        if self.taskbar_toolbar:
            from PySide6.QtMultimedia import QMediaPlayer
            is_playing = (state == QMediaPlayer.PlayingState)
            self.taskbar_toolbar.update_play_state(is_playing)
    
    def nativeEvent(self, eventType, message):
        """Handle Windows native events for taskbar button clicks."""
        if eventType == b"windows_generic_MSG" or eventType == "windows_generic_MSG":
            try:
                import struct
                # Parse Windows message
                msg = int.from_bytes(message, byteorder='little')
                # WM_COMMAND = 0x0111
                # Extract message ID from first 4 bytes
                msgstruct = struct.unpack('IHHllll', message[:24])
                msg_id = msgstruct[0]
                wparam = msgstruct[1]
                
                if msg_id == 0x0111:  # WM_COMMAND
                    # Extract LOWORD(wParam) which contains button ID
                    button_id = wparam & 0xFFFF
                    if self.taskbar_toolbar and button_id in [BUTTON_PREV, BUTTON_PLAYPAUSE, BUTTON_NEXT]:
                        self.taskbar_toolbar.handle_button_click(button_id)
                        return True, 0
            except:
                pass
        
        return super().nativeEvent(eventType, message)
    
    def _on_music_panel_loaded(self, success):
        """Called when HTML music panel finishes loading."""
        if success and hasattr(self, 'music_bridge'):
            # Get playlist name from folder
            if self.audio_player and hasattr(self.audio_player, 'playlist') and self.audio_player.playlist:
                folder = os.path.dirname(self.audio_player.playlist[0])
                name = os.path.basename(folder)
                self.music_bridge.set_playlist_name(name)
            else:
                self.music_bridge.requestPlaylist()
    

    def _setup_cpu_panel(self):
        """Setup the CPU control panel with modern card-based design."""
        self.cpu_panel = QWidget()
        self.cpu_panel.setObjectName("cpuPanel")
        layout = QVBoxLayout(self.cpu_panel)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(24)
        
        # Check if RyzenAdj is available - if not, show download prompt
        if not is_ryzenadj_available():
            layout.addStretch()
            
            no_ryzenadj_label = QLabel("RyzenAdj Not Found")
            no_ryzenadj_label.setStyleSheet("font-size: 24px; color: #FDA903; font-weight: bold;")
            no_ryzenadj_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_ryzenadj_label)
            
            info_label = QLabel("CPU Control requires RyzenAdj.\nClick below to download and install automatically.")
            info_label.setStyleSheet("font-size: 14px; color: #9DB2BF;")
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setWordWrap(True)
            layout.addWidget(info_label)
            
            # Auto-download button
            def do_download():
                try:
                    from integrations.tools_downloader import download_ryzenadj, RYZENADJ_DIR
                    from PySide6.QtWidgets import QProgressDialog, QMessageBox
                    
                    # Show progress dialog
                    progress = QProgressDialog("Downloading RyzenAdj...", "Cancel", 0, 100, self)
                    progress.setWindowTitle("Installing RyzenAdj")
                    progress.setWindowModality(Qt.WindowModal)
                    progress.setMinimumDuration(0)
                    progress.show()
                    
                    def update_progress(downloaded: int, total: int):
                        if progress.wasCanceled():
                            return
                        percent = int((downloaded / total) * 100) if total > 0 else 0
                        progress.setValue(percent)
                        progress.setLabelText(f"Downloading... {downloaded // 1024} KB / {total // 1024} KB")
                    
                    success, error = download_ryzenadj(update_progress)
                    progress.close()
                    
                    if success:
                        QMessageBox.information(self, "Download Complete", 
                            "RyzenAdj installed successfully!\n\nReloading CPU Controller...")
                        # Reload the CPU panel
                        self._reload_cpu_panel()
                    else:
                        QMessageBox.critical(self, "Download Failed", f"Failed to install RyzenAdj:\n{error}")
                except Exception as e:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Error", f"Download error: {e}")
            
            download_btn = AnimatedButton("Download RyzenAdj (Auto-Install)")
            download_btn.setFixedSize(300, 50)
            download_btn.setCursor(Qt.PointingHandCursor)
            download_btn.setStyleSheet("QPushButton { background: #526D82; color: #DDE6ED; border: none; border-radius: 12px; font-size: 14px; font-weight: 600; } QPushButton:hover { background: #9DB2BF; color: #27374D; }")
            download_btn.clicked.connect(do_download)
            
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.addStretch()
            btn_layout.addWidget(download_btn)
            btn_layout.addStretch()
            layout.addWidget(btn_container)
            
            # Show installation path info
            try:
                from integrations.tools_downloader import RYZENADJ_DIR
                install_path = RYZENADJ_DIR
            except ImportError:
                install_path = "%APPDATA%\\HELXAID\\tools\\ryzenadj"
            instructions = QLabel(f"Will be installed to:\n{install_path}")
            instructions.setStyleSheet("font-size: 11px; color: #6c757d; margin-top: 10px;")
            instructions.setAlignment(Qt.AlignCenter)
            instructions.setWordWrap(True)
            layout.addWidget(instructions)
            
            layout.addStretch()
            self.content_stack.addWidget(self.cpu_panel)
            return
        
        # Initialize CPU settings - use AppData for persistence
        settings_path = os.path.join(APPDATA_DIR, "cpu_settings.json")
        self.cpu_settings = CPUControlSettings(settings_path)
        
        # Start auto-reapply timer if enabled in settings
        if self.cpu_settings._settings.get("keep_settings_applied", False):
            # Get saved interval - enforce minimum 300s (5 min) for safety
            saved_interval = max(300, self.cpu_settings._settings.get("reapply_interval", 300))
            # Delay timer start to allow UI to initialize
            from PySide6.QtCore import QTimer as QTimerLocal
            QTimerLocal.singleShot(5000, lambda: self._start_cpu_reapply_timer(saved_interval))
        
        # ===== HEADER SECTION =====
        header_container = QWidget()
        header_container.setObjectName("headerCard")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(24, 20, 24, 20)
        
        title_section = QVBoxLayout()
        title_section.setSpacing(4)
        
        header = QLabel("HELXAIL")
        header.setObjectName("cpuControlTitle")
        header.setStyleSheet("font-size: 28px; font-weight: 600; color: #DDE6ED; letter-spacing: 1px;")
        title_section.addWidget(header)
        
        subtitle = QLabel("AMD RyzenAdj Integration")
        subtitle.setObjectName("cpuControlSubtitle")
        subtitle.setStyleSheet("font-size: 12px; color: #9DB2BF; letter-spacing: 0.5px;")
        title_section.addWidget(subtitle)
        
        header_layout.addLayout(title_section)
        header_layout.addStretch()
        
        # Status badge
        if self.uxtu_installed:
            status_text, status_style = "● CONNECTED", "background: rgba(76, 175, 80, 0.15); color: #4CAF50; border: 1px solid rgba(76, 175, 80, 0.3); border-radius: 12px; padding: 6px 14px; font-size: 11px; font-weight: bold;"
        else:
            status_text, status_style = "● OFFLINE", "background: rgba(244, 67, 54, 0.15); color: #f44336; border: 1px solid rgba(244, 67, 54, 0.3); border-radius: 12px; padding: 6px 14px; font-size: 11px; font-weight: bold;"
        
        status_badge = QLabel(status_text)
        status_badge.setObjectName("cpuStatusBadge")
        status_badge.setStyleSheet(status_style)
        header_layout.addWidget(status_badge, 0, Qt.AlignVCenter)
        
        # Settings button
        settings_btn = AnimatedButton("")
        settings_btn.setObjectName("cpuSettingsBtn")
        settings_btn.setFixedSize(50, 50)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setToolTip("CPU Settings")
        # Set icon
        icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "setting-icon.png")
        if os.path.exists(icon_path):
            settings_btn.setIcon(QIcon(icon_path))
            settings_btn.setIconSize(QSize(50, 50))
        settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
        """)
        
        # Setup animated icon rotation on hover
        if os.path.exists(icon_path):
            from PySide6.QtGui import QPixmap, QTransform
            from PySide6.QtCore import QTimer
            
            # Create icon frames for animation (0 to -45 degrees)
            pixmap = QPixmap(icon_path)
            original_size = pixmap.size()
            frames = []
            num_frames = 9  # 0, -5, -10, -15, -20, -25, -30, -35, -40, -45
            for i in range(num_frames + 1):
                angle = -5 * i  # 0 to -45 degrees
                transform = QTransform().rotate(angle)
                rotated = pixmap.transformed(transform, Qt.SmoothTransformation)
                
                # Create fixed-size canvas and center the rotated icon
                from PySide6.QtGui import QPainter
                canvas = QPixmap(original_size)
                canvas.fill(Qt.transparent)
                painter = QPainter(canvas)
                # Center the rotated pixmap on canvas
                x = (original_size.width() - rotated.width()) // 2
                y = (original_size.height() - rotated.height()) // 2
                painter.drawPixmap(x, y, rotated)
                painter.end()
                
                frames.append(QIcon(canvas))
            
            # Store animation state on button
            settings_btn._rot_frames = frames
            settings_btn._rot_index = 0
            settings_btn._rot_forward = True  # True = rotating, False = returning
            settings_btn._rot_timer = QTimer()
            settings_btn._rot_timer.setInterval(20)  # 20ms per frame = ~200ms total
            
            def _animate_frame():
                if settings_btn._rot_forward:
                    if settings_btn._rot_index < len(frames) - 1:
                        settings_btn._rot_index += 1
                        settings_btn.setIcon(frames[settings_btn._rot_index])
                    else:
                        settings_btn._rot_timer.stop()
                else:
                    if settings_btn._rot_index > 0:
                        settings_btn._rot_index -= 1
                        settings_btn.setIcon(frames[settings_btn._rot_index])
                    else:
                        settings_btn._rot_timer.stop()
            
            settings_btn._rot_timer.timeout.connect(_animate_frame)
            
            # Override enter/leave events
            original_enter = settings_btn.enterEvent
            original_leave = settings_btn.leaveEvent
            
            def new_enter(event):
                settings_btn._rot_forward = True
                settings_btn._rot_timer.start()
                original_enter(event)
            
            def new_leave(event):
                settings_btn._rot_forward = False
                settings_btn._rot_timer.start()
                original_leave(event)
            
            settings_btn.enterEvent = new_enter
            settings_btn.leaveEvent = new_leave
        
        settings_btn.clicked.connect(self._open_cpu_settings)
        header_layout.addWidget(settings_btn, 0, Qt.AlignVCenter)
        
        header_container.setStyleSheet("QWidget#headerCard { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(26, 26, 26, 0.9), stop:1 rgba(45, 45, 45, 0.6)); border-radius: 16px; border: 1px solid rgba(255, 91, 6, 0.3); }")
        layout.addWidget(header_container)
        
        # ===== PRESET CARD =====
        preset_card = QWidget()
        preset_card.setObjectName("presetCard")
        preset_layout = QHBoxLayout(preset_card)
        preset_layout.setContentsMargins(20, 16, 20, 16)
        preset_layout.setSpacing(12)
        
        preset_icon = QLabel("")
        preset_icon.setObjectName("cpuPresetIcon")
        preset_icon.setStyleSheet("font-size: 20px;")
        preset_layout.addWidget(preset_icon)
        
        preset_label = QLabel("Preset")
        preset_label.setObjectName("cpuPresetLabel")
        preset_label.setStyleSheet("color: #FDA903; font-size: 13px; font-weight: 500;")
        preset_layout.addWidget(preset_label)
        
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("cpuPresetCombo")
        self.preset_combo.setMinimumWidth(220)
        self.preset_combo.setFixedHeight(38)
        self.preset_combo.setEditable(True)
        # Use down-arrow.png for dropdown icon
        arrow_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "down-arrow.png").replace("\\", "/")
        self.preset_combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(26, 26, 26, 0.8); color: #e0e0e0; border: 1px solid rgba(255, 91, 6, 0.5); border-radius: 10px; padding: 8px 16px; font-size: 13px; }}
            QComboBox:hover {{ border: 1px solid #FDA903; }}
            QComboBox::drop-down {{ border: none; width: 32px; }}
            QComboBox::down-arrow {{ image: url({arrow_icon_path}); width: 12px; height: 12px; }}
            QComboBox QAbstractItemView {{ background: #1a1a1a; color: #e0e0e0; selection-background-color: #FF5B06; border: 1px solid #FF5B06; border-radius: 8px; }}
        """)
        self._refresh_preset_combo()
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.preset_combo, 1)
        
        save_btn = AnimatedButton("Save")
        save_btn.setObjectName("cpuSavePresetButton")
        save_btn.setFixedSize(70, 38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setHoverGradient(['#FF5B06', '#FDA903'])  # Orange theme
        save_btn.setStyleSheet("QPushButton { background: #FF5B06; color: #ffffff; border: none; border-radius: 10px; font-size: 12px; font-weight: 600; } QPushButton:hover { background: #FDA903; color: #1a1a1a; }")
        save_btn.clicked.connect(self._save_current_preset)
        preset_layout.addWidget(save_btn)
        
        del_btn = AnimatedButton("X")
        del_btn.setObjectName("cpuDeletePresetButton")
        del_btn.setFixedSize(38, 38)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Delete preset")
        del_btn.setHoverGradient(['#f44336', '#ff5252'])  # Red for delete
        del_btn.setStyleSheet("QPushButton { background: transparent; color: #FDA903; border: 1px solid rgba(255, 91, 6, 0.5); border-radius: 10px; font-size: 14px; } QPushButton:hover { background: rgba(244, 67, 54, 0.2); border-color: #f44336; color: #f44336; }")
        del_btn.clicked.connect(self._delete_current_preset)
        preset_layout.addWidget(del_btn)
        
        preset_card.setStyleSheet("QWidget#presetCard { background: rgba(26, 26, 26, 0.5); border-radius: 14px; border: 1px solid rgba(255, 91, 6, 0.3); }")
        layout.addWidget(preset_card)
        
        # ===== SLIDERS SECTION =====
        scroll = SmoothScrollArea()
        scroll.setObjectName("cpuSlidersScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)  # Always show scrollbar
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(26, 26, 26, 0.3); width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #FF5B06; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #FDA903; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        
        sliders_widget = QWidget()
        sliders_widget.setObjectName("cpuSlidersContainer")
        sliders_widget.setStyleSheet("background: transparent;")
        sliders_layout = QVBoxLayout(sliders_widget)
        sliders_layout.setContentsMargins(0, 0, 8, 0)
        sliders_layout.setSpacing(8)
        
        self.cpu_sliders = {}
        self._cpu_slider_checkboxes = {}  # Stores enabled checkboxes for each slider
        
        # ===== AMD BOOST PROFILE MENU =====
        boost_container = QWidget()
        boost_container.setObjectName("cpuBoostProfile")
        boost_container.setFixedHeight(56)
        boost_layout = QHBoxLayout(boost_container)
        boost_layout.setContentsMargins(16, 10, 16, 10)
        boost_layout.setSpacing(12)
        
        # Gear icon
        boost_icon = QLabel("")
        boost_icon.setStyleSheet("font-size: 20px; background: transparent;")
        boost_layout.addWidget(boost_icon)
        
        # Title + Description
        boost_text_layout = QVBoxLayout()
        boost_text_layout.setSpacing(2)
        boost_title = QLabel("AMD Boost Profile")
        boost_title.setObjectName("cpuBoostProfileTitle")
        boost_title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 600; background: transparent;")
        boost_desc = QLabel("Set a manual boost profile which impacts boost delay.")
        boost_desc.setObjectName("cpuBoostProfileDesc")
        boost_desc.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        boost_text_layout.addWidget(boost_title)
        boost_text_layout.addWidget(boost_desc)
        boost_layout.addLayout(boost_text_layout)
        
        boost_layout.addStretch()
        
        # Dropdown
        self.boost_profile_combo = QComboBox()
        self.boost_profile_combo.setObjectName("cpuBoostProfileCombo")
        self.boost_profile_combo.addItems(["Auto", "Eco", "Balance", "Performance", "Max"])
        self.boost_profile_combo.setFixedSize(120, 32)
        arrow_path = os.path.join(SCRIPT_DIR, "UI Icons", "down-arrow.png").replace("\\", "/")
        self.boost_profile_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(50, 54, 62, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QComboBox:hover {{
                border-color: rgba(255, 91, 6, 0.5);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #FF5B06;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
            }}
        """)
        self.boost_profile_combo.currentTextChanged.connect(self._on_boost_profile_changed)
        boost_layout.addWidget(self.boost_profile_combo)
        
        boost_container.setStyleSheet("""
            QWidget#cpuBoostProfile {
                background: rgba(40, 44, 52, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.3);
                border-radius: 8px;
            }
            QWidget#cpuBoostProfile:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)
        sliders_layout.addWidget(boost_container)
        
        # ===== DISPLAY REFRESH RATE MENU =====
        refresh_container = QWidget()
        refresh_container.setObjectName("cpuRefreshRate")
        refresh_container.setFixedHeight(56)
        refresh_layout = QHBoxLayout(refresh_container)
        refresh_layout.setContentsMargins(16, 10, 16, 10)
        refresh_layout.setSpacing(12)
        
        # Monitor icon
        refresh_icon = QLabel("")
        refresh_icon.setStyleSheet("font-size: 20px; background: transparent;")
        refresh_layout.addWidget(refresh_icon)
        
        # Title + Description
        refresh_text_layout = QVBoxLayout()
        refresh_text_layout.setSpacing(2)
        refresh_title = QLabel("Display Refresh Rate")
        refresh_title.setObjectName("cpuRefreshRateTitle")
        refresh_title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 600; background: transparent;")
        refresh_desc = QLabel("Set a custom display refresh rate. May not work for everyone!")
        refresh_desc.setObjectName("cpuRefreshRateDesc")
        refresh_desc.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        refresh_text_layout.addWidget(refresh_title)
        refresh_text_layout.addWidget(refresh_desc)
        refresh_layout.addLayout(refresh_text_layout)
        
        refresh_layout.addStretch()
        
        # Dropdown - Get available refresh rates from Windows
        self.refresh_rate_combo = QComboBox()
        self.refresh_rate_combo.setObjectName("cpuRefreshRateCombo")
        
        # Detect available refresh rates using Windows API
        available_rates = self._get_available_refresh_rates()
        rate_options = ["System Controlled"] + [f"{rate} Hz" for rate in sorted(set(available_rates), reverse=True)]
        self.refresh_rate_combo.addItems(rate_options)
        self.refresh_rate_combo.setFixedSize(140, 32)
        self.refresh_rate_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(50, 54, 62, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QComboBox:hover {{
                border-color: rgba(255, 91, 6, 0.5);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #FF5B06;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
            }}
        """)
        self.refresh_rate_combo.currentTextChanged.connect(self._on_refresh_rate_changed)
        refresh_layout.addWidget(self.refresh_rate_combo)
        
        refresh_container.setStyleSheet("""
            QWidget#cpuRefreshRate {
                background: rgba(40, 44, 52, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.3);
                border-radius: 8px;
            }
            QWidget#cpuRefreshRate:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)
        sliders_layout.addWidget(refresh_container)
        
        # ===== WINDOWS POWER MODE MENU =====
        power_mode_container = QWidget()
        power_mode_container.setObjectName("cpuPowerMode")
        power_mode_container.setFixedHeight(56)
        power_mode_layout = QHBoxLayout(power_mode_container)
        power_mode_layout.setContentsMargins(16, 10, 16, 10)
        power_mode_layout.setSpacing(12)
        
        # Power icon
        power_mode_icon = QLabel("⏻")
        power_mode_icon.setStyleSheet("font-size: 20px; background: transparent;")
        power_mode_layout.addWidget(power_mode_icon)
        
        # Title + Description
        power_mode_text_layout = QVBoxLayout()
        power_mode_text_layout.setSpacing(2)
        power_mode_title = QLabel("Windows Power Mode")
        power_mode_title.setObjectName("cpuPowerModeTitle")
        power_mode_title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 600; background: transparent;")
        power_mode_desc = QLabel("Change Windows power mode from a preset.")
        power_mode_desc.setObjectName("cpuPowerModeDesc")
        power_mode_desc.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        power_mode_text_layout.addWidget(power_mode_title)
        power_mode_text_layout.addWidget(power_mode_desc)
        power_mode_layout.addLayout(power_mode_text_layout)
        
        power_mode_layout.addStretch()
        
        # Dropdown
        self.power_mode_combo = QComboBox()
        self.power_mode_combo.setObjectName("cpuPowerModeCombo")
        self.power_mode_combo.addItems(["System Controlled", "Power Saver", "Balanced", "High Performance", "Ultimate Performance"])
        self.power_mode_combo.setFixedSize(160, 32)
        self.power_mode_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(50, 54, 62, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QComboBox:hover {{
                border-color: rgba(255, 91, 6, 0.5);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #FF5B06;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
            }}
        """)
        self.power_mode_combo.currentTextChanged.connect(self._on_power_mode_changed)
        power_mode_layout.addWidget(self.power_mode_combo)
        
        power_mode_container.setStyleSheet("""
            QWidget#cpuPowerMode {
                background: rgba(40, 44, 52, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.3);
                border-radius: 8px;
            }
            QWidget#cpuPowerMode:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)
        sliders_layout.addWidget(power_mode_container)
        
        # Group definitions with icons and descriptions
        slider_groups = [
            ("", "Temperature Tuning", "Set CPU thermal targets", "temperature", [
                ("temp_limit", "Temperature Limit (°C)", "°C"), 
                ("temp_skin_limit", "Skin Temperature Limit (°C)", "°C")
            ]),
            ("", "Power Limits", "Configure power delivery", "power", [
                ("stapm_limit", "STAPM Power (W)", "W"), 
                ("slow_limit", "Slow Power (W)", "W"), 
                ("fast_limit", "Fast Power (W)", "W")
            ]),
            ("", "Boost Timing", "Adjust boost durations", "timing", [
                ("slow_duration", "Slow Duration (s)", "s"), 
                ("fast_duration", "Fast Duration (s)", "s")
            ]),
            ("", "Current Limits", "Set TDC/EDC values", "current", [
                ("cpu_tdc", "CPU TDC (A)", "A"), 
                ("cpu_edc", "CPU EDC (A)", "A"), 
                ("gfx_tdc", "GFX TDC (A)", "A"), 
                ("gfx_edc", "GFX EDC (A)", "A"),
                ("soc_tdc", "SoC TDC (A)", "A"),  # NEW
                ("soc_edc", "SoC EDC (A)", "A"),  # NEW
            ]),
            ("", "iGPU Tuning", "Configure integrated graphics", "igpu", [
                ("igpu_clock", "iGPU Clock (MHz)", "MHz"),  # NEW
            ]),
        ]
        
        self._cpu_collapsible_groups = {}
        
        for idx, (icon, title, desc, group_id, sliders) in enumerate(slider_groups):
            # Main container with border
            group_container = QWidget()
            group_container.setObjectName(f"cpuGroup_{group_id}")
            group_container_layout = QVBoxLayout(group_container)
            group_container_layout.setContentsMargins(0, 0, 0, 0)
            group_container_layout.setSpacing(0)
            
            # Header widget (clickable area)
            header_widget = QWidget()
            header_widget.setObjectName(f"cpuGroupHeader_{group_id}")
            header_widget.setCursor(Qt.PointingHandCursor)
            header_widget.setFixedHeight(52)
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(16, 10, 16, 10)
            header_layout.setSpacing(12)
            
            # Icon
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 20px; background: transparent;")
            header_layout.addWidget(icon_label)
            
            # Title + Description
            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            title_label = QLabel(title)
            title_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 600; background: transparent;")
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
            text_layout.addWidget(title_label)
            text_layout.addWidget(desc_label)
            header_layout.addLayout(text_layout)
            
            header_layout.addStretch()
            
            # Chevron arrow (using icon with rotation)
            from PySide6.QtGui import QPixmap, QTransform
            chevron = QLabel()
            chevron.setObjectName(f"cpuChevron_{group_id}")
            chevron.setFixedSize(16, 16)
            chevron_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "down-arrow.png")
            chevron_pixmap = QPixmap(chevron_icon_path)
            if not chevron_pixmap.isNull():
                chevron_pixmap = chevron_pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # Store original pixmap for rotation
            chevron.setProperty("original_pixmap", chevron_pixmap)
            # Initially rotated -90 for collapsed (pointing right)
            if idx == 0:
                # First group expanded - pointing down (0 rotation)
                chevron.setPixmap(chevron_pixmap)
            else:
                # Other groups collapsed - pointing right (-90 rotation)
                transform = QTransform().rotate(-90)
                rotated = chevron_pixmap.transformed(transform, Qt.SmoothTransformation)
                chevron.setPixmap(rotated)
            chevron.setStyleSheet("background: transparent;")
            header_layout.addWidget(chevron)
            
            header_widget.setStyleSheet(f"""
                QWidget#cpuGroupHeader_{group_id} {{
                    background: rgba(40, 44, 52, 0.9);
                    border: 1px solid rgba(80, 80, 80, 0.3);
                    border-radius: 8px;
                }}
                QWidget#cpuGroupHeader_{group_id}:hover {{
                    background: rgba(50, 54, 62, 0.95);
                    border-color: rgba(255, 91, 6, 0.4);
                }}
            """)
            group_container_layout.addWidget(header_widget)
            
            # Content widget with sliders
            content_widget = QWidget()
            content_widget.setObjectName(f"cpuGroupContent_{group_id}")
            content_widget.setStyleSheet(f"""
                QWidget#cpuGroupContent_{group_id} {{
                    background: rgba(35, 38, 45, 0.6);
                    border: 1px solid rgba(80, 80, 80, 0.2);
                    border-top: none;
                    border-radius: 0 0 8px 8px;
                }}
            """)
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(16, 12, 16, 16)
            content_layout.setSpacing(14)
            
            for key, label_text, unit in sliders:
                limits = SAFETY_LIMITS.get(key, {"min": 0, "max": 100, "default": 50})
                current_value = self.cpu_settings.get_value(key)
                
                row = QWidget()
                row.setObjectName(f"cpuSliderRow_{key}")
                row.setStyleSheet("background: transparent;")
                row_layout = QVBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)
                
                # Label row
                label = QLabel(label_text)
                label.setObjectName(f"cpuSliderLabel_{key}")
                label.setStyleSheet("color: #b0b0b0; font-size: 12px; background: transparent;")
                row_layout.addWidget(label)
                
                # Spinbox + Slider row
                control_row = QHBoxLayout()
                control_row.setSpacing(12)
                
                # Enable/disable checkbox (placed BEFORE spinbox)
                from PySide6.QtWidgets import QCheckBox
                enable_cb = QCheckBox()
                enable_cb.setObjectName(f"cpuSliderCheck_{key}")
                # Get enabled state from settings (default True for existing, False for new)
                enabled_settings = self.cpu_settings.profile.get("enabled_settings", {})
                is_checked = enabled_settings.get(key, key not in ["soc_tdc", "soc_edc", "igpu_clock"])
                enable_cb.setChecked(is_checked)
                enable_cb.setFixedSize(24, 24)
                enable_cb.setStyleSheet("""
                    QCheckBox::indicator { 
                        width: 18px; height: 18px; 
                        border: 2px solid #555; 
                        border-radius: 4px; 
                        background: #2a2a2a; 
                    }
                    QCheckBox::indicator:hover { 
                        border-color: #FF5B06; 
                    }
                    QCheckBox::indicator:checked { 
                        background: #FF5B06; 
                        border-color: #FF5B06; 
                    }
                """)
                control_row.addWidget(enable_cb)
                
                # Spinbox with custom arrow icons
                from PySide6.QtWidgets import QSpinBox
                spinbox = QSpinBox()
                spinbox.setObjectName(f"cpuSpinbox_{key}")
                spinbox.setMinimum(limits["min"])
                spinbox.setMaximum(limits["max"])
                spinbox.setValue(current_value)
                spinbox.setFixedSize(80, 32)
                up_arrow_path = os.path.join(SCRIPT_DIR, "UI Icons", "up-arrow.png").replace("\\", "/")
                down_arrow_path = os.path.join(SCRIPT_DIR, "UI Icons", "down-arrow.png").replace("\\", "/")
                spinbox.setStyleSheet(f"""
                    QSpinBox {{
                        background: rgba(30, 33, 40, 0.9);
                        color: #e0e0e0;
                        border: 1px solid rgba(80, 80, 80, 0.4);
                        border-radius: 6px;
                        padding: 4px 8px;
                        font-size: 13px;
                    }}
                    QSpinBox::up-button {{
                        width: 18px;
                        background: rgba(60, 64, 72, 0.8);
                        border: none;
                        subcontrol-origin: border;
                        subcontrol-position: top right;
                    }}
                    QSpinBox::up-button:hover {{
                        background: rgba(255, 91, 6, 0.3);
                    }}
                    QSpinBox::up-arrow {{
                        image: url({up_arrow_path});
                        width: 10px;
                        height: 10px;
                    }}
                    QSpinBox::down-button {{
                        width: 18px;
                        background: rgba(60, 64, 72, 0.8);
                        border: none;
                        subcontrol-origin: border;
                        subcontrol-position: bottom right;
                    }}
                    QSpinBox::down-button:hover {{
                        background: rgba(255, 91, 6, 0.3);
                    }}
                    QSpinBox::down-arrow {{
                        image: url({down_arrow_path});
                        width: 10px;
                        height: 10px;
                    }}
                """)
                control_row.addWidget(spinbox)
                
                # Slider
                slider = NoScrollSlider(Qt.Horizontal)
                slider.setObjectName(f"cpuSlider_{key}")
                slider.setMinimum(limits["min"])
                slider.setMaximum(limits["max"])
                slider.setValue(current_value)
                slider.setFixedHeight(20)
                slider.setStyleSheet("""
                    QSlider::groove:horizontal { height: 4px; background: rgba(60, 64, 72, 0.8); border-radius: 2px; }
                    QSlider::handle:horizontal { 
                        background: #e0e0e0; 
                        width: 14px; 
                        height: 14px; 
                        margin: -5px 0; 
                        border-radius: 7px;
                        border: none;
                    }
                    QSlider::handle:horizontal:hover { background: #ffffff; }
                    QSlider::sub-page:horizontal { background: rgba(255, 91, 6, 0.6); border-radius: 2px; }
                """)
                control_row.addWidget(slider, 1)
                
                # Connect checkbox to enable/disable slider + spinbox
                def make_enable_toggle(sp, sl, k):
                    def toggle(checked):
                        sp.setEnabled(checked)
                        sl.setEnabled(checked)
                        opacity_style = "" if checked else "color: #666;"
                        sp.setStyleSheet(sp.styleSheet().replace("color: #666;", "") + opacity_style)
                        # Save to settings
                        self._on_cpu_checkbox_toggled(k, checked)
                    return toggle
                enable_cb.toggled.connect(make_enable_toggle(spinbox, slider, key))
                # Apply initial disabled state if unchecked
                if not is_checked:
                    spinbox.setEnabled(False)
                    slider.setEnabled(False)
                
                row_layout.addLayout(control_row)
                
                # Sync spinbox and slider
                def make_sync(sp, sl, lbl, u, k):
                    def sync_from_slider(val):
                        sp.blockSignals(True)
                        sp.setValue(val)
                        sp.blockSignals(False)
                        self._on_cpu_slider_changed(val, lbl, u, k)
                    def sync_from_spinbox(val):
                        sl.blockSignals(True)
                        sl.setValue(val)
                        sl.blockSignals(False)
                        self._on_cpu_slider_changed(val, lbl, u, k)
                    return sync_from_slider, sync_from_spinbox
                
                # Create a value label (hidden, for compatibility)
                value_label = QLabel(f"{current_value}")
                value_label.setObjectName(f"cpuSliderValue_{key}")
                value_label.hide()
                
                sync_slider, sync_spinbox = make_sync(spinbox, slider, value_label, unit, key)
                slider.valueChanged.connect(sync_slider)
                spinbox.valueChanged.connect(sync_spinbox)
                
                self.cpu_sliders[key] = (slider, value_label, unit)
                self._cpu_slider_checkboxes[key] = enable_cb
                content_layout.addWidget(row)
            
            group_container_layout.addWidget(content_widget)
            
            # Store references
            self._cpu_collapsible_groups[group_id] = {
                "header": header_widget, "content": content_widget, "chevron": chevron,
                "expanded": idx == 0, "title": title
            }
            
            # Click handler for header with animations
            def make_toggle(gid, content_w, chevron_lbl):
                def toggle(event):
                    from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QVariantAnimation
                    from PySide6.QtGui import QTransform
                    
                    grp = self._cpu_collapsible_groups[gid]
                    grp["expanded"] = not grp["expanded"]
                    
                    # Get original pixmap for rotation
                    orig_pixmap = chevron_lbl.property("original_pixmap")
                    
                    if grp["expanded"]:
                        # EXPAND: Show content first, then animate
                        content_w.setVisible(True)
                        content_w.setMaximumHeight(0)
                        
                        # Animate height
                        target_height = content_w.sizeHint().height()
                        anim = QPropertyAnimation(content_w, b"maximumHeight")
                        anim.setDuration(200)
                        anim.setStartValue(0)
                        anim.setEndValue(target_height + 50)  # Extra buffer
                        anim.setEasingCurve(QEasingCurve.OutCubic)
                        anim.start()
                        grp["anim"] = anim  # Keep reference
                        
                        # Chevron animation (rotate to 0)
                        if orig_pixmap:
                            def animate_chevron(progress):
                                angle = -90 + (90 * progress)  # -90 to 0
                                transform = QTransform().rotate(angle)
                                rotated = orig_pixmap.transformed(transform, Qt.SmoothTransformation)
                                chevron_lbl.setPixmap(rotated)
                            
                            chevron_anim = QVariantAnimation()
                            chevron_anim.setDuration(200)
                            chevron_anim.setStartValue(0.0)
                            chevron_anim.setEndValue(1.0)
                            chevron_anim.valueChanged.connect(animate_chevron)
                            chevron_anim.start()
                            grp["chevron_anim"] = chevron_anim
                    else:
                        # COLLAPSE: Animate height, then hide
                        current_height = content_w.height()
                        
                        anim = QPropertyAnimation(content_w, b"maximumHeight")
                        anim.setDuration(150)
                        anim.setStartValue(current_height)
                        anim.setEndValue(0)
                        anim.setEasingCurve(QEasingCurve.InCubic)
                        anim.finished.connect(lambda: content_w.setVisible(False))
                        anim.start()
                        grp["anim"] = anim
                        
                        # Chevron animation (rotate to -90)
                        if orig_pixmap:
                            def animate_chevron(progress):
                                angle = 0 - (90 * progress)  # 0 to -90
                                transform = QTransform().rotate(angle)
                                rotated = orig_pixmap.transformed(transform, Qt.SmoothTransformation)
                                chevron_lbl.setPixmap(rotated)
                            
                            chevron_anim = QVariantAnimation()
                            chevron_anim.setDuration(150)
                            chevron_anim.setStartValue(0.0)
                            chevron_anim.setEndValue(1.0)
                            chevron_anim.valueChanged.connect(animate_chevron)
                            chevron_anim.start()
                            grp["chevron_anim"] = chevron_anim
                
                return toggle
            
            header_widget.mousePressEvent = make_toggle(group_id, content_widget, chevron)
            
            # Collapse non-first groups (chevron already set above)
            if idx > 0:
                content_widget.setVisible(False)
            
            sliders_layout.addWidget(group_container)
        
        sliders_layout.addStretch()
        scroll.setWidget(sliders_widget)
        layout.addWidget(scroll, 1)
        
        # ===== ACTION BUTTONS =====
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(16)
        
        reset_btn = AnimatedButton("↺  Reset Defaults")
        reset_btn.setObjectName("cpuResetButton")
        reset_btn.setFixedHeight(44)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setHoverGradient(['#FF5B06', '#FDA903'])  # Orange theme
        reset_btn.setStyleSheet("QPushButton { background: transparent; color: #FDA903; border: 2px solid rgba(255, 91, 6, 0.5); border-radius: 12px; font-size: 13px; font-weight: 500; padding: 0 24px; } QPushButton:hover { background: rgba(255, 91, 6, 0.2); border-color: #FDA903; color: #e0e0e0; }")
        reset_btn.clicked.connect(self._reset_cpu_sliders)
        btn_layout.addWidget(reset_btn)
        
        btn_layout.addStretch()
        
        apply_btn = AnimatedButton("Apply with RyzenAdj")
        apply_btn.setObjectName("cpuApplyButton")
        apply_btn.setFixedHeight(44)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setHoverGradient(['#FF5B06', '#FDA903', '#e0e0e0'])  # Orange gradient
        apply_btn.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903); color: #1a1a1a; border: none; border-radius: 12px; font-size: 14px; font-weight: bold; padding: 0 32px; } QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:1 #FFD700); }")
        apply_btn.clicked.connect(self._apply_cpu_settings)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
        
        # ===== PANEL BACKGROUND =====
        self.cpu_panel.setStyleSheet("QWidget#cpuPanel { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0a0a0a, stop:0.5 #1a1a1a, stop:1 #0a0a0a); }")
        
        # Add to stack (will be added at end, use insertWidget for specific position)
        if not hasattr(self, '_cpu_panel_insert_index'):
            self.content_stack.addWidget(self.cpu_panel)
        else:
            self.content_stack.insertWidget(self._cpu_panel_insert_index, self.cpu_panel)
            delattr(self, '_cpu_panel_insert_index')
    
    def _reload_cpu_panel(self):
        """Reload the CPU panel after RyzenAdj installation."""
        # Get current panel index (should be 2)
        cpu_panel_index = self.content_stack.indexOf(self.cpu_panel)
        if cpu_panel_index < 0:
            cpu_panel_index = 2  # Default CPU panel index
        
        # Remove old panel
        self.content_stack.removeWidget(self.cpu_panel)
        self.cpu_panel.deleteLater()
        
        # Set insert index for _setup_cpu_panel
        self._cpu_panel_insert_index = cpu_panel_index
        
        # Recreate the panel at correct position
        self._setup_cpu_panel()
        
        # Switch to the CPU panel
        self.switch_panel(cpu_panel_index)
    
    def _on_boost_profile_changed(self, profile: str):
        """Handle boost profile selection change."""
        # Map profile names to RyzenAdj power-saving values
        profile_map = {
            "Auto": None,  # Default, no override
            "Eco": {"power_saving": 2},
            "Balance": {"power_saving": 1},
            "Performance": {"power_saving": 0},
            "Max": {"max_performance": True}
        }
        
        settings = profile_map.get(profile, None)
        if settings:
            # Store selected profile for later application
            if hasattr(self, 'cpu_settings'):
                self.cpu_settings.boost_profile = profile
            print(f"[CPU] Boost profile changed to: {profile}")
    
    def _on_refresh_rate_changed(self, rate: str):
        """Handle refresh rate selection change."""
        if rate == "System Controlled":
            print("[Display] Refresh rate: System Controlled")
            return
        
        # Extract Hz value
        try:
            hz_value = int(rate.replace(" Hz", ""))
            print(f"[Display] Refresh rate changed to: {hz_value} Hz")
            # TODO: Implement actual refresh rate change using Windows API
            # This would require ctypes to call ChangeDisplaySettingsEx
        except ValueError:
            pass
    
    def _on_cpu_nav_clicked(self):
        """Handle CPU Control button click - collapse all dropdowns first."""
        from PySide6.QtGui import QTransform
        
        # Collapse all expanded CPU groups
        if hasattr(self, '_cpu_collapsible_groups'):
            for gid, grp in self._cpu_collapsible_groups.items():
                if grp.get("expanded", False):
                    grp["expanded"] = False
                    content_w = grp["content"]
                    chevron = grp["chevron"]
                    
                    # Hide content immediately (no animation for nav click)
                    content_w.setVisible(False)
                    
                    # Rotate chevron to collapsed state (-90 degrees)
                    orig_pixmap = chevron.property("original_pixmap")
                    if orig_pixmap:
                        transform = QTransform().rotate(-90)
                        rotated = orig_pixmap.transformed(transform, Qt.SmoothTransformation)
                        chevron.setPixmap(rotated)
        
        # Switch to CPU panel
        self.switch_panel(2)
    
    def _setup_hardware_panel(self):
        """Setup the Hardware Monitor panel."""
        self.hardware_panel = HardwarePanelWidget()
        self.hardware_panel.setObjectName("hardwarePanel")
        self.content_stack.addWidget(self.hardware_panel)
        print("[Hardware] HardwarePanelWidget added to content stack")
    
    def _on_power_mode_changed(self, mode: str):
        """Handle Windows power mode selection change."""
        # Power plan GUIDs
        power_plans = {
            "System Controlled": None,
            "Power Saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
            "Balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
            "High Performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "Ultimate Performance": "e9a42b02-d5df-448d-aa00-03f14749eb61"
        }
        
        guid = power_plans.get(mode)
        if guid:
            print(f"[Power] Power mode changed to: {mode}")
            # Execute powercfg to change power plan
            try:
                import subprocess
                subprocess.run(["powercfg", "/setactive", guid], capture_output=True, shell=True)
            except Exception as e:
                print(f"[Power] Failed to change power mode: {e}")
        else:
            print("[Power] Power mode: System Controlled")
    
    def _get_available_refresh_rates(self) -> list:
        """Get available display refresh rates from Windows using EnumDisplaySettings API."""
        refresh_rates = []
        try:
            import ctypes
            from ctypes import wintypes
            
            # DEVMODE structure
            class DEVMODE(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName", wintypes.WCHAR * 32),
                    ("dmSpecVersion", wintypes.WORD),
                    ("dmDriverVersion", wintypes.WORD),
                    ("dmSize", wintypes.WORD),
                    ("dmDriverExtra", wintypes.WORD),
                    ("dmFields", wintypes.DWORD),
                    ("dmPositionX", wintypes.LONG),
                    ("dmPositionY", wintypes.LONG),
                    ("dmDisplayOrientation", wintypes.DWORD),
                    ("dmDisplayFixedOutput", wintypes.DWORD),
                    ("dmColor", wintypes.SHORT),
                    ("dmDuplex", wintypes.SHORT),
                    ("dmYResolution", wintypes.SHORT),
                    ("dmTTOption", wintypes.SHORT),
                    ("dmCollate", wintypes.SHORT),
                    ("dmFormName", wintypes.WCHAR * 32),
                    ("dmLogPixels", wintypes.WORD),
                    ("dmBitsPerPel", wintypes.DWORD),
                    ("dmPelsWidth", wintypes.DWORD),
                    ("dmPelsHeight", wintypes.DWORD),
                    ("dmDisplayFlags", wintypes.DWORD),
                    ("dmDisplayFrequency", wintypes.DWORD),
                ]
            
            user32 = ctypes.windll.user32
            
            # Get current display settings to match resolution
            current_mode = DEVMODE()
            current_mode.dmSize = ctypes.sizeof(DEVMODE)
            user32.EnumDisplaySettingsW(None, -1, ctypes.byref(current_mode))  # ENUM_CURRENT_SETTINGS
            current_width = current_mode.dmPelsWidth
            current_height = current_mode.dmPelsHeight
            
            # Enumerate all display modes
            mode_num = 0
            mode = DEVMODE()
            mode.dmSize = ctypes.sizeof(DEVMODE)
            
            while user32.EnumDisplaySettingsW(None, mode_num, ctypes.byref(mode)):
                # Only add refresh rates for current resolution
                if mode.dmPelsWidth == current_width and mode.dmPelsHeight == current_height:
                    if mode.dmDisplayFrequency > 0:
                        refresh_rates.append(mode.dmDisplayFrequency)
                mode_num += 1
            
            # Remove duplicates and filter common values
            refresh_rates = list(set(refresh_rates))
            print(f"[Display] Available refresh rates: {sorted(refresh_rates)} Hz")
            
        except Exception as e:
            print(f"[Display] Failed to get refresh rates: {e}")
            # Fallback to common rates
            refresh_rates = [60, 144]
        
        return refresh_rates if refresh_rates else [60]
    
    def _open_cpu_settings(self):
        """Open CPU settings dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("CPU Settings")
        dialog.setObjectName("cpuSettingsDialog")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet("""
            QDialog {
                background: #1a2636;
                color: #DDE6ED;
            }
            QLabel {
                color: #DDE6ED;
            }
            QCheckBox {
                color: #DDE6ED;
                font-size: 14px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("CPU Settings")
        title.setObjectName("cpuSettingsTitle")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #FDA903;")
        layout.addWidget(title)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: rgba(157, 178, 191, 0.3);")
        layout.addWidget(separator)
        
        # Apply current preset at startup checkbox
        auto_apply_cb = QCheckBox("Apply current preset at startup")
        auto_apply_cb.setObjectName("cpuAutoApplyCheckbox")
        
        # Get current value from settings
        current_value = False
        if hasattr(self, 'cpu_settings') and self.cpu_settings._settings:
            current_value = self.cpu_settings._settings.get("auto_apply_on_startup", False)
        auto_apply_cb.setChecked(current_value)
        layout.addWidget(auto_apply_cb)
        
        # Info label about what gets applied
        if hasattr(self, 'cpu_settings'):
            current_preset = self.cpu_settings.current_preset_name
            if current_preset:
                info_text = f"Will apply preset: {current_preset}"
            else:
                info_text = "Will apply current slider values"
            preset_label = QLabel(info_text)
            preset_label.setObjectName("cpuCurrentPresetLabel")
            preset_label.setStyleSheet("color: #9DB2BF; font-size: 12px; margin-top: 8px;")
            layout.addWidget(preset_label)
        
        # Keep settings applied (auto re-apply timer)
        keep_applied_cb = QCheckBox("Keep settings applied")
        keep_applied_cb.setObjectName("cpuKeepAppliedCheckbox")
        keep_applied_cb.setToolTip("Re-applies CPU settings periodically to prevent Windows/BIOS from resetting them")
        
        keep_applied_value = False
        if hasattr(self, 'cpu_settings') and self.cpu_settings._settings:
            keep_applied_value = self.cpu_settings._settings.get("keep_settings_applied", False)
        keep_applied_cb.setChecked(keep_applied_value)
        layout.addWidget(keep_applied_cb)
        
        # Reapply interval slider
        interval_layout = QHBoxLayout()
        interval_label = QLabel("Reapply interval:")
        interval_label.setStyleSheet("color: #9DB2BF; font-size: 12px;")
        interval_layout.addWidget(interval_label)
        
        interval_slider = QSlider(Qt.Horizontal)
        interval_slider.setObjectName("cpuReapplyIntervalSlider")
        # SAFETY: Minimum 300s (5 min) to prevent driver crashes from frequent RyzenAdj calls
        interval_slider.setRange(300, 1800)  # 5 min to 30 min
        interval_slider.setSingleStep(60)  # 1 minute steps
        interval_slider.setTickInterval(300)  # 5 minute ticks
        interval_slider.setTickPosition(QSlider.TicksBelow)
        
        # Get saved interval - enforce minimum 300s for safety
        saved_interval = 300  # Default 5 minutes
        if hasattr(self, 'cpu_settings') and self.cpu_settings._settings:
            saved_interval = max(300, self.cpu_settings._settings.get("reapply_interval", 300))
        interval_slider.setValue(saved_interval)
        interval_layout.addWidget(interval_slider)
        
        interval_value_label = QLabel(f"{saved_interval // 60}m")
        interval_value_label.setObjectName("cpuReapplyIntervalValue")
        interval_value_label.setStyleSheet("color: #DDE6ED; font-size: 12px; min-width: 30px;")
        interval_layout.addWidget(interval_value_label)
        
        def update_interval_label(val):
            interval_value_label.setText(f"{val // 60}m")
        interval_slider.valueChanged.connect(update_interval_label)
        
        layout.addLayout(interval_layout)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = AnimatedButton("Save")
        save_btn.setObjectName("cpuSettingsSaveButton")
        save_btn.setFixedSize(100, 40)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setHoverGradient(['#526D82', '#9DB2BF', '#DDE6ED'])
        save_btn.clicked.connect(lambda: self._save_cpu_settings(auto_apply_cb.isChecked(), keep_applied_cb.isChecked(), interval_slider.value(), dialog))
        btn_layout.addWidget(save_btn)
        
        close_btn = AnimatedButton("Close")
        close_btn.setObjectName("cpuSettingsCloseButton")
        close_btn.setFixedSize(100, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setHoverGradient(['#526D82', '#9DB2BF', '#DDE6ED'])
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _save_cpu_settings(self, auto_apply, keep_applied, interval, dialog):
        """Save CPU settings and manage auto-reapply timer."""
        if hasattr(self, 'cpu_settings') and self.cpu_settings._settings is not None:
            self.cpu_settings._settings["auto_apply_on_startup"] = auto_apply
            self.cpu_settings._settings["keep_settings_applied"] = keep_applied
            self.cpu_settings._settings["reapply_interval"] = interval
            self.cpu_settings.save()
            
            # Start or stop the auto-reapply timer based on setting
            if keep_applied:
                self._start_cpu_reapply_timer(interval)
            else:
                self._stop_cpu_reapply_timer()
        dialog.close()
    
    def _start_cpu_reapply_timer(self, interval_seconds=300):
        """Start the auto-reapply timer that re-applies CPU settings at specified interval.
        
        SAFETY: Minimum interval is 300s (5 min) to prevent driver crashes.
        """
        # Enforce minimum 300s for safety - frequent RyzenAdj calls can crash iGPU driver
        interval_seconds = max(300, interval_seconds)
        
        # Stop existing timer if any
        self._stop_cpu_reapply_timer()
        
        # Create and start new timer
        self._cpu_reapply_timer = QTimer(self)
        self._cpu_reapply_timer.timeout.connect(self._reapply_cpu_settings)
        self._cpu_reapply_timer.start(interval_seconds * 1000)  # Convert to milliseconds
        print(f"[CPU] Auto-reapply timer started ({interval_seconds // 60}m interval)")
    
    def _stop_cpu_reapply_timer(self):
        """Stop the auto-reapply timer."""
        if hasattr(self, '_cpu_reapply_timer') and self._cpu_reapply_timer:
            self._cpu_reapply_timer.stop()
            self._cpu_reapply_timer = None
            print("[CPU] Auto-reapply timer stopped")
    
    def _reapply_cpu_settings(self):
        """Re-apply current CPU settings (called by timer).
        
        Runs in background thread to prevent UI lag.
        """
        import threading
        
        def apply_in_background():
            try:
                # Get current profile from sliders if available, otherwise from saved settings
                profile = {}
                if hasattr(self, 'cpu_sliders') and self.cpu_sliders:
                    for key, (slider, label, unit) in self.cpu_sliders.items():
                        profile[key] = slider.value()
                elif hasattr(self, 'cpu_settings'):
                    profile = self.cpu_settings.profile
                else:
                    return
                
                # Apply settings silently (no popup) - runs in background
                success, error = apply_settings_direct(profile)
                if success:
                    print("[CPU] Settings re-applied successfully")
                else:
                    print(f"[CPU] Re-apply failed: {error}")
            except Exception as e:
                print(f"[CPU] Re-apply error: {e}")
        
        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=apply_in_background, daemon=True)
        thread.start()
    
    def _setup_crosshair_panel(self):
        """Setup the Crosshair overlay panel."""
        self.crosshair_panel = CrosshairWidget()
        self.crosshair_panel.setStyleSheet("""
            QWidget#crosshairPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5D8736, stop:0.33 #809D3C, stop:0.66 #A9C46C, stop:1 #F4FFC3);
            }
        """)
        self.content_stack.addWidget(self.crosshair_panel)
    
    def _setup_macro_panel(self):
        """Setup the Macro settings panel."""
        try:
            from MacroSettingsPanel import MacroSettingsPanel
            self.macro_panel = MacroSettingsPanel(self)
            self.content_stack.addWidget(self.macro_panel)
        except ImportError as e:
            # Fallback: create empty placeholder panel
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
            self.macro_panel = QWidget()
            self.macro_panel.setObjectName("macroPanel")
            layout = QVBoxLayout(self.macro_panel)
            error_label = QLabel(f"Macro system unavailable:\n{e}")
            error_label.setStyleSheet("color: #e74c3c; font-size: 16px;")
            layout.addWidget(error_label)
            self.content_stack.addWidget(self.macro_panel)
    
    def get_macro_bridge(self):
        """Get the macro bridge, initializing if needed."""
        if self._macro_bridge is None:
            try:
                from macro_system.integration import LauncherBridge
                self._macro_bridge = LauncherBridge(self)
                self._macro_bridge.initialize()
            except Exception as e:
                print(f"[MacroSystem] Failed to initialize: {e}")
                return None
        return self._macro_bridge
    
    def _on_cpu_slider_changed(self, value, label, unit, key):
        """Handle CPU slider value change."""
        label.setText(f"{value}{unit}")
        self.cpu_settings.set_value(key, value)
    
    def _on_cpu_checkbox_toggled(self, key, checked):
        """Handle CPU slider enable/disable checkbox toggle."""
        # Get current enabled_settings or create new dict
        profile = self.cpu_settings.profile
        if "enabled_settings" not in profile:
            profile["enabled_settings"] = {}
        profile["enabled_settings"][key] = checked
        self.cpu_settings.profile = profile
        print(f"[CPU] Setting {key} {'enabled' if checked else 'disabled'}")
    
    def _reset_cpu_sliders(self):
        """Reset all CPU sliders to default values."""
        defaults = get_default_profile()
        for key, (slider, label, unit) in self.cpu_sliders.items():
            default_val = defaults.get(key, slider.value())
            slider.setValue(default_val)
            label.setText(f"{default_val}{unit}")
        self.cpu_settings.profile = defaults
    
    def _apply_cpu_settings(self):
        """Apply CPU settings via RyzenAdj (primary) or UXTU (fallback).
        
        Runs in background thread to avoid blocking UI during hardware writes or UAC elevation.
        """
        # Check if any method is available
        ryzenadj_ok = is_ryzenadj_available()
        uxtu_ok = self.uxtu_installed
        
        if not ryzenadj_ok and not uxtu_ok:
            QMessageBox.warning(
                self,
                "No CPU Control Available",
                "Neither RyzenAdj nor UXTU was found.\n\n"
                "To use CPU control:\n"
                "1. Download ryzenadj.exe from GitHub\n"
                "2. Place it in the 'assets' folder"
            )
            return
        
        # Gather current slider values
        profile = {}
        for key, (slider, label, unit) in self.cpu_sliders.items():
            profile[key] = slider.value()
        
        # Define the background worker
        def run_apply_background():
            import threading
            print(f"[CPU] Applying settings in background thread...")
            # Apply settings (RyzenAdj is primary, UXTU fallback)
            success, error = apply_settings_direct(profile)
            
            # Show result in main thread
            def show_result():
                if success:
                    method = "RyzenAdj" if ryzenadj_ok else "UXTU"
                    QMessageBox.information(
                        self,
                        "Settings Applied",
                        f"CPU settings applied successfully via {method}!"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Application Failed",
                        f"Failed to apply settings:\n\n{error}\n\n"
                        "Try running the launcher as administrator."
                    )
            
            # Schedule UI update on main thread
            QTimer.singleShot(0, show_result)
            
        # Run in background to prevent UI freeze (especially during 2s sleep in elevated path)
        import threading
        apply_thread = threading.Thread(target=run_apply_background, daemon=True)
        apply_thread.start()
    
    def _refresh_preset_combo(self):
        """Refresh the preset dropdown with current presets."""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        
        # Add existing presets
        preset_names = self.cpu_settings.get_preset_names()
        for name in preset_names:
            self.preset_combo.addItem(name)
        
        # Set current preset
        current = self.cpu_settings.current_preset_name
        if current:
            idx = self.preset_combo.findText(current)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            else:
                self.preset_combo.setCurrentText(current)
        
        self.preset_combo.blockSignals(False)
    
    def _on_preset_selected(self, text):
        """Handle preset selection from dropdown."""
        if not text:
            return
        
        # Check if this is an existing preset
        if text in self.cpu_settings.get_preset_names():
            # Load the preset
            if self.cpu_settings.load_preset(text):
                # Update sliders to reflect loaded values
                profile = self.cpu_settings.profile
                for key, (slider, label, unit) in self.cpu_sliders.items():
                    val = profile.get(key, slider.value())
                    slider.blockSignals(True)
                    slider.setValue(val)
                    slider.blockSignals(False)
                    label.setText(f"{val}{unit}")
    
    def _save_current_preset(self):
        """Save current slider values as a preset."""
        preset_name = self.preset_combo.currentText().strip()
        
        if not preset_name:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Please enter a preset name."
            )
            return
        
        # Check if overwriting existing
        if preset_name in self.cpu_settings.get_preset_names():
            reply = QMessageBox.question(
                self,
                "Overwrite Preset",
                f"Preset '{preset_name}' already exists.\n\nDo you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        # Gather current slider values
        profile = {}
        for key, (slider, label, unit) in self.cpu_sliders.items():
            profile[key] = slider.value()
        
        # Save preset
        self.cpu_settings.save_preset(preset_name, profile)
        self._refresh_preset_combo()
        
        QMessageBox.information(
            self,
            "Preset Saved",
            f"Preset '{preset_name}' has been saved."
        )
    
    def _delete_current_preset(self):
        """Delete the currently selected preset."""
        preset_name = self.preset_combo.currentText().strip()
        
        if not preset_name:
            return
        
        if preset_name not in self.cpu_settings.get_preset_names():
            QMessageBox.warning(
                self,
                "Not Found",
                f"Preset '{preset_name}' does not exist."
            )
            return
        
        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Are you sure you want to delete preset '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.cpu_settings.delete_preset(preset_name)
            self._refresh_preset_combo()
            QMessageBox.information(
                self,
                "Preset Deleted",
                f"Preset '{preset_name}' has been deleted."
            )

    def refresh_library(self):
        """Reload the game library from config.json and re-extract all icons"""
        self.data = load_json()
        
        # Re-extract icons for all games in background
        def extract_icons_background():
            updated = False
            for i, game in enumerate(self.data):
                exe_path = game.get("exe", "")
                if exe_path and os.path.exists(exe_path):
                    print(f"[Refresh] Extracting icon {i+1}/{len(self.data)}: {os.path.basename(exe_path)}")
                    icon_path = extract_icon_from_exe(exe_path)
                    if icon_path:
                        game["icon"] = icon_path
                        updated = True
            
            if updated:
                save_json(self.data)
            
            # Refresh UI on main thread
            QTimer.singleShot(0, self.refresh)
            print(f"[Refresh] Icon extraction complete for {len(self.data)} games")
        
        # Run in background thread
        import threading
        thread = threading.Thread(target=extract_icons_background, daemon=True)
        thread.start()
        
        # Immediate refresh to show current state
        self.refresh()
    
    def sort_az(self):
        games = load_json()
        games.sort(key=lambda g: (g.get("name", "") or g.get("exe", "")).lower())
        save_json(games)
        self.refresh()
    
    def _on_drag_enter(self, event):
        """Handle drag enter event - accept .exe and .lnk files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile().lower()
                if file_path.endswith('.exe') or file_path.endswith('.lnk'):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def _on_drop(self, event):
        """Handle drop event - add .exe and .lnk files to library."""
        if event.mimeData().hasUrls():
            added = 0
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                
                # Handle .lnk shortcut files
                if file_path.lower().endswith('.lnk') and os.path.exists(file_path):
                    target_path = self._resolve_shortcut(file_path)
                    # Use shortcut filename as game name (better than exe name)
                    shortcut_name = os.path.splitext(os.path.basename(file_path))[0]
                    if target_path and target_path.lower().endswith('.exe') and os.path.exists(target_path):
                        if self._add_exe_to_library(target_path, custom_name=shortcut_name):
                            added += 1
                # Handle .exe files directly
                elif file_path.lower().endswith('.exe') and os.path.exists(file_path):
                    if self._add_exe_to_library(file_path):
                        added += 1
            
            if added > 0:
                self.refresh()
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Added Successfully",
                    f"Added {added} game(s) to library!"
                )
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def _resolve_shortcut(self, lnk_path: str) -> str:
        """Resolve .lnk shortcut to get target path."""
        # Method 1: Binary parsing (works everywhere, no COM dependency)
        try:
            with open(lnk_path, 'rb') as f:
                content = f.read()
            
            # LNK file structure: header (76 bytes) + shell item ID list + link info
            # Check for LNK magic bytes
            if content[:4] != b'\x4c\x00\x00\x00':
                raise ValueError("Not a valid LNK file")
            
            # Flags at offset 0x14
            flags = int.from_bytes(content[0x14:0x18], 'little')
            has_shell_item_id = flags & 0x01
            has_link_info = flags & 0x02
            
            pos = 0x4C  # Start after header
            
            # Skip shell item ID list if present
            if has_shell_item_id:
                shell_item_size = int.from_bytes(content[pos:pos+2], 'little')
                pos += 2 + shell_item_size
            
            # Parse link info if present
            if has_link_info:
                link_info_size = int.from_bytes(content[pos:pos+4], 'little')
                link_info = content[pos:pos+link_info_size]
                
                # Local base path offset at offset 0x10 in link info
                local_base_path_offset = int.from_bytes(link_info[0x10:0x14], 'little')
                if local_base_path_offset > 0:
                    # Extract null-terminated string
                    path_start = local_base_path_offset
                    path_end = link_info.find(b'\x00', path_start)
                    target_path = link_info[path_start:path_end].decode('cp1252', errors='ignore')
                    if target_path and os.path.exists(target_path):
                        return target_path
        except Exception as e:
            print(f"[DragDrop] Binary parsing failed: {e}")
        
        # Method 2: pythoncom (may not work in PyInstaller)
        try:
            import pythoncom
            from win32com.shell import shell
            
            pythoncom.CoInitialize()
            try:
                link = pythoncom.CoCreateInstance(
                    shell.CLSID_ShellLink, None,
                    pythoncom.CLSCTX_INPROC_SERVER,
                    shell.IID_IShellLink
                )
                persist = link.QueryInterface(pythoncom.IID_IPersistFile)
                persist.Load(lnk_path)
                target_path, _ = link.GetPath(shell.SLGP_RAWPATH)
                return target_path if target_path else None
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            print(f"[DragDrop] pythoncom failed: {e}")
        
        return None
    
    def _add_exe_to_library(self, exe_path: str, custom_name: str = None) -> bool:
        """Add an .exe file to the game library."""
        # Check if already exists
        games = load_json()
        for game in games:
            if game.get("exe", "").lower() == exe_path.lower():
                print(f"[DragDrop] {exe_path} already in library")
                return False
        
        # Use custom name if provided, otherwise extract from filename
        if custom_name:
            name = custom_name
        else:
            name = os.path.splitext(os.path.basename(exe_path))[0]
        
        # Extract icon
        icon_path = None
        icons_dir = os.path.join(APPDATA_DIR, "icons")
        os.makedirs(icons_dir, exist_ok=True)
        
        try:
            if NATIVE_CPP_AVAILABLE and get_icon_extractor:
                extractor = get_icon_extractor()
                icon_path = extractor.extract_icon(exe_path, os.path.join(icons_dir, f"{name}.png"))
            
            if not icon_path or not os.path.exists(icon_path):
                # Fallback: use Windows API
                from PIL import Image
                import win32ui
                import win32gui
                import win32api
                import win32con
                
                ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
                ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)
                
                large, small = win32gui.ExtractIconEx(exe_path, 0)
                if large:
                    hicon = large[0]
                    hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                    hbmp = win32ui.CreateBitmap()
                    hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
                    hdc = hdc.CreateCompatibleDC()
                    hdc.SelectObject(hbmp)
                    hdc.DrawIcon((0, 0), hicon)
                    
                    bmpinfo = hbmp.GetInfo()
                    bmpstr = hbmp.GetBitmapBits(True)
                    img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)
                    
                    icon_path = os.path.join(icons_dir, f"{name}.png")
                    img.save(icon_path)
                    
                    win32gui.DestroyIcon(hicon)
                    for h in large[1:] + small:
                        win32gui.DestroyIcon(h)
        except Exception as e:
            print(f"[DragDrop] Failed to extract icon: {e}")
        
        # Create game entry
        new_game = {
            "name": name,
            "exe": exe_path,
            "icon": icon_path or "",
            "notes": "",
            "category": "",
            "tags": [],
            "favorite": False,
            "hidden": False,
            "launch_options": "",
            "play_time_seconds": 0,
            "last_played": "",
            "first_played": "",
            "date_added": "",
            "session_history": [],
            "genre": "",
            "developer": "",
            "app_type": "game"
        }
        
        games.append(new_game)
        save_json(games)
        print(f"[DragDrop] Added {name} to library from drag & drop")
        return True
        
    def clear_grid(self):
        """Clear all items from the grid"""
        # Clear selected button reference to prevent stale references
        AnimatedGameButton._selected_button = None
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i).widget()
            if item:
                item.setParent(None)
    
    def populate_recently_played(self):
        """Populate the Recently Played section with last 5 played games."""
        # Clear ALL items (including title) and rebuild fresh
        while self.recently_played_layout.count() > 0:
            item = self.recently_played_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        
        # Get games with last_played timestamp, sorted by most recent
        played_games = [g for g in self.data if g.get("last_played")]
        played_games.sort(key=lambda g: g.get("last_played", "") or "", reverse=True)
        recent = played_games[:5]  # Top 5
        
        if not recent:
            # Hide the section if no recently played
            self.recently_played_widget.hide()
            return
        
        self.recently_played_widget.show()
        
        # Add "Currently Playing" label if a game is running (not utilities)
        if self.current_session:
            game = self.current_session.get("game", {})
            game_name = game.get("name", "Unknown")
            
            # Skip if this is a utility, not a game
            app_type = game.get("app_type", "game")
            if app_type != "utility":
                # Use window title detection to determine launcher vs game
                game_status = self._is_in_game_by_window_title(game)
                
                # Build the label text based on whether we're in launcher or game
                if game_status == "game":
                    status_text = f"Playing: {game_name}"
                    status_color = "#4CAF50"  # Green for playing
                elif game_status == "launcher":
                    status_text = f"{game_name} Launcher"
                    status_color = "#FFA726"  # Orange for launcher
                else:
                    # Unknown - default to process-based detection
                    game_exe_list = game.get("game_exe", "")
                    if game_exe_list:
                        # Check if any of the actual game processes are running
                        for game_exe in game_exe_list.split(","):
                            exe_name = game_exe.strip().lower()
                            if exe_name and self._is_process_running(exe_name):
                                status_text = f"Playing: {game_name}"
                                status_color = "#4CAF50"
                                break
                        else:
                            status_text = f"{game_name} Launcher"
                            status_color = "#FFA726"
                    else:
                        status_text = f"Playing: {game_name}"
                        status_color = "#4CAF50"
                
                # Truncate if too long
                if len(status_text) > 30:
                    status_text = status_text[:29] + "…"
                
                # Create currently playing label with pulsing green dot
                playing_label = QLabel(status_text)
                playing_label.setObjectName("currentlyPlayingLabel")
                playing_label.setStyleSheet(f"""
                    QLabel {{
                        font-size: 13px;
                        color: {status_color};
                        font-weight: bold;
                        background: rgba(0, 0, 0, 0.65);
                        border: none;
                        border-radius: 8px;
                        padding: 5px 12px;
                    }}
                """)
                self.recently_played_layout.addWidget(playing_label)
                
                # Add separator
                separator = QLabel("|")
                separator.setStyleSheet("color: #555555; font-size: 16px; margin: 0 5px;")
                self.recently_played_layout.addWidget(separator)
        
        # Add "Recently Played" label
        title_label = QLabel("Recently Played:")
        title_label.setStyleSheet("font-size: 13px; color: #FFFFFF; font-weight: bold;")
        self.recently_played_layout.addWidget(title_label)
        
        # Add each recently played game as a small clickable button
        for game in recent:
            btn = AnimatedButton()
            btn.setFixedSize(120, 40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setHoverGradient(['#F443A2', '#FE5500', '#FE0800', '#FFAB00'])  # Game panel gradient
            
            # Truncate name if too long
            name = game.get("name", "Unknown")
            if len(name) > 12:
                name = name[:11] + "…"
            btn.setText(name)
            
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 30, 30, 0.8);
                    border: 1px solid rgba(255, 91, 6, 0.5);
                    border-radius: 5px;
                    padding: 5px;
                    color: #e0e0e0;
                    font-size: 11px;
                    text-align: left;
                }
                QPushButton:hover {
                    background: rgba(255, 91, 6, 0.3);
                    border: 1px solid #FF5B06;
                }
            """)
            
            btn.doubleClicked.connect(lambda p=game.get("exe", ""): self.launch_game(p))
            btn.setToolTip(f"Double-click to launch {game.get('name', '')}")
            self.recently_played_layout.addWidget(btn)
        
        self.recently_played_layout.addStretch()
                
    def reflow_grid(self):
        """Quickly re-layout existing items in the grid based on current window width."""
        if not hasattr(self, 'game_buttons') or not self.game_buttons:
            return
            
        if not hasattr(self, "grid"):
            return
            
        # Calculate number of columns based on available width
        tile_size = getattr(self, "grid_size", 100) + 80
        grid_spacing = 20
        scrollbar_width = 20
        # self.width() includes the 80px sidebar, and containers have ~20px margins
        sidebar_and_margins = 100 
        available_width = self.width() - sidebar_and_margins - scrollbar_width - grid_spacing
        
        num_columns = max(1, int((available_width + grid_spacing) / (tile_size + grid_spacing)))
        
        # Don't reflow if columns haven't changed
        if hasattr(self, '_last_num_columns') and self._last_num_columns == num_columns:
            return
        self._last_num_columns = num_columns
            
        # Collect all active items from grid (tile_container widgets)
        items = []
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            if item and item.widget():
                items.append(item.widget())
                
        if not items:
            return
                
        # Remove them from the layout (without deleting the widgets)
        for i in reversed(range(self.grid.count())):
            self.grid.takeAt(i)
            
        # Re-add to grid with new column alignment
        col = 0
        row = 0
        for item in items:
            self.grid.addWidget(item, row, col, Qt.AlignLeft | Qt.AlignTop)
            col += 1
            if col >= num_columns:
                col = 0
                row += 1
                
    def refresh(self):
        # Reload data from config.json
        self.data = load_json()
        
        # Clear keyboard navigation state
        self.game_buttons = []
        self.selected_game_index = -1
        
        # Clear the grid
        self.clear_grid()
        
        # Clear and populate Recently Played section
        self.populate_recently_played()

        # Calculate number of columns based on available width
        # Account for: scrollbar (~20px), grid spacing (20px per gap), container margins
        tile_size = self.grid_size + 80  # Match the tile_size calculation used below
        grid_spacing = 20  # From self.grid.setSpacing(20)
        scrollbar_width = 20  # Approximate scrollbar width
        # Account for 80px sidebar and ~20px container margins
        sidebar_and_margins = 100
        available_width = self.width() - sidebar_and_margins - scrollbar_width - grid_spacing
        
        # Calculate max columns that fit without clipping
        # Each tile needs tile_size + spacing (except last one)
        # So: num_columns * tile_size + (num_columns - 1) * spacing <= available_width
        # Solving: num_columns <= (available_width + spacing) / (tile_size + spacing)
        num_columns = max(1, int((available_width + grid_spacing) / (tile_size + grid_spacing)))
        
        # Filter and sort games
        show_hidden = self.settings.get("show_hidden_games", False)
        games_to_show = []
        
        for game in self.data:
            # Filter hidden games
            if game.get("hidden", False) and not show_hidden:
                continue
            
            # Apply search filter by game name (case-insensitive)
            if self.search_query:
                if self.search_query not in game.get("name", "").lower():
                    continue
            
            # Apply type filter (All / Games / Utilities)
            filter_combo = getattr(self, 'filter_combo', None)
            current_filter = filter_combo.currentText() if filter_combo else "All"
            if current_filter != "All":
                exe_path = game.get("exe", "")
                # Check for manual override first
                manual_type = game.get("app_type", "auto")
                if manual_type == "game":
                    app_type = "game"
                elif manual_type == "utility":
                    app_type = "utility"
                else:
                    app_type = self.detect_app_type(exe_path)
                
                if current_filter == "Games" and app_type != "game":
                    continue
                if current_filter == "Utilities" and app_type != "utility":
                    continue
            
            games_to_show.append(game)
        
        # Update game counter
        self.game_counter.setText(f"{len(games_to_show)} Game{'s' if len(games_to_show) != 1 else ''}")
        
        # Get sort mode from dropdown
        sort_mode = getattr(self, 'sort_combo', None)
        sort_text = sort_mode.currentText() if sort_mode else "Name (A-Z)"
        
        # Sort favorites first, then apply user's sort preference
        favorites = [g for g in games_to_show if g.get("favorite", False)]
        non_favorites = [g for g in games_to_show if not g.get("favorite", False)]
        
        # Apply sort to both lists
        def apply_sort(game_list, sort_text):
            if sort_text == "Name (A-Z)":
                game_list.sort(key=lambda g: g.get("name", "").lower())
            elif sort_text == "Name (Z-A)":
                game_list.sort(key=lambda g: g.get("name", "").lower(), reverse=True)
            elif sort_text == "Last Played":
                game_list.sort(key=lambda g: g.get("last_played", "") or "", reverse=True)
            elif sort_text == "Play Time":
                game_list.sort(key=lambda g: g.get("play_time_seconds", 0), reverse=True)
            elif sort_text == "Date Added":
                game_list.sort(key=lambda g: g.get("date_added", "") or "", reverse=True)
        
        apply_sort(favorites, sort_text)
        apply_sort(non_favorites, sort_text)
        
        games_to_show = favorites + non_favorites
        
        # Render the grid icons
        col = 0
        row = 0
        for game in games_to_show:

            # Resolve icon path. Supports:
            # - absolute paths
            # - legacy relative paths like 'icons\\TLauncher.png' stored in config.json
            #   which used to be relative to the project root
            # We try SCRIPT_DIR first (python folder), then the parent (project root).
            raw_icon = game.get("icon")
            icon_path = None
            if raw_icon:
                candidates = []
                if os.path.isabs(raw_icon):
                    candidates.append(raw_icon)
                else:
                    # python/icons/...
                    candidates.append(os.path.join(SCRIPT_DIR, raw_icon))
                    # project-root/icons/...
                    project_root = os.path.dirname(SCRIPT_DIR)
                    candidates.append(os.path.join(project_root, raw_icon))

                for candidate in candidates:
                    if os.path.exists(candidate):
                        icon_path = candidate
                        break

            # Calculate sizes
            tile_size = self.grid_size + 80
            icon_thumb_size = int(tile_size * 0.7)  # Icon takes more space now
            
            # Calculate fixed tile height to prevent overlap
            # Height = icon + spacing + max label height
            max_label_height = 50  # Slightly reduced to ensure fit
            tile_height = icon_thumb_size + 4 + max_label_height
            
            # Create container widget for the entire game tile
            tile_container = QWidget()
            tile_container.setFixedSize(tile_size, tile_height)
            tile_container.setStyleSheet("background: transparent;")
            tile_layout = QVBoxLayout(tile_container)
            tile_layout.setContentsMargins(0, 0, 0, 0)
            tile_layout.setSpacing(4)
            tile_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

            # Create the icon button with animation (orange border) - contains ONLY the icon
            btn = AnimatedGameButton()
            btn.setObjectName("gameBtn")  # Allows CSS override to strip the global orange border
            btn.setFixedSize(icon_thumb_size, icon_thumb_size)
            btn.base_size = icon_thumb_size
            
            # Auto-fix missing icons (path doesn't exist, is empty, or is in temp folder)
            needs_reextract = False
            if not icon_path:
                # Icon path is empty - need to extract
                needs_reextract = True
                print(f"[Icon] Empty icon path for: {game.get('name', 'Unknown')}")
            elif not os.path.exists(icon_path):
                # Icon file doesn't exist
                needs_reextract = True
                print(f"[Icon] Icon file not found: {icon_path}")
            elif "Temp" in icon_path or "_MEI" in icon_path or "\\Temp\\" in icon_path:
                # Icon is in a temp folder that may be deleted
                needs_reextract = True
                print(f"[Icon] Icon in temp folder: {icon_path}")
                
            if needs_reextract and game.get("exe") and os.path.exists(game["exe"]):
                print(f"[Icon] Re-extracting icon for: {game.get('name', 'Unknown')}")
                try:
                    new_icon = extract_icon_from_exe(game["exe"])
                    if new_icon:
                        game["icon"] = new_icon
                        icon_path = new_icon
                        # Mark config for save
                        self._needs_config_save = True
                        print(f"[Icon] Updated icon path: {new_icon}")
                except Exception as e:
                    print(f"[Icon] Re-extract failed: {e}")
            
            if icon_path and os.path.exists(icon_path):
                # --- Generic icon detection ---
                # If the icon belongs to a generic engine/store (Unity, Unreal,
                # Epic, etc.), replace it with a text icon showing the game title.
                exe_path = game.get("exe", "")
                is_generic = _is_generic_icon(icon_path, exe_path)
                
                if is_generic:
                    cache_key = f"_texticon_{game.get('name', '')}_{icon_thumb_size}"
                    if cache_key in GameLauncher._icon_cache:
                        btn.setIcon(GameLauncher._icon_cache[cache_key])
                        btn.setIconSize(QSize(icon_thumb_size - 16, icon_thumb_size - 16))
                    else:
                        # Generate a text icon with the game's title
                        text_pixmap = _create_text_icon(
                            game.get("name", "?"), icon_thumb_size - 16
                        )
                        icon = QIcon(text_pixmap)
                        GameLauncher._icon_cache[cache_key] = icon
                        btn.setIcon(icon)
                        btn.setIconSize(QSize(icon_thumb_size - 16, icon_thumb_size - 16))
                        print(f"[Icon] Generic icon replaced with text: {game.get('name', '?')}")
                else:
                    # --- Normal icon loading ---
                    # Use cached icon if available
                    # Cache key includes version so logic changes invalidate old cached icons
                    cache_key = f"{icon_path}_{icon_thumb_size}_{_BG_ICON_VERSION}"
                    if cache_key in GameLauncher._icon_cache:
                        btn.setIcon(GameLauncher._icon_cache[cache_key])
                        btn.setIconSize(QSize(icon_thumb_size - 16, icon_thumb_size - 16))
                    else:
                        # Load and cache the icon
                        pixmap = QPixmap()
                        if pixmap.load(icon_path):
                            # Use SmoothTransformation for bilinear filtering (better quality)
                            scaled_pixmap = pixmap.scaled(
                                icon_thumb_size - 16,
                                icon_thumb_size - 16,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                            # Add shape-matching background color.
                            # This makes the background follow the icon's actual shape
                            # (rounded for rounded icons, circular for circular, etc.)
                            scaled_pixmap = _create_shaped_bg_icon(scaled_pixmap)
                            icon = QIcon(scaled_pixmap)
                            GameLauncher._icon_cache[cache_key] = icon
                            btn.setIcon(icon)
                            btn.setIconSize(QSize(icon_thumb_size - 16, icon_thumb_size - 16))
            
            # NOTE: Semi-transparent black background is now baked into the
            # icon pixmap itself via _create_shaped_bg_icon(), matching the
            # icon's actual shape. No CSS background needed on the button.

            # Tooltip with game info (shown on hover)
            tooltip_parts = [game.get('name', '')]
            if game.get("category"):
                tooltip_parts.append(f"Category: {game['category']}")
            if game.get("notes"):
                tooltip_parts.append(game["notes"])
            # Show play time
            play_time_secs = game.get("play_time_seconds", 0)
            if play_time_secs > 0:
                hours = play_time_secs // 3600
                minutes = (play_time_secs % 3600) // 60
                if hours > 0:
                    tooltip_parts.append(f"⏱ {hours}h {minutes}m played")
                else:
                    tooltip_parts.append(f"⏱ {minutes}m played")
            if game.get("last_played"):
                try:
                    last = datetime.fromisoformat(game["last_played"])
                    tooltip_parts.append(f"Last played: {last.strftime('%Y-%m-%d %H:%M')}")
                except:
                    pass
            if game.get("favorite"):
                tooltip_parts.insert(1, "★ Favorite")
            tooltip_text = "\n".join(tooltip_parts)
            btn.setToolTip(tooltip_text + "\n\n💡 Double-click to launch")

            # Connect double-click to launch game (single-click shows info)
            btn.doubleClicked.connect(lambda p=game["exe"]: self.launch_game(p))

            # Add right-click context menu to button
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, g=game, b=btn: self.show_context_menu(pos, g, b))

            # Create the title label (OUTSIDE the button)
            raw_name = game.get("name", "")
            # If name is all uppercase, convert to title case (e.g., "METAL GEAR" -> "Metal Gear")
            if raw_name.isupper():
                raw_name = raw_name.title()
            # Insert spaces before a capital letter ONLY when it follows a lowercase letter or digit
            # (genuine PascalCase split: "MyGame" -> "My Game", "REPOold" -> "Repository old")
            # This avoids splitting consecutive caps like "REPO" into "R E P O"
            display_name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw_name).strip() or raw_name
            text_label = QLabel(display_name)
            
            # Calculate font size (ensure it's at least 8pt)
            font_size = max(9, int(self.grid_size * 0.11))
            text_color = getattr(self, '_game_text_color', '#e0e0e0')
            font_weight = '700' if getattr(self, '_has_bg_image', False) else 'normal'
            # Get dynamic opacity based on image brightness (set in apply_theme)
            title_opacity = getattr(self, '_title_bg_opacity', 0.50) if getattr(self, '_has_bg_image', False) else 0
            title_bg = f'rgba(0, 0, 0, {title_opacity})' if title_opacity > 0 else 'transparent'
            text_label.setStyleSheet(f"""
                QLabel {{
                    font-size: {font_size}pt;
                    font-weight: {font_weight};
                    color: {text_color};
                    padding: 2px 6px;
                    background: {title_bg};
                    border-radius: 4px;
                }}
            """)
            text_label.setWordWrap(True)
            text_label.setAlignment(Qt.AlignCenter)
            text_label.setFixedWidth(tile_size)
            text_label.setMaximumHeight(max_label_height)  # Match tile_height calculation

            # Add button and label to container
            tile_layout.addWidget(btn, 0, Qt.AlignCenter)
            tile_layout.addWidget(text_label, 0, Qt.AlignCenter)
            
            # Add star icon for favorite games (positioned at top-left of tile)
            if game.get("favorite", False):
                star_label = QLabel("★", btn)  # Parent to button for overlay
                star_label.setObjectName("favoriteStarLabel")
                star_label.setStyleSheet("""
                    QLabel#favoriteStarLabel {
                        color: #FFD700;
                        font-size: 18px;
                        font-weight: bold;
                        background: rgba(0, 0, 0, 0.6);
                        border-radius: 4px;
                        padding: 2px 4px;
                    }
                """)
                star_label.adjustSize()
                star_label.move(5, 5)  # Position at top-left with small margin
                star_label.show()

            # Add the container to the grid
            self.grid.addWidget(tile_container, row, col, Qt.AlignLeft | Qt.AlignTop)
            
            # Store button for keyboard navigation
            self.game_buttons.append((btn, game))
            
            # Track hovered game for DELETE key
            def make_hover_handlers(g, orig_enter, orig_leave):
                def on_enter(event):
                    self._hovered_game = g
                    if orig_enter:
                        orig_enter(event)
                def on_leave(event):
                    if self._hovered_game == g:
                        self._hovered_game = None
                    if orig_leave:
                        orig_leave(event)
                return on_enter, on_leave
            enter_handler, leave_handler = make_hover_handlers(game, btn.enterEvent, btn.leaveEvent)
            btn.enterEvent = enter_handler
            btn.leaveEvent = leave_handler

            col += 1
            if col >= num_columns:
                col = 0
                row += 1
        
        # Save config if any icons were re-extracted
        if getattr(self, '_needs_config_save', False):
            print("[Icon] Saving config with re-extracted icons...")
            save_json(self.data)
            self._needs_config_save = False


    def on_search_text_changed(self, text):
        self.search_query = text.strip().lower()
        self.refresh()

    def on_sort_changed(self, text):
        """Handle sort dropdown change."""
        self.refresh()

    def on_filter_changed(self, text):
        """Handle filter dropdown change."""
        self.refresh()
    
    def detect_app_type(self, exe_path):
        """Advanced detection to classify app as game or utility.
        
        Uses multiple detection layers:
        1. Known Steam utility app IDs (most reliable)
        2. App name keyword matching
        3. Exe name pattern matching  
        4. Steam manifest category detection
        5. Path-based fallback
        """
        path_lower = exe_path.lower().replace("\\", "/")
        
        # === Layer 1: Known Steam Utility App IDs ===
        # These are Steam apps that are utilities, not games
        STEAM_UTILITY_APPIDS = {
            "431960": "Wallpaper Engine",
            "1118310": "Wallpaper Engine Workshop",
            "250820": "SteamVR",
            "323180": "SteamVR Environments",
            "755870": "Steam Linux Runtime",
            "1070560": "Steam Artcraft",
            "1493710": "Proton Experimental",
            "228980": "Steamworks Common Redistributables",
            "1391110": "Steam Deck",
            "976310": "Source SDK Base 2007",
            "205100": "Source Filmmaker",
            "323850": "Source SDK 2013 Multiplayer",
            "243750": "Source SDK 2013 Singleplayer",
            "1887720": "Stream Deck Plugin",
            "870780": "Control Panel",
        }
        
        # Try to extract Steam AppID from path
        if "steamapps/common/" in path_lower:
            # Check for known utility game names in path
            steam_utility_names = [
                "wallpaper engine", "wallpaper",
                "steamvr", "steam vr",
                "source sdk", "source filmmaker",
                "proton", "linux runtime",
                "redistributable", "redist",
            ]
            for name in steam_utility_names:
                if name in path_lower:
                    return "utility"
        
        # === Layer 2: App Name Keyword Detection ===
        # Get app name from the game data if available
        app_name = ""
        for game in getattr(self, 'data', []):
            if game.get("exe", "").lower().replace("\\", "/") == path_lower:
                app_name = game.get("name", "").lower()
                break
        
        # Utility app name keywords (case-insensitive)
        utility_name_keywords = [
            "wallpaper engine", "wallpaper",
            "obs studio", "obs",
            "discord", "spotify", "steam client",
            "nvidia", "geforce", "geforce experience",
            "amd software", "radeon", "adrenalin",
            "razer synapse", "razer cortex",
            "logitech g hub", "logitech gaming",
            "corsair icue", "icue",
            "omen gaming hub", "omen command center",
            "msi afterburner", "msi dragon center",
            "armoury crate", "asus gpu tweak",
            "voicemeeter", "equalizer apo", "peace",
            "steelseries gg", "steelseries engine",
            "hwinfo", "cpu-z", "gpu-z",
            "msi kombustor", "furmark",
            "afterburner", "rivatuner",
            "driver", "launcher", "updater",
            "benchmark", "settings", "control panel",
        ]
        
        for keyword in utility_name_keywords:
            if keyword in app_name:
                return "utility"
        
        # === Layer 3: Exe Name Pattern Detection ===
        exe_name = path_lower.split("/")[-1] if "/" in path_lower else path_lower
        
        utility_exe_patterns = [
            "launcher", "updater", "setup", "install",
            "unins", "config", "settings",
            "helper", "service", "daemon",
            "crash", "report", "diagnostic",
        ]
        
        for pattern in utility_exe_patterns:
            if pattern in exe_name and exe_name != pattern + ".exe":
                # Avoid false positives - launchers for games are ok
                if "game" not in exe_name:
                    return "utility"
        
        # === Layer 4: Steam Manifest Detection ===
        # Try to read Steam's appmanifest files for app type
        if "steamapps/common/" in path_lower:
            try:
                # Extract steam library path
                steam_path_match = path_lower.split("steamapps/common/")[0]
                manifest_dir = steam_path_match + "steamapps/"
                
                import os
                import re
                
                # Find the game folder name
                after_common = path_lower.split("steamapps/common/")[1]
                game_folder = after_common.split("/")[0]
                
                # Look for manifest files
                manifest_dir_real = manifest_dir.replace("/", "\\")
                if os.path.exists(manifest_dir_real):
                    for f in os.listdir(manifest_dir_real):
                        if f.startswith("appmanifest_") and f.endswith(".acf"):
                            manifest_path = os.path.join(manifest_dir_real, f)
                            try:
                                with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as mf:
                                    content = mf.read()
                                    # Check if this manifest is for our game
                                    if f'"installdir"\\s+"' in content.lower() or game_folder.lower() in content.lower():
                                        # Look for app type indicators
                                        if '"type"' in content.lower():
                                            if '"tool"' in content.lower() or '"application"' in content.lower():
                                                return "utility"
                            except:
                                pass
            except Exception as e:
                pass  # Silently fail and continue with other detection methods
        
        # === Layer 5: Path-Based Fallback ===
        # Known utility folder patterns (not in Steam)
        utility_path_patterns = [
            "/program files/", "/program files (x86)/",
            "/appdata/", "/programdata/",
        ]
        
        # Check for specific utility folders outside Steam
        non_steam_utility_folders = [
            "/obs-studio/", "/discord/", "/spotify/",
            "/nvidia corporation/", "/amd/", "/razer/",
            "/logitech/", "/corsair/", "/steelseries/",
            "/voicemeeter/", "/equalizer apo/",
        ]
        
        for pattern in non_steam_utility_folders:
            if pattern in path_lower:
                return "utility"
        
        # If in Program Files but not a known utility, still likely utility
        if any(p in path_lower for p in utility_path_patterns):
            # Unless it's clearly a game
            game_indicators = ["/games/", "/game/", "steamapps", "epic games", "gog galaxy"]
            if not any(g in path_lower for g in game_indicators):
                return "utility"
        
        # Games folder is definitely games
        if "/games/" in path_lower or "/game/" in path_lower:
            return "game"
        
        # Steam common folder is typically games
        if "steamapps/common/" in path_lower:
            return "game"
        
        # Epic Games folder
        if "epic games/" in path_lower:
            return "game"
        
        # Default to game
        return "game"
    
    def update_grid_size(self):
        base = 50 + (getattr(self, "icon_scale", 1) - 1) * 16.67
        # Only icon_scale should affect icon size; UI scale is for controls
        self.grid_size = base

    def change_grid_size(self, value):
        # Update icon scale (1-10) and recompute actual pixel size with
        self.icon_scale = value
        self.update_grid_size()
        self.refresh()
    
    def eventFilter(self, obj, event):
        """Global event filter for keyboard shortcuts."""
        # Guard against recursion
        if hasattr(self, '_in_event_filter') and self._in_event_filter:
            return False
        
        try:
            self._in_event_filter = True
            
            from PySide6.QtCore import QEvent, Qt
            from PySide6.QtWidgets import QLineEdit
            
            # Only handle key press events on music panel (index 1)
            if event.type() == QEvent.KeyPress:
                if hasattr(self, 'content_stack') and self.content_stack.currentIndex() == 1:
                    if hasattr(self, 'music_panel') and self.music_panel:
                        key = event.key()
                        focus_widget = QApplication.focusWidget()
                        
                        # Skip if typing in input
                        if isinstance(focus_widget, QLineEdit):
                            return False
                        
                        # Space: Toggle play/pause
                        if key == Qt.Key_Space:
                            self.music_panel._toggle_play()
                            return True
                        # P: Previous track
                        elif key == Qt.Key_P:
                            self.music_panel._prev_track()
                            return True
                        # N: Next track
                        elif key == Qt.Key_N:
                            self.music_panel._next_track()
                            return True
                        # Left Arrow: Rewind 5 seconds
                        elif key == Qt.Key_Left:
                            current_pos = self.music_panel._player.position()
                            new_pos = max(0, current_pos - 5000)
                            self.music_panel._player.setPosition(new_pos)
                            return True
                        # Right Arrow: Forward 5 seconds
                        elif key == Qt.Key_Right:
                            current_pos = self.music_panel._player.position()
                            duration = self.music_panel._player.duration()
                            new_pos = min(duration, current_pos + 5000)
                            self.music_panel._player.setPosition(new_pos)
                            return True
                        # L: Loop toggle
                        elif key == Qt.Key_L:
                            self.music_panel.player_bar._toggle_loop()
                            return True
                        # R: Shuffle toggle
                        elif key == Qt.Key_R:
                            self.music_panel.player_bar._toggle_shuffle()
                            return True
            
            return False
        except Exception:
            return False
        finally:
            self._in_event_filter = False
    
    def select_game(self, index):
        """Select a game by index and update visual feedback."""
        if index < 0 or index >= len(self.game_buttons):
            return
        
        # Remove highlight from previous selection
        if 0 <= self.selected_game_index < len(self.game_buttons):
            old_btn, _ = self.game_buttons[self.selected_game_index]
            old_btn.setStyleSheet(old_btn.styleSheet().replace("border: 3px solid #00FF00;", "border: 3px solid transparent;"))
        
        # Add highlight to new selection
        self.selected_game_index = index
        new_btn, _ = self.game_buttons[index]
        current_style = new_btn.styleSheet()
        if "border: 3px solid transparent;" in current_style:
            new_btn.setStyleSheet(current_style.replace("border: 3px solid transparent;", "border: 3px solid #00FF00;"))
        
        # Ensure button is visible
        new_btn.setFocus()
    
    def open_settings(self):
        """Full settings dialog opened from the top-bar HELXAID settings button.
        Includes Display and Library sections only.
        Background & System settings are in Quick Settings (navbar gear).
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)


        # === Display Settings Group ===
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout(display_group)
        
        # Icon Size
        icon_layout = QHBoxLayout()
        icon_label = QLabel("Icon Size (1-10):")
        icon_spin = QSpinBox()
        icon_spin.setRange(1, 10)
        icon_spin.setValue(self.icon_scale)
        icon_layout.addWidget(icon_label)
        icon_layout.addWidget(icon_spin)
        icon_layout.addStretch()
        display_layout.addLayout(icon_layout)
        
        # Show hidden games
        show_hidden_cb = QCheckBox("Show hidden games")
        show_hidden_cb.setChecked(self.settings.get("show_hidden_games", False))
        display_layout.addWidget(show_hidden_cb)
        
        layout.addWidget(display_group)

        # === Library Settings Group ===
        lib_group = QGroupBox("Library")
        lib_layout = QVBoxLayout(lib_group)
        
        # Multi Delete shortcut
        multi_layout = QHBoxLayout()
        multi_label = QLabel("Bulk actions:")
        multi_btn = AnimatedButton("Open Multi Delete")
        multi_btn.clicked.connect(self.multi_delete)
        multi_layout.addWidget(multi_label)
        multi_layout.addWidget(multi_btn)
        lib_layout.addLayout(multi_layout)
        
        # Backup/Restore
        backup_layout = QHBoxLayout()
        backup_btn = AnimatedButton("Backup Library")
        backup_btn.clicked.connect(self.backup_library)
        restore_btn = AnimatedButton("Restore Library")
        restore_btn.clicked.connect(self.restore_library)
        backup_layout.addWidget(backup_btn)
        backup_layout.addWidget(restore_btn)
        lib_layout.addLayout(backup_layout)
        
        layout.addWidget(lib_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        result = dialog.exec()
        if result == QDialog.Accepted:
            # Save Display settings
            self.icon_scale = icon_spin.value()
            
            # Update settings dict
            self.settings["show_hidden_games"] = show_hidden_cb.isChecked()
            self.settings["icon_scale"] = self.icon_scale
            save_settings(self.settings)
            
            self.update_grid_size()
            self.refresh()
    
    def open_quick_settings(self):
        """Compact settings dialog opened from the navbar settings button.
        Only includes Background & Theme and System Settings.
        Display and Library are accessible from the full settings (top-bar gear icon).
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Quick Settings")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # === Background Settings Group ===
        bg_group = QGroupBox("Background & Theme")
        bg_layout = QVBoxLayout(bg_group)
        
        # Background image
        bg_image_layout = QHBoxLayout()
        bg_image_label = QLabel("Background Image:")
        self._qs_bg_path = QLineEdit(self.settings.get("background_image", ""))
        self._qs_bg_path.setReadOnly(True)
        bg_browse_btn = AnimatedButton("Browse...")
        bg_browse_btn.clicked.connect(lambda: self._browse_qs_bg())
        bg_clear_btn = AnimatedButton("Clear")
        bg_clear_btn.clicked.connect(lambda: self._qs_bg_path.setText(""))
        bg_image_layout.addWidget(bg_image_label)
        bg_image_layout.addWidget(self._qs_bg_path)
        bg_image_layout.addWidget(bg_browse_btn)
        bg_image_layout.addWidget(bg_clear_btn)
        bg_layout.addLayout(bg_image_layout)
        
        # Background mode
        bg_mode_layout = QHBoxLayout()
        bg_mode_label = QLabel("Position Mode:")
        self._qs_bg_mode = QComboBox()
        self._qs_bg_mode.addItems(["fill", "fit", "stretch", "tile", "center", "span"])
        current_mode = self.settings.get("background_mode", "fill")
        idx = self._qs_bg_mode.findText(current_mode)
        if idx >= 0:
            self._qs_bg_mode.setCurrentIndex(idx)
        bg_mode_layout.addWidget(bg_mode_label)
        bg_mode_layout.addWidget(self._qs_bg_mode)
        bg_mode_layout.addStretch()
        bg_layout.addLayout(bg_mode_layout)
        
        layout.addWidget(bg_group)

        # === Display Settings Group ===
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout(display_group)
        
        # Resizable window
        resizable_cb = QCheckBox("Allow window resizing")
        resizable_cb.setChecked(self.settings.get("resizable_window", True))
        display_layout.addWidget(resizable_cb)
        
        # Fullscreen mode
        fullscreen_cb = QCheckBox("Fullscreen mode (F11)")
        fullscreen_cb.setChecked(self.isFullScreen())
        display_layout.addWidget(fullscreen_cb)
        
        # Window Opacity
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel("Window Opacity:")
        opacity_slider = QSlider(Qt.Horizontal)
        opacity_slider.setRange(20, 100)  # 20% to 100%
        opacity_slider.setValue(int(self.settings.get("window_opacity", 1.0) * 100))
        opacity_layout.addWidget(opacity_label)
        opacity_layout.addWidget(opacity_slider)
        opacity_layout.addStretch()
        display_layout.addLayout(opacity_layout)
        
        layout.addWidget(display_group)

        # === System Settings ===
        confirm_exit_cb = QCheckBox("Ask for confirmation before exiting")
        confirm_exit_cb.setChecked(self.confirm_on_exit)
        layout.addWidget(confirm_exit_cb)

        startup_cb = QCheckBox("Start on system boot")
        startup_cb.setChecked(is_startup_enabled())
        layout.addWidget(startup_cb)
        
        start_minimised_cb = QCheckBox("Start minimised to tray")
        start_minimised_cb.setChecked(self.settings.get("start_minimised", False))
        layout.addWidget(start_minimised_cb)
        
        minimize_to_tray_cb = QCheckBox("Minimize to tray on minimize")
        minimize_to_tray_cb.setChecked(self.settings.get("minimize_to_tray", True))
        layout.addWidget(minimize_to_tray_cb)

        # Version label and Update button
        version_layout = QHBoxLayout()
        version_label = QLabel("Version - 4.8")
        version_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        check_update_btn = AnimatedButton("Check for Updates")
        check_update_btn.setStyleSheet("""
            QPushButton {
                background: #FF5B06;
                color: white;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FF7B36;
            }
        """)
        check_update_btn.clicked.connect(self.check_for_updates)
        
        version_layout.addWidget(version_label)
        version_layout.addWidget(check_update_btn)
        version_layout.addStretch()
        layout.addLayout(version_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        result = dialog.exec()
        if result == QDialog.Accepted:
            self.confirm_on_exit = confirm_exit_cb.isChecked()
            set_startup_enabled(startup_cb.isChecked())
            
            self.settings["background_image"] = self._qs_bg_path.text()
            self.settings["background_mode"] = self._qs_bg_mode.currentText()
            self.settings["start_minimised"] = start_minimised_cb.isChecked()
            self.settings["minimize_to_tray"] = minimize_to_tray_cb.isChecked()
            self.settings["confirm_on_exit"] = confirm_exit_cb.isChecked()
            self.settings["resizable_window"] = resizable_cb.isChecked()
            self.settings["window_fullscreen"] = fullscreen_cb.isChecked()
            self.settings["window_opacity"] = opacity_slider.value() / 100.0
            save_settings(self.settings)
            
            # Apply display settings immediately
            self.setWindowOpacity(self.settings["window_opacity"])
            
            # Apply fullscreen ONLY if the setting actually changed
            is_currently_fullscreen = bool(self.windowState() & Qt.WindowFullScreen)
            wants_fullscreen = self.settings["window_fullscreen"]
            if wants_fullscreen and not is_currently_fullscreen:
                self.showFullScreen()
            elif not wants_fullscreen and is_currently_fullscreen:
                self.showNormal()
                
            # Apply resizable window setting
            if resizable_cb.isChecked():
                self.setMinimumSize(1380, 790)
                self.setMaximumSize(16777215, 16777215)  # Qt default max
            else:
                self.setFixedSize(self.size())
            
            self.apply_theme()
            self.refresh()
            
        del dialog

    def check_for_updates(self):
        """Check for application updates."""
        try:
            import urllib.request
            import urllib.error
            import json
            import threading
            
            CURRENT_VERSION = "4.8"
            API_URL = "https://api.github.com/repos/TDD131/HELXAID/releases/latest"
            
            def run_check():
                try:
                    req = urllib.request.Request(API_URL, headers={'User-Agent': 'HELXAID-Launcher'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        data = json.loads(response.read().decode())
                        latest_version = data.get("tag_name", "").lower().replace("v", "")
                        release_url = data.get("html_url", "")
                        
                        # Trigger UI update in main thread
                        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                        QMetaObject.invokeMethod(self, "_on_update_result", Qt.QueuedConnection,
                                                 Q_ARG(str, latest_version),
                                                 Q_ARG(str, release_url))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        print("[UpdateCheck] No releases found on GitHub yet.")
                        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                        QMetaObject.invokeMethod(self, "_on_update_result", Qt.QueuedConnection,
                                                 Q_ARG(str, "NO_RELEASES"),
                                                 Q_ARG(str, ""))
                    else:
                        print(f"[UpdateCheck] HTTP Error: {e}")
                        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                        QMetaObject.invokeMethod(self, "_on_update_result", Qt.QueuedConnection,
                                                 Q_ARG(str, "ERROR"),
                                                 Q_ARG(str, str(e)))
                except Exception as e:
                    print(f"[UpdateCheck] Failed: {e}")
                    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "_on_update_result", Qt.QueuedConnection,
                                             Q_ARG(str, "ERROR"),
                                             Q_ARG(str, str(e)))
            
            # Show waiting cursor while checking
            self.setCursor(Qt.WaitCursor)
            
            checking_thread = threading.Thread(target=run_check, daemon=True)
            checking_thread.start()
            
            # Let the thread run; the cursor will be restored in _on_update_result
            
        except Exception as e:
            self.setCursor(Qt.ArrowCursor)
            QMessageBox.warning(self, "Update Error", f"An error occurred: {e}")

    @Slot(str, str)
    def _on_update_result(self, latest_version: str, release_url: str):
        """Callback from background thread update checker."""
        self.setCursor(Qt.ArrowCursor)  # Restore cursor
        
        if latest_version == "ERROR":
            print(f"[UpdateCheck] Could not reach update server: {release_url}")
            QMessageBox.warning(self, "Update Error", f"Failed to check for updates!\n\nPlease ensure your internet connection is stable.\nError: {release_url}")
            return
            
        CURRENT_VERSION = "4.8"
        
        if latest_version == "NO_RELEASES":
            QMessageBox.information(self, "Update", f"No releases have been published on GitHub yet.\n\nYour current version: {CURRENT_VERSION}")
            return
        
        # Simple string comparison
        if latest_version and latest_version != CURRENT_VERSION:
            reply = QMessageBox.question(self, "Update Available!", 
                                         f"A new version ({latest_version}) is available!\n\nYour current version: {CURRENT_VERSION}\n\nWould you like to download it now?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes and release_url:
                QDesktopServices.openUrl(QUrl(release_url))
        else:
            QMessageBox.information(self, "Update", f"You are already using the latest version ({CURRENT_VERSION})!")
    
    
    def _browse_qs_bg(self):
        """Browse background image for quick settings dialog.
        
        Opens the file dialog at the directory of the currently selected
        background image, so the user lands back in the same folder on
        subsequent browses instead of starting from the system default.
        """
        # Priority for starting directory:
        # 1. Dedicated last-browse key (saved per-browse, survives cancel/restart)
        # 2. Folder of the currently selected background image in settings
        # 3. Folder shown in the input field right now
        start_dir = self.settings.get("last_bg_browse_dir", "")
        
        if not start_dir or not os.path.exists(start_dir):
            # Fall back to folder of whatever path is currently displayed or saved
            current_path = self._qs_bg_path.text().strip() or self.settings.get("background_image", "")
            if current_path:
                candidate = os.path.dirname(current_path)
                if os.path.exists(candidate):
                    start_dir = candidate
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            self._qs_bg_path.setText(file_path)
            # Save last browse directory immediately — independent of OK click
            # so the folder is remembered even after cancel or restart
            self.settings["last_bg_browse_dir"] = os.path.dirname(file_path)
            save_settings(self.settings)
    
    def browse_background_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            self.bg_image_path.setText(file_path)
    
    def backup_library(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Backup Library",
            "helxaid_backup.json",
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                import shutil
                shutil.copy(JSON_PATH, file_path)
                QMessageBox.information(self, "Backup", "Library backed up successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to backup: {e}")
    
    def restore_library(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Restore Library",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            reply = QMessageBox.question(
                self,
                "Restore Library",
                "This will replace your current library. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    import shutil
                    shutil.copy(file_path, JSON_PATH)
                    self.data = load_json()
                    self.refresh()
                    QMessageBox.information(self, "Restore", "Library restored successfully!")
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to restore: {e}")
    
    def show_statistics_dashboard(self, parent_dialog=None):
        """Show game statistics dashboard."""
        dialog = QDialog(parent_dialog or self)
        dialog.setWindowTitle("📊 Game Statistics")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Calculate statistics
        total_games = len(self.data)
        total_play_time = sum(g.get("play_time_seconds", 0) for g in self.data)
        total_hours = total_play_time // 3600
        total_minutes = (total_play_time % 3600) // 60
        
        # Get current session info for live updates FIRST (needed for accurate sorting)
        current_game_name = None
        current_session_secs = 0
        if self.current_session:
            current_game_name = self.current_session["game"].get("name")
            current_session_secs = int(time.time() - self.current_session["start_time"])
        
        # Sort games by play time INCLUDING current session time for accurate ranking
        def get_effective_play_time(game):
            play_time = game.get("play_time_seconds", 0)
            # Add current session time if this is the game being played
            if game.get("name") == current_game_name:
                play_time += current_session_secs
            return play_time
        
        games_by_playtime = sorted(self.data, key=get_effective_play_time, reverse=True)
        
        # Header
        header = QLabel("Your Gaming Statistics")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #FF5B06; margin-bottom: 10px;")
        layout.addWidget(header)
        
        # Summary stats (include current session in total)
        total_play_time_with_session = total_play_time + current_session_secs
        total_hours = total_play_time_with_session // 3600
        total_minutes = (total_play_time_with_session % 3600) // 60
        
        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout(summary_group)
        
        stats_text = f"""
        <b>Total Games:</b> {total_games}
        <b>Total Play Time:</b> {total_hours}h {total_minutes}m
        <b>Favorites:</b> {sum(1 for g in self.data if g.get('favorite', False))}
        <b>Hidden:</b> {sum(1 for g in self.data if g.get('hidden', False))}
        """
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("font-size: 14px;")
        stats_label.setTextFormat(Qt.RichText)
        summary_layout.addWidget(stats_label)
        layout.addWidget(summary_group)
        

        most_played_group = QGroupBox("Most Played Games")
        most_played_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #FF5B06;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        most_played_layout = QVBoxLayout(most_played_group)
        
        # Get max play time for scaling bars
        max_play_time = max((g.get("play_time_seconds", 0) for g in games_by_playtime[:10]), default=1)
        if self.current_session and games_by_playtime:
            for g in games_by_playtime[:10]:
                if g.get("name") == current_game_name:
                    max_play_time = max(max_play_time, g.get("play_time_seconds", 0) + current_session_secs)
        max_play_time = max(max_play_time, 1)
        
        # RAGEOUS Bar colors - Fire theme!
        bar_colors = [
            ("#FFD700", "#FF6B00", "#FF0000"),  # Gold with fire
            ("#E8E8E8", "#A0A0A0", "#606060"),  # Silver with steel
            ("#CD7F32", "#8B4513", "#5C3317"),  # Bronze with copper
        ]
        default_colors = ("#FF5B06", "#FF0000", "#AA0000")  # Orange fire
        
        # Top 5 games
        top_games = []
        for game in games_by_playtime[:5]:
            play_secs = game.get("play_time_seconds", 0)
            is_playing = game.get("name") == current_game_name
            if is_playing:
                play_secs += current_session_secs
            if play_secs > 0:
                top_games.append((game, play_secs, is_playing))
        
        if top_games:
            max_bar_height = 150  # TALLER bars!
            
            chart_container = QWidget()
            chart_layout = QHBoxLayout(chart_container)
            chart_layout.setContentsMargins(20, 20, 20, 10)
            chart_layout.setSpacing(25)  # More spacing
            chart_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
            
            for i, (game, play_secs, is_playing) in enumerate(top_games):
                hours = play_secs // 3600
                mins = (play_secs % 3600) // 60
                secs = play_secs % 60  # Also track seconds for tooltip
                percentage = play_secs / max_play_time
                bar_height = int(max_bar_height * percentage)
                bar_height = max(bar_height, 30)  # Minimum height
                
                # Build detailed tooltip
                first_played_str = game.get("first_played", "")
                if first_played_str:
                    try:
                        first_dt = datetime.fromisoformat(first_played_str)
                        first_played_formatted = first_dt.strftime("%B %d, %Y at %I:%M %p")
                    except:
                        first_played_formatted = "Unknown"
                else:
                    first_played_formatted = "Never played"
                
                tooltip_text = f"""
<b>{game.get('name', 'Unknown')}</b>
<hr>
Total Play Time: {hours}h {mins}m {secs}s
First Played: {first_played_formatted}
"""
                
                # Column container with right-click context menu
                col = QWidget()
                col.setToolTip(tooltip_text)
                col.setContextMenuPolicy(Qt.CustomContextMenu)
                
                # Store game reference for context menu
                col.game_data = game
                col.stats_dialog = dialog  # Reference to parent dialog
                col.launcher = self  # Reference to launcher
                
                # Connect right-click handler
                def show_game_context_menu(pos, widget=col):
                    self._show_most_played_context_menu(pos, widget)
                col.customContextMenuRequested.connect(show_game_context_menu)
                
                col_layout = QVBoxLayout(col)
                col_layout.setContentsMargins(0, 0, 0, 0)
                col_layout.setSpacing(8)
                col_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
                
                # Time label with glow effect
                time_label = QLabel(f"{hours}h {mins}m")
                time_label.setAlignment(Qt.AlignCenter)
                time_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFD700;")
                col_layout.addWidget(time_label)
                
                # Get colors for this rank
                colors = bar_colors[i] if i < 3 else default_colors
                
                # The RAGEOUS vertical bar with glow!
                bar = QWidget()
                bar.setFixedHeight(bar_height)
                bar.setFixedWidth(50)  # WIDER bars!
                bar.setStyleSheet(f"""
                    QWidget {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {colors[0]}, 
                            stop:0.3 {colors[1]}, 
                            stop:1 {colors[2]});
                        border-radius: 8px;
                        border: 3px solid {colors[0]};
                    }}
                """)
                col_layout.addWidget(bar, alignment=Qt.AlignHCenter)
                
                # Medal - BIGGER!
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                medal_label = QLabel(medal)
                medal_label.setAlignment(Qt.AlignCenter)
                medal_label.setStyleSheet("font-size: 24px;")  # BIGGER medals!
                col_layout.addWidget(medal_label)
                
                # Game name with style
                name_text = game.get('name', 'Unknown')
                if len(name_text) > 12:
                    name_text = name_text[:10] + ".."
                playing_indicator = "🎮" if is_playing else ""
                name_label = QLabel(f"{playing_indicator}{name_text}")
                name_label.setAlignment(Qt.AlignCenter)
                name_label.setFixedWidth(70)
                name_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #fff;")
                name_label.setWordWrap(True)
                col_layout.addWidget(name_label)
                
                chart_layout.addWidget(col)
            
            most_played_layout.addWidget(chart_container)
        
        if not any(g.get("play_time_seconds", 0) > 0 for g in self.data):
            no_data_label = QLabel("No play time data yet. Play some games!")
            no_data_label.setStyleSheet("font-style: italic; color: #FF5B06; font-size: 14px;")
            no_data_label.setAlignment(Qt.AlignCenter)
            most_played_layout.addWidget(no_data_label)
        
        layout.addWidget(most_played_group)
        
        # Close button
        close_btn = AnimatedButton("Close")
        close_btn.setHoverGradient(['#F443A2', '#FE5500', '#FE0800', '#FFAB00'])  # Game panel gradient
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def _show_most_played_context_menu(self, pos, widget):
        """Show context menu for Most Played Games bar chart."""
        game = widget.game_data
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                border: 1px solid #FF5B06;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background-color: rgba(255, 91, 6, 0.3);
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 5px 10px;
            }
        """)
        

        
        # Open Install Folder action
        folder_action = menu.addAction("Open Install Folder")
        
        menu.addSeparator()
        
        # More Info action
        info_action = menu.addAction("ℹMore Info...")
        
        action = menu.exec(widget.mapToGlobal(pos))
        

        if action == folder_action:
            exe_path = game.get("exe", "")
            if exe_path and os.path.exists(exe_path):
                folder = os.path.dirname(exe_path)
                os.startfile(folder)
        elif action == info_action:
            self._show_game_more_info(game)
    
    def _show_game_more_info(self, game):
        """Show detailed info dialog for a game."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{game.get('name', 'Unknown')}")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0;")
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        
        # Game title header
        header = QLabel(f"{game.get('name', 'Unknown')}")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #FF5B06;")
        layout.addWidget(header)
        
        # === Playtime Stats Section ===
        playtime_group = QGroupBox("Playtime Stats")
        playtime_group.setStyleSheet("QGroupBox { font-weight: bold; color: #FFD700; }")
        playtime_layout = QVBoxLayout(playtime_group)
        
        total_secs = game.get("play_time_seconds", 0)
        hours = total_secs // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        
        # Session history calculations
        session_history = game.get("session_history", [])
        if session_history:
            durations = [s.get("duration", 0) for s in session_history]
            avg_session = sum(durations) // len(durations) if durations else 0
            longest_session = max(durations) if durations else 0
            session_count = len(durations)
        else:
            avg_session = 0
            longest_session = 0
            session_count = 0
        
        # Format times
        def format_time(secs):
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            return f"{h}h {m}m {s}s"
        
        # First/last played
        first_played = game.get("first_played", "")
        last_played = game.get("last_played", "")
        
        def format_date(iso_str):
            if not iso_str:
                return "Never"
            try:
                dt = datetime.fromisoformat(iso_str)
                return dt.strftime("%B %d, %Y at %I:%M %p")
            except:
                return "Unknown"
        
        stats_html = f"""
        <table style='color: #e0e0e0; font-size: 12px;'>
            <tr><td><b>Total Time:</b></td><td>{hours}h {mins}m {secs}s</td></tr>
            <tr><td><b>Sessions:</b></td><td>{session_count}</td></tr>
            <tr><td><b>Average Session:</b></td><td>{format_time(avg_session)}</td></tr>
            <tr><td><b>Longest Session:</b></td><td>{format_time(longest_session)}</td></tr>
            <tr><td><b>First Played:</b></td><td>{format_date(first_played)}</td></tr>
            <tr><td><b>Last Played:</b></td><td>{format_date(last_played)}</td></tr>
        </table>
        """
        stats_label = QLabel(stats_html)
        stats_label.setTextFormat(Qt.RichText)
        playtime_layout.addWidget(stats_label)
        layout.addWidget(playtime_group)
        
        # === Metadata Section ===
        metadata_group = QGroupBox("Metadata")
        metadata_group.setStyleSheet("QGroupBox { font-weight: bold; color: #7289DA; }")
        metadata_layout = QGridLayout(metadata_group)
        
        exe_path = game.get("exe", "")
        
        # Try to get Steam App ID and fetch metadata
        steam_app_id = self._get_steam_app_id(exe_path)
        steam_metadata = {}
        if steam_app_id and not game.get("genre") and not game.get("developer"):
            # Fetch from Steam API if not already set
            steam_metadata = self._fetch_steam_metadata(steam_app_id)
            if steam_metadata:
                # Auto-populate if empty
                if not game.get("genre") and steam_metadata.get("genre"):
                    game["genre"] = steam_metadata["genre"]
                if not game.get("developer") and steam_metadata.get("developer"):
                    game["developer"] = steam_metadata["developer"]
                save_json(self.data)
        
        # Genre field (editable)
        genre_label = QLabel("Genre:")
        genre_edit = QLineEdit(game.get("genre", ""))
        genre_edit.setPlaceholderText("Enter genre...")
        genre_edit.setStyleSheet("background: #333; border: 1px solid #555; padding: 5px;")
        metadata_layout.addWidget(genre_label, 0, 0)
        metadata_layout.addWidget(genre_edit, 0, 1)
        
        # Developer field (editable)
        dev_label = QLabel("Developer:")
        dev_edit = QLineEdit(game.get("developer", ""))
        dev_edit.setPlaceholderText("Enter developer...")
        dev_edit.setStyleSheet("background: #333; border: 1px solid #555; padding: 5px;")
        metadata_layout.addWidget(dev_label, 1, 0)
        metadata_layout.addWidget(dev_edit, 1, 1)
        
        # Steam App ID (if found)
        if steam_app_id:
            appid_label = QLabel("Steam App ID:")
            appid_value = QLabel(str(steam_app_id))
            appid_value.setStyleSheet("color: #7289DA;")
            metadata_layout.addWidget(appid_label, 2, 0)
            metadata_layout.addWidget(appid_value, 2, 1)
        
        # Install size (calculated)
        install_size = "Unknown"
        if exe_path and os.path.exists(exe_path):
            folder = os.path.dirname(exe_path)
            try:
                total_size = sum(
                    os.path.getsize(os.path.join(dirpath, f))
                    for dirpath, _, filenames in os.walk(folder)
                    for f in filenames
                )
                if total_size >= 1024**3:
                    install_size = f"{total_size / (1024**3):.2f} GB"
                else:
                    install_size = f"{total_size / (1024**2):.2f} MB"
            except:
                install_size = "Unable to calculate"
        
        size_label_title = QLabel("Install Size:")
        size_label = QLabel(install_size)
        size_label.setStyleSheet("color: #aaa;")
        metadata_layout.addWidget(size_label_title, 3, 0)
        metadata_layout.addWidget(size_label, 3, 1)
        
        layout.addWidget(metadata_group)
        
        # === Extra Section ===
        extra_group = QGroupBox("Extra")
        extra_group.setStyleSheet("QGroupBox { font-weight: bold; color: #43B581; }")
        extra_layout = QHBoxLayout(extra_group)
        
        # Open folder button
        open_folder_btn = AnimatedButton("Open Folder")
        open_folder_btn.setStyleSheet("background: #333; padding: 8px; border-radius: 5px;")
        open_folder_btn.clicked.connect(lambda: os.startfile(os.path.dirname(exe_path)) if exe_path else None)
        extra_layout.addWidget(open_folder_btn)
        
        # Open Steam page (if Steam game)
        if "steamapps" in exe_path.lower():
            steam_btn = AnimatedButton("Steam Page")
            steam_btn.setStyleSheet("background: #333; padding: 8px; border-radius: 5px;")
            steam_btn.setToolTip("Opens this game's Steam page")
            steam_btn.clicked.connect(lambda: os.startfile(f"steam://nav/games/details"))
            extra_layout.addWidget(steam_btn)
        
        layout.addWidget(extra_group)
        
        # === User Notes Section ===
        notes_group = QGroupBox("Notes")
        notes_group.setStyleSheet("QGroupBox { font-weight: bold; color: #FAA61A; }")
        notes_layout = QVBoxLayout(notes_group)
        
        notes_edit = QTextEdit()
        notes_edit.setPlaceholderText("Add your notes about this game...")
        notes_edit.setText(game.get("notes", ""))
        notes_edit.setStyleSheet("background: #333; border: 1px solid #555; padding: 5px; min-height: 60px;")
        notes_layout.addWidget(notes_edit)
        layout.addWidget(notes_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_btn = AnimatedButton("Save Changes")
        save_btn.setStyleSheet("background: #FF5B06; padding: 10px; border-radius: 5px; font-weight: bold;")
        
        close_btn = AnimatedButton("Close")
        close_btn.setStyleSheet("background: #444; padding: 10px; border-radius: 5px;")
        
        def save_changes():
            game["genre"] = genre_edit.text()
            game["developer"] = dev_edit.text()
            game["notes"] = notes_edit.toPlainText()
            save_json(self.data)
            dialog.accept()
        
        save_btn.clicked.connect(save_changes)
        close_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.exec()
    
    def _get_steam_app_id(self, exe_path):
        """Extract Steam App ID from game path by reading appmanifest files."""
        if not exe_path or "steamapps" not in exe_path.lower():
            return None
        
        try:
            # Find the steamapps/common folder and go up to steamapps
            path_lower = exe_path.lower()
            common_idx = path_lower.find("steamapps\\common")
            if common_idx == -1:
                common_idx = path_lower.find("steamapps/common")
            if common_idx == -1:
                return None
            
            steamapps_dir = exe_path[:common_idx + len("steamapps")]
            
            # Get the game folder name
            common_path = exe_path[common_idx + len("steamapps\\common") + 1:]
            if "\\" in common_path:
                game_folder = common_path.split("\\")[0]
            elif "/" in common_path:
                game_folder = common_path.split("/")[0]
            else:
                game_folder = common_path
            
            # Search appmanifest files for this game folder
            for file in os.listdir(steamapps_dir):
                if file.startswith("appmanifest_") and file.endswith(".acf"):
                    manifest_path = os.path.join(steamapps_dir, file)
                    with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if game_folder.lower() in content.lower():
                            # Extract appid from filename
                            app_id = file.replace("appmanifest_", "").replace(".acf", "")
                            return app_id
        except Exception as e:
            print(f"Error getting Steam App ID: {e}")
        
        return None
    
    def _fetch_steam_metadata(self, app_id):
        """Fetch game metadata from Steam Store API."""
        try:
            import urllib.request
            import json as json_module
            
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json_module.loads(response.read().decode())
            
            if str(app_id) in data and data[str(app_id)].get("success"):
                game_data = data[str(app_id)]["data"]
                
                # Extract genres
                genres = game_data.get("genres", [])
                genre_str = ", ".join([g.get("description", "") for g in genres[:3]])
                
                # Extract developers
                developers = game_data.get("developers", [])
                dev_str = ", ".join(developers[:2]) if developers else ""
                
                return {
                    "genre": genre_str,
                    "developer": dev_str,
                    "publisher": ", ".join(game_data.get("publishers", [])[:2]),
                    "short_description": game_data.get("short_description", "")
                }
        except Exception as e:
            print(f"Error fetching Steam metadata: {e}")
        
        return {}
    
    def _search_and_download_icon(self, game_name, exe_path):
        """Search for game icon from the internet with interactive preview."""
        import urllib.request
        import urllib.parse
        
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        os.makedirs(icons_dir, exist_ok=True)
        
        # Clean game name for filename
        safe_name = "".join(c for c in game_name if c.isalnum() or c in " -_").strip()
        icon_path = os.path.join(icons_dir, f"{safe_name}_web.png")
        
        # Collect all possible image URLs
        image_candidates = []
        
        # Method 1: Google Images Scraping (no API key needed)
        try:
            search_query = urllib.parse.quote(f"{game_name} game icon logo png")
            google_url = f"https://www.google.com/search?q={search_query}&tbm=isch&tbs=isz:m"
            
            req = urllib.request.Request(google_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                # Extract image URLs using regex
                import re
                # Pattern for Google Images data
                patterns = [
                    r'\["(https?://[^"]+\.(?:jpg|jpeg|png|webp))",[0-9]+,[0-9]+\]',
                    r'"ou":"(https?://[^"]+)"',
                    r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"',
                ]
                
                found_urls = set()
                for pattern in patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for url in matches:
                        if url and 'gstatic' not in url and 'google' not in url and len(url) < 500:
                            found_urls.add(url)
                
                for i, url in enumerate(list(found_urls)[:15]):
                    image_candidates.append({
                        "url": url,
                        "name": f"{game_name} - Image {i+1}",
                        "source": "Google Images"
                    })
                    
                print(f"[IconSearch] Found {len(found_urls)} images from Google")
        except Exception as e:
            print(f"Google Images scraping failed: {e}")
        
        # Method 1b: DuckDuckGo Image Search (free, no API key needed)
        try:
            search_query = urllib.parse.quote(f"{game_name} game icon logo")
            # DuckDuckGo instant answer API
            ddg_url = f"https://duckduckgo.com/?q={search_query}&iax=images&ia=images&format=json"
            req = urllib.request.Request(ddg_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode()
                # Extract image URLs from response using regex
                import re
                # Find vqd token for image search
                vqd_match = re.search(r'vqd=([^&"\']+)', html)
                if vqd_match:
                    vqd = vqd_match.group(1)
                    # Now get actual images
                    img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={search_query}&vqd={vqd}&p=1"
                    img_req = urllib.request.Request(img_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Referer': 'https://duckduckgo.com/'
                    })
                    with urllib.request.urlopen(img_req, timeout=10) as img_response:
                        import json as json_module
                        img_data = json_module.loads(img_response.read().decode())
                        for result in img_data.get("results", [])[:10]:
                            image_url = result.get("image")
                            title = result.get("title", game_name)
                            if image_url:
                                image_candidates.append({
                                    "url": image_url,
                                    "name": title[:50] if len(title) > 50 else title,
                                    "source": "DuckDuckGo"
                                })
        except Exception as e:
            print(f"DuckDuckGo search failed: {e}")
        
        # Method 2: Try Steam Store images if it's a Steam game
        steam_app_id = self._get_steam_app_id(exe_path)
        if steam_app_id:
            # Add multiple Steam image types
            image_candidates.insert(0, {
                "url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{steam_app_id}/library_600x900.jpg",
                "name": game_name,
                "source": "Steam Library"
            })
            image_candidates.insert(1, {
                "url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{steam_app_id}/header.jpg",
                "name": game_name,
                "source": "Steam Header"
            })
        
        if not image_candidates:
            return None
        
        # Show interactive preview dialog
        return self._show_icon_preview_dialog(image_candidates, icon_path, game_name)
    
    def _show_icon_preview_dialog(self, image_candidates, icon_path, game_name):
        """Show interactive dialog for selecting an icon from candidates."""
        import urllib.request
        from io import BytesIO
        
        current_index = [0]  # Use list to allow modification in nested function
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle(f"Select Icon for {game_name}")
        preview_dialog.setMinimumWidth(400)
        preview_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0a00, stop:0.5 #0a0a0a, stop:1 #1a0a00);
                color: #e0e0e0;
                border: 2px solid #FF5B06;
                border-radius: 15px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                transform: scale(1.05);
            }
        """)
        
        layout = QVBoxLayout(preview_dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("ICON SEARCH")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: #FF5B06;
        """)
        layout.addWidget(title_label)
        
        # Status label
        status_label = QLabel(f"Found {len(image_candidates)} result(s)")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("font-size: 12px; color: #FDA903;")
        layout.addWidget(status_label)
        
        # Source label with glow
        source_label = QLabel("")
        source_label.setAlignment(Qt.AlignCenter)
        source_label.setStyleSheet("""
            font-size: 12px; 
            color: #FF5B06; 
            font-weight: bold;
            padding: 5px;
            background: rgba(255, 91, 6, 0.1);
            border-radius: 5px;
        """)
        layout.addWidget(source_label)
        
        # Image preview with glowing border
        preview_label = QLabel()
        preview_label.setFixedSize(220, 220)
        preview_label.setAlignment(Qt.AlignCenter)
        preview_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #1a1a1a, stop:1 #2a2a2a);
            border: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
            border-radius: 15px;
        """)
        layout.addWidget(preview_label, alignment=Qt.AlignCenter)
        
        # Name label with style
        name_label = QLabel("")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: white;
            padding: 8px;
        """)
        name_label.setWordWrap(True)
        layout.addWidget(name_label)
        
        # Counter label with fire styling
        counter_label = QLabel("")
        counter_label.setAlignment(Qt.AlignCenter)
        counter_label.setStyleSheet("""
            font-size: 13px; 
            color: #FDA903;
            font-weight: bold;
        """)
        layout.addWidget(counter_label)
        
        # Store the current image data
        current_img_data = [None]
        
        def load_preview(index):
            if index >= len(image_candidates):
                preview_label.setText("No more\nresults")
                name_label.setText("")
                source_label.setText("")
                counter_label.setText("")
                return False
            
            candidate = image_candidates[index]
            counter_label.setText(f"Result {index + 1} of {len(image_candidates)}")
            source_label.setText(f"Source: {candidate['source']}")
            name_label.setText(candidate["name"])
            
            preview_label.setText("Loading...")
            QApplication.processEvents()
            
            try:
                req = urllib.request.Request(candidate["url"], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    img_data = response.read()
                    current_img_data[0] = img_data
                    
                    # Create preview pixmap
                    pixmap = QPixmap()
                    pixmap.loadFromData(img_data)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        preview_label.setPixmap(scaled)
                        return True
                    else:
                        preview_label.setText("Failed to\nload image")
                        return False
            except Exception as e:
                print(f"Failed to load preview: {e}")
                preview_label.setText("Failed to\nload image")
                return False
        
        # Buttons with RAGEOUS styling
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        accept_btn = AnimatedButton("ACCEPT")
        accept_btn.setIcon(QIcon())  # Clear any icon
        accept_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5dff5d, stop:0.5 #43B581, stop:1 #2d8d5d);
                padding: 12px 25px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                color: white;
                border: 2px solid #43B581;
                text-align: center;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7fff7f, stop:0.5 #5dff5d, stop:1 #43B581);
                border: 2px solid #5dff5d;
            }
        """)
        
        next_btn = AnimatedButton("NEXT")
        next_btn.setIcon(QIcon())  # Clear any icon
        next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FDA903, stop:0.5 #FF5B06, stop:1 #cc4800);
                padding: 12px 25px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                color: white;
                border: 2px solid #FF5B06;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffcc00, stop:0.5 #FDA903, stop:1 #FF5B06);
                border: 2px solid #FDA903;
            }
        """)
        
        skip_btn = AnimatedButton("SKIP")
        skip_btn.setIcon(QIcon())  # Clear any icon
        skip_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #666, stop:0.5 #444, stop:1 #333);
                padding: 12px 25px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                color: #ccc;
                border: 2px solid #555;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff4444, stop:0.5 #cc3333, stop:1 #aa2222);
                border: 2px solid #ff4444;
                color: white;
            }
        """)
        
        selected_path = [None]
        
        def accept_icon():
            if current_img_data[0]:
                try:
                    from PIL import Image
                    img = Image.open(BytesIO(current_img_data[0]))
                    # Crop to square
                    min_dim = min(img.width, img.height)
                    left = (img.width - min_dim) // 2
                    top = (img.height - min_dim) // 2
                    img = img.crop((left, top, left + min_dim, top + min_dim))
                    img = img.resize((256, 256), Image.LANCZOS)
                    img = img.convert('RGBA')
                    img.save(icon_path, 'PNG')
                    selected_path[0] = icon_path
                    preview_dialog.accept()
                except Exception as e:
                    print(f"Failed to save icon: {e}")
                    # Fallback: save raw
                    with open(icon_path, 'wb') as f:
                        f.write(current_img_data[0])
                    selected_path[0] = icon_path
                    preview_dialog.accept()
        
        def next_icon():
            current_index[0] += 1
            if current_index[0] >= len(image_candidates):
                QMessageBox.information(preview_dialog, "No More Results", 
                    "No more icons found. Try 'Change icon from local...' to select manually.")
                preview_dialog.reject()
            else:
                if not load_preview(current_index[0]):
                    next_icon()  # Skip failed ones
        
        def prev_icon():
            if current_index[0] > 0:
                current_index[0] -= 1
                if not load_preview(current_index[0]):
                    prev_icon()  # Skip failed ones
        
        # Previous button
        prev_btn = AnimatedButton("PREV")
        prev_btn.setIcon(QIcon())  # Clear any icon
        prev_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7289DA, stop:0.5 #5865F2, stop:1 #4752C4);
                padding: 12px 20px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                color: white;
                border: 2px solid #5865F2;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #99AAF2, stop:0.5 #7289DA, stop:1 #5865F2);
                border: 2px solid #7289DA;
            }
        """)
        prev_btn.clicked.connect(prev_icon)
        
        accept_btn.clicked.connect(accept_icon)
        next_btn.clicked.connect(next_icon)
        skip_btn.clicked.connect(preview_dialog.reject)
        
        btn_layout.addWidget(accept_btn)
        btn_layout.addWidget(prev_btn)
        btn_layout.addWidget(next_btn)
        btn_layout.addWidget(skip_btn)
        layout.addLayout(btn_layout)
        
        # Load first preview
        load_preview(0)
        
        preview_dialog.exec()
        return selected_path[0]

    def resizeEvent(self, event):
        # Clear cached background on resize (for proper background scaling)
        self._cached_bg_pixmap = None
        super().resizeEvent(event)
        
        # Debounce the grid reflow so it doesn't stutter during window dragging
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.reflow_grid)
        self._resize_timer.start(100)  # 100ms debounce
        
        # Re-scale background image to new container size (debounced separately)
        # Without this, the background stays at the initial startup size after resize
        if self.settings.get("background_image"):
            if not hasattr(self, '_bg_resize_timer'):
                self._bg_resize_timer = QTimer(self)
                self._bg_resize_timer.setSingleShot(True)
                self._bg_resize_timer.timeout.connect(self.apply_theme)
            self._bg_resize_timer.start(200)  # 200ms debounce to avoid stutter

    def closeEvent(self, event):
        if self.confirm_on_exit:
            reply = QMessageBox.question(
                self,
                "Exit",
                "Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        
        # Save audio player state
        if hasattr(self, 'audio_player') and self.audio_player:
            self.audio_player._save_last_track()
        
        # Save music panel state (position, folder, etc.)
        if hasattr(self, 'music_panel') and self.music_panel:
            self.music_panel._save_state()
            
        # Shutdown macro system bridge to release input hooks and stop threads
        if hasattr(self, '_macro_bridge') and self._macro_bridge:
            try:
                print("[HELXAID] Shutting down macro system bridge...")
                self._macro_bridge.shutdown()
            except Exception as e:
                print(f"Error shutting down macro bridge: {e}")
            
        # Save window geometry before closing
        if not self.isFullScreen():
            self.settings["window_geometry"] = [self.x(), self.y(), self.width(), self.height()]
        save_settings(self.settings)
        
        event.accept()
    
    def showEvent(self, event):
        """Initialize taskbar thumbnail toolbar when window is shown."""
        super().showEvent(event)
        
        # Setup taskbar toolbar after window is visible (needs valid HWND)
        if TASKBAR_TOOLBAR_AVAILABLE and TaskbarThumbnailToolbar and not getattr(self, 'taskbar_toolbar', None):
            try:
                hwnd = int(self.winId())
                self.taskbar_toolbar = TaskbarThumbnailToolbar(
                    hwnd,
                    on_prev=self._taskbar_prev,
                    on_playpause=self._taskbar_playpause,
                    on_next=self._taskbar_next
                )
                # Delay button addition to ensure window is fully initialized
                # Use longer delay and retry mechanism for reliability
                self._taskbar_retry_count = 0
                QTimer.singleShot(1000, self._init_taskbar_buttons)
            except Exception as e:
                print(f"Could not setup taskbar toolbar: {e}")
    
    def _init_taskbar_buttons(self):
        """Initialize taskbar thumbnail buttons with retry mechanism."""
        if self.taskbar_toolbar:
            success = self.taskbar_toolbar.add_buttons()
            
            # Retry up to 3 times if failed
            if not success and hasattr(self, '_taskbar_retry_count'):
                self._taskbar_retry_count += 1
                if self._taskbar_retry_count < 3:
                    delay = 1000 * self._taskbar_retry_count  # 1s, 2s delays
                    print(f"Taskbar buttons failed, retry {self._taskbar_retry_count}/3 in {delay}ms")
                    QTimer.singleShot(delay, self._init_taskbar_buttons)
                else:
                    print("Taskbar buttons failed after 3 retries")
    
    def nativeEvent(self, eventType, message):
        """Handle Windows native events for taskbar button clicks."""
        try:
            if eventType == b"windows_generic_MSG" and self.taskbar_toolbar:
                # Parse MSG structure - handle PySide6's shiboken.VoidPtr
                import ctypes
                from ctypes.wintypes import MSG
                
                # Convert shiboken.VoidPtr to int then to ctypes pointer
                msg_ptr = int(message)
                msg = ctypes.cast(msg_ptr, ctypes.POINTER(MSG)).contents
                
                WM_COMMAND = 0x0111
                if msg.message == WM_COMMAND:
                    # LOWORD of wParam is the button ID
                    button_id = msg.wParam & 0xFFFF
                    if button_id in (BUTTON_PREV, BUTTON_PLAYPAUSE, BUTTON_NEXT):
                        self.taskbar_toolbar.handle_button_click(button_id)
                        return True, 0
        except Exception as e:
            # Silently ignore errors to not spam console
            pass
        
        return super().nativeEvent(eventType, message)
    
    def _taskbar_prev(self):
        """Handle taskbar Previous button."""
        if hasattr(self, 'audio_player') and self.audio_player:
            self.audio_player.prev_track()
    
    def _taskbar_playpause(self):
        """Handle taskbar Play/Pause toggle button."""
        if hasattr(self, 'music_panel'):
            self.music_panel._toggle_play()
        elif hasattr(self, 'audio_player') and self.audio_player:
            self.audio_player.toggle_play()
    
    def _taskbar_next(self):
        """Handle taskbar Next button."""
        if hasattr(self, 'music_panel'):
            self.music_panel._next_track()
        elif hasattr(self, 'audio_player') and self.audio_player:
            self.audio_player.next_track()
    
    def _update_taskbar_play_state(self, state):
        """Update taskbar button based on playback state."""
        if self.taskbar_toolbar:
            from PySide6.QtMultimedia import QMediaPlayer
            is_playing = (state == QMediaPlayer.PlayingState)
            self.taskbar_toolbar.update_play_state(is_playing)
    
    def _setup_single_instance_server(self):
        """Setup local server to listen for restore signals from second instance."""
        from PySide6.QtNetwork import QLocalServer
        
        is_frozen = getattr(sys, 'frozen', False)
        server_name = "HELXAIDLocalServer_EXE" if is_frozen else "HELXAIDLocalServer_DEBUG"
        
        self._local_server = QLocalServer(self)
        
        # Remove existing server if crashed previously
        QLocalServer.removeServer(server_name)
        
        if self._local_server.listen(server_name):
            self._local_server.newConnection.connect(self._on_new_instance_connection)
            print(f"[SingleInstance] Server listening on: {server_name}")
        else:
            print(f"[SingleInstance] Failed to start server: {self._local_server.errorString()}")
    
    def _on_new_instance_connection(self):
        """Handle connection from second instance trying to launch."""
        socket = self._local_server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(1000)
            data = socket.readAll().data()
            if data == b"RESTORE":
                print("[SingleInstance] Received RESTORE signal, showing window")
                self.show_from_tray()
            socket.disconnectFromServer()
    
    def _enable_drag_drop_for_elevated(self):
        """Enable drag-drop from non-elevated Explorer to elevated app (UAC bypass for drag-drop)."""
        if os.name != 'nt':
            return
        
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows message filter constants
            WM_DROPFILES = 0x0233
            WM_COPYDATA = 0x004A
            WM_COPYGLOBALDATA = 0x0049
            MSGFLT_ALLOW = 1
            
            # Get ChangeWindowMessageFilterEx function
            user32 = ctypes.windll.user32
            ChangeWindowMessageFilterEx = user32.ChangeWindowMessageFilterEx
            ChangeWindowMessageFilterEx.argtypes = [
                wintypes.HWND,  # hwnd
                wintypes.UINT,  # message
                wintypes.DWORD, # action
                ctypes.c_void_p # pChangeFilterStruct (can be NULL)
            ]
            ChangeWindowMessageFilterEx.restype = wintypes.BOOL
            
            # Get window handle
            hwnd = int(self.winId())
            
            # Allow drag-drop messages
            ChangeWindowMessageFilterEx(hwnd, WM_DROPFILES, MSGFLT_ALLOW, None)
            ChangeWindowMessageFilterEx(hwnd, WM_COPYDATA, MSGFLT_ALLOW, None)
            ChangeWindowMessageFilterEx(hwnd, WM_COPYGLOBALDATA, MSGFLT_ALLOW, None)
            
            print("[DragDrop] Enabled drag-drop for elevated process (main window)")
        except Exception as e:
            print(f"[DragDrop] Failed to enable drag-drop for elevated: {e}")
    
    def _enable_drag_drop_for_widget(self, widget):
        """Enable drag-drop for a specific widget in elevated app."""
        if os.name != 'nt':
            return
        
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows message filter constants
            WM_DROPFILES = 0x0233
            WM_COPYDATA = 0x004A
            WM_COPYGLOBALDATA = 0x0049
            MSGFLT_ALLOW = 1
            
            user32 = ctypes.windll.user32
            
            # Method 1: ChangeWindowMessageFilter (process-wide, simpler)
            ChangeWindowMessageFilter = user32.ChangeWindowMessageFilter
            ChangeWindowMessageFilter.argtypes = [wintypes.UINT, wintypes.DWORD]
            ChangeWindowMessageFilter.restype = wintypes.BOOL
            
            ChangeWindowMessageFilter(WM_DROPFILES, MSGFLT_ALLOW)
            ChangeWindowMessageFilter(WM_COPYDATA, MSGFLT_ALLOW)
            ChangeWindowMessageFilter(WM_COPYGLOBALDATA, MSGFLT_ALLOW)
            
            # Method 2: ChangeWindowMessageFilterEx (per-window)
            ChangeWindowMessageFilterEx = user32.ChangeWindowMessageFilterEx
            ChangeWindowMessageFilterEx.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p
            ]
            ChangeWindowMessageFilterEx.restype = wintypes.BOOL
            
            hwnd = int(widget.winId())
            ChangeWindowMessageFilterEx(hwnd, WM_DROPFILES, MSGFLT_ALLOW, None)
            ChangeWindowMessageFilterEx(hwnd, WM_COPYDATA, MSGFLT_ALLOW, None)
            ChangeWindowMessageFilterEx(hwnd, WM_COPYGLOBALDATA, MSGFLT_ALLOW, None)
            
            print(f"[DragDrop] Enabled drag-drop for widget: {widget.objectName()}")
        except Exception as e:
            print(f"[DragDrop] Failed to enable drag-drop for widget: {e}")
    
    def setup_system_tray(self):
        """Setup system tray icon with menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set the icon
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "UI Icons", "launcher-icon.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.windowIcon())
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = tray_menu.addAction("Show Launcher")
        show_action.triggered.connect(self.show_from_tray)
        
        tray_menu.addSeparator()
        
        # Crosshair toggle
        crosshair_action = tray_menu.addAction("Toggle Crosshair (Ctrl+Shift+C)")
        crosshair_action.triggered.connect(self._toggle_crosshair_from_tray)
        
        tray_menu.addSeparator()
        
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.setToolTip("HELXAID")
        self.tray_icon.show()
    
    def show_from_tray(self):
        """Show the window from system tray."""
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def on_tray_activated(self, reason):
        """Handle tray icon click."""
        if reason == QSystemTrayIcon.Trigger:  # Left click
            if self.isVisible():
                self.hide()
            else:
                self.show_from_tray()
    
    def _toggle_crosshair_from_tray(self):
        """Toggle crosshair overlay from tray menu."""
        if hasattr(self, 'crosshair_panel') and self.crosshair_panel:
            self.crosshair_panel._on_toggle()
    
    def quit_app(self):
        """Actually quit the application."""
        self.confirm_on_exit = False
        
        # Save music panel state before quitting
        if hasattr(self, 'music_panel') and self.music_panel:
            self.music_panel._save_state()
        
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        QApplication.quit()
    
    def changeEvent(self, event):
        """Minimize to tray when window minimized (if enabled) - but not for Show Desktop."""
        from PySide6.QtCore import QEvent, QTimer
        if event.type() == QEvent.WindowStateChange:
            # Intercept maximize event to act like F11 (fullscreen)
            if self.windowState() & Qt.WindowMaximized:
                QTimer.singleShot(0, self.toggle_fullscreen)
                
            if self.windowState() & Qt.WindowMinimized:
                # Check if minimize to tray is enabled (default True)
                if self.settings.get("minimize_to_tray", True):
                    # Only minimize to tray if window was active before (user clicked minimize)
                    # Win+D (Show Desktop) doesn't set focus before minimizing
                    if getattr(self, '_was_active_before_minimize', False):
                        event.ignore()
                        self.hide()
                        if hasattr(self, 'tray_icon'):
                            self.tray_icon.showMessage(
                                "HELXAID",
                                "Minimized to system tray",
                                self.tray_icon.icon(),
                                1500
                            )
                        self._was_active_before_minimize = False
                        return
                # If disabled, just minimize normally (don't hide to tray)
            else:
                # Window being shown/restored - track active state
                self._was_active_before_minimize = True
        super().changeEvent(event)
    
    def update_discord_button_text(self):
        """Update Discord button text based on state."""
        if self.discord_enabled:
            self.discord_btn.setText("Discord: ON")
            self.discord_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5865F2, stop:1 #7289DA);
                    border: 2px solid #5865F2;
                    border-radius: 6px;
                    padding: 3px 12px 2px 12px;
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7289DA, stop:1 #99AAF2);
                    border: 2px solid #7289DA;
                }
                QPushButton:pressed {
                    background: #4752C4;
                }
            """)
        else:
            self.discord_btn.setText("Discord: OFF")
            self.discord_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 30, 30, 0.9);
                    border: 2px solid #5865F2;
                    border-radius: 6px;
                    padding: 3px 12px 1px 12px;
                    color: #888888;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(88, 101, 242, 0.3);
                    color: #e0e0e0;
                }
            """)
    
    def toggle_discord_rpc(self):
        """Toggle Discord Rich Presence on/off with debounce protection."""
        # Prevent rapid clicking - add cooldown
        if hasattr(self, '_discord_cooldown') and self._discord_cooldown:
            return  # Ignore clicks during cooldown
        
        # Set cooldown flag
        self._discord_cooldown = True
        self.discord_btn.setEnabled(False)  # Disable clicking
        
        # Start loading animation
        self._discord_loading_progress = 0
        self._discord_loading_timer = QTimer()
        self._discord_loading_timer.timeout.connect(self._update_discord_loading_animation)
        self._discord_loading_timer.start(30)  # Update every 30ms for smooth animation
        
        # Reset cooldown after 3 seconds
        QTimer.singleShot(3000, self._reset_discord_cooldown)
        
        self.discord_enabled = not self.discord_enabled
        self.settings["discord_rpc"] = self.discord_enabled
        save_settings(self.settings)
        
        # Run Discord connection in background thread to prevent UI freeze
        if self.discord_enabled:
            # Check if Discord is running first
            if not self._is_discord_running():
                # Discord not running - show notification
                self._discord_cooldown = False
                self.discord_btn.setEnabled(True)
                if hasattr(self, '_discord_loading_timer') and self._discord_loading_timer:
                    self._discord_loading_timer.stop()
                self.discord_enabled = False
                self.settings["discord_rpc"] = False
                save_settings(self.settings)
                self.update_discord_button_text()
                QMessageBox.information(self, "Discord Not Running", 
                    "Discord is not running!\n\n"
                    "Please start Discord first, then try again.\n\n"
                    "💡 Tip: Make sure Discord is fully loaded before connecting.")
                return
            threading.Thread(target=self._connect_discord_threaded, daemon=True).start()
        else:
            threading.Thread(target=self._disconnect_discord_threaded, daemon=True).start()
    
    def _is_discord_running(self):
        """Check if Discord process is running."""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'discord' in proc.info['name'].lower():
                    return True
        except:
            pass
        
        # Fallback: check with tasklist on Windows
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq Discord.exe'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            return 'Discord.exe' in result.stdout
        except:
            pass
        
        return False  # Assume not running if can't check
    
    def _check_discord_installed(self):
        """Check if Discord is installed on the system."""
        # Check common Discord installation paths on Windows
        discord_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Discord"),
            os.path.expandvars(r"%APPDATA%\Discord"),
            os.path.expandvars(r"%LOCALAPPDATA%\DiscordPTB"),
            os.path.expandvars(r"%LOCALAPPDATA%\DiscordCanary"),
        ]
        
        for path in discord_paths:
            if os.path.exists(path):
                return True
        
        return False
    
    def _update_discord_loading_animation(self):
        """Update the sliding loading bar animation on Discord button."""
        self._discord_loading_progress += 1  # Slower increment for 3-second animation
        if self._discord_loading_progress > 100:
            self._discord_loading_progress = 100  # Stop at end, don't loop
        
        # Calculate gradient positions for sliding effect
        pos1 = max(0, self._discord_loading_progress - 30) / 100
        pos2 = self._discord_loading_progress / 100
        pos3 = min(100, self._discord_loading_progress + 30) / 100
        
        # Create a sliding highlight effect
        self.discord_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3d4270,
                    stop:{pos1:.2f} #3d4270,
                    stop:{pos2:.2f} #7289DA,
                    stop:{pos3:.2f} #3d4270,
                    stop:1 #3d4270);
                border: 2px solid #5865F2;
                border-radius: 6px;
                padding: 5px 12px;
                color: white;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        
        # Update button text to show loading
        if self.discord_enabled:
            self.discord_btn.setText("🔄 Connecting...")
        else:
            self.discord_btn.setText("🔄 Disconnecting...")
    
    def _reset_discord_cooldown(self):
        """Reset the Discord toggle cooldown and stop animation."""
        self._discord_cooldown = False
        self.discord_btn.setEnabled(True)
        
        # Stop loading animation
        if hasattr(self, '_discord_loading_timer') and self._discord_loading_timer:
            self._discord_loading_timer.stop()
        
        # Restore proper button styling
        self.update_discord_button_text()
    
    def _connect_discord_threaded(self):
        """Connect to Discord in background thread."""
        self.connect_discord()
    
    def _disconnect_discord_threaded(self):
        """Disconnect from Discord in background thread."""
        self.disconnect_discord()
    
    def connect_discord(self):
        """Connect to Discord Rich Presence."""
        try:
            from pypresence import Presence
            # You need to create a Discord application at https://discord.com/developers/applications
            # Replace this with your own application ID
            CLIENT_ID = "1447147625361969275"  # Replace with your Discord App ID
            
            self.discord_rpc = Presence(CLIENT_ID)
            self.discord_rpc.connect()
            self.discord_rpc.update(
                state="Browsing Games",
                details="Launching HELXAID",
                large_image="launcher",
                large_text="HELXAID",
            )
            print("Discord Rich Presence connected!")
        except Exception as e:
            print(f"Discord RPC error: {e}")
            self.discord_enabled = False
            self.settings["discord_rpc"] = False
            save_settings(self.settings)
            # Use QTimer.singleShot to update UI from main thread (safe from background thread)
            error_msg = str(e)
            QTimer.singleShot(0, lambda: self._show_discord_error(error_msg))
    
    def _show_discord_error(self, error_msg):
        """Show Discord error message from main thread."""
        self.update_discord_button_text()
        QMessageBox.warning(self, "Discord Error", 
            f"Failed to connect to Discord.\n\nMake sure Discord is running.\n\nError: {error_msg}")
    
    def disconnect_discord(self):
        """Disconnect from Discord Rich Presence."""
        try:
            if hasattr(self, 'discord_rpc') and self.discord_rpc:
                self.discord_rpc.close()
                self.discord_rpc = None
                print("Discord Rich Presence disconnected")
        except Exception as e:
            print(f"Discord disconnect error: {e}")
    
    def update_discord_playing(self, game_name):
        """Update Discord status to show playing a game (and music if playing)."""
        if not self.discord_enabled or not hasattr(self, 'discord_rpc') or not self.discord_rpc:
            return
        try:
            # Check if music is also playing
            music_playing = False
            music_name = None
            if hasattr(self, 'audio_player') and self.audio_player and self.audio_player.is_playing:
                if self.audio_player.playlist and 0 <= self.audio_player.current_index < len(self.audio_player.playlist):
                    import os
                    track_path = self.audio_player.playlist[self.audio_player.current_index]
                    music_name = os.path.splitext(os.path.basename(track_path))[0]
                    if len(music_name) > 80:
                        music_name = music_name[:77] + "..."
                    music_playing = True
            
            if music_playing and music_name:
                # Show BOTH game and music
                self.discord_rpc.update(
                    details=f"Playing {game_name}",
                    state=f"🎵 {music_name}",
                    large_image="launcher",
                    large_text="HELXAID",
                    small_image="music",
                    small_text="Listening to Music",
                )
                print(f"Discord: Playing {game_name} | Music: {music_name}")
            else:
                # Just game
                self.discord_rpc.update(
                    details=f"Playing {game_name}",
                    state="In Game",
                    large_image="launcher",
                    large_text="HELXAID",
                )
                print(f"Discord: Playing {game_name}")
        except Exception as e:
            print(f"Discord update error: {e}")
    
    def update_discord_browsing(self):
        """Update Discord status back to browsing."""
        if not self.discord_enabled or not hasattr(self, 'discord_rpc') or not self.discord_rpc:
            return
        try:
            self.discord_rpc.update(
                state="Browsing Games",
                details="HELXAID",
                large_image="launcher",
                large_text="HELXAID",
            )
            print("Discord: Browsing Games")
        except Exception as e:
            print(f"Discord update error: {e}")
    
    def update_discord_music(self, track_name=None, is_playing=True):
        """Update Discord status to show currently playing music (and game if running)."""
        if not self.discord_enabled or not hasattr(self, 'discord_rpc') or not self.discord_rpc:
            return
            
        try:
            # Check if a game is running
            game_running = hasattr(self, 'current_session') and self.current_session
            game_name = self.current_session.get("game", {}).get("name", "Unknown") if game_running else None
            
            if is_playing and track_name:
                # Clean up track name (remove extension)
                import os
                clean_name = os.path.splitext(os.path.basename(track_name))[0]
                # Truncate if too long
                if len(clean_name) > 80:
                    clean_name = clean_name[:77] + "..."
                
                if game_running:
                    # Show BOTH game and music
                    self.discord_rpc.update(
                        details=f"Playing {game_name}",
                        state=f"🎵 {clean_name}",
                        large_image="launcher",
                        large_text="HELXAID",
                        small_image="music",
                        small_text="Listening to Music",
                    )
                    print(f"Discord: Playing {game_name} | Music: {clean_name}")
                else:
                    # Just music
                    self.discord_rpc.update(
                        details="Listening to Music",
                        state=f"🎵 {clean_name}",
                        large_image="launcher",
                        large_text="HELXAID - Music Player",
                        small_image="music",
                        small_text="Now Playing",
                    )
                    print(f"Discord: Listening to {clean_name}")
            else:
                # Not playing music
                if game_running:
                    # Keep showing game
                    self.update_discord_playing(game_name)
                else:
                    # Back to browsing
                    self.update_discord_browsing()
        except Exception as e:
            print(f"Discord music update error: {e}")
    
    def _on_music_track_changed(self, track_path):
        """Called when track changes - detect video vs audio and update display."""
        VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.flv', '.m4v'}
        
        if not track_path:
            self._is_playing_video = False
            return
        
        ext = os.path.splitext(track_path)[1].lower()
        
        if ext in VIDEO_EXTENSIONS:
            # Playing video - show video background, make content semi-transparent
            self._is_playing_video = True
            
            # Resize video item and content proxy to fill view
            if hasattr(self, 'music_graphics_view') and hasattr(self, 'music_video_item'):
                view_size = self.music_graphics_view.size()
                self.music_video_item.setSize(QSizeF(view_size.width(), view_size.height()))
                
                if hasattr(self, 'music_content_proxy') and hasattr(self, 'music_content'):
                    self.music_content.setFixedSize(view_size.width(), view_size.height())
                    self.music_scene.setSceneRect(0, 0, view_size.width(), view_size.height())
            
            # Apply semi-transparent overlay to content
            if hasattr(self, 'music_content'):
                self.music_content.setStyleSheet("""
                    QWidget#musicContentOverlay {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(18, 18, 18, 0.7),
                            stop:0.5 rgba(18, 18, 18, 0.8),
                            stop:1 rgba(18, 18, 18, 0.95));
                    }
                """)
            print(f"[Music] Playing VIDEO: {os.path.basename(track_path)}")
        else:
            # Playing audio - opaque dark background
            self._is_playing_video = False
            if hasattr(self, 'music_content'):
                self.music_content.setStyleSheet("""
                    QWidget#musicContentOverlay {
                        background: #121212;
                    }
                """)
            print(f"[Music] Playing AUDIO: {os.path.basename(track_path)}")
    
    def _on_track_changed_for_discord(self, track_path):
        """Called when a new track starts playing - update Discord."""
        if hasattr(self, 'audio_player') and self.audio_player and self.audio_player.is_playing:
            self.update_discord_music(track_path, is_playing=True)
    
    def _on_playback_state_changed_for_discord(self, state):
        """Called when playback state changes - update Discord."""
        from PySide6.QtMultimedia import QMediaPlayer
        
        if state == QMediaPlayer.PlayingState:
            # Get current track name
            if hasattr(self, 'audio_player') and self.audio_player:
                if self.audio_player.playlist and 0 <= self.audio_player.current_index < len(self.audio_player.playlist):
                    track_path = self.audio_player.playlist[self.audio_player.current_index]
                    self.update_discord_music(track_path, is_playing=True)
        elif state == QMediaPlayer.StoppedState or state == QMediaPlayer.PausedState:
            # Music stopped or paused - revert to browsing (unless a game is running)
            self.update_discord_music(is_playing=False)
    
    def force_end_game(self):
        """Force end the currently running game."""
        if not self.current_session:
            QMessageBox.information(self, "No Game Running", "No game is currently running.")
            return
        
        game = self.current_session["game"]
        game_name = game.get("name", "Unknown")
        exe_path = game.get("exe", "")
        exe_name = os.path.basename(exe_path).lower() if exe_path else ""
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Force End Game",
            f"Are you sure you want to force end '{game_name}'?\n\nThis will kill the process immediately.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            # Use psutil to find and kill the process
            killed = False
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'].lower() == exe_name:
                        proc.kill()
                        killed = True
                        print(f"Killed process: {proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if not killed:
                # Process not found - it may have already closed
                print(f"Process {exe_name} not found - may have already closed")
            
            # Record play time
            elapsed = int(time.time() - self.current_session["start_time"])
            game["play_time_seconds"] = game.get("play_time_seconds", 0) + elapsed
            game["last_played"] = datetime.now().isoformat()
            save_json(self.data)
            print(f"Force ended: {game_name} (played {elapsed}s)")
            
            # Clear session and update UI
            self.current_session = None
            self.end_game_btn.hide()
            self.populate_recently_played()
            self.update_discord_browsing()
            
            QMessageBox.information(self, "Game Ended", f"'{game_name}' session ended.\nPlay time recorded: {elapsed}s")
            
        except psutil.AccessDenied:
            QMessageBox.warning(self, "Access Denied", f"Cannot end '{game_name}'.\n\nThe game may require administrator privileges to terminate.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error: {e}")
    
    def connect_and_check_running_games(self):
        """Connect to Discord and check if any games are currently running."""
        self.connect_discord()
        
        # Check if any library games are currently running
        if not self.discord_enabled:
            return
            
        try:
            kwargs = {}
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            output = subprocess.check_output(
                ["tasklist"],
                **kwargs,
            ).decode(errors="ignore").lower()
            
            # Check each game in library
            for game in self.data:
                exe_path = game.get("exe", "")
                if not exe_path:
                    continue
                exe_name = os.path.basename(exe_path).lower()
                if exe_name in output:
                    game_name = game.get("name", "Unknown")
                    print(f"Detected running game: {game_name}")
                    
                    # Set up current session tracking
                    self.current_session = {"game": game, "start_time": time.time()}
                    self.end_game_btn.show()
                    
                    self.update_discord_playing(game_name)
                    return  # Found a running game, stop checking
                    
        except Exception as e:
            print(f"Error checking running games: {e}")

    def _scan_for_running_games(self):
        """Background scanner: Detect games running from outside the launcher.
        
        Uses a TWO-PASS approach to avoid false positives from library ordering:
        
        PASS 1: Collect ALL games with at least one matching running process.
                Apply java.exe special-case filtering during this pass.
        
        PASS 2: If already tracking a candidate, keep tracking it.
                If single candidate, detect immediately.
                If multiple candidates, use _disambiguate_candidates() to score
                and pick the best match using path/name/title signals.
        
        Previously used first-match-wins which caused games earlier in the library
        (e.g. Minecraft at index 2) to always beat games later (e.g. WuWa at index 14)
        when both had matching processes due to contaminated game_exe fields.
        """
        # Skip if already tracking a game launched from the launcher
        if self.current_session and self.current_session.get("from_launcher"):
            # Check if the launcher-started game is still running
            game = self.current_session.get("game")
            if game:
                # Check both the launcher exe and the game exe (if different)
                exe_names = self._get_game_exe_names(game)
                game_still_running = any(self._is_process_running(name) for name in exe_names)
                if not game_still_running:
                    # Game launched from launcher has stopped
                    self._handle_game_stopped()
                else:
                    # Game still running - refresh UI to update launcher vs playing status
                    self.populate_recently_played()
            return
        
        # Get set of running process names
        running_exes = self._get_running_processes()
        
        # ===== PASS 1: Collect ALL candidate games with matching processes =====
        candidates = []  # list of (game_dict, matched_exe_name)
        
        for game in self.data:
            exe_names = self._get_game_exe_names(game)
            if not exe_names:
                continue
            
            for exe_name in exe_names:
                if not exe_name or exe_name not in running_exes:
                    continue
                
                # Special case for java.exe (used by TLauncher/Minecraft)
                # Must verify by window title to avoid false positives with other Java apps
                if exe_name in ("java.exe", "javaw.exe"):
                    game_name = game.get("name", "").lower()
                    if "tlauncher" in game_name or "minecraft" in game_name:
                        mc_status = self._is_tlauncher_or_minecraft_running()
                        if mc_status is None:
                            continue  # Not TLauncher/Minecraft window, skip
                    else:
                        continue  # Non-Minecraft game matched java.exe, skip
                
                # This game has a matching running process
                candidates.append((game, exe_name))
                break  # One match per game is enough for candidacy
        
        # No candidates found
        if not candidates:
            if self.current_session and not self.current_session.get("from_launcher"):
                self._handle_game_stopped()
            return
        
        # ===== PASS 2: Already tracking? Single match? Multiple? =====
        
        # Check if we're already tracking one of the candidates
        if self.current_session:
            current_game = self.current_session.get("game", {})
            current_name = current_game.get("name", "")
            for game, _ in candidates:
                if game.get("name") == current_name:
                    # Already tracking this game - just refresh UI
                    self.populate_recently_played()
                    return
        
        # Single candidate - detect immediately (no ambiguity)
        if len(candidates) == 1:
            self._handle_detected_game(candidates[0][0])
            return
        
        # Multiple candidates - disambiguate using scoring
        best = self._disambiguate_candidates(candidates)
        self._handle_detected_game(best)
    
    def _get_game_exe_names(self, game):
        """Get list of process names to check for a game.
        
        Returns list of lowercase exe names including:
        - The launcher/main exe (from 'exe' field)
        - The actual game process (from 'game_exe' field if set)
        
        Automatically filters out system processes from SYSTEM_PROCESS_BLACKLIST
        to prevent false positives from corrupted game_exe data.
        """
        exe_names = []
        
        # Main exe (the launcher or game itself)
        exe_path = game.get("exe", "")
        if exe_path:
            exe_names.append(os.path.basename(exe_path).lower())
        
        # Game exe (for games that have separate launchers)
        # This can be a single exe name or comma-separated list
        game_exe = game.get("game_exe", "")
        if game_exe:
            for name in game_exe.split(","):
                name = name.strip().lower()
                if name and name not in SYSTEM_PROCESS_BLACKLIST:
                    exe_names.append(name)
        
        return exe_names
    
    def _sanitize_game_exes(self):
        """Remove invalid/system processes from all game_exe fields at startup.
        
        Two-pass cleanup:
        1. Remove entries in SYSTEM_PROCESS_BLACKLIST (system services, runtime hosts)
        2. Remove entries whose filename contains ANOTHER game's name
           (e.g. 'wuthering waves.exe' in Minecraft's game_exe)
        
        Called once during __init__ after loading game library data.
        Saves changes to disk if any cleanup was performed.
        """
        changes = False
        
        # Build a set of all game names (lowercase) for cross-contamination check
        game_names = set()
        for g in self.data:
            name = g.get("name", "").lower().strip()
            if name and len(name) > 3:  # Skip very short names to avoid false matches
                game_names.add(name)
        
        for game in self.data:
            game_exe = game.get("game_exe", "")
            if not game_exe:
                continue
            
            game_name = game.get("name", "").lower().strip()
            exes = [e.strip() for e in game_exe.split(",") if e.strip()]
            
            clean = []
            removed = set()
            for e in exes:
                e_lower = e.lower()
                
                # PASS 1: Remove blacklisted system processes
                if e_lower in SYSTEM_PROCESS_BLACKLIST:
                    removed.add(e_lower)
                    continue
                
                # PASS 2: Remove exes that contain ANOTHER game's name
                # e.g. "wuthering waves.exe" should not be in Minecraft's game_exe
                is_foreign = False
                for other_name in game_names:
                    if other_name != game_name and other_name in e_lower:
                        removed.add(e_lower)
                        is_foreign = True
                        break
                
                if not is_foreign:
                    clean.append(e)
            
            if removed:
                game["game_exe"] = ", ".join(clean) if clean else ""
                changes = True
                print(f"[Sanitize] Cleaned {game.get('name', '?')}: removed {removed}")
        
        if changes:
            save_json(self.data)
            print("[Sanitize] Game library cleaned and saved")
    
    def _get_game_install_dir(self, game):
        """Get the root install directory for a game from its exe path.
        
        Extracts the parent directory of the game's main executable.
        Used for path-based validation to verify that a matched process
        actually belongs to this game (not another game sharing the same exe name).
        
        Parameters:
            game: dict with at least an 'exe' key containing the path to the launcher
            
        Returns:
            Lowercase absolute path string, or empty string if unavailable.
        """
        exe_path = game.get("exe", "")
        if exe_path:
            return os.path.dirname(os.path.abspath(exe_path)).lower()
        return ""
    
    def _disambiguate_candidates(self, candidates):
        """Pick the best game from multiple candidates using multi-signal scoring.
        
        When multiple games match running processes (e.g. because of shared exe names
        like client-win64-shipping.exe or contaminated game_exe fields), this method
        scores each candidate to determine which game is actually running.
        
        Scoring signals (from strongest to weakest):
        - +10: Process path is under the game's install directory (strongest proof)
        - +5:  Exe name contains the game's name (e.g. 'wuthering waves.exe')
        - +3:  Window title matches game name (game is actively in foreground)
        - +1:  Window title shows launcher for this game
        - +1:  Matched exe is from game_exe field (not the main launcher exe)
        
        Parameters:
            candidates: list of (game_dict, matched_exe_name) tuples
            
        Returns:
            The game dict with the highest disambiguation score.
        """
        best_game = candidates[0][0]
        best_score = -1
        
        for game, matched_exe in candidates:
            score = 0
            install_dir = self._get_game_install_dir(game)
            
            # PATH MATCH (+10): Process is running from this game's install tree
            # This is the strongest disambiguation signal because each game
            # installs to a unique directory
            if install_dir:
                exe_paths = self._get_process_exe_path(matched_exe)
                for path in exe_paths:
                    if path.lower().startswith(install_dir):
                        score += 10
                        break
            
            # NAME-IN-EXE (+5): The exe filename contains the game's name
            # e.g. "wuthering waves.exe" for game "Wuthering Waves"
            game_name = game.get("name", "").lower()
            if game_name and game_name in matched_exe:
                score += 5
            
            # WINDOW TITLE (+3/+1): Check visible windows for this game
            try:
                status = self._is_in_game_by_window_title(game)
                if status == "game":
                    score += 3
                elif status == "launcher":
                    score += 1
            except Exception:
                pass
            
            # NON-LAUNCHER EXE BONUS (+1): matched exe is a game_exe entry,
            # not just the main launcher exe (more specific match)
            main_exe = os.path.basename(game.get("exe", "")).lower()
            if matched_exe != main_exe:
                score += 1
            
            if score > best_score:
                best_score = score
                best_game = game
        
        print(f"[Disambiguate] Selected: {best_game.get('name', '?')} (score={best_score})")
        return best_game
    
    def _start_process_scan_thread(self):
        """Start a daemon thread that periodically scans running processes
        using psutil and caches the result. This keeps psutil OFF the UI thread
        to prevent 'Not Responding' freezes.
        
        Caches three things:
          - _process_cache:      set of lowercase exe names
          - _process_path_cache: dict mapping lowercase exe name -> set of full paths
          - _process_ppid_cache: dict mapping pid -> ppid (for child-process tracking)
        """
        def _scan_loop():
            while True:
                try:
                    name_set = set()
                    path_dict = {}
                    ppid_dict = {}
                    for p in psutil.process_iter(['name', 'exe', 'ppid']):
                        try:
                            info = p.info
                            name = (info.get('name') or '').lower()
                            exe_path = info.get('exe') or ''
                            ppid = info.get('ppid', 0)
                            
                            if name:
                                name_set.add(name)
                                # Group full paths by name for path-based disambiguation
                                if exe_path:
                                    path_dict.setdefault(name, set()).add(exe_path)
                            
                            # Store ppid mapping for child process awareness
                            if ppid:
                                ppid_dict[p.pid] = ppid
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    with self._process_cache_lock:
                        self._process_cache = name_set
                        self._process_path_cache = path_dict
                        self._process_ppid_cache = ppid_dict
                except Exception:
                    pass
                time.sleep(2.0)  # Scan every 2 seconds in background
        
        t = threading.Thread(target=_scan_loop, daemon=True, name="ProcessScanner")
        t.start()
    
    def _get_running_processes(self):
        """Get set of running process names (lowercase) from background cache.
        
        CRITICAL: This method runs on the UI thread via QTimer.
        It must NEVER call psutil directly -- that blocks the event loop
        for 500ms-2s and causes 'Not Responding'. Instead, it reads from
        the cache populated by _start_process_scan_thread.
        """
        with self._process_cache_lock:
            return set(self._process_cache)  # Return a copy
    
    def _is_process_running(self, exe_name):
        """Check if a specific process is running using cached process list.
        
        CRITICAL: Must NOT call psutil.process_iter() directly.
        Reads from the background-cached process snapshot.
        """
        with self._process_cache_lock:
            return exe_name.lower() in self._process_cache
    
    def _get_process_exe_path(self, exe_name):
        """Get the full executable path(s) for a process name from cache.
        
        Returns set of full paths, or empty set if not found.
        Useful for disambiguating games that share the same exe basename.
        """
        with self._process_cache_lock:
            return set(self._process_path_cache.get(exe_name.lower(), set()))
    
    def _is_child_of_known_launcher(self, exe_name):
        """Check if the given process was spawned by a known platform launcher.
        
        Walks up the process tree via cached ppid mapping. If any ancestor
        is in KNOWN_LAUNCHERS, returns True. This catches games launched via
        Steam, Epic, etc. even when the game exe itself isn't in the library.
        Limits traversal depth to 5 to avoid infinite loops.
        """
        with self._process_cache_lock:
            # Find PIDs for this exe name
            target_pids = []
            for p_name, paths in self._process_path_cache.items():
                if p_name == exe_name.lower():
                    # Get PIDs by checking process cache
                    try:
                        for proc in psutil.process_iter(['name', 'pid']):
                            if (proc.info.get('name') or '').lower() == exe_name.lower():
                                target_pids.append(proc.info['pid'])
                    except Exception:
                        pass
                    break
            
            ppid_cache = dict(self._process_ppid_cache)
        
        # Walk up the tree for each target PID
        for pid in target_pids:
            current = pid
            for _ in range(5):  # Max 5 levels up to avoid infinite loops
                parent_pid = ppid_cache.get(current)
                if not parent_pid or parent_pid == current:
                    break
                # Check parent's name
                try:
                    parent_proc = psutil.Process(parent_pid)
                    parent_name = parent_proc.name().lower()
                    if parent_name in KNOWN_LAUNCHERS:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                current = parent_pid
        
        return False
    
    def _fuzzy_match_game_name(self, game_name, window_title):
        """Check if a game name fuzzy-matches a window title.
        
        Uses multi-strategy matching:
        1. Direct substring: "Wuthering Waves" in "Wuthering Waves - DirectX 12"
        2. Word-based: all significant words of game_name appear in title
        3. Cleaned comparison: strips version numbers, edition suffixes, etc.
        
        Parameters:
            game_name:    The game's display name from the library (e.g. "Wuthering Waves")
            window_title: The actual window title text (e.g. "Wuthering Waves")
            
        Returns True if the title likely belongs to this game.
        """
        if not game_name or not window_title:
            return False
        
        name_lower = game_name.lower().strip()
        title_lower = window_title.lower().strip()
        
        # Strategy 1: Direct substring match (most reliable)
        if name_lower in title_lower:
            return True
        
        # Strategy 2: Word-based match — all significant words must appear
        # Skip short filler words that cause false positives
        skip_words = {"the", "of", "a", "an", "and", "or", "in", "on", "at", "to", "for", "is", "it"}
        name_words = [w for w in re.split(r'[\s\-_:]+', name_lower) if w and w not in skip_words and len(w) > 1]
        
        if name_words and len(name_words) >= 2:
            # For multi-word names, require all significant words
            if all(word in title_lower for word in name_words):
                return True
        
        # Strategy 3: Clean both strings (remove version/edition suffixes, numbers at end)
        def clean(s):
            # Strip common suffixes
            s = re.sub(r'\s*(x64|x86|64bit|32bit|dx11|dx12|vulkan|opengl)\s*', ' ', s, flags=re.IGNORECASE)
            s = re.sub(r'\s*v?\d+\.\d+.*$', '', s)  # Remove version numbers at end
            s = re.sub(r'\s*(edition|remastered|definitive|enhanced|deluxe|goty)\s*', ' ', s, flags=re.IGNORECASE)
            return s.strip()
        
        cleaned_name = clean(name_lower)
        cleaned_title = clean(title_lower)
        if cleaned_name and cleaned_name in cleaned_title:
            return True
        
        return False
    
    def _is_tlauncher_or_minecraft_running(self):
        """Check if TLauncher or Minecraft is actually running by window title.
        
        This is needed because TLauncher uses java.exe which causes false positives
        when other Java apps are running.
        
        Returns: 'game' if Minecraft is running, 'launcher' if TLauncher is open, None otherwise
        """
        if not WINDOWS_API_AVAILABLE:
            return None
        
        try:
            result = {'status': None}
            
            def check_window(hwnd, _):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            title_lower = title.lower()
                            # Check for Minecraft game window (not launcher)
                            if "minecraft" in title_lower and "launcher" not in title_lower and "tlauncher" not in title_lower:
                                result['status'] = 'game'
                                return False  # Stop enumeration
                            # Check for TLauncher window
                            elif "tlauncher" in title_lower:
                                if result['status'] != 'game':  # Don't override game status
                                    result['status'] = 'launcher'
                except Exception:
                    pass
                return True
            
            win32gui.EnumWindows(check_window, None)
            return result['status']
        except Exception:
            return None
    
    def _get_window_titles_for_process(self, exe_name):
        """Get list of window titles for a specific process using win32gui."""
        if not WINDOWS_API_AVAILABLE:
            return []
        
        titles = []
        try:
            def enum_windows_callback(hwnd, results):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        _, pid = win32gui.GetWindowThreadProcessId(hwnd) if hasattr(win32gui, 'GetWindowThreadProcessId') else (0, 0)
                        # Get process by PID
                        try:
                            proc = psutil.Process(pid)
                            if proc.name().lower() == exe_name.lower():
                                title = win32gui.GetWindowText(hwnd)
                                if title:
                                    results.append(title)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception:
                    pass
                return True
            
            win32gui.EnumWindows(enum_windows_callback, titles)
        except Exception as e:
            pass
        
        return titles
    
    def _is_in_game_by_window_title(self, game):
        """Determine if the user is in the actual game or just the launcher.
        
        Uses a generic multi-step algorithm instead of hardcoded per-game patterns:
        
        1. Special case: java.exe based games (TLauncher/Minecraft) - needs exact window check
        2. If game_exe is set and has a visible window with matching title -> "game"
        3. Window title contains a LAUNCHER_TITLE_KEYWORD -> "launcher"
        4. Window title fuzzy-matches the game name (and no launcher keywords) -> "game"
        5. Main exe is in KNOWN_LAUNCHERS and no game window found -> "launcher"
        6. game_exe process is running (no window check needed) -> "game"
        7. Fallback -> "unknown"
        
        Returns: 'game', 'launcher', or 'unknown'
        """
        game_name = game.get("name", "").lower()
        game_exe_list = game.get("game_exe", "")
        launcher_exe = os.path.basename(game.get("exe", "")).lower()
        
        # ===== STEP 1: Special case for java.exe games (TLauncher/Minecraft) =====
        # Java-based games need exact window title matching because java.exe is
        # shared by many non-game applications
        exe_names_all = self._get_game_exe_names(game)
        if any(n in ("java.exe", "javaw.exe") for n in exe_names_all):
            if "tlauncher" in game_name or "minecraft" in game_name:
                mc_status = self._is_tlauncher_or_minecraft_running()
                if mc_status:
                    return mc_status
                return "unknown"
        
        # ===== STEP 2: Collect window titles from all related processes =====
        all_titles = []
        
        # Titles from the launcher exe
        if launcher_exe:
            all_titles.extend(self._get_window_titles_for_process(launcher_exe))
        
        # Titles from game exe(s)
        game_exe_titles = []
        if game_exe_list:
            for exe in game_exe_list.split(","):
                exe = exe.strip()
                if exe:
                    titles = self._get_window_titles_for_process(exe)
                    game_exe_titles.extend(titles)
                    all_titles.extend(titles)
        
        # ===== STEP 3: If game_exe has a visible window, check its title =====
        if game_exe_titles:
            for title in game_exe_titles:
                title_lower = title.lower()
                # game_exe window that is NOT a launcher keyword -> definitely playing
                is_launcher_window = any(kw in title_lower for kw in LAUNCHER_TITLE_KEYWORDS)
                if not is_launcher_window:
                    return "game"
        
        if not all_titles:
            # No windows found — fallback to process-based detection
            if game_exe_list:
                for exe in game_exe_list.split(","):
                    exe_name = exe.strip().lower()
                    if exe_name and self._is_process_running(exe_name):
                        return "game"
            return "unknown"
        
        # ===== STEP 4: Analyze window titles generically =====
        has_game_window = False
        has_launcher_window = False
        
        for title in all_titles:
            title_lower = title.lower()
            
            # Check for launcher keywords in the title
            is_launcher = any(kw in title_lower for kw in LAUNCHER_TITLE_KEYWORDS)
            if is_launcher:
                has_launcher_window = True
                continue
            
            # Fuzzy match: does the window title match the game name?
            if self._fuzzy_match_game_name(game.get("name", ""), title):
                has_game_window = True
        
        # Decide based on what we found
        if has_game_window:
            return "game"
        if has_launcher_window:
            return "launcher"
        
        # ===== STEP 5: Main exe is a known platform launcher =====
        if launcher_exe in KNOWN_LAUNCHERS:
            # The library entry's main exe is just a platform launcher (Steam, Epic, etc.)
            # If no game_exe window was found, user is just browsing the launcher
            if game_exe_list:
                for exe in game_exe_list.split(","):
                    exe_name = exe.strip().lower()
                    if exe_name and self._is_process_running(exe_name):
                        return "game"
            return "launcher"
        
        # ===== STEP 6: UE generic exe detection =====
        # If the game uses a generic Unreal Engine exe name, compare install directories
        if launcher_exe in GENERIC_UE_EXES and game.get("exe"):
            game_install_dir = os.path.dirname(game["exe"]).lower()
            running_paths = self._get_process_exe_path(launcher_exe)
            for rpath in running_paths:
                # Check if the running exe is inside the game's install directory
                if game_install_dir and rpath.lower().startswith(game_install_dir):
                    return "game"
        
        # ===== STEP 7: Fallback - check if game_exe process is running =====
        if game_exe_list:
            for exe in game_exe_list.split(","):
                exe_name = exe.strip().lower()
                if exe_name and self._is_process_running(exe_name):
                    return "game"
        
        return "unknown"
    
    def _handle_detected_game(self, game):
        """Handle when a game is detected running externally."""
        game_name = game.get("name", "Unknown")
        print(f"[Background Detection] Game detected: {game_name}")
        
        # Start tracking session (marked as NOT from launcher)
        self.current_session = {
            "game": game,
            "start_time": time.time(),
            "from_launcher": False
        }
        
        # Update UI
        self.end_game_btn.show()
        self.populate_recently_played()  # Update Currently Playing label
        
        # Update Discord RPC if enabled
        if self.discord_enabled:
            self.update_discord_playing(game_name)
    
    def _handle_game_stopped(self):
        """Handle when a tracked game (external or launcher) stops."""
        if not self.current_session:
            return
        
        game = self.current_session.get("game")
        if game:
            # Calculate and save play time
            elapsed = int(time.time() - self.current_session.get("start_time", time.time()))
            if elapsed > 0:
                game["play_time_seconds"] = game.get("play_time_seconds", 0) + elapsed
                game["last_played"] = datetime.now().isoformat()
                
                # Add to session history
                if "session_history" not in game:
                    game["session_history"] = []
                game["session_history"].append({
                    "duration": elapsed,
                    "date": datetime.now().isoformat()
                })
                
                save_json(self.data)
                game_name = game.get("name", "Unknown")
                print(f"[Background Detection] Game stopped: {game_name} (played {elapsed}s)")
        
        # Clear session and update UI
        self.current_session = None
        self.end_game_btn.hide()
        self.populate_recently_played()  # Update to remove Currently Playing label
        
        # Update Discord RPC
        if self.discord_enabled:
            self.update_discord_browsing()


    def animate_game_added(self, button):
        """Animate the button when a game is added"""
        # Set initial state
        button.setGraphicsEffect(None)  # Remove any existing effects
        
        # Create opacity effect
        opacity_effect = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(opacity_effect)
        
        # Create animations
        opacity_anim = QPropertyAnimation(opacity_effect, b'opacity')
        opacity_anim.setDuration(500)
        opacity_anim.setStartValue(0)
        opacity_anim.setEndValue(1)
        
        # Create scale animation using a property
        button.setProperty('scale', 0.5)
        scale_anim = QPropertyAnimation(button, b'geometry')
        scale_anim.setDuration(500)
        scale_anim.setEasingCurve(QEasingCurve.OutBack)
        
        # Get final geometry
        final_geo = button.geometry()
        
        # Set initial geometry (scaled down and centered)
        initial_geo = final_geo
        initial_geo.setWidth(int(final_geo.width() * 0.5))
        initial_geo.setHeight(int(final_geo.height() * 0.5))
        initial_geo.moveCenter(final_geo.center())
        
        scale_anim.setStartValue(initial_geo)
        scale_anim.setEndValue(final_geo)
        
        # Start animations
        opacity_anim.start()
        scale_anim.start()
        
        # Make sure the button is visible after animation
        button.show()

    def add_game_manual(self):
        exe_path, _ = QFileDialog.getOpenFileName(self, "Pilih Game/Software", "", "Executable (*.exe)")
        if not exe_path:
            return

        # Try to extract icon but don't block if it fails
        icon_path = None
        if WINDOWS_API_AVAILABLE:
            icon_path = extract_icon_from_exe(exe_path)
            if not icon_path:
                print(f"Could not extract icon from {exe_path}")
        else:
            print("Windows API not available - skipping icon extraction")

        # Get the filename and remove .exe extension if present
        name = os.path.basename(exe_path)
        if name.lower().endswith('.exe'):
            name = name[:-4]  # Remove .exe extension
        # Capitalize first letter of the name
        name = name[0].upper() + name[1:]

        # Add to data
        self.data.append({
            "name": name,
            "exe": exe_path,
            "icon": icon_path if icon_path else "",
            "description": ""
        })
        # Persist to config.json; the user can click Refresh to reload the library UI
        save_json(self.data)
        self.show_loading_and_refresh()

    def universal_scan(self):
        """Universal scan combining Steam and Google Play Games."""
        steam_found = self.scan_steam_libraries(silent=True)
        google_found = self.scan_google_play_games(silent=True)
        
        if not steam_found and not google_found:
            QMessageBox.information(self, "Universal Scan", "No new games found in Steam or Google Play Games.")

    def scan_steam_libraries(self, silent=False):
        # Scan Steam libraries and let the user add games automatically.
        common_dirs = self._find_steam_common_dirs()
        if not common_dirs:
            if not silent:
                QMessageBox.information(self, "Steam Scan", "No Steam libraries found.")
            return False

        games = self._find_steam_games(common_dirs)
        if not games:
            if not silent:
                QMessageBox.information(self, "Steam Scan", "No games found in Steam libraries.")
            return False

        # Filter out games that are already in the library (by exe path)
        existing_exes = {os.path.normcase(g.get("exe", "")) for g in self.data if g.get("exe")}
        new_games = [g for g in games if os.path.normcase(g["exe"]) not in existing_exes]
        if not new_games:
            if not silent:
                QMessageBox.information(self, "Steam Scan", "All detected Steam games are already in your library.")
            return False

        # Let user choose which Steam games to add
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Games from Steam")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        info_label = QLabel("Select the Steam games you want to add:")
        layout.addWidget(info_label)

        # Optional helper checkbox to quickly select/deselect all detected games
        select_all_cb = QCheckBox("Select All")
        layout.addWidget(select_all_cb)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(5, 5, 5, 5)
        list_layout.setSpacing(4)

        items = []
        for game in new_games:
            cb = QCheckBox(game["name"])
            cb.setToolTip(game["exe"])
            cb.setStyleSheet("QCheckBox { padding: 2px; }")
            list_layout.addWidget(cb)
            items.append((cb, game))
        
        # Add stretch at end to push items to top
        list_layout.addStretch()

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_widget)
        scroll.setMaximumHeight(300)  # Limit height so dialog isn't too tall
        layout.addWidget(scroll)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        def any_selected():
            return any(cb.isChecked() for cb, _ in items)

        ok_button = button_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setEnabled(False)

        def update_ok():
            btn = button_box.button(QDialogButtonBox.Ok)
            if btn:
                btn.setEnabled(any_selected())

        # When 'Select All' is toggled, check/uncheck all game checkboxes
        def on_select_all_toggled(checked: bool):
            # Use click() so each checkbox fully updates its visual state
            # and emits its own signals. Only click when the state differs.
            for cb, _ in items:
                if cb.isChecked() != checked:
                    cb.click()
            update_ok()

        select_all_cb.toggled.connect(on_select_all_toggled)

        for cb, _ in items:
            cb.stateChanged.connect(lambda _state, u=update_ok: u())

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        result = dialog.exec()
        if result != QDialog.Accepted:
            return False

        selected_games = [game for cb, game in items if cb.isChecked()]
        if not selected_games:
            return False

        # Add the selected games, extracting icons where possible
        for g in selected_games:
            exe_path = g["exe"]
            icon_path = None
            if WINDOWS_API_AVAILABLE:
                icon_path = extract_icon_from_exe(exe_path)
                if not icon_path:
                    print(f"Could not extract icon from {exe_path}")
            else:
                print("Windows API not available - skipping icon extraction")

            name = g["name"]
            self.data.append({
                "name": name,
                "exe": exe_path,
                "icon": icon_path if icon_path else "",
                "description": ""
            })

        save_json(self.data)
        self.show_loading_and_refresh()
        return True
    
    def manage_game_folders(self):
        """Dialog to manage custom game folders to scan."""
        dialog = QDialog(self)
        dialog.setWindowTitle("📁 Manage Local Game Folders")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)
        dialog.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0;")
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header = QLabel("Add folders containing games to auto-detect:")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF5B06;")
        layout.addWidget(header)
        
        # List of folders
        self.folders_list = QTextEdit()
        self.folders_list.setReadOnly(True)
        self.folders_list.setStyleSheet("background: #333; border: 1px solid #555; padding: 10px;")
        
        watch_folders = self.settings.get("watch_folders", [])
        if watch_folders:
            self.folders_list.setText("\n".join(watch_folders))
        else:
            self.folders_list.setPlaceholderText("No folders added yet. Click 'Add Folder' to add one.")
        layout.addWidget(self.folders_list)
        
        # Buttons for add/remove
        btn_layout = QHBoxLayout()
        
        add_btn = AnimatedButton("Add Folder")
        add_btn.setStyleSheet("background: #FF5B06; padding: 10px; border-radius: 5px;")
        
        remove_btn = AnimatedButton("Remove Selected")
        remove_btn.setStyleSheet("background: #333; padding: 10px; border-radius: 5px;")
        
        scan_btn = AnimatedButton("Scan Folders Now")
        scan_btn.setStyleSheet("background: #43B581; padding: 10px; border-radius: 5px;")
        
        def add_folder():
            folder = QFileDialog.getExistingDirectory(dialog, "Select Game Folder")
            if folder:
                watch_folders = self.settings.get("watch_folders", [])
                if folder not in watch_folders:
                    watch_folders.append(folder)
                    self.settings["watch_folders"] = watch_folders
                    save_settings(self.settings)
                    self.folders_list.setText("\n".join(watch_folders))
        
        def remove_folder():
            watch_folders = self.settings.get("watch_folders", [])
            if watch_folders:
                # Remove last folder (simple approach)
                folder, ok = QInputDialog.getItem(
                    dialog, "Remove Folder", "Select folder to remove:",
                    watch_folders, 0, False
                )
                if ok and folder:
                    watch_folders.remove(folder)
                    self.settings["watch_folders"] = watch_folders
                    save_settings(self.settings)
                    self.folders_list.setText("\n".join(watch_folders) if watch_folders else "")
        
        def scan_now():
            dialog.accept()
            self.scan_local_folders()
        
        add_btn.clicked.connect(add_folder)
        remove_btn.clicked.connect(remove_folder)
        scan_btn.clicked.connect(scan_now)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(scan_btn)
        layout.addLayout(btn_layout)
        
        # Close button
        close_btn = AnimatedButton("Close")
        close_btn.setStyleSheet("background: #444; padding: 10px; border-radius: 5px;")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def scan_local_folders(self):
        """Scan user-added folders for games."""
        watch_folders = self.settings.get("watch_folders", [])
        if not watch_folders:
            QMessageBox.information(self, "Scan Local", 
                "No folders configured.\n\nUse 'Manage Local Game Folders' to add folders first.")
            return
        
        # Find games in watch folders
        games = []
        existing_exes = {os.path.normcase(g.get("exe", "")) for g in self.data if g.get("exe")}
        
        for folder in watch_folders:
            if not os.path.exists(folder):
                continue
            
            # Scan folder for game directories
            try:
                for entry in os.listdir(folder):
                    game_dir = os.path.join(folder, entry)
                    if not os.path.isdir(game_dir):
                        continue
                    
                    exe_path = self._find_main_exe_in_dir(game_dir)
                    if not exe_path:
                        continue
                    
                    norm_exe = os.path.normcase(os.path.abspath(exe_path))
                    if norm_exe in existing_exes:
                        continue
                    
                    # Format name from folder
                    name = entry.replace("_", " ").replace("-", " ").strip()
                    if name:
                        name = name[0].upper() + name[1:]
                    games.append({"name": name, "exe": exe_path})
            except Exception as e:
                print(f"Error scanning folder {folder}: {e}")
        
        if not games:
            QMessageBox.information(self, "Scan Local", "No new games found in watched folders.")
            return
        
        # Show selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Games to Add")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        info_label = QLabel(f"Found {len(games)} games. Select which to add:")
        layout.addWidget(info_label)
        
        # Select All checkbox
        select_all_cb = QCheckBox("Select All")
        layout.addWidget(select_all_cb)
        
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(2)  # Minimal spacing between items
        
        items = []
        for game in games:
            cb = QCheckBox(game["name"])
            cb.setToolTip(game["exe"])
            list_layout.addWidget(cb)
            items.append((cb, game))
        
        list_layout.addStretch()  # Push items to top
        
        # Connect Select All to toggle all checkboxes
        def toggle_all():
            checked = select_all_cb.isChecked()
            for cb, _ in items:
                cb.setChecked(checked)
        select_all_cb.clicked.connect(toggle_all)
        
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_widget)
        layout.addWidget(scroll)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() != QDialog.Accepted:
            return
        
        # Add selected games immediately (without icons for now)
        added = 0
        games_to_extract_icons = []
        for cb, g in items:
            if not cb.isChecked():
                continue
            
            exe_path = g["exe"]
            game_entry = {
                "name": g["name"],
                "exe": exe_path,
                "icon": "",  # Will be filled in background
                "description": ""
            }
            self.data.append(game_entry)
            games_to_extract_icons.append(game_entry)
            added += 1
        
        if added > 0:
            save_json(self.data)
            self.show_loading_and_refresh()
            
            # Extract icons in background thread to prevent freezing
            if WINDOWS_API_AVAILABLE and games_to_extract_icons:
                def extract_icons_background():
                    for game in games_to_extract_icons:
                        try:
                            icon_path = extract_icon_from_exe(game["exe"])
                            if icon_path:
                                game["icon"] = icon_path
                                print(f"[Icon] Saved to game data: {icon_path}")
                        except Exception as e:
                            print(f"Icon extraction failed for {game['name']}: {e}")
                    # Save updated data with icons
                    save_json(self.data)
                    print("[Icon] All icons extracted, triggering UI refresh...")
                    # Schedule UI refresh on main thread
                    QTimer.singleShot(100, self.show_loading_and_refresh)
                
                # Start background thread
                icon_thread = threading.Thread(target=extract_icons_background, daemon=True)
                icon_thread = threading.Thread(target=extract_icons_background, daemon=True)
                icon_thread.start()

    def scan_google_play_games(self, silent=False):
        """Scan for games installed via Google Play Games on PC."""
        # Google Play Games creates shortcuts in Start Menu
        gpg_shortcuts_dir = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Google Play Games"
        )
        
        if not os.path.exists(gpg_shortcuts_dir):
            if not silent:
                QMessageBox.information(
                    self, "Google Play Games",
                    "Could not find Google Play Games shortcuts.\n\n"
                    "Please ensure Google Play Games is installed and you have games installed:\n"
                    "https://play.google.com/googleplaygames"
                )
            return False
        
        # Find all .lnk shortcut files
        found_games = []
        existing_paths = set(g.get("exe", "").lower() for g in self.data)
        
        for item in os.listdir(gpg_shortcuts_dir):
            if item.endswith(".lnk"):
                shortcut_path = os.path.join(gpg_shortcuts_dir, item)
                game_name = item.replace(".lnk", "")
                
                # Skip if already added
                if shortcut_path.lower() not in existing_paths:
                    found_games.append((game_name, shortcut_path))
        
        if not found_games:
            if not silent:
                QMessageBox.information(
                    self, "Google Play Games",
                    "No new games found in Google Play Games."
                )
            return False
        
        # Show selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Google Play Games")
        dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(dialog)
        
        label = QLabel(f"Found {len(found_games)} game(s). Select games to add:")
        layout.addWidget(label)
        
        # Scrollable checkbox list
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        checkboxes = []
        for game_name, shortcut_path in found_games:
            cb = QCheckBox(f"{game_name}")
            cb.setChecked(True)
            cb.setProperty("game_data", (game_name, shortcut_path))
            checkboxes.append(cb)
            scroll_layout.addWidget(cb)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_none = QPushButton("Select None")
        ok_btn = QPushButton("Add Selected")
        cancel_btn = QPushButton("Cancel")
        
        btn_layout.addWidget(select_all)
        btn_layout.addWidget(select_none)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes])
        select_none.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes])
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        if dialog.exec() != QDialog.Accepted:
            return False
        
        # Add selected games
        added = 0
        games_without_icons = []
        
        for cb in checkboxes:
            if cb.isChecked():
                game_name, shortcut_path = cb.property("game_data")
                
                # Try to extract icon
                icon_path = ""
                
                # Method 1: Extract from shortcut target
                try:
                    if WINDOWS_API_AVAILABLE and shortcut_path.lower().endswith(".lnk"):
                        shell = win32com.client.Dispatch("WScript.Shell")
                        shortcut = shell.CreateShortCut(shortcut_path)
                        target = shortcut.Targetpath
                        if target and os.path.exists(target):
                            extracted = extract_icon_from_exe(target)
                            if extracted and os.path.exists(extracted):
                                icon_path = extracted
                                print(f"[GooglePlay] Icon extracted from target: {icon_path}")
                except Exception as e:
                    print(f"[GooglePlay] Method 1 failed for {game_name}: {e}")
                
                # Method 2: Extract from shortcut itself
                if not icon_path:
                    try:
                        extracted = extract_icon_from_exe(shortcut_path)
                        if extracted and os.path.exists(extracted):
                            icon_path = extracted
                            print(f"[GooglePlay] Icon extracted from shortcut: {icon_path}")
                    except Exception as e:
                        print(f"[GooglePlay] Method 2 failed for {game_name}: {e}")
                
                game_entry = {
                    "name": game_name,
                    "exe": shortcut_path,  # Launch via shortcut
                    "icon": icon_path,
                    "source": "google_play_games"
                }
                self.data.append(game_entry)
                added += 1
                
                # Track games without icons (only if icon truly missing)
                if not icon_path or not os.path.exists(icon_path):
                    games_without_icons.append(game_entry)
                    print(f"[GooglePlay] No icon for: {game_name}")
        
        if added > 0:
            save_json(self.data)
            self.show_loading_and_refresh()
            QMessageBox.information(self, "Success", f"Added {added} Google Play game(s)!")
            
            # Offer to search for icons for games without icons
            if games_without_icons:
                reply = QMessageBox.question(
                    self, "Missing Icons",
                    f"{len(games_without_icons)} game(s) have no icon.\n\n"
                    "Would you like to search for icons from the internet?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    for game in games_without_icons:
                        icon = self._search_and_download_icon(game["name"], game["exe"])
                        if icon:
                            game["icon"] = icon
                    save_json(self.data)
                    self.show_loading_and_refresh()
        return True

    def _find_steam_common_dirs(self):
        # Return a list of 'steamapps/common' directories for all Steam libraries found.
        common_dirs = []
        seen = set()

        # Candidate libraryfolders.vdf locations on Windows
        drives = [f"{chr(c)}:" for c in range(ord("C"), ord("Z") + 1)]
        candidate_files = []

        # Default install locations
        candidate_files.append(r"C:\\Program Files (x86)\\Steam\\steamapps\\libraryfolders.vdf")
        candidate_files.append(r"C:\\Program Files\\Steam\\steamapps\\libraryfolders.vdf")

        # Additional drives that might contain Steam
        for d in drives:
            candidate_files.append(os.path.join(d + "\\", "Steam", "steamapps", "libraryfolders.vdf"))
            candidate_files.append(os.path.join(d + "\\", "SteamLibrary", "steamapps", "libraryfolders.vdf"))

        for path in candidate_files:
            if os.path.exists(path):
                steam_dirs = self._parse_libraryfolders(path)
                for sd in steam_dirs:
                    common = os.path.join(sd, "steamapps", "common")
                    if os.path.isdir(common):
                        norm = os.path.normcase(os.path.abspath(common))
                        if norm not in seen:
                            seen.add(norm)
                            common_dirs.append(common)

        return common_dirs

    def _parse_libraryfolders(self, vdf_path):
        # Parse a Steam libraryfolders.vdf and return a set of library root paths.
        libs = set()
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            # Newer format: "path" "D:\SteamLibrary"
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                libs.add(m.group(1))

            # Older format: "0" "C:\Program Files (x86)\Steam"
            for m in re.finditer(r'"(\d+)"\s+"([^"]+)"', text):
                libs.add(m.group(2))

            # Always include the Steam folder that owns this file
            steam_dir = os.path.dirname(os.path.dirname(vdf_path))
            libs.add(steam_dir)
        except Exception as e:
            print(f"Failed to parse {vdf_path}: {e}")
        return {os.path.abspath(p) for p in libs}

    def _find_steam_games(self, common_dirs):
        # Return a list of {'name': ..., 'exe': ...} for games under steamapps/common.
        games = []
        seen_exes = set()

        for common in common_dirs:
            try:
                for entry in os.listdir(common):
                    game_dir = os.path.join(common, entry)
                    if not os.path.isdir(game_dir):
                        continue
                    exe_path = self._find_main_exe_in_dir(game_dir)
                    if not exe_path:
                        continue
                    norm_exe = os.path.normcase(os.path.abspath(exe_path))
                    if norm_exe in seen_exes:
                        continue
                    seen_exes.add(norm_exe)

                    # Use folder name as game name, nicely formatted
                    name = entry.replace("_", " ").replace("-", " ").strip()
                    if name:
                        name = name[0].upper() + name[1:]
                    games.append({"name": name, "exe": exe_path})
            except Exception as e:
                print(f"Failed to scan Steam common dir {common}: {e}")

        return games

    def _find_main_exe_in_dir(self, root_dir):
        """Heuristically find the main .exe file in a game directory.
        Uses depth scoring - shallower executables are preferred.
        Priority: launcher names > folder name match > depth score > size
        """
        folder_name = os.path.basename(root_dir).lower()
        # Also try parent parts for matching (e.g., "Plant Versus Zombies Fusion")
        folder_words = set(folder_name.replace("-", " ").replace("_", " ").split())
        
        # Patterns to exclude (utilities, runtimes, not the main game)
        exclude_patterns = [
            "vcredist", "vc_redist", "dxsetup", "setup", "installer",
            "unins", "crashhandler", "unitycrashhandler", "ue4prereqsetup",
            "dotnet", "directx", "redist", "helper", "updater",
            # Java runtime exclusions
            "javaw", "java", "javaws", "jre", "jdk", "runtime",
            # Common system/tool executables
            "createdump", "certutil", "appdata", "patcher",
            # Modding tool executables
            "cpp2il", "dumper", "injector", "doorstop", "proxy"
        ]
        
        # Folder patterns to completely skip scanning
        exclude_folders = [
            "runtime", "jre-legacy", "jre", "jdk", "java", "bin",
            "__pycache__", ".git", "node_modules", "cache", "temp",
            "redist", "redistributables", "prerequisites", "_commonredist",
            "support", "tools", "sdk",
            # Modding tools - should never be detected as game
            "melonloader", "bepinex", "il2cppinspector", "il2cppassemblygenerator",
            "cpp2il", "unhollower", "managed", "mono", "dependencies",
            "plugins", "mods", "userdata", "userlibs", "dotnet",
            # Engine internals
            "engine", "thirdparty", "content", "resources", "data"
        ]
        
        # Subfolders that are valid game locations (treat as near-root)
        valid_game_subfolders = [
            "game files", "gamefiles", "binaries", "win64", "win32",
            "windows", "x64", "x86", "release", "game"
        ]
        
        # Preferred launcher/game names (highest priority)
        launcher_names = [
            "launcher", "game", "play", "start",
            # Common specific launchers
            "tlauncher", "minecraft", 
            # Use folder name words
        ] + list(folder_words)
        
        # Score candidates: (path, size, depth, is_launcher_match, is_folder_match)
        all_candidates = []
        
        try:
            for dirpath, dirnames, filenames in os.walk(root_dir):
                # Calculate depth
                rel_path = os.path.relpath(dirpath, root_dir)
                if rel_path == ".":
                    depth = 0
                    rel_path_lower = ""
                else:
                    depth = rel_path.count(os.sep) + 1
                    rel_path_lower = rel_path.lower()
                
                # Skip excluded folders
                if any(ex in rel_path_lower for ex in exclude_folders):
                    dirnames.clear()
                    continue
                
                # Check if this is a valid game subfolder (treat as depth 0-1)
                is_valid_subfolder = any(vsf in rel_path_lower for vsf in valid_game_subfolders)
                effective_depth = min(depth, 1) if is_valid_subfolder else depth
                
                for fname in filenames:
                    if not fname.lower().endswith(".exe"):
                        continue
                    lower = fname.lower()
                    name_without_ext = lower[:-4]
                    
                    # Skip excluded utilities
                    if any(x in lower for x in exclude_patterns):
                        continue
                    
                    full = os.path.join(dirpath, fname)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    
                    # Check for launcher/game name match
                    is_launcher = any(ln in name_without_ext for ln in launcher_names)
                    
                    # Check folder name word match
                    exe_words = set(name_without_ext.replace("-", " ").replace("_", " ").split())
                    word_overlap = len(folder_words & exe_words)
                    is_folder_match = word_overlap > 0 or folder_name in name_without_ext
                    
                    all_candidates.append({
                        "path": full,
                        "size": size,
                        "depth": effective_depth,
                        "is_launcher": is_launcher,
                        "is_folder_match": is_folder_match,
                        "word_overlap": word_overlap
                    })
                    
        except Exception as e:
            print(f"Error scanning {root_dir} for executables: {e}")
        
        if not all_candidates:
            return None
        
        # Scoring function: lower depth + launcher/folder match + size
        def score(c):
            # Priority multipliers
            depth_penalty = c["depth"] * 1000  # Shallower = better
            launcher_bonus = 50000 if c["is_launcher"] else 0
            folder_bonus = 30000 if c["is_folder_match"] else 0
            word_bonus = c["word_overlap"] * 10000
            size_bonus = c["size"] // 1000000  # Size in MB as tiebreaker
            
            return launcher_bonus + folder_bonus + word_bonus + size_bonus - depth_penalty
        
        # Sort by score (highest first)
        all_candidates.sort(key=score, reverse=True)
        
        best = all_candidates[0]
        print(f"[Scan] Selected: {os.path.basename(best['path'])} (depth={best['depth']}, launcher={best['is_launcher']}, folder_match={best['is_folder_match']})")
        
        return best["path"]

    def show_loading_and_refresh(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Loading")
        layout = QVBoxLayout(dialog)
        label = QLabel("Updating library...")
        progress = QProgressBar()
        progress.setRange(0, 0)  # Indeterminate/busy mode
        layout.addWidget(label)
        layout.addWidget(progress)

        def finish():
            self.refresh()
            dialog.accept()

        QTimer.singleShot(800, finish)
        dialog.exec()

    def launch_game(self, path):
        """Launch a game or app via the Windows shell.

        Using os.startfile() is closer to how Explorer/shortcuts launch apps,
        and supports both .exe and .lnk targets.
        """
        if os.name == 'nt' and path:
            exe_name = os.path.basename(path)
            try:
                kwargs = {}
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
                    **kwargs,
                ).decode(errors="ignore")
                if exe_name.lower() in output.lower() and "No tasks are running" not in output:
                    QMessageBox.information(self, "Game already running", "Game already running!")
                    return
            except Exception as e:
                print(f"Failed to check if game is already running: {e}")

        try:
            # Launch from the game's directory (important for cracked games)
            game_dir = os.path.dirname(path)
            
            # Use subprocess.Popen with flags to create a fully independent process
            # This ensures the game doesn't close when the launcher exits
            # DETACHED_PROCESS: The process runs independently of the console
            # CREATE_NEW_PROCESS_GROUP: Creates a new process group (doesn't share console signals)
            # CREATE_BREAKAWAY_FROM_JOB: Allows the process to break away from any job object
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            CREATE_NO_WINDOW = 0x08000000
            
            creation_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
            
            try:
                # First try subprocess.Popen which gives us the most control over process creation
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 1  # SW_SHOWNORMAL
                
                # Note: Do NOT use start_new_session=True on Windows, it's a Unix feature
                # and can actually prevent the process from being properly detached
                process = subprocess.Popen(
                    [path],
                    cwd=game_dir,
                    creationflags=creation_flags,
                    startupinfo=startupinfo,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True
                )
                # Don't keep a reference to the process - let it run independently
                del process
            except (PermissionError, OSError) as popen_error:
                # If Popen fails (e.g., needs elevation), fall back to ShellExecuteW
                import ctypes
                result = ctypes.windll.shell32.ShellExecuteW(
                    None,           # hwnd
                    "runas",        # operation - request elevation
                    path,           # file to execute
                    None,           # parameters
                    game_dir,       # working directory
                    1               # SW_SHOWNORMAL
                )
                
                if result <= 32:
                    raise OSError(f"Failed to launch with admin privileges (error {result})")
            
            # Update last_played timestamp for recently played feature
            for game in self.data:
                if game.get("exe") == path:
                    game["last_played"] = datetime.now().isoformat()
                    # Set first_played only if not already set (first time playing)
                    if not game.get("first_played"):
                        game["first_played"] = datetime.now().isoformat()
                    # Set date_added if not already set
                    if not game.get("date_added"):
                        game["date_added"] = datetime.now().isoformat()
                    save_json(self.data)
                    
                    # Track current session for live stats (marked as from launcher)
                    self.current_session = {"game": game, "start_time": time.time(), "from_launcher": True}
                    
                    # Show End Game button
                    self.end_game_btn.show()
                    
                    # Update Discord Rich Presence to show playing this game
                    self.update_discord_playing(game.get("name", "Unknown"))
                    
                    # Start play time tracking in background thread
                    self.start_play_time_tracking(path, game)
                    
                    # Apply game booster optimizations if enabled
                    self._apply_game_booster(exe_name, game)
                    break
                    
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Gagal menjalankan aplikasi.\n\n{e}"
            )
    
    def _apply_game_booster(self, exe_name: str, game: dict):
        """Apply booster optimizations when a game is launched.
        
        Checks booster_settings.json and applies:
        - set_game_priority: Set game to High priority
        - disable_winkey: Block Windows key
        """
        try:
            import json
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            if not os.path.exists(settings_path):
                return
            
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            selected = settings.get("essential_optimizations", [])
            
            if not selected:
                return
            
            from essential_optimizations import get_optimizer
            optimizer = get_optimizer()
            
            print(f"[Booster] Applying optimizations for {game.get('name', exe_name)}: {selected}")
            
            # Set Game Priority - wait a bit for process to start
            if "set_game_priority" in selected:
                def apply_priority():
                    import time
                    time.sleep(3)  # Wait for game process to fully start
                    result = optimizer.set_game_priority(exe_name, "high")
                    if result.get("success"):
                        print(f"[Booster] Game priority set to HIGH for {exe_name}")
                    else:
                        print(f"[Booster] Failed to set priority: {result.get('error')}")
                
                import threading
                threading.Thread(target=apply_priority, daemon=True).start()
            
            # Disable Windows Key
            if "disable_winkey" in selected:
                result = optimizer.disable_windows_key()
                if result.get("success"):
                    print(f"[Booster] Windows key disabled for gaming")
        
        except Exception as e:
            print(f"[Booster] Error applying game booster: {e}")
    
    def start_play_time_tracking(self, path, game):
        """Start background thread to track play time."""
        exe_name = os.path.basename(path).lower()
        start_time = time.time()
        
        # Get processes before launching to detect new ones later
        processes_before = self._get_running_processes()
        
        def track_play_time():
            """Monitor game process and record play time when it exits."""
            time.sleep(5)  # Wait for game to fully start
            
            # Detect new processes (child processes spawned by the launcher)
            processes_after = self._get_running_processes()
            new_processes = processes_after - processes_before
            
            # Build the game's install directory path for path-based filtering
            # Only learn processes whose exe path is under this directory
            game_install_dir = os.path.dirname(os.path.abspath(path)).lower()
            
            # Collect exes already claimed by OTHER games in the library
            # to prevent cross-contamination (e.g. WuWa's exes leaking into Minecraft)
            other_game_exes = set()
            for other_game in self.data:
                if other_game.get("name") != game.get("name"):
                    for e in self._get_game_exe_names(other_game):
                        other_game_exes.add(e)
            
            detected_game_exes = []
            for proc in new_processes:
                proc_lower = proc.lower()
                
                # FILTER 1: Skip system processes (comprehensive blacklist)
                if proc_lower in SYSTEM_PROCESS_BLACKLIST:
                    continue
                
                # FILTER 2: Skip the launcher exe itself
                if proc_lower == exe_name:
                    continue
                
                # FILTER 3: Skip processes already owned by another game
                # Prevents cross-game contamination from concurrent game launches
                if proc_lower in other_game_exes:
                    continue
                
                # FILTER 4: Path check — only learn processes running from
                # the game's install directory tree. This is the strongest filter.
                proc_paths = self._get_process_exe_path(proc_lower)
                if proc_paths:
                    # Process has known path(s) — require at least one under install dir
                    if not any(p.lower().startswith(game_install_dir) for p in proc_paths):
                        continue
                
                detected_game_exes.append(proc)
            
            # If we detected new game processes, save them
            if detected_game_exes:
                existing_game_exe = game.get("game_exe", "")
                existing_exes = set(x.strip().lower() for x in existing_game_exe.split(",") if x.strip())
                new_exes = [e for e in detected_game_exes if e.lower() not in existing_exes]
                
                if new_exes:
                    # Add new detected exes to the game
                    combined = list(existing_exes) + new_exes
                    game["game_exe"] = ", ".join(combined)
                    save_json(self.data)
                    print(f"[Auto-detect] Saved game processes for {game.get('name', 'Unknown')}: {new_exes}")
            
            # Get all exe names to monitor (launcher + game processes)
            exe_names_to_check = self._get_game_exe_names(game)
            
            while True:
                try:
                    # Check if any of the game's processes are still running
                    game_running = False
                    for check_exe in exe_names_to_check:
                        if self._is_process_running(check_exe):
                            game_running = True
                            break
                    
                    if not game_running:
                        # Game has exited - record play time
                        elapsed = int(time.time() - start_time)
                        game["play_time_seconds"] = game.get("play_time_seconds", 0) + elapsed
                        
                        # Record session to history for avg/longest calculation
                        session_history = game.get("session_history", [])
                        session_history.append({
                            "duration": elapsed,
                            "date": datetime.now().isoformat()
                        })
                        game["session_history"] = session_history
                        
                        save_json(self.data)
                        print(f"Play time recorded: {elapsed}s for {game.get('name', 'Unknown')}")
                        
                        # Update Discord status back to browsing
                        self.update_discord_browsing()
                        
                        # Clear current session tracking and hide End Game button
                        self.current_session = None
                        self.end_game_btn.hide()
                        break
                except Exception as e:
                    print(f"Play time tracking error: {e}")
                    break
                
                time.sleep(5)  # Check every 5 seconds
        
        thread = threading.Thread(target=track_play_time, daemon=True)
        thread.start()

    def launch_omen_hub(self):
        """Launch OMEN Gaming Hub via its app ID using PowerShell."""
        app_id = r"AD2F1837.OMENCommandCenter_v10z8vjag6ke6!AD2F1837.OMENCommandCenter"
        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f'Start-Process "shell:AppsFolder\\{app_id}"'
            ]
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Gagal menjalankan OMEN Gaming Hub.\n\n{e}"
            )

    def show_context_menu(self, pos, game, button):
        menu = QMenu(self)

        # Favorite toggle
        is_favorite = game.get("favorite", False)
        favorite_action = menu.addAction("★ Remove from Favorites" if is_favorite else "☆ Add to Favorites")
        
        # Hide toggle
        is_hidden = game.get("hidden", False)
        hide_action = menu.addAction("Show Game" if is_hidden else "Hide Game")
        
        menu.addSeparator()
        
        # Open Install Folder
        folder_action = menu.addAction("Open Install Folder")
        
        # More Info
        info_action = menu.addAction("More Info...")
        
        menu.addSeparator()
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")

        action = menu.exec(button.mapToGlobal(pos))

        if action == favorite_action:
            game["favorite"] = not is_favorite
            save_json(self.data)
            self.refresh()
        elif action == hide_action:
            game["hidden"] = not is_hidden
            save_json(self.data)
            self.refresh()
        elif action == folder_action:
            exe_path = game.get("exe", "")
            if exe_path and os.path.exists(exe_path):
                folder = os.path.dirname(exe_path)
                os.startfile(folder)
        elif action == info_action:
            self._show_game_more_info(game)
        elif action == edit_action:
            self.edit_game(game)
        elif action == delete_action:
            self.confirm_delete_game(game)

    def edit_game(self, game):
        # Create a new window for editing
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle("Edit Game")
        edit_dialog.setMinimumWidth(500)
        
        # Store the original game reference
        self.current_edit_game = game
        
        # Main layout
        layout = QVBoxLayout(edit_dialog)
        
        # Game Name
        name_layout = QHBoxLayout()
        name_label = QLabel("Name:")
        self.name_edit = QLineEdit(game["name"])
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit)
        
        # Category
        category_layout = QHBoxLayout()
        category_label = QLabel("Category:")
        self.category_edit = QLineEdit(game.get("category", ""))
        self.category_edit.setPlaceholderText("e.g., Action, RPG, Puzzle")
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_edit)
        
        # Notes (replaces description)
        notes_layout = QVBoxLayout()
        notes_label = QLabel("Notes:")
        self.notes_edit = QTextEdit(game.get("notes", ""))
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlaceholderText("Personal notes, tips, or reminders about this game...")
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.notes_edit)
        
        # Launch Options
        launch_layout = QHBoxLayout()
        launch_label = QLabel("Launch Options:")
        self.launch_edit = QLineEdit(game.get("launch_options", ""))
        self.launch_edit.setPlaceholderText("e.g., -windowed -novid")
        launch_layout.addWidget(launch_label)
        launch_layout.addWidget(self.launch_edit)
        
        # App Type Override
        type_layout = QHBoxLayout()
        type_label = QLabel("Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Auto-detect", "Game", "Utility"])
        self.type_combo.setStyleSheet("""
            QComboBox {
                background: rgba(30, 30, 30, 0.9);
                border: 1px solid #FF5B06;
                border-radius: 5px;
                padding: 3px 10px;
                color: #e0e0e0;
                font-size: 12px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e;
                border: 1px solid #FF5B06;
                selection-background-color: #FF5B06;
                font-size: 12px;
            }
        """)
        current_type = game.get("app_type", "auto")
        if current_type == "game":
            self.type_combo.setCurrentIndex(1)
        elif current_type == "utility":
            self.type_combo.setCurrentIndex(2)
        else:
            self.type_combo.setCurrentIndex(0)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        
        # File Directory
        file_layout = QHBoxLayout()
        file_label = QLabel("Executable:")
        self.file_edit = QLineEdit(game["exe"])
        self.file_edit.setReadOnly(True)
        browse_btn = AnimatedButton("Browse...")
        browse_btn.clicked.connect(lambda: self.browse_file())
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(browse_btn)
        
        # Icon Preview
        icon_layout = QVBoxLayout()
        icon_label = QLabel("Icon:")
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setStyleSheet("background-color: #3a3a3a; border: 1px solid #5a5a5a;")
        
        if game.get("icon") and os.path.exists(game["icon"]):
            pixmap = QPixmap(game["icon"]).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_preview.setPixmap(pixmap)
        
        change_icon_btn = AnimatedButton("Change icon from local...")
        change_icon_btn.clicked.connect(lambda: self.change_icon())
        
        # Reimport icon from exe button
        reimport_icon_btn = AnimatedButton("Reimport Icon from .exe")
        reimport_icon_btn.setToolTip("Re-extract icon from the game's executable file")
        
        def reimport_icon():
            exe_path = self.file_edit.text()
            if not exe_path or not os.path.exists(exe_path):
                QMessageBox.warning(edit_dialog, "Error", "Executable file not found!")
                return
            
            # Force re-extract the icon
            icon_path = extract_icon_from_exe(exe_path)
            if icon_path:
                self.current_edit_game["icon"] = icon_path
                self.update_icon_preview(icon_path)
                # Save and refresh the game grid
                save_json(self.data)
                self.refresh()
                QMessageBox.information(edit_dialog, "Success", "Icon reimported successfully!")
            else:
                QMessageBox.warning(edit_dialog, "Error", "Could not extract icon from executable.")
        
        reimport_icon_btn.clicked.connect(reimport_icon)
        
        icon_layout.addWidget(icon_label)
        icon_layout.addWidget(self.icon_preview)
        icon_layout.addWidget(change_icon_btn)
        icon_layout.addWidget(reimport_icon_btn)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(lambda: self.save_edit(edit_dialog))
        button_box.rejected.connect(edit_dialog.reject)
        
        # Add all to main layout
        layout.addLayout(name_layout)
        layout.addLayout(category_layout)
        layout.addLayout(launch_layout)
        layout.addLayout(type_layout)
        layout.addLayout(file_layout)
        layout.addLayout(icon_layout)
        layout.addWidget(button_box)
        
        edit_dialog.exec()
    
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Executable",
            os.path.dirname(self.file_edit.text()) if self.file_edit.text() else "",
            "Executable (*.exe)"
        )
        if file_path:
            self.file_edit.setText(file_path)
            # Auto-extract icon when new exe is selected
            icon_path = extract_icon_from_exe(file_path)
            if icon_path:
                self.current_edit_game["icon"] = icon_path
                self.update_icon_preview(icon_path)
    
    def change_icon(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.ico)"
        )
        if file_path:
            self.current_edit_game["icon"] = file_path
            self.update_icon_preview(file_path)
    
    def update_icon_preview(self, icon_path):
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_preview.setPixmap(pixmap)
    
    def save_edit(self, dialog):
        # Update game data
        self.current_edit_game["name"] = self.name_edit.text().strip()
        self.current_edit_game["notes"] = self.notes_edit.toPlainText().strip()
        self.current_edit_game["category"] = self.category_edit.text().strip()
        self.current_edit_game["launch_options"] = self.launch_edit.text().strip()
        
        # Save app type override
        type_index = self.type_combo.currentIndex()
        if type_index == 0:
            self.current_edit_game["app_type"] = "auto"
        elif type_index == 1:
            self.current_edit_game["app_type"] = "game"
        else:
            self.current_edit_game["app_type"] = "utility"
        
        # Only update EXE and icon if they changed
        new_exe = self.file_edit.text().strip()
        if new_exe and new_exe != self.current_edit_game["exe"]:
            self.current_edit_game["exe"] = new_exe
            # Re-extract icon for new exe if no custom icon was chosen
            if not self.current_edit_game.get("icon"):
                icon_path = extract_icon_from_exe(new_exe)
                if icon_path:
                    self.current_edit_game["icon"] = icon_path
                    self.update_icon_preview(icon_path)
        
        # Icon is already updated in self.current_edit_game by change_icon/browse_file
        save_json(self.data)
        self.refresh()
        dialog.accept()

    def multi_delete(self):
        if not self.data:
            QMessageBox.information(self, "Multi Delete", "There are no games to delete.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Multi Delete")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        info_label = QLabel("Select the games you want to delete:")
        layout.addWidget(info_label)

        # Optional helper checkbox to quickly select/deselect all games
        select_all_cb = QCheckBox("Select All")
        layout.addWidget(select_all_cb)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(2)

        items = []
        for game in self.data:
            cb = QCheckBox(game.get("name", ""))
            list_layout.addWidget(cb)
            items.append((cb, game))

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_widget)
        layout.addWidget(scroll)

        confirm_label = QLabel('Type "DELETE GAMES" to confirm deleting the selected games.')
        layout.addWidget(confirm_label)

        input_edit = QLineEdit()
        input_edit.setPlaceholderText("Type \"DELETE GAMES\" to confirm")
        layout.addWidget(input_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = button_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setEnabled(False)

        def update_ok_button():
            btn = button_box.button(QDialogButtonBox.Ok)
            if not btn:
                return
            any_selected = any(cb.isChecked() for cb, _ in items)
            btn.setEnabled(any_selected and input_edit.text().strip() == "DELETE GAMES")

        # When 'Select All' is toggled, check/uncheck all game checkboxes
        def on_select_all_toggled(checked: bool):
            # Use click() so each checkbox fully updates its visual state
            # and emits its own signals. Only click when the state differs.
            for cb, _ in items:
                if cb.isChecked() != checked:
                    cb.click()
            update_ok_button()

        select_all_cb.toggled.connect(on_select_all_toggled)

        input_edit.textChanged.connect(lambda _text: update_ok_button())
        for cb, _game in items:
            cb.stateChanged.connect(lambda _state, u=update_ok_button: u())

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        layout.addWidget(button_box)

        result = dialog.exec()
        if result == QDialog.Accepted and input_edit.text().strip() == "DELETE GAMES":
            selected_games = [game for cb, game in items if cb.isChecked()]
            if not selected_games:
                return
            for game in selected_games:
                self.delete_game(game, save_and_refresh=False)
            # force_save=True to allow deleting all games intentionally
            save_json(self.data, force_save=True)
            self.refresh()

    def confirm_delete_game(self, game):
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Game")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        name = game.get("name", "")
        label = QLabel(f'Type "DELETE" to delete this game:\n\n{name}')
        input_edit = QLineEdit()
        input_edit.setPlaceholderText("Type DELETE to confirm")

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = button_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setEnabled(False)

        def on_text_changed(text):
            btn = button_box.button(QDialogButtonBox.Ok)
            if btn:
                btn.setEnabled(text.strip() == "DELETE")

        input_edit.textChanged.connect(on_text_changed)

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        layout.addWidget(label)
        layout.addWidget(input_edit)
        layout.addWidget(button_box)

        result = dialog.exec()
        if result == QDialog.Accepted and input_edit.text().strip() == "DELETE":
            self.delete_game(game, save_and_refresh=True)

    def delete_game(self, game, save_and_refresh=True):
        # Remember the icon path before removing the game
        icon_path = game.get("icon")

        # Remove the game from the in-memory list
        if game in self.data:
            self.data.remove(game)

        # If this icon is not used by any other game, delete the file from disk
        if icon_path:
            still_used = any(g.get("icon") == icon_path for g in self.data)
            if not still_used:
                try:
                    # Resolve absolute paths
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    icons_dir = os.path.join(script_dir, "icons")

                    # Build absolute path to icon
                    if os.path.isabs(icon_path):
                        abs_icon_path = icon_path
                    else:
                        abs_icon_path = os.path.abspath(os.path.join(script_dir, icon_path))

                    # Only delete if icon lives inside the icons directory
                    if os.path.commonpath([abs_icon_path, icons_dir]) == icons_dir and os.path.exists(abs_icon_path):
                        os.remove(abs_icon_path)
                except Exception as e:
                    print(f"Failed to delete icon file {icon_path}: {e}")
        if save_and_refresh:
            # force_save=True allows deleting all games intentionally
            save_json(self.data, force_save=True)
            self.refresh()




if __name__ == "__main__":
    # Suppress Qt warning messages (like QFont::setPointSize warnings)
    import warnings
    warnings.filterwarnings("ignore")
    
    # Also suppress Qt's internal warning messages
    os.environ["QT_LOGGING_RULES"] = "*.warning=false"
    
    # Enable WebEngine DevTools (connect to localhost:9222 in Chrome to inspect)
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"
    
    # Set Windows AppUserModelID BEFORE QApplication (required for taskbar icon)
    if os.name == 'nt':
        try:
            import ctypes
            myappid = 'HELXAID'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    
    # Single instance check using QSharedMemory + QLocalServer for window activation
    # Use different keys for debug (.py) and production (.exe) to allow both to run
    from PySide6.QtCore import QSharedMemory
    from PySide6.QtNetwork import QLocalSocket, QLocalServer
    
    # Detect if running as frozen exe or as Python script (debug mode)
    is_frozen = getattr(sys, 'frozen', False)
    instance_key = "HELXAIDSingleInstance_EXE" if is_frozen else "HELXAIDSingleInstance_DEBUG"
    server_name = "HELXAIDLocalServer_EXE" if is_frozen else "HELXAIDLocalServer_DEBUG"
    
    shared_mem = QSharedMemory(instance_key)
    if not shared_mem.create(1):
        # Another instance is already running - try to signal it to restore
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if socket.waitForConnected(1000):
            socket.write(b"RESTORE")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            print("[SingleInstance] Signaled existing instance to restore")
        else:
            print("[SingleInstance] Could not connect to existing instance server")
        sys.exit(0)
    
    app = QApplication(sys.argv)
    
    # Initialize Debug Console (captures stdout/stderr for viewing in .exe mode)
    # Press F12 to toggle visibility
    try:
        from DebugConsoleWidget import get_debug_console
        debug_console = get_debug_console()
    except Exception as e:
        print(f"[Debug] Could not init debug console: {e}")
    
    # =============================================
    # SPLASH SCREEN - Show while loading
    # =============================================
    from PySide6.QtWidgets import QSplashScreen, QProgressBar, QVBoxLayout, QWidget, QLabel
    from PySide6.QtGui import QPixmap, QPainter, QColor, QFont as QFontGui
    from PySide6.QtCore import Qt, QTimer
    
    # Create splash screen
    class LoadingSplash(QSplashScreen):
        def __init__(self):
            # Create a pixmap for the splash
            splash_pixmap = QPixmap(400, 250)
            splash_pixmap.fill(QColor("#121212"))
            
            # Draw content on pixmap
            painter = QPainter(splash_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw gradient background
            from PySide6.QtGui import QLinearGradient
            gradient = QLinearGradient(0, 0, 0, 250)
            gradient.setColorAt(0, QColor("#1a1a1a"))
            gradient.setColorAt(1, QColor("#0a0a0a"))
            painter.fillRect(0, 0, 400, 250, gradient)
            
            # Draw accent line
            painter.fillRect(0, 0, 400, 3, QColor("#FF5B06"))
            
            # Draw title
            title_font = QFontGui("Orbitron", 24, QFontGui.Bold)
            painter.setFont(title_font)
            painter.setPen(QColor("#FF5B06"))
            painter.drawText(0, 60, 400, 50, Qt.AlignCenter, "HELXAID")
            
            # Draw subtitle
            sub_font = QFontGui("Segoe UI", 10)
            painter.setFont(sub_font)
            painter.setPen(QColor("#888888"))
            painter.drawText(0, 100, 400, 30, Qt.AlignCenter, "Game Launcher, Music Player and utilities")
            
            # Draw loading text placeholder
            painter.setPen(QColor("#666666"))
            painter.drawText(0, 200, 400, 30, Qt.AlignCenter, "Loading...")
            
            painter.end()
            
            super().__init__(splash_pixmap)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            
            # Add progress bar overlay
            self.progress = 0
            self.status_text = "Initializing..."
            
        def drawContents(self, painter):
            # Draw the base pixmap content
            super().drawContents(painter)
            
            # Draw loading bar
            bar_y = 170
            bar_width = 300
            bar_height = 4
            bar_x = (400 - bar_width) // 2
            
            # Background
            painter.fillRect(bar_x, bar_y, bar_width, bar_height, QColor("#333333"))
            
            # Progress
            progress_width = int((self.progress / 100) * bar_width)
            painter.fillRect(bar_x, bar_y, progress_width, bar_height, QColor("#FF5B06"))
            
            # Status text
            painter.setPen(QColor("#888888"))
            font = QFontGui("Segoe UI", 9)
            painter.setFont(font)
            painter.drawText(0, 185, 400, 30, Qt.AlignCenter, self.status_text)
        
        def setProgress(self, value, status=""):
            self.progress = min(100, max(0, value))
            if status:
                self.status_text = status
            self.repaint()
    
    splash = LoadingSplash()
    splash.show()
    app.processEvents()
    
    # Progress: Loading fonts
    splash.setProgress(10, "Loading fonts...")
    app.processEvents()
    
    # Load bundled Orbitron font
    from PySide6.QtGui import QFont, QFontDatabase
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    orbitron_loaded = False
    if os.path.exists(fonts_dir):
        for font_file in os.listdir(fonts_dir):
            if font_file.endswith('.ttf') or font_file.endswith('.otf'):
                font_path = os.path.join(fonts_dir, font_file)
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    orbitron_loaded = True
                    print(f"[Font] Loaded: {font_file}")
    
    splash.setProgress(30, "Loading configuration...")
    app.processEvents()
    
    # Set default application font (Orbitron if loaded, else Segoe UI fallback)
    if orbitron_loaded:
        default_font = QFont("Orbitron", 10)
    else:
        default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)
    
    splash.setProgress(50, "Initializing launcher...")
    app.processEvents()
    
    # Exclude this process from RivaTuner/MSI Afterburner OSD overlay.
    # RTSS hooks per-process via D3D injection. Writing its profile
    # with EnableHooking=0 is the official supported opt-out method.
    _exclude_from_rtss()
    
    # Create main window
    w = GameLauncher()
    
    splash.setProgress(90, "Almost ready...")
    app.processEvents()
    
    # Check if we should start minimised
    start_min = w.settings.get("start_minimised", False)
    has_tray = hasattr(w, 'tray_icon') and w.tray_icon is not None
    print(f"[Startup] start_minimised={start_min}, has_tray_icon={has_tray}")
    
    if start_min:
        # Start hidden to tray (don't show main window)
        splash.setProgress(100, "Starting minimized...")
        app.processEvents()
        splash.close()
        
        # Ensure tray icon is created and visible
        if hasattr(w, 'tray_icon') and w.tray_icon:
            w.tray_icon.show()
            w.tray_icon.showMessage(
                "HELXAID",
                "Running in system tray",
                QSystemTrayIcon.Information,
                2000
            )
        # Window stays hidden
    else:
        splash.setProgress(100, "Ready!")
        app.processEvents()
        
        # Close splash and show main window
        splash.finish(w)
        w.show()
    
    sys.exit(app.exec())
    
    