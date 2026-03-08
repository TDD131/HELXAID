"""
Macro Settings Dialog

A separate settings dialog for configuring macros, profiles, and layers.
"""

import os
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QCheckBox, QLineEdit, QGroupBox, QFormLayout, QMessageBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QAbstractItemView
)
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import Qt, Signal


class MacroSettingsDialog(QDialog):
    """
    Settings dialog for the macro system.
    
    Tabs:
    - Macros: Create, edit, delete macros
    - Profiles: Manage profiles and app bindings
    - Quick Actions: Common macro presets
    """
    
    macros_changed = Signal()
    
    def __init__(self, macro_bridge, parent=None):
        super().__init__(parent)
        self._bridge = macro_bridge
        self._setup_ui()
        self._load_data()
        
    def _setup_ui(self):
        self.setWindowTitle("Macro Settings")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                background: #1a1a1a;
            }
            QTabBar::tab {
                background: #252525;
                color: #888;
                padding: 10px 20px;
                border: none;
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background: #FF5B06;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #333;
            }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #FF5B06;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background: #FF5B06;
            }
            QPushButton:pressed {
                background: #CC4905;
            }
            QPushButton#primaryBtn {
                background: #FF5B06;
            }
            QLineEdit, QSpinBox, QComboBox {
                background: #252525;
                color: #e0e0e0;
                border: 1px solid #333;
                padding: 8px;
                border-radius: 5px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #FF5B06;
            }
            QTableWidget {
                background: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #333;
                gridline-color: #333;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background: #FF5B06;
            }
            QHeaderView::section {
                background: #252525;
                color: #888;
                padding: 8px;
                border: none;
            }
            QListWidget {
                background: #252525;
                border: 1px solid #333;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background: #FF5B06;
            }
            QTextEdit {
                background: #252525;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 5px;
                font-family: Consolas, monospace;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QLabel("Macro Settings")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        header.setStyleSheet("color: #FF5B06; padding: 10px 0;")
        layout.addWidget(header)
        
        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        
        # Create tabs
        self._create_quick_tab()
        self._create_macros_tab()
        self._create_profiles_tab()
        
        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("Save All")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self._save_all)
        btn_layout.addWidget(self.save_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
    def _create_quick_tab(self):
        """Quick actions tab for common macros."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Status
        status_group = QGroupBox("Macro System Status")
        status_layout = QHBoxLayout(status_group)
        
        self.status_label = QLabel("● Not Running")
        self.status_label.setStyleSheet("color: #888; font-size: 14px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.toggle_btn = QPushButton("Start Macro System")
        self.toggle_btn.clicked.connect(self._toggle_system)
        status_layout.addWidget(self.toggle_btn)
        
        layout.addWidget(status_group)
        
        # Quick Actions
        quick_group = QGroupBox("Quick Actions")
        quick_layout = QVBoxLayout(quick_group)
        
        # Auto-clicker
        ac_layout = QHBoxLayout()
        ac_layout.addWidget(QLabel("Auto-Clicker:"))
        
        self.ac_button = QComboBox()
        self.ac_button.addItems(["Left Click", "Right Click", "Middle Click"])
        ac_layout.addWidget(self.ac_button)
        
        ac_layout.addWidget(QLabel("Interval (ms):"))
        self.ac_interval = QSpinBox()
        self.ac_interval.setRange(10, 5000)
        self.ac_interval.setValue(100)
        ac_layout.addWidget(self.ac_interval)
        
        ac_layout.addWidget(QLabel("Toggle Key:"))
        self.ac_hotkey = QLineEdit("F6")
        self.ac_hotkey.setMaximumWidth(60)
        ac_layout.addWidget(self.ac_hotkey)
        
        self.ac_create_btn = QPushButton("Create")
        self.ac_create_btn.clicked.connect(self._create_autoclicker)
        ac_layout.addWidget(self.ac_create_btn)
        
        ac_layout.addStretch()
        quick_layout.addLayout(ac_layout)
        
        # Button Remap
        remap_layout = QHBoxLayout()
        remap_layout.addWidget(QLabel("Button Remap:"))
        
        self.remap_from = QComboBox()
        self.remap_from.addItems(["X1 (Side)", "X2 (Side)", "Middle"])
        remap_layout.addWidget(self.remap_from)
        
        remap_layout.addWidget(QLabel("→"))
        
        self.remap_to = QLineEdit("ctrl")
        self.remap_to.setMaximumWidth(80)
        remap_layout.addWidget(self.remap_to)
        
        self.remap_create_btn = QPushButton("Create")
        self.remap_create_btn.clicked.connect(self._create_remap)
        remap_layout.addWidget(self.remap_create_btn)
        
        remap_layout.addStretch()
        quick_layout.addLayout(remap_layout)
        
        layout.addWidget(quick_group)
        
        # Active Macros
        active_group = QGroupBox("Active Macros")
        active_layout = QVBoxLayout(active_group)
        
        self.active_list = QListWidget()
        active_layout.addWidget(self.active_list)
        
        active_btn_layout = QHBoxLayout()
        self.disable_all_btn = QPushButton("Disable All")
        self.disable_all_btn.clicked.connect(self._disable_all)
        active_btn_layout.addWidget(self.disable_all_btn)
        
        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.clicked.connect(self._delete_selected)
        active_btn_layout.addWidget(self.delete_selected_btn)
        
        active_btn_layout.addStretch()
        active_layout.addLayout(active_btn_layout)
        
        layout.addWidget(active_group, 1)
        
        self.tabs.addTab(tab, "Quick Actions")
        
    def _create_macros_tab(self):
        """Advanced macro creation tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Macro table
        self.macro_table = QTableWidget()
        self.macro_table.setColumnCount(5)
        self.macro_table.setHorizontalHeaderLabels(["Name", "Type", "Trigger", "Status", "Actions"])
        self.macro_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.macro_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.macro_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.new_macro_btn = QPushButton("+ New Macro")
        self.new_macro_btn.clicked.connect(self._new_macro)
        btn_layout.addWidget(self.new_macro_btn)
        
        self.edit_macro_btn = QPushButton("Edit")
        self.edit_macro_btn.clicked.connect(self._edit_macro)
        btn_layout.addWidget(self.edit_macro_btn)
        
        self.delete_macro_btn = QPushButton("Delete")
        self.delete_macro_btn.clicked.connect(self._delete_macro)
        btn_layout.addWidget(self.delete_macro_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.tabs.addTab(tab, "Macros")
        
    def _create_profiles_tab(self):
        """Profile management tab."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        # Profile list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("Profiles"))
        
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        left_layout.addWidget(self.profile_list)
        
        profile_btn_layout = QHBoxLayout()
        self.new_profile_btn = QPushButton("+")
        self.new_profile_btn.clicked.connect(self._new_profile)
        profile_btn_layout.addWidget(self.new_profile_btn)
        
        self.delete_profile_btn = QPushButton("-")
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        profile_btn_layout.addWidget(self.delete_profile_btn)
        
        left_layout.addLayout(profile_btn_layout)
        
        layout.addWidget(left)
        
        # Profile details
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        form = QFormLayout()
        
        self.profile_name = QLineEdit()
        form.addRow("Name:", self.profile_name)
        
        self.profile_apps = QLineEdit()
        self.profile_apps.setPlaceholderText("e.g., gta5.exe, valorant.exe")
        form.addRow("Bound Apps:", self.profile_apps)
        
        self.profile_hotkey = QLineEdit()
        self.profile_hotkey.setPlaceholderText("e.g., ctrl+shift+1")
        form.addRow("Activation Hotkey:", self.profile_hotkey)
        
        right_layout.addLayout(form)
        
        # Macros in profile
        right_layout.addWidget(QLabel("Macros in this profile:"))
        self.profile_macros = QListWidget()
        right_layout.addWidget(self.profile_macros)
        
        layout.addWidget(right, 2)
        
        self.tabs.addTab(tab, "Profiles")
        
    def _load_data(self):
        """Load data from macro bridge."""
        self._update_status()
        self._load_macros()
        self._load_profiles()
        
    def _update_status(self):
        """Update system status display."""
        if self._bridge and self._bridge.is_running:
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 14px;")
            self.toggle_btn.setText("Stop Macro System")
        else:
            self.status_label.setText("● Not Running")
            self.status_label.setStyleSheet("color: #888; font-size: 14px;")
            self.toggle_btn.setText("Start Macro System")
            
    def _toggle_system(self):
        """Toggle macro system on/off."""
        if not self._bridge:
            return
            
        if self._bridge.is_running:
            self._bridge.stop()
        else:
            self._bridge.start()
            
        self._update_status()
        self._load_macros()
        
    def _load_macros(self):
        """Load macros into table and list."""
        self.macro_table.setRowCount(0)
        self.active_list.clear()
        
        if not self._bridge or not self._bridge.profile_manager:
            return
            
        for profile in self._bridge.profile_manager.get_all_profiles():
            macros = self._bridge.profile_manager.get_macros_for_profile(profile.id)
            for macro in macros:
                # Add to table
                row = self.macro_table.rowCount()
                self.macro_table.insertRow(row)
                
                self.macro_table.setItem(row, 0, QTableWidgetItem(macro.name))
                self.macro_table.setItem(row, 1, QTableWidgetItem(type(macro).__name__.replace("Macro", "")))
                
                trigger_str = ""
                if macro.trigger:
                    if macro.trigger.button:
                        trigger_str = f"Mouse: {macro.trigger.button}"
                    elif macro.trigger.key:
                        trigger_str = f"Key: {macro.trigger.key}"
                self.macro_table.setItem(row, 2, QTableWidgetItem(trigger_str))
                
                status = "Enabled" if macro.enabled else "Disabled"
                self.macro_table.setItem(row, 3, QTableWidgetItem(status))
                
                # Actions column
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(4, 4, 4, 4)
                
                toggle_btn = QPushButton("Toggle")
                toggle_btn.setProperty("macro_id", macro.id)
                toggle_btn.clicked.connect(lambda checked, m=macro: self._toggle_macro(m))
                actions_layout.addWidget(toggle_btn)
                
                self.macro_table.setCellWidget(row, 4, actions_widget)
                
                # Add to active list
                item = QListWidgetItem(f"{'✓' if macro.enabled else '○'} {macro.name}")
                item.setData(Qt.UserRole, macro.id)
                self.active_list.addItem(item)
                
    def _load_profiles(self):
        """Load profiles into list."""
        self.profile_list.clear()
        
        if not self._bridge or not self._bridge.profile_manager:
            return
            
        for profile in self._bridge.profile_manager.get_all_profiles():
            item = QListWidgetItem(profile.name)
            item.setData(Qt.UserRole, profile.id)
            self.profile_list.addItem(item)
            
    def _on_profile_selected(self, current, previous):
        """Handle profile selection."""
        if not current:
            return
            
        profile_id = current.data(Qt.UserRole)
        profile = self._bridge.profile_manager.get_profile(profile_id)
        
        if profile:
            self.profile_name.setText(profile.name)
            self.profile_apps.setText(", ".join(profile.bound_apps))
            self.profile_hotkey.setText(profile.activation_hotkey or "")
            
            # Load macros in profile
            self.profile_macros.clear()
            macros = self._bridge.profile_manager.get_macros_for_profile(profile_id)
            for macro in macros:
                self.profile_macros.addItem(macro.name)
                
    def _create_autoclicker(self):
        """Create auto-clicker from quick action."""
        if not self._bridge:
            return
            
        button_map = {"Left Click": "left", "Right Click": "right", "Middle Click": "middle"}
        button = button_map.get(self.ac_button.currentText(), "left")
        interval = self.ac_interval.value()
        hotkey = self.ac_hotkey.text().lower().strip()
        
        macro_id = self._bridge.create_quick_autoclicker(button, interval, hotkey)
        QMessageBox.information(self, "Created", f"Auto-clicker created!\nToggle with: {hotkey.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _create_remap(self):
        """Create button remap from quick action."""
        if not self._bridge:
            return
            
        from_map = {"X1 (Side)": "x1", "X2 (Side)": "x2", "Middle": "middle"}
        from_btn = from_map.get(self.remap_from.currentText(), "x1")
        to_key = self.remap_to.text().lower().strip()
        
        macro_id = self._bridge.create_quick_remap(from_btn, to_key)
        QMessageBox.information(self, "Created", f"Remap created!\n{from_btn.upper()} → {to_key.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _toggle_macro(self, macro):
        """Toggle a macro's enabled state."""
        macro.enabled = not macro.enabled
        self._load_macros()
        
    def _disable_all(self):
        """Disable all macros."""
        if not self._bridge or not self._bridge.engine:
            return
            
        self._bridge.engine.cancel_all_macros()
        QMessageBox.information(self, "Disabled", "All active macros stopped.")
        
    def _delete_selected(self):
        """Delete selected macro from active list."""
        current = self.active_list.currentItem()
        if not current:
            return
            
        macro_id = current.data(Qt.UserRole)
        
        reply = QMessageBox.question(self, "Delete Macro",
            "Are you sure you want to delete this macro?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.Yes:
            self._bridge.profile_manager.remove_macro(macro_id)
            self._load_macros()
            self.macros_changed.emit()
            
    def _new_macro(self):
        """Create new macro (opens sub-dialog)."""
        QMessageBox.information(self, "Coming Soon",
            "Advanced macro editor coming soon!\n\nUse Quick Actions tab for now.")
            
    def _edit_macro(self):
        """Edit selected macro."""
        QMessageBox.information(self, "Coming Soon",
            "Advanced macro editor coming soon!")
            
    def _delete_macro(self):
        """Delete selected macro from table."""
        row = self.macro_table.currentRow()
        if row < 0:
            return
            
        name = self.macro_table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "Delete Macro",
            f"Delete macro '{name}'?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.Yes:
            # Find and delete by name
            for profile in self._bridge.profile_manager.get_all_profiles():
                macros = self._bridge.profile_manager.get_macros_for_profile(profile.id)
                for macro in macros:
                    if macro.name == name:
                        self._bridge.profile_manager.remove_macro(macro.id)
                        break
            self._load_macros()
            self.macros_changed.emit()
            
    def _new_profile(self):
        """Create new profile."""
        from PySide6.QtWidgets import QInputDialog
        
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name:
            self._bridge.profile_manager.create_profile(name)
            self._load_profiles()
            
    def _delete_profile(self):
        """Delete selected profile."""
        current = self.profile_list.currentItem()
        if not current:
            return
            
        profile_id = current.data(Qt.UserRole)
        
        if profile_id == "default":
            QMessageBox.warning(self, "Cannot Delete", "Cannot delete the default profile.")
            return
            
        reply = QMessageBox.question(self, "Delete Profile",
            "Delete this profile?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.Yes:
            self._bridge.profile_manager.delete_profile(profile_id)
            self._load_profiles()
            
    def _save_all(self):
        """Save all profiles and macros."""
        if self._bridge and self._bridge.profile_manager:
            self._bridge.profile_manager.save_all()
            QMessageBox.information(self, "Saved", "All macros and profiles saved!")
