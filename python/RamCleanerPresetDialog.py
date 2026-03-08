"""
RAM Cleaner Custom Preset Dialog

A 4-tab dialog for configuring custom RAM cleaner presets in HELXAID.
- Tab 1: Essential Optimizations (CPU/Memory toggles)
- Tab 2: Background Processes (running processes list)
- Tab 3: Basic Windows Services (safe to stop)
- Tab 4: Advanced Windows Services (risky)

Component Name: RamCleanerPresetDialog
"""

import os
import sys
import psutil
from dataclasses import dataclass
from typing import List, Optional, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QScrollArea, QCheckBox, QFrame, QStackedWidget,
    QGridLayout, QSizePolicy
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtGui import QFont, QIcon, QPixmap, QCursor, QPainter, QColor
from PySide6.QtCore import Qt, Signal


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class OptimizationItem:
    """Essential optimization toggle item."""
    id: str
    name: str
    description: str
    enabled: bool = False


@dataclass  
class ProcessItem:
    """Running process item."""
    pid: int
    name: str
    exe_path: str
    memory_mb: float
    icon: Optional[QPixmap] = None
    selected: bool = False


@dataclass
class ServiceItem:
    """Windows service item."""
    name: str
    display_name: str
    description: str
    status: str = "Unknown"
    selected: bool = False


# ============================================================================
# Predefined Lists
# ============================================================================

ESSENTIAL_OPTIMIZATIONS = [
    {"id": "clear_clipboard", "name": "Clear Clipboard", 
     "description": "Clear Clipboard history to release memory"},
    {"id": "disable_dvr", "name": "Disable automatic background recording",
     "description": "Temporarily disables automatic background video recording (DVR)"},
    {"id": "disable_updates", "name": "Disable Automatic Updates",
     "description": "Temporarily disable Windows automatic updates"},
    {"id": "disable_core_parking", "name": "Disable CPU Core Parking",
     "description": "Prevents CPU cores from sleeping - keeps all cores active for maximum gaming performance"},
    {"id": "disable_file_sharing", "name": "Disable File and Printer Sharing",
     "description": "Temporarily disable File and Printer Sharing"},
    {"id": "disable_game_bar", "name": "Disable Game Bar",
     "description": "Temporarily disables the Microsoft Game Bar"},
    {"id": "disable_game_mode", "name": "Disable Game Mode",
     "description": "Turn off Game Mode from Windows Settings"},
    {"id": "disable_winkey", "name": "Disable Windows Key",
     "description": "Temporarily disables the Windows key"},
    {"id": "memory_boost", "name": "Memory Boost",
     "description": "Clear unused working and standby memory"},
    {"id": "set_game_priority", "name": "Set game process to High Priority",
     "description": "Temporarily sets the process of the game to High Priority to allow the OS to prioritize CPU and RAM resources to the game."}
]

BASIC_SERVICES = [
    {"name": "defragsvc", "display": "Optimize Drives", 
     "desc": "Helps the computer run more efficiently by optimizing files on storage drives"},
    {"name": "DiagTrack", "display": "Connected User Experiences",
     "desc": "Telemetry service for diagnostics and usage information"},
    {"name": "DoSvc", "display": "Delivery Optimization",
     "desc": "Performs content delivery optimization tasks"},
    {"name": "DPS", "display": "Diagnostic Policy Service",
     "desc": "Enables problem detection and troubleshooting for Windows components"},
    {"name": "ShellHWDetection", "display": "Shell Hardware Detection",
     "desc": "Provides notifications for AutoPlay hardware events"},
    {"name": "Spooler", "display": "Print Spooler",
     "desc": "Spools print jobs and handles interaction with the printer"},
    {"name": "SstpSvc", "display": "SSTP Service",
     "desc": "Provides support for the Secure Socket Tunneling Protocol (SSTP) to connect to remote computers using VPN"},
    {"name": "StorSvc", "display": "Storage Service",
     "desc": "Provides enabling services for storage settings and external storage expansion"},
    {"name": "SysMain", "display": "SysMain (Superfetch)",
     "desc": "Maintains and improves system performance over time"},
    {"name": "TrkWks", "display": "Distributed Link Tracking",
     "desc": "Maintains links between NTFS files within a computer or across computers in a network"},
    {"name": "UsoSvc", "display": "Update Orchestrator",
     "desc": "Manages Windows Updates. If stopped, your devices will not be able to download and install the latest updates"},
    {"name": "VaultSvc", "display": "Credential Manager",
     "desc": "Provides secure storage and retrieval of credentials to users, applications and security service packages"},
    {"name": "wuauserv", "display": "Windows Update",
     "desc": "Enables detection, download, and installation of updates"}
]

