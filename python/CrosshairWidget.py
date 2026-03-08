"""
CrosshairWidget - Panel UI for crosshair settings and controls.
Provides sliders, color pickers, and shape selectors for crosshair customization.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QComboBox, QCheckBox, QGroupBox, QColorDialog, QFileDialog,
    QScrollArea, QFrame, QSpinBox, QGridLayout, QSystemTrayIcon, QApplication, QMenu
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtCore import Qt, Signal, Property, QPropertyAnimation, QEasingCurve, QTimer, QPoint, QRect
from PySide6.QtGui import QColor, QPixmap, QIcon, QCursor, QPainter, QScreen, QPen, QBrush
from CrosshairOverlay import CrosshairOverlay
import os
import json
import threading

# Try to import keyboard for global hotkeys (works with games)
try:
    import keyboard as kb_hook
    KEYBOARD_AVAILABLE = True
    print("keyboard library loaded successfully")
except ImportError as e:
    KEYBOARD_AVAILABLE = False
    print(f"keyboard library not available - global hotkeys disabled: {e}")
except Exception as e:
    KEYBOARD_AVAILABLE = False
    print(f"keyboard library error: {e}")


# Custom widgets that ignore mouse wheel to prevent accidental value changes
class NoScrollSlider(QSlider):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class EyedropperOverlay(QWidget):
    """Full-screen overlay for picking colors from screen with zoom preview."""
    colorPicked = Signal(str)
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.BlankCursor)  # Hide real cursor
        
        # Capture entire screen
        screen = QApplication.primaryScreen()
        self._screen_pixmap = screen.grabWindow(0)
        self.setGeometry(screen.geometry())
        
        # Zoom settings
        self._zoom_size = 160  # Size of zoom preview
        self._zoom_factor = 8  # Magnification level
        self._current_color = QColor("#ffffff")
        
        # Virtual cursor with reduced sensitivity
        self._sensitivity = 0.2  # Mouse sensitivity (0.3 = 30% of normal speed)
        self._virtual_pos = QPoint(screen.geometry().width() // 2, screen.geometry().height() // 2)
        self._last_mouse_pos = QCursor.pos()
        
        # Update timer for smooth tracking
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_virtual_cursor)
        self._timer.start(16)  # ~60fps
        
        # Ignore initial click that opened this overlay
        self._click_ready = False
        QTimer.singleShot(500, self._enable_click)  # Wait 500ms before accepting clicks
    
    def _enable_click(self):
        self._click_ready = True
    
    def _update_virtual_cursor(self):
        """Update virtual cursor position with reduced sensitivity."""
        current_pos = QCursor.pos()
        
        # Calculate center of screen for re-centering
        center_x = self._screen_pixmap.width() // 2
        center_y = self._screen_pixmap.height() // 2
        
        delta_x = current_pos.x() - self._last_mouse_pos.x()
        delta_y = current_pos.y() - self._last_mouse_pos.y()
        
        # Apply sensitivity reduction
        new_x = self._virtual_pos.x() + int(delta_x * self._sensitivity)
        new_y = self._virtual_pos.y() + int(delta_y * self._sensitivity)
        
        # Clamp to screen bounds
        new_x = max(0, min(new_x, self._screen_pixmap.width() - 1))
        new_y = max(0, min(new_y, self._screen_pixmap.height() - 1))
        
        self._virtual_pos = QPoint(new_x, new_y)
        
        # Re-center real mouse to prevent hitting screen edge
        QCursor.setPos(center_x, center_y)
        self._last_mouse_pos = QPoint(center_x, center_y)
        
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Draw captured screen
        painter.drawPixmap(0, 0, self._screen_pixmap)
        
        # Semi-transparent overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 50))
        
        # Use virtual cursor position instead of real cursor
        cursor_pos = self._virtual_pos
        
        # Sample pixel color
        if 0 <= cursor_pos.x() < self._screen_pixmap.width() and 0 <= cursor_pos.y() < self._screen_pixmap.height():
            image = self._screen_pixmap.toImage()
            self._current_color = QColor(image.pixel(cursor_pos.x(), cursor_pos.y()))
        
        # Draw crosshair at virtual cursor position
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawLine(cursor_pos.x() - 10, cursor_pos.y(), cursor_pos.x() + 10, cursor_pos.y())
        painter.drawLine(cursor_pos.x(), cursor_pos.y() - 10, cursor_pos.x(), cursor_pos.y() + 10)
        
        # Draw zoom preview
        zoom_x = cursor_pos.x() + 20
        zoom_y = cursor_pos.y() + 20
        
        # Keep zoom preview on screen
        if zoom_x + self._zoom_size > self.width():
            zoom_x = cursor_pos.x() - self._zoom_size - 20
        if zoom_y + self._zoom_size + 80 > self.height():
            zoom_y = cursor_pos.y() - self._zoom_size - 100
        
        # Zoom preview background
        panel_height = self._zoom_size + 80  # More space for text
        painter.fillRect(zoom_x - 2, zoom_y - 2, self._zoom_size + 4, panel_height, QColor(30, 30, 30, 230))
        painter.setPen(QPen(QColor("#FF5B06"), 2))
        painter.drawRect(zoom_x - 2, zoom_y - 2, self._zoom_size + 4, panel_height)
        
        # Draw zoomed area
        sample_size = self._zoom_size // self._zoom_factor
        source_rect = QRect(
            cursor_pos.x() - sample_size // 2,
            cursor_pos.y() - sample_size // 2,
            sample_size, sample_size
        )
        target_rect = QRect(zoom_x, zoom_y, self._zoom_size, self._zoom_size)
        painter.drawPixmap(target_rect, self._screen_pixmap, source_rect)
        
        # Crosshair in zoom preview center
        center_x = zoom_x + self._zoom_size // 2
        center_y = zoom_y + self._zoom_size // 2
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawLine(center_x - 8, center_y, center_x + 8, center_y)
        painter.drawLine(center_x, center_y - 8, center_x, center_y + 8)
        
        # Color preview box
        color_box_y = zoom_y + self._zoom_size + 5
        painter.fillRect(zoom_x, color_box_y, 30, 25, self._current_color)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawRect(zoom_x, color_box_y, 30, 25)
        
        # Color hex text
        painter.setPen(QColor("#e0e0e0"))
        painter.drawText(zoom_x + 35, color_box_y + 17, self._current_color.name().upper())
        
        # Cancel instruction
        painter.setPen(QColor("#888888"))
        painter.drawText(zoom_x, color_box_y + 45, "ESC or Right Click to cancel")
    
    def mousePressEvent(self, event):
        if not self._click_ready:
            return  # Ignore clicks during startup
        if event.button() == Qt.LeftButton:
            self.colorPicked.emit(self._current_color.name())
            self.close()
        elif event.button() == Qt.RightButton:
            self.cancelled.emit()
            self.close()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
    
    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class HorizontalSpinBox(QFrame):
    """SpinBox with horizontal +/- buttons on the right side."""
    valueChanged = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._min = -100
        self._max = 100
        
        # Force exact height
        self.setFixedHeight(32)
        self.setMaximumHeight(32)
        self.setMinimumHeight(32)
        self.setStyleSheet("QFrame { background: transparent; }")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Value display
        self._value_edit = QLabel("0")
        self._value_edit.setAlignment(Qt.AlignCenter)
        self._value_edit.setMinimumWidth(50)
        self._value_edit.setFixedHeight(32)
        self._value_edit.setStyleSheet("""
            QLabel {
                background: rgba(30, 33, 40, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 8px;
                padding: 0px 10px;
                color: #e0e0e0;
                font-weight: 500;
            }
        """)
        layout.addWidget(self._value_edit, 1)
        
        # Plus button (increase)
        self._plus_btn = QPushButton("+")
        self._plus_btn.setFixedSize(32, 32)
        self._plus_btn.clicked.connect(self._increment)
        self._plus_btn.setStyleSheet(self._button_style())
        layout.addWidget(self._plus_btn)
        
        # Minus button (decrease)
        self._minus_btn = QPushButton("-")
        self._minus_btn.setFixedSize(32, 32)
        self._minus_btn.clicked.connect(self._decrement)
        self._minus_btn.setStyleSheet(self._button_style())
        layout.addWidget(self._minus_btn)
    
    def _button_style(self):
        return """
            QPushButton {
                background: rgba(30, 33, 40, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                color: #e0e0e0;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
            }
            QPushButton:pressed {
                background: rgba(255, 91, 6, 0.5);
            }
        """
    
    def _increment(self):
        self.setValue(self._value + 1)
    
    def _decrement(self):
        self.setValue(self._value - 1)
    
    def setValue(self, value):
        value = max(self._min, min(self._max, value))
        if value != self._value:
            self._value = value
            self._value_edit.setText(str(value))
            self.valueChanged.emit(value)
    
    def value(self):
        return self._value
    
    def setRange(self, min_val, max_val):
        self._min = min_val
        self._max = max_val
    
    def wheelEvent(self, event):
        event.ignore()


class AnimatedComboBox(QComboBox):
    """ComboBox with animated arrow fade on open/close."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_value = 0.0  # 0 = down arrow, 1 = up arrow
        self._is_open = False
        self._animation = None
        
        # Load both arrow images
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self._down_pixmap = QPixmap(os.path.join(script_dir, "down-arrow.png"))
        self._up_pixmap = QPixmap(os.path.join(script_dir, "up-arrow.png"))
        
        # Custom arrow label
        self._arrow_label = QLabel(self)
        self._arrow_label.setFixedSize(12, 12)
        self._arrow_label.setStyleSheet("background: transparent;")
        self._update_arrow_blend()
        
    def showPopup(self):
        super().showPopup()
        self._is_open = True
        self._animate_fade(1.0)  # Fade to up arrow
    
    def hidePopup(self):
        super().hidePopup()
        self._is_open = False
        self._animate_fade(0.0)  # Fade to down arrow
    
    def _animate_fade(self, target_value):
        """Animate fade between arrows."""
        if self._animation:
            self._animation.stop()
        
        self._animation = QPropertyAnimation(self, b"fadeValue")
        self._animation.setDuration(500)
        self._animation.setStartValue(self._fade_value)
        self._animation.setEndValue(target_value)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.start()
    
    def _get_fade_value(self):
        return self._fade_value
    
    def _set_fade_value(self, value):
        self._fade_value = value
        self._update_arrow_blend()
    
    def _update_arrow_blend(self):
        """Blend between down and up arrows based on fade value."""
        from PySide6.QtGui import QPainter
        
        # Create blended image
        size = 12
        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw down arrow with fading opacity
        if self._fade_value < 1.0:
            painter.setOpacity(1.0 - self._fade_value)
            painter.drawPixmap(0, 0, self._down_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # Draw up arrow with increasing opacity
        if self._fade_value > 0.0:
            painter.setOpacity(self._fade_value)
            painter.drawPixmap(0, 0, self._up_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        painter.end()
        self._arrow_label.setPixmap(result)
    
    fadeValue = Property(float, _get_fade_value, _set_fade_value)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        arrow_x = self.width() - 25
        arrow_y = (self.height() - 12) // 2
        self._arrow_label.move(arrow_x, arrow_y)
    
    def wheelEvent(self, event):
        event.ignore()


class ColorButton(QPushButton):
    """Button that shows a color and opens color picker on click."""
    colorChanged = Signal(str)
    
    def __init__(self, color="#00FF00", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(40, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._update_style()
    
    def _update_style(self):
        # Use object name to ensure style only applies to this button, not QColorDialog buttons
        self.setObjectName("colorPickerButton")
        self.setStyleSheet(f"""
            QPushButton#colorPickerButton {{
                background-color: {self._color};
                border: 2px solid #555;
                border-radius: 4px;
            }}
            QPushButton#colorPickerButton:hover {{
                border: 2px solid #FF5B06;
            }}
        """)
    
    def _pick_color(self):
        try:
            # Create dialog to access custom colors
            dialog = QColorDialog(QColor(self._color), self)
            dialog.setWindowTitle("Select Color")
            dialog.setOption(QColorDialog.DontUseNativeDialog, True)
            
            # Find and rename "Pick Screen Color" button to "Eyedrop"
            for btn in dialog.findChildren(QPushButton):
                if "pick" in btn.text().lower() or "screen" in btn.text().lower():
                    btn.setText("Eyedrop")
                    # Replace Qt eyedropper with custom one
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, d=dialog: self._open_custom_eyedropper(d))
            
            # Try to load saved custom colors from parent CrosshairWidget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'overlay'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'overlay'):
                saved_colors = parent_widget.overlay.settings.get("custom_colors", [])
                for i, hex_color in enumerate(saved_colors[:16]):  # Max 16 custom colors
                    dialog.setCustomColor(i, QColor(hex_color))
            
            if dialog.exec():
                color = dialog.currentColor()
                if color.isValid():
                    self._color = color.name()
                    self._update_style()
                    self.colorChanged.emit(self._color)
                
                # Save custom colors back to settings (always save when dialog closes)
                if parent_widget and hasattr(parent_widget, 'overlay'):
                    custom_colors = []
                    for i in range(16):
                        c = dialog.customColor(i)
                        custom_colors.append(c.name())
                    print(f"[Crosshair] Saving custom colors: {custom_colors}")
                    parent_widget.overlay.update_settings("custom_colors", custom_colors)
        except Exception as e:
            print(f"Color picker error: {e}")
    
    def _open_custom_eyedropper(self, dialog):
        """Open custom eyedropper with zoom preview."""
        dialog.hide()  # Hide dialog temporarily
        self._pending_dialog = dialog
        
        # Delay to ensure mouse button is released before opening eyedropper
        QTimer.singleShot(200, self._show_eyedropper)
    
    def _show_eyedropper(self):
        """Actually show the eyedropper after delay."""
        print("[Eyedrop] Opening eyedropper overlay...")
        self._eyedropper = EyedropperOverlay()
        self._eyedropper.colorPicked.connect(self._on_eyedrop_color_picked)
        self._eyedropper.cancelled.connect(self._on_eyedrop_cancelled)
        self._eyedropper.show()
        self._eyedropper.activateWindow()
        self._eyedropper.raise_()
    
    def _on_eyedrop_color_picked(self, color_hex):
        """Handle color picked from eyedropper."""
        print(f"[Eyedrop] Color picked: {color_hex}")
        if hasattr(self, '_pending_dialog') and self._pending_dialog:
            self._pending_dialog.setCurrentColor(QColor(color_hex))
            self._pending_dialog.show()
    
    def _on_eyedrop_cancelled(self):
        """Handle eyedropper cancelled."""
        print("[Eyedrop] Cancelled")
        if hasattr(self, '_pending_dialog') and self._pending_dialog:
            self._pending_dialog.show()
    
    def _on_eyedrop_picked(self, color_hex, dialog):
        """Handle color picked from eyedropper."""
        dialog.setCurrentColor(QColor(color_hex))
        dialog.show()
    
    def color(self):
        return self._color
    
    def setColor(self, color):
        self._color = color
        self._update_style()


class CrosshairWidget(QWidget):
    """Panel UI for crosshair customization."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("crosshairPanel")
        
        # Create the overlay (hidden by default)
        self.overlay = CrosshairOverlay()
        
        # Setup global hotkey listener
        if KEYBOARD_AVAILABLE:
            self._setup_hotkey()
        
        self.setup_ui()
        self.load_ui_from_settings()
    
    def setup_ui(self):
        """Build the crosshair settings UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(24)
        
        # Header Card
        header_container = QWidget()
        header_container.setObjectName("headerCard")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(24, 20, 24, 20)
        
        header_icon = QLabel("")
        header_icon.setStyleSheet("font-size: 32px;")
        header_layout.addWidget(header_icon)
        
        header_text = QLabel("HELXAIR")
        header_text.setStyleSheet("font-size: 26px; font-weight: bold; color: #FF5B06;")
        header_layout.addWidget(header_text)
        header_layout.addStretch()
        
        header_container.setStyleSheet("""
            QWidget#headerCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 rgba(26, 26, 26, 0.9), stop:1 rgba(45, 45, 45, 0.6));
                border-radius: 16px;
                border: 1px solid rgba(255, 91, 6, 0.3);
            }
        """)
        main_layout.addWidget(header_container)
        
        # Scroll area for settings
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QWidget {
                background: transparent;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        
        # === ENABLE/TOGGLE SECTION ===
        toggle_group = QGroupBox("Quick Controls")
        toggle_group.setStyleSheet(self._group_style())
        toggle_layout = QHBoxLayout(toggle_group)
        
        self.enable_btn = QPushButton("Enable Crosshair")
        self.enable_btn.setCheckable(True)
        self.enable_btn.setStyleSheet(self._toggle_btn_style())
        self.enable_btn.clicked.connect(self._on_toggle)
        toggle_layout.addWidget(self.enable_btn)
        
        hotkey_label = QLabel("Hotkey: Ctrl+Shift+C")
        hotkey_label.setStyleSheet("color: #888; font-size: 12px;")
        toggle_layout.addWidget(hotkey_label)
        toggle_layout.addStretch()
        
        scroll_layout.addWidget(toggle_group)
        
        # === SHAPE SECTION ===
        shape_group = QGroupBox("Shape")
        shape_group.setStyleSheet(self._group_style())
        shape_layout = QVBoxLayout(shape_group)
        
        self.shape_combo = AnimatedComboBox()
        self.shape_combo.addItems(["Dot", "Cross", "Circle", "T-Shape", "Custom Image"])
        self.shape_combo.setStyleSheet(self._animated_combo_style())
        self.shape_combo.currentTextChanged.connect(self._on_shape_change)
        shape_layout.addWidget(self.shape_combo)
        
        # Custom image button
        self.custom_img_btn = QPushButton("Load Custom Image...")
        self.custom_img_btn.setStyleSheet(self._btn_style())
        self.custom_img_btn.clicked.connect(self._load_custom_image)
        self.custom_img_btn.hide()
        shape_layout.addWidget(self.custom_img_btn)
        
        scroll_layout.addWidget(shape_group)
        
        # === COLOR SECTION ===
        color_group = QGroupBox("Colors")
        color_group.setStyleSheet(self._group_style())
        color_layout = QGridLayout(color_group)
        
        # Main color
        color_layout.addWidget(QLabel("Main Color:"), 0, 0)
        self.main_color_btn = ColorButton("#00FF00")
        self.main_color_btn.colorChanged.connect(lambda c: self._update_setting("color", c))
        color_layout.addWidget(self.main_color_btn, 0, 1)
        
        # Outline
        self.outline_check = QCheckBox("Outline")
        self.outline_check.setChecked(True)
        self.outline_check.stateChanged.connect(lambda s: self._update_setting("outline_enabled", bool(s)))
        color_layout.addWidget(self.outline_check, 1, 0)
        
        self.outline_color_btn = ColorButton("#000000")
        self.outline_color_btn.colorChanged.connect(lambda c: self._update_setting("outline_color", c))
        color_layout.addWidget(self.outline_color_btn, 1, 1)
        
        scroll_layout.addWidget(color_group)
        
        # === SIZE & THICKNESS SECTION ===
        size_group = QGroupBox("Size and Thickness")
        size_group.setStyleSheet(self._group_style())
        size_layout = QGridLayout(size_group)
        
        # Size slider
        size_layout.addWidget(QLabel("Size:"), 0, 0)
        self.size_slider = NoScrollSlider(Qt.Horizontal)
        self.size_slider.setRange(5, 100)
        self.size_slider.setValue(20)
        self.size_slider.setStyleSheet(self._slider_style())
        self.size_slider.valueChanged.connect(lambda v: self._update_setting("size", v))
        size_layout.addWidget(self.size_slider, 0, 1)
        self.size_label = QLabel("20")
        self.size_slider.valueChanged.connect(lambda v: self.size_label.setText(str(v)))
        size_layout.addWidget(self.size_label, 0, 2)
        
        # Thickness slider
        size_layout.addWidget(QLabel("Thickness:"), 1, 0)
        self.thickness_slider = NoScrollSlider(Qt.Horizontal)
        self.thickness_slider.setRange(1, 10)
        self.thickness_slider.setValue(2)
        self.thickness_slider.setStyleSheet(self._slider_style())
        self.thickness_slider.valueChanged.connect(lambda v: self._update_setting("thickness", v))
        size_layout.addWidget(self.thickness_slider, 1, 1)
        self.thickness_label = QLabel("2")
        self.thickness_slider.valueChanged.connect(lambda v: self.thickness_label.setText(str(v)))
        size_layout.addWidget(self.thickness_label, 1, 2)
        
        # Gap slider
        size_layout.addWidget(QLabel("Center Gap:"), 2, 0)
        self.gap_slider = NoScrollSlider(Qt.Horizontal)
        self.gap_slider.setRange(0, 20)
        self.gap_slider.setValue(4)
        self.gap_slider.setStyleSheet(self._slider_style())
        self.gap_slider.valueChanged.connect(lambda v: self._update_setting("gap", v))
        size_layout.addWidget(self.gap_slider, 2, 1)
        self.gap_label = QLabel("4")
        self.gap_slider.valueChanged.connect(lambda v: self.gap_label.setText(str(v)))
        size_layout.addWidget(self.gap_label, 2, 2)
        
        scroll_layout.addWidget(size_group)
        
        # === OPACITY SECTION ===
        opacity_group = QGroupBox("Opacity")
        opacity_group.setStyleSheet(self._group_style())
        opacity_layout = QHBoxLayout(opacity_group)
        
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.opacity_slider = NoScrollSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setStyleSheet(self._slider_style())
        self.opacity_slider.valueChanged.connect(lambda v: self._update_setting("opacity", v))
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_layout.addWidget(self.opacity_label)
        
        scroll_layout.addWidget(opacity_group)
        
        # === CENTER DOT SECTION ===
        dot_group = QGroupBox("Center Dot")
        dot_group.setStyleSheet(self._group_style())
        dot_layout = QGridLayout(dot_group)
        
        self.dot_check = QCheckBox("Show Center Dot")
        self.dot_check.setChecked(True)
        self.dot_check.stateChanged.connect(lambda s: self._update_setting("dot_enabled", bool(s)))
        dot_layout.addWidget(self.dot_check, 0, 0, 1, 2)
        
        dot_layout.addWidget(QLabel("Dot Size:"), 1, 0)
        self.dot_size_slider = NoScrollSlider(Qt.Horizontal)
        self.dot_size_slider.setRange(2, 20)
        self.dot_size_slider.setValue(4)
        self.dot_size_slider.setStyleSheet(self._slider_style())
        self.dot_size_slider.valueChanged.connect(lambda v: self._update_setting("dot_size", v))
        dot_layout.addWidget(self.dot_size_slider, 1, 1)
        
        scroll_layout.addWidget(dot_group)
        
        # === POSITION & ROTATION SECTION ===
        pos_group = QGroupBox("Position & Rotation")
        pos_group.setStyleSheet(self._group_style())
        pos_layout = QGridLayout(pos_group)
        pos_layout.setVerticalSpacing(8)
        pos_layout.setColumnStretch(1, 1)
        
        # X Offset - inline layout
        pos_layout.addWidget(QLabel("X Offset:"), 0, 0, Qt.AlignVCenter)
        self.x_offset_value = QLabel("0")
        self.x_offset_value.setAlignment(Qt.AlignCenter)
        self.x_offset_value.setFixedHeight(40)
        self.x_offset_value.setStyleSheet("""
            QLabel {
                background: rgba(30, 33, 40, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 8px;
                padding: 0px 10px;
                color: #e0e0e0;
                font-weight: 500;
            }
        """)
        pos_layout.addWidget(self.x_offset_value, 0, 1)
        
        x_plus = QPushButton("+")
        x_plus.setMinimumSize(40, 40)
        x_plus.setMaximumWidth(40)
        x_plus.setStyleSheet(self._offset_btn_style())
        x_plus.clicked.connect(lambda: self._change_offset("x", 1))
        pos_layout.addWidget(x_plus, 0, 2)
        
        x_minus = QPushButton("-")
        x_minus.setMinimumSize(40, 40)
        x_minus.setMaximumWidth(40)
        x_minus.setStyleSheet(self._offset_btn_style())
        x_minus.clicked.connect(lambda: self._change_offset("x", -1))
        pos_layout.addWidget(x_minus, 0, 3)
        
        # Y Offset - inline layout
        pos_layout.addWidget(QLabel("Y Offset:"), 1, 0, Qt.AlignVCenter)
        self.y_offset_value = QLabel("0")
        self.y_offset_value.setAlignment(Qt.AlignCenter)
        self.y_offset_value.setFixedHeight(40)
        self.y_offset_value.setStyleSheet("""
            QLabel {
                background: rgba(30, 33, 40, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 8px;
                padding: 0px 10px;
                color: #e0e0e0;
                font-weight: 500;
            }
        """)
        pos_layout.addWidget(self.y_offset_value, 1, 1)
        
        y_plus = QPushButton("+")
        y_plus.setMinimumSize(40, 40)
        y_plus.setMaximumWidth(40)
        y_plus.setStyleSheet(self._offset_btn_style())
        y_plus.clicked.connect(lambda: self._change_offset("y", 1))
        pos_layout.addWidget(y_plus, 1, 2)
        
        y_minus = QPushButton("-")
        y_minus.setMinimumSize(40, 40)
        y_minus.setMaximumWidth(40)
        y_minus.setStyleSheet(self._offset_btn_style())
        y_minus.clicked.connect(lambda: self._change_offset("y", -1))
        pos_layout.addWidget(y_minus, 1, 3)
        
        # Store offset values
        self._offset_x = 0
        self._offset_y = 0
        
        # Rotation
        pos_layout.addWidget(QLabel("Rotation:"), 2, 0)
        self.rotation_slider = NoScrollSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setStyleSheet(self._slider_style())
        self.rotation_slider.valueChanged.connect(lambda v: self._update_setting("rotation", v))
        pos_layout.addWidget(self.rotation_slider, 2, 1, 1, 2)
        self.rotation_label = QLabel("0°")
        self.rotation_slider.valueChanged.connect(lambda v: self.rotation_label.setText(f"{v}°"))
        pos_layout.addWidget(self.rotation_label, 2, 3)
        
        scroll_layout.addWidget(pos_group)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        scroll.viewport().setStyleSheet("background: transparent;")
        main_layout.addWidget(scroll)
    
    def _setup_hotkey(self):
        """Setup global hotkey listener for Ctrl+Shift+C (works in games)."""
        if not KEYBOARD_AVAILABLE:
            print("Hotkey disabled - keyboard library not available")
            return
        
        try:
            # Use keyboard library - uses low-level Windows hooks that work in games
            kb_hook.add_hotkey('ctrl+shift+c', self._on_toggle, suppress=False)
            print("Global hotkey registered: Ctrl+Shift+C (low-level hook)")
        except Exception as e:
            print(f"Failed to register hotkey: {e}")
    
    def _on_toggle(self):
        """Toggle crosshair overlay."""
        self.overlay.toggle()
        is_enabled = self.overlay.isVisible()
        self.enable_btn.setChecked(is_enabled)
        self.enable_btn.setText("Crosshair Enabled" if is_enabled else "Enable Crosshair")
    
    def _offset_btn_style(self):
        return """
            QPushButton {
                background: rgba(30, 33, 40, 0.9);
                border: 1px solid rgba(80, 80, 80, 0.4);
                border-radius: 6px;
                color: #e0e0e0;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
            }
            QPushButton:pressed {
                background: rgba(255, 91, 6, 0.5);
            }
        """
    
    def _change_offset(self, axis, delta):
        """Change X or Y offset value."""
        if axis == "x":
            self._offset_x = max(-500, min(500, self._offset_x + delta))
            self.x_offset_value.setText(str(self._offset_x))
            self._update_setting("offset_x", self._offset_x)
        else:
            self._offset_y = max(-500, min(500, self._offset_y + delta))
            self.y_offset_value.setText(str(self._offset_y))
            self._update_setting("offset_y", self._offset_y)
    
    def _on_shape_change(self, shape_text):
        """Handle shape selection change."""
        shape_map = {
            "Dot": "dot",
            "Cross": "cross",
            "Circle": "circle",
            "T-Shape": "t-shape",
            "Custom Image": "custom"
        }
        shape = shape_map.get(shape_text, "cross")
        self._update_setting("shape", shape)
        self.custom_img_btn.setVisible(shape == "custom")
    
    def _load_custom_image(self):
        """Load a custom crosshair image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Crosshair Image",
            "", "Images (*.png *.jpg *.svg *.bmp)"
        )
        if file_path:
            self._update_setting("custom_image", file_path)
    
    def _update_setting(self, key, value):
        """Update overlay setting and refresh."""
        self.overlay.update_settings(key, value)
    
    def load_ui_from_settings(self):
        """Load UI controls from overlay settings."""
        s = self.overlay.settings
        
        # Update UI to match settings
        shape_map = {"dot": 0, "cross": 1, "circle": 2, "t-shape": 3, "custom": 4}
        self.shape_combo.setCurrentIndex(shape_map.get(s.get("shape", "cross"), 1))
        
        self.main_color_btn.setColor(s.get("color", "#00FF00"))
        self.outline_check.setChecked(s.get("outline_enabled", True))
        self.outline_color_btn.setColor(s.get("outline_color", "#000000"))
        
        self.size_slider.setValue(s.get("size", 20))
        self.thickness_slider.setValue(s.get("thickness", 2))
        self.gap_slider.setValue(s.get("gap", 4))
        self.opacity_slider.setValue(s.get("opacity", 100))
        
        self.dot_check.setChecked(s.get("dot_enabled", True))
        self.dot_size_slider.setValue(s.get("dot_size", 4))
        
        self._offset_x = s.get("offset_x", 0)
        self._offset_y = s.get("offset_y", 0)
        self.x_offset_value.setText(str(self._offset_x))
        self.y_offset_value.setText(str(self._offset_y))
        self.rotation_slider.setValue(s.get("rotation", 0))
        
        # Update enable button state
        if s.get("enabled", False):
            self.overlay.show()
            self.enable_btn.setChecked(True)
            self.enable_btn.setText("Crosshair Enabled")
    
    def cleanup(self):
        """Cleanup resources on close."""
        if KEYBOARD_AVAILABLE:
            try:
                kb_hook.remove_hotkey('ctrl+shift+c')
            except:
                pass
        self.overlay.hide()
    
    # === STYLE HELPERS ===
    def _group_style(self):
        return """
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                color: #FDA903;
                background: rgba(26, 26, 26, 0.5);
                border: 1px solid rgba(255, 91, 6, 0.3);
                border-radius: 14px;
                margin-top: 12px;
                padding: 16px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px;
                color: #FDA903;
            }
            QLabel {
                color: #e0e0e0;
                background: transparent;
            }
            QCheckBox {
                color: #e0e0e0;
                background: transparent;
            }
        """
    
    def _btn_style(self):
        return """
            QPushButton {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 91, 6, 0.5);
                border-radius: 10px;
                padding: 10px 18px;
                color: #e0e0e0;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.2);
                border-color: #FDA903;
            }
        """
    
    def _toggle_btn_style(self):
        return """
            QPushButton {
                background: rgba(26, 26, 26, 0.8);
                border: 2px solid rgba(255, 91, 6, 0.5);
                border-radius: 8px;
                padding: 12px 20px;
                color: #FDA903;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.2);
                border-color: #FDA903;
            }
            QPushButton:checked {
                background: rgba(255, 91, 6, 0.3);
                border-color: #FF5B06;
                color: #ffffff;
            }
        """
    
    def _combo_style(self):
        return """
            QComboBox {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 91, 6, 0.5);
                border-radius: 10px;
                padding: 10px 14px;
                color: #e0e0e0;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #FDA903;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url(python/down-arrow.png);
                width: 10px;
                height: 10px;
            }
            QComboBox::down-arrow:on {
                image: url(python/up-arrow.png);
                width: 10px;
                height: 10px;
            }
            QComboBox QAbstractItemView {
                background: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #FF5B06;
                border: 1px solid #FF5B06;
                border-radius: 8px;
            }
        """
    
    def _animated_combo_style(self):
        """Style for AnimatedComboBox - hides default arrow since we use custom animated one."""
        return """
            QComboBox {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 91, 6, 0.5);
                border-radius: 10px;
                padding: 10px 35px 10px 14px;
                color: #e0e0e0;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #FDA903;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #FF5B06;
                border: 1px solid #FF5B06;
                border-radius: 8px;
            }
        """
    
    def _slider_style(self):
        return """
            QSlider::groove:horizontal { 
                height: 4px; 
                background: rgba(60, 64, 72, 0.8); 
                border-radius: 2px; 
            }
            QSlider::handle:horizontal { 
                background: #1a1a1a; 
                width: 14px; 
                height: 14px; 
                margin: -5px 0; 
                border-radius: 7px;
                border: 2px solid #ffffff;
            }
            QSlider::handle:horizontal:hover { 
                background: #FF5B06; 
            }
            QSlider::sub-page:horizontal { 
                background: rgba(255, 130, 60, 0.8); 
                border-radius: 2px; 
            }
        """
    
    def _spin_style(self):
        return """
            QSpinBox {
                background: rgba(255, 91, 6, 0.7);
                border: 1px solid rgba(255, 130, 60, 0.6);
                border-radius: 10px;
                padding: 8px 12px;
                color: #e0e0e0;
                font-weight: 500;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: transparent;
                border: none;
                width: 20px;
                height: 12px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: rgba(255, 130, 60, 0.3);
            }
            QSpinBox::up-arrow {
                image: url(python/up-arrow.png);
                width: 10px;
                height: 10px;
            }
            QSpinBox::down-arrow {
                image: url(python/down-arrow.png);
                width: 10px;
                height: 10px;
            }
        """
