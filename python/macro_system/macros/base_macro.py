"""
Base Macro Module

Abstract base class and common data structures for all macro types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any, Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


class TriggerType(Enum):
    """Types of macro triggers."""
    MOUSE_BUTTON = "mouse_button"
    KEYBOARD_KEY = "keyboard_key"
    HOTKEY = "hotkey"
    GESTURE = "gesture"
    APP_FOCUS = "app_focus"
    TIMER = "timer"
    MANUAL = "manual"


class ActionType(Enum):
    """Types of macro actions."""
    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    KEY_TAP = "key_tap"
    KEY_COMBO = "key_combo"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    MOUSE_MOVE = "mouse_move"
    MOUSE_MOVE_RELATIVE = "mouse_move_relative"
    MOUSE_SCROLL = "mouse_scroll"
    DELAY = "delay"
    SCRIPT = "script"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    SET_STATE = "set_state"
    CANCEL = "cancel"


class ConditionType(Enum):
    """Types of conditions for conditional execution."""
    MODIFIER_HELD = "modifier_held"
    KEY_PRESSED = "key_pressed"
    MOUSE_BUTTON_PRESSED = "mouse_button_pressed"
    APP_ACTIVE = "app_active"
    WINDOW_TITLE = "window_title"
    MACRO_STATE = "macro_state"
    TOGGLE_ON = "toggle_on"
    LAYER_ACTIVE = "layer_active"
    CUSTOM = "custom"
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class MacroCondition:
    """Condition for conditional macro execution."""
    type: ConditionType
    
    # For modifier/key checks
    key: Optional[str] = None
    modifiers: Optional[List[str]] = None
    
    # For app/window checks
    process_name: Optional[str] = None
    window_title: Optional[str] = None
    window_title_contains: Optional[str] = None
    
    # For state checks
    macro_id: Optional[str] = None
    state_key: Optional[str] = None
    state_value: Optional[Any] = None
    
    # For layer checks
    layer_id: Optional[str] = None
    
    # For compound conditions (AND/OR)
    conditions: Optional[List['MacroCondition']] = None
    
    # Negate the result
    negate: bool = False
    
    def evaluate(self, engine: Any, modifiers: Dict[str, bool]) -> bool:
        """Evaluate this condition. Returns True if condition is met."""
        result = self._evaluate_inner(engine, modifiers)
        return not result if self.negate else result
        
    def _evaluate_inner(self, engine: Any, modifiers: Dict[str, bool]) -> bool:
        """Internal evaluation without negation."""
        if self.type == ConditionType.MODIFIER_HELD:
            if self.modifiers:
                return all(modifiers.get(m, False) for m in self.modifiers)
            if self.key:
                return modifiers.get(self.key, False)
            return False
            
        elif self.type == ConditionType.KEY_PRESSED:
            if self.key and hasattr(engine, 'input_simulator'):
                return engine.input_simulator.is_key_pressed(self.key)
            return False
            
        elif self.type == ConditionType.MOUSE_BUTTON_PRESSED:
            if self.key and hasattr(engine, 'input_simulator'):
                return engine.input_simulator.is_mouse_button_pressed(self.key)
            return False
            
        elif self.type == ConditionType.TOGGLE_ON:
            if self.macro_id and hasattr(engine, 'is_toggle_on'):
                return engine.is_toggle_on(self.macro_id)
            return False
            
        elif self.type == ConditionType.LAYER_ACTIVE:
            if self.layer_id and hasattr(engine, '_active_layer'):
                return engine._active_layer == self.layer_id
            return False
            
        elif self.type == ConditionType.AND:
            if self.conditions:
                return all(c.evaluate(engine, modifiers) for c in self.conditions)
            return True
            
        elif self.type == ConditionType.OR:
            if self.conditions:
                return any(c.evaluate(engine, modifiers) for c in self.conditions)
            return False
            
        elif self.type == ConditionType.NOT:
            if self.conditions and len(self.conditions) > 0:
                return not self.conditions[0].evaluate(engine, modifiers)
            return True
            
        # Default to True for unimplemented conditions
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = {"type": self.type.value, "negate": self.negate}
        
        if self.key:
            data["key"] = self.key
        if self.modifiers:
            data["modifiers"] = self.modifiers
        if self.process_name:
            data["process_name"] = self.process_name
        if self.window_title:
            data["window_title"] = self.window_title
        if self.macro_id:
            data["macro_id"] = self.macro_id
        if self.layer_id:
            data["layer_id"] = self.layer_id
        if self.conditions:
            data["conditions"] = [c.to_dict() for c in self.conditions]
            
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MacroCondition':
        """Deserialize from dictionary."""
        conditions = None
        if "conditions" in data:
            conditions = [cls.from_dict(c) for c in data["conditions"]]
            
        return cls(
            type=ConditionType(data["type"]),
            negate=data.get("negate", False),
            key=data.get("key"),
            modifiers=data.get("modifiers"),
            process_name=data.get("process_name"),
            window_title=data.get("window_title"),
            macro_id=data.get("macro_id"),
            layer_id=data.get("layer_id"),
            conditions=conditions
        )


@dataclass
class MacroAction:
    """Single action within a macro."""
    type: ActionType
    
    # Key actions
    key: Optional[str] = None
    keys: Optional[List[str]] = None  # For combos
    
    # Mouse actions
    button: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    dx: Optional[int] = None
    dy: Optional[int] = None
    scroll_delta: Optional[int] = None
    
    # Timing
    delay_ms: int = 0
    hold_ms: int = 0
    
    # Repeat
    repeat_count: int = 1
    repeat_interval_ms: int = 0
    
    # For loops
    loop_count: Optional[int] = None  # None = infinite
    loop_actions: Optional[List['MacroAction']] = None
    
    # For conditionals
    condition: Optional[MacroCondition] = None
    if_true: Optional[List['MacroAction']] = None
    if_false: Optional[List['MacroAction']] = None
    
    # For scripts
    script: Optional[str] = None
    script_path: Optional[str] = None
    
    # For state management
    state_key: Optional[str] = None
    state_value: Optional[Any] = None
    
    async def execute(self, context: 'ExecutionContext'):
        """Execute this action."""
        sim = context.simulator
        
        # Pre-delay
        if self.delay_ms > 0:
            await context.delay(self.delay_ms)
            
        for _ in range(self.repeat_count):
            context.check_cancelled()
            
            if self.type == ActionType.KEY_TAP:
                sim.key_tap(self.key, self.hold_ms)
                
            elif self.type == ActionType.KEY_PRESS:
                sim.key_down(self.key)
                
            elif self.type == ActionType.KEY_RELEASE:
                sim.key_up(self.key)
                
            elif self.type == ActionType.KEY_COMBO:
                sim.key_combo(*self.keys, hold_ms=self.hold_ms)
                
            elif self.type == ActionType.MOUSE_CLICK:
                sim.mouse_click(self.button or "left")
                
            elif self.type == ActionType.MOUSE_DOWN:
                sim.mouse_down(self.button or "left")
                
            elif self.type == ActionType.MOUSE_UP:
                sim.mouse_up(self.button or "left")
                
            elif self.type == ActionType.MOUSE_MOVE:
                sim.mouse_move(self.x, self.y)
                
            elif self.type == ActionType.MOUSE_MOVE_RELATIVE:
                sim.mouse_move_relative(self.dx or 0, self.dy or 0)
                
            elif self.type == ActionType.MOUSE_SCROLL:
                sim.mouse_scroll(self.scroll_delta or 0)
                
            elif self.type == ActionType.DELAY:
                await context.delay(self.delay_ms)
                
            elif self.type == ActionType.CONDITIONAL:
                if self.condition and self.condition.evaluate(
                    context.engine, context.modifiers
                ):
                    if self.if_true:
                        for action in self.if_true:
                            await action.execute(context)
                else:
                    if self.if_false:
                        for action in self.if_false:
                            await action.execute(context)
                            
            elif self.type == ActionType.LOOP:
                count = 0
                while True:
                    context.check_cancelled()
                    
                    if self.loop_count and count >= self.loop_count:
                        break
                        
                    if self.loop_actions:
                        for action in self.loop_actions:
                            await action.execute(context)
                            
                    count += 1
                    
            elif self.type == ActionType.SET_STATE:
                if self.state_key:
                    context.data[self.state_key] = self.state_value
                    
            # Repeat interval
            if self.repeat_count > 1 and self.repeat_interval_ms > 0:
                await context.delay(self.repeat_interval_ms)
                
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = {"type": self.type.value}
        
        if self.key:
            data["key"] = self.key
        if self.keys:
            data["keys"] = self.keys
        if self.button:
            data["button"] = self.button
        if self.x is not None:
            data["x"] = self.x
        if self.y is not None:
            data["y"] = self.y
        if self.dx is not None:
            data["dx"] = self.dx
        if self.dy is not None:
            data["dy"] = self.dy
        if self.scroll_delta is not None:
            data["scroll_delta"] = self.scroll_delta
        if self.delay_ms:
            data["delay_ms"] = self.delay_ms
        if self.hold_ms:
            data["hold_ms"] = self.hold_ms
        if self.repeat_count != 1:
            data["repeat_count"] = self.repeat_count
        if self.repeat_interval_ms:
            data["repeat_interval_ms"] = self.repeat_interval_ms
        if self.loop_count is not None:
            data["loop_count"] = self.loop_count
        if self.loop_actions:
            data["loop_actions"] = [a.to_dict() for a in self.loop_actions]
        if self.condition:
            data["condition"] = self.condition.to_dict()
        if self.if_true:
            data["if_true"] = [a.to_dict() for a in self.if_true]
        if self.if_false:
            data["if_false"] = [a.to_dict() for a in self.if_false]
        if self.script:
            data["script"] = self.script
        if self.script_path:
            data["script_path"] = self.script_path
        if self.state_key:
            data["state_key"] = self.state_key
        if self.state_value is not None:
            data["state_value"] = self.state_value
            
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MacroAction':
        """Deserialize from dictionary."""
        return cls(
            type=ActionType(data["type"]),
            key=data.get("key"),
            keys=data.get("keys"),
            button=data.get("button"),
            x=data.get("x"),
            y=data.get("y"),
            dx=data.get("dx"),
            dy=data.get("dy"),
            scroll_delta=data.get("scroll_delta"),
            delay_ms=data.get("delay_ms", 0),
            hold_ms=data.get("hold_ms", 0),
            repeat_count=data.get("repeat_count", 1),
            repeat_interval_ms=data.get("repeat_interval_ms", 0),
            loop_count=data.get("loop_count"),
            loop_actions=[cls.from_dict(a) for a in data.get("loop_actions", [])],
            condition=MacroCondition.from_dict(data["condition"]) if "condition" in data else None,
            if_true=[cls.from_dict(a) for a in data.get("if_true", [])],
            if_false=[cls.from_dict(a) for a in data.get("if_false", [])],
            script=data.get("script"),
            script_path=data.get("script_path"),
            state_key=data.get("state_key"),
            state_value=data.get("state_value"),
        )


@dataclass
class MacroTrigger:
    """Trigger definition for a macro."""
    type: TriggerType
    
    # For mouse/keyboard triggers
    button: Optional[str] = None
    key: Optional[str] = None
    event: str = "down"  # "down", "up", "click"
    
    # For hotkey triggers
    hotkey: Optional[str] = None  # e.g., "ctrl+shift+m"
    
    # For gesture triggers
    gesture_name: Optional[str] = None
    
    # For app triggers
    process_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = {"type": self.type.value, "event": self.event}
        if self.button:
            data["button"] = self.button
        if self.key:
            data["key"] = self.key
        if self.hotkey:
            data["hotkey"] = self.hotkey
        if self.gesture_name:
            data["gesture_name"] = self.gesture_name
        if self.process_name:
            data["process_name"] = self.process_name
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MacroTrigger':
        return cls(
            type=TriggerType(data["type"]),
            button=data.get("button"),
            key=data.get("key"),
            event=data.get("event", "down"),
            hotkey=data.get("hotkey"),
            gesture_name=data.get("gesture_name"),
            process_name=data.get("process_name"),
        )


@dataclass
class BaseMacro(ABC):
    """Abstract base class for all macro types."""
    id: str
    name: str
    enabled: bool = True
    description: str = ""
    
    # Trigger that activates this macro
    trigger: Optional[MacroTrigger] = None
    
    # Conditions that must be met
    conditions: List[MacroCondition] = field(default_factory=list)
    
    # Layer this macro belongs to
    layer: str = "default"
    
    # Execution options
    allow_overlap: bool = False  # Allow multiple instances
    is_toggle: bool = False  # Toggle on/off behavior
    
    @abstractmethod
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute the macro."""
        pass
        
    def cancel(self) -> None:
        """Cancel execution (override if cleanup needed)."""
        pass
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.__class__.__name__,
            "enabled": self.enabled,
            "description": self.description,
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "conditions": [c.to_dict() for c in self.conditions],
            "layer": self.layer,
            "allow_overlap": self.allow_overlap,
            "is_toggle": self.is_toggle,
        }
