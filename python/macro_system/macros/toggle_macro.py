"""
Toggle Macro Module

Macros that toggle ON/OFF and persist state while active.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import asyncio

from .base_macro import BaseMacro, MacroAction, MacroTrigger

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass  
class ToggleMacro(BaseMacro):
    """
    Toggle macro that can be switched ON/OFF.
    
    While ON, can:
    - Repeat an action at an interval (e.g., auto-clicker)
    - Hold a key/button down
    - Run a continuous script
    """
    
    is_toggle: bool = True  # Override - always a toggle
    
    # Action to perform while ON
    on_action: Optional[MacroAction] = None
    
    # For repeating actions
    repeat_action: Optional[MacroAction] = None
    repeat_interval_ms: int = 100
    
    # For held keys/buttons
    hold_key: Optional[str] = None
    hold_button: Optional[str] = None
    
    # Actions to run when toggled ON
    on_activate_actions: List[MacroAction] = field(default_factory=list)
    
    # Actions to run when toggled OFF
    on_deactivate_actions: List[MacroAction] = field(default_factory=list)
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute toggle behavior."""
        sim = context.simulator
        
        # Run activation actions
        for action in self.on_activate_actions:
            await action.execute(context)
            
        # Hold key/button if specified
        if self.hold_key:
            sim.key_down(self.hold_key)
        if self.hold_button:
            sim.mouse_down(self.hold_button)
            
        # One-time action
        if self.on_action:
            await self.on_action.execute(context)
            
        # Repeat action while toggled ON
        if self.repeat_action:
            import time
            try:
                while True:
                    context.check_cancelled()
                    start = time.perf_counter()
                    await self.repeat_action.execute(context)
                    
                    # High-precision timing for low intervals
                    if self.repeat_interval_ms <= 15:
                        # Busy-wait for sub-15ms precision (Windows timer resolution limit)
                        target = start + (self.repeat_interval_ms / 1000)
                        while time.perf_counter() < target:
                            # Check cancellation during spin wait to allow quick stop
                            context.check_cancelled()
                    else:
                        # Normal async sleep for larger intervals
                        elapsed = (time.perf_counter() - start) * 1000
                        remaining = max(0, self.repeat_interval_ms - elapsed)
                        if remaining > 0:
                            await context.delay(remaining)
            except asyncio.CancelledError:
                pass
        else:
            # No repeat action - just wait until cancelled
            try:
                while True:
                    context.check_cancelled()
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
                
    def cancel(self) -> None:
        """Called when toggle is turned OFF."""
        # Release held keys/buttons (done in the finally block ideally)
        pass
        
    async def cleanup(self, context: 'ExecutionContext'):
        """Cleanup when toggled OFF."""
        sim = context.simulator
        
        # Release held inputs
        if self.hold_key:
            sim.key_up(self.hold_key)
        if self.hold_button:
            sim.mouse_up(self.hold_button)
            
        # Run deactivation actions
        for action in self.on_deactivate_actions:
            try:
                await action.execute(context)
            except:
                pass
                
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "on_action": self.on_action.to_dict() if self.on_action else None,
            "repeat_action": self.repeat_action.to_dict() if self.repeat_action else None,
            "repeat_interval_ms": self.repeat_interval_ms,
            "hold_key": self.hold_key,
            "hold_button": self.hold_button,
            "on_activate_actions": [a.to_dict() for a in self.on_activate_actions],
            "on_deactivate_actions": [a.to_dict() for a in self.on_deactivate_actions],
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToggleMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            on_action=MacroAction.from_dict(data["on_action"]) if data.get("on_action") else None,
            repeat_action=MacroAction.from_dict(data["repeat_action"]) if data.get("repeat_action") else None,
            repeat_interval_ms=data.get("repeat_interval_ms", 100),
            hold_key=data.get("hold_key"),
            hold_button=data.get("hold_button"),
            on_activate_actions=[MacroAction.from_dict(a) for a in data.get("on_activate_actions", [])],
            on_deactivate_actions=[MacroAction.from_dict(a) for a in data.get("on_deactivate_actions", [])],
        )
