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
from datetime import timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QGroupBox, QCheckBox, QSpinBox,
    QComboBox, QSlider, QLineEdit, QFormLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QApplication, QDialog
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import Qt, Signal, QTimer, QSize, Slot, QObject, QPropertyAnimation, QEasingCurve, QPoint, QAbstractNativeEventFilter
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QLinearGradient, QTransform
from AnimatedButton import AnimatedButton, AnimatedCheckBox, HoverCloseButton, FadeHoverButton

# Paths
if hasattr(sys, '_MEIPASS'):
    SCRIPT_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
script_dir = SCRIPT_DIR
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
HELRCUS_CONFIG_PATH = os.path.join(APPDATA_DIR, "helrcus_settings.json")

_PIXMAP_CACHE = {}

def get_cached_pixmap(path: str, width: int = None, height: int = None) -> QPixmap:
    """Retrieve or cache a scaled QPixmap to prevent duplicate memory allocations."""
    if not path or not os.path.exists(path):
        return QPixmap()
    
    key = (path, width, height)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    
    pixmap = QPixmap(path)
    if width and height and not pixmap.isNull():
        pixmap = pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


class TimeMaskLineEdit(QLineEdit):
    """Custom QLineEdit implementing segmented HH:MM time masking with auto-skip and indestructible ':' separator."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeMaskLineEdit")
        self.setText("00:00")
        self.setMaxLength(5)
        self.setAlignment(Qt.AlignCenter)
        
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, lambda: self.setSelection(0, 2))
        
    def mousePressEvent(self, event):
        had_focus = self.hasFocus()
        super().mousePressEvent(event)
        if not had_focus:
            QTimer.singleShot(0, lambda: self.setSelection(0, 2))

    def keyPressEvent(self, event):
        key = event.key()
        text = self.text()
        
        if len(text) != 5 or (len(text) >= 3 and text[2] != ':'):
            text = "00:00"
            self.setText(text)
            
        cursor_pos = self.cursorPosition()
        has_sel = self.hasSelectedText()
        sel_start = self.selectionStart()
        sel_len = len(self.selectedText())
        
        # If user selected all text (0..5) and types a digit
        if has_sel and sel_start == 0 and sel_len >= 4:
            if Qt.Key_0 <= key <= Qt.Key_9:
                digit = chr(key)
                if int(digit) >= 3:
                    self.setText(f"0{digit}:00")
                    self.setSelection(3, 2)
                else:
                    self.setText(f"{digit}0:00")
                    self.setCursorPosition(1)
                return
            elif key in (Qt.Key_Colon, Qt.Key_Semicolon):
                self.setSelection(3, 2)
                return
            elif key in (Qt.Key_Backspace, Qt.Key_Delete):
                self.setText("00:00")
                self.setSelection(0, 2)
                return

        # If user selected hour segment (0..2)
        if has_sel and sel_start == 0 and sel_len == 2:
            if Qt.Key_0 <= key <= Qt.Key_9:
                digit = chr(key)
                min_part = text[3:5] if len(text) >= 5 else "00"
                if int(digit) >= 3:
                    self.setText(f"0{digit}:{min_part}")
                    self.setSelection(3, 2)
                else:
                    self.setText(f"{digit}0:{min_part}")
                    self.setCursorPosition(1)
                return

        # If user selected minute segment (3..5)
        if has_sel and sel_start >= 3:
            if Qt.Key_0 <= key <= Qt.Key_9:
                digit = chr(key)
                hr_part = text[0:2] if len(text) >= 2 else "00"
                self.setText(f"{hr_part}:{digit}0")
                self.setCursorPosition(4)
                return

        # Digit key typing at cursor position
        if Qt.Key_0 <= key <= Qt.Key_9:
            digit = chr(key)
            chars = list(text if len(text) == 5 else "00:00")
            
            if cursor_pos == 2:
                cursor_pos = 3
                
            if cursor_pos < 2:
                chars[cursor_pos] = digit
                new_pos = cursor_pos + 1
                if new_pos == 2:  # Skip over ':'
                    new_pos = 3
            elif cursor_pos >= 3 and cursor_pos < 5:
                chars[cursor_pos] = digit
                new_pos = min(5, cursor_pos + 1)
            else:
                new_pos = 5
                
            new_text = "".join(chars)
            self.setText(new_text)
            self.setCursorPosition(new_pos)
            return

        # Colon, Semicolon, or Right Arrow: Jump to Minute section
        if key in (Qt.Key_Colon, Qt.Key_Semicolon) or (key == Qt.Key_Right and cursor_pos == 2):
            self.setSelection(3, 2)
            return
            
        # Left Arrow at ':' position: Jump back to Hour section
        if key == Qt.Key_Left and cursor_pos == 3:
            self.setSelection(0, 2)
            return

        # Backspace
        if key == Qt.Key_Backspace:
            if cursor_pos == 3:  # Just after ':'
                self.setSelection(0, 2)
                return
            elif cursor_pos > 0:
                target_pos = cursor_pos - 1
                if target_pos == 2:
                    target_pos = 1
                chars = list(text if len(text) == 5 else "00:00")
                chars[target_pos] = '0'
                self.setText("".join(chars))
                self.setCursorPosition(target_pos)
                return

        super().keyPressEvent(event)


def _load_helrcus_config():
    """Load HELRCUS settings from disk."""
    defaults = {
        "lock_screen": {
            "enabled": False,
            "hotkey": "Ctrl+Alt+L",
            "unlock_hotkey": "Ctrl+Shift+L",
            "opacity": 1,
            "auto_lock_minutes": 0,
            "lock_on_exit": False,
            "pin_hash": ""
        },
        "windows_update": {
            "pause_updates": False,
            "pause_years": 1,
            "pause_until_date": "",
            "disable_auto_restart": False,
            "active_hours_preset": "Always Active (Max 18h)",
            "active_hours_start": 0,
            "active_hours_end": 18,
            "metered_connection": False
        },
        "module_settings": {
            "init_at_main_initialize": True,
            "startup_hotkeys": True,
            "keep_in_memory": True
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


class HelrcusGlobalHotkeyEventFilter(QAbstractNativeEventFilter):
    """
    Application-wide native event filter for HELRCUS Global Activation Hotkey.
    Catches WM_HOTKEY (0x0312) messages across any window/thread state
    and routes them directly to WindowsCustomPanel._activate_lock_screen().
    
    Component Name: HelrcusGlobalHotkeyEventFilter
    """
    def __init__(self, panel):
        super().__init__()
        import weakref
        self._panel_ref = weakref.ref(panel)

    def nativeEventFilter(self, eventType, message):
        try:
            msg_ptr = int(message)
            msg = ctypes.wintypes.MSG.from_address(msg_ptr)
            if msg.message == 0x0312:  # WM_HOTKEY
                panel = self._panel_ref()
                if panel is not None and hasattr(panel, "_activation_hotkey_id"):
                    if msg.wParam == panel._activation_hotkey_id:
                        print(f"[HELRCUS] Caught global activation hotkey (id={panel._activation_hotkey_id}) in nativeEventFilter!", flush=True)
                        QTimer.singleShot(0, panel._activate_lock_screen)
                        return True, 0
        except Exception:
            pass
        return False, 0


class HotkeyRecordButton(QPushButton):
    """
    A button that records a hotkey when clicked.
    Click to start recording, press modifiers and letter, it captures it.
    Equipped with Win32 WH_KEYBOARD_LL low-level hook & real-time visual chord feedback.
    
    Component Name: HotkeyRecordButton
    """
    
    hotkeyChanged = Signal(str)
    recordingStarted = Signal()
    recordingStopped = Signal()
    _preview_changed = Signal(str)
    _commit_signal = Signal(str)
    _prompt_signal = Signal(str)
    _cancel_signal = Signal()
    
    def __init__(self, default_key: str = "Ctrl+Alt+L", parent=None, min_keys=3, forbidden_keys=None):
        super().__init__(parent)
        self.setObjectName("helrcusActivationHotkeyBtn")
        self._recording = False
        self._hook = None
        self._hook_proc_ref = None
        self._prompt_timer = None
        self._active_held_keys = []
        self._min_keys = min_keys
        self._forbidden_keys = forbidden_keys or []
        self._hotkey = default_key
        self.setText(default_key.upper())
        self.setFixedWidth(160)
        self.setFixedHeight(32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to record a new activation hotkey")
        self.clicked.connect(self._start_recording)

        self._preview_changed.connect(self._on_preview_changed, Qt.QueuedConnection)
        self._commit_signal.connect(self._validate_and_commit, Qt.QueuedConnection)
        self._prompt_signal.connect(self._show_prompt, Qt.QueuedConnection)
        self._cancel_signal.connect(self._cancel_recording, Qt.QueuedConnection)

        self._update_style()
        
    def setForbiddenKeys(self, keys: list):
        self._forbidden_keys = keys
        
    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 91, 6, 0.9);
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #e0e0e0;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 91, 6, 0.35);
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: rgba(255, 91, 6, 0.6);
                }
            """)

    @Slot(str)
    def _on_preview_changed(self, text: str):
        if self._recording:
            self.setText(text.upper())

    def _install_hook(self):
        if self._hook is not None:
            return
        try:
            from ctypes import wintypes
            self._user32_dll = ctypes.WinDLL("user32", use_last_error=True)
            
            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_ulonglong)
                ]
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))
            
            self._user32_dll.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            self._user32_dll.SetWindowsHookExW.restype = wintypes.HHOOK
            self._user32_dll.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            self._user32_dll.UnhookWindowsHookEx.restype = wintypes.BOOL
            self._user32_dll.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)]
            self._user32_dll.CallNextHookEx.restype = ctypes.c_longlong
            self._user32_dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self._user32_dll.GetAsyncKeyState.restype = ctypes.c_short
            self._user32_dll.GetKeyState.argtypes = [ctypes.c_int]
            self._user32_dll.GetKeyState.restype = ctypes.c_short

            def _low_level_kb_proc(nCode, wParam, lParam):
                if nCode >= 0 and self._recording:
                    vk = lParam.contents.vkCode
                    flags = lParam.contents.flags

                    # Win Key swallowed
                    if vk in (0x5B, 0x5C):
                        if wParam in (0x0100, 0x0104):
                            try:
                                self._user32_dll.keybd_event(0xE8, 0, 0, 0)
                                self._user32_dll.keybd_event(0xE8, 0, 2, 0)
                            except Exception:
                                pass
                            self._prompt_signal.emit("No Win Key!")
                        return 1

                    # Escape cancels recording
                    if vk == 0x1B:
                        if wParam in (0x0100, 0x0104):
                            self._cancel_signal.emit()
                        return 1

                    # Real-time modifier tracking
                    MODIFIER_KEYS = {
                        0x11: "Ctrl", 0xA2: "Ctrl", 0xA3: "Ctrl",
                        0x12: "Alt", 0xA4: "Alt", 0xA5: "Alt",
                        0x10: "Shift", 0xA0: "Shift", 0xA1: "Shift",
                    }
                    if vk in MODIFIER_KEYS:
                        mod_name = MODIFIER_KEYS[vk]
                        if wParam in (0x0100, 0x0104):  # Key down
                            if mod_name not in self._active_held_keys:
                                self._active_held_keys.append(mod_name)
                            preview = " + ".join(self._active_held_keys) + " + ..."
                            self._preview_changed.emit(preview)
                        elif wParam in (0x0101, 0x0105):  # Key up
                            if mod_name in self._active_held_keys:
                                self._active_held_keys.remove(mod_name)
                            if self._active_held_keys:
                                preview = " + ".join(self._active_held_keys) + " + ..."
                                self._preview_changed.emit(preview)
                            else:
                                self._preview_changed.emit("Press key...")
                        return 1

                    # Non-modifier key handling on key down
                    if wParam in (0x0100, 0x0104):
                        # F1-F24 restricted
                        if 0x70 <= vk <= 0x87:
                            self._prompt_signal.emit("No F1-F12 Keys!")
                            return 1

                        # Numbers / Numpad restricted
                        if (0x30 <= vk <= 0x39) or (0x60 <= vk <= 0x69):
                            self._prompt_signal.emit("No Numbers!")
                            return 1

                        # Enter, Backspace, Delete restricted
                        if vk in (0x0D, 0x08, 0x2E):
                            self._prompt_signal.emit("No Enter/Del!")
                            return 1

                        # Alphabet A-Z allowed
                        if 0x41 <= vk <= 0x5A:
                            char = chr(vk).upper()
                            detected_mods = set(self._active_held_keys)
                            if flags & 0x20:
                                detected_mods.add("Alt")
                            try:
                                if (self._user32_dll.GetAsyncKeyState(0x11) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA2) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA3) & 0x8000):
                                    detected_mods.add("Ctrl")
                                if (self._user32_dll.GetAsyncKeyState(0x12) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA4) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA5) & 0x8000):
                                    detected_mods.add("Alt")
                                if (self._user32_dll.GetAsyncKeyState(0x10) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA0) & 0x8000) or (self._user32_dll.GetAsyncKeyState(0xA1) & 0x8000):
                                    detected_mods.add("Shift")
                                if (self._user32_dll.GetKeyState(0x11) & 0x8000) or (self._user32_dll.GetKeyState(0xA2) & 0x8000) or (self._user32_dll.GetKeyState(0xA3) & 0x8000):
                                    detected_mods.add("Ctrl")
                                if (self._user32_dll.GetKeyState(0x12) & 0x8000) or (self._user32_dll.GetKeyState(0xA4) & 0x8000) or (self._user32_dll.GetKeyState(0xA5) & 0x8000):
                                    detected_mods.add("Alt")
                                if (self._user32_dll.GetKeyState(0x10) & 0x8000) or (self._user32_dll.GetKeyState(0xA0) & 0x8000) or (self._user32_dll.GetKeyState(0xA1) & 0x8000):
                                    detected_mods.add("Shift")
                            except Exception:
                                pass

                            mods = [m for m in ("Ctrl", "Alt", "Shift") if m in detected_mods]
                            if not mods:
                                self._prompt_signal.emit("Add Ctrl/Alt/Shift!")
                                return 1

                            full_key = "+".join(mods) + "+" + char
                            self._commit_signal.emit(full_key)
                            return 1
                        else:
                            self._prompt_signal.emit("A-Z Letters Only!")
                            return 1

                    elif wParam in (0x0101, 0x0105):
                        return 1

                return self._user32_dll.CallNextHookEx(self._hook, nCode, wParam, lParam)

            self._hook_proc_ref = HOOKPROC(_low_level_kb_proc)
            self._hook = self._user32_dll.SetWindowsHookExW(13, self._hook_proc_ref, None, 0)
        except Exception as e:
            print(f"[HotkeyRecordButton] Hook install error: {e}")
            self._hook = None

    def _remove_hook(self):
        if self._hook is not None:
            try:
                if hasattr(self, '_user32_dll') and self._user32_dll:
                    self._user32_dll.UnhookWindowsHookEx(self._hook)
                else:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
            self._hook_proc_ref = None

    def _start_recording(self):
        if self._recording:
            self._cancel_recording()
            return
        if self._prompt_timer and self._prompt_timer.isActive():
            self._prompt_timer.stop()
        self._active_held_keys = []
        self._recording = True
        self.setText("Press key...")
        self._update_style()
        self.setFocus()
        self.grabKeyboard()
        self._install_hook()
        self.recordingStarted.emit()

    def mousePressEvent(self, event):
        if self._recording:
            self._cancel_recording()
            event.accept()
            return
        super().mousePressEvent(event)

    @Slot()
    def _cancel_recording(self):
        self._remove_hook()
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        if self._prompt_timer and self._prompt_timer.isActive():
            self._prompt_timer.stop()
        self._active_held_keys = []
        self._recording = False
        self.setText(self._hotkey.upper())
        self._update_style()
        self.recordingStopped.emit()

    @Slot(str)
    def _show_prompt(self, text: str, auto_reset_to_key: bool = False):
        if self._prompt_timer and self._prompt_timer.isActive():
            self._prompt_timer.stop()
        self.setText(text)
        self._prompt_timer = QTimer(self)
        self._prompt_timer.setSingleShot(True)
        if auto_reset_to_key or not self._recording:
            self._prompt_timer.timeout.connect(lambda: self.setText(self._hotkey.upper()))
        else:
            self._prompt_timer.timeout.connect(
                lambda: self.setText("Press key...") if self._recording else self.setText(self._hotkey.upper())
            )
        self._prompt_timer.start(1500)

    @Slot(str)
    def _validate_and_commit(self, full_key: str):
        self._remove_hook()
        try:
            self.releaseKeyboard()
        except Exception:
            pass

        self._active_held_keys = []

        # Rule 7: No Windows reserved system shortcuts
        RESERVED_WIN_SHORTCUTS = {
            "CTRL+C", "CTRL+V", "CTRL+X", "CTRL+A", "CTRL+Z", "CTRL+Y",
            "CTRL+S", "CTRL+P", "CTRL+F", "CTRL+W", "CTRL+N", "CTRL+T",
            "CTRL+O", "CTRL+H", "ALT+TAB", "ALT+F4", "ALT+ESC", "ALT+SPACE",
            "CTRL+ALT+DEL", "CTRL+SHIFT+ESC", "CTRL+ESC"
        }
        if full_key.upper() in RESERVED_WIN_SHORTCUTS:
            self._recording = False
            self._update_style()
            self._show_prompt("Reserved Windows!", auto_reset_to_key=True)
            self.recordingStopped.emit()
            return

        # Check forbidden keys (e.g. cross-validation against unlock hotkey)
        if self._forbidden_keys and full_key.upper() in [k.upper() for k in self._forbidden_keys]:
            self._recording = False
            self._update_style()
            self._show_prompt("Already In Use!", auto_reset_to_key=True)
            target_w = self.window() if self.window() else self
            try:
                from MacroSettingsPanel import FloatingToast
                other_name = "Unlock Hotkey" if self.objectName() == "helrcusActivationHotkeyBtn" else "Activation Hotkey"
                FloatingToast.show_toast(
                    target_w,
                    "Shortcut Conflict",
                    f"'{full_key}' is already assigned to {other_name}."
                )
            except Exception:
                pass
            self.recordingStopped.emit()
            return

        # Rule 8: Global Shortcut Conflict Validation across HELXAID
        try:
            from MacroSettingsPanel import validate_shortcut_conflict, FloatingToast
            owner_id = "helrcus_lock" if self.objectName() == "helrcusActivationHotkeyBtn" else "helrcus_unlock"
            is_valid, conflict_owner = validate_shortcut_conflict(full_key, owner_id=owner_id)
            if not is_valid:
                target_w = self.window() if self.window() else self
                FloatingToast.show_toast(
                    target_w,
                    "Shortcut Conflict",
                    f"'{full_key}' is already assigned to {conflict_owner}. Please choose another hotkey."
                )
                self._recording = False
                self._update_style()
                self._show_prompt("Already In Use!", auto_reset_to_key=True)
                self.recordingStopped.emit()
                return
        except Exception as e:
            print(f"[HotkeyRecordButton] Conflict check error: {e}")

        if self._prompt_timer and self._prompt_timer.isActive():
            self._prompt_timer.stop()

        self._hotkey = full_key
        self.setText(full_key.upper())
        self._recording = False
        self._update_style()
        self.recordingStopped.emit()
        self.hotkeyChanged.emit(full_key)
        
    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()
            if key == Qt.Key_Escape:
                self._cancel_recording()
                event.accept()
                return

            if (event.modifiers() & Qt.MetaModifier) or key in (Qt.Key_Meta, Qt.Key_Super_L, Qt.Key_Super_R):
                self._show_prompt("No Win Key!")
                event.accept()
                return

            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt):
                mod_name = "Ctrl" if key == Qt.Key_Control else ("Alt" if key == Qt.Key_Alt else "Shift")
                if mod_name not in self._active_held_keys:
                    self._active_held_keys.append(mod_name)
                preview = " + ".join(self._active_held_keys) + " + ..."
                self._on_preview_changed(preview)
                event.accept()
                return

            if Qt.Key_F1 <= key <= Qt.Key_F24:
                self._show_prompt("No F1-F12 Keys!")
                event.accept()
                return

            if key in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter):
                self._show_prompt("No Enter/Del!")
                event.accept()
                return

            if key in (Qt.Key_NumLock, 0x01000035):
                self._show_prompt("No Num Lock!")
                event.accept()
                return

            if (Qt.Key_0 <= key <= Qt.Key_9) or (event.modifiers() & Qt.KeypadModifier):
                self._show_prompt("No Numbers!")
                event.accept()
                return

            if Qt.Key_A <= key <= Qt.Key_Z:
                char = chr(key).upper()
            elif event.text() and len(event.text()) == 1 and ('a' <= event.text().lower() <= 'z'):
                char = event.text().upper()
            else:
                self._show_prompt("A-Z Letters Only!")
                event.accept()
                return

            detected_mods = set(self._active_held_keys)
            if event.modifiers() & Qt.ControlModifier:
                detected_mods.add("Ctrl")
            if event.modifiers() & Qt.AltModifier:
                detected_mods.add("Alt")
            if event.modifiers() & Qt.ShiftModifier:
                detected_mods.add("Shift")
            try:
                u = ctypes.windll.user32
                if (u.GetAsyncKeyState(0x11) & 0x8000) or (u.GetAsyncKeyState(0xA2) & 0x8000) or (u.GetAsyncKeyState(0xA3) & 0x8000):
                    detected_mods.add("Ctrl")
                if (u.GetAsyncKeyState(0x12) & 0x8000) or (u.GetAsyncKeyState(0xA4) & 0x8000) or (u.GetAsyncKeyState(0xA5) & 0x8000):
                    detected_mods.add("Alt")
                if (u.GetAsyncKeyState(0x10) & 0x8000) or (u.GetAsyncKeyState(0xA0) & 0x8000) or (u.GetAsyncKeyState(0xA1) & 0x8000):
                    detected_mods.add("Shift")
            except Exception:
                pass

            mods = [m for m in ("Ctrl", "Alt", "Shift") if m in detected_mods]
            if not mods:
                self._show_prompt("Add Ctrl/Alt/Shift!")
                event.accept()
                return

            full_key = "+".join(mods) + "+" + char
            self._validate_and_commit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._recording:
            key = event.key()
            if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift):
                mod_name = "Ctrl" if key == Qt.Key_Control else ("Alt" if key == Qt.Key_Alt else "Shift")
                if mod_name in self._active_held_keys:
                    self._active_held_keys.remove(mod_name)
                if self._active_held_keys:
                    self._on_preview_changed(" + ".join(self._active_held_keys) + " + ...")
                else:
                    self._on_preview_changed("Press key...")
                event.accept()
                return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        # Do not cancel recording on focusOutEvent because Alt key triggers temporary focus loss in Windows
        super().focusOutEvent(event)

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
            icon_label.setObjectName("featureCardIcon")
            icon_pixmap = get_cached_pixmap(self._icon_path, 28, 28)
            icon_label.setPixmap(icon_pixmap)
            icon_label.setFixedSize(28, 28)
            icon_label.setStyleSheet("background: transparent;")
            header.addWidget(icon_label)
        
        title_container = QVBoxLayout()
        title_container.setSpacing(2)
        
        self.title_label = QLabel(self._title)
        self.title_label.setObjectName("featureCardTitle")
        self.title_label.setStyleSheet("""
            color: #e0e0e0; 
            font-size: 16px; 
            font-weight: bold; 
            font-family: 'Orbitron';
            background: transparent;
        """)
        title_container.addWidget(self.title_label)
        
        if self._description:
            self.desc_label = QLabel(self._description)
            self.desc_label.setObjectName("featureCardDesc")
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
    hide_password = Signal()

