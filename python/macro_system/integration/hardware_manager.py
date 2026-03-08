"""
Hardware Manager Module

Centralizes all HID communication in a background thread to prevent UI stalling.
Implements a request-response queue and periodic state polling.
"""

import threading
import queue
import time
from typing import Optional, Any, Callable, Dict, List
from dataclasses import field, dataclass
from .native_bridge import NativeHIDController, is_native_available

@dataclass
class HardwareRequest:
    """A command to be executed on the HID device."""
    command: str  # 'get_battery', 'set_dpi', 'get_dpi_stage', 'set_mapping', etc.
    args: List[Any] = field(default_factory=list)
    callback: Optional[Callable[[Any], None]] = None
    priority: int = 0  # 0=Normal, 1=High

class HardwareManager(threading.Thread):
    """
    Background manager for Furycube HID communication.
    
    Prevents blocking the UI thread by moving all hidapi operations
    to this dedicated worker thread.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HardwareManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        super().__init__(name="HELXAIRO-HardwareManager", daemon=True)
        
        if is_native_available():
            print("[HardwareManager] Using native C++ HID controller")
            self.hid = NativeHIDController()
            self._use_native = True
        else:
            from FurycubeHID import FurycubeHID
            self.hid = FurycubeHID()
            self._use_native = False
        
        self.request_queue = queue.PriorityQueue()
        self.running = False
        self._ever_connected = False
        self._last_dpi_write = 0.0
        
        # State Cache
        self.state = {
            'connected': False,
            'connection_type': 'unknown',
            'battery_level': 0,
            'is_charging': False,
            'active_dpi_stage': 0,
            'last_seen': 0
        }
        self.state_lock = threading.Lock()
        
        # Subscriptions
        self.callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        self.polling_paused_until = 0
        self._initialized = True

    def start_manager(self):
        """Start the background thread."""
        if not self.running:
            self.running = True
            self.start()
            print("[HardwareManager] Background thread started")

    def stop_manager(self):
        """Stop the background thread."""
        self.running = False

    def enqueue(self, command: str, *args, callback: Optional[Callable] = None, priority: int = 0):
        """Add a command to the execution queue."""
        request = HardwareRequest(command, list(args), callback, priority)
        # PriorityQueue uses (priority, item) - lower number = higher priority
        self.request_queue.put((-priority, time.time(), request))

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        """Subscribe to hardware state updates."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def get_state(self) -> Dict[str, Any]:
        """Get a copy of the current hardware state."""
        with self.state_lock:
            return self.state.copy()

    def run(self):
        """Main loop for HID communication."""
        now = time.time()
        # STARTUP DELAY: Trigger first battery poll immediately upon connection
        # DPI poll after 5 seconds to reduce lock contention
        last_battery_poll = now - 65.0
        last_dpi_poll = now - 5.0
        last_connection_check = 0
        
        while self.running:
            try:
                # 1. Handle queued requests with timeout
                try:
                    # Non-blocking check for requests
                    _, _, request = self.request_queue.get(timeout=0.2)
                    self._process_request(request)
                    self.request_queue.task_done()
                except queue.Empty:
                    pass

                # 2. Maintenance: Connection Management
                now = time.time()
                
                # CRITICAL: Prioritize commands over polling.
                # If there are queued commands, skip polling entirely to prevent 
                # stale state from being read while writes are in flight.
                if not self.request_queue.empty():
                    time.sleep(0.01)
                    continue
                if now - last_connection_check > 5.0:
                    self._check_connection()
                    last_connection_check = now

                if not self.state['connected']:
                    time.sleep(0.5)
                    continue

                # 3. Periodic Polling (only if connected)
                if now < self.polling_paused_until:
                    # Polling paused to allow hardware set commands to settle
                    time.sleep(0.01)
                    continue

                # Poll DPI stage (Fast - 2s)
                # INTERNAL GUARD: Block cache updates for 10s after a write
                if now - getattr(self, '_last_dpi_write', 0) >= 10.0 and now - last_dpi_poll > 2.0:
                    self._update_dpi_state()
                    last_dpi_poll = now

                # Poll Battery (every 15s to quickly detect charging state changes).
                # Previously 60s which caused up to a 1-minute lag when cable was plugged in.
                if now - last_battery_poll > 5.0:
                    self._update_battery_state()
                    last_battery_poll = now

                # Release GIL in fast loops
                time.sleep(0.01)

            except Exception as e:
                print(f"[HardwareManager] Loop error: {e}")
                time.sleep(1.0)

    def _process_request(self, req: HardwareRequest):
        """Execute a single request on the HID device."""
        try:
            # 1. IMMEDIATE PAUSE: Block polling for 5.0s as soon as we start processing a write.
            # Increased to 5s to ensure total silence during the throttle period.
            if req.command.startswith('set_'):
                self.polling_paused_until = time.time() + 5.0

            connected = self.hid.is_connected() if self._use_native else self.hid.is_connected
            if not connected:
                if not self._ever_connected and req.command.startswith('set_'):
                    if req.callback: req.callback(None)
                    return
                if not self.hid.connect():
                    if req.callback: req.callback(None)
                    return

            result = None
            if req.command == 'set_button_mapping':
                result = self.hid.set_button_mapping(req.args[0], req.args[1])
            elif req.command == 'set_dpi_stage_value':
                result = self.hid.set_dpi_stage_value(req.args[0], req.args[1])
            elif req.command == 'set_current_dpi_stage':
                result = self.hid.set_current_dpi_stage(req.args[0])
                if result:
                    self._last_dpi_write = time.time()
                    with self.state_lock:
                        self.state['active_dpi_stage'] = req.args[0]
            elif req.command == 'set_dpi_stages_count':
                result = self.hid.set_dpi_stages_count(req.args[0])
                if result:
                    with self.state_lock:
                        self.state['dpi_stages_count'] = req.args[0]
            elif req.command == 'set_polling_rate':
                result = self.hid.set_polling_rate(req.args[0])
                if result:
                    with self.state_lock:
                        self.state['polling_rate'] = req.args[0]
            elif req.command == 'set_lod':
                result = self.hid.set_lod(req.args[0])
            elif req.command == 'set_ripple':
                result = self.hid.set_ripple(req.args[0])
            elif req.command == 'set_angle_snapping':
                result = self.hid.set_angle_snapping(req.args[0])
            elif req.command == 'set_motion_sync':
                result = self.hid.set_motion_sync(req.args[0])
            elif req.command == 'set_highest_performance':
                result = self.hid.set_highest_performance(req.args[0])
            elif req.command == 'set_performance_time':
                result = self.hid.set_performance_time(req.args[0])
            elif req.command == 'set_sensor_mode':
                result = self.hid.set_sensor_mode(req.args[0])
            elif req.command == 'set_dpi_effect_mode':
                result = self.hid.set_dpi_effect_mode(req.args[0])
            elif req.command == 'set_dpi_effect_brightness':
                result = self.hid.set_dpi_effect_brightness(req.args[0])
            elif req.command == 'set_dpi_effect_speed':
                result = self.hid.set_dpi_effect_speed(req.args[0])
            elif req.command == 'set_dpi_color':
                result = self.hid.set_dpi_color(req.args[0], req.args[1], req.args[2], req.args[3])
            elif req.command == 'force_reconnect':
                # Force a full disconnect + reconnect cycle so the UI picks up
                # a freshly enumerated device after USB/wireless drop.
                try:
                    if self._use_native:
                        self.hid.disconnect()
                    else:
                        self.hid.disconnect()
                except Exception:
                    pass
                # Reset connection state so _check_connection tries again immediately
                with self.state_lock:
                    self.state['connected'] = False
                    self.state['connection_type'] = 'unknown'
                self._check_connection()
                self._notify_subscribers()
            
            # THROTTLING: Mandatory 300ms delay after writes to prevent firmware flooding
            # This is essential for cheap MCUs in some FuryCube models.
            if req.command.startswith('set_'):
                time.sleep(0.300)

            if req.callback:
                req.callback(result)
                
        except Exception as e:
            print(f"[HardwareManager] Request error ({req.command}): {e}")
            if req.callback: req.callback(None)

    def _check_connection(self):
        """Verify connection status and prioritize wired.
        
        IMPORTANT: This method must NEVER chain to connect() from
        get_connection_type(). The native getConnectionType() was fixed
        to return 0 if not connected (instead of recursively calling connect()).
        Connection type is inferred from the cached product ID after connect().
        """
        try:
            if self._use_native:
                # Step 1: If not connected, attempt ONE connect call
                if not self.hid.is_connected():
                    self.hid.connect()
                
                is_connected = self.hid.is_connected()
                
                # Step 2: Get connection type ONLY if connected
                # get_connection_type() now returns 0 if not connected
                # (no recursive connect() call)
                if is_connected:
                    raw_type = self.hid.get_connection_type()
                    conn_type = 'wired' if raw_type == 1 else 'wireless' if raw_type == 2 else 'unknown'
                    self._ever_connected = True
                else:
                    conn_type = 'unknown'
            else:
                # Python fallback logic
                devices = self.hid.enumerate_devices()
                from FurycubeHID import FurycubePID
                has_wired = any(d.get('product_id') == FurycubePID.PID_WIRED for d in devices)
                has_wireless = any(d.get('product_id') == FurycubePID.PID for d in devices)
                
                curr_type = self.hid.connection_type
                target_type = 'unknown'
                if has_wired: target_type = 'wired'
                elif has_wireless: target_type = 'wireless'

                # Reconnect if type changed or not connected
                if target_type != 'unknown' and (not self.hid.is_connected or curr_type != target_type):
                    self.hid.disconnect()
                    if self.hid.connect():
                        print(f"[HardwareManager] Connected to {target_type} mouse")
                        self._ever_connected = True
                is_connected = self.hid.is_connected
                conn_type = self.hid.connection_type
            
            with self.state_lock:
                status_changed = (self.state['connected'] != is_connected or 
                                self.state['connection_type'] != conn_type)
                
                self.state['connected'] = is_connected
                self.state['connection_type'] = conn_type
                if is_connected:
                    self.state['last_seen'] = time.time()
                
            if status_changed and is_connected:
                print(f"[HardwareManager] Connected via {conn_type}")
            elif status_changed:
                print(f"[HardwareManager] Device disconnected")
                
            if status_changed:
                self._notify_subscribers()
        except Exception as e:
            print(f"[HardwareManager] Connection check failed: {e}")

    def _update_dpi_state(self):
        """Poll active DPI stage."""
        try:
            # Native returns int, Python returns int
            stage = self.hid.get_active_dpi_stage()
            should_notify = False
            if stage is not None and isinstance(stage, int):
                with self.state_lock:
                    if self.state['active_dpi_stage'] != stage:
                        self.state['active_dpi_stage'] = stage
                        should_notify = True
            # CRITICAL: Notify OUTSIDE of state_lock to prevent self-deadlock.
            # _notify_subscribers() calls get_state() which re-acquires state_lock.
            # threading.Lock is non-reentrant -- acquiring it twice from the same
            # thread causes permanent deadlock.
            if should_notify:
                self._notify_subscribers()
        except Exception as e:
            print(f"[HardwareManager] DPI update error: {e}")

    def _update_battery_state(self):
        """Poll battery level and charging state from the device.
        
        Priority order for data source:
        1. _get_furycube_battery_python() — direct HID raw commands, returns (perc, charging)
        2. Native C++ get_battery_level() — returns only int percentage, no charging info
           In this case, charging is INFERRED from connection type (wired = likely charging
           unless already at 100%).
        """
        try:
            furycube_b = self._get_furycube_battery_python()
            if furycube_b:
                # Best-quality source: raw HID report that includes charge current flag
                perc, charging = furycube_b
            else:
                # Native returns int (percentage) only — no charging bit available
                res = self.hid.get_battery_level()
                
                perc = 0
                charging = False
                
                if self._use_native:
                    if isinstance(res, int) and res >= 0:
                        perc = res
                        # Native driver has no charging flag. Infer from connection type:
                        # If the mouse is connected via USB cable AND battery is not full,
                        # it is very likely charging. This avoids the hardcoded False.
                        with self.state_lock:
                            conn_type = self.state.get('connection_type', 'unknown')
                        charging = (conn_type == 'wired') and (perc < 100)
                else:
                    # Python fallback returns tuple (perc, charging)
                    if res:
                        perc, charging = res
            
            with self.state_lock:
                prev_charging = self.state.get('is_charging', False)
                self.state['battery_level'] = perc
                self.state['is_charging'] = charging
            # CRITICAL: Notify OUTSIDE of state_lock (same deadlock prevention).
            # Only notify if charging state actually changed to avoid spurious UI redraws.
            self._notify_subscribers()
        except Exception as e:
            print(f"[HardwareManager] Battery update error: {e}")

    def _get_furycube_battery_python(self):
        """WebHub-style raw battery voltage processing specifically designed for Furycube devices"""
        try:
            import hid
            import time
            devices = hid.enumerate()
            for d in devices:
                if d['vendor_id'] == 0x3554 and d['product_id'] in (0xf5d5, 0xf511):
                    if d['usage_page'] == 0xff02:
                        try:
                            h = hid.device()
                            h.open_path(d['path'])
                            h.set_nonblocking(1)
                            # Ensure device is online before fetching battery (Cmd 3)
                            payload_online = [3] + [0]*14 + [0]
                            payload_online[15] = ((85 - (sum(payload_online[:15]) & 0xFF)) - 8) & 0xFF
                            h.write([8] + payload_online)
                            time.sleep(0.05)
                            online = False
                            for _ in range(3):
                                resp = h.read(64)
                                if resp and len(resp) >= 6 and resp[0] == 8 and resp[1] == 3:
                                    online = resp[6] == 1
                                    break
                                time.sleep(0.02)
                        
                            if online:
                                payload_batt = [4] + [0]*14 + [0]
                                payload_batt[15] = ((85 - (sum(payload_batt[:15]) & 0xFF)) - 8) & 0xFF
                                h.write([8] + payload_batt)
                                time.sleep(0.05)
                                for _ in range(5):
                                    resp = h.read(64)
                                    if resp and len(resp) >= 10 and resp[0] == 8 and resp[1] == 4:
                                        level = resp[6]
                                        charging = resp[7] == 1
                                        voltage = (resp[8] << 8) + resp[9]
                                        h.close()
                                        
                                        if voltage > 0: # Use curve calculation if voltage available
                                            curve = [3050, 3420, 3480, 3540, 3600, 3660, 3720, 3760, 3800, 3840, 3880, 3920, 3940, 3960, 3980, 4000, 4020, 4040, 4060, 4080, 4110]
                                            if voltage > curve[-1]:
                                                return (99 if charging else 100, charging)
                                            for idx, cv in enumerate(curve):
                                                if voltage < cv:
                                                    if idx == 0:
                                                        s = 0
                                                    else:
                                                        i_val = (curve[idx] - curve[idx-1]) / 5.0
                                                        s = (voltage - curve[idx-1]) / i_val + 5 * (idx - 1)
                                                    s = round(s)
                                                    if s > 0 and s != 15:
                                                        s += 1
                                                    return (min(100, s), charging)
                                            return (100, charging)
                                        else:
                                            return (level, charging)
                                    time.sleep(0.02)
                            h.close()
                        except Exception:
                            pass
        except Exception:
            pass
        return None

    def _notify_subscribers(self):
        """Fire callbacks with latest state."""
        state_copy = self.get_state()
        for callback in self.callbacks:
            try:
                callback(state_copy)
            except:
                pass

# Singleton access
def get_hardware_manager() -> HardwareManager:
    return HardwareManager()
