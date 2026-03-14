"""
Macro Settings Panel

A panel widget for the sidebar stack to configure macros, profiles, and layers.
"""

import os
import time
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QMenu,
    QSpinBox, QCheckBox, QLineEdit, QGroupBox, QFormLayout, QMessageBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QAbstractItemView, QSlider, QColorDialog, QAbstractSpinBox,
    QRadioButton, QFrame
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtGui import QIcon, QFont, QKeySequence, QAction, QColor
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, Slot, QMetaObject
# FurycubeHID is NOT imported here -- ButtonAction is lazy-imported where needed (line ~2989).
# Loading this module at import time pulled in the hidapi DLL, adding ~200ms to startup.
from macro_system.integration.hardware_manager import get_hardware_manager



class DraggableLabel(QLabel):
    """
    A QLabel that can be dragged to reposition when drag mode is enabled.
    Used for button indicator overlays on the mouse image.
    """
    
    positionChanged = Signal(int, int, int)  # index, x, y
    
    def __init__(self, text: str, index: int, parent=None):
        super().__init__(text, parent)
        self._index = index
        self._drag_enabled = False
        self._dragging = False
        self._drag_start_pos = QPoint()
        
    def set_drag_enabled(self, enabled: bool):
        """Enable or disable drag mode for this label."""
        self._drag_enabled = enabled
        if enabled:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
    
    def mousePressEvent(self, event):
        """Start dragging if enabled and left button pressed."""
        if self._drag_enabled and event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Move the label if dragging."""
        if self._dragging:
            # Calculate new position relative to parent
            new_pos = self.mapToParent(event.pos() - self._drag_start_pos)
            # Keep within parent bounds
            parent = self.parentWidget()
            if parent:
                new_x = max(0, min(new_pos.x(), parent.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent.height() - self.height()))
                self.move(new_x, new_y)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Stop dragging and emit position changed signal."""
        if self._dragging:
            self._dragging = False
            if self._drag_enabled:
                self.setCursor(Qt.OpenHandCursor)
            # Emit signal with new position
            self.positionChanged.emit(self._index, self.x(), self.y())
        super().mouseReleaseEvent(event)


