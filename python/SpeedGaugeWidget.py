"""
High-Tech Vector Speed Gauge Widget for HELXTATS Speedtest Lab.
Custom Tachometer & Real-time Throughput Gauge built purely with QPainter,
Orbitron typography, and smooth hardware-accelerated animations.

Component Name: SpeedGaugeWidget
"""

import math
import time
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QRadialGradient, 
    QBrush, QLinearGradient
)


class SpeedGaugeWidget(QWidget):
    """
    Circular vector speed gauge rendering real-time Mbps bandwidth,
    animated sweep needle, stable logarithmic/dynamic tick scale, and stage subtitles.
    
    Component Name: SpeedGaugeWidget
    """

    def __init__(self, max_speed: float = 500.0, parent=None):
        super().__init__(parent)
        self.setObjectName("SpeedGaugeWidget")
        self.setMinimumSize(240, 240)
        self.setMaximumSize(360, 360)

        self._max_speed = 500.0         # Default stable standard tier (500 Mbps)
        self._target_max_speed = 500.0
        self._current_speed = 0.0       # Target value
        self._animated_speed = 0.0      # Smoothed display value (60 FPS lerp)
        self._peak_speed = 0.0          # Peak Mbps recorded in session
        self._stage_text = "READY"
        self._unit_text = "Mbps"
        self._active_color = QColor("#FF5B06")  # HELXAID Orange accent

        # Decay animation parameters
        self._is_decaying = False
        self._decay_start_speed = 0.0
        self._decay_start_time = 0.0
        self._decay_duration = 6.0

        # Continuous smooth 60 FPS interpolation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._step_animation)
        self._anim_timer.start()

    def set_speed(self, speed_mbps: float):
        """Update target speed value in Mbps."""
        self._is_decaying = False
        val = max(0.0, float(speed_mbps))
        self._current_speed = val
        
        # Determine appropriate max scale tier without jitter
        if val > 950.0:
            self._target_max_speed = 2500.0
        elif val > 480.0:
            self._target_max_speed = 1000.0
        else:
            self._target_max_speed = 500.0

    def decay_to_zero(self, duration: float = 6.0):
        """Smoothly ease current speed down to 0.0 Mbps over a specified duration (e.g. 6.0s)."""
        if self._animated_speed <= 0.05:
            self._current_speed = 0.0
            self._animated_speed = 0.0
            self._is_decaying = False
            self.update()
            return

        self._decay_start_speed = self._animated_speed
        self._decay_start_time = time.perf_counter()
        self._decay_duration = max(0.1, duration)
        self._is_decaying = True
        self._current_speed = 0.0

    def set_stage(self, stage_text: str, color_hex: str = "#FF5B06"):
        """Update current stage label (e.g. 'DOWNLOAD', 'UPLOAD', 'PING', 'COMPLETE')."""
        self._stage_text = str(stage_text).upper()
        self._active_color = QColor(color_hex)
        self.update()

    def reset_peak(self, new_peak: float = 0.0):
        """Reset peak speed to 0.0 (or a specific value) when transitioning between test stages."""
        self._peak_speed = max(0.0, float(new_peak))
        self._current_speed = 0.0
        self._animated_speed = 0.0
        self._is_decaying = False
        self.update()

    def reset_gauge(self):
        """Reset gauge values back to initial zero state."""
        self._is_decaying = False
        self._current_speed = 0.0
        self._animated_speed = 0.0
        self._peak_speed = 0.0
        self._max_speed = 500.0
        self._target_max_speed = 500.0
        self._stage_text = "READY"
        self._active_color = QColor("#FF5B06")
        self.update()

    def _step_animation(self):
        """Smooth continuous lerp interpolation for silky needle movement."""
        # 1. Smoothly transition max scale tier if needed
        max_diff = self._target_max_speed - self._max_speed
        if abs(max_diff) > 1.0:
            self._max_speed += max_diff * 0.08
        else:
            self._max_speed = self._target_max_speed

        # 2. Smoothly transition current speed
        if getattr(self, '_is_decaying', False):
            elapsed = time.perf_counter() - self._decay_start_time
            progress = min(1.0, elapsed / self._decay_duration)
            ease_factor = (1.0 - progress) ** 2.5
            self._animated_speed = self._decay_start_speed * ease_factor
            if progress >= 1.0 or self._animated_speed < 0.02:
                self._animated_speed = 0.0
                self._current_speed = 0.0
                self._is_decaying = False
        else:
            diff = self._current_speed - self._animated_speed
            if abs(diff) < 0.02:
                self._animated_speed = self._current_speed
            else:
                # Continuous critically damped easing (0.12 factor)
                self._animated_speed += diff * 0.12

        # 3. Track smoothed peak (only while active test is running and not decaying)
        if not getattr(self, '_is_decaying', False) and self._animated_speed > self._peak_speed:
            self._peak_speed = self._animated_speed

        self.update()

    def _speed_to_angle(self, speed: float) -> float:
        """
        Map speed value (0 .. max_speed) to arc angle in degrees.
        Total sweep = 240 degrees (from 150 deg on left to 390 deg on right).
        Uses a fixed exponent power curve (0.60) for optimal visual spread across 0-500 Mbps.
        """
        effective_max = max(100.0, self._max_speed)
        clamped = max(0.0, min(speed, effective_max))
        fraction = math.pow(clamped / effective_max, 0.60)
        return 150.0 + (fraction * 240.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        width = self.width()
        height = self.height()
        size = min(width, height)
        
        center_x = width / 2.0
        center_y = height / 2.0
        radius = (size / 2.0) - 16.0

        if radius <= 20:
            return

        arc_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # ── 1. BACKGROUND GLOW & TRACK ───────────────────────
        bg_pen = QPen(QColor(255, 255, 255, 14), 10.0, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(arc_rect, int(-150 * 16), int(-240 * 16))

        # ── 2. TICK MARKS & SCALE NUMBERS ────────────────────
        if self._max_speed >= 2000:
            tick_speeds = [0, 250, 500, 1000, 1500, 2000, 2500]
        elif self._max_speed >= 800:
            tick_speeds = [0, 50, 100, 250, 500, 750, 1000]
        else:
            tick_speeds = [0, 25, 50, 100, 200, 350, 500]

        painter.setFont(QFont("Orbitron", 8, QFont.Bold))
        for ts in tick_speeds:
            if ts > self._max_speed * 1.05:
                continue
            deg = self._speed_to_angle(ts)
            rad = math.radians(deg)

            # Outer tick position
            x_outer = center_x + (radius - 8.0) * math.cos(rad)
            y_outer = center_y + (radius - 8.0) * math.sin(rad)
            x_inner = center_x + (radius - 16.0) * math.cos(rad)
            y_inner = center_y + (radius - 16.0) * math.sin(rad)

            # Highlight ticks below current speed
            is_active = self._animated_speed >= ts
            tick_color = self._active_color if is_active else QColor(255, 255, 255, 40)
            
            painter.setPen(QPen(tick_color, 2.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x_inner, y_inner), QPointF(x_outer, y_outer))

        # ── 3. ACTIVE GLOWING PROGRESS ARC ───────────────────
        if self._animated_speed > 0.05:
            current_angle = self._speed_to_angle(self._animated_speed)
            sweep_deg = current_angle - 150.0

            # Dynamic gradient for active arc matching current stage
            grad = QLinearGradient(arc_rect.topLeft(), arc_rect.bottomRight())
            if "UPLOAD" in self._stage_text:
                # Signature HELXAID Orange -> Amber -> Coral glow
                grad.setColorAt(0.0, QColor("#FF5B06"))
                grad.setColorAt(0.5, QColor("#FDA903"))
                grad.setColorAt(1.0, QColor("#FF007A"))
            elif "DOWNLOAD" in self._stage_text:
                # Cyan -> Electric Blue glow
                grad.setColorAt(0.0, QColor("#00B4D8"))
                grad.setColorAt(0.5, QColor("#00E5FF"))
                grad.setColorAt(1.0, QColor("#0077B6"))
            elif "PING" in self._stage_text:
                # Emerald Green glow
                grad.setColorAt(0.0, QColor("#059669"))
                grad.setColorAt(0.5, QColor("#4ADE80"))
                grad.setColorAt(1.0, QColor("#10B981"))
            else:
                grad.setColorAt(0.0, self._active_color.darker(120))
                grad.setColorAt(0.5, self._active_color)
                grad.setColorAt(1.0, self._active_color.lighter(120))

            active_pen = QPen(QBrush(grad), 10.0, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(active_pen)
            painter.drawArc(arc_rect, int(-150 * 16), int(-sweep_deg * 16))

            # ── 4. GLOWING NEEDLE HEAD POINT ─────────────────
            tip_rad = math.radians(current_angle)
            tip_x = center_x + (radius) * math.cos(tip_rad)
            tip_y = center_y + (radius) * math.sin(tip_rad)

            # Draw glowing halo around needle tip
            halo_grad = QRadialGradient(tip_x, tip_y, 14.0)
            halo_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
            halo_grad.setColorAt(0.4, self._active_color)
            halo_grad.setColorAt(1.0, QColor(self._active_color.red(), self._active_color.green(), self._active_color.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(halo_grad))
            painter.drawEllipse(QPointF(tip_x, tip_y), 12.0, 12.0)

        # ── 5. INNER DIAL & DIGITAL SPEED DISPLAY ────────────
        inner_radius = radius * 0.72
        inner_rect = QRectF(center_x - inner_radius, center_y - inner_radius, inner_radius * 2, inner_radius * 2)
        
        inner_grad = QRadialGradient(center_x, center_y, inner_radius)
        inner_grad.setColorAt(0.0, QColor(25, 25, 30, 220))
        inner_grad.setColorAt(0.85, QColor(16, 16, 20, 240))
        inner_grad.setColorAt(1.0, QColor(35, 35, 42, 200))
        
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1.5))
        painter.setBrush(QBrush(inner_grad))
        painter.drawEllipse(inner_rect)

        # Stage Status Badge (e.g. "DOWNLOAD")
        painter.setFont(QFont("Orbitron", 9, QFont.Bold))
        painter.setPen(self._active_color)
        stage_rect = QRectF(center_x - 80, center_y - (inner_radius * 0.58), 160, 20)
        painter.drawText(stage_rect, Qt.AlignCenter, self._stage_text)

        # Digital Speed Value (Large Orbitron)
        speed_str = f"{self._animated_speed:.1f}" if self._animated_speed < 100 else f"{self._animated_speed:.0f}"
        font_size = 28 if len(speed_str) <= 4 else 23
        painter.setFont(QFont("Orbitron", font_size, QFont.Bold))
        painter.setPen(QColor("#FFFFFF"))
        
        val_rect = QRectF(center_x - 90, center_y - 14, 180, 36)
        painter.drawText(val_rect, Qt.AlignCenter, speed_str)

        # Unit Label ("Mbps")
        painter.setFont(QFont("Orbitron", 9, QFont.Bold))
        painter.setPen(QColor(160, 160, 160))
        unit_rect = QRectF(center_x - 50, center_y + 22, 100, 18)
        painter.drawText(unit_rect, Qt.AlignCenter, self._unit_text)

        # Peak indicator subtitle
        if self._peak_speed > 0.05:
            painter.setFont(QFont("Orbitron", 8))
            painter.setPen(QColor(110, 110, 120))
            peak_rect = QRectF(center_x - 80, center_y + (inner_radius * 0.52), 160, 16)
            painter.drawText(peak_rect, Qt.AlignCenter, f"PEAK: {self._peak_speed:.1f} Mbps")

        painter.end()
