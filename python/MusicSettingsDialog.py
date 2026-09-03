import os
import json
import shutil
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout, 
    QFrame, QWidget, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtMultimedia import QMediaDevices, QAudioDevice, QAudioOutput

from YouTubeAccountEngine import YouTubeAccountEngine
from SpotifyAccountEngine import SpotifyAccountEngine


class MusicSettingsDialog(QDialog):
    # Signal emitted when music folder changes
    folderChanged = Signal(str)
    
    def __init__(self, audio_player, parent=None):
        super().__init__(parent)
        self.audio_player = audio_player
        self.audio_output = self.audio_player.audio_output
        self.setWindowTitle("Music Settings")
        self.setFixedSize(480, 640)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #14161D, stop:1 #1A1D27);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
            }
            QLabel {
                color: #ffffff;
                font-family: 'Orbitron', sans-serif;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 12px;
                min-height: 36px;
                font-size: 13px;
            }
            QComboBox:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 2px solid rgba(255, 255, 255, 0.5);
                border-bottom: 2px solid rgba(255, 255, 255, 0.5);
                width: 8px;
                height: 8px;
                margin-right: 10px;
                transform: rotate(45deg);
            }
            QComboBox QAbstractItemView {
                background-color: #1e2128;
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 4px 8px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #ff7b3b);
                color: white;
                border: none;
                border-radius: 18px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 13px;
                font-family: 'Orbitron', sans-serif;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff7026, stop:1 #ff915b);
            }
            QFrame[frameShape="4"] {
                color: rgba(255, 255, 255, 0.08);
            }
        """)
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setObjectName("MusicSettingsDialog")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(12)
        
        # Header
        header_row = QHBoxLayout()
        header_label = QLabel("MUSIC SETTINGS")
        header_label.setObjectName("musicSettingsHeader")
        header_label.setStyleSheet("font-size: 18px; font-weight: 900; color: #fff; letter-spacing: 1px;")
        header_row.addWidget(header_label)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        # Scroll Area for all settings
        scroll = QScrollArea(self)
        scroll.setObjectName("musicSettingsScrollArea")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setObjectName("musicSettingsContainer")
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        
        # 1. Audio Output Selection
        dev_layout = QVBoxLayout()
        dev_layout.setSpacing(6)
        dev_label = QLabel("Audio Output Device")
        dev_label.setObjectName("musicSettingsDevLabel")
        self.device_combo = QComboBox()
        self.device_combo.setObjectName("musicSettingsDeviceCombo")
        self.populate_audio_devices()
        self.device_combo.currentIndexChanged.connect(self.change_audio_device)
        self.device_combo.setEditable(False)
        
        dev_layout.addWidget(dev_label)
        dev_layout.addWidget(self.device_combo)
        layout.addLayout(dev_layout)
        
        # 2. Stereo Mode Selection
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(6)
        mode_label = QLabel("Stereo Mode")
        mode_label.setObjectName("musicSettingsModeLabel")
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("musicSettingsModeCombo")
        self.mode_combo.addItems([
            "Stereo (Default)", 
            "Mono", 
            "Left Channel Only", 
            "Right Channel Only", 
            "Reverse Stereo"
        ])
        
        current_mode = getattr(self.audio_player, 'stereo_mode', 0)
        self.mode_combo.setCurrentIndex(current_mode)
        self.mode_combo.currentIndexChanged.connect(self.change_stereo_mode)
        self.mode_combo.setEditable(False)
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        # 3. Local Music Folder Selection
        folder_layout = QVBoxLayout()
        folder_layout.setSpacing(6)
        folder_label = QLabel("Local Music Folder")
        folder_label.setObjectName("musicSettingsFolderLabel")
        
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        
        self.folder_path = QLabel("No folder selected")
        self.folder_path.setObjectName("folderPath")
        self.folder_path.setStyleSheet("""
            QLabel#folderPath {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
                color: #888;
                font-size: 11px;
            }
        """)
        self.folder_path.setWordWrap(True)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("browseBtn")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setFixedWidth(85)
        browse_btn.setStyleSheet("""
            QPushButton#browseBtn {
                background: rgba(255, 255, 255, 0.08);
                color: #e0e0e0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton#browseBtn:hover {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
            }
        """)
        browse_btn.clicked.connect(self._browse_folder)
        
        folder_row.addWidget(self.folder_path, stretch=1)
        folder_row.addWidget(browse_btn)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addLayout(folder_row)
        layout.addLayout(folder_layout)
        
        self._load_current_folder()

        # 4. Direct Stream Pointer Settings
        settings = QSettings("TDD131", "HELXAID")

        stream_dest_layout = QVBoxLayout()
        stream_dest_layout.setSpacing(6)
        stream_dest_label = QLabel("Stream Auto-Save Routing")
        stream_dest_label.setObjectName("musicSettingsStreamDestLabel")

        self.stream_dest_combo = QComboBox()
        self.stream_dest_combo.setObjectName("musicSettingsStreamDestCombo")
        self.stream_dest_combo.addItem("Save to Library & Playlist (Both)", "both")
        self.stream_dest_combo.addItem("Active Playlist Only (Ephemeral)", "playlist")
        self.stream_dest_combo.addItem("Media Library Only (.hxstream File)", "library")

        current_dest = settings.value("MusicSettings/stream_default_destination", "both", type=str)
        dest_idx = self.stream_dest_combo.findData(current_dest)
        if dest_idx >= 0:
            self.stream_dest_combo.setCurrentIndex(dest_idx)
        self.stream_dest_combo.currentIndexChanged.connect(self._on_stream_dest_changed)

        stream_dest_layout.addWidget(stream_dest_label)
        stream_dest_layout.addWidget(self.stream_dest_combo)
        layout.addLayout(stream_dest_layout)

        # 5. Cloud Streaming Accounts
        cloud_hdr = QLabel("Cloud Accounts & Sync")
        cloud_hdr.setObjectName("musicSettingsCloudHeader")
        cloud_hdr.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; margin-top: 6px;")
        layout.addWidget(cloud_hdr)

        # YouTube Sync Box
        yt_box = QFrame()
        yt_box.setObjectName("musicSettingsYtBox")
        yt_box.setStyleSheet("background: #11131A; border-radius: 8px; border: 1px solid rgba(255, 0, 0, 0.2); padding: 8px;")
        yt_layout = QVBoxLayout(yt_box)
        yt_layout.setSpacing(6)

        yt_lbl = QLabel("YouTube Music Session")
        yt_lbl.setObjectName("musicSettingsYtLabel")
        yt_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        yt_layout.addWidget(yt_lbl)

        self.yt_status = QLabel("Checking status...")
        self.yt_status.setObjectName("musicSettingsYtStatus")
        self.yt_status.setStyleSheet("color: #8C90A0; font-size: 10px;")
        yt_layout.addWidget(self.yt_status)

        yt_action_row = QHBoxLayout()
        self.yt_browser_combo = QComboBox()
        self.yt_browser_combo.setObjectName("musicSettingsYtBrowserCombo")
        self.yt_browser_combo.addItems(["Chrome", "Edge", "Brave", "Firefox", "Opera"])
        self.yt_browser_combo.setFixedHeight(30)
        self.yt_browser_combo.setStyleSheet("background: #1C1E28; font-size: 11px;")
        yt_action_row.addWidget(self.yt_browser_combo)

        self.yt_sync_btn = QPushButton("Sync")
        self.yt_sync_btn.setObjectName("musicSettingsYtSyncBtn")
        self.yt_sync_btn.setFixedHeight(30)
        self.yt_sync_btn.setStyleSheet("background: #FF0000; font-size: 11px; border-radius: 4px; padding: 4px 12px;")
        self.yt_sync_btn.clicked.connect(self._sync_youtube)
        yt_action_row.addWidget(self.yt_sync_btn)

        self.yt_disc_btn = QPushButton("Disconnect")
        self.yt_disc_btn.setObjectName("musicSettingsYtDisconnectBtn")
        self.yt_disc_btn.setFixedHeight(30)
        self.yt_disc_btn.setStyleSheet("background: rgba(255,255,255,0.06); font-size: 10px; border-radius: 4px; padding: 4px 8px;")
        self.yt_disc_btn.clicked.connect(self._disconnect_youtube)
        yt_action_row.addWidget(self.yt_disc_btn)

        yt_layout.addLayout(yt_action_row)
        layout.addWidget(yt_box)

        # Spotify Sync Box
        sp_box = QFrame()
        sp_box.setObjectName("musicSettingsSpBox")
        sp_box.setStyleSheet("background: #11131A; border-radius: 8px; border: 1px solid rgba(29, 185, 84, 0.25); padding: 8px;")
        sp_layout = QVBoxLayout(sp_box)
        sp_layout.setSpacing(6)

        sp_lbl = QLabel("Spotify Account (OAuth2)")
        sp_lbl.setObjectName("musicSettingsSpLabel")
        sp_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        sp_layout.addWidget(sp_lbl)

        self.sp_status = QLabel("Checking status...")
        self.sp_status.setObjectName("musicSettingsSpStatus")
        self.sp_status.setStyleSheet("color: #8C90A0; font-size: 10px;")
        sp_layout.addWidget(self.sp_status)

        sp_action_row = QHBoxLayout()
        self.sp_connect_btn = QPushButton("Connect Spotify")
        self.sp_connect_btn.setObjectName("musicSettingsSpConnectBtn")
        self.sp_connect_btn.setFixedHeight(30)
        self.sp_connect_btn.setStyleSheet("background: #1DB954; font-size: 11px; border-radius: 4px; padding: 4px 12px;")
        self.sp_connect_btn.clicked.connect(self._connect_spotify)
        sp_action_row.addWidget(self.sp_connect_btn)

        self.sp_disc_btn = QPushButton("Logout")
        self.sp_disc_btn.setObjectName("musicSettingsSpDisconnectBtn")
        self.sp_disc_btn.setFixedHeight(30)
        self.sp_disc_btn.setStyleSheet("background: rgba(255,255,255,0.06); font-size: 10px; border-radius: 4px; padding: 4px 8px;")
        self.sp_disc_btn.clicked.connect(self._disconnect_spotify)
        sp_action_row.addWidget(self.sp_disc_btn)

        sp_layout.addLayout(sp_action_row)
        layout.addWidget(sp_box)

        # Clear Cloud Cache Button
        clear_cache_btn = QPushButton("Clear Cloud Cache")
        clear_cache_btn.setObjectName("musicSettingsClearCacheBtn")
        clear_cache_btn.setFixedHeight(32)
        clear_cache_btn.setStyleSheet("background: rgba(255, 255, 255, 0.05); color: #A0A5B5; font-size: 10px; border-radius: 6px;")
        clear_cache_btn.clicked.connect(self._clear_cloud_cache)
        layout.addWidget(clear_cache_btn)
        layout.addWidget(clear_cache_btn)

        self._refresh_cloud_accounts_ui()

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)
        
        # Done Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Done")
        close_btn.setObjectName("musicSettingsDoneBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedWidth(110)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

    def _refresh_cloud_accounts_ui(self):
        yt_engine = YouTubeAccountEngine.get_instance()
        if yt_engine.is_authenticated():
            self.yt_status.setText(f"Connected: {yt_engine.get_user_name()}")
            self.yt_status.setStyleSheet("color: #00E676; font-size: 10px;")
            self.yt_browser_combo.hide()
            self.yt_sync_btn.setText("Resync")
            self.yt_disc_btn.show()
        else:
            self.yt_status.setText("Not connected")
            self.yt_status.setStyleSheet("color: #8C90A0; font-size: 10px;")
            self.yt_browser_combo.show()
            self.yt_sync_btn.setText("Sync")
            self.yt_disc_btn.hide()

        sp_engine = SpotifyAccountEngine.get_instance()
        if sp_engine.is_authenticated():
            self.sp_status.setText(f"Connected: {sp_engine.get_display_name()}")
            self.sp_status.setStyleSheet("color: #1DB954; font-size: 10px;")
            self.sp_connect_btn.hide()
            self.sp_disc_btn.show()
        else:
            self.sp_status.setText("Not connected")
            self.sp_status.setStyleSheet("color: #8C90A0; font-size: 10px;")
            self.sp_connect_btn.show()
            self.sp_disc_btn.hide()

    def _sync_youtube(self):
        browser = self.yt_browser_combo.currentText()
        YouTubeAccountEngine.get_instance().sync_from_browser(browser)
        self._refresh_cloud_accounts_ui()

    def _disconnect_youtube(self):
        YouTubeAccountEngine.get_instance().disconnect()
        self._refresh_cloud_accounts_ui()

    def _connect_spotify(self):
        SpotifyAccountEngine.get_instance().start_oauth_flow()

    def _disconnect_spotify(self):
        SpotifyAccountEngine.get_instance().disconnect()
        self._refresh_cloud_accounts_ui()

    def _clear_cloud_cache(self):
        cache_dir = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                pass
        
    def populate_audio_devices(self):
        self.devices = QMediaDevices.audioOutputs()
        current_device = self.audio_output.device()
        current_desc = current_device.description()
        
        self.device_combo.clear()
        current_idx = -1
        
        for i, device in enumerate(self.devices):
            desc = device.description()
            self.device_combo.addItem(desc)
            if device.id() == current_device.id():
                current_idx = i
            elif current_idx == -1 and desc == current_desc:
                current_idx = i

        if self.devices:
            if current_idx == -1:
                current_idx = 0
            self.device_combo.setCurrentIndex(current_idx)
            self.device_combo.setEnabled(True)
        else:
            self.device_combo.addItem("No audio output devices found")
            self.device_combo.setCurrentIndex(0)
            self.device_combo.setEnabled(False)
        
    def change_audio_device(self, index):
        if 0 <= index < len(self.devices):
            selected_device = self.devices[index]
            self.audio_output.setDevice(selected_device)
            desc = selected_device.description()
            print(f"Switched audio device to: {desc}")
            if hasattr(self.audio_player, '_save_last_track'):
                 self.audio_player._save_last_track()

    def change_stereo_mode(self, index):
        if hasattr(self.audio_player, 'set_stereo_mode'):
            self.audio_player.set_stereo_mode(index)
    
    def _load_current_folder(self):
        if hasattr(self.audio_player, 'music_folder'):
            folder = self.audio_player.music_folder
            if folder and os.path.exists(folder):
                self.folder_path.setText(folder)
                self.folder_path.setStyleSheet("""
                    QLabel#folderPath {
                        background: rgba(255, 255, 255, 0.04);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 8px;
                        padding: 8px;
                        color: #e0e0e0;
                        font-size: 11px;
                    }
                """)
    
    def _browse_folder(self):
        from PySide6.QtWidgets import QFileDialog
        current = self.folder_path.text()
        start_dir = current if current != "No folder selected" and os.path.exists(current) else os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Select Media Folder", start_dir, QFileDialog.ShowDirsOnly)
        if folder:
            self.folder_path.setText(folder)
            self.folder_path.setStyleSheet("""
                QLabel#folderPath {
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                    padding: 8px;
                    color: #e0e0e0;
                    font-size: 11px;
                }
            """)
            if hasattr(self.audio_player, 'set_music_folder'):
                self.audio_player.set_music_folder(folder)
            elif hasattr(self.audio_player, 'music_folder'):
                self.audio_player.music_folder = folder
            if hasattr(self, 'folderChanged'):
                self.folderChanged.emit(folder)

    def _on_stream_dest_changed(self, index):
        mode = self.stream_dest_combo.itemData(index)
        if mode:
            settings = QSettings("TDD131", "HELXAID")
            settings.setValue("MusicSettings/stream_default_destination", mode)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QAudioOutput
    import sys
    
    app = QApplication(sys.argv)
    
    class MockAudioPlayer:
        def __init__(self):
            self.audio_output = QAudioOutput()
            self.music_folder = ""
            self.stereo_mode = 0
        def set_stereo_mode(self, mode): pass
        def set_music_folder(self, folder): pass
    
    dialog = MusicSettingsDialog(MockAudioPlayer())
    dialog.setWindowFlags(Qt.Window)
    dialog.show()
    sys.exit(app.exec())
