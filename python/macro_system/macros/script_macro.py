"""
Script Macro Module

Macros defined as Python scripts with sandboxed execution.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import asyncio

from .base_macro import BaseMacro, MacroTrigger

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass
class ScriptMacro(BaseMacro):
    """
    Macro with custom Python script execution.
    
    Scripts are executed in a restricted environment with access to:
    - Input simulation (mouse, keyboard)
    - Timing functions (delay, wait)
    - State management
    - Condition checks
    
    Scripts do NOT have access to:
    - File system
    - Network
    - System commands
    - Import statements (limited)
    """
    
    # Inline script code
    script: str = ""
    
    # Path to external script file (relative to macro_scripts/)
    script_path: Optional[str] = None
    
    # Script parameters (passed to script as 'params' dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Use sandboxed execution (recommended)
    sandboxed: bool = True
    
    # Maximum execution time (ms)
    timeout_ms: int = 30000
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute the script."""
        # Get script code
        code = self.script
        if self.script_path:
            code = self._load_script_file()
            
        if not code:
            return
            
        if self.sandboxed:
            await self._execute_sandboxed(code, context)
        else:
            await self._execute_unrestricted(code, context)
            
    def _load_script_file(self) -> str:
        """Load script from file."""
        import os
        
        # Look in macro_scripts directory
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_dir = os.path.join(base_dir, "macro_scripts")
        script_path = os.path.join(script_dir, self.script_path)
        
        if os.path.exists(script_path):
            with open(script_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
        
    async def _execute_sandboxed(self, code: str, context: 'ExecutionContext'):
        """Execute script in sandboxed environment."""
        # Create safe API
        api = ScriptAPI(context)
        
        # Restricted globals
        safe_globals = {
            '__builtins__': {
                'True': True,
                'False': False,
                'None': None,
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'range': range,
                'len': len,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'print': api.log,
            },
            # Script API
            'mouse': api.mouse,
            'keyboard': api.keyboard,
            'delay': api.delay,
            'wait': api.wait,
            'get_state': api.get_state,
            'set_state': api.set_state,
            'is_key_pressed': api.is_key_pressed,
            'is_button_pressed': api.is_button_pressed,
            'get_cursor_pos': api.get_cursor_pos,
            'params': self.parameters.copy(),
            'cancel': api.check_cancelled,
        }
        
        try:
            # Compile and execute
            compiled = compile(code, '<macro_script>', 'exec')
            
            # Execute with timeout
            async def run_script():
                exec(compiled, safe_globals)
                
                # Check for async main() function
                if 'main' in safe_globals and asyncio.iscoroutinefunction(safe_globals['main']):
                    await safe_globals['main']()
                elif 'main' in safe_globals and callable(safe_globals['main']):
                    safe_globals['main']()
                    
            await asyncio.wait_for(
                run_script(),
                timeout=self.timeout_ms / 1000
            )
            
        except asyncio.TimeoutError:
            print(f"[ScriptMacro] Script '{self.name}' timed out")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[ScriptMacro] Script '{self.name}' error: {e}")
            
    async def _execute_unrestricted(self, code: str, context: 'ExecutionContext'):
        """Execute script without restrictions (use with caution)."""
        api = ScriptAPI(context)
        
        globals_dict = {
            'mouse': api.mouse,
            'keyboard': api.keyboard,
            'delay': api.delay,
            'wait': api.wait,
            'get_state': api.get_state,
            'set_state': api.set_state,
            'is_key_pressed': api.is_key_pressed,
            'is_button_pressed': api.is_button_pressed,
            'get_cursor_pos': api.get_cursor_pos,
            'params': self.parameters.copy(),
            'context': context,
        }
        
        try:
            compiled = compile(code, '<macro_script>', 'exec')
            exec(compiled, globals_dict)
            
            if 'main' in globals_dict:
                if asyncio.iscoroutinefunction(globals_dict['main']):
                    await globals_dict['main']()
                else:
                    globals_dict['main']()
                    
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[ScriptMacro] Script '{self.name}' error: {e}")
            
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "script": self.script,
            "script_path": self.script_path,
            "parameters": self.parameters,
            "sandboxed": self.sandboxed,
            "timeout_ms": self.timeout_ms,
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScriptMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            script=data.get("script", ""),
            script_path=data.get("script_path"),
            parameters=data.get("parameters", {}),
            sandboxed=data.get("sandboxed", True),
            timeout_ms=data.get("timeout_ms", 30000),
        )


class ScriptAPI:
    """Safe API exposed to macro scripts."""
    
    def __init__(self, context: 'ExecutionContext'):
        self._context = context
        self._sim = context.simulator
        
    def log(self, *args):
        """Print to console."""
        print("[Script]", *args)
        
    def check_cancelled(self):
        """Check if macro was cancelled."""
        self._context.check_cancelled()
        
    @property
    def mouse(self):
        """Mouse control API."""
        return MouseAPI(self._sim)
        
    @property
    def keyboard(self):
        """Keyboard control API."""
        return KeyboardAPI(self._sim)
        
    def delay(self, ms: float):
        """Synchronous delay (use in non-async scripts)."""
        import time
        self._context.check_cancelled()
        time.sleep(ms / 1000)
        
    async def wait(self, ms: float):
        """Async delay."""
        await self._context.delay(ms)
        
    def get_state(self, key: str, default=None):
        """Get state value."""
        return self._context.data.get(key, default)
        
    def set_state(self, key: str, value):
        """Set state value."""
        self._context.data[key] = value
        
    def is_key_pressed(self, key: str) -> bool:
        """Check if key is pressed."""
        return self._sim.is_key_pressed(key)
        
    def is_button_pressed(self, button: str = "left") -> bool:
        """Check if mouse button is pressed."""
        return self._sim.is_mouse_button_pressed(button)
        
    def get_cursor_pos(self):
        """Get cursor position."""
        return self._sim.get_cursor_position()


class MouseAPI:
    """Mouse control for scripts."""
    
    def __init__(self, sim):
        self._sim = sim
        
    def click(self, button: str = "left", count: int = 1):
        self._sim.mouse_click(button, count)
        
    def down(self, button: str = "left"):
        self._sim.mouse_down(button)
        
    def up(self, button: str = "left"):
        self._sim.mouse_up(button)
        
    def move(self, x: int, y: int):
        self._sim.mouse_move(x, y)
        
    def move_relative(self, dx: int, dy: int):
        self._sim.mouse_move_relative(dx, dy)
        
    def scroll(self, delta: int):
        self._sim.mouse_scroll(delta)
        
    @property
    def position(self):
        return self._sim.get_cursor_position()


class KeyboardAPI:
    """Keyboard control for scripts."""
    
    def __init__(self, sim):
        self._sim = sim
        
    def tap(self, key: str, hold_ms: int = 0):
        self._sim.key_tap(key, hold_ms)
        
    def down(self, key: str):
        self._sim.key_down(key)
        
    def up(self, key: str):
        self._sim.key_up(key)
        
    def combo(self, *keys, hold_ms: int = 0):
        self._sim.key_combo(*keys, hold_ms=hold_ms)
        
    def type(self, text: str, interval_ms: int = 0):
        self._sim.type_text(text, interval_ms)
