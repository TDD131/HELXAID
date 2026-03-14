"""
VLC-Style Video Player Widget

A sleek video player with split top/bottom overlay bars that auto-hide.
The center of the video remains uncovered for hardware-accelerated rendering.
Used in the Music Panel for playing music videos.

Component Name: VideoPlayerWidget
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QGraphicsOpacityEffect, QSizePolicy,
    QSpacerItem, QComboBox, QApplication
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, QPoint, QUrl, QRect
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPalette, QCursor,
    QPainter, QBrush, QLinearGradient, QFontMetrics
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import os
import re
import bisect
import time
from typing import Optional


class _SubtitleRenderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._style_preset = "outline"

        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        self.setFont(f)
        self.setVisible(False)

    def setText(self, text: str):
        self._text = text or ""
        self.update()

    def text(self) -> str:
        return self._text

    def clear(self):
        self._text = ""
        self.setVisible(False)
        self.update()

    def set_font_point_size(self, pt: int):
        try:
            v = int(pt)
        except Exception:
            return
        if v < 6:
            v = 6
        f = self.font()
        f.setPointSize(v)
        self.setFont(f)
        self.update()

    def get_font_point_size(self) -> int:
        try:
            return int(self.font().pointSize())
        except Exception:
            return 16

    def set_font_variant(self, bold: bool, italic: bool):
        try:
            b = bool(bold)
            i = bool(italic)
        except Exception:
            b = False
            i = False
        f = self.font()
        try:
            f.setBold(b)
        except Exception:
            pass
        try:
            f.setItalic(i)
        except Exception:
            pass
        self.setFont(f)
        self.update()

    def get_font_variant(self):
        try:
            f = self.font()
            return bool(f.bold()), bool(f.italic())
        except Exception:
            return False, False

    def set_style_preset(self, preset: str):
        p = (preset or "").strip().lower()
        if p not in ("outline", "shadow", "box"):
            p = "outline"
        self._style_preset = p
        self.update()

    def get_style_preset(self) -> str:
        return self._style_preset

    def paintEvent(self, event):
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        preset = self._style_preset
        draw_box = preset == "box"
        draw_shadow = preset == "shadow"
        draw_outline = preset == "outline"

        text_flags = Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap

        if draw_box:
            pad_x = 16
            pad_y = 10
            max_w = max(1, rect.width() - (pad_x * 2))
            fm = QFontMetrics(self.font())
            text_br = fm.boundingRect(QRect(0, 0, max_w, 10000), text_flags, self._text)
            if text_br.width() <= 0 or text_br.height() <= 0:
                text_br = QRect(0, 0, max_w, max(1, fm.height()))

            box_w = min(rect.width(), text_br.width() + (pad_x * 2))
            box_h = min(rect.height(), text_br.height() + (pad_y * 2))
            box = QRect(0, 0, box_w, box_h)
            box.moveCenter(rect.center())
            box = box.intersected(rect)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.drawRoundedRect(box, 10, 10)

        if draw_shadow:
            painter.setPen(QColor(0, 0, 0, 180))
            painter.drawText(rect.translated(2, 2), text_flags, self._text)

        if draw_outline:
            painter.setPen(QColor(0, 0, 0, 255))
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (-2, 2), (2, -2), (2, 2)]:
                painter.drawText(rect.translated(dx, dy), text_flags, self._text)

        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(rect, text_flags, self._text)


class _SubtitleOverlayWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.label_top = _SubtitleRenderWidget(self)
        self.label_bottom = _SubtitleRenderWidget(self)

        self.label_top.setGeometry(0, 0, 0, 0)
        self.label_bottom.setGeometry(0, 0, 0, 0)

        # Backwards compatibility: existing code expects `.label`.
        self.label = self.label_bottom


class VideoTopBar(QFrame):
    """
    Top overlay bar for video player.
    Contains back button, title, aspect ratio dropdown, and fullscreen button.
    Positioned at the very top of the video area so the center remains uncovered,
    allowing Qt/Windows to hardware-accelerate video rendering.

    Component Name: VideoTopBar
    """

    fullscreenClicked = Signal()
    backClicked = Signal()
    aspectRatioChanged = Signal(str)  # "fill", "fit", or "stretch"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("videoTopBar")
        self.setFixedHeight(50)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "UI Icons")

        top_layout = QHBoxLayout(self)
        top_layout.setContentsMargins(15, 10, 15, 10)

        # Back button
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("overlayBtn")
        self.back_btn.setFixedSize(36, 36)
        self.back_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.back_btn.setToolTip("Back to Playlist")
        self.back_btn.clicked.connect(self.backClicked.emit)
        self.back_btn.setText("\u2190")
        top_layout.addWidget(self.back_btn)

        # Title label
        self.title_label = QLabel("Now Playing")
        self.title_label.setObjectName("videoTitle")
        top_layout.addWidget(self.title_label, stretch=1)

        # Aspect ratio dropdown
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.setObjectName("aspectRatioCombo")
        self.aspect_ratio_combo.addItems(["Fill", "Fit", "Stretch"])
        self.aspect_ratio_combo.setCurrentText("Fit")
        self.aspect_ratio_combo.setFixedWidth(100)
        self.aspect_ratio_combo.setFixedHeight(30)
        self.aspect_ratio_combo.setToolTip("Video Aspect Ratio")
        self.aspect_ratio_combo.setCursor(QCursor(Qt.PointingHandCursor))
        # Inline styling to ensure visibility above video
        self.aspect_ratio_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 4px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox:hover {
                background: rgba(255, 91, 6, 0.4);
                border-color: #FF5B06;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 0.95);
                border: 1px solid #FF5B06;
                color: #ffffff;
                selection-background-color: #FF5B06;
            }
        """)
        self.aspect_ratio_combo.currentTextChanged.connect(
            lambda text: self.aspectRatioChanged.emit(text.lower())
        )
        top_layout.addWidget(self.aspect_ratio_combo)

        # Fullscreen button
        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setObjectName("overlayBtn")
        self.fullscreen_btn.setFixedSize(36, 36)
        self.fullscreen_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.fullscreen_btn.setToolTip("Fullscreen")
        self.fullscreen_btn.clicked.connect(self.fullscreenClicked.emit)
        self.fullscreen_btn.setText("\u26F6")
        top_layout.addWidget(self.fullscreen_btn)

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#videoTopBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0.7),
                    stop:1 transparent);
            }

            QPushButton#overlayBtn {
                background: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 18px;
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton#overlayBtn:hover {
                background: rgba(255, 91, 6, 0.5);
            }

            QLabel#videoTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                padding-left: 15px;
            }

            QComboBox#aspectRatioCombo {
                background: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox#aspectRatioCombo:hover {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
            }
            QComboBox#aspectRatioCombo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#aspectRatioCombo::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #ffffff;
                width: 0;
                height: 0;
            }
            QComboBox#aspectRatioCombo QAbstractItemView {
                background: rgba(30, 30, 30, 0.95);
                border: 1px solid #FF5B06;
                color: #ffffff;
                selection-background-color: #FF5B06;
                selection-color: #ffffff;
            }
        """)

    def set_title(self, title: str):
        self.title_label.setText(title)


class VideoBottomBar(QFrame):
    """
    Bottom overlay bar for video player.
    Contains timeline slider, time labels, play/pause button, and volume controls.
    Positioned at the very bottom of the video area so the center remains uncovered,
    allowing Qt/Windows to hardware-accelerate video rendering.

    Component Name: VideoBottomBar
    """

    playClicked = Signal()
    seekChanged = Signal(float)
    volumeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("videoBottomBar")
        self.setFixedHeight(80)
        self._is_playing = False
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "UI Icons")

        bottom_layout = QVBoxLayout(self)
        bottom_layout.setContentsMargins(20, 10, 20, 15)
        bottom_layout.setSpacing(10)

        # Timeline row
        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(12)

        self.time_current = QLabel("0:00")
        self.time_current.setObjectName("timeLabel")
        self.time_current.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setObjectName("videoTimeline")
        self.timeline.setRange(0, 1000)
        self.timeline.sliderMoved.connect(lambda v: self.seekChanged.emit(v / 1000.0))

        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("timeLabel")
        # Don't use right-alignment - it causes clipping of leading digits when narrow
        self.time_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.time_total.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        try:
            # Force a very wide minimum to prevent any possible clipping
            fm = QFontMetrics(self.time_total.font())
            sample = "88:88:88"
            min_w = int(fm.horizontalAdvance(sample) + 64)
            if min_w < 200:
                min_w = 200
            self.time_current.setMinimumWidth(min_w)
            self.time_total.setMinimumWidth(min_w)
        except Exception:
            self.time_current.setMinimumWidth(200)
            self.time_total.setMinimumWidth(200)

        timeline_row.addWidget(self.time_current)
        timeline_row.addWidget(self.timeline, stretch=1)
        timeline_row.addWidget(self.time_total)

        bottom_layout.addLayout(timeline_row)

        # Controls row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(15)

        # Play/Pause button (large, center)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("playBtnLarge")
        self.play_btn.setFixedSize(50, 50)
        self.play_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.play_btn.clicked.connect(self.playClicked.emit)

        icon_path = os.path.join(icons_dir, "play-button-icon.png")
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
            self.play_btn.setIconSize(QSize(28, 28))
        else:
            self.play_btn.setText(">")

        controls_row.addStretch()
        controls_row.addWidget(self.play_btn)
        controls_row.addStretch()

        # Volume on the right
        volume_section = QHBoxLayout()
        volume_section.setSpacing(8)

        self.volume_icon = QLabel("")
        self.volume_icon.setObjectName("volumeIconVideo")

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("volumeSliderVideo")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.volumeChanged.emit)

        volume_section.addWidget(self.volume_icon)
        volume_section.addWidget(self.volume_slider)

        controls_row.addLayout(volume_section)

        bottom_layout.addLayout(controls_row)

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#videoBottomBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 transparent,
                    stop:1 rgba(0, 0, 0, 0.85));
            }

            QLabel#timeLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 12px;
                qproperty-alignment: AlignLeft | AlignVCenter;
            }

            QSlider#videoTimeline::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 5px;
                border-radius: 2px;
            }
            QSlider#videoTimeline::handle:horizontal {
                background: #FF5B06;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider#videoTimeline::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 2px;
            }

            QPushButton#playBtnLarge {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FF5B06, stop:1 #FDA903);
                border: none;
                border-radius: 25px;
            }
            QPushButton#playBtnLarge:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FF7525, stop:1 #FFC030);
            }

            QLabel#volumeIconVideo {
                color: rgba(255, 255, 255, 0.8);
                font-size: 16px;
            }

            QSlider#volumeSliderVideo::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider#volumeSliderVideo::handle:horizontal {
                background: #ffffff;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider#volumeSliderVideo::sub-page:horizontal {
                background: rgba(255, 255, 255, 0.6);
                border-radius: 2px;
            }
        """)

    def set_playing(self, playing: bool):
        self._is_playing = playing
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_name = "pause-button-icon.png" if playing else "play-button-icon.png"
        icon_path = os.path.join(script_dir, "UI Icons", icon_name)
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
        else:
            self.play_btn.setText("||" if playing else ">")

    def set_position(self, current: float, total: float):
        if total > 0:
            try:
                v = int((current / total) * 1000)
            except Exception:
                v = 0

            try:
                if self.timeline.value() != v:
                    self.timeline.blockSignals(True)
                    self.timeline.setValue(v)
                    self.timeline.blockSignals(False)
            except Exception:
                try:
                    self.timeline.blockSignals(True)
                    self.timeline.setValue(v)
                    self.timeline.blockSignals(False)
                except Exception:
                    pass

        try:
            cur_txt = self._format_time(current)
            if self.time_current.text() != cur_txt:
                self.time_current.setText(cur_txt)
        except Exception:
            pass

        try:
            # QMediaPlayer can report duration as 0/-1 while metadata loads.
            # Avoid displaying negative or bogus times.
            if total <= 0:
                tot_txt = "--:--"
            else:
                tot_txt = self._format_time(total)
            if self.time_total.text() != tot_txt:
                self.time_total.setText(tot_txt)
        except Exception:
            pass

    def _format_time(self, seconds: float) -> str:
        try:
            s = float(seconds)
        except Exception:
            return "--:--"

        if s != s:
            return "--:--"
        if s < 0:
            s = 0.0

        total = int(s)
        hh = total // 3600
        mm = (total % 3600) // 60
        ss = total % 60

        if hh > 0:
            return f"{hh}:{mm:02d}:{ss:02d}"
        return f"{mm}:{ss:02d}"


