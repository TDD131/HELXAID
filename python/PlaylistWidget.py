import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtMultimedia import QMediaPlayer
from MusicSettingsDialog import MusicSettingsDialog
from AnimatedButton import AnimatedButton

# Try to import mutagen for duration reading
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("mutagen not available - duration reading disabled")

class DurationWorker(QThread):
    duration_found = Signal(int, float)
    
    def __init__(self, track_list, get_duration_func, parent=None):
        super().__init__(parent)
        self.track_list = track_list
        self.get_duration_func = get_duration_func
        self._is_running = True
        
    def run(self):
        for idx, path in self.track_list:
            if not self._is_running:
                break
            duration = self.get_duration_func(path)
            if duration > 0:
                self.duration_found.emit(idx, duration)
                
    def stop(self):
        self._is_running = False


class PlaylistWidget(QWidget):
    """Spotify-style playlist view."""
    
    def __init__(self, audio_player, settings_path=None, parent=None):
        super().__init__(parent)
        self.audio_player = audio_player
        self.settings_path = settings_path
        self.setAttribute(Qt.WA_TranslucentBackground, False)  # Allow transparent children
        
        
        self.audio_player.trackChanged.connect(self.on_track_changed)
        self.audio_player.playbackStarted.connect(self.refresh_playing_status)
        self.audio_player.playbackStopped.connect(self.refresh_playing_status)
        self.audio_player.playlistChanged.connect(self.populate)
        self.audio_player.coverChanged.connect(self.update_cover)
        
        self.setup_ui()
        self._duration_thread = None
        self.populate()
        
        # Load saved column widths if available
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # --- Header Section ---
        header = QWidget()
        header.setFixedHeight(220)
        # Gradient background for header (semi-transparent for video background)
        header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(42, 42, 42, 120), stop:1 rgba(18, 18, 18, 150));
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(30, 30, 30, 30)
        header_layout.setSpacing(20)
        
        # Big Cover Art
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(160, 160)
        self.cover_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF5B06, stop:1 #FDA903);
            border-radius: 4px;
        """)
        self.cover_label.setAlignment(Qt.AlignCenter)
        
        # Icon inside cover
        # Icon inside cover
        self.icon_label = QLabel("")
        self.icon_label.setStyleSheet("font-size: 64px; color: rgba(255, 255, 255, 0.5); background: transparent;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        cover_layout = QVBoxLayout(self.cover_label)
        cover_layout.addWidget(self.icon_label)
        
        # Info Column
        info_col = QVBoxLayout()
        info_col.setAlignment(Qt.AlignBottom)
        
        type_label = QLabel("PLAYLIST")
        type_label.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold; background: transparent;")
        
        self.title_label = QLabel("Local Music")
        self.title_label.setStyleSheet("""
            color: #FFFFFF;
            font-size: 48px;
            font-weight: 800;
            background: transparent;
        """)
        
        self.stats_label = QLabel("0 songs")
        self.stats_label.setStyleSheet("color: #b3b3b3; font-size: 13px; font-weight: 600; background: transparent;")
        
        info_col.addWidget(type_label)
        info_col.addWidget(self.title_label)
        info_col.addWidget(self.stats_label)
        
        header_layout.addWidget(self.cover_label)
        header_layout.addLayout(info_col)
        header_layout.addStretch()

        # Settings Button (Top Right)
        self.settings_btn = AnimatedButton()
        self.settings_btn.setFixedSize(48, 48)
        # Use QIcon with the image file
        icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "setting-icon.png")
        if os.path.exists(icon_path):
            self.settings_btn.setIcon(QIcon(icon_path))
            self.settings_btn.setIconSize(QSize(48, 48))
        else:
            self.settings_btn.setText("") # Fallback
            
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 16px;
                color: #b3b3b3;
                font-size: 20px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        
        # Align to top right
        settings_wrapper = QVBoxLayout()
        settings_wrapper.addWidget(self.settings_btn)
        settings_wrapper.addStretch()
        
        header_layout.addLayout(settings_wrapper)
        
        layout.addWidget(header)
        

        
        # --- Song List Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Title ▾", "Date Added", "Length"])
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)  # Remove outline
        
        # Sorting state
        self._sort_column = 1  # Default sort by Title
        self._sort_ascending = True
        self._playlist_data = []  # Store (path, mtime, title) for sorting
        
        # Enable sorting via header click
        self.table.setSortingEnabled(False)  # We'll handle it manually
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(18, 18, 18, 100);
                border: none;
                gridline-color: transparent;
                padding: 0 20px;
            }
            QTableWidget::item {
                padding: 8px;
                border-radius: 4px;
                color: #b3b3b3;
            }
            QTableWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            QTableWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QHeaderView::section {
                background-color: rgba(18, 18, 18, 120);
                color: #b3b3b3;
                border: none;
                border-bottom: 1px solid rgba(40, 40, 40, 150);
                border-right: 1px solid rgba(40, 40, 40, 150);
                padding: 10px;
                font-weight: bold;
                text-align: left;
            }
            QHeaderView::section:hover {
                background-color: rgba(26, 26, 26, 220);
                color: #FFFFFF;
            }
            QScrollBar:vertical {
                background: rgba(18, 18, 18, 100);
                width: 14px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: rgba(85, 85, 85, 200);
                min-height: 20px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(136, 136, 136, 220);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Header adjustments - ALL COLUMNS FIXED (no resizing)
        header_view = self.table.horizontalHeader()
        
        # Column 0: # (Fixed)
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)
        
        # Column 1: Title (Stretch to fill remaining space)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Column 2: Date Added (Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 150)

        # Column 3: Length (Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 80)
        
        # Disable all resizing and reordering
        header_view.setSectionsMovable(False)
        header_view.setStretchLastSection(False)
        
        # Connect resize signal to save settings AND enforce mins
        header_view.sectionResized.connect(self._on_section_resized)
        header_view.sectionMoved.connect(self.save_settings)
        
        self.table.verticalHeader().hide()
        
        # Connect play event
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        
        layout.addWidget(self.table)
        
    def _on_section_resized(self, logical_index, old_size, new_size):
        # Enforce minimum and maximum widths per column
        min_widths = {
            1: 250, # Title min
            2: 150, # Date Added min
            3: 80   # Length (fixed)
        }
        max_widths = {
            1: 800, # Title max - prevent pushing Length column
        }
        
        if logical_index in min_widths:
            min_w = min_widths[logical_index]
            if new_size < min_w:
                self.table.setColumnWidth(logical_index, min_w)
                return
        
        if logical_index in max_widths:
            max_w = max_widths[logical_index]
            if new_size > max_w:
                self.table.setColumnWidth(logical_index, max_w)
                return
                
        self.save_settings()
    
    def _get_duration(self, file_path):
        """Get audio/video duration in seconds using mutagen."""
        if not MUTAGEN_AVAILABLE:
            return 0
        
        filename = os.path.basename(file_path)
        
        try:
            # Try generic mutagen first
            audio = MutagenFile(file_path)
            if audio is not None and audio.info and audio.info.length:
                duration = audio.info.length
                if duration and duration > 0:
                    return duration
        except Exception as e:
            pass
        
        # Try specific handlers for common formats
        try:
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext in ('.mp4', '.m4a', '.m4v', '.mov'):
                from mutagen.mp4 import MP4
                try:
                    audio = MP4(file_path)
                    if audio.info and audio.info.length:
                        return audio.info.length
                except Exception as e:
                    print(f"[Duration] MP4 handler failed for {filename}: {e}")
            elif ext in ('.mp3',):
                from mutagen.mp3 import MP3
                audio = MP3(file_path)
                if audio.info and audio.info.length:
                    return audio.info.length
            elif ext in ('.flac',):
                from mutagen.flac import FLAC
                audio = FLAC(file_path)
                if audio.info and audio.info.length:
                    return audio.info.length
            elif ext in ('.ogg', '.opus'):
                from mutagen.oggopus import OggOpus
                from mutagen.oggvorbis import OggVorbis
                try:
                    audio = OggOpus(file_path)
                    if audio.info and audio.info.length:
                        return audio.info.length
                except:
                    try:
                        audio = OggVorbis(file_path)
                        if audio.info and audio.info.length:
                            return audio.info.length
                    except:
                        pass
            elif ext in ('.wav', '.wave'):
                from mutagen.wave import WAVE
                audio = WAVE(file_path)
                if audio.info and audio.info.length:
                    return audio.info.length
            elif ext in ('.wma',):
                from mutagen.asf import ASF
                audio = ASF(file_path)
                if audio.info and audio.info.length:
                    return audio.info.length
        except Exception as e:
            pass  # Will try ffprobe fallback
        
        # Fallback: Try using ffprobe (from FFmpeg) for files mutagen can't read
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
                 '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
                capture_output=True, text=True, timeout=5, 
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                if duration > 0:
                    return duration
        except Exception:
            pass
        
        # Print which files have no duration (only if both methods failed)
        print(f"[Duration] Could not read: {filename}")
        return 0
    
    def _format_duration(self, seconds):
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        if seconds <= 0:
            return "--:--"
        seconds = int(seconds)
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}:{secs:02d}"
        
    def populate(self):
        """Populate table from audio_player playlist."""
        self.table.setRowCount(0)
        playlist = self.audio_player.playlist
        
        # Update header stats
        self.stats_label.setText(f"{len(playlist)} songs")
        
        # Update title based on folder name if available
        if playlist:
            folder_name = os.path.basename(os.path.dirname(playlist[0]))
            self.title_label.setText(folder_name or "Local Music")
        else:
            self.title_label.setText("Local Music")
        
        # Build sortable data: (original_index, path, title, mtime, duration)
        self._playlist_data = []
        total_duration = 0
        
        # Stop previous thread if running
        if hasattr(self, '_duration_thread') and self._duration_thread:
            self._duration_thread.stop()
            self._duration_thread.wait()
            
        tracks_to_process = []
        
        for idx, file_path in enumerate(playlist):
            filename = os.path.basename(file_path)
            name, ext = os.path.splitext(filename)
            try:
                mtime = os.path.getmtime(file_path)
            except:
                mtime = 0
            
            # Lazy Loading Default Duration
            duration = 0
            
            self._playlist_data.append({
                'original_index': idx,
                'path': file_path,
                'title': name,
                'mtime': mtime,
                'duration': duration,
                'duration_str': self._format_duration(duration),
                'date_str': datetime.fromtimestamp(mtime).strftime("%b %d, %Y") if mtime else "-"
            })
            tracks_to_process.append((idx, file_path))
        
        # Update stats with total duration
        total_dur_str = self._format_duration(total_duration)
        self.stats_label.setText(f"{len(playlist)} songs • {total_dur_str}")
        
        # Apply current sort
        self._apply_sort()
        
        # Start background duration loader
        if tracks_to_process:
            self._duration_thread = DurationWorker(tracks_to_process, self._get_duration, self)
            self._duration_thread.duration_found.connect(self._on_duration_found)
            self._duration_thread.start()

    def _on_duration_found(self, original_index, duration):
        """Update duration info dynamically when found."""
        # Update data
        for item in self._playlist_data:
            if item['original_index'] == original_index:
                item['duration'] = duration
                item['duration_str'] = self._format_duration(duration)
                break
        
        # Recalculate total duration
        total_duration = sum(t['duration'] for t in self._playlist_data)
        total_dur_str = self._format_duration(total_duration)
        self.stats_label.setText(f"{len(self._playlist_data)} songs • {total_dur_str}")
        
        # Update table directly without resorting
        for row in range(self.table.rowCount()):
            num_item = self.table.item(row, 0)
            if num_item and num_item.data(Qt.UserRole) == original_index:
                time_item = self.table.item(row, 3)
                if time_item:
                    time_item.setText(self._format_duration(duration))
                break
        
    def _apply_sort(self):
        """Apply current sorting to the table."""
        data = self._playlist_data.copy()
        
        # Sort based on current column
        if self._sort_column == 1:  # Title
            data.sort(key=lambda x: x['title'].lower(), reverse=not self._sort_ascending)
        elif self._sort_column == 2:  # Date Added
            data.sort(key=lambda x: x['mtime'], reverse=not self._sort_ascending)
        elif self._sort_column == 3:  # Length (duration)
            data.sort(key=lambda x: x['duration'], reverse=not self._sort_ascending)
        
        # Populate table with sorted data
        self.table.setRowCount(len(data))
        
        for row, item in enumerate(data):
            # Store original index in first column's data
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setData(Qt.UserRole, item['original_index'])  # Store original playlist index
            self.table.setItem(row, 0, num_item)
            
            # Title
            title_item = QTableWidgetItem(item['title'])
            title_item.setForeground(QColor("#FFFFFF"))
            title_item.setFont(self._get_font(bold=True, size=10))
            self.table.setItem(row, 1, title_item)
            
            # Date Added
            date_item = QTableWidgetItem(item['date_str'])
            self.table.setItem(row, 2, date_item)
            
            # Duration (actual value)
            time_item = QTableWidgetItem(item['duration_str'])
            time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, time_item)
        
        self.refresh_playing_status()
    
    def _on_header_clicked(self, column):
        """Handle header click for sorting."""
        # Only sort by columns 1, 2, 3 (Title, Date Added, Length)
        if column < 1:
            return
        
        # Toggle sort direction if same column, otherwise reset to ascending
        if self._sort_column == column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        
        # Update header labels with sort indicator
        labels = ["#", "Title", "Date Added", "Length"]
        for i in range(len(labels)):
            if i == column:
                arrow = "▴" if self._sort_ascending else "▾"
                labels[i] = f"{labels[i]} {arrow}"
        self.table.setHorizontalHeaderLabels(labels)
        
        # Re-apply sorting
        self._apply_sort()

    def _get_font(self, bold=False, size=9):
        # Helper to get font with specific weight/size
        f = self.font()
        f.setBold(bold)
        f.setPointSize(size)
        return f

    def on_row_double_clicked(self, row, col):
        # Get the original playlist index from the first column's UserRole data
        num_item = self.table.item(row, 0)
        if num_item:
            original_index = num_item.data(Qt.UserRole)
            if original_index is not None:
                self.audio_player.play_at_index(original_index)
                self.refresh_playing_status()
                return
        # Fallback to row index
        self.audio_player.play_at_index(row)
        self.refresh_playing_status()


        
    def on_track_changed(self, track_path):
        self.mark_active_track()
        
    def refresh_playing_status(self):

        self.mark_active_track()

    def update_cover(self, pixmap: QPixmap):
        """Update cover art display."""
        if not pixmap.isNull():
            # Scale pixmap to fit label while keeping aspect ratio (or crop?)
            # User wants it as background.
            # We can use setPixmap on cover_label and setScaledContents(True) 
            # BUT we have a layout inside. 
            # If we setPixmap, it might not work well with layout. 
            # Alternative: Set stylesheet background-image? No, harder with pixmap content.
            # Best approach: 
            # 1. Hide icon_label.
            # 2. Set pixmap on cover_label.
            # 3. Ensure cover_label scales it.
            
            scaled = pixmap.scaled(self.cover_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.cover_label.setPixmap(scaled)
            self.cover_label.setScaledContents(False) # We scaled it manually to 'cover' likely
            # Actually KeepAspectRatioByExpanding means it might differ in one dimension.
            # Let's try simple setPixmap with scaledContents=True but validation?
            # Creating a dedicated stylesheet is tricky for dynamic images.
            # Let's just setPixmap.
            
            self.icon_label.setVisible(False)
            self.cover_label.setPixmap(scaled)
        else:
            self.cover_label.clear()
            self.cover_label.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF5B06, stop:1 #FDA903);
                border-radius: 4px;
            """)
            self.icon_label.setVisible(True)

    def mark_active_track(self):
        # Highlight the currently playing row text green/orange
        current = self.audio_player.current_index
        
        # Reset all colors first
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    # Default colors
                    if c == 1: item.setForeground(QColor("#FFFFFF"))
                    else: item.setForeground(QColor("#b3b3b3"))
                    
        # Highlight current
        if 0 <= current < self.table.rowCount():
            for c in range(self.table.columnCount()):
                item = self.table.item(current, c)
                if item:
                    item.setForeground(QColor("#FF5B06")) # Orange highlight

    def load_settings(self):
        """Load column widths and order from settings."""
        if not self.settings_path or not os.path.exists(self.settings_path):
            return
            
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                
            pl_settings = settings.get('playlist_widget', {})
            
            # Load column widths
            widths = pl_settings.get('column_widths', {})
            for col_idx, width in widths.items():
                self.table.setColumnWidth(int(col_idx), width)
            
        except Exception as e:
            print(f"Error loading playlist settings: {e}")

    def save_settings(self, *args):
        """Save column widths to settings."""
        if not self.settings_path:
            return
            
        try:
            settings = {}
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
            
            pl_settings = settings.get('playlist_widget', {})
            
            # Save widths
            widths = {}
            for i in range(self.table.columnCount()):
                widths[str(i)] = self.table.columnWidth(i)
            
            pl_settings['column_widths'] = widths
            settings['playlist_widget'] = pl_settings
            
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
                
        except Exception as e:
            print(f"Error saving playlist settings: {e}")

    def open_settings(self):
        """Open the music settings dialog."""
        dialog = MusicSettingsDialog(self.audio_player, self)
        
        # Connect video fit mode change signal to parent's handler if available
        parent = self.parent()
        if parent and hasattr(parent, 'set_fit_mode'):
            dialog.videoFitModeChanged.connect(parent.set_fit_mode)
        
        dialog.exec()
