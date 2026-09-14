"""
Toggle Macro Module

Macros that toggle ON/OFF and persist state while active.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import asyncio
import time
import ctypes
import sys

from .base_macro import BaseMacro, MacroAction, MacroTrigger

if TYPE_CHECKING:
    from ..core.macro_engine import ExecutionContext


@dataclass  
class ToggleMacro(BaseMacro):
    """
    Toggle macro that can be switched ON/OFF.
    
    While ON, can:
    - Repeat an action at an interval (e.g., auto-clicker)
    - Hold a key/button down
    - Run a continuous script
    """
    
    is_toggle: bool = True  # Override - always a toggle
    execution_mode: str = "standard"  # "standard" (OS-Safe, zero-backlog) | "turbo" (1340+ CPS bypass)
    
    # Action to perform while ON
    on_action: Optional[MacroAction] = None
    
    # For repeating actions
    repeat_action: Optional[MacroAction] = None
    repeat_interval_ms: int = 100
    
    # For held keys/buttons
    hold_key: Optional[str] = None
    hold_button: Optional[str] = None
    
    # Actions to run when toggled ON
    on_activate_actions: List[MacroAction] = field(default_factory=list)
    
    # Actions to run when toggled OFF
    on_deactivate_actions: List[MacroAction] = field(default_factory=list)
    
    async def execute(self, context: 'ExecutionContext') -> None:
        """Execute toggle behavior."""
        sim = context.simulator
        winmm = None
        try:
            winmm = ctypes.windll.winmm
            winmm.timeBeginPeriod(1)
        except Exception:
            winmm = None
        
        try:
            # Run activation actions
            for action in self.on_activate_actions:
                await action.execute(context)
                
            # Hold key/button if specified
            if self.hold_key:
                sim.key_down(self.hold_key)
            if self.hold_button:
                sim.mouse_down(self.hold_button)
                
            # One-time action
            if self.on_action:
                await self.on_action.execute(context)
                
            # Repeat action while toggled ON
            if self.repeat_action:
                # Fast Path for high-speed Auto-Clickers & Key Auto-Pressers
                repeat_act_type = getattr(self.repeat_action, 'type', None)
                if hasattr(repeat_act_type, 'value'):
                    repeat_act_type = repeat_act_type.value
                elif isinstance(repeat_act_type, str):
                    repeat_act_type = repeat_act_type.lower()

                fast_inputs = None

                if repeat_act_type == "mouse_click" and hasattr(sim, '_get_click_array'):
                    btn = getattr(self.repeat_action, 'button', 'left') or 'left'
                    fast_inputs = sim._get_click_array(str(btn))
                elif repeat_act_type == "key_tap" and hasattr(sim, '_get_key_tap_array'):
                    hold = getattr(self.repeat_action, 'hold_ms', 0) or 0
                    if hold <= 0:
                        k = getattr(self.repeat_action, 'key', 'a') or 'a'
                        fast_inputs = sim._get_key_tap_array(str(k))

                if fast_inputs is not None:
                    byref_inputs = ctypes.byref(fast_inputs)
                    sizeof_input = ctypes.sizeof(fast_inputs._type_)
                    send_input = sim._user32.SendInput

                    try:
                        sys.setswitchinterval(0.0005)
                    except Exception:
                        pass

                    mode = str(getattr(self, 'execution_mode', 'standard') or 'standard').lower()
                    is_turbo = mode in ("turbo", "bypass", "raw", "overdrive")

                    interval_ms = max(1, int(self.repeat_interval_ms))

                    if is_turbo:
                        # 1. TURBO MODE (BYPASS): Force Windows with microsecond spin-wait (1340+ CPS for 1ms)
                        if interval_ms <= 1:
                            target_dt = 0.000746
                            yield_mask = 31
                        elif interval_ms <= 24:
                            target_dt = interval_ms / 1000.0
                            yield_mask = 7
                        else:
                            target_dt = interval_ms / 1000.0
                            yield_mask = 1

                        cycle = 0
                        next_time = time.perf_counter()

                        if interval_ms <= 24:
                            while True:
                                if context.cancelled:
                                    break

                                send_input(2, byref_inputs, sizeof_input)
                                cycle += 1
                                next_time += target_dt

                                now = time.perf_counter()
                                if now < next_time:
                                    while time.perf_counter() < next_time:
                                        if context.cancelled:
                                            break
                                elif now - next_time > target_dt * 2:
                                    next_time = now

                                if (cycle & yield_mask) == 0:
                                    await asyncio.sleep(0)
                        else:
                            while True:
                                if context.cancelled:
                                    break
                                send_input(2, byref_inputs, sizeof_input)
                                await context.delay(self.repeat_interval_ms)
                    else:
                        # 2. STANDARD MODE (OS-SAFE): Standard OS message queue pacing (~30-33 CPS safe baseline)
                        effective_delay = max(30, interval_ms) if interval_ms <= 30 else interval_ms
                        while True:
                            if context.cancelled:
                                break
                            send_input(2, byref_inputs, sizeof_input)
                            await context.delay(effective_delay)
                else:
                    # Generic fallback for complex repeat actions
                    mode = str(getattr(self, 'execution_mode', 'standard') or 'standard').lower()
                    is_turbo = mode in ("turbo", "bypass", "raw", "overdrive")
                    interval_ms = max(1, int(self.repeat_interval_ms))

                    if is_turbo:
                        target_dt = 0.000746 if interval_ms <= 1 else (interval_ms / 1000.0)
                        next_time = time.perf_counter()
                        cycle = 0
                        while True:
                            if context.cancelled:
                                break
                            await self.repeat_action.execute(context)
                            cycle += 1
                            next_time += target_dt
                            now = time.perf_counter()
                            if now < next_time:
                                while time.perf_counter() < next_time:
                                    if context.cancelled:
                                        break
                            elif now - next_time > target_dt * 2:
                                next_time = now
                            if (cycle & 7) == 0:
                                await asyncio.sleep(0)
                    else:
                        effective_delay = max(30, interval_ms) if interval_ms <= 30 else interval_ms
                        while True:
                            if context.cancelled:
                                break
                            await self.repeat_action.execute(context)
                            await context.delay(effective_delay)
            else:
                # No repeat action - just wait until cancelled
                while True:
                    context.check_cancelled()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[ToggleMacro] Execution error: {e}")
        finally:
            if winmm:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:
                    pass
            # Safety First: Always release inputs and run cleanup on cancellation or exit!
            await self.cleanup(context)
                
    def cancel(self) -> None:
        """Called when toggle is turned OFF."""
        # Release held keys/buttons (done in the finally block ideally)
        pass
        
    async def cleanup(self, context: 'ExecutionContext'):
        """Cleanup when toggled OFF."""
        sim = context.simulator
        
        # Release held inputs
        if self.hold_key:
            sim.key_up(self.hold_key)
        if self.hold_button:
            sim.mouse_up(self.hold_button)

        # Explicit release for repeat actions in case cancelled mid-stroke
        if self.repeat_action:
            repeat_act_type = getattr(self.repeat_action, 'type', None)
            if hasattr(repeat_act_type, 'value'):
                repeat_act_type = repeat_act_type.value
            elif isinstance(repeat_act_type, str):
                repeat_act_type = repeat_act_type.lower()
            
            if repeat_act_type == "mouse_click":
                btn = getattr(self.repeat_action, 'button', 'left') or 'left'
                sim.mouse_up(str(btn))
            elif repeat_act_type == "key_tap":
                k = getattr(self.repeat_action, 'key', None)
                if k:
                    sim.key_up(str(k))
            
        # Run deactivation actions
        for action in self.on_deactivate_actions:
            try:
                await action.execute(context)
            except:
                pass
                
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "execution_mode": getattr(self, 'execution_mode', 'standard'),
            "on_action": self.on_action.to_dict() if self.on_action else None,
            "repeat_action": self.repeat_action.to_dict() if self.repeat_action else None,
            "repeat_interval_ms": self.repeat_interval_ms,
            "hold_key": self.hold_key,
            "hold_button": self.hold_button,
            "on_activate_actions": [a.to_dict() for a in self.on_activate_actions],
            "on_deactivate_actions": [a.to_dict() for a in self.on_deactivate_actions],
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToggleMacro':
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=data.get("enabled", True),
            execution_mode=data.get("execution_mode", "standard"),
            description=data.get("description", ""),
            trigger=MacroTrigger.from_dict(data["trigger"]) if data.get("trigger") else None,
            layer=data.get("layer", "default"),
            on_action=MacroAction.from_dict(data["on_action"]) if data.get("on_action") else None,
            repeat_action=MacroAction.from_dict(data["repeat_action"]) if data.get("repeat_action") else None,
            repeat_interval_ms=data.get("repeat_interval_ms", 100),
            hold_key=data.get("hold_key"),
            hold_button=data.get("hold_button"),
            on_activate_actions=[MacroAction.from_dict(a) for a in data.get("on_activate_actions", [])],
            on_deactivate_actions=[MacroAction.from_dict(a) for a in data.get("on_deactivate_actions", [])],
        )
