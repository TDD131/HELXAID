"""
Macro Recorder Module

Records user inputs (mouse/keyboard) with timing for playback.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any
from enum import Enum


class RecordedActionType(Enum):
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    MOUSE_MOVE = "mouse_move"
    MOUSE_SCROLL = "mouse_scroll"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"


@dataclass
class RecordedAction:
    """A single recorded input action."""
    action_type: RecordedActionType
    timestamp: float = 0.0
    delay: float = 0.0  # Delay from previous action
    
    # Mouse data
    button: Optional[str] = None
    x: int = 0
    y: int = 0
    scroll_delta: int = 0
    
    # Keyboard data
    key_code: int = 0
    key_name: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "type": self.action_type.value,
            "timestamp": self.timestamp,
            "delay": self.delay,
            "button": self.button,
            "x": self.x,
            "y": self.y,
            "scroll_delta": self.scroll_delta,
            "key_code": self.key_code,
            "key_name": self.key_name
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RecordedAction":
        """Create from dictionary."""
        return cls(
            action_type=RecordedActionType(data["type"]),
            timestamp=data.get("timestamp", 0),
            delay=data.get("delay", 0),
            button=data.get("button"),
            x=data.get("x", 0),
            y=data.get("y", 0),
            scroll_delta=data.get("scroll_delta", 0),
            key_code=data.get("key_code", 0),
            key_name=data.get("key_name", "")
        )


@dataclass
class MacroRecording:
    """A complete macro recording."""
    name: str = "New Recording"
    actions: List[RecordedAction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    total_duration: float = 0.0
    loop_count: int = 1  # 0 = infinite
    speed_multiplier: float = 1.0
    playback_hotkey: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "actions": [a.to_dict() for a in self.actions],
            "created_at": self.created_at,
            "total_duration": self.total_duration,
            "loop_count": self.loop_count,
            "speed_multiplier": self.speed_multiplier,
            "playback_hotkey": self.playback_hotkey
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MacroRecording":
        return cls(
            name=data.get("name", "Recording"),
            actions=[RecordedAction.from_dict(a) for a in data.get("actions", [])],
            created_at=data.get("created_at", time.time()),
            total_duration=data.get("total_duration", 0),
            loop_count=data.get("loop_count", 1),
            speed_multiplier=data.get("speed_multiplier", 1.0),
            playback_hotkey=data.get("playback_hotkey", "")
        )


class MacroRecorder:
    """
    Records mouse and keyboard inputs with timing.
    
    Usage:
        recorder = MacroRecorder()
        recorder.start_recording()
        # ... user performs actions ...
        recorder.stop_recording()
        recording = recorder.get_recording()
    """
    
    def __init__(self):
        self._recording = False
        self._actions: List[RecordedAction] = []
        self._start_time: float = 0
        self._last_action_time: float = 0
        
        # Filters
        self.record_mouse_clicks: bool = True
        self.record_mouse_movement: bool = False  # Off by default (noisy)
        self.record_mouse_scroll: bool = True
        self.record_keyboard: bool = True
        
        # Movement sampling (reduce noise)
        self._last_move_time: float = 0
        self.movement_sample_rate: float = 0.05  # 50ms between move samples
        
        # Callbacks
        self.on_action_recorded: Optional[Callable[[RecordedAction], None]] = None
        
    @property
    def is_recording(self) -> bool:
        return self._recording
    
    @property
    def action_count(self) -> int:
        return len(self._actions)
    
    def start_recording(self):
        """Start recording inputs."""
        self._actions.clear()
        self._recording = True
        self._start_time = time.time()
        self._last_action_time = self._start_time
        self._last_move_time = 0
        print("[MacroRecorder] Recording started")
        
    def stop_recording(self) -> MacroRecording:
        """Stop recording and return the recording."""
        self._recording = False
        
        # Calculate total duration
        if self._actions:
            total_duration = self._actions[-1].timestamp - self._start_time
        else:
            total_duration = 0
            
        recording = MacroRecording(
            name=f"Recording {time.strftime('%H:%M:%S')}",
            actions=self._actions.copy(),
            total_duration=total_duration
        )
        
        print(f"[MacroRecorder] Recording stopped: {len(self._actions)} actions, {total_duration:.2f}s")
        return recording
    
    def get_recording(self) -> MacroRecording:
        """Get the current recording without stopping."""
        if self._actions:
            total_duration = self._actions[-1].timestamp - self._start_time
        else:
            total_duration = 0
            
        return MacroRecording(
            actions=self._actions.copy(),
            total_duration=total_duration
        )
    
    def clear(self):
        """Clear recorded actions."""
        self._actions.clear()
        
    def record_mouse_event(self, event_type: str, button: Optional[str], x: int, y: int, scroll_delta: int = 0):
        """Record a mouse event."""
        if not self._recording:
            return
            
        # Filter based on settings
        if event_type in ("mouse_down", "mouse_up") and not self.record_mouse_clicks:
            return
        if event_type == "mouse_move" and not self.record_mouse_movement:
            return
        if event_type == "mouse_scroll" and not self.record_mouse_scroll:
            return
            
        # Rate limit mouse movement
        if event_type == "mouse_move":
            now = time.time()
            if now - self._last_move_time < self.movement_sample_rate:
                return
            self._last_move_time = now
            
        self._add_action(RecordedAction(
            action_type=RecordedActionType(event_type),
            button=button,
            x=x,
            y=y,
            scroll_delta=scroll_delta
        ))
        
    def record_keyboard_event(self, event_type: str, key_code: int, key_name: str):
        """Record a keyboard event."""
        if not self._recording or not self.record_keyboard:
            return
            
        self._add_action(RecordedAction(
            action_type=RecordedActionType(event_type),
            key_code=key_code,
            key_name=key_name
        ))
        
    def _add_action(self, action: RecordedAction):
        """Add an action with timing."""
        now = time.time()
        action.timestamp = now
        action.delay = now - self._last_action_time
        self._last_action_time = now
        
        self._actions.append(action)
        
        if self.on_action_recorded:
            self.on_action_recorded(action)


class MacroPlayer:
    """
    Plays back a recorded macro.
    """
    
    def __init__(self, simulator=None):
        self._playing = False
        self._should_stop = False
        self._simulator = simulator
        self._current_loop = 0
        
    @property
    def is_playing(self) -> bool:
        return self._playing
    
    def stop(self):
        """Stop playback."""
        self._should_stop = True
        
    def play(self, recording: MacroRecording, simulator=None):
        """
        Play a recording.
        Should be called in a separate thread.
        """
        if self._playing:
            return
            
        sim = simulator or self._simulator
        if not sim:
            print("[MacroPlayer] No simulator available")
            return
            
        self._playing = True
        self._should_stop = False
        
        loop_count = recording.loop_count if recording.loop_count > 0 else float('inf')
        speed = recording.speed_multiplier
        
        print(f"[MacroPlayer] Playing: {recording.name} ({len(recording.actions)} actions, {loop_count} loops)")
        
        try:
            loop = 0
            while loop < loop_count and not self._should_stop:
                loop += 1
                self._current_loop = loop
                
                for action in recording.actions:
                    if self._should_stop:
                        break
                        
                    # Wait for delay (adjusted by speed)
                    if action.delay > 0:
                        time.sleep(action.delay / speed)
                        
                    # Execute action
                    self._execute_action(action, sim)
                    
        finally:
            self._playing = False
            self._current_loop = 0
            print("[MacroPlayer] Playback finished")
            
    def _execute_action(self, action: RecordedAction, sim):
        """Execute a single recorded action."""
        try:
            if action.action_type == RecordedActionType.MOUSE_DOWN:
                # Move to position first, then press
                sim.mouse_move(action.x, action.y)
                sim.mouse_down(action.button or "left")
            elif action.action_type == RecordedActionType.MOUSE_UP:
                sim.mouse_up(action.button or "left")
            elif action.action_type == RecordedActionType.MOUSE_MOVE:
                sim.mouse_move(action.x, action.y)
            elif action.action_type == RecordedActionType.MOUSE_SCROLL:
                sim.mouse_scroll(action.scroll_delta)
            elif action.action_type == RecordedActionType.KEY_DOWN:
                sim.key_down(action.key_name or str(action.key_code))
            elif action.action_type == RecordedActionType.KEY_UP:
                sim.key_up(action.key_name or str(action.key_code))
        except Exception as e:
            print(f"[MacroPlayer] Action error: {e}")