class HotkeyRecordButton(QPushButton):
    """
    A button that records a hotkey when clicked.
    Click to start recording, press a key, it captures it.
    """
    
    hotkeyChanged = Signal(str)
    
    def __init__(self, default_key: str = "F6", parent=None):
        super().__init__(parent)
        self._recording = False
        self._hotkey = default_key
        self.setText(default_key.upper())
        self.setFixedWidth(120)
        self.setToolTip("Click to record a new hotkey")
        self.clicked.connect(self._start_recording)
        self._update_style()
        
    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background: #FF5B06;
                    color: white;
                    border: none;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 91, 6, 0.4);
                    color: #e0e0e0;
                    border: none;
                    padding: 8px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #FF5B06;
                    color: white;
                }
            """)
            
    def _start_recording(self):
        self._recording = True
        self.setText("Press key...")
        self._update_style()
        self.setFocus()
        
    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()
            
            # Build key name first (before checking modifiers)
            key_name = self._key_to_name(key)
            
            # If it's a modifier key alone and no other modifiers, record just the modifier
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_CapsLock):
                # Use native scan code/virtual key to distinguish left/right
                native_key = event.nativeVirtualKey()
                
                # Windows virtual key codes for left/right modifiers
                modifier_names = {
                    # Left modifiers (Windows VK codes)
                    0xA0: "lshift",   # VK_LSHIFT
                    0xA1: "rshift",   # VK_RSHIFT
                    0xA2: "lctrl",    # VK_LCONTROL
                    0xA3: "rctrl",    # VK_RCONTROL
                    0xA4: "lalt",     # VK_LMENU
                    0xA5: "ralt",     # VK_RMENU
                    0x5B: "lwin",     # VK_LWIN
                    0x5C: "rwin",     # VK_RWIN
                    0x14: "capslock", # VK_CAPITAL
                }
                
                # Fallback to generic names
                generic_names = {
                    Qt.Key_Control: "ctrl",
                    Qt.Key_Shift: "shift", 
                    Qt.Key_Alt: "alt",
                    Qt.Key_Meta: "win",
                    Qt.Key_CapsLock: "capslock"
                }
                
                full_key = modifier_names.get(native_key, generic_names.get(key, key_name))
            else:
                # Add modifiers for non-modifier keys
                modifiers = []
                if event.modifiers() & Qt.ControlModifier:
                    modifiers.append("ctrl")
                if event.modifiers() & Qt.ShiftModifier:
                    modifiers.append("shift")
                if event.modifiers() & Qt.AltModifier:
                    modifiers.append("alt")
                    
                if modifiers:
                    full_key = "+".join(modifiers) + "+" + key_name
                else:
                    full_key = key_name
                
            self._hotkey = full_key
            self.setText(full_key.upper())
            self._recording = False
            self._update_style()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self.setText(self._hotkey.upper())
            self._update_style()
        super().focusOutEvent(event)
        
    def _key_to_name(self, key: int) -> str:
        """Convert Qt key code to key name."""
        # Check special keys FIRST (before A-Z check to prevent conflicts)
        key_map = {
            Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3", Qt.Key_F4: "f4",
            Qt.Key_F5: "f5", Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8",
            Qt.Key_F9: "f9", Qt.Key_F10: "f10", Qt.Key_F11: "f11", Qt.Key_F12: "f12",
            Qt.Key_Escape: "esc", Qt.Key_Tab: "tab", Qt.Key_Backspace: "backspace",
            Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Space: "space",
            Qt.Key_Insert: "insert", Qt.Key_Delete: "delete", Qt.Key_Home: "home",
            Qt.Key_End: "end", Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
            Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_CapsLock: "capslock", Qt.Key_NumLock: "numlock",
            Qt.Key_Pause: "pause", Qt.Key_Print: "printscreen",
            Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift", Qt.Key_Alt: "alt",
            Qt.Key_Meta: "win", Qt.Key_Backtab: "tab",
        }
        
        # Check special keys first
        if key in key_map:
            return key_map[key]
        # Then check A-Z (key codes 65-90)
        elif 65 <= key <= 90:  # Qt.Key_A to Qt.Key_Z
            return chr(key).lower()
        elif Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)
        else:
            return f"key{key}"
            
    def hotkey(self) -> str:
        return self._hotkey
        
    def setHotkey(self, key: str):
        self._hotkey = key
        self.setText(key.upper())


class MacroSettingsPanel(QWidget):
    """
    Settings panel for the macro system (fits in content stack).
    """
    
    macros_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = None  # Will be set lazily
        self._recording = False
        self._mouse_listener = None
        self._keyboard_listener = None
        self._current_macro_events = []
        self._updating_dpi_slider = False  # Flag to prevent circular updates
        self.setObjectName("macroPanel")
        # Initialize DPI settings storage
        self._dpi_settings = [] # Will be populated in _setup_ui
        self._restored_dpi_colors = None # Used to restore from saved settings
        self._last_sensor_mode_index = 1 # Track previous sensor mode (Default: HP)
        
        # UI now ONLY uses HardwareManager to avoid thread contention/freezes
        self._hw_manager = get_hardware_manager()
        self._setup_ui()
        
        # Timer for fast UI status updates (macro lists, active markers)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._refresh_macro_status)
        self._refresh_timer.timeout.connect(self._check_active_dpi_from_cache)
        
        # Timer for debouncing DPI save
        self._dpi_save_timer = QTimer(self)
        self._dpi_save_timer.setSingleShot(True)
        self._dpi_save_timer.setInterval(500)  # 500ms delay
        self._dpi_save_timer.timeout.connect(self._on_dpi_debounce_timeout)
        
        # Timer for battery polling (every 3 seconds)
        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(3000)
        self._battery_timer.timeout.connect(self._update_battery_display)
        self._battery_timer.start()
        
        # Initial battery read after 1 second delay
        QTimer.singleShot(1000, self._update_battery_display)
        
        # Auto-initialize and start macro bridge (no manual start/stop needed)
        # This makes all macro features work immediately without user intervention
        QTimer.singleShot(500, self._auto_init_macro_system)
        
    def set_bridge(self, bridge):
        """Set the macro bridge and load data."""
        self._bridge = bridge
        self._load_data()
        
    def _setup_ui(self):
        # Build absolute path for icons
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow.png").replace("\\", "/")
        
        self.setStyleSheet(f"""
            QWidget#macroPanel {{
                background: transparent;
            }}
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin-top: 12px;
                padding: 15px;
                font-weight: bold;
                color: #FF5B06;
                background: rgba(30, 33, 40, 0.6);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
            }}
            QPushButton {{
                background: rgba(26, 26, 26, 0.9);
                color: #e0e0e0;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 91, 6, 0.3);
                border: none;
                color: white;
            }}
            QPushButton:pressed {{
                background: rgba(255, 91, 6, 0.5);
            }}
            QPushButton#primaryBtn {{
                background: rgba(26, 26, 26, 0.9);
                border: none;
                color: white;
            }}
            QLineEdit, QSpinBox, QComboBox {{
                background: rgba(30, 33, 40, 0.9);
                color: #e0e0e0;
                border: none;
                padding: 10px;
                border-radius: 6px;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: none;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 25px;
                border-left: 1px solid rgba(255, 91, 6, 0.3);
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background: rgba(255, 91, 6, 0.3);
            }}
            QComboBox::down-arrow {{
                image: url({down_arrow_path});
                width: 12px;
                height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1a;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }}
            QListWidget {{
                background: rgba(30, 33, 40, 0.5);
                border: none;
                border-radius: 6px;
                color: #e0e0e0;
            }}
            QListWidget::item {{
                padding: 12px;
                border-bottom: 1px solid rgba(80, 80, 80, 0.2);
            }}
            QListWidget::item:selected {{
                background: rgba(255, 91, 6, 0.3);
            }}
            QListWidget::item:hover {{
                background: rgba(255, 91, 6, 0.2);
            }}
            QLabel {{
                color: #e0e0e0;
            }}
            QCheckBox {{
                color: #e0e0e0;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 91, 6, 0.5);
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #FF5B06;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        header = QLabel("HELXAIRO")
        header.setFont(QFont("Segoe UI", 24, QFont.Bold))
        header.setStyleSheet("color: #FF5B06; padding: 0;")
        header_layout.addWidget(header)
        
        header_layout.addStretch()
        
        
        # ===== BATTERY INDICATOR =====
        battery_container = QWidget()
        battery_container.setObjectName("batteryContainer")
        battery_container.setStyleSheet("""
            QWidget#batteryContainer {
                background: rgba(40, 40, 40, 0.8);
                border: none;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        battery_layout = QHBoxLayout(battery_container)
        battery_layout.setContentsMargins(8, 4, 8, 4)
        battery_layout.setSpacing(6)
        
        # Battery icon (visual bar)
        self._battery_bar = QWidget()
        self._battery_bar.setObjectName("batteryBar")
        self._battery_bar.setFixedSize(30, 14)
        self._battery_bar.setStyleSheet("""
            QWidget#batteryBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:1 #8BC34A);
                border: none;
                border-radius: 3px;
            }
        """)
        battery_layout.addWidget(self._battery_bar)
        
        # Percentage text
        self._battery_label = QLabel("---%")
        self._battery_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: bold;")
        battery_layout.addWidget(self._battery_label)
        
        # Charging indicator
        self._charging_label = QLabel("")
        self._charging_label.setStyleSheet("color: #FFC107; font-size: 12px;")
        battery_layout.addWidget(self._charging_label)
        
        header_layout.addWidget(battery_container)
        
        # ===== MOUSE REFRESH BUTTON =====
        # Placed directly to the right of the battery container.
        # Triggers a force_reconnect command via HardwareManager so the app
        # re-enumerates USB/wireless devices without requiring a full restart.
        import os as _os
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        _refresh_icon_path = _os.path.join(_script_dir, "UI Icons", "refresh.png")
        
        self._refresh_btn = QPushButton()
        self._refresh_btn.setObjectName("helxairo_refreshBtn")
        self._refresh_btn.setFixedSize(32, 32)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setToolTip("Refresh mouse connection")
        
        if _os.path.exists(_refresh_icon_path):
            from PySide6.QtGui import QIcon as _QIcon
            self._refresh_btn.setIcon(_QIcon(_refresh_icon_path))
            from PySide6.QtCore import QSize as _QSize
            self._refresh_btn.setIconSize(_QSize(18, 18))
        
        self._refresh_btn.setStyleSheet("""
            QPushButton#helxairo_refreshBtn {
                background: rgba(40, 40, 40, 0.8);
                border: none;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton#helxairo_refreshBtn:hover {
                background: rgba(255, 91, 6, 0.25);
                border-color: transparent;
            }
            QPushButton#helxairo_refreshBtn:pressed {
                background: rgba(255, 91, 6, 0.5);
            }
        """)
        self._refresh_btn.clicked.connect(self._on_refresh_connection_clicked)
        header_layout.addWidget(self._refresh_btn)
        
        layout.addLayout(header_layout)
        
        # ===== CUSTOM TAB BAR (HELXTATS Style) =====
        tab_bar_container = QWidget()
        tab_bar_container.setObjectName("macroTabBarContainer")
        tab_bar_container.setFixedHeight(45)
        tab_bar_container.setStyleSheet("""
            QWidget#macroTabBarContainer {
                background: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 6px;
            }
        """)
        tab_bar_layout = QHBoxLayout(tab_bar_container)
        tab_bar_layout.setContentsMargins(8, 0, 8, 0)
        tab_bar_layout.setSpacing(4)
        
        # Tab button names
        tab_names = ["Home", "DPI", "Macro", "Settings"]
        self._tab_buttons = []
        self._current_tab = 0  # Default to Home tab
        
        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setObjectName(f"macroTabBtn_{i}")
            btn.setFixedHeight(35)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("tab_index", i)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            tab_bar_layout.addWidget(btn)
        
        tab_bar_layout.addStretch()
        layout.addWidget(tab_bar_container)
        
        # ===== PAGE STACK =====
        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("macroPageStack")
        
        
        # === HOME TAB ===
        home_tab = QWidget()
        home_main_layout = QHBoxLayout(home_tab)
        home_main_layout.setContentsMargins(20, 20, 20, 20)
        home_main_layout.setSpacing(20)
        
        # ===== LEFT COLUMN - Button Mappings =====
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # Button mapping combo style
        btn_combo_style = """
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
                min-width: 120px;
            }
            QComboBox:hover {
                border-color: transparent;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 12px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #3a3d45;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #FF5B06;
                color: white;
            }
        """
        
        # Button mappings (1-5) using QPushButton + QMenu for proper submenus
        button_defaults = ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]
        self._button_mapping_btns = []
        
        # Menu style
        menu_style = """
            QMenu {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                padding: 5px;
            }
            QMenu::item {
                padding: 6px 25px 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: #FF5B06;
            }
            QMenu::separator {
                height: 1px;
                background: #4a4d55;
                margin: 4px 10px;
            }
            QMenu::right-arrow {
                width: 12px;
                height: 12px;
            }
        """
        
        for i, default_action in enumerate(button_defaults):
            row = QHBoxLayout()
            row.setSpacing(10)
            
            # Number indicator
            num_label = QLabel(str(i + 1))
            num_label.setObjectName(f"helxairo_btnNum_{i+1}")
            num_label.setFixedSize(24, 24)
            num_label.setAlignment(Qt.AlignCenter)
            num_label.setStyleSheet("""
                QLabel {
                    background: #FF5B06;
                    color: white;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
            row.addWidget(num_label)
            
            # Action button with dropdown menu
            btn = QPushButton(f"   {default_action}")
            btn.setObjectName(f"helxairo_btnMap_{i+1}")
            btn.setProperty("button_index", i)  # Store button index for protection check
            btn.setStyleSheet("""
                QPushButton {
                    background: #2a2d35;
                    color: #e0e0e0;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 20px 8px 16px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    border-color: transparent;
                }
                QPushButton::menu-indicator {
                    subcontrol-position: right center;
                    subcontrol-origin: padding;
                    right: 10px;
                }
            """)
            btn.setCursor(Qt.PointingHandCursor)
            
            # For button 1 (Left Click), show protection dialog instead of menu
            if i == 0:
                btn.clicked.connect(lambda checked, b=btn: self._show_left_click_protection())
                # No menu for button 1 - just the warning
            else:
                # Create menu with submenus for buttons 2-5
                menu = QMenu(btn)
                menu.setStyleSheet(menu_style)
                
                # Store button index for lambda capture
                btn_idx = i
                
                # Buttons submenu
                buttons_menu = menu.addMenu("Buttons")
                buttons_menu.setStyleSheet(menu_style)
                for action in ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]:
                    act = buttons_menu.addAction(action)
                    act.triggered.connect(lambda checked, b=btn, a=action, idx=btn_idx: (b.setText(f"   {a}"), self._on_button_mapping_changed(idx, a)))
                
                # DPI submenu
                dpi_menu = menu.addMenu("DPI Switch")
                dpi_menu.setStyleSheet(menu_style)
                for action in ["DPI Loop", "DPI +", "DPI -"]:
                    act = dpi_menu.addAction(action)
                    act.triggered.connect(lambda checked, b=btn, a=action, idx=btn_idx: (b.setText(f"   {a}"), self._on_button_mapping_changed(idx, a)))
                
                # Scroll submenu
                scroll_menu = menu.addMenu("Scroll")
                scroll_menu.setStyleSheet(menu_style)
                for action in ["Scroll Up", "Scroll Down", "Scroll Left", "Scroll Right"]:
                    act = scroll_menu.addAction(action)
                    act.triggered.connect(lambda checked, b=btn, a=action, idx=btn_idx: (b.setText(f"   {a}"), self._on_button_mapping_changed(idx, a)))
                
                # Multimedia submenu
                media_menu = menu.addMenu("Multimedia")
                media_menu.setStyleSheet(menu_style)
                for action in ["Play/Pause", "Next Track", "Prev Track", "Stop", "Mute", "Volume +", "Volume -"]:
                    act = media_menu.addAction(action)
                    act.triggered.connect(lambda checked, b=btn, a=action, idx=btn_idx: (b.setText(f"   {a}"), self._on_button_mapping_changed(idx, a)))
                
                menu.addSeparator()
                
                # Direct actions (no submenu)
                for action in ["Fire Key", "Combo Key", "Polling Switch", "Macro"]:
                    act = menu.addAction(action)
                    act.triggered.connect(lambda checked, b=btn, a=action, idx=btn_idx: (b.setText(f"   {a}"), self._on_button_mapping_changed(idx, a)))
                
                menu.addSeparator()
                
                disable_act = menu.addAction("Disable")
                disable_act.triggered.connect(lambda checked, b=btn, idx=btn_idx: (b.setText("   Disable"), self._on_button_mapping_changed(idx, "Disable")))
                
                btn.setMenu(menu)
                # Make clicking anywhere on button open the menu (like Furycube)
                btn.clicked.connect(lambda checked, b=btn: b.showMenu())
            
            self._button_mapping_btns.append(btn)
            row.addWidget(btn, 1)
            
            left_layout.addLayout(row)
        
        left_layout.addSpacing(20)
        
        # Debounce Time
        debounce_label = QLabel("Debounce Time")
        debounce_label.setStyleSheet("color: #888; font-size: 11px;")
        left_layout.addWidget(debounce_label)
        
        self._debounce_slider = QSlider(Qt.Horizontal)
        self._debounce_slider.setObjectName("helxairo_debounceSlider")
        self._debounce_slider.setRange(0, 30)
        self._debounce_slider.setValue(10)
        self._debounce_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #2a2d35;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FF5B06;
                border: none;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 3px;
            }
        """)
        self._debounce_slider.setCursor(Qt.PointingHandCursor)
        
        # Spinbox for manual input
        self._debounce_spinbox = QSpinBox()
        self._debounce_spinbox.setObjectName("helxairo_debounceSpinbox")
        self._debounce_spinbox.setRange(0, 30)
        self._debounce_spinbox.setValue(10)
        self._debounce_spinbox.setSuffix("ms")
        self._debounce_spinbox.setFixedWidth(70)
        self._debounce_spinbox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._debounce_spinbox.setStyleSheet("""
            QSpinBox {
                background: transparent;
                color: #FF5B06;
                font-weight: bold;
                border: none;
                padding: 4px;
            }
            QSpinBox:focus {
                color: white;
            }
        """)
        
        # Row layout for slider + spinbox
        db_row = QHBoxLayout()
        db_row.addWidget(self._debounce_slider)
        db_row.addWidget(self._debounce_spinbox)
        
        # Connect signals (Sync Slider <-> SpinBox)
        # Slider -> SpinBox
        self._debounce_slider.valueChanged.connect(lambda v: self._debounce_spinbox.setValue(v))
        
        # SpinBox -> Slider
        self._debounce_spinbox.valueChanged.connect(lambda v: self._debounce_slider.setValue(v))
        
        # Hardware Update (on slider release OR spinbox editing finished)
        self._debounce_slider.sliderReleased.connect(self._on_debounce_changed)
        # Clear focus on finish (Enter key) and then update
        self._debounce_spinbox.editingFinished.connect(lambda: (self._debounce_spinbox.clearFocus(), self._on_debounce_changed()))
        
        left_layout.addLayout(db_row)
        
        left_layout.addStretch()
        home_main_layout.addWidget(left_column)
        
        # ===== CENTER COLUMN - Mouse Diagram with Button Indicators =====
        center_column = QWidget()
        center_column.setAttribute(Qt.WA_TranslucentBackground)
        center_layout = QVBoxLayout(center_column)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container for mouse image with overlays - transparent background
        mouse_container = QWidget()
        mouse_container.setObjectName("helxairo_mouseContainer")
        mouse_container.setMinimumSize(500, 550)
        mouse_container.setFixedSize(500, 550)
        mouse_container.setAttribute(Qt.WA_TranslucentBackground)
        mouse_container.setStyleSheet("background: transparent;")
        
        # Mouse image from Furycube
        mouse_label = QLabel(mouse_container)
        mouse_label.setAlignment(Qt.AlignCenter)
        mouse_label.setStyleSheet("background: transparent;")
        mouse_label.setAttribute(Qt.WA_TranslucentBackground)
        
        # Load mouse image
        import os
        mouse_img_path = os.path.join(os.path.dirname(__file__), "UI Icons", "furycubeMouse.png")
        if os.path.exists(mouse_img_path):
            from PySide6.QtGui import QPixmap
            pixmap = QPixmap(mouse_img_path)
            # Scale to fit while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(450, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            mouse_label.setPixmap(scaled_pixmap)
            mouse_label.resize(scaled_pixmap.size())
            # Center the mouse image in container
            offset_x = (500 - scaled_pixmap.width()) // 2
            mouse_label.move(offset_x, 20)
        else:
            mouse_label.setText("Mouse Image Not Found")
            mouse_label.setStyleSheet("color: #666; font-size: 14px; background: transparent;")
        
        # Button indicator positions (x, y) - based on Furycube mouse layout
        # Looking at mouse image:
        # - Left click area is on the upper-left portion of mouse body
        # - Scroll wheel is the white ring near top-center
        # - 2 side buttons are on the right side of mouse body
        button_positions = [
            (120, 160),  # Button 1 - Left Click (left side of mouse body)
            (75, 115),   # Button 2 - Near scroll area (upper left)
            (170, 65),   # Button 3 - Scroll wheel (top center, white ring area)
            (290, 125),  # Button 4 - Side button (forward - upper side button)
            (320, 145),  # Button 5 - Side button (backward - lower side button)
        ]
        
        # Create numbered circle overlays - HELXAID Orange
        indicator_style = """
            QLabel {
                background: #FF5B06;
                color: white;
                border-radius: 11px;
                font-size: 11px;
                font-weight: bold;
            }
        """
        
        self._button_indicators = []
        for i, (x, y) in enumerate(button_positions):
            indicator = DraggableLabel(str(i + 1), i, mouse_container)
            indicator.setFixedSize(22, 22)
            indicator.setAlignment(Qt.AlignCenter)
            indicator.setStyleSheet(indicator_style)
            indicator.move(x, y)
            indicator.raise_()  # Bring to front
            indicator.positionChanged.connect(self._on_indicator_position_changed)
            self._button_indicators.append(indicator)
        
        center_layout.addWidget(mouse_container, 1, Qt.AlignCenter)
        
        home_main_layout.addWidget(center_column, 1)
        
        # ===== RIGHT COLUMN - Profile & Export =====
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # Profile selector
        self._profile_combo = QComboBox()
        self._profile_combo.setObjectName("helxairo_profileCombo")
        self._profile_combo.addItems(["Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"])
        self._profile_combo.setStyleSheet(btn_combo_style)
        self._profile_combo.setCursor(Qt.PointingHandCursor)
        
        # Load saved profile index BEFORE connecting signal to avoid mismatch
        import json
        saved_profile_idx = 0
        try:
            global_path = os.path.join(os.getenv('APPDATA'), 'HELXAID', 'helxairo_global.json')
            if os.path.exists(global_path):
                with open(global_path, 'r') as f:
                    state = json.load(f)
                    saved_profile_idx = state.get('active_profile_index', 0)
                    print(f"[HELXAIRO-INIT] Loaded saved profile index: {saved_profile_idx}")
        except Exception as e:
            print(f"[HELXAIRO-INIT] Could not load saved profile: {e}")
        
        # Set dropdown to saved profile BEFORE connecting signal
        self._profile_combo.setCurrentIndex(saved_profile_idx)
        self._current_profile_index = saved_profile_idx
        print(f"[HELXAIRO-INIT] Initialized dropdown to Profile {saved_profile_idx + 1}")
        
        # NOW connect the signal
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        right_layout.addWidget(self._profile_combo)
        
        right_layout.addStretch()
        
        # Export/Import/Restore buttons
        action_btn_style = """
            QPushButton {
                background: #3a3d45;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #4a4d55;
                border-color: transparent;
            }
        """
        
        export_btn = QPushButton("Export")
        export_btn.setObjectName("helxairo_exportBtn")
        export_btn.setStyleSheet(action_btn_style)
        export_btn.setCursor(Qt.PointingHandCursor)
        right_layout.addWidget(export_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setObjectName("helxairo_importBtn")
        import_btn.setStyleSheet(action_btn_style)
        import_btn.setCursor(Qt.PointingHandCursor)
        right_layout.addWidget(import_btn)
        
        restore_btn = QPushButton("Restore")
        restore_btn.setObjectName("helxairo_restoreBtn")
        restore_btn.setStyleSheet(action_btn_style)
        restore_btn.setCursor(Qt.PointingHandCursor)
        right_layout.addWidget(restore_btn)
        
        home_main_layout.addWidget(right_column)
        
        self._page_stack.addWidget(home_tab)

        
        # === DPI TAB ===
        dpi_tab = QWidget()
        dpi_scroll = SmoothScrollArea()
        dpi_scroll.setWidgetResizable(True)
        dpi_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        dpi_content = QWidget()
        dpi_layout = QVBoxLayout(dpi_content)
        dpi_layout.setContentsMargins(20, 20, 20, 20)
        dpi_layout.setSpacing(25)
        
        # ===== DPI STAGES SECTION =====
        dpi_stages_section = QWidget()
        dpi_stages_layout = QVBoxLayout(dpi_stages_section)
        dpi_stages_layout.setSpacing(15)
        
        # DPI of Stages row
        stages_row = QHBoxLayout()
        stages_row.setSpacing(10)
        
        stages_icon = QLabel("≡")
        stages_icon.setStyleSheet("color: #888; font-size: 16px;")
        stages_row.addWidget(stages_icon)
        
        stages_label = QLabel("DPI of Stages")
        stages_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        stages_row.addWidget(stages_label)
        
        self._dpi_stages_combo = QComboBox()
        self._dpi_stages_combo.setObjectName("dpiStagesCombo")
        self._dpi_stages_combo.addItems([str(i) for i in range(1, 7)])  # 1-6 stages
        self._dpi_stages_combo.setCurrentText("6")
        self._dpi_stages_combo.setFixedWidth(80)
        self._dpi_stages_combo.setCursor(Qt.PointingHandCursor)
        
        # Build path for down arrow icon (same as global stylesheet)
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow.png").replace("\\", "/")
        
        self._dpi_stages_combo.setStyleSheet(f"""
            QComboBox#dpiStagesCombo {{
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 25px 8px 12px;
                font-size: 12px;
            }}
            QComboBox#dpiStagesCombo:hover {{
                border-color: transparent;
            }}
            QComboBox#dpiStagesCombo::drop-down {{
                border: none;
                background: transparent;
                width: 20px;
                subcontrol-position: right center;
                subcontrol-origin: padding;
            }}
            QComboBox#dpiStagesCombo::down-arrow {{
                image: url({arrow_path});
                width: 10px;
                height: 10px;
            }}
            QComboBox#dpiStagesCombo QAbstractItemView {{
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }}
        """)
        self._dpi_stages_combo.currentTextChanged.connect(self._on_dpi_stages_changed)
        stages_row.addWidget(self._dpi_stages_combo)
        
        stages_row.addStretch()
        dpi_stages_layout.addLayout(stages_row)
        
        # DPI Slider with value display
        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        
        self._dpi_slider = QSlider(Qt.Horizontal)
        self._dpi_slider.setObjectName("helxairo_dpiSlider")
        self._dpi_slider.setRange(20, 440)  # (1000-22000)/50 = 20-440 steps
        self._dpi_slider.setValue(32)  # 1600 DPI default
        self._dpi_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #2a2d35;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FF5B06;
                border: none;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 3px;
            }
        """)
        self._dpi_slider.valueChanged.connect(self._on_dpi_slider_changed)
        slider_row.addWidget(self._dpi_slider, 1)
        
        # DPI value control (unified container: - | value | +)
        dpi_value_container = QWidget()
        dpi_value_container.setObjectName("dpiValueContainer")
        dpi_value_container.setFixedHeight(32)
        dpi_value_container.setFixedWidth(180) # Increased from 150 to prevent truncation of high DPI values
        dpi_value_container.setStyleSheet("""
            QWidget#dpiValueContainer {
                background: #1a1d25;
                border: none;
                border-radius: 4px;
            }
        """)
        value_row = QHBoxLayout(dpi_value_container)
        value_row.setContentsMargins(8, 0, 8, 0)
        value_row.setSpacing(6)
        
        # Minus button - match container height for perfect alignment
        dpi_minus_btn = QPushButton("-")
        dpi_minus_btn.setObjectName("helxairo_dpiMinusBtn")
        dpi_minus_btn.setFixedHeight(30)  # Same as container minus margins
        dpi_minus_btn.setFixedWidth(28)
        dpi_minus_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 20px;
                font-weight: bold;
                text-align: center;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        dpi_minus_btn.clicked.connect(lambda: self._adjust_dpi(-50))
        value_row.addWidget(dpi_minus_btn)
        
        # DPI value input field - allows typing a DPI value directly
        self._dpi_value_input = QLineEdit("1600")
        self._dpi_value_input.setObjectName("helxairo_dpiValueInput")
        self._dpi_value_input.setAlignment(Qt.AlignCenter)
        self._dpi_value_input.setFixedHeight(30)
        self._dpi_value_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #e0e0e0;
                border: none;
                font-size: 14px;
                padding: 0px;
                margin: 0px;
                selection-background-color: #FF5B06;
            }
            QLineEdit:focus {
                color: white;
            }
        """)
        self._dpi_value_input.setMinimumWidth(80)
        # Commit the typed DPI when user presses Enter or leaves the field
        self._dpi_value_input.returnPressed.connect(self._on_dpi_input_committed)
        self._dpi_value_input.editingFinished.connect(self._on_dpi_input_committed)
        value_row.addWidget(self._dpi_value_input, 1)
        
        # Plus button - match container height for perfect alignment
        dpi_plus_btn = QPushButton("+")
        dpi_plus_btn.setObjectName("helxairo_dpiPlusBtn")
        dpi_plus_btn.setFixedHeight(30)  # Same as container minus margins  
        dpi_plus_btn.setFixedWidth(28)
        dpi_plus_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 20px;
                font-weight: bold;
                text-align: center;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        dpi_plus_btn.clicked.connect(lambda: self._adjust_dpi(50))
        value_row.addWidget(dpi_plus_btn)
        
        slider_row.addWidget(dpi_value_container)
        
        dpi_stages_layout.addLayout(slider_row)
        
        # DPI Stage Boxes
        stages_boxes_row = QHBoxLayout()
        stages_boxes_row.setSpacing(12)
        
        # Default DPI values and colors matching website
        dpi_defaults = [
            (650, "#ff0000"),    # Red
            (1600, "#9c27b0"),   # Purple
            (2400, "#ffd700"),   # Yellow
            (3200, "#00ff00"),   # Green
            (4000, "#00ffff"),   # Cyan
            (5000, "#0000ff"),   # Blue
        ]
        
        # Override with saved colors if available
        if hasattr(self, '_restored_dpi_colors') and self._restored_dpi_colors is not None and len(self._restored_dpi_colors) == len(dpi_defaults):
             # Use saved values (dpi, color)
             self._dpi_settings = [list(x) for x in self._restored_dpi_colors] # Convert to list to make mutable
             print("[HELXAIRO] Applied saved DPI colors")
        else:
            self._dpi_settings = [list(x) for x in dpi_defaults] # Initialize with defaults, convert to list
        
        self._dpi_stage_boxes = []
        self._current_dpi_stage = 1  # Second stage (1600) is default selected
        
        for i, (dpi_val, color) in enumerate(self._dpi_settings): # Iterate over self._dpi_settings
            box = QWidget()
            box.setObjectName("dpiStageBox")
            box.setProperty("stage_index", i)
            box.setCursor(Qt.PointingHandCursor)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 6, 8, 4)
            box_layout.setSpacing(2)
            
            # DPI value label - no border!
            value_label = QLabel(str(dpi_val))
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 500; background: transparent; border: none;")
            box_layout.addWidget(value_label)
            
            # Color bar - no border, just color
            color_bar = QLabel()
            color_bar.setFixedHeight(4)
            color_bar.setStyleSheet(f"background: {color}; border: none;")
            box_layout.addWidget(color_bar)
            
            # Selection indicator (triangle) - orange like reference
            indicator = QLabel("▲")
            indicator.setAlignment(Qt.AlignCenter)
            indicator.setStyleSheet("color: #FF8C00; font-size: 10px; background: transparent; border: none;")
            indicator.setVisible(i == self._current_dpi_stage)
            box_layout.addWidget(indicator)
            
            # Box style - use #dpiStageBox to target ONLY the parent, not children
            if i == self._current_dpi_stage:
                box.setStyleSheet("""
                    QWidget#dpiStageBox {
                        background: #1a1d25;
                        border: none;
                        border-radius: 4px;
                    }
                """)
            else:
                box.setStyleSheet("""
                    QWidget#dpiStageBox {
                        background: transparent;
                        border: none;
                        border-radius: 4px;
                    }
                """)
            box.setFixedSize(85, 65)
            
            # Store references
            box.value_label = value_label
            box.color_bar = color_bar
            box.indicator = indicator
            box.dpi_value = dpi_val
            box.color = color
            
            # Click handler logic
            # We need separate handlers for selecting the stage vs picking color
            # Since color bar is inside the box, we can use child event filter or specific widget click
            
            # Make color bar clickable
            box.color_bar.setCursor(Qt.PointingHandCursor)
            # We use a custom mousePressEvent for the color bar
            # We need to use EventFilter or subclass, but lambda assignment to instance method works in Python
            
            def make_color_click_handler(idx):
                def handler(event):
                    if event.button() == Qt.LeftButton:
                        self._pick_dpi_color(idx)
                        event.accept()
                return handler
                
            box.color_bar.mousePressEvent = make_color_click_handler(i)
            
            # Main box click selects stage (ignore if clicking child utilized)
            # The box.mousePressEvent overrides children unless we are careful.
            # But here color_bar is on top. If we assign mousePressEvent to color_bar, it should catch it first.
            box.mousePressEvent = lambda e, idx=i: self._on_stage_clicked(idx)
            
            self._dpi_stage_boxes.append(box)
            stages_boxes_row.addWidget(box)
        
        stages_boxes_row.addStretch()
        dpi_stages_layout.addLayout(stages_boxes_row)
        
        dpi_layout.addWidget(dpi_stages_section)
        
        # ===== POLLING RATE SECTION =====
        polling_section = QWidget()
        polling_layout = QVBoxLayout(polling_section)
        polling_layout.setSpacing(10)
        
        polling_header = QHBoxLayout()
        polling_icon = QLabel("≡")
        polling_icon.setStyleSheet("color: #888; font-size: 16px;")
        polling_header.addWidget(polling_icon)
        polling_label = QLabel("Polling Rate")
        polling_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        polling_header.addWidget(polling_label)
        polling_header.addStretch()
        polling_layout.addLayout(polling_header)
        
        polling_btns_row = QHBoxLayout()
        polling_btns_row.setSpacing(8)
        
        polling_rates = ["125Hz", "250Hz", "500Hz", "1000Hz"]
        self._polling_buttons = []
        self._current_polling = 3  # 1000Hz default
        
        for i, rate in enumerate(polling_rates):
            btn = QPushButton(rate)
            btn.setObjectName(f"helxairo_pollingBtn_{rate}")
            btn.setFixedSize(90, 35)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("rate_index", i)
            
            if i == self._current_polling:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #ff5b06;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #2a2d35;
                        color: #e0e0e0;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        border-color: transparent;
                    }
                """)
            
            btn.clicked.connect(lambda checked, idx=i: self._select_polling_rate(idx))
            self._polling_buttons.append(btn)
            polling_btns_row.addWidget(btn)
        
        polling_btns_row.addStretch()
        polling_layout.addLayout(polling_btns_row)
        
        dpi_layout.addWidget(polling_section)
        
        # ===== SENSOR SETTINGS SECTION =====
        sensor_section = QWidget()
        sensor_section.setObjectName("helxairo_sensorSection")
        sensor_layout = QVBoxLayout(sensor_section)
        sensor_layout.setSpacing(15)
        
        sensor_header = QHBoxLayout()
        sensor_icon = QLabel("≡")
        sensor_icon.setStyleSheet("color: #888; font-size: 16px;")
        sensor_header.addWidget(sensor_icon)
        sensor_label = QLabel("Sensor settings")
        sensor_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        sensor_header.addWidget(sensor_label)
        sensor_header.addStretch()
        sensor_layout.addLayout(sensor_header)
        
        sensor_controls = QHBoxLayout()
        sensor_controls.setSpacing(30)
        
        # Select mode
        mode_col = QVBoxLayout()
        mode_label = QLabel("Select mode")
        mode_label.setStyleSheet("color: #888; font-size: 11px;")
        mode_col.addWidget(mode_label)
        
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("helxairo_modeCombo")
        self._mode_combo.addItems(["LP", "HP", "Corded"])
        self._mode_combo.setFixedWidth(100)
        self._mode_combo.setStyleSheet("""
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                selection-background-color: #409eff;
            }
        """)
        mode_col.addWidget(self._mode_combo)
        sensor_controls.addLayout(mode_col)
        
        # Highest performance
        perf_col = QVBoxLayout()
        perf_row = QHBoxLayout()
        
        self._highest_perf_check = QCheckBox("Highest performance")
        self._highest_perf_check.setObjectName("helxairo_highestPerfCheck")
        self._highest_perf_check.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        perf_row.addWidget(self._highest_perf_check)
        
        perf_col.addLayout(perf_row)
        
        self._perf_time_combo = QComboBox()
        self._perf_time_combo.setObjectName("helxairo_perfTimeCombo")
        self._perf_time_combo.addItems(["10s", "30s", "1min", "2min", "5min", "10min"])
        self._perf_time_combo.setCurrentText("1min")
        self._perf_time_combo.setFixedWidth(80)
        self._perf_time_combo.setStyleSheet("""
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                selection-background-color: #409eff;
            }
        """)
        self._perf_time_combo.currentTextChanged.connect(self._on_perf_time_changed)
        perf_col.addWidget(self._perf_time_combo)
        sensor_controls.addLayout(perf_col)
        
        # Toggle switches
        toggles_col = QVBoxLayout()
        toggles_col.setSpacing(8)
        
        toggle_style = """
            QCheckBox {
                color: #e0e0e0;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 36px;
                height: 20px;
                border-radius: 10px;
                background: #4a4d55;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06;
            }
        """
        
        self._ripple_toggle = QCheckBox("Ripple control")
        self._ripple_toggle.setObjectName("helxairo_rippleToggle")
        self._ripple_toggle.setStyleSheet(toggle_style)
        toggles_col.addWidget(self._ripple_toggle)
        
        self._angle_snap_toggle = QCheckBox("Angle snap")
        self._angle_snap_toggle.setObjectName("helxairo_angleSnapToggle")
        self._angle_snap_toggle.setStyleSheet(toggle_style)
        toggles_col.addWidget(self._angle_snap_toggle)
        
        sensor_controls.addLayout(toggles_col)
        sensor_controls.addLayout(toggles_col)
        sensor_controls.addStretch()
        
        sensor_layout.addLayout(sensor_controls)
        dpi_layout.addWidget(sensor_section)
        
        # Connect signals
        self._mode_combo.currentIndexChanged.connect(self._on_sensor_mode_changed)
        self._highest_perf_check.toggled.connect(self._on_highest_perf_changed)
        self._perf_time_combo.currentTextChanged.connect(self._on_perf_time_changed)
        self._ripple_toggle.toggled.connect(self._on_ripple_changed)
        self._angle_snap_toggle.toggled.connect(self._on_angle_snap_changed)
        
        # ===== DPI EFFECT SECTION =====
        effect_section = QWidget()
        effect_section.setObjectName("helxairo_effectSection")
        effect_layout = QVBoxLayout(effect_section)
        effect_layout.setSpacing(15)
        
        effect_header = QHBoxLayout()
        effect_icon = QLabel("≡")
        effect_icon.setStyleSheet("color: #888; font-size: 16px;")
        effect_header.addWidget(effect_icon)
        effect_label = QLabel("DPI effect")
        effect_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        effect_header.addWidget(effect_label)
        effect_header.addStretch()
        effect_layout.addLayout(effect_header)
        
        effect_controls = QHBoxLayout()
        effect_controls.setSpacing(30)
        
        # Effect mode
        self._effect_combo = QComboBox()
        self._effect_combo.setObjectName("helxairo_effectCombo")
        # Map Mode ID to Name. Skipping Mode 3 as per user report.
        effect_modes = [
            (0, "Off"),
            (1, "Steady"),
            (2, "Breathing")
        ]
        for mode_id, name in effect_modes:
            self._effect_combo.addItem(name, mode_id)
            
        self._effect_combo.setFixedWidth(120)
        self._effect_combo.setStyleSheet("""
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                selection-background-color: #409eff;
            }
        """)
        effect_controls.addWidget(self._effect_combo)
        
        # Brightness slider
        brightness_col = QHBoxLayout()
        brightness_col.setSpacing(10)
        brightness_label = QLabel("Brightness")
        brightness_label.setStyleSheet("color: #888; font-size: 11px;")
        brightness_col.addWidget(brightness_label)
        
        self._brightness_slider = QSlider(Qt.Horizontal)
        self._brightness_slider.setObjectName("helxairo_brightnessSlider")
        self._brightness_slider.setRange(1, 5)
        self._brightness_slider.setValue(5)
        self._brightness_slider.setFixedWidth(120)
        self._brightness_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #2a2d35;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::groove:horizontal:disabled {
                background: #202020;
                border-color: transparent;
            }
            QSlider::handle:horizontal {
                background: #FF5B06;
                border: none;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:disabled {
                background: #404040;
                border: none;
            }
            QSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal:disabled {
                background: #404040;
            }
        """)
        brightness_col.addWidget(self._brightness_slider)
        
        self._brightness_value = QLabel("5")
        self._brightness_value.setObjectName("helxairo_brightnessValue")
        self._brightness_value.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        self._brightness_slider.valueChanged.connect(lambda v: self._brightness_value.setText(str(v)))
        brightness_col.addWidget(self._brightness_value)
        
        effect_controls.addLayout(brightness_col)
        
        # Speed slider
        speed_col = QHBoxLayout()
        speed_col.setSpacing(10)
        speed_label = QLabel("Speed")
        speed_label.setStyleSheet("color: #888; font-size: 11px;")
        speed_col.addWidget(speed_label)
        
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setObjectName("helxairo_speedSlider")
        self._speed_slider.setRange(1, 5)  # Firmware only supports 1-5
        self._speed_slider.setValue(3)
        self._speed_slider.setFixedWidth(120)
        self._speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #2a2d35;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::groove:horizontal:disabled {
                background: #202020;
                border-color: transparent;
            }
            QSlider::handle:horizontal {
                background: #FF5B06;
                border: none;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:disabled {
                background: #404040;
                border: none;
            }
            QSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal:disabled {
                background: #404040;
            }
        """)
        speed_col.addWidget(self._speed_slider)
        
        self._speed_value = QLabel("3")
        self._speed_value.setObjectName("helxairo_speedValue")
        self._speed_value.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        self._speed_slider.valueChanged.connect(lambda v: self._speed_value.setText(str(v)))
        speed_col.addWidget(self._speed_value)
        
        effect_controls.addLayout(speed_col)
        effect_controls.addStretch()
        
        effect_layout.addLayout(effect_controls)
        dpi_layout.addWidget(effect_section)
        
        # Connect DPI Effect signals
        # Connect DPI Effect signals
        self._effect_combo.currentIndexChanged.connect(self._on_dpi_effect_changed)
        
        # Update labels on drag (Visual feedback)
        self._brightness_slider.valueChanged.connect(lambda v: self._brightness_value.setText(str(v)))
        self._speed_slider.valueChanged.connect(lambda v: self._speed_value.setText(str(v)))
        
        # Apply settings ONLY on release (MouseUp) to prevent flooding HID
        self._brightness_slider.sliderReleased.connect(lambda: self._on_dpi_brightness_changed(self._brightness_slider.value()))
        self._speed_slider.sliderReleased.connect(lambda: self._on_dpi_speed_changed(self._speed_slider.value()))
        
        dpi_layout.addStretch()
        
        dpi_scroll.setWidget(dpi_content)
        dpi_tab_layout = QVBoxLayout(dpi_tab)
        dpi_tab_layout.setContentsMargins(0, 0, 0, 0)
        dpi_tab_layout.addWidget(dpi_scroll)
        
        self._page_stack.addWidget(dpi_tab)
        
        # === MACRO TAB ===
        macro_tab = QWidget()
        macro_scroll = SmoothScrollArea()
        macro_scroll.setWidgetResizable(True)
        macro_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        macro_content = QWidget()
        macro_content.setStyleSheet("background: transparent;")
        macro_layout = QVBoxLayout(macro_content)
        macro_layout.setContentsMargins(20, 20, 20, 20)
        macro_layout.setSpacing(15)

        # Shared QGroupBox style — matches Settings tab exactly
        _grp_style = """
            QGroupBox {
                color: #ff5b06;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """

        # Shared button style — matches global panel style
        _btn_style = """
            QPushButton {
                background: #3a3d45;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4a4d55;
                border-color: transparent;
                color: white;
            }
            QPushButton:pressed { background: #ff5b06; color: white; }
            QPushButton:disabled { color: #555; border-color: transparent; }
        """

        # Shared combo style — matches DPI tab
        _combo_style = """
            QComboBox {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QComboBox:hover { border-color: transparent; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }
        """
        # ── Macro Editor (New Top Section) ──────────────────────────────
        editor_layout = QHBoxLayout()
        editor_layout.setSpacing(20)

        # Left Column: Macro list
        col1 = QVBoxLayout()
        col1_lbl = QLabel("Macro list")
        col1_lbl.setStyleSheet("color: #e0e0e0; font-family: Segoe UI; font-size: 13px;")
        col1.addWidget(col1_lbl)

        self.editor_macro_list = QListWidget()
        self.editor_macro_list.setObjectName("helxairo_editorMacroList")
        self.editor_macro_list.setMinimumHeight(350)
        self.editor_macro_list.setStyleSheet("""
            QListWidget {
                background: #2a2d35;
                border: none;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 13px;
            }
            QListWidget::item { padding: 8px 12px; }
            QListWidget::item:selected { background: #FF5B06; color: white; }
            QListWidget::item:hover { background: #3a3d45; }
        """)
        col1.addWidget(self.editor_macro_list)

        col1_btns = QHBoxLayout()
        col1_btns.setSpacing(10)
        self.editor_new_macro_btn = QPushButton("New Macro")
        self.editor_new_macro_btn.setStyleSheet(_btn_style)
        self.editor_new_macro_btn.setCursor(Qt.PointingHandCursor)
        col1_btns.addWidget(self.editor_new_macro_btn)

        self.editor_delete_macro_btn = QPushButton("Delete")
        self.editor_delete_macro_btn.setStyleSheet(_btn_style)
        self.editor_delete_macro_btn.setCursor(Qt.PointingHandCursor)
        col1_btns.addWidget(self.editor_delete_macro_btn)

        col1.addLayout(col1_btns)
        editor_layout.addLayout(col1, 1)

        # Middle Column: List of keys
        col2 = QVBoxLayout()
        col2_lbl = QLabel("List of keys")
        col2_lbl.setStyleSheet("color: #e0e0e0; font-family: Segoe UI; font-size: 13px;")
        col2.addWidget(col2_lbl)

        self.editor_keys_list = QListWidget()
        self.editor_keys_list.setObjectName("helxairo_editorKeysList")
        self.editor_keys_list.setMinimumHeight(350)
        self.editor_keys_list.setStyleSheet(self.editor_macro_list.styleSheet())
        col2.addWidget(self.editor_keys_list)

        col2_btns = QHBoxLayout()
        col2_btns.setSpacing(10)

        self.editor_modify_key_btn = QPushButton("Modify")
        self.editor_modify_key_btn.setStyleSheet(_btn_style)
        self.editor_modify_key_btn.setCursor(Qt.PointingHandCursor)
        col2_btns.addWidget(self.editor_modify_key_btn)

        self.editor_delete_key_btn = QPushButton("Delete")
        self.editor_delete_key_btn.setStyleSheet(_btn_style)
        self.editor_delete_key_btn.setCursor(Qt.PointingHandCursor)
        col2_btns.addWidget(self.editor_delete_key_btn)

        col2.addLayout(col2_btns)
        editor_layout.addLayout(col2, 1)

        # Right Column: Controls
        col3 = QVBoxLayout()
        col3.setSpacing(10)
        
        # We need a spacer above to align controls properly with lists
        col3.addSpacing(22)

        self.editor_start_record_btn = QPushButton("  Start recording")
        self.editor_start_record_btn.setStyleSheet("""
            QPushButton {
                background: rgba(220, 50, 50, 0.15);
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover { background: rgba(220, 50, 50, 0.3); color: white; }
            QPushButton:pressed { background: rgba(220, 50, 50, 0.5); }
        """)
        self.editor_start_record_btn.setCursor(Qt.PointingHandCursor)
        # Adding a red dot using Unicode
        self.editor_start_record_btn.setText("🔴 Start recording")
        col3.addWidget(self.editor_start_record_btn)

        col3.addSpacing(15)

        _radio_style = """
            QRadioButton { color: #e0e0e0; font-family: Segoe UI; font-size: 13px; spacing: 8px; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; background: #2a2d35; border: none; }
            QRadioButton::indicator:checked { background: #FF5B06; border: none; }
        """
        
        # Delay section
        self.rb_auto_delay = QRadioButton("Auto insert delay")
        self.rb_auto_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_auto_delay)

        self.rb_default_delay = QRadioButton("Default delay")
        self.rb_default_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_default_delay)

        self.spin_default_delay = QSpinBox()
        self.spin_default_delay.setRange(0, 9999)
        self.spin_default_delay.setValue(10)
        self.spin_default_delay.setAlignment(Qt.AlignCenter)
        self.spin_default_delay.setStyleSheet("""
            QSpinBox { background: #2a2d35; color: #e0e0e0; border: none; border-radius: 4px; padding: 4px; margin-left: 24px; }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; }
        """)
        col3.addWidget(self.spin_default_delay)

        col3.addSpacing(15)

        # Cycle section
        self.rb_cycle_release = QRadioButton("Cycle until the button is released")
        self.rb_cycle_release.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_release)

        self.rb_cycle_any = QRadioButton("Cycle until any button is pressed")
        self.rb_cycle_any.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_any)

        self.rb_cycle_press = QRadioButton("Cycle until the button is pressed")
        self.rb_cycle_press.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_press)

        self.rb_cycle_times = QRadioButton("Cycle Times")
        self.rb_cycle_times.setStyleSheet(_radio_style)
        self.rb_cycle_times.setChecked(True)
        col3.addWidget(self.rb_cycle_times)

        self.spin_cycle_times = QSpinBox()
        self.spin_cycle_times.setRange(1, 9999)
        self.spin_cycle_times.setValue(1)
        self.spin_cycle_times.setAlignment(Qt.AlignCenter)
        self.spin_cycle_times.setStyleSheet(self.spin_default_delay.styleSheet())
        col3.addWidget(self.spin_cycle_times)

        col3.addSpacing(15)

        # Insert Command
        lbl_insert = QLabel("Insert command")
        lbl_insert.setStyleSheet("color: #e0e0e0; font-family: Segoe UI; font-size: 13px;")
        col3.addWidget(lbl_insert)

        self.combo_insert_cmd = QComboBox()
        self.combo_insert_cmd.setStyleSheet(_combo_style)
        col3.addWidget(self.combo_insert_cmd)

        col3.addSpacing(10)

        # Save Button
        self.editor_save_btn = QPushButton("Save")
        self.editor_save_btn.setStyleSheet("""
            QPushButton {
                background: #FF5B06;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #ff7530; }
            QPushButton:pressed { background: #e04b00; }
        """)
        self.editor_save_btn.setCursor(Qt.PointingHandCursor)
        col3.addWidget(self.editor_save_btn)
        
        col3.addStretch()
        editor_layout.addLayout(col3, 1)

        macro_layout.addLayout(editor_layout)
        
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("background-color: #4a4d55;")
        macro_layout.addWidget(sep)
        macro_layout.addSpacing(10)

        # ── Quick Actions ──────────────────────────────
        quick_group = QGroupBox("Quick Actions")
        quick_group.setStyleSheet(_grp_style)
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setSpacing(12)

        # Auto-Clicker row
        ac_layout = QHBoxLayout()
        ac_layout.setSpacing(10)

        ac_lbl = QLabel("Auto-Clicker:")
        ac_lbl.setStyleSheet("color: #e0e0e0;")
        ac_layout.addWidget(ac_lbl)

        self.ac_button = QComboBox()
        self.ac_button.setObjectName("helxairo_acType")
        self.ac_button.addItems(["Left Click", "Right Click", "Middle Click", "Custom Key"])
        self.ac_button.setFixedWidth(130)
        self.ac_button.setStyleSheet(_combo_style)
        self.ac_button.currentTextChanged.connect(self._on_ac_type_changed)
        ac_layout.addWidget(self.ac_button)

        self.ac_custom_key = HotkeyRecordButton("E")
        self.ac_custom_key.setFixedWidth(80)
        self.ac_custom_key.setVisible(False)
        ac_layout.addWidget(self.ac_custom_key)

        interval_lbl = QLabel("Interval:")
        interval_lbl.setStyleSheet("color: #e0e0e0;")
        ac_layout.addWidget(interval_lbl)

        self.ac_interval = QSpinBox()
        self.ac_interval.setObjectName("helxairo_acInterval")
        self.ac_interval.setRange(1, 5000)
        self.ac_interval.setValue(100)
        self.ac_interval.setSuffix(" ms")
        self.ac_interval.setFixedWidth(95)
        ac_layout.addWidget(self.ac_interval)

        hotkey_lbl = QLabel("Hotkey:")
        hotkey_lbl.setStyleSheet("color: #e0e0e0;")
        ac_layout.addWidget(hotkey_lbl)

        self.ac_hotkey = HotkeyRecordButton("F8")
        ac_layout.addWidget(self.ac_hotkey)

        self.ac_create_btn = QPushButton("Create")
        self.ac_create_btn.setObjectName("helxairo_acCreateBtn")
        self.ac_create_btn.setCursor(Qt.PointingHandCursor)
        self.ac_create_btn.setStyleSheet(_btn_style)
        self.ac_create_btn.clicked.connect(self._create_autoclicker)
        ac_layout.addWidget(self.ac_create_btn)

        ac_layout.addStretch()
        quick_layout.addLayout(ac_layout)

        # Button Remap row
        remap_layout = QHBoxLayout()
        remap_layout.setSpacing(10)

        remap_lbl = QLabel("Button Remap:")
        remap_lbl.setStyleSheet("color: #e0e0e0;")
        remap_layout.addWidget(remap_lbl)

        self.remap_from = QComboBox()
        self.remap_from.setObjectName("helxairo_remapFrom")
        self.remap_from.addItems(["X1 (Side)", "X2 (Side)", "Middle"])
        self.remap_from.setFixedWidth(120)
        self.remap_from.setStyleSheet(_combo_style)
        remap_layout.addWidget(self.remap_from)

        arrow_lbl = QLabel("→")
        arrow_lbl.setStyleSheet("color: #FF5B06; font-size: 16px;")
        remap_layout.addWidget(arrow_lbl)

        self.remap_to = HotkeyRecordButton("ctrl")
        remap_layout.addWidget(self.remap_to)

        self.remap_create_btn = QPushButton("Create")
        self.remap_create_btn.setObjectName("helxairo_remapCreateBtn")
        self.remap_create_btn.setCursor(Qt.PointingHandCursor)
        self.remap_create_btn.setStyleSheet(_btn_style)
        self.remap_create_btn.clicked.connect(self._create_remap)
        remap_layout.addWidget(self.remap_create_btn)

        remap_layout.addStretch()
        quick_layout.addLayout(remap_layout)

        macro_layout.addWidget(quick_group)

        # ── Macro Recorder ────────────────────────────
        recorder_group = QGroupBox("Record Macro")
        recorder_group.setStyleSheet(_grp_style)
        recorder_layout = QVBoxLayout(recorder_group)
        recorder_layout.setSpacing(12)

        # Initialize recorder state
        self._recorder = None
        self._player = None
        self._current_recording = None

        # Record controls row
        record_controls = QHBoxLayout()
        record_controls.setSpacing(10)

        self.record_btn = QPushButton("Record")
        self.record_btn.setObjectName("helxairo_recordBtn")
        self.record_btn.setFixedWidth(120)
        self.record_btn.setCursor(Qt.PointingHandCursor)
        self.record_btn.setStyleSheet(_btn_style)
        self.record_btn.clicked.connect(self._toggle_recording)
        record_controls.addWidget(self.record_btn)

        self.record_status = QLabel("Ready")
        self.record_status.setStyleSheet("color: #888; font-size: 12px;")
        record_controls.addWidget(self.record_status)

        record_controls.addStretch()

        self.action_count_label = QLabel("0 actions")
        self.action_count_label.setStyleSheet("color: #A43F96; font-size: 12px; font-weight: bold;")
        record_controls.addWidget(self.action_count_label)

        self.playback_status = QLabel("")
        self.playback_status.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 12px;")
        record_controls.addWidget(self.playback_status)

        recorder_layout.addLayout(record_controls)

        # Options row
        options_row = QHBoxLayout()
        options_row.setSpacing(15)

        self.record_mouse_cb = QCheckBox("Mouse Clicks")
        self.record_mouse_cb.setChecked(True)
        options_row.addWidget(self.record_mouse_cb)

        self.record_movement_cb = QCheckBox("Mouse Movement")
        self.record_movement_cb.setChecked(False)
        options_row.addWidget(self.record_movement_cb)

        self.record_keyboard_cb = QCheckBox("Keyboard")
        self.record_keyboard_cb.setChecked(True)
        options_row.addWidget(self.record_keyboard_cb)

        options_row.addStretch()
        recorder_layout.addLayout(options_row)

        # Playback options row
        playback_row = QHBoxLayout()
        playback_row.setSpacing(10)

        speed_lbl = QLabel("Speed:")
        speed_lbl.setStyleSheet("color: #e0e0e0;")
        playback_row.addWidget(speed_lbl)

        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("helxairo_speedCombo")
        self.speed_combo.addItems(["0.5x", "1x", "2x", "4x"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setFixedWidth(80)
        self.speed_combo.setStyleSheet(_combo_style)
        playback_row.addWidget(self.speed_combo)

        loops_lbl = QLabel("Loops:")
        loops_lbl.setStyleSheet("color: #e0e0e0;")
        playback_row.addWidget(loops_lbl)

        self.loop_spin = QSpinBox()
        self.loop_spin.setObjectName("helxairo_loopSpin")
        self.loop_spin.setRange(0, 999)
        self.loop_spin.setValue(1)
        self.loop_spin.setFixedWidth(70)
        self.loop_spin.setToolTip("0 = infinite loop")
        playback_row.addWidget(self.loop_spin)

        hotkey2_lbl = QLabel("Hotkey:")
        hotkey2_lbl.setStyleSheet("color: #e0e0e0;")
        playback_row.addWidget(hotkey2_lbl)

        self.playback_hotkey = HotkeyRecordButton("F9")
        playback_row.addWidget(self.playback_hotkey)

        playback_row.addStretch()
        recorder_layout.addLayout(playback_row)

        # Save/Play/Clear buttons
        save_row = QHBoxLayout()
        save_row.setSpacing(8)

        self.save_recording_btn = QPushButton("Save Recording")
        self.save_recording_btn.setObjectName("helxairo_saveRec")
        self.save_recording_btn.setCursor(Qt.PointingHandCursor)
        self.save_recording_btn.setStyleSheet(_btn_style)
        self.save_recording_btn.clicked.connect(self._save_recording)
        self.save_recording_btn.setEnabled(False)
        save_row.addWidget(self.save_recording_btn)

        self.play_recording_btn = QPushButton("Play")
        self.play_recording_btn.setObjectName("helxairo_playRec")
        self.play_recording_btn.setCursor(Qt.PointingHandCursor)
        self.play_recording_btn.setStyleSheet(_btn_style)
        self.play_recording_btn.clicked.connect(self._play_recording)
        self.play_recording_btn.setEnabled(False)
        save_row.addWidget(self.play_recording_btn)

        self.clear_recording_btn = QPushButton("Clear")
        self.clear_recording_btn.setObjectName("helxairo_clearRec")
        self.clear_recording_btn.setCursor(Qt.PointingHandCursor)
        self.clear_recording_btn.setStyleSheet(_btn_style)
        self.clear_recording_btn.clicked.connect(self._clear_recording)
        save_row.addWidget(self.clear_recording_btn)

        save_row.addStretch()
        recorder_layout.addLayout(save_row)

        macro_layout.addWidget(recorder_group)

        # ── Active Macros ─────────────────────────────
        active_group = QGroupBox("Active Macros")
        active_group.setStyleSheet(_grp_style)
        active_layout = QVBoxLayout(active_group)

        self.active_list = QListWidget()
        self.active_list.setObjectName("helxairo_activeList")
        self.active_list.setMinimumHeight(160)
        self.active_list.setStyleSheet("""
            QListWidget {
                background: #2a2d35;
                border: none;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QListWidget::item { padding: 8px 12px; }
            QListWidget::item:selected { background: #FF5B06; color: white; }
            QListWidget::item:hover { background: #3a3d45; }
        """)
        active_layout.addWidget(self.active_list)

        active_btn_row = QHBoxLayout()
        active_btn_row.setSpacing(8)

        self.toggle_macro_btn = QPushButton("Toggle Selected")
        self.toggle_macro_btn.setObjectName("helxairo_toggleMacro")
        self.toggle_macro_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_macro_btn.setStyleSheet(_btn_style)
        self.toggle_macro_btn.clicked.connect(self._toggle_selected_macro)
        active_btn_row.addWidget(self.toggle_macro_btn)

        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.setObjectName("helxairo_deleteSelected")
        self.delete_selected_btn.setCursor(Qt.PointingHandCursor)
        self.delete_selected_btn.setStyleSheet(_btn_style)
        self.delete_selected_btn.clicked.connect(self._delete_selected)
        active_btn_row.addWidget(self.delete_selected_btn)

        self.disable_all_btn = QPushButton("Stop All")
        self.disable_all_btn.setObjectName("helxairo_stopAll")
        self.disable_all_btn.setCursor(Qt.PointingHandCursor)
        self.disable_all_btn.setStyleSheet(_btn_style)
        self.disable_all_btn.clicked.connect(self._disable_all)
        active_btn_row.addWidget(self.disable_all_btn)

        active_btn_row.addStretch()
        active_layout.addLayout(active_btn_row)

        macro_layout.addWidget(active_group)

        # ── Profiles ──────────────────────────────────
        profile_group = QGroupBox("Profiles")
        profile_group.setStyleSheet(_grp_style)
        profile_layout = QHBoxLayout(profile_group)

        # Left: profile list + new/delete buttons
        profile_left = QVBoxLayout()

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("helxairo_profileList")
        self.profile_list.setMaximumWidth(200)
        self.profile_list.setStyleSheet("""
            QListWidget {
                background: #2a2d35;
                border: none;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QListWidget::item { padding: 7px 12px; }
            QListWidget::item:selected { background: #FF5B06; color: white; }
            QListWidget::item:hover { background: #3a3d45; }
        """)
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        profile_left.addWidget(self.profile_list)

        profile_btn_row = QHBoxLayout()
        profile_btn_row.setSpacing(6)

        self.new_profile_btn = QPushButton("+")
        self.new_profile_btn.setObjectName("helxairo_newProfileBtn")
        self.new_profile_btn.setFixedWidth(36)
        self.new_profile_btn.setCursor(Qt.PointingHandCursor)
        self.new_profile_btn.setStyleSheet(_btn_style)
        self.new_profile_btn.clicked.connect(self._new_profile)
        profile_btn_row.addWidget(self.new_profile_btn)

        self.delete_profile_btn = QPushButton("-")
        self.delete_profile_btn.setObjectName("helxairo_delProfileBtn")
        self.delete_profile_btn.setFixedWidth(36)
        self.delete_profile_btn.setCursor(Qt.PointingHandCursor)
        self.delete_profile_btn.setStyleSheet(_btn_style)
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        profile_btn_row.addWidget(self.delete_profile_btn)

        profile_btn_row.addStretch()
        profile_left.addLayout(profile_btn_row)
        profile_layout.addLayout(profile_left)

        # Right: name, bound apps, save button
        profile_right = QVBoxLayout()

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("helxairo_profileName")
        self.profile_name.setPlaceholderText("Profile name...")
        form.addRow("Name:", self.profile_name)

        self.profile_apps = QLineEdit()
        self.profile_apps.setObjectName("helxairo_profileApps")
        self.profile_apps.setPlaceholderText("e.g., gta5.exe, valorant.exe")
        form.addRow("Bound Apps:", self.profile_apps)

        profile_right.addLayout(form)

        self.save_profile_btn = QPushButton("Save Profile")
        self.save_profile_btn.setObjectName("helxairo_saveProfileBtn")
        self.save_profile_btn.setCursor(Qt.PointingHandCursor)
        self.save_profile_btn.setStyleSheet(_btn_style)
        self.save_profile_btn.clicked.connect(self._save_profile)
        profile_right.addWidget(self.save_profile_btn)

        profile_right.addStretch()
        profile_layout.addLayout(profile_right, 1)

        macro_layout.addWidget(profile_group)

        macro_layout.addStretch()
        macro_scroll.setWidget(macro_content)

        macro_tab_layout = QVBoxLayout(macro_tab)
        macro_tab_layout.setContentsMargins(0, 0, 0, 0)
        macro_tab_layout.addWidget(macro_scroll)

        self._page_stack.addWidget(macro_tab)
        
        # === SETTINGS TAB ===
        settings_scroll = SmoothScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setStyleSheet("background: transparent; border: none;")
        settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        settings_content = QWidget()
        settings_content.setStyleSheet("background: transparent;")
        
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(15)
        
        settings_header = QLabel("Settings")
        settings_header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        settings_header.setStyleSheet("color: #FF5B06;")
        settings_layout.addWidget(settings_header)
        
        # Indicator Drag Mode checkbox (KEPT per user request)
        self._drag_mode_checkbox = QCheckBox("Enable indicator drag mode (reposition button numbers on mouse image)")
        self._drag_mode_checkbox.setStyleSheet("""
            QCheckBox {
                color: #e0e0e0;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: none;
                border-radius: 4px;
                background: #2a2d35;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06;
                border-color: transparent;
                image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
            }
        """)
        self._drag_mode_checkbox.stateChanged.connect(self._toggle_indicator_drag_mode)
        settings_layout.addWidget(self._drag_mode_checkbox)
        
        settings_layout.addSpacing(10)
        
        # === GENERAL SETTINGS GROUP ===
        general_group = QGroupBox("General")
        general_group.setStyleSheet("""
            QGroupBox {
                color: #ff5b06;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """)
        general_layout = QFormLayout(general_group)
        general_layout.setSpacing(12)
        
        # Combo style for settings
        settings_combo_style = """
            QComboBox {
                background: #2a2d35;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 120px;
            }
            QComboBox:hover { border-color: transparent; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888;
            }
            QComboBox QAbstractItemView {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                selection-background-color: #FF5B06;
            }
        """
        
        # Language dropdown
        self._language_combo = QComboBox()
        self._language_combo.addItems(["English", "Chinese"])
        self._language_combo.setStyleSheet(settings_combo_style)
        self._language_combo.currentTextChanged.connect(self._on_language_changed)
        general_layout.addRow("Language:", self._language_combo)
        
        # Sleep Time dropdown
        self._sleep_time_combo = QComboBox()
        self._sleep_time_combo.addItems(["10sec", "30sec", "1min", "2min", "5min", "10min", "15min"])
        self._sleep_time_combo.setStyleSheet(settings_combo_style)
        self._sleep_time_combo.currentTextChanged.connect(self._on_sleep_time_changed)
        general_layout.addRow("Sleep Time:", self._sleep_time_combo)
        
        settings_layout.addWidget(general_group)
        
        # === ADVANCED SETTINGS GROUP ===
        advanced_group = QGroupBox("Advanced")
        advanced_group.setStyleSheet(general_group.styleSheet())
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setSpacing(10)
        
        # Long Distance Mode checkbox
        self._long_distance_check = QCheckBox("Long Distance Mode")
        self._long_distance_check.setStyleSheet(self._drag_mode_checkbox.styleSheet())
        self._long_distance_check.stateChanged.connect(self._on_long_distance_changed)
        advanced_layout.addWidget(self._long_distance_check)
        
        # Description label
        long_dist_desc = QLabel("Increases anti-interference and power for wireless mode.\nMay reduce battery life.")
        long_dist_desc.setStyleSheet("color: #888; font-size: 11px; margin-left: 26px;")
        long_dist_desc.setWordWrap(True)
        advanced_layout.addWidget(long_dist_desc)
        
        settings_layout.addWidget(advanced_group)
        
        # === FIRMWARE INFO GROUP ===
        firmware_group = QGroupBox("Device Information")
        firmware_group.setStyleSheet(general_group.styleSheet())
        firmware_layout = QFormLayout(firmware_group)
        firmware_layout.setSpacing(10)
        
        # Firmware version labels (will be updated when connected)
        self._receiver_fw_label = QLabel("--")
        self._receiver_fw_label.setStyleSheet("color: #e0e0e0;")
        firmware_layout.addRow("Receiver Firmware:", self._receiver_fw_label)
        
        self._mouse_fw_label = QLabel("--")
        self._mouse_fw_label.setStyleSheet("color: #e0e0e0;")
        firmware_layout.addRow("Mouse Firmware:", self._mouse_fw_label)
        
        settings_layout.addWidget(firmware_group)
        
        # === PROFILE MANAGEMENT GROUP ===
        profile_mgmt_group = QGroupBox("Profile Management")
        profile_mgmt_group.setStyleSheet(general_group.styleSheet())
        profile_mgmt_layout = QHBoxLayout(profile_mgmt_group)
        profile_mgmt_layout.setSpacing(10)
        
        # Button style
        mgmt_btn_style = """
            QPushButton {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                border-color: transparent;
                background: #3a3d45;
            }
            QPushButton:pressed {
                background: #FF5B06;
            }
        """
        
        # Profile Selector (Synchronized with Home)
        self._profile_settings_combo = QComboBox()
        self._profile_settings_combo.addItems(["Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"])
        self._profile_settings_combo.setStyleSheet(settings_combo_style)
        self._profile_settings_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_mgmt_layout.addWidget(self._profile_settings_combo)
        
        export_btn = QPushButton("Export")
        export_btn.setStyleSheet(mgmt_btn_style)
        export_btn.clicked.connect(self._export_profile)
        profile_mgmt_layout.addWidget(export_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setStyleSheet(mgmt_btn_style)
        import_btn.clicked.connect(self._import_profile)
        profile_mgmt_layout.addWidget(import_btn)
        
        restore_btn = QPushButton("Restore")
        restore_btn.setStyleSheet(mgmt_btn_style)
        restore_btn.clicked.connect(self._restore_defaults)
        profile_mgmt_layout.addWidget(restore_btn)
        
        profile_mgmt_layout.addStretch()
        settings_layout.addWidget(profile_mgmt_group)
        
        # === PAIR TOOL ===
        pair_group = QGroupBox("Wireless Pairing")
        pair_group.setStyleSheet(general_group.styleSheet())
        pair_layout = QHBoxLayout(pair_group)
        
        pair_btn = QPushButton("Pair Tool")
        pair_btn.setStyleSheet("""
            QPushButton {
                background: #FF5B06;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ff7a33;
            }
            QPushButton:pressed {
                background: #cc4905;
            }
        """)
        pair_btn.clicked.connect(self._open_pair_tool)
        pair_layout.addWidget(pair_btn)
        pair_layout.addStretch()
        
        settings_layout.addWidget(pair_group)
        
        settings_layout.addStretch()
        settings_scroll.setWidget(settings_content)
        self._page_stack.addWidget(settings_scroll)
        
        # Default to Home tab
        self._page_stack.setCurrentIndex(0)
        self._update_tab_buttons()
        
        layout.addWidget(self._page_stack, 1)
        
        # Load and apply saved HELXAIRO settings (after all UI is created)
        self._apply_saved_helxairo_settings()

    def _switch_tab(self, index: int):
        """Switch to specified tab."""
        self._current_tab = index
        self._page_stack.setCurrentIndex(index)
        self._update_tab_buttons()
    
    def _update_tab_buttons(self):
        """Update tab button styles based on current selection (HELXTATS style)."""
        for i, btn in enumerate(self._tab_buttons):
            if i == self._current_tab:
                # Active tab: gradient top border (orange -> pink -> purple) with rounded corners
                btn.setStyleSheet("""
                    QPushButton {
                        background: #2a2a2a;
                        color: #e0e0e0;
                        border: none;
                        border-top: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #cc47aa, stop:0.5 #ff0919, stop:1 #e89805);
                        border-top-left-radius: 6px;
                        border-top-right-radius: 6px;
                        border-bottom-left-radius: 0px;
                        border-bottom-right-radius: 0px;
                        font-size: 14px;
                        padding: 8px 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #888888;
                        border: none;
                        border-top: 3px solid transparent;
                        border-radius: 0px;
                        font-size: 14px;
                        padding: 8px 12px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.05);
                        color: #b0b0b0;
                    }
                """)

    
    def _pick_dpi_color(self, stage_index: int):
        """Open color picker for DPI stage and update hardware + save."""
        if stage_index >= len(self._dpi_stage_boxes):
            return
            
        box = self._dpi_stage_boxes[stage_index]
        current_color = box.color
        
        color = QColorDialog.getColor(current_color, self, f"Choose Color for Stage {stage_index+1}")
        
        if color.isValid():
            hex_color = color.name()
            rgb = (color.red(), color.green(), color.blue())
            
            # Update UI
            box.color = hex_color
            box.color_bar.setStyleSheet(f"background: {hex_color}; border: none;")
            
            # Update Hardware
            self._hw_manager.enqueue('set_dpi_color', stage_index, *rgb)
            
            # Update internal list for saving
            # We need to reconstruct the dpi_defaults list format to save it
            current_settings = []
            for b in self._dpi_stage_boxes:
                current_settings.append([b.dpi_value, b.color])
            
            if not hasattr(self, '_dpi_settings'):
                self._dpi_settings = {}
            
            self._dpi_settings['dpi_colors'] = current_settings
            
            # Save to disk
            self._save_helxairo_settings()
            self._save_global_state()
            print(f"[HELXAIRO] Saved new color {hex_color} for stage {stage_index+1}")
            
    # ===== DPI TAB HANDLERS =====
    
    def _on_dpi_stages_changed(self, value: str):
        """Handle DPI stages count change."""
        num_stages = int(value)
        # Show/hide stage boxes based on count
        for i, box in enumerate(self._dpi_stage_boxes):
            box.setVisible(i < num_stages)
            
        # Skip redundant signal processing ONLY if we are already syncing to hardware.
        if getattr(self, '_syncing_to_hardware', False):
            return
            
        print(f"[DPI] Active stages set to {num_stages}")
        
        # Send to hardware
        # This is now throttled by HardwareManager (100ms)
        self._send_stage_count_to_hardware(num_stages)
        
        # Auto-save settings
        self._save_helxairo_settings()
    
    def _on_dpi_slider_changed(self, value: int):
        """Handle DPI slider value change.
        
        Updates the DPI value input and the currently selected stage box.
        Uses _updating_dpi_slider flag to prevent circular updates when
        programmatically changing slider position during stage selection.
        """
        dpi_value = value * 50  # Convert to actual DPI (range: 50-22000)
        # Update the editable input field — block signals to avoid feedback loop
        self._dpi_value_input.blockSignals(True)
        self._dpi_value_input.setText(str(dpi_value))
        self._dpi_value_input.blockSignals(False)
        
        # Only update stage box if this is a manual slider change (not from _select_dpi_stage)
        if not self._updating_dpi_slider:
            if hasattr(self, '_dpi_stage_boxes') and self._current_dpi_stage < len(self._dpi_stage_boxes):
                box = self._dpi_stage_boxes[self._current_dpi_stage]
                box.dpi_value = dpi_value
                box.value_label.setText(str(dpi_value))
                # Trigger auto-save
                if hasattr(self, '_dpi_save_timer'):
                    self._dpi_save_timer.start()
                    
    def _on_dpi_debounce_timeout(self):
        """Handle debounce timeout for DPI slider changes."""
        # Get current stage and value
        try:
            stage_idx = self._current_dpi_stage
            if hasattr(self, '_dpi_stage_boxes') and stage_idx < len(self._dpi_stage_boxes):
                dpi_value = self._dpi_stage_boxes[stage_idx].dpi_value
                
                # Send to hardware
                self._send_dpi_update_to_hardware(stage_idx, dpi_value)
                
                # Save settings
                self._save_helxairo_settings()
        except Exception as e:
            print(f"[DPI] Debounce error: {e}")

    def _on_dpi_input_committed(self):
        """Handle user typing a DPI value directly into the input field.
        
        Parses the typed value, clamps it to the valid DPI range (50-22000),
        rounds to the nearest 50-step increment (matching the slider), then
        applies it to the current stage — updating the slider, stage box,
        hardware, and saving settings.
        """
        try:
            raw = self._dpi_value_input.text().strip().replace("DPI", "").replace(" ", "")
            if not raw:
                return
                
            typed = int(raw)
            
            # Clamp to valid range and round to nearest 50
            clamped = max(50, min(22000, typed))
            snapped = round(clamped / 50) * 50
            
            # Show the corrected value in the field
            self._dpi_value_input.blockSignals(True)
            self._dpi_value_input.setText(str(snapped))
            self._dpi_value_input.blockSignals(False)
            
            # Apply to current stage box
            stage_idx = self._current_dpi_stage
            if hasattr(self, '_dpi_stage_boxes') and stage_idx < len(self._dpi_stage_boxes):
                box = self._dpi_stage_boxes[stage_idx]
                box.dpi_value = snapped
                box.value_label.setText(str(snapped))
            
            # Update slider to match (block signals to avoid feedback loop)
            self._updating_dpi_slider = True
            self._dpi_slider.blockSignals(True)
            self._dpi_slider.setValue(snapped // 50)
            self._dpi_slider.blockSignals(False)
            self._updating_dpi_slider = False
            
            print(f"[DPI] Value set via input: {snapped} DPI")
            
            # Send to hardware and save
            self._send_dpi_update_to_hardware(stage_idx, snapped)
            self._save_helxairo_settings()
            
        except (ValueError, AttributeError) as e:
            # Restore current slider value if input was invalid
            current_dpi = self._dpi_slider.value() * 50
            self._dpi_value_input.blockSignals(True)
            self._dpi_value_input.setText(str(current_dpi))
            self._dpi_value_input.blockSignals(False)
            print(f"[DPI] Invalid input value: {e}")
    
    def _adjust_dpi(self, delta: int):
        """Adjust DPI by +/- delta for the currently active stage.
        
        Reads the current displayed value, applies the delta step (50 DPI units),
        clamps to the valid range, and immediately commits the change via
        _on_dpi_input_committed — the same proven code path used when the user
        presses Enter after typing. This guarantees the hardware write fires
        instantly without waiting for the debounce timer.
        """
        # Read the authoritative current value directly from the input field
        # (not the slider) to stay in sync with whatever is currently displayed.
        try:
            raw = self._dpi_value_input.text().strip().replace("DPI", "").replace(" ", "")
            current_dpi = int(raw) if raw else self._dpi_slider.value() * 50
        except (ValueError, AttributeError):
            current_dpi = self._dpi_slider.value() * 50
        
        new_dpi = max(50, min(22000, current_dpi + delta))
        
        # Write the new value into the field and commit immediately so that
        # _on_dpi_input_committed handles slider sync, hardware write, and save.
        self._dpi_value_input.setText(str(new_dpi))
        self._on_dpi_input_committed()
    
    def _on_stage_clicked(self, index: int):
        """Handle click on DPI stage box."""
        # If clicking the already active stage, open color picker
        if hasattr(self, '_current_dpi_stage') and self._current_dpi_stage == index:
            self._pick_dpi_color(index)
        else:
            self._select_dpi_stage(index)



    def _show_left_click_protection(self):
        """
        Show protection dialog when user tries to change button 1 (Left Click).
        This matches Furycube's behavior where Left Click must remain assigned to button 1.
        """
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Button Protection")
        dialog.setText("Must keep left key")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        dialog.setDefaultButton(QMessageBox.Ok)
        
        # Apply dark theme styling
        dialog.setStyleSheet("""
            QMessageBox {
                background: #1a1a1a;
                color: #e0e0e0;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
                font-size: 13px;
                padding: 10px 20px;
            }
            QPushButton {
                background: #2a2d35;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                min-width: 60px;
            }
            QPushButton:hover {
                background: #3a3d45;
            }
            QPushButton:pressed {
                background: #FF5B06;
            }
        """)
        
        dialog.exec()
    
    def _toggle_indicator_drag_mode(self, state: int):
        """
        Enable or disable drag mode for all button indicators.
        When enabled, indicators can be dragged to reposition them on the mouse image.
        """
        # stateChanged passes int: 0=Unchecked, 2=Checked
        enabled = (state == 2)
        if hasattr(self, '_button_indicators'):
            for indicator in self._button_indicators:
                indicator.set_drag_enabled(enabled)
        
        # Visual feedback
        if enabled:
            print("[HELXAIRO] Indicator drag mode ENABLED - drag the numbers to reposition")
        else:
            print("[HELXAIRO] Indicator drag mode DISABLED")
    
    def _on_indicator_position_changed(self, index: int, x: int, y: int):
        """
        Handle indicator position change after drag.
        Auto-saves the new position to settings file.
        """
        print(f"[HELXAIRO] Indicator {index + 1} moved to ({x}, {y})")
        
        # Save positions to settings
        if not hasattr(self, '_indicator_positions'):
            self._indicator_positions = {}
        self._indicator_positions[index] = (x, y)
        
        # Auto-save to file
        self._save_global_state()
    
    def _reset_indicator_positions(self):
        """
        Reset all button indicators to their default positions.
        """
        default_positions = self._get_default_indicator_positions()
        
        if hasattr(self, '_button_indicators'):
            for i, (x, y) in enumerate(default_positions):
                if i < len(self._button_indicators):
                    self._button_indicators[i].move(x, y)
        
        # Clear saved positions and save
        self._indicator_positions = {}
        self._save_global_state()
        print("[HELXAIRO] Indicator positions reset to defaults")
    
    def _get_default_indicator_positions(self):
        """Get default indicator positions."""
        return [
            (120, 160),  # Button 1
            (75, 115),   # Button 2
            (170, 65),   # Button 3
            (290, 125),  # Button 4
            (320, 145),  # Button 5
        ]
    

    
    # ===== SETTINGS TAB HANDLERS =====
    
    def _on_language_changed(self, text: str):
        """Handle language change. Currently just saves the preference."""
        print(f"[HELXAIRO] Language set to: {text}")
        self._save_helxairo_settings()
    
    def _on_sleep_time_changed(self, text: str):
        """
        Handle sleep time change.
        Maps text values to firmware indices and sends to HID.
        """
        mapping = {
            "10sec": 1, "30sec": 2, "1min": 3, "2min": 4,
            "5min": 5, "10min": 6, "15min": 7
        }
        val = mapping.get(text, 3)
        
        try:
            self._hw_manager.enqueue('set_sleep_time', val)
            print(f"[HELXAIRO] Sleep time set to: {text}")
            self._save_helxairo_settings()
        except Exception as e:
            print(f"[HELXAIRO] Sleep time update failed: {e}")
    
    def _on_long_distance_changed(self, state: int):
        """
        Handle Long Distance Mode change.
        Increases wireless range at cost of battery life.
        """
        enabled = (state == Qt.Checked)
        try:
            self._hw_manager.enqueue('set_long_distance_mode', enabled)
            print(f"[HELXAIRO] Long Distance Mode: {'ON' if enabled else 'OFF'}")
            self._save_helxairo_settings()
        except Exception as e:
            print(f"[HELXAIRO] Long distance mode update failed: {e}")
    
    def _export_profile(self):
        """Export current settings to a JSON file."""
        from PySide6.QtWidgets import QFileDialog
        import json
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                settings = self._collect_current_settings()
                with open(file_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                print(f"[HELXAIRO] Profile exported to: {file_path}")
            except Exception as e:
                print(f"[HELXAIRO] Export failed: {e}")
    
    def _import_profile(self):
        """Import settings from a JSON file."""
        from PySide6.QtWidgets import QFileDialog
        import json
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    settings = json.load(f)
                self._apply_imported_settings(settings)
                print(f"[HELXAIRO] Profile imported from: {file_path}")
            except Exception as e:
                print(f"[HELXAIRO] Import failed: {e}")
    
    def _collect_current_settings(self) -> dict:
        """Collect current settings into a dictionary for export."""
        settings = {}
        # Collect DPI, button mappings, sensor settings, etc.
        if hasattr(self, '_dpi_stage_boxes'):
            settings['dpi_stages'] = [
                {'dpi': box.dpi_value, 'color': box.color}
                for box in self._dpi_stage_boxes
            ]
        if hasattr(self, '_button_mappings'):
            settings['button_mappings'] = self._button_mappings
        return settings
    
    def _apply_imported_settings(self, settings: dict):
        """Apply imported settings to the UI and hardware."""
        # Apply DPI stages
        if 'dpi_stages' in settings and hasattr(self, '_dpi_stage_boxes'):
            for i, stage_data in enumerate(settings['dpi_stages']):
                if i < len(self._dpi_stage_boxes):
                    box = self._dpi_stage_boxes[i]
                    box.dpi_value = stage_data.get('dpi', box.dpi_value)
                    box.color = stage_data.get('color', box.color)
        self._save_helxairo_settings()
    
    def _restore_defaults(self):
        """Restore all settings to factory defaults."""
        reply = QMessageBox.question(
            self, "Restore Defaults",
            "Are you sure you want to restore all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # TODO: Implement full hardware reset when HID command is known
                print("[HELXAIRO] Restoring factory defaults...")
                self._hw_manager.enqueue('restore_defaults') # Assuming a restore_defaults command
                print("[HELXAIRO] Defaults restored")
            except Exception as e:
                print(f"[HELXAIRO] Restore failed: {e}")
    
    def _open_pair_tool(self):
        """Open the wireless pairing tool dialog."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Pair Tool")
        dialog.setText("Put the receiver into pairing mode, then press the button on the bottom of the mouse.")
        dialog.setIcon(QMessageBox.Information)
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.setStyleSheet("""
            QMessageBox { background: #1a1a1a; color: #e0e0e0; }
            QMessageBox QLabel { color: #e0e0e0; font-size: 13px; padding: 10px 20px; }
            QPushButton { background: #2a2d35; color: #e0e0e0; border: none; border-radius: 4px; padding: 8px 24px; min-width: 60px; }
            QPushButton:hover { background: #3a3d45; }
        """)
        
        # Actually trigger pairing if HID supports it
        try:
            self._hw_manager.enqueue('start_pairing')
            print("[HELXAIRO] Pairing mode started")
        except Exception as e:
            print(f"[HELXAIRO] Pairing error: {e}")
        
        dialog.exec()

    def _on_dpi_effect_changed(self, index: int):
        """Handle DPI effect mode change."""
        mode_id = self._effect_combo.currentData()
        if mode_id is None: 
            mode_id = 1
            
        # Update visibility/enabled state based on mode
        if hasattr(self, '_brightness_slider') and hasattr(self, '_speed_slider'):
            is_off = (mode_id == 0)
            is_steady = (mode_id == 1)
            is_breathing = (mode_id == 2)
            
            # Brightness only works in Steady mode
            self._brightness_slider.setEnabled(is_steady)
            
            # Speed only works in Breathing/Dynamic modes
            self._speed_slider.setEnabled(is_breathing and not is_off)

        self._hw_manager.enqueue('set_dpi_effect_mode', mode_id)
            
        self._save_helxairo_settings()

    def _on_dpi_brightness_changed(self, value: int):
        """Handle DPI brightness change."""
        self._hw_manager.enqueue('set_dpi_effect_brightness', value)
        print(f"[HELXAIRO] Setting brightness to {value}")
            
        self._save_helxairo_settings()

    def _on_dpi_speed_changed(self, value: int):
        """Handle DPI speed change."""
        self._hw_manager.enqueue('set_dpi_effect_speed', value)
        self._save_helxairo_settings()

    def _save_helxairo_settings(self):
        """Save HELXAIRO settings (indicator positions, button mappings) to file."""
        if getattr(self, '_loading_settings', False):
            return
            
        # Collect DPI stage values
        stage_values = {}
        if hasattr(self, '_dpi_stage_boxes'):
            for i, box in enumerate(self._dpi_stage_boxes):
                if hasattr(box, 'dpi_value'):
                    stage_values[str(i)] = box.dpi_value

        # Identify selected polling rate
        pooling_rate_idx = getattr(self, '_current_polling', 0)

        # Collect current DPI Colors
        current_colors = []
        if hasattr(self, '_dpi_stage_boxes'):
            for box in self._dpi_stage_boxes:
                if hasattr(box, 'dpi_value') and hasattr(box, 'color'):
                    current_colors.append([box.dpi_value, box.color])

        settings = {
            'button_mappings': getattr(self, '_button_mappings', self._get_default_button_mappings()),
            'dpi_settings': {
                'stages_count': int(self._dpi_stages_combo.currentText()) if hasattr(self, '_dpi_stages_combo') else 6,
                'current_stage_index': getattr(self, '_current_dpi_stage', 0),
                'stage_values': stage_values,
                'polling_rate_index': pooling_rate_idx,
                'dpi_colors': current_colors
            },
            'dpi_effect_settings': {
                'mode': self._effect_combo.currentData() if hasattr(self, '_effect_combo') else 1,
                'brightness': self._brightness_slider.value() if hasattr(self, '_brightness_slider') else 8,
                'speed': self._speed_slider.value() if hasattr(self, '_speed_slider') else 5
            },
            'sensor_settings': {
                'lod_index': self._lod_combo.currentIndex() if hasattr(self, '_lod_combo') else 0,
                'ripple': self._ripple_check.isChecked() if hasattr(self, '_ripple_check') else False,
                'angle_snap': self._angle_snap_check.isChecked() if hasattr(self, '_angle_snap_check') else False,
                'motion_sync': self._motion_sync_check.isChecked() if hasattr(self, '_motion_sync_check') else False,
                'debounce_time': self._debounce_slider.value() if hasattr(self, '_debounce_slider') else 10,
                'sensor_mode': self._mode_combo.currentIndex() if hasattr(self, '_mode_combo') else 0,
                'highest_performance': self._highest_perf_check.isChecked() if hasattr(self, '_highest_perf_check') else False,
                'perf_time': self._perf_time_combo.currentText() if hasattr(self, '_perf_time_combo') else "1min"
            }
        }
        
        try:
            with open(self._get_helxairo_settings_path(), 'w') as f:
                json.dump(settings, f, indent=2)
            # print("[HELXAIRO] Settings saved")
        except Exception as e:
            print(f"[HELXAIRO] Failed to save settings: {e}")
    
    def _load_helxairo_settings(self):
        """Load HELXAIRO settings from file."""
        try:
            with open(self._get_helxairo_settings_path(), 'r') as f:
                settings = json.load(f)
            
            # Load button mappings
            self._button_mappings = settings.get('button_mappings', self._get_default_button_mappings())
            
            # Load DPI settings
            self._dpi_settings = settings.get('dpi_settings', {})
            
            # Restore custom DPI colors if saved
            if 'dpi_colors' in self._dpi_settings:
                try:
                    loaded_colors = self._dpi_settings['dpi_colors']
                    # loaded_colors is list of [dpi, color_hex]
                    # We need to update existing defaults or override them
                    # We'll store them to be used during UI setup or checking against defaults
                    self._restored_dpi_colors = loaded_colors
                except Exception as e:
                    print(f"[HELXAIRO] Failed to parse saved DPI colors: {e}")
            
            # Load Sensor Settings
            self._sensor_settings = settings.get('sensor_settings', {})
            self._dpi_effect_settings = settings.get('dpi_effect_settings', {})
            
            print("[HELXAIRO] Settings loaded")
            return True
        except FileNotFoundError:
            self._button_mappings = self._get_default_button_mappings()
            self._dpi_settings = {}
            return False
        except Exception as e:
            self._button_mappings = self._get_default_button_mappings()
            self._dpi_settings = {}
            return False
    
    def _get_default_button_mappings(self):
        """Get default button mappings."""
        return ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]
    
    def _on_button_mapping_changed(self, button_index: int, new_action: str):
        """
        Handle button mapping change from dropdown menu.
        Saves to local settings AND sends HID command to mouse hardware.
        
        Args:
            button_index: Button index (0-4)
            new_action: Action name string (e.g., "Left Click", "Right Click", etc.)
        """
        if not hasattr(self, '_button_mappings'):
            self._button_mappings = self._get_default_button_mappings()
        
        self._button_mappings[button_index] = new_action
        self._save_helxairo_settings()
        print(f"[HELXAIRO] Button {button_index + 1} mapped to: {new_action}")
        
        # Send HID command to mouse hardware
        self._send_button_mapping_to_hardware(button_index, new_action)
    
    def _on_debounce_changed(self):
        """Handle debounce time slider change."""
        if not hasattr(self, '_debounce_slider'):
            return
            
        ms = self._debounce_slider.value()
        self._save_helxairo_settings()
        
        try:
            self._hw_manager.enqueue('set_debounce_time', ms)
            print(f"[HELXAIRO] Debounce time set to {ms}ms")
        except Exception as e:
            print(f"[HELXAIRO] Failed to set debounce: {e}")

    def _on_sensor_mode_changed(self, index: int):
        """Handle sensor mode change."""
        try:
            # Check for Corded selection in Wireless mode
            is_corded_selection = (index == 2) # Index 2 is "Corded"
            conn_type = self._hw_manager.get_state()['connection_type']
            
            if is_corded_selection and conn_type == 'wireless':
                QMessageBox.warning(self, "Connection Required", 
                                  "Please connect the USB cable to use Corded mode.\n\n"
                                  "This mode provides direct hardware connection for lowest latency.")
                
                # Revert to PREVIOUS mode (instead of Default HP)
                # This ensures we go back to LP if we were on LP
                rev_idx = str(self._last_sensor_mode_index)
                print(f"[HELXAIRO] Reverting to previous mode: {rev_idx}")
                self._mode_combo.setCurrentIndex(self._last_sensor_mode_index)
                return

            self._hw_manager.enqueue('set_sensor_mode', index)
            self._save_helxairo_settings()
            
            # Update last known valid mode
            if index != 2: # Don't save Corded as "previous" if it was a mistake? 
                           # Actually, if we successfully set it (wired), we should save it?
                           # But here we are in the success block. 
                           # If wired, we can be in Corded mode.
                self._last_sensor_mode_index = index
            elif conn_type == 'wired':
                # If we are wired and set to corded, that is valid
                self._last_sensor_mode_index = index
        except Exception as e:
            print(f"[HELXAIRO] Failed to set sensor mode: {e}")

    def _on_highest_perf_changed(self, checked: bool):
        """Handle highest performance checkbox."""
        self._save_helxairo_settings()
        
        try:
            self._hw_manager.enqueue('set_highest_performance', checked)
        except Exception as e:
            print(f"[HELXAIRO] Failed to set highest perf: {e}")

    def _on_perf_time_changed(self, text: str):
        """Handle performance time change."""
        self._save_helxairo_settings()
        
        try:
            # Map text to value
            mapping = {"10s": 1, "30s": 2, "1min": 3, "2min": 4, "5min": 5, "10min": 6}
            val = mapping.get(text, 3) # default 1min
            self._hw_manager.enqueue('set_performance_time', val)
        except Exception as e:
            print(f"[HELXAIRO] Failed to set perf time: {e}")

    def _on_ripple_changed(self, checked: bool):
        """Handle Ripple Control change."""
        self._save_helxairo_settings()
        try:
            self._hw_manager.enqueue('set_ripple', checked)
            print(f"[HELXAIRO] Ripple control: {'ON' if checked else 'OFF'}")
        except Exception as e:
            print(f"[HELXAIRO] Ripple update failed: {e}")

    def _on_angle_snap_changed(self, checked: bool):
        """Handle Angle Snapping change."""
        self._save_helxairo_settings()
        try:
            self._hw_manager.enqueue('set_angle_snapping', checked)
            print(f"[HELXAIRO] Angle snap: {'ON' if checked else 'OFF'}")
        except Exception as e:
            print(f"[HELXAIRO] Angle Snap update failed: {e}")

    def _on_motion_sync_changed(self, checked: bool):
        """Handle Motion Sync change."""
        self._save_helxairo_settings()
        try:
            self._hw_manager.enqueue('set_motion_sync', checked)
            print(f"[HELXAIRO] Motion sync: {'ON' if checked else 'OFF'}")
        except Exception as e:
            print(f"[HELXAIRO] Motion Sync update failed: {e}")

    def _on_lod_changed(self, index: int):
        """Handle LOD change (0=1mm, 1=2mm)."""
        value = index + 1
        self._save_helxairo_settings()
        try:
            self._hw_manager.enqueue('set_lod', value)
            print(f"[HELXAIRO] LOD set to {value}mm")
        except Exception as e:
            print(f"[HELXAIRO] LOD update failed: {e}")

    def _update_sensor_ui_for_connection(self):
        """
        Update the UI states based on whether the mouse is Wired or Wireless.
        """
        try:
            print("[TIMING] Inside _update_sensor_ui: about to get_state()", flush=True)
            conn_type = self._hw_manager.get_state()['connection_type']
            print(f"[TIMING] get_state() returned, conn_type={conn_type}", flush=True)
            
            model = self._mode_combo.model()
            corded_index = 2 # Index of "Corded" in ["LP", "HP", "Corded"]

            if conn_type == 'wireless':
                # Wireless Mode:
                # - "Corded" option visible and ENABLED
                # - "Highest Performance" & "Perf Time" ENABLED
                
                # Enable "Corded" item in dropdown (so user can click it to get prompt)
                if model:
                   item = model.item(corded_index)
                   if item:
                       item.setEnabled(True)
                
                # We do NOT auto-switch anymore based on user request.
                # Logic moved to _on_sensor_mode_changed to show popup.
                
                self._highest_perf_check.setEnabled(True)
                self._perf_time_combo.setEnabled(True)
                self._highest_perf_check.setToolTip("Enable peak performance mode (consumes more battery)")
                
            elif conn_type == 'wired':
                # Wired Mode:
                # - "Corded" option enabled
                # - "Highest Performance" & "Perf Time" DISABLED (irrelevant)
                
                # Enable "Corded" item
                if model:
                   item = model.item(corded_index)
                   if item:
                       item.setEnabled(True)
                
                # Auto-switch to Corded if not already
                # actually, maybe just let user choose? But Corded makes sense.
                # Let's just enable the item. User can select.
                
                self._highest_perf_check.setEnabled(False)
                self._highest_perf_check.setChecked(True) # Force ON visually or OFF? Usually wired is max perf.
                self._perf_time_combo.setEnabled(False)
                
                self._highest_perf_check.setToolTip("Always on max performance in Wired mode")
                
        except Exception as e:
            print(f"[HELXAIRO] Error updating UI for connection: {e}")

    def _on_hardware_state_changed(self, state):
        """Callback from HardwareManager when state updates (battery, connection, DPI)."""
        # This is called from a background thread! Use QTimer.singleShot for UI updates.
        QMetaObject.invokeMethod(self, "_update_ui_from_hw_state", Qt.QueuedConnection)

    @Slot()
    def _update_ui_from_hw_state(self):
        """Sync UI with latest hardware state from manager cache."""
        state = self._hw_manager.get_state()
        
        # 1. Battery Info (Handled by _update_battery_display timer now)
        pass
        
        # 2. Connection Type
        conn_type = state['connection_type']
        if hasattr(self, '_conn_type_label'):
            self._conn_type_label.setText(conn_type.capitalize())
            
    def _check_active_dpi_from_cache(self):
        """Monitor hardware DPI state for logging purposes only.
        
        DESIGN: User's DPI selection is AUTHORITATIVE. Hardware polling 
        NEVER overrides the UI. The firmware's flash readback is unreliable 
        and causes infinite feedback loops if used to override the UI.
        
        This method only logs mismatches for diagnostic visibility.
        """
        state = self._hw_manager.get_state()
        if not state['connected'] or state['active_dpi_stage'] is None:
            return
            
        stage_idx = state['active_dpi_stage']
        
        # LOG ONLY: Report mismatch but NEVER change UI
        if stage_idx != self._current_dpi_stage:
            if not hasattr(self, '_last_logged_hw_mismatch') or self._last_logged_hw_mismatch != stage_idx:
                print(f"[DPI] HW reports stage {stage_idx+1}, UI is stage {self._current_dpi_stage+1} (ignoring HW - user selection is authoritative)")
                self._last_logged_hw_mismatch = stage_idx
        else:
            # Clear the mismatch tracker when they agree
            self._last_logged_hw_mismatch = -1
            
    def _select_dpi_stage(self, index: int):
        """Select a DPI stage, update UI, sync to hardware, and save settings.
        
        This method is the SINGLE source of truth for DPI stage selection.
        Called by: user clicks (_on_stage_clicked), startup restore (_apply_saved_helxairo_settings).
        Hardware polling NEVER calls this method.
        
        Args:
            index: The DPI stage index to select (0-based).
        """
        if not hasattr(self, '_dpi_stage_boxes') or index >= len(self._dpi_stage_boxes):
            return

        # Skip if already on this stage (prevents unnecessary writes on repeated clicks)
        if hasattr(self, '_current_dpi_stage') and self._current_dpi_stage == index:
            return
        
        target_dpi = self._dpi_stage_boxes[index].dpi_value
        print(f"[DPI] Stage {index+1} selected ({target_dpi} DPI)")

        self._current_dpi_stage = index
        
        # Update styling
        for i, box in enumerate(self._dpi_stage_boxes):
            is_selected = (i == index)
            if is_selected:
                box.setStyleSheet("""
                    QWidget#dpiStageBox {
                        background: #1a1d25;
                        border: none;
                        border-radius: 4px;
                    }
                """)
            else:
                box.setStyleSheet("""
                    QWidget#dpiStageBox {
                        background: transparent;
                        border: none;
                        border-radius: 4px;
                    }
                """)
            box.indicator.setVisible(is_selected)
            
        # Update slider value without triggering handler loop
        self._updating_dpi_slider = True
        self._dpi_slider.blockSignals(True)
        self._dpi_slider.setValue(target_dpi // 50)
        self._dpi_slider.blockSignals(False)
        self._updating_dpi_slider = False
        
        # SYNC FIX: blockSignals prevents _on_dpi_slider_changed from firing,
        # so we must explicitly update the input field to match the selected stage.
        self._dpi_value_input.blockSignals(True)
        self._dpi_value_input.setText(str(target_dpi))
        self._dpi_value_input.blockSignals(False)
        
        # Send color to hardware
        try:
            current_box = self._dpi_stage_boxes[index]
            c = QColor(current_box.color)
            rgb = (c.red(), c.green(), c.blue())
            self._hw_manager.enqueue('set_dpi_color', index, *rgb)
        except Exception as e:
            print(f"[DPI] Failed to sync color: {e}")

        # Send active stage to hardware
        self._send_current_stage_to_hardware(index)
        
        # Save settings to disk
        self._save_helxairo_settings()

    def _select_polling_rate(self, index: int):
        """Select a polling rate and update UI."""
        rates = [125, 250, 500, 1000]
        rate = rates[index] if index < len(rates) else 1000
        print(f"[DPI] Polling rate set to {rate}Hz")
        
        self._current_polling = index
        
        for i, btn in enumerate(self._polling_buttons):
            if i == index:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #ff5b06;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #2a2d35;
                        color: #e0e0e0;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        border-color: transparent;
                    }
                """)
        
        # Send to hardware
        self._send_polling_rate_to_hardware(rate)
        
        # Auto-save settings
        self._save_helxairo_settings()

    def _send_button_mapping_to_hardware(self, button_index: int, action_name: str):
        """Send button mapping command to manager queue."""
        action_map = {
            "Left Click": 10, # Action codes... reduced for brevity
            # ... (mapping uses ButtonAction enums internally in manager if we pass names? 
            # No, let's keep it simple and pass the code directly)
        }
        # Note: Re-using the logic from _send_button_mapping_to_hardware
        # Mapping name to code...
        from FurycubeHID import ButtonAction
        
        m = {
            "Left Click": ButtonAction.LEFT_CLICK, "Right Click": ButtonAction.RIGHT_CLICK,
            "Wheel Click": ButtonAction.MIDDLE_CLICK, "Middle Click": ButtonAction.MIDDLE_CLICK,
            "Forward": ButtonAction.FORWARD, "Backward": ButtonAction.BACKWARD,
            "Disable": ButtonAction.DISABLED, "DPI Loop": ButtonAction.DPI_LOOP,
            "DPI +": ButtonAction.DPI_PLUS, "DPI -": ButtonAction.DPI_MINUS,
            "Scroll Up": ButtonAction.SCROLL_UP, "Scroll Down": ButtonAction.SCROLL_DOWN,
        }
        code = m.get(action_name)
        if code is not None:
            self._hw_manager.enqueue('set_button_mapping', button_index, code)

    def _send_dpi_update_to_hardware(self, stage_index: int, value: int):
        self._hw_manager.enqueue('set_dpi_stage_value', stage_index, value)

    def _send_current_stage_to_hardware(self, stage_index: int):
        self._hw_manager.enqueue('set_current_dpi_stage', stage_index, priority=1)

    def _send_stage_count_to_hardware(self, count: int):
        self._hw_manager.enqueue('set_dpi_stages_count', count)

    def _send_polling_rate_to_hardware(self, rate_hz: int):
        self._hw_manager.enqueue('set_polling_rate', rate_hz)

    def _apply_saved_helxairo_settings(self):
        """Load and apply saved HELXAIRO settings on startup."""
        self._loading_settings = True
        self._syncing_to_hardware = True
        try:
            # Ensure it exists even if unforeseen error occurred above (fallback)
            if not hasattr(self, '_current_profile_index'):
                self._current_profile_index = 0
                
            # Update UI combos
            self._updating_profile = True
            try:
                if hasattr(self, '_profile_combo'):
                    self._profile_combo.setCurrentIndex(self._current_profile_index)
                if hasattr(self, '_profile_settings_combo'):
                    self._profile_settings_combo.setCurrentIndex(self._current_profile_index)
            finally:
                self._updating_profile = False
                
            self._load_helxairo_settings()
            import time as _t; _t0 = _t.perf_counter()
            print(f"[TIMING] Post-load start: {_t.perf_counter():.3f}")
            
            # Initialize HID connection ONCE for startup sync
            try:
                # Force Hardware to 6 Stages
                self._hw_manager.enqueue('set_dpi_stages_count', 6)
                
                # Force Sync ALL DPI Values
                if hasattr(self, '_dpi_stage_boxes'):
                    # First apply restored values to exactly match saved state
                    if hasattr(self, '_restored_dpi_colors') and self._restored_dpi_colors:
                        from PySide6.QtGui import QColor
                        for i, box in enumerate(self._dpi_stage_boxes):
                            if i < len(self._restored_dpi_colors):
                                dpi_val, color_hex = self._restored_dpi_colors[i]
                                box.dpi_value = dpi_val
                                box.color = color_hex
                                box.value_label.setText(str(dpi_val))
                                box.color_bar.setStyleSheet(f"background: {color_hex}; border: none;")
                                c = QColor(color_hex)
                                self._hw_manager.enqueue('set_dpi_color', i, c.red(), c.green(), c.blue())
                                
                    for i, box in enumerate(self._dpi_stage_boxes):
                        val = box.dpi_value
                        self._hw_manager.enqueue('set_dpi_stage_value', i, val)
                        
                # Sync other settings...
                if self._sensor_settings:
                    # ... (existing sync log) ...
                    pass
            except Exception as e:
                print(f"[HELXAIRO] Startup Sync Error: {e}")
            print(f"[TIMING] HID enqueue batch done: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
                
            # Continue with UI application (which sets active stage)
            # This prevents repeated slow connection attempts during individual setting applies
            try:
                # Update UI based on connection type (Wired/Wireless)
                print(f"[TIMING] About to call _update_sensor_ui_for_connection", flush=True)
                self._update_sensor_ui_for_connection()
                print(f"[TIMING] _update_sensor_ui_for_connection returned", flush=True)
                
            except Exception as e:
                print(f"[HELXAIRO] Startup connection error: {e}")
            
            print(f"[TIMING] Sensor UI done: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
            # Apply saved indicator positions from global state
            import os, json
            global_path = os.path.join(os.getenv('APPDATA'), 'HELXAID', 'helxairo_global.json')
            try:
                if os.path.exists(global_path):
                    with open(global_path, 'r') as f:
                        g_state = json.load(f)
                        self._indicator_positions = {int(k): tuple(v) for k, v in g_state.get('indicator_positions', {}).items()}
                        
                        if 'custom_colors' in g_state:
                            from PySide6.QtGui import QColor
                            from PySide6.QtWidgets import QColorDialog
                            for i, color_hex in enumerate(g_state['custom_colors']):
                                QColorDialog.setCustomColor(i, QColor(color_hex))
            except Exception:
                pass
                
            if hasattr(self, '_button_indicators') and hasattr(self, '_indicator_positions'):
                for idx, pos in self._indicator_positions.items():
                    if idx < len(self._button_indicators):
                        self._button_indicators[idx].move(pos[0], pos[1])
            
            # Apply saved button mappings
            if hasattr(self, '_button_mapping_btns') and hasattr(self, '_button_mappings'):
                for i, mapping in enumerate(self._button_mappings):
                    if i < len(self._button_mapping_btns):
                        self._button_mapping_btns[i].setText(f"   {mapping}")
                        # Sync to hardware
                        self._send_button_mapping_to_hardware(i, mapping)
            print(f"[TIMING] Button mappings done: +{(_t.perf_counter()-_t0)*1000:.0f}ms")

            # Apply Saved DPI Effect Settings
            if hasattr(self, '_dpi_effect_settings'):
                e = self._dpi_effect_settings
                
                if 'mode' in e and hasattr(self, '_effect_combo'):
                    mode = int(e['mode'])
                    # Find index for this mode data
                    idx = self._effect_combo.findData(mode)
                    if idx >= 0:
                        self._effect_combo.setCurrentIndex(idx)
                        # Manually trigger handler to ensure UI state (sliders) syncs
                        self._on_dpi_effect_changed(idx)
                        
                if 'brightness' in e and hasattr(self, '_brightness_slider'):
                    val = int(e['brightness'])
                    self._brightness_slider.setValue(val)
                    self._hw_manager.enqueue('set_dpi_effect_brightness', val)
                        
                if 'speed' in e and hasattr(self, '_speed_slider'):
                    val = int(e['speed'])
                    self._speed_slider.setValue(val)
                    self._hw_manager.enqueue('set_dpi_effect_speed', val)

            # Apply Saved Sensor Settings
            if hasattr(self, '_sensor_settings'):
                s = self._sensor_settings
                
                # LOD
                if 'lod_index' in s and hasattr(self, '_lod_combo'):
                    self._lod_combo.setCurrentIndex(s['lod_index'])
                    # Hardware sync handled by signal OR we force it if signals are blocked (usually blocked during init? No, we didn't block them)
                    # But to be safe AND efficient, let's set it directly via HID if connected
                    self._hw_manager.enqueue('set_lod', s['lod_index'] + 1)
                
                # Ripple
                if 'ripple' in s and hasattr(self, '_ripple_check'):
                    self._ripple_check.setChecked(s['ripple'])
                    self._hw_manager.enqueue('set_ripple', s['ripple'])

                # Angle Snap
                if 'angle_snap' in s and hasattr(self, '_angle_snap_check'):
                    self._angle_snap_check.setChecked(s['angle_snap'])
                    self._hw_manager.enqueue('set_angle_snapping', s['angle_snap'])

                # Motion Sync
                if 'motion_sync' in s and hasattr(self, '_motion_sync_check'):
                    self._motion_sync_check.setChecked(s['motion_sync'])
                    self._hw_manager.enqueue('set_motion_sync', s['motion_sync'])

                # Debounce Time
                if 'debounce_time' in s:
                    val = int(s['debounce_time'])
                    if hasattr(self, '_debounce_slider'):
                        self._debounce_slider.setValue(val)
                        # Label update handled by signal
                        
                    self._hw_manager.enqueue('set_debounce_time', val)

                # Sensor Mode
                if 'sensor_mode' in s and hasattr(self, '_mode_combo'):
                    mode_idx = int(s['sensor_mode'])
                    self._mode_combo.setCurrentIndex(mode_idx)
                    
                    # Sync last valid mode from saved settings
                    if mode_idx in [0, 1]:
                        self._last_sensor_mode_index = mode_idx
                    elif mode_idx == 2 and self._hw_manager.get_state()['connected']:
                         # If saved as Corded, we accept it if valid
                         self._last_sensor_mode_index = mode_idx
                    
                    self._hw_manager.enqueue('set_sensor_mode', mode_idx)

                # Highest Performance
                if 'highest_performance' in s and hasattr(self, '_highest_perf_check'):
                    enabled = bool(s['highest_performance'])
                    self._highest_perf_check.setChecked(enabled)
                    self._hw_manager.enqueue('set_highest_performance', enabled)

                # Performance Time
                if 'perf_time' in s and hasattr(self, '_perf_time_combo'):
                    time_str = str(s['perf_time'])
                    self._perf_time_combo.setCurrentText(time_str)
                    # Hardware sync handled by signal via text change, but we can force it
                    mapping = {"10s": 1, "30s": 2, "1min": 3, "2min": 4, "5min": 5, "10min": 6}
                    val = mapping.get(time_str, 3)
                    self._hw_manager.enqueue('set_performance_time', val)

            # Apply saved DPI settings
            if hasattr(self, '_dpi_settings') and self._dpi_settings:
                dpi = self._dpi_settings
                
                # Apply polling rate
                if 'polling_rate_index' in dpi and hasattr(self, '_polling_buttons'):
                    idx = dpi['polling_rate_index']
                    if 0 <= idx < len(self._polling_buttons):
                        # Call select to update UI style and ensure hardware sync
                        # (Uses the open connection)
                        self._select_polling_rate(idx)
                
                # OPTIMIZATION: Apply stage VALUES and COLORS first (before setting count)
                # This ensures that when we trigger the "sync all stages" loop by setting the count,
                # we send the CORRECT saved values, not the default ones.
                
                # 1. Apply UI Colors
                if 'dpi_colors' in dpi and hasattr(self, '_dpi_stage_boxes'):
                    saved_colors = dpi['dpi_colors'] # List of [dpi, color] or similar
                    # Check format. In _pick_dpi_color we save: [[dpi, color], [dpi, color]...]
                    
                    for i, item in enumerate(saved_colors):
                        if i < len(self._dpi_stage_boxes) and len(item) >= 2:
                            box = self._dpi_stage_boxes[i]
                            # item[1] is the hex color
                            color_hex = item[1]
                            box.color = color_hex
                            box.color_bar.setStyleSheet(f"background: {color_hex}; border: none;")

                # 2. Apply Stage DPI Values
                if 'stage_values' in dpi and hasattr(self, '_dpi_stage_boxes'):
                    stage_values = dpi['stage_values']
                    for i_str, val in stage_values.items():
                        i = int(i_str)
                        if 0 <= i < len(self._dpi_stage_boxes):
                            box = self._dpi_stage_boxes[i]
                            box.dpi_value = int(val)
                            box.value_label.setText(str(val))
                            # Note: We update UI only here. Hardware sync happens when we set stages_count next.

                # Apply stages count (Triggers _on_dpi_stages_changed loop)
                # Since values are updated above, the loop will sync the correct values to hardware.
                # And since connection is open, it should be faster.
                print(f"[TIMING] DPI values/colors done: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
                if 'stages_count' in dpi and hasattr(self, '_dpi_stages_combo'):
                    count = str(dpi['stages_count'])
                    self._dpi_stages_combo.blockSignals(True)
                    self._dpi_stages_combo.setCurrentText(count)
                    self._dpi_stages_combo.blockSignals(False)
                    # Manually call handler to ensure logic runs without signal recursion
                    self._on_dpi_stages_changed(count)
                print(f"[TIMING] DPI stages combo set: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
                
                # Apply current stage (do this last to update slider)
                if 'current_stage_index' in dpi:
                    idx = dpi['current_stage_index']
                    # Crucial: NO from_hardware=True here.
                    # We MUST write the saved stage to the mouse on startup.
                    self._select_dpi_stage(idx)
                print(f"[TIMING] DPI stage select done: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
            
            print(f"[TIMING] _apply_saved TOTAL: +{(_t.perf_counter()-_t0)*1000:.0f}ms")
        finally:
            self._loading_settings = False
            self._syncing_to_hardware = False
    
    def _create_info_label(self, text: str) -> QLabel:
        """Create a styled info label for device info card."""
        label = QLabel(text)
        label.setStyleSheet("color: #888; font-size: 12px; font-weight: 500;")
        label.setFixedWidth(80)
        return label
    
    def _create_stat_widget(self, title: str, value: str) -> QWidget:
        """Create a stat widget with title and value for Quick Stats card."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        value_label.setStyleSheet("color: #FF5B06;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 10))
        title_label.setStyleSheet("color: #888;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Store reference for updating later
        widget.value_label = value_label
        return widget

        
    def showEvent(self, event):
        """Called when panel becomes visible."""
        super().showEvent(event)
        
        # Start timers for UI and hardware updates
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()
            print("[HELXAIRO] Refresh timer started")
            
        # The _hw_poll_timer and _conn_check_timer are now managed by HardwareManager
        # No need to start them here.
            
        # Init bridge if needed
        if not self._bridge:
            self._init_bridge()
            
        # Ensure bridge is running if initialized
        if self._bridge and not self._bridge.is_running:
            try:
                self._bridge.start()
                print("[HELXAIRO] Macro system started in showEvent")
            except Exception as e:
                print(f"[HELXAIRO] Failed to start macro bridge in showEvent: {e}")
                
        self._load_data()
    
    def hideEvent(self, event):
        """Called when panel becomes hidden."""
        super().hideEvent(event)
        # Stop timers to avoid unnecessary updates when hidden
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        # The _hw_poll_timer and _conn_check_timer are now managed by HardwareManager
        # No need to stop them here.
        print("[HELXAIRO] All update timers stopped")
    
    def _refresh_macro_status(self):
        """Refresh macro list status without full reload (preserves selection)."""
        if not self._bridge or not self._bridge.profile_manager:
            return
        
        # Update each item's status in place
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            macro = item.data(Qt.UserRole + 1)
            if macro:
                status = "✓" if macro.enabled else "○"
                type_name = type(macro).__name__.replace("Macro", "")
                
                trigger_str = ""
                if macro.trigger:
                    if macro.trigger.button:
                        trigger_str = f"[{macro.trigger.button}]"
                    elif macro.trigger.key:
                        trigger_str = f"[{macro.trigger.key.upper()}]"
                
                new_text = f"{status} {macro.name} {trigger_str} - {type_name}"
                if item.text() != new_text:
                    item.setText(new_text)
        
        # Also update system status
        self._update_status()
        
    def _load_data(self):
        """Load data from macro bridge."""
        self._update_status()
        self._load_macros()
        self._load_profiles()
        
    def _update_status(self):
        """Update system status display."""
        # Note: status_label and toggle_btn were removed (replaced with battery indicator)
        # This method is kept for compatibility but does nothing now
        # The bridge auto-starts and runs continuously
        pass
            
    def _toggle_system(self):
        """Toggle macro system on/off."""
        if not self._bridge:
            self._init_bridge()
            
        if not self._bridge:
            return
            
        if self._bridge.is_running:
            self._bridge.stop()
        else:
            self._bridge.start()
            
        self._update_status()
        self._load_macros()
        
    def _auto_init_macro_system(self):
        """Auto-initializing and start macro system on panel load."""
        try:
            import time as _t; _s = _t.perf_counter()
            print("[TIMING] _auto_init_macro_system START")
            self._init_bridge()
            print(f"[TIMING] _init_bridge done: +{(_t.perf_counter()-_s)*1000:.0f}ms")
            if self._bridge and not self._bridge.is_running:
                self._bridge.start()
                print(f"[TIMING] bridge.start done: +{(_t.perf_counter()-_s)*1000:.0f}ms")
            self._load_macros()
            print(f"[TIMING] _load_macros done: +{(_t.perf_counter()-_s)*1000:.0f}ms")
            self._load_profiles()
            print(f"[TIMING] _auto_init TOTAL: +{(_t.perf_counter()-_s)*1000:.0f}ms")
        except Exception as e:
            print(f"[HELXAIRO] Failed to auto-init macro system: {e}")
    
    def _init_bridge(self):
        """Initialize the macro bridge if not already, using parent's bridge if available."""
        if self._bridge:
            return
            
        try:
            # First try to get existing bridge from parent (GameLauncher)
            parent = self.parent()
            # Traverse up to find GameLauncher if parent is not it directly
            while parent and not hasattr(parent, 'get_macro_bridge'):
                # Try sibling or grand-parent if needed, but usually it's the MainWindow
                if hasattr(parent, 'parent'):
                    parent = parent.parent()
                else:
                    break
                    
            if parent and hasattr(parent, 'get_macro_bridge'):
                print("[HELXAIRO] Attempting to use parent's macro bridge...")
                self._bridge = parent.get_macro_bridge()
                    
            if not self._bridge:
                # Fallback to creating local bridge if not found in parent hierachy or if parent returned None
                print("[HELXAIRO] Parent bridge not available, creating local instance...")
                from macro_system.integration import LauncherBridge
                self._bridge = LauncherBridge()
                self._bridge.initialize()
        except Exception as e:
            print(f"[HELXAIRO] Failed to initialize macro bridge: {e}")
            
    def _load_macros(self):
        """Load macros into list."""
        print("[MacroPanel] Loading macros into list...")
        self.active_list.clear()
        
        if not self._bridge or not self._bridge.profile_manager:
            print("[MacroPanel] Error: Bridge or profile manager not available")
            return
            
        profiles = self._bridge.profile_manager.get_all_profiles()
        print(f"[MacroPanel] Found {len(profiles)} profiles")
        
        for profile in profiles:
            macros = self._bridge.profile_manager.get_macros_for_profile(profile.id)
            print(f"[MacroPanel] Profile '{profile.name}' has {len(macros)} macros")
            
            for macro in macros:
                try:
                    status = "✓" if macro.enabled else "○"
                    type_name = type(macro).__name__.replace("Macro", "")
                    
                    trigger_str = ""
                    if macro.trigger:
                        if macro.trigger.button:
                            trigger_str = f"[{macro.trigger.button}]"
                        elif macro.trigger.key:
                            trigger_str = f"[{macro.trigger.key.upper()}]"
                            
                    item = QListWidgetItem(f"{status} {macro.name} {trigger_str} - {type_name}")
                    item.setData(Qt.UserRole, macro.id)
                    item.setData(Qt.UserRole + 1, macro)
                    self.active_list.addItem(item)
                except Exception as e:
                    print(f"[MacroPanel] Error adding macro item: {e}")
                
    def _load_profiles(self):
        """Load profiles into list."""
        self.profile_list.clear()
        
        if not self._bridge or not self._bridge.profile_manager:
            # Show default even if not initialized
            item = QListWidgetItem("Default")
            item.setData(Qt.UserRole, "default")
            self.profile_list.addItem(item)
            return
            
        for profile in self._bridge.profile_manager.get_all_profiles():
            item = QListWidgetItem(profile.name)
            item.setData(Qt.UserRole, profile.id)
            self.profile_list.addItem(item)
            
    def _on_profile_selected(self, current, previous):
        """Handle profile selection."""
        if not current or not self._bridge:
            return
            
        profile_id = current.data(Qt.UserRole)
        profile = self._bridge.profile_manager.get_profile(profile_id)
        
        if profile:
            self.profile_name.setText(profile.name)
            self.profile_apps.setText(", ".join(profile.bound_apps))
                
    def _on_ac_type_changed(self, text: str):
        """Show/hide custom key input based on dropdown selection."""
        is_custom = (text == "Custom Key")
        self.ac_custom_key.setVisible(is_custom)
    
    def _create_autoclicker(self):
        """Create auto-clicker from quick action."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
            if not self._bridge.is_running:
                self._bridge.start()
            
        selected = self.ac_button.currentText()
        
        # Determine if it's a mouse button or custom key
        if selected == "Custom Key":
            # Use custom key for key-based auto-clicker
            custom_key = self.ac_custom_key.hotkey().lower().strip()
            button = f"key:{custom_key}"  # Special format for key press
        else:
            button_map = {"Left Click": "left", "Right Click": "right", "Middle Click": "middle"}
            button = button_map.get(selected, "left")
        
        interval = self.ac_interval.value()
        hotkey = self.ac_hotkey.hotkey().lower().strip()
        
        macro_id = self._bridge.create_quick_autoclicker(button, interval, hotkey)
        
        if selected == "Custom Key":
            QMessageBox.information(self, "Created", f"Key auto-presser created!\nKey: {custom_key.upper()}\nToggle with: {hotkey.upper()}")
        else:
            QMessageBox.information(self, "Created", f"Auto-clicker created!\nToggle with: {hotkey.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _create_remap(self):
        """Create button remap from quick action."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
            if not self._bridge.is_running:
                self._bridge.start()
            
        from_map = {"X1 (Side)": "x1", "X2 (Side)": "x2", "Middle": "middle"}
        from_btn = from_map.get(self.remap_from.currentText(), "x1")
        to_key = self.remap_to.hotkey().lower().strip()
        
        macro_id = self._bridge.create_quick_remap(from_btn, to_key)
        QMessageBox.information(self, "Created", f"Remap created!\n{from_btn.upper()} → {to_key.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _toggle_selected_macro(self):
        """Toggle the selected macro's enabled state."""
        current = self.active_list.currentItem()
        if not current:
            return
            
        macro = current.data(Qt.UserRole + 1)
        if macro:
            macro.enabled = not macro.enabled
            self._load_macros()
            
    def _disable_all(self):
        """Disable all running macros."""
        if not self._bridge or not self._bridge.engine:
            return
            
        self._bridge.engine.cancel_all_macros()
        QMessageBox.information(self, "Stopped", "All active macros stopped.")
        
    def _delete_selected(self):
        """Delete selected macro."""
        current = self.active_list.currentItem()
        if not current:
            return
            
        macro_id = current.data(Qt.UserRole)
        
        reply = QMessageBox.question(self, "Delete Macro",
            "Delete this macro?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.Yes:
            self._bridge.profile_manager.remove_macro(macro_id)
            self._bridge.profile_manager.save_all()
            self._load_macros()
            self.macros_changed.emit()
            
    def _new_profile(self):
        """Create new profile."""
        from PySide6.QtWidgets import QInputDialog
        
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
        
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
            
        if reply == QMessageBox.Yes and self._bridge:
            self._bridge.profile_manager.delete_profile(profile_id)
            self._load_profiles()
            
    def _save_profile(self):
        """Save current profile settings."""
        current = self.profile_list.currentItem()
        if not current or not self._bridge:
            return
            
        profile_id = current.data(Qt.UserRole)
        profile = self._bridge.profile_manager.get_profile(profile_id)
        
        if profile:
            profile.name = self.profile_name.text()
            profile.bound_apps = [a.strip() for a in self.profile_apps.text().split(",") if a.strip()]
            self._bridge.profile_manager.save_profile(profile)
            self._load_profiles()
            QMessageBox.information(self, "Saved", "Profile saved!")
            
    # ===== MACRO RECORDER METHODS =====
    
    def _init_recorder(self):
        """Initialize the macro recorder if not already."""
        if self._recorder is None:
            try:
                from .macro_system.core.macro_engine import MacroEngine, MacroState
                from .macro_system.core.input_listener import MouseButton
                from .macro_system.integration.hardware_manager import get_hardware_manager
                from macro_system.core.macro_recorder import MacroRecorder, MacroPlayer
                from macro_system.core.input_listener import InputListener
                self._recorder = MacroRecorder()
                self._recorder.on_action_recorded = self._on_action_recorded
                self._player = MacroPlayer()
                
                # Create separate input listener for recording
                self._recording_listener = InputListener()
                self._recording_listener.on_mouse_event = self._on_mouse_for_recording
                self._recording_listener.on_keyboard_event = self._on_keyboard_for_recording
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to init recorder: {e}")
                return False
        return True
        
    def _toggle_recording(self):
        """Toggle recording on/off."""
        if not self._init_recorder():
            return
            
        if self._recorder.is_recording:
            # Stop recording
            self._current_recording = self._recorder.stop_recording()
            self.record_btn.setText("Record")
            self.record_btn.setStyleSheet("")
            self.record_status.setText(f"Recorded {len(self._current_recording.actions)} actions")
            self.record_status.setStyleSheet("color: #2ecc71;")
            
            # Enable save/play buttons
            self.save_recording_btn.setEnabled(True)
            self.play_recording_btn.setEnabled(True)
            
            # Stop the recording input listener
            if hasattr(self, '_recording_listener') and self._recording_listener:
                self._recording_listener.stop()
        else:
            # Apply filter settings
            self._recorder.record_mouse_clicks = self.record_mouse_cb.isChecked()
            self._recorder.record_mouse_movement = self.record_movement_cb.isChecked()
            self._recorder.record_keyboard = self.record_keyboard_cb.isChecked()
            
            # Start recording
            self._recorder.start_recording()
            self.record_btn.setText("Stop")
            self.record_btn.setStyleSheet("background: #e74c3c; color: white;")
            self.record_status.setText("Recording...")
            self.record_status.setStyleSheet("color: #e74c3c;")
            
            # Start the recording input listener
            if hasattr(self, '_recording_listener') and self._recording_listener:
                # PERFORMANCE: Only listen to move if user wants to record it
                self._recording_listener.listen_to_move = self.record_movement_cb.isChecked()
                self._recording_listener.start()
                
    def _on_mouse_for_recording(self, event):
        """Handle mouse event for recording."""
        if self._recorder and self._recorder.is_recording:
            button_str = event.button.value if event.button else None
            self._recorder.record_mouse_event(
                event.type.value,
                button_str,
                event.x,
                event.y,
                event.delta
            )
        return False  # Don't suppress
        
    def _on_keyboard_for_recording(self, event):
        """Handle keyboard event for recording."""
        if self._recorder and self._recorder.is_recording:
            self._recorder.record_keyboard_event(
                event.type.value,
                event.key_code,
                event.key_name
            )
        return False  # Don't suppress
        
    def _on_action_recorded(self, action):
        """Called when an action is recorded."""
        if self._recorder:
            self.action_count_label.setText(f"{self._recorder.action_count} actions")
            
    def _save_recording(self):
        """Save the current recording as a macro."""
        if not self._current_recording:
            return
            
        # Get speed multiplier
        speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0}
        self._current_recording.speed_multiplier = speed_map.get(self.speed_combo.currentText(), 1.0)
        self._current_recording.loop_count = self.loop_spin.value()
        self._current_recording.playback_hotkey = self.playback_hotkey.hotkey()
        
        # Save to recordings folder
        import os
        import json
        import sys
        if getattr(sys, 'frozen', False):
            # If frozen, use executable dir
            base_dir = os.path.dirname(sys.executable)
        else:
            # If script, use script dir
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        recordings_dir = os.path.join(base_dir, "macro_recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        
        filename = f"recording_{int(self._current_recording.created_at)}.json"
        filepath = os.path.join(recordings_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(self._current_recording.to_dict(), f, indent=2)
            
        QMessageBox.information(self, "Saved", f"Recording saved!\nHotkey: {self._current_recording.playback_hotkey.upper()}")
        
    def _play_recording(self):
        """Play the current recording."""
        if not self._current_recording or not self._player:
            return
            
        if self._player.is_playing:
            self._player.stop()
            self.play_recording_btn.setText("Play")
            return
            
        # Get speed
        speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0}
        self._current_recording.speed_multiplier = speed_map.get(self.speed_combo.currentText(), 1.0)
        self._current_recording.loop_count = self.loop_spin.value()
        
        # Get simulator
        if not self._bridge:
            self._init_bridge()
        if not self._bridge:
            return
            
        self.play_recording_btn.setText("Stop")

    # ===== PROFILE MANAGEMENT (HELXAIRO) =====
    
    def _get_helxairo_settings_path(self, profile_index: int = None) -> str:
        """Get path to settings file. If index None, use current profile."""
        import os
        base_dir = os.path.join(os.getenv('APPDATA'), 'HELXAID')
        os.makedirs(base_dir, exist_ok=True)
        
        idx = profile_index if profile_index is not None else getattr(self, '_current_profile_index', 0)
        
        # Profile 0 is default/legacy
        if idx == 0:
            return os.path.join(base_dir, 'helxairo_settings.json')
        else:
            return os.path.join(base_dir, f'helxairo_settings_profile_{idx}.json')

    def _on_profile_changed(self, index: int):
        """Handle profile change from Home or Settings tab."""
        if getattr(self, '_updating_profile', False):
            return
        
        old_idx = getattr(self, '_current_profile_index', 0)
        if index == old_idx:
            return

        print(f"[HELXAIRO] Switching Profile: {old_idx + 1} -> {index + 1}")
        
        # 1. Save CURRENT settings to OLD profile
        # Ensure _current_profile_index is still old_idx
        self._save_helxairo_settings()
        
        # 2. Update Index
        self._current_profile_index = index
        
        # 3. Synchronize UI Combos
        # 3. Synchronize UI Combos
        self._updating_profile = True
        try:
            if hasattr(self, '_profile_combo'):
                print(f"[HELXAIRO-DEBUG] Home combo state: index={self._profile_combo.currentIndex()} text='{self._profile_combo.currentText()}' visible={self._profile_combo.isVisible()}")
                
                # Always set current index to make sure
                if self._profile_combo.currentIndex() != index:
                    self._profile_combo.setCurrentIndex(index)
                
                # Schedule visual force update
                from PySide6.QtCore import QTimer
                QTimer.singleShot(50, lambda: self._force_update_combo_visual(index))
                
            if hasattr(self, '_profile_settings_combo'):
                if self._profile_settings_combo.currentIndex() != index:
                    self._profile_settings_combo.setCurrentIndex(index)
        finally:
            self._updating_profile = False
            
        # 4. Load NEW settings and Apply
        # We manually call load to update internal dicts
        if not self._load_helxairo_settings():
            self._load_defaults_for_new_profile()
            
        # 5. Apply to UI and Hardware
        # _apply_saved_helxairo_settings calls _load again internally, but that's fine (just extra read)
        # It handles the full UI refresh and Hardware Sync
        self._apply_saved_helxairo_settings()
        
        # 6. Save Global State
        self._save_global_state()

    def _save_global_state(self):
        """Save global state (active profile index)."""
        import os
        import json
        path = os.path.join(os.getenv('APPDATA'), 'HELXAID', 'helxairo_global.json')
        try:
            from PySide6.QtWidgets import QColorDialog
            custom_colors = [QColorDialog.customColor(i).name() for i in range(16)]
        except Exception:
            custom_colors = []
            
        try:
            state = {
                'active_profile_index': getattr(self, '_current_profile_index', 0),
                'indicator_positions': {str(k): v for k, v in getattr(self, '_indicator_positions', {}).items()},
                'custom_colors': custom_colors
            }
            with open(path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[HELXAIRO] Failed to save global state: {e}")
            
    def _load_defaults_for_new_profile(self):
        """Reset internal variables to defaults for a fresh profile."""
        self._dpi_settings = {}
        self._button_mappings = self._get_default_button_mappings()
        self._sensor_settings = {}
        self._dpi_effect_settings = {}
        print("[HELXAIRO] Loaded defaults for new profile")



    def _force_update_combo_visual(self, index):
        """Hack to force visual update of the combo box."""
        if not hasattr(self, '_profile_combo'):
            return
            
        print(f"[HELXAIRO-DEBUG] Forcing combo visual update for index {index}")
        try:
            # Block signals to prevent recursive calls
            was_blocked = self._profile_combo.blockSignals(True)
            
            # 1. Reset selection temporarily
            self._profile_combo.setCurrentIndex(-1)
            
            # 2. Set correct selection
            self._profile_combo.setCurrentIndex(index)
            
            # 3. Force repaint
            self._profile_combo.repaint()
            self._profile_combo.update()
            
            # 4. Check text
            print(f"[HELXAIRO-DEBUG] Post-force text: '{self._profile_combo.currentText()}' (Expected: 'Profile {index + 1}')")
            
            self._profile_combo.blockSignals(was_blocked)
        except Exception as e:
            print(f"[HELXAIRO-DEBUG] Force update error: {e}")


        
    def _clear_recording(self):
        """Clear the current recording."""
        if self._recorder:
            self._recorder.clear()
        self._current_recording = None
        self.action_count_label.setText("0 actions")
        self.record_status.setText("Ready")
        self.record_status.setStyleSheet("color: #888;")
        self.save_recording_btn.setEnabled(False)
        self.play_recording_btn.setEnabled(False)

    def _update_battery_display(self):
        """Update battery UI using cached state from HardwareManager (Non-blocking)."""
        if not hasattr(self, '_battery_label') or not hasattr(self, '_battery_bar') or not hasattr(self, '_charging_label'):
            return
        try:
            state = self._hw_manager.get_state()
            is_connected = state.get('connected', False)
            
            if not is_connected:
                self._battery_label.setText("---%")
                self._charging_label.setText("")
                self._battery_bar.setFixedWidth(30)
                self._battery_bar.setStyleSheet("""
                    QWidget#batteryBar {
                        background: #444;
                        border: none;
                        border-radius: 3px;
                    }
                """)
                return

            # Get values from HardwareManager state (updated periodically in BG thread)
            percentage = state.get('battery_level', -1)
            is_charging = state.get('is_charging', False)

            if percentage >= 0:
                # Show ⚡ emoji and style text yellow while charging
                if is_charging:
                    self._charging_label.setText("⚡")
                    self._charging_label.setStyleSheet("color: #FFD600; font-size: 14px;")
                    self._battery_label.setText(f"{percentage}%")
                    self._battery_label.setStyleSheet("color: #FFD600; font-size: 12px; font-weight: bold;")
                else:
                    self._charging_label.setText("")
                    self._charging_label.setStyleSheet("")
                    self._battery_label.setText(f"{percentage}%")
                    self._battery_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: bold;")
                
                # Update bar width (max 30px)
                bar_width = max(2, int((percentage / 100.0) * 30))
                self._battery_bar.setFixedWidth(bar_width)
                
                # Bar color: amber while charging, level-based when not charging
                if is_charging:
                    color  = "#FFD600"
                    color2 = "#FFA000"
                elif percentage <= 15:
                    color  = "#ff3333"
                    color2 = "#cc0000"
                elif percentage <= 30:
                    color  = "#ffaa00"
                    color2 = "#cc8800"
                else:
                    color  = "#4CAF50"
                    color2 = "#8BC34A"
                    
                self._battery_bar.setStyleSheet(f"""
                    QWidget#batteryBar {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {color}, stop:1 {color2});
                        border: none;
                        border-radius: 3px;
                    }}
                """)
            else:
                self._battery_label.setText("READING...")
        except Exception as e:
            print(f"[MacroSettingsPanel] Battery update error: {e}")
    
    def _on_refresh_connection_clicked(self):
        """Force the HardwareManager to re-enumerate and reconnect to the mouse.
        
        Useful when the mouse was unplugged/replugged or the wireless dongle lost
        sync since the app started. Enqueues a high-priority 'force_reconnect'
        command and provides brief visual feedback on the button.
        """
        if not hasattr(self, '_refresh_btn'):
            return
        
        # Visual feedback: disable button temporarily and update tooltip
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setToolTip("Refreshing...")
        self._refresh_btn.setStyleSheet("""
            QPushButton#helxairo_refreshBtn {
                background: rgba(255, 91, 6, 0.4);
                border: none;
                border-radius: 8px;
                padding: 0px;
            }
        """)
        
        # Enqueue the reconnect at high priority so it runs before polling
        self._hw_manager.enqueue('force_reconnect', priority=1)
        
        def _restore_btn():
            """Restore button state after reconnect attempt completes."""
            if hasattr(self, '_refresh_btn') and self._refresh_btn:
                self._refresh_btn.setEnabled(True)
                self._refresh_btn.setToolTip("Refresh mouse connection")
                self._refresh_btn.setStyleSheet("""
                    QPushButton#helxairo_refreshBtn {
                        background: rgba(40, 40, 40, 0.8);
                        border: none;
                        border-radius: 8px;
                        padding: 0px;
                    }
                    QPushButton#helxairo_refreshBtn:hover {
                        background: rgba(255, 91, 6, 0.25);
                        border-color: transparent;
                    }
                    QPushButton#helxairo_refreshBtn:pressed {
                        background: rgba(255, 91, 6, 0.5);
                    }
                """)
            # Force immediate battery + connection UI refresh
            self._update_battery_display()
        
        # Give the background thread ~2s to finish reconnect before restoring UI
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, _restore_btn)

