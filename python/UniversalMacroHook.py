import ctypes
import socket
import threading
import time
import sys
import os
import random
import json
from ctypes import wintypes
from AHKPluginManager import AHKPluginManager

def log_msg(msg):
    try:
        print(msg)
        sys.stdout.flush()
    except Exception:
        pass

# =========================================================================
# WIN32 API CONSTANTS & STRUCTURES
# =========================================================================

WH_MOUSE_LL = 14
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

LLMHF_INJECTED = 0x01

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx",          wintypes.LONG),
                ("dy",          wintypes.LONG),
                ("mouseData",   wintypes.DWORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk",         wintypes.WORD),
                ("wScan",       wintypes.WORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)))

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg",    wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))

class INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT))

class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD),
                ("union", INPUT_UNION))

CMPFUNC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

ctypes.windll.user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
ctypes.windll.user32.CallNextHookEx.restype = wintypes.LPARAM

ctypes.windll.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, CMPFUNC, wintypes.HINSTANCE, wintypes.DWORD]
ctypes.windll.user32.SetWindowsHookExW.restype = ctypes.c_void_p

ctypes.windll.user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
ctypes.windll.user32.GetCursorPos.restype = wintypes.BOOL

ctypes.windll.user32.WindowFromPoint.argtypes = [POINT]
ctypes.windll.user32.WindowFromPoint.restype = wintypes.HWND

ctypes.windll.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
ctypes.windll.user32.PostMessageW.restype = wintypes.BOOL


