import os
import json
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QLineEdit,
    QFileDialog, QAbstractItemView, QApplication, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QThread, QObject, QEvent
from PySide6.QtGui import QCursor, QColor, QIcon, QFont, QKeySequence, QShortcut

class NoFocusDelegate(QStyledItemDelegate):
    """Custom delegate to suppress Qt's default dotted focus rectangle outline."""
    def paint(self, painter, option, index):
        if option.state & QStyle.State_HasFocus:
            option.state = option.state ^ QStyle.State_HasFocus
        super().paint(painter, option, index)

# Try to import mutagen for metadata
try:
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.oggvorbis import OggVorbis
    from mutagen.wave import WAVE
    from mutagen.m4a import M4A
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from AnimatedButton import AnimatedCheckBox

class MediaLibraryPage(QWidget):
    """The Media Library tab using a Tree View for folders and tracks."""
    folderSelected = Signal(str)
    tracksAddedToPlaylist = Signal(list, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library_data = []  # List of dicts representing added roots (folders or files)
        self.audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        self._allow_same_folder = False
        
        # Track items mapping for search
        self._all_track_items = []
        self._all_folder_items = []
        
        self.setAcceptDrops(True)
        self._setup_ui()
        self._setup_shortcuts()
        
        QTimer.singleShot(100, self.load_library)

    def _setup_shortcuts(self):
        sc_file = QShortcut(QKeySequence("Ctrl+O"), self, activated=self._add_single_file)
        sc_file.setContext(Qt.WidgetWithChildrenShortcut)
        sc_folder = QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self._add_single_folder)
        sc_folder.setContext(Qt.WidgetWithChildrenShortcut)
        sc_mfiles = QShortcut(QKeySequence("Ctrl+K, Ctrl+O"), self, activated=self._add_multiple_files)
        sc_mfiles.setContext(Qt.WidgetWithChildrenShortcut)
        sc_mfold = QShortcut(QKeySequence("Ctrl+K, Shift+O"), self, activated=self._add_multiple_folders)
        sc_mfold.setContext(Qt.WidgetWithChildrenShortcut)
        sc_all = QShortcut(QKeySequence("Ctrl+A"), self, activated=self._select_all_if_not_input)
        sc_all.setContext(Qt.WidgetWithChildrenShortcut)
        sc_del = QShortcut(QKeySequence("Delete"), self, activated=self._delete_selected_if_not_input)
        sc_del.setContext(Qt.WidgetWithChildrenShortcut)

    def _select_all_if_not_input(self):
        from PySide6.QtWidgets import QApplication, QLineEdit
        if not isinstance(QApplication.focusWidget(), QLineEdit):
            self.select_all()

    def select_all(self):
        folders = getattr(self, '_all_folder_items', [])
        tracks = getattr(self, '_all_track_items', [])
        self.tree.setUpdatesEnabled(False)
        try:
            for folder_item in folders:
                folder_item.setSelected(True)
            for track_item in tracks:
                track_item.setSelected(True)
            self._update_item_selection_styles()
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.viewport().update()

    def _update_item_selection_styles(self):
        from PySide6.QtGui import QColor
        for folder_item in getattr(self, '_all_folder_items', []):
            if folder_item.isSelected():
                for c in range(5):
                    folder_item.setBackground(c, QColor(255, 91, 6, 120))
            else:
                for c in range(5):
                    folder_item.setBackground(c, QColor(40, 40, 45, 180))
        self.tree.viewport().update()

    def _delete_selected_if_not_input(self):
        from PySide6.QtWidgets import QApplication, QLineEdit
        if not isinstance(QApplication.focusWidget(), QLineEdit):
            self._on_delete_selected()

    def _setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("MediaLibraryPage { background: transparent; }")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # --- Top Area ---
        top_container = QWidget()
        top_container.setStyleSheet("background: rgba(18, 18, 18, 120);")
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(30, 20, 30, 20)
        top_layout.setSpacing(15)
        
        # Top Header (Allow Same folder + Stats)
        header_layout = QHBoxLayout()
        
        self.allow_same_btn = AnimatedCheckBox("Allow Same folder")
        self.allow_same_btn.setCursor(Qt.PointingHandCursor)
        self.allow_same_btn.toggled.connect(self._on_allow_same_toggled)
        
        self.stats_label = QLabel("0 tracks | 0:00 total | 0 folder(s)")
        self.stats_label.setStyleSheet("color: #b3b3b3; font-size: 13px; font-weight: bold;")
        
        header_layout.addWidget(self.allow_same_btn)
        header_layout.addStretch()
        header_layout.addWidget(self.stats_label)
        
        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search library... (title, artist, album)")
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background: rgba(30, 30, 30, 0.8);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.5);
                border-radius: 8px;
                padding: 10px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #FF5B06;
                background: rgba(40, 40, 40, 0.9);
            }
        """)
        self.search_bar.textChanged.connect(self._on_search)
        
        top_layout.addLayout(header_layout)
        top_layout.addWidget(self.search_bar)
        
        # --- Tree Widget ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["#", "Title", "Artist", "Album", "Duration"])
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.setRootIsDecorated(False) # Turn off default expand arrow
        self.tree.setItemsExpandable(True)
        self.tree.setFocusPolicy(Qt.ClickFocus)
        self.tree.setItemDelegate(NoFocusDelegate(self.tree))
        self.tree.setStyleSheet("""
            QTreeWidget {
                background: transparent;
                background-color: transparent;
                border: none;
                color: #e0e0e0;
                outline: none;
                outline: 0;
            }
            QTreeWidget:focus {
                outline: none;
                border: none;
            }
            QTreeWidget QHeaderView {
                background: transparent;
            }
            QTreeWidget::viewport {
                background: transparent;
            }
            QTreeWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                outline: none;
                border-top: none;
                border-left: none;
                border-right: none;
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
                background: rgba(255, 91, 6, 0.45);
                color: #ffffff;
                outline: none;
                border-top: none;
                border-left: none;
                border-right: none;
            }
        """)
        
        self.tree.itemSelectionChanged.connect(self._update_item_selection_styles)
        
        # Force the tree to pass drag & drop events to the parent logic
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        
        orig_tree_keyPressEvent = self.tree.keyPressEvent
        def _tree_keyPressEvent(event):
            print(f"[DEBUG MediaLibraryTree] keyPressEvent key={event.key()}, modifiers={event.modifiers()}")
            if event.key() == Qt.Key_A and bool(event.modifiers() & Qt.ControlModifier):
                print("[DEBUG MediaLibraryTree] Ctrl+A matched in tree.keyPressEvent!")
                self.select_all()
                event.accept()
                return
            elif event.key() == Qt.Key_Delete:
                print("[DEBUG MediaLibraryTree] Delete matched in tree.keyPressEvent!")
                self._on_delete_selected()
                event.accept()
                return
            orig_tree_keyPressEvent(event)
        self.tree.keyPressEvent = _tree_keyPressEvent

        # --- Rubber Band Setup ---
        from PySide6.QtWidgets import QRubberBand
        from PySide6.QtCore import QRect
        self.tree._rubber_band = QRubberBand(QRubberBand.Rectangle, self.tree.viewport())
        self.tree._rubber_band_origin = None
        self.tree._rubber_band_active = False
        
        orig_mousePressEvent = self.tree.mousePressEvent
        orig_mouseMoveEvent = self.tree.mouseMoveEvent
        orig_mouseReleaseEvent = self.tree.mouseReleaseEvent
        
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
                    
            orig_mousePressEvent(event)
            
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
            
        orig_mouseDoubleClickEvent = self.tree.mouseDoubleClickEvent
        def _tree_mouseDoubleClickEvent(event):
            if event.button() == Qt.LeftButton:
                item = self.tree.itemAt(event.pos())
                if item and item.data(0, Qt.UserRole) == "folder":
                    item.setExpanded(not item.isExpanded())
                    event.accept()
                    return
            orig_mouseDoubleClickEvent(event)

        self.tree.mousePressEvent = _tree_mousePressEvent
        self.tree.mouseMoveEvent = _tree_mouseMoveEvent
        self.tree.mouseReleaseEvent = _tree_mouseReleaseEvent
        self.tree.mouseDoubleClickEvent = _tree_mouseDoubleClickEvent
        # ------------------------
        
        self.tree.dragEnterEvent = self.dragEnterEvent
        self.tree.dragMoveEvent = self.dragMoveEvent
        self.tree.dropEvent = self.dropEvent
        
        # Override mimeData to allow dragging items out (to OS or other widgets)
        orig_mimeData = self.tree.mimeData
        def _tree_mimeData(items):
            from PySide6.QtCore import QUrl
            mime = orig_mimeData(items)
            urls = []
            for item in items:
                path = item.data(1, Qt.UserRole)
                if path:
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

        self.tree.setStyleSheet(self.tree.styleSheet() + """
            QHeaderView::section {
                background: transparent;
                color: #888888;
                font-size: 12px;
                font-weight: bold;
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
        
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        header_view = self.tree.header()
        
        header_item = self.tree.headerItem()
        header_item.setTextAlignment(0, Qt.AlignCenter)
        header_item.setTextAlignment(1, Qt.AlignLeft | Qt.AlignVCenter)
        header_item.setTextAlignment(2, Qt.AlignLeft | Qt.AlignVCenter)
        header_item.setTextAlignment(3, Qt.AlignLeft | Qt.AlignVCenter)
        header_item.setTextAlignment(4, Qt.AlignCenter)
        
        header_view.setStretchLastSection(False)
        header_view.setSectionsMovable(False)
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tree.setColumnWidth(0, 50)
        
        # Title takes the most space (Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Artist, Album, and Duration have specific sizes and cannot be resized by user
        header_view.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(2, 130)  # Artist
        
        header_view.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tree.setColumnWidth(3, 130)  # Album
        
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tree.setSortingEnabled(False)
        self._sort_column = None
        self._sort_ascending = True
        
        # Block sorting on the '#' column by intercepting clicks
        class HeaderFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress:
                    logicalIndex = header_view.logicalIndexAt(event.pos().x())
                    if logicalIndex == 0:
                        return True # Block event
                return super().eventFilter(obj, event)
                
        self._header_filter = HeaderFilter(self)
        header_view.viewport().installEventFilter(self._header_filter)
        header_view.setSortIndicatorShown(False)
        header_view.sortIndicatorChanged.connect(self._update_header_labels)
        
        # Smooth scrolling
        from smooth_scroll import SmoothTableWidget
        self._tree_smoother = SmoothTableWidget(self.tree)
        
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(top_container)
        layout.addWidget(self.tree)
        
    def _update_header_labels(self, logicalIndex, order):
        """Update header labels with custom sort indicators to match Playlist tab."""
        
        if logicalIndex == 1:
            self._sort_column = "title"
        elif logicalIndex == 2:
            self._sort_column = "artist"
        elif logicalIndex == 3:
            self._sort_column = "album"
        elif logicalIndex == 4:
            self._sort_column = "duration"
        else:
            return
            
        self._sort_ascending = (order == Qt.AscendingOrder)
        
        arrow = " ▲" if order == Qt.AscendingOrder else " ▼"
        titles = ["#", "Title", "Artist", "Album", "Duration"]
        
        header_item = self.tree.headerItem()
        for i, title in enumerate(titles):
            if i == logicalIndex and i != 0:
                header_item.setText(i, title + arrow)
            else:
                header_item.setText(i, title)
                
        # Trigger refresh to apply manual sorting
        self._refresh_tree()
        self._renumber_items()
        
    def _renumber_items(self):
        folder_idx = 1
        track_idx = 1
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == "folder":
                item.setText(0, str(folder_idx))
                folder_idx += 1
            else:
                item.setText(0, f"0.{track_idx}")
                track_idx += 1
                
    def _on_allow_same_toggled(self, checked):
        self._allow_same_folder = checked

    # --- Context Menu ---
    def _show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        item = self.tree.itemAt(pos)
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #28282d; color: #ffffff; border: 1px solid #3c3c41; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #FF5B06; }
        """)
        
        if self.tree.selectedItems():
            add_selected_action = QAction("Add to Playlist", self)
            add_selected_action.triggered.connect(self._on_add_selected_to_playlist)
            menu.addAction(add_selected_action)
            
        add_all_action = QAction("Add All to Playlist", self)
        add_all_action.triggered.connect(self._on_add_all_to_playlist)
        menu.addAction(add_all_action)
        
        menu.addSeparator()
        
        delete_selected_action = QAction("Delete Selected", self)
        delete_selected_action.triggered.connect(self._on_delete_selected)
        menu.addAction(delete_selected_action)
        
        delete_all_action = QAction("Delete All", self)
        delete_all_action.triggered.connect(self._on_delete_all)
        menu.addAction(delete_all_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(pos))
        
    def _get_tracks_from_item(self, item):
        tracks = []
        role = item.data(0, Qt.UserRole)
        path = item.data(1, Qt.UserRole)
        if role == "folder":
            tracks.extend(self._scan_folder(path))
        elif role == "track":
            meta = self._get_track_meta(path)
            if meta:
                tracks.append(meta)
        return tracks

    def _on_add_to_playlist(self, item):
        tracks = self._get_tracks_from_item(item)
        group_name = None
        if item.data(0, Qt.UserRole) == "folder":
            group_name = os.path.basename(item.data(1, Qt.UserRole)) or item.data(1, Qt.UserRole)
        if tracks:
            self.tracksAddedToPlaylist.emit(tracks, group_name)

    def _on_add_selected_to_playlist(self):
        for item in self.tree.selectedItems():
            self._on_add_to_playlist(item)
            
    def _on_add_all_to_playlist(self):
        for data in self._library_data:
            path = data['path']
            if data.get('is_folder', True) or os.path.isdir(path):
                tracks = self._scan_folder(path)
                group_name = os.path.basename(path) or path
                if tracks:
                    self.tracksAddedToPlaylist.emit(tracks, group_name)
            else:
                meta = self._get_track_meta(path)
                if meta:
                    self.tracksAddedToPlaylist.emit([meta], None)
            
    def _on_delete_selected(self):
        root_paths_to_remove = set()
        for item in self.tree.selectedItems():
            top = item
            while top.parent() is not None:
                top = top.parent()
            path = top.data(1, Qt.UserRole)
            if path:
                root_paths_to_remove.add(path)
                
        if not root_paths_to_remove:
            return
            
        new_library = []
        for data in self._library_data:
            if data['path'] not in root_paths_to_remove:
                new_library.append(data)
                
        if len(new_library) != len(self._library_data):
            self._library_data = new_library
            self._save_library()
            self._refresh_tree()
            
    def _on_delete_all(self):
        self._library_data = []
        self._save_library()
        self._refresh_tree()
            
    # --- Drag and Drop ---
    def dragEnterEvent(self, event):
        if event.source() == self.tree:
            from PySide6.QtWidgets import QTreeWidget
            QTreeWidget.dragEnterEvent(self.tree, event)
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        if event.source() == self.tree:
            from PySide6.QtWidgets import QTreeWidget
            QTreeWidget.dragMoveEvent(self.tree, event)
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        if event.source() == self.tree:
            from PySide6.QtWidgets import QTreeWidget
            QTreeWidget.dropEvent(self.tree, event)
            self._sync_library_from_tree()
            return
            
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        self._process_dropped_paths(paths)
        event.acceptProposedAction()
        
    def _sync_library_from_tree(self):
        new_library = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            role_data = item.data(0, Qt.UserRole)
            path = item.data(1, Qt.UserRole)
            if role_data == "folder":
                new_library.append({'path': path, 'is_folder': True})
            elif role_data == "track":
                new_library.append({'path': path, 'is_folder': False})
                
        if len(new_library) == len(self._library_data):
            self._library_data = new_library
            self._sort_column = None
            self._save_library()
            self._refresh_tree()
        
    def _process_dropped_paths(self, paths):
        for path in paths:
            if os.path.isdir(path):
                self._add_path_to_library(path, is_folder=True)
            elif os.path.isfile(path) and os.path.splitext(path)[1].lower() in self.audio_exts:
                self._add_path_to_library(path, is_folder=False)
        self._save_library()
        self._refresh_tree()
        
    # --- Shortcuts ---
    def _add_single_file(self):
        filters = "Audio Files (" + " ".join(["*" + e for e in self.audio_exts]) + ");;All Files (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Add File", "", filters)
        if path:
            self._add_path_to_library(path, is_folder=False)
            self._save_library()
            self._refresh_tree()
            
    def _add_single_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Add Folder")
        if path:
            self._add_path_to_library(path, is_folder=True)
            self._save_library()
            self._refresh_tree()
            
    def _add_multiple_files(self):
        filters = "Audio Files (" + " ".join(["*" + e for e in self.audio_exts]) + ");;All Files (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Multiple Files", "", filters)
        if paths:
            for path in paths:
                self._add_path_to_library(path, is_folder=False)
            self._save_library()
            self._refresh_tree()
            
    def _add_multiple_folders(self):
        # QFileDialog doesn't directly support multiple folders on all OS.
        # Fallback to single folder picker.
        path = QFileDialog.getExistingDirectory(self, "Add Multiple Folders (Select one by one)")
        if path:
            self._add_path_to_library(path, is_folder=True)
            self._save_library()
            self._refresh_tree()

    # --- Library Management ---
    def _add_path_to_library(self, path, is_folder):
        if not self._allow_same_folder:
            # Check if path already exists
            if any(item.get('path') == path for item in self._library_data):
                return # Skip
        
        self._library_data.append({
            'path': path,
            'is_folder': is_folder
        })
        
    def load_library(self):
        settings_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json')
        self._library_data = []
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self._library_data = settings.get('media_library_items', [])
        except Exception as e:
            print(f"[MediaLibrary] Error loading settings: {e}")
            
        self._refresh_tree()
        
    def _save_library(self):
        settings_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'settings.json')
        try:
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            settings['media_library_items'] = self._library_data
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MediaLibrary] Error saving settings: {e}")

    # --- Tree View Logic ---
    def _refresh_tree(self):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        self._all_track_items = []
        self._all_folder_items = []
        
        total_tracks = 0
        total_duration = 0
        total_folders = 0
        
        import re
        def natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]
            
        # Separate folders and files
        folders = [item for item in self._library_data if item.get('is_folder', True)]
        standalone_files = [item for item in self._library_data if not item.get('is_folder', True)]
        
        # Sort folders
        def sort_folder(item_data):
            return natural_sort_key(os.path.basename(item_data['path']))
            
        if self._sort_column is not None:
            folders = sorted(folders, key=sort_folder, reverse=not self._sort_ascending)
        
        # Sort standalone files
        def sort_file(item_data):
            path = item_data['path']
            track = self._get_track_meta(path)
            if not track:
                return natural_sort_key(path)
            if self._sort_column == "title":
                return natural_sort_key(track.get('title', ''))
            elif self._sort_column == "artist":
                return natural_sort_key(track.get('artist', ''))
            elif self._sort_column == "album":
                return natural_sort_key(track.get('album', ''))
            elif self._sort_column == "length":
                return track.get('duration', 0)
            else:
                return natural_sort_key(track.get('title', ''))
                
        if self._sort_column is not None:
            standalone_files = sorted(standalone_files, key=sort_file, reverse=not self._sort_ascending)
        
        # Combine them with folders always on top
        sorted_library_data = folders + standalone_files
        
        for item_data in sorted_library_data:
            path = item_data['path']
            is_folder = item_data.get('is_folder', True) # Backwards compat
            
            if is_folder:
                total_folders += 1
                folder_item = QTreeWidgetItem(self.tree)
                folder_name = os.path.basename(path) or path
                from PySide6.QtGui import QIcon
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "folder-icon.svg").replace("\\", "/")
                folder_item.setIcon(1, QIcon(icon_path))
                folder_item.setText(1, folder_name)
                folder_item.setData(0, Qt.UserRole, "folder")
                folder_item.setData(1, Qt.UserRole, path)
                
                folder_item.setText(0, str(total_folders))
                folder_item.setTextAlignment(0, Qt.AlignCenter)
                
                # Make folder row highlighted
                for c in range(5):
                    folder_item.setBackground(c, QColor(40, 40, 45, 180))
                    font = folder_item.font(c)
                    font.setBold(True)
                    folder_item.setFont(c, font)
                    if c not in (0, 1):
                        folder_item.setText(c, "")
                        
                self._all_folder_items.append(folder_item)
                
                # Scan and sort tracks inside folder
                tracks = self._scan_folder(path)
                def sort_track(track):
                    if self._sort_column == "title":
                        return natural_sort_key(track.get('title', ''))
                    elif self._sort_column == "artist":
                        return natural_sort_key(track.get('artist', ''))
                    elif self._sort_column == "album":
                        return natural_sort_key(track.get('album', ''))
                    elif self._sort_column == "length":
                        return track.get('duration', 0)
                    else:
                        return natural_sort_key(track.get('title', ''))
                        
                if self._sort_column is not None:
                    sorted_tracks = sorted(tracks, key=sort_track, reverse=not self._sort_ascending)
                else:
                    sorted_tracks = tracks
                
                for idx, track in enumerate(sorted_tracks):
                    track_item = QTreeWidgetItem(folder_item)
                    track_item.setFlags(track_item.flags() & ~Qt.ItemIsDropEnabled)
                    track_item.setData(0, Qt.UserRole, "track")
                    track_item.setData(1, Qt.UserRole, track['path'])
                    
                    track_item.setText(0, "")
                    track_item.setText(1, track['title'])
                    track_item.setText(2, track['artist'])
                    track_item.setText(3, track['album'])
                    
                    dur = track['duration']
                    if dur > 0:
                        m, s = divmod(int(dur), 60)
                        track_item.setText(4, f"{m}:{s:02d}")
                    else:
                        track_item.setText(4, "")
                        
                    track_item.setTextAlignment(0, Qt.AlignCenter)
                    track_item.setTextAlignment(1, Qt.AlignLeft | Qt.AlignVCenter)
                    track_item.setTextAlignment(2, Qt.AlignLeft | Qt.AlignVCenter)
                    track_item.setTextAlignment(3, Qt.AlignLeft | Qt.AlignVCenter)
                    track_item.setTextAlignment(4, Qt.AlignCenter)
                    
                    self._all_track_items.append(track_item)
                    total_tracks += 1
                    total_duration += dur
                    
                folder_item.setExpanded(False)
            else:
                # Top level file
                track = self._get_track_meta(path)
                if not track: continue
                
                track_item = QTreeWidgetItem(self.tree)
                track_item.setFlags(track_item.flags() & ~Qt.ItemIsDropEnabled)
                track_item.setData(0, Qt.UserRole, "track")
                track_item.setData(1, Qt.UserRole, track['path'])
                
                total_tracks += 1
                track_item.setText(0, "")
                track_item.setText(1, track['title'])
                track_item.setText(2, track['artist'])
                track_item.setText(3, track['album'])
                
                dur = track['duration']
                if dur > 0:
                    m, s = divmod(int(dur), 60)
                    track_item.setText(4, f"{m}:{s:02d}")
                else:
                    track_item.setText(4, "")
                    
                track_item.setTextAlignment(0, Qt.AlignCenter)
                track_item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
                
                self._all_track_items.append(track_item)
                total_duration += dur
                
        # Update Stats
        h, rem = divmod(int(total_duration), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
        self.stats_label.setText(f"{total_tracks} tracks | {time_str} total | {total_folders} folder(s)")
        
        self._renumber_items()
        self.tree.clearSelection()
        self._update_item_selection_styles()

    def _on_item_double_clicked(self, item, column):
        role = item.data(0, Qt.UserRole)
        if role == "folder":
            item.setExpanded(not item.isExpanded())

    def _on_item_clicked(self, item, column):
        pass # Just select it

    def _on_search(self, text):
        query = text.lower()
        
        if not query:
            for item in self._all_folder_items + self._all_track_items:
                item.setHidden(False)
            return
            
        for item in self._all_track_items:
            title = item.text(1).lower()
            artist = item.text(2).lower()
            album = item.text(3).lower()
            
            if query in title or query in artist or query in album:
                item.setHidden(False)
                if item.parent():
                    item.parent().setHidden(False)
                    item.parent().setExpanded(True)
            else:
                item.setHidden(True)
                
        # Hide empty folders
        for folder in self._all_folder_items:
            has_visible_child = False
            for i in range(folder.childCount()):
                if not folder.child(i).isHidden():
                    has_visible_child = True
                    break
            if not has_visible_child:
                folder.setHidden(True)
            else:
                folder.setHidden(False)
                
    def _scan_folder(self, folder):
        tracks = []
        if not os.path.exists(folder):
            return tracks
            
        for root, _, files in os.walk(folder):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.audio_exts:
                    path = os.path.join(root, f)
                    meta = self._get_track_meta(path)
                    if meta:
                        tracks.append(meta)
        return tracks
        
    def _get_track_meta(self, path):
        if not hasattr(self, '_meta_cache'):
            self._meta_cache = {}
            
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0
            
        if path in self._meta_cache and self._meta_cache[path].get('mtime') == mtime:
            return self._meta_cache[path]['meta']
            
        title = os.path.splitext(os.path.basename(path))[0]
        artist = ""
        album = ""
        duration = 0.0
        
        if MUTAGEN_AVAILABLE:
            try:
                ext = os.path.splitext(path)[1].lower()
                audio = None
                
                if ext == '.mp3':
                    try:
                        audio = MP3(path)
                        id3 = EasyID3(path)
                        title = id3.get('title', [title])[0]
                        artist = id3.get('artist', [artist])[0]
                        album = id3.get('album', [album])[0]
                    except Exception:
                        pass
                elif ext == '.flac':
                    audio = FLAC(path)
                    title = audio.get('title', [title])[0]
                    artist = audio.get('artist', [artist])[0]
                    album = audio.get('album', [album])[0]
                elif ext == '.ogg':
                    audio = OggVorbis(path)
                    title = audio.get('title', [title])[0]
                    artist = audio.get('artist', [artist])[0]
                    album = audio.get('album', [album])[0]
                elif ext in ['.m4a', '.mp4', '.m4v']:
                    from mutagen.mp4 import MP4
                    audio = MP4(path)
                    try:
                        title = audio.tags.get('\xa9nam', [title])[0]
                        artist = audio.tags.get('\xa9ART', [artist])[0]
                        album = audio.tags.get('\xa9alb', [album])[0]
                    except:
                        pass
                
                if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                    duration = audio.info.length
            except Exception:
                pass
                
        if duration == 0.0:
            try:
                import subprocess
                cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path]
                # Windows flag to hide terminal window (creationflags=0x08000000)
                out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, creationflags=0x08000000, timeout=1)
                dur_str = out.decode('utf-8').strip()
                if dur_str:
                    duration = float(dur_str)
            except Exception:
                pass
                
        res = {
            'path': path,
            'title': title,
            'artist': artist,
            'album': album,
            'duration': duration
        }
        self._meta_cache[path] = {'mtime': mtime, 'meta': res}
        return res
