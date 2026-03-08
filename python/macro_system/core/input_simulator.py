"""
Input Simulator Module

Low-level input injection for mouse and keyboard simulation.
Uses Windows SendInput API for reliable, low-latency simulation.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import time


# Windows input types
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Mouse event flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# X button identifiers
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002

# Keyboard event flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]


# Virtual key codes
VK_CODES = {
    # Modifiers
    "ctrl": 0x11, "lctrl": 0xA2, "rctrl": 0xA3,
    "shift": 0x10, "lshift": 0xA0, "rshift": 0xA1,
    "alt": 0x12, "lalt": 0xA4, "ralt": 0xA5,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    
    # Function keys
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    
    # Navigation
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E,
    
    # Special
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
    "printscreen": 0x2C, "pause": 0x13,
    
    # Numpad
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63,
    "num4": 0x64, "num5": 0x65, "num6": 0x66, "num7": 0x67,
    "num8": 0x68, "num9": 0x69,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D,
    "decimal": 0x6E, "divide": 0x6F,
    
    # Media
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "medianext": 0xB0, "mediaprev": 0xB1, "mediastop": 0xB2,
    "mediaplaypause": 0xB3,
}

# Extended key codes (require KEYEVENTF_EXTENDEDKEY)
EXTENDED_KEYS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # Navigation
    0x2D, 0x2E,  # Insert, Delete
    0x5B, 0x5C,  # Win keys
    0x6F,  # Numpad divide
    0xA3, 0xA5,  # Right Ctrl, Right Alt
}


class InputSimulator:
    """
    Low-latency input simulation using Windows SendInput API.
    
    Supports:
    - Mouse clicks, movement, scrolling
    - Keyboard keys and combinations
    - Precise timing between actions
    """
    
    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._extra_info = ctypes.pointer(ctypes.c_ulong(0))
        
        # Screen dimensions for absolute positioning
        self._screen_width = self._user32.GetSystemMetrics(0)
        self._screen_height = self._user32.GetSystemMetrics(1)
        
    def _send_input(self, inputs: List[INPUT]) -> int:
        """Send input events using Windows SendInput."""
        n_inputs = len(inputs)
        array_type = INPUT * n_inputs
        input_array = array_type(*inputs)
        
        return self._user32.SendInput(
            n_inputs,
            ctypes.byref(input_array),
            ctypes.sizeof(INPUT)
        )
        
    # ==================== MOUSE ====================
    
    def mouse_move(self, x: int, y: int, absolute: bool = True):
        """Move mouse to position."""
        flags = MOUSEEVENTF_MOVE
        
        if absolute:
            flags |= MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            # Convert to normalized coordinates (0-65535)
            x = int(x * 65535 / self._screen_width)
            y = int(y * 65535 / self._screen_height)
            
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = x
        inp.union.mi.dy = y
        inp.union.mi.dwFlags = flags
        inp.union.mi.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def mouse_move_relative(self, dx: int, dy: int):
        """Move mouse by relative offset."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = dx
        inp.union.mi.dy = dy
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE
        inp.union.mi.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def mouse_down(self, button: str = "left"):
        """Press mouse button down."""
        flags, data = self._get_mouse_button_flags(button, down=True)
        
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = flags
        inp.union.mi.mouseData = data
        inp.union.mi.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def mouse_up(self, button: str = "left"):
        """Release mouse button."""
        flags, data = self._get_mouse_button_flags(button, down=False)
        
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = flags
        inp.union.mi.mouseData = data
        inp.union.mi.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def mouse_click(self, button: str = "left", count: int = 1, interval_ms: int = 50):
        """Click mouse button."""
        for i in range(count):
            self.mouse_down(button)
            # Minimal delay - SendInput is fast enough
            self.mouse_up(button)
            
            if i < count - 1:
                time.sleep(interval_ms / 1000)
                
    def mouse_scroll(self, delta: int, horizontal: bool = False):
        """Scroll mouse wheel. Positive = up/right, negative = down/left."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
        inp.union.mi.mouseData = delta * 120  # 120 = one notch
        inp.union.mi.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def _get_mouse_button_flags(self, button: str, down: bool) -> Tuple[int, int]:
        """Get mouse event flags for button."""
        button = button.lower()
        
        if button == "left":
            return (MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP, 0)
        elif button == "right":
            return (MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP, 0)
        elif button == "middle":
            return (MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP, 0)
        elif button == "x1":
            return (MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP, XBUTTON1)
        elif button == "x2":
            return (MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP, XBUTTON2)
        else:
            raise ValueError(f"Unknown mouse button: {button}")
            
    # ==================== KEYBOARD ====================
    
    def key_down(self, key: str):
        """Press key down."""
        vk = self._get_vk_code(key)
        flags = KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_KEYS else 0
        
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = flags
        inp.union.ki.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def key_up(self, key: str):
        """Release key."""
        vk = self._get_vk_code(key)
        flags = KEYEVENTF_KEYUP
        if vk in EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY
            
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = flags
        inp.union.ki.dwExtraInfo = self._extra_info
        
        self._send_input([inp])
        
    def key_tap(self, key: str, hold_ms: int = 0):
        """Press and release a key."""
        self.key_down(key)
        if hold_ms > 0:
            time.sleep(hold_ms / 1000)
        # No delay if hold_ms is 0 - SendInput is fast enough
        self.key_up(key)
        
    def key_combo(self, *keys: str, hold_ms: int = 0):
        """
        Press a key combination (e.g., Ctrl+Shift+A).
        Keys are pressed in order and released in reverse order.
        """
        # Press all keys
        for key in keys:
            self.key_down(key)
            
        if hold_ms > 0:
            time.sleep(hold_ms / 1000)
            
        # Release in reverse order
        for key in reversed(keys):
            self.key_up(key)
            
    def type_text(self, text: str, interval_ms: int = 0):
        """Type a string of text using Unicode input."""
        for char in text:
            # Use Unicode input for accurate typing
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.union.ki.wVk = 0
            down.union.ki.wScan = ord(char)
            down.union.ki.dwFlags = KEYEVENTF_UNICODE
            down.union.ki.dwExtraInfo = self._extra_info
            
            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.union.ki.wVk = 0
            up.union.ki.wScan = ord(char)
            up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            up.union.ki.dwExtraInfo = self._extra_info
            
            self._send_input([down, up])
            
            if interval_ms > 0:
                time.sleep(interval_ms / 1000)
                
    def _get_vk_code(self, key: str) -> int:
        """Convert key name to virtual key code."""
        key = key.lower().strip()
        
        # Check named keys
        if key in VK_CODES:
            return VK_CODES[key]
            
        # Single character
        if len(key) == 1:
            code = ord(key.upper())
            # Letters A-Z
            if 0x41 <= code <= 0x5A:
                return code
            # Numbers 0-9
            if 0x30 <= code <= 0x39:
                return code
                
        # Try parsing as vkXX
        if key.startswith("vk"):
            try:
                return int(key[2:])
            except ValueError:
                pass
                
        raise ValueError(f"Unknown key: {key}")
        
    # ==================== UTILITY ====================
    
    def get_cursor_position(self) -> Tuple[int, int]:
        """Get current cursor position."""
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            
        pt = POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)
        
    def is_key_pressed(self, key: str) -> bool:
        """Check if a key is currently pressed."""
        vk = self._get_vk_code(key)
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)
        
    def is_mouse_button_pressed(self, button: str = "left") -> bool:
        """Check if a mouse button is currently pressed."""
        vk_map = {
            "left": 0x01,
            "right": 0x02,
            "middle": 0x04,
            "x1": 0x05,
            "x2": 0x06,
        }
        vk = vk_map.get(button.lower(), 0x01)
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)