ADVANCED_SERVICES = [
    {"name": "AppReadiness", "display": "App Readiness",
     "desc": "Gets apps ready for use the first time a user signs in to this PC and when adding new apps"},
    {"name": "BTAGService", "display": "Bluetooth Audio Gateway",
     "desc": "Service supporting the audio gateway role of the Bluetooth Handsfree Profile"},
    {"name": "BthAvctpSvc", "display": "AVCTP Service",
     "desc": "This is Audio Video Control Transport Protocol service"},
    {"name": "DeviceAssociationService", "display": "Device Association",
     "desc": "Enables pairing between the system and wired or wireless devices"},
    {"name": "DeviceInstall", "display": "Device Install Service",
     "desc": "Enables a computer to recognize and adapt to hardware changes with little or no user input"},
    {"name": "dmwappushservice", "display": "WAP Push Message",
     "desc": "Routes Wireless Application Protocol (WAP) Push messages received by the device and synchronizes Device Management sessions"},
    {"name": "DsmSvc", "display": "Device Setup Manager",
     "desc": "Enables the detection, download and installation of device-related software"},
    {"name": "DusmSvc", "display": "Data Usage",
     "desc": "Network data usage, data limit, restrict background data, metered networks"},
    {"name": "LanmanWorkstation", "display": "Workstation",
     "desc": "Creates and maintains client network connections to remote servers using the SMB protocol"},
    {"name": "Themes", "display": "Themes",
     "desc": "Provides user experience theme management"},
    {"name": "wlidsvc", "display": "Microsoft Account Sign-in",
     "desc": "Enables user sign-in through Microsoft account identity services. If stopped, users will not be able to logon with their Microsoft account"}
]

# Tab descriptions
TAB_DESCRIPTIONS = [
    "Essential items for CPU and memory optimization for overall performance boost.",
    "Selected background processes will be automatically closed during Boost. We recommend only selecting the ones you are familiar with.",
    "Basic Windows Services that can be safely turned off to free up system resources while gaming.",
    "Advanced Windows Services. Terminating these may disrupt normal operation of your PC."
]


# ============================================================================
# Helper Functions
# ============================================================================

def format_memory_size(bytes_val: int) -> str:
    """Format bytes to human readable (e.g., 1.25 GB, 890 MB)."""
    if bytes_val >= 1024 ** 3:
        return f"{bytes_val / (1024 ** 3):.2f} GB"
    elif bytes_val >= 1024 ** 2:
        return f"{bytes_val / (1024 ** 2):.0f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.0f} KB"
    return f"{bytes_val} B"


def get_service_status(service_name: str) -> str:
    """Get status of a Windows service using native module."""
    try:
        import native_wrapper
        engine = native_wrapper.get_boost_engine()
        if engine:
            res = engine.query_service_statuses([service_name])
            if res and len(res) > 0:
                status = res[0].status
                if status == "Running":
                    return "Running"
                elif status == "Stopped":
                    return "Stopped"
                return status
    except Exception as e:
        print(f"[Boost] get_service_status native error: {e}")
    
    return "Unknown"


# ============================================================================
# Tab Button Widget
# ============================================================================