lock_signals = LockScreenSignals()

class LockScreenOverlay(QWidget):
    """Qt Overlay panel that shows 'Screen is Locked' with an Unlock button."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("lockScreenOverlay")
        
        self.setFixedSize(300, 160)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        container = QFrame()
        container.setObjectName("lockScreenContainer")
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
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setAlignment(Qt.AlignCenter)
        
        lock_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "lock-icon.svg")
        if os.path.exists(lock_icon_path):
            lock_icon_label = QLabel()
            lock_icon_label.setObjectName("lockScreenIcon")
            lock_icon_label.setPixmap(get_cached_pixmap(lock_icon_path, 20, 20))
            lock_icon_label.setStyleSheet("border: none; background: transparent;")
            title_row.addWidget(lock_icon_label)
            
        title = QLabel("Screen is Locked")
        title.setObjectName("lockScreenTitle")
        title.setStyleSheet("color: #E0E0E0; font-size: 16px; font-weight: 600; border: none; background: transparent;")
        title_row.addWidget(title)
        vbox.addLayout(title_row)
        
        hint = QLabel("Click Unlock to verify your identity")
        hint.setObjectName("lockScreenHint")
        hint.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        hint.setAlignment(Qt.AlignCenter)
        vbox.addWidget(hint)
        
        # Unlock button
        unlock_btn = QPushButton("Unlock")
        unlock_btn.setObjectName("lockScreenUnlockBtn")
        unlock_btn.setCursor(Qt.PointingHandCursor)
        unlock_btn.setFixedHeight(36)
        unlock_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: #e0e0e0;
                font-size: 13px;
                font-weight: 600;
                border-radius: 10px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.3);
            }
        """)
        unlock_btn.clicked.connect(self._do_unlock)
        vbox.addWidget(unlock_btn)
        
        layout.addWidget(container)
        
        # Center on primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2
        )
        
        # Fade-in animation setup
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
    
    def _do_unlock(self):
        """Unlock via Windows lock screen."""
        self.close()
        InvisibleLockScreen.unlock()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        with InvisibleLockScreen._lock:
            InvisibleLockScreen._overlay_hwnd = int(self.winId())
        if InvisibleLockScreen._hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                user32.SetWindowLongPtrW.restype = ctypes.c_void_p
                user32.SetWindowLongPtrW(ctypes.c_void_p(int(self.winId())), -8, ctypes.c_void_p(InvisibleLockScreen._hwnd))
            except Exception:
                pass
        if not getattr(self, "_fade_started", False):
            self._fade_started = True
            self._opacity_effect.setOpacity(0.0)
            self._fade_anim.start()
        else:
            self._opacity_effect.setOpacity(1.0)
    
    def closeEvent(self, event):
        """Clean up animations and graphics effects before destruction."""
        with InvisibleLockScreen._lock:
            if InvisibleLockScreen._overlay_hwnd == int(self.winId()):
                InvisibleLockScreen._overlay_hwnd = None
        if hasattr(self, "_fade_anim") and self._fade_anim:
            self._fade_anim.stop()
        self.setGraphicsEffect(None)
        super().closeEvent(event)
    
    def focusOutEvent(self, event):
        # Keep lock overlay steady while lock screen is active
        super().focusOutEvent(event)




