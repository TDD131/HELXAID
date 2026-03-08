"""
Layer System Module

Manages input layers for context-based macro switching.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class Layer:
    """Input layer definition."""
    
    id: str
    name: str
    description: str = ""
    
    # Modifier-based activation (temporary layer while key held)
    is_modifier_layer: bool = False
    modifier_key: Optional[str] = None  # Key that activates this layer
    
    # Button/key mappings specific to this layer
    mappings: Dict[str, str] = field(default_factory=dict)  # trigger -> macro_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_modifier_layer": self.is_modifier_layer,
            "modifier_key": self.modifier_key,
            "mappings": self.mappings,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Layer':
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            is_modifier_layer=data.get("is_modifier_layer", False),
            modifier_key=data.get("modifier_key"),
            mappings=data.get("mappings", {}),
        )


class LayerSystem:
    """
    Manages input layers for context-based behavior.
    
    Features:
    - Base layer (always active)
    - Modifier layers (active while key held)
    - Layer stack for nested activation
    - Per-layer macro mappings
    """
    
    def __init__(self):
        self._layers: Dict[str, Layer] = {}
        self._active_layer: str = "default"
        self._layer_stack: List[str] = []  # For nested layers
        self._modifier_states: Dict[str, bool] = {}
        
        # Callbacks
        self._on_layer_change: Optional[callable] = None
        
        # Create default layer
        self._create_default_layer()
        
    def _create_default_layer(self):
        """Create the default base layer."""
        default = Layer(
            id="default",
            name="Default",
            description="Base layer - always active when no other layer is"
        )
        self._layers["default"] = default
        
    # ==================== LAYER MANAGEMENT ====================
    
    def add_layer(self, layer: Layer):
        """Add a layer."""
        self._layers[layer.id] = layer
        
    def remove_layer(self, layer_id: str) -> bool:
        """Remove a layer."""
        if layer_id == "default":
            return False
        if layer_id in self._layers:
            del self._layers[layer_id]
            return True
        return False
        
    def get_layer(self, layer_id: str) -> Optional[Layer]:
        """Get a layer by ID."""
        return self._layers.get(layer_id)
        
    def get_all_layers(self) -> List[Layer]:
        """Get all layers."""
        return list(self._layers.values())
        
    # ==================== LAYER SWITCHING ====================
    
    @property
    def active_layer(self) -> str:
        """Get the currently active layer ID."""
        return self._active_layer
        
    @property
    def active_layer_obj(self) -> Optional[Layer]:
        """Get the currently active layer object."""
        return self._layers.get(self._active_layer)
        
    def switch_layer(self, layer_id: str) -> bool:
        """Switch to a layer (permanent switch)."""
        if layer_id not in self._layers:
            return False
            
        old_layer = self._active_layer
        self._active_layer = layer_id
        self._layer_stack.clear()  # Clear any pushed layers
        
        if self._on_layer_change and old_layer != layer_id:
            self._on_layer_change(old_layer, layer_id)
            
        return True
        
    def push_layer(self, layer_id: str) -> bool:
        """Push a layer onto the stack (temporary, for modifier keys)."""
        if layer_id not in self._layers:
            return False
            
        self._layer_stack.append(self._active_layer)
        old_layer = self._active_layer
        self._active_layer = layer_id
        
        if self._on_layer_change and old_layer != layer_id:
            self._on_layer_change(old_layer, layer_id)
            
        return True
        
    def pop_layer(self) -> Optional[str]:
        """Pop a layer from the stack (return to previous layer)."""
        if not self._layer_stack:
            return None
            
        old_layer = self._active_layer
        self._active_layer = self._layer_stack.pop()
        
        if self._on_layer_change and old_layer != self._active_layer:
            self._on_layer_change(old_layer, self._active_layer)
            
        return self._active_layer
        
    def reset_to_default(self):
        """Reset to default layer."""
        self._layer_stack.clear()
        if self._active_layer != "default":
            old = self._active_layer
            self._active_layer = "default"
            if self._on_layer_change:
                self._on_layer_change(old, "default")
                
    # ==================== MODIFIER HANDLING ====================
    
    def handle_modifier_press(self, key: str):
        """Handle a modifier key being pressed."""
        self._modifier_states[key] = True
        
        # Check if any layer uses this modifier
        for layer in self._layers.values():
            if layer.is_modifier_layer and layer.modifier_key == key:
                self.push_layer(layer.id)
                break
                
    def handle_modifier_release(self, key: str):
        """Handle a modifier key being released."""
        self._modifier_states[key] = False
        
        # Check if current layer uses this modifier
        current = self._layers.get(self._active_layer)
        if current and current.is_modifier_layer and current.modifier_key == key:
            self.pop_layer()
            
    # ==================== MAPPING QUERIES ====================
    
    def get_mapping(self, trigger: str) -> Optional[str]:
        """Get macro ID for a trigger in the current layer."""
        layer = self._layers.get(self._active_layer)
        if layer:
            mapping = layer.mappings.get(trigger)
            if mapping:
                return mapping
                
        # Fall back to default layer
        if self._active_layer != "default":
            default = self._layers.get("default")
            if default:
                return default.mappings.get(trigger)
                
        return None
        
    def set_mapping(self, layer_id: str, trigger: str, macro_id: str):
        """Set a mapping in a layer."""
        layer = self._layers.get(layer_id)
        if layer:
            layer.mappings[trigger] = macro_id
            
    def remove_mapping(self, layer_id: str, trigger: str):
        """Remove a mapping from a layer."""
        layer = self._layers.get(layer_id)
        if layer and trigger in layer.mappings:
            del layer.mappings[trigger]
            
    # ==================== SERIALIZATION ====================
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "layers": {lid: l.to_dict() for lid, l in self._layers.items()},
            "active_layer": self._active_layer,
        }
        
    def from_dict(self, data: Dict[str, Any]):
        self._layers.clear()
        for lid, ldata in data.get("layers", {}).items():
            self._layers[lid] = Layer.from_dict(ldata)
        self._active_layer = data.get("active_layer", "default")
        
        if "default" not in self._layers:
            self._create_default_layer()
            
    # ==================== CALLBACKS ====================
    
    def on_layer_change(self, callback: callable):
        """Set callback for layer changes."""
        self._on_layer_change = callback
