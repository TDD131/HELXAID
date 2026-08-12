"""
Macro Settings Panel

A panel widget for the sidebar stack to configure macros, profiles, and layers.
"""

import os
import time
import json
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QMenu,
    QSpinBox, QCheckBox, QLineEdit, QGroupBox, QFormLayout, QMessageBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QAbstractItemView, QSlider, QColorDialog, QAbstractSpinBox,
    QRadioButton, QFrame, QGraphicsOpacityEffect, QRubberBand, QApplication, QSizePolicy, QAbstractButton
)
from smooth_scroll import SmoothScrollArea
from PySide6.QtGui import QIcon, QFont, QKeySequence, QAction, QColor, QCursor, QShortcut, QPixmap, QPainter, QPainterPath, QBrush, QPen, QTextDocument, QTextCursor
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, Slot, QMetaObject, QPropertyAnimation, QRect, QEasingCurve, QObject, QEvent, QSize, QVariantAnimation, QAbstractAnimation
# FurycubeHID is NOT imported here -- ButtonAction is lazy-imported where needed (line ~2989).
# Loading this module at import time pulled in the hidapi DLL, adding ~200ms to startup.
from macro_system.integration.hardware_manager import get_hardware_manager
from AnimatedButton import AnimatedCheckBox, FadeHoverButton


def apply_custom_titlebar(widget, color_hex="#000000"):
    """Apply Windows 11 custom title bar color and Windows 10 dark mode."""
    import sys
    if sys.platform != "win32":
        return
        
    try:
        import ctypes
        hwnd = int(widget.winId())
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        
        # 1. Enable base immersive dark mode
        rendering_policy = ctypes.c_int(1)
        result = set_window_attribute(hwnd, 20, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
        if result != 0:
            set_window_attribute(hwnd, 19, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
            
        # 2. Apply Custom Exact Color (Windows 11 ONLY)
        if color_hex:
            color_hex = color_hex.lstrip('#')
            if len(color_hex) == 6:
                r = color_hex[0:2]
                g = color_hex[2:4]
                b = color_hex[4:6]
                bgr_hex = f"0x00{b}{g}{r}"
                bg_color = ctypes.c_int(int(bgr_hex, 16))
                set_window_attribute(hwnd, 35, ctypes.byref(bg_color), ctypes.sizeof(bg_color))
                
                # Text color (light grey)
                text_color = ctypes.c_int(0x00E0E0E0)
                set_window_attribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
    except Exception as e:
        print(f"[Theme] Failed to apply custom title bar: {e}")


def show_custom_question_box(parent, title: str, text: str) -> bool:
    """
    Custom dark QMessageBox question dialog with title bar set to #121212
    and custom button hover styling (No button has transparent gray hover).
    Returns True if Yes is clicked, False otherwise.
    """
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(QMessageBox.Question)
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setDefaultButton(QMessageBox.No)

    apply_custom_titlebar(msg, "#000000")

    msg.setStyleSheet("""
        QMessageBox {
            background-color: #121212;
            color: #e0e0e0;
        }
        QMessageBox QLabel {
            color: #e0e0e0;
            font-family: 'Orbitron', sans-serif;
            font-size: 13px;
            padding: 10px 15px;
        }
    """)

    btn_style_base = """
        QPushButton {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            color: #e0e0e0;
            font-family: 'Orbitron', sans-serif;
            font-size: 12px;
            font-weight: bold;
            padding: 6px 20px;
            min-width: 75px;
            min-height: 28px;
            text-decoration: none;
            outline: none;
        }
    """

    yes_btn = msg.button(QMessageBox.Yes)
    no_btn = msg.button(QMessageBox.No)

    if yes_btn:
        yes_btn.setText("Yes")
        yes_btn.setCursor(Qt.PointingHandCursor)
        yes_btn.setStyleSheet(btn_style_base + """
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.4);
                border-color: #FF5B06;
                color: #ffffff;
                text-decoration: none;
            }
            QPushButton:pressed {
                background: rgba(255, 91, 6, 0.65);
                border-color: #FF5B06;
                color: #ffffff;
                text-decoration: none;
            }
            QPushButton:focus {
                outline: none;
                border-color: #FF5B06;
                text-decoration: none;
            }
        """)

    if no_btn:
        no_btn.setText("No")
        no_btn.setCursor(Qt.PointingHandCursor)
        no_btn.setStyleSheet(btn_style_base + """
            QPushButton:hover {
                background: rgba(160, 160, 160, 0.25);
                border-color: rgba(255, 255, 255, 0.3);
                color: #ffffff;
                text-decoration: none;
            }
            QPushButton:pressed {
                background: rgba(160, 160, 160, 0.4);
                border-color: rgba(255, 255, 255, 0.4);
                color: #ffffff;
                text-decoration: none;
            }
            QPushButton:focus {
                outline: none;
                border-color: rgba(255, 255, 255, 0.3);
                text-decoration: none;
            }
        """)


    res = msg.exec()
    return res == QMessageBox.Yes


class HelxairoMacroGroupCardWidget(QFrame):
    """
    Unified Card Container for a Macro in List of Keys, combining Macro Title Header
    and all its Step items into a single container card.
    """
    def __init__(self, macro_name: str, step_count: int, steps_info: list, list_item=None, list_widget=None, parent=None):
        super().__init__(parent)
        self.list_item = list_item
        self.list_widget = list_widget
        self.step_count = max(1, len(steps_info))
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("HelxairoMacroGroupCardWidget")
        
        self.setStyleSheet("""
            QFrame#HelxairoMacroGroupCardWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QFrame#HelxairoMacroGroupCardWidget:hover {
                background-color: rgba(255, 255, 255, 0.06);
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # 1. Macro Title Header Row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.title_lbl = QLabel(macro_name)
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-weight: bold; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        header_layout.addWidget(self.title_lbl)

        step_suffix = "step" if step_count == 1 else "steps"
        self.count_lbl = QLabel(f"({step_count} {step_suffix})")
        self.count_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        header_layout.addWidget(self.count_lbl)

        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Subtle Horizontal Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); min-height: 1px; max-height: 1px; border: none;")
        main_layout.addWidget(line)

        # 2. Step Rows Container
        for step_idx, (key_name, delay_str) in enumerate(steps_info, start=1):
            step_row = QHBoxLayout()
            step_row.setContentsMargins(4, 2, 4, 2)
            step_row.setSpacing(10)

            step_lbl = QLabel(f"Step {step_idx}")
            step_lbl.setStyleSheet("color: #E0E0E0; font-weight: bold; font-family: 'Orbitron', sans-serif; font-size: 11px;")
            step_row.addWidget(step_lbl)

            key_lbl = QLabel(key_name)
            key_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px;")
            step_row.addWidget(key_lbl)

            step_row.addStretch()

            interval_lbl = QLabel(f"Interval {delay_str}")
            interval_lbl.setStyleSheet("""
                color: #888888;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                background: transparent;
                border: none;
            """)
            step_row.addWidget(interval_lbl)

            main_layout.addLayout(step_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.list_widget and self.list_item:
                self.list_widget.setCurrentItem(self.list_item)
        super().mousePressEvent(event)

    def sizeHint(self):
        w = 0
        if self.list_widget and hasattr(self.list_widget, 'viewport'):
            w = max(0, self.list_widget.viewport().width() - 4)
        calculated_h = 36 + (self.step_count * 28) + 12
        return QSize(w, calculated_h)


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
        self.setObjectName("HelxairoHotkeyBtn")
        self._recording = False
        self._hotkey = default_key
        self.setText(default_key.upper())
        self.setFixedWidth(120)
        self.setFixedHeight(32)
        self.setToolTip("Click to record a new hotkey")
        self.clicked.connect(self._start_recording)
        
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(300)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_frames = [".", "..", "..."]
        self._anim_index = 0
        
        self._update_style()
        
    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton#HelxairoHotkeyBtn {
                    background-color: rgba(30, 30, 30, 0.85);
                    color: #ffffff;
                    border: 1px solid #FF5B06;
                    border-radius: 6px;
                    padding: 0px 10px !important;
                    margin: 0px !important;
                    min-height: 32px !important;
                    max-height: 32px !important;
                    height: 32px !important;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton#HelxairoHotkeyBtn {
                    background-color: rgba(30, 30, 30, 0.85);
                    color: #e0e0e0;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 0px 10px !important;
                    margin: 0px !important;
                    min-height: 32px !important;
                    max-height: 32px !important;
                    height: 32px !important;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton#HelxairoHotkeyBtn:hover {
                    background-color: rgba(40, 40, 40, 0.95);
                    border-color: #FF5B06;
                    color: #ffffff;
                }
            """)
            
    def _on_anim_tick(self):
        if self._recording:
            self._anim_index = (self._anim_index + 1) % len(self._anim_frames)
            self.setText(self._anim_frames[self._anim_index])

    def _start_recording(self):
        self._recording = True
        self._anim_index = 0
        self.setText(self._anim_frames[0])
        self._update_style()
        self.setFocus()
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _stop_recording_ui(self):
        self._recording = False
        if self._anim_timer.isActive():
            self._anim_timer.stop()
        self.setText(self._hotkey.upper())
        self._update_style()

    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()
            if key == Qt.Key_Escape:
                self._stop_recording_ui()
                event.accept()
                return
            
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
            self._stop_recording_ui()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def focusOutEvent(self, event):
        if self._recording:
            self._stop_recording_ui()
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


class SmoothListScroller(QObject):
    """Silky smooth item-aligned wheel scroller with OutCubic animation for QListWidget.
    Intercepts wheel events via eventFilter to prevent outer main scrollbar from scrolling.
    """
    def __init__(self, list_widget: QListWidget):
        super().__init__(list_widget)
        list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget = list_widget
        self.scrollbar = list_widget.verticalScrollBar()
        self._anim = QPropertyAnimation(self.scrollbar, b"value", list_widget)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setDuration(180)
        self._target_val = self.scrollbar.value()
        
        list_widget.installEventFilter(self)
        if list_widget.viewport():
            list_widget.viewport().installEventFilter(self)

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        self.shortcut = QShortcut(QKeySequence("Ctrl+A"), list_widget)
        self.shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.shortcut.activated.connect(self._on_shortcut_activated)

    def _do_select_all(self) -> bool:
        if not self.list_widget.isVisible():
            return False

        # Native Qt DPI-aware local coordinate transformation
        local_pos = self.list_widget.mapFromGlobal(QCursor.pos())
        is_hovered = self.list_widget.rect().contains(local_pos)
        is_focused = self.list_widget.hasFocus()

        if is_hovered or is_focused:
            self.list_widget.setFocus()
            # Explicitly mark every item selected to override invalid selection model anchor states
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item:
                    item.setSelected(True)
            self.list_widget.selectAll()
            return True
        return False

    def _on_shortcut_activated(self):
        self._do_select_all()

    def _get_item_height(self) -> int:
        if self.list_widget.count() > 0:
            first_item = self.list_widget.item(0)
            rect = self.list_widget.visualItemRect(first_item)
            if rect.height() > 0:
                return rect.height()
        return 36  # Default fallback item height

    def _find_parent_panel(self):
        w = self.list_widget.parentWidget()
        while w:
            if hasattr(w, '_delete_profile') or w.inherits("MacroSettingsPanel"):
                return w
            w = w.parentWidget()
        return None

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Wheel:
            if watched in (self.list_widget, self.list_widget.viewport()):
                delta = event.angleDelta().y()
                if delta != 0:
                    min_v = self.scrollbar.minimum()
                    max_v = self.scrollbar.maximum()
                    
                    item_h = self._get_item_height()
                    notches = 1 if delta < 0 else -1
                    scroll_step = notches * item_h
                    
                    if self._anim.state() == QPropertyAnimation.Running:
                        self._target_val = max(min_v, min(max_v, self._target_val + scroll_step))
                    else:
                        self._target_val = max(min_v, min(max_v, self.scrollbar.value() + scroll_step))
                        
                    self._anim.stop()
                    self._anim.setStartValue(self.scrollbar.value())
                    self._anim.setEndValue(int(self._target_val))
                    self._anim.start()
                
                event.accept()
                return True  # Block wheel event from propagating to main window scrollbar!

        elif event.type() in (QEvent.KeyPress, QEvent.ShortcutOverride):
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
            focus = QApplication.focusWidget()
            if focus and isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
                return super().eventFilter(watched, event)

            key = event.key()
            modifiers = event.modifiers()

            # Ctrl + A -> Select All
            if key == Qt.Key_A and (modifiers & Qt.ControlModifier):
                if self._do_select_all():
                    event.accept()
                    return True

            # File Explorer Keyboard Shortcuts
            local_pos = self.list_widget.mapFromGlobal(QCursor.pos())
            if self.list_widget.hasFocus() or self.list_widget.rect().contains(local_pos):
                panel = self._find_parent_panel()
                obj_name = self.list_widget.objectName()

                # Delete / Shift+Delete -> Delete item(s)
                if key == Qt.Key_Delete:
                    if panel:
                        if obj_name == "helxairo_profileList":
                            panel._delete_profile()
                            event.accept()
                            return True
                        elif obj_name in ("helxairo_editorMacroList", "helxairo_activeList"):
                            panel._delete_selected()
                            event.accept()
                            return True

                # Enter / Return -> Load/Activate profile or Edit macro
                elif key in (Qt.Key_Return, Qt.Key_Enter):
                    if panel:
                        if obj_name == "helxairo_profileList":
                            panel._load_selected_profile()
                            event.accept()
                            return True
                        elif obj_name in ("helxairo_editorMacroList", "helxairo_activeList"):
                            panel._edit_selected()
                            event.accept()
                            return True

                # F2 -> Rename profile (focus name field) or Edit macro
                elif key == Qt.Key_F2:
                    if panel:
                        if obj_name == "helxairo_profileList":
                            panel.profile_name.setFocus()
                            panel.profile_name.selectAll()
                            event.accept()
                            return True
                        elif obj_name in ("helxairo_editorMacroList", "helxairo_activeList"):
                            panel._edit_selected()
                            event.accept()
                            return True

                # Ctrl + D / Ctrl + C -> Duplicate profile
                elif (key == Qt.Key_D and (modifiers & Qt.ControlModifier)) or (key == Qt.Key_C and (modifiers & Qt.ControlModifier)):
                    if panel and obj_name == "helxairo_profileList":
                        panel._duplicate_selected_profile()
                        event.accept()
                        return True

                # Ctrl + N -> New Profile
                elif key == Qt.Key_N and (modifiers & Qt.ControlModifier):
                    if panel and obj_name == "helxairo_profileList":
                        panel._new_profile()
                        event.accept()
                        return True

        return super().eventFilter(watched, event)


def enable_rubber_band_selection(list_widget: QListWidget):
    """Enables QRubberBand drag multi-selection with 60fps auto-scroll and silky smooth wheel scrolling."""
    list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
    # NOTE FOR AGENTS / DEVELOPERS: DO NOT re-enable horizontal scrollbars for list_widget; keep ScrollBarAlwaysOff.
    list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    list_widget._smoother = SmoothListScroller(list_widget)
    
    rubber_band = QRubberBand(QRubberBand.Rectangle, list_widget.viewport())
    rubber_band.setStyleSheet("""
        QRubberBand {
            background-color: rgba(255, 91, 6, 0.2);
            border: 1px solid rgba(255, 91, 6, 0.7);
        }
    """)
    list_widget._rubber_band = rubber_band
    list_widget._rubber_band_origin = None
    list_widget._rubber_band_start_vbar = 0
    list_widget._rubber_band_active = False
    
    scroll_timer = QTimer(list_widget)
    scroll_timer.setInterval(16)  # 60fps frame rate for micro-step auto-scroll
    list_widget._auto_scroll_step = 0

    def _update_selection_on_drag():
        if not getattr(list_widget, '_rubber_band_active', False) or list_widget._rubber_band_origin is None:
            return
            
        current_pos = list_widget.viewport().mapFromGlobal(QCursor.pos())
        current_vbar = list_widget.verticalScrollBar().value()
        vbar_delta = current_vbar - getattr(list_widget, '_rubber_band_start_vbar', 0)
        
        origin = list_widget._rubber_band_origin
        adjusted_origin = QPoint(origin.x(), origin.y() - vbar_delta)
        
        rect = QRect(adjusted_origin, current_pos).normalized()
        rubber_band.setGeometry(rect)
        
        modifiers = QApplication.keyboardModifiers()
        is_multi_modifier = bool(modifiers & (Qt.ControlModifier | Qt.ShiftModifier))
        
        list_widget.blockSignals(True)
        selection_changed = False
        try:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                item_rect = list_widget.visualItemRect(item)
                intersects = rect.intersects(item_rect)
                if intersects:
                    if not item.isSelected():
                        item.setSelected(True)
                        selection_changed = True
                elif not is_multi_modifier:
                    if item.isSelected():
                        item.setSelected(False)
                        selection_changed = True
        finally:
            list_widget.blockSignals(False)
            
        if selection_changed:
            list_widget.itemSelectionChanged.emit()

    def _on_scroll_timer():
        step = getattr(list_widget, '_auto_scroll_step', 0)
        if step != 0:
            vbar = list_widget.verticalScrollBar()
            vbar.setValue(vbar.value() + step)
            _update_selection_on_drag()
        else:
            scroll_timer.stop()

    scroll_timer.timeout.connect(_on_scroll_timer)
    
    orig_mousePressEvent = list_widget.mousePressEvent
    orig_mouseMoveEvent = list_widget.mouseMoveEvent
    orig_mouseReleaseEvent = list_widget.mouseReleaseEvent
    
    def _mousePressEvent(event):
        if event.button() == Qt.LeftButton:
            item = list_widget.itemAt(event.pos())
            list_widget._rubber_band_origin = event.pos()
            list_widget._rubber_band_start_vbar = list_widget.verticalScrollBar().value()
            rubber_band.setGeometry(QRect(event.pos(), event.pos()))
            rubber_band.show()
            list_widget._rubber_band_active = True
            list_widget._auto_scroll_step = 0
            
            if not item and not (event.modifiers() & Qt.ControlModifier):
                list_widget.clearSelection()
                
        orig_mousePressEvent(event)
        
    def _mouseMoveEvent(event):
        if getattr(list_widget, '_rubber_band_active', False) and list_widget._rubber_band_origin is not None:
            pos = event.pos()
            viewport_h = list_widget.viewport().height()
            margin = 18
            
            if pos.y() < margin:
                speed = max(2, (margin - pos.y()) // 2)
                list_widget._auto_scroll_step = -speed
                if not scroll_timer.isActive():
                    scroll_timer.start()
            elif pos.y() > viewport_h - margin:
                speed = max(2, (pos.y() - (viewport_h - margin)) // 2)
                list_widget._auto_scroll_step = speed
                if not scroll_timer.isActive():
                    scroll_timer.start()
            else:
                list_widget._auto_scroll_step = 0
                if scroll_timer.isActive():
                    scroll_timer.stop()

            _update_selection_on_drag()
            return
        orig_mouseMoveEvent(event)
        
    def _mouseReleaseEvent(event):
        was_active = getattr(list_widget, '_rubber_band_active', False)
        if event.button() == Qt.LeftButton and was_active:
            if scroll_timer.isActive():
                scroll_timer.stop()
            list_widget._auto_scroll_step = 0
            rubber_band.hide()
            list_widget._rubber_band_active = False
            list_widget._rubber_band_origin = None
            list_widget._rubber_band_start_vbar = 0
            list_widget.itemSelectionChanged.emit()
        orig_mouseReleaseEvent(event)
        
    list_widget.mousePressEvent = _mousePressEvent
    list_widget.mouseMoveEvent = _mouseMoveEvent
    list_widget.mouseReleaseEvent = _mouseReleaseEvent


class FloatingToast(QFrame):
    """Sleek floating toast notification overlay panel for HELXAID."""
    _active_toasts = []

    def __init__(self, parent, title: str, message: str, duration: int = 3500):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setObjectName("floatingToast")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("toastCard")
        self.card.setAttribute(Qt.WA_StyledBackground)
        self.card.setStyleSheet("""
            QFrame#toastCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QFrame#toastCard:hover {
                border-color: rgba(255, 91, 6, 0.4);
            }
        """)

        layout = QHBoxLayout(self.card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(0)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 600; background: transparent; border: none;")
        text_layout.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent; border: none;")
        text_layout.addWidget(msg_lbl)

        layout.addLayout(text_layout)

        outer_layout.addWidget(self.card)
        self.adjustSize()
        
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        
        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_in.setDuration(220)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.start()
        
        if duration > 0:
            QTimer.singleShot(duration, self.fade_out)

    @classmethod
    def show_toast(cls, parent, title: str, message: str, duration: int = 3500):
        if parent is None:
            return None
        for t in list(cls._active_toasts):
            try:
                t.close()
                t.deleteLater()
            except Exception:
                pass
        cls._active_toasts.clear()

        toast = cls(parent, title, message, duration)
        cls._active_toasts.append(toast)

        parent_rect = parent.rect()
        toast_width = toast.width()
        x = parent_rect.x() + (parent_rect.width() - toast_width) // 2
        y = parent_rect.y() + 18
        toast.move(x, y)
        toast.show()
        toast.raise_()
        return toast

    def fade_out(self):
        if hasattr(self, "_anim_out") and self._anim_out.state() == QPropertyAnimation.Running:
            return
        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_out.setDuration(250)
        self._anim_out.setStartValue(self._opacity_effect.opacity())
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(self._on_fade_out_finished)
        self._anim_out.start()

    def _on_fade_out_finished(self):
        if self in FloatingToast._active_toasts:
            FloatingToast._active_toasts.remove(self)
        self.close()
        self.deleteLater()


class SafeSpinBox(QSpinBox):
    """QSpinBox with 400ms hover delay protection before accepting mouse wheel scrolling.
    Prevents accidental value changes and scroll-trapping when scrolling past spinboxes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._can_wheel = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(400)  # Must hover continuously for 400ms
        self._hover_timer.timeout.connect(self._on_hover_timeout)

    def _on_hover_timeout(self):
        self._can_wheel = True

    def enterEvent(self, event):
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._can_wheel = False
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if self._can_wheel or self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class AdaptiveSpinBox(SafeSpinBox):
    """QSpinBox with dynamic adaptive font sizing based on text length and 100ms hover wheel protection."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.valueChanged.connect(self._adjust_font_size)

    def setSuffix(self, suffix: str):
        super().setSuffix(suffix)
        self._adjust_font_size()

    def setValue(self, val: int):
        super().setValue(val)
        self._adjust_font_size(val)

    def showEvent(self, event):
        super().showEvent(event)
        self._adjust_font_size()

    def _adjust_font_size(self, val=None):
        if val is None:
            val = self.value()
        text_str = f"{val}{self.suffix()}"
        length = len(text_str)
        if length <= 4:
            size = 11
        elif length == 5:
            size = 10
        elif length == 6:
            size = 9
        else:
            size = 8

        line_edit = self.findChild(QLineEdit)
        if line_edit:
            line_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: transparent;
                    color: #e0e0e0;
                    border: none;
                    padding: 0px;
                    margin: 0px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: {int(size)}px;
                    font-weight: bold;
                    selection-background-color: #FF5B06;
                }}
            """)


class DeviceWarningOverlay(QWidget):
    """
    Overlay panel that displays a warning when the mouse is disconnected
    or not a Furycube G13 Pro device. Used in DPI tab, Advanced settings,
    and Wireless Pairing sections.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setObjectName("deviceWarningOverlay")
        self.setMinimumHeight(80)
        self.setMinimumWidth(300)
        self.setStyleSheet("""
            QWidget#deviceWarningOverlay {
                background: rgba(255, 60, 60, 0.15);
                border: 1px solid rgba(255, 60, 60, 0.4);
                border-radius: 8px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)
        
        # Warning icon
        icon_label = QLabel("!")
        icon_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                font-size: 24px;
                font-weight: bold;
                background: transparent;
            }
        """)
        icon_label.setFixedWidth(30)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        # Warning text container
        text_container = QWidget()
        text_container.setStyleSheet("background: transparent;")
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        self._title_label = QLabel("Device Not Connected")
        self._title_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            }
        """)
        text_layout.addWidget(self._title_label)
        
        self._desc_label = QLabel("Connect your Furycube G13 Pro to use this feature.")
        self._desc_label.setStyleSheet("""
            QLabel {
                color: #aa8888;
                font-size: 11px;
                background: transparent;
            }
        """)
        text_layout.addWidget(self._desc_label)
        
        layout.addWidget(text_container, 1)
        # Show by default - will be hidden if device is connected
        self.show()
    
    def set_disconnected(self):
        """Set overlay to show disconnected state."""
        self._title_label.setText("Device Not Connected")
        self._desc_label.setText("Connect your Furycube G13 Pro to use this feature.")
        self.show()
    
    def set_wrong_device(self, device_name: str = ""):
        """Set overlay to show wrong device state."""
        self._title_label.setText("Unsupported Device")
        if device_name:
            self._desc_label.setText(f"Connected device '{device_name}' is not a Furycube G13 Pro.")
        else:
            self._desc_label.setText("The connected device is not a Furycube G13 Pro.")
        self.show()
    
    def check_and_update(self, hw_manager):
        """
        Check hardware state and update overlay visibility.
        Returns True if device is connected and correct, False otherwise.
        
        Args:
            hw_manager: HardwareManager instance to query state from
            
        Returns:
            bool: True if device is OK (connected + correct device), False otherwise
        """
        try:
            state = hw_manager.get_state()
            connected = state.get('connected', False)
            
            if not connected:
                self.set_disconnected()
                return False
            
            # Check if device is Furycube G13 Pro
            # The HardwareManager/FurycubeHID only connects to Furycube devices,
            # so if connected=True, it's the correct device
            self.hide()
            return True
            
        except Exception as e:
            print(f"[DeviceWarningOverlay] Error checking state: {e}")
            self.set_disconnected()
            return False


class MacroStatusCheckWidget(QWidget):
    """
    Pure QPainter Vector Status Check/Uncheck Indicator with Smooth QVariantAnimation.
    Matches the smooth 150ms checkmark drawing & color transition of AnimatedCheckBox in main settings.
    - Checked (True): Green checkmark (#00FF88) with subtle green glow on hover
    - Unchecked (False): Grey circle outline (#777777) with subtle white glow on hover
    - Zero event propagation leak & zero state desync.
    
    Component Name: MacroStatusCheckWidget
    """
    clicked = Signal()

    def __init__(self, is_enabled=True, parent=None):
        super().__init__(parent)
        self.setObjectName("MacroStatusCheckWidget")
        self._is_enabled = is_enabled
        self._progress = 1.0 if is_enabled else 0.0
        self.setFixedSize(20, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to toggle Macro ON/OFF")
        
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.valueChanged.connect(self._on_anim_value_changed)

    def isChecked(self) -> bool:
        return self._is_enabled

    def set_enabled_state(self, state: bool):
        target_dir = QAbstractAnimation.Forward if state else QAbstractAnimation.Backward
        
        # If animation is currently running towards this state, let it finish smoothly without interrupting or snapping _progress
        if self._anim.state() == QAbstractAnimation.Running:
            if self._anim.direction() == target_dir:
                return
            else:
                self._is_enabled = state
                self._anim.setDirection(target_dir)
                return

        if self._is_enabled != state:
            self._is_enabled = state
            self._anim.setDirection(target_dir)
            self._progress = 0.05 if state else 0.95
            self._anim.start()
        elif not (0.0 < self._progress < 1.0):
            self._progress = 1.0 if state else 0.0
            self.update()

    def _on_anim_value_changed(self, value):
        self._progress = float(value)
        self.update()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            event.accept()
            print(f"[HELXAIRO-TOGGLE] MacroStatusCheckWidget clicked! Current state={self._is_enabled}")
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        rect = self.rect()
        w, h = rect.width(), rect.height()
        
        is_hovered = self.underMouse()
        
        # Subtle hover background glow for interactive toggle feedback
        if is_hovered:
            bg_alpha = int(35 * self._progress) if self._progress > 0 else 25
            bg_color = QColor(0, 255, 136, bg_alpha) if self._progress > 0 else QColor(255, 255, 255, 25)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(bg_color))
            painter.drawEllipse(rect.adjusted(1, 1, -1, -1))

        # 1. Unchecked Grey Circle Outline (smoothly fades out as _progress -> 1.0)
        circle_alpha = int(255 * (1.0 - self._progress))
        if circle_alpha > 0:
            circle_color = QColor(119, 119, 119, circle_alpha) if not is_hovered else QColor(204, 204, 204, circle_alpha)
            pen = QPen(circle_color, 1.8, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            center = rect.center()
            radius = int(w * 0.34)
            painter.drawEllipse(center, radius, radius)
        
        # 2. Checked Green Checkmark (smoothly draws path & fades in as _progress > 0)
        if self._progress > 0:
            target_green = QColor("#00FF88") if not is_hovered else QColor("#55FFB0")
            r = int(119 + (target_green.red() - 119) * self._progress)
            g = int(119 + (target_green.green() - 119) * self._progress)
            b = int(119 + (target_green.blue() - 119) * self._progress)
            pen_color = QColor(r, g, b, int(255 * self._progress))
            
            pen = QPen(pen_color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            p1_x, p1_y = w * 0.22, h * 0.52
            p2_x, p2_y = w * 0.42, h * 0.72
            p3_x, p3_y = w * 0.78, h * 0.28
            
            threshold = 0.33
            
            path = QPainterPath()
            path.moveTo(p1_x, p1_y)
            
            if self._progress <= threshold:
                t = self._progress / threshold
                cur_x = p1_x + (p2_x - p1_x) * t
                cur_y = p1_y + (p2_y - p1_y) * t
                path.lineTo(cur_x, cur_y)
            else:
                path.lineTo(p2_x, p2_y)
                t = (self._progress - threshold) / (1.0 - threshold)
                cur_x = p2_x + (p3_x - p2_x) * t
                cur_y = p2_y + (p3_y - p2_y) * t
                path.lineTo(cur_x, cur_y)
                
            painter.drawPath(path)


class HelxairoMacroItemWidget(QFrame):
    """
    Expandable HELXAIL-style Accordion Dropdown Card Widget for Active Macros list.
    
    Header Row (2-Line HELXAIL Layout):
    - Status Icon (Check / Uncheck on left)
    - Vertical Title VBox:
      - Line 1: Macro Name (White bold Orbitron, 13px)
      - Line 2: Subtitle / Profile name (Muted grey #999999 Orbitron, 11px)
    - Expand/Collapse Accordion Arrow Button (far right)
    
    Details Frame (Expandable Dropdown Body):
    - Hotkey pill
    - Interval pill
    - Action target pill
    
    Component Name: HelxairoMacroItemWidget
    """
    def __init__(self, macro, profile_name, list_item, list_widget, parent=None):
        super().__init__(parent)
        self.macro = macro
        self.profile_name = profile_name
        self.list_item = list_item
        self.list_widget = list_widget
        self._is_expanded = False
        
        self._click_count = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_click_timer_timeout)
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("HelxairoMacroItemWidget")
        self._setup_ui()

    def sizeHint(self):
        """Dynamic size hint matching QListWidget viewport width and content height."""
        w = 0
        if self.list_widget and hasattr(self.list_widget, 'viewport'):
            w = max(0, self.list_widget.viewport().width() - 18)
        h = 38
        if hasattr(self, 'name_edit') and self.name_edit.isVisible():
            h = max(38, self.name_edit.height() + 14)
        elif hasattr(self, 'title_lbl') and hasattr(self, 'header_frame'):
            total_w = self.width() if self.width() > 100 else (self.list_widget.viewport().width() - 20 if hasattr(self, 'list_widget') and self.list_widget and hasattr(self.list_widget, 'viewport') and self.list_widget.viewport().width() > 100 else 260)
            status_w = self.status_icon.width() if hasattr(self, 'status_icon') and self.status_icon else 20
            hotkey_w = self.hotkey_lbl.sizeHint().width() if hasattr(self, 'hotkey_lbl') and self.hotkey_lbl else 60
            spacing = 32
            avail_w = max(40, total_w - status_w - hotkey_w - spacing)
            
            lbl_h = self.title_lbl.heightForWidth(avail_w)
            h = max(38, lbl_h + 14)
        elif self.layout():
            h = max(38, self.layout().sizeHint().height())
        return QSize(w, h)

    def set_selected_state(self, is_selected: bool):
        """Update selected visual style of item card frame with inverted color theme."""
        if getattr(self, '_is_selected', None) == is_selected:
            return
        self._is_selected = is_selected
        if is_selected:
            self.setStyleSheet("""
                QFrame#HelxairoMacroItemWidget {
                    background-color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                }
                QFrame#HelxairoMacroItemWidget:hover {
                    background-color: #F2F2F2;
                    border-color: rgba(255, 91, 6, 0.35);
                }
                QFrame#MacroHeaderFrame {
                    background: transparent;
                    border: none;
                }
            """)
            if hasattr(self, 'title_lbl'):
                self.title_lbl.setStyleSheet("color: #000000; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent; padding: 0px; margin: 0px;")
            if hasattr(self, 'name_edit'):
                self.name_edit.setStyleSheet("""
                    QTextEdit#MacroItemInlineEdit {
                        background: transparent;
                        color: #000000;
                        border: none;
                        padding: 0px;
                        margin: 0px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 12px;
                        font-weight: bold;
                        selection-background-color: #000000;
                        selection-color: #FFFFFF;
                    }
                """)
            if hasattr(self, 'hotkey_lbl'):
                self.hotkey_lbl.setStyleSheet("color: #333333; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent;")
        else:
            self.setStyleSheet("""
                QFrame#HelxairoMacroItemWidget {
                    background-color: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                }
                QFrame#HelxairoMacroItemWidget:hover {
                    background-color: rgba(255, 255, 255, 0.06);
                    border-color: rgba(255, 91, 6, 0.35);
                }
                QFrame#MacroHeaderFrame {
                    background: transparent;
                    border: none;
                }
            """)
            if hasattr(self, 'title_lbl'):
                self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent; padding: 0px; margin: 0px;")
            if hasattr(self, 'name_edit'):
                self.name_edit.setStyleSheet("""
                    QTextEdit#MacroItemInlineEdit {
                        background: transparent;
                        color: #FFFFFF;
                        border: none;
                        padding: 0px;
                        margin: 0px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 12px;
                        font-weight: bold;
                        selection-background-color: rgba(255, 91, 6, 0.4);
                        selection-color: #FFFFFF;
                    }
                """)
            if hasattr(self, 'hotkey_lbl'):
                self.hotkey_lbl.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent;")

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header Frame (Dynamic container height)
        self.header_frame = QFrame()
        self.header_frame.setObjectName("MacroHeaderFrame")
        self.header_frame.setMinimumHeight(30)
        
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(10, 4, 10, 4)
        header_layout.setSpacing(8)
        
        # Status Icon (Pure Vector QPainter Toggle Button - Clickable to toggle macro on/off)
        is_enabled = getattr(self.macro, 'enabled', True)
        self.status_icon = MacroStatusCheckWidget(is_enabled=is_enabled)
        self.status_icon.clicked.connect(self._on_status_icon_clicked)
        header_layout.addWidget(self.status_icon, 0, Qt.AlignVCenter)
        
        # Title Label for Display Mode (Native Qt.AlignVCenter for 100% vertical centering)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("MacroItemTitle")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent; padding: 0px; margin: 0px;")
        header_layout.addWidget(self.title_lbl, 1, Qt.AlignVCenter)

        # Inline Name Edit Input (QTextEdit used when double-clicked to edit)
        self.name_edit = QTextEdit()
        self.name_edit.setObjectName("MacroItemInlineEdit")
        self.name_edit.setMinimumHeight(24)
        self.name_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.name_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.name_edit.setVisible(False)
        self.name_edit.textChanged.connect(self._adjust_edit_height)
        self.name_edit.installEventFilter(self)
        header_layout.addWidget(self.name_edit, 1, Qt.AlignVCenter)
        
        # Extract Hotkey
        trigger_str = ""
        trigger = getattr(self.macro, 'trigger', None)
        if trigger:
            if getattr(trigger, 'button', None):
                trigger_str = trigger.button.upper()
            elif getattr(trigger, 'key', None):
                trigger_str = trigger.key.upper()
        if not trigger_str:
            trigger_str = "No Hotkey"
            
        self.hotkey_lbl = QLabel(f"  |  {trigger_str}")
        self.hotkey_lbl.setObjectName("MacroItemHotkey")
        self.hotkey_lbl.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold; font-family: 'Orbitron', sans-serif; background: transparent;")
        header_layout.addWidget(self.hotkey_lbl, 0, Qt.AlignVCenter)
        
        main_layout.addWidget(self.header_frame, 1)
        self._update_display_name()
        self.set_selected_state(getattr(self, '_is_selected', False))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.list_widget and self.list_item:
                self.list_widget.setCurrentItem(self.list_item)
            
            self._click_count += 1
            if self._click_timer.isActive():
                self._click_timer.stop()
            
            if self._click_count >= 3:
                self._handle_click_action(3)
            else:
                self._click_timer.start(280)
        super().mousePressEvent(event)

    def _on_click_timer_timeout(self):
        count = self._click_count
        self._handle_click_action(count)

    def _find_macro_panel(self):
        """Traverse parent tree to find MacroSettingsPanel."""
        curr = self.parent()
        while curr is not None:
            if hasattr(curr, '_toggle_macro') or hasattr(curr, '_edit_selected'):
                return curr
            curr = curr.parent() if hasattr(curr, 'parent') else None
        return None

    def _update_item_size_hint(self):
        """Update QListWidgetItem size hint dynamically so QListWidget resizes item row height."""
        if hasattr(self, 'list_item') and self.list_item and hasattr(self, 'list_widget') and self.list_widget:
            self.updateGeometry()
            new_size = self.sizeHint()
            if self.list_item.sizeHint() != new_size:
                self.list_item.setSizeHint(new_size)
                if hasattr(self.list_widget, 'doItemsLayout'):
                    self.list_widget.doItemsLayout()

    def _shake_header_frame(self):
        """Vibrate / Shake header_frame horizontally as visual error feedback when line limit is reached."""
        target_widget = self.header_frame if hasattr(self, 'header_frame') and self.header_frame else self
        if not target_widget:
            return
            
        anim = QPropertyAnimation(target_widget, b"pos", self)
        anim.setDuration(280)
        orig_pos = target_widget.pos()
        
        anim.setKeyValueAt(0.0, orig_pos)
        anim.setKeyValueAt(0.15, orig_pos + QPoint(-8, 0))
        anim.setKeyValueAt(0.30, orig_pos + QPoint(8, 0))
        anim.setKeyValueAt(0.45, orig_pos + QPoint(-6, 0))
        anim.setKeyValueAt(0.60, orig_pos + QPoint(6, 0))
        anim.setKeyValueAt(0.75, orig_pos + QPoint(-3, 0))
        anim.setKeyValueAt(0.90, orig_pos + QPoint(3, 0))
        anim.setKeyValueAt(1.0, orig_pos)
        
        self._shake_anim = anim
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _show_line_limit_toast(self):
        """Show standard FloatingToast notification and shake header_frame horizontally when 5-line limit is reached."""
        self._shake_header_frame()
        panel = self._find_macro_panel()
        target = panel if panel else self.window()
        if target:
            FloatingToast.show_toast(target, "Limit Exceeded", "Maximum 5 lines allowed for macro title")

    def _adjust_edit_height(self):
        """Dynamically fit name_edit height to content so it expands like WhatsApp message bubble."""
        if not hasattr(self, 'name_edit'):
            return
        if getattr(self, '_is_adjusting_height', False):
            return
        self._is_adjusting_height = True
        try:
            text = self.name_edit.toPlainText()
            lines = text.split('\n')
            if len(lines) > 5:
                truncated = '\n'.join(lines[:5])
                self.name_edit.blockSignals(True)
                self.name_edit.setPlainText(truncated)
                cursor = self.name_edit.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.name_edit.setTextCursor(cursor)
                self.name_edit.blockSignals(False)
                self._show_line_limit_toast()

            total_w = self.width() if self.width() > 100 else (self.list_widget.viewport().width() - 20 if hasattr(self, 'list_widget') and self.list_widget and hasattr(self.list_widget, 'viewport') and self.list_widget.viewport().width() > 100 else 260)
            status_w = self.status_icon.width() if hasattr(self, 'status_icon') and self.status_icon else 20
            hotkey_w = self.hotkey_lbl.sizeHint().width() if hasattr(self, 'hotkey_lbl') and self.hotkey_lbl else 60
            spacing = 32
            avail_w = max(40, total_w - status_w - hotkey_w - spacing)

            doc = self.name_edit.document()
            doc.setDocumentMargin(0)
            doc.setTextWidth(avail_w)
            raw_h = int(doc.size().height())

            if len(lines) <= 1:
                doc_h = max(18, min(20, raw_h))
            else:
                doc_h = max(24, raw_h + 4)

            if self.name_edit.height() != doc_h:
                self.name_edit.setFixedHeight(doc_h)
                self._update_item_size_hint()
        finally:
            self._is_adjusting_height = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(30, self._adjust_edit_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() > 0 and event.oldSize().width() != event.size().width():
            if hasattr(self, 'name_edit'):
                self._adjust_edit_height()

    def _update_display_name(self):
        name = getattr(self.macro, 'name', 'Unnamed Macro')
        for sym in ("✓", "○", "✔"):
            if name.startswith(sym):
                name = name[len(sym):].strip()
        
        trigger_str = ""
        trigger = getattr(self.macro, 'trigger', None)
        if trigger:
            if getattr(trigger, 'button', None):
                trigger_str = trigger.button.upper()
            elif getattr(trigger, 'key', None):
                trigger_str = trigger.key.upper()
        if not trigger_str:
            trigger_str = "No Hotkey"
            
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(name)
            self.title_lbl.setVisible(True)
        if hasattr(self, 'name_edit'):
            self.name_edit.setPlainText(name)
            self.name_edit.setVisible(False)
            self._adjust_edit_height()
        self.hotkey_lbl.setText(f"  |  {trigger_str}")

    def _start_inline_rename(self):
        """Start inline renaming of macro title directly in item header."""
        if getattr(self, '_is_renaming', False):
            return
        self._is_renaming = True
        
        name = getattr(self.macro, 'name', 'Unnamed Macro')
        for sym in ("✓", "○", "✔"):
            if name.startswith(sym):
                name = name[len(sym):].strip()
                
        self.set_selected_state(True)
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setVisible(False)
        if hasattr(self, 'name_edit'):
            self.name_edit.setVisible(True)
            self.name_edit.setPlainText(name)
            self._adjust_edit_height()
            self.name_edit.setFocus()
            self.name_edit.selectAll()

    def _finish_inline_rename(self):
        """Save inline renamed macro title and restore label view smoothly without reloading list."""
        if not getattr(self, '_is_renaming', False):
            return
        self._is_renaming = False
        
        new_name = self.name_edit.toPlainText().strip() if hasattr(self, 'name_edit') else ""
        if new_name and hasattr(self, 'macro') and self.macro:
            self.macro.name = new_name
            panel = self._find_macro_panel()
            if panel and hasattr(panel, '_bridge') and panel._bridge and hasattr(panel._bridge, 'profile_manager') and panel._bridge.profile_manager:
                panel._bridge.profile_manager.save_all()
                    
        self._update_display_name()
        
        if hasattr(self, 'list_widget') and self.list_widget and hasattr(self, 'list_item') and self.list_item:
            self.list_widget.setCurrentItem(self.list_item)

    def eventFilter(self, obj, event):
        if obj is getattr(self, 'name_edit', None):
            if event.type() == QEvent.FocusOut:
                if getattr(self, '_is_renaming', False):
                    self._finish_inline_rename()
                return False
            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self._is_renaming = False
                    self.name_edit.setReadOnly(True)
                    self.name_edit.setTextInteractionFlags(Qt.NoTextInteraction)
                    self._update_display_name()
                    return True
                elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if event.modifiers() & Qt.ShiftModifier:
                        lines = self.name_edit.toPlainText().split('\n')
                        if len(lines) >= 5:
                            self._show_line_limit_toast()
                            return True
                    else:
                        self._finish_inline_rename()
                        return True
        return super().eventFilter(obj, event)

    def _handle_click_action(self, count):
        self._click_timer.stop()
        self._click_count = 0
        if count == 1:
            # 1x click: Select item only
            pass
        elif count >= 2:
            # 2x click: Rename title directly in item panel!
            self._start_inline_rename()

    def _on_status_icon_clicked(self, *args):
        """Clicking on status toggle button directly toggles this macro's enable/disable state."""
        macro_id = getattr(self.macro, 'id', 'unknown')
        macro_name = getattr(self.macro, 'name', 'unknown')
        curr_enabled = getattr(self.macro, 'enabled', None)
        print(f"[HELXAIRO-TOGGLE] _on_status_icon_clicked: macro_id={macro_id}, name='{macro_name}', curr_enabled={curr_enabled}")
        
        if self.list_widget and self.list_item:
            self.list_widget.setCurrentItem(self.list_item)
            
        panel = self._find_macro_panel()
        if panel:
            print(f"[HELXAIRO-TOGGLE] Found MacroSettingsPanel: {panel}")
            if hasattr(panel, '_toggle_macro'):
                panel._toggle_macro(self.macro)
            elif hasattr(panel, '_toggle_selected_macro'):
                panel._toggle_selected_macro()
        else:
            print("[HELXAIRO-TOGGLE] ERR: Could not find MacroSettingsPanel in parent tree!")


