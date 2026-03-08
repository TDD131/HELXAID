"""
Hardware Panel Widget - System Monitoring Dashboard

Features:
- RAM Cleaner with circular gauge
- CPU/RAM/Disk/Network monitoring charts
- Hardware Health (temps)
- Customizable update interval (100-1000ms)

Component Name: HardwarePanelWidget
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QGridLayout, QSlider, QSpinBox,
    QScrollArea, QSizePolicy, QGraphicsDropShadowEffect, QProgressBar,
    QCheckBox
)
from smooth_scroll import SmoothScrollArea, SmoothTableWidget
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QConicalGradient

import pyqtgraph as pg
from hardware_wrapper import get_monitor, HardwareMonitor

import os
import io

# Try to import icoextract for exe icon extraction
try:
    from icoextract import IconExtractor
    ICOEXTRACT_AVAILABLE = True
except ImportError:
    ICOEXTRACT_AVAILABLE = False
    print("[Hardware] icoextract not available, using default icons")


# ============================================
# CUSTOM WIDGETS
# ============================================

class CircularGauge(QWidget):
    """
    Circular gauge widget for displaying percentage values.
    
    Component Name: CircularGauge
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CircularGauge")
        self._value = 0
        self._max_value = 100
        self._title = ""
        self._subtitle = ""
        self._accent_color = QColor("#FF5B06")
        self._bg_color = QColor("#2a2a2a")
        self.setMinimumSize(200, 200)
    
    def setValue(self, value: float):
        self._value = max(0, min(self._max_value, value))
        self.update()
    
    def setTitle(self, title: str):
        self._title = title
        self.update()
    
    def setSubtitle(self, subtitle: str):
        self._subtitle = subtitle
        self.update()
    
    def setAccentColor(self, color: QColor):
        self._accent_color = color
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate dimensions
        size = min(self.width(), self.height())
        margin = 15
        arc_width = 12
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = (size - margin * 2) / 2
        
        # Background arc
        bg_pen = QPen(self._bg_color, arc_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(bg_pen)
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        # Center the rect
        rect.moveCenter(self.rect().center())
        painter.drawArc(rect, 225 * 16, -270 * 16)
        
        # Value arc with gradient
        if self._value > 0:
            sweep = int(-270 * (self._value / self._max_value) * 16)
            
            # Create gradient for arc
            gradient_pen = QPen(self._accent_color, arc_width, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(gradient_pen)
            painter.drawArc(rect, 225 * 16, sweep)
        
        # Center text - percentage
        painter.setPen(QColor("#ffffff"))
        percent_font = QFont("Segoe UI", int(size * 0.18), QFont.Bold)
        painter.setFont(percent_font)
        percent_text = f"{int(self._value)}%"
        painter.drawText(self.rect(), Qt.AlignCenter, percent_text)
        
        # Subtitle below percentage
        if self._subtitle:
            painter.setPen(QColor("#888888"))
            sub_font = QFont("Segoe UI", int(size * 0.05))
            painter.setFont(sub_font)
            sub_rect = self.rect()
            sub_rect.moveTop(int(size * 0.15))
            painter.drawText(sub_rect, Qt.AlignCenter, self._subtitle)
        
        painter.end()


class StatsCard(QFrame):
    """
    Card widget for displaying stats with optional chart.
    
    Component Name: StatsCard
    """
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        self._title = title
        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        # Title
        self.title_label = QLabel(self._title)
        self.title_label.setObjectName("statsCardTitle")
        self.title_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: 600; background: transparent;")
        layout.addWidget(self.title_label)
        
        # Content area (for chart or stats)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("statsCardContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content_widget, stretch=1)
    
    def _apply_style(self):
        # Apply style without objectName dependency - use direct property
        self.setProperty("class", "statsCard")
        self.setStyleSheet("""
            QFrame {
                background: rgba(28, 28, 32, 0.95);
                border: none;
                border-radius: 12px;
            }
        """)
    
    def addWidget(self, widget):
        self.content_layout.addWidget(widget)


class ProgressBarWidget(QWidget):
    """
    Custom styled progress bar with left percent and right info text.
    
    Component Name: ProgressBarWidget
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProgressBarWidget")
        self._value = 0
        self._max_value = 100
        self._label = ""
        self._right_label = ""  # For GB info on right side
        self._show_percent = True
        self.setFixedHeight(24)
    
    def setValue(self, value: float):
        self._value = max(0, min(self._max_value, value))
        self.update()
    
    def setLabel(self, label: str):
        self._label = label
        self.update()
    
    def setRightLabel(self, label: str):
        """Set text to display on the right side (e.g., '150 GB / 500 GB')."""
        self._right_label = label
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        bg_rect = self.rect()
        painter.setBrush(QColor("#2a2a2a"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 6, 6)
        
        # Progress bar
        if self._value > 0:
            progress_width = int((self._value / self._max_value) * self.width())
            progress_rect = bg_rect.adjusted(0, 0, -(self.width() - progress_width), 0)
            
            # Gradient fill
            gradient = QLinearGradient(0, 0, progress_width, 0)
            gradient.setColorAt(0, QColor("#FF5B06"))
            gradient.setColorAt(1, QColor("#FDA903"))
            painter.setBrush(gradient)
            painter.drawRoundedRect(progress_rect, 6, 6)
        
        # Text overlay - left side (drive letter + percent)
        painter.setPen(QColor("#ffffff"))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        
        left_text = self._label
        if self._show_percent:
            left_text = f"{left_text}  {int(self._value)}%" if left_text else f"{int(self._value)}%"
        
        painter.drawText(self.rect().adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, left_text)
        
        # Right side text (GB info)
        if self._right_label:
            painter.setPen(QColor("#cccccc"))
            painter.drawText(self.rect().adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignRight, self._right_label)
        
        painter.end()


# ============================================
# MAIN HARDWARE PANEL
# ============================================

class HardwarePanelWidget(QWidget):
    """
    Main Hardware Panel with Overview and sub-pages.
    
    Component Name: HardwarePanelWidget
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HardwarePanelWidget")
        
        # Initialize hardware monitor
        self.monitor = get_monitor(500)  # 500ms default
        
        # Update timer
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_stats)
        
        # History for charts (growing arrays, not fixed length)
        self._cpu_history = []
        self._ram_history = []
        self._disk_usage_history = []
        self._chart_display_length = 60  # Show last 60 points
        self._hwmon_check_counter = 0  # Counter for throttled hwmon status check
        
        # Auto-scroll control per chart - pauses when user manually scrolls, resumes when head is visible
        self._chart_auto_scroll = {
            'cpu': True,
            'ram': True,
            'disk': True
        }
        
        # Disk usage tracking for clickable bars
        self._active_drives = {}  # drive letter -> active state (True/False)
        self._drive_history = {}  # drive letter -> usage history list
        self._drive_curves = {}   # drive letter -> plot curve
        self._drive_colors = ['#ff6b35', '#22d3ee', '#a78bfa', '#fbbf24', '#4ade80']  # Colors for drives
        self._drive_color_map = {}  # drive letter -> fixed color
        self._disk_details = {}  # Cache for disk model/type info (fetched once)
        self._disk_details_fetched = False
        
        self._setup_ui()
        self._apply_style()
        
        # Start updates when visible
        self._update_timer.start(self.monitor.update_interval_ms)
        
        print("[Hardware] HardwarePanelWidget initialized")
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header with settings
        header = self._create_header()
        layout.addWidget(header)
        
        # Navigation bar with tabs
        navbar = self._create_navbar()
        layout.addWidget(navbar)
        
        # Stacked widget for different pages
        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("hardwarePageStack")
        
        # Track which pages have been created (for lazy loading)
        self._pages_created = [False] * 6
        
        # Create ONLY the first page (Quick Setup) immediately - others are lazy loaded
        quick_setup_page = self._create_overview_page()
        self._page_stack.addWidget(quick_setup_page)  # Index 0
        self._pages_created[0] = True
        
        # Add placeholder widgets for other pages (will be replaced on first visit)
        for i in range(1, 6):
            placeholder = QWidget()
            placeholder.setObjectName(f"placeholder_{i}")
            self._page_stack.addWidget(placeholder)
        
        layout.addWidget(self._page_stack, stretch=1)
    
    def _create_navbar(self):
        """Create navigation bar with tab buttons."""
        navbar = QWidget()
        navbar.setObjectName("hardwareNavbar")
        navbar.setFixedHeight(40)
        navbar_layout = QHBoxLayout(navbar)
        navbar_layout.setContentsMargins(0, 0, 0, 0)
        navbar_layout.setSpacing(4)
        
        # Tab buttons
        tab_names = ["Quick Setup", "Booster", "CPU", "Drive", "Health", "Fan"]
        self._nav_buttons = []
        
        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setObjectName(f"navBtn_{name.replace(' ', '')}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(i == 0)  # First tab active by default
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #888888;
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    color: #e0e0e0;
                    background: rgba(255, 91, 6, 0.1);
                }
                QPushButton:checked {
                    color: #FF5B06;
                    border-bottom: 2px solid #FF5B06;
                }
            """)
            self._nav_buttons.append(btn)
            navbar_layout.addWidget(btn)
        
        navbar_layout.addStretch()
        
        return navbar
    
    def _switch_page(self, index: int):
        """Switch to a different page in the stack, lazy-loading if needed."""
        # Lazy load page if not yet created
        if not self._pages_created[index]:
            self._create_page_lazy(index)
        
        self._page_stack.setCurrentIndex(index)
        
        # Update button states
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        
        # Reset chart histories when switching pages
        self._reset_chart_histories()
    
    def _create_page_lazy(self, index: int):
        """Create a page on-demand (lazy loading)."""
        page_creators = {
            1: self._create_ram_page,      # Booster
            2: self._create_cpu_page,      # CPU
            3: self._create_drive_page,    # Drive
            4: self._create_health_page,   # Health
            5: self._create_fan_page,      # Fan
        }
        
        if index in page_creators:
            # Create the actual page
            new_page = page_creators[index]()
            
            # Replace the placeholder widget
            old_widget = self._page_stack.widget(index)
            self._page_stack.removeWidget(old_widget)
            old_widget.deleteLater()
            
            # Insert at correct position
            self._page_stack.insertWidget(index, new_page)
            self._pages_created[index] = True
            print(f"[Hardware] Lazy loaded page {index}")
    
    def _reset_chart_histories(self):
        """Reset all chart histories (called on page change)."""
        self._cpu_history = []
        self._ram_history = []
        self._disk_usage_history = []
        self._drive_history = {}
        # Reset all chart auto-scroll on page change
        self._chart_auto_scroll = {'cpu': True, 'ram': True, 'disk': True}
    
    def _get_chart_key(self, chart) -> str:
        """Get the key for a specific chart."""
        if chart == self.ram_chart:
            return 'ram'
        elif chart == self.cpu_chart:
            return 'cpu'
        elif chart == self.disk_chart:
            return 'disk'
        return ''
    
    def _pause_auto_scroll_for_chart(self, chart):
        """Pause auto-scroll for a specific chart when user drags it."""
        key = self._get_chart_key(chart)
        if key:
            self._chart_auto_scroll[key] = False
    
    def _check_auto_scroll_from_view(self, chart, history_len: int):
        """Check if user has scrolled to view the head (latest data). If so, resume auto-scroll for that chart."""
        if history_len == 0:
            return
        key = self._get_chart_key(chart)
        if not key:
            return
        # Get current X-axis view range
        view_range = chart.viewRange()
        _, x_max_view = view_range[0]
        # Head is at index (history_len - 1)
        # If the view includes the head position, resume auto-scroll for this chart
        head_pos = history_len - 1
        if x_max_view >= head_pos:
            self._chart_auto_scroll[key] = True
    
    def _get_chart_history_len(self, chart) -> int:
        """Get the history length for a specific chart."""
        if chart == self.ram_chart:
            return len(self._ram_history)
        elif chart == self.cpu_chart:
            return len(self._cpu_history)
        elif chart == self.disk_chart:
            return len(self._disk_usage_history)
        return 0
    
    def _create_ram_page(self):
        """Create RAM detailed page with cleaner UI."""
        page = QWidget()
        page.setObjectName("ramPage")
        main_layout = QHBoxLayout(page)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(20)
        
        # ====== Left Side: Gauge + Controls ======
        left_panel = QWidget()
        left_panel.setObjectName("ramLeftPanel")
        left_panel.setFixedWidth(220)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Title
        booster_title = QLabel("BOOSTER")
        booster_title.setObjectName("boosterTitle")
        booster_title.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: 700; background: transparent;")
        booster_title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(booster_title)
        
        # Circular Gauge
        self.ram_gauge = CircularGauge()
        self.ram_gauge.setObjectName("ramGauge")
        self.ram_gauge.setFixedSize(180, 180)
        self.ram_gauge.setValue(0)
        left_layout.addWidget(self.ram_gauge, alignment=Qt.AlignCenter)
        
        # Items to optimize label
        self.items_label = QLabel("0 items to be optimized")
        self.items_label.setObjectName("itemsLabel")
        self.items_label.setStyleSheet("color: #e0e0e0; font-size: 14px; background: transparent;")
        self.items_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.items_label)
        
        # Custom toggle button (toggle on/off for custom mode)
        self.custom_mode_btn_ram = QPushButton("Save Custom Preset")
        self.custom_mode_btn_ram.setObjectName("ramCustomBtn")
        self.custom_mode_btn_ram.setFixedSize(200, 35)
        self.custom_mode_btn_ram.setCursor(Qt.PointingHandCursor)
        self.custom_mode_btn_ram.setToolTip("Save current settings as a custom preset")
        self.custom_mode_btn_ram.clicked.connect(self._save_custom_preset)
        self.custom_mode_btn_ram.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        left_layout.addWidget(self.custom_mode_btn_ram, alignment=Qt.AlignCenter)
        
        # Manual Boost button
        self.manual_boost_btn = QPushButton("MANUAL BOOST")
        self.manual_boost_btn.setObjectName("manualBoostBtn")
        self.manual_boost_btn.setFixedHeight(40)
        self.manual_boost_btn.setCursor(Qt.PointingHandCursor)
        self.manual_boost_btn.clicked.connect(self._run_manual_boost)
        self.manual_boost_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        left_layout.addWidget(self.manual_boost_btn)
        
        left_layout.addSpacing(10)
        
        # Memory Usage section
        mem_label = QLabel("Memory Usage:")
        mem_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        left_layout.addWidget(mem_label)
        
        # Memory bar
        self.ram_usage_bar = ProgressBarWidget()
        self.ram_usage_bar.setObjectName("ramUsageBar")
        self.ram_usage_bar.setFixedHeight(20)
        left_layout.addWidget(self.ram_usage_bar)
        
        # Memory stats
        self.ram_stats_label = QLabel("Total: 0 GB\nUsed: 0 GB\nFree: 0 GB")
        self.ram_stats_label.setObjectName("ramStatsLabel")
        self.ram_stats_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        left_layout.addWidget(self.ram_stats_label)
        
        left_layout.addStretch()
        
        # Notification checkboxes
        self.notify_boost_cb = QCheckBox("Notify me when boosting")
        self.notify_boost_cb.setObjectName("notifyBoostCb")
        self.notify_boost_cb.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        self.notify_boost_cb.setChecked(True)  # Default: ON
        self.notify_boost_cb.toggled.connect(self._save_booster_settings)
        left_layout.addWidget(self.notify_boost_cb)
        
        self.auto_update_cb = QCheckBox("Auto update Boost settings\non profile change when\nBoost is active")
        self.auto_update_cb.setObjectName("autoUpdateCb")
        self.auto_update_cb.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        left_layout.addWidget(self.auto_update_cb)
        
        main_layout.addWidget(left_panel)
        
        # ====== Right Side: Embedded 4-Tab Content ======
        right_panel = QWidget()
        right_panel.setObjectName("ramRightPanel")
        right_panel.setStyleSheet("""
            QWidget#ramRightPanel {
                background: rgba(30, 30, 30, 0.5);
                border-radius: 8px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Tab bar
        tab_bar = QWidget()
        tab_bar.setObjectName("ramTabBar")
        tab_bar.setFixedHeight(45)
        tab_bar.setStyleSheet("""
            QWidget#ramTabBar {
                background: rgba(20, 20, 20, 0.8);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(10, 0, 10, 0)
        tab_bar_layout.setSpacing(5)
        
        # Create tab buttons
        tab_icons = ["Essential", "Processes", "Basic", "Advanced"]
        tab_names = ["Essential", "Processes", "Basic", "Advanced"]
        self._ram_tab_btns = []
        
        for i, (icon, name) in enumerate(zip(tab_icons, tab_names)):
            btn = QPushButton(f"{icon}")
            btn.setObjectName(f"ramTabBtn_{i}")
            btn.setFixedHeight(35)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            btn.setProperty("tab_index", i)
            btn.clicked.connect(lambda checked, idx=i: self._switch_ram_tab(idx))
            self._ram_tab_btns.append(btn)
            tab_bar_layout.addWidget(btn)
        
        tab_bar_layout.addStretch()
        
        right_layout.addWidget(tab_bar)
        
        # Description label
        self._ram_tab_desc = QLabel("Essential items for CPU and memory optimization.")
        self._ram_tab_desc.setObjectName("ramTabDesc")
        self._ram_tab_desc.setFixedHeight(35)
        self._ram_tab_desc.setWordWrap(True)
        self._ram_tab_desc.setStyleSheet("""
            QLabel { 
                color: #888888; 
                font-size: 10px; 
                padding: 8px 15px;
                background: rgba(0, 0, 0, 0.3);
            }
        """)
        right_layout.addWidget(self._ram_tab_desc)
        
        # Content stack
        self._ram_tab_stack = QStackedWidget()
        self._ram_tab_stack.setObjectName("ramTabStack")
        
        # Add 4 tab pages
        self._ram_tab_stack.addWidget(self._create_essential_tab())
        self._ram_tab_stack.addWidget(self._create_processes_tab())
        self._ram_tab_stack.addWidget(self._create_basic_services_tab())
        self._ram_tab_stack.addWidget(self._create_advanced_services_tab())
        
        right_layout.addWidget(self._ram_tab_stack, stretch=1)
        
        self._current_ram_tab = 0
        self._update_ram_tab_buttons()
        
        main_layout.addWidget(right_panel, stretch=1)
        
        # Load preset settings for processes and services tabs
        self._load_custom_preset_settings()
        
        return page
    
    def _on_ram_mode_selected(self, mode_index: int):
        """Handle RAM mode button selection."""
        self._current_ram_mode = mode_index
        self._update_ram_mode_buttons()
        
        # Show/hide Custom Preset button
        if mode_index == 2:  # Custom mode
            self.custom_preset_btn.show()
        else:
            self.custom_preset_btn.hide()
    
    def _update_ram_mode_buttons(self):
        """Update mode button styles based on current selection."""
        for i, btn in enumerate(self._ram_mode_btns):
            if i == self._current_ram_mode:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                        color: #1a1a1a;
                        border: none;
                        border-radius: 6px;
                        font-size: 14px;
                        font-weight: 600;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #333;
                        color: #e0e0e0;
                        border: 1px solid #444;
                        border-radius: 6px;
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background: #444;
                        border-color: #FF5B06;
                    }
                """)
    
    def _save_custom_preset(self):
        """Save all selections across the 4 tabs into booster_settings.json."""
        import json
        import os
        from launcher import APPDATA_DIR
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
        
        # Read current settings
        settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except:
                pass
                
        # 1. Essential
        if hasattr(self, '_essential_checks'):
            selected = []
            for i, cb in enumerate(self._essential_checks):
                if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                    selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
            settings["essential_optimizations"] = selected
            
        # 2. Processes
        if hasattr(self, '_process_checks') and hasattr(self, '_process_data'):
            selected = []
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    selected.append(self._process_data[i]["name"])
            settings["processes_to_close"] = selected
            
        # 3. Basic Services
        if hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_service_data'):
            selected = []
            for i, cb in enumerate(self._basic_service_checks):
                if cb.isChecked() and i < len(self._basic_service_data):
                    selected.append(self._basic_service_data[i]["name"])
            settings["basic_services_to_stop"] = selected
            
        # 4. Advanced Services
        if hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_service_data'):
            selected = []
            for i, cb in enumerate(self._advanced_service_checks):
                if cb.isChecked() and i < len(self._advanced_service_data):
                    selected.append(self._advanced_service_data[i]["name"])
            settings["advanced_services_to_stop"] = selected
            
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            print(f"[Booster] Custom preset saved successfully.")
            
            # Show notification
            if hasattr(self.window(), 'tray_icon') and self.window().tray_icon:
                self.window().tray_icon.showMessage(
                    "HELXAID Booster",
                    "Custom boost preset has been saved successfully.",
                    self.window().windowIcon(),
                    3000
                )
        except Exception as e:
            print(f"[Booster] Error saving custom preset: {e}")

    def _load_custom_preset_settings(self):
        """Load processes and services checked states from booster_settings.json."""
        import json
        import os
        from launcher import APPDATA_DIR
        
        settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
        if not os.path.exists(settings_path):
            return
            
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
            # Note: Essential tab already loads its own state via _load_essential_states
            
            # 2. Processes (Since processes are loaded dynamically, we just set the tracking set.
            #   _populate_processes_tab will read from it when it builds the list.)
            if "processes_to_close" in settings:
                if not hasattr(self, '_checked_process_names') or not self._checked_process_names:
                    self._checked_process_names = set(settings["processes_to_close"])
                
            # 3. Basic Services
            if "basic_services_to_stop" in settings and hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_service_data'):
                saved_basic = set(settings["basic_services_to_stop"])
                for i, cb in enumerate(self._basic_service_checks):
                    if i < len(self._basic_service_data):
                        svc_name = self._basic_service_data[i]["name"]
                        cb.blockSignals(True)
                        cb.setChecked(svc_name in saved_basic)
                        cb.blockSignals(False)
                if hasattr(self, '_update_basic_count'):
                    self._update_basic_count()
                        
            # 4. Advanced Services
            if "advanced_services_to_stop" in settings and hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_service_data'):
                saved_adv = set(settings["advanced_services_to_stop"])
                for i, cb in enumerate(self._advanced_service_checks):
                    if i < len(self._advanced_service_data):
                        svc_name = self._advanced_service_data[i]["name"]
                        cb.blockSignals(True)
                        cb.setChecked(svc_name in saved_adv)
                        cb.blockSignals(False)
                if hasattr(self, '_update_advanced_count'):
                    self._update_advanced_count()
                        
        except Exception as e:
            print(f"[Booster] Error loading custom preset settings: {e}")
    
    def _run_manual_boost(self):
        """Run manual boost applying optimizations from ALL 4 tabs in background thread.
        
        Boost re-applies every 60 seconds until user clicks Stop Boost.
        This ensures optimizations persist (e.g. Windows key stays disabled
        even if the OS re-enables it).
        """
        # If already boosting, stop it
        if getattr(self, '_is_boosting', False):
            print("[Boost] Stop requested by user")
            self._boost_cancel_requested = True
            self.manual_boost_btn.setText("STOPPING...")
            if hasattr(self, 'clean_btn'):
                self.clean_btn.setText("STOPPING...")
            
            # Stop the reapply timer immediately
            if hasattr(self, '_boost_reapply_timer') and self._boost_reapply_timer is not None:
                self._boost_reapply_timer.stop()
            
            # Force reset after 3 seconds if thread doesn't respond
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, self._force_boost_reset)
            return
        
        print("[Boost] Manual boost triggered - starting background thread")
        
        # Set boosting state
        self._is_boosting = True
        self._boost_cancel_requested = False
        self._boost_cycle_count = 0
        
        # Change button to STOP mode with animated gradient
        self.manual_boost_btn.setText("STOP BOOST")
        if hasattr(self, 'clean_btn'):
            self.clean_btn.setText("STOP BOOST")
            self.clean_btn.setStyleSheet("""
                QPushButton#cleanRamButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E53935, stop:1 #B71C1C);
                    color: #ffffff;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton#cleanRamButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EF5350, stop:1 #C62828);
                }
            """)
        
        # Start animated gradient for STOP button (same as nav buttons)
        self._boost_btn_gradient_offset = 0.0
        
        # Create timer for gradient animation
        if not hasattr(self, '_boost_gradient_timer') or self._boost_gradient_timer is None:
            from PySide6.QtCore import QTimer
            self._boost_gradient_timer = QTimer(self)
            self._boost_gradient_timer.timeout.connect(self._update_boost_btn_gradient)
        self._boost_gradient_timer.start(17)  # 17ms = ~60fps
        
        # Apply initial gradient
        self._update_boost_btn_gradient()
        
        # Show overlay on tab content
        self._show_boost_overlay(True)
        
        # Create reapply timer (fires every 60 seconds to re-apply boost)
        if not hasattr(self, '_boost_reapply_timer') or self._boost_reapply_timer is None:
            from PySide6.QtCore import QTimer
            self._boost_reapply_timer = QTimer(self)
            self._boost_reapply_timer.timeout.connect(self._reapply_boost)
        
        # Run first boost immediately
        self._execute_boost_cycle()
        
        # Start the 60-second reapply timer
        self._boost_reapply_timer.start(60000)  # 60 seconds
        print("[Boost] Reapply timer started (60s interval)")
    
    def _reapply_boost(self):
        """Called every 60 seconds by the reapply timer to re-apply boost.
        
        Re-collects current checkbox state from all 4 tabs so that
        any changes the user makes mid-boost are picked up on the
        next cycle.
        """
        if not getattr(self, '_is_boosting', False):
            return
        if getattr(self, '_boost_cancel_requested', False):
            return
        
        # Don't start a new cycle if the previous one is still running
        if hasattr(self, '_boost_thread') and self._boost_thread is not None and self._boost_thread.is_alive():
            print("[Boost] Previous cycle still running, skipping this reapply")
            return
        
        print("[Boost] Reapply timer fired - re-applying boost")
        self._execute_boost_cycle()
    
    def _execute_boost_cycle(self):
        """Collect UI state and run one boost cycle in a background thread."""
        self._boost_cycle_count = getattr(self, '_boost_cycle_count', 0) + 1
        print(f"[Boost] Starting cycle #{self._boost_cycle_count}")
        
        # Collect data from UI before starting thread (must be done in main thread)
        boost_data = {
            'selected_essential': self._get_selected_optimizations() if hasattr(self, '_get_selected_optimizations') else [],
            'process_data': [],
            'basic_service_data': [],
            'advanced_service_data': []
        }
        
        # Collect checked processes (skip blacklisted)
        if hasattr(self, '_process_checks') and hasattr(self, '_process_data'):
            blacklist = getattr(self, '_process_blacklist', set())
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    proc_name = self._process_data[i]['name']
                    if proc_name not in blacklist:
                        boost_data['process_data'].append(self._process_data[i])
                    else:
                        print(f"[Boost] Skipping blacklisted process: {proc_name}")
        
        # Collect checked basic services
        if hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_service_data'):
            for i, cb in enumerate(self._basic_service_checks):
                if cb.isChecked() and i < len(self._basic_service_data):
                    boost_data['basic_service_data'].append(self._basic_service_data[i])
        
        # Collect checked advanced services
        if hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_service_data'):
            for i, cb in enumerate(self._advanced_service_checks):
                if cb.isChecked() and i < len(self._advanced_service_data):
                    boost_data['advanced_service_data'].append(self._advanced_service_data[i])
        
        # Run in background thread
        import threading
        self._boost_thread = threading.Thread(target=self._run_boost_worker, args=(boost_data,), daemon=True)
        self._boost_thread.start()
    
    def _show_boost_overlay(self, show: bool):
        """Show/hide overlay on tab content to prevent interaction during boost."""
        if not hasattr(self, '_ram_tab_stack'):
            return
        
        # Parent overlay to the tab stack itself (covers content but not tab bar)
        parent_widget = self._ram_tab_stack
        
        if show:
            # Create overlay if not exists
            if not hasattr(self, '_boost_overlay') or self._boost_overlay is None:
                from PySide6.QtWidgets import QFrame
                self._boost_overlay = QFrame(parent_widget)
                self._boost_overlay.setObjectName("boostOverlay")
                self._boost_overlay.setStyleSheet("""
                    QFrame#boostOverlay {
                        background: rgba(0, 0, 0, 0.7);
                        border-radius: 8px;
                    }
                """)
                self._boost_overlay.setCursor(Qt.WaitCursor)
            else:
                # Re-parent overlay to ensure it's in the right parent
                self._boost_overlay.setParent(parent_widget)
            
            # Position overlay over the tab stack content area only
            self._boost_overlay.setGeometry(parent_widget.rect())
            self._boost_overlay.raise_()
            self._boost_overlay.show()
        else:
            # Hide overlay
            if hasattr(self, '_boost_overlay') and self._boost_overlay:
                self._boost_overlay.hide()
    
    def _force_boost_reset(self):
        """Force reset boost state if still in boosting/stopping state."""
        if getattr(self, '_is_boosting', False) or self.manual_boost_btn.text() == "STOPPING...":
            print("[Boost] Force reset after timeout")
            self._full_boost_reset()
    
    def _update_boost_btn_gradient(self):
        """Update the gradient offset for animated STOP button."""
        if not getattr(self, '_is_boosting', False):
            return
        
        # OMEN gradient colors (extended for seamless loop)
        colors = ['#ff3da7', '#ff0c2b', '#ff5700', '#ffab00', '#ff3da7']
        
        # Shift offset (0.0 to 1.0) - small step for slow, smooth animation at 60fps
        self._boost_btn_gradient_offset += 0.005
        if self._boost_btn_gradient_offset >= 1.0:
            self._boost_btn_gradient_offset = 0.0
        
        offset = self._boost_btn_gradient_offset
        
        # Build gradient with offset positions
        stops = []
        num_colors = len(colors)
        for i, color in enumerate(colors):
            base_pos = i / (num_colors - 1)
            shifted_pos = (base_pos + offset) % 1.0
            stops.append((shifted_pos, color))
        
        # Sort stops by position for valid gradient
        stops.sort(key=lambda x: x[0])
        
        # Build QSS gradient string
        gradient_stops = ', '.join([f'stop:{pos:.3f} {color}' for pos, color in stops])
        
        self.manual_boost_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient_stops});
                color: #ffffff;
                border: 2px solid rgba(255, 91, 6, 0.8);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                text-shadow: 0 0 10px #ff5500;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
        """)
    
    def _run_boost_worker(self, boost_data):
        """Worker function that runs in background thread."""
        import psutil
        import subprocess
        
        results = {
            'essential': {'success': 0, 'total': 0, 'items': []},
            'processes': {'closed': 0, 'failed': 0, 'items': []},
            'basic_services': {'stopped': 0, 'failed': 0, 'items': []},
            'advanced_services': {'stopped': 0, 'failed': 0, 'items': []}
        }
        
        any_selected = False
        cancelled = False
        
        try:
            # Check cancel before each major step
            if getattr(self, '_boost_cancel_requested', False):
                cancelled = True
                raise Exception("Cancelled by user")
            
            # ========== 1. ESSENTIAL TAB ==========
            # Track services that failed in essentials due to needing admin.
            # These will be routed through the scheduled task batch later.
            _essential_needs_elevation = []
            
            selected_essential = boost_data.get('selected_essential', [])
            if selected_essential:
                any_selected = True
                results['essential']['total'] = len(selected_essential)
                # Call essential optimizations (these are usually registry changes, fast)
                try:
                    essential_results = self._apply_essential_optimizations()
                    for name, result in essential_results.items():
                        if result.get('success', False):
                            results['essential']['success'] += 1
                            results['essential']['items'].append(f"V {name}")
                        else:
                            # Check if it failed because admin is needed (service stop)
                            err = result.get('error', '')
                            if 'admin' in str(err).lower() or 'denied' in str(err).lower():
                                # Route through scheduled task instead of marking as failed
                                if 'file_sharing' in name or 'file sharing' in name.lower():
                                    _essential_needs_elevation.append({
                                        'name': 'LanmanServer',
                                        'display': 'File and Printer Sharing',
                                        'essential_key': name
                                    })
                                    print(f"[Boost] {name} needs admin — routing via scheduled task")
                                else:
                                    results['essential']['items'].append(f"X {name}")
                            else:
                                results['essential']['items'].append(f"X {name}")
                except Exception as e:
                    print(f"[Boost] Essential error: {e}")
            
            # ========== 2. PROCESSES TAB ==========
            process_data = boost_data.get('process_data', [])
            if process_data:
                any_selected = True
                process_names = [proc_info['name'] for proc_info in process_data]
                
                import native_wrapper
                boost_engine = native_wrapper.get_boost_engine()
                
                if boost_engine:
                    kill_results = boost_engine.kill_processes(process_names)
                    for r in kill_results:
                        if r.success and r.killed_pids > 0:
                            results['processes']['closed'] += 1
                            count_str = f" ({r.killed_pids} instances)" if r.total_pids > 1 else ""
                            results['processes']['items'].append(f"✓ {r.name}{count_str}")
                            print(f"[Boost] Closed process: {r.name} ({r.killed_pids}/{r.total_pids} PIDs)")
                        else:
                            results['processes']['failed'] += 1
                            reason = "access denied" if r.total_pids > 0 else "not running"
                            results['processes']['items'].append(f"✗ {r.name} ({reason})")
                            print(f"[Boost] Failed to close {r.name}")
                else:
                    # Python fallback
                    for proc_info in process_data:
                        pids = proc_info.get('pids', [proc_info.get('pid')])
                        closed_count = 0
                        failed_count = 0
                        
                        for pid in pids:
                            try:
                                p = psutil.Process(pid)
                                p.terminate()
                                p.wait(timeout=2)
                                closed_count += 1
                            except Exception:
                                failed_count += 1
                        
                        if closed_count > 0:
                            results['processes']['closed'] += 1
                            count_str = f" ({closed_count} instances)" if len(pids) > 1 else ""
                            results['processes']['items'].append(f"✓ {proc_info['name']}{count_str}")
                            print(f"[Boost] Closed process: {proc_info['name']} ({closed_count}/{len(pids)} PIDs)")
                        else:
                            results['processes']['failed'] += 1
                            results['processes']['items'].append(f"✗ {proc_info['name']} (access denied)")
                            print(f"[Boost] Failed to close {proc_info['name']}")
            
            # ========== 3 & 4. SERVICES (BASIC + ADVANCED) — SCHEDULED TASK ==========
            all_services = []
            
            for ess_svc in _essential_needs_elevation:
                all_services.append(('essential', ess_svc))
            
            for svc in boost_data.get('basic_service_data', []):
                any_selected = True
                all_services.append(('basic', svc))
            for svc in boost_data.get('advanced_service_data', []):
                any_selected = True
                all_services.append(('advanced', svc))
            
            if all_services:
                import tempfile
                import native_wrapper
                boost_engine = native_wrapper.get_boost_engine()
                
                appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID')
                os.makedirs(appdata_dir, exist_ok=True)
                
                input_path = os.path.join(tempfile.gettempdir(), "helxaid_boost_input.txt")
                log_path = os.path.join(tempfile.gettempdir(), "helxaid_boost_svc.log")
                task_script = os.path.join(appdata_dir, "boost_services.ps1")
                task_name = "HELXAID_BoostService"
                
                if boost_engine:
                    # --- Native implementation ---
                    boost_engine.write_boost_script(task_script, input_path, log_path)
                    task_exists = boost_engine.ensure_task_exists(task_name, task_script)
                    
                    if not task_exists:
                        print("[Boost] Scheduled task creation failed/denied")
                        for cat, svc in all_services:
                            key = 'basic_services' if cat == 'basic' else 'advanced_services'
                            results[key]['failed'] += 1
                            results[key]['items'].append(f"X {svc.get('display', svc['name'])} (setup needed)")
                    else:
                        from helxaid_native import ServiceEntry
                        native_services = []
                        for cat, svc in all_services:
                            native_services.append(ServiceEntry(svc['name'], svc.get('display', svc['name']), cat))
                        
                        stop_results = boost_engine.stop_services(native_services, task_name)
                        
                        for sr in stop_results:
                            cat = sr.category
                            if cat == 'essential':
                                if sr.success:
                                    results['essential']['success'] += 1
                                    results['essential']['items'].append(f"V {sr.display_name}")
                                    print(f"[Boost] Essential service stopped: {sr.name} ({sr.status})")
                                else:
                                    results['essential']['items'].append(f"X {sr.display_name}")
                                    print(f"[Boost] Essential service failed: {sr.name}")
                            else:
                                key = 'basic_services' if cat == 'basic' else 'advanced_services'
                                if sr.success:
                                    results[key]['stopped'] += 1
                                    results[key]['items'].append(f"V {sr.display_name}")
                                    print(f"[Boost] Stopped service: {sr.name} ({sr.status})")
                                else:
                                    results[key]['failed'] += 1
                                    results[key]['items'].append(f"X {sr.display_name}")
                                    print(f"[Boost] Failed to stop {sr.name}")
                else:
                    # Native module not available
                    for cat, svc in all_services:
                        key = 'basic_services' if cat == 'basic' else 'advanced_services'
                        results[key]['failed'] += 1
                        results[key]['items'].append(f"X {svc.get('display', svc['name'])} (native module missing)")
                    print("[Boost] Native C++ module not available, services not stopped.")
            
            # ========== SHOW RESULTS ==========
            if not any_selected:
                # Schedule UI update in main thread
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._boost_complete(None, "No Items Selected", 
                    "Please select at least one item from any tab\n(Essential, Processes, Basic, or Advanced)."))
                return
            
            # Build summary message
            msg_parts = []
            
            if results['essential']['total'] > 0:
                msg_parts.append(f"🔧 Essential: {results['essential']['success']}/{results['essential']['total']}")
            
            proc_total = results['processes']['closed'] + results['processes']['failed']
            if proc_total > 0:
                msg_parts.append(f"⚡ Processes closed: {results['processes']['closed']}/{proc_total}")
            
            basic_total = results['basic_services']['stopped'] + results['basic_services']['failed']
            if basic_total > 0:
                msg_parts.append(f"📦 Basic services stopped: {results['basic_services']['stopped']}/{basic_total}")
            
            adv_total = results['advanced_services']['stopped'] + results['advanced_services']['failed']
            if adv_total > 0:
                msg_parts.append(f"⚠️ Advanced services stopped: {results['advanced_services']['stopped']}/{adv_total}")
            
            summary = "\n".join(msg_parts)
            
            # Check for any failures
            total_failed = (
                (results['essential']['total'] - results['essential']['success']) +
                results['processes']['failed'] +
                results['basic_services']['failed'] +
                results['advanced_services']['failed']
            )
            
            print(f"[Boost] Complete - {summary}")
            
            # Schedule UI update in main thread safely
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "_boost_complete_safe", Qt.QueuedConnection, 
                                     Q_ARG(object, results), Q_ARG(str, summary), 
                                     Q_ARG(object, None), Q_ARG(int, total_failed))
                
        except Exception as e:
            print(f"[Boost] Error: {e}")
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "_boost_complete_safe", Qt.QueuedConnection, 
                                     Q_ARG(object, None), Q_ARG(str, None), 
                                     Q_ARG(object, str(e)), Q_ARG(int, 0))
    
    @QtCore.Slot(object, str, object, int)
    def _boost_complete_safe(self, results, summary, error, total_failed):
        """Wrapper strictly for cross-thread calls"""
        self._boost_complete(results, summary, error, total_failed)
        
    def _boost_complete(self, results, summary, error, total_failed=0):
        """Called in main thread after a single boost cycle completes.
        
        In recurring mode (reapply timer active), this does NOT reset
        the boost state. It only logs results and sends notifications.
        Full reset only happens when user clicks Stop Boost (cancel path)
        or when an unrecoverable error occurs.
        """
        cycle = getattr(self, '_boost_cycle_count', 1)
        print(f"[Boost] Cycle #{cycle} complete - error={error}, summary={summary}")
        
        # Handle cancel / stop case: full reset
        if error and "Cancelled" in str(error):
            print("[Boost] Boost was cancelled by user")
            self._full_boost_reset()
            return
        
        # Handle "No items selected" on first cycle: full reset
        if error and summary and "No Items Selected" in str(summary):
            self._full_boost_reset()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Items Selected", error)
            return
        
        # Handle unexpected error: full reset
        if error:
            self._full_boost_reset()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Boost Error", f"An error occurred:\n{error}")
            return
        
        # -- Success path: log results, send notification, but keep boost active --
        
        # Show tray notification on the first boost cycle only (to avoid spam).
        # Uses a multi-strategy approach to find tray_icon because self.window()
        # may not directly return the GameLauncher window when nested in tab widgets.
        if cycle == 1:
            try:
                from PySide6.QtWidgets import QSystemTrayIcon, QApplication
                from PySide6.QtGui import QIcon

                tray = None

                # Strategy 1: look on the direct parent window
                main_window = self.window()
                print(f"[Boost] self.window() = {main_window.__class__.__name__}, has tray_icon = {hasattr(main_window, 'tray_icon')}")
                if hasattr(main_window, 'tray_icon') and main_window.tray_icon:
                    tray = main_window.tray_icon

                # Strategy 2: scan all top-level widgets for one that has tray_icon
                if tray is None:
                    for widget in QApplication.topLevelWidgets():
                        if hasattr(widget, 'tray_icon') and widget.tray_icon:
                            tray = widget.tray_icon
                            print(f"[Boost] Found tray_icon on {widget.__class__.__name__}")
                            break

                # Strategy 3: create a temporary QSystemTrayIcon for this notification only
                if tray is None:
                    print("[Boost] No tray_icon found on any window, creating temporary one")
                    tray = QSystemTrayIcon()
                    # Use app icon or a blank icon
                    app_icon = QApplication.windowIcon()
                    if not app_icon.isNull():
                        tray.setIcon(app_icon)
                    else:
                        tray.setIcon(QIcon())
                    tray.show()
                    _temp_tray = tray  # keep alive for duration of message
                else:
                    _temp_tray = None

                notif_msg = summary if summary else "Optimizations applied."
                if total_failed == 0:
                    tray.showMessage("Boosting...", notif_msg, tray.icon(), 5000)
                else:
                    tray.showMessage("Boosting... (warnings)", notif_msg, tray.icon(), 5000)
                print(f"[Boost] Notification sent: 'Boosting...' | {notif_msg}")

            except Exception as e:
                print(f"[Boost] Notification error: {e}")
        
        # Refresh processes list after closing some
        if results and results['processes']['closed'] > 0:
            self._populate_processes_tab()
        
        # Refresh service status labels after stopping services
        if results and (results['basic_services']['stopped'] > 0 or results['advanced_services']['stopped'] > 0):
            try:
                self._refresh_service_statuses()
            except Exception as e:
                print(f"[Boost] Service status refresh error: {e}")
        
        print(f"[Boost] Cycle #{cycle} done. Next reapply in 60s (boost stays active).")
    

    def _full_boost_reset(self):

        """Fully reset boost state: stop timers, hide overlay, reset button."""
        self._is_boosting = False
        self._boost_cancel_requested = False
        
        # Stop reapply timer
        if hasattr(self, '_boost_reapply_timer') and self._boost_reapply_timer:
            self._boost_reapply_timer.stop()
            print("[Boost] Reapply timer stopped")
        
        # Stop gradient animation timer
        if hasattr(self, '_boost_gradient_timer') and self._boost_gradient_timer:
            self._boost_gradient_timer.stop()
        
        # Hide overlay
        self._show_boost_overlay(False)
        
        # Reset button style and text
        try:
            self.manual_boost_btn.setEnabled(True)
            self.manual_boost_btn.setText("MANUAL BOOST")
            self.manual_boost_btn.setStyleSheet("""
                QPushButton {
                    background: #333;
                    color: #e0e0e0;
                    border: 1px solid #555;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #444;
                    border-color: #FF5B06;
                }
            """)
            print("[Boost] Button reset to MANUAL BOOST")
            
            if hasattr(self, 'clean_btn'):
                self.clean_btn.setText("Clean RAM")
                self.clean_btn.setStyleSheet("""
                    QPushButton#cleanRamButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                        color: #ffffff;
                        border: none;
                        border-radius: 12px;
                        font-size: 14px;
                        font-weight: 600;
                    }
                    QPushButton#cleanRamButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7B26, stop:1 #FDC933);
                    }
                    QPushButton#cleanRamButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E54B00, stop:1 #DD9903);
                    }
                """)
        except Exception as e:
            print(f"[Boost] Error resetting button: {e}")
    
    # ============================================
    # EMBEDDED RAM TAB METHODS
    # ============================================
    
    def _refresh_service_statuses(self):
        """Re-query and update service status labels in the Basic/Advanced tables.
        
        Uses `sc query` (no admin needed) to get the current state of each
        service, then updates the Status column (column 2) in the table.
        Called after a boost cycle stops services so the UI reflects reality.
        """
        from RamCleanerPresetDialog import BASIC_SERVICES, ADVANCED_SERVICES, get_service_status
        
        # Refresh basic table
        if hasattr(self, '_basic_table') and hasattr(self, '_basic_service_data'):
            for idx, svc in enumerate(self._basic_service_data):
                if idx < self._basic_table.rowCount():
                    status = get_service_status(svc['name'])
                    item = self._basic_table.item(idx, 2)
                    if item:
                        item.setText(status)
                        color = "#4ade80" if status == "Running" else "#888888"
                        item.setForeground(QColor(color))
        
        # Refresh advanced table
        if hasattr(self, '_advanced_table') and hasattr(self, '_advanced_service_data'):
            for idx, svc in enumerate(self._advanced_service_data):
                if idx < self._advanced_table.rowCount():
                    status = get_service_status(svc['name'])
                    item = self._advanced_table.item(idx, 2)
                    if item:
                        item.setText(status)
                        color = "#4ade80" if status == "Running" else "#888888"
                        item.setForeground(QColor(color))
        
        print("[Boost] Service statuses refreshed in UI")
    
    def _switch_ram_tab(self, index: int):
        """Switch to specified RAM tab."""
        self._current_ram_tab = index
        self._ram_tab_stack.setCurrentIndex(index)
        self._update_ram_tab_buttons()
        
        # Refresh overlay if boosting is active
        if getattr(self, '_is_boosting', False):
            self._show_boost_overlay(True)
        
        # Update description
        descriptions = [
            "Essential items for CPU and memory optimization.",
            "Background processes that can be closed to free RAM.",
            "Basic Windows Services that can be safely stopped.",
            "Advanced Windows Services. Use with caution."
        ]
        self._ram_tab_desc.setText(descriptions[index])
    
    def _update_ram_tab_buttons(self):
        """Update tab button styles based on current selection."""
        for i, btn in enumerate(self._ram_tab_btns):
            if i == self._current_ram_tab:
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
    
    def _refresh_ram_tab_content(self):
        """Refresh content of current RAM tab."""
        if self._current_ram_tab == 1:  # Processes tab
            self._populate_processes_tab()
        print(f"[RAM] Refreshed tab {self._current_ram_tab}")
    
    def _update_total_items_count(self):
        """Update the items_label with total selected items from ALL tabs."""
        total = 0
        
        # 1. Essential tab
        if hasattr(self, '_essential_checks'):
            total += sum(1 for cb in self._essential_checks if cb.isChecked())
        
        # 2. Processes tab
        if hasattr(self, '_process_checks'):
            total += sum(1 for cb in self._process_checks if cb.isChecked())
        
        # 3. Basic Services tab
        if hasattr(self, '_basic_service_checks'):
            total += sum(1 for cb in self._basic_service_checks if cb.isChecked())
        
        # 4. Advanced Services tab
        if hasattr(self, '_advanced_service_checks'):
            total += sum(1 for cb in self._advanced_service_checks if cb.isChecked())
        
        # Update the label
        if hasattr(self, 'items_label'):
            if total == 0:
                self.items_label.setText("0 items to be optimized")
            elif total == 1:
                self.items_label.setText("1 item to be optimized")
            else:
                self.items_label.setText(f"{total} items to be optimized")
    
    def _create_essential_tab(self) -> QWidget:
        """Create Essential Optimizations tab content matching reference design."""
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        page = QWidget()
        page.setObjectName("essentialPage")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # Header row with Select All, Name, Description columns
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName("essentialSelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet("""
            QFrame#essentialSelectRow {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        
        self._essential_select_all = QCheckBox("Select all")
        self._essential_select_all.setObjectName("essentialSelectAll")
        self._essential_select_all.setStyleSheet("""
            QCheckBox { color: #e0e0e0; font-size: 11px; background: transparent; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
            QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
        """)
        self._essential_select_all.toggled.connect(self._on_essential_select_all)
        select_layout.addWidget(self._essential_select_all)
        
        self._essential_count_label = QLabel(f"0/{len(ESSENTIAL_OPTIMIZATIONS)}")
        self._essential_count_label.setObjectName("essentialCountLabel")
        self._essential_count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        select_layout.addWidget(self._essential_count_label)
        select_layout.addStretch()
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        table = QTableWidget()
        table.setObjectName("essentialTable")
        table.setColumnCount(3)
        table.setRowCount(len(ESSENTIAL_OPTIMIZATIONS))
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "Name", "Description"])
        

        # Essential tab Column widths
        table.setColumnWidth(0, 50)   # Checkbox (#) - fixed
        table.setColumnWidth(1, 350)  # Name
        table.horizontalHeader().setStretchLastSection(True)  # Description stretches
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setMinimumSectionSize(50)
        
        # Styling
        table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::item:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QHeaderView::section {
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }
            QHeaderView::section:hover {
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 3px;
            }
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Populate table
        self._essential_checks = []
        self._essential_table = table
        
        for idx, item in enumerate(ESSENTIAL_OPTIMIZATIONS):
            # Column 0: Checkbox
            cb_widget = QWidget()
            cb_widget.setObjectName(f"essentialCheckWidget_{idx}")
            cb_widget.setStyleSheet("background: transparent;")
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            
            cb = QCheckBox()
            cb.setObjectName(f"essentialCheck_{idx}")
            cb.setStyleSheet("""
                QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
                QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
            """)
            cb.toggled.connect(self._update_essential_count)
            cb.toggled.connect(self._save_essential_states)
            cb.toggled.connect(self._update_total_items_count)
            self._essential_checks.append(cb)
            cb_layout.addWidget(cb)
            table.setCellWidget(idx, 0, cb_widget)
            
            # Column 1: Name
            name_item = QTableWidgetItem(item["name"])
            name_item.setForeground(QColor("#e0e0e0"))
            table.setItem(idx, 1, name_item)
            
            # Column 2: Description
            desc_item = QTableWidgetItem(item["description"])
            desc_item.setForeground(QColor("#666666"))
            table.setItem(idx, 2, desc_item)
        
        page_layout.addWidget(table, 1)
        
        # Enable smooth scrolling for this table
        self._essential_table_smoother = SmoothTableWidget(table)
        
        
        # Bottom bar with Reset button
        bottom = QFrame()
        bottom.setObjectName("essentialBottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet("""
            QFrame#essentialBottom {
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName("essentialResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_essential_selections)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
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
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Load saved checkbox states
        self._load_essential_states()
        self._load_booster_settings()
        
        # Update total items count in left panel
        self._update_total_items_count()
        
        return page
    
    def _on_essential_select_all(self, checked: bool):
        """Handle Select All checkbox for essential tab."""
        for cb in self._essential_checks:
            cb.setChecked(checked)
        self._update_essential_count()
    
    def _sort_essential_list(self):
        """Sort the essential optimizations list by name."""
        # Toggle sort order
        self._essential_sort_asc = not self._essential_sort_asc
        
        # Update header text
        arrow = "▲" if self._essential_sort_asc else "▼"
        self._essential_name_header.setText(f"Name {arrow}")
        
        # Get container layout
        container = self._essential_container
        layout = container.layout()
        
        # Collect all row widgets with their indices and names
        rows = []
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget:
                # Find the name label in this row
                name_label = widget.findChild(QLabel, "")  # Get first QLabel
                if name_label:
                    rows.append((widget, name_label.text(), i))
        
        # Sort rows by name
        rows.sort(key=lambda x: x[1].lower(), reverse=not self._essential_sort_asc)
        
        # Reorder widgets
        for idx, (widget, name, orig_idx) in enumerate(rows):
            layout.removeWidget(widget)
        
        for idx, (widget, name, orig_idx) in enumerate(rows):
            layout.insertWidget(idx, widget)
        
        print(f"[Essential] Sorted by name {'A→Z' if self._essential_sort_asc else 'Z→A'}")
    
    def _update_essential_count(self):
        """Update essential items selection count."""
        selected = sum(1 for cb in self._essential_checks if cb.isChecked())
        total = len(self._essential_checks)
        self._essential_count_label.setText(f"{selected}/{total}")
        
        # Update select all checkbox state
        self._essential_select_all.blockSignals(True)
        self._essential_select_all.setChecked(selected == total and total > 0)
        self._essential_select_all.blockSignals(False)
    
    def _reset_essential_selections(self):
        """Reset all essential selections to default.
        Default: All checked EXCEPT clear_clipboard (idx 0) and disable_winkey (idx 7)
        """
        # Items that should be UNCHECKED by default
        unchecked_by_default = [0, 7]  # clear_clipboard, disable_winkey
        
        for idx, cb in enumerate(self._essential_checks):
            cb.setChecked(idx not in unchecked_by_default)
        
        self._update_essential_count()
        self._save_essential_states()
    
    def _save_essential_states(self):
        """Save essential checkbox states to separate config file."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Read current settings
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            
            # Get selected optimization IDs
            from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
            selected = []
            for i, cb in enumerate(self._essential_checks):
                if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                    selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
            
            # Save to settings
            settings["essential_optimizations"] = selected
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            
            print(f"[Booster] Saved essential states: {selected}")
            
        except Exception as e:
            print(f"[Booster] Error saving essential states: {e}")
    
    def _save_booster_settings(self):
        """Save booster checkbox settings (notify, auto-update)."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Read current settings
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            
            # Save checkbox states
            if hasattr(self, 'notify_boost_cb'):
                settings["notify_when_boosting"] = self.notify_boost_cb.isChecked()
            if hasattr(self, 'auto_update_cb'):
                settings["auto_update_on_profile"] = self.auto_update_cb.isChecked()
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            
        except Exception as e:
            print(f"[Booster] Error saving booster settings: {e}")
    
    def _load_booster_settings(self):
        """Load booster checkbox settings (notify, auto-update)."""
        try:
            import json
            from launcher import APPDATA_DIR
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # Restore checkbox states
                if hasattr(self, 'notify_boost_cb'):
                    self.notify_boost_cb.setChecked(settings.get("notify_when_boosting", True))
                if hasattr(self, 'auto_update_cb'):
                    self.auto_update_cb.setChecked(settings.get("auto_update_on_profile", False))
                    
        except Exception as e:
            print(f"[Booster] Error loading booster settings: {e}")
    
    def _load_essential_states(self):
        """Load essential checkbox states from config file, or apply defaults."""
        try:
            import json
            from launcher import APPDATA_DIR
            from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
            
            settings_path = os.path.join(APPDATA_DIR, "booster_settings.json")
            
            # Default: all checked EXCEPT clear_clipboard (idx 0) and disable_winkey (idx 7)
            unchecked_by_default = [0, 7]
            
            if not os.path.exists(settings_path):
                # Apply defaults on first load
                for idx, cb in enumerate(self._essential_checks):
                    cb.blockSignals(True)
                    cb.setChecked(idx not in unchecked_by_default)
                    cb.blockSignals(False)
                self._update_essential_count()
                return
            
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            selected = settings.get("essential_optimizations", None)
            
            if selected is None:
                # No saved settings, apply defaults
                for idx, cb in enumerate(self._essential_checks):
                    cb.blockSignals(True)
                    cb.setChecked(idx not in unchecked_by_default)
                    cb.blockSignals(False)
                self._update_essential_count()
                return
            
            # Set checkbox states from saved
            for i, cb in enumerate(self._essential_checks):
                if i < len(ESSENTIAL_OPTIMIZATIONS):
                    opt_id = ESSENTIAL_OPTIMIZATIONS[i]["id"]
                    cb.blockSignals(True)
                    cb.setChecked(opt_id in selected)
                    cb.blockSignals(False)
            
            self._update_essential_count()
            print(f"[Booster] Loaded essential states: {selected}")
            
        except Exception as e:
            print(f"[Booster] Error loading essential states: {e}")
    
    def _get_selected_optimizations(self) -> list:
        """Get list of selected optimization IDs."""
        from RamCleanerPresetDialog import ESSENTIAL_OPTIMIZATIONS
        
        selected = []
        for i, cb in enumerate(self._essential_checks):
            if cb.isChecked() and i < len(ESSENTIAL_OPTIMIZATIONS):
                selected.append(ESSENTIAL_OPTIMIZATIONS[i]["id"])
        return selected
    
    def _apply_essential_optimizations(self, game_exe: str = None) -> dict:
        """
        Apply selected essential optimizations.
        
        Args:
            game_exe: Optional game executable name for priority setting
        
        Returns dict with results for each optimization.
        """
        from essential_optimizations import get_optimizer
        
        optimizer = get_optimizer()
        selected = self._get_selected_optimizations()
        results = {}
        
        print(f"[Essential] Applying optimizations: {selected}")
        
        # Memory Boost
        if "memory_boost" in selected:
            results["memory_boost"] = optimizer.memory_boost()
        
        # Set Game Priority (only when game is running)
        if "set_game_priority" in selected:
            if game_exe:
                results["set_game_priority"] = optimizer.set_game_priority(game_exe, "high")
            else:
                # Skip but mark as success (no game to boost)
                results["set_game_priority"] = {"success": True, "skipped": True}
                print("[EssentialOpt] Set Game Priority: skipped (no game running)")
        
        # Disable Windows Key
        if "disable_winkey" in selected:
            results["disable_winkey"] = optimizer.disable_windows_key()
        
        # Clear Clipboard
        if "clear_clipboard" in selected:
            results["clear_clipboard"] = optimizer.clear_clipboard()
        
        # Disable Game Bar
        if "disable_game_bar" in selected:
            results["disable_game_bar"] = optimizer.disable_game_bar()
        
        # Disable Game Mode
        if "disable_game_mode" in selected:
            results["disable_game_mode"] = optimizer.disable_game_mode()
        
        # Disable DVR
        if "disable_dvr" in selected:
            results["disable_dvr"] = optimizer.disable_dvr()
        
        # Disable Updates
        if "disable_updates" in selected:
            results["disable_updates"] = optimizer.disable_updates()
        
        # Disable Core Parking
        if "disable_core_parking" in selected:
            results["disable_core_parking"] = optimizer.disable_core_parking()
        
        # Disable File Sharing
        if "disable_file_sharing" in selected:
            results["disable_file_sharing"] = optimizer.disable_file_sharing()
        
        return results
    
    def _restore_essential_optimizations(self, game_exe: str = None):
        """Restore settings changed by essential optimizations."""
        from essential_optimizations import get_optimizer
        
        optimizer = get_optimizer()
        selected = self._get_selected_optimizations()
        
        # Re-enable Windows Key
        if "disable_winkey" in selected:
            optimizer.enable_windows_key()
        
        # Restore game priority
        if "set_game_priority" in selected and game_exe:
            optimizer.restore_game_priority(game_exe)
        
        # Re-enable Game Bar
        if "disable_game_bar" in selected:
            optimizer.enable_game_bar()
        
        # Re-enable Game Mode
        if "disable_game_mode" in selected:
            optimizer.enable_game_mode()
        
        # Re-enable DVR
        if "disable_dvr" in selected:
            optimizer.enable_dvr()
        
        # Re-enable Updates
        if "disable_updates" in selected:
            optimizer.enable_updates()
        
        # Re-enable Core Parking
        if "disable_core_parking" in selected:
            optimizer.enable_core_parking()
        
        # Re-enable File Sharing
        if "disable_file_sharing" in selected:
            optimizer.enable_file_sharing()
        
        print("[Essential] Restored optimizations")

    def _create_processes_tab(self) -> QWidget:
        """Create Processes tab content matching reference design."""
        page = QWidget()
        page.setObjectName("processesPage")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # Warning banner at top
        warning = QFrame()
        warning.setObjectName("processesWarning")
        warning.setFixedHeight(50)
        warning.setStyleSheet("""
            QFrame#processesWarning {
                background: rgba(255, 91, 6, 0.15);
                border-bottom: 1px solid rgba(255, 91, 6, 0.3);
            }
        """)
        warning_layout = QHBoxLayout(warning)
        warning_layout.setContentsMargins(15, 10, 15, 10)
        
        warning_text = QLabel("Selected background processes will be automatically closed during Boost. "
                              "Terminating some processes may disrupt the normal operation of your PC. "
                              "We recommend only selecting the ones you are familiar with.")
        warning_text.setObjectName("processesWarningText")
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #cccccc; font-size: 10px; background: transparent;")
        warning_layout.addWidget(warning_text)
        
        page_layout.addWidget(warning)
        
        # Header row
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName("processesSelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet("""
            QFrame#processesSelectRow {
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        
        self._processes_select_all = QCheckBox("Select all")
        self._processes_select_all.setObjectName("processesSelectAll")
        self._processes_select_all.setStyleSheet("""
            QCheckBox { color: #e0e0e0; font-size: 11px; background: transparent; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
            QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
        """)
        self._processes_select_all.toggled.connect(self._on_processes_select_all)
        select_layout.addWidget(self._processes_select_all)
        
        self._processes_count_label = QLabel("0/0")
        self._processes_count_label.setObjectName("processesCountLabel")
        self._processes_count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        select_layout.addWidget(self._processes_count_label)
        select_layout.addStretch()
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        self._processes_sort_column = "memory"  # Default sort by memory
        self._processes_sort_asc = False  # Default descending (highest first)
        
        table = QTableWidget()
        table.setObjectName("processesTable")
        table.setColumnCount(5)  # Checkbox, Icon, Name, Memory, Blacklist
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(False)  # Disable built-in sorting, we handle it manually
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "", "Name", "Memory", "Blacklist"])
        
        # Column widths - generous sizing
        table.setColumnWidth(0, 50)   # Checkbox (#)
        table.setColumnWidth(1, 50)   # Icon
        table.setColumnWidth(2, 200)  # Name
        table.setColumnWidth(3, 100)  # Memory
        table.setColumnWidth(4, 80)   # Blacklist
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)  # Icon fixed
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Name stretches to fill remaining
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)  # Memory fixed
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)  # Blacklist fixed
        table.horizontalHeader().setMinimumSectionSize(35)
        
        # Custom sort handler for header clicks
        table.horizontalHeader().sectionClicked.connect(self._on_processes_header_clicked)
        
        # Styling
        table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::item:hover {
                background: rgba(255, 91, 6, 0.08);
            }
            QHeaderView::section {
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }
            QHeaderView::section:hover {
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 3px;
            }
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Store table reference
        self._processes_table = table
        
        page_layout.addWidget(table, 1)
        
        # Enable smooth scrolling for this table
        self._processes_table_smoother = SmoothTableWidget(table)
        
        
        # Bottom bar with Reset button (matching Essential tab style)
        bottom = QFrame()
        bottom.setObjectName("processesBottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet("""
            QFrame#processesBottom {
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName("processesResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_processes_selection)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
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
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Populate on load
        self._populate_processes_tab()
        
        return page
    
    def _on_processes_select_all(self, checked: bool):
        """Handle Select All checkbox for processes tab."""
        for cb in self._process_checks:
            cb.setChecked(checked)
        self._update_processes_count()
    
    def _update_processes_count(self):
        """Update processes selection count."""
        selected = sum(1 for cb in self._process_checks if cb.isChecked())
        total = len(self._process_checks)
        self._processes_count_label.setText(f"{selected}/{total}")
        
        # Update select all checkbox state
        self._processes_select_all.blockSignals(True)
        self._processes_select_all.setChecked(selected == total and total > 0)
        self._processes_select_all.blockSignals(False)
    
    def _on_processes_header_clicked(self, column: int):
        """Handle header click for sorting."""
        if column == 2:  # Name column
            self._sort_processes("name")
        elif column == 3:  # Memory column
            self._sort_processes("memory")
    
    def _sort_processes(self, column: str):
        """Sort processes by column."""
        if self._processes_sort_column == column:
            self._processes_sort_asc = not self._processes_sort_asc
        else:
            self._processes_sort_column = column
            self._processes_sort_asc = column == "name"  # Name ascending by default, memory descending
        
        # Update header indicators via QTableWidget
        name_arrow = " ▲" if self._processes_sort_column == "name" and self._processes_sort_asc else " ▼" if self._processes_sort_column == "name" else ""
        mem_arrow = " ▲" if self._processes_sort_column == "memory" and self._processes_sort_asc else " ▼" if self._processes_sort_column == "memory" else ""
        
        # Update table headers with sort arrows
        self._processes_table.setHorizontalHeaderLabels(["#", "", f"Name{name_arrow}", f"Memory{mem_arrow}", "Blacklist"])
        
        # Re-populate with new sorting
        self._populate_processes_tab()
    
    def _refresh_processes_list(self):
        """Refresh the processes list."""
        self._populate_processes_tab()
    
    def _reset_processes_selection(self):
        """Reset all process selections."""
        for cb in self._process_checks:
            cb.setChecked(False)
        self._update_processes_count()
    
    def _get_process_icon(self, exe_path: str) -> QPixmap:
        """Extract icon from exe file and return as QPixmap.
        
        Uses icoextract library to get the first icon from the exe.
        Returns default icon if extraction fails.
        """
        from PySide6.QtGui import QPixmap, QImage
        import tempfile
        
        # Initialize cache if not exists
        if not hasattr(self, '_process_icon_cache'):
            self._process_icon_cache = {}
        
        # Check cache first
        if exe_path in self._process_icon_cache:
            return self._process_icon_cache[exe_path]
        
        default_pixmap = QPixmap()
        
        if not ICOEXTRACT_AVAILABLE or not exe_path or not os.path.exists(exe_path):
            return default_pixmap
        
        try:
            from PIL import Image
            
            extractor = IconExtractor(exe_path)
            
            # Use temp file instead of BytesIO (more reliable)
            with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as tmp:
                tmp_path = tmp.name
            
            try:
                # Export icon to temp file
                extractor.export_icon(tmp_path, num=0)
                
                # Use PIL to open ICO and convert to PNG
                pil_img = Image.open(tmp_path)
                
                # Convert to RGBA and resize to 24x24
                pil_img = pil_img.convert('RGBA')
                pil_img.thumbnail((24, 24), Image.Resampling.LANCZOS)
                
                # Convert to PNG bytes
                png_data = io.BytesIO()
                pil_img.save(png_data, format='PNG')
                png_data.seek(0)
                
                # Load into QImage
                img = QImage()
                if img.loadFromData(png_data.read()):
                    pixmap = QPixmap.fromImage(img)
                    self._process_icon_cache[exe_path] = pixmap
                    return pixmap
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                
        except Exception as e:
            pass  # Silent fail, will use fallback emoji
        
        return default_pixmap
    
    def _populate_processes_tab(self):
        """Populate processes tab with running processes using QTableWidget."""
        import psutil
        import json
        import os
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtGui import QIcon, QPixmap
        
        table = self._processes_table
        
        # Load blacklist from file
        blacklist_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'process_blacklist.json')
        try:
            if os.path.exists(blacklist_path):
                with open(blacklist_path, 'r') as f:
                    self._process_blacklist = set(json.load(f))
            else:
                self._process_blacklist = set()
        except:
            self._process_blacklist = set()
        
        # Save currently checked process names BEFORE clearing
        checked_process_names = set()
        if hasattr(self, '_process_checks') and hasattr(self, '_process_data'):
            for i, cb in enumerate(self._process_checks):
                if cb.isChecked() and i < len(self._process_data):
                    checked_process_names.add(self._process_data[i]['name'])
        
        # Clear existing
        table.setRowCount(0)
        
        self._process_checks = []
        self._process_blacklist_checks = []  # Blacklist checkboxes
        self._process_data = []  # Store process info alongside checkboxes
        
        # Store checked names for restoring later
        self._checked_process_names = checked_process_names
        
        # Initialize icon cache if not exists
        if not hasattr(self, '_process_icon_cache'):
            self._process_icon_cache = {}
        
        # Processes to hide from list (lowercase)
        PROCESS_BLACKLIST = {
            'pwsh.exe', 'powershell.exe', 'cmd.exe', 'conhost.exe',
            'regedit.exe', 'registry', 'reg.exe',
            'svchost.exe', 'csrss.exe', 'smss.exe', 'wininit.exe',
            'services.exe', 'lsass.exe', 'winlogon.exe',
            'dwm.exe', 'explorer.exe', 'system', 'system idle process',
            'searchindexer.exe', 'searchhost.exe', 'runtimebroker.exe',
            'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
            'dllhost.exe', 'ctfmon.exe', 'textinputhost.exe',
            'shellexperiencehost.exe', 'startmenuexperiencehost.exe',
            'applicationframehost.exe', 'securityhealthsystray.exe',
            'helxaid.exe',  # Hide our own launcher
        }
        
        # Get processes and group by name
        process_groups = {}  # name -> {pids: [], memory: total, exe: first_exe}
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'exe']):
            try:
                info = proc.info
                mem = info['memory_info'].rss if info['memory_info'] else 0
                name = info['name']
                exe = info.get('exe', '')
                pid = info['pid']
                
                # Skip blacklisted processes and empty names
                if not name or name.lower() in PROCESS_BLACKLIST:
                    continue
                
                
                if name in process_groups:
                    process_groups[name]['pids'].append(pid)
                    process_groups[name]['memory'] += mem
                    # Keep first exe found (for icon)
                    if not process_groups[name]['exe'] and exe:
                        process_groups[name]['exe'] = exe
                else:
                    process_groups[name] = {
                        'pids': [pid],
                        'memory': mem,
                        'exe': exe
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Convert to list and filter by memory > 50MB
        processes = []
        for name, data in process_groups.items():
            if data['memory'] > 50 * 1024 * 1024:  # > 50 MB total
                processes.append({
                    'pids': data['pids'],  # Store all PIDs for killing
                    'name': name,
                    'memory': data['memory'],
                    'exe': data['exe'],
                    'count': len(data['pids'])  # Number of instances
                })
        
        # Sort based on current setting
        if self._processes_sort_column == "name":
            # For name: asc=True means A-Z (reverse=False), asc=False means Z-A (reverse=True)
            processes.sort(key=lambda x: x['name'].lower(), reverse=not self._processes_sort_asc)
        else:  # memory
            # For memory: asc=False means highest first (reverse=True), asc=True means lowest first (reverse=False)
            processes.sort(key=lambda x: x['memory'], reverse=not self._processes_sort_asc)
            
        # Set row count
        display_processes = processes[:50]
        table.setRowCount(len(display_processes))
        
        # Default icon for processes without exe
        default_icon = QIcon.fromTheme("application-x-executable")
        
        for idx, proc in enumerate(display_processes):
            # Column 0: Checkbox
            cb_widget = QWidget()
            cb_widget.setObjectName(f"processCheckWidget_{idx}")
            cb_widget.setStyleSheet("background: transparent;")
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            
            cb = QCheckBox()
            cb.setObjectName(f"processCheck_{idx}")
            cb.setStyleSheet("""
                QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
                QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
            """)
            # Restore checked state if this process was checked before refresh
            if hasattr(self, '_checked_process_names') and proc['name'] in self._checked_process_names:
                cb.setChecked(True)
            cb.toggled.connect(self._update_processes_count)
            cb.toggled.connect(self._update_total_items_count)
            self._process_checks.append(cb)
            self._process_data.append({'pids': proc['pids'], 'name': proc['name'], 'count': proc['count']})
            cb_layout.addWidget(cb)
            table.setCellWidget(idx, 0, cb_widget)
            
            # Column 1: Icon
            icon_widget = QWidget()
            icon_widget.setStyleSheet("background: transparent;")
            icon_layout = QHBoxLayout(icon_widget)
            icon_layout.setContentsMargins(4, 4, 4, 4)
            icon_layout.setAlignment(Qt.AlignCenter)
            
            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setStyleSheet("background: transparent;")
            
            # Try to get icon from cache or extract
            exe_path = proc.get('exe', '')
            if exe_path and exe_path in self._process_icon_cache:
                pixmap = self._process_icon_cache[exe_path]
                icon_label.setPixmap(pixmap)
            elif exe_path:
                try:
                    import os
                    if os.path.exists(exe_path):
                        icon = QIcon(exe_path)
                        if not icon.isNull():
                            pixmap = icon.pixmap(24, 24)
                            icon_label.setPixmap(pixmap)
                            self._process_icon_cache[exe_path] = pixmap
                        else:
                            # Try Windows shell icon extraction
                            from PySide6.QtWidgets import QFileIconProvider
                            from PySide6.QtCore import QFileInfo
                            provider = QFileIconProvider()
                            file_info = QFileInfo(exe_path)
                            icon = provider.icon(file_info)
                            if not icon.isNull():
                                pixmap = icon.pixmap(24, 24)
                                icon_label.setPixmap(pixmap)
                                self._process_icon_cache[exe_path] = pixmap
                except Exception:
                    pass  # Silently fail, no icon shown
            
            icon_layout.addWidget(icon_label)
            table.setCellWidget(idx, 1, icon_widget)
            
            # Column 2: Name
            name_item = QTableWidgetItem(proc['name'])
            name_item.setForeground(QColor("#e0e0e0"))
            table.setItem(idx, 2, name_item)
            
            # Column 3: Memory
            mem = proc['memory']
            mem_str = f"{mem / (1024**3):.2f} GB" if mem >= 1024**3 else f"{mem / (1024**2):.0f} MB"
            mem_item = QTableWidgetItem(mem_str)
            mem_item.setForeground(QColor("#888888"))
            mem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # Store raw memory value for proper numeric sorting
            mem_item.setData(Qt.UserRole, mem)
            table.setItem(idx, 3, mem_item)
            
            # Column 4: Blacklist checkbox
            bl_widget = QWidget()
            bl_widget.setObjectName(f"processBlacklistWidget_{idx}")
            bl_widget.setStyleSheet("background: transparent;")
            bl_layout = QHBoxLayout(bl_widget)
            bl_layout.setContentsMargins(8, 0, 8, 0)
            bl_layout.setAlignment(Qt.AlignCenter)
            
            bl_cb = QCheckBox()
            bl_cb.setObjectName(f"processBlacklist_{idx}")
            bl_cb.setStyleSheet("""
                QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
                QCheckBox::indicator:checked { background: #ff3333; border-color: #ff3333; }
            """)
            bl_cb.setToolTip("Blacklist: Skip this process during boost")
            # Check if this process is in blacklist
            if proc['name'] in self._process_blacklist:
                bl_cb.setChecked(True)
            bl_cb.toggled.connect(lambda checked, name=proc['name']: self._on_blacklist_toggled(name, checked))
            self._process_blacklist_checks.append(bl_cb)
            bl_layout.addWidget(bl_cb)
            table.setCellWidget(idx, 4, bl_widget)
        
        self._update_processes_count()
    
    def _on_blacklist_toggled(self, process_name: str, checked: bool):
        """Handle blacklist checkbox toggle - save to file."""
        import json
        import os
        
        if checked:
            self._process_blacklist.add(process_name)
        else:
            self._process_blacklist.discard(process_name)
        
        # Save to file
        blacklist_path = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID', 'process_blacklist.json')
        try:
            os.makedirs(os.path.dirname(blacklist_path), exist_ok=True)
            with open(blacklist_path, 'w') as f:
                json.dump(list(self._process_blacklist), f)
            print(f"[Blacklist] Saved: {process_name} = {checked}")
        except Exception as e:
            print(f"[Blacklist] Error saving: {e}")
    
    def _create_basic_services_tab(self) -> QWidget:
        """Create Basic Services tab content."""
        from RamCleanerPresetDialog import BASIC_SERVICES, get_service_status
        self._basic_service_checks = []  # Store for MANUAL BOOST
        self._basic_service_data = []  # Store service names
        return self._create_services_list(BASIC_SERVICES, get_service_status, 
                                          self._basic_service_checks, self._basic_service_data, "basic")
    
    def _create_advanced_services_tab(self) -> QWidget:
        """Create Advanced Services tab content."""
        from RamCleanerPresetDialog import ADVANCED_SERVICES, get_service_status
        self._advanced_service_checks = []  # Store for MANUAL BOOST
        self._advanced_service_data = []  # Store service names
        return self._create_services_list(ADVANCED_SERVICES, get_service_status,
                                          self._advanced_service_checks, self._advanced_service_data, "advanced")
    
    def _create_services_list(self, services: list, get_status, check_storage: list = None, data_storage: list = None, tab_id: str = "services") -> QWidget:
        """Create a services list using QTableWidget for proper column alignment.
        
        Args:
            services: List of service dicts with 'name', 'display', 'desc' keys
            get_status: Function to get service status
            check_storage: Optional list to store checkboxes (for MANUAL BOOST)
            data_storage: Optional list to store service names (for stopping)
            tab_id: Unique ID for this tab (basic/advanced)
        """
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        
        page = QWidget()
        page.setObjectName(f"{tab_id}Page")
        page.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # ========== SELECT ALL ROW ==========
        select_row = QFrame()
        select_row.setObjectName(f"{tab_id}SelectRow")
        select_row.setFixedHeight(35)
        select_row.setStyleSheet(f"""
            QFrame#{tab_id}SelectRow {{
                background: rgba(40, 40, 40, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }}
        """)
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(12, 0, 12, 0)
        select_layout.setSpacing(8)
        
        select_all_cb = QCheckBox("Select all")
        select_all_cb.setObjectName(f"{tab_id}SelectAll")
        select_all_cb.setStyleSheet("""
            QCheckBox { color: #e0e0e0; font-size: 11px; background: transparent; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
            QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
        """)
        if tab_id == "basic":
            self._basic_select_all = select_all_cb
            select_all_cb.setChecked(True)  # Default: all checked for basic
            select_all_cb.toggled.connect(self._on_basic_select_all)
        else:
            self._advanced_select_all = select_all_cb
            select_all_cb.toggled.connect(self._on_advanced_select_all)
        select_layout.addWidget(select_all_cb)
        
        count_label = QLabel(f"0/{len(services)}")
        count_label.setObjectName(f"{tab_id}CountLabel")
        count_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        if tab_id == "basic":
            self._basic_count_label = count_label
        else:
            self._advanced_count_label = count_label
        select_layout.addWidget(count_label)
        select_layout.addStretch()
        
        page_layout.addWidget(select_row)
        
        # ========== TABLE WIDGET ==========
        table = QTableWidget()
        table.setObjectName(f"{tab_id}Table")
        table.setColumnCount(4)
        table.setRowCount(len(services))
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        
        # Set header labels
        table.setHorizontalHeaderLabels(["#", "Name", "Status", "Description"])
        
        # Column widths
        table.setColumnWidth(0, 50)   # Checkbox (#) - fixed
        table.setColumnWidth(1, 250)  # Name - min 200
        table.setColumnWidth(2, 100)  # Status - min 175
        table.horizontalHeader().setStretchLastSection(True)  # Description stretches
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # # column fixed
        table.horizontalHeader().setMinimumSectionSize(50)  # Base minimum
        
        # Set minimum sizes for Name and Status columns
        header = table.horizontalHeader()
        header.setMinimumSectionSize(50)  # Minimum for resizable columns
        
        # Styling
        table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent;
                border: none;
                color: #e0e0e0;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            QTableWidget::item:hover {{
                background: rgba(255, 91, 6, 0.08);
            }}
            QHeaderView::section {{
                background: rgba(40, 40, 40, 0.9);
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px;
            }}
            QHeaderView::section:hover {{
                background: rgba(255, 91, 6, 0.15);
                color: #FF5B06;
            }}
            QScrollBar:vertical {{
                background: #1a1a1a;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #444;
                border-radius: 3px;
            }}
        """)
        
        # Row height
        table.verticalHeader().setDefaultSectionSize(45)
        
        # Populate table
        for idx, svc in enumerate(services):
            status = get_status(svc["name"])
            
            # Column 0: Checkbox
            cb_widget = QWidget()
            cb_widget.setObjectName(f"{tab_id}CheckWidget_{idx}")
            cb_widget.setStyleSheet("background: transparent;")
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            
            cb = QCheckBox()
            cb.setObjectName(f"{tab_id}Check_{idx}")
            cb.setStyleSheet("""
                QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #555; border-radius: 3px; background: #2a2a2a; }
                QCheckBox::indicator:checked { background: #FF5B06; border-color: #FF5B06; }
            """)
            # Default: Basic tab = all checked, Advanced tab = all unchecked
            if tab_id == "basic":
                cb.setChecked(True)
            cb_layout.addWidget(cb)
            table.setCellWidget(idx, 0, cb_widget)
            
            # Store checkbox and data for MANUAL BOOST
            if check_storage is not None:
                check_storage.append(cb)
                cb.toggled.connect(self._update_total_items_count)
                if tab_id == "basic":
                    cb.toggled.connect(self._update_basic_count)
                else:
                    cb.toggled.connect(self._update_advanced_count)
            if data_storage is not None:
                data_storage.append({'name': svc['name'], 'display': svc['display']})
            
            # Column 1: Name
            name_item = QTableWidgetItem(svc["display"])
            name_item.setForeground(QColor("#e0e0e0"))
            table.setItem(idx, 1, name_item)
            
            # Column 2: Status
            status_item = QTableWidgetItem(status)
            status_color = "#4ade80" if status == "Running" else "#888888"
            status_item.setForeground(QColor(status_color))
            table.setItem(idx, 2, status_item)
            
            # Column 3: Description
            desc_item = QTableWidgetItem(svc["desc"])
            desc_item.setForeground(QColor("#666666"))
            table.setItem(idx, 3, desc_item)
        
        page_layout.addWidget(table, 1)
        
        # Store table reference for sorting
        if tab_id == "basic":
            self._basic_table = table
            self._basic_table_smoother = SmoothTableWidget(table)
        else:
            self._advanced_table = table
            self._advanced_table_smoother = SmoothTableWidget(table)
        
        
        # ========== BOTTOM BAR ==========
        bottom = QFrame()
        bottom.setObjectName(f"{tab_id}Bottom")
        bottom.setFixedHeight(75)
        bottom.setStyleSheet(f"""
            QFrame#{tab_id}Bottom {{
                background: rgba(30, 30, 30, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }}
        """)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        bottom_layout.setAlignment(Qt.AlignVCenter)
        bottom_layout.addStretch()
        
        reset_btn = QPushButton("RESET TO DEFAULT")
        reset_btn.setObjectName(f"{tab_id}ResetBtn")
        reset_btn.setFixedSize(170, 38)
        reset_btn.setCursor(Qt.PointingHandCursor)
        if tab_id == "basic":
            reset_btn.clicked.connect(self._reset_basic_services)
        else:
            reset_btn.clicked.connect(self._reset_advanced_services)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
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
        bottom_layout.addWidget(reset_btn, alignment=Qt.AlignVCenter)
        
        page_layout.addWidget(bottom)
        
        # Update count label after all checkboxes are created
        if tab_id == "basic":
            self._update_basic_count()
        else:
            self._update_advanced_count()
        
        return page
    
    def _on_basic_select_all(self, checked: bool):
        """Handle Select All checkbox for Basic Services tab."""
        if hasattr(self, '_basic_service_checks'):
            for cb in self._basic_service_checks:
                cb.setChecked(checked)
        self._update_basic_count()
        self._update_total_items_count()
    
    def _on_advanced_select_all(self, checked: bool):
        """Handle Select All checkbox for Advanced Services tab."""
        if hasattr(self, '_advanced_service_checks'):
            for cb in self._advanced_service_checks:
                cb.setChecked(checked)
        self._update_advanced_count()
        self._update_total_items_count()
    
    def _update_basic_count(self):
        """Update Basic Services count label."""
        if hasattr(self, '_basic_service_checks') and hasattr(self, '_basic_count_label'):
            selected = sum(1 for cb in self._basic_service_checks if cb.isChecked())
            total = len(self._basic_service_checks)
            self._basic_count_label.setText(f"{selected}/{total}")
    
    def _update_advanced_count(self):
        """Update Advanced Services count label."""
        if hasattr(self, '_advanced_service_checks') and hasattr(self, '_advanced_count_label'):
            selected = sum(1 for cb in self._advanced_service_checks if cb.isChecked())
            total = len(self._advanced_service_checks)
            self._advanced_count_label.setText(f"{selected}/{total}")
    
    def _refresh_services_status(self):
        """Refresh status column for Basic and Advanced Services tabs."""
        from RamCleanerPresetDialog import BASIC_SERVICES, ADVANCED_SERVICES, get_service_status
        
        # Refresh Basic Services tab
        if hasattr(self, '_basic_table'):
            for idx, svc in enumerate(BASIC_SERVICES):
                if idx < self._basic_table.rowCount():
                    status = get_service_status(svc["name"])
                    status_item = self._basic_table.item(idx, 2)
                    if status_item:
                        status_item.setText(status)
                        status_color = "#4ade80" if status == "Running" else "#888888"
                        status_item.setForeground(QColor(status_color))
        
        # Refresh Advanced Services tab
        if hasattr(self, '_advanced_table'):
            for idx, svc in enumerate(ADVANCED_SERVICES):
                if idx < self._advanced_table.rowCount():
                    status = get_service_status(svc["name"])
                    status_item = self._advanced_table.item(idx, 2)
                    if status_item:
                        status_item.setText(status)
                        status_color = "#4ade80" if status == "Running" else "#888888"
                        status_item.setForeground(QColor(status_color))
    
    def _reset_basic_services(self):
        """Reset all Basic Services checkboxes to default (all checked)."""
        if hasattr(self, '_basic_service_checks'):
            for cb in self._basic_service_checks:
                cb.setChecked(True)
        if hasattr(self, '_basic_select_all'):
            self._basic_select_all.setChecked(True)
        self._update_basic_count()
        self._update_total_items_count()
    
    def _reset_advanced_services(self):
        """Reset all Advanced Services checkboxes to unchecked."""
        if hasattr(self, '_advanced_service_checks'):
            for cb in self._advanced_service_checks:
                cb.setChecked(False)
        if hasattr(self, '_advanced_select_all'):
            self._advanced_select_all.setChecked(False)
        self._update_advanced_count()
        self._update_total_items_count()
    
    def _create_cpu_page(self):
        """Create CPU detailed page."""
        page = QWidget()
        page.setObjectName("cpuPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("CPU Details")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("CPU detailed view coming soon...")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_drive_page(self):
        """Create Drive detailed page."""
        page = QWidget()
        page.setObjectName("drivePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("Drive Details")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("Drive detailed view coming soon...")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_health_page(self):
        """Create Health detailed page."""
        page = QWidget()
        page.setObjectName("healthPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("Hardware Health")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("Health detailed view coming soon...")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_fan_page(self):
        """Create Fan Speed detailed page."""
        page = QWidget()
        page.setObjectName("fanPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        
        title = QLabel("Fan Speed Monitor")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        placeholder = QLabel("Fan detailed view coming soon...")
        placeholder.setStyleSheet("color: #888888; font-size: 14px; background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder, stretch=1)
        
        return page
    
    def _create_header(self):
        """Create header with title and update interval control."""
        header = QWidget()
        header.setObjectName("hardwareHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QLabel("HELXTATS")
        title.setObjectName("hardwareTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 24px; font-weight: 700; background: transparent;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Update interval control
        interval_label = QLabel("Update Interval:")
        interval_label.setObjectName("intervalLabel")
        interval_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        header_layout.addWidget(interval_label)
        
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setObjectName("intervalSpinbox")
        self.interval_spinbox.setRange(100, 1000)
        self.interval_spinbox.setSingleStep(100)
        self.interval_spinbox.setValue(500)
        self.interval_spinbox.setSuffix(" ms")
        self.interval_spinbox.setFixedWidth(100)
        self.interval_spinbox.valueChanged.connect(self._on_interval_changed)
        self.interval_spinbox.setStyleSheet("""
            QSpinBox {
                background: rgba(40, 44, 52, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                padding: 4px 8px;
            }
        """)
        header_layout.addWidget(self.interval_spinbox)
        
        return header
    
    def _create_overview_page(self):
        """Create the main overview dashboard."""
        scroll = SmoothScrollArea()
        scroll.setObjectName("overviewScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        content = QWidget()
        content.setObjectName("overviewContent")
        
        # Outer vertical layout to keep cards at natural height (no vertical stretch)
        outer_layout = QVBoxLayout(content)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        # Inner horizontal layout for RAM Cleaner + Stats Grid
        inner_widget = QWidget()
        main_layout = QHBoxLayout(inner_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)
        
        # LEFT COLUMN - RAM Cleaner
        left_col = self._create_ram_cleaner_section()
        main_layout.addWidget(left_col)
        
        # RIGHT COLUMN - Stats grid
        right_col = self._create_stats_grid()
        main_layout.addWidget(right_col, stretch=1)
        
        outer_layout.addWidget(inner_widget)
        outer_layout.addStretch()  # Push everything to top, prevent vertical stretching
        
        scroll.setWidget(content)
        return scroll
    
    def _create_ram_cleaner_section(self):
        """Create the RAM Cleaner section with gauge."""
        container = QFrame()
        container.setObjectName("ramCleanerContainer")
        container.setFixedWidth(320)
        container.setStyleSheet("""
            QFrame#ramCleanerContainer {
                background: rgba(24, 24, 28, 0.95);
                border: none;
                border-radius: 16px;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Title
        title = QLabel("RAM Cleaner")
        title.setObjectName("ramCleanerTitle")
        title.setStyleSheet("color: #e0e0e0; font-size: 18px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        # Circular gauge (overview page gauge - separate from RAM page gauge)
        self.overview_ram_gauge = CircularGauge()
        self.overview_ram_gauge.setObjectName("overviewRamGauge")
        self.overview_ram_gauge.setMinimumSize(200, 200)
        layout.addWidget(self.overview_ram_gauge, alignment=Qt.AlignCenter)
        
        # Before/After stats
        stats_row = QHBoxLayout()
        
        # Before
        before_col = QVBoxLayout()
        before_label = QLabel("Before:")
        before_label.setObjectName("beforeLabel")
        before_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        self.before_value = QLabel("0 GB / 0%")
        self.before_value.setObjectName("beforeValue")
        self.before_value.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: 500; background: transparent;")
        before_col.addWidget(before_label)
        before_col.addWidget(self.before_value)
        stats_row.addLayout(before_col)
        
        # After
        after_col = QVBoxLayout()
        after_label = QLabel("After:")
        after_label.setObjectName("afterLabel")
        after_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        self.after_value = QLabel("Estimated")
        self.after_value.setObjectName("afterValue")
        self.after_value.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: 500; background: transparent;")
        after_col.addWidget(after_label)
        after_col.addWidget(self.after_value)
        stats_row.addLayout(after_col)
        
        layout.addLayout(stats_row)
        
        # Used/Free bar
        self.ram_bar = ProgressBarWidget()
        self.ram_bar.setObjectName("ramUsageBar")
        self.ram_bar.setLabel("Used")
        layout.addWidget(self.ram_bar)
        
        # Free label
        self.free_label = QLabel("Free: 0 GB")
        self.free_label.setObjectName("freeRamLabel")
        self.free_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        layout.addWidget(self.free_label)
        
        # Custom mode toggle button
        self._custom_mode_active = False
        self.custom_mode_btn = QPushButton("Custom Preset")
        self.custom_mode_btn.setObjectName("customModeButton")
        self.custom_mode_btn.setCursor(Qt.PointingHandCursor)
        self.custom_mode_btn.setFixedHeight(36)
        self.custom_mode_btn.setCheckable(True)
        self.custom_mode_btn.clicked.connect(lambda: self._toggle_custom_mode())
        # Initial inactive style
        self.custom_mode_btn.setStyleSheet("""
            QPushButton#customModeButton {
                background: rgba(60, 60, 70, 0.8);
                color: #aaaaaa;
                border: 1px solid rgba(100, 100, 100, 0.3);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton#customModeButton:hover {
                background: rgba(80, 80, 90, 0.9);
                color: #dddddd;
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)
        layout.addWidget(self.custom_mode_btn)
        
        # Clean RAM button
        self.clean_btn = QPushButton("Clean RAM")
        self.clean_btn.setObjectName("cleanRamButton")
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.setFixedHeight(48)
        
        def _on_clean_btn_clicked():
            if getattr(self, '_is_boosting', False):
                self._run_manual_boost()
            else:
                self._clean_ram()
                
        self.clean_btn.clicked.connect(_on_clean_btn_clicked)
        self.clean_btn.setStyleSheet("""
            QPushButton#cleanRamButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton#cleanRamButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7B26, stop:1 #FDC933);
            }
            QPushButton#cleanRamButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E54B00, stop:1 #DD9903);
            }
        """)
        layout.addWidget(self.clean_btn)
        
        layout.addStretch()
        
        return container
    
    def _create_stats_grid(self):
        """Create the stats grid with charts."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        
        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True, background='#23262d', foreground='#888888')
        
        # CPU Usage card with chart
        cpu_card = StatsCard("CPU Usage")
        cpu_card.setObjectName("cpuUsageCard")
        self.cpu_chart = pg.PlotWidget()
        self.cpu_chart.setObjectName("cpuChart")
        self.cpu_chart.setFixedHeight(100)
        self.cpu_chart.showGrid(x=False, y=True, alpha=0.3)
        self.cpu_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.cpu_chart.hideAxis('bottom')
        self.cpu_chart.getAxis('left').setWidth(30)
        self.cpu_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.cpu_chart.enableAutoRange(axis='x')   # X auto-range
        self.cpu_curve = self.cpu_chart.plot(pen=pg.mkPen('#FF5B06', width=2))
        # Text label at leading edge showing current value
        self.cpu_leading_text = pg.TextItem(text='0%', color='#FF5B06', anchor=(0, 0.5))
        self.cpu_leading_text.setFont(QFont('Segoe UI', 9, QFont.Bold))
        self.cpu_chart.addItem(self.cpu_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.cpu_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.cpu_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.cpu_chart)
        cpu_card.addWidget(self.cpu_chart)
        
        # CPU stats row
        cpu_stats = QHBoxLayout()
        self.cpu_percent_label = QLabel("0%")
        self.cpu_percent_label.setObjectName("cpuPercentLabel")
        self.cpu_percent_label.setStyleSheet("color: #FF5B06; font-size: 24px; font-weight: 700; background: transparent;")
        cpu_stats.addWidget(self.cpu_percent_label)
        self.cpu_freq_label = QLabel("0 GHz")
        self.cpu_freq_label.setObjectName("cpuFreqLabel")
        self.cpu_freq_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        cpu_stats.addWidget(self.cpu_freq_label)
        cpu_stats.addStretch()
        cpu_stats_widget = QWidget()
        cpu_stats_widget.setObjectName("cpuStatsWidget")
        cpu_stats_widget.setLayout(cpu_stats)
        cpu_card.addWidget(cpu_stats_widget)
        grid.addWidget(cpu_card, 0, 0)
        
        # RAM Usage card with chart (same as CPU)
        ram_card = StatsCard("RAM Usage")
        ram_card.setObjectName("ramUsageCard")
        self.ram_chart = pg.PlotWidget()
        self.ram_chart.setObjectName("ramChart")
        self.ram_chart.setFixedHeight(100)
        self.ram_chart.showGrid(x=False, y=True, alpha=0.3)
        self.ram_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.ram_chart.hideAxis('bottom')
        self.ram_chart.getAxis('left').setWidth(30)
        self.ram_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.ram_chart.enableAutoRange(axis='x')   # X auto-range
        self.ram_curve = self.ram_chart.plot(pen=pg.mkPen('#FDA903', width=2))
        # Text label at leading edge showing current value
        self.ram_leading_text = pg.TextItem(text='0%', color='#FDA903', anchor=(0, 0.5))
        self.ram_leading_text.setFont(QFont('Segoe UI', 9, QFont.Bold))
        self.ram_chart.addItem(self.ram_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.ram_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.ram_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.ram_chart)
        ram_card.addWidget(self.ram_chart)
        
        # RAM stats row
        ram_stats = QHBoxLayout()
        self.ram_percent_label = QLabel("0%")
        self.ram_percent_label.setObjectName("ramPercentLabel")
        self.ram_percent_label.setStyleSheet("color: #FDA903; font-size: 24px; font-weight: 700; background: transparent;")
        ram_stats.addWidget(self.ram_percent_label)
        self.qs_ram_stats_label = QLabel("0 GB / 0 GB")
        self.qs_ram_stats_label.setObjectName("qsRamStatsLabel")
        self.qs_ram_stats_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        ram_stats.addWidget(self.qs_ram_stats_label)
        ram_stats.addStretch()
        ram_stats_widget = QWidget()
        ram_stats_widget.setObjectName("ramStatsWidget")
        ram_stats_widget.setLayout(ram_stats)
        ram_card.addWidget(ram_stats_widget)
        grid.addWidget(ram_card, 0, 1)
        
        # Network Usage card (compact - no icons)
        network_card = StatsCard("Network")
        network_card.setObjectName("networkUsageCard")
        network_card.setMaximumHeight(70)  # Compact height
        net_layout = QHBoxLayout()
        net_layout.setSpacing(12)
        net_layout.setContentsMargins(0, 0, 0, 0)
        
        # Download label with inline arrow
        self.download_label = QLabel("↓ 0 Mbps")
        self.download_label.setObjectName("downloadLabel")
        self.download_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600; background: transparent;")
        net_layout.addWidget(self.download_label)
        
        # Upload label with inline arrow
        self.upload_label = QLabel("↑ 0 Mbps")
        self.upload_label.setObjectName("uploadLabel")
        self.upload_label.setStyleSheet("color: #f97316; font-size: 11px; font-weight: 600; background: transparent;")
        net_layout.addWidget(self.upload_label)
        
        net_layout.addStretch()
        
        net_widget = QWidget()
        net_widget.setObjectName("networkWidget")
        net_widget.setLayout(net_layout)
        network_card.addWidget(net_widget)
        grid.addWidget(network_card, 1, 1)
        
        # Disk S.M.A.R.T card (below Network)
        disk_health_card = StatsCard("Disk S.M.A.R.T")
        disk_health_card.setObjectName("diskHealthCard")
        disk_health_card.setMinimumHeight(220)
        
        # Container for disk health items (vertical layout with scroll)
        self.disk_health_container = QVBoxLayout()
        self.disk_health_container.setSpacing(4)
        self.disk_health_container.setContentsMargins(0, 0, 0, 0)
        
        disk_health_content = QWidget()
        disk_health_content.setObjectName("diskHealthContent")
        disk_health_content.setLayout(self.disk_health_container)
        disk_health_content.setStyleSheet("background: transparent;")
        
        # Scroll area for disk health
        disk_scroll = SmoothScrollArea()
        disk_scroll.setObjectName("diskHealthScroll")
        disk_scroll.setWidgetResizable(True)
        disk_scroll.setWidget(disk_health_content)
        disk_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        disk_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        disk_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.05);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.2);
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        disk_scroll.setMinimumHeight(180)
        
        disk_health_card.addWidget(disk_scroll)
        grid.addWidget(disk_health_card, 2, 1)
        
        # Disk Usage card with speed chart + usage bars
        disk_card = StatsCard("Disk Usage")
        disk_card.setObjectName("diskUsageCard")
        
        # Disk usage chart - single line showing overall disk usage %
        self.disk_chart = pg.PlotWidget()
        self.disk_chart.setObjectName("diskChart")
        self.disk_chart.setFixedHeight(80)
        self.disk_chart.showGrid(x=False, y=True, alpha=0.3)
        self.disk_chart.setYRange(-10, 100)  # Start at -10 to ensure values < 1 are visible
        self.disk_chart.hideAxis('bottom')
        self.disk_chart.getAxis('left').setWidth(30)
        self.disk_chart.disableAutoRange(axis='y')  # Keep Y fixed at 0-100
        self.disk_chart.enableAutoRange(axis='x')   # X auto-range
        self.disk_chart.setXRange(0, 60, padding=0)  # Default to View All (60 data points)
        self.disk_usage_curve = self.disk_chart.plot(pen=pg.mkPen('#f97316', width=2), name='Usage')
        # Text label at leading edge showing current value
        self.disk_leading_text = pg.TextItem(text='0%', color='#f97316', anchor=(0, 0.5))
        self.disk_leading_text.setFont(QFont('Segoe UI', 9, QFont.Bold))
        self.disk_chart.addItem(self.disk_leading_text)
        # Lock Y-axis to 0-100 even when View All is triggered
        self.disk_chart.sigRangeChanged.connect(lambda: self._enforce_chart_y_range(self.disk_chart, -10, 100))
        # Setup mutual exclusive X/Y axis dragging
        self._setup_mutual_exclusive_drag(self.disk_chart)
        disk_card.addWidget(self.disk_chart)
        
        # Disk usage stats row (similar to CPU)
        disk_stats = QHBoxLayout()
        self.disk_percent_label = QLabel("0%")
        self.disk_percent_label.setObjectName("diskPercentLabel")
        self.disk_percent_label.setStyleSheet("color: #f97316; font-size: 24px; font-weight: 700; background: transparent;")
        disk_stats.addWidget(self.disk_percent_label)
        disk_stats.addStretch()
        disk_stats_widget = QWidget()
        disk_stats_widget.setObjectName("diskStatsWidget")
        disk_stats_widget.setLayout(disk_stats)
        disk_card.addWidget(disk_stats_widget)
        
        # Disk usage bars container
        self.disk_bars_container = QVBoxLayout()
        disk_bars_widget = QWidget()
        disk_bars_widget.setObjectName("diskBarsWidget")
        disk_bars_widget.setLayout(self.disk_bars_container)
        disk_card.addWidget(disk_bars_widget)
        grid.addWidget(disk_card, 1, 0, 2, 1)  # Span 2 rows in column 0
        
        # Hardware Health card (compact)
        health_card = StatsCard("Health")
        health_card.setObjectName("healthCard")
        health_card.setMaximumHeight(125)
        health_card.setMaximumWidth(446)
        
        # Check if LibreHardwareMonitor or HWiNFO is available for temps
        try:
            from integrations.tools_downloader import (
                is_librehwmon_available, is_hwinfo_available,
                LIBREHWMON_DIR, HWINFO_DIR
            )
            self._librehwmon_available = is_librehwmon_available()
            self._hwinfo_available = is_hwinfo_available()
            self._hwmon_available = self._librehwmon_available or self._hwinfo_available
        except ImportError:
            self._librehwmon_available = False
            self._hwinfo_available = False
            self._hwmon_available = False
        
        health_row = QHBoxLayout()
        health_row.setSpacing(20)
        health_row.setContentsMargins(5, 5, 5, 5)
        
        # CPU Section
        cpu_box = QVBoxLayout()
        cpu_box.setSpacing(2)
        cpu_header = QLabel("CPU")
        cpu_header.setObjectName("cpuHeader")
        cpu_header.setStyleSheet("color: #ff6b35; font-size: 11px; font-weight: bold; background: transparent;")
        cpu_header.setAlignment(Qt.AlignCenter)
        
        self.cpu_temp_value = QLabel("--°C")
        self.cpu_temp_value.setObjectName("cpuTempValue")
        self.cpu_temp_value.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: 600; background: transparent;")
        self.cpu_temp_value.setAlignment(Qt.AlignCenter)
        
        self.cpu_load_value = QLabel("--%")
        self.cpu_load_value.setObjectName("cpuLoadValue")
        self.cpu_load_value.setStyleSheet("color: #60a5fa; font-size: 11px; font-weight: 500; background: transparent;")
        self.cpu_load_value.setAlignment(Qt.AlignCenter)
        
        cpu_box.addWidget(cpu_header)
        cpu_box.addWidget(self.cpu_temp_value)
        cpu_box.addWidget(self.cpu_load_value)
        health_row.addLayout(cpu_box)
        
        # GPU Section
        gpu_box = QVBoxLayout()
        gpu_box.setSpacing(2)
        gpu_header = QLabel("GPU")
        gpu_header.setObjectName("gpuHeader")
        gpu_header.setStyleSheet("color: #22d3ee; font-size: 11px; font-weight: bold; background: transparent;")
        gpu_header.setAlignment(Qt.AlignCenter)
        
        self.gpu_temp_value = QLabel("--°C")
        self.gpu_temp_value.setObjectName("gpuTempValue")
        self.gpu_temp_value.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: 600; background: transparent;")
        self.gpu_temp_value.setAlignment(Qt.AlignCenter)
        
        self.gpu_load_value = QLabel("--%")
        self.gpu_load_value.setObjectName("gpuLoadValue")
        self.gpu_load_value.setStyleSheet("color: #60a5fa; font-size: 11px; font-weight: 500; background: transparent;")
        self.gpu_load_value.setAlignment(Qt.AlignCenter)
        
        gpu_box.addWidget(gpu_header)
        gpu_box.addWidget(self.gpu_temp_value)
        gpu_box.addWidget(self.gpu_load_value)
        health_row.addLayout(gpu_box)
        
        # Power Section (FAN moved to separate card)
        pwr_box = QVBoxLayout()
        pwr_box.setSpacing(2)
        pwr_header = QLabel("PWR")
        pwr_header.setObjectName("pwrHeader")
        pwr_header.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; background: transparent;")
        pwr_header.setAlignment(Qt.AlignCenter)
        
        self.power_value = QLabel("--")
        self.power_value.setObjectName("powerValue")
        self.power_value.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 500; background: transparent;")
        self.power_value.setAlignment(Qt.AlignCenter)
        
        pwr_box.addWidget(pwr_header)
        pwr_box.addWidget(self.power_value)
        pwr_box.addStretch()
        health_row.addLayout(pwr_box)
        
        health_row.addStretch()
        
        # Install or Start button for hardware monitor (LibreHardwareMonitor or HWiNFO)
        if not self._hwmon_available:
            # Not installed - show Install button
            install_col = QVBoxLayout()
            install_col.setSpacing(2)
            self.install_monitor_btn = QPushButton("📥 Install")
            self.install_monitor_btn.setObjectName("installHWMonBtn")
            self.install_monitor_btn.setFixedSize(70, 30)
            self.install_monitor_btn.setCursor(Qt.PointingHandCursor)
            self.install_monitor_btn.setStyleSheet("""
                QPushButton {
                    background: #526D82; color: #DDE6ED; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #9DB2BF; color: #27374D; }
            """)
            self.install_monitor_btn.setToolTip("Install LibreHardwareMonitor for temperature monitoring")
            self.install_monitor_btn.clicked.connect(self._install_librehwmon)
            install_col.addWidget(self.install_monitor_btn, alignment=Qt.AlignCenter)
            health_row.addLayout(install_col)
        else:
            # Installed - show Start button to launch as admin
            start_col = QVBoxLayout()
            start_col.setSpacing(2)
            self.start_monitor_btn = QPushButton("Start")
            self.start_monitor_btn.setObjectName("startHWMonBtn")
            self.start_monitor_btn.setFixedSize(70, 30)
            self.start_monitor_btn.setCursor(Qt.PointingHandCursor)
            self.start_monitor_btn.setStyleSheet("""
                QPushButton {
                    background: #4ade80; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #22c55e; }
            """)
            self.start_monitor_btn.setToolTip("Choose and launch hardware monitor (LibreHardwareMonitor or HWiNFO)")
            self.start_monitor_btn.clicked.connect(self._show_hwmon_selection_dialog)
            start_col.addWidget(self.start_monitor_btn, alignment=Qt.AlignCenter)
            health_row.addLayout(start_col)
        
        health_widget = QWidget()
        health_widget.setObjectName("healthWidget")
        health_widget.setLayout(health_row)
        health_card.addWidget(health_widget)
        grid.addWidget(health_card, 3, 0)  # Single column, Fan card beside it
        
        # Fan Speed card (beside Health)
        fan_card = StatsCard("Fan Speed")
        fan_card.setObjectName("fanSpeedCard")
        fan_card.setMaximumHeight(125)
        
        fan_row = QHBoxLayout()
        fan_row.setSpacing(15)
        fan_row.setContentsMargins(5, 5, 5, 5)
        
        # CPU Fan Section
        cpu_fan_box = QVBoxLayout()
        cpu_fan_box.setSpacing(2)
        cpu_fan_header = QLabel("🌀 CPU")
        cpu_fan_header.setObjectName("cpuFanHeader")
        cpu_fan_header.setStyleSheet("color: #60a5fa; font-size: 11px; font-weight: bold; background: transparent;")
        cpu_fan_header.setAlignment(Qt.AlignCenter)
        
        self.cpu_fan_value = QLabel("-- RPM")
        self.cpu_fan_value.setObjectName("cpuFanValue")
        self.cpu_fan_value.setStyleSheet("color: #22d3ee; font-size: 13px; font-weight: 600; background: transparent;")
        self.cpu_fan_value.setAlignment(Qt.AlignCenter)
        
        cpu_fan_box.addWidget(cpu_fan_header)
        cpu_fan_box.addWidget(self.cpu_fan_value)
        fan_row.addLayout(cpu_fan_box)
        
        # GPU Fan Section
        gpu_fan_box = QVBoxLayout()
        gpu_fan_box.setSpacing(2)
        gpu_fan_header = QLabel("🌀 GPU")
        gpu_fan_header.setObjectName("gpuFanHeader")
        gpu_fan_header.setStyleSheet("color: #a78bfa; font-size: 11px; font-weight: bold; background: transparent;")
        gpu_fan_header.setAlignment(Qt.AlignCenter)
        
        self.gpu_fan_value = QLabel("-- RPM")
        self.gpu_fan_value.setObjectName("gpuFanValue")
        self.gpu_fan_value.setStyleSheet("color: #c084fc; font-size: 13px; font-weight: 600; background: transparent;")
        self.gpu_fan_value.setAlignment(Qt.AlignCenter)
        
        gpu_fan_box.addWidget(gpu_fan_header)
        gpu_fan_box.addWidget(self.gpu_fan_value)
        fan_row.addLayout(gpu_fan_box)
        
        # System/Chassis Fan Section
        sys_fan_box = QVBoxLayout()
        sys_fan_box.setSpacing(2)
        sys_fan_header = QLabel("🌀 SYS")
        sys_fan_header.setObjectName("sysFanHeader")
        sys_fan_header.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold; background: transparent;")
        sys_fan_header.setAlignment(Qt.AlignCenter)
        
        self.sys_fan_value = QLabel("-- RPM")
        self.sys_fan_value.setObjectName("sysFanValue")
        self.sys_fan_value.setStyleSheet("color: #86efac; font-size: 13px; font-weight: 600; background: transparent;")
        self.sys_fan_value.setAlignment(Qt.AlignCenter)
        
        sys_fan_box.addWidget(sys_fan_header)
        sys_fan_box.addWidget(self.sys_fan_value)
        fan_row.addLayout(sys_fan_box)
        
        fan_widget = QWidget()
        fan_widget.setObjectName("fanWidget")
        fan_widget.setLayout(fan_row)
        fan_card.addWidget(fan_widget)
        grid.addWidget(fan_card, 3, 1)
        
        return container
    
    def _enforce_chart_y_range(self, chart, min_val: float, max_val: float):
        """Enforce Y-axis range on chart (prevents View All from changing it)."""
        # Block signals to avoid recursion
        chart.blockSignals(True)
        chart.setYRange(min_val, max_val, padding=0)
        chart.blockSignals(False)
    
    def _setup_mutual_exclusive_drag(self, chart):
        """Setup mutual exclusive X/Y axis dragging for a chart.
        When dragging starts, detect direction and lock the other axis."""
        chart.setMouseEnabled(x=True, y=True)  # Enable both axes
        chart._drag_axis = None  # Track which axis is being dragged
        chart._drag_start_pos = None
        
        # Store original mousePressEvent and mouseMoveEvent
        original_mouse_press = chart.getPlotItem().vb.mousePressEvent
        original_mouse_move = chart.getPlotItem().vb.mouseDragEvent
        original_mouse_release = chart.getPlotItem().vb.mouseReleaseEvent
        
        def custom_drag_event(ev, axis=None):
            if ev.isStart():
                chart._drag_start_pos = ev.buttonDownPos()
                chart._drag_axis = None
            elif chart._drag_start_pos is not None and chart._drag_axis is None:
                # Determine drag direction based on movement
                delta = ev.pos() - chart._drag_start_pos
                if abs(delta.x()) > abs(delta.y()) * 1.5:
                    chart._drag_axis = 'x'
                    chart.setMouseEnabled(x=True, y=False)
                    # Pause auto-scroll for THIS chart only when user drags X-axis
                    self._pause_auto_scroll_for_chart(chart)
                elif abs(delta.y()) > abs(delta.x()) * 1.5:
                    chart._drag_axis = 'y'
                    chart.setMouseEnabled(x=False, y=True)
            
            if ev.isFinish():
                # Check if user scrolled to view head ONLY when drag finishes
                if chart._drag_axis == 'x':
                    # Get the history length for this chart
                    history_len = self._get_chart_history_len(chart)
                    self._check_auto_scroll_from_view(chart, history_len)
                chart._drag_axis = None
                chart._drag_start_pos = None
                chart.setMouseEnabled(x=True, y=True)  # Reset to both enabled
            
            original_mouse_move(ev, axis)
        
        chart.getPlotItem().vb.mouseDragEvent = custom_drag_event
    
    def _apply_style(self):
        """Apply main panel styling."""
        self.setStyleSheet("""
            QWidget#HardwarePanelWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f0f1a);
            }
        """)
    
    def _on_interval_changed(self, value: int):
        """Handle update interval change."""
        self.monitor.set_update_interval(value)
        self._update_timer.setInterval(value)
        print(f"[Hardware] Update interval changed to {value}ms")
    
    def _update_stats(self):
        """Update all stats from hardware monitor."""
        try:
            snapshot = self.monitor.get_snapshot()
            
            # RAM
            ram = snapshot["ram"]
            ram_percent = ram["percent"]
            
            # Update RAM gauge (RAM Cleaner sub-page)
            if hasattr(self, 'ram_gauge'):
                self.ram_gauge.setValue(ram_percent)
                self.ram_gauge.setSubtitle(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update overview RAM gauge (Quick Setup page)
            if hasattr(self, 'overview_ram_gauge'):
                self.overview_ram_gauge.setValue(ram_percent)
                self.overview_ram_gauge.setSubtitle(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update RAM bar if exists
            if hasattr(self, 'ram_bar'):
                self.ram_bar.setValue(ram_percent)
            
            # Update RAM usage bar (Booster page)
            if hasattr(self, 'ram_usage_bar'):
                self.ram_usage_bar.setValue(ram_percent)
            
            # Only update before_value if not cleaning and widget exists
            if not getattr(self, '_is_cleaning', False):
                if hasattr(self, 'before_value'):
                    self.before_value.setText(f"{ram['used']:.1f} GB / {ram['percent']:.0f}%")
                    # Estimate after cleanup (~15% of used RAM typically freed)
                    estimated_freed = ram['used'] * 0.15
                    estimated_after = ram['used'] - estimated_freed
                    estimated_percent = (estimated_after / ram['total']) * 100 if ram['total'] > 0 else 0
                    if hasattr(self, 'after_value'):
                        self.after_value.setText(f"~{estimated_after:.1f} GB / {estimated_percent:.0f}%")
            
            if hasattr(self, 'free_label'):
                self.free_label.setText(f"Free: {ram['free']:.1f} GB")
            
            # Update RAM stats label (Total/Used/Free) - RAM Cleaner left panel
            if hasattr(self, 'ram_stats_label'):
                self.ram_stats_label.setText(f"Total: {ram['total']:.1f} GB\nUsed: {ram['used']:.1f} GB\nFree: {ram['free']:.1f} GB")
            
            # Update Quick Setup RAM stats label (used / total format)
            if hasattr(self, 'qs_ram_stats_label'):
                self.qs_ram_stats_label.setText(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # Update RAM chart (append only, auto-scroll)
            self._ram_history.append(ram_percent)
            if hasattr(self, 'ram_curve'):
                self.ram_curve.setData(self._ram_history)
            # Auto-scroll X-axis to show last _chart_display_length points (only if not manually scrolling)
            if self._chart_auto_scroll['ram'] and hasattr(self, 'ram_chart'):
                x_max = len(self._ram_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.ram_chart.setXRange(x_min, x_max, padding=0)
            # Update leading edge text position and value
            if hasattr(self, 'ram_leading_text'):
                self.ram_leading_text.setText(f'{ram_percent:.0f}%')
                self.ram_leading_text.setPos(len(self._ram_history) - 1, ram_percent)
            if hasattr(self, 'ram_percent_label'):
                self.ram_percent_label.setText(f"{ram_percent:.0f}%")
            if hasattr(self, 'ram_stats_label'):
                self.ram_stats_label.setText(f"{ram['used']:.1f} GB / {ram['total']:.1f} GB")
            
            # CPU (append only, auto-scroll)
            cpu = snapshot["cpu"]
            cpu_usage = cpu["usage"]
            self._cpu_history.append(cpu_usage)
            self.cpu_curve.setData(self._cpu_history)
            # Auto-scroll X-axis (only if not manually scrolling)
            if self._chart_auto_scroll['cpu']:
                x_max = len(self._cpu_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.cpu_chart.setXRange(x_min, x_max, padding=0)
            # Update leading edge text position and value
            self.cpu_leading_text.setText(f'{cpu_usage:.0f}%')
            self.cpu_leading_text.setPos(len(self._cpu_history) - 1, cpu_usage)
            self.cpu_percent_label.setText(f"{cpu_usage:.0f}%")
            self.cpu_freq_label.setText(f"{cpu.get('freq_ghz', 0):.2f} GHz • {cpu.get('cores', 0)} cores • {cpu.get('threads', 0)} threads")
            
            # Update disk activity chart (append only, auto-scroll)
            disk_io = snapshot.get("disk_io", {})
            read_speed = disk_io.get("read_mbps", 0)
            write_speed = disk_io.get("write_mbps", 0)
            # Calculate disk activity % (normalized to 500 MB/s max for SSD)
            max_speed = 500  # MB/s - typical SSD max
            disk_activity = min(100, (read_speed + write_speed) / max_speed * 100)
            self._disk_usage_history.append(disk_activity)
            self.disk_usage_curve.setData(self._disk_usage_history)
            # Auto-scroll X-axis (only if not manually scrolling)
            if self._chart_auto_scroll['disk']:
                x_max = len(self._disk_usage_history)
                x_min = max(0, x_max - self._chart_display_length)
                self.disk_chart.setXRange(x_min, x_max, padding=0)
            # Update leading edge text position and value
            self.disk_leading_text.setText(f'{disk_activity:.1f}%')
            self.disk_leading_text.setPos(len(self._disk_usage_history) - 1, disk_activity)
            self.disk_percent_label.setText(f"{disk_activity:.1f}%")
            
            # Disk Usage bars (clickable)
            disks = snapshot["disk"]
            
            # Update drive history for all drives
            for disk in disks[:5]:  # Track up to 5 drives
                drive = disk["drive"]
                if drive not in self._drive_history:
                    self._drive_history[drive] = [0] * 60
                    self._active_drives[drive] = False
                    # Assign fixed color for this drive
                    if drive not in self._drive_color_map:
                        color_idx = len(self._drive_color_map)
                        self._drive_color_map[drive] = self._drive_colors[color_idx % len(self._drive_colors)]
                # Update history
                self._drive_history[drive].pop(0)
                self._drive_history[drive].append(disk["percent"])
            
            # Clear and rebuild disk bars
            while self.disk_bars_container.count():
                item = self.disk_bars_container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            for i, disk in enumerate(disks[:5]):  # Show up to 5 drives
                drive = disk["drive"]
                color = self._drive_color_map.get(drive, self._drive_colors[i % len(self._drive_colors)])
                
                # Create display-only bar (not clickable)
                bar_label = QLabel()
                bar_label.setFixedHeight(24)
                bar_label.setProperty("drive", drive)
                bar_label.setProperty("color", color)
                
                percent = disk["percent"]
                used = disk["used"]
                total = disk["total"]
                
                # Style the bar
                bar_label.setStyleSheet(f"""
                    QLabel {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 rgba(255,107,53,0.7), stop:{percent/100} rgba(255,107,53,0.7), 
                            stop:{percent/100 + 0.01} rgba(40,40,40,0.8), stop:1 rgba(40,40,40,0.8));
                        border: 1px solid rgba(100,100,100,0.4);
                        border-radius: 4px;
                        color: #e0e0e0;
                        font-size: 10px;
                        font-weight: 600;
                        padding-left: 8px;
                    }}
                """)
                
                bar_label.setText(f"{drive} {percent:.1f}%        {used:.1f} GB / {total:.1f} GB")
                self.disk_bars_container.addWidget(bar_label)

            
            # Network
            net = snapshot["network"]
            self.download_label.setText(f"↓ {net['download_mbps']:.1f} Mbps")
            self.upload_label.setText(f"↑ {net['upload_mbps']:.1f} Mbps")
            
            # Disk S.M.A.R.T - clear and rebuild
            while self.disk_health_container.count():
                item = self.disk_health_container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Fetch disk details once (WMI query)
            if not self._disk_details_fetched:
                self._disk_details = self.monitor.get_disk_details()
                self._disk_details_fetched = True
            
            for disk in disks:  # Show all drives
                drive_path = disk['drive']
                details = self._disk_details.get(drive_path, {})
                
                # Create a row for each disk with detailed info
                disk_row = QWidget()
                disk_row.setStyleSheet("background: transparent;")
                main_layout = QVBoxLayout()
                main_layout.setContentsMargins(8, 6, 8, 6)
                main_layout.setSpacing(4)
                
                # Row 1: Drive letter + Type badge + Model name
                top_row = QHBoxLayout()
                top_row.setSpacing(8)
                
                drive_label = QLabel(f"{drive_path}")
                drive_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 600; background: transparent;")
                top_row.addWidget(drive_label)
                
                # Health status
                health_label = QLabel("OK")
                health_label.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: 600; background: transparent;")
                top_row.addWidget(health_label)
                
                # Disk type badge (SSD/HDD)
                disk_type = details.get('type', 'HDD')
                type_color = "#22d3ee" if disk_type == 'SSD' else "#fbbf24"
                type_label = QLabel(disk_type)
                type_label.setStyleSheet(f"""
                    color: {type_color}; 
                    font-size: 9px; 
                    font-weight: bold;
                    background: rgba({34 if disk_type == 'SSD' else 251}, {211 if disk_type == 'SSD' else 191}, {238 if disk_type == 'SSD' else 36}, 0.2);
                    padding: 1px 4px;
                    border-radius: 3px;
                """)
                top_row.addWidget(type_label)
                
                # File system
                fstype = disk.get('fstype', 'NTFS')
                fstype_label = QLabel(f"[{fstype}]")
                fstype_label.setStyleSheet("color: #60a5fa; font-size: 9px; background: transparent;")
                top_row.addWidget(fstype_label)
                
                top_row.addStretch()
                
                # Usage percentage (right side)
                usage_pct = disk.get('percent', 0)
                usage_color = "#4ade80" if usage_pct < 70 else "#f97316" if usage_pct < 90 else "#ef4444"
                usage_label = QLabel(f"{usage_pct:.0f}%")
                usage_label.setStyleSheet(f"color: {usage_color}; font-size: 11px; font-weight: 600; background: transparent;")
                top_row.addWidget(usage_label)
                
                top_widget = QWidget()
                top_widget.setLayout(top_row)
                top_widget.setStyleSheet("background: transparent;")
                main_layout.addWidget(top_widget)
                
                # Row 2: Model name (truncated if too long)
                model = details.get('model', 'Unknown')
                if len(model) > 40:
                    model = model[:37] + "..."
                model_label = QLabel(f"{model}")
                model_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
                main_layout.addWidget(model_label)
                
                # Row 3: Progress bar + Size info
                bar_row = QHBoxLayout()
                bar_row.setSpacing(10)
                
                bar = QProgressBar()
                bar.setFixedHeight(6)
                bar.setValue(int(usage_pct))
                bar.setTextVisible(False)
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background: rgba(60, 60, 60, 0.5);
                        border-radius: 3px;
                        border: none;
                    }}
                    QProgressBar::chunk {{
                        background: {usage_color};
                        border-radius: 3px;
                    }}
                """)
                bar_row.addWidget(bar, stretch=1)
                
                # Size: Used / Total (Free)
                free_gb = disk.get('free', 0)
                total_gb = disk.get('total', 0)
                used_gb = disk.get('used', 0)
                size_label = QLabel(f"{used_gb:.0f}/{total_gb:.0f} GB ({free_gb:.0f} free)")
                size_label.setStyleSheet("color: #aaaaaa; font-size: 9px; background: transparent;")
                bar_row.addWidget(size_label)
                
                bar_widget = QWidget()
                bar_widget.setLayout(bar_row)
                bar_widget.setStyleSheet("background: transparent;")
                main_layout.addWidget(bar_widget)
                
                disk_row.setLayout(main_layout)
                self.disk_health_container.addWidget(disk_row)
            
            # Temps and Hardware Stats from LHM
            temps = snapshot["temps"]
            cpu_temp = temps.get("cpu_temp", 0)
            gpu_temp = temps.get("gpu_temp", 0)
            cpu_load = temps.get("cpu_load", 0)
            gpu_load = temps.get("gpu_load", 0)
            fan_speed = temps.get("fan_speed", 0)
            power = temps.get("power", 0)
            
            # CPU Temp
            if cpu_temp > 0:
                self.cpu_temp_value.setText(f"{cpu_temp:.0f}°C")
                color = "#4ade80" if cpu_temp < 70 else "#f97316" if cpu_temp < 85 else "#ef4444"
                self.cpu_temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;")
            
            # CPU Load
            if cpu_load > 0:
                self.cpu_load_value.setText(f"{cpu_load:.0f}%")
                color = "#60a5fa" if cpu_load < 80 else "#f97316" if cpu_load < 95 else "#ef4444"
                self.cpu_load_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # GPU Temp
            if gpu_temp > 0:
                self.gpu_temp_value.setText(f"{gpu_temp:.0f}°C")
                color = "#4ade80" if gpu_temp < 75 else "#f97316" if gpu_temp < 90 else "#ef4444"
                self.gpu_temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;")
            
            # GPU Load
            if gpu_load > 0:
                self.gpu_load_value.setText(f"{gpu_load:.0f}%")
                color = "#60a5fa" if gpu_load < 80 else "#f97316" if gpu_load < 95 else "#ef4444"
                self.gpu_load_value.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            
            # Fan Speed (now in separate Fan Speed card)
            if fan_speed > 0:
                self.cpu_fan_value.setText(f"{fan_speed:.0f} RPM")
                self.gpu_fan_value.setText("N/A")  # Requires NVML for NVIDIA
                self.sys_fan_value.setText("N/A")  # Not available via LHM
            else:
                self.cpu_fan_value.setText("-- RPM")
                self.gpu_fan_value.setText("-- RPM")
                self.sys_fan_value.setText("-- RPM")
            
            # Power
            if power > 0:
                self.power_value.setText(f"{power:.0f}W")
                color = "#fbbf24" if power < 45 else "#f97316" if power < 65 else "#ef4444"
                self.power_value.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 500; background: transparent;")
        
        
            # Auto-refresh Processes list every 3 seconds (6 intervals at 500ms)
            if not hasattr(self, '_processes_refresh_counter'):
                self._processes_refresh_counter = 0
            self._processes_refresh_counter += 1
            if self._processes_refresh_counter >= 6:  # Every 3 seconds
                self._processes_refresh_counter = 0
                if hasattr(self, '_current_ram_tab') and self._current_ram_tab == 1:
                    self._populate_processes_tab()
            
            # Auto-refresh Services status every 5 seconds (10 intervals at 500ms)
            if not hasattr(self, '_services_refresh_counter'):
                self._services_refresh_counter = 0
            self._services_refresh_counter += 1
            if self._services_refresh_counter >= 10:  # Every 5 seconds
                self._services_refresh_counter = 0
                # Refresh if Basic (tab 2) or Advanced (tab 3) Services tab is active
                if hasattr(self, '_current_ram_tab') and self._current_ram_tab in [2, 3]:
                    self._refresh_services_status()
        
        except Exception as e:
            print(f"[Hardware] Update error: {e}")
    

    
    def _toggle_custom_mode(self):
        """Toggle custom cleaning mode on/off."""
        self._custom_mode_active = not self._custom_mode_active
        self._update_custom_mode_style()
        print(f"[Hardware] Custom mode: {'ON' if self._custom_mode_active else 'OFF'}")
    
    def _update_custom_mode_style(self):
        """Update Custom button styling based on active state."""
        if self._custom_mode_active:
            self.custom_mode_btn.setStyleSheet("""
                QPushButton#customModeButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                    color: #ffffff;
                    border: none;
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton#customModeButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7B26, stop:1 #FDC933);
                }
            """)
            self.custom_mode_btn.setText("Custom Preset")
        else:
            self.custom_mode_btn.setStyleSheet("""
                QPushButton#customModeButton {
                    background: rgba(60, 60, 70, 0.8);
                    color: #aaaaaa;
                    border: 1px solid rgba(100, 100, 100, 0.3);
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton#customModeButton:hover {
                    background: rgba(80, 80, 90, 0.9);
                    color: #dddddd;
                    border-color: rgba(255, 91, 6, 0.5);
                }
            """)
            self.custom_mode_btn.setText("Custom Preset")
        
        # Throttled check for hardware monitor running status (every 5 updates)
        self._hwmon_check_counter += 1
        if self._hwmon_check_counter >= 5:
            self._hwmon_check_counter = 0
            self._update_hwmon_button_status()
    
    def _clean_ram(self):
        """Clean RAM and show results."""
        from PySide6.QtWidgets import QApplication
        
        self._is_cleaning = True  # Flag to prevent before_value updates
        self.clean_btn.setText("Cleaning...")
        self.clean_btn.setEnabled(False)
        
        # Stop timer and process any pending events
        self._update_timer.stop()
        QApplication.processEvents()  # Flush pending timer callbacks
        
        # Get before stats and immediately display it
        before_ram = self.monitor.get_ram_info()
        before_used = before_ram['used']
        before_percent = before_ram['percent']
        self.before_value.setText(f"{before_used:.1f} GB / {before_percent:.0f}%")
        print(f"[Hardware] Before: {before_used:.2f} GB ({before_percent:.0f}%)")
        
        # Apply essential optimizations ONLY if Custom mode is ON
        if self._custom_mode_active:
            try:
                opt_results = self._apply_essential_optimizations()
                if opt_results:
                    print(f"[Hardware] Custom mode ON - Essential optimizations applied: {list(opt_results.keys())}")
            except Exception as e:
                print(f"[Hardware] Essential optimizations error: {e}")
        else:
            print("[Hardware] Custom mode OFF - Skipping essential optimizations")
        
        # Clean RAM (existing monitor method)
        result = self.monitor.clean_ram()
        
        # Get after stats
        after_ram = self.monitor.get_ram_info()
        after_used = after_ram['used']
        after_percent = after_ram['percent']
        print(f"[Hardware] After: {after_used:.2f} GB ({after_percent:.0f}%)")
        
        # Update UI
        cleaned = result.get("processes_cleaned", 0)
        freed = max(0, before_used - after_used)
        
        self.after_value.setText(f"{after_used:.1f} GB / {after_percent:.0f}%")
        
        # Reset button
        self.clean_btn.setText(f"Cleaned! ({freed:.2f} GB freed)")
        
        # Resume timer after 10 seconds
        def _resume_timer():
            self._is_cleaning = False
            self.clean_btn.setText("Clean RAM")
            self.clean_btn.setEnabled(True)
            self.after_value.setText("Estimated")  # Reset after value
            self._update_timer.start(self.monitor.update_interval_ms)
        
        QTimer.singleShot(10000, _resume_timer)
        
        print(f"[Hardware] RAM cleaned: {cleaned} processes, ~{freed:.2f} GB freed")
    
    def showEvent(self, event):
        """Start updates when visible."""
        super().showEvent(event)
        if not self._update_timer.isActive():
            self._update_timer.start(self.monitor.update_interval_ms)
    
    def hideEvent(self, event):
        """Stop updates when hidden."""
        super().hideEvent(event)
        self._update_timer.stop()
    
    def _install_librehwmon(self):
        """Download and install hardware monitoring tool (LHM or HWiNFO)."""
        try:
            from PySide6.QtWidgets import QProgressDialog, QMessageBox, QInputDialog
            from integrations.tools_downloader import (
                download_librehwmon, LIBREHWMON_DIR,
                download_hwinfo, HWINFO_DIR
            )
            
            # Show choice dialog
            items = ["LibreHardwareMonitor (~2MB, WMI support)", "HWiNFO Portable (~5MB, more accurate)"]
            item, ok = QInputDialog.getItem(
                self, "Choose Hardware Monitor",
                "Select which hardware monitor to install:",
                items, 0, False
            )
            
            if not ok:
                return
            
            # Determine which tool to download
            if "HWiNFO" in item:
                tool_name = "HWiNFO Portable"
                download_func = download_hwinfo
                install_dir = HWINFO_DIR
                note = "Remember to enable 'Shared Memory Support' in HWiNFO settings for real-time data."
            else:
                tool_name = "LibreHardwareMonitor"
                download_func = download_librehwmon
                install_dir = LIBREHWMON_DIR
                note = "LibreHardwareMonitor requires running as Administrator for best results."
            
            # Show progress dialog
            progress = QProgressDialog(f"Downloading {tool_name}...", "Cancel", 0, 100, self)
            progress.setWindowTitle(f"Installing {tool_name}")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()
            
            # State for thread communication
            state = {"downloaded": 0, "total": 0, "done": False, "success": False, "error": ""}
            
            def on_progress(downloaded: int, total: int):
                state["downloaded"] = downloaded
                state["total"] = total
            
            def do_download():
                success, error = download_func(on_progress)
                state["success"] = success
                state["error"] = error or ""
                state["done"] = True
            
            # Start download in thread
            import threading
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
            
            # Poll for completion
            from PySide6.QtWidgets import QApplication
            import time
            while not state["done"]:
                QApplication.processEvents()
                if progress.wasCanceled():
                    break
                if state["total"] > 0:
                    percent = int((state["downloaded"] / state["total"]) * 100)
                    progress.setValue(percent)
                    progress.setLabelText(f"Downloading... {state['downloaded'] // 1024} KB / {state['total'] // 1024} KB")
                time.sleep(0.05)
            
            progress.close()
            
            if state["success"]:
                # Update Install button to Start button
                if hasattr(self, 'install_monitor_btn') and self.install_monitor_btn:
                    self.install_monitor_btn.setText("▶️ Start")
                    self.install_monitor_btn.setStyleSheet("""
                        QPushButton {
                            background: #4ade80; color: #1a1a2e; border: none; 
                            border-radius: 6px; font-size: 10px; font-weight: 600;
                        }
                        QPushButton:hover { background: #22c55e; }
                    """)
                    self.install_monitor_btn.setToolTip("Launch LibreHardwareMonitor as Administrator")
                    try:
                        self.install_monitor_btn.clicked.disconnect()
                    except RuntimeError:
                        pass
                    self.install_monitor_btn.clicked.connect(self._start_librehwmon)
                    # Update internal state
                    self._hwmon_available = True
                    self._librehwmon_available = True
                
                QMessageBox.information(self, "Download Complete", 
                    f"{tool_name} installed to:\n{install_dir}\n\n"
                    f"Click 'Start' to launch the hardware monitor.\n\n"
                    f"Note: {note}")
            elif not progress.wasCanceled():
                QMessageBox.critical(self, "Download Failed", f"Failed to install {tool_name}:\n{state['error']}")
        
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Download error: {e}")
    
    def _show_hwmon_selection_dialog(self):
        """Show dialog to select and launch/install hardware monitor (LHM or HWiNFO)."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
        from PySide6.QtCore import Qt
        
        try:
            from integrations.tools_downloader import (
                is_librehwmon_available, is_hwinfo_available,
                get_librehwmon_path, get_hwinfo_path, get_hwinfo32_path
            )
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", "Could not load tools_downloader module.")
            return
        
        # Check what's installed
        lhm_installed = is_librehwmon_available()
        hwinfo_installed = is_hwinfo_available()
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Hardware Monitor")
        dialog.setFixedSize(320, 220)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a2e; }
            QLabel { color: #e0e0e0; font-size: 12px; }
            QPushButton {
                background: #333; color: #e0e0e0; border: 1px solid #555;
                border-radius: 6px; padding: 10px 16px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #444; border-color: #FF5B06; }
            QPushButton:disabled { background: #222; color: #666; }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Select Hardware Monitor")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FF5B06;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Choose a hardware monitor to get temperature, fan speed, and power data.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        # Recommendation note
        recommend = QLabel("We recommend using Libre because it's the most optimal for now.")
        recommend.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        recommend.setWordWrap(True)
        recommend.setAlignment(Qt.AlignCenter)
        layout.addWidget(recommend)
        
        layout.addSpacing(5)
        
        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        # LibreHardwareMonitor button
        lhm_btn = QPushButton("LibreHardwareMonitor" if lhm_installed else "Download LHM")
        if lhm_installed:
            lhm_btn.setStyleSheet("background: #FF5B06; color: #fff; border: none; border-radius: 6px; padding: 10px 16px; font-size: 9px; font-weight: 600;")
        btn_row.addWidget(lhm_btn)
        lhm_btn.clicked.connect(lambda: self._handle_hwmon_selection(dialog, "lhm", lhm_installed))
        
        # HWiNFO button  
        hwinfo_btn = QPushButton("HWiNFO" if hwinfo_installed else "Download HWiNFO")
        if hwinfo_installed:
            hwinfo_btn.setStyleSheet("background: #FF5B06; color: #fff; border: none; border-radius: 6px; padding: 10px 16px; font-size: 9px; font-weight: 600;")
        hwinfo_btn.clicked.connect(lambda: self._handle_hwmon_selection(dialog, "hwinfo", hwinfo_installed))
        btn_row.addWidget(hwinfo_btn)
        
        layout.addLayout(btn_row)
        
        # Status label
        status = QLabel("")
        status.setStyleSheet("color: #888; font-size: 10px;")
        status.setAlignment(Qt.AlignCenter)
        if lhm_installed:
            status.setText("✓ LibreHardwareMonitor installed")
        elif hwinfo_installed:
            status.setText("✓ HWiNFO installed")
        else:
            status.setText("No hardware monitor installed")
        layout.addWidget(status)
        
        dialog.exec()
    
    def _handle_hwmon_selection(self, dialog, tool: str, is_installed: bool):
        """Handle hardware monitor selection - install or launch."""
        dialog.close()
        
        if is_installed:
            # Launch the tool
            self._launch_hwmon(tool)
        else:
            # Install the tool
            self._install_hwmon(tool)
    
    def _launch_hwmon(self, tool: str):
        """Launch the specified hardware monitor as admin."""
        import os
        import ctypes
        
        try:
            from integrations.tools_downloader import (
                get_librehwmon_path, get_hwinfo_path, get_hwinfo32_path
            )
            
            if tool == "lhm":
                exe_path = get_librehwmon_path()
                tool_name = "LibreHardwareMonitor"
            else:
                # Prefer 64-bit, fallback to 32-bit
                if os.path.exists(get_hwinfo_path()):
                    exe_path = get_hwinfo_path()
                else:
                    exe_path = get_hwinfo32_path()
                tool_name = "HWiNFO"
                # Auto-enable shared memory
                self._enable_hwinfo_shared_memory(exe_path)
            
            if not exe_path or not os.path.exists(exe_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", f"{tool_name} executable not found.")
                return
            
            # Launch as admin
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, None,
                os.path.dirname(exe_path), 1
            )
            
            if result > 32:
                print(f"[Hardware] {tool_name} started as Administrator")
                btn = getattr(self, 'start_monitor_btn', None)
                if btn:
                    btn.setText("✓ Launched")
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(3000, lambda: btn.setText("Start"))
            else:
                print(f"[Hardware] Failed to start {tool_name} (code: {result})")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to launch: {e}")
    
    def _install_hwmon(self, tool: str):
        """Install the specified hardware monitor."""
        from PySide6.QtWidgets import QProgressDialog, QMessageBox
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication
        import threading
        
        try:
            from integrations.tools_downloader import download_librehwmon, download_hwinfo
            
            tool_name = "LibreHardwareMonitor" if tool == "lhm" else "HWiNFO"
            download_func = download_librehwmon if tool == "lhm" else download_hwinfo
            
            # Show progress dialog
            progress = QProgressDialog(f"Downloading {tool_name}...", "Cancel", 0, 100, self)
            progress.setWindowTitle(f"Installing {tool_name}")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()
            
            # Shared state for thread communication
            state = {"done": False, "success": False, "error": "", "progress": 0}
            
            def on_progress(downloaded, total):
                # Just update state, don't touch UI from here
                if total > 0:
                    state["progress"] = int(downloaded / total * 100)
            
            def download_thread():
                try:
                    download_func(on_progress)
                    state["success"] = True
                except Exception as e:
                    state["error"] = str(e)
                state["done"] = True
            
            thread = threading.Thread(target=download_thread, daemon=True)
            thread.start()
            
            # Poll for completion and update UI from main thread
            def check_done():
                # Update progress from main thread
                progress.setValue(state["progress"])
                QApplication.processEvents()  # Keep UI responsive
                
                if progress.wasCanceled():
                    state["done"] = True
                    state["error"] = "Cancelled by user"
                    progress.close()
                    return
                
                if state["done"]:
                    progress.close()
                    if state["success"]:
                        QMessageBox.information(self, "Success", 
                            f"{tool_name} installed successfully!\n\nPlease restart the launcher to use it.")
                    else:
                        QMessageBox.critical(self, "Error", f"Download failed: {state['error']}")
                else:
                    QTimer.singleShot(100, check_done)
            
            check_done()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Install error: {e}")
    
    def _start_librehwmon(self):
        """Launch hardware monitor as Administrator (LibreHardwareMonitor or HWiNFO)."""
        try:
            from integrations.tools_downloader import (
                get_librehwmon_path, get_hwinfo_path, get_hwinfo32_path,
                is_librehwmon_available, is_hwinfo_available
            )
            import ctypes
            import os
            
            # Determine which tool to launch
            exe_path = None
            tool_name = None
            
            if is_librehwmon_available():
                exe_path = get_librehwmon_path()
                tool_name = "LibreHardwareMonitor"
            elif is_hwinfo_available():
                # Prefer 64-bit, fallback to 32-bit
                if os.path.exists(get_hwinfo_path()):
                    exe_path = get_hwinfo_path()
                else:
                    exe_path = get_hwinfo32_path()
                tool_name = "HWiNFO"
            
            if not exe_path or not os.path.exists(exe_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", 
                    "No hardware monitor found.\nPlease install LibreHardwareMonitor or HWiNFO first.")
                return
            
            # Launch as admin using ShellExecuteW with 'runas' verb
            # For HWiNFO: Auto-enable Shared Memory Support in config
            if tool_name == "HWiNFO":
                self._enable_hwinfo_shared_memory(exe_path)
            
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, None, 
                os.path.dirname(exe_path), 1  # SW_SHOWNORMAL
            )
            
            if result > 32:
                # Success - update button temporarily to show it launched
                btn = getattr(self, 'start_monitor_btn', None) or getattr(self, 'install_monitor_btn', None)
                if btn:
                    btn.setText("✓ Launched")
                    btn.setStyleSheet("""
                        QPushButton {
                            background: #22c55e; color: #1a1a2e; border: none; 
                            border-radius: 6px; font-size: 10px; font-weight: 600;
                        }
                    """)
                    # Reset button after 3 seconds so user can launch again if needed
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(3000, lambda: self._reset_monitor_btn(btn))
                print(f"[Hardware] {tool_name} started as Administrator")
            else:
                # User cancelled UAC or error
                print(f"[Hardware] Failed to start {tool_name} (code: {result})")
        
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to start hardware monitor:\n{e}")
    
    def _reset_monitor_btn(self, btn):
        """Reset monitor button back to Start state."""
        if btn:
            btn.setText("▶️ Start")
            btn.setStyleSheet("""
                QPushButton {
                    background: #4ade80; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #22c55e; }
            """)
            btn.setEnabled(True)
    
    def _enable_hwinfo_shared_memory(self, exe_path: str):
        """Auto-enable Shared Memory Support in HWiNFO config file.
        
        HWiNFO stores settings in HWiNFO64.INI or HWiNFO32.INI in the same directory.
        This modifies the config to enable shared memory so users don't have to manually configure it.
        """
        import os
        import configparser
        
        try:
            # HWiNFO config is in same dir as exe, named HWiNFO64.INI or HWiNFO32.INI
            exe_dir = os.path.dirname(exe_path)
            exe_name = os.path.basename(exe_path)
            
            # Determine INI file name based on exe
            if "64" in exe_name:
                ini_name = "HWiNFO64.INI"
            else:
                ini_name = "HWiNFO32.INI"
            
            ini_path = os.path.join(exe_dir, ini_name)
            
            # Read existing config or create new
            config = configparser.ConfigParser()
            if os.path.exists(ini_path):
                config.read(ini_path)
            
            # Ensure section exists
            if 'Settings' not in config:
                config['Settings'] = {}
            
            # Enable Shared Memory Support (SensorsSM key)
            # Value 1 = enabled
            config['Settings']['SensorsSM'] = '1'
            
            # Write config back
            with open(ini_path, 'w') as f:
                config.write(f)
            
            print(f"[Hardware] HWiNFO Shared Memory enabled in {ini_name}")
        except Exception as e:
            print(f"[Hardware] Could not auto-enable HWiNFO shared memory: {e}")
    
    
    def _is_hwmon_running(self) -> bool:
        """Check if any hardware monitor process is running."""
        try:
            import psutil
            hwmon_processes = ['HWiNFO64.exe', 'HWiNFO32.exe', 'LibreHardwareMonitor.exe']
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] in hwmon_processes:
                    return True
            return False
        except Exception:
            return False
    
    def _update_hwmon_button_status(self):
        """Update hardware monitor button based on running state."""
        btn = getattr(self, 'start_monitor_btn', None) or getattr(self, 'install_monitor_btn', None)
        if not btn:
            return
        
        is_running = self._is_hwmon_running()
        
        if is_running:
            btn.setText("✓ Running")
            btn.setStyleSheet("""
                QPushButton {
                    background: #22c55e; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
            """)
            btn.setEnabled(False)
        else:
            btn.setText("▶️ Start")
            btn.setStyleSheet("""
                QPushButton {
                    background: #4ade80; color: #1a1a2e; border: none; 
                    border-radius: 6px; font-size: 10px; font-weight: 600;
                }
                QPushButton:hover { background: #22c55e; }
            """)
            btn.setEnabled(True)
