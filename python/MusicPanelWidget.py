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
    QDialog, QComboBox, QRadioButton, QButtonGroup,
    QProgressBar, QGroupBox, QSplitter, QApplication
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, QPoint, QUrl, QThread, QSettings
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPalette, QCursor,
    QFontDatabase
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from VideoPlayerWidget import VideoPlayerWidget

import os
import sys
import json
import subprocess
import tempfile
import urllib.request
import hashlib
from typing import Optional
from functools import partial


class ClickSlider(QSlider):
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


# ---- YouTube Downloader Classes ----

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

    def __init__(self, url, out_dir, fmt, quality_idx):
        super().__init__()
        self.url = url
        self.out_dir = out_dir
        self.fmt = fmt
        self.quality_idx = quality_idx
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
        """Execute the download in a shell via yt-dlp module."""
        import subprocess
        import os
        import sys
        
        try:
            import yt_dlp as _yt_dlp_mod
            main_py = os.path.join(os.path.dirname(_yt_dlp_mod.__file__), '__main__.py')
            
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
            
            # Build command line
            cmd = [
                sys.executable, main_py,
                '--newline',
                '--no-playlist',
                '--no-check-certificate',
                '--format', f_str,
                '--output', out_tmpl,
                '--progress-template', '"[download] %(progress._percent_str)s"',
                self.url
            ]

            if ffmpeg_location:
                cmd.extend(['--ffmpeg-location', ffmpeg_location])
            
            if self.fmt == 'audio':
                # Convert to mp3 and remove the original downloaded container
                # so the user only gets a single mp3 file.
                cmd.extend(['--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0', '--no-keep-video'])
            else:
                # Force a single merged output container when possible.
                cmd.extend(['--merge-output-format', 'mp4'])

            startupinfo = None
            if sys.platform == 'win32':
                from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
                startupinfo = STARTUPINFO()
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                
            self._proc = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                encoding='utf-8', 
                errors='replace',
                startupinfo=startupinfo
            )
            
            while not self._is_cancelled:
                line = self._proc.stdout.readline()
                if not line:
                    break
                
                clean_line = line.strip()
                if not clean_line:
                    continue
                
                self.status.emit(clean_line)
                
                # Parse progress percent
                if '[download]' in clean_line and '%' in clean_line:
                    try:
                        # Extract percentage (e.g., "[download] 12.5%")
                        parts = clean_line.split()
                        for p in parts:
                            if '%' in p:
                                val_str = p.replace('%', '').replace('"', '').strip()
                                val = float(val_str)
                                self.progress.emit(int(val))
                                break
                    except:
                        pass
            
            self._proc.wait()
            
            if self._is_cancelled:
                self.error.emit("Download cancelled by user.")
            elif self._proc.returncode == 0:
                self.finished.emit("Download successful!")
            else:
                err_msg = self._proc.stderr.read()
                self.error.emit(err_msg or f"yt-dlp exited with code {self._proc.returncode}")
                
        except Exception as e:
            self.error.emit(str(e))


class MetadataWorker(QThread):
    """
    Worker for fetching media metadata and estimating file size before download.
    
    Component Name: MetadataWorker
    """
    metadata = Signal(dict)
    error    = Signal(str)

    def __init__(self, url, fmt, quality_idx):
        super().__init__()
        self.url = url
        self.fmt = fmt
        self.quality_idx = quality_idx
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        import subprocess
        import os
        import sys
        
        if self._is_cancelled: return

        try:
            import yt_dlp as _yt_dlp_mod
            main_py = os.path.join(os.path.dirname(_yt_dlp_mod.__file__), '__main__.py')
            
            dw = DownloadWorker(self.url, "", self.fmt, self.quality_idx)
            f_str = dw.get_f_str()
            
            # Request Title, Thumbnail URL, and Size
            cmd = [
                sys.executable, main_py,
                '--simulate',
                '--no-playlist',
                '--no-check-certificate',
                '--quiet',
                '--no-warnings',
                '--format', f_str,
                '--print', 'title',
                '--print', 'thumbnail',
                '--print', 'filesize,filesize_approx',
                self.url
            ]
            
            startupinfo = None
            if sys.platform == 'win32':
                from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
                startupinfo = STARTUPINFO()
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
            
            if self._is_cancelled: return

            if res.returncode == 0:
                lines = [l.strip() for l in res.stdout.strip().split('\n') if l.strip()]
                
                title = lines[0] if len(lines) > 0 else "Unknown Title"
                thumb_url = lines[1] if len(lines) > 1 else None
                size_raw = lines[2] if len(lines) > 2 and lines[2] != 'NA' else "Unknown"
                
                if size_raw != "Unknown":
                    try:
                        val = int(size_raw)
                        for unit in ['B','KB','MB','GB']:
                            if val < 1024:
                                size_raw = f"{val:.1f} {unit}"
                                break
                            val /= 1024
                    except: pass
                
                if not self._is_cancelled:
                    self.metadata.emit({
                        'title': title,
                        'thumb_url': thumb_url,
                        'size': size_raw
                    })
            else:
                if not self._is_cancelled:
                    self.error.emit("Failed to fetch meta.")
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
        try:
            data = urllib.request.urlopen(self.url, timeout=10).read()
            if data: self.loaded.emit(data)
        except: pass


