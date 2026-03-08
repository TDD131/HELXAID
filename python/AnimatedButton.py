"""
AnimatedButton - A QPushButton with smooth hover animations.
Features:
- Sliding blue background fill from left to right on hover
- Border fade out during animation
- Text color transition from white to black
- Only applies sliding effect to text buttons (no icon)
"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import QSize, QTimer, Property, QPropertyAnimation, QEasingCurve, Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath


class AnimatedButton(QPushButton):
    """Button with smooth animated hover effect (sliding fill for text buttons)."""
    
    # Signal emitted on double-click
    doubleClicked = Signal()
    
    # Default gradient colors (orange theme: #FF5B06 to #FDA903)
    DEFAULT_GRADIENT = [(255, 91, 6), (253, 169, 3)]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fill_progress = 0.0  # 0 = no fill, 1 = fully filled
        self._animation = None
        self._is_text_button = True  # Will be determined based on icon
        
        # Gradient colors for hover fill (list of RGB tuples)
        self._gradient_colors = self.DEFAULT_GRADIENT
        
        # For icon buttons - click animation
        self._original_icon_size = None
        self._current_scale = 1.0
        # Whether the press/release bounce animation is enabled (default True)
        self._click_animation_enabled = True
    
    def setHoverGradient(self, colors):
        """Set custom gradient colors for hover effect.
        Args:
            colors: List of hex strings like ['#FF0000', '#00FF00'] or RGB tuples
        """
        parsed = []
        for c in colors:
            if isinstance(c, str):
                # Parse hex color
                c = c.lstrip('#')
                parsed.append((int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)))
            else:
                parsed.append(c)
        self._gradient_colors = parsed
    
    def setClickAnimation(self, enabled: bool):
        """Enable or disable the press/release icon bounce animation.
        
        Call setClickAnimation(False) on nav buttons to suppress the shrink-pop
        effect that fires every time an icon button is clicked.
        """
        self._click_animation_enabled = enabled
        
    def enterEvent(self, event):
        """Mouse enters button - start fill animation."""
        # Check if this is a text-only button
        if self.icon().isNull():
            self._animate_fill(1.0)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Mouse leaves button - reverse fill animation."""
        if self.icon().isNull():
            self._animate_fill(0.0)
        super().leaveEvent(event)
    
    def _animate_fill(self, target):
        """Animate the fill progress."""
        if self._animation:
            self._animation.stop()
        
        self._animation = QPropertyAnimation(self, b"fillProgress")
        self._animation.setDuration(300)  # 0.3 seconds
        self._animation.setStartValue(self._fill_progress)
        self._animation.setEndValue(target)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.start()
    
    def getFillProgress(self):
        return self._fill_progress
    
    def setFillProgress(self, value):
        self._fill_progress = value
        self.update()  # Trigger repaint
    
    fillProgress = Property(float, getFillProgress, setFillProgress)
    
    def paintEvent(self, event):
        """Custom paint for sliding fill effect on text buttons."""
        # Only custom paint for text buttons
        if not self.icon().isNull():
            super().paintEvent(event)
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        radius = 12  # Border radius
        
        # Calculate fill width based on progress
        fill_width = int(rect.width() * self._fill_progress)
        
        # Draw background fill with gradient (sliding from left)
        if fill_width > 0:
            from PySide6.QtGui import QLinearGradient
            
            # Create horizontal gradient using custom colors
            gradient = QLinearGradient(0, 0, rect.width(), 0)
            colors = self._gradient_colors
            if len(colors) == 1:
                gradient.setColorAt(0, QColor(*colors[0]))
                gradient.setColorAt(1, QColor(*colors[0]))
            else:
                for i, c in enumerate(colors):
                    gradient.setColorAt(i / (len(colors) - 1), QColor(*c))
            
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            
            # Clip to rounded rect
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), radius, radius)
            painter.setClipPath(path)
            
            # Draw the fill rectangle (from left to fill_width)
            painter.drawRect(0, 0, fill_width, rect.height())
            painter.setClipping(False)
        
        # Draw border (fades as fill progresses)
        border_opacity = 1.0 - self._fill_progress
        if border_opacity > 0.05:
            border_color = QColor(255, 255, 255, int(150 * border_opacity))
            pen = QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        
        # Draw text with color transition (white -> black)
        text_r = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_g = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_b = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_color = QColor(text_r, text_g, text_b)
        
        painter.setPen(text_color)
        painter.setFont(self.font())
        painter.drawText(rect, Qt.AlignCenter, self.text())
        
        painter.end()
    
    # === Icon button click animations (bouncy pop) ===
    
    def mousePressEvent(self, event):
        # Only animate icon buttons when click animation is enabled
        if self._click_animation_enabled and not self.icon().isNull():
            if self._original_icon_size is None or self._original_icon_size.width() == 0:
                self._original_icon_size = self.iconSize()
            
            if self._original_icon_size.width() > 0:
                # Shrink down quickly on press
                self._animate_icon_scale(0.75, 60)
        
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if self._click_animation_enabled and not self.icon().isNull():
            if self._original_icon_size and self._original_icon_size.width() > 0:
                # Bounce back with overshoot (pop effect)
                self._animate_icon_scale_bounce(1.0, 180)
        
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Emit doubleClicked signal on double-click."""
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
    
    def _ensure_restored(self):
        """Ensure icon is restored to original size."""
        if self._current_scale < 1.0 and self._original_icon_size:
            self._animate_icon_scale(1.0, 100)
    
    def _animate_icon_scale(self, target_scale, duration_ms):
        """Smoothly animate icon size with ease-out."""
        if not self._original_icon_size or self._original_icon_size.width() == 0:
            return
            
        start_scale = self._current_scale
        steps = max(1, duration_ms // 16)
        
        def animate_step(step=0):
            if step >= steps:
                self._current_scale = target_scale
                self._apply_scale(target_scale)
                return
            
            t = step / steps
            eased_t = 1 - (1 - t) * (1 - t)  # Ease out
            current = start_scale + (target_scale - start_scale) * eased_t
            
            self._current_scale = current
            self._apply_scale(current)
            
            QTimer.singleShot(16, lambda: animate_step(step + 1))
        
        animate_step(0)
    
    def _animate_icon_scale_bounce(self, target_scale, duration_ms):
        """Animate icon size with bouncy overshoot effect (pop!)."""
        if not self._original_icon_size or self._original_icon_size.width() == 0:
            return
            
        start_scale = self._current_scale
        overshoot = 1.18  # Go 18% past target then settle
        steps = max(1, duration_ms // 12)
        
        def animate_step(step=0):
            if step >= steps:
                self._current_scale = target_scale
                self._apply_scale(target_scale)
                return
            
            t = step / steps
            
            # Overshoot easing: goes past target then settles back
            # Based on ease-out-back curve
            c1 = 1.70158
            c3 = c1 + 1
            eased_t = 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
            
            # Apply overshoot to scale
            current = start_scale + (target_scale * overshoot - start_scale) * eased_t
            # Blend back to target in final portion
            if t > 0.6:
                blend = (t - 0.6) / 0.4
                current = current * (1 - blend) + target_scale * blend
            
            self._current_scale = current
            self._apply_scale(current)
            
            QTimer.singleShot(12, lambda: animate_step(step + 1))
        
        animate_step(0)
    
    def _apply_scale(self, scale):
        """Apply the scale to icon size."""
        if self._original_icon_size:
            new_size = QSize(
                int(self._original_icon_size.width() * scale),
                int(self._original_icon_size.height() * scale)
            )
            self.setIconSize(new_size)
    
    # === Pop animation for active state ===
    
    def popAnimation(self, duration_ms=200):
        """
        Play a bouncy pop animation - scales up slightly then back to normal.
        Call this when the button becomes active/selected.
        """
        if self._original_icon_size is None or self._original_icon_size.width() == 0:
            if not self.icon().isNull():
                self._original_icon_size = self.iconSize()
            else:
                return
        
        # Scale sequence: 1.0 -> 1.2 -> 1.0 (with overshoot)
        self._pop_animate_step(1.0, 1.25, duration_ms // 2, 
                               lambda: self._pop_animate_step(1.25, 1.0, duration_ms // 2, None, True), False)
    
    def _pop_animate_step(self, start_scale, end_scale, duration_ms, on_complete=None, use_bounce=False):
        """Animate one step of the pop animation."""
        if not self._original_icon_size or self._original_icon_size.width() == 0:
            if on_complete:
                on_complete()
            return
        
        steps = max(1, duration_ms // 12)
        
        def animate(step=0):
            if step >= steps:
                self._current_scale = end_scale
                self._apply_scale(end_scale)
                if on_complete:
                    on_complete()
                return
            
            t = step / steps
            
            if use_bounce:
                # Overshoot easing (goes past target then settles)
                eased_t = 1 - pow(1 - t, 3) * (1 + 2.5 * (1 - t))
                eased_t = max(0, min(1, eased_t))
            else:
                # Fast out easing
                eased_t = 1 - (1 - t) ** 2
            
            current = start_scale + (end_scale - start_scale) * eased_t
            self._current_scale = current
            self._apply_scale(current)
            
            QTimer.singleShot(12, lambda: animate(step + 1))
        
        animate(0)
