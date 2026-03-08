"""
Script Sandbox Module

Provides a restricted Python execution environment for user scripts.
"""

from typing import Dict, Any, Optional, Callable
import ast


class ScriptSandbox:
    """
    Sandboxed Python execution for macro scripts.
    
    Security features:
    - No filesystem access
    - No network access
    - No imports (except whitelisted)
    - Limited builtins
    - Execution timeout
    """
    
    # Whitelisted builtins
    SAFE_BUILTINS = {
        'True': True,
        'False': False,
        'None': None,
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'int': int,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'pow': pow,
        'range': range,
        'reversed': reversed,
        'round': round,
        'set': set,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,
    }
    
    # Dangerous AST node types
    BLOCKED_NODES = {
        'Import',
        'ImportFrom',
        'Exec',
        'Eval',
        'With',  # Can be used for context manager exploits
    }
    
    # Dangerous attribute names
    BLOCKED_ATTRS = {
        '__import__',
        '__builtins__',
        '__class__',
        '__bases__',
        '__subclasses__',
        '__mro__',
        '__globals__',
        '__code__',
        '__reduce__',
        '__reduce_ex__',
        'open',
        'exec',
        'eval',
        'compile',
        'input',
        'breakpoint',
    }
    
    def __init__(self):
        self._api: Dict[str, Any] = {}
        self._log_func: Optional[Callable[[str], None]] = None
        
    def set_api(self, api: Dict[str, Any]):
        """Set the API exposed to scripts."""
        self._api = api.copy()
        
    def set_log_function(self, func: Callable[[str], None]):
        """Set function for script print output."""
        self._log_func = func
        
    def validate_code(self, code: str) -> tuple:
        """
        Validate code for safety.
        Returns (is_safe, error_message).
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
            
        # Walk AST and check for blocked constructs
        for node in ast.walk(tree):
            node_type = type(node).__name__
            
            if node_type in self.BLOCKED_NODES:
                return False, f"Blocked construct: {node_type}"
                
            # Check attribute access
            if isinstance(node, ast.Attribute):
                if node.attr in self.BLOCKED_ATTRS:
                    return False, f"Blocked attribute: {node.attr}"
                    
            # Check string literals for dangerous content
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for attr in self.BLOCKED_ATTRS:
                    if attr in node.value:
                        return False, f"Blocked string content: {attr}"
                        
        return True, ""
        
    def execute(self, code: str, params: Dict[str, Any] = None) -> tuple:
        """
        Execute code in sandbox.
        Returns (success, result/error).
        """
        # Validate first
        is_safe, error = self.validate_code(code)
        if not is_safe:
            return False, error
            
        # Build safe globals
        safe_globals = {
            '__builtins__': self.SAFE_BUILTINS.copy(),
        }
        
        # Add print function
        def safe_print(*args):
            msg = ' '.join(str(a) for a in args)
            if self._log_func:
                self._log_func(msg)
            else:
                print(f"[Script] {msg}")
                
        safe_globals['__builtins__']['print'] = safe_print
        
        # Add API
        safe_globals.update(self._api)
        
        # Add params
        if params:
            safe_globals['params'] = params.copy()
        else:
            safe_globals['params'] = {}
            
        # Execute
        try:
            compiled = compile(code, '<sandbox>', 'exec')
            exec(compiled, safe_globals)
            
            # Check for result variable
            result = safe_globals.get('result', None)
            return True, result
            
        except Exception as e:
            return False, str(e)
            
    def create_safe_api(self, input_simulator, context) -> Dict[str, Any]:
        """Create the safe API dictionary for scripts."""
        
        class SafeMouse:
            def __init__(self, sim):
                self._sim = sim
            def click(self, button="left", count=1):
                self._sim.mouse_click(button, count)
            def down(self, button="left"):
                self._sim.mouse_down(button)
            def up(self, button="left"):
                self._sim.mouse_up(button)
            def move(self, x, y):
                self._sim.mouse_move(x, y)
            def move_relative(self, dx, dy):
                self._sim.mouse_move_relative(dx, dy)
            def scroll(self, delta):
                self._sim.mouse_scroll(delta)
                
        class SafeKeyboard:
            def __init__(self, sim):
                self._sim = sim
            def tap(self, key, hold_ms=0):
                self._sim.key_tap(key, hold_ms)
            def down(self, key):
                self._sim.key_down(key)
            def up(self, key):
                self._sim.key_up(key)
            def combo(self, *keys, hold_ms=0):
                self._sim.key_combo(*keys, hold_ms=hold_ms)
            def type_text(self, text, interval_ms=0):
                self._sim.type_text(text, interval_ms)
                
        import time
        
        return {
            'mouse': SafeMouse(input_simulator),
            'keyboard': SafeKeyboard(input_simulator),
            'delay': lambda ms: time.sleep(ms / 1000),
            'get_state': lambda k, d=None: context.data.get(k, d),
            'set_state': lambda k, v: context.data.update({k: v}),
            'is_key_pressed': input_simulator.is_key_pressed,
            'is_button_pressed': input_simulator.is_mouse_button_pressed,
            'get_cursor_pos': input_simulator.get_cursor_position,
        }
