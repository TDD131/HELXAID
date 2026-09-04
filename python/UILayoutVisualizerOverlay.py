"""
UILayoutVisualizerOverlay.py - Real-Size UI Bounds & Dimensions Visualizer for HELXAID
=====================================================================================
A non-intrusive, 100% click-through HUD wireframe overlay that renders clean border outlines
around all visible UI widgets to clearly inspect gaps, paddings, and bounds without visual clutter.

Shortcut: Ctrl + F12 (Global Toggle)
Component Name: UILayoutVisualizerOverlay
"""

import os
from typing import List, Tuple, Optional
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QCursor
from PySide6.QtWidgets import QWidget, QApplication, QFrame, QPushButton, QLineEdit, QLabel, QScrollArea


class UILayoutVisualizerOverlay(QWidget):
    """
    Component Name: uiLayoutVisualizerOverlay
    Global transparent wireframe overlay that renders clean border outlines around all
    visible UI widgets without cluttering badges, while showing exact dimensions on hover.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("uiLayoutVisualizerOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        
        # Cover entire parent window
        if parent:
            self.setGeometry(parent.rect())
        self.hide()
        
        # Auto-refresh timer for dynamic scrolling & cursor tracking
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(80)  # ~12 FPS polling for smooth tracking
        self._refresh_timer.timeout.connect(self._check_and_repaint)
        
        self._is_active = False

    def toggle(self):
        """Toggle the visualizer overlay ON / OFF."""
        if self._is_active:
            self.deactivate()
        else:
            self.activate()

    def activate(self):
        self._is_active = True
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._refresh_timer.start()
        self.update()

    def deactivate(self):
        self._is_active = False
        self._refresh_timer.stop()
        self.hide()

    def _check_and_repaint(self):
        if self._is_active and self.isVisible():
            if self.parentWidget() and self.geometry() != self.parentWidget().rect():
                self.setGeometry(self.parentWidget().rect())
            self.raise_()
            self.update()

    def paintEvent(self, event):
        if not self._is_active or not self.parentWidget():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)  # Crisp 1px pixel-aligned lines

        parent_window = self.parentWidget()
        all_widgets = parent_window.findChildren(QWidget)
        
        overlay_rect = self.rect()
        cursor_pos = self.mapFromGlobal(QCursor.pos())

        hovered_widget = None
        hovered_box = None
        hovered_info = ""
        smallest_hover_area = float('inf')

        # 1. First pass: Draw pure clean 1px border outlines around all widgets (NO background, NO clutter)
        painter.setBrush(Qt.NoBrush)

        for w in all_widgets:
            if w is self or not w.isVisible() or w.isHidden():
                continue
            
            # Skip tiny invisible spacers
            rect = w.rect()
            if rect.width() < 10 or rect.height() < 10:
                continue

            # Map coordinates to overlay via global coordinates to ensure perfect alignment in windowed mode
            top_left = self.mapFromGlobal(w.mapToGlobal(QPoint(0, 0)))
            box_rect = QRect(top_left.x(), top_left.y(), rect.width(), rect.height())

            # Intersect with overlay bounds to ensure it's in viewport
            if not box_rect.intersects(overlay_rect):
                continue
            
            # Check parent scroll clipping if inside a QScrollArea viewport
            p = w.parentWidget()
            is_clipped = False
            while p and p is not parent_window:
                if p.isWidgetType() and isinstance(p.parentWidget(), QScrollArea):
                    vp_top_left = self.mapFromGlobal(p.mapToGlobal(QPoint(0, 0)))
                    vp_rect = QRect(vp_top_left, p.size())
                    if not box_rect.intersects(vp_rect):
                        is_clipped = True
                        break
                p = p.parentWidget()
            if is_clipped:
                continue

            # Check if this widget is hovered by mouse (select the innermost/smallest widget under cursor)
            if box_rect.contains(cursor_pos):
                area = box_rect.width() * box_rect.height()
                if area < smallest_hover_area:
                    smallest_hover_area = area
                    hovered_widget = w
                    hovered_box = box_rect
                    name = w.objectName() or w.__class__.__name__
                    hovered_info = f"#{name} [{rect.width()} x {rect.height()}]"

            # Determine crisp outline color based on widget type
            cls_name = w.__class__.__name__
            if isinstance(w, QPushButton):
                border_color = QColor(255, 91, 6, 200)    # Cyber Orange
            elif isinstance(w, QLineEdit):
                border_color = QColor(255, 214, 0, 200)   # Neon Yellow
            elif isinstance(w, QFrame) or "Card" in cls_name or "Panel" in cls_name or "Section" in cls_name:
                border_color = QColor(0, 229, 255, 180)   # Neon Cyan
            elif isinstance(w, QLabel):
                border_color = QColor(187, 134, 252, 130) # Neon Purple
            else:
                border_color = QColor(0, 255, 136, 120)   # Neon Green

            # Draw clean 1px outline
            pen = QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(box_rect)

        # 2. Highlight ONLY the single hovered widget (if any) with a high-contrast box & dimension badge
        if hovered_widget and hovered_box:
            painter.setRenderHint(QPainter.Antialiasing, True)
            
            # Hovered bright border
            h_pen = QPen(QColor(255, 255, 255, 255))
            h_pen.setWidth(2)
            painter.setPen(h_pen)
            painter.setBrush(QBrush(QColor(255, 91, 6, 25)))
            painter.drawRect(hovered_box)

            # Single compact dimension badge over hovered widget
            font = QFont("Orbitron", 8)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(hovered_info) + 12
            th = fm.height() + 4

            bx = hovered_box.x()
            by = hovered_box.y() - th - 2
            if by < 0:
                by = hovered_box.y() + 2
            if bx + tw > overlay_rect.width():
                bx = overlay_rect.width() - tw - 2

            badge_rect = QRect(bx, by, tw, th)
            painter.setPen(QPen(QColor(255, 91, 6), 1))
            painter.setBrush(QBrush(QColor(14, 16, 23, 245)))
            painter.drawRoundedRect(badge_rect, 3, 3)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignCenter, hovered_info)

        # 3. Draw Clean Minimal HUD Banner at top-right
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Orbitron", 8)
        font.setBold(True)
        painter.setFont(font)
        
        banner_text = f"⚡ UI WIREFRAME: ON | {hovered_info if hovered_info else 'Hover any widget for size'} | Ctrl+F12"
        fm = painter.fontMetrics()
        bw = fm.horizontalAdvance(banner_text) + 24
        bh = 26
        banner_rect = QRect(overlay_rect.width() - bw - 16, 12, bw, bh)

        painter.setPen(QPen(QColor(255, 91, 6, 200), 1))
        painter.setBrush(QBrush(QColor(14, 16, 23, 230)))
        painter.drawRoundedRect(banner_rect, 4, 4)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(banner_rect, Qt.AlignCenter, banner_text)

        painter.end()
