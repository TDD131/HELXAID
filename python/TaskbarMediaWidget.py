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
import ctypes
from ctypes import windll, Structure, byref, c_long
from ctypes.wintypes import HWND, RECT, DWORD

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame,
    QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPoint
from PySide6.QtGui import QFont, QColor, QPainter, QIcon, QPixmap, QCursor
from PySide6.QtSvg import QSvgRenderer

user32 = windll.user32


class RECT_STRUCT(Structure):
    _fields_ = [
        ("left", c_long),
        ("top", c_long),
        ("right", c_long),
        ("bottom", c_long),
    ]


def _render_svg_icon(svg_xml: str, size: int = 14, color: str = "#FF5B06") -> QIcon:
    """Helper to render vector SVG XML into crisp QIcon."""
    formatted_svg = svg_xml.replace('currentColor', color)
    renderer = QSvgRenderer(bytearray(formatted_svg, encoding='utf-8'))
    pixmap = QPixmap(size * 2, size * 2)
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


# Clean vector SVG definitions (Used for note, close, and fallback)
SVG_PREV = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>"""
SVG_PLAY = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>"""
SVG_PAUSE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>"""
SVG_NEXT = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>"""
SVG_MUSIC_NOTE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>"""
SVG_CLOSE = """<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>"""


class TaskbarMediaWidget(QWidget):
    """
    Taskbar Media Widget for HELXAIC.
    Docks seamlessly to the Windows Taskbar with zero-focus stealing.
    
    Component Name: taskbarMediaWidget
    """
    prev_clicked = Signal()
    playpause_clicked = Signal()
    next_clicked = Signal()
    title_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setObjectName("taskbarMediaWidget")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._is_playing = False
        self._full_title = "HELXAIC Ready"
        self._artist = ""

        self._init_win32_styles()
        self._init_ui()
        self._init_timer()

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
        self.setMinimumWidth(220)
        self.setMaximumWidth(380)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container Frame
        self.container = QFrame(self)
        self.container.setObjectName("taskbarMediaContainer")
        
        # UI Rule: Less border, more rich background-color + Orbitron font + Glassmorphism
        self.container.setStyleSheet("""
            QFrame#taskbarMediaContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(36, 38, 50, 0.65),
                    stop:1 rgba(16, 16, 24, 0.75));
                border-radius: 8px;
                border: none;
            }
            QFrame#taskbarMediaContainer:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(46, 48, 64, 0.75),
                    stop:1 rgba(22, 22, 32, 0.85));
                border: none;
            }
            QLabel#taskbarMediaTitle {
                color: #f2f2f8;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: 700;
                background: transparent;
                padding-left: 2px;
            }
            QLabel#taskbarMediaTitle:hover {
                color: #FDA903;
            }
            QLabel#taskbarMediaIcon {
                background: transparent;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 5px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #383b41;
            }
            QPushButton:pressed {
                background: #464a52;
            }
            QPushButton#taskbarMediaCloseBtn {
                background: transparent;
            }
            QPushButton#taskbarMediaCloseBtn:hover {
                background: #383b41;
            }
        """)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(7, 2, 7, 2)
        container_layout.setSpacing(4)

        # Music Note Icon
        self.lbl_note_icon = QLabel(self.container)
        self.lbl_note_icon.setObjectName("taskbarMediaIcon")
        self.lbl_note_icon.setPixmap(_render_svg_icon(SVG_MUSIC_NOTE, size=12, color="#FF5B06").pixmap(12, 12))
        container_layout.addWidget(self.lbl_note_icon)

        # Track Title Label (Clickable)
        self.lbl_title = QLabel("HELXAIC Music", self.container)
        self.lbl_title.setObjectName("taskbarMediaTitle")
        self.lbl_title.setCursor(QCursor(Qt.PointingHandCursor))
        self.lbl_title.mousePressEvent = lambda ev: self.title_clicked.emit()
        container_layout.addWidget(self.lbl_title, 1)

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

        # Subtle Close / Hide Button
        self.btn_close = QPushButton(self.container)
        self.btn_close.setObjectName("taskbarMediaCloseBtn")
        self.btn_close.setFixedSize(16, 16)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setIcon(_render_svg_icon(SVG_CLOSE, size=9, color="#888888"))
        self.btn_close.setIconSize(QSize(9, 9))
        self.btn_close.setToolTip("Hide Taskbar Widget")
        self.btn_close.clicked.connect(self.close_clicked.emit)
        container_layout.addWidget(self.btn_close)

        main_layout.addWidget(self.container)

    def _init_timer(self):
        """Setup position synchronization timer."""
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self.sync_position)
        self._pos_timer.start(200)

    def set_playback_state(self, is_playing: bool):
        """Update Play/Pause icon based on playback state."""
        self._is_playing = is_playing
        if is_playing:
            self.btn_play.setIcon(_get_taskbar_icon("taskbar-pause-icon.png", SVG_PAUSE, size=13, color="#FF5B06"))
            self.btn_play.setToolTip("Pause")
        else:
            self.btn_play.setIcon(_get_taskbar_icon("taskbar-play-icon.png", SVG_PLAY, size=13, color="#FF5B06"))
            self.btn_play.setToolTip("Play")

    def set_track_info(self, title: str, artist: str = ""):
        """Update displayed track title and artist."""
        clean_title = (title or "HELXAIC Music").strip()
        if artist and artist.strip():
            clean_title = f"{clean_title} - {artist.strip()}"
        
        self._full_title = clean_title
        self._artist = artist or ""
        
        # Elide text to fit compactly
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.lbl_title.font())
        elided = fm.elidedText(self._full_title, Qt.ElideRight, 120)
        self.lbl_title.setText(elided)
        self.lbl_title.setToolTip(f"Now Playing: {self._full_title}\nClick to open HELXAIC")
        
        self.adjustSize()
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
        self.sync_position()
        self.raise_()

    def sync_position(self):
        """Calculate and dock position based on selected position mode."""
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

        w = max(220, min(380, self.sizeHint().width()))
        h = min(34, max(28, tb_h - 10))
        mode = getattr(self, '_position_mode', 'left')

        if mode == "center":
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
