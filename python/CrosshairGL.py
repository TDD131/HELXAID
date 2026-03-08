"""
CrosshairGL - GPU-accelerated crosshair overlay using OpenGL.

Provides smooth, low-latency crosshair rendering with hardware anti-aliasing.
Falls back to QPainter if OpenGL is not available.
"""
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
import math

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False
    print("[CrosshairGL] OpenGL not available")


def hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple:
    """
    Convert hex color string to OpenGL RGBA tuple (0.0-1.0 range).
    
    Args:
        hex_color: Color in hex format (e.g., "#00FF00" or "00FF00")
        opacity: Opacity value from 0.0 to 1.0
    
    Returns:
        Tuple of (r, g, b, a) with values from 0.0 to 1.0
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b, opacity)


class CrosshairGL(QOpenGLWidget):
    """
    OpenGL-based crosshair renderer.
    
    Uses GPU acceleration for smooth, low-latency rendering.
    Supports all crosshair shapes: dot, cross, circle, t-shape.
    """
    
    # Component name for UI inspector
    COMPONENT_NAME = "CrosshairGL"
    
    def __init__(self, settings: dict, parent=None):
        """
        Initialize OpenGL crosshair widget.
        
        Args:
            settings: Dictionary containing crosshair settings
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName(self.COMPONENT_NAME)
        
        self.settings = settings
        
        # Setup surface format for MSAA and transparency
        fmt = QSurfaceFormat()
        fmt.setSamples(4)  # 4x MSAA for smooth edges
        fmt.setSwapInterval(0)  # No VSync for lowest latency
        fmt.setAlphaBufferSize(8)  # Enable alpha channel
        self.setFormat(fmt)
        
        # Transparent background
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        
        # Cached rendering values
        self._cache_settings()
    
    def _cache_settings(self):
        """
        Cache settings as OpenGL-ready values for fast rendering.
        Called when settings change or on resize.
        """
        # Center position with offset
        self.cx = self.width() // 2 + self.settings.get("offset_x", 0)
        self.cy = self.height() // 2 + self.settings.get("offset_y", 0)
        
        # Colors
        opacity = self.settings.get("opacity", 100) / 100.0
        self.color_rgba = hex_to_rgba(
            self.settings.get("color", "#00FF00"), opacity
        )
        self.outline_rgba = hex_to_rgba(
            self.settings.get("outline_color", "#000000"), opacity
        )
        
        # Dimensions
        self.size = self.settings.get("size", 20)
        self.thickness = float(self.settings.get("thickness", 2))
        self.gap = self.settings.get("gap", 4)
        self.dot_size = self.settings.get("dot_size", 4)
        self.rotation = self.settings.get("rotation", 0)
        self.shape = self.settings.get("shape", "cross")
        
        # Flags
        self.outline_enabled = self.settings.get("outline_enabled", True)
        self.outline_thickness = self.settings.get("outline_thickness", 1)
        self.dot_enabled = self.settings.get("dot_enabled", True)
    
    def update_settings(self, key: str, value):
        """
        Update a setting and refresh display.
        
        Args:
            key: Setting key to update
            value: New value
        """
        self.settings[key] = value
        self._cache_settings()
        self.update()  # Trigger repaint
    
    def initializeGL(self):
        """
        Setup OpenGL state for 2D rendering with transparency.
        Called once when the widget is first shown.
        """
        # Enable blending for transparency
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Enable line smoothing (anti-aliasing)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        
        # Enable point smoothing for dots
        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        
        # Transparent clear color
        glClearColor(0.0, 0.0, 0.0, 0.0)
        
        print("[CrosshairGL] OpenGL initialized")
    
    def resizeGL(self, w: int, h: int):
        """
        Handle widget resize - update viewport and projection.
        
        Args:
            w: New width
            h: New height
        """
        glViewport(0, 0, w, h)
        
        # Setup orthographic projection for 2D
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Y-axis flipped to match Qt coordinate system (0,0 at top-left)
        glOrtho(0, w, h, 0, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Recache settings with new dimensions
        self._cache_settings()
    
    def paintGL(self):
        """
        GPU-accelerated crosshair rendering.
        Called every frame when update() is triggered.
        """
        # Clear with transparent background
        glClear(GL_COLOR_BUFFER_BIT)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Apply rotation around center
        if self.rotation != 0:
            glTranslatef(self.cx, self.cy, 0)
            glRotatef(self.rotation, 0, 0, 1)
            glTranslatef(-self.cx, -self.cy, 0)
        
        # Draw based on shape
        if self.shape == "dot":
            self._draw_dot()
        elif self.shape == "cross":
            self._draw_cross()
        elif self.shape == "circle":
            self._draw_circle()
        elif self.shape == "t-shape":
            self._draw_t_shape()
        
        # Draw center dot if enabled and not already a dot shape
        if self.dot_enabled and self.shape != "dot":
            self._draw_center_dot()
    
    def _draw_dot(self):
        """
        Draw a filled circle (dot) crosshair.
        Uses GL_TRIANGLE_FAN for smooth circle rendering.
        """
        cx, cy = self.cx, self.cy
        radius = self.dot_size / 2
        segments = 32  # More segments = smoother circle
        
        # Draw outline first (behind main dot)
        if self.outline_enabled:
            glColor4f(*self.outline_rgba)
            self._draw_filled_circle(
                cx, cy, radius + self.outline_thickness, segments
            )
        
        # Draw main dot
        glColor4f(*self.color_rgba)
        self._draw_filled_circle(cx, cy, radius, segments)
    
    def _draw_center_dot(self):
        """Draw a small center dot."""
        cx, cy = self.cx, self.cy
        radius = self.dot_size / 2
        segments = 24
        
        glColor4f(*self.color_rgba)
        self._draw_filled_circle(cx, cy, radius, segments)
    
    def _draw_filled_circle(self, cx: float, cy: float, radius: float, segments: int):
        """
        Helper to draw a filled circle using triangle fan.
        
        Args:
            cx, cy: Center coordinates
            radius: Circle radius
            segments: Number of triangle segments
        """
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)  # Center vertex
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            glVertex2f(x, y)
        glEnd()
    
    def _draw_cross(self):
        """
        Draw a + shaped crosshair with 4 lines.
        """
        cx, cy = self.cx, self.cy
        size = self.size
        gap = self.gap
        
        # Draw outline first
        if self.outline_enabled:
            glLineWidth(self.thickness + self.outline_thickness * 2)
            glColor4f(*self.outline_rgba)
            self._draw_cross_lines(cx, cy, size, gap)
        
        # Draw main lines
        glLineWidth(self.thickness)
        glColor4f(*self.color_rgba)
        self._draw_cross_lines(cx, cy, size, gap)
    
    def _draw_cross_lines(self, cx: float, cy: float, size: int, gap: int):
        """
        Helper to draw the 4 lines of a cross.
        
        Args:
            cx, cy: Center coordinates
            size: Line length
            gap: Gap from center
        """
        glBegin(GL_LINES)
        # Top line
        glVertex2f(cx, cy - gap - size)
        glVertex2f(cx, cy - gap)
        # Bottom line
        glVertex2f(cx, cy + gap)
        glVertex2f(cx, cy + gap + size)
        # Left line
        glVertex2f(cx - gap - size, cy)
        glVertex2f(cx - gap, cy)
        # Right line
        glVertex2f(cx + gap, cy)
        glVertex2f(cx + gap + size, cy)
        glEnd()
    
    def _draw_circle(self):
        """
        Draw a circle (ring) crosshair.
        Uses GL_LINE_LOOP for smooth ring rendering.
        """
        cx, cy = self.cx, self.cy
        radius = self.size
        segments = 48  # More segments for smooth circle
        
        # Draw outline first
        if self.outline_enabled:
            glLineWidth(self.thickness + self.outline_thickness * 2)
            glColor4f(*self.outline_rgba)
            self._draw_ring(cx, cy, radius, segments)
        
        # Draw main circle
        glLineWidth(self.thickness)
        glColor4f(*self.color_rgba)
        self._draw_ring(cx, cy, radius, segments)
    
    def _draw_ring(self, cx: float, cy: float, radius: float, segments: int):
        """
        Helper to draw a ring (unfilled circle).
        
        Args:
            cx, cy: Center coordinates
            radius: Circle radius
            segments: Number of line segments
        """
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            glVertex2f(x, y)
        glEnd()
    
    def _draw_t_shape(self):
        """
        Draw a T-shaped crosshair (no top line).
        """
        cx, cy = self.cx, self.cy
        size = self.size
        gap = self.gap
        
        # Draw outline first
        if self.outline_enabled:
            glLineWidth(self.thickness + self.outline_thickness * 2)
            glColor4f(*self.outline_rgba)
            self._draw_t_lines(cx, cy, size, gap)
        
        # Draw main lines
        glLineWidth(self.thickness)
        glColor4f(*self.color_rgba)
        self._draw_t_lines(cx, cy, size, gap)
    
    def _draw_t_lines(self, cx: float, cy: float, size: int, gap: int):
        """
        Helper to draw the 3 lines of a T-shape.
        
        Args:
            cx, cy: Center coordinates
            size: Line length
            gap: Gap from center
        """
        glBegin(GL_LINES)
        # Bottom line only (no top)
        glVertex2f(cx, cy + gap)
        glVertex2f(cx, cy + gap + size)
        # Left line
        glVertex2f(cx - gap - size, cy)
        glVertex2f(cx - gap, cy)
        # Right line
        glVertex2f(cx + gap, cy)
        glVertex2f(cx + gap + size, cy)
        glEnd()
