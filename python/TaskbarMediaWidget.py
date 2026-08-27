"""
TaskbarMediaWidget - Docked Media Controls for Windows Taskbar
==============================================================
Component Name: TaskbarMediaWidget
Description:
    Cyber-sleek, glassmorphic media widget docked directly onto the
    Windows Taskbar (adjacent to the System Tray / Clock).
    Provides instant Play/Pause, Next, Previous controls and live track
    title feedback without stealing focus from active games/apps (WS_EX_NOACTIVATE).

Rules strictly followed:
    - Orbitron font everywhere
    - SVG vector icons (NO emojis)
    - Less border, more rich background-color
    - Component names (setObjectName) on every element
"""

import os
import sys
import random
import ctypes
from ctypes import windll, Structure, byref, c_long
from ctypes.wintypes import HWND, RECT, DWORD

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame,
    QGraphicsDropShadowEffect, QApplication, QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPoint, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import (
    QFont, QColor, QPainter, QIcon, QPixmap, QCursor,
    QAction, QLinearGradient, QBrush, QPen
)
from PySide6.QtSvg import QSvgRenderer

user32 = windll.user32


class RECT_STRUCT(Structure):
    _fields_ = [
        ("left", c_long),
        ("top", c_long),
        ("right", c_long),
        ("bottom", c_long),
    ]


def _render_svg_icon(svg_xml: str, size: int = 14, color: str = "#FF5B06", w: int = None, h: int = None) -> QIcon:
    """Helper to render vector SVG XML into crisp QIcon."""
    width = w if w is not None else size
    height = h if h is not None else size
    formatted_svg = svg_xml.replace('currentColor', color)
    renderer = QSvgRenderer(bytearray(formatted_svg, encoding='utf-8'))
    pixmap = QPixmap(width * 2, height * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


def _get_taskbar_icon(filename: str, fallback_svg: str = "", size: int = 14, color: str = "#FF5B06") -> QIcon:
    """Load icon from 'UI Taskbar Icons' directory with fallback to inline SVG."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "UI Taskbar Icons", filename)
    if not os.path.exists(icon_path) and getattr(sys, 'frozen', False):
        icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), "UI Taskbar Icons", filename)
        
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    elif fallback_svg:
        return _render_svg_icon(fallback_svg, size=size, color=color)
    return QIcon()


def _get_ui_icon(filename: str, fallback_svg: str = "", size: int = 14, color: str = "#FFFFFF") -> QIcon:
    """Load icon from 'UI Icons' directory with fallback to inline SVG."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "UI Icons", filename)
    if not os.path.exists(icon_path) and getattr(sys, 'frozen', False):
        icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), "UI Icons", filename)
        
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    elif fallback_svg:
        return _render_svg_icon(fallback_svg, size=size, color=color)
    return QIcon()


# Clean vector SVG definitions (Used for note, close, grip, and fallback)
SVG_PREV = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>"""
SVG_PLAY = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>"""
SVG_PAUSE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>"""
SVG_NEXT = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>"""
SVG_MUSIC_NOTE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>"""
SVG_CLOSE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>"""
SVG_MINIMIZE_GRIP = """<svg viewBox="0 0 14 24" fill="currentColor"><rect x="2.2" y="3.5" width="2.8" height="17" rx="1.4"/><rect x="9" y="3.5" width="2.8" height="17" rx="1.4"/></svg>"""
SVG_LOCK = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>"""
SVG_UNLOCK = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5-2.28 0-4.27 1.54-4.84 3.75-.14.54.18 1.08.72 1.23.53.14 1.08-.18 1.22-.72C9.44 3.88 10.6 3 12 3c1.66 0 3 1.34 3 3v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z"/></svg>"""
SVG_POSITION = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>"""
SVG_OPEN_APP = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>"""
SVG_OPACITY = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18V4c4.41 0 8 3.59 8 8s-3.59 8-8 8z"/></svg>"""