class HelxairoLowIntervalWarningOverlayPanel(QWidget):
    """
    Floating overlay panel warning user about low intervals (<40ms or <5ms).
    Matching HELXAIL floating guide / edit panel style.
    
    Component Name: HelxairoLowIntervalWarningOverlayPanel
    """
    def __init__(self, parent_panel, on_proceed_callback, title="Low Interval Warning", description=None, proceed_text="Proceed", is_extreme_risk=False):
        super().__init__(parent_panel)
        self.parent_panel = parent_panel
        self.on_proceed_callback = on_proceed_callback
        self.panel_title = title
        self.panel_desc = description if description else (
            "Setting an interval below 40ms may cause high CPU load or system instability due to extremely rapid input rates.\n\nAre you sure you want to proceed?"
        )
        self.proceed_text = proceed_text
        self.is_extreme_risk = is_extreme_risk
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("HelxairoLowIntervalWarningOverlayPanel")
        
        self.setGeometry(0, 0, parent_panel.width(), parent_panel.height())
        self._setup_ui()
        
        # Shortcut Esc to close (Cancel)
        self._esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._esc_shortcut.activated.connect(self.close)

    def _setup_ui(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        warning_icon_path = os.path.join(script_dir, "UI Icons", "warning-icon.svg").replace('\\', '/')

        overlay_bg = "rgba(105, 12, 12, 0.52)" if self.is_extreme_risk else "rgba(0, 0, 0, 0.55)"
        card_bg_border = (
            "background-color: rgba(26, 12, 14, 0.98); border: 1px solid rgba(239, 68, 68, 0.55);"
            if self.is_extreme_risk else
            "background-color: rgba(22, 22, 26, 0.98); border: none;"
        )

        self.setStyleSheet(f"""
            QWidget#HelxairoLowIntervalWarningOverlayPanel {{
                background-color: {overlay_bg};
            }}
            QFrame#HelxairoWarningCard {{
                {card_bg_border}
                border-radius: 14px;
            }}
            QWidget#HelxairoWarningTitleBar {{
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QScrollArea#HelxairoWarningScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea#HelxairoWarningScrollArea QScrollBar:vertical {{
                background: rgba(15, 15, 18, 0.6);
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }}
            QScrollArea#HelxairoWarningScrollArea QScrollBar::handle:vertical {{
                background: #FF5B06;
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollArea#HelxairoWarningScrollArea QScrollBar::handle:vertical:hover {{
                background: #FDA903;
            }}
            QScrollArea#HelxairoWarningScrollArea QScrollBar::add-line:vertical, QScrollArea#HelxairoWarningScrollArea QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollArea#HelxairoWarningScrollArea QScrollBar::add-page:vertical, QScrollArea#HelxairoWarningScrollArea QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        
        self.card = QFrame()
        self.card.setObjectName("HelxairoWarningCard")
        self.card.setFixedSize(450, 240)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 16)
        card_layout.setSpacing(14)
        
        # 1. Header Title Bar
        title_bar = QWidget()
        title_bar.setObjectName("HelxairoWarningTitleBar")
        title_bar.setFixedHeight(44)
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(18, 0, 18, 0)
        title_layout.setSpacing(10)
        
        # SVG Warning Icon (No emoji, vector SVG icon)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setPixmap(QPixmap(warning_icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_lbl.setStyleSheet("background: transparent;")
        
        title_label = QLabel(self.panel_title)
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        
        title_layout.addWidget(icon_lbl)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        card_layout.addWidget(title_bar)
        
        # 2. Body Warning Message in QScrollArea with larger text (13px)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("HelxairoWarningScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 4, 16, 4)
        scroll_layout.setSpacing(0)
        
        msg_lbl = QLabel(self.panel_desc)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #D8D8D8; font-family: 'Orbitron', sans-serif; font-size: 13px; line-height: 1.5; background: transparent;")
        scroll_layout.addWidget(msg_lbl)
        
        scroll_area.setWidget(scroll_content)
        card_layout.addWidget(scroll_area, 1)
        
        # 3. Footer Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(20, 0, 20, 0)
        btn_layout.setSpacing(12)
        
        if self.is_extreme_risk:
            cancel_btn = FadeHoverButton("Cancel", is_secondary=False, border_radius=8.0, color_mode="green")
            proceed_btn = FadeHoverButton(self.proceed_text, is_secondary=False, border_radius=8.0, color_mode="red")
        else:
            cancel_btn = FadeHoverButton("Cancel", is_secondary=True, border_radius=8.0)
            proceed_btn = FadeHoverButton(self.proceed_text, is_secondary=False, border_radius=8.0, color_mode="default")
            
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.clicked.connect(self.close)
        
        btn_w = max(110, len(self.proceed_text) * 9 + 20)
        proceed_btn.setFixedSize(btn_w, 36)
        proceed_btn.clicked.connect(self._on_proceed)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(proceed_btn)
        
        card_layout.addLayout(btn_layout)
        
        # Center card in outer layout
        outer_layout.addStretch()
        h_center = QHBoxLayout()
        h_center.addStretch()
        h_center.addWidget(self.card)
        h_center.addStretch()
        outer_layout.addLayout(h_center)
        outer_layout.addStretch()

    def paintEvent(self, event):
        from PySide6.QtWidgets import QStyle, QStyleOption
        from PySide6.QtGui import QPainter
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)
        super().paintEvent(event)

    def _on_proceed(self):
        self.close()
        if self.on_proceed_callback:
            self.on_proceed_callback()

    def mousePressEvent(self, event):
        focused = QApplication.focusWidget()
        if focused and focused is not self:
            focused.clearFocus()
            
        if hasattr(self, 'card') and self.card:
            if not self.card.geometry().contains(event.pos()):
                self.close()
                return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        super().resizeEvent(event)


class StarRatingWidget(QWidget):
    """
    Universal Vector Star Rating Widget for benchmark and score ratings (No Emojis, pure QPainter vector).
    Supports optional sequential lighting animation.
    
    Component Name: StarRatingWidget
    """
    def __init__(self, rating=5, max_stars=5, star_size=18, animate=True, parent=None):
        super().__init__(parent)
        self.setObjectName("StarRatingWidget")
        self.target_rating = rating
        self.max_stars = max_stars
        self.star_size = star_size
        self.setFixedSize(max_stars * (star_size + 4), star_size)
        
        if animate:
            self.current_rating = 0
            self._timer = QTimer(self)
            self._timer.setInterval(90)
            self._timer.timeout.connect(self._step_star)
        else:
            self.current_rating = rating
            self._timer = None

    def start_animation(self):
        if hasattr(self, '_timer') and self._timer:
            self.current_rating = 0
            self.update()
            self._timer.start()

    def _step_star(self):
        if self.current_rating < self.target_rating:
            self.current_rating += 1
            self.update()
        else:
            self._timer.stop()

    def set_rating(self, rating):
        self.target_rating = rating
        self.current_rating = rating
        self.update()

    def paintEvent(self, event):
        import math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        for i in range(self.max_stars):
            painter.save()
            painter.translate(i * (self.star_size + 4), 0)
            
            # Star path polygon
            path = QPainterPath()
            cx = self.star_size / 2.0
            cy = self.star_size / 2.0
            outer_r = self.star_size / 2.0
            inner_r = outer_r * 0.4
            
            for k in range(10):
                r = outer_r if k % 2 == 0 else inner_r
                angle = (k * 36 - 90) * math.pi / 180.0
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                if k == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()

            if i < self.current_rating:
                painter.setBrush(QBrush(QColor("#FFC107")))
                painter.setPen(Qt.NoPen)
            else:
                painter.setBrush(QBrush(QColor("#35353d")))
                painter.setPen(Qt.NoPen)
                
            painter.drawPath(path)
            painter.restore()


class CpsResultOverlayPanel(QWidget):
    """
    Universal floating modal overlay panel displaying CPS Benchmark results.
    Includes smooth backdrop fade-in, sequential star lighting, and rolling stats count-up.
    
    Component Name: CpsResultOverlayPanel
    """
    def __init__(self, parent_panel, on_retry_callback, cps_score, peak_cps, total_clicks, rank_badge, star_rating, rank_desc, rank_color, avg_cps=0.0):
        super().__init__(parent_panel)
        self.parent_panel = parent_panel
        self.on_retry_callback = on_retry_callback
        self.cps_score = cps_score
        self.peak_cps = peak_cps
        self.avg_cps = avg_cps
        self.total_clicks = total_clicks
        self.rank_badge = rank_badge
        self.star_rating = star_rating
        self.rank_desc = rank_desc
        self.rank_color = rank_color
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("CpsResultOverlayPanel")
        
        self.setGeometry(0, 0, parent_panel.width(), parent_panel.height())
        self._setup_ui()

    def _setup_ui(self):
        # Rule 1: Less use border, more use background-color contrast
        self.setStyleSheet("""
            QWidget#CpsResultOverlayPanel {
                background-color: rgba(0, 0, 0, 0.70);
            }
            QFrame#CpsResultCard {
                background-color: #18181c;
                border: none;
                border-radius: 12px;
            }
            QWidget#CpsResultTitleBar {
                background-color: #22222a;
                border: none;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
        """)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        
        self.card = QFrame()
        self.card.setObjectName("CpsResultCard")
        self.card.setFixedSize(480, 250)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 16)
        card_layout.setSpacing(14)
        
        # 1. Header Title Bar
        title_bar = QWidget()
        title_bar.setObjectName("CpsResultTitleBar")
        title_bar.setFixedHeight(44)
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(18, 0, 18, 0)
        title_layout.setSpacing(10)
        
        title_label = QLabel("BENCHMARK RESULT")
        title_label.setObjectName("CpsResultTitleLabel")
        title_label.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        card_layout.addWidget(title_bar)
        
        # 2. Main Result Content
        body_content = QWidget()
        body_content.setObjectName("CpsResultBody")
        body_content.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body_content)
        body_layout.setContentsMargins(20, 4, 20, 4)
        body_layout.setSpacing(12)
        
        # Rank Row (Rank Tag + Universal Vector Star Rating Widget)
        rank_row = QHBoxLayout()
        rank_row.setSpacing(12)
        
        rank_lbl = QLabel(self.rank_badge)
        rank_lbl.setObjectName("CpsResultRankTag")
        rank_lbl.setFont(QFont("Orbitron", 15, QFont.Bold))
        rank_lbl.setStyleSheet(f"color: {self.rank_color}; font-family: 'Orbitron', sans-serif; background: transparent;")
        rank_row.addWidget(rank_lbl)

        # Universal Vector Star Rating with Sequential Animation
        self.star_widget = StarRatingWidget(rating=self.star_rating, max_stars=5, star_size=16, animate=True)
        self.star_widget.setObjectName("CpsResultStarRating")
        rank_row.addWidget(self.star_widget)

        rank_row.addStretch()
        body_layout.addLayout(rank_row)
        
        # Score Breakdown Stats Grid (Background contrast boxes, no borders)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        
        self.cps_stat = QLabel("CPS <span style='color: #888;'>0.0</span>")
        self.cps_stat.setObjectName("CpsStatBadge")
        self.cps_stat.setStyleSheet("""
            color: #E0E0E0;
            font-family: 'Orbitron', sans-serif;
            font-size: 12px;
            font-weight: bold;
            background-color: #24242c;
            border: none;
            border-radius: 6px;
            padding: 6px 12px;
        """)
        
        self.peak_stat = QLabel("PEAK <span style='color: #888;'>0.0</span>")
        self.peak_stat.setObjectName("PeakStatBadge")
        self.peak_stat.setStyleSheet("""
            color: #E0E0E0;
            font-family: 'Orbitron', sans-serif;
            font-size: 12px;
            font-weight: bold;
            background-color: #24242c;
            border: none;
            border-radius: 6px;
            padding: 6px 12px;
        """)
        
        self.clicks_stat = QLabel("CLICKS <span style='color: #888;'>0</span>")
        self.clicks_stat.setObjectName("ClicksStatBadge")
        self.clicks_stat.setStyleSheet("""
            color: #E0E0E0;
            font-family: 'Orbitron', sans-serif;
            font-size: 12px;
            font-weight: bold;
            background-color: #24242c;
            border: none;
            border-radius: 6px;
            padding: 6px 12px;
        """)
        
        stats_row.addWidget(self.cps_stat)
        stats_row.addWidget(self.peak_stat)
        stats_row.addWidget(self.clicks_stat)
        stats_row.addStretch()
        body_layout.addLayout(stats_row)
        
        # Rank Description Text
        desc_lbl = QLabel(self.rank_desc)
        desc_lbl.setObjectName("CpsResultDescLabel")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #A0A0A0; font-family: 'Orbitron', sans-serif; font-size: 12px; background: transparent;")
        body_layout.addWidget(desc_lbl)
        
        card_layout.addWidget(body_content, 1)
        
        # 3. Footer Action Button (Single Primary "Close" button)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(20, 0, 20, 0)
        btn_layout.setSpacing(0)
        
        close_btn = FadeHoverButton("Close", is_secondary=False, border_radius=8.0, color_mode="default")
        close_btn.setObjectName("CpsResultCloseBtn")
        close_btn.setFixedSize(110, 34)
        close_btn.setFont(QFont("Orbitron", 10, QFont.Bold))
        close_btn.clicked.connect(self._on_close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        card_layout.addLayout(btn_layout)
        
        # Center card in outer layout
        outer_layout.addStretch()
        h_center = QHBoxLayout()
        h_center.addStretch()
        h_center.addWidget(self.card)
        h_center.addStretch()
        outer_layout.addLayout(h_center)
        outer_layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        self._start_animations()

    def _start_animations(self):
        # 1. Smooth Backdrop Fade-in Animation (Opacity 0 -> 1 over 250ms)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

        # 2. Sequential Vector Star Lighting Animation
        if hasattr(self, 'star_widget'):
            self.star_widget.start_animation()

        # 3. Smooth Stats Count-Up Roll Animation (450ms OutCubic)
        self._anim_start_time = time.perf_counter()
        self._count_timer = QTimer(self)
        self._count_timer.setInterval(20)
        self._count_timer.timeout.connect(self._step_countup)
        self._count_timer.start()

    def _step_countup(self):
        elapsed = time.perf_counter() - self._anim_start_time
        duration = 0.45  # 450ms smooth roll-up
        progress = min(1.0, elapsed / duration)
        
        # Smooth OutCubic easing math
        ease = 1.0 - (1.0 - progress) ** 3
        
        cur_cps = self.avg_cps * ease
        cur_peak = self.peak_cps * ease
        cur_clicks = int(round(self.total_clicks * ease))

        self.cps_stat.setText(f"CPS <span style='color:{self.rank_color};'>{cur_cps:.1f}</span>")
        self.peak_stat.setText(f"PEAK <span style='color:#FDA903;'>{cur_peak:.1f}</span>")
        self.clicks_stat.setText(f"CLICKS <span style='color:#00FF66;'>{cur_clicks}</span>")

        if progress >= 1.0:
            self._count_timer.stop()

    def paintEvent(self, event):
        from PySide6.QtWidgets import QStyle, QStyleOption
        from PySide6.QtGui import QPainter
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)
        super().paintEvent(event)

    def _on_close(self):
        if getattr(self, '_is_closing', False):
            return
        self._is_closing = True

        if hasattr(self, '_count_timer') and self._count_timer:
            self._count_timer.stop()

        # Smooth 200ms Backdrop & Modal Fade-out Animation
        if not hasattr(self, '_opacity_effect') or not self._opacity_effect:
            self._opacity_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._opacity_effect)
            
        self._fade_out_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out_anim.setDuration(200)
        self._fade_out_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.InCubic)

        def _finish_and_destroy():
            super(CpsResultOverlayPanel, self).close()
            if self.on_retry_callback:
                self.on_retry_callback()

        self._fade_out_anim.finished.connect(_finish_and_destroy)
        self._fade_out_anim.start()

    def mousePressEvent(self, event):
        focused = QApplication.focusWidget()
        if focused and focused is not self:
            focused.clearFocus()
        event.accept()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        super().resizeEvent(event)


class CpsBenchmarkPanel(QWidget):
    """
    Universal High-precision Click Per Second (CPS) Benchmark Panel.
    Supports human manual clicking, fast jitter clicking, and ultra-high speed (1340+ CPS) autoclickers.
    
    Component Name: CpsBenchmarkPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CpsBenchmarkPanel")

        self._total_clicks = 0
        self._peak_cps = 0.0
        self._current_cps = 0.0  # Live 1s sliding window CPS
        self._avg_cps = 0.0      # Running average CPS (total / elapsed)
        self._is_testing = False
        self._test_duration = 5.0  # Default 5 seconds
        self._time_remaining = 5.0
        self._target_button = "left"  # left, right, middle, any
        self._start_time = 0.0

        # Timer-based CPS sampling & Microsecond Click Timestamps Ring-Buffer
        from collections import deque
        self._samples = deque()
        self._click_timestamps = deque()

        # Background click-counter thread for autoclicker-proof counting.
        # At 1000+ CPS autoclicker SendInput generates WM_LBUTTONDOWN + WM_LBUTTONUP
        # that Qt must dispatch. 2000 Windows messages/s saturates the UI thread → freeze.
        # Fix: daemon thread polls GetAsyncKeyState at ~0.5ms with Multimedia High-Resolution Timer.
        import ctypes, threading
        self._user32 = ctypes.windll.user32
        try:
            self._winmm = ctypes.windll.winmm
        except Exception:
            self._winmm = None
        self._click_counter_stop = threading.Event()
        self._click_counter_thread = None
        self._VK_LBUTTON = 0x01
        self._VK_RBUTTON = 0x02
        self._VK_MBUTTON = 0x04
        self._vk_map = {"left": 0x01, "right": 0x02, "middle": 0x04}

        # High-frequency UI update timer (20ms interval = 50 FPS smooth stats)
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._update_stats)
        
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # ── 1. TOP HEADER & CONTROLS ROW ─────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("CpsHeaderFrame")
        header_frame.setFixedHeight(38)
        header_frame.setStyleSheet("""
            QFrame#CpsHeaderFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        # Vector Back Arrow Button (Integrated directly into header frame)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("CpsBackBtn")
        self.back_btn.setFixedSize(30, 26)
        self.back_btn.setIcon(QIcon(back_icon_path))
        self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Benchmark Lab")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#CpsBackBtn {
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
            QPushButton#CpsBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("CPS BENCHMARK LAB")
        title_lbl.setObjectName("CpsHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        # Target Button Selector
        btn_lbl = QLabel("Button:")
        btn_lbl.setObjectName("CpsBtnLabel")
        btn_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        h_layout.addWidget(btn_lbl)

        self.btn_combo = QComboBox()
        self.btn_combo.setObjectName("CpsBtnCombo")
        self.btn_combo.addItems(["Left Click", "Right Click", "Middle Click", "Any Button"])
        self.btn_combo.setFixedWidth(105)
        self.btn_combo.setFixedHeight(26)
        self.btn_combo.setStyleSheet("""
            QComboBox#CpsBtnCombo {
                background-color: rgba(30, 30, 30, 0.85);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 2px 6px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.btn_combo.currentIndexChanged.connect(self._on_btn_combo_changed)
        h_layout.addWidget(self.btn_combo)

        # Duration Mode Selector
        dur_lbl = QLabel("Duration:")
        dur_lbl.setObjectName("CpsDurLabel")
        dur_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        h_layout.addWidget(dur_lbl)

        self.dur_combo = QComboBox()
        self.dur_combo.setObjectName("CpsDurCombo")
        self.dur_combo.addItems(["5 Seconds", "10 Seconds", "15 Seconds", "30 Seconds", "Uncapped Live"])
        self.dur_combo.setFixedWidth(115)
        self.dur_combo.setFixedHeight(26)
        self.dur_combo.setStyleSheet("""
            QComboBox#CpsDurCombo {
                background-color: rgba(30, 30, 30, 0.85);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 2px 6px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.dur_combo.currentIndexChanged.connect(self._on_dur_combo_changed)
        h_layout.addWidget(self.dur_combo)

        # Reset Button (Universal objectName CpsResetBtn + strict QSS dimensions)
        self.reset_btn = FadeHoverButton("Reset", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("CpsResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#CpsResetBtn, FadeHoverButton#CpsResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self.reset_benchmark)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # ── 2. METRICS DISPLAY CARDS (4 COLUMNS) ───────────────
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(8)

        # Metric 1: Current CPS (1s sliding window)
        self.card_cps_val = self._create_metric_card("CURRENT CPS", "0.0", "#FF5B06")
        metrics_layout.addWidget(self.card_cps_val)

        # Metric 2: Peak CPS
        self.card_peak_val = self._create_metric_card("PEAK CPS", "0.0", "#FDA903")
        metrics_layout.addWidget(self.card_peak_val)

        # Metric 3: Total Clicks
        self.card_clicks_val = self._create_metric_card("TOTAL CLICKS", "0", "#00FF66")
        metrics_layout.addWidget(self.card_clicks_val)

        # Metric 4: Timer Remaining
        self.card_timer_val = self._create_metric_card("TIME LEFT", "5.0s", "#00E5FF")
        metrics_layout.addWidget(self.card_timer_val)

        main_layout.addLayout(metrics_layout)

        # ── 3. MAIN INTERACTIVE CLICK ZONE ────────────────────
        self.click_target_zone = QFrame()
        self.click_target_zone.setObjectName("CpsClickTargetZone")
        self.click_target_zone.setFixedHeight(110)
        self.click_target_zone.setCursor(Qt.PointingHandCursor)
        self.click_target_zone.setStyleSheet("""
            QFrame#CpsClickTargetZone {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 91, 6, 0.08), stop:1 rgba(20, 22, 28, 0.95));
                border: 2px dashed rgba(255, 91, 6, 0.4);
                border-radius: 10px;
            }
            QFrame#CpsClickTargetZone:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 91, 6, 0.15), stop:1 rgba(30, 32, 40, 0.95));
                border: 2px solid #FF5B06;
            }
        """)

        target_layout = QVBoxLayout(self.click_target_zone)
        target_layout.setAlignment(Qt.AlignCenter)
        target_layout.setSpacing(4)

        self.target_status_lbl = QLabel("CLICK HERE TO START BENCHMARK")
        self.target_status_lbl.setFont(QFont("Orbitron", 15, QFont.Bold))
        self.target_status_lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.target_status_lbl.setAlignment(Qt.AlignCenter)
        target_layout.addWidget(self.target_status_lbl)

        self.target_hint_lbl = QLabel("Click manually or toggle your autoclicker inside this box to test CPS")
        self.target_hint_lbl.setFont(QFont("Orbitron", 10))
        self.target_hint_lbl.setStyleSheet("color: #888888; background: transparent;")
        self.target_hint_lbl.setAlignment(Qt.AlignCenter)
        target_layout.addWidget(self.target_hint_lbl)

        # Hook mouse press on target zone (only for first click auto-start)
        self.click_target_zone.mousePressEvent = self._on_zone_mouse_press

        # Install event filter to eat mouse events during benchmark.
        # Without this, Qt dispatches every WM_LBUTTONDOWN/UP through its full
        # event pipeline (hit-test → focus → widget routing) even if the handler
        # is a no-op. At 1000+ CPS that's 2000 events/s freezing the UI thread.
        self.click_target_zone.installEventFilter(self)

        main_layout.addWidget(self.click_target_zone)

        # ── 4. RECENT BENCHMARK HISTORY SECTION ────────────────
        history_frame = QFrame()
        history_frame.setObjectName("CpsHistoryFrame")
        history_frame.setStyleSheet("""
            QFrame#CpsHistoryFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        hist_main_layout = QVBoxLayout(history_frame)
        hist_main_layout.setContentsMargins(10, 8, 10, 8)
        hist_main_layout.setSpacing(8)

        # Header Row
        hist_header_layout = QHBoxLayout()
        hist_header_layout.setContentsMargins(2, 0, 2, 0)

        hist_title = QLabel("RECENT BENCHMARK HISTORY")
        hist_title.setObjectName("CpsHistoryTitle")
        hist_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: bold; background: transparent;")
        hist_header_layout.addWidget(hist_title)

        hist_header_layout.addStretch()

        self.clear_hist_btn = FadeHoverButton("Clear History", is_secondary=True, border_radius=6.0)
        self.clear_hist_btn.setObjectName("CpsHistoryClearBtn")
        self.clear_hist_btn.setFixedSize(95, 24)
        self.clear_hist_btn.setStyleSheet("""
            QPushButton#CpsHistoryClearBtn, FadeHoverButton#CpsHistoryClearBtn {
                min-width: 95px;
                max-width: 95px;
                min-height: 24px;
                max-height: 24px;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.clear_hist_btn.clicked.connect(self._clear_history)
        hist_header_layout.addWidget(self.clear_hist_btn)

        hist_main_layout.addLayout(hist_header_layout)

        # Container QListWidget (Macro List Style)
        self.history_list_widget = QListWidget()
        self.history_list_widget.setObjectName("CpsHistoryListWidget")
        self.history_list_widget.setStyleSheet("""
            QListWidget#CpsHistoryListWidget {
                background-color: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget#CpsHistoryListWidget::item {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                padding: 2px;
                margin-bottom: 4px;
            }
            QListWidget#CpsHistoryListWidget::item:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.4);
            }
            QListWidget#CpsHistoryListWidget::item:selected {
                background-color: rgba(255, 91, 6, 0.15);
                border-color: #FF5B06;
            }
        """)
        self.history_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.history_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history_list_widget.setSelectionMode(QAbstractItemView.NoSelection)

        hist_main_layout.addWidget(self.history_list_widget, 1)

        main_layout.addWidget(history_frame, 1)

        # Initialize history disk persistence
        appdata_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'HELXAID')
        self._history_file_path = os.path.join(appdata_dir, 'cps_history.json')
        self._history_records = self._load_history_from_disk()
        self._update_history_ui()

    def _load_history_from_disk(self):
        try:
            if os.path.exists(self._history_file_path):
                with open(self._history_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as e:
            print(f"[CPS History] Error loading from disk: {e}")
        return []

    def _save_history_to_disk(self):
        try:
            os.makedirs(os.path.dirname(self._history_file_path), exist_ok=True)
            with open(self._history_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._history_records, f, indent=2)
        except Exception as e:
            print(f"[CPS History] Error saving to disk: {e}")

    def _add_history_record(self, cps, peak_cps, total_clicks, badge, star_rating, color):
        import time as pytime
        now_time_str = pytime.strftime("%H:%M:%S")
        now_date_str = pytime.strftime("%d/%m/%y")
        btn_name = self.btn_combo.currentText()
        dur_name = self.dur_combo.currentText()
        dur_short = dur_name.replace(" Seconds", "s").replace("Uncapped Live", "Live")
        
        record = {
            "time": now_time_str,
            "date": now_date_str,
            "btn": btn_name,
            "dur": dur_short,
            "cps": cps,
            "peak": peak_cps,
            "clicks": total_clicks,
            "badge": badge,
            "stars": star_rating,
            "color": color
        }
        self._history_records.insert(0, record)
        if len(self._history_records) > 10:
            self._history_records.pop()
        self._save_history_to_disk()
        self._update_history_ui()

    def _clear_history(self):
        self._history_records.clear()
        self._save_history_to_disk()
        self._update_history_ui()

    def _update_history_ui(self):
        self.history_list_widget.clear()
        
        if not self._history_records:
            empty_item = QListWidgetItem(self.history_list_widget)
            empty_item.setSizeHint(QSize(0, 44))

            empty_lbl = QLabel("No benchmark history recorded yet. Complete a test above to record your score!")
            empty_lbl.setObjectName("CpsHistoryEmptyLabel")
            empty_lbl.setFont(QFont("Orbitron", 10))
            empty_lbl.setStyleSheet("color: #666666; font-family: 'Orbitron', sans-serif; background: transparent;")
            empty_lbl.setAlignment(Qt.AlignCenter)
            
            self.history_list_widget.setItemWidget(empty_item, empty_lbl)
            return

        for item in self._history_records:
            list_item = QListWidgetItem(self.history_list_widget)
            list_item.setSizeHint(QSize(0, 36))

            item_widget = QWidget()
            item_widget.setObjectName("CpsHistoryItemWidget")
            item_widget.setStyleSheet("background: transparent;")
            
            card_layout = QHBoxLayout(item_widget)
            card_layout.setContentsMargins(8, 2, 8, 2)
            card_layout.setSpacing(10)

            # Left Rank Tag & Vector Star Rating
            badge_lbl = QLabel(item['badge'])
            badge_lbl.setObjectName("CpsHistoryBadge")
            badge_lbl.setFont(QFont("Orbitron", 10, QFont.Bold))
            badge_lbl.setStyleSheet(f"color: {item['color']}; font-family: 'Orbitron', sans-serif; background: transparent;")
            card_layout.addWidget(badge_lbl)

            stars = StarRatingWidget(rating=item['stars'], max_stars=5, star_size=11, animate=False)
            stars.setObjectName("CpsHistoryStars")
            card_layout.addWidget(stars)

            card_layout.addStretch()

            # Center Stats summary
            stats_lbl = QLabel(f"CPS <span style='color:{item['color']}; font-weight:bold;'>{item['cps']:.1f}</span>  |  PEAK <span style='color:#FDA903;'>{item['peak']:.1f}</span>  |  CLICKS <span style='color:#00FF66;'>{item['clicks']}</span>")
            stats_lbl.setObjectName("CpsHistoryStats")
            stats_lbl.setFont(QFont("Orbitron", 9.5))
            stats_lbl.setStyleSheet("color: #CCCCCC; font-family: 'Orbitron', sans-serif; background: transparent;")
            card_layout.addWidget(stats_lbl)

            card_layout.addStretch()

            # Right Meta Info: Left Click (5s) • HH:MM:SS DD/MM/YY
            meta_lbl = QLabel(f"{item['btn']} ({item['dur']})  •  {item['time']} {item['date']}")
            meta_lbl.setObjectName("CpsHistoryMeta")
            meta_lbl.setFont(QFont("Orbitron", 8.5))
            meta_lbl.setStyleSheet("color: #777777; font-family: 'Orbitron', sans-serif; background: transparent;")
            card_layout.addWidget(meta_lbl)

            self.history_list_widget.setItemWidget(list_item, item_widget)

    def _create_metric_card(self, title, default_val, color_hex):
        card = QFrame()
        card.setObjectName("CpsMetricCard")
        card.setFixedHeight(48)
        card.setStyleSheet(f"""
            QFrame#CpsMetricCard {{
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)

        val_lbl = QLabel(default_val)
        val_lbl.setFont(QFont("Orbitron", 16, QFont.Bold))
        val_lbl.setStyleSheet(f"color: {color_hex}; background: transparent;")
        val_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(val_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Orbitron", 8))
        title_lbl.setStyleSheet("color: #777777; background: transparent;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        card.val_label = val_lbl
        return card

    def _click_counter_loop(self):
        """Background thread: poll GetAsyncKeyState at high precision to count click transitions.
        Runs as daemon — dies with main thread. Pushes microsecond timestamps into _click_timestamps
        for exact CPS & Peak CPS calculations without GUI timer quantization noise."""
        import time as _time
        get_key = self._user32.GetAsyncKeyState
        stop_ev = self._click_counter_stop

        # Enable Windows Multimedia high-resolution timer (1ms period)
        if hasattr(self, '_winmm') and self._winmm:
            try:
                self._winmm.timeBeginPeriod(1)
            except Exception:
                pass

        try:
            # Build list of VK codes to watch
            if self._target_button == "any":
                vk_list = [0x01, 0x02, 0x04]
            else:
                vk_list = [self._vk_map.get(self._target_button, 0x01)]

            prev_states = {vk: False for vk in vk_list}

            while not stop_ev.is_set():
                now_ts = _time.perf_counter()
                for vk in vk_list:
                    state = get_key(vk)
                    pressed = bool(state & 0x8000)  # bit 15 = currently pressed
                    if pressed and not prev_states[vk]:
                        # Transition: released → pressed = one click
                        self._total_clicks += 1
                        self._click_timestamps.append(now_ts)
                    prev_states[vk] = pressed
                _time.sleep(0.0005)
        finally:
            if hasattr(self, '_winmm') and self._winmm:
                try:
                    self._winmm.timeEndPeriod(1)
                except Exception:
                    pass

    def register_click(self, btn_name="left"):
        """Handle first click to auto-start benchmark. Once running, the background
        thread counts clicks — this method is effectively a no-op during testing."""
        if self._is_testing:
            # Background thread handles counting — ignore Qt events to avoid flood
            return

        # Check if button matches target filter
        if self._target_button != "any":
            if self._target_button == "left" and btn_name != "left":
                return
            elif self._target_button == "right" and btn_name != "right":
                return
            elif self._target_button == "middle" and btn_name != "middle":
                return

        # First click starts benchmark (background thread takes over counting)
        self.start_benchmark()

    def _on_zone_mouse_press(self, event):
        if self._is_testing:
            event.accept()
            return
        btn_map = {Qt.LeftButton: "left", Qt.RightButton: "right", Qt.MiddleButton: "middle"}
        btn_name = btn_map.get(event.button(), "left")
        self.register_click(btn_name)
        event.accept()

    def eventFilter(self, obj, event):
        """Eat mouse press/release events on click zone during benchmark.
        This blocks Qt's full event dispatch pipeline (hit-test, focus, routing)
        which is what actually freezes the UI at high CPS, not our handler code."""
        if self._is_testing and obj is self.click_target_zone:
            etype = event.type()
            if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                         QEvent.MouseButtonDblClick):
                return True  # Consumed — Qt skips all further dispatch
        return super().eventFilter(obj, event)

    def _stop_click_counter(self):
        """Stop background click counter thread if running."""
        if hasattr(self, '_click_counter_stop') and self._click_counter_stop:
            self._click_counter_stop.set()
        if hasattr(self, '_click_counter_thread') and self._click_counter_thread and self._click_counter_thread.is_alive():
            self._click_counter_thread.join(timeout=0.1)
        self._click_counter_thread = None

    def start_benchmark(self):
        """Start or restart the benchmark run."""
        # Stop any previous counter thread
        self._stop_click_counter()

        self._is_testing = True
        self._start_time = time.perf_counter()
        self._samples.clear()
        self._click_timestamps.clear()
        self._click_timestamps.append(self._start_time)
        self._total_clicks = 1  # Count the click that triggered start
        self._peak_cps = 0.0
        self._current_cps = 0.0
        self._avg_cps = 0.0

        # Launch background click counter thread
        import threading
        self._click_counter_stop = threading.Event()
        self._click_counter_thread = threading.Thread(
            target=self._click_counter_loop, daemon=True,
            name="CPS-ClickCounter"
        )
        self._click_counter_thread.start()

        # Make click zone transparent to mouse events so Qt's message pump
        # skips hit-testing and routing for this widget entirely.
        # Without this, 2000 WM_LBUTTONDOWN/UP per second from SendInput
        # saturates Qt's internal event dispatch even if our handler is a no-op.
        self.click_target_zone.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Also make child labels transparent so they don't catch events either
        self.target_status_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.target_hint_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        self.target_status_lbl.setText("CLICK AS FAST AS YOU CAN!")
        self.target_status_lbl.setStyleSheet("color: #FF5B06; background: transparent;")
        self.click_target_zone.setStyleSheet("""
            QFrame#CpsClickTargetZone {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 91, 6, 0.2), stop:1 rgba(30, 32, 40, 0.95));
                border: 2px solid #FF5B06;
                border-radius: 12px;
            }
        """)
        self._timer.start()

    def finish_benchmark(self):
        """Complete the benchmark and show full floating modal result panel over the software window."""
        self._is_testing = False
        self._timer.stop()
        self._stop_click_counter()
        # Restore mouse event handling on click zone
        self.click_target_zone.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.target_status_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.target_hint_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
        # Peak CPS already tracked incrementally — just update label
        self.card_peak_val.val_label.setText(f"{self._peak_cps:.1f}")

        # Final avg CPS = Total Clicks / Duration
        if self._test_duration > 0:
            self._avg_cps = self._total_clicks / self._test_duration

        # Final current CPS = last 1s window (already computed by _update_stats)
        self.card_cps_val.val_label.setText(f"{self._current_cps:.1f}")

        self.target_status_lbl.setText("BENCHMARK COMPLETE!")
        self.target_status_lbl.setStyleSheet("color: #00FF66; background: transparent;")
        self.click_target_zone.setStyleSheet("""
            QFrame#CpsClickTargetZone {
                background: rgba(255, 255, 255, 0.03);
                border: 2px solid rgba(0, 255, 102, 0.5);
                border-radius: 12px;
            }
        """)

        # Compute rank based on Peak / Current CPS achieved (No Emojis per UI Rules)
        cps = max(self._current_cps, self._peak_cps)
        if cps >= 100:
            badge = "GODLIKE MONSTER"
            star_rating = 5
            desc = f"UNBELIEVABLE! {cps:.1f} CPS Auto-Clicker Beast Speed!"
            color = "#FF0055"
        elif cps >= 20:
            badge = "CYBER SONIC"
            star_rating = 5
            desc = f"Superhuman speed! {cps:.1f} CPS Jitter/Butterfly God!"
            color = "#00E5FF"
        elif cps >= 10:
            badge = "CHEETAH"
            star_rating = 4
            desc = f"Blistering speed! {cps:.1f} CPS Pro Gamer Reflexes!"
            color = "#FF5B06"
        elif cps >= 5:
            badge = "RABBIT"
            star_rating = 3
            desc = f"Solid speed! {cps:.1f} CPS Casual Gamer Pace."
            color = "#FDA903"
        else:
            badge = "TURTLE"
            star_rating = 2
            desc = f"Taking it slow! {cps:.1f} CPS Steady Pace."
            color = "#888888"

        # Add entry to Recent Benchmark History list
        self._add_history_record(cps, self._peak_cps, self._total_clicks, badge, star_rating, color)

        # Launch full window floating modal overlay (centered on application window)
        parent_panel = self.window()
        overlay = CpsResultOverlayPanel(
            parent_panel=parent_panel,
            on_retry_callback=self.reset_benchmark,
            cps_score=cps,
            peak_cps=self._peak_cps,
            total_clicks=self._total_clicks,
            rank_badge=badge,
            star_rating=star_rating,
            rank_desc=desc,
            rank_color=color,
            avg_cps=self._avg_cps
        )
        overlay.show()

    def reset_benchmark(self):
        """Reset benchmark state back to initial."""
        self._is_testing = False
        self._timer.stop()
        self._stop_click_counter()
        # Restore mouse event handling
        self.click_target_zone.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.target_status_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.target_hint_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._samples.clear()
        self._click_timestamps.clear()
        self._total_clicks = 0
        self._peak_cps = 0.0
        self._current_cps = 0.0
        self._avg_cps = 0.0
        self._time_remaining = self._test_duration

        self.card_cps_val.val_label.setText("0.0")
        self.card_peak_val.val_label.setText("0.0")
        self.card_clicks_val.val_label.setText("0")
        
        if self._test_duration <= 0:
            self.card_timer_val.val_label.setText("∞ Live")
        else:
            self.card_timer_val.val_label.setText(f"{self._test_duration:.1f}s")
            
        self.target_status_lbl.setText("CLICK HERE TO START BENCHMARK")
        self.target_status_lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.click_target_zone.setStyleSheet("""
            QFrame#CpsClickTargetZone {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 91, 6, 0.08), stop:1 rgba(20, 22, 28, 0.95));
                border: 2px dashed rgba(255, 91, 6, 0.4);
                border-radius: 12px;
            }
            QFrame#CpsClickTargetZone:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 91, 6, 0.15), stop:1 rgba(30, 32, 40, 0.95));
                border: 2px solid #FF5B06;
            }
        """)

    def _update_stats(self):
        """Update CPS metrics from background thread's click counter (runs every 20ms).
        Uses high-precision per-click microsecond timestamp deque to calculate:
        - Current CPS: Sustained 1.0s sliding window CPS
        - Burst CPS: 0.5s sliding window CPS
        - Peak CPS: Highest legitimate sustained/burst CPS after warmup grace period (>= 0.3s)
        """
        now = time.perf_counter()

        if self._is_testing:
            elapsed = max(0.001, now - self._start_time)

            # Evict click timestamps older than 2.0 seconds
            cutoff_2s = now - 2.0
            while self._click_timestamps and self._click_timestamps[0] < cutoff_2s:
                self._click_timestamps.popleft()

            # 1. Calculate Current CPS (1.0s sliding window)
            cutoff_1s = now - 1.0
            clicks_in_1s = sum(1 for t in self._click_timestamps if t >= cutoff_1s)
            if elapsed < 1.0:
                self._current_cps = clicks_in_1s / elapsed
            else:
                self._current_cps = float(clicks_in_1s)

            # 2. Calculate Burst CPS (0.5s sliding window)
            cutoff_05s = now - 0.5
            clicks_in_05s = sum(1 for t in self._click_timestamps if t >= cutoff_05s)
            burst_cps = clicks_in_05s / 0.5

            # 3. Calculate Avg CPS
            self._avg_cps = self._total_clicks / elapsed

            # 4. Calculate Peak CPS (Warmup Grace Period of 0.3s & >= 3 clicks to prevent initial startup spikes)
            if elapsed >= 0.3 and self._total_clicks >= 3:
                achieved_max = max(self._current_cps, burst_cps)
                if achieved_max > self._peak_cps:
                    self._peak_cps = achieved_max

            # Handle countdown
            if self._test_duration > 0:
                self._time_remaining = max(0.0, self._test_duration - elapsed)
                self.card_timer_val.val_label.setText(f"{self._time_remaining:.1f}s")

                if self._time_remaining <= 0:
                    self.finish_benchmark()

        self.card_cps_val.val_label.setText(f"{self._current_cps:.1f}")
        self.card_peak_val.val_label.setText(f"{self._peak_cps:.1f}")
        self.card_clicks_val.val_label.setText(str(self._total_clicks))

    def hideEvent(self, event):
        """Cleanup background thread and timers when widget is hidden or tab changed."""
        self._stop_click_counter()
        if hasattr(self, '_timer') and self._timer.isActive():
            self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        """Cleanup background thread and timers when widget is destroyed."""
        self._stop_click_counter()
        if hasattr(self, '_timer') and self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)

    def _on_btn_combo_changed(self, idx):
        maps = ["left", "right", "middle", "any"]
        self._target_button = maps[idx] if idx < len(maps) else "left"

    def _on_dur_combo_changed(self, idx):
        durations = [5.0, 10.0, 15.0, 30.0, -1.0]
        val = durations[idx] if idx < len(durations) else 5.0
        self._test_duration = val
        self.reset_benchmark()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_result_banner()

    def _reposition_result_banner(self):
        if hasattr(self, 'result_banner') and hasattr(self, 'click_target_zone') and self.result_banner.isVisible():
            w = min(self.click_target_zone.width() - 30, 720)
            h = 44
            x = max(0, (self.click_target_zone.width() - w) // 2)



class HelxairoPulseGraphWidget(QWidget):
    """
    Real-time Digital Oscilloscope Waveform Plotter for Click Pulse Signals.
    Component Name: HelxairoPulseGraphWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelxairoPulseGraphWidget")
        from collections import deque
        self._samples = deque(maxlen=80)
        self.setMinimumHeight(120)
        self.setMaximumHeight(160)

    def add_sample(self, state: bool, dt_ms: float, is_chatter: bool):
        self._samples.append({
            'state': state,
            'dt_ms': dt_ms,
            'is_chatter': is_chatter,
            'time': time.perf_counter_ns()
        })
        self.update()

    def clear_graph(self):
        self._samples.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        # Background container
        painter.fillRect(rect, QColor(14, 16, 20, 220))

        # Grid lines
        grid_pen = QPen(QColor(255, 255, 255, 12), 1, Qt.DashLine)
        painter.setPen(grid_pen)
        
        y_high = int(h * 0.3)
        y_low = int(h * 0.75)
        painter.drawLine(0, y_high, w, y_high)
        painter.drawLine(0, y_low, w, y_low)

        lbl_font = QFont("Orbitron", 8, QFont.Bold)
        painter.setFont(lbl_font)
        painter.setPen(QColor(0, 230, 118, 180))
        painter.drawText(10, y_high - 6, "HIGH (PRESS)")
        painter.setPen(QColor(160, 160, 160, 140))
        painter.drawText(10, y_low + 16, "LOW (RELEASE)")

        if not self._samples:
            painter.setPen(QColor(120, 120, 120, 120))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "CLICK IN TEST CANVA TO RECORD SIGNAL WAVEFORM")
            return

        n = len(self._samples)
        step_x = max(10.0, (w - 60) / max(1, n - 1))
        
        path = QPainterPath()
        last_x = 50.0
        last_y = y_low if not self._samples[0]['state'] else y_high
        path.moveTo(last_x, last_y)

        for i, sample in enumerate(self._samples):
            curr_x = 50.0 + i * step_x
            curr_y = y_high if sample['state'] else y_low

            path.lineTo(curr_x, last_y)
            path.lineTo(curr_x, curr_y)

            last_x = curr_x
            last_y = curr_y

        pulse_pen = QPen(QColor(255, 91, 6), 2)
        painter.setPen(pulse_pen)
        painter.drawPath(path)

        for i, sample in enumerate(self._samples):
            curr_x = 50.0 + i * step_x
            curr_y = y_high if sample['state'] else y_low

            if sample['is_chatter']:
                painter.setBrush(QBrush(QColor(255, 51, 51, 200)))
                painter.setPen(QPen(QColor(255, 51, 51), 2))
                painter.drawEllipse(QPoint(int(curr_x), int(curr_y)), 6, 6)
                
                painter.setFont(QFont("Orbitron", 7, QFont.Bold))
                painter.drawText(int(curr_x) - 15, int(curr_y) - 10, f"{sample['dt_ms']:.1f}ms !")
            else:
                painter.setBrush(QBrush(QColor(0, 230, 118, 220)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(int(curr_x), int(curr_y)), 3, 3)


class HelxairoMouseGraphicWidget(QWidget):
    """
    Vector Mouse Silhouette Graphic with Interactive Button State Feedback.
    Component Name: HelxairoMouseGraphicWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelxairoMouseGraphicWidget")
        self.setFixedSize(140, 210)
        self._button_states = {
            'left': 'normal',
            'right': 'normal',
            'middle': 'normal',
            'x1': 'normal',
            'x2': 'normal',
        }

    def set_button_state(self, button: str, state: str):
        if button in self._button_states:
            self._button_states[button] = state
            self.update()

    def reset_all_buttons(self):
        for k in self._button_states:
            self._button_states[k] = 'normal'
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw Side Buttons First
        mb5_rect = QRect(23, 75, 6, 18)
        mb4_rect = QRect(23, 96, 6, 18)
        
        def _color_for_side_btn(state_val):
            if state_val == 'pressed':
                return QColor(0, 230, 118, 200)
            elif state_val == 'chatter':
                return QColor(255, 51, 51, 220)
            elif state_val == 'fast_dc':
                return QColor(255, 183, 77, 200)
            return QColor(50, 50, 50, 255)

        x2_color = _color_for_side_btn(self._button_states['x2'])
        x1_color = _color_for_side_btn(self._button_states['x1'])
        
        painter.setPen(QPen(QColor("#474747"), 1))
        painter.setBrush(QBrush(x2_color))
        painter.drawRoundedRect(mb5_rect, 2, 2)
        
        painter.setBrush(QBrush(x1_color))
        painter.drawRoundedRect(mb4_rect, 2, 2)

        # Draw Body
        body_path = QPainterPath()
        body_path.moveTo(70, 10)
        body_path.cubicTo(98, 10, 112, 16, 112, 40)
        body_path.cubicTo(112, 80, 108, 110, 114, 145)
        body_path.cubicTo(119, 180, 98, 200, 70, 200)
        body_path.cubicTo(42, 200, 21, 180, 26, 145)
        body_path.cubicTo(32, 110, 28, 80, 28, 40)
        body_path.cubicTo(28, 16, 42, 10, 70, 10)

        painter.setPen(QPen(QColor("#474747"), 2))
        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.drawPath(body_path)

        # Left Button Zone
        lmb_path = QPainterPath()
        lmb_path.moveTo(69, 12)
        lmb_path.cubicTo(42, 12, 30, 18, 30, 40)
        lmb_path.cubicTo(30, 50, 32, 60, 33, 70)
        lmb_path.cubicTo(42, 75, 55, 75, 69, 70)
        lmb_path.lineTo(69, 56)
        lmb_path.cubicTo(69, 56, 64, 56, 64, 50)
        lmb_path.lineTo(64, 32)
        lmb_path.cubicTo(64, 26, 69, 26, 69, 26)
        lmb_path.lineTo(69, 12)

        lmb_color = QColor(50, 50, 50, 255)
        if self._button_states['left'] == 'pressed':
            lmb_color = QColor(0, 230, 118, 140)
        elif self._button_states['left'] == 'chatter':
            lmb_color = QColor(255, 51, 51, 180)
        elif self._button_states['left'] == 'fast_dc':
            lmb_color = QColor(255, 183, 77, 160)

        painter.setPen(QPen(QColor("#ff5500"), 1))
        painter.setBrush(QBrush(lmb_color))
        painter.drawPath(lmb_path)

        # Right Button Zone
        rmb_path = QPainterPath()
        rmb_path.moveTo(71, 12)
        rmb_path.cubicTo(98, 12, 110, 18, 110, 40)
        rmb_path.cubicTo(110, 50, 108, 60, 107, 70)
        rmb_path.cubicTo(98, 75, 85, 75, 71, 70)
        rmb_path.lineTo(71, 56)
        rmb_path.cubicTo(71, 56, 76, 56, 76, 50)
        rmb_path.lineTo(76, 32)
        rmb_path.cubicTo(76, 26, 71, 26, 71, 26)
        rmb_path.lineTo(71, 12)

        rmb_color = QColor(50, 50, 50, 255)
        if self._button_states['right'] == 'pressed':
            rmb_color = QColor(0, 230, 118, 140)
        elif self._button_states['right'] == 'chatter':
            rmb_color = QColor(255, 51, 51, 180)
        elif self._button_states['right'] == 'fast_dc':
            rmb_color = QColor(255, 183, 77, 160)

        painter.setPen(QPen(QColor("#ff5500"), 1))
        painter.setBrush(QBrush(rmb_color))
        painter.drawPath(rmb_path)

        # Scroll Wheel & MMB
        mmb_rect = QRect(66, 28, 8, 26)
        mmb_color = QColor("#141414")
        if self._button_states['middle'] == 'pressed':
            mmb_color = QColor(0, 230, 118, 220)
        elif self._button_states['middle'] == 'chatter':
            mmb_color = QColor(255, 51, 51, 240)
        elif self._button_states['middle'] == 'fast_dc':
            mmb_color = QColor(255, 183, 77, 220)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(mmb_color))
        painter.drawRoundedRect(mmb_rect, 4, 4)

        # Text Labels
        painter.setFont(QFont("Orbitron", 7, QFont.Bold))
        painter.setPen(QColor(220, 220, 220, 180))
        painter.drawText(45, 55, "L")
        painter.drawText(87, 55, "R")


