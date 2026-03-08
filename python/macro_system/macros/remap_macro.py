"""
Remap Macro Module

Button/key remapping to other buttons, keys, or key combinations.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from .base_macro import BaseMacro, MacroAction, ActionType, MacroTrigger, TriggerType

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass
class RemapMacro(BaseMacro):
    """
    Remaps one input to another.
    
    Supports:
    - Mouse button → Key
    - Mouse button → Key combo
    - Mouse button → Mouse button
    - Key → Key
    - Key → Mouse button
    """
    
    # What to remap to
    target_key: Optional[str] = None
    target_keys: Optional[List[str]] = None  # For combos
    target_button: Optional[str] = None
    
    # Hold behavior: if True, holds target while source is held
    hold_while_pressed: bool = True
    
    # Tap behavior: if True, taps target once per source press
    tap_on_press: bool = False
    tap_hold_ms: int = 0
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute the remap action."""
        sim = context.simulator
        trigger_event = context.trigger_event
        
        # Determine if this is a press or release
        is_down = False
        if trigger_event:
            if trigger_event.mouse:
                from ..core.input_listener import EventType
                is_down = trigger_event.mouse.type == EventType.MOUSE_DOWN
            elif trigger_event.keyboard:
                from ..core.input_listener import EventType
                is_down = trigger_event.keyboard.type == EventType.KEY_DOWN
                
        if self.tap_on_press:
            # Only act on press, ignore release
            if is_down:
                if self.target_keys:
                    sim.key_combo(*self.target_keys, hold_ms=self.tap_hold_ms)
                elif self.target_key:
                    sim.key_tap(self.target_key, hold_ms=self.tap_hold_ms)
                elif self.target_button:
                    sim.mouse_click(self.target_button)
                    
        elif self.hold_while_pressed:
            # Mirror press/release
            if is_down:
                if self.target_keys:
                    # Press all keys in combo order
                    for key in self.target_keys:
                        sim.key_down(key)
                elif self.target_key:
                    sim.key_down(self.target_key)
                elif self.target_button:
                    sim.mouse_down(self.target_button)
            else:
                # Release
                if self.target_keys:
                    # Release in reverse order
                    for key in reversed(self.target_keys):
                        sim.key_up(key)
                elif self.target_key:
                    sim.key_up(self.target_key)
                elif self.target_button:
                    sim.mouse_up(self.target_button)
                    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "target_key": self.target_key,
            "target_keys": self.target_keys,
            "target_button": self.target_button,
            "hold_while_pressed": self.hold_while_pressed,
            "tap_on_press": self.tap_on_press,
            "tap_hold_ms": self.tap_hold_ms,
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RemapMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            target_key=data.get("target_key"),
            target_keys=data.get("target_keys"),
            target_button=data.get("target_button"),
            hold_while_pressed=data.get("hold_while_pressed", True),
            tap_on_press=data.get("tap_on_press", False),
            tap_hold_ms=data.get("tap_hold_ms", 0),
        )
