"""
Native Qt Lyrics Page Widget for HELXAIC
Interactive synchronized real-time lyric scrolling with Orbitron typography,
ambient glowing highlights, click-to-seek, manual sync offset controls, and smooth easing.

Component Name: LyricsWidget
"""

import os
import bisect
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu, QSpinBox, QDoubleSpinBox, QComboBox, QListView,
    QGraphicsOpacityEffect, QApplication, QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem, QStyle
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QVariantAnimation, QEasingCurve, QSize, QRectF, QRect, Property, QPoint, QEvent
from PySide6.QtGui import QFont, QColor, QCursor, QPainter, QFontMetrics, QAction, QIcon, QPixmap

from LyricsEngine import LyricData, LyricLine, LyricsCacheManager, LyricsFetchWorker, LyricQuerySanitizer


class LyricLineWidget(QWidget):
    """
    Zero-ghosting custom-painted lyric line item with dynamic geometry and smooth transitions.
    Renders animated background pills, smooth color/scale interpolation,
    neon glowing highlights, and Orbitron typography via QPainter.
    """
    clicked = Signal(int)  # Emits time_ms

    def __init__(self, index: int, line_data: LyricLine, parent=None):
        super().__init__(parent)
        self.index = index
        self.line_data = line_data
        self.time_ms = line_data.time_ms
        self.text = line_data.text or "♪"
        self.translation = line_data.translation

        self.font_main = QFont("Orbitron", 13, QFont.Bold)
        self.font_main.setFamilies(["Orbitron", "Yu Gothic UI", "Meiryo", "MS Gothic", "Segoe UI", "sans-serif"])

        self.font_sub = QFont("Orbitron", 10, QFont.Normal)
        self.font_sub.setFamilies(["Orbitron", "Yu Gothic UI", "Meiryo", "MS Gothic", "Segoe UI", "sans-serif"])

        self.setObjectName(f"lyricLineItem_{index}")
        self.setCursor(QCursor(Qt.PointingHandCursor) if self.time_ms >= 0 else QCursor(Qt.ArrowCursor))
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._is_active = False
        self._is_hovered = False
        self._anim_progress = 0.0
        self._hover_progress = 0.0
        self._main_h = 26
        self._sub_h = 18

        # Active transition animation (0.0 = inactive, 1.0 = active)
        self._active_anim = QPropertyAnimation(self, b"animProgress", self)
        self._active_anim.setDuration(260)
        self._active_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Hover transition animation (0.0 = unhovered, 1.0 = hovered)
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(160)
        self._is_animating_slide = False
        self._last_calc_w = None
        self._recalculate_height()

    def _recalculate_height(self):
        """Calculate exact dynamic height required to fit main text and subtext with padding."""
        if getattr(self, '_is_animating_slide', False):
            return

        parent_w = self.parent().width() if (self.parent() and self.parent().width() > 50) else 380
        w = max(100, self.width() if self.width() > 0 else parent_w)
        avail_w = max(50, w - 48)

        if getattr(self, '_last_calc_w', None) == avail_w:
            return
        self._last_calc_w = avail_w

        fm_main = QFontMetrics(self.font_main)
        main_rect = fm_main.boundingRect(0, 0, avail_w, 2000, Qt.AlignCenter | Qt.TextWordWrap, self.text)
        self._main_h = max(26, main_rect.height())

        if self.translation:
            fm_sub = QFontMetrics(self.font_sub)
            sub_rect = fm_sub.boundingRect(0, 0, avail_w, 2000, Qt.AlignCenter | Qt.TextWordWrap, self.translation)
            self._sub_h = max(18, sub_rect.height())
            total_h = 10 + self._main_h + 6 + self._sub_h + 10
        else:
            self._sub_h = 0
            total_h = 12 + self._main_h + 12

        final_h = max(48 if not self.translation else 70, total_h)
        if self.height() != final_h:
            self.setFixedHeight(final_h)

    def set_animating_state(self, is_animating: bool):
        """Freeze or unfreeze height recalculations during animated panel sliding."""
        self._is_animating_slide = is_animating
        if not is_animating:
            self._last_calc_w = None
            self._recalculate_height()

    def set_subtext(self, text: Optional[str]):
        """Dynamically update secondary subtext (Romaji / Translation / None)."""
        clean = text.strip() if text else None
        if self.translation != clean:
            self.translation = clean
            self._last_calc_w = None
            self._recalculate_height()
            self.updateGeometry()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalculate_height()

    def get_anim_progress(self) -> float:
        return self._anim_progress

    def set_anim_progress(self, val: float):
        self._anim_progress = max(0.0, min(1.0, float(val)))
        self.update()

    animProgress = Property(float, get_anim_progress, set_anim_progress)

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, val: float):
        self._hover_progress = max(0.0, min(1.0, float(val)))
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def set_active(self, active: bool):
        if self._is_active != active:
            self._is_active = active
            self._active_anim.stop()
            self._active_anim.setStartValue(self._anim_progress)
            self._active_anim.setEndValue(1.0 if active else 0.0)
            self._active_anim.setDuration(260 if active else 220)
            self._active_anim.setEasingCurve(QEasingCurve.OutCubic if active else QEasingCurve.OutQuad)
            self._active_anim.start()

    def enterEvent(self, event):
        self._is_hovered = True
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def set_hovered(self, hovered: bool):
        """Programmatically trigger hover transition animation."""
        if self._is_hovered != hovered:
            self._is_hovered = hovered
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_progress)
            self._hover_anim.setEndValue(1.0 if hovered else 0.0)
            self._hover_anim.setDuration(160)
            self._hover_anim.start()


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.time_ms >= 0:
            self.clicked.emit(self.time_ms)
        super().mousePressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(200, self.height() if self.height() > 0 else 48)

    def minimumSizeHint(self) -> QSize:
        return QSize(50, 48 if not self.translation else 70)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        t = self._anim_progress      # 0.0 (inactive) -> 1.0 (active)
        ht = self._hover_progress    # 0.0 (unhovered) -> 1.0 (hovered)

        top_y = 10
        main_h = getattr(self, '_main_h', 26)
        main_rect = QRectF(24, top_y, w - 48, main_h)

        # Main Lyric Typography Interpolation
        base_r = 140 + (255 - 140) * ht
        base_g = 145 + (255 - 145) * ht
        base_b = 165 + (255 - 165) * ht

        cur_r = int(base_r + (255 - base_r) * t)
        cur_g = int(base_g + (91 - base_g) * t)
        cur_b = int(base_b + (6 - base_b) * t)
        cur_a = int(170 + (255 - 170) * max(t, ht * 0.7))

        painter.setFont(self.font_main)

        # Ambient neon glow behind active text
        if t > 0.05:
            glow_alpha = int(80 * t)
            painter.setPen(QColor(255, 91, 6, glow_alpha))
            painter.drawText(main_rect.translated(0, 1), Qt.AlignCenter | Qt.TextWordWrap, self.text)
            painter.drawText(main_rect.translated(0, -1), Qt.AlignCenter | Qt.TextWordWrap, self.text)

        painter.setPen(QColor(cur_r, cur_g, cur_b, cur_a))
        painter.drawText(main_rect, Qt.AlignCenter | Qt.TextWordWrap, self.text)

        # Translation / Romaji Subtext
        if self.translation:
            sub_y = top_y + main_h + 6
            sub_h = getattr(self, '_sub_h', 18)
            sub_rect = QRectF(24, sub_y, w - 48, sub_h)

            s_base_r = 155 + (255 - 155) * ht
            s_base_g = 175 + (255 - 175) * ht
            s_base_b = 205 + (255 - 205) * ht

            sub_r = int(s_base_r + (253 - s_base_r) * t)
            sub_g = int(s_base_g + (169 - s_base_g) * t)
            sub_b = int(s_base_b + (3 - s_base_b) * t)
            sub_a = int(185 + (255 - 185) * max(t, ht * 0.6))

            painter.setFont(self.font_sub)
            painter.setPen(QColor(sub_r, sub_g, sub_b, sub_a))
            painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextWordWrap, self.translation)

    def cleanup(self):
        """Stop all running QPropertyAnimations before destruction."""
        try:
            if hasattr(self, '_active_anim'):
                self._active_anim.stop()
            if hasattr(self, '_hover_anim'):
                self._hover_anim.stop()
        except Exception:
            pass


