"""
SniperLoupeOverlay - High-performance optical zoom screen magnifier for tactical shooters.
Component Name: SniperLoupeOverlay
Page Domain: HELXAIR (Crosshair Overlay)

Features:
- Micro-region 60 FPS desktop capture around the active crosshair position.
- Real-time 2.0x to 5.0x optical magnification.
- Circular tactical scope lens or rounded HUD window.
- Tactical Mil-Dot reticles, fine crosshairs, and Orbitron HUD magnification badges.
- Hardware-level click-through via Qt.WA_TransparentForMouseEvents and Win32 WS_EX_TRANSPARENT.
- Prevents recursive screen-capture echo (hall-of-mirrors) using SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE).
- Zero CPU usage when idle (timer stopped).
"""

import os
import sys
import json
import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QBrush, QColor, QPen, QPainterPath, QPixmap,
    QFont, QRadialGradient, QLinearGradient
)

# Win32 API Constants for Click-Through and Capture Exclusion
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def apply_win32_window_attributes(hwnd: int) -> bool:
    """Apply native Windows extended styles for click-through and screen capture exclusion."""
    if not sys.platform.startswith("win"):
        return False
    try:
        user32 = ctypes.windll.user32
        is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8

        if is_64bit and hasattr(user32, "GetWindowLongPtrW"):
            get_wlong = user32.GetWindowLongPtrW
            set_wlong = user32.SetWindowLongPtrW
            get_wlong.restype = ctypes.c_ssize_t
            get_wlong.argtypes = [wintypes.HWND, ctypes.c_int]
            set_wlong.restype = ctypes.c_ssize_t
            set_wlong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        else:
            get_wlong = user32.GetWindowLongW
            set_wlong = user32.SetWindowLongW
            get_wlong.restype = ctypes.c_long
            get_wlong.argtypes = [wintypes.HWND, ctypes.c_int]
            set_wlong.restype = ctypes.c_long
            set_wlong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

        current_style = get_wlong(hwnd, GWL_EXSTYLE)
        target_style = current_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
        set_wlong(hwnd, GWL_EXSTYLE, target_style)

        # SetWindowDisplayAffinity prevents recursive screen grab feedback
        if hasattr(user32, "SetWindowDisplayAffinity"):
            user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

        return True
    except Exception as e:
        print(f"[SniperLoupe] Win32 style/affinity setup error: {e}")
        return False


