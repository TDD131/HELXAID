"""
AnimatedButton - A QPushButton with smooth hover animations.
Features:
- Sliding blue background fill from left to right on hover
- Border fade out during animation
- Text color transition from white to black
- Only applies sliding effect to text buttons (no icon)
"""
from PySide6.QtCore import QVariantAnimation
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import QSize, QTimer, Property, QPropertyAnimation, QEasingCurve, Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QIcon, QLinearGradient, QFontMetrics, QFont


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
        
        # Force hover fill animation even if button has an icon
        self._force_hover_fill = False
        self._hover_mode = "slide"  # "slide" or "fade"
        self._gradient_direction = "horizontal"  # "horizontal" or "vertical"
        self._border_radius = None
        self._custom_font_size = None
    
    def setBorderRadius(self, radius: float):
        """Set custom corner radius for the button (e.g. 5.0 or 6.0)."""
        self._border_radius = float(radius)

    def setFontSize(self, size: int):
        """Set custom font point size (e.g. 9 or 10)."""
        self._custom_font_size = int(size)

    def setHoverMode(self, mode: str):
        """Set hover animation mode: 'slide' (sliding wipe) or 'fade' (full button fade)."""
        self._hover_mode = mode

    def setGradientDirection(self, direction: str):
        """Set gradient direction: 'horizontal' (left-to-right) or 'vertical' (top-to-bottom)."""
        self._gradient_direction = direction

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
        
    def setForceHoverFill(self, enabled: bool):
        """Force the sliding fill hover animation even if the button has an icon."""
        self._force_hover_fill = enabled
        
    def enterEvent(self, event):
        """Mouse enters button - start fill animation."""
        # Check if this is a text-only button or force fill is enabled
        if self.icon().isNull() or self._force_hover_fill:
            self._animate_fill(1.0)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Mouse leaves button - reverse fill animation."""
        if self.icon().isNull() or self._force_hover_fill:
            self._animate_fill(0.0)
        super().leaveEvent(event)
    
    def _animate_fill(self, target):
        """Animate the fill progress."""
        duration = 180 if self._hover_mode == "fade" else 300
        easing = QEasingCurve.InOutQuad if self._hover_mode == "fade" else QEasingCurve.InOutCubic
        if not hasattr(self, '_fill_animation'):
            self._fill_animation = QPropertyAnimation(self, b"fillProgress")
            self._fill_animation.setDuration(duration)
            self._fill_animation.setEasingCurve(easing)
        else:
            self._fill_animation.stop()
            self._fill_animation.setDuration(duration)
            self._fill_animation.setEasingCurve(easing)
        
        self._fill_animation.setStartValue(self._fill_progress)
        self._fill_animation.setEndValue(target)
        self._fill_animation.start()
    
    def getFillProgress(self):
        return self._fill_progress
    
    def setFillProgress(self, value):
        self._fill_progress = value
        self.update()  # Trigger repaint
    
    fillProgress = Property(float, getFillProgress, setFillProgress)
    
    def paintEvent(self, event):
        """Custom paint for sliding fill effect on text buttons."""
        # Only custom paint for text buttons unless forced
        if not self.icon().isNull() and not self._force_hover_fill:
            super().paintEvent(event)
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        adjusted_rect = QRectF(0.5, 0.5, max(0.0, float(rect.width() - 1.0)), max(0.0, float(rect.height() - 1.0)))
        if self._border_radius is not None:
            radius = self._border_radius
        else:
            radius = min(4.0 if adjusted_rect.height() <= 32 else 12.0, adjusted_rect.height() / 2.0)
        
        if self._hover_mode == "fade":
            # Fade hover mode: full-surface opacity fade matching FadeHoverButton / helxairo_editorDeleteKeyBtn
            if self._fill_progress > 0.001:
                if self._gradient_direction == "vertical":
                    gradient = QLinearGradient(0, 0, 0, rect.height())
                else:
                    gradient = QLinearGradient(0, 0, rect.width(), 0)
                colors = self._gradient_colors
                if len(colors) == 1:
                    gradient.setColorAt(0, QColor(*colors[0]))
                    gradient.setColorAt(1, QColor(*colors[0]))
                else:
                    for i, c in enumerate(colors):
                        gradient.setColorAt(i / (len(colors) - 1), QColor(*c))
                
                path = QPainterPath()
                path.addRoundedRect(adjusted_rect, radius, radius)
                painter.setOpacity(self._fill_progress)
                painter.fillPath(path, QBrush(gradient))
                painter.setOpacity(1.0)
            
            # Draw border (fades out on hover so fully hovered state is borderless matching helxairo_editorModifyKeyBtn)
            border_opacity = 1.0 - self._fill_progress
            if border_opacity > 0.05:
                border_color = QColor(255, 255, 255, int(150 * border_opacity))
                pen = QPen(border_color)
                pen.setWidth(1)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(adjusted_rect, radius, radius)
            
            # Text stays crisp white Orbitron matching helxairo_editorModifyKeyBtn
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Orbitron")
            font.setBold(True)
            if hasattr(self, '_custom_pixel_size') and self._custom_pixel_size is not None:
                font.setPixelSize(self._custom_pixel_size)
            elif self._custom_font_size is not None:
                if self._custom_font_size <= 13:
                    font.setPixelSize(self._custom_font_size)
                else:
                    font.setPointSize(self._custom_font_size)
            elif adjusted_rect.height() <= 32:
                font.setPixelSize(10)
            else:
                font = self.font()
                font.setFamily("Orbitron")
                font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, self.text())
            painter.end()
            return

        # Calculate fill width based on progress
        fill_width = int(rect.width() * self._fill_progress)
        
        # Draw background fill with gradient (sliding from left)
        if fill_width > 0:
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
            path.addRoundedRect(adjusted_rect, radius, radius)
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
            painter.drawRoundedRect(adjusted_rect, radius, radius)
        
        # Draw text with color transition (white -> black)
        text_r = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_g = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_b = int(255 * (1 - self._fill_progress) + 0 * self._fill_progress)
        text_color = QColor(text_r, text_g, text_b)
        
        if not self.text():
            # If no text but has an icon and forced fill, draw the icon
            if not self.icon().isNull():
                icon = self.icon()
                # Determine which state/mode to use. We can just use the button's standard painting for the icon
                # by rendering the icon pixmap centered
                icon_size = self.iconSize()
                if icon_size.width() == 0:
                    icon_size = QSize(20, 20)
                
                # Check if we should draw active or normal state based on hover
                mode = QIcon.Active if self._fill_progress > 0.5 else QIcon.Normal
                pixmap = icon.pixmap(icon_size, mode, QIcon.On)
                
                # Center the icon
                x = int((rect.width() - icon_size.width()) / 2)
                y = int((rect.height() - icon_size.height()) / 2)
                painter.drawPixmap(x, y, pixmap)
        else:
            painter.setPen(text_color)
            font = QFont("Orbitron")
            font.setBold(True)
            if hasattr(self, '_custom_pixel_size') and self._custom_pixel_size is not None:
                font.setPixelSize(self._custom_pixel_size)
            elif self._custom_font_size is not None:
                if self._custom_font_size <= 13:
                    font.setPixelSize(self._custom_font_size)
                else:
                    font.setPointSize(self._custom_font_size)
            elif adjusted_rect.height() <= 32:
                font.setPixelSize(10)
            else:
                font = self.font()
                font.setFamily("Orbitron")
                font.setBold(True)
            painter.setFont(font)
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


from PySide6.QtWidgets import QAbstractButton

class AnimatedCheckBox(QAbstractButton):
    """A checkbox that animates its background and checkmark smoothly, built on QAbstractButton."""
    stateChanged = Signal(int)
    
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        
        self._check_state = 2 if self.isChecked() else 0 # 0: Unchecked, 1: PartiallyChecked (-), 2: Checked (v)
        self._progress = 1.0 if self.isChecked() else 0.0
        
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.valueChanged.connect(self._update_anim)
        
        self.toggled.connect(self._on_toggled)

    def _animate_to(self, target: float):
        if hasattr(self, '_anim'):
            if self._anim.state() == QVariantAnimation.Running:
                self._anim.stop()
            
            if abs(self._progress - target) < 0.001:
                self._progress = target
                self.update()
                return

            self._anim.setDirection(QVariantAnimation.Forward)
            self._anim.setStartValue(self._progress)
            self._anim.setEndValue(target)
            self._anim.start()

    def setCheckState(self, state: int):
        """Set state: 0=Unchecked, 1=PartiallyChecked (-), 2=Checked (v)."""
        self._check_state = state
        is_chk = (state != 0)
        self.blockSignals(True)
        super().setChecked(is_chk)
        self.blockSignals(False)
        self._animate_to(1.0 if is_chk else 0.0)

    def checkState(self) -> int:
        return getattr(self, '_check_state', 2 if self.isChecked() else 0)

    def setChecked(self, checked: bool):
        self._check_state = 2 if checked else 0
        self.blockSignals(True)
        super().setChecked(checked)
        self.blockSignals(False)
        self._animate_to(1.0 if checked else 0.0)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        font_metrics = self.fontMetrics()
        lines = self.text().split("\n")
        max_line_w = max([font_metrics.horizontalAdvance(line) for line in lines]) if lines else 0
        line_count = len(lines)
        text_height = line_count * font_metrics.height() + (line_count - 1) * 2
        width = 18 + 8 + max_line_w + 10
        height = max(24, text_height + 6)
        return QSize(int(width), int(height))
        
    def _update_anim(self, value):
        self._progress = value
        self.update()
        
    def _on_toggled(self, checked):
        if getattr(self, '_check_state', 0) == 1 and checked:
            self._check_state = 2
        elif not checked:
            self._check_state = 0
        elif checked and getattr(self, '_check_state', 0) == 0:
            self._check_state = 2

        self._animate_to(1.0 if checked else 0.0)
        self.stateChanged.emit(self._check_state)
        
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QBrush
        from PySide6.QtCore import QRectF, Qt, QRect
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        box_size = 18
        lines = self.text().split("\n")
        if len(lines) > 1:
            box_y = 2
        else:
            box_y = (self.height() - box_size) / 2
        box_rect = QRectF(0, box_y, box_size, box_size)

        # HELXAID Orange Style
        bg_uncheck = QColor("#2a2a2a")
        bg_check = QColor("#FF5B06")
        border_uncheck = QColor("#555555")
        border_check = QColor("#FF5B06")
        
        # Interpolate
        r = bg_uncheck.red() + (bg_check.red() - bg_uncheck.red()) * self._progress
        g = bg_uncheck.green() + (bg_check.green() - bg_uncheck.green()) * self._progress
        b = bg_uncheck.blue() + (bg_check.blue() - bg_uncheck.blue()) * self._progress
        bg_color = QColor(int(r), int(g), int(b))
        
        br = border_uncheck.red() + (border_check.red() - border_uncheck.red()) * self._progress
        bg = border_uncheck.green() + (border_check.green() - border_uncheck.green()) * self._progress
        bb = border_uncheck.blue() + (border_check.blue() - border_uncheck.blue()) * self._progress
        border_color = QColor(int(br), int(bg), int(bb))
        
        p.setPen(QPen(border_color, 2))
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(box_rect, 4, 4)
        
        # Checkmark / Dash draw animation
        if self._progress > 0:
            p.setPen(QPen(QColor(255, 255, 255, 255), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            
            if getattr(self, '_check_state', 2) == 1:
                # Partially checked (-) horizontal line
                line_y = box_rect.y() + box_size / 2.0
                start_x = box_rect.x() + 4
                end_x = box_rect.x() + box_size - 4
                cur_end_x = start_x + (end_x - start_x) * self._progress
                p.drawLine(int(start_x), int(line_y), int(cur_end_x), int(line_y))
            else:
                # Checkmark (v)
                p1 = (box_rect.x() + 4, box_rect.y() + 9)
                p2 = (box_rect.x() + 8, box_rect.y() + 13)
                p3 = (box_rect.x() + 15, box_rect.y() + 5)
                
                l1 = 5.65 # approx length of segment 1
                l2 = 10.63 # approx length of segment 2
                total_l = l1 + l2
                
                threshold = l1 / total_l # approx 0.35
                
                path = QPainterPath()
                path.moveTo(*p1)
                
                if self._progress <= threshold:
                    t = self._progress / threshold
                    cur_x = p1[0] + (p2[0] - p1[0]) * t
                    cur_y = p1[1] + (p2[1] - p1[1]) * t
                    path.lineTo(cur_x, cur_y)
                else:
                    path.lineTo(*p2)
                    t = (self._progress - threshold) / (1.0 - threshold)
                    cur_x = p2[0] + (p3[0] - p2[0]) * t
                    cur_y = p2[1] + (p3[1] - p2[1]) * t
                    path.lineTo(cur_x, cur_y)
                    
                p.drawPath(path)
            
        # Text
        p.setPen(QColor("#e0e0e0"))
        font = self.font()
        p.setFont(font)
        text_rect = QRect(int(box_size + 8), 0, int(self.width() - box_size - 8), int(self.height()))
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.text())


class FadeHoverButton(QPushButton):
    """Button with smooth fade-in / fade-out linear gradient hover opacity transition.
    Styled matching cpuSavePresetBtn (#FF5B06 -> #FDA903 theme, border-radius 10px, Orbitron font).
    """
    
    # Signal emitted on double-click
    doubleClicked = Signal()

    def __init__(
        self,
        text="",
        parent=None,
        is_secondary=False,
        border_radius=6.0,
        color_mode="default",
        text_align=Qt.AlignCenter,
        font_size=None,
        border_color=None,
        hover_border_color=None,
        padding_left=0
    ):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("border: none; background: transparent;")
        self._hover_progress = 0.0
        
        self._anim = QPropertyAnimation(self, b"hoverProgress")
        self._anim.setDuration(180)  # 180ms smooth fade
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        self._is_secondary = is_secondary
        self._color_mode = color_mode if not is_secondary else "secondary"
        self._border_radius = float(border_radius)  # Default 6.0px matching input controls
        self._text_align = text_align
        self._font_size = font_size
        self._border_color = border_color
        self._hover_border_color = hover_border_color
        self._padding_left = padding_left

    def getHoverProgress(self) -> float:
        return self._hover_progress

    def setHoverProgress(self, val: float):
        self._hover_progress = val
        self.update()

    hoverProgress = Property(float, getHoverProgress, setHoverProgress)

    def setCustomColors(self, radius=10.0):
        self._border_radius = radius
        self.update()

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.35)
        rect = QRectF(self.rect())
        adjusted_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)

        # Build horizontal linear gradient (0, 0 -> width, 0)
        gradient = QLinearGradient(0, 0, rect.width(), 0)

        if self._color_mode == "secondary" or self._is_secondary:
            # Secondary theme: Dark charcoal (30, 32, 38) -> Medium dark (#3a3d45 -> #4a4d55)
            r0 = int(30 + (58 - 30) * self._hover_progress)
            g0 = int(32 + (61 - 32) * self._hover_progress)
            b0 = int(38 + (69 - 38) * self._hover_progress)
            a0 = int(220 + (255 - 220) * self._hover_progress)

            r1 = int(30 + (74 - 30) * self._hover_progress)
            g1 = int(32 + (77 - 32) * self._hover_progress)
            b1 = int(38 + (85 - 38) * self._hover_progress)
            a1 = int(220 + (255 - 220) * self._hover_progress)

            text_r = int(224 + (255 - 224) * self._hover_progress)
            text_g = int(224 + (255 - 224) * self._hover_progress)
            text_b = int(224 + (255 - 224) * self._hover_progress)
        elif self._color_mode == "green":
            # Green theme: Dark forest green (#162C20) -> Emerald green gradient (#0E623B -> #1DB954)
            r0 = int(22 + (14 - 22) * self._hover_progress)
            g0 = int(44 + (98 - 44) * self._hover_progress)
            b0 = int(32 + (59 - 32) * self._hover_progress)
            a0 = int(220 + (255 - 220) * self._hover_progress)

            r1 = int(22 + (29 - 22) * self._hover_progress)
            g1 = int(44 + (185 - 44) * self._hover_progress)
            b1 = int(32 + (84 - 32) * self._hover_progress)
            a1 = int(220 + (255 - 220) * self._hover_progress)

            text_r = 255
            text_g = 255
            text_b = 255
        elif self._color_mode == "red":
            # Red theme: Dark danger red (#771212) -> Danger red gradient (#B91C1C -> #FF3838)
            r0 = int(119 + (185 - 119) * self._hover_progress)
            g0 = int(18 + (28 - 18) * self._hover_progress)
            b0 = int(18 + (28 - 18) * self._hover_progress)
            a0 = int(220 + (255 - 220) * self._hover_progress)

            r1 = int(119 + (255 - 119) * self._hover_progress)
            g1 = int(18 + (56 - 18) * self._hover_progress)
            b1 = int(18 + (56 - 18) * self._hover_progress)
            a1 = int(220 + (255 - 220) * self._hover_progress)

            text_r = 255
            text_g = 255
            text_b = 255
        else:
            # HELXAIR default dark state (40, 40, 40) -> cpuSavePresetBtn orange gradient (#FF5B06 -> #FDA903)
            r0 = int(40 + (255 - 40) * self._hover_progress)
            g0 = int(40 + (91 - 40) * self._hover_progress)
            b0 = int(40 + (6 - 40) * self._hover_progress)
            a0 = int(220 + (255 - 220) * self._hover_progress)

            r1 = int(40 + (253 - 40) * self._hover_progress)
            g1 = int(40 + (169 - 40) * self._hover_progress)
            b1 = int(40 + (3 - 40) * self._hover_progress)
            a1 = int(220 + (255 - 220) * self._hover_progress)

            text_r = int(255 + (26 - 255) * self._hover_progress)
            text_g = int(255 + (26 - 255) * self._hover_progress)
            text_b = int(255 + (26 - 255) * self._hover_progress)

        gradient.setColorAt(0.0, QColor(r0, g0, b0, a0))
        gradient.setColorAt(1.0, QColor(r1, g1, b1, a1))

        # Smooth rounded rect path
        path = QPainterPath()
        path.addRoundedRect(adjusted_rect, self._border_radius, self._border_radius)
        painter.fillPath(path, QBrush(gradient))

        # Optional border drawing
        if self._border_color is not None:
            if self._hover_border_color is not None:
                br0, bg0, bb0, ba0 = self._border_color.getRgb()
                br1, bg1, bb1, ba1 = self._hover_border_color.getRgb()
                curr_br = int(br0 + (br1 - br0) * self._hover_progress)
                curr_bg = int(bg0 + (bg1 - bg0) * self._hover_progress)
                curr_bb = int(bb0 + (bb1 - bb0) * self._hover_progress)
                curr_ba = int(ba0 + (ba1 - ba0) * self._hover_progress)
                border_col = QColor(curr_br, curr_bg, curr_bb, curr_ba)
            else:
                border_col = self._border_color
            pen = QPen(border_col, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(adjusted_rect, self._border_radius, self._border_radius)

        # Draw text & icon with proper layout
        has_text = bool(self.text())
        has_icon = not self.icon().isNull()

        if has_text or has_icon:
            font = self.font()
            font.setFamily("Orbitron")
            if self._font_size is not None:
                font.setPixelSize(self._font_size)
            elif self.height() <= 24:
                font.setPixelSize(10)
            else:
                font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_r, text_g, text_b))

            if has_icon and has_text:
                icon_size = self.iconSize() if not self.iconSize().isEmpty() else QSize(16, 16)
                pix = self.icon().pixmap(icon_size)
                spacing = 6
                
                fm = QFontMetrics(font)
                text_w = fm.horizontalAdvance(self.text())
                total_w = icon_size.width() + spacing + text_w
                
                start_x = int((rect.width() - total_w) / 2)
                icon_y = int((rect.height() - icon_size.height()) / 2)
                
                painter.drawPixmap(start_x, icon_y, pix)
                
                text_rect = QRectF(start_x + icon_size.width() + spacing, 0, text_w + 4, rect.height())
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
            elif has_icon:
                icon_size = self.iconSize() if not self.iconSize().isEmpty() else QSize(18, 18)
                pix = self.icon().pixmap(icon_size)
                ix = int((rect.width() - icon_size.width()) / 2)
                iy = int((rect.height() - icon_size.height()) / 2)
                painter.drawPixmap(ix, iy, pix)
            elif has_text:
                if self._text_align == Qt.AlignCenter:
                    painter.drawText(adjusted_rect, Qt.AlignCenter, self.text())
                else:
                    pad = self._padding_left if self._padding_left > 0 else 8
                    text_rect = adjusted_rect.adjusted(pad, 0, -4, 0)
                    painter.drawText(text_rect, self._text_align | Qt.AlignVCenter, self.text())

        painter.end()


class HoverCloseButton(QPushButton):
    """
    Component Name: hoverCloseButton
    Interactive close button that dynamically recolors close-icon.svg via code.
    Idle color: #999999 (soft gray), Hover color: #FF5B06 (HELXAID cyber orange).
    """
    def __init__(self, size: int = 20, icon_size: int = 12, idle_color: str = "#999999", hover_color: str = "#FF5B06", parent=None):
        super().__init__(parent)
        self.setObjectName("hoverCloseButton")
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0px; margin: 0px; }")
        
        self._icon_size = icon_size
        self._idle_icon = self._render_svg_icon(idle_color, icon_size)
        self._hover_icon = self._render_svg_icon(hover_color, icon_size)
        
        self.setIcon(self._idle_icon)
        self.setIconSize(QSize(icon_size, icon_size))
        
    @staticmethod
    def _render_svg_icon(color_hex: str, size: int) -> QIcon:
        import os, re
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap
        base_dir = os.path.dirname(os.path.abspath(__file__))
        svg_path = os.path.join(base_dir, "UI Icons", "close-icon.svg")
        content = ""
        if os.path.exists(svg_path):
            try:
                with open(svg_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = ""
        if not content:
            content = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
            
        content = re.sub(r'stroke="#[0-9a-fA-F]{3,8}"', f'stroke="{color_hex}"', content)
        content = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', f'fill="{color_hex}"', content)
        
        renderer = QSvgRenderer(content.encode('utf-8'))
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(p)
        p.end()
        return QIcon(pix)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.setIcon(self._hover_icon)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.setIcon(self._idle_icon)
