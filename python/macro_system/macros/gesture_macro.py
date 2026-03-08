"""
Gesture Macro Module

Macros triggered by mouse gesture patterns.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import math

from .base_macro import BaseMacro, MacroAction, MacroTrigger, TriggerType

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass
class GestureVector:
    """Single direction vector in a gesture."""
    direction: str  # "up", "down", "left", "right", "upleft", "upright", "downleft", "downright"
    min_distance: int = 30  # Minimum pixels to recognize this segment
    
    def to_dict(self) -> Dict[str, Any]:
        return {"direction": self.direction, "min_distance": self.min_distance}
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GestureVector':
        return cls(direction=data["direction"], min_distance=data.get("min_distance", 30))


@dataclass
class GesturePattern:
    """Complete gesture pattern definition."""
    name: str
    vectors: List[GestureVector] = field(default_factory=list)
    tolerance: float = 0.4  # Direction tolerance (0-1, higher = more lenient)
    min_total_distance: int = 50  # Minimum total pixel movement
    timeout_ms: int = 500  # Maximum time to complete gesture
    
    # Which button must be held during gesture
    hold_button: str = "right"  # Default: right-click + drag
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "vectors": [v.to_dict() for v in self.vectors],
            "tolerance": self.tolerance,
            "min_total_distance": self.min_total_distance,
            "timeout_ms": self.timeout_ms,
            "hold_button": self.hold_button,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GesturePattern':
        return cls(
            name=data["name"],
            vectors=[GestureVector.from_dict(v) for v in data.get("vectors", [])],
            tolerance=data.get("tolerance", 0.4),
            min_total_distance=data.get("min_total_distance", 50),
            timeout_ms=data.get("timeout_ms", 500),
            hold_button=data.get("hold_button", "right"),
        )


# Common preset gestures
PRESET_GESTURES = {
    "swipe_up": GesturePattern("swipe_up", [GestureVector("up")]),
    "swipe_down": GesturePattern("swipe_down", [GestureVector("down")]),
    "swipe_left": GesturePattern("swipe_left", [GestureVector("left")]),
    "swipe_right": GesturePattern("swipe_right", [GestureVector("right")]),
    "L_shape": GesturePattern("L_shape", [GestureVector("down"), GestureVector("right")]),
    "reverse_L": GesturePattern("reverse_L", [GestureVector("down"), GestureVector("left")]),
    "V_shape": GesturePattern("V_shape", [GestureVector("downright"), GestureVector("upright")]),
    "zigzag": GesturePattern("zigzag", [GestureVector("right"), GestureVector("left"), GestureVector("right")]),
    "circle_cw": GesturePattern("circle_cw", [GestureVector("right"), GestureVector("down"), GestureVector("left"), GestureVector("up")]),
}


@dataclass
class GestureMacro(BaseMacro):
    """
    Macro triggered by mouse gestures.
    
    Recognizes movement patterns while a button is held
    and triggers actions when the pattern matches.
    """
    
    # Gesture pattern to match
    pattern: Optional[GesturePattern] = None
    
    # Preset gesture name (alternative to pattern)
    preset_name: Optional[str] = None
    
    # Actions to execute when gesture is recognized
    actions: List[MacroAction] = field(default_factory=list)
    
    # Visual feedback
    show_trail: bool = False
    trail_color: str = "#00AAFF"
    
    def __post_init__(self):
        # Load preset if specified
        if self.preset_name and not self.pattern:
            self.pattern = PRESET_GESTURES.get(self.preset_name)
            
        # Create trigger from pattern
        if self.pattern and not self.trigger:
            self.trigger = MacroTrigger(
                type=TriggerType.GESTURE,
                gesture_name=self.pattern.name
            )
            
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute actions after gesture is recognized."""
        for action in self.actions:
            context.check_cancelled()
            await action.execute(context)
            
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "pattern": self.pattern.to_dict() if self.pattern else None,
            "preset_name": self.preset_name,
            "actions": [a.to_dict() for a in self.actions],
            "show_trail": self.show_trail,
            "trail_color": self.trail_color,
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GestureMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            pattern=GesturePattern.from_dict(data["pattern"]) if data.get("pattern") else None,
            preset_name=data.get("preset_name"),
            actions=[MacroAction.from_dict(a) for a in data.get("actions", [])],
            show_trail=data.get("show_trail", False),
            trail_color=data.get("trail_color", "#00AAFF"),
        )
