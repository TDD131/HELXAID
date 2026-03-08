"""
Dynamic Smooth Scrolling for PySide6
=====================================

Smooth scrolling with dynamic easing - more responsive, no stutter.

Usage:
    from smooth_scroll import SmoothScrollArea
    
    scroll = SmoothScrollArea()
    scroll.setWidget(your_content_widget)
"""

from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QWheelEvent
import time


class SmoothScrollArea(QScrollArea):
    """
    QScrollArea with dynamic smooth scrolling.
    
    Features:
    - Dynamic duration based on scroll speed
    - Bounce-back easing for dynamic feel
    - No timer-based updates (no stutter)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Animation
        self._animation = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # State tracking
        self._target = 0
        self._last_wheel_time = 0
        self._velocity = 0
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle wheel with dynamic speed-based animation."""
        delta = event.angleDelta().y()
        
        if delta == 0:
            event.accept()
            return
        
        scrollbar = self.verticalScrollBar()
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        
        # Get current time
        current_time = time.time() * 1000  # ms
        time_diff = current_time - self._last_wheel_time
        self._last_wheel_time = current_time
        
        # Calculate base scroll amount
        scroll_amount = -delta * 1.2
        
        # Build up velocity if scrolling fast (multiple wheel events close together)
        if time_diff < 100:  # Fast scrolling (less than 100ms between events)
            self._velocity = min(self._velocity + abs(scroll_amount) * 0.3, 800)
        else:
            self._velocity = abs(scroll_amount)
        
        # If animation running, accumulate
        if self._animation.state() == QPropertyAnimation.Running:
            remaining = self._target - scrollbar.value()
            self._target = scrollbar.value() + scroll_amount + remaining * 0.7
        else:
            self._target = scrollbar.value() + scroll_amount
        
        # Apply velocity boost
        if self._velocity > 200:
            boost = (self._velocity / 200) * 0.3
            self._target = scrollbar.value() + scroll_amount * (1 + boost)
        
        # Clamp to valid range
        self._target = max(min_val, min(max_val, self._target))
        
        # Dynamic duration - faster scroll = longer smooth animation
        base_duration = 250
        velocity_factor = min(self._velocity / 300, 2.0)
        duration = int(base_duration + (velocity_factor * 150))
        
        # Dynamic easing - faster = more dramatic curve
        if self._velocity > 500:
            self._animation.setEasingCurve(QEasingCurve.OutExpo)
        elif self._velocity > 300:
            self._animation.setEasingCurve(QEasingCurve.OutQuart)
        else:
            self._animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Start animation
        self._animation.stop()
        self._animation.setDuration(duration)
        self._animation.setStartValue(scrollbar.value())
        self._animation.setEndValue(int(self._target))
        self._animation.start()
        
        event.accept()


class SmoothTableWidget:
    """
    Mixin/helper to add smooth scrolling to any QTableWidget.
    Simple pixel-based smooth scrolling without queue.
    
    Usage:
        table = QTableWidget()
        smoother = SmoothTableWidget(table)
    """
    
    def __init__(self, table_widget):
        from PySide6.QtWidgets import QAbstractItemView
        
        self.table = table_widget
        
        # Use pixel-based scrolling for smoother movement
        table_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        # Animation for vertical scroll
        scrollbar = table_widget.verticalScrollBar()
        self._animation = QPropertyAnimation(scrollbar, b"value")
        self._animation.setEasingCurve(QEasingCurve.OutQuad)
        self._animation.setDuration(120)  # Short for responsive feel
        
        self._target = 0
        
        # Override wheelEvent
        table_widget.wheelEvent = self._smooth_wheel_event
    
    def _smooth_wheel_event(self, event: QWheelEvent):
        """Smooth wheel scrolling - pixel based."""
        delta = event.angleDelta().y()
        
        if delta == 0:
            event.accept()
            return
        
        scrollbar = self.table.verticalScrollBar()
        current = scrollbar.value()
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        
        # Scroll amount: ~45 pixels per tick (about 1 row)
        scroll_amount = -45 if delta > 0 else 45
        
        # If animation running, accumulate
        if self._animation.state() == QPropertyAnimation.Running:
            self._target += scroll_amount
        else:
            self._target = current + scroll_amount
        
        # Clamp target
        self._target = max(min_val, min(max_val, self._target))
        
        # Start/update animation
        self._animation.stop()
        self._animation.setStartValue(current)
        self._animation.setEndValue(self._target)
        self._animation.start()
        
        event.accept()


# ============================================================================
# Example / Test
# ============================================================================

if __name__ == "__main__":
    import sys
    
    app = QApplication(sys.argv)
    
    scroll = SmoothScrollArea()
    scroll.setWindowTitle("Dynamic Smooth Scroll")
    scroll.setWidgetResizable(True)
    scroll.resize(450, 550)
    
    content = QWidget()
    content.setStyleSheet("background: #151520;")
    layout = QVBoxLayout(content)
    layout.setSpacing(8)
    layout.setContentsMargins(15, 15, 15, 15)
    
    for i in range(100):
        label = QLabel(f"Item {i + 1} - Scroll fast for dynamic effect!")
        label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #252535, stop:1 #1f1f2f);
                color: #e0e0e0;
                padding: 18px 20px;
                border-radius: 10px;
                font-size: 13px;
                border: 1px solid #303045;
            }
            QLabel:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #303045, stop:1 #252535);
                border-color: #FF5B06;
            }
        """)
        layout.addWidget(label)
    
    scroll.setWidget(content)
    scroll.setStyleSheet("""
        QScrollArea {
            background: #151520;
            border: none;
        }
        QScrollBar:vertical {
            background: #1a1a25;
            width: 10px;
            border-radius: 5px;
            margin: 3px;
        }
        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #555, stop:1 #666);
            border-radius: 5px;
            min-height: 40px;
        }
        QScrollBar::handle:vertical:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #FF5B06, stop:1 #FF7B36);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
            height: 0;
        }
    """)
    
    scroll.show()
    sys.exit(app.exec())