class TabButton(QPushButton):
    """Custom tab button with icon and count display."""
    
    def __init__(self, icon: str, index: int, parent=None):
        super().__init__(parent)
        self.tab_index = index
        self._icon = icon
        self._count = (0, 0)  # (selected, total)
        self._active = False
        self.setObjectName(f"tabButton_{index}")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(45)
        self.setMinimumWidth(100)
        self._update_text()
        self._apply_style()
    
    def set_count(self, selected: int, total: int):
        """Update the count display."""
        self._count = (selected, total)
        self._update_text()
    
    def set_active(self, active: bool):
        """Set tab as active/inactive."""
        self._active = active
        self._apply_style()
    
    def _update_text(self):
        """Update button text with icon and count."""
        self.setText(f"{self._icon} ({self._count[0]}/{self._count[1]})")
    
    def _apply_style(self):
        """Apply styling based on active state."""
        if self._active:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #e0e0e0;
                    border: none;
                    border-bottom: 2px solid #FF5B06;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 8px 16px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #888888;
                    border: none;
                    border-bottom: 2px solid transparent;
                    font-size: 13px;
                    font-weight: 500;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    color: #b0b0b0;
                    border-bottom: 2px solid #444444;
                }
            """)


# ============================================================================
# Item Row Widgets
# ============================================================================

class OptimizationRow(QFrame):
    """Row widget for essential optimization items."""
    
    toggled = Signal(str, bool)  # (item_id, checked)
    
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item_id = item["id"]
        self.setObjectName(f"optRow_{item['id']}")
        self.setFixedHeight(50)
        self._setup_ui(item)
        self._apply_style()
    
    def _setup_ui(self, item: dict):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(15)
        
        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setObjectName(f"optCheck_{item['id']}")
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.toggled.connect(lambda c: self.toggled.emit(self.item_id, c))
        layout.addWidget(self.checkbox)
        
        # Name
        name_label = QLabel(item["name"])
        name_label.setObjectName("optName")
        name_label.setFixedWidth(200)
        name_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 500; background: transparent;")
        layout.addWidget(name_label)
        
        # Description
        desc_label = QLabel(item["description"])
        desc_label.setObjectName("optDesc")
        desc_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label, 1)
    
    def _apply_style(self):
        self.setStyleSheet("""
            QFrame {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QFrame:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555;
                border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06;
                border-color: #FF5B06;
            }
            QCheckBox::indicator:hover {
                border-color: #FF5B06;
            }
        """)
    
    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)
    
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


class ProcessRow(QFrame):
    """Row widget for process items."""
    
    toggled = Signal(int, bool)  # (pid, checked)
    
    def __init__(self, proc: ProcessItem, parent=None):
        super().__init__(parent)
        self.pid = proc.pid
        self.setObjectName(f"procRow_{proc.pid}")
        self.setFixedHeight(45)
        self._setup_ui(proc)
        self._apply_style()
    
    def _setup_ui(self, proc: ProcessItem):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(12)
        
        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.toggled.connect(lambda c: self.toggled.emit(self.pid, c))
        layout.addWidget(self.checkbox)
        
        # Icon placeholder
        icon_label = QLabel("")
        icon_label.setFixedSize(24, 24)
        icon_label.setStyleSheet("font-size: 16px; background: transparent;")
        layout.addWidget(icon_label)
        
        # Name
        name_label = QLabel(proc.name)
        name_label.setStyleSheet("color: #e0e0e0; font-size: 12px; background: transparent;")
        layout.addWidget(name_label, 1)
        
        # Memory usage
        mem_label = QLabel(format_memory_size(int(proc.memory_mb * 1024 * 1024)))
        mem_label.setFixedWidth(80)
        mem_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        mem_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        layout.addWidget(mem_label)
    
    def _apply_style(self):
        self.setStyleSheet("""
            QFrame {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QFrame:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 2px solid #555; border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06; border-color: #FF5B06;
            }
        """)
    
    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)
    
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


class ServiceRow(QFrame):
    """Row widget for service items."""
    
    toggled = Signal(str, bool)  # (service_name, checked)
    
    def __init__(self, svc: dict, status: str, parent=None):
        super().__init__(parent)
        self.service_name = svc["name"]
        self.setObjectName(f"svcRow_{svc['name']}")
        self.setFixedHeight(60)
        self._setup_ui(svc, status)
        self._apply_style()
    
    def _setup_ui(self, svc: dict, status: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(12)
        
        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.toggled.connect(lambda c: self.toggled.emit(self.service_name, c))
        layout.addWidget(self.checkbox)
        
        # Name
        name_label = QLabel(svc["display"])
        name_label.setFixedWidth(150)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 500; background: transparent;")
        layout.addWidget(name_label)
        
        # Status
        status_color = "#4ade80" if status == "Running" else "#888888"
        status_label = QLabel(status)
        status_label.setFixedWidth(70)
        status_label.setStyleSheet(f"color: {status_color}; font-size: 11px; background: transparent;")
        layout.addWidget(status_label)
        
        # Description
        desc_label = QLabel(svc["desc"])
        desc_label.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label, 1)
    
    def _apply_style(self):
        self.setStyleSheet("""
            QFrame {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QFrame:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 2px solid #555; border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06; border-color: #FF5B06;
            }
        """)
    
    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)
    
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


# ============================================================================
# Main Dialog
# ============================================================================

class RamCleanerPresetDialog(QDialog):
    """
    Dialog for configuring custom RAM cleaner presets.
    
    Component Name: RamCleanerPresetDialog
    """
    
    presetsChanged = Signal(dict)  # Emitted when user saves changes
    
    def __init__(self, parent=None, config: dict = None):
        super().__init__(parent)
        self.setObjectName("RamCleanerPresetDialog")
        self.setWindowTitle("Custom Preset Configuration")
        self.setFixedSize(750, 550)
        self.setModal(True)
        
        self._config = config or {}
        self._current_tab = 0
        
        # Item tracking
        self._optimization_rows: List[OptimizationRow] = []
        self._process_rows: List[ProcessRow] = []
        self._basic_service_rows: List[ServiceRow] = []
        self._advanced_service_rows: List[ServiceRow] = []
        
        self._setup_ui()
        self._load_config()
        self._switch_tab(0)
    
    def _setup_ui(self):
        """Create all UI elements."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab bar
        self._tab_bar = self._create_tab_bar()
        layout.addWidget(self._tab_bar)
        
        # Description
        self._desc_label = QLabel(TAB_DESCRIPTIONS[0])
        self._desc_label.setObjectName("descLabel")
        self._desc_label.setWordWrap(True)
        self._desc_label.setFixedHeight(50)
        self._desc_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 11px;
                padding: 10px 20px;
                background: rgba(0, 0, 0, 0.3);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        layout.addWidget(self._desc_label)
        
        # Header row (Select all + column labels)
        header = self._create_header()
        layout.addWidget(header)
        
        # Content stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("contentStack")
        
        # Create pages
        self._stack.addWidget(self._create_essential_page())
        self._stack.addWidget(self._create_processes_page())
        self._stack.addWidget(self._create_basic_services_page())
        self._stack.addWidget(self._create_advanced_services_page())
        
        layout.addWidget(self._stack, 1)
        
        # Bottom buttons
        bottom = self._create_bottom_bar()
        layout.addWidget(bottom)
        
        # Apply dialog styling
        self.setStyleSheet("""
            QDialog#RamCleanerPresetDialog {
                background: #121212;
                border: 1px solid #333;
            }
        """)
    
    def _create_tab_bar(self) -> QWidget:
        """Create the 4-tab navigation bar."""
        container = QWidget()
        container.setObjectName("tabBarContainer")
        container.setFixedHeight(50)
        container.setStyleSheet("""
            QWidget#tabBarContainer {
                background: #1a1a1a;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(5)
        
        icons = ["", "", "", ""]
        self._tab_buttons: List[TabButton] = []
        
        for i, icon in enumerate(icons):
            btn = TabButton(icon, i)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            layout.addWidget(btn)
        
        layout.addStretch()
        return container
    
    def _create_header(self) -> QWidget:
        """Create header with Select All and column labels."""
        container = QWidget()
        container.setObjectName("headerContainer")
        container.setFixedHeight(40)
        container.setStyleSheet("""
            QWidget#headerContainer {
                background: rgba(30, 30, 30, 0.8);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(12)
        
        # Select all checkbox
        self._select_all = QCheckBox("Select all")
        self._select_all.setStyleSheet("""
            QCheckBox {
                color: #e0e0e0;
                font-size: 12px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 2px solid #555; border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background: #FF5B06; border-color: #FF5B06;
            }
        """)
        self._select_all.toggled.connect(self._toggle_select_all)
        layout.addWidget(self._select_all)
        
        # Selection count
        self._count_label = QLabel("0 out of 0 items selected")
        self._count_label.setStyleSheet("color: #666666; font-size: 11px; background: transparent;")
        layout.addWidget(self._count_label)
        
        layout.addStretch()
        
        # Column headers (will be updated per tab)
        self._col_name = QLabel("Name")
        self._col_name.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: 600; background: transparent;")
        layout.addWidget(self._col_name)
        
        self._col_extra = QLabel("Description")
        self._col_extra.setFixedWidth(200)
        self._col_extra.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: 600; background: transparent;")
        layout.addWidget(self._col_extra)
        
        return container
    
    def _create_scroll_area(self) -> QScrollArea:
        """Create a styled scroll area."""
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #FF5B06;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        return scroll
    
    def _create_essential_page(self) -> QWidget:
        """Create Tab 1 - Essential Optimizations page."""
        scroll = self._create_scroll_area()
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        for item in ESSENTIAL_OPTIMIZATIONS:
            row = OptimizationRow(item)
            row.toggled.connect(self._on_item_toggled)
            self._optimization_rows.append(row)
            layout.addWidget(row)
        
        layout.addStretch()
        scroll.setWidget(container)
        return scroll
    
    def _create_processes_page(self) -> QWidget:
        """Create Tab 2 - Background Processes page."""
        scroll = self._create_scroll_area()
        
        self._processes_container = QWidget()
        self._processes_container.setStyleSheet("background: transparent;")
        self._processes_layout = QVBoxLayout(self._processes_container)
        self._processes_layout.setContentsMargins(0, 0, 0, 0)
        self._processes_layout.setSpacing(0)
        
        # Load processes
        self._refresh_processes()
        
        scroll.setWidget(self._processes_container)
        return scroll
    
    def _create_basic_services_page(self) -> QWidget:
        """Create Tab 3 - Basic Services page."""
        scroll = self._create_scroll_area()
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        for svc in BASIC_SERVICES:
            status = get_service_status(svc["name"])
            row = ServiceRow(svc, status)
            row.toggled.connect(self._on_item_toggled)
            self._basic_service_rows.append(row)
            layout.addWidget(row)
        
        layout.addStretch()
        scroll.setWidget(container)
        return scroll
    
    def _create_advanced_services_page(self) -> QWidget:
        """Create Tab 4 - Advanced Services page."""
        scroll = self._create_scroll_area()
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        for svc in ADVANCED_SERVICES:
            status = get_service_status(svc["name"])
            row = ServiceRow(svc, status)
            row.toggled.connect(self._on_item_toggled)
            self._advanced_service_rows.append(row)
            layout.addWidget(row)
        
        layout.addStretch()
        scroll.setWidget(container)
        return scroll
    
    def _create_bottom_bar(self) -> QWidget:
        """Create bottom bar with Refresh and Reset buttons."""
        container = QWidget()
        container.setObjectName("bottomBar")
        container.setFixedHeight(60)
        container.setStyleSheet("""
            QWidget#bottomBar {
                background: #1a1a1a;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(15)
        
        # Refresh button
        self._refresh_btn = QPushButton("REFRESH")
        self._refresh_btn.setObjectName("refreshBtn")
        self._refresh_btn.setFixedSize(100, 35)
        self._refresh_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._refresh_btn.clicked.connect(self._refresh_current_tab)
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
            }
        """)
        layout.addWidget(self._refresh_btn)
        
        layout.addStretch()
        
        # Reset button
        self._reset_btn = QPushButton("RESET TO DEFAULT")
        self._reset_btn.setObjectName("resetBtn")
        self._reset_btn.setFixedSize(140, 35)
        self._reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._reset_btn.clicked.connect(self._reset_to_default)
        self._reset_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        layout.addWidget(self._reset_btn)
        
        return container
    
    def _switch_tab(self, index: int):
        """Switch to specified tab and update UI."""
        self._current_tab = index
        self._stack.setCurrentIndex(index)
        self._desc_label.setText(TAB_DESCRIPTIONS[index])
        
        # Update tab buttons
        for i, btn in enumerate(self._tab_buttons):
            btn.set_active(i == index)
        
        # Update column headers based on tab
        if index == 0:  # Essential
            self._col_name.setText("Name")
            self._col_extra.setText("Description")
            self._col_extra.setFixedWidth(300)
        elif index == 1:  # Processes
            self._col_name.setText("Name")
            self._col_extra.setText("Memory Usage ▼")
            self._col_extra.setFixedWidth(100)
        else:  # Services
            self._col_name.setText("Name")
            self._col_extra.setText("Status")
            self._col_extra.setFixedWidth(80)
        
        self._update_counts()
    
    def _update_counts(self):
        """Update all tab buttons with current selection counts."""
        # Tab 0 - Essential
        selected_0 = sum(1 for r in self._optimization_rows if r.is_checked())
        total_0 = len(self._optimization_rows)
        self._tab_buttons[0].set_count(selected_0, total_0)
        
        # Tab 1 - Processes
        selected_1 = sum(1 for r in self._process_rows if r.is_checked())
        total_1 = len(self._process_rows)
        self._tab_buttons[1].set_count(selected_1, total_1)
        
        # Tab 2 - Basic Services
        selected_2 = sum(1 for r in self._basic_service_rows if r.is_checked())
        total_2 = len(self._basic_service_rows)
        self._tab_buttons[2].set_count(selected_2, total_2)
        
        # Tab 3 - Advanced Services
        selected_3 = sum(1 for r in self._advanced_service_rows if r.is_checked())
        total_3 = len(self._advanced_service_rows)
        self._tab_buttons[3].set_count(selected_3, total_3)
        
        # Update header count label for current tab
        if self._current_tab == 0:
            self._count_label.setText(f"{selected_0} out of {total_0} items selected")
        elif self._current_tab == 1:
            self._count_label.setText(f"{selected_1} out of {total_1} items selected")
        elif self._current_tab == 2:
            self._count_label.setText(f"{selected_2} out of {total_2} items selected")
        else:
            self._count_label.setText(f"{selected_3} out of {total_3} items selected")
    
    def _on_item_toggled(self, *args):
        """Handle item checkbox toggle."""
        self._update_counts()
    
    def _toggle_select_all(self, checked: bool):
        """Handle Select All checkbox toggle."""
        if self._current_tab == 0:
            for row in self._optimization_rows:
                row.set_checked(checked)
        elif self._current_tab == 1:
            for row in self._process_rows:
                row.set_checked(checked)
        elif self._current_tab == 2:
            for row in self._basic_service_rows:
                row.set_checked(checked)
        else:
            for row in self._advanced_service_rows:
                row.set_checked(checked)
        
        self._update_counts()
    
    def _refresh_processes(self):
        """Refresh the running processes list."""
        # Clear existing rows
        for row in self._process_rows:
            row.deleteLater()
        self._process_rows.clear()
        
        # Get running processes sorted by memory
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'exe']):
            try:
                info = proc.info
                memory_mb = info['memory_info'].rss / (1024 * 1024) if info['memory_info'] else 0
                if memory_mb > 50:  # Only show processes using > 50MB
                    processes.append(ProcessItem(
                        pid=info['pid'],
                        name=info['name'] or "Unknown",
                        exe_path=info['exe'] or "",
                        memory_mb=memory_mb
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by memory descending
        processes.sort(key=lambda p: p.memory_mb, reverse=True)
        
        # Create rows
        for proc in processes[:50]:  # Limit to top 50
            row = ProcessRow(proc)
            row.toggled.connect(self._on_item_toggled)
            self._process_rows.append(row)
            self._processes_layout.addWidget(row)
        
        self._processes_layout.addStretch()
        self._update_counts()
    
    def _refresh_current_tab(self):
        """Refresh content of current tab."""
        if self._current_tab == 1:
            self._refresh_processes()
        # Services don't need refresh as status is queried on load
    
    def _reset_to_default(self):
        """Reset all selections to default values."""
        # Uncheck all
        for row in self._optimization_rows:
            row.set_checked(False)
        for row in self._process_rows:
            row.set_checked(False)
        for row in self._basic_service_rows:
            row.set_checked(False)
        for row in self._advanced_service_rows:
            row.set_checked(False)
        
        # Set defaults for essential (common safe options)
        default_essential = ["clear_clipboard", "clear_standby_list", "flush_dns"]
        for row in self._optimization_rows:
            if row.item_id in default_essential:
                row.set_checked(True)
        
        self._update_counts()
    
    def _load_config(self):
        """Load configuration from stored settings."""
        if not self._config:
            self._reset_to_default()
            return
        
        preset = self._config.get("ram_cleaner_preset", {})
        
        # Essential
        essential = preset.get("essential", {})
        for row in self._optimization_rows:
            row.set_checked(essential.get(row.item_id, False))
        
        # Processes (by name)
        saved_processes = preset.get("processes", [])
        for row in self._process_rows:
            # Can't restore by name reliably, skip for now
            pass
        
        # Basic services
        saved_basic = preset.get("basic_services", [])
        for row in self._basic_service_rows:
            row.set_checked(row.service_name in saved_basic)
        
        # Advanced services
        saved_advanced = preset.get("advanced_services", [])
        for row in self._advanced_service_rows:
            row.set_checked(row.service_name in saved_advanced)
        
        self._update_counts()
    
    def get_config(self) -> dict:
        """Get current configuration as dictionary."""
        return {
            "ram_cleaner_preset": {
                "essential": {
                    row.item_id: row.is_checked() 
                    for row in self._optimization_rows
                },
                "processes": [
                    # Store process names for selected
                ],
                "basic_services": [
                    row.service_name 
                    for row in self._basic_service_rows 
                    if row.is_checked()
                ],
                "advanced_services": [
                    row.service_name 
                    for row in self._advanced_service_rows 
                    if row.is_checked()
                ]
            }
        }


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    dialog = RamCleanerPresetDialog()
    dialog.show()
    
    sys.exit(app.exec())