class TaskbarGripButton(QPushButton):
    """Interactive grip handle with two orange bars supporting click toggle & horizontal drag resize."""
    drag_started = Signal(int)
    dragged = Signal(int)
    drag_finished = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskbarMediaMinimizeBtn")
        self.setFixedSize(14, 22)
        self.setCursor(QCursor(Qt.SizeHorCursor))
        self.setToolTip("Minimize / Expand (Drag to resize)")
        self._dragging = False
        self._press_x = 0
        self._has_dragged = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._has_dragged = False
            self._press_x = event.globalPosition().x()
            self.drag_started.emit(int(self._press_x))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            cur_x = event.globalPosition().x()
            delta_x = cur_x - self._press_x
            if abs(delta_x) >= 3:
                self._has_dragged = True
            if self._has_dragged:
                self.dragged.emit(int(delta_x))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            if self._has_dragged:
                self.drag_finished.emit()
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MiniSpectrumVisualizer(QWidget):
    """
    Mini animated audio spectrum equalizer bars for TaskbarMediaWidget with smooth transitions.
    Component Name: taskbarMediaVisualizer
    """
    def __init__(self, parent=None, bar_count: int = 7):
        super().__init__(parent)
        self.setObjectName("taskbarMediaVisualizer")
        self.setFixedSize(35, 16)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("Audio Spectrum Visualizer")
        self._bar_count = bar_count
        self._is_active = False
        self._suppressed = False
        self._opacity = 1.0
        
        # Initial bar heights normalized (0.0 to 1.0)
        self._bar_heights = [0.15] * bar_count
        self._target_heights = [0.15] * bar_count
        
        # Smooth transition animation
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_anim.valueChanged.connect(self._on_fade_value_changed)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._fade_finish_cb = None
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_bars)
        self._timer.start(50)  # 20 FPS smooth animation
        
    def _on_fade_value_changed(self, val):
        self._opacity = float(val)
        self.update()

    def _on_fade_finished(self):
        if self._suppressed:
            self.hide()
        if hasattr(self, '_fade_finish_cb') and self._fade_finish_cb:
            cb = self._fade_finish_cb
            self._fade_finish_cb = None
            try:
                cb()
            except Exception:
                pass

    def set_active(self, active: bool):
        """Set whether the visualizer is active (music playing) or idling (stopped/paused)."""
        self._is_active = bool(active)
        if not self._is_active:
            self._target_heights = [0.15] * self._bar_count
        self.update()

    def set_suppressed(self, suppressed: bool, animate: bool = True):
        """Smoothly fade out/in when suppressed by main HELXAIC visualizer."""
        self._suppressed = bool(suppressed)
        if self._fade_anim.state() == QVariantAnimation.Running:
            self._fade_anim.stop()

        if self._suppressed:
            if animate and self.isVisible():
                self._fade_anim.setDuration(240)
                self._fade_anim.setStartValue(float(self._opacity))
                self._fade_anim.setEndValue(0.0)
                self._fade_anim.start()
            else:
                self._opacity = 0.0
                self.hide()
        else:
            self.show()
            if animate:
                self._fade_anim.setDuration(300)
                self._fade_anim.setStartValue(float(self._opacity))
                self._fade_anim.setEndValue(1.0)
                self._fade_anim.start()
            else:
                self._opacity = 1.0
                self.update()

    def _update_bars(self):
        """Animate bars smoothly with realistic audio frequency dynamics."""
        if not self._is_active or self._suppressed:
            # Gradually settle bars to resting idle line
            for i in range(self._bar_count):
                self._bar_heights[i] += (0.15 - self._bar_heights[i]) * 0.15
            self.update()
            return

        for i in range(self._bar_count):
            if random.random() < 0.35:
                # Bass (left) has higher amplitude peaks, Mids balanced, Treble (right) has faster jitter
                if i <= 1:
                    base = 0.45
                elif i <= 4:
                    base = 0.35
                else:
                    base = 0.20
                self._target_heights[i] = min(1.0, max(0.18, base + random.random() * 0.70))
            
            # Smooth interpolation
            self._bar_heights[i] += (self._target_heights[i] - self._bar_heights[i]) * 0.38
            
        self.update()

    def paintEvent(self, event):
        if self._opacity <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self._opacity)
        
        w = self.width()
        h = self.height()
        gap = 1.6
        bar_w = max(2.2, (w - (self._bar_count - 1) * gap) / self._bar_count)
        
        for i in range(self._bar_count):
            bh = max(2.5, self._bar_heights[i] * (h - 1.0))
            bx = i * (bar_w + gap)
            by = h - bh
            
            # Glowing Cyberpunk Gradient (Vivid Yellow-Orange to Signal Orange)
            grad = QLinearGradient(bx, by, bx, h)
            grad.setColorAt(0.0, QColor("#FDA903"))
            grad.setColorAt(1.0, QColor("#FF5B06"))
            
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(bx, by, bar_w, bh), bar_w / 2.0, bar_w / 2.0)
            
        p.end()


