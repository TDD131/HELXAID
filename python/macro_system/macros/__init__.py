"""Macro type classes."""

from .base_macro import BaseMacro, MacroTrigger, MacroAction, MacroCondition, ActionType, TriggerType, ConditionType
from .remap_macro import RemapMacro
from .sequence_macro import SequenceMacro
from .toggle_macro import ToggleMacro
from .conditional_macro import ConditionalMacro
from .gesture_macro import GestureMacro
from .script_macro import ScriptMacro

__all__ = [
    "BaseMacro",
    "MacroTrigger",
    "MacroAction",
    "MacroCondition",
    "ActionType",
    "TriggerType",
    "ConditionType",
    "RemapMacro",
    "SequenceMacro",
    "ToggleMacro",
    "ConditionalMacro",
    "GestureMacro",
    "ScriptMacro",
]
