"""
CrosshairOverlay - Transparent always-on-top crosshair window.
Provides a click-through overlay that displays a customizable crosshair.

Supports GPU-accelerated OpenGL rendering with automatic QPainter fallback.
"""
from PySide6.QtWidgets import QWidget, QApplication, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap
import json
import os

# Try to import OpenGL renderer
OPENGL_AVAILABLE = False
try:
    from CrosshairGL import CrosshairGL, OPENGL_AVAILABLE as GL_AVAILABLE
    if GL_AVAILABLE:
        OPENGL_AVAILABLE = True
        print("[Crosshair] OpenGL acceleration available")
except ImportError as e:
    print(f"[Crosshair] OpenGL not available: {e}")


class CrosshairOverlay(QWidget):
    """Transparent overlay window for crosshair display."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Get screen dimensions
        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()
        
        # Crosshair settings (defaults)
        self.settings = {
            "enabled": False,
            "shape": "cross",  # dot, cross, circle, t-shape, custom
            "color": "#00FF00",  # Main color
            "size": 20,  # Overall size
            "thickness": 2,  # Line thickness
            "opacity": 100,  # 0-100%
            "dot_size": 4,  # Center dot size
            "dot_enabled": True,
            "outline_enabled": True,
            "outline_color": "#000000",
            "outline_thickness": 1,
            "gap": 4,  # Gap from center
            "offset_x": 0,  # X offset from center
            "offset_y": 0,  # Y offset from center
            "rotation": 0,  # Rotation in degrees
            "custom_image": None,  # Path to custom image
            "custom_colors": [],  # User-saved custom colors from color picker
        }
        
        # Setup window properties for overlay
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # Set window to cover entire screen
        self.setGeometry(0, 0, self.screen_width, self.screen_height)
        
        # Load saved settings
        self.load_settings()
        
        # Try to use OpenGL renderer
        self._use_opengl = False
        self._gl_widget = None
        if OPENGL_AVAILABLE:
            self._setup_opengl()
    
    def _setup_opengl(self):
        """Initialize OpenGL rendering backend."""
        try:
            # Create OpenGL widget
            self._gl_widget = CrosshairGL(self.settings, self)
            
            # Layout to host GL widget
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._gl_widget)
            
            self._use_opengl = True
            print("[Crosshair] OpenGL renderer initialized")
        except Exception as e:
            print(f"[Crosshair] OpenGL init failed: {e}, using QPainter fallback")
            self._use_opengl = False
            self._gl_widget = None
    
    def load_settings(self):
        """Load crosshair settings from file."""
        # Save to AppData for persistence
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID')
        os.makedirs(appdata_dir, exist_ok=True)
        settings_path = os.path.join(appdata_dir, "crosshair_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception as e:
                print(f"Error loading crosshair settings: {e}")
    
    def save_settings(self):
        """Save crosshair settings to file."""
        # Save to AppData for persistence
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'HELXAID')
        os.makedirs(appdata_dir, exist_ok=True)
        settings_path = os.path.join(appdata_dir, "crosshair_settings.json")
        try:
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving crosshair settings: {e}")
    
    def update_settings(self, key, value):
        """Update a setting and refresh display."""
        self.settings[key] = value
        self.save_settings()
        
        # Update OpenGL widget if using it
        if self._use_opengl and self._gl_widget:
            self._gl_widget.update_settings(key, value)
        else:
            self.update()  # Trigger QPainter repaint
    
    def toggle(self):
        """Toggle crosshair visibility."""
        if self.isVisible():
            self.hide()
            self.settings["enabled"] = False
        else:
            self.show()
            self.settings["enabled"] = True
        self.save_settings()
    
    def paintEvent(self, event):
        """Draw the crosshair using QPainter (fallback when OpenGL not available)."""
        # Skip if using OpenGL - the GL widget handles rendering
        if self._use_opengl:
            return
        
        if not self.settings.get("enabled", False) and not self.isVisible():
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate center with offset
        center_x = self.screen_width // 2 + self.settings.get("offset_x", 0)
        center_y = self.screen_height // 2 + self.settings.get("offset_y", 0)
        
        # Apply rotation
        rotation = self.settings.get("rotation", 0)
        if rotation != 0:
            painter.translate(center_x, center_y)
            painter.rotate(rotation)
            painter.translate(-center_x, -center_y)
        
        # Get settings
        color = QColor(self.settings.get("color", "#00FF00"))
        opacity = self.settings.get("opacity", 100) / 100.0
        color.setAlphaF(opacity)
        
        size = self.settings.get("size", 20)
        thickness = self.settings.get("thickness", 2)
        gap = self.settings.get("gap", 4)
        shape = self.settings.get("shape", "cross")
        
        # Outline settings
        outline_enabled = self.settings.get("outline_enabled", True)
        outline_color = QColor(self.settings.get("outline_color", "#000000"))
        outline_color.setAlphaF(opacity)
        outline_thickness = self.settings.get("outline_thickness", 1)
        
        # Draw based on shape
        if shape == "custom" and self.settings.get("custom_image"):
            self._draw_custom_image(painter, center_x, center_y, size)
        elif shape == "dot":
            self._draw_dot(painter, center_x, center_y, color, outline_enabled, outline_color, outline_thickness, opacity)
        elif shape == "cross":
            self._draw_cross(painter, center_x, center_y, color, size, thickness, gap, outline_enabled, outline_color, outline_thickness)
        elif shape == "circle":
            self._draw_circle(painter, center_x, center_y, color, size, thickness, outline_enabled, outline_color, outline_thickness)
        elif shape == "t-shape":
            self._draw_t_shape(painter, center_x, center_y, color, size, thickness, gap, outline_enabled, outline_color, outline_thickness)
        
        # Draw center dot if enabled
        if self.settings.get("dot_enabled", True) and shape != "dot":
            dot_size = self.settings.get("dot_size", 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                center_x - dot_size // 2,
                center_y - dot_size // 2,
                dot_size,
                dot_size
            )
    
    def _draw_dot(self, painter, cx, cy, color, outline, outline_color, outline_thick, opacity):
        """Draw a dot crosshair."""
        dot_size = self.settings.get("dot_size", 6)
        
        if outline:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(outline_color))
            painter.drawEllipse(
                cx - (dot_size + outline_thick*2) // 2,
                cy - (dot_size + outline_thick*2) // 2,
                dot_size + outline_thick*2,
                dot_size + outline_thick*2
            )
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(
            cx - dot_size // 2,
            cy - dot_size // 2,
            dot_size,
            dot_size
        )
    
    def _draw_cross(self, painter, cx, cy, color, size, thickness, gap, outline, outline_color, outline_thick):
        """Draw a cross (+) crosshair."""
        pen = QPen(color, thickness)
        
        # Draw outline first
        if outline:
            outline_pen = QPen(outline_color, thickness + outline_thick * 2)
            painter.setPen(outline_pen)
            # Top
            painter.drawLine(cx, cy - gap - size, cx, cy - gap)
            # Bottom
            painter.drawLine(cx, cy + gap, cx, cy + gap + size)
            # Left
            painter.drawLine(cx - gap - size, cy, cx - gap, cy)
            # Right
            painter.drawLine(cx + gap, cy, cx + gap + size, cy)
        
        # Draw main lines
        painter.setPen(pen)
        # Top
        painter.drawLine(cx, cy - gap - size, cx, cy - gap)
        # Bottom
        painter.drawLine(cx, cy + gap, cx, cy + gap + size)
        # Left
        painter.drawLine(cx - gap - size, cy, cx - gap, cy)
        # Right
        painter.drawLine(cx + gap, cy, cx + gap + size, cy)
    
    def _draw_circle(self, painter, cx, cy, color, size, thickness, outline, outline_color, outline_thick):
        """Draw a circle crosshair."""
        if outline:
            outline_pen = QPen(outline_color, thickness + outline_thick * 2)
            painter.setPen(outline_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cx - size, cy - size, size * 2, size * 2)
        
        pen = QPen(color, thickness)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(cx - size, cy - size, size * 2, size * 2)
    
    def _draw_t_shape(self, painter, cx, cy, color, size, thickness, gap, outline, outline_color, outline_thick):
        """Draw a T-shape crosshair (no top line)."""
        pen = QPen(color, thickness)
        
        if outline:
            outline_pen = QPen(outline_color, thickness + outline_thick * 2)
            painter.setPen(outline_pen)
            # Bottom
            painter.drawLine(cx, cy + gap, cx, cy + gap + size)
            # Left
            painter.drawLine(cx - gap - size, cy, cx - gap, cy)
            # Right
            painter.drawLine(cx + gap, cy, cx + gap + size, cy)
        
        painter.setPen(pen)
        # Bottom
        painter.drawLine(cx, cy + gap, cx, cy + gap + size)
        # Left
        painter.drawLine(cx - gap - size, cy, cx - gap, cy)
        # Right
        painter.drawLine(cx + gap, cy, cx + gap + size, cy)
    
    def _draw_custom_image(self, painter, cx, cy, size):
        """Draw a custom image crosshair."""
        img_path = self.settings.get("custom_image")
        if not img_path or not os.path.exists(img_path):
            return
        
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
        
        # Scale to size
        scaled = pixmap.scaled(size * 2, size * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Apply opacity
        opacity = self.settings.get("opacity", 100) / 100.0
        painter.setOpacity(opacity)
        
        # Draw centered
        painter.drawPixmap(
            cx - scaled.width() // 2,
            cy - scaled.height() // 2,
            scaled
        )
        painter.setOpacity(1.0)
