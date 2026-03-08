"""
Gesture Detector Module

Detects mouse gesture patterns from movement data.
"""

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable


@dataclass
class GesturePoint:
    """A point in a gesture path."""
    x: int
    y: int
    timestamp: float


@dataclass
class DetectedGesture:
    """Result of gesture detection."""
    pattern_name: str
    confidence: float
    points: List[GesturePoint]
    total_distance: float
    duration_ms: float


class GestureDetector:
    """
    Detects mouse gestures from movement sequences.
    
    Features:
    - Direction vector analysis
    - Pattern matching with tolerance
    - Configurable sensitivity
    """
    
    # Direction angles (in degrees, 0 = right, counter-clockwise)
    DIRECTIONS = {
        "right": 0,
        "upright": 45,
        "up": 90,
        "upleft": 135,
        "left": 180,
        "downleft": 225,
        "down": 270,
        "downright": 315,
    }
    
    def __init__(self):
        self._patterns: Dict[str, Any] = {}  # GesturePattern objects
        self._current_gesture: List[GesturePoint] = []
        self._gesture_start_time: float = 0
        self._is_tracking: bool = False
        
        # Detection settings
        self.min_segment_distance = 20  # Min pixels to form a segment
        self.direction_tolerance = 45  # Degrees of tolerance
        self.gesture_timeout_ms = 1000  # Max time to complete gesture
        
        # Callbacks
        self._on_gesture_detected: Optional[Callable[[DetectedGesture], None]] = None
        
    def register_pattern(self, pattern):
        """Register a gesture pattern for detection."""
        self._patterns[pattern.name] = pattern
        
    def unregister_pattern(self, pattern_name: str):
        """Remove a gesture pattern."""
        self._patterns.pop(pattern_name, None)
        
    def clear_patterns(self):
        """Clear all patterns."""
        self._patterns.clear()
        
    def on_gesture_detected(self, callback: Callable[[DetectedGesture], None]):
        """Set callback for detected gestures."""
        self._on_gesture_detected = callback
        
    # ==================== TRACKING ====================
    
    def start_tracking(self, x: int, y: int):
        """Start tracking a potential gesture."""
        self._current_gesture = [GesturePoint(x, y, time.time())]
        self._gesture_start_time = time.time()
        self._is_tracking = True
        
    def add_point(self, x: int, y: int):
        """Add a point to the current gesture."""
        if not self._is_tracking:
            return
            
        # Check timeout
        if (time.time() - self._gesture_start_time) * 1000 > self.gesture_timeout_ms:
            self.cancel_tracking()
            return
            
        self._current_gesture.append(GesturePoint(x, y, time.time()))
        
    def end_tracking(self) -> Optional[DetectedGesture]:
        """End tracking and try to detect a gesture."""
        if not self._is_tracking:
            return None
            
        self._is_tracking = False
        
        if len(self._current_gesture) < 2:
            return None
            
        # Analyze the gesture
        detected = self._analyze_gesture()
        
        if detected and self._on_gesture_detected:
            self._on_gesture_detected(detected)
            
        return detected
        
    def cancel_tracking(self):
        """Cancel current gesture tracking."""
        self._is_tracking = False
        self._current_gesture = []
        
    # ==================== ANALYSIS ====================
    
    def _analyze_gesture(self) -> Optional[DetectedGesture]:
        """Analyze recorded gesture and match against patterns."""
        if len(self._current_gesture) < 2:
            return None
            
        # Simplify gesture to direction segments
        segments = self._simplify_to_segments()
        
        if not segments:
            return None
            
        # Calculate total distance and duration
        total_dist = self._calculate_total_distance()
        duration = (self._current_gesture[-1].timestamp - self._current_gesture[0].timestamp) * 1000
        
        # Match against patterns
        best_match = None
        best_confidence = 0.0
        
        for pattern in self._patterns.values():
            confidence = self._match_pattern(segments, pattern)
            if confidence > best_confidence and confidence >= 0.5:
                best_confidence = confidence
                best_match = pattern
                
        if best_match:
            return DetectedGesture(
                pattern_name=best_match.name,
                confidence=best_confidence,
                points=self._current_gesture.copy(),
                total_distance=total_dist,
                duration_ms=duration
            )
            
        return None
        
    def _simplify_to_segments(self) -> List[str]:
        """Simplify gesture points to direction segments."""
        if len(self._current_gesture) < 2:
            return []
            
        segments = []
        current_dir = None
        segment_start = self._current_gesture[0]
        
        for i in range(1, len(self._current_gesture)):
            point = self._current_gesture[i]
            dx = point.x - segment_start.x
            dy = point.y - segment_start.y
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist >= self.min_segment_distance:
                # Determine direction
                direction = self._get_direction(dx, dy)
                
                if direction != current_dir:
                    if current_dir is not None:
                        segments.append(current_dir)
                    current_dir = direction
                    segment_start = point
                    
        # Add final segment
        if current_dir is not None:
            segments.append(current_dir)
            
        return segments
        
    def _get_direction(self, dx: int, dy: int) -> str:
        """Get direction name from dx, dy."""
        # Calculate angle (note: screen Y is inverted)
        angle = math.degrees(math.atan2(-dy, dx))
        if angle < 0:
            angle += 360
            
        # Find closest direction
        best_dir = "right"
        best_diff = 360
        
        for dir_name, dir_angle in self.DIRECTIONS.items():
            diff = abs(angle - dir_angle)
            if diff > 180:
                diff = 360 - diff
            if diff < best_diff:
                best_diff = diff
                best_dir = dir_name
                
        return best_dir
        
    def _match_pattern(self, segments: List[str], pattern) -> float:
        """Match segments against a pattern. Returns confidence 0-1."""
        pattern_vectors = [v.direction for v in pattern.vectors]
        
        if len(segments) != len(pattern_vectors):
            return 0.0
            
        # Check each segment
        matches = 0
        for seg, pat in zip(segments, pattern_vectors):
            if self._directions_similar(seg, pat, pattern.tolerance):
                matches += 1
                
        return matches / len(pattern_vectors)
        
    def _directions_similar(self, dir1: str, dir2: str, tolerance: float) -> bool:
        """Check if two directions are similar within tolerance."""
        if dir1 == dir2:
            return True
            
        angle1 = self.DIRECTIONS.get(dir1, 0)
        angle2 = self.DIRECTIONS.get(dir2, 0)
        
        diff = abs(angle1 - angle2)
        if diff > 180:
            diff = 360 - diff
            
        # Tolerance is 0-1, map to degrees
        tolerance_degrees = tolerance * 90  # 0.5 = 45 degrees
        return diff <= tolerance_degrees
        
    def _calculate_total_distance(self) -> float:
        """Calculate total distance traveled."""
        if len(self._current_gesture) < 2:
            return 0.0
            
        total = 0.0
        for i in range(1, len(self._current_gesture)):
            p1 = self._current_gesture[i - 1]
            p2 = self._current_gesture[i]
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            total += math.sqrt(dx * dx + dy * dy)
            
        return total
