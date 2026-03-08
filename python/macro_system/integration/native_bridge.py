"""
Native Bridge Module

Wrapper that provides Python fallback when C++ native module is unavailable.
Uses helxairo_native for high-performance input when available.
"""

from typing import Optional, Tuple, List
import time

# Try to import native module
try:
    import helxairo_native as _native
    NATIVE_AVAILABLE = True
    print("[NativeBridge] C++ native module loaded (v" + _native.__version__ + ")")
except ImportError as e:
    _native = None
    NATIVE_AVAILABLE = False
    print(f"[NativeBridge] Native module not available, using Python fallback. Error: {e}")

# Global singletons to prevent instance fragmentation
_engine_instance = None
_hook_instance = None
_simulator_instance = None

def get_native_engine():
    """Get or create the unified native MacroEngine instance."""
    global _engine_instance
    if _native and _engine_instance is None:
        try:
            _engine_instance = _native.MacroEngine()
            print("[NativeBridge] Unified Native Engine initialized")
        except Exception as e:
            print(f"[NativeBridge] Failed to initialize native engine: {e}")
    return _engine_instance

def get_native_hook():
    """Get or create the unified native InputHook instance."""
    global _hook_instance
    if _native and _hook_instance is None:
        try:
            _hook_instance = _native.InputHook()
            print("[NativeBridge] Unified Native Hook initialized")
        except Exception as e:
            print(f"[NativeBridge] Failed to initialize native hook: {e}")
    return _hook_instance

def get_native_simulator():
    """Get or create the unified native InputSimulator instance."""
    global _simulator_instance
    if _native and _simulator_instance is None:
        try:
            # Prefer getting simulator via engine if available (matches instance)
            engine = get_native_engine()
            if engine and hasattr(engine, 'get_simulator'):
                _simulator_instance = engine.get_simulator()
            else:
                _simulator_instance = _native.InputSimulator()
            print("[NativeBridge] Unified Native Simulator initialized")
        except Exception as e:
            print(f"[NativeBridge] Failed to initialize native simulator: {e}")
    return _simulator_instance


class NativeInputSimulator:
    """
    High-performance input simulator.
    Uses C++ native when available, falls back to Python.
    """
    
    def __init__(self):
        if NATIVE_AVAILABLE:
            self._native = _native.InputSimulator()
        else:
            # Fallback to Python implementation
            from ..core.input_simulator import InputSimulator as PyInputSimulator
            self._native = PyInputSimulator()
    
    def mouse_move(self, x: int, y: int, absolute: bool = True):
        self._native.mouse_move(x, y, absolute)
    
    def mouse_click(self, button: str = "left", count: int = 1):
        self._native.mouse_click(button, count)
    
    def mouse_down(self, button: str = "left"):
        self._native.mouse_down(button)
    
    def mouse_up(self, button: str = "left"):
        self._native.mouse_up(button)
    
    def key_tap(self, key: str, hold_ms: int = 0):
        self._native.key_tap(key, hold_ms)
    
    def key_down(self, key: str):
        self._native.key_down(key)
    
    def key_up(self, key: str):
        self._native.key_up(key)
    
    def get_cursor_position(self) -> Tuple[int, int]:
        return self._native.get_cursor_position()


class NativeTimer:
    """
    High-precision timer.
    Uses C++ busy-wait for sub-millisecond accuracy when native available.
    """
    
    def __init__(self):
        if NATIVE_AVAILABLE:
            self._native = _native.HighPrecisionTimer()
        else:
            self._native = None
            self._start = time.perf_counter()
    
    def now_micros(self) -> int:
        if self._native:
            return self._native.now_micros()
        return int((time.perf_counter() - self._start) * 1_000_000)
    
    def now_millis(self) -> float:
        if self._native:
            return self._native.now_millis()
        return (time.perf_counter() - self._start) * 1000
    
    def delay_micros(self, microseconds: int):
        if self._native:
            self._native.delay_micros(microseconds)
        else:
            # Python fallback - less precise
            time.sleep(microseconds / 1_000_000)
    
    def delay_millis(self, milliseconds: float):
        if self._native:
            self._native.delay_millis(milliseconds)
        else:
            time.sleep(milliseconds / 1000)


