"""
Macro Engine Module

Central coordinator for macro execution, state management, and event routing.
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum
import time

from .input_listener import InputListener, InputEvent, MouseEvent, KeyboardEvent, EventType, MouseButton
from .input_simulator import InputSimulator
from .timer_manager import TimerManager, precise_time
from ..integration.native_bridge import is_native_available


class MacroState(Enum):
    """Possible states of a macro execution."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ExecutionContext:
    """Context passed to macro execution, providing access to engine services."""
    
    engine: 'MacroEngine'
    simulator: InputSimulator
    timer: TimerManager
    
    # Event that triggered this execution
    trigger_event: Optional[InputEvent] = None
    
    # Modifier state at trigger time
    modifiers: Dict[str, bool] = field(default_factory=dict)
    
    # For gesture macros
    gesture_points: List[tuple] = field(default_factory=list)
    
    # Cancellation token
    cancelled: bool = False
    
    # Custom data storage for macro scripts
    data: Dict[str, Any] = field(default_factory=dict)
    
    def check_cancelled(self):
        """Raise if execution was cancelled."""
        if self.cancelled:
            raise asyncio.CancelledError("Macro execution cancelled")
            
    async def delay(self, ms: float):
        """Async delay that respects cancellation."""
        self.check_cancelled()
        await asyncio.sleep(ms / 1000)
        self.check_cancelled()


@dataclass
class MacroBinding:
    """Binding between a trigger and a macro."""
    macro_id: str
    trigger_type: str  # "mouse", "keyboard", "gesture"
    trigger_value: Any  # Button, key code, gesture pattern
    event_type: str  # "down", "up", "click"
    conditions: List[Any] = field(default_factory=list)
    layer: str = "default"


