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
    QSpacerItem, QComboBox
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, QPoint, QUrl
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPalette, QCursor,
    QPainter, QBrush, QLinearGradient
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import os


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
        self.time_current.setFixedWidth(50)

        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setObjectName("videoTimeline")
        self.timeline.setRange(0, 1000)
        self.timeline.sliderMoved.connect(lambda v: self.seekChanged.emit(v / 1000.0))

        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("timeLabel")
        self.time_total.setFixedWidth(50)
        self.time_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

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
            self.timeline.blockSignals(True)
            self.timeline.setValue(int((current / total) * 1000))
            self.timeline.blockSignals(False)

        self.time_current.setText(self._format_time(current))
        self.time_total.setText(self._format_time(total))

    def _format_time(self, seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"


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
        self.bottom_bar.set_position(pos / 1000.0, dur / 1000.0)

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
        self._player.play()

        if title:
            self.set_title(title)
        else:
            self.set_title(os.path.basename(path))


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
