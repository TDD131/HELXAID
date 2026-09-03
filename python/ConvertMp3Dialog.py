import os
import re
import subprocess
import shutil
from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QProgressBar,
    QRadioButton, QButtonGroup, QSpinBox, QFrame,
    QWidget, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon


def sanitize_filename(filename: str) -> str:
    """Sanitize string for Windows filename compatibility."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", filename)
    cleaned = cleaned.strip(" .")
    return cleaned or "converted_track"


def resolve_ffmpeg_path() -> Optional[str]:
    """Find FFmpeg binary in AppData or system PATH."""
    try:
        from integrations.tools_downloader import get_ffmpeg_path, is_ffmpeg_available
        if is_ffmpeg_available():
            p = get_ffmpeg_path()
            if os.path.exists(p):
                return p
            # Check FFMPEG_DIR directly
            appdata = os.environ.get('APPDATA', '')
            direct = os.path.join(appdata, 'HELXAID', 'tools', 'ffmpeg', 'ffmpeg.exe')
            if os.path.exists(direct):
                return direct
    except Exception:
        pass

    # Check AppData fallback
    try:
        appdata = os.environ.get('APPDATA', '')
        p = os.path.join(appdata, 'HELXAID', 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
        if os.path.exists(p):
            return p
    except Exception:
        pass

    # Check system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    return "ffmpeg"


class ConvertMp3Worker(QThread):
    """
    Background worker thread for asynchronous MP3 audio conversion using FFmpeg.
    
    Component Name: ConvertMp3Worker
    """
    progressChanged = Signal(int, int, str, float)  # current, total, filename, percentage
    statusMessage = Signal(str)
    fileCompleted = Signal(str, str, bool, str)  # input_path, output_path, success, message
    conversionComplete = Signal(int, int, int, list)  # success_count, failed_count, skipped_count, errors

    def __init__(self, tracks: List[Dict], output_dir: str, bitrate: int = 320, parent=None):
        super().__init__(parent)
        self.setObjectName("ConvertMp3Worker")
        self._tracks = tracks
        self._output_dir = output_dir
        self._bitrate = bitrate
        self._is_cancelled = False
        self._current_proc: Optional[subprocess.Popen] = None
        self._current_output_file: Optional[str] = None

    def cancel(self):
        """Request cancellation of conversion process."""
        self._is_cancelled = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        # Clean up partial output file if any
        if self._current_output_file and os.path.exists(self._current_output_file):
            try:
                os.remove(self._current_output_file)
            except Exception:
                pass

    def run(self):
        ffmpeg_bin = resolve_ffmpeg_path()
        total = len(self._tracks)
        success_count = 0
        failed_count = 0
        skipped_count = 0
        error_logs = []

        if not os.path.exists(self._output_dir):
            try:
                os.makedirs(self._output_dir, exist_ok=True)
            except Exception as e:
                self.statusMessage.emit(f"Failed to create output directory: {e}")
                self.conversionComplete.emit(0, total, 0, [str(e)])
                return

        for i, track in enumerate(self._tracks):
            if self._is_cancelled:
                self.statusMessage.emit("Conversion cancelled by user.")
                break

            input_path = track.get('path', '')
            track_title = track.get('title') or os.path.basename(input_path) or f"Track_{i+1}"
            
            pct = ((i) / total) * 100 if total > 0 else 0
            self.progressChanged.emit(i, total, track_title, pct)

            if not input_path or not os.path.exists(input_path):
                failed_count += 1
                err = f"File not found: {input_path}"
                error_logs.append(err)
                self.fileCompleted.emit(input_path, "", False, err)
                continue

            # Check if source is already MP3
            if input_path.lower().endswith(".mp3"):
                skipped_count += 1
                self.statusMessage.emit(f"Skipped (already MP3): {track_title}")
                self.fileCompleted.emit(input_path, input_path, True, "Already MP3")
                continue

            # Build destination filename
            clean_name = sanitize_filename(track_title)
            output_file = os.path.join(self._output_dir, f"{clean_name}.mp3")
            self._current_output_file = output_file

            self.statusMessage.emit(f"Converting ({i+1}/{total}): {track_title}")

            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", input_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-ab", f"{self._bitrate}k",
                "-map_metadata", "0",
                "-id3v2_version", "3",
                output_file
            ]

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            try:
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags
                )
                _, stderr = self._current_proc.communicate()

                if self._is_cancelled:
                    # Clean up interrupted file
                    if os.path.exists(output_file):
                        try:
                            os.remove(output_file)
                        except Exception:
                            pass
                    break

                if self._current_proc.returncode == 0 and os.path.exists(output_file):
                    success_count += 1
                    # Inject Apple Music canonical metadata, HD artwork, and synced lyrics
                    self._inject_studio_metadata_and_lyrics(output_file, track)
                    self.fileCompleted.emit(input_path, output_file, True, "OK")
                else:
                    failed_count += 1
                    err_msg = stderr.decode('utf-8', errors='ignore')[-200:] if stderr else "Unknown error"
                    error_logs.append(f"{track_title}: {err_msg}")
                    self.fileCompleted.emit(input_path, output_file, False, err_msg)
            except Exception as e:
                failed_count += 1
                error_logs.append(f"{track_title}: {str(e)}")
                self.fileCompleted.emit(input_path, output_file, False, str(e))
            finally:
                self._current_proc = None
                self._current_output_file = None

        final_pct = 100.0 if not self._is_cancelled else pct
        self.progressChanged.emit(total, total, "Finished", final_pct)
        self.conversionComplete.emit(success_count, failed_count, skipped_count, error_logs)

    def _inject_studio_metadata_and_lyrics(self, output_file: str, track: Dict):
        """Embed ID3 tags, 1200px Apple Music cover art, and synced lyrics into converted MP3, plus sidecar .lrc."""
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, USLT, ID3NoHeaderError
            from CanonicalMetadataEngine import iTunesMetadataClient
            from LyricsEngine import LRCLibClient, NetEaseClient, MusixmatchClient

            title = track.get('title', '')
            artist = track.get('artist', '')
            album = track.get('album', '')
            artwork_url = track.get('artwork_url', '')

            # Resolve canonical metadata if missing album or artwork
            if not album or not artwork_url:
                canonical = iTunesMetadataClient.resolve_metadata(title, artist)
                if canonical:
                    title = canonical.title or title
                    artist = canonical.artist or artist
                    album = canonical.album or album
                    artwork_url = canonical.artwork_url or artwork_url

            # Fetch synchronized lyrics
            lyrics_data = (
                MusixmatchClient.fetch_lyrics(title, artist)
                or NetEaseClient.fetch_lyrics(title, artist)
                or LRCLibClient.fetch_lyrics(title, artist)
            )

            # Write sidecar .lrc file
            if lyrics_data and lyrics_data.lines:
                base_path = os.path.splitext(output_file)[0]
                lrc_path = base_path + ".lrc"
                try:
                    with open(lrc_path, "w", encoding="utf-8") as f:
                        if lyrics_data.is_synced:
                            for line in lyrics_data.lines:
                                if line.time_ms >= 0:
                                    mins = line.time_ms // 60000
                                    secs = (line.time_ms % 60000) / 1000.0
                                    f.write(f"[{mins:02d}:{secs:05.2f}]{line.text}\n")
                        else:
                            f.write(lyrics_data.plain_text or "")
                except Exception as e:
                    print(f"[ConvertMp3] Sidecar LRC write error: {e}")

            # Open or initialize ID3 tag
            try:
                audio = ID3(output_file)
            except ID3NoHeaderError:
                audio = ID3()

            if title:
                audio.add(TIT2(encoding=3, text=title))
            if artist:
                audio.add(TPE1(encoding=3, text=artist))
            if album:
                audio.add(TALB(encoding=3, text=album))
            if lyrics_data and lyrics_data.plain_text:
                audio.add(USLT(encoding=3, lang='eng', desc='', text=lyrics_data.plain_text))

            # Download and embed cover artwork
            if artwork_url:
                try:
                    import urllib.request, ssl
                    ctx = ssl._create_unverified_context()
                    req = urllib.request.Request(artwork_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=4.0, context=ctx) as img_resp:
                        if img_resp.status == 200:
                            img_data = img_resp.read()
                            audio.add(APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,  # Front cover
                                desc='Cover',
                                data=img_data
                            ))
                except Exception as e:
                    print(f"[ConvertMp3] Cover art embed notice: {e}")

            audio.save(output_file)
            print(f"[ConvertMp3] Injected studio metadata, artwork, and lyrics into '{os.path.basename(output_file)}'")
        except Exception as e:
            print(f"[ConvertMp3] Metadata injection notice: {e}")


class ConvertMp3Dialog(QDialog):
    """
    Redesigned Cyberpunk HELXAID/HELXAIC Audio Converter Modal.
    
    Component Name: ConvertMp3Dialog
    """
    def __init__(self, parent=None, playlist: Optional[List[Dict]] = None, current_index: int = -1, default_output_dir: Optional[str] = None):
        super().__init__(parent)
        self.setObjectName("ConvertMp3Dialog")
        self.setWindowTitle("Convert to MP3 - HELXAID")
        
        try:
            from launcher import apply_custom_titlebar
            apply_custom_titlebar(self, "#0e0f14")
        except Exception:
            pass

        self.setFixedSize(540, 560)
        self.setModal(True)

        self._playlist = playlist or []
        self._current_index = current_index
        self._output_dir = default_output_dir or os.path.expanduser("~/Music")
        self._worker: Optional[ConvertMp3Worker] = None
        self._preset_buttons: List[QPushButton] = []

        self._init_ui()
        self._apply_styling()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # -------------------------------------------------------------
        # Header Section
        # -------------------------------------------------------------
        header_widget = QWidget(self)
        header_widget.setObjectName("headerWidget")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        # SVG or stylized icon badge
        icon_label = QLabel(header_widget)
        icon_label.setObjectName("headerIconBadge")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(30, 30)
        
        # SVG icon badge
        icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "notes-icon.svg")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "playlist-icon.svg")
        if os.path.exists(icon_path):
            icon_label.setPixmap(QIcon(icon_path).pixmap(18, 18))
        else:
            icon_label.setPixmap(QIcon(os.path.join(os.path.dirname(__file__), "UI Icons", "library-icon.svg")).pixmap(18, 18))
        
        header_layout.addWidget(icon_label)

        title_container = QVBoxLayout()
        title_container.setSpacing(1)
        
        main_title = QLabel("MP3 AUDIO CONVERTER", header_widget)
        main_title.setObjectName("dialogHeaderTitle")
        
        sub_title = QLabel("HELXAIC HI-FI ENCODING ENGINE", header_widget)
        sub_title.setObjectName("dialogHeaderSubtitle")
        
        title_container.addWidget(main_title)
        title_container.addWidget(sub_title)
        header_layout.addLayout(title_container)
        header_layout.addStretch()

        root_layout.addWidget(header_widget)

        # -------------------------------------------------------------
        # 1. Source Selection Card
        # -------------------------------------------------------------
        source_card = QFrame(self)
        source_card.setObjectName("sourceCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(14, 12, 14, 12)
        source_layout.setSpacing(10)

        source_title = QLabel("SOURCE TRACK SELECTION", source_card)
        source_title.setObjectName("cardHeaderLabel")
        source_layout.addWidget(source_title)

        self._btn_group = QButtonGroup(self)

        current_title = "No Track Selected"
        if 0 <= self._current_index < len(self._playlist):
            t = self._playlist[self._current_index]
            current_title = t.get('title') or os.path.basename(t.get('path', '')) or "Current Track"
            if len(current_title) > 42:
                current_title = current_title[:39] + "..."

        self.radio_current = QRadioButton(f"Current Track:  {current_title}", source_card)
        self.radio_current.setObjectName("radioCurrentTrack")
        self._btn_group.addButton(self.radio_current, 0)

        total_tracks = len(self._playlist)
        self.radio_all = QRadioButton(f"All Tracks in Playlist  ({total_tracks} items)", source_card)
        self.radio_all.setObjectName("radioAllTracks")
        self._btn_group.addButton(self.radio_all, 1)

        if 0 <= self._current_index < len(self._playlist):
            self.radio_current.setChecked(True)
        else:
            self.radio_all.setChecked(True)

        source_layout.addWidget(self.radio_current)
        source_layout.addWidget(self.radio_all)
        root_layout.addWidget(source_card)

        # -------------------------------------------------------------
        # 2. Quality & Bitrate Card
        # -------------------------------------------------------------
        quality_card = QFrame(self)
        quality_card.setObjectName("qualityCard")
        quality_layout = QVBoxLayout(quality_card)
        quality_layout.setContentsMargins(14, 12, 14, 12)
        quality_layout.setSpacing(10)

        quality_title_row = QHBoxLayout()
        quality_title = QLabel("AUDIO BITRATE & ENCODING", quality_card)
        quality_title.setObjectName("cardHeaderLabel")
        quality_title_row.addWidget(quality_title)
        quality_title_row.addStretch()

        encoder_badge = QLabel("LAME MP3 (CBR)", quality_card)
        encoder_badge.setObjectName("encoderBadge")
        quality_title_row.addWidget(encoder_badge)
        quality_layout.addLayout(quality_title_row)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(8)

        presets = [("128 kbps", 128), ("192 kbps", 192), ("256 kbps", 256), ("320 kbps (Max)", 320)]
        for label, val in presets:
            btn = QPushButton(label, quality_card)
            btn.setObjectName(f"bitratePresetBtn_{val}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("bitrateValue", val)
            btn.clicked.connect(lambda checked, v=val: self._on_preset_clicked(v))
            presets_row.addWidget(btn)
            self._preset_buttons.append(btn)

        quality_layout.addLayout(presets_row)

        spin_row = QHBoxLayout()
        spin_row.setSpacing(8)
        
        custom_label = QLabel("Custom Bitrate (kbps):", quality_card)
        custom_label.setObjectName("customBitrateLabel")
        spin_row.addWidget(custom_label)

        self.bitrate_spin = QSpinBox(quality_card)
        self.bitrate_spin.setObjectName("bitrateSpinBox")
        self.bitrate_spin.setRange(64, 320)
        self.bitrate_spin.setSingleStep(32)
        self.bitrate_spin.setValue(320)
        self.bitrate_spin.valueChanged.connect(self._on_spin_changed)
        spin_row.addWidget(self.bitrate_spin)
        spin_row.addStretch()

        quality_layout.addLayout(spin_row)
        root_layout.addWidget(quality_card)

        # -------------------------------------------------------------
        # 3. Destination Directory Card
        # -------------------------------------------------------------
        dest_card = QFrame(self)
        dest_card.setObjectName("destCard")
        dest_layout = QVBoxLayout(dest_card)
        dest_layout.setContentsMargins(14, 12, 14, 12)
        dest_layout.setSpacing(8)

        dest_title = QLabel("DESTINATION FOLDER", dest_card)
        dest_title.setObjectName("cardHeaderLabel")
        dest_layout.addWidget(dest_title)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)

        self.dest_path_lbl = QLabel(self._output_dir, dest_card)
        self.dest_path_lbl.setObjectName("destPathLabel")
        self.dest_path_lbl.setToolTip(self._output_dir)
        dest_row.addWidget(self.dest_path_lbl, 1)

        self.browse_btn = QPushButton("BROWSE...", dest_card)
        self.browse_btn.setObjectName("browseBtn")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        
        folder_svg = os.path.join(os.path.dirname(__file__), "UI Icons", "folder-icon-white.svg")
        if os.path.exists(folder_svg):
            self.browse_btn.setIcon(QIcon(folder_svg))
            self.browse_btn.setIconSize(QSize(14, 14))

        self.browse_btn.clicked.connect(self._on_browse_clicked)
        dest_row.addWidget(self.browse_btn)

        dest_layout.addLayout(dest_row)
        root_layout.addWidget(dest_card)

        # -------------------------------------------------------------
        # 4. Progress & Status Card
        # -------------------------------------------------------------
        self.progress_card = QFrame(self)
        self.progress_card.setObjectName("progressCard")
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(14, 10, 14, 10)
        progress_layout.setSpacing(6)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready to convert", self.progress_card)
        self.status_label.setObjectName("statusLabel")
        status_row.addWidget(self.status_label, 1)

        self.pct_label = QLabel("0%", self.progress_card)
        self.pct_label.setObjectName("percentLabel")
        status_row.addWidget(self.pct_label)
        progress_layout.addLayout(status_row)

        self.progress_bar = QProgressBar(self.progress_card)
        self.progress_bar.setObjectName("convertProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)

        root_layout.addWidget(self.progress_card)

        # -------------------------------------------------------------
        # 5. Bottom Action Buttons
        # -------------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("CANCEL", self)
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.cancel_btn)

        self.convert_btn = QPushButton("CONVERT TO MP3", self)
        self.convert_btn.setObjectName("convertBtn")
        self.convert_btn.setCursor(Qt.PointingHandCursor)
        self.convert_btn.clicked.connect(self._on_start_convert)
        btn_row.addWidget(self.convert_btn)

        root_layout.addLayout(btn_row)

        # Set default active preset button (320 kbps)
        self._update_preset_buttons(320)

    def _apply_styling(self):
        self.setStyleSheet("""
            QDialog#ConvertMp3Dialog {
                background-color: #0d0e15;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            /* Header */
            QLabel#dialogHeaderTitle {
                font-family: 'Orbitron', sans-serif;
                font-size: 13px;
                font-weight: 900;
                color: #FFFFFF;
                letter-spacing: 1.5px;
            }
            QLabel#dialogHeaderSubtitle {
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: bold;
                color: #FF5B06;
                letter-spacing: 1px;
            }
            QLabel#headerIconBadge {
                background-color: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
            }

            /* Section Cards - Less border, more background */
            QFrame#sourceCard, QFrame#qualityCard, QFrame#destCard, QFrame#progressCard {
                background-color: #141520;
                border: none;
                border-radius: 8px;
            }

            QLabel#cardHeaderLabel {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: 800;
                color: #FF5B06;
                letter-spacing: 1.2px;
            }

            QLabel#encoderBadge {
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: bold;
                color: #9A9AB0;
                background-color: rgba(255, 255, 255, 0.05);
                padding: 2px 6px;
                border-radius: 4px;
            }

            /* Radio Buttons */
            QRadioButton {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
                color: #E2E2EC;
                padding: 6px 8px;
                border-radius: 5px;
                spacing: 8px;
                background-color: transparent;
            }
            QRadioButton:hover {
                background-color: rgba(255, 91, 6, 0.08);
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #3C3E52;
                background-color: #191B26;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #FF5B06;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #FF5B06;
                background-color: #FF5B06;
            }

            /* Bitrate Preset Buttons */
            QPushButton[objectName^="bitratePresetBtn_"] {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                color: #A0A0B5;
                background-color: #1B1C28;
                border: none;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QPushButton[objectName^="bitratePresetBtn_"]:hover {
                color: #FFFFFF;
                background-color: #262838;
            }
            QPushButton[objectName^="bitratePresetBtn_"]:checked {
                color: #FFFFFF;
                background-color: #FF5B06;
            }

            /* SpinBox */
            QLabel#customBitrateLabel {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                color: #9A9AB0;
            }
            QSpinBox#bitrateSpinBox {
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                color: #FFFFFF;
                background-color: #1B1C28;
                border: none;
                border-radius: 5px;
                padding: 4px 8px;
                min-width: 75px;
            }
            QSpinBox#bitrateSpinBox::up-button, QSpinBox#bitrateSpinBox::down-button {
                background-color: #242636;
                border: none;
                width: 16px;
            }
            QSpinBox#bitrateSpinBox::up-button:hover, QSpinBox#bitrateSpinBox::down-button:hover {
                background-color: #FF5B06;
            }

            /* Destination Path */
            QLabel#destPathLabel {
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                color: #C0C0D0;
                background-color: #1B1C28;
                border: none;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QPushButton#browseBtn {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                color: #FFFFFF;
                background-color: #252738;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
            }
            QPushButton#browseBtn:hover {
                background-color: #FF5B06;
            }

            /* Progress and Status */
            QLabel#statusLabel {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                color: #9A9AB0;
            }
            QLabel#percentLabel {
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                color: #FF5B06;
            }
            QProgressBar#convertProgressBar {
                background-color: #1B1C28;
                border: none;
                border-radius: 4px;
            }
            QProgressBar#convertProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 4px;
            }

            /* Action Buttons */
            QPushButton#cancelBtn {
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                color: #B0B0C0;
                background-color: #1B1C28;
                border: none;
                border-radius: 6px;
                padding: 9px 20px;
            }
            QPushButton#cancelBtn:hover {
                color: #FFFFFF;
                background-color: #282A3C;
            }
            QPushButton#convertBtn {
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 900;
                color: #FFFFFF;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FF7824);
                border: none;
                border-radius: 6px;
                padding: 9px 24px;
            }
            QPushButton#convertBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7824, stop:1 #FDA903);
            }
            QPushButton#convertBtn:disabled {
                background-color: #333444;
                color: #666777;
            }
        """)

    def _on_preset_clicked(self, bitrate: int):
        self.bitrate_spin.blockSignals(True)
        self.bitrate_spin.setValue(bitrate)
        self.bitrate_spin.blockSignals(False)
        self._update_preset_buttons(bitrate)

    def _on_spin_changed(self, value: int):
        self._update_preset_buttons(value)

    def _update_preset_buttons(self, active_val: int):
        for btn in self._preset_buttons:
            val = btn.property("bitrateValue")
            btn.setChecked(val == active_val)

    def _on_browse_clicked(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self._output_dir)
        if folder:
            self._output_dir = folder
            self.dest_path_lbl.setText(folder)
            self.dest_path_lbl.setToolTip(folder)

    def _get_selected_tracks(self) -> List[Dict]:
        if self.radio_current.isChecked():
            if 0 <= self._current_index < len(self._playlist):
                return [self._playlist[self._current_index]]
            elif self._playlist:
                return [self._playlist[0]]
            return []
        return self._playlist

    def _on_start_convert(self):
        if self._worker and self._worker.isRunning():
            return

        tracks = self._get_selected_tracks()
        if not tracks:
            self.status_label.setText("No tracks selected to convert.")
            return

        if not self._output_dir or not os.path.exists(self._output_dir):
            try:
                os.makedirs(self._output_dir, exist_ok=True)
            except Exception:
                self.status_label.setText("Invalid destination folder.")
                return

        # Disable interactive controls during conversion
        self.radio_current.setEnabled(False)
        self.radio_all.setEnabled(False)
        self.bitrate_spin.setEnabled(False)
        for btn in self._preset_buttons:
            btn.setEnabled(False)
        self.browse_btn.setEnabled(False)

        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("CONVERTING...")
        self.cancel_btn.setText("STOP")

        self.progress_bar.setValue(0)
        self.pct_label.setText("0%")
        self.status_label.setText("Initializing FFmpeg converter...")

        bitrate = self.bitrate_spin.value()
        self._worker = ConvertMp3Worker(tracks, self._output_dir, bitrate=bitrate, parent=self)
        self._worker.progressChanged.connect(self._on_worker_progress)
        self._worker.statusMessage.connect(self._on_worker_status)
        self._worker.conversionComplete.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_progress(self, current: int, total: int, filename: str, percentage: float):
        self.progress_bar.setValue(int(percentage))
        self.pct_label.setText(f"{int(percentage)}%")

    def _on_worker_status(self, message: str):
        if len(message) > 55:
            message = message[:52] + "..."
        self.status_label.setText(message)

    def _on_worker_finished(self, success: int, failed: int, skipped: int, errors: list):
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("DONE")
        self.cancel_btn.setText("CLOSE")

        try:
            self.convert_btn.clicked.disconnect()
        except Exception:
            pass
        self.convert_btn.clicked.connect(self.accept)

        if failed == 0 and skipped == 0:
            self.status_label.setText(f"Completed! Converted {success} track(s) to MP3.")
        else:
            summary = f"Done: {success} converted"
            if skipped > 0:
                summary += f", {skipped} skipped"
            if failed > 0:
                summary += f", {failed} failed"
            self.status_label.setText(summary)

    def _on_cancel_clicked(self):
        if self._worker and self._worker.isRunning():
            self.status_label.setText("Stopping conversion...")
            self._worker.cancel()
            self._worker.wait(1500)
            self.reject()
        else:
            self.reject()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)
        event.accept()