class MacroEngine:
    """
    Central macro execution engine.
    
    Responsibilities:
    - Route input events to appropriate macros
    - Manage macro execution lifecycle
    - Handle toggle states
    - Coordinate with layer system
    """
    
    def __init__(self):
        # Core components
        self.input_listener = InputListener()
        self.input_simulator = InputSimulator()
        self.timer_manager = TimerManager()
        
        # Execution state
        self._running = False
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_thread: Optional[threading.Thread] = None
        
        # Macro registry
        self._macros: Dict[str, Any] = {}  # macro_id -> macro instance
        
        # Optimized bindings: {type: {value: [bindings]}}
        self._bindings: Dict[str, Dict[Any, List[MacroBinding]]] = {
            "mouse": {},
            "keyboard": {},
            "gesture": {}
        }
        
        # Running macros
        self._running_macros: Dict[str, asyncio.Task] = {}
        self._running_contexts: Dict[str, ExecutionContext] = {}  # Track contexts for cancellation
        self._macro_states: Dict[str, MacroState] = {}
        
        # Toggle states (for toggle macros)
        self._toggle_states: Dict[str, bool] = {}
        self._active_layer = "default"
        
        # Native optimization
        self._native_engine = None
        if is_native_available():
            from ..integration.native_bridge import get_native_engine
            self._native_engine = get_native_engine()
            print("[MacroEngine] Using unified native C++ matching engine")
        
        # Callbacks
        self._on_macro_start: Optional[Callable[[str], None]] = None
        self._on_macro_end: Optional[Callable[[str, MacroState], None]] = None
        
        # Setup input callbacks
        self.input_listener.on_mouse_event = self._handle_mouse_event
        self.input_listener.on_keyboard_event = self._handle_keyboard_event
        
    def start(self):
        """Start the macro engine."""
        if self._running:
            return
            
        self._running = True
        
        # Start async event loop in separate thread
        self._async_loop = asyncio.new_event_loop()
        self._async_thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True
        )
        self._async_thread.start()
        
        # Start components
        self.timer_manager.start()
        self.input_listener.start()
        
        print("[MacroEngine] Started")
        
    def stop(self):
        """Stop the macro engine."""
        self._running = False
        
        # Cancel all running macros
        self.cancel_all_macros()
        
        # Stop components
        self.input_listener.stop()
        self.timer_manager.stop()
        
        # Stop async loop
        if self._async_loop:
            self._async_loop.call_soon_threadsafe(self._async_loop.stop)
            
        if self._async_thread:
            self._async_thread.join(timeout=1.0)
            
        print("[MacroEngine] Stopped")
        
    def _run_async_loop(self):
        """Run the async event loop."""
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()
        
    # ==================== MACRO REGISTRATION ====================
    
    def register_macro(self, macro_id: str, macro: Any):
        """Register a macro instance."""
        self._macros[macro_id] = macro
        self._macro_states[macro_id] = MacroState.IDLE
        
    def unregister_macro(self, macro_id: str):
        """Unregister a macro."""
        self.cancel_macro(macro_id)
        self._macros.pop(macro_id, None)
        self._macro_states.pop(macro_id, None)
        self._toggle_states.pop(macro_id, None)
        
    def add_binding(self, binding: MacroBinding):
        """Add a trigger binding for a macro with O(1) lookup-ready structure."""
        b_type = binding.trigger_type
        # Ensure trigger_value is hashable/valid
        b_val = binding.trigger_value
        
        # Initialize list if missing
        if b_val not in self._bindings[b_type]:
            self._bindings[b_type][b_val] = []
            
        self._bindings[b_type][b_val].append(binding)
        
        if self._native_engine and b_type != "gesture":
            from ..integration.native_bridge import _native
            nb = _native.MacroBinding()
            nb.macro_id = binding.macro_id
            nb.trigger_type = b_type
            # Handle native button vs vkCode
            if b_type == "mouse":
                btn_map = {MouseButton.LEFT: 1, MouseButton.RIGHT: 2, MouseButton.MIDDLE: 3, MouseButton.X1: 4, MouseButton.X2: 5}
                # Handle both enum and raw int
                nb.trigger_value = btn_map.get(b_val, b_val.value if hasattr(b_val, 'value') else 0)
            else:
                if isinstance(b_val, int):
                    nb.trigger_value = b_val
                elif isinstance(b_val, str):
                    nb.trigger_value = self._get_vk_code(b_val)
                else:
                    nb.trigger_value = 0
            
            nb.event_type = binding.event_type
            nb.layer = binding.layer
            self._native_engine.add_binding(nb)
            
    def _get_vk_code(self, key: str) -> int:
        """Convert key name to Windows virtual key code."""
        key = key.lower()
        if key.startswith('f') and key[1:].isdigit():
            return 0x70 + (int(key[1:]) - 1)
        if len(key) == 1 and key.isalpha():
            return ord(key.upper())
            
        vk_map = {
            'space': 0x20, 'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'escape': 0x1B,
            'backspace': 0x08, 'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12,
            'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
            'insert': 0x2D, 'delete': 0x2E, 'home': 0x24, 'end': 0x23,
            'pageup': 0x21, 'pagedown': 0x22, 'printscreen': 0x2C,
            'lwin': 0x5B, 'rwin': 0x5C, 'capslock': 0x14, 'numlock': 0x90,
            'scrolllock': 0x91, 'pause': 0x13
        }
        return vk_map.get(key, 0)
        
    def remove_bindings(self, macro_id: str):
        """Remove all bindings for a macro."""
        for b_type in self._bindings:
            for b_val in self._bindings[b_type]:
                self._bindings[b_type][b_val] = [
                    b for b in self._bindings[b_type][b_val] if b.macro_id != macro_id
                ]
        
    def clear_bindings(self):
        """Clear all bindings."""
        for b_type in self._bindings:
            self._bindings[b_type].clear()
        if self._native_engine:
            self._native_engine.clear_bindings()
        
    # ==================== LAYER SYSTEM ====================
    
    def set_layer_system(self, layer_system: Any):
        """Set the layer system reference."""
        self._layer_system = layer_system
        
    def set_active_layer(self, layer: str):
        """Set the active layer for macro lookups."""
        self._active_layer = layer
        
    # ==================== EVENT HANDLING ====================
    
    def _handle_mouse_event(self, event: MouseEvent) -> bool:
        """Handle mouse event using native engine or Python lookup."""
        if not self._running:
            return False
            
        # NATIVE PATH: Fast C++ matching
        native_ev = self.input_listener.current_native_event
        if native_ev and self._native_engine:
            macro_id = self._native_engine.check_match_mouse(native_ev, self._active_layer)
            if macro_id:
                self._trigger_macro(macro_id, InputEvent(mouse=event))
                return True
            return False

        # FALLBACK PATH: Dictionary lookup by button
        possible_bindings = self._bindings["mouse"].get(event.button)
        if not possible_bindings:
            return False
            
        suppress = False
        active_layer = self._active_layer
        
        for binding in possible_bindings:
            # Match layer
            if binding.layer != active_layer and binding.layer != "*":
                continue
                
            # Match event type
            if binding.event_type == "down" and event.type != EventType.MOUSE_DOWN:
                continue
            if binding.event_type == "up" and event.type != EventType.MOUSE_UP:
                continue
                
            # Check conditions (modifier states are cached, so this is fast)
            if not self._check_conditions(binding.conditions):
                continue
                
            # Trigger macro (asynchronously)
            self._trigger_macro(binding.macro_id, InputEvent(mouse=event))
            suppress = True
                
        return suppress
        
    def _handle_keyboard_event(self, event: KeyboardEvent) -> bool:
        """Handle keyboard event using native engine or Python lookup."""
        if not self._running:
            return False
            
        # NATIVE PATH: Fast C++ matching
        native_ev = self.input_listener.current_native_event
        if native_ev and self._native_engine:
            macro_id = self._native_engine.check_match_keyboard(native_ev, self._active_layer)
            if macro_id:
                self._trigger_macro(macro_id, InputEvent(keyboard=event))
                return True
            return False
            
        # FAST PATH: Check both key_code and key_name in dictionary
        bindings_code = self._bindings["keyboard"].get(event.key_code, [])
        bindings_name = self._bindings["keyboard"].get(event.key_name, [])
        possible_bindings = bindings_code + bindings_name
        
        if not possible_bindings:
            return False
            
        suppress = False
        active_layer = self._active_layer
        
        for binding in possible_bindings:
            # Match layer
            if binding.layer != active_layer and binding.layer != "*":
                continue
                
            # Match event type
            if binding.event_type == "down" and event.type != EventType.KEY_DOWN:
                continue
            if binding.event_type == "up" and event.type != EventType.KEY_UP:
                continue
                
            # Check conditions
            if not self._check_conditions(binding.conditions):
                continue
                
            # Trigger macro
            self._trigger_macro(binding.macro_id, InputEvent(keyboard=event))
            suppress = True
                
        return suppress
        
    def _check_conditions(self, conditions: List[Any]) -> bool:
        """Evaluate condition list. Returns True if all conditions pass."""
        if not conditions:
            return True
            
        modifiers = self.input_listener.get_modifier_state()
        
        for condition in conditions:
            if hasattr(condition, 'evaluate'):
                if not condition.evaluate(self, modifiers):
                    return False
                    
        return True
        
    # ==================== MACRO EXECUTION ====================
    
    def _trigger_macro(self, macro_id: str, trigger_event: Optional[InputEvent] = None):
        """Trigger execution of a macro."""
        macro = self._macros.get(macro_id)
        if not macro:
            return
            
        # Handle toggle macros
        if hasattr(macro, 'is_toggle') and macro.is_toggle:
            current = self._toggle_states.get(macro_id, False)
            self._toggle_states[macro_id] = not current
            
            if not self._toggle_states[macro_id]:
                # Toggle off - cancel running macro
                self.cancel_macro(macro_id)
                return
                
        # Cancel existing execution if running
        if macro_id in self._running_macros:
            if hasattr(macro, 'allow_overlap') and not macro.allow_overlap:
                self.cancel_macro(macro_id)
                
        # Create execution context
        context = ExecutionContext(
            engine=self,
            simulator=self.input_simulator,
            timer=self.timer_manager,
            trigger_event=trigger_event,
            modifiers=self.input_listener.get_modifier_state()
        )
        
        # Schedule async execution
        if self._async_loop:
            future = asyncio.run_coroutine_threadsafe(
                self._execute_macro(macro_id, macro, context),
                self._async_loop
            )
            
    async def _execute_macro(self, macro_id: str, macro: Any, context: ExecutionContext):
        """Execute a macro asynchronously."""
        self._macro_states[macro_id] = MacroState.RUNNING
        
        if self._on_macro_start:
            self._on_macro_start(macro_id)
            
        task = asyncio.current_task()
        if task:
            self._running_macros[macro_id] = task
            self._running_contexts[macro_id] = context  # Store context for cancellation
            
        try:
            await macro.execute(context)
            self._macro_states[macro_id] = MacroState.COMPLETED
            
        except asyncio.CancelledError:
            self._macro_states[macro_id] = MacroState.CANCELLED
            
        except Exception as e:
            self._macro_states[macro_id] = MacroState.ERROR
            print(f"[MacroEngine] Macro {macro_id} error: {e}")
            
        finally:
            self._running_macros.pop(macro_id, None)
            self._running_contexts.pop(macro_id, None)  # Cleanup context
            
            if self._on_macro_end:
                self._on_macro_end(macro_id, self._macro_states[macro_id])
                
    def cancel_macro(self, macro_id: str):
        """Cancel a running macro."""
        # Set context cancelled flag first for immediate effect
        context = self._running_contexts.get(macro_id)
        if context:
            context.cancelled = True
        
        # Then cancel the asyncio task
        task = self._running_macros.get(macro_id)
        if task:
            task.cancel()
            
        self._toggle_states.pop(macro_id, None)
        
    def cancel_all_macros(self):
        """Cancel all running macros."""
        for macro_id in list(self._running_macros.keys()):
            self.cancel_macro(macro_id)
            
        self._toggle_states.clear()
        
    # ==================== STATE QUERIES ====================
    
    def get_macro_state(self, macro_id: str) -> MacroState:
        """Get current state of a macro."""
        return self._macro_states.get(macro_id, MacroState.IDLE)
        
    def is_macro_running(self, macro_id: str) -> bool:
        """Check if a macro is currently running."""
        return macro_id in self._running_macros
        
    def is_toggle_on(self, macro_id: str) -> bool:
        """Check if a toggle macro is currently ON."""
        return self._toggle_states.get(macro_id, False)
        
    def set_toggle_state(self, macro_id: str, state: bool):
        """Manually set toggle state."""
        self._toggle_states[macro_id] = state
        
    def get_running_macros(self) -> List[str]:
        """Get list of currently running macro IDs."""
        return list(self._running_macros.keys())

    # Compatibility for InputListener callbacks when using native hooks
    @property
    def _native_hook_event(self):
        """Access the raw native event if currently processing one."""
        # This would be set by InputListener during its callback
        return getattr(self.input_listener, '_current_native_event', None)