class VideoPlayerWidget(QWidget):
    """
    VLC-style Video Player with auto-hiding split overlay controls.
    Uses separate top bar and bottom bar overlays instead of a single full-screen
    overlay. This leaves the center of the video uncovered, allowing the OS to
    hardware-accelerate video rendering without software compositing overhead.

    Component Name: VideoPlayerWidget
    """

    # Signals
    backRequested = Signal()
    fullscreenToggled = Signal(bool)  # True = entering fullscreen, False = exiting

    def __init__(self, player: QMediaPlayer = None, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoPlayerWidget")

        # Use provided player or create new one
        if player:
            self._player = player
            self._own_player = False
        else:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._player.setAudioOutput(self._audio_output)
            self._own_player = True

        # State
        self._controls_visible = True
        self._is_fullscreen = False

        self._subtitle_cues = []
        self._subtitle_idx = -1
        self._subtitle_path = None
        self._subtitle_last_error = None
        self._subtitle_start_times = []

        self._subtitle_geom_cache = {
            'top': {'text': None, 'font_pt': None, 'w': None, 'h': 72},
            'bottom': {'text': None, 'font_pt': None, 'w': None, 'h': 72},
        }

        self._last_position_ui_update_t = 0.0
        self._position_ui_update_interval_s = 0.12

        self._render_suspended = False

        # Hide timer
        self._hide_timer = QTimer()
        self._hide_timer.timeout.connect(self._hide_controls)
        self._hide_timer.setSingleShot(True)

        self._setup_ui()
        self._connect_signals()

        # Start with controls visible
        self._show_controls()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display
        self.video_widget = QVideoWidget()
        self.video_widget.setObjectName("videoDisplay")

        # Only set video output if we own the player
        # If shared player, caller should set video output when switching views
        if self._own_player:
            self._player.setVideoOutput(self.video_widget)

        layout.addWidget(self.video_widget)

        self._subtitle_overlay = _SubtitleOverlayWindow()
        self.subtitle_label_top = self._subtitle_overlay.label_top
        self.subtitle_label_bottom = self._subtitle_overlay.label_bottom
        self.subtitle_label = self.subtitle_label_bottom
        self._subtitle_overlay_visible = False
        self._subtitle_overlay_timer = QTimer(self)
        self._subtitle_overlay_timer.setInterval(500)
        self._subtitle_overlay_timer.timeout.connect(self._update_subtitle_overlay_geometry)
        try:
            QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)
        except Exception:
            pass

        # Split overlay bars (positioned absolutely over video edges only).
        # The center of the video stays uncovered so Qt can hardware-accelerate
        # the video surface without needing to software-blend a transparent overlay.
        self.top_bar = VideoTopBar(self)
        self.bottom_bar = VideoBottomBar(self)

        # Styling
        self.setStyleSheet("""
            QWidget#VideoPlayerWidget {
                background: #000000;
            }
            QVideoWidget#videoDisplay {
                background: #000000;
            }
        """)

        # Enable mouse tracking for auto-hide
        self.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)

    def _connect_signals(self):
        # Top bar signals
        self.top_bar.fullscreenClicked.connect(self._toggle_fullscreen)
        self.top_bar.backClicked.connect(self.backRequested.emit)
        self.top_bar.aspectRatioChanged.connect(self._set_aspect_ratio)

        # Bottom bar signals
        self.bottom_bar.playClicked.connect(self._toggle_play)
        self.bottom_bar.seekChanged.connect(self._seek)
        self.bottom_bar.volumeChanged.connect(self._set_volume)

        # Player signals
        self._player.positionChanged.connect(self._on_position)
        self._player.playbackStateChanged.connect(self._on_state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position bars at top and bottom edges only.
        # The center of the video remains completely uncovered for HW rendering.
        self.top_bar.setGeometry(0, 0, self.width(), 50)
        self.bottom_bar.setGeometry(0, self.height() - 80, self.width(), 80)

        margin = 18
        self._update_subtitle_overlay_geometry(margin)
        self.top_bar.raise_()
        self.bottom_bar.raise_()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._update_subtitle_overlay_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            if not self._render_suspended:
                self._subtitle_overlay.show()
                self._subtitle_overlay_timer.start()
        except Exception:
            pass
        self._update_subtitle_overlay_geometry()

    def hideEvent(self, event):
        try:
            self._subtitle_overlay.hide()
            self._subtitle_overlay_timer.stop()
        except Exception:
            pass
        super().hideEvent(event)

    def set_render_suspended(self, suspended: bool):
        try:
            self._render_suspended = bool(suspended)
        except Exception:
            self._render_suspended = True

        if self._render_suspended:
            try:
                self._subtitle_overlay_timer.stop()
            except Exception:
                pass
            try:
                self.subtitle_label_bottom.clear()
                self.subtitle_label_top.clear()
            except Exception:
                pass
            try:
                self._subtitle_overlay.hide()
            except Exception:
                pass
            try:
                self._subtitle_overlay_visible = False
            except Exception:
                pass
            return

        try:
            if self.isVisible():
                self._subtitle_overlay.show()
                self._subtitle_overlay_timer.start()
        except Exception:
            pass
        try:
            self._update_subtitle_overlay_geometry()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self._subtitle_overlay.close()
            self._subtitle_overlay_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_app_state_changed(self, state):
        self._update_subtitle_overlay_geometry()

    def set_subtitle_style_preset(self, preset: str):
        try:
            self.subtitle_label_bottom.set_style_preset(preset)
            self.subtitle_label_top.set_style_preset(preset)
        except Exception:
            pass

    def get_subtitle_style_preset(self) -> str:
        try:
            return self.subtitle_label_bottom.get_style_preset()
        except Exception:
            return "outline"

    def _update_subtitle_overlay_geometry(self, margin: int = 18):
        try:
            if not hasattr(self, '_subtitle_overlay') or not self._subtitle_overlay:
                return
            if not self.isVisible() or not self.video_widget.isVisible():
                self._subtitle_overlay.hide()
                self._subtitle_overlay_visible = False
                return

            mw = self.window()
            if mw and mw.isMinimized():
                self._subtitle_overlay.hide()
                self._subtitle_overlay_visible = False
                return

            if QApplication.applicationState() != Qt.ApplicationActive:
                self._subtitle_overlay.hide()
                self._subtitle_overlay_visible = False
                return

            top_left = self.video_widget.mapToGlobal(QPoint(0, 0))
            w = self.video_widget.width()
            h = self.video_widget.height()
            if w <= 0 or h <= 0:
                self._subtitle_overlay.hide()
                self._subtitle_overlay_visible = False
                return

            video_rect = QRect(top_left, QSize(w, h))
            if mw:
                win_tl = mw.mapToGlobal(QPoint(0, 0))
                win_rect = QRect(win_tl, mw.size())
                clipped = video_rect.intersected(win_rect)
            else:
                clipped = video_rect

            if clipped.isEmpty():
                self._subtitle_overlay.hide()
                self._subtitle_overlay_visible = False
                return

            if not self._subtitle_overlay_visible:
                self._subtitle_overlay.show()
                self._subtitle_overlay_visible = True

            self._subtitle_overlay.setGeometry(clipped)

            rel = QPoint(video_rect.x() - clipped.x(), video_rect.y() - clipped.y())
            local_w = clipped.width()
            local_h = clipped.height()

            max_width = int(w * 0.86)
            label_w = max(200, max_width)
            label_x = (w - label_w) // 2 - rel.x()

            def _measure_label_h(lbl, cache_key: str):
                try:
                    fm = QFontMetrics(lbl.font())
                    text_flags = Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap
                    txt = ""
                    try:
                        txt = lbl.text() or ""
                    except Exception:
                        txt = ""
                    if not txt:
                        txt = "X"

                    try:
                        font_pt = int(lbl.font().pointSize())
                    except Exception:
                        font_pt = None

                    cache = self._subtitle_geom_cache.get(cache_key) if hasattr(self, '_subtitle_geom_cache') else None
                    if cache is not None:
                        if cache.get('text') == txt and cache.get('font_pt') == font_pt and cache.get('w') == label_w:
                            return cache.get('h', 72)

                    br = fm.boundingRect(QRect(0, 0, label_w, 10000), text_flags, txt)

                    extra_px = 18
                    lh = max(fm.height() + extra_px, br.height() + extra_px)
                    lh = min(int(h * 0.32), lh)
                    if lh < 48:
                        lh = 48

                    if cache is not None:
                        cache['text'] = txt
                        cache['font_pt'] = font_pt
                        cache['w'] = label_w
                        cache['h'] = lh

                    return lh
                except Exception:
                    return 72

            top_h = _measure_label_h(self.subtitle_label_top, 'top')
            bot_h = _measure_label_h(self.subtitle_label_bottom, 'bottom')

            # Top label: below top bar (50px) + margin
            top_bar_h = 50
            top_y = top_bar_h + margin - rel.y()
            min_y = margin - rel.y()
            if top_y < min_y:
                top_y = min_y
            self.subtitle_label_top.setGeometry(label_x, top_y, label_w, top_h)

            # Bottom label: above bottom bar (80px) + margin
            bot_y = h - 80 - bot_h - margin - rel.y()
            if bot_y < min_y:
                bot_y = min_y
            self.subtitle_label_bottom.setGeometry(label_x, bot_y, label_w, bot_h)

            self._subtitle_overlay.raise_()
            self.subtitle_label_top.raise_()
            self.subtitle_label_bottom.raise_()
        except Exception:
            return

    def enterEvent(self, event):
        self._show_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._start_hide_timer()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self._show_controls()
        self._start_hide_timer()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_play()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._toggle_play()
        elif event.key() == Qt.Key_Escape:
            if self._is_fullscreen:
                self._toggle_fullscreen()
        elif event.key() == Qt.Key_F:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key_Left:
            self._seek_relative(-5)
        elif event.key() == Qt.Key_Right:
            self._seek_relative(5)
        elif event.key() == Qt.Key_Up:
            self._adjust_volume(5)
        elif event.key() == Qt.Key_Down:
            self._adjust_volume(-5)
        else:
            super().keyPressEvent(event)

    def _show_controls(self):
        """Show both overlay bars and reset the hide timer."""
        self._hide_timer.stop()
        if not self._controls_visible:
            self.top_bar.show()
            self.bottom_bar.show()
            self._controls_visible = True
            self.setCursor(QCursor(Qt.ArrowCursor))

    def _hide_controls(self):
        """Hide both overlay bars when video is playing (after inactivity)."""
        if self._controls_visible and self._player.playbackState() == QMediaPlayer.PlayingState:
            self.top_bar.hide()
            self.bottom_bar.hide()
            self._controls_visible = False
            self.setCursor(QCursor(Qt.BlankCursor))

    def _start_hide_timer(self):
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._hide_timer.start(3000)  # Hide after 3 seconds

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._show_controls()
        else:
            self._player.play()
            self._start_hide_timer()

    def _seek(self, percent: float):
        if self._player.duration() > 0:
            self._player.setPosition(int(percent * self._player.duration()))

    def _seek_relative(self, seconds: int):
        new_pos = self._player.position() + (seconds * 1000)
        new_pos = max(0, min(new_pos, self._player.duration()))
        self._player.setPosition(new_pos)

    def _set_volume(self, value: int):
        if self._own_player:
            self._audio_output.setVolume(value / 100.0)
        else:
            # Get audio output from player
            audio = self._player.audioOutput()
            if audio:
                audio.setVolume(value / 100.0)

    def _adjust_volume(self, delta: int):
        current = self.bottom_bar.volume_slider.value()
        new_vol = max(0, min(100, current + delta))
        self.bottom_bar.volume_slider.setValue(new_vol)

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        print(f"Fullscreen: {'ON' if self._is_fullscreen else 'OFF'}")

        # Emit signal for parent to handle fullscreen on the main window
        self.fullscreenToggled.emit(self._is_fullscreen)

        if not self._is_fullscreen:
            # IMMEDIATELY stop PlayerBar animation and reset
            self._stop_playerbar_animation_now()

            # Force parent layout recalculation after exiting fullscreen
            QTimer.singleShot(100, self._fix_parent_layout)

    def _stop_playerbar_animation_now(self):
        """Immediately stop PlayerBar animation and reset to full visibility."""
        parent = self.parentWidget()
        while parent:
            if hasattr(parent, 'player_bar'):
                # Stop animation
                if hasattr(parent, '_playerbar_animation'):
                    parent._playerbar_animation.stop()
                # Reset opacity to fully visible
                if hasattr(parent, '_playerbar_opacity_effect'):
                    parent._playerbar_opacity_effect.setOpacity(1.0)
                # Ensure visible
                parent.player_bar.show()
                break
            parent = parent.parentWidget()

    def _fix_parent_layout(self):
        """Fix parent layout after fullscreen exit to prevent PlayerBar clipping."""
        # Find MusicPanelWidget parent
        parent = self.parentWidget()
        music_panel = None

        while parent:
            if hasattr(parent, 'player_bar'):
                music_panel = parent
                break
            parent = parent.parentWidget()

        if music_panel:
            # Resize trick: briefly change size to force complete relayout
            current_size = music_panel.size()
            music_panel.resize(current_size.width(), current_size.height() - 1)
            QTimer.singleShot(50, lambda: self._restore_size(music_panel, current_size))

    def _restore_size(self, widget, original_size):
        """Restore original size after resize trick."""
        widget.resize(original_size)

        # Stop any running playerbar animation
        if hasattr(widget, '_playerbar_animation'):
            widget._playerbar_animation.stop()

        # Reset player_bar to full height (must set maximumHeight too since animation uses it)
        if hasattr(widget, 'player_bar'):
            widget.player_bar.setMaximumHeight(75)  # Reset maximumHeight that animation changes
            widget.player_bar.setFixedHeight(75)
            widget.player_bar.setMinimumHeight(75)
            widget.player_bar.show()

    def _set_aspect_ratio(self, mode: str):
        """Set video aspect ratio mode: fill, fit, or stretch."""
        if mode == "fill":
            self.video_widget.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        elif mode == "fit":
            self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        elif mode == "stretch":
            self.video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)

    def _on_position(self, pos: int):
        dur = self._player.duration()
        try:
            # Throttle UI updates to avoid flooding the GUI thread.
            # QMediaPlayer.positionChanged can fire very frequently.
            # When video is complex, excessive slider/label updates can cause stutter.
            if hasattr(self, 'bottom_bar') and hasattr(self.bottom_bar, 'timeline'):
                if self.bottom_bar.timeline.isSliderDown():
                    # User is dragging; don't fight their interaction.
                    pass
                else:
                    now = time.monotonic()
                    if (now - getattr(self, '_last_position_ui_update_t', 0.0)) >= getattr(self, '_position_ui_update_interval_s', 0.12):
                        self._last_position_ui_update_t = now
                        self.bottom_bar.set_position(pos / 1000.0, dur / 1000.0)
        except Exception:
            try:
                self.bottom_bar.set_position(pos / 1000.0, dur / 1000.0)
            except Exception:
                pass
        if getattr(self, '_render_suspended', False):
            return
        self._update_subtitle(pos)

    def _on_state(self, state):
        is_playing = state == QMediaPlayer.PlayingState
        self.bottom_bar.set_playing(is_playing)

        if not is_playing:
            self._show_controls()

    def set_title(self, title: str):
        self.top_bar.set_title(title)

    def play_file(self, path: str, title: str = None):
        """Load and play a video file."""
        self._player.setSource(QUrl.fromLocalFile(path))
        self._auto_load_sidecar_subtitles(path)
        self._player.play()

        if title:
            self.set_title(title)
        else:
            self.set_title(os.path.basename(path))

    def set_subtitle_file(self, subtitle_path: Optional[str]):
        self._load_subtitles(subtitle_path)

    def clear_subtitles(self):
        self._subtitle_cues = []
        self._subtitle_idx = -1
        self._subtitle_path = None
        self._subtitle_last_error = None
        self._subtitle_start_times = []
        try:
            self.subtitle_label_bottom.clear()
            self.subtitle_label_top.clear()
        except Exception:
            pass
        try:
            self._subtitle_overlay.hide()
        except Exception:
            pass
        self._subtitle_overlay_visible = False

    def set_subtitle_font_size(self, pt: int):
        try:
            self.subtitle_label_bottom.set_font_point_size(int(pt))
            self.subtitle_label_top.set_font_point_size(int(pt))
        except Exception:
            try:
                f = self.subtitle_label_bottom.font()
                f.setPointSize(int(pt))
                self.subtitle_label_bottom.setFont(f)
                self.subtitle_label_top.setFont(f)
                self.subtitle_label_bottom.update()
                self.subtitle_label_top.update()
            except Exception:
                pass

    def get_subtitle_font_size(self) -> int:
        try:
            return int(self.subtitle_label_bottom.get_font_point_size())
        except Exception:
            try:
                return int(self.subtitle_label_bottom.font().pointSize())
            except Exception:
                return 16

    def set_subtitle_font_variant(self, bold: bool, italic: bool):
        try:
            self.subtitle_label_bottom.set_font_variant(bool(bold), bool(italic))
            self.subtitle_label_top.set_font_variant(bool(bold), bool(italic))
        except Exception:
            try:
                f = self.subtitle_label_bottom.font()
                f.setBold(bool(bold))
                f.setItalic(bool(italic))
                self.subtitle_label_bottom.setFont(f)
                self.subtitle_label_top.setFont(f)
                self.subtitle_label_bottom.update()
                self.subtitle_label_top.update()
            except Exception:
                pass

    def get_subtitle_font_variant(self):
        try:
            return self.subtitle_label_bottom.get_font_variant()
        except Exception:
            try:
                f = self.subtitle_label_bottom.font()
                return bool(f.bold()), bool(f.italic())
            except Exception:
                return False, False

    def get_active_subtitle_path(self):
        return self._subtitle_path

    def get_subtitle_cue_count(self):
        try:
            return len(self._subtitle_cues)
        except Exception:
            return 0

    def get_subtitle_last_error(self):
        return self._subtitle_last_error

    def _auto_load_sidecar_subtitles(self, video_path: str):
        try:
            base, _ext = os.path.splitext(video_path)
            cand = [
                base + '.srt', base + '.vtt', base + '.ass', base + '.ssa',
                base + '.SRT', base + '.VTT', base + '.ASS', base + '.SSA',
            ]
            for p in cand:
                if os.path.exists(p):
                    self._load_subtitles(p)
                    return
        except Exception:
            pass
        self.clear_subtitles()

    def _parse_time_ms(self, s: str) -> int:
        s = s.strip().replace(',', '.')
        parts = s.split(':')
        if len(parts) == 3:
            hh, mm, rest = parts
        elif len(parts) == 2:
            hh = '0'
            mm, rest = parts
        else:
            return 0
        if '.' in rest:
            ss, ms = rest.split('.', 1)
        else:
            ss, ms = rest, '0'
        ms = (ms + '000')[:3]
        return (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(ms)

    def _parse_ass_time_ms(self, s: str) -> int:
        try:
            s = s.strip()
            parts = s.split(':')
            if len(parts) != 3:
                return 0
            hh = int(parts[0])
            mm = int(parts[1])
            ss_cs = parts[2]
            if '.' in ss_cs:
                ss_str, cs_str = ss_cs.split('.', 1)
            else:
                ss_str, cs_str = ss_cs, '0'
            ss = int(ss_str)
            cs = int((cs_str + '00')[:2])
            return ((hh * 3600 + mm * 60 + ss) * 1000) + (cs * 10)
        except Exception:
            return 0

    def _ass_to_plain_text(self, text: str) -> str:
        try:
            t = text
            t = t.replace('\\N', '\n').replace('\\n', '\n')
            t = t.replace('\\h', ' ')
            t = re.sub(r'\{[^}]*\}', '', t)
            t = re.sub(r'\s+', ' ', t)
            t = t.replace('\\', '\\')
            return t.strip()
        except Exception:
            return text.strip()

    def _ass_is_vector_drawing(self, raw_text: str) -> bool:
        try:
            if not raw_text:
                return False

            # ASS drawing mode is enabled with tags like {\p1} and disabled with {\p0}.
            # When drawing mode is enabled, the dialogue "Text" field contains
            # vector path commands (m/l/b/s/p/c...) which are NOT human-readable.
            # Our renderer is text-only, so we must skip these cues.
            drawing = False

            # 1) Primary signal: explicit \pN drawing mode toggles inside override blocks.
            for m in re.finditer(r'\{([^}]*)\}', raw_text):
                tags = (m.group(1) or '').lower()
                p = re.search(r'\\p(\d+)', tags)
                if not p:
                    continue
                try:
                    n = int(p.group(1))
                    drawing = n > 0
                except Exception:
                    continue

            if drawing:
                return True

            # 2) Some files can still contain pure drawing payloads even when \p tags are
            # missing/stripped during extraction/conversion. Add a heuristic fallback:
            # if the visible text looks like ASS vector path commands, skip it.
            t = raw_text
            try:
                t = t.replace('\\N', ' ').replace('\\n', ' ').replace('\\h', ' ')
            except Exception:
                pass
            t = re.sub(r'\{[^}]*\}', '', t).strip()
            if not t:
                return False

            tl = t.lower()
            # Common drawing command lines start with: m/l/b/s/p/c and then lots of numbers.
            if re.match(r'^[mlbspc]\s', tl):
                nums = re.findall(r'-?\d+(?:\.\d+)?', tl)
                letters = re.findall(r'[a-z]', tl)
                if len(nums) >= 6 and len(letters) <= 6:
                    return True

            return False
        except Exception:
            return False

    def _ass_detect_placement(self, raw_text: str):
        try:
            # Determine whether this line should be drawn near the top.
            # This is a lightweight heuristic, not full ASS typesetting.
            #
            # Supported cases:
            # - {\an8} (top-center) and other top-aligned variants {\an7},{\an8},{\an9}
            # - {\pos(x,y)}: if y is in upper half of the frame, consider it top
            #
            # Returns: 'top' or 'bottom'

            t = raw_text or ""

            # Look at the first override block; many scripts use it for alignment/pos.
            m = re.search(r'\{([^}]*)\}', t)
            tags = m.group(1) if m else ""
            tags_l = tags.lower()

            an = re.search(r'\\an(\d)', tags_l)
            if an:
                try:
                    n = int(an.group(1))
                    if n in (7, 8, 9):
                        return 'top'
                    return 'bottom'
                except Exception:
                    pass

            pos = re.search(r'\\pos\(\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\)', tags_l)
            if pos:
                try:
                    y = float(pos.group(2))
                    # Without PlayResY we can't properly map coordinates.
                    # Empirically, many scripts use 720/1080 coordinate space.
                    # Treat y < 0.5*720 as top.
                    if y < 360.0:
                        return 'top'
                except Exception:
                    pass

            return 'bottom'
        except Exception:
            return 'bottom'

    def _split_ass_fields(self, s: str, count: int):
        out = []
        cur = ''
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == ',' and len(out) < count - 1:
                out.append(cur)
                cur = ''
            else:
                cur += ch
            i += 1
        out.append(cur)
        if len(out) < count:
            out.extend([''] * (count - len(out)))
        return out

    def _parse_ass(self, content: str):
        lines = [ln.strip('\r') for ln in content.splitlines()]
        in_events = False
        fmt = None
        cues = []
        for ln in lines:
            s = ln.strip()
            if not s or s.startswith(';'):
                continue
            if s.startswith('[') and s.endswith(']'):
                in_events = (s.lower() == '[events]')
                continue
            if not in_events:
                continue
            if s.lower().startswith('format:'):
                fmt_raw = s.split(':', 1)[1].strip()
                fmt = [f.strip().lower() for f in fmt_raw.split(',')]
                continue
            if not s.lower().startswith('dialogue:'):
                continue
            if not fmt:
                fmt = ['layer', 'start', 'end', 'style', 'name', 'marginl', 'marginr', 'marginv', 'effect', 'text']
            payload = s.split(':', 1)[1].lstrip()
            fields = self._split_ass_fields(payload, len(fmt))
            row = {fmt[i]: fields[i] for i in range(min(len(fmt), len(fields)))}
            start_ms = self._parse_ass_time_ms(row.get('start', '0:00:00.00'))
            end_ms = self._parse_ass_time_ms(row.get('end', '0:00:00.00'))
            if end_ms <= start_ms:
                continue
            raw_text = row.get('text', '')
            if self._ass_is_vector_drawing(raw_text):
                continue
            placement = self._ass_detect_placement(raw_text)
            text = self._ass_to_plain_text(raw_text)
            if not text:
                continue
            cues.append((start_ms, end_ms, text, placement))
        cues.sort(key=lambda x: x[0])
        return cues

    def _parse_srt(self, content: str):
        blocks = re.split(r'\n\s*\n', content.strip(), flags=re.MULTILINE)
        cues = []
        for b in blocks:
            lines = [ln.strip('\r') for ln in b.splitlines() if ln.strip('\r') != '']
            if len(lines) < 2:
                continue
            if '-->' in lines[0]:
                time_line = lines[0]
                text_lines = lines[1:]
            else:
                time_line = lines[1] if len(lines) >= 2 else ''
                text_lines = lines[2:] if len(lines) >= 3 else []
            if '-->' not in time_line:
                continue
            left, right = [x.strip() for x in time_line.split('-->', 1)]
            right = right.split()[0].strip()
            start = self._parse_time_ms(left)
            end = self._parse_time_ms(right)
            if end <= start:
                continue
            text = '\n'.join(text_lines).strip()
            if not text:
                continue
            cues.append((start, end, text))
        cues.sort(key=lambda x: x[0])
        return cues

    def _parse_vtt(self, content: str):
        content = content.lstrip('\ufeff')
        lines_all = content.splitlines()
        if lines_all and lines_all[0].strip().upper().startswith('WEBVTT'):
            lines_all = lines_all[1:]
        normalized = '\n'.join(lines_all)
        blocks = re.split(r'\n\s*\n', normalized.strip(), flags=re.MULTILINE)
        cues = []
        for b in blocks:
            lines = [ln.strip('\r') for ln in b.splitlines() if ln.strip('\r') != '']
            if not lines:
                continue
            if '-->' in lines[0]:
                time_line = lines[0]
                text_lines = lines[1:]
            elif len(lines) > 1 and '-->' in lines[1]:
                time_line = lines[1]
                text_lines = lines[2:]
            else:
                continue
            left, right = [x.strip() for x in time_line.split('-->', 1)]
            right = right.split()[0].strip()
            start = self._parse_time_ms(left)
            end = self._parse_time_ms(right)
            if end <= start:
                continue
            text = '\n'.join(text_lines).strip()
            if not text:
                continue
            cues.append((start, end, text))
        cues.sort(key=lambda x: x[0])
        return cues

    def _load_subtitles(self, subtitle_path: Optional[str]):
        if not subtitle_path:
            self.clear_subtitles()
            return
        try:
            if not os.path.exists(subtitle_path):
                self._subtitle_last_error = "Subtitle file not found"
                self.clear_subtitles()
                return
            with open(subtitle_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                data = f.read()
            ext = os.path.splitext(subtitle_path)[1].lower()
            if ext == '.srt':
                cues = self._parse_srt(data)
            elif ext == '.vtt':
                cues = self._parse_vtt(data)
            elif ext in ('.ass', '.ssa'):
                cues = self._parse_ass(data)
            else:
                self._subtitle_last_error = "Unsupported subtitle format"
                self.clear_subtitles()
                return

            self._subtitle_cues = cues
            self._subtitle_idx = -1
            self._subtitle_path = subtitle_path
            try:
                self._subtitle_start_times = [int(c[0]) for c in cues]
            except Exception:
                self._subtitle_start_times = []

            if not cues:
                self._subtitle_last_error = "No subtitle cues parsed"
            else:
                self._subtitle_last_error = None

            self.subtitle_label.clear()
            self.subtitle_label.setVisible(False)
            try:
                self.subtitle_label_top.clear()
                self.subtitle_label_top.setVisible(False)
                self.subtitle_label_bottom.clear()
                self.subtitle_label_bottom.setVisible(False)
            except Exception:
                pass
        except Exception:
            self._subtitle_last_error = "Failed to load subtitles"
            self.clear_subtitles()

    def _update_subtitle(self, pos_ms: int):
        if not self._subtitle_cues:
            try:
                if self.subtitle_label_bottom.isVisible():
                    self.subtitle_label_bottom.setVisible(False)
                if self.subtitle_label_top.isVisible():
                    self.subtitle_label_top.setVisible(False)
            except Exception:
                pass
            return

        try:
            active_top = []
            active_bottom = []

            # Fast windowing: start from the last cue that begins before current time.
            start_i = 0
            try:
                if getattr(self, '_subtitle_start_times', None):
                    start_i = bisect.bisect_right(self._subtitle_start_times, pos_ms) - 1
                    if start_i < 0:
                        start_i = 0
            except Exception:
                start_i = 0

            # Scan a small neighborhood around start_i for overlapping cues.
            # This prevents O(n) scans on every positionChanged for long subtitle tracks.
            i = start_i
            while i >= 0:
                try:
                    s, e = self._subtitle_cues[i][0], self._subtitle_cues[i][1]
                except Exception:
                    break
                if e < pos_ms:
                    break
                i -= 1
            scan_from = max(0, i)

            max_scan = 220
            scanned = 0
            for cue in self._subtitle_cues[scan_from:]:
                scanned += 1
                if scanned > max_scan:
                    break
                try:
                    s, e, t, placement = cue
                except Exception:
                    # Backwards compat for older tuples
                    s, e, t = cue
                    placement = 'bottom'
                if s > pos_ms:
                    break
                if s <= pos_ms <= e and t:
                    if placement == 'top':
                        active_top.append(t)
                    else:
                        active_bottom.append(t)

            if active_top:
                tt = "\n".join(active_top[-3:])
                if self.subtitle_label_top.text() != tt:
                    self.subtitle_label_top.setText(tt)
                if not self.subtitle_label_top.isVisible():
                    self.subtitle_label_top.setVisible(True)
                self.subtitle_label_top.raise_()
            else:
                if self.subtitle_label_top.isVisible():
                    self.subtitle_label_top.setVisible(False)

            if active_bottom:
                tb = "\n".join(active_bottom[-3:])
                if self.subtitle_label_bottom.text() != tb:
                    self.subtitle_label_bottom.setText(tb)
                if not self.subtitle_label_bottom.isVisible():
                    self.subtitle_label_bottom.setVisible(True)
                self.subtitle_label_bottom.raise_()
            else:
                if self.subtitle_label_bottom.isVisible():
                    self.subtitle_label_bottom.setVisible(False)
            return
        except Exception:
            pass

        idx = self._subtitle_idx
        if 0 <= idx < len(self._subtitle_cues):
            s, e, t = self._subtitle_cues[idx]
            if s <= pos_ms <= e:
                best = idx
                best_s = s

                i = idx + 1
                while i < len(self._subtitle_cues):
                    s2, e2, _t2 = self._subtitle_cues[i]
                    if s2 > pos_ms:
                        break
                    if s2 <= pos_ms <= e2 and s2 >= best_s:
                        best = i
                        best_s = s2
                    i += 1

                if best != idx:
                    self._subtitle_idx = best
                    _s, _e, t = self._subtitle_cues[best]

                if self.subtitle_label.text() != t:
                    self.subtitle_label.setText(t)
                if not self.subtitle_label.isVisible():
                    self.subtitle_label.setVisible(True)
                self.subtitle_label.raise_()
                return
            if pos_ms > e:
                idx += 1
        else:
            idx = 0

        lo = max(0, idx)
        hi = len(self._subtitle_cues) - 1
        found = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            s, e, _t = self._subtitle_cues[mid]
            if pos_ms < s:
                hi = mid - 1
            elif pos_ms > e:
                lo = mid + 1
            else:
                found = mid
                break

        self._subtitle_idx = found
        if found >= 0:
            best = found
            best_s, best_e, best_t = self._subtitle_cues[best]

            i = found - 1
            while i >= 0:
                s2, e2, t2 = self._subtitle_cues[i]
                if e2 < pos_ms:
                    break
                if s2 <= pos_ms <= e2 and s2 >= best_s:
                    best = i
                    best_s, best_e, best_t = s2, e2, t2
                i -= 1

            i = found + 1
            while i < len(self._subtitle_cues):
                s2, e2, t2 = self._subtitle_cues[i]
                if s2 > pos_ms:
                    break
                if s2 <= pos_ms <= e2 and s2 >= best_s:
                    best = i
                    best_s, best_e, best_t = s2, e2, t2
                i += 1

            self._subtitle_idx = best
            t = best_t
            if self.subtitle_label.text() != t:
                self.subtitle_label.setText(t)
            if not self.subtitle_label.isVisible():
                self.subtitle_label.setVisible(True)
            self.subtitle_label.raise_()
        else:
            if self.subtitle_label.isVisible():
                self.subtitle_label.setVisible(False)


# Test standalone
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    player = VideoPlayerWidget()
    player.resize(800, 450)
    player.setWindowTitle("Video Player Test")
    player.show()

    # Test with a video file if exists
    test_file = r"C:\Users\TDD\Music\Fujii Kaze - Damn (Official Video).mp4"
    if os.path.exists(test_file):
        player.play_file(test_file)

    sys.exit(app.exec())
