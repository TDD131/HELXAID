"""
Global Media Key Service (Non-Exclusive)

Listens for hardware media key events (Play/Pause, Next, Previous, Stop)
from ALL input devices: laptop keyboard, Bluetooth headphones/earbuds,
USB media controllers, external keyboards, etc.

Uses Win32 SetWindowsHookEx with WH_KEYBOARD_LL to intercept media keys
globally WITHOUT stealing them from other applications. The key events
are forwarded to other apps (YouTube, Spotify, etc.) via CallNextHookEx,
so both HELXAID and other media apps can respond to the same key press.

Windows translates all media key input sources (keyboard Fn keys,
Bluetooth AVRCP protocol from headphones, USB HID media controls)
into the same virtual keycodes (VK_MEDIA_*), so a single hook
catches input from every device type.

Component Name: MediaKeyService
"""

import ctypes
import ctypes.wintypes
import threading
from PySide6.QtCore import QObject, Signal


# ============================================================
# Win32 Constants
# ============================================================

# Hook type: Low-level keyboard hook that monitors keystrokes
# before they reach any application. Non-exclusive by design
# when CallNextHookEx is called in the callback.
WH_KEYBOARD_LL = 13

# Key event message types
WM_KEYDOWN = 0x0100     # Standard key press
WM_KEYUP = 0x0101       # Standard key release
WM_SYSKEYDOWN = 0x0104  # System key press (Alt combinations)
WM_SYSKEYUP = 0x0105    # System key release

# Message loop control
WM_QUIT = 0x0012

# Media key virtual keycodes
# These are the SAME keycodes regardless of input source:
# - Laptop keyboard Fn+F7/F8/F9 (HP Victus 15)
# - Bluetooth headphone/earbuds buttons (AVRCP protocol)
# - USB media controllers
# - External keyboards with media keys
VK_MEDIA_PLAY_PAUSE = 0xB3  # Toggle play/pause
VK_MEDIA_NEXT_TRACK = 0xB0  # Next track / forward
VK_MEDIA_PREV_TRACK = 0xB1  # Previous track / backward
VK_MEDIA_STOP = 0xB2        # Stop playback

# Set of media key VK codes for fast lookup in the hook callback
_MEDIA_VK_CODES = {
    VK_MEDIA_PLAY_PAUSE,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PREV_TRACK,
    VK_MEDIA_STOP,
}


# ============================================================
# Win32 Structures and Types
# ============================================================

