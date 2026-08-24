"""
Native Qt Music Panel Widget

Exact replica of the HTML5 music panel design for consistency.
Matches the existing web/music_panel.html styling.

Component Name: MusicPanelWidget
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QStackedWidget, QSizePolicy, QAbstractItemView,
    QScrollArea, QLineEdit, QSpinBox, QSpacerItem,
    QDialog, QComboBox, QRadioButton, QButtonGroup, QCheckBox,
    QProgressBar, QGroupBox, QSplitter, QApplication, QToolButton,
    QStyledItemDelegate, QStyle, QMenu, QGraphicsDropShadowEffect
)
from AnimatedButton import FadeHoverButton, AnimatedButton
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, QPoint, QUrl, QThread, QSettings, QRect, Property, QEvent
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPalette, QCursor,
    QFontDatabase
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from MediaLibraryPage import MediaLibraryPage

import os
import sys
import json
import subprocess
import tempfile
import urllib.request
import hashlib
import time
from typing import Optional
from functools import partial

try:
    from PIL import Image, JpegImagePlugin, PngImagePlugin, WebPImagePlugin
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def trim_current_process_memory():
    """
    Instantly trim working set memory of HELXAID process.
    Releases unused pages (post-extraction/yt-dlp/FFmpeg setup) back to OS.
    """
    try:
        import gc
        gc.collect()
        if sys.platform == 'win32':
            import ctypes
            h_proc = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(h_proc)
    except Exception:
        pass



class FadingHandleSlider(QSlider):
    """Base slider with a handle that fades out after inactivity and fades in on hover."""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._handle_opacity = 0.0
        self._is_hovered = False
        self._is_pressed = False
        self._handle_color = QColor("#FF5B06")
        self._handle_hover_color = QColor("#FDA903")
        self._handle_size = 14
        
        self._anim = QPropertyAnimation(self, b"handleOpacity")
        self._anim.setDuration(200)
        
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(3000)
        self._hide_timer.timeout.connect(self._fade_out)
        
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)

    @Property(float)
    def handleOpacity(self):
        return self._handle_opacity

    @handleOpacity.setter
    def handleOpacity(self, value):
        self._handle_opacity = value
        self.update()
        
    def _fade_in(self):
        self._anim.stop()
        self._anim.setEndValue(1.0)
        self._anim.start()
        
    def _fade_out(self):
        if not self._is_hovered and not self._is_pressed:
            self._anim.stop()
            self._anim.setEndValue(0.0)
            self._anim.start()
            
    def enterEvent(self, event):
        self._is_hovered = True
        self._hide_timer.stop()
        self._fade_in()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self._is_hovered = False
        if not self._is_pressed:
            self._hide_timer.start()
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        self._is_pressed = True
        self._hide_timer.stop()
        self._fade_in()
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        self._is_pressed = False
        if not self._is_hovered:
            self._hide_timer.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._handle_opacity > 0:
            from PySide6.QtWidgets import QStyleOptionSlider, QStyle
            from PySide6.QtGui import QPainter, QBrush
            import PySide6.QtWidgets
            from PySide6.QtCore import QPoint
            from PySide6.QtGui import Qt
            
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            hr = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
            
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setOpacity(self._handle_opacity)
            
            color = self._handle_hover_color if self._is_hovered or self._is_pressed else self._handle_color
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            
            cx = hr.center().x()
            cy = hr.center().y()
            radius = self._handle_size / 2
            
            painter.drawEllipse(QPoint(cx, cy), radius, radius)
            painter.end()

class ClickSlider(FadingHandleSlider):
    """Custom slider that jumps to mouse click position."""
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            from PySide6.QtWidgets import QStyle, QStyleOptionSlider
            
            # Prepare style option for the slider
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            
            # Get the groove rectangle
            sr = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
            
            # Calculate position within the groove
            if self.orientation() == Qt.Horizontal:
                slider_length = sr.width()
                slider_pos = event.position().x() - sr.x()
            else:
                slider_length = sr.height()
                slider_pos = event.position().y() - sr.y()
            
            # Calculate value from 0 to 1 ratio
            if slider_length > 0:
                # Invert for vertical sliders as they are bottom-to-top
                if self.orientation() == Qt.Vertical:
                    ratio = 1.0 - (slider_pos / slider_length)
                else:
                    ratio = slider_pos / slider_length
                
                # Snap ratio to [0, 1]
                ratio = max(0.0, min(1.0, ratio))
                
                new_val = self.minimum() + int(ratio * (self.maximum() - self.minimum()))
                self.setValue(new_val)
                self.sliderMoved.emit(new_val)
                
        # Call base class to ensure sliderPressed and other logic still fires
        super().mousePressEvent(event)


class VolumeSlider(QSlider):
    """Custom slider with 5-step scroll increments for volume control."""
    
    def wheelEvent(self, event):
        """Handle mouse wheel with 5-step increments, snapping to multiples of 5."""
        delta = event.angleDelta().y()
        current = self.value()
        
        if delta > 0:  # Scroll up
            # Round up to next multiple of 5
            new_value = ((current // 5) + 1) * 5
        else:  # Scroll down
            # Round down to previous multiple of 5
            if current % 5 == 0:
                # Already at multiple of 5, go down by 5
                new_value = current - 5
            else:
                # Not at multiple, round down
                new_value = (current // 5) * 5
        
        # Clamp to range
        new_value = max(self.minimum(), min(self.maximum(), new_value))
        self.setValue(new_value)
        event.accept()


class MarqueeLabel(QLabel):
    """
    A label that scrolls text horizontally when it's too long.
    
    Component Name: MarqueeLabel
    """
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._offset = 0
        self._is_scrolling = False
        self._scroll_speed = 2  # pixels per tick
        self._pause_at_start = 30  # ticks to pause at start
        self._pause_counter = 0
        self._max_width = 180  # max display width
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.setInterval(50)  # 50ms = 20fps
        
        self.setFixedWidth(self._max_width)
    
    def setText(self, text: str):
        """Set text and start scrolling if needed."""
        self._full_text = text
        self._offset = 0
        self._pause_counter = self._pause_at_start
        
        # Check if text needs scrolling
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        
        if text_width > self._max_width - 10:
            # Text is too long, start marquee
            self._is_scrolling = True
            super().setText(text)
            if not self._timer.isActive():
                self._timer.start()
        else:
            # Text fits, no scrolling needed
            self._is_scrolling = False
            self._timer.stop()
            super().setText(text)
    
    def _scroll(self):
        """Animate the scroll."""
        if not self._is_scrolling:
            return
        
        # Pause at start
        if self._pause_counter > 0:
            self._pause_counter -= 1
            return
        
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._full_text)
        
        # Scroll
        self._offset += self._scroll_speed
        
        # Reset when fully scrolled
        if self._offset > text_width + 50:
            self._offset = 0
            self._pause_counter = self._pause_at_start
        
        self.update()
    
    def paintEvent(self, event):
        """Custom paint for scrolling text."""
        if not self._is_scrolling:
            super().paintEvent(event)
            return
        
        from PySide6.QtGui import QPainter
        
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.setFont(self.font())
        
        # Draw text at offset position
        y = (self.height() + painter.fontMetrics().ascent() - painter.fontMetrics().descent()) // 2
        painter.drawText(-self._offset, y, self._full_text)
        
        # Draw second copy for seamless loop
        text_width = painter.fontMetrics().horizontalAdvance(self._full_text)
        painter.drawText(-self._offset + text_width + 50, y, self._full_text)
        
        painter.end()


# ---- Universal Downloader Classes ----

def prepare_ytdlp_target(input_str: str) -> str:
    """If input is not a URL, format as a ytsearch query for yt-dlp."""
    s = (input_str or "").strip()
    if not s:
        return s
    if s.startswith(('http://', 'https://', 'www.')) or '://' in s:
        return s
    return f"ytsearch1:{s}"


class DownloadWorker(QThread):
    """
    Background worker for downloading YouTube content using yt-dlp.
    Handles both audio (MP3) and video (MP4) with quality selection.
    
    Component Name: DownloadWorker
    """
    progress = Signal(int)
    status   = Signal(str)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, url, out_dir, fmt, quality_idx, browser_cookies="None"):
        super().__init__()
        self.url = prepare_ytdlp_target(url)
        self.out_dir = out_dir
        self.fmt = fmt
        self.quality_idx = quality_idx
        self.browser_cookies = browser_cookies
        self._is_cancelled = False
        self._proc = None

    def cancel(self):
        """Abort the current download process."""
        self._is_cancelled = True
        if self._proc:
            if sys.platform == 'win32':
                import subprocess
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self._proc.pid)], 
                             capture_output=True, creationflags=0x08000000)
            else:
                self._proc.terminate()

    def get_f_str(self):
        """Map quality index to yt-dlp format strings."""
        if self.fmt == 'audio':
            # Audio Qualities: Best, High (256), Med (128), Low (64)
            q_map = ['bestaudio/best', 'bestaudio[abr<=256]', 'bestaudio[abr<=128]', 'bestaudio[abr<=64]']
            return q_map[min(self.quality_idx, len(q_map)-1)]
        else:
            # Video Qualities: BestAvailable, 1080p, 720p, 480p, 360p
            res_map = ['best', '1080', '720', '480', '360']
            res = res_map[min(self.quality_idx, len(res_map)-1)]
            if res == 'best':
                return 'bestvideo+bestaudio/best'
            return f'bestvideo[height<={res}]+bestaudio/best[height<={res}]/best'

    def run(self):
        """Execute the download in-process via yt-dlp Python API."""
        import os
        import sys
        
        self.downloaded_path = None
        
        try:
            import yt_dlp
            
            f_str = self.get_f_str()
            out_tmpl = os.path.join(self.out_dir, '%(title)s.%(ext)s')

            # If HELXAID bundles ffmpeg, tell yt-dlp explicitly so it can merge
            # separate video+audio streams into a single file.
            ffmpeg_location = None
            try:
                appdata = os.environ.get('APPDATA', '')
                helxaid_ffmpeg_bin = os.path.join(appdata, 'HELXAID', 'tools', 'ffmpeg', 'bin')
                if os.path.isdir(helxaid_ffmpeg_bin):
                    ffmpeg_location = helxaid_ffmpeg_bin
            except Exception:
                ffmpeg_location = None
            
            def progress_hook(d):
                if self._is_cancelled:
                    raise Exception("Download cancelled by user.")
                
                status_type = d.get('status')
                if status_type == 'downloading':
                    p_str = d.get('_percent_str', '').strip()
                    if p_str:
                        clean_p = p_str.replace('%', '').replace('"', '').strip()
                        try:
                            val = float(clean_p)
                            self.progress.emit(int(val))
                        except Exception:
                            pass
                        self.status.emit(f"[download] {p_str}")
                    
                    fn = d.get('filename')
                    if fn:
                        self.downloaded_path = fn
                elif status_type == 'finished':
                    fn = d.get('filename')
                    if fn:
                        self.downloaded_path = fn
                    self.status.emit("[download] 100%")

            ydl_opts = {
                'format': f_str,
                'outtmpl': out_tmpl,
                'nocheckcertificate': True,
                'noplaylist': True,
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
                'retries': 10,
                'fragment_retries': 10,
                'extractor_args': {'youtube': {'player_client': ['android', 'mweb', 'web']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
            }

            if ffmpeg_location:
                ydl_opts['ffmpeg_location'] = ffmpeg_location

            if getattr(self, 'browser_cookies', 'None').lower() != 'none':
                ydl_opts['cookiesfrombrowser'] = (self.browser_cookies.lower(),)

            if self.fmt == 'audio':
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '0',
                }]
                ydl_opts['keepvideo'] = False
            else:
                ydl_opts['merge_output_format'] = 'mp4'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info:
                    if isinstance(info, dict) and 'entries' in info:
                        entries = [e for e in info.get('entries', []) if isinstance(e, dict)]
                        if entries:
                            info = entries[0]
                    if 'requested_downloads' in info and info['requested_downloads']:
                        self.downloaded_path = info['requested_downloads'][0].get('filepath') or self.downloaded_path
                    elif '_filename' in info:
                        self.downloaded_path = info.get('_filename') or self.downloaded_path

            if self._is_cancelled:
                self.error.emit("Download cancelled by user.")
            else:
                print(f"[DEBUG DownloadWorker] Finished successfully. Captured path: {self.downloaded_path}")
                self.finished.emit(self.downloaded_path or "Download successful!")
                
        except Exception as e:
            if self._is_cancelled:
                self.error.emit("Download cancelled by user.")
            else:
                self.error.emit(str(e))


class MetadataWorker(QThread):
    """
    Worker for fetching media metadata and estimating file size before download.
    
    Component Name: MetadataWorker
    """
    metadata = Signal(dict)
    error    = Signal(str)

    def __init__(self, url, fmt, quality_idx, browser_cookies="None"):
        super().__init__()
        self.url = prepare_ytdlp_target(url)
        self.fmt = fmt
        self.quality_idx = quality_idx
        self.browser_cookies = browser_cookies
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        import os
        import sys
        
        if self._is_cancelled: return

        try:
            import yt_dlp
            
            dw = DownloadWorker(self.url, "", self.fmt, self.quality_idx, self.browser_cookies)
            f_str = dw.get_f_str()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'noplaylist': True,
                'format': f_str,
                'extract_flat': False,
                'extractor_args': {'youtube': {'player_client': ['android', 'mweb', 'web']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
            }
            if getattr(self, 'browser_cookies', 'None').lower() != 'none':
                ydl_opts['cookiesfrombrowser'] = (self.browser_cookies.lower(),)
                
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    if not self._is_cancelled:
                        self.error.emit("Failed to fetch meta.")
                    return

                # If query was a search string ('ytsearch1:...'), unpack first entry
                if isinstance(info, dict) and 'entries' in info:
                    entries = [e for e in info.get('entries', []) if isinstance(e, dict)]
                    if entries:
                        info = entries[0]
                
                title = info.get('title', 'Unknown Title')
                thumb_url = info.get('thumbnail', None)
                if not thumb_url and info.get('thumbnails'):
                    thumbnails = info.get('thumbnails')
                    if isinstance(thumbnails, list) and len(thumbnails) > 0:
                        thumb_url = thumbnails[-1].get('url')
                        
                val = info.get('filesize') or info.get('filesize_approx')
                if not val and info.get('requested_downloads'):
                    reqs = info.get('requested_downloads')
                    if isinstance(reqs, list) and reqs:
                        val = sum(r.get('filesize') or r.get('filesize_approx') or 0 for r in reqs if isinstance(r, dict))
                if not val and info.get('formats'):
                    for f in info.get('formats', []):
                        if isinstance(f, dict) and (f.get('filesize') or f.get('filesize_approx')):
                            val = f.get('filesize') or f.get('filesize_approx')
                            break
                if not val and info.get('duration'):
                    try:
                        dur = float(info.get('duration'))
                        bitrate = 320000 if self.fmt == 'audio' else 2500000
                        val = (dur * bitrate) / 8
                    except Exception:
                        pass

                size_raw = "Unknown"
                if val:
                    try:
                        val_num = float(val)
                        for unit in ['B','KB','MB','GB']:
                            if val_num < 1024:
                                size_raw = f"{val_num:.1f} {unit}"
                                break
                            val_num /= 1024
                    except Exception:
                        pass
                
                if not self._is_cancelled:
                    self.metadata.emit({
                        'title': title,
                        'thumb_url': thumb_url,
                        'size': size_raw
                    })
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))


class ImageLoader(QThread):
    """Async image downloader for previews."""
    loaded = Signal(bytes)
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        import urllib.request
        import ssl
        try:
            req = urllib.request.Request(
                self.url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                }
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = resp.read()
                if data:
                    self.loaded.emit(data)
        except Exception as e:
            print(f"[ImageLoader] Error loading thumbnail from {self.url}: {e}")


class SpinningLoader(QWidget):
    """Smooth animated spinning arc loading indicator for previews."""
    def __init__(self, parent=None, size=36):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._rotate)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()
        
    def start(self):
        self._angle = 0
        if not self._timer.isActive():
            self._timer.start()
        self.show()
        if self.parentWidget():
            self.raise_()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QColor
        from PySide6.QtCore import Qt, QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        margin = 4
        w = self.width() - margin * 2
        rect = QRectF(margin, margin, w, w)
        
        # Track ring
        pen_bg = QPen(QColor(255, 255, 255, 30), 3)
        p.setPen(pen_bg)
        p.drawEllipse(rect)
        
        # Rotating arc
        pen_arc = QPen(QColor(255, 255, 255, 230), 3)
        pen_arc.setCapStyle(Qt.RoundCap)
        p.setPen(pen_arc)
        
        p.drawArc(rect, -int(self._angle * 16), -int(100 * 16))


class PreviewCardFrame(QFrame):
    """Container frame for full-card thumbnail with title overlay and spinning loader."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumb_lbl = None
        self.overlay_widget = None
        self.spinner = SpinningLoader(self, size=36)
        self._on_resize_cb = None

    def set_resize_callback(self, cb):
        self._on_resize_cb = cb

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if self.thumb_lbl:
            self.thumb_lbl.setGeometry(0, 0, w, h)
        if self.overlay_widget:
            self.overlay_widget.setGeometry(0, 0, w, h)
            self.overlay_widget.raise_()
        if hasattr(self, 'spinner') and self.spinner:
            sw = self.spinner.width()
            sh = self.spinner.height()
            self.spinner.setGeometry((w - sw) // 2, (h - sh) // 2, sw, sh)
            if self.spinner.isVisible():
                self.spinner.raise_()
        if callable(self._on_resize_cb):
            self._on_resize_cb()





class ResponsiveAutoAddWidget(QWidget):
    """
    Responsive container for Auto-add options.
    Dynamically switches between single-line layout (wide panels)
    and multi-line layout (narrow panels) on resize.
    """
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._is_compact = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 2, 0, 2)
        self.main_layout.setSpacing(2)

        # Row 1 container
        self.row1_container = QWidget()
        self.row1_layout = QHBoxLayout(self.row1_container)
        self.row1_layout.setContentsMargins(0, 0, 0, 0)
        self.row1_layout.setSpacing(6)

        # Row 2 container (for narrow panel mode)
        self.row2_container = QWidget()
        self.row2_layout = QHBoxLayout(self.row2_container)
        self.row2_layout.setContentsMargins(22, 0, 0, 0)
        self.row2_layout.setSpacing(0)

        # Element 1: Toggle Checkbox
        from AnimatedButton import AnimatedCheckBox
        self.auto_add_cb = AnimatedCheckBox("Auto-add to")
        self.auto_add_cb.setCursor(Qt.PointingHandCursor)
        auto_add_enabled = self.settings.value("UniversalDownloader/auto_add_enabled", True, type=bool)
        self.auto_add_cb.setChecked(auto_add_enabled)

        # Element 2: Dropdown
        self.auto_add_target_combo = QComboBox()
        self.auto_add_target_combo.addItems(["Track Playlist", "Media Library"])
        self.auto_add_target_combo.setCursor(Qt.PointingHandCursor)

        saved_target = self.settings.value("UniversalDownloader/auto_add_target", "Track Playlist", type=str)
        t_idx = self.auto_add_target_combo.findText(saved_target)
        if t_idx >= 0:
            self.auto_add_target_combo.setCurrentIndex(t_idx)

        # Compact & Elegant Dropdown QSS Styling (HELXAIL Style)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        self.auto_add_target_combo.setFixedHeight(28)
        self.auto_add_target_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                color: #ffffff;
                padding: 2px 22px 2px 8px;
                font-size: 11px;
                font-weight: 500;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
            }
            QComboBox:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
            QComboBox:disabled {
                background-color: rgba(255, 255, 255, 0.02);
                color: #555555;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url('""" + icon_path + """');
                width: 10px;
                height: 10px;
            }
        """)

        try:
            from PySide6.QtGui import QPalette, QColor
            view = self.auto_add_target_combo.view()
            view.setAutoFillBackground(True)
            pal = view.palette()
            pal.setColor(QPalette.Base, QColor(18, 18, 26))
            pal.setColor(QPalette.Text, QColor(255, 255, 255))
            view.setPalette(pal)
            view.setStyleSheet("""
                QAbstractItemView {
                    background-color: #1a1a1a;
                    border: none;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 500;
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    selection-background-color: rgba(255, 255, 255, 0.12);
                    selection-color: #ffffff;
                    outline: 0;
                    padding: 4px;
                }
                QAbstractItemView::item {
                    min-height: 28px;
                    padding: 4px 10px;
                    border-radius: 6px;
                    background: transparent;
                }
                QAbstractItemView::item:hover,
                QAbstractItemView::item:selected {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #ffffff;
                }
            """)
        except Exception:
            pass

        # Element 3: Text Suffix
        self.lbl_after = QLabel("after download")
        self.lbl_after.setStyleSheet(f"color: {'#ffffff' if auto_add_enabled else '#555555'}; font-size: 11px; font-weight: normal; font-family: 'Orbitron', 'Segoe UI', sans-serif;")

        self.auto_add_target_combo.setEnabled(auto_add_enabled)

        def on_auto_add_toggled(checked):
            self.auto_add_target_combo.setEnabled(checked)
            self.lbl_after.setStyleSheet(f"color: {'#ffffff' if checked else '#555555'}; font-size: 11px; font-weight: normal; font-family: 'Orbitron', 'Segoe UI', sans-serif;")
            self.settings.setValue("UniversalDownloader/auto_add_enabled", checked)

        def on_target_changed(text):
            self.settings.setValue("UniversalDownloader/auto_add_target", text)

        self.auto_add_cb.toggled.connect(on_auto_add_toggled)
        self.auto_add_target_combo.currentTextChanged.connect(on_target_changed)

        self.main_layout.addWidget(self.row1_container)
        self.main_layout.addWidget(self.row2_container)

        # Apply initial layout based on current width (default to compact if small)
        self._apply_layout(is_compact=(self.width() < 280 if self.width() > 0 else True))

    def _apply_layout(self, is_compact: bool):
        if self._is_compact == is_compact:
            return
        self._is_compact = is_compact

        # Clear layouts safely
        while self.row1_layout.count():
            item = self.row1_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        while self.row2_layout.count():
            item = self.row2_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if is_compact:
            # Line 1: Checkbox + Dropdown
            self.row1_layout.addWidget(self.auto_add_cb)
            self.row1_layout.addWidget(self.auto_add_target_combo)
            self.row1_layout.addStretch()

            # Line 2: "after download" below (cleanly indented under checkbox text)
            self.row2_layout.addWidget(self.lbl_after)
            self.row2_layout.addStretch()
            self.row2_container.show()
        else:
            # Line 1: Checkbox + Dropdown + "after download"
            self.row1_layout.addWidget(self.auto_add_cb)
            self.row1_layout.addWidget(self.auto_add_target_combo)
            self.row1_layout.addWidget(self.lbl_after)
            self.row1_layout.addStretch()

            self.row2_container.hide()

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(150, 30)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(200, 32 if not self._is_compact else 54)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        if w < 280:
            self._apply_layout(is_compact=True)
        else:
            self._apply_layout(is_compact=False)


class YtScrollContentWidget(QWidget):
    """Custom content container with unconstrained minimum width to allow smooth splitter shrinking."""
    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(200, 100)


class UniversalDownloaderPanel(QFrame):
    """
    Integrated YouTube downloader panel that replaces the floating dialog.
    Matches the sleek dark design of HELXAID.
    
    Component Name: UniversalDownloaderPanel
    """
    downloadFinished = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ytDownloaderPanel")
        self._worker = None
        self._size_worker = None
        self._img_worker = None
        self._thread_graveyard = []  # Track workers that are still finishing tasks
        self._setup_ui()
        self._apply_style()

    def _cleanup_worker(self, attr_name):
        """Safely stop and delete a worker attribute."""
        worker = getattr(self, attr_name, None)
        if worker:
            # Clear reference first so any late signals can be ignored by guards
            setattr(self, attr_name, None)
            try:
                # Disconnect signals to stop callbacks; safe even if already disconnected
                worker.disconnect()
            except Exception:
                pass

            # Politely request cancellation if the worker supports it.
            try:
                if hasattr(worker, 'cancel'):
                    worker.cancel()
            except Exception:
                pass
                
            if hasattr(self, '_thread_graveyard'):
                self._thread_graveyard.append(worker)
                # Cleanup graveyard when thread actually finishes
                try:
                    worker.finished.connect(lambda w=worker: self._safe_remove_from_graveyard(w))
                except RuntimeError:
                    # Signal source has already been deleted
                    pass

    def _safe_remove_from_graveyard(self, worker):
        """Called when a worker in the graveyard finally finishes."""
        if hasattr(self, '_thread_graveyard') and worker in self._thread_graveyard:
            try:
                self._thread_graveyard.remove(worker)
                worker.deleteLater()
            except (ValueError, RuntimeError):
                pass

    def closeEvent(self, event):
        """Ensure all threads are killed when panel closes."""
        self._cleanup_worker('_worker')
        self._cleanup_worker('_size_worker')
        self._cleanup_worker('_img_worker')
        
        # Power-kill everything in graveyard on app close to prevent zombie yt-dlp
        if hasattr(self, '_thread_graveyard'):
            for w in self._thread_graveyard:
                try:
                    if hasattr(w, 'cancel'): w.cancel()
                    w.terminate()
                except:
                    pass
        super().closeEvent(event)

    def _setup_ui(self):
        self.setMinimumWidth(350)
        self.setMaximumWidth(450)
        # Master layout for the panel frame
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(0)

        # Content in a Scroll Area for small windowed mode
        from smooth_scroll import SmoothScrollArea
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        self.scroll_content = YtScrollContentWidget()
        self.scroll_content.setObjectName("ytScrollContent")
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(12)

        # Header with close button
        header_row = QHBoxLayout()
        title = QLabel("UNIVERSAL DOWNLOADER (BETA)")
        title.setStyleSheet("font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: 900; color: #ffffff; letter-spacing: 1px;")
        title.setWordWrap(True)
        title.setMinimumWidth(10)
        header_row.addWidget(title)
        
        header_row.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 20px; font-weight: bold; }
            QPushButton:hover { color: #ffffff; }
        """)
        close_btn.clicked.connect(self.closeRequested.emit)
        header_row.addWidget(close_btn, 0, Qt.AlignVCenter)
        layout.addLayout(header_row)

        # URL / Search input
        url_lbl = QLabel("LINK OR MEDIA NAME")
        url_lbl.setStyleSheet("color: #e0e0e0; font-size: 10px; font-weight: bold; letter-spacing: 1px; font-family: 'Orbitron', sans-serif;")
        layout.addWidget(url_lbl)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste URL or type media name...")
        self.url_edit.setMinimumWidth(10)
        layout.addWidget(self.url_edit)

        # ---- Preview Section (Thumbnail Card with Title Overlay) ----
        self.preview_section = PreviewCardFrame(self)
        self.preview_section.setObjectName("ytPreviewSection")
        self.preview_section.setFixedHeight(150)
        self.preview_section.setStyleSheet("""
            QFrame#ytPreviewSection {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        self.preview_section.hide()

        # Layer 0: Thumbnail Image (Filling full card background)
        self.thumb_lbl = QLabel(self.preview_section)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet("border-radius: 8px;")
        self.preview_section.thumb_lbl = self.thumb_lbl

        # Layer 1: Title Overlay at bottom with dark gradient (Created AFTER thumb_lbl to sit on top)
        self.overlay_widget = QWidget(self.preview_section)
        self.overlay_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.preview_section.overlay_widget = self.overlay_widget

        overlay_layout = QVBoxLayout(self.overlay_widget)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)
        overlay_layout.addStretch()

        title_box = QFrame()
        title_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(10, 10, 18, 0), stop:0.35 rgba(10, 10, 18, 0.8), stop:1 rgba(10, 10, 18, 0.98));
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        title_box_layout = QVBoxLayout(title_box)
        title_box_layout.setContentsMargins(12, 10, 12, 10)

        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold; font-family: 'Orbitron', sans-serif;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_box_layout.addWidget(self.title_lbl)

        overlay_layout.addWidget(title_box)
        self.preview_section.set_resize_callback(self._update_scaled_thumb)
        
        layout.addWidget(self.preview_section)

        # Format & Quality
        fmt_group = QFrame()
        fmt_group.setObjectName("ytModernGroup")
        fmt_layout = QVBoxLayout(fmt_group)
        fmt_layout.setContentsMargins(12, 12, 12, 12)
        fmt_layout.setSpacing(10)
        
        fmt_title = QLabel("FORMAT & QUALITY")
        fmt_title.setStyleSheet("color: #e0e0e0; font-size: 10px; font-weight: bold; letter-spacing: 1px; font-family: 'Orbitron', sans-serif;")
        fmt_layout.addWidget(fmt_title)
        
        rb_layout = QHBoxLayout()
        from AnimatedButton import AnimatedCheckBox
        self.rb_audio = AnimatedCheckBox("Audio (MP3)")
        self.rb_video = AnimatedCheckBox("Video (MP4)")
        self.rb_audio.setChecked(True)
        self.rb_audio.setCursor(Qt.PointingHandCursor)
        self.rb_video.setCursor(Qt.PointingHandCursor)
        
        self.fmt_btn_group = QButtonGroup(self)
        self.fmt_btn_group.addButton(self.rb_audio)
        self.fmt_btn_group.addButton(self.rb_video)
        self.fmt_btn_group.setExclusive(True)
        
        rb_layout.addWidget(self.rb_audio)
        rb_layout.addWidget(self.rb_video)
        rb_layout.addStretch()
        fmt_layout.addLayout(rb_layout)
        
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("ytQualityCombo")
        self.quality_combo.setCursor(Qt.PointingHandCursor)
        self.quality_combo.setMinimumHeight(34)
        fmt_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        self.quality_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 8px;
                padding: 4px 24px 4px 12px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 500;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
            }
            QComboBox:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url('""" + fmt_icon_path + """');
                width: 10px;
                height: 10px;
            }
        """)

        try:
            from PySide6.QtGui import QPalette, QColor
            view = self.quality_combo.view()
            view.setAutoFillBackground(True)
            pal = view.palette()
            pal.setColor(QPalette.Base, QColor(18, 18, 26))
            pal.setColor(QPalette.Text, QColor(255, 255, 255))
            view.setPalette(pal)
            view.setStyleSheet("""
                QAbstractItemView {
                    background-color: #1a1a1a;
                    border: none;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 500;
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    selection-background-color: rgba(255, 255, 255, 0.12);
                    selection-color: #ffffff;
                    outline: 0;
                    padding: 4px;
                }
                QAbstractItemView::item {
                    min-height: 28px;
                    padding: 4px 10px;
                    border-radius: 6px;
                    background: transparent;
                }
                QAbstractItemView::item:hover,
                QAbstractItemView::item:selected {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #ffffff;
                }
            """)
        except Exception:
            pass
        
        def update_opts():
            self.quality_combo.clear()
            if self.rb_audio.isChecked():
                self.quality_combo.addItems(["Best (320kbps)", "High (256kbps)", "Medium (128kbps)", "Low (64kbps)"])
            else:
                self.quality_combo.addItems(["Best Available", "1080p", "720p", "480p", "360p"])
                idx = self.quality_combo.findText("1080p")
                if idx >= 0:
                    self.quality_combo.setCurrentIndex(idx)
        
        self.rb_audio.toggled.connect(update_opts)
        update_opts()
        
        # Size Preview
        self.size_lbl = QLabel("Ready")
        self.size_lbl.setStyleSheet("color: #888; font-size: 11px; margin-top: 5px;")
        self.size_lbl.setWordWrap(True)
        
        fmt_layout.addWidget(self.quality_combo)
        fmt_layout.addWidget(self.quality_combo)
        fmt_layout.addWidget(self.size_lbl)
        layout.addWidget(fmt_group)

        # Output Folder
        folder_group = QFrame()
        folder_group.setObjectName("ytModernGroup")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(10)
        
        folder_title = QLabel("SAVE DIRECTORY")
        folder_title.setStyleSheet("color: #e0e0e0; font-size: 10px; font-weight: bold; letter-spacing: 1px; font-family: 'Orbitron', sans-serif;")
        folder_layout.addWidget(folder_title)
        
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setCursor(Qt.ArrowCursor)
        self.folder_edit.setMinimumWidth(10)
        settings = QSettings("TDD131", "HELXAID")
        last_dir = settings.value("UniversalDownloader/last_output_dir", "", type=str)
        if not last_dir:
            last_dir = settings.value("YouTubeDownloader/last_output_dir", "", type=str)
            if last_dir:
                settings.setValue("UniversalDownloader/last_output_dir", last_dir)
        default_path = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
        self.folder_edit.setText(last_dir or default_path)
        
        browse_btn = QToolButton()
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "folder-icon.svg").replace("\\", "/")
        browse_btn.setIcon(QIcon(icon_path))
        browse_btn.setIconSize(QSize(16, 16))
        browse_btn.setFixedSize(30, 30)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet("""
            QToolButton { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; }
            QToolButton:hover { background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.2); }
        """)
        
        def pick_folder():
            from PySide6.QtWidgets import QFileDialog
            start_dir = self.folder_edit.text().strip() or default_path
            d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
            if d:
                self.folder_edit.setText(d)
                settings.setValue("UniversalDownloader/last_output_dir", d)
        
        browse_btn.clicked.connect(pick_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse_btn)
        folder_layout.addLayout(folder_row)
        layout.addWidget(folder_group)

        # Browser Cookies Selection
        cookie_group = QFrame()
        cookie_group.setObjectName("ytModernGroup")
        cookie_layout = QVBoxLayout(cookie_group)
        cookie_layout.setContentsMargins(12, 12, 12, 12)
        cookie_layout.setSpacing(5)
        
        cookie_title = QLabel("COOKIES (LOGIN BYPASS)")
        cookie_title.setStyleSheet("color: #e0e0e0; font-size: 10px; font-weight: bold; letter-spacing: 1px; font-family: 'Orbitron', sans-serif;")
        cookie_layout.addWidget(cookie_title)
        
        cookie_desc = QLabel("Bypass age-restrictions or private videos by using your browser session.")
        cookie_desc.setStyleSheet("color: #888; font-size: 10px;")
        cookie_desc.setWordWrap(True)
        cookie_layout.addWidget(cookie_desc)
        
        self.cookie_combo = QComboBox()
        self.cookie_combo.addItems(["None", "Edge", "Chrome", "Firefox", "Brave", "Opera", "Vivaldi", "Safari"])
        self.cookie_combo.setCursor(Qt.PointingHandCursor)
        self.cookie_combo.setMinimumHeight(34)
        cookie_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        self.cookie_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 8px;
                padding: 4px 24px 4px 12px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 500;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
            }
            QComboBox:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url('""" + cookie_icon_path + """');
                width: 10px;
                height: 10px;
            }
        """)
        
        try:
            from PySide6.QtGui import QPalette, QColor
            view = self.cookie_combo.view()
            view.setAutoFillBackground(True)
            pal = view.palette()
            pal.setColor(QPalette.Base, QColor(18, 18, 26))
            pal.setColor(QPalette.Text, QColor(255, 255, 255))
            view.setPalette(pal)
            view.setStyleSheet("""
                QAbstractItemView {
                    background-color: #1a1a1a;
                    border: none;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 500;
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    selection-background-color: rgba(255, 255, 255, 0.12);
                    selection-color: #ffffff;
                    outline: 0;
                    padding: 4px;
                }
                QAbstractItemView::item {
                    min-height: 28px;
                    padding: 4px 10px;
                    border-radius: 6px;
                    background: transparent;
                }
                QAbstractItemView::item:hover,
                QAbstractItemView::item:selected {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #ffffff;
                }
            """)
        except Exception:
            pass
        
        saved_browser = settings.value("UniversalDownloader/browser_cookies", "None", type=str)
        idx = self.cookie_combo.findText(saved_browser)
        if idx >= 0:
            self.cookie_combo.setCurrentIndex(idx)
            
        def on_browser_changed(text):
            settings.setValue("UniversalDownloader/browser_cookies", text)
            
        self.cookie_combo.currentTextChanged.connect(on_browser_changed)
        cookie_layout.addWidget(self.cookie_combo)
        layout.addWidget(cookie_group)

        # Auto-add Option Responsive Row
        self.auto_add_widget = ResponsiveAutoAddWidget(settings, self)
        self.auto_add_cb = self.auto_add_widget.auto_add_cb
        self.auto_add_target_combo = self.auto_add_widget.auto_add_target_combo
        layout.addWidget(self.auto_add_widget)

        # Progress Section
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #888; font-size: 10px;")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        # Animation for fetching metadata
        from PySide6.QtCore import QTimer
        self._meta_anim_timer = QTimer(self)
        self._meta_anim_dots = 0
        self._meta_anim_timer.timeout.connect(self._animate_metadata_label)
        
        # Action Button
        self.download_btn = QPushButton("Start Download")
        self.download_btn.setObjectName("ytPanelDownloadBtn")
        self.download_btn.setFixedHeight(40)
        self.download_btn.setStyleSheet("""
            QPushButton#ytPanelDownloadBtn {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                padding: 10px 16px;
                font-family: 'Orbitron', sans-serif;
                font-weight: 700;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QPushButton#ytPanelDownloadBtn:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton#ytPanelDownloadBtn:pressed {
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPushButton#ytPanelDownloadBtn:focus { outline: 0; }
            QPushButton#ytPanelDownloadBtn:disabled { background-color: rgba(255, 255, 255, 0.03); color: #666; border-color: rgba(255,255,255,0.05); }
        """)
        self.download_btn.clicked.connect(self._start_download)
        layout.addWidget(self.download_btn)

        # Finalize Scroll Area
        self.scroll_area.setWidget(self.scroll_content)
        master_layout.addWidget(self.scroll_area)

        # Timer for size estimate
        self.size_timer = QTimer(self)
        self.size_timer.setSingleShot(True)
        self.size_timer.timeout.connect(self._update_size_estimate)
        self.url_edit.textChanged.connect(lambda: self.size_timer.start(800))
        
        # Debounce radio buttons too to avoid rapid-toggle hitch
        self.rb_audio.toggled.connect(lambda: self.size_timer.start(300))
        self.quality_combo.currentIndexChanged.connect(lambda: self.size_timer.start(300))

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#ytDownloaderPanel {
                background-color: transparent;
                border-left: 1px solid rgba(255, 255, 255, 0.05);
            }
            QLabel { color: #e0e0e0; background: transparent; }
            QLineEdit {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px; padding: 7px 10px; color: #fff; font-size: 12px;
            }
            QLineEdit:focus { border-color: rgba(255, 255, 255, 0.25); background: rgba(255, 255, 255, 0.07); }
            QFrame#ytModernGroup {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }
            
            QCheckBox {
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.25);
                background: rgba(255, 255, 255, 0.05);
            }
            QCheckBox::indicator:hover {
                border-color: rgba(255, 255, 255, 0.5);
                background: rgba(255, 255, 255, 0.1);
            }
            QCheckBox::indicator:checked {
                border: 1px solid rgba(255, 255, 255, 0.8);
                background: rgba(255, 255, 255, 0.2);
                image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
            }
            QComboBox {
                background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px; padding: 5px 10px; color: #e0e0e0;
            }
            QComboBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: rgba(255, 255, 255, 0.08);
            }
            QComboBox QAbstractItemView {
                background: #151519;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 8px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QRadioButton { color: #ccc; font-size: 12px; }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid rgba(255, 255, 255, 0.35);
                background: rgba(0, 0, 0, 0.25);
            }
            QRadioButton::indicator:hover {
                border-color: rgba(255, 255, 255, 0.6);
            }
            QRadioButton::indicator:checked {
                border-color: #ffffff;
                background: rgba(255, 255, 255, 0.3);
            }
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px;
                background: rgba(0, 0, 0, 0.4); text-align: center; color: #fff; height: 16px;
            }
            QProgressBar::chunk { background: rgba(255, 255, 255, 0.25); border-radius: 3px; }
            QPushButton#ytPanelDownloadBtn {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                padding: 10px 16px;
                font-family: 'Orbitron', sans-serif;
                font-weight: 700;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QPushButton#ytPanelDownloadBtn:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton#ytPanelDownloadBtn:pressed {
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPushButton#ytPanelDownloadBtn:focus { outline: 0; }
            QPushButton#ytPanelDownloadBtn:disabled { background-color: rgba(255, 255, 255, 0.03); color: #666; border-color: rgba(255,255,255,0.05); }
        """)

    def _update_size_estimate(self):
        url = self.url_edit.text().strip()
        
        # Basic validation: must have at least 2 characters
        if not url or len(url) < 2:
            if hasattr(self, '_meta_anim_timer'):
                self._meta_anim_timer.stop()
            self.size_lbl.setText("Ready")
            self.size_lbl.setStyleSheet("color: #888; font-size: 11px;")
            if hasattr(self.preview_section, 'spinner'):
                self.preview_section.spinner.stop()
            self.preview_section.hide()
            self.thumb_lbl.clear()
            self.title_lbl.clear()
            self._raw_thumb_pixmap = None
            self._cleanup_worker('_size_worker')
            self._cleanup_worker('_img_worker')
            return

        self._cleanup_worker('_size_worker')
        self._cleanup_worker('_img_worker')
        
        # Clear UI for fresh fetch
        self.thumb_lbl.clear()
        self._raw_thumb_pixmap = None
        self.title_lbl.setText("Resolving link...")
        self.preview_section.show()
        if hasattr(self.preview_section, 'spinner'):
            self.preview_section.spinner.start()
        if hasattr(self, 'overlay_widget') and self.overlay_widget:
            self.overlay_widget.raise_()
        if hasattr(self.preview_section, 'spinner'):
            self.preview_section.spinner.raise_()

        self._meta_anim_dots = 0
        self.size_lbl.setText("Fetching Metadata")
        if hasattr(self, '_meta_anim_timer'):
            self._meta_anim_timer.start(500)

        fmt = 'audio' if self.rb_audio.isChecked() else 'video'
        worker = MetadataWorker(url, fmt, self.quality_combo.currentIndex(), self.cookie_combo.currentText())
        self._size_worker = worker
        
        def on_meta(d):
            # Guard: Check if this worker is still the active one
            if self._size_worker != worker:
                return
            
            try:
                self.size_lbl.setText(f"Est. Size: {d.get('size', 'Unknown')}")
                self.title_lbl.setText(d.get('title', ''))
                self.preview_section.show()
                if hasattr(self, 'overlay_widget') and self.overlay_widget:
                    self.overlay_widget.raise_()
                
                # Fetch thumbnail if available
                thumb_url = d.get('thumb_url')
                if thumb_url:
                    self._cleanup_worker('_img_worker')
                    
                    img_worker = ImageLoader(thumb_url)
                    self._img_worker = img_worker
                    img_worker.loaded.connect(self._on_thumb_loaded)
                    img_worker.finished.connect(img_worker.deleteLater)
                    img_worker.start()
                else:
                    if hasattr(self.preview_section, 'spinner'):
                        self.preview_section.spinner.stop()
            except RuntimeError:
                pass

        worker.metadata.connect(on_meta)
        
        def on_error(err):
            if hasattr(self, '_meta_anim_timer'):
                self._meta_anim_timer.stop()
            self.size_lbl.setText("Meta: Failed")
            if hasattr(self.preview_section, 'spinner'):
                self.preview_section.spinner.stop()
            
        worker.error.connect(on_error)
        worker.start()

    def _animate_metadata_label(self):
        """Animates the size_lbl with dots while fetching metadata."""
        if not self.size_lbl.text().startswith("Fetching Metadata"):
            self._meta_anim_timer.stop()
            return
            
        self._meta_anim_dots = (self._meta_anim_dots + 1) % 4
        dots = "." * self._meta_anim_dots
        self.size_lbl.setText(f"Fetching Metadata{dots}")

    def _on_thumb_loaded(self, data):
        """Update thumbnail label with downloaded preview image filling full panel."""
        if hasattr(self.preview_section, 'spinner'):
            self.preview_section.spinner.stop()
        if not data:
            return
            
        try:
            if not self.isVisible():
                return
                
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self._raw_thumb_pixmap = pixmap
                self._update_scaled_thumb()
            else:
                # Fallback to PIL in case QPixmap fails on certain webp or image containers
                try:
                    import io
                    from PIL import Image
                    from PySide6.QtGui import QImage
                    im = Image.open(io.BytesIO(data))
                    im = im.convert('RGBA')
                    qimg = QImage(im.tobytes('raw', 'RGBA'), im.width, im.height, QImage.Format_RGBA8888)
                    pixmap = QPixmap.fromImage(qimg)
                    if not pixmap.isNull():
                        self._raw_thumb_pixmap = pixmap
                        self._update_scaled_thumb()
                except Exception as err:
                    print(f"[UniversalDownloader] Image fallback error: {err}")
        except (RuntimeError, AttributeError):
            pass

    def _update_scaled_thumb(self):
        if not getattr(self, '_raw_thumb_pixmap', None) or self._raw_thumb_pixmap.isNull():
            return
        card_w = self.preview_section.width()
        card_h = self.preview_section.height()
        if card_w > 10 and card_h > 10:
            scaled = self._raw_thumb_pixmap.scaled(card_w, card_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            crop_x = max(0, (scaled.width() - card_w) // 2)
            crop_y = max(0, (scaled.height() - card_h) // 2)
            cropped = scaled.copy(crop_x, crop_y, card_w, card_h)

            from PySide6.QtGui import QPainter, QPainterPath
            rounded = QPixmap(card_w, card_h)
            rounded.fill(Qt.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, card_w, card_h, 8, 8)
            p.setClipPath(path)
            p.drawPixmap(0, 0, cropped)
            p.end()

            self.thumb_lbl.setPixmap(rounded)
        else:
            self.thumb_lbl.setPixmap(self._raw_thumb_pixmap)

        if hasattr(self, 'overlay_widget') and self.overlay_widget:
            self.overlay_widget.raise_()

    def _start_download(self):
        url = self.url_edit.text().strip()
        if not url: return

        if self.download_btn.text() == "Stop":
            self._cleanup_worker('_worker')
            return

        fmt = 'audio' if self.rb_audio.isChecked() else 'video'
        out_dir = self.folder_edit.text().strip()
        if not out_dir: return
        
        self.download_btn.setText("Stop")
        self.progress_bar.setVisible(True)
        self.status_lbl.setVisible(True)
        self.progress_bar.setValue(0)
        
        self._cleanup_worker('_worker')
        worker = DownloadWorker(url, out_dir, fmt, self.quality_combo.currentIndex(), self.cookie_combo.currentText())
        self._worker = worker
        worker.progress.connect(self.progress_bar.setValue)
        worker.status.connect(lambda s: self.status_lbl.setText(s[-100:]))
        
        def on_done(msg):
            self._reset_ui()
            dest_file = msg
            print(f"[DEBUG UniversalDownloaderPanel] on_done received: {msg}")
            if not dest_file or not os.path.isfile(dest_file):
                try:
                    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
                    media_files = [f for f in files if os.path.isfile(f) and f.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.mp4', '.webm'))]
                    if media_files:
                        dest_file = max(media_files, key=os.path.getmtime)
                        print(f"[DEBUG UniversalDownloaderPanel] Resolved file via directory scan: {dest_file}")
                except Exception as ex:
                    print(f"[DEBUG UniversalDownloaderPanel] Directory scan error: {ex}")
            
            print(f"[DEBUG UniversalDownloaderPanel] Emitting downloadFinished with: {dest_file}")
            self.downloadFinished.emit(dest_file)
            self.status_lbl.setText("Done!")
            self._cleanup_worker('_worker')
        
        def on_err(msg):
            self._reset_ui()
            self.status_lbl.setText(f"Error: {msg}")
            self._cleanup_worker('_worker')
        
        worker.finished.connect(on_done)
        worker.error.connect(on_err)
        worker.start()

    def _reset_ui(self):
        self.download_btn.setText("Start Download")
        self.download_btn.setEnabled(True)

    def set_url(self, url):
        self.url_edit.setText(url)
        self.url_edit.setFocus()







class _CropCanvas(QWidget):
    """
    Custom canvas widget that draws a loaded image and renders an interactive
    1:1 (square) crop region on top of it.

    The crop region can be:
      - Dragged to move it across the image.
      - Resized by dragging any of the four corner handles while keeping the
        square aspect ratio intact.
      - Replaced entirely by click-dragging on an area outside the current
        crop rectangle (the new drag defines the new square from its diagonal).

    Internal coordinate system
    --------------------------
    All positions stored in this widget are in *canvas* coordinates (pixels
    relative to this widget's top-left corner).  `_image_rect` describes
    where the image is drawn (centered and letterboxed to fit the canvas).
    `_crop_rect` is the currently active square crop region.

    Component Name: _CropCanvas
    """

    # Signal emitted whenever the crop rect changes (for info label updates)
    cropChanged = Signal(object)  # passes the current QRect

    # Size of the draggable corner handle squares (px)
    HANDLE_SIZE = 10

    def __init__(self, pixmap: "QPixmap", parent=None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self._image_rect = None    # QRect: where the image is drawn on canvas
        self._crop_rect = None     # QRect: current square crop region (canvas coords)

        # Drag state machine
        # mode: None | 'move' | 'resize' | 'draw'
        self._drag_mode = None
        self._drag_start = None    # QPoint: mouse position at drag-start
        self._drag_orig_rect = None  # QRect: crop_rect at drag-start
        self._resize_corner = None   # int 0-3: which corner is being resized

        self.setMinimumSize(420, 360)
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _build_image_rect(self) -> "QRect":
        """
        Compute where the source pixmap should be drawn on this canvas so that
        it fills as much space as possible while preserving aspect ratio
        (letterboxed / pillarboxed to fit).

        Returns a QRect in canvas coordinates.
        """
        from PySide6.QtCore import QRect
        cw, ch = self.width(), self.height()
        img_w, img_h = self._source_pixmap.width(), self._source_pixmap.height()

        # Compute scale factor that fits image inside canvas
        scale = min(cw / img_w, ch / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)

        # Center within canvas
        x = (cw - draw_w) // 2
        y = (ch - draw_h) // 2
        return QRect(x, y, draw_w, draw_h)

    def _default_crop_rect(self, image_rect: "QRect") -> "QRect":
        """
        Return a square crop QRect centered on `image_rect`.
        The side length is the smaller of the image_rect's width and height so
        the initial crop covers as much of the image as possible.
        """
        from PySide6.QtCore import QRect
        side = min(image_rect.width(), image_rect.height())
        cx = image_rect.x() + (image_rect.width() - side) // 2
        cy = image_rect.y() + (image_rect.height() - side) // 2
        return QRect(cx, cy, side, side)

    def _corner_handle_rects(self) -> list:
        """
        Return a list of four QRect objects, one per corner of the current
        crop rect, for hit-testing and painting.  Order: TL, TR, BL, BR.
        """
        from PySide6.QtCore import QRect
        r = self._crop_rect
        hs = self.HANDLE_SIZE
        half = hs // 2
        return [
            QRect(r.left() - half,            r.top() - half,            hs, hs),  # 0: TL
            QRect(r.right() - half,           r.top() - half,            hs, hs),  # 1: TR
            QRect(r.left() - half,            r.bottom() - half,         hs, hs),  # 2: BL
            QRect(r.right() - half,           r.bottom() - half,         hs, hs),  # 3: BR
        ]

    def _clamp_crop_to_image(self, rect: "QRect") -> "QRect":
        """
        Clamp `rect` so it stays fully inside `_image_rect`.
        The rect's size is preserved; only position is adjusted.
        """
        from PySide6.QtCore import QRect
        ir = self._image_rect
        # 1. First clamp the square size to not exceed image bounds
        w = min(rect.width(), ir.width())
        h = min(rect.height(), ir.height())
        side = min(w, h)

        # 2. Then clamp position based on the adjusted size
        x = max(ir.left(), min(rect.x(), ir.right() - side))
        y = max(ir.top(), min(rect.y(), ir.bottom() - side))
        return QRect(x, y, side, side)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event):
        """Initialize image/crop rects on first show (size is known by now)."""
        super().showEvent(event)
        if self._image_rect is None or self._crop_rect is None:
            self._image_rect = self._build_image_rect()
            self._crop_rect = self._default_crop_rect(self._image_rect)
            self.cropChanged.emit(self._crop_rect)

    def resizeEvent(self, event):
        """
        Recalculate image rect when canvas is resized.  The crop rect is
        scaled proportionally so the user's selection feels stable.
        """
        super().resizeEvent(event)
        old_img = self._image_rect
        new_img = self._build_image_rect()

        if old_img and old_img.width() > 0 and old_img.height() > 0 and self._crop_rect:
            from PySide6.QtCore import QRect
            # Scale crop rect from old image space to new image space
            sx = new_img.width() / old_img.width()
            sy = new_img.height() / old_img.height()
            # Use uniform scale (image is square in canvas due to letterbox)
            scale = min(sx, sy)
            cx = new_img.x() + int((self._crop_rect.x() - old_img.x()) * sx)
            cy = new_img.y() + int((self._crop_rect.y() - old_img.y()) * sy)
            side = int(self._crop_rect.width() * scale)
            self._crop_rect = QRect(cx, cy, side, side)
        else:
            self._crop_rect = self._default_crop_rect(new_img)

        self._image_rect = new_img
        self.update()

    def paintEvent(self, event):
        """
        Render:
          1. The source image (scaled to fit canvas, letterboxed).
          2. Dark translucent mask outside the crop square.
          3. Bright #FF5B06 border around the crop square.
          4. White corner handles.
        """
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush
        from PySide6.QtCore import QRect

        if self._image_rect is None or self._crop_rect is None:
            self._image_rect = self._build_image_rect()
            self._crop_rect = self._default_crop_rect(self._image_rect)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. Draw background fill
        painter.fillRect(self.rect(), QColor(20, 20, 30))

        # 2. Draw the source image
        scaled_img = self._source_pixmap.scaled(
            self._image_rect.size(),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation
        )
        painter.drawPixmap(self._image_rect.topLeft(), scaled_img)

        # 3. Dark mask outside crop (4 rectangles around the crop square)
        mask_color = QColor(0, 0, 0, 160)
        ir = self._image_rect
        cr = self._crop_rect

        # Top strip
        painter.fillRect(QRect(ir.x(), ir.y(), ir.width(), cr.y() - ir.y()), mask_color)
        # Bottom strip
        painter.fillRect(QRect(ir.x(), cr.bottom(), ir.width(), ir.bottom() - cr.bottom()), mask_color)
        # Left strip (between top/bottom strips)
        painter.fillRect(QRect(ir.x(), cr.y(), cr.x() - ir.x(), cr.height()), mask_color)
        # Right strip (between top/bottom strips)
        painter.fillRect(QRect(cr.right(), cr.y(), ir.right() - cr.right(), cr.height()), mask_color)

        # 4. Crop border — brand orange #FF5B06
        pen = QPen(QColor(0xFF, 0x5B, 0x06), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(cr)

        # 5. Corner handles — white filled squares
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        for rect in self._corner_handle_rects():
            painter.drawRect(rect)

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        """
        Determine drag mode based on where the user clicked:
          - On a corner handle  → resize mode
          - Inside crop rect     → move mode
          - Elsewhere            → draw mode (define new square from drag)
        """
        from PySide6.QtCore import QRect
        pos = event.pos()

        if self._crop_rect is None:
            return

        # Check corner handles first (priority over move)
        for i, rect in enumerate(self._corner_handle_rects()):
            if rect.contains(pos):
                self._drag_mode = 'resize'
                self._resize_corner = i
                self._drag_start = pos
                self._drag_orig_rect = QRect(self._crop_rect)
                return

        if self._crop_rect.contains(pos):
            self._drag_mode = 'move'
            self._drag_start = pos
            self._drag_orig_rect = QRect(self._crop_rect)
        else:
            # Start drawing a new crop rect
            self._drag_mode = 'draw'
            self._drag_start = pos
            self._crop_rect = QRect(pos.x(), pos.y(), 0, 0)

    def mouseMoveEvent(self, event):
        """
        Handle in-progress drag based on current mode.

        Move mode: translate the crop rect by the delta since drag-start,
                   then clamp to image bounds.

        Resize mode: compute new side length from the dragged corner,
                     keeping the opposite corner fixed and enforcing square.

        Draw mode: expand a new square from the drag origin, clamped to
                   image bounds.  The square grows in all four directions
                   from the origin point to keep behaviour intuitive.
        """
        from PySide6.QtCore import QRect
        pos = event.pos()

        if self._drag_mode == 'move':
            dx = pos.x() - self._drag_start.x()
            dy = pos.y() - self._drag_start.y()
            new_rect = QRect(
                self._drag_orig_rect.x() + dx,
                self._drag_orig_rect.y() + dy,
                self._drag_orig_rect.width(),
                self._drag_orig_rect.height()
            )
            self._crop_rect = self._clamp_crop_to_image(new_rect)

        elif self._drag_mode == 'resize':
            orig = self._drag_orig_rect
            ir = self._image_rect

            # Compute new side from mouse distance; use max of dx/dy for diagonal drag
            if self._resize_corner == 0:    # Top-Left: fixed = BR
                new_x = max(ir.left(), min(pos.x(), orig.right() - 10))
                new_y = max(ir.top(),  min(pos.y(), orig.bottom() - 10))
                side = min(orig.right() - new_x, orig.bottom() - new_y)
                side = max(side, 10)
                self._crop_rect = QRect(orig.right() - side, orig.bottom() - side, side, side)

            elif self._resize_corner == 1:  # Top-Right: fixed = BL
                new_r = min(ir.right(), max(pos.x(), orig.left() + 10))
                new_y = max(ir.top(), min(pos.y(), orig.bottom() - 10))
                side = min(new_r - orig.left(), orig.bottom() - new_y)
                side = max(side, 10)
                self._crop_rect = QRect(orig.left(), orig.bottom() - side, side, side)

            elif self._resize_corner == 2:  # Bottom-Left: fixed = TR
                new_x = max(ir.left(), min(pos.x(), orig.right() - 10))
                new_b = min(ir.bottom(), max(pos.y(), orig.top() + 10))
                side = min(orig.right() - new_x, new_b - orig.top())
                side = max(side, 10)
                self._crop_rect = QRect(orig.right() - side, orig.top(), side, side)

            elif self._resize_corner == 3:  # Bottom-Right: fixed = TL
                new_r = min(ir.right(), max(pos.x(), orig.left() + 10))
                new_b = min(ir.bottom(), max(pos.y(), orig.top() + 10))
                side = min(new_r - orig.left(), new_b - orig.top())
                side = max(side, 10)
                self._crop_rect = QRect(orig.left(), orig.top(), side, side)

        elif self._drag_mode == 'draw':
            ir = self._image_rect
            if ir is None:
                return
            # Compute a square from drag_start to current pos, clamped to image
            x0 = self._drag_start.x()
            y0 = self._drag_start.y()
            dx = pos.x() - x0
            dy = pos.y() - y0
            
            # Find max room available in the drag direction
            room_x = (ir.right() - x0) if dx >= 0 else (x0 - ir.left())
            room_y = (ir.bottom() - y0) if dy >= 0 else (y0 - ir.top())
            
            # Side length = min of drag distance and available room
            side = min(max(abs(dx), abs(dy)), room_x, room_y)
            side = max(side, 10)
            
            # Determine top-left by direction of drag
            rx = x0 if dx >= 0 else x0 - side
            ry = y0 if dy >= 0 else y0 - side
            rect = QRect(rx, ry, side, side)
            self._crop_rect = self._clamp_crop_to_image(rect)

        self.cropChanged.emit(self._crop_rect)
        self.update()

    def mouseReleaseEvent(self, event):
        """Finalize drag — reset mode."""
        self._drag_mode = None
        self._drag_start = None
        self._drag_orig_rect = None
        self._resize_corner = None


class CoverCropDialog(QDialog):
    """
    Modal dialog that lets the user interactively select a square (1:1) crop
    region from an image before saving it as cover art.

    Layout
    ------
    - _CropCanvas  : fills most of the dialog; shows the image + drag handles
    - Info label   : shows current crop size in original image pixels
    - Instruction  : one-line usage hint
    - Accept / Cancel buttons

    Usage
    -----
    dialog = CoverCropDialog(pixmap, parent)
    if dialog.exec() == QDialog.Accepted:
        cropped_pixmap = dialog.get_cropped_pixmap()

    Component Name: CoverCropDialog
    """

    def __init__(self, pixmap: "QPixmap", parent=None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self.setWindowTitle("Crop Cover Art")
        self.setFixedSize(580, 540)
        self.setModal(True)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Build dialog layout: canvas, info label, instruction, buttons."""
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Canvas occupies the bulk of the dialog
        self._canvas = _CropCanvas(self._source_pixmap, self)
        self._canvas.cropChanged.connect(self._on_crop_changed)
        root.addWidget(self._canvas, stretch=1)

        # Info row: crop size in original image pixels
        info_row = QHBoxLayout()
        self._info_label = QLabel("Crop: —")
        self._info_label.setObjectName("cropInfoLabel")
        info_row.addWidget(self._info_label)
        info_row.addStretch()
        root.addLayout(info_row)

        # Instruction hint
        hint = QLabel("Drag to move  |  Drag corners to resize  |  Click outside crop to draw new")
        hint.setObjectName("cropHintLabel")
        root.addWidget(hint)

        # Accept / Cancel
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setObjectName("cropCancelBtn")
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_accept = QPushButton("Apply Crop")
        self._btn_accept.setObjectName("cropAcceptBtn")
        self._btn_accept.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_accept)
        root.addLayout(btn_row)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background: #1a1a2e;
            }
            QLabel {
                color: #c0c0c0;
                background: transparent;
                font-size: 12px;
            }
            QLabel#cropInfoLabel {
                color: #FF5B06;
                font-weight: bold;
                font-size: 12px;
            }
            QLabel#cropHintLabel {
                color: #666;
                font-size: 11px;
            }
            QPushButton#cropCancelBtn {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 5px;
                color: #aaa;
                padding: 7px 20px;
                font-size: 12px;
            }
            QPushButton#cropCancelBtn:hover {
                background: rgba(255,255,255,0.12);
                color: #fff;
            }
            QPushButton#cropAcceptBtn {
                background: #FF5B06;
                border: 1px solid rgba(255,91,6,0.6);
                border-radius: 5px;
                color: #fff;
                padding: 7px 20px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#cropAcceptBtn:hover {
                background: #FF7B26;
            }
            QPushButton#cropAcceptBtn:pressed {
                background: #E94F00;
            }
        """)

    def _on_crop_changed(self, canvas_rect):
        """
        Update the info label to show the crop size in original image pixels
        whenever the crop rectangle changes.

        Parameters
        ----------
        canvas_rect : QRect
            Current crop rectangle in canvas (widget) coordinates.
        """
        canvas = self._canvas
        ir = canvas._image_rect
        if ir is None or ir.width() == 0 or ir.height() == 0 or canvas_rect is None:
            return

        # Convert canvas crop size to original image pixels
        orig_w = self._source_pixmap.width()
        scale_x = orig_w / ir.width()
        pixel_size = int(canvas_rect.width() * scale_x)
        self._info_label.setText(f"Crop: {pixel_size} x {pixel_size} px")

    def get_cropped_pixmap(self) -> "QPixmap":
        """
        Map the current canvas-space crop rectangle back to original image
        coordinates and return the corresponding square crop as a QPixmap.

        The returned pixmap is cropped from the *full-resolution* source so
        no quality is lost at this stage.  Callers are responsible for
        further downscaling before saving.

        Returns
        -------
        QPixmap
            Square crop of the original image.  Never returns a null pixmap
            because the dialog can only be accepted when a valid crop exists.
        """
        canvas = self._canvas
        img_rect = canvas._image_rect      # QRect: image draw area on canvas
        crop_rect = canvas._crop_rect      # QRect: crop square in canvas coords

        if img_rect is None or img_rect.width() == 0:
            return self._source_pixmap

        orig_w = self._source_pixmap.width()
        orig_h = self._source_pixmap.height()

        # Scale factors: canvas px → original image px
        scale_x = orig_w / img_rect.width()
        scale_y = orig_h / img_rect.height()

        # Convert crop rect from canvas to original image coordinates
        rel_x = int((crop_rect.x() - img_rect.x()) * scale_x)
        rel_y = int((crop_rect.y() - img_rect.y()) * scale_y)
        crop_size = int(crop_rect.width() * scale_x)

        # Clamp to valid image bounds to prevent QPixmap.copy() from going OOB
        rel_x = max(0, min(rel_x, orig_w - 1))
        rel_y = max(0, min(rel_y, orig_h - 1))
        crop_size = max(1, min(crop_size, orig_w - rel_x, orig_h - rel_y))

        return self._source_pixmap.copy(rel_x, rel_y, crop_size, crop_size)


class FullscreenImageOverlay(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        from PySide6.QtGui import QGuiApplication
        screen = parent.screen() if parent and hasattr(parent, 'screen') and parent.screen() else QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGraphicsOpacityEffect
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("QFrame { background-color: rgba(0, 0, 0, 230); }")
        main_layout.addWidget(self.bg_frame)

        # Smooth Opacity Transition Effect
        self.opacity_effect = QGraphicsOpacityEffect(self.bg_frame)
        self.opacity_effect.setOpacity(0.0)
        self.bg_frame.setGraphicsEffect(self.opacity_effect)

        self._fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self._fade_anim.finished.connect(self._on_anim_finished)
        self._is_closing = False
        
        frame_layout = QHBoxLayout(self.bg_frame)
        frame_layout.setContentsMargins(50, 50, 50, 50)
        frame_layout.setSpacing(40)
        
        frame_layout.addStretch()
        
        # Left Close Label
        self.close_lbl_left = QLabel("Click here to close", self.bg_frame)
        self.close_lbl_left.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; background: transparent;")
        self.close_lbl_left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.close_lbl_left.setCursor(Qt.PointingHandCursor)
        frame_layout.addWidget(self.close_lbl_left)
        
        self.img_lbl = QLabel(self.bg_frame)
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setStyleSheet("background: transparent;")
        
        if pixmap and not pixmap.isNull():
            if screen:
                geom = screen.geometry()
                w = int(geom.width() * 0.60)
                h = int(geom.height() * 0.85)
                self.img_lbl.setPixmap(pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        frame_layout.addWidget(self.img_lbl)
        
        # Right Close Label
        self.close_lbl_right = QLabel("Click here to close", self.bg_frame)
        self.close_lbl_right.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; background: transparent;")
        self.close_lbl_right.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.close_lbl_right.setCursor(Qt.PointingHandCursor)
        frame_layout.addWidget(self.close_lbl_right)
        
        frame_layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        self._fade_anim.stop()
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def _start_close_transition(self):
        if self._is_closing:
            return
        self._is_closing = True
        self._fade_anim.stop()
        self._fade_anim.setDuration(160)
        self._fade_anim.setStartValue(self.opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self._fade_anim.start()

    def _on_anim_finished(self):
        if self._is_closing:
            super().accept()
        
    def mousePressEvent(self, event):
        if self._is_closing:
            return
        child = self.childAt(event.pos())
        if child == self.img_lbl:
            return
        self._start_close_transition()
        
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space):
            if not self._is_closing:
                self._start_close_transition()
                event.accept()
                return
        super().keyPressEvent(event)

    def done(self, r):
        super().done(r)
        if self.parent():
            self.parent().activateWindow()
            self.parent().raise_()
            self.parent().setFocus()


class RoundedImageLabel(QLabel):
    def __init__(self, radius=8, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._radius = radius
        self._border_width = 1
        from PySide6.QtGui import QColor
        self._border_color = QColor("#444444")
        self._bg_color = QColor("#2a2a3a")
        
    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        from PySide6.QtGui import QPixmap
        super().setPixmap(QPixmap())  # Clear native pixmap so we draw custom
        self.update()
        
    def clear(self):
        self._pixmap = None
        super().clear()
        self.update()
        
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPainterPath, QBrush, QPen
        from PySide6.QtCore import Qt, QRectF
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = QRectF(self.rect()).adjusted(
            self._border_width/2, self._border_width/2, 
            -self._border_width/2, -self._border_width/2
        )
        
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        
        painter.fillPath(path, QBrush(self._bg_color))
        
        if self._pixmap and not self._pixmap.isNull():
            painter.setClipPath(path)
            scaled = self._pixmap.scaled(self.rect().size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled)
            painter.setClipping(False)
            
        pen = QPen(self._border_color, self._border_width)
        painter.setPen(pen)
        painter.drawPath(path)
        
        super().paintEvent(event)


class InteractiveCoverLabel(QFrame):
    """
    Glass card containing a single cover preview (Front or Back),
    action overlay, directory path, and explore button.

    Component Name: InteractiveCoverLabel
    """
    clicked_signal = Signal()
    remove_clicked_signal = Signal()
    folder_clicked_signal = Signal()

    def __init__(self, title, action_text, parent=None):
        super().__init__(parent)
        self.setObjectName("interactiveCoverCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.action_text = action_text
        self._current_pixmap = None

        self.setStyleSheet("""
            QFrame#interactiveCoverCard {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#coverTitleLabel {
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                letter-spacing: 0.5px;
            }
            QLabel#coverDirLabel {
                color: #8a8d98;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                background: transparent;
            }
            QLineEdit#coverPathEdit {
                background: rgba(0, 0, 0, 0.4);
                color: #d0d0d0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                padding: 2px 6px;
            }
            QToolButton#coverFolderBtn {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
                padding: 0px;
                margin: 0px;
            }
            QToolButton#coverFolderBtn:hover {
                background: rgba(255, 91, 6, 0.35);
                border: 1px solid rgba(255, 91, 6, 0.8);
            }
            QToolButton#coverFolderBtn:disabled {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.04);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("coverTitleLabel")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # Image Container
        self.img_container = QWidget()
        self.img_container.setObjectName("coverImgContainer")
        self.img_container.setFixedSize(170, 170)

        self.img_lbl = RoundedImageLabel(radius=10, parent=self.img_container)
        self.img_lbl.setObjectName("coverRoundedImg")
        self.img_lbl.setGeometry(0, 0, 170, 170)

        self.overlay = QLabel(self.img_container)
        self.overlay.setObjectName("coverActionOverlay")
        self.overlay.setGeometry(0, 0, 170, 170)
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setText(self.action_text)
        self.overlay.hide()
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet("""
            QLabel#coverActionOverlay {
                background: rgba(8, 8, 12, 0.78);
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                font-weight: bold;
                font-size: 11px;
                border-radius: 10px;
                border: 1px solid rgba(255, 91, 6, 0.6);
            }
        """)

        if self.action_text:
            self.img_container.setCursor(Qt.PointingHandCursor)
            self.img_container.mousePressEvent = self._on_press
            self.img_container.installEventFilter(self)

        layout.addWidget(self.img_container, alignment=Qt.AlignCenter)

        # Directory row
        dir_layout = QHBoxLayout()
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)
        dir_lbl = QLabel("Directory:")
        dir_lbl.setObjectName("coverDirLabel")
        dir_lbl.setFixedHeight(24)

        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("coverPathEdit")
        self.path_edit.setReadOnly(True)
        self.path_edit.setFixedHeight(24)
        self.path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.path_edit.setCursor(Qt.ArrowCursor)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        folder_icon_path = os.path.join(script_dir, "UI Icons", "folder-icon-white.svg").replace("\\", "/")

        self.folder_btn = QToolButton()
        self.folder_btn.setObjectName("coverFolderBtn")
        self.folder_btn.setFixedSize(24, 24)
        self.folder_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.folder_btn.setIcon(QIcon(folder_icon_path))
        self.folder_btn.setIconSize(QSize(14, 14))
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.setToolTip("Pick File" if action_text == "Edit" else "Open Folder in Explorer")
        self.folder_btn.clicked.connect(self.folder_clicked_signal.emit)
        self.folder_btn.setEnabled(False)

        dir_layout.addWidget(dir_lbl, 0)
        dir_layout.addWidget(self.path_edit, 1)
        dir_layout.addWidget(self.folder_btn, 0)

        layout.addLayout(dir_layout)

    def _on_press(self, event):
        if event.button() == Qt.LeftButton:
            self.overlay.hide()
            if self._current_pixmap and not self._current_pixmap.isNull() and self.action_text == "Edit":
                if event.pos().y() > self.img_container.height() / 2:
                    self.remove_clicked_signal.emit()
                else:
                    self.clicked_signal.emit()
            else:
                self.clicked_signal.emit()

    def eventFilter(self, obj, event):
        if obj == self.img_container and self.action_text:
            if event.type() == QEvent.Enter:
                self.overlay.show()
            elif event.type() == QEvent.Leave:
                self.overlay.hide()
        return super().eventFilter(obj, event)

    def set_content(self, pixmap, source_path):
        self._current_pixmap = pixmap
        if pixmap and not pixmap.isNull():
            self.img_lbl.setPixmap(pixmap)
            if self.action_text == "Edit":
                self.overlay.setText("Edit\n\n\nRemove")
        else:
            self.img_lbl.clear()
            self.img_lbl.setText("No Cover")
            self.img_lbl.setAlignment(Qt.AlignCenter)
            if self.action_text == "Edit":
                self.overlay.setText("Add")

        self.path_edit.setText(source_path)
        self.path_edit.setCursorPosition(0)  # Reset scroll
        self.folder_btn.setEnabled(bool(source_path))

    def _open_folder(self):
        """Review Mode only action. Opens the file's containing folder."""
        path = self.path_edit.text()
        if path and os.path.exists(path):
            try:
                subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            except Exception as e:
                print(f"[Cover] Error opening explorer: {e}")

    @property
    def current_path(self):
        return self.path_edit.text()


class CoverManagerDialog(QDialog):
    """
    Glassmorphism Floating Panel Dialog for Reviewing and Editing Album/Track Covers.
    
    Component Name: CoverManagerDialog
    """
    def __init__(self, mode, front_path, back_path, front_source='', back_source='', parent=None):
        super().__init__(parent)
        self.mode = mode
        self.front_path = front_path
        self.back_path = back_path
        self.front_source = front_source
        self.back_source = back_source
        
        self.new_front_pixmap = None
        self.new_back_pixmap = None
        self.new_front_source = front_source
        self.new_back_source = back_source
        self.reset_all = False

        self._is_dragging = False
        self._drag_start_pos = QPoint()

        self.setObjectName("CoverManagerDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(560, 430)

        # Smooth Open & Close Window Opacity Animation
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._is_closing = False
        self._close_action = "reject"
        self.setWindowOpacity(0.0)

        # Outer Layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # Glass Container
        self.container = QFrame(self)
        self.container.setObjectName("coverManagerContainer")
        self.container.setStyleSheet("""
            QFrame#coverManagerContainer {
                background-color: rgba(14, 15, 20, 0.97);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QWidget#coverManagerTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#coverManagerTitleLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 0.5px;
            }
            QPushButton#coverManagerCloseBtn {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton#coverManagerCloseBtn:hover {
                background: rgba(255, 255, 255, 0.08);
            }
        """)

        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        outer_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Title Bar
        self.title_bar = QWidget()
        self.title_bar.setObjectName("coverManagerTitleBar")
        self.title_bar.setFixedHeight(44)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(14, 0, 10, 0)
        title_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        panel_icon_path = os.path.join(script_dir, "UI Icons", "display-icon.svg").replace('\\', '/')
        close_icon_path = os.path.join(script_dir, "UI Icons", "close-icon-white.svg").replace('\\', '/')

        icon_lbl = QLabel()
        icon_lbl.setObjectName("coverManagerIconLabel")
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setScaledContents(True)
        if os.path.exists(panel_icon_path):
            icon_lbl.setPixmap(QPixmap(panel_icon_path))
        title_layout.addWidget(icon_lbl)

        dialog_title = "REVIEW IMAGES" if mode == 'review' else "EDIT COVERS"
        title_lbl = QLabel(dialog_title)
        title_lbl.setObjectName("coverManagerTitleLabel")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()

        container_layout.addWidget(self.title_bar)

        # Content Area
        content_widget = QWidget()
        content_widget.setObjectName("coverManagerContentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(16)

        # Covers Layout
        covers_layout = QHBoxLayout()
        covers_layout.setSpacing(14)
        is_edit = (self.mode == 'edit')
        action_text = "Edit" if is_edit else "Show at Fullscreen"

        self.front_lbl = InteractiveCoverLabel("Front Cover", action_text=action_text)
        self.front_lbl.setObjectName("frontCoverCard")
        self.front_lbl.clicked_signal.connect(lambda: self._handle_click('front'))
        self.front_lbl.remove_clicked_signal.connect(lambda: self._handle_remove('front'))
        self.front_lbl.folder_clicked_signal.connect(lambda: self._handle_folder_click('front'))

        self.back_lbl = InteractiveCoverLabel("Back Cover", action_text=action_text)
        self.back_lbl.setObjectName("backCoverCard")
        self.back_lbl.clicked_signal.connect(lambda: self._handle_click('back'))
        self.back_lbl.remove_clicked_signal.connect(lambda: self._handle_remove('back'))
        self.back_lbl.folder_clicked_signal.connect(lambda: self._handle_folder_click('back'))

        covers_layout.addWidget(self.front_lbl)
        covers_layout.addWidget(self.back_lbl)
        content_layout.addLayout(covers_layout)

        # Initial content loading
        self._load_initial_contents()

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        if self.mode == 'review':
            btn_layout.addStretch()
            self.close_action_btn = FadeHoverButton("Close", border_radius=6.0, is_secondary=True)
            self.close_action_btn.setObjectName("coverManagerReviewCloseBtn")
            self.close_action_btn.setFixedSize(110, 36)
            self.close_action_btn.clicked.connect(self.reject)
            btn_layout.addWidget(self.close_action_btn)
        else:
            self.reset_btn = FadeHoverButton("Reset to Defaults", border_radius=6.0, color_mode="red")
            self.reset_btn.setObjectName("coverManagerResetBtn")
            self.reset_btn.setFixedSize(170, 36)
            self.reset_btn.clicked.connect(self._reset_covers)
            btn_layout.addWidget(self.reset_btn)

            btn_layout.addStretch()

            self.cancel_btn = FadeHoverButton("Cancel", border_radius=6.0, is_secondary=True)
            self.cancel_btn.setObjectName("coverManagerCancelBtn")
            self.cancel_btn.setFixedSize(100, 36)
            self.cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(self.cancel_btn)

            self.apply_btn = FadeHoverButton("Save & Apply", border_radius=6.0, is_secondary=False)
            self.apply_btn.setObjectName("coverManagerApplyBtn")
            self.apply_btn.setFixedSize(140, 36)
            self.apply_btn.clicked.connect(self.accept)
            btn_layout.addWidget(self.apply_btn)

        content_layout.addLayout(btn_layout)
        container_layout.addWidget(content_widget)

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        self._fade_anim.stop()
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def accept(self):
        self._start_close_animation("accept")

    def reject(self):
        self._start_close_animation("reject")

    def _start_close_animation(self, action="reject"):
        if self._is_closing:
            return
        self._is_closing = True
        self._close_action = action
        self._fade_anim.stop()
        self._fade_anim.setDuration(140)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self._fade_anim.start()

    def _on_fade_finished(self):
        if self._is_closing:
            if self._close_action == "accept":
                super().accept()
            else:
                super().reject()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            title_rect = self.title_bar.rect()
            title_mapped = self.title_bar.mapTo(self, title_rect.topLeft())
            drag_area = QRect(title_mapped, self.title_bar.size())
            click_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if drag_area.contains(click_pos):
                self._is_dragging = True
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self._drag_start_pos = global_pos - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(global_pos - self._drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F12:
            main_window = self.parent()
            while main_window and not hasattr(main_window, '_trigger_inspector'):
                main_window = main_window.parent()
            if main_window and hasattr(main_window, '_trigger_inspector'):
                main_window._trigger_inspector()
            else:
                self._trigger_dialog_inspector()
            event.accept()
            return
        elif event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def _trigger_dialog_inspector(self):
        """Component Inspector handler inside modal CoverManagerDialog."""
        cursor_pos = QCursor.pos()
        widget = QApplication.widgetAt(cursor_pos)
        if not widget:
            pos = self.mapFromGlobal(cursor_pos)
            widget = self.childAt(pos)
        if widget:
            hierarchy = []
            w = widget
            while w:
                name = w.objectName() or "(no name)"
                hierarchy.append(f"{w.__class__.__name__}#{name}")
                w = w.parent()

            widget_type = widget.__class__.__name__
            component_name = widget.objectName() or widget_type
            selector_text = f"{widget_type}#{widget.objectName()}" if widget.objectName() else f"<{widget_type}: set objectName first>"
            info = f"""Component Inspector

Component: {component_name}
Widget Type: {widget_type}
Object Name: {widget.objectName() or '(not set)'}
Size: {widget.width()} x {widget.height()}

Hierarchy (child \u2192 parent):
{chr(10).join(f"  {i}. {h}" for i, h in enumerate(hierarchy[:6]))}

Stylesheet Selector:
  {selector_text}
"""
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Component Inspector (F12) - HELXAID")
            msg.setText(info)
            msg.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            QApplication.clipboard().setText(info)
            msg.addButton("Copy Info", QMessageBox.ActionRole)
            msg.addButton(QMessageBox.Ok)
            msg.exec()


    def _load_initial_contents(self):
        f_pix = QPixmap(self.front_path) if self.front_path else None
        b_pix = QPixmap(self.back_path) if self.back_path else None
        self.front_lbl.set_content(f_pix, self.front_path)
        self.back_lbl.set_content(b_pix, self.back_path)

    def _reset_covers(self):
        self.reset_all = True
        self.new_front_pixmap = None
        self.new_back_pixmap = None
        self.new_front_source = ''
        self.new_back_source = ''
        self.front_lbl.set_content(None, "")
        self.back_lbl.set_content(None, "")

    def _handle_remove(self, target):
        self.reset_all = False
        if target == 'front':
            self.new_front_pixmap = "REMOVED"
            self.new_front_source = ''
            self.front_lbl.set_content(None, "")
        else:
            self.new_back_pixmap = "REMOVED"
            self.new_back_source = ''
            self.back_lbl.set_content(None, "")

    def _handle_click(self, target):
        if self.mode == 'edit':
            # CLICK IMAGE (Edit) = CROP current source (Priority: High-Res Source)
            lbl = self.front_lbl if target == 'front' else self.back_lbl
            source = self.new_front_source if target == 'front' else self.new_back_source
            
            # Use high-res source if available and exists, else fallback to current display path (cropped)
            path = source if source and os.path.exists(source) else lbl.current_path
            
            if path and os.path.exists(path):
                self._pick_and_crop(target, path)
            else:
                # Fallback to picker if no image is present (default cover)
                self._handle_folder_click(target)
        else:
            # Mode review: Show Fullscreen Overlay
            lbl = self.front_lbl if target == 'front' else self.back_lbl
            lbl.overlay.hide()
            pixmap = lbl._current_pixmap
            if pixmap and not pixmap.isNull():
                overlay = FullscreenImageOverlay(pixmap, self)
                overlay.showFullScreen()
                overlay.exec()
                self.activateWindow()
                self.raise_()
                self.setFocus()

    def _handle_folder_click(self, target):
        if self.mode == 'edit':
            # CLICK FOLDER BUTTON = PICK NEW SOURCE
            path = self._open_file_picker(target)
            if path:
                self._pick_and_crop(target, path)
        else:
            # Mode review: Open explorer location
            lbl = self.front_lbl if target == 'front' else self.back_lbl
            lbl._open_folder()

    def _open_file_picker(self, target):
        from PySide6.QtWidgets import QFileDialog

        IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif *.ico);;All Files (*)"
        last_dir = ""
        settings_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json')
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    last_dir = json.load(f).get('last_cover_dir', '')
        except Exception:
            pass

        path, _ = QFileDialog.getOpenFileName(self, f"Select {target.capitalize()} Cover Source", last_dir, IMAGE_FILTER)
        if not path or not os.path.exists(path):
            return ""
            
        # Save new directory memory
        try:
            d = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
            d['last_cover_dir'] = os.path.dirname(path)
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
        return path

    def _pick_and_crop(self, target, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
            
        max_size = 2048
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Show Crop Dialog
        dialog = CoverCropDialog(pixmap, self)
        if dialog.exec() == QDialog.Accepted:
            cropped = dialog.get_cropped_pixmap()
            if not cropped or cropped.isNull():
                return
            
            self.reset_all = False
            if target == 'front':
                self.new_front_pixmap = cropped
                self.new_front_source = path
                self.front_lbl.set_content(cropped, path)
            else:
                self.new_back_pixmap = cropped
                self.new_back_source = path
                self.back_lbl.set_content(cropped, path)

    def get_changes(self):
        return {
            'reset': self.reset_all,
            'front': self.new_front_pixmap,
            'back': self.new_back_pixmap,
            'front_source': self.new_front_source,
            'back_source': self.new_back_source
        }


class PlaylistHeader(QFrame):
    """
    Playlist header matching HTML5 design.
    
    Component Name: PlaylistHeader
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistHeader")

        # Per-playlist cover paths (populated by _pick_cover / load_saved_cover)
        self._cover_front_path = ''
        self._cover_back_path = ''
        self._cover_front_source = ''
        self._cover_back_source = ''

        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 20)
        layout.setSpacing(20)

        # Build the 120x120 cover container using the dedicated helper
        cover_container = self._setup_cover_container()
        layout.addWidget(cover_container)

        # Playlist info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        self.playlist_label = QLabel("PLAYLIST")
        self.playlist_label.setObjectName("playlistLabel")

        self.playlist_title = QLabel("My Playlist")
        self.playlist_title.setObjectName("playlistTitle")

        self.playlist_stats = QLabel("0 Media · 0:00:00")
        self.playlist_stats.setObjectName("playlistStats")

        info_layout.addStretch()
        info_layout.addWidget(self.playlist_label)
        info_layout.addWidget(self.playlist_title)
        info_layout.addWidget(self.playlist_stats)
        info_layout.addStretch()

        layout.addLayout(info_layout, stretch=1)

        # No settings button here - moved to menu bar

    def _setup_cover_container(self) -> QWidget:
        """
        Build and return the 120x120 cover-art container widget.

        Contains:
          - cover_back   (QLabel, 90x90, offset to top-right)
          - cover_front  (QLabel, 100x100, overlaps back)
          - _cover_edit_overlay  (QLabel, full-size, hidden by default)
            Shown on mouse-enter; displays a semi-transparent tint with
            'Edit' text to signal that the covers are clickable/editable.

        Mouse routing:
          - Left  button  -> _pick_cover('front')  (most common action)
          - Right button  -> context menu: Change Front / Change Back / Reset

        An event filter is installed on the container so we can detect
        QEvent.Enter / QEvent.Leave for the hover overlay without
        subclassing QWidget.
        """
        container = QWidget()
        container.setObjectName("coverContainer")
        container.setFixedSize(120, 120)

        # Back cover (moved right and up to clearly look like a vinyl sleeve/back album)
        self.cover_back = RoundedImageLabel(radius=6, parent=container)
        self.cover_back.setObjectName("coverBack")
        self.cover_back.setGeometry(25, 5, 85, 85)
        self.cover_back.setCursor(Qt.PointingHandCursor)
        self.cover_back.setToolTip("Left-click: Edit Covers")

        # Front cover (slightly smaller so back cover is heavily visible)
        self.cover_front = RoundedImageLabel(radius=6, parent=container)
        self.cover_front.setObjectName("coverFront")
        self.cover_front.setGeometry(0, 20, 95, 95)
        self.cover_front.setCursor(Qt.PointingHandCursor)
        self.cover_front.setToolTip("Left-click: Edit Covers")
        
        # Add a subtle drop shadow to ground the front cover and make layers pop
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setOffset(3, 3)
        shadow.setColor(Qt.black)
        self.cover_front.setGraphicsEffect(shadow)

        # Edit overlay (shown on hover over container)
        self._cover_edit_overlay = QLabel(container)
        self._cover_edit_overlay.setObjectName("coverEditOverlay")
        self._cover_edit_overlay.setGeometry(0, 0, 120, 120)
        self._cover_edit_overlay.setStyleSheet("background: rgba(0, 0, 0, 0.7); border-radius: 8px; border: none;")
        self._cover_edit_overlay.setAlignment(Qt.AlignCenter)
        self._cover_edit_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        edit_icon_path = os.path.join(script_dir, "UI Icons", "edit.svg").replace("\\", "/")
        self._cover_edit_overlay.setPixmap(QIcon(edit_icon_path).pixmap(28, 28))
        self._cover_edit_overlay.show()
        
        # Setup opacity effect for fade in/out
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self._cover_edit_effect = QGraphicsOpacityEffect(self._cover_edit_overlay)
        self._cover_edit_effect.setOpacity(0.0)
        self._cover_edit_overlay.setGraphicsEffect(self._cover_edit_effect)
        
        self._cover_fade_in = QPropertyAnimation(self._cover_edit_effect, b"opacity", self)
        self._cover_fade_in.setDuration(200)
        self._cover_fade_in.setEndValue(1.0)
        
        self._cover_fade_out = QPropertyAnimation(self._cover_edit_effect, b"opacity", self)
        self._cover_fade_out.setDuration(250)
        self._cover_fade_out.setEndValue(0.0)
        
        # Install event filter to detect hover specifically on the container
        container.installEventFilter(self)

        # Route mouse button presses to _on_cover_mousepress
        self.cover_back.mousePressEvent = self._on_cover_mousepress
        self.cover_front.mousePressEvent = self._on_cover_mousepress

        self._cover_container = container
        return container

    def eventFilter(self, obj, event):
        """Handle hover overlay on front cover."""
        if obj == self._cover_container:
            if event.type() == QEvent.Enter:
                self._cover_edit_overlay.show()
                self._cover_fade_out.stop()
                self._cover_fade_in.setStartValue(self._cover_edit_effect.opacity())
                self._cover_fade_in.start()
            elif event.type() == QEvent.Leave:
                self._cover_fade_in.stop()
                self._cover_fade_out.setStartValue(self._cover_edit_effect.opacity())
                self._cover_fade_out.start()
        return super().eventFilter(obj, event)
    def _apply_style(self):
        self.setStyleSheet("""
            QWidget#coverContainer {
                background: transparent;
            }
            
            QFrame#playlistHeader {
                background: transparent;
            }
            
            QLabel#coverBack {
                background: #2a2a3a;
                border-radius: 8px;
                border: 1px solid #444444;
            }
            
            QLabel#coverFront {
                background: #3a3a4a;
                border-radius: 8px;
                border: 1px solid #FF5B06;
            }
            
            QLabel#playlistLabel {
                color: #888888;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            
            QLabel#playlistTitle {
                color: #ffffff;
                font-size: 32px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
            }
            
            QLabel#playlistStats {
                color: #888888;
                font-size: 13px;
            }
            
            QPushButton#settingsBtn {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 20px;
            }
            QPushButton#settingsBtn:hover {
                background: rgba(255, 91, 6, 0.25);
            }
        """)
    
    def set_info(self, name: str, track_count: int, total_duration: str):
        self._name = name # Store name for metadata refresh callbacks
        self.playlist_title.setText(name)
        self.playlist_stats.setText(f"{track_count} Media · {total_duration}")
    
    def set_covers(self, cover1_path: str, cover2_path: str):
        """Set cover art images. cover1 = back cover, cover2 = front cover."""
        # Guard against identical path updates to prevent heavy pixmap reloads/stutters
        if getattr(self, '_last_cover1', None) == cover1_path and \
           getattr(self, '_last_cover2', None) == cover2_path:
            return
            
        self._last_cover1 = cover1_path
        self._last_cover2 = cover2_path

        if cover1_path and os.path.exists(cover1_path):
            pixmap = QPixmap(cover1_path)
            self.cover_back.setPixmap(pixmap)
        
        if cover2_path and os.path.exists(cover2_path):
            pixmap = QPixmap(cover2_path)
            self.cover_front.setPixmap(pixmap)
    
    def _on_cover_mousepress(self, event):
        """
        Route mouse button events on the cover container:
          - Left button  → Show context menu for managing covers.
          - Right button → Ignored.
        """
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        
        if event.button() == Qt.LeftButton:
            menu = QMenu(self)
            menu.addAction("Review Images", lambda: self._open_cover_manager('review'))
            menu.addAction("Edit images", lambda: self._open_cover_manager('edit'))
            menu.exec(QCursor.pos())

    def _open_cover_manager(self, mode: str):
        """
        Instantiate and show the CoverManagerDialog. Handle its result.
        """
        dialog = CoverManagerDialog(
            mode, 
            self._cover_front_path, self._cover_back_path,
            self._cover_front_source, self._cover_back_source,
            self
        )
        from PySide6.QtWidgets import QDialog
        if dialog.exec() == QDialog.Accepted:
            changes = dialog.get_changes()
            playlist_name = getattr(self, '_name', '') or (self.playlist_title.text() if hasattr(self, 'playlist_title') else '') or 'My Playlist'
            if not playlist_name:
                playlist_name = 'My Playlist'

            if changes.get('reset'):
                self._reset_covers()
                return

            changed = False
            
            # Apply Front Cover changes
            f_pix = changes.get('front')
            if f_pix == "REMOVED":
                if os.path.exists(self._cover_front_path):
                    try: os.remove(self._cover_front_path)
                    except Exception: pass
                self._cover_front_path = ''
                self._cover_front_source = ''
                self.cover_front.clear()
                changed = True
            elif f_pix is not None:
                saved_path = self._save_cropped_cover(f_pix, 'front')
                if saved_path:
                    self._cover_front_path = saved_path
                    self._cover_front_source = changes.get('front_source', '')
                    self.cover_front.setPixmap(
                        f_pix.scaled(95, 95, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    changed = True
                    
            # Apply Back Cover changes
            b_pix = changes.get('back')
            if b_pix == "REMOVED":
                if os.path.exists(self._cover_back_path):
                    try: os.remove(self._cover_back_path)
                    except Exception: pass
                self._cover_back_path = ''
                self._cover_back_source = ''
                self.cover_back.clear()
                changed = True
            elif b_pix is not None:
                saved_path = self._save_cropped_cover(b_pix, 'back')
                if saved_path:
                    self._cover_back_path = saved_path
                    self._cover_back_source = changes.get('back_source', '')
                    self.cover_back.setPixmap(
                        b_pix.scaled(85, 85, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    changed = True

            # If edits were made, persist the UI setting
            if changed:
                self._save_cover_setting(
                    playlist_name,
                    self._cover_front_path,
                    self._cover_back_path,
                    self._cover_front_source,
                    self._cover_back_source
                )

    def _save_cropped_cover(self, pixmap: "QPixmap", target: str) -> str:
        """
        Save a square QPixmap to APPDATA/HELXAID/covers/{slug}_{target}.png
        at a fixed 512x512 resolution.

        512x512 provides sufficient quality for the 90-100 px display labels
        without excessive disk usage.  Re-picking an image overwrites the
        previous file for the same playlist and target.

        Parameters
        ----------
        pixmap : QPixmap
            Square pixmap as returned by CoverCropDialog.get_cropped_pixmap().
        target : str
            'front' or 'back' — used as the filename suffix.

        Returns
        -------
        str
            Absolute path of the saved PNG file, or '' on failure.
        """
        import re
        covers_dir = os.path.join(
            os.environ.get('APPDATA', ''), 'HELXAID', 'covers'
        )
        os.makedirs(covers_dir, exist_ok=True)

        name = getattr(self, '_name', 'playlist')
        # Sanitize playlist name so it is safe to use as part of a filename.
        # Replace any character that is not alphanumeric, underscore, or dash.
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:40] or 'playlist'

        out_path = os.path.join(covers_dir, f"{slug}_{target}.png")
        scaled = pixmap.scaled(
            512, 512, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        if scaled.save(out_path, "PNG"):
            return out_path

        print(f"[Cover] Failed to save cropped cover to: {out_path}")
        return ''

    def _reset_covers(self):
        """
        Clear both cover labels back to the default blank placeholder state
        and remove the persisted paths from settings.json for this playlist.
        """
        self._cover_front_path = ''
        self._cover_back_path = ''
        self._cover_front_source = ''
        self._cover_back_source = ''
        self.cover_front.clear()
        self.cover_back.clear()
        playlist_name = getattr(self, '_name', '') or (self.playlist_title.text() if hasattr(self, 'playlist_title') else '') or 'My Playlist'
        if playlist_name:
            self._save_cover_setting(playlist_name, '', '', '', '')
            if playlist_name == 'My Playlist':
                self._save_cover_setting('__default__', '', '', '', '')

    def _save_cover_setting(
        self, playlist_name: str, front_path: str, back_path: str, 
        front_source: str = '', back_source: str = ''
    ):
        """
        Persist the front and back cover paths to APPDATA/HELXAID/settings.json.
        Also syncs __default__ fallback so custom covers persist seamlessly.

        Storage schema::

            settings['playlist_covers'][playlist_name] = {
                'front': '/absolute/path/to/front.png',
                'back':  '/absolute/path/to/back.png',
                'front_source': '/path/to/original.jpg',
                'back_source':  '/path/to/original.png'
            }

        Parameters
        ----------
        playlist_name : str
            Playlist display name used as the dictionary key.
        front_path : str
            Absolute path to the front cover PNG, or '' to clear.
        back_path : str
            Absolute path to the back cover PNG, or '' to clear.
        front_source : str
            Absolute path to original source file for front cover.
        back_source : str
            Absolute path to original source file for back cover.
        """
        import json
        settings_path = os.path.join(
            os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json'
        )
        try:
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            covers = settings.setdefault('playlist_covers', {})
            cover_entry = {
                'front': front_path, 
                'back': back_path,
                'front_source': front_source,
                'back_source': back_source
            }
            covers[playlist_name] = cover_entry
            
            # Sync to __default__ fallback if on 'My Playlist' or if __default__ has no front/back
            if playlist_name == 'My Playlist' or '__default__' not in covers or not (covers['__default__'].get('front') or covers['__default__'].get('back')):
                covers['__default__'] = dict(cover_entry)

            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Cover] Failed to save cover setting: {e}")

    def load_saved_cover(self, playlist_name: str = ''):
        """
        Restore previously saved cover images for this playlist on load with hierarchical fallback.

        Resolution Order:
          1. Exact match for `playlist_name` in settings['playlist_covers'].
          2. Global fallback key `__default__` or `My Playlist`.
          3. Any first valid custom cover entry in settings['playlist_covers'].
          4. Default placeholder (clear labels).

        Parameters
        ----------
        playlist_name : str, optional
            Playlist display name used to look up the saved entry. If empty,
            uses current title or 'My Playlist'.
        """
        import json
        settings_path = os.path.join(
            os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json'
        )

        # Reset in-memory paths before loading
        self._cover_front_path = ''
        self._cover_back_path = ''
        self._cover_front_source = ''
        self._cover_back_source = ''

        try:
            if not os.path.exists(settings_path):
                self.cover_front.clear()
                self.cover_back.clear()
                return
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            covers_map = settings.get('playlist_covers', {})
            if not isinstance(covers_map, dict) or not covers_map:
                self.cover_front.clear()
                self.cover_back.clear()
                return

            lookup_name = playlist_name or getattr(self, '_name', '') or (self.playlist_title.text() if hasattr(self, 'playlist_title') else '') or 'My Playlist'

            def _extract_paths(entry):
                if not entry:
                    return None, None, '', ''
                if isinstance(entry, str):
                    if os.path.exists(entry):
                        return entry, entry, '', ''
                    return None, None, '', ''
                elif isinstance(entry, dict):
                    f_p = entry.get('front', '')
                    b_p = entry.get('back', '')
                    f_src = entry.get('front_source', '')
                    b_src = entry.get('back_source', '')
                    f_valid = f_p if (f_p and os.path.exists(f_p)) else None
                    b_valid = b_p if (b_p and os.path.exists(b_p)) else None
                    if f_valid or b_valid:
                        return f_valid, b_valid, f_src, b_src
                return None, None, '', ''

            # Tier 1: Exact match
            front_path, back_path, front_source, back_source = _extract_paths(covers_map.get(lookup_name))

            # Tier 2: Global default / fallback ('__default__', 'My Playlist')
            if not front_path and not back_path:
                front_path, back_path, front_source, back_source = _extract_paths(covers_map.get('__default__'))
            if not front_path and not back_path:
                front_path, back_path, front_source, back_source = _extract_paths(covers_map.get('My Playlist'))

            # Tier 3: First available valid custom cover entry
            if not front_path and not back_path:
                for k, entry in covers_map.items():
                    fp, bp, fs, bs = _extract_paths(entry)
                    if fp or bp:
                        front_path, back_path, front_source, back_source = fp, bp, fs, bs
                        break

            # Tier 4: No valid covers anywhere
            if not front_path and not back_path:
                self.cover_front.clear()
                self.cover_back.clear()
                return

            self._cover_front_path = front_path or ''
            self._cover_back_path  = back_path or ''
            self._cover_front_source = front_source or ''
            self._cover_back_source = back_source or ''

            if front_path:
                pix = QPixmap(front_path)
                self.cover_front.setPixmap(
                    pix.scaled(95, 95, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                self.cover_front.clear()

            if back_path:
                pix = QPixmap(back_path)
                self.cover_back.setPixmap(
                    pix.scaled(85, 85, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                self.cover_back.clear()

        except Exception as e:
            print(f"[Cover] Failed to load saved cover: {e}")


class PlaylistTable(QWidget):
    """
    Playlist table using QTreeWidget to support folders.
    
    Component Name: PlaylistTable
    """
    
    trackDoubleClicked = Signal(int)
    sortChanged = Signal(str, bool)  # column, ascending
    deleteSelected = Signal(list)
    deleteAll = Signal()
    flattenGroup = Signal(str)
    
    # Context menu media addition signals
    addFileRequested = Signal()
    addMultipleFilesRequested = Signal()
    addFolderRequested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistTableContainer")
        self._tracks = []
        self._current_index = -1
        self._sort_column = "title"
        self._sort_ascending = True
        self._sorted_indices = []  # Stores sorted order of original indices
        self._click_count = 0
        self._last_clicked_item = None
        self._setup_ui()
    
    def _setup_ui(self):
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
        from smooth_scroll import SmoothTableWidget
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create tree
        self.tree = QTreeWidget()
        self.tree.setObjectName("playlistTree")
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["#", "Title", "Date Added", "Duration"])
        
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection) # Allow multiple delete
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSortingEnabled(False)  # We handle sorting manually
        self.tree.setFocusPolicy(Qt.ClickFocus)
        from MediaLibraryPage import NoFocusDelegate
        self.tree.setItemDelegate(NoFocusDelegate(self.tree))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(False) # Manual handling for triple click
        self.tree.setRootIsDecorated(False) # Hide expand arrows for cleaner look
        self.tree.setIndentation(12) # Reduce indent to prevent text clipping
        
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        orig_playlist_keyPressEvent = self.tree.keyPressEvent
        def _playlist_keyPressEvent(event):
            if event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
                self.select_all()
                event.accept()
                return
            elif event.key() == Qt.Key_Delete:
                self._on_delete_selected()
                event.accept()
                return
            orig_playlist_keyPressEvent(event)
        self.tree.keyPressEvent = _playlist_keyPressEvent

        # --- Rubber Band Setup ---
        from PySide6.QtWidgets import QRubberBand
        from PySide6.QtCore import QRect
        self.tree._rubber_band = QRubberBand(QRubberBand.Rectangle, self.tree.viewport())
        self.tree._rubber_band_origin = None
        self.tree._rubber_band_active = False
        
        orig_mousePressEvent = self.tree.mousePressEvent
        orig_mouseMoveEvent = self.tree.mouseMoveEvent
        orig_mouseReleaseEvent = self.tree.mouseReleaseEvent
        orig_mouseDoubleClickEvent = self.tree.mouseDoubleClickEvent
        
        from PySide6.QtCore import QTimer
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        
        def _on_click_timeout():
            if self._click_count == 2:
                item = getattr(self, '_last_clicked_item', None)
                try:
                    if item and item.data(0, Qt.UserRole) == "folder":
                        item.setExpanded(not item.isExpanded())
                except RuntimeError:
                    pass
            
            self._click_count = 0
            self._last_clicked_item = None
            
        self._click_timer.timeout.connect(_on_click_timeout)

        def _tree_mousePressEvent(event):
            if event.button() == Qt.LeftButton:
                self.tree._click_start_pos = event.pos()
                item = self.tree.itemAt(event.pos())
                column = self.tree.columnAt(event.pos().x())
                
                should_rubber_band = False
                if not item or column == -1:
                    should_rubber_band = True
                elif column >= 2:
                    should_rubber_band = True
                else:
                    from PySide6.QtGui import QFontMetrics
                    font = item.font(column) if item.font(column).family() else self.tree.font()
                    fm = QFontMetrics(font)
                    text_width = fm.horizontalAdvance(item.text(column))
                    
                    cell_x = self.tree.header().sectionPosition(column)
                    depth = 0
                    p = item.parent()
                    while p:
                        depth += 1
                        p = p.parent()
                        
                    indent = 0
                    if column == 0:
                        indent = depth * self.tree.indentation() + 24
                        
                    if event.pos().x() > (cell_x + indent + text_width + 30):
                        should_rubber_band = True
                        
                if item and item.isSelected():
                    should_rubber_band = False
                
                if should_rubber_band:
                    self.tree._rubber_band_origin = event.pos()
                    self.tree._rubber_band.setGeometry(QRect(self.tree._rubber_band_origin, self.tree._rubber_band_origin))
                    self.tree._rubber_band.show()
                    self.tree._rubber_band_active = True
                    self.tree._rubber_band_dragged = False
                    
                    if not item and not (event.modifiers() & Qt.ControlModifier):
                        self.tree.clearSelection()
                        self._update_item_selection_styles()
                        
                    orig_mousePressEvent(event)
                    return
                else:
                    self.tree._rubber_band_active = False
                
                if not self._click_timer.isActive():
                    self._click_count = 1
                    self._last_clicked_item = item
                    self._click_timer.start(500)
                else:
                    self._click_count += 1
                    
                if self._click_count >= 3:
                    self._click_timer.stop()
                    item_target = getattr(self, '_last_clicked_item', None)
                    if item_target:
                        try:
                            if item_target.data(0, Qt.UserRole) == "folder":
                                folder_name = item_target.text(1)
                                self.flattenGroup.emit(folder_name)
                        except RuntimeError:
                            pass
                    self._click_count = 0
                    self._last_clicked_item = None
                    return
            orig_mousePressEvent(event)
            
        def _tree_mouseDoubleClickEvent(event):
            if event.button() == Qt.LeftButton:
                item = self.tree.itemAt(event.pos())
                
                if self._click_timer.isActive():
                    self._click_count += 1
                else:
                    self._click_count = 2
                    self._last_clicked_item = item
                    self._click_timer.start(500)
                    
                if self._click_count >= 3:
                    self._click_timer.stop()
                    item_target = getattr(self, '_last_clicked_item', None)
                    if item_target and item_target.data(0, Qt.UserRole) == "folder":
                        folder_name = item_target.text(1)
                        self.flattenGroup.emit(folder_name)
                    self._click_count = 0
                    self._last_clicked_item = None
                    return
                    
                if item and item.data(0, Qt.UserRole) == "folder":
                    return # Block native expansion!
                    
            orig_mouseDoubleClickEvent(event)
            
        def _tree_mouseMoveEvent(event):
            if getattr(self.tree, '_rubber_band_active', False) and getattr(self.tree, '_rubber_band_origin', None) is not None:
                if (event.pos() - self.tree._rubber_band_origin).manhattanLength() > 3:
                    self.tree._rubber_band_dragged = True
                    
                rect = QRect(self.tree._rubber_band_origin, event.pos()).normalized()
                self.tree._rubber_band.setGeometry(rect)
                
                def check_item(item):
                    item_rect = self.tree.visualItemRect(item)
                    if rect.top() <= item_rect.bottom() and rect.bottom() >= item_rect.top():
                        item.setSelected(True)
                    else:
                        item.setSelected(False)
                    if item.isExpanded():
                        for j in range(item.childCount()):
                            check_item(item.child(j))
                            
                for i in range(self.tree.topLevelItemCount()):
                    check_item(self.tree.topLevelItem(i))
                self._update_item_selection_styles()
                return
            orig_mouseMoveEvent(event)
            
        def _tree_mouseReleaseEvent(event):
            if event.button() == Qt.LeftButton:
                if getattr(self.tree, '_rubber_band_active', False):
                    self.tree._rubber_band.hide()
                    self.tree._rubber_band_active = False
                    self.tree._rubber_band_origin = None
                    if getattr(self.tree, '_rubber_band_dragged', False):
                        self._update_item_selection_styles()
                        return
                else:
                    click_pos = getattr(self.tree, '_click_start_pos', None)
                    if click_pos and (event.pos() - click_pos).manhattanLength() < 5:
                        if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                            item = self.tree.itemAt(event.pos())
                            if item:
                                self.tree.clearSelection()
                                item.setSelected(True)
                                self.tree.setCurrentItem(item)
                            else:
                                self.tree.clearSelection()
                            self._update_item_selection_styles()
                            return
            orig_mouseReleaseEvent(event)
            
        self.tree.mousePressEvent = _tree_mousePressEvent
        self.tree.mouseDoubleClickEvent = _tree_mouseDoubleClickEvent
        self.tree.mouseMoveEvent = _tree_mouseMoveEvent
        self.tree.mouseReleaseEvent = _tree_mouseReleaseEvent
        
        # Override mimeData to allow dragging items out (to OS or other widgets)
        orig_mimeData = self.tree.mimeData
        def _tree_mimeData(items):
            from PySide6.QtCore import QUrl
            import os
            mime = orig_mimeData(items)
            urls = []
            for item in items:
                role_data = item.data(0, Qt.UserRole)
                if isinstance(role_data, int) and 0 <= role_data < len(self._tracks):
                    path = self._tracks[role_data].get('path')
                    if path and os.path.exists(path):
                        urls.append(QUrl.fromLocalFile(path))
                elif role_data == "folder":
                    folder_path = item.data(1, Qt.UserRole)
                    if folder_path and os.path.exists(folder_path):
                        urls.append(QUrl.fromLocalFile(folder_path))
                    else:
                        group_name = item.text(1)
                        found_folder = None
                        for track in self._tracks:
                            if track.get('playlist_group') == group_name:
                                tpath = track.get('path')
                                if tpath and os.path.exists(tpath):
                                    parent_dir = os.path.dirname(tpath)
                                    if os.path.isdir(parent_dir):
                                        found_folder = parent_dir
                                        break
                        if found_folder and os.path.exists(found_folder):
                            urls.append(QUrl.fromLocalFile(found_folder))
                        else:
                            for track in self._tracks:
                                if track.get('playlist_group') == group_name:
                                    path = track.get('path')
                                    if path and os.path.exists(path):
                                        urls.append(QUrl.fromLocalFile(path))
            if urls:
                mime.setUrls(urls)
            return mime
        self.tree.mimeData = _tree_mimeData
        # Override startDrag to show a custom clean pixmap instead of a huge row snapshot
        def _custom_startDrag(supportedActions):
            from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor, QFont
            from PySide6.QtCore import Qt, QPoint
            
            selected_items = self.tree.selectedItems()
            if not selected_items:
                return
                
            drag = QDrag(self.tree)
            drag.setMimeData(self.tree.mimeData(selected_items))
            
            count = len(selected_items)
            text = f"Dragging {count} item{'s' if count > 1 else ''}"
            if count == 1:
                text = selected_items[0].text(1)
                if len(text) > 25: text = text[:22] + "..."
                
            pixmap = QPixmap(200, 36)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(40, 40, 45, 230))
            painter.setPen(QColor("#FF5B06"))
            painter.drawRoundedRect(1, 1, 198, 34, 6, 6)
            
            painter.setPen(QColor("#ffffff"))
            font = QFont("Orbitron", 9, QFont.Bold)
            painter.setFont(font)
            painter.drawText(0, 0, 200, 36, Qt.AlignCenter, text)
            painter.end()
            
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
            drag.exec_(supportedActions)
            
        self.tree.startDrag = _custom_startDrag
        
        # Column widths & resize behavior
        self.tree.setColumnWidth(0, 70)    # Index
        self.tree.setColumnWidth(2, 160)   # Date Added
        self.tree.setColumnWidth(3, 80)    # Duration
        
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)           
        header.setSectionResizeMode(1, QHeaderView.Stretch)         
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(70)
        header.setStretchLastSection(False)
        
        header_item = self.tree.headerItem()
        header_item.setTextAlignment(0, Qt.AlignCenter)
        header_item.setTextAlignment(1, Qt.AlignLeft | Qt.AlignVCenter)
        header_item.setTextAlignment(2, Qt.AlignLeft | Qt.AlignVCenter)
        header_item.setTextAlignment(3, Qt.AlignCenter)
        
        # Header click for sorting
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_click)
        
        # Click handlers
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        # Styling
        self._apply_style()
        
        layout.addWidget(self.tree)
        
        # Enable smooth scrolling
        self._tree_smoother = SmoothTableWidget(self.tree)
    
    def _apply_style(self):
        self.tree.setStyleSheet("""
            QTreeWidget {
                background: transparent;
                background-color: transparent;
                border: none;
                color: #e0e0e0;
                outline: none;
                outline: 0;
                font-family: 'Orbitron', sans-serif;
            }
            QTreeWidget:focus {
                outline: none;
                border: none;
            }
            QTreeWidget QHeaderView {
                background: transparent;
                font-family: 'Orbitron', sans-serif;
            }
            QTreeWidget::viewport {
                background: transparent;
            }
            QTreeWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                border-top: none;
                border-left: none;
                border-right: none;
                outline: none;
                font-family: 'Orbitron', sans-serif;
            }
            QTreeWidget::item:focus {
                outline: none;
                border-top: none;
                border-left: none;
                border-right: none;
            }
            QTreeWidget::item:hover {
                background: rgba(255, 255, 255, 0.05);
            }
            QTreeWidget::item:selected {
                background: rgba(255, 255, 255, 0.12);
                outline: none;
                border-top: none;
                border-left: none;
                border-right: none;
            }
            QHeaderView::section {
                background: transparent;
                color: #888888;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                border-right: 1px solid rgba(255, 255, 255, 0.1);
                padding: 10px 8px;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QHeaderView::section:hover {
                color: #ffffff;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.2);
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 91, 6, 0.4);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 91, 6, 0.7);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0;
            }
        """)
    
    def _on_header_click(self, column_idx: int):
        column_map = {0: None, 1: "title", 2: "date", 3: "length"}
        column = column_map.get(column_idx)
        
        if column is None:
            return  
        
        if self._sort_column == column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        
        self._update_header_labels()
        self.sortChanged.emit(column, self._sort_ascending)
        self._render_tracks()
    
    def _update_header_labels(self):
        arrow = " ▲" if self._sort_ascending else " ▼"
        
        titles = ["#", "Title", "Date Added", "Duration"]
        for i, title in enumerate(titles):
            item = self.tree.headerItem()
            if item:
                if i == 1 and self._sort_column == "title":
                    item.setText(i, title + arrow)
                elif i == 2 and self._sort_column == "date":
                    item.setText(i, title + arrow)
                elif i == 3 and self._sort_column == "length":
                    item.setText(i, title + arrow)
                else:
                    item.setText(i, title)
    
    def _on_item_clicked(self, item, column):
        pass

    def _on_item_double_clicked(self, item, column):
        role = item.data(0, Qt.UserRole)
        if role == "folder":
            pass # Expansion is handled securely by the timeout logic now
        else:
            orig_idx = item.data(0, Qt.UserRole)
            if orig_idx is not None and isinstance(orig_idx, int):
                self.trackDoubleClicked.emit(orig_idx)

    def _show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #28282d; color: #ffffff; border: 1px solid #3c3c41; padding: 4px; font-family: 'Orbitron', sans-serif; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; font-size: 12px; }
            QMenu::item:selected { background-color: #FF5B06; }
            QMenu::separator { height: 1px; background: rgba(255, 255, 255, 0.1); margin: 4px 6px; }
        """)
        
        item = self.tree.itemAt(pos)
        selected = self.tree.selectedItems()
        target_item = item if item else (selected[0] if len(selected) == 1 else None)
        
        if target_item:
            target_path = None
            role_data = target_item.data(0, Qt.UserRole)
            if isinstance(role_data, int) and 0 <= role_data < len(self._tracks):
                target_path = self._tracks[role_data].get('path')
            elif role_data == "folder":
                target_path = target_item.data(1, Qt.UserRole)
                
            if target_path:
                view_explorer_action = QAction("View at Explorer", self)
                view_explorer_action.triggered.connect(lambda _, p=target_path: self._on_view_at_explorer(p))
                menu.addAction(view_explorer_action)
                menu.addSeparator()

        # Folder-specific context menu actions
        if item and item.data(0, Qt.UserRole) == "folder":
            extract_action = QAction("Extract Folder (Flatten)", self)
            folder_name = item.text(1)
            extract_action.triggered.connect(lambda: self.flattenGroup.emit(folder_name))
            menu.addAction(extract_action)
            menu.addSeparator()

        # Add Media Actions
        add_file_action = QAction("Add File...\tCtrl+O", self)
        add_file_action.triggered.connect(self.addFileRequested.emit)
        menu.addAction(add_file_action)

        add_multiple_action = QAction("Add Multiple Files...\tCtrl+K, Ctrl+O", self)
        add_multiple_action.triggered.connect(self.addMultipleFilesRequested.emit)
        menu.addAction(add_multiple_action)

        add_folder_action = QAction("Add Folder...\tCtrl+Shift+O", self)
        add_folder_action.triggered.connect(self.addFolderRequested.emit)
        menu.addAction(add_folder_action)

        menu.addSeparator()

        delete_selected_action = QAction("Delete Selected", self)
        delete_selected_action.triggered.connect(self._on_delete_selected)
        
        delete_all_action = QAction("Delete All", self)
        delete_all_action.triggered.connect(lambda: self.deleteAll.emit())
        
        if selected:
            menu.addAction(delete_selected_action)
        menu.addAction(delete_all_action)
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _on_view_at_explorer(self, path):
        import os, subprocess
        if path and os.path.exists(path):
            path_norm = os.path.normpath(path)
            try:
                if os.path.isfile(path_norm):
                    subprocess.Popen(['explorer', '/select,', path_norm])
                else:
                    subprocess.Popen(['explorer', path_norm])
            except Exception as e:
                print(f"[PlaylistTable] Error launching explorer: {e}")
        else:
            self._show_invalid_path_panel()

    def _show_invalid_path_panel(self, message="The path is invalid or the file is deleted."):
        p = self.window()
        if hasattr(p, 'show_invalid_path_panel'):
            p.show_invalid_path_panel(message)
        else:
            from MediaLibraryPage import FloatingInvalidPathPanel
            if not hasattr(self, '_invalid_path_panel') or self._invalid_path_panel is None:
                self._invalid_path_panel = FloatingInvalidPathPanel(self, message)
            self._invalid_path_panel.show_panel()
        
    def _on_delete_selected(self):
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
            
        orig_indices = set()
        for item in selected_items:
            orig_idx = item.data(0, Qt.UserRole)
            if orig_idx is not None and isinstance(orig_idx, int):
                orig_indices.add(orig_idx)
            elif orig_idx == "folder":
                for i in range(item.childCount()):
                    c_idx = item.child(i).data(0, Qt.UserRole)
                    if isinstance(c_idx, int):
                        orig_indices.add(c_idx)
                
        if orig_indices:
            # Sort in reverse to delete correctly from list
            sorted_indices = sorted(list(orig_indices), reverse=True)
            self.deleteSelected.emit(sorted_indices)

    def select_all(self):
        self.tree.setUpdatesEnabled(False)
        try:
            def _select_recursive(item):
                item.setSelected(True)
                for c in range(item.childCount()):
                    _select_recursive(item.child(c))

            for i in range(self.tree.topLevelItemCount()):
                _select_recursive(self.tree.topLevelItem(i))

            self._update_item_selection_styles()
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.viewport().update()

    def _update_item_selection_styles(self):
        from PySide6.QtGui import QColor
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == "folder":
                if item.isSelected():
                    for c in range(4):
                        item.setBackground(c, QColor(255, 255, 255, 31))
                else:
                    for c in range(4):
                        item.setBackground(c, QColor(40, 40, 45, 180))
        self.tree.viewport().update()
    
    def set_tracks(self, tracks: list):
        self._tracks = tracks
        self._render_tracks()
    
    def _render_tracks(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        from PySide6.QtGui import QColor, QFont
        
        # Save expanded states before clearing
        expanded_states = {}
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == "folder":
                group_name = item.text(1)
                expanded_states[group_name] = item.isExpanded()
                
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        
        sorted_tracks = list(enumerate(self._tracks))
        
        import re
        def natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
        
        if self._sort_column == "title":
            sorted_tracks.sort(key=lambda x: natural_sort_key(x[1].get('title', '')), 
                             reverse=not self._sort_ascending)
        elif self._sort_column == "date":
            sorted_tracks.sort(key=lambda x: x[1].get('date_added', ''), 
                             reverse=not self._sort_ascending)
        elif self._sort_column == "length":
            sorted_tracks.sort(key=lambda x: x[1].get('duration', 0), 
                             reverse=not self._sort_ascending)
        
        self._sorted_indices = [orig_idx for orig_idx, track in sorted_tracks]
        
        # Separate grouped items and standalone items to keep folders on top
        grouped_items = []
        standalone_items = []
        for orig_idx, track in sorted_tracks:
            if track.get('playlist_group'):
                grouped_items.append((orig_idx, track))
            else:
                standalone_items.append((orig_idx, track))
                
        # Group items by folder while preserving sorted order
        folders_dict = {}
        for orig_idx, track in grouped_items:
            group = track.get('playlist_group')
            if group not in folders_dict:
                folders_dict[group] = []
            folders_dict[group].append((orig_idx, track))
            
        track_counter = 1
        created_folders = {}
        
        def _create_track_item(parent, orig_idx, track, num_str):
            is_playing = orig_idx == self._current_index
            track_item = QTreeWidgetItem(parent)
            track_item.setFlags(track_item.flags() & ~Qt.ItemIsDropEnabled)
            track_item.setData(0, Qt.UserRole, orig_idx)
            num_text = ">" if is_playing else num_str
            track_item.setText(0, " " + num_text)
            track_item.setTextAlignment(0, Qt.AlignLeft | Qt.AlignVCenter)
            if is_playing:
                track_item.setForeground(0, QColor("#FF5B06"))
            else:
                track_item.setForeground(0, QColor("#888888"))
                
            title = track.get('title', 'Unknown')
            track_item.setText(1, title)
            track_item.setForeground(1, QColor("#e0e0e0"))
            track_item.setToolTip(1, title)
            
            date_added = track.get('date_added', '')
            track_item.setText(2, date_added)
            track_item.setForeground(2, QColor("#888888"))
            track_item.setTextAlignment(2, Qt.AlignLeft | Qt.AlignVCenter)
            
            dur_val = track.get('duration', 0)
            try:
                if isinstance(dur_val, str) and ':' in dur_val:
                    parts = dur_val.split(':')
                    if len(parts) == 2:
                        duration = float(parts[0]) * 60 + float(parts[1])
                    elif len(parts) == 3:
                        duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        duration = 0.0
                else:
                    duration = float(dur_val or 0)
            except (ValueError, TypeError):
                duration = 0.0
                
            mins = int(duration // 60)
            secs = int(duration % 60)
            track_item.setText(3, f"{mins}:{secs:02d}")
            track_item.setForeground(3, QColor("#888888"))
            track_item.setTextAlignment(3, Qt.AlignCenter)
            
            if is_playing:
                for col in range(4):
                    track_item.setBackground(col, QColor(255, 91, 6, 38))

        # Rebuild _sorted_indices to match the actual visual UI order (grouped first, then standalone)
        new_sorted_indices = []
        
        # Process grouped items folder by folder
        for group, items in folders_dict.items():
            folder_item = QTreeWidgetItem(self.tree)
            from PySide6.QtGui import QIcon
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "folder-icon.svg").replace("\\", "/")
            folder_item.setIcon(1, QIcon(icon_path))
            folder_item.setText(1, group)
            folder_item.setData(0, Qt.UserRole, "folder")
            
            # Store group folder path if available
            group_folder_path = None
            for _, trk in items:
                t_p = trk.get('path')
                if t_p and os.path.exists(t_p):
                    p_dir = os.path.dirname(t_p)
                    if os.path.isdir(p_dir) and (os.path.basename(p_dir) == group or not group_folder_path):
                        group_folder_path = p_dir
                        if os.path.basename(p_dir) == group:
                            break
            if group_folder_path:
                folder_item.setData(1, Qt.UserRole, group_folder_path)
                
            for c in range(4):
                folder_item.setBackground(c, QColor(40, 40, 45, 180))
                font = folder_item.font(c)
                font.setBold(True)
                folder_item.setFont(c, font)
            self.tree.addTopLevelItem(folder_item)
            created_folders[group] = folder_item
            
            for orig_idx, track in items:
                new_sorted_indices.append(orig_idx)
                _create_track_item(folder_item, orig_idx, track, str(track_counter))
                track_counter += 1
                
        # Then process standalone items
        for orig_idx, track in standalone_items:
            new_sorted_indices.append(orig_idx)
            _create_track_item(self.tree, orig_idx, track, str(track_counter))
            track_counter += 1
            
        self._sorted_indices = new_sorted_indices
                    
        # Restore expanded states (default to collapsed for new folders)
        for group, folder_item in created_folders.items():
            folder_item.setExpanded(expanded_states.get(group, False))
            
        self.tree.clearSelection()
        self._update_item_selection_styles()
        self.tree.setUpdatesEnabled(True)
            
    def highlight_playing(self, index: int):
        self._current_index = index
        self._render_tracks()
        
        # Auto-expand the folder of the currently playing track
        if 0 <= index < len(self._tracks):
            playing_track = self._tracks[index]
            playing_group = playing_track.get('playlist_group')
            if playing_group:
                # Find the folder item in the tree
                for i in range(self.tree.topLevelItemCount()):
                    item = self.tree.topLevelItem(i)
                    if item.data(0, Qt.UserRole) == "folder" and item.text(1) == playing_group:
                        if not item.isExpanded():
                            item.setExpanded(True)
                        break
    
    def get_next_index(self, current_index: int) -> int:
        if not self._sorted_indices:
            return (current_index + 1) % len(self._tracks) if self._tracks else -1
        
        try:
            pos = self._sorted_indices.index(current_index)
            next_pos = (pos + 1) % len(self._sorted_indices)
            return self._sorted_indices[next_pos]
        except ValueError:
            return self._sorted_indices[0] if self._sorted_indices else -1
    
    def get_prev_index(self, current_index: int) -> int:
        if not self._sorted_indices:
            return (current_index - 1) % len(self._tracks) if self._tracks else -1
        
        try:
            pos = self._sorted_indices.index(current_index)
            prev_pos = (pos - 1) % len(self._sorted_indices)
            return self._sorted_indices[prev_pos]
        except ValueError:
            return self._sorted_indices[-1] if self._sorted_indices else -1

class PlayerBar(QFrame):
    """
    Player controls bar matching HTML5 design.
    
    Component Name: PlayerBar
    """
    
    playClicked = Signal()
    prevClicked = Signal()
    nextClicked = Signal()
    shuffleClicked = Signal()
    loopClicked = Signal()
    seekChanged = Signal(float)
    volumeChanged = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerBar")
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFixedHeight(75)
        self.setMinimumHeight(75)  # Prevent compression
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Never shrink vertically
        self._is_playing = False
        self._loop_mode = "off"  # off, all, one
        self._is_shuffled = False
        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(15)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "UI Icons")
        
        # === Left: Track Info ===
        track_section = QHBoxLayout()
        track_section.setSpacing(12)
        track_section.setAlignment(Qt.AlignVCenter)
        
        # Track text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        # Use MarqueeLabel for scrolling long titles
        self.title_label = MarqueeLabel("No track playing")
        self.title_label.setObjectName("playerTitle")
        
        self.artist_label = QLabel("-")
        self.artist_label.setObjectName("playerArtist")
        
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.artist_label)
        track_section.addLayout(text_layout)
        
        layout.addLayout(track_section)
        
        # === Center: Controls ===
        controls = QHBoxLayout()
        controls.setSpacing(12)
        controls.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        
        # Shuffle
        self.shuffle_btn = self._create_icon_btn("shuffle-icon.png", "Shuffle (R)")
        self.shuffle_btn.setObjectName("shuffleBtn")
        self.shuffle_btn.clicked.connect(self._toggle_shuffle)
        controls.addWidget(self.shuffle_btn)
        
        # Prev
        self.prev_btn = self._create_icon_btn("previous-button-icon.png", "Previous (P)")
        self.prev_btn.setObjectName("prevBtn")
        self.prev_btn.setIconSize(QSize(24, 24))  # Larger than shuffle/loop
        self.prev_btn.clicked.connect(self.prevClicked.emit)
        controls.addWidget(self.prev_btn)
        
        # Play (main button)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedSize(48, 48)
        self.play_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.play_btn.setToolTip("Play/Pause (Space)")
        self.play_btn.clicked.connect(self.playClicked.emit)
        icon_path = os.path.join(icons_dir, "play-button-icon.png")
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
            self.play_btn.setIconSize(QSize(36, 36))  # Largest icon
        controls.addWidget(self.play_btn)
        
        # Next
        self.next_btn = self._create_icon_btn("forward-button-icon.png", "Next (N)")
        self.next_btn.setObjectName("nextBtn")
        self.next_btn.setIconSize(QSize(24, 24))  # Larger than shuffle/loop
        self.next_btn.clicked.connect(self.nextClicked.emit)
        controls.addWidget(self.next_btn)
        
        # Loop (moved after next)
        self.loop_btn = self._create_icon_btn("loop-button-icon.png", "Loop (L)")
        self.loop_btn.setObjectName("loopBtn")
        self.loop_btn.clicked.connect(self._toggle_loop)
        controls.addWidget(self.loop_btn)
        
        # Loop One (hidden until loop mode is 'one')
        self.loop_one_btn = self._create_icon_btn("loop-one-button-icon.png", "Loop One")
        self.loop_one_btn.setObjectName("loopOneBtn")
        self.loop_one_btn.clicked.connect(self._toggle_loop)
        self.loop_one_btn.hide()
        controls.addWidget(self.loop_one_btn)
        
        layout.addLayout(controls, stretch=1)
        
        # === Timeline ===
        timeline_layout = QHBoxLayout()
        timeline_layout.setSpacing(8)
        timeline_layout.setAlignment(Qt.AlignVCenter)
        
        self.time_current = QLineEdit("0:00")
        self.time_current.setObjectName("timeLabel")
        self.time_current.setFixedWidth(80)
        self.time_current.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.time_current.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: white;
                padding: 0;
            }
        """)
        self.time_current.returnPressed.connect(self._on_time_input)
        
        from PySide6.QtGui import QColor
        self.timeline = ClickSlider(Qt.Horizontal)
        self.timeline._handle_color = QColor("#FF5B06")
        self.timeline._handle_hover_color = QColor("#FDA903")
        self.timeline.setObjectName("timelineSlider")
        self.timeline.setRange(0, 1000)
        self.timeline.setFixedWidth(200)
        self.timeline.sliderMoved.connect(self._on_timeline_moved)
        self.timeline.sliderPressed.connect(lambda: setattr(self, '_is_dragging_timeline', True))
        self.timeline.sliderReleased.connect(self._on_timeline_released)
        
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("timeDurationLabel")
        self.time_total.setFixedWidth(80)
        self.time_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        timeline_layout.addWidget(self.time_current)
        timeline_layout.addWidget(self.timeline)
        timeline_layout.addWidget(self.time_total)
        
        layout.addLayout(timeline_layout)
        
        # Spacer
        layout.addSpacerItem(QSpacerItem(20, 0))
        
        # === Right: Volume ===
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(8)
        volume_layout.setAlignment(Qt.AlignVCenter)
        
        self.volume_icon = QLabel()
        self.volume_icon.setObjectName("volumeIcon")
        icon_path = os.path.join(icons_dir, "speaker-icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.volume_icon.setPixmap(pixmap)
        
        self.volume_slider = VolumeSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 125)  # Allow volume boost up to 125%
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self._on_volume_change)
        
        self.volume_input = QLineEdit("100")
        self.volume_input.setObjectName("volumeInput")
        self.volume_input.setFixedWidth(55)
        self.volume_input.setAlignment(Qt.AlignCenter)
        self.volume_input.editingFinished.connect(self._on_volume_input_return)
        
        volume_layout.addWidget(self.volume_icon)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_input)
        # Install event filters so global shortcuts aren't swallowed by inputs
        self.time_current.installEventFilter(self)
        self.volume_input.installEventFilter(self)
            
        layout.addLayout(volume_layout)
        
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import Qt
        if event.type() == QEvent.KeyPress:
            key = event.key()
            # Intercept global media controls (Space, P, N, L, R, F)
            if key in (Qt.Key_Space, Qt.Key_P, Qt.Key_N, Qt.Key_L, Qt.Key_R, Qt.Key_F):
                # Don't intercept if modifier keys like Ctrl are pressed (for normal text shortcuts like Ctrl+C)
                if event.modifiers() == Qt.NoModifier:
                    parent = self.parentWidget()
                    while parent:
                        if parent.__class__.__name__ == "MusicPanelWidget":
                            parent.keyPressEvent(event)
                            return True
                        parent = parent.parentWidget()
        return super().eventFilter(obj, event)
    
    def _create_icon_btn(self, icon_name: str, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("controlBtn")
        btn.setFixedSize(48, 48)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setToolTip(tooltip)
        
        # Support both dev and bundled exe paths
        import sys
        if getattr(sys, 'frozen', False):
            # Running as bundled exe
            base_path = sys._MEIPASS
        else:
            # Running as script
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        icon_path = os.path.join(base_path, "UI Icons", icon_name)
        if os.path.exists(icon_path):
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(18, 18))
        
        return btn
    
    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#playerBar {
                background: rgba(15, 15, 20, 0.95);
                border-top: 1px solid rgba(255, 91, 6, 0.25);
            }
            
            QLabel#playerTitle {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }
            QLabel#playerArtist {
                color: #888888;
                font-size: 11px;
            }
            
            QPushButton#controlBtn,
            QPushButton#shuffleBtn,
            QPushButton#loopBtn,
            QPushButton#prevBtn,
            QPushButton#nextBtn,
            QPushButton#loopOneBtn {
                background: transparent;
                border: none;
                border-radius: 24px;
            }
            QPushButton#controlBtn:hover,
            QPushButton#shuffleBtn:hover,
            QPushButton#loopBtn:hover,
            QPushButton#prevBtn:hover,
            QPushButton#nextBtn:hover,
            QPushButton#loopOneBtn:hover {
                background: rgba(255, 255, 255, 0.1);
            }
            
            QPushButton#playBtn {
                background: transparent;
                border: none;
                border-radius: 24px;
            }
            QPushButton#playBtn:hover {
                background: rgba(255, 255, 255, 0.1);
            }
            
            QLabel#timeLabel {
                color: #888888;
                font-size: 11px;
            }
            
            QSlider#timelineSlider {
                background: transparent;
            }
            
            QSlider#timelineSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.1);
                height: 4px;
                border-radius: 2px;
            }
            QSlider#timelineSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                margin: -6px 0;
                background: transparent;
                border: none;
            }
            QSlider#timelineSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 2px;
            }
            
            QSlider#volumeSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.1);
                height: 4px;
                border-radius: 2px;
            }
            QSlider#volumeSlider::handle:horizontal {
                background: #e0e0e0;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: none;
            }
            QSlider#volumeSlider::handle:horizontal:hover {
                background: #ffffff;
            }
            QSlider#volumeSlider::sub-page:horizontal {
                background: #888888;
                border-radius: 2px;
            }
            
            QSpinBox#volumeInput {
                background: rgba(30, 30, 40, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
                padding: 2px 5px;
            }
            
        """)
    
    def _toggle_shuffle(self):
        self._is_shuffled = not self._is_shuffled
        self._update_shuffle_style()
        self.shuffleClicked.emit()
    
    def _toggle_loop(self):
        if self._loop_mode == "off":
            self._loop_mode = "all"
        elif self._loop_mode == "all":
            self._loop_mode = "one"
        else:
            self._loop_mode = "off"
        self._update_loop_style()
        self.loopClicked.emit()
    
    def _update_shuffle_style(self):
        if self._is_shuffled:
            # Transparent background with orange border
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 2px solid #FF5B06;
                    border-radius: 16px;
                }
            """)
        else:
            # No background, transparent border (to keep size consistent)
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 2px solid transparent;
                    border-radius: 16px;
                }
            """)
    
    def _update_loop_style(self):
        if self._loop_mode == "one":
            # Show loop-one icon, hide regular loop
            self.loop_btn.hide()
            self.loop_one_btn.show()
            # Orange background (25% opacity) with border
            self.loop_one_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.25);
                    border: 2px solid #FF5B06;
                    border-radius: 16px;
                }
            """)
        else:
            # Show regular loop icon, hide loop-one
            self.loop_one_btn.hide()
            self.loop_btn.show()
            
            if self._loop_mode == "all":
                # Transparent background with orange border
                self.loop_btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 2px solid #FF5B06;
                        border-radius: 16px;
                    }
                """)
            else:
                # Off - no background, transparent border (to keep size consistent)
                self.loop_btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 2px solid transparent;
                        border-radius: 16px;
                    }
                """)
    
    def _on_volume_change(self, value: int):
        self.volume_input.blockSignals(True)
        self.volume_input.setText(str(value))
        self.volume_input.blockSignals(False)
        self.volumeChanged.emit(value)
    
    def _on_volume_input_return(self):
        text = self.volume_input.text().strip()
        try:
            val = int(text)
            val = max(0, min(125, val))
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(val)
            self.volume_slider.blockSignals(False)
            self.volumeChanged.emit(val)
            self.volume_input.setText(str(val))
        except ValueError:
            pass
        self.volume_input.clearFocus()
    
    def set_playing(self, playing: bool):
        self._is_playing = playing
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_name = "pause-button-icon.png" if playing else "play-button-icon.png"
        icon_path = os.path.join(script_dir, "UI Icons", icon_name)
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
    
    def set_track_info(self, title: str, artist: str):
        self.title_label.setText(title)
        self.artist_label.setText(artist or "-")
        # Update docked taskbar widget if available across parent hierarchy
        curr = self.parent()
        while curr is not None:
            if hasattr(curr, '_taskbar_media_widget') and curr._taskbar_media_widget:
                curr._taskbar_media_widget.set_track_info(title, artist if artist != "-" else "")
                break
            curr = curr.parent()

    def set_shuffle(self, enabled: bool):
        """Set shuffle state and update UI."""
        self._is_shuffled = enabled
        self._update_shuffle_style()

    def set_loop_mode(self, mode: str):
        """Set loop mode (off, all, one) and update UI."""
        if mode in ("off", "all", "one"):
            self._loop_mode = mode
            self._update_loop_style()
    
    def set_position(self, current: float, total: float, skip_throttle: bool = False):
        self._last_total_duration = total  # Store for drag updates
        
        # Check if user is interacting with the slider
        is_dragging = getattr(self, '_is_dragging_timeline', False)
        
        if total > 0 and not is_dragging:
            self.timeline.blockSignals(True)
            self.timeline.setValue(int((current / total) * 1000))
            self.timeline.blockSignals(False)
        
        # Don't overwrite time field while user is editing or dragging
        if not self.time_current.hasFocus() and not is_dragging:
            self.time_current.setText(self._format_time(current))
            self.time_total.setText(self._format_time(total))
    
    def _on_timeline_moved(self, value: int):
        """Update current time label in real-time while dragging."""
        total = getattr(self, '_last_total_duration', 0)
        if total > 0:
            current = (value / 1000.0) * total
            self.time_current.setText(self._format_time(current))
        self.seekChanged.emit(value / 1000.0)
    
    def _on_timeline_released(self):
        """Finalize seek on slider release."""
        setattr(self, '_is_dragging_timeline', False)
        # Emit one final seek to be sure
        self.seekChanged.emit(self.timeline.value() / 1000.0)
    
    def _format_time(self, seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"
    
    def _on_time_input(self):
        """Handle time input from the editable time field."""
        text = self.time_current.text().strip()
        try:
            total_seconds = 0
            if ':' in text:
                parts = text.split(':')
                parts.reverse()  # [secs, mins, hours]
                secs = int(parts[0]) if len(parts) > 0 else 0
                mins = int(parts[1]) if len(parts) > 1 else 0
                hours = int(parts[2]) if len(parts) > 2 else 0
                total_seconds = hours * 3600 + mins * 60 + secs
            else:
                # Advanced raw number logic (e.g. 130 -> 1m30s, 10265 -> 1h02m65s)
                if len(text) <= 2:
                    total_seconds = int(text)
                else:
                    secs = int(text[-2:])
                    remaining = text[:-2]
                    if len(remaining) <= 2:
                        mins = int(remaining)
                        total_seconds = mins * 60 + secs
                    else:
                        mins = int(remaining[-2:])
                        hours = int(remaining[:-2])
                        total_seconds = hours * 3600 + mins * 60 + secs
            
            duration = getattr(self, '_last_total_duration', 0)
            if duration > 0:
                # Convert raw seconds into a percentage (0.0 to 1.0) for the seek method
                percent = max(0.0, min(1.0, total_seconds / duration))
                self.seekChanged.emit(percent)
        except (ValueError, IndexError):
            pass  # Invalid input, ignore
        
        # Deselect the field
        self.time_current.clearFocus()





class SplitResumeButton(QWidget):
    """
    Split button widget combining a main action button and a dropdown menu button.
    Component Name: SplitResumeButton
    """
    clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("splitResumeContainer")
        
        arrow_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.btn_main = QPushButton("Resume", self)
        self.btn_main.setObjectName("splitResumeMain")
        self.btn_main.setCursor(Qt.PointingHandCursor)
        self.btn_main.setFixedHeight(28)
        
        self.btn_arrow = QToolButton(self)
        self.btn_arrow.setObjectName("splitResumeArrow")
        self.btn_arrow.setCursor(Qt.PointingHandCursor)
        self.btn_arrow.setPopupMode(QToolButton.InstantPopup)
        self.btn_arrow.setFixedSize(22, 28)
        
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        if os.path.exists(arrow_icon):
            self.btn_arrow.setIcon(QIcon(arrow_icon))
            self.btn_arrow.setIconSize(QSize(10, 8))
        
        layout.addWidget(self.btn_main)
        layout.addWidget(self.btn_arrow)
        
        self.setStyleSheet(f"""
            QWidget#splitResumeContainer {{
                background: transparent;
                border: none;
            }}
            QPushButton#splitResumeMain {{
                color: #FFFFFF;
                background-color: #333544;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 0px 14px;
                min-height: 28px;
                max-height: 28px;
                min-width: 130px;
                font-family: 'Orbitron', 'Rajdhani', sans-serif;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton#splitResumeMain:hover {{
                background-color: #484b60;
                border-color: rgba(255, 255, 255, 0.25);
            }}
            QPushButton#splitResumeMain:pressed {{
                background-color: #242530;
            }}
            QToolButton#splitResumeArrow {{
                background-color: #333544;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 1px solid rgba(255, 255, 255, 0.15);
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                min-height: 28px;
                max-height: 28px;
            }}
            QToolButton#splitResumeArrow:hover {{
                background-color: #484b60;
                border-color: rgba(255, 255, 255, 0.25);
            }}
            QToolButton#splitResumeArrow:pressed {{
                background-color: #242530;
            }}
            QToolButton#splitResumeArrow::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)
        
        # Menu Setup
        self.resume_menu = QMenu(self)
        self.resume_menu.setObjectName("resumeMenu")
        self.resume_menu.setStyleSheet("""
            QMenu#resumeMenu {
                background-color: #1a1a1a;
                border: none;
                border-radius: 8px;
                color: #ffffff;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: 500;
                padding: 4px;
            }
            QMenu#resumeMenu::item {
                padding: 6px 12px;
                min-height: 24px;
                border-radius: 4px;
                background: transparent;
                color: #ffffff;
            }
            QMenu#resumeMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
        """)
        
        self.act_resume = self.resume_menu.addAction("Resume")
        self.act_resume_folder = self.resume_menu.addAction("Resume and folder")
        self.btn_arrow.setMenu(self.resume_menu)
        
        # QSettings Load
        from PySide6.QtCore import QSettings
        self._settings = QSettings("TDD131", "HELXAID")
        pref = self._settings.value("Music/resume_mode_pref", "Resume", type=str)
        if pref not in ("Resume", "Resume and folder"):
            pref = "Resume"
        self._active_pref = pref
        self.btn_main.setText(self._active_pref)
        
        # Signal Connections
        self.btn_main.clicked.connect(self.clicked.emit)
        self.act_resume.triggered.connect(lambda: self._select_pref("Resume"))
        self.act_resume_folder.triggered.connect(lambda: self._select_pref("Resume and folder"))
        self.resume_menu.aboutToShow.connect(self._position_resume_menu)

    def _position_resume_menu(self):
        try:
            from PySide6.QtCore import QPoint
            w = self.resume_menu.sizeHint().width()
            pos = self.mapToGlobal(QPoint(self.width() - w, self.height() + 2))
            self.resume_menu.move(pos)
        except Exception:
            pass
        
    def _select_pref(self, pref_name):
        self._active_pref = pref_name
        self.btn_main.setText(pref_name)
        self._settings.setValue("Music/resume_mode_pref", pref_name)
        self.adjustSize()
        p = self.parent()
        while p:
            if hasattr(p, 'update_position'):
                p.update_position()
                break
            p = p.parent()

    def get_preference(self):
        return self._active_pref

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.btn_main.setEnabled(enabled)
        self.btn_arrow.setEnabled(enabled)


class ResumeNotificationWidget(QFrame):
    """
    Banner to notify the user of an unfinished playlist from a previous session.
    Component Name: ResumeNotificationWidget
    """
    
    resume_clicked = Signal()
    resume_and_folder_clicked = Signal()
    dismiss_clicked = Signal()
    auto_timeout = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resumeNotification")
        self.setFixedHeight(44)
        
        self.setStyleSheet("""
            QFrame#resumeNotification {
                background-color: rgba(31, 32, 41, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Orbitron', 'Rajdhani', sans-serif;
                font-size: 11px;
                background: transparent;
                border: none;
            }
            QPushButton#resumeDismissBtn {
                color: #FFFFFF;
                background-color: #333544;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 0px 14px;
                min-height: 28px;
                max-height: 28px;
                min-width: 80px;
                font-family: 'Orbitron', 'Rajdhani', sans-serif;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton#resumeDismissBtn:hover {
                background-color: #484b60;
                border-color: rgba(255, 255, 255, 0.25);
            }
            QPushButton#resumeDismissBtn:pressed {
                background-color: #242530;
            }
        """)
        
        from PySide6.QtWidgets import QVBoxLayout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        content_widget = QWidget(self)
        content_widget.setObjectName("resumeContentWidget")
        content_widget.setStyleSheet("QWidget#resumeContentWidget { background: transparent; border: none; }")
        layout = QHBoxLayout(content_widget)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(12)
        main_layout.addWidget(content_widget, stretch=1)
        
        # Label
        self.lbl_msg = QLabel("Resume: Unknown?", self)
        self.lbl_msg.setObjectName("resumeLabel")
        layout.addWidget(self.lbl_msg, alignment=Qt.AlignVCenter)
        
        # Split Resume Dropdown Button Component
        self.btn_resume = SplitResumeButton(self)
        
        self.btn_dismiss = QPushButton("Dismiss", self)
        self.btn_dismiss.setObjectName("resumeDismissBtn")
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        self.btn_dismiss.setFixedHeight(28)
        self.btn_dismiss.setMinimumWidth(80)
        
        layout.addWidget(self.btn_resume, alignment=Qt.AlignVCenter)
        layout.addWidget(self.btn_dismiss, alignment=Qt.AlignVCenter)
        
        # Push everything to the left
        layout.addStretch()
        
        from PySide6.QtWidgets import QProgressBar
        self.progress = QProgressBar(self)
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: transparent;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #FF5B06;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        main_layout.addWidget(self.progress)
        
        # Auto-dismiss timer
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_progress)
        self._timeout_ms = 10000
        self._elapsed_ms = 0
        
        self.progress.setRange(0, self._timeout_ms)
        
        # Connections
        self.btn_resume.clicked.connect(self._on_main_button_clicked)
        self.btn_dismiss.clicked.connect(self._on_dismiss_clicked)
        self.btn_resume.resume_menu.aboutToShow.connect(self._on_menu_shown)
        self.btn_resume.resume_menu.aboutToHide.connect(self._on_menu_hidden)
        
    def _on_menu_shown(self):
        self._timer.stop()

    def _on_menu_hidden(self):
        # Resume auto-dismiss countdown when dropdown closes
        if self.isVisible() and hasattr(self, '_timer') and self._elapsed_ms < self._timeout_ms:
            self._timer.start()

    def _on_main_button_clicked(self):
        self._timer.stop()
        pref = self.btn_resume.get_preference()
        print(f"[Music DEBUG] ResumeNotificationWidget main button clicked! Active Preference: {pref}")
        try:
            if pref == "Resume and folder":
                print("[Music DEBUG] Emitting resume_and_folder_clicked signal...")
                self.resume_and_folder_clicked.emit()
            else:
                print("[Music DEBUG] Emitting resume_clicked signal...")
                self.resume_clicked.emit()
        except Exception as e:
            print(f"[Music DEBUG ERROR] Signal emission error: {e}")

    def _on_dismiss_clicked(self):
        self._timer.stop()
        self.dismiss_clicked.emit()
        
    def _update_progress(self):
        self._elapsed_ms += 16
        remaining = max(0, self._timeout_ms - self._elapsed_ms)
        self.progress.setValue(remaining)
        if self._elapsed_ms >= self._timeout_ms:
            self._timer.stop()
            self.auto_timeout.emit()

    def set_track_title(self, title):
        self._full_title = title
        self.btn_resume.setEnabled(True)
        self.btn_dismiss.setEnabled(True)
        if self.graphicsEffect():
            self.graphicsEffect().setOpacity(1.0)
        self.update_position()

    def update_position(self):
        if not self.parent():
            return
        parent_w = self.parent().width()
        max_allowed_w = max(320, parent_w - 40)
        self.setMaximumWidth(max_allowed_w)
        
        if hasattr(self, '_full_title') and self._full_title:
            from PySide6.QtGui import QFontMetrics
            fm = QFontMetrics(self.lbl_msg.font())
            btns_w = self.btn_resume.sizeHint().width() + self.btn_dismiss.sizeHint().width()
            avail_lbl_w = max(60, max_allowed_w - btns_w - 70)
            prefix = "Resume: "
            suffix = " ?"
            p_w = fm.horizontalAdvance(prefix)
            s_w = fm.horizontalAdvance(suffix)
            track_avail = max(20, avail_lbl_w - p_w - s_w)
            elided_title = fm.elidedText(self._full_title, Qt.ElideRight, track_avail)
            self.lbl_msg.setText(f"{prefix}{elided_title}{suffix}")
            self.lbl_msg.setToolTip(f"Resume: {self._full_title}?")
        
        self.adjustSize()
        w = self.width()
        x = max(20, parent_w - w - 20)
        self.move(x, 20)

    def animate_out(self, callback=None):
        """Fade out and slide up the banner, then execute callback."""
        self._timer.stop()
        self.btn_resume.setEnabled(False)
        self.btn_dismiss.setEnabled(False)
        
        from PySide6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QPoint, QAbstractAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        
        if not self.graphicsEffect():
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
        else:
            effect = self.graphicsEffect()
            
        self._anim_group = QParallelAnimationGroup(self)
        
        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(250)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + QPoint(0, -30))
        pos_anim.setEasingCurve(QEasingCurve.InCubic)
        
        fade_anim = QPropertyAnimation(effect, b"opacity")
        fade_anim.setDuration(250)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        
        self._anim_group.addAnimation(pos_anim)
        self._anim_group.addAnimation(fade_anim)
        
        def on_finished():
            self.hide()
            self.setGraphicsEffect(None)
            if callback:
                callback()
                
        self._anim_group.finished.connect(on_finished)
        self._anim_group.start(QAbstractAnimation.DeleteWhenStopped)

    def showEvent(self, event):
        super().showEvent(event)
        self.btn_resume.setEnabled(True)
        self.btn_dismiss.setEnabled(True)
        self.progress.setValue(self._timeout_ms)
        self._elapsed_ms = 0
        self._timer.start()
        
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        if not self.graphicsEffect():
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
        else:
            effect = self.graphicsEffect()
            
        effect.setOpacity(0.0)
        self.update_position()
            
        from PySide6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QPoint, QAbstractAnimation
        self._in_anim_group = QParallelAnimationGroup(self)
        
        target_y = self.y()
        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(300)
        pos_anim.setStartValue(QPoint(self.x(), -30))
        pos_anim.setEndValue(QPoint(self.x(), target_y))
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        fade_anim = QPropertyAnimation(effect, b"opacity")
        fade_anim.setDuration(300)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        
        self._in_anim_group.addAnimation(pos_anim)
        self._in_anim_group.addAnimation(fade_anim)
        
        def on_in_finished():
            self.setGraphicsEffect(None)
        self._in_anim_group.finished.connect(on_in_finished)
        self._in_anim_group.start(QAbstractAnimation.DeleteWhenStopped)


SVG_CLOSE_ICON = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>"""


def _render_svg_icon_sharp(svg_str: str, size: int = 12, color: str = "#FFFFFF"):
    """Render crisp, sharp vector SVG icon with anti-aliasing and DevicePixelRatio 2.0."""
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPainter, QPixmap, QIcon
        from PySide6.QtCore import Qt
        formatted_svg = svg_str.replace('currentColor', color)
        renderer = QSvgRenderer(bytearray(formatted_svg, encoding='utf-8'))
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2.0)
        return QIcon(pixmap)
    except Exception:
        from PySide6.QtGui import QIcon
        return QIcon()


class FloatingUrlInputWidget(QFrame):
    """
    Floating URL input overlay matching HELXAID glassmorphism UI design system.
    
    Component Name: FloatingUrlInputWidget
    """
    url_submitted = Signal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("floatingUrlInput")
        self.setFixedSize(480, 116)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._is_closing = False
        self._is_dragging = False
        self._drag_start_pos = QPoint()
        self.hide()
        
        # Load user's preferred stream mode (default: "buffer")
        from PySide6.QtCore import QSettings
        settings = QSettings("TDD131", "HELXAID")
        self._current_mode = settings.value("MusicPlayer/stream_mode", "buffer", type=str)
        if self._current_mode not in ("buffer", "direct"):
            self._current_mode = "buffer"
        
        # Glassmorphism floating panel design system
        self.setStyleSheet("""
            QFrame#floatingUrlInput {
                background-color: rgba(14, 15, 20, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QWidget#floatingUrlTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 11px;
                border-top-right-radius: 11px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#floatingUrlTitleLabel {
                color: #FFFFFF;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 0.5px;
            }
            QPushButton#floatingUrlCloseBtn {
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
            }
            QPushButton#floatingUrlCloseBtn:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QWidget#streamModeContainer {
                background-color: rgba(255, 255, 255, 0.04);
                border: none;
                border-radius: 5px;
            }
            QPushButton#btnModeBuffer, QPushButton#btnModeDirect {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: 600;
                border: none;
                border-radius: 4px;
                padding: 0px 8px;
                min-height: 22px;
                max-height: 22px;
                height: 22px;
                color: #888888;
                background-color: transparent;
            }
            QPushButton#btnModeBuffer:hover, QPushButton#btnModeDirect:hover {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.06);
            }
            QPushButton#btnModeBuffer[active="true"], QPushButton#btnModeDirect[active="true"] {
                color: #FFFFFF;
                font-weight: bold;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
            }
            QLineEdit#streamUrlInput {
                background-color: rgba(30, 30, 30, 0.85);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 5px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                padding: 0px 8px;
                min-height: 28px;
                max-height: 28px;
                height: 28px;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }
            QLineEdit#streamUrlInput:focus {
                background-color: #383b41;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QLineEdit#streamUrlInput::placeholder {
                color: #70737d;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
            }
            QPushButton#btnSearchStream {
                color: #FFFFFF;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border: none;
                border-radius: 5px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 0.5px;
                padding: 0px 14px;
                min-height: 28px;
                max-height: 28px;
                height: 28px;
            }
            QPushButton#btnSearchStream:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7326, stop:1 #FFBA24);
            }
            QPushButton#btnSearchStream:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E04B00, stop:1 #E09000);
            }
            QLabel#streamErrorLabel {
                color: #FF4D4D;
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: 600;
                background: transparent;
            }
            QToolTip {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                color: #EDEDED;
                background-color: #121318;
                border: 1px solid rgba(255, 91, 6, 0.45);
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setColor(QColor(0, 0, 0, 180))
            shadow.setOffset(0, 8)
            self.setGraphicsEffect(shadow)
        except Exception:
            pass
        
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
        from PySide6.QtGui import QPixmap, QIcon
        from PySide6.QtCore import QSize
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Draggable Title Bar (32px)
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("floatingUrlTitleBar")
        self.title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 0, 10, 0)
        title_layout.setSpacing(8)
        title_layout.setAlignment(Qt.AlignVCenter)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        panel_icon_path = os.path.join(script_dir, "UI Icons", "open-white.svg").replace('\\', '/')
        
        icon_lbl = QLabel(self.title_bar)
        icon_lbl.setObjectName("floatingUrlIconLabel")
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setScaledContents(True)
        if os.path.exists(panel_icon_path):
            icon_lbl.setPixmap(QPixmap(panel_icon_path))
        title_layout.addWidget(icon_lbl, 0, Qt.AlignVCenter)
        
        self.lbl_header = QLabel("OPEN STREAM URL", self.title_bar)
        self.lbl_header.setObjectName("floatingUrlTitleLabel")
        title_layout.addWidget(self.lbl_header, 0, Qt.AlignVCenter)
        title_layout.addStretch(1)
        
        self.btn_close_header = QPushButton(self.title_bar)
        self.btn_close_header.setObjectName("floatingUrlCloseBtn")
        self.btn_close_header.setFixedSize(22, 22)
        self.btn_close_header.setCursor(Qt.PointingHandCursor)
        self.btn_close_header.setToolTip("Close (Esc / Ctrl+Y)")
        self.btn_close_header.setIcon(_render_svg_icon_sharp(SVG_CLOSE_ICON, size=10, color="#FFFFFF"))
        self.btn_close_header.setIconSize(QSize(10, 10))
        self.btn_close_header.clicked.connect(self.close_panel)
        title_layout.addWidget(self.btn_close_header, 0, Qt.AlignVCenter)
        
        layout.addWidget(self.title_bar)
        
        # Content Area
        content_widget = QWidget(self)
        content_widget.setObjectName("floatingUrlContentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 6, 12, 8)
        content_layout.setSpacing(5)
        
        # Mode Switcher (Pill Selector)
        self.mode_container = QWidget(content_widget)
        self.mode_container.setObjectName("streamModeContainer")
        self.mode_container.setFixedHeight(26)
        mode_layout = QHBoxLayout(self.mode_container)
        mode_layout.setContentsMargins(2, 2, 2, 2)
        mode_layout.setSpacing(3)
        
        self.btn_mode_buffer = QPushButton("Buffer Cache", self.mode_container)
        self.btn_mode_buffer.setObjectName("btnModeBuffer")
        self.btn_mode_buffer.setFixedHeight(22)
        self.btn_mode_buffer.setFocusPolicy(Qt.NoFocus)
        self.btn_mode_buffer.setCursor(Qt.PointingHandCursor)
        self.btn_mode_buffer.setToolTip(
            "<b>BUFFER CACHE (Recommended for Gaming)</b><br>"
            "Downloads audio stream to local temp cache.<br>"
            "• 100% stutter-free & zero lag during gameplay<br>"
            "• Instant seeking without buffering delays<br>"
            "• Temp files auto-cleaned after 24h"
        )
        
        self.btn_mode_direct = QPushButton("Direct Stream", self.mode_container)
        self.btn_mode_direct.setObjectName("btnModeDirect")
        self.btn_mode_direct.setFixedHeight(22)
        self.btn_mode_direct.setFocusPolicy(Qt.NoFocus)
        self.btn_mode_direct.setCursor(Qt.PointingHandCursor)
        self.btn_mode_direct.setToolTip(
            "<b>DIRECT STREAM (Instant Stream)</b><br>"
            "Streams audio directly without downloading to disk.<br>"
            "• Immediate playback startup with minimal disk usage<br>"
            "• Best for quick music preview and streaming"
        )
        
        mode_layout.addWidget(self.btn_mode_buffer)
        mode_layout.addWidget(self.btn_mode_direct)
        content_layout.addWidget(self.mode_container)
        
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        
        self.input_field = QLineEdit(content_widget)
        self.input_field.setObjectName("streamUrlInput")
        self.input_field.setPlaceholderText("Type media title or paste stream URL...")
        self.input_field.setFixedHeight(28)
        
        self.btn_play = QPushButton("Search", content_widget)
        self.btn_play.setObjectName("btnSearchStream")
        self.btn_play.setFixedHeight(28)
        self.btn_play.setFocusPolicy(Qt.NoFocus)
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setToolTip("Extract and play stream (Enter)")
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.btn_play)
        content_layout.addLayout(input_layout)
        
        self.error_label = QLabel("", content_widget)
        self.error_label.setObjectName("streamErrorLabel")
        self.error_label.hide()
        content_layout.addWidget(self.error_label)
        
        layout.addWidget(content_widget)
        
        # Connections
        self.btn_mode_buffer.clicked.connect(lambda: self._set_mode("buffer"))
        self.btn_mode_direct.clicked.connect(lambda: self._set_mode("direct"))
        self._set_mode(self._current_mode)
        
        self.btn_play.clicked.connect(self._submit)
        self.input_field.returnPressed.connect(self._submit)
        
        # Install robust event filter for Spacebar and shortcut interception
        self.input_field.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self.input_field:
            if event.type() == QEvent.ShortcutOverride:
                # Stop Qt shortcut system from stealing Space, Backspace, or letters while typing
                if event.key() in (Qt.Key_Space, Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_P, Qt.Key_N, Qt.Key_L, Qt.Key_F, Qt.Key_R):
                    event.accept()
                    return True
            elif event.type() == QEvent.KeyPress:
                if (event.key() == Qt.Key_Y and bool(event.modifiers() & Qt.ControlModifier)) or event.key() == Qt.Key_Escape:
                    self.close_panel()
                    return True
                if event.key() == Qt.Key_Space:
                    self.input_field.insert(" ")
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _set_mode(self, mode: str):
        self._current_mode = mode
        self.btn_mode_buffer.setProperty("active", "true" if mode == "buffer" else "false")
        self.btn_mode_direct.setProperty("active", "true" if mode == "direct" else "false")
        self.btn_mode_buffer.style().unpolish(self.btn_mode_buffer)
        self.btn_mode_buffer.style().polish(self.btn_mode_buffer)
        self.btn_mode_direct.style().unpolish(self.btn_mode_direct)
        self.btn_mode_direct.style().polish(self.btn_mode_direct)
        
        from PySide6.QtCore import QSettings
        settings = QSettings("TDD131", "HELXAID")
        settings.setValue("MusicPlayer/stream_mode", mode)
        self.input_field.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            title_rect = self.title_bar.rect()
            title_mapped = self.title_bar.mapTo(self, title_rect.topLeft())
            drag_area = QRect(title_mapped, self.title_bar.size())
            click_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if drag_area.contains(click_pos):
                self._is_dragging = True
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self._drag_start_pos = global_pos - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(global_pos - self._drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Y and bool(event.modifiers() & Qt.ControlModifier)) or event.key() == Qt.Key_Escape:
            self.close_panel()
            return
        if event.key() == Qt.Key_Space:
            self.input_field.insert(" ")
            self.input_field.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_panel(self):
        self._is_closing = False
        self.error_label.hide()
        self.input_field.clear()
        self.show()
        self.raise_()
        self.input_field.setFocus()
        
        target_x = max(10, (self.parent().width() - self.width()) // 2) if self.parent() else self.x()
        target_y = max(10, (self.parent().height() - self.height()) // 2) if self.parent() else self.y()
        self.move(target_x, target_y)
            
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint
        if hasattr(self, '_anim') and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()
            
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setStartValue(QPoint(target_x, max(0, target_y - 25)))
        self._anim.setEndValue(QPoint(target_x, target_y))
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._anim.start()
        
    def close_panel(self):
        if getattr(self, '_is_closing', False):
            return
        self._is_closing = True
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint
        if hasattr(self, '_anim') and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()
            
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(180)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(self.x(), 10))
        self._anim.setEasingCurve(QEasingCurve.InBack)
        
        def on_finish():
            self.hide()
            self._is_closing = False
            
        self._anim.finished.connect(on_finish)
        self._anim.start()
        
    def animate_out(self):
        self.close_panel()

    def _submit(self):
        url = self.input_field.text().strip()
        if url:
            if "spotify.com" in url.lower():
                self.error_label.setText("Spotify DRM Restricted. Type media title instead.")
                self.error_label.show()
                
                import math
                from PySide6.QtCore import QVariantAnimation
                self._shake_var = QVariantAnimation(self)
                self._shake_var.setDuration(400)
                self._shake_var.setStartValue(0.0)
                self._shake_var.setEndValue(1.0)
                
                base_x = self.x()
                base_y = self.y()
                
                def on_shake(val):
                    offset = math.sin(val * math.pi * 6) * 10 * (1 - val)
                    self.move(int(base_x + offset), base_y)
                    
                self._shake_var.valueChanged.connect(on_shake)
                self._shake_var.start()
                return
                
            self.url_submitted.emit(url, self._current_mode)
            self.close_panel()


class StreamLoadingOverlayWidget(QFrame):
    """
    Floating draggable loading overlay with progress bar and collapsible console for Stream extraction.
    
    Component Name: StreamLoadingOverlayWidget
    """
    log_updated = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamLoadingOverlay")
        self.setFixedSize(460, 138)
        self.hide()
        
        self._is_dragging = False
        self._drag_start_pos = None
        
        # Obey UI Rule: Less use border, more use background-color
        self.setStyleSheet("""
            QFrame#streamLoadingOverlay {
                background-color: rgba(20, 21, 26, 0.98);
                border: none;
                border-radius: 10px;
            }
            QWidget#floatingStreamLoadingTitleBar {
                background-color: rgba(255, 255, 255, 0.03);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            }
            QLabel#floatingStreamLoadingTitleLabel {
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
                background: transparent;
            }
            QPushButton#floatingStreamLoadingCloseBtn {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
            }
            QPushButton#floatingStreamLoadingCloseBtn:hover {
                background-color: rgba(255, 255, 255, 0.12);
            }
            QWidget#streamLoadingContentWidget {
                background: transparent;
            }
            QLabel#lblMsg {
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 500;
                background: transparent;
                border: none;
            }
            QProgressBar#streamLoadingProgressBar {
                background-color: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 2px;
                min-height: 4px;
                max-height: 4px;
                height: 4px;
            }
            QProgressBar#streamLoadingProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 2px;
            }
            QPlainTextEdit#streamLoadingTerminal {
                background-color: rgba(12, 13, 17, 0.95);
                color: #B8B8B8;
                font-family: 'Consolas', 'Orbitron', monospace;
                font-size: 10px;
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QPushButton#streamLoadingToggleBtn {
                background-color: transparent;
                color: #888888;
                border: none;
                text-align: left;
                font-size: 10px;
                font-family: 'Orbitron', sans-serif;
                padding: 0px;
            }
            QPushButton#streamLoadingToggleBtn:hover {
                color: #FFFFFF;
            }
            QPushButton#streamLoadingCopyBtn {
                background-color: rgba(255, 255, 255, 0.06);
                color: #E0E0E0;
                border: none;
                border-radius: 5px;
                font-size: 10px;
                font-family: 'Orbitron', sans-serif;
                padding: 0 10px;
                min-height: 24px;
                max-height: 24px;
                height: 24px;
            }
            QPushButton#streamLoadingCopyBtn:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
            QPushButton#streamLoadingCloseBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                font-size: 10px;
                font-family: 'Orbitron', sans-serif;
                font-weight: 600;
                padding: 0 14px;
                min-height: 24px;
                max-height: 24px;
                height: 24px;
            }
            QPushButton#streamLoadingCloseBtn:hover {
                background-color: rgba(220, 53, 69, 0.85);
            }
            QPushButton#streamLoadingCloseBtn:pressed {
                background-color: #C82333;
            }
        """)
        
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setColor(QColor(0, 0, 0, 180))
            shadow.setOffset(0, 8)
            self.setGraphicsEffect(shadow)
        except Exception:
            pass
            
        from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QPlainTextEdit, QPushButton
        from PySide6.QtGui import QPixmap, QIcon
        from PySide6.QtCore import Qt, QSize, QPoint
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Draggable Title Bar (32px)
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("floatingStreamLoadingTitleBar")
        self.title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 0, 10, 0)
        title_layout.setSpacing(8)
        title_layout.setAlignment(Qt.AlignVCenter)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        panel_icon_path = os.path.join(script_dir, "UI Icons", "open-white.svg").replace('\\', '/')
        
        icon_lbl = QLabel(self.title_bar)
        icon_lbl.setObjectName("floatingStreamLoadingIconLabel")
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setScaledContents(True)
        if os.path.exists(panel_icon_path):
            icon_lbl.setPixmap(QPixmap(panel_icon_path))
        title_layout.addWidget(icon_lbl, 0, Qt.AlignVCenter)
        
        self.lbl_tag = QLabel("STREAM EXTRACTION", self.title_bar)
        self.lbl_tag.setObjectName("floatingStreamLoadingTitleLabel")
        title_layout.addWidget(self.lbl_tag, 0, Qt.AlignVCenter)
        title_layout.addStretch(1)
        
        self.btn_close_header = QPushButton(self.title_bar)
        self.btn_close_header.setObjectName("floatingStreamLoadingCloseBtn")
        self.btn_close_header.setFixedSize(22, 22)
        self.btn_close_header.setCursor(Qt.PointingHandCursor)
        self.btn_close_header.setToolTip("Close")
        self.btn_close_header.setIcon(_render_svg_icon_sharp(SVG_CLOSE_ICON, size=10, color="#FFFFFF"))
        self.btn_close_header.setIconSize(QSize(10, 10))
        self.btn_close_header.clicked.connect(self.hide)
        title_layout.addWidget(self.btn_close_header, 0, Qt.AlignVCenter)
        
        layout.addWidget(self.title_bar)
        
        # Content Area
        content_widget = QWidget(self)
        content_widget.setObjectName("streamLoadingContentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 8, 14, 10)
        content_layout.setSpacing(6)
        
        self.lbl_msg = QLabel("Extracting stream URL...", content_widget)
        self.lbl_msg.setObjectName("lblMsg")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        self.lbl_msg.setWordWrap(True)
        content_layout.addWidget(self.lbl_msg)
        
        self.progress = QProgressBar(content_widget)
        self.progress.setObjectName("streamLoadingProgressBar")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        content_layout.addWidget(self.progress)
        
        self.terminal = QPlainTextEdit(content_widget)
        self.terminal.setObjectName("streamLoadingTerminal")
        self.terminal.setReadOnly(True)
        self.terminal.setMaximumBlockCount(150)
        self.terminal.setFixedHeight(110)
        self.terminal.hide()
        self.terminal.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        content_layout.addWidget(self.terminal)
        
        # Footer Action Row
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 2, 0, 0)
        footer_layout.setSpacing(6)
        
        self.btn_toggle = QPushButton("▶ Show Details", content_widget)
        self.btn_toggle.setObjectName("streamLoadingToggleBtn")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        
        def toggle_terminal():
            if self.terminal.isHidden():
                self.terminal.show()
                self.btn_copy.show()
                self.btn_toggle.setText("▼ Hide Details")
                self.setFixedSize(460, 265)
                if self.parent() and not getattr(self, '_is_dragging', False):
                    self.move(max(10, (self.parent().width() - 460) // 2), max(10, (self.parent().height() - 265) // 2))
            else:
                self.terminal.hide()
                self.btn_copy.hide()
                self.btn_toggle.setText("▶ Show Details")
                self.setFixedSize(460, 138)
                if self.parent() and not getattr(self, '_is_dragging', False):
                    self.move(max(10, (self.parent().width() - 460) // 2), max(10, (self.parent().height() - 138) // 2))
            
        self.btn_toggle.clicked.connect(toggle_terminal)
        footer_layout.addWidget(self.btn_toggle)
        footer_layout.addStretch()
        
        self.btn_copy = QPushButton("Copy Log", content_widget)
        self.btn_copy.setObjectName("streamLoadingCopyBtn")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_log)
        self.btn_copy.hide()
        footer_layout.addWidget(self.btn_copy)
        
        self.btn_close = QPushButton("Close", content_widget)
        self.btn_close.setObjectName("streamLoadingCloseBtn")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        footer_layout.addWidget(self.btn_close)
        
        content_layout.addLayout(footer_layout)
        layout.addWidget(content_widget)
        
        self.log_updated.connect(self._append_log)
        
    def mousePressEvent(self, event):
        from PySide6.QtCore import Qt, QRect
        if event.button() == Qt.LeftButton:
            title_rect = self.title_bar.rect()
            title_mapped = self.title_bar.mapTo(self, title_rect.topLeft())
            drag_area = QRect(title_mapped, self.title_bar.size())
            click_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if drag_area.contains(click_pos):
                self._is_dragging = True
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self._drag_start_pos = global_pos - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        from PySide6.QtCore import Qt
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(global_pos - self._drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def _copy_log(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.terminal.toPlainText())
        self.btn_copy.setText("Copied!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("Copy Log") if hasattr(self, 'btn_copy') else None)
        
    def log_msg(self, msg):
        """Thread-safe log message emission."""
        if hasattr(self, 'log_updated'):
            self.log_updated.emit(str(msg))
        else:
            self._append_log(str(msg))

    def _append_log(self, msg):
        self.terminal.appendPlainText(msg.strip())
        bar = self.terminal.verticalScrollBar()
        bar.setValue(bar.maximum())
        
    def show_msg(self, msg):
        self.lbl_msg.setText(msg)
        self.terminal.clear()
        self.setFixedSize(460, 138)
        self.show()
        self.raise_()
        if self.parent():
            x = max(10, (self.parent().width() - self.width()) // 2)
            y = max(10, (self.parent().height() - self.height()) // 2)
            self.move(x, y)
            
    def finish_and_close_with_countdown(self):
        self.progress.setMaximum(100)
        self.progress.setValue(100)
        self.lbl_msg.setText("Done! Added to playlist.")
        
        self.btn_close.setStyleSheet("""
            QPushButton#streamLoadingCloseBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                font-size: 10px;
                font-family: 'Orbitron', sans-serif;
                font-weight: 600;
                padding: 0 14px;
                min-height: 24px;
                max-height: 24px;
                height: 24px;
            }
            QPushButton#streamLoadingCloseBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7326, stop:1 #FFBA24);
            }
        """)
        
        # Check Developer Mode toggle: keep panel open without auto-close countdown
        from PySide6.QtCore import QSettings
        settings = QSettings("TDD131", "HELXAID")
        is_dev = settings.value("Developer/developer_mode", False, type=bool)
        no_auto_close = is_dev and settings.value("Developer/stream_extract_no_auto_close", False, type=bool)
        
        if no_auto_close:
            if hasattr(self, '_countdown_timer'):
                self._countdown_timer.stop()
            if hasattr(self, '_countdown'):
                delattr(self, '_countdown')
            self.btn_close.setText("Close")
            return
        
        self._countdown = 3
        self.btn_close.setText(f"Closing in {self._countdown}...")
        
        if not hasattr(self, '_hover_filter_installed'):
            self.btn_close.installEventFilter(self)
            self._hover_filter_installed = True
            
        from PySide6.QtCore import QTimer
        if hasattr(self, '_countdown_timer'):
            self._countdown_timer.stop()
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_timer.start(1000)

    def _on_countdown_tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown_timer.stop()
            self.hide()
        else:
            if not self.btn_close.underMouse():
                self.btn_close.setText(f"Closing in {self._countdown}...")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self.btn_close and hasattr(self, '_countdown'):
            if event.type() == QEvent.Enter:
                self.btn_close.setText("Close")
            elif event.type() == QEvent.Leave:
                self.btn_close.setText(f"Closing in {self._countdown}...")
        return super().eventFilter(obj, event)

    def _reset_ui(self):
        if hasattr(self, 'progress'):
            self.progress.setRange(0, 0)
        if hasattr(self, '_countdown_timer'):
            self._countdown_timer.stop()
        if hasattr(self, '_countdown'):
            delattr(self, '_countdown')
        if hasattr(self, 'btn_close'):
            self.btn_close.setText("Close")
            self.btn_close.setStyleSheet("""
                QPushButton#streamLoadingCloseBtn {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #FFFFFF;
                    border: none;
                    border-radius: 5px;
                    font-size: 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-weight: 600;
                    padding: 0 14px;
                    min-height: 24px;
                    max-height: 24px;
                    height: 24px;
                }
                QPushButton#streamLoadingCloseBtn:hover {
                    background-color: rgba(220, 53, 69, 0.85);
                }
            """)
        if hasattr(self, 'terminal'):
            self.terminal.hide()
        if hasattr(self, 'btn_copy'):
            self.btn_copy.hide()
        if hasattr(self, 'btn_toggle'):
            self.btn_toggle.setText("▶ Show Details")
        self.setFixedSize(460, 138)

    def hideEvent(self, event):
        self._reset_ui()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            x = max(10, (self.parent().width() - self.width()) // 2)
            y = max(10, (self.parent().height() - self.height()) // 2)
            self.move(x, y)


class MusicPanelWidget(QWidget):
    """
    Main Music Panel - Native Qt replica of HTML5 music panel.
    
    Component Name: MusicPanelWidget
    """
    
    # Signal emitted when playback state changes (for taskbar integration)
    from PySide6.QtCore import Signal
    playbackStateChanged = Signal(object)  # Emits QMediaPlayer.PlaybackState
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MusicPanelWidget")
        self.setFocusPolicy(Qt.ClickFocus)
        self.setAcceptDrops(True)
        
        # Check FFmpeg availability first
        self._ffmpeg_available = self._check_ffmpeg()
        
        if not self._ffmpeg_available:
            # Create dummy attributes to prevent AttributeError
            self._player = None
            self._audio_output = None
            self._playlist = []
            self._current_index = -1
            self._setup_ffmpeg_required_ui()
            return
        
        # Qt Multimedia player (lazy loaded on tick 0)
        self._player = None
        self._audio_output = None
        QTimer.singleShot(0, self._ensure_player)
        
        # Secondary player for crossfade (lazy loaded on demand)
        self._player2 = None
        self._audio_output2 = None
        
        # Crossfade state
        self._crossfade_enabled = True  # Enabled by default
        self._crossfade_duration = 3.0  # Default 3 seconds
        self._crossfade_active = False
        self._crossfade_timer = None
        self._active_player = 1  # 1 or 2, indicates which player is "main"
        self._user_volume = 1.0  # Store user's volume preference
        
        # State
        self._playlist = []
        self._current_index = -1
        self._shuffled_sequence = []
        self._shuffled_pointer = -1
        self._music_folder = None

        self._helxaic_page_visible = False
        self._render_gate_reason = None

        self._is_maximized = False
        self._initial_state_loaded = False

        # Internal state
        self._rtss_excluded_once = False
        
        # Discord Rich Presence (deferred by 1s for zero-latency page switch)
        self._discord = None
        QTimer.singleShot(1000, self._init_discord)
        
        # Config file for persistence (use AppData for bundled exe)
        appdata_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
        os.makedirs(appdata_dir, exist_ok=True)
        self._config_path = os.path.join(appdata_dir, "music_page.json")
        
        self._setup_ui()
        self._connect_signals()

        try:
            app = QApplication.instance()
            if app:
                app.applicationStateChanged.connect(self._on_app_state_changed_for_render_gate)
        except Exception:
            pass
        
        # Ensure minimum height so PlayerBar never gets clipped
        self.setMinimumHeight(400)  # Menu(30) + Header(~200) + PlayerBar(75) + margin
        
        # Restore last state (deferred to singleShot for zero-latency UI show)
        QTimer.singleShot(0, self._load_last_state)
        
        # If no playlist was loaded from the last state, ensure the default playlist's cover is still loaded
        if not getattr(self, '_playlist', None) and hasattr(self, 'header'):
            self.header.load_saved_cover(self.header.playlist_title.text())
        
        # Connect to app exit signal for final state save
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._save_state)
        
        # Start global media key listener and taskbar widget (ready quickly after UI init)
        QTimer.singleShot(100, self._setup_media_key_service)
        
        # Auto RAM Trimmer (debounced working set trim)
        self._ram_trim_timer = QTimer(self)
        self._ram_trim_timer.setSingleShot(True)
        self._ram_trim_timer.timeout.connect(trim_current_process_memory)
        self.schedule_ram_trim(3000)
        
        # Monitor audio device changes (deferred by 2s)
        # connects (e.g. Bluetooth headphones, USB DAC)
        QTimer.singleShot(2000, self._setup_audio_device_monitor)
        
        print("[Music] Native Qt MusicPanelWidget initialized")

    def _is_app_render_allowed(self) -> bool:
        try:
            if QApplication.applicationState() != Qt.ApplicationActive:
                return False
        except Exception:
            return False

        try:
            mw = self.window()
            if mw and mw.isMinimized():
                return False
        except Exception:
            pass

        return True



    def schedule_ram_trim(self, delay_ms: int = 2000):
        """Schedule a debounced working set memory trim."""
        if hasattr(self, '_ram_trim_timer'):
            self._ram_trim_timer.start(delay_ms)

    def on_helxaic_page_hidden(self):
        self._helxaic_page_visible = False
        self.schedule_ram_trim(500)

    def on_helxaic_page_shown(self):
        self._helxaic_page_visible = True

    def _on_app_state_changed_for_render_gate(self, state):
        pass
    
    def showEvent(self, event):
        """Force layout update when widget is shown to prevent PlayerBar clipping."""
        super().showEvent(event)
        # Force immediate layout recalculation
        self.updateGeometry()
        if hasattr(self, 'player_bar'):
            self.player_bar.updateGeometry()
            self.player_bar.update()
            
            # Refresh duration explicitly if VLC or QMediaPlayer is currently active
            try:
                if hasattr(self, '_player') and self._player:
                    pos = self._player.position()
                    dur = self._player.duration()
                    if dur > 0:
                        self.player_bar.set_position(pos / 1000.0, dur / 1000.0)
                        if hasattr(self, '_playlist') and 0 <= self._current_index < len(self._playlist):
                            track = self._playlist[self._current_index]
                            if track.get('duration', 0) == 0:
                                track['duration'] = dur / 1000.0
                                if hasattr(self, 'table'): self.table._render_tracks()
            except Exception:
                pass
                
        if hasattr(self, 'resume_banner') and not self.resume_banner.isHidden():
            if hasattr(self.resume_banner, 'update_position'):
                self.resume_banner.update_position()
            self.resume_banner.raise_()

        # Show and sync taskbar media widget when HELXAIC panel is viewed
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            if getattr(self, '_taskbar_widget_enabled', True):
                self._taskbar_media_widget.show()
                self._taskbar_media_widget.sync_position()
                self._taskbar_media_widget.raise_()
        elif getattr(self, '_taskbar_widget_enabled', True):
            self._setup_media_key_service()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available in AppData tools path."""
        try:
            from integrations.tools_downloader import is_ffmpeg_available
            return is_ffmpeg_available()
        except ImportError:
            from integrations.tools_downloader import get_ffmpeg_path
            return os.path.exists(get_ffmpeg_path())
    
    def _setup_ffmpeg_required_ui(self):
        """Setup placeholder UI when FFmpeg is not available."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Main container
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a0a, stop:0.5 #1a1a1a, stop:1 #0a0a0a);
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setSpacing(20)
        
        # Icon
        icon_label = QLabel("")
        icon_label.setStyleSheet("font-size: 64px; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(icon_label)
        
        # Title
        title = QLabel("FFmpeg Required")
        title.setStyleSheet("color: #e0e0e0; font-size: 28px; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Description
        desc = QLabel("Music Player requires FFmpeg for audio/video playback.\nClick below to download and install it automatically.")
        desc.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        desc.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(desc)
        
        # Download button
        download_btn = QPushButton("Download FFmpeg")
        download_btn.setFixedSize(220, 50)
        download_btn.setCursor(QCursor(Qt.PointingHandCursor))
        download_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                color: #1a1a1a;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:1 #FFD700);
            }
        """)
        download_btn.clicked.connect(self._download_ffmpeg)
        container_layout.addWidget(download_btn, alignment=Qt.AlignCenter)
        
        layout.addWidget(container)
    
    def _download_ffmpeg(self):
        """Download FFmpeg using tools_downloader and restart app."""
        try:
            from integrations.tools_downloader import ensure_ffmpeg
            ensure_ffmpeg(self)
        except ImportError as e:
            print(f"[Music] Failed to import tools_downloader: {e}")
    
    def _setup_media_key_service(self):
        """Initialize global media key listener and Windows SMTC service for hardware media controls.
        
        1. WindowsSMTCService: Native Windows 10/11 System Media Transport Controls
           Enables Bluetooth AVRCP (TWS earbuds, wireless headphones), lock screen controls,
           and Windows Volume overlay display without requiring window focus or physical keyboard input.
        
        2. MediaKeyService: Low-level Win32 keyboard hook (WH_KEYBOARD_LL)
           Non-exclusive fallback for USB hardware knobs, external macro pads, and Fn media keys.
        """
        # 1. Native Windows SMTC Service (Bluetooth AVRCP & Lock Screen)
        try:
            from WindowsSMTCService import WindowsSMTCService
            self._smtc_service = WindowsSMTCService(self)
            if self._smtc_service.is_available:
                self._smtc_service.play_requested.connect(self._play_current_or_resume)
                self._smtc_service.pause_requested.connect(self._pause_playback)
                self._smtc_service.toggle_play_requested.connect(self._toggle_play)
                self._smtc_service.next_requested.connect(self._next_track)
                self._smtc_service.prev_requested.connect(self._prev_track)
                self._smtc_service.stop_requested.connect(
                    lambda: self._player.stop() if self._player else None
                )
                print("[Music] Windows SMTC Service connected to HELXAIC (Bluetooth AVRCP active)")
            else:
                self._smtc_service = None
        except Exception as e:
            self._smtc_service = None
            print(f"[Music] Windows SMTC Service init failed: {e}")

        # 2. Win32 Low-Level Keyboard Hook
        try:
            from MediaKeyService import MediaKeyService
            
            self._media_key_service = MediaKeyService(self)
            
            # Connect media key signals to playback controls
            self._media_key_service.play_pause.connect(self._toggle_play)
            self._media_key_service.next_track.connect(self._next_track)
            self._media_key_service.prev_track.connect(self._prev_track)
            self._media_key_service.stop_playback.connect(
                lambda: self._player.stop() if self._player else None
            )
            
            # Start the global listener
            self._media_key_service.start()
            print("[Music] Global media key service started (all devices)")
            
        except ImportError as e:
            # MediaKeyService.py not found - degrade gracefully.
            self._media_key_service = None
            print(f"[Music] MediaKeyService not available: {e}")
        except Exception as e:
            # Unexpected error - log but don't crash the music panel
            self._media_key_service = None
            print(f"[Music] Failed to start media key service: {e}")

        # 3. Native Taskbar Docked Media Controls (Directly on Windows Taskbar)
        try:
            from TaskbarMediaWidget import TaskbarMediaWidget
            if not hasattr(self, '_taskbar_media_widget') or self._taskbar_media_widget is None:
                self._taskbar_media_widget = TaskbarMediaWidget(self)
                self._taskbar_media_widget.prev_clicked.connect(self._prev_track)
                self._taskbar_media_widget.playpause_clicked.connect(self._toggle_play)
                self._taskbar_media_widget.next_clicked.connect(self._next_track)
                self._taskbar_media_widget.title_clicked.connect(self._bring_helxaic_to_front)
                self._taskbar_media_widget.close_clicked.connect(self._hide_taskbar_media_widget)
                self._taskbar_media_widget.state_changed.connect(self._save_state)
                
                # Apply saved position mode & opacity (default: left near start, 75% opacity)
                saved_pos = getattr(self, '_taskbar_widget_position', 'left')
                saved_opacity = getattr(self, '_taskbar_widget_opacity', 75)
                self._taskbar_media_widget.set_position_mode(saved_pos)
                self._taskbar_media_widget.set_widget_opacity(saved_opacity)
                
                # Sync current state
                from PySide6.QtMultimedia import QMediaPlayer
                is_playing = (self._player.playbackState() == QMediaPlayer.PlayingState) if hasattr(self, '_player') and self._player else False
                self._taskbar_media_widget.set_playback_state(is_playing)
                
                current_title = ""
                current_artist = ""
                if hasattr(self, '_playlist') and self._playlist and 0 <= getattr(self, '_current_index', -1) < len(self._playlist):
                    track = self._playlist[self._current_index]
                    current_title = track.get('title', '')
                    current_artist = track.get('artist', '')
                
                if not current_title and hasattr(self, 'player_bar') and hasattr(self.player_bar, 'title_label'):
                    txt = self.player_bar.title_label.text()
                    if txt and txt != "No track playing":
                        current_title = txt
                        current_artist = self.player_bar.artist_label.text() if hasattr(self.player_bar, 'artist_label') else ""
                
                if current_title:
                    self._taskbar_media_widget.set_track_info(current_title, current_artist if current_artist != "-" else "")
                
                # Only show immediately if HELXAIC panel is currently visible or music is currently playing
                if getattr(self, '_taskbar_widget_enabled', True) and (self.isVisible() or is_playing):
                    self._taskbar_media_widget.show()
                    self._taskbar_media_widget.sync_position()
                    self._taskbar_media_widget.raise_()
                print("[Music] Taskbar Media Widget docked to Windows Taskbar")
        except Exception as e:
            self._taskbar_media_widget = None
            print(f"[Music] Taskbar Media Widget init error: {e}")

    def _bring_helxaic_to_front(self):
        """Restore and raise HELXAID window directly to the HELXAIC music page."""
        try:
            main_win = self.window()
            if main_win:
                if main_win.isMinimized():
                    main_win.showNormal()
                main_win.show()
                main_win.raise_()
                main_win.activateWindow()
                if hasattr(main_win, 'switch_panel'):
                    main_win.switch_panel(1)
        except Exception as e:
            print(f"[Music] Error bringing HELXAIC to front: {e}")

    def _hide_taskbar_media_widget(self):
        """Hide the taskbar widget and persist user preference."""
        self._taskbar_widget_enabled = False
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            self._taskbar_media_widget.hide()
        if hasattr(self, 'action_taskbar_enable'):
            self.action_taskbar_enable.blockSignals(True)
            self.action_taskbar_enable.setChecked(False)
            self.action_taskbar_enable.blockSignals(False)
        self._save_state()

    def toggle_taskbar_media_widget(self, enabled=None):
        """Toggle or set taskbar widget visibility."""
        if enabled is None:
            self._taskbar_widget_enabled = not getattr(self, '_taskbar_widget_enabled', True)
        else:
            self._taskbar_widget_enabled = bool(enabled)
            
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            if self._taskbar_widget_enabled:
                self._taskbar_media_widget.show()
                self._taskbar_media_widget.sync_position()
            else:
                self._taskbar_media_widget.hide()
        elif self._taskbar_widget_enabled:
            self._setup_media_key_service()
            
        if hasattr(self, 'action_taskbar_enable'):
            self.action_taskbar_enable.blockSignals(True)
            self.action_taskbar_enable.setChecked(self._taskbar_widget_enabled)
            self.action_taskbar_enable.blockSignals(False)
            
        self._save_state()

    def set_taskbar_media_position(self, mode: str):
        """Change taskbar widget position and persist setting."""
        self._taskbar_widget_position = mode
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            self._taskbar_media_widget.set_position_mode(mode)
        
        # Sync menu checkmarks
        if hasattr(self, '_taskbar_pos_actions'):
            for m_key, action in self._taskbar_pos_actions.items():
                action.blockSignals(True)
                action.setChecked(m_key == mode)
                action.blockSignals(False)
                
        self._save_state()

    def _play_current_or_resume(self):
        """Resume playback if paused, or play current/first track."""
        if not hasattr(self, '_player') or self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() != QMediaPlayer.PlayingState:
            self._toggle_play()

    def _pause_playback(self):
        """Pause playback if currently playing."""
        if not hasattr(self, '_player') or self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
    
    def _setup_audio_device_monitor(self):
        """Set up automatic audio device switching when new devices connect.
        
        Uses QMediaDevices.audioOutputsChanged to detect when audio
        output devices are added or removed. When a new device appears
        (e.g. Bluetooth headphones connecting, USB DAC plugged in),
        automatically switches the audio output to the new device.
        
        This provides seamless audio routing - plug in headphones and
        music automatically plays through them without manual switching.
        
        The monitor keeps a snapshot of currently known device IDs to
        detect which devices are "new" vs already present.
        """
        try:
            from PySide6.QtMultimedia import QMediaDevices
            
            # QMediaDevices must be kept alive as a member to receive signals
            self._media_devices = QMediaDevices(self)
            
            # Take initial snapshot of connected devices (by ID)
            # so we can detect newly added devices later
            self._known_device_ids = set()
            for device in QMediaDevices.audioOutputs():
                self._known_device_ids.add(device.id().data().decode() if isinstance(device.id(), (bytes, bytearray)) else str(device.id()))
            
            # Connect the change signal
            self._media_devices.audioOutputsChanged.connect(self._on_audio_devices_changed)
            
            print(f"[Audio] Device monitor started, tracking {len(self._known_device_ids)} device(s)")
            
        except Exception as e:
            print(f"[Audio] Device monitor setup failed: {e}")
            self._media_devices = None
            self._known_device_ids = set()
    
    def _on_audio_devices_changed(self):
        """Handle audio output device list changes.
        
        Called by Qt when audio devices are added or removed.
        Compares current device list against the known snapshot
        to identify newly connected devices. If a new device is
        found, auto-switches audio output to it.
        
        Device removal (e.g. Bluetooth disconnecting) is handled
        automatically by Qt - it falls back to the default device.
        """
        try:
            from PySide6.QtMultimedia import QMediaDevices
            
            current_devices = QMediaDevices.audioOutputs()
            current_ids = set()
            new_devices = []
            
            for device in current_devices:
                dev_id = device.id().data().decode() if isinstance(device.id(), (bytes, bytearray)) else str(device.id())
                current_ids.add(dev_id)
                
                # Check if this is a newly connected device
                if dev_id not in self._known_device_ids:
                    new_devices.append(device)
            
            # Update known devices snapshot
            self._known_device_ids = current_ids
            
            if new_devices:
                # Switch to the most recently added device
                # (usually the one the user just connected)
                new_device = new_devices[-1]
                print(f"[Audio] New device detected: {new_device.description()}")
                print(f"[Audio] Auto-switching output to: {new_device.description()}")
                
                # Switch both the main player and crossfade player
                if self._audio_output:
                    self._audio_output.setDevice(new_device)
                if hasattr(self, '_audio_output2') and self._audio_output2:
                    self._audio_output2.setDevice(new_device)
                
                # Update VLC player output if active
                if getattr(self, '_playing_vlc', False) and hasattr(self, '_vlc_player') and self._vlc_player:
                    try:
                        # VLC uses its own audio routing - set the device name
                        self._vlc_player.audio_output_device_set(None, new_device.description())
                        print(f"[Audio] VLC output switched to: {new_device.description()}")
                    except Exception:
                        pass
                
                print(f"[Audio] Output device auto-switched successfully")
            else:
                # Device removed - Qt handles fallback automatically
                removed = self._known_device_ids - current_ids
                if removed:
                    print(f"[Audio] Device(s) removed, Qt will fallback to default")
                    
        except Exception as e:
            print(f"[Audio] Device change handling error: {e}")

    def show_invalid_path_panel(self, message="The path is invalid or the file is deleted."):
        """Display floating invalid path notification overlay matching HELXAIL UI."""
        from MediaLibraryPage import FloatingInvalidPathPanel
        if not hasattr(self, '_invalid_path_panel') or self._invalid_path_panel is None:
            self._invalid_path_panel = FloatingInvalidPathPanel(self, message)
        self._invalid_path_panel.show_panel()

    def reload_current_view(self):
        """Reload/refresh tracks for whichever tab/view is currently active in HELXAIC."""
        if hasattr(self, 'stack'):
            idx = self.stack.currentIndex()
            if idx == 1 and hasattr(self, 'media_lib_page'):
                print("[MusicPanelWidget] Reloading Media Library...")
                if hasattr(self.media_lib_page, 'load_library'):
                    self.media_lib_page.load_library()
                return

        # Default / Playlist page (idx == 0):
        if hasattr(self, '_music_folder') and self._music_folder and os.path.exists(self._music_folder):
            print(f"[MusicPanelWidget] Rescanning current folder: {self._music_folder}")
            self._load_tracks_from_folder(self._music_folder)
        elif hasattr(self, '_playlist') and hasattr(self, 'table'):
            print("[MusicPanelWidget] Refreshing track playlist and purging missing files...")
            valid_playlist = []
            for t in self._playlist:
                if isinstance(t, dict):
                    path = t.get('path')
                    # Keep online tracks or local files that still exist on disk
                    if t.get('is_online', False) or (path and os.path.exists(path)):
                        valid_playlist.append(t)
            if len(valid_playlist) != len(self._playlist):
                print(f"[MusicPanelWidget] Removed {len(self._playlist) - len(valid_playlist)} missing/deleted track(s)")
                self._playlist = valid_playlist
                if hasattr(self, '_save_state'):
                    self._save_state()
            self.table.set_tracks(self._playlist)
            if hasattr(self, 'refresh_playlist_stats'):
                self.refresh_playlist_stats()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts and media keys for music control."""
        if hasattr(self, 'floating_url_input') and self.floating_url_input.isVisible():
            super().keyPressEvent(event)
            return

        from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        
        # === Hardware & Multimedia Key Events (from OS / WM_APPCOMMAND) ===
        if key in (Qt.Key_MediaTogglePlayPause, Qt.Key_MediaPlay, Qt.Key_MediaPause):
            self._toggle_play()
            event.accept()
            return
        elif key == Qt.Key_MediaNext:
            self._next_track()
            event.accept()
            return
        elif key == Qt.Key_MediaPrevious:
            self._prev_track()
            event.accept()
            return
        elif key == Qt.Key_MediaStop:
            if hasattr(self, '_player') and self._player:
                self._player.stop()
            event.accept()
            return

        # === Standard Keyboard Shortcuts ===
        
        # Spacebar: Play/Pause
        if key == Qt.Key_Space:
            self._toggle_play()
            event.accept()
            return
        
        # P: Previous track (always wraps, regardless of loop mode)
        if key == Qt.Key_P:
            self._prev_track(force_wrap=True)
            event.accept()
            return
        
        # N: Next track (always wraps, regardless of loop mode)
        if key == Qt.Key_N:
            self._next_track(force_wrap=True)
            event.accept()
            return
        
        # L: Loop toggle
        if key == Qt.Key_L:
            self.player_bar._toggle_loop()
            event.accept()
            return
        
        # Ctrl + R or F5: Reload currently viewed tracks
        if key == Qt.Key_F5 or (key == Qt.Key_R and bool(modifiers & Qt.ControlModifier)):
            self.reload_current_view()
            event.accept()
            return

        # R (standalone without Ctrl): Shuffle toggle
        if key == Qt.Key_R and not bool(modifiers & Qt.ControlModifier):
            self.player_bar._toggle_shuffle()
            event.accept()
            return
        
        # F: Toggle fullscreen
        if key == Qt.Key_F:
            try:
                self._toggle_fullscreen()
            except Exception:
                pass
            event.accept()
            return
        
        # Escape: Exit fullscreen
        if key == Qt.Key_Escape:
            if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
                try:
                    self._toggle_fullscreen()
                except Exception:
                    pass
                event.accept()
                return
        
        # Left Arrow: Rewind 5 seconds
        if key == Qt.Key_Left:
            current_pos = self._player.position()
            new_pos = max(0, current_pos - 5000)  # 5000ms = 5 seconds
            self._player.setPosition(new_pos)
            event.accept()
            return
        
        # Right Arrow: Forward 5 seconds
        if key == Qt.Key_Right:
            current_pos = self._player.position()
            duration = self._player.duration()
            new_pos = min(duration, current_pos + 5000)  # 5000ms = 5 seconds
            self._player.setPosition(new_pos)
            event.accept()
            return
            
        # Up Arrow: Volume Up 5%
        if key == Qt.Key_Up:
            if hasattr(self, 'player_bar'):
                current_vol = self.player_bar.volume_slider.value()
                self.player_bar.volume_slider.setValue(min(125, current_vol + 5))
            event.accept()
            return
            
        # Down Arrow: Volume Down 5%
        if key == Qt.Key_Down:
            if hasattr(self, 'player_bar'):
                current_vol = self.player_bar.volume_slider.value()
                self.player_bar.volume_slider.setValue(max(0, current_vol - 5))
            event.accept()
            return
        
        # Pass to parent if not handled
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        # If Media Library tab is active (index 1), delegate directly to media_lib_page
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1:
            if hasattr(self, 'media_lib_page') and self.media_lib_page:
                if hasattr(self.media_lib_page, 'tree') and event.source() == self.media_lib_page.tree:
                    event.ignore()
                    return
                urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
                paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
                if paths:
                    self.media_lib_page._process_dropped_paths(paths)
                    event.acceptProposedAction()
            return
            
        # Ignore internal drops from the playlist itself to prevent accidental track duplication and playback
        if hasattr(self, 'table') and event.source() == self.table.tree:
            event.ignore()
            return
            
        urls = event.mimeData().urls()
        if urls:
            paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if not paths:
                return
            
            import os
            import datetime
            audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
            
            if not hasattr(self, '_playlist'):
                self._playlist = []
                
            start_idx = len(self._playlist)
            tracks_to_add = []
            
            for path in paths:
                if os.path.isdir(path):
                    folder_name = os.path.basename(path) or path
                    folder_tracks = []
                    try:
                        for entry in os.scandir(path):
                            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in audio_exts:
                                title = os.path.splitext(entry.name)[0]
                                try:
                                    mtime = entry.stat().st_mtime
                                    dt = datetime.datetime.fromtimestamp(mtime)
                                    date_str = dt.strftime("%b %d, %Y")
                                except Exception:
                                    date_str = ""
                                folder_tracks.append({
                                    'path': entry.path,
                                    'title': title,
                                    'artist': 'Dropped File',
                                    'duration': 0,
                                    'date_added': date_str,
                                    'playlist_group': folder_name
                                })
                    except Exception:
                        pass
                    tracks_to_add.extend(folder_tracks)
                elif os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if ext in audio_exts:
                        title = os.path.splitext(os.path.basename(path))[0]
                        try:
                            mtime = os.path.getmtime(path)
                            dt = datetime.datetime.fromtimestamp(mtime)
                            date_str = dt.strftime("%b %d, %Y")
                        except Exception:
                            date_str = ""
                            
                        tracks_to_add.append({
                            'path': path,
                            'title': title,
                            'artist': 'Dropped File',
                            'duration': 0,
                            'date_added': date_str
                        })
                        
            if tracks_to_add:
                self._playlist.extend(tracks_to_add)
                if hasattr(self, 'table'):
                    self.table.set_tracks(self._playlist)
                self._save_state()
                self.refresh_playlist_stats()
                if hasattr(self, '_track_count_label'):
                    self._track_count_label.setText(f"{len(self._playlist)} tracks")
                
                # Fetch metadata asynchronously for the newly added tracks
                self._fetch_metadata_async(self._playlist, "Playlist")
                # Removed autoplay on drag & drop per user request
                # self._play_track(start_idx)
    
    def _create_music_sidebar(self, parent_container):
        class SidebarWidget(QWidget):
            def __init__(self, parent_panel):
                super().__init__()
                self.parent_panel = parent_panel
                self.setMaximumWidth(200)
                self.setMinimumWidth(50)
                self.setObjectName("musicSidebar")
                self._transitioning = False
                self.setAcceptDrops(True)
                
                from PySide6.QtCore import QTimer
                self._drag_hover_timer = QTimer(self)
                self._drag_hover_timer.setSingleShot(True)
                self._drag_hover_timer.timeout.connect(self._on_drag_hover_timeout)
                self._drag_hover_target = None
                
            def _on_drag_hover_timeout(self):
                p = self.parent_panel
                w = self._drag_hover_target
                if not w: return
                if hasattr(p, 'stack') and hasattr(p, 'btn_playlist') and hasattr(p, 'btn_media_lib'):
                    if w == p.btn_playlist and p.stack.currentIndex() != 0:
                        p.btn_playlist.click()
                    elif w == p.btn_media_lib and p.stack.currentIndex() != 1:
                        p.btn_media_lib.click()
                
            def dragEnterEvent(self, event):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    
            def dragMoveEvent(self, event):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    try:
                        pos = event.position().toPoint()
                    except AttributeError:
                        pos = event.pos()
                        
                    w = self.childAt(pos)
                    # If we hover over a different button, restart the timer
                    if w != self._drag_hover_target:
                        self._drag_hover_target = w
                        self._drag_hover_timer.stop()
                        if w in (getattr(self.parent_panel, 'btn_playlist', None), getattr(self.parent_panel, 'btn_media_lib', None)):
                            self._drag_hover_timer.start(400) # 400ms delay to switch tab
                            
            def dragLeaveEvent(self, event):
                self._drag_hover_timer.stop()
                self._drag_hover_target = None
                            
            def dropEvent(self, event):
                # Consume the drop event so it doesn't bubble up to MusicPanelWidget
                event.acceptProposedAction()

            def _set_icon_only(self, icon_only):
                """Apply icon_only state to all buttons immediately."""
                p = self.parent_panel
                if icon_only:
                    p.btn_playlist.setText("")
                    p.btn_playlist.setToolTip("Playlist")
                    p.btn_playlist.setProperty("icon_only", True)
                    p.btn_media_lib.setText("")
                    p.btn_media_lib.setToolTip("Media Library")
                    p.btn_media_lib.setProperty("icon_only", True)
                else:
                    p.btn_playlist.setText(" Playlist")
                    p.btn_playlist.setToolTip("")
                    p.btn_playlist.setProperty("icon_only", False)
                    p.btn_media_lib.setText(" Media Library")
                    p.btn_media_lib.setToolTip("")
                    p.btn_media_lib.setProperty("icon_only", False)
                for btn in [p.btn_playlist, p.btn_media_lib]:
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

            def _animate_transition(self, to_icon_only):
                """Fade out buttons, switch content, fade back in."""
                from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
                from PySide6.QtWidgets import QGraphicsOpacityEffect
                self._transitioning = True
                p = self.parent_panel
                buttons = [p.btn_playlist, p.btn_media_lib]

                # Ensure each button has an opacity effect
                effects = []
                for btn in buttons:
                    effect = QGraphicsOpacityEffect(btn)
                    effect.setOpacity(1.0)
                    btn.setGraphicsEffect(effect)
                    effects.append(effect)

                # Phase 1: fade out
                fade_out_anims = []
                for effect in effects:
                    anim = QPropertyAnimation(effect, b"opacity")
                    anim.setDuration(120)
                    anim.setStartValue(1.0)
                    anim.setEndValue(0.0)
                    anim.setEasingCurve(QEasingCurve.OutCubic)
                    fade_out_anims.append(anim)

                finished_count = [0]

                def on_fade_out_done():
                    finished_count[0] += 1
                    if finished_count[0] < len(fade_out_anims):
                        return
                    # Switch content while invisible
                    self._set_icon_only(to_icon_only)
                    # Phase 2: fade in
                    fade_in_anims = []
                    for effect in effects:
                        anim = QPropertyAnimation(effect, b"opacity")
                        anim.setDuration(150)
                        anim.setStartValue(0.0)
                        anim.setEndValue(1.0)
                        anim.setEasingCurve(QEasingCurve.InCubic)
                        fade_in_anims.append(anim)
                    done_count = [0]
                    def on_fade_in_done():
                        done_count[0] += 1
                        if done_count[0] >= len(fade_in_anims):
                            # Remove effects so they don't interfere with other styling
                            for btn in buttons:
                                btn.setGraphicsEffect(None)
                            self._transitioning = False
                    from PySide6.QtCore import QAbstractAnimation
                    for anim in fade_in_anims:
                        anim.finished.connect(on_fade_in_done)
                        anim.start(QAbstractAnimation.DeleteWhenStopped)

                for anim in fade_out_anims:
                    anim.finished.connect(on_fade_out_done)
                    anim.start()

            def resizeEvent(self, event):
                super().resizeEvent(event)
                if not hasattr(self.parent_panel, 'btn_playlist'):
                    return
                is_small = self.width() < 120
                currently_icon_only = self.parent_panel.btn_playlist.text() == ""

                if is_small and not currently_icon_only and not self._transitioning:
                    self._animate_transition(to_icon_only=True)
                elif not is_small and currently_icon_only and not self._transitioning:
                    self._animate_transition(to_icon_only=False)


        self.sidebar_widget = SidebarWidget(self)
        
        # Style for the sidebar and buttons
        self.sidebar_widget.setStyleSheet("""
            QWidget#musicSidebar {
                background-color: transparent;
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }
            QPushButton {
                text-align: left;
                padding: 12px 16px;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                background-color: transparent;
                color: #b3b3b3;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPushButton[active="true"] {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border: none;
            }
            QPushButton[icon_only="true"] {
                text-align: center;
                padding: 12px 0px;
            }
        """)
        
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(10)
        
        # Playlist Button
        self.btn_playlist = QPushButton(" Playlist")
        self.btn_playlist.setCursor(Qt.PointingHandCursor)
        self.btn_playlist.setProperty("active", True)
        
        # Try to set icon
        script_dir = os.path.dirname(os.path.abspath(__file__))
        playlist_icon_path = os.path.join(script_dir, "UI Icons", "playlist-icon.svg")
        if os.path.exists(playlist_icon_path):
            self.btn_playlist.setIcon(QIcon(playlist_icon_path))
            self.btn_playlist.setIconSize(QSize(20, 20))
            
        # Media Library Button
        self.btn_media_lib = QPushButton(" Media Library")
        self.btn_media_lib.setCursor(Qt.PointingHandCursor)
        self.btn_media_lib.setProperty("active", False)
        
        media_icon_path = os.path.join(script_dir, "UI Icons", "library-icon.svg")
        if os.path.exists(media_icon_path):
            self.btn_media_lib.setIcon(QIcon(media_icon_path))
            self.btn_media_lib.setIconSize(QSize(20, 20))
            
        # Connect clicks
        self.btn_playlist.clicked.connect(lambda: self._on_sidebar_nav("playlist"))
        self.btn_media_lib.clicked.connect(lambda: self._on_sidebar_nav("media_lib"))
        
        sidebar_layout.addWidget(self.btn_playlist)
        sidebar_layout.addWidget(self.btn_media_lib)
        sidebar_layout.addStretch()
        parent_container.addWidget(self.sidebar_widget)

    def _on_sidebar_nav(self, target):
        if target == "playlist":
            self.btn_playlist.setProperty("active", True)
            self.btn_media_lib.setProperty("active", False)
            if hasattr(self, 'stack'):
                self.stack.setCurrentIndex(0)
        elif target == "media_lib":
            self.btn_playlist.setProperty("active", False)
            self.btn_media_lib.setProperty("active", True)
            if hasattr(self, 'stack'):
                self.stack.setCurrentIndex(1)
            
        self.btn_playlist.style().unpolish(self.btn_playlist)
        self.btn_playlist.style().polish(self.btn_playlist)
        self.btn_media_lib.style().unpolish(self.btn_media_lib)
        self.btn_media_lib.style().polish(self.btn_media_lib)
        
        # Reset styles to let main stylesheet take over again
        self.btn_playlist.setStyleSheet("")
        self.btn_media_lib.setStyleSheet("")

    def _update_splitter_gradient(self):
        if not hasattr(self, 'main_splitter'):
            return
            
        colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']
        self._splitter_gradient_offset += 0.04
        if self._splitter_gradient_offset >= 1.0:
            self._splitter_gradient_offset = 0.0
            
        offset = self._splitter_gradient_offset
        stops = []
        num_colors = len(colors)
        for i, color in enumerate(colors):
            base_pos = i / (num_colors - 1)
            shifted_pos = (base_pos + offset) % 1.0
            stops.append((shifted_pos, color))
            
        stops.sort(key=lambda x: x[0])
        gradient_stops = ', '.join([f"stop:{pos:.3f} {color}" for pos, color in stops])
        
        self.main_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: rgba(15, 15, 25, 0.95);
            }}
            QSplitter::handle:hover {{
                background-color: rgba(255, 91, 6, 0.3);
            }}
            QSplitter::handle:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, {gradient_stops});
            }}
        """)

    def _setup_ui(self):
        from PySide6.QtCore import QTimer
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === Menu Bar ===
        self._create_menu_bar(layout)
        
        # Resume Notification Banner (Floating, hidden by default)
        self.resume_banner = ResumeNotificationWidget(self)
        self.resume_banner.hide()
        
        # Connect signals
        self.resume_banner.dismiss_clicked.connect(self._dismiss_banner_by_user)
        self.resume_banner.auto_timeout.connect(self._dismiss_banner_by_timeout)
        self.resume_banner.resume_clicked.connect(self._resume_playback_from_banner)
        self.resume_banner.resume_and_folder_clicked.connect(self._resume_and_open_folder)
        
        # Floating URL Input
        self.floating_url_input = FloatingUrlInputWidget(self)
        self.floating_url_input.url_submitted.connect(self._process_url_stream_async)
        
        # Loading Overlay for Streams
        self.stream_loading = StreamLoadingOverlayWidget(self)
        
        # Main content stack
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(200)
        
        # === Page 0: Playlist View ===
        playlist_page = QWidget()
        playlist_page.setObjectName("playlistPage")
        playlist_layout = QVBoxLayout(playlist_page)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(0)
        
        self.header = PlaylistHeader()
        self.table = PlaylistTable()
        
        # Search bar
        self._create_search_bar(playlist_layout)
        
        playlist_layout.addWidget(self.header)
        playlist_layout.addWidget(self._search_container)
        playlist_layout.addWidget(self.table, stretch=1)
        
        self.stack.addWidget(playlist_page)
        
        # === Page 1: Media Library (Deferred for zero-latency page load) ===
        self.media_lib_placeholder = QWidget()
        self.stack.addWidget(self.media_lib_placeholder)
        
        def _init_media_lib():
            if hasattr(self, 'media_lib_placeholder') and self.media_lib_placeholder:
                self.media_lib_page = MediaLibraryPage()
                self.media_lib_page.folderSelected.connect(self._load_tracks_from_folder)
                self.media_lib_page.tracksAddedToPlaylist.connect(self._append_tracks_to_playlist)
                idx = self.stack.indexOf(self.media_lib_placeholder)
                if idx >= 0:
                    self.stack.removeWidget(self.media_lib_placeholder)
                    self.media_lib_placeholder.deleteLater()
                    self.media_lib_placeholder = None
                    self.stack.insertWidget(idx, self.media_lib_page)

        QTimer.singleShot(300, _init_media_lib)

        
        
        # Main view area (Playlist + YouTube Sidebar) with user-resizable splitter
        from PySide6.QtWidgets import QSplitter, QSplitterHandle
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
        from PySide6.QtGui import QColor, QPainter, QBrush

        class AnimatedSplitterHandle(QSplitterHandle):
            """Custom splitter handle with smooth color transitions on hover/press."""
            # Color definitions (r, g, b, a)
            COLOR_NORMAL  = (15,  15,  25,  242)   # rgba(15,15,25,0.95)
            COLOR_HOVER   = (255, 91,  6,   76)    # rgba(255,91,6,0.3)
            COLOR_PRESSED = (255, 91,  6,   255)   # solid orange (gradient overrides this)

            def __init__(self, orientation, parent):
                super().__init__(orientation, parent)
                self._r, self._g, self._b, self._a = self.COLOR_NORMAL
                self._target = self.COLOR_NORMAL
                self._is_pressed = False
                self._gradient_offset = 0.0
                self._gradient_colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']

                self._anim_timer = QTimer(self)
                self._anim_timer.setInterval(16)  # ~60fps
                self._anim_timer.timeout.connect(self._tick)
                self._anim_timer.start()
                self.setAttribute(Qt.WA_Hover, True)

            def _lerp(self, a, b, t):
                return a + (b - a) * t

            def _tick(self):
                speed = 0.15  # interpolation speed per frame
                tr, tg, tb, ta = self._target
                changed = False
                for attr, tval in [('_r', tr), ('_g', tg), ('_b', tb), ('_a', ta)]:
                    cur = getattr(self, attr)
                    nxt = cur + (tval - cur) * speed
                    if abs(nxt - tval) < 1.0:
                        nxt = tval
                    if abs(nxt - cur) > 0.1:
                        changed = True
                    setattr(self, attr, nxt)

                if self._is_pressed:
                    self._gradient_offset = (self._gradient_offset + 0.005) % 1.0
                    changed = True

                if changed:
                    self.update()

            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)

                if self._is_pressed:
                    # Draw animated gradient
                    from PySide6.QtGui import QLinearGradient, QGradient
                    h = self.height()
                    shift = self._gradient_offset * h
                    gradient = QLinearGradient(0, shift, 0, h + shift)
                    gradient.setSpread(QGradient.RepeatSpread)
                    
                    colors = self._gradient_colors
                    for i, color in enumerate(colors):
                        base = i / (len(colors) - 1)
                        gradient.setColorAt(base, QColor(color))
                        
                    painter.fillRect(self.rect(), gradient)
                else:
                    color = QColor(
                        int(self._r), int(self._g),
                        int(self._b), int(self._a)
                    )
                    painter.fillRect(self.rect(), color)

                painter.end()

            def enterEvent(self, event):
                if not self._is_pressed:
                    self._target = self.COLOR_HOVER
                super().enterEvent(event)

            def leaveEvent(self, event):
                if not self._is_pressed:
                    self._target = self.COLOR_NORMAL
                super().leaveEvent(event)

            def mousePressEvent(self, event):
                if event.button() == Qt.LeftButton:
                    self._is_pressed = True
                    self._target = self.COLOR_PRESSED
                super().mousePressEvent(event)

            def mouseReleaseEvent(self, event):
                if event.button() == Qt.LeftButton:
                    self._is_pressed = False
                    # Check if still hovering
                    if self.rect().contains(event.position().toPoint()):
                        self._target = self.COLOR_HOVER
                    else:
                        self._target = self.COLOR_NORMAL
                super().mouseReleaseEvent(event)

        class AnimatedSplitter(QSplitter):
            def createHandle(self):
                return AnimatedSplitterHandle(self.orientation(), self)

        self.main_splitter = AnimatedSplitter(Qt.Horizontal, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.setOpaqueResize(True)
        # Clear QSS on handle since we paint manually
        self.main_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        
        self._splitter_gradient_offset = 0.0

        # Add Sidebar to main_splitter directly
        self._create_music_sidebar(self.main_splitter)
        
        self.main_splitter.addWidget(self.stack)

        # YouTube Panel (Lazy loaded on demand)
        self.dl_panel = None

        # Keep main content dominant when splitter moves
        # Index 0: Sidebar, Index 1: Stack, Index 2: YT Panel
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)

        # Default sizes: sidebar 200, stack max, YT panel 0
        self._yt_last_width = 320
        self._update_yt_panel_constraints()
        self.main_splitter.setSizes([200, 1000, 0])

        layout.addWidget(self.main_splitter, stretch=1)
        
        # Player bar (wrapped so we can detach/overlay it during fullscreen video)
        self._player_bar_container = QFrame(self)
        try:
            self._player_bar_container.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        _pb_layout = QVBoxLayout(self._player_bar_container)
        _pb_layout.setContentsMargins(0, 0, 0, 0)
        _pb_layout.setSpacing(0)
        self.player_bar = PlayerBar(self._player_bar_container)
        _pb_layout.addWidget(self.player_bar)
        layout.addWidget(self._player_bar_container)
        
        # Main styling - gradient background
        self.setStyleSheet("""
            QWidget#MusicPanelWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f0f1a);
            }
            QWidget#playlistPage {
                background: transparent;
            }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Enforce max sidebar width (<= 50% of panel)
        self._update_yt_panel_constraints()
        
        if hasattr(self, 'resume_banner') and not self.resume_banner.isHidden():
            if hasattr(self.resume_banner, 'update_position'):
                self.resume_banner.update_position()
            else:
                self.resume_banner.move(max(20, (self.width() - self.resume_banner.width()) // 2), 20)
            
        if hasattr(self, 'floating_url_input') and self.floating_url_input.isVisible() and not getattr(self.floating_url_input, '_is_dragging', False):
            self.floating_url_input.move(max(10, (self.width() - self.floating_url_input.width()) // 2), max(10, (self.height() - self.floating_url_input.height()) // 2))
        if hasattr(self, 'stream_loading') and self.stream_loading.isVisible() and not getattr(self.stream_loading, '_is_dragging', False):
            self.stream_loading.move(max(10, (self.width() - self.stream_loading.width()) // 2), max(10, (self.height() - self.stream_loading.height()) // 2))
            
        try:
            if getattr(self, '_is_fullscreen', False) and getattr(self, '_playerbar_overlay_enabled', False):
                self._update_playerbar_overlay_geometry()
        except Exception:
            pass

    def _update_yt_panel_constraints(self):
        """Clamp Universal Downloader panel width to <= 70% of available width (max 450px)."""
        if not hasattr(self, 'dl_panel'):
            return
        total_w = max(1, self.width())
        # Minimum width is 350px, maximum is 70% of total (capped at 450px)
        min_w = 350
        max_w = min(450, max(min_w, int(total_w * 0.7)))
        if getattr(self, 'dl_panel', None) is None:
            return
        self.dl_panel.setMinimumWidth(min_w)
        self.dl_panel.setMaximumWidth(max_w)

        # If visible and currently wider than max, pull it back via splitter sizes.
        if hasattr(self, 'main_splitter') and self.dl_panel.isVisible():
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 3:
                if sizes[2] > max_w:
                    diff = sizes[2] - max_w
                    sizes[2] = max_w
                    sizes[1] += diff
                    self.main_splitter.setSizes(sizes)
                # Also ensure dl_panel is at least min_w when visible
                elif sizes[2] < min_w and sizes[2] > 0:
                    diff = min_w - sizes[2]
                    sizes[2] = min_w
                    sizes[1] = max(1, sizes[1] - diff)
                    self.main_splitter.setSizes(sizes)

    def _on_main_splitter_moved(self, pos, index):
        # Record the user's chosen width and keep it clamped.
        if hasattr(self, 'main_splitter'):
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 3:
                # Remember last width but keep it within current min/max.
                total_w = max(1, self.width())
                min_w = 350
                max_w = min(450, max(min_w, int(total_w * 0.7)))
                self._yt_last_width = max(min_w, min(max_w, sizes[2]))
        self._update_yt_panel_constraints()
    
    def _create_search_bar(self, parent_layout):
        """Create the search/filter bar."""
        from PySide6.QtWidgets import QLineEdit
        
        self._search_container = QFrame()
        self._search_container.setObjectName("searchContainer")
        self._search_container.setFixedHeight(45)
        
        search_layout = QHBoxLayout(self._search_container)
        search_layout.setContentsMargins(25, 8, 25, 8)
        search_layout.setSpacing(10)
        
        # Search icon label
        search_icon = QLabel("")
        search_icon.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        search_layout.addWidget(search_icon)
        
        # Search input
        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("Search tracks... (Ctrl+F)")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._filter_tracks)
        self._search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px 12px;
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #FF5B06;
                background: rgba(255, 255, 255, 0.12);
            }
            QLineEdit::placeholder {
                color: #666;
            }
        """)
        search_layout.addWidget(self._search_input, 1)
        
        # Track count
        self._track_count_label = QLabel("0 tracks")
        self._track_count_label.setStyleSheet("color: #888; font-size: 12px; background: transparent;")
        search_layout.addWidget(self._track_count_label)
        
        self._search_container.setStyleSheet("""
            QFrame#searchContainer {
                background: rgba(0, 0, 0, 0.3);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
    
    def _filter_tracks(self, query: str):
        """Filter playlist tracks based on search query."""
        query = query.lower().strip()
        
        if not query:
            # Show all tracks - clear filter mapping
            self._filtered_indices = None
            self.table.set_tracks(self._playlist)
            self._track_count_label.setText(f"{len(self._playlist)} tracks")
            return
        
        # Filter tracks and store original indices
        self._filtered_indices = []
        filtered = []
        for i, t in enumerate(self._playlist):
            if query in t.get('title', '').lower() or query in t.get('artist', '').lower():
                filtered.append(t)
                self._filtered_indices.append(i)  # Store original index
        
        self.table.set_tracks(filtered)
        self._track_count_label.setText(f"{len(filtered)} of {len(self._playlist)} tracks")

    def _delete_playlist_tracks(self, indices):
        """Remove tracks by their original indices in self._playlist."""
        # Sort in reverse order to safely delete by index
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._playlist):
                # If we are deleting the currently playing track, handle it
                if idx == self._current_index:
                    self._player.stop()
                    self._current_index = -1
                    self.player_bar.set_playing(False)
                    self.player_bar.set_track_info("", "")
                elif idx < self._current_index:
                    # Adjust current track index if a track before it was deleted
                    self._current_index -= 1
                    
                del self._playlist[idx]
                
        if len(self._playlist) == 0:
            self._music_folder = ''
            self._last_known_position = 0
            self._pending_seek_position = 0
            if hasattr(self, 'resume_banner') and self.resume_banner.isVisible():
                self.resume_banner.hide()
            
        self._save_state()
        if hasattr(self, 'table'):
            self.table.set_tracks(self._playlist)
        self.refresh_playlist_stats()

    def _clear_playlist(self):
        """Clear all tracks from the playlist."""
        self._playlist = []
        self._music_folder = ''
        self._last_known_position = 0
        self._pending_seek_position = 0
        self._player.stop()
        self._current_index = -1
        self.player_bar.set_playing(False)
        self.player_bar.set_track_info("", "")
        if hasattr(self, 'resume_banner') and self.resume_banner.isVisible():
            self.resume_banner.hide()
        self._save_state()
        if hasattr(self, 'table'):
            self.table.set_tracks(self._playlist)
        self.refresh_playlist_stats()

    def _append_tracks_to_playlist(self, new_tracks, group_name=None):
        """Append tracks directly from Media Library to Playlist."""
        if group_name:
            for track in new_tracks:
                track['playlist_group'] = group_name
        self._playlist.extend(new_tracks)
        if hasattr(self, 'table'):
            self.table.set_tracks(self._playlist)
        self._save_state()
        self.refresh_playlist_stats()
        if hasattr(self, '_track_count_label'):
            self._track_count_label.setText(f"{len(self._playlist)} tracks")

    def _flatten_playlist_group(self, group_name: str):
        for track in self._playlist:
            if track.get('playlist_group') == group_name:
                track['playlist_group'] = None
        self._save_state()
        if hasattr(self, 'table'):
            self.table.set_tracks(self._playlist)
        self.refresh_playlist_stats()
    
    def _connect_signals(self):
        # Player bar
        self.player_bar.playClicked.connect(self._toggle_play)
        self.player_bar.prevClicked.connect(self._prev_track)
        self.player_bar.nextClicked.connect(self._next_track)
        self.player_bar.loopClicked.connect(self._save_state)
        
        # Background shortcut removed due to conflict
        from PySide6.QtGui import QKeySequence, QShortcut
        # Shortcut for Ctrl+A (Select All Tracks)
        self.sc_select_all = QShortcut(QKeySequence("Ctrl+A"), self)
        self.sc_select_all.setContext(Qt.WidgetWithChildrenShortcut)
        self.sc_select_all.activated.connect(self._on_select_all_tracks)
        
        self.player_bar.seekChanged.connect(self._seek)
        self.player_bar.volumeChanged.connect(self._set_volume)
                
        # Setup shuffle logic on click
        def on_shuffle_clicked():
            is_shuffled = getattr(self.player_bar, '_is_shuffled', False)
            if is_shuffled:
                # User turned it ON -> Generate fresh random deck
                self._generate_shuffled_sequence()
            else:
                # User turned it OFF -> Discard/Clear old deck sequence as requested
                self._shuffled_sequence = []
                self._shuffled_pointer = -1
            self._save_state()
            
        self.player_bar.shuffleClicked.connect(on_shuffle_clicked)
        
        # Table
        self.table.trackDoubleClicked.connect(self._play_track)
        self.table.deleteSelected.connect(self._delete_playlist_tracks)
        self.table.deleteAll.connect(self._clear_playlist)
        self.table.flattenGroup.connect(self._flatten_playlist_group)
        self.table.addFileRequested.connect(self._open_file_direct)
        self.table.addMultipleFilesRequested.connect(self._open_multiple_files_direct)
        self.table.addFolderRequested.connect(self._browse_folder_direct)
        
    def _ensure_player(self):
        """Ensure main QMediaPlayer is initialized lazily."""
        if getattr(self, '_player', None) is None:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(getattr(self, '_user_volume', 1.0))
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration_changed)
            self._player.playbackStateChanged.connect(self._on_state)
            self._player.errorOccurred.connect(self._on_player_error)
            self._player.mediaStatusChanged.connect(self._on_media_status)
    
    def _on_select_all_tracks(self):
        from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            fw.selectAll()
        else:
            if hasattr(self, 'stack'):
                idx = self.stack.currentIndex()
                if idx == 0 and hasattr(self, 'table'):
                    self.table.select_all()
                elif idx == 1 and hasattr(self, 'media_lib_page'):
                    self.media_lib_page.select_all()
            elif hasattr(self, 'table'):
                self.table.select_all()
                
    def _on_player_error(self, error, error_string):
        """Handle media player errors with automatic recovery for online streams."""
        import time
        from PySide6.QtMultimedia import QMediaPlayer
        print(f"Player error: {error} - {error_string}")
        
        # Auto-recover online streams from CDN dropouts / Demuxing failed
        if 0 <= getattr(self, '_current_index', -1) < len(getattr(self, '_playlist', [])):
            track = self._playlist[self._current_index]
            if isinstance(track, dict) and track.get('is_online', False):
                now = time.time()
                last_retry = getattr(self, '_last_stream_error_retry', 0)
                retry_count = getattr(self, '_stream_error_retry_count', 0)
                
                if now - last_retry > 12:
                    retry_count = 0
                    
                if retry_count < 3:
                    self._last_stream_error_retry = now
                    self._stream_error_retry_count = retry_count + 1
                    
                    saved_pos = max(0, getattr(self, '_last_known_pos', 0) or (self._player.position() if hasattr(self, '_player') else 0))
                    print(f"[Stream Auto-Recovery] Attempt {self._stream_error_retry_count}/3: Reconnecting stream at {saved_pos}ms...")
                    
                    # Invalidate expired stream URL to force fresh token extraction
                    track.pop('stream_url', None)
                    
                    def _recover():
                        self._load_and_play_stream(track, start_pos=saved_pos)
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(600, _recover)
    
    def _on_media_status(self, status):
        """Handle media status changes (for end-of-track and loop handling)."""
        if status == QMediaPlayer.EndOfMedia:
            # If crossfade handled the transition, don't do auto-next
            if self._crossfade_active:
                return
            
            # Get loop mode from player_bar
            loop_mode = self.player_bar._loop_mode
            print(f"[Music] EndOfMedia - loop_mode: {loop_mode}")
            
            if loop_mode == "one":
                # Loop-one: reload and replay current track
                print("[Music] Loop-one: replaying current track")
                self._play_track(self._current_index)
            elif loop_mode == "all":
                # Loop-all: go to next track (will loop to beginning when at end)
                self._next_track()
            else:
                # No loop: go to next track, stop at end of playlist
                if self._current_index < len(self._playlist) - 1:
                    self._next_track()
                else:
                    if hasattr(self, 'action_close_on_done') and self.action_close_on_done.isChecked():
                        self.window().close()
    
    def _init_discord(self):
        """Initialize Discord Rich Presence."""
        try:
            from integrations.discord_presence import DiscordPresence
            self._discord = DiscordPresence()
            if self._discord.is_available:
                self._discord.connect()
                print("[Discord] Rich Presence initialized")
            else:
                print("[Discord] pypresence not available")
        except Exception as e:
            print(f"[Discord] Init error: {e}")
            self._discord = None
    
    def _update_discord(self, title: str, artist: str, is_playing: bool = True):
        """Update Discord Rich Presence with current track."""
        if self._discord and self._discord.is_connected:
            if is_playing:
                self._discord.set_playing(title, artist)
            else:
                self._discord.set_paused(title, artist)
    
    def _create_menu_bar(self, layout):
        """Create the menu bar with Audio, Video, and Tools menus."""
        from PySide6.QtWidgets import QMenuBar, QMenu
        from PySide6.QtGui import QAction, QActionGroup, QKeySequence
        
        menu_bar = QMenuBar()
        menu_bar.setObjectName("musicMenuBar")
        
        # === Media Menu ===
        media_menu = menu_bar.addMenu("Media")
        media_menu.setObjectName("mediaMenu")
        
        # Refresh Current Track / List (Top Item)
        self.action_refresh_track = QAction("Refresh current track\tCtrl+R or F5", self)
        self.action_refresh_track.setShortcuts([QKeySequence("Ctrl+R"), QKeySequence("F5")])
        self.action_refresh_track.setShortcutContext(Qt.WindowShortcut)
        self.action_refresh_track.triggered.connect(self.reload_current_view)
        media_menu.addAction(self.action_refresh_track)
        self.addAction(self.action_refresh_track)
        
        media_menu.addSeparator()

        # Add File
        self.action_open_file = QAction("Add File", self)
        self.action_open_file.setShortcut("Ctrl+O")
        self.action_open_file.setShortcutContext(Qt.WindowShortcut)
        self.action_open_file.triggered.connect(self._open_file_direct)
        media_menu.addAction(self.action_open_file)
        self.addAction(self.action_open_file)
        
        # Add Multiple Files
        self.action_open_multiple_files = QAction("Add Multiple Files", self)
        self.action_open_multiple_files.setShortcut("Ctrl+K, Ctrl+O")
        self.action_open_multiple_files.setShortcutContext(Qt.WindowShortcut)
        self.action_open_multiple_files.triggered.connect(self._open_multiple_files_direct)
        media_menu.addAction(self.action_open_multiple_files)
        self.addAction(self.action_open_multiple_files)
        
        # Add Folder
        self.action_open_folder = QAction("Add Folder", self)
        self.action_open_folder.setShortcut("Ctrl+Shift+O")
        self.action_open_folder.setShortcutContext(Qt.WindowShortcut)
        self.action_open_folder.triggered.connect(self._browse_folder_direct)
        media_menu.addAction(self.action_open_folder)
        self.addAction(self.action_open_folder)

        
        # Add Location From Clipboard
        self.action_open_clipboard = QAction("Add Location From Clipboard", self)
        self.action_open_clipboard.setShortcut("Ctrl+Shift+V")
        self.action_open_clipboard.setShortcutContext(Qt.WindowShortcut)
        self.action_open_clipboard.triggered.connect(self._open_clipboard_direct)
        media_menu.addAction(self.action_open_clipboard)
        self.addAction(self.action_open_clipboard)
        
        media_menu.addSeparator()
        
        # Open Recent Media (Submenu)
        self.recent_media_menu = media_menu.addMenu("Open Recent Media")
        self.recent_media_menu.setObjectName("recentMediaMenu")
        self.recent_media_menu.addAction("No Recent Media").setEnabled(False)
        
        # === Audio Menu ===
        audio_menu = menu_bar.addMenu("Audio")
        audio_menu.setObjectName("audioMenu")
        self._audio_menu = audio_menu  # Store reference for dynamic updates
        
        # Preferred Output submenu
        self._device_menu = audio_menu.addMenu("Preferred Output")
        self._device_menu.setObjectName("deviceMenu")
        self._device_menu.aboutToShow.connect(self._populate_audio_devices)
        
        audio_menu.addSeparator()
        
        # Playback Speed submenu
        speed_menu = audio_menu.addMenu("Playback Speed")
        speed_menu.setObjectName("speedMenu")
        self._speed_actions = {}
        
        for rate in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            action = QAction(f"{rate}x" + (" (Normal)" if rate == 1.0 else ""), self)
            action.setCheckable(True)
            action.setChecked(rate == 1.0)
            action.triggered.connect(lambda checked, r=rate: self._set_playback_speed(r))
            speed_menu.addAction(action)
            self._speed_actions[rate] = action
        
        audio_menu.addSeparator()
        
        # Crossfade submenu with slider
        crossfade_menu = audio_menu.addMenu("Crossfade")
        crossfade_menu.setObjectName("crossfadeMenu")
        
        # Create slider widget for menu
        from PySide6.QtWidgets import QWidgetAction, QWidget, QHBoxLayout, QSlider, QLabel
        
        slider_widget = QWidget()
        slider_widget.setStyleSheet("""
            QWidget { background: transparent; padding: 5px 10px; }
            QLabel { color: #e0e0e0; font-size: 12px; min-width: 60px; }
            QSlider::groove:horizontal { height: 4px; background: rgba(60, 64, 72, 0.8); border-radius: 2px; }
            QSlider::handle:horizontal { background: #e0e0e0; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; border: none; }
            QSlider::handle:horizontal:hover { background: #ffffff; }
            QSlider::sub-page:horizontal { background: rgba(255, 91, 6, 0.6); border-radius: 2px; }
        """)
        
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(10, 5, 10, 5)
        slider_layout.setSpacing(10)
        
        self._crossfade_slider = QSlider(Qt.Horizontal)
        self._crossfade_slider.setRange(0, 10)
        self._crossfade_slider.setValue(3)  # Default 3 seconds
        self._crossfade_slider.setSingleStep(1)  # Scroll moves 1 sec per tick
        self._crossfade_slider.setFixedWidth(120)
        
        self._crossfade_label = QLabel("3 sec")
        self._crossfade_label.setFixedWidth(70)
        
        def on_crossfade_slider_change(val):
            if val == 0:
                self._crossfade_label.setText("Off")
                self._crossfade_enabled = False
            else:
                self._crossfade_label.setText(f"{val} sec")
                self._crossfade_enabled = True
                self._crossfade_duration = float(val)
            self._save_state()
        
        self._crossfade_slider.valueChanged.connect(on_crossfade_slider_change)
        
        slider_layout.addWidget(self._crossfade_slider)
        slider_layout.addWidget(self._crossfade_label)
        
        slider_action = QWidgetAction(self)
        slider_action.setDefaultWidget(slider_widget)
        crossfade_menu.addAction(slider_action)
        

        # === Tools Menu ===
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.setObjectName("toolsMenu")
        
        # Play from URL (Stream)
        self.action_play_url = QAction("URL Stream (Beta)", self)
        self.action_play_url.setShortcut("Ctrl+Y")
        self.action_play_url.setShortcutContext(Qt.ApplicationShortcut)
        self.action_play_url.triggered.connect(self._prompt_play_url)
        tools_menu.addAction(self.action_play_url)
        self.addAction(self.action_play_url)
        
        tools_menu.addSeparator()
        
        # Universal Downloader
        self.action_download_universal = QAction("Universal Downloader (Beta)", self)
        self.action_download_universal.setShortcut("Ctrl+U")
        self.action_download_universal.triggered.connect(self._toggle_yt_panel)
        tools_menu.addAction(self.action_download_universal)
        
        tools_menu.addSeparator()
        
        # Rescan Folder
        self.action_rescan = QAction("Rescan Folder", self)
        self.action_rescan.setShortcut("F5")
        self.action_rescan.triggered.connect(self._rescan_folder)
        tools_menu.addAction(self.action_rescan)
        
        tools_menu.addSeparator()
        
        # Convert to MP3
        self.action_convert_mp3 = QAction("Convert to MP3...", self)
        self.action_convert_mp3.triggered.connect(self._show_convert_dialog)
        tools_menu.addAction(self.action_convert_mp3)
        
        tools_menu.addSeparator()
        
        # Taskbar Media Widget Submenu (with Position dropdown on hover)
        self.taskbar_media_menu = tools_menu.addMenu("Taskbar Media Widget")
        self.taskbar_media_menu.setObjectName("taskbarMediaMenu")
        
        # Enable / Disable Action
        self.action_taskbar_enable = QAction("Enable Widget", self)
        self.action_taskbar_enable.setCheckable(True)
        self.action_taskbar_enable.setChecked(getattr(self, '_taskbar_widget_enabled', True))
        self.action_taskbar_enable.toggled.connect(self.toggle_taskbar_media_widget)
        self.taskbar_media_menu.addAction(self.action_taskbar_enable)
        
        self.taskbar_media_menu.addSeparator()
        
        # Position Selection Group
        self._taskbar_pos_group = QActionGroup(self)
        self._taskbar_pos_group.setExclusive(True)
        
        pos_options = [
            ("right", "Dock: Right (Near System Tray)"),
            ("center", "Dock: Center (Taskbar Center)"),
            ("left", "Dock: Left (Near Start Button)"),
            ("top_right", "Float: Top-Right Screen"),
            ("top_center", "Float: Top-Center Screen")
        ]
        
        self._taskbar_pos_actions = {}
        current_pos = getattr(self, '_taskbar_widget_position', 'left')
        
        for mode_key, mode_label in pos_options:
            pos_act = QAction(mode_label, self)
            pos_act.setCheckable(True)
            pos_act.setChecked(mode_key == current_pos)
            pos_act.triggered.connect(lambda checked, m=mode_key: self.set_taskbar_media_position(m))
            self._taskbar_pos_group.addAction(pos_act)
            self.taskbar_media_menu.addAction(pos_act)
            self._taskbar_pos_actions[mode_key] = pos_act
        
        # Apply menu bar styling
        menu_bar.setStyleSheet("""
            QMenuBar {
                background: rgba(15, 15, 25, 0.95);
                color: #e0e0e0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 4px 10px;
                font-size: 12px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: rgba(255, 255, 255, 0.12);
            }
            QMenuBar::item:pressed {
                background: rgba(255, 255, 255, 0.12);
            }
            QMenu {
                background: rgba(25, 25, 35, 0.98);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)
        
        self._menu_bar_widget = menu_bar  # Store reference for fullscreen toggle
        layout.addWidget(menu_bar)

    def _set_current_media_local_path(self, path: Optional[str]):
        self._current_media_path = path
        self._current_media_url = None

    def _set_current_media_url(self, url: Optional[str]):
        self._current_media_path = None
        self._current_media_url = url

    def _get_ffmpeg_bin_dir(self):
        try:
            appdata = os.environ.get('APPDATA', '')
            p = os.path.join(appdata, 'HELXAID', 'tools', 'ffmpeg', 'bin')
            if os.path.isdir(p):
                return p
        except Exception:
            pass
        return None

    def _get_ffprobe_path(self):
        bin_dir = self._get_ffmpeg_bin_dir()
        if bin_dir:
            exe = os.path.join(bin_dir, 'ffprobe.exe')
            if os.path.exists(exe):
                return exe
        return 'ffprobe'

    def _get_ffmpeg_path(self):
        bin_dir = self._get_ffmpeg_bin_dir()
        if bin_dir:
            exe = os.path.join(bin_dir, 'ffmpeg.exe')
            if os.path.exists(exe):
                return exe
        return 'ffmpeg'





    
    def _populate_audio_devices(self):
        """Populate the audio device submenu with available devices."""
        self._ensure_player()
        from PySide6.QtMultimedia import QMediaDevices
        from PySide6.QtGui import QAction
        
        self._device_menu.clear()
        
        # Newly Connected Device (Auto)
        is_auto = getattr(self, '_auto_audio_device', True)
        auto_action = QAction("Newly Connected Device", self)
        auto_action.setCheckable(True)
        auto_action.setChecked(is_auto)
        auto_action.triggered.connect(self._set_default_audio_device)
        self._device_menu.addAction(auto_action)
        
        self._device_menu.addSeparator()
        
        devices = QMediaDevices.audioOutputs()
        current_device = self._audio_output.device()
        
        if not devices:
            action = QAction("No devices found", self)
            action.setEnabled(False)
            self._device_menu.addAction(action)
            return
        
        for device in devices:
            action = QAction(device.description(), self)
            action.setCheckable(True)
            action.setChecked(not is_auto and device.id() == current_device.id())
            action.triggered.connect(lambda checked, d=device: self._set_audio_device(d))
            self._device_menu.addAction(action)

    def _set_default_audio_device(self):
        """Set to automatically use default (newly connected) device."""
        from PySide6.QtMultimedia import QMediaDevices
        self._auto_audio_device = True
        default_dev = QMediaDevices.defaultAudioOutput()
        self._audio_output.setDevice(default_dev)
        if hasattr(self, '_audio_output2'):
            self._audio_output2.setDevice(default_dev)
        self._save_state()
        print("Audio device set to: Newly Connected Device (Auto)")
    
    def _set_audio_device(self, device):
        """Set the audio output device."""
        from PySide6.QtMultimedia import QAudioDevice
        
        self._auto_audio_device = False
        self._audio_output.setDevice(device)
        if hasattr(self, '_audio_output2'):
            self._audio_output2.setDevice(device)
        
        # Save to config
        self._save_state()
        print(f"Audio device set to: {device.description()}")
    
    def _set_playback_speed(self, rate: float):
        """Set playback speed."""
        self._player.setPlaybackRate(rate)
        
        # Update checkmarks
        for r, action in self._speed_actions.items():
            action.setChecked(r == rate)
            
        self._save_state()
        
        print(f"Playback speed: {rate}x")
    
    def _start_crossfade(self):
        """Start crossfade to next track."""
        from PySide6.QtCore import QTimer, QUrl
        
        if self._crossfade_active:
            return
        
        # Don't crossfade if loop-one mode - let track repeat
        if hasattr(self, 'player_bar') and self.player_bar._loop_mode == "one":
            return
        
        # Get next track index
        import random
        if hasattr(self, 'player_bar') and self.player_bar._is_shuffled:
            # Shuffle mode: pick random track
            if len(self._playlist) > 1:
                available = [i for i in range(len(self._playlist)) if i != self._current_index]
                next_idx = random.choice(available)
            else:
                next_idx = 0
        elif hasattr(self, 'table') and hasattr(self.table, 'get_next_index'):
            next_idx = self.table.get_next_index(self._current_index)
        else:
            next_idx = (self._current_index + 1) % len(self._playlist) if self._playlist else -1
        
        if next_idx < 0 or next_idx >= len(self._playlist):
            self._crossfade_disabled_for_current = True
            return
        
        # Get next track path
        next_track = self._playlist[next_idx]
        next_path = next_track.get('path', '')
        is_online = next_track.get('is_online', False)
        
        if not next_path or is_online:
            self._crossfade_disabled_for_current = True
            return
            
        self._crossfade_active = True
        self._crossfade_next_idx = next_idx
        self._crossfade_start_time = self._player.position()
        
        print(f"[Music] Starting crossfade to: {next_track.get('title', 'Unknown')}")
        
        # Ensure secondary player is initialized lazily
        if self._player2 is None:
            self._player2 = QMediaPlayer()
            self._audio_output2 = QAudioOutput()
            self._player2.setAudioOutput(self._audio_output2)
            self._audio_output2.setVolume(0.0)
            
        # Load next track into secondary player
        self._player2.setSource(QUrl.fromLocalFile(next_path))
        self._audio_output2.setVolume(0.0)
        self._player2.play()
        
        # Start volume fade timer (update every 50ms)
        self._crossfade_steps = int(self._crossfade_duration * 1000 / 50)
        self._crossfade_step = 0
        
        self._crossfade_timer = QTimer(self)
        self._crossfade_timer.timeout.connect(self._crossfade_tick)
        self._crossfade_timer.start(50)
    
    def _crossfade_tick(self):
        """Update volumes during crossfade."""
        self._crossfade_step += 1
        progress = min(1.0, self._crossfade_step / self._crossfade_steps)
        
        # Fade out current, fade in next
        fade_out_volume = self._user_volume * (1.0 - progress)
        fade_in_volume = self._user_volume * progress
        
        self._audio_output.setVolume(fade_out_volume)
        self._audio_output2.setVolume(fade_in_volume)
        
        if progress >= 1.0:
            self._finish_crossfade()
    
    def _finish_crossfade(self):
        """Complete crossfade transition."""
        if self._crossfade_timer:
            self._crossfade_timer.stop()
            self._crossfade_timer = None
        
        # Set flag BEFORE stop() to prevent StoppedState from changing icon
        self._switching_track = True
        
        # Stop old player
        self._player.stop()
        
        # Swap references - player2 becomes player
        self._player, self._player2 = self._player2, self._player
        self._audio_output, self._audio_output2 = self._audio_output2, self._audio_output
        
        # Reconnect signals to new main player
        try:
            self._player2.positionChanged.disconnect()
            self._player2.playbackStateChanged.disconnect()
            self._player2.errorOccurred.disconnect()
            self._player2.mediaStatusChanged.disconnect()
        except RuntimeError:
            pass
        
        self._player.positionChanged.connect(self._on_position)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        
        # Update current index
        self._current_index = self._crossfade_next_idx
        self.table.highlight_playing(self._current_index)
        
        # Update UI
        track = self._playlist[self._current_index]
        title = track.get('title', 'Unknown')
        artist = track.get('artist', '')
        self.player_bar.set_track_info(title, artist)
        
        # Force icon to show pause (playing state) since track is playing
        self.player_bar.set_playing(True)
        from PySide6.QtMultimedia import QMediaPlayer
        self.playbackStateChanged.emit(QMediaPlayer.PlayingState)
        
        # Explicitly sync taskbar media widget and visualizer
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            self._taskbar_media_widget.set_playback_state(True)
            self._taskbar_media_widget.set_track_info(title, artist if artist != "-" else "")
        
        # Reset state
        self._audio_output.setVolume(self._user_volume)
        self._audio_output2.setVolume(0.0)
        self._crossfade_active = False
        
        # Clear switching flag after short delay
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
        
        print(f"[Music] Crossfade complete: {title}")
    
    def _show_balance_dialog(self):
        """Show stereo mode selection dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QLabel, QPushButton, QButtonGroup
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Stereo Mode")
        dialog.setFixedSize(320, 280)
        dialog.setStyleSheet("""
            QDialog {
                background: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #FF5B06;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
                background: transparent;
            }
            QRadioButton {
                color: #e0e0e0;
                font-size: 12px;
                padding: 8px 12px;
                background: transparent;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:checked {
                background: #FF5B06;
                border: 2px solid #FF5B06;
                border-radius: 8px;
            }
            QRadioButton::indicator:unchecked {
                background: #2a2a2a;
                border: 2px solid #555;
                border-radius: 8px;
            }
            QRadioButton:hover {
                background: rgba(255, 91, 6, 0.15);
                border-radius: 5px;
            }
            QPushButton {
                background: #FF5B06;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #FF7B26;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Select Stereo Mode")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF5B06;")
        layout.addWidget(title)
        
        # Radio buttons
        self._stereo_group = QButtonGroup(dialog)
        
        modes = [
            ("stereo", "Stereo", "Normal stereo (Left + Right)"),
            ("mono", "Mono", "Combine both channels"),
            ("left", "Left Only", "Play left channel on both speakers"),
            ("right", "Right Only", "Play right channel on both speakers"),
            ("reverse", "Reverse Stereo", "Swap left and right channels"),
        ]
        
        current_mode = getattr(self, '_stereo_mode', 'stereo')
        
        for i, (mode_id, label, description) in enumerate(modes):
            radio = QRadioButton(f"{label}\n   {description}")
            radio.setProperty("mode_id", mode_id)
            radio.setChecked(mode_id == current_mode)
            self._stereo_group.addButton(radio, i)
            layout.addWidget(radio)
        
        layout.addStretch()
        
        # Apply button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(lambda: self._apply_stereo_mode(dialog))
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _apply_stereo_mode(self, dialog):
        """Apply selected stereo mode."""
        selected = self._stereo_group.checkedButton()
        if selected:
            mode = selected.property("mode_id")
            self._stereo_mode = mode
            print(f"Stereo mode set to: {mode}")
            
            # Note: Actual audio channel manipulation requires audio processing
            # which is beyond QMediaPlayer's capabilities. This stores the preference.
            # For real implementation, consider using audio filters or a different backend.
            
        dialog.accept()
    
    def _show_audio_settings(self):
        """Show audio output settings dialog."""
        self._open_settings()
    
    def _ensure_dl_panel(self):
        """Lazy load UniversalDownloaderPanel when requested."""
        if getattr(self, 'dl_panel', None) is None:
            self.dl_panel = UniversalDownloaderPanel(self)
            self.dl_panel.hide()
            self.dl_panel.closeRequested.connect(self._toggle_yt_panel)
            self.dl_panel.downloadFinished.connect(self._on_yt_download_finished)
            if hasattr(self, 'main_splitter'):
                self.main_splitter.addWidget(self.dl_panel)
                self.main_splitter.setStretchFactor(2, 0)
                self._update_yt_panel_constraints()

    def _toggle_yt_panel(self):
        """Toggle the integrated YouTube downloader sidebar."""
        self._ensure_dl_panel()
        if self.dl_panel and self.dl_panel.isVisible():
            self.dl_panel.hide()
            if hasattr(self, 'main_splitter'):
                # Collapse YT panel, preserve sidebar
                current_sizes = self.main_splitter.sizes()
                sidebar_size = current_sizes[0] if len(current_sizes) > 0 else 200
                total = sum(current_sizes)
                self.main_splitter.setSizes([sidebar_size, max(1, total - sidebar_size), 0])
        else:
            self.dl_panel.show()
            self._update_yt_panel_constraints()
            if hasattr(self, 'main_splitter'):
                current_sizes = self.main_splitter.sizes()
                sidebar_size = current_sizes[0] if len(current_sizes) > 0 else 200
                max_w = self.dl_panel.maximumWidth()
                desired = min(max_w, max(self.dl_panel.minimumWidth(), int(getattr(self, '_yt_last_width', 350) or 350)))
                total = max(1, self.width())
                self.main_splitter.setSizes([sidebar_size, max(1, total - sidebar_size - desired), desired])
            self.dl_panel.url_edit.setFocus()
            # If paste buffer has a YT link, auto-fill it
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()
            if text.startswith('http://') or text.startswith('https://'):
                self.dl_panel.set_url(text)

    def _on_yt_download_finished(self, dest_path):
        """Handle track after integrated download completion."""
        print(f"[DEBUG MusicPanelWidget] _on_yt_download_finished called with path: {dest_path}")
        if hasattr(self, 'dl_panel') and self.dl_panel and hasattr(self.dl_panel, 'auto_add_cb'):
            is_checked = self.dl_panel.auto_add_cb.isChecked()
            print(f"[DEBUG MusicPanelWidget] Auto-add toggle status: {is_checked}")
            if not is_checked:
                print(f"[Universal DL] Download completed (Auto-add disabled): {os.path.basename(str(dest_path or ''))}")
                return

        target = "Track Playlist"
        if hasattr(self, 'dl_panel') and hasattr(self.dl_panel, 'auto_add_target_combo'):
            target = self.dl_panel.auto_add_target_combo.currentText()
        print(f"[DEBUG MusicPanelWidget] Auto-add target selected: '{target}' for file: '{dest_path}'")

        if dest_path and os.path.isfile(dest_path):
            if "Media Library" in target:
                if hasattr(self, 'media_lib_page') and self.media_lib_page:
                    try:
                        if hasattr(self.media_lib_page, 'add_path_to_library'):
                            self.media_lib_page.add_path_to_library(dest_path, is_folder=False)
                        else:
                            self.media_lib_page._add_path_to_library(dest_path, is_folder=False)
                            if hasattr(self.media_lib_page, '_save_library'):
                                self.media_lib_page._save_library()
                            if hasattr(self.media_lib_page, '_refresh_tree'):
                                self.media_lib_page._refresh_tree()
                        print(f"[DEBUG MusicPanelWidget] Successfully added track to Media Library: {dest_path}")
                    except Exception as ex:
                        print(f"[DEBUG MusicPanelWidget] Error adding track to Media Library: {ex}")
                else:
                    print("[DEBUG MusicPanelWidget] media_lib_page not found on widget!")
            else:
                # Default to Track Playlist
                from PlaylistWidget import PlaylistWidget as _PW
                track = _PW.build_track_meta(dest_path) if hasattr(_PW, 'build_track_meta') else {
                    'path': dest_path,
                    'title': os.path.splitext(os.path.basename(dest_path))[0],
                    'artist': 'Downloaded',
                    'duration': 0,
                    'is_online': False,
                    'mtime': os.path.getmtime(dest_path),
                }
                if not hasattr(self, '_playlist') or self._playlist is None:
                    self._playlist = []
                
                existing_paths = [t.get('path') for t in self._playlist if isinstance(t, dict)]
                if dest_path not in existing_paths:
                    self._playlist.append(track)
                    if hasattr(self, 'table') and hasattr(self.table, 'set_tracks'):
                        self.table.set_tracks(self._playlist)
                    print(f"[DEBUG MusicPanelWidget] Successfully added track to Track Playlist: {track.get('title')} ({dest_path})")
                else:
                    print(f"[DEBUG MusicPanelWidget] Track already present in Track Playlist: {dest_path}")
        else:
            print(f"[DEBUG MusicPanelWidget] Could not add to target because file was not found: '{dest_path}'")

    def _rescan_folder(self):
        """Rescan current music folder."""
        if self._music_folder and os.path.exists(self._music_folder):
            self._load_tracks_from_folder(self._music_folder)
            print(f"Rescanned: {self._music_folder}")
    
    def _show_convert_dialog(self):
        """Show dialog to convert selected/all tracks to MP3 with HELXAID styling."""
        try:
            from ConvertMp3Dialog import ConvertMp3Dialog
            dialog = ConvertMp3Dialog(
                parent=self,
                playlist=getattr(self, '_playlist', []),
                current_index=getattr(self, '_current_index', -1),
                default_output_dir=getattr(self, '_music_folder', None)
            )
            if dialog.exec():
                # If output was inside current music folder, rescan
                if getattr(self, '_music_folder', None) and os.path.exists(self._music_folder):
                    out_dir = getattr(dialog, '_output_dir', '')
                    if out_dir and os.path.exists(out_dir) and os.path.abspath(out_dir) == os.path.abspath(self._music_folder):
                        self._rescan_folder()
        except Exception as e:
            print(f"[MusicPanel] Failed to show ConvertMp3Dialog: {e}")

        
    def _generate_shuffled_sequence(self):
        """Generate a random Fisher-Yates shuffled sequence of track indices."""
        if not hasattr(self, '_playlist') or not self._playlist:
            self._shuffled_sequence = []
            self._shuffled_pointer = -1
            return
            
        import random
        indices = list(range(len(self._playlist)))
        random.shuffle(indices)
        self._shuffled_sequence = indices
        
        # If a track is already playing, move pointer to its position in the deck
        if self._current_index >= 0:
            try:
                self._shuffled_pointer = self._shuffled_sequence.index(self._current_index)
            except ValueError:
                self._shuffled_pointer = 0
        else:
            self._shuffled_pointer = 0
            
    def _sync_shuffled_pointer_to_current(self):
        """Sync the shuffled pointer to the currently playing track index."""
        if self._shuffled_sequence and self._current_index >= 0:
            try:
                self._shuffled_pointer = self._shuffled_sequence.index(self._current_index)
            except ValueError:
                # Track might not be in sequence (e.g. newly added or playlist changed)
                self._generate_shuffled_sequence()
    
    def _format_playlist_duration(self) -> str:
        """Calculate and format total playlist duration as HH:MM:SS or MM:SS."""
        if not hasattr(self, '_playlist') or not self._playlist:
            return "0:00"
        
        total = 0.0
        for t in self._playlist:
            dur = t.get('duration', 0)
            try:
                if dur is None:
                    continue
                if isinstance(dur, str):
                    if ':' in dur:
                        parts = dur.split(':')
                        if len(parts) == 2:
                            total += float(parts[0]) * 60 + float(parts[1])
                        elif len(parts) == 3:
                            total += float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        total += float(dur)
                else:
                    total += float(dur)
            except (ValueError, TypeError):
                pass
                
        h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
        
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        else:
            return f"{m}:{s:02d}"
            
    def refresh_playlist_stats(self):
        """Manually trigger a UI refresh of the playlist duration and track count."""
        if hasattr(self, 'header') and hasattr(self, '_playlist'):
            name = self.header.playlist_title.text()
            self.header.set_info(name, len(self._playlist), self._format_playlist_duration())
            
        if hasattr(self, 'table') and hasattr(self.table, '_render_tracks'):
            self.table._render_tracks()
    
    def set_playlist(self, name: str, tracks: list):
        """Set playlist data."""
        self._playlist = tracks
        
        # Clear search
        if hasattr(self, '_search_input'):
            self._search_input.clear()
        
        # Update track count label
        if hasattr(self, '_track_count_label'):
            self._track_count_label.setText(f"{len(tracks)} tracks")
        
        self.header.set_info(name, len(tracks), self._format_playlist_duration())
        self.table.set_tracks(tracks)
        
        # Load user-selected cover art for this playlist (if previously saved)
        self.header.load_saved_cover(name)
    

    def _play_track(self, index: int):

        # If filter is active, translate display index to original index
        if hasattr(self, '_filtered_indices') and self._filtered_indices is not None:
            if 0 <= index < len(self._filtered_indices):
                index = self._filtered_indices[index]
            else:
                return  # Invalid filtered index
        
        if 0 <= index < len(self._playlist):
            self._current_index = index
            track = self._playlist[index]
            
            # Anti-Race Condition Tracking for Asynchronous youtube-dl queries 
            if getattr(self, '_stream_request_id', None) is None:
                self._stream_request_id = 0
            self._stream_request_id += 1
            
            # Subdue overlapping QMediaPlayer triggers
            self._player.stop()
            if hasattr(self, 'resume_banner') and self.resume_banner.isVisible():
                self.resume_banner.hide()
            
            # Hard kill any overlapping VLC active streams before launching next
            if getattr(self, '_playing_vlc', False) and hasattr(self, '_vlc_player') and self._vlc_player:
                try:
                    self._vlc_player.stop()
                    self._playing_vlc = False
                    if hasattr(self, '_vlc_timer'):
                        self._vlc_timer.stop()
                except Exception:
                    pass
            
            title = track.get('title', 'Unknown')
            artist = track.get('artist', '')
            
            self.player_bar.set_track_info(title, artist)
            self.table.highlight_playing(index)
            
            # Reset crossfade prevention for new track
            self._crossfade_disabled_for_current = False
            
            path = track.get('path', '')
            is_online = track.get('is_online', False)
            
            if is_online:
                print(f"Loading online stream: {title}")
                self._load_and_play_stream(track)
            elif path and os.path.exists(path):
                print(f"Playing: {title}")
                # Set flag to ignore StoppedState during track switch
                self._switching_track = True

                self._player.setSource(QUrl.fromLocalFile(path))
                self._set_current_media_local_path(path)
                self._player.play()

                if hasattr(self, '_pending_seek_position') and self._pending_seek_position > 0:
                    target_seek = self._pending_seek_position
                    self._pending_seek_position = 0
                    def _do_resume_seek(status):
                        if status == QMediaPlayer.LoadedMedia or self._player.playbackState() == QMediaPlayer.PlayingState:
                            self._player.setPosition(target_seek)
                            try:
                                self._player.mediaStatusChanged.disconnect(_do_resume_seek)
                            except Exception:
                                pass
                    self._player.mediaStatusChanged.connect(_do_resume_seek)
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(100, lambda: self._player.setPosition(target_seek))

                from PySide6.QtCore import QTimer
                QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
                
                # Sync shuffle pointer if active
                if getattr(self.player_bar, '_is_shuffled', False):
                    self._sync_shuffled_pointer_to_current()
                    
                self._save_state()
                
                # Update Discord Rich Presence
                self._update_discord(title, artist, is_playing=True)

                # Update Windows SMTC metadata (Bluetooth AVRCP / Windows Volume Flyout)
                if hasattr(self, '_smtc_service') and self._smtc_service:
                    thumb = getattr(self, '_current_cover_path', None)
                    self._smtc_service.update_metadata(title=title, artist=artist, thumbnail_path=thumb)
                    self._smtc_service.set_playback_status(is_playing=True)
                    
                # Schedule debounced RAM trim after playback starts
                self.schedule_ram_trim(2000)
            else:
                print(f"File not found: {path}")
    
    def _toggle_play(self):
        from PySide6.QtMultimedia import QMediaPlayer
        
        if hasattr(self, 'resume_banner') and self.resume_banner.isVisible():
            self.resume_banner.hide()
            self._pending_seek_position = 0
        
        # If no track is currently selected/playing, play the first or a random track
        if getattr(self, '_current_index', -1) < 0 and hasattr(self, '_playlist') and self._playlist:
            is_shuffled = getattr(self.player_bar, '_is_shuffled', False) if hasattr(self, 'player_bar') else False
            if is_shuffled:
                if not getattr(self, '_shuffled_sequence', []):
                    self._generate_shuffled_sequence()
                if hasattr(self, '_shuffled_sequence') and self._shuffled_sequence:
                    self._shuffled_pointer = 0
                    self._play_track(self._shuffled_sequence[self._shuffled_pointer])
                    return
            
            self._play_track(0)
            return
            
        # If a track is selected (e.g. from state restore) but not loaded into the player yet
        if getattr(self, '_current_index', -1) >= 0 and self._player.source().isEmpty() and hasattr(self, '_playlist') and self._playlist:
            self._play_track(self._current_index)
            return
            
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()
    
    def _prev_track(self, force_wrap=False):
        """Go to previous track, respecting current playback mode.
        
        Args:
            force_wrap: If True, always wrap around at boundaries
                        regardless of loop mode. Used by keyboard
                        shortcuts (P key). Media keys pass False
                        to respect loop mode boundaries.
        
        Mode behavior:
        - Loop One: Restart current track from beginning
        - Shuffle ON: Pick a random track (excluding current)
        - Loop All OR force_wrap + at first track: Wrap to last track
        - No loop + at first track: Do nothing (stay on current)
        - Default: Follow sorted playlist order
        """
        if not self._playlist:
            return
        
        loop_mode = self.player_bar._loop_mode if hasattr(self, 'player_bar') else "off"
        is_shuffled = self.player_bar._is_shuffled if hasattr(self, 'player_bar') else False
        
        # Loop One: restart current track (only for media keys)
        if loop_mode == "one" and not force_wrap:
            self._play_track(self._current_index)
            return
        
        # Shuffle: navigate via the shuffled sequence deck
        if is_shuffled:
            if not self._shuffled_sequence:
                self._generate_shuffled_sequence()
                
            if self._shuffled_sequence:
                # Move pointer backward
                self._shuffled_pointer -= 1
                
                # Wrap pointer if at start
                if self._shuffled_pointer < 0:
                    if loop_mode == "all" or force_wrap:
                        self._shuffled_pointer = len(self._shuffled_sequence) - 1
                    else:
                        self._shuffled_pointer = 0
                        return # Stay on current
                        
                new_idx = self._shuffled_sequence[self._shuffled_pointer]
                self._play_track(new_idx)
                return
        
        # Determine whether to wrap at boundaries
        can_wrap = force_wrap or loop_mode == "all"
        
        # Get the sorted position of current track
        if hasattr(self, 'table') and hasattr(self.table, '_sorted_indices') and self.table._sorted_indices:
            sorted_indices = self.table._sorted_indices
            try:
                pos = sorted_indices.index(self._current_index)
            except ValueError:
                pos = 0
            
            if pos == 0:
                if can_wrap:
                    self._play_track(sorted_indices[-1])
                # else: no wrap, stay on current
            else:
                self._play_track(sorted_indices[pos - 1])
        else:
            if self._current_index > 0:
                self._play_track(self._current_index - 1)
            elif can_wrap:
                self._play_track(len(self._playlist) - 1)
    
    def _next_track(self, force_wrap=False):
        """Go to next track, respecting current playback mode.
        
        Args:
            force_wrap: If True, always wrap around at boundaries
                        regardless of loop mode. Used by keyboard
                        shortcuts (N key). Media keys pass False
                        to respect loop mode boundaries.
        
        Mode behavior:
        - Loop One: Restart current track from beginning
        - Shuffle ON: Pick a random track (excluding current)
        - Loop All OR force_wrap + at last track: Wrap to first track
        - No loop + at last track: Do nothing (stay on current)
        - Default: Follow sorted playlist order
        """
        if not self._playlist:
            return
        
        loop_mode = self.player_bar._loop_mode if hasattr(self, 'player_bar') else "off"
        is_shuffled = self.player_bar._is_shuffled if hasattr(self, 'player_bar') else False
        
        # Loop One: restart current track (only for media keys)
        if loop_mode == "one" and not force_wrap:
            self._play_track(self._current_index)
            return
        
        # Shuffle: navigate via the shuffled sequence deck
        if is_shuffled:
            if not self._shuffled_sequence:
                self._generate_shuffled_sequence()
                
            if self._shuffled_sequence:
                # Move pointer forward
                self._shuffled_pointer += 1
                
                # Wrap pointer if at end
                if self._shuffled_pointer >= len(self._shuffled_sequence):
                    if loop_mode == "all" or force_wrap:
                        # Reshuffle on full loop for better variety in next pass
                        self._generate_shuffled_sequence()
                        self._shuffled_pointer = 0
                    else:
                        self._shuffled_pointer = len(self._shuffled_sequence) - 1
                        return # Stay on current
                        
                new_idx = self._shuffled_sequence[self._shuffled_pointer]
                self._play_track(new_idx)
                return
        
        # Determine whether to wrap at boundaries
        can_wrap = force_wrap or loop_mode == "all"
        
        # Get the sorted position of current track
        if hasattr(self, 'table') and hasattr(self.table, '_sorted_indices') and self.table._sorted_indices:
            sorted_indices = self.table._sorted_indices
            try:
                pos = sorted_indices.index(self._current_index)
            except ValueError:
                pos = 0
            
            if pos == len(sorted_indices) - 1:
                if can_wrap:
                    self._play_track(sorted_indices[0])
                # else: no wrap, stay on current
            else:
                self._play_track(sorted_indices[pos + 1])
        else:
            if self._current_index < len(self._playlist) - 1:
                self._play_track(self._current_index + 1)
            elif can_wrap:
                self._play_track(0)
    
    def _seek(self, percent: float):
        # VLC overlay seek intercept
            
        if self._player.duration() > 0:
            self._player.setPosition(int(percent * self._player.duration()))
            self._save_state()
    
    def _set_volume(self, value: int):
        # Apply curve for more natural volume feeling
        linear = value / 100.0  # 0.0 to 1.25 (with boost)
        if linear <= 0:
            volume = 0.0
        elif linear <= 1.0:
            # Square curve for 0-100%: makes low values quieter
            volume = linear * linear
        else:
            # Above 100%: linear boost (100% + extra)
            # 125% slider = 100% + 25% extra = 1.0 + 0.25 = 1.25
            volume = 1.0 + (linear - 1.0)
        
        self._user_volume = volume  # Store for crossfade
        self._audio_output.setVolume(volume)
        self._save_state()
    

    def _show_load_url_dialog(self):
        """Show input dialog for stream URL."""
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Open Stream", "Enter stream URL (YouTube, SoundCloud, Spotify, etc):")
        if ok and url.strip():
            url = url.strip()
            
            # --- Fast Path ---
            import urllib.request
            import urllib.parse
            import json
            import ssl
            
            initial_title = None
            initial_artist = None
            
            try:
                is_fast_path = False
                if ('youtube.com' in url or 'youtu.be' in url) and 'playlist?list=' not in url:
                    api_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
                    is_fast_path = True
                elif 'soundcloud.com/' in url and '/sets/' not in url:
                    api_url = f"https://soundcloud.com/oembed?url={urllib.parse.quote(url)}&format=json"
                    is_fast_path = True
                    
                if is_fast_path:
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    ctx = ssl._create_unverified_context()
                    with urllib.request.urlopen(req, timeout=1.5, context=ctx) as response:
                        res = json.loads(response.read().decode('utf-8'))
                        initial_title = res.get('title')
                        initial_artist = res.get('author_name')
            except Exception:
                pass
            
            needs_background_fetch = False
            
            if initial_title:
                track = {
                    'path': url,
                    'original_url': url,
                    'title': initial_title,
                    'artist': initial_artist or 'Unknown',
                    'duration': 0,
                    'is_online': True,
                    'mtime': 0,
                }
            else:
                track = {
                    'path': url,
                    'original_url': url,
                    'title': 'Resolving link...',
                    'artist': url,
                    'duration': 0,
                    'is_online': True,
                    'mtime': 0,
                    'dummy': True
                }
                needs_background_fetch = True
            
            if not hasattr(self, '_playlist') or self._playlist is None:
                self._playlist = []
                
            was_empty = (len(self._playlist) == 0)
            self._playlist.append(track)
            
            playlist_name = "Online Streams"
            if self._music_folder and hasattr(self, 'header'):
                playlist_name = self.header.playlist_title.text()
                
            self.set_playlist(playlist_name, self._playlist)
            if was_empty:
                self._play_track(0)
                
            if needs_background_fetch:
                self._fetch_url_metadata(url, track)

    def _fetch_url_metadata(self, url, dummy_track=None):
        """Fetch metadata for a URL using yt-dlp in a background thread."""
        import threading
        
        def fetch():
            import sys
            import json
            import os
            
            try:
                import yt_dlp
            except ImportError as e:
                print(f"yt-dlp core module missing entirely: {e}")
                return
            
            ydl_opts = {
                'extract_flat': 'in_playlist',
                'playlistend': 50,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 10,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'mweb', 'web']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return
                    
                    tracks_to_add = []
                    entries = info.get('entries', [])
                    if entries:
                        for idx, entry in enumerate(entries):
                            if entry:
                                tracks_to_add.append({
                                    'path': entry.get('url', ''),
                                    'original_url': entry.get('url', ''),
                                    'title': entry.get('title', f"Stream {idx+1}"),
                                    'artist': entry.get('uploader', info.get('uploader', 'Unknown')),
                                    'duration': entry.get('duration') or 0,
                                    'is_online': True,
                                    'mtime': 0,
                                })
                    else:
                        tracks_to_add.append({
                            'path': info.get('webpage_url', info.get('url', url)),
                            'original_url': info.get('webpage_url', info.get('url', url)),
                            'title': info.get('title', 'Unknown Stream'),
                            'artist': info.get('uploader', 'Unknown'),
                            'duration': info.get('duration') or 0,
                            'is_online': True,
                            'mtime': 0,
                        })
                    if tracks_to_add:
                        def update_ui():
                            # Safety check to reliably replace the dummy object
                            try:
                                if dummy_track and dummy_track in self._playlist:
                                    idx = self._playlist.index(dummy_track)
                                    self._playlist[idx:idx+1] = tracks_to_add
                                else:
                                    if not dummy_track:
                                        self._playlist.extend(tracks_to_add)
                                        
                                # Refresh table and header
                                if hasattr(self, 'table') and hasattr(self.table, '_render_tracks'):
                                    self.table._render_tracks()
                                if hasattr(self, 'header') and hasattr(self.header, 'set_info'):
                                    total = sum(int(t.get('duration') or 0) for t in self._playlist)
                                    h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
                                    duration_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                                    self.header.set_info(self.header.playlist_title.text(), len(self._playlist), duration_str)
                            except Exception as e:
                                print(f"Error updating UI after yt-dlp fetch: {e}")
                                
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(0, update_ui)
            except Exception as e:
                print(f"Failed to fetch metadata (yt-dlp): {e}")
                if dummy_track:
                    dummy_track['title'] = 'Failed to load stream'
                    dummy_track['artist'] = ''
                    dummy_track.pop('dummy', None)
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.table._render_tracks() if hasattr(self, 'table') else None)
                
        threading.Thread(target=fetch, daemon=True).start()
        
    def _load_and_play_stream(self, track, start_pos=0):
        """Fetch the direct stream URL and play it using C++ Fast-Path with yt-dlp fallback."""
        import threading
        from fast_stream_resolver import resolve_stream
        
        request_id = getattr(self, '_stream_request_id', 0)
        direct_url = track.get('stream_url')
        if direct_url and (direct_url.startswith('http://') or direct_url.startswith('https://')):
            self._play_resolved_stream(direct_url, track, request_id, start_pos=start_pos)
            return

        self.player_bar.set_track_info(f"Loading {track.get('title', 'Stream')}...", track.get('artist', ''))
        
        raw_url = track.get('original_url') or track.get('path', '')
        target_url = prepare_ytdlp_target(raw_url)
        
        def fetch():
            res = resolve_stream(target_url)
            if res.get('success') and res.get('stream_url'):
                stream_url = res['stream_url']
                if res.get('original_url'):
                    track['original_url'] = res['original_url']
                track['stream_url'] = stream_url
                if res.get('title') and (not track.get('title') or track.get('title').startswith('Loading') or track.get('title') == 'Stream'):
                    track['title'] = res['title']
                if res.get('artist') and not track.get('artist'):
                    track['artist'] = res['artist']
                if res.get('duration') and not track.get('duration'):
                    track['duration'] = res['duration']
                    
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._play_resolved_stream(stream_url, track, request_id, start_pos=start_pos))
            else:
                print(f"[FastStream] Resolution failed for {target_url}: {res.get('error')}")
                self._revert_loading_ui(track, request_id)
                
        threading.Thread(target=fetch, daemon=True).start()
        
    def _revert_loading_ui(self, track, request_id):
        # Abort overlapping race condition requests
        if request_id != getattr(self, '_stream_request_id', 0):
            return
        from PySide6.QtCore import QTimer
        def restore():
            title = track.get('title', 'Unknown Stream')
            artist = track.get('artist', '')
            self.player_bar.set_track_info(f"Failed: {title[:20]}", artist)
        QTimer.singleShot(0, restore)
        
    def _play_resolved_stream(self, stream_url, track, request_id, start_pos=0):
        """Play the resolved direct stream URL with QMediaPlayer."""
        from PySide6.QtCore import QUrl, QTimer
        
        # Abort overlapping race condition requests (e.g if user presses Next 5 times very fast)
        if request_id != getattr(self, '_stream_request_id', 0):
            return
            
        title = track.get('title', 'Unknown Stream')
        artist = track.get('artist', '')
        
        print(f"Playing resolved stream: {title}")
        
        self.player_bar.set_track_info(title, artist)
        self.table.highlight_playing(self._current_index)
        
        self._switching_track = True
        
        self.player_bar.set_track_info(title, artist)
        self.table.highlight_playing(self._current_index)
        self._player.setSource(QUrl(stream_url))
        self._set_current_media_url(stream_url)
        self._player.play()
        if start_pos > 0:
            QTimer.singleShot(300, lambda: self._player.setPosition(int(start_pos)))
            
        QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
        self._save_state()
        self._update_discord(title, artist, is_playing=True)
        
        # Background pre-fetching of next track in playlist (C++ 0ms instant Next play)
        try:
            from fast_stream_resolver import prefetch_track
            next_idx = self._current_index + 1
            if hasattr(self, '_playlist') and 0 <= next_idx < len(self._playlist):
                next_t = self._playlist[next_idx]
                if isinstance(next_t, dict) and (next_t.get('is_online') or next_t.get('is_stream')):
                    prefetch_track(next_t)
        except Exception:
            pass
            
        # Schedule debounced RAM trim after stream playback starts
        self.schedule_ram_trim(2000)
    

    def eventFilter(self, obj, event):
        """Event filter for fullscreen key and mouse events."""
        from PySide6.QtCore import QEvent
        
        # Handle double-click to toggle fullscreen (works in both fullscreen and normal mode)
        if event.type() == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                try:
                    self._toggle_fullscreen()
                except Exception:
                    pass
                return True
        
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            # Handle key press events
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key_F or key == Qt.Key_Escape:
                    try:
                        self._toggle_fullscreen()
                    except Exception:
                        pass
                    return True
            
            # Handle mouse move events for player bar hover
            elif event.type() == QEvent.Type.MouseMove:
                parent_window = self.window()
                if parent_window:
                    screen_height = parent_window.height()
                    mouse_y = event.globalPosition().y() - parent_window.y()
                    
                    if mouse_y >= screen_height - 100:
                        # Show playerbar with animation
                        if not self.player_bar.isVisible():
                            self._animate_playerbar(show=True)
                        
                        # Restart hide timer
                        if hasattr(self, '_playerbar_hide_timer'):
                            self._playerbar_hide_timer.start(2000)
        
        return super().eventFilter(obj, event)
    
    
    def _animate_playerbar(self, show: bool):
        """Animate player bar fade in/out using window opacity."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        
        if not hasattr(self, '_playerbar_fade_animation'):
            self._playerbar_fade_animation = QPropertyAnimation(self.player_bar, b"windowOpacity")
            self._playerbar_fade_animation.setDuration(200)
            self._playerbar_fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Disconnect previous finished callbacks
        try:
            self._playerbar_fade_animation.finished.disconnect()
        except RuntimeError:
            pass
        
        if show:
            self.player_bar.show()
            self._playerbar_fade_animation.setStartValue(0.0)
            self._playerbar_fade_animation.setEndValue(1.0)
        else:
            # Only hide if still in fullscreen when the hide is requested
            if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
                # Don't hide if cursor is over the PlayerBar area
                try:
                    local = self.player_bar.mapFromGlobal(self.cursor().pos())
                    if QRect(0, 0, self.player_bar.width(), self.player_bar.height()).contains(local):
                        return
                except Exception:
                    pass
                
                self._playerbar_fade_animation.setStartValue(1.0)
                self._playerbar_fade_animation.setEndValue(0.0)
                self._playerbar_fade_animation.finished.connect(self._on_playerbar_fade_finished)
            else:
                return  # Not in fullscreen, don't hide
        
        self._playerbar_fade_animation.start()
    
    def _on_playerbar_fade_finished(self):
        """Called when playerbar fade-out animation finishes."""
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            self.player_bar.hide()
            self.player_bar.setWindowOpacity(1.0)  # Reset for next show
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for fullscreen playerbar show."""
        super().mouseMoveEvent(event)
        
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            # Check if mouse is near bottom of screen (within 100px)
            screen_height = self.height()
            mouse_y = event.pos().y()
            
            if mouse_y >= screen_height - 100:
                # Show playerbar with animation
                if not self.player_bar.isVisible():
                    self._animate_playerbar(show=True)
                
                # Restart hide timer
                if hasattr(self, '_playerbar_hide_timer'):
                    self._playerbar_hide_timer.start(2000)
    
    
    def _on_duration_changed(self, duration: int):
        """Update the player UI immediately when new media is parsed, without waiting for playback."""
        if not hasattr(self, 'player_bar') or self.player_bar is None:
            return
        
        # Update the duration natively. Handle 0 safely.
        if duration > 0:
            pos = self._player.position()
            is_dragging = getattr(self.player_bar, '_is_dragging_timeline', False)
            self.player_bar.set_position(pos / 1000.0, duration / 1000.0, skip_throttle=is_dragging)
            
            # Sync metadata back to playlist dictionary if it was 0 (the Feedback Loop)
            if hasattr(self, '_playlist') and 0 <= self._current_index < len(self._playlist):
                track = self._playlist[self._current_index]
                if track.get('duration', 0) == 0:
                    track['duration'] = duration / 1000.0
                    self.table._render_tracks()
                    # Also refresh header total
                    total = sum(t.get('duration', 0) for t in self._playlist)
                    h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
                    dur_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                    self.header.set_info(self.header._name if hasattr(self.header, '_name') else "Playlist", len(self._playlist), dur_str)

    def _on_position(self, pos: int):
        if not hasattr(self, 'player_bar') or self.player_bar is None:
            return
        
        dur = self._player.duration()
        # Correctly check the dragging state of the timeline slider from the player bar
        is_dragging = getattr(self.player_bar, '_is_dragging_timeline', False)
        self.player_bar.set_position(pos / 1000.0, dur / 1000.0, skip_throttle=is_dragging)
        
        # Sync metadata back to playlist dictionary just in case durationChanged didn't fire
        if dur > 0 and hasattr(self, '_playlist') and 0 <= self._current_index < len(self._playlist):
            track = self._playlist[self._current_index]
            if track.get('duration', 0) == 0:
                track['duration'] = dur / 1000.0
                self.table._render_tracks()
        
        # Track position for save state (player.position() returns 0 when stopped)
        self._last_known_position = pos

        # Periodic save (every 5 seconds) to prevent data loss on crash/force close
        now = time.time()
        if not hasattr(self, '_last_periodic_save_time'):
            self._last_periodic_save_time = now
        elif now - self._last_periodic_save_time >= 1:
            # Only save if playing or paused (ignore stopped/invalid)
            if self._player.playbackState() in (QMediaPlayer.PlayingState, QMediaPlayer.PausedState):
                # Update last known position before saving to ensure it's current
                self._save_state()
                self._last_periodic_save_time = now
        
        # Loop-one mode: handle replay directly (EndOfMedia may not work in PyInstaller)
        if hasattr(self, 'player_bar') and self.player_bar._loop_mode == "one":
            track = self._playlist[self._current_index] if hasattr(self, '_playlist') and 0 <= self._current_index < len(self._playlist) else {}
            is_online = track.get('is_online', False)
            
            if dur > 0 and not is_online:
                time_remaining = (dur - pos) / 1000.0  # seconds remaining
                # When very close to end (less than 0.5 sec), seek back to start
                if time_remaining <= 0.5 and time_remaining >= 0:
                    self._player.setPosition(0)
            return  # Skip crossfade monitoring
        
        # Crossfade monitoring for other modes
        if self._crossfade_enabled and dur > 0 and not self._crossfade_active:
            if getattr(self, '_crossfade_disabled_for_current', False):
                return
                
            time_remaining = (dur - pos) / 1000.0  # seconds remaining
            if time_remaining <= self._crossfade_duration and time_remaining > 0:
                self._start_crossfade()
        
        # Ensure taskbar widget visualizer stays active when audio position is actively advancing
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            if hasattr(self._taskbar_media_widget, 'visualizer') and self._taskbar_media_widget.visualizer:
                if not self._taskbar_media_widget.visualizer._is_active:
                    if hasattr(self, '_player') and self._player and self._player.playbackState() == QMediaPlayer.PlayingState:
                        self._taskbar_media_widget.set_playback_state(True)
    
    def _on_state(self, state):
        if not hasattr(self, 'player_bar') or self.player_bar is None:
            return
            
        # Ignore StoppedState during track switching or active crossfade
        if state == QMediaPlayer.StoppedState and (getattr(self, '_switching_track', False) or getattr(self, '_crossfade_active', False)):
            return
        
        self.player_bar.set_playing(state == QMediaPlayer.PlayingState)
        
        # Emit signal for external listeners (e.g., taskbar integration)
        self.playbackStateChanged.emit(state)
        
        # Sync with Windows SMTC service for Bluetooth AVRCP & OS Volume Flyout
        if hasattr(self, '_smtc_service') and self._smtc_service:
            is_playing = (state == QMediaPlayer.PlayingState)
            is_stopped = (state == QMediaPlayer.StoppedState)
            self._smtc_service.set_playback_status(is_playing=is_playing, is_stopped=is_stopped)
            
        # Sync with docked taskbar media widget
        if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
            is_play = (state == QMediaPlayer.PlayingState)
            self._taskbar_media_widget.set_playback_state(is_play)
            if is_play and getattr(self, '_taskbar_widget_enabled', True):
                self._taskbar_media_widget.show()
                self._taskbar_media_widget.sync_position()
                self._taskbar_media_widget.raise_()
        
        # In fullscreen: show playerbar when paused, hide when playing
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            if state == QMediaPlayer.PausedState:
                # Stop hide timer and show playerbar when paused
                if hasattr(self, '_playerbar_hide_timer'):
                    self._playerbar_hide_timer.stop()
                if not self.player_bar.isVisible():
                    self._animate_playerbar(show=True)
            elif state == QMediaPlayer.PlayingState:
                # Hide playerbar when playing (after delay)
                if hasattr(self, '_playerbar_hide_timer'):
                    self._playerbar_hide_timer.start(2000)
        
        # Save state when playback stops or pauses
        if state in (QMediaPlayer.StoppedState, QMediaPlayer.PausedState):
            self._save_state()
    

    def _dismiss_banner_by_user(self):
        """User explicitly clicked 'Dismiss' button. Clear saved resume state."""
        print("[Music DEBUG] _dismiss_banner_by_user: Clearing saved resume position")
        self._last_known_position = 0
        self._pending_seek_position = 0
        self._pending_single_track_resume = None
        self._save_state()
        try:
            if hasattr(self.resume_banner, 'animate_out'):
                self.resume_banner.animate_out()
            else:
                self.resume_banner.hide()
        except Exception:
            self.resume_banner.hide()

    def _dismiss_banner_by_timeout(self):
        """Banner timed out naturally. Hide banner but keep last_position for next session."""
        print("[Music DEBUG] _dismiss_banner_by_timeout: Auto-dismissing without clearing saved position")
        try:
            if hasattr(self.resume_banner, 'animate_out'):
                self.resume_banner.animate_out()
            else:
                self.resume_banner.hide()
        except Exception:
            self.resume_banner.hide()

    def _dismiss_banner(self):
        self._dismiss_banner_by_timeout()
        
    def _finalize_dismiss(self):
        if hasattr(self, '_pending_single_track_resume'):
            self._pending_single_track_resume = None

    def _resume_playback_from_banner(self):
        print("[Music DEBUG] _resume_playback_from_banner triggered!")
        try:
            self._finalize_resume()
        except Exception as e:
            print(f"[Music DEBUG ERROR] Exception in _finalize_resume: {e}")
            import traceback
            traceback.print_exc()

        try:
            if hasattr(self.resume_banner, 'animate_out'):
                self.resume_banner.animate_out()
            else:
                self.resume_banner.hide()
        except Exception:
            self.resume_banner.hide()

    def _resume_and_open_folder(self):
        print("[Music DEBUG] _resume_and_open_folder triggered!")
        try:
            self._finalize_resume_and_open_folder()
        except Exception as e:
            print(f"[Music DEBUG ERROR] Exception in _finalize_resume_and_open_folder: {e}")
            import traceback
            traceback.print_exc()

        try:
            if hasattr(self.resume_banner, 'animate_out'):
                self.resume_banner.animate_out()
            else:
                self.resume_banner.hide()
        except Exception:
            self.resume_banner.hide()

    def _finalize_resume_and_open_folder(self):
        print("[Music DEBUG] Executing 'Resume and folder' parent folder expansion...")
        target_path = None
        seek_pos = 0
        
        if hasattr(self, '_pending_single_track_resume') and self._pending_single_track_resume:
            target_path = self._pending_single_track_resume.get('path')
            seek_pos = self._pending_single_track_resume.get('position', 0)
        elif hasattr(self, '_playlist') and self._playlist and getattr(self, '_current_index', -1) >= 0:
            try:
                target_path = self._playlist[self._current_index].get('path')
            except Exception:
                target_path = None

        if target_path and os.path.exists(target_path):
            matched_folder = None
            norm_target_path = os.path.normcase(os.path.normpath(target_path))
            
            # Check settings.json media_library_items
            settings_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json')
            try:
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        s_data = json.load(f)
                        for item in s_data.get('media_library_items', []):
                            if item.get('is_folder'):
                                f_path = os.path.normcase(os.path.normpath(item.get('path', '')))
                                if norm_target_path.startswith(f_path + os.sep) or norm_target_path == f_path:
                                    matched_folder = item.get('path')
                                    break
            except Exception:
                pass
            
            parent_folder = matched_folder if matched_folder else os.path.dirname(target_path)
            
            # If parent_folder is a broad root directory containing other registered media library folders, do not swallow the entire root
            is_root_container = False
            if not matched_folder and parent_folder and os.path.isdir(parent_folder):
                try:
                    if os.path.exists(settings_path):
                        with open(settings_path, 'r', encoding='utf-8') as f:
                            s_data = json.load(f)
                            norm_parent = os.path.normcase(os.path.normpath(parent_folder))
                            for item in s_data.get('media_library_items', []):
                                if item.get('is_folder'):
                                    f_p = os.path.normcase(os.path.normpath(item.get('path', '')))
                                    if f_p.startswith(norm_parent + os.sep) and f_p != norm_parent:
                                        is_root_container = True
                                        break
                except Exception:
                    pass

            if is_root_container:
                print(f"[Music DEBUG] Track is a standalone file in root directory '{parent_folder}'. Resuming as single track.")
                self._finalize_resume()
                return

            if parent_folder and os.path.isdir(parent_folder):
                folder_name = os.path.basename(parent_folder) or "Folder"
                print(f"[Music DEBUG] Expanding parent folder '{folder_name}' into Track Playlist: '{parent_folder}'")
                self._load_tracks_from_folder(parent_folder)
                
                # Assign playlist_group so the folder remains EXPANDED as a group in PlaylistTable
                for t in self._playlist:
                    t['playlist_group'] = folder_name
                    
                self.table.set_tracks(self._playlist)
                
                # Locate target track in expanded playlist
                norm_target = os.path.normpath(target_path).lower()
                found_idx = next((i for i, t in enumerate(self._playlist) if os.path.normpath(t.get('path', '')).lower() == norm_target), 0)
                
                self._pending_single_track_resume = None
                if seek_pos > 0:
                    self._pending_seek_position = seek_pos
                elif hasattr(self, '_last_known_position') and self._last_known_position > 0:
                    self._pending_seek_position = self._last_known_position
                    
                if hasattr(self, 'stack'):
                    self.stack.setCurrentIndex(0)
                self._play_track(found_idx)
                return

        print("[Music DEBUG] Parent folder unavailable, falling back to single track resume.")
        self._finalize_resume()

    def _finalize_resume(self):
        print(f"[Music DEBUG] _finalize_resume triggered! pending_single={getattr(self, '_pending_single_track_resume', None)}, current_index={getattr(self, '_current_index', -1)}, playlist_len={len(getattr(self, '_playlist', []))}")
        if hasattr(self, '_pending_single_track_resume') and self._pending_single_track_resume:
            track_info = self._pending_single_track_resume
            import datetime
            try:
                mtime = os.path.getmtime(track_info['path'])
                dt = datetime.datetime.fromtimestamp(mtime)
                date_str = dt.strftime("%b %d, %Y")
            except Exception:
                date_str = ""
                
            track = {
                'path': track_info['path'],
                'title': track_info['title'],
                'artist': 'Single Track',
                'duration': 0,
                'date_added': date_str
            }
            target_path = track_info['path']
            if not hasattr(self, '_playlist') or self._playlist is None:
                self._playlist = []
                
            found_index = next((i for i, t in enumerate(self._playlist) if t.get('path') == target_path), -1)
            if found_index == -1:
                self._playlist.append(track)
                found_index = len(self._playlist) - 1
                
            print(f"[Music DEBUG] Resuming pending single track: '{track_info['title']}' at index {found_index}")
            self.table.set_tracks(self._playlist)
            if hasattr(self, 'header') and hasattr(self.header, 'set_info'):
                pl_name = track_info.get('playlist_name', 'Single Track')
                self.header.set_info(pl_name, len(self._playlist), self._format_playlist_duration())
                self.header.load_saved_cover(pl_name)
            self._pending_single_track_resume = None
            
            if track_info.get('position', 0) > 0:
                self._pending_seek_position = track_info['position']
                
            if hasattr(self, 'stack'):
                self.stack.setCurrentIndex(0)
            self._play_track(found_index)
            return

        if hasattr(self, '_playlist') and self._playlist and getattr(self, '_current_index', -1) >= 0:
            print(f"[Music DEBUG] Resuming existing track at index {self._current_index}")
            self.table.set_tracks(self._playlist)
            if hasattr(self, 'header') and hasattr(self.header, 'load_saved_cover'):
                self.header.load_saved_cover()
            if hasattr(self, 'stack'):
                self.stack.setCurrentIndex(0)
            if hasattr(self, '_last_known_position') and self._last_known_position > 0:
                self._pending_seek_position = self._last_known_position
            self._play_track(self._current_index)
            return
            
        print("[Music DEBUG] Fallback to _toggle_play")
        self._toggle_play()

    def _load_last_state(self):
        """Load last music folder and track from config."""
        import json
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                # Load folder
                folder = state.get('folder', '')
                if folder and os.path.exists(folder):
                    self._music_folder = folder
                    self._load_tracks_from_folder(folder)
                elif hasattr(self, 'header') and hasattr(self.header, 'load_saved_cover'):
                    # Ensure covers are loaded even if no folder is active
                    self.header.load_saved_cover(state.get('playlist_name', ''))
                    
                # Restore last track
                last_path = state.get('last_track_path', '')
                if last_path:
                    last_path_norm = last_path.replace('\\', '/')
                    track_found = False
                    
                    # Find track index by path
                    for i, track in enumerate(self._playlist):
                        track_path_norm = track.get('path', '').replace('\\', '/')
                        if track_path_norm == last_path_norm:
                            self._current_index = i
                            self.table.highlight_playing(i)
                            self.player_bar.set_track_info(
                                track.get('title', ''), 
                                track.get('artist', '')
                            )
                            
                            # Set source so play button works
                            path = track.get('path', '')
                            if path and os.path.exists(path):
                                self._player.setSource(QUrl.fromLocalFile(path))
                                try:
                                    self._set_current_media_local_path(path)
                                except Exception:
                                    pass
                                
                                # Show resume banner if last position > 0, but DO NOT auto-seek
                                last_pos = state.get('last_position', 0)
                                if last_pos > 0:
                                    self._last_known_position = last_pos
                                    self._pending_seek_position = last_pos
                                    self.resume_banner.set_track_title(track.get('title', 'Unknown'))
                                    self.resume_banner.show()
                                    self.resume_banner.raise_()
                            
                            if hasattr(self, 'header') and hasattr(self.header, 'load_saved_cover'):
                                self.header.load_saved_cover(state.get('playlist_name', ''))
                                
                            print(f"Restored last track: {track.get('title')}")
                            track_found = True
                            break
                    
                    if not track_found and os.path.exists(last_path):
                        # Track not found in playlist, but file exists.
                        last_pos = state.get('last_position', 0)
                        title = os.path.splitext(os.path.basename(last_path))[0]
                        self._pending_single_track_resume = {
                            'path': last_path,
                            'title': title,
                            'position': last_pos,
                            'playlist_name': state.get('playlist_name', 'Previous Session')
                        }
                        if hasattr(self, 'header') and hasattr(self.header, 'load_saved_cover'):
                            self.header.load_saved_cover(state.get('playlist_name', 'Previous Session'))
                            
                        if last_pos > 0:
                            self._last_known_position = last_pos
                            self.resume_banner.set_track_title(title)
                            self.resume_banner.show()
                            self.resume_banner.raise_()
                
                # Restore volume
                volume = state.get('volume', 100)
                self._audio_output.setVolume(volume / 100.0)
                self.player_bar.volume_slider.setValue(volume)
                
                # Restore aspect ratio
                
                # Restore shuffle and loop mode
                shuffle = state.get('shuffle', False)
                self.player_bar.set_shuffle(shuffle)
                
                if 'loop_mode' in state:
                    self.player_bar.set_loop_mode(state['loop_mode'])
                    
                # Restore audio device
                auto_audio = state.get('auto_audio_device', True)
                self._auto_audio_device = auto_audio
                if not auto_audio:
                    device_id = state.get('audio_device_id', '')
                    if device_id:
                        from PySide6.QtMultimedia import QMediaDevices
                        for device in QMediaDevices.audioOutputs():
                            if device.id().data().decode('utf-8', 'ignore') == device_id:
                                if getattr(self, '_audio_output', None) is not None:
                                    self._audio_output.setDevice(device)
                                if getattr(self, '_audio_output2', None) is not None:
                                    self._audio_output2.setDevice(device)
                                break
                                
                # Restore playback speed
                speed = state.get('playback_speed', 1.0)
                if hasattr(self, '_set_playback_speed'):
                    self._set_playback_speed(speed)
                    
                # Restore crossfade
                crossfade_enabled = state.get('crossfade_enabled', True)
                crossfade_dur = state.get('crossfade_duration', 3.0)
                if hasattr(self, '_crossfade_slider'):
                    # Temporarily block signals to prevent redundant save
                    self._crossfade_slider.blockSignals(True)
                    if crossfade_enabled:
                        self._crossfade_slider.setValue(int(crossfade_dur))
                        if hasattr(self, '_crossfade_label'):
                            self._crossfade_label.setText(f"{int(crossfade_dur)} sec")
                    else:
                        self._crossfade_slider.setValue(0)
                        if hasattr(self, '_crossfade_label'):
                            self._crossfade_label.setText("Off")
                    self._crossfade_slider.blockSignals(False)
                    self._crossfade_enabled = crossfade_enabled
                    self._crossfade_duration = crossfade_dur
                
                # Restore shuffle sequence and pointer
                self._shuffled_sequence = state.get('shuffled_sequence', [])
                self._shuffled_pointer = state.get('shuffled_pointer', -1)
                
                # Verify consistency of restored shuffle data
                if self._shuffled_sequence and (len(self._shuffled_sequence) != len(self._playlist)):
                    # Playlist size changed since last run, invalidate sequence
                    self._shuffled_sequence = []
                    self._shuffled_pointer = -1
                
                # Restore taskbar widget state & position & collapse & custom position & lock & opacity
                taskbar_enabled = state.get('taskbar_widget_enabled', True)
                self._taskbar_widget_enabled = taskbar_enabled
                taskbar_pos = state.get('taskbar_widget_position', 'left')
                self._taskbar_widget_position = taskbar_pos
                taskbar_custom_pos = state.get('taskbar_widget_custom_pos', None)
                taskbar_collapsed = state.get('taskbar_widget_collapsed', False)
                taskbar_locked = state.get('taskbar_widget_locked', False)
                taskbar_width = state.get('taskbar_widget_width', 240)
                taskbar_opacity = state.get('taskbar_widget_opacity', 75)
                self._taskbar_widget_opacity = taskbar_opacity

                if hasattr(self, 'action_taskbar_enable'):
                    self.action_taskbar_enable.blockSignals(True)
                    self.action_taskbar_enable.setChecked(taskbar_enabled)
                    self.action_taskbar_enable.blockSignals(False)

                if hasattr(self, '_taskbar_pos_actions'):
                    for m_key, action in self._taskbar_pos_actions.items():
                        action.blockSignals(True)
                        action.setChecked(m_key == taskbar_pos)
                        action.blockSignals(False)

                if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
                    if taskbar_custom_pos:
                        self._taskbar_media_widget._custom_pos = taskbar_custom_pos
                    self._taskbar_media_widget.set_locked(taskbar_locked)
                    self._taskbar_media_widget.set_position_mode(taskbar_pos)
                    self._taskbar_media_widget._expanded_width = taskbar_width
                    self._taskbar_media_widget.set_widget_opacity(taskbar_opacity)
                    if taskbar_collapsed:
                        self._taskbar_media_widget.collapse(animate=False)
                    else:
                        self._taskbar_media_widget.expand(animate=False)
                    if taskbar_enabled and (self.isVisible() or (hasattr(self, '_player') and self._player and self._player.playbackState() == QMediaPlayer.PlayingState)):
                        self._taskbar_media_widget.show()
                        self._taskbar_media_widget.sync_position()
                    else:
                        self._taskbar_media_widget.hide()

                print(f"Loaded state: {folder}")
        except Exception as e:
            print(f"Failed to load state: {e}")
        finally:
            self._initial_state_loaded = True
    
    def _save_state(self):
        """Save current state to config."""
        import json
        try:
            if not getattr(self, '_initial_state_loaded', False):
                return
            if not hasattr(self, 'player_bar') or self.player_bar is None:
                return
                
            current_track_path = ''
            position = 0
            
            if hasattr(self, '_playlist') and self._playlist and len(self._playlist) > 0:
                if 0 <= self._current_index < len(self._playlist):
                    current_track_path = self._playlist[self._current_index].get('path', '')
                # Use tracked position (player.position() returns 0 when stopped)
                position = getattr(self, '_last_known_position', 0) or (self._player.position() if hasattr(self, '_player') and self._player else 0)
            elif getattr(self, '_pending_single_track_resume', None):
                current_track_path = self._pending_single_track_resume.get('path', '')
                position = getattr(self, '_last_known_position', 0) or self._pending_single_track_resume.get('position', 0)
            elif getattr(self, '_current_media_path', None) and os.path.exists(self._current_media_path):
                current_track_path = self._current_media_path
                position = getattr(self, '_last_known_position', 0) or (self._player.position() if hasattr(self, '_player') and self._player else 0)
            else:
                self._music_folder = ''
                self._last_known_position = 0
                self._pending_seek_position = 0
                
            print(f"[Music] Saving position: {position}ms (_last_known: {getattr(self, '_last_known_position', 'not set')})")
            
            is_collapsed = False
            is_locked = False
            custom_w = 240
            custom_pos = None
            pos_mode = getattr(self, '_taskbar_widget_position', 'left')
            widget_opacity = getattr(self, '_taskbar_widget_opacity', 75)
            if hasattr(self, '_taskbar_media_widget') and self._taskbar_media_widget:
                is_collapsed = getattr(self._taskbar_media_widget, '_is_collapsed', False)
                is_locked = getattr(self._taskbar_media_widget, '_is_locked', False)
                custom_w = getattr(self._taskbar_media_widget, '_expanded_width', 240)
                custom_pos = getattr(self._taskbar_media_widget, '_custom_pos', None)
                pos_mode = self._taskbar_media_widget.get_position_mode()
                widget_opacity = self._taskbar_media_widget.get_widget_opacity()

            state = {
                'folder': self._music_folder or '',
                'playlist_name': getattr(self.header, '_name', 'Previous Session') if hasattr(self, 'header') else 'Previous Session',
                'last_track_path': current_track_path,
                'last_position': position,
                'volume': self.player_bar.volume_slider.value(),
                'shuffle': getattr(self.player_bar, '_is_shuffled', False),
                'loop_mode': getattr(self.player_bar, '_loop_mode', 'off'),
                'shuffled_sequence': self._shuffled_sequence,
                'shuffled_pointer': self._shuffled_pointer,
                'auto_audio_device': getattr(self, '_auto_audio_device', True),
                'audio_device_id': getattr(self._audio_output.device(), 'id', lambda: b'')().data().decode('utf-8', 'ignore') if hasattr(self, '_audio_output') and hasattr(self._audio_output, 'device') else '',
                'playback_speed': getattr(self._player, 'playbackRate', lambda: 1.0)() if hasattr(self, '_player') else 1.0,
                'crossfade_enabled': getattr(self, '_crossfade_enabled', True),
                'crossfade_duration': getattr(self, '_crossfade_duration', 3.0),
                'taskbar_widget_enabled': getattr(self, '_taskbar_widget_enabled', True),
                'taskbar_widget_position': pos_mode,
                'taskbar_widget_custom_pos': custom_pos,
                'taskbar_widget_collapsed': is_collapsed,
                'taskbar_widget_locked': is_locked,
                'taskbar_widget_width': custom_w,
                'taskbar_widget_opacity': widget_opacity
            }
            
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            
            print(f"Saved state: {current_track_path}")
        except Exception as e:
            print(f"Failed to save state: {e}")
    
    def _browse_folder_direct(self):
        """Quick folder selection from player bar button or Menu Bar (Ctrl+Shift+O)."""
        from PySide6.QtWidgets import QFileDialog
        
        # Check if user is currently on Media Library tab (index 1)
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1 and hasattr(self, 'media_lib_page') and self.media_lib_page:
            self.media_lib_page._add_single_folder()
            return
        
        start = getattr(self, '_music_folder', None) or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Select Media Folder", start, QFileDialog.ShowDirsOnly)
        
        if folder:
            self._music_folder = folder
            self._load_tracks_from_folder(folder)
            # Save immediately so folder is remembered after restart
            QTimer.singleShot(500, self._save_state)

    def _open_multiple_files_direct(self):
        """Pick multiple media files and append them to current playlist or add to Media Library."""
        from PySide6.QtWidgets import QFileDialog
        import datetime
        import os
        
        # Check if user is currently on Media Library tab (index 1)
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1 and hasattr(self, 'media_lib_page') and self.media_lib_page:
            self.media_lib_page._add_multiple_files()
            return
            
        audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        filters = "Media Files (" + " ".join(["*" + e for e in audio_exts]) + ");;All Files (*.*)"
        start_dir = getattr(self, '_music_folder', None) or os.path.expanduser("~")
        dialog = QFileDialog(self, "Open Multiple Media Files", start_dir)
        dialog.setNameFilter(filters)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setOption(QFileDialog.ShowDirsOnly, False)
        paths = dialog.selectedFiles() if dialog.exec() else []
        
        if paths:
            tracks_to_append = []
            for path in paths:
                ext = os.path.splitext(path)[1].lower()
                title = os.path.splitext(os.path.basename(path))[0]
                
                try:
                    mtime = os.path.getmtime(path)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    date_str = dt.strftime("%b %d, %Y")
                except Exception:
                    date_str = ""
                    
                track = {
                    'path': path,
                    'title': title,
                    'artist': 'Single Track',
                    'duration': 0,
                    'date_added': date_str
                }
                
                tracks_to_append.append(track)
                
            self._append_tracks_to_playlist(tracks_to_append)
            self._fetch_metadata_async(self._playlist, "Multiple Files")
            QTimer.singleShot(500, self._save_state)
            
    def _prompt_play_url(self):
        if hasattr(self, 'floating_url_input'):
            if self.floating_url_input.isVisible() and not getattr(self.floating_url_input, '_is_closing', False):
                self.floating_url_input.close_panel()
            else:
                self.floating_url_input.show_panel()

    def _process_url_stream_async(self, url, mode=None):
        import threading
        
        if not mode:
            from PySide6.QtCore import QSettings
            settings = QSettings("TDD131", "HELXAID")
            mode = settings.value("MusicPlayer/stream_mode", "buffer", type=str)
        if mode not in ("buffer", "direct"):
            mode = "buffer"
            
        from PySide6.QtWidgets import QMessageBox
        
        if hasattr(self, 'stream_loading'):
            display_url = url if len(url) <= 45 else url[:42] + "..."
            mode_tag = "Direct Stream" if mode == "direct" else "Buffer Cache"
            self.stream_loading.show_msg(f"Extracting ({mode_tag})\n{display_url}")
            
        class YtLogger:
            def __init__(self, overlay):
                self.overlay = overlay
            def debug(self, msg):
                if hasattr(self.overlay, 'log_updated'):
                    self.overlay.log_updated.emit(msg)
            def warning(self, msg):
                if hasattr(self.overlay, 'log_updated'):
                    self.overlay.log_updated.emit(f"[WARN] {msg}")
            def error(self, msg):
                if hasattr(self.overlay, 'log_updated'):
                    self.overlay.log_updated.emit(f"[ERR] {msg}")
        
        def _worker():
            import yt_dlp
            from PySide6.QtCore import QTimer
            import tempfile
            import os
            import time
            import glob
            
            from PySide6.QtCore import QSettings
            settings = QSettings("TDD131", "HELXAID")
            saved_browser = settings.value("UniversalDownloader/browser_cookies", "None", type=str)
            
            target_query = prepare_ytdlp_target(url)
            
            # --- Mode == "direct" (Direct Fast Stream Resolution via Native C++ / yt-dlp) ---
            if mode == "direct":
                try:
                    from fast_stream_resolver import resolve_stream
                    logger = YtLogger(self.stream_loading) if hasattr(self, 'stream_loading') else None
                    if hasattr(self, 'stream_loading'):
                        if hasattr(self.stream_loading, 'log_msg'):
                            self.stream_loading.log_msg(f"[Engine] Resolving via Fast-Path Engine: {target_query}")
                        elif hasattr(self.stream_loading, 'log_updated'):
                            self.stream_loading.log_updated.emit(f"[Engine] Resolving via Fast-Path Engine: {target_query}")
                        
                    res = resolve_stream(target_query, logger=logger)
                    
                    if res.get('success') and res.get('stream_url'):
                        stream_url = res['stream_url']
                        title = res.get('title', 'Unknown Stream')
                        artist = res.get('artist', 'Unknown Artist')
                        duration = res.get('duration', 0)
                        webpage_url = res.get('original_url') or url
                        
                        track = {
                            'path': stream_url,
                            'title': title,
                            'artist': artist,
                            'duration': duration,
                            'date_added': "Direct Stream",
                            'is_stream': True,
                            'is_online': True,
                            'original_url': webpage_url,
                            'stream_url': stream_url
                        }
                        def _update_ui_direct():
                            if hasattr(self, 'stream_loading'):
                                self.stream_loading.finish_and_close_with_countdown()
                            self._append_tracks_to_playlist([track], group_name="Online Streams")
                            if hasattr(self, '_playlist') and self._playlist:
                                target_idx = len(self._playlist) - 1
                                self._play_track(target_idx)
                            self.schedule_ram_trim(1500)
                        QTimer.singleShot(0, self, _update_ui_direct)
                    else:
                        err_msg = res.get('error', 'Failed to extract direct stream URL.')
                        def _err_direct():
                            if hasattr(self, 'stream_loading'):
                                self.stream_loading.hide()
                            from PySide6.QtWidgets import QMessageBox
                            QMessageBox.warning(self, "Stream Error", f"Could not resolve direct stream:\n{err_msg}")
                        QTimer.singleShot(0, self, _err_direct)
                except Exception as e:
                    print(f"[Stream] Error resolving direct URL: {e}")
                    def _err_ex_direct():
                        if hasattr(self, 'stream_loading'):
                            self.stream_loading.hide()
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Stream Error", f"Could not resolve direct stream:\n{e}")
                    QTimer.singleShot(0, self, _err_ex_direct)
                return

            # --- Mode == "buffer" (Download to Temp Buffer) ---
            temp_dir = os.path.join(tempfile.gettempdir(), 'HELXAID_Streams')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Clean up streams older than 1 day
            try:
                now = time.time()
                for f in glob.glob(os.path.join(temp_dir, '*')):
                    if now - os.path.getmtime(f) > 86400:
                        os.remove(f)
            except Exception:
                pass
            
            ffmpeg_location = None
            try:
                appdata = os.environ.get('APPDATA', '')
                helxaid_ffmpeg_bin = os.path.join(appdata, 'HELXAID', 'tools', 'ffmpeg', 'bin')
                if os.path.isdir(helxaid_ffmpeg_bin):
                    ffmpeg_location = helxaid_ffmpeg_bin
            except Exception:
                ffmpeg_location = None

            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'nocheckcertificate': True,
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'retries': 10,
                'fragment_retries': 10,
                'default_search': 'ytsearch',
                'extractor_args': {'youtube': {'player_client': ['android', 'mweb', 'web', 'ios']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
            }

            if ffmpeg_location:
                ydl_opts['ffmpeg_location'] = ffmpeg_location
            
            if hasattr(self, 'stream_loading'):
                ydl_opts['logger'] = YtLogger(self.stream_loading)
                
            if saved_browser.lower() != 'none':
                ydl_opts['cookiesfrombrowser'] = (saved_browser.lower(),)
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target_query, download=True)
                    
                    if 'entries' in info:
                        info = info['entries'][0]
                        
                    local_path = ydl.prepare_filename(info)
                    title = info.get('title', 'Unknown Stream')
                    artist = info.get('uploader', 'Unknown Artist')
                    duration = info.get('duration', 0)
                    webpage_url = info.get('webpage_url') or (f"https://www.youtube.com/watch?v={info.get('id')}" if info.get('id') else url)
                    
                    if os.path.exists(local_path):
                        track = {
                            'path': local_path,
                            'title': title,
                            'artist': artist,
                            'duration': duration,
                            'date_added': "Online Stream",
                            'is_stream': True,
                            'is_online': False,  # Play natively as local file
                            'original_url': webpage_url
                        }
                        
                        def _update_ui():
                            if hasattr(self, 'stream_loading'):
                                self.stream_loading.finish_and_close_with_countdown()
                            self._append_tracks_to_playlist([track], group_name="Online Streams")
                            if hasattr(self, '_playlist') and self._playlist:
                                target_idx = len(self._playlist) - 1
                                self._play_track(target_idx)
                            self.schedule_ram_trim(1500)
                            
                        QTimer.singleShot(0, self, _update_ui)
                    else:
                        def _err_no_url():
                            if hasattr(self, 'stream_loading'):
                                self.stream_loading.hide()
                            from PySide6.QtWidgets import QMessageBox
                            QMessageBox.warning(self, "Stream Error", "Failed to download stream.")
                        QTimer.singleShot(0, self, _err_no_url)
            except Exception as e:
                print(f"[Stream] Error extracting URL: {e}")
                def _err_ex():
                    if hasattr(self, 'stream_loading'):
                        self.stream_loading.hide()
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "Stream Error", f"Could not process URL:\n{e}")
                QTimer.singleShot(0, self, _err_ex)
                
        threading.Thread(target=_worker, daemon=True).start()

    def _open_clipboard_direct(self):
        """Open a file or folder from clipboard."""
        from PySide6.QtGui import QClipboard
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        import os
        import datetime
        
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        raw_text = clipboard.text()
        print(f"[Clipboard] Raw text: {repr(raw_text)}")
        
        # Check if it's a URL
        if raw_text.strip().startswith("http://") or raw_text.strip().startswith("https://"):
            if "spotify.com" in raw_text.lower():
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Spotify DRM Restricted", "Spotify links cannot be downloaded due to strict DRM encryption.\n\nPRO TIP: Open the Stream URL box and type the Media Name to search and download it instead!")
                return
            self._process_url_stream_async(raw_text.strip())
            return
            
        print(f"[Clipboard] Has URLs: {mime_data.hasUrls()}")
        
        path = raw_text.strip().strip('"').strip("'")
        
        if not path and mime_data.hasUrls():
            urls = mime_data.urls()
            print(f"[Clipboard] URLs found: {urls}")
            if urls and urls[0].isLocalFile():
                path = urls[0].toLocalFile()
                
        print(f"[Clipboard] Final parsed path: {repr(path)}")
        print(f"[Clipboard] Path exists? {os.path.exists(path) if path else False}")
                
        if not path or not os.path.exists(path):
            print("[Clipboard] Invalid path or does not exist. Aborting.")
            return
            
        # Check if user is currently on Media Library tab (index 1)
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1 and hasattr(self, 'media_lib_page') and self.media_lib_page:
            if os.path.isdir(path):
                self.media_lib_page.add_path_to_library(path, is_folder=True)
                return
            elif os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
                if ext in audio_exts:
                    self.media_lib_page.add_path_to_library(path, is_folder=False)
                return
            
        if os.path.isdir(path):
            audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
            folder_name = os.path.basename(path)
            folder_tracks = []
            
            for root, dirs, files in os.walk(path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in audio_exts:
                        fpath = os.path.join(root, f)
                        title = os.path.splitext(f)[0]
                        try:
                            mtime = os.path.getmtime(fpath)
                            dt = datetime.datetime.fromtimestamp(mtime)
                            date_str = dt.strftime("%b %d, %Y")
                        except Exception:
                            date_str = ""
                            
                        folder_tracks.append({
                            'path': fpath,
                            'title': title,
                            'artist': '',
                            'duration': 0,
                            'date_added': date_str
                        })
            
            if folder_tracks:
                self._append_tracks_to_playlist(folder_tracks, group_name=folder_name)
                self._fetch_metadata_async(self._playlist, folder_name)
                
            QTimer.singleShot(500, self._save_state)
        elif os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
            if ext in audio_exts:
                title = os.path.splitext(os.path.basename(path))[0]
                try:
                    mtime = os.path.getmtime(path)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    date_str = dt.strftime("%b %d, %Y")
                except Exception:
                    date_str = ""
                    
                track = {
                    'path': path,
                    'title': title,
                    'artist': 'Single Track',
                    'duration': 0,
                    'date_added': date_str
                }
                
                self._append_tracks_to_playlist([track])
                self._fetch_metadata_async(self._playlist, "Single File")

    def _open_file_direct(self):
        """Pick a single media file and play it or add to Media Library."""
        from PySide6.QtWidgets import QFileDialog
        import datetime
        
        # Check if user is currently on Media Library tab (index 1)
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1 and hasattr(self, 'media_lib_page') and self.media_lib_page:
            self.media_lib_page._add_single_file()
            return
        
        audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        dialog_filters = "Media Files (" + " ".join(["*" + e for e in (audio_exts)]) + ");;All Files (*.*)"
        dialog = QFileDialog(self, "Open Media File", getattr(self, '_music_folder', None) or "")
        dialog.setNameFilter(dialog_filters)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setOption(QFileDialog.ShowDirsOnly, False)
        path = dialog.selectedFiles()[0] if dialog.exec() else ""
        
        if path:
            ext = os.path.splitext(path)[1].lower()
            title = os.path.splitext(os.path.basename(path))[0]
            
            # Create a track dictionary
            try:
                mtime = os.path.getmtime(path)
                dt = datetime.datetime.fromtimestamp(mtime)
                date_str = dt.strftime("%b %d, %Y")
            except Exception:
                date_str = ""
            
            track = {
                'path': path,
                'title': os.path.splitext(os.path.basename(path))[0],
                'artist': 'Single Track',
                'duration': 0,
                'date_added': date_str
            }
            
            self._append_tracks_to_playlist([track])
            self._fetch_metadata_async(self._playlist, "Single File")
            
            # Save state so the track is remembered in session
            QTimer.singleShot(500, self._save_state)
    def _open_settings(self):
        """Open settings dialog for folder selection."""
        from PySide6.QtWidgets import QFileDialog, QDialog, QVBoxLayout, QLabel, QPushButton
        
        # Create simple settings popup
        dialog = QDialog(self)
        dialog.setWindowTitle("Music Settings")
        dialog.setFixedSize(450, 200)
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a2e, stop:1 #16213e);
                border: 1px solid rgba(255, 91, 6, 0.3);
                border-radius: 12px;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
            }
            QPushButton#doneBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border: none;
                font-weight: bold;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Title
        title = QLabel("Music Folder")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Current folder
        current = getattr(self, '_music_folder', None) or "No folder selected"
        self._folder_label = QLabel(current)
        self._folder_label.setStyleSheet("color: #888; font-size: 12px;")
        self._folder_label.setWordWrap(True)
        layout.addWidget(self._folder_label)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_and_load(dialog))
        btn_row.addWidget(browse_btn)
        
        btn_row.addStretch()
        
        done_btn = QPushButton("Done")
        done_btn.setObjectName("doneBtn")
        done_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(done_btn)
        
        layout.addStretch()
        layout.addLayout(btn_row)
        
        dialog.exec()
    
    def _browse_and_load(self, dialog):
        """Browse for folder and load tracks."""
        from PySide6.QtWidgets import QFileDialog
        
        start = getattr(self, '_music_folder', None) or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Media Folder", start, QFileDialog.ShowDirsOnly
        )
        
        if folder:
            self._music_folder = folder
            self._folder_label.setText(folder)
            self._load_tracks_from_folder(folder)
            # Save immediately so folder is remembered after restart
            QTimer.singleShot(500, self._save_state)
    

    def _fetch_metadata_async(self, target_tracks, target_name):
        import subprocess
        import shutil
        import threading
        from PySide6.QtCore import QTimer
        import os
        
        print(f"[Duration] Starting metadata fetch for {len(target_tracks)} tracks")
        
        def _fetch_worker():
            # Try to import mutagen for fast metadata reading (works for audio files)
            try:
                import mutagen
                has_mutagen = True
            except ImportError:
                has_mutagen = False
            
            # Find ffprobe path for fallback
            ffprobe_path = shutil.which("ffprobe")
            if not ffprobe_path:
                appdata_tools = os.path.join(os.environ.get("APPDATA", ""), "HELXAID", "tools")
                if os.path.exists(appdata_tools):
                    possible_paths = [
                        os.path.join(appdata_tools, "ffmpeg", "bin", "ffprobe.exe"),
                        os.path.join(appdata_tools, "ffmpeg", "ffprobe.exe"),
                        os.path.join(appdata_tools, "ffprobe.exe")
                    ]
                    for p in possible_paths:
                        if os.path.exists(p):
                            ffprobe_path = p
                            break
                    if not ffprobe_path:
                        for root, dirs, fnames in os.walk(appdata_tools):
                            for fn in fnames:
                                if fn.lower() == "ffprobe.exe":
                                    ffprobe_path = os.path.join(root, fn)
                                    break
                            if ffprobe_path: break
            
            changed = False
            success_count = 0
            fail_count = 0
            
            for t in target_tracks:
                # Stop parsing if playlist was changed/switched
                if getattr(self, '_playlist', None) is not target_tracks:
                    break
                    
                path = t.get('path', '')
                if not os.path.exists(path):
                    continue
                
                # Only fetch if duration is 0
                if t.get('duration', 0) > 0:
                    continue
                
                dur = 0
                artist = ''
                
                if has_mutagen:
                    try:
                        m = mutagen.File(path)
                        if m is not None and hasattr(m, 'info'):
                            dur = getattr(m.info, 'length', 0)
                            if hasattr(m, 'tags') and m.tags:
                                if 'artist' in m.tags:
                                    val = m.tags['artist']
                                    artist = str(val[0]) if isinstance(val, list) and len(val) > 0 else str(val)
                    except Exception:
                        pass
                
                if dur <= 0 and ffprobe_path:
                    try:
                        result = subprocess.run(
                            [ffprobe_path, "-v", "quiet", "-show_entries", "format=duration", 
                             "-of", "default=noprint_wrappers=1:nokey=1", path],
                            capture_output=True, text=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            dur = float(result.stdout.strip())
                    except Exception:
                        pass
                
                if dur > 0:
                    t['duration'] = dur
                    changed = True
                    success_count += 1
                else:
                    fail_count += 1
                
                if artist and not t.get('artist') and t.get('artist') != 'Dropped File':
                    t['artist'] = artist
                elif artist and t.get('artist') == 'Dropped File':
                    t['artist'] = artist
                
                # Incremental UI update every 5 tracks
                if (success_count + fail_count) % 5 == 0 and changed:
                    print(f"[Duration] Incremental UI update triggered for {success_count+fail_count} tracks")
                    _snap = list(target_tracks)
                    _n = target_name
                    def _incr(_s=_snap, _nm=_n):
                        if getattr(self, '_playlist', None) is not target_tracks:
                            return
                        if hasattr(self, 'table') and hasattr(self.table, '_render_tracks'):
                            self.table._render_tracks()
                        if hasattr(self, 'header') and hasattr(self.header, 'set_info'):
                            self.header.set_info(_nm, len(target_tracks), self._format_playlist_duration())
                    QTimer.singleShot(0, self, _incr)
            
            print(f"[Duration] Fetch loop complete. changed={changed}, success={success_count}, fail={fail_count}")
            # Final update
            if changed and getattr(self, '_playlist', None) is target_tracks:
                print(f"[Duration] Scheduling final update_ui")
                def update_ui():
                    print(f"[Duration] Running update_ui on main thread")
                    if getattr(self, '_playlist', None) is not target_tracks:
                        print(f"[Duration] update_ui aborted: playlist changed")
                        return
                    if hasattr(self, 'header') and hasattr(self.header, 'set_info'):
                        self.header.set_info(target_name, len(target_tracks), self._format_playlist_duration())
                    if hasattr(self, 'table') and hasattr(self.table, '_render_tracks'):
                        self.table._render_tracks()
                        print(f"[Duration] update_ui table._render_tracks() called")
                QTimer.singleShot(0, self, update_ui)
            else:
                print(f"[Duration] Final update_ui NOT scheduled. changed={changed}")
                
        t = threading.Thread(target=_fetch_worker, daemon=True)
        t.start()

    def _on_tracks_dropped(self, paths):
        """Fallback handler for native Windows OLE drops routed from launcher.py."""
        if not paths:
            return
        if hasattr(self, 'stack') and self.stack.currentIndex() == 1 and hasattr(self, 'media_lib_page') and self.media_lib_page:
            self.media_lib_page._process_dropped_paths(paths)
            return
        # Otherwise handle for playlist
        audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        if not hasattr(self, '_playlist'):
            self._playlist = []
        tracks_to_add = []
        import datetime
        for path in paths:
            if os.path.isdir(path):
                folder_name = os.path.basename(path) or path
                try:
                    for entry in os.scandir(path):
                        if entry.is_file() and os.path.splitext(entry.name)[1].lower() in audio_exts:
                            title = os.path.splitext(entry.name)[0]
                            try:
                                mtime = entry.stat().st_mtime
                                dt = datetime.datetime.fromtimestamp(mtime)
                                date_str = dt.strftime("%b %d, %Y")
                            except Exception:
                                date_str = ""
                            tracks_to_add.append({
                                'path': entry.path,
                                'title': title,
                                'artist': 'Dropped File',
                                'duration': 0,
                                'date_added': date_str,
                                'playlist_group': folder_name
                            })
                except Exception:
                    pass
            elif os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext in audio_exts:
                    title = os.path.splitext(os.path.basename(path))[0]
                    try:
                        mtime = os.path.getmtime(path)
                        dt = datetime.datetime.fromtimestamp(mtime)
                        date_str = dt.strftime("%b %d, %Y")
                    except Exception:
                        date_str = ""
                    tracks_to_add.append({
                        'path': path,
                        'title': title,
                        'artist': 'Dropped File',
                        'duration': 0,
                        'date_added': date_str
                    })
        if tracks_to_add:
            self._append_tracks_to_playlist(tracks_to_add)
            self._fetch_metadata_async(self._playlist, "Dropped Media")

    def _load_tracks_from_folder(self, folder: str):
        """Scan folder and load tracks."""
        # Use Python fallback scanner - C++ has encoding issues with special characters
        self._load_tracks_fallback(folder)
    
    def _load_tracks_fallback(self, folder: str):
        """Fallback track loading without C++ extension."""
        import datetime
        import subprocess
        
        audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        tracks = []
        try:
            for entry in os.scandir(folder):
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in audio_exts:
                        path = entry.path
                        title = os.path.splitext(entry.name)[0]
                        
                        # Get file modified time as date added
                        try:
                            mtime = entry.stat().st_mtime
                            dt = datetime.datetime.fromtimestamp(mtime)
                            date_str = dt.strftime("%b %d, %Y")
                        except Exception:
                            date_str = ""
                        
                        # Lazy loading for duration
                        duration = 0
                        
                        tracks.append({
                            'path': path,
                            'title': title,
                            'artist': '',
                            'duration': duration,
                            'date_added': date_str
                        })
        except Exception as e:
            print(f"[Music] Error scanning folder {folder}: {e}")
        
        playlist_name = os.path.basename(folder) + "'s Playlist"
        self.set_playlist(playlist_name, tracks)
        print(f"Loaded {len(tracks)} tracks from {folder} (fallback)")
        
        # Async metadata loading to prevent UI freeze
        self._fetch_metadata_async(tracks, playlist_name)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Load Orbitron font if available
    script_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(script_dir, "fonts", "Orbitron-Bold.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)
    
    panel = MusicPanelWidget()
    panel.resize(900, 650)
    panel.setWindowTitle("Music Panel - Qt Native")
    panel.show()
    
    # Panel loads last state automatically via _load_last_state()
    # If no state, user can click folder button to Select Media Folder
    
    sys.exit(app.exec())
