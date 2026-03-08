"""
Essential Optimizations Helper Module

Implements the actual functionality for essential optimization checkboxes:
- Memory Boost: Clear working sets and standby memory
- Set Game Priority: Elevate game process to High priority
- Disable Windows Key: Block Windows key during gaming

Component Name: EssentialOptimizations
"""

import os
import sys
import ctypes
from ctypes import wintypes
import subprocess
from typing import Optional, Callable

# Windows API constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_LWIN = 0x5B
VK_RWIN = 0x5C

# Global hook handle
_winkey_hook = None
_hook_dll = None


class EssentialOptimizations:
    """
    Helper class for essential optimizations.
    
    Component Name: EssentialOptimizations
    """
    
    def __init__(self):
        self._winkey_disabled = False
        self._original_priority = {}  # pid -> original priority class
        self._hook_installed = False
    
    # ==========================================================================
    # MEMORY BOOST
    # ==========================================================================
    
    def memory_boost(self) -> dict:
        """Clear unused working and standby memory WITHOUT touching game processes.
        
        Skips processes that are:
        - System (PID 0, 4)
        - Running at HIGH or REALTIME priority class (games, important apps)
        - The currently focused/foreground window's process
        - Our own launcher process
        
        This prevents stuttering in RAM-heavy games like Minecraft (javaw.exe),
        which relies on large working sets for chunk cache and textures.
        
        Returns dict with 'success' and 'freed_mb' keys.
        """
        try:
            import psutil
            
            # HIGH_PRIORITY_CLASS = 0x80, REALTIME_PRIORITY_CLASS = 0x100
            # These map to psutil constants
            SKIP_PRIORITIES = {
                psutil.HIGH_PRIORITY_CLASS,
                psutil.REALTIME_PRIORITY_CLASS,
            }
            
            # Get foreground window PID (the active window the user is on)
            foreground_pid = None
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    fg_pid = ctypes.wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(fg_pid))
                    foreground_pid = fg_pid.value
            except Exception:
                pass
            
            # Our own process PID (never trim the launcher)
            import os as _os
            our_pid = _os.getpid()
            
            # Get before stats
            before = psutil.virtual_memory()
            before_available = before.available
            
            # Track what was skipped for logging
            cleared_count = 0
            skipped_game = 0
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pid = proc.info['pid']
                    
                    # Skip system idle / System processes
                    if pid in [0, 4]:
                        continue
                    
                    # Skip ourselves
                    if pid == our_pid:
                        continue
                    
                    # Skip the foreground window's process (likely the game)
                    if foreground_pid and pid == foreground_pid:
                        skipped_game += 1
                        continue
                    
                    # Skip HIGH or REALTIME priority processes  
                    # (games boosted by the launcher, or other critical apps)
                    try:
                        prio = proc.nice()
                        if prio in SKIP_PRIORITIES:
                            skipped_game += 1
                            continue
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    
                    # Safe to trim this background process
                    handle = ctypes.windll.kernel32.OpenProcess(
                        0x1F0FFF,  # PROCESS_ALL_ACCESS
                        False,
                        pid
                    )
                    
                    if handle:
                        # EmptyWorkingSet pushes idle pages to standby/page file.
                        # Only safe for background processes that aren't actively gaming
                        ctypes.windll.psapi.EmptyWorkingSet(handle)
                        ctypes.windll.kernel32.CloseHandle(handle)
                        cleared_count += 1
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    pass
            
            # Clear standby list (requires admin, fallback to RAMMap)
            self._clear_standby_list()
            
            # Get after stats
            after = psutil.virtual_memory()
            after_available = after.available
            
            freed_mb = (after_available - before_available) / (1024 * 1024)
            
            print(f"[EssentialOpt] Memory Boost: Cleared {cleared_count} bg processes "
                  f"(skipped {skipped_game} game/high-priority), freed {freed_mb:.1f} MB")
            
            return {
                "success": True,
                "cleared_processes": cleared_count,
                "skipped_game_processes": skipped_game,
                "freed_mb": max(0, freed_mb)
            }
            
        except Exception as e:
            print(f"[EssentialOpt] Memory Boost error: {e}")
            return {"success": False, "error": str(e), "freed_mb": 0}
    
    def _clear_standby_list(self):
        """Clear Windows standby memory list (requires elevation)."""
        try:
            # Try using RAMMap command line if available
            rammap_path = os.path.join(os.environ.get('TEMP', ''), 'RAMMap64.exe')
            if os.path.exists(rammap_path):
                subprocess.run(
                    [rammap_path, '-Ew'],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        except Exception:
            pass  # Silently fail if RAMMap not available
    
    # ==========================================================================
    # SET GAME PRIORITY
    # ==========================================================================
    
    def set_game_priority(self, game_exe: str, priority: str = "high") -> dict:
        """
        Set game process to specified priority.
        
        Args:
            game_exe: Name of game executable (e.g., 'game.exe')
            priority: 'realtime', 'high', 'above_normal', 'normal', 'below_normal', 'idle'
        
        Returns dict with 'success' and 'pid' keys.
        """
        try:
            import psutil
            
            priority_map = {
                'realtime': psutil.REALTIME_PRIORITY_CLASS,
                'high': psutil.HIGH_PRIORITY_CLASS,
                'above_normal': psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                'normal': psutil.NORMAL_PRIORITY_CLASS,
                'below_normal': psutil.BELOW_NORMAL_PRIORITY_CLASS,
                'idle': psutil.IDLE_PRIORITY_CLASS
            }
            
            priority_class = priority_map.get(priority.lower(), psutil.HIGH_PRIORITY_CLASS)
            
            # Find game process
            game_exe_lower = game_exe.lower()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == game_exe_lower:
                        pid = proc.info['pid']
                        p = psutil.Process(pid)
                        
                        # Store original priority for restoration
                        if pid not in self._original_priority:
                            self._original_priority[pid] = p.nice()
                        
                        # Set new priority
                        p.nice(priority_class)
                        
                        print(f"[EssentialOpt] Set {game_exe} (PID {pid}) to {priority} priority")
                        return {"success": True, "pid": pid, "priority": priority}
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"[EssentialOpt] Cannot set priority for {game_exe}: {e}")
                    pass
            
            print(f"[EssentialOpt] Game process '{game_exe}' not found")
            return {"success": False, "error": "Process not found"}
            
        except Exception as e:
            print(f"[EssentialOpt] Set priority error: {e}")
            return {"success": False, "error": str(e)}
    
    def restore_game_priority(self, game_exe: str) -> dict:
        """Restore game process to original priority."""
        try:
            import psutil
            
            game_exe_lower = game_exe.lower()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == game_exe_lower:
                        pid = proc.info['pid']
                        
                        if pid in self._original_priority:
                            p = psutil.Process(pid)
                            p.nice(self._original_priority[pid])
                            del self._original_priority[pid]
                            
                            print(f"[EssentialOpt] Restored {game_exe} priority")
                            return {"success": True, "pid": pid}
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return {"success": False, "error": "Process not found or no saved priority"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE WINDOWS KEY
    # ==========================================================================
    
    def disable_windows_key(self) -> dict:
        """
        Disable Windows key using registry Scancode Map.
        
        Note: Changes take effect after logoff/restart, or use keyboard library for immediate effect.
        
        Returns dict with 'success' key.
        """
        if self._winkey_disabled:
            return {"success": True, "message": "Already disabled"}
        
        try:
            # Method 1: Try using keyboard library (immediate effect)
            try:
                import keyboard
                keyboard.block_key('left windows')
                keyboard.block_key('right windows')
                self._winkey_disabled = True
                print("[EssentialOpt] Windows key disabled (keyboard library)")
                return {"success": True, "method": "keyboard"}
            except Exception as e:
                print(f"[EssentialOpt] keyboard library method failed: {e}")
            
            # Method 2: Registry Scancode Map (requires restart to take effect)
            import winreg
            
            key_path = r"SYSTEM\CurrentControlSet\Control\Keyboard Layout"
            
            # Scancode map to disable LWin and RWin
            # Format: Header (8 bytes) + Mappings (4 bytes each) + NULL terminator (4 bytes)
            # LWin (0xE05B) -> disabled, RWin (0xE05C) -> disabled
            scancode_map = bytes([
                0x00, 0x00, 0x00, 0x00,  # Header (version)
                0x00, 0x00, 0x00, 0x00,  # Header (flags)
                0x03, 0x00, 0x00, 0x00,  # Number of entries (2 + null terminator)
                0x00, 0x00, 0x5B, 0xE0,  # LWin -> null
                0x00, 0x00, 0x5C, 0xE0,  # RWin -> null
                0x00, 0x00, 0x00, 0x00   # Null terminator
            ])
            
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, 
                                     winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                winreg.SetValueEx(key, "Scancode Map", 0, winreg.REG_BINARY, scancode_map)
                winreg.CloseKey(key)
                self._winkey_disabled = True
                print("[EssentialOpt] Windows key disabled (registry - restart required)")
                return {"success": True, "method": "registry", "note": "Restart required for full effect"}
            except PermissionError:
                print("[EssentialOpt] Registry method requires admin rights")
                return {"success": False, "error": "Admin rights required. Please run as administrator."}
            except Exception as e:
                print(f"[EssentialOpt] Registry method failed: {e}")
                return {"success": False, "error": str(e)}
                
        except Exception as e:
            print(f"[EssentialOpt] Disable Windows key error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_windows_key(self) -> dict:
        """
        Re-enable Windows key.
        
        Returns dict with 'success' key.
        """
        if not self._winkey_disabled:
            return {"success": True, "message": "Already enabled"}
        
        try:
            # Method 1: Try using keyboard library
            try:
                import keyboard
                keyboard.unblock_key('left windows')
                keyboard.unblock_key('right windows')
                self._winkey_disabled = False
                print("[EssentialOpt] Windows key enabled (keyboard library)")
                return {"success": True}
            except Exception:
                pass
            
            # Method 2: Remove registry Scancode Map
            import winreg
            
            key_path = r"SYSTEM\CurrentControlSet\Control\Keyboard Layout"
            
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                                     winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                try:
                    winreg.DeleteValue(key, "Scancode Map")
                except FileNotFoundError:
                    pass  # Already deleted
                winreg.CloseKey(key)
                self._winkey_disabled = False
                print("[EssentialOpt] Windows key enabled (registry - restart for full effect)")
                return {"success": True}
            except PermissionError:
                return {"success": False, "error": "Admin rights required"}
            except Exception as e:
                return {"success": False, "error": str(e)}
                
        except Exception as e:
            print(f"[EssentialOpt] Enable Windows key error: {e}")
            return {"success": False, "error": str(e)}
    
    def is_winkey_disabled(self) -> bool:
        """Check if Windows key is currently disabled."""
        return self._winkey_disabled
    
    # ==========================================================================
    # CLEAR CLIPBOARD
    # ==========================================================================
    
    def clear_clipboard(self) -> dict:
        """
        Clear Windows clipboard AND clipboard history using WinRT API.
        
        Returns dict with 'success' key.
        """
        try:
            user32 = ctypes.windll.user32
            
            # 1. Clear current clipboard content
            if user32.OpenClipboard(None):
                user32.EmptyClipboard()
                user32.CloseClipboard()
            
            # 2. Clear clipboard history using WinRT API (same as OMEN Gaming Hub)
            try:
                from winrt.windows.applicationmodel.datatransfer import Clipboard
                Clipboard.clear_history()
                print("[EssentialOpt] Clipboard and history cleared (WinRT)")
            except ImportError:
                print("[EssentialOpt] WinRT not available, only current clipboard cleared")
            except Exception as e:
                print(f"[EssentialOpt] WinRT clear history warning: {e}")
            
            return {"success": True}
                
        except Exception as e:
            print(f"[EssentialOpt] Clear clipboard error: {e}")
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE GAME BAR
    # ==========================================================================
    
    def disable_game_bar(self) -> dict:
        """
        Disable Windows Game Bar via registry.
        
        Returns dict with 'success' key.
        """
        try:
            import winreg
            
            success_count = 0
            
            # Try multiple registry paths (Windows versions vary)
            paths_to_try = [
                # Windows 10/11 main path
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\GameBar", [
                    ("AllowAutoGameMode", 0),
                    ("UseNexusForGameBarEnabled", 0),
                ]),
                # Alternative path for Windows 11
                (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", [
                    ("GameDVR_Enabled", 0),
                ]),
            ]
            
            for hkey, key_path, values in paths_to_try:
                try:
                    # Try to open existing key first
                    try:
                        key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                    except FileNotFoundError:
                        # Create if not exists
                        key = winreg.CreateKey(hkey, key_path)
                    
                    for value_name, value_data in values:
                        try:
                            # Store original
                            try:
                                original = winreg.QueryValueEx(key, value_name)[0]
                                if not hasattr(self, '_original_game_bar_values'):
                                    self._original_game_bar_values = {}
                                self._original_game_bar_values[f"{key_path}\\{value_name}"] = original
                            except FileNotFoundError:
                                pass
                            
                            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value_data)
                            success_count += 1
                        except PermissionError:
                            print(f"[EssentialOpt] Game Bar: No permission for {value_name}")
                        except Exception as e:
                            print(f"[EssentialOpt] Game Bar: Error setting {value_name}: {e}")
                    
                    winreg.CloseKey(key)
                except PermissionError:
                    print(f"[EssentialOpt] Game Bar: No permission for {key_path}")
                except Exception as e:
                    print(f"[EssentialOpt] Game Bar: Error with {key_path}: {e}")
            
            if success_count > 0:
                print(f"[EssentialOpt] Game Bar disabled ({success_count} settings changed)")
                return {"success": True}
            else:
                print("[EssentialOpt] Game Bar: Could not change any settings (may need admin)")
                return {"success": False, "error": "Permission denied - try running as Administrator"}
            
        except Exception as e:
            print(f"[EssentialOpt] Disable Game Bar error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_game_bar(self) -> dict:
        """Re-enable Windows Game Bar."""
        try:
            import winreg
            
            key_path = r"SOFTWARE\Microsoft\GameBar"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            original = getattr(self, '_original_game_bar', 1)
            winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, original)
            winreg.SetValueEx(key, "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
            print("[EssentialOpt] Game Bar enabled")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE GAME MODE
    # ==========================================================================
    
    def disable_game_mode(self) -> dict:
        """
        Disable Windows Game Mode via registry.
        
        Returns dict with 'success' key.
        """
        try:
            import winreg
            
            success_count = 0
            
            # Try multiple registry paths
            paths_to_try = [
                # Windows 10/11 main path
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\GameBar", [
                    ("AutoGameModeEnabled", 0),
                    ("AllowAutoGameMode", 0),
                ]),
                # Alternative path for Game Mode
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", [
                    ("AutoGameModeEnabled", 0),
                ]),
            ]
            
            for hkey, key_path, values in paths_to_try:
                try:
                    try:
                        key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                    except FileNotFoundError:
                        key = winreg.CreateKey(hkey, key_path)
                    
                    for value_name, value_data in values:
                        try:
                            # Store original
                            try:
                                original = winreg.QueryValueEx(key, value_name)[0]
                                if not hasattr(self, '_original_game_mode_values'):
                                    self._original_game_mode_values = {}
                                self._original_game_mode_values[f"{key_path}\\{value_name}"] = original
                            except FileNotFoundError:
                                pass
                            
                            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value_data)
                            success_count += 1
                        except PermissionError:
                            print(f"[EssentialOpt] Game Mode: No permission for {value_name}")
                        except Exception as e:
                            print(f"[EssentialOpt] Game Mode: Error setting {value_name}: {e}")
                    
                    winreg.CloseKey(key)
                except PermissionError:
                    print(f"[EssentialOpt] Game Mode: No permission for {key_path}")
                except Exception as e:
                    print(f"[EssentialOpt] Game Mode: Error with {key_path}: {e}")
            
            if success_count > 0:
                print(f"[EssentialOpt] Game Mode disabled ({success_count} settings changed)")
                return {"success": True}
            else:
                print("[EssentialOpt] Game Mode: Could not change any settings (may need admin)")
                return {"success": False, "error": "Permission denied - try running as Administrator"}
            
        except Exception as e:
            print(f"[EssentialOpt] Disable Game Mode error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_game_mode(self) -> dict:
        """Re-enable Windows Game Mode."""
        try:
            import winreg
            
            key_path = r"SOFTWARE\Microsoft\GameBar"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            original = getattr(self, '_original_game_mode', 1)
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, original)
            winreg.CloseKey(key)
            
            print("[EssentialOpt] Game Mode enabled")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE DVR (Xbox Game DVR)
    # ==========================================================================
    
    def disable_dvr(self) -> dict:
        """
        Disable Xbox Game DVR via registry.
        
        Returns dict with 'success' key.
        """
        try:
            import winreg
            
            success_count = 0
            
            # Try multiple registry paths
            paths_to_try = [
                # Main GameDVR path
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR", [
                    ("AppCaptureEnabled", 0),
                ]),
                # System GameConfigStore path
                (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", [
                    ("GameDVR_Enabled", 0),
                ]),
            ]
            
            for hkey, key_path, values in paths_to_try:
                try:
                    try:
                        key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                    except FileNotFoundError:
                        key = winreg.CreateKey(hkey, key_path)
                    
                    for value_name, value_data in values:
                        try:
                            # Store original
                            try:
                                original = winreg.QueryValueEx(key, value_name)[0]
                                if not hasattr(self, '_original_dvr_values'):
                                    self._original_dvr_values = {}
                                self._original_dvr_values[f"{key_path}\\{value_name}"] = original
                            except FileNotFoundError:
                                pass
                            
                            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value_data)
                            success_count += 1
                        except PermissionError:
                            print(f"[EssentialOpt] DVR: No permission for {value_name}")
                        except Exception as e:
                            print(f"[EssentialOpt] DVR: Error setting {value_name}: {e}")
                    
                    winreg.CloseKey(key)
                except PermissionError:
                    print(f"[EssentialOpt] DVR: No permission for {key_path}")
                except Exception as e:
                    print(f"[EssentialOpt] DVR: Error with {key_path}: {e}")
            
            if success_count > 0:
                print(f"[EssentialOpt] Game DVR disabled ({success_count} settings changed)")
                return {"success": True}
            else:
                print("[EssentialOpt] DVR: Could not change any settings (may need admin)")
                return {"success": False, "error": "Permission denied - try running as Administrator"}
            
        except Exception as e:
            print(f"[EssentialOpt] Disable DVR error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_dvr(self) -> dict:
        """Re-enable Xbox Game DVR."""
        try:
            import winreg
            
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            original = getattr(self, '_original_dvr', 1)
            winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, original)
            winreg.CloseKey(key)
            
            print("[EssentialOpt] Game DVR enabled")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE WINDOWS UPDATE (Temporary)
    # ==========================================================================
    
    def disable_updates(self) -> dict:
        """
        Temporarily pause Windows Update service.
        
        Note: Requires admin rights. Will be re-enabled on restore.
        
        Returns dict with 'success' key.
        """
        try:
            # Stop Windows Update service
            result = subprocess.run(
                ["net", "stop", "wuauserv"],
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 or b"is not started" in result.stderr:
                self._updates_disabled = True
                print("[EssentialOpt] Windows Update paused")
                return {"success": True}
            else:
                error = result.stderr.decode(errors='ignore')
                if "Access is denied" in error:
                    return {"success": False, "error": "Admin rights required"}
                return {"success": False, "error": error}
                
        except Exception as e:
            print(f"[EssentialOpt] Disable updates error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_updates(self) -> dict:
        """Re-enable Windows Update service."""
        try:
            result = subprocess.run(
                ["net", "start", "wuauserv"],
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self._updates_disabled = False
            print("[EssentialOpt] Windows Update resumed")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE CORE PARKING
    # ==========================================================================
    
    def disable_core_parking(self) -> dict:
        """
        Disable CPU core parking for better gaming performance.
        
        Uses powercfg to set core parking to 100% (no parking).
        
        Returns dict with 'success' key.
        """
        try:
            # Get current power scheme GUID
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Extract scheme GUID from output
            output = result.stdout.decode(errors='ignore')
            import re
            match = re.search(r'([a-f0-9-]{36})', output, re.IGNORECASE)
            
            if not match:
                return {"success": False, "error": "Could not get power scheme"}
            
            scheme_guid = match.group(1)
            
            # Core parking subgroup and setting GUIDs
            # PROCESSOR_SUBGROUP = 54533251-82be-4824-96c1-47b60b740d00
            # CPMINCORES = 0cc5b647-c1df-4637-891a-dec35c318583
            
            # Set minimum cores to 100% (disable parking)
            subprocess.run(
                ["powercfg", "/setacvalueindex", scheme_guid,
                 "54533251-82be-4824-96c1-47b60b740d00",
                 "0cc5b647-c1df-4637-891a-dec35c318583", "100"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Apply changes
            subprocess.run(
                ["powercfg", "/setactive", scheme_guid],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self._core_parking_disabled = True
            print("[EssentialOpt] Core parking disabled")
            return {"success": True}
            
        except Exception as e:
            print(f"[EssentialOpt] Disable core parking error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_core_parking(self) -> dict:
        """Re-enable CPU core parking (restore default)."""
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            output = result.stdout.decode(errors='ignore')
            import re
            match = re.search(r'([a-f0-9-]{36})', output, re.IGNORECASE)
            
            if match:
                scheme_guid = match.group(1)
                # Restore to 50% (Windows default)
                subprocess.run(
                    ["powercfg", "/setacvalueindex", scheme_guid,
                     "54533251-82be-4824-96c1-47b60b740d00",
                     "0cc5b647-c1df-4637-891a-dec35c318583", "50"],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                subprocess.run(
                    ["powercfg", "/setactive", scheme_guid],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            
            self._core_parking_disabled = False
            print("[EssentialOpt] Core parking enabled")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # DISABLE FILE SHARING
    # ==========================================================================
    
    def disable_file_sharing(self) -> dict:
        """
        Temporarily stop LanmanServer (File Sharing) service.
        
        Returns dict with 'success' key.
        """
        try:
            result = subprocess.run(
                ["net", "stop", "LanmanServer"],
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 or b"is not started" in result.stderr:
                self._file_sharing_disabled = True
                print("[EssentialOpt] File Sharing stopped")
                return {"success": True}
            else:
                error = result.stderr.decode(errors='ignore')
                if "Access is denied" in error:
                    print("[EssentialOpt] File Sharing: Access denied (need admin)")
                    return {"success": False, "error": "Admin rights required"}
                print(f"[EssentialOpt] File Sharing failed: {error}")
                return {"success": False, "error": error}
                
        except Exception as e:
            print(f"[EssentialOpt] Disable file sharing error: {e}")
            return {"success": False, "error": str(e)}
    
    def enable_file_sharing(self) -> dict:
        """Re-enable File Sharing service."""
        try:
            subprocess.run(
                ["net", "start", "LanmanServer"],
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self._file_sharing_disabled = False
            print("[EssentialOpt] File Sharing started")
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==========================================================================
    # CLEANUP
    # ==========================================================================
    
    def cleanup(self):
        """Clean up all hooks and restore settings."""
        # Restore Windows key
        if self._winkey_disabled:
            self.enable_windows_key()
        
        # Restore process priorities
        import psutil
        for pid, priority in list(self._original_priority.items()):
            try:
                p = psutil.Process(pid)
                p.nice(priority)
            except:
                pass
        self._original_priority.clear()


# Singleton instance
_optimizer = None

def get_optimizer() -> EssentialOptimizations:
    """Get the singleton optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = EssentialOptimizations()
    return _optimizer
