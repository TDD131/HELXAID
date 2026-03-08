import os
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout, 
    QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtMultimedia import QMediaDevices, QAudioDevice, QAudioOutput

class MusicSettingsDialog(QDialog):
    # Signal emitted when music folder changes
    folderChanged = Signal(str)
    
    def __init__(self, audio_player, parent=None):
        super().__init__(parent)
        self.audio_player = audio_player
        self.audio_output = self.audio_player.audio_output
        self.setWindowTitle("Music Settings")
        self.setFixedSize(450, 480)  # Increased for folder selection
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a1a, stop:1 #252525);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
            }
            QLabel {
                color: #ffffff;
                font-family: "Segoe UI", sans-serif;
                font-size: 14px;
                font-weight: 500;
            }
            QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px 12px;
                min-height: 40px;
                font-size: 14px;
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
                image: none; /* Can replace with custom icon or simple text 'v' handled elsewhere if needed, or keeping it default but styled */
                border-left: 2px solid rgba(255, 255, 255, 0.5);
                border-bottom: 2px solid rgba(255, 255, 255, 0.5);
                width: 8px;
                height: 8px;
                margin-right: 10px;
                transform: rotate(45deg); /* Simple CSS arrow hack */
            }
            QComboBox QAbstractItemView {
                background-color: #252525;
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 8px;
                selection-background-color: #FF5B06;
                selection-color: #ffffff;
                padding: 5px;
                outline: none;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #ff7b3b);
                color: white;
                border: none;
                border-radius: 20px; /* Pill shape */
                padding: 10px 24px;
                font-weight: bold;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff7026, stop:1 #ff915b);
                margin-top: -1px; /* Slight lift effect */
            }
            QPushButton:pressed {
                margin-top: 1px;
                background: #e04a00;
            }
            QFrame[frameShape="4"] { /* HLine */
                color: rgba(255, 255, 255, 0.1);
            }
        """)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(24) # Increased spacing
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header_label = QLabel("Music Settings")
        header_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #fff; margin-bottom: 5px;")
        layout.addWidget(header_label)
        
        # Audio Output Selection
        dev_layout = QVBoxLayout()
        dev_layout.setSpacing(8)
        dev_label = QLabel("Audio Output Device")
        self.device_combo = QComboBox()
        self.populate_audio_devices()
        self.device_combo.currentIndexChanged.connect(self.change_audio_device)
        self.device_combo.setEditable(False)
        # Removed inline stylesheet
        
        dev_layout.addWidget(dev_label)
        dev_layout.addWidget(self.device_combo)
        layout.addLayout(dev_layout)
        
        # Stereo Mode Selection
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(8)
        mode_label = QLabel("Stereo Mode")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Stereo (Default)", 
            "Mono", 
            "Left Channel Only", 
            "Right Channel Only", 
            "Reverse Stereo"
        ])
        
        # Load current stereo mode from player
        current_mode = getattr(self.audio_player, 'stereo_mode', 0)
        self.mode_combo.setCurrentIndex(current_mode)
        
        self.mode_combo.currentIndexChanged.connect(self.change_stereo_mode)
        self.mode_combo.setEditable(False)
        # Removed inline stylesheet
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        # Music Folder Selection
        folder_layout = QVBoxLayout()
        folder_layout.setSpacing(8)
        folder_label = QLabel("Music Folder")
        
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        
        self.folder_path = QLabel("No folder selected")
        self.folder_path.setObjectName("folderPath")
        self.folder_path.setStyleSheet("""
            QLabel#folderPath {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 10px;
                color: #888;
                font-size: 12px;
            }
        """)
        self.folder_path.setWordWrap(True)
        
        from PySide6.QtWidgets import QFileDialog
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("browseBtn")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setFixedWidth(100)
        browse_btn.setStyleSheet("""
            QPushButton#browseBtn {
                background: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
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
        
        # Load current folder
        self._load_current_folder()

        
        layout.addStretch()
        
        # Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Done")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedWidth(120)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        
    def populate_audio_devices(self):
        """Fetch available audio outputs and populate combo box."""
        self.devices = QMediaDevices.audioOutputs()
        current_device = self.audio_output.device()
        current_desc = current_device.description()
        
        self.device_combo.clear()
        current_idx = -1
        
        for i, device in enumerate(self.devices):
            desc = device.description()
            self.device_combo.addItem(desc)
            # Try to match by ID first, then by description
            if device.id() == current_device.id():
                current_idx = i
            elif current_idx == -1 and desc == current_desc:
                current_idx = i

        if self.devices:
            # If we didn't find a matching current device, fall back to the first one
            if current_idx == -1:
                current_idx = 0
            self.device_combo.setCurrentIndex(current_idx)
            self.device_combo.setEnabled(True)
        else:
            # No devices available: show a placeholder so the dropdown isn't blank
            self.device_combo.addItem("No audio output devices found")
            self.device_combo.setCurrentIndex(0)
            self.device_combo.setEnabled(False)
        
    def change_audio_device(self, index):
        """Update the audio output device."""
        if 0 <= index < len(self.devices):
            selected_device = self.devices[index]
            self.audio_output.setDevice(selected_device)
            desc = selected_device.description()
            print(f"Switched audio device to: {desc}")

            # Persist device via player's method if available, or update variable
            # The player saves settings when track changes or app closes, 
            # but we can force a save if needed or just rely on the player's internal state.
            # However, player._save_last_track reads from self.audio_output.device(), 
            # so simply setting it on the object (which we just did) is enough 
            # for when _save_last_track is eventually called.
            
            # For immediate persistence (so restarting app remembers it):
            if hasattr(self.audio_player, '_save_last_track'):
                 self.audio_player._save_last_track()

    def change_stereo_mode(self, index):
        """Update stereo mode setting."""
        if hasattr(self.audio_player, 'set_stereo_mode'):
            self.audio_player.set_stereo_mode(index)
    
    def _load_current_folder(self):
        """Load and display current music folder."""
        if hasattr(self.audio_player, 'music_folder'):
            folder = self.audio_player.music_folder
            if folder and os.path.exists(folder):
                self.folder_path.setText(folder)
                self.folder_path.setStyleSheet("""
                    QLabel#folderPath {
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 8px;
                        padding: 10px;
                        color: #e0e0e0;
                        font-size: 12px;
                    }
                """)
    
    def _browse_folder(self):
        """Open folder browser dialog."""
        from PySide6.QtWidgets import QFileDialog
        
        current = self.folder_path.text()
        start_dir = current if current != "No folder selected" and os.path.exists(current) else os.path.expanduser("~")
        
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Music Folder",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if folder:
            self.folder_path.setText(folder)
            self.folder_path.setStyleSheet("""
                QLabel#folderPath {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    padding: 10px;
                    color: #e0e0e0;
                    font-size: 12px;
                }
            """)
            
            # Save to audio player
            if hasattr(self.audio_player, 'set_music_folder'):
                self.audio_player.set_music_folder(folder)
            elif hasattr(self.audio_player, 'music_folder'):
                self.audio_player.music_folder = folder
                
            # Emit signal if available
            if hasattr(self, 'folderChanged'):
                self.folderChanged.emit(folder)
            
            print(f"Music folder set to: {folder}")


# Standalone test
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    import sys
    
    app = QApplication(sys.argv)
    
    # Create mock audio player
    class MockAudioPlayer:
        def __init__(self):
            self.audio_output = QAudioOutput()
            self.music_folder = ""
            self.stereo_mode = 0
        
        def set_stereo_mode(self, mode):
            self.stereo_mode = mode
            print(f"Stereo mode set to: {mode}")
        
        def set_music_folder(self, folder):
            self.music_folder = folder
            print(f"Music folder set to: {folder}")
    
    mock_player = MockAudioPlayer()
    
    dialog = MusicSettingsDialog(mock_player)
    dialog.setWindowFlags(Qt.Window)  # Show as regular window for testing
    dialog.show()
    
    sys.exit(app.exec())
