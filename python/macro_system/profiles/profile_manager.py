"""
Profile Manager Module

Manages macro profiles with persistence and app binding.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ..macros.base_macro import BaseMacro


@dataclass
class MacroProfile:
    """A collection of macros with configuration."""
    
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    
    # Applications this profile is bound to (auto-activate)
    bound_apps: List[str] = field(default_factory=list)  # Process names
    
    # Hotkey to manually activate this profile
    activation_hotkey: Optional[str] = None
    
    # Layer configuration
    default_layer: str = "default"
    layer_switch_hotkeys: Dict[str, str] = field(default_factory=dict)
    
    # Macro IDs in this profile
    macro_ids: List[str] = field(default_factory=list)
    
    # Profile-level settings
    settings: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "bound_apps": self.bound_apps,
            "activation_hotkey": self.activation_hotkey,
            "default_layer": self.default_layer,
            "layer_switch_hotkeys": self.layer_switch_hotkeys,
            "macro_ids": self.macro_ids,
            "settings": self.settings,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MacroProfile':
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            bound_apps=data.get("bound_apps", []),
            activation_hotkey=data.get("activation_hotkey"),
            default_layer=data.get("default_layer", "default"),
            layer_switch_hotkeys=data.get("layer_switch_hotkeys", {}),
            macro_ids=data.get("macro_ids", []),
            settings=data.get("settings", {}),
        )


class ProfileManager:
    """
    Manages macro profiles with persistence.
    
    Features:
    - Profile CRUD operations
    - App-based auto-switching
    - Hotkey-based switching
    - Profile export/import
    """
    
    def __init__(self, profiles_dir: str):
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        self._profiles: Dict[str, MacroProfile] = {}
        self._active_profile: Optional[MacroProfile] = None
        self._macros: Dict[str, Any] = {}  # All loaded macros
        
        # Callbacks
        self._on_profile_change: Optional[callable] = None
        
    def load_profiles(self):
        """Load all profiles from disk."""
        self._profiles.clear()
        
        # Load profiles
        for file in self.profiles_dir.glob("*.json"):
            if file.name == "macros.json":
                continue
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    profile = MacroProfile.from_dict(data)
                    self._profiles[profile.id] = profile
            except Exception as e:
                print(f"[ProfileManager] Error loading {file}: {e}")
                
        # Load macros
        macros_file = self.profiles_dir / "macros.json"
        if macros_file.exists():
            try:
                with open(macros_file, 'r', encoding='utf-8') as f:
                    macros_data = json.load(f)
                    self._load_macros(macros_data)
            except Exception as e:
                print(f"[ProfileManager] Error loading macros: {e}")
                
        # Create default profile if none exist
        if not self._profiles:
            self._create_default_profile()
            
        print(f"[ProfileManager] Loaded {len(self._profiles)} profiles, {len(self._macros)} macros")
        
    def _load_macros(self, macros_data: List[Dict[str, Any]]):
        """Load macro instances from data."""
        from ..macros import (
            RemapMacro, SequenceMacro, ToggleMacro,
            ConditionalMacro, GestureMacro, ScriptMacro
        )
        
        TYPE_MAP = {
            "RemapMacro": RemapMacro,
            "SequenceMacro": SequenceMacro,
            "ToggleMacro": ToggleMacro,
            "ConditionalMacro": ConditionalMacro,
            "GestureMacro": GestureMacro,
            "ScriptMacro": ScriptMacro,
        }
        
        for macro_data in macros_data:
            macro_type = macro_data.get("type")
            if macro_type in TYPE_MAP:
                try:
                    macro = TYPE_MAP[macro_type].from_dict(macro_data)
                    self._macros[macro.id] = macro
                except Exception as e:
                    print(f"[ProfileManager] Error loading macro {macro_data.get('id')}: {e}")
                    
    def _create_default_profile(self):
        """Create a default profile."""
        default = MacroProfile(
            id="default",
            name="Default Profile",
            description="Default macro profile"
        )
        self._profiles["default"] = default
        self.save_profile(default)
        
    def save_profile(self, profile: MacroProfile):
        """Save a profile to disk."""
        file_path = self.profiles_dir / f"{profile.id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(profile.to_dict(), f, indent=2)
            
    def save_macros(self):
        """Save all macros to disk."""
        macros_file = self.profiles_dir / "macros.json"
        macros_data = [m.to_dict() for m in self._macros.values()]
        with open(macros_file, 'w', encoding='utf-8') as f:
            json.dump(macros_data, f, indent=2)
            
    def save_all(self):
        """Save all profiles and macros."""
        for profile in self._profiles.values():
            self.save_profile(profile)
        self.save_macros()
        
    # ==================== PROFILE OPERATIONS ====================
    
    def get_profile(self, profile_id: str) -> Optional[MacroProfile]:
        """Get a profile by ID."""
        return self._profiles.get(profile_id)
        
    def get_all_profiles(self) -> List[MacroProfile]:
        """Get all profiles."""
        return list(self._profiles.values())
        
    def create_profile(self, name: str, description: str = "") -> MacroProfile:
        """Create a new profile."""
        import uuid
        profile_id = str(uuid.uuid4())[:8]
        
        profile = MacroProfile(
            id=profile_id,
            name=name,
            description=description
        )
        
        self._profiles[profile_id] = profile
        self.save_profile(profile)
        return profile
        
    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile."""
        if profile_id not in self._profiles:
            return False
            
        # Don't delete if it's the active profile
        if self._active_profile and self._active_profile.id == profile_id:
            return False
            
        del self._profiles[profile_id]
        
        # Delete file
        file_path = self.profiles_dir / f"{profile_id}.json"
        if file_path.exists():
            file_path.unlink()
            
        return True
        
    def activate_profile(self, profile_id: str) -> bool:
        """Activate a profile."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return False
            
        old_profile = self._active_profile
        self._active_profile = profile
        
        if self._on_profile_change:
            self._on_profile_change(old_profile, profile)
            
        print(f"[ProfileManager] Activated profile: {profile.name}")
        return True
        
    @property
    def active_profile(self) -> Optional[MacroProfile]:
        """Get the currently active profile."""
        return self._active_profile
        
    def get_profile_for_app(self, process_name: str) -> Optional[MacroProfile]:
        """Find a profile bound to an application."""
        process_lower = process_name.lower()
        
        for profile in self._profiles.values():
            if not profile.enabled:
                continue
                
            for app in profile.bound_apps:
                if app.lower() in process_lower or process_lower in app.lower():
                    return profile
                    
        return None
        
    # ==================== MACRO OPERATIONS ====================
    
    def get_macro(self, macro_id: str) -> Optional[Any]:
        """Get a macro by ID."""
        return self._macros.get(macro_id)
        
    def get_macros_for_profile(self, profile_id: str) -> List[Any]:
        """Get all macros in a profile."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return []
            
        return [self._macros[mid] for mid in profile.macro_ids if mid in self._macros]
        
    def add_macro(self, macro: Any, profile_id: str = "default"):
        """Add a macro to a profile."""
        self._macros[macro.id] = macro
        
        profile = self._profiles.get(profile_id)
        if profile and macro.id not in profile.macro_ids:
            profile.macro_ids.append(macro.id)
            self.save_profile(profile)
            
    def remove_macro(self, macro_id: str):
        """Remove a macro from all profiles."""
        if macro_id in self._macros:
            del self._macros[macro_id]
            
        for profile in self._profiles.values():
            if macro_id in profile.macro_ids:
                profile.macro_ids.remove(macro_id)
                
    # ==================== CALLBACKS ====================
    
    def on_profile_change(self, callback: callable):
        """Set callback for profile changes."""
        self._on_profile_change = callback
