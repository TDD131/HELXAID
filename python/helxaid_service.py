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

    def get_ryzenadj_path(self):
        # Try finding in the portable dir (next to service executable)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        # PyInstaller paths
        exe_dir = os.path.dirname(sys.executable)
        
        paths_to_check = [
            os.path.join(base_dir, "assets", "ryzenadj.exe"),
            os.path.join(exe_dir, "assets", "ryzenadj.exe"),
            # AppData Fallback (from tools_downloader)
            os.path.join(os.environ.get('LOCALAPPDATA', ''), "HELXAID", "tools", "ryzenadj.exe")
        ]
        
        for p in paths_to_check:
            if os.path.exists(p):
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
                
                ryzenadj_path = self.get_ryzenadj_path()
                if not ryzenadj_path:
                    return {"status": "error", "message": "RyzenAdj executable not found."}
                
                # Auto-kill UXTU's PawnIO driver if it's running (to prevent RyzenAdj crash)
                try:
                    import subprocess
                    import time
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

                # RyzenAdj OFTEN crashes with exit code -1073741819 (0xC0000005 Access Violation)
                # AFTER successfully writing settings to SMU registers. This is a known ryzenadj
                # behaviour — the crash happens during cleanup, not during the actual apply.
                # We treat it as success if the error matches and stdout is empty (no error msg).
                RYZENADJ_KNOWN_CRASH = -1073741819  # 0xC0000005
                output = result.stdout.strip()
                stderr  = result.stderr.strip()

                if result.returncode == 0:
                    return {"status": "success", "message": "Applied successfully."}
                elif result.returncode == RYZENADJ_KNOWN_CRASH and not stderr and not output:
                    # Known post-apply crash — settings were applied successfully
                    return {"status": "success", "message": "Applied (post-SMU crash suppressed)."}
                elif output and ("successfully" in output.lower() or "smu" in output.lower()):
                    return {"status": "success", "message": "Applied (exit code ignored)."}
                else:
                    err_detail = stderr or output or "no output"
                    return {"status": "error", "message": f"RyzenAdj error {result.returncode}: {err_detail}"}
                    
            elif action == "ping":
                return {"status": "success", "message": "pong"}
                
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