class SniperLoupeOverlay(QWidget):
    """
    Floating 60 FPS Optical Screen Magnifier Window with Click-Through Transparency.
    Component Name: SniperLoupeOverlay
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SniperLoupeOverlay")

        # Window flags for borderless always-on-top transparent overlay
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Default Settings
        self.settings = {
            "enabled": False,
            "zoom_factor": 3.0,          # 2.0 to 5.0x magnification
            "diameter": 220,             # Lens diameter in pixels (160 to 320)
            "shape": "circle",           # "circle" or "rounded_hud"
            "reticle_type": "mil_dot",    # "mil_dot", "fine_cross", "circle_dot", "none"
            "tint_mode": "clear",        # "clear", "tactical_amber", "cyber_green", "night_vision"
            "show_hud_badge": True,      # Orbitron zoom indicator badge
            "border_color": "#FF5B06",   # Outer scope bezel glow color
            "offset_x": 0,               # Coordinate offset matching crosshair
            "offset_y": 0,               # Coordinate offset matching crosshair
            "trigger_mode": "toggle",    # "toggle" or "hold"
            "hotkey": "f7"               # Global trigger hotkey
        }

        self.is_active = False
        self._win32_configured = False

        # Load persisted settings
        self.load_settings()

        # Update geometry
        d = int(self.settings.get("diameter", 220))
        self.setFixedSize(d, d)
        self._recenter_window()

        # 60 FPS High-Frequency Timer (only runs when active)
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(16)  # ~60 FPS
        self._fps_timer.timeout.connect(self.update)

    def load_settings(self):
        """Load settings from user AppData."""
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID')
        os.makedirs(appdata_dir, exist_ok=True)
        settings_path = os.path.join(appdata_dir, "sniper_loupe_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception as e:
                print(f"[SniperLoupe] Error loading settings: {e}")

    def save_settings(self):
        """Save settings to user AppData."""
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID')
        os.makedirs(appdata_dir, exist_ok=True)
        settings_path = os.path.join(appdata_dir, "sniper_loupe_settings.json")
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"[SniperLoupe] Error saving settings: {e}")

    def update_setting(self, key, value):
        """Update individual setting and adjust overlay properties."""
        self.settings[key] = value
        self.save_settings()

        if key == "diameter":
            d = int(value)
            self.setFixedSize(d, d)
            self._recenter_window()
        elif key in ("offset_x", "offset_y"):
            self._recenter_window()

        if self.is_active:
            self.update()

    def set_offsets(self, offset_x: int, offset_y: int):
        """Synchronize center alignment with the active crosshair position."""
        self.settings["offset_x"] = offset_x
        self.settings["offset_y"] = offset_y
        self._recenter_window()
        if self.is_active:
            self.update()

    def _recenter_window(self):
        """Center the loupe window directly over the crosshair center coordinates."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.geometry()
        cx = geom.x() + geom.width() // 2 + int(self.settings.get("offset_x", 0))
        cy = geom.y() + geom.height() // 2 + int(self.settings.get("offset_y", 0))
        d = int(self.settings.get("diameter", 220))
        self.move(cx - d // 2, cy - d // 2)

    def showEvent(self, event):
        """Ensure native Win32 click-through and affinity are configured on show."""
        super().showEvent(event)
        if not self._win32_configured:
            hwnd = int(self.winId())
            self._win32_configured = apply_win32_window_attributes(hwnd)

    def toggle_loupe(self):
        """Toggle magnification on/off."""
        if self.is_active:
            self.hide_loupe()
        else:
            self.show_loupe()

    def show_loupe(self):
        """Activate and display optical loupe."""
        self.is_active = True
        self.settings["enabled"] = True
        self._recenter_window()
        self.show()
        # Re-apply win32 attributes just in case window handle was recreated
        apply_win32_window_attributes(int(self.winId()))
        self._fps_timer.start()
        self.update()

    def hide_loupe(self):
        """Deactivate optical loupe and stop screen grab timer to release CPU."""
        self.is_active = False
        self.settings["enabled"] = False
        self._fps_timer.stop()
        self.hide()

    def paintEvent(self, event):
        """Paint 60 FPS magnified micro-sample with tactical reticle and bezel."""
        if not self.is_active:
            return

        screen = QApplication.primaryScreen()
        if not screen:
            return

        geom = screen.geometry()
        d = int(self.settings.get("diameter", 220))
        zoom = float(self.settings.get("zoom_factor", 3.0))
        if zoom < 1.0:
            zoom = 1.0

        # Exact pixel center of target
        cx = geom.x() + geom.width() // 2 + int(self.settings.get("offset_x", 0))
        cy = geom.y() + geom.height() // 2 + int(self.settings.get("offset_y", 0))

        # Micro-crop dimensions
        sample_w = max(4, int(d / zoom))
        sample_h = max(4, int(d / zoom))

        crop_x = cx - sample_w // 2
        crop_y = cy - sample_h // 2

        # Clamp crop rectangle within screen geometry to prevent grab crash
        crop_x = max(geom.x(), min(crop_x, geom.x() + geom.width() - sample_w))
        crop_y = max(geom.y(), min(crop_y, geom.y() + geom.height() - sample_h))

        # Grab micro-crop from screen
        pix = screen.grabWindow(0, crop_x, crop_y, sample_w, sample_h)
        if pix.isNull() or pix.width() == 0 or pix.height() == 0:
            return

        # High quality smooth bilinear magnification
        scaled_pix = pix.scaled(d, d, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        shape_mode = self.settings.get("shape", "circle")
        border_color = QColor(self.settings.get("border_color", "#FF5B06"))

        # 1. Lens Shape Clipping Path
        path = QPainterPath()
        if shape_mode == "circle":
            path.addEllipse(2, 2, d - 4, d - 4)
        else:
            path.addRoundedRect(2, 2, d - 4, d - 4, 18, 18)

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled_pix)

        # 2. Optical Tint Filters
        tint_mode = self.settings.get("tint_mode", "clear")
        if tint_mode == "tactical_amber":
            # Amber high-contrast recon tint
            painter.fillRect(0, 0, d, d, QColor(255, 180, 0, 35))
        elif tint_mode == "cyber_green":
            # Cyber HUD neon green tint
            painter.fillRect(0, 0, d, d, QColor(0, 255, 120, 30))
        elif tint_mode == "night_vision":
            # Tactical phosphorescent night vision tint
            painter.fillRect(0, 0, d, d, QColor(10, 255, 40, 50))

        # 3. Vignette Edge Falloff (Realistic scope curvature shading)
        vignette = QRadialGradient(d / 2, d / 2, d / 2)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.75, QColor(0, 0, 0, 15))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 140))
        painter.fillRect(0, 0, d, d, vignette)

        # 4. Superimposed Reticle Inside Loupe
        reticle_type = self.settings.get("reticle_type", "mil_dot")
        center_x = d // 2
        center_y = d // 2

        if reticle_type != "none":
            self._draw_reticle(painter, d, center_x, center_y, reticle_type, border_color)

        # 5. Reset Clip & Draw Outer Scope Bezel & Glowing Rim
        painter.setClipping(False)

        # Outer bezel ring
        bezel_pen = QPen(QColor(18, 20, 24, 240), 5)
        painter.setPen(bezel_pen)
        painter.setBrush(Qt.NoBrush)
        if shape_mode == "circle":
            painter.drawEllipse(3, 3, d - 6, d - 6)
        else:
            painter.drawRoundedRect(3, 3, d - 6, d - 6, 18, 18)

        # Accent Glow Rim
        glow_pen = QPen(border_color, 2)
        painter.setPen(glow_pen)
        if shape_mode == "circle":
            painter.drawEllipse(1, 1, d - 2, d - 2)
        else:
            painter.drawRoundedRect(1, 1, d - 2, d - 2, 18, 18)

        # 6. Orbitron Tactical HUD Badge (e.g. "[ 3.0X MAG ]")
        if self.settings.get("show_hud_badge", True):
            self._draw_hud_badge(painter, d, zoom, border_color)

    def _draw_reticle(self, painter, d, cx, cy, r_type, accent_color):
        """Draw tactical scope reticles with sub-pixel precision."""
        if r_type == "mil_dot":
            # Tactical Mil-Dot reticle
            cross_color = QColor(255, 255, 255, 210)
            painter.setPen(QPen(cross_color, 1))

            # Fine cross lines
            arm = d // 2 - 14
            painter.drawLine(cx - arm, cy, cx - 10, cy)
            painter.drawLine(cx + 10, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy - 10)
            painter.drawLine(cx, cy + 10, cx, cy + arm)

            # Mil dots along axes (spaced every 18 px)
            painter.setBrush(QBrush(accent_color))
            painter.setPen(Qt.NoPen)
            for dist in [20, 38, 56, 74]:
                if dist < arm:
                    # Horizontal dots
                    painter.drawEllipse(cx - dist - 1.5, cy - 1.5, 3, 3)
                    painter.drawEllipse(cx + dist - 1.5, cy - 1.5, 3, 3)
                    # Vertical dots
                    painter.drawEllipse(cx - 1.5, cy - dist - 1.5, 3, 3)
                    painter.drawEllipse(cx - 1.5, cy + dist - 1.5, 3, 3)

            # Center Dot
            painter.setBrush(QBrush(QColor("#00FF88")))
            painter.drawEllipse(cx - 2, cy - 2, 4, 4)

        elif r_type == "fine_cross":
            # Ultra-thin precision cross
            painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
            arm = d // 2 - 12
            painter.drawLine(cx - arm, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy + arm)

            # Center hollow ring
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(accent_color, 1.5))
            painter.drawEllipse(cx - 5, cy - 5, 10, 10)

        elif r_type == "circle_dot":
            # Circular reflex target with dot
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(accent_color, 1.5))
            painter.drawEllipse(cx - 24, cy - 24, 48, 48)

            painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
            painter.drawLine(cx - 32, cy, cx - 24, cy)
            painter.drawLine(cx + 24, cy, cx + 32, cy)
            painter.drawLine(cx, cy - 32, cx, cy - 24)
            painter.drawLine(cx, cy + 24, cx, cy + 32)

            painter.setBrush(QBrush(accent_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(cx - 2.5, cy - 2.5, 5, 5)

    def _draw_hud_badge(self, painter, d, zoom, accent_color):
        """Draw HUD magnification badge in Orbitron font at top/bottom of lens."""
        hud_font = QFont("Orbitron", 7)
        hud_font.setBold(True)
        painter.setFont(hud_font)

        # Top Badge: "[ 3.0X MAG ]"
        badge_text = f"[{zoom:.1f}X MAG]"
        painter.setPen(QPen(accent_color))
        painter.drawText(QRectF(0, 8, d, 14), Qt.AlignHCenter | Qt.AlignVCenter, badge_text)
