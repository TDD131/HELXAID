"""
App Detector Module

Monitors foreground application for profile auto-switching.
"""

import ctypes
from ctypes import wintypes
import threading
import time
from typing import Optional, Callable, Tuple
import os


class AppDetector:
    """
    Monitors the foreground application.
    
    Features:
    - Detect active window changes
    - Get process name and window title
    - Trigger callbacks on app change
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        self._current_process: str = ""
        self._current_title: str = ""
        self._current_hwnd: int = 0
        
        # Callback on app change
        self._on_app_change: Optional[Callable[[str, str], None]] = None
        
        # Polling interval (ms)
        self._poll_interval_ms = 250
        
        # Windows API
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._psapi = ctypes.windll.psapi
        
    @property
    def current_process(self) -> str:
        """Get current foreground process name."""
        return self._current_process
        
    @property
    def current_title(self) -> str:
        """Get current foreground window title."""
        return self._current_title
        
    def on_app_change(self, callback: Callable[[str, str], None]):
        """Set callback for app changes. Args: (process_name, window_title)"""
        self._on_app_change = callback
        
    def start(self):
        """Start monitoring."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[AppDetector] Started")
        
    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        print("[AppDetector] Stopped")
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                hwnd = self._user32.GetForegroundWindow()
                
                if hwnd != self._current_hwnd:
                    process_name, window_title = self._get_window_info(hwnd)
                    
                    if process_name != self._current_process or window_title != self._current_title:
                        old_process = self._current_process
                        
                        self._current_hwnd = hwnd
                        self._current_process = process_name
                        self._current_title = window_title
                        
                        if self._on_app_change and process_name:
                            try:
                                self._on_app_change(process_name, window_title)
                            except Exception as e:
                                print(f"[AppDetector] Callback error: {e}")
                                
            except Exception as e:
                print(f"[AppDetector] Monitor error: {e}")
                
            time.sleep(self._poll_interval_ms / 1000)
            
    def _get_window_info(self, hwnd: int) -> Tuple[str, str]:
        """Get process name and window title for a window handle."""
        process_name = ""
        window_title = ""
        
        try:
            # Get window title
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buffer, length + 1)
                window_title = buffer.value
                
            # Get process ID
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            if pid.value:
                # Open process
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = self._kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    pid.value
                )
                
                if handle:
                    try:
                        # Get process name
                        buffer = ctypes.create_unicode_buffer(260)
                        size = wintypes.DWORD(260)
                        
                        # Try QueryFullProcessImageNameW
                        result = self._kernel32.QueryFullProcessImageNameW(
                            handle, 0, buffer, ctypes.byref(size)
                        )
                        
                        if result:
                            process_name = os.path.basename(buffer.value)
                            
                    finally:
                        self._kernel32.CloseHandle(handle)
                        
        except Exception as e:
            print(f"[AppDetector] Error getting window info: {e}")
            
        return process_name, window_title
        
    def is_app_active(self, process_name: str) -> bool:
        """Check if a specific app is currently in foreground."""
        return self._current_process.lower() == process_name.lower()
        
    def is_title_match(self, title_contains: str) -> bool:
        """Check if current window title contains text."""
        return title_contains.lower() in self._current_title.lower()
