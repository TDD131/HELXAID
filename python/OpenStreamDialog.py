"""
OpenStreamDialog.py - HELXAIC Direct Stream Input & Routing Modal
================================================================
Modern Cyberpunk/Dark styled modal for inputting stream URLs, live metadata preview,
and routing destination selection:
- Active Playlist Only (Ephemeral)
- Media Library Only (.hxstream file on disk)
- Both (Save .hxstream file + Add to current playlist)

Component Name: OpenStreamDialog
"""

import os
import json
import urllib.request
import urllib.parse
import ssl
from typing import Optional, Dict, Any, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QRadioButton,
    QButtonGroup, QFrame, QWidget, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QSize
from PySide6.QtGui import QIcon, QPixmap

from StreamFileEngine import sanitize_stream_filename, write_stream_file, STREAM_FILE_EXTENSION


class StreamMetadataWorker(QThread):
    """Background worker for fast oEmbed/metadata resolution without freezing the UI."""
    metadataFound = Signal(dict)
    metadataFailed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = (url or "").strip()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled or not self.url:
            return

        url = self.url
        title = None
        artist = None
        thumbnail_url = None
        duration = 0.0

        try:
            # 1. Fast oEmbed Path for YouTube
            if ('youtube.com' in url or 'youtu.be' in url) and 'playlist?list=' not in url:
                api_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=2.0, context=ctx) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    title = res.get('title')
                    artist = res.get('author_name')
                    thumbnail_url = res.get('thumbnail_url')

            # 2. Fast oEmbed Path for SoundCloud
            elif 'soundcloud.com/' in url and '/sets/' not in url:
                api_url = f"https://soundcloud.com/oembed?url={urllib.parse.quote(url)}&format=json"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=2.0, context=ctx) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    title = res.get('title')
                    artist = res.get('author_name')
                    thumbnail_url = res.get('thumbnail_url')
        except Exception:
            pass

        if self._is_cancelled:
            return

        # If fast path succeeded
        if title:
            self.metadataFound.emit({
                'title': title,
                'artist': artist or 'Unknown Artist',
                'album': 'Online Stream',
                'duration': duration,
                'original_url': url,
                'thumbnail_url': thumbnail_url or '',
                'is_online': True,
                'is_stream': True
            })
            return

        # Fast Canonical & Innertube title search path
        try:
            from CanonicalMetadataEngine import CanonicalSearchEngine
            res = CanonicalSearchEngine.resolve_target(url)
            if self._is_cancelled:
                return
            if res.get('success') and res.get('resolved_url'):
                self.metadataFound.emit({
                    'title': res.get('title', 'Unknown Title'),
                    'artist': res.get('artist', 'Unknown Artist'),
                    'album': res.get('album', 'Online Stream'),
                    'duration': float(res.get('duration', 0)),
                    'original_url': res.get('resolved_url'),
                    'thumbnail_url': res.get('artwork_url', ''),
                    'is_online': True,
                    'is_stream': True
                })
                return
        except Exception as ex:
            print(f"[OpenStream] CanonicalSearchEngine notice: {ex}")

        # Fallback to yt-dlp flat extraction if oEmbed failed
        try:
            import yt_dlp
            ydl_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 4,
                'nocheckcertificate': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if self._is_cancelled or not info:
                    return
                entries = info.get('entries', [])
                if entries:
                    best = entries[0]
                    title = best.get('title')
                    artist = best.get('uploader') or info.get('uploader')
                    duration = best.get('duration') or 0.0
                    thumbnail_url = best.get('thumbnail')
                else:
                    title = info.get('title')
                    artist = info.get('uploader')
                    duration = info.get('duration') or 0.0
                    thumbnail_url = info.get('thumbnail')

            if self._is_cancelled:
                return

            if title:
                self.metadataFound.emit({
                    'title': title,
                    'artist': artist or 'Unknown Artist',
                    'album': 'Online Stream',
                    'duration': duration,
                    'original_url': url,
                    'thumbnail_url': thumbnail_url or '',
                    'is_online': True,
                    'is_stream': True
                })
            else:
                self.metadataFailed.emit("Could not extract stream title")
        except Exception as e:
            if not self._is_cancelled:
                self.metadataFailed.emit(str(e))