def is_instrumental_line(text: Optional[str]) -> bool:
    """Check if text is an instrumental placeholder or music note marker."""
    if not text:
        return True
    t = text.strip()
    if not t:
        return True
    t_lower = t.lower()
    return t in ("♪", "♫", "♬", "---", "--", "...", "…") or t_lower in (
        "(instrumental)", "[instrumental]", "instrumental",
        "(music)", "[music]", "music",
        "(solo)", "[solo]", "solo",
        "(interlude)", "[interlude]", "interlude",
        "(intro)", "[intro]", "(outro)", "[outro]"
    )


class SmoothListView(QListView):
    """
    QListView with HELXAID signature kinetic smooth scrolling (momentum + cubic easing).
    Uses ScrollPerPixel for fluid, non-jittery scrolling.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self._scroll_target = 0
        self._last_wheel_time = 0
        self._scroll_velocity = 0
        
        self.verticalScrollBar().sliderPressed.connect(self._scroll_anim.stop)
        if self.viewport():
            self.viewport().installEventFilter(self)
            self.viewport().setMouseTracking(True)
            self.viewport().setAttribute(Qt.WA_Hover, True)

    def eventFilter(self, watched, event):
        if watched == self.viewport():
            if event.type() == QEvent.Wheel:
                self._handle_wheel(event)
                return True
            elif event.type() == QEvent.MouseMove:
                idx = self.indexAt(event.pos())
                if not idx.isValid():
                    self.clearSelection()
                    if self.selectionModel():
                        self.selectionModel().clearCurrentIndex()
            elif event.type() == QEvent.Leave:
                self.clearSelection()
                if self.selectionModel():
                    self.selectionModel().clearCurrentIndex()
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        self._handle_wheel(event)

    def _handle_wheel(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        scrollbar = self.verticalScrollBar()
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        if min_val == max_val:
            event.accept()
            return

        import time
        current_time = time.time() * 1000
        time_diff = current_time - self._last_wheel_time
        self._last_wheel_time = current_time

        scroll_amount = -delta * 0.45

        if time_diff < 100:
            self._scroll_velocity = min(self._scroll_velocity + abs(scroll_amount) * 0.3, 800)
        else:
            self._scroll_velocity = abs(scroll_amount)

        if self._scroll_anim.state() == QPropertyAnimation.Running:
            remaining = self._scroll_target - scrollbar.value()
            self._scroll_target = scrollbar.value() + scroll_amount + remaining * 0.6
        else:
            self._scroll_target = scrollbar.value() + scroll_amount

        if self._scroll_velocity > 200:
            boost = (self._scroll_velocity / 200) * 0.25
            self._scroll_target = scrollbar.value() + scroll_amount * (1 + boost)

        self._scroll_target = max(min_val, min(max_val, self._scroll_target))

        duration = int(220 + min(self._scroll_velocity / 300, 2.0) * 120)
        self._scroll_anim.stop()
        self._scroll_anim.setDuration(duration)
        self._scroll_anim.setStartValue(scrollbar.value())
        self._scroll_anim.setEndValue(int(self._scroll_target))
        self._scroll_anim.start()
        event.accept()

    def mouseMoveEvent(self, event):
        idx = self.indexAt(event.pos())
        if not idx.isValid():
            self.clearSelection()
            if self.selectionModel():
                self.selectionModel().clearCurrentIndex()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.clearSelection()
        if self.selectionModel():
            self.selectionModel().clearCurrentIndex()
        super().leaveEvent(event)


class PillDropdownDelegate(QStyledItemDelegate):
    """
    Custom item delegate for DirectionalComboBox.
    Renders items as sleek floating rounded pills with #272727 hover/selection background,
    proper insets so highlights never touch or bleed into the popup container's rounded corners,
    crisp Orbitron typography, and centered icons.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.font = QFont("Orbitron", 9, QFont.Medium)
        self.font.setFamilies(["Orbitron", "Yu Gothic UI", "Meiryo", "MS Gothic", "Segoe UI", "sans-serif"])

    def sizeHint(self, option, index):
        return QSize(option.rect.width() if option.rect.width() > 0 else 160, 28)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        is_hovered = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        # Inset pill rect so it never touches outer corners or window edges
        pill_rect = option.rect.adjusted(4, 1, -4, -1)

        if is_hovered or is_selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#272727"))
            painter.drawRoundedRect(pill_rect, 4, 4)

        # Retrieve text and icon
        text = index.data(Qt.DisplayRole) or ""
        icon = index.data(Qt.DecorationRole)

        content_left = pill_rect.left() + 8

        # Draw icon if available
        if icon:
            if isinstance(icon, QIcon) and not icon.isNull():
                ico_size = 12
                ico_y = option.rect.top() + (option.rect.height() - ico_size) // 2
                icon_rect = QRect(content_left, ico_y, ico_size, ico_size)
                pix = icon.pixmap(ico_size, ico_size)
                painter.drawPixmap(icon_rect, pix)
                content_left += ico_size + 8
            elif isinstance(icon, QPixmap) and not icon.isNull():
                ico_size = 12
                ico_y = option.rect.top() + (option.rect.height() - ico_size) // 2
                icon_rect = QRect(content_left, ico_y, ico_size, ico_size)
                painter.drawPixmap(icon_rect, icon.scaled(ico_size, ico_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                content_left += ico_size + 8

        # Draw text
        painter.setFont(self.font)
        painter.setPen(QColor("#ffffff") if (is_hovered or is_selected) else QColor("#e0e0e0"))

        text_rect = QRect(
            content_left,
            option.rect.top(),
            max(0, pill_rect.right() - content_left - 4),
            option.rect.height()
        )
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()


class DirectionalComboBox(QComboBox):
    """
    QComboBox whose dropdown popup menu opens in a specified direction ('up' or 'down')
    with ZERO visual flicker, frameless translucent container, smooth directional entrance & exit transitions
    (floating upwards from button on open, gliding back into button on close), kinetic smooth scrolling, and Orbitron list view styling.
    """
    def __init__(self, direction: str = "up", parent=None):
        super().__init__(parent)
        self.direction = direction.lower()
        self.setView(SmoothListView(self))
        self.view().setItemDelegate(PillDropdownDelegate(self.view()))
        self.view().setCursor(QCursor(Qt.PointingHandCursor))
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setMouseTracking(True)
        self.view().setAttribute(Qt.WA_Hover, True)
        self._repositioning = False
        self._is_closing_anim = False
        self._popup_anim: Optional[QVariantAnimation] = None
        self._setup_container()

    def _setup_container(self):
        container = self.view().parentWidget()
        if container and not getattr(self, '_container_initialized', False):
            container.installEventFilter(self)
            container.setWindowFlags(container.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            container.setAttribute(Qt.WA_TranslucentBackground, True)
            self._container_initialized = True

    def wheelEvent(self, event):
        event.ignore()

    def showPopup(self):
        self._is_closing_anim = False
        self._setup_container()
        container = self.view().parentWidget()
        
        # Suppress Qt's hardcoded top-to-bottom qSlideEffect(Qt::TopEdge)
        prev_effect = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, False)
        try:
            super().showPopup()
        finally:
            if prev_effect:
                QApplication.setEffectEnabled(Qt.UI_AnimateCombo, True)
                
        if container:
            self._animate_open(container)

    def hidePopup(self):
        container = self.view().parentWidget() if hasattr(self, 'view') and self.view() else None
        if not container or not container.isVisible() or getattr(self, '_is_closing_anim', False):
            super().hidePopup()
            return
            
        self._is_closing_anim = True
        if self._popup_anim:
            self._popup_anim.stop()

        target_x, target_y, total_w, total_h, _ = self._calc_target_geometry()
        end_y = target_y + 14 if self.direction == "up" else target_y - 14

        self._popup_anim = QVariantAnimation(self)
        self._popup_anim.setDuration(110)
        self._popup_anim.setEasingCurve(QEasingCurve.InQuad)
        self._popup_anim.setStartValue(1.0)
        self._popup_anim.setEndValue(0.0)

        def _on_close_frame(progress: float):
            try:
                self._repositioning = True
                curr_y = int(target_y + (end_y - target_y) * (1.0 - progress))
                container.setGeometry(target_x, curr_y, total_w, total_h)
                if hasattr(self, '_opacity_effect') and self._opacity_effect:
                    self._opacity_effect.setOpacity(progress)
            finally:
                self._repositioning = False

        def _on_close_finished():
            try:
                super(DirectionalComboBox, self).hidePopup()
            finally:
                self._is_closing_anim = False
                if hasattr(self, '_opacity_effect') and self._opacity_effect:
                    self._opacity_effect.setOpacity(1.0)

        self._popup_anim.valueChanged.connect(_on_close_frame)
        self._popup_anim.finished.connect(_on_close_finished)
        self._popup_anim.start()

    def eventFilter(self, obj, event):
        container = self.view().parentWidget()
        if obj == container:
            if event.type() in (QEvent.Resize, QEvent.Move) and not getattr(self, '_repositioning', False):
                if not (self._popup_anim and self._popup_anim.state() == QVariantAnimation.Running):
                    self._position_container(container)
        return super().eventFilter(obj, event)

    def _calc_target_geometry(self):
        count = max(1, self.count())
        item_h = 28
        total_h = count * item_h + 8
        total_w = max(self.width(), 160)

        p = self.mapToGlobal(QPoint(0, 0))
        target_x = p.x()

        if self.direction == "up":
            target_y = p.y() - total_h - 4
            if target_y < 10:
                target_y = 10
        else:
            target_y = p.y() + self.height() + 4

        screen = self.screen() or (self.window().screen() if self.window() else None)
        if screen:
            screen_rect = screen.availableGeometry()
            if target_x + total_w > screen_rect.right() - 5:
                target_x = screen_rect.right() - total_w - 5
            if target_x < screen_rect.left() + 5:
                target_x = screen_rect.left() + 5
            if self.direction == "down" and (target_y + total_h > screen_rect.bottom() - 5):
                if p.y() - total_h - 4 >= screen_rect.top() + 5:
                    target_y = p.y() - total_h - 4
                else:
                    target_y = max(screen_rect.top() + 5, screen_rect.bottom() - total_h - 5)
            elif self.direction == "up" and target_y < screen_rect.top() + 5:
                target_y = screen_rect.top() + 5

        return target_x, target_y, total_w, total_h, p

    def _position_container(self, container):
        if not container or not self.isVisible() or getattr(self, '_repositioning', False):
            return
        try:
            self._repositioning = True
            target_x, target_y, total_w, total_h, _ = self._calc_target_geometry()
            container.setGeometry(target_x, target_y, total_w, total_h)
            self.view().setGeometry(0, 0, total_w, total_h)
        finally:
            self._repositioning = False

    def _animate_open(self, container):
        if not container or not self.isVisible():
            return
        target_x, target_y, total_w, total_h, p = self._calc_target_geometry()

        if self._popup_anim:
            self._popup_anim.stop()

        # Initial offset: starts closer to the button (14px lower for 'up', 14px higher for 'down')
        start_y = target_y + 14 if self.direction == "up" else target_y - 14
        container.setGeometry(target_x, start_y, total_w, total_h)
        self.view().setGeometry(0, 0, total_w, total_h)

        if not hasattr(self, '_opacity_effect') or not self._opacity_effect:
            self._opacity_effect = QGraphicsOpacityEffect(self.view())
            self.view().setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._popup_anim = QVariantAnimation(self)
        self._popup_anim.setDuration(130)
        self._popup_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)

        def _on_frame(progress: float):
            try:
                self._repositioning = True
                curr_y = int(start_y + (target_y - start_y) * progress)
                container.setGeometry(target_x, curr_y, total_w, total_h)
                if self._opacity_effect:
                    self._opacity_effect.setOpacity(progress)
            finally:
                self._repositioning = False

        def _on_finished():
            try:
                self._repositioning = True
                container.setGeometry(target_x, target_y, total_w, total_h)
                if self._opacity_effect:
                    self._opacity_effect.setOpacity(1.0)
            finally:
                self._repositioning = False

        self._popup_anim.valueChanged.connect(_on_frame)
        self._popup_anim.finished.connect(_on_finished)
        self._popup_anim.start()


class UpwardComboBox(DirectionalComboBox):
    """Backward-compatible subclass for upward-opening combo boxes."""
    def __init__(self, parent=None):
        super().__init__(direction="up", parent=parent)



class LyricsWidget(QWidget):
    """Main Lyrics Page placed in the MusicPanelWidget stack."""
    seekRequested = Signal(int)  # Emits target ms to QMediaPlayer
    closeRequested = Signal()  # Emitted when user clicks close/collapse button on lyrics panel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LyricsWidget")
        self.cache_mgr = LyricsCacheManager()
        self.current_data: Optional[LyricData] = None
        self.current_worker: Optional[LyricsFetchWorker] = None
        self.current_track: Dict[str, Any] = {}
        self.active_index = -1
        self.request_id_counter = 0
        self.active_request_id = 0
        self.line_widgets: List[LyricLineWidget] = []
        self.timestamps: List[int] = []
        self.user_offset_ms = 0
        self.subtext_line_offset = 0
        self._last_pos_ms = 0
        self._user_scrolling_paused = False
        self.selected_provider = "auto"
        self.subtext_mode = "auto"

        self._setup_ui()

        # Smooth persistent scrollbar animator (prevents overlapping animations / jitter)
        self._scroll_anim = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(280)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Smooth interactive reload spin animator
        self._orig_refresh_pixmap: Optional[QPixmap] = None
        self._reload_spin_anim = QVariantAnimation(self)
        self._reload_spin_anim.setDuration(550)
        self._reload_spin_anim.setStartValue(0.0)
        self._reload_spin_anim.setEndValue(360.0)
        self._reload_spin_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reload_spin_anim.valueChanged.connect(self._on_reload_spin_frame)
        self._reload_spin_anim.finished.connect(self._on_reload_spin_finished)

        # Scroll resume timer (resumes auto-scroll 4s after manual user scroll)
        self.scroll_resume_timer = QTimer(self)
        self.scroll_resume_timer.setSingleShot(True)
        self.scroll_resume_timer.setInterval(4000)
        self.scroll_resume_timer.timeout.connect(self._resume_auto_scroll)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # === Top Header (Minimalist Title & Close Button) ===
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(4, 2, 4, 2)
        header_bar.setSpacing(8)
        header_bar.setAlignment(Qt.AlignVCenter)

        self.title_label = QLabel("LYRICS")
        self.title_label.setObjectName("lyricsHeaderTitle")
        self.title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.title_label.setStyleSheet("""
            QLabel#lyricsHeaderTitle {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
                background: transparent;
            }
        """)
        header_bar.addWidget(self.title_label, stretch=1, alignment=Qt.AlignVCenter)

        # Close / Collapse Button
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("lyricsCloseBtn")
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setToolTip("Close Lyrics Panel")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setStyleSheet("""
            QPushButton#lyricsCloseBtn {
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                color: #8c92a4;
                background: transparent;
                border: none;
                padding: 0;
                margin: 0;
            }
            QPushButton#lyricsCloseBtn:hover {
                color: #ffffff;
                background: transparent;
            }
        """)
        self.btn_close.clicked.connect(self.closeRequested.emit)
        header_bar.addWidget(self.btn_close, 0, Qt.AlignVCenter)

        main_layout.addLayout(header_bar)

        # === Center Scroll Area (Takes Maximum Vertical Space) ===
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("lyricsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea#lyricsScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 91, 6, 0.35);
                border-radius: 2px;
                min-height: 25px;
            }
            QScrollBar::handle:vertical:hover {
                background: #FF5B06;
            }
        """)

        # Container inside scroll area
        self.container = QWidget()
        self.container.setObjectName("lyricsContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self.container.setStyleSheet("QWidget#lyricsContainer { background: transparent; }")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 40, 10, 80)
        self.container_layout.setSpacing(8)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # Detect manual user scrolling
        self.scroll_area.verticalScrollBar().sliderMoved.connect(self._on_user_scroll)

        # === Expandable Bottom Bar Widget (Single Unified Card) ===
        self.bottom_bar = QFrame(self)
        self.bottom_bar.setObjectName("lyricsBottomBar")
        self.bottom_bar.setStyleSheet("""
            QFrame#lyricsBottomBar {
                background: rgba(15, 15, 28, 0.75);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 2px;
            }
        """)
        bottom_layout = QVBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(6, 4, 6, 4)
        bottom_layout.setSpacing(4)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self._down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        self._up_arrow_path = os.path.join(script_dir, "UI Icons", "up-arrow-triangle.svg").replace("\\", "/")
        if not os.path.exists(self._down_arrow_path):
            self._down_arrow_path = r"D:\Software\tididi\HELXAID\python\UI Icons\down-arrow-triangle.svg"
        if not os.path.exists(self._up_arrow_path):
            self._up_arrow_path = r"D:\Software\tididi\HELXAID\python\UI Icons\up-arrow-triangle.svg"

        self._source_icon_path = os.path.join(script_dir, "UI Icons", "source-lyrics-icon.svg").replace("\\", "/")
        if not os.path.exists(self._source_icon_path):
            self._source_icon_path = r"D:\Software\tididi\HELXAID\python\UI Icons\source-lyrics-icon.svg"

        self._subtext_icon_path = os.path.join(script_dir, "UI Icons", "subtext-icon.svg").replace("\\", "/")
        if not os.path.exists(self._subtext_icon_path):
            self._subtext_icon_path = r"D:\Software\tididi\HELXAID\python\UI Icons\subtext-icon.svg"

        refresh_icon_path = os.path.join(script_dir, "UI Icons", "refresh.svg").replace("\\", "/")
        if not os.path.exists(refresh_icon_path):
            refresh_icon_path = r"D:\Software\tididi\HELXAID\python\UI Icons\refresh.svg"
        self._refresh_icon_path = refresh_icon_path

        # 1. Top Row: Source Dropdown, Subtext Dropdown, and Expand/Collapse Toggle Button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.setAlignment(Qt.AlignVCenter)

        # Source Dropdown ComboBox (with Music/Lyrics Icon, styled identically to cpuPowerModeCombo)
        source_ico = QIcon(self._source_icon_path)
        self.source_pill = DirectionalComboBox(direction="up", parent=self.bottom_bar)
        self.source_pill.setObjectName("lyricsSourcePill")
        self.source_pill.addItem(source_ico, "Auto", "auto")
        self.source_pill.addItem(source_ico, "Musixmatch", "musixmatch")
        self.source_pill.addItem(source_ico, "NetEase", "netease")
        self.source_pill.addItem(source_ico, "LRCLIB", "lrclib")
        self.source_pill.addItem(source_ico, "Local", "local")
        self.source_pill.setIconSize(QSize(12, 12))
        self.source_pill.setCursor(QCursor(Qt.PointingHandCursor))
        self.source_pill.setToolTip("Select lyrics provider")
        self.source_pill.setFixedHeight(22)
        self.source_pill.setStyleSheet(f"""
            QComboBox#lyricsSourcePill {{
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 1px 20px 1px 7px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10.5px;
                font-weight: 500;
                min-height: 20px;
                max-height: 22px;
            }}
            QComboBox#lyricsSourcePill:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QComboBox#lyricsSourcePill::drop-down {{
                border: none;
                width: 16px;
                background: transparent;
            }}
            QComboBox#lyricsSourcePill::down-arrow {{
                image: url('{self._up_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QComboBox#lyricsSourcePill QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                padding: 4px 0px;
                outline: none;
            }}
            QComboBox#lyricsSourcePill QAbstractItemView::item {{
                min-height: 28px;
                max-height: 28px;
                padding: 0px 10px;
                color: #e0e0e0;
            }}
        """)
        self.source_pill.currentTextChanged.connect(self._on_source_combo_text_changed)
        top_row.addWidget(self.source_pill, 0, Qt.AlignVCenter)

        # Subtext Dropdown ComboBox (with Sub/Text Icon, styled identically to cpuPowerModeCombo)
        subtext_ico = QIcon(self._subtext_icon_path)
        self.subtext_pill = UpwardComboBox(self.bottom_bar)
        self.subtext_pill.setObjectName("lyricsSubtextPill")
        self.subtext_pill.addItem(subtext_ico, "Sub: Auto", "auto")
        self.subtext_pill.addItem(subtext_ico, "Sub: Romaji", "romaji")
        self.subtext_pill.addItem(subtext_ico, "Sub: Translate", "translation")
        self.subtext_pill.addItem(subtext_ico, "Sub: Off", "none")
        self.subtext_pill.setIconSize(QSize(12, 12))
        self.subtext_pill.setCursor(QCursor(Qt.PointingHandCursor))
        self.subtext_pill.setToolTip("Select subtext stream (Romaji / Translation / Off)")
        self.subtext_pill.setFixedHeight(22)
        self.subtext_pill.setStyleSheet(f"""
            QComboBox#lyricsSubtextPill {{
                background: rgba(255, 255, 255, 0.1);
                color: #00E5FF;
                border: none;
                border-radius: 6px;
                padding: 1px 20px 1px 7px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10.5px;
                font-weight: 500;
                min-height: 20px;
                max-height: 22px;
            }}
            QComboBox#lyricsSubtextPill:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QComboBox#lyricsSubtextPill::drop-down {{
                border: none;
                width: 16px;
                background: transparent;
            }}
            QComboBox#lyricsSubtextPill::down-arrow {{
                image: url('{self._up_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QComboBox#lyricsSubtextPill QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                padding: 4px 0px;
                outline: none;
            }}
            QComboBox#lyricsSubtextPill QAbstractItemView::item {{
                min-height: 28px;
                max-height: 28px;
                padding: 0px 10px;
                color: #e0e0e0;
            }}
        """)
        self.subtext_pill.currentTextChanged.connect(self._on_subtext_combo_text_changed)
        top_row.addWidget(self.subtext_pill, 0, Qt.AlignVCenter)

        top_row.addStretch(1)

        # Reload Button (Placed in lyricsBottomBar with vibrant hover and click feedback)
        self.btn_reload = QPushButton(self.bottom_bar)
        self.btn_reload.setObjectName("lyricReloadBtn")
        self.btn_reload.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_reload.setToolTip("Re-fetch lyrics for current track")
        self.btn_reload.setFixedSize(20, 18)
        self.btn_reload.setIcon(QIcon(self._refresh_icon_path))
        self.btn_reload.setIconSize(QSize(12, 12))
        self.btn_reload.setStyleSheet("""
            QPushButton#lyricReloadBtn {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0;
                margin: 0;
                min-height: 18px;
                max-height: 18px;
                min-width: 20px;
                max-width: 20px;
            }
            QPushButton#lyricReloadBtn:hover {
                background-color: rgba(255, 91, 6, 0.25);
            }
            QPushButton#lyricReloadBtn:pressed {
                background-color: rgba(255, 91, 6, 0.50);
            }
        """)
        self.btn_reload.clicked.connect(self.reload_current_track)
        top_row.addWidget(self.btn_reload, 0, Qt.AlignVCenter)

        # Expand / Collapse Button (Top Right of Bottom Bar)
        self.btn_expand = QPushButton(self.bottom_bar)
        self.btn_expand.setObjectName("lyricsExpandBtn")
        self.btn_expand.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_expand.setToolTip("Toggle lyrics timing & offset controls")
        self.btn_expand.setFixedSize(22, 18)
        self.btn_expand.setIcon(QIcon(self._down_arrow_path))
        self.btn_expand.setIconSize(QSize(9, 9))
        self.btn_expand.setStyleSheet("""
            QPushButton#lyricsExpandBtn {
                background-color: rgba(255, 255, 255, 0.07);
                border: none;
                border-radius: 5px;
                padding: 0;
                margin: 0;
                min-height: 18px;
                max-height: 18px;
                min-width: 22px;
                max-width: 22px;
            }
            QPushButton#lyricsExpandBtn:hover {
                background-color: rgba(255, 91, 6, 0.28);
            }
            QPushButton#lyricsExpandBtn:pressed {
                background-color: rgba(255, 91, 6, 0.45);
                padding-top: 1px;
                padding-left: 1px;
            }
        """)
        self.btn_expand.clicked.connect(self._toggle_offset_controls)
        top_row.addWidget(self.btn_expand, 0, Qt.AlignVCenter)

        bottom_layout.addLayout(top_row)

        # 2. Bottom Row: Timing & Sub Controls (Placed directly BELOW pills on 1 sleek row)
        self.offset_widget = QWidget(self.bottom_bar)
        self.offset_widget.setObjectName("lyricsOffsetControlsContainer")
        offset_layout = QHBoxLayout(self.offset_widget)
        offset_layout.setContentsMargins(0, 2, 0, 2)
        offset_layout.setSpacing(4)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow_path = os.path.join(script_dir, "UI Icons", "up-arrow-triangle.svg").replace("\\", "/")
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")

        # 1. Lyric Sync Timing Offset Label + QDoubleSpinBox
        self.lyric_offset_label = QLabel("Sync")
        self.lyric_offset_label.setObjectName("lyricsSyncOffsetLabel")
        self.lyric_offset_label.setStyleSheet("""
            QLabel#lyricsSyncOffsetLabel {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 10.5px;
                font-weight: bold;
                color: #FF5B06;
                background: transparent;
                padding-left: 2px;
            }
        """)
        offset_layout.addWidget(self.lyric_offset_label)

        self.lyric_offset_spin = QDoubleSpinBox(self.offset_widget)
        self.lyric_offset_spin.setObjectName("lyricsSyncOffsetSpinBox")
        self.lyric_offset_spin.setRange(-30.0, 30.0)
        self.lyric_offset_spin.setDecimals(1)
        self.lyric_offset_spin.setSingleStep(0.5)
        self.lyric_offset_spin.setValue(0.0)
        self.lyric_offset_spin.setPrefix(" ")
        self.lyric_offset_spin.setSuffix(" s")
        self.lyric_offset_spin.setToolTip("Shift lyric timing sync earlier/later in seconds (-30.0s to +30.0s)")
        self.lyric_offset_spin.setFixedWidth(88)
        self.lyric_offset_spin.setFixedHeight(24)
        self.lyric_offset_spin.setStyleSheet(f"""
            QDoubleSpinBox#lyricsSyncOffsetSpinBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px 15px 0px 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox QLineEdit {{
                background: transparent;
                color: #e0e0e0;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                selection-background-color: #FF5B06;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::up-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-top-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::up-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::up-arrow {{
                image: url('{up_arrow_path}');
                width: 7px;
                height: 7px;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::down-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-bottom-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QDoubleSpinBox#lyricsSyncOffsetSpinBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 7px;
                height: 7px;
            }}
        """)
        self.lyric_offset_spin.valueChanged.connect(self._on_lyric_spin_changed)
        offset_layout.addWidget(self.lyric_offset_spin)

        # Subtle separator
        sep = QFrame(self.offset_widget)
        sep.setObjectName("lyricsOffsetSeparator")
        sep.setFixedSize(1, 14)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.12); border: none;")
        offset_layout.addWidget(sep)

        # 2. Sub Offset Label + QSpinBox (Styled identically to HELXAIRO helxairo_acInterval)
        self.sub_offset_label = QLabel("Sub")
        self.sub_offset_label.setObjectName("lyricsSubOffsetLabel")
        self.sub_offset_label.setStyleSheet("""
            QLabel#lyricsSubOffsetLabel {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 10.5px;
                font-weight: bold;
                color: #00E5FF;
                background: transparent;
                padding-left: 2px;
            }
        """)
        offset_layout.addWidget(self.sub_offset_label)

        self.sub_offset_spin = QSpinBox(self.offset_widget)
        self.sub_offset_spin.setObjectName("lyricsSubOffsetSpinBox")
        self.sub_offset_spin.setRange(-20, 20)
        self.sub_offset_spin.setValue(0)
        self.sub_offset_spin.setPrefix(" ")
        self.sub_offset_spin.setSuffix(" L")
        self.sub_offset_spin.setToolTip("Shift subtext/romaji alignment by lines (-20 to +20)")
        self.sub_offset_spin.setFixedWidth(76)
        self.sub_offset_spin.setFixedHeight(24)
        self.sub_offset_spin.setStyleSheet(f"""
            QSpinBox#lyricsSubOffsetSpinBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px 15px 0px 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
            }}
            QSpinBox#lyricsSubOffsetSpinBox QLineEdit {{
                background: transparent;
                color: #e0e0e0;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                selection-background-color: #FF5B06;
            }}
            QSpinBox#lyricsSubOffsetSpinBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-top-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-arrow {{
                image: url('{up_arrow_path}');
                width: 7px;
                height: 7px;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-bottom-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 7px;
                height: 7px;
            }}
        """)
        self.sub_offset_spin.valueChanged.connect(self._on_sub_spin_changed)
        offset_layout.addWidget(self.sub_offset_spin)

        offset_layout.addStretch(1)

        # Collapsed by default with smooth height animation
        self._offset_expanded = False
        self._offset_anim = QPropertyAnimation(self.offset_widget, b"maximumHeight", self)
        self._offset_anim.finished.connect(self._on_offset_anim_finished)
        self.offset_widget.setMaximumHeight(0)
        self.offset_widget.setVisible(False)
        bottom_layout.addWidget(self.offset_widget)

        main_layout.addWidget(self.bottom_bar)

    def _toggle_offset_controls(self):
        """Toggle expand/collapse of lyrics offset controls with buttery smooth cubic animation."""
        self._offset_expanded = not getattr(self, "_offset_expanded", False)
        target_h = max(28, self.offset_widget.sizeHint().height())

        self._offset_anim.stop()

        if self._offset_expanded:
            self.offset_widget.setVisible(True)
            self._offset_anim.setDuration(260)
            self._offset_anim.setStartValue(self.offset_widget.height())
            self._offset_anim.setEndValue(target_h)
            self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._offset_anim.start()

            self.btn_expand.setIcon(QIcon(getattr(self, '_up_arrow_path', '')))
            self.btn_expand.setToolTip("Collapse lyrics timing controls")
            self.btn_expand.setStyleSheet("""
                QPushButton#lyricsExpandBtn {
                    background-color: rgba(255, 91, 6, 0.22);
                    border: none;
                    border-radius: 5px;
                    padding: 0;
                    margin: 0;
                    min-height: 18px;
                    max-height: 18px;
                    min-width: 22px;
                    max-width: 22px;
                }
                QPushButton#lyricsExpandBtn:hover {
                    background-color: rgba(255, 91, 6, 0.35);
                }
                QPushButton#lyricsExpandBtn:pressed {
                    background-color: rgba(255, 91, 6, 0.50);
                    padding-top: 1px;
                    padding-left: 1px;
                }
            """)
        else:
            self._offset_anim.setDuration(200)
            self._offset_anim.setStartValue(self.offset_widget.height())
            self._offset_anim.setEndValue(0)
            self._offset_anim.setEasingCurve(QEasingCurve.OutQuad)
            self._offset_anim.start()

            self.btn_expand.setIcon(QIcon(getattr(self, '_down_arrow_path', '')))
            self.btn_expand.setToolTip("Expand lyrics timing controls")
            self.btn_expand.setStyleSheet("""
                QPushButton#lyricsExpandBtn {
                    background-color: rgba(255, 255, 255, 0.07);
                    border: none;
                    border-radius: 5px;
                    padding: 0;
                    margin: 0;
                    min-height: 18px;
                    max-height: 18px;
                    min-width: 22px;
                    max-width: 22px;
                }
                QPushButton#lyricsExpandBtn:hover {
                    background-color: rgba(255, 91, 6, 0.28);
                }
                QPushButton#lyricsExpandBtn:pressed {
                    background-color: rgba(255, 91, 6, 0.45);
                    padding-top: 1px;
                    padding-left: 1px;
                }
            """)

    def _on_offset_anim_finished(self):
        """Cleanly hide widget when collapse animation reaches 0 height."""
        if not getattr(self, "_offset_expanded", False):
            self.offset_widget.setVisible(False)

    def _on_source_combo_text_changed(self, text: str):
        """Handle provider selection change from lyricsSourcePill dropdown."""
        mapping = {
            "Auto": "auto",
            "Musixmatch": "musixmatch",
            "NetEase": "netease",
            "LRCLIB": "lrclib",
            "Local": "local"
        }
        provider = mapping.get(text, "auto")
        if provider != getattr(self, "selected_provider", "auto"):
            self._set_provider_and_fetch(provider)

    def _set_source_badge(self, text: str, color: str = "#e0e0e0", bg_color: str = "", tooltip: str = ""):
        """Set branded styling and informative tooltip on the source combobox dropdown."""
        if hasattr(self, 'source_pill') and self.source_pill:
            self.source_pill.setToolTip(tooltip or text)

    def _on_subtext_combo_text_changed(self, text: str):
        """Handle subtext stream selection change from lyricsSubtextPill dropdown."""
        mapping = {
            "Sub: Auto": "auto",
            "Sub: Romaji": "romaji",
            "Sub: Translate": "translation",
            "Sub: Off": "none"
        }
        mode = mapping.get(text, "auto")
        if mode != getattr(self, "subtext_mode", "auto"):
            self._set_subtext_mode(mode)

    def _set_subtext_badge(self, text: str, color: str = "#00E5FF", bg_color: str = "", tooltip: str = ""):
        """Set branded styling and informative tooltip on the subtext combobox."""
        if hasattr(self, 'subtext_pill') and self.subtext_pill:
            self.subtext_pill.setToolTip(tooltip or text)

    def _on_source_pill_clicked(self, event):
        """Handle click on source pill to pop up provider selection menu."""
        if event.button() == Qt.LeftButton:
            self._show_provider_menu()

    def _on_subtext_pill_clicked(self, event):
        """Handle click on subtext pill to pop up subtitle stream selection menu."""
        if event.button() == Qt.LeftButton:
            self._show_subtext_menu()

    def _show_provider_menu(self):
        """Open sleek menu to switch lyrics provider, styled identically to cpuPowerModeCombo."""
        if hasattr(self, 'source_pill') and isinstance(self.source_pill, QComboBox):
            self.source_pill.showPopup()

    def _show_subtext_menu(self):
        """Open sleek menu to switch subtext stream, styled identically to cpuPowerModeCombo."""
        if hasattr(self, 'subtext_pill') and isinstance(self.subtext_pill, QComboBox):
            self.subtext_pill.showPopup()

    def _set_subtext_mode(self, mode: str):
        """Change active subtext mode and dynamically update line widgets with on-demand background fetch."""
        self.subtext_mode = mode
        rev_mapping = {
            "auto": "Sub: Auto",
            "google": "Sub: Romaji",
            "genius": "Sub: Romaji",
            "netease": "Sub: Romaji",
            "romaji": "Sub: Romaji",
            "translation": "Sub: Translate",
            "none": "Sub: Off"
        }
        if hasattr(self, 'subtext_pill') and isinstance(self.subtext_pill, QComboBox):
            target_text = rev_mapping.get(mode, "Sub: Auto")
            self.subtext_pill.blockSignals(True)
            self.subtext_pill.setCurrentText(target_text)
            self.subtext_pill.blockSignals(False)
        cd = self.current_data
        req_id = getattr(self, 'active_request_id', 0)

        # 1. On-demand fetch for Google AI Romaji
        if mode == "google" and cd and not getattr(cd, 'has_google_romaji', False):
            from LyricsEngine import GoogleRomajiClient
            if not GoogleRomajiClient.breaker.can_execute():
                rem = GoogleRomajiClient.breaker.get_remaining_cooldown()
                print(f"[Lyrics] Google Romaji cooldown active ({rem}s remaining). Using available alternative romaji.")
            else:
                self._set_subtext_badge("ENRICHING...", "#00E5FF", "rgba(0, 229, 255, 0.20)", "Generating Google AI Romaji...")
                import threading
                def _bg_manual_google():
                    success = GoogleRomajiClient.enrich_lyrics(
                        cd,
                        cancellation_check=lambda: getattr(self, 'active_request_id', 0) != req_id
                    )
                    if success and getattr(self, 'active_request_id', 0) == req_id:
                        if self.current_track:
                            title = self.current_track.get('title', '')
                            artist = self.current_track.get('artist', '')
                            duration = self.current_track.get('duration', 0.0)
                            self.cache_mgr.put(title, artist, duration, cd)
                        QTimer.singleShot(0, lambda: self._render_lyrics(cd))
                threading.Thread(target=_bg_manual_google, daemon=True).start()

        # 2. On-demand fetch for Genius Romanized
        elif mode == "genius" and cd and not getattr(cd, 'has_genius_romaji', False):
            from LyricsEngine import GeniusClient
            self._set_subtext_badge("SEARCHING GENIUS...", "#00E5FF", "rgba(0, 229, 255, 0.20)", "Searching Genius.com Romanizations...")
            import threading
            def _bg_manual_genius():
                title = self.current_track.get('title', '') if self.current_track else cd.title
                artist = self.current_track.get('artist', '') if self.current_track else cd.artist
                duration = self.current_track.get('duration', 0.0) if self.current_track else 0.0
                success = GeniusClient.enrich_lyrics(
                    cd, title=title, artist=artist,
                    cancellation_check=lambda: getattr(self, 'active_request_id', 0) != req_id
                )
                if success and getattr(self, 'active_request_id', 0) == req_id:
                    self.cache_mgr.put(title, artist, duration, cd)
                    QTimer.singleShot(0, lambda: self._render_lyrics(cd))
                elif not success and getattr(self, 'active_request_id', 0) == req_id:
                    QTimer.singleShot(0, self._apply_subtext_mode)
            threading.Thread(target=_bg_manual_genius, daemon=True).start()

        # 3. On-demand fetch for NetEase Romaji / Translation
        elif mode in ("netease", "translation") and cd and not (getattr(cd, 'has_netease_romaji', False) or getattr(cd, 'has_translation', False)):
            from LyricsEngine import NetEaseClient
            self._set_subtext_badge("FETCHING NETEASE...", "#00FF9D", "rgba(0, 255, 157, 0.20)", "Querying NetEase Cloud Romaji & Translation...")
            import threading
            def _bg_manual_netease():
                title = self.current_track.get('title', '') if self.current_track else cd.title
                artist = self.current_track.get('artist', '') if self.current_track else cd.artist
                duration = self.current_track.get('duration', 0.0) if self.current_track else 0.0
                success = NetEaseClient.enrich_lyrics(
                    cd, title=title, artist=artist, duration=duration,
                    cancellation_check=lambda: getattr(self, 'active_request_id', 0) != req_id
                )
                if success and getattr(self, 'active_request_id', 0) == req_id:
                    self.cache_mgr.put(title, artist, duration, cd)
                    QTimer.singleShot(0, lambda: self._render_lyrics(cd))
                elif not success and getattr(self, 'active_request_id', 0) == req_id:
                    QTimer.singleShot(0, self._apply_subtext_mode)
            threading.Thread(target=_bg_manual_netease, daemon=True).start()

        self._apply_subtext_mode()

    def _apply_subtext_mode(self):
        """Apply active subtext mode across all displayed lyric line items with subtext_line_offset support, smart fallback, and instrumental skipping."""
        mode = getattr(self, "subtext_mode", "auto")
        sub_offset = getattr(self, "subtext_line_offset", 0)
        has_any_sub = False
        has_google = False
        has_genius = False
        has_netease = False
        has_roma = False
        has_trans = False

        # 1. Identify vocal line widgets and extract their raw subtexts (skip instrumental markers like '♪')
        vocal_line_widgets = []
        raw_vocal_subtexts = []

        for lw in self.line_widgets:
            ld = lw.line_data
            if getattr(ld, 'google_romaji', None):
                has_google = True
            if getattr(ld, 'genius_romaji', None):
                has_genius = True
            if getattr(ld, 'netease_romaji', None):
                has_netease = True
            if getattr(ld, 'romaji', None):
                has_roma = True
            if getattr(ld, 'raw_translation', None):
                has_trans = True

            # If this line is an instrumental marker (e.g. '♪' / music icon), clear subtext and skip
            if is_instrumental_line(lw.text):
                lw.set_subtext(None)
                continue

            vocal_line_widgets.append(lw)

            target = ""
            if mode == "google":
                target = getattr(ld, 'google_romaji', None) or getattr(ld, 'romaji', None) or ""
            elif mode == "genius":
                # Smart fallback: If Genius wasn't found, fallback to Google Romaji or general Romaji
                target = getattr(ld, 'genius_romaji', None) or getattr(ld, 'google_romaji', None) or getattr(ld, 'romaji', None) or ""
            elif mode == "netease":
                # Smart fallback: If NetEase wasn't found, fallback to Google Romaji or general Romaji
                target = getattr(ld, 'netease_romaji', None) or getattr(ld, 'google_romaji', None) or getattr(ld, 'romaji', None) or ""
            elif mode == "romaji":
                target = (
                    getattr(ld, 'google_romaji', None)
                    or getattr(ld, 'romaji', None)
                    or getattr(ld, 'genius_romaji', None)
                    or getattr(ld, 'netease_romaji', None)
                    or ""
                )
            elif mode == "translation":
                # Smart fallback: If translation wasn't found, fallback to Romaji
                target = getattr(ld, 'raw_translation', None) or getattr(ld, 'google_romaji', None) or getattr(ld, 'romaji', None) or ""
            elif mode == "none":
                target = ""
            else:  # auto
                target = (
                    getattr(ld, 'google_romaji', None)
                    or getattr(ld, 'genius_romaji', None)
                    or getattr(ld, 'netease_romaji', None)
                    or getattr(ld, 'romaji', None)
                    or getattr(ld, 'raw_translation', None)
                    or ld.translation
                    or ""
                )
            clean_sub = target.strip() if target else None
            if is_instrumental_line(clean_sub):
                clean_sub = None
            elif clean_sub:
                # Defensive guard: reject any subtext containing unparsed delimiter remnants or excessive block lengths
                if '⟦' in clean_sub or '⟧' in clean_sub or '[ # ]' in clean_sub or '§#§' in clean_sub or '|||' in clean_sub or len(clean_sub) > max(140, len(lw.text or "") * 5):
                    clean_sub = None
            raw_vocal_subtexts.append(clean_sub)

        # 2. Map subtexts strictly across vocal lines respecting subtext_line_offset
        num_vocal = len(vocal_line_widgets)
        for i, lw in enumerate(vocal_line_widgets):
            source_idx = i + sub_offset
            clean = raw_vocal_subtexts[source_idx] if 0 <= source_idx < num_vocal else None
            lw.set_subtext(clean)
            if clean:
                has_any_sub = True

        # Refresh container and scroll layout to prevent squishing or clipping
        if hasattr(self, 'container_layout') and self.container_layout:
            self.container_layout.activate()
        if hasattr(self, 'container') and self.container:
            self.container.adjustSize()
        if hasattr(self, 'scroll_area') and self.scroll_area:
            self.scroll_area.update()

        # Update subtext pill badge UI
        if mode == "google":
            label = "SUB: G-ROMA"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "genius":
            label = "SUB: GENIUS"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "netease":
            label = "SUB: NETEASE"
            color = "#00FF9D"
            bg = "rgba(0, 255, 157, 0.15)"
        elif mode == "romaji":
            label = "SUB: ROMA"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "translation":
            label = "SUB: TRANS"
            color = "#A78BFA"
            bg = "rgba(167, 139, 250, 0.15)"
        elif mode == "none":
            label = "SUB: OFF"
            color = "#8c92a4"
            bg = "rgba(255, 255, 255, 0.08)"
        else:  # auto
            if has_google:
                label = "SUB: G-ROMA"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_genius:
                label = "SUB: GENIUS"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_netease or has_roma:
                label = "SUB: ROMA"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_trans:
                label = "SUB: TRANS"
                color = "#A78BFA"
                bg = "rgba(167, 139, 250, 0.15)"
            else:
                label = "SUB: AUTO"
                color = "#00E5FF" if has_any_sub else "#8c92a4"
                bg = "rgba(0, 229, 255, 0.15)" if has_any_sub else "rgba(255, 255, 255, 0.08)"

        tooltip = f"Subtext Stream: {label.replace('SUB: ', '')} (Click to switch)"
        if getattr(self.current_data, 'genius_url', ''):
            tooltip += f" | Genius: {self.current_data.genius_url}"
        self._set_subtext_badge(label, color, bg, tooltip)

    def _set_provider_and_fetch(self, provider_key: str):
        """Update provider preference and re-fetch lyrics for the active track."""
        self.selected_provider = provider_key
        rev_mapping = {
            "auto": "Auto",
            "musixmatch": "Musixmatch",
            "netease": "NetEase",
            "lrclib": "LRCLIB",
            "local": "Local"
        }
        if hasattr(self, 'source_pill') and isinstance(self.source_pill, QComboBox):
            target_text = rev_mapping.get(provider_key, "Auto")
            self.source_pill.blockSignals(True)
            self.source_pill.setCurrentText(target_text)
            self.source_pill.blockSignals(False)
        if self.current_track:
            title = self.current_track.get('title', '')
            artist = self.current_track.get('artist', '')
            duration = self.current_track.get('duration', 0.0)
            if provider_key != "auto":
                self.cache_mgr.delete(title, artist, duration)
            self.load_track(self.current_track, provider=provider_key)

    def _on_user_scroll(self):
        self._user_scrolling_paused = True
        self.scroll_resume_timer.start()

    def _resume_auto_scroll(self):
        self._user_scrolling_paused = False
        if self.active_index >= 0:
            self._scroll_to_index(self.active_index)
        elif self.timestamps and self.current_data and self.current_data.is_synced:
            vbar = self.scroll_area.verticalScrollBar()
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(vbar.value())
            self._scroll_anim.setEndValue(0)
            self._scroll_anim.start()

    def load_track(self, track: Dict[str, Any], provider: Optional[str] = None):
        """Load lyrics for a newly selected track with optional provider override."""
        if not track:
            return

        chosen_provider = provider or getattr(self, 'selected_provider', 'auto')
        self.current_track = track
        self.request_id_counter += 1
        self.active_request_id = self.request_id_counter
        self.active_index = -1
        self.user_offset_ms = 0
        self.subtext_line_offset = 0
        if hasattr(self, 'lyric_offset_spin'):
            self.lyric_offset_spin.blockSignals(True)
            self.lyric_offset_spin.setValue(0.0)
            self.lyric_offset_spin.blockSignals(False)
        if hasattr(self, 'sub_offset_spin'):
            self.sub_offset_spin.blockSignals(True)
            self.sub_offset_spin.setValue(0)
            self.sub_offset_spin.blockSignals(False)

        raw_title = track.get('title', 'Unknown Track')
        raw_artist = track.get('artist', '')
        candidates = LyricQuerySanitizer.extract_candidates(raw_title, raw_artist)
        if candidates:
            disp_title, disp_artist = candidates[0]
        else:
            disp_title = LyricQuerySanitizer.clean_title(raw_title) or raw_title
            disp_artist = LyricQuerySanitizer.clean_artist(raw_artist)

        if disp_artist:
            self.title_label.setText(f"{disp_title}  —  {disp_artist}")
        else:
            self.title_label.setText(disp_title)

        provider_tag = f" ({chosen_provider.upper()})" if chosen_provider != "auto" else ""
        self._set_source_badge(f"SEARCHING{provider_tag}...", "#FDA903", "rgba(253, 169, 3, 0.15)", f"Searching via {chosen_provider.upper()}... Click to switch")

        self._clear_lines()

        # Stop previous worker if active
        if self.current_worker and self.current_worker.isRunning():
            try:
                self.current_worker.cancel()
                self.current_worker.disconnect()
            except Exception:
                pass

        # Launch background worker
        self.current_worker = LyricsFetchWorker(self.active_request_id, track, self.cache_mgr, provider=chosen_provider, parent=self)
        self.current_worker.lyricsReady.connect(self._on_lyrics_ready)
        self.current_worker.start()

    def _start_reload_animation(self):
        """Trigger rotating spin animation on reload icon."""
        if hasattr(self, '_reload_spin_anim') and self._reload_spin_anim:
            self._reload_spin_anim.stop()
            self._reload_spin_anim.start()

    def _on_reload_spin_frame(self, angle: float):
        """Rotate reload SVG icon around invariant center pivot during spin animation."""
        if not hasattr(self, 'btn_reload') or not self.btn_reload:
            return
        if not hasattr(self, '_orig_refresh_pixmap') or self._orig_refresh_pixmap is None or self._orig_refresh_pixmap.isNull():
            path = getattr(self, '_refresh_icon_path', '')
            if not path or not os.path.exists(path):
                return
            self._orig_refresh_pixmap = QIcon(path).pixmap(QSize(32, 32))
            if self._orig_refresh_pixmap.isNull():
                return

        canvas_size = 48
        canvas = QPixmap(canvas_size, canvas_size)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        center = canvas_size / 2.0
        p.translate(center, center)
        p.rotate(angle)
        src_w = self._orig_refresh_pixmap.width()
        src_h = self._orig_refresh_pixmap.height()
        p.drawPixmap(int(-src_w / 2.0), int(-src_h / 2.0), self._orig_refresh_pixmap)
        p.end()
        self.btn_reload.setIcon(QIcon(canvas))

    def _on_reload_spin_finished(self):
        """Reset icon to original clean state after rotation animation completes."""
        if hasattr(self, 'btn_reload') and self.btn_reload and hasattr(self, '_refresh_icon_path'):
            self.btn_reload.setIcon(QIcon(self._refresh_icon_path))

    def reload_current_track(self):
        """Force re-fetch lyrics for current track and delete cache."""
        self._start_reload_animation()
        if self.current_track:
            title = self.current_track.get('title', '')
            artist = self.current_track.get('artist', '')
            duration = self.current_track.get('duration', 0.0)
            self.cache_mgr.delete(title, artist, duration)
            self.load_track(self.current_track, provider=getattr(self, 'selected_provider', 'auto'))

    def _on_lyrics_ready(self, req_id: int, data: LyricData):
        if req_id != self.active_request_id:
            return  # Ignore outdated responses from fast track skips

        self.current_data = data
        source_raw = (data.source or "NONE").upper()
        
        # Clean & shorten source brand name for the badge
        if "MUSIXMATCH" in source_raw:
            source_brand = "MUSIXMATCH"
            pill_color = "#1DB954"
            pill_bg = "rgba(29, 185, 84, 0.18)"
        elif "NETEASE" in source_raw:
            source_brand = "NETEASE"
            pill_color = "#00E5FF"
            pill_bg = "rgba(0, 229, 255, 0.18)"
        elif "LRCLIB" in source_raw:
            source_brand = "LRCLIB"
            pill_color = "#FF5B06"
            pill_bg = "rgba(255, 91, 6, 0.18)"
        elif "LOCAL" in source_raw:
            source_brand = "LOCAL LRC"
            pill_color = "#FDA903"
            pill_bg = "rgba(253, 169, 3, 0.18)"
        elif "TAG" in source_raw or "EMBEDDED" in source_raw:
            source_brand = "EMBEDDED"
            pill_color = "#FDA903"
            pill_bg = "rgba(253, 169, 3, 0.18)"
        elif "CACHE" in source_raw:
            source_brand = "CACHED"
            pill_color = "#A78BFA"
            pill_bg = "rgba(167, 139, 250, 0.18)"
        else:
            source_brand = source_raw.replace("ONLINE", "").strip() or "UNKNOWN"
            pill_color = "#8c92a4"
            pill_bg = "rgba(255, 255, 255, 0.08)"

        tooltip_text = f"Source: {data.source} (Click to switch provider)" if data.source else "No lyrics (Click to switch provider)"

        if data.is_synced:
            self._set_source_badge(f"SYNCED • {source_brand}", pill_color, pill_bg, tooltip_text)
        elif data.plain_text and data.source != "none":
            self._set_source_badge(f"PLAIN • {source_brand}", pill_color, pill_bg, tooltip_text)
        else:
            self._set_source_badge("NO LYRICS", "#8c92a4", "rgba(255, 255, 255, 0.08)", "No lyrics available (Click to switch provider)")

        # If data has title/artist from tags or LRCLIB, update header title
        if data.title:
            if data.artist:
                self.title_label.setText(f"{data.title}  —  {data.artist}")
            else:
                self.title_label.setText(data.title)

        self._render_lyrics(data)

    def _clear_lines(self):
        if hasattr(self, '_scroll_anim'):
            self._scroll_anim.stop()
        for w in self.line_widgets:
            if hasattr(w, 'cleanup'):
                w.cleanup()
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.line_widgets.clear()
        self.timestamps.clear()

    def _render_lyrics(self, data: LyricData):
        if not data:
            self.current_data = None
            self._clear_lines()
            return

        self.current_data = data

        # Smooth in-place update if widgets already match the line count (e.g. Romaji / translation arrival)
        if self.line_widgets and len(self.line_widgets) == len(data.lines):
            for idx, line in enumerate(data.lines):
                if idx < len(self.line_widgets):
                    self.line_widgets[idx].line_data = line
                    if line.text and self.line_widgets[idx].text != line.text:
                        self.line_widgets[idx].text = line.text
            self._apply_subtext_mode()
            return

        self._clear_lines()
        for idx, line in enumerate(data.lines):
            item_widget = LyricLineWidget(idx, line, self.container)
            item_widget.clicked.connect(self.seekRequested.emit)
            self.container_layout.addWidget(item_widget)
            self.line_widgets.append(item_widget)
            if line.time_ms >= 0:
                self.timestamps.append(line.time_ms)
        self._apply_subtext_mode()

    def on_position_changed(self, pos_ms: int):
        """Update active lyric line based on current player position."""
        self._last_pos_ms = pos_ms
        if not self.current_data or not self.current_data.is_synced or not self.timestamps:
            return

        effective_pos = pos_ms + self.user_offset_ms

        # 1. Pre-vocal intro period: before the first synchronized lyric cue
        if effective_pos < self.timestamps[0]:
            if self.active_index != -1:
                if 0 <= self.active_index < len(self.line_widgets):
                    self.line_widgets[self.active_index].set_active(False)
                self.active_index = -1
                if not self._user_scrolling_paused:
                    vbar = self.scroll_area.verticalScrollBar()
                    self._scroll_anim.stop()
                    self._scroll_anim.setStartValue(vbar.value())
                    self._scroll_anim.setEndValue(0)
                    self._scroll_anim.start()
            return

        # 2. Active vocal period: binary search for the active cue line
        idx = bisect.bisect_right(self.timestamps, effective_pos) - 1
        idx = max(0, min(idx, len(self.line_widgets) - 1))

        if idx != self.active_index:
            if 0 <= self.active_index < len(self.line_widgets):
                self.line_widgets[self.active_index].set_active(False)
            self.active_index = idx
            if 0 <= idx < len(self.line_widgets):
                self.line_widgets[idx].set_active(True)
                if not self._user_scrolling_paused:
                    self._scroll_to_index(idx)

    def _scroll_to_index(self, idx: int):
        if 0 <= idx < len(self.line_widgets):
            target_widget = self.line_widgets[idx]
            vbar = self.scroll_area.verticalScrollBar()
            viewport_h = self.scroll_area.viewport().height()
            target_y = target_widget.pos().y() + (target_widget.height() // 2) - (viewport_h // 2)
            clamped_y = max(0, min(target_y, vbar.maximum()))

            # Stop existing scroll animation and smoothly transition from current value
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(vbar.value())
            self._scroll_anim.setEndValue(clamped_y)
            self._scroll_anim.start()

    def adjust_offset(self, delta_ms: int, reset: bool = False):
        """Adjust or reset lyric sync offset."""
        if reset:
            self.user_offset_ms = 0
        else:
            self.user_offset_ms += delta_ms
        if hasattr(self, 'lyric_offset_spin'):
            self.lyric_offset_spin.blockSignals(True)
            self.lyric_offset_spin.setValue(self.user_offset_ms / 1000.0)
            self.lyric_offset_spin.blockSignals(False)
        if hasattr(self, '_last_pos_ms') and self._last_pos_ms is not None:
            self.on_position_changed(self._last_pos_ms)
        elif self.active_index >= 0 and not self._user_scrolling_paused:
            self._scroll_to_index(self.active_index)

    def _on_lyric_spin_changed(self, value: float):
        """Handle lyric timing sync offset change from QDoubleSpinBox."""
        self.user_offset_ms = int(round(value * 1000))
        if hasattr(self, '_last_pos_ms') and self._last_pos_ms is not None:
            self.on_position_changed(self._last_pos_ms)
        elif self.active_index >= 0 and not self._user_scrolling_paused:
            self._scroll_to_index(self.active_index)

    def _on_sub_spin_changed(self, value: int):
        """Handle subtext line alignment change from QSpinBox."""
        self.subtext_line_offset = value
        self._apply_subtext_mode()

    def adjust_sub_offset(self, delta_lines: int, reset: bool = False):
        """Adjust or reset subtext line alignment offset."""
        if reset:
            self.subtext_line_offset = 0
        else:
            self.subtext_line_offset = getattr(self, "subtext_line_offset", 0) + delta_lines
            
        if hasattr(self, 'sub_offset_spin'):
            self.sub_offset_spin.blockSignals(True)
            self.sub_offset_spin.setValue(self.subtext_line_offset)
            self.sub_offset_spin.blockSignals(False)
        self._apply_subtext_mode()

    def set_animating_state(self, is_animating: bool):
        """Freeze or unfreeze line measurements and layout recalculations during splitter sliding."""
        self._is_animating_slide = is_animating
        for line in getattr(self, 'line_widgets', []):
            if hasattr(line, 'set_animating_state'):
                line.set_animating_state(is_animating)
        if not is_animating and hasattr(self, 'active_index') and self.active_index >= 0:
            self._scroll_to_index(self.active_index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, '_is_animating_slide', False):
            for line in getattr(self, 'line_widgets', []):
                if hasattr(line, '_recalculate_height'):
                    line._recalculate_height()

    def cleanup(self):
        """Stop all running timers and property animations before destruction."""
        try:
            if hasattr(self, '_scroll_anim') and self._scroll_anim:
                self._scroll_anim.stop()
            if hasattr(self, '_offset_anim') and self._offset_anim:
                self._offset_anim.stop()
            if hasattr(self, '_reload_spin_anim') and self._reload_spin_anim:
                self._reload_spin_anim.stop()
            if hasattr(self, 'scroll_resume_timer') and self.scroll_resume_timer:
                self.scroll_resume_timer.stop()
            if hasattr(self, 'current_worker') and self.current_worker and self.current_worker.isRunning():
                self.current_worker.cancel()
            for line in getattr(self, 'line_widgets', []):
                if hasattr(line, 'cleanup'):
                    line.cleanup()
        except Exception:
            pass