class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Low-level keyboard input event structure.
    
    Passed to the LowLevelKeyboardProc callback via lParam.
    Contains the virtual keycode and other key state info.
    """
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),      # Virtual-key code
        ("scanCode", ctypes.wintypes.DWORD),     # Hardware scan code
        ("flags", ctypes.wintypes.DWORD),        # Key event flags
        ("time", ctypes.wintypes.DWORD),         # Timestamp
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),  # Extra info
    ]

# Callback function type for SetWindowsHookEx
# LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,          # Return: LRESULT
    ctypes.c_int,           # nCode: hook code
    ctypes.wintypes.WPARAM, # wParam: message type (WM_KEYDOWN etc.)
    ctypes.wintypes.LPARAM  # lParam: pointer to KBDLLHOOKSTRUCT
)


class MediaKeyService(QObject):
    """
    Non-exclusive global media key listener using Win32 keyboard hook.

    Captures Play/Pause, Next, Previous, and Stop media key events
    from ALL input devices (keyboard, Bluetooth, USB) even when
    the application does not have focus.

    Unlike RegisterHotKey, this hook is NON-EXCLUSIVE: other apps
    (YouTube, Spotify, etc.) will also receive the media key events.
    This is achieved by always calling CallNextHookEx in the hook
    callback, which forwards the key event down the hook chain.

    Signals are emitted on the Qt main thread via automatic
    queued connection, making them safe to connect directly
    to GUI slot methods.

    Usage:
        service = MediaKeyService()
        service.play_pause.connect(music_panel._toggle_play)
        service.next_track.connect(music_panel._next_track)
        service.prev_track.connect(music_panel._prev_track)
        service.start()
        # ... later ...
        service.stop()

    Component Name: MediaKeyService
    """

    # Signals emitted when the corresponding media key is pressed.
    # Connected to MusicPanelWidget playback control methods.
    # Thread-safe: PySide6 auto-queues signals from non-GUI threads.
    play_pause = Signal()     # VK_MEDIA_PLAY_PAUSE (0xB3)
    next_track = Signal()     # VK_MEDIA_NEXT_TRACK (0xB0)
    prev_track = Signal()     # VK_MEDIA_PREV_TRACK (0xB1)
    stop_playback = Signal()  # VK_MEDIA_STOP (0xB2)

    def __init__(self, parent=None):
        """Initialize the media key service.

        Args:
            parent: Optional QObject parent for Qt ownership.
                    The service does NOT start automatically;
                    call start() explicitly.
        """
        super().__init__(parent)
        self._thread = None
        self._running = False
        self._thread_id = None  # Win32 thread ID for PostThreadMessageW
        self._hook_handle = None  # Handle from SetWindowsHookEx
        self._hook_proc = None  # Must keep reference to prevent GC

    def start(self):
        """Start listening for global media key events.

        Spawns a daemon background thread that installs a low-level
        keyboard hook and runs a Win32 GetMessage loop. The thread
        auto-terminates when the main application exits (daemon=True).

        Safe to call multiple times; subsequent calls are no-ops
        if the listener is already running.
        """
        if self._running:
            print("[MediaKeyService] Already running, skipping start")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._listen,
            name="MediaKeyService",
            daemon=True  # Auto-terminate when main thread exits
        )
        self._thread.start()
        print("[MediaKeyService] Started global media key listener (non-exclusive)")

    def stop(self):
        """Stop listening for media key events and clean up.

        Posts WM_QUIT to the listener thread's message queue to
        break the GetMessage loop, then waits for the thread to
        finish (with timeout). The keyboard hook is uninstalled
        inside the listener thread before it exits.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if not self._running:
            return

        self._running = False

        # Post WM_QUIT to break the GetMessage loop in the listener thread.
        # PostThreadMessageW is thread-safe and can be called from any thread.
        if self._thread_id is not None:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, WM_QUIT, 0, 0
                )
            except Exception as e:
                print(f"[MediaKeyService] Error posting quit message: {e}")

        # Wait for the listener thread to finish cleanup
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        self._thread_id = None
        print("[MediaKeyService] Stopped global media key listener")

    def _listen(self):
        """Background thread: install keyboard hook and run message loop.

        This method runs entirely in a background thread. It:
        1. Gets the current thread ID (needed for PostThreadMessageW)
        2. Creates the hook callback function
        3. Installs a WH_KEYBOARD_LL hook via SetWindowsHookEx
        4. Runs a blocking GetMessage loop (required for LL hooks)
        5. Unhooks the keyboard hook when the loop exits

        IMPORTANT: The keyboard hook and message loop must run in
        the same thread. The callback function reference must be
        kept alive (prevent garbage collection) for the entire
        duration of the hook.
        """
        # Get the Win32 thread ID for this thread so the main thread
        # can post WM_QUIT to break the GetMessage loop on shutdown
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        user32 = ctypes.windll.user32

        # Signal dispatch map: VK code -> Qt signal
        signal_map = {
            VK_MEDIA_PLAY_PAUSE: (self.play_pause, "play_pause"),
            VK_MEDIA_NEXT_TRACK: (self.next_track, "next_track"),
            VK_MEDIA_PREV_TRACK: (self.prev_track, "prev_track"),
            VK_MEDIA_STOP: (self.stop_playback, "stop_playback"),
        }

        def _hook_callback(nCode, wParam, lParam):
            """Low-level keyboard hook callback.
            
            Called by Windows for every keyboard event system-wide.
            We only process media key WM_KEYDOWN events and emit
            the corresponding Qt signal. The event is ALWAYS passed
            to the next hook via CallNextHookEx so other apps
            (YouTube, Spotify, etc.) also receive it.
            
            Args:
                nCode: Hook code. If >= 0, we should process.
                wParam: Message type (WM_KEYDOWN, WM_KEYUP, etc.)
                lParam: Pointer to KBDLLHOOKSTRUCT with key info.
                
            Returns:
                Result of CallNextHookEx (forwards event to next hook).
            """
            if nCode >= 0 and wParam == WM_KEYDOWN:
                # Cast lParam to KBDLLHOOKSTRUCT pointer to read vkCode
                kb_struct = ctypes.cast(
                    lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)
                ).contents
                vk_code = kb_struct.vkCode

                # Check if this is a media key we care about
                if vk_code in _MEDIA_VK_CODES:
                    entry = signal_map.get(vk_code)
                    if entry:
                        signal, name = entry
                        print(f"[MediaKeyService] Media key pressed: {name}")
                        # Emit Qt signal. PySide6 auto-queues to main thread.
                        signal.emit()

            # CRITICAL: Always call CallNextHookEx to forward the event
            # to other applications. This makes the hook NON-EXCLUSIVE.
            # Without this call, media keys would be blocked from reaching
            # YouTube, Spotify, and all other apps.
            return user32.CallNextHookEx(
                self._hook_handle, nCode, wParam, lParam
            )

        # Create the hook procedure and keep a reference to prevent
        # Python's garbage collector from freeing the callback while
        # the hook is still active (would cause a crash).
        self._hook_proc = HOOKPROC(_hook_callback)

        # Install the low-level keyboard hook.
        # Parameters:
        #   WH_KEYBOARD_LL (13): Low-level keyboard hook type
        #   self._hook_proc: Our callback function
        #   None: No DLL module (hook is in this process)
        #   0: Monitor all threads (required for LL hooks)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc,
            None,
            0
        )

        if not self._hook_handle:
            error_code = ctypes.GetLastError()
            print(f"[MediaKeyService] ERROR: Failed to install keyboard hook, "
                  f"error={error_code}")
            self._running = False
            return

        print(f"[MediaKeyService] Keyboard hook installed (handle={self._hook_handle})")
        print("[MediaKeyService] Mode: NON-EXCLUSIVE (other apps also receive media keys)")

        # Win32 message struct for GetMessage
        msg = ctypes.wintypes.MSG()

        # Blocking message loop.
        # A message loop is REQUIRED for WH_KEYBOARD_LL hooks to work.
        # GetMessageW returns:
        #   >0 = valid message received
        #    0 = WM_QUIT received (our shutdown signal)
        #   -1 = error
        print("[MediaKeyService] Entering message loop...")
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                # WM_QUIT received or error - exit the loop
                break
            # Translate and dispatch standard messages
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup: remove the keyboard hook.
        # This MUST happen before the thread exits.
        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None

        self._hook_proc = None
        print("[MediaKeyService] Message loop exited, keyboard hook removed")
