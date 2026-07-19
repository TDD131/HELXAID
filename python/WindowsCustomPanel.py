"""
Windows Customization Panel - HELRCUS

Features:
- Invisible Lock Screen (transparent screensaver that blocks input)
- Windows Update Custom (control Windows Update behavior)

Component Name: WindowsCustomPanel
"""

import os
import sys
import json
import subprocess
import ctypes
from ctypes import wintypes
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QGroupBox, QCheckBox, QSpinBox,
    QComboBox, QSlider, QLineEdit, QFormLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QApplication
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import Qt, Signal, QTimer, QSize, Slot, QObject
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QLinearGradient
from AnimatedButton import AnimatedCheckBox

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
HELRCUS_CONFIG_PATH = os.path.join(APPDATA_DIR, "helrcus_settings.json")


def _load_helrcus_config():
    """Load HELRCUS settings from disk."""
    defaults = {
        "lock_screen": {
            "enabled": False,
            "hotkey": "Ctrl+Alt+L",
            "unlock_hotkey": "Ctrl+Shift+L",
            "opacity": 1,
            "auto_lock_minutes": 0,
            "lock_on_exit": True,
            "pin_hash": ""
        },
        "windows_update": {
            "pause_updates": False,
            "pause_years": 1,
            "pause_until_date": "",
            "disable_auto_restart": False,
            "active_hours_preset": "Customize",
            "active_hours_start": 8,
            "active_hours_end": 23,
            "metered_connection": False
        }
    }
    try:
        if os.path.exists(HELRCUS_CONFIG_PATH):
            with open(HELRCUS_CONFIG_PATH, 'r') as f:
                saved = json.load(f)
                # Merge with defaults
                for key in defaults:
                    if key not in saved:
                        saved[key] = defaults[key]
                    else:
                        for subkey in defaults[key]:
                            if subkey not in saved[key]:
                                saved[key][subkey] = defaults[key][subkey]
                return saved
    except Exception as e:
        print(f"[HELRCUS] Error loading config: {e}")
    return defaults


def _save_helrcus_config(config):
    """Save HELRCUS settings to disk."""
    try:
        os.makedirs(os.path.dirname(HELRCUS_CONFIG_PATH), exist_ok=True)
        tmp_path = HELRCUS_CONFIG_PATH + ".tmp"
        with open(tmp_path, 'w') as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, HELRCUS_CONFIG_PATH)
    except Exception as e:
        print(f"[HELRCUS] Error saving config: {e}")


def _parse_hotkey_string(hotkey_str):
    """
    Parse a hotkey string like 'Ctrl+Alt+L' into (modifiers, vk_code).
    Returns (None, None) if parsing fails.
    """
    if not hotkey_str:
        return None, None
        
    parts = hotkey_str.split("+")
    modifiers = 0
    vk_code = None
    
    # Windows API modifiers
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    
    # Qt/Windows virtual key codes
    vk_map = {
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
        "ESC": 0x1B, "TAB": 0x09, "BACKSPACE": 0x08,
        "ENTER": 0x0D, "SPACE": 0x20, "INSERT": 0x2D,
        "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
        "PAGEUP": 0x21, "PAGEDOWN": 0x22,
        "LEFT": 0x25, "RIGHT": 0x27, "UP": 0x26, "DOWN": 0x28,
        "CAPSLOCK": 0x14, "NUMLOCK": 0x90, "PAUSE": 0x13,
        "PRINTSCREEN": 0x2C
    }
    
    for part in parts:
        part_upper = part.upper()
        if part_upper == "CTRL":
            modifiers |= MOD_CONTROL
        elif part_upper == "ALT":
            modifiers |= MOD_ALT
        elif part_upper == "SHIFT":
            modifiers |= MOD_SHIFT
        elif part_upper == "WIN":
            modifiers |= MOD_WIN
        else:
            # Base key
            if part_upper in vk_map:
                vk_code = vk_map[part_upper]
            elif len(part_upper) == 1:
                vk_code = ord(part_upper)
            elif part_upper.startswith("KEY") and part_upper[3:].isdigit():
                vk_code = int(part_upper[3:])
                
    return modifiers, vk_code


class HotkeyRecordButton(QPushButton):
    """
    A button that records a hotkey when clicked.
    Click to start recording, press a key, it captures it.
    
    Component Name: HotkeyRecordButton
    """
    
    hotkeyChanged = Signal(str)
    recordingStarted = Signal()
    recordingStopped = Signal()
    
    def __init__(self, default_key: str = "Ctrl+Alt+L", parent=None, min_keys=3, forbidden_keys=None):
        super().__init__(parent)
        self._recording = False
        self._min_keys = min_keys
        self._forbidden_keys = forbidden_keys or []
        self._hotkey = default_key
        self.setText(default_key.upper())
        self.setFixedWidth(160)
        self.setToolTip("Click to record a new activation hotkey")
        self.clicked.connect(self._start_recording)
        self._update_style()
        
    def setForbiddenKeys(self, keys: list):
        self._forbidden_keys = keys
        
    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background: #FF5B06;
                    color: white;
                    border: none;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.4);
                    color: #e0e0e0;
                    border: none;
                    padding: 8px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #FF5B06;
                    color: white;
                }
            """)
            
    def _start_recording(self):
        self._recording = True
        self.setText("Press key...")
        self._update_style()
        self.setFocus()
        self.recordingStarted.emit()
        
    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()
            
            # Check for modifier keys pressed alone
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                event.accept()
                return
                
            key_name = self._key_to_name(key)
            
            modifiers = []
            if event.modifiers() & Qt.ControlModifier:
                modifiers.append("Ctrl")
            if event.modifiers() & Qt.ShiftModifier:
                modifiers.append("Shift")
            if event.modifiers() & Qt.AltModifier:
                modifiers.append("Alt")
            if event.modifiers() & Qt.MetaModifier:
                modifiers.append("Win")
                
            if modifiers:
                full_key = "+".join(modifiers) + "+" + key_name
            else:
                full_key = key_name
                
            parts = full_key.split("+")
            if len(parts) < self._min_keys:
                self.setText(f"Min {self._min_keys} keys!")
                event.accept()
                return
                
            if full_key in self._forbidden_keys:
                self.setText("Key in use!")
                event.accept()
                return
                
            self._hotkey = full_key
            self.setText(full_key.upper())
            self._recording = False
            self._update_style()
            self.recordingStopped.emit()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self.setText(self._hotkey.upper())
            self._update_style()
            self.recordingStopped.emit()
        super().focusOutEvent(event)
        
    def _key_to_name(self, key: int) -> str:
        """Convert Qt key code to key name."""
        key_map = {
            Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
            Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
            Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
            Qt.Key_Escape: "Esc", Qt.Key_Tab: "Tab", Qt.Key_Backspace: "Backspace",
            Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter", Qt.Key_Space: "Space",
            Qt.Key_Insert: "Insert", Qt.Key_Delete: "Delete", Qt.Key_Home: "Home",
            Qt.Key_End: "End", Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown",
            Qt.Key_Left: "Left", Qt.Key_Right: "Right", Qt.Key_Up: "Up", Qt.Key_Down: "Down",
            Qt.Key_CapsLock: "CapsLock", Qt.Key_NumLock: "NumLock",
            Qt.Key_Pause: "Pause", Qt.Key_Print: "PrintScreen",
        }
        
        if key in key_map:
            return key_map[key]
        elif 65 <= key <= 90:  # A-Z
            return chr(key).upper()
        elif Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)
        else:
            return f"Key{key}"
            
    def hotkey(self) -> str:
        return self._hotkey
        
    def setHotkey(self, key: str):
        self._hotkey = key
        self.setText(key.upper())


class FeatureCard(QFrame):
    """
    Reusable card widget for each feature section.
    
    Component Name: FeatureCard
    """
    
    def __init__(self, title: str, description: str = "", icon_path: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("featureCard")
        self._title = title
        self._description = description
        self._icon_path = icon_path
        self._setup_ui()
    
    def _setup_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(12)
        
        # Header row
        header = QHBoxLayout()
        header.setSpacing(12)
        
        if self._icon_path and os.path.exists(self._icon_path):
            icon_label = QLabel()
            icon_pixmap = QPixmap(self._icon_path)
            icon_scaled = icon_pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_scaled)
            icon_label.setFixedSize(28, 28)
            icon_label.setStyleSheet("background: transparent;")
            header.addWidget(icon_label)
        
        title_container = QVBoxLayout()
        title_container.setSpacing(2)
        
        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet("""
            color: #e0e0e0; 
            font-size: 16px; 
            font-weight: bold; 
            background: transparent;
        """)
        title_container.addWidget(self.title_label)
        
        if self._description:
            self.desc_label = QLabel(self._description)
            self.desc_label.setStyleSheet("""
                color: #888888; 
                font-size: 11px; 
                background: transparent;
            """)
            self.desc_label.setWordWrap(True)
            title_container.addWidget(self.desc_label)
        
        header.addLayout(title_container, 1)
        self._layout.addLayout(header)
    
    def add_content(self, widget):
        """Add a widget to the card content area."""
        self._layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Add a layout to the card content area."""
        self._layout.addLayout(layout)


