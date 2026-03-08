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
    QDialog, QComboBox, QRadioButton, QButtonGroup
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, QPoint, QUrl
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPalette, QCursor,
    QFontDatabase
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from VideoPlayerWidget import VideoPlayerWidget

import os


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
        
        # Column widths
        self.table.setColumnWidth(0, 50)    # #
        self.table.setColumnWidth(1, 900)   # Title - will stretch
        self.table.setColumnWidth(2, 140)   # Date Added - wider for full date
        self.table.setColumnWidth(3, 80)    # Duration
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Title - user resizable
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # Date - user resizable
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Duration - user resizable
        header.setStretchLastSection(True)  # Last column fills remaining
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
        self.time_current.setFixedWidth(45)
        self.time_current.setAlignment(Qt.AlignCenter)
        self.time_current.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: white;
                padding: 0;
            }
        """)
        self.time_current.returnPressed.connect(self._on_time_input)
        
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setObjectName("timelineSlider")
        self.timeline.setRange(0, 1000)
        self.timeline.setFixedWidth(200)
        self.timeline.sliderMoved.connect(lambda v: self.seekChanged.emit(v / 1000.0))
        
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("timeDurationLabel")
        self.time_total.setFixedWidth(40)
        self.time_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
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
        self.folder_btn.setToolTip("Select Music Folder")
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
            # Get total duration from timeline
            total_duration = self.timeline.maximum() / 1000.0  # Approximate
            if total_duration > 0:
                ratio = total_seconds / (total_duration * 1000)  # Convert to slider ratio
                self.seekChanged.emit(min(1.0, max(0.0, ratio)))
        except (ValueError, IndexError):
            pass  # Invalid input, ignore
        
        # Deselect the field
        self.time_current.clearFocus()


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
        
        # Discord Rich Presence
        self._discord = None
        self._init_discord()
        
        # Config file for persistence (use AppData for bundled exe)
        appdata_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
        os.makedirs(appdata_dir, exist_ok=True)
        self._config_path = os.path.join(appdata_dir, "music_panel_state.json")
        
        self._setup_ui()
        self._connect_signals()
        
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
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f0f1a);
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
            self._toggle_fullscreen()
            event.accept()
            return
        
        # Escape: Exit fullscreen
        if key == Qt.Key_Escape:
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
        
        layout.addWidget(self.stack, stretch=1)
        
        # Player bar
        self.player_bar = PlayerBar()
        layout.addWidget(self.player_bar)
        
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
        from PySide6.QtGui import QAction
        
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
        
        # === Tools Menu ===
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.setObjectName("toolsMenu")
        
        # Select Folder
        self.action_select_folder = QAction("Select Music Folder...", self)
        self.action_select_folder.setShortcut("Ctrl+O")
        self.action_select_folder.triggered.connect(self._browse_folder_direct)
        tools_menu.addAction(self.action_select_folder)
        
        # Load Stream URL
        self.action_load_url = QAction("Open Stream URL...", self)
        self.action_load_url.setShortcut("Ctrl+U")
        self.action_load_url.triggered.connect(self._show_load_url_dialog)
        tools_menu.addAction(self.action_load_url)
        
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
                self._player.setSource(QUrl.fromLocalFile(path))
                self._player.play()
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
            self.player_bar.show()
    
    def _toggle_video(self):
        """Switch between playlist view and video view."""
        self._video_mode = not self._video_mode
        
        # Switch video output based on mode
        if self._video_mode:
            # Set video output to video player widget
            self._player.setVideoOutput(self.video_player.video_widget)
            
            # Re-trigger RTSS/MSI Afterburner exclusion every time the video
            # player opens. The startup call may have been missed if RTSS was
            # launched after this app started (the reload signal has no target
            # then). Calling again here catches that scenario so the D3D OSD
            # overlay is never rendered on top of the video surface.
            try:
                import sys as _sys
                # launcher.py exposes _exclude_from_rtss at module level;
                # import the function without triggering a full re-import.
                _lm = _sys.modules.get('__main__') or _sys.modules.get('launcher')
                if _lm and hasattr(_lm, '_exclude_from_rtss'):
                    _lm._exclude_from_rtss()
            except Exception:
                pass  # Non-critical: RTSS exclusion failure must never crash the video player
            
            # Set video title
            if 0 <= self._current_index < len(self._playlist):
                track = self._playlist[self._current_index]
                self.video_player.set_title(track.get('title', 'Now Playing'))
        else:
            # Clear video output (audio only mode)
            self._player.setVideoOutput(None)
        
        self.stack.setCurrentIndex(1 if self._video_mode else 0)
    
    def _switch_to_playlist(self):
        """Switch back to playlist view (from video player back button)."""
        self._video_mode = False
        self._player.setVideoOutput(None)  # Audio only
        self.stack.setCurrentIndex(0)
    
    def _set_aspect_ratio(self, mode: str):
        """Set video aspect ratio mode: fill, fit, or stretch."""
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
                self._toggle_fullscreen()
                return True
        
        if hasattr(self, '_is_fullscreen') and self._is_fullscreen:
            # Handle key press events
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key_F or key == Qt.Key_Escape:
                    self._toggle_fullscreen()
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
                cursor_pos = self.mapFromGlobal(self.cursor().pos())
                playerbar_rect = self.player_bar.geometry()
                if playerbar_rect.contains(cursor_pos):
                    return  # Don't hide if hovering
                
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
        self.player_bar.set_position(pos / 1000.0, dur / 1000.0)
        
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
                'volume': self.player_bar.volume_slider.value()
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
            self, "Select Music Folder", start, QFileDialog.ShowDirsOnly
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
            self, "Select Music Folder", start, QFileDialog.ShowDirsOnly
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
    # If no state, user can click folder button to select music folder
    
    sys.exit(app.exec())