class NativeMacroEngine:
    """
    Native macro engine wrapper.
    Uses C++ engine for hooks and execution when available.
    """
    
    def __init__(self):
        self._use_native = NATIVE_AVAILABLE
        
        if self._use_native:
            self._engine = get_native_engine()
            self._simulator = get_native_simulator()
        else:
            from ..core.macro_engine import MacroEngine as PyMacroEngine
            self._engine = PyMacroEngine()
            self._simulator = None
        
        self._toggle_macros = {}  # Store toggle macro instances
        self._bindings = []
    
    def start(self):
        self._engine.start()
    
    def stop(self):
        self._engine.stop()
    
    def is_running(self) -> bool:
        return self._engine.is_running()
    
    def register_macro(self, macro_id: str, macro: Any):
        if self._use_native:
            # If it's a native macro object, register it directly
            self._engine.register_macro(macro_id, macro)
        else:
            self._engine.register_macro(macro_id, macro)

    def unregister_macro(self, macro_id: str):
        self._engine.unregister_macro(macro_id)

    def add_binding(self, binding: Any):
        if self._use_native:
            # Convert Python binding to native binding if needed
            # For now, let's assume it's already a native binding or compatible
            try:
                if not hasattr(binding, 'macro_id'): # Ensure it's a MacroBinding-like object
                     return
                     
                if not isinstance(binding, _native.MacroBinding):
                    n_binding = _native.MacroBinding()
                    n_binding.macro_id = binding.macro_id
                    n_binding.trigger_type = binding.trigger_type
                    if isinstance(binding.trigger_value, str):
                        n_binding.trigger_value = self._get_vk_code(binding.trigger_value)
                    else:
                        n_binding.trigger_value = binding.trigger_value
                    n_binding.event_type = binding.event_type
                    n_binding.layer = binding.layer
                    binding = n_binding
                self._engine.add_binding(binding)
            except Exception as e:
                print(f"[NativeBridge] Error adding binding: {e}")
        else:
            self._engine.add_binding(binding)

    def clear_bindings(self):
        self._engine.clear_bindings()

    def set_active_layer(self, layer: str):
        self._engine.set_active_layer(layer)

    def check_match_mouse(self, event, layer):
        if self._use_native:
            return self._engine.check_match_mouse(event, layer)
        return ""

    def check_match_keyboard(self, event, layer):
        if self._use_native:
            return self._engine.check_match_keyboard(event, layer)
        return ""

    def register_toggle_macro(self, macro_id: str, name: str, 
                               action_type: str, target: str,
                               interval_ms: float, trigger_key: str):
        """
        Register a toggle macro (auto-clicker style).
        
        action_type: "mouse_click" or "key_tap"
        target: button name or key name
        interval_ms: repeat interval in milliseconds
        trigger_key: hotkey to toggle on/off (e.g., "f6")
        """
        if self._use_native:
            # Create native toggle macro
            macro = _native.ToggleMacro(macro_id, name)
            
            # Set up repeat action
            action = _native.RepeatAction()
            if action_type == "mouse_click":
                action.type = _native.ActionType.MouseClick
            else:
                action.type = _native.ActionType.KeyTap
            action.target = target
            action.hold_ms = 0
            
            macro.set_repeat_action(action)
            macro.set_repeat_interval_ms(interval_ms)
            
            # Register with engine
            self._engine.register_macro(macro_id, macro)
            
            # Create binding
            binding = _native.MacroBinding()
            binding.macro_id = macro_id
            binding.trigger_type = "keyboard"
            binding.trigger_value = self._get_vk_code(trigger_key)
            binding.event_type = "down"
            binding.layer = "default"
            
            self._engine.add_binding(binding)
            self._toggle_macros[macro_id] = macro
        else:
            # Use Python implementation
            from ..macros.toggle_macro import ToggleMacro
            from ..macros.base_macro import MacroTrigger, MacroAction, TriggerType, ActionType
            
            if action_type == "mouse_click":
                action = MacroAction(type=ActionType.MOUSE_CLICK, button=target)
            else:
                action = MacroAction(type=ActionType.KEY_TAP, key=target, hold_ms=50)
            
            trigger = MacroTrigger(
                type=TriggerType.KEYBOARD,
                key=trigger_key,
                event="down"
            )
            
            macro = ToggleMacro(
                id=macro_id,
                name=name,
                trigger=trigger,
                actions=[action],
                repeat_interval_ms=interval_ms
            )
            
            self._engine.register_macro(macro_id, macro)
            self._toggle_macros[macro_id] = macro
    
    def is_toggle_on(self, macro_id: str) -> bool:
        if self._use_native:
            return self._engine.is_toggle_on(macro_id)
        else:
            macro = self._toggle_macros.get(macro_id)
            return macro.is_active if macro else False
    
    def cancel_all(self):
        if self._use_native:
            self._engine.cancel_all_macros()
        else:
            for macro in self._toggle_macros.values():
                if hasattr(macro, 'cancel'):
                    macro.cancel()
    
    def _get_vk_code(self, key: str) -> int:
        """Convert key name to Windows virtual key code."""
        key = key.lower()
        
        # Function keys
        if key.startswith('f') and key[1:].isdigit():
            num = int(key[1:])
            return 0x70 + (num - 1)  # VK_F1 = 0x70
        
        # Letters
        if len(key) == 1 and key.isalpha():
            return ord(key.upper())
        
        # Common keys
        vk_map = {
            'space': 0x20, 'enter': 0x0D, 'tab': 0x09,
            'escape': 0x1B, 'esc': 0x1B, 'backspace': 0x08,
            'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12,
            'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
            'insert': 0x2D, 'delete': 0x2E, 'home': 0x24, 'end': 0x23,
            'pageup': 0x21, 'pagedown': 0x22,
        }
        return vk_map.get(key, 0)