# ============================================
# INVISIBLE LOCK SCREEN FEATURE
# ============================================

class LockScreenSignals(QObject):
    show_password = Signal()

lock_signals = LockScreenSignals()

class LockScreenOverlay(QWidget):
    """Qt Overlay panel that shows 'Screen is Locked' with an Unlock button."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("lockScreenOverlay")
        
        self.setFixedSize(300, 160)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 22, 0.98);
                border: none;
                border-radius: 12px;
            }
        """)
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(14)
        
        # Lock icon + title
        title = QLabel("🔒  Screen is Locked")
        title.setStyleSheet("color: #E0E0E0; font-size: 16px; font-weight: 600; border: none; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(title)
        
        hint = QLabel("Click Unlock to verify your identity")
        hint.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        hint.setAlignment(Qt.AlignCenter)
        vbox.addWidget(hint)
        
        # Unlock button
        unlock_btn = QPushButton("Unlock")
        unlock_btn.setCursor(Qt.PointingHandCursor)
        unlock_btn.setFixedHeight(36)
        unlock_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 91, 6, 0.9);
                border: none;
                color: #FFF;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: rgba(255, 120, 40, 1.0);
            }
            QPushButton:pressed {
                background: rgba(200, 70, 5, 1.0);
            }
        """)
        unlock_btn.clicked.connect(self._do_unlock)
        vbox.addWidget(unlock_btn)
        
        layout.addWidget(container)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
    
    def _do_unlock(self):
        """Unlock via Windows lock screen."""
        self.close()
        InvisibleLockScreen.unlock()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
    
    def focusOutEvent(self, event):
        # Only collapse if focus moved completely outside this window
        focused = QApplication.focusWidget()
        if focused is not None and self.isAncestorOf(focused):
            super().focusOutEvent(event)
            return
        InvisibleLockScreen.set_visibility(False)
        self.close()
        super().focusOutEvent(event)




class InvisibleLockScreen:
    """
    Implements the transparent lock screen feature.
    Creates a fullscreen transparent overlay that blocks input,
    unlockable via Ctrl+L, then triggers Windows Lock Screen.
    
    Based on: https://github.com/billiegoose/lock-screen
    """
    
    _instance = None
    _active = False
    _hwnd = None
    _current_opacity = 100
    _overlay_shown = False
    _verifying = False  # True while Windows Hello dialog is open
    _lock = threading.Lock()
    
    @classmethod
    def is_active(cls):
        with cls._lock:
            return cls._active
    
    @classmethod
    def unlock(cls):
        """Unlock the HELXAID lock screen and trigger the Windows lock screen."""
        with cls._lock:
            if cls._active and cls._hwnd:
                import ctypes
                # Call LockWorkStation FIRST (while hwnd is still valid)
                ctypes.windll.user32.LockWorkStation()
                # Then tear down the lock screen
                cls._active = False
                ctypes.windll.user32.PostMessageW(cls._hwnd, 0x0010, 0, 0)  # WM_CLOSE
    
    @classmethod
    def set_visibility(cls, visible):
        """Toggle background opacity when password overlay appears/disappears."""
        with cls._lock:
            if not cls._active or not cls._hwnd:
                return
            hwnd_val = cls._hwnd
            opacity_val = cls._current_opacity
            cls._overlay_shown = visible
            
        import ctypes
        user32 = ctypes.windll.user32
        # LWA_ALPHA = 0x00000002
        if visible:
            alpha = int(255 * (opacity_val / 100))
        else:
            alpha = 1  # 1 is practically invisible but still receives mouse clicks
        user32.SetLayeredWindowAttributes(hwnd_val, 0, alpha, 2)
    
    
    @classmethod
    def activate(cls, opacity=100, unlock_hotkey="Ctrl+Shift+L"):
        """Activate the invisible lock screen overlay."""
        with cls._lock:
            if cls._active:
                return
            
            cls._active = True
            cls._current_opacity = opacity
            
        # Use a thread to run the lock screen logic
        thread = threading.Thread(target=cls._run_lock, args=(opacity, unlock_hotkey), daemon=True)
        thread.start()
    
    @classmethod
    def deactivate(cls):
        """Deactivate and trigger Windows lock."""
        with cls._lock:
            cls._active = False
    
    @classmethod
    def _run_lock(cls, opacity, unlock_hotkey):
        """Run the lock screen overlay using Win32 API."""
        try:
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            gdi32 = ctypes.windll.gdi32
            
            # Explicitly define argtypes for 64-bit compatibility to prevent OverflowError
            # when handling 64-bit pointers (WPARAM, LPARAM, HINSTANCE).
            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = wintypes.LPARAM
            
            user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
            user32.UnregisterClassW.restype = wintypes.BOOL
            
            # Window class registration
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, wintypes.HWND, ctypes.c_uint,
                wintypes.WPARAM, wintypes.LPARAM
            )
            
            WS_EX_TOPMOST = 0x00000008
            WS_EX_LAYERED = 0x00080000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_POPUP = 0x80000000
            WS_VISIBLE = 0x10000000
            GWL_EXSTYLE = -20
            LWA_ALPHA = 0x02
            WM_DESTROY = 0x0002
            WM_KEYDOWN = 0x0100
            WM_HOTKEY = 0x0312
            VK_L = 0x4C
            MOD_CONTROL = 0x0002
            
            # Calculate opacity byte (1-255, where 1 = nearly invisible)
            alpha_byte = max(1, min(255, int(opacity * 2.55)))  # opacity is 1-100
            
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            
            # Create a simple message-only approach using hotkey
            # Register Ctrl+L as the unlock hotkey
            HOTKEY_ID = 9999
            
            # Create invisible fullscreen window
            class_name = "HelrcusLockScreen"
            
            # Parse unlock_hotkey
            unlock_modifiers, unlock_vk = _parse_hotkey_string(unlock_hotkey)
            if unlock_modifiers is None or unlock_vk is None:
                unlock_modifiers, unlock_vk = 0x0002, 0x4C  # Fallback to Ctrl+L
                
            class WNDCLASSEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("style", ctypes.c_uint),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HICON),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HICON),
                ]
            
            hwnd_ref = [None]
            cls._hwnd = None
            
            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == 0x0312 and wparam == HOTKEY_ID:  # WM_HOTKEY
                    # Ctrl+L pressed - unlock
                    cls.unlock()
                    return 0
                elif msg == 0x0201:  # WM_LBUTTONDOWN
                    # Show background + "Screen is Locked" overlay
                    if not cls._overlay_shown:
                        cls._overlay_shown = True
                        cls.set_visibility(True)
                        lock_signals.show_password.emit()
                    return 0
                elif msg == 0x0010:  # WM_CLOSE
                    user32.UnregisterHotKey(hwnd, HOTKEY_ID)
                    user32.DestroyWindow(hwnd)
                    return 0
                elif msg == 0x0002:  # WM_DESTROY
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            
            wnd_proc_cb = WNDPROC(wnd_proc)
            
            # Explicitly set restype to HMODULE so the full 64-bit handle is
            # preserved on 64-bit Python (default c_int would truncate it).
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            hInstance = kernel32.GetModuleHandleW(None)
            # Cast to c_void_p so CreateWindowExW receives the correct pointer type
            hInstance_ptr = ctypes.c_void_p(hInstance)
            
            wc = WNDCLASSEX()
            wc.cbSize = ctypes.sizeof(WNDCLASSEX)
            wc.style = 0
            wc.lpfnWndProc = wnd_proc_cb
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hInstance
            wc.hIcon = None
            
            # Load standard arrow cursor to prevent 'AppStarting' / loading cursor
            user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
            user32.LoadCursorW.restype = wintypes.HICON
            wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
            wc.hbrBackground = gdi32.CreateSolidBrush(0x00000000)  # Black
            wc.lpszMenuName = None
            wc.lpszClassName = class_name
            wc.hIconSm = None
            
            atom = user32.RegisterClassExW(ctypes.byref(wc))
            if not atom:
                print("[HELRCUS] Failed to register window class")
                cls._active = False
                return
            
            # Explicitly define argtypes to prevent ctypes from implicitly casting 
            # pointer/handle arguments to 32-bit integers, which causes OverflowError
            user32.CreateWindowExW.argtypes = [
                wintypes.DWORD,      # dwExStyle
                wintypes.LPCWSTR,    # lpClassName
                wintypes.LPCWSTR,    # lpWindowName
                wintypes.DWORD,      # dwStyle
                ctypes.c_int,        # x
                ctypes.c_int,        # y
                ctypes.c_int,        # nWidth
                ctypes.c_int,        # nHeight
                wintypes.HWND,       # hWndParent
                wintypes.HMENU,      # hMenu
                wintypes.HINSTANCE,  # hInstance
                ctypes.c_void_p      # lpParam
            ]
            user32.CreateWindowExW.restype = wintypes.HWND
            
            # Create the window — pass hInstance_ptr (c_void_p) to avoid
            # OverflowError on 64-bit when hInstance is a large int.
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW,
                class_name,
                "HELRCUS Lock",
                WS_POPUP | WS_VISIBLE,
                0, 0, screen_w, screen_h,
                None, None, hInstance_ptr, None
            )
            
            if not hwnd:
                print("[HELRCUS] Failed to create lock window")
                cls._active = False
                return
            
            hwnd_ref[0] = hwnd
            with cls._lock:
                cls._hwnd = hwnd
            
            # Start completely invisible (alpha = 1)
            user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
            
            # Register unlock hotkey
            user32.RegisterHotKey(hwnd, HOTKEY_ID, unlock_modifiers, unlock_vk)
            
            # Bring to front and capture focus
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            
            # Block input by keeping window on top
            # Message loop
            msg = wintypes.MSG()
            while cls._active:
                ret = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
                if ret:
                    if msg.message == 0x0012:  # WM_QUIT
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # Keep window on top ONLY when not verifying (Windows Hello needs to be above)
                    if hwnd_ref[0] and not cls._verifying:
                        user32.SetWindowPos(hwnd_ref[0], -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE
                    ctypes.windll.kernel32.Sleep(50)
            
            # Cleanup
            if hwnd_ref[0]:
                user32.UnregisterHotKey(hwnd_ref[0], HOTKEY_ID)
                user32.DestroyWindow(hwnd_ref[0])
            
            user32.UnregisterClassW(class_name, hInstance)
            with cls._lock:
                cls._active = False
                cls._hwnd = None
            
        except Exception as e:
            print(f"[HELRCUS] Lock screen error: {e}")
            import traceback
            traceback.print_exc()
            with cls._lock:
                cls._active = False
                cls._hwnd = None


# ============================================
# WINDOWS UPDATE CONTROL
# ============================================

class WindowsUpdateControl:
    """
    Controls Windows Update behavior via registry and services.
    Requires admin privileges for some operations.
    """
    
    @staticmethod
    def is_admin():
        """Check if running with admin privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    
    @staticmethod
    def _execute_admin_commands(commands):
        """Execute a list of commands. If not admin, prompts for UAC elevation without console flash."""
        if WindowsUpdateControl.is_admin():
            success = True
            error_msg = ""
            for cmd in commands:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if res.returncode != 0:
                    success = False
                    error_msg = res.stderr.strip()
            return success, error_msg
        else:
            # Need elevation - use VBS wrapper to prevent console flash
            import tempfile, os, time
            
            temp_dir = tempfile.gettempdir()
            bat_path = os.path.join(temp_dir, "helxaid_wu_commands.bat")
            vbs_path = os.path.join(temp_dir, "helxaid_wu_wrapper.vbs")
            log_path = os.path.join(temp_dir, "helxaid_wu_log.txt")
            
            # Write commands to batch file
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write("@echo off\n")
                for cmd in commands:
                    f.write(cmd + "\n")
                # Write an empty file to indicate completion
                f.write(f'echo done > "{log_path}"\n')
            
            # Write VBS wrapper (0 = hide window, True = wait for exit)
            vbs_script = f'Set objShell = CreateObject("WScript.Shell")\nobjShell.Run Chr(34) & "{bat_path}" & Chr(34), 0, True\n'
            with open(vbs_path, 'w', encoding='utf-8') as f:
                f.write(vbs_script)
                
            # Clear previous log
            if os.path.exists(log_path):
                try: os.remove(log_path)
                except OSError: pass
                
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "wscript.exe",
                    f'//B //Nologo "{vbs_path}"',
                    None, 0  # SW_HIDE
                )
                
                if ret > 32:
                    # ShellExecute is async, wait for log file or timeout
                    # UAC might take time, so we wait up to 60 seconds
                    for _ in range(120):
                        time.sleep(0.5)
                        if os.path.exists(log_path):
                            time.sleep(0.2) # Give it a moment to finish writing
                            break
                    
                    return True, ""
                else:
                    return False, "Action cancelled (UAC denied) or failed."
            except Exception as e:
                return False, str(e)
            finally:
                # Cleanup
                for path_to_clean in [bat_path, vbs_path, log_path]:
                    if os.path.exists(path_to_clean):
                        try: os.remove(path_to_clean)
                        except OSError: pass

    @staticmethod
    def pause_updates(days_or_date):
        """Pause Windows Updates for specified days or until a specific datetime."""
        try:
            from datetime import datetime, timedelta, timezone
            if isinstance(days_or_date, datetime):
                pause_until = days_or_date
            else:
                pause_until = datetime.now() + timedelta(days=days_or_date)
                
            # Convert naive local datetime to local system tz, then to UTC
            pause_until_utc = pause_until.astimezone().astimezone(timezone.utc)
            pause_str = pause_until_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            now_utc = datetime.now().astimezone().astimezone(timezone.utc)
            now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Use reg command to set pause
            commands = [
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseUpdatesExpiryTime /t REG_SZ /d "{pause_str}" /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseFeatureUpdatesStartTime /t REG_SZ /d "{now_str}" /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseQualityUpdatesStartTime /t REG_SZ /d "{now_str}" /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseFeatureUpdatesEndTime /t REG_SZ /d "{pause_str}" /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseQualityUpdatesEndTime /t REG_SZ /d "{pause_str}" /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseUpdatesState /t REG_DWORD /d 1 /f',
            ]
            
            success, error_msg = WindowsUpdateControl._execute_admin_commands(commands)
            
            if success:
                return True, f"Updates paused until {pause_until.strftime('%d/%m/%Y')}"
            else:
                return False, f"Failed to pause updates: {error_msg}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def resume_updates():
        """Resume Windows Updates by removing pause keys."""
        try:
            keys_to_delete = [
                "PauseUpdatesExpiryTime",
                "PauseFeatureUpdatesStartTime",
                "PauseQualityUpdatesStartTime",
                "PauseFeatureUpdatesEndTime",
                "PauseQualityUpdatesEndTime",
                "PauseUpdatesState",
            ]
            commands = []
            for key in keys_to_delete:
                commands.append(f'reg delete "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v {key} /f')
            
            # Restart Windows Update service to make changes take effect immediately
            commands.append('net stop wuauserv & net start wuauserv')
            
            success, error_msg = WindowsUpdateControl._execute_admin_commands(commands)
            
            if success:
                return True, "Updates resumed"
            else:
                return False, f"Failed to resume updates: {error_msg}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def disable_auto_restart():
        """Disable automatic restart after updates."""
        try:
            cmd = 'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f'
            success, error_msg = WindowsUpdateControl._execute_admin_commands([cmd])
            return success, "Auto-restart disabled" if success else f"Failed: {error_msg}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def enable_auto_restart():
        """Re-enable automatic restart after updates."""
        try:
            cmd = 'reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoRebootWithLoggedOnUsers /f'
            success, error_msg = WindowsUpdateControl._execute_admin_commands([cmd])
            return success, "Auto-restart enabled" if success else f"Failed: {error_msg}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def set_active_hours(start=8, end=23):
        """Set Windows Update active hours (won't restart during these hours)."""
        try:
            commands = [
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v ActiveHoursStart /t REG_DWORD /d {start} /f',
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v ActiveHoursEnd /t REG_DWORD /d {end} /f',
            ]
            
            success, error_msg = WindowsUpdateControl._execute_admin_commands(commands)
            
            if success:
                return True, f"Active hours set: {start:02d}:00 - {end:02d}:00"
            else:
                return False, f"Failed to set active hours: {error_msg}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def set_metered_connection(enable=True):
        """Set current network as metered to limit update downloads."""
        try:
            # Get current network adapter GUID
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\DefaultMediaCost"
            if enable:
                cmd = f'reg add "HKLM\\{key_path}" /v Ethernet /t REG_DWORD /d 2 /f'
            else:
                cmd = f'reg add "HKLM\\{key_path}" /v Ethernet /t REG_DWORD /d 1 /f'
            result = subprocess.run(cmd, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            status = "enabled" if enable else "disabled"
            return result.returncode == 0, f"Metered connection {status}"
        except Exception as e:
            return False, str(e)
    @staticmethod
    def get_update_status():
        """Get current Windows Update pause status."""
        try:
            result = subprocess.run(
                'reg query "HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings" /v PauseUpdatesExpiryTime',
                shell=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and "PauseUpdatesExpiryTime" in result.stdout:
                # Extract the date
                for line in result.stdout.split('\n'):
                    if "PauseUpdatesExpiryTime" in line:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            raw_date = parts[-1]
                            try:
                                # Standard registry format is "YYYY-MM-DDTHH:MM:SSZ"
                                date_part = raw_date.split('T')[0]
                                from datetime import datetime as _dt
                                parsed = _dt.strptime(date_part, "%Y-%m-%d")
                                return True, parsed.strftime("%d/%m/%Y")
                            except Exception:
                                return True, raw_date
            return False, "Not paused"
        except Exception:
            return False, "Unknown"


# ============================================
# MAIN PANEL WIDGET
# ============================================

class WindowsCustomPanel(QWidget):
    """
    HELRCUS - Windows Customization Panel.
    
    Features:
    - Invisible Lock Screen
    - Windows Update Custom
    
    Component Name: WindowsCustomPanel
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("windowsCustomPanel")
        self._config = _load_helrcus_config()
        self._setup_ui()
        self._load_state()
        QTimer.singleShot(100, self._register_global_hotkey)
        lock_signals.show_password.connect(self._show_lock_overlay)

    def _setup_ui(self):
        """Build the panel UI."""
        # Build absolute path for icons
        script_dir = os.path.dirname(os.path.abspath(__file__))
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow.png").replace("\\", "/")
        
        self.setStyleSheet(f"""
            QWidget#windowsCustomPanel {{
                background: transparent;
            }}

            QFrame#featureCard {{
                background: rgba(28, 28, 30, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }}
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin-top: 12px;
                padding: 15px;
                font-weight: bold;
                color: #FF5B06;
                background: rgba(30, 33, 40, 0.6);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
            }}

            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 25px;
                border-left: 1px solid rgba(255, 91, 6, 0.3);
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background: rgba(255, 91, 6, 0.3);
            }}
            QComboBox::down-arrow {{
                image: url({down_arrow_path});
                width: 12px;
                height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }}
            QLabel {{
                color: #e0e0e0;
                background: transparent;
            }}
            QCheckBox {{
                color: #e0e0e0;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #555;
                background: rgba(30, 33, 40, 0.9);
            }}
            QCheckBox::indicator:checked {{
                background: #FF5B06;
                border: 2px solid #FF5B06;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: #404040;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #FF5B06;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: #FF5B06;
                border-radius: 3px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 91, 6, 0.5);
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #FF5B06;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: rgba(255, 91, 6, 0.3);
                border: none;
                width: 20px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.6);
            }}
        """)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Scrollable content
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(20)
        
        # ===== HEADER =====
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        title_label = QLabel("HELRCUS")
        title_label.setStyleSheet("""
            color: #FF5B06;
            font-size: 28px;
            font-weight: bold;
            font-family: 'Orbitron';
        """)
        header_layout.addWidget(title_label)
        
        subtitle_label = QLabel("Windows Customization")
        subtitle_label.setStyleSheet("""
            color: #888888;
            font-size: 13px;
            font-family: 'Orbitron';
        """)
        header_layout.addWidget(subtitle_label)
        
        content_layout.addLayout(header_layout)
        
        # ===== INVISIBLE LOCK SCREEN CARD =====
        self._setup_lock_screen_card(content_layout)
        
        # ===== WINDOWS UPDATE CARD =====
        self._setup_windows_update_card(content_layout)
        
        # Bottom spacer
        content_layout.addStretch()
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    
    def _setup_lock_screen_card(self, parent_layout):
        """Setup the Invisible Lock Screen feature card."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        lock_icon = os.path.join(script_dir, "UI Reguler", "lock.png")
        
        card = FeatureCard(
            title="Invisible Lock Screen",
            description="Transparent overlay that blocks mouse & keyboard. Unlock with Ctrl+L, then Windows Lock Screen appears.",
            icon_path=lock_icon
        )
        
        # Status indicator
        self._lock_status = QLabel("● Inactive")
        self._lock_status.setStyleSheet("color: #888888; font-size: 12px; font-weight: 500;")
        card.add_content(self._lock_status)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(255, 255, 255, 0.05); max-height: 1px; border: none;")
        card.add_content(sep)
        
        # Controls
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(12)
        
        # Opacity slider
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(10)
        opacity_row.setAlignment(Qt.AlignVCenter)
        opacity_lbl = QLabel("Opacity:")
        opacity_lbl.setFixedWidth(140)
        opacity_lbl.setStyleSheet("font-size: 12px;")
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(1, 100)
        self._opacity_slider.setValue(self._config["lock_screen"]["opacity"])
        self._opacity_slider.setFixedHeight(20)
        self._opacity_value = QLabel(f"{self._config['lock_screen']['opacity']}%")
        self._opacity_value.setFixedWidth(40)
        self._opacity_value.setStyleSheet("font-size: 12px; color: #FF5B06;")
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(opacity_lbl)
        opacity_row.addWidget(self._opacity_slider, 1)
        opacity_row.addWidget(self._opacity_value)
        controls_layout.addLayout(opacity_row)
        
        # Global Activation Hotkey
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(10)
        hotkey_row.setAlignment(Qt.AlignVCenter)
        hotkey_lbl = QLabel("Activation Hotkey:")
        hotkey_lbl.setFixedWidth(140)
        hotkey_lbl.setStyleSheet("font-size: 12px;")
        
        self._activation_hotkey_btn = HotkeyRecordButton(self._config["lock_screen"].get("hotkey", "Ctrl+Alt+L"))
        self._activation_hotkey_btn.hotkeyChanged.connect(self._on_activation_hotkey_changed)
        # Pause the OS-level hotkey while the user is recording a new one,
        # otherwise the current combo fires the lock screen before Qt captures it.
        self._activation_hotkey_btn.recordingStarted.connect(self._unregister_global_hotkey)
        self._activation_hotkey_btn.recordingStopped.connect(self._register_global_hotkey)
        
        hotkey_hint = QLabel("(Global activation)")
        hotkey_hint.setStyleSheet("color: #666; font-size: 10px;")
        
        hotkey_row.addWidget(hotkey_lbl)
        hotkey_row.addWidget(self._activation_hotkey_btn)
        hotkey_row.addWidget(hotkey_hint)
        hotkey_row.addStretch()
        controls_layout.addLayout(hotkey_row)
        
        # Global Unlock Hotkey
        unlock_row = QHBoxLayout()
        unlock_row.setSpacing(10)
        unlock_row.setAlignment(Qt.AlignVCenter)
        unlock_lbl = QLabel("Unlock Hotkey:")
        unlock_lbl.setFixedWidth(140)
        unlock_lbl.setStyleSheet("font-size: 12px;")
        
        self._unlock_hotkey_btn = HotkeyRecordButton(self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L"))
        self._unlock_hotkey_btn.hotkeyChanged.connect(self._on_unlock_hotkey_changed)
        self._unlock_hotkey_btn.recordingStarted.connect(self._unregister_global_hotkey)
        self._unlock_hotkey_btn.recordingStopped.connect(self._register_global_hotkey)
        
        unlock_hint = QLabel("(Unlock when active)")
        unlock_hint.setStyleSheet("color: #666; font-size: 10px;")
        
        unlock_row.addWidget(unlock_lbl)
        unlock_row.addWidget(self._unlock_hotkey_btn)
        unlock_row.addWidget(unlock_hint)
        unlock_row.addStretch()
        controls_layout.addLayout(unlock_row)
        
        # Cross-validation setup
        self._activation_hotkey_btn.setForbiddenKeys([self._unlock_hotkey_btn.hotkey()])
        self._unlock_hotkey_btn.setForbiddenKeys([self._activation_hotkey_btn.hotkey()])
        
        # Unlock info row
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        info_row.setAlignment(Qt.AlignVCenter)
        info_icon_lbl = QLabel("🔐")
        info_icon_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        info_lbl = QLabel("Click lock screen → Unlock button → Windows lock screen (PIN / Fingerprint / Face)")
        info_lbl.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        info_lbl.setWordWrap(True)
        info_row.addWidget(info_icon_lbl)
        info_row.addWidget(info_lbl, 1)
        controls_layout.addLayout(info_row)
        
        # Lock on app exit checkbox
        self._lock_on_exit_cb = AnimatedCheckBox("Lock workstation when HELXAID exits")
        self._lock_on_exit_cb.setChecked(self._config["lock_screen"]["lock_on_exit"])
        self._lock_on_exit_cb.toggled.connect(self._on_lock_exit_changed)
        controls_layout.addWidget(self._lock_on_exit_cb)
        
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        card.add_content(controls_widget)
        
        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignVCenter)
        
        self._lock_activate_btn = QPushButton("  Activate Lock Screen")
        self._lock_activate_btn.setObjectName("primaryBtn")
        self._lock_activate_btn.setFixedHeight(40)
        # Set lock icon on button
        lock_btn_icon_path = os.path.join(script_dir, "UI Reguler", "lock.png")
        if os.path.exists(lock_btn_icon_path):
            self._lock_activate_btn.setIcon(QIcon(lock_btn_icon_path))
            self._lock_activate_btn.setIconSize(QSize(18, 18))
        self._lock_activate_btn.clicked.connect(self._activate_lock_screen)
        btn_row.addWidget(self._lock_activate_btn)
        
        btn_row.addStretch()
        
        btn_widget = QWidget()
        btn_widget.setLayout(btn_row)
        card.add_content(btn_widget)
        
        # Hotkey info with icon
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(6)
        hotkey_row.setAlignment(Qt.AlignVCenter)
        tips_icon_path = os.path.join(script_dir, "UI Reguler", "tips.png")
        if os.path.exists(tips_icon_path):
            tips_icon = QLabel()
            tips_pix = QPixmap(tips_icon_path).scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            tips_icon.setPixmap(tips_pix)
            tips_icon.setFixedSize(14, 14)
            tips_icon.setStyleSheet("background: transparent;")
            hotkey_row.addWidget(tips_icon)
        unlock_key = self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L")
        self._hotkey_info = QLabel(f"Press {unlock_key} to unlock → Windows Lock Screen will appear")
        self._hotkey_info.setStyleSheet("color: #aaa; font-size: 11px;")
        hotkey_row.addWidget(self._hotkey_info)
        hotkey_row.addStretch()
        hotkey_widget = QWidget()
        hotkey_widget.setLayout(hotkey_row)
        card.add_content(hotkey_widget)
        
        parent_layout.addWidget(card)

    
    def _setup_windows_update_card(self, parent_layout):
        """Setup the Windows Update control card."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        update_icon = os.path.join(script_dir, "UI Reguler", "windowsIcon.png")
        
        card = FeatureCard(
            title="Windows Update Control",
            description="Manage Windows Update behavior — pause updates, disable auto-restart, set active hours.",
            icon_path=update_icon
        )
        
        # Admin status
        is_admin = WindowsUpdateControl.is_admin()
        admin_status = QLabel("● Running as Administrator" if is_admin else "● Some features require Administrator")
        admin_status.setStyleSheet(
            "color: #4CAF50; font-size: 11px;" if is_admin else "color: #FFA726; font-size: 11px;"
        )
        card.add_content(admin_status)
        
        # Current status
        paused, pause_info = WindowsUpdateControl.get_update_status()
        self._update_status = QLabel(f"● Updates paused until {pause_info}" if paused else "● Updates active")
        self._update_status.setStyleSheet(
            f"color: {'#FFA726' if paused else '#4CAF50'}; font-size: 12px; font-weight: 500;"
        )
        card.add_content(self._update_status)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(255, 255, 255, 0.05); max-height: 1px; border: none;")
        card.add_content(sep)
        
        # Controls container
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 8, 0, 0)
        controls_layout.setSpacing(14)
        
        # --- Pause Updates Section ---
        pause_lbl = QLabel("Pause until:")
        pause_lbl.setStyleSheet("font-size: 12px;")
        controls_layout.addWidget(pause_lbl)
        
        pause_date_row = QHBoxLayout()
        pause_date_row.setSpacing(6)
        pause_date_row.setAlignment(Qt.AlignVCenter)
        
        from datetime import datetime as _dt
        _now = _dt.now()
        saved_date = self._config["windows_update"].get("pause_until_date", "")
        
        # Shared inline style for date input boxes (overrides global launcher stylesheet)
        _input_style = """
            QLineEdit {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 5px;
                padding: 6px 8px;
                font-size: 12px;
                margin: 0px;
            }
            QLineEdit:focus {
                background: #32353e;
                border: 1px solid rgba(255, 91, 6, 0.6);
            }
        """
        
        # Day input
        self._pause_day = QLineEdit()
        self._pause_day.setPlaceholderText("DD")
        self._pause_day.setFixedWidth(48)
        self._pause_day.setFixedHeight(36)
        self._pause_day.setMaxLength(2)
        self._pause_day.setStyleSheet(_input_style)
        
        sep1 = QLabel("/")
        sep1.setStyleSheet("color: #888; font-size: 14px; margin: 0px; background: transparent;")
        sep1.setFixedWidth(10)
        sep1.setFixedHeight(36)
        sep1.setAlignment(Qt.AlignCenter)
        
        # Month input
        self._pause_month = QLineEdit()
        self._pause_month.setPlaceholderText("MM")
        self._pause_month.setFixedWidth(48)
        self._pause_month.setFixedHeight(36)
        self._pause_month.setMaxLength(2)
        self._pause_month.setStyleSheet(_input_style)
        
        sep2 = QLabel("/")
        sep2.setStyleSheet("color: #888; font-size: 14px; margin: 0px; background: transparent;")
        sep2.setFixedWidth(10)
        sep2.setFixedHeight(36)
        sep2.setAlignment(Qt.AlignCenter)
        
        # Year input
        self._pause_year = QLineEdit()
        self._pause_year.setPlaceholderText("YYYY")
        self._pause_year.setFixedWidth(64)
        self._pause_year.setFixedHeight(36)
        self._pause_year.setMaxLength(4)
        self._pause_year.setStyleSheet(_input_style)
        
        # Populate from saved config or leave blank
        if saved_date:
            try:
                _saved = _dt.strptime(saved_date, "%d/%m/%Y")
                self._pause_day.setText(f"{_saved.day:02d}")
                self._pause_month.setText(f"{_saved.month:02d}")
                self._pause_year.setText(str(_saved.year))
            except ValueError:
                pass
        
        # --- Per-widget button style (MacroSettingsPanel pattern) ---
        _btn_style = """
            QPushButton {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 500;
                margin: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.2);
                color: white;
            }
            QPushButton:pressed {
                background: rgba(255, 91, 6, 0.4);
            }
        """
        _primary_btn_style = """
            QPushButton {
                background: #FF5B06;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                margin: 0px;
            }
            QPushButton:hover {
                background: #ff7b36;
            }
            QPushButton:pressed {
                background: #cc4905;
            }
        """
        
        # Store styles and icons for toggling
        self._wu_primary_btn_style = _primary_btn_style
        self._wu_secondary_btn_style = _btn_style
        self._wu_pause_icon_path = os.path.join(script_dir, "UI Reguler", "pauseRegular.png")
        self._wu_resume_icon_path = os.path.join(script_dir, "UI Reguler", "loopRegular.png")
        
        self._toggle_update_btn = QPushButton()
        self._toggle_update_btn.setFixedHeight(36)
        self._toggle_update_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_update_btn.clicked.connect(self._on_toggle_update_clicked)
        
        self._update_toggle_button_ui(paused)
        
        pause_date_row.setContentsMargins(0, 0, 0, 0)
        pause_date_row.addWidget(self._pause_day, 0, Qt.AlignVCenter)
        pause_date_row.addWidget(sep1, 0, Qt.AlignVCenter)
        pause_date_row.addWidget(self._pause_month, 0, Qt.AlignVCenter)
        pause_date_row.addWidget(sep2, 0, Qt.AlignVCenter)
        pause_date_row.addWidget(self._pause_year, 0, Qt.AlignVCenter)
        pause_date_row.addSpacing(10)
        pause_date_row.addWidget(self._toggle_update_btn, 0, Qt.AlignVCenter)
        pause_date_row.addStretch()
        controls_layout.addLayout(pause_date_row)
        
        # --- Disable Auto-Restart ---
        self._no_restart_cb = AnimatedCheckBox("Disable automatic restart after updates")
        self._no_restart_cb.setChecked(self._config["windows_update"]["disable_auto_restart"])
        self._no_restart_cb.toggled.connect(self._on_auto_restart_changed)
        controls_layout.addWidget(self._no_restart_cb)
        
        # --- Active Hours ---
        hours_row = QHBoxLayout()
        hours_row.setSpacing(10)
        hours_row.setAlignment(Qt.AlignVCenter)
        
        hours_lbl = QLabel("Active hours:")
        hours_lbl.setFixedWidth(110)
        hours_lbl.setFixedHeight(36)
        hours_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hours_lbl.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        # Shared inline style for hour combo boxes (overrides global launcher stylesheet)
        _combo_style = """
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QComboBox:focus {
                background: #32353e;
                border: 1px solid rgba(255, 91, 6, 0.6);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border-left: none;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                background: rgba(255, 91, 6, 0.25);
            }
            QComboBox QAbstractItemView {
                background: #1e2028;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }
        """
        
        self._hours_preset_combo = QComboBox()
        self._hours_preset_combo.addItems(["Always Active", "8 Hours", "12 Hours", "18 Hours", "Customize"])
        # Set default selection from config
        saved_preset = self._config["windows_update"].get("active_hours_preset", "Customize")
        preset_idx = self._hours_preset_combo.findText(saved_preset)
        if preset_idx >= 0:
            self._hours_preset_combo.setCurrentIndex(preset_idx)
        else:
            self._hours_preset_combo.setCurrentIndex(4)  # Default to Customize
        self._hours_preset_combo.setFixedWidth(140)
        self._hours_preset_combo.setFixedHeight(36)
        self._hours_preset_combo.setStyleSheet(_combo_style)
        self._hours_preset_combo.currentIndexChanged.connect(self._on_hours_preset_changed)
        
        # Custom duration container widget
        self._custom_hours_widget = QWidget()
        self._custom_hours_widget.setFixedHeight(36)
        self._custom_hours_widget.setStyleSheet("background: transparent; margin: 0px;")
        custom_layout = QHBoxLayout(self._custom_hours_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(10)
        custom_layout.setAlignment(Qt.AlignVCenter)
        
        self._hours_start = QComboBox()
        self._hours_start.addItems([f"{i:02d}:00" for i in range(24)])
        self._hours_start.setCurrentIndex(self._config["windows_update"]["active_hours_start"])
        self._hours_start.setFixedWidth(90)
        self._hours_start.setFixedHeight(36)
        self._hours_start.setStyleSheet(_combo_style)
        
        hours_to = QLabel("to")
        hours_to.setFixedHeight(36)
        hours_to.setAlignment(Qt.AlignCenter)
        hours_to.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        self._hours_end = QComboBox()
        self._hours_end.addItems([f"{i:02d}:00" for i in range(24)])
        self._hours_end.setCurrentIndex(self._config["windows_update"]["active_hours_end"])
        self._hours_end.setFixedWidth(90)
        self._hours_end.setFixedHeight(36)
        self._hours_end.setStyleSheet(_combo_style)
        
        custom_layout.addWidget(self._hours_start, 0, Qt.AlignVCenter)
        custom_layout.addWidget(hours_to, 0, Qt.AlignVCenter)
        custom_layout.addWidget(self._hours_end, 0, Qt.AlignVCenter)
        
        self._apply_hours_btn = QPushButton("Apply")
        self._apply_hours_btn.setObjectName("primaryBtn")
        self._apply_hours_btn.setFixedHeight(36)
        self._apply_hours_btn.setFixedWidth(90)
        self._apply_hours_btn.setStyleSheet(_primary_btn_style)
        self._apply_hours_btn.setCursor(Qt.PointingHandCursor)
        self._apply_hours_btn.clicked.connect(self._apply_active_hours)
        
        hours_row.setContentsMargins(0, 0, 0, 0)
        hours_row.addWidget(hours_lbl, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._hours_preset_combo, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._custom_hours_widget, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._apply_hours_btn, 0, Qt.AlignVCenter)
        hours_row.addStretch()
        controls_layout.addLayout(hours_row)
        
        # Hide custom duration selectors if not Customize
        self._custom_hours_widget.setVisible(self._hours_preset_combo.currentText() == "Customize")
        
        
        card.add_content(controls)
        
        # Info note with icon
        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        info_row.setAlignment(Qt.AlignVCenter)
        tips_icon_path = os.path.join(script_dir, "UI Reguler", "tips.png")
        if os.path.exists(tips_icon_path):
            tips_icon2 = QLabel()
            tips_pix2 = QPixmap(tips_icon_path).scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            tips_icon2.setPixmap(tips_pix2)
            tips_icon2.setFixedSize(14, 14)
            tips_icon2.setStyleSheet("background: transparent;")
            info_row.addWidget(tips_icon2)
        info_note = QLabel("Pause & active hours changes take effect immediately. Some options require admin privileges.")
        info_note.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        info_note.setWordWrap(True)
        info_row.addWidget(info_note, 1)
        info_widget = QWidget()
        info_widget.setLayout(info_row)
        card.add_content(info_widget)
        
        parent_layout.addWidget(card)

    
    # ============================================
    # EVENT HANDLERS
    # ============================================
    
    def _on_opacity_changed(self, value):
        """Handle opacity slider change."""
        self._opacity_value.setText(f"{value}%")
        self._config["lock_screen"]["opacity"] = value
        self._save_config()
    
    def _on_lock_exit_changed(self, state):
        """Handle lock-on-exit checkbox."""
        self._config["lock_screen"]["lock_on_exit"] = bool(state)
        self._save_config()
    
    def _show_lock_overlay(self):
        """Show the 'Screen is Locked' overlay panel."""
        # Close any existing overlay and reset the click guard
        if hasattr(self, "_lock_overlay") and self._lock_overlay is not None:
            try:
                self._lock_overlay.close()
            except Exception:
                pass
        InvisibleLockScreen._overlay_shown = False

        self._lock_overlay = LockScreenOverlay(self.window())
        self._lock_overlay.show()

    
    def _activate_lock_screen(self):
        """Activate the invisible lock screen."""
        if InvisibleLockScreen.is_active():
            return
        
        opacity = self._config["lock_screen"]["opacity"]
        unlock_hotkey = self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L")
        InvisibleLockScreen.activate(opacity, unlock_hotkey)
        
        self._lock_status.setText("● Active")
        self._lock_status.setStyleSheet("color: #FF5B06; font-size: 12px; font-weight: 500;")
        self._lock_activate_btn.setText("  Lock Screen Active...")
        self._lock_activate_btn.setEnabled(False)
        
        # Poll for deactivation
        self._lock_poll_timer = QTimer(self)
        self._lock_poll_timer.setInterval(500)
        self._lock_poll_timer.timeout.connect(self._check_lock_status)
        self._lock_poll_timer.start()
    
    def _check_lock_status(self):
        """Check if lock screen is still active."""
        if not InvisibleLockScreen.is_active():
            self._lock_poll_timer.stop()
            self._lock_status.setText("● Inactive")
            self._lock_status.setStyleSheet("color: #888888; font-size: 12px; font-weight: 500;")
            self._lock_activate_btn.setText("  Activate Lock Screen")
            self._lock_activate_btn.setEnabled(True)
    
    def _update_toggle_button_ui(self, is_paused):
        """Update the toggle button appearance based on paused state."""
        if is_paused:
            self._toggle_update_btn.setText("  Resume Updates")
            self._toggle_update_btn.setStyleSheet(self._wu_secondary_btn_style)
            self._toggle_update_btn.setObjectName("")  # Remove primaryBtn styling if any
            if hasattr(self, '_wu_resume_icon_path') and os.path.exists(self._wu_resume_icon_path):
                self._toggle_update_btn.setIcon(QIcon(self._wu_resume_icon_path))
                self._toggle_update_btn.setIconSize(QSize(16, 16))
        else:
            self._toggle_update_btn.setText("  Pause Updates")
            self._toggle_update_btn.setStyleSheet(self._wu_primary_btn_style)
            self._toggle_update_btn.setObjectName("primaryBtn")
            if hasattr(self, '_wu_pause_icon_path') and os.path.exists(self._wu_pause_icon_path):
                self._toggle_update_btn.setIcon(QIcon(self._wu_pause_icon_path))
                self._toggle_update_btn.setIconSize(QSize(16, 16))
                
    def _on_toggle_update_clicked(self):
        """Handle the toggle button click."""
        is_paused = self._config["windows_update"].get("pause_updates", False)
        if is_paused:
            self._resume_updates()
        else:
            self._pause_updates()
            
    def _pause_updates(self):
        """Pause Windows Updates until a specific date (DD/MM/YYYY)."""
        try:
            day_str = self._pause_day.text().strip()
            month_str = self._pause_month.text().strip()
            year_str = self._pause_year.text().strip()
            
            if not day_str or not month_str or not year_str:
                raise ValueError("All date fields (DD, MM, YYYY) must be filled.")
                
            day = int(day_str)
            month = int(month_str)
            year = int(year_str)
            
            from datetime import datetime
            # Set time to 23:59:59 so updates are paused through the end of that day
            target_date = datetime(year, month, day, 23, 59, 59)
            
            if target_date <= datetime.now():
                raise ValueError("Date must be in the future.")
        except ValueError as e:
            err_msg = str(e)
            if "invalid literal for int()" in err_msg:
                err_msg = "Please enter valid numbers for DD, MM, and YYYY."
            self._update_status.setText(f"● Error: {err_msg}")
            self._update_status.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 500;")
            return
            
        success, msg = WindowsUpdateControl.pause_updates(target_date)
        
        if success:
            self._update_status.setText(f"● {msg}")
            self._update_status.setStyleSheet("color: #FFA726; font-size: 12px; font-weight: 500;")
            self._config["windows_update"]["pause_updates"] = True
            self._config["windows_update"]["pause_until_date"] = target_date.strftime("%d/%m/%Y")
            self._update_toggle_button_ui(True)
        else:
            self._update_status.setText(f"● Error: {msg}")
            self._update_status.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 500;")
        
        self._save_config()
    
    def _resume_updates(self):
        """Resume Windows Updates."""
        success, msg = WindowsUpdateControl.resume_updates()
        
        if success:
            self._update_status.setText("● Updates active")
            self._update_status.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: 500;")
            self._config["windows_update"]["pause_updates"] = False
            self._update_toggle_button_ui(False)
        else:
            self._update_status.setText(f"● Error: {msg}")
            self._update_status.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 500;")
        
        self._save_config()
    
    def _on_auto_restart_changed(self, state):
        """Handle auto-restart checkbox."""
        if state:
            success, msg = WindowsUpdateControl.disable_auto_restart()
        else:
            success, msg = WindowsUpdateControl.enable_auto_restart()
        
        self._config["windows_update"]["disable_auto_restart"] = bool(state)
        self._save_config()
    
    def _on_hours_preset_changed(self, index):
        """Handle active hours preset changes."""
        preset = self._hours_preset_combo.currentText()
        self._custom_hours_widget.setVisible(preset == "Customize")
        
    def _apply_active_hours(self):
        """Apply active hours setting based on preset or custom values."""
        preset = self._hours_preset_combo.currentText()
        
        if preset == "Always Active":
            start = 0
            end = 18
        elif preset == "8 Hours":
            start = 8
            end = 16
        elif preset == "12 Hours":
            start = 8
            end = 20
        elif preset == "18 Hours":
            start = 6
            end = 0
        else:  # Customize
            start = self._hours_start.currentIndex()
            end = self._hours_end.currentIndex()
            
        success, msg = WindowsUpdateControl.set_active_hours(start, end)
        
        self._config["windows_update"]["active_hours_preset"] = preset
        self._config["windows_update"]["active_hours_start"] = start
        self._config["windows_update"]["active_hours_end"] = end
        self._save_config()
    
    
    # ============================================
    # PERSISTENCE
    # ============================================
    
    def _save_config(self):
        """Save current config to disk."""
        _save_helrcus_config(self._config)
    
    def _load_state(self):
        """Load and apply saved state on startup."""
        # Check if lock screen is somehow still active
        if InvisibleLockScreen.is_active():
            self._lock_status.setText("● Active")
            self._lock_status.setStyleSheet("color: #FF5B06; font-size: 12px; font-weight: 500;")

    def _register_global_hotkey(self):
        """Register the global activation hotkey."""
        self._unregister_global_hotkey()
        
        hotkey_str = self._config["lock_screen"].get("hotkey", "Ctrl+Alt+L")
        modifiers, vk_code = _parse_hotkey_string(hotkey_str)
        
        if modifiers is not None and vk_code is not None:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            self._activation_hotkey_id = 54321
            success = user32.RegisterHotKey(hwnd, self._activation_hotkey_id, modifiers, vk_code)
            if not success:
                print(f"[HELRCUS] Failed to register global activation hotkey: {hotkey_str}")
            else:
                print(f"[HELRCUS] Registered global activation hotkey: {hotkey_str}")

    def _unregister_global_hotkey(self):
        """Unregister the global activation hotkey."""
        if hasattr(self, "_activation_hotkey_id"):
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.UnregisterHotKey(hwnd, self._activation_hotkey_id)

    def _on_activation_hotkey_changed(self, value):
        """Handle activation hotkey change."""
        self._config["lock_screen"]["hotkey"] = value
        self._save_config()
        self._register_global_hotkey()
        if hasattr(self, '_unlock_hotkey_btn'):
            self._unlock_hotkey_btn.setForbiddenKeys([value])

    def _on_unlock_hotkey_changed(self, value):
        """Handle unlock hotkey change."""
        self._config["lock_screen"]["unlock_hotkey"] = value
        self._save_config()
        if hasattr(self, '_activation_hotkey_btn'):
            self._activation_hotkey_btn.setForbiddenKeys([value])
        if hasattr(self, '_hotkey_info'):
            self._hotkey_info.setText(f"Press {value} to unlock → Windows Lock Screen will appear")

    def nativeEvent(self, eventType, message):
        """Handle native Windows events for global hotkeys."""
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:  # WM_HOTKEY
                if hasattr(self, "_activation_hotkey_id") and msg.wParam == self._activation_hotkey_id:
                    self._activate_lock_screen()
                    return True, 0
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        """Clean up hotkeys when window is closed."""
        self._unregister_global_hotkey()
        super().closeEvent(event)
