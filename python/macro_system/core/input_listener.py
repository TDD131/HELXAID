"""
Input Listener Module

Low-level mouse and keyboard input capture with event suppression support.
Uses pynput for cross-platform compatibility with Windows hooks for suppression.
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Set, Dict, Any
from queue import Queue
import ctypes
from ctypes import wintypes
from ..integration.native_bridge import NativeInputHook, is_native_available

# Windows constants for low-level hooks
WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Button constants
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002


class MouseButton(Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"
    X1 = "x1"
    X2 = "x2"


class EventType(Enum):
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    MOUSE_MOVE = "mouse_move"
    MOUSE_SCROLL = "mouse_scroll"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"


@dataclass
class MouseEvent:
    """Mouse input event data."""
    type: EventType
    button: Optional[MouseButton] = None
    x: int = 0
    y: int = 0
    delta: int = 0  # Scroll delta
    timestamp: float = field(default_factory=time.time)
    suppressed: bool = False
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass  
class KeyboardEvent:
    """Keyboard input event data."""
    type: EventType
    key_code: int = 0
    scan_code: int = 0
    key_name: str = ""
    timestamp: float = field(default_factory=time.time)
    suppressed: bool = False
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class InputEvent:
    """Unified input event wrapper."""
    mouse: Optional[MouseEvent] = None
    keyboard: Optional[KeyboardEvent] = None
    
    @property
    def is_mouse(self) -> bool:
        return self.mouse is not None
    
    @property
    def is_keyboard(self) -> bool:
        return self.keyboard is not None
    
    @property
    def timestamp(self) -> float:
        if self.mouse:
            return self.mouse.timestamp
        if self.keyboard:
            return self.keyboard.timestamp
        return time.time()


# Windows structures for hooks
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


# Hook procedure type
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class InputListener:
    """
    Low-level input listener with event suppression capability.
    
    Uses Windows low-level hooks for mouse/keyboard capture.
    Supports suppressing specific inputs for remapping.
    """
    
    # Injected event marker (to ignore our own simulated inputs)
    INJECTED_FLAG = 0x00000001
    INJECTED_LOWER = 0x00000002
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Callbacks
        self._on_mouse: Optional[Callable[[MouseEvent], bool]] = None
        self._on_keyboard: Optional[Callable[[KeyboardEvent], bool]] = None
        
        # Suppression state
        self._suppress_buttons: Set[MouseButton] = set()
        self._suppress_keys: Set[int] = set()
        self._suppress_next_up: Dict[str, bool] = {}
        
        # Modifier state tracking (cached to avoid expensive GetAsyncKeyState calls in hook)
        self._modifiers = {
            "ctrl": False, "shift": False, "alt": False,
            "lctrl": False, "rctrl": False, "lshift": False,
            "rshift": False, "lalt": False, "ralt": False, "win": False
        }
        
        # Hook handles
        self._mouse_hook = None
        self._keyboard_hook = None
        
        # Performance optimization: skip MOUSE_MOVE events unless requested
        self.listen_to_move = False
        
        # Keep references to prevent garbage collection
        self._mouse_proc = None
        self._keyboard_proc = None
        self._current_native_event = None
        
        # Native hook
        self._native_hook: Optional[NativeInputHook] = None
        if is_native_available():
            self._native_hook = NativeInputHook()
        
        # Event queue for thread-safe processing
        self._event_queue: Queue = Queue()
        
        # Windows API with proper prototypes
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        
        # Setup function prototypes for proper type handling
        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,      # idHook
            HOOKPROC,          # lpfn
            wintypes.HINSTANCE, # hmod
            wintypes.DWORD     # dwThreadId
        ]
        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        
        self._user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM
        ]
        self._user32.CallNextHookEx.restype = ctypes.c_long
        
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        
        self._user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT
        ]
        self._user32.GetMessageW.restype = wintypes.BOOL
        
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        
    @property
    def on_mouse_event(self) -> Optional[Callable[[MouseEvent], bool]]:
        return self._on_mouse
    
    @on_mouse_event.setter
    def on_mouse_event(self, callback: Callable[[MouseEvent], bool]):
        """Set mouse event callback. Return True to suppress the event."""
        self._on_mouse = callback
        
    @property
    def on_keyboard_event(self) -> Optional[Callable[[KeyboardEvent], bool]]:
        return self._on_keyboard
    
    @on_keyboard_event.setter
    def on_keyboard_event(self, callback: Callable[[KeyboardEvent], bool]):
        """Set keyboard event callback. Return True to suppress the event."""
        self._on_keyboard = callback
        
    def suppress_button(self, button: MouseButton, suppress: bool = True):
        """Add or remove a mouse button from suppression list."""
        if suppress:
            self._suppress_buttons.add(button)
        else:
            self._suppress_buttons.discard(button)
            
    @property
    def current_native_event(self) -> Any:
        """Get the native C++ event being processed (if any)."""
        return self._current_native_event
            
    def suppress_key(self, key_code: int, suppress: bool = True):
        """Add or remove a key from suppression list."""
        if suppress:
            self._suppress_keys.add(key_code)
        else:
            self._suppress_keys.discard(key_code)
            
    def suppress_next_release(self, identifier: str):
        """Suppress the next button/key release for this identifier."""
        self._suppress_next_up[identifier] = True
        
    def start(self):
        """Start listening for input events."""
        if self._running:
            return
            
        self._running = True
        
        if self._native_hook:
            print("[InputListener] Starting native C++ hook")
            try:
                # Map native C++ callbacks to Python handlers
                self._native_hook.set_listen_to_move(self.listen_to_move)
                self._native_hook.set_mouse_callback(self._native_mouse_callback)
                self._native_hook.set_keyboard_callback(self._native_keyboard_callback)
                
                self._native_hook.start()
                
                # Check if it's actually running
                if self._native_hook.is_running():
                    print("[InputListener] Native hook started successfully")
                    return
                else:
                    print("[InputListener] Native hook failed to start (is_running=False), falling back to Python")
            except Exception as e:
                print(f"[InputListener] Error starting native hook: {e}, falling back to Python")

        self._thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop listening for input events."""
        self._running = False
        
        if self._native_hook:
            self._native_hook.stop()
        
        # Post quit message to hook thread
        if self._thread and self._thread.is_alive():
            self._user32.PostThreadMessageW(
                self._thread.ident,
                0x0012,  # WM_QUIT
                0, 0
            )
            self._thread.join(timeout=1.0)
            
        self._unhook()
        
    def _hook_thread(self):
        """Thread function that installs and runs the hooks."""
        try:
            self._install_hooks()
            
            # Message loop
            msg = wintypes.MSG()
            while self._running:
                result = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                self._user32.TranslateMessage(ctypes.byref(msg))
                self._user32.DispatchMessageW(ctypes.byref(msg))
                
        finally:
            self._unhook()
            
    def _install_hooks(self):
        """Install low-level mouse and keyboard hooks."""
        # Create hook procedures
        self._mouse_proc = HOOKPROC(self._mouse_hook_proc)
        self._keyboard_proc = HOOKPROC(self._keyboard_hook_proc)
        
        # Get module handle (None = current process)
        h_module = self._kernel32.GetModuleHandleW(None)
        
        # Try to install mouse hook
        for attempt in range(3):
            self._mouse_hook = self._user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                self._mouse_proc,
                h_module,
                0
            )
            if self._mouse_hook:
                break
            time.sleep(0.1)
        
        # Try to install keyboard hook
        for attempt in range(3):
            self._keyboard_hook = self._user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._keyboard_proc,
                h_module,
                0
            )
            if self._keyboard_hook:
                break
            time.sleep(0.1)
        
        # Check results
        if not self._mouse_hook and not self._keyboard_hook:
            error_code = self._kernel32.GetLastError()
            error_msg = f"Failed to install input hooks (error code: {error_code})"
            print(f"[InputListener] {error_msg}")
            # Don't raise - allow partial functionality
            if not self._mouse_hook:
                print("[InputListener] Warning: Mouse hook not installed")
            if not self._keyboard_hook:
                print("[InputListener] Warning: Keyboard hook not installed")
        else:
            print(f"[InputListener] Hooks installed (mouse: {bool(self._mouse_hook)}, keyboard: {bool(self._keyboard_hook)})")
            
    def _unhook(self):
        """Remove installed hooks."""
        if self._mouse_hook:
            self._user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
            
        if self._keyboard_hook:
            self._user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
            
    def _mouse_hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        """Low-level mouse hook procedure."""
        if n_code >= 0 and self._running:
            data = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            
            # Check if this is an injected event (our own simulation)
            if data.flags & (self.INJECTED_FLAG | self.INJECTED_LOWER):
                return self._user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)
            
            # PERFORMANCE OPTIMIZATION: Skip mouse move events if not requested.
            # Processing every pixel of movement in a low-level hook can cause hardware lag.
            if w_param == WM_MOUSEMOVE and not self.listen_to_move:
                return self._user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)
            
            event = self._parse_mouse_event(w_param, data)
            if event:
                suppress = self._handle_mouse_event(event)
                if suppress:
                    return 1  # Block the event
                    
        return self._user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)
        
    def _keyboard_hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        """Low-level keyboard hook procedure."""
        if n_code >= 0 and self._running:
            data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            
            # FAST TRACK: Update modifier state regardless of injection
            self._update_modifier_state(w_param, data.vkCode)
            
            # Check if this is an injected event
            if data.flags & (self.INJECTED_FLAG | self.INJECTED_LOWER):
                return self._user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param)
            
            # FAST TRACK: Check for direct suppression before parsing
            if data.vkCode in self._suppress_keys:
                return 1
            
            event = self._parse_keyboard_event(w_param, data)
            if event:
                suppress = self._handle_keyboard_event(event)
                if suppress:
                    return 1  # Block the event
                    
        return self._user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param)

    def _update_modifier_state(self, w_param: int, vk_code: int):
        """Update cached modifier state from hook data."""
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        self._set_modifier_state(vk_code, is_down)

    def _set_modifier_state(self, vk_code: int, is_down: bool):
        """Internal helper to set modifier state bits."""
        if vk_code in (0x10, 0xA0, 0xA1): # SHIFT
            self._modifiers["shift"] = is_down
            if vk_code == 0xA0: self._modifiers["lshift"] = is_down
            elif vk_code == 0xA1: self._modifiers["rshift"] = is_down
        elif vk_code in (0x11, 0xA2, 0xA3): # CTRL
            self._modifiers["ctrl"] = is_down
            if vk_code == 0xA2: self._modifiers["lctrl"] = is_down
            elif vk_code == 0xA3: self._modifiers["rctrl"] = is_down
        elif vk_code in (0x12, 0xA4, 0xA5): # ALT
            self._modifiers["alt"] = is_down
            if vk_code == 0xA4: self._modifiers["lalt"] = is_down
            elif vk_code == 0xA5: self._modifiers["ralt"] = is_down
        elif vk_code in (0x5B, 0x5C): # WIN
            self._modifiers["win"] = is_down

    def _native_mouse_callback(self, native_ev) -> bool:
        """Handler for native C++ mouse events."""
        from ..integration.native_bridge import _native
        # Map native button enum to Python enum
        button_map = {
            _native.MouseButton.Left: MouseButton.LEFT,
            _native.MouseButton.Right: MouseButton.RIGHT,
            _native.MouseButton.Middle: MouseButton.MIDDLE,
            _native.MouseButton.X1: MouseButton.X1,
            _native.MouseButton.X2: MouseButton.X2
        }
        
        self._current_native_event = native_ev
        
        # Determine event type based on native EventType enum
        ev_type = EventType.MOUSE_MOVE
        if native_ev.type == _native.EventType.MouseDown:
            ev_type = EventType.MOUSE_DOWN
        elif native_ev.type == _native.EventType.MouseUp:
            ev_type = EventType.MOUSE_UP
        elif native_ev.type == _native.EventType.MouseScroll:
            ev_type = EventType.MOUSE_SCROLL

        event = MouseEvent(
            type=ev_type,
            button=button_map.get(native_ev.button, None),
            x=native_ev.x,
            y=native_ev.y,
            delta=native_ev.delta,
            timestamp=native_ev.timestamp / 1000000.0 # Convert microseconds to seconds
        )
        try:
            return self._handle_mouse_event(event)
        finally:
            self._current_native_event = None

    def _native_keyboard_callback(self, native_ev) -> bool:
        """Handler for native C++ keyboard events."""
        from ..integration.native_bridge import _native
        is_down = (native_ev.type == _native.EventType.KeyDown)
        
        # Update modifier state
        self._set_modifier_state(native_ev.vk_code, is_down)
        
        self._current_native_event = native_ev
        event = KeyboardEvent(
            type=EventType.KEY_DOWN if is_down else EventType.KEY_UP,
            key_code=native_ev.vk_code,
            key_name=self._vk_to_name(native_ev.vk_code),
            timestamp=native_ev.timestamp / 1000000.0
        )
        try:
            return self._handle_keyboard_event(event)
        finally:
            self._current_native_event = None
        
    def _parse_mouse_event(self, w_param: int, data: MSLLHOOKSTRUCT) -> Optional[MouseEvent]:
        """Parse mouse hook data into MouseEvent."""
        event_type = None
        button = None
        delta = 0
        
        if w_param == WM_LBUTTONDOWN:
            event_type = EventType.MOUSE_DOWN
            button = MouseButton.LEFT
        elif w_param == WM_LBUTTONUP:
            event_type = EventType.MOUSE_UP
            button = MouseButton.LEFT
        elif w_param == WM_RBUTTONDOWN:
            event_type = EventType.MOUSE_DOWN
            button = MouseButton.RIGHT
        elif w_param == WM_RBUTTONUP:
            event_type = EventType.MOUSE_UP
            button = MouseButton.RIGHT
        elif w_param == WM_MBUTTONDOWN:
            event_type = EventType.MOUSE_DOWN
            button = MouseButton.MIDDLE
        elif w_param == WM_MBUTTONUP:
            event_type = EventType.MOUSE_UP
            button = MouseButton.MIDDLE
        elif w_param == WM_XBUTTONDOWN:
            event_type = EventType.MOUSE_DOWN
            hi_word = (data.mouseData >> 16) & 0xFFFF
            button = MouseButton.X1 if hi_word == XBUTTON1 else MouseButton.X2
        elif w_param == WM_XBUTTONUP:
            event_type = EventType.MOUSE_UP
            hi_word = (data.mouseData >> 16) & 0xFFFF
            button = MouseButton.X1 if hi_word == XBUTTON1 else MouseButton.X2
        elif w_param == WM_MOUSEWHEEL:
            event_type = EventType.MOUSE_SCROLL
            delta = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
        elif w_param == WM_MOUSEMOVE:
            event_type = EventType.MOUSE_MOVE
        else:
            return None
            
        return MouseEvent(
            type=event_type,
            button=button,
            x=data.pt.x,
            y=data.pt.y,
            delta=delta
        )
        
    def _parse_keyboard_event(self, w_param: int, data: KBDLLHOOKSTRUCT) -> Optional[KeyboardEvent]:
        """Parse keyboard hook data into KeyboardEvent."""
        if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            event_type = EventType.KEY_DOWN
        elif w_param in (WM_KEYUP, WM_SYSKEYUP):
            event_type = EventType.KEY_UP
        else:
            return None
            
        # Get key name
        key_name = self._vk_to_name(data.vkCode)
        
        return KeyboardEvent(
            type=event_type,
            key_code=data.vkCode,
            scan_code=data.scanCode,
            key_name=key_name
        )
        
    def _vk_to_name(self, vk_code: int) -> str:
        """Convert virtual key code to key name."""
        # Common key mappings
        VK_NAMES = {
            0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "shift",
            0x11: "ctrl", 0x12: "alt", 0x13: "pause", 0x14: "capslock",
            0x1B: "esc", 0x20: "space", 0x21: "pageup", 0x22: "pagedown",
            0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up",
            0x27: "right", 0x28: "down", 0x2C: "printscreen", 0x2D: "insert",
            0x2E: "delete", 0x5B: "lwin", 0x5C: "rwin",
            0x70: "f1", 0x71: "f2", 0x72: "f3", 0x73: "f4",
            0x74: "f5", 0x75: "f6", 0x76: "f7", 0x77: "f8",
            0x78: "f9", 0x79: "f10", 0x7A: "f11", 0x7B: "f12",
            0xA0: "lshift", 0xA1: "rshift", 0xA2: "lctrl", 0xA3: "rctrl",
            0xA4: "lalt", 0xA5: "ralt",
        }
        
        if vk_code in VK_NAMES:
            return VK_NAMES[vk_code]
        elif 0x30 <= vk_code <= 0x39:  # 0-9
            return chr(vk_code)
        elif 0x41 <= vk_code <= 0x5A:  # A-Z
            return chr(vk_code).lower()
        elif 0x60 <= vk_code <= 0x69:  # Numpad 0-9
            return f"num{vk_code - 0x60}"
        else:
            return f"vk{vk_code}"
            
    def _handle_mouse_event(self, event: MouseEvent) -> bool:
        """Handle mouse event and determine if it should be suppressed."""
        # Check if button is in suppression list
        if event.button and event.button in self._suppress_buttons:
            event.suppressed = True
            
        # Check for next-release suppression
        if event.type == EventType.MOUSE_UP and event.button:
            key = f"mouse_{event.button.value}"
            if self._suppress_next_up.pop(key, False):
                event.suppressed = True
                
        # Call user callback
        if self._on_mouse:
            try:
                if self._on_mouse(event):
                    event.suppressed = True
            except Exception as e:
                print(f"[MacroSystem] Mouse callback error: {e}")
                
        return event.suppressed
        
    def _handle_keyboard_event(self, event: KeyboardEvent) -> bool:
        """Handle keyboard event and determine if it should be suppressed."""
        # Check if key is in suppression list
        if event.key_code in self._suppress_keys:
            event.suppressed = True
            
        # Check for next-release suppression
        if event.type == EventType.KEY_UP:
            key = f"key_{event.key_code}"
            if self._suppress_next_up.pop(key, False):
                event.suppressed = True
                
        # Call user callback
        if self._on_keyboard:
            try:
                if self._on_keyboard(event):
                    event.suppressed = True
            except Exception as e:
                print(f"[MacroSystem] Keyboard callback error: {e}")
                
        return event.suppressed
        
    def get_modifier_state(self) -> Dict[str, bool]:
        """Get cached state of modifier keys (fast)."""
        return self._modifiers.copy()
