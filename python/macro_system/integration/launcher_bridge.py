"""
Launcher Bridge Module

Integrates the macro system with HELXAID lifecycle.
Uses C++ native module for high-performance when available.
"""

import os
from typing import Optional, Any, TYPE_CHECKING
from pathlib import Path

# Check for native module availability
try:
    from .native_bridge import NATIVE_AVAILABLE, NativeInputSimulator, NativeTimer
    if NATIVE_AVAILABLE:
        print("[LauncherBridge] Native C++ acceleration enabled")
except ImportError:
    NATIVE_AVAILABLE = False
    print("[LauncherBridge] Using Python implementation")

if TYPE_CHECKING:
    from ..core.macro_engine import MacroEngine
    from ..profiles.profile_manager import ProfileManager
    from ..profiles.layer_system import LayerSystem
    from ..detection.app_detector import AppDetector


class LauncherBridge:
    """
    Bridge between HELXAID and the macro system.
    
    Handles:
    - Macro system lifecycle (start/stop with launcher)
    - Game launch/exit events
    - Profile auto-switching based on game
    - Settings integration
    """
    
    def __init__(self, launcher_ref: Optional[Any] = None):
        self._launcher = launcher_ref
        
        # Macro system components
        self._engine: Optional['MacroEngine'] = None
        self._profile_manager: Optional['ProfileManager'] = None
        self._layer_system: Optional['LayerSystem'] = None
        self._app_detector: Optional['AppDetector'] = None
        
        # State
        self._initialized = False
        self._current_game: Optional[str] = None
        self._game_profile: Optional[str] = None  # Profile active due to game
        
        # Paths
        script_dir = Path(__file__).parent.parent.parent
        self._profiles_dir = script_dir / "macro_profiles"
        self._scripts_dir = script_dir / "macro_scripts"
        
    def initialize(self):
        """Initialize the macro system."""
        if self._initialized:
            return
            
        from ..core.macro_engine import MacroEngine
        from ..profiles.profile_manager import ProfileManager
        from ..profiles.layer_system import LayerSystem
        from ..detection.app_detector import AppDetector
        
        # Create directories
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._scripts_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self._profile_manager = ProfileManager(str(self._profiles_dir))
        self._profile_manager.load_profiles()
        
        self._layer_system = LayerSystem()
        
        self._engine = MacroEngine()
        self._engine.set_layer_system(self._layer_system)
        
        self._app_detector = AppDetector()
        self._app_detector.on_app_change(self._on_app_change)
        
        # Connect profile changes
        self._profile_manager.on_profile_change(self._on_profile_change)
        self._layer_system.on_layer_change(self._on_layer_change)
        
        self._initialized = True
        print("[LauncherBridge] Macro system initialized")
    
    @property
    def simulator(self):
        """Get the input simulator from the engine."""
        if self._engine:
            return self._engine.input_simulator
        return None
    
    @property
    def input_listener(self):
        """Get the input listener from the engine."""
        if self._engine:
            return self._engine.input_listener
        return None
        
    def start(self):
        """Start the macro system."""
        if not self._initialized:
            self.initialize()
            
        self._engine.start()
        self._app_detector.start()
        
        # Activate default profile
        self._profile_manager.activate_profile("default")
        self._load_profile_macros("default")
        
        print("[LauncherBridge] Macro system started")
        
    def stop(self):
        """Stop the macro system."""
        if self._engine:
            self._engine.stop()
        if self._app_detector:
            self._app_detector.stop()
            
        print("[LauncherBridge] Macro system stopped")
        
    def shutdown(self):
        """Full shutdown with cleanup."""
        self.stop()
        
        if self._profile_manager:
            self._profile_manager.save_all()
            
        self._initialized = False
        print("[LauncherBridge] Macro system shutdown complete")
        
    # ==================== GAME EVENTS ====================
    
    def on_game_launch(self, game_name: str, process_name: str):
        """Called when a game is launched from the launcher."""
        self._current_game = process_name
        
        # Check for game-specific profile
        profile = self._profile_manager.get_profile_for_app(process_name)
        if profile:
            self._game_profile = profile.id
            self._profile_manager.activate_profile(profile.id)
            self._load_profile_macros(profile.id)
            print(f"[LauncherBridge] Activated game profile: {profile.name}")
            
    def on_game_exit(self, game_name: str):
        """Called when a game exits."""
        self._current_game = None
        
        # Return to default profile if we switched for a game
        if self._game_profile:
            self._game_profile = None
            self._profile_manager.activate_profile("default")
            self._load_profile_macros("default")
            print("[LauncherBridge] Returned to default profile")
            
    # ==================== PROFILE MANAGEMENT ====================
    
    def _on_app_change(self, process_name: str, window_title: str):
        """Handle foreground app change."""
        # Skip if we're tracking a game from launcher
        if self._current_game:
            return
            
        # Check for app-specific profile
        profile = self._profile_manager.get_profile_for_app(process_name)
        if profile:
            if self._profile_manager.active_profile != profile:
                self._profile_manager.activate_profile(profile.id)
                self._load_profile_macros(profile.id)
                
    def _on_profile_change(self, old_profile, new_profile):
        """Handle profile change."""
        if new_profile:
            self._layer_system.reset_to_default()
            
    def _on_layer_change(self, old_layer: str, new_layer: str):
        """Handle layer change."""
        if self._engine:
            self._engine.set_active_layer(new_layer)
            
    def _load_profile_macros(self, profile_id: str):
        """Load macros for a profile into the engine."""
        if not self._engine or not self._profile_manager:
            return
            
        # Clear current bindings
        self._engine.clear_bindings()
        
        # Get macros for profile
        macros = self._profile_manager.get_macros_for_profile(profile_id)
        
        # Register each macro
        for macro in macros:
            if not macro.enabled:
                continue
                
            self._engine.register_macro(macro.id, macro)
            
            # Create binding from trigger
            if macro.trigger:
                from ..core.macro_engine import MacroBinding
                from ..core.input_listener import MouseButton
                
                binding = MacroBinding(
                    macro_id=macro.id,
                    trigger_type=self._trigger_type_to_string(macro.trigger.type),
                    trigger_value=self._get_trigger_value(macro.trigger),
                    event_type=macro.trigger.event,
                    conditions=macro.conditions,
                    layer=macro.layer
                )
                self._engine.add_binding(binding)
                
    def _trigger_type_to_string(self, trigger_type) -> str:
        """Convert trigger type enum to string."""
        from ..macros.base_macro import TriggerType
        
        if trigger_type == TriggerType.MOUSE_BUTTON:
            return "mouse"
        elif trigger_type == TriggerType.KEYBOARD_KEY:
            return "keyboard"
        elif trigger_type == TriggerType.GESTURE:
            return "gesture"
        return "unknown"
        
    def _get_trigger_value(self, trigger) -> Any:
        """Get the trigger value for binding."""
        from ..macros.base_macro import TriggerType
        from ..core.input_listener import MouseButton
        
        if trigger.type == TriggerType.MOUSE_BUTTON:
            button_map = {
                "left": MouseButton.LEFT,
                "right": MouseButton.RIGHT,
                "middle": MouseButton.MIDDLE,
                "x1": MouseButton.X1,
                "x2": MouseButton.X2,
            }
            return button_map.get(trigger.button, MouseButton.LEFT)
        elif trigger.type == TriggerType.KEYBOARD_KEY:
            return trigger.key
        elif trigger.type == TriggerType.GESTURE:
            return trigger.gesture_name
            
        return None
        
    # ==================== API ====================
    
    @property
    def engine(self) -> Optional['MacroEngine']:
        return self._engine
        
    @property
    def profile_manager(self) -> Optional['ProfileManager']:
        return self._profile_manager
        
    @property
    def layer_system(self) -> Optional['LayerSystem']:
        return self._layer_system
        
    @property
    def is_running(self) -> bool:
        return self._initialized and self._engine and self._engine._running
        
    def create_quick_remap(self, button: str, target_key: str, profile_id: str = "default"):
        """Convenience method to create a simple button remap."""
        from ..macros.remap_macro import RemapMacro
        from ..macros.base_macro import MacroTrigger, TriggerType
        import uuid
        
        macro = RemapMacro(
            id=f"remap_{uuid.uuid4().hex[:6]}",
            name=f"Remap {button} → {target_key}",
            trigger=MacroTrigger(
                type=TriggerType.MOUSE_BUTTON,
                button=button,
                event="down"
            ),
            target_key=target_key,
            hold_while_pressed=True
        )
        
        self._profile_manager.add_macro(macro, profile_id)
        self._profile_manager.save_all()
        self._load_profile_macros(profile_id)
        
        return macro.id
        
    def create_quick_autoclicker(self, button: str = "left", interval_ms: int = 100, 
                                  trigger_key: str = "f6", profile_id: str = "default"):
        """Convenience method to create an auto-clicker toggle."""
        from ..macros.toggle_macro import ToggleMacro
        from ..macros.base_macro import MacroTrigger, MacroAction, TriggerType, ActionType
        import uuid
        
        # Determine action type and key/button
        if button.startswith("key:"):
            # Keyboard action
            key_name = button.split(":", 1)[1]
            action = MacroAction(
                type=ActionType.KEY_TAP,
                key=key_name,
                hold_ms=0  # No hold for fastest possible repeat
            )
            macro_name = f"Auto-press ({key_name.upper()})"
        else:
            # Mouse click action
            action = MacroAction(
                type=ActionType.MOUSE_CLICK,
                button=button
            )
            macro_name = f"Auto-clicker ({button})"
            
        macro = ToggleMacro(
            id=f"autoclicker_{uuid.uuid4().hex[:6]}",
            name=macro_name,
            trigger=MacroTrigger(
                type=TriggerType.KEYBOARD_KEY,
                key=trigger_key,
                event="down"
            ),
            repeat_action=action,
            repeat_interval_ms=interval_ms
        )
        
        self._profile_manager.add_macro(macro, profile_id)
        self._profile_manager.save_all()
        self._load_profile_macros(profile_id)
        
        return macro.id