class OpenStreamDialog(QDialog):
    """
    Cyberpunk / Dark Modal for Direct Stream Input, Live Preview, and Destination Routing.
    Component Name: OpenStreamDialog
    """
    streamConfirmed = Signal(dict, str, str)  # (track_dict, destination_mode, save_directory)

    def __init__(self, parent=None, default_save_folder: Optional[str] = None, default_mode: str = "both"):
        super().__init__(parent)
        self.setObjectName("OpenStreamDialog")
        self.setWindowTitle("Open Stream - HELXAIC")
        
        try:
            from launcher import apply_custom_titlebar
            apply_custom_titlebar(self, "#0e0f14")
        except Exception:
            pass

        self.setFixedSize(540, 520)
        self.setModal(True)

        self._default_save_folder = default_save_folder or os.path.expanduser("~/Music/Streams")
        self._default_mode = default_mode
        self._resolved_metadata: Optional[Dict[str, Any]] = None
        self._meta_worker: Optional[StreamMetadataWorker] = None
        
        # Debounce timer for URL typing
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(400)
        self._typing_timer.timeout.connect(self._start_metadata_fetch)

        self._init_ui()
        self._apply_styling()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(12)

        # -------------------------------------------------------------
        # Header Section
        # -------------------------------------------------------------
        header_widget = QWidget(self)
        header_widget.setObjectName("streamHeaderWidget")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        # Icon badge
        icon_label = QLabel(header_widget)
        icon_label.setObjectName("streamHeaderIconBadge")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(34, 34)

        icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "stream-signal-icon.svg")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "playlist-icon.svg")
        if os.path.exists(icon_path):
            icon_label.setPixmap(QIcon(icon_path).pixmap(20, 20))

        header_layout.addWidget(icon_label)

        title_container = QVBoxLayout()
        title_container.setSpacing(2)
        
        main_title = QLabel("OPEN DIRECT STREAM", header_widget)
        main_title.setObjectName("streamDialogHeaderTitle")
        
        sub_title = QLabel("STREAM POINTER & ZERO-DOWNLOAD PLAYBACK", header_widget)
        sub_title.setObjectName("streamDialogHeaderSubtitle")
        
        title_container.addWidget(main_title)
        title_container.addWidget(sub_title)
        header_layout.addLayout(title_container)
        header_layout.addStretch()

        root_layout.addWidget(header_widget)

        # -------------------------------------------------------------
        # 1. URL Input Card
        # -------------------------------------------------------------
        url_card = QFrame(self)
        url_card.setObjectName("streamUrlCard")
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(14, 12, 14, 12)
        url_layout.setSpacing(8)

        url_title = QLabel("STREAM TARGET URL", url_card)
        url_title.setObjectName("streamCardHeaderLabel")
        url_layout.addWidget(url_title)

        url_input_row = QHBoxLayout()
        url_input_row.setSpacing(8)

        self.url_input = QLineEdit(url_card)
        self.url_input.setObjectName("streamUrlInput")
        self.url_input.setPlaceholderText("Paste YouTube, SoundCloud, or direct audio stream link...")
        self.url_input.textChanged.connect(self._on_url_text_changed)
        url_input_row.addWidget(self.url_input)

        paste_btn = QPushButton("Paste", url_card)
        paste_btn.setObjectName("streamPasteBtn")
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.setFixedWidth(70)
        paste_btn.clicked.connect(self._on_paste_clicked)
        url_input_row.addWidget(paste_btn)

        url_layout.addLayout(url_input_row)
        root_layout.addWidget(url_card)

        # -------------------------------------------------------------
        # 2. Metadata Preview Card
        # -------------------------------------------------------------
        self.preview_card = QFrame(self)
        self.preview_card.setObjectName("streamPreviewCard")
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(14, 10, 14, 10)
        preview_layout.setSpacing(4)

        self.preview_title = QLabel("Waiting for stream link...", self.preview_card)
        self.preview_title.setObjectName("streamPreviewTitle")

        self.preview_artist = QLabel("Enter a valid URL above to preview track details", self.preview_card)
        self.preview_artist.setObjectName("streamPreviewArtist")

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_artist)
        root_layout.addWidget(self.preview_card)

        # -------------------------------------------------------------
        # 3. Destination Routing Card
        # -------------------------------------------------------------
        dest_card = QFrame(self)
        dest_card.setObjectName("streamDestinationCard")
        dest_layout = QVBoxLayout(dest_card)
        dest_layout.setContentsMargins(14, 12, 14, 12)
        dest_layout.setSpacing(10)

        dest_title = QLabel("AUTO-SAVE & PLAYLIST ROUTING", dest_card)
        dest_title.setObjectName("streamCardHeaderLabel")
        dest_layout.addWidget(dest_title)

        self._btn_group = QButtonGroup(self)

        self.radio_both = QRadioButton("Save to Library & Add to Active Playlist (Recommended)", dest_card)
        self.radio_both.setObjectName("radioDestBoth")
        self._btn_group.addButton(self.radio_both, 0)

        self.radio_playlist = QRadioButton("Active Playlist Only (Ephemeral / No File)", dest_card)
        self.radio_playlist.setObjectName("radioDestPlaylist")
        self._btn_group.addButton(self.radio_playlist, 1)

        self.radio_library = QRadioButton("Media Library Only (Create .hxstream File)", dest_card)
        self.radio_library.setObjectName("radioDestLibrary")
        self._btn_group.addButton(self.radio_library, 2)

        if self._default_mode == "playlist":
            self.radio_playlist.setChecked(True)
        elif self._default_mode == "library":
            self.radio_library.setChecked(True)
        else:
            self.radio_both.setChecked(True)

        self.radio_both.toggled.connect(self._on_dest_toggled)
        self.radio_library.toggled.connect(self._on_dest_toggled)
        self.radio_playlist.toggled.connect(self._on_dest_toggled)

        dest_layout.addWidget(self.radio_both)
        dest_layout.addWidget(self.radio_playlist)
        dest_layout.addWidget(self.radio_library)

        # Folder selector row
        self.folder_container = QWidget(dest_card)
        self.folder_container.setObjectName("streamFolderContainer")
        folder_layout = QHBoxLayout(self.folder_container)
        folder_layout.setContentsMargins(0, 4, 0, 0)
        folder_layout.setSpacing(8)

        self.folder_input = QLineEdit(self.folder_container)
        self.folder_input.setObjectName("streamFolderInput")
        self.folder_input.setText(self._default_save_folder)
        self.folder_input.setReadOnly(True)
        folder_layout.addWidget(self.folder_input)

        browse_btn = QPushButton("Browse...", self.folder_container)
        browse_btn.setObjectName("streamBrowseFolderBtn")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._on_browse_folder)
        folder_layout.addWidget(browse_btn)

        dest_layout.addWidget(self.folder_container)
        root_layout.addWidget(dest_card)

        # -------------------------------------------------------------
        # 4. Action Buttons Row
        # -------------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("CANCEL", self)
        self.cancel_btn.setObjectName("streamCancelBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.add_btn = QPushButton("ADD STREAM", self)
        self.add_btn.setObjectName("streamAddBtn")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self.add_btn)

        root_layout.addLayout(btn_row)

    def _apply_styling(self):
        self.setStyleSheet("""
            QDialog#OpenStreamDialog {
                background-color: #121318;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel {
                font-family: 'Orbitron', sans-serif;
                color: #e0e0e0;
            }
            QLabel#streamHeaderIconBadge {
                background-color: rgba(255, 91, 6, 0.12);
                border-radius: 8px;
            }
            QLabel#streamDialogHeaderTitle {
                font-size: 15px;
                font-weight: bold;
                color: #FFFFFF;
                letter-spacing: 1px;
            }
            QLabel#streamDialogHeaderSubtitle {
                font-size: 10px;
                color: #888892;
                letter-spacing: 0.5px;
            }
            QFrame#streamUrlCard, QFrame#streamPreviewCard, QFrame#streamDestinationCard {
                background-color: #181920;
                border-radius: 10px;
            }
            QLabel#streamCardHeaderLabel {
                font-size: 11px;
                font-weight: bold;
                color: #FF5B06;
                letter-spacing: 0.8px;
            }
            QLineEdit#streamUrlInput, QLineEdit#streamFolderInput {
                background-color: #20222a;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                color: #ffffff;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                padding: 8px 12px;
            }
            QLineEdit#streamUrlInput:focus {
                background-color: #262832;
                border: 1px solid #FF5B06;
            }
            QPushButton#streamPasteBtn, QPushButton#streamBrowseFolderBtn {
                background-color: #242630;
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton#streamPasteBtn:hover, QPushButton#streamBrowseFolderBtn:hover {
                background-color: rgba(255, 91, 6, 0.25);
                color: #ffffff;
            }
            QLabel#streamPreviewTitle {
                font-size: 12px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#streamPreviewArtist {
                font-size: 11px;
                color: #9da0aa;
            }
            QRadioButton {
                font-family: 'Orbitron', sans-serif;
                color: #d0d2dc;
                font-size: 11px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background-color: #20222a;
            }
            QRadioButton::indicator:checked {
                background-color: #FF5B06;
                border: 1px solid #FF7A2E;
            }
            QPushButton#streamCancelBtn {
                background-color: #20222a;
                color: #a0a2ac;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 22px;
            }
            QPushButton#streamCancelBtn:hover {
                background-color: #282a34;
                color: #ffffff;
            }
            QPushButton#streamAddBtn {
                background-color: #FF5B06;
                color: #ffffff;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 26px;
                letter-spacing: 0.5px;
            }
            QPushButton#streamAddBtn:hover {
                background-color: #ff7026;
            }
            QPushButton#streamAddBtn:pressed {
                background-color: #e04a00;
            }
        """)

    def _on_url_text_changed(self, text: str):
        url = text.strip()
        if not url:
            self.preview_title.setText("Waiting for stream link...")
            self.preview_artist.setText("Enter a valid URL above to preview track details")
            self._resolved_metadata = None
            return

        self.preview_title.setText("Resolving stream information...")
        self.preview_artist.setText("Fetching metadata...")
        self._typing_timer.start()

    def _on_paste_clicked(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self._start_metadata_fetch()

    def _start_metadata_fetch(self):
        url = self.url_input.text().strip()
        if not url:
            return

        if self._meta_worker and self._meta_worker.isRunning():
            self._meta_worker.cancel()
            self._meta_worker.wait(100)

        self._meta_worker = StreamMetadataWorker(url, parent=self)
        self._meta_worker.metadataFound.connect(self._on_metadata_found)
        self._meta_worker.metadataFailed.connect(self._on_metadata_failed)
        self._meta_worker.start()

    def _on_metadata_found(self, meta: Dict[str, Any]):
        self._resolved_metadata = meta
        title = meta.get('title', 'Unknown Stream')
        artist = meta.get('artist', 'Unknown Artist')
        dur = meta.get('duration', 0)
        
        dur_str = ""
        if dur > 0:
            m, s = divmod(int(dur), 60)
            dur_str = f" • {m}:{s:02d}"

        self.preview_title.setText(title)
        self.preview_artist.setText(f"{artist}{dur_str} • Direct Stream")

    def _on_metadata_failed(self, error: str):
        url = self.url_input.text().strip()
        self.preview_title.setText("Direct Stream")
        self.preview_artist.setText(f"Target: {url[:45]}..." if len(url) > 45 else f"Target: {url}")
        self._resolved_metadata = {
            'title': 'Direct Stream',
            'artist': url,
            'album': 'Online Stream',
            'duration': 0.0,
            'original_url': url,
            'is_online': True,
            'is_stream': True
        }

    def _on_dest_toggled(self):
        is_saving_file = self.radio_both.isChecked() or self.radio_library.isChecked()
        self.folder_container.setEnabled(is_saving_file)

    def _on_browse_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Stream Save Folder", self.folder_input.text())
        if chosen:
            self.folder_input.setText(chosen)

    def _on_submit(self):
        url = self.url_input.text().strip()
        if not url:
            return

        if not self._resolved_metadata:
            self._resolved_metadata = {
                'title': 'Direct Stream',
                'artist': url,
                'album': 'Online Stream',
                'duration': 0.0,
                'original_url': url,
                'is_online': True,
                'is_stream': True
            }

        mode = "both"
        if self.radio_playlist.isChecked():
            mode = "playlist"
        elif self.radio_library.isChecked():
            mode = "library"

        save_dir = self.folder_input.text().strip() or self._default_save_folder

        # If saving to disk (mode is 'both' or 'library')
        if mode in ("both", "library"):
            created_path = write_stream_file(save_dir, self._resolved_metadata, format_ext=STREAM_FILE_EXTENSION)
            if created_path:
                self._resolved_metadata['path'] = created_path
                self._resolved_metadata['is_stream_file'] = True

        self.streamConfirmed.emit(self._resolved_metadata, mode, save_dir)
        self.accept()

    def get_result(self) -> Optional[Tuple[Dict[str, Any], str, str]]:
        if self.result() == QDialog.Accepted and self._resolved_metadata:
            mode = "both"
            if self.radio_playlist.isChecked():
                mode = "playlist"
            elif self.radio_library.isChecked():
                mode = "library"
            save_dir = self.folder_input.text().strip() or self._default_save_folder
            return self._resolved_metadata, mode, save_dir
        return None