class HelxairoChatterLogTableWidget(QTableWidget):
    """
    High-Performance Event Log Table for Double-Click and Microswitch Chatter Events.
    Component Name: HelxairoChatterLogTableWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelxairoChatterLogTableWidget")
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["ID", "Button", "Hold (ms)", "Interval (ms)", "Status Badge"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setStyleSheet("""
            QTableWidget#HelxairoChatterLogTableWidget {
                background-color: rgba(0, 0, 0, 0.25);
                border: none;
                border-radius: 8px;
                gridline-color: rgba(255, 255, 255, 0.05);
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
            }
            QTableWidget#HelxairoChatterLogTableWidget QHeaderView::section {
                background-color: rgba(255, 255, 255, 0.05);
                color: #FF5B06;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                border: none;
                padding: 6px;
            }
            QTableWidget#HelxairoChatterLogTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QTableWidget#HelxairoChatterLogTableWidget::item:selected {
                background-color: rgba(255, 91, 6, 0.15);
            }
        """)

    def add_log_entry(self, event_id: int, button_name: str, hold_ms: float, interval_ms: float, classification: str):
        row = self.rowCount()
        self.insertRow(row)

        item_id = QTableWidgetItem(f"#{event_id:03d}")
        item_btn = QTableWidgetItem(button_name.upper())
        item_hold = QTableWidgetItem(f"{hold_ms:.1f} ms" if hold_ms > 0 else "--")
        item_int = QTableWidgetItem(f"{interval_ms:.1f} ms" if interval_ms > 0 else "--")
        item_status = QTableWidgetItem(classification)

        item_id.setTextAlignment(Qt.AlignCenter)
        item_btn.setTextAlignment(Qt.AlignCenter)
        item_hold.setTextAlignment(Qt.AlignCenter)
        item_int.setTextAlignment(Qt.AlignCenter)
        item_status.setTextAlignment(Qt.AlignCenter)

        if classification == "CHATTER FAULT!":
            item_status.setForeground(QColor(255, 51, 51))
            item_status.setFont(QFont("Orbitron", 9, QFont.Bold))
        elif classification == "FAST DOUBLE":
            item_status.setForeground(QColor(255, 183, 77))
        else:
            item_status.setForeground(QColor(0, 230, 118))

        self.setItem(row, 0, item_id)
        self.setItem(row, 1, item_btn)
        self.setItem(row, 2, item_hold)
        self.setItem(row, 3, item_int)
        self.setItem(row, 4, item_status)

        self.scrollToBottom()

    def clear_logs(self):
        self.setRowCount(0)


import ctypes
from ctypes import wintypes
from PySide6.QtCore import QThread, Signal

# Win32 Constants
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WHEEL_DELTA = 120

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

class LowLevelMouseHook(QThread):
    mouse_event_signal = Signal(str, str, int)

    def __init__(self):
        super().__init__()
        self._hook_id = None
        self._user32 = ctypes.windll.user32
        self._pointer = CMPFUNC(self._hook_callback)
        self._thread_id = None
        self.is_running = True

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0:
            msg = wParam
            struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            
            btn_name = None
            action = None
            
            if msg == WM_LBUTTONDOWN: btn_name, action = 'left', 'press'
            elif msg == WM_LBUTTONUP: btn_name, action = 'left', 'release'
            elif msg == WM_RBUTTONDOWN: btn_name, action = 'right', 'press'
            elif msg == WM_RBUTTONUP: btn_name, action = 'right', 'release'
            elif msg == WM_MBUTTONDOWN: btn_name, action = 'middle', 'press'
            elif msg == WM_MBUTTONUP: btn_name, action = 'middle', 'release'
            elif msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                high_word = (struct.mouseData >> 16) & 0xFFFF
                btn_name = 'x1' if high_word == 1 else 'x2'
                action = 'press' if msg == WM_XBUTTONDOWN else 'release'
            elif msg == WM_MOUSEWHEEL:
                high_word = (struct.mouseData >> 16) & 0xFFFF
                delta = ctypes.c_short(high_word).value
                btn_name = 'wheel'
                action = str(delta)

            if btn_name and action:
                self.mouse_event_signal.emit(btn_name, action, struct.time)

        return self._user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def run(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._hook_id = self._user32.SetWindowsHookExW(WH_MOUSE_LL, self._pointer, None, 0)
        if not self._hook_id:
            return

        msg = wintypes.MSG()
        while self.is_running:
            bRet = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if bRet <= 0:
                break
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_id:
            self._user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    def stop(self):
        self.is_running = False
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)


class DoubleClickTestPanel(QWidget):
    """
    Universal Mouse Button & Microswitch Chatter Test Suite Panel.
    Component Name: DoubleClickTestPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DoubleClickTestPanel")

        self._chatter_threshold_ms = 50.0
        self._event_counter = 0
        self._total_clicks = 0
        self._chatter_fault_count = 0
        self._fast_double_count = 0
        self._reset_timers = {}
        self._mouse_hook = None
        
        self._button_stats = {
            'left': {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0},
            'right': {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0},
            'middle': {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0},
            'x1': {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0},
            'x2': {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0},
        }

        self._setup_ui()

    def showEvent(self, event):
        if not self._mouse_hook or not self._mouse_hook.is_running:
            self._mouse_hook = LowLevelMouseHook()
            self._mouse_hook.mouse_event_signal.connect(self._on_global_mouse_event)
            self._mouse_hook.start()
        super().showEvent(event)

    def hideEvent(self, event):
        if self._mouse_hook and self._mouse_hook.is_running:
            self._mouse_hook.stop()
            self._mouse_hook.wait()
            self._mouse_hook = None
        super().hideEvent(event)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # ── 1. HEADER ROW ─────────────────────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("DoubleClickHeaderFrame")
        header_frame.setFixedHeight(38)
        header_frame.setStyleSheet("""
            QFrame#DoubleClickHeaderFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        # Back Button
        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("DoubleClickBackBtn")
        self.back_btn.setFixedSize(30, 26)
        self.back_btn.setIcon(QIcon(back_icon_path))
        self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Benchmark Lab")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#DoubleClickBackBtn {
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
            QPushButton#DoubleClickBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("DOUBLE CLICK & MICROSWITCH CHATTER LAB")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        thresh_lbl = QLabel("Chatter Threshold:")
        thresh_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        h_layout.addWidget(thresh_lbl)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(10, 120)
        self.threshold_slider.setValue(50)
        self.threshold_slider.setFixedWidth(100)
        self.threshold_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FF5B06;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        h_layout.addWidget(self.threshold_slider)

        self.thresh_val_lbl = QLabel("50 ms")
        self.thresh_val_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        h_layout.addWidget(self.thresh_val_lbl)

        self.reset_btn = FadeHoverButton("Reset", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("DoubleClickResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#DoubleClickResetBtn, FadeHoverButton#DoubleClickResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self.reset_test)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # ── 2. DASHBOARD STATS CARDS ─────────────────────────
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: transparent;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(10)

        self.card_total = self._create_stat_card("TOTAL CLICKS", "0", "#ffffff")
        self.total_val_lbl = self.card_total.findChild(QLabel, "StatValLbl")
        stats_layout.addWidget(self.card_total)

        self.card_faults = self._create_stat_card("CHATTER FAULTS", "0", "#FF3333")
        self.faults_val_lbl = self.card_faults.findChild(QLabel, "StatValLbl")
        stats_layout.addWidget(self.card_faults)

        self.card_bounce = self._create_stat_card("BOUNCE RATIO", "0.0 %", "#FFB74D")
        self.bounce_val_lbl = self.card_bounce.findChild(QLabel, "StatValLbl")
        stats_layout.addWidget(self.card_bounce)

        self.card_health = self._create_stat_card("SWITCH HEALTH", "100%", "#00E676")
        self.health_val_lbl = self.card_health.findChild(QLabel, "StatValLbl")
        stats_layout.addWidget(self.card_health)

        self.btn_guide = QPushButton()
        self.btn_guide.setObjectName("GuideCardBtn")
        self.btn_guide.setCursor(Qt.PointingHandCursor)
        self.btn_guide.setStyleSheet("""
            QPushButton#GuideCardBtn {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
                text-align: left;
            }
            QPushButton#GuideCardBtn:hover {
                background-color: rgba(255, 91, 6, 0.1);
                border: 1px solid rgba(255, 91, 6, 0.6);
            }
        """)
        
        g_layout = QVBoxLayout(self.btn_guide)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(2)
        
        g_title = QLabel("NEED HELP?")
        g_title.setAttribute(Qt.WA_TransparentForMouseEvents)
        g_title.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; background: transparent;")
        
        g_val = QLabel("GUIDE")
        g_val.setAttribute(Qt.WA_TransparentForMouseEvents)
        g_val.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; background: transparent;")
        
        g_layout.addWidget(g_title)
        g_layout.addWidget(g_val)
        
        self.btn_guide.clicked.connect(self._show_guide)
        stats_layout.addWidget(self.btn_guide)

        main_layout.addWidget(stats_frame)

        # ── 3. MIDDLE ROW: CLICK ZONE CANVAS & VECTOR MOUSE & GRAPH ──
        mid_widget = QWidget()
        mid_layout = QHBoxLayout(mid_widget)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(12)

        self.click_canvas = QFrame()
        self.click_canvas.setObjectName("DoubleClickTestZoneFrame")
        self.click_canvas.setCursor(Qt.CrossCursor)
        self.click_canvas.setStyleSheet("""
            QFrame#DoubleClickTestZoneFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border: 2px dashed rgba(255, 91, 6, 0.4);
                border-radius: 10px;
            }
            QFrame#DoubleClickTestZoneFrame:hover {
                background-color: rgba(255, 91, 6, 0.05);
                border-color: rgba(255, 91, 6, 0.8);
            }
        """)
        canvas_layout = QVBoxLayout(self.click_canvas)
        canvas_layout.setAlignment(Qt.AlignCenter)
        
        canvas_lbl1 = QLabel("INTERACTIVE CLICK TEST ZONE")
        canvas_lbl1.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        canvas_lbl2 = QLabel("Click anywhere inside this area using Left, Right, Middle, or Side Mouse Buttons")
        canvas_lbl2.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        canvas_lbl1.setAlignment(Qt.AlignCenter)
        canvas_lbl2.setAlignment(Qt.AlignCenter)

        canvas_layout.addWidget(canvas_lbl1)
        canvas_layout.addWidget(canvas_lbl2)

        mid_layout.addWidget(self.click_canvas, 2)

        self.mouse_graphic = HelxairoMouseGraphicWidget()
        mid_layout.addWidget(self.mouse_graphic, 0)

        main_layout.addWidget(mid_widget, 1)

        # ── 4. OSCILLOSCOPE WAVEFORM GRAPH ───────────────────
        self.pulse_graph = HelxairoPulseGraphWidget()
        main_layout.addWidget(self.pulse_graph)

        # ── 5. EVENT HISTORY TABLE ───────────────────────────
        self.log_table = HelxairoChatterLogTableWidget()
        self.log_table.setMaximumHeight(140)
        main_layout.addWidget(self.log_table)

    def _create_stat_card(self, title: str, init_val: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold;")
        
        val_lbl = QLabel(init_val)
        val_lbl.setObjectName("StatValLbl")
        val_lbl.setStyleSheet(f"color: {color_hex}; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold;")

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        return card

    def _on_threshold_changed(self, val):
        self._chatter_threshold_ms = float(val)
        self.thresh_val_lbl.setText(f"{val} ms")

    def _on_global_mouse_event(self, btn_name: str, action: str, os_time_ms: int):
        canvas_rect = self.click_canvas.rect()
        global_pos = QCursor.pos()
        local_pos = self.click_canvas.mapFromGlobal(global_pos)
        
        if not canvas_rect.contains(local_pos):
            return
            
        if action == 'press':
            self._handle_mouse_press_ctypes(btn_name, os_time_ms)
        elif action == 'release':
            self._handle_mouse_release_ctypes(btn_name, os_time_ms)

    def _handle_mouse_press_ctypes(self, btn_name: str, os_time_ms: int):
        if btn_name in self._reset_timers and self._reset_timers[btn_name].isActive():
            self._reset_timers[btn_name].stop()

        stats = self._button_stats[btn_name]
        self._total_clicks += 1
        stats['clicks'] += 1
        self._event_counter += 1

        inter_ms = 0.0
        if stats['release_ms'] > 0:
            inter_ms = float(os_time_ms - stats['release_ms'])

        stats['press_ms'] = os_time_ms
        is_chatter = False
        status_str = "NORMAL"

        if stats['release_ms'] > 0 and 0.0 <= inter_ms < self._chatter_threshold_ms:
            is_chatter = True
            self._chatter_fault_count += 1
            stats['faults'] += 1
            status_str = "CHATTER FAULT!"
            self.mouse_graphic.set_button_state(btn_name, 'chatter')
        elif stats['release_ms'] > 0 and self._chatter_threshold_ms <= inter_ms < 300.0:
            self._fast_double_count += 1
            status_str = "FAST DOUBLE"
            self.mouse_graphic.set_button_state(btn_name, 'fast_dc')
        else:
            self.mouse_graphic.set_button_state(btn_name, 'pressed')

        self.pulse_graph.add_sample(True, inter_ms, is_chatter)
        self.log_table.add_log_entry(self._event_counter, btn_name, 0.0, inter_ms, status_str)
        self._update_dashboard()

    def _handle_mouse_release_ctypes(self, btn_name: str, os_time_ms: int):
        stats = self._button_stats[btn_name]
        
        hold_ms = 0.0
        if stats['press_ms'] > 0:
            hold_ms = float(os_time_ms - stats['press_ms'])

        stats['release_ms'] = os_time_ms
        self.pulse_graph.add_sample(False, hold_ms, False)
        
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda b=btn_name: self.mouse_graphic.set_button_state(b, 'normal'))
        self._reset_timers[btn_name] = timer
        timer.start(150)

    def _update_dashboard(self):
        self.total_val_lbl.setText(str(self._total_clicks))
        self.faults_val_lbl.setText(str(self._chatter_fault_count))
        
        bounce_pct = 0.0
        if self._total_clicks > 0:
            bounce_pct = (self._chatter_fault_count / self._total_clicks) * 100.0
        self.bounce_val_lbl.setText(f"{bounce_pct:.1f} %")

        if bounce_pct == 0.0:
            self.health_val_lbl.setText("100% PERFECT")
            self.health_val_lbl.setStyleSheet("color: #00E676; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold;")
        elif bounce_pct < 5.0:
            self.health_val_lbl.setText("GOOD (MINOR)")
            self.health_val_lbl.setStyleSheet("color: #FFB74D; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold;")
        else:
            self.health_val_lbl.setText("DEFECTIVE!")
            self.health_val_lbl.setStyleSheet("color: #FF3333; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold;")

    def reset_test(self):
        self._event_counter = 0
        self._total_clicks = 0
        self._chatter_fault_count = 0
        self._fast_double_count = 0
        for btn in self._button_stats:
            self._button_stats[btn] = {'press_ms': 0, 'release_ms': 0, 'clicks': 0, 'faults': 0}
        self.pulse_graph.clear_graph()
        self.log_table.clear_logs()
        self.mouse_graphic.reset_all_buttons()
        self._update_dashboard()

    def _show_guide(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("How To Use")
        msg.setText(
            "1. Hover your mouse inside the dashed 'CLICK TEST ZONE'.\n"
            "2. Click as fast as you can (or drag click).\n"
            "3. If a physical hardware bounce registers under your set threshold, it will trigger a 'CHATTER FAULT'.\n"
            "4. A low 'SWITCH HEALTH' means your mouse switch might be physically failing and needs replacement."
        )
        msg.setIcon(QMessageBox.Information)
        
        ok_btn = FadeHoverButton("OK", is_secondary=True, border_radius=6.0)
        ok_btn.setStyleSheet("""
            FadeHoverButton {
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 20px;
            }
        """)
        msg.addButton(ok_btn, QMessageBox.AcceptRole)
        
        try:
            apply_custom_titlebar(msg, "#000000")
        except NameError:
            pass

        msg.setStyleSheet("""
            QMessageBox {
                background-color: #121212;
                color: #e0e0e0;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                padding: 10px;
            }
        """)
        msg.exec()


class ScrollWheelTestPanel(QWidget):
    """
    Scroll Wheel & Encoder Test Suite Panel.
    Component Name: ScrollWheelTestPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScrollWheelTestPanel")

        self._mouse_hook = None
        
        # Accumulator data
        self._total_events = 0
        self._steps_up = 0
        self._steps_down = 0
        self._max_velocity = 0
        self._current_velocity = 0.0
        self._accumulator_delta = 0
        
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(16)  # ~60fps
        self._ui_timer.timeout.connect(self._update_ui)
        
        self._setup_ui()

    def showEvent(self, event):
        if not self._mouse_hook or not self._mouse_hook.is_running:
            self._mouse_hook = LowLevelMouseHook()
            self._mouse_hook.mouse_event_signal.connect(self._on_global_mouse_event)
            self._mouse_hook.start()
        self._ui_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._ui_timer.stop()
        if self._mouse_hook and self._mouse_hook.is_running:
            try:
                self._mouse_hook.mouse_event_signal.disconnect(self._on_global_mouse_event)
            except Exception:
                pass
            self._mouse_hook.stop()
            self._mouse_hook.wait()
            self._mouse_hook = None
        super().hideEvent(event)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # Header Row
        header_frame = QFrame()
        header_frame.setObjectName("ScrollHeaderFrame")
        header_frame.setFixedHeight(38)
        header_frame.setStyleSheet("""
            QFrame#ScrollHeaderFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("ScrollBackBtn")
        self.back_btn.setFixedSize(30, 26)
        self.back_btn.setIcon(QIcon(back_icon_path))
        self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Benchmark Lab")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#ScrollBackBtn {
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
            QPushButton#ScrollBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("SCROLL WHEEL & ENCODER LAB")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        self.reset_btn = FadeHoverButton("Reset", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("ScrollResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#ScrollResetBtn, FadeHoverButton#ScrollResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self._reset_stats)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # Stats Grid
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        self.up_lbl = self._create_stat_card("SCROLL UP", "0", stats_layout)
        self.down_lbl = self._create_stat_card("SCROLL DOWN", "0", stats_layout)
        self.vel_lbl = self._create_stat_card("CURRENT VELOCITY", "0 lines/s", stats_layout)
        self.max_vel_lbl = self._create_stat_card("MAX VELOCITY", "0 lines/s", stats_layout)

        main_layout.addLayout(stats_layout)

        # Log visualizer area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                color: #e0e0e0;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 8px;
            }
            QTextEdit QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QTextEdit QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.log_area, 1)

    def _create_stat_card(self, title, init_val, parent_layout):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setAlignment(Qt.AlignCenter)
        
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 10px; border: none; background: transparent;")
        t_lbl.setAlignment(Qt.AlignCenter)
        
        v_lbl = QLabel(init_val)
        v_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 18px; font-weight: bold; border: none; background: transparent;")
        v_lbl.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(t_lbl)
        layout.addWidget(v_lbl)
        parent_layout.addWidget(card)
        return v_lbl

    def _reset_stats(self):
        self._total_events = 0
        self._steps_up = 0
        self._steps_down = 0
        self._max_velocity = 0
        self._current_velocity = 0.0
        self.log_area.clear()
        self._update_ui()

    def _on_global_mouse_event(self, btn_name, action, time_ms):
        if btn_name == 'wheel':
            try:
                delta = int(action)
                self._accumulator_delta += delta
                self._total_events += 1
                if delta > 0:
                    self._steps_up += 1
                else:
                    self._steps_down += 1
            except ValueError:
                pass

    def _update_ui(self):
        target_vel = 0
        
        if self._accumulator_delta != 0:
            lines_scrolled = self._accumulator_delta // WHEEL_DELTA
            if lines_scrolled == 0:
                # E.g. precision scroll wheels might send delta < 120
                lines_scrolled = 1 if self._accumulator_delta > 0 else -1
            
            # Simple velocity calc for the 16ms window
            target_vel = abs(lines_scrolled) * (1000 // 16)
                
            dir_str = "UP" if self._accumulator_delta > 0 else "DOWN"
            log_msg = f"[{self._total_events:04d}] Scroll {dir_str} | Delta: {self._accumulator_delta} | Lines: {abs(lines_scrolled)}"
            self.log_area.append(log_msg)
            
            # Auto scroll to bottom
            sb = self.log_area.verticalScrollBar()
            sb.setValue(sb.maximum())
            
            self._accumulator_delta = 0
            
            self.up_lbl.setText(str(self._steps_up))
            self.down_lbl.setText(str(self._steps_down))
            
        # Fast Attack, Slow Release (Smoothing)
        if target_vel > self._current_velocity:
            self._current_velocity = target_vel
        else:
            self._current_velocity += (target_vel - self._current_velocity) * 0.025
            
        # Snap to 0 if very slow to avoid floating point trailing
        if self._current_velocity < 0.5:
            self._current_velocity = 0
            
        if self._current_velocity > self._max_velocity:
            self._max_velocity = int(self._current_velocity)
            self.max_vel_lbl.setText(f"{self._max_velocity} lines/s")
            
        self.vel_lbl.setText(f"{int(self._current_velocity)} lines/s")


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
        QTimer.singleShot(0, self._hw_manager.start_manager)  # Start the background thread on tick 0
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
        
        # Initial device warning check after HardwareManager has time to initialize
        QTimer.singleShot(2000, self._check_device_warnings_initial)
        
        # Auto-initialize and start macro bridge (deferred by 1.5s for zero-latency page switch)
        QTimer.singleShot(1500, self._auto_init_macro_system)
        
    def set_bridge(self, bridge):
        """Set the macro bridge and load data."""
        self._bridge = bridge
        self._load_data()
        
    def _setup_ui(self):
        # Build absolute path for icons
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow_path = os.path.join(script_dir, "UI Icons", "up-arrow-triangle.svg").replace("\\", "/")
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")
        
        self.setStyleSheet(f"""
            QWidget#macroPanel {{
                background: transparent;
            }}
            QGroupBox {{
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 12px;
                padding: 15px;
                font-family: 'Orbitron', sans-serif;
                font-size: 15px;
                font-weight: bold;
                color: #FF5B06;
                background: rgba(255, 255, 255, 0.03);
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
            QLineEdit {{
                background: rgba(30, 33, 40, 0.9);
                color: #e0e0e0;
                border: none;
                padding: 10px;
                border-radius: 6px;
            }}
            QLineEdit:focus {{
                border: none;
            }}
            QSpinBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px 18px 0px 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }}
            QSpinBox QLineEdit {{
                background: transparent;
                color: #e0e0e0;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                selection-background-color: #FF5B06;
            }}
            QSpinBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QSpinBox::up-button {{
                width: 16px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-top-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }}
            QSpinBox::up-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox::up-arrow {{
                image: url('{up_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QSpinBox::down-button {{
                width: 16px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-bottom-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }}
            QSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QComboBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 28px 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 28px;
                padding: 4px 10px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }}
            QListWidget {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: #e0e0e0;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                font-weight: bold;
                outline: none;
            }}
            QListWidget::item:hover {{
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
            }}
            QLabel {{
                color: #e0e0e0;
            }}
            QCheckBox {{
                color: #e0e0e0;
                font-size: 13px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #555;
                background: rgba(30, 33, 40, 0.9);
            }}
            QCheckBox::indicator:hover {{
                border-color: #FF5B06;
            }}
            QCheckBox::indicator:checked {{
                background: #FF5B06;
                border: 2px solid #FF5B06;
            }}
            QScrollBar:vertical {{
                background: rgba(20, 22, 28, 0.6);
                width: 14px;
                border-radius: 7px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 6px;
                min-height: 40px;
                border: 1px solid rgba(253, 169, 3, 0.8);
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: 1px solid #FFFF00;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        header = QLabel("HELXAIRO")
        header.setFont(QFont("Orbitron", 24, QFont.Bold))
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
        tab_names = ["Home", "DPI", "Macro", "Benchmark", "Settings"]
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
                background: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 12px;
                min-height: 24px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
        """
        
        # Button mappings (1-5) using QPushButton + QMenu for proper submenus
        button_defaults = ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]
        self._button_mapping_btns = []
        
        # Menu style
        menu_style = """
            QMenu {
                background: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 25px 6px 20px;
                border-radius: 4px;
                background: transparent;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
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
                height: 4px;
                background: #2a2d35;
                margin: 0px;
                border-radius: 2px;
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
                border-radius: 2px;
            }
        """)
        self._debounce_slider.setCursor(Qt.PointingHandCursor)
        
        # Spinbox for manual input
        self._debounce_spinbox = AdaptiveSpinBox()
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
        
        # Add placeholders for remaining tabs (built deferred on tick 0)
        for _ in range(4):
            ph = QWidget()
            self._page_stack.addWidget(ph)
            
        layout.addWidget(self._page_stack, 1)
        self._page_stack.setCurrentIndex(0)
        self._update_tab_buttons()
        
        # Build remaining tabs deferred on tick 0 for zero-latency page load
        QTimer.singleShot(0, self._build_remaining_tabs)

    def _build_remaining_tabs(self):
        """Build DPI, Macro, Benchmark, and Settings tabs asynchronously on tick 0."""
        # Remove 4 placeholder widgets
        while self._page_stack.count() > 1:
            w = self._page_stack.widget(1)
            self._page_stack.removeWidget(w)
            w.deleteLater()

        # === DPI TAB ===
        dpi_tab = QWidget()
        dpi_scroll = SmoothScrollArea()
        dpi_scroll.setWidgetResizable(True)
        dpi_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(20, 22, 28, 0.6); width: 14px; border-radius: 7px; margin: 2px; }
            QScrollBar::handle:vertical { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06); border-radius: 6px; min-height: 40px; border: 1px solid rgba(253, 169, 3, 0.8); }
            QScrollBar::handle:vertical:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903); border: 1px solid #FFFF00; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
        """)
        
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
                height: 4px;
                background: #2a2d35;
                margin: 0px;
                border-radius: 2px;
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
                border-radius: 2px;
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
        mode_col.addWidget(self._mode_combo)
        sensor_controls.addLayout(mode_col)
        
        # Highest performance
        perf_col = QVBoxLayout()
        perf_row = QHBoxLayout()
        
        self._highest_perf_check = AnimatedCheckBox("Highest performance")
        self._highest_perf_check.setObjectName("helxairo_highestPerfCheck")
        perf_row.addWidget(self._highest_perf_check)
        
        perf_col.addLayout(perf_row)
        
        self._perf_time_combo = QComboBox()
        self._perf_time_combo.setObjectName("helxairo_perfTimeCombo")
        self._perf_time_combo.addItems(["10s", "30s", "1min", "2min", "5min", "10min"])
        self._perf_time_combo.setCurrentText("1min")
        self._perf_time_combo.setFixedWidth(80)
        self._perf_time_combo.currentTextChanged.connect(self._on_perf_time_changed)
        perf_col.addWidget(self._perf_time_combo)
        sensor_controls.addLayout(perf_col)
        
        # Toggle switches
        toggles_col = QVBoxLayout()
        toggles_col.setSpacing(8)
        
        self._ripple_toggle = AnimatedCheckBox("Ripple control")
        self._ripple_toggle.setObjectName("helxairo_rippleToggle")
        toggles_col.addWidget(self._ripple_toggle)
        
        self._angle_snap_toggle = AnimatedCheckBox("Angle snap")
        self._angle_snap_toggle.setObjectName("helxairo_angleSnapToggle")
        toggles_col.addWidget(self._angle_snap_toggle)
        
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
                height: 4px;
                background: #2a2d35;
                margin: 0px;
                border-radius: 2px;
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
                border-radius: 2px;
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
                height: 4px;
                background: #2a2d35;
                margin: 0px;
                border-radius: 2px;
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
                border-radius: 2px;
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
        dpi_tab_layout.setSpacing(0)
        
        # Add device warning overlay OUTSIDE scroll area so it's always visible
        self._dpi_device_warning = DeviceWarningOverlay(dpi_tab)
        dpi_tab_layout.addWidget(self._dpi_device_warning)
        
        dpi_tab_layout.addWidget(dpi_scroll)
        
        self._page_stack.addWidget(dpi_tab)
        
        # === MACRO TAB ===
        macro_tab = QWidget()
        macro_tab.setObjectName("helxairo_macroTab")
        macro_tab_layout = QVBoxLayout(macro_tab)
        macro_tab_layout.setContentsMargins(20, 15, 20, 20)
        macro_tab_layout.setSpacing(15)

        # ── SUB-TAB NAVIGATION BAR ──────────────────
        sub_tab_container = QWidget()
        sub_tab_container.setObjectName("macroSubNav")
        sub_tab_container.setFixedHeight(40)
        sub_tab_container.setStyleSheet("""
            QWidget#macroSubNav {
                background: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                color: #888888;
                border: none;
                border-bottom: 2px solid transparent;
                border-radius: 6px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: 600;
                font-family: 'Orbitron', sans-serif;
            }
            QPushButton:hover {
                color: #ffffff;
                background: rgba(255, 91, 6, 0.12);
                border-radius: 6px;
            }
            QPushButton:checked {
                color: #FF5B06;
                border-bottom: 2px solid #FF5B06;
                background: rgba(255, 91, 6, 0.06);
                border-radius: 6px;
            }
            QPushButton:checked:hover {
                color: #FF5B06;
                background: rgba(255, 91, 6, 0.15);
                border-radius: 6px;
            }
        """)
        sub_tab_layout = QHBoxLayout(sub_tab_container)
        sub_tab_layout.setContentsMargins(6, 5, 6, 5)
        sub_tab_layout.setSpacing(6)

        sub_tab_names = ["Editor", "Live Recorder", "Profiles"]
        sub_tab_keys = ["editor", "recorder", "profiles"]
        self._macro_sub_buttons = []
        self._current_macro_subtab = 0  # Default to Editor

        for i, (name, key) in enumerate(zip(sub_tab_names, sub_tab_keys)):
            btn = QPushButton(name)
            btn.setObjectName(f"macroSubNav_{key}")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda checked, idx=i: self._switch_macro_subtab(idx))
            self._macro_sub_buttons.append(btn)
            sub_tab_layout.addWidget(btn)

        sub_tab_layout.addStretch()
        macro_tab_layout.addWidget(sub_tab_container)

        # ── SUB-PAGE STACK ──────────────────────────
        self._macro_sub_stack = QStackedWidget()
        self._macro_sub_stack.setObjectName("macroSubStack")

        # Shared QGroupBox style — matches Settings tab & HELXAIL exactly
        _grp_style = """
            QGroupBox {
                color: #ff5b06;
                font-family: 'Orbitron', sans-serif;
                font-size: 16px;
                font-weight: bold;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 10px;
                padding: 15px;
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

        # Shared combo style — matches HELXAIL hardware panel style
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow_path = os.path.join(script_dir, "UI Icons", "up-arrow-triangle.svg").replace("\\", "/")
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")

        _spinbox_style = f"""
            QSpinBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px 18px 0px 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }}
            QSpinBox QLineEdit {{
                background: transparent;
                color: #e0e0e0;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
                selection-background-color: #FF5B06;
            }}
            QSpinBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QSpinBox::up-button {{
                width: 16px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-top-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }}
            QSpinBox::up-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox::up-arrow {{
                image: url('{up_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QSpinBox::down-button {{
                width: 16px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-bottom-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }}
            QSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 8px;
                height: 8px;
            }}
        """

        _combo_style = f"""
            QComboBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 28px 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 28px;
                padding: 4px 10px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }}
        """

        _unit_combo_style = f"""
            QComboBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px 18px 4px 8px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }}
            QComboBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 14px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 8px;
                height: 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2128;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 24px;
                padding: 2px 6px;
                background: transparent;
                color: #e0e0e0;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }}
        """

        _lineedit_style = """
            QLineEdit {
                background-color: rgba(30, 30, 30, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 8px;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #FF5B06;
                background-color: rgba(30, 30, 30, 0.85);
            }
        """

        _scroll_style = """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(20, 22, 28, 0.6);
                width: 14px;
                border-radius: 7px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 6px;
                min-height: 40px;
                border: 1px solid rgba(253, 169, 3, 0.8);
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: 1px solid #FFFF00;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """

        _list_style = """
            QListWidget {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: #e0e0e0;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 3px 6px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                font-weight: bold;
                outline: none;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
            }
        """

        # ── SUB-PAGE 0: MACRO EDITOR (Default Page) ──────────────
        page_editor = QWidget()
        page_editor_scroll = SmoothScrollArea()
        page_editor_scroll.setWidgetResizable(True)
        page_editor_scroll.setStyleSheet(_scroll_style)
        page_editor_content = QWidget()
        page_editor_content.setStyleSheet("background: transparent;")
        layout_editor = QVBoxLayout(page_editor_content)
        layout_editor.setContentsMargins(0, 0, 0, 0)
        layout_editor.setSpacing(15)

        # Quick Actions (Auto-Clicker) Card at top of Editor
        quick_group = QGroupBox("Quick Actions")
        quick_group.setStyleSheet(_grp_style)
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setSpacing(12)
        quick_layout.setAlignment(Qt.AlignVCenter)

        ac_layout = QHBoxLayout()
        ac_layout.setSpacing(10)
        ac_layout.setAlignment(Qt.AlignVCenter)

        # 1. Macro Name Input
        ac_name_lbl = QLabel("Macro Name")
        ac_name_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        ac_name_lbl.setAlignment(Qt.AlignVCenter)
        ac_layout.addWidget(ac_name_lbl, 0, Qt.AlignVCenter)

        self.ac_name_input = QLineEdit()
        self.ac_name_input.setObjectName("helxairo_acName")
        self.ac_name_input.setPlaceholderText("Auto-clicker")
        self.ac_name_input.setFixedWidth(110)
        self.ac_name_input.setFixedHeight(30)
        self.ac_name_input.setStyleSheet(_lineedit_style)
        ac_layout.addWidget(self.ac_name_input, 0, Qt.AlignVCenter)

        # 2. Bound Apps Input
        ac_apps_lbl = QLabel("Bound Apps")
        ac_apps_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        ac_apps_lbl.setAlignment(Qt.AlignVCenter)
        ac_apps_lbl.setToolTip("Auto-activate this profile when specified apps/games are running (comma-separated, e.g., gta5.exe, valorant.exe)")
        ac_layout.addWidget(ac_apps_lbl, 0, Qt.AlignVCenter)

        self.ac_apps_input = QLineEdit()
        self.ac_apps_input.setObjectName("helxairo_acApps")
        self.ac_apps_input.setPlaceholderText("e.g. gta5.exe")
        self.ac_apps_input.setToolTip("Auto-activate this profile when specified apps/games are running (comma-separated, e.g., gta5.exe, valorant.exe)")
        self.ac_apps_input.setFixedWidth(110)
        self.ac_apps_input.setFixedHeight(30)
        self.ac_apps_input.setStyleSheet(_lineedit_style)
        self.ac_apps_input.editingFinished.connect(self._save_ac_apps)
        ac_layout.addWidget(self.ac_apps_input, 0, Qt.AlignVCenter)

        # 2. Auto Click Key Selector
        ac_lbl = QLabel("Auto Click Key")
        ac_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        ac_lbl.setAlignment(Qt.AlignVCenter)
        ac_layout.addWidget(ac_lbl, 0, Qt.AlignVCenter)

        self.ac_button = QComboBox()
        self.ac_button.setObjectName("helxairo_acType")
        self.ac_button.addItems(["Left Click", "Right Click", "Middle Click", "Custom Key"])
        self.ac_button.setFixedWidth(120)
        self.ac_button.setFixedHeight(30)
        self.ac_button.setStyleSheet(_combo_style)
        self.ac_button.currentTextChanged.connect(self._on_ac_type_changed)
        ac_layout.addWidget(self.ac_button, 0, Qt.AlignVCenter)

        self.ac_custom_key = HotkeyRecordButton("E")
        self.ac_custom_key.setFixedWidth(80)
        self.ac_custom_key.setFixedHeight(30)
        self.ac_custom_key.setVisible(False)
        ac_layout.addWidget(self.ac_custom_key, 0, Qt.AlignVCenter)

        interval_lbl = QLabel("Interval")
        interval_lbl.setStyleSheet("color: #e0e0e0;")
        interval_lbl.setAlignment(Qt.AlignVCenter)
        ac_layout.addWidget(interval_lbl, 0, Qt.AlignVCenter)

        self.ac_interval = AdaptiveSpinBox()
        self.ac_interval.setObjectName("helxairo_acInterval")
        self.ac_interval.setRange(1, 999)
        self.ac_interval.setValue(500)
        self.ac_interval.setSingleStep(5)
        self.ac_interval.setSuffix("")
        self.ac_interval.setFixedWidth(75)
        self.ac_interval.setFixedHeight(30)
        self.ac_interval.setStyleSheet(_spinbox_style)
        ac_layout.addWidget(self.ac_interval, 0, Qt.AlignVCenter)

        self.ac_unit = QComboBox()
        self.ac_unit.setObjectName("helxairo_acUnit")
        self.ac_unit.addItems(["ms", "s"])
        self.ac_unit.setCurrentText("ms")
        self.ac_unit.setFixedWidth(65)
        self.ac_unit.setFixedHeight(30)
        self.ac_unit.setStyleSheet(_unit_combo_style)
        self.ac_unit.currentTextChanged.connect(self._on_ac_unit_changed)
        ac_layout.addWidget(self.ac_unit, 0, Qt.AlignVCenter)

        hotkey_lbl = QLabel("Hotkey")
        hotkey_lbl.setStyleSheet("color: #e0e0e0;")
        hotkey_lbl.setAlignment(Qt.AlignVCenter)
        ac_layout.addWidget(hotkey_lbl, 0, Qt.AlignVCenter)

        self.ac_hotkey = HotkeyRecordButton("F8")
        self.ac_hotkey.setFixedWidth(80)
        self.ac_hotkey.setFixedHeight(30)
        ac_layout.addWidget(self.ac_hotkey, 0, Qt.AlignVCenter)

        self.ac_create_btn = FadeHoverButton("Create", border_radius=6.0)
        self.ac_create_btn.setObjectName("helxairo_acCreateBtn")
        self.ac_create_btn.setFixedHeight(30)
        self.ac_create_btn.setFixedWidth(85)
        self.ac_create_btn.clicked.connect(self._create_autoclicker)
        ac_layout.addWidget(self.ac_create_btn, 0, Qt.AlignVCenter)

        ac_layout.addStretch()
        quick_layout.addLayout(ac_layout)
        layout_editor.addWidget(quick_group)

        editor_group = QGroupBox("Macro Editor")
        editor_group.setStyleSheet(_grp_style)
        editor_group_layout = QVBoxLayout(editor_group)
        editor_group_layout.setSpacing(12)

        editor_layout = QHBoxLayout()
        editor_layout.setSpacing(20)

        # Left Column: Macro list
        # Left Column: Unified Macro list
        col1 = QVBoxLayout()
        col1_lbl = QLabel("Macro list")
        col1_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px;")
        col1.addWidget(col1_lbl)

        # Container Frame for Search Bar + Macro Item List
        self.macro_list_container = QFrame()
        self.macro_list_container.setObjectName("macroListContainer")
        self.macro_list_container.setStyleSheet("""
            QFrame#macroListContainer {
                background: rgba(18, 20, 26, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """)
        macro_container_layout = QVBoxLayout(self.macro_list_container)
        macro_container_layout.setContentsMargins(8, 8, 8, 8)
        macro_container_layout.setSpacing(8)

        # Search Bar + Sort Button Row inside Container
        search_sort_row = QHBoxLayout()
        search_sort_row.setContentsMargins(0, 0, 0, 0)
        search_sort_row.setSpacing(6)

        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "UI Icons")
        sort_icon_path = os.path.join(icons_dir, "sort-icon-white.svg")

        # Square Sort Button (32x32, fixed aspect ratio)
        self.macro_sort_btn = QPushButton()
        self.macro_sort_btn.setObjectName("macroSortBtn")
        self.macro_sort_btn.setFixedSize(32, 32)
        self.macro_sort_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if os.path.exists(sort_icon_path):
            self.macro_sort_btn.setIcon(QIcon(sort_icon_path))
            self.macro_sort_btn.setIconSize(QSize(16, 16))
        self.macro_sort_btn.setToolTip("Sort Macros")
        self.macro_sort_btn.setCursor(Qt.PointingHandCursor)
        self.macro_sort_btn.setStyleSheet("""
            QPushButton#macroSortBtn {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton#macroSortBtn:hover {
                background: rgba(255, 255, 255, 0.15);
                border-color: #FF5B06;
            }
            QPushButton#macroSortBtn:pressed {
                background: rgba(255, 91, 6, 0.25);
                border-color: #FF5B06;
            }
        """)
        self.macro_sort_btn.clicked.connect(self._show_sort_menu)
        search_sort_row.addWidget(self.macro_sort_btn)

        # Responsive Search Bar inside Container (expands to fill remaining width)
        self.macro_search_input = QLineEdit()
        self.macro_search_input.setObjectName("macroSearchInput")
        self.macro_search_input.setPlaceholderText("Search macro...")
        self.macro_search_input.setFixedHeight(32)
        self.macro_search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.macro_search_input.setStyleSheet("""
            QLineEdit#macroSearchInput {
                background: rgba(255, 255, 255, 0.06);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px 10px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }
            QLineEdit#macroSearchInput:focus {
                border: 1px solid #FF5B06;
                background: rgba(255, 255, 255, 0.1);
            }
        """)
        self.macro_search_input.textChanged.connect(self._filter_macro_list)
        search_sort_row.addWidget(self.macro_search_input, 1)

        macro_container_layout.addLayout(search_sort_row)

        self.active_list = QListWidget()
        self.active_list.setObjectName("helxairo_activeList")
        # NOTE FOR AGENTS / DEVELOPERS: DO NOT EVER re-enable horizontal scrollbars on active_list.
        # It must strictly remain ScrollBarAlwaysOff to prevent visual glitches and framedrops.
        self.active_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.active_list.setMinimumHeight(330)
        self.active_list.setStyleSheet(_list_style + """
            QListWidget#helxairo_activeList {
                border: none;
                background: transparent;
            }
            QListWidget#helxairo_activeList QScrollBar:horizontal {
                height: 0px;
                background: transparent;
            }
            QListWidget#helxairo_activeList::item {
                padding: 0px;
                margin: 2px 14px 2px 0px;
                background: transparent;
                border: none;
            }
            QListWidget#helxairo_activeList::item:selected {
                background: transparent;
                border: none;
            }
            QListWidget#helxairo_activeList::item:hover {
                background: transparent;
                border: none;
            }
        """)
        enable_rubber_band_selection(self.active_list)
        
        self.active_list.itemSelectionChanged.connect(self._on_macro_selection_changed)
        
        def _on_active_list_resize(event):
            type(self.active_list).resizeEvent(self.active_list, event)
            vp_w = max(0, self.active_list.viewport().width() - 18)
            for i in range(self.active_list.count()):
                item = self.active_list.item(i)
                w = self.active_list.itemWidget(item)
                if item and w:
                    item_h = max(38, w.sizeHint().height())
                    item.setSizeHint(QSize(vp_w, item_h))
            self.active_list.doItemsLayout()

        self.active_list.resizeEvent = _on_active_list_resize
        macro_container_layout.addWidget(self.active_list)
        col1.addWidget(self.macro_list_container)

        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "UI Icons")

        col1_btns = QHBoxLayout()
        col1_btns.setSpacing(6)

        self.editor_new_macro_btn = FadeHoverButton("", is_secondary=False)
        self.editor_new_macro_btn.setIcon(QIcon(os.path.join(icons_dir, "plus-icon.svg")))
        self.editor_new_macro_btn.setIconSize(QSize(16, 16))
        self.editor_new_macro_btn.setFixedHeight(32)
        self.editor_new_macro_btn.setToolTip("New Macro")
        col1_btns.addWidget(self.editor_new_macro_btn)

        self.edit_selected_btn = FadeHoverButton("", is_secondary=True)
        self.edit_selected_btn.setObjectName("helxairo_editSelected")
        self.edit_selected_btn.setIcon(QIcon(os.path.join(icons_dir, "edit.svg")))
        self.edit_selected_btn.setIconSize(QSize(16, 16))
        self.edit_selected_btn.setFixedHeight(32)
        self.edit_selected_btn.setToolTip("Edit Macro")
        self.edit_selected_btn.clicked.connect(self._edit_selected)
        col1_btns.addWidget(self.edit_selected_btn)

        self.toggle_macro_btn = FadeHoverButton("", is_secondary=True)
        self.toggle_macro_btn.setObjectName("helxairo_toggleMacro")
        self.toggle_macro_btn.setIcon(QIcon(os.path.join(icons_dir, "star-white.svg")))
        self.toggle_macro_btn.setIconSize(QSize(16, 16))
        self.toggle_macro_btn.setFixedHeight(32)
        self.toggle_macro_btn.setToolTip("Toggle Active")
        self.toggle_macro_btn.clicked.connect(self._toggle_selected_macro)
        col1_btns.addWidget(self.toggle_macro_btn)

        self.delete_selected_btn = FadeHoverButton("", is_secondary=True)
        self.delete_selected_btn.setObjectName("helxairo_deleteSelected")
        self.delete_selected_btn.setIcon(QIcon(os.path.join(icons_dir, "trash-icon-white.svg")))
        self.delete_selected_btn.setIconSize(QSize(16, 16))
        self.delete_selected_btn.setFixedHeight(32)
        self.delete_selected_btn.setToolTip("Delete Macro")
        self.delete_selected_btn.clicked.connect(self._delete_selected)
        col1_btns.addWidget(self.delete_selected_btn)

        self.disable_all_btn = FadeHoverButton("", is_secondary=True)
        self.disable_all_btn.setObjectName("helxairo_stopAll")
        self.disable_all_btn.setIcon(QIcon(os.path.join(icons_dir, "close-icon-white.svg")))
        self.disable_all_btn.setIconSize(QSize(16, 16))
        self.disable_all_btn.setFixedHeight(32)
        self.disable_all_btn.setToolTip("Stop All Macros")
        self.disable_all_btn.clicked.connect(self._disable_all)
        col1_btns.addWidget(self.disable_all_btn)

        col1.addLayout(col1_btns)
        editor_layout.addLayout(col1, 1)

        # Middle Column: List of keys
        col2 = QVBoxLayout()
        col2_lbl = QLabel("List of keys")
        col2_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px;")
        col2.addWidget(col2_lbl)

        self.editor_keys_list = QListWidget()
        self.editor_keys_list.setObjectName("helxairo_editorKeysList")
        self.editor_keys_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_keys_list.setMinimumHeight(350)
        self.editor_keys_list.setSpacing(4)
        self.editor_keys_list.setStyleSheet("""
            QListWidget#helxairo_editorKeysList {
                background: rgba(18, 20, 26, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                color: #e0e0e0;
                font-size: 13px;
                outline: none;
                padding: 6px;
            }
            QListWidget#helxairo_editorKeysList::item {
                background: transparent;
                border: none;
                padding: 0px;
                margin-bottom: 2px;
            }
            QListWidget#helxairo_editorKeysList::item:selected {
                background: transparent;
                outline: none;
            }
            QListWidget#helxairo_editorKeysList::item:hover {
                background: transparent;
            }
        """)
        enable_rubber_band_selection(self.editor_keys_list)

        def _on_editor_keys_list_resize(event):
            type(self.editor_keys_list).resizeEvent(self.editor_keys_list, event)
            vp_w = max(0, self.editor_keys_list.viewport().width() - 4)
            for i in range(self.editor_keys_list.count()):
                item = self.editor_keys_list.item(i)
                w = self.editor_keys_list.itemWidget(item)
                if item and w:
                    item.setSizeHint(QSize(vp_w, w.sizeHint().height()))
            self.editor_keys_list.doItemsLayout()

        self.editor_keys_list.resizeEvent = _on_editor_keys_list_resize
        col2.addWidget(self.editor_keys_list)

        col2_btns = QHBoxLayout()
        col2_btns.setSpacing(10)

        self.editor_modify_key_btn = FadeHoverButton("Modify", is_secondary=True)
        self.editor_modify_key_btn.setFixedHeight(32)
        self.editor_modify_key_btn.setToolTip("Modify selected key action")
        col2_btns.addWidget(self.editor_modify_key_btn)

        self.editor_delete_key_btn = FadeHoverButton("Delete", is_secondary=True)
        self.editor_delete_key_btn.setFixedHeight(32)
        self.editor_delete_key_btn.setToolTip("Delete selected key from sequence")
        col2_btns.addWidget(self.editor_delete_key_btn)

        col2.addLayout(col2_btns)
        editor_layout.addLayout(col2, 1)

        # Right Column: Controls
        col3 = QVBoxLayout()
        col3.setSpacing(10)
        col3.addSpacing(22)

        self.editor_start_record_btn = FadeHoverButton("Start recording", is_secondary=True)
        self.editor_start_record_btn.setFixedHeight(36)
        col3.addWidget(self.editor_start_record_btn)

        col3.addSpacing(15)

        _radio_style = """
            QRadioButton { color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px; spacing: 8px; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; background: #2a2d35; border: none; }
            QRadioButton::indicator:checked { background: #FF5B06; border: none; }
        """
        
        self.rb_auto_delay = QRadioButton("Auto insert delay")
        self.rb_auto_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_auto_delay)

        self.rb_default_delay = QRadioButton("Default delay")
        self.rb_default_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_default_delay)

        self.spin_default_delay = AdaptiveSpinBox()
        self.spin_default_delay.setRange(0, 9999)
        self.spin_default_delay.setValue(10)
        self.spin_default_delay.setAlignment(Qt.AlignCenter)
        self.spin_default_delay.setFixedWidth(85)
        self.spin_default_delay.setStyleSheet(_spinbox_style)
        col3.addWidget(self.spin_default_delay)

        col3.addSpacing(15)

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

        self.spin_cycle_times = AdaptiveSpinBox()
        self.spin_cycle_times.setRange(1, 9999)
        self.spin_cycle_times.setValue(1)
        self.spin_cycle_times.setAlignment(Qt.AlignCenter)
        self.spin_cycle_times.setFixedWidth(85)
        self.spin_cycle_times.setStyleSheet(_spinbox_style)
        col3.addWidget(self.spin_cycle_times)

        col3.addSpacing(15)

        lbl_insert = QLabel("Insert command")
        lbl_insert.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px;")
        col3.addWidget(lbl_insert)

        self.combo_insert_cmd = QComboBox()
        self.combo_insert_cmd.setStyleSheet(_combo_style)
        col3.addWidget(self.combo_insert_cmd)

        col3.addStretch()

        self.editor_save_btn = FadeHoverButton("Save", is_secondary=False)
        self.editor_save_btn.setIcon(QIcon(os.path.join(icons_dir, "save-floppy.svg")))
        self.editor_save_btn.setIconSize(QSize(16, 16))
        self.editor_save_btn.setFixedHeight(32)
        col3.addWidget(self.editor_save_btn)

        editor_layout.addLayout(col3, 1)
        editor_group_layout.addLayout(editor_layout)
        layout_editor.addWidget(editor_group)
        layout_editor.addStretch()

        page_editor_scroll.setWidget(page_editor_content)
        pe_layout = QVBoxLayout(page_editor)
        pe_layout.setContentsMargins(0, 0, 0, 0)
        pe_layout.addWidget(page_editor_scroll)

        self._macro_sub_stack.addWidget(page_editor)

        # ── SUB-PAGE 2: LIVE RECORDER ─────────────────────────────
        page_recorder = QWidget()
        page_recorder_scroll = SmoothScrollArea()
        page_recorder_scroll.setWidgetResizable(True)
        page_recorder_scroll.setStyleSheet(_scroll_style)
        page_recorder_content = QWidget()
        page_recorder_content.setStyleSheet("background: transparent;")
        layout_recorder = QVBoxLayout(page_recorder_content)
        layout_recorder.setContentsMargins(0, 0, 0, 0)
        layout_recorder.setSpacing(15)

        recorder_group = QGroupBox("Record Macro")
        recorder_group.setStyleSheet(_grp_style)
        recorder_layout = QVBoxLayout(recorder_group)
        recorder_layout.setSpacing(12)

        self._recorder = None
        self._player = None
        self._current_recording = None

        record_controls = QHBoxLayout()
        record_controls.setSpacing(10)

        self.record_btn = FadeHoverButton("Record")
        self.record_btn.setObjectName("helxairo_recordBtn")
        self.record_btn.setFixedSize(120, 34)
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

        options_row = QHBoxLayout()
        options_row.setSpacing(15)

        self.record_mouse_cb = AnimatedCheckBox("Mouse Clicks")
        self.record_mouse_cb.setChecked(True)
        options_row.addWidget(self.record_mouse_cb)

        self.record_movement_cb = AnimatedCheckBox("Mouse Movement")
        self.record_movement_cb.setChecked(False)
        options_row.addWidget(self.record_movement_cb)

        self.record_keyboard_cb = AnimatedCheckBox("Keyboard")
        self.record_keyboard_cb.setChecked(True)
        options_row.addWidget(self.record_keyboard_cb)

        options_row.addStretch()
        recorder_layout.addLayout(options_row)

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

        self.loop_spin = AdaptiveSpinBox()
        self.loop_spin.setObjectName("helxairo_loopSpin")
        self.loop_spin.setRange(0, 999)
        self.loop_spin.setValue(1)
        self.loop_spin.setFixedWidth(75)
        self.loop_spin.setToolTip("0 = infinite loop")
        self.loop_spin.setStyleSheet(_spinbox_style)
        playback_row.addWidget(self.loop_spin)

        hotkey2_lbl = QLabel("Hotkey:")
        hotkey2_lbl.setStyleSheet("color: #e0e0e0;")
        playback_row.addWidget(hotkey2_lbl)

        self.playback_hotkey = HotkeyRecordButton("F9")
        playback_row.addWidget(self.playback_hotkey)

        playback_row.addStretch()
        recorder_layout.addLayout(playback_row)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)

        self.save_recording_btn = FadeHoverButton("Save Recording")
        self.save_recording_btn.setObjectName("helxairo_saveRec")
        self.save_recording_btn.setFixedHeight(34)
        self.save_recording_btn.clicked.connect(self._save_recording)
        self.save_recording_btn.setEnabled(False)
        save_row.addWidget(self.save_recording_btn)

        self.play_recording_btn = FadeHoverButton("Play")
        self.play_recording_btn.setObjectName("helxairo_playRec")
        self.play_recording_btn.setFixedHeight(34)
        self.play_recording_btn.clicked.connect(self._play_recording)
        self.play_recording_btn.setEnabled(False)
        save_row.addWidget(self.play_recording_btn)

        self.clear_recording_btn = FadeHoverButton("Clear", is_secondary=True)
        self.clear_recording_btn.setObjectName("helxairo_clearRec")
        self.clear_recording_btn.setFixedHeight(34)
        self.clear_recording_btn.clicked.connect(self._clear_recording)
        save_row.addWidget(self.clear_recording_btn)

        save_row.addStretch()
        recorder_layout.addLayout(save_row)
        layout_recorder.addWidget(recorder_group)
        layout_recorder.addStretch()

        page_recorder_scroll.setWidget(page_recorder_content)
        pr_layout = QVBoxLayout(page_recorder)
        pr_layout.setContentsMargins(0, 0, 0, 0)
        pr_layout.addWidget(page_recorder_scroll)

        self._macro_sub_stack.addWidget(page_recorder)

        # ── SUB-PAGE 3: PROFILES ─────────────────────────────────
        page_profiles = QWidget()
        page_profiles_scroll = SmoothScrollArea()
        page_profiles_scroll.setWidgetResizable(True)
        page_profiles_scroll.setStyleSheet(_scroll_style)
        page_profiles_content = QWidget()
        page_profiles_content.setStyleSheet("background: transparent;")
        layout_profiles = QVBoxLayout(page_profiles_content)
        layout_profiles.setContentsMargins(0, 0, 0, 0)
        layout_profiles.setSpacing(15)

        profile_group = QGroupBox("Profiles")
        profile_group.setStyleSheet(_grp_style)
        profile_layout = QHBoxLayout(profile_group)

        profile_left = QVBoxLayout()

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("helxairo_profileList")
        self.profile_list.setMaximumWidth(220)
        self.profile_list.setIconSize(QSize(16, 16))
        self.profile_list.setStyleSheet(_list_style)
        enable_rubber_band_selection(self.profile_list)
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.profile_list.itemDoubleClicked.connect(self._on_profile_double_clicked)
        profile_left.addWidget(self.profile_list)

        profile_btn_row = QHBoxLayout()
        profile_btn_row.setSpacing(6)

        import os as _os
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        _plus_icon_path = _os.path.join(_script_dir, "UI Icons", "plus-icon.svg").replace("\\", "/")
        _load_icon_path = _os.path.join(_script_dir, "UI Icons", "folder-load.svg").replace("\\", "/")
        _save_icon_path = _os.path.join(_script_dir, "UI Icons", "save-floppy.svg").replace("\\", "/")
        _trash_icon_path = _os.path.join(_script_dir, "UI Icons", "trash-icon-white.svg").replace("\\", "/")

        _btn_icon_style = """
            QPushButton {
                background: rgba(40, 40, 40, 0.8);
                border: none;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 91, 6, 0.3);
            }
            QPushButton:pressed {
                background: rgba(255, 91, 6, 0.5);
            }
            QPushButton#helxairo_delProfileBtn:hover {
                background: rgba(220, 53, 69, 0.4);
            }
        """

        # 1. New Profile (+)
        self.new_profile_btn = QPushButton()
        self.new_profile_btn.setObjectName("helxairo_newProfileBtn")
        self.new_profile_btn.setFixedSize(34, 32)
        self.new_profile_btn.setCursor(Qt.PointingHandCursor)
        self.new_profile_btn.setToolTip("Create New Profile")
        self.new_profile_btn.setStyleSheet(_btn_icon_style)
        if _os.path.exists(_plus_icon_path):
            self.new_profile_btn.setIcon(QIcon(_plus_icon_path))
            self.new_profile_btn.setIconSize(QSize(16, 16))
        else:
            self.new_profile_btn.setText("+")
        self.new_profile_btn.clicked.connect(self._new_profile)
        profile_btn_row.addWidget(self.new_profile_btn)

        # 2. Load / Activate Profile (Folder with Down Arrow)
        self.load_profile_btn = QPushButton()
        self.load_profile_btn.setObjectName("helxairo_loadProfileBtn")
        self.load_profile_btn.setFixedSize(34, 32)
        self.load_profile_btn.setCursor(Qt.PointingHandCursor)
        self.load_profile_btn.setToolTip("Load & Activate Selected Profile (or double-click profile)")
        self.load_profile_btn.setStyleSheet(_btn_icon_style)
        if _os.path.exists(_load_icon_path):
            self.load_profile_btn.setIcon(QIcon(_load_icon_path))
            self.load_profile_btn.setIconSize(QSize(16, 16))
        else:
            self.load_profile_btn.setText("📂")
        self.load_profile_btn.clicked.connect(self._load_selected_profile)
        profile_btn_row.addWidget(self.load_profile_btn)

        # 3. Save Profile (Floppy Disk)
        self.save_profile_btn = QPushButton()
        self.save_profile_btn.setObjectName("helxairo_saveProfileBtn")
        self.save_profile_btn.setFixedSize(34, 32)
        self.save_profile_btn.setCursor(Qt.PointingHandCursor)
        self.save_profile_btn.setToolTip("Save Profile Settings")
        self.save_profile_btn.setStyleSheet(_btn_icon_style)
        if _os.path.exists(_save_icon_path):
            self.save_profile_btn.setIcon(QIcon(_save_icon_path))
            self.save_profile_btn.setIconSize(QSize(16, 16))
        else:
            self.save_profile_btn.setText("💾")
        self.save_profile_btn.clicked.connect(self._save_profile)
        profile_btn_row.addWidget(self.save_profile_btn)

        # 4. Delete Profile (Trash)
        self.delete_profile_btn = QPushButton()
        self.delete_profile_btn.setObjectName("helxairo_delProfileBtn")
        self.delete_profile_btn.setFixedSize(34, 32)
        self.delete_profile_btn.setCursor(Qt.PointingHandCursor)
        self.delete_profile_btn.setToolTip("Delete Selected Profile")
        self.delete_profile_btn.setStyleSheet(_btn_icon_style)
        if _os.path.exists(_trash_icon_path):
            self.delete_profile_btn.setIcon(QIcon(_trash_icon_path))
            self.delete_profile_btn.setIconSize(QSize(16, 16))
        else:
            self.delete_profile_btn.setText("-")
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        profile_btn_row.addWidget(self.delete_profile_btn)

        profile_btn_row.addStretch()
        profile_left.addLayout(profile_btn_row)
        profile_layout.addLayout(profile_left)

        profile_right = QVBoxLayout()

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        _profile_input_style = """
            QLineEdit {
                background-color: rgba(30, 30, 30, 0.85);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 0px 10px;
                min-height: 32px;
                max-height: 32px;
                height: 32px;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #FF5B06;
                background-color: rgba(30, 30, 30, 0.85);
            }
        """

        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("helxairo_profileName")
        self.profile_name.setPlaceholderText("Profile name...")
        self.profile_name.setStyleSheet(_profile_input_style)
        form.addRow("Name", self.profile_name)

        profile_right.addLayout(form)

        profile_right.addStretch()
        profile_layout.addLayout(profile_right, 1)

        layout_profiles.addWidget(profile_group)
        layout_profiles.addStretch()

        page_profiles_scroll.setWidget(page_profiles_content)
        pp_layout = QVBoxLayout(page_profiles)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.addWidget(page_profiles_scroll)

        self._macro_sub_stack.addWidget(page_profiles)

        # ── SUB-PAGE 3: MOUSE TESTER (Placeholder Panel) ─────────
        page_mousetester = QWidget()
        page_mousetester.setObjectName("HelxairoMouseTesterPanel")
        page_mousetester_scroll = SmoothScrollArea()
        page_mousetester_scroll.setWidgetResizable(True)
        page_mousetester_scroll.setStyleSheet(_scroll_style)
        
        page_mousetester_content = QWidget()
        page_mousetester_content.setStyleSheet("background: transparent;")
        mt_layout = QVBoxLayout(page_mousetester_content)
        mt_layout.setContentsMargins(15, 15, 15, 15)
        mt_layout.setSpacing(15)

        # Header Group Box
        mt_group = QGroupBox("Benchmark Lab")
        mt_group.setObjectName("HelxairoMouseTesterGroup")
        mt_group.setStyleSheet(_grp_style)
        mt_group_layout = QVBoxLayout(mt_group)
        mt_group_layout.setContentsMargins(16, 20, 16, 16)
        mt_group_layout.setSpacing(12)

        mt_desc = QLabel("Comprehensive Mouse Performance & CPS Diagnostics Suite")
        mt_desc.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        mt_group_layout.addWidget(mt_desc)

        # Grid of Placeholder Feature Cards
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(15)

        # Card 1: CPS Benchmark
        card_cps = QFrame()
        card_cps.setObjectName("HelxairoCpsTestCard")
        card_cps.setStyleSheet("""
            QFrame#HelxairoCpsTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#HelxairoCpsTestCard:hover {
                background-color: rgba(255, 91, 6, 0.05);
            }
        """)
        cps_layout = QVBoxLayout(card_cps)
        cps_title = QLabel("CPS Benchmark")
        cps_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        cps_sub = QLabel("Real-time Click Per Second (CPS) Speed Test & High-Precision Counter")
        cps_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        cps_sub.setWordWrap(True)
        cps_layout.addWidget(cps_title)
        cps_layout.addWidget(cps_sub)
        cps_layout.addStretch()

        # Card 2: Mouse Button & Double Click Test
        card_btn = QFrame()
        card_btn.setObjectName("HelxairoButtonTestCard")
        card_btn.setStyleSheet("""
            QFrame#HelxairoButtonTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#HelxairoButtonTestCard:hover {
                background-color: rgba(255, 91, 6, 0.05);
            }
        """)
        btn_layout = QVBoxLayout(card_btn)
        btn_title = QLabel("Button & Double-Click Test")
        btn_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        btn_sub = QLabel("Interactive mouse button tester, debouncing & chatter detection")
        btn_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        btn_sub.setWordWrap(True)
        btn_layout.addWidget(btn_title)
        btn_layout.addWidget(btn_sub)
        btn_layout.addStretch()

        # Card 3: Scroll & Wheel Test
        card_scroll = QFrame()
        card_scroll.setObjectName("HelxairoScrollTestCard")
        card_scroll.setStyleSheet("""
            QFrame#HelxairoScrollTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#HelxairoScrollTestCard:hover {
                background-color: rgba(255, 91, 6, 0.05);
            }
        """)
        scroll_layout = QVBoxLayout(card_scroll)
        scroll_title = QLabel("Scroll Wheel Test")
        scroll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        scroll_sub = QLabel("Scroll direction, delta smoothness & wheel step counter")
        scroll_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        scroll_sub.setWordWrap(True)
        scroll_layout.addWidget(scroll_title)
        scroll_layout.addWidget(scroll_sub)
        scroll_layout.addStretch()

        # Card 4: Polling Rate & Latency
        card_poll = QFrame()
        card_poll.setObjectName("HelxairoPollingTestCard")
        card_poll.setStyleSheet("""
            QFrame#HelxairoPollingTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#HelxairoPollingTestCard:hover {
                background-color: rgba(255, 91, 6, 0.05);
            }
        """)
        poll_layout = QVBoxLayout(card_poll)
        poll_title = QLabel("Polling Rate & Latency")
        poll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        poll_sub = QLabel("Hz frequency report, motion smoothness & click latency estimation")
        poll_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        poll_sub.setWordWrap(True)
        poll_layout.addWidget(poll_title)
        poll_layout.addWidget(poll_sub)
        poll_layout.addStretch()

        grid_layout.addWidget(card_cps, 0, 0)
        grid_layout.addWidget(card_btn, 0, 1)
        grid_layout.addWidget(card_scroll, 1, 0)
        grid_layout.addWidget(card_poll, 1, 1)

        mt_group_layout.addWidget(grid_container)
        mt_layout.addWidget(mt_group)
        mt_layout.addStretch()

        page_mousetester_scroll.setWidget(page_mousetester_content)
        pmt_layout = QVBoxLayout(page_mousetester)
        pmt_layout.setContentsMargins(0, 0, 0, 0)
        pmt_layout.addWidget(page_mousetester_scroll)

        macro_tab_layout.addWidget(self._macro_sub_stack, 1)
        self._switch_macro_subtab(0)  # Default to Quick Actions (Page 0)

        self._page_stack.addWidget(macro_tab)

        # === BENCHMARK TAB (Main Top Tab Page 3) ===
        benchmark_tab = QWidget()
        benchmark_tab.setObjectName("BenchmarkTab")
        benchmark_layout = QVBoxLayout(benchmark_tab)
        benchmark_layout.setContentsMargins(0, 0, 0, 0)

        self._benchmark_stack = QStackedWidget()
        self._benchmark_stack.setObjectName("BenchmarkStack")

        # ── SUB-PAGE 0: BENCHMARK HUB GRID (4 Cards Selector) ──
        hub_scroll = SmoothScrollArea()
        hub_scroll.setWidgetResizable(True)
        hub_scroll.setStyleSheet(_scroll_style)
        
        hub_content = QWidget()
        hub_content.setStyleSheet("background: transparent;")
        hub_layout = QVBoxLayout(hub_content)
        hub_layout.setContentsMargins(20, 20, 20, 20)
        hub_layout.setSpacing(15)

        # Benchmark Lab Group Box
        hub_group = QGroupBox("Benchmark Lab")
        hub_group.setObjectName("MouseTesterGroup")
        hub_group.setStyleSheet(_grp_style)
        hub_group_layout = QVBoxLayout(hub_group)
        hub_group_layout.setContentsMargins(16, 20, 16, 16)
        hub_group_layout.setSpacing(12)

        hub_desc = QLabel("Comprehensive Mouse Performance & CPS Diagnostics Suite")
        hub_desc.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        hub_group_layout.addWidget(hub_desc)

        # 2x2 Grid of Feature Cards
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(15)

        # Card 1: CPS Benchmark (Clickable -> Opens CPS Page)
        card_cps = QFrame()
        card_cps.setObjectName("CpsBenchmarkCard")
        card_cps.setCursor(Qt.PointingHandCursor)
        card_cps.setStyleSheet("""
            QFrame#CpsBenchmarkCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#CpsBenchmarkCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)
        cps_card_layout = QVBoxLayout(card_cps)
        cps_card_title = QLabel("CPS Benchmark")
        cps_card_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        cps_card_sub = QLabel("Real-time Click Per Second (CPS) Speed Test & High-Precision Counter")
        cps_card_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        cps_card_sub.setWordWrap(True)
        cps_card_layout.addWidget(cps_card_title)
        cps_card_layout.addWidget(cps_card_sub)
        cps_card_layout.addStretch()
        
        # Connect click event on CPS card to switch to Page 1!
        card_cps.mousePressEvent = lambda e: self._benchmark_stack.setCurrentIndex(1)

        # Card 2: Mouse Button & Double Click Test
        card_btn = QFrame()
        card_btn.setObjectName("ButtonTestCard")
        card_btn.setCursor(Qt.PointingHandCursor)
        card_btn.setStyleSheet("""
            QFrame#ButtonTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#ButtonTestCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)
        btn_layout = QVBoxLayout(card_btn)
        btn_title = QLabel("Button & Double-Click Test")
        btn_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        btn_sub = QLabel("Interactive mouse button tester, debouncing & chatter detection")
        btn_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        btn_sub.setWordWrap(True)
        btn_layout.addWidget(btn_title)
        btn_layout.addWidget(btn_sub)
        btn_layout.addStretch()

        # Connect click event on Button & Double Click test card to switch to Page 2!
        card_btn.mousePressEvent = lambda e: self._benchmark_stack.setCurrentIndex(2)

        # Card 3: Scroll & Wheel Test
        card_scroll = QFrame()
        card_scroll.setObjectName("ScrollTestCard")
        card_scroll.setCursor(Qt.PointingHandCursor)
        card_scroll.setStyleSheet("""
            QFrame#ScrollTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#ScrollTestCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)
        
        # Connect click event on Scroll & Wheel test card to switch to Page 3!
        card_scroll.mousePressEvent = lambda e: self._benchmark_stack.setCurrentIndex(3)
        scroll_layout = QVBoxLayout(card_scroll)
        scroll_title = QLabel("Scroll Wheel Test")
        scroll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        scroll_sub = QLabel("Scroll direction, delta smoothness & wheel step counter")
        scroll_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        scroll_sub.setWordWrap(True)
        scroll_layout.addWidget(scroll_title)
        scroll_layout.addWidget(scroll_sub)
        scroll_layout.addStretch()

        # Card 4: Polling Rate & Latency
        card_poll = QFrame()
        card_poll.setObjectName("PollingTestCard")
        card_poll.setCursor(Qt.PointingHandCursor)
        card_poll.setStyleSheet("""
            QFrame#PollingTestCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#PollingTestCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)
        poll_layout = QVBoxLayout(card_poll)
        poll_title = QLabel("Polling Rate & Latency")
        poll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        poll_sub = QLabel("Hz frequency report, motion smoothness & click latency estimation")
        poll_sub.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        poll_sub.setWordWrap(True)
        poll_layout.addWidget(poll_title)
        poll_layout.addWidget(poll_sub)
        poll_layout.addStretch()

        grid_layout.addWidget(card_cps, 0, 0)
        grid_layout.addWidget(card_btn, 0, 1)
        grid_layout.addWidget(card_scroll, 1, 0)
        grid_layout.addWidget(card_poll, 1, 1)

        hub_group_layout.addWidget(grid_container)
        hub_layout.addWidget(hub_group)
        hub_layout.addStretch()

        hub_scroll.setWidget(hub_content)
        self._benchmark_stack.addWidget(hub_scroll)  # Index 0: Hub Grid

        # ── SUB-PAGE 1: DEDICATED CPS BENCHMARK PAGE ──────────
        cps_page = QWidget()
        cps_page_layout = QVBoxLayout(cps_page)
        cps_page_layout.setContentsMargins(12, 10, 12, 10)
        cps_page_layout.setSpacing(8)

        # Active CPS Panel Suite (Back button integrated in header frame)
        self.cps_benchmark_panel = CpsBenchmarkPanel()
        self.cps_benchmark_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        cps_page_layout.addWidget(self.cps_benchmark_panel, 1)

        self._benchmark_stack.addWidget(cps_page)  # Index 1: CPS Benchmark Suite

        # ── SUB-PAGE 2: DEDICATED DOUBLE CLICK & CHATTER TEST PAGE ──────────
        dc_page = QWidget()
        dc_page_layout = QVBoxLayout(dc_page)
        dc_page_layout.setContentsMargins(12, 10, 12, 10)
        dc_page_layout.setSpacing(8)

        self.double_click_panel = DoubleClickTestPanel()
        self.double_click_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        dc_page_layout.addWidget(self.double_click_panel, 1)

        self._benchmark_stack.addWidget(dc_page)  # Index 2: Double Click & Chatter Test Suite

        # ── SUB-PAGE 3: DEDICATED SCROLL WHEEL TEST PAGE ──────────
        scroll_page = QWidget()
        scroll_page_layout = QVBoxLayout(scroll_page)
        scroll_page_layout.setContentsMargins(12, 10, 12, 10)
        scroll_page_layout.setSpacing(8)

        self.scroll_wheel_panel = ScrollWheelTestPanel()
        self.scroll_wheel_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        scroll_page_layout.addWidget(self.scroll_wheel_panel, 1)

        self._benchmark_stack.addWidget(scroll_page)  # Index 3: Scroll Wheel Test Suite

        benchmark_layout.addWidget(self._benchmark_stack)
        self._page_stack.addWidget(benchmark_tab)
        
        # === SETTINGS TAB ===
        settings_scroll = SmoothScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setStyleSheet(_scroll_style)
        settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        settings_content = QWidget()
        settings_content.setStyleSheet("background: transparent;")
        
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(15)
        
        settings_header = QLabel("Settings")
        settings_header.setFont(QFont("Orbitron", 16, QFont.Bold))
        settings_header.setStyleSheet("color: #FF5B06;")
        settings_layout.addWidget(settings_header)
        
        # Indicator Drag Mode checkbox (KEPT per user request)
        self._drag_mode_checkbox = AnimatedCheckBox("Enable indicator drag mode (reposition button numbers on mouse image)")
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
        settings_combo_style = _combo_style
        
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
        
        # Device warning overlay for Advanced section
        self._advanced_device_warning = DeviceWarningOverlay(advanced_group)
        advanced_layout.addWidget(self._advanced_device_warning)
        self._advanced_device_warning.raise_()
        self._advanced_device_warning.show()
        
        # Long Distance Mode checkbox
        self._long_distance_check = AnimatedCheckBox("Long Distance Mode")
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
        pair_outer_layout = QVBoxLayout(pair_group)
        pair_outer_layout.setSpacing(10)
        
        # Device warning overlay for Wireless Pairing section
        self._pairing_device_warning = DeviceWarningOverlay(pair_group)
        pair_outer_layout.addWidget(self._pairing_device_warning)
        
        pair_layout = QHBoxLayout()
        pair_outer_layout.addLayout(pair_layout)
        
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
        
        # Load and apply saved HELXAIRO settings
        self._apply_saved_helxairo_settings()

    def _switch_tab(self, index: int):
        """Switch to specified tab."""
        self._current_tab = index
        self._page_stack.setCurrentIndex(index)
        self._update_tab_buttons()

    def _switch_macro_subtab(self, index: int):
        """Switch between sub-tabs in the Macro tab."""
        self._current_macro_subtab = index
        self._macro_sub_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._macro_sub_buttons):
            btn.setChecked(i == index)
    
    def _update_tab_buttons(self):
        """Update tab button styles based on current selection (HELXTATS style)."""
        for i, btn in enumerate(self._tab_buttons):
            if i == self._current_tab:
                # Active tab: gradient top border (orange -> pink -> purple) with rounded corners
                btn.setStyleSheet("""
                    QPushButton {
                        background: #2a2a2a;
                        color: #ffffff;
                        border: none;
                        border-top: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #cc47aa, stop:0.5 #ff0919, stop:1 #e89805);
                        border-top-left-radius: 6px;
                        border-top-right-radius: 6px;
                        border-bottom-left-radius: 0px;
                        border-bottom-right-radius: 0px;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        font-weight: bold;
                        padding-top: 0px;
                        padding-bottom: 3px;
                        padding-left: 14px;
                        padding-right: 14px;
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
                        font-family: 'Orbitron', sans-serif;
                        font-size: 13px;
                        padding-top: 0px;
                        padding-bottom: 3px;
                        padding-left: 14px;
                        padding-right: 14px;
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
        if show_custom_question_box(
            self, "Restore Defaults",
            "Are you sure you want to restore all settings to defaults?"
        ):
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
        value_label.setFont(QFont("Orbitron", 24, QFont.Bold))
        value_label.setStyleSheet("color: #FF5B06;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Orbitron", 10))
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
            
        # Defer macro system bridge init & data loading by 1s for zero-latency page switch
        def _deferred_macro_init():
            if not self._bridge:
                self._init_bridge()
                
            if self._bridge and not self._bridge.is_running:
                try:
                    self._bridge.start()
                    print("[HELXAIRO] Macro system started (deferred)")
                except Exception as e:
                    print(f"[HELXAIRO] Failed to start macro bridge in showEvent: {e}")
                    
            self._load_data()

        QTimer.singleShot(1000, _deferred_macro_init)
    
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
            widget = self.active_list.itemWidget(item)
            macro = item.data(Qt.UserRole + 1)
            if macro and isinstance(widget, HelxairoMacroItemWidget):
                prof = self._bridge.profile_manager.get_profile_for_macro(macro.id)
                prof_name = prof.name if prof else None
                widget.macro = macro
                widget.profile_name = prof_name
                is_enabled = getattr(macro, 'enabled', True)
                widget.status_icon.set_enabled_state(is_enabled)
                if hasattr(widget, 'sub_lbl') and prof_name:
                    widget.sub_lbl.setText(f"Profile: {prof_name}")
        
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
            
    def _format_macro_item_label(self, macro, profile_name=None) -> str:
        """Generate a detailed, readable label for a macro item."""
        # 1. Trigger / Hotkey
        trigger_str = ""
        trigger = getattr(macro, 'trigger', None)
        if trigger:
            if getattr(trigger, 'button', None):
                trigger_str = f"[{trigger.button.upper()}]"
            elif getattr(trigger, 'key', None):
                trigger_str = f"[{trigger.key.upper()}]"
        if not trigger_str:
            trigger_str = "[No Hotkey]"
            
        # 2. Mode
        is_toggle = getattr(macro, 'is_toggle', False)
        mode_str = "Toggle" if is_toggle else "Press"
        
        # 3. Details (Interval, Action, Steps)
        details = []
        
        # Interval
        interval_ms = getattr(macro, 'repeat_interval_ms', None)
        if interval_ms is None and hasattr(macro, 'interval_ms'):
            interval_ms = getattr(macro, 'interval_ms', None)
            
        if interval_ms is not None and interval_ms > 0:
            if interval_ms >= 1000 and interval_ms % 1000 == 0:
                details.append(f"Interval: {interval_ms // 1000}s")
            else:
                details.append(f"Interval: {interval_ms}ms")
                
        # Hold / Action
        hold_b = getattr(macro, 'hold_button', None)
        hold_k = getattr(macro, 'hold_key', None)
        if hold_b:
            details.append(f"Action: {hold_b.capitalize()} Click")
        elif hold_k:
            details.append(f"Action: Key '{hold_k.upper()}'")
            
        # Sequence / Steps
        actions = getattr(macro, 'actions', None) or getattr(macro, 'sequence', None)
        if actions and isinstance(actions, list):
            details.append(f"{len(actions)} steps")
            
        details_str = f"  |  {', '.join(details)}" if details else ""
        name = getattr(macro, 'name', 'Unnamed Macro')
        
        # Strip leading status symbols if present in macro name
        for sym in ("✓", "○", "✔"):
            if name.startswith(sym):
                name = name[len(sym):].strip()
        
        prof_str = f"  |  Profile: {profile_name}" if profile_name else ""
        return f"{name}{prof_str}  |  Hotkey: {trigger_str}{details_str}"

    def _load_macros(self):
        """Load macros belonging to the active profile into the macro lists."""
        print("[MacroPanel] Loading macros for active profile into list...")
        self.active_list.clear()
        
        if not self._bridge or not self._bridge.profile_manager:
            print("[MacroPanel] Error: Bridge or profile manager not available")
            return
            
        active_prof = self._bridge.profile_manager.active_profile
        if not active_prof:
            profiles = self._bridge.profile_manager.get_all_profiles()
            active_prof = profiles[0] if profiles else None
            
        if hasattr(self, 'ac_apps_input'):
            self.ac_apps_input.blockSignals(True)
            self.ac_apps_input.setText(", ".join(active_prof.bound_apps))
            self.ac_apps_input.blockSignals(False)

        macros = self._bridge.profile_manager.get_macros_for_profile(active_prof.id)
        print(f"[MacroPanel] Active Profile '{active_prof.name}' (id={active_prof.id}) has {len(macros)} macro(s)")
        
        for macro in macros:
            try:
                # Add item to active_list (Macro list)
                item = QListWidgetItem()
                widget = HelxairoMacroItemWidget(macro, active_prof.name, item, self.active_list, parent=self.active_list)
                item.setData(Qt.UserRole, macro.id)
                item.setData(Qt.UserRole + 1, macro)
                item.setSizeHint(widget.sizeHint())
                self.active_list.addItem(item)
                self.active_list.setItemWidget(item, widget)
            except Exception as e:
                print(f"[MacroPanel] Error adding macro item: {e}")
                
        if self._bridge and hasattr(self._bridge, 'reload_active_profile_macros'):
            self._bridge.reload_active_profile_macros()
            
        self._filter_macro_list()
        
        # Ensure clean unselected state when sub-tab or profile is loaded
        self.active_list.clearSelection()
        self._on_macro_selection_changed()
        QTimer.singleShot(60, self._recalculate_all_item_sizes)

    def _recalculate_all_item_sizes(self):
        """Recalculate item sizes for active_list after initial panel render."""
        if not hasattr(self, 'active_list') or not self.active_list:
            return
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            if item:
                w = self.active_list.itemWidget(item)
                if w and hasattr(w, '_adjust_edit_height'):
                    w._adjust_edit_height()
        self.active_list.doItemsLayout()

    def _on_macro_selection_changed(self):
        """Update selected visual state across all HelxairoMacroItemWidget items and populate List of keys."""
        if not hasattr(self, 'active_list') or not self.active_list:
            return
            
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            if item:
                widget = self.active_list.itemWidget(item)
                if widget and hasattr(widget, 'set_selected_state'):
                    widget.set_selected_state(item.isSelected())

        if getattr(self.active_list, '_rubber_band_active', False):
            if not hasattr(self, '_keys_list_update_timer'):
                self._keys_list_update_timer = QTimer(self)
                self._keys_list_update_timer.setSingleShot(True)
                self._keys_list_update_timer.setInterval(40)
                self._keys_list_update_timer.timeout.connect(self._flush_keys_list_update)
            self._keys_list_update_timer.start(40)
        else:
            if hasattr(self, '_keys_list_update_timer') and self._keys_list_update_timer.isActive():
                self._keys_list_update_timer.stop()
            self._flush_keys_list_update()

    def _flush_keys_list_update(self):
        if not hasattr(self, 'active_list') or not self.active_list:
            return
        selected_items = self.active_list.selectedItems()
        if not selected_items:
            if hasattr(self, 'editor_keys_list'):
                self.editor_keys_list.clear()
        elif len(selected_items) == 1:
            item = selected_items[0]
            macro = item.data(Qt.UserRole + 1)
            self._update_keys_list_for_macro(macro)
        else:
            macros = [item.data(Qt.UserRole + 1) for item in selected_items if item.data(Qt.UserRole + 1)]
            self._update_keys_list_for_multiple_macros(macros)

    def _update_keys_list_for_multiple_macros(self, macros):
        """Populate List of keys (self.editor_keys_list) with unified macro container cards per selected macro."""
        if not hasattr(self, 'editor_keys_list'):
            return
        self.editor_keys_list.clear()
        if not macros:
            return

        for macro in macros:
            macro_name = getattr(macro, 'name', 'Unnamed Macro')
            actions = getattr(macro, 'actions', None) or getattr(macro, 'sequence', None)
            steps_info = []

            if actions and isinstance(actions, list) and len(actions) > 0:
                for idx, act in enumerate(actions):
                    if isinstance(act, dict):
                        action_type = act.get('type', act.get('action', 'Key Event'))
                        b = act.get('button')
                        k = act.get('key', act.get('code', ''))
                        delay_ms = act.get('delay', act.get('delay_ms', act.get('interval', 0)))
                    else:
                        action_type = str(getattr(act, 'type', getattr(act, 'action_type', 'Key Event')))
                        b = getattr(act, 'button', None)
                        k = getattr(act, 'key', None)
                        delay_ms = getattr(act, 'delay', getattr(act, 'delay_ms', getattr(act, 'interval', 0)))

                    if b:
                        key_name = f"{str(b).capitalize()} Click"
                    elif k:
                        key_name = f"Key '{str(k).upper()}'"
                    elif action_type:
                        key_name = str(action_type).replace("_", " ").capitalize()
                    else:
                        key_name = "Key Action"

                    delay_str = f"{delay_ms}ms" if delay_ms < 1000 else f"{delay_ms / 1000:.1f}s"
                    steps_info.append((key_name, delay_str))
            else:
                target_name, int_str = self._get_single_action_info(macro)
                steps_info.append((target_name, int_str))

            step_count = len(steps_info)
            item = QListWidgetItem()
            widget = HelxairoMacroGroupCardWidget(macro_name, step_count, steps_info, list_item=item, list_widget=self.editor_keys_list)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, (macro, 0))
            self.editor_keys_list.addItem(item)
            self.editor_keys_list.setItemWidget(item, widget)

    def _get_single_action_info(self, macro):
        """Helper to extract single action target name and interval string."""
        hold_b = getattr(macro, 'hold_button', None)
        hold_k = getattr(macro, 'hold_key', None)
        repeat_act = getattr(macro, 'repeat_action', None) or getattr(macro, 'on_action', None)
        
        target_name = ""
        if hold_b:
            target_name = f"{str(hold_b).capitalize()} Click"
        elif hold_k:
            target_name = f"Key '{str(hold_k).upper()}'"
        elif repeat_act:
            if isinstance(repeat_act, dict):
                rb = repeat_act.get('button')
                rk = repeat_act.get('key')
            else:
                rb = getattr(repeat_act, 'button', None)
                rk = getattr(repeat_act, 'key', None)
            
            if rb:
                target_name = f"{str(rb).capitalize()} Click"
            elif rk:
                target_name = f"Key '{str(rk).upper()}'"

        if not target_name:
            to_k = getattr(macro, 'to_key', getattr(macro, 'target_key', None))
            to_b = getattr(macro, 'to_button', getattr(macro, 'target_button', None))
            if to_k:
                target_name = f"Key '{str(to_k).upper()}'"
            elif to_b:
                target_name = f"{str(to_b).capitalize()} Click"
            else:
                target_name = getattr(macro, 'name', 'Macro Action')

        interval_ms = getattr(macro, 'repeat_interval_ms', None)
        if interval_ms is None:
            interval_ms = getattr(macro, 'interval_ms', 100)
            
        int_str = f"{interval_ms // 1000}s" if (interval_ms >= 1000 and interval_ms % 1000 == 0) else f"{interval_ms}ms"
        return target_name, int_str

    def _toggle_accordion_items(self, expanded: bool, items: list):
        """Show or hide child step items for an accordion header."""
        for item in items:
            item.setHidden(not expanded)

    def _update_keys_list_for_macro(self, macro):
        """Populate List of keys (self.editor_keys_list) with unified macro container card."""
        if not hasattr(self, 'editor_keys_list'):
            return
        self.editor_keys_list.clear()
        if not macro:
            return

        macro_name = getattr(macro, 'name', 'Unnamed Macro')
        actions = getattr(macro, 'actions', None) or getattr(macro, 'sequence', None)
        steps_info = []

        if actions and isinstance(actions, list) and len(actions) > 0:
            for idx, act in enumerate(actions):
                if isinstance(act, dict):
                    action_type = act.get('type', act.get('action', 'Key Event'))
                    b = act.get('button')
                    k = act.get('key', act.get('code', ''))
                    delay_ms = act.get('delay', act.get('delay_ms', act.get('interval', 0)))
                else:
                    action_type = str(getattr(act, 'type', getattr(act, 'action_type', 'Key Event')))
                    b = getattr(act, 'button', None)
                    k = getattr(act, 'key', None)
                    delay_ms = getattr(act, 'delay', getattr(act, 'delay_ms', getattr(act, 'interval', 0)))

                if b:
                    key_name = f"{str(b).capitalize()} Click"
                elif k:
                    key_name = f"Key '{str(k).upper()}'"
                elif action_type:
                    key_name = str(action_type).replace("_", " ").capitalize()
                else:
                    key_name = "Key Action"

                delay_str = f"{delay_ms}ms" if delay_ms < 1000 else f"{delay_ms / 1000:.1f}s"
                steps_info.append((key_name, delay_str))
        else:
            target_name, int_str = self._get_single_action_info(macro)
            steps_info.append((target_name, int_str))

        step_count = len(steps_info)
        item = QListWidgetItem()
        widget = HelxairoMacroGroupCardWidget(macro_name, step_count, steps_info, list_item=item, list_widget=self.editor_keys_list)
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.UserRole, (macro, 0))
        self.editor_keys_list.addItem(item)
        self.editor_keys_list.setItemWidget(item, widget)

    def _show_sort_menu(self):
        """Show dropdown QMenu under sort button to re-order items in active_list."""
        if not hasattr(self, 'macro_sort_btn'):
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(24, 26, 32, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 91, 6, 0.2);
                color: #ffffff;
            }
        """)
        
        act_az = menu.addAction("Name (A - Z)")
        act_za = menu.addAction("Name (Z - A)")
        act_active = menu.addAction("Active First")
        act_default = menu.addAction("Default Order")
        
        btn_pos = self.macro_sort_btn.mapToGlobal(QPoint(0, self.macro_sort_btn.height() + 4))
        chosen = menu.exec(btn_pos)
        
        if chosen == act_az:
            self._sort_macro_list("a_z")
        elif chosen == act_za:
            self._sort_macro_list("z_a")
        elif chosen == act_active:
            self._sort_macro_list("active")
        elif chosen == act_default:
            self._sort_macro_list("default")

    def _sort_macro_list(self, criteria="a_z"):
        """Sort items in self.active_list based on chosen criteria safely."""
        if not hasattr(self, 'active_list') or not self._bridge or not self._bridge.profile_manager:
            return
            
        active_prof = self._bridge.profile_manager.active_profile
        if not active_prof:
            profiles = self._bridge.profile_manager.get_all_profiles()
            active_prof = profiles[0] if profiles else None
        if not active_prof:
            return
            
        macros = list(self._bridge.profile_manager.get_macros_for_profile(active_prof.id))
        if not macros:
            return

        def _get_name(m):
            n = getattr(m, 'name', '') or 'Unnamed'
            for sym in ("✓", "○", "✔"):
                if n.startswith(sym):
                    n = n[len(sym):].strip()
            return n.lower()

        if criteria == "a_z":
            macros.sort(key=_get_name)
        elif criteria == "z_a":
            macros.sort(key=_get_name, reverse=True)
        elif criteria == "active":
            macros.sort(key=lambda m: (not getattr(m, 'enabled', True), _get_name(m)))

        self.active_list.blockSignals(True)
        self.active_list.clear()

        for macro in macros:
            try:
                item = QListWidgetItem()
                widget = HelxairoMacroItemWidget(macro, active_prof.name, item, self.active_list, parent=self.active_list)
                item.setData(Qt.UserRole, macro.id)
                item.setData(Qt.UserRole + 1, macro)
                item.setSizeHint(widget.sizeHint())
                self.active_list.addItem(item)
                self.active_list.setItemWidget(item, widget)
            except Exception as e:
                print(f"[Sort] Error populating sorted item: {e}")

        self.active_list.blockSignals(False)
        self._filter_macro_list()

        self.active_list.clearSelection()
        self._on_macro_selection_changed()

    def _filter_macro_list(self, text=None):
        """Filter items in active_list based on search query."""
        if not hasattr(self, 'active_list') or not hasattr(self, 'macro_search_input'):
            return
        query = (text if text is not None else self.macro_search_input.text()).strip().lower()
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            macro = item.data(Qt.UserRole + 1)
            widget = self.active_list.itemWidget(item)
            
            name = ""
            if macro and hasattr(macro, 'name') and macro.name:
                name = macro.name
            elif widget and hasattr(widget, '_macro') and hasattr(widget._macro, 'name'):
                name = widget._macro.name
            elif widget and hasattr(widget, 'name_lbl') and hasattr(widget.name_lbl, 'text'):
                name = widget.name_lbl.text()
            elif item.text():
                name = item.text()
                
            if not query or query in name.lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
                
    def _load_profiles(self):
        """Load profiles into list with SVG star icon for active profile."""
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        star_icon_path = os.path.join(script_dir, "UI Icons", "star-filled.svg").replace("\\", "/")
        star_icon = QIcon(star_icon_path) if os.path.exists(star_icon_path) else None

        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        
        if hasattr(self, 'ac_profile_combo'):
            self.ac_profile_combo.clear()
            
        if not self._bridge or not self._bridge.profile_manager:
            item = QListWidgetItem("Default [Active]")
            item.setData(Qt.UserRole, "default")
            if star_icon:
                item.setIcon(star_icon)
            item.setForeground(QColor("#FF5B06"))
            self.profile_list.addItem(item)
            if hasattr(self, 'ac_profile_combo'):
                self.ac_profile_combo.addItem("Default", "default")
            self.profile_list.blockSignals(False)
            return
            
        active_prof = self._bridge.profile_manager.active_profile
        active_id = active_prof.id if active_prof else "default"
        
        for profile in self._bridge.profile_manager.get_all_profiles():
            is_active = (profile.id == active_id)
            display_text = f"{profile.name} [Active]" if is_active else profile.name
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, profile.id)
            if is_active:
                if star_icon:
                    item.setIcon(star_icon)
                item.setForeground(QColor("#FF5B06"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                
            self.profile_list.addItem(item)
            if hasattr(self, 'ac_profile_combo'):
                self.ac_profile_combo.addItem(profile.name, profile.id)
                
        self.profile_list.blockSignals(False)
            
    def _on_profile_selected(self, current, previous):
        """Handle single-click profile selection to inspect/edit properties."""
        if not current or not self._bridge or not self._bridge.profile_manager:
            return
            
        profile_id = current.data(Qt.UserRole)
        profile = self._bridge.profile_manager.get_profile(profile_id)
        
        if profile:
            self.profile_name.setText(profile.name)
            if hasattr(self, 'profile_apps'):
                self.profile_apps.setText(", ".join(profile.bound_apps))

    def _on_profile_double_clicked(self, item):
        """Handle double-clicking a profile item to LOAD & ACTIVATE it instantly."""
        if not item:
            return
        profile_id = item.data(Qt.UserRole)
        self._load_selected_profile(target_profile_id=profile_id)

    def _load_selected_profile(self, target_profile_id=None):
        """Load and activate the specified or currently selected profile into the engine."""
        if not self._bridge or not self._bridge.profile_manager:
            return
            
        if not target_profile_id:
            current = self.profile_list.currentItem()
            if current:
                target_profile_id = current.data(Qt.UserRole)
                
        if not target_profile_id:
            FloatingToast.show_toast(self, "No Profile Selected", "Please select a profile to load.")
            return
            
        profile = self._bridge.profile_manager.get_profile(target_profile_id)
        if profile:
            self._bridge.profile_manager.activate_profile(target_profile_id)
            if hasattr(self._bridge, 'reload_active_profile_macros'):
                self._bridge.reload_active_profile_macros()
            self._load_profiles()
            self._load_macros()
            self.macros_changed.emit()
            FloatingToast.show_toast(self, "Profile Loaded", f"Activated profile: {profile.name}")
                
    def _on_ac_type_changed(self, text: str):
        """Show/hide custom key input based on dropdown selection."""
        is_custom = (text == "Custom Key")
        self.ac_custom_key.setVisible(is_custom)

    def _on_ac_unit_changed(self, unit: str):
        """Adjust spinbox range and step when switching between ms and s."""
        if unit == "s":
            self.ac_interval.setRange(1, 300)
            self.ac_interval.setSingleStep(1)
            if self.ac_interval.value() > 300:
                self.ac_interval.setValue(1)
        else:
            self.ac_interval.setRange(1, 999)
            self.ac_interval.setSingleStep(5)
            if self.ac_interval.value() < 1 or self.ac_interval.value() > 999:
                self.ac_interval.setValue(500)
    
    def _save_ac_apps(self):
        """Save bound apps entered in Quick Actions to the active profile."""
        if not self._bridge or not self._bridge.profile_manager:
            return
        active_prof = self._bridge.profile_manager.active_profile
        if active_prof and hasattr(self, 'ac_apps_input'):
            apps_text = self.ac_apps_input.text()
            active_prof.bound_apps = [a.strip() for a in apps_text.split(",") if a.strip()]
            self._bridge.profile_manager.save_profile(active_prof)
            self._bridge.profile_manager.save_all()

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
            default_name = f"Auto-press ({custom_key.upper()})"
        else:
            button_map = {"Left Click": "left", "Right Click": "right", "Middle Click": "middle"}
            button = button_map.get(selected, "left")
            default_name = f"Auto-Clicker ({selected})"
            custom_key = ""
        
        interval = self.ac_interval.value()
        if hasattr(self, 'ac_unit') and self.ac_unit.currentText() == "s":
            interval = interval * 1000
        hotkey = self.ac_hotkey.hotkey().lower().strip()
        
        # Custom Macro Name from LineEdit (or default from selected Auto Click Key)
        custom_name = self.ac_name_input.text().strip() if hasattr(self, 'ac_name_input') else ""
        if not custom_name:
            custom_name = default_name
            
        if interval < 40 and not getattr(self, '_ac_warning_ack', False):
            parent_window = self.window()
            
            def on_first_proceed_ac():
                if interval < 5 and not getattr(self, '_ac_extreme_ack', False):
                    def on_second_proceed_ac():
                        self._ac_warning_ack = True
                        self._ac_extreme_ack = True
                        self._do_create_autoclicker(button, interval, hotkey, custom_name, selected, custom_key)
                        self._ac_warning_ack = False
                        self._ac_extreme_ack = False

                    panel2 = HelxairoLowIntervalWarningOverlayPanel(
                        parent_window,
                        on_second_proceed_ac,
                        title="Extreme Risk Warning",
                        description="Intervals below 10ms carry a severe risk of system freezing, CPU overload, or hardware instability. We assume no responsibility for any system damage or issues, as you have been warned twice.\n\nDo you still wish to proceed at your own risk?",
                        proceed_text="Proceed at Own Risk",
                        is_extreme_risk=True
                    )
                    panel2.show()
                    panel2.raise_()
                else:
                    self._ac_warning_ack = True
                    self._do_create_autoclicker(button, interval, hotkey, custom_name, selected, custom_key)
                    self._ac_warning_ack = False

            warn_overlay = HelxairoLowIntervalWarningOverlayPanel(parent_window, on_first_proceed_ac)
            warn_overlay.show()
            warn_overlay.raise_()
            return

        self._ac_warning_ack = False
        self._ac_extreme_ack = False
        self._do_create_autoclicker(button, interval, hotkey, custom_name, selected, custom_key)

    def _do_create_autoclicker(self, button, interval, hotkey, custom_name, selected, custom_key):
        self._save_ac_apps()
        # Target current active profile connected with Profile sub-tab
        active_prof = self._bridge.profile_manager.active_profile if (self._bridge and hasattr(self._bridge, 'profile_manager')) else None
        target_profile_id = active_prof.id if active_prof else "default"
        
        macro_id = self._bridge.create_quick_autoclicker(button, interval, hotkey, profile_id=target_profile_id, name=custom_name)
        
        if selected == "Custom Key":
            FloatingToast.show_toast(self, "Key Auto-Presser Created", f"Key: {custom_key.upper()}  |  Toggle: {hotkey.upper()}")
        else:
            FloatingToast.show_toast(self, "Auto-Clicker Created", f"Toggle with: {hotkey.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _create_remap(self, from_btn=None, to_key=None):
        """Create button remap from quick action."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
            if not self._bridge.is_running:
                self._bridge.start()
            
        if not from_btn:
            if hasattr(self, 'remap_from'):
                from_map = {"X1 (Side)": "x1", "X2 (Side)": "x2", "Middle": "middle"}
                from_btn = from_map.get(self.remap_from.currentText(), "x1")
            else:
                from_btn = "x1"
                
        if not to_key:
            if hasattr(self, 'remap_to'):
                to_key = self.remap_to.text().lower().strip()
            else:
                to_key = "a"
            
        active_prof = self._bridge.profile_manager.active_profile if (self._bridge and hasattr(self._bridge, 'profile_manager')) else None
        target_profile_id = active_prof.id if active_prof else "default"
        
        macro_id = self._bridge.create_quick_remap(from_btn, to_key, profile_id=target_profile_id)
        FloatingToast.show_toast(self, "Remap Created", f"{from_btn.upper()} → {to_key.upper()}")
        
        self._load_macros()
        self.macros_changed.emit()
        
    def _toggle_macro(self, macro):
        """Toggle a specific macro's enabled state."""
        if not macro:
            print("[HELXAIRO-TOGGLE] ERR: _toggle_macro called with None macro!")
            return
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                print("[HELXAIRO-TOGGLE] ERR: _toggle_macro bridge is unavailable!")
                return
                
        old_state = getattr(macro, 'enabled', True)
        new_state = not old_state
        macro.enabled = new_state
        print(f"[HELXAIRO-TOGGLE] _toggle_macro: macro_id={macro.id}, name='{getattr(macro, 'name', '')}', state changed {old_state} -> {new_state}")
        
        if self._bridge.profile_manager:
            self._bridge.profile_manager.save_all()
            print("[HELXAIRO-TOGGLE] Saved profile manager to disk.")
        if hasattr(self._bridge, 'reload_active_profile_macros'):
            self._bridge.reload_active_profile_macros()
            print("[HELXAIRO-TOGGLE] Engine reloaded active profile macros.")
            
        self._refresh_macro_status()
        self.macros_changed.emit()
        status_str = "Enabled" if new_state else "Disabled"
        macro_name = getattr(macro, 'name', 'Macro')
        FloatingToast.show_toast(self, f"Macro {status_str}", f"'{macro_name}' is now {status_str.lower()}.")

    def _toggle_selected_macro(self):
        """Toggle enabled status for all selected macros in active_list."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
                
        selected_items = self.active_list.selectedItems()
        if not selected_items:
            current = self.active_list.currentItem()
            if current:
                selected_items = [current]
                
        if not selected_items:
            FloatingToast.show_toast(self, "No Selection", "Please select macro(s) to toggle.")
            return
            
        toggled_count = 0
        for item in selected_items:
            macro = item.data(Qt.UserRole + 1)
            if macro:
                old_st = getattr(macro, 'enabled', True)
                macro.enabled = not old_st
                print(f"[HELXAIRO-TOGGLE] _toggle_selected_macro: macro_id={macro.id}, {old_st} -> {macro.enabled}")
                toggled_count += 1
                
        if toggled_count > 0:
            if self._bridge.profile_manager:
                self._bridge.profile_manager.save_all()
            if hasattr(self._bridge, 'reload_active_profile_macros'):
                self._bridge.reload_active_profile_macros()
            self._refresh_macro_status()
            self.macros_changed.emit()
            FloatingToast.show_toast(self, "Macros Toggled", f"Toggled {toggled_count} selected macro(s).")
            
    def _disable_all(self):
        """Stop and disable all macros across all profiles."""
        if not self._bridge:
            self._init_bridge()
            
        disabled_count = 0
        if self._bridge and self._bridge.profile_manager:
            for profile in self._bridge.profile_manager.get_all_profiles():
                macros = self._bridge.profile_manager.get_macros_for_profile(profile.id)
                for macro in macros:
                    if macro.enabled:
                        macro.enabled = False
                        disabled_count += 1
            self._bridge.profile_manager.save_all()
            if hasattr(self._bridge, 'reload_active_profile_macros'):
                self._bridge.reload_active_profile_macros()
            
        if self._bridge and self._bridge.engine:
            self._bridge.engine.cancel_all_macros()
            
        self._load_macros()
        self.macros_changed.emit()
        FloatingToast.show_toast(self, "All Macros Stopped", f"Disabled and stopped all active macros ({disabled_count} stopped).")

    def _edit_selected(self):
        """Start inline renaming for selected macro in active_list."""
        selected_items = self.active_list.selectedItems()
        if not selected_items:
            current = self.active_list.currentItem()
            if current:
                selected_items = [current]
                
        if not selected_items:
            FloatingToast.show_toast(self, "No Selection", "Please select a macro to edit.")
            return
            
        for item in selected_items:
            widget = self.active_list.itemWidget(item)
            if widget and hasattr(widget, '_start_inline_rename'):
                widget._start_inline_rename()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        
    def _delete_selected(self):
        """Delete all selected macros in active_list."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge:
                return
                
        selected_items = self.active_list.selectedItems()
        if not selected_items:
            current = self.active_list.currentItem()
            if current:
                selected_items = [current]
                
        if not selected_items:
            FloatingToast.show_toast(self, "No Selection", "Please select macro(s) to delete.")
            return
            
        if show_custom_question_box(
            self, "Delete Selected Macros",
            f"Are you sure you want to delete {len(selected_items)} selected macro(s)?"
        ):
            deleted_count = 0
            for item in selected_items:
                macro_id = item.data(Qt.UserRole)
                if macro_id and self._bridge.profile_manager:
                    self._bridge.profile_manager.remove_macro(macro_id)
                    deleted_count += 1
                    
            if deleted_count > 0:
                if self._bridge.profile_manager:
                    self._bridge.profile_manager.save_all()
                self._load_macros()
                self.macros_changed.emit()
                FloatingToast.show_toast(self, "Macros Deleted", f"Deleted {deleted_count} macro(s).")
            
    def _new_profile(self):
        """Create new profile."""
        from PySide6.QtWidgets import QInputDialog
        
        if not self._bridge:
            self._init_bridge()
            if not self._bridge or not self._bridge.profile_manager:
                return
        
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name and name.strip():
            prof = self._bridge.profile_manager.create_profile(name.strip())
            self._bridge.profile_manager.save_all()
            self._load_profiles()
            FloatingToast.show_toast(self, "Profile Created", f"Created profile '{name.strip()}'.")
            
    def _delete_profile(self):
        """Delete selected profile(s)."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge or not self._bridge.profile_manager:
                return

        selected_items = self.profile_list.selectedItems()
        if not selected_items:
            current = self.profile_list.currentItem()
            if current:
                selected_items = [current]

        if not selected_items:
            FloatingToast.show_toast(self, "No Selection", "Please select profile(s) to delete.")
            return

        valid_items = []
        has_default_in_selection = False

        for item in selected_items:
            pid = item.data(Qt.UserRole)
            prof = self._bridge.profile_manager.get_profile(pid) if pid else None
            is_default = (pid == "default") or (prof and prof.id == "default") or (prof and prof.name.lower() == "default profile")
            
            if is_default:
                has_default_in_selection = True
            else:
                valid_items.append(item)

        # If ONLY default profile is selected, show FloatingToast notification ONLY (no pop-up window)
        if not valid_items:
            if has_default_in_selection:
                FloatingToast.show_toast(self, "Default Profile", "Cannot delete the default profile.")
            return

        # If default profile was selected along with other profiles, notify via toast
        if has_default_in_selection:
            FloatingToast.show_toast(self, "Default Profile", "Cannot delete the default profile.")

        if len(valid_items) == 1:
            p_id = valid_items[0].data(Qt.UserRole)
            prof = self._bridge.profile_manager.get_profile(p_id)
            p_name = prof.name if prof else "this"
            msg = f"Are you sure you want to delete '{p_name}' profile?"
        else:
            msg = f"Are you sure you want to delete {len(valid_items)} selected profiles?"

        if show_custom_question_box(self, "Delete Profile(s)", msg):
            deleted_count = 0
            for item in valid_items:
                profile_id = item.data(Qt.UserRole)
                if profile_id and profile_id != "default":
                    self._bridge.profile_manager.delete_profile(profile_id)
                    deleted_count += 1

            if deleted_count > 0:
                self._bridge.profile_manager.save_all()
                self._load_profiles()
                self.macros_changed.emit()
                FloatingToast.show_toast(self, "Profiles Deleted", f"Deleted {deleted_count} profile(s).")

    def _save_profile(self):
        """Save current profile settings."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge or not self._bridge.profile_manager:
                return

        current = self.profile_list.currentItem()
        profile_id = current.data(Qt.UserRole) if current else None
        
        if not profile_id:
            active_prof = self._bridge.profile_manager.active_profile
            profile_id = active_prof.id if active_prof else "default"
            
        profile = self._bridge.profile_manager.get_profile(profile_id)
        
        if profile:
            new_name = self.profile_name.text().strip()
            if new_name:
                profile.name = new_name
            if hasattr(self, 'profile_apps'):
                profile.bound_apps = [a.strip() for a in self.profile_apps.text().split(",") if a.strip()]
            self._bridge.profile_manager.save_profile(profile)
            self._bridge.profile_manager.save_all()
            self._load_profiles()
            self.macros_changed.emit()
            FloatingToast.show_toast(self, "Profile Saved", f"Saved settings for '{profile.name}'.")
        else:
            FloatingToast.show_toast(self, "Save Failed", "No profile selected to save.")

    def _duplicate_selected_profile(self):
        """Duplicate currently selected profile(s)."""
        if not self._bridge:
            self._init_bridge()
            if not self._bridge or not self._bridge.profile_manager:
                return

        selected_items = self.profile_list.selectedItems()
        if not selected_items:
            current = self.profile_list.currentItem()
            if current:
                selected_items = [current]

        if not selected_items:
            FloatingToast.show_toast(self, "No Selection", "Please select profile(s) to duplicate.")
            return

        dup_count = 0
        import copy
        import uuid

        for item in selected_items:
            profile_id = item.data(Qt.UserRole)
            src_profile = self._bridge.profile_manager.get_profile(profile_id)
            if not src_profile:
                continue

            new_name = f"{src_profile.name} (Copy)"
            new_prof = self._bridge.profile_manager.create_profile(new_name)
            new_prof.bound_apps = list(src_profile.bound_apps)

            # Copy macros from original profile to new profile
            src_macros = self._bridge.profile_manager.get_macros_for_profile(profile_id)
            for m in src_macros:
                cloned_m = copy.deepcopy(m)
                cloned_m.id = str(uuid.uuid4())
                self._bridge.profile_manager.add_macro_to_profile(new_prof.id, cloned_m)

            self._bridge.profile_manager.save_profile(new_prof)
            dup_count += 1

        if dup_count > 0:
            self._bridge.profile_manager.save_all()
            self._load_profiles()
            self.macros_changed.emit()
            FloatingToast.show_toast(self, "Profiles Duplicated", f"Duplicated {dup_count} profile(s).")
            
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
            
        FloatingToast.show_toast(self, "Recording Saved", f"Hotkey: {self._current_recording.playback_hotkey.upper()}")
        
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
            
            # Update device warning overlays
            self._update_device_warnings(is_connected)
            
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
    
    def _update_device_warnings(self, is_connected: bool):
        """
        Update all device warning overlays based on connection state.
        Called periodically from _update_battery_display.
        
        Args:
            is_connected: Whether the Furycube G13 Pro is connected
        """
        try:
            # Update DPI tab warning
            if hasattr(self, '_dpi_device_warning'):
                if is_connected:
                    self._dpi_device_warning.hide()
                else:
                    self._dpi_device_warning.set_disconnected()
                    self._dpi_device_warning.show()
                    print("[HELXAIRO] DPI warning shown (disconnected)")
            
            # Update Advanced settings warning
            if hasattr(self, '_advanced_device_warning'):
                if is_connected:
                    self._advanced_device_warning.hide()
                else:
                    self._advanced_device_warning.set_disconnected()
                    self._advanced_device_warning.show()
            
            # Update Wireless Pairing warning
            if hasattr(self, '_pairing_device_warning'):
                if is_connected:
                    self._pairing_device_warning.hide()
                else:
                    self._pairing_device_warning.set_disconnected()
                    self._pairing_device_warning.show()
                    
        except Exception as e:
            print(f"[MacroSettingsPanel] Device warning update error: {e}")
    
    def _check_device_warnings_initial(self):
        """Initial check of device warnings when panel first loads."""
        try:
            state = self._hw_manager.get_state()
            is_connected = state.get('connected', False)
            print(f"[HELXAIRO] Device warning check: connected={is_connected}")
            self._update_device_warnings(is_connected)
        except Exception as e:
            print(f"[MacroSettingsPanel] Initial device warning check error: {e}")
            # Default to showing warning if we can't check state
            self._update_device_warnings(False)
    
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

