"""
Hardware Panel Widget - System Monitoring Dashboard

Features:
- RAM Cleaner with circular gauge
- CPU/RAM/Disk/Network monitoring charts
- Hardware Health (temps)
- Customizable update interval (100-1000ms)

Component Name: HardwarePanelWidget
"""

from PySide6.QtWidgets import QComboBox
from PySide6.QtGui import QGradient
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QGridLayout, QSlider, QLineEdit,
    QScrollArea, QSizePolicy, QGraphicsDropShadowEffect, QProgressBar,
    QCheckBox, QGroupBox, QDialog, QListWidget, QListWidgetItem,
    QGraphicsOpacityEffect, QSplitter, QSplitterHandle
)
from AnimatedButton import AnimatedCheckBox
from smooth_scroll import SmoothScrollArea, SmoothTableWidget
from PySide6.QtCore import Qt, Signal, QTimer, QSize, Slot, QThread, QPropertyAnimation, QEasingCurve, QRect, Property
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, 
    QConicalGradient, QIntValidator, QPixmap, QFontMetrics, QImage
)
from PySide6.QtSvg import QSvgRenderer

import collections
import threading
import pyqtgraph as pg
from datetime import datetime
from hardware_wrapper import get_monitor, HardwareMonitor

import os
import io
import time

# Maximum chart history points (10 minutes at 500ms = 1200 points)
MAX_CHART_HISTORY = 1200

# Try to import icoextract for exe icon extraction
try:
    from icoextract import IconExtractor
    ICOEXTRACT_AVAILABLE = True
except ImportError:
    ICOEXTRACT_AVAILABLE = False
    print("[Hardware] icoextract not available, using default icons")


# ============================================
# CUSTOM WIDGETS
# ============================================