class TaskbarMarqueeLabel(QLabel):
    """
    Animated Marquee Title Label for TaskbarMediaWidget.
    Smoothly scrolls long track titles horizontally when playing, with seamless loop.
    
    Component Name: TaskbarMarqueeLabel
    """
    def __init__(self, text="HELXAIC Music", parent=None):
        super().__init__(text, parent)
        self.setObjectName("taskbarMediaTitle")
        self._full_text = text
        self._offset = 0.0
        self._is_scrolling = False
        self._is_playing = False
        self._scroll_speed = 1.0  # smooth pixels per tick
        self._pause_at_start = 30  # ticks to pause at beginning (~1.0s)
        self._pause_counter = self._pause_at_start
        self._loop_gap = 40  # pixels between loop repetitions
        
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll_tick)
        self._timer.setInterval(33)  # ~30fps smooth animation

    def set_full_text(self, text: str):
        """Update track title and check if marquee scrolling is needed."""
        clean = (text or "").strip()
        if clean == self._full_text and self._is_scrolling:
            return
        self._full_text = clean
        self._offset = 0.0
        self._pause_counter = self._pause_at_start
        self._check_scroll_needed()
        self.update()

    def set_playback_state(self, is_playing: bool):
        """Start or pause marquee scrolling based on playback state."""
        self._is_playing = is_playing
        if not is_playing:
            self._timer.stop()
            self._offset = 0.0
            self._pause_counter = self._pause_at_start
        else:
            self._check_scroll_needed()
        self.update()

    def _check_scroll_needed(self):
        """Determine if text length exceeds label width."""
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._full_text)
        avail_width = self.width()

        if text_width > avail_width and avail_width > 15:
            self._is_scrolling = True
            if self._is_playing and not self._timer.isActive():
                self._timer.start()
        else:
            self._is_scrolling = False
            self._timer.stop()
            self._offset = 0.0
            self._pause_counter = self._pause_at_start

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll_needed()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def _scroll_tick(self):
        """Advance marquee scroll position."""
        if not self._is_scrolling or not self._is_playing:
            return

        if self._pause_counter > 0:
            self._pause_counter -= 1
            return

        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._full_text)

        self._offset += self._scroll_speed
        if self._offset >= text_width + self._loop_gap:
            self._offset = 0.0
            self._pause_counter = self._pause_at_start

        self.update()

    def paintEvent(self, event):
        """Custom paint with smooth clipping and marquee text loop."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(self.font())
        
        is_hover = self.underMouse()
        color = QColor("#FDA903") if is_hover else QColor("#f2f2f8")
        painter.setPen(color)

        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(self._full_text)
        avail_width = self.width()
        y = (self.height() + fm.ascent() - fm.descent()) // 2

        if not self._is_scrolling or not self._is_playing:
            if text_width > avail_width and avail_width > 10:
                elided = fm.elidedText(self._full_text, Qt.ElideRight, avail_width)
                painter.drawText(0, y, elided)
            else:
                painter.drawText(0, y, self._full_text)
        else:
            painter.setClipRect(0, 0, avail_width, self.height())
            x1 = int(-self._offset)
            painter.drawText(x1, y, self._full_text)
            
            x2 = int(-self._offset + text_width + self._loop_gap)
            painter.drawText(x2, y, self._full_text)

        painter.end()


class TaskbarMediaWidget(QWidget):
    """
    Taskbar Media Widget for HELXAIC.
    Docks seamlessly to the Windows Taskbar with zero-focus stealing.
    Supports animated collapse/expand and interactive drag resizing.
    
    Component Name: taskbarMediaWidget
    """
    prev_clicked = Signal()
    playpause_clicked = Signal()
    next_clicked = Signal()
    title_clicked = Signal()
    close_clicked = Signal()
    state_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setObjectName("taskbarMediaWidget")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._is_playing = False
        self._full_title = "HELXAIC Ready"
        self._artist = ""
        self._is_collapsed = False
        self._is_locked = False
        self._collapsed_width = 48
        self._expanded_width = 240
        self._is_animating = False
        self._is_dragging = False
        self._widget_opacity = 75

        self._init_win32_styles()
        self._init_ui()
        self._init_timer()

    def get_widget_opacity(self) -> int:
        """Get container background idle opacity percentage (65 to 100)."""
        return getattr(self, '_widget_opacity', 75)

    def set_widget_opacity(self, pct: int):
        """Set container background idle opacity (65% to 100%) and update stylesheet."""
        pct = max(65, min(100, int(pct)))
        self._widget_opacity = pct
        self._apply_style()
        self.state_changed.emit()

    def _apply_style(self):
        """Apply container background gradient stylesheet based on configured idle opacity."""
        pct = self.get_widget_opacity()
        if pct >= 100:
            idle_top = 1.0
            idle_bot = 1.0
            hover_top = 1.0
            hover_bot = 1.0
        else:
            base_alpha = pct / 100.0
            # Idle: Top slightly softer (-0.10), Bottom is base_alpha
            idle_top = max(0.40, base_alpha - 0.10)
            idle_bot = base_alpha
            # Hover: +10% boost for interactive glass highlight
            hover_top = min(1.0, base_alpha)
            hover_bot = min(1.0, base_alpha + 0.10)

        self.container.setStyleSheet(f"""
            QFrame#taskbarMediaContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(36, 38, 50, {idle_top:.2f}),
                    stop:1 rgba(16, 16, 24, {idle_bot:.2f}));
                border-radius: 8px;
                border: none;
            }}
            QFrame#taskbarMediaContainer:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(46, 48, 64, {hover_top:.2f}),
                    stop:1 rgba(22, 22, 32, {hover_bot:.2f}));
                border: none;
            }}
            QLabel#taskbarMediaTitle {{
                color: #f2f2f8;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: 700;
                background: transparent;
                padding-left: 2px;
            }}
            QLabel#taskbarMediaTitle:hover {{
                color: #FDA903;
            }}
            QLabel#taskbarMediaIcon {{
                background: transparent;
            }}
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 5px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: #383b41;
            }}
            QPushButton:pressed {{
                background: #464a52;
            }}
            QPushButton#taskbarMediaCloseBtn {{
                background: transparent;
            }}
            QPushButton#taskbarMediaCloseBtn:hover {{
                background: #383b41;
            }}
            QPushButton#taskbarMediaMinimizeBtn {{
                background: transparent;
                border-radius: 3px;
            }}
            QPushButton#taskbarMediaMinimizeBtn:hover {{
                background: rgba(255, 91, 6, 0.25);
            }}
            QPushButton#taskbarMediaMinimizeBtn:pressed {{
                background: rgba(255, 91, 6, 0.40);
            }}
        """)

    def nativeEvent(self, eventType, message):
        """Intercept native Windows messages to prevent click focus stealing and Z-order flicker."""
        if eventType == b"windows_generic_MSG":
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            # WM_MOUSEACTIVATE (0x0021) -> return MA_NOACTIVATE (3)
            if msg.message == 0x0021:
                return True, 3
            # WM_NCACTIVATE (0x0086) -> return True (1)
            elif msg.message == 0x0086:
                return True, 1
        return super().nativeEvent(eventType, message)

    def _init_win32_styles(self):
        """Apply WS_EX_TOPMOST and WS_EX_NOACTIVATE to guarantee topmost taskbar positioning with zero focus stealing."""
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            WS_EX_NOACTIVATE = 0x08000000
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_TOPMOST | WS_EX_NOACTIVATE) & ~0x00000080)
        except Exception as e:
            print(f"[TaskbarMediaWidget] Failed to apply WS_EX_NOACTIVATE: {e}")

    def _init_ui(self):
        """Construct the cyber-sleek UI following HELXAID styling rules."""
        self.setFixedHeight(34)
        self.setMinimumWidth(48)
        self.setMaximumWidth(380)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container Frame
        self.container = QFrame(self)
        self.container.setObjectName("taskbarMediaContainer")
        
        # UI Rule: Less border, more rich background-color + Orbitron font + Glassmorphism
        self._apply_style()

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(6, 2, 6, 2)
        container_layout.setSpacing(4)

        # Music Note Icon (Clickable & Draggable: Drag to move, Click: Expand if collapsed, open HELXAIC if expanded)
        self.lbl_note_icon = QLabel(self.container)
        self.lbl_note_icon.setObjectName("taskbarMediaIcon")
        self.lbl_note_icon.setCursor(QCursor(Qt.PointingHandCursor))
        self.lbl_note_icon.setPixmap(_render_svg_icon(SVG_MUSIC_NOTE, size=12, color="#FF5B06").pixmap(12, 12))
        self.lbl_note_icon.mousePressEvent = self._on_body_mouse_press
        self.lbl_note_icon.mouseMoveEvent = self._on_body_mouse_move
        self.lbl_note_icon.mouseReleaseEvent = self._on_body_mouse_release
        container_layout.addWidget(self.lbl_note_icon)

        # Track Title Label (Clickable & Draggable with animated Marquee scrolling)
        self.lbl_title = TaskbarMarqueeLabel("HELXAIC Music", self.container)
        container_layout.addWidget(self.lbl_title)

        # Enable free drag moving on container and title
        self._body_drag_active = False
        self._body_press_global = QPoint()
        self._body_widget_pos = QPoint()
        self._body_has_moved = False

        self.container.mousePressEvent = self._on_body_mouse_press
        self.container.mouseMoveEvent = self._on_body_mouse_move
        self.container.mouseReleaseEvent = self._on_body_mouse_release

        self.lbl_title.mousePressEvent = self._on_body_mouse_press
        self.lbl_title.mouseMoveEvent = self._on_body_mouse_move
        self.lbl_title.mouseReleaseEvent = self._on_body_mouse_release

        # Left Stretch (Symmetrically balances visualizer between Title and Prev button)
        container_layout.addStretch(1)

        # Animated Mini Spectrum Visualizer (Positioned in the middle)
        self.visualizer = MiniSpectrumVisualizer(self.container, bar_count=7)
        self.visualizer.mousePressEvent = self._on_body_mouse_press
        self.visualizer.mouseMoveEvent = self._on_body_mouse_move
        self.visualizer.mouseReleaseEvent = self._on_body_mouse_release
        container_layout.addWidget(self.visualizer)

        # Right Stretch (Symmetrically balances visualizer between Title and Prev button)
        container_layout.addStretch(1)

        # Prev Button
        self.btn_prev = QPushButton(self.container)
        self.btn_prev.setObjectName("taskbarMediaPrevBtn")
        self.btn_prev.setFixedSize(22, 22)
        self.btn_prev.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_prev.setIcon(_get_taskbar_icon("taskbar-previous-icon.png", SVG_PREV, size=12, color="#FDA903"))
        self.btn_prev.setIconSize(QSize(12, 12))
        self.btn_prev.setToolTip("Previous Track")
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        container_layout.addWidget(self.btn_prev)

        # Play/Pause Button
        self.btn_play = QPushButton(self.container)
        self.btn_play.setObjectName("taskbarMediaPlayBtn")
        self.btn_play.setFixedSize(24, 22)
        self.btn_play.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_play.setIcon(_get_taskbar_icon("taskbar-play-icon.png", SVG_PLAY, size=13, color="#FF5B06"))
        self.btn_play.setIconSize(QSize(13, 13))
        self.btn_play.setToolTip("Play / Pause")
        self.btn_play.clicked.connect(self.playpause_clicked.emit)
        container_layout.addWidget(self.btn_play)

        # Next Button
        self.btn_next = QPushButton(self.container)
        self.btn_next.setObjectName("taskbarMediaNextBtn")
        self.btn_next.setFixedSize(22, 22)
        self.btn_next.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_next.setIcon(_get_taskbar_icon("taskbar-next-icon.png", SVG_NEXT, size=12, color="#FDA903"))
        self.btn_next.setIconSize(QSize(12, 12))
        self.btn_next.setToolTip("Next Track")
        self.btn_next.clicked.connect(self.next_clicked.emit)
        container_layout.addWidget(self.btn_next)

        # Minimize / Grip Handle (Two Orange Lines)
        self.btn_minimize = TaskbarGripButton(self.container)
        self.btn_minimize.setFixedSize(14, 22)
        self.btn_minimize.setIcon(_render_svg_icon(SVG_MINIMIZE_GRIP, color="#FF5B06", w=10, h=17))
        self.btn_minimize.setIconSize(QSize(10, 17))
        self.btn_minimize.clicked.connect(self.toggle_collapse)
        self.btn_minimize.drag_started.connect(self._on_handle_drag_start)
        self.btn_minimize.dragged.connect(self._on_handle_drag)
        self.btn_minimize.drag_finished.connect(self._on_handle_drag_finished)
        container_layout.addWidget(self.btn_minimize)

        # Wire context menu to every single UI element inside widget
        for elem in [self, self.container, self.lbl_title, self.lbl_note_icon,
                     self.visualizer, self.btn_prev, self.btn_play, self.btn_next, self.btn_minimize]:
            elem.setContextMenuPolicy(Qt.CustomContextMenu)
            elem.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.container)

    def contextMenuEvent(self, event):
        """Standard Qt context menu trigger."""
        self.show_context_menu(event.globalPos())
        event.accept()

    def show_context_menu(self, pos=None):
        """Display cyber-sleek context menu with Lock Position, Preset Positions, Open HELXAIC, and Hide."""
        if isinstance(pos, QPoint):
            if pos.x() < 1200 and pos.y() < 1200 and self.rect().contains(pos):
                global_pos = self.mapToGlobal(pos)
            else:
                global_pos = pos
        else:
            global_pos = QCursor.pos()

        menu = QMenu(self)
        menu.setObjectName("taskbarMediaContextMenu")
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setStyleSheet("""
            QMenu#taskbarMediaContextMenu {
                background-color: #14151e;
                border: none;
                border-radius: 8px;
                padding: 4px;
                color: #f0f0f5;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu#taskbarMediaContextMenu::item {
                padding: 6px 18px 6px 8px;
                border-radius: 5px;
                border: none;
                background: transparent;
            }
            QMenu#taskbarMediaContextMenu::item:selected {
                background-color: #2b2d3a;
                color: #FDA903;
            }
            QMenu#taskbarMediaContextMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.08);
                margin: 3px 6px;
                border: none;
            }
        """)

        # 1. Lock / Unlock Position Action
        is_locked = getattr(self, '_is_locked', False)
        lock_text = "Unlock Position" if is_locked else "Lock Position"
        lock_icon = _get_ui_icon("pin-white.svg", fallback_svg=SVG_LOCK, size=14)
        act_lock = menu.addAction(lock_icon, lock_text)
        act_lock.triggered.connect(self.toggle_lock_position)

        menu.addSeparator()

        # 2. Position Presets Submenu
        dock_icon = _get_ui_icon("location-white.svg", fallback_svg=SVG_POSITION, size=13)
        pos_menu = menu.addMenu(dock_icon, "Dock Position")
        pos_menu.setObjectName("taskbarMediaContextMenu")
        pos_menu.setWindowFlags(pos_menu.windowFlags() | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        positions = [
            ("left", "Dock: Left (Near Start Button)"),
            ("center", "Dock: Center (Taskbar Center)"),
            ("right", "Dock: Right (Near System Tray)"),
            ("top_right", "Float: Top-Right Screen"),
            ("top_center", "Float: Top-Center Screen"),
        ]
        current_mode = self.get_position_mode()
        for key, label in positions:
            act = pos_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current_mode == key)
            act.triggered.connect(lambda chk=False, k=key: self.set_position_mode(k))

        menu.addSeparator()

        # 3. Widget Opacity Submenu (65% to 100%)
        opacity_icon = _get_ui_icon("opacity-white.svg", fallback_svg=SVG_OPACITY, size=13)
        opacity_menu = menu.addMenu(opacity_icon, "Widget Opacity")
        opacity_menu.setObjectName("taskbarMediaContextMenu")
        opacity_menu.setWindowFlags(opacity_menu.windowFlags() | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        opacity_options = [
            (65, "65% (Minimum)"),
            (70, "70%"),
            (75, "75% (Default)"),
            (80, "80%"),
            (85, "85%"),
            (90, "90%"),
            (95, "95%"),
            (100, "100% (Solid)"),
        ]
        curr_opacity = self.get_widget_opacity()
        for pct_val, label in opacity_options:
            act = opacity_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(curr_opacity == pct_val)
            act.triggered.connect(lambda chk=False, v=pct_val: self.set_widget_opacity(v))

        menu.addSeparator()

        # 4. Open HELXAIC Action
        open_icon = _get_ui_icon("open-white.svg", fallback_svg=SVG_OPEN_APP, size=13)
        act_open = menu.addAction(open_icon, "Open HELXAIC")
        act_open.triggered.connect(self.title_clicked.emit)

        # 5. Hide Widget Action
        hide_icon = _get_ui_icon("close-icon-white.svg", fallback_svg=SVG_CLOSE, size=12)
        act_hide = menu.addAction(hide_icon, "Hide Widget")
        act_hide.triggered.connect(self.close_clicked.emit)

        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else None
        menu_h = menu.sizeHint().height()

        widget_top_global = self.mapToGlobal(QPoint(0, 0)).y()
        if screen_geo and widget_top_global > screen_geo.height() // 2:
            popup_pos = QPoint(global_pos.x(), max(0, widget_top_global - menu_h - 4))
        else:
            popup_pos = QPoint(global_pos.x(), self.mapToGlobal(QPoint(0, self.height())).y() + 4)

        self._is_menu_active = True
        try:
            menu.exec(popup_pos)
        finally:
            self._is_menu_active = False

    def toggle_lock_position(self):
        """Toggle position locking to prevent accidental moving."""
        self._is_locked = not getattr(self, '_is_locked', False)
        self.state_changed.emit()

    def is_locked(self) -> bool:
        """Check if widget position is locked."""
        return getattr(self, '_is_locked', False)

    def set_locked(self, locked: bool):
        """Set position locked state."""
        self._is_locked = bool(locked)

    def _on_body_mouse_press(self, event):
        if event.button() == Qt.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        elif event.button() == Qt.LeftButton:
            self._body_drag_active = True
            self._body_has_moved = False
            self._body_press_global = event.globalPosition().toPoint()
            self._body_widget_pos = self.pos()
            event.accept()
            return
        event.ignore()

    def _on_body_mouse_move(self, event):
        if getattr(self, '_body_drag_active', False):
            if getattr(self, '_is_locked', False):
                return
            cur_global = event.globalPosition().toPoint()
            delta = cur_global - self._body_press_global
            if abs(delta.x()) >= 3 or abs(delta.y()) >= 3:
                self._body_has_moved = True
            if self._body_has_moved:
                new_pos = self._body_widget_pos + delta
                
                # Smoothly clamp to screen boundaries without fighting with timer
                screen = QApplication.primaryScreen()
                if screen:
                    sg = screen.geometry()
                    w = self.width()
                    h = self.height()
                    clamped_x = max(sg.left(), min(sg.right() - w, new_pos.x()))
                    clamped_y = max(sg.top(), min(sg.bottom() - h, new_pos.y()))
                    new_pos = QPoint(clamped_x, clamped_y)

                self._position_mode = "custom"
                self._custom_pos = [new_pos.x(), new_pos.y()]
                self.move(new_pos)
                try:
                    hwnd = int(self.winId())
                    user32.SetWindowPos(hwnd, -1, new_pos.x(), new_pos.y(), self.width(), self.height(), 0x0010 | 0x0040)
                except Exception:
                    pass
            event.accept()
            return
        event.ignore()

    def _on_body_mouse_release(self, event):
        if getattr(self, '_body_drag_active', False) and event.button() == Qt.LeftButton:
            self._body_drag_active = False
            if self._body_has_moved:
                screen = QApplication.primaryScreen()
                x, y = self.x(), self.y()
                if screen:
                    sg = screen.geometry()
                    w = self.width()
                    h = self.height()
                    x = max(sg.left(), min(sg.right() - w, x))
                    y = max(sg.top(), min(sg.bottom() - h, y))
                self._custom_pos = [x, y]
                self._position_mode = "custom"
                self.state_changed.emit()
            else:
                if self._is_collapsed:
                    self.expand(animate=True)
                else:
                    self.title_clicked.emit()
            event.accept()
            return
        event.ignore()

    def _on_note_clicked(self):
        if self._is_collapsed:
            self.expand(animate=True)
        else:
            self.title_clicked.emit()

    def toggle_collapse(self):
        """Toggle between collapsed (icon only) and expanded modes."""
        if self._is_collapsed:
            self.expand(animate=True)
        else:
            self.collapse(animate=True)

    def collapse(self, animate: bool = True):
        """Collapse widget into compact mode showing only the music icon and minimize grip."""
        self._is_collapsed = True
        self.lbl_title.hide()
        self.visualizer.hide()
        self.btn_prev.hide()
        self.btn_play.hide()
        self.btn_next.hide()
        self.btn_minimize.setToolTip("Expand Widget (Click or drag right)")

        if animate:
            self._animate_width(self._collapsed_width)
        else:
            self.setFixedWidth(self._collapsed_width)
            self.sync_position()
        self.state_changed.emit()

    def expand(self, animate: bool = True):
        """Expand widget to show full title and playback controls."""
        self._is_collapsed = False
        self.lbl_title.show()
        self.visualizer.show()
        self.btn_prev.show()
        self.btn_play.show()
        self.btn_next.show()
        self.btn_minimize.setToolTip("Minimize / Collapse (Click or drag left)")

        target_w = max(200, min(380, getattr(self, '_expanded_width', 240)))
        if animate:
            self._animate_width(target_w)
        else:
            self.setFixedWidth(target_w)
            self.sync_position()
        self.state_changed.emit()

    def _animate_width(self, target_w: int):
        """Smoothly animate widget width transition using QEasingCurve."""
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        if hasattr(self, '_width_anim') and self._width_anim.state() == QVariantAnimation.Running:
            self._width_anim.stop()

        self._is_animating = True
        start_w = self.width()

        self._width_anim = QVariantAnimation(self)
        self._width_anim.setDuration(220)
        self._width_anim.setStartValue(start_w)
        self._width_anim.setEndValue(target_w)
        self._width_anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_val(v):
            w_int = int(v)
            self.setFixedWidth(w_int)
            self._update_title_elide()
            self.sync_position()

        def _on_done():
            self._is_animating = False
            self.setFixedWidth(target_w)
            self._update_title_elide()
            self.sync_position()

        self._width_anim.valueChanged.connect(_on_val)
        self._width_anim.finished.connect(_on_done)
        self._width_anim.start()

    def _on_handle_drag_start(self, initial_x: int):
        """Track initial width before drag starts."""
        self._is_dragging = True
        self._drag_initial_w = self.width() if not self._is_collapsed else self._collapsed_width

    def _on_handle_drag(self, total_delta_x: int):
        """Handle dynamic dragging to resize widget horizontally."""
        self._is_dragging = True
        mode = getattr(self, '_position_mode', 'left')
        eff_delta = -total_delta_x if mode == 'right' else total_delta_x
        target_w = getattr(self, '_drag_initial_w', self.width()) + eff_delta

        # Snap to collapse when dragged to <= 170px
        if target_w <= 170:
            if not self._is_collapsed:
                self._is_collapsed = True
                self.lbl_title.hide()
                self.visualizer.hide()
                self.btn_prev.hide()
                self.btn_play.hide()
                self.btn_next.hide()
                self.btn_minimize.setToolTip("Expand Widget (Click or drag right)")
            self.setFixedWidth(self._collapsed_width)
        else:
            if self._is_collapsed:
                self._is_collapsed = False
                self.lbl_title.show()
                self.visualizer.show()
                self.btn_prev.show()
                self.btn_play.show()
                self.btn_next.show()
                self.btn_minimize.setToolTip("Minimize / Collapse (Click or drag left)")
            target_w = min(380, max(180, target_w))
            self._expanded_width = target_w
            self.setFixedWidth(target_w)
            self._update_title_elide()

        self.sync_position()

    def _on_handle_drag_finished(self):
        self._is_dragging = False
        if self._is_collapsed:
            self.collapse(animate=False)
        else:
            self.expand(animate=False)
        self.state_changed.emit()

    def _init_timer(self):
        """Setup position synchronization timer."""
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self.sync_position)
        self._pos_timer.start(200)

    def set_playback_state(self, is_playing: bool):
        """Update Play/Pause icon, audio visualizer, and marquee scrolling based on playback state."""
        self._is_playing = is_playing
        if hasattr(self, 'visualizer') and self.visualizer:
            if getattr(self, '_visualizer_suppressed', False):
                if hasattr(self.visualizer, 'set_suppressed'):
                    self.visualizer.set_suppressed(True, animate=True)
                else:
                    self.visualizer.set_active(False)
                    self.visualizer.hide()
            elif not getattr(self, '_is_collapsed', False):
                if hasattr(self.visualizer, 'set_suppressed'):
                    self.visualizer.set_suppressed(False, animate=True)
                else:
                    self.visualizer.show()
                self.visualizer.set_active(is_playing)
            else:
                self.visualizer.set_active(is_playing)
        if hasattr(self, 'lbl_title') and hasattr(self.lbl_title, 'set_playback_state'):
            self.lbl_title.set_playback_state(is_playing)
        if is_playing:
            self.btn_play.setIcon(_get_taskbar_icon("taskbar-pause-icon.png", SVG_PAUSE, size=13, color="#FF5B06"))
            self.btn_play.setToolTip("Pause")
        else:
            self.btn_play.setIcon(_get_taskbar_icon("taskbar-play-icon.png", SVG_PLAY, size=13, color="#FF5B06"))
            self.btn_play.setToolTip("Play")

    def set_visualizer_suppressed(self, suppressed: bool, animate: bool = True):
        """Suppress mini visualizer when HELXAIC page is active with main visualizer."""
        self._visualizer_suppressed = bool(suppressed)
        if hasattr(self, 'visualizer') and self.visualizer:
            if hasattr(self.visualizer, 'set_suppressed'):
                self.visualizer.set_suppressed(self._visualizer_suppressed, animate=animate)
                if not self._visualizer_suppressed:
                    self.visualizer.set_active(getattr(self, '_is_playing', False))
            else:
                if self._visualizer_suppressed:
                    self.visualizer.set_active(False)
                    self.visualizer.hide()
                elif not getattr(self, '_is_collapsed', False):
                    self.visualizer.show()
                    self.visualizer.set_active(getattr(self, '_is_playing', False))

    def _update_title_elide(self):
        """Update marquee scroll bounds dynamically based on current widget width."""
        if hasattr(self, 'lbl_title') and hasattr(self.lbl_title, '_check_scroll_needed'):
            self.lbl_title._check_scroll_needed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_title_elide()

    def set_track_info(self, title: str, artist: str = ""):
        """Update displayed track title and artist with marquee animation."""
        clean_title = (title or "HELXAIC Music").strip()
        if artist and artist.strip():
            clean_title = f"{clean_title} - {artist.strip()}"
        
        self._full_title = clean_title
        self._artist = artist or ""
        if hasattr(self, 'lbl_title') and hasattr(self.lbl_title, 'set_full_text'):
            self.lbl_title.set_full_text(self._full_title)
            self.lbl_title.setToolTip(f"Now Playing: {self._full_title}\nClick to open HELXAIC")
        self.sync_position()

    def set_position_mode(self, mode: str):
        """Set docking position mode: 'left', 'right', 'center', 'top_right', 'top_center'."""
        self._position_mode = mode
        self.sync_position()

    def get_position_mode(self) -> str:
        """Get current position mode."""
        return getattr(self, '_position_mode', 'left')

    def showEvent(self, event):
        super().showEvent(event)
        self._update_title_elide()
        self.sync_position()
        self.raise_()

    def sync_position(self):
        """Calculate and dock position based on selected position mode."""
        if getattr(self, '_is_menu_active', False) or getattr(self, '_body_drag_active', False) or getattr(self, '_is_dragging', False):
            return

        screen = QApplication.primaryScreen()
        if not screen:
            return

        sg = screen.geometry()
        ag = screen.availableGeometry()

        # Taskbar bounds from screen geometry
        tb_x = sg.x()
        tb_w = sg.width()
        tb_y = ag.bottom()
        tb_h = max(38, sg.bottom() - ag.bottom())

        if getattr(self, '_is_animating', False) or getattr(self, '_is_dragging', False):
            w = self.width()
        elif getattr(self, '_is_collapsed', False):
            w = self._collapsed_width
        else:
            w = max(190, min(380, getattr(self, '_expanded_width', 240)))

        h = min(34, max(28, tb_h - 10))
        mode = getattr(self, '_position_mode', 'left')

        if mode == "custom" and hasattr(self, '_custom_pos') and self._custom_pos:
            x = self._custom_pos[0]
            y = self._custom_pos[1]
            x = max(sg.left(), min(sg.right() - w, x))
            y = max(sg.top(), min(sg.bottom() - h, y))
        elif mode == "center":
            x = tb_x + (tb_w - w) // 2
            y = tb_y + (tb_h - h) // 2
        elif mode == "left":
            x = tb_x + 55  # Offset next to Start / Widgets
            y = tb_y + (tb_h - h) // 2
        elif mode == "top_right":
            x = sg.right() - w - 20
            y = sg.top() + 20
        elif mode == "top_center":
            x = sg.left() + (sg.width() - w) // 2
            y = sg.top() + 15
        else:  # "right" - default adjacent to Tray
            x = max(tb_x + 20, tb_x + tb_w - w - 230)
            y = tb_y + (tb_h - h) // 2

        self.setGeometry(x, y, w, h)
        
        # Enforce topmost z-order directly over the taskbar without stealing focus
        try:
            hwnd = int(self.winId())
            HWND_TOPMOST = -1
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
            self.raise_()
        except Exception:
            pass
