"""
Conditional Macro Module

Macros with if/else logic based on runtime conditions.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from .base_macro import BaseMacro, MacroAction, MacroCondition, MacroTrigger

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass
class ConditionalMacro(BaseMacro):
    """
    Macro with conditional execution paths.
    
    Evaluates conditions at runtime and executes different
    action sequences based on the result.
    """
    
    # Main condition to evaluate
    condition: Optional[MacroCondition] = None
    
    # Actions if condition is True
    if_true_actions: List[MacroAction] = field(default_factory=list)
    
    # Actions if condition is False
    if_false_actions: List[MacroAction] = field(default_factory=list)
    
    # Additional elif branches
    elif_branches: List[tuple] = field(default_factory=list)  # List of (condition, actions)
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute with conditional logic."""
        # Evaluate main condition
        if self.condition and self.condition.evaluate(context.engine, context.modifiers):
            for action in self.if_true_actions:
                context.check_cancelled()
                await action.execute(context)
            return
            
        # Check elif branches
        for elif_condition, elif_actions in self.elif_branches:
            if elif_condition.evaluate(context.engine, context.modifiers):
                for action in elif_actions:
                    context.check_cancelled()
                    await action.execute(context)
                return
                
        # Fall through to else
        for action in self.if_false_actions:
            context.check_cancelled()
            await action.execute(context)
            
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "condition": self.condition.to_dict() if self.condition else None,
            "if_true_actions": [a.to_dict() for a in self.if_true_actions],
            "if_false_actions": [a.to_dict() for a in self.if_false_actions],
            "elif_branches": [
                {"condition": c.to_dict(), "actions": [a.to_dict() for a in actions]}
                for c, actions in self.elif_branches
            ],
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConditionalMacro':
        elif_branches = []
        for branch in data.get("elif_branches", []):
            cond = MacroCondition.from_dict(branch["condition"])
            actions = [MacroAction.from_dict(a) for a in branch["actions"]]
            elif_branches.append((cond, actions))
            
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            condition=MacroCondition.from_dict(data["condition"]) if data.get("condition") else None,
            if_true_actions=[MacroAction.from_dict(a) for a in data.get("if_true_actions", [])],
            if_false_actions=[MacroAction.from_dict(a) for a in data.get("if_false_actions", [])],
            elif_branches=elif_branches,
        )
