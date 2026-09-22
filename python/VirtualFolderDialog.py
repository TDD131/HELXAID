"""
VirtualFolderDialog.py - HELXAIC Virtual Folder Creation & Renaming Modal
=========================================================================
Cyberpunk styled modal for creating and renaming in-app virtual folders.

Component Name: VirtualFolderDialog
"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QIcon
from AnimatedButton import HoverCloseButton


class VirtualFolderDialog(QDialog):
    """
    Cyberpunk / Dark Modal for creating or renaming virtual folders in Media Library.
    Component Name: VirtualFolderDialog
    """
    def __init__(self, parent=None, title="CREATE VIRTUAL FOLDER", initial_name="New Virtual Folder", confirm_text="CREATE"):
        super().__init__(parent)
        self.setObjectName("VirtualFolderDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(440, 200)
        self.setModal(True)

        self._is_dragging = False
        self._drag_start_pos = QPoint(0, 0)
        self._folder_name = ""

        self._setup_ui(title, initial_name, confirm_text)
        self._apply_styling()

    def _setup_ui(self, title_text, initial_name, confirm_text):
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # Background Container
        container = QFrame(self)
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Title Bar
        title_bar = QWidget(container)
        title_bar.setObjectName("dialogTitleBar")
        title_bar.setFixedHeight(38)

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 0, 14, 0)
        tb_layout.setSpacing(10)

        # Icon
        icon_label = QLabel()
        icon_label.setObjectName("dialogIcon")
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "virtual-folder-icon.svg").replace("\\", "/")
        if os.path.exists(icon_path):
            pixmap = QIcon(icon_path).pixmap(18, 18)
            icon_label.setPixmap(pixmap)
            tb_layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        title_label = QLabel(title_text)
        title_label.setObjectName("dialogTitle")
        tb_layout.addWidget(title_label, 0, Qt.AlignVCenter)
        tb_layout.addStretch()

        close_btn = HoverCloseButton(size=16, icon_size=12, parent=title_bar)
        close_btn.setObjectName("dialogCloseBtn")
        close_btn.clicked.connect(self.reject)
        tb_layout.addWidget(close_btn, 0, Qt.AlignVCenter)

        # Drag handling for title bar
        def title_mousePress(event):
            if event.button() == Qt.LeftButton:
                self._is_dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

        def title_mouseMove(event):
            if self._is_dragging and event.buttons() & Qt.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_start_pos)
                event.accept()

        def title_mouseRelease(event):
            self._is_dragging = False
            event.accept()

        title_bar.mousePressEvent = title_mousePress
        title_bar.mouseMoveEvent = title_mouseMove
        title_bar.mouseReleaseEvent = title_mouseRelease

        container_layout.addWidget(title_bar)

        # 2. Content Body
        content = QWidget(container)
        content.setObjectName("dialogContent")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(20, 14, 20, 16)
        c_layout.setSpacing(12)

        tip_label = QLabel("Virtual folders exist exclusively in HELXAIC and do not alter files on disk.")
        tip_label.setObjectName("dialogTipLabel")
        tip_label.setWordWrap(True)
        c_layout.addWidget(tip_label)

        # Input line edit
        self.name_input = QLineEdit()
        self.name_input.setObjectName("folderNameInput")
        self.name_input.setPlaceholderText("Enter folder name...")
        self.name_input.setText(initial_name)
        self.name_input.selectAll()
        self.name_input.returnPressed.connect(self._on_confirm)
        c_layout.addWidget(self.name_input)

        c_layout.addStretch()

        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setObjectName("dialogCancelBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedHeight(30)
        self.cancel_btn.clicked.connect(self.reject)

        self.confirm_btn = QPushButton(confirm_text)
        self.confirm_btn.setObjectName("dialogConfirmBtn")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedHeight(30)
        self.confirm_btn.clicked.connect(self._on_confirm)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        c_layout.addLayout(btn_layout)

        container_layout.addWidget(content, 1)
        main_vbox.addWidget(container)

    def _apply_styling(self):
        self.setStyleSheet("""
            QFrame#dialogContainer {
                background-color: #16161a;
                border: 1px solid rgba(0, 229, 255, 0.3);
                border-radius: 12px;
            }
            QWidget#dialogTitleBar {
                background-color: rgba(0, 0, 0, 0.45);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }
            QLabel#dialogTitle {
                color: #00E5FF;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 0.5px;
            }
            QLabel#dialogTipLabel {
                color: #9E9E9E;
                font-size: 11px;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                line-height: 1.3;
            }
            QLineEdit#folderNameInput {
                background-color: rgba(30, 30, 35, 0.9);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-family: 'Orbitron', sans-serif;
            }
            QLineEdit#folderNameInput:focus {
                border: 1px solid #00E5FF;
                background-color: rgba(35, 38, 48, 0.95);
            }
            QPushButton#dialogCancelBtn {
                background-color: rgba(40, 40, 45, 0.8);
                color: #aaaaaa;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 0px 16px;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
            }
            QPushButton#dialogCancelBtn:hover {
                background-color: rgba(60, 60, 65, 0.9);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            QPushButton#dialogConfirmBtn {
                background-color: #00E5FF;
                color: #0e0f14;
                border: none;
                border-radius: 6px;
                padding: 0px 18px;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
            }
            QPushButton#dialogConfirmBtn:hover {
                background-color: #33EBFF;
                color: #000000;
            }
            QPushButton#dialogConfirmBtn:pressed {
                background-color: #00B8D4;
            }
        """)

    def _on_confirm(self):
        text = self.name_input.text().strip()
        if text:
            self._folder_name = text
            self.accept()

    def get_folder_name(self) -> str:
        return self._folder_name

    @classmethod
    def get_name(cls, parent=None, title="CREATE VIRTUAL FOLDER", initial_name="New Virtual Folder", confirm_text="CREATE") -> str:
        """Helper classmethod to prompt for folder name modally."""
        dlg = cls(parent=parent, title=title, initial_name=initial_name, confirm_text=confirm_text)
        if dlg.exec() == QDialog.Accepted:
            return dlg.get_folder_name()
        return ""