class HelrcusHotkeyGuidePanel(QFrame):
    """
    In-app Cyberpunk Floating Guide Panel for HELRCUS Hotkey Validation Rules.
    Adheres strictly to HELXAID's signature floating panel design system:
    - Less border, more background-color
    - 100% Orbitron typography
    - SVG iconography (info-icon.svg, close-icon.svg)
    - In-app HoverCloseButton on custom draggable titlebar
    - Dark glassmorphism with QGraphicsDropShadowEffect
    - Structured cyberpunk cards and stealth micro-scrollbar
    - Draggable within parent window bounds
    - Full component names (setObjectName) for every element
    
    Component Name: HelrcusHotkeyGuidePanel
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("HelrcusHotkeyGuidePanel")
        
        self._is_dragging = False
        self._drag_start_pos = QPoint(0, 0)
        
        self.setFixedSize(550, 540)
        
        # Authentic HELXAID Floating Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        
        self.setStyleSheet("""
            QFrame#HelrcusHotkeyGuidePanel {
                background-color: rgba(12, 12, 16, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QWidget#helrcusGuideTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#helrcusGuideTitleLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 1px;
            }
            QScrollArea#helrcusGuideScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#helrcusGuideScrollContent {
                background: transparent;
            }
            QScrollArea#helrcusGuideScrollArea QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0px;
                border: none;
            }
            QScrollArea#helrcusGuideScrollArea QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                min-height: 20px;
                border-radius: 2px;
                border: none;
            }
            QScrollArea#helrcusGuideScrollArea QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QScrollArea#helrcusGuideScrollArea QScrollBar::add-line:vertical, 
            QScrollArea#helrcusGuideScrollArea QScrollBar::sub-line:vertical,
            QScrollArea#helrcusGuideScrollArea QScrollBar::add-page:vertical,
            QScrollArea#helrcusGuideScrollArea QScrollBar::sub-page:vertical {
                height: 0px;
                width: 0px;
                background: transparent;
                border: none;
            }
            QFrame#helrcusGuideSummaryCard {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
            QLabel#helrcusGuideSummaryLabel {
                color: #C2C6D0;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                line-height: 1.5;
            }
            QFrame#helrcusGuideReqCard, QFrame#helrcusGuideForbiddenCard {
                background: rgba(255, 255, 255, 0.025);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 10px;
            }
            QLabel#helrcusGuideCardTitleLabel {
                font-size: 13px;
                font-weight: 800;
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 0.8px;
            }
            QLabel#helrcusGuideItemLabel {
                color: #B8BCC8;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            }
            QWidget#helrcusGuideFooter {
                background: transparent;
                border-top: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)
        
        # 1. Title Bar (Draggable)
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("helrcusGuideTitleBar")
        self.title_bar.setFixedHeight(42)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(14, 0, 14, 0)
        tb_layout.setSpacing(10)
        
        info_icon_path = os.path.join(script_dir, "UI Icons", "info-icon.svg")
        if os.path.exists(info_icon_path):
            icon_lbl = QLabel(self.title_bar)
            icon_lbl.setObjectName("helrcusGuideTitleIcon")
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setScaledContents(True)
            icon_lbl.setPixmap(get_cached_pixmap(info_icon_path, 16, 16))
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            tb_layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)
            
        title_lbl = QLabel("HOTKEY VALIDATION RULES", self.title_bar)
        title_lbl.setObjectName("helrcusGuideTitleLabel")
        tb_layout.addWidget(title_lbl, stretch=1, alignment=Qt.AlignVCenter)
        
        main_vbox.addWidget(self.title_bar)
        
        # 2. Content Area with SmoothScrollArea
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setObjectName("helrcusGuideScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("helrcusGuideScrollContent")
        content_vbox = QVBoxLayout(scroll_content)
        content_vbox.setContentsMargins(16, 12, 16, 10)
        content_vbox.setSpacing(10)
        
        # Summary Header Card
        summary_card = QFrame(scroll_content)
        summary_card.setObjectName("helrcusGuideSummaryCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(4)
        
        summary_lbl = QLabel("Standard validation rules to guarantee custom hotkeys operate reliably without conflicts against Windows OS shortcuts.", summary_card)
        summary_lbl.setObjectName("helrcusGuideSummaryLabel")
        summary_lbl.setWordWrap(True)
        summary_layout.addWidget(summary_lbl)
        content_vbox.addWidget(summary_card)
        
        # Card 1: Key Requirements
        req_card = QFrame(scroll_content)
        req_card.setObjectName("helrcusGuideReqCard")
        req_layout = QVBoxLayout(req_card)
        req_layout.setContentsMargins(14, 10, 14, 10)
        req_layout.setSpacing(6)
        
        req_title = QLabel("KEY REQUIREMENTS", req_card)
        req_title.setObjectName("helrcusGuideCardTitleLabel")
        req_layout.addWidget(req_title)
        
        req_text = (
            "<p style='margin: 0; font-size: 12px; line-height: 1.7;'>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>Modifier Required:</b> <span style='color: #B8BCC8; font-weight: 600;'>Must include </span><b style='color: #FFFFFF; font-weight: 800;'>Ctrl</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Alt</b><span style='color: #B8BCC8; font-weight: 600;'>, or </span><b style='color: #FFFFFF; font-weight: 800;'>Shift</b>.<br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>Alphabet Only:</b> <span style='color: #B8BCC8; font-weight: 600;'>Base key must be a single letter (</span><b style='color: #FFFFFF; font-weight: 800;'>A – Z</b><span style='color: #B8BCC8; font-weight: 600;'>).</span>"
            "</p>"
        )
        req_lbl = QLabel(req_text, req_card)
        req_lbl.setObjectName("helrcusGuideItemLabel")
        req_lbl.setWordWrap(True)
        req_layout.addWidget(req_lbl)
        content_vbox.addWidget(req_card)
        
        # Card 2: Forbidden Keys & Conflicts
        forbid_card = QFrame(scroll_content)
        forbid_card.setObjectName("helrcusGuideForbiddenCard")
        forbid_layout = QVBoxLayout(forbid_card)
        forbid_layout.setContentsMargins(14, 10, 14, 10)
        forbid_layout.setSpacing(6)
        
        forbid_title = QLabel("FORBIDDEN KEYS & CONFLICTS", forbid_card)
        forbid_title.setObjectName("helrcusGuideCardTitleLabel")
        forbid_layout.addWidget(forbid_title)
        
        forbid_text = (
            "<p style='margin: 0; font-size: 12px; line-height: 1.7;'>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>No Windows Key:</b> <span style='color: #B8BCC8; font-weight: 600;'>Win / Meta key is forbidden.</span><br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>No Function Keys:</b> <b style='color: #FFFFFF; font-weight: 800;'>F1 – F12</b> <span style='color: #B8BCC8; font-weight: 600;'>keys are forbidden.</span><br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>No Editing Keys:</b> <span style='color: #B8BCC8; font-weight: 600;'>Editing & Enter keys (</span><b style='color: #FFFFFF; font-weight: 800;'>Backspace</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Delete</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Enter</b><span style='color: #B8BCC8; font-weight: 600;'>) are forbidden.</span><br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>No Numbers / Numpad:</b> <span style='color: #B8BCC8; font-weight: 600;'>Digits (</span><b style='color: #FFFFFF; font-weight: 800;'>0 – 9</b><span style='color: #B8BCC8; font-weight: 600;'>) & Numpad keys are forbidden.</span><br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>No System Reserved:</b> <span style='color: #B8BCC8; font-weight: 600;'>Windows shortcuts (</span><b style='color: #FFFFFF; font-weight: 800;'>Ctrl+C</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Alt+Tab</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Alt+F4</b><span style='color: #B8BCC8; font-weight: 600;'>, </span><b style='color: #FFFFFF; font-weight: 800;'>Ctrl+Alt+Del</b><span style='color: #B8BCC8; font-weight: 600;'>) are forbidden.</span><br>"
            "<span style='color: #8E96A4; font-weight: bold;'>•</span> <b style='color: #FFFFFF; font-weight: 800;'>Conflict Prevention:</b> <span style='color: #B8BCC8; font-weight: 600;'>Activation and Unlock hotkeys cannot be identical.</span>"
            "</p>"
        )
        forbid_lbl = QLabel(forbid_text, forbid_card)
        forbid_lbl.setObjectName("helrcusGuideItemLabel")
        forbid_lbl.setWordWrap(True)
        forbid_layout.addWidget(forbid_lbl)
        content_vbox.addWidget(forbid_card)
        
        self.scroll_area.setWidget(scroll_content)
        main_vbox.addWidget(self.scroll_area, 1)
        
        # 3. Action Footer
        footer_widget = QWidget(self)
        footer_widget.setObjectName("helrcusGuideFooter")
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(16, 10, 16, 12)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()
        
        got_it_btn = FadeHoverButton("GOT IT", is_secondary=False, border_radius=6.0, parent=footer_widget)
        got_it_btn.setObjectName("helrcusGuideGotItBtn")
        got_it_btn.setFixedSize(95, 34)
        got_it_btn.clicked.connect(self.close_panel)
        footer_layout.addWidget(got_it_btn)
        
        main_vbox.addWidget(footer_widget)
        
    def close_panel(self):
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and hasattr(self, "title_bar") and self.title_bar.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                new_pos = QPoint(new_x, new_y)
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)


class HelrcusSettingsFloatingPanel(QFrame):
    """
    In-app Cyberpunk Floating Settings Panel for HELRCUS Module.
    Configures module-level behaviors:
    1. Initialize at Main Initialize (Preload during software startup, default ON)
    2. Register Hotkeys on Startup (Activate Invisible Lock shortcuts at boot, default ON)
    3. Keep in Memory on Tab Switch (Preserve widget tree in memory, default ON)
    4. Reset HELRCUS Settings to Default
    
    Adheres strictly to HELXAID's signature floating panel design system:
    - Less use border, more use background-color
    - 100% Orbitron typography
    - Vector SVG iconography (settings-icon.svg)
    - Dark glassmorphism with QGraphicsDropShadowEffect
    - Smooth draggable header with boundary clamp
    - Complete component names (setObjectName) for every element
    
    Component Name: HelrcusSettingsFloatingPanel
    """
    def __init__(self, panel, parent=None):
        super().__init__(parent or panel)
        self.panel = panel
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("HelrcusSettingsFloatingPanel")
        
        self._is_dragging = False
        self._drag_start_pos = QPoint(0, 0)
        
        self.setFixedSize(540, 390)
        
        # Authentic HELXAID Floating Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        
        script_dir = SCRIPT_DIR
        
        self.setStyleSheet("""
            QFrame#HelrcusSettingsFloatingPanel {
                background-color: rgba(12, 12, 16, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QWidget#helrcusSettingsTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#helrcusSettingsTitleLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 1px;
            }
            QScrollArea#helrcusSettingsScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#helrcusSettingsScrollContent {
                background: transparent;
            }
            QScrollArea#helrcusSettingsScrollArea QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0px;
                border: none;
            }
            QScrollArea#helrcusSettingsScrollArea QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                min-height: 20px;
                border-radius: 2px;
                border: none;
            }
            QScrollArea#helrcusSettingsScrollArea QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QScrollArea#helrcusSettingsScrollArea QScrollBar::add-line:vertical, 
            QScrollArea#helrcusSettingsScrollArea QScrollBar::sub-line:vertical,
            QScrollArea#helrcusSettingsScrollArea QScrollBar::add-page:vertical,
            QScrollArea#helrcusSettingsScrollArea QScrollBar::sub-page:vertical {
                height: 0px;
                width: 0px;
                background: transparent;
                border: none;
            }
            QFrame#helrcusSettingsCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 10px;
            }
            QLabel#helrcusSettingsCardTitleLabel {
                font-size: 12px;
                font-weight: 800;
                color: #FF5B06;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 0.5px;
            }
            QLabel#helrcusSettingsDescLabel {
                color: #888888;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                background: transparent;
                padding-left: 26px;
            }
            QWidget#helrcusSettingsFooter {
                background-color: rgba(6, 6, 8, 0.85);
                border-bottom-left-radius: 13px;
                border-bottom-right-radius: 13px;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)
        
        # 1. Title Bar (Draggable)
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("helrcusSettingsTitleBar")
        self.title_bar.setFixedHeight(42)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(14, 0, 14, 0)
        tb_layout.setSpacing(10)
        
        settings_icon_path = os.path.join(script_dir, "UI Icons", "settings-icon.svg")
        if os.path.exists(settings_icon_path):
            icon_lbl = QLabel(self.title_bar)
            icon_lbl.setObjectName("helrcusSettingsTitleIcon")
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setScaledContents(True)
            icon_lbl.setPixmap(get_cached_pixmap(settings_icon_path, 16, 16))
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            tb_layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)
            
        title_lbl = QLabel("HELRCUS SETTINGS", self.title_bar)
        title_lbl.setObjectName("helrcusSettingsTitleLabel")
        tb_layout.addWidget(title_lbl, stretch=1, alignment=Qt.AlignVCenter)
        
        main_vbox.addWidget(self.title_bar)
        
        # 2. Scroll Area
        scroll_area = SmoothScrollArea(self)
        scroll_area.setObjectName("helrcusSettingsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("helrcusSettingsScrollContent")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)
        
        # Read initial values from panel._config
        cfg = getattr(panel, "_config", {})
        mod_cfg = cfg.get("module_settings", {})
        
        val_init_main = mod_cfg.get("init_at_main_initialize", True)
        val_startup_hotkeys = mod_cfg.get("startup_hotkeys", True)
        val_keep_memory = mod_cfg.get("keep_in_memory", True)
        
        # CARD 1: STARTUP & LIFECYCLE
        card1 = QFrame()
        card1.setObjectName("helrcusSettingsCard")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(14, 12, 14, 14)
        c1_layout.setSpacing(8)
        
        t1_label = QLabel("STARTUP & LIFECYCLE")
        t1_label.setObjectName("helrcusSettingsCardTitleLabel")
        c1_layout.addWidget(t1_label)
        
        # Item 1: Initialize at Main Initialize
        self.init_at_main_cb = AnimatedCheckBox("Initialize at Main Initialize")
        self.init_at_main_cb.setObjectName("helrcusInitAtMainCheckBox")
        self.init_at_main_cb.setChecked(val_init_main)
        c1_layout.addWidget(self.init_at_main_cb)
        
        init_desc = QLabel("Preload HELRCUS during software startup for 0ms instant tab switching")
        init_desc.setObjectName("helrcusSettingsDescLabel")
        init_desc.setWordWrap(True)
        c1_layout.addWidget(init_desc)
        
        c1_layout.addSpacing(4)
        
        # Item 2: Register Hotkeys on Startup
        self.startup_hotkeys_cb = AnimatedCheckBox("Register Hotkeys on Startup")
        self.startup_hotkeys_cb.setObjectName("helrcusStartupHotkeysCheckBox")
        self.startup_hotkeys_cb.setChecked(val_startup_hotkeys)
        c1_layout.addWidget(self.startup_hotkeys_cb)
        
        hotkeys_desc = QLabel("Register Invisible Lock global shortcuts immediately on launcher launch")
        hotkeys_desc.setObjectName("helrcusSettingsDescLabel")
        hotkeys_desc.setWordWrap(True)
        c1_layout.addWidget(hotkeys_desc)
        
        c1_layout.addSpacing(4)
        
        # Item 3: Keep in Memory on Tab Switch
        self.keep_in_memory_cb = AnimatedCheckBox("Keep in Memory on Tab Switch")
        self.keep_in_memory_cb.setObjectName("helrcusKeepInMemoryCheckBox")
        self.keep_in_memory_cb.setChecked(val_keep_memory)
        c1_layout.addWidget(self.keep_in_memory_cb)
        
        memory_desc = QLabel("Preserve widget tree in memory for zero-lag page navigation")
        memory_desc.setObjectName("helrcusSettingsDescLabel")
        memory_desc.setWordWrap(True)
        c1_layout.addWidget(memory_desc)
        
        content_layout.addWidget(card1)
        
        # CARD 2: MAINTENANCE
        card2 = QFrame()
        card2.setObjectName("helrcusSettingsCard")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(14, 12, 14, 14)
        c2_layout.setSpacing(8)
        
        t2_label = QLabel("MAINTENANCE")
        t2_label.setObjectName("helrcusSettingsCardTitleLabel")
        c2_layout.addWidget(t2_label)
        
        # Item 6: Reset Button
        reset_btn = FadeHoverButton("Reset HELRCUS Settings to Default", is_secondary=True, border_radius=6.0)
        reset_btn.setObjectName("helrcusResetDefaultsBtn")
        reset_btn.setFixedHeight(32)
        reset_btn.clicked.connect(self._reset_to_defaults)
        c2_layout.addWidget(reset_btn)
        
        content_layout.addWidget(card2)
        content_layout.addStretch()
        
        scroll_area.setWidget(scroll_content)
        main_vbox.addWidget(scroll_area)
        
        # 3. Footer Bar
        footer_widget = QWidget(self)
        footer_widget.setObjectName("helrcusSettingsFooter")
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(16, 10, 16, 12)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()
        
        ok_btn = FadeHoverButton("OK", is_secondary=False, border_radius=6.0, parent=footer_widget)
        ok_btn.setObjectName("helrcusSettingsOkBtn")
        ok_btn.setFixedSize(85, 34)
        ok_btn.clicked.connect(self.save_and_close)
        footer_layout.addWidget(ok_btn)
        
        cancel_btn = FadeHoverButton("CANCEL", is_secondary=True, border_radius=6.0, parent=footer_widget)
        cancel_btn.setObjectName("helrcusSettingsCancelBtn")
        cancel_btn.setFixedSize(85, 34)
        cancel_btn.clicked.connect(self.close_panel)
        footer_layout.addWidget(cancel_btn)
        
        main_vbox.addWidget(footer_widget)

    def _reset_to_defaults(self):
        """Reset checkboxes to default values (1=ON, 2=ON, 3=ON)."""
        self.init_at_main_cb.setChecked(True)
        self.startup_hotkeys_cb.setChecked(True)
        self.keep_in_memory_cb.setChecked(True)

    def save_and_close(self):
        """Save settings to config and close floating panel."""
        if "module_settings" not in self.panel._config:
            self.panel._config["module_settings"] = {}
        self.panel._config["module_settings"]["init_at_main_initialize"] = self.init_at_main_cb.isChecked()
        self.panel._config["module_settings"]["startup_hotkeys"] = self.startup_hotkeys_cb.isChecked()
        self.panel._config["module_settings"]["keep_in_memory"] = self.keep_in_memory_cb.isChecked()
        
        self.panel._save_config()
        self.close_panel()

    def close_panel(self):
        self.close()
        if hasattr(self.panel, "_settings_panel") and self.panel._settings_panel is self:
            self.panel._settings_panel = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and hasattr(self, "title_bar") and self.title_bar.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                new_pos = QPoint(new_x, new_y)
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)


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
    _overlay_hwnd = None
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
                lock_signals.hide_password.emit()
    
    @classmethod
    def set_visibility(cls, visible, animate=True):
        """Toggle background opacity when password overlay appears/disappears."""
        with cls._lock:
            if not cls._active or not cls._hwnd:
                return
            hwnd_val = cls._hwnd
            opacity_val = cls._current_opacity
            cls._overlay_shown = visible
            
        import ctypes
        user32 = ctypes.windll.user32
        target_alpha = int(255 * (opacity_val / 100)) if visible else 1
        
        if animate:
            def _fade_thread():
                import time
                steps = 10
                delay = 0.02  # 200ms total
                for i in range(1, steps + 1):
                    if not cls._active:
                        break
                    curr_alpha = max(1, min(255, int(target_alpha * (i / steps))))
                    user32.SetLayeredWindowAttributes(hwnd_val, 0, curr_alpha, 2)
                    time.sleep(delay)
            threading.Thread(target=_fade_thread, daemon=True).start()
        else:
            user32.SetLayeredWindowAttributes(hwnd_val, 0, target_alpha, 2)
    
    
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
            
            HWND_TOPMOST = ctypes.c_void_p(-1)

            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND

            user32.IsWindow.argtypes = [wintypes.HWND]
            user32.IsWindow.restype = wintypes.BOOL

            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL

            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL

            user32.GetForegroundWindow.argtypes = []
            user32.GetForegroundWindow.restype = wintypes.HWND

            user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetClassNameW.restype = ctypes.c_int

            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.UINT
            ]
            user32.SetWindowPos.restype = wintypes.BOOL

            def _get_taskmgr_hwnd():
                for cls_name in ("TaskManagerWindow", "TaskmanagerWindow"):
                    hwnd_tm = user32.FindWindowW(cls_name, None)
                    if hwnd_tm and user32.IsWindow(hwnd_tm) and user32.IsWindowVisible(hwnd_tm) and not user32.IsIconic(hwnd_tm):
                        return hwnd_tm
                return None

            # Calculate opacity byte (1-255, where 1 = nearly invisible)
            alpha_byte = max(1, min(255, int(opacity * 2.55)))  # opacity is 1-100
            
            # Query Virtual Screen metrics to cover all connected displays (Multi-Monitor Support)
            # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77, SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
            virt_x = user32.GetSystemMetrics(76)
            virt_y = user32.GetSystemMetrics(77)
            virt_w = user32.GetSystemMetrics(78)
            virt_h = user32.GetSystemMetrics(79)
            if virt_w <= 0:
                virt_w = user32.GetSystemMetrics(0)
            if virt_h <= 0:
                virt_h = user32.GetSystemMetrics(1)
            
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
                elif msg == 0x007E:  # WM_DISPLAYCHANGE
                    # Re-query virtual bounds if display topology/resolution changes while locked
                    vx = user32.GetSystemMetrics(76)
                    vy = user32.GetSystemMetrics(77)
                    vw = user32.GetSystemMetrics(78)
                    vh = user32.GetSystemMetrics(79)
                    if vw <= 0: vw = user32.GetSystemMetrics(0)
                    if vh <= 0: vh = user32.GetSystemMetrics(1)
                    hwnd_tm = _get_taskmgr_hwnd()
                    if hwnd_tm:
                        user32.SetWindowPos(hwnd, hwnd_tm, vx, vy, vw, vh, 0x0010 | 0x0040)
                    else:
                        user32.SetWindowPos(hwnd, HWND_TOPMOST, vx, vy, vw, vh, 0x0010 | 0x0040)
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
            
            # Create the window spanning all displays (virtual screen rect)
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW,
                class_name,
                "HELRCUS Lock",
                WS_POPUP | WS_VISIBLE,
                virt_x, virt_y, virt_w, virt_h,
                None, None, hInstance_ptr, None
            )
            
            if not hwnd:
                print("[HELRCUS] Failed to create lock window")
                cls._active = False
                return
            
            hwnd_ref[0] = hwnd
            with cls._lock:
                cls._hwnd = hwnd
            
            # Start in stealth/invisible mode (overlay panel will only show if user clicks screen)
            cls._overlay_shown = False
            cls.set_visibility(False, animate=False)
            
            # Low-level Keyboard Hook definitions to block all user input except emergency shortcuts (Ctrl+Shift+Esc, Ctrl+Alt+Del) & unlock hotkey
            WH_KEYBOARD_LL = 13
            
            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_ulonglong)
                ]
            
            HOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_longlong, ctypes.c_int,
                wintypes.WPARAM, wintypes.LPARAM
            )
            
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_longlong
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = ctypes.c_short

            def _is_pressed(vk):
                return (user32.GetAsyncKeyState(vk) & 0x8000) != 0

            h_hook_ref = [None]

            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            GA_ROOT = 2

            def low_level_keyboard_proc(nCode, wParam, lParam):
                if nCode >= 0:
                    try:
                        # Allow all keyboard inputs when Task Manager is in focus or root ancestor is Task Manager
                        fg_hwnd = user32.GetForegroundWindow()
                        hwnd_tm = _get_taskmgr_hwnd()
                        if hwnd_tm and (fg_hwnd == hwnd_tm or user32.GetAncestor(fg_hwnd, GA_ROOT) == hwnd_tm):
                            return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)

                        if fg_hwnd:
                            buf = ctypes.create_unicode_buffer(256)
                            user32.GetClassNameW(fg_hwnd, buf, 256)
                            if buf.value.lower() in ("taskmanagerwindow", "resmonwindowclass"):
                                return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)

                        kbd_struct = KBDLLHOOKSTRUCT.from_address(lParam)
                        vk = kbd_struct.vkCode
                        
                        # 1. Allow Ctrl + Shift + Esc (Task Manager)
                        if vk == 0x1B:  # VK_ESCAPE
                            if _is_pressed(0x11) and _is_pressed(0x10):  # Ctrl + Shift
                                return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)
                        
                        # 2. Allow Ctrl + Alt + Del (Security Attention Sequence)
                        if vk == 0x2E:  # VK_DELETE
                            if _is_pressed(0x11) and _is_pressed(0x12):  # Ctrl + Alt
                                return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)

                        # 3. Always pass through modifier keypress events (Ctrl, Shift, Alt) so emergency shortcuts & unlock hotkey combos work
                        if vk in (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                            return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)

                        is_mod_ctrl = bool(unlock_modifiers & 0x0002)
                        is_mod_shift = bool(unlock_modifiers & 0x0004)
                        is_mod_alt = bool(unlock_modifiers & 0x0001)

                        ctrl_down = _is_pressed(0x11) or _is_pressed(0xA2) or _is_pressed(0xA3)
                        shift_down = _is_pressed(0x10) or _is_pressed(0xA0) or _is_pressed(0xA1)
                        alt_down = _is_pressed(0x12) or _is_pressed(0xA4) or _is_pressed(0xA5)
                        
                        if vk == unlock_vk and (ctrl_down == is_mod_ctrl) and (shift_down == is_mod_shift) and (alt_down == is_mod_alt):
                            cls.unlock()
                            return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)

                        # 4. Block all other system/application inputs
                        return 1
                    except Exception:
                        pass
                return user32.CallNextHookEx(h_hook_ref[0], nCode, wParam, lParam)
            
            kb_hook_proc = HOOKPROC(low_level_keyboard_proc)
            h_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, kb_hook_proc, hInstance_ptr, 0)
            h_hook_ref[0] = h_hook

            # Register unlock hotkey
            user32.RegisterHotKey(hwnd, HOTKEY_ID, unlock_modifiers, unlock_vk)
            
            # Bring to front and capture focus
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            
            gdi32.CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            gdi32.CreateRectRgn.restype = wintypes.HRGN

            gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
            gdi32.CombineRgn.restype = ctypes.c_int

            gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            gdi32.DeleteObject.restype = wintypes.BOOL

            user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
            user32.SetWindowRgn.restype = ctypes.c_int

            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL

            prev_tm_rect = [None]
            
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
                        vx = user32.GetSystemMetrics(76)
                        vy = user32.GetSystemMetrics(77)
                        vw = user32.GetSystemMetrics(78)
                        vh = user32.GetSystemMetrics(79)
                        if vw <= 0: vw = user32.GetSystemMetrics(0)
                        if vh <= 0: vh = user32.GetSystemMetrics(1)
                        
                        hwnd_tm = _get_taskmgr_hwnd()
                        with cls._lock:
                            ov_hwnd = cls._overlay_hwnd

                        has_ov = ov_hwnd and user32.IsWindow(ov_hwnd) and user32.IsWindowVisible(ov_hwnd)

                        if hwnd_tm:
                            # Physically cut out Task Manager's bounding rect from the lock screen window region
                            rect_tm = wintypes.RECT()
                            if user32.GetWindowRect(hwnd_tm, ctypes.byref(rect_tm)):
                                curr_rect = (rect_tm.left, rect_tm.top, rect_tm.right, rect_tm.bottom)
                                if prev_tm_rect[0] != curr_rect:
                                    prev_tm_rect[0] = curr_rect
                                    rgn_full = gdi32.CreateRectRgn(vx, vy, vx + vw, vy + vh)
                                    rgn_tm = gdi32.CreateRectRgn(rect_tm.left, rect_tm.top, rect_tm.right, rect_tm.bottom)
                                    rgn_diff = gdi32.CreateRectRgn(0, 0, 0, 0)
                                    gdi32.CombineRgn(rgn_diff, rgn_full, rgn_tm, 4)  # RGN_DIFF = 4
                                    user32.SetWindowRgn(hwnd_ref[0], rgn_diff, True)
                                    gdi32.DeleteObject(rgn_full)
                                    gdi32.DeleteObject(rgn_tm)

                            # Keep Task Manager on TOPMOST layer (-1)
                            user32.SetWindowPos(hwnd_tm, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                            
                            if has_ov:
                                # Place LockScreenOverlay directly behind Task Manager
                                user32.SetWindowPos(ov_hwnd, hwnd_tm, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
                                # Place fullscreen lock screen directly behind LockScreenOverlay
                                user32.SetWindowPos(hwnd_ref[0], ov_hwnd, vx, vy, vw, vh, 0x0010 | 0x0040)
                            else:
                                # Place transparent lock screen directly behind Task Manager
                                user32.SetWindowPos(hwnd_ref[0], hwnd_tm, vx, vy, vw, vh, 0x0010 | 0x0040)
                        else:
                            if prev_tm_rect[0] is not None:
                                prev_tm_rect[0] = None
                                user32.SetWindowRgn(hwnd_ref[0], None, True)

                            if has_ov:
                                # Keep LockScreenOverlay at TOPMOST (-1)
                                user32.SetWindowPos(ov_hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
                                # Place fullscreen lock screen directly behind LockScreenOverlay
                                user32.SetWindowPos(hwnd_ref[0], ov_hwnd, vx, vy, vw, vh, 0x0010 | 0x0040)
                            else:
                                user32.SetWindowPos(hwnd_ref[0], HWND_TOPMOST, vx, vy, vw, vh, 0x0010 | 0x0040)
                    ctypes.windll.kernel32.Sleep(50)
            
            # Cleanup
            if h_hook_ref[0]:
                user32.UnhookWindowsHookEx(h_hook_ref[0])
            
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
            # First attempt Zero-UAC Helper Service execution (No UAC prompt)
            try:
                from integrations.cpu_controller import is_service_running, send_service_command
                if is_service_running():
                    res = send_service_command({"action": "exec_batch_commands", "commands": commands})
                    if isinstance(res, dict) and res.get("status") == "success":
                        return True, ""
                    elif isinstance(res, dict) and res.get("message"):
                        print(f"[WindowsUpdateControl] Helper service exec error: {res.get('message')}, trying UAC fallback...")
            except Exception as svc_err:
                print(f"[WindowsUpdateControl] Helper service check exception: {svc_err}")

            # Fallback for non-Zero-UAC mode — use VBS wrapper to prevent console flash
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
        """Get current Windows Update pause status via native Win32 registry API (<0.1ms)."""
        try:
            import winreg
            from datetime import datetime as _dt
            access_mask = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", 0, access_mask) as key:
                raw_date, _ = winreg.QueryValueEx(key, "PauseUpdatesExpiryTime")
                if raw_date:
                    try:
                        date_part = str(raw_date).split('T')[0]
                        parsed = _dt.strptime(date_part, "%Y-%m-%d")
                        return True, parsed.strftime("%d/%m/%Y")
                    except Exception:
                        return True, str(raw_date)
            return False, "Not paused"
        except (FileNotFoundError, OSError):
            return False, "Not paused"
        except Exception:
            return False, "Unknown"

    @staticmethod
    def get_auto_restart_status():
        """Get current NoAutoRebootWithLoggedOnUsers status from registry (<0.1ms)."""
        try:
            import winreg
            access_mask = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", 0, access_mask) as key:
                val, _ = winreg.QueryValueEx(key, "NoAutoRebootWithLoggedOnUsers")
                return int(val) == 1
        except (FileNotFoundError, OSError):
            return False
        except Exception:
            return False



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
        self._ui_initialized = True
        self._lock_overlay = None
        self._native_hotkey_filter = None
        self._registered_hotkey_hwnd = None
        
        # Build UI and load state immediately in memory so page transitions are 0ms instant
        self._setup_ui()
        self._load_state()
        
        QTimer.singleShot(100, self._register_global_hotkey)
        lock_signals.show_password.connect(self._show_lock_overlay)
        lock_signals.hide_password.connect(self._hide_lock_overlay)

    def showEvent(self, event):
        """Refresh dynamic status on tab display."""
        super().showEvent(event)
        self._load_state()

    def _setup_ui(self):
        """Build the panel UI."""
        # Build absolute path for icons
        script_dir = os.path.dirname(os.path.abspath(__file__))
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        
        self.setStyleSheet(f"""
            QWidget#windowsCustomPanel {{
                background: transparent;
            }}
            QFrame#featureCard {{
                background: rgba(30, 30, 30, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }}
            QFrame#featureCard:hover {{
                border-color: rgba(255, 91, 6, 0.4);
            }}
            QGroupBox {{
                background: rgba(30, 30, 30, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                margin-top: 12px;
                padding: 15px;
                font-weight: bold;
                color: #FF5B06;
            }}
            QGroupBox:hover {{
                border-color: rgba(255, 91, 6, 0.4);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
            }}

            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: rgba(255, 255, 255, 0.05);
            }}
            QCheckBox::indicator:hover {{
                border-color: #FF5B06;
            }}
            QCheckBox::indicator:checked {{
                background-color: #FF5B06;
                border-color: #FF5B06;
            }}

            QComboBox {{
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: none;
                border-radius: 10px;
                padding-left: 12px;
                padding-right: 30px;
                padding-top: 6px;
                padding-bottom: 6px;
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                border: none;
                width: 24px;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                subcontrol-origin: content;
                subcontrol-position: center;
                image: url({down_arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: rgba(18, 20, 26, 0.65);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
                outline: 0px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 26px;
                padding: 4px 8px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
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
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(60, 64, 72, 0.8);
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #e0e0e0;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: none;
            }}
            QSlider::handle:horizontal:hover {{
                background: #ffffff;
            }}
            QSlider::sub-page:horizontal {{
                background: rgba(255, 91, 6, 0.6);
                border-radius: 2px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 16px;
                border-radius: 8px;
                margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 7px;
                min-height: 40px;
                border: 2px solid rgba(253, 169, 3, 0.8);
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: 2px solid #FFFF00;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
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
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(24)
        
        # ===== HEADER =====
        header_container = QWidget()
        header_container.setObjectName("headerCard")
        header_card_layout = QHBoxLayout(header_container)
        header_card_layout.setContentsMargins(24, 20, 24, 20)
        
        title_section = QVBoxLayout()
        title_section.setSpacing(4)
        
        title_label = QLabel("HELRCUS")
        title_label.setObjectName("helrcusHeaderTitle")
        title_label.setStyleSheet("""
            color: #DDE6ED;
            font-size: 28px;
            font-weight: 600;
            letter-spacing: 1px;
            font-family: 'Orbitron';
            background: transparent;
        """)
        title_section.addWidget(title_label)
        
        subtitle_label = QLabel("Windows Customization")
        subtitle_label.setObjectName("helrcusHeaderSubtitle")
        subtitle_label.setStyleSheet("""
            color: #9DB2BF;
            font-size: 12px;
            letter-spacing: 0.5px;
            font-family: 'Orbitron';
            background: transparent;
        """)
        title_section.addWidget(subtitle_label)
        
        header_card_layout.addLayout(title_section)
        header_card_layout.addStretch()
        
        # Settings button (opens HelrcusSettingsFloatingPanel, styled identically to cpuSettingsBtn)
        settings_btn = AnimatedButton("")
        settings_btn.setObjectName("helrcusHeaderSettingsBtn")
        settings_btn.setFixedSize(50, 50)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setToolTip("HELRCUS Settings")
        
        icon_path = os.path.join(script_dir, "UI Icons", "setting-icon.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(script_dir, "UI Icons", "settings-icon.svg")
            
        if os.path.exists(icon_path):
            settings_btn.setIcon(QIcon(icon_path))
            settings_btn.setIconSize(QSize(50, 50))
            
        settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
        """)
        
        # Setup animated icon rotation on hover matching cpuSettingsBtn (lazy initialized on first hover)
        if os.path.exists(icon_path):
            settings_btn._rot_frames = None
            settings_btn._rot_index = 0
            settings_btn._rot_forward = True
            settings_btn._rot_timer = QTimer(settings_btn)
            settings_btn._rot_timer.setInterval(20)  # 20ms per frame = ~200ms total
            
            def _lazy_init_frames():
                if getattr(settings_btn, '_rot_frames', None) is not None:
                    return
                full_pixmap = QPixmap(icon_path)
                target_size = QSize(50, 50)
                pixmap = full_pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                del full_pixmap
                original_size = pixmap.size()
                frames = []
                for i in range(10):
                    angle = -5 * i
                    transform = QTransform().rotate(angle)
                    rotated = pixmap.transformed(transform, Qt.SmoothTransformation)
                    canvas = QPixmap(original_size)
                    canvas.fill(Qt.transparent)
                    painter = QPainter(canvas)
                    x = (original_size.width() - rotated.width()) // 2
                    y = (original_size.height() - rotated.height()) // 2
                    painter.drawPixmap(x, y, rotated)
                    painter.end()
                    frames.append(QIcon(canvas))
                settings_btn._rot_frames = frames

            def _animate_frame():
                frames = getattr(settings_btn, '_rot_frames', None)
                if not frames:
                    return
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
                _lazy_init_frames()
                settings_btn._rot_forward = True
                settings_btn._rot_timer.start()
                original_enter(event)
            
            def new_leave(event):
                settings_btn._rot_forward = False
                settings_btn._rot_timer.start()
                original_leave(event)
            
            settings_btn.enterEvent = new_enter
            settings_btn.leaveEvent = new_leave
            
        settings_btn.clicked.connect(self._show_helrcus_settings_dialog)
        header_card_layout.addWidget(settings_btn, alignment=Qt.AlignVCenter)
        
        header_container.setStyleSheet("""
            QWidget#headerCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 rgba(26, 26, 26, 0.9), stop:1 rgba(45, 45, 45, 0.6));
                border-radius: 16px;
                border: 1px solid rgba(255, 91, 6, 0.3);
            }
        """)
        main_layout.addWidget(header_container)
        
        # Scrollable content
        scroll = SmoothScrollArea()
        scroll.setObjectName("helrcusScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 16px;
                border-radius: 8px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 7px;
                min-height: 40px;
                border: 2px solid rgba(253, 169, 3, 0.8);
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: 2px solid #FFFF00;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        
        content = QWidget()
        content.setObjectName("helrcusContentWidget")
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)
        
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
        lock_icon = os.path.join(script_dir, "UI Icons", "lock-icon.svg")
        
        card = FeatureCard(
            title="Invisible Lock Screen",
            description="Transparent overlay that blocks mouse & keyboard. Unlock with Ctrl+L, then Windows Lock Screen appears.",
            icon_path=lock_icon
        )
        
        # Status indicator
        self._lock_status = QLabel("● Inactive")
        self._lock_status.setObjectName("helrcusLockStatus")
        self._lock_status.setStyleSheet("color: #888888; font-size: 12px; font-weight: 500;")
        card.add_content(self._lock_status)
        
        # Separator
        sep = QFrame()
        sep.setObjectName("helrcusLockSep")
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
        opacity_lbl.setObjectName("helrcusOpacityLabel")
        opacity_lbl.setFixedWidth(140)
        opacity_lbl.setStyleSheet("font-size: 12px;")
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setObjectName("helrcusOpacitySlider")
        self._opacity_slider.setRange(1, 100)
        self._opacity_slider.setValue(self._config["lock_screen"]["opacity"])
        self._opacity_slider.setFixedHeight(20)
        self._opacity_value = QLabel(f"{self._config['lock_screen']['opacity']}%")
        self._opacity_value.setObjectName("helrcusOpacityValue")
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
        hotkey_lbl.setObjectName("helrcusActivationHotkeyLabel")
        hotkey_lbl.setFixedWidth(140)
        hotkey_lbl.setFixedHeight(34)
        hotkey_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hotkey_lbl.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        self._activation_hotkey_btn = HotkeyRecordButton(self._config["lock_screen"].get("hotkey", "Ctrl+Alt+L"))
        self._activation_hotkey_btn.setObjectName("helrcusActivationHotkeyBtn")
        self._activation_hotkey_btn.hotkeyChanged.connect(self._on_activation_hotkey_changed)
        # Pause the OS-level hotkey while the user is recording a new one,
        # otherwise the current combo fires the lock screen before Qt captures it.
        self._activation_hotkey_btn.recordingStarted.connect(self._unregister_global_hotkey)
        self._activation_hotkey_btn.recordingStopped.connect(self._register_global_hotkey)
        
        hotkey_hint = QLabel("(Global activation)")
        hotkey_hint.setObjectName("helrcusActivationHotkeyHint")
        hotkey_hint.setFixedHeight(24)
        hotkey_hint.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hotkey_hint.setStyleSheet("color: #666; font-size: 10px; margin: 0px; padding: 0px; background: transparent;")
        
        rules_info_btn = QPushButton()
        rules_info_btn.setObjectName("helrcusRulesInfoBtn")
        rules_info_btn.setFixedSize(24, 24)
        rules_info_btn.setCursor(Qt.PointingHandCursor)
        rules_info_btn.setToolTip("View Hotkey Rules")
        if os.path.exists(os.path.join(script_dir, "UI Icons", "info-icon.svg")):
            rules_info_btn.setIcon(QIcon(os.path.join(script_dir, "UI Icons", "info-icon.svg")))
            rules_info_btn.setIconSize(QSize(16, 16))
            rules_info_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; padding: 0px; margin: 0px; }
                QPushButton:hover { background: rgba(255, 255, 255, 0.1); border-radius: 12px; }
            """)
        else:
            rules_info_btn.setText("ℹ")
            rules_info_btn.setStyleSheet("background: transparent; border: none; color: #FF5B06; font-size: 14px; padding: 0px; margin: 0px;")
        rules_info_btn.clicked.connect(self._show_hotkey_rules_dialog)
        
        hotkey_row.addWidget(hotkey_lbl, 0, Qt.AlignVCenter)
        hotkey_row.addWidget(self._activation_hotkey_btn, 0, Qt.AlignVCenter)
        hotkey_row.addWidget(hotkey_hint, 0, Qt.AlignVCenter)
        hotkey_row.addWidget(rules_info_btn, 0, Qt.AlignVCenter)
        hotkey_row.addStretch()
        controls_layout.addLayout(hotkey_row)
        
        # Global Unlock Hotkey
        unlock_row = QHBoxLayout()
        unlock_row.setSpacing(10)
        unlock_row.setAlignment(Qt.AlignVCenter)
        unlock_lbl = QLabel("Unlock Hotkey:")
        unlock_lbl.setObjectName("helrcusUnlockHotkeyLabel")
        unlock_lbl.setFixedWidth(140)
        unlock_lbl.setFixedHeight(34)
        unlock_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        unlock_lbl.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        self._unlock_hotkey_btn = HotkeyRecordButton(self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L"))
        self._unlock_hotkey_btn.setObjectName("helrcusUnlockHotkeyBtn")
        self._unlock_hotkey_btn.hotkeyChanged.connect(self._on_unlock_hotkey_changed)
        self._unlock_hotkey_btn.recordingStarted.connect(self._unregister_global_hotkey)
        self._unlock_hotkey_btn.recordingStopped.connect(self._register_global_hotkey)
        
        unlock_hint = QLabel("(Unlock when active)")
        unlock_hint.setObjectName("helrcusUnlockHotkeyHint")
        unlock_hint.setFixedHeight(24)
        unlock_hint.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        unlock_hint.setStyleSheet("color: #666; font-size: 10px; margin: 0px; padding: 0px; background: transparent;")
        
        unlock_row.addWidget(unlock_lbl, 0, Qt.AlignVCenter)
        unlock_row.addWidget(self._unlock_hotkey_btn, 0, Qt.AlignVCenter)
        unlock_row.addWidget(unlock_hint, 0, Qt.AlignVCenter)
        unlock_row.addStretch()
        controls_layout.addLayout(unlock_row)
        
        # Cross-validation setup
        self._activation_hotkey_btn.setForbiddenKeys([self._unlock_hotkey_btn.hotkey()])
        self._unlock_hotkey_btn.setForbiddenKeys([self._activation_hotkey_btn.hotkey()])
        
        # Unlock info row
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        info_row.setAlignment(Qt.AlignVCenter)
        
        info_icon_lbl = QLabel()
        info_icon_lbl.setObjectName("helrcusLockInfoIcon")
        lock_icon_path = os.path.join(SCRIPT_DIR, "UI Icons", "lock-icon.svg")
        if os.path.exists(lock_icon_path):
            info_icon_lbl.setPixmap(get_cached_pixmap(lock_icon_path, 18, 18))
            info_icon_lbl.setFixedSize(18, 18)
        info_icon_lbl.setStyleSheet("background: transparent;")
        
        info_lbl = QLabel("Click lock screen → Unlock button → Windows lock screen (PIN / Fingerprint / Face)")
        info_lbl.setObjectName("helrcusLockInfoLabel")
        info_lbl.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        info_lbl.setWordWrap(True)
        info_row.addWidget(info_icon_lbl)
        info_row.addWidget(info_lbl, 1)
        controls_layout.addLayout(info_row)
        
        # Lock on app exit checkbox
        self._lock_on_exit_cb = AnimatedCheckBox("Lock workstation when HELXAID exits")
        self._lock_on_exit_cb.setObjectName("helrcusLockOnExitCheckBox")
        self._lock_on_exit_cb.setChecked(self._config["lock_screen"]["lock_on_exit"])
        self._lock_on_exit_cb.toggled.connect(self._on_lock_exit_changed)
        controls_layout.addWidget(self._lock_on_exit_cb)
        
        controls_widget = QWidget()
        controls_widget.setObjectName("helrcusLockControlsWidget")
        controls_widget.setLayout(controls_layout)
        card.add_content(controls_widget)
        
        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignVCenter)
        
        self._lock_activate_btn = QPushButton("  Activate Lock Screen")
        self._lock_activate_btn.setObjectName("helrcusActivateLockBtn")
        self._lock_activate_btn.setFixedHeight(40)
        self._lock_activate_btn.setFocusPolicy(Qt.NoFocus)
        # Set lock icon on button
        lock_btn_icon_path = os.path.join(script_dir, "UI Icons", "lock-icon.svg")
        if os.path.exists(lock_btn_icon_path):
            self._lock_activate_btn.setIcon(QIcon(lock_btn_icon_path))
            self._lock_activate_btn.setIconSize(QSize(18, 18))
        self._lock_activate_btn.clicked.connect(self._activate_lock_screen)
        btn_row.addWidget(self._lock_activate_btn)
        
        btn_row.addStretch()
        
        btn_widget = QWidget()
        btn_widget.setObjectName("helrcusLockBtnWidget")
        btn_widget.setLayout(btn_row)
        card.add_content(btn_widget)
        
        # Hotkey info with icon
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(6)
        hotkey_row.setAlignment(Qt.AlignVCenter)
        tips_icon_path = os.path.join(script_dir, "UI Icons", "tip-icon.svg")
        if os.path.exists(tips_icon_path):
            tips_icon = QLabel()
            tips_icon.setObjectName("helrcusLockTipsIcon")
            tips_pix = get_cached_pixmap(tips_icon_path, 14, 14)
            tips_icon.setPixmap(tips_pix)
            tips_icon.setFixedSize(14, 14)
            tips_icon.setStyleSheet("background: transparent;")
            hotkey_row.addWidget(tips_icon)
        unlock_key = self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L")
        self._hotkey_info = QLabel(f"Press {unlock_key} to unlock → Windows Lock Screen will appear")
        self._hotkey_info.setObjectName("helrcusLockHotkeyInfo")
        self._hotkey_info.setStyleSheet("color: #aaa; font-size: 11px;")
        hotkey_row.addWidget(self._hotkey_info)
        hotkey_row.addStretch()
        hotkey_widget = QWidget()
        hotkey_widget.setObjectName("helrcusLockHotkeyWidget")
        hotkey_widget.setLayout(hotkey_row)
        card.add_content(hotkey_widget)
        
        parent_layout.addWidget(card)

    
    def _setup_windows_update_card(self, parent_layout):
        """Setup the Windows Update control card."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        update_icon = os.path.join(script_dir, "UI Icons", "windowsIcon.png")
        
        card = FeatureCard(
            title="Windows Update Control",
            description="Manage Windows Update behavior — pause updates, disable auto-restart, set active hours.",
            icon_path=update_icon
        )
        
        # Admin status
        is_admin = WindowsUpdateControl.is_admin()
        admin_status = QLabel("● Running as Administrator" if is_admin else "● Some features require Administrator")
        admin_status.setObjectName("helrcusUpdateAdminStatus")
        admin_status.setStyleSheet(
            "color: #4CAF50; font-size: 11px;" if is_admin else "color: #FFA726; font-size: 11px;"
        )
        card.add_content(admin_status)
        
        # Current status
        paused, pause_info = WindowsUpdateControl.get_update_status()
        self._update_status = QLabel(f"● Updates paused until {pause_info}" if paused else "● Updates active")
        self._update_status.setObjectName("helrcusUpdateStatus")
        self._update_status.setStyleSheet(
            f"color: {'#FFA726' if paused else '#4CAF50'}; font-size: 12px; font-weight: 500;"
        )
        card.add_content(self._update_status)
        
        # Separator
        sep = QFrame()
        sep.setObjectName("helrcusUpdateSep")
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(255, 255, 255, 0.05); max-height: 1px; border: none;")
        card.add_content(sep)
        
        # Controls container
        controls = QWidget()
        controls.setObjectName("helrcusUpdateControls")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 8, 0, 0)
        controls_layout.setSpacing(14)
        
        # --- Pause Updates Section ---
        pause_lbl = QLabel("Pause until (DD/MM/YY):")
        pause_lbl.setObjectName("helrcusPauseLabel")
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
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px 6px;
                font-size: 13px;
                font-weight: 600;
                margin: 0px;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }
            QLineEdit::selection {
                background-color: #ffffff;
                color: #000000;
            }
            QLineEdit:hover {
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 91, 6, 0.5);
            }
            QLineEdit:focus {
                background: rgba(255, 91, 6, 0.15);
                border: 1.5px solid #FF5B06;
                color: #ffffff;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }
        """
        
        from PySide6.QtGui import QPalette, QColor
        _sel_palette = QPalette()
        _sel_palette.setColor(QPalette.Highlight, QColor("#ffffff"))
        _sel_palette.setColor(QPalette.HighlightedText, QColor("#000000"))

        # Day input
        self._pause_day = QLineEdit()
        self._pause_day.setObjectName("helrcusPauseDayInput")
        self._pause_day.setPlaceholderText("DD")
        self._pause_day.setFixedWidth(48)
        self._pause_day.setFixedHeight(36)
        self._pause_day.setMaxLength(2)
        self._pause_day.setAlignment(Qt.AlignCenter)
        self._pause_day.setPalette(_sel_palette)
        self._pause_day.setStyleSheet(_input_style)
        
        sep1 = QLabel("/")
        sep1.setObjectName("helrcusPauseDateSep1")
        sep1.setStyleSheet("color: #888; font-size: 14px; margin: 0px; background: transparent;")
        sep1.setFixedWidth(10)
        sep1.setFixedHeight(36)
        sep1.setAlignment(Qt.AlignCenter)
        
        # Month input
        self._pause_month = QLineEdit()
        self._pause_month.setObjectName("helrcusPauseMonthInput")
        self._pause_month.setPlaceholderText("MM")
        self._pause_month.setFixedWidth(48)
        self._pause_month.setFixedHeight(36)
        self._pause_month.setMaxLength(2)
        self._pause_month.setAlignment(Qt.AlignCenter)
        self._pause_month.setPalette(_sel_palette)
        self._pause_month.setStyleSheet(_input_style)
        
        sep2 = QLabel("/")
        sep2.setObjectName("helrcusPauseDateSep2")
        sep2.setStyleSheet("color: #888; font-size: 14px; margin: 0px; background: transparent;")
        sep2.setFixedWidth(10)
        sep2.setFixedHeight(36)
        sep2.setAlignment(Qt.AlignCenter)
        
        # Year input
        self._pause_year = QLineEdit()
        self._pause_year.setObjectName("helrcusPauseYearInput")
        self._pause_year.setPlaceholderText("YYYY")
        self._pause_year.setFixedWidth(64)
        self._pause_year.setFixedHeight(36)
        self._pause_year.setMaxLength(4)
        self._pause_year.setAlignment(Qt.AlignCenter)
        self._pause_year.setPalette(_sel_palette)
        self._pause_year.setStyleSheet(_input_style)
        
        # Populate from saved config or default to 30 days from today
        if saved_date:
            try:
                _saved = _dt.strptime(saved_date, "%d/%m/%Y")
                self._pause_day.setText(f"{_saved.day:02d}")
                self._pause_month.setText(f"{_saved.month:02d}")
                self._pause_year.setText(str(_saved.year))
            except ValueError:
                pass
        else:
            _default_date = _dt.now() + timedelta(days=30)
            self._pause_day.setText(f"{_default_date.day:02d}")
            self._pause_month.setText(f"{_default_date.month:02d}")
            self._pause_year.setText(str(_default_date.year))
        
        # --- Per-widget button style (MacroSettingsPanel pattern) ---
        _btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 500;
                margin: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: white;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.3);
            }
        """
        _primary_btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                margin: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.3);
            }
        """
        
        # Store styles and icons for toggling
        self._wu_primary_btn_style = _primary_btn_style
        self._wu_secondary_btn_style = _btn_style
        self._wu_pause_icon_path = os.path.join(script_dir, "UI Icons", "pause-icon.svg")
        self._wu_resume_icon_path = os.path.join(script_dir, "UI Icons", "loop-icon.svg")
        
        self._toggle_update_btn = QPushButton()
        self._toggle_update_btn.setObjectName("helrcusToggleUpdateBtn")
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
        self._no_restart_cb.setObjectName("helrcusNoRestartCheckBox")
        self._no_restart_cb.setChecked(self._config["windows_update"]["disable_auto_restart"])
        self._no_restart_cb.toggled.connect(self._on_auto_restart_changed)
        controls_layout.addWidget(self._no_restart_cb)
        
        # --- Active Hours Container ---
        self._active_hours_container = QFrame()
        self._active_hours_container.setObjectName("helrcusActiveHoursContainer")
        self._active_hours_container.setStyleSheet("background: transparent; border: none; margin: 0px;")
        
        hours_row = QHBoxLayout(self._active_hours_container)
        hours_row.setContentsMargins(0, 0, 0, 0)
        hours_row.setSpacing(10)
        hours_row.setAlignment(Qt.AlignVCenter)
        
        hours_lbl = QLabel("Active hours:")
        hours_lbl.setObjectName("helrcusActiveHoursLabel")
        hours_lbl.setFixedWidth(110)
        hours_lbl.setFixedHeight(36)
        hours_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hours_lbl.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        # Shared inline style for hour combo boxes (overrides global launcher stylesheet)
        _combo_style = f"""
            QComboBox {{
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 8px;
                padding: 3px 26px 3px 10px;
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: 500;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }}
            QComboBox:editable {{
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }}
            QComboBox QLineEdit {{
                background: transparent;
                color: #ffffff;
                border: none;
                font-family: 'Orbitron', sans-serif;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }}
            QComboBox QLineEdit::selection {{
                background-color: #ffffff;
                color: #000000;
            }}
            QComboBox:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                border: none;
                width: 24px;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                subcontrol-origin: content;
                subcontrol-position: center;
                image: url({down_arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #1e2128;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                color: #e0e0e0;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 26px;
                padding: 4px 8px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
                font-family: 'Orbitron', sans-serif;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }}
            QComboBox QAbstractItemView QScrollBar:vertical,
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px 4px 0px;
                border: none;
            }}
            QComboBox QAbstractItemView QScrollBar::handle:vertical,
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.2);
                min-height: 24px;
                border-radius: 3px;
                border: none;
            }}
            QComboBox QAbstractItemView QScrollBar::handle:vertical:hover,
            QScrollBar::handle:vertical:hover {{
                background: #FF5B06;
            }}
            QComboBox QAbstractItemView QScrollBar::handle:vertical:pressed,
            QScrollBar::handle:vertical:pressed {{
                background: #FDA903;
            }}
            QComboBox QAbstractItemView QScrollBar::add-line:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-line:vertical,
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                width: 0px;
                background: transparent;
                border: none;
            }}
            QComboBox QAbstractItemView QScrollBar::add-page:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-page:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
            }}
        """
        
        self._hours_preset_combo = QComboBox()
        self._hours_preset_combo.setObjectName("helrcusHoursPresetCombo")
        self._hours_preset_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._hours_preset_combo.addItems(["Always Active (Max 18h)", "8 Hours", "12 Hours", "18 Hours", "Customize"])
        # Set default selection from config (backward-compatible with legacy "Always Active")
        saved_preset = self._config["windows_update"].get("active_hours_preset", "Always Active (Max 18h)")
        if saved_preset == "Always Active":
            saved_preset = "Always Active (Max 18h)"
        preset_idx = self._hours_preset_combo.findText(saved_preset)
        if preset_idx >= 0:
            self._hours_preset_combo.setCurrentIndex(preset_idx)
        else:
            self._hours_preset_combo.setCurrentIndex(0)  # Default to Always Active (Max 18h)
        self._hours_preset_combo.setMinimumWidth(185)
        self._hours_preset_combo.setFixedHeight(36)
        self._hours_preset_combo.setStyleSheet(_combo_style)
        self._hours_preset_combo.setToolTip(
            "Windows limits Active Hours to a maximum of 18 hours (e.g. 12:00 AM - 6:00 PM).\n"
            "To completely prevent automatic restarts 24/7, check 'Disable automatic restart after updates' above."
        )
        self._hours_preset_combo.currentIndexChanged.connect(self._on_hours_preset_changed)
        if self._hours_preset_combo.view() is not None:
            self._hours_preset_combo.view().setObjectName("helrcusHoursPresetView")
            if self._hours_preset_combo.view().verticalScrollBar() is not None:
                self._hours_preset_combo.view().verticalScrollBar().setObjectName("helrcusHoursPresetScrollBar")
        
        # Custom duration container widget
        self._custom_hours_widget = QWidget()
        self._custom_hours_widget.setObjectName("helrcusCustomHoursWidget")
        self._custom_hours_widget.setFixedHeight(36)
        self._custom_hours_widget.setStyleSheet("background: transparent; margin: 0px;")
        custom_layout = QHBoxLayout(self._custom_hours_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(10)
        custom_layout.setAlignment(Qt.AlignVCenter)
        
        from PySide6.QtGui import QPalette, QColor
        _sel_palette = QPalette()
        _sel_palette.setColor(QPalette.Highlight, QColor("#ffffff"))
        _sel_palette.setColor(QPalette.HighlightedText, QColor("#000000"))

        self._hours_start = QComboBox()
        self._hours_start.setObjectName("helrcusHoursStartCombo")
        self._hours_start.setEditable(True)
        self._hours_start.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._hours_start.addItems([f"{i:02d}:00" for i in range(24)])
        self._hours_start.setCurrentIndex(self._config["windows_update"]["active_hours_start"])
        self._hours_start.setMinimumWidth(100)
        self._hours_start.setFixedHeight(36)
        self._hours_start.setStyleSheet(_combo_style)
        self._setup_time_combo_behavior(self._hours_start, _sel_palette)
        
        hours_to = QLabel("to")
        hours_to.setObjectName("helrcusHoursToLabel")
        hours_to.setFixedHeight(36)
        hours_to.setAlignment(Qt.AlignCenter)
        hours_to.setStyleSheet("font-size: 12px; margin: 0px; background: transparent;")
        
        self._hours_end = QComboBox()
        self._hours_end.setObjectName("helrcusHoursEndCombo")
        self._hours_end.setEditable(True)
        self._hours_end.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._hours_end.addItems([f"{i:02d}:00" for i in range(24)])
        self._hours_end.setCurrentIndex(self._config["windows_update"]["active_hours_end"])
        self._hours_end.setMinimumWidth(100)
        self._hours_end.setFixedHeight(36)
        self._hours_end.setStyleSheet(_combo_style)
        self._setup_time_combo_behavior(self._hours_end, _sel_palette)
        
        custom_layout.addWidget(self._hours_start, 0, Qt.AlignVCenter)
        custom_layout.addWidget(hours_to, 0, Qt.AlignVCenter)
        custom_layout.addWidget(self._hours_end, 0, Qt.AlignVCenter)
        
        self._apply_hours_btn = QPushButton("Apply")
        self._apply_hours_btn.setObjectName("helrcusApplyHoursBtn")
        self._apply_hours_btn.setFixedHeight(36)
        self._apply_hours_btn.setFixedWidth(90)
        self._apply_hours_btn.setStyleSheet(_primary_btn_style)
        self._apply_hours_btn.setCursor(Qt.PointingHandCursor)
        self._apply_hours_btn.setToolTip("Apply Active Hours to Windows Registry.")
        self._apply_hours_btn.clicked.connect(self._apply_active_hours)
        
        hours_row.addWidget(hours_lbl, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._hours_preset_combo, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._custom_hours_widget, 0, Qt.AlignVCenter)
        hours_row.addWidget(self._apply_hours_btn, 0, Qt.AlignVCenter)
        hours_row.addStretch()
        
        # Opacity effect for dimming / dark overlay state when Disable Auto-Restart is checked
        self._active_hours_opacity = QGraphicsOpacityEffect(self._active_hours_container)
        self._active_hours_container.setGraphicsEffect(self._active_hours_opacity)
        
        controls_layout.addWidget(self._active_hours_container)
        
        # Apply initial active hours dimmed state based on auto-restart toggle
        self._update_active_hours_state(self._no_restart_cb.isChecked(), animate=False)
        
        # Hide custom duration selectors if not Customize
        self._custom_hours_widget.setVisible(self._hours_preset_combo.currentText() == "Customize")
        
        card.add_content(controls)
        
        # Info note with icon
        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        info_row.setAlignment(Qt.AlignVCenter)
        tips_icon_path = os.path.join(script_dir, "UI Icons", "tip-icon.svg")
        if os.path.exists(tips_icon_path):
            tips_icon2 = QLabel()
            tips_icon2.setObjectName("helrcusUpdateTipsIcon")
            tips_pix2 = get_cached_pixmap(tips_icon_path, 14, 14)
            tips_icon2.setPixmap(tips_pix2)
            tips_icon2.setFixedSize(14, 14)
            tips_icon2.setStyleSheet("background: transparent;")
            info_row.addWidget(tips_icon2)
        info_note = QLabel("Pause & active hours take effect immediately. Note: Windows caps Active Hours at 18h max (e.g. 12 AM - 6 PM). For 24/7 protection, check 'Disable automatic restart' above.")
        info_note.setObjectName("helrcusUpdateInfoNote")
        info_note.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        info_note.setWordWrap(True)
        info_row.addWidget(info_note, 1)
        info_widget = QWidget()
        info_widget.setObjectName("helrcusUpdateInfoWidget")
        info_widget.setLayout(info_row)
        card.add_content(info_widget)
        
        parent_layout.addWidget(card)

    
    # ============================================
    # EVENT HANDLERS
    # ============================================
    
    def _show_hotkey_rules_dialog(self):
        """Display the floating Hotkey Rules & Guidelines panel matching HELXAIL guide style."""
        if getattr(self, "_guide_panel", None) is not None:
            try:
                self._guide_panel.close()
            except Exception:
                pass
            self._guide_panel = None
            
        parent_win = self.window()
        self._guide_panel = HelrcusHotkeyGuidePanel(parent_win)
        
        # Center inside parent window
        rect = parent_win.rect()
        self._guide_panel.move(
            (rect.width() - self._guide_panel.width()) // 2,
            (rect.height() - self._guide_panel.height()) // 2
        )
        self._guide_panel.show()

    def _show_helrcus_settings_dialog(self):
        """Display the floating HELRCUS Module Settings panel."""
        if getattr(self, "_settings_panel", None) is not None:
            try:
                self._settings_panel.close()
            except Exception:
                pass
            self._settings_panel = None
            
        parent_win = self.window()
        self._settings_panel = HelrcusSettingsFloatingPanel(self, parent_win)
        
        # Center inside parent window
        rect = parent_win.rect()
        self._settings_panel.move(
            max(0, (rect.width() - self._settings_panel.width()) // 2),
            max(0, (rect.height() - self._settings_panel.height()) // 2)
        )
        self._settings_panel.show()
        self._settings_panel.raise_()

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
        if hasattr(self, "_lock_overlay") and self._lock_overlay is not None:
            try:
                self._lock_overlay.raise_()
                self._lock_overlay.activateWindow()
                InvisibleLockScreen._overlay_shown = True
                return
            except Exception:
                pass

        InvisibleLockScreen._overlay_shown = True
        self._lock_overlay = LockScreenOverlay(None)
        self._lock_overlay.show()

    def _hide_lock_overlay(self):
        """Close and dispose of the 'Screen is Locked' overlay panel."""
        if hasattr(self, "_lock_overlay") and self._lock_overlay is not None:
            try:
                overlay = self._lock_overlay
                self._lock_overlay = None
                overlay.close()
                overlay.deleteLater()
            except Exception:
                pass
        InvisibleLockScreen._overlay_shown = False

    
    def _activate_lock_screen(self):
        """Activate the invisible lock screen."""
        if InvisibleLockScreen.is_active():
            return
        
        opacity = self._config["lock_screen"]["opacity"]
        unlock_hotkey = self._config["lock_screen"].get("unlock_hotkey", "Ctrl+Shift+L")
        InvisibleLockScreen.activate(opacity, unlock_hotkey)
        
        if hasattr(self, "_lock_status") and self._lock_status is not None:
            self._lock_status.setText("● Active")
            self._lock_status.setStyleSheet("color: #FF5B06; font-size: 12px; font-weight: 500;")
        if hasattr(self, "_lock_activate_btn") and self._lock_activate_btn is not None:
            self._lock_activate_btn.setText("  Lock Screen Active...")
            self._lock_activate_btn.clearFocus()
            self.setFocus()
            self._lock_activate_btn.setEnabled(False)
        
        # Poll for deactivation
        if not hasattr(self, "_lock_poll_timer") or self._lock_poll_timer is None:
            self._lock_poll_timer = QTimer(self)
            self._lock_poll_timer.setInterval(500)
            self._lock_poll_timer.timeout.connect(self._check_lock_status)
        if not self._lock_poll_timer.isActive():
            self._lock_poll_timer.start()
    
    def _check_lock_status(self):
        """Check if lock screen is still active."""
        if not InvisibleLockScreen.is_active():
            if hasattr(self, "_lock_poll_timer") and self._lock_poll_timer is not None:
                self._lock_poll_timer.stop()
            if hasattr(self, "_lock_status") and self._lock_status is not None:
                self._lock_status.setText("● Inactive")
                self._lock_status.setStyleSheet("color: #888888; font-size: 12px; font-weight: 500;")
            if hasattr(self, "_lock_activate_btn") and self._lock_activate_btn is not None:
                self._lock_activate_btn.setText("  Activate Lock Screen")
                self._lock_activate_btn.setEnabled(True)
                self._lock_activate_btn.clearFocus()
            self._hide_lock_overlay()
    
    def _update_toggle_button_ui(self, is_paused):
        """Update the toggle button appearance based on paused state."""
        if is_paused:
            self._toggle_update_btn.setText("  Resume Updates")
            self._toggle_update_btn.setStyleSheet(self._wu_secondary_btn_style)
            self._toggle_update_btn.setObjectName("helrcusToggleUpdateBtn")
            if hasattr(self, '_wu_resume_icon_path') and os.path.exists(self._wu_resume_icon_path):
                self._toggle_update_btn.setIcon(QIcon(self._wu_resume_icon_path))
                self._toggle_update_btn.setIconSize(QSize(16, 16))
        else:
            self._toggle_update_btn.setText("  Pause Updates")
            self._toggle_update_btn.setStyleSheet(self._wu_primary_btn_style)
            self._toggle_update_btn.setObjectName("helrcusToggleUpdateBtn")
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
            
            from datetime import datetime, timedelta
            # Set time to 23:59:59 so updates are paused through the end of that day
            target_date = datetime(year, month, day, 23, 59, 59)
            
            now = datetime.now()
            min_date = now + timedelta(days=29)   # Minimum 30 days from today
            
            if target_date < min_date:
                raise ValueError("Pause date must be at least 30 days from today.")
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
        is_checked = bool(state)
        if is_checked:
            success, msg = WindowsUpdateControl.disable_auto_restart()
        else:
            success, msg = WindowsUpdateControl.enable_auto_restart()
        
        self._config["windows_update"]["disable_auto_restart"] = is_checked
        self._save_config()
        self._update_active_hours_state(is_checked, animate=True)
        
        if hasattr(self, "_update_status") and self._update_status is not None:
            if success:
                status_text = "● Auto-restart disabled (NoAutoRebootWithLoggedOnUsers = 1)" if is_checked else "● Auto-restart enabled (policy removed)"
                self._update_status.setText(status_text)
                self._update_status.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: 500;")
            else:
                self._update_status.setText(f"● Error updating auto-restart policy: {msg}")
                self._update_status.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 500;")

    def _update_active_hours_state(self, is_no_restart: bool, animate: bool = True):
        """Update Active Hours container opacity and interaction when auto-restart is disabled."""
        if not hasattr(self, "_active_hours_container") or not hasattr(self, "_active_hours_opacity"):
            return
        
        target_opacity = 0.35 if is_no_restart else 1.0
        self._active_hours_container.setEnabled(not is_no_restart)
        
        if is_no_restart:
            self._active_hours_container.setToolTip("Active hours are bypassed because automatic restart is disabled.")
        else:
            self._active_hours_container.setToolTip("")
            
        if not animate:
            self._active_hours_opacity.setOpacity(target_opacity)
            return
            
        if not hasattr(self, "_active_hours_anim") or self._active_hours_anim is None:
            self._active_hours_anim = QPropertyAnimation(self._active_hours_opacity, b"opacity", self)
            self._active_hours_anim.setDuration(220)
            self._active_hours_anim.setEasingCurve(QEasingCurve.OutCubic)
            
        self._active_hours_anim.stop()
        self._active_hours_anim.setStartValue(self._active_hours_opacity.opacity())
        self._active_hours_anim.setEndValue(target_opacity)
        self._active_hours_anim.start()
    
    def _on_hours_preset_changed(self, index):
        """Handle active hours preset changes."""
        preset = self._hours_preset_combo.currentText()
        self._custom_hours_widget.setVisible(preset == "Customize")
        
    @staticmethod
    def _setup_time_combo_behavior(combo, sel_palette):
        """Setup segmented HH:MM time mask line edit for combo box."""
        current_val = combo.currentText()
        time_mask_edit = TimeMaskLineEdit(combo)
        time_mask_edit.setObjectName("timeMaskLineEdit")
        combo.setLineEdit(time_mask_edit)
        
        line_edit = combo.lineEdit()
        if current_val:
            line_edit.setText(current_val)
        line_edit.setAlignment(Qt.AlignCenter)
        line_edit.setPalette(sel_palette)
        line_edit.setMaxLength(5)
        
        def on_editing_finished():
            txt = line_edit.text().strip()
            if not txt or len(txt) != 5 or txt[2] != ':':
                txt = "00:00"
            else:
                parts = txt.split(":")
                try:
                    h = max(0, min(23, int(parts[0])))
                    m = max(0, min(59, int(parts[1])))
                    txt = f"{h:02d}:{m:02d}"
                except ValueError:
                    txt = "00:00"
                    
            line_edit.setText(txt)
            matching_idx = combo.findText(txt)
            if matching_idx >= 0:
                combo.setCurrentIndex(matching_idx)

        line_edit.editingFinished.connect(on_editing_finished)

        # Setup combo popup view and its vertical scrollbar
        view = combo.view()
        if view is not None:
            combo_name = combo.objectName() or "timeCombo"
            view.setObjectName(f"{combo_name}View")
            vbar = view.verticalScrollBar()
            if vbar is not None:
                vbar.setObjectName(f"{combo_name}ScrollBar")
                vbar.setStyleSheet("""
                    QScrollBar:vertical {
                        background: transparent;
                        width: 6px;
                        margin: 4px 2px 4px 0px;
                        border: none;
                    }
                    QScrollBar::handle:vertical {
                        background: rgba(255, 255, 255, 0.2);
                        min-height: 24px;
                        border-radius: 3px;
                        border: none;
                    }
                    QScrollBar::handle:vertical:hover {
                        background: #FF5B06;
                    }
                    QScrollBar::handle:vertical:pressed {
                        background: #FDA903;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
                    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                        height: 0px;
                        width: 0px;
                        background: transparent;
                        border: none;
                    }
                """)

    @staticmethod
    def _parse_hour(combo):
        """Parse hour integer (0-23) from a combo box whether selected or typed manually."""
        idx = combo.currentIndex()
        if idx >= 0:
            return idx % 24
        txt = combo.currentText().strip()
        if not txt:
            return 0
        try:
            if ":" in txt:
                txt = txt.split(":")[0]
            val = int(txt)
            return max(0, min(23, val))
        except ValueError:
            return 0

    def _apply_active_hours(self):
        """Apply active hours setting based on preset or custom values."""
        preset = self._hours_preset_combo.currentText()
        
        if preset in ("Always Active", "Always Active (Max 18h)"):
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
            start = self._parse_hour(self._hours_start)
            end = self._parse_hour(self._hours_end)
            
        success, msg = WindowsUpdateControl.set_active_hours(start, end)
        
        if hasattr(self, "_update_status") and self._update_status is not None:
            if success:
                display_end = "00:00" if end == 0 else f"{end:02d}:00"
                self._update_status.setText(f"● Active hours applied: {start:02d}:00 - {display_end} (Max 18h)")
                self._update_status.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: 500;")
            else:
                self._update_status.setText(f"● Error applying active hours: {msg}")
                self._update_status.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 500;")
        
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
            if hasattr(self, "_lock_status") and self._lock_status is not None:
                self._lock_status.setText("● Active")
                self._lock_status.setStyleSheet("color: #FF5B06; font-size: 12px; font-weight: 500;")
            if hasattr(self, "_lock_activate_btn") and self._lock_activate_btn is not None:
                self._lock_activate_btn.setText("  Lock Screen Active...")
                self._lock_activate_btn.clearFocus()
                self._lock_activate_btn.setEnabled(False)

        # Synchronize auto-restart checkbox with actual Windows Registry state
        if hasattr(self, "_no_restart_cb") and self._no_restart_cb is not None:
            reg_disabled = WindowsUpdateControl.get_auto_restart_status()
            cfg_disabled = self._config["windows_update"].get("disable_auto_restart", False)
            
            # If config is True but registry key is missing, enforce it into registry
            if cfg_disabled and not reg_disabled:
                WindowsUpdateControl.disable_auto_restart()
                reg_disabled = True
            elif not cfg_disabled and reg_disabled:
                self._config["windows_update"]["disable_auto_restart"] = True
                self._save_config()
                cfg_disabled = True
                
            effective_state = bool(cfg_disabled or reg_disabled)
            self._no_restart_cb.setChecked(effective_state)
            self._update_active_hours_state(effective_state, animate=False)

    def _register_global_hotkey(self):
        """Register the global activation hotkey."""
        self._unregister_global_hotkey()
        
        # Check module_settings for startup_hotkeys
        if not self._config.get("module_settings", {}).get("startup_hotkeys", True):
            print("[HELRCUS] Global hotkey registration disabled in module settings.")
            return
        
        hotkey_str = self._config["lock_screen"].get("hotkey", "Ctrl+Alt+L")
        modifiers, vk_code = _parse_hotkey_string(hotkey_str)
        
        if modifiers is not None and vk_code is not None:
            top_win = self.window()
            hwnd = int(top_win.winId()) if top_win is not None else int(self.winId())
            user32 = ctypes.windll.user32
            self._activation_hotkey_id = 54321
            self._registered_hotkey_hwnd = hwnd
            
            # MOD_NOREPEAT (0x4000) prevents key auto-repeat spam
            MOD_NOREPEAT = 0x4000
            fs_modifiers = modifiers | MOD_NOREPEAT
            success = user32.RegisterHotKey(hwnd, self._activation_hotkey_id, fs_modifiers, vk_code)
            if not success:
                # Fallback without MOD_NOREPEAT
                success = user32.RegisterHotKey(hwnd, self._activation_hotkey_id, modifiers, vk_code)
                
            if not success:
                print(f"[HELRCUS] Failed to register global activation hotkey: {hotkey_str} on HWND {hex(hwnd)}")
            else:
                print(f"[HELRCUS] Registered global activation hotkey: {hotkey_str} on HWND {hex(hwnd)}")

            # Install application-level native event filter
            app = QApplication.instance()
            if app is not None and self._native_hotkey_filter is None:
                self._native_hotkey_filter = HelrcusGlobalHotkeyEventFilter(self)
                app.installNativeEventFilter(self._native_hotkey_filter)
                print("[HELRCUS] Installed HelrcusGlobalHotkeyEventFilter on QApplication.")

    def _unregister_global_hotkey(self):
        """Unregister the global activation hotkey and clean up native filter."""
        if hasattr(self, "_activation_hotkey_id"):
            hwnd = getattr(self, "_registered_hotkey_hwnd", None)
            if hwnd is None:
                top_win = self.window()
                hwnd = int(top_win.winId()) if top_win is not None else int(self.winId())
            try:
                user32 = ctypes.windll.user32
                user32.UnregisterHotKey(hwnd, self._activation_hotkey_id)
            except Exception:
                pass
                
        if getattr(self, "_native_hotkey_filter", None) is not None:
            try:
                app = QApplication.instance()
                if app is not None:
                    app.removeNativeEventFilter(self._native_hotkey_filter)
            except Exception:
                pass
            self._native_hotkey_filter = None

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
        """Handle native Windows events for global hotkeys (Layer 2 backup)."""
        try:
            msg_ptr = int(message)
            msg = ctypes.wintypes.MSG.from_address(msg_ptr)
            if msg.message == 0x0312:  # WM_HOTKEY
                if hasattr(self, "_activation_hotkey_id") and msg.wParam == self._activation_hotkey_id:
                    self._activate_lock_screen()
                    return True, 0
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        """Clean up hotkeys, event filter, and timers when window is closed."""
        if hasattr(self, "_lock_poll_timer") and self._lock_poll_timer is not None:
            self._lock_poll_timer.stop()
        self._unregister_global_hotkey()
        super().closeEvent(event)
