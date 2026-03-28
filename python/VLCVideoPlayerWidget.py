"""
VLC Video Player Widget

A video player using VLC backend with hardware decoding.
Drop-in replacement for VideoPlayerWidget using VLC instead of Qt MediaPlayer.

Features:
- Hardware decoding (D3D11VA/DXVA2)
- Audio pitch correction at playback speed changes
- All codec support
- Same interface as VideoPlayerWidget for seamless integration

Component Name: VLCVideoPlayerWidget
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

import os
import re
import bisect
import time
from typing import Optional

# VLC availability check - defer actual import to avoid OpenGL conflict at startup
_VLC_AVAILABLE = None  # Will be checked at runtime

def _check_vlc_available():
    """Check if VLC module exists without importing it (to avoid OpenGL conflict)."""
    global _VLC_AVAILABLE
    if _VLC_AVAILABLE is not None:
        return _VLC_AVAILABLE
    try:
        # Just check if the module can be found, don't actually import it
        import importlib.util
        spec = importlib.util.find_spec("vlc")
        _VLC_AVAILABLE = spec is not None
        return _VLC_AVAILABLE
    except (ImportError, ModuleNotFoundError):
        _VLC_AVAILABLE = False
        return False

# Import existing subtitle rendering from VideoPlayerWidget
from VideoPlayerWidget import (
    _SubtitleRenderWidget,
    _SubtitleOverlayWindow,
    VideoTopBar,
    VideoBottomBar,
    _format_time
)


class VLCVideoPlayerWidget(QWidget):
    """
    VLC-based Video Player with auto-hiding split overlay controls.
    Uses VLC backend for hardware-accelerated video playback with all codec support.
    
    Drop-in replacement for VideoPlayerWidget.
    
    Component Name: VLCVideoPlayerWidget
    """

    # Signals (same as VideoPlayerWidget for compatibility)
    backRequested = Signal()
    fullscreenToggled = Signal(bool)  # True = entering fullscreen, False = exiting

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VLCVideoPlayerWidget")
        
        # Check VLC availability (deferred to avoid OpenGL conflict at startup)
        if not _check_vlc_available():
            raise ImportError("VLC not available. Install python-vlc and ensure VLC is installed.")
        
        # Initialize VLC player (deferred until first use)
        self._vlc_instance = None
        self._vlc_player = None
        # Don't initialize VLC here - defer until video is actually played
        # self._init_vlc()
        
        # State
        self._controls_visible = True
        self._is_fullscreen = False
        self._is_playing = False
        self._duration = 0
        self._position = 0
        self._volume = 100

        # Subtitle support
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
        # Position UI throttle: update slider and time labels at most every 120ms
        # (human eye can't perceive sub-100ms timeline movement, no need to update more)
        self._position_ui_update_interval_s = 0.12

        self._render_suspended = False
        self._current_media_path = None
        # Track last known playing state to avoid redundant set_playing widget signals
        self._last_known_playing_state = None

        # Hide timer
        self._hide_timer = QTimer()
        self._hide_timer.timeout.connect(self._hide_controls)
        self._hide_timer.setSingleShot(True)
        
        # Position polling timer (VLC doesn't have Qt signals, need to poll)
        # IMPORTANT: Set to 80ms (not 100ms) to de-phase from the subtitle overlay timer (137ms).
        # When both were 100ms, they fired simultaneously every ~1s causing coordinated UI spikes.
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(80)  # 80ms avoids coincidence with subtitle overlay (137ms)
        self._poll_timer.timeout.connect(self._poll_vlc_state)

        self._setup_ui()
        self._connect_signals()

        # Start with controls visible
        self._show_controls()

    def _init_vlc(self):
        """Initialize VLC instance with optimal settings for video playback."""
        # Import vlc locally to avoid OpenGL conflict at module level
        import vlc
        
        try:
            # VLC arguments for hardware decoding and optimal playback
            # Use DXVA2 instead of D3D11VA to avoid conflict with OpenGL (CrosshairWidget)
            vlc_args = [
                # Hardware decoding - DXVA2 only (D3D11VA conflicts with OpenGL)
                '--avcodec-hw=dxva2',
                
                # Disable OpenGL/GLX in VLC to prevent conflict with Qt OpenGL
                '--disable-gl',
                '--no-gl',
                
                # Use DirectX Direct3D for video output
                '--vout=d3d11,direct3d9,directdraw',
                
                # Audio pitch correction at speed changes (time-stretch)
                '--audio-time-stretch',
                
                # Disable VLC's internal logging and OSD
                '--no-video-title-show',
                '--no-stats',
                '--no-osd',
                '--no-xlib',
                
                # Network caching for smooth streaming
                '--network-caching=1000',
                
                # File caching
                '--file-caching=1000',
                
                # Live media caching
                '--live-caching=1000',
            ]
            
            # Create VLC instance
            self._vlc_instance = vlc.Instance(' '.join(vlc_args))
            
            if self._vlc_instance:
                self._vlc_player = self._vlc_instance.media_player_new()
                print("[VLC] Video player initialized with hardware decoding")
            else:
                print("[VLC] Failed to create VLC instance")
                
        except Exception as e:
            print(f"[VLC] Initialization failed: {e}")
            self._vlc_instance = None
            self._vlc_player = None

    def _setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display widget (container for VLC video output)
        self.video_widget = QWidget()
        self.video_widget.setObjectName("videoDisplay")
        self.video_widget.setStyleSheet("background: #000000;")
        layout.addWidget(self.video_widget)

        # Subtitle overlay window (separate top-level to overlay on hardware-rendered video)
        self._subtitle_overlay = _SubtitleOverlayWindow()
        self.subtitle_label_top = self._subtitle_overlay.label_top
        self.subtitle_label_bottom = self._subtitle_overlay.label_bottom
        self.subtitle_label = self.subtitle_label_bottom
        self._subtitle_overlay_visible = False
        self._subtitle_overlay_timer = QTimer(self)
        # IMPORTANT: Use 137ms (prime number) to de-phase from 80ms poll timer.
        # At 100ms both would collide every ~1 second causing coordinated UI hitches.
        self._subtitle_overlay_timer.setInterval(137)
        self._subtitle_overlay_timer.timeout.connect(self._update_subtitle_overlay_geometry)
        try:
            QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)
        except Exception:
            pass

        # Split overlay bars (positioned absolutely over video edges only)
        self.top_bar = VideoTopBar(self)
        self.bottom_bar = VideoBottomBar(self)

        # Styling
        self.setStyleSheet("""
            QWidget#VLCVideoPlayerWidget {
                background: #000000;
            }
            QWidget#videoDisplay {
                background: #000000;
            }
        """)

        # Enable mouse tracking for auto-hide
        self.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)

    def _connect_signals(self):
        """Connect UI signals."""
        # Top bar signals
        self.top_bar.fullscreenClicked.connect(self._toggle_fullscreen)
        self.top_bar.backClicked.connect(self.backRequested.emit)
        self.top_bar.aspectRatioChanged.connect(self._set_aspect_ratio)

        # Bottom bar signals
        self.bottom_bar.playClicked.connect(self._toggle_play)
        self.bottom_bar.seekChanged.connect(self._seek)
        self.bottom_bar.volumeChanged.connect(self._set_volume)

    def _attach_vlc_video(self):
        """Attach VLC video output to our video widget."""
        if not self._vlc_player:
            return
        
        try:
            # Get window handle for video embedding
            win_id = int(self.video_widget.winId())
            
            if os.name == 'nt':  # Windows
                self._vlc_player.set_hwnd(win_id)
            elif sys.platform == 'darwin':  # macOS
                self._vlc_player.set_nsobject(win_id)
            else:  # Linux
                self._vlc_player.set_xwindow(win_id)
            
            print(f"[VLC] Video attached to window {win_id}")
        except Exception as e:
            print(f"[VLC] Failed to attach video: {e}")

    def showEvent(self, event):
        """Handle show event - attach VLC video output."""
        super().showEvent(event)
        
        # Attach VLC video to widget when shown
        self._attach_vlc_video()
        
        try:
            if not self._render_suspended:
                self._subtitle_overlay.show()
                self._subtitle_overlay_timer.start()
        except Exception:
            pass
        self._update_subtitle_overlay_geometry()

    def resizeEvent(self, event):
        """Handle resize - reposition overlay bars."""
        super().resizeEvent(event)
        # Position bars at top and bottom edges only
        self.top_bar.setGeometry(0, 0, self.width(), 50)
        self.bottom_bar.setGeometry(0, self.height() - 80, self.width(), 80)

        margin = 18
        self._update_subtitle_overlay_geometry(margin)
        self.top_bar.raise_()
        self.bottom_bar.raise_()
        
        # Re-attach VLC video after resize
        QTimer.singleShot(50, self._attach_vlc_video)

    def moveEvent(self, event):
        """Handle move event."""
        super().moveEvent(event)
        self._update_subtitle_overlay_geometry()

    def hideEvent(self, event):
        """Handle hide event."""
        try:
            self._subtitle_overlay.hide()
            self._subtitle_overlay_timer.stop()
        except Exception:
            pass
        super().hideEvent(event)

    def closeEvent(self, event):
        """Handle close event."""
        try:
            self._subtitle_overlay.close()
            self._subtitle_overlay_timer.stop()
            self._poll_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_app_state_changed(self, state):
        """Handle application state change."""
        self._update_subtitle_overlay_geometry()

    # === Subtitle Methods (same as VideoPlayerWidget) ===
    
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
        """Update subtitle overlay geometry - copied from VideoPlayerWidget."""
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

            # Use global coordinates for separate top-level window
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

            # Cache video size to skip unnecessary geometry recalculations
            if hasattr(self, '_last_video_size'):
                current_size = self.video_widget.size()
                if self._last_video_size == current_size and self._subtitle_overlay_visible:
                    return
                self._last_video_size = current_size
            else:
                self._last_video_size = self.video_widget.size()

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

            top_bar_h = 50
            top_y = top_bar_h + margin - rel.y()
            min_y = margin - rel.y()
            if top_y < min_y:
                top_y = min_y
            self.subtitle_label_top.setGeometry(label_x, top_y, label_w, top_h)

            bot_y = h - 80 - bot_h - margin - rel.y()
            if bot_y < min_y:
                bot_y = min_y
            self.subtitle_label_bottom.setGeometry(label_x, bot_y, label_w, bot_h)

            self._subtitle_overlay.raise_()
            self.subtitle_label_top.raise_()
            self.subtitle_label_bottom.raise_()
        except Exception:
            return

    # === VLC State Polling ===
    
    def _poll_vlc_state(self):
        """Poll VLC player state and update UI."""
        if not self._vlc_player:
            return
        
        try:
            # Get current state
            state = self._vlc_player.get_state()
            
            # Update playing state (track change to avoid redundant widget signals)
            new_is_playing = (state == vlc.State.Playing)
            self._is_playing = new_is_playing
            
            # Get position and duration
            self._position = self._vlc_player.get_time()
            self._duration = self._vlc_player.get_length()
            
            # Throttle timeline/time-label updates - only update if enough time has passed.
            # This prevents the progress bar from consuming CPU on every 80ms poll tick.
            now = time.monotonic()
            if (now - self._last_position_ui_update_t) >= self._position_ui_update_interval_s:
                self._last_position_ui_update_t = now
                self.bottom_bar.set_position(self._position / 1000.0, self._duration / 1000.0)
            
            # Update subtitle (only if not suspended)
            if not self._render_suspended:
                self._update_subtitle(self._position)
            
            # Only signal the play button if state actually changed - avoids repeated QPainter calls
            if new_is_playing != self._last_known_playing_state:
                self._last_known_playing_state = new_is_playing
                self.bottom_bar.set_playing(new_is_playing)
            
            # Check for end of media
            if state == vlc.State.Ended:
                self._is_playing = False
                self._show_controls()
                
        except Exception as e:
            pass

    # === Control Visibility ===
    
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
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._toggle_play()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            parent = self.parentWidget()
            is_fullscreen = False
            while parent:
                if hasattr(parent, '_is_fullscreen'):
                    is_fullscreen = parent._is_fullscreen
                    break
                parent = parent.parentWidget()
            if is_fullscreen:
                self._toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key_F:
            self._toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key_Left:
            self._seek_relative(-5)
            event.accept()
        elif event.key() == Qt.Key_Right:
            self._seek_relative(5)
            event.accept()
        elif event.key() == Qt.Key_Up:
            self._adjust_volume(5)
            event.accept()
        elif event.key() == Qt.Key_Down:
            self._adjust_volume(-5)
            event.accept()
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
        if self._controls_visible and self._is_playing:
            self.top_bar.hide()
            self.bottom_bar.hide()
            self._controls_visible = False
            self.setCursor(QCursor(Qt.BlankCursor))

    def _start_hide_timer(self):
        if self._is_playing:
            self._hide_timer.start(3000)  # Hide after 3 seconds

    # === Playback Controls ===
    
    def _toggle_play(self):
        """Toggle play/pause."""
        if not self._vlc_player:
            return
        
        if self._is_playing:
            self._vlc_player.pause()
            self._show_controls()
        else:
            self._vlc_player.play()
            self._start_hide_timer()
            # Start polling if not already
            if not self._poll_timer.isActive():
                self._poll_timer.start()

    def _seek(self, percent: float):
        """Seek to position (0.0 to 1.0)."""
        if self._vlc_player and self._duration > 0:
            self._vlc_player.set_time(int(percent * self._duration))

    def _seek_relative(self, seconds: int):
        """Seek relative to current position."""
        if self._vlc_player:
            new_pos = self._vlc_player.get_time() + (seconds * 1000)
            new_pos = max(0, min(new_pos, self._duration))
            self._vlc_player.set_time(new_pos)

    def _set_volume(self, value: int):
        """Set volume (0-100)."""
        if self._vlc_player:
            # VLC volume: 0-100 normal, can go higher for amplification
            self._vlc_player.audio_set_volume(value)
            self._volume = value

    def _adjust_volume(self, delta: int):
        """Adjust volume by delta."""
        current = self.bottom_bar.volume_slider.value()
        new_vol = max(0, min(100, current + delta))
        self.bottom_bar.volume_slider.setValue(new_vol)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        parent = self.parentWidget()
        is_currently_fullscreen = False
        while parent:
            if hasattr(parent, '_is_fullscreen'):
                is_currently_fullscreen = parent._is_fullscreen
                break
            parent = parent.parentWidget()
        
        new_fullscreen = not is_currently_fullscreen
        print(f"VLC VideoPlayer requesting fullscreen: {'ON' if new_fullscreen else 'OFF'}")

        self.fullscreenToggled.emit(new_fullscreen)

        if not new_fullscreen:
            self._stop_playerbar_animation_now()
            QTimer.singleShot(100, self._fix_parent_layout)

    def _stop_playerbar_animation_now(self):
        """Immediately stop PlayerBar animation and reset to full visibility."""
        parent = self.parentWidget()
        while parent:
            if hasattr(parent, 'player_bar'):
                if hasattr(parent, '_playerbar_animation'):
                    parent._playerbar_animation.stop()
                if hasattr(parent, '_playerbar_opacity_effect'):
                    parent._playerbar_opacity_effect.setOpacity(1.0)
                parent.player_bar.show()
                break
            parent = parent.parentWidget()

    def _fix_parent_layout(self):
        """Fix parent layout after fullscreen exit."""
        parent = self.parentWidget()
        music_panel = None

        while parent:
            if hasattr(parent, 'player_bar'):
                music_panel = parent
                break
            parent = parent.parentWidget()

        if music_panel:
            current_size = music_panel.size()
            music_panel.resize(current_size.width(), current_size.height() - 1)
            QTimer.singleShot(50, lambda: self._restore_size(music_panel, current_size))

    def _restore_size(self, widget, original_size):
        """Restore original size after resize trick."""
        widget.resize(original_size)

        if hasattr(widget, '_playerbar_animation'):
            widget._playerbar_animation.stop()

        if hasattr(widget, 'player_bar'):
            widget.player_bar.setMaximumHeight(75)
            widget.player_bar.setFixedHeight(75)
            widget.player_bar.setMinimumHeight(75)
            widget.player_bar.show()

    def _set_aspect_ratio(self, mode: str):
        """Set video aspect ratio mode."""
        # VLC uses different aspect ratio settings
        # This is a simplified version - VLC has more complex aspect ratio control
        pass  # TODO: Implement VLC aspect ratio control

    # === Public API (same as VideoPlayerWidget) ===
    
    def set_title(self, title: str):
        """Set title in top bar."""
        self.top_bar.set_title(title)

    def play_file(self, path: str, title: str = None):
        """Load and play a video file using VLC."""
        # Initialize VLC on first use (deferred to avoid OpenGL conflict at startup)
        if not self._vlc_player or not self._vlc_instance:
            self._init_vlc()
            if not self._vlc_player or not self._vlc_instance:
                print("[VLC] Player not initialized")
                return
        
        try:
            # Create media
            media = self._vlc_instance.media_new(path)
            self._vlc_player.set_media(media)
            self._current_media_path = path
            
            # Attach video output
            self._attach_vlc_video()
            
            # Start playback
            self._vlc_player.play()
            
            # Start polling
            self._poll_timer.start()
            
            # Auto-load sidecar subtitles
            self._auto_load_sidecar_subtitles(path)
            
            if title:
                self.set_title(title)
            else:
                self.set_title(os.path.basename(path))
            
            print(f"[VLC] Playing: {path}")
            
        except Exception as e:
            print(f"[VLC] Failed to play file: {e}")

    def set_subtitle_file(self, subtitle_path: Optional[str]):
        """Load external subtitle file."""
        self._load_subtitles(subtitle_path)

    def clear_subtitles(self):
        """Clear all subtitles."""
        self._subtitle_cues = []
        self._subtitle_idx = -1
        self._subtitle_path = None
        self._subtitle_last_error = None
        self.subtitle_label_top.clear()
        self.subtitle_label_bottom.clear()

    def set_render_suspended(self, suspended: bool):
        """Suspend or resume rendering."""
        self._render_suspended = bool(suspended)
        
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
            self._subtitle_overlay_visible = False
            return
        
        try:
            if self.isVisible():
                self._subtitle_overlay.show()
                self._subtitle_overlay_timer.start()
        except Exception:
            pass
        self._update_subtitle_overlay_geometry()

    # === Subtitle Loading (copied from VideoPlayerWidget) ===
    
    def _auto_load_sidecar_subtitles(self, video_path: str):
        """Auto-load subtitle file with same name as video."""
        if not video_path:
            return
        
        base = os.path.splitext(video_path)[0]
        extensions = ['.srt', '.vtt', '.ass', '.ssa']
        
        for ext in extensions:
            sub_path = base + ext
            if os.path.exists(sub_path):
                self._load_subtitles(sub_path)
                return
        
        # Clear subtitles if no sidecar found
        self.clear_subtitles()

    def _load_subtitles(self, path: str):
        """Load subtitle file and parse cues."""
        if not path or not os.path.exists(path):
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                self._subtitle_last_error = str(e)
                return
        
        # Parse based on extension
        ext = os.path.splitext(path)[1].lower()
        
        if ext == '.srt':
            self._parse_srt(content)
        elif ext == '.vtt':
            self._parse_vtt(content)
        elif ext in ('.ass', '.ssa'):
            self._parse_ass(content)
        
        self._subtitle_path = path

    def _parse_srt(self, content: str):
        """Parse SRT subtitle format."""
        self._subtitle_cues = []
        self._subtitle_start_times = []
        
        # SRT pattern: index, timestamp, text
        pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\n|\n$|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            idx, start, end, text = match
            start_ms = self._parse_srt_timestamp(start)
            end_ms = self._parse_srt_timestamp(end)
            text = text.strip().replace('\n', ' ')
            
            self._subtitle_cues.append({
                'start': start_ms,
                'end': end_ms,
                'text': text
            })
            self._subtitle_start_times.append(start_ms)
        
        self._subtitle_idx = -1

    def _parse_srt_timestamp(self, ts: str) -> int:
        """Parse SRT timestamp to milliseconds."""
        parts = ts.replace(',', ':').split(':')
        h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        return h * 3600000 + m * 60000 + s * 1000 + ms

    def _parse_vtt(self, content: str):
        """Parse WebVTT subtitle format."""
        self._subtitle_cues = []
        self._subtitle_start_times = []
        
        # Remove header
        if 'WEBVTT' in content:
            content = content.split('WEBVTT', 1)[1]
        
        # VTT pattern: timestamp --> timestamp, text
        pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.*?)(?=\n\n|\n$|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            start, end, text = match
            start_ms = self._parse_vtt_timestamp(start)
            end_ms = self._parse_vtt_timestamp(end)
            text = text.strip().replace('\n', ' ')
            
            self._subtitle_cues.append({
                'start': start_ms,
                'end': end_ms,
                'text': text
            })
            self._subtitle_start_times.append(start_ms)
        
        self._subtitle_idx = -1

    def _parse_vtt_timestamp(self, ts: str) -> int:
        """Parse VTT timestamp to milliseconds."""
        parts = ts.replace('.', ':').split(':')
        h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        return h * 3600000 + m * 60000 + s * 1000 + ms

    def _parse_ass(self, content: str):
        """Parse ASS/SSA subtitle format."""
        self._subtitle_cues = []
        self._subtitle_start_times = []
        
        # Find dialogue lines
        for line in content.split('\n'):
            if line.startswith('Dialogue:'):
                parts = line.split(',', 9)
                if len(parts) >= 10:
                    start = self._parse_ass_timestamp(parts[1])
                    end = self._parse_ass_timestamp(parts[2])
                    text = parts[9].strip()
                    # Remove ASS formatting tags
                    text = re.sub(r'\{[^}]*\}', '', text)
                    text = re.sub(r'\\[Nn]', ' ', text)
                    
                    self._subtitle_cues.append({
                        'start': start,
                        'end': end,
                        'text': text
                    })
                    self._subtitle_start_times.append(start)
        
        self._subtitle_idx = -1

    def _parse_ass_timestamp(self, ts: str) -> int:
        """Parse ASS timestamp to milliseconds."""
        # ASS format: H:MM:SS.CC
        parts = ts.strip().split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        cs = int(s_parts[1]) if len(s_parts) > 1 else 0  # centiseconds
        
        return h * 3600000 + m * 60000 + s * 1000 + cs * 10

    def _update_subtitle(self, pos_ms: int):
        """Update subtitle display based on current position."""
        if not self._subtitle_cues:
            return
        
        # Binary search for current cue
        idx = bisect.bisect_right(self._subtitle_start_times, pos_ms) - 1
        
        if idx >= 0 and idx < len(self._subtitle_cues):
            cue = self._subtitle_cues[idx]
            if cue['start'] <= pos_ms <= cue['end']:
                if self._subtitle_idx != idx:
                    self._subtitle_idx = idx
                    self.subtitle_label_bottom.setText(cue['text'])
                    self.subtitle_label_top.clear()
                return
        
        # No cue active
        if self._subtitle_idx != -1:
            self._subtitle_idx = -1
            self.subtitle_label_bottom.clear()
            self.subtitle_label_top.clear()

    # === Subtitle Font Methods ===
    
    def set_subtitle_font_size(self, pt: int):
        """Set subtitle font size in points."""
        try:
            pt = int(pt)
        except Exception:
            return
        if pt < 8:
            pt = 8
        if pt > 48:
            pt = 48
        self.subtitle_label_bottom.set_font_point_size(pt)
        self.subtitle_label_top.set_font_point_size(pt)

    def get_subtitle_font_size(self) -> int:
        """Get subtitle font size in points."""
        try:
            return int(self.subtitle_label_bottom.get_font_point_size())
        except Exception:
            return 16

    def set_subtitle_font_variant(self, bold: bool, italic: bool):
        """Set subtitle font variant (bold/italic)."""
        self.subtitle_label_bottom.set_font_variant(bold, italic)
        self.subtitle_label_top.set_font_variant(bold, italic)

    def get_subtitle_font_variant(self):
        """Get subtitle font variant (bold, italic)."""
        return self.subtitle_label_bottom.get_font_variant()

    # === Compatibility Properties ===
    
    @property
    def video_widget(self):
        """Return the video widget for compatibility."""
        return self._video_widget
    
    @video_widget.setter
    def video_widget(self, value):
        self._video_widget = value


# Module exports
__all__ = ['VLCVideoPlayerWidget']
