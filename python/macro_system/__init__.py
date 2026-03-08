"""
HELXAID - Mouse Macro & Input Remapping System

A production-grade input automation framework for gaming.
"""

from .core import InputListener, MacroEngine, InputSimulator
from .profiles import ProfileManager, LayerSystem
from .macros import (
    BaseMacro, RemapMacro, SequenceMacro, ToggleMacro,
    ConditionalMacro, GestureMacro, ScriptMacro
)
from .detection import AppDetector, GestureDetector
from .integration import LauncherBridge

__version__ = "1.0.0"
__all__ = [
    "InputListener",
    "MacroEngine", 
    "InputSimulator",
    "ProfileManager",
    "LayerSystem",
    "BaseMacro",
    "RemapMacro",
    "SequenceMacro",
    "ToggleMacro",
    "ConditionalMacro",
    "GestureMacro",
    "ScriptMacro",
    "AppDetector",
    "GestureDetector",
    "LauncherBridge",
]
