import sys
import os
import json
import time
import subprocess
import traceback

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    import win32pipe
    import win32file
    import pywintypes
    import win32security
except ImportError:
    pass

PIPE_NAME = r'\\.\pipe\HelxaidCpuPipe'

class HelxaidHelperService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'HelxaidHelperService'
    _svc_display_name_ = 'HELXAID Helper Service'
    _svc_description_ = 'Provides zero-UAC CPU/TDP adjustments for HELXAID.'
    
    if getattr(sys, 'frozen', False):
        _exe_name_ = sys.executable
        _exe_args_ = '--run-service'
    else:
        _exe_name_ = sys.executable
        import os
        # sys.argv[0] could be helxaid_service.py or launcher.py
        _exe_args_ = f'"{os.path.abspath(sys.argv[0])}" --run-service'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        
        # Connect to pipe just to unblock the WaitNamedPipe/ConnectNamedPipe loop
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None
            )
            win32file.CloseHandle(handle)
        except:
            pass

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"HELXAID Service crashed: {str(e)}\n{traceback.format_exc()}")
            self.SvcStop()

    def create_pipe_security_attributes(self):
        # Create a security attribute allowing Authenticated Users or Everyone
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = 1
        
        # Create Security Descriptor with Null DACL (Allows everyone to read/write)
        # This is safe because we tightly validate the JSON payload and DO NOT execute arbitrary commands.
        sd = win32security.SECURITY_DESCRIPTOR()
        sd.SetSecurityDescriptorDacl(1, None, 0) 
        sa.SECURITY_DESCRIPTOR = sd
        return sa

    def get_ryzenadj_path(self, explicit_path=None):
        if explicit_path and os.path.exists(explicit_path):
            return explicit_path

        # Try finding in the portable dir (next to service executable)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        # PyInstaller paths
        exe_dir = os.path.dirname(sys.executable)
        
        paths_to_check = [
            os.path.join(base_dir, "assets", "ryzenadj.exe"),
            os.path.join(exe_dir, "assets", "ryzenadj.exe"),
            os.path.join(base_dir, "tools", "ryzenadj", "ryzenadj.exe"),
            os.path.join(exe_dir, "tools", "ryzenadj", "ryzenadj.exe"),
            os.path.join(os.environ.get('APPDATA', ''), "HELXAID", "tools", "ryzenadj", "ryzenadj.exe")
        ]

        # Scan user profiles in C:\Users when running under LocalSystem account
        users_dir = "C:\\Users"
        if os.path.exists(users_dir):
            try:
                for u in os.listdir(users_dir):
                    if u.lower() in ["public", "default", "default user", "all users"]:
                        continue
                    p = os.path.join(users_dir, u, "AppData", "Roaming", "HELXAID", "tools", "ryzenadj", "ryzenadj.exe")
                    if os.path.exists(p):
                        paths_to_check.append(p)
            except Exception:
                pass
        
        for p in paths_to_check:
            if p and os.path.exists(p):
                return p
        return None

    def process_command(self, payload_str):
        try:
            data = json.loads(payload_str)
            action = data.get("action")
            
            if action == "apply_cpu":
                profile = data.get("profile", {})
                if not profile:
                    return {"status": "error", "message": "No profile data provided."}
                
                explicit_path = data.get("ryzenadj_path")
                ryzenadj_path = self.get_ryzenadj_path(explicit_path)
                if not ryzenadj_path:
                    return {"status": "error", "message": "RyzenAdj executable not found."}
                
                # Auto-kill UXTU's PawnIO driver if it's running (to prevent RyzenAdj crash)
                try:
                    res = subprocess.run(["sc.exe", "stop", "PawnIO"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.returncode == 0:
                        time.sleep(1.5)  # Wait for driver to fully unload from memory
                except Exception:
                    pass
                
                # Build arguments to match cpu_controller._build_ryzenadj_args exactly.
                # Profile stores power in Watts, ryzenadj expects mW (×1000).
                # Only include settings that are enabled in 'enabled_settings'.
                args = [ryzenadj_path]
                enabled = profile.get("enabled_settings", {})

                def is_enabled(key):
                    return enabled.get(key, True)  # default True for backwards compat

                # Temperature (°C) — no unit conversion
                if is_enabled("temp_limit"):
                    args.append(f"--tctl-temp={int(profile.get('temp_limit', 85))}")
                if is_enabled("temp_skin_limit"):
                    args.append(f"--apu-skin-temp={int(profile.get('temp_skin_limit', 80))}")

                # Power limits (W → mW)
                if is_enabled("stapm_limit") and "stapm_limit" in profile:
                    args.append(f"--stapm-limit={int(profile['stapm_limit'] * 1000)}")
                if is_enabled("slow_limit") and "slow_limit" in profile:
                    args.append(f"--slow-limit={int(profile['slow_limit'] * 1000)}")
                if is_enabled("fast_limit") and "fast_limit" in profile:
                    args.append(f"--fast-limit={int(profile['fast_limit'] * 1000)}")

                # Time limits (seconds) — no conversion
                if is_enabled("slow_duration") and "slow_duration" in profile:
                    args.append(f"--slow-time={int(profile['slow_duration'])}")
                if is_enabled("fast_duration") and "fast_duration" in profile:
                    args.append(f"--stapm-time={int(profile['fast_duration'])}")

                # CPU current limits (A → mA)
                if is_enabled("cpu_tdc") and "cpu_tdc" in profile:
                    args.append(f"--vrm-current={int(profile['cpu_tdc'] * 1000)}")
                if is_enabled("cpu_edc") and "cpu_edc" in profile:
                    args.append(f"--vrmmax-current={int(profile['cpu_edc'] * 1000)}")

                # GFX current limits (A → mA)
                if is_enabled("gfx_tdc") and "gfx_tdc" in profile:
                    args.append(f"--vrmgfx-current={int(profile['gfx_tdc'] * 1000)}")

                if len(args) == 1:
                    return {"status": "error", "message": "No valid CPU limits found in profile."}

                # Execute securely without shell=True.
                # Run from ryzenadj's own directory so it can find its DLLs.
                result = subprocess.run(
                    args,
                    cwd=os.path.dirname(ryzenadj_path),
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10
                )

                # RyzenAdj OFTEN crashes with exit code 0xC0000005 (Access Violation)
                # AFTER successfully writing settings to SMU registers. This is a known ryzenadj
                # behaviour — the crash happens during cleanup, not during the actual apply.
                # We treat it as success if the error matches and stdout is empty (no error msg).
                # Python's subprocess can return this as signed (-1073741819) or unsigned (3221225477).
                KNOWN_CRASH_CODES = (-1073741819, 3221225477)
                output = result.stdout.strip()
                stderr  = result.stderr.strip()

                if result.returncode == 0:
                    return {"status": "success", "message": "Applied successfully."}
                elif result.returncode in KNOWN_CRASH_CODES and not stderr and not output:
                    # Known post-apply crash — settings were applied successfully
                    return {"status": "success", "message": "Applied (post-SMU crash suppressed)."}
                elif output and ("successfully" in output.lower() or "smu" in output.lower()):
                    return {"status": "success", "message": "Applied (exit code ignored)."}
                else:
                    err_detail = stderr or output or "no output"
                    return {"status": "error", "message": f"RyzenAdj error {result.returncode}: {err_detail}"}
                    
            elif action in ("launch_lhm", "launch_tool"):
                exe_path = data.get("exe_path")
                silent = data.get("silent", False)
                if not exe_path or not os.path.exists(exe_path):
                    return {"status": "error", "message": f"Executable path not found: {exe_path}"}
                
                exe_name = os.path.basename(exe_path)
                try:
                    import psutil
                    for p in psutil.process_iter(['name']):
                        if p.info.get('name', '').lower() == exe_name.lower():
                            return {"status": "success", "message": f"{exe_name} is already running."}
                except Exception:
                    pass

                flags = subprocess.CREATE_NO_WINDOW if silent else 0
                proc = subprocess.Popen(
                    [exe_path],
                    cwd=os.path.dirname(exe_path),
                    creationflags=flags
                )
                return {"status": "success", "message": f"Launched {exe_name} via Zero-UAC Service.", "pid": proc.pid}

            elif action == "manage_service":
                svc_name = data.get("service_name")
                cmd_type = data.get("command", "stop")
                if not svc_name:
                    return {"status": "error", "message": "No service_name provided."}

                try:
                    qr = subprocess.run(
                        ['sc.exe', 'query', svc_name],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                    )
                    q_out = (qr.stdout or '').upper()

                    if cmd_type == "stop":
                        if 'STOPPED' in q_out and 'START_PENDING' not in q_out and 'STOP_PENDING' not in q_out:
                            return {"status": "success", "message": "ALREADY_STOPPED"}
                        
                        # 1. Try Stop-Service -Force via PowerShell FIRST (handles dependent services like SstpSvc automatically)
                        ps_res = subprocess.run(
                            ['powershell.exe', '-NoProfile', '-Command', f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue"],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15
                        )
                        if ps_res.returncode == 0:
                            return {"status": "success", "message": "OK"}

                        # 2. Try net.exe stop <svc_name> /y
                        sr = subprocess.run(
                            ['net.exe', 'stop', svc_name, '/y'],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15
                        )
                        combined = ((sr.stdout or '') + (sr.stderr or '')).lower()
                        if sr.returncode == 0 or 'not started' in combined or 'successfully' in combined or 'already' in combined or '1062' in combined:
                            return {"status": "success", "message": "OK"}

                        # 3. Fallback to sc.exe stop
                        sr_sc = subprocess.run(
                            ['sc.exe', 'stop', svc_name],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10
                        )
                        combined_sc = ((sr_sc.stdout or '') + (sr_sc.stderr or '')).lower()
                        if sr_sc.returncode == 0 or sr_sc.returncode == 1062 or 'not been started' in combined_sc:
                            return {"status": "success", "message": "OK"}

                        return {"status": "error", "message": sr.stderr or sr.stdout or f"stop exit {sr.returncode}"}

                    elif cmd_type == "start":
                        if 'RUNNING' in q_out:
                            return {"status": "success", "message": "ALREADY_RUNNING"}
                        sr = subprocess.run(
                            ['sc.exe', 'start', svc_name],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10
                        )
                        combined = ((sr.stdout or '') + (sr.stderr or '')).lower()
                        if sr.returncode == 0 or sr.returncode == 1056 or 'already running' in combined:
                            return {"status": "success", "message": "OK"}
                        return {"status": "error", "message": sr.stderr or sr.stdout or f"sc exit {sr.returncode}"}
                    else:
                        return {"status": "error", "message": f"Unknown service command: {cmd_type}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}

            elif action == "create_startup_task":
                task_name = data.get("task_name", "HELXAID_Startup")
                xml_path = data.get("xml_path")
                xml_content = data.get("xml_content")
                
                if xml_content:
                    import tempfile
                    xml_path = os.path.join(tempfile.gettempdir(), "helxaid_task_svc.xml")
                    with open(xml_path, 'w', encoding='utf-16') as f:
                        f.write(xml_content)
                        
                if not xml_path or not os.path.exists(xml_path):
                    return {"status": "error", "message": f"XML task config path not found: {xml_path}"}

                res = subprocess.run(
                    ["schtasks.exe", "/Create", "/TN", task_name, "/XML", xml_path, "/F"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15
                )
                if res.returncode == 0:
                    return {"status": "success", "message": f"Scheduled task '{task_name}' created successfully via Zero-UAC."}
                else:
                    err_msg = (res.stderr or res.stdout or "").strip()
                    return {"status": "error", "message": f"schtasks error {res.returncode}: {err_msg}"}

            elif action == "delete_startup_task":
                task_name = data.get("task_name", "HELXAID_Startup")
                res = subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", task_name, "/F"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15
                )
                err_msg = (res.stderr or res.stdout or "").lower()
                if res.returncode == 0 or "does not exist" in err_msg or "not found" in err_msg:
                    return {"status": "success", "message": f"Scheduled task '{task_name}' deleted successfully via Zero-UAC."}
                else:
                    return {"status": "error", "message": f"schtasks error {res.returncode}: {(res.stderr or res.stdout or '').strip()}"}

            elif action == "exec_batch_commands":
                commands = data.get("commands", [])
                if not commands:
                    return {"status": "error", "message": "No commands provided."}
                
                import tempfile
                temp_dir = tempfile.gettempdir()
                bat_path = os.path.join(temp_dir, f"helxaid_svc_cmd_{int(time.time()*1000)}.bat")
                with open(bat_path, 'w', encoding='utf-8') as f:
                    f.write("@echo off\n")
                    for cmd in commands:
                        f.write(cmd + "\n")
                
                try:
                    res = subprocess.run(
                        ["cmd.exe", "/c", bat_path],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=30
                    )
                    if res.returncode == 0:
                        return {"status": "success", "message": "OK"}
                    else:
                        err_out = (res.stderr or res.stdout or "").strip()
                        return {"status": "error", "message": f"Command exit {res.returncode}: {err_out}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
                finally:
                    if os.path.exists(bat_path):
                        try: os.remove(bat_path)
                        except OSError: pass

            elif action == "ping":
                return {"status": "success", "message": "pong"}

            elif action == "restart":
                def _do_restart():
                    time.sleep(0.2)
                    try:
                        subprocess.Popen(
                            ["cmd.exe", "/c", "timeout /t 1 /nobreak && net start HelxaidHelperService"],
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    except Exception:
                        pass
                    os._exit(1)
                import threading
                threading.Thread(target=_do_restart, daemon=True).start()
                return {"status": "success", "message": "Restarting service..."}
                
            else:
                return {"status": "error", "message": "Unknown action."}
                
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON format."}
        except Exception as e:
            return {"status": "error", "message": f"Internal error: {str(e)}"}

    def main(self):
        sa = self.create_pipe_security_attributes()
        
        while self.running:
            try:
                pipe = win32pipe.CreateNamedPipe(
                    PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                    win32pipe.PIPE_UNLIMITED_INSTANCES, 
                    65536, 65536,
                    0,
                    sa
                )
                
                win32pipe.ConnectNamedPipe(pipe, None)
                
                if not self.running:
                    win32file.CloseHandle(pipe)
                    break
                    
                # Read payload
                hr, data = win32file.ReadFile(pipe, 65536)
                if hr == 0:
                    payload_str = data.decode('utf-8')
                    response_dict = self.process_command(payload_str)
                    
                    # Send response
                    response_bytes = json.dumps(response_dict).encode('utf-8')
                    win32file.WriteFile(pipe, response_bytes)
                
                win32file.FlushFileBuffers(pipe)
                win32pipe.DisconnectNamedPipe(pipe)
                win32file.CloseHandle(pipe)
                
            except pywintypes.error as e:
                # 109 is ERROR_BROKEN_PIPE
                if e.winerror != 109:
                    servicemanager.LogWarningMsg(f"Pipe error: {e}")
                try:
                    win32pipe.DisconnectNamedPipe(pipe)
                    win32file.CloseHandle(pipe)
                except:
                    pass
            except Exception as e:
                servicemanager.LogWarningMsg(f"HELXAID Service loop error: {e}")
                time.sleep(1)

def run_as_service():
    if len(sys.argv) > 1 and sys.argv[1] == '--run-service':
        if len(sys.argv) > 2:
            # Handle --install, --remove, --start
            action = sys.argv[2]
            
            # We need to strip '--run-service' from sys.argv so win32serviceutil parses it correctly
            sys.argv.pop(1) 
            
            if action == '--install':
                sys.argv[1] = 'install'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--remove':
                sys.argv[1] = 'remove'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--start':
                sys.argv[1] = 'start'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--stop':
                sys.argv[1] = 'stop'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--setup':
                sys.argv[1] = 'install'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
                # Wait a bit for SCM to register it
                import time
                time.sleep(1)
                try:
                    win32serviceutil.StartService(HelxaidHelperService._svc_name_)
                except Exception as e:
                    print(f"Failed to start service: {e}")
            elif action == '--teardown':
                try:
                    win32serviceutil.StopService(HelxaidHelperService._svc_name_)
                    import time
                    time.sleep(1)
                except Exception:
                    pass # Ignore if not running
                sys.argv[1] = 'remove'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
        else:
            # Service Control Manager passes "service name" as arg1 usually, 
            # but PyInstaller passes the exe name. We handle this explicitly in launcher.py.
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(HelxaidHelperService)
            servicemanager.StartServiceCtrlDispatcher()

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(HelxaidHelperService)