class CircularGauge(QWidget):
    """
    Circular gauge widget for displaying percentage values.
    
    Component Name: CircularGauge
    """
    clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CircularGauge")
        self._value = 0
        self._max_value = 100
        self._title = ""
        self._subtitle = ""
        self._accent_color = QColor("#FF5B06")
        self._bg_color = QColor("#2a2a2a")
        
        self._show_text = True
        self._is_animated = False
        self._gradient_angle = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = None

        self.setMinimumSize(200, 200)

    def trigger_fade_transition(self, duration_ms: int = 220, on_midpoint_callback=None):
        """
        Soft pulse transition (1.0 -> 0.70 -> 1.0) to prevent fading to black.
        """
        if getattr(self, '_fade_anim', None) and self._fade_anim.state() == QPropertyAnimation.Running:
            self._fade_anim.stop()

        half_dur = max(30, duration_ms // 2)
        anim_out = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim_out.setDuration(half_dur)
        anim_out.setStartValue(self._opacity_effect.opacity())
        anim_out.setEndValue(0.70)
        anim_out.setEasingCurve(QEasingCurve.OutQuad)

        def _on_fade_out_finished():
            if on_midpoint_callback:
                on_midpoint_callback()
            anim_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
            anim_in.setDuration(half_dur)
            anim_in.setStartValue(0.70)
            anim_in.setEndValue(1.0)
            anim_in.setEasingCurve(QEasingCurve.InQuad)
            anim_in.start()
            self._fade_anim = anim_in

        anim_out.finished.connect(_on_fade_out_finished)
        anim_out.start()
        self._fade_anim = anim_out
    
    def showEvent(self, event):
        super().showEvent(event)
        if (getattr(self, '_is_animated', False) or getattr(self, '_use_gradient_for_value', False)) and not self._anim_timer.isActive():
            self._anim_timer.start(33)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def pause_animation(self):
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def resume_animation(self):
        if (getattr(self, '_is_animated', False) or getattr(self, '_use_gradient_for_value', False)) and self.isVisible() and not self._anim_timer.isActive():
            self._anim_timer.start(33)

    def setShowText(self, show: bool):
        self._show_text = show
        self.update()
        
    def setAnimated(self, animated: bool):
        self._is_animated = animated
        if animated and self.isVisible() and not self._anim_timer.isActive():
            self._anim_timer.start(33)
        elif not animated and not getattr(self, '_use_gradient_for_value', False) and self._anim_timer.isActive():
            self._anim_timer.stop()
        self.update()
        
    def setUseGradientForValue(self, use_gradient: bool):
        self._use_gradient_for_value = use_gradient
        if use_gradient and self.isVisible() and not self._anim_timer.isActive():
            self._anim_timer.start(33)
        elif not use_gradient and not getattr(self, '_is_animated', False) and self._anim_timer.isActive():
            self._anim_timer.stop()
        self.update()
        
    def _update_animation(self):
        if getattr(self, '_clockwise', False):
            self._gradient_angle = (self._gradient_angle - 4) % 360
        else:
            self._gradient_angle = (self._gradient_angle + 4) % 360
        self.update()
        
    def setClockwise(self, clockwise: bool):
        self._clockwise = clockwise
    
    def setValue(self, value: float):
        self._value = max(0, min(self._max_value, value))
        self.update()
    
    def setTitle(self, title: str):
        self._title = title
        self.update()
    
    def setSubtitle(self, subtitle: str):
        self._subtitle = subtitle
        self.update()
    
    def setAccentColor(self, color: QColor):
        self._accent_color = color
        self.update()
        
    def setGrayscale(self, grayscale: bool):
        self._is_grayscale = grayscale
        self.update()

    def setCenterText(self, text: str):
        self._center_text = text
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate dimensions
        size = min(self.width(), self.height())
        margin = 15
        arc_width = 12
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = (size - margin * 2) / 2
        
        # Background arc
        is_animated = getattr(self, '_is_animated', False)
        
        bg_pen = QPen(self._bg_color, arc_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(bg_pen)
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        # Center the rect
        rect.moveCenter(self.rect().center())
        
        if is_animated:
            painter.drawArc(rect, 0, 360 * 16)
        else:
            painter.drawArc(rect, 225 * 16, -270 * 16)
        
        # Value arc with gradient
        if is_animated or self._value > 0:
            if is_animated:
                sweep = 360 * 16
                if getattr(self, '_is_grayscale', False):
                    # Perfectly symmetrical metallic silver linear gradient flowing to the left
                    # Use a continuous accumulator to avoid origin jumps that cause Qt rendering stutter
                    if not hasattr(self, '_linear_shift'):
                        self._linear_shift = 0.0
                    
                    # Advance by the equivalent of 4 degrees
                    step = (4.0 / 360.0) * rect.width()
                    self._linear_shift += step
                    
                    # Wrap safely at exactly 100x width to prevent float overflow while maintaining perfect tiling
                    wrap_limit = rect.width() * 100
                    if self._linear_shift > wrap_limit:
                        self._linear_shift -= wrap_limit
                        
                    x1 = rect.right() - self._linear_shift
                    x2 = x1 - rect.width()
                    
                    # Use 0 for Y-coordinates to create a purely horizontal gradient vector
                    gradient = QLinearGradient(x1, 0, x2, 0)
                    gradient.setSpread(QGradient.RepeatSpread)
                    gradient.setColorAt(0.0, QColor('#555555'))
                    gradient.setColorAt(0.5, QColor('#737373'))
                    gradient.setColorAt(1.0, QColor('#555555'))
                else:
                    gradient = QConicalGradient(rect.center(), self._gradient_angle)
                    gradient.setColorAt(0.0, QColor('#ff3da7'))
                    gradient.setColorAt(0.25, QColor('#ff0c2b'))
                    gradient.setColorAt(0.5, QColor('#ff5700'))
                    gradient.setColorAt(0.75, QColor('#ffab00'))
                    gradient.setColorAt(1.0, QColor('#ff3da7'))
                gradient_pen = QPen(QBrush(gradient), arc_width, Qt.SolidLine, Qt.RoundCap)
                painter.setPen(gradient_pen)
                painter.drawArc(rect, 0, sweep)
            else:
                sweep = int(-270 * (self._value / self._max_value) * 16)
                if getattr(self, '_use_gradient_for_value', False):
                    if not hasattr(self, '_linear_shift'):
                        self._linear_shift = 0.0
                    step = (4.0 / 360.0) * rect.width()
                    self._linear_shift += step
                    wrap_limit = rect.width() * 100
                    if self._linear_shift > wrap_limit:
                        self._linear_shift -= wrap_limit
                    x1 = rect.right() - self._linear_shift
                    x2 = x1 - rect.width()
                    
                    gradient = QLinearGradient(x1, 0, x2, 0)
                    gradient.setSpread(QGradient.RepeatSpread)
                    gradient.setColorAt(0.0, QColor('#ff3da7'))
                    gradient.setColorAt(0.25, QColor('#ff0c2b'))
                    gradient.setColorAt(0.5, QColor('#ff5700'))
                    gradient.setColorAt(0.75, QColor('#ffab00'))
                    gradient.setColorAt(1.0, QColor('#ff3da7'))
                    gradient_pen = QPen(QBrush(gradient), arc_width, Qt.SolidLine, Qt.RoundCap)
                else:
                    gradient_pen = QPen(self._accent_color, arc_width, Qt.SolidLine, Qt.RoundCap)
                painter.setPen(gradient_pen)
                painter.drawArc(rect, 225 * 16, sweep)
        
        if getattr(self, '_show_text', True):
            center_txt = getattr(self, '_center_text', None)
            if center_txt:
                if "Scanning" in center_txt:
                    font_size = int(size * 0.075)
                    primary_color = QColor("#ffffff")
                elif "GB" in center_txt or "MB" in center_txt or "KB" in center_txt or "B" in center_txt:
                    font_size = int(size * 0.10)
                    primary_color = QColor("#FF5B06")
                elif center_txt == "CLEANED":
                    font_size = int(size * 0.09)
                    primary_color = QColor("#00FF66")
                else:
                    font_size = int(size * 0.09)
                    primary_color = QColor("#ffffff")
                
                center_font = QFont("Orbitron", font_size, QFont.Bold)
                fm = QFontMetrics(center_font)
                max_width = int(size - margin * 2 - 28)
                while fm.horizontalAdvance(center_txt) > max_width and font_size > 8:
                    font_size -= 1
                    center_font.setPointSize(font_size)
                    fm = QFontMetrics(center_font)

                painter.setPen(primary_color)
                painter.setFont(center_font)
                
                if self._subtitle:
                    y_offset = int(-size * 0.05)
                    txt_rect = self.rect().translated(0, y_offset)
                    painter.drawText(txt_rect, Qt.AlignCenter, center_txt)
                    
                    painter.setPen(QColor("#aaaaaa"))
                    sub_font = QFont("Orbitron", int(size * 0.052))
                    painter.setFont(sub_font)
                    sub_rect = txt_rect.translated(0, int(size * 0.125))
                    painter.drawText(sub_rect, Qt.AlignCenter, self._subtitle)
                else:
                    painter.drawText(self.rect(), Qt.AlignCenter, center_txt)
            else:
                # Center text - percentage (shifted slightly upward to align with 270-degree arc)
                y_offset = int(-size * 0.07)
                percent_rect = self.rect().translated(0, y_offset)
                
                painter.setPen(QColor("#ffffff"))
                percent_font = QFont("Orbitron", int(size * 0.13), QFont.Bold)
                painter.setFont(percent_font)
                percent_text = f"{int(self._value)}%"
                painter.drawText(percent_rect, Qt.AlignCenter, percent_text)
                
                # Subtitle below percentage
                if self._subtitle:
                    painter.setPen(QColor("#aaaaaa"))
                    sub_font = QFont("Orbitron", int(size * 0.052))
                    painter.setFont(sub_font)
                    sub_rect = percent_rect.translated(0, int(size * 0.13))
                    painter.drawText(sub_rect, Qt.AlignCenter, self._subtitle)
        
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class TimeAxisItem(pg.AxisItem):
    def __init__(self, filter_mode, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_mode = filter_mode

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            dt = datetime.fromtimestamp(v)
            if self.filter_mode == '24 Hours':
                strings.append(dt.strftime('%I %p'))
            elif self.filter_mode == '7 Days':
                strings.append(dt.strftime('%a %I%p'))
            else:
                strings.append(dt.strftime('%b %d'))
        return strings

class NetRateAxisItem(pg.AxisItem):
    """Custom Y-axis for network rate graphs to display human-readable byte rates."""
    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            if v <= 0:
                strings.append("0 B")
            elif v >= 1024 ** 2:
                strings.append(f"{v / (1024 ** 2):.1f} MB")
            elif v >= 1024:
                strings.append(f"{v / 1024:.0f} KB")
            else:
                strings.append(f"{int(v)} B")
        return strings

class NetworkDetailPanel(QWidget):
    """
    Expandable panel for per-process network history graph.
    
    Component Name: NetworkDetailPanel
    """
    def __init__(self, color_hex: str = "#FF5B06", parent=None):
        super().__init__(parent)
        self.setObjectName("netDetailPanel")
        # Start collapsed
        self.setMaximumHeight(0)
        
        # Styles
        self.setStyleSheet("""
            QWidget#netDetailPanel {
                background-color: rgba(30, 30, 35, 0.4);
                border-top: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
                margin-top: -4px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)
        
        left_axis = NetRateAxisItem(orientation='left')
        left_axis.setWidth(55)
        left_axis.setStyle(showValues=True)
        left_axis.setTextPen(pg.mkPen('#888888'))

        self.chart = pg.PlotWidget(axisItems={'left': left_axis})
        self.chart.setObjectName("netDetailChart")
        self.chart.setFixedHeight(100)
        self.chart.showGrid(x=False, y=True, alpha=0.15)
        self.chart.showAxis('left')
        self.chart.hideAxis('bottom')
        self.chart.setMouseEnabled(x=False, y=False)
        self.chart.setMenuEnabled(False)
        
        self.color_hex = color_hex
        self.color = QColor(color_hex)
        fill_color = QColor(self.color)
        fill_color.setAlpha(20)
        
        self.curve = self.chart.plot(pen=pg.mkPen(self.color, width=2), 
                                     brush=pg.mkBrush(fill_color),
                                     fillLevel=0)
        self.bar_item = None
        
        layout.addWidget(self.chart)
        
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_peak_title = QLabel("Peak:")
        self.lbl_peak_title.setStyleSheet("color: #888888; font-size: 10px; font-weight: 500; background: transparent;")
        self.lbl_peak_val = QLabel("0 B/s")
        self.lbl_peak_val.setStyleSheet("color: #ffffff; font-size: 12px; font-family: 'Orbitron'; font-weight: 700; background: transparent;")
        
        self.lbl_low_title = QLabel("Lowest:")
        self.lbl_low_title.setStyleSheet("color: #888888; font-size: 10px; font-weight: 500; background: transparent;")
        self.lbl_low_val = QLabel("0 B/s")
        self.lbl_low_val.setStyleSheet("color: #ffffff; font-size: 12px; font-family: 'Orbitron'; font-weight: 700; background: transparent;")
        
        stats_layout.addWidget(self.lbl_peak_title)
        stats_layout.addWidget(self.lbl_peak_val)
        stats_layout.addSpacing(15)
        stats_layout.addWidget(self.lbl_low_title)
        stats_layout.addWidget(self.lbl_low_val)
        stats_layout.addStretch()
        
        layout.addLayout(stats_layout)
        self._active_filter = "Total History"
        
    def _fmt_net_bytes(self, b):
        if b >= 1024 ** 2:
            return f"{b / (1024 ** 2):.1f} MB/s"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB/s"
        return f"{b} B/s"
        
    def set_data(self, history, explicit_filter=None, historical_points=None):
        if explicit_filter is not None:
            self._active_filter = explicit_filter
            
        if self._active_filter in ["Total History", "3 Hours"]:
            self.chart.hideAxis('bottom')
            if self.bar_item:
                self.chart.removeItem(self.bar_item)
                self.bar_item = None
                
            self.curve.show()
            if not history:
                return
                
            self.curve.setData(history)
            
            peak = max(history) if history else 0
            non_zero = [x for x in history if x > 0]
            lowest = min(non_zero) if non_zero else 0
            
            self.lbl_peak_val.setText(self._fmt_net_bytes(peak))
            self.lbl_low_val.setText(self._fmt_net_bytes(lowest))
            
            y_max = max(10240, peak * 1.15)
            self.chart.getPlotItem().setYRange(0, y_max, padding=0)
            
        else:
            if not historical_points:
                return
                
            self.curve.hide()
            if self.bar_item:
                self.chart.removeItem(self.bar_item)
                self.bar_item = None
                
            x_vals = [p['timestamp'] for p in historical_points]
            y_vals = [p['bytes'] for p in historical_points]
            
            # Only reconstruct the time axis when the filter actually changes.
            # Re-injecting a new TimeAxisItem into pyqtgraph on every tick is expensive;
            # the axis format is fully determined by the filter string alone.
            if not hasattr(self, '_last_axis_filter') or self._last_axis_filter != self._active_filter:
                time_axis = TimeAxisItem(filter_mode=self._active_filter, orientation='bottom')
                self.chart.setAxisItems({'bottom': time_axis})
                self.chart.showAxis('bottom')
                self._last_axis_filter = self._active_filter
            
            if len(x_vals) > 1:
                width = (x_vals[1] - x_vals[0]) * 0.8
            else:
                width = 3000

            self.bar_item = pg.BarGraphItem(x=x_vals, height=y_vals, width=width, brush=self.color_hex)
            self.chart.addItem(self.bar_item)
            
            peak = max(y_vals) if y_vals else 0
            non_zero = [x for x in y_vals if x > 0]
            lowest = min(non_zero) if non_zero else 0
            
            self.lbl_peak_val.setText(self._fmt_net_bytes(peak).replace('/s', ''))
            self.lbl_low_val.setText(self._fmt_net_bytes(lowest).replace('/s', ''))
            
            y_max = max(10240, peak * 1.15)
            self.chart.getPlotItem().setYRange(0, y_max, padding=0)

class StatsCard(QGroupBox):
    """
    Card widget for displaying stats with optional chart.
    
    Component Name: StatsCard
    """
    
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setObjectName("StatsCard")
        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 12)
        layout.setSpacing(8)
        
        # Content area (for chart or stats)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("statsCardContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content_widget, stretch=1)
    
    def _apply_style(self):
        # Apply style matching HELXAIR/HELXAIRO groupbox style
        self.setProperty("class", "statsCard")
        self.setStyleSheet("""
            QGroupBox[class="statsCard"], QGroupBox#StatsCard, QGroupBox#cpuUsageCard, QGroupBox#ramUsageCard, QGroupBox#networkUsageCard, QGroupBox#diskHealthCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox[class="statsCard"]:hover, QGroupBox#StatsCard:hover, QGroupBox#cpuUsageCard:hover, QGroupBox#ramUsageCard:hover, QGroupBox#networkUsageCard:hover, QGroupBox#diskHealthCard:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            }
        """)
    
    def addWidget(self, widget):
        self.content_layout.addWidget(widget)


class ProgressBarWidget(QWidget):
    """
    Custom styled progress bar with left percent and right info text.
    
    Component Name: ProgressBarWidget
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProgressBarWidget")
        self._value = 0
        self._max_value = 100
        self._label = ""
        self._right_label = ""  # For GB info on right side
        self._show_percent = True
        self.setFixedHeight(24)
    
    def setValue(self, value: float):
        self._value = max(0, min(self._max_value, value))
        self.update()
    
    def setLabel(self, label: str):
        self._label = label
        self.update()
    
    def setRightLabel(self, label: str):
        """Set text to display on the right side (e.g., '150 GB / 500 GB')."""
        self._right_label = label
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        bg_rect = self.rect()
        text_rect = bg_rect.adjusted(8, 0, -8, 0)
        font = QFont("Orbitron", 10)
        painter.setFont(font)
        
        left_text = self._label
        if self._show_percent:
            left_text = f"{left_text}  {int(self._value)}%" if left_text else f"{int(self._value)}%"
        
        # 1. Background track (#2a2a2a)
        painter.setBrush(QColor("#2a2a2a"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 6, 6)
        
        # 2. PASS 1: Render light text for the unfilled/dark area
        painter.setPen(QColor("#e0e0e0"))
        if left_text:
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, left_text)
        if self._right_label:
            painter.setPen(QColor("#cccccc"))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignRight, self._right_label)
            
        # 3. PASS 2: Progress Fill & Inverted Dark Text for the filled area
        if self._value > 0:
            progress_width = int((self._value / self._max_value) * self.width())
            if progress_width > 0:
                progress_rect = bg_rect.adjusted(0, 0, -(self.width() - progress_width), 0)
                
                # Gradient Fill (#FF5B06 -> #FDA903)
                gradient = QLinearGradient(0, 0, progress_width, 0)
                gradient.setColorAt(0, QColor("#FF5B06"))
                gradient.setColorAt(1, QColor("#FDA903"))
                painter.setBrush(gradient)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(progress_rect, 6, 6)
                
                # Clip drawing strictly to filled progress rectangle
                painter.setClipRect(progress_rect)
                
                # Draw inverted dark text on top of orange progress fill
                painter.setPen(QColor("#0a0a0a"))
                if left_text:
                    painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, left_text)
                if self._right_label:
                    painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignRight, self._right_label)
        
        painter.end()


_DRIVE_ICON_CACHE = {}
_DRIVE_PIXMAP_CACHE = {}


def _get_cached_drive_icon(path: str) -> QIcon:
    if path not in _DRIVE_ICON_CACHE:
        if os.path.exists(path):
            _DRIVE_ICON_CACHE[path] = QIcon(path)
        else:
            _DRIVE_ICON_CACHE[path] = QIcon()
    return _DRIVE_ICON_CACHE[path]


def _get_cached_drive_pixmap(path: str, width: int = None, height: int = None) -> QPixmap:
    key = (path, width, height)
    if key not in _DRIVE_PIXMAP_CACHE:
        if os.path.exists(path):
            pix = QPixmap(path)
            if width and height:
                pix = pix.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _DRIVE_PIXMAP_CACHE[key] = pix
        else:
            _DRIVE_PIXMAP_CACHE[key] = QPixmap()
    return _DRIVE_PIXMAP_CACHE[key]


class DriveScanWorker(QThread):
    """
    Async junk scanner for Drive page.

    Component Name: DriveScanWorker
    """
    scan_completed = Signal(dict)
    scan_progress = Signal(str, int)

    def run(self):
        try:
            from utils.drive_utils import scan_junk_categories
            results = scan_junk_categories(progress_callback=self.scan_progress.emit)
            self.scan_completed.emit(results)
        except Exception as e:
            self.scan_progress.emit(f"Scan failed: {e}", 100)
            self.scan_completed.emit({})


class DiskCleanWorker(QThread):
    """
    Async disk cleaner for Drive page.

    Component Name: DiskCleanWorker
    """
    clean_completed = Signal(int, int, object)
    clean_progress = Signal(str, int)

    def __init__(self, selected_categories, parent=None):
        super().__init__(parent)
        self.selected_categories = list(selected_categories)

    def run(self):
        try:
            from utils.drive_utils import clean_junk_categories
            cleaned, skipped, errors = clean_junk_categories(
                self.selected_categories,
                progress_callback=self.clean_progress.emit,
            )
            self.clean_completed.emit(int(cleaned), int(skipped), errors)
        except Exception as e:
            self.clean_progress.emit(f"Clean failed: {e}", 100)
            self.clean_completed.emit(0, 0, [str(e)])


class DriveInfoWorker(QThread):
    """
    Async hardware & SMART drive info fetcher for HELXTATS Drive page.
    Prevents blocking the UI thread with COM WMI queries.

    Component Name: DriveInfoWorker
    """
    data_ready = Signal(list, dict, list, list)

    def run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                from utils.drive_utils import (
                    get_drive_partitions_info,
                    get_drive_hardware_info,
                    get_physical_disks_info,
                )
                from hardware_wrapper import get_monitor
                partitions = get_drive_partitions_info()
                hardware = get_drive_hardware_info(partitions=partitions)
                physical_disks = get_physical_disks_info(partitions=partitions)
                monitor = get_monitor()
                smart_disks = monitor.get_smart_disks() if monitor else []
                self.data_ready.emit(partitions, hardware, physical_disks, smart_disks)
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            print(f"[DriveInfoWorker] Error querying drive info: {e}")


class DriveSplitterHandle(QSplitterHandle):
    """
    Custom vertical splitter handle rendering resize-handle-vertical-white.svg vector icon.
    Component Name: DriveSplitterHandle
    """
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setObjectName("DriveSplitterHandle")
        self.setCursor(Qt.SplitVCursor)
        self._is_pressed = False
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        svg_path = os.path.join(script_dir, "UI Icons", "resize-handle-vertical-white.svg")
        self._svg_renderer = None
        if os.path.exists(svg_path):
            self._svg_renderer = QSvgRenderer(svg_path)

    def mousePressEvent(self, event):
        self._is_pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_pressed = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        active = self.underMouse() or self._is_pressed
        
        # 1. Subtle horizontal track line across full width
        line_height = 2 if not active else 4
        line_y = rect.center().y() - line_height // 2
        line_rect = QRect(rect.x() + 10, line_y, rect.width() - 20, line_height)
        
        line_color = QColor(255, 91, 6, 220) if active else QColor(255, 255, 255, 30)
        painter.fillRect(line_rect, line_color)
        
        # 2. Centered White 90-degree rotated SVG resize handle icon pill
        center_x = rect.center().x()
        center_y = rect.center().y()
        
        pill_w = 52
        pill_h = 22
        pill_rect = QRect(center_x - pill_w // 2, center_y - pill_h // 2, pill_w, pill_h)
        
        # Pill background
        pill_bg = QColor(255, 91, 6) if active else QColor(28, 28, 35)
        painter.setBrush(QBrush(pill_bg))
        border_pen = QPen(QColor(255, 91, 6) if active else QColor(255, 255, 255, 50), 1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(pill_rect, 11, 11)
        
        # 3. Render SVG Icon
        if self._svg_renderer and self._svg_renderer.isValid():
            icon_size = 20
            icon_rect = QRect(center_x - icon_size // 2, center_y - icon_size // 2, icon_size, icon_size)
            self._svg_renderer.render(painter, icon_rect)


class DrivePageSplitter(QSplitter):
    """
    Custom vertical QSplitter for Drive page using DriveSplitterHandle.
    Component Name: DrivePageSplitter
    """
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setObjectName("DrivePageSplitter")

    def createHandle(self):
        return DriveSplitterHandle(self.orientation(), self)


_DRIVE_ARROW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
_DRIVE_OVERVIEW_COMBO_STYLESHEET = """
    QComboBox#driveOverviewSelector {
        background: rgba(255, 255, 255, 0.08);
        color: #e0e0e0;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 6px;
        padding-left: 10px;
        padding-right: 26px;
        font-family: 'Orbitron', sans-serif;
        font-size: 10px;
        font-weight: 700;
    }
    QComboBox#driveOverviewSelector:hover {
        background: rgba(255, 255, 255, 0.14);
        border-color: rgba(255, 255, 255, 0.25);
        color: #ffffff;
    }
    QComboBox#driveOverviewSelector::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border: none;
        background: transparent;
    }
    QComboBox#driveOverviewSelector::down-arrow {
        subcontrol-origin: content;
        subcontrol-position: center;
        image: url("%s");
        width: 10px;
        height: 10px;
    }
    QComboBox#driveOverviewSelector QAbstractItemView {
        background: rgba(18, 20, 26, 0.95);
        color: #e0e0e0;
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 6px;
        padding: 4px;
        outline: 0px;
        font-family: 'Orbitron', sans-serif;
        font-size: 10px;
    }
    QComboBox#driveOverviewSelector QAbstractItemView::item {
        min-height: 24px;
        padding: 4px 8px;
        background: transparent;
        color: #e0e0e0;
        border-radius: 4px;
    }
    QComboBox#driveOverviewSelector QAbstractItemView::item:hover,
    QComboBox#driveOverviewSelector QAbstractItemView::item:selected {
        background-color: rgba(255, 255, 255, 0.12);
        color: #ffffff;
    }
""" % _DRIVE_ARROW_PATH


class DriveOverviewWidget(QWidget):
    """
    Storage hero summary for HELXTATS Drive page with physical drive selector dropdown.

    Component Name: DriveOverviewWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DriveOverviewWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#DriveOverviewWidget {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QWidget#DriveOverviewWidget:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)

        self._latest_partitions = []
        self._latest_hardware = {}
        self._latest_disk_io = {}
        self._latest_physical_disks = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)

        cap_col = QVBoxLayout()
        cap_col.setSpacing(6)
        cap_col.setAlignment(Qt.AlignTop)

        self.combo_drive_selector = QComboBox()
        self.combo_drive_selector.setObjectName("driveOverviewSelector")
        self.combo_drive_selector.setFixedHeight(24)
        self.combo_drive_selector.setCursor(Qt.PointingHandCursor)
        self.combo_drive_selector.setStyleSheet(_DRIVE_OVERVIEW_COMBO_STYLESHEET)
        self.combo_drive_selector.addItem("TOTAL STORAGE")
        self.combo_drive_selector.currentIndexChanged.connect(self._on_selector_changed)

        self.lbl_disk_type = QLabel("STORAGE")
        self.lbl_disk_type.setObjectName("driveDiskTypeLabel")
        self.lbl_disk_type.setStyleSheet("color: #888888; font-size: 9px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")

        self.lbl_total_capacity = QLabel("0 B / 0 B")
        self.lbl_total_capacity.setObjectName("driveTotalCapacity")
        self.lbl_total_capacity.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        cap_col.addWidget(self.combo_drive_selector, alignment=Qt.AlignLeft)
        cap_col.addWidget(self.lbl_disk_type)
        cap_col.addWidget(self.lbl_total_capacity)
        layout.addLayout(cap_col)

        layout.addStretch(1)

        bottom_col = QVBoxLayout()
        bottom_col.setSpacing(8)

        self.lbl_health_title = QLabel("SMART HEALTH")
        self.lbl_health_title.setObjectName("driveHealthScoreTitle")
        self.lbl_health_title.setStyleSheet("color: #888888; font-size: 9px; font-weight: 700; background: transparent;")
        self.lbl_health_score = QLabel("HEALTH UNKNOWN")
        self.lbl_health_score.setObjectName("driveHealthScore")
        self.lbl_health_score.setStyleSheet("color: #FFCC00; font-size: 14px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")

        health_col = QVBoxLayout()
        health_col.setSpacing(2)
        health_col.addWidget(self.lbl_health_title)
        health_col.addWidget(self.lbl_health_score)
        bottom_col.addLayout(health_col)

        self.lbl_io_title = QLabel("LIVE I/O")
        self.lbl_io_title.setObjectName("driveLiveIoTitle")
        self.lbl_io_title.setStyleSheet("color: #888888; font-size: 9px; font-weight: 700; background: transparent;")
        self.lbl_live_io = QLabel("R: 0.0 MB/s | W: 0.0 MB/s")
        self.lbl_live_io.setObjectName("driveLiveIo")
        self.lbl_live_io.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")

        io_col = QVBoxLayout()
        io_col.setSpacing(2)
        io_col.addWidget(self.lbl_io_title)
        io_col.addWidget(self.lbl_live_io)
        bottom_col.addLayout(io_col)

        layout.addLayout(bottom_col)

    def _on_selector_changed(self, index):
        self._update_display()

    def set_data(self, partitions, hardware, disk_io, physical_disks=None):
        from utils.drive_utils import format_bytes
        self._latest_partitions = partitions or []
        self._latest_hardware = hardware or {}
        self._latest_disk_io = disk_io or {}

        if physical_disks is not None:
            self._latest_physical_disks = physical_disks
            new_labels = ["TOTAL STORAGE"] + [
                ((d.get('model') or f"Disk {d.get('index', 0)}") if len(d.get('model') or '') <= 24 else (d.get('model') or '')[:21] + "...")
                for d in physical_disks
            ]
            current_labels = [self.combo_drive_selector.itemText(i) for i in range(self.combo_drive_selector.count())]
            if new_labels != current_labels:
                self.combo_drive_selector.blockSignals(True)
                curr_idx = self.combo_drive_selector.currentIndex()
                self.combo_drive_selector.clear()
                for i, d_label in enumerate(new_labels):
                    self.combo_drive_selector.addItem(d_label)
                    if i > 0:
                        d = physical_disks[i - 1]
                        self.combo_drive_selector.setItemData(i, d.get('model', ''), Qt.ToolTipRole)
                if curr_idx < self.combo_drive_selector.count():
                    self.combo_drive_selector.setCurrentIndex(curr_idx)
                self.combo_drive_selector.blockSignals(False)

        self._update_display()

    def _update_display(self):
        from utils.drive_utils import format_bytes
        idx = self.combo_drive_selector.currentIndex()

        if idx <= 0 or not self._latest_physical_disks or idx > len(self._latest_physical_disks):
            # Aggregated Total Storage View — hide SMART HEALTH and LIVE I/O
            self.lbl_health_title.setVisible(False)
            self.lbl_health_score.setVisible(False)
            self.lbl_io_title.setVisible(False)
            self.lbl_live_io.setVisible(False)

            media_types = set()
            for d in self._latest_physical_disks:
                if d.get("media_type"):
                    media_types.add(d["media_type"].upper())
            if not media_types:
                type_str = "SYSTEM STORAGE"
            elif len(media_types) == 1:
                type_str = f"{next(iter(media_types))} STORAGE"
            else:
                type_str = "HYBRID STORAGE"
            self.lbl_disk_type.setText(type_str)

            total = sum(int(p.get("total_bytes", 0)) for p in self._latest_partitions)
            used = sum(int(p.get("used_bytes", 0)) for p in self._latest_partitions)
            self.lbl_total_capacity.setText(f"{format_bytes(used)} / {format_bytes(total)}")
        else:
            # Selected Physical Drive View — show SMART HEALTH and LIVE I/O
            self.lbl_health_title.setVisible(True)
            self.lbl_health_score.setVisible(True)
            self.lbl_io_title.setVisible(True)
            self.lbl_live_io.setVisible(True)

            target_disk = self._latest_physical_disks[idx - 1]
            logicals = target_disk.get("logicals", [])

            mtype = str(target_disk.get("media_type", "DISK")).upper()
            self.lbl_disk_type.setText(mtype)

            matching_partitions = [
                p for p in self._latest_partitions
                if (p.get("drive") in logicals or p.get("letter") in [l.rstrip("\\") for l in logicals])
            ]

            used = sum(int(p.get("used_bytes", 0)) for p in matching_partitions)
            total = target_disk.get("size_bytes", 0)
            if total <= 0:
                total = sum(int(p.get("total_bytes", 0)) for p in matching_partitions)

            self.lbl_total_capacity.setText(f"{format_bytes(used)} / {format_bytes(total)}")

            smart_status = str(target_disk.get("smart_status", "OK")).upper()
            health_text = target_disk.get("health_text", "")
            health_pct = target_disk.get("health_pct", 100)
            temp_c = int(target_disk.get("temp_c", 0) or 0)

            if health_pct >= 90 and "CRITICAL" not in smart_status and "WARN" not in smart_status:
                color = "#00FF66"
            elif health_pct >= 60 and "CRITICAL" not in smart_status:
                color = "#FFCC00"
            else:
                color = "#FF3355"

            display_health = f"{health_text} | {temp_c}°C" if temp_c > 0 else health_text
            self.lbl_health_score.setText(display_health)
            self.lbl_health_score.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")

            read_speed = float(self._latest_disk_io.get("read_mbps", 0) or 0)
            write_speed = float(self._latest_disk_io.get("write_mbps", 0) or 0)
            self.lbl_live_io.setText(f"R: {read_speed:.1f} MB/s | W: {write_speed:.1f} MB/s")


class DriveVolumeCard(QWidget):
    """
    Per-volume storage card for HELXTATS Drive page.

    Component Name: DriveVolumeCard
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DriveVolumeCard")
        self.setStyleSheet("""
            QWidget#DriveVolumeCard {
                background-color: rgba(35, 35, 42, 0.5);
                border-radius: 6px;
            }
            QWidget#DriveVolumeCard:hover {
                background-color: rgba(45, 45, 52, 0.8);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.title_label = QLabel("(C:) Local Disk")
        self.title_label.setObjectName("driveVolumeTitle")
        self.title_label.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: 800; background: transparent;")
        top.addWidget(self.title_label)

        self.type_badge = QLabel("Storage")
        self.type_badge.setObjectName("driveVolumeTypeBadge")
        self.type_badge.setStyleSheet("color: #00E5FF; background-color: rgba(0, 229, 255, 0.14); border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800;")
        top.addWidget(self.type_badge)
        top.addStretch()
        layout.addLayout(top)

        self.usage_bar = ProgressBarWidget()
        self.usage_bar.setObjectName("driveUsageBar")
        layout.addWidget(self.usage_bar)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.fs_label = QLabel("FS: Unknown")
        self.fs_label.setObjectName("driveVolumeFsLabel")
        self.cluster_label = QLabel("Cluster: Unknown")
        self.cluster_label.setObjectName("driveVolumeClusterLabel")
        self.free_label = QLabel("Free: 0 B")
        self.free_label.setObjectName("driveVolumeFreeLabel")
        for label in (self.fs_label, self.cluster_label, self.free_label):
            label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
            bottom.addWidget(label)
        bottom.addStretch()
        layout.addLayout(bottom)

    def set_data(self, partition, hardware_info=None):
        from utils.drive_utils import format_bytes
        hardware_info = hardware_info or {}
        letter = partition.get("letter") or partition.get("drive", "").rstrip("\\/")
        label = partition.get("label") or "Local Disk"
        self.title_label.setText(f"({letter}) {label}")

        media_type = hardware_info.get("media_type") or partition.get("drive_type") or "Storage"
        model = hardware_info.get("model") or "Unknown model"
        self.type_badge.setText(str(media_type))
        self.type_badge.setToolTip(model)

        percent = float(partition.get("percent_used", 0) or 0)
        used = int(partition.get("used_bytes", 0) or 0)
        total = int(partition.get("total_bytes", 0) or 0)
        free = int(partition.get("free_bytes", 0) or 0)
        self.usage_bar.setValue(percent)
        self.usage_bar.setLabel(letter)
        self.usage_bar.setRightLabel(f"{format_bytes(used)} / {format_bytes(total)}")

        cluster = int(partition.get("cluster_size", 0) or 0)
        self.fs_label.setText(f"FS: {partition.get('filesystem') or 'Unknown'}")
        self.cluster_label.setText(f"Cluster: {format_bytes(cluster) if cluster else 'Unknown'}")
        self.free_label.setText(f"Free: {format_bytes(free)}")


class JunkItemsFloatingPanel(QDialog):
    """
    Floating panel displaying individual junk paths matching the HELXTATS dark theme.

    Component Name: JunkItemsFloatingPanel
    """
    def __init__(self, title="ITEMS", paths=None, parent=None):
        super().__init__(parent)
        self.setObjectName("JunkItemsFloatingPanel")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(620, 380)
        self._drag_pos = None

        container = QFrame(self)
        container.setObjectName("junkItemsContainer")
        container.setStyleSheet("""
            QFrame#junkItemsContainer {
                background-color: #141414;
                border: none;
                border-radius: 8px;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Header bar matching reference image with orange gradient
        header_bar = QWidget()
        header_bar.setObjectName("junkItemsHeaderBar")
        header_bar.setFixedHeight(38)
        header_bar.setStyleSheet("""
            QWidget#junkItemsHeaderBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                border-bottom: none;
            }
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(12, 0, 10, 0)
        header_layout.setSpacing(8)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        tag_icon_path = os.path.join(script_dir, "UI Icons", "tag-icon.svg")
        close_icon_path = os.path.join(script_dir, "UI Icons", "close-icon.svg")

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setScaledContents(True)
        if os.path.exists(tag_icon_path):
            icon_lbl.setPixmap(QPixmap(tag_icon_path))
        header_layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)

        title_lbl = QLabel(str(title).upper())
        title_lbl.setObjectName("junkItemsHeaderTitle")
        title_lbl.setStyleSheet("color: #ffffff; font-family: 'Orbitron'; font-size: 12px; font-weight: 800; background: transparent;")
        header_layout.addWidget(title_lbl, stretch=1, alignment=Qt.AlignVCenter)

        btn_close = QPushButton()
        btn_close.setObjectName("junkItemsCloseBtn")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        if os.path.exists(close_icon_path):
            btn_close.setIcon(QIcon(close_icon_path))
            btn_close.setIconSize(QSize(14, 14))
        btn_close.setStyleSheet("""
            QPushButton#junkItemsCloseBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#junkItemsCloseBtn:hover {
                background: rgba(0, 0, 0, 0.25);
                border-radius: 4px;
            }
        """)
        btn_close.clicked.connect(self.accept)
        header_layout.addWidget(btn_close, alignment=Qt.AlignVCenter)

        container_layout.addWidget(header_bar)

        # High-performance virtualized list widget (handles 100,000+ items instantly without freezing)
        list_widget = QListWidget()
        list_widget.setObjectName("junkItemsListWidget")
        list_widget.setSelectionMode(QListWidget.SingleSelection)
        list_widget.setStyleSheet("""
            QListWidget#junkItemsListWidget {
                background: transparent;
                border: none;
                outline: none;
                font-family: 'Orbitron', monospace;
                font-size: 11px;
                color: #e0e0e0;
                padding: 6px;
            }
            QListWidget#junkItemsListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget#junkItemsListWidget::item:hover {
                background: rgba(255, 91, 6, 0.18);
                color: #ffffff;
            }
            QListWidget#junkItemsListWidget::item:selected {
                background: rgba(255, 91, 6, 0.3);
                color: #ffffff;
            }
            QScrollBar:vertical { background: #181818; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #3a3a3a; min-height: 20px; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #FF5B06; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        paths_list = [str(p) for p in paths] if paths else []
        if not paths_list:
            item = QListWidgetItem("No junk file paths scanned or found for this category.")
            item.setFlags(Qt.NoItemFlags)
            list_widget.addItem(item)
        else:
            list_widget.addItems(paths_list)

        def _on_item_clicked(item):
            path_str = item.text()
            if not path_str or "No junk file paths" in path_str:
                return
            try:
                import os, subprocess, threading
                def _launch():
                    target = os.path.abspath(path_str)
                    if os.path.isfile(target):
                        subprocess.Popen(f'explorer.exe /select,"{target}"')
                    elif os.path.exists(target):
                        subprocess.Popen(f'explorer.exe "{target}"')
                    else:
                        parent_dir = os.path.dirname(target)
                        if os.path.exists(parent_dir):
                            subprocess.Popen(f'explorer.exe "{parent_dir}"')
                threading.Thread(target=_launch, daemon=True).start()
            except Exception as err:
                print(f"[JunkPaths] Error opening path: {err}")

        list_widget.itemClicked.connect(_on_item_clicked)
        container_layout.addWidget(list_widget, stretch=1)

        if paths_list:
            footer_lbl = QLabel(f"Total Items: {len(paths_list)}")
            footer_lbl.setObjectName("junkItemsFooterLabel")
            footer_lbl.setStyleSheet("color: #777777; font-family: 'Orbitron'; font-size: 10px; padding: 4px 12px 8px 12px; background: transparent;")
            container_layout.addWidget(footer_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()


class DiskCleanerPanel(QWidget):
    """
    Tiered disk cleaner control panel with Hero Scan Panel and Category List.

    Component Name: DiskCleanerPanel
    """
    scan_requested = Signal()
    clean_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiskCleanerPanel")
        self._category_rows = {}
        self._is_scanned = False
        self._is_scanning_active = False
        self._scan_dot_step = 0
        self._scan_dot_timer = QTimer(self)
        self._scan_dot_timer.timeout.connect(self._animate_scan_dots)
        self._hero_gradient_offset = 0.0
        self._hero_gradient_timer = QTimer(self)
        self._hero_gradient_timer.setInterval(100)
        self._hero_gradient_timer.timeout.connect(self._update_hero_gradient)
        self.setStyleSheet("QWidget#DiskCleanerPanel { background: transparent; }")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # === LEFT PANEL: HERO SCAN PANEL (Booster-style with CircularGauge) ===
        self.hero_panel = QWidget()
        self.hero_panel.setObjectName("DriveScanHeroWidget")
        self.hero_panel.setFixedWidth(240)
        self.hero_panel.setStyleSheet("""
            QWidget#DriveScanHeroWidget {
                background: transparent;
                border: none;
            }
        """)
        hero_layout = QVBoxLayout(self.hero_panel)
        hero_layout.setContentsMargins(14, 16, 14, 16)
        hero_layout.setSpacing(10)

        hero_title = QLabel("DISK CLEANER")
        hero_title.setObjectName("driveCleanerHeroTitle")
        hero_title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        hero_title.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(hero_title)

        # Circular Gauge Widget (reused from top of HardwarePanelWidget)
        self.hero_gauge = CircularGauge()
        self.hero_gauge.setObjectName("driveCleanerHeroGauge")
        self.hero_gauge.setFixedSize(180, 180)
        self.hero_gauge.setShowText(True)
        self.hero_gauge.setCenterText("SCAN")
        self.hero_gauge.setAnimated(False)
        self.hero_gauge.setSubtitle("Ready to Scan")
        self.hero_gauge.setAccentColor(QColor("#FF5B06"))
        hero_layout.addWidget(self.hero_gauge, 0, Qt.AlignCenter)
        self.hero_gauge.setCursor(Qt.PointingHandCursor)
        self.hero_gauge.clicked.connect(self._on_hero_action_clicked)
        
        self.hero_status_lbl = QLabel("Tier 1 selected by default")
        self.hero_status_lbl.setObjectName("driveCleanerHeroStatus")
        self.hero_status_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; background: transparent; font-family: 'Orbitron'; font-weight: 500;")
        self.hero_status_lbl.setAlignment(Qt.AlignCenter)
        self.hero_status_lbl.setWordWrap(True)
        hero_layout.addWidget(self.hero_status_lbl)

        self.btn_back_scan = QPushButton("BACK TO SCAN")
        self.btn_back_scan.setObjectName("driveBackScanButton")
        self.btn_back_scan.setFixedHeight(50)
        self.btn_back_scan.setCursor(Qt.PointingHandCursor)
        self.btn_back_scan.setStyleSheet("""
            QPushButton#driveBackScanButton {
                background: transparent;
                color: #888888;
                border: 1px solid #444;
                border-radius: 6px;
                height: 50px;
                min-height: 50px;
                max-height: 50px;
                padding: 0px;
                margin: 0px;
                font-size: 11px;
                font-weight: 700;
                font-family: 'Orbitron';
            }
            QPushButton#driveBackScanButton:hover {
                background: rgba(255, 255, 255, 0.05);
                color: #cccccc;
                border-color: #666;
            }
            QPushButton#driveBackScanButton:disabled {
                color: #444444;
                border-color: #333333;
                background: transparent;
            }
        """)
        self.btn_back_scan.clicked.connect(self._on_back_scan_clicked)
        self.btn_back_scan.setEnabled(False)
        hero_layout.addWidget(self.btn_back_scan)
        
        hero_layout.addStretch()
        main_layout.addWidget(self.hero_panel, stretch=0)

        # === RIGHT PANEL: CLEANUP CATEGORIES LIST ===
        self.category_panel = QWidget()
        self.category_panel.setObjectName("DriveCleanerCategoryPanel")
        self.category_panel.setStyleSheet("""
            QWidget#DriveCleanerCategoryPanel {
                background: transparent;
                border: none;
            }
        """)
        cat_panel_layout = QVBoxLayout(self.category_panel)
        cat_panel_layout.setContentsMargins(0, 0, 0, 0)
        cat_panel_layout.setSpacing(0)

        # Sub-tab bar (Booster tab style: Essential, System, Advanced, All Junk)
        tab_bar = QWidget()
        tab_bar.setObjectName("driveCleanerTabBar")
        tab_bar.setFixedHeight(40)
        tab_bar.setStyleSheet("""
            QWidget#driveCleanerTabBar {
                background: rgba(26, 26, 26, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """)
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(6, 5, 6, 5)
        tab_bar_layout.setSpacing(6)

        tab_names = ["System clean-up", "System tweaks", "Disk defragment"]
        self._cleaner_tab_btns = []
        self._current_cleaner_tab = 0

        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setObjectName(f"driveCleanerTabBtn_{i}")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"Open {name}")
            btn.clicked.connect(lambda checked, idx=i: self._switch_cleaner_tab(idx))
            self._cleaner_tab_btns.append(btn)
            tab_bar_layout.addWidget(btn)

        tab_bar_layout.addStretch()
        cat_panel_layout.addWidget(tab_bar)

        # QStackedWidget for 3 Sub-Tabs (Item Container with Booster-style background & border)
        self.cleaner_stack = QStackedWidget()
        self.cleaner_stack.setObjectName("driveCleanerStack")
        self.cleaner_stack.setAttribute(Qt.WA_StyledBackground, True)
        self.cleaner_stack.setStyleSheet("""
            QStackedWidget#driveCleanerStack {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top: none;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
        """)

        # Page 0: System clean-up (Disk Cleaner Scroll Area)
        scroll = SmoothScrollArea()
        scroll.setObjectName("DriveCleanerScroll")
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1e1e1e; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.category_container = QWidget()
        self.category_container.setObjectName("driveCleanerCategoryContainer")
        self.category_container.setStyleSheet("background: transparent;")
        self.category_layout = QVBoxLayout(self.category_container)
        self.category_layout.setContentsMargins(10, 10, 10, 10)
        self.category_layout.setSpacing(6)

        scroll.setWidget(self.category_container)

        # Empty State View (shown before user scans)
        self.empty_state_page = QWidget()
        self.empty_state_page.setObjectName("driveCleanerEmptyStatePage")
        empty_layout = QVBoxLayout(self.empty_state_page)
        empty_layout.setContentsMargins(20, 30, 20, 30)
        empty_layout.setSpacing(12)
        empty_layout.setAlignment(Qt.AlignCenter)

        self.empty_gauge = CircularGauge()
        self.empty_gauge.setObjectName("driveCleanerEmptyGauge")
        self.empty_gauge.setFixedSize(140, 140)
        self.empty_gauge.setShowText(True)
        self.empty_gauge.setCenterText("SCAN")
        self.empty_gauge.setAnimated(False)
        self.empty_gauge.setGrayscale(True)
        empty_layout.addWidget(self.empty_gauge, 0, Qt.AlignCenter)

        empty_title = QLabel("It's a little empty here.")
        empty_title.setObjectName("driveEmptyTitle")
        empty_title.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_subtitle = QLabel("Click SCAN to see more.")
        empty_subtitle.setObjectName("driveEmptySubtitle")
        empty_subtitle.setStyleSheet("color: #888888; font-size: 12px; font-weight: 500; font-family: 'Orbitron'; background: transparent;")
        empty_subtitle.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_subtitle)

        # View Stack for System clean-up page (Index 0: Empty State, Index 1: Category Table)
        self.cleanup_view_stack = QStackedWidget()
        self.cleanup_view_stack.setObjectName("driveCleanupViewStack")
        self.cleanup_view_stack.addWidget(self.empty_state_page)
        self.cleanup_view_stack.addWidget(scroll)

        self.cleaner_stack.addWidget(self.cleanup_view_stack)

        # Page 1: System tweaks (Placeholder for future tweaks)
        tweaks_page = QWidget()
        tweaks_page.setObjectName("driveSystemTweaksPage")
        tweaks_layout = QVBoxLayout(tweaks_page)
        tweaks_lbl = QLabel("System Tweaks coming soon...")
        tweaks_lbl.setObjectName("driveSystemTweaksLabel")
        tweaks_lbl.setStyleSheet("color: #888888; font-size: 13px; font-family: 'Orbitron'; background: transparent;")
        tweaks_lbl.setAlignment(Qt.AlignCenter)
        tweaks_layout.addWidget(tweaks_lbl)
        self.cleaner_stack.addWidget(tweaks_page)

        # Page 2: Disk defragment (Placeholder for future defrag tool)
        defrag_page = QWidget()
        defrag_page.setObjectName("driveDefragPage")
        defrag_layout = QVBoxLayout(defrag_page)
        defrag_lbl = QLabel("Disk Defragmentation coming soon...")
        defrag_lbl.setObjectName("driveDefragLabel")
        defrag_lbl.setStyleSheet("color: #888888; font-size: 13px; font-family: 'Orbitron'; background: transparent;")
        defrag_lbl.setAlignment(Qt.AlignCenter)
        defrag_layout.addWidget(defrag_lbl)
        self.cleaner_stack.addWidget(defrag_page)

        cat_panel_layout.addWidget(self.cleaner_stack, stretch=1)

        self._categories_built = False
        self._switch_cleaner_tab(0)

        # Deferred background warm-up: builds 51 rows on idle tick for instant <15ms tab switch
        QTimer.singleShot(100, self._ensure_categories_built)

        cat_panel_layout.addSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("driveCleanerProgress")
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: rgba(60, 60, 60, 0.5); border: none; border-radius: 3px; }
            QProgressBar::chunk { background: #FF5B06; border-radius: 3px; }
        """)
        cat_panel_layout.addWidget(self.progress_bar)

        # Bottom Bar with Status Label & RESET TO DEFAULT button (matching essentialBottom in Booster tab)
        bottom_bar = QFrame()
        bottom_bar.setObjectName("driveCleanerBottomBar")
        bottom_bar.setFixedHeight(58)
        bottom_bar.setStyleSheet("""
            QFrame#driveCleanerBottomBar {
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(15, 8, 15, 8)
        bottom_layout.setSpacing(10)

        self.status_label = QLabel("Tier 1 selected by default. Review before cleaning.")
        self.status_label.setObjectName("driveCleanerStatusLabel")
        self.status_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent; font-family: 'Orbitron';")
        self.status_label.setWordWrap(True)
        bottom_layout.addWidget(self.status_label, stretch=1, alignment=Qt.AlignVCenter)

        self.btn_reset = QPushButton("RESET TO DEFAULT")
        self.btn_reset.setObjectName("driveCleanerResetBtn")
        self.btn_reset.setFixedSize(180, 35)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setToolTip("Reset all selections to default tier configuration")
        self.btn_reset.setStyleSheet("""
            QPushButton#driveCleanerResetBtn {
                background: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                height: 30px;
                min-height: 30px;
                max-height: 30px;
                padding: 0px;
                margin: 0px;
                text-align: center;
                font-family: 'Orbitron';
                font-size: 9px;
                font-weight: 600;
            }
            QPushButton#driveCleanerResetBtn:hover {
                background: #444;
                border-color: #FF5B06;
                color: #ffffff;
            }
            QPushButton#driveCleanerResetBtn:pressed {
                background: #2a2a2a;
            }
        """)
        self.btn_reset.clicked.connect(self._reset_cleanup_selections)
        bottom_layout.addWidget(self.btn_reset, alignment=Qt.AlignVCenter)

        cat_panel_layout.addWidget(bottom_bar)

        main_layout.addWidget(self.category_panel, stretch=6)

    def _ensure_categories_built(self):
        """Ensure category rows are built (lazy / deferred on-demand)."""
        if getattr(self, '_categories_built', False):
            return
        self._build_categories()

    def _reset_cleanup_selections(self):
        """Reset all category row checkboxes to their default configuration."""
        self._ensure_categories_built()
        from utils.drive_utils import JUNK_CATEGORIES
        default_map = {c.id: c.default for c in JUNK_CATEGORIES}

        for cat_id, row_data in self._category_rows.items():
            check = row_data.get("check")
            if check and check.isEnabled():
                cat_def = row_data.get("cat_default", default_map.get(cat_id, False))
                check.blockSignals(True)
                check.setChecked(bool(cat_def))
                check.blockSignals(False)

        # Also reset group / subgroup checkboxes to match
        if hasattr(self, '_subgroup_rows'):
            for sgid, subgrp in self._subgroup_rows.items():
                child_rows = [r for r in self._category_rows.values() if r.get("subgroup_id") == sgid]
                enabled_children = [r["check"] for r in child_rows if r["check"].isEnabled()]
                if enabled_children:
                    checked_count = sum(1 for c in enabled_children if c.isChecked())
                    subgrp["check"].blockSignals(True)
                    if checked_count == len(enabled_children):
                        subgrp["check"].setCheckState(2)
                    elif checked_count > 0:
                        subgrp["check"].setCheckState(1)
                    else:
                        subgrp["check"].setCheckState(0)
                    subgrp["check"].blockSignals(False)

        if hasattr(self, '_group_rows'):
            for group_id, grp in self._group_rows.items():
                child_rows = [r for r in self._category_rows.values() if r.get("group_id") == group_id]
                enabled_children = [r["check"] for r in child_rows if r["check"].isEnabled()]
                if enabled_children:
                    checked_count = sum(1 for c in enabled_children if c.isChecked())
                    grp["check"].blockSignals(True)
                    if checked_count == len(enabled_children):
                        grp["check"].setCheckState(2)
                    elif checked_count > 0:
                        grp["check"].setCheckState(1)
                    else:
                        grp["check"].setCheckState(0)
                    grp["check"].blockSignals(False)

        self._recalculate_selected_junk()

    def _animate_scan_dots(self):
        if not getattr(self, '_is_scanning_active', False):
            if hasattr(self, '_scan_dot_timer') and self._scan_dot_timer.isActive():
                self._scan_dot_timer.stop()
            return
        self._scan_dot_step = (self._scan_dot_step % 3) + 1
        dots = "." * self._scan_dot_step
        self.hero_gauge.setCenterText(f"Scanning{dots}")
        self.hero_status_lbl.setText(f"Scanning{dots}")

    def _on_hero_action_clicked(self):
        self._ensure_categories_built()
        if not self._is_scanned:
            def _start_scan_anim():
                self._is_scanning_active = True
                self._scan_dot_step = 1
                self.hero_gauge.setCenterText("Scanning.")
                self.hero_gauge.setSubtitle("0%")
                self.hero_status_lbl.setText("Scanning system categories...")
                self.hero_gauge.setAnimated(True)
                self.hero_gauge.setGrayscale(True)
                if not self._scan_dot_timer.isActive():
                    self._scan_dot_timer.start(400)
                self.scan_requested.emit()
            self.hero_gauge.trigger_fade_transition(220, _start_scan_anim)
        else:
            selected = self.selected_category_ids()
            if selected:
                self.clean_requested.emit(selected)

    def _update_hero_gradient(self):
        if not getattr(self, '_is_scanned', False):
            if hasattr(self, '_hero_gradient_timer') and self._hero_gradient_timer.isActive():
                self._hero_gradient_timer.stop()
            return
        
        colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']
        self._hero_gradient_offset += 0.005
        if self._hero_gradient_offset >= 1.0:
            self._hero_gradient_offset = 0.0
        
        offset = self._hero_gradient_offset
        num_colors = len(colors)
        stops = []
        for i, color in enumerate(colors):
            base_pos = i / (num_colors - 1)
            shifted_pos = (base_pos + offset) % 1.0
            stops.append((shifted_pos, color))
        
        stops.sort(key=lambda x: x[0])
        gradient_stops = ', '.join([f'stop:{pos:.3f} {color}' for pos, color in stops])
        
        # The hero gauge is already animated based on the scanning state.


    def _on_back_scan_clicked(self):
        def _reset_scan_state():
            self._is_scanning_active = False
            if hasattr(self, '_scan_dot_timer') and self._scan_dot_timer.isActive():
                self._scan_dot_timer.stop()
            self._is_scanned = False
            for row in self._category_rows.values():
                row["bytes"] = 0
            self.progress_bar.setValue(0)
            self._recalculate_selected_junk()
        self.hero_gauge.trigger_fade_transition(220, _reset_scan_state)

    def _recalculate_selected_junk(self):
        if not getattr(self, '_categories_built', False):
            if hasattr(self, 'hero_gauge'):
                self.hero_gauge.setValue(0)
                self.hero_gauge.setCenterText("SCAN")
                self.hero_gauge.setSubtitle("Ready to scan")
            if hasattr(self, 'cleanup_view_stack'):
                self.cleanup_view_stack.setCurrentIndex(0)
            return

        from utils.drive_utils import format_bytes
        selected_ids = self.selected_category_ids()
        selected_bytes = sum(row["bytes"] for cat_id, row in self._category_rows.items() if cat_id in selected_ids)
        total_scanned_bytes = sum(row["bytes"] for row in self._category_rows.values())

        # 0. Update Category Rows Visibility
        for cat_id, row in self._category_rows.items():
            row["row"].setVisible(True)

        # 1. Update Subgroups (e.g. Windows Temp Files, Google Chrome)
        if hasattr(self, '_subgroup_rows'):
            for sgid, subgrp in self._subgroup_rows.items():
                sg_total_bytes = sum(row["bytes"] for cat_id, row in self._category_rows.items() if row.get("subgroup_id") == sgid)
                subgrp["size_lbl"].setText(format_bytes(sg_total_bytes) if (self._is_scanned or sg_total_bytes > 0) else "")
                
                # Hide empty subgroups when scanned
                if self._is_scanned and sg_total_bytes == 0:
                    subgrp["frame"].setVisible(False)
                else:
                    subgrp["frame"].setVisible(True)

                child_rows = [row for cat_id, row in self._category_rows.items() if row.get("subgroup_id") == sgid]
                enabled_children = [r["check"] for r in child_rows if r["check"].isEnabled()]
                if enabled_children:
                    checked_count = sum(1 for c in enabled_children if c.isChecked())
                    subgrp["check"].blockSignals(True)
                    if checked_count == len(enabled_children):
                        subgrp["check"].setCheckState(2)
                    elif checked_count > 0:
                        subgrp["check"].setCheckState(1)
                    else:
                        subgrp["check"].setCheckState(0)
                    subgrp["check"].blockSignals(False)

        # 2. Update Main Groups (e.g. System, Browser)
        if hasattr(self, '_group_rows'):
            for group_id, grp in self._group_rows.items():
                group_total_bytes = sum(row["bytes"] for cat_id, row in self._category_rows.items() if row["group_id"] == group_id)
                grp["size_lbl"].setText(format_bytes(group_total_bytes) if (self._is_scanned or group_total_bytes > 0) else "")
                
                # Hide empty main groups when scanned
                if self._is_scanned and group_total_bytes == 0:
                    grp["frame"].setVisible(False)
                else:
                    grp["frame"].setVisible(True)

                child_rows = [row for cat_id, row in self._category_rows.items() if row["group_id"] == group_id]
                enabled_children = [r["check"] for r in child_rows if r["check"].isEnabled()]
                if enabled_children:
                    checked_count = sum(1 for c in enabled_children if c.isChecked())
                    grp["check"].blockSignals(True)
                    if checked_count == len(enabled_children):
                        grp["check"].setCheckState(2)
                    elif checked_count > 0:
                        grp["check"].setCheckState(1)
                    else:
                        grp["check"].setCheckState(0)
                    grp["check"].blockSignals(False)

        if self._is_scanned:
            if total_scanned_bytes > 0 and selected_bytes > 0:
                calc_pct = (selected_bytes / total_scanned_bytes) * 100
                percent = max(1, min(100, int(calc_pct)))
                self.hero_gauge.setValue(percent)
                self.hero_gauge.setCenterText(format_bytes(selected_bytes))
                self.hero_gauge.setSubtitle("CLEAN NOW")
            else:
                self.hero_gauge.setValue(0)
                self.hero_gauge.setCenterText("0 B")
                self.hero_gauge.setSubtitle("0 B Junk")
        else:
            self.hero_gauge.setValue(0)
            self.hero_gauge.setCenterText("SCAN")
            self.hero_gauge.setSubtitle("Ready to scan")

        if hasattr(self, 'cleanup_view_stack'):
            self.cleanup_view_stack.setCurrentIndex(1 if self._is_scanned else 0)

        if self._is_scanned:
            cat_str = "category" if len(selected_ids) == 1 else "categories"
            self.hero_status_lbl.setText(f"Click to clean {len(selected_ids)} {cat_str}\n({format_bytes(selected_bytes)})")
            self.hero_gauge.setEnabled(bool(selected_ids))
            if not self._hero_gradient_timer.isActive() and self.isVisible():
                self._hero_gradient_timer.start(100)
            self._update_hero_gradient()
            self.btn_back_scan.setEnabled(True)
            self.hero_gauge.setAnimated(False)
            self.hero_gauge.setGrayscale(False)
            self.hero_gauge.setClockwise(False)
            self.hero_gauge.setUseGradientForValue(True)
        else:
            if self._hero_gradient_timer.isActive():
                self._hero_gradient_timer.stop()
            cat_str = "category" if len(selected_ids) == 1 else "categories"
            self.hero_status_lbl.setText(f"Ready to scan\n{len(selected_ids)} {cat_str}")
            self.btn_back_scan.setEnabled(False)
            self.hero_gauge.setAnimated(False)
            self.hero_gauge.setGrayscale(True)
            self.hero_gauge.setClockwise(False)
            self.hero_gauge.setUseGradientForValue(False)

    def pause_animations(self):
        if hasattr(self, '_scan_dot_timer') and self._scan_dot_timer.isActive():
            self._scan_dot_timer.stop()
        if hasattr(self, '_hero_gradient_timer') and self._hero_gradient_timer.isActive():
            self._hero_gradient_timer.stop()
        if hasattr(self, 'hero_gauge'):
            self.hero_gauge.pause_animation()
        if hasattr(self, 'empty_gauge'):
            self.empty_gauge.pause_animation()

    def resume_animations(self):
        if not self.isVisible():
            return
        if hasattr(self, 'hero_gauge'):
            self.hero_gauge.resume_animation()
        if hasattr(self, 'empty_gauge'):
            self.empty_gauge.resume_animation()
        if getattr(self, '_is_scanned', False) and hasattr(self, '_hero_gradient_timer') and not self._hero_gradient_timer.isActive():
            self._hero_gradient_timer.start(100)

    def showEvent(self, event):
        super().showEvent(event)
        self.resume_animations()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pause_animations()

    def _create_category_row(self, cat, admin):
        cat_id = cat["id"] if isinstance(cat, dict) else cat.id
        cat_name = cat["name"] if isinstance(cat, dict) else cat.name
        cat_tier = cat.get("tier", 1) if isinstance(cat, dict) else cat.tier
        cat_default = cat.get("default", True) if isinstance(cat, dict) else cat.default
        cat_req_admin = cat.get("requires_admin", False) if isinstance(cat, dict) else cat.requires_admin
        gid = cat.get("group_id", "system") if isinstance(cat, dict) else getattr(cat, "group_id", "system")
        sgid = cat.get("subgroup_id") if isinstance(cat, dict) else getattr(cat, "subgroup_id", None)

        row = QFrame()
        row.setObjectName(f"driveCleanRow_{cat_id}")
        row.setProperty("class", "driveCleanRow")
        row.setFixedHeight(35)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 0, 15, 0)
        row_layout.setSpacing(8)

        # Placeholder to align CheckBox with parent headers that have a 16px arrow button
        dummy_arrow = QWidget()
        dummy_arrow.setObjectName(f"driveCleanDummyArrow_{cat_id}")
        dummy_arrow.setFixedSize(16, 16)
        dummy_arrow.setStyleSheet("background: transparent;")
        row_layout.addWidget(dummy_arrow, alignment=Qt.AlignVCenter)

        cb = AnimatedCheckBox()
        cb.setObjectName(f"driveCleanCheck_{cat_id}")
        cb.blockSignals(True)
        cb.setChecked(bool(cat_default))
        cb.blockSignals(False)
        cb.setEnabled(True)  # Enabled unconditionally since Zero-UAC handles elevated tasks
        cb.setStyleSheet("background: transparent;")
        cb.toggled.connect(lambda checked: self._recalculate_selected_junk())
        row_layout.addWidget(cb, alignment=Qt.AlignVCenter)

        name = QLabel(cat_name)
        name.setObjectName(f"driveCleanName_{cat_id}")
        name.setStyleSheet("color: #e0e0e0; font-size: 11px; font-weight: 600; font-family: 'Orbitron'; background: transparent;")
        row_layout.addWidget(name, stretch=1, alignment=Qt.AlignVCenter)

        if cat_req_admin and not admin:
            badge = QLabel("Zero-UAC")
            badge.setObjectName(f"driveCleanBadge_{cat_id}")
            badge.setStyleSheet("color: #FFCC00; background-color: rgba(255, 204, 0, 0.12); border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800;")
            row_layout.addWidget(badge, alignment=Qt.AlignVCenter)
        else:
            badge = None

        # Folder inspect button positioned immediately to the left of the total size label
        btn_folder = QPushButton()
        btn_folder.setObjectName(f"driveCleanFolderBtn_{cat_id}")
        btn_folder.setProperty("class", "driveCleanFolderBtn")
        btn_folder.setFixedSize(22, 22)
        btn_folder.setCursor(Qt.PointingHandCursor)
        btn_folder.setToolTip(f"Inspect junk paths for {cat_name}")
        folder_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "folder-icon-white.svg")
        folder_icon = _get_cached_drive_icon(folder_icon_path)
        if not folder_icon.isNull():
            btn_folder.setIcon(folder_icon)
            btn_folder.setIconSize(QSize(13, 13))
        else:
            btn_folder.setText("📁")
        btn_folder.clicked.connect(lambda checked=False, cid=cat_id: self._show_junk_items_panel(cid))
        row_layout.addWidget(btn_folder, alignment=Qt.AlignVCenter)

        size = QLabel("—")
        size.setObjectName(f"driveCleanSize_{cat_id}")
        size.setStyleSheet("color: #888888; font-size: 11px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")
        size.setMinimumWidth(80)
        size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_layout.addWidget(size, alignment=Qt.AlignVCenter)

        self._category_rows[cat_id] = {
            "row": row,
            "check": cb,
            "size": size,
            "badge": badge,
            "name": cat_name,
            "btn_folder": btn_folder,
            "tier": cat_tier,
            "cat_default": cat_default,
            "group_id": gid,
            "subgroup_id": sgid,
            "bytes": 0,
            "paths": [],
        }
        return row, cat_id

    def _build_categories(self):
        if getattr(self, '_categories_built', False):
            return
        self._categories_built = True

        import os
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtCore import QSize
        from utils.drive_utils import get_junk_categories, is_admin

        self.category_container.setUpdatesEnabled(False)
        self.category_container.setStyleSheet("""
            QFrame[class="driveCleanRow"] {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QFrame[class="driveCleanRow"]:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QWidget[class="driveGroupHeader"] {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QWidget[class="driveSubGroupHeader"] {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QWidget[class="driveSubGroupHeader"]:hover {
                background: rgba(255, 91, 6, 0.15);
            }
            QPushButton[class="driveCleanFolderBtn"] {
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 2px;
            }
            QPushButton[class="driveCleanFolderBtn"]:hover {
                background: rgba(255, 91, 6, 0.25);
            }
        """)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        down_icon_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg")
        right_icon_path = os.path.join(script_dir, "UI Icons", "right-arrow-triangle.svg")
        down_pixmap = _get_cached_drive_pixmap(down_icon_path, 16, 16)
        right_pixmap = _get_cached_drive_pixmap(right_icon_path, 16, 16)

        admin = is_admin()
        categories = get_junk_categories()

        # Group categories by group_id -> subgroup_id
        groups_map = {}
        for cat in categories:
            gid = cat.get("group_id", "system") if isinstance(cat, dict) else getattr(cat, "group_id", "system")
            gname = cat.get("group_name", "System") if isinstance(cat, dict) else getattr(cat, "group_name", "System")
            sgid = cat.get("subgroup_id") if isinstance(cat, dict) else getattr(cat, "subgroup_id", None)
            sgname = cat.get("subgroup_name") if isinstance(cat, dict) else getattr(cat, "subgroup_name", None)

            if gid not in groups_map:
                groups_map[gid] = {"name": gname, "direct_items": [], "subgroups": {}}

            if sgid:
                if sgid not in groups_map[gid]["subgroups"]:
                    groups_map[gid]["subgroups"][sgid] = {"name": sgname, "items": []}
                groups_map[gid]["subgroups"][sgid]["items"].append(cat)
            else:
                groups_map[gid]["direct_items"].append(cat)

        self._group_rows = {}
        self._subgroup_rows = {}

        SUBGROUP_ICON_MAP = {
            "chrome": "chrome.png",
            "edge": "edge.png",
            "brave": "brave.png",
            "firefox": "firefox.png",
            "opera": "opera.png",
            "vivaldi": "vivaldi.png",
        }

        for gid, grp_info in groups_map.items():
            group_frame = QFrame()
            group_frame.setObjectName(f"driveGroupFrame_{gid}")
            group_frame.setStyleSheet(f"QFrame#driveGroupFrame_{gid} {{ background-color: transparent; border: none; }}")
            group_layout = QVBoxLayout(group_frame)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(0)

            # --- Main Group Header Row ---
            header_row = QWidget()
            header_row.setObjectName(f"driveGroupHeader_{gid}")
            header_row.setProperty("class", "driveGroupHeader")
            header_row.setFixedHeight(35)
            header_layout = QHBoxLayout(header_row)
            header_layout.setContentsMargins(8, 0, 15, 0)
            header_layout.setSpacing(8)

            btn_toggle = QLabel()
            btn_toggle.setObjectName(f"driveGroupToggleBtn_{gid}")
            btn_toggle.setFixedSize(16, 16)
            btn_toggle.setScaledContents(True)
            btn_toggle.setPixmap(down_pixmap)
            btn_toggle.setCursor(Qt.PointingHandCursor)

            grp_cb = AnimatedCheckBox()
            grp_cb.setObjectName(f"driveGroupCheck_{gid}")
            grp_cb.blockSignals(True)
            grp_cb.setChecked(True)
            grp_cb.blockSignals(False)
            grp_cb.setStyleSheet("background: transparent;")

            grp_title = QLabel(grp_info["name"])
            grp_title.setObjectName(f"driveGroupTitle_{gid}")
            grp_title.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")

            grp_size = QLabel("")
            grp_size.setObjectName(f"driveGroupSize_{gid}")
            grp_size.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")

            header_layout.addWidget(btn_toggle, alignment=Qt.AlignVCenter)
            header_layout.addWidget(grp_cb, alignment=Qt.AlignVCenter)
            header_layout.addWidget(grp_title, alignment=Qt.AlignVCenter)
            header_layout.addStretch()
            header_layout.addWidget(grp_size, alignment=Qt.AlignVCenter)
            group_layout.addWidget(header_row)

            # --- Main Group Content Container ---
            child_container = QWidget()
            child_container.setObjectName(f"driveGroupChildContainer_{gid}")
            child_layout = QVBoxLayout(child_container)
            child_layout.setContentsMargins(18, 0, 0, 0)
            child_layout.setSpacing(0)

            def _toggle_main(e, container=child_container, btn=btn_toggle):
                container.setVisible(not container.isVisible())
                btn.setPixmap(down_pixmap if container.isVisible() else right_pixmap)
            btn_toggle.mousePressEvent = _toggle_main

            def _on_main_group_toggled(checked, group_id=gid):
                for cat_id, row_data in self._category_rows.items():
                    if row_data["group_id"] == group_id and row_data["check"].isEnabled():
                        row_data["check"].blockSignals(True)
                        row_data["check"].setChecked(checked)
                        row_data["check"].blockSignals(False)
                self._recalculate_selected_junk()

            grp_cb.toggled.connect(_on_main_group_toggled)

            # 1) Direct Items under Main Group (e.g. Recycle Bin)
            for cat in grp_info["direct_items"]:
                row, cat_id = self._create_category_row(cat, admin)
                child_layout.addWidget(row)

            # 2) Subgroups under Main Group (e.g. Windows Temp Files)
            for sgid, subgrp_info in grp_info["subgroups"].items():
                sub_frame = QFrame()
                sub_frame.setObjectName(f"driveSubGroupFrame_{sgid}")
                sub_frame.setStyleSheet(f"QFrame#driveSubGroupFrame_{sgid} {{ background-color: transparent; border: none; }}")
                sub_layout = QVBoxLayout(sub_frame)
                sub_layout.setContentsMargins(0, 0, 0, 0)
                sub_layout.setSpacing(0)

                sub_header = QWidget()
                sub_header.setObjectName(f"driveSubGroupHeader_{sgid}")
                sub_header.setProperty("class", "driveSubGroupHeader")
                sub_header.setFixedHeight(35)
                sub_h_layout = QHBoxLayout(sub_header)
                sub_h_layout.setContentsMargins(8, 0, 15, 0)
                sub_h_layout.setSpacing(8)

                btn_sub_toggle = QLabel()
                btn_sub_toggle.setObjectName(f"driveSubGroupToggleBtn_{sgid}")
                btn_sub_toggle.setFixedSize(16, 16)
                btn_sub_toggle.setScaledContents(True)
                btn_sub_toggle.setPixmap(down_pixmap)
                btn_sub_toggle.setCursor(Qt.PointingHandCursor)

                sub_cb = AnimatedCheckBox()
                sub_cb.setObjectName(f"driveSubGroupCheck_{sgid}")
                sub_cb.blockSignals(True)
                sub_cb.setChecked(True)
                sub_cb.blockSignals(False)
                sub_cb.setStyleSheet("background: transparent;")

                sub_h_layout.addWidget(btn_sub_toggle, alignment=Qt.AlignVCenter)
                sub_h_layout.addWidget(sub_cb, alignment=Qt.AlignVCenter)

                sub_title = QLabel(subgrp_info["name"])
                sub_title.setObjectName(f"driveSubGroupTitle_{sgid}")
                sub_title.setStyleSheet("color: #e0e0e0; font-size: 11px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")
                sub_h_layout.addWidget(sub_title, alignment=Qt.AlignVCenter)

                icon_filename = SUBGROUP_ICON_MAP.get(sgid)
                if icon_filename:
                    icon_path = os.path.join(script_dir, "UI Icons", icon_filename)
                    sub_pix = _get_cached_drive_pixmap(icon_path, 18, 18)
                    if not sub_pix.isNull():
                        sub_icon_lbl = QLabel()
                        sub_icon_lbl.setObjectName(f"driveSubGroupIcon_{sgid}")
                        sub_icon_lbl.setFixedSize(18, 18)
                        sub_icon_lbl.setPixmap(sub_pix)
                        sub_icon_lbl.setStyleSheet("background: transparent;")
                        sub_h_layout.addWidget(sub_icon_lbl, alignment=Qt.AlignVCenter)

                sub_size = QLabel("")
                sub_size.setObjectName(f"driveSubGroupSize_{sgid}")
                sub_size.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")

                sub_h_layout.addStretch()
                sub_h_layout.addWidget(sub_size, alignment=Qt.AlignVCenter)
                sub_layout.addWidget(sub_header)

                sub_child_container = QWidget()
                sub_child_container.setObjectName(f"driveSubGroupChildContainer_{sgid}")
                sub_child_layout = QVBoxLayout(sub_child_container)
                sub_child_layout.setContentsMargins(18, 0, 0, 0)
                sub_child_layout.setSpacing(0)

                def _toggle_sub(e, container=sub_child_container, btn=btn_sub_toggle):
                    container.setVisible(not container.isVisible())
                    btn.setPixmap(down_pixmap if container.isVisible() else right_pixmap)
                btn_sub_toggle.mousePressEvent = _toggle_sub

                def _on_subgroup_toggled(checked, subgroup_id=sgid):
                    for cat_id, row_data in self._category_rows.items():
                        if row_data.get("subgroup_id") == subgroup_id and row_data["check"].isEnabled():
                            row_data["check"].blockSignals(True)
                            row_data["check"].setChecked(checked)
                            row_data["check"].blockSignals(False)
                    self._recalculate_selected_junk()

                sub_cb.toggled.connect(_on_subgroup_toggled)

                for cat in subgrp_info["items"]:
                    row, cat_id = self._create_category_row(cat, admin)
                    sub_child_layout.addWidget(row)

                sub_layout.addWidget(sub_child_container)
                child_layout.addWidget(sub_frame)

                self._subgroup_rows[sgid] = {
                    "frame": sub_frame,
                    "check": sub_cb,
                    "size_lbl": sub_size,
                    "title_lbl": sub_title,
                    "container": sub_child_container,
                    "group_id": gid,
                }

            group_layout.addWidget(child_container)
            self.category_layout.addWidget(group_frame)
            self._group_rows[gid] = {
                "frame": group_frame,
                "check": grp_cb,
                "size_lbl": grp_size,
                "title_lbl": grp_title,
                "container": child_container,
            }

        self.category_layout.addStretch()
        self.category_container.setUpdatesEnabled(True)
        self._recalculate_selected_junk()

    def _switch_cleaner_tab(self, index):
        """Switch sub-tab between System clean-up, System tweaks, and Disk defragment."""
        self._current_cleaner_tab = index
        self._update_cleaner_tab_buttons()
        self.cleaner_stack.setCurrentIndex(index)
        if index == 0 and getattr(self, '_categories_built', False):
            # Ensure all categories are visible in System clean-up page
            for cat_id, data in self._category_rows.items():
                data["row"].setVisible(True)

    def _update_cleaner_tab_buttons(self):
        """Update sub-tab button styles matching macroSubNav style 100%."""
        for i, btn in enumerate(self._cleaner_tab_btns):
            if i == self._current_cleaner_tab:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 91, 6, 0.08);
                        color: #FF5B06;
                        border: none;
                        border-bottom: 2px solid #FF5B06;
                        border-radius: 6px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 11px;
                        font-weight: 700;
                        padding-top: 4px;
                        padding-bottom: 2px;
                        padding-left: 12px;
                        padding-right: 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #888888;
                        border: none;
                        border-bottom: 2px solid transparent;
                        border-radius: 6px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 11px;
                        font-weight: 600;
                        padding-top: 4px;
                        padding-bottom: 2px;
                        padding-left: 12px;
                        padding-right: 12px;
                    }
                    QPushButton:hover {
                        color: #ffffff;
                        background: rgba(255, 91, 6, 0.12);
                        border-radius: 6px;
                    }
                """)

    def selected_category_ids(self):
        self._ensure_categories_built()
        return [cat_id for cat_id, row in self._category_rows.items() if row["check"].isChecked() and row["check"].isEnabled()]

    def selected_has_tier3(self):
        self._ensure_categories_built()
        return any(row["tier"] >= 3 and row["check"].isChecked() for row in self._category_rows.values())

    def set_busy(self, busy, text="Working...", percent=0):
        self.progress_bar.setValue(percent)
        self.status_label.setText(text)
        self.hero_gauge.setEnabled(not busy)
        self.hero_status_lbl.setText("Scanning..." if not self._is_scanned else "Cleaning...")
        if busy:
            self.hero_gauge.setAnimated(True)
            self.hero_gauge.setGrayscale(False)
            self.hero_gauge.setClockwise(True)
            self.hero_gauge.setUseGradientForValue(False)

    def update_progress(self, text, percent):
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self.status_label.setText(text)
        if getattr(self, '_is_scanning_active', False):
            self.hero_gauge.setSubtitle(f"{int(percent)}%")

    def _show_junk_items_panel(self, cat_id):
        self._ensure_categories_built()
        row_data = self._category_rows.get(cat_id)
        if not row_data:
            return
        cat_name = row_data.get("name", "ITEMS")
        paths = row_data.get("paths", [])
        if not paths:
            from utils.drive_utils import JUNK_CATEGORIES, _expanded_paths
            orig_cat = next((c for c in JUNK_CATEGORIES if c.id == cat_id), None)
            if orig_cat:
                paths = _expanded_paths(orig_cat.paths)

        panel = JunkItemsFloatingPanel(title=f"ITEMS", paths=paths, parent=self.window() or self)
        parent_win = self.window() or self
        geo = parent_win.geometry()
        x = geo.x() + (geo.width() - panel.width()) // 2
        y = geo.y() + (geo.height() - panel.height()) // 2
        panel.move(x, y)
        panel.exec()

    def update_results(self, results):
        self._ensure_categories_built()
        from utils.drive_utils import format_bytes
        def _apply_scanned_results():
            self._is_scanning_active = False
            if hasattr(self, '_scan_dot_timer') and self._scan_dot_timer.isActive():
                self._scan_dot_timer.stop()
            self._is_scanned = True
            total = 0
            for cat_id, row in self._category_rows.items():
                data = results.get(cat_id, {})
                bytes_found = int(data.get("bytes", 0) or 0)
                row["bytes"] = bytes_found
                row["paths"] = data.get("paths", [])
                row["size"].setText(format_bytes(bytes_found))
                if data.get("admin_required") and row.get("badge") is not None:
                    row["badge"].setText("Zero-UAC")
                total += bytes_found

            self.progress_bar.setValue(100)
            self.status_label.setText("Scan complete. Review categories before cleaning.")
            self._recalculate_selected_junk()

        self.hero_gauge.trigger_fade_transition(220, _apply_scanned_results)

    def finish_clean(self, cleaned, skipped, errors):
        self._ensure_categories_built()
        from utils.drive_utils import format_bytes
        freed = format_bytes(cleaned)
        def _apply_cleaned_state():
            self._is_scanning_active = False
            if hasattr(self, '_scan_dot_timer') and self._scan_dot_timer.isActive():
                self._scan_dot_timer.stop()
            self._is_scanned = False
            self.hero_status_lbl.setText(f"Cleaned {freed}!")
            self.btn_back_scan.setEnabled(False)
            self.hero_gauge.setEnabled(True)
            self.hero_gauge.setValue(0)
            self.hero_gauge.setSubtitle(f"Cleaned {freed}")
            self.hero_gauge.setCenterText("SCAN")
            self.progress_bar.setValue(0)
            for cat_id in self.selected_category_ids():
                if cat_id in self._category_rows:
                    self._category_rows[cat_id]["bytes"] = 0
                    self._category_rows[cat_id]["size"].setText("0 B")

            self._recalculate_selected_junk()

        self.hero_gauge.trigger_fade_transition(220, _apply_cleaned_state)


class HeaderLhmIconButton(QPushButton):
    """
    Header LHM Icon Button with brightened icon on hover, 100% center-pivot pop animation, and no border.
    Component Name: HeaderLhmIconButton
    """
    def __init__(self, icon_path, parent=None):
        super().__init__("", parent)
        self.setObjectName("headerOpenLhmBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 38)
        self.setToolTip("Open LHM Panel")

        self.normal_pixmap = QPixmap()
        self.hover_pixmap = QPixmap()
        self._scale_val = 1.0

        if os.path.exists(icon_path):
            self.normal_pixmap = QPixmap(icon_path)
            
            # True RGB channel brightness scaling (+45% brighter, preserving original colors)
            img = self.normal_pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
            w, h = img.width(), img.height()
            for y in range(h):
                for x in range(w):
                    c = QColor(img.pixelColor(x, y))
                    if c.alpha() > 0:
                        r = min(255, int(c.red() * 1.45))
                        g = min(255, int(c.green() * 1.45))
                        b = min(255, int(c.blue() * 1.45))
                        img.setPixelColor(x, y, QColor(r, g, b, c.alpha()))
            
            self.hover_pixmap = QPixmap.fromImage(img)

        self._anim = QPropertyAnimation(self, b"scaleVal")
        self._anim.setDuration(180)

        self.setStyleSheet("""
            QPushButton#headerOpenLhmBtn {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton#headerOpenLhmBtn:hover {
                background: rgba(255, 255, 255, 0.14);
                border: none;
            }
            QPushButton#headerOpenLhmBtn:pressed {
                background: rgba(255, 255, 255, 0.22);
                border: none;
            }
        """)

    def getScaleVal(self):
        return self._scale_val

    def setScaleVal(self, val):
        self._scale_val = val
        self.update()

    scaleVal = Property(float, getScaleVal, setScaleVal)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._anim.setStartValue(self._scale_val)
        self._anim.setEndValue(1.18)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setStartValue(self._scale_val)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        # 1. Paint button background & QSS styles
        super().paintEvent(event)
        
        # 2. Paint icon with 100% TRUE CENTER PIVOT (0.5, 0.5)
        pix = self.hover_pixmap if (self.underMouse() and not self.hover_pixmap.isNull()) else self.normal_pixmap
        if not pix.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            rect = self.rect()
            cx = rect.center().x()
            cy = rect.center().y()
            
            sz = int(26 * self._scale_val)
            icon_rect = QRect(cx - sz // 2, cy - sz // 2, sz, sz)
            
            painter.drawPixmap(icon_rect, pix)


# ============================================
# MAIN HARDWARE PANEL
# ============================================

def _is_tab_profiling_enabled():
    try:
        import json, os
        appdata = os.getenv("APPDATA", "")
        settings_file = os.path.join(appdata, "HELXAID", "settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r") as f:
                return json.load(f).get("calculate_tab_initialize", False)
    except Exception:
        pass
    return False


class HardwarePanelWidget(QWidget):
    """
    Main Hardware Panel with Overview and sub-pages.
    
    Component Name: HardwarePanelWidget
    """
    
    # Signal to handle cross-thread updates back to GUI (must be defined at class level)
    boost_completed_signal = Signal(dict, str, str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HardwarePanelWidget")
        
        # Connect the signal to the safe wrapper
        self.boost_completed_signal.connect(self._boost_complete_safe)
        
        # Initialize boosters buttons (lazy loaded in pages)
        self.manual_boost_btn = None
        self.clean_btn = None
        
        # Initialize check lists for boosters
        self._essential_checks = []
        self._process_checks = []
        self._basic_service_checks = []
        self._advanced_service_checks = []
        
        # Initialize hardware monitor
        self.monitor = get_monitor(500)  # 500ms default
        
        # Update timer
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_stats)
        
        # History for charts (bounded deques to prevent memory leaks)
        self._cpu_history = collections.deque(maxlen=MAX_CHART_HISTORY)
        self._ram_history = collections.deque(maxlen=MAX_CHART_HISTORY)
        self._disk_usage_history = collections.deque(maxlen=MAX_CHART_HISTORY)
        self._chart_display_length = 60  # Show last 60 points
        self._hwmon_check_counter = 0  # Counter for throttled hwmon status check
        
        # Auto-refresh counters (initialized here to avoid issues if _update_stats errors early)
        self._processes_refresh_counter = 0
        self._services_refresh_counter = 0
        
        # Boost thread lock and generation tracking to prevent overlapping cycles and stale signals
        self._boost_lock = threading.Lock()
        self._boost_generation_id = 0
        
        # Auto-scroll control per chart - pauses when user manually scrolls, resumes when head is visible
        self._chart_auto_scroll = {
            'cpu': True,
            'ram': True,
            'disk': True
        }
        
        # Disk usage tracking for clickable bars
        self._active_drives = {}  # drive letter -> active state (True/False)
        self._drive_history = {}  # drive letter -> usage history list
        self._drive_curves = {}   # drive letter -> plot curve
        self._drive_colors = ['#ff6b35', '#22d3ee', '#a78bfa', '#fbbf24', '#4ade80']  # Colors for drives
        self._drive_color_map = {}  # drive letter -> fixed color
        self._disk_details = {}  # Cache for disk model/type info (fetched once)
        self._disk_details_fetched = False
        self._drive_hardware_info = {}
        self._drive_volume_cards = {}
        self._drive_scan_worker = None
        self._drive_clean_worker = None
        self._cpu_freq_unit = "GHz"

        self._setup_ui()
        self._apply_style()

        print("[Hardware] HardwarePanelWidget initialized")
    
    def _setup_ui(self):
        self.setObjectName("hardwarePanelWidget")
        self.setStyleSheet("QWidget#hardwarePanelWidget { background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header with settings
        header = self._create_header()
        layout.addWidget(header)
        
        # Navigation bar with tabs
        navbar = self._create_navbar()
        layout.addWidget(navbar)
        
        # Stacked widget for different pages
        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("hardwarePageStack")
        
        # Track which pages have been created (for lazy loading)
        self._pages_created = [False] * 6
        
        # Create Page 0 (Quick Setup) immediately so HELXTATS is NEVER blank
        quick_setup_page = self._create_overview_page()
        self._page_stack.addWidget(quick_setup_page)
        self._pages_created[0] = True
        
        # Add placeholder widgets for remaining pages 1-5 (populated lazily on tab click)
        for i in range(1, 6):
            placeholder = QWidget()
            placeholder.setObjectName(f"placeholder_{i}")
            self._page_stack.addWidget(placeholder)
        
        layout.addWidget(self._page_stack, stretch=1)
        self._page_stack.setCurrentIndex(0)
        
        # Initial count update (will pull from config since others aren't loaded)
        self._update_total_items_count()
        
        # Trigger async drive & SMART info query immediately on startup for Quick Setup page
        self._request_async_drive_info()
    
    def _create_navbar(self):
        """Create navigation bar with tab buttons."""
        navbar = QWidget()
        navbar.setObjectName("hardwareNavbar")
        navbar.setFixedHeight(40)
        navbar_layout = QHBoxLayout(navbar)
        navbar_layout.setContentsMargins(0, 0, 0, 0)
        navbar_layout.setSpacing(4)
        
        # Tab buttons
        tab_names = ["Quick Setup", "Booster", "CPU", "Drive", "Health", "Network"]
        self._nav_buttons = []
        
        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setObjectName(f"navBtn_{name.replace(' ', '')}")
            btn.setFixedHeight(35)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(i == 0)  # First tab active by default
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            self._nav_buttons.append(btn)
            navbar_layout.addWidget(btn)
        
        navbar_layout.addStretch()
        self._update_nav_button_styles()
        
        return navbar

    def _update_nav_button_styles(self):
        """Update main navbar tab button styles 100% matching HELXAIRO style."""
        current_idx = self._page_stack.currentIndex() if hasattr(self, '_page_stack') else 0
        for i, btn in enumerate(self._nav_buttons):
            if i == current_idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #2a2a2a;
                        color: #ffffff;
                        border: none;
                        border-top: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #cc47aa, stop:0.5 #ff0919, stop:1 #e89805);
                        border-top-left-radius: 6px;
                        border-top-right-radius: 6px;
                        border-bottom-left-radius: 0px;
                        border-bottom-right-radius: 0px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        font-weight: bold;
                        padding-top: 0px;
                        padding-bottom: 3px;
                        padding-left: 14px;
                        padding-right: 14px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #888888;
                        border: none;
                        border-top: 3px solid transparent;
                        border-radius: 0px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        padding-top: 0px;
                        padding-bottom: 3px;
                        padding-left: 14px;
                        padding-right: 14px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.05);
                        color: #b0b0b0;
                    }
                """)
    
    def _switch_page(self, index: int):
        """Switch to a different page in the stack, lazy-loading if needed with latency profiling."""
        is_profiling = _is_tab_profiling_enabled()
        t_start = time.perf_counter() if is_profiling else 0.0

        was_active = self._update_timer.isActive()
        self._update_timer.stop()

        # Pause animation timers on previously active Drive tab if moving away
        old_index = self._page_stack.currentIndex() if hasattr(self, '_page_stack') else -1
        if old_index == 3 and hasattr(self, 'drive_cleaner'):
            self.drive_cleaner.pause_animations()

        # Lazy load page if not yet created
        if not self._pages_created[index]:
            self._create_page_lazy(index)

        self._page_stack.setCurrentIndex(index)

        # Update button states matching HELXAIRO
        self._update_nav_button_styles()

        # Show Update Interval control only on tabs that use hardware polling
        # 0=Quick Setup, 2=CPU, 3=Drive, 4=Health
        interval_visible_tabs = {0, 2, 3, 4}
        if hasattr(self, '_interval_container'):
            self._interval_container.setVisible(index in interval_visible_tabs)

        # Resume animations & trigger async info fetch if switching to Drive tab (index 3)
        if index == 3:
            if hasattr(self, 'drive_cleaner'):
                self.drive_cleaner.resume_animations()
            self._request_async_drive_info()

        # Resume timer after page switch is complete
        if was_active:
            self._update_timer.start(self.monitor.update_interval_ms)

        if is_profiling:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            tab_names = {
                0: "HELXTATS - Quick Setup",
                1: "HELXTATS - Booster",
                2: "HELXTATS - CPU",
                3: "HELXTATS - Drive",
                4: "HELXTATS - Health",
                5: "HELXTATS - Network",
            }
            tab_label = tab_names.get(index, f"HELXTATS Tab {index}")
            print(f"[Tab Profiler] {tab_label} initialized in {elapsed_ms:.2f} ms")
            try:
                from launcher import TabInitProfilerWindow
                self._tab_profiler_win = TabInitProfilerWindow(tab_label, elapsed_ms)
                self._tab_profiler_win.show()
                self._tab_profiler_win.raise_()
                self._tab_profiler_win.activateWindow()
            except Exception as pe:
                print(f"[Tab Profiler Error] {pe}")
    
    def _create_page_lazy(self, index: int):
        """Create a page on-demand (lazy loading)."""
        page_creators = {
            0: self._create_overview_page,  # Quick Setup
            1: self._create_ram_page,       # Booster
            2: self._create_cpu_page,       # CPU
            3: self._create_drive_page,     # Drive
            4: self._create_health_page,    # Health
            5: self._create_network_page,   # Network
        }
        
        if index in page_creators:
            # Create the actual page
            new_page = page_creators[index]()
            
            # Replace the placeholder widget cleanly without shrinking/shifting stack indices
            old_widget = self._page_stack.widget(index)
            self._page_stack.insertWidget(index, new_page)
            if old_widget:
                self._page_stack.removeWidget(old_widget)
                old_widget.deleteLater()
            
            self._pages_created[index] = True
            self._page_stack.setCurrentIndex(index)
            print(f"[Hardware] Lazy loaded page {index}")
    
    def _reset_chart_histories(self):
        """Reset all chart histories (called on page change)."""
        self._cpu_history.clear()
        self._ram_history.clear()
        self._disk_usage_history.clear()
        self._drive_history = {}
        # Reset all chart auto-scroll on page change
        self._chart_auto_scroll = {'cpu': True, 'ram': True, 'disk': True}
    
    def _get_chart_key(self, chart) -> str:
        """Get the key for a specific chart."""
        if hasattr(self, 'ram_chart') and chart == self.ram_chart:
            return 'ram'
        elif hasattr(self, 'cpu_chart') and chart == self.cpu_chart:
            return 'cpu'
        elif hasattr(self, 'disk_chart') and chart == self.disk_chart:
            return 'disk'
        return ''
    
    def _pause_auto_scroll_for_chart(self, chart):
        """Pause auto-scroll for a specific chart when user drags it."""
        key = self._get_chart_key(chart)
        if key:
            self._chart_auto_scroll[key] = False
    
    def _check_auto_scroll_from_view(self, chart, history_len: int):
        """Check if user has scrolled to view the head (latest data). If so, resume auto-scroll for that chart."""
        if history_len == 0:
            return
        key = self._get_chart_key(chart)
        if not key:
            return
        # Get current X-axis view range
        view_range = chart.viewRange()
        _, x_max_view = view_range[0]
        # Head is at index (history_len - 1)
        # If the view includes the head position, resume auto-scroll for this chart
        head_pos = history_len - 1
        if x_max_view >= head_pos:
            self._chart_auto_scroll[key] = True
    
    def _get_chart_history_len(self, chart) -> int:
        """Get the history length for a specific chart."""
        if chart == self.ram_chart:
            return len(self._ram_history)
        elif chart == self.cpu_chart:
            return len(self._cpu_history)
        elif chart == self.disk_chart:
            return len(self._disk_usage_history)
        return 0
    
    def _create_ram_page(self):
        """Create RAM detailed page with cleaner UI."""
        page = QWidget()
        page.setObjectName("ramPage")
        main_layout = QHBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)
        
        # ====== Left Side: Gauge + Controls ======
        left_panel = QWidget()
        left_panel.setObjectName("ramLeftPanel")
        left_panel.setFixedWidth(220)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Title
        booster_title = QLabel("BOOSTER")
        booster_title.setObjectName("boosterTitle")
        booster_title.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: 700; background: transparent;")
        booster_title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(booster_title)
        
        # Circular Gauge
        self.ram_gauge = CircularGauge()
        self.ram_gauge.setObjectName("ramGauge")
        self.ram_gauge.setFixedSize(180, 180)
        self.ram_gauge.setValue(0)
        left_layout.addWidget(self.ram_gauge, alignment=Qt.AlignCenter)
        
        # Items to optimize label
        self.items_label = QLabel("0 items to be optimized")
        self.items_label.setObjectName("itemsLabel")
        self.items_label.setStyleSheet("color: #e0e0e0; font-size: 14px; background: transparent;")
        self.items_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.items_label)
        

        # Manual Boost button
        self.manual_boost_btn = QPushButton("MANUAL BOOST")
        self.manual_boost_btn.setObjectName("manualBoostBtn")
        self.manual_boost_btn.setFixedHeight(40)
        self.manual_boost_btn.setCursor(Qt.PointingHandCursor)
        self.manual_boost_btn.clicked.connect(self._run_manual_boost)
        self.manual_boost_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        left_layout.addWidget(self.manual_boost_btn)
        

        left_layout.addStretch()
        
        # Notification checkboxes
        self.notify_boost_cb = AnimatedCheckBox("Notify me when boosting")
        self.notify_boost_cb.setObjectName("notifyBoostCb")
        self.notify_boost_cb.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        self.notify_boost_cb.setChecked(True)  # Default: ON
        self.notify_boost_cb.toggled.connect(self._save_booster_settings)
        left_layout.addWidget(self.notify_boost_cb)
        
        self.auto_update_cb = AnimatedCheckBox("Auto update Boost settings\non profile change when\nBoost is active")
        self.auto_update_cb.setObjectName("autoUpdateCb")
        self.auto_update_cb.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        left_layout.addWidget(self.auto_update_cb)
        
        main_layout.addWidget(left_panel)
        
        # ====== Right Side: Embedded 4-Tab Content ======
        right_panel = QWidget()
        right_panel.setObjectName("ramRightPanel")
        right_panel.setStyleSheet("""
            QWidget#ramRightPanel {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Tab bar container matching macroSubNav
        tab_bar = QWidget()
        tab_bar.setObjectName("ramTabBar")
        tab_bar.setFixedHeight(40)
        tab_bar.setStyleSheet("""
            QWidget#ramTabBar {
                background: rgba(26, 26, 26, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(6, 5, 6, 5)
        tab_bar_layout.setSpacing(6)
        
        # Create tab buttons
        tab_icons = ["Essential", "Processes", "Basic", "Advanced"]
        tab_names = ["Essential", "Processes", "Basic", "Advanced"]
        self._ram_tab_btns = []
        
        for i, (icon, name) in enumerate(zip(tab_icons, tab_names)):
            btn = QPushButton(f"{icon}")
            btn.setObjectName(f"ramTabBtn_{i}")
            btn.setFixedHeight(35)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            btn.setProperty("tab_index", i)
            btn.clicked.connect(lambda checked, idx=i: self._switch_ram_tab(idx))
            self._ram_tab_btns.append(btn)
            tab_bar_layout.addWidget(btn)
        
        tab_bar_layout.addStretch()
        
        right_layout.addWidget(tab_bar)
        
        # Description label
        self._ram_tab_desc = QLabel("Essential items for CPU and memory optimization.")
        self._ram_tab_desc.setObjectName("ramTabDesc")
        self._ram_tab_desc.setFixedHeight(35)
        self._ram_tab_desc.setWordWrap(True)
        self._ram_tab_desc.setStyleSheet("""
            QLabel { 
                color: #888888; 
                font-size: 10px; 
                padding: 8px 15px;
                background: rgba(0, 0, 0, 0.3);
            }
        """)
        right_layout.addWidget(self._ram_tab_desc)
        
        # Content stack
        self._ram_tab_stack = QStackedWidget()
        self._ram_tab_stack.setObjectName("ramTabStack")
        
        # Add 4 tab pages (Lazy Loading: only Essential tab is created eagerly)
        self._ram_subtabs_created = [True, False, False, False]
        self._ram_tab_stack.addWidget(self._create_essential_tab())
        for _ in range(3):
            placeholder = QWidget()
            placeholder.setStyleSheet("background: transparent;")
            self._ram_tab_stack.addWidget(placeholder)
        
        right_layout.addWidget(self._ram_tab_stack, stretch=1)
        
        self._current_ram_tab = 0
        self._update_ram_tab_buttons()
        
        main_layout.addWidget(right_panel, stretch=1)
        
        # Load preset settings for processes and services tabs
        self._load_custom_preset_settings()
        
        # Force a UI sync of all checked items now that all tabs are built
        self._update_total_items_count()
        
        return page
    
    def _on_ram_mode_selected(self, mode_index: int):
        """Handle RAM mode button selection."""
        self._current_ram_mode = mode_index
        self._update_ram_mode_buttons()
        
        # Show/hide Custom Preset button
        if mode_index == 2:  # Custom mode
            self.custom_preset_btn.show()
        else:
            self.custom_preset_btn.hide()
    
    def _update_ram_mode_buttons(self):
        """Update mode button styles based on current selection."""
        for i, btn in enumerate(self._ram_mode_btns):
            if i == self._current_ram_mode:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                        color: #1a1a1a;
                        border: none;
                        border-radius: 6px;
                        font-size: 14px;
                        font-weight: 600;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #333;
                        color: #e0e0e0;
                        border: 1px solid #444;
                        border-radius: 6px;
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background: #444;
                        border-color: #FF5B06;
                    }
                """)
    
    def _save_booster_json_safe(self, settings_dict: dict) -> bool:
        """Atomically save dictionary to booster_settings.json using temporary file."""
        import os, json
        from launcher import APPDATA_DIR
        
        settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
        temp_path = settings_path + ".tmp"
        
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=4)
            os.replace(temp_path, settings_path)
            return True
        except Exception as e:
            print(f"[Booster] Atomic save failed: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return False

    def _load_booster_json_safe(self) -> dict:
        """Safely load dictionary from booster_settings.json with corruption recovery."""
        import os, json
        from launcher import APPDATA_DIR
        
        settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
        if not os.path.exists(settings_path):
            return {}
            
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[Booster] Corrupt JSON detected ({e}). Backing up file.")
            try:
                os.replace(settings_path, settings_path + ".corrupted")
            except Exception:
                pass
            return {}
        except Exception as e:
            print(f"[Booster] Error reading booster settings: {e}")
            return {}

    def _save_custom_preset(self):
        """Save all selections across the 4 tabs into booster_settings.json."""
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        settings = self._load_booster_json_safe()
                
        # 1. Essential
        if hasattr(self, '_essential_checks'):
            selected = []
            for i, cb in enumerate(self._essential_checks):
                if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                    selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
            settings["essential_optimizations"] = selected
            
        # 2. Processes
        if hasattr(self, '_process_checks') and hasattr(self, '_process_data'):
            selected = []
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    selected.append(self._process_data[i]["name"])
            settings["processes_to_close"] = selected
            
        # 3. Basic Services
        if hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_service_data'):
            selected = []
            for i, cb in enumerate(self._basic_service_checks):
                if cb.isChecked() and i < len(self._basic_service_data):
                    selected.append(self._basic_service_data[i]["name"])
            settings["basic_services_to_stop"] = selected
            
        # 4. Advanced Services
        if hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_service_data'):
            selected = []
            for i, cb in enumerate(self._advanced_service_checks):
                if cb.isChecked() and i < len(self._advanced_service_data):
                    selected.append(self._advanced_service_data[i]["name"])
            settings["advanced_services_to_stop"] = selected
            
        if self._save_booster_json_safe(settings):
            print("[Booster] Custom preset auto-saved.")

    def _load_custom_preset_settings(self):
        """Load processes and services checked states from booster_settings.json."""
        try:
            settings = self._load_booster_json_safe()
            if not settings:
                return
                
            # Note: Essential tab already loads its own state via _load_essential_states
            
            # 2. Processes (Since processes are loaded dynamically, we just set the tracking set.
            #   _populate_processes_tab will read from it when it builds the list.)
            if "processes_to_close" in settings:
                if not hasattr(self, '_checked_process_names') or not self._checked_process_names:
                    self._checked_process_names = set(settings["processes_to_close"])
                
            # 3. Basic Services
            if "basic_services_to_stop" in settings and hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_service_data'):
                saved_basic = set(settings["basic_services_to_stop"])
                for i, cb in enumerate(self._basic_service_checks):
                    if i < len(self._basic_service_data):
                        svc_name = self._basic_service_data[i]["name"]
                        cb.blockSignals(True)
                        cb.setChecked(svc_name in saved_basic)
                        cb.blockSignals(False)
                if hasattr(self, '_update_basic_count'):
                    self._update_basic_count()
                        
            # 4. Advanced Services
            if "advanced_services_to_stop" in settings and hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_service_data'):
                saved_adv = set(settings["advanced_services_to_stop"])
                for i, cb in enumerate(self._advanced_service_checks):
                    if i < len(self._advanced_service_data):
                        svc_name = self._advanced_service_data[i]["name"]
                        cb.blockSignals(True)
                        cb.setChecked(svc_name in saved_adv)
                        cb.blockSignals(False)
                if hasattr(self, '_update_advanced_count'):
                    self._update_advanced_count()
                        
        except Exception as e:
            print(f"[Booster] Error loading custom preset settings: {e}")
    
    def _run_manual_boost(self):
        """Run manual boost applying optimizations from ALL 4 tabs in background thread.
        
        Boost re-applies every 60 seconds until user clicks Stop Boost.
        This ensures optimizations persist (e.g. Windows key stays disabled
        even if the OS re-enables it).
        """
        # If already boosting, stop it
        if getattr(self, '_is_boosting', False):
            print("[Boost] Stop requested by user")
            self._boost_cancel_requested = True
            self._boost_generation_id += 1
            if self.manual_boost_btn:
                self.manual_boost_btn.setText("STOPPING...")
            if self.clean_btn:
                self.clean_btn.setText("STOPPING...")
            
            # Stop the reapply timer immediately
            if hasattr(self, '_boost_reapply_timer') and self._boost_reapply_timer is not None:
                self._boost_reapply_timer.stop()
            
            # Force reset after 3 seconds if thread doesn't respond
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, self._force_boost_reset)
            return
        
        print("[Boost] Manual boost triggered - starting background thread")
        
        # Set boosting state and generation counter
        self._is_boosting = True
        self._boost_cancel_requested = False
        self._boost_generation_id += 1
        self._boost_cycle_count = 0
        
        # Change button to STOP mode with animated gradient
        if self.manual_boost_btn:
            self.manual_boost_btn.setText("STOP BOOST")
        if self.clean_btn:
            self.clean_btn.setText("STOP BOOST")
            self.clean_btn.setStyleSheet("""
                QPushButton#cleanRamButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E53935, stop:1 #B71C1C);
                    color: #ffffff;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton#cleanRamButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EF5350, stop:1 #C62828);
                }
            """)
        
        # Start animated gradient for STOP button (same as nav buttons)
        self._boost_btn_gradient_offset = 0.0
        
        # Create timer for gradient animation
        if not hasattr(self, '_boost_gradient_timer') or self._boost_gradient_timer is None:
            from PySide6.QtCore import QTimer
            self._boost_gradient_timer = QTimer(self)
            self._boost_gradient_timer.timeout.connect(self._update_boost_btn_gradient)
        self._boost_gradient_timer.start(17)  # 17ms = ~60fps
        
        # Apply initial gradient
        self._update_boost_btn_gradient()
        
        # Show overlay on tab content
        self._show_boost_overlay(True)
        
        # Create reapply timer (fires every 60 seconds to re-apply boost)
        if not hasattr(self, '_boost_reapply_timer') or self._boost_reapply_timer is None:
            from PySide6.QtCore import QTimer
            self._boost_reapply_timer = QTimer(self)
            self._boost_reapply_timer.timeout.connect(self._reapply_boost)
        
        # Run first boost immediately
        self._execute_boost_cycle()
        
        # Start the 60-second reapply timer
        self._boost_reapply_timer.start(60000)  # 60 seconds
        print("[Boost] Reapply timer started (60s interval)")
    
    def _reapply_boost(self):
        """Called every 60 seconds by the reapply timer to re-apply boost.
        
        Re-collects current checkbox state from all 4 tabs so that
        any changes the user makes mid-boost are picked up on the
        next cycle. Uses a lock to prevent overlapping boost cycles
        which can cause state corruption.
        """
        if not getattr(self, '_is_boosting', False):
            return
        if getattr(self, '_boost_cancel_requested', False):
            return
        
        # Use lock to prevent overlapping cycles (race condition fix)
        if not self._boost_lock.acquire(blocking=False):
            print("[Boost] Previous cycle still running, skipping this reapply")
            return
        
        print("[Boost] Reapply timer fired - re-applying boost")
        self._execute_boost_cycle()
    
    def _execute_boost_cycle(self):
        """Collect UI state and run one boost cycle in a background thread."""
        self._boost_cycle_count = getattr(self, '_boost_cycle_count', 0) + 1
        current_gen = getattr(self, '_boost_generation_id', 0)
        print(f"[Boost] Starting cycle #{self._boost_cycle_count} (gen #{current_gen})")
        
        # 1. Essential optimizations (always handled by _get_selected_optimizations)
        boost_data = {
            'selected_essential': self._get_selected_optimizations(),
            'process_data': [],
            'basic_service_data': [],
            'advanced_service_data': []
        }
        
        # Load config as fallback if UI is not loaded
        config_settings = {}
        need_config = not (self._process_checks and self._basic_service_checks and self._advanced_service_checks)
        if need_config:
            config_settings = self._load_booster_json_safe()

        # 2. Processes
        if self._process_checks and getattr(self, '_process_data', None):
            # UI loaded - use checkbox states
            blacklist = getattr(self, '_process_blacklist', set())
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    proc_name = self._process_data[i]['name']
                    if proc_name not in blacklist:
                        boost_data['process_data'].append(self._process_data[i])
        else:
            # UI not loaded - use config
            proc_names = config_settings.get("processes_to_close", [])
            for name in proc_names:
                boost_data['process_data'].append({'name': name, 'pids': []})

        # 3. Basic Services
        if self._basic_service_checks and getattr(self, '_basic_service_data', None):
            for i, cb in enumerate(self._basic_service_checks):
                if cb.isChecked() and i < len(self._basic_service_data):
                    boost_data['basic_service_data'].append(self._basic_service_data[i])
        else:
            svc_names = config_settings.get("basic_services_to_stop", [])
            for name in svc_names:
                boost_data['basic_service_data'].append({'name': name})

        # 4. Advanced Services
        if self._advanced_service_checks and getattr(self, '_advanced_service_data', None):
            for i, cb in enumerate(self._advanced_service_checks):
                if cb.isChecked() and i < len(self._advanced_service_data):
                    boost_data['advanced_service_data'].append(self._advanced_service_data[i])
        else:
            svc_names = config_settings.get("advanced_services_to_stop", [])
            for name in svc_names:
                boost_data['advanced_service_data'].append({'name': name})
        
        # Run in background thread
        import threading
        self._boost_thread = threading.Thread(target=self._run_boost_worker, args=(boost_data, current_gen), daemon=True)
        self._boost_thread.start()
    
    def _show_boost_overlay(self, show: bool):
        """Show/hide overlay on tab content to prevent interaction during boost."""
        if not hasattr(self, '_ram_tab_stack'):
            return
        
        # Parent overlay to the tab stack itself (covers content but not tab bar)
        parent_widget = self._ram_tab_stack
        
        if show:
            # Create overlay if not exists
            if not hasattr(self, '_boost_overlay') or self._boost_overlay is None:
                from PySide6.QtWidgets import QFrame
                self._boost_overlay = QFrame(parent_widget)
                self._boost_overlay.setObjectName("boostOverlay")
                self._boost_overlay.setStyleSheet("""
                    QFrame#boostOverlay {
                        background: rgba(0, 0, 0, 0.7);
                        border-radius: 8px;
                    }
                """)
                self._boost_overlay.setCursor(Qt.WaitCursor)
            else:
                # Re-parent overlay to ensure it's in the right parent
                self._boost_overlay.setParent(parent_widget)
            
            # Position overlay over the tab stack content area only
            self._boost_overlay.setGeometry(parent_widget.rect())
            self._boost_overlay.raise_()
            self._boost_overlay.show()
        else:
            # Hide overlay
            if hasattr(self, '_boost_overlay') and self._boost_overlay:
                self._boost_overlay.hide()
    
    def _force_boost_reset(self):
        """Force reset boost state if still in boosting/stopping state."""
        is_stopping = False
        if self.manual_boost_btn:
            is_stopping = self.manual_boost_btn.text() == "STOPPING..."
        elif self.clean_btn:
            is_stopping = self.clean_btn.text() == "STOPPING..."
            
        if getattr(self, '_is_boosting', False) or is_stopping:
            print("[Boost] Force reset after timeout")
            self._full_boost_reset()
    
    def _update_boost_btn_gradient(self):
        """Update the gradient offset for animated STOP button."""
        if not getattr(self, '_is_boosting', False):
            if hasattr(self, '_boost_gradient_timer') and self._boost_gradient_timer is not None:
                self._boost_gradient_timer.stop()
            return
        
        # OMEN gradient colors (extended for seamless loop)
        colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']
        
        # Shift offset (0.0 to 1.0) - small step for slow, smooth animation at 60fps
        self._boost_btn_gradient_offset += 0.005
        if self._boost_btn_gradient_offset >= 1.0:
            self._boost_btn_gradient_offset = 0.0
        
        offset = self._boost_btn_gradient_offset
        
        # Build gradient with offset positions
        stops = []
        num_colors = len(colors)
        for i, color in enumerate(colors):
            base_pos = i / (num_colors - 1)
            shifted_pos = (base_pos + offset) % 1.0
            stops.append((shifted_pos, color))
        
        # Sort stops by position for valid gradient
        stops.sort(key=lambda x: x[0])
        
        # Build QSS gradient string
        gradient_stops = ', '.join([f'stop:{pos:.3f} {color}' for pos, color in stops])
        
        if self.manual_boost_btn:
            self.manual_boost_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient_stops});
                color: #ffffff;
                border: 2px solid rgba(255, 91, 6, 0.8);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                text-shadow: 0 0 10px #ff5500;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
        """)
        
        if hasattr(self, 'clean_btn'):
            self.clean_btn.setStyleSheet(f"""
                QPushButton#cleanRamButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient_stops});
                    color: #ffffff;
                    border: 2px solid rgba(255, 91, 6, 0.8);
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                    text-shadow: 0 0 10px #ff5500;
                }}
                QPushButton#cleanRamButton:hover {{
                    border-color: #ffffff;
                }}
            """)
    
    def _run_boost_worker(self, boost_data, generation_id=0):
        """Worker function that runs in background thread."""
        import os
        import psutil
        import subprocess
        
        results = {
            'essential': {'success': 0, 'total': 0, 'items': []},
            'processes': {'closed': 0, 'failed': 0, 'items': []},
            'basic_services': {'started': 0, 'failed': 0, 'items': []},
            'advanced_services': {'stopped': 0, 'failed': 0, 'items': []}
        }
        
        any_selected = False
        cancelled = False
        
        try:
            # Check cancel before each major step
            if getattr(self, '_boost_cancel_requested', False) or generation_id != getattr(self, '_boost_generation_id', 0):
                cancelled = True
                raise Exception("Cancelled by user")
            
            # ========== 1. ESSENTIAL TAB ==========
            _essential_needs_elevation = []
            
            selected_essential = boost_data.get('selected_essential', [])
            if selected_essential:
                any_selected = True
                results['essential']['total'] = len(selected_essential)
                try:
                    essential_results = self._apply_essential_optimizations()
                    for name, result in essential_results.items():
                        if result.get('success', False):
                            results['essential']['success'] += 1
                            results['essential']['items'].append(f"V {name}")
                        else:
                            err = result.get('error', '')
                            if 'admin' in str(err).lower() or 'denied' in str(err).lower():
                                if 'file_sharing' in name or 'file sharing' in name.lower():
                                    _essential_needs_elevation.append({
                                        'name': 'LanmanServer',
                                        'display': 'File and Printer Sharing',
                                        'essential_key': name
                                    })
                                    print(f"[Boost] {name} needs admin — routing via scheduled task")
                                else:
                                    results['essential']['items'].append(f"X {name}")
                            else:
                                results['essential']['items'].append(f"X {name}")
                except Exception as e:
                    print(f"[Boost] Essential error: {e}")
            
            # ========== 2. PROCESSES TAB ==========
            if getattr(self, '_boost_cancel_requested', False) or generation_id != getattr(self, '_boost_generation_id', 0):
                cancelled = True
                raise Exception("Cancelled by user")

            process_data = boost_data.get('process_data', [])
            if process_data:
                any_selected = True
                process_names = [proc_info['name'] for proc_info in process_data]
                
                import native_wrapper
                boost_engine = native_wrapper.get_boost_engine()
                
                if boost_engine:
                    kill_results = boost_engine.kill_processes(process_names)
                    for r in kill_results:
                        if r.success and r.killed_pids > 0:
                            results['processes']['closed'] += 1
                            count_str = f" ({r.killed_pids} instances)" if r.total_pids > 1 else ""
                            results['processes']['items'].append(f"✓ {r.name}{count_str}")
                            print(f"[Boost] Closed process: {r.name} ({r.killed_pids}/{r.total_pids} PIDs)")
                        else:
                            results['processes']['failed'] += 1
                            reason = "access denied" if r.total_pids > 0 else "not running"
                            results['processes']['items'].append(f"✗ {r.name} ({reason})")
                            print(f"[Boost] Failed to close {r.name}")
                else:
                    # Python fallback
                    for proc_info in process_data:
                        pids = proc_info.get('pids', [proc_info.get('pid')])
                        closed_count = 0
                        failed_count = 0
                        
                        for pid in pids:
                            try:
                                p = psutil.Process(pid)
                                p.terminate()
                                p.wait(timeout=2)
                                closed_count += 1
                            except Exception:
                                failed_count += 1
                        
                        if closed_count > 0:
                            results['processes']['closed'] += 1
                            count_str = f" ({closed_count} instances)" if len(pids) > 1 else ""
                            results['processes']['items'].append(f"✓ {proc_info['name']}{count_str}")
                            print(f"[Boost] Closed process: {proc_info['name']} ({closed_count}/{len(pids)} PIDs)")
                        else:
                            results['processes']['failed'] += 1
                            results['processes']['items'].append(f"✗ {proc_info['name']} (access denied)")
                            print(f"[Boost] Failed to close {proc_info['name']}")
            
            # ========== 3 & 4. SERVICES (BASIC = START, ADVANCED = STOP) ==========
            if getattr(self, '_boost_cancel_requested', False) or generation_id != getattr(self, '_boost_generation_id', 0):
                cancelled = True
                raise Exception("Cancelled by user")

            all_services = []

            for ess_svc in _essential_needs_elevation:
                all_services.append(('essential', ess_svc))

            for svc in boost_data.get('basic_service_data', []):
                any_selected = True
                all_services.append(('basic', svc))
            for svc in boost_data.get('advanced_service_data', []):
                any_selected = True
                all_services.append(('advanced', svc))

            if all_services:
                CF_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

                def _manage_service_direct(svc_name, action="stop"):
                    try:
                        from integrations.cpu_controller import is_service_running, send_service_command
                        if is_service_running():
                            res = send_service_command({"action": "manage_service", "service_name": svc_name, "command": action})
                            if res.get("status") == "success":
                                msg = res.get("message", "")
                                if msg in ("ALREADY_STOPPED", "ALREADY_RUNNING"):
                                    return msg
                                return 'OK'
                    except Exception as e:
                        print(f"[Boost] Zero-UAC Service exception for {svc_name}: {e}")

                    try:
                        qr = subprocess.run(
                            ['sc', 'query', svc_name],
                            capture_output=True, text=True,
                            creationflags=CF_NO_WINDOW, timeout=10
                        )
                        q_out = (qr.stdout or '').upper()
                        if action == "stop":
                            if 'STOPPED' in q_out and 'START_PENDING' not in q_out and 'STOP_PENDING' not in q_out:
                                return 'ALREADY_STOPPED'
                        else:
                            if 'RUNNING' in q_out and 'START_PENDING' not in q_out and 'STOP_PENDING' not in q_out:
                                return 'ALREADY_RUNNING'

                        sr = subprocess.run(
                            ['sc', action, svc_name],
                            capture_output=True, text=True,
                            creationflags=CF_NO_WINDOW, timeout=15
                        )

                        if sr.returncode == 0:
                            return 'OK'

                        combined = ((sr.stdout or '') + (sr.stderr or '')).lower()

                        if action == "stop" and (sr.returncode == 1062 or 'not been started' in combined):
                            return 'ALREADY_STOPPED'
                        elif action == "start" and (sr.returncode == 1056 or 'already running' in combined):
                            return 'ALREADY_RUNNING'
                        elif action == "start" and (sr.returncode == 1058 or 'disabled' in combined):
                            return 'DISABLED'

                        if sr.returncode == 5 or 'access is denied' in combined or 'access denied' in combined:
                            return 'ACCESS_DENIED'

                        return 'FAIL'

                    except subprocess.TimeoutExpired:
                        return 'FAIL'
                    except Exception:
                        return 'FAIL'

                for cat, svc in all_services:
                    svc_name = svc['name']
                    display  = svc.get('display', svc_name)

                    act = 'start' if cat == 'basic' else 'stop'
                    st = _manage_service_direct(svc_name, action=act)
                    ok = st in ('OK', 'ALREADY_STOPPED', 'ALREADY_RUNNING')

                    if cat == 'essential':
                        if ok:
                            results['essential']['success'] += 1
                            results['essential']['items'].append(f'V {display}')
                        else:
                            reason = 'access denied' if st == 'ACCESS_DENIED' else 'failed'
                            results['essential']['items'].append(f'X {display} ({reason})')
                    elif cat == 'basic':
                        if ok:
                            results['basic_services']['started'] += 1
                            results['basic_services']['items'].append(f'V {display}')
                        else:
                            reason = 'disabled' if st == 'DISABLED' else ('access denied' if st == 'ACCESS_DENIED' else 'failed')
                            results['basic_services']['items'].append(f'X {display} ({reason})')
                    else: # advanced
                        if ok:
                            results['advanced_services']['stopped'] += 1
                            results['advanced_services']['items'].append(f'V {display}')
                        else:
                            reason = 'access denied' if st == 'ACCESS_DENIED' else 'failed'
                            results['advanced_services']['items'].append(f'X {display} ({reason})')

            # ========== SHOW RESULTS ==========
            if not any_selected:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._boost_complete(None, "No Items Selected", 
                    "Please select at least one item from any tab\n(Essential, Processes, Basic, or Advanced).", 0, generation_id))
                return
            
            # Build summary message
            msg_parts = []
            
            if results['essential']['total'] > 0:
                msg_parts.append(f"🔧 Essential: {results['essential']['success']}/{results['essential']['total']}")
            
            proc_total = results['processes']['closed'] + results['processes']['failed']
            if proc_total > 0:
                msg_parts.append(f"⚡ Processes closed: {results['processes']['closed']}/{proc_total}")
            
            basic_total = results['basic_services']['started'] + results['basic_services']['failed']
            if basic_total > 0:
                msg_parts.append(f"📦 Basic services started: {results['basic_services']['started']}/{basic_total}")
            
            adv_total = results['advanced_services']['stopped'] + results['advanced_services']['failed']
            if adv_total > 0:
                msg_parts.append(f"⚠️ Advanced services stopped: {results['advanced_services']['stopped']}/{adv_total}")
            
            summary = "\n".join(msg_parts)
            
            total_failed = (
                (results['essential']['total'] - results['essential']['success']) +
                results['processes']['failed'] +
                results['basic_services']['failed'] +
                results['advanced_services']['failed']
            )
            
            print(f"[Boost] Complete - {summary}")
            
            # Schedule UI update in main thread safely using Signal
            self.boost_completed_signal.emit(results, summary, "", total_failed, generation_id)
                
        except Exception as e:
            print(f"[Boost] Error: {e}")
            self.boost_completed_signal.emit({}, "", str(e), 0, generation_id)
        finally:
            # Release boost lock safely
            try:
                if self._boost_lock.locked():
                    self._boost_lock.release()
            except RuntimeError:
                pass
    
    @Slot(dict, str, str, int, int)
    def _boost_complete_safe(self, results, summary, error, total_failed, generation_id=0):
        """Wrapper strictly for cross-thread calls"""
        self._boost_complete(results, summary, error, total_failed, generation_id)
        
    def _boost_complete(self, results, summary, error, total_failed=0, generation_id=0):
        """Called in main thread after a single boost cycle completes."""
        if generation_id != getattr(self, '_boost_generation_id', 0):
            print(f"[Boost] Discarding stale completion signal from generation #{generation_id} (current #{getattr(self, '_boost_generation_id', 0)})")
            return

        cycle = getattr(self, '_boost_cycle_count', 1)
        print(f"[Boost] Cycle #{cycle} complete - error={error}, summary={summary}")
        
        # Handle cancel / stop case: full reset
        if error and "Cancelled" in str(error):
            print("[Boost] Boost was cancelled by user")
            self._full_boost_reset()
            return
        
        # Handle "No items selected" on first cycle: full reset
        if error and summary and "No Items Selected" in str(summary):
            self._full_boost_reset()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Items Selected", error)
            return
        
        # Handle unexpected error: full reset
        if error:
            self._full_boost_reset()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Boost Error", f"An error occurred:\n{error}")
            return
        
        # -- Success path: log results, send notification, but keep boost active --
        if cycle == 1:
            # Check if user enabled notifications
            should_notify = True
            if hasattr(self, 'notify_boost_cb'):
                should_notify = self.notify_boost_cb.isChecked()
                
            if should_notify:
                try:
                    from PySide6.QtWidgets import QSystemTrayIcon, QApplication
                    from PySide6.QtGui import QIcon

                    tray = None
                    main_window = self.window()
                    if hasattr(main_window, 'tray_icon') and main_window.tray_icon:
                        tray = main_window.tray_icon

                    if tray is None:
                        for widget in QApplication.topLevelWidgets():
                            if hasattr(widget, 'tray_icon') and widget.tray_icon:
                                tray = widget.tray_icon
                                break

                    if tray is None:
                        if not hasattr(self, '_boost_temp_tray') or self._boost_temp_tray is None:
                            self._boost_temp_tray = QSystemTrayIcon(self)
                            app_icon = QApplication.windowIcon()
                            if not app_icon.isNull():
                                self._boost_temp_tray.setIcon(app_icon)
                            else:
                                import os
                                ui_icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons")
                                icon_path = os.path.join(ui_icons_dir, "helxtats-icon.png")
                                if not os.path.exists(icon_path):
                                    icon_path = os.path.join(ui_icons_dir, "helxtats_icon.png")
                                if os.path.exists(icon_path):
                                    self._boost_temp_tray.setIcon(QIcon(icon_path))
                        self._boost_temp_tray.show()
                        tray = self._boost_temp_tray

                    notif_msg = summary if summary else "Optimizations applied."
                    icon_type = QSystemTrayIcon.Information if total_failed == 0 else QSystemTrayIcon.Warning
                    
                    tray.show()
                    tray.showMessage("Boosting...", notif_msg, icon_type, 5000)
                    print(f"[Boost] Windows Native Notification sent: 'Boosting...' | {notif_msg}")

                except Exception as e:
                    print(f"[Boost] Windows Native Notification error: {e}")
        
        # Refresh processes list after closing some
        if results and results.get('processes', {}).get('closed', 0) > 0:
            self._populate_processes_tab()
        
        # Refresh service status labels after starting/stopping services
        if results and (results.get('basic_services', {}).get('started', 0) > 0 or results.get('advanced_services', {}).get('stopped', 0) > 0):
            try:
                self._refresh_service_statuses()
            except Exception as e:
                print(f"[Boost] Service status refresh error: {e}")
        
        print(f"[Boost] Cycle #{cycle} done. Next reapply in 60s (boost stays active).")
        
        print(f"[Boost] Cycle #{cycle} done. Next reapply in 60s (boost stays active).")

    def _full_boost_reset(self):
        """Fully reset boost state: stop timers, hide overlay, reset button."""
        self._is_boosting = False
        self._boost_cancel_requested = False
        self._boost_generation_id += 1
        
        # Stop reapply timer
        if hasattr(self, '_boost_reapply_timer') and self._boost_reapply_timer:
            self._boost_reapply_timer.stop()
            print("[Boost] Reapply timer stopped")
        
        # Stop gradient animation timer
        if hasattr(self, '_boost_gradient_timer') and self._boost_gradient_timer:
            self._boost_gradient_timer.stop()
        
        # Hide overlay
        self._show_boost_overlay(False)
        
        # Reset button style and text
        try:
            if self.manual_boost_btn:
                self.manual_boost_btn.setEnabled(True)
                self.manual_boost_btn.setText("MANUAL BOOST")
                self.manual_boost_btn.setStyleSheet("""
                    QPushButton {
                        background: #333;
                        color: #e0e0e0;
                        border: 1px solid #555;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background: #444;
                        border-color: #FF5B06;
                    }
                """)
                print("[Boost] Button reset to MANUAL BOOST")
                
            if self.clean_btn:
                self.clean_btn.setText("MANUAL BOOST")
                self.clean_btn.setEnabled(True)
                self.clean_btn.setStyleSheet("""
                    QPushButton#cleanRamButton {
                        background: #333;
                        color: #e0e0e0;
                        border: 1px solid #555;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton#cleanRamButton:hover {
                        background: #444;
                        border-color: #FF5B06;
                    }
                """)
        except Exception as e:
            print(f"[Boost] Error resetting button: {e}")

    def closeEvent(self, event):
        """Cleanup boost threads, timers, and signals on widget closure."""
        try:
            self._full_boost_reset()
            if hasattr(self, '_update_timer') and self._update_timer:
                self._update_timer.stop()
        except Exception as e:
            print(f"[Hardware] Error during closeEvent: {e}")
        super().closeEvent(event)
    
    # ============================================
    # EMBEDDED RAM TAB METHODS
    # ============================================
    
    def _refresh_service_statuses(self):
        """Re-query and update service status labels in the Basic/Advanced tables.
        
        Uses `sc query` (no admin needed) to get the current state of each
        service, then updates the Status column (column 2) in the table.
        Called after a boost cycle stops services so the UI reflects reality.
        """
        from RamCleanerPresetDialog import BASIC_SERVICES, ADVANCED_SERVICES, get_service_status
        
        # Refresh basic table
        if hasattr(self, '_basic_table') and hasattr(self, '_basic_service_data'):
            for idx, svc in enumerate(self._basic_service_data):
                if idx < self._basic_table.rowCount():
                    status = get_service_status(svc['name'])
                    item = self._basic_table.item(idx, 2)
                    if item:
                        item.setText(status)
                        color = "#4ade80" if status == "Running" else "#888888"
                        item.setForeground(QColor(color))
        
        # Refresh advanced table
        if hasattr(self, '_advanced_table') and hasattr(self, '_advanced_service_data'):
            for idx, svc in enumerate(self._advanced_service_data):
                if idx < self._advanced_table.rowCount():
                    status = get_service_status(svc['name'])
                    item = self._advanced_table.item(idx, 2)
                    if item:
                        item.setText(status)
                        color = "#4ade80" if status == "Running" else "#888888"
                        item.setForeground(QColor(color))
        
        print("[Boost] Service statuses refreshed in UI")
    
    def _switch_ram_tab(self, index: int):
        """Switch to specified RAM tab (with lazy loading)."""
        if 0 <= index < 4:
            subtabs_created = getattr(self, '_ram_subtabs_created', [True]*4)
            if not subtabs_created[index]:
                creators = {
                    1: self._create_processes_tab,
                    2: self._create_basic_services_tab,
                    3: self._create_advanced_services_tab
                }
                if index in creators:
                    new_tab = creators[index]()
                    old_widget = self._ram_tab_stack.widget(index)
                    self._ram_tab_stack.removeWidget(old_widget)
                    old_widget.deleteLater()
                    self._ram_tab_stack.insertWidget(index, new_tab)
                    self._ram_subtabs_created[index] = True
                    self._load_custom_preset_settings()

            self._current_ram_tab = index
            self._ram_tab_stack.setCurrentIndex(index)
            self._update_ram_tab_buttons()
        
        # Refresh overlay if boosting is active
        if getattr(self, '_is_boosting', False):
            self._show_boost_overlay(True)
        
        # Update description
        descriptions = [
            "Essential items for CPU and memory optimization.",
            "Background processes that can be closed to free RAM.",
            "Basic Windows Services that will be started to optimize performance for gaming.",
            "Advanced Windows Services. Use with caution."
        ]
        self._ram_tab_desc.setText(descriptions[index])
    
    def _update_ram_tab_buttons(self):
        """Update tab button styles matching macroSubNav style 100%."""
        for i, btn in enumerate(self._ram_tab_btns):
            if i == self._current_ram_tab:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 91, 6, 0.08);
                        color: #FF5B06;
                        border: none;
                        border-bottom: 2px solid #FF5B06;
                        border-radius: 6px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        font-weight: 700;
                        padding-top: 4px;
                        padding-bottom: 2px;
                        padding-left: 14px;
                        padding-right: 14px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #888888;
                        border: none;
                        border-bottom: 2px solid transparent;
                        border-radius: 6px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        font-weight: 500;
                        padding-top: 4px;
                        padding-bottom: 2px;
                        padding-left: 14px;
                        padding-right: 14px;
                    }
                    QPushButton:hover {
                        color: #ffffff;
                        background: rgba(255, 91, 6, 0.12);
                        border-radius: 6px;
                    }
                """)
    
    def _refresh_ram_tab_content(self):
        """Refresh content of current RAM tab."""
        if self._current_ram_tab == 1:  # Processes tab
            self._populate_processes_tab()
        print(f"[RAM] Refreshed tab {self._current_ram_tab}")
    
    def _update_total_items_count(self):
        """Update the items_label with total selected items from ALL 4 tabs (UI checkboxes or saved settings fallback per sub-tab)."""
        total = 0
        saved_settings = self._load_booster_json_safe()
        
        # 1. Essential tab
        if hasattr(self, '_essential_checks') and self._essential_checks:
            total += sum(1 for cb in self._essential_checks if cb.isChecked())
        else:
            if "essential_optimizations" in saved_settings:
                total += len(saved_settings["essential_optimizations"])
            else:
                from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
                total += len(ESSENTIAL_OPTIMIZATIONS) - 2  # Default essentials except 0 and 7
                
        # 2. Processes tab
        if hasattr(self, '_process_checks') and self._process_checks:
            total += sum(1 for cb in self._process_checks if cb.isChecked())
        else:
            total += len(saved_settings.get("processes_to_close", []))
            
        # 3. Basic Services tab
        if hasattr(self, '_basic_service_checks') and self._basic_service_checks:
            total += sum(1 for cb in self._basic_service_checks if cb.isChecked())
        else:
            total += len(saved_settings.get("basic_services_to_stop", []))
            
        # 4. Advanced Services tab
        if hasattr(self, '_advanced_service_checks') and self._advanced_service_checks:
            total += sum(1 for cb in self._advanced_service_checks if cb.isChecked())
        else:
            total += len(saved_settings.get("advanced_services_to_stop", []))
            
        # Update the Booster tab label
        text = f"{total} items to be optimized" if total != 1 else "1 item to be optimized"
        if total == 0:
            text = "0 items to be optimized"
        
        if hasattr(self, 'items_label'):
            self.items_label.setText(text)

        # Sync Quick Setup tab items label (mirrors Booster tab)
        if hasattr(self, 'qs_items_label'):
            self.qs_items_label.setText(text)
    
    def _create_essential_tab(self) -> QWidget:
        """Create Essential Optimizations tab content matching reference design."""
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        page = QWidget()
        page.setObjectName("essentialPage")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # Header row with Select All, Name, Description columns
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName("essentialSelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet("""
            QFrame#essentialSelectRow {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        
        self._essential_select_all = AnimatedCheckBox("Select all")
        self._essential_select_all.setObjectName("essentialSelectAll")
        self._essential_select_all.setStyleSheet("color: #e0e0e0; font-size: 11px; background: transparent;")
        self._essential_select_all.toggled.connect(self._on_essential_select_all)
        select_layout.addWidget(self._essential_select_all)
        
        self._essential_count_label = QLabel(f"0/{len(ESSENTIAL_OPTIMIZATIONS)}")
        self._essential_count_label.setObjectName("essentialCountLabel")
        self._essential_count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        select_layout.addWidget(self._essential_count_label)
        select_layout.addStretch()
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        table = QTableWidget()
        table.setObjectName("essentialTable")
        table.setColumnCount(3)
        table.setRowCount(len(ESSENTIAL_OPTIMIZATIONS))
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "Name", "Description"])
        

        # Essential tab Column widths
        table.setColumnWidth(0, 50)   # Checkbox (#) - fixed
        table.setColumnWidth(1, 350)  # Name
        table.horizontalHeader().setStretchLastSection(True)  # Description stretches
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setMinimumSectionSize(50)
        
        # Styling
        table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::item:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QHeaderView::section {
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }
            QHeaderView::section:hover {
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 3px;
            }
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Populate table
        self._essential_checks = []
        self._essential_table = table
        
        for idx, item in enumerate(ESSENTIAL_OPTIMIZATIONS):
            # Column 0: Checkbox
            cb_widget = QWidget()
            cb_widget.setObjectName(f"essentialCheckWidget_{idx}")
            cb_widget.setStyleSheet("background: transparent;")
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            
            cb = AnimatedCheckBox()
            cb.setObjectName(f"essentialCheck_{idx}")
            cb.toggled.connect(self._update_essential_count)
            cb.toggled.connect(self._save_essential_states)
            cb.toggled.connect(self._update_total_items_count)
            # Autosave preset on every toggle so user never needs to manually save
            cb.toggled.connect(self._save_custom_preset)
            self._essential_checks.append(cb)
            cb_layout.addWidget(cb)
            table.setCellWidget(idx, 0, cb_widget)
            
            # Column 1: Name
            name_item = QTableWidgetItem(item["name"])
            name_item.setForeground(QColor("#e0e0e0"))
            table.setItem(idx, 1, name_item)
            
            # Column 2: Description
            desc_item = QTableWidgetItem(item["description"])
            desc_item.setForeground(QColor("#666666"))
            table.setItem(idx, 2, desc_item)
        
        page_layout.addWidget(table, 1)
        
        # Enable smooth scrolling for this table
        self._essential_table_smoother = SmoothTableWidget(table)
        
        
        # Bottom bar with Reset button
        bottom = QFrame()
        bottom.setObjectName("essentialBottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet("""
            QFrame#essentialBottom {
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName("essentialResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_essential_selections)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Load saved checkbox states
        self._load_essential_states()
        self._load_booster_settings()
        
        # Update total items count in left panel
        self._update_total_items_count()
        
        return page
    
    def _on_essential_select_all(self, checked: bool):
        """Handle Select All checkbox for essential tab."""
        for cb in self._essential_checks:
            cb.setChecked(checked)
        self._update_essential_count()
    
    def _sort_essential_list(self):
        """Sort the essential optimizations list by name."""
        # Toggle sort order
        self._essential_sort_asc = not self._essential_sort_asc
        
        # Update header text
        arrow = "▲" if self._essential_sort_asc else "▼"
        self._essential_name_header.setText(f"Name {arrow}")
        
        # Get container layout
        container = self._essential_container
        layout = container.layout()
        
        # Collect all row widgets with their indices and names
        rows = []
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget:
                # Find the name label in this row
                name_label = widget.findChild(QLabel, "")  # Get first QLabel
                if name_label:
                    rows.append((widget, name_label.text(), i))
        
        # Sort rows by name
        rows.sort(key=lambda x: x[1].lower(), reverse=not self._essential_sort_asc)
        
        # Reorder widgets
        for idx, (widget, name, orig_idx) in enumerate(rows):
            layout.removeWidget(widget)
        
        for idx, (widget, name, orig_idx) in enumerate(rows):
            layout.insertWidget(idx, widget)
        
        print(f"[Essential] Sorted by name {'A→Z' if self._essential_sort_asc else 'Z→A'}")
    
    def _update_essential_count(self):
        """Update essential items selection count."""
        selected = sum(1 for cb in self._essential_checks if cb.isChecked())
        total = len(self._essential_checks)
        self._essential_count_label.setText(f"{selected}/{total}")
        
        # Update select all checkbox state
        self._essential_select_all.blockSignals(True)
        self._essential_select_all.setChecked(selected == total and total > 0)
        self._essential_select_all.blockSignals(False)
    
    def _reset_essential_selections(self):
        """Reset all essential selections to default.
        Default: All checked EXCEPT clear_clipboard (idx 0) and disable_winkey (idx 7)
        """
        # Items that should be UNCHECKED by default
        unchecked_by_default = [0, 7]  # clear_clipboard, disable_winkey
        
        for idx, cb in enumerate(self._essential_checks):
            cb.setChecked(idx not in unchecked_by_default)
        
        self._update_essential_count()
        self._save_essential_states()
    
    def _save_essential_states(self):
        """Save essential checkbox states to separate config file."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Read current settings
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            
            # Get selected optimization IDs
            from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
            selected = []
            for i, cb in enumerate(self._essential_checks):
                if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                    selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
            
            # Save to settings
            settings["essential_optimizations"] = selected
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            
            print(f"[Booster] Saved essential states: {selected}")
            
        except Exception as e:
            print(f"[Booster] Error saving essential states: {e}")
    
    def _save_booster_settings(self):
        """Save booster checkbox settings (notify, auto-update)."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Read current settings
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            
            # Save checkbox states
            if hasattr(self, 'notify_boost_cb'):
                settings["notify_when_boosting"] = self.notify_boost_cb.isChecked()
            if hasattr(self, 'auto_update_cb'):
                settings["auto_update_on_profile"] = self.auto_update_cb.isChecked()
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            
        except Exception as e:
            print(f"[Booster] Error saving booster settings: {e}")
    
    def _load_booster_settings(self):
        """Load booster checkbox settings (notify, auto-update)."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # Restore checkbox states
                if hasattr(self, 'notify_boost_cb'):
                    self.notify_boost_cb.setChecked(settings.get("notify_when_boosting", True))
                if hasattr(self, 'auto_update_cb'):
                    self.auto_update_cb.setChecked(settings.get("auto_update_on_profile", False))
                    
        except Exception as e:
            print(f"[Booster] Error loading booster settings: {e}")
    
    def _load_essential_states(self):
        """Load essential checkbox states from config file, or apply defaults."""
        try:
            import json
            from launcher import APPDATA_DIR
            from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Default: all checked EXCEPT clear_clipboard (idx 0) and disable_winkey (idx 7)
            unchecked_by_default = [0, 7]
            
            if not os.path.exists(settings_path):
                # Apply defaults on first load
                for idx, cb in enumerate(self._essential_checks):
                    cb.blockSignals(True)
                    cb.setChecked(idx not in unchecked_by_default)
                    cb.blockSignals(False)
                self._update_essential_count()
                return
            
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            selected = settings.get("essential_optimizations", None)
            
            if selected is None:
                # No saved settings, apply defaults
                for idx, cb in enumerate(self._essential_checks):
                    cb.blockSignals(True)
                    cb.setChecked(idx not in unchecked_by_default)
                    cb.blockSignals(False)
                self._update_essential_count()
                return
            
            # Set checkbox states from saved
            for i, cb in enumerate(self._essential_checks):
                if i < len(ESSENTIAL_OPTIMIZATIONS):
                    opt_id = ESSENTIAL_OPTIMIZATIONS[i]["id"]
                    cb.blockSignals(True)
                    cb.setChecked(opt_id in selected)
                    cb.blockSignals(False)
            
            self._update_essential_count()
            print(f"[Booster] Loaded essential states: {selected}")
            
        except Exception as e:
            print(f"[Booster] Error loading essential states: {e}")
    
    def _get_selected_optimizations(self) -> list:
        """Get list of selected optimization IDs."""
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        # If UI not loaded yet, return what's in the config file
        if not self._essential_checks:
            try:
                import json
                from launcher import APPDATA_DIR
                settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    return settings.get("essential_optimizations", [])
                
                # Default fallback if no file (all except 0 and 7)
                return [ESSENTIAL_OPTIMIZATIONS[i]["id"] for i in range(len(ESSENTIAL_OPTIMIZATIONS)) if i not in [0, 7]]
            except Exception:
                return []
            
        selected = []
        for i, cb in enumerate(self._essential_checks):
            if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
        return selected
    
    def _apply_essential_optimizations(self, game_exe: str = None) -> dict:
        """
        Apply selected essential optimizations.
        
        Args:
            game_exe: Optional game executable name for priority setting
        
        Returns dict with results for each optimization.
        """
        from essential_optimizations import get_optimizer
        
        optimizer = get_optimizer()
        selected = self._get_selected_optimizations()
        results = {}
        
        print(f"[Essential] Applying optimizations: {selected}")
        
        # Memory Boost
        if "memory_boost" in selected:
            results["memory_boost"] = optimizer.memory_boost()
        
        # Set Game Priority (only when game is running)
        if "set_game_priority" in selected:
            if game_exe:
                results["set_game_priority"] = optimizer.set_game_priority(game_exe, "high")
            else:
                # Skip but mark as success (no game to boost)
                results["set_game_priority"] = {"success": True, "skipped": True}
                print("[EssentialOpt] Set Game Priority: skipped (no game running)")
        
        # Disable Windows Key
        if "disable_winkey" in selected:
            results["disable_winkey"] = optimizer.disable_windows_key()
        
        # Clear Clipboard
        if "clear_clipboard" in selected:
            results["clear_clipboard"] = optimizer.clear_clipboard()
        
        # Disable Game Bar
        if "disable_game_bar" in selected:
            results["disable_game_bar"] = optimizer.disable_game_bar()
        
        # Disable Game Mode
        if "disable_game_mode" in selected:
            results["disable_game_mode"] = optimizer.disable_game_mode()
        
        # Disable DVR
        if "disable_dvr" in selected:
            results["disable_dvr"] = optimizer.disable_dvr()
        
        # Disable Updates
        if "disable_updates" in selected:
            results["disable_updates"] = optimizer.disable_updates()
        
        # Disable Core Parking
        if "disable_core_parking" in selected:
            results["disable_core_parking"] = optimizer.disable_core_parking()
        
        # Disable File Sharing
        if "disable_file_sharing" in selected:
            results["disable_file_sharing"] = optimizer.disable_file_sharing()
        
        return results
    
    def _restore_essential_optimizations(self, game_exe: str = None):
        """Restore settings changed by essential optimizations."""
        from essential_optimizations import get_optimizer
        
        optimizer = get_optimizer()
        selected = self._get_selected_optimizations()
        
        # Re-enable Windows Key
        if "disable_winkey" in selected:
            optimizer.enable_windows_key()
        
        # Restore game priority
        if "set_game_priority" in selected and game_exe:
            optimizer.restore_game_priority(game_exe)
        
        # Re-enable Game Bar
        if "disable_game_bar" in selected:
            optimizer.enable_game_bar()
        
        # Re-enable Game Mode
        if "disable_game_mode" in selected:
            optimizer.enable_game_mode()
        
        # Re-enable DVR
        if "disable_dvr" in selected:
            optimizer.enable_dvr()
        
        # Re-enable Updates
        if "disable_updates" in selected:
            optimizer.enable_updates()
        
        # Re-enable Core Parking
        if "disable_core_parking" in selected:
            optimizer.enable_core_parking()
        
        # Re-enable File Sharing
        if "disable_file_sharing" in selected:
            optimizer.enable_file_sharing()
        
        print("[Essential] Restored optimizations")

    def _create_processes_tab(self) -> QWidget:
        """Create Processes tab content matching reference design."""
        page = QWidget()
        page.setObjectName("processesPage")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # Warning banner at top
        warning = QFrame()
        warning.setObjectName("processesWarning")
        warning.setFixedHeight(50)
        warning.setStyleSheet("""
            QFrame#processesWarning {
                background: rgba(255, 91, 6, 0.15);
                border-bottom: 1px solid rgba(255, 91, 6, 0.3);
            }
        """)
        warning_layout = QHBoxLayout(warning)
        warning_layout.setContentsMargins(15, 10, 15, 10)
        
        warning_text = QLabel("Selected background processes will be automatically closed during Boost. "
                              "Terminating some processes may disrupt the normal operation of your PC. "
                              "We recommend only selecting the ones you are familiar with.")
        warning_text.setObjectName("processesWarningText")
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #cccccc; font-size: 10px; background: transparent;")
        warning_layout.addWidget(warning_text)
        
        page_layout.addWidget(warning)
        
        # Header row
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName("processesSelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet("""
            QFrame#processesSelectRow {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        select_layout.setAlignment(Qt.AlignVCenter)
        
        self._processes_select_all = AnimatedCheckBox("Select all")
        self._processes_select_all.setObjectName("processesSelectAll")
        self._processes_select_all.setStyleSheet("color: #e0e0e0; font-size: 11px; background: transparent;")
        self._processes_select_all.toggled.connect(self._on_processes_select_all)
        select_layout.addWidget(self._processes_select_all, alignment=Qt.AlignVCenter)
        
        self._processes_count_label = QLabel("0/0")
        self._processes_count_label.setObjectName("processesCountLabel")
        self._processes_count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        select_layout.addWidget(self._processes_count_label, alignment=Qt.AlignVCenter)
        
        select_layout.addStretch()
        
        # Manual Refresh Icon Button (Far right corner of processesSelectRow, strictly 30x30 outer bounds, vertically centered)
        self._processes_refresh_btn = QPushButton()
        self._processes_refresh_btn.setObjectName("processesRefreshBtn")
        self._processes_refresh_btn.setFixedSize(30, 30)
        self._processes_refresh_btn.setMinimumSize(30, 30)
        self._processes_refresh_btn.setMaximumSize(30, 30)
        self._processes_refresh_btn.setCursor(Qt.PointingHandCursor)
        self._processes_refresh_btn.setToolTip("Refresh process list manually")
        self._processes_refresh_btn.clicked.connect(self._on_manual_processes_refresh)
        
        refresh_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "refresh.png")
        if os.path.exists(refresh_icon_path):
            from PySide6.QtCore import QSize
            self._processes_refresh_btn.setIcon(QIcon(refresh_icon_path))
            self._processes_refresh_btn.setIconSize(QSize(18, 18))
            
        self._processes_refresh_btn.setStyleSheet("""
            QPushButton#processesRefreshBtn {
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                width: 28px;
                height: 28px;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton#processesRefreshBtn:hover {
                background: rgba(255, 91, 6, 0.2);
                border-color: #FF5B06;
            }
            QPushButton#processesRefreshBtn:pressed {
                background: rgba(255, 91, 6, 0.35);
            }
        """)
        select_layout.addWidget(self._processes_refresh_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        self._processes_sort_column = "memory"  # Default sort by memory
        self._processes_sort_asc = False  # Default descending (highest first)
        
        table = QTableWidget()
        table.setObjectName("processesTable")
        table.setColumnCount(5)  # Checkbox, Icon, Name, Memory, Blacklist
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(False)  # Disable built-in sorting, we handle it manually
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "", "Name", "Memory", "Blacklist"])
        
        # Column widths - generous sizing
        table.setColumnWidth(0, 50)   # Checkbox (#)
        table.setColumnWidth(1, 50)   # Icon
        table.setColumnWidth(2, 200)  # Name
        table.setColumnWidth(3, 100)  # Memory
        table.setColumnWidth(4, 80)   # Blacklist
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)  # Icon fixed
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Name stretches to fill remaining
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)  # Memory fixed
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)  # Blacklist fixed
        table.horizontalHeader().setMinimumSectionSize(35)
        
        # Custom sort handler for header clicks
        table.horizontalHeader().sectionClicked.connect(self._on_processes_header_clicked)
        
        # Styling
        table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::item:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QHeaderView::section {
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }
            QHeaderView::section:hover {
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 3px;
            }
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Store table reference
        self._processes_table = table
        
        page_layout.addWidget(table, 1)
        
        # Enable smooth scrolling for this table
        self._processes_table_smoother = SmoothTableWidget(table)
        
        
        # Bottom bar with Reset button (matching Essential tab style)
        bottom = QFrame()
        bottom.setObjectName("processesBottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet("""
            QFrame#processesBottom {
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName("processesResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_processes_selection)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Populate processes list asynchronously/deferred to keep tab creation < 10ms
        from PySide6.QtCore import QTimer
        QTimer.singleShot(20, self._populate_processes_tab)
        
        return page
    
    def _on_processes_select_all(self, checked: bool):
        """Handle Select All checkbox for processes tab."""
        for cb in self._process_checks:
            cb.setChecked(checked)
        self._update_processes_count()
    
    def _update_processes_count(self):
        """Update processes selection count."""
        selected = sum(1 for cb in self._process_checks if cb.isChecked())
        total = len(self._process_checks)
        self._processes_count_label.setText(f"{selected}/{total}")
        
        # Update select all checkbox state
        self._processes_select_all.blockSignals(True)
        self._processes_select_all.setChecked(selected == total and total > 0)
        self._processes_select_all.blockSignals(False)
    
    def _on_processes_header_clicked(self, column: int):
        """Handle header click for sorting."""
        if column == 2:  # Name column
            self._sort_processes("name")
        elif column == 3:  # Memory column
            self._sort_processes("memory")
    
    def _sort_processes(self, column: str):
        """Sort processes by column."""
        if self._processes_sort_column == column:
            self._processes_sort_asc = not self._processes_sort_asc
        else:
            self._processes_sort_column = column
            self._processes_sort_asc = column == "name"  # Name ascending by default, memory descending
        
        # Update header indicators via QTableWidget
        name_arrow = " ▲" if self._processes_sort_column == "name" and self._processes_sort_asc else " ▼" if self._processes_sort_column == "name" else ""
        mem_arrow = " ▲" if self._processes_sort_column == "memory" and self._processes_sort_asc else " ▼" if self._processes_sort_column == "memory" else ""
        
        # Update table headers with sort arrows
        self._processes_table.setHorizontalHeaderLabels(["#", "", f"Name{name_arrow}", f"Memory{mem_arrow}", "Blacklist"])
        
        # Re-populate with new sorting
        self._populate_processes_tab()
    
    def _refresh_processes_list(self):
        """Refresh the processes list."""
        self._populate_processes_tab()

    def _on_manual_processes_refresh(self):
        """Manual refresh button click handler with visual feedback."""
        if hasattr(self, '_processes_refresh_btn'):
            self._processes_refresh_btn.setEnabled(False)
            
        self._populate_processes_tab()
        
        if hasattr(self, '_processes_refresh_btn'):
            QTimer.singleShot(300, lambda: self._processes_refresh_btn.setEnabled(True) if hasattr(self, '_processes_refresh_btn') else None)

    def _smart_update_processes_tab(self):
        """Smart in-place memory update executed every 3 seconds.
        
        Updates RAM numbers on existing QTableWidgetItems without destroying widgets.
        Only performs full table rebuild if process list items change.
        """
        if not hasattr(self, '_processes_table') or self._processes_table.rowCount() == 0:
            self._populate_processes_tab()
            return
            
        import psutil
        
        PROCESS_BLACKLIST = {
            'pwsh.exe', 'powershell.exe', 'cmd.exe', 'conhost.exe',
            'regedit.exe', 'registry', 'reg.exe',
            'svchost.exe', 'csrss.exe', 'smss.exe', 'wininit.exe',
            'services.exe', 'lsass.exe', 'winlogon.exe',
            'dwm.exe', 'explorer.exe', 'system', 'system idle process',
            'searchindexer.exe', 'searchhost.exe', 'runtimebroker.exe',
            'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
            'dllhost.exe', 'ctfmon.exe', 'textinputhost.exe',
            'shellexperiencehost.exe', 'startmenuexperiencehost.exe',
            'applicationframehost.exe', 'securityhealthsystray.exe',
            'helxaid.exe',
        }
        
        process_groups = {}
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info = proc.info
                mem = info['memory_info'].rss if info['memory_info'] else 0
                name = info['name']
                pid = info['pid']
                
                if not name or name.lower() in PROCESS_BLACKLIST:
                    continue
                    
                if name in process_groups:
                    process_groups[name]['pids'].append(pid)
                    process_groups[name]['memory'] += mem
                else:
                    process_groups[name] = {'pids': [pid], 'memory': mem}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        active_procs = {}
        for name, data in process_groups.items():
            if data['memory'] > 50 * 1024 * 1024:  # > 50 MB
                active_procs[name] = data
                
        table = self._processes_table
        existing_row_names = {}
        for r in range(table.rowCount()):
            item = table.item(r, 2)
            if item:
                existing_row_names[item.text()] = r
                
        current_names = set(active_procs.keys())
        existing_names = set(existing_row_names.keys())
        
        # If process list items changed (new app opened or app closed), perform full refresh
        if current_names != existing_names:
            self._populate_processes_tab()
            return
            
        # IN-PLACE MEMORY UPDATE (0% widget destruction, 0.05ms execution, ZERO PC FRAME DROP!)
        table.setUpdatesEnabled(False)
        try:
            for name, r in existing_row_names.items():
                if name in active_procs:
                    mem = active_procs[name]['memory']
                    mem_str = f"{mem / (1024**3):.2f} GB" if mem >= 1024**3 else f"{mem / (1024**2):.0f} MB"
                    
                    mem_item = table.item(r, 3)
                    if mem_item and mem_item.text() != mem_str:
                        mem_item.setText(mem_str)
                        mem_item.setData(Qt.UserRole, mem)
                    
                    if r < len(self._process_data):
                        self._process_data[r]['pids'] = active_procs[name]['pids']
        finally:
            table.setUpdatesEnabled(True)
    
    def _reset_processes_selection(self):
        """Reset all process selections."""
        for cb in self._process_checks:
            cb.setChecked(False)
        self._update_processes_count()
    
    def _get_process_icon(self, exe_path: str, process_name: str = "") -> QPixmap:
        """Extract icon from exe file, cache to APPDATA/icon_cache/, and return as QPixmap.
        
        Check RAM cache first, then APPDATA disk cache. If miss, extract 1x and save to APPDATA.
        Uses UI Icons/default_process.png scaled with KeepAspectRatio as fallback.
        """
        from PySide6.QtGui import QPixmap, QImage
        from PySide6.QtCore import Qt
        import tempfile
        import io
        
        # Initialize in-memory cache if not exists
        if not hasattr(self, '_process_icon_cache'):
            self._process_icon_cache = {}
        
        cache_key = (process_name.lower() if process_name else (os.path.basename(exe_path).lower() if exe_path else "")).strip()
        
        # Default fallback pixmap (UI Icons/default_process.png scaled smoothly to 24x24)
        default_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "default_process.png")
        if os.path.exists(default_icon_path):
            default_pixmap = QPixmap(default_icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            default_pixmap = QPixmap()
            
        if not cache_key:
            return default_pixmap
            
        # 1. Check RAM cache first
        if cache_key in self._process_icon_cache:
            return self._process_icon_cache[cache_key]
        
        # 2. Check APPDATA disk cache first (Instant load < 0.1ms!)
        icon_cache_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'icon_cache')
        try:
            os.makedirs(icon_cache_dir, exist_ok=True)
        except Exception:
            pass
            
        disk_cache_file = os.path.join(icon_cache_dir, f"{cache_key}.png")
        if os.path.exists(disk_cache_file):
            try:
                pixmap = QPixmap(disk_cache_file)
                if not pixmap.isNull():
                    if pixmap.width() > 24 or pixmap.height() > 24:
                        pixmap = pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self._process_icon_cache[cache_key] = pixmap
                    return pixmap
            except Exception:
                pass

        if not exe_path or not os.path.exists(exe_path):
            self._process_icon_cache[cache_key] = default_pixmap
            return default_pixmap
        
        # 3. Extraction attempt 1: icoextract
        pixmap = QPixmap()
        if ICOEXTRACT_AVAILABLE:
            try:
                from PIL import Image
                extractor = IconExtractor(exe_path)
                with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as tmp:
                    tmp_path = tmp.name
                
                try:
                    extractor.export_icon(tmp_path, num=0)
                    pil_img = Image.open(tmp_path)
                    pil_img = pil_img.convert('RGBA')
                    pil_img.thumbnail((24, 24), Image.Resampling.LANCZOS)
                    
                    png_data = io.BytesIO()
                    pil_img.save(png_data, format='PNG')
                    png_data.seek(0)
                    
                    img = QImage()
                    if img.loadFromData(png_data.read()):
                        pixmap = QPixmap.fromImage(img)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            except Exception:
                pass

        # Extraction attempt 2: Qt / Windows Shell FileIconProvider fallback
        if pixmap.isNull():
            try:
                from PySide6.QtWidgets import QFileIconProvider
                from PySide6.QtCore import QFileInfo
                provider = QFileIconProvider()
                icon = provider.icon(QFileInfo(exe_path))
                if not icon.isNull():
                    pixmap = icon.pixmap(24, 24)
            except Exception:
                pass

        # 4. If pixmap was successfully extracted, save PNG to APPDATA for permanent fast load!
        if not pixmap.isNull():
            if pixmap.width() > 24 or pixmap.height() > 24:
                pixmap = pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            try:
                pixmap.save(disk_cache_file, "PNG")
            except Exception:
                pass
            self._process_icon_cache[cache_key] = pixmap
            return pixmap

        # Fallback if extraction failed
        self._process_icon_cache[cache_key] = default_pixmap
        return default_pixmap
    
    def _populate_processes_tab(self):
        """Populate processes tab with running processes using QTableWidget."""
        import psutil
        import json
        import os
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtGui import QIcon, QPixmap
        
        table = self._processes_table
        
        # Load blacklist from file
        blacklist_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'process_blacklist.json')
        try:
            if os.path.exists(blacklist_path):
                with open(blacklist_path, 'r') as f:
                    self._process_blacklist = set(json.load(f))
            else:
                self._process_blacklist = set()
        except:
            self._process_blacklist = set()
        
        # Save currently checked process names BEFORE clearing
        checked_process_names = set()
        if hasattr(self, '_process_checks') and hasattr(self, '_process_data'):
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    checked_process_names.add(self._process_data[i]['name'])
        
        # Clear existing
        table.setRowCount(0)
        
        self._process_checks = []
        self._process_blacklist_checks = []  # Blacklist checkboxes
        self._process_data = []  # Store process info alongside checkboxes
        
        # Store checked names for restoring later
        self._checked_process_names = checked_process_names
        
        # Initialize icon cache if not exists
        if not hasattr(self, '_process_icon_cache'):
            self._process_icon_cache = {}
        
        # Processes to hide from list (lowercase)
        PROCESS_BLACKLIST = {
            'pwsh.exe', 'powershell.exe', 'cmd.exe', 'conhost.exe',
            'regedit.exe', 'registry', 'reg.exe',
            'svchost.exe', 'csrss.exe', 'smss.exe', 'wininit.exe',
            'services.exe', 'lsass.exe', 'winlogon.exe',
            'dwm.exe', 'explorer.exe', 'system', 'system idle process',
            'searchindexer.exe', 'searchhost.exe', 'runtimebroker.exe',
            'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
            'dllhost.exe', 'ctfmon.exe', 'textinputhost.exe',
            'shellexperiencehost.exe', 'startmenuexperiencehost.exe',
            'applicationframehost.exe', 'securityhealthsystray.exe',
            'helxaid.exe',  # Hide our own launcher
        }
        
        # Get processes and group by name
        process_groups = {}  # name -> {pids: [], memory: total, exe: first_exe}
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'exe']):
            try:
                info = proc.info
                mem = info['memory_info'].rss if info['memory_info'] else 0
                name = info['name']
                exe = info.get('exe', '')
                pid = info['pid']
                
                # Skip blacklisted processes and empty names
                if not name or name.lower() in PROCESS_BLACKLIST:
                    continue
                
                if name in process_groups:
                    process_groups[name]['pids'].append(pid)
                    process_groups[name]['memory'] += mem
                    # Keep first exe found (for icon)
                    if not process_groups[name]['exe'] and exe:
                        process_groups[name]['exe'] = exe
                else:
                    process_groups[name] = {
                        'pids': [pid],
                        'memory': mem,
                        'exe': exe
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Convert to list and filter by memory > 50MB
        processes = []
        for name, data in process_groups.items():
            if data['memory'] > 50 * 1024 * 1024:  # > 50 MB total
                processes.append({
                    'pids': data['pids'],  # Store all PIDs for killing
                    'name': name,
                    'memory': data['memory'],
                    'exe': data['exe'],
                    'count': len(data['pids'])  # Number of instances
                })
        
        # Sort based on current setting
        if self._processes_sort_column == "name":
            processes.sort(key=lambda x: x['name'].lower(), reverse=not self._processes_sort_asc)
        else:  # memory
            processes.sort(key=lambda x: x['memory'], reverse=not self._processes_sort_asc)
            
        # Freeze table updates during bulk insertion to eliminate layout reflow lag
        table.setUpdatesEnabled(False)
        try:
            display_processes = processes[:50]
            table.setRowCount(len(display_processes))
            
            for idx, proc in enumerate(display_processes):
                # Column 0: Checkbox
                cb_widget = QWidget()
                cb_widget.setObjectName(f"processCheckWidget_{idx}")
                cb_widget.setStyleSheet("background: transparent;")
                cb_layout = QHBoxLayout(cb_widget)
                cb_layout.setContentsMargins(8, 0, 0, 0)
                cb_layout.setAlignment(Qt.AlignCenter)
                
                cb = AnimatedCheckBox()
                cb.setObjectName(f"processCheck_{idx}")
                if hasattr(self, '_checked_process_names') and proc['name'] in self._checked_process_names:
                    cb.setChecked(True)
                cb.toggled.connect(self._update_processes_count)
                cb.toggled.connect(self._update_total_items_count)
                cb.toggled.connect(self._save_custom_preset)
                self._process_checks.append(cb)
                self._process_data.append({'pids': proc['pids'], 'name': proc['name'], 'count': proc['count']})
                cb_layout.addWidget(cb)
                table.setCellWidget(idx, 0, cb_widget)
                
                # Column 1: Icon (Loaded from APPDATA disk cache or extracted 1x)
                icon_widget = QWidget()
                icon_widget.setStyleSheet("background: transparent;")
                icon_layout = QHBoxLayout(icon_widget)
                icon_layout.setContentsMargins(4, 4, 4, 4)
                icon_layout.setAlignment(Qt.AlignCenter)
                
                icon_label = QLabel()
                icon_label.setFixedSize(24, 24)
                icon_label.setStyleSheet("background: transparent;")
                
                exe_path = proc.get('exe', '')
                pixmap = self._get_process_icon(exe_path, proc['name'])
                if not pixmap.isNull():
                    icon_label.setPixmap(pixmap)
                
                icon_layout.addWidget(icon_label)
                table.setCellWidget(idx, 1, icon_widget)
                
                # Column 2: Name
                name_item = QTableWidgetItem(proc['name'])
                name_item.setForeground(QColor("#e0e0e0"))
                table.setItem(idx, 2, name_item)
                
                # Column 3: Memory
                mem = proc['memory']
                mem_str = f"{mem / (1024**3):.2f} GB" if mem >= 1024**3 else f"{mem / (1024**2):.0f} MB"
                mem_item = QTableWidgetItem(mem_str)
                mem_item.setForeground(QColor("#888888"))
                mem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                mem_item.setData(Qt.UserRole, mem)
                table.setItem(idx, 3, mem_item)
                
                # Column 4: Blacklist checkbox
                bl_widget = QWidget()
                bl_widget.setObjectName(f"processBlacklistWidget_{idx}")
                bl_widget.setStyleSheet("background: transparent;")
                bl_layout = QHBoxLayout(bl_widget)
                bl_layout.setContentsMargins(8, 0, 8, 0)
                bl_layout.setAlignment(Qt.AlignCenter)
                
                bl_cb = AnimatedCheckBox()
                bl_cb.setObjectName(f"processBlacklist_{idx}")
                bl_cb.setToolTip("Blacklist: Skip this process during boost")
                if proc['name'] in self._process_blacklist:
                    bl_cb.setChecked(True)
                bl_cb.toggled.connect(lambda checked, name=proc['name']: self._on_blacklist_toggled(name, checked))
                self._process_blacklist_checks.append(bl_cb)
                bl_layout.addWidget(bl_cb)
                table.setCellWidget(idx, 4, bl_widget)
        finally:
            table.setUpdatesEnabled(True)  # Single clean repaint
        
        self._update_processes_count()
    
    def _on_blacklist_toggled(self, process_name: str, checked: bool):
        """Handle blacklist checkbox toggle - save to file."""
        import json
        import os
        
        if checked:
            self._process_blacklist.add(process_name)
        else:
            self._process_blacklist.discard(process_name)
        
        # Save to file
        blacklist_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'process_blacklist.json')
        try:
            os.makedirs(os.path.dirname(blacklist_path), exist_ok=True)
            with open(blacklist_path, 'w') as f:
                json.dump(list(self._process_blacklist), f)
            print(f"[Blacklist] Saved: {process_name} = {checked}")
        except Exception as e:
            print(f"[Blacklist] Error saving: {e}")
    
    def _create_basic_services_tab(self) -> QWidget:
        """Create Basic Services tab content."""
        from RamCleanerPresetDialog import BASIC_SERVICES, get_service_status
        self._basic_service_checks = []  # Store for MANUAL BOOST
        self._basic_service_data = []  # Store service names
        return self._create_services_list(BASIC_SERVICES, get_service_status, 
                                          self._basic_service_checks, self._basic_service_data, "basic")
    
    def _create_advanced_services_tab(self) -> QWidget:
        """Create Advanced Services tab content."""
        from RamCleanerPresetDialog import ADVANCED_SERVICES, get_service_status
        self._advanced_service_checks = []  # Store for MANUAL BOOST
        self._advanced_service_data = []  # Store service names
        return self._create_services_list(ADVANCED_SERVICES, get_service_status,
                                          self._advanced_service_checks, self._advanced_service_data, "advanced")
    
    def _create_services_list(self, services: list, get_status, check_storage: list = None, data_storage: list = None, tab_id: str = "services") -> QWidget:
        """Create a services list using QTableWidget for proper column alignment.
        
        Args:
            services: List of service dicts with 'name', 'display', 'desc' keys
            get_status: Function to get service status
            check_storage: Optional list to store checkboxes (for MANUAL BOOST)
            data_storage: Optional list to store service names (for stopping)
            tab_id: Unique ID for this tab (basic/advanced)
        """
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        page = QWidget()
        page.setObjectName(f"{tab_id}Page")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName(f"{tab_id}SelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet(f"""
            QFrame#{tab_id}SelectRow {{
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }}
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        
        select_all_cb = AnimatedCheckBox("Select all")
        select_all_cb.setObjectName(f"{tab_id}SelectAll")
        select_all_cb.setStyleSheet("color: #e0e0e0; font-size: 11px; background: transparent;")
        if tab_id == "basic":
            self._basic_select_all = select_all_cb
            select_all_cb.setChecked(True)  # Default: all checked for basic
            select_all_cb.toggled.connect(self._on_basic_select_all)
        else:
            self._advanced_select_all = select_all_cb
            select_all_cb.toggled.connect(self._on_advanced_select_all)
        select_layout.addWidget(select_all_cb)
        
        count_label = QLabel(f"0/{len(services)}")
        count_label.setObjectName(f"{tab_id}CountLabel")
        count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        if tab_id == "basic":
            self._basic_count_label = count_label
        else:
            self._advanced_count_label = count_label
        select_layout.addWidget(count_label)
        select_layout.addStretch()
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        table = QTableWidget()
        table.setObjectName(f"{tab_id}Table")
        table.setColumnCount(4)
        table.setRowCount(len(services))
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "Name", "Status", "Description"])
        
        # Column widths
        table.setColumnWidth(0, 50)   # Checkbox (#) - fixed
        table.setColumnWidth(1, 250)  # Name - min 200
        table.setColumnWidth(2, 100)  # Status - min 175
        table.horizontalHeader().setStretchLastSection(True)  # Description stretches
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setMinimumSectionSize(50)  # Base minimum
        
        # Set minimum sizes for Name and Status columns
        header = table.horizontalHeader()
        header.setMinimumSectionSize(50)  # Minimum for resizable columns
        
        # Styling
        table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            QTableWidget::item:hover {{
                background: rgba(255, 91, 6, 0.08);
            }}
            QHeaderView::section {{
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }}
            QHeaderView::section:hover {{
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }}
            QScrollBar:vertical {{
                background: #1a1a1a;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #444;
                border-radius: 3px;
            }}
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Populate table
        for idx, svc in enumerate(services):
            status = get_status(svc["name"])
            
            # Column 0: Checkbox
            cb_widget = QWidget()
            cb_widget.setObjectName(f"{tab_id}CheckWidget_{idx}")
            cb_widget.setStyleSheet("background: transparent;")
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            
            cb = AnimatedCheckBox()
            cb.setObjectName(f"{tab_id}Check_{idx}")
            # Default: Basic tab = all checked, Advanced tab = all unchecked
            if tab_id == "basic":
                cb.setChecked(True)
            cb_layout.addWidget(cb)
            table.setCellWidget(idx, 0, cb_widget)
            
            # Store checkbox and data for MANUAL BOOST
            if check_storage is not None:
                check_storage.append(cb)
                cb.toggled.connect(self._update_total_items_count)
                # Autosave preset on every toggle so user never needs to manually save
                cb.toggled.connect(self._save_custom_preset)
                if tab_id == "basic":
                    cb.toggled.connect(self._update_basic_count)
                else:
                    cb.toggled.connect(self._update_advanced_count)
            if data_storage is not None:
                data_storage.append({'name': svc['name'], 'display': svc['display']})
            
            # Column 1: Name
            name_item = QTableWidgetItem(svc["display"])
            name_item.setForeground(QColor("#e0e0e0"))
            table.setItem(idx, 1, name_item)
            
            # Column 2: Status
            status_item = QTableWidgetItem(status)
            status_color = "#4ade80" if status == "Running" else "#888888"
            status_item.setForeground(QColor(status_color))
            table.setItem(idx, 2, status_item)
            
            # Column 3: Description
            desc_item = QTableWidgetItem(svc["desc"])
            desc_item.setForeground(QColor("#666666"))
            table.setItem(idx, 3, desc_item)
        
        page_layout.addWidget(table, 1)
        
        # Store table reference for sorting
        if tab_id == "basic":
            self._basic_table = table
            self._basic_table_smoother = SmoothTableWidget(table)
        else:
            self._advanced_table = table
            self._advanced_table_smoother = SmoothTableWidget(table)
        
        
        # ========== BOTTOM BAR ==========
        bottom = QFrame()
        bottom.setObjectName(f"{tab_id}Bottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet(f"""
            QFrame#{tab_id}Bottom {{
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }}
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName(f"{tab_id}ResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        if tab_id == "basic":
            reset_btn.clicked.connect(self._reset_basic_services)
        else:
            reset_btn.clicked.connect(self._reset_advanced_services)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Update count label after all checkboxes are created
        if tab_id == "basic":
            self._update_basic_count()
        else:
            self._update_advanced_count()
        
        return page
    
    def _on_basic_select_all(self, checked: bool):
        """Handle Select All checkbox for Basic Services tab."""
        if hasattr(self, '_basic_service_checks'):
            for cb in self._basic_service_checks:
                cb.setChecked(checked)
        self._update_basic_count()
        self._update_total_items_count()
    
    def _on_advanced_select_all(self, checked: bool):
        """Handle Select All checkbox for Advanced Services tab."""
        if hasattr(self, '_advanced_service_checks'):
            for cb in self._advanced_service_checks:
                cb.setChecked(checked)
        self._update_advanced_count()
        self._update_total_items_count()
    
    def _update_basic_count(self):
        """Update Basic Services count label."""
        if hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_count_label'):
            selected = sum(1 for cb in self._basic_service_checks if cb.isChecked())
            total = len(self._basic_service_checks)
            self._basic_count_label.setText(f"{selected}/{total}")
    
    def _update_advanced_count(self):
        """Update Advanced Services count label."""
        if hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_count_label'):
            selected = sum(1 for cb in self._advanced_service_checks if cb.isChecked())
            total = len(self._advanced_service_checks)
            self._advanced_count_label.setText(f"{selected}/{total}")
    
    def _refresh_services_status(self):
        """Refresh status column for Basic and Advanced Services tabs."""
        from RamCleanerPresetDialog import BASIC_SERVICES, ADVANCED_SERVICES, get_service_status
        
        # Refresh Basic Services tab
        if hasattr(self, '_basic_table'):
            for idx, svc in enumerate(BASIC_SERVICES):
                if idx < self._basic_table.rowCount():
                    status = get_service_status(svc["name"])
                    status_item = self._basic_table.item(idx, 2)
                    if status_item:
                        status_item.setText(status)
                        status_color = "#4ade80" if status == "Running" else "#888888"
                        status_item.setForeground(QColor(status_color))
        
        # Refresh Advanced Services tab
        if hasattr(self, '_advanced_table'):
            for idx, svc in enumerate(ADVANCED_SERVICES):
                if idx < self._advanced_table.rowCount():
                    status = get_service_status(svc["name"])
                    status_item = self._advanced_table.item(idx, 2)
                    if status_item:
                        status_item.setText(status)
                        status_color = "#4ade80" if status == "Running" else "#888888"
                        status_item.setForeground(QColor(status_color))
    
    def _reset_basic_services(self):
        """Reset all Basic Services checkboxes to default (all checked)."""
        if hasattr(self, '_basic_service_checks'):
            for cb in self._basic_service_checks:
                cb.setChecked(True)
        if hasattr(self, '_basic_select_all'):
            self._basic_select_all.setChecked(True)
        self._update_basic_count()
        self._update_total_items_count()
    
    def _reset_advanced_services(self):
        """Reset all Advanced Services checkboxes to unchecked."""
        if hasattr(self, '_advanced_service_checks'):
            for cb in self._advanced_service_checks:
                cb.setChecked(False)
        if hasattr(self, '_advanced_select_all'):
            self._advanced_select_all.setChecked(False)
        self._update_advanced_count()
        self._update_total_items_count()
    
    def _create_cpu_page(self):
        """Create CPU detailed page."""
        page = QWidget()
        page.setObjectName("cpuPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("CPU Details")
        title.setObjectName("cpuDetailsTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("CPU detailed view coming soon...")
        placeholder.setObjectName("cpuPlaceholder")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_drive_page(self):
        """Create Drive detailed page (Option A Layout: Top Split Total Storage | Drive Volumes).

        Component Name: DrivePage
        """
        page = QWidget()
        page.setObjectName("drivePage")
        page.setStyleSheet("background: transparent;")
        page.setUpdatesEnabled(False)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(12)

        # === TOP SECTION: Total Storage Card (Left) + Drive Volumes Panel (Right) ===
        top_container = QWidget()
        top_container.setObjectName("DriveTopContainer")
        top_container.setStyleSheet("background: transparent;")
        top_row = QHBoxLayout(top_container)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        # 1. Total Storage Overview Card (Left side of top row)
        self.drive_overview = DriveOverviewWidget()
        self.drive_overview.setMaximumWidth(360)
        top_row.addWidget(self.drive_overview)

        # 2. Drive Volumes Panel (Right side of top row, side-by-side with Total Storage)
        volumes_panel = QWidget()
        volumes_panel.setObjectName("DriveVolumeListPanel")
        volumes_panel.setAttribute(Qt.WA_StyledBackground, True)
        volumes_panel.setStyleSheet("""
            QWidget#DriveVolumeListPanel {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QWidget#DriveVolumeListPanel:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)
        volumes_layout = QVBoxLayout(volumes_panel)
        volumes_layout.setContentsMargins(14, 12, 14, 12)
        volumes_layout.setSpacing(8)

        title_row = QHBoxLayout()
        volumes_title = QLabel("DRIVE VOLUMES")
        volumes_title.setObjectName("driveVolumesTitle")
        volumes_title.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        title_row.addWidget(volumes_title)
        title_row.addStretch()
        self.drive_refresh_label = QLabel("Live")
        self.drive_refresh_label.setObjectName("driveRefreshLabel")
        self.drive_refresh_label.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: 800; background: transparent;")
        title_row.addWidget(self.drive_refresh_label)
        volumes_layout.addLayout(title_row)

        scroll = SmoothScrollArea()
        scroll.setObjectName("DriveVolumeScroll")
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1e1e1e; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.drive_volume_container = QWidget()
        self.drive_volume_container.setObjectName("DriveVolumeContainer")
        self.drive_volume_container.setStyleSheet("background: transparent;")
        self.drive_volume_layout = QVBoxLayout(self.drive_volume_container)
        self.drive_volume_layout.setContentsMargins(0, 0, 6, 0)
        self.drive_volume_layout.setSpacing(8)
        self.drive_volume_layout.addStretch()
        scroll.setWidget(self.drive_volume_container)
        volumes_layout.addWidget(scroll, stretch=1)

        top_row.addWidget(volumes_panel, stretch=1)

        # === BOTTOM SECTION: Disk Cleaner (Full Width) ===
        self.drive_cleaner = DiskCleanerPanel()
        self.drive_cleaner.scan_requested.connect(self._start_drive_scan)
        self.drive_cleaner.clean_requested.connect(self._start_drive_clean)

        # === VERTICAL SPLITTER WITH RESIZE HANDLE LINE BELOW TOP CARDS ===
        drive_splitter = DrivePageSplitter(Qt.Vertical)
        drive_splitter.setObjectName("DrivePageSplitter")
        drive_splitter.setStyleSheet("""
            QSplitter#DrivePageSplitter::handle {
                height: 24px;
                background: transparent;
            }
        """)
        drive_splitter.addWidget(top_container)
        drive_splitter.addWidget(self.drive_cleaner)
        drive_splitter.setStretchFactor(0, 0)
        drive_splitter.setStretchFactor(1, 1)

        layout.addWidget(drive_splitter, stretch=1)

        self._drive_refresh_counter = 0
        self._request_async_drive_info()
        page.setUpdatesEnabled(True)
        return page

    def _request_async_drive_info(self):
        """Asynchronously query drive hardware info without blocking the UI thread."""
        if getattr(self, '_drive_info_worker', None) and self._drive_info_worker.isRunning():
            return
        self._drive_info_worker = DriveInfoWorker(self)
        self._drive_info_worker.data_ready.connect(self._on_drive_info_updated)
        self._drive_info_worker.finished.connect(self._drive_info_worker.deleteLater)
        self._drive_info_worker.start()

    def _on_drive_info_updated(self, partitions, hardware_info, physical_disks, lhm_drives=None):
        if lhm_drives:
            self._lhm_storage = lhm_drives
            self._smart_disks = lhm_drives
            self._disk_smart_fetched = True
        else:
            # Fallback to previously cached valid SMART data if current read is transiently empty
            cached_lhm = getattr(self, '_lhm_storage', [])
            if cached_lhm:
                lhm_drives = cached_lhm
                self._smart_disks = cached_lhm
            elif lhm_drives is None:
                lhm_drives = []
        
        def _is_match(n1_str, n2_str):
            if not n1_str or not n2_str:
                return False
            if len(physical_disks) == 1 and len(lhm_drives) == 1:
                return True
            u1, u2 = n1_str.upper(), n2_str.upper()
            if u1 in u2 or u2 in u1:
                return True
            s1 = set(u1.replace('_', ' ').replace('-', ' ').split()) - {'1TB','2TB','4TB','500GB','250GB','1000GB','2000GB','SSD','NVME','DISK','DRIVE','GENERIC'}
            s2 = set(u2.replace('_', ' ').replace('-', ' ').split()) - {'1TB','2TB','4TB','500GB','250GB','1000GB','2000GB','SSD','NVME','DISK','DRIVE','GENERIC'}
            return bool(s1 & s2)

        for idx_d, disk in enumerate(physical_disks):
            d_model = disk.get('model', '')
            matched_lhm = None
            for lhm_disk in lhm_drives:
                lhm_name = lhm_disk.get('model') or lhm_disk.get('name', '')
                if _is_match(d_model, lhm_name):
                    matched_lhm = lhm_disk
                    break
            if not matched_lhm and len(lhm_drives) > 0:
                lhm_idx = min(idx_d, len(lhm_drives) - 1)
                matched_lhm = lhm_drives[lhm_idx]

            if matched_lhm:
                lhm_name = matched_lhm.get('model') or matched_lhm.get('name', '')
                if lhm_name and any(gen in d_model.lower() for gen in ('system storage', 'physical drive', 'storage')):
                    disk['model'] = lhm_name
                if matched_lhm.get('temp', 0) > 0:
                    disk['temp_c'] = matched_lhm['temp']
                lhm_health = matched_lhm.get('health_percent', 0)
                if lhm_health > 0:
                    disk['health_pct'] = lhm_health
                    disk['health_text'] = f"{int(lhm_health)}% HEALTHY"
                    if lhm_health < 90:
                        disk['health_text'] = f"{int(lhm_health)}% WARNING"

        for hw_key, hw_val in hardware_info.items():
            hw_model = hw_val.get('model', '')
            matched_lhm = None
            for lhm_disk in lhm_drives:
                lhm_name = lhm_disk.get('model') or lhm_disk.get('name', '')
                if _is_match(hw_model, lhm_name):
                    matched_lhm = lhm_disk
                    break
            if not matched_lhm and len(lhm_drives) > 0:
                matched_lhm = lhm_drives[0]

            if matched_lhm:
                lhm_name = matched_lhm.get('model') or matched_lhm.get('name', '')
                if lhm_name and any(gen in hw_model.lower() for gen in ('system storage', 'physical drive', 'storage')):
                    hw_val['model'] = lhm_name
                if matched_lhm.get('temp', 0) > 0:
                    hw_val['temperature'] = matched_lhm['temp']
                lhm_health = matched_lhm.get('health_percent', 0)
                if lhm_health > 0:
                    hw_val['health_pct'] = lhm_health
                    if lhm_health >= 90 and 'CRITICAL' not in hw_val.get('smart_status', '').upper():
                        hw_val['smart_status'] = 'OK'

        self._drive_partitions = partitions
        self._drive_hardware_info = hardware_info
        self._drive_physical_disks = physical_disks
        self._drive_info_worker = None

        if hasattr(self, 'drive_overview'):
            disk_io = getattr(self, '_last_disk_io', {"read_mbps": 0, "write_mbps": 0})
            self.drive_overview.set_data(partitions, hardware_info, disk_io, physical_disks)

        current_tab = self._page_stack.currentIndex() if hasattr(self, '_page_stack') else -1
        if current_tab == 3:  # Only render Drive cards if Drive tab is currently active
            self._render_drive_cards(partitions)
            if hasattr(self, "drive_refresh_label"):
                self.drive_refresh_label.setText(f"{len(partitions)} volumes")

    def _get_drive_hw_for_partition(self, partition):
        drive = partition.get("drive", "")
        letter = partition.get("letter", "")
        candidates = [drive, letter, f"{letter}\\" if letter else "", f"{letter}\\\\" if letter else ""]
        for key in candidates:
            if key in self._drive_hardware_info:
                return self._drive_hardware_info[key]
        return next(iter(self._drive_hardware_info.values()), {}) if len(self._drive_hardware_info) == 1 else {}

    def _merge_drive_snapshot(self, partitions, disks):
        by_drive = {str(disk.get("drive", "")).rstrip("\\/").upper(): disk for disk in disks}
        for partition in partitions:
            key = str(partition.get("drive", "")).rstrip("\\/").upper()
            disk = by_drive.get(key)
            if not disk:
                continue
            total = int(float(disk.get("total", 0) or 0) * (1024 ** 3))
            used = int(float(disk.get("used", 0) or 0) * (1024 ** 3))
            free = int(float(disk.get("free", 0) or 0) * (1024 ** 3))
            if total > 0:
                partition["total_bytes"] = total
                partition["used_bytes"] = used
                partition["free_bytes"] = free
                partition["percent_used"] = float(disk.get("percent", 0) or 0)
                partition["filesystem"] = disk.get("fstype") or partition.get("filesystem") or "Unknown"
        return partitions

    def _render_drive_cards(self, partitions):
        if not hasattr(self, "drive_volume_layout"):
            return
        current = set()
        for partition in partitions:
            drive = partition.get("drive") or partition.get("letter")
            if not drive:
                continue
            current.add(drive)
            card = self._drive_volume_cards.get(drive)
            if card is None:
                card = DriveVolumeCard()
                self.drive_volume_layout.insertWidget(max(0, self.drive_volume_layout.count() - 1), card)
                self._drive_volume_cards[drive] = card
            card.set_data(partition, self._get_drive_hw_for_partition(partition))

        for drive in list(self._drive_volume_cards.keys()):
            if drive in current:
                continue
            card = self._drive_volume_cards.pop(drive)
            self.drive_volume_layout.removeWidget(card)
            card.deleteLater()

    def _update_drive_metrics_from_snapshot(self, disks, disk_io):
        if not hasattr(self, "drive_overview"):
            return
        self._last_disk_io = disk_io or {}
        current_tab = self._page_stack.currentIndex() if hasattr(self, '_page_stack') else -1

        # Only process if Drive Tab (3) or Overview Tab (0) is active
        if current_tab not in (0, 3):
            return

        try:
            self._drive_refresh_counter = getattr(self, "_drive_refresh_counter", 0) + 1
            should_refresh = self._drive_refresh_counter >= 15 or not getattr(self, "_drive_partitions", None)
            if should_refresh:
                self._drive_refresh_counter = 0
                self._request_async_drive_info()

            if getattr(self, "_drive_partitions", None):
                partitions = [dict(p) for p in getattr(self, "_drive_partitions", [])]
                partitions = self._merge_drive_snapshot(partitions, disks or [])
                self._drive_partitions = partitions
                
                # Compare state signature to avoid redundant UI rebuilds on every poll tick
                state_sig = (
                    tuple((p.get('drive'), p.get('used_bytes'), p.get('total_bytes')) for p in partitions),
                    round(float((disk_io or {}).get('read_mbps', 0) or 0), 1),
                    round(float((disk_io or {}).get('write_mbps', 0) or 0), 1)
                )
                prev_sig = getattr(self, '_last_drive_state_sig', None)
                if state_sig != prev_sig:
                    self._last_drive_state_sig = state_sig
                    if current_tab == 3:
                        self._render_drive_cards(partitions)
                        self.drive_overview.set_data(
                            partitions, 
                            getattr(self, "_drive_hardware_info", {}), 
                            disk_io or {},
                            getattr(self, "_drive_physical_disks", [])
                        )
                        if hasattr(self, "drive_refresh_label"):
                            self.drive_refresh_label.setText(f"{len(partitions)} volumes")
        except Exception as e:
            if hasattr(self, "drive_refresh_label"):
                self.drive_refresh_label.setText("Drive scan unavailable")
            print(f"[Drive] Update error: {e}")

    def _start_drive_scan(self):
        if getattr(self, '_drive_scan_worker', None) and self._drive_scan_worker.isRunning():
            return
        self.drive_cleaner.set_busy(True, "Scanning junk files...", 0)
        self._drive_scan_worker = DriveScanWorker(self)
        self._drive_scan_worker.scan_progress.connect(self.drive_cleaner.update_progress)
        self._drive_scan_worker.scan_completed.connect(self._on_drive_scan_complete)
        self._drive_scan_worker.finished.connect(self._drive_scan_worker.deleteLater)
        self._drive_scan_worker.start()

    def _on_drive_scan_complete(self, results):
        if hasattr(self, "drive_cleaner"):
            self.drive_cleaner.update_results(results)
        self._drive_scan_worker = None

    def _start_drive_clean(self, selected_categories):
        if self._drive_clean_worker and self._drive_clean_worker.isRunning():
            return
        if not selected_categories:
            self.drive_cleaner.update_progress("Select at least one category first.", 0)
            return
        if self.drive_cleaner.selected_has_tier3():
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Confirm Advanced Cleanup",
                "Tier 3 cleanup can remove advanced Windows cache/log files. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.drive_cleaner.set_busy(True, "Cleaning selected categories...", 0)
        self._drive_clean_worker = DiskCleanWorker(selected_categories, self)
        self._drive_clean_worker.clean_progress.connect(self.drive_cleaner.update_progress)
        self._drive_clean_worker.clean_completed.connect(self._on_drive_clean_complete)
        self._drive_clean_worker.finished.connect(self._drive_clean_worker.deleteLater)
        self._drive_clean_worker.start()

    def _on_drive_clean_complete(self, cleaned, skipped, errors):
        if hasattr(self, "drive_cleaner"):
            self.drive_cleaner.finish_clean(cleaned, skipped, errors)
        self._drive_clean_worker = None
        self._drive_refresh_counter = 999
        self._update_drive_metrics_from_snapshot([], {"read_mbps": 0, "write_mbps": 0})

    def _create_health_page(self):
        """Create Health detailed page."""
        page = QWidget()
        page.setObjectName("healthPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("Hardware Health")
        title.setObjectName("healthDetailsTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("Health detailed view coming soon...")
        placeholder.setObjectName("healthPlaceholder")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_network_page(self):
        """Create Network Diagnostics & Benchmark Suite for HELXTATS.
        Structured with a Hub & Sub-Page architecture matching HELXAIRO Benchmark Lab:
        - Sub-Page 0: Network Hub View (Feature Cards Selector)
        - Sub-Page 1: Live Process Traffic Monitor
        - Sub-Page 2: Network Speedtest Lab (Lazily loaded)
        - Sub-Page 3: Usage History & Timeline Analytics (Lazily loaded)
        
        Component Name: NetworkPage
        """
        from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout
        from NetworkMonitor import NetworkMonitor

        page = QWidget()
        page.setObjectName("networkPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._net_stack = QStackedWidget(page)
        self._net_stack.setObjectName("netStack")

        # Sub-Page 0: Hub Selector View
        hub_view = self._create_net_hub_view()
        self._net_stack.addWidget(hub_view)

        # Sub-Page 1: Live Process Traffic View
        live_view = self._create_net_live_view(page)
        self._net_stack.addWidget(live_view)

        # Sub-Pages 2 & 3: Placeholders (lazily loaded on demand)
        self._net_placeholder_speedtest = QWidget()
        self._net_placeholder_speedtest.setObjectName("netPlaceholderSpeedtest")
        self._net_stack.addWidget(self._net_placeholder_speedtest)

        self._net_placeholder_history = QWidget()
        self._net_placeholder_history.setObjectName("netPlaceholderHistory")
        self._net_stack.addWidget(self._net_placeholder_history)

        layout.addWidget(self._net_stack)
        self._net_stack.setCurrentIndex(0)

        # Ensure NetworkMonitor instance exists and its signal is connected
        if not hasattr(self, '_net_monitor') or self._net_monitor is None:
            self._net_monitor = NetworkMonitor(parent=None)
            self._net_monitor_initialized = True

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self._net_monitor.data_updated.disconnect(self._on_net_data_updated)
            except Exception:
                pass
        self._net_monitor.data_updated.connect(self._on_net_data_updated)

        if not self._net_monitor.isRunning():
            self._net_monitor.start()
            print("[Hardware] NetworkMonitor started in network page")
        else:
            print("[Hardware] NetworkMonitor already running, connected signal")

        # Shutdown monitor when the page widget is destroyed
        page.destroyed.connect(lambda: self._stop_net_monitor())

        return page

    def _create_net_hub_view(self):
        """Create Network Diagnostics & Benchmark Lab Hub Selector Grid matching HELXAIRO Benchmark Lab exactly."""
        from PySide6.QtWidgets import (
            QFrame, QVBoxLayout, QLabel, 
            QGridLayout, QWidget, QGroupBox, QSizePolicy
        )
        from PySide6.QtCore import Qt
        from smooth_scroll import SmoothScrollArea

        hub_scroll = SmoothScrollArea()
        hub_scroll.setObjectName("netHubScroll")
        hub_scroll.setWidgetResizable(True)
        hub_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1e1e1e; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        content = QWidget()
        content.setObjectName("netHubContent")
        content.setStyleSheet("background: transparent;")
        hub_layout = QVBoxLayout(content)
        hub_layout.setContentsMargins(0, 0, 0, 0)
        hub_layout.setSpacing(15)

        # Network Lab Group Box (Matches Benchmark Lab GroupBox in HELXAIRO)
        hub_group = QGroupBox("Network Lab")
        hub_group.setObjectName("netHubGroup")
        hub_group.setStyleSheet("""
            QGroupBox {
                color: #ff5b06;
                font-family: 'Orbitron', sans-serif;
                font-size: 16px;
                font-weight: bold;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 10px;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """)
        hub_group_layout = QVBoxLayout(hub_group)
        hub_group_layout.setContentsMargins(16, 20, 16, 16)
        hub_group_layout.setSpacing(12)

        hub_desc = QLabel("Comprehensive Network Performance & Traffic Diagnostics Suite")
        hub_desc.setObjectName("netHubDesc")
        hub_desc.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        hub_group_layout.addWidget(hub_desc)

        # 2x2 Grid of Feature Cards (Matches HELXAIRO Benchmark Lab)
        grid_container = QWidget()
        grid_container.setObjectName("netHubGrid")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(15)

        # ── Card 1: Live Traffic Monitor ──
        card1 = QFrame()
        card1.setObjectName("netCardLiveTraffic")
        card1.setCursor(Qt.PointingHandCursor)
        card1.setMinimumHeight(105)
        card1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card1.setStyleSheet("""
            QFrame#netCardLiveTraffic {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#netCardLiveTraffic:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
            QFrame#netCardLiveTraffic QLabel {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        c1_lay = QVBoxLayout(card1)
        c1_lay.setContentsMargins(0, 0, 0, 0)
        c1_lay.setSpacing(6)
        c1_title = QLabel("Live Traffic Monitor")
        c1_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        c1_sub = QLabel("Real-time per-process network bandwidth consumption, active sockets & live throughput charts")
        c1_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent; border: none;")
        c1_sub.setWordWrap(True)
        c1_lay.addWidget(c1_title)
        c1_lay.addWidget(c1_sub)
        c1_lay.addStretch()

        card1.mousePressEvent = lambda e: self._switch_net_subpage(1)
        grid_layout.addWidget(card1, 0, 0)

        # ── Card 2: Network Speedtest Lab ──
        card2 = QFrame()
        card2.setObjectName("netCardSpeedtest")
        card2.setCursor(Qt.PointingHandCursor)
        card2.setMinimumHeight(105)
        card2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card2.setStyleSheet("""
            QFrame#netCardSpeedtest {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#netCardSpeedtest:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
            QFrame#netCardSpeedtest QLabel {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        c2_lay = QVBoxLayout(card2)
        c2_lay.setContentsMargins(0, 0, 0, 0)
        c2_lay.setSpacing(6)
        c2_title = QLabel("Network Speedtest Lab")
        c2_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        c2_sub = QLabel("Multi-stream download, upload, ping latency, vector tachometer gauge & gaming benchmark")
        c2_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent; border: none;")
        c2_sub.setWordWrap(True)
        c2_lay.addWidget(c2_title)
        c2_lay.addWidget(c2_sub)
        c2_lay.addStretch()

        card2.mousePressEvent = lambda e: self._switch_net_subpage(2)
        grid_layout.addWidget(card2, 0, 1)

        # ── Card 3: Network Adapter & Service Guide ──
        card_guide = QFrame()
        card_guide.setObjectName("netCardGuide")
        card_guide.setCursor(Qt.PointingHandCursor)
        card_guide.setMinimumHeight(105)
        card_guide.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card_guide.setStyleSheet("""
            QFrame#netCardGuide {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#netCardGuide:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
            QFrame#netCardGuide QLabel {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        cg_lay = QVBoxLayout(card_guide)
        cg_lay.setContentsMargins(0, 0, 0, 0)
        cg_lay.setSpacing(6)
        cg_title = QLabel("Network Adapter & Service Guide")
        cg_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        cg_sub = QLabel("Hardware network interface controller diagnostics, ETW service configuration & troubleshooting wizard")
        cg_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent; border: none;")
        cg_sub.setWordWrap(True)
        cg_lay.addWidget(cg_title)
        cg_lay.addWidget(cg_sub)
        cg_lay.addStretch()

        card_guide.mousePressEvent = lambda e: self._open_settings_for_net()
        grid_layout.addWidget(card_guide, 1, 0, 1, 2)

        hub_group_layout.addWidget(grid_container)
        hub_layout.addWidget(hub_group)
        hub_layout.addStretch()

        hub_scroll.setWidget(content)
        return hub_scroll

    def _create_net_live_view(self, parent_page):
        """Create the live process monitor sub-page with a top navigation bar."""
        from PySide6.QtWidgets import QComboBox, QFrame, QProgressBar, QFileIconProvider, QPushButton
        from PySide6.QtCore import QFileInfo, QSize
        from PySide6.QtGui import QIcon
        from smooth_scroll import SmoothScrollArea
        import psutil
        import os

        # One-time NIC baseline for the adapter combo
        nic_stats = psutil.net_io_counters(pernic=True)
        active_nics = [
            name for name, s in nic_stats.items()
            if (s.bytes_sent + s.bytes_recv) > 0
        ]
        display_nic = max(active_nics, key=lambda n: nic_stats[n].bytes_sent + nic_stats[n].bytes_recv) if active_nics else None

        page = QWidget()
        page.setObjectName("netLiveView")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 10, 0)
        layout.setSpacing(14)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')
        arrow_icon_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace('\\', '/')

        combo_style = f"""
            QComboBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 28px 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url('{arrow_icon_path}');
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 28px;
                padding: 4px 10px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }}
        """

        # ---- Top Header Bar with Back Button ----
        header_bar = QFrame()
        header_bar.setObjectName("netLiveHeaderBar")
        header_bar.setFixedHeight(38)
        header_bar.setStyleSheet("""
            QFrame#netLiveHeaderBar {
                background: rgba(255, 255, 255, 0.03);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        back_btn = QPushButton()
        back_btn.setObjectName("netLiveBackBtn")
        back_btn.setFixedSize(30, 26)
        back_btn.setIcon(QIcon(back_icon_path))
        back_btn.setIconSize(QSize(15, 15))
        back_btn.setToolTip("Back to Network Hub")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton#netLiveBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                margin: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#netLiveBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        back_btn.clicked.connect(lambda: self._net_stack.setCurrentIndex(0))
        h_layout.addWidget(back_btn)

        title_lbl = QLabel("LIVE PROCESS TRAFFIC MONITOR")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron'; font-size: 13px; font-weight: bold; background: transparent;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        layout.addWidget(header_bar)

        # ---- 1. Top Section (Stats & Limit) ----------------------------------
        top_section = QHBoxLayout()
        top_section.setSpacing(20)

        # Left: Session total
        total_data_layout = QVBoxLayout()
        total_data_layout.setSpacing(2)
        self._net_total_lbl = QLabel("0 B")
        self._net_total_lbl.setObjectName("netTotalLabel")
        self._net_total_lbl.setStyleSheet("color: #ffffff; font-size: 32px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        self._net_nic_lbl = QLabel("Loading history...")
        self._net_nic_lbl.setObjectName("netNicLabel")
        self._net_nic_lbl.setStyleSheet("color: #FF5B06; font-size: 11px; font-weight: 600; background: transparent;")
        total_data_layout.addWidget(self._net_total_lbl)
        total_data_layout.addWidget(self._net_nic_lbl)
        total_data_layout.addStretch()
        top_section.addLayout(total_data_layout)

        # Middle: Info text
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_title = QLabel("Network usage")
        info_title.setObjectName("netInfoTitle")
        info_title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold; background: transparent;")
        info_desc = QLabel("Real-time network consumption by process.")
        info_desc.setObjectName("netInfoDesc")
        info_desc.setWordWrap(True)
        info_desc.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        info_layout.addWidget(info_title)
        info_layout.addWidget(info_desc)
        info_layout.addStretch()
        top_section.addLayout(info_layout, stretch=1)

        # Right: Adapter selector
        ctrl_layout = QVBoxLayout()
        ctrl_layout.setSpacing(10)

        def _get_wifi_ssid() -> str:
            try:
                import subprocess, re
                out = subprocess.check_output("netsh wlan show interfaces", shell=True, text=True, errors="ignore", timeout=2)
                match = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.MULTILINE)
                if match:
                    ssid = match.group(1).strip()
                    if ssid and not ssid.startswith("BSSID"):
                        return ssid
            except Exception:
                pass
            return ""

        wifi_ssid = _get_wifi_ssid()

        adapter_combo = QComboBox()
        adapter_combo.setObjectName("netAdapterCombo")
        if active_nics:
            for nic_name in active_nics:
                display_label = nic_name
                if ("wi-fi" in nic_name.lower() or "wlan" in nic_name.lower() or "wireless" in nic_name.lower()) and wifi_ssid:
                    display_label = f"{nic_name} ({wifi_ssid})"
                adapter_combo.addItem(f" {display_label}")
            if display_nic in active_nics:
                adapter_combo.setCurrentIndex(active_nics.index(display_nic))
        else:
            adapter_combo.addItem(" No active adapter")
        adapter_combo.setStyleSheet(combo_style)
        adapter_combo.setFixedWidth(220)

        ctrl_layout.addWidget(adapter_combo, alignment=Qt.AlignRight)
        ctrl_layout.addStretch()
        top_section.addLayout(ctrl_layout)

        layout.addLayout(top_section)

        # ---- 2. Middle Section (section title & filter) -----------------------
        filter_section = QHBoxLayout()
        stat_title = QLabel("Usage statistics")
        stat_title.setObjectName("netStatTitle")
        stat_title.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: 600; background: transparent;")
        filter_section.addWidget(stat_title)
        filter_section.addStretch()

        self._net_time_filter = QComboBox()
        self._net_time_filter.setObjectName("netTimeFilter")
        self._net_time_filter.addItems(["3 Hours", "24 Hours", "7 Days", "30 Days", "Total History"])
        self._net_time_filter.setCurrentText("Total History")
        self._net_time_filter.setCursor(Qt.PointingHandCursor)
        self._net_time_filter.setStyleSheet(combo_style)
        self._net_time_filter.setFixedWidth(140)
        filter_section.addWidget(self._net_time_filter)
        
        def on_time_filter_changed(text):
            if hasattr(self, '_net_monitor') and self._net_monitor is not None:
                self._net_monitor.set_timeframe_filter(text)
                
        self._net_time_filter.currentTextChanged.connect(on_time_filter_changed)

        layout.addLayout(filter_section)

        # ---- 3. Scrollable process list --------------------------------------
        scroll_area = SmoothScrollArea()
        scroll_area.setObjectName("netScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: #1a1a1a; }
            QScrollBar:vertical { background: #1e1e1e; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self._net_list_widget = QWidget()
        self._net_list_widget.setObjectName("netListWidget")
        self._net_list_widget.setStyleSheet("background: #1a1a1a;")
        self._net_list_layout = QVBoxLayout(self._net_list_widget)
        self._net_list_layout.setObjectName("netListLayout")
        self._net_list_layout.setContentsMargins(0, 0, 10, 0)
        self._net_list_layout.setSpacing(2)

        # Placeholder shown while waiting for first data tick
        self._net_placeholder_widget = QWidget()
        ph_layout = QVBoxLayout(self._net_placeholder_widget)
        ph_layout.setContentsMargins(0, 40, 0, 40)
        ph_layout.addStretch(1)
        
        self._net_placeholder = QLabel("Monitoring... first update in 1 second")
        self._net_placeholder.setObjectName("netPlaceholder")
        self._net_placeholder.setStyleSheet("color: #666666; font-size: 13px; font-weight: 500; background: transparent;")
        self._net_placeholder.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(self._net_placeholder, alignment=Qt.AlignCenter)
        ph_layout.addStretch(1)

        # Centered guide widget shown when both Psutil is off and ETW is unavailable
        self._net_disabled_guide_widget = QWidget()
        guide_layout = QVBoxLayout(self._net_disabled_guide_widget)
        guide_layout.setContentsMargins(20, 60, 20, 60)
        guide_layout.addStretch(1)

        guide_btn = QPushButton("Click here to turn on Psutil or Activate ETW to see Network History")
        guide_btn.setObjectName("netDisabledGuideBtn")
        guide_btn.setCursor(Qt.PointingHandCursor)
        guide_btn.setStyleSheet("""
            QPushButton#netDisabledGuideBtn {
                background: transparent;
                color: #a0a0a0;
                border: none;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#netDisabledGuideBtn:hover {
                background: transparent;
                border: none;
                color: #ffffff;
            }
        """)
        guide_btn.clicked.connect(self._open_settings_for_net)
        guide_layout.addWidget(guide_btn, alignment=Qt.AlignCenter)
        guide_layout.addStretch(1)
        self._net_disabled_guide_widget.setVisible(False)

        self._net_list_layout.addWidget(self._net_placeholder_widget)
        self._net_list_layout.addWidget(self._net_disabled_guide_widget)

        self._net_rows = {}
        self._net_icon_provider = QFileIconProvider()

        scroll_area.setWidget(self._net_list_widget)
        layout.addWidget(scroll_area, stretch=1)

        return page

    def _switch_net_subpage(self, index: int):
        """Switch sub-page in Network Stack with lazy initialization."""
        if index == 0 or index == 1:
            self._net_stack.setCurrentIndex(index)
        elif index == 2:
            if not hasattr(self, '_net_speedtest_panel') or self._net_speedtest_panel is None:
                from NetworkSpeedtestPanel import NetworkSpeedtestPanel
                self._net_speedtest_panel = NetworkSpeedtestPanel(parent=self)
                self._net_speedtest_panel.back_clicked.connect(lambda: self._net_stack.setCurrentIndex(0))
                self._net_stack.insertWidget(2, self._net_speedtest_panel)
            self._net_stack.setCurrentIndex(2)
        elif index == 3:
            if not hasattr(self, '_net_history_panel') or self._net_history_panel is None:
                from NetworkHistoryPanel import NetworkHistoryPanel
                self._net_history_panel = NetworkHistoryPanel(parent=self)
                self._net_history_panel.back_clicked.connect(lambda: self._net_stack.setCurrentIndex(0))
                self._net_stack.insertWidget(3, self._net_history_panel)
            self._net_history_panel.refresh_data()
            self._net_stack.setCurrentIndex(3)

    def _open_settings_for_net(self):
        """Helper to show Network Guide Wizard (matching HELXAIL guide) from network guide button."""
        win = self.window()
        if hasattr(win, '_show_network_info_dialog'):
            win._show_network_info_dialog()
        elif hasattr(win, 'open_settings_dialog'):
            win.open_settings_dialog(highlight_target="psutil")
        elif hasattr(self.parent(), 'open_settings_dialog'):
            self.parent().open_settings_dialog(highlight_target="psutil")

    def _stop_net_monitor(self):
        """Stop the NetworkMonitor thread gracefully."""
        if hasattr(self, '_net_speedtest_panel') and self._net_speedtest_panel is not None:
            try:
                self._net_speedtest_panel.stop_speedtest()
            except Exception:
                pass

        if hasattr(self, '_net_monitor') and self._net_monitor is not None:
            try:
                self._net_monitor.stop()
                if not self._net_monitor.wait(3000):  # Wait up to 3 seconds
                    print("[Hardware] NetworkMonitor thread did not stop in time, terminating")
                    self._net_monitor.terminate()
                    self._net_monitor.wait(1000)
            except Exception as e:
                print(f"[Hardware] Error stopping NetworkMonitor: {e}")
            self._net_monitor = None
            self._net_monitor_initialized = False  # Allow re-creation if panel is shown again

    def _on_net_data_updated(self, data):
        """Receive live data from NetworkMonitor and refresh Network tab widgets."""
        import os
        from PySide6.QtWidgets import QFileIconProvider

        if not hasattr(self, '_net_total_lbl') or self._net_total_lbl is None:
            return
        try:
            self._net_total_lbl.setText(self._fmt_net_bytes(data.get('session_bytes', 0)))
            nic_name = data.get('nic_name', '')
            current_filter = self._net_time_filter.currentText() if hasattr(self, '_net_time_filter') else "Total History"
            self._net_nic_lbl.setText(f"{current_filter}  |  {nic_name}" if nic_name else current_filter)
        except RuntimeError:
            return

        monitoring_disabled = data.get('monitoring_disabled', False)

        if monitoring_disabled:
            try:
                if hasattr(self, '_net_placeholder_widget') and self._net_placeholder_widget is not None:
                    self._net_placeholder_widget.setVisible(False)
                if hasattr(self, '_net_disabled_guide_widget') and self._net_disabled_guide_widget is not None:
                    self._net_disabled_guide_widget.setVisible(True)
            except RuntimeError:
                pass

            # Remove any process rows from layout
            for name in list(self._net_rows.keys()):
                try:
                    row = self._net_rows.pop(name)
                    self._net_list_layout.removeWidget(row['container'])
                    row['container'].deleteLater()
                except Exception:
                    pass
            return
        else:
            try:
                if hasattr(self, '_net_disabled_guide_widget') and self._net_disabled_guide_widget is not None:
                    self._net_disabled_guide_widget.setVisible(False)
            except RuntimeError:
                pass

        processes = data.get('processes', [])

        # Always hide loading placeholder once first data tick arrives
        try:
            if hasattr(self, '_net_placeholder_widget') and self._net_placeholder_widget is not None:
                self._net_placeholder_widget.setVisible(False)
            if hasattr(self, '_net_placeholder') and self._net_placeholder is not None:
                self._net_placeholder.setVisible(False)
        except RuntimeError:
            pass

        if not processes:
            return

        max_total = max((p['total_bytes'] for p in processes), default=1) or 1

        for i, entry in enumerate(processes):
            name = entry['name']
            total_bytes = entry['total_bytes']
            rate_bytes = entry['rate_bytes']
            exe_path = entry.get('exe_path')
            history = entry.get('history', [])

            total_str = self._fmt_net_bytes(total_bytes)
            if rate_bytes >= 1024 * 1024:
                rate_str = f"{rate_bytes / (1024 * 1024):.1f} MB/s"
            elif rate_bytes >= 1024:
                rate_str = f"{rate_bytes / 1024:.1f} KB/s"
            elif rate_bytes > 0:
                rate_str = f"{rate_bytes} B/s"
            else:
                rate_str = ""
            display_str = f"{total_str}  {rate_str}".strip() if rate_str else total_str
            pct = int((total_bytes / max_total) * 100)

            if name in self._net_rows:
                try:
                    row = self._net_rows[name]
                    row['size_lbl'].setText(display_str)
                    # Keep the relative-usage bar in sync on every tick.
                    # pct is recalculated each update against the current max_total
                    # so bars always reflect the current top-consumer proportions.
                    row['prog'].setValue(pct)
                    hist_data = None
                    if row.get('is_expanded') and current_filter != "Total History":
                        if hasattr(self, '_net_monitor') and self._net_monitor is not None:
                            hist_data = self._net_monitor.fetch_historical_points(name, current_filter)
                            
                    # Only update the chart when the panel is visible (is_expanded) to avoid
                    # wasting CPU computing graph data for collapsed rows every second.
                    if row.get('is_expanded'):
                        row['detail'].set_data(history, explicit_filter=current_filter, historical_points=hist_data)
                    
                    # Ensure the widget is at the correct sorted position in the layout
                    # Index i because we want it to match the 'processes' list order.
                    if self._net_list_layout.indexOf(row['container']) != i:
                        self._net_list_layout.insertWidget(i, row['container'])
                except RuntimeError:
                    del self._net_rows[name]
            else:
                try:
                    self._build_net_row(name, exe_path, display_str, pct, i)
                except Exception:
                    pass

        # Cleanup: Remove rows that are no longer in the top 15 active/active-ish processes
        active_names = {p['name'] for p in processes}
        for name in list(self._net_rows.keys()):
            if name not in active_names:
                try:
                    row = self._net_rows.pop(name)
                    self._net_list_layout.removeWidget(row['container'])
                    row['container'].deleteLater()
                except (RuntimeError, KeyError):
                    pass

    def _build_net_row(self, name, exe_path, display_str, pct, position):
        """Create and append a new process row to the network list.

        Only called once per unique process name. Subsequent ticks only update
        the mutable widget refs stored in self._net_rows.

        Args:
            name:         Process exe name, e.g. "chrome.exe".
            exe_path:     Absolute path to exe for icon extraction, or None.
            display_str:  Formatted label text (total + rate).
            pct:          Progress bar fill percentage 0-100.
            position:     The index in the layout to insert the widget at.
        """
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QFileIconProvider, QWidget
        from PySide6.QtCore import QFileInfo, QPropertyAnimation, QEasingCurve, Qt
        import os

        layout = self._net_list_layout
        
        container = QWidget()
        container.setObjectName(f"netContainer_{name}")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        item_frame = QFrame()
        item_frame.setObjectName("netItemFrame")
        item_frame.setFixedHeight(50)
        item_frame.setCursor(Qt.PointingHandCursor)
        item_frame.setStyleSheet("""
            QFrame#netItemFrame { 
                background: #252528; 
                border-radius: 6px; 
                border: 1px solid #2A2A2A;
            }
            QFrame#netItemFrame:hover { 
                background: #2F1A13; 
                border: 1px solid #552718;
            }
        """)

        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(12, 6, 12, 6)
        item_layout.setSpacing(12)

        # Icon label
        icon_lbl = QLabel()
        icon_lbl.setObjectName(f"netIcon_{name}")
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setStyleSheet("background: transparent;")

        pixmap = None
        provider = self._net_icon_provider
        try:
            if name.lower() in ('system', 'idle'):
                icon = provider.icon(QFileIconProvider.IconType.Computer)
                if not icon.isNull():
                    pixmap = icon.pixmap(24, 24)
            elif exe_path and os.path.exists(exe_path):
                icon = provider.icon(QFileInfo(exe_path))
                if not icon.isNull():
                    pixmap = icon.pixmap(24, 24)
            else:
                icon = provider.icon(QFileInfo(name))
                if not icon.isNull():
                    pixmap = icon.pixmap(24, 24)
        except Exception:
            pass

        # Deterministic color per name so the same app always gets the same color
        colors = ['#ff6b35', '#22d3ee', '#a78bfa', '#fbbf24', '#f87171',
                  '#c084fc', '#4ade80', '#60a5fa', '#fcd34d']
        c = colors[hash(name) % len(colors)]

        if pixmap and not pixmap.isNull():
            icon_lbl.setPixmap(pixmap)
        else:
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setStyleSheet(f"background-color: {c}; border-radius: 3px;")

        # Name + rate row
        right_layout = QVBoxLayout()
        right_layout.setSpacing(1)
        right_layout.setAlignment(Qt.AlignVCenter)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(name)
        name_lbl.setObjectName(f"netName_{name}")
        name_lbl.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 700; background: transparent;")

        size_lbl = QLabel(display_str)
        size_lbl.setObjectName(f"netSize_{name}")
        size_lbl.setStyleSheet("color: #FDA903; font-size: 11px; font-weight: 600; font-family: 'Orbitron'; background: transparent;")

        top_row.addWidget(name_lbl)
        top_row.addStretch()
        top_row.addWidget(size_lbl)

        prog = QProgressBar()
        prog.setObjectName(f"netProg_{name}")
        prog.setFixedHeight(4)
        prog.setTextVisible(False)
        prog.setValue(pct)
        prog.setStyleSheet(f"""
            QProgressBar {{ background-color: #1A1A1A; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c}, stop:1 #ffffff); border-radius: 2px; }}
        """)

        right_layout.addLayout(top_row)
        right_layout.addWidget(prog)
        item_layout.addWidget(icon_lbl)
        item_layout.addLayout(right_layout)
        
        detail_panel = NetworkDetailPanel(color_hex=c, parent=container)
        
        container_layout.addWidget(item_frame)
        container_layout.addWidget(detail_panel)
        
        # Click interaction
        row_dict = {'container': container, 'frame': item_frame, 'size_lbl': size_lbl, 'prog': prog, 'detail': detail_panel, 'is_expanded': False, 'anim': None}
        self._net_rows[name] = row_dict
        
        def toggle_expansion(event):
            is_expanded = row_dict['is_expanded']
            
            # Collapse others
            for other_name, other_row in self._net_rows.items():
                if other_name != name and other_row['is_expanded']:
                    other_row['is_expanded'] = False
                    anim = other_row['anim']
                    if anim:
                        anim.stop()
                    anim = QPropertyAnimation(other_row['detail'], b"maximumHeight")
                    anim.setDuration(300)
                    anim.setStartValue(other_row['detail'].height())
                    anim.setEndValue(0)
                    anim.setEasingCurve(QEasingCurve.OutCubic)
                    other_row['anim'] = anim
                    anim.start()
                    
            target_height = 0 if is_expanded else 160
            row_dict['is_expanded'] = not is_expanded
            
            anim = row_dict['anim']
            if anim:
                anim.stop()
            anim = QPropertyAnimation(row_dict['detail'], b"maximumHeight")
            anim.setDuration(300)
            anim.setStartValue(row_dict['detail'].height())
            anim.setEndValue(target_height)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            row_dict['anim'] = anim
            anim.start()

        item_frame.mousePressEvent = toggle_expansion

        layout.insertWidget(position, container)

    @staticmethod
    def _fmt_net_bytes(b):
        """Format raw byte count as human-readable string (GB / MB / KB / B)."""
        if b >= 1024 ** 3:
            return f"{b / (1024 ** 3):.2f} GB"
        elif b >= 1024 ** 2:
            return f"{b / (1024 ** 2):.1f} MB"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    def _create_header(self):
        """Create header with title and update interval control."""
        header = QWidget()
        header.setObjectName("hardwareHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title Layout (HELXTATS + LHM Panel Button side-by-side)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(12)

        title = QLabel("HELXTATS")
        title.setObjectName("hardwareTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 24px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")
        title_layout.addWidget(title)

        # LHM Panel Button right next to HELXTATS title with full icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "libre.png")
        self.btn_open_lhm = HeaderLhmIconButton(icon_path)
        self.btn_open_lhm.clicked.connect(lambda: self._start_librehwmon(silent_launch=False))
        title_layout.addWidget(self.btn_open_lhm, alignment=Qt.AlignVCenter)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        # Update interval control — wrapped in a single container for easy show/hide
        self._interval_container = QWidget()
        self._interval_container.setObjectName("intervalContainer")
        interval_layout = QHBoxLayout(self._interval_container)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.setSpacing(4)
        
        interval_label = QLabel("Update Interval:")
        interval_label.setObjectName("intervalLabel")
        interval_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        interval_layout.addWidget(interval_label)
        
        self.interval_input = QLineEdit()
        self.interval_input.setObjectName("intervalInput")
        self.interval_input.setText("500")
        self.interval_input.setFixedWidth(60)
        self.interval_input.setAlignment(Qt.AlignCenter)
        
        # QIntValidator with a wide range so intermediate values (e.g. "1", "50") are
        # never marked Invalid — the actual 100-5000 clamping happens inside the slot.
        validator = QIntValidator(1, 9999, self)
        self.interval_input.setValidator(validator)

        # editingFinished fires on focus-loss; returnPressed fires on Enter key press.
        # Both are needed because QIntValidator can suppress editingFinished on Enter
        # when the field contains an "Intermediate" value like "1" or "50".
        self.interval_input.editingFinished.connect(self._on_interval_input_finished)
        self.interval_input.returnPressed.connect(self._on_interval_input_finished)
        
        self.interval_input.setStyleSheet("""
            QLineEdit {
                background: rgba(30, 30, 30, 0.9);
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px;
                font-family: 'Orbitron';
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit:focus {
                background: rgba(40, 40, 40, 1.0);
            }
        """)
        interval_layout.addWidget(self.interval_input)
        
        ms_label = QLabel("ms")
        ms_label.setStyleSheet("color: #888888; font-size: 11px; font-weight: 600; margin-left: 2px;")
        interval_layout.addWidget(ms_label)
        
        header_layout.addWidget(self._interval_container, 0, Qt.AlignRight)
        
        return header
    
    def _create_overview_page(self):
        """Create the main overview dashboard."""
        scroll = SmoothScrollArea()
        scroll.setObjectName("overviewScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea#overviewScrollArea, QWidget#overviewScrollArea > QWidget { background: transparent; border: none; }")
        
        content = QWidget()
        content.setObjectName("overviewContent")
        content.setStyleSheet("QWidget#overviewContent { background: transparent; }")
        
        # Outer vertical layout to keep cards at natural height (no vertical stretch)
        outer_layout = QVBoxLayout(content)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        # Inner horizontal layout for RAM Cleaner + Stats Grid
        inner_widget = QWidget()
        main_layout = QHBoxLayout(inner_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)
        
        # LEFT COLUMN - RAM Cleaner
        left_col = self._create_ram_cleaner_section()
        main_layout.addWidget(left_col)
        
        # RIGHT COLUMN - Stats grid
        right_col = self._create_stats_grid()
        main_layout.addWidget(right_col, stretch=1)
        
        outer_layout.addWidget(inner_widget)
        outer_layout.addStretch()  # Push everything to top, prevent vertical stretching
        
        scroll.setWidget(content)
        return scroll
    
    def _create_ram_cleaner_section(self):
        """Create the Quick Setup Booster section, mirroring the Booster tab layout."""
        container = QFrame()
        container.setObjectName("ramCleanerContainer")
        container.setFixedWidth(220)
        container.setStyleSheet("""
            QFrame#ramCleanerContainer {
                background: transparent;
                border: none;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Title - matches the Booster tab title style
        title = QLabel("BOOSTER")
        title.setObjectName("ramCleanerTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: 700; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Circular gauge (Quick Setup overview gauge, separate from Booster tab gauge)
        self.overview_ram_gauge = CircularGauge()
        self.overview_ram_gauge.setObjectName("overviewRamGauge")
        self.overview_ram_gauge.setFixedSize(180, 180)
        layout.addWidget(self.overview_ram_gauge, alignment=Qt.AlignCenter)

        # Items to be optimized label - synced from _update_total_items_count
        self.qs_items_label = QLabel("0 items to be optimized")
        self.qs_items_label.setObjectName("qsItemsLabel")
        self.qs_items_label.setStyleSheet("color: #e0e0e0; font-size: 14px; background: transparent;")
        self.qs_items_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.qs_items_label)

        # MANUAL BOOST button - triggers full boost (not just RAM clean)
        self.clean_btn = QPushButton("MANUAL BOOST")
        self.clean_btn.setObjectName("cleanRamButton")
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.setFixedHeight(40)
        # Always triggers the full manual boost, same as the Booster tab button
        self.clean_btn.clicked.connect(self._run_manual_boost)
        self.clean_btn.setStyleSheet("""
            QPushButton#cleanRamButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#cleanRamButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        layout.addWidget(self.clean_btn)

        # Keep custom mode flag for internal compatibility (no button shown)
        self._custom_mode_active = False

        layout.addStretch()
        return container
    
    def _create_stats_grid(self):
        """Create the stats grid with charts."""
        container = QWidget()
        container.setObjectName("statsGridContainer")
        container.setStyleSheet("QWidget#statsGridContainer { background: transparent; }")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        
        # Configure pyqtgraph with transparent background and lightweight rasterization
        pg.setConfigOptions(antialias=False, background=None, foreground='#888888')
        
        # CPU Usage card with chart
        cpu_card = StatsCard("CPU Usage")
        cpu_card.setObjectName("cpuUsageCard")
        self.cpu_chart = pg.PlotWidget()
        self.cpu_chart.setObjectName("cpuChart")
        self.cpu_chart.setBackground(None)
        self.cpu_chart.setStyleSheet("background: transparent;")
        self.cpu_chart.setFixedHeight(100)
        self.cpu_chart.showGrid(x=False, y=True, alpha=0.3)
        self.cpu_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.cpu_chart.hideAxis('bottom')
        self.cpu_chart.getAxis('left').setWidth(30)
        self.cpu_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.cpu_chart.enableAutoRange(axis='x')   # X auto-range
        self.cpu_curve = self.cpu_chart.plot(pen=pg.mkPen('#FF5B06', width=2))
        try:
            self.cpu_curve.setDownsampling(mode='peak', auto=True)
            self.cpu_curve.setClipToView(True)
        except Exception:
            pass
        # Text label at leading edge showing current value
        self.cpu_leading_text = pg.TextItem(text='0%', color='#FF5B06', anchor=(0, 0.5))
        self.cpu_leading_text.setFont(QFont('Orbitron', 9, QFont.Bold))
        self.cpu_chart.addItem(self.cpu_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.cpu_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.cpu_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.cpu_chart)
        cpu_card.addWidget(self.cpu_chart)
        
        # CPU stats row
        cpu_stats = QHBoxLayout()
        self.cpu_percent_label = QLabel("0%")
        self.cpu_percent_label.setObjectName("cpuPercentLabel")
        self.cpu_percent_label.setStyleSheet("color: #FF5B06; font-size: 24px; font-weight: 700; background: transparent;")
        cpu_stats.addWidget(self.cpu_percent_label)
        self.cpu_freq_label = QLabel("0.00 GHz")
        self.cpu_freq_label.setObjectName("cpuFreqLabel")
        self.cpu_freq_label.setStyleSheet("""
            QLabel#cpuFreqLabel {
                color: #888888;
                font-size: 12px;
                background: transparent;
            }
            QLabel#cpuFreqLabel:hover {
                color: #ffffff;
            }
        """)
        self.cpu_freq_label.setCursor(Qt.PointingHandCursor)
        self.cpu_freq_label.setToolTip("Right click to toggle frequency unit (GHz / MHz)")
        self.cpu_freq_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cpu_freq_label.customContextMenuRequested.connect(self._show_cpu_freq_context_menu)
        cpu_stats.addWidget(self.cpu_freq_label)
        cpu_stats.addStretch()
        cpu_stats_widget = QWidget()
        cpu_stats_widget.setObjectName("cpuStatsWidget")
        cpu_stats_widget.setLayout(cpu_stats)
        cpu_card.addWidget(cpu_stats_widget)
        grid.addWidget(cpu_card, 0, 0)
        
        # RAM Usage card with chart (same as CPU)
        ram_card = StatsCard("RAM Usage")
        ram_card.setObjectName("ramUsageCard")
        self.ram_chart = pg.PlotWidget()
        self.ram_chart.setObjectName("ramChart")
        self.ram_chart.setBackground(None)
        self.ram_chart.setStyleSheet("background: transparent;")
        self.ram_chart.setFixedHeight(100)
        self.ram_chart.showGrid(x=False, y=True, alpha=0.3)
        self.ram_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.ram_chart.hideAxis('bottom')
        self.ram_chart.getAxis('left').setWidth(30)
        self.ram_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.ram_chart.enableAutoRange(axis='x')   # X auto-range
        self.ram_curve = self.ram_chart.plot(pen=pg.mkPen('#FDA903', width=2))
        try:
            self.ram_curve.setDownsampling(mode='peak', auto=True)
            self.ram_curve.setClipToView(True)
        except Exception:
            pass
        # Text label at leading edge showing current value
        self.ram_leading_text = pg.TextItem(text='0%', color='#FDA903', anchor=(0, 0.5))
        self.ram_leading_text.setFont(QFont('Orbitron', 9, QFont.Bold))
        self.ram_chart.addItem(self.ram_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.ram_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.ram_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.ram_chart)
        ram_card.addWidget(self.ram_chart)
        
        # RAM stats row
        ram_stats = QHBoxLayout()
        self.ram_percent_label = QLabel("0%")
        self.ram_percent_label.setObjectName("ramPercentLabel")
        self.ram_percent_label.setStyleSheet("color: #FDA903; font-size: 24px; font-weight: 700; background: transparent;")
        ram_stats.addWidget(self.ram_percent_label)
        self.qs_ram_stats_label = QLabel("0 GB / 0 GB")
        self.qs_ram_stats_label.setObjectName("qsRamStatsLabel")
        self.qs_ram_stats_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        ram_stats.addWidget(self.qs_ram_stats_label)
        ram_stats.addStretch()
        ram_stats_widget = QWidget()
        ram_stats_widget.setObjectName("ramStatsWidget")
        ram_stats_widget.setLayout(ram_stats)
        ram_card.addWidget(ram_stats_widget)
        grid.addWidget(ram_card, 0, 1)
        
        # Network Usage card (compact - no icons)
        network_card = StatsCard("Network")
        network_card.setObjectName("networkUsageCard")
        network_card.setMaximumHeight(70)  # Compact height
        net_layout = QHBoxLayout()
        net_layout.setSpacing(12)
        net_layout.setContentsMargins(0, 0, 0, 0)
        
        # Download label with inline arrow
        self.download_label = QLabel("↓ 0 Mbps")
        self.download_label.setObjectName("downloadLabel")
        self.download_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600; background: transparent;")
        net_layout.addWidget(self.download_label)
        
        # Upload label with inline arrow
        self.upload_label = QLabel("↑ 0 Mbps")
        self.upload_label.setObjectName("uploadLabel")
        self.upload_label.setStyleSheet("color: #f97316; font-size: 11px; font-weight: 600; background: transparent;")
        net_layout.addWidget(self.upload_label)
        
        net_layout.addStretch()
        
        net_widget = QWidget()
        net_widget.setObjectName("networkWidget")
        net_widget.setLayout(net_layout)
        network_card.addWidget(net_widget)
        grid.addWidget(network_card, 1, 1)
        
        # Disk S.M.A.R.T card (below Network)
        disk_health_card = StatsCard("Disk S.M.A.R.T")
        disk_health_card.setObjectName("diskHealthCard")
        disk_health_card.setMinimumHeight(120)
        
        # Container for disk health items (vertical layout with scroll)
        self.disk_health_container = QVBoxLayout()
        self.disk_health_container.setSpacing(4)
        self.disk_health_container.setContentsMargins(0, 0, 0, 0)
        
        disk_health_content = QWidget()
        disk_health_content.setObjectName("diskHealthContent")
        disk_health_content.setLayout(self.disk_health_container)
        disk_health_content.setStyleSheet("background: transparent;")
        
        # Scroll area for disk health
        disk_scroll = SmoothScrollArea()
        disk_scroll.setObjectName("diskHealthScroll")
        disk_scroll.setWidgetResizable(True)
        disk_scroll.setWidget(disk_health_content)
        disk_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        disk_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        disk_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.05);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.2);
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        disk_scroll.setMinimumHeight(80)
        
        disk_health_card.addWidget(disk_scroll)
        grid.addWidget(disk_health_card, 2, 1)
        
        # Disk Usage card with speed chart + usage bars
        disk_card = StatsCard("Disk Usage")
        disk_card.setObjectName("diskUsageCard")
        
        # Disk usage chart - single line showing overall disk usage %
        self.disk_chart = pg.PlotWidget()
        self.disk_chart.setObjectName("diskChart")
        self.disk_chart.setBackground(None)
        self.disk_chart.setStyleSheet("background: transparent;")
        self.disk_chart.setFixedHeight(80)
        self.disk_chart.showGrid(x=False, y=True, alpha=0.3)
        self.disk_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.disk_chart.hideAxis('bottom')
        self.disk_chart.getAxis('left').setWidth(30)
        self.disk_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.disk_usage_curve = self.disk_chart.plot(pen=pg.mkPen('#f97316', width=2), name='Usage')
        try:
            self.disk_usage_curve.setDownsampling(mode='peak', auto=True)
            self.disk_usage_curve.setClipToView(True)
        except Exception:
            pass
        # Text label at leading edge showing current value
        self.disk_leading_text = pg.TextItem(text='0%', color='#f97316', anchor=(0, 0.5))
        self.disk_leading_text.setFont(QFont('Orbitron', 9, QFont.Bold))
        self.disk_chart.addItem(self.disk_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.disk_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.disk_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.disk_chart)
        disk_card.addWidget(self.disk_chart)
        
        # Disk usage stats row (similar to CPU)
        disk_stats = QHBoxLayout()
        self.disk_percent_label = QLabel("0%")
        self.disk_percent_label.setObjectName("diskPercentLabel")
        self.disk_percent_label.setStyleSheet("color: #f97316; font-size: 24px; font-weight: 700; background: transparent;")
        disk_stats.addWidget(self.disk_percent_label)
        disk_stats.addStretch()
        disk_stats_widget = QWidget()
        disk_stats_widget.setObjectName("diskStatsWidget")
        disk_stats_widget.setLayout(disk_stats)
        disk_card.addWidget(disk_stats_widget)
        
        # Disk usage bars container
        self.disk_bars_container = QVBoxLayout()
        disk_bars_widget = QWidget()
        disk_bars_widget.setObjectName("diskBarsWidget")
        disk_bars_widget.setLayout(self.disk_bars_container)
        disk_card.addWidget(disk_bars_widget)
        grid.addWidget(disk_card, 1, 0, 2, 1)  # Span 2 rows in column 0
        
        # Hardware Health card (compact + responsive width)
        health_card = StatsCard("System Vitals")
        health_card.setObjectName("healthCard")
        health_card.setMaximumHeight(165)
        
        # Check if LibreHardwareMonitor or HWiNFO is available for temps
        try:
            from integrations.tools_downloader import (
                is_librehwmon_available, is_hwinfo_available,
                LIBREHWMON_DIR, HWINFO_DIR
            )
            self._librehwmon_available = is_librehwmon_available()
            self._hwinfo_available = is_hwinfo_available()
            self._hwmon_available = self._librehwmon_available or self._hwinfo_available
        except ImportError:
            self._librehwmon_available = False
            self._hwinfo_available = False
            self._hwmon_available = False
        
        # ── System Vitals: QGridLayout table ──────────────────────────────────
        # Grid column mapping:
        #  0 = component label  1 = VLine  2 = Temp  3 = VLine  4 = Load  5 = VLine  6 = Power
        # Grid row mapping:
        #  0 = column headers   1 = HLine  2 = CPU   3 = HLine  4 = iGPU  5 = HLine  6 = dGPU
        vitals_grid = QGridLayout()
        vitals_grid.setSpacing(0)
        vitals_grid.setContentsMargins(6, 4, 6, 4)
        # Give fixed widths to value columns so they stay aligned regardless of content
        vitals_grid.setColumnMinimumWidth(0, 40)   # label
        vitals_grid.setColumnMinimumWidth(2, 50)   # temp
        vitals_grid.setColumnMinimumWidth(4, 44)   # load
        vitals_grid.setColumnMinimumWidth(6, 44)   # power
        vitals_grid.setColumnStretch(0, 1)
        vitals_grid.setColumnStretch(2, 1)
        vitals_grid.setColumnStretch(4, 1)
        vitals_grid.setColumnStretch(6, 1)

        def _vline():
            """Thin vertical separator between columns."""
            f = QFrame()
            f.setFrameShape(QFrame.VLine)
            f.setStyleSheet("background: #2a2a3a; max-width: 1px; border: none;")
            f.setFixedWidth(1)
            return f

        def _hline(cols=7):
            """Thin horizontal separator spanning all grid columns."""
            f = QFrame()
            f.setFrameShape(QFrame.HLine)
            f.setStyleSheet("background: #2a2a3a; max-height: 1px; border: none;")
            f.setFixedHeight(1)
            return f

        def _hdr(text, align=Qt.AlignCenter):
            """Small column header label."""
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #555577; font-size: 9px; font-weight: 600; background: transparent;")
            lbl.setAlignment(align)
            return lbl

        # Row 0 — column headers
        vitals_grid.addWidget(_hdr("", Qt.AlignLeft),        0, 0)
        vitals_grid.addWidget(_hdr("Temp"),                  0, 2)
        vitals_grid.addWidget(_hdr("Load"),                  0, 4)
        vitals_grid.addWidget(_hdr("Pwr"),                   0, 6)
        # Vertical separators in header row
        vitals_grid.addWidget(_vline(), 0, 1, 7, 1)  # span all 7 data rows + header
        vitals_grid.addWidget(_vline(), 0, 3, 7, 1)
        vitals_grid.addWidget(_vline(), 0, 5, 7, 1)

        # Row 1 — horizontal separator under headers
        vitals_grid.addWidget(_hline(), 1, 0, 1, 7)

        # ── CPU Row (row 2) ──────────────────────────────
        cpu_lbl = QLabel("CPU")
        cpu_lbl.setObjectName("cpuHeader")
        cpu_lbl.setStyleSheet("color: #ff6b35; font-size: 11px; font-weight: bold; background: transparent;")
        cpu_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        vitals_grid.addWidget(cpu_lbl, 2, 0)

        self.cpu_temp_value = QLabel("--°C")
        self.cpu_temp_value.setObjectName("cpuTempValue")
        self.cpu_temp_value.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 600; background: transparent;")
        self.cpu_temp_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.cpu_temp_value, 2, 2)

        self.cpu_load_value = QLabel("--%")
        self.cpu_load_value.setObjectName("cpuLoadValue")
        self.cpu_load_value.setStyleSheet("color: #60a5fa; font-size: 12px; font-weight: 500; background: transparent;")
        self.cpu_load_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.cpu_load_value, 2, 4)

        self.cpu_power_value = QLabel("--W")
        self.cpu_power_value.setObjectName("cpuPowerValue")
        self.cpu_power_value.setStyleSheet("color: #fbbf24; font-size: 12px; font-weight: 500; background: transparent;")
        self.cpu_power_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.cpu_power_value, 2, 6)

        # Row 3 — horizontal separator
        vitals_grid.addWidget(_hline(), 3, 0, 1, 7)

        # ── iGPU Row (row 4) ─────────────────────────────
        igpu_lbl = QLabel("iGPU")
        igpu_lbl.setObjectName("igpuHeader")
        igpu_lbl.setStyleSheet("color: #22d3ee; font-size: 11px; font-weight: bold; background: transparent;")
        igpu_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        vitals_grid.addWidget(igpu_lbl, 4, 0)

        self.igpu_temp_value = QLabel("--°C")
        self.igpu_temp_value.setObjectName("igpuTempValue")
        self.igpu_temp_value.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 600; background: transparent;")
        self.igpu_temp_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.igpu_temp_value, 4, 2)

        self.igpu_load_value = QLabel("--%")
        self.igpu_load_value.setObjectName("igpuLoadValue")
        self.igpu_load_value.setStyleSheet("color: #60a5fa; font-size: 12px; font-weight: 500; background: transparent;")
        self.igpu_load_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.igpu_load_value, 4, 4)

        self.igpu_power_value = QLabel("--W")
        self.igpu_power_value.setObjectName("igpuPowerValue")
        self.igpu_power_value.setStyleSheet("color: #fbbf24; font-size: 12px; font-weight: 500; background: transparent;")
        self.igpu_power_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.igpu_power_value, 4, 6)

        # Row 5 — horizontal separator
        vitals_grid.addWidget(_hline(), 5, 0, 1, 7)

        # ── dGPU Row (row 6) ─────────────────────────────
        dgpu_lbl = QLabel("dGPU")
        dgpu_lbl.setObjectName("dgpuHeader")
        dgpu_lbl.setStyleSheet("color: #a78bfa; font-size: 11px; font-weight: bold; background: transparent;")
        dgpu_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        vitals_grid.addWidget(dgpu_lbl, 6, 0)

        self.dgpu_temp_value = QLabel("--°C")
        self.dgpu_temp_value.setObjectName("dgpuTempValue")
        self.dgpu_temp_value.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 600; background: transparent;")
        self.dgpu_temp_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.dgpu_temp_value, 6, 2)

        self.dgpu_load_value = QLabel("--%")
        self.dgpu_load_value.setObjectName("dgpuLoadValue")
        self.dgpu_load_value.setStyleSheet("color: #a78bfa; font-size: 12px; font-weight: 500; background: transparent;")
        self.dgpu_load_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.dgpu_load_value, 6, 4)

        self.dgpu_power_value = QLabel("--W")
        self.dgpu_power_value.setObjectName("dgpuPowerValue")
        self.dgpu_power_value.setStyleSheet("color: #fbbf24; font-size: 12px; font-weight: 500; background: transparent;")
        self.dgpu_power_value.setAlignment(Qt.AlignCenter)
        vitals_grid.addWidget(self.dgpu_power_value, 6, 6)

        # Wrap grid in a container widget to add to StatsCard
        health_inner = QWidget()
        health_inner.setObjectName("healthInner")
        health_inner.setLayout(vitals_grid)

        
        health_card.addWidget(health_inner)
        grid.addWidget(health_card, 3, 0, 1, 2)  # Make Health card span both columns
        
        return container

    def _show_cpu_freq_context_menu(self, pos):
        """Show context menu on CPU frequency label to switch between GHz and MHz."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setObjectName("cpuFreqContextMenu")
        menu.setStyleSheet("""
            QMenu#cpuFreqContextMenu {
                background-color: #1e1e24;
                color: #e0e0e0;
                border: 1px solid #3c3c45;
                border-radius: 6px;
                padding: 4px;
                font-family: 'Orbitron';
                font-size: 11px;
            }
            QMenu#cpuFreqContextMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu#cpuFreqContextMenu::item:selected {
                background-color: #FF5B06;
                color: #ffffff;
            }
        """)
        
        ghz_action = menu.addAction("GHz (Gigahertz)")
        ghz_action.setCheckable(True)
        ghz_action.setChecked(getattr(self, '_cpu_freq_unit', 'GHz') == "GHz")
        
        mhz_action = menu.addAction("MHz (Megahertz)")
        mhz_action.setCheckable(True)
        mhz_action.setChecked(getattr(self, '_cpu_freq_unit', 'GHz') == "MHz")
        
        action = menu.exec_(self.cpu_freq_label.mapToGlobal(pos))
        if action == ghz_action:
            self._cpu_freq_unit = "GHz"
            self._update_stats()
        elif action == mhz_action:
            self._cpu_freq_unit = "MHz"
            self._update_stats()
    
    def _enforce_chart_y_range(self, chart, min_val: float, max_val: float):
        """Enforce Y-axis range on chart (prevents View All from changing it)."""
        # Block signals to avoid recursion
        chart.blockSignals(True)
        chart.getPlotItem().setYRange(min_val, max_val, padding=0)
        chart.blockSignals(False)
    
    def _setup_mutual_exclusive_drag(self, chart):
        """Setup mutual exclusive X/Y axis dragging for a chart.
        When dragging starts, detect direction and lock the other axis."""
        chart.setMouseEnabled(x=True, y=True)  # Enable both axes
        chart._drag_axis = None  # Track which axis is being dragged
        chart._drag_start_pos = None
        
        # Store original mousePressEvent and mouseMoveEvent
        original_mouse_press = chart.getPlotItem().vb.mousePressEvent
        original_mouse_move = chart.getPlotItem().vb.mouseDragEvent
        original_mouse_release = chart.getPlotItem().vb.mouseReleaseEvent
        
        def custom_drag_event(ev, axis=None):
            if ev.isStart():
                chart._drag_start_pos = ev.buttonDownPos()
                chart._drag_axis = None
            elif chart._drag_start_pos is not None and chart._drag_axis is None:
                # Determine drag direction based on movement
                delta = ev.pos() - chart._drag_start_pos
                if abs(delta.x()) > abs(delta.y()) * 1.5:
                    chart._drag_axis = 'x'
                    chart.setMouseEnabled(x=True, y=False)
                    # Pause auto-scroll for THIS chart only when user drags X-axis
                    self._pause_auto_scroll_for_chart(chart)
                elif abs(delta.y()) > abs(delta.x()) * 1.5:
                    chart._drag_axis = 'y'
                    chart.setMouseEnabled(x=False, y=True)
            
            if ev.isFinish():
                # Check if user scrolled to view head ONLY when drag finishes
                if chart._drag_axis == 'x':
                    # Get the history length for this chart
                    history_len = self._get_chart_history_len(chart)
                    self._check_auto_scroll_from_view(chart, history_len)
                chart._drag_axis = None
                chart._drag_start_pos = None
                chart.setMouseEnabled(x=True, y=True)  # Reset to both enabled
            
            original_mouse_move(ev, axis)
        
        chart.getPlotItem().vb.mouseDragEvent = custom_drag_event
    
    def _apply_style(self):
        """Apply main panel styling."""
        self.setStyleSheet("""
            QWidget#HardwarePanelWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f0f1a);
            }
        """)
    
    def _on_interval_input_finished(self):
        """Handle interval text input completion."""
        text = self.interval_input.text()
        if not text:
            return
        try:
            val = int(text)
            # Ensure it stays within logical bounds if validator didn't catch it
            val = max(100, min(val, 5000))
            self.interval_input.setText(str(val))
            self._on_interval_changed(val)
        except ValueError:
            pass

    def _on_interval_changed(self, value: int):
        """Handle update interval change."""
        self.monitor.set_update_interval(value)
        self._update_timer.setInterval(value)
        print(f"[Hardware] Update interval changed to {value}ms")
    
    def _update_stats(self):
        """Update all stats from hardware monitor."""
        # Throttled check for hardware monitor running status (every 5 updates)
        self._hwmon_check_counter += 1
        if self._hwmon_check_counter >= 5:
            self._hwmon_check_counter = 0
            self._update_hwmon_button_status()

        try:
            snapshot = self.monitor.get_snapshot()
            # Storage SMART data is fetched asynchronously via DriveInfoWorker to prevent blocking UI thread
            self._lhm_storage = getattr(self, '_lhm_storage', [])
            
            # RAM
            ram = snapshot["ram"]
            ram_percent = ram["percent"]
            
            # Update RAM gauge (RAM Cleaner sub-page)
            if hasattr(self, 'ram_gauge'):
                self.ram_gauge.setValue(ram_percent)
                self.ram_gauge.setSubtitle(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update overview RAM gauge (Quick Setup page)
            if hasattr(self, 'overview_ram_gauge'):
                self.overview_ram_gauge.setValue(ram_percent)
                self.overview_ram_gauge.setSubtitle(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update RAM bar if exists
            if hasattr(self, 'ram_bar'):
                self.ram_bar.setValue(ram_percent)
            
            # Update RAM usage bar (Booster page)
            if hasattr(self, 'ram_usage_bar'):
                self.ram_usage_bar.setValue(ram_percent)
            


            # Update RAM stats label (Total/Used/Free) - RAM Cleaner left panel
            if hasattr(self, 'ram_stats_label'):
                self.ram_stats_label.setText(f"Total: {ram['total']:.1f} GB\nUsed: {ram['used']:.1f} GB\nFree: {ram['free']:.1f} GB")
            
            # Update Quick Setup RAM stats label (used / total format)
            if hasattr(self, 'qs_ram_stats_label'):
                self.qs_ram_stats_label.setText(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update RAM chart (append only, auto-scroll)
            self._ram_history.append(ram_percent)
            if hasattr(self, 'ram_curve'):
                self.ram_curve.setData(self._ram_history)
            # Auto-scroll X-axis to show last _chart_display_length points (only if not manually scrolling)
            if self._chart_auto_scroll['ram'] and hasattr(self, 'ram_chart'):
                x_max = len(self._ram_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.ram_chart.getPlotItem().setXRange(x_min, x_max + 3, padding=0)
            # Update leading edge text position and value
            if hasattr(self, 'ram_leading_text'):
                self.ram_leading_text.setText(f'{ram_percent:.0f}%')
                self.ram_leading_text.setPos(len(self._ram_history) - 1, ram_percent)
            if hasattr(self, 'ram_percent_label'):
                self.ram_percent_label.setText(f"{ram_percent:.0f}%")
            if hasattr(self, 'ram_stats_label'):
                self.ram_stats_label.setText(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # CPU (append only, auto-scroll)
            cpu = snapshot["cpu"]
            cpu_usage = cpu["usage"]
            self._cpu_history.append(cpu_usage)
            self.cpu_curve.setData(self._cpu_history)
            # Auto-scroll X-axis (only if not manually scrolling)
            if self._chart_auto_scroll['cpu']:
                x_max = len(self._cpu_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.cpu_chart.getPlotItem().setXRange(x_min, x_max + 3, padding=0)
            # Update leading edge text position and value
            self.cpu_leading_text.setText(f'{cpu_usage:.0f}%')
            self.cpu_leading_text.setPos(len(self._cpu_history) - 1, cpu_usage)
            self.cpu_percent_label.setText(f"{cpu_usage:.0f}%")
            freq_ghz = cpu.get('freq_ghz', 0)
            cores = cpu.get('cores', 0)
            threads = cpu.get('threads', 0)
            unit = getattr(self, '_cpu_freq_unit', 'GHz')
            if unit == 'MHz':
                freq_str = f"{freq_ghz * 1000:.0f} MHz"
            else:
                freq_str = f"{freq_ghz:.2f} GHz"
            self.cpu_freq_label.setText(f"{freq_str} • {cores} cores • {threads} threads")
            
            # Update disk activity chart (append only, auto-scroll)
            disk_io = snapshot.get("disk_io", {})
            read_speed = disk_io.get("read_mbps", 0)
            write_speed = disk_io.get("write_mbps", 0)
            # Calculate disk activity % (normalized to 500 MB/s max for SSD)
            max_speed = 500  # MB/s - typical SSD max
            disk_activity = min(100, (read_speed + write_speed) / max_speed * 100)
            self._disk_usage_history.append(disk_activity)
            self.disk_usage_curve.setData(self._disk_usage_history)
            # Auto-scroll X-axis (only if not manually scrolling)
            if self._chart_auto_scroll['disk']:
                x_max = len(self._disk_usage_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.disk_chart.getPlotItem().setXRange(x_min, x_max + 3, padding=0)
            # Update leading edge text position and value
            self.disk_leading_text.setText(f'{disk_activity:.1f}%')
            self.disk_leading_text.setPos(len(self._disk_usage_history) - 1, disk_activity)
            self.disk_percent_label.setText(f"{disk_activity:.1f}%")
            
            # Disk Usage bars (in-place update to avoid widget churn)
            disks = snapshot["disk"]
            
            # Update drive history for all drives (using deque for O(1) append)
            for disk in disks[:5]:  # Track up to 5 drives
                drive = disk["drive"]
                if drive not in self._drive_history:
                    self._drive_history[drive] = collections.deque([0] * 60, maxlen=60)
                    self._active_drives[drive] = False
                    # Assign fixed color for this drive
                    if drive not in self._drive_color_map:
                        color_idx = len(self._drive_color_map)
                        self._drive_color_map[drive] = self._drive_colors[color_idx % len(self._drive_colors)]
                # Update history (deque auto-evicts oldest)
                self._drive_history[drive].append(disk["percent"])
            
            # Update disk bars in-place (no widget recreation)
            if not hasattr(self, '_disk_bar_widgets'):
                self._disk_bar_widgets = {}
            
            current_drives = set()
            for i, disk in enumerate(disks[:5]):  # Show up to 5 drives
                drive = disk["drive"]
                current_drives.add(drive)
                percent = disk["percent"]
                used = disk["used"]
                total = disk["total"]
                
                # Clamp gradient stops to valid range [0.0, 1.0] (Bug #12)
                stop1 = min(percent / 100, 0.99)
                stop2 = min(stop1 + 0.01, 1.0)
                
                if drive not in self._disk_bar_widgets:
                    # Create new bar only for new drives
                    bar_label = QLabel()
                    bar_label.setFixedHeight(24)
                    self.disk_bars_container.addWidget(bar_label)
                    self._disk_bar_widgets[drive] = bar_label
                
                bar_label = self._disk_bar_widgets[drive]
                bar_label.setText(f"{drive} {percent:.1f}%        {used:.1f} GB / {total:.1f} GB")
                if abs(getattr(bar_label, '_last_percent', -1.0) - percent) >= 0.5:
                    bar_label._last_percent = percent
                    bar_label.setStyleSheet(f"""
                        QLabel {{
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                                stop:0 rgba(255,107,53,0.7), stop:{stop1} rgba(255,107,53,0.7), 
                                stop:{stop2} rgba(40,40,40,0.8), stop:1 rgba(40,40,40,0.8));
                            border: 1px solid rgba(100,100,100,0.4);
                            border-radius: 4px;
                            color: #e0e0e0;
                            font-size: 10px;
                            font-weight: 600;
                            padding-left: 8px;
                        }}
                    """)
            
            # Remove bars for drives that disappeared
            for drive in list(self._disk_bar_widgets.keys()):
                if drive not in current_drives:
                    widget = self._disk_bar_widgets.pop(drive)
                    self.disk_bars_container.removeWidget(widget)
                    widget.deleteLater()

            self._update_drive_metrics_from_snapshot(disks, disk_io)


            # Network
            net = snapshot["network"]
            self.download_label.setText(f"↓ {net['download_mbps']:.1f} Mbps")
            self.upload_label.setText(f"↑ {net['upload_mbps']:.1f} Mbps")
            
            # Disk SMART info is populated asynchronously by DriveInfoWorker
            display_disks = getattr(self, '_smart_disks', [])
            if not hasattr(self, '_smart_disk_row_widgets'):
                self._smart_disk_row_widgets = {}
            
            for pdisk in display_disks:
                model_name = pdisk['model']
                disk_key = pdisk.get('device', model_name)
                health_pct = pdisk['health_percent']
                status_color = "#4ade80" if pdisk['status'] == "OK" else "#f97316" if pdisk['status'] == "Warning" else "#ef4444"
                
                if disk_key not in self._smart_disk_row_widgets:
                    # Create row ONCE (Object Pooling)
                    disk_row = QWidget()
                    disk_row.setStyleSheet("background: transparent;")
                    main_layout = QVBoxLayout()
                    main_layout.setContentsMargins(8, 6, 8, 6)
                    main_layout.setSpacing(4)
                    
                    top_row = QHBoxLayout()
                    top_row.setSpacing(8)
                    
                    disp_name = model_name if len(model_name) <= 30 else model_name[:27] + "..."
                    drive_label = QLabel(disp_name)
                    drive_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 600; background: transparent;")
                    top_row.addWidget(drive_label, alignment=Qt.AlignVCenter)
                    
                    health_label = QLabel(pdisk['status'])
                    health_label.setStyleSheet(f"color: {status_color}; font-size: 10px; font-weight: 600; background: transparent;")
                    top_row.addWidget(health_label, alignment=Qt.AlignVCenter)
                    
                    disk_type = pdisk['type']
                    type_color = "#22d3ee" if disk_type == 'SSD' else "#fbbf24"
                    type_label = QLabel(disk_type)
                    type_label.setStyleSheet(f"""
                        color: {type_color}; 
                        font-size: 9px; 
                        font-weight: bold;
                        background: rgba({34 if disk_type == 'SSD' else 251}, {211 if disk_type == 'SSD' else 191}, {238 if disk_type == 'SSD' else 36}, 0.2);
                        padding: 1px 4px;
                        border-radius: 3px;
                    """)
                    top_row.addWidget(type_label, alignment=Qt.AlignVCenter)
                    
                    temp_label = QLabel(f"{pdisk['temp']:.0f}°C" if pdisk['temp'] > 0 else "")
                    temp_label.setStyleSheet("color: #60a5fa; font-size: 9px; background: transparent; font-weight: bold;")
                    top_row.addWidget(temp_label, alignment=Qt.AlignVCenter)
                    
                    top_row.addStretch()
                    
                    health_label_value = QLabel(f"{health_pct:.0f}%")
                    health_label_value.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: 600; background: transparent;")
                    top_row.addWidget(health_label_value, alignment=Qt.AlignVCenter)
                    
                    top_widget = QWidget()
                    top_widget.setLayout(top_row)
                    top_widget.setStyleSheet("background: transparent;")
                    main_layout.addWidget(top_widget)
                    
                    bar_row = QHBoxLayout()
                    bar_row.setSpacing(10)
                    bar = QProgressBar()
                    bar.setFixedHeight(6)
                    bar.setValue(int(health_pct))
                    bar.setTextVisible(False)
                    bar.setStyleSheet(f"""
                        QProgressBar {{
                            background: rgba(60, 60, 60, 0.5);
                            border-radius: 3px;
                            border: none;
                        }}
                        QProgressBar::chunk {{
                            background: {status_color};
                            border-radius: 3px;
                        }}
                    """)
                    bar_row.addWidget(bar, stretch=1)
                    
                    bar_widget = QWidget()
                    bar_widget.setLayout(bar_row)
                    bar_widget.setStyleSheet("background: transparent;")
                    main_layout.addWidget(bar_widget)
                    
                    disk_row.setLayout(main_layout)
                    self.disk_health_container.addWidget(disk_row)
                    
                    self._smart_disk_row_widgets[disk_key] = {
                        'temp_lbl': temp_label,
                        'health_lbl': health_label,
                        'pct_lbl': health_label_value,
                        'bar': bar
                    }
                else:
                    # Update existing pooled widget (Zero widget allocation)
                    w_dict = self._smart_disk_row_widgets[disk_key]
                    if pdisk['temp'] > 0:
                        w_dict['temp_lbl'].setText(f"{pdisk['temp']:.0f}°C")
                    w_dict['health_lbl'].setText(pdisk['status'])
                    w_dict['pct_lbl'].setText(f"{health_pct:.0f}%")
                    w_dict['bar'].setValue(int(health_pct))
            
            # Temps and Hardware Stats from LHM
            temps = snapshot["temps"]
            cpu_temp = temps.get("cpu_temp", 0)
            cpu_load = temps.get("cpu_load", 0)
            cpu_power = temps.get("cpu_power", temps.get("power", 0))
            
            igpu_temp = temps.get("igpu_temp", 0)
            igpu_load = temps.get("igpu_load", 0)
            igpu_power = temps.get("igpu_power", 0)
            
            dgpu_temp = temps.get("dgpu_temp", 0)
            dgpu_load = temps.get("dgpu_load", 0)
            dgpu_power = temps.get("dgpu_power", 0)
            
            # CPU Temp
            if cpu_temp > 0:
                self.cpu_temp_value.setText(f"{cpu_temp:.0f}°C")
                color = "#4ade80" if cpu_temp < 70 else "#f97316" if cpu_temp < 85 else "#ef4444"
                if getattr(self, '_cpu_temp_color', '') != color:
                    self._cpu_temp_color = color
                    self.cpu_temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;")
            
            # CPU Load
            if cpu_load >= 0 and cpu_temp > 0:
                self.cpu_load_value.setText(f"{cpu_load:.0f}%")
                color = "#60a5fa" if cpu_load < 80 else "#f97316" if cpu_load < 95 else "#ef4444"
                if getattr(self, '_cpu_load_color', '') != color:
                    self._cpu_load_color = color
                    self.cpu_load_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # CPU Power
            if cpu_power >= 0 and cpu_temp > 0:
                self.cpu_power_value.setText(f"{cpu_power:.0f}W")
                color = "#fbbf24" if cpu_power < 45 else "#f97316" if cpu_power < 65 else "#ef4444"
                if getattr(self, '_cpu_power_color', '') != color:
                    self._cpu_power_color = color
                    self.cpu_power_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # iGPU Temp
            if igpu_temp > 0:
                self.igpu_temp_value.setText(f"{igpu_temp:.0f}°C")
                color = "#4ade80" if igpu_temp < 75 else "#f97316" if igpu_temp < 90 else "#ef4444"
                if getattr(self, '_igpu_temp_color', '') != color:
                    self._igpu_temp_color = color
                    self.igpu_temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;")
            
            # iGPU Load
            if igpu_load >= 0 and igpu_temp > 0:
                self.igpu_load_value.setText(f"{igpu_load:.0f}%")
                color = "#60a5fa" if igpu_load < 80 else "#f97316" if igpu_load < 95 else "#ef4444"
                if getattr(self, '_igpu_load_color', '') != color:
                    self._igpu_load_color = color
                    self.igpu_load_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # iGPU Power
            if igpu_power >= 0 and igpu_temp > 0:
                self.igpu_power_value.setText(f"{igpu_power:.0f}W")
                color = "#fbbf24" if igpu_power < 30 else "#f97316" if igpu_power < 50 else "#ef4444"
                if getattr(self, '_igpu_power_color', '') != color:
                    self._igpu_power_color = color
                    self.igpu_power_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # dGPU Temp
            if dgpu_temp > 0:
                self.dgpu_temp_value.setText(f"{dgpu_temp:.0f}°C")
                color = "#4ade80" if dgpu_temp < 75 else "#f97316" if dgpu_temp < 90 else "#ef4444"
                if getattr(self, '_dgpu_temp_color', '') != color:
                    self._dgpu_temp_color = color
                    self.dgpu_temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;")
            
            # dGPU Load
            if dgpu_load >= 0 and dgpu_temp > 0:
                self.dgpu_load_value.setText(f"{dgpu_load:.0f}%")
                color = "#a78bfa" if dgpu_load < 80 else "#f97316" if dgpu_load < 95 else "#ef4444"
                if getattr(self, '_dgpu_load_color', '') != color:
                    self._dgpu_load_color = color
                    self.dgpu_load_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # dGPU Power
            if dgpu_power >= 0 and dgpu_temp > 0:
                self.dgpu_power_value.setText(f"{dgpu_power:.0f}W")
                color = "#fbbf24" if dgpu_power < 60 else "#f97316" if dgpu_power < 120 else "#ef4444"
                if getattr(self, '_dgpu_power_color', '') != color:
                    self._dgpu_power_color = color
                    self.dgpu_power_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
        
        
            # Auto-refresh Processes list every 3 seconds (smart in-place memory update - 0% frame drop)
            self._processes_refresh_counter += 1
            if self._processes_refresh_counter >= 6:  # Every 3 seconds
                self._processes_refresh_counter = 0
                if hasattr(self, '_current_ram_tab') and self._current_ram_tab == 1:
                    self._smart_update_processes_tab()
            
            # Auto-refresh Services status every 5 seconds (10 intervals at 500ms)
            self._services_refresh_counter += 1
            if self._services_refresh_counter >= 10:  # Every 5 seconds
                self._services_refresh_counter = 0
                # Refresh if Basic (tab 2) or Advanced (tab 3) Services tab is active
                if hasattr(self, '_current_ram_tab') and self._current_ram_tab in [2, 3]:
                    self._refresh_services_status()
        
        except Exception as e:
            print(f"[Hardware] Update error: {e}")
    

    def _clean_ram(self):
        """Clean RAM and show results (legacy fallback - Quick Setup now uses _run_manual_boost)."""
        from PySide6.QtWidgets import QApplication

        if hasattr(self, 'clean_btn'):
            self.clean_btn.setText("Cleaning...")
            self.clean_btn.setEnabled(False)

        # Stop timer and flush pending events
        self._update_timer.stop()
        QApplication.processEvents()

        # Apply essential optimizations when custom mode is ON
        if self._custom_mode_active:
            try:
                opt_results = self._apply_essential_optimizations()
                if opt_results:
                    print(f"[Hardware] Essential optimizations applied: {list(opt_results.keys())}")
            except Exception as e:
                print(f"[Hardware] Essential optimizations error: {e}")

        # Clean RAM via monitor
        result = self.monitor.clean_ram()
        before_used = 0
        freed = result.get("freed_gb", 0) if isinstance(result, dict) else 0
        cleaned = result.get("processes_cleaned", 0) if isinstance(result, dict) else 0

        if hasattr(self, 'clean_btn'):
            self.clean_btn.setText(f"Cleaned! ({freed:.2f} GB freed)")

        # Resume timer after 10 seconds and reset button
        def _resume_timer():
            if hasattr(self, 'clean_btn'):
                self.clean_btn.setText("MANUAL BOOST")
                self.clean_btn.setEnabled(True)
            self._update_timer.start(self.monitor.update_interval_ms)

        QTimer.singleShot(10000, _resume_timer)
        print(f"[Hardware] RAM cleaned: {cleaned} processes, ~{freed:.2f} GB freed")

    
    def showEvent(self, event):
        """Start updates when visible, defer heavy NetworkMonitor and LHM launch."""
        super().showEvent(event)
        
        # Ensure background temp monitoring thread is running
        self.monitor.start()
        
        if not self._update_timer.isActive():
            self._update_timer.start(self.monitor.update_interval_ms)
        
        # Defer NetworkMonitor and LHM initialization by 1s for zero-latency page switch
        def _deferred_show_tasks():
            if not hasattr(self, '_net_monitor_initialized') or not self._net_monitor_initialized:
                try:
                    from NetworkMonitor import NetworkMonitor
                    self._net_monitor_initialized = True
                    self._net_monitor = NetworkMonitor(parent=None)
                    self._net_monitor.data_updated.connect(self._on_net_data_updated)
                    self._net_monitor.start()
                    print("[Hardware] NetworkMonitor initialized (deferred)")
                except Exception as e:
                    print(f"[Hardware] Failed to initialize NetworkMonitor: {e}")
                    self._net_monitor_initialized = False
                
            # Hardware monitoring uses native hardware_wrapper.py (psutil/WMI/ctypes) by default.
            # External monitors (LHM/HWiNFO) are launched on-demand via explicit user button click.
            pass

        # Schedule safe working set compaction 600ms after layout renders
        def _compact_ws():
            try:
                from hardware_wrapper import trim_process_working_set
                trim_process_working_set()
            except Exception:
                pass
        QTimer.singleShot(600, _compact_ws)
            
        if getattr(self, '_is_boosting', False) and hasattr(self, '_boost_gradient_timer') and not self._boost_gradient_timer.isActive():
            self._boost_gradient_timer.start(33)
    
    def hideEvent(self, event):
        """Stop updates when hidden."""
        super().hideEvent(event)
        self._update_timer.stop()
        if hasattr(self, '_boost_gradient_timer'):
            self._boost_gradient_timer.stop()
        import gc
        gc.collect()
        try:
            from hardware_wrapper import trim_process_working_set
            trim_process_working_set()
        except Exception:
            pass
    
    def _install_librehwmon(self):
        """Download and install hardware monitoring tool (LHM or HWiNFO)."""
        try:
            from PySide6.QtWidgets import QProgressDialog, QMessageBox, QInputDialog
            from integrations.tools_downloader import (
                download_librehwmon, LIBREHWMON_DIR,
                download_hwinfo, HWINFO_DIR
            )
            
            # Show choice dialog
            items = ["LibreHardwareMonitor (~2MB, WMI support)", "HWiNFO Portable (~5MB, more accurate)"]
            item, ok = QInputDialog.getItem(
                self, "Choose Hardware Monitor",
                "Select which hardware monitor to install:",
                items, 0, False
            )
            
            if not ok:
                return
            
            # Determine which tool to download
            if "HWiNFO" in item:
                tool_name = "HWiNFO Portable"
                download_func = download_hwinfo
                install_dir = HWINFO_DIR
                note = "Remember to enable 'Shared Memory Support' in HWiNFO settings for real-time data."
            else:
                tool_name = "LibreHardwareMonitor"
                download_func = download_librehwmon
                install_dir = LIBREHWMON_DIR
                note = "LibreHardwareMonitor requires running as Administrator for best results."
            
            # Show progress dialog
            from integrations.tools_downloader import HELXAIDProgressDialog
            progress = HELXAIDProgressDialog(f"Installing {tool_name}", "Cancel", 0, 100, self)
            progress.set_status(f"Downloading {tool_name}...")
            progress.show()
            
            # State for thread communication
            state = {"downloaded": 0, "total": 0, "done": False, "success": False, "error": ""}
            
            def on_progress(downloaded: int, total: int):
                state["downloaded"] = downloaded
                state["total"] = total
            
            def do_download():
                success, error = download_func(on_progress)
                state["success"] = success
                state["error"] = error or ""
                state["done"] = True
            
            # Start download in thread
            import threading
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
            
            # Poll for completion
            from PySide6.QtWidgets import QApplication
            import time
            while not state["done"]:
                QApplication.processEvents()
                if progress.wasCanceled():
                    break
                if state["total"] > 0:
                    progress.set_progress(state["downloaded"], state["total"])
                time.sleep(0.05)
            
            progress.close()
            
            if state["success"]:
                # Update Install button to Start button
                if hasattr(self, 'install_monitor_btn') and self.install_monitor_btn:
                    self.install_monitor_btn.setText("Open Monitor")
                    self.install_monitor_btn.setStyleSheet("""
                        QPushButton {
                            background: #4ade80; color: #1a1a2e; border: none; 
                            border-radius: 6px; font-size: 10px; font-weight: 600;
                        }
                        QPushButton:hover { background: #22c55e; }
                    """)
                    self.install_monitor_btn.setToolTip("Launch LibreHardwareMonitor as Administrator")
                    try:
                        self.install_monitor_btn.clicked.disconnect()
                    except RuntimeError:
                        pass
                    self.install_monitor_btn.clicked.connect(self._start_librehwmon)
                    # Update internal state
                    self._hwmon_available = True
                    self._librehwmon_available = True
                
                QMessageBox.information(self, "Download Complete", 
                    f"{tool_name} installed to:\n{install_dir}\n\n"
                    f"Click 'Start' to launch the hardware monitor.\n\n"
                    f"Note: {note}")
            elif not progress.wasCanceled():
                QMessageBox.critical(self, "Download Failed", f"Failed to install {tool_name}:\n{state['error']}")
        
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Download error: {e}")
    
    def _show_hwmon_selection_dialog(self):
        """Show dialog to select and launch/install hardware monitor (LHM or HWiNFO)."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
        from PySide6.QtCore import Qt
        
        try:
            from integrations.tools_downloader import (
                is_librehwmon_available, is_hwinfo_available,
                get_librehwmon_path, get_hwinfo_path, get_hwinfo32_path
            )
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", "Could not load tools_downloader module.")
            return
        
        # Check what's installed
        lhm_installed = is_librehwmon_available()
        hwinfo_installed = is_hwinfo_available()
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Hardware Monitor")
        dialog.setFixedSize(320, 220)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a2e; }
            QLabel { color: #e0e0e0; font-size: 12px; }
            QPushButton {
                background: #333; color: #e0e0e0; border: 1px solid #555;
                border-radius: 6px; padding: 10px 16px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #444; border-color: #FF5B06; }
            QPushButton:disabled { background: #222; color: #666; }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Select Hardware Monitor")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FF5B06;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Choose a hardware monitor to get temperature, system status, and power data.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        # Recommendation note
        recommend = QLabel("We recommend using Libre because it's the most optimal for now.")
        recommend.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        recommend.setWordWrap(True)
        recommend.setAlignment(Qt.AlignCenter)
        layout.addWidget(recommend)
        
        layout.addSpacing(5)
        
        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        # LibreHardwareMonitor button
        lhm_btn = QPushButton("LibreHardwareMonitor" if lhm_installed else "Download LHM")
        if lhm_installed:
            lhm_btn.setStyleSheet("background: #FF5B06; color: #fff; border: none; border-radius: 6px; padding: 10px 16px; font-size: 9px; font-weight: 600;")
        btn_row.addWidget(lhm_btn)
        lhm_btn.clicked.connect(lambda: self._handle_hwmon_selection(dialog, "lhm", lhm_installed))
        
        # HWiNFO button  
        hwinfo_btn = QPushButton("HWiNFO" if hwinfo_installed else "Download HWiNFO")
        if hwinfo_installed:
            hwinfo_btn.setStyleSheet("background: #FF5B06; color: #fff; border: none; border-radius: 6px; padding: 10px 16px; font-size: 9px; font-weight: 600;")
        hwinfo_btn.clicked.connect(lambda: self._handle_hwmon_selection(dialog, "hwinfo", hwinfo_installed))
        btn_row.addWidget(hwinfo_btn)
        
        layout.addLayout(btn_row)
        
        # Status label
        status = QLabel("")
        status.setStyleSheet("color: #888; font-size: 10px;")
        status.setAlignment(Qt.AlignCenter)
        if lhm_installed:
            status.setText("✓ LibreHardwareMonitor installed")
        elif hwinfo_installed:
            status.setText("✓ HWiNFO installed")
        else:
            status.setText("No hardware monitor installed")
        layout.addWidget(status)
        
        dialog.exec()
    
    def _handle_hwmon_selection(self, dialog, tool: str, is_installed: bool):
        """Handle hardware monitor selection - install or launch."""
        dialog.close()
        
        if is_installed:
            # Launch the tool
            self._launch_hwmon(tool)
        else:
            # Install the tool
            self._install_hwmon(tool)
    
    def _launch_hwmon(self, tool: str):
        """Launch the specified hardware monitor as admin."""
        import os
        import ctypes
        
        try:
            from integrations.tools_downloader import (
                get_librehwmon_path, get_hwinfo_path, get_hwinfo32_path
            )
            
            if tool == "lhm":
                exe_path = get_librehwmon_path()
                tool_name = "LibreHardwareMonitor"
            else:
                # Prefer 64-bit, fallback to 32-bit
                if os.path.exists(get_hwinfo_path()):
                    exe_path = get_hwinfo_path()
                else:
                    exe_path = get_hwinfo32_path()
                tool_name = "HWiNFO"
                # Auto-enable shared memory
                self._enable_hwinfo_shared_memory(exe_path)
            
            if not exe_path or not os.path.exists(exe_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", f"{tool_name} executable not found.")
                return
            
            # Launch as admin
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, None,
                os.path.dirname(exe_path), 1
            )
            
            if result > 32:
                print(f"[Hardware] {tool_name} started as Administrator")
                btn = getattr(self, 'start_monitor_btn', None)
                if btn:
                    btn.setText("✓ Launched")
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(3000, lambda: btn.setText("Open Monitor"))
            else:
                print(f"[Hardware] Failed to start {tool_name} (code: {result})")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to launch: {e}")
    
    def _install_hwmon(self, tool: str):
        """Install the specified hardware monitor."""
        from PySide6.QtWidgets import QProgressDialog, QMessageBox
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication
        import threading
        
        try:
            from integrations.tools_downloader import download_librehwmon, download_hwinfo
            
            tool_name = "LibreHardwareMonitor" if tool == "lhm" else "HWiNFO"
            download_func = download_librehwmon if tool == "lhm" else download_hwinfo
            
            # Show progress dialog
            from integrations.tools_downloader import HELXAIDProgressDialog
            progress = HELXAIDProgressDialog(f"Installing {tool_name}", "Cancel", 0, 100, self)
            progress.set_status(f"Downloading {tool_name}...")
            progress.show()
            
            # Shared state for thread communication
            state = {"done": False, "success": False, "error": "", "progress": 0}
            
            def on_progress(downloaded, total):
                # Just update state, don't touch UI from here
                if total > 0:
                    state["progress"] = int(downloaded / total * 100)
            
            def download_thread():
                try:
                    download_func(on_progress)
                    state["success"] = True
                except Exception as e:
                    state["error"] = str(e)
                state["done"] = True
            
            thread = threading.Thread(target=download_thread, daemon=True)
            thread.start()
            
            # Poll for completion and update UI from main thread
            def check_done():
                # Update progress from main thread
                progress.setValue(state["progress"])
                QApplication.processEvents()  # Keep UI responsive
                
                if progress.wasCanceled():
                    state["done"] = True
                    state["error"] = "Cancelled by user"
                    progress.close()
                    return
                
                if state["done"]:
                    progress.close()
                    if state["success"]:
                        QMessageBox.information(self, "Success", 
                            f"{tool_name} installed successfully!\n\nPlease restart the launcher to use it.")
                    else:
                        QMessageBox.critical(self, "Error", f"Download failed: {state['error']}")
                else:
                    QTimer.singleShot(100, check_done)
            
            check_done()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Install error: {e}")
    
    def _start_librehwmon(self, silent_launch=False):
        """Launch standalone LibreHardwareMonitor.exe directly on user desktop."""
        self._start_librehwmon_standalone(silent_launch=silent_launch)

    def _start_librehwmon_standalone(self, silent_launch=False):
        """Launch standalone LibreHardwareMonitor.exe as Administrator on interactive desktop."""
        try:
            from integrations.tools_downloader import get_librehwmon_path, is_librehwmon_available
            import ctypes
            import os
            import subprocess

            exe_path = get_librehwmon_path() if is_librehwmon_available() else None
            if not exe_path or not os.path.exists(exe_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", "LibreHardwareMonitor.exe not found.")
                return

            # 1. Clean up any Session 0 background process running under SYSTEM
            try:
                from integrations.cpu_controller import is_service_running, send_service_command
                if is_service_running():
                    send_service_command({
                        "action": "cleanup_lhm",
                        "exe_path": exe_path
                    })
                else:
                    subprocess.run(["taskkill", "/F", "/IM", "LibreHardwareMonitor.exe"], capture_output=True)
            except Exception as ex:
                print(f"[Hardware] Background cleanup warning: {ex}")

            # 2. Check if window already running on user desktop (Session 1) and restore it
            try:
                import win32gui, win32con
                hwnd = win32gui.FindWindow(None, "Libre Hardware Monitor")
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    print("[Hardware] Restored existing LibreHardwareMonitor window")
                    return
            except Exception:
                pass

            # 3. Launch interactive instance on desktop (SW_SHOWNORMAL = 1)
            show_cmd = 0 if silent_launch else 1
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, None,
                os.path.dirname(exe_path), show_cmd
            )
            print(f"[Hardware] Started LibreHardwareMonitor.exe as Administrator (result={result})")

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to start hardware monitor:\n{e}")
    
    def _reset_monitor_btn(self, btn):
        """Reset monitor button back to Start state."""
        if btn:
            btn.setText("Open Monitor")
            btn.setStyleSheet("""
                QPushButton {
                    background: #4ade80; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #22c55e; }
            """)
            btn.setEnabled(True)
    
    def _enable_hwinfo_shared_memory(self, exe_path: str):
        """Auto-enable Shared Memory Support in HWiNFO config file.
        
        HWiNFO stores settings in HWiNFO64.INI or HWiNFO32.INI in the same directory.
        This modifies the config to enable shared memory so users don't have to manually configure it.
        """
        import os
        import configparser
        
        try:
            # HWiNFO config is in same dir as exe, named HWiNFO64.INI or HWiNFO32.INI
            exe_dir = os.path.dirname(exe_path)
            exe_name = os.path.basename(exe_path)
            
            # Determine INI file name based on exe
            if "64" in exe_name:
                ini_name = "HWiNFO64.INI"
            else:
                ini_name = "HWiNFO32.INI"
            
            ini_path = os.path.join(exe_dir, ini_name)
            
            # Read existing config or create new
            config = configparser.ConfigParser()
            if os.path.exists(ini_path):
                config.read(ini_path)
            
            # Ensure section exists
            if 'Settings' not in config:
                config['Settings'] = {}
            
            # Enable Shared Memory Support (SensorsSM key)
            # Value 1 = enabled
            config['Settings']['SensorsSM'] = '1'
            
            # Write config back
            with open(ini_path, 'w') as f:
                config.write(f)
            
            print(f"[Hardware] HWiNFO Shared Memory enabled in {ini_name}")
        except Exception as e:
            print(f"[Hardware] Could not auto-enable HWiNFO shared memory: {e}")
    
    
    def _is_hwmon_running(self) -> bool:
        """Check if any hardware monitor process is running."""
        try:
            import psutil
            hwmon_processes = ['HWiNFO64.exe', 'HWiNFO32.exe', 'LibreHardwareMonitor.exe']
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] in hwmon_processes:
                    return True
            return False
        except Exception:
            return False
    
    def _update_hwmon_button_status(self):
        """Update hardware monitor button to always be clickable for opening the panel."""
        btn = getattr(self, 'start_monitor_btn', None) or getattr(self, 'install_monitor_btn', None)
        if not btn:
            return
        
        # Don't disable the button. If it's available, show standard "Open Panel" styling.
        if getattr(self, '_hwmon_available', False):
            if btn.text() not in ["✓ Launched", "Download LHM"]:
                # Optionally, we could show "Open HWiNFO" if HWiNFO is used, but "Open Panel" or "Open LHM" is fine.
                btn.setText("Open Monitor")
            btn.setStyleSheet("""
                QPushButton {
                    background: #4ade80; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #22c55e; }
            """)
            btn.setEnabled(True)

