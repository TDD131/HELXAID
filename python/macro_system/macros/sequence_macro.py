"""
Sequence Macro Module

Executes a sequence of actions with configurable delays and repeats.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, TYPE_CHECKING

from .base_macro import BaseMacro, MacroAction, MacroTrigger

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass
class SequenceMacro(BaseMacro):
    """
    Executes a predefined sequence of actions.
    
    Features:
    - Multiple actions in order
    - Configurable delays between actions
    - Optional repeat count
    - Cancel on trigger release
    """
    
    # Actions to execute
    actions: List[MacroAction] = field(default_factory=list)
    
    # Repeat the entire sequence
    repeat_count: int = 1
    repeat_interval_ms: int = 0
    
    # Cancel if trigger is released
    cancel_on_release: bool = False
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute the action sequence."""
        for rep in range(self.repeat_count):
            context.check_cancelled()
            
            for action in self.actions:
                context.check_cancelled()
                await action.execute(context)
                
            # Interval between repeats
            if rep < self.repeat_count - 1 and self.repeat_interval_ms > 0:
                await context.delay(self.repeat_interval_ms)
                
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "actions": [a.to_dict() for a in self.actions],
            "repeat_count": self.repeat_count,
            "repeat_interval_ms": self.repeat_interval_ms,
            "cancel_on_release": self.cancel_on_release,
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SequenceMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            actions=[MacroAction.from_dict(a) for a in data.get("actions", [])],
            repeat_count=data.get("repeat_count", 1),
            repeat_interval_ms=data.get("repeat_interval_ms", 0),
            cancel_on_release=data.get("cancel_on_release", False),
        )
