import os
import subprocess
import time

class AHKPluginManager:
    """
    Manages the lifecycle and generation of AutoHotkey (AHK) scripts for OS-Level Macros.
    """
    def __init__(self, plugin_dir="plugins/ahk"):
        # Resolve AppData safely with a hard fallback to User Directory
        default_appdata = os.path.expanduser("~\\AppData\\Roaming")
        appdata_dir = os.path.join(os.environ.get("APPDATA", default_appdata), "HELXAID")
        
        # Point the plugin directory to AppData
        self.plugin_dir = os.path.join(appdata_dir, plugin_dir)
        self.script_path = os.path.join(self.plugin_dir, "current_profile.ahk")
        
        # Try AppData path via tools_downloader first, fallback to plugins/ahk/AutoHotkey.exe
        try:
            from integrations.tools_downloader import get_ahk_path
            self.ahk_exe_path = get_ahk_path()
        except ImportError:
            self.ahk_exe_path = os.path.join(self.plugin_dir, "AutoHotkey.exe")

        self._process = None
        
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir, exist_ok=True)

    def _generate_ahk_script(self, mappings: dict, bypass_anticheat: bool) -> str:
        """
        Converts internal HELXAID mappings to AHK v1.1 syntax.
        """
        # Base settings for gaming compatibility
        ahk_script = [
            "#NoEnv",
            "#NoTrayIcon",
            "SendMode Input",
            "SetWorkingDir %A_ScriptDir%",
            ""
        ]

        if bypass_anticheat:
            # Event mode is sometimes better for bypassing simple anti-cheats
            ahk_script.append("SendMode Event")
            ahk_script.append("SetKeyDelay, 20, 20")

        # Mapping HELXAID Button IDs to AHK Keys
        btn_to_ahk = {
            '0': 'LButton',
            '1': 'RButton',
            '2': 'MButton',
            '3': 'XButton1',
            '4': 'XButton2'
        }

        # Default actions for each button (skip generating hotkey if action is default)
        default_actions = {
            '0': ["Left Click", "LButton"],
            '1': ["Right Click", "RButton"],
            '2': ["Wheel Click", "Middle Click", "MButton"],
            '3': ["Backward", "XButton1"],
            '4': ["Forward", "XButton2"]
        }

        for btn_id, action in mappings.items():
            if not action or action == "Disable":
                continue
                
            btn_str = str(btn_id)
            # If action is default for this button, skip AHK interception
            if action in default_actions.get(btn_str, []):
                continue

            ahk_key = btn_to_ahk.get(btn_str)
            if not ahk_key:
                continue

            # We use the * prefix so it triggers even if modifiers (Ctrl/Shift) are held
            hotkey = f"*{ahk_key}::"

            # Parse Action
            if action == "Scroll Up":
                body = f"""    While GetKeyState("{ahk_key}", "P") {{
        Send {{WheelUp}}
        Sleep 30
    }}
    return"""
            elif action == "Scroll Down":
                body = f"""    While GetKeyState("{ahk_key}", "P") {{
        Send {{WheelDown}}
        Sleep 30
    }}
    return"""
            elif action == "Right Click":
                body = "    Send {RButton}\n    return"
            elif action == "Left Click":
                body = "    Send {LButton}\n    return"
            elif action == "Wheel Click" or action == "Middle Click":
                body = "    Send {MButton}\n    return"
            elif action == "Backward":
                body = "    Send {XButton1}\n    return"
            elif action == "Forward":
                body = "    Send {XButton2}\n    return"
            elif action == "Volume +":
                body = "    Send {Volume_Up}\n    return"
            elif action == "Volume -":
                body = "    Send {Volume_Down}\n    return"
            elif action == "Mute":
                body = "    Send {Volume_Mute}\n    return"
            elif action == "Play/Pause":
                body = "    Send {Media_Play_Pause}\n    return"
            elif action == "Next Track":
                body = "    Send {Media_Next}\n    return"
            elif action == "Prev Track":
                body = "    Send {Media_Prev}\n    return"
            elif action == "Stop":
                body = "    Send {Media_Stop}\n    return"
            elif "+" in action:
                parts = [p.strip().upper() for p in action.split('+')]
                ahk_send = ""
                for p in parts:
                    if p == 'CTRL': ahk_send += "^"
                    elif p == 'ALT': ahk_send += "!"
                    elif p == 'SHIFT': ahk_send += "+"
                    else: ahk_send += f"{{{p.lower()}}}"
                body = f"    Send {ahk_send}\n    return"
            else:
                val = action.lower()
                body = f"    Send {{{val}}}\n    return"

            ahk_script.append(hotkey)
            ahk_script.append(body)
            ahk_script.append("")

        return "\n".join(ahk_script)

    def apply_mappings(self, mappings: dict, bypass_anticheat: bool = False):
        """
        Writes the AHK script and restarts the AHK process.
        """
        self.stop() # Kill existing first
        
        if not mappings:
            return

        # Write new script
        script_content = self._generate_ahk_script(mappings, bypass_anticheat)
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Check if AutoHotkey.exe exists (auto-download if missing)
        if not os.path.exists(self.ahk_exe_path):
            print(f"[AHKPluginManager] AutoHotkey.exe not found at {self.ahk_exe_path}. Attempting auto-download...")
            try:
                from integrations.tools_downloader import download_ahk, get_ahk_path
                success, res = download_ahk()
                if success:
                    self.ahk_exe_path = res
                    print(f"[AHKPluginManager] Auto-download succeeded: {res}")
                else:
                    print(f"[AHKPluginManager] Auto-download failed: {res}")
                    return
            except Exception as e:
                print(f"[AHKPluginManager] Auto-download error: {e}")
                return

        # Start process
        try:
            # Use CREATE_NO_WINDOW to hide the console if running from a script
            CREATE_NO_WINDOW = 0x08000000
            self._process = subprocess.Popen(
                [self.ahk_exe_path, self.script_path],
                creationflags=CREATE_NO_WINDOW
            )
            print(f"[AHKPluginManager] Spawned AutoHotkey process (PID: {self._process.pid})")
        except Exception as e:
            print(f"[AHKPluginManager] Failed to spawn AutoHotkey: {e}")

    def stop(self):
        """
        Terminates the running AHK script process.
        """
        if self._process:
            try:
                self._process.kill()
                self._process.wait(timeout=1)
                print("[AHKPluginManager] AutoHotkey process terminated.")
            except Exception as e:
                print(f"[AHKPluginManager] Error terminating AHK: {e}")
            self._process = None
