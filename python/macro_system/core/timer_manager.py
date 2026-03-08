"""
Timer Manager Module

Precise timing utilities for macro execution.
Uses high-resolution timers for gaming-grade accuracy.
"""

import time
import threading
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field
import ctypes


# Windows high-resolution timer
try:
    _kernel32 = ctypes.windll.kernel32
    _freq = ctypes.c_int64()
    _kernel32.QueryPerformanceFrequency(ctypes.byref(_freq))
    _PERF_FREQ = _freq.value
    _HAS_PERF_COUNTER = True
except Exception:
    _HAS_PERF_COUNTER = False
    _PERF_FREQ = 1


def precise_time() -> float:
    """Get high-resolution timestamp in seconds."""
    if _HAS_PERF_COUNTER:
        counter = ctypes.c_int64()
        _kernel32.QueryPerformanceCounter(ctypes.byref(counter))
        return counter.value / _PERF_FREQ
    return time.perf_counter()


def precise_sleep(seconds: float):
    """
    High-precision sleep using spin-wait for short durations.
    
    For durations < 2ms, uses spin-wait for accuracy.
    For longer durations, uses a hybrid approach.
    """
    if seconds <= 0:
        return
        
    target = precise_time() + seconds
    
    if seconds > 0.002:  # > 2ms
        # Sleep for most of the duration, then spin-wait
        time.sleep(seconds - 0.001)
        
    # Spin-wait for remaining time (high precision)
    while precise_time() < target:
        pass


@dataclass
class ScheduledTask:
    """A scheduled task to be executed."""
    id: str
    callback: Callable[[], None]
    fire_time: float
    interval_ms: Optional[float] = None  # For repeating tasks
    cancelled: bool = False


class TimerManager:
    """
    High-precision timer manager for macro timing.
    
    Features:
    - Sub-millisecond precision
    - One-shot and repeating timers
    - Minimal CPU usage when idle
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tasks: Dict[str, ScheduledTask] = {}
        self._task_lock = threading.Lock()
        self._next_id = 0
        
    def start(self):
        """Start the timer manager."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop the timer manager."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            
        with self._task_lock:
            self._tasks.clear()
            
    def schedule(
        self,
        callback: Callable[[], None],
        delay_ms: float,
        task_id: Optional[str] = None
    ) -> str:
        """
        Schedule a one-shot callback after delay_ms milliseconds.
        Returns the task ID for cancellation.
        """
        if task_id is None:
            task_id = f"task_{self._next_id}"
            self._next_id += 1
            
        fire_time = precise_time() + (delay_ms / 1000)
        
        task = ScheduledTask(
            id=task_id,
            callback=callback,
            fire_time=fire_time
        )
        
        with self._task_lock:
            self._tasks[task_id] = task
            
        return task_id
        
    def schedule_repeating(
        self,
        callback: Callable[[], None],
        interval_ms: float,
        initial_delay_ms: float = 0,
        task_id: Optional[str] = None
    ) -> str:
        """
        Schedule a repeating callback every interval_ms milliseconds.
        Returns the task ID for cancellation.
        """
        if task_id is None:
            task_id = f"repeat_{self._next_id}"
            self._next_id += 1
            
        delay = initial_delay_ms if initial_delay_ms > 0 else interval_ms
        fire_time = precise_time() + (delay / 1000)
        
        task = ScheduledTask(
            id=task_id,
            callback=callback,
            fire_time=fire_time,
            interval_ms=interval_ms
        )
        
        with self._task_lock:
            self._tasks[task_id] = task
            
        return task_id
        
    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task. Returns True if found and cancelled."""
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id].cancelled = True
                del self._tasks[task_id]
                return True
        return False
        
    def cancel_all(self):
        """Cancel all scheduled tasks."""
        with self._task_lock:
            for task in self._tasks.values():
                task.cancelled = True
            self._tasks.clear()
            
    def _timer_loop(self):
        """Main timer thread loop."""
        while self._running:
            now = precise_time()
            tasks_to_run = []
            next_fire = None
            
            with self._task_lock:
                # Find tasks ready to fire
                for task in list(self._tasks.values()):
                    if task.cancelled:
                        continue
                        
                    if task.fire_time <= now:
                        tasks_to_run.append(task)
                    else:
                        # Track next fire time
                        if next_fire is None or task.fire_time < next_fire:
                            next_fire = task.fire_time
                            
            # Execute ready tasks
            for task in tasks_to_run:
                if task.cancelled:
                    continue
                    
                try:
                    task.callback()
                except Exception as e:
                    print(f"[TimerManager] Task {task.id} error: {e}")
                    
                # Handle repeating tasks
                with self._task_lock:
                    if task.interval_ms and not task.cancelled and task.id in self._tasks:
                        task.fire_time = precise_time() + (task.interval_ms / 1000)
                        if next_fire is None or task.fire_time < next_fire:
                            next_fire = task.fire_time
                    elif task.id in self._tasks:
                        del self._tasks[task.id]
                        
            # Sleep until next task or check interval
            if next_fire:
                sleep_time = next_fire - precise_time()
                if sleep_time > 0.001:  # > 1ms
                    time.sleep(min(sleep_time, 0.01))  # Cap at 10ms for responsiveness
            else:
                time.sleep(0.01)  # No tasks, sleep 10ms


class Stopwatch:
    """Simple high-precision stopwatch."""
    
    def __init__(self):
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None
        
    def start(self):
        """Start or restart the stopwatch."""
        self._start_time = precise_time()
        self._stop_time = None
        
    def stop(self) -> float:
        """Stop the stopwatch and return elapsed time in seconds."""
        self._stop_time = precise_time()
        return self.elapsed
        
    def reset(self):
        """Reset the stopwatch."""
        self._start_time = None
        self._stop_time = None
        
    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self._start_time is None:
            return 0.0
            
        end = self._stop_time if self._stop_time else precise_time()
        return end - self._start_time
        
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return self.elapsed * 1000
        
    @property
    def is_running(self) -> bool:
        """Check if stopwatch is currently running."""
        return self._start_time is not None and self._stop_time is None