class YouTubeDownloaderPanel(QFrame):
    """
    Integrated YouTube downloader panel that replaces the floating dialog.
    Matches the sleek dark design of HELXAID.
    
    Component Name: YouTubeDownloaderPanel
    """
    downloadFinished = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ytDownloaderPanel")
        self._worker = None
        self._size_worker = None
        self._img_worker = None
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
            # We intentionally avoid QThread.terminate() here because forcibly
            # killing threads can crash the Python/Qt runtime, especially while
            # running subprocesses (yt-dlp) for size estimation or downloads.
            try:
                if hasattr(worker, 'cancel'):
                    worker.cancel()
            except Exception:
                pass

    def closeEvent(self, event):
        """Ensure all threads are killed when panel closes."""
        self._cleanup_worker('_worker')
        self._cleanup_worker('_size_worker')
        self._cleanup_worker('_img_worker')
        for w in self._thread_graveyard:
            try: w.terminate()
            except: pass
        super().closeEvent(event)

    def _setup_ui(self):
        # Master layout for the panel frame
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(0)

        # Content in a Scroll Area for small windowed mode
        from smooth_scroll import SmoothScrollArea
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ytScrollContent")
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(15, 20, 15, 15)
        layout.setSpacing(15)

        # Header with close button
        header_row = QHBoxLayout()
        title = QLabel("YouTube Downloader")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #FF5B06;")
        header_row.addWidget(title)
        
        header_row.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 20px; font-weight: bold; }
            QPushButton:hover { color: #FF5B06; }
        """)
        close_btn.clicked.connect(self.closeRequested.emit)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)

        # URL input
        url_lbl = QLabel("Paste URL:")
        url_lbl.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        layout.addWidget(url_lbl)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/...")
        layout.addWidget(self.url_edit)

        # ---- Preview Section (Thumbnail + Title) ----
        self.preview_section = QFrame()
        self.preview_section.setObjectName("ytPreviewSection")
        self.preview_section.setStyleSheet("""
            QFrame#ytPreviewSection {
                background: rgba(0,0,0,0.2);
                border: 1px solid rgba(255, 91, 6, 0.1);
                border-radius: 8px;
            }
        """)
        self.preview_section.hide()
        
        preview_layout = QVBoxLayout(self.preview_section)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(8)

        # Image Container
        self.thumb_container = QFrame()
        self.thumb_container.setFixedSize(270, 152) # 16:9 balanced for 320px panel
        self.thumb_container.setStyleSheet("background: rgba(0,0,0,0.4); border-radius: 4px;")
        
        thumb_inner_layout = QVBoxLayout(self.thumb_container)
        thumb_inner_layout.setContentsMargins(0,0,0,0)
        
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        thumb_inner_layout.addWidget(self.thumb_lbl)
        preview_layout.addWidget(self.thumb_container, 0, Qt.AlignCenter)

        # Title below image
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet("color: #FF5B06; font-size: 11px; font-weight: bold;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.title_lbl)
        
        layout.addWidget(self.preview_section)

        # Format & Quality
        fmt_group = QGroupBox("Format & Quality")
        fmt_layout = QVBoxLayout(fmt_group)
        
        self.rb_audio = QRadioButton("Audio (MP3)")
        self.rb_video = QRadioButton("Video (MP4)")
        self.rb_audio.setChecked(True)
        fmt_layout.addWidget(self.rb_audio)
        fmt_layout.addWidget(self.rb_video)
        
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("ytQualityCombo")

        # Ensure the dropdown popup is opaque. The popup is a separate top-level
        # view and may not reliably inherit the parent stylesheet.
        try:
            from PySide6.QtGui import QPalette, QColor
            view = self.quality_combo.view()
            view.setAutoFillBackground(True)
            pal = view.palette()
            pal.setColor(QPalette.Base, QColor(15, 15, 25))
            pal.setColor(QPalette.Text, QColor(224, 224, 224))
            view.setPalette(pal)
            view.setStyleSheet("""
                QAbstractItemView {
                    background-color: rgba(15, 15, 25, 0.98);
                    border: 1px solid rgba(255,255,255,0.12);
                    color: #e0e0e0;
                    selection-background-color: rgba(255, 91, 6, 0.35);
                    selection-color: #ffffff;
                    outline: 0;
                }
                QAbstractItemView::item {
                    padding: 6px 8px;
                    background: transparent;
                }
                QAbstractItemView::item:hover {
                    background: rgba(255, 91, 6, 0.22);
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
        
        fmt_layout.addWidget(QLabel("Quality:"))
        fmt_layout.addWidget(self.quality_combo)
        fmt_layout.addWidget(self.size_lbl)
        layout.addWidget(fmt_group)

        # Output Folder
        folder_group = QGroupBox("Save to")
        folder_layout = QHBoxLayout(folder_group)
        
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        settings = QSettings("TDD131", "HELXAID")
        last_dir = settings.value("YouTubeDownloader/last_output_dir", "", type=str)
        default_path = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
        self.folder_edit.setText(last_dir or default_path)
        
        browse_btn = QPushButton("...")
        browse_btn.setFixedSize(30, 26)
        browse_btn.setStyleSheet("background: rgba(255,255,255,0.1); font-weight: normal;")
        
        def pick_folder():
            from PySide6.QtWidgets import QFileDialog
            start_dir = self.folder_edit.text().strip() or default_path
            d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
            if d:
                self.folder_edit.setText(d)
                settings.setValue("YouTubeDownloader/last_output_dir", d)
        
        browse_btn.clicked.connect(pick_folder)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_group)

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

        # Action Button
        self.download_btn = QPushButton("Start Download")
        self.download_btn.setObjectName("ytPanelDownloadBtn")
        self.download_btn.setFixedHeight(40)
        self.download_btn.setStyleSheet("""
            QPushButton#ytPanelDownloadBtn {
                background-color: #FF5B06;
                color: #ffffff;
                border: 1px solid rgba(255, 91, 6, 0.55);
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#ytPanelDownloadBtn:hover { background-color: #FF7B26; }
            QPushButton#ytPanelDownloadBtn:pressed { background-color: #E94F00; }
            QPushButton#ytPanelDownloadBtn:focus { outline: 0; }
            QPushButton#ytPanelDownloadBtn:disabled { background-color: #333; color: #666; border-color: rgba(255,255,255,0.08); }
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
                background: rgba(15, 15, 25, 0.95);
                border-left: 1px solid rgba(255, 91, 6, 0.2);
            }
            QLabel { color: #e0e0e0; background: transparent; }
            QLineEdit {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; padding: 6px; color: #fff; font-size: 12px;
            }
            QLineEdit:focus { border-color: #FF5B06; }
            QGroupBox {
                border: 1px solid rgba(255, 91, 6, 0.1);
                border-radius: 6px; margin-top: 15px; padding-top: 15px;
                color: #888; font-size: 11px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #FF5B06; }
            QComboBox {
                background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; padding: 4px; color: #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background: rgba(15, 15, 25, 0.98);
                border: 1px solid rgba(255,255,255,0.12);
                selection-background-color: rgba(255, 91, 6, 0.35);
                selection-color: #ffffff;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 8px;
                background: transparent;
                color: #e0e0e0;
            }
            QComboBox QAbstractItemView::item:hover {
                background: rgba(255, 91, 6, 0.22);
                color: #ffffff;
            }
            QRadioButton { color: #ccc; font-size: 12px; }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid rgba(255,255,255,0.35);
                background: rgba(0,0,0,0.25);
            }
            QRadioButton::indicator:hover {
                border-color: rgba(255, 91, 6, 0.85);
            }
            QRadioButton::indicator:checked {
                border-color: rgba(255, 91, 6, 0.95);
                background: #FF5B06;
            }
            QProgressBar {
                border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;
                background: rgba(0,0,0,0.4); text-align: center; color: #fff; height: 16px;
            }
            QProgressBar::chunk { background: #FF5B06; border-radius: 3px; }
            QPushButton#ytPanelDownloadBtn {
                background-color: #FF5B06;
                color: #ffffff;
                border: 1px solid rgba(255, 91, 6, 0.55);
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#ytPanelDownloadBtn:hover { background-color: #FF7B26; }
            QPushButton#ytPanelDownloadBtn:pressed { background-color: #E94F00; }
            QPushButton#ytPanelDownloadBtn:focus { outline: 0; }
            QPushButton#ytPanelDownloadBtn:disabled { background-color: #333; color: #666; border-color: rgba(255,255,255,0.08); }
        """)

    def _update_size_estimate(self):
        url = self.url_edit.text().strip()
        
        # Basic validation to avoid yt-dlp noise on random text
        # Must have at least one dot and look like a potential link
        if not url or len(url) < 8 or '.' not in url:
            self.size_lbl.setText("Ready")
            self.size_lbl.setStyleSheet("color: #888; font-size: 11px;")
            self.preview_section.hide()
            self.thumb_lbl.clear()
            self.title_lbl.clear()
            self._cleanup_worker('_size_worker')
            self._cleanup_worker('_img_worker')
            return

        self._cleanup_worker('_size_worker')
        self._cleanup_worker('_img_worker')
        
        # Clear UI for fresh fetch
        self.thumb_lbl.clear()
        self.title_lbl.setText("Resolving link...")
        self.size_lbl.setText("Fetching metadata...")

        fmt = 'audio' if self.rb_audio.isChecked() else 'video'
        worker = MetadataWorker(url, fmt, self.quality_combo.currentIndex())
        self._size_worker = worker
        
        def on_meta(d):
            # Guard: Check if this worker is still the active one
            if self._size_worker != worker:
                return
            
            try:
                self.size_lbl.setText(f"Est. Size: {d.get('size', 'Unknown')}")
                self.title_lbl.setText(d.get('title', ''))
                self.preview_section.show()
                
                # Fetch thumbnail if available
                thumb_url = d.get('thumb_url')
                if thumb_url:
                    self._cleanup_worker('_img_worker')
                    
                    img_worker = ImageLoader(thumb_url)
                    self._img_worker = img_worker
                    img_worker.loaded.connect(self._on_thumb_loaded)
                    img_worker.finished.connect(img_worker.deleteLater)
                    img_worker.start()
            except RuntimeError:
                pass

        worker.metadata.connect(on_meta)
        worker.error.connect(lambda _: self.size_lbl.setText("Meta: Failed"))
        worker.start()

    def _on_thumb_loaded(self, data):
        # Verify img_worker still exists (might have been cleaned up)
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled = pixmap.scaled(self.thumb_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_lbl.setPixmap(scaled)

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
        worker = DownloadWorker(url, out_dir, fmt, self.quality_combo.currentIndex())
        self._worker = worker
        worker.progress.connect(self.progress_bar.setValue)
        worker.status.connect(lambda s: self.status_lbl.setText(s[-100:]))
        
        def on_done(msg):
            self._reset_ui()
            self.downloadFinished.emit(msg)
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


class PlaylistHeader(QFrame):
    """
    Playlist header matching HTML5 design.
    
    Component Name: PlaylistHeader
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistHeader")
        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 20)
        layout.setSpacing(20)
        
        # Cover art stack
        cover_container = QWidget()
        cover_container.setFixedSize(120, 120)
        
        # Back cover (offset)
        self.cover_back = QLabel(cover_container)
        self.cover_back.setObjectName("coverBack")
        self.cover_back.setGeometry(15, 10, 90, 90)
        self.cover_back.setScaledContents(True)
        
        # Front cover
        self.cover_front = QLabel(cover_container)
        self.cover_front.setObjectName("coverFront")
        self.cover_front.setGeometry(0, 20, 100, 100)
        self.cover_front.setScaledContents(True)
        
        layout.addWidget(cover_container)
        
        # Playlist info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        
        self.playlist_label = QLabel("PLAYLIST")
        self.playlist_label.setObjectName("playlistLabel")
        
        self.playlist_title = QLabel("My Playlist")
        self.playlist_title.setObjectName("playlistTitle")
        
        self.playlist_stats = QLabel("0 songs · 0:00:00")
        self.playlist_stats.setObjectName("playlistStats")
        
        info_layout.addStretch()
        info_layout.addWidget(self.playlist_label)
        info_layout.addWidget(self.playlist_title)
        info_layout.addWidget(self.playlist_stats)
        info_layout.addStretch()
        
        layout.addLayout(info_layout, stretch=1)
        
        # No settings button here - moved to menu bar
    
    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#playlistHeader {
                background: transparent;
            }
            
            QLabel#coverBack {
                background: #2a2a3a;
                border-radius: 10px;
            }
            
            QLabel#coverFront {
                background: #3a3a4a;
                border-radius: 10px;
                border: 2px solid rgba(255, 91, 6, 0.4);
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
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
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
        self.playlist_title.setText(name)
        self.playlist_stats.setText(f"{track_count} songs · {total_duration}")
    
    def set_covers(self, cover1_path: str, cover2_path: str):
        if cover1_path and os.path.exists(cover1_path):
            pixmap = QPixmap(cover1_path)
            self.cover_back.setPixmap(pixmap)
        
        if cover2_path and os.path.exists(cover2_path):
            pixmap = QPixmap(cover2_path)
            self.cover_front.setPixmap(pixmap)


class PlaylistTable(QWidget):
    """
    Playlist table using QTableWidget like Basic Services tab.
    
    Component Name: PlaylistTable
    """
    
    trackDoubleClicked = Signal(int)
    sortChanged = Signal(str, bool)  # column, ascending
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistTableContainer")
        self._tracks = []
        self._current_index = -1
        self._sort_column = "title"
        self._sort_ascending = True
        self._sorted_indices = []  # Stores sorted order of original indices
        self._setup_ui()
    
    def _setup_ui(self):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        from smooth_scroll import SmoothTableWidget
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create table
        self.table = QTableWidget()
        self.table.setObjectName("playlistTable")
        self.table.setColumnCount(4)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)  # We handle sorting manually
        self.table.setFocusPolicy(Qt.NoFocus)
        
        # Set header labels
        self.table.setHorizontalHeaderLabels(["#", "Title", "Date Added", "Duration"])
        
        # Column widths & resize behavior (adaptive to table size)
        self.table.setColumnWidth(0, 50)    # Index
        self.table.setColumnWidth(2, 160)   # Date Added
        self.table.setColumnWidth(3, 80)    # Duration
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)           # Index stays narrow
        header.setSectionResizeMode(1, QHeaderView.Stretch)         # Title takes remaining space
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)# Date adapts to content
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)# Duration adapts to content
        header.setMinimumSectionSize(50)
        
        # Header click for sorting
        header.sectionClicked.connect(self._on_header_click)
        
        # Row height
        self.table.verticalHeader().setDefaultSectionSize(45)
        
        # Single click to play
        self.table.cellClicked.connect(self._on_double_click)
        
        # Styling
        self._apply_style()
        
        layout.addWidget(self.table)
        
        # Enable smooth scrolling
        self._table_smoother = SmoothTableWidget(self.table)
    
    def _apply_style(self):
        self.table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                background-color: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }
            QTableWidget QTableCornerButton::section {
                background: transparent;
                border: none;
            }
            QTableWidget QHeaderView {
                background: transparent;
            }
            QTableWidget::viewport {
                background: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            QTableWidget::item:hover {
                background: rgba(255, 255, 255, 0.05);
            }
            QTableWidget::item:selected {
                background: rgba(255, 91, 6, 0.15);
            }
            QHeaderView::section {
                background: transparent;
                color: #888888;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                border-right: 1px solid rgba(255, 255, 255, 0.1);
                padding: 10px 8px;
                text-align: left;
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
        """Handle header click for sorting."""
        column_map = {0: None, 1: "title", 2: "date", 3: "length"}
        column = column_map.get(column_idx)
        
        if column is None:
            return  # # column not sortable
        
        if self._sort_column == column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        
        self._update_header_labels()
        self.sortChanged.emit(column, self._sort_ascending)
        self._render_tracks()
    
    def _update_header_labels(self):
        """Update header labels with sort indicators."""
        arrow = " ▲" if self._sort_ascending else " ▼"
        
        titles = ["#", "Title", "Date Added", "Duration"]
        for i, title in enumerate(titles):
            if i == 1 and self._sort_column == "title":
                self.table.setHorizontalHeaderItem(i, QTableWidgetItem(title + arrow))
            elif i == 2 and self._sort_column == "date":
                self.table.setHorizontalHeaderItem(i, QTableWidgetItem(title + arrow))
            elif i == 3 and self._sort_column == "length":
                self.table.setHorizontalHeaderItem(i, QTableWidgetItem(title + arrow))
            else:
                self.table.setHorizontalHeaderItem(i, QTableWidgetItem(title))
    
    def _on_double_click(self, row: int, column: int):
        """Handle double click to play track."""
        # Get original index from row data
        item = self.table.item(row, 0)
        if item:
            orig_idx = item.data(Qt.UserRole)
            if orig_idx is not None:
                self.trackDoubleClicked.emit(orig_idx)
    
    def set_tracks(self, tracks: list):
        self._tracks = tracks
        self._render_tracks()
    
    def _render_tracks(self):
        """Render tracks to table."""
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtGui import QColor
        
        self.table.setRowCount(0)
        
        # Sort tracks
        sorted_tracks = list(enumerate(self._tracks))
        
        # Natural sort key for titles (handles numbers correctly)
        import re
        def natural_sort_key(text):
            """Convert text to natural sort key - numbers are sorted numerically."""
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
        
        # Store sorted order for next/prev navigation
        self._sorted_indices = [orig_idx for orig_idx, track in sorted_tracks]
        
        self.table.setRowCount(len(sorted_tracks))
        
        for display_idx, (orig_idx, track) in enumerate(sorted_tracks):
            is_playing = orig_idx == self._current_index
            
            # Column 0: # (or ▶ if playing)
            num_text = ">" if is_playing else str(display_idx + 1)
            num_item = QTableWidgetItem(num_text)
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setData(Qt.UserRole, orig_idx)  # Store original index
            if is_playing:
                num_item.setForeground(QColor("#FF5B06"))
            else:
                num_item.setForeground(QColor("#888888"))
            self.table.setItem(display_idx, 0, num_item)
            
            # Column 1: Title
            title = track.get('title', 'Unknown')
            title_item = QTableWidgetItem(title)
            title_item.setForeground(QColor("#e0e0e0"))
            title_item.setToolTip(title)
            self.table.setItem(display_idx, 1, title_item)
            
            # Column 2: Date Added
            date_item = QTableWidgetItem(track.get('date_added', ''))
            date_item.setForeground(QColor("#888888"))
            date_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(display_idx, 2, date_item)
            
            # Column 3: Duration
            duration = track.get('duration', 0)
            mins = int(duration // 60)
            secs = int(duration % 60)
            length_item = QTableWidgetItem(f"{mins}:{secs:02d}")
            length_item.setForeground(QColor("#888888"))
            length_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(display_idx, 3, length_item)
            
            # Highlight playing row
            if is_playing:
                for col in range(4):
                    item = self.table.item(display_idx, col)
                    if item:
                        item.setBackground(QColor(255, 91, 6, 38))  # ~15% opacity
    
    def highlight_playing(self, index: int):
        self._current_index = index
        self._render_tracks()
    
    def get_next_index(self, current_index: int) -> int:
        """Get the next track index based on sorted order."""
        if not self._sorted_indices:
            return (current_index + 1) % len(self._tracks) if self._tracks else -1
        
        try:
            pos = self._sorted_indices.index(current_index)
            next_pos = (pos + 1) % len(self._sorted_indices)
            return self._sorted_indices[next_pos]
        except ValueError:
            return self._sorted_indices[0] if self._sorted_indices else -1
    
    def get_prev_index(self, current_index: int) -> int:
        """Get the previous track index based on sorted order."""
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
    videoToggled = Signal()
    folderClicked = Signal()  # For music folder selection
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerBar")
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
        
        # Video toggle button with cover
        self.video_btn = QPushButton()
        self.video_btn.setObjectName("playerCoverBtn")
        self.video_btn.setFixedSize(50, 50)
        self.video_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.video_btn.clicked.connect(self.videoToggled.emit)
        self.video_btn.setToolTip("Switch Video/Audio")
        
        icon_path = os.path.join(icons_dir, "music-video-switch.png")
        if os.path.exists(icon_path):
            self.video_btn.setIcon(QIcon(icon_path))
            self.video_btn.setIconSize(QSize(30, 30))
        
        track_section.addWidget(self.video_btn)
        
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
        
        self.timeline = ClickSlider(Qt.Horizontal)
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
        
        # === Folder Button (before volume) ===
        folder_layout = QHBoxLayout()
        folder_layout.setAlignment(Qt.AlignVCenter)
        
        self.folder_btn = QPushButton()
        self.folder_btn.setObjectName("folderBtn")
        self.folder_btn.setFixedSize(48, 48)  # Match other buttons
        self.folder_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.folder_btn.setToolTip("Select Media Folder")
        self.folder_btn.clicked.connect(self.folderClicked.emit)
        
        folder_icon_path = os.path.join(icons_dir, "folder-icon.png")
        if os.path.exists(folder_icon_path):
            self.folder_btn.setIcon(QIcon(folder_icon_path))
            self.folder_btn.setIconSize(QSize(18, 18))
        else:
            self.folder_btn.setText("📁")
        
        folder_layout.addWidget(self.folder_btn)
        layout.addLayout(folder_layout)
        
        # Small spacer between folder and volume
        layout.addSpacerItem(QSpacerItem(10, 0))
        
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
        
        self.volume_input = QSpinBox()
        self.volume_input.setObjectName("volumeInput")
        self.volume_input.setRange(0, 125)  # Allow volume boost up to 125%
        self.volume_input.setValue(100)
        self.volume_input.setFixedWidth(50)
        self.volume_input.setButtonSymbols(QSpinBox.NoButtons)
        self.volume_input.valueChanged.connect(self._on_volume_input_change)
        
        volume_layout.addWidget(self.volume_icon)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_input)
        
        layout.addLayout(volume_layout)
    
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
            
            QPushButton#playerCoverBtn {
                background: rgba(40, 40, 50, 0.9);
                border: 2px solid rgba(255, 91, 6, 0.4);
                border-radius: 8px;
            }
            QPushButton#playerCoverBtn:hover {
                border-color: #FF5B06;
                background: rgba(255, 91, 6, 0.15);
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
            
            QSlider#timelineSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.1);
                height: 4px;
                border-radius: 2px;
            }
            QSlider#timelineSlider::handle:horizontal {
                background: #FF5B06;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
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
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
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
            
            QPushButton#folderBtn {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
            }
            QPushButton#folderBtn:hover {
                background: rgba(255, 91, 6, 0.25);
                border-color: rgba(255, 91, 6, 0.5);
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
        self.volume_input.setValue(value)
        self.volume_input.blockSignals(False)
        self.volumeChanged.emit(value)
    
    def _on_volume_input_change(self, value: int):
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(value)
        self.volume_slider.blockSignals(False)
        self.volumeChanged.emit(value)
    
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
            # Parse mm:ss or m:ss format
            if ':' in text:
                parts = text.split(':')
                mins = int(parts[0])
                secs = int(parts[1]) if len(parts) > 1 else 0
            else:
                # Just seconds
                mins = 0
                secs = int(text)
            
            total_seconds = mins * 60 + secs
            # Emit seek in seconds directly
            self.seekChanged.emit(total_seconds)
        except (ValueError, IndexError):
            pass  # Invalid input, ignore
        
        # Deselect the field
        self.time_current.clearFocus()


class _PlayerBarOverlayWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("playerBarOverlayWindow")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay

    def set_bar(self, bar: QWidget):
        try:
            if bar is None:
                return
            try:
                bar.setParent(self)
            except Exception:
                pass
            try:
                self._lay.addWidget(bar)
            except Exception:
                pass
            try:
                bar.show()
            except Exception:
                pass
        except Exception:
            pass


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
        
        # Qt Multimedia player
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)  # Set initial volume to 100%
        
        # Secondary player for crossfade
        self._player2 = QMediaPlayer()
        self._audio_output2 = QAudioOutput()
        self._player2.setAudioOutput(self._audio_output2)
        self._audio_output2.setVolume(0.0)  # Start silent
        
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
        self._video_mode = False
        self._music_folder = None

        self._helxaic_page_visible = False
        self._render_gate_reason = None
        self._video_mode_restore_pending = False
        self._video_was_on_when_suspended = False

        self._rtss_excluded_once = False
        self._subtitle_appearance_applied_once = False
        self._last_media_for_sub_auto_pick = None
        
        # Discord Rich Presence
        self._discord = None
        self._init_discord()
        
        # Config file for persistence (use AppData for bundled exe)
        appdata_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
        os.makedirs(appdata_dir, exist_ok=True)
        self._config_path = os.path.join(appdata_dir, "music_page.json")
        
        # Initialize subtitle preference defaults
        self._subtitle_style_preset = 'outline'
        self._subtitle_font_size = 16
        
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
        
        # Load last state
        self._load_last_state()
        
        # Start global media key listener for hardware media keys
        # (keyboard Fn keys, Bluetooth headphone/earbuds, USB controllers)
        self._setup_media_key_service()
        
        # Monitor audio device changes to auto-switch when a new device
        # connects (e.g. Bluetooth headphones, USB DAC)
        self._setup_audio_device_monitor()
        
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

    def _disable_video_output_and_subtitles(self, reason: str, switch_to_playlist: bool):
        try:
            if hasattr(self, 'video_player') and self.video_player:
                try:
                    self.video_player.set_render_suspended(True)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, '_player') and self._player:
                self._player.setVideoOutput(None)
        except Exception:
            pass

        if switch_to_playlist:
            try:
                self._video_mode = False
            except Exception:
                pass
            try:
                if hasattr(self, 'stack') and self.stack:
                    self.stack.setCurrentIndex(0)
            except Exception:
                pass

        try:
            self._render_gate_reason = reason
        except Exception:
            pass

    def _enable_video_output_and_subtitles(self, reason: str):
        try:
            if not hasattr(self, '_player') or not self._player:
                return
        except Exception:
            return

        try:
            self._video_mode = True
        except Exception:
            pass

        try:
            if hasattr(self, 'stack') and self.stack:
                self.stack.setCurrentIndex(1)
        except Exception:
            pass

        try:
            if hasattr(self, 'video_player') and self.video_player:
                self._player.setVideoOutput(self.video_player.video_widget)
        except Exception:
            pass

        try:
            if hasattr(self, 'video_player') and self.video_player:
                self.video_player.set_render_suspended(False)
        except Exception:
            pass

        try:
            self._render_gate_reason = reason
        except Exception:
            pass

        try:
            QTimer.singleShot(0, self._auto_pick_embedded_subtitles_if_available)
        except Exception:
            pass

    def on_helxaic_page_hidden(self):
        try:
            self._helxaic_page_visible = False
        except Exception:
            pass

        try:
            self._video_mode_restore_pending = bool(getattr(self, '_video_mode', False))
        except Exception:
            self._video_mode_restore_pending = False

        self._disable_video_output_and_subtitles('page_hidden', switch_to_playlist=True)

    def on_helxaic_page_shown(self):
        try:
            self._helxaic_page_visible = True
        except Exception:
            pass

        try:
            if not getattr(self, '_video_mode_restore_pending', False):
                return
        except Exception:
            return

        if not self._is_app_render_allowed():
            return

        try:
            self._video_mode_restore_pending = False
        except Exception:
            pass
        self._enable_video_output_and_subtitles('page_shown_restore')

    def _on_app_state_changed_for_render_gate(self, state):
        try:
            if not getattr(self, '_helxaic_page_visible', False):
                return
        except Exception:
            return

        allowed = self._is_app_render_allowed()

        if not allowed:
            try:
                if getattr(self, '_video_mode', False):
                    self._video_was_on_when_suspended = True
                    self._disable_video_output_and_subtitles('app_inactive', switch_to_playlist=False)
                else:
                    self._video_was_on_when_suspended = False
            except Exception:
                pass
            return

        try:
            if getattr(self, '_video_mode_restore_pending', False):
                self._video_mode_restore_pending = False
                self._enable_video_output_and_subtitles('app_active_restore')
                return
        except Exception:
            pass

        try:
            if getattr(self, '_video_was_on_when_suspended', False) and getattr(self, '_video_mode', False):
                self._enable_video_output_and_subtitles('app_active_resume')
            self._video_was_on_when_suspended = False
        except Exception:
            pass
    
    def showEvent(self, event):
        """Force layout update when widget is shown to prevent PlayerBar clipping."""
        super().showEvent(event)
        # Force immediate layout recalculation
        self.updateGeometry()
        if hasattr(self, 'player_bar'):
            self.player_bar.updateGeometry()
            self.player_bar.update()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            from integrations.tools_downloader import is_ffmpeg_available
            return is_ffmpeg_available()
        except ImportError:
            # Fallback: check if ffmpeg is in PATH
            import subprocess
            try:
                result = subprocess.run(
                    ["ffmpeg", "-version"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                return result.returncode == 0
            except Exception:
                return False
    
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
        """Initialize global media key listener for hardware media controls.
        
        Creates a MediaKeyService that captures Play/Pause, Next, Previous,
        and Stop media key events from ALL input devices globally:
        - Laptop keyboard Fn keys (e.g. HP Victus Fn+F7/F8/F9)
        - Bluetooth headphones/earbuds (AVRCP protocol)  
        - USB media controllers
        - External keyboards with media keys
        
        The service runs in a background daemon thread and uses Win32
        RegisterHotKey to capture keys even when the app is not focused.
        Signals are connected to the corresponding playback control methods.
        """
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
            # Qt keyPressEvent will still handle media keys when focused.
            self._media_key_service = None
            print(f"[Music] MediaKeyService not available: {e}")
            print("[Music] Media keys will only work when app has focus")
        except Exception as e:
            # Unexpected error - log but don't crash the music panel
            self._media_key_service = None
            print(f"[Music] Failed to start media key service: {e}")
    
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
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for music control.
        
        Standard letter keys (Space, P, N, etc.) are handled here.
        Hardware media keys (Play/Pause, Next, Previous, Stop) are
        handled exclusively by MediaKeyService's global hook to
        avoid double-fire when the app has focus.
        """
        key = event.key()
        
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
        
        # R: Shuffle toggle
        if key == Qt.Key_R:
            self.player_bar._toggle_shuffle()
            event.accept()
            return
        
        # F: Toggle fullscreen
        if key == Qt.Key_F:
            try:
                # In video view, use the VideoPlayerWidget fullscreen path so overlays
                # (subtitles + PlayerBar overlay window) work correctly.
                if getattr(self, '_video_mode', False) and hasattr(self, 'video_player') and self.video_player is not None:
                    self.video_player._toggle_fullscreen()
                else:
                    self._toggle_fullscreen()
            except Exception:
                try:
                    self._toggle_fullscreen()
                except Exception:
                    pass
            event.accept()
            return
        
        # Escape: Exit fullscreen
        if key == Qt.Key_Escape:
            try:
                # Prefer exiting VideoPlayerWidget fullscreen when in video view.
                if getattr(self, '_video_mode', False) and hasattr(self, 'video_player') and self.video_player is not None:
                    if getattr(self.video_player, '_is_fullscreen', False):
                        self.video_player._toggle_fullscreen()
                        event.accept()
                        return
            except Exception:
                pass

            if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
                self._toggle_fullscreen()
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
        
        # Pass to parent if not handled
        super().keyPressEvent(event)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === Menu Bar ===
        self._create_menu_bar(layout)
        
        # Main content stack
        self.stack = QStackedWidget()
        
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
        
        # === Page 1: Video View (VLC-style player) ===
        self.video_player = VideoPlayerWidget(self._player, self)
        self.video_player.backRequested.connect(self._switch_to_playlist)
        self.video_player.fullscreenToggled.connect(self._toggle_window_fullscreen)
        self.stack.addWidget(self.video_player)

        try:
            self._apply_saved_subtitle_appearance()
        except Exception:
            pass
        
        # Main view area (Playlist + YouTube Sidebar) with user-resizable splitter
        self.main_splitter = QSplitter(Qt.Horizontal, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.setOpaqueResize(True)

        self.main_splitter.addWidget(self.stack)

        # YouTube Panel (Initially Hidden)
        self.yt_panel = YouTubeDownloaderPanel(self)
        self.yt_panel.hide()
        self.yt_panel.closeRequested.connect(self._toggle_yt_panel)
        self.yt_panel.downloadFinished.connect(self._on_yt_download_finished)
        self.main_splitter.addWidget(self.yt_panel)

        # Keep main content dominant when splitter moves
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)

        # Default (panel hidden): all width to main content
        self._yt_last_width = 320
        self._update_yt_panel_constraints()
        self.main_splitter.setSizes([1, 0])

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
            QVideoWidget#videoWidget {
                background: #000000;
            }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Enforce max sidebar width (<= 50% of panel)
        self._update_yt_panel_constraints()
        try:
            if getattr(self, '_is_fullscreen', False) and getattr(self, '_playerbar_overlay_enabled', False):
                self._update_playerbar_overlay_geometry()
        except Exception:
            pass

    def _update_yt_panel_constraints(self):
        """Clamp YouTube panel width to <= 50% of available width."""
        if not hasattr(self, 'yt_panel'):
            return
        total_w = max(1, self.width())
        # Minimum width is 20% of total, maximum is 50% of total
        min_w = max(1, int(total_w * 0.2))
        max_w = max(min_w, int(total_w * 0.5))

        self.yt_panel.setMinimumWidth(min_w)
        self.yt_panel.setMaximumWidth(max_w)

        # If visible and currently wider than max, pull it back via splitter sizes.
        if hasattr(self, 'main_splitter') and self.yt_panel.isVisible():
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 2:
                total = max(1, sizes[0] + sizes[1])
                if sizes[1] > max_w:
                    sizes[1] = max_w
                    sizes[0] = max(1, total - sizes[1])
                    self.main_splitter.setSizes(sizes)

    def _on_main_splitter_moved(self, pos, index):
        # Record the user's chosen width and keep it clamped.
        if hasattr(self, 'main_splitter'):
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 2:
                # Remember last width but keep it within current min/max.
                total_w = max(1, self.width())
                min_w = max(1, int(total_w * 0.2))
                max_w = max(min_w, int(total_w * 0.5))
                self._yt_last_width = max(min_w, min(max_w, sizes[1]))
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
    
    def _connect_signals(self):
        # Player bar
        self.player_bar.playClicked.connect(self._toggle_play)
        self.player_bar.prevClicked.connect(self._prev_track)
        self.player_bar.nextClicked.connect(self._next_track)
        self.player_bar.seekChanged.connect(self._seek)
        self.player_bar.volumeChanged.connect(self._set_volume)
        self.player_bar.videoToggled.connect(self._toggle_video)
        self.player_bar.folderClicked.connect(self._browse_folder_direct)
        
        # Table
        self.table.trackDoubleClicked.connect(self._play_track)
        
        # Player signals
        self._player.positionChanged.connect(self._on_position)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)
    
    def _on_player_error(self, error, error_string):
        """Handle media player errors."""
        print(f"Player error: {error} - {error_string}")
    
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
                # else: stay stopped at end
    
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
        from PySide6.QtGui import QAction, QActionGroup
        
        menu_bar = QMenuBar()
        menu_bar.setObjectName("musicMenuBar")
        
        # === Audio Menu ===
        audio_menu = menu_bar.addMenu("Audio")
        audio_menu.setObjectName("audioMenu")
        self._audio_menu = audio_menu  # Store reference for dynamic updates
        
        # Output Device submenu
        self._device_menu = audio_menu.addMenu("Output Device")
        self._device_menu.setObjectName("deviceMenu")
        self._populate_audio_devices()
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
            QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #1a1a1a; border: 1px solid #FF5B06; width: 12px; height: 12px; margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #FF5B06; border-radius: 3px; }
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
        
        self._crossfade_slider.valueChanged.connect(on_crossfade_slider_change)
        
        slider_layout.addWidget(self._crossfade_slider)
        slider_layout.addWidget(self._crossfade_label)
        
        slider_action = QWidgetAction(self)
        slider_action.setDefaultWidget(slider_widget)
        crossfade_menu.addAction(slider_action)
        
        # === Video Menu ===
        video_menu = menu_bar.addMenu("Video")
        video_menu.setObjectName("videoMenu")
        
        # Toggle Video Mode
        self.action_toggle_video = QAction("Toggle Video View", self)
        self.action_toggle_video.setShortcut("V")
        self.action_toggle_video.triggered.connect(self._toggle_video)
        video_menu.addAction(self.action_toggle_video)
        
        video_menu.addSeparator()
        
        # Aspect Ratio submenu (moved above Fullscreen)
        aspect_menu = video_menu.addMenu("Aspect Ratio")
        aspect_menu.setObjectName("aspectRatioMenu")
        
        self.action_aspect_fill = QAction("Fill", self)
        self.action_aspect_fill.setCheckable(True)
        self.action_aspect_fill.triggered.connect(lambda: self._set_aspect_ratio("fill"))
        aspect_menu.addAction(self.action_aspect_fill)
        
        self.action_aspect_fit = QAction("Fit", self)
        self.action_aspect_fit.setCheckable(True)
        self.action_aspect_fit.setChecked(True)  # Default
        self.action_aspect_fit.triggered.connect(lambda: self._set_aspect_ratio("fit"))
        aspect_menu.addAction(self.action_aspect_fit)
        
        self.action_aspect_stretch = QAction("Stretch", self)
        self.action_aspect_stretch.setCheckable(True)
        self.action_aspect_stretch.triggered.connect(lambda: self._set_aspect_ratio("stretch"))
        aspect_menu.addAction(self.action_aspect_stretch)
        
        video_menu.addSeparator()
        
        # Fullscreen
        self.action_fullscreen = QAction("Fullscreen", self)
        self.action_fullscreen.setShortcut("F")
        self.action_fullscreen.triggered.connect(self._toggle_fullscreen)
        video_menu.addAction(self.action_fullscreen)

        # === Subtitle Menu ===
        subtitle_menu = menu_bar.addMenu("Subtitle")
        subtitle_menu.setObjectName("subtitleMenu")

        self.action_add_subtitle = QAction("Add Subtitle File...", self)
        self.action_add_subtitle.triggered.connect(self._add_subtitle_file)
        subtitle_menu.addAction(self.action_add_subtitle)

        subtitle_menu.addSeparator()

        self._subtitle_track_menu = subtitle_menu.addMenu("Sub Track")
        self._subtitle_track_menu.setObjectName("subtitleTrackMenu")
        self._subtitle_track_menu.aboutToShow.connect(self._populate_subtitle_tracks_menu)

        subtitle_menu.addSeparator()

        self._subtitle_style_menu = subtitle_menu.addMenu("Style")
        self._subtitle_style_menu.setObjectName("subtitleStyleMenu")
        self._subtitle_style_menu.aboutToShow.connect(self._sync_subtitle_style_menu)

        self._subtitle_style_variant_actions = {}
        self._subtitle_style_variant_groups = {}
        self._subtitle_style_submenus = {}

        self._subtitle_style_global_group = QActionGroup(self)
        self._subtitle_style_global_group.setExclusive(True)

        def _add_variant(preset_key: str, label: str, bold: bool, italic: bool):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, pk=preset_key, b=bold, i=italic: self._set_subtitle_style_variant(pk, b, i))
            try:
                self._subtitle_style_global_group.addAction(act)
            except Exception:
                pass
            self._subtitle_style_submenus[preset_key].addAction(act)
            self._subtitle_style_variant_actions[(preset_key, bool(bold), bool(italic))] = act

        for key, label in [
            ("outline", "Outline"),
            ("shadow", "Shadow"),
            ("box", "Box"),
        ]:
            sub = self._subtitle_style_menu.addMenu(label)
            sub.setObjectName(f"subtitleStyleSubMenu_{key}")
            self._subtitle_style_submenus[key] = sub

            self._subtitle_style_variant_groups[key] = self._subtitle_style_global_group

            _add_variant(key, "Regular", False, False)
            _add_variant(key, "Bold", True, False)
            _add_variant(key, "Italic", False, True)
            _add_variant(key, "Bold Italic", True, True)

        subtitle_menu.addSeparator()

        self._subtitle_size_menu = subtitle_menu.addMenu("Size")
        self._subtitle_size_menu.setObjectName("subtitleSizeMenu")
        self._subtitle_size_menu.aboutToShow.connect(self._sync_subtitle_size_menu)

        from PySide6.QtWidgets import QWidgetAction, QWidget, QHBoxLayout, QSlider, QLabel, QSpinBox

        size_widget = QWidget()
        size_widget.setStyleSheet("""
            QWidget { background: transparent; padding: 5px 10px; }
            QLabel { color: #e0e0e0; font-size: 12px; min-width: 40px; }
            QSpinBox {
                background: rgba(50, 54, 62, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 54px;
            }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px; border: none; }
            QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #1a1a1a; border: 1px solid #FF5B06; width: 12px; height: 12px; margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #FF5B06; border-radius: 3px; }
        """)

        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(10, 5, 10, 5)
        size_layout.setSpacing(10)

        size_label = QLabel("Text")
        self._subtitle_size_slider = QSlider(Qt.Horizontal)
        self._subtitle_size_slider.setRange(8, 48)
        self._subtitle_size_slider.setValue(16)
        self._subtitle_size_slider.setFixedWidth(130)

        self._subtitle_size_spin = QSpinBox()
        self._subtitle_size_spin.setRange(8, 48)
        self._subtitle_size_spin.setValue(16)

        def _apply_size(val: int):
            try:
                self._set_subtitle_font_size(int(val))
            except Exception:
                pass

        def _on_slider(val: int):
            self._subtitle_size_spin.blockSignals(True)
            self._subtitle_size_spin.setValue(int(val))
            self._subtitle_size_spin.blockSignals(False)
            _apply_size(val)

        def _on_spin(val: int):
            self._subtitle_size_slider.blockSignals(True)
            self._subtitle_size_slider.setValue(int(val))
            self._subtitle_size_slider.blockSignals(False)
            _apply_size(val)

        self._subtitle_size_slider.valueChanged.connect(_on_slider)
        self._subtitle_size_spin.valueChanged.connect(_on_spin)

        size_layout.addWidget(size_label)
        size_layout.addWidget(self._subtitle_size_slider)
        size_layout.addWidget(self._subtitle_size_spin)

        size_action = QWidgetAction(self)
        size_action.setDefaultWidget(size_widget)
        self._subtitle_size_menu.addAction(size_action)
        
        # === Tools Menu ===
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.setObjectName("toolsMenu")
        
        # Select Folder
        self.action_select_folder = QAction("Select Media Folder...", self)
        self.action_select_folder.setShortcut("Ctrl+O")
        self.action_select_folder.triggered.connect(self._browse_folder_direct)
        tools_menu.addAction(self.action_select_folder)
        
        # Download from YouTube
        self.action_download_yt = QAction("YouTube Downloader", self)
        self.action_download_yt.setShortcut("Ctrl+U")
        self.action_download_yt.triggered.connect(self._toggle_yt_panel)
        tools_menu.addAction(self.action_download_yt)
        
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
                background: rgba(255, 91, 6, 0.3);
            }
            QMenuBar::item:pressed {
                background: rgba(255, 91, 6, 0.5);
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
                background: rgba(255, 91, 6, 0.4);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)
        
        self._menu_bar_widget = menu_bar  # Store reference for fullscreen toggle
        layout.addWidget(menu_bar)

        try:
            self._apply_saved_subtitle_style_preset()
        except Exception:
            pass

        try:
            self._apply_saved_subtitle_font_size()
        except Exception:
            pass

    def _get_subtitle_style_settings(self):
        try:
            return QSettings("TDD131", "HELXAID")
        except Exception:
            return QSettings()

    def _apply_saved_subtitle_style_preset(self):
        if not hasattr(self, 'video_player'):
            return
        s = self._get_subtitle_style_settings()
        preset = s.value("MusicPlayer/SubtitleStylePreset", "outline", type=str)
        preset = (preset or "outline").strip().lower()
        if preset not in ("outline", "shadow", "box"):
            preset = "outline"
        try:
            self.video_player.set_subtitle_style_preset(preset)
        except Exception:
            pass

        try:
            bold = bool(int(s.value("MusicPlayer/SubtitleFontBold", 1)))
        except Exception:
            bold = True
        try:
            italic = bool(int(s.value("MusicPlayer/SubtitleFontItalic", 0)))
        except Exception:
            italic = False
        try:
            self.video_player.set_subtitle_font_variant(bold, italic)
        except Exception:
            pass

    def _apply_saved_subtitle_appearance(self):
        try:
            self._apply_saved_subtitle_style_preset()
        except Exception:
            pass
        try:
            self._apply_saved_subtitle_font_size()
        except Exception:
            pass

    def _apply_saved_subtitle_font_size(self):
        if not hasattr(self, 'video_player'):
            return
        s = self._get_subtitle_style_settings()
        try:
            pt = int(s.value("MusicPlayer/SubtitleFontSize", 16))
        except Exception:
            pt = 16
        if pt < 8:
            pt = 8
        if pt > 48:
            pt = 48
        try:
            self.video_player.set_subtitle_font_size(pt)
        except Exception:
            pass

    def _set_subtitle_font_size(self, pt: int):
        try:
            v = int(pt)
        except Exception:
            v = 16
        if v < 8:
            v = 8
        if v > 48:
            v = 48
        self._subtitle_font_size = v
        try:
            if hasattr(self, 'video_player'):
                self.video_player.set_subtitle_font_size(v)
        except Exception:
            pass
        # Save to JSON state
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._save_state)
        except Exception:
            pass

    def _sync_subtitle_size_menu(self):
        if not hasattr(self, '_subtitle_size_slider') or not hasattr(self, '_subtitle_size_spin'):
            return
        pt = 16
        try:
            if hasattr(self, 'video_player'):
                pt = int(self.video_player.get_subtitle_font_size())
        except Exception:
            pt = 16
        if pt < 8:
            pt = 8
        if pt > 48:
            pt = 48
        try:
            self._subtitle_size_slider.blockSignals(True)
            self._subtitle_size_spin.blockSignals(True)
            self._subtitle_size_slider.setValue(pt)
            self._subtitle_size_spin.setValue(pt)
        finally:
            self._subtitle_size_slider.blockSignals(False)
            self._subtitle_size_spin.blockSignals(False)

    def _set_subtitle_style_preset(self, preset: str):
        preset = (preset or "outline").strip().lower()
        if preset not in ("outline", "shadow", "box"):
            preset = "outline"
        self._subtitle_style_preset = preset
        try:
            if hasattr(self, 'video_player'):
                self.video_player.set_subtitle_style_preset(preset)
        except Exception:
            pass
        # Save to JSON state
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._save_state)
        except Exception:
            pass

    def _set_subtitle_style_variant(self, preset: str, bold: bool, italic: bool):
        preset = (preset or "outline").strip().lower()
        if preset not in ("outline", "shadow", "box"):
            preset = "outline"
        try:
            if hasattr(self, 'video_player'):
                self.video_player.set_subtitle_style_preset(preset)
        except Exception:
            pass
        try:
            if hasattr(self, 'video_player'):
                self.video_player.set_subtitle_font_variant(bool(bold), bool(italic))
        except Exception:
            pass
        try:
            s = self._get_subtitle_style_settings()
            s.setValue("MusicPlayer/SubtitleStylePreset", preset)
            s.setValue("MusicPlayer/SubtitleFontBold", 1 if bool(bold) else 0)
            s.setValue("MusicPlayer/SubtitleFontItalic", 1 if bool(italic) else 0)
            try:
                s.sync()
            except Exception:
                pass
        except Exception:
            pass

    def _sync_subtitle_style_menu(self):
        preset = "outline"
        try:
            if hasattr(self, 'video_player'):
                preset = self.video_player.get_subtitle_style_preset()
        except Exception:
            preset = "outline"
        preset = (preset or "outline").strip().lower()
        if preset not in ("outline", "shadow", "box"):
            preset = "outline"

        bold = True
        italic = False
        try:
            if hasattr(self, 'video_player'):
                b, i = self.video_player.get_subtitle_font_variant()
                bold = bool(b)
                italic = bool(i)
        except Exception:
            bold = True
            italic = False

        try:
            act = self._subtitle_style_variant_actions.get((preset, bool(bold), bool(italic)))
            if act:
                act.setChecked(True)
        except Exception:
            pass

    def _ensure_subtitle_state(self):
        if not hasattr(self, '_current_media_path'):
            self._current_media_path = None
        if not hasattr(self, '_current_media_url'):
            self._current_media_url = None
        if not hasattr(self, '_subtitle_extract_cache'):
            self._subtitle_extract_cache = {}
        if not hasattr(self, '_subtitle_embedded_reverse'):
            self._subtitle_embedded_reverse = {}
        if not hasattr(self, '_subtitle_extract_last_error'):
            self._subtitle_extract_last_error = {}
        if not hasattr(self, '_subtitle_user_disabled'):
            self._subtitle_user_disabled = False
        if not hasattr(self, '_subtitle_prefer_embedded'):
            self._subtitle_prefer_embedded = True
        if not hasattr(self, '_subtitle_pref_loaded'):
            self._subtitle_pref_loaded = False

        if not self._subtitle_pref_loaded:
            self._subtitle_pref_loaded = True
            try:
                s = self._get_subtitle_style_settings()
                mode = s.value("MusicPlayer/SubtitleDefaultMode", "embedded", type=str)
                mode = (mode or "embedded").strip().lower()
                self._subtitle_prefer_embedded = (mode == "embedded")
            except Exception:
                self._subtitle_prefer_embedded = True

    def _set_subtitle_default_mode(self, mode: str):
        self._ensure_subtitle_state()
        m = (mode or "embedded").strip().lower()
        if m not in ("embedded", "external"):
            m = "embedded"
        self._subtitle_prefer_embedded = (m == "embedded")
        try:
            s = self._get_subtitle_style_settings()
            s.setValue("MusicPlayer/SubtitleDefaultMode", m)
            try:
                s.sync()
            except Exception:
                pass
        except Exception:
            pass

    def _on_subtitles_disabled_by_user(self):
        self._ensure_subtitle_state()
        self._subtitle_user_disabled = True
        try:
            self._set_subtitle_default_mode("external")
        except Exception:
            pass
        if hasattr(self, 'video_player'):
            try:
                self.video_player.clear_subtitles()
            except Exception:
                pass

    def _mark_subtitles_enabled_by_user(self):
        self._ensure_subtitle_state()
        self._subtitle_user_disabled = False

    def _pick_best_embedded_subtitle_stream(self, streams):
        try:
            if not streams:
                return None
            def score(s):
                lang = (s.get('lang') or '').lower().strip()
                title = (s.get('title') or '').lower()
                codec = (s.get('codec') or '').lower()
                sc = 0
                if lang in ('eng', 'en'):
                    sc += 100
                if 'english' in title:
                    sc += 90
                if codec in ('ass', 'ssa'):
                    sc += 10
                return sc
            return sorted(streams, key=score, reverse=True)[0]
        except Exception:
            return streams[0] if streams else None

    def _auto_pick_embedded_subtitles_if_available(self):
        self._ensure_subtitle_state()
        if not hasattr(self, 'video_player'):
            return
        if not self._current_media_path or not os.path.exists(self._current_media_path):
            return
        if getattr(self, '_subtitle_user_disabled', False):
            return
        if not getattr(self, '_subtitle_prefer_embedded', True):
            return
        try:
            active_path = self.video_player.get_active_subtitle_path()
        except Exception:
            active_path = None
        if active_path:
            return

        streams = self._list_embedded_subtitle_streams(self._current_media_path)
        if not streams:
            return
        best = self._pick_best_embedded_subtitle_stream(streams)
        if not best:
            return

        try:
            idx = int(best.get('stream_index'))
        except Exception:
            return
        codec = best.get('codec') or ''
        out_sub = self._extract_embedded_subtitle(self._current_media_path, idx, codec)
        if not out_sub:
            return
        try:
            self.video_player.set_subtitle_file(out_sub)
            self._mark_subtitles_enabled_by_user()
            self._set_subtitle_default_mode("embedded")
        except Exception:
            pass

    def _set_current_media_local_path(self, path: Optional[str]):
        self._ensure_subtitle_state()
        self._current_media_path = path
        self._current_media_url = None

    def _set_current_media_url(self, url: Optional[str]):
        self._ensure_subtitle_state()
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

    def _list_embedded_subtitle_streams(self, video_path: str):
        try:
            ffprobe = self._get_ffprobe_path()
            cmd = [
                ffprobe,
                '-v', 'error',
                '-select_streams', 's',
                '-show_entries', 'stream=index,codec_name:stream_tags=language,title',
                '-of', 'json',
                video_path,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=0x08000000)
            if r.returncode != 0:
                return []
            data = json.loads(r.stdout or '{}')
            streams = data.get('streams', []) or []
            out = []
            for s in streams:
                idx = s.get('index', None)
                codec = s.get('codec_name', '')
                tags = s.get('tags', {}) or {}
                lang = tags.get('language', '')
                title = tags.get('title', '')
                if idx is None:
                    continue
                out.append({'stream_index': int(idx), 'codec': codec, 'lang': lang, 'title': title})
            return out
        except Exception:
            return []

    def _extract_embedded_subtitle(self, video_path: str, stream_index: int, codec: str = ''):
        self._ensure_subtitle_state()
        codec_l = (codec or '').lower().strip()

        image_based = codec_l in (
            'hdmv_pgs_subtitle', 'pgs', 'dvd_subtitle', 'vobsub', 'dvb_subtitle',
            'xsub', 'dvbsub',
        )
        if image_based:
            cache_key = (video_path, int(stream_index), '.sup')
            self._subtitle_extract_last_error[cache_key] = (
                f"Embedded subtitle codec '{codec_l}' is image-based (PGS/VobSub/DVB). "
                "HELXAIC current subtitle renderer is text-only, so this codec cannot be extracted into SRT/ASS reliably."
            )
            return None

        out_ext = '.ass' if codec_l in ('ass', 'ssa') else '.srt'

        cache_key = (video_path, int(stream_index), out_ext)
        cached = self._subtitle_extract_cache.get(cache_key)
        if cached and os.path.exists(cached):
            self._subtitle_embedded_reverse[cached] = cache_key
            return cached

        ffmpeg = self._get_ffmpeg_path()
        out_dir = os.path.join(tempfile.gettempdir(), 'HELXAID_subs')
        os.makedirs(out_dir, exist_ok=True)
        h = hashlib.sha1(f"{video_path}|{stream_index}|{out_ext}".encode('utf-8', errors='replace')).hexdigest()[:16]
        out_path = os.path.join(out_dir, f"sub_{h}_s{stream_index}{out_ext}")

        if out_ext == '.ass':
            cmd = [
                ffmpeg,
                '-y',
                '-i', video_path,
                '-map', f'0:{int(stream_index)}',
                '-c:s', 'copy',
                out_path,
            ]
        else:
            cmd = [
                ffmpeg,
                '-y',
                '-i', video_path,
                '-map', f'0:{int(stream_index)}',
                '-c:s', 'srt',
                out_path,
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=0x08000000)
        if r.returncode == 0 and os.path.exists(out_path):
            self._subtitle_extract_cache[cache_key] = out_path
            self._subtitle_embedded_reverse[out_path] = cache_key
            self._subtitle_extract_last_error[cache_key] = None
            return out_path
        try:
            err = (r.stderr or '').strip()
            self._subtitle_extract_last_error[cache_key] = err if err else f"ffmpeg failed with code {r.returncode}"
        except Exception:
            pass
        return None

    def _add_subtitle_file(self):
        from PySide6.QtWidgets import QFileDialog
        self._ensure_subtitle_state()
        start_dir = ''
        if self._current_media_path and os.path.exists(self._current_media_path):
            try:
                start_dir = os.path.dirname(self._current_media_path)
            except Exception:
                start_dir = ''
        f, _ = QFileDialog.getOpenFileName(self, 'Select Subtitle File', start_dir, 'Subtitles (*.srt *.vtt *.ass *.ssa)')
        if not f:
            return
        if hasattr(self, 'video_player'):
            self._mark_subtitles_enabled_by_user()
            try:
                self._set_subtitle_default_mode("external")
            except Exception:
                pass
            self.video_player.set_subtitle_file(f)

    def _populate_subtitle_tracks_menu(self):
        from PySide6.QtGui import QAction, QActionGroup
        self._ensure_subtitle_state()
        menu = self._subtitle_track_menu
        menu.clear()

        self._subtitle_action_group = QActionGroup(self)
        self._subtitle_action_group.setExclusive(True)

        active_path = None
        if hasattr(self, 'video_player'):
            try:
                active_path = self.video_player.get_active_subtitle_path()
            except Exception:
                active_path = None

        active_embedded = None
        try:
            if active_path:
                active_embedded = self._subtitle_embedded_reverse.get(active_path)
        except Exception:
            active_embedded = None

        disable_action = QAction('Disable', self)
        disable_action.setCheckable(True)
        disable_action.setChecked(not active_path)
        disable_action.triggered.connect(lambda _c=False: self._on_subtitles_disabled_by_user())
        self._subtitle_action_group.addAction(disable_action)
        menu.addAction(disable_action)

        if not (self._current_media_path and os.path.exists(self._current_media_path)):
            try:
                print(f"[Subtitle] No local media path for embedded subtitles. _current_media_path={self._current_media_path}")
            except Exception:
                pass

        # Sidecar subtitles (same basename)
        if self._current_media_path and os.path.exists(self._current_media_path):
            base, _ext = os.path.splitext(self._current_media_path)
            sidecars = []
            for p in [
                base + '.srt', base + '.vtt', base + '.ass', base + '.ssa',
                base + '.SRT', base + '.VTT', base + '.ASS', base + '.SSA',
            ]:
                if os.path.exists(p) and p not in sidecars:
                    sidecars.append(p)
            if sidecars:
                menu.addSeparator()
                for p in sidecars:
                    name = os.path.basename(p)
                    a = QAction(name, self)
                    a.setCheckable(True)
                    if active_path and os.path.normcase(active_path) == os.path.normcase(p):
                        a.setChecked(True)
                    def _on_pick_sidecar(_c=False, _p=p):
                        if not hasattr(self, 'video_player'):
                            return
                        self._mark_subtitles_enabled_by_user()
                        try:
                            self._set_subtitle_default_mode("external")
                        except Exception:
                            pass
                        self.video_player.set_subtitle_file(_p)
                    a.triggered.connect(_on_pick_sidecar)
                    self._subtitle_action_group.addAction(a)
                    menu.addAction(a)
            else:
                try:
                    print(f"[Subtitle] ffprobe found 0 embedded subtitle streams for: {self._current_media_path}")
                except Exception:
                    pass

        # Embedded subtitles
        if self._current_media_path and os.path.exists(self._current_media_path):
            streams = self._list_embedded_subtitle_streams(self._current_media_path)
            if streams:
                menu.addSeparator()
                for s in streams:
                    idx = s.get('stream_index')
                    lang = s.get('lang') or ''
                    title = s.get('title') or ''
                    codec = s.get('codec') or ''
                    label = f"Embedded: s:{idx}"
                    if lang:
                        label += f" [{lang}]"
                    if title:
                        label += f" {title}"
                    if codec:
                        label += f" ({codec})"
                    a = QAction(label, self)
                    a.setCheckable(True)

                    try:
                        if active_embedded and active_embedded[0] == self._current_media_path and int(active_embedded[1]) == int(idx):
                            a.setChecked(True)
                    except Exception:
                        pass

                    def on_pick_embedded(_c=False, stream_index=int(idx), video_path=self._current_media_path, stream_codec=codec, stream_label=label):
                        if not hasattr(self, 'video_player'):
                            return
                        self._mark_subtitles_enabled_by_user()
                        try:
                            self._set_subtitle_default_mode("embedded")
                        except Exception:
                            pass
                        try:
                            print(f"[Subtitle] Pick embedded: path={video_path} stream={stream_index} codec={stream_codec}")
                        except Exception:
                            pass
                        out_sub = self._extract_embedded_subtitle(video_path, stream_index, stream_codec)
                        if out_sub:
                            try:
                                print(f"[Subtitle] Extracted embedded to: {out_sub}")
                            except Exception:
                                pass
                            self.video_player.set_subtitle_file(out_sub)
                            try:
                                cue_count = self.video_player.get_subtitle_cue_count()
                            except Exception:
                                cue_count = 0
                            try:
                                last_err = None
                                try:
                                    last_err = self.video_player.get_subtitle_last_error()
                                except Exception:
                                    last_err = None
                                print(f"[Subtitle] Parsed cues: {cue_count} (last_error={last_err})")
                            except Exception:
                                pass
                            if cue_count > 0:
                                return
                            try:
                                from PySide6.QtWidgets import QMessageBox
                                msg = 'Embedded subtitle was extracted but no cues could be parsed.'
                                if stream_codec:
                                    msg += f"\n\nStream codec: {stream_codec}"
                                if last_err:
                                    msg += f"\n\nSubtitle parser: {last_err}"
                                msg += "\n\nTip: If the embedded subtitle is ASS/SSA/PGS, it may not convert cleanly to SRT. Try an external .srt/.vtt file."
                                QMessageBox.warning(self, 'No Subtitles Parsed', msg)
                            except Exception:
                                pass
                            return
                        try:
                            from PySide6.QtWidgets import QMessageBox
                            err = None
                            try:
                                codec_l = (stream_codec or '').lower().strip()
                                image_based = codec_l in (
                                    'hdmv_pgs_subtitle', 'pgs', 'dvd_subtitle', 'vobsub', 'dvb_subtitle',
                                    'xsub', 'dvbsub',
                                )
                                if image_based:
                                    err = self._subtitle_extract_last_error.get((video_path, int(stream_index), '.sup'))
                                else:
                                    err = self._subtitle_extract_last_error.get(
                                        (video_path, int(stream_index), '.ass' if codec_l in ('ass', 'ssa') else '.srt')
                                    )
                            except Exception:
                                err = None
                            try:
                                print(f"[Subtitle] Extraction failed: {err}")
                            except Exception:
                                pass
                            msg = 'Could not extract embedded subtitles.'
                            if stream_codec:
                                msg += f"\n\nStream codec: {stream_codec}"
                            if err:
                                msg += f"\n\nffmpeg: {err[:900]}"
                            msg += "\n\nMake sure ffmpeg is available and the subtitle format is supported."
                            QMessageBox.warning(self, 'Subtitle Extraction Failed', msg)
                        except Exception:
                            pass

                    a.triggered.connect(on_pick_embedded)
                    self._subtitle_action_group.addAction(a)
                    menu.addAction(a)

    def _maybe_auto_load_sidecar_subtitles(self, media_path: str):
        if not hasattr(self, 'video_player'):
            return
        try:
            self._ensure_subtitle_state()
            if getattr(self, '_subtitle_user_disabled', False):
                return
            if getattr(self, '_subtitle_prefer_embedded', True):
                return
        except Exception:
            pass
        try:
            if self.video_player.get_active_subtitle_path():
                return
        except Exception:
            pass
        try:
            base, _ext = os.path.splitext(media_path)
            cand = [
                base + '.srt', base + '.vtt', base + '.ass', base + '.ssa',
                base + '.SRT', base + '.VTT', base + '.ASS', base + '.SSA',
            ]
            for p in cand:
                if os.path.exists(p):
                    self.video_player.set_subtitle_file(p)
                    return
        except Exception:
            return
        try:
            self.video_player.clear_subtitles()
        except Exception:
            pass
    
    def _populate_audio_devices(self):
        """Populate the audio device submenu with available devices."""
        from PySide6.QtMultimedia import QMediaDevices
        from PySide6.QtGui import QAction
        
        self._device_menu.clear()
        
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
            action.setChecked(device.id() == current_device.id())
            action.triggered.connect(lambda checked, d=device: self._set_audio_device(d))
            self._device_menu.addAction(action)
    
    def _set_audio_device(self, device):
        """Set the audio output device."""
        from PySide6.QtMultimedia import QAudioDevice
        
        self._audio_output.setDevice(device)
        
        # Save to config
        self._save_state()
        print(f"Audio device set to: {device.description()}")
    
    def _set_playback_speed(self, rate: float):
        """Set playback speed."""
        self._player.setPlaybackRate(rate)
        
        # Update checkmarks
        for r, action in self._speed_actions.items():
            action.setChecked(r == rate)
        
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
        
        # Reconnect video output if in video mode
        if self._video_mode and hasattr(self, 'video_player'):
            self._player.setVideoOutput(self.video_player.video_widget)
        
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
    
    def _toggle_yt_panel(self):
        """Toggle the integrated YouTube downloader sidebar."""
        if self.yt_panel.isVisible():
            self.yt_panel.hide()
            if hasattr(self, 'main_splitter'):
                # Collapse sidebar
                self.main_splitter.setSizes([1, 0])
        else:
            self.yt_panel.show()
            self._update_yt_panel_constraints()
            if hasattr(self, 'main_splitter'):
                max_w = self.yt_panel.maximumWidth()
                desired = min(max_w, max(self.yt_panel.minimumWidth(), int(getattr(self, '_yt_last_width', 320) or 320)))
                total = max(1, self.width())
                self.main_splitter.setSizes([max(1, total - desired), desired])
            self.yt_panel.url_edit.setFocus()
            # If paste buffer has a YT link, auto-fill it
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()
            if 'youtube.com' in text or 'youtu.be' in text:
                self.yt_panel.set_url(text)

    def _on_yt_download_finished(self, dest_path):
        """Handle track after integrated download completion."""
        if dest_path and os.path.isfile(dest_path):
            from PlaylistWidget import PlaylistWidget as _PW
            track = _PW.build_track_meta(dest_path) if hasattr(_PW, 'build_track_meta') else {
                'path': dest_path,
                'title': os.path.splitext(os.path.basename(dest_path))[0],
                'artist': 'YouTube',
                'duration': 0,
                'is_online': False,
                'mtime': os.path.getmtime(dest_path),
            }
            if not hasattr(self, '_playlist') or self._playlist is None:
                self._playlist = []
            self._playlist.append(track)
            self.table.set_tracks(self._playlist)
            print(f"[YouTube DL] Added to playlist: {os.path.basename(dest_path)}")

    def _rescan_folder(self):
        """Rescan current music folder."""
        if self._music_folder and os.path.exists(self._music_folder):
            self._load_tracks_from_folder(self._music_folder)
            print(f"Rescanned: {self._music_folder}")
    
    def _show_convert_dialog(self):
        """Show dialog to convert selected/all tracks to MP3."""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                        QPushButton, QFileDialog, QProgressBar,
                                        QRadioButton, QButtonGroup, QSpinBox, QGroupBox)
        from PySide6.QtCore import QThread, Signal
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Convert to MP3")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet("""
            QDialog {
                background: #1e1e2e;
                color: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                color: #FF5B06;
            }
            QRadioButton {
                color: #e0e0e0;
                padding: 5px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #666;
                background: #2a2a2a;
            }
            QRadioButton::indicator:checked {
                background: #FF5B06;
                border: 2px solid #FF5B06;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #FF5B06;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background: #FF5B06;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FF7B26;
            }
            QPushButton:disabled {
                background: #555;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 5px;
                background: #2a2a2a;
                height: 20px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 4px;
            }
            QSpinBox {
                background: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px 25px 5px 10px;
                min-width: 60px;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                background: #444;
                border-top-right-radius: 4px;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                background: #444;
                border-bottom-right-radius: 4px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #FF5B06;
            }
            QSpinBox::up-arrow {
                image: url(UI Icons/up-arrow.png);
                width: 10px;
                height: 10px;
            }
            QSpinBox::down-arrow {
                image: url(UI Icons/down-arrow.png);
                width: 10px;
                height: 10px;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        
        source_btn_group = QButtonGroup(dialog)
        current_track_radio = QRadioButton(f"Current track: {self._playlist[self._current_index].get('title', 'Unknown') if self._playlist else 'None'}")
        all_tracks_radio = QRadioButton(f"All tracks in playlist ({len(self._playlist)} tracks)")
        source_btn_group.addButton(current_track_radio, 0)
        source_btn_group.addButton(all_tracks_radio, 1)
        current_track_radio.setChecked(True)
        
        source_layout.addWidget(current_track_radio)
        source_layout.addWidget(all_tracks_radio)
        layout.addWidget(source_group)
        
        # Quality settings
        quality_group = QGroupBox("Quality")
        quality_layout = QHBoxLayout(quality_group)
        
        bitrate_label = QLabel("Bitrate (kbps):")
        bitrate_spin = QSpinBox()
        bitrate_spin.setRange(128, 320)
        bitrate_spin.setValue(320)
        bitrate_spin.setSingleStep(32)
        
        quality_layout.addWidget(bitrate_label)
        quality_layout.addWidget(bitrate_spin)
        quality_layout.addStretch()
        layout.addWidget(quality_group)
        
        # Output folder
        output_layout = QHBoxLayout()
        output_label = QLabel("Output folder:")
        output_path = QLabel(self._music_folder or "Not set")
        output_path.setStyleSheet("color: #888; font-size: 11px;")
        output_btn = QPushButton("Browse...")
        output_btn.setFixedWidth(100)
        
        def browse_output():
            folder = QFileDialog.getExistingDirectory(dialog, "Select Output Folder", self._music_folder or "")
            if folder:
                output_path.setText(folder)
        
        output_btn.clicked.connect(browse_output)
        output_layout.addWidget(output_label)
        output_layout.addWidget(output_path, 1)
        output_layout.addWidget(output_btn)
        layout.addLayout(output_layout)
        
        # Progress bar
        progress = QProgressBar()
        progress.setValue(0)
        progress.setVisible(False)
        layout.addWidget(progress)
        
        # Status label
        status_label = QLabel("")
        status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        convert_btn = QPushButton("Convert")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background: #444;")
        
        btn_layout.addStretch()
        btn_layout.addWidget(convert_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        cancel_btn.clicked.connect(dialog.reject)
        
        def start_convert():
            import subprocess
            
            # Get tracks to convert
            if current_track_radio.isChecked():
                tracks = [self._playlist[self._current_index]] if self._playlist else []
            else:
                tracks = self._playlist
            
            if not tracks:
                status_label.setText("No tracks to convert!")
                return
            
            output_dir = output_path.text()
            if not output_dir or not os.path.exists(output_dir):
                status_label.setText("Invalid output folder!")
                return
            
            bitrate = bitrate_spin.value()
            progress.setVisible(True)
            progress.setMaximum(len(tracks))
            convert_btn.setEnabled(False)
            
            success_count = 0
            for i, track in enumerate(tracks):
                input_path = track.get('path', '')
                if not input_path or not os.path.exists(input_path):
                    continue
                
                # Skip if already MP3
                if input_path.lower().endswith('.mp3'):
                    status_label.setText(f"Skipping (already MP3): {track.get('title', 'Unknown')}")
                    progress.setValue(i + 1)
                    continue
                
                # Output filename
                base_name = os.path.splitext(os.path.basename(input_path))[0]
                output_file = os.path.join(output_dir, f"{base_name}.mp3")
                
                status_label.setText(f"Converting: {track.get('title', 'Unknown')}")
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
                
                try:
                    # Use FFmpeg to convert
                    cmd = [
                        "ffmpeg", "-y", "-i", input_path,
                        "-vn",  # No video
                        "-acodec", "libmp3lame",
                        "-ab", f"{bitrate}k",
                        output_file
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    
                    if result.returncode == 0:
                        success_count += 1
                except Exception as e:
                    print(f"Convert error: {e}")
                
                progress.setValue(i + 1)
                QApplication.processEvents()
            
            status_label.setText(f"Done! Converted {success_count} of {len(tracks)} tracks.")
            convert_btn.setEnabled(True)
            convert_btn.setText("Done")
            convert_btn.clicked.disconnect()
            convert_btn.clicked.connect(dialog.accept)
        
        convert_btn.clicked.connect(start_convert)
        
        dialog.exec()
    
    def set_playlist(self, name: str, tracks: list):
        """Set playlist data."""
        self._playlist = tracks
        
        # Clear search
        if hasattr(self, '_search_input'):
            self._search_input.clear()
        
        # Update track count label
        if hasattr(self, '_track_count_label'):
            self._track_count_label.setText(f"{len(tracks)} tracks")
        
        # Calculate duration
        total = sum(t.get('duration', 0) for t in tracks)
        h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
        duration = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
        
        self.header.set_info(name, len(tracks), duration)
        self.table.set_tracks(tracks)
        
        # Update cover art from video thumbnails
        self._update_covers(tracks)
    
    def _update_covers(self, tracks: list):
        """Extract cover art from 1:1 aspect ratio video thumbnails asynchronously."""
        import threading
        
        def run_update():
            import subprocess
            import tempfile
            import json
            import os
            
            if len(tracks) < 1:
                return
            
            # Filter for 1:1 aspect ratio videos
            square_tracks = []
            for track in tracks:
                video_path = track.get('path', '')
                if not video_path or not os.path.exists(video_path):
                    continue
                
                try:
                    # Use ffprobe to get video dimensions
                    result = subprocess.run([
                        'ffprobe', '-v', 'quiet', '-print_format', 'json',
                        '-show_streams', '-select_streams', 'v:0', video_path
                    ], capture_output=True, text=True, timeout=3,
                       creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if data.get('streams'):
                            stream = data['streams'][0]
                            width = stream.get('width', 0)
                            height = stream.get('height', 0)
                            
                            # Check if aspect ratio is 1:1 (square)
                            if width > 0 and height > 0 and abs(width - height) < 10:
                                square_tracks.append(track)
                                if len(square_tracks) >= 2:
                                    break
                except Exception:
                    continue
            
            if len(square_tracks) < 1:
                return
            
            # Extract thumbnails from square videos
            cover_paths = []
            for track in square_tracks[:2]:
                video_path = track.get('path', '')
                
                try:
                    # Create temp file for thumbnail
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        thumb_path = tmp.name
                    
                    # Extract frame at 5 seconds
                    subprocess.run([
                        'ffmpeg', '-ss', '5', '-i', video_path,
                        '-vframes', '1', '-q:v', '2', '-y', thumb_path
                    ], capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    
                    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                        cover_paths.append(thumb_path)
                except Exception as e:
                    print(f"[Cover] Failed to extract thumbnail: {e}")
                    continue
            
            # Set covers if we got any - back to main thread
            from PySide6.QtCore import QTimer
            if len(cover_paths) >= 2:
                QTimer.singleShot(0, lambda: self.header.set_covers(cover_paths[0], cover_paths[1]) if hasattr(self, 'header') else None)
            elif len(cover_paths) == 1:
                QTimer.singleShot(0, lambda: self.header.set_covers(cover_paths[0], cover_paths[0]) if hasattr(self, 'header') else None)

        threading.Thread(target=run_update, daemon=True).start()
    
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

                try:
                    if hasattr(self, 'video_player'):
                        self.video_player.clear_subtitles()
                except Exception:
                    pass

                self._player.setSource(QUrl.fromLocalFile(path))
                self._set_current_media_local_path(path)
                self._maybe_auto_load_sidecar_subtitles(path)
                self._player.play()

                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, self._auto_pick_embedded_subtitles_if_available)
                except Exception:
                    pass
                # Clear flag after a short delay to allow state to settle
                from PySide6.QtCore import QTimer
                QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
                self._save_state()
                
                # Update Discord Rich Presence
                self._update_discord(title, artist, is_playing=True)
            else:
                print(f"File not found: {path}")
    
    def _toggle_play(self):
        # VLC overlay toggle intercept
        if getattr(self, '_playing_vlc', False) and hasattr(self, '_vlc_player') and self._vlc_player:
            import vlc
            state = self._vlc_player.get_state()
            if state == vlc.State.Playing:
                self._vlc_player.pause()
            else:
                self._vlc_player.play()
            return
            
        from PySide6.QtMultimedia import QMediaPlayer
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
        
        # Shuffle: pick random track (excluding current)
        if is_shuffled:
            import random
            if len(self._playlist) > 1:
                available = [i for i in range(len(self._playlist)) if i != self._current_index]
                new_idx = random.choice(available)
            else:
                new_idx = 0
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
        
        # Shuffle: pick random track (excluding current)
        if is_shuffled:
            import random
            if len(self._playlist) > 1:
                available = [i for i in range(len(self._playlist)) if i != self._current_index]
                new_idx = random.choice(available)
            else:
                new_idx = 0
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
        if getattr(self, '_playing_vlc', False) and hasattr(self, '_vlc_player') and self._vlc_player:
            dur = self._vlc_player.get_length()
            if dur > 0:
                self._vlc_player.set_time(int(percent * dur))
            return
            
        if self._player.duration() > 0:
            self._player.setPosition(int(percent * self._player.duration()))
    
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
        
        # VLC overlay volume sync intercept
        if getattr(self, '_playing_vlc', False) and hasattr(self, '_vlc_player') and self._vlc_player:
            # Set VLC volume (0-100+)
            vlc_vol = max(0, min(200, int(volume * 100)))
            self._vlc_player.audio_set_volume(vlc_vol)
    

    def _show_load_url_dialog(self):
        """Show input dialog for stream URL."""
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Open Stream", "Enter stream URL (YouTube, SoundCloud, etc.):")
        if ok and url.strip():
            url = url.strip()
            
            # --- Fast Path ---
            # Attempt to resolve single URLs instantly via oEmbed 
            # (under ~200ms) to avoid all "dummy track" visual glitches.
            import urllib.request
            import urllib.parse
            import json
            import ssl
            
            initial_title = None
            initial_artist = None
            
            try:
                is_fast_path = False
                # Narrow down to single-track candidates and bypass playlists
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
                pass # Proceed silently to dummy track
            
            needs_background_fetch = False
            
            if initial_title:
                # Fast path resolved instantly, we have the full identity
                track = {
                    'path': url,
                    'original_url': url,
                    'title': initial_title,
                    'artist': initial_artist or 'Unknown',
                    'duration': 0,
                    'has_video': True,
                    'is_online': True,
                    'mtime': 0,
                }
            else:
                # Fallback to the dummy track logic while yt-dlp computes
                track = {
                    'path': url,
                    'original_url': url,
                    'title': 'Resolving link...',
                    'artist': url,
                    'duration': 0,
                    'has_video': False,
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
                
            # Render track onto the UI immediately
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
            import subprocess
            import json
            import os
            
            try:
                import yt_dlp
                main_py = os.path.join(os.path.dirname(yt_dlp.__file__), '__main__.py')
            except ImportError as e:
                print(f"yt-dlp core module missing entirely: {e}")
                return
            
            cmd = [
                sys.executable, main_py,
                '--dump-json',
                '--extract-flat',
                '--quiet',
                '--no-warnings',
                '--playlist-end', '50',
                '--socket-timeout', '10',
                '--no-check-certificate',
                '--extractor-args', 'youtube:player_client=android',
                url
            ]
            
            try:
                startupinfo = None
                if sys.platform == 'win32':
                    from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
                    startupinfo = STARTUPINFO()
                    startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                    
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=25, startupinfo=startupinfo)
                if result.returncode == 0 and result.stdout:
                    # yt-dlp with extract_flat might print multiple JSON objects for playlists
                    tracks_to_add = []
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if not line.strip(): continue
                        try:
                            info = json.loads(line)
                            
                            # Flattening logic depending on if it's a playlist container or entries
                            if 'entries' in info and info['entries']:
                                for idx, entry in enumerate(info['entries']):
                                    if entry:
                                        tracks_to_add.append({
                                            'path': entry.get('url', ''),
                                            'original_url': entry.get('url', ''),
                                            'title': entry.get('title', f"Stream {idx+1}"),
                                            'artist': entry.get('uploader', info.get('uploader', 'Unknown')),
                                            'duration': entry.get('duration') or 0,
                                            'has_video': False,
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
                                    'has_video': True,
                                    'is_online': True,
                                    'mtime': 0,
                                })
                        except json.JSONDecodeError:
                            continue
                        
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
                else:
                    raise Exception(result.stderr)
            except Exception as e:
                print(f"Failed to fetch metadata (yt-dlp shell): {e}")
                if dummy_track:
                    dummy_track['title'] = 'Failed to load stream'
                    dummy_track['artist'] = ''
                    dummy_track.pop('dummy', None)
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.table._render_tracks() if hasattr(self, 'table') else None)
                
        threading.Thread(target=fetch, daemon=True).start()
        
    def _load_and_play_stream(self, track):
        """Fetch the direct stream URL and play it."""
        import threading
        self.player_bar.set_track_info(f"Loading {track.get('title', 'Stream')}...", track.get('artist', ''))
        
        def fetch():
            import sys
            import subprocess
            import json
            import os
            
            url = track.get('original_url', track.get('path', ''))
            # Capture tracking ticket BEFORE we go into heavy shell blocking
            request_id = getattr(self, '_stream_request_id', 0)
            
            try:
                import yt_dlp
                main_py = os.path.join(os.path.dirname(yt_dlp.__file__), '__main__.py')
            except ImportError as e:
                print(f"yt-dlp core module missing entirely: {e}")
                return
            
            cmd = [
                sys.executable, main_py,
                '--dump-json',
                '-f', '18/best[ext=mp4][height<=360]/bestaudio/best',
                '--no-playlist',
                '--quiet',
                '--no-warnings',
                '--socket-timeout', '10',
                '--no-check-certificate',
                '--extractor-args', 'youtube:player_client=android',
                url
            ]
            
            try:
                startupinfo = None
                if sys.platform == 'win32':
                    from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
                    startupinfo = STARTUPINFO()
                    startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                    
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=25, startupinfo=startupinfo)
                if result.returncode == 0 and result.stdout:
                    info = json.loads(result.stdout)
                    stream_url = info.get('url')
                    
                    if stream_url:
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: self._play_resolved_stream(stream_url, track, request_id))
                    else:
                        print(f"Failed to extract stream url for {url}")
                        self._revert_loading_ui(track, request_id)
                else:
                    print(f"yt-dlp shell error: {result.stderr}")
                    self._revert_loading_ui(track, request_id)
            except Exception as e:
                print(f"yt-dlp fetch error: {e}")
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
        
    def _play_resolved_stream(self, stream_url, track, request_id):
        """Play the resolved direct stream URL with native VLC backend."""
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
        
        try:
            # We strictly enforce VLC for seamless HTTP livestream processing
            import vlc
            if not hasattr(self, '_vlc_instance') or self._vlc_instance is None:
                self._vlc_instance = vlc.Instance('--no-video', '--network-caching=500', '--http-reconnect', '--http-forward-cookies')
                self._vlc_player = self._vlc_instance.media_player_new()
                
                self._vlc_timer = QTimer(self)
                def poll_vlc():
                    if getattr(self, '_playing_vlc', False) and self._vlc_player:
                        state = self._vlc_player.get_state()
                        
                        # Monitor EOF
                        if state in (vlc.State.Ended, vlc.State.Stopped):
                            self._playing_vlc = False
                            self._vlc_timer.stop()
                            from PySide6.QtMultimedia import QMediaPlayer
                            self._on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
                            return
                            
                        # Monitor and update UI ticks when running flawlessly
                        if state == vlc.State.Playing:
                            # Verify volume mirroring matches parent widget
                            vol = max(0, min(200, int(getattr(self, '_user_volume', 1.0) * 100)))
                            if self._vlc_player.audio_get_volume() != vol:
                                self._vlc_player.audio_set_volume(vol)
                            
                            pos = self._vlc_player.get_time()
                            dur = self._vlc_player.get_length()
                            if pos >= 0:
                                self.player_bar.update_time(pos)
                            if dur > 0:
                                self.player_bar.update_duration(dur)
                                
                self._vlc_timer.timeout.connect(poll_vlc)
                
            self._player.stop() # Abort WMF module entirely
            self._playing_vlc = True
            
            media = self._vlc_instance.media_new(stream_url)
            self._vlc_player.set_media(media)
            self._vlc_player.play()
            self._vlc_timer.start(500)
            
        except Exception as e:
            print(f"VLC unavailable or failed ({e}), falling back to QMediaPlayer")
            self._player.setSource(QUrl(stream_url))
            self._set_current_media_url(stream_url)
            self._player.play()
            
        QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
        self._save_state()
        self._update_discord(title, artist, is_playing=True)
        artist = track.get('artist', '')
        
        print(f"Playing resolved stream: {title}")
        
        # Update track info since we might have better data now
        self.player_bar.set_track_info(title, artist)
        self.table.highlight_playing(self._current_index)
        
        self._switching_track = True
        self._player.setSource(QUrl(stream_url))
        self._set_current_media_url(stream_url)
        self._player.play()
        
        QTimer.singleShot(200, lambda: setattr(self, '_switching_track', False))
        self._save_state()
        self._update_discord(title, artist, is_playing=True)
    
    def _toggle_window_fullscreen(self, is_fullscreen: bool):
        """Toggle main window fullscreen when video player requests it.
        
        Preserves the main window's prior fullscreen state so that exiting
        video fullscreen does not accidentally exit the software's own
        fullscreen mode.
        """
        self._is_fullscreen = is_fullscreen
        
        # Find the top-level window (main launcher window)
        main_window = self.window()
        
        if is_fullscreen:
            # Remember whether the main window was already fullscreen
            # before the video requested fullscreen, so we can restore
            # the correct state on exit
            self._was_window_fullscreen_before_video = main_window.isFullScreen()
            
            # Store original window state for restoration
            self._original_window_flags = main_window.windowFlags()
            self._original_geometry = main_window.geometry()
            
            # Hide menu bar
            if hasattr(self, 'menu_bar'):
                self.menu_bar.hide()
            
            # Hide sidebar in launcher if available
            if hasattr(main_window, 'sidebar'):
                main_window.sidebar.hide()
            
            # Go fullscreen
            main_window.showFullScreen()
            
            try:
                self._set_playerbar_overlay_enabled(True)
            except Exception:
                pass

            # Hide PlayerBar initially in fullscreen (will show on hover)
            self.player_bar.hide()
        else:
            # Restore to the correct window state:
            # If the software was already fullscreen before the video
            # fullscreen, keep it fullscreen. Otherwise go back to normal.
            if getattr(self, '_was_window_fullscreen_before_video', False):
                main_window.showFullScreen()
            else:
                main_window.showNormal()
            
            # Show menu bar
            if hasattr(self, 'menu_bar'):
                self.menu_bar.show()
            
            # Show sidebar in launcher if available
            if hasattr(main_window, 'sidebar'):
                main_window.sidebar.show()
            
            # Show PlayerBar
            try:
                self._set_playerbar_overlay_enabled(False)
            except Exception:
                pass
            self.player_bar.show()

    def _set_playerbar_overlay_enabled(self, enabled: bool):
        try:
            enabled = bool(enabled)
        except Exception:
            enabled = False

        if enabled == getattr(self, '_playerbar_overlay_enabled', False):
            return
        self._playerbar_overlay_enabled = enabled

        if enabled:
            # Remove reserved layout space and move PlayerBar into a top-level overlay.
            # QVideoWidget is a native surface and often cannot be reliably overlaid
            # by normal child widgets.
            try:
                if hasattr(self, '_player_bar_container'):
                    self._player_bar_container.hide()
            except Exception:
                pass

            try:
                if not hasattr(self, '_playerbar_overlay_window') or self._playerbar_overlay_window is None:
                    self._playerbar_overlay_window = _PlayerBarOverlayWindow()
                self._playerbar_overlay_window.set_bar(self.player_bar)
                self._playerbar_overlay_window.show()
                self._update_playerbar_overlay_geometry()
            except Exception:
                pass
            return

        # Restore to normal layout container.
        try:
            try:
                if hasattr(self, '_playerbar_overlay_window') and self._playerbar_overlay_window is not None:
                    self._playerbar_overlay_window.hide()
            except Exception:
                pass

            self.player_bar.setParent(self._player_bar_container)
            try:
                lay = self._player_bar_container.layout()
                if lay is not None:
                    lay.addWidget(self.player_bar)
            except Exception:
                pass
            self.player_bar.show()
        except Exception:
            pass

        try:
            if hasattr(self, '_player_bar_container'):
                self._player_bar_container.show()
        except Exception:
            pass

    def _update_playerbar_overlay_geometry(self):
        try:
            if not getattr(self, '_playerbar_overlay_enabled', False):
                return
            if not hasattr(self, 'video_player') or self.video_player is None:
                return

            if not hasattr(self, '_playerbar_overlay_window') or self._playerbar_overlay_window is None:
                return

            vw = None
            try:
                vw = getattr(self.video_player, 'video_widget', None)
            except Exception:
                vw = None
            if vw is None:
                return

            # Position overlay window aligned to the video surface in global coords.
            try:
                from PySide6.QtCore import QPoint
                gp = vw.mapToGlobal(QPoint(0, 0))
                w = vw.width()
                h = vw.height()
            except Exception:
                return

            bar_h = self.player_bar.height() if self.player_bar.height() > 0 else 75
            self._playerbar_overlay_window.setGeometry(int(gp.x()), int(gp.y() + max(0, h - bar_h)), int(max(1, w)), int(bar_h))
            try:
                self._playerbar_overlay_window.raise_()
            except Exception:
                pass
        except Exception:
            pass
    
    def _toggle_video(self):
        """Switch between playlist view and video view."""
        self._video_mode = not self._video_mode

        if self._video_mode:
            try:
                self._video_mode_restore_pending = False
            except Exception:
                pass

            if not self._is_app_render_allowed() or not getattr(self, '_helxaic_page_visible', True):
                self._disable_video_output_and_subtitles('render_gate_block', switch_to_playlist=False)
                self.stack.setCurrentIndex(1)
                return

            # Switch UI immediately for responsiveness, then do heavier work async.
            self.stack.setCurrentIndex(1)

            def _finish_enter_video_view():
                try:
                    self._player.setVideoOutput(self.video_player.video_widget)
                except Exception:
                    pass

                try:
                    self.video_player.set_render_suspended(False)
                except Exception:
                    pass

                try:
                    if not getattr(self, '_subtitle_appearance_applied_once', False):
                        self._apply_saved_subtitle_appearance()
                        self._subtitle_appearance_applied_once = True
                except Exception:
                    pass

                # RTSS exclusion is expensive (file IO). Do it once per run.
                try:
                    if not getattr(self, '_rtss_excluded_once', False):
                        import sys as _sys
                        _lm = _sys.modules.get('__main__') or _sys.modules.get('launcher')
                        if _lm and hasattr(_lm, '_exclude_from_rtss'):
                            _lm._exclude_from_rtss()
                        self._rtss_excluded_once = True
                except Exception:
                    pass

                try:
                    if 0 <= self._current_index < len(self._playlist):
                        track = self._playlist[self._current_index]
                        self.video_player.set_title(track.get('title', 'Now Playing'))
                except Exception:
                    pass

                # Embedded subtitle probing can be slow (ffprobe). Only do it if the media changed.
                try:
                    cur = None
                    try:
                        cur = self._player.source().toString() if self._player.source() else None
                    except Exception:
                        cur = None

                    if cur and cur != getattr(self, '_last_media_for_sub_auto_pick', None):
                        self._last_media_for_sub_auto_pick = cur
                        QTimer.singleShot(0, self._auto_pick_embedded_subtitles_if_available)
                except Exception:
                    pass

            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, _finish_enter_video_view)
            except Exception:
                _finish_enter_video_view()
            return

        # Leaving video view
        try:
            self._player.setVideoOutput(None)
        except Exception:
            pass

        try:
            self.video_player.set_render_suspended(True)
        except Exception:
            pass

        self.stack.setCurrentIndex(0)

    def _switch_to_playlist(self):
        """Switch back to playlist view (from video player back button)."""
        self._video_mode = False
        try:
            self._player.setVideoOutput(None)
        except Exception:
            pass
        try:
            self.video_player.set_render_suspended(True)
        except Exception:
            pass
        self.stack.setCurrentIndex(0)

    def _set_aspect_ratio(self, mode: str):
        """Set video aspect ratio mode: fill, fit, or stretch."""
        self._current_aspect_ratio = mode
        
        # Update checkmarks
        self.action_aspect_fill.setChecked(mode == "fill")
        self.action_aspect_fit.setChecked(mode == "fit")
        self.action_aspect_stretch.setChecked(mode == "stretch")
        
        # Apply to video widget
        if mode == "fill":
            self.video_player.video_widget.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        elif mode == "fit":
            self.video_player.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        elif mode == "stretch":
            self.video_player.video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)
        
        # Save state when changed
        if hasattr(self, '_config_path'):
            # Use QTimer to avoid rapid multiple saves if called repeatedly
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._save_state)
            
        print(f"Aspect ratio set to: {mode}")

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode for video player.
        
        Preserves the main window's prior fullscreen state so that
        exiting video fullscreen does not accidentally exit the
        software's own fullscreen mode (e.g. when the user pressed
        F11 before entering video fullscreen).
        """
        # Don't allow fullscreen if no track is playing
        if self._current_index < 0 or not self._playlist:
            return
        
        if not hasattr(self, '_is_fullscreen'):
            self._is_fullscreen = False
        
        self._is_fullscreen = not self._is_fullscreen
        
        # Get parent window and sidebar
        parent_window = self.window()
        sidebar = parent_window.findChild(QWidget, "sidebarNav") if parent_window else None
        
        if self._is_fullscreen:
            # Remember whether the main window was already fullscreen
            # BEFORE we enter video fullscreen so we can restore later
            self._was_window_fullscreen_before_video = (
                parent_window.isFullScreen() if parent_window else False
            )
            
            # Switch to video view if not already
            if not self._video_mode:
                self._toggle_video()
            
            # Hide UI elements
            if sidebar:
                sidebar.hide()
            if hasattr(self, '_menu_bar_widget'):
                self._menu_bar_widget.hide()
            self.player_bar.hide()
            
            # Enable mouse tracking for playerbar show on hover
            self.setMouseTracking(True)
            self.video_player.setMouseTracking(True)
            self.video_player.video_widget.setMouseTracking(True)
            self.stack.setMouseTracking(True)
            if parent_window:
                parent_window.setMouseTracking(True)
            
            # Create hide timer if not exists
            if not hasattr(self, '_playerbar_hide_timer'):
                self._playerbar_hide_timer = QTimer()
                self._playerbar_hide_timer.timeout.connect(self._hide_playerbar_fullscreen)
                self._playerbar_hide_timer.setSingleShot(True)
            
            # Go fullscreen
            if parent_window:
                self._original_geometry = parent_window.geometry()
                parent_window.showFullScreen()
                
                # Install event filter on parent window and video widget for key/mouse events
                parent_window.installEventFilter(self)
                self.video_player.video_widget.installEventFilter(self)
                
                # Set focus to self for keyboard input
                self.setFocus()
            
            print("Fullscreen: ON")
        else:
            # Show UI elements
            if sidebar:
                sidebar.show()
            if hasattr(self, '_menu_bar_widget'):
                self._menu_bar_widget.show()
            self.player_bar.show()
            
            # Stop hide timer
            if hasattr(self, '_playerbar_hide_timer'):
                self._playerbar_hide_timer.stop()
            
            # Restore window to its previous state
            if parent_window:
                # Remove event filters
                parent_window.removeEventFilter(self)
                self.video_player.video_widget.removeEventFilter(self)
                
                # If the software was already fullscreen before video
                # fullscreen, keep it fullscreen. Otherwise restore
                # the original geometry (normal/windowed mode).
                if getattr(self, '_was_window_fullscreen_before_video', False):
                    parent_window.showFullScreen()
                else:
                    parent_window.showNormal()
                    if hasattr(self, '_original_geometry'):
                        parent_window.setGeometry(self._original_geometry)
            
            print("Fullscreen: OFF")
    
    def eventFilter(self, obj, event):
        """Event filter for fullscreen key and mouse events."""
        from PySide6.QtCore import QEvent
        
        # Handle double-click to toggle fullscreen (works in both fullscreen and normal mode)
        if event.type() == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                try:
                    if getattr(self, '_video_mode', False) and hasattr(self, 'video_player') and self.video_player is not None:
                        self.video_player._toggle_fullscreen()
                    else:
                        self._toggle_fullscreen()
                except Exception:
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
                        if getattr(self, '_video_mode', False) and hasattr(self, 'video_player') and self.video_player is not None:
                            self.video_player._toggle_fullscreen()
                        else:
                            self._toggle_fullscreen()
                    except Exception:
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
    
    def _hide_playerbar_fullscreen(self):
        """Hide player bar in fullscreen mode with slide-down animation."""
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            # Animate slide down
            self._animate_playerbar(show=False)
    
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
    
    
    def _on_position(self, pos: int):
        dur = self._player.duration()
        # Correctly check the dragging state of the timeline slider from the player bar
        is_dragging = getattr(self.player_bar, '_is_dragging_timeline', False)
        self.player_bar.set_position(pos / 1000.0, dur / 1000.0, skip_throttle=is_dragging)
        
        # Track position for save state (player.position() returns 0 when stopped)
        self._last_known_position = pos
        
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
    
    def _on_state(self, state):
        # Ignore StoppedState during track switching to prevent icon flicker
        if state == QMediaPlayer.StoppedState and getattr(self, '_switching_track', False):
            return
        
        self.player_bar.set_playing(state == QMediaPlayer.PlayingState)
        
        # Emit signal for external listeners (e.g., taskbar integration)
        self.playbackStateChanged.emit(state)
        
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
        
        # Save state when playback stops
        if state == QMediaPlayer.StoppedState:
            self._save_state()
    
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
                    
                    # Restore last track
                    last_path = state.get('last_track_path', '')
                    if last_path:
                        # Normalize path for comparison (handle both / and \)
                        last_path_norm = last_path.replace('\\', '/')
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
                                    
                                    # Restore last position after media loads
                                    last_pos = state.get('last_position', 0)
                                    if last_pos > 0:
                                        self._pending_seek_position = last_pos
                                        # Connect once to restore position when media loads
                                        def on_media_loaded(status):
                                            if status == QMediaPlayer.LoadedMedia:
                                                if hasattr(self, '_pending_seek_position') and self._pending_seek_position > 0:
                                                    self._player.setPosition(self._pending_seek_position)
                                                    print(f"Restored position: {self._pending_seek_position / 1000:.1f}s")
                                                    self._pending_seek_position = 0
                                                try:
                                                    self._player.mediaStatusChanged.disconnect(on_media_loaded)
                                                except:
                                                    pass
                                        self._player.mediaStatusChanged.connect(on_media_loaded)
                                
                                print(f"Restored last track: {track.get('title')}")
                                break
                    
                    # Restore volume
                    volume = state.get('volume', 100)
                    self._audio_output.setVolume(volume / 100.0)
                    self.player_bar.volume_slider.setValue(volume)
                    
                    # Restore aspect ratio
                    aspect_ratio = state.get('video_aspect_ratio', 'fit')
                    self._set_aspect_ratio(aspect_ratio)
                    
                    # Restore subtitle preferences
                    self._subtitle_style_preset = state.get('subtitle_style_preset', 'outline')
                    self._subtitle_font_size = state.get('subtitle_font_size', 16)
                    # Apply after video player is available
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, self._apply_saved_subtitle_appearance)
                    
                    print(f"Loaded state: {folder}")
        except Exception as e:
            print(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save current state to config."""
        import json
        try:
            current_track_path = ''
            if 0 <= self._current_index < len(self._playlist):
                current_track_path = self._playlist[self._current_index].get('path', '')
            # Use tracked position (player.position() returns 0 when stopped)
            position = getattr(self, '_last_known_position', 0) or self._player.position()
            print(f"[Music] Saving position: {position}ms (_last_known: {getattr(self, '_last_known_position', 'not set')})")
            
            state = {
                'folder': self._music_folder or '',
                'last_track_path': current_track_path,
                'last_position': position,
                'volume': self.player_bar.volume_slider.value(),
                'video_aspect_ratio': getattr(self, '_current_aspect_ratio', 'fit'),
                'subtitle_style_preset': getattr(self, '_subtitle_style_preset', 'outline'),
                'subtitle_font_size': getattr(self, '_subtitle_font_size', 16)
            }
            
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            
            print(f"Saved state: {current_track_path}")
        except Exception as e:
            print(f"Failed to save state: {e}")
    
    def _browse_folder_direct(self):
        """Quick folder selection from player bar button."""
        from PySide6.QtWidgets import QFileDialog
        
        start = getattr(self, '_music_folder', None) or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Media Folder", start, QFileDialog.ShowDirsOnly
        )
        
        if folder:
            self._music_folder = folder
            self._load_tracks_from_folder(folder)
            # Save immediately so folder is remembered after restart
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
    
    def _load_tracks_from_folder(self, folder: str):
        """Scan folder and load tracks."""
        # Use Python fallback scanner - C++ has encoding issues with special characters
        self._load_tracks_fallback(folder)
    
    def _load_tracks_fallback(self, folder: str):
        """Fallback track loading without C++ extension."""
        import datetime
        import subprocess
        
        audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma'}
        video_exts = {'.mp4', '.mkv', '.avi', '.webm', '.mov'}
        
        tracks = []
        for root, dirs, files in os.walk(folder):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in audio_exts or ext in video_exts:
                    path = os.path.join(root, f)
                    title = os.path.splitext(f)[0]
                    
                    # Get file modified time as date added
                    try:
                        mtime = os.path.getmtime(path)
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
                        'has_video': ext in video_exts,
                        'date_added': date_str
                    })
        
        playlist_name = os.path.basename(folder) + "'s Playlist"
        self.set_playlist(playlist_name, tracks)
        print(f"Loaded {len(tracks)} tracks from {folder} (fallback)")
        
        # Async metadata loading to prevent UI freeze
        def _fetch_metadata(target_tracks, target_name):
            import subprocess
            import shutil
            
            print(f"[Duration] Starting metadata fetch for {len(target_tracks)} tracks")
            
            # Try to import mutagen for fast metadata reading (works for audio files)
            try:
                import mutagen
                has_mutagen = True
                print(f"[Duration] mutagen available")
            except ImportError:
                has_mutagen = False
                print("[Duration] mutagen NOT available")
            
            # Find ffprobe path for fallback (handles MKV, MP4 without tags, etc.)
            ffprobe_path = shutil.which("ffprobe")
            if not ffprobe_path:
                # Check HELXAID's bundled FFmpeg tools
                appdata_tools = os.path.join(
                    os.environ.get("APPDATA", ""), "HELXAID", "tools", "ffmpeg"
                )
                if os.path.isdir(appdata_tools):
                    for root, dirs, fnames in os.walk(appdata_tools):
                        for fn in fnames:
                            if fn.lower() == "ffprobe.exe":
                                ffprobe_path = os.path.join(root, fn)
                                break
                        if ffprobe_path:
                            break
            
            print(f"[Duration] ffprobe path: {ffprobe_path}")
                            
            from PySide6.QtCore import QTimer
            changed = False
            success_count = 0
            fail_count = 0
            
            for t in target_tracks:
                # Stop parsing if playlist was changed/switched
                if getattr(self, '_playlist', None) is not target_tracks:
                    print("[Duration] Playlist changed, aborting")
                    break
                    
                path = t.get('path', '')
                if not os.path.exists(path):
                    continue
                
                dur = 0
                artist = ''
                
                # Step 1: Try mutagen first (fast, works for MP3/FLAC/OGG/some MP4)
                if has_mutagen:
                    try:
                        m = mutagen.File(path)
                        if m is not None and hasattr(m, 'info'):
                            dur = getattr(m.info, 'length', 0)
                            
                            # Try to get artist name for better UX
                            if hasattr(m, 'tags') and m.tags:
                                if 'artist' in m.tags:
                                    val = m.tags['artist']
                                    if isinstance(val, list) and len(val) > 0:
                                        artist = str(val[0])
                                    else:
                                        artist = str(val)
                    except Exception as e:
                        pass
                
                # Step 2: Fallback to ffprobe if mutagen couldn't get duration.
                # This handles MKV, MP4 without metadata tags, WebM, etc.
                # ffprobe is always reliable as it reads container headers directly.
                if dur <= 0 and ffprobe_path:
                    try:
                        result = subprocess.run(
                            [
                                ffprobe_path,
                                "-v", "quiet",
                                "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1",
                                path
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            dur = float(result.stdout.strip())
                    except (subprocess.TimeoutExpired, ValueError, Exception) as e:
                        print(f"[Duration] ffprobe error for {os.path.basename(path)}: {e}")
                
                # Apply results
                if dur > 0:
                    t['duration'] = dur
                    changed = True
                    success_count += 1
                else:
                    fail_count += 1
                if artist:
                    t['artist'] = artist
            
            print(f"[Duration] Fetch complete: {success_count} ok, {fail_count} failed, changed={changed}")
            
            # Update UI on main thread only if changes were made and playlist is still active
            if changed and getattr(self, '_playlist', None) is target_tracks:
                def update_ui():
                    if getattr(self, '_playlist', None) is not target_tracks:
                        return
                    
                    # Update header duration calculation
                    total = sum(tr.get('duration', 0) for tr in target_tracks)
                    h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
                    duration_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                    
                    print(f"[Duration] Updating UI: total={duration_str}")
                    
                    if hasattr(self, 'header') and hasattr(self.header, 'set_info'):
                        self.header.set_info(target_name, len(target_tracks), duration_str)
                        
                    # Refresh table to show updated durations
                    if hasattr(self, 'table') and hasattr(self.table, '_render_tracks'):
                        self.table._render_tracks()
                        
                QTimer.singleShot(0, update_ui)
            else:
                print(f"[Duration] NOT updating UI: changed={changed}, playlist_match={getattr(self, '_playlist', None) is target_tracks}")
                
        import threading
        t = threading.Thread(target=_fetch_metadata, args=(tracks, playlist_name), daemon=True)
        t.start()


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
