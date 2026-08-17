from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont


class SpotlightOverlay(QWidget):
    """
    A full-screen (or full-dialog) overlay that darkens everything except 
    a rounded spotlight hole over a target widget. Optionally shows 
    an instruction label near the spotlight.
    """

    def __init__(self, parent, target_widget, on_target_clicked=None, instruction_text="", auto_click_target=True):
        super().__init__(parent)
        self.target_widget = target_widget
        self.on_target_clicked = on_target_clicked
        self.instruction_text = instruction_text
        self.auto_click_target = auto_click_target
        self._fading_out = False

        # CRITICAL: Do NOT set WA_StyledBackground.
        # It forces Qt to paint a solid background before paintEvent, making the overlay black.
        # Child widgets are transparent by default; we paint everything ourselves.
        self.setObjectName("spotlightOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Fill the entire parent
        self.setGeometry(parent.rect())

        # --- Instruction label ---
        self._label = QLabel(instruction_text, self)
        self._label.setObjectName("spotlightOverlayLabel")
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setFont(QFont("Orbitron", 11, QFont.Bold))
        self._label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: rgba(20, 20, 20, 200);
                border-radius: 10px;
                padding: 10px 18px;
                border: 1px solid rgba(255, 91, 6, 0.6);
            }
        """)
        self._label.setVisible(bool(instruction_text))

        # --- Opacity effect for fade ---
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(350)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def show_with_fade_in(self):
        """Show the overlay and fade in from 0 → 1."""
        self.show()
        self.raise_()
        self._position_label()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def fade_out(self):
        """Fade out 1 → 0 then destroy the widget."""
        if self._fading_out:
            return
        self._fading_out = True
        self.anim.stop()
        # Use UniqueConnection so we don't stack multiple deleteLater calls
        try:
            self.anim.finished.connect(self.deleteLater, Qt.UniqueConnection)
        except RuntimeError:
            pass
        self.anim.setStartValue(self.opacity_effect.opacity())
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _get_target_rect(self):
        """Get target widget's rect in this overlay's coordinate space."""
        if not self.target_widget or not self.target_widget.isVisible():
            return QRect()
        try:
            global_pos = self.target_widget.mapToGlobal(QPoint(0, 0))
            local_pos = self.mapFromGlobal(global_pos)
            return QRect(local_pos, self.target_widget.size())
        except RuntimeError:
            return QRect()

    def _position_label(self):
        """Place the instruction label above or below the spotlight hole."""
        if not self.instruction_text:
            return
        target_rect = self._get_target_rect()
        self._label.adjustSize()
        lw = max(self._label.sizeHint().width() + 36, 280)
        lh = self._label.sizeHint().height() + 20
        self._label.setFixedSize(lw, lh)

        # Prefer to show BELOW the spotlight; fall back to ABOVE if near bottom
        spotlight_adjusted = target_rect.adjusted(-10, -10, 10, 10)
        label_x = max(10, spotlight_adjusted.center().x() - lw // 2)
        label_x = min(label_x, self.width() - lw - 10)

        gap = 16
        if spotlight_adjusted.bottom() + lh + gap < self.height():
            label_y = spotlight_adjusted.bottom() + gap
        else:
            label_y = spotlight_adjusted.top() - lh - gap
        label_y = max(10, min(label_y, self.height() - lh - 10))

        self._label.move(label_x, label_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_label()

    # ---------- painting ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        full_path = QPainterPath()
        full_path.addRect(QRectF(self.rect()))

        target_rect = self._get_target_rect()
        if not target_rect.isEmpty():
            spotlight_path = QPainterPath()
            spotlight_path.addRoundedRect(
                QRectF(target_rect.adjusted(-10, -10, 10, 10)), 14, 14
            )
            full_path = full_path.subtracted(spotlight_path)

        painter.fillPath(full_path, QColor(0, 0, 0, 185))

    # ---------- input ----------

    def mousePressEvent(self, event):
        if self._fading_out:
            event.accept()
            return

        target_rect = self._get_target_rect()
        click_rect = target_rect.adjusted(-10, -10, 10, 10)

        if not target_rect.isEmpty() and click_rect.contains(event.position().toPoint()):
            # Clicked inside the spotlight — fade out, then fire callbacks
            self.fade_out()
            cb = self.on_target_clicked
            tw = self.target_widget if self.auto_click_target else None
            # Use class-level static ref so the lambda doesn't hold 'self'
            # (self may be deleted by deleteLater before the timer fires)
            _fn = SpotlightOverlay._fire_callbacks
            QTimer.singleShot(50, lambda: _fn(cb, tw))
        else:
            # Outside spotlight — consume the event
            event.accept()

    @staticmethod
    def _fire_callbacks(cb, tw):
        try:
            if cb:
                cb()
        except RuntimeError:
            pass
        try:
            if tw and hasattr(tw, 'click'):
                tw.click()
        except RuntimeError:
            pass
