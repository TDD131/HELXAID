"""
Network Historical Usage & Timeline Analytics Panel for HELXTATS.
Provides interactive SQLite timeline charts, per-app bandwidth attribution,
peak day summaries, and CSV/JSON export capabilities matching HELXAIRO style.

Component Name: NetworkHistoryPanel
"""

import os
import re
from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QComboBox, QProgressBar, QListWidget, QListWidgetItem, 
    QAbstractItemView, QFileDialog, QMessageBox, QFileIconProvider
)
from PySide6.QtCore import Qt, Signal, QSize, QFileInfo
from PySide6.QtGui import QFont, QIcon, QColor
import pyqtgraph as pg

from NetworkHistoryEngine import (
    get_usage_summary, get_daily_timeline, get_top_apps,
    export_history_to_csv, export_history_to_json, clear_all_network_history
)


class NetworkHistoryPanel(QWidget):
    """
    Historical Network Usage Analytics Panel for HELXTATS.
    
    Component Name: NetworkHistoryPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NetworkHistoryPanel")

        self._active_timeframe = "Last 30 Days"
        self._icon_provider = QFileIconProvider()

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # ── 1. TOP HEADER & CONTROLS ROW ─────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("NetHistHeaderFrame")
        header_frame.setFixedHeight(38)
        header_frame.setStyleSheet("""
            QFrame#NetHistHeaderFrame {
                background: rgba(255, 255, 255, 0.03);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        # Back button
        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("NetHistBackBtn")
        self.back_btn.setFixedSize(30, 26)
        self.back_btn.setIcon(QIcon(back_icon_path))
        self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Network Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#NetHistBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                margin: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#NetHistBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("NETWORK USAGE & TIMELINE ANALYTICS")
        title_lbl.setObjectName("NetHistHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron'; font-size: 13px; font-weight: bold; background: transparent;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        # Timeframe Dropdown
        tf_lbl = QLabel("Range:")
        tf_lbl.setObjectName("netHistRangeLabel")
        tf_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron'; font-size: 11px;")
        h_layout.addWidget(tf_lbl)

        self.tf_combo = QComboBox()
        self.tf_combo.setObjectName("NetHistTimeframeCombo")
        self.tf_combo.addItems(["Last 7 Days", "Last 30 Days", "All Time"])
        self.tf_combo.setCurrentText(self._active_timeframe)
        self.tf_combo.setFixedWidth(130)
        self.tf_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border-radius: 6px;
                padding: 4px 10px;
                font-family: 'Orbitron';
                font-size: 11px;
            }
            QComboBox:hover {
                background-color: rgba(40, 40, 40, 0.95);
                color: #ffffff;
            }
        """)
        self.tf_combo.currentTextChanged.connect(self._on_timeframe_changed)
        h_layout.addWidget(self.tf_combo)

        # Export CSV Button
        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("netHistExportBtn")
        export_btn.setFixedSize(85, 26)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #e0e0e0;
                font-family: 'Orbitron';
                font-size: 10px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #FF5B06;
                color: #ffffff;
            }
        """)
        export_btn.clicked.connect(self._handle_export_csv)
        h_layout.addWidget(export_btn)

        main_layout.addWidget(header_frame)

        # ── 2. HERO SUMMARY METRIC CARDS ─────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self.card_tot, self.lbl_tot_val, self.lbl_tot_sub = self._build_stat_card("TOTAL CONSUMED", "0 GB", "0 Active Apps", "#00E5FF")
        self.card_avg, self.lbl_avg_val, self.lbl_avg_sub = self._build_stat_card("DAILY AVERAGE", "0 GB", "Per Day", "#FF5B06")
        self.card_top, self.lbl_top_val, self.lbl_top_sub = self._build_stat_card("TOP CONSUMER", "None", "0%", "#4ADE80")
        self.card_peak, self.lbl_peak_val, self.lbl_peak_sub = self._build_stat_card("PEAK DAY", "N/A", "0 GB", "#FB923C")

        cards_row.addWidget(self.card_tot)
        cards_row.addWidget(self.card_avg)
        cards_row.addWidget(self.card_top)
        cards_row.addWidget(self.card_peak)
        main_layout.addLayout(cards_row)

        # ── 3. TIMELINE BAR / AREA CHART ─────────────────────
        chart_frame = QFrame()
        chart_frame.setObjectName("NetHistChartFrame")
        chart_frame.setFixedHeight(150)
        chart_frame.setStyleSheet("""
            QFrame#NetHistChartFrame {
                background: rgba(255, 255, 255, 0.02);
                border-radius: 10px;
            }
        """)
        c_layout = QVBoxLayout(chart_frame)
        c_layout.setContentsMargins(12, 8, 12, 8)
        c_layout.setSpacing(4)

        chart_title_row = QHBoxLayout()
        chart_title = QLabel("DAILY CONSUMPTION TIMELINE (GB)")
        chart_title.setObjectName("netHistChartTitle")
        chart_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron'; font-size: 11px; font-weight: bold; background: transparent;")
        chart_title_row.addWidget(chart_title)
        chart_title_row.addStretch()
        c_layout.addLayout(chart_title_row)

        self.timeline_chart = pg.PlotWidget()
        self.timeline_chart.setObjectName("netHistTimelinePlot")
        self.timeline_chart.setBackground(None)
        self.timeline_chart.showGrid(x=False, y=True, alpha=0.15)
        self.timeline_chart.hideAxis('bottom')
        self.timeline_chart.getAxis('left').setStyle(showValues=True)
        self.timeline_chart.getAxis('left').setTextPen(pg.mkPen('#888888'))
        self.timeline_chart.setMouseEnabled(x=False, y=False)
        self.timeline_chart.setMenuEnabled(False)

        pen = pg.mkPen(color=QColor("#00E5FF"), width=2)
        brush = pg.mkBrush(color=QColor(0, 229, 255, 35))
        self.timeline_curve = self.timeline_chart.plot(pen=pen, brush=brush, fillLevel=0)

        c_layout.addWidget(self.timeline_chart)
        main_layout.addWidget(chart_frame)

        # ── 4. PROCESS BREAKDOWN LIST ────────────────────────
        list_frame = QFrame()
        list_frame.setObjectName("NetHistListFrame")
        list_frame.setStyleSheet("""
            QFrame#NetHistListFrame {
                background: rgba(255, 255, 255, 0.02);
                border-radius: 10px;
            }
        """)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(12, 10, 12, 10)
        list_layout.setSpacing(8)

        l_head = QHBoxLayout()
        l_title = QLabel("TOP BANDWIDTH CONSUMING APPLICATIONS")
        l_title.setObjectName("netHistTopAppsTitle")
        l_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron'; font-size: 11px; font-weight: bold; background: transparent;")
        l_head.addWidget(l_title)
        l_head.addStretch()
        list_layout.addLayout(l_head)

        self.apps_list = QListWidget()
        self.apps_list.setObjectName("NetHistAppsList")
        self.apps_list.setStyleSheet("""
            QListWidget#NetHistAppsList {
                background-color: rgba(0, 0, 0, 0.2);
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QListWidget#NetHistAppsList::item {
                background-color: rgba(255, 255, 255, 0.02);
                border-radius: 4px;
                padding: 2px;
                margin-bottom: 3px;
            }
            QListWidget#NetHistAppsList::item:hover {
                background-color: rgba(255, 91, 6, 0.08);
            }
        """)
        self.apps_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.apps_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        list_layout.addWidget(self.apps_list, stretch=1)

        main_layout.addWidget(list_frame, stretch=1)

        self.refresh_data()

    def _build_stat_card(self, title: str, val: str, sub: str, color_hex: str):
        frame = QFrame()
        clean_title = re.sub(r'[^a-zA-Z0-9]', '', title)
        frame.setObjectName(f"netHistStatCard_{clean_title}")
        frame.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.03);
            border-radius: 8px;
            padding: 8px;
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        t_lbl = QLabel(title)
        t_lbl.setObjectName(f"netHistStatTitle_{clean_title}")
        t_lbl.setStyleSheet(f"color: {color_hex}; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; background: transparent;")
        
        v_lbl = QLabel(val)
        v_lbl.setObjectName(f"netHistStatVal_{clean_title}")
        v_lbl.setStyleSheet("color: #ffffff; font-family: 'Orbitron'; font-size: 14px; font-weight: bold; background: transparent;")

        s_lbl = QLabel(sub)
        s_lbl.setObjectName(f"netHistStatSub_{clean_title}")
        s_lbl.setStyleSheet("color: #777777; font-family: 'Orbitron'; font-size: 9px; background: transparent;")

        layout.addWidget(t_lbl)
        layout.addWidget(v_lbl)
        layout.addWidget(s_lbl)
        return frame, v_lbl, s_lbl

    def _on_timeframe_changed(self, text: str):
        self._active_timeframe = text
        self.refresh_data()

    def refresh_data(self):
        """Fetch updated analytics from SQLite and refresh all widgets."""
        summary = get_usage_summary(self._active_timeframe)
        
        # 1. Update Summary Cards
        tot_bytes = summary.get("total_bytes", 0)
        self.lbl_tot_val.setText(self._fmt_bytes(tot_bytes))
        self.lbl_tot_sub.setText(f"{summary.get('active_apps_count', 0)} Active Apps")

        avg_bytes = summary.get("daily_avg_bytes", 0)
        self.lbl_avg_val.setText(self._fmt_bytes(avg_bytes))

        top_name = summary.get("top_app_name", "None")
        top_pct = summary.get("top_app_pct", 0.0)
        self.lbl_top_val.setText(top_name)
        self.lbl_top_sub.setText(f"{self._fmt_bytes(summary.get('top_app_bytes', 0))} ({top_pct}%)")

        peak_str = summary.get("peak_day_str", "N/A")
        peak_bytes = summary.get("peak_day_bytes", 0)
        self.lbl_peak_val.setText(peak_str)
        self.lbl_peak_sub.setText(self._fmt_bytes(peak_bytes))

        # 2. Update Timeline Chart (Last 30 days)
        timeline_pts = get_daily_timeline(30)
        gb_data = [pt["bytes"] / (1024.0 ** 3) for pt in timeline_pts]
        self.timeline_curve.setData(gb_data)

        # 3. Update Apps List
        apps = get_top_apps(self._active_timeframe, limit=25)
        self.apps_list.clear()

        if not apps:
            empty_item = QListWidgetItem(self.apps_list)
            empty_item.setSizeHint(QSize(0, 36))
            lbl = QLabel("No network usage recorded in this timeframe.")
            lbl.setObjectName("netHistEmptyLbl")
            lbl.setStyleSheet("color: #666666; font-family: 'Orbitron'; font-size: 10px; background: transparent;")
            lbl.setAlignment(Qt.AlignCenter)
            self.apps_list.setItemWidget(empty_item, lbl)
            return

        for app in apps:
            item = QListWidgetItem(self.apps_list)
            item.setSizeHint(QSize(0, 36))

            app_id = re.sub(r'[^a-zA-Z0-9]', '', app['name'])
            row_w = QWidget()
            row_w.setObjectName(f"netHistAppRow_{app_id}")
            row_w.setStyleSheet("background: transparent;")
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(8, 2, 8, 2)
            r_lay.setSpacing(12)

            # Name
            name_lbl = QLabel(app["name"])
            name_lbl.setObjectName(f"netHistAppName_{app_id}")
            name_lbl.setFixedWidth(150)
            name_lbl.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 11px;")
            r_lay.addWidget(name_lbl)

            # Progress bar for share
            prog = QProgressBar()
            prog.setObjectName(f"netHistAppProg_{app_id}")
            prog.setFixedHeight(4)
            prog.setTextVisible(False)
            prog.setValue(int(app["percentage"]))
            prog.setStyleSheet("""
                QProgressBar { background-color: #1A1A1A; border: none; border-radius: 2px; }
                QProgressBar::chunk { background: #FF5B06; border-radius: 2px; }
            """)
            r_lay.addWidget(prog, stretch=1)

            # Total Bytes
            bytes_lbl = QLabel(self._fmt_bytes(app["bytes"]))
            bytes_lbl.setObjectName(f"netHistAppBytes_{app_id}")
            bytes_lbl.setFixedWidth(90)
            bytes_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bytes_lbl.setStyleSheet("color: #FDA903; font-family: 'Orbitron'; font-size: 10px; font-weight: bold;")
            r_lay.addWidget(bytes_lbl)

            # Percentage
            pct_lbl = QLabel(f"{app['percentage']:.1f}%")
            pct_lbl.setObjectName(f"netHistAppPct_{app_id}")
            pct_lbl.setFixedWidth(50)
            pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron'; font-size: 10px;")
            r_lay.addWidget(pct_lbl)

            self.apps_list.setItemWidget(item, row_w)

    def _handle_export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Network History to CSV", "network_usage_history.csv", "CSV Files (*.csv)"
        )
        if file_path:
            ok, msg = export_history_to_csv(file_path, self._active_timeframe)
            if ok:
                QMessageBox.information(self, "Export Successful", msg)
            else:
                QMessageBox.warning(self, "Export Error", msg)

    @staticmethod
    def _fmt_bytes(b: int) -> str:
        if b >= 1024 ** 4:
            return f"{b / (1024 ** 4):.2f} TB"
        elif b >= 1024 ** 3:
            return f"{b / (1024 ** 3):.2f} GB"
        elif b >= 1024 ** 2:
            return f"{b / (1024 ** 2):.1f} MB"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"