class MacroInterceptorProcess:
    """
    Standalone Hook Engine.
    Listens on UDP port 48123 for macro mappings.
    """
    def __init__(self, port=48123):
        self.port = port
        self.macro_map = {}
        self._hook_id = None
        self.last_heartbeat = time.time()
        self.is_running = True
        self._pointer = None
        
        self.scroll_injection_mode = "Gaming"
        self.macro_execution_mode = "Option A"
        self._scroll_flags = {}
        self._active_scroll_threads = {}
        
        self.ahk_manager = AHKPluginManager()
        
        # Attempt to kill any lingering old instance
        try:
            kill_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            kill_sock.sendto(json.dumps({'cmd': 'exit'}).encode('utf-8'), ('127.0.0.1', 48123))
            kill_sock.close()
        except Exception:
            pass

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Attempt to bind with retry for rapid restarts
        for _ in range(10):
            try:
                self.sock.bind(('127.0.0.1', self.port))
                break
            except OSError:
                time.sleep(0.5)
        else:
            log_msg("[UniversalMacroHook] Failed to bind UDP socket.")
            sys.exit(1)
        self.sock.settimeout(0.5)

    def _ipc_listener_loop(self):
        while self.is_running:
            try:
                data, addr = self.sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                cmd = msg.get('cmd')
                
                if cmd == 'ping':
                    self.last_heartbeat = time.time()
                
                elif cmd == 'map':
                    btn_name = msg.get('btn_name')
                    macro = msg.get('macro')
                    
                    if macro == 'Disable' or not macro:
                        if btn_name in self.macro_map:
                            del self.macro_map[btn_name]
                    else:
                        self.macro_map[btn_name] = macro
                        
                    log_msg(f"[UniversalMacroHook] Updated Mapping: {btn_name} -> {macro}")
                    self._update_ahk_state()
                    
                elif cmd == 'set_anticheat_bypass':
                    self.bypass_anti_cheat = msg.get('enabled', False)
                    log_msg(f"[UniversalMacroHook] Anti-Cheat Bypass Mode: {self.bypass_anti_cheat}")
                    
                elif cmd == 'set_pagedown_emulation':
                    self.pagedown_emulation = msg.get('enabled', False)
                    log_msg(f"[UniversalMacroHook] PageDown Emulation Mode: {self.pagedown_emulation}")
                    
                elif cmd == 'set_scroll_injection_mode':
                    self.scroll_injection_mode = msg.get('mode', 'Gaming')
                    log_msg(f"[UniversalMacroHook] Scroll Injection Mode: {self.scroll_injection_mode}")
                    
                elif cmd == 'set_macro_execution_mode':
                    self.macro_execution_mode = msg.get('mode', 'Option A')
                    log_msg(f"[UniversalMacroHook] Macro Execution Mode: {self.macro_execution_mode}")
                    self._update_ahk_state()
                    
                elif cmd == 'exit':
                    self.is_running = False
                    if hasattr(self, 'ahk_manager'):
                        self.ahk_manager.stop()
                    break
            except socket.timeout:
                continue
            except Exception as e:
                pass

    def _update_ahk_state(self):
        """Applies or kills the AHK plugin based on current execution mode and mappings."""
        if not hasattr(self, 'ahk_manager'):
            return
            
        if getattr(self, 'macro_execution_mode', 'Option A') == "Option B":
            self.ahk_manager.apply_mappings(self.macro_map, getattr(self, 'bypass_anti_cheat', False))
        else:
            self.ahk_manager.stop()

    def _check_heartbeat(self):
        if time.time() - self.last_heartbeat > 3.0:
            log_msg("[UniversalMacroHook] Heartbeat timeout! Parent process died. Exiting safely.")
            return False
        return True

    def _inject_key(self, vk_code, is_press=True):
        x = INPUT(type=INPUT_KEYBOARD,
                  union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code,
                                                  wScan=0,
                                                  dwFlags=0 if is_press else KEYEVENTF_KEYUP,
                                                  time=0,
                                                  dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

    def _inject_mouse_scroll(self, amount):
        MOUSEEVENTF_WHEEL = 0x0800
        if getattr(self, 'bypass_anti_cheat', False):
            # Legacy mouse_event API bypasses LLMHF_INJECTED flags checked by some anti-cheat filters
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount & 0xFFFFFFFF, 0)
        else:
            x = INPUT(type=INPUT_MOUSE,
                      union=INPUT_UNION(mi=MOUSEINPUT(dx=0, dy=0, mouseData=amount & 0xFFFFFFFF, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None)))
            ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

    def _inject_window_scroll(self, amount):
        """Sends WM_MOUSEWHEEL directly to the window under the cursor via PostMessage."""
        pt = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            hwnd = ctypes.windll.user32.WindowFromPoint(pt)
            if hwnd:
                # amount must be shifted to high-order word for WM_MOUSEWHEEL
                # WHEEL_DELTA is 120. If amount is -120, we need to pass it properly as 16-bit signed
                wParam = (amount & 0xFFFF) << 16
                lParam = (pt.y << 16) | (pt.x & 0xFFFF)
                ctypes.windll.user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wParam, lParam)

    def _inject_media_key(self, vk_code):
        # Media keys often require extended key flag
        KEYEVENTF_EXTENDEDKEY = 0x0001
        
        # Press
        x_down = INPUT(type=INPUT_KEYBOARD,
                  union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_EXTENDEDKEY, time=0, dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(x_down), ctypes.sizeof(x_down))
        
        time.sleep(0.01)
        
        # Release
        x_up = INPUT(type=INPUT_KEYBOARD,
                  union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(x_up), ctypes.sizeof(x_up))

    def _inject_macro(self, macro_str):
        # Native OS injection for actions corrupted by hardware firmware
        if macro_str == "Scroll Up":
            if getattr(self, 'pagedown_emulation', False):
                self._inject_key(0x21, True)  # VK_PRIOR / Page Up
                time.sleep(0.01)
                self._inject_key(0x21, False)
            else:
                self._inject_mouse_scroll(120)
            return
        elif macro_str == "Scroll Down":
            if getattr(self, 'pagedown_emulation', False):
                self._inject_key(0x22, True)  # VK_NEXT / Page Down
                time.sleep(0.01)
                self._inject_key(0x22, False)
            else:
                self._inject_mouse_scroll(-120)
            return
        elif macro_str == "Play/Pause":
            self._inject_media_key(0xB3) # VK_MEDIA_PLAY_PAUSE
            return
        elif macro_str == "Next Track":
            self._inject_media_key(0xB0) # VK_MEDIA_NEXT_TRACK
            return
        elif macro_str == "Prev Track":
            self._inject_media_key(0xB1) # VK_MEDIA_PREV_TRACK
            return
        elif macro_str == "Stop":
            self._inject_media_key(0xB2) # VK_MEDIA_STOP
            return
        elif macro_str == "Mute":
            self._inject_media_key(0xAD) # VK_VOLUME_MUTE
            return
        elif macro_str == "Volume +":
            self._inject_media_key(0xAF) # VK_VOLUME_UP
            return
        elif macro_str == "Volume -":
            self._inject_media_key(0xAE) # VK_VOLUME_DOWN
            return
        
        vk_map = {
            'A': 0x41, 'B': 0x42, 'C': 0x43, 'D': 0x44, 'E': 0x45, 'F': 0x46,
            'G': 0x47, 'H': 0x48, 'I': 0x49, 'J': 0x4A, 'K': 0x4B, 'L': 0x4C,
            'M': 0x4D, 'N': 0x4E, 'O': 0x4F, 'P': 0x50, 'Q': 0x51, 'R': 0x52,
            'S': 0x53, 'T': 0x54, 'U': 0x55, 'V': 0x56, 'W': 0x57, 'X': 0x58,
            'Y': 0x59, 'Z': 0x5A,
            'CTRL': 0x11, 'SHIFT': 0x10, 'ALT': 0x12, 'ENTER': 0x0D, 'SPACE': 0x20
        }
        
        parts = [p.strip().upper() for p in macro_str.split('+')]
        vk_codes = [vk_map.get(p, 0x41) for p in parts] 
        
        for vk in vk_codes:
            self._inject_key(vk, True)
            time.sleep(random.uniform(0.015, 0.025))
            
        for vk in reversed(vk_codes):
            self._inject_key(vk, False)
            time.sleep(random.uniform(0.015, 0.025))

    def _continuous_scroll_worker(self, btn_name, direction, mode):
        delta = 120 if direction == "Up" else -120
        interval = 0.03  # 30ms delay
        
        while self._scroll_flags.get(btn_name, False):
            if mode == "Safe Browsing (Window Message Injection)":
                self._inject_window_scroll(delta)
            else:
                self._inject_mouse_scroll(delta)
            time.sleep(interval)
            
    def _hook_callback(self, nCode, wParam, lParam):
        # If AHK is active, bypass Python hook logic completely so AHK can handle it
        if getattr(self, 'macro_execution_mode', 'Option A') == "Option B":
            return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)
            
        if nCode >= 0:
            struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            
            if struct.flags & LLMHF_INJECTED:
                return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)
            
            btn_name = None
            is_press = False
            
            if wParam == WM_LBUTTONDOWN: btn_name, is_press = '0', True
            elif wParam == WM_LBUTTONUP: btn_name, is_press = '0', False
            elif wParam == WM_RBUTTONDOWN: btn_name, is_press = '1', True
            elif wParam == WM_RBUTTONUP: btn_name, is_press = '1', False
            elif wParam == WM_MBUTTONDOWN: btn_name, is_press = '2', True
            elif wParam == WM_MBUTTONUP: btn_name, is_press = '2', False
            elif wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                high_word = (struct.mouseData >> 16) & 0xFFFF
                btn_name = '4' if high_word == 1 else '3'
                is_press = True if wParam == WM_XBUTTONDOWN else False

            if btn_name and btn_name in self.macro_map:
                action = self.macro_map[btn_name]
                log_msg(f"[DEBUG-HOOK] Received physical button {btn_name}, mapped to action: {action}. is_press={is_press}")
                
                NATIVE_ACTIONS = {
                    "Left Click", "Right Click", "Wheel Click", "Forward", "Backward",
                    "Disable"
                }
                
                DEFAULT_MAPPINGS = {
                    '0': 'Left Click',
                    '1': 'Right Click',
                    '2': 'Wheel Click',
                    '3': 'Forward',
                    '4': 'Backward'
                }
                
                if action == DEFAULT_MAPPINGS.get(btn_name):
                    log_msg(f"[DEBUG-HOOK] Action {action} is default for {btn_name}. Passing through.")
                    return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)
                    
                if action in NATIVE_ACTIONS:
                    log_msg(f"[DEBUG-HOOK] Action {action} is NATIVE. Consuming and letting hardware handle it.")
                    return 1
                    
                log_msg(f"[DEBUG-HOOK] Action {action} is SOFTWARE. Swallowing click.")
                
                # Check for Continuous Scroll
                if "Scroll" in action:
                    if is_press:
                        direction = "Up" if "Up" in action else "Down"
                        self._scroll_flags[btn_name] = True
                        log_msg(f"[DEBUG-HOOK] Starting Continuous Scroll {direction} using mode {self.scroll_injection_mode}")
                        thread = threading.Thread(
                            target=self._continuous_scroll_worker,
                            args=(btn_name, direction, getattr(self, 'scroll_injection_mode', 'Gaming')),
                            daemon=True
                        )
                        self._active_scroll_threads[btn_name] = thread
                        thread.start()
                    else:
                        log_msg(f"[DEBUG-HOOK] Stopping Continuous Scroll")
                        self._scroll_flags[btn_name] = False
                    return 1

                # Normal Macro Handling
                if is_press:
                    log_msg(f"[DEBUG-HOOK] Injecting macro: {action}")
                    threading.Thread(target=self._inject_macro, args=(action,), daemon=True).start()
                return 1 

        return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def run(self):
        self._pointer = CMPFUNC(self._hook_callback)
        
        listener_thread = threading.Thread(target=self._ipc_listener_loop, daemon=True)
        listener_thread.start()
        
        self._hook_id = ctypes.windll.user32.SetWindowsHookExW(WH_MOUSE_LL, self._pointer, None, 0)
        
        if not self._hook_id:
            log_msg("[UniversalMacroHook] Failed to set WH_MOUSE_LL hook.")
            return

        log_msg(f"[UniversalMacroHook] Engine Started on UDP port {self.port} & Hook Installed.")
        
        msg = wintypes.MSG()
        PM_REMOVE = 0x0001
        
        while self.is_running:
            if not self._check_heartbeat():
                break
                
            if ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == 0x0012: # WM_QUIT
                    break
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.005) 
                
        if self._hook_id:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        self.sock.close()
        log_msg("[UniversalMacroHook] Engine Terminated Safely.")
        os._exit(0)

if __name__ == "__main__":
    port = 48123
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    engine = MacroInterceptorProcess(port=port)
    engine.run()