class NativeInputHook:
    """Native low-level hook wrapper."""
    def __init__(self):
        self._native = _native.InputHook() if NATIVE_AVAILABLE else None
        
    def set_mouse_callback(self, cb):
        if self._native: self._native.set_mouse_callback(cb)
        
    def set_keyboard_callback(self, cb):
        if self._native: self._native.set_keyboard_callback(cb)
        
    def start(self):
        if self._native:
            return self._native.start()
        return False
    
    def is_running(self):
        return self._native.is_running() if self._native else False
        
    def stop(self):
        if self._native: self._native.stop()
        
    def set_listen_to_move(self, enable: bool):
        if self._native: self._native.set_listen_to_move(enable)

class NativeHIDController:
    """Native HID communication wrapper."""
    def __init__(self):
        self._native = _native.HIDController() if NATIVE_AVAILABLE else None
        
    def connect(self):
        return self._native.connect() if self._native else False
        
    def set_button_mapping(self, index: int, code: int):
        return self._native.set_button_mapping(index, code) if self._native else False
        
    def get_battery_level(self):
        return self._native.get_battery_level() if self._native else -1

    def get_active_dpi_stage(self):
        return self._native.get_active_dpi_stage() if self._native else None

    def set_dpi_stage_value(self, index, dpi):
        return self._native.set_dpi_stage_value(index, dpi) if self._native else False

    def set_current_dpi_stage(self, index):
        return self._native.set_current_dpi_stage(index) if self._native else False

    def set_dpi_stages_count(self, count):
        return self._native.set_dpi_stages_count(count) if self._native else False

    def set_polling_rate(self, rate_hz):
        return self._native.set_polling_rate(rate_hz) if self._native else False

    def set_lod(self, lod_value):
        return self._native.set_lod(lod_value) if self._native else False

    def set_ripple(self, enabled):
        return self._native.set_ripple(enabled) if self._native else False

    def set_angle_snapping(self, enabled):
        return self._native.set_angle_snapping(enabled) if self._native else False

    def set_motion_sync(self, enabled):
        return self._native.set_motion_sync(enabled) if self._native else False

    def set_debounce_time(self, ms):
        return self._native.set_debounce_time(ms) if self._native else False

    def set_sensor_mode(self, mode):
        return self._native.set_sensor_mode(mode) if self._native else False

    def set_highest_performance(self, enabled):
        return self._native.set_highest_performance(enabled) if self._native else False

    def set_performance_time(self, val):
        return self._native.set_performance_time(val) if self._native else False

    def set_dpi_color(self, stage_index, r, g, b):
        return self._native.set_dpi_color(stage_index, r, g, b) if self._native else False

    def set_dpi_effect_mode(self, mode):
        return self._native.set_dpi_effect_mode(mode) if self._native else False

    def set_dpi_effect_brightness(self, level):
        return self._native.set_dpi_effect_brightness(level) if self._native else False

    def set_dpi_effect_speed(self, speed):
        return self._native.set_dpi_effect_speed(speed) if self._native else False

    def is_connected(self):
        return self._native.is_connected() if self._native else False

    def get_connection_type(self):
        if not self._native: return 0
        return self._native.get_connection_type()

    def disconnect(self):
        if self._native: self._native.disconnect()

def is_native_available() -> bool:
    """Check if native module is loaded."""
    return NATIVE_AVAILABLE
def get_timestamp() -> float:
    """Get high-precision timestamp."""
    return time.time()
