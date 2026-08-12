"""
LibreHardwareMonitor Sensor Panel Dialog - High-Tech Interactive Hardware Monitor

Displays live CPU/GPU temperatures, clocks, loads, power wattage, fan speeds,
and storage health in a sleek dark Orbitron PySide6 UI inside HELXAID.

Component Name: LHMSensorPanelDialog
"""

import sys
import os
import math
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap

from core.lhm_wrapper import get_lhm_reader_instance


class SensorCard(QFrame):
    """Card widget for individual hardware metrics."""
    def __init__(self, title: str, unit: str = "", color_hex: str = "#FF5B06", parent=None):
        super().__init__(parent)
        self.setObjectName("SensorCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._unit = unit
        self._color_hex = color_hex

        self.setStyleSheet(f"""
            QFrame#SensorCard {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }}
            QFrame#SensorCard:hover {{
                border-color: {color_hex};
                background: rgba(255, 255, 255, 0.06);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #888888; font-size: 10px; font-weight: 700; font-family: 'Orbitron'; background: transparent;")
        layout.addWidget(self.lbl_title)

        self.lbl_val = QLabel(f"-- {unit}")
        self.lbl_val.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        layout.addWidget(self.lbl_val)

    def set_value(self, val, decimal_places: int = 1):
        if val is None or val == 0:
            self.lbl_val.setText(f"-- {self._unit}".strip())
            return
        if isinstance(val, (int, float)):
            if decimal_places == 0:
                text = f"{int(val)} {self._unit}".strip()
            else:
                text = f"{val:.{decimal_places}f} {self._unit}".strip()
        else:
            text = f"{val} {self._unit}".strip()
        self.lbl_val.setText(text)


class LHMSensorPanelDialog(QDialog):
    """
    High-tech interactive LHM Sensor Monitor Panel Dialog.

    Component Name: LHMSensorPanelDialog
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LHMSensorPanelDialog")
        self.setWindowTitle("HELXAID - LibreHardwareMonitor Panel")
        try:
            from launcher import apply_custom_titlebar
            apply_custom_titlebar(self, "#000000")
        except Exception:
            pass
        self.setMinimumSize(780, 520)
        self.resize(860, 580)
        self.setStyleSheet("QDialog#LHMSensorPanelDialog { background: #121316; color: #e0e0e0; }")

        self._lhm = get_lhm_reader_instance()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # === HEADER ROW ===
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        icon_lbl = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI Icons", "libre.png")
        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("LIBRE HARDWARE MONITOR")
        title_lbl.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: 800; font-family: 'Orbitron'; background: transparent;")
        header_row.addWidget(title_lbl)

        sub_lbl = QLabel("• Live Sensor Feed (100% In-Process Engine)")
        sub_lbl.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 600; font-family: 'Orbitron'; background: transparent;")
        header_row.addWidget(sub_lbl)

        header_row.addStretch()

        self.btn_standalone = QPushButton("LAUNCH STANDALONE WINDOW")
        self.btn_standalone.setObjectName("lhmStandaloneBtn")
        self.btn_standalone.setCursor(Qt.PointingHandCursor)
        self.btn_standalone.setFixedSize(220, 34)
        self.btn_standalone.setStyleSheet("""
            QPushButton#lhmStandaloneBtn {
                background: rgba(255, 91, 6, 0.2);
                color: #FF5B06;
                border: 1px solid rgba(255, 91, 6, 0.5);
                border-radius: 6px;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton#lhmStandaloneBtn:hover {
                background: #FF5B06;
                color: #ffffff;
            }
        """)
        self.btn_standalone.clicked.connect(self._launch_standalone_window)
        header_row.addWidget(self.btn_standalone)

        main_layout.addLayout(header_row)

        # === SENSOR CARDS GRID ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a1a; width: 6px; }
            QScrollBar::handle:vertical { background: #444; border-radius: 3px; }
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # Create cards
        self.cards = {
            "gpu_temp": SensorCard("NVIDIA GPU Temp", "°C", "#ff4757"),
            "hotspot_temp": SensorCard("GPU Hotspot Temp", "°C", "#ff6b81"),
            "vram_temp": SensorCard("VRAM Junction Temp", "°C", "#ffa502"),
            "gpu_power": SensorCard("GPU Power", "W", "#2ed573"),
            "gpu_load": SensorCard("GPU Load", "%", "#1e90ff"),
            "gpu_clock": SensorCard("GPU Core Clock", "MHz", "#70a1ff"),
            "cpu_load": SensorCard("CPU Total Load", "%", "#3742fa"),
            "cpu_power": SensorCard("CPU Package Power", "W", "#7bed9f"),
            "cpu_temp": SensorCard("CPU Temp", "°C", "#eccc68"),
            "fan_speed": SensorCard("Fan Speed", "RPM", "#a4b0be"),
        }

        keys = list(self.cards.keys())
        cols = 3
        for idx, key in enumerate(keys):
            row = idx // cols
            col = idx % cols
            grid.addWidget(self.cards[key], row, col)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        # Polling timer (500ms)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_sensors)
        self._timer.start(500)
        self._update_sensors()

    def _update_sensors(self):
        metrics = self._lhm.read_sensors()
        if not metrics or not metrics.get("available"):
            return

        self.cards["gpu_temp"].set_value(metrics.get("gpu_temp"))
        self.cards["hotspot_temp"].set_value(metrics.get("hotspot_temp"))
        self.cards["vram_temp"].set_value(metrics.get("vram_temp"))
        self.cards["gpu_power"].set_value(metrics.get("gpu_power"))
        self.cards["gpu_load"].set_value(metrics.get("gpu_load"), 0)
        self.cards["gpu_clock"].set_value(metrics.get("gpu_clock"), 0)
        self.cards["cpu_load"].set_value(metrics.get("cpu_load"), 0)
        self.cards["cpu_power"].set_value(metrics.get("cpu_power"))
        self.cards["cpu_temp"].set_value(metrics.get("cpu_temp"))
        self.cards["fan_speed"].set_value(metrics.get("fan_speed"), 0)

    def _launch_standalone_window(self):
        parent_panel = self.parent()
        if parent_panel and hasattr(parent_panel, '_start_librehwmon_standalone'):
            parent_panel._start_librehwmon_standalone()
        else:
            # Fallback launch
            import ctypes, subprocess
            from integrations.tools_downloader import get_librehwmon_path
            exe_path = get_librehwmon_path()
            if exe_path and os.path.exists(exe_path):
                # Terminate any background Session 0 instance first
                try:
                    subprocess.run(["taskkill", "/F", "/IM", "LibreHardwareMonitor.exe"], capture_output=True)
                except Exception:
                    pass
                ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, None, os.path.dirname(exe_path), 1)

    def closeEvent(self, event):
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)
