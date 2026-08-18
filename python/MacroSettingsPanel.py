"""
Macro Settings Panel

A panel widget for the sidebar stack to configure macros, profiles, and layers.
"""

from PySide6.QtCore import QRectF
import os
import sys
import time
import collections
import json
import re
import atexit
import ctypes
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QMenu,
    QSpinBox, QCheckBox, QLineEdit, QGroupBox, QFormLayout, QMessageBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QAbstractItemView, QSlider, QColorDialog, QAbstractSpinBox,
    QRadioButton, QFrame, QGraphicsOpacityEffect, QRubberBand, QApplication, QSizePolicy, QAbstractButton
)
from smooth_scroll import SmoothScrollArea
import math, random
from PySide6.QtGui import QIcon, QFont, QKeySequence, QAction, QColor, QCursor, QShortcut, QPixmap, QPainter, QPainterPath, QBrush, QPen, QTextDocument, QTextCursor, QRadialGradient, QLinearGradient
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QPointF, Slot, QMetaObject, QPropertyAnimation, QRect, QEasingCurve, QObject, QEvent, QSize, QVariantAnimation, QAbstractAnimation
from AnimatedButton import AnimatedButton, AnimatedCheckBox, FadeHoverButton


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
        self.title_lbl.setObjectName("HelxairoMacroGroupCardTitle")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-weight: bold; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        header_layout.addWidget(self.title_lbl)

        step_suffix = "step" if step_count == 1 else "steps"
        self.count_lbl = QLabel(f"({step_count} {step_suffix})")
        self.count_lbl.setObjectName("HelxairoMacroGroupCardCount")
        self.count_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        header_layout.addWidget(self.count_lbl)

        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Subtle Horizontal Separator Line
        line = QFrame()
        line.setObjectName("HelxairoMacroGroupCardSeparator")
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); min-height: 1px; max-height: 1px; border: none;")
        main_layout.addWidget(line)

        # 2. Step Rows Container
        for step_idx, (key_name, delay_str) in enumerate(steps_info, start=1):
            step_row = QHBoxLayout()
            step_row.setContentsMargins(4, 2, 4, 2)
            step_row.setSpacing(10)

            step_lbl = QLabel(f"Step {step_idx}")
            step_lbl.setObjectName(f"HelxairoMacroGroupCardStep_{step_idx}")
            step_lbl.setStyleSheet("color: #E0E0E0; font-weight: bold; font-family: 'Orbitron', sans-serif; font-size: 11px;")
            step_row.addWidget(step_lbl)

            key_lbl = QLabel(key_name)
            key_lbl.setObjectName(f"HelxairoMacroGroupCardKey_{step_idx}")
            key_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px;")
            step_row.addWidget(key_lbl)

            step_row.addStretch()

            interval_lbl = QLabel(f"Interval {delay_str}")
            interval_lbl.setObjectName(f"HelxairoMacroGroupCardInterval_{step_idx}")
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
    rubber_band.setObjectName("helxairo_rubberBand")
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
        title_lbl.setObjectName("toastTitleLbl")
        title_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 600; background: transparent; border: none;")
        text_layout.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setObjectName("toastMsgLbl")
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
        icon_lbl.setObjectName("HelxairoWarningIcon")
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setPixmap(QPixmap(warning_icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_lbl.setStyleSheet("background: transparent;")
        
        title_label = QLabel(self.panel_title)
        title_label.setObjectName("HelxairoWarningTitle")
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
        scroll_content.setObjectName("HelxairoWarningScrollContent")
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 4, 16, 4)
        scroll_layout.setSpacing(0)
        
        msg_lbl = QLabel(self.panel_desc)
        msg_lbl.setObjectName("HelxairoWarningMessage")
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
            cancel_btn.setObjectName("HelxairoWarningCancelBtn")
            proceed_btn = FadeHoverButton(self.proceed_text, is_secondary=False, border_radius=8.0, color_mode="red")
            proceed_btn.setObjectName("HelxairoWarningProceedBtn")
        else:
            cancel_btn = FadeHoverButton("Cancel", is_secondary=True, border_radius=8.0)
            cancel_btn.setObjectName("HelxairoWarningCancelBtn")
            proceed_btn = FadeHoverButton(self.proceed_text, is_secondary=False, border_radius=8.0, color_mode="default")
            proceed_btn.setObjectName("HelxairoWarningProceedBtn")
            
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
    Supports optional sequential lighting animation, full stars, and half stars.
    
    Component Name: StarRatingWidget
    """
    def __init__(self, rating=5, max_stars=5, star_size=18, animate=True, star_color="#FFD600", parent=None):
        super().__init__(parent)
        self.setObjectName("StarRatingWidget")
        self.target_rating = float(rating)
        self.max_stars = max_stars
        self.star_size = star_size
        self.star_color = star_color
        self.setFixedSize(max_stars * (star_size + 4), star_size)
        
        if animate:
            self.current_rating = 0.0
            self._timer = QTimer(self)
            self._timer.setInterval(80)
            self._timer.timeout.connect(self._step_star)
        else:
            self.current_rating = float(rating)
            self._timer = None

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_timer') and self._timer:
            self.start_animation()
        else:
            self.current_rating = self.target_rating
            self.update()

    def start_animation(self):
        if hasattr(self, '_timer') and self._timer:
            self.current_rating = 0.0
            self.update()
            if not self._timer.isActive():
                self._timer.start()
        else:
            self.current_rating = self.target_rating
            self.update()

    def _step_star(self):
        if self.current_rating < self.target_rating:
            self.current_rating = min(self.target_rating, self.current_rating + 1.0)
            self.update()
        else:
            if self._timer and self._timer.isActive():
                self._timer.stop()

    def set_rating(self, rating):
        self.target_rating = float(rating)
        self.current_rating = float(rating)
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
            inner_r = outer_r * 0.42
            
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

            # Fill Star based on rating progress
            val = self.current_rating - i
            if val >= 0.95:
                # Fully lit star
                painter.setBrush(QBrush(QColor(self.star_color)))
                painter.setPen(Qt.NoPen)
                painter.drawPath(path)
            elif val >= 0.35:
                # Half-lit star
                # 1. Base dark star
                painter.setBrush(QBrush(QColor("#35353d")))
                painter.setPen(Qt.NoPen)
                painter.drawPath(path)
                
                # 2. Golden left half
                painter.setClipRect(QRectF(0, 0, cx, self.star_size))
                painter.setBrush(QBrush(QColor(self.star_color)))
                painter.drawPath(path)
            else:
                # Dark empty star
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
        self.target_status_lbl.setObjectName("CpsTargetStatusLabel")
        self.target_status_lbl.setFont(QFont("Orbitron", 15, QFont.Bold))
        self.target_status_lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.target_status_lbl.setAlignment(Qt.AlignCenter)
        target_layout.addWidget(self.target_status_lbl)

        self.target_hint_lbl = QLabel("Click manually or toggle your autoclicker inside this box to test CPS")
        self.target_hint_lbl.setObjectName("CpsTargetHintLabel")
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
        val_lbl.setObjectName("CpsMetricCardVal")
        val_lbl.setFont(QFont("Orbitron", 16, QFont.Bold))
        val_lbl.setStyleSheet(f"color: {color_hex}; background: transparent;")
        val_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(val_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("CpsMetricCardTitle")
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
WM_MOUSEMOVE = 0x0200
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

CMPFUNC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

class LowLevelMouseHook(QThread):
    mouse_event_signal = Signal(str, str, int)

    def __init__(self):
        super().__init__()
        self._hook_id = None
        self._user32 = ctypes.windll.user32
        self._pointer = CMPFUNC(self._hook_callback)
        self._thread_id = None
        self.is_running = True
        self.measure_polling_rate = False
        self._polling_timestamps = collections.deque(maxlen=10000)

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0:
            msg = wParam
            
            # Polling Rate Fast Path
            if self.measure_polling_rate and msg == WM_MOUSEMOVE:
                self._polling_timestamps.append(time.perf_counter())
                return self._user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)
                
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
        title_lbl.setObjectName("DoubleClickHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        thresh_lbl = QLabel("Chatter Threshold:")
        thresh_lbl.setObjectName("DoubleClickThreshLabel")
        thresh_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        h_layout.addWidget(thresh_lbl)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setObjectName("DoubleClickThresholdSlider")
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
        self.thresh_val_lbl.setObjectName("DoubleClickThreshValLabel")
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
        stats_frame.setObjectName("DoubleClickStatsFrame")
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
        g_title.setObjectName("GuideCardTitle")
        g_title.setAttribute(Qt.WA_TransparentForMouseEvents)
        g_title.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; background: transparent;")
        
        g_val = QLabel("GUIDE")
        g_val.setObjectName("GuideCardVal")
        g_val.setAttribute(Qt.WA_TransparentForMouseEvents)
        g_val.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; background: transparent;")
        
        g_layout.addWidget(g_title)
        g_layout.addWidget(g_val)
        
        self.btn_guide.clicked.connect(self._show_guide)
        stats_layout.addWidget(self.btn_guide)

        main_layout.addWidget(stats_frame)

        # ── 3. MIDDLE ROW: CLICK ZONE CANVAS & VECTOR MOUSE & GRAPH ──
        mid_widget = QWidget()
        mid_widget.setObjectName("DoubleClickMidRowWidget")
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
        canvas_lbl1.setObjectName("DoubleClickZoneTitle")
        canvas_lbl1.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        canvas_lbl2 = QLabel("Click anywhere inside this area using Left, Right, Middle, or Side Mouse Buttons")
        canvas_lbl2.setObjectName("DoubleClickZoneHint")
        canvas_lbl2.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px;")
        canvas_lbl1.setAlignment(Qt.AlignCenter)
        canvas_lbl2.setAlignment(Qt.AlignCenter)

        canvas_layout.addWidget(canvas_lbl1)
        canvas_layout.addWidget(canvas_lbl2)

        mid_layout.addWidget(self.click_canvas, 2)

        self.mouse_graphic = HelxairoMouseGraphicWidget()
        self.mouse_graphic.setObjectName("DoubleClickMouseGraphic")
        mid_layout.addWidget(self.mouse_graphic, 0)

        main_layout.addWidget(mid_widget, 1)

        # ── 4. OSCILLOSCOPE WAVEFORM GRAPH ───────────────────
        self.pulse_graph = HelxairoPulseGraphWidget()
        self.pulse_graph.setObjectName("DoubleClickPulseGraph")
        main_layout.addWidget(self.pulse_graph)

        # ── 5. EVENT HISTORY TABLE ───────────────────────────
        self.log_table = HelxairoChatterLogTableWidget()
        self.log_table.setObjectName("DoubleClickLogTable")
        self.log_table.setMaximumHeight(140)
        main_layout.addWidget(self.log_table)

    def _create_stat_card(self, title: str, init_val: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setObjectName("DoubleClickStatCard")
        card.setStyleSheet("""
            QFrame#DoubleClickStatCard {
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
        title_lbl.setObjectName("DoubleClickStatTitleLbl")
        title_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; border: none; background: transparent;")
        
        val_lbl = QLabel(init_val)
        val_lbl.setObjectName("StatValLbl")
        val_lbl.setStyleSheet(f"color: {color_hex}; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; border: none; background: transparent;")

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
            self.health_val_lbl.setStyleSheet("color: #00E676; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        elif bounce_pct < 5.0:
            self.health_val_lbl.setText("GOOD (MINOR)")
            self.health_val_lbl.setStyleSheet("color: #FFB74D; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        else:
            self.health_val_lbl.setText("DEFECTIVE!")
            self.health_val_lbl.setStyleSheet("color: #FF3333; font-family: 'Orbitron', sans-serif; font-size: 16px; font-weight: bold; border: none; background: transparent;")

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
        msg.setObjectName("DoubleClickGuideDialog")
        msg.setWindowTitle("How To Use")
        msg.setText(
            "1. Hover your mouse inside the dashed 'CLICK TEST ZONE'.\n"
            "2. Click as fast as you can (or drag click).\n"
            "3. If a physical hardware bounce registers under your set threshold, it will trigger a 'CHATTER FAULT'.\n"
            "4. A low 'SWITCH HEALTH' means your mouse switch might be physically failing and needs replacement."
        )
        msg.setIcon(QMessageBox.Information)
        
        ok_btn = FadeHoverButton("OK", is_secondary=True, border_radius=6.0)
        ok_btn.setObjectName("DoubleClickGuideOkBtn")
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
        title_lbl.setObjectName("ScrollHeaderTitle")
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
        self.up_lbl.setObjectName("ScrollUpValLbl")
        self.down_lbl = self._create_stat_card("SCROLL DOWN", "0", stats_layout)
        self.down_lbl.setObjectName("ScrollDownValLbl")
        self.vel_lbl = self._create_stat_card("CURRENT VELOCITY", "0 lines/s", stats_layout)
        self.vel_lbl.setObjectName("ScrollCurrentVelValLbl")
        self.max_vel_lbl = self._create_stat_card("MAX VELOCITY", "0 lines/s", stats_layout)
        self.max_vel_lbl.setObjectName("ScrollMaxVelValLbl")

        main_layout.addLayout(stats_layout)

        # Log visualizer area
        self.log_area = QTextEdit()
        self.log_area.setObjectName("ScrollLogArea")
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
        card.setObjectName("ScrollStatCard")
        card.setStyleSheet("""
            QFrame#ScrollStatCard {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setAlignment(Qt.AlignCenter)
        
        t_lbl = QLabel(title)
        t_lbl.setObjectName("ScrollStatTitle")
        t_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 10px; border: none; background: transparent;")
        t_lbl.setAlignment(Qt.AlignCenter)
        
        v_lbl = QLabel(init_val)
        v_lbl.setObjectName("ScrollStatVal")
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


class PollingGraph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PollingGraph")
        self.setMinimumHeight(150)
        self._history = collections.deque([0.0]*60, maxlen=60)
        
    def add_value(self, val):
        self._history.append(val)
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        painter.fillRect(rect, QColor(255, 255, 255, 5))
        
        # Grid lines
        pen_grid = QPen(QColor(255, 255, 255, 20))
        pen_grid.setStyle(Qt.DashLine)
        painter.setPen(pen_grid)
        
        h = rect.height()
        w = rect.width()
        
        # Draw 125, 500, 1000 lines approx
        max_val = max(1000, max(self._history) * 1.2)
        
        for y_lbl in [125, 500, 1000, 2000, 4000, 8000]:
            if y_lbl < max_val:
                y_pos = h - (y_lbl / max_val * h)
                painter.drawLine(0, int(y_pos), w, int(y_pos))
                painter.drawText(5, int(y_pos) - 2, f"{y_lbl} Hz")

        if not self._history:
            return
            
        path = QPainterPath()
        step = w / (len(self._history) - 1) if len(self._history) > 1 else w
        
        for i, val in enumerate(self._history):
            x = i * step
            y = h - (val / max_val * h)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
                
        pen_line = QPen(QColor("#FF5B06"))
        pen_line.setWidth(2)
        painter.setPen(pen_line)
        painter.drawPath(path)


class PollingRateTestPanel(QWidget):
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PollingRateTestPanel")
        self._mouse_hook = None
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._update_ui)
        
        self._current_hz = 0.0
        self._peak_hz = 0
        self._avg_hz = 0
        self._last_tick_time = time.perf_counter()
        
        self._setup_ui()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._mouse_hook or not self._mouse_hook.is_running:
            self._mouse_hook = LowLevelMouseHook()
            self._mouse_hook.measure_polling_rate = True
            self._mouse_hook.start()
        else:
            self._mouse_hook._polling_timestamps.clear()
            self._mouse_hook.measure_polling_rate = True
        self._ui_timer.start(16)
        self._last_tick_time = time.perf_counter()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._mouse_hook and self._mouse_hook.is_running:
            self._mouse_hook.measure_polling_rate = False
            self._mouse_hook.stop()
            self._mouse_hook.wait()
            self._mouse_hook = None
        self._ui_timer.stop()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # Header
        header_frame = QFrame()
        header_frame.setObjectName("PollingHeaderFrame")
        header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("PollingBackBtn")
        self.back_btn.setFixedSize(30, 26)
        self.back_btn.setIcon(QIcon(back_icon_path))
        self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Benchmark Lab")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#PollingBackBtn {
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
            QPushButton#PollingBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("POLLING RATE & LATENCY LAB")
        title_lbl.setObjectName("PollingHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        self.reset_btn = FadeHoverButton("Reset", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("PollingResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#PollingResetBtn, FadeHoverButton#PollingResetBtn {
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
        
        # Graph
        self.graph = PollingGraph()
        self.graph.setObjectName("PollingRateGraph")
        main_layout.addWidget(self.graph, 1)

        # Stats Grid
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        self.current_lbl = self._create_stat_card("CURRENT (Hz)", "0", stats_layout)
        self.current_lbl.setObjectName("PollingCurrentValLbl")
        self.peak_lbl = self._create_stat_card("PEAK (Hz)", "0", stats_layout)
        self.peak_lbl.setObjectName("PollingPeakValLbl")
        self.avg_lbl = self._create_stat_card("AVERAGE (Hz)", "0", stats_layout)
        self.avg_lbl.setObjectName("PollingAvgValLbl")
        self.latency_lbl = self._create_stat_card("LATENCY", "0.00 ms", stats_layout)
        self.latency_lbl.setObjectName("PollingLatencyValLbl")

        main_layout.addLayout(stats_layout)

    def _create_stat_card(self, title, val, parent_layout):
        card = QFrame()
        card.setObjectName("PollingStatCard")
        card.setStyleSheet("""
            QFrame#PollingStatCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignCenter)
        
        t_lbl = QLabel(title)
        t_lbl.setObjectName("PollingStatTitle")
        t_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        t_lbl.setAlignment(Qt.AlignCenter)
        
        v_lbl = QLabel(val)
        v_lbl.setObjectName("PollingStatVal")
        v_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: bold; border: none; background: transparent;")
        v_lbl.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(t_lbl)
        layout.addWidget(v_lbl)
        parent_layout.addWidget(card)
        return v_lbl

    def showEvent(self, event):
        super().showEvent(event)
        if not self._mouse_hook or not self._mouse_hook.is_running:
            self._mouse_hook = LowLevelMouseHook()
            self._mouse_hook.measure_polling_rate = True
            self._mouse_hook.start()
        else:
            self._mouse_hook._polling_timestamps.clear()
            self._mouse_hook.measure_polling_rate = True
        self._ui_timer.start(16)
        self._last_tick_time = time.perf_counter()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._mouse_hook and self._mouse_hook.is_running:
            self._mouse_hook.measure_polling_rate = False
            self._mouse_hook.stop()
            self._mouse_hook.wait()
            self._mouse_hook = None
        self._ui_timer.stop()

    def _reset_stats(self):
        self._current_hz = 0.0
        self._peak_hz = 0
        self._avg_hz = 0
        if self._mouse_hook:
            self._mouse_hook._polling_timestamps.clear()
        self._history = collections.deque([0.0]*60, maxlen=60)
        self.graph._history.clear()
        self.graph.update()
        self.current_lbl.setText("0")
        self.peak_lbl.setText("0")
        self.avg_lbl.setText("0")
        self.latency_lbl.setText("0.00 ms")

    def _update_ui(self):
        if not self._mouse_hook:
            return

        now = time.perf_counter()
        window_size = 0.1
        cutoff = now - window_size
        
        # Using a list copy as thread-safe snapshot of deque
        events = list(self._mouse_hook._polling_timestamps)
        recent_count = sum(1 for t in events if t > cutoff)
        
        target_hz = recent_count * (1.0 / window_size)
        
        if len(events) > 2:
            time_span = events[-1] - events[0]
            if time_span > 0:
                self._avg_hz = int(len(events) / time_span)
        
        # Smooth the current Hz
        if target_hz > self._current_hz:
            self._current_hz = target_hz  # Fast Attack
        else:
            self._current_hz += (target_hz - self._current_hz) * 0.1  # Slow Release
        if self._current_hz < 5:
            self._current_hz = 0
            
        current_hz_int = int(self._current_hz)
        
        if current_hz_int > self._peak_hz:
            self._peak_hz = current_hz_int
            
        latency = 0.0
        if current_hz_int > 0:
            latency = 1000.0 / current_hz_int
            
        self.graph.add_value(self._current_hz)
        
        self.current_lbl.setText(str(current_hz_int))
        self.peak_lbl.setText(str(self._peak_hz))
        self.avg_lbl.setText(str(self._avg_hz))
        self.latency_lbl.setText(f"{latency:.2f} ms")


# =====================================================================
# REFLEX LAB & AIM ARENA CLASSES
# =====================================================================

class TargetParticle:
    """Vector particle explosion entity for Gridshot targets."""
    def __init__(self, x: float, y: float, color: QColor):
        import random, math
        self.x = x
        self.y = y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2.5, 7.5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.radius = random.uniform(2.0, 5.5)
        self.alpha = 255
        self.color = color

    def update(self) -> bool:
        self.x += self.vx
        self.y += self.vy
        self.alpha = max(0, self.alpha - 14)
        self.radius = max(0.4, self.radius - 0.12)
        return self.alpha > 0

    def paint(self, painter: QPainter):
        c = QColor(self.color)
        c.setAlpha(int(self.alpha))
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(self.x, self.y), self.radius, self.radius)


class ReflexResultOverlay(QWidget):
    """
    Universal floating modal overlay panel displaying Reflex Benchmark results.
    Includes rank evaluation, vector stars, structured vertical KPI stat cards, and retry/hub actions.
    
    Component Name: ReflexResultOverlay
    """
    def __init__(self, parent_panel, title="BENCHMARK RESULT", rank_badge="GODLIKE", star_rating=5, rank_color="#00FF88", metrics=None, on_retry=None, on_hub=None):
        super().__init__(parent_panel)
        self.parent_panel = parent_panel
        self.on_retry = on_retry
        self.on_hub = on_hub
        self.metrics = metrics or []
        self.rank_badge = rank_badge
        self.star_rating = star_rating
        self.rank_color = rank_color
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("ReflexResultOverlay")
        self.setGeometry(0, 0, parent_panel.width(), parent_panel.height())
        self._setup_ui(title)

    def _setup_ui(self, title_text):
        self.setStyleSheet("""
            QWidget#ReflexResultOverlay {
                background-color: rgba(0, 0, 0, 0.78);
            }
            QFrame#ReflexResultCard {
                background-color: #18181c;
                border: none;
                border-radius: 12px;
            }
            QWidget#ReflexResultTitleBar {
                background-color: #22222a;
                border: none;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
        """)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        
        self.card = QFrame()
        self.card.setObjectName("ReflexResultCard")
        self.card.setFixedSize(540, 310)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 18)
        card_layout.setSpacing(14)
        
        # 1. Header Title Bar
        title_bar = QWidget()
        title_bar.setObjectName("ReflexResultTitleBar")
        title_bar.setFixedHeight(44)
        t_layout = QHBoxLayout(title_bar)
        t_layout.setContentsMargins(18, 0, 18, 0)
        t_label = QLabel(title_text)
        t_label.setObjectName("ReflexResultTitleLabel")
        t_label.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        t_layout.addWidget(t_label)
        t_layout.addStretch()
        card_layout.addWidget(title_bar)
        
        # 2. Main Body Content
        body = QWidget()
        body.setObjectName("ReflexResultBody")
        body.setStyleSheet("background: transparent;")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(20, 4, 20, 4)
        b_layout.setSpacing(14)
        
        # Rank Row (Badge + Vector Stars)
        rank_row = QHBoxLayout()
        rank_row.setSpacing(14)
        rank_lbl = QLabel(self.rank_badge)
        rank_lbl.setObjectName("ReflexResultRankTag")
        rank_lbl.setFont(QFont("Orbitron", 15, QFont.Bold))
        rank_lbl.setStyleSheet(f"color: {self.rank_color}; font-family: 'Orbitron', sans-serif; background: transparent;")
        rank_row.addWidget(rank_lbl)
        
        self.star_widget = StarRatingWidget(rating=self.star_rating, max_stars=5, star_size=16, animate=True, star_color="#FFD600")
        self.star_widget.setObjectName("ReflexResultStarRating")
        rank_row.addWidget(self.star_widget)
        rank_row.addStretch()
        b_layout.addLayout(rank_row)
        
        # Metrics Grid - Vertical 2-Line KPI Stat Boxes
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)
        for label, val in self.metrics:
            box = QFrame()
            box.setObjectName("ReflexStatBox")
            box.setStyleSheet("""
                QFrame#ReflexStatBox {
                    background-color: #24242c;
                    border: none;
                    border-radius: 8px;
                }
            """)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(6, 8, 6, 8)
            box_layout.setSpacing(4)
            
            clean_label = label.rstrip(':').upper()
            lbl_title = QLabel(clean_label)
            lbl_title.setObjectName(f"StatTitle_{clean_label.replace(' ', '_')}")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; background: transparent;")
            box_layout.addWidget(lbl_title)
            
            lbl_val = QLabel(str(val))
            lbl_val.setObjectName(f"StatVal_{clean_label.replace(' ', '_')}")
            lbl_val.setAlignment(Qt.AlignCenter)
            lbl_val.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; background: transparent;")
            box_layout.addWidget(lbl_val)
            
            metrics_row.addWidget(box, 1)
            
        b_layout.addLayout(metrics_row)
        card_layout.addWidget(body)
        
        # 3. Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 0, 20, 0)
        btn_row.setSpacing(14)
        
        btn_retry = FadeHoverButton("Retry Test", is_secondary=False, border_radius=6.0)
        btn_retry.setObjectName("ReflexRetryBtn")
        btn_retry.setFixedHeight(36)
        btn_retry.setStyleSheet("""
            QPushButton#ReflexRetryBtn, FadeHoverButton#ReflexRetryBtn {
                background-color: #FF5B06;
                color: #ffffff;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
            }
        """)
        btn_retry.clicked.connect(self._handle_retry)
        btn_row.addWidget(btn_retry)
        
        btn_hub = FadeHoverButton("Back to Hub", is_secondary=True, border_radius=6.0)
        btn_hub.setObjectName("ReflexBackHubBtn")
        btn_hub.setFixedHeight(36)
        btn_hub.setStyleSheet("""
            QPushButton#ReflexBackHubBtn, FadeHoverButton#ReflexBackHubBtn {
                background-color: #2a2a35;
                color: #E0E0E0;
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
            }
        """)
        btn_hub.clicked.connect(self._handle_hub)
        btn_row.addWidget(btn_hub)
        
        card_layout.addLayout(btn_row)
        
        outer_layout.addStretch()
        h_center = QHBoxLayout()
        h_center.addStretch()
        h_center.addWidget(self.card)
        h_center.addStretch()
        outer_layout.addLayout(h_center)
        outer_layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'star_widget') and self.star_widget:
            self.star_widget.start_animation()

    def _handle_retry(self):
        self.close()
        if self.on_retry:
            self.on_retry()

    def _handle_hub(self):
        self.close()
        if self.on_hub:
            self.on_hub()

    def resizeEvent(self, event):
        if self.parent_panel:
            self.setGeometry(0, 0, self.parent_panel.width(), self.parent_panel.height())
        super().resizeEvent(event)


class ReactionZoneWidget(QWidget):
    """
    Interactive State-Machine Reaction Test Area.
    State 0: IDLE
    State 1: WAITING (Red)
    State 2: TRIGGERED (Green)
    State 3: FALSE_START (Amber/Red warning)
    State 4: RESULT (Round score display)
    
    Component Name: ReactionZoneWidget
    """
    round_finished = Signal(float)  # Latency in ms
    session_finished = Signal(list, float)  # All rounds, average

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReactionZoneWidget")
        self.setCursor(Qt.PointingHandCursor)
        self.state = 0  # 0=IDLE, 1=WAITING, 2=TRIGGERED, 3=FALSE_START, 4=RESULT
        self.rounds = []
        self.current_round_latency = 0.0
        self._start_perf_time = 0.0
        
        self._trigger_timer = QTimer(self)
        self._trigger_timer.setSingleShot(True)
        self._trigger_timer.timeout.connect(self._on_trigger)

    def reset_session(self):
        self._trigger_timer.stop()
        self.state = 0
        self.rounds = []
        self.current_round_latency = 0.0
        self.update()

    def mousePressEvent(self, event):
        import time, random
        if event.button() != Qt.LeftButton:
            return

        if self.state == 0 or self.state == 4 or self.state == 3:
            # Start next round
            if len(self.rounds) >= 5:
                self.rounds = []
            self.state = 1  # WAITING
            self.update()
            delay_ms = random.randint(1500, 4500)
            self._trigger_timer.start(delay_ms)
        elif self.state == 1:
            # False start
            self._trigger_timer.stop()
            self.state = 3  # FALSE_START
            self.update()
        elif self.state == 2:
            # Clicked on green
            latency = (time.perf_counter() - self._start_perf_time) * 1000.0
            self.current_round_latency = latency
            self.rounds.append(latency)
            self.state = 4  # RESULT
            self.update()
            self.round_finished.emit(latency)
            
            if len(self.rounds) >= 5:
                avg = sum(self.rounds) / len(self.rounds)
                self.session_finished.emit(self.rounds, avg)

    def _on_trigger(self):
        import time
        self.state = 2  # TRIGGERED (GREEN)
        self._start_perf_time = time.perf_counter()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Determine background color and text based on state
        if self.state == 0:
            bg_color = QColor("#1e2028")
            title = "CLICK ANYWHERE TO START"
            subtext = "When the screen turns green, click as quickly as you can."
            sub_color = QColor("#a0a0b0")
        elif self.state == 1:
            bg_color = QColor("#661818")
            title = "WAIT FOR GREEN..."
            subtext = "Do not click yet!"
            sub_color = QColor("#ffaaaa")
        elif self.state == 2:
            bg_color = QColor("#00C853")
            title = "CLICK NOW!"
            subtext = "CLICK CLICK CLICK!"
            sub_color = QColor("#ffffff")
        elif self.state == 3:
            bg_color = QColor("#882020")
            title = "TOO EARLY!"
            subtext = "False start detected! Click to try this round again."
            sub_color = QColor("#ffcccc")
        elif self.state == 4:
            bg_color = QColor("#1c2738")
            title = f"{self.current_round_latency:.1f} MS"
            round_idx = len(self.rounds)
            subtext = f"Round {round_idx} of 5 completed. Click to continue."
            sub_color = QColor("#88ccff")

        # Draw smooth rounded card background
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)

        # Draw decorative vector lightning / pulse waves
        painter.setPen(QPen(QColor(255, 255, 255, 20), 2))
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        painter.drawEllipse(QPointF(cx, cy), 140, 140)
        painter.drawEllipse(QPointF(cx, cy), 200, 200)

        # Draw Title
        painter.setFont(QFont("Orbitron", 22, QFont.Bold))
        painter.setPen(QPen(QColor("#ffffff")))
        title_rect = QRect(0, int(cy - 45), self.width(), 45)
        painter.drawText(title_rect, Qt.AlignCenter, title)

        # Draw Subtext
        painter.setFont(QFont("Orbitron", 12))
        painter.setPen(QPen(sub_color))
        sub_rect = QRect(0, int(cy + 15), self.width(), 35)
        painter.drawText(sub_rect, Qt.AlignCenter, subtext)


class ReactionTimePanel(QWidget):
    """
    Reaction Time Test Suite Page.
    
    Component Name: ReactionTimePanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReactionTimePanel")
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("ReactionHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#ReactionHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("ReactionBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Reflex Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#ReactionBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#ReactionBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("REACTION TIME TEST")
        title_lbl.setObjectName("ReactionHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        self.reset_btn = FadeHoverButton("Reset", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("ReactionResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#ReactionResetBtn, FadeHoverButton#ReactionResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self._on_reset)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # ── 2. STATS & ROUNDS ROW ──────────────────────────────
        stats_frame = QFrame()
        stats_frame.setObjectName("ReactionStatsFrame")
        stats_frame.setStyleSheet("""
            QFrame#ReactionStatsFrame {
                background-color: rgba(26, 26, 32, 0.9);
                border: none;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        s_layout = QHBoxLayout(stats_frame)
        s_layout.setContentsMargins(16, 8, 16, 8)
        s_layout.setSpacing(20)

        # Round indicator
        self.round_lbl = QLabel("ROUND: <span style='color:#FF5B06;'>0 / 5</span>")
        self.round_lbl.setObjectName("ReactionRoundLbl")
        self.round_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        s_layout.addWidget(self.round_lbl)

        # Best round
        self.best_lbl = QLabel("BEST: <span style='color:#00FF88;'>--- ms</span>")
        self.best_lbl.setObjectName("ReactionBestLbl")
        self.best_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        s_layout.addWidget(self.best_lbl)

        # Average
        self.avg_lbl = QLabel("AVERAGE: <span style='color:#FFD600;'>--- ms</span>")
        self.avg_lbl.setObjectName("ReactionAvgLbl")
        self.avg_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        s_layout.addWidget(self.avg_lbl)

        s_layout.addStretch()
        main_layout.addWidget(stats_frame)

        # ── 3. INTERACTIVE CLICK ZONE ──────────────────────────
        self.zone = ReactionZoneWidget()
        self.zone.setObjectName("ReactionInteractiveZone")
        self.zone.round_finished.connect(self._on_round_done)
        self.zone.session_finished.connect(self._on_session_done)
        main_layout.addWidget(self.zone, 1)

    def _on_round_done(self, latency):
        rounds = self.zone.rounds
        self.round_lbl.setText(f"ROUND: <span style='color:#FF5B06;'>{len(rounds)} / 5</span>")
        best = min(rounds)
        self.best_lbl.setText(f"BEST: <span style='color:#00FF88;'>{best:.1f} ms</span>")
        avg = sum(rounds) / len(rounds)
        self.avg_lbl.setText(f"AVERAGE: <span style='color:#FFD600;'>{avg:.1f} ms</span>")

    def _on_session_done(self, rounds, avg):
        # Determine Rank
        if avg < 160:
            rank, color, stars = "GODLIKE", "#00FF88", 5
        elif avg < 195:
            rank, color, stars = "ELITE MASTER", "#00E5FF", 4.5
        elif avg < 235:
            rank, color, stars = "DIAMOND PRO", "#7C4DFF", 4
        elif avg < 280:
            rank, color, stars = "PLATINUM", "#FFD600", 3
        else:
            rank, color, stars = "RECRUIT", "#FF5B06", 2

        best = min(rounds)
        metrics = [
            ("Average:", f"{avg:.1f} ms"),
            ("Best Round:", f"{best:.1f} ms"),
            ("Consistency:", f"{max(rounds)-min(rounds):.1f} ms range")
        ]

        overlay = ReflexResultOverlay(
            parent_panel=self,
            title="REACTION BENCHMARK RESULT",
            rank_badge=rank,
            star_rating=stars,
            rank_color=color,
            metrics=metrics,
            on_retry=self._on_reset,
            on_hub=self.back_clicked.emit
        )
        overlay.show()

    def _on_reset(self):
        self.zone.reset_session()
        self.round_lbl.setText("ROUND: <span style='color:#FF5B06;'>0 / 5</span>")
        self.best_lbl.setText("BEST: <span style='color:#00FF88;'>--- ms</span>")
        self.avg_lbl.setText("AVERAGE: <span style='color:#FFD600;'>--- ms</span>")


class GridshotCanvasWidget(QWidget):
    """
    Interactive 2D Canvas for Gridshot Flicking Arena (60 FPS).
    Supports Easy, Medium, Hard, and Extreme difficulty levels.
    
    Component Name: GridshotCanvasWidget
    """
    stats_updated = Signal(dict)  # time_left, score, hits, misses, accuracy, tps
    game_finished = Signal(dict)

    DIFFICULTIES = {
        "easy": {
            "normal_radius": 32.0,
            "shrinking_init_radius": 52.0,
            "shrinking_min_radius": 14.0,
            "lifetime": 3.2,
            "target_count": 3,
            "score_mult": 0.85
        },
        "medium": {
            "normal_radius": 24.0,
            "shrinking_init_radius": 42.0,
            "shrinking_min_radius": 8.0,
            "lifetime": 2.4,
            "target_count": 3,
            "score_mult": 1.0
        },
        "hard": {
            "normal_radius": 17.0,
            "shrinking_init_radius": 34.0,
            "shrinking_min_radius": 6.0,
            "lifetime": 1.7,
            "target_count": 4,
            "score_mult": 1.35
        },
        "extreme": {
            "normal_radius": 12.0,
            "shrinking_init_radius": 32.0,
            "shrinking_min_radius": 5.0,
            "lifetime": 1.4,
            "target_count": 4,
            "score_mult": 1.75
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GridshotCanvasWidget")
        self.setCursor(Qt.CrossCursor)
        self.is_running = False
        self.difficulty = "medium"
        self.time_left = 30.0
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.streak = 0
        self.spawn_count = 0
        self.targets = []
        self.particles = []
        
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(16)
        self._fps_timer.timeout.connect(self._tick)

    def set_difficulty(self, diff_key: str):
        if diff_key in self.DIFFICULTIES:
            self.difficulty = diff_key
            if not self.is_running:
                self.targets = []
                cfg = self.DIFFICULTIES[self.difficulty]
                for _ in range(cfg["target_count"]):
                    self._spawn_target()
                self.update()

    def start_game(self):
        self.is_running = True
        self.time_left = 30.0
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.streak = 0
        self.spawn_count = 0
        self.particles = []
        self.targets = []
        
        cfg = self.DIFFICULTIES.get(self.difficulty, self.DIFFICULTIES["medium"])
        for _ in range(cfg["target_count"]):
            self._spawn_target()

        self._fps_timer.start()

    def stop_game(self):
        self.is_running = False
        self._fps_timer.stop()
        self.update()

    def _spawn_target(self):
        import random, time, math
        self.spawn_count += 1
        w = max(120, self.width())
        h = max(120, self.height())
        padding = 55

        cfg = self.DIFFICULTIES.get(self.difficulty, self.DIFFICULTIES["medium"])
        
        # Difficulty-based shrinking behavior:
        # Easy: 0% shrinking (Murni 100% target normal/statis, tanpa shrinking)
        # Medium: 33% (every 3rd target) shrinks
        # Hard: 50% (every 2nd target) shrinks
        # Extreme: 100% of targets shrink!
        if self.difficulty == "easy":
            is_shrinking = False
        elif self.difficulty == "extreme":
            is_shrinking = True
        elif self.difficulty == "hard":
            is_shrinking = (self.spawn_count % 2 == 0)
        else:  # medium
            is_shrinking = (self.spawn_count % 3 == 0)

        if is_shrinking:
            init_radius = cfg["shrinking_init_radius"]
            min_radius = cfg["shrinking_min_radius"]
            lifetime = cfg["lifetime"]
            target_type = "shrinking"
        else:
            init_radius = cfg["normal_radius"]
            min_radius = cfg["normal_radius"]
            lifetime = 0.0
            target_type = "normal"

        for _ in range(60):
            tx = random.uniform(padding, w - padding)
            ty = random.uniform(padding, h - padding)
            
            overlap = False
            for t in self.targets:
                dist = math.hypot(tx - t['x'], ty - t['y'])
                if dist < (init_radius + t['radius'] + 15):
                    overlap = True
                    break
            if not overlap:
                self.targets.append({
                    'x': tx,
                    'y': ty,
                    'radius': init_radius,
                    'initial_radius': init_radius,
                    'min_radius': min_radius,
                    'target_type': target_type,
                    'spawn_time': time.perf_counter(),
                    'lifetime': lifetime,
                    'shrink_progress': 0.0
                })
                break

    def mousePressEvent(self, event):
        import time, math
        if event.button() != Qt.LeftButton:
            return

        if not self.is_running:
            self.start_game()
            return

        mx = event.position().x()
        my = event.position().y()
        
        hit_idx = -1
        for i, t in enumerate(self.targets):
            dist = math.hypot(mx - t['x'], my - t['y'])
            if dist <= (t['radius'] + 3.0):
                hit_idx = i
                break

        if hit_idx != -1:
            hit_target = self.targets.pop(hit_idx)
            self.hits += 1
            self.streak += 1
            
            # Particle explosion
            particle_count = 16 if hit_target['target_type'] == 'shrinking' else 12
            particle_color = QColor("#FF7A00") if hit_target['target_type'] == 'shrinking' else QColor("#FF5B06")
            for _ in range(particle_count):
                self.particles.append(TargetParticle(hit_target['x'], hit_target['y'], particle_color))
                
            # Score Calculation with Speed, Precision & Difficulty Bonus
            speed_mult = max(1.0, 2.2 - (time.perf_counter() - hit_target['spawn_time']))
            streak_bonus = min(2.5, 1.0 + (self.streak * 0.05))
            cfg = self.DIFFICULTIES.get(self.difficulty, self.DIFFICULTIES["medium"])
            score_diff_mult = cfg["score_mult"]
            
            if hit_target['target_type'] == 'shrinking':
                base_pts = 1200 + int((1.0 - (hit_target['radius'] / hit_target['initial_radius'])) * 800)
            else:
                base_pts = 1000
                
            pts = int(base_pts * speed_mult * streak_bonus * score_diff_mult)
            self.score += pts
            
            self._spawn_target()
        else:
            self.misses += 1
            self.streak = 0
            self.score = max(0, self.score - 150)

        self._emit_stats()
        self.update()

    def _tick(self):
        import time
        self.time_left = max(0.0, self.time_left - 0.016)
        now = time.perf_counter()
        
        # 1. Update shrinking targets & handle expiration
        expired_targets = []
        for t in self.targets:
            if t['target_type'] == 'shrinking' and t['lifetime'] > 0:
                elapsed = now - t['spawn_time']
                progress = min(1.0, elapsed / t['lifetime'])
                t['shrink_progress'] = progress
                t['radius'] = max(t['min_radius'], t['initial_radius'] * (1.0 - progress) + t['min_radius'] * progress)
                
                if elapsed >= t['lifetime']:
                    expired_targets.append(t)

        for exp_t in expired_targets:
            if exp_t in self.targets:
                self.targets.remove(exp_t)
                self.misses += 1
                self.streak = 0
                for _ in range(8):
                    self.particles.append(TargetParticle(exp_t['x'], exp_t['y'], QColor("#777777")))
                self._spawn_target()

        # 2. Update particle physics
        self.particles = [p for p in self.particles if p.update()]
        
        self._emit_stats()
        self.update()

        if self.time_left <= 0.0:
            self.stop_game()
            total_clicks = self.hits + self.misses
            acc = (self.hits / total_clicks * 100.0) if total_clicks > 0 else 0.0
            tps = self.hits / 30.0
            self.game_finished.emit({
                'score': self.score,
                'hits': self.hits,
                'misses': self.misses,
                'accuracy': acc,
                'tps': tps,
                'difficulty': self.difficulty.upper()
            })

    def _emit_stats(self):
        total_clicks = self.hits + self.misses
        acc = (self.hits / total_clicks * 100.0) if total_clicks > 0 else 100.0
        elapsed = 30.0 - self.time_left
        tps = (self.hits / elapsed) if elapsed > 0.5 else 0.0
        self.stats_updated.emit({
            'time_left': self.time_left,
            'score': self.score,
            'hits': self.hits,
            'misses': self.misses,
            'accuracy': acc,
            'tps': tps
        })

    def paintEvent(self, event):
        import time, math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Canvas background
        painter.setBrush(QBrush(QColor("#111116")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)

        # Draw grid pattern
        painter.setPen(QPen(QColor(255, 255, 255, 8), 1))
        step = 40
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)

        if not self.is_running:
            # Start Overlay
            painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
            painter.drawRoundedRect(self.rect(), 12, 12)
            
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            
            painter.setFont(QFont("Orbitron", 20, QFont.Bold))
            painter.setPen(QPen(QColor("#FF5B06")))
            painter.drawText(QRect(0, int(cy - 40), self.width(), 40), Qt.AlignCenter, "CLICK TO START GRIDSHOT")
            
            painter.setFont(QFont("Orbitron", 11))
            painter.setPen(QPen(QColor("#888888")))
            painter.drawText(QRect(0, int(cy + 10), self.width(), 30), Qt.AlignCenter, f"Difficulty: {self.difficulty.upper()} | 30 Seconds Challenge")
            return

        # Draw Targets
        now = time.time()
        pulse = (math.sin(now * 8.0) + 1.0) * 0.5
        
        for t in self.targets:
            tx = t['x']
            ty = t['y']
            r = t['radius']
            is_shrinking = (t['target_type'] == 'shrinking')
            
            if is_shrinking:
                outer_r = r + (pulse * 5.0) + 2.0
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 122, 0, int(150 + pulse * 105)), 2.5))
                painter.drawEllipse(QPointF(tx, ty), outer_r, outer_r)

                grad = QRadialGradient(tx, ty, r)
                grad.setColorAt(0.0, QColor("#FFA726"))
                grad.setColorAt(0.7, QColor("#FF6D00"))
                grad.setColorAt(1.0, QColor("#D50000"))
                painter.setBrush(QBrush(grad))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.drawEllipse(QPointF(tx, ty), r, r)

                dot_r = max(2.5, r * 0.2)
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(tx, ty), dot_r, dot_r)
            else:
                outer_r = r + (pulse * 6.0)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 91, 6, int(120 + pulse * 100)), 2))
                painter.drawEllipse(QPointF(tx, ty), outer_r, outer_r)

                grad = QRadialGradient(tx, ty, r)
                grad.setColorAt(0.0, QColor("#FF8A06"))
                grad.setColorAt(0.8, QColor("#FF5B06"))
                grad.setColorAt(1.0, QColor("#C43800"))
                painter.setBrush(QBrush(grad))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.drawEllipse(QPointF(tx, ty), r, r)

                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(tx, ty), max(2.5, r * 0.2), max(2.5, r * 0.2))

        # Draw Particles
        for p in self.particles:
            p.paint(painter)


GRIDSHOT_DIFFICULTY_RANKS = {
    "easy": [
        (65000, "WARRIOR", "#00FF88", 5),
        (50000, "MARKSMAN", "#00E5FF", 4),
        (35000, "CADET", "#FFD600", 3),
        (20000, "SCOUT", "#FF5B06", 2),
        (0,     "ROOKIE", "#888888", 1),
    ],
    "medium": [
        (80000, "COMMANDER", "#00FF88", 5),
        (60000, "SHARPSHOOTER", "#7C4DFF", 4),
        (42000, "GLADIATOR", "#FFD600", 3),
        (25000, "VANGUARD", "#FF5B06", 2),
        (0,     "SOLDIER", "#888888", 1),
    ],
    "hard": [
        (100000, "GRANDMASTER", "#00FF88", 5),
        (75000,  "APEX HUNTER", "#00E5FF", 4),
        (52000,  "SNIPER PRO", "#FFD600", 3),
        (30000,  "ASSASSIN", "#FF5B06", 2),
        (0,      "VETERAN", "#888888", 1),
    ],
    "extreme": [
        (125000, "GODLIKE", "#00FF88", 5),
        (95000,  "IMMORTAL", "#00E5FF", 4),
        (68000,  "AIM BOT", "#FFD600", 3),
        (40000,  "HYPER TITAN", "#FF5B06", 2),
        (0,      "CYBER REAPER", "#888888", 1),
    ]
}


class GridshotArenaPanel(QWidget):
    """
    Gridshot Aim Arena Page.
    
    Component Name: GridshotArenaPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GridshotArenaPanel")
        self.current_difficulty = "medium"
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("GridshotHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#GridshotHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("GridshotBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Reflex Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#GridshotBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#GridshotBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self._on_back)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("GRIDSHOT FLICK ARENA")
        title_lbl.setObjectName("GridshotHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        # Segmented Difficulty Selector
        diff_container = QWidget()
        diff_container.setObjectName("GridshotDiffContainer")
        diff_container.setFixedHeight(28)
        diff_container.setStyleSheet("""
            QWidget#GridshotDiffContainer {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
            }
        """)
        diff_layout = QHBoxLayout(diff_container)
        diff_layout.setContentsMargins(3, 3, 3, 3)
        diff_layout.setSpacing(3)

        self.diff_buttons = {}
        for diff_key, diff_title in [("easy", "EASY"), ("medium", "MEDIUM"), ("hard", "HARD"), ("extreme", "EXTREME")]:
            btn = QPushButton(diff_title)
            btn.setObjectName(f"GridshotDiffBtn_{diff_key}")
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda ch, k=diff_key: self._set_difficulty(k))
            diff_layout.addWidget(btn)
            self.diff_buttons[diff_key] = btn

        h_layout.addWidget(diff_container)

        self.reset_btn = FadeHoverButton("Restart", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("GridshotResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#GridshotResetBtn, FadeHoverButton#GridshotResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self._on_restart)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # ── 2. LIVE KPI TELEMETRY BAR ──────────────────────────
        kpi_frame = QFrame()
        kpi_frame.setObjectName("GridshotKpiFrame")
        kpi_frame.setStyleSheet("""
            QFrame#GridshotKpiFrame {
                background-color: rgba(26, 26, 32, 0.9);
                border: none;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        k_layout = QHBoxLayout(kpi_frame)
        k_layout.setContentsMargins(16, 6, 16, 6)
        k_layout.setSpacing(20)

        self.time_lbl = QLabel("TIME: <span style='color:#FF5B06;'>30.0s</span>")
        self.time_lbl.setObjectName("GridshotTimeLbl")
        self.time_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.time_lbl)

        self.score_lbl = QLabel("SCORE: <span style='color:#00FF88;'>0</span>")
        self.score_lbl.setObjectName("GridshotScoreLbl")
        self.score_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.score_lbl)

        self.acc_lbl = QLabel("ACCURACY: <span style='color:#FFD600;'>100.0%</span>")
        self.acc_lbl.setObjectName("GridshotAccLbl")
        self.acc_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.acc_lbl)

        self.tps_lbl = QLabel("TPS: <span style='color:#00E5FF;'>0.0</span>")
        self.tps_lbl.setObjectName("GridshotTpsLbl")
        self.tps_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.tps_lbl)

        k_layout.addStretch()
        main_layout.addWidget(kpi_frame)

        # ── 3. 2D AIM CANVAS ──────────────────────────────────
        self.canvas = GridshotCanvasWidget()
        self.canvas.setObjectName("GridshotCanvas")
        self.canvas.stats_updated.connect(self._on_stats)
        self.canvas.game_finished.connect(self._on_game_over)
        main_layout.addWidget(self.canvas, 1)

        self._set_difficulty("medium")

    def _set_difficulty(self, key):
        self.current_difficulty = key
        self.canvas.set_difficulty(key)
        for d_key, btn in self.diff_buttons.items():
            if d_key == key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF5B06;
                        color: #ffffff;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #888888;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        color: #ffffff;
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)

    def _on_stats(self, s):
        self.time_lbl.setText(f"TIME: <span style='color:#FF5B06;'>{s['time_left']:.1f}s</span>")
        self.score_lbl.setText(f"SCORE: <span style='color:#00FF88;'>{s['score']:,}</span>")
        self.acc_lbl.setText(f"ACCURACY: <span style='color:#FFD600;'>{s['accuracy']:.1f}%</span>")
        self.tps_lbl.setText(f"TPS: <span style='color:#00E5FF;'>{s['tps']:.1f}</span>")

    def _on_game_over(self, data):
        score = data['score']
        acc = data['accuracy']
        tps = data['tps']
        diff_key = self.current_difficulty.lower()
        diff_label = diff_key.upper()
        
        ranks_list = GRIDSHOT_DIFFICULTY_RANKS.get(diff_key, GRIDSHOT_DIFFICULTY_RANKS["medium"])
        rank, color, stars = ranks_list[-1][1], ranks_list[-1][2], ranks_list[-1][3]
        for min_s, r_title, r_color, r_stars in ranks_list:
            if score >= min_s:
                rank, color, stars = r_title, r_color, r_stars
                break

        metrics = [
            ("Difficulty:", diff_label),
            ("Final Score:", f"{score:,}"),
            ("Accuracy:", f"{acc:.1f}%"),
            ("Hit Rate:", f"{tps:.1f} TPS")
        ]

        overlay = ReflexResultOverlay(
            parent_panel=self,
            title="GRIDSHOT FLICK EVALUATION",
            rank_badge=rank,
            star_rating=stars,
            rank_color=color,
            metrics=metrics,
            on_retry=self._on_restart,
            on_hub=self._on_back
        )
        overlay.show()

    def _on_restart(self):
        self.canvas.start_game()

    def _on_back(self):
        self.canvas.stop_game()
        self.back_clicked.emit()


class TrackingCanvasWidget(QWidget):
    """
    Interactive 2D Canvas for Precision Tracking Lab (60 FPS).
    Supports Easy, Medium, Hard, Extreme difficulties.
    
    Component Name: TrackingCanvasWidget
    """
    stats_updated = Signal(dict)  # time_left, dwell_time, accuracy, is_on_target
    game_finished = Signal(dict)

    DIFFICULTIES = {
        "easy": {"orb_radius": 38.0, "base_speed": 2.4, "max_speed": 4.0},
        "medium": {"orb_radius": 30.0, "base_speed": 3.5, "max_speed": 5.5},
        "hard": {"orb_radius": 20.0, "base_speed": 5.0, "max_speed": 7.5},
        "extreme": {"orb_radius": 14.0, "base_speed": 6.8, "max_speed": 9.5},
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TrackingCanvasWidget")
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.is_running = False
        self.difficulty = "medium"
        self.time_left = 30.0
        self.dwell_time = 0.0
        self.cursor_pos = QPointF(-100, -100)
        
        # Orb physics
        self.orb_x = 250.0
        self.orb_y = 200.0
        self.orb_vx = 3.2
        self.orb_vy = 2.4
        self.orb_radius = 30.0
        self.is_on_target = False
        
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(16)
        self._fps_timer.timeout.connect(self._tick)

    def set_difficulty(self, diff_key: str):
        if diff_key in self.DIFFICULTIES:
            self.difficulty = diff_key
            cfg = self.DIFFICULTIES[self.difficulty]
            self.orb_radius = cfg["orb_radius"]
            self.update()

    def start_game(self):
        self.is_running = True
        self.time_left = 30.0
        self.dwell_time = 0.0
        self.orb_x = self.width() / 2.0
        self.orb_y = self.height() / 2.0
        cfg = self.DIFFICULTIES.get(self.difficulty, self.DIFFICULTIES["medium"])
        self.orb_radius = cfg["orb_radius"]
        self.orb_vx = cfg["base_speed"]
        self.orb_vy = cfg["base_speed"] * 0.8
        self._fps_timer.start()

    def stop_game(self):
        self.is_running = False
        self._fps_timer.stop()
        self.update()

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.position()
        if not self.is_running and event.buttons() & Qt.LeftButton:
            self.start_game()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_running:
            self.start_game()

    def _tick(self):
        import random, math
        self.time_left = max(0.0, self.time_left - 0.016)
        cfg = self.DIFFICULTIES.get(self.difficulty, self.DIFFICULTIES["medium"])
        
        # Move orb with smooth wall bounces & subtle velocity drift
        self.orb_x += self.orb_vx
        self.orb_y += self.orb_vy
        
        # Jitter acceleration slightly based on difficulty
        drift = 0.25 if self.difficulty in ("hard", "extreme") else 0.15
        self.orb_vx += random.uniform(-drift, drift)
        self.orb_vy += random.uniform(-drift, drift)
        
        # Clamp velocity
        speed = math.hypot(self.orb_vx, self.orb_vy)
        max_s = cfg["max_speed"]
        min_s = cfg["base_speed"] * 0.7
        if speed > max_s:
            self.orb_vx = (self.orb_vx / speed) * max_s
            self.orb_vy = (self.orb_vy / speed) * max_s
        elif speed < min_s:
            self.orb_vx = (self.orb_vx / max(0.1, speed)) * min_s
            self.orb_vy = (self.orb_vy / max(0.1, speed)) * min_s

        # Wall bounce
        pad = self.orb_radius + 15
        if self.orb_x <= pad:
            self.orb_x = pad
            self.orb_vx = abs(self.orb_vx)
        elif self.orb_x >= self.width() - pad:
            self.orb_x = self.width() - pad
            self.orb_vx = -abs(self.orb_vx)

        if self.orb_y <= pad:
            self.orb_y = pad
            self.orb_vy = abs(self.orb_vy)
        elif self.orb_y >= self.height() - pad:
            self.orb_y = self.height() - pad
            self.orb_vy = -abs(self.orb_vy)

        # Check dwell
        dist = math.hypot(self.cursor_pos.x() - self.orb_x, self.cursor_pos.y() - self.orb_y)
        self.is_on_target = (dist <= self.orb_radius)
        if self.is_on_target:
            self.dwell_time += 0.016

        elapsed = 30.0 - self.time_left
        acc = (self.dwell_time / max(0.01, elapsed)) * 100.0
        
        self.stats_updated.emit({
            'time_left': self.time_left,
            'dwell_time': self.dwell_time,
            'accuracy': acc,
            'is_on_target': self.is_on_target
        })
        self.update()

        if self.time_left <= 0.0:
            self.stop_game()
            self.game_finished.emit({
                'dwell_time': self.dwell_time,
                'total_time': 30.0,
                'accuracy': (self.dwell_time / 30.0) * 100.0,
                'difficulty': self.difficulty.upper()
            })

    def paintEvent(self, event):
        import time, math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Canvas background
        painter.setBrush(QBrush(QColor("#111116")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)

        # Draw grid
        painter.setPen(QPen(QColor(255, 255, 255, 8), 1))
        step = 40
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)

        if not self.is_running:
            # Start Overlay
            painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
            painter.drawRoundedRect(self.rect(), 12, 12)
            
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            
            painter.setFont(QFont("Orbitron", 20, QFont.Bold))
            painter.setPen(QPen(QColor("#FF5B06")))
            painter.drawText(QRect(0, int(cy - 40), self.width(), 40), Qt.AlignCenter, "CLICK TO START TRACKING")
            
            painter.setFont(QFont("Orbitron", 11))
            painter.setPen(QPen(QColor("#888888")))
            painter.drawText(QRect(0, int(cy + 10), self.width(), 30), Qt.AlignCenter, f"Difficulty: {self.difficulty.upper()} | 30 Seconds Tracking Test")
            return

        # Draw Orb
        now = time.time()
        pulse = (math.sin(now * 10.0) + 1.0) * 0.5
        
        if self.is_on_target:
            glow_color = QColor("#00FF88")
            body_color = QColor("#00C853")
            core_color = QColor("#ffffff")
        else:
            glow_color = QColor("#00E5FF")
            body_color = QColor("#0091EA")
            core_color = QColor("#E0F7FA")

        # Outer aura
        outer_r = self.orb_radius + (pulse * 8.0)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(140 + pulse * 100)), 2.5))
        painter.drawEllipse(QPointF(self.orb_x, self.orb_y), outer_r, outer_r)

        # Solid body
        from PySide6.QtGui import QRadialGradient
        grad = QRadialGradient(self.orb_x, self.orb_y, self.orb_radius)
        grad.setColorAt(0.0, core_color)
        grad.setColorAt(0.6, glow_color)
        grad.setColorAt(1.0, body_color)
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.drawEllipse(QPointF(self.orb_x, self.orb_y), self.orb_radius, self.orb_radius)

        # Crosshair on cursor
        painter.setPen(QPen(QColor(255, 91, 6, 180), 1.5))
        cx = self.cursor_pos.x()
        cy = self.cursor_pos.y()
        painter.drawLine(int(cx - 10), int(cy), int(cx + 10), int(cy))
        painter.drawLine(int(cx), int(cy - 10), int(cx), int(cy + 10))


TRACKING_DIFFICULTY_RANKS = {
    "easy": [
        (85.0, "WARRIOR", "#00FF88", 5),
        (70.0, "MARKSMAN", "#00E5FF", 4),
        (50.0, "CADET", "#FFD600", 3),
        (30.0, "SCOUT", "#FF5B06", 2),
        (0.0,  "ROOKIE", "#888888", 1),
    ],
    "medium": [
        (88.0, "COMMANDER", "#00FF88", 5),
        (72.0, "SHARPSHOOTER", "#7C4DFF", 4),
        (52.0, "GLADIATOR", "#FFD600", 3),
        (32.0, "VANGUARD", "#FF5B06", 2),
        (0.0,  "SOLDIER", "#888888", 1),
    ],
    "hard": [
        (82.0, "GRANDMASTER", "#00FF88", 5),
        (68.0, "APEX HUNTER", "#00E5FF", 4),
        (48.0, "SNIPER PRO", "#FFD600", 3),
        (28.0, "ASSASSIN", "#FF5B06", 2),
        (0.0,  "VETERAN", "#888888", 1),
    ],
    "extreme": [
        (78.0, "GODLIKE", "#00FF88", 5),
        (62.0, "IMMORTAL", "#00E5FF", 4),
        (42.0, "AIM BOT", "#FFD600", 3),
        (24.0, "HYPER TITAN", "#FF5B06", 2),
        (0.0,  "CYBER REAPER", "#888888", 1),
    ]
}


class PrecisionTrackingPanel(QWidget):
    """
    Precision Tracking Lab Page.
    
    Component Name: PrecisionTrackingPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PrecisionTrackingPanel")
        self.current_difficulty = "medium"
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("TrackingHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#TrackingHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("TrackingBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Reflex Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#TrackingBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#TrackingBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self._on_back)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("PRECISION TRACKING LAB")
        title_lbl.setObjectName("TrackingHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        # Segmented Difficulty Selector
        diff_container = QWidget()
        diff_container.setObjectName("TrackingDiffContainer")
        diff_container.setFixedHeight(28)
        diff_container.setStyleSheet("""
            QWidget#TrackingDiffContainer {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
            }
        """)
        diff_layout = QHBoxLayout(diff_container)
        diff_layout.setContentsMargins(3, 3, 3, 3)
        diff_layout.setSpacing(3)

        self.diff_buttons = {}
        for diff_key, diff_title in [("easy", "EASY"), ("medium", "MEDIUM"), ("hard", "HARD"), ("extreme", "EXTREME")]:
            btn = QPushButton(diff_title)
            btn.setObjectName(f"TrackingDiffBtn_{diff_key}")
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda ch, k=diff_key: self._set_difficulty(k))
            diff_layout.addWidget(btn)
            self.diff_buttons[diff_key] = btn

        h_layout.addWidget(diff_container)

        self.reset_btn = FadeHoverButton("Restart", is_secondary=True, border_radius=6.0)
        self.reset_btn.setObjectName("TrackingResetBtn")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton#TrackingResetBtn, FadeHoverButton#TrackingResetBtn {
                min-width: 65px;
                max-width: 65px;
                min-height: 26px;
                max-height: 26px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
            }
        """)
        self.reset_btn.clicked.connect(self._on_restart)
        h_layout.addWidget(self.reset_btn)

        main_layout.addWidget(header_frame)

        # ── 2. LIVE KPI TELEMETRY BAR ──────────────────────────
        kpi_frame = QFrame()
        kpi_frame.setObjectName("TrackingKpiFrame")
        kpi_frame.setStyleSheet("""
            QFrame#TrackingKpiFrame {
                background-color: rgba(26, 26, 32, 0.9);
                border: none;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        k_layout = QHBoxLayout(kpi_frame)
        k_layout.setContentsMargins(16, 6, 16, 6)
        k_layout.setSpacing(20)

        self.time_lbl = QLabel("TIME: <span style='color:#FF5B06;'>30.0s</span>")
        self.time_lbl.setObjectName("PrecisionTrackingTimeLbl")
        self.time_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.time_lbl)

        self.dwell_lbl = QLabel("DWELL: <span style='color:#00FF88;'>0.0s</span>")
        self.dwell_lbl.setObjectName("PrecisionTrackingDwellLbl")
        self.dwell_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.dwell_lbl)

        self.acc_lbl = QLabel("ACCURACY: <span style='color:#FFD600;'>0.0%</span>")
        self.acc_lbl.setObjectName("PrecisionTrackingAccLbl")
        self.acc_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.acc_lbl)

        self.status_lbl = QLabel("STATUS: <span style='color:#888888;'>OFF TARGET</span>")
        self.status_lbl.setObjectName("PrecisionTrackingStatusLbl")
        self.status_lbl.setStyleSheet("color:#E0E0E0; font-family:'Orbitron', sans-serif; font-size:12px; font-weight:bold;")
        k_layout.addWidget(self.status_lbl)

        k_layout.addStretch()
        main_layout.addWidget(kpi_frame)

        # ── 3. 2D TRACKING CANVAS ──────────────────────────────
        self.canvas = TrackingCanvasWidget()
        self.canvas.setObjectName("PrecisionTrackingCanvas")
        self.canvas.stats_updated.connect(self._on_stats)
        self.canvas.game_finished.connect(self._on_game_over)
        main_layout.addWidget(self.canvas, 1)

        self._set_difficulty("medium")

    def _set_difficulty(self, key):
        self.current_difficulty = key
        self.canvas.set_difficulty(key)
        for d_key, btn in self.diff_buttons.items():
            if d_key == key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF5B06;
                        color: #ffffff;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #888888;
                        font-family: 'Orbitron', sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        color: #ffffff;
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)

    def _on_stats(self, s):
        self.time_lbl.setText(f"TIME: <span style='color:#FF5B06;'>{s['time_left']:.1f}s</span>")
        self.dwell_lbl.setText(f"DWELL: <span style='color:#00FF88;'>{s['dwell_time']:.1f}s</span>")
        self.acc_lbl.setText(f"ACCURACY: <span style='color:#FFD600;'>{s['accuracy']:.1f}%</span>")
        
        if s['is_on_target']:
            self.status_lbl.setText("STATUS: <span style='color:#00FF88; font-weight:bold;'>TRACKING</span>")
        else:
            self.status_lbl.setText("STATUS: <span style='color:#FF5B06;'>OFF TARGET</span>")

    def _on_game_over(self, data):
        acc = data['accuracy']
        dwell = data['dwell_time']
        diff_key = self.current_difficulty.lower()
        diff_label = diff_key.upper()
        
        ranks_list = TRACKING_DIFFICULTY_RANKS.get(diff_key, TRACKING_DIFFICULTY_RANKS["medium"])
        rank, color, stars = ranks_list[-1][1], ranks_list[-1][2], ranks_list[-1][3]
        for min_acc, r_title, r_color, r_stars in ranks_list:
            if acc >= min_acc:
                rank, color, stars = r_title, r_color, r_stars
                break

        metrics = [
            ("Difficulty:", diff_label),
            ("Accuracy:", f"{acc:.1f}%"),
            ("Time On Target:", f"{dwell:.1f}s / 30s"),
            ("Consistency:", "High Precision")
        ]

        overlay = ReflexResultOverlay(
            parent_panel=self,
            title="PRECISION TRACKING RESULT",
            rank_badge=rank,
            star_rating=stars,
            rank_color=color,
            metrics=metrics,
            on_retry=self._on_restart,
            on_hub=self._on_back
        )
        overlay.show()

    def _on_restart(self):
        self.canvas.start_game()

    def _on_back(self):
        self.canvas.stop_game()
        self.back_clicked.emit()


class ReflexHubPanel(QWidget):
    """
    Reflex Lab Selection Hub with 3 Feature Cards.
    Matching Benchmark Lab styling with enclosing QGroupBox.
    
    Component Name: ReflexHubPanel
    """
    mode_selected = Signal(int)  # 1: Reaction Time, 2: Gridshot, 3: Tracking

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReflexHubPanel")
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

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

        # Reflex & Aim Arena Group Box (Use && to escape mnemonic shortcut in Qt)
        hub_group = QGroupBox("Reflex && Aim Arena")
        hub_group.setObjectName("ReflexArenaGroup")
        hub_group.setStyleSheet(_grp_style)
        hub_group_layout = QVBoxLayout(hub_group)
        hub_group_layout.setContentsMargins(16, 20, 16, 16)
        hub_group_layout.setSpacing(12)

        desc_lbl = QLabel("Universal Reflex Training, Flick Accuracy & Smooth Mouse Tracking Diagnostics Suite")
        desc_lbl.setObjectName("ReflexHubHeaderDesc")
        desc_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        hub_group_layout.addWidget(desc_lbl)

        # 3 Cards Row
        cards_container = QWidget()
        cards_container.setObjectName("ReflexCardsContainer")
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(15)

        # Card 1: Reaction Test
        card1 = self._create_card(
            card_id="ReactionCard",
            title="Reaction Time Test",
            desc="Measure visual reflex latency in milliseconds across 5 rounds.",
            mode_idx=1
        )
        cards_layout.addWidget(card1)

        # Card 2: Gridshot Arena
        card2 = self._create_card(
            card_id="GridshotCard",
            title="Gridshot Flick Arena",
            desc="30s high-speed target flicking test. Measure TPS and accuracy %.",
            mode_idx=2
        )
        cards_layout.addWidget(card2)

        # Card 3: Precision Tracking
        card3 = self._create_card(
            card_id="TrackingCard",
            title="Precision Tracking Lab",
            desc="Smooth continuous tracking test. Measure cursor dwell accuracy.",
            mode_idx=3
        )
        cards_layout.addWidget(card3)

        hub_group_layout.addWidget(cards_container)
        main_layout.addWidget(hub_group)
        main_layout.addStretch()

    def _create_card(self, card_id, title, desc, mode_idx):
        card = QFrame()
        card.setObjectName(card_id)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(f"""
            QFrame#{card_id} {{
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }}
            QFrame#{card_id}:hover {{
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(15, 15, 15, 15)
        c_layout.setSpacing(6)

        # Title
        t_lbl = QLabel(title)
        t_lbl.setObjectName(f"{card_id}_Title")
        t_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        t_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        c_layout.addWidget(t_lbl)

        # Description
        d_lbl = QLabel(desc)
        d_lbl.setObjectName(f"{card_id}_Desc")
        d_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        d_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent;")
        d_lbl.setWordWrap(True)
        c_layout.addWidget(d_lbl)
        c_layout.addStretch()

        card.mousePressEvent = lambda e: self.mode_selected.emit(mode_idx)
        return card


# =====================================================================
# ── TACTICAL TOOLS SUITE: FEATURE 1 — SNIPER DPI CLUTCH ─────────────
# =====================================================================

SPI_GETMOUSESPEED = 0x0070
SPI_SETMOUSESPEED = 0x0071
SPIF_SENDCHANGE = 0x0002


class SniperClutchController(QObject):
    """
    Win32 Dynamic Precision Pointer Throttler.
    Component Name: SniperClutchController
    """
    clutch_state_changed = Signal(bool, int, int)  # is_active, current_speed, baseline_speed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SniperClutchController")
        self.is_enabled = False
        self.is_clutch_held = False
        self.hold_to_trigger = False  # Default OFF (Toggle Mode)
        self._last_phys_down = False
        self.damping_percent = 40  # 40% of baseline speed
        self.trigger_key = "Right Click"
        
        # Read system baseline speed once and anchor it
        detected = self._get_system_mouse_speed()
        self.baseline_speed = detected if (1 <= detected <= 20) else 10
        self._calculate_clutch_speed()

        # High-frequency watchdog (25ms) to detect physical key hold/release
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(25)
        self._watchdog.timeout.connect(self._poll_physical_trigger)
        
        atexit.register(self.force_restore)

    def _get_system_mouse_speed(self) -> int:
        try:
            speed = ctypes.c_int()
            ctypes.windll.user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, ctypes.byref(speed), 0)
            val = speed.value
            return val if (1 <= val <= 20) else 10
        except Exception:
            return 10

    def _set_system_mouse_speed(self, speed: int):
        try:
            val = max(1, min(20, int(speed)))
            ctypes.windll.user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, ctypes.c_void_p(val), SPIF_SENDCHANGE)
        except Exception as e:
            print(f"[SniperClutch] Failed to set pointer speed: {e}")

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if enabled:
            # Refresh baseline before starting
            if not self.is_clutch_held:
                cur = self._get_system_mouse_speed()
                if 1 <= cur <= 20:
                    self.baseline_speed = cur
                self._calculate_clutch_speed()
            self._watchdog.start()
            print(f"[SniperClutch] Armed & Enabled (Baseline: {self.baseline_speed}, Clutch: {self.clutch_speed}, Key: {self.trigger_key})")
        else:
            self._watchdog.stop()
            self.force_restore()
            print("[SniperClutch] Disarmed & Disabled")

    def _calculate_clutch_speed(self):
        self.clutch_speed = max(1, int(round(self.baseline_speed * (self.damping_percent / 100.0))))

    def set_damping_percent(self, val: int):
        self.damping_percent = max(10, min(90, int(val)))
        self._calculate_clutch_speed()

    def set_trigger_key(self, key_name: str):
        self.trigger_key = key_name
        self._hotkey_last_state = True
        self._suppress_hotkey_ticks = 20  # Debounce suppression for ~500ms after recording

    def reset_to_standard_baseline(self):
        """Emergency reset Windows speed back to 10."""
        self.baseline_speed = 10
        self._calculate_clutch_speed()
        self._set_system_mouse_speed(10)
        self.is_clutch_held = False
        self.clutch_state_changed.emit(False, 10, 10)

    def _get_vk_code(self, key_name: str) -> int:
        raw = key_name.strip().lower()
        mapping = {
            "left click": 0x01,      # VK_LBUTTON
            "mouse 1": 0x01,
            "right click": 0x02,     # VK_RBUTTON
            "rclick": 0x02,
            "mouse 2": 0x02,
            "middle click": 0x04,    # VK_MBUTTON
            "wheel": 0x04,
            "mouse 3": 0x04,
            "mouse 4": 0x05,         # VK_XBUTTON1
            "mouse button 4": 0x05,
            "mouse 5": 0x06,         # VK_XBUTTON2
            "mouse button 5": 0x06,
            "left alt": 0xA4,        # VK_LMENU (0xA4)
            "right alt": 0xA5,       # VK_RMENU (0xA5)
            "alt": 0x12,             # VK_MENU
            "left ctrl": 0xA2,       # VK_LCONTROL (0xA2)
            "right ctrl": 0xA3,      # VK_RCONTROL (0xA3)
            "ctrl": 0x11,            # VK_CONTROL
            "control": 0x11,
            "left shift": 0xA0,      # VK_LSHIFT (0xA0)
            "right shift": 0xA1,     # VK_RSHIFT (0xA1)
            "shift": 0x10,           # VK_SHIFT
            "space": 0x20,           # VK_SPACE
            "spacebar": 0x20,
            "tab": 0x09,
            "caps lock": 0x14,
            "capslock": 0x14,
            "enter": 0x0D,
            "return": 0x0D,
            "backspace": 0x08,
            "delete": 0x2E,
            "insert": 0x2D,
        }
        for i in range(1, 13):
            mapping[f"f{i}"] = 0x70 + (i - 1)

        if raw in mapping:
            return mapping[raw]
            
        if len(raw) == 1:
            return ord(raw.upper())
            
        if raw.startswith("key ") or raw.startswith("key_"):
            char = raw.split()[-1]
            if len(char) == 1:
                return ord(char.upper())

        return 0x01

    def set_hold_to_trigger(self, hold: bool):
        self.hold_to_trigger = bool(hold)
        if not self.hold_to_trigger:
            self._last_phys_down = False

    def _poll_physical_trigger(self):
        if not self.is_enabled:
            return
        vk = self._get_vk_code(self.trigger_key)
        is_physically_down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        
        if self.hold_to_trigger:
            # HOLD MODE: Active while key is physically held down
            if is_physically_down and not self.is_clutch_held:
                self._set_system_mouse_speed(self.clutch_speed)
                self.is_clutch_held = True
                self.clutch_state_changed.emit(True, self.clutch_speed, self.baseline_speed)
            elif not is_physically_down and self.is_clutch_held:
                self._set_system_mouse_speed(self.baseline_speed)
                self.is_clutch_held = False
                self.clutch_state_changed.emit(False, self.baseline_speed, self.baseline_speed)
        else:
            # TOGGLE MODE (Default): Press once to toggle on, press again to toggle off
            if is_physically_down and not self._last_phys_down:
                new_state = not self.is_clutch_held
                self.is_clutch_held = new_state
                target_speed = self.clutch_speed if new_state else self.baseline_speed
                self._set_system_mouse_speed(target_speed)
                self.clutch_state_changed.emit(new_state, target_speed, self.baseline_speed)
            self._last_phys_down = is_physically_down

    def force_restore(self):
        self._set_system_mouse_speed(self.baseline_speed)
        self.is_clutch_held = False
        self.clutch_state_changed.emit(False, self.baseline_speed, self.baseline_speed)


class TacticalInputCatcherButton(QPushButton):
    """
    Interactive Key & Mouse Input Catcher Widget.
    Automatically captures ANY keyboard key or mouse button pressed.
    Component Name: TacticalInputCatcherButton
    """
    input_captured = Signal(str)
    win_key_swallowed = Signal()

    def __init__(self, default_key="Right Click", parent=None):
        super().__init__(parent)
        self.setObjectName("TacticalInputCatcherBtn")
        self._current_key = default_key
        self._is_capturing = False
        self._hook = None
        self._hook_proc_ref = None
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.win_key_swallowed.connect(self._on_win_key_swallowed, Qt.QueuedConnection)
        self._update_display()

    def _install_hook(self):
        if self._hook is not None:
            return
        try:
            from ctypes import wintypes
            # Use isolated WinDLL handle to prevent argtypes collision with MediaKeyService/UniversalMacroHook
            self._user32_dll = ctypes.WinDLL("user32", use_last_error=True)
            
            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_ulonglong)
                ]
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))
            
            self._user32_dll.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            self._user32_dll.SetWindowsHookExW.restype = wintypes.HHOOK
            self._user32_dll.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            self._user32_dll.UnhookWindowsHookEx.restype = wintypes.BOOL
            self._user32_dll.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)]
            self._user32_dll.CallNextHookEx.restype = ctypes.c_longlong

            def _low_level_kb_proc(nCode, wParam, lParam):
                if nCode >= 0 and self._is_capturing:
                    vk = lParam.contents.vkCode
                    if vk in (0x5B, 0x5C):  # VK_LWIN, VK_RWIN
                        if wParam in (0x0100, 0x0104):  # WM_KEYDOWN, WM_SYSKEYDOWN
                            # Inject dummy key (0xE8) to permanently cancel Windows Start Menu trigger
                            try:
                                self._user32_dll.keybd_event(0xE8, 0, 0, 0)
                                self._user32_dll.keybd_event(0xE8, 0, 2, 0)
                            except Exception:
                                pass
                            self.win_key_swallowed.emit()
                        return 1  # Swallow Windows key on both KEYDOWN & KEYUP!
                return self._user32_dll.CallNextHookEx(self._hook, nCode, wParam, lParam)

            self._hook_proc_ref = HOOKPROC(_low_level_kb_proc)
            self._hook = self._user32_dll.SetWindowsHookExW(13, self._hook_proc_ref, None, 0)
            if not self._hook:
                err = ctypes.get_last_error()
                print(f"[TacticalInputCatcher] Hook install failed with code: {err}")
        except Exception as e:
            print(f"[TacticalInputCatcher] Hook install error: {e}")
            self._hook = None

    def _remove_hook(self):
        if self._hook is not None:
            try:
                if hasattr(self, '_user32_dll') and self._user32_dll:
                    self._user32_dll.UnhookWindowsHookEx(self._hook)
                else:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
            self._hook_proc_ref = None

    @Slot()
    def _on_win_key_swallowed(self):
        target_w = self.window() if self.window() else self
        FloatingToast.show_toast(target_w, "Trigger Key Restricted", "Windows Key is reserved by the OS (Please choose another key)")
        QTimer.singleShot(150, lambda: self._finish_capture(self._current_key))

    def set_captured_key(self, key_name: str):
        self._current_key = key_name
        self._is_capturing = False
        self._update_display()

    def get_captured_key(self) -> str:
        return self._current_key

    def _update_display(self):
        if self._is_capturing:
            self.setText("[ PRESS ANY KEY OR MOUSE BUTTON... ]")
            self.setStyleSheet("""
                QPushButton#TacticalInputCatcherBtn {
                    background-color: #1e2128;
                    color: #FF5B06;
                    border: 1px solid #FF5B06;
                    border-radius: 6px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    text-align: center;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.setText(f"BOUND: {self._current_key.upper()}")
            self.setStyleSheet("""
                QPushButton#TacticalInputCatcherBtn {
                    background-color: #1e2128;
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 6px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    text-align: center;
                    min-height: 26px;
                    max-height: 26px;
                }
                QPushButton#TacticalInputCatcherBtn:hover {
                    background-color: #1e2128;
                    border: 1px solid #FF5B06;
                    color: #FF5B06;
                }
            """)

    def mousePressEvent(self, event):
        if not self._is_capturing:
            # Start capturing mode
            self._is_capturing = True
            self._update_display()
            self.setFocus()
            self.grabKeyboard()
            self.grabMouse()
            self._install_hook()
            event.accept()
        else:
            # Capture the pressed mouse button (Reject Left Click)
            btn = event.button()
            if btn == Qt.LeftButton:
                target_w = self.window() if self.window() else self
                FloatingToast.show_toast(target_w, "Trigger Key Restricted", "Left Click is reserved for primary shooting / clicking")
                self._finish_capture(self._current_key)
                event.accept()
                return

            btn_name = "Right Click"
            if btn == Qt.RightButton:
                btn_name = "Right Click"
            elif btn == Qt.MiddleButton:
                btn_name = "Middle Click"
            elif btn == Qt.BackButton or btn == Qt.XButton1:
                btn_name = "Mouse 4"
            elif btn == Qt.ForwardButton or btn == Qt.XButton2:
                btn_name = "Mouse 5"

            self._finish_capture(btn_name)
            event.accept()

    def keyPressEvent(self, event):
        if self._is_capturing:
            key = event.key()
            if key == Qt.Key_Escape:
                # Cancel capturing without changes
                self._finish_capture(self._current_key)
                event.accept()
                return

            if key in (Qt.Key_Meta, 0x5B, 0x5C):
                target_w = self.window() if self.window() else self
                FloatingToast.show_toast(target_w, "Trigger Key Restricted", "Windows Key is reserved by the OS (Please choose another key)")
                self._finish_capture(self._current_key)
                event.accept()
                return

            key_name = self._format_key(event)
            self._finish_capture(key_name)
            event.accept()
        else:
            super().keyPressEvent(event)

    def _format_key(self, event) -> str:
        key = event.key()
        vk = event.nativeVirtualKey()
        scan = event.nativeScanCode()

        # Modifier keys (Distinguish Left vs Right)
        if key == Qt.Key_Alt or vk in (0x12, 0xA4, 0xA5):
            try:
                if (ctypes.windll.user32.GetAsyncKeyState(0xA5) & 0x8000) != 0:
                    return "Right Alt"
                elif (ctypes.windll.user32.GetAsyncKeyState(0xA4) & 0x8000) != 0:
                    return "Left Alt"
            except Exception:
                pass
            return "Right Alt" if (event.nativeModifiers() & 0x02000000 or vk == 0xA5) else "Left Alt"

        if key == Qt.Key_Control or vk in (0x11, 0xA2, 0xA3):
            try:
                if (ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000) != 0:
                    return "Right Ctrl"
                elif (ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000) != 0:
                    return "Left Ctrl"
            except Exception:
                pass
            return "Right Ctrl" if (event.nativeModifiers() & 0x02000000 or vk == 0xA3) else "Left Ctrl"

        if key == Qt.Key_Shift or vk in (0x10, 0xA0, 0xA1):
            try:
                if (ctypes.windll.user32.GetAsyncKeyState(0xA1) & 0x8000) != 0:
                    return "Right Shift"
                elif (ctypes.windll.user32.GetAsyncKeyState(0xA0) & 0x8000) != 0:
                    return "Left Shift"
            except Exception:
                pass
            return "Right Shift" if (scan == 54 or vk == 0xA1) else "Left Shift"

        if key == Qt.Key_Space:
            return "Spacebar"
        elif key == Qt.Key_Tab:
            return "Tab"
        elif key == Qt.Key_CapsLock:
            return "Caps Lock"
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            return "Enter"
        elif key == Qt.Key_Backspace:
            return "Backspace"
        elif key == Qt.Key_Delete:
            return "Delete"
        elif key == Qt.Key_Insert:
            return "Insert"
        elif key >= Qt.Key_F1 and key <= Qt.Key_F12:
            return f"F{key - Qt.Key_F1 + 1}"

        # Single alphanumeric characters (remove "Key " prefix)
        text = event.text().strip().upper()
        if text and len(text) == 1 and text.isprintable():
            return text

        seq = QKeySequence(key).toString().strip()
        if seq:
            if seq.startswith("Key "):
                seq = seq[4:].strip()
            return seq

        return "Right Click"

    def _finish_capture(self, key_name: str):
        self._remove_hook()
        try:
            self.releaseKeyboard()
            self.releaseMouse()
        except Exception:
            pass
        self._current_key = key_name
        self._is_capturing = False
        self._update_display()
        self.input_captured.emit(key_name)

    def focusOutEvent(self, event):
        if self._is_capturing:
            self._remove_hook()
            try:
                self.releaseKeyboard()
                self.releaseMouse()
            except Exception:
                pass
            self._is_capturing = False
            self._update_display()
        super().focusOutEvent(event)


class SniperAimCanvas(QWidget):
    """
    Live Aim Calibration Canvas for testing Sniper DPI Clutch.
    Ultra-smooth, zero-latency canvas with cached background rendering.
    Component Name: SniperAimCanvas
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SniperAimCanvas")
        self.setMouseTracking(True)
        self.is_clutch_active = False
        self.current_speed = 10
        self.baseline_speed = 10
        self.cursor_pos = QPoint(150, 100)
        self._bg_cache = None

    def set_clutch_state(self, active: bool, cur_speed: int, base_speed: int):
        if self.is_clutch_active != active or self.current_speed != cur_speed or self.baseline_speed != base_speed:
            self.is_clutch_active = active
            self.current_speed = cur_speed
            self.baseline_speed = base_speed
            self._render_background_cache()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_background_cache()

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.pos()
        self.update()

    def _render_background_cache(self):
        w = max(1, self.width())
        h = max(1, self.height())
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Canvas Background
        bg_color = QColor(24, 18, 16, 240) if self.is_clutch_active else QColor(18, 18, 22, 240)
        painter.setBrush(QBrush(bg_color))
        border_pen = QPen(QColor(255, 91, 6, 160) if self.is_clutch_active else QColor(255, 255, 255, 25), 1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 10, 10)

        # Tactical Grid Lines
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1, Qt.DashLine))
        for x in range(30, w, 30):
            painter.drawLine(x, 0, x, h)
        for y in range(30, h, 30):
            painter.drawLine(0, y, w, y)

        # Concentric Target Circles in Center
        cx, cy = w // 2, h // 2
        ring_pen = QPen(QColor(255, 91, 6, 140) if self.is_clutch_active else QColor(255, 255, 255, 30), 1.5)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 40, 40)
        painter.drawEllipse(QPointF(cx, cy), 80, 80)
        painter.drawEllipse(QPointF(cx, cy), 120, 120)

        # Center Crosshair
        painter.setPen(QPen(QColor(255, 91, 6, 220) if self.is_clutch_active else QColor(255, 255, 255, 60), 1.5))
        painter.drawLine(cx - 15, cy, cx + 15, cy)
        painter.drawLine(cx, cy - 15, cx, cy + 15)

        painter.end()
        self._bg_cache = pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw Cached Background
        if self._bg_cache is not None:
            painter.drawPixmap(0, 0, self._bg_cache)
        else:
            self._render_background_cache()
            if self._bg_cache is not None:
                painter.drawPixmap(0, 0, self._bg_cache)

        # Follow Cursor Reticle
        cx_pos = max(10, min(self.width() - 10, self.cursor_pos.x()))
        cy_pos = max(10, min(self.height() - 10, self.cursor_pos.y()))

        reticle_color = QColor("#FF5B06") if self.is_clutch_active else QColor("#888888")
        painter.setPen(QPen(reticle_color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(cx_pos, cy_pos), 14, 14)
        painter.drawLine(cx_pos - 18, cy_pos, cx_pos + 18, cy_pos)
        painter.drawLine(cx_pos, cy_pos - 18, cx_pos, cy_pos + 18)

        # Telemetry Text Overlay
        painter.setFont(QFont("Orbitron", 10, QFont.Bold))
        if self.is_clutch_active:
            painter.setPen(QColor("#FF5B06"))
            status_text = f"[AIM ENGAGED] SNIPER CLUTCH ACTIVE [SPEED: {self.current_speed} / {self.baseline_speed}]"
        else:
            painter.setPen(QColor("#888888"))
            status_text = f"[STANDBY] NORMAL POINTER SPEED [{self.baseline_speed} / 20] — Hold Trigger Key to Test"
class SniperTriggerGuidePanel(QFrame):
    """
    Floating guide panel for Sniper DPI Clutch Trigger Key Validation Rules.
    Matching HELRCUS / HELXAIL floating guide style.
    
    Component Name: SniperTriggerGuidePanel
    """
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("SniperTriggerGuidePanel")
        self._is_dragging = False
        self._drag_start_pos = QPoint(0, 0)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.setStyleSheet("""
            QFrame#SniperTriggerGuidePanel {
                background-color: rgba(22, 22, 26, 0.98);
                border: none;
                border-radius: 14px;
            }
            QWidget#GuideTitleBar {
                background-color: rgba(14, 14, 16, 0.7);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                border: none;
            }
            QLabel#GuideTitle {
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                border: none;
                background: transparent;
            }
        """)
        
        self.setFixedSize(480, 340)
        
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 16)
        main_vbox.setSpacing(10)
        
        # Title bar (Draggable)
        self.title_bar = QWidget()
        self.title_bar.setObjectName("GuideTitleBar")
        self.title_bar.setFixedHeight(42)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(16, 0, 12, 0)
        
        info_icon_path = os.path.join(script_dir, "UI Icons", "info-icon.svg").replace('\\', '/')
        if os.path.exists(info_icon_path):
            icon_lbl = QLabel()
            icon_lbl.setObjectName("SniperGuideIconLbl")
            pixmap = QPixmap(info_icon_path)
            if not pixmap.isNull():
                icon_lbl.setPixmap(pixmap.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_lbl.setStyleSheet("background: transparent;")
            tb_layout.addWidget(icon_lbl)
            
        title_lbl = QLabel("Trigger Key Validation Rules")
        title_lbl.setObjectName("GuideTitle")
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()
        
        main_vbox.addWidget(self.title_bar)
        
        # Content body with SmoothScrollArea
        content_container = QWidget()
        content_container.setObjectName("SniperGuideContentContainer")
        body_vbox = QVBoxLayout(content_container)
        body_vbox.setContentsMargins(16, 0, 16, 0)
        body_vbox.setSpacing(0)
        
        rules_html = """
        <p style='font-size: 12px; color: #aaa; line-height: 1.4; margin-bottom: 8px; font-family: Orbitron, sans-serif;'>
        Standard rules to ensure custom trigger keys do not conflict with Windows OS & game controls:
        </p>
        <ul style='font-size: 12px; color: #e0e0e0; line-height: 1.7; margin-left: -15px; font-family: Orbitron, sans-serif;'>
            <li><b>Left Click Restricted:</b> Left Click is reserved for primary interaction & shooting in games.</li>
            <li><b>No Windows Key:</b> Win / Meta key is forbidden to prevent opening OS Start Menu.</li>
            <li><b>No Escape Key:</b> Escape key is reserved for cancelling key capture & game menus.</li>
            <li><b>Supported Mouse Buttons:</b> <b>Right Click</b>, <b>Middle Click</b>, <b>Mouse 4</b>, <b>Mouse 5</b>.</li>
            <li><b>Supported Modifiers:</b> <b>Left/Right Alt</b>, <b>Left/Right Ctrl</b>, <b>Left/Right Shift</b>.</li>
            <li><b>Supported Keyboard Keys:</b> <b>Spacebar</b>, <b>Tab</b>, <b>Caps Lock</b>, <b>Enter</b>, <b>A – Z</b>, <b>0 – 9</b>, <b>F1 – F12</b>.</li>
        </ul>
        """
        rules_lbl = QLabel(rules_html)
        rules_lbl.setObjectName("SniperGuideRulesLbl")
        rules_lbl.setWordWrap(True)
        rules_lbl.setStyleSheet("background: transparent; color: #e0e0e0;")
        
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setObjectName("SniperGuideScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.2);
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 91, 6, 0.5);
                border-radius: 4px;
                min-height: 25px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 91, 6, 0.8);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0;
            }
        """)
        self.scroll_area.setWidget(rules_lbl)
        body_vbox.addWidget(self.scroll_area, 1)
        
        main_vbox.addWidget(content_container, 1)
        
        # Action button (Got It - styled matching helxairo_acCreateBtn)
        action_row = QHBoxLayout()
        action_row.setContentsMargins(20, 0, 20, 0)
        action_row.addStretch()
        
        got_it_btn = FadeHoverButton("Got It", border_radius=6.0)
        got_it_btn.setObjectName("helxairo_guideGotItBtn")
        got_it_btn.setFixedHeight(30)
        got_it_btn.setFixedWidth(85)
        got_it_btn.clicked.connect(self.close_panel)
        action_row.addWidget(got_it_btn)
        
        main_vbox.addLayout(action_row)
        
        # Opacity & animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self._opacity_effect.setOpacity(0.0)
        self._fade_anim.start()
        
    def close_panel(self):
        self.close()
        self.closed.emit()
        self.deleteLater()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and hasattr(self, "title_bar") and self.title_bar.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                new_pos = QPoint(new_x, new_y)
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)


class SniperClutchPanel(QWidget):
    """
    Sniper DPI Clutch Configuration & Calibration Panel.
    Component Name: SniperClutchPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SniperClutchPanel")
        self.controller = SniperClutchController(self)
        self._guide_panel = None
        self._setup_ui()
        # Default to DISABLED for clean startup safety
        self._set_active_state(False)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("SniperHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#SniperHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("SniperBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Tactical Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#SniperBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#SniperBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self._on_back)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("SNIPER DPI CLUTCH")
        title_lbl.setObjectName("SniperHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        self.reset_spd_btn = QPushButton("Reset Speed (10)")
        self.reset_spd_btn.setObjectName("SniperResetSpeedBtn")
        self.reset_spd_btn.setFixedSize(120, 26)
        self.reset_spd_btn.setCursor(Qt.PointingHandCursor)
        self.reset_spd_btn.setToolTip("Reset Windows pointer speed back to normal 10")
        self.reset_spd_btn.setStyleSheet("""
            QPushButton#SniperResetSpeedBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0px 6px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#SniperResetSpeedBtn:hover {
                background-color: rgba(255, 91, 6, 0.3);
                color: #FFFFFF;
            }
        """)
        self.reset_spd_btn.clicked.connect(self.controller.reset_to_standard_baseline)
        h_layout.addWidget(self.reset_spd_btn)

        self.enable_btn = QPushButton("DISABLED")
        self.enable_btn.setObjectName("SniperEnableBtn")
        self.enable_btn.setFixedSize(90, 26)
        self.enable_btn.setCursor(Qt.PointingHandCursor)
        self.enable_btn.setStyleSheet("""
            QPushButton#SniperEnableBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #888888;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0px 8px;
                min-height: 26px;
                max-height: 26px;
            }
        """)
        self.enable_btn.clicked.connect(self._toggle_enable)
        h_layout.addWidget(self.enable_btn)

        main_layout.addWidget(header_frame)

        # ── 2. CONFIGURATION CARDS (2 COLUMNS) ─────────────────
        cfg_layout = QHBoxLayout()
        cfg_layout.setSpacing(12)

        # Card 1: Trigger Key Selection
        key_card = QFrame()
        key_card.setObjectName("SniperKeyCard")
        key_card.setFixedHeight(76)
        key_card.setStyleSheet("""
            QFrame#SniperKeyCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        kc_layout = QVBoxLayout(key_card)
        kc_layout.setContentsMargins(12, 10, 12, 10)
        kc_layout.setSpacing(6)

        kc_title = QLabel("TRIGGER KEY BINDING")
        kc_title.setObjectName("SniperKeyTitle")
        kc_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        kc_layout.addWidget(kc_title)

        # Horizontal row for universal key input + info button + hold toggle
        self.key_row_layout = QHBoxLayout()
        self.key_row_layout.setContentsMargins(0, 0, 0, 0)
        self.key_row_layout.setSpacing(8)

        # Universal Trigger Key Input Catcher Button
        self.custom_key_input = TacticalInputCatcherButton(default_key="Right Click")
        self.custom_key_input.setObjectName("SniperCustomKeyInput")
        self.custom_key_input.setFixedHeight(28)
        self.custom_key_input.setVisible(True)
        self.custom_key_input.input_captured.connect(self._on_custom_input_captured)

        # Info Button for Restricted Keys Guide
        self.custom_info_btn = QPushButton()
        self.custom_info_btn.setObjectName("SniperCustomInfoBtn")
        self.custom_info_btn.setFixedSize(28, 28)
        self.custom_info_btn.setCursor(Qt.PointingHandCursor)
        info_icon_path = os.path.join(script_dir, "UI Icons", "info-icon.svg").replace('\\', '/')
        if os.path.exists(info_icon_path):
            self.custom_info_btn.setIcon(QIcon(info_icon_path))
            self.custom_info_btn.setIconSize(QSize(26, 26))
        self.custom_info_btn.setToolTip(
            "RESTRICTED KEYS (Cannot be used):\n"
            "• Left Click (Primary interaction/firing button)\n"
            "• Windows Key (OS Reserved)\n"
            "• Escape Key (Cancel action)\n\n"
            "SUPPORTED KEYS:\n"
            "• Right Click, Middle Click, Mouse 4, Mouse 5\n"
            "• Alt, Ctrl, Shift, Spacebar, Tab, Caps Lock\n"
            "• Any Letter (A-Z), Number, Function Keys (F1-F12)"
        )
        self.custom_info_btn.setStyleSheet("""
            QPushButton#SniperCustomInfoBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#SniperCustomInfoBtn:hover {
                background: transparent;
                border: none;
            }
        """)
        self.custom_info_btn.setVisible(True)
        self.custom_info_btn.clicked.connect(self._show_restricted_keys_dialog)

        # Hold to Trigger Toggle Switch (Standard HELXAID AnimatedCheckBox)
        self.hold_toggle = AnimatedCheckBox("Hold to trigger")
        self.hold_toggle.setObjectName("helxairo_sniperHoldToggle")
        self.hold_toggle.setToolTip("When enabled (Hold mode): Clutch stays active while key is held down.\nWhen disabled (Toggle mode): Press key once to toggle clutch on/off.")
        self.hold_toggle.setFixedSize(130, 28)
        self.hold_toggle.setChecked(False)
        self.hold_toggle.toggled.connect(self._on_hold_toggle_changed)
        self.hold_toggle.stateChanged.connect(lambda s: self._on_hold_toggle_changed(s == 2))

        self.key_row_layout.addWidget(self.custom_key_input, 1)
        self.key_row_layout.addWidget(self.custom_info_btn)
        self.key_row_layout.addWidget(self.hold_toggle)
        kc_layout.addLayout(self.key_row_layout)
        cfg_layout.addWidget(key_card, 1)

        # Card 2: Damping Percentage Slider
        damp_card = QFrame()
        damp_card.setObjectName("SniperDampCard")
        damp_card.setFixedHeight(76)
        damp_card.setStyleSheet("""
            QFrame#SniperDampCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        dc_layout = QVBoxLayout(damp_card)
        dc_layout.setContentsMargins(12, 10, 12, 10)
        dc_layout.setSpacing(6)

        dc_title_row = QHBoxLayout()
        dc_title = QLabel("AIM SENSITIVITY DAMPING")
        dc_title.setObjectName("SniperDampTitle")
        dc_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        dc_title_row.addWidget(dc_title)
        dc_title_row.addStretch()

        self.damp_val_lbl = QLabel("40% (Slow)")
        self.damp_val_lbl.setObjectName("SniperDampValLabel")
        self.damp_val_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        dc_title_row.addWidget(self.damp_val_lbl)
        dc_layout.addLayout(dc_title_row)

        self.damp_slider = QSlider(Qt.Horizontal)
        self.damp_slider.setObjectName("SniperDampSlider")
        self.damp_slider.setRange(10, 80)
        self.damp_slider.setValue(40)
        self.damp_slider.setStyleSheet("""
            QSlider#SniperDampSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            QSlider#SniperDampSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 2px;
            }
            QSlider#SniperDampSlider::handle:horizontal {
                background: #FFFFFF;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        self.damp_slider.valueChanged.connect(self._on_damp_changed)
        dc_layout.addWidget(self.damp_slider)
        cfg_layout.addWidget(damp_card, 1)

        main_layout.addLayout(cfg_layout)

        # ── 3. LIVE AIM TEST CANVAS ────────────────────────────
        self.aim_canvas = SniperAimCanvas()
        self.aim_canvas.setObjectName("SniperAimCanvas")
        self.controller.clutch_state_changed.connect(self.aim_canvas.set_clutch_state)
        main_layout.addWidget(self.aim_canvas, 1)

    def _toggle_enable(self):
        new_state = not self.controller.is_enabled
        self._set_active_state(new_state)

    def _set_active_state(self, active: bool):
        self.controller.set_enabled(active)
        if active:
            self.enable_btn.setText("ACTIVE")
            self.enable_btn.setStyleSheet("""
                QPushButton#SniperEnableBtn {
                    background-color: #00FF88;
                    color: #000000;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.enable_btn.setText("DISABLED")
            self.enable_btn.setStyleSheet("""
                QPushButton#SniperEnableBtn {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #888888;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)

    def _on_hold_toggle_changed(self, checked: bool):
        self.controller.set_hold_to_trigger(checked)
        mode_str = "Hold Mode" if checked else "Toggle Mode"
        print(f"[SniperClutch] Trigger Mode Changed: {mode_str} (Hold to trigger: {checked})")

    def _on_custom_input_captured(self, key_name: str):
        self.controller.set_trigger_key(key_name)
        print(f"[SniperClutch] Trigger Key Captured & Bound: {key_name}")

    def _show_restricted_keys_dialog(self):
        try:
            if self._guide_panel is not None:
                if self._guide_panel.isVisible():
                    self._guide_panel.close_panel()
                    self._guide_panel = None
                    return
        except (RuntimeError, Exception):
            self._guide_panel = None

        target_parent = self.window() if self.window() else self
        self._guide_panel = SniperTriggerGuidePanel(target_parent)
        self._guide_panel.closed.connect(self._on_guide_panel_destroyed)
        self._guide_panel.destroyed.connect(self._on_guide_panel_destroyed)
        gx = max(20, (target_parent.width() - self._guide_panel.width()) // 2)
        gy = max(20, (target_parent.height() - self._guide_panel.height()) // 2)
        self._guide_panel.move(gx, gy)
        self._guide_panel.show()

    def _on_guide_panel_destroyed(self):
        self._guide_panel = None

    def _on_damp_changed(self, val):
        self.controller.set_damping_percent(val)
        desc = "Ultra Slow" if val <= 20 else ("Slow" if val <= 45 else ("Medium" if val <= 65 else "Subtle"))
        self.damp_val_lbl.setText(f"{val}% ({desc})")

    def _on_back(self):
        self.controller.force_restore()
        self.back_clicked.emit()




class Win32Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class CursorClampHotkeyButton(QPushButton):
    """
    Interactive Hotkey Record Button (HELRCUS Style).
    Records modifier combinations (Ctrl+Alt+C, Alt+X, Ctrl+Shift+L) & mouse buttons.
    
    Component Name: CursorClampHotkeyButton
    """
    hotkeyChanged = Signal(str)
    recordingStarted = Signal()
    recordingStopped = Signal()

    def __init__(self, default_key: str = "Ctrl+Alt+C", parent=None):
        super().__init__(parent)
        self.setObjectName("CursorClampUnlockBtn")
        self._recording = False
        self._hotkey = default_key
        self.setText(default_key.upper())
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to record a new emergency unlock / toggle hotkey")
        self.clicked.connect(self._start_recording)
        self._update_style()

    def set_hotkey(self, key_str: str):
        self._hotkey = key_str
        self.setText(key_str.upper())
        self._recording = False
        self._update_style()

    def get_hotkey(self) -> str:
        return self._hotkey

    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #FF5B06;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 0px 10px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    min-height: 26px;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.16);
                    color: #FFFFFF;
                }
            """)

    def _start_recording(self):
        self._recording = True
        self.setText("Press key...")
        self._update_style()
        self.setFocus()
        self.recordingStarted.emit()

    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()

            # Cancel recording on Escape
            if key == Qt.Key_Escape:
                self._recording = False
                self.setText(self._hotkey.upper())
                self._update_style()
                self.recordingStopped.emit()
                event.accept()
                return

            # Wait for modifier-only keys
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                event.accept()
                return

            # Restrict Windows Key
            if (event.modifiers() & Qt.MetaModifier) or key in (Qt.Key_Meta, 0x5B, 0x5C):
                target_w = self.window() if self.window() else self
                FloatingToast.show_toast(target_w, "Restricted Key", "Windows Key is reserved by the OS")
                self._recording = False
                self.setText(self._hotkey.upper())
                self._update_style()
                self.recordingStopped.emit()
                event.accept()
                return

            # Build modifiers
            modifiers = []
            if event.modifiers() & Qt.ControlModifier:
                modifiers.append("Ctrl")
            if event.modifiers() & Qt.AltModifier:
                modifiers.append("Alt")
            if event.modifiers() & Qt.ShiftModifier:
                modifiers.append("Shift")

            # Determine key name
            key_name = ""
            if Qt.Key_F1 <= key <= Qt.Key_F12:
                key_name = f"F{key - Qt.Key_F1 + 1}"
            elif key == Qt.Key_Space:
                key_name = "Space"
            elif key == Qt.Key_Tab:
                key_name = "Tab"
            elif key == Qt.Key_CapsLock:
                key_name = "Caps Lock"
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                key_name = "Enter"
            elif key == Qt.Key_Backspace:
                key_name = "Backspace"
            elif key == Qt.Key_Delete:
                key_name = "Delete"
            else:
                txt = event.text().strip().upper()
                if txt and len(txt) == 1 and txt.isprintable():
                    key_name = txt
                else:
                    seq = QKeySequence(key).toString().strip()
                    if seq.startswith("Key "):
                        seq = seq[4:].strip()
                    key_name = seq or "C"

            full_key = "+".join(modifiers + [key_name]) if modifiers else key_name

            self._hotkey = full_key
            self.setText(full_key.upper())
            self._recording = False
            self._update_style()
            self.recordingStopped.emit()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._recording:
            btn = event.button()
            if btn == Qt.LeftButton:
                # Left click while recording commits nothing, ignores or cancels
                super().mousePressEvent(event)
                return

            modifiers = []
            if event.modifiers() & Qt.ControlModifier:
                modifiers.append("Ctrl")
            if event.modifiers() & Qt.AltModifier:
                modifiers.append("Alt")
            if event.modifiers() & Qt.ShiftModifier:
                modifiers.append("Shift")

            btn_name = "Right Click"
            if btn == Qt.RightButton:
                btn_name = "Right Click"
            elif btn == Qt.MiddleButton:
                btn_name = "Middle Click"
            elif btn in (Qt.BackButton, Qt.XButton1):
                btn_name = "Mouse 4"
            elif btn in (Qt.ForwardButton, Qt.XButton2):
                btn_name = "Mouse 5"

            full_key = "+".join(modifiers + [btn_name]) if modifiers else btn_name

            self._hotkey = full_key
            self.setText(full_key.upper())
            self._recording = False
            self._update_style()
            self.recordingStopped.emit()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self.setText(self._hotkey.upper())
            self._update_style()
            self.recordingStopped.emit()
        super().focusOutEvent(event)


class SlidingSegmentedPill(QWidget):
    """
    Smooth animated sliding pill segmented switcher (HELXAID signature style).
    Component Name: CursorClampModeTabFrame
    """
    modeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CursorClampModeTabFrame")
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self._current_mode = "primary_monitor"  # "primary_monitor" | "game_window"
        self._slide_progress = 0.0              # 0.0 = primary, 1.0 = game_window
        
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_mode(self, mode: str):
        if mode == self._current_mode:
            return
        self._current_mode = mode
        target = 1.0 if mode == "game_window" else 0.0
        
        if self._anim.state() == QVariantAnimation.Running:
            self._anim.stop()
        self._anim.setStartValue(self._slide_progress)
        self._anim.setEndValue(target)
        self._anim.start()
        self.modeChanged.emit(self._current_mode)

    def get_mode(self) -> str:
        return self._current_mode

    def _on_anim_step(self, value):
        self._slide_progress = float(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            click_x = event.position().x() if hasattr(event, 'position') else event.x()
            if click_x < (w / 2.0):
                self.set_mode("primary_monitor")
            else:
                self.set_mode("game_window")
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Dark container track
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 12)))
        p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)

        # 2. Calculate sliding pill geometry
        pad = 2.0
        pill_w = (w - (pad * 3.0)) / 2.0
        pill_h = h - (pad * 2.0)
        pill_x = pad + self._slide_progress * (pill_w + pad)
        pill_y = pad

        # 3. Draw sliding orange gradient pill
        gradient = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
        gradient.setColorAt(0.0, QColor("#FF5B06"))
        gradient.setColorAt(1.0, QColor("#FDA903"))

        p.setBrush(QBrush(gradient))
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

        # 4. Draw Tab Texts with smooth color interpolation
        p.setFont(QFont("Orbitron", 9, QFont.Bold))

        # Primary Display text color (Black when active, #888888 when unselected)
        r0 = int(0 + (136 - 0) * self._slide_progress)
        g0 = int(0 + (136 - 0) * self._slide_progress)
        b0 = int(0 + (136 - 0) * self._slide_progress)
        p.setPen(QColor(r0, g0, b0))
        left_rect = QRectF(pad, 0, pill_w, h)
        p.drawText(left_rect, Qt.AlignCenter, "PRIMARY DISPLAY")

        # Active Game Window text color (#888888 when unselected, Black when active)
        r1 = int(136 + (0 - 136) * self._slide_progress)
        g1 = int(136 + (0 - 136) * self._slide_progress)
        b1 = int(136 + (0 - 136) * self._slide_progress)
        p.setPen(QColor(r1, g1, b1))
        right_rect = QRectF(pad + pill_w + pad, 0, pill_w, h)
        p.drawText(right_rect, Qt.AlignCenter, "ACTIVE GAME WINDOW")


class CursorClampController(QObject):
    """
    Multi-Monitor Hardware-Enforced Cursor Clamping Engine.
    Uses Win32 user32.ClipCursor with zero-overhead focus & bounds tracking.
    
    Component Name: CursorClampController
    """
    clamp_state_changed = Signal(bool, str)   # (is_clamped, status_desc)
    cursor_pos_updated = Signal(int, int)     # (global_x, global_y)
    enabled_state_changed = Signal(bool)      # (is_enabled) for UI state synchronization

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CursorClampController")
        self.is_enabled = False
        self.is_clamped = False
        self.clamp_mode = "primary_monitor"   # "primary_monitor" | "game_window"
        self.auto_release_on_unfocus = True
        self.sound_enabled = True
        self.manual_override = False          # Temporary hotkey release
        self.trigger_key = "Ctrl+Alt+C"
        self._last_rect = None
        self._active_target_name = "Primary Screen"
        self._hotkey_last_state = False
        self._active_locked_hwnd = None
        self._active_locked_pid = None
        self._alt_tab_active = False
        
        # High-DPI Win32 Per-Monitor Awareness V2
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass

        # High-frequency watchdog timer (25ms = 40 Hz) - Always active for hotkey & radar updates
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(25)
        self._watchdog.timeout.connect(self._on_watchdog_tick)
        self._watchdog.start()

        # Emergency cleanup hook
        atexit.register(self.release_clamp)
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self.release_clamp)

    def set_trigger_key(self, key_name: str):
        self.trigger_key = key_name
        self._hotkey_last_state = True
        self._suppress_hotkey_ticks = 20  # Debounce suppression for ~500ms after recording

    def set_enabled(self, enabled: bool):
        self.is_enabled = bool(enabled)
        self.manual_override = False
        self._alt_tab_active = False
        if self.is_enabled:
            fg = ctypes.windll.user32.GetForegroundWindow()
            helxaid_pid = os.getpid()
            if fg:
                fg_root = ctypes.windll.user32.GetAncestor(fg, 2) or fg
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(fg_root, ctypes.byref(pid))
                if pid.value and pid.value != helxaid_pid:
                    self._active_locked_pid = pid.value
                    self._active_locked_hwnd = fg_root
                else:
                    self._active_locked_pid = None
                    self._active_locked_hwnd = None
            else:
                self._active_locked_pid = None
                self._active_locked_hwnd = None
            self._check_and_apply_clamp()
            if self.sound_enabled:
                self._play_sound(True)
        else:
            self.release_clamp()
            if self.sound_enabled:
                self._play_sound(False)
        self.enabled_state_changed.emit(self.is_enabled)

    def toggle_enable(self):
        """Toggle master clamp state."""
        self.set_enabled(not self.is_enabled)

    def emergency_unlock(self):
        """Instant full liberation: Disables clamp, resets state, and frees cursor across all monitors."""
        self.is_enabled = False
        self.manual_override = False
        self.release_clamp()
        self.enabled_state_changed.emit(False)
        self.clamp_state_changed.emit(False, "EMERGENCY UNLOCKED (FREE)")
        if self.sound_enabled:
            self._play_sound(False)

    def set_clamp_mode(self, mode: str):
        self.clamp_mode = mode
        if self.is_enabled:
            self._last_rect = None
            self._check_and_apply_clamp()

    def set_auto_release(self, auto_rel: bool):
        self.auto_release_on_unfocus = auto_rel

    def set_sound_enabled(self, enabled: bool):
        self.sound_enabled = enabled

    def toggle_manual_override(self):
        """Emergency / Temporary Toggle Hotkey Handler."""
        if not self.is_enabled:
            self.set_enabled(True)
            return

        self.manual_override = not self.manual_override
        if self.manual_override:
            self.release_clamp()
            self.clamp_state_changed.emit(False, "OVERRIDDEN (FREE)")
            if self.sound_enabled:
                self._play_sound(False)
        else:
            self._check_and_apply_clamp()
            if self.sound_enabled:
                self._play_sound(True)

    def _play_sound(self, locked: bool):
        try:
            import winsound
            if locked:
                winsound.Beep(1200, 80)
            else:
                winsound.Beep(600, 100)
        except Exception:
            try:
                if locked:
                    ctypes.windll.user32.MessageBeep(0x00000040)  # MB_ICONASTERISK
                else:
                    ctypes.windll.user32.MessageBeep(0x00000000)  # MB_OK
            except Exception:
                pass

    def _get_vk_code(self, key_name: str) -> int:
        raw = key_name.strip().lower()
        mapping = {
            "left click": 0x01,
            "mouse 1": 0x01,
            "right click": 0x02,
            "rclick": 0x02,
            "mouse 2": 0x02,
            "middle click": 0x04,
            "wheel": 0x04,
            "mouse 3": 0x04,
            "mouse 4": 0x05,
            "mouse button 4": 0x05,
            "mouse 5": 0x06,
            "mouse button 5": 0x06,
            "left alt": 0xA4,
            "right alt": 0xA5,
            "alt": 0x12,
            "left ctrl": 0xA2,
            "right ctrl": 0xA3,
            "ctrl": 0x11,
            "control": 0x11,
            "left shift": 0xA0,
            "right shift": 0xA1,
            "shift": 0x10,
            "space": 0x20,
            "spacebar": 0x20,
            "tab": 0x09,
            "caps lock": 0x14,
            "capslock": 0x14,
            "enter": 0x0D,
            "return": 0x0D,
            "backspace": 0x08,
            "delete": 0x2E,
            "insert": 0x2D,
        }
        for i in range(1, 13):
            mapping[f"f{i}"] = 0x70 + (i - 1)

        if raw in mapping:
            return mapping[raw]
        if len(raw) == 1:
            return ord(raw.upper())
        if raw.startswith("key ") or raw.startswith("key_"):
            char = raw.split()[-1]
            if len(char) == 1:
                return ord(char.upper())
        return 0

    def _is_hotkey_down(self) -> bool:
        if not self.trigger_key:
            return False
        parts = [p.strip().lower() for p in self.trigger_key.split('+') if p.strip()]
        if not parts:
            return False

        for part in parts:
            if part in ("ctrl", "control", "left ctrl", "right ctrl"):
                ctrl_down = bool((ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000) or
                                 (ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000) or
                                 (ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000))
                if not ctrl_down:
                    return False
            elif part in ("alt", "left alt", "right alt", "menu"):
                alt_down = bool((ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) or
                                (ctypes.windll.user32.GetAsyncKeyState(0xA4) & 0x8000) or
                                (ctypes.windll.user32.GetAsyncKeyState(0xA5) & 0x8000))
                if not alt_down:
                    return False
            elif part in ("shift", "left shift", "right shift"):
                shift_down = bool((ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000) or
                                  (ctypes.windll.user32.GetAsyncKeyState(0xA0) & 0x8000) or
                                  (ctypes.windll.user32.GetAsyncKeyState(0xA1) & 0x8000))
                if not shift_down:
                    return False
            else:
                vk = self._get_vk_code(part)
                if vk <= 0 or not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                    return False
        return True

    def _on_watchdog_tick(self):
        # 1. Continuous Global Hotkey Watcher
        self._check_global_hotkeys()

        # 2. Track global cursor position for Multi-Monitor HUD Radar
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            self.cursor_pos_updated.emit(pt.x, pt.y)

        # 3. Focus and boundary clamp check
        if self.is_enabled and not self.manual_override:
            self._check_and_apply_clamp()
        elif not self.is_enabled and self.is_clamped:
            self.release_clamp()

    def _check_global_hotkeys(self):
        try:
            if hasattr(self, '_suppress_hotkey_ticks') and self._suppress_hotkey_ticks > 0:
                self._suppress_hotkey_ticks -= 1
                self._hotkey_last_state = True
                return

            # Check user customized trigger chord
            trigger_down = self._is_hotkey_down()

            # Universal failsafe combo: Ctrl + Alt + C (Always active in background)
            failsafe_down = bool(
                ((ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000)) and
                ((ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0xA4) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0xA5) & 0x8000)) and
                (ctypes.windll.user32.GetAsyncKeyState(0x43) & 0x8000)
            )

            combo_down = trigger_down or failsafe_down

            if combo_down:
                if not self._hotkey_last_state:
                    self._hotkey_last_state = True
                    self.toggle_enable()
            else:
                self._hotkey_last_state = False
        except Exception:
            pass

    def _check_and_apply_clamp(self):
        if not self.is_enabled or self.manual_override:
            if self.is_clamped:
                self.release_clamp(reason="Disabled / Manual Override")
            return

        # 1. Resolve Foreground Root Window and Process ID (PID)
        raw_fg = ctypes.windll.user32.GetForegroundWindow()
        hwnd_fg = ctypes.windll.user32.GetAncestor(raw_fg, 2) if raw_fg else 0  # GA_ROOT = 2
        if not hwnd_fg:
            hwnd_fg = raw_fg

        fg_pid = wintypes.DWORD(0)
        if hwnd_fg:
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd_fg, ctypes.byref(fg_pid))
        pid_fg_val = fg_pid.value
        helxaid_pid = os.getpid()

        # 2. Check for Windows Shell / Start Menu / Taskbar / Task Switcher
        is_shell = False
        if hwnd_fg:
            class_name = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd_fg, class_name, 256)
            c_name = class_name.value.lower()
            SHELL_CLASSES = (
                "shell_traywnd", "progman", "workerw", "multitaskingviewframe",
                "taskswitcherwnd", "cortana", "windows.ui.core.corewindow",
                "xaml_windowed_popup_host", "launcherwindow", "immersivelauncher",
                "searchpanewindow", "shellexperiencehost", "startmenu", "applicationframewindow"
            )
            if c_name in SHELL_CLASSES or not c_name:
                is_shell = True

        # 3. Direct Physical Alt+Tab Chord Monitoring
        alt_down = bool((ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA4) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA5) & 0x8000))
        tab_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x09) & 0x8000)

        if self.auto_release_on_unfocus:
            if alt_down and tab_down:
                self._alt_tab_active = True
                if self.is_clamped:
                    self.release_clamp(reason="Alt+Tab Chord Pressed")
                    self.clamp_state_changed.emit(False, "PAUSED (ALT+TAB ACTIVE)")
                return

            if getattr(self, '_alt_tab_active', False):
                if alt_down or is_shell:
                    if self.is_clamped:
                        self.release_clamp(reason="Alt+Tab Menu Open")
                    return
                else:
                    self._alt_tab_active = False

        # 4. Release on OS Shell / Taskbar Focus
        if self.auto_release_on_unfocus and is_shell:
            if self.is_clamped:
                self.release_clamp(reason=f"OS Shell Window in Focus ({c_name})")
                self.clamp_state_changed.emit(False, "PAUSED (OS FOCUS)")
            return

        # 5. Adopt Target Game / Application Process when user switches away from HELXAID
        if pid_fg_val and pid_fg_val != helxaid_pid and not is_shell:
            if not self._active_locked_pid or self._active_locked_pid != pid_fg_val:
                title_buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd_fg, title_buf, 256)
                self._active_locked_pid = pid_fg_val
                self._active_locked_hwnd = hwnd_fg
                self._active_target_name = title_buf.value or f"App PID {pid_fg_val}"
                print(f"[CursorClamp-DEBUG] TARGET ADOPTED: {self._active_target_name} (PID: {pid_fg_val}, HWND: {hex(hwnd_fg)})")

        # 6. Lost Focus Check against the Target Process (PID Based)
        if self.auto_release_on_unfocus and self._active_locked_pid:
            if pid_fg_val == helxaid_pid:
                if self.is_clamped:
                    self.release_clamp(reason="HELXAID App in Focus")
                    self.clamp_state_changed.emit(False, "PAUSED (HELXAID CONFIG)")
                return

            if pid_fg_val and pid_fg_val != self._active_locked_pid:
                # User has switched focus to a different process (e.g. Chrome, Discord)
                if self.is_clamped:
                    title_buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(hwnd_fg, title_buf, 256)
                    switched_title = title_buf.value or "Other Process"
                    self.release_clamp(reason=f"Focus switched to {switched_title} (PID: {pid_fg_val})")
                    self.clamp_state_changed.emit(False, f"PAUSED (LOST FOCUS: {switched_title[:18]})")
                return

        # 7. Mode Boundary Calculation
        target_rect = None

        if self.clamp_mode == "primary_monitor":
            # Multi-Monitor Monitor Switch Check
            if self.auto_release_on_unfocus and hwnd_fg:
                hMon_fg = ctypes.windll.user32.MonitorFromWindow(hwnd_fg, 2)
                hMon_primary = ctypes.windll.user32.MonitorFromWindow(0, 1)
                if hMon_fg and hMon_primary and (hMon_fg != hMon_primary):
                    if self.is_clamped:
                        self.release_clamp(reason="Focus moved to Secondary Monitor")
                        self.clamp_state_changed.emit(False, "PAUSED (SECONDARY MONITOR FOCUS)")
                    return

            w = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
            h = ctypes.windll.user32.GetSystemMetrics(1)   # SM_CYSCREEN
            target_rect = Win32Rect(0, 0, w, h)
            self._active_target_name = f"Primary Monitor ({w}x{h})"

        elif self.clamp_mode == "game_window":
            target_hwnd = self._active_locked_hwnd or hwnd_fg
            if target_hwnd and pid_fg_val != helxaid_pid:
                r = Win32Rect()
                ctypes.windll.user32.GetWindowRect(target_hwnd, ctypes.byref(r))
                w = r.right - r.left
                h = r.bottom - r.top
                if w > 100 and h > 100:
                    target_rect = r
                    title_buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(target_hwnd, title_buf, 256)
                    self._active_target_name = title_buf.value or "Target Window"
                else:
                    target_rect = None

        if target_rect:
            rect_tuple = (target_rect.left, target_rect.top, target_rect.right, target_rect.bottom)
            if not self.is_clamped or self._last_rect != rect_tuple:
                self._apply_rect(target_rect)
        else:
            if self.is_clamped:
                self.release_clamp(reason="No valid target window in focus")
                self.clamp_state_changed.emit(False, "SEARCHING FOR TARGET")

    def _apply_rect(self, rect: Win32Rect):
        ctypes.windll.user32.ClipCursor(ctypes.byref(rect))
        self._last_rect = (rect.left, rect.top, rect.right, rect.bottom)
        self.is_clamped = True
        desc = f"LOCKED TO {self._active_target_name.upper()}"
        print(f"[CursorClamp-DEBUG] CLAMP APPLIED: {desc} -> Bounds=({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")
        self.clamp_state_changed.emit(True, desc)

    def release_clamp(self, reason="Manual"):
        ctypes.windll.user32.ClipCursor(None)
        self._last_rect = None
        if self.is_clamped:
            self.is_clamped = False
            print(f"[CursorClamp-DEBUG] CLAMP RELEASED: Reason={reason}")
            self.clamp_state_changed.emit(False, "UNLOCKED (FREE)")

    def force_restore(self):
        """Force cursor liberation and reset state."""
        self.emergency_unlock()

    def __del__(self):
        self.release_clamp()


class CursorClampCanvas(QWidget):
    """
    Live Multi-Monitor HUD Visualizer & Cursor Boundary Radar.
    Renders top-down virtual monitor geometry, active boundary lines, and live pointer tracking.
    
    Component Name: CursorClampCanvas
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CursorClampCanvas")
        self.setMinimumHeight(240)
        self.is_clamped = False
        self.status_text = "SYSTEM IDLE (FREE)"
        self.cursor_x = 0
        self.cursor_y = 0
        self._pulse_alpha = 200
        self._pulse_dir = -3
        self._hz_cache = {}
        
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._step_pulse)
        self._anim_timer.start()

    def _get_screen_max_hz(self, screen) -> int:
        s_name = screen.name() if screen else ""
        s_geom = screen.geometry() if screen else None
        key = (s_name, s_geom.width() if s_geom else 0, s_geom.height() if s_geom else 0)
        if key in self._hz_cache:
            return self._hz_cache[key]

        max_hz = 0
        try:
            class DEVMODEW(ctypes.Structure):
                _fields_ = [
                    ('dmDeviceName', wintypes.WCHAR * 32),
                    ('dmSpecVersion', wintypes.WORD),
                    ('dmDriverVersion', wintypes.WORD),
                    ('dmSize', wintypes.WORD),
                    ('dmDriverExtra', wintypes.WORD),
                    ('dmFields', wintypes.DWORD),
                    ('dmOrientation', ctypes.c_short),
                    ('dmPaperSize', ctypes.c_short),
                    ('dmPaperLength', ctypes.c_short),
                    ('dmPaperWidth', ctypes.c_short),
                    ('dmScale', ctypes.c_short),
                    ('dmCopies', ctypes.c_short),
                    ('dmDefaultSource', ctypes.c_short),
                    ('dmPrintQuality', ctypes.c_short),
                    ('dmColor', ctypes.c_short),
                    ('dmDuplex', ctypes.c_short),
                    ('dmYResolution', ctypes.c_short),
                    ('dmTTOption', ctypes.c_short),
                    ('dmCollate', ctypes.c_short),
                    ('dmFormName', wintypes.WCHAR * 32),
                    ('dmLogPixels', wintypes.WORD),
                    ('dmBitsPerPel', wintypes.DWORD),
                    ('dmPelsWidth', wintypes.DWORD),
                    ('dmPelsHeight', wintypes.DWORD),
                    ('dmDisplayFlags', wintypes.DWORD),
                    ('dmDisplayFrequency', wintypes.DWORD),
                    ('dmICMMethod', wintypes.DWORD),
                    ('dmICMIntent', wintypes.DWORD),
                    ('dmMediaType', wintypes.DWORD),
                    ('dmDitherType', wintypes.DWORD),
                    ('dmReserved1', wintypes.DWORD),
                    ('dmReserved2', wintypes.DWORD),
                    ('dmPanningWidth', wintypes.DWORD),
                    ('dmPanningHeight', wintypes.DWORD),
                ]
            dm = DEVMODEW()
            dm.dmSize = ctypes.sizeof(DEVMODEW)
            target_w = s_geom.width() if s_geom else 0
            target_h = s_geom.height() if s_geom else 0
            i = 0
            while ctypes.windll.user32.EnumDisplaySettingsW(s_name if s_name else None, i, ctypes.byref(dm)):
                if target_w and target_h:
                    if dm.dmPelsWidth == target_w and dm.dmPelsHeight == target_h:
                        if dm.dmDisplayFrequency > max_hz:
                            max_hz = dm.dmDisplayFrequency
                else:
                    if dm.dmDisplayFrequency > max_hz:
                        max_hz = dm.dmDisplayFrequency
                i += 1
        except Exception:
            max_hz = 0

        if max_hz <= 0 and screen:
            try:
                max_hz = int(round(screen.refreshRate()))
            except Exception:
                max_hz = 60

        self._hz_cache[key] = max_hz
        return max_hz

    def _step_pulse(self):
        if self.is_clamped:
            self._pulse_alpha += self._pulse_dir * 4
            if self._pulse_alpha <= 90:
                self._pulse_alpha = 90
                self._pulse_dir = 3
            elif self._pulse_alpha >= 230:
                self._pulse_alpha = 230
                self._pulse_dir = -3
            self.update()

    def set_clamp_state(self, is_clamped: bool, status_desc: str):
        self.is_clamped = is_clamped
        self.status_text = status_desc
        self.update()

    def set_cursor_pos(self, gx: int, gy: int):
        self.cursor_x = gx
        self.cursor_y = gy
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Background dark canvas
        bg_brush = QBrush(QColor("#111115"))
        painter.setBrush(bg_brush)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 10, 10)

        # 2. Subtle Tech Grid Pattern
        grid_pen = QPen(QColor(255, 255, 255, 8), 1, Qt.DotLine)
        painter.setPen(grid_pen)
        step = 32
        for x in range(0, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            painter.drawLine(0, y, w, y)

        # 3. Detect Connected Monitors
        screens = QApplication.screens()
        if not screens:
            screens = [QApplication.primaryScreen()]

        # Calculate bounding box of all screens in virtual coordinate space
        min_x = min(s.geometry().left() for s in screens)
        min_y = min(s.geometry().top() for s in screens)
        max_x = max(s.geometry().right() for s in screens)
        max_y = max(s.geometry().bottom() for s in screens)

        virt_w = max(1, max_x - min_x)
        virt_h = max(1, max_y - min_y)

        # Usable canvas region with generous padding
        pad_x = 40
        pad_y = 50
        draw_area_w = w - (pad_x * 2)
        draw_area_h = h - (pad_y * 2) - 20

        scale = min(draw_area_w / virt_w, draw_area_h / virt_h) * 0.88
        offset_x = (w - (virt_w * scale)) / 2.0
        offset_y = ((h - 20) - (virt_h * scale)) / 2.0 + 15

        primary_screen = QApplication.primaryScreen()

        # 4. Render Monitor Rectangles
        for idx, screen in enumerate(screens):
            s_geom = screen.geometry()
            sx = offset_x + (s_geom.left() - min_x) * scale
            sy = offset_y + (s_geom.top() - min_y) * scale
            sw = s_geom.width() * scale
            sh = s_geom.height() * scale

            is_primary = (screen == primary_screen)

            if is_primary:
                if self.is_clamped:
                    # Electric Neon Orange Clamped Boundary
                    m_bg = QColor(255, 91, 6, 22)
                    border_color = QColor(255, 91, 6, self._pulse_alpha)
                    border_w = 2.5
                else:
                    m_bg = QColor(255, 255, 255, 12)
                    border_color = QColor("#FF5B06")
                    border_w = 1.5
            else:
                # Secondary Monitor
                m_bg = QColor(255, 255, 255, 4)
                border_color = QColor(255, 255, 255, 35)
                border_w = 1.0

            # Draw monitor body
            painter.setBrush(QBrush(m_bg))
            painter.setPen(QPen(border_color, border_w))
            painter.drawRoundedRect(QRectF(sx, sy, sw, sh), 8, 8)

            # Draw L-Corner Tech Brackets for Primary Monitor
            if is_primary:
                corner_pen = QPen(QColor("#FF5B06"), 2.0)
                painter.setPen(corner_pen)
                b_len = min(12.0, sw * 0.15)
                # Top-Left
                painter.drawLine(QPointF(sx, sy), QPointF(sx + b_len, sy))
                painter.drawLine(QPointF(sx, sy), QPointF(sx, sy + b_len))
                # Top-Right
                painter.drawLine(QPointF(sx + sw, sy), QPointF(sx + sw - b_len, sy))
                painter.drawLine(QPointF(sx + sw, sy), QPointF(sx + sw, sy + b_len))
                # Bottom-Left
                painter.drawLine(QPointF(sx, sy + sh), QPointF(sx + b_len, sy + sh))
                painter.drawLine(QPointF(sx, sy + sh), QPointF(sx, sy + sh - b_len))
                # Bottom-Right
                painter.drawLine(QPointF(sx + sw, sy + sh), QPointF(sx + sw - b_len, sy + sh))
                painter.drawLine(QPointF(sx + sw, sy + sh), QPointF(sx + sw, sy + sh - b_len))

            # Monitor Label
            painter.setFont(QFont("Orbitron", 9, QFont.Bold))
            tag_color = QColor("#FF5B06") if is_primary else QColor("#888888")
            painter.setPen(QPen(tag_color))
            tag_text = f"DISPLAY {idx+1} (PRIMARY)" if is_primary else f"DISPLAY {idx+1}"
            painter.drawText(QRectF(sx, sy + 10, sw, 20), Qt.AlignCenter, tag_text)

            # Maximum Supported Hardware Refresh Rate from Win32
            hz = self._get_screen_max_hz(screen)
            painter.setFont(QFont("Orbitron", 8))
            painter.setPen(QPen(QColor("#AAAAAA")))
            res_text = f"{s_geom.width()}x{s_geom.height()} @ {hz}Hz"
            painter.drawText(QRectF(sx, sy + 30, sw, 20), Qt.AlignCenter, res_text)

            # Lock badge inside primary display
            if is_primary:
                badge_text = "[ HARDWARE CLAMP LOCKED ]" if self.is_clamped else "[ UNLOCKED / FREE ]"
                badge_color = QColor("#00FF88") if self.is_clamped else QColor("#777777")
                painter.setFont(QFont("Orbitron", 8, QFont.Bold))
                painter.setPen(QPen(badge_color))
                painter.drawText(QRectF(sx, sy + sh - 28, sw, 20), Qt.AlignCenter, badge_text)

        # 5. Live Cursor Pointer Target Crosshair
        cx = offset_x + (self.cursor_x - min_x) * scale
        cy = offset_y + (self.cursor_y - min_y) * scale

        # Draw glowing dot
        dot_color = QColor("#00FF88") if self.is_clamped else QColor("#00E5FF")
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)

        # Outer Reticle Ring
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(dot_color, 1.2, Qt.DashLine))
        painter.drawEllipse(QPointF(cx, cy), 11.0, 11.0)

        # 6. Bottom HUD Coordinates Bar
        hud_bg = QColor(0, 0, 0, 120)
        painter.setBrush(QBrush(hud_bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(15, h - 34, w - 30, 24), 6, 6)

        painter.setFont(QFont("Orbitron", 8, QFont.Bold))
        status_color = QColor("#00FF88") if self.is_clamped else QColor("#FF5B06")
        painter.setPen(QPen(status_color))
        hud_left = f"STATUS: {self.status_text}"
        painter.drawText(QRectF(25, h - 34, w * 0.6, 24), Qt.AlignVCenter | Qt.AlignLeft, hud_left)

        painter.setPen(QPen(QColor("#888888")))
        hud_right = f"VIRTUAL CURSOR: X={self.cursor_x}, Y={self.cursor_y} | MONITORS: {len(screens)}"
        painter.drawText(QRectF(w * 0.4, h - 34, w * 0.6 - 25, 24), Qt.AlignVCenter | Qt.AlignRight, hud_right)


class CursorClampPanel(QWidget):
    """
    Multi-Monitor Cursor Clamp Configuration & Calibration Panel.
    Component Name: CursorClampPanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CursorClampPanel")
        self.controller = CursorClampController(self)
        self._guide_panel = None
        self._setup_ui()
        self.controller.enabled_state_changed.connect(self._sync_active_ui)
        self._sync_active_ui(False)


    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("CursorClampHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#CursorClampHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(8)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("CursorClampBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Tactical Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#CursorClampBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#CursorClampBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self._on_back)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("MULTI-MONITOR CURSOR CLAMP")
        title_lbl.setObjectName("CursorClampHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        # Standalone "Emergency Unlock:" text label (HELRCUS Style)
        self.unlock_lbl = QLabel("Emergency Unlock:")
        self.unlock_lbl.setObjectName("CursorClampUnlockLabel")
        self.unlock_lbl.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        h_layout.addWidget(self.unlock_lbl)

        # Customizable Hotkey Button (HELRCUS Style pill box)
        self.unlock_btn = CursorClampHotkeyButton(default_key="Ctrl+Alt+C")
        self.unlock_btn.setObjectName("CursorClampUnlockBtn")
        self.unlock_btn.setFixedWidth(140)
        self.unlock_btn.hotkeyChanged.connect(self._on_hotkey_changed)
        h_layout.addWidget(self.unlock_btn)

        # Disarm Button (Instant Liberation)
        self.disarm_btn = QPushButton("DISARM")
        self.disarm_btn.setObjectName("CursorClampDisarmBtn")
        self.disarm_btn.setFixedSize(70, 26)
        self.disarm_btn.setCursor(Qt.PointingHandCursor)
        self.disarm_btn.setToolTip("Immediately disarms and liberates cursor confinement across all monitors")
        self.disarm_btn.setStyleSheet("""
            QPushButton#CursorClampDisarmBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0px 6px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#CursorClampDisarmBtn:hover {
                background-color: rgba(255, 91, 6, 0.35);
                color: #FFFFFF;
            }
        """)
        self.disarm_btn.clicked.connect(self.controller.emergency_unlock)
        h_layout.addWidget(self.disarm_btn)

        self.enable_btn = QPushButton("DISABLED")
        self.enable_btn.setObjectName("CursorClampEnableBtn")
        self.enable_btn.setFixedSize(90, 26)
        self.enable_btn.setCursor(Qt.PointingHandCursor)
        self.enable_btn.setStyleSheet("""
            QPushButton#CursorClampEnableBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #888888;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0px 8px;
                min-height: 26px;
                max-height: 26px;
            }
        """)
        self.enable_btn.clicked.connect(self._toggle_enable)
        h_layout.addWidget(self.enable_btn)

        main_layout.addWidget(header_frame)

        # ── 2. CONFIGURATION CARDS (2 COLUMNS) ─────────────────
        cfg_layout = QHBoxLayout()
        cfg_layout.setSpacing(12)

        # Card 1: Target Clamp Region Selection
        mode_card = QFrame()
        mode_card.setObjectName("CursorClampModeCard")
        mode_card.setFixedHeight(96)
        mode_card.setStyleSheet("""
            QFrame#CursorClampModeCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        mc_layout = QVBoxLayout(mode_card)
        mc_layout.setContentsMargins(12, 12, 12, 12)
        mc_layout.setSpacing(6)

        mc_title = QLabel("TARGET LOCK BOUNDARY")
        mc_title.setObjectName("CursorClampModeTitle")
        mc_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        mc_layout.addWidget(mc_title)

        self.mode_switcher = SlidingSegmentedPill()
        self.mode_switcher.setObjectName("CursorClampModeTabFrame")
        self.mode_switcher.modeChanged.connect(self.controller.set_clamp_mode)
        mc_layout.addWidget(self.mode_switcher)

        mc_layout.addSpacing(2)

        self.cb_autorel = AnimatedCheckBox("Auto-Release on Alt+Tab / Lost Focus")
        self.cb_autorel.setObjectName("CursorClampAutoReleaseCb")
        self.cb_autorel.setChecked(True)
        self.cb_autorel.toggled.connect(self._on_autorel_toggled)
        self.cb_autorel.clicked.connect(lambda: self._on_autorel_toggled(self.cb_autorel.isChecked()))
        mc_layout.addWidget(self.cb_autorel)

        cfg_layout.addWidget(mode_card, 1)

        # Card 2: Hotkey & Audio Feedback
        hotkey_card = QFrame()
        hotkey_card.setObjectName("CursorClampHotkeyCard")
        hotkey_card.setFixedHeight(96)
        hotkey_card.setStyleSheet("""
            QFrame#CursorClampHotkeyCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        hc_layout = QVBoxLayout(hotkey_card)
        hc_layout.setContentsMargins(12, 10, 12, 10)
        hc_layout.setSpacing(6)

        hc_title = QLabel("ACTIVATION & EMERGENCY UNLOCK HOTKEY")
        hc_title.setObjectName("CursorClampHotkeyTitle")
        hc_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        hc_layout.addWidget(hc_title)

        hc_row = QHBoxLayout()
        hc_row.setSpacing(8)

        # Synchronized Custom Key Input in Card 2
        self.custom_key_input = CursorClampHotkeyButton(default_key="Ctrl+Alt+C")
        self.custom_key_input.setObjectName("CursorClampCustomKeyInput")
        self.custom_key_input.setFixedHeight(28)
        self.custom_key_input.hotkeyChanged.connect(self._on_hotkey_changed)
        hc_row.addWidget(self.custom_key_input, 1)

        self.cb_sound = AnimatedCheckBox("Audible Tone")
        self.cb_sound.setObjectName("CursorClampSoundCb")
        self.cb_sound.setChecked(True)
        self.cb_sound.setToolTip("Plays notification chime upon cursor lock/unlock")
        self.cb_sound.toggled.connect(self.controller.set_sound_enabled)
        hc_row.addWidget(self.cb_sound)

        hc_layout.addLayout(hc_row)

        hc_desc = QLabel("Press your custom hotkey or Ctrl+Alt+C in-game to instantly toggle cursor lock.")
        hc_desc.setObjectName("CursorClampHotkeyDesc")
        hc_desc.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 9px;")
        hc_layout.addWidget(hc_desc)

        cfg_layout.addWidget(hotkey_card, 1)
        main_layout.addLayout(cfg_layout)

        # ── 3. LIVE MULTI-MONITOR RADAR CANVAS ─────────────────
        self.clamp_canvas = CursorClampCanvas()
        self.clamp_canvas.setObjectName("CursorClampCanvas")
        self.controller.clamp_state_changed.connect(self.clamp_canvas.set_clamp_state)
        self.controller.cursor_pos_updated.connect(self.clamp_canvas.set_cursor_pos)
        main_layout.addWidget(self.clamp_canvas, 1)

    def _on_autorel_toggled(self, checked: bool):
        self.controller.set_auto_release(checked)
        print(f"[CursorClamp] Auto-Release on Alt+Tab set to: {checked}")

    def _on_hotkey_changed(self, key_name: str):
        self.controller.set_trigger_key(key_name)
        if hasattr(self, 'unlock_btn') and self.unlock_btn.get_hotkey() != key_name:
            self.unlock_btn.set_hotkey(key_name)
        if hasattr(self, 'custom_key_input') and self.custom_key_input.get_hotkey() != key_name:
            self.custom_key_input.set_hotkey(key_name)
        print(f"[CursorClamp] Activation Hotkey set to: {key_name}")

    def _toggle_enable(self):
        self.controller.toggle_enable()

    def _sync_active_ui(self, active: bool):
        if active:
            self.enable_btn.setText("ACTIVE")
            self.enable_btn.setStyleSheet("""
                QPushButton#CursorClampEnableBtn {
                    background-color: #00FF88;
                    color: #000000;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.enable_btn.setText("DISABLED")
            self.enable_btn.setStyleSheet("""
                QPushButton#CursorClampEnableBtn {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #888888;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)

    def _on_back(self):
        self.controller.force_restore()
        self.back_clicked.emit()


# =====================================================================
# ── TACTICAL TOOLS SUITE: FEATURE 3 — UNIVERSAL RAPID-FIRE & BURST ───
# =====================================================================

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class SlidingSegmentedPill3(QWidget):
    """
    Smooth 3-segment animated sliding pill switcher.
    Component Name: RapidFireModeTabFrame
    """
    modeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireModeTabFrame")
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self._current_mode = "continuous"  # "continuous" | "burst_3" | "burst_5"
        self._slide_progress = 0.0          # 0.0 = continuous, 0.5 = burst_3, 1.0 = burst_5

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_mode(self, mode: str):
        if mode == self._current_mode:
            return
        self._current_mode = mode
        if mode == "burst_3":
            target = 0.5
        elif mode == "burst_5":
            target = 1.0
        else:
            target = 0.0

        if self._anim.state() == QVariantAnimation.Running:
            self._anim.stop()
        self._anim.setStartValue(self._slide_progress)
        self._anim.setEndValue(target)
        self._anim.start()
        self.modeChanged.emit(self._current_mode)

    def get_mode(self) -> str:
        return self._current_mode

    def _on_anim_step(self, value):
        self._slide_progress = float(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            click_x = event.position().x() if hasattr(event, 'position') else event.x()
            if click_x < (w / 3.0):
                self.set_mode("continuous")
            elif click_x < (2.0 * w / 3.0):
                self.set_mode("burst_3")
            else:
                self.set_mode("burst_5")
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Container track
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 12)))
        p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)

        # 2. Sliding pill geometry (3 segments)
        pad = 2.0
        pill_w = (w - (pad * 4.0)) / 3.0
        pill_h = h - (pad * 2.0)
        pill_x = pad + self._slide_progress * 2.0 * (pill_w + pad)
        pill_y = pad

        # 3. Sliding gradient pill
        gradient = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
        gradient.setColorAt(0.0, QColor("#FF5B06"))
        gradient.setColorAt(1.0, QColor("#FDA903"))

        p.setBrush(QBrush(gradient))
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

        # 4. Text labels with smooth color transition
        p.setFont(QFont("Orbitron", 8, QFont.Bold))

        # Zone 0: FULL-AUTO (Active at progress 0.0)
        dist0 = min(1.0, abs(self._slide_progress - 0.0) * 2.0)
        c0 = int(0 + (136 - 0) * dist0)
        p.setPen(QColor(c0, c0, c0))
        r0 = QRectF(pad, 0, pill_w, h)
        p.drawText(r0, Qt.AlignCenter, "FULL-AUTO")

        # Zone 1: 3-BURST (Active at progress 0.5)
        dist1 = min(1.0, abs(self._slide_progress - 0.5) * 2.0)
        c1 = int(0 + (136 - 0) * dist1)
        p.setPen(QColor(c1, c1, c1))
        r1 = QRectF(pad + (pill_w + pad), 0, pill_w, h)
        p.drawText(r1, Qt.AlignCenter, "3-BURST")

        # Zone 2: 5-BURST (Active at progress 1.0)
        dist2 = min(1.0, abs(self._slide_progress - 1.0) * 2.0)
        c2 = int(0 + (136 - 0) * dist2)
        p.setPen(QColor(c2, c2, c2))
        r2 = QRectF(pad + (pill_w + pad) * 2.0, 0, pill_w, h)
        p.drawText(r2, Qt.AlignCenter, "5-BURST")


class SlidingSegmentedPillTriggerType(QWidget):
    """
    Smooth 2-segment animated sliding pill switcher for Trigger Activation Type (Hold vs Single Click).
    Component Name: RapidFireTriggerTypeFrame
    """
    triggerTypeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireTriggerTypeFrame")
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self._current_type = "hold"  # "hold" | "single_click"
        self._slide_progress = 0.0   # 0.0 = hold, 1.0 = single_click

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_trigger_type(self, t_type: str):
        if t_type == self._current_type:
            return
        self._current_type = t_type
        target_val = 1.0 if t_type == "single_click" else 0.0

        if self._anim.state() == QVariantAnimation.Running:
            self._anim.stop()
        self._anim.setStartValue(self._slide_progress)
        self._anim.setEndValue(target_val)
        self._anim.start()
        self.triggerTypeChanged.emit(self._current_type)

    def get_trigger_type(self) -> str:
        return self._current_type

    def _on_anim_step(self, value):
        self._slide_progress = float(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            click_x = event.position().x() if hasattr(event, 'position') else event.x()
            if click_x < (w / 2.0):
                self.set_trigger_type("hold")
            else:
                self.set_trigger_type("single_click")
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Container track
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 12)))
        p.drawRoundedRect(QRectF(0, 0, w, h), 5, 5)

        # 2. Sliding pill geometry
        pad = 2.0
        pill_w = (w - (pad * 3.0)) / 2.0
        pill_h = h - (pad * 2.0)
        pill_x = pad + self._slide_progress * (pill_w + pad)
        pill_y = pad

        # 3. Sliding gradient pill
        gradient = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
        gradient.setColorAt(0.0, QColor("#FF5B06"))
        gradient.setColorAt(1.0, QColor("#FDA903"))

        p.setBrush(QBrush(gradient))
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

        # 4. Text labels
        p.setFont(QFont("Orbitron", 8, QFont.Bold))

        r0 = int(0 + (136 - 0) * self._slide_progress)
        p.setPen(QColor(r0, r0, r0))
        left_rect = QRectF(pad, 0, pill_w, h)
        p.drawText(left_rect, Qt.AlignCenter, "HOLD (PRESS)")

        r1 = int(136 + (0 - 136) * self._slide_progress)
        p.setPen(QColor(r1, r1, r1))
        right_rect = QRectF(pad + pill_w + pad, 0, pill_w, h)
        p.drawText(right_rect, Qt.AlignCenter, "SINGLE CLICK (TOGGLE)")


class SlidingSegmentedPillTarget(QWidget):
    """
    Smooth 2-segment animated sliding pill switcher for Target Button.
    Component Name: RapidFireTargetTabFrame
    """
    targetChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireTargetTabFrame")
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self._current_target = "left"  # "left" | "right"
        self._slide_progress = 0.0     # 0.0 = left, 1.0 = right

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_target(self, target_btn: str):
        if target_btn == self._current_target:
            return
        self._current_target = target_btn
        target_val = 1.0 if target_btn == "right" else 0.0

        if self._anim.state() == QVariantAnimation.Running:
            self._anim.stop()
        self._anim.setStartValue(self._slide_progress)
        self._anim.setEndValue(target_val)
        self._anim.start()
        self.targetChanged.emit(self._current_target)

    def get_target(self) -> str:
        return self._current_target

    def _on_anim_step(self, value):
        self._slide_progress = float(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            click_x = event.position().x() if hasattr(event, 'position') else event.x()
            if click_x < (w / 2.0):
                self.set_target("left")
            else:
                self.set_target("right")
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Container track
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 12)))
        p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)

        # 2. Sliding pill geometry
        pad = 2.0
        pill_w = (w - (pad * 3.0)) / 2.0
        pill_h = h - (pad * 2.0)
        pill_x = pad + self._slide_progress * (pill_w + pad)
        pill_y = pad

        # 3. Sliding gradient pill
        gradient = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
        gradient.setColorAt(0.0, QColor("#FF5B06"))
        gradient.setColorAt(1.0, QColor("#FDA903"))

        p.setBrush(QBrush(gradient))
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

        # 4. Text labels
        p.setFont(QFont("Orbitron", 8, QFont.Bold))

        r0 = int(0 + (136 - 0) * self._slide_progress)
        p.setPen(QColor(r0, r0, r0))
        left_rect = QRectF(pad, 0, pill_w, h)
        p.drawText(left_rect, Qt.AlignCenter, "LEFT CLICK (M1)")

        r1 = int(136 + (0 - 136) * self._slide_progress)
        p.setPen(QColor(r1, r1, r1))
        right_rect = QRectF(pad + pill_w + pad, 0, pill_w, h)
        p.drawText(right_rect, Qt.AlignCenter, "RIGHT CLICK (M2)")


class SlidingSegmentedPillSpeedPresets(QWidget):
    """
    Cadence Speed Quick-Preset Pill Switcher (10, 18, 25, 35 CPS).
    Component Name: RapidFireSpeedPresetTabFrame
    """
    presetSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireSpeedPresetTabFrame")
        self.setFixedHeight(24)
        self.setCursor(Qt.PointingHandCursor)
        self._presets = [10, 18, 25, 35]
        self._labels = ["10 TAP", "18 MED", "25 FAST", "35 MAX"]
        self._current_index = 1  # 18 CPS default
        self._slide_progress = 1.0 / 3.0
        self._pill_alpha = 1.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_preset_from_val(self, val: int):
        if val in self._presets:
            idx = self._presets.index(val)
            self._current_index = idx
            target = idx / 3.0
            self._pill_alpha = 1.0
            if self._anim.state() == QVariantAnimation.Running:
                self._anim.stop()
            self._anim.setStartValue(self._slide_progress)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._current_index = -1
            self._pill_alpha = 0.35
            self.update()

    def set_index(self, idx: int):
        if 0 <= idx < len(self._presets):
            self._current_index = idx
            target = idx / 3.0
            self._pill_alpha = 1.0
            if self._anim.state() == QVariantAnimation.Running:
                self._anim.stop()
            self._anim.setStartValue(self._slide_progress)
            self._anim.setEndValue(target)
            self._anim.start()
            self.presetSelected.emit(self._presets[idx])

    def _on_anim_step(self, value):
        self._slide_progress = float(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            click_x = event.position().x() if hasattr(event, 'position') else event.x()
            idx = int(click_x / (w / 4.0))
            idx = max(0, min(3, idx))
            self.set_index(idx)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Background Track
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 10)))
        p.drawRoundedRect(QRectF(0, 0, w, h), 5, 5)

        # 2. Sliding Gradient Pill
        pad = 2.0
        pill_w = (w - (pad * 5.0)) / 4.0
        pill_h = h - (pad * 2.0)
        pill_x = pad + self._slide_progress * 3.0 * (pill_w + pad)
        pill_y = pad

        if self._pill_alpha > 0.05:
            gradient = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
            gradient.setColorAt(0.0, QColor(255, 91, 6, int(255 * self._pill_alpha)))
            gradient.setColorAt(1.0, QColor(253, 169, 3, int(255 * self._pill_alpha)))
            p.setBrush(QBrush(gradient))
            p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

        # 3. Text Labels
        p.setFont(QFont("Orbitron", 7, QFont.Bold))
        for i, text in enumerate(self._labels):
            target_p = i / 3.0
            dist = min(1.0, abs(self._slide_progress - target_p) * 3.0)
            if self._current_index == i:
                c = int(0 + (140 - 0) * dist)
            else:
                c = 140
            p.setPen(QColor(c, c, c))
            rx = pad + i * (pill_w + pad)
            p.drawText(QRectF(rx, 0, pill_w, h), Qt.AlignCenter, text)


class RapidFireHotkeyButton(QPushButton):
    """
    Interactive Hotkey Binding Button for Rapid Fire Arming / Toggle.
    Component Name: RapidFireHotkeyBtn
    """
    hotkeyChanged = Signal(str)
    recordingStarted = Signal()
    recordingStopped = Signal()

    def __init__(self, default_key="F8", parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireHotkeyBtn")
        self._hotkey = default_key
        self._recording = False
        self.setText(self._hotkey.upper())
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_style()
        self.clicked.connect(self._toggle_recording)

    def set_hotkey(self, key_str: str):
        self._hotkey = key_str
        self.setText(key_str.upper())
        self._recording = False
        self._update_style()

    def get_hotkey(self) -> str:
        return self._hotkey

    def _toggle_recording(self):
        self._recording = not self._recording
        if self._recording:
            self.setText("[ PRESS ANY KEY... ]")
            self._update_style()
            self.setFocus()
            self.recordingStarted.emit()
        else:
            self.setText(self._hotkey.upper())
            self._update_style()
            self.recordingStopped.emit()

    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton#RapidFireHotkeyBtn {
                    background-color: #1e2128;
                    color: #FF5B06;
                    border: 1px solid #FF5B06;
                    border-radius: 6px;
                    padding: 0px 8px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    text-align: center;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton#RapidFireHotkeyBtn {
                    background-color: #1e2128;
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 6px;
                    padding: 0px 8px;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    text-align: center;
                    min-height: 26px;
                    max-height: 26px;
                }
                QPushButton#RapidFireHotkeyBtn:hover {
                    background-color: #1e2128;
                    border: 1px solid #FF5B06;
                    color: #FF5B06;
                }
            """)

    def keyPressEvent(self, event):
        if self._recording:
            key = event.key()
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                return

            modifiers = []
            if event.modifiers() & Qt.ControlModifier:
                modifiers.append("Ctrl")
            if event.modifiers() & Qt.AltModifier:
                modifiers.append("Alt")
            if event.modifiers() & Qt.ShiftModifier:
                modifiers.append("Shift")

            if key == Qt.Key_Escape:
                self._recording = False
                self.setText(self._hotkey.upper())
                self._update_style()
                self.recordingStopped.emit()
                event.accept()
                return

            if Qt.Key_F1 <= key <= Qt.Key_F12:
                key_name = f"F{key - Qt.Key_F1 + 1}"
            elif key == Qt.Key_Space:
                key_name = "Space"
            elif key == Qt.Key_Tab:
                key_name = "Tab"
            elif key == Qt.Key_CapsLock:
                key_name = "CapsLock"
            elif key == Qt.Key_Return or key == Qt.Key_Enter:
                key_name = "Enter"
            elif key == Qt.Key_Backspace:
                key_name = "Backspace"
            else:
                txt = event.text().strip().upper()
                if txt and len(txt) == 1 and txt.isprintable():
                    key_name = txt
                else:
                    seq = QKeySequence(key).toString().strip()
                    if seq.startswith("Key "):
                        seq = seq[4:].strip()
                    key_name = seq or "F8"

            full_key = "+".join(modifiers + [key_name]) if modifiers else key_name
            self._hotkey = full_key
            self.setText(full_key.upper())
            self._recording = False
            self._update_style()
            self.recordingStopped.emit()
            self.hotkeyChanged.emit(full_key)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self.setText(self._hotkey.upper())
            self._update_style()
            self.recordingStopped.emit()
        super().focusOutEvent(event)


RAPID_FIRE_EXTRA_INFO = 0x48454C58  # 'HELX'


class LowLevelRapidFireHook(QThread):
    """
    Dedicated Win32 Low-Level Mouse Hook Thread with Message Pump.
    Filters synthetic RapidFire clicks and dispatches physical mouse events globally across PC/Games.
    Component Name: LowLevelRapidFireHook
    """
    button_event_signal = Signal(str, bool)  # (button_name, is_pressed)

    def __init__(self):
        super().__init__()
        self.setObjectName("LowLevelRapidFireHook")
        self._hook_id = None
        self._user32 = ctypes.windll.user32
        self._pointer = CMPFUNC(self._hook_callback)
        self._thread_id = None
        self.is_running = True

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0 and lParam:
            try:
                struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                extra = int(struct.dwExtraInfo or 0)
                is_synthetic = (extra == RAPID_FIRE_EXTRA_INFO) or bool(struct.flags & 1)

                if not is_synthetic:
                    btn_name = None
                    is_pressed = None

                    if wParam == WM_LBUTTONDOWN:
                        btn_name, is_pressed = "left click", True
                    elif wParam == WM_LBUTTONUP:
                        btn_name, is_pressed = "left click", False
                    elif wParam == WM_RBUTTONDOWN:
                        btn_name, is_pressed = "right click", True
                    elif wParam == WM_RBUTTONUP:
                        btn_name, is_pressed = "right click", False
                    elif wParam == WM_MBUTTONDOWN:
                        btn_name, is_pressed = "middle click", True
                    elif wParam == WM_MBUTTONUP:
                        btn_name, is_pressed = "middle click", False
                    elif wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                        high_word = (struct.mouseData >> 16) & 0xFFFF
                        btn_name = "mouse 4" if high_word == 1 else "mouse 5"
                        is_pressed = (wParam == WM_XBUTTONDOWN)

                    if btn_name is not None:
                        self.button_event_signal.emit(btn_name, is_pressed)
            except Exception:
                pass

        return self._user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def run(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._hook_id = self._user32.SetWindowsHookExW(14, self._pointer, None, 0)
        if not self._hook_id:
            print("[RapidFireHook] Failed to install WH_MOUSE_LL hook")
            return

        print("[RapidFireHook] WH_MOUSE_LL hook installed and pumping messages globally")
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
        print("[RapidFireHook] WH_MOUSE_LL hook uninstalled cleanly")

    def stop(self):
        self.is_running = False
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        self.wait(200)


class RapidFireWorker(QThread):
    """
    Sub-millisecond High-Precision Click Dispatch Engine with Auto-Chained Burst Fire.
    Component Name: RapidFireWorker
    """
    shotFired = Signal(int, float)      # (shot_index, instantaneous_cps)
    firingStateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireWorker")
        self.is_firing = False
        self.target_cps = 18.0
        self.mode = "continuous"  # "continuous" | "burst_3" | "burst_5"
        self.trigger_type = "hold"  # "hold" | "single_click"
        self.burst_delay_ms = 200
        self.humanize_jitter = True
        self.target_button = "left"  # "left" | "right"
        self._stop_requested = False
        self._total_shots_fired = 0

    def configure(self, target_cps: float, mode: str, humanize: bool, target_button: str, burst_delay_ms: int = 200, trigger_type: str = "hold"):
        self.target_cps = max(5.0, min(35.0, float(target_cps)))
        self.mode = mode
        self.humanize_jitter = bool(humanize)
        self.target_button = target_button
        self.burst_delay_ms = max(50, min(1000, int(burst_delay_ms)))
        self.trigger_type = trigger_type

    def stop_firing(self):
        self._stop_requested = True

    def run(self):
        self.is_firing = True
        self._stop_requested = False
        self.firingStateChanged.emit(True)

        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

        down_flag = MOUSEEVENTF_LEFTDOWN if self.target_button == "left" else MOUSEEVENTF_RIGHTDOWN
        up_flag = MOUSEEVENTF_LEFTUP if self.target_button == "left" else MOUSEEVENTF_RIGHTUP

        is_burst = self.mode in ("burst_3", "burst_5")
        burst_size = 3 if self.mode == "burst_3" else (5 if self.mode == "burst_5" else 99999999)
        total_shot_count = 0
        last_shot_time = time.perf_counter()

        try:
            while not self._stop_requested:
                # ── 1. FIRE ONE BURST (OR CONTINUOUS CYCLE) ──
                current_burst_shots = 0
                while not self._stop_requested and current_burst_shots < burst_size:
                    base_period = 1.0 / max(5.0, min(35.0, self.target_cps))

                    # Humanized Hold Duration
                    base_hold = min(0.014, base_period * 0.4)
                    hold_time = base_hold
                    if self.humanize_jitter:
                        jitter = random.gauss(0, base_hold * 0.15)
                        hold_time = max(0.006, min(base_period * 0.6, base_hold + jitter))

                    # Atomic DOWN with RAPID_FIRE_EXTRA_INFO signature
                    ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, RAPID_FIRE_EXTRA_INFO)

                    t_end = time.perf_counter() + hold_time
                    while time.perf_counter() < t_end:
                        time.sleep(0.0005)

                    # Atomic UP with RAPID_FIRE_EXTRA_INFO signature (guaranteed release)
                    ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, RAPID_FIRE_EXTRA_INFO)
                    current_burst_shots += 1
                    total_shot_count += 1
                    self._total_shots_fired += 1

                    now = time.perf_counter()
                    interval = now - last_shot_time
                    instant_cps = (1.0 / interval) if (interval > 0.001 and total_shot_count > 1) else self.target_cps
                    last_shot_time = now
                    self.shotFired.emit(total_shot_count, instant_cps)

                    if self._stop_requested or current_burst_shots >= burst_size:
                        break

                    # Release interval between bullets inside the same burst
                    base_rest = max(0.008, base_period - hold_time)
                    rest_time = base_rest
                    if self.humanize_jitter:
                        jitter = random.gauss(0, base_rest * 0.15)
                        rest_time = max(0.006, base_rest + jitter)

                    t_rest_end = time.perf_counter() + rest_time
                    while time.perf_counter() < t_rest_end:
                        if self._stop_requested:
                            break
                        time.sleep(0.0005)

                # ── 2. POST-BURST HANDLING ──
                if self._stop_requested:
                    break

                if is_burst:
                    if self.trigger_type == "single_click":
                        # Single tap fires only 1 burst cycle then stops
                        break
                    else:
                        # Hold mode: Pause for Burst Repeat Delay then fire next burst!
                        base_delay = self.burst_delay_ms / 1000.0
                        actual_delay = base_delay
                        if self.humanize_jitter:
                            delay_jitter = random.gauss(0, base_delay * 0.10)
                            actual_delay = max(0.020, base_delay + delay_jitter)

                        t_delay_end = time.perf_counter() + actual_delay
                        while time.perf_counter() < t_delay_end:
                            if self._stop_requested:
                                break
                            time.sleep(0.0005)

        finally:
            try:
                ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, RAPID_FIRE_EXTRA_INFO)
            except Exception:
                pass
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
            self.is_firing = False
            self.firingStateChanged.emit(False)


class RapidFireController(QObject):
    """
    Rapid-Fire Master Engine & Global Physical Mouse Hook Coordinator.
    Component Name: RapidFireController
    """
    state_changed = Signal(bool, str)       # (is_active, status_desc)
    shot_dispatched = Signal(int, float)    # (shot_count, instant_cps)
    enabled_state_changed = Signal(bool)    # (is_enabled)
    stats_reset = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireController")
        self.is_enabled = False
        self.target_cps = 18.0
        self.mode = "continuous"            # "continuous" | "burst_3" | "burst_5"
        self.trigger_type = "hold"          # "hold" | "single_click"
        self.burst_delay_ms = 200
        self.humanize_jitter = True
        self.target_button = "left"        # "left" | "right"
        self.trigger_key = "Left Click"
        self.toggle_hotkey = "F8"
        self.sound_enabled = True

        self._last_kb_trigger_state = False
        self._last_toggle_state = False
        self._suppress_ticks = 0
        self._burst_fired_for_press = False

        self._worker = RapidFireWorker(self)
        self._worker.shotFired.connect(self._on_worker_shot)
        self._worker.firingStateChanged.connect(self._on_firing_state_changed)

        # Start Dedicated Low-Level Mouse Hook Thread (WH_MOUSE_LL with Message Loop)
        self._mouse_hook = LowLevelRapidFireHook()
        self._mouse_hook.button_event_signal.connect(self._on_physical_button_event)
        self._mouse_hook.start()

        # Watchdog for toggle hotkey and keyboard trigger keys (15ms ~ 66Hz)
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(15)
        self._watchdog.timeout.connect(self._on_watchdog_tick)
        self._watchdog.start()

        atexit.register(self.force_restore)
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self.force_restore)

    def _on_physical_button_event(self, btn: str, is_down: bool):
        if not self.is_enabled:
            return

        cur_trigger = self.trigger_key.strip().lower()
        match = (cur_trigger == btn) or (cur_trigger.replace("click", "").strip() == btn.replace("click", "").strip())
        if match:
            if self.trigger_type == "hold":
                # Standard Hold Mode (fires continuously or auto-repeats bursts)
                if is_down:
                    if not self._worker.isRunning():
                        self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                        self._worker.start()
                else:
                    if self._worker.isRunning():
                        self._worker.stop_firing()
            else:
                # Single Click / Tap-to-Toggle Mode
                if is_down:
                    if self.mode in ("burst_3", "burst_5"):
                        if self._worker.isRunning():
                            self._worker.stop_firing()
                            self._worker.wait(50)
                        self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                        self._worker.start()
                    else:
                        if self._worker.isRunning():
                            self._worker.stop_firing()
                        else:
                            self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                            self._worker.start()

    def _on_worker_shot(self, count, cps):
        self.shot_dispatched.emit(count, cps)

    def _on_firing_state_changed(self, active):
        if active:
            self.state_changed.emit(True, "RAPID FIRING ENGAGED")
        else:
            status = "ARMED (STANDBY)" if self.is_enabled else "DISARMED (DISABLED)"
            self.state_changed.emit(self.is_enabled, status)

    def set_enabled(self, enabled: bool):
        self.is_enabled = bool(enabled)
        if not self.is_enabled and self._worker.isRunning():
            self._worker.stop_firing()
        if self.sound_enabled:
            self._play_sound(self.is_enabled)
        self.enabled_state_changed.emit(self.is_enabled)
        status = "ARMED (STANDBY)" if self.is_enabled else "DISARMED (DISABLED)"
        self.state_changed.emit(self.is_enabled, status)

    def toggle_enable(self):
        self.set_enabled(not self.is_enabled)

    def set_target_cps(self, cps: float):
        self.target_cps = max(5.0, min(35.0, float(cps)))

    def set_mode(self, mode: str):
        self.mode = mode

    def set_trigger_type(self, trigger_type: str):
        self.trigger_type = trigger_type
        if self._worker.isRunning():
            self._worker.stop_firing()

    def set_burst_delay_ms(self, delay_ms: int):
        self.burst_delay_ms = max(50, min(1000, int(delay_ms)))

    def set_humanize_jitter(self, enable: bool):
        self.humanize_jitter = bool(enable)

    def set_target_button(self, btn: str):
        self.target_button = btn

    def set_trigger_key(self, key_name: str):
        self.trigger_key = key_name
        self._last_kb_trigger_state = True
        self._suppress_ticks = 15

    def set_toggle_hotkey(self, key_name: str):
        self.toggle_hotkey = key_name
        self._last_toggle_state = True
        self._suppress_ticks = 15

    def set_sound_enabled(self, enabled: bool):
        self.sound_enabled = bool(enabled)

    def force_restore(self):
        if hasattr(self, '_mouse_hook') and self._mouse_hook:
            self._mouse_hook.stop()
        if self._worker.isRunning():
            self._worker.stop_firing()
            self._worker.wait(150)
        try:
            up_flag = MOUSEEVENTF_LEFTUP if self.target_button == "left" else MOUSEEVENTF_RIGHTUP
            ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, RAPID_FIRE_EXTRA_INFO)
        except Exception:
            pass

    def _play_sound(self, armed: bool):
        try:
            import winsound
            if armed:
                winsound.Beep(1100, 70)
            else:
                winsound.Beep(450, 90)
        except Exception:
            try:
                if armed:
                    ctypes.windll.user32.MessageBeep(0x00000040)
                else:
                    ctypes.windll.user32.MessageBeep(0x00000000)
            except Exception:
                pass

    def _get_vk_code(self, key_name: str) -> int:
        raw = key_name.strip().lower()
        mapping = {
            "left click": 0x01, "mouse 1": 0x01, "mouse 1 (m1)": 0x01,
            "right click": 0x02, "rclick": 0x02, "mouse 2": 0x02, "mouse 2 (m2)": 0x02,
            "middle click": 0x04, "wheel": 0x04, "mouse 3": 0x04,
            "mouse 4": 0x05, "mouse button 4": 0x05, "xbutton1": 0x05,
            "mouse 5": 0x06, "mouse button 5": 0x06, "xbutton2": 0x06,
            "left alt": 0xA4, "right alt": 0xA5, "alt": 0x12,
            "left ctrl": 0xA2, "right ctrl": 0xA3, "ctrl": 0x11, "control": 0x11,
            "left shift": 0xA0, "right shift": 0xA1, "shift": 0x10,
            "space": 0x20, "spacebar": 0x20, "tab": 0x09, "caps lock": 0x14,
            "capslock": 0x14, "enter": 0x0D, "return": 0x0D, "backspace": 0x08,
            "delete": 0x2E, "insert": 0x2D,
        }
        for i in range(1, 13):
            mapping[f"f{i}"] = 0x70 + (i - 1)

        if raw in mapping:
            return mapping[raw]
        if len(raw) == 1:
            return ord(raw.upper())
        if raw.startswith("key ") or raw.startswith("key_"):
            char = raw.split()[-1]
            if len(char) == 1:
                return ord(char.upper())
        return 0

    def _is_hotkey_down(self, hotkey_str: str) -> bool:
        if not hotkey_str:
            return False
        parts = [p.strip().lower() for p in hotkey_str.split('+') if p.strip()]
        if not parts:
            return False

        for part in parts:
            if part in ("ctrl", "control", "left ctrl", "right ctrl"):
                if not ((ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000)):
                    return False
            elif part in ("alt", "left alt", "right alt", "menu"):
                if not ((ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA4) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA5) & 0x8000)):
                    return False
            elif part in ("shift", "left shift", "right shift"):
                if not ((ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA0) & 0x8000) or
                        (ctypes.windll.user32.GetAsyncKeyState(0xA1) & 0x8000)):
                    return False
            else:
                vk = self._get_vk_code(part)
                if vk > 0:
                    if not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                        return False
                else:
                    return False
        return True

    def _on_watchdog_tick(self):
        if self._suppress_ticks > 0:
            self._suppress_ticks -= 1
            return

        # 1. Check Toggle Arming Hotkey
        toggle_down = self._is_hotkey_down(self.toggle_hotkey)
        if toggle_down and not self._last_toggle_state:
            self.toggle_enable()
        self._last_toggle_state = toggle_down

        # 2. Check Keyboard Trigger Keys (only if trigger is NOT a mouse button)
        if not self.is_enabled:
            return

        raw_trig = self.trigger_key.strip().lower()
        is_mouse_trig = any(m in raw_trig for m in ("left click", "right click", "middle click", "mouse 4", "mouse 5", "mouse 1", "mouse 2", "mouse 3"))

        if not is_mouse_trig:
            kb_down = self._is_hotkey_down(self.trigger_key)
            if kb_down and not self._last_kb_trigger_state:
                if self.trigger_type == "hold":
                    if not self._worker.isRunning():
                        self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                        self._worker.start()
                else:
                    if self.mode in ("burst_3", "burst_5"):
                        if self._worker.isRunning():
                            self._worker.stop_firing()
                            self._worker.wait(50)
                        self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                        self._worker.start()
                    else:
                        if self._worker.isRunning():
                            self._worker.stop_firing()
                        else:
                            self._worker.configure(self.target_cps, self.mode, self.humanize_jitter, self.target_button, self.burst_delay_ms, self.trigger_type)
                            self._worker.start()

            elif not kb_down and self._last_kb_trigger_state:
                if self.trigger_type == "hold":
                    if self._worker.isRunning():
                        self._worker.stop_firing()

            self._last_kb_trigger_state = kb_down


class RapidFireTargetCanvas(QWidget):
    """
    Interactive Live Target Practice Range, Cadence Radar & Dynamic Burst Rhythm Visualizer.
    Component Name: RapidFireTargetCanvas
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RapidFireTargetCanvas")
        self.setMinimumHeight(240)
        self.setCursor(Qt.CrossCursor)

        self._engine_enabled = False
        self._is_firing_active = False
        self._status_text = "DISARMED (DISABLED)"
        self._current_instant_cps = 0.0
        self._target_cps = 18.0
        self._mode = "continuous"
        self._humanize_jitter = True
        self._total_shots = 0
        self._hits_in_bullseye = 0
        self._decals = []
        self._jitter_history = collections.deque(maxlen=35)
        self._muzzle_flash_alpha = 0.0
        self._recoil_offset_y = 0.0
        self._flash_center_x = None
        self._flash_center_y = None

        # Burst Rhythm Animation States
        self._burst_shot_in_cycle = 0
        self._burst_cooldown_progress = 0.0
        self._burst_cooldown_start = 0.0

        # Animation timer (40 FPS = 25ms)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(25)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

    def set_engine_enabled(self, enabled: bool):
        self._engine_enabled = bool(enabled)
        if not self._engine_enabled:
            self._is_firing_active = False
            self._status_text = "DISARMED (DISABLED)"
        else:
            self._status_text = "ARMED (STANDBY)"
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        self._burst_shot_in_cycle = 0
        self._burst_cooldown_progress = 0.0
        self._burst_cooldown_start = 0.0
        self.update()

    def set_humanize_jitter(self, enable: bool):
        self._humanize_jitter = bool(enable)

    def set_target_cps(self, cps: float):
        self._target_cps = max(5.0, min(35.0, float(cps)))

    def set_firing_state(self, is_active: bool, desc: str):
        self._is_firing_active = is_active
        self._status_text = desc
        if not is_active:
            self._burst_shot_in_cycle = 0
        self.update()

    def record_shot(self, count: int, cps: float):
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        self.record_shot_at(cx, cy, count, cps)

    def record_shot_at(self, x: float, y: float, count: int, cps: float):
        self._total_shots += 1
        self._current_instant_cps = cps
        self._muzzle_flash_alpha = 1.0
        self._flash_center_x = x
        self._flash_center_y = y
        self._recoil_offset_y = max(-14.0, self._recoil_offset_y - 4.0)

        # Dynamic Burst Pip & Cooldown Tracking
        burst_size = 3 if self._mode == "burst_3" else (5 if self._mode == "burst_5" else 0)
        if burst_size > 0:
            self._burst_shot_in_cycle = (self._burst_shot_in_cycle % burst_size) + 1
            if self._burst_shot_in_cycle == burst_size:
                self._burst_cooldown_start = time.perf_counter()
                self._burst_cooldown_progress = 1.0

        expected_interval_ms = (1000.0 / max(1.0, self._target_cps))
        actual_interval_ms = (1000.0 / max(1.0, cps)) if cps > 0 else expected_interval_ms
        delta_ms = actual_interval_ms - expected_interval_ms
        self._jitter_history.append(delta_ms)

        spread = max(5.0, min(30.0, (self._target_cps / 35.0) * 25.0))
        gx = random.gauss(0, spread)
        gy = random.gauss(0, spread) + self._recoil_offset_y * 0.4
        hit_x = x + gx
        hit_y = y + gy

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dist_to_center = math.hypot(hit_x - cx, hit_y - cy)
        score = 10 if dist_to_center < 18 else (9 if dist_to_center < 42 else (8 if dist_to_center < 70 else 7))
        if score == 10:
            self._hits_in_bullseye += 1

        self._decals.append({
            'x': hit_x,
            'y': hit_y,
            'time': time.perf_counter(),
            'score': score,
            'alpha': 1.0
        })

        if len(self._decals) > 120:
            self._decals.pop(0)

        self.update()

    def clear_target(self):
        self._decals.clear()
        self._total_shots = 0
        self._hits_in_bullseye = 0
        self._jitter_history.clear()
        self._current_instant_cps = 0.0
        self._burst_shot_in_cycle = 0
        self._burst_cooldown_progress = 0.0
        self._burst_cooldown_start = 0.0
        self.update()

    def _on_anim_tick(self):
        now = time.perf_counter()
        if self._muzzle_flash_alpha > 0.01:
            self._muzzle_flash_alpha *= 0.72
        else:
            self._muzzle_flash_alpha = 0.0

        if abs(self._recoil_offset_y) > 0.1:
            self._recoil_offset_y *= 0.82
        else:
            self._recoil_offset_y = 0.0

        # Burst Cooldown Dynamic Progress Decay
        if self._burst_cooldown_start > 0.0:
            elapsed = now - self._burst_cooldown_start
            if elapsed < 0.28:
                self._burst_cooldown_progress = max(0.0, 1.0 - (elapsed / 0.28))
            else:
                self._burst_cooldown_start = 0.0
                self._burst_cooldown_progress = 0.0

        alive_decals = []
        for d in self._decals:
            age = now - d['time']
            if age < 15.0:
                d['alpha'] = max(0.2, 1.0 - (age / 15.0))
                alive_decals.append(d)
        self._decals = alive_decals

        if not self._is_firing_active and self._current_instant_cps > 0.1:
            self._current_instant_cps *= 0.90
            if self._current_instant_cps < 0.1:
                self._current_instant_cps = 0.0

        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.width()
            pos = event.position() if hasattr(event, 'position') else event.pos()
            if pos.x() > (w - 120) and pos.y() < 45:
                self.clear_target()
                return

            if not self._engine_enabled:
                self._status_text = "DISARMED (ENABLE FIRST)"
                self.update()
                return

        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        # 1. Tactical dark background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#0d1015")))
        p.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)

        # 2. Tactical Grid Lines
        p.setPen(QPen(QColor(255, 255, 255, 8), 1, Qt.DotLine))
        grid_step = 30
        x = cx % grid_step
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += grid_step
        y = cy % grid_step
        while y < h:
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += grid_step

        # 3. Concentric Target Rings
        rings = [
            (140, QColor(255, 255, 255, 14), 1, "7"),
            (100, QColor(255, 255, 255, 22), 1, "8"),
            (65,  QColor(255, 255, 255, 35), 1, "9"),
            (32,  QColor(255, 91, 6, 80),   2, "10"),
            (12,  QColor(255, 91, 6, 180),  2, "X"),
        ]

        for radius, color, pen_w, label in rings:
            p.setPen(QPen(color, pen_w))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)
            if radius > 15:
                p.setFont(QFont("Orbitron", 7))
                p.setPen(QPen(QColor(255, 255, 255, 40)))
                p.drawText(QRectF(cx - 15, cy - radius - 10, 30, 10), Qt.AlignCenter, label)

        # 4. Crosshair Reticle Lines with Recoil Offset
        recoil_cy = cy + self._recoil_offset_y
        p.setPen(QPen(QColor(255, 91, 6, 140), 1))
        p.drawLine(QPointF(cx - 160, recoil_cy), QPointF(cx - 18, recoil_cy))
        p.drawLine(QPointF(cx + 18, recoil_cy), QPointF(cx + 160, recoil_cy))
        p.drawLine(QPointF(cx, recoil_cy - 120), QPointF(cx, recoil_cy - 18))
        p.drawLine(QPointF(cx, recoil_cy + 18), QPointF(cx, recoil_cy + 120))

        # Center bullseye glow
        bullseye_grad = QRadialGradient(cx, recoil_cy, 14)
        bullseye_grad.setColorAt(0.0, QColor(255, 91, 6, 180))
        bullseye_grad.setColorAt(1.0, QColor(255, 91, 6, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bullseye_grad))
        p.drawEllipse(QPointF(cx, recoil_cy), 14, 14)

        # 5. Muzzle Flash Pulse (at shot position or center)
        if self._muzzle_flash_alpha > 0.02:
            fx = self._flash_center_x if self._flash_center_x is not None else cx
            fy = (self._flash_center_y if self._flash_center_y is not None else cy) + self._recoil_offset_y
            flash_rad = 36 * (1.0 + (1.0 - self._muzzle_flash_alpha))
            flash_grad = QRadialGradient(fx, fy, flash_rad)
            alpha_int = int(255 * self._muzzle_flash_alpha)
            flash_grad.setColorAt(0.0, QColor(255, 230, 120, alpha_int))
            flash_grad.setColorAt(0.5, QColor(255, 91, 6, int(alpha_int * 0.7)))
            flash_grad.setColorAt(1.0, QColor(255, 91, 6, 0))
            p.setBrush(QBrush(flash_grad))
            p.drawEllipse(QPointF(fx, fy), flash_rad, flash_rad)

        # 6. Bullet Decals
        for d in self._decals:
            alpha = d['alpha']
            dx = d['x']
            dy = d['y']
            score = d['score']
            r = 4.5 if score == 10 else 3.5

            glow = QRadialGradient(dx, dy, r * 2.2)
            glow.setColorAt(0.0, QColor(255, 200, 60, int(220 * alpha)))
            glow.setColorAt(0.4, QColor(255, 91, 6, int(160 * alpha)))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(dx, dy), r * 2.2, r * 2.2)

            p.setBrush(QBrush(QColor(20, 20, 20, int(240 * alpha))))
            p.setPen(QPen(QColor(255, 91, 6, int(180 * alpha)), 1))
            p.drawEllipse(QPointF(dx, dy), r, r)

        # 7. TOP-LEFT HUD: CPS SPEEDOMETER GAUGE
        gauge_x = 20
        gauge_y = 20
        gauge_w = 110
        gauge_h = 75
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 100)))
        p.drawRoundedRect(QRectF(gauge_x, gauge_y, gauge_w, gauge_h), 6, 6)

        arc_rect = QRectF(gauge_x + 15, gauge_y + 8, 80, 80)
        p.setPen(QPen(QColor(255, 255, 255, 20), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 30 * 16, 210 * 16)

        pct = min(1.0, self._current_instant_cps / 40.0)
        p.setPen(QPen(QColor("#FF5B06"), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 240 * 16, int(-210 * 16 * pct))

        p.setFont(QFont("Orbitron", 11, QFont.Bold))
        p.setPen(QColor("#FF5B06") if self._current_instant_cps > 0 else QColor("#888888"))
        cps_str = f"{self._current_instant_cps:.1f}" if self._current_instant_cps > 0 else f"{self._target_cps:.0f}"
        p.drawText(QRectF(gauge_x, gauge_y + 36, gauge_w, 16), Qt.AlignCenter, f"{cps_str} CPS")

        p.setFont(QFont("Orbitron", 7))
        p.setPen(QColor("#888888"))
        p.drawText(QRectF(gauge_x, gauge_y + 54, gauge_w, 12), Qt.AlignCenter, "REAL-TIME SPEED")

        # 8. TOP-CENTER HUD: BURST CYCLE CADENCE & PIPS (Dynamic Animation)
        if self._mode in ("burst_3", "burst_5"):
            burst_cap = 3 if self._mode == "burst_3" else 5
            mode_title = "3-BURST CYCLE" if self._mode == "burst_3" else "5-BURST CYCLE"
            hud_w = 136
            hud_h = 36
            hud_x = cx - (hud_w / 2.0)
            hud_y = 16

            # Container Background & Subtle Border
            p.setPen(QPen(QColor(255, 255, 255, 15), 1))
            p.setBrush(QBrush(QColor(0, 0, 0, 140)))
            p.drawRoundedRect(QRectF(hud_x, hud_y, hud_w, hud_h), 6, 6)

            # Title Label with balanced top padding
            p.setFont(QFont("Orbitron", 7, QFont.Bold))
            p.setPen(QColor("#E0E0E0"))
            p.drawText(QRectF(hud_x, hud_y + 5, hud_w, 11), Qt.AlignCenter, mode_title)

            # Draw Bullet Pips (centered vertically with balanced bottom padding)
            pip_spacing = 15
            start_px = hud_x + (hud_w / 2.0) - ((burst_cap - 1) * pip_spacing / 2.0)
            pip_y = hud_y + 23.5

            for i in range(burst_cap):
                px = start_px + (i * pip_spacing)
                is_fired = (i < self._burst_shot_in_cycle)
                
                if is_fired:
                    pip_grad = QRadialGradient(px, pip_y, 5)
                    pip_grad.setColorAt(0.0, QColor("#FF5B06"))
                    pip_grad.setColorAt(1.0, QColor(255, 91, 6, 90))
                    p.setBrush(QBrush(pip_grad))
                    p.setPen(QPen(QColor("#FFFFFF"), 1))
                else:
                    p.setBrush(QBrush(QColor(255, 255, 255, 18)))
                    p.setPen(QPen(QColor(255, 255, 255, 35), 1))
                p.drawEllipse(QPointF(px, pip_y), 3.5, 3.5)

            # Draw Cooldown Progress Line during inter-burst delay
            if self._burst_cooldown_progress > 0.01:
                bar_w = hud_w - 20
                bar_x = hud_x + 10
                bar_y = hud_y + hud_h - 3.5
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 20)))
                p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, 2), 1, 1)

                fill_w = bar_w * (1.0 - self._burst_cooldown_progress)
                p.setBrush(QBrush(QColor("#FF5B06")))
                p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, 2), 1, 1)

        # 9. BOTTOM-LEFT HUD: HUMANIZATION JITTER OSCILLOSCOPE
        if len(self._jitter_history) > 1:
            scope_x = 20
            scope_y = h - 65
            scope_w = 140
            scope_h = 45
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 100)))
            p.drawRoundedRect(QRectF(scope_x, scope_y, scope_w, scope_h), 6, 6)

            p.setFont(QFont("Orbitron", 7, QFont.Bold))
            p.setPen(QColor("#00FF88"))
            p.drawText(QRectF(scope_x + 8, scope_y + 4, scope_w, 10), Qt.AlignLeft, "JITTER OSCILLOSCOPE")

            mid_y = scope_y + 28
            p.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
            p.drawLine(QPointF(scope_x + 8, mid_y), QPointF(scope_x + scope_w - 8, mid_y))

            p.setPen(QPen(QColor("#00FF88"), 1.5))
            pts = list(self._jitter_history)
            step = (scope_w - 16) / max(1, len(pts) - 1)
            for i in range(len(pts) - 1):
                y1 = mid_y - max(-14.0, min(14.0, pts[i] * 1.5))
                y2 = mid_y - max(-14.0, min(14.0, pts[i+1] * 1.5))
                p.drawLine(QPointF(scope_x + 8 + i * step, y1), QPointF(scope_x + 8 + (i + 1) * step, y2))

        # 10. TOP-RIGHT HUD: ACCURACY & SHOTS STATS + CLEAR BUTTON
        stat_w = 120
        stat_h = 60
        stat_x = w - stat_w - 15
        stat_y = 15
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 100)))
        p.drawRoundedRect(QRectF(stat_x, stat_y, stat_w, stat_h), 6, 6)

        p.setFont(QFont("Orbitron", 8, QFont.Bold))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(stat_x + 8, stat_y + 6, stat_w - 16, 14), Qt.AlignLeft, f"SHOTS: {self._total_shots}")

        acc = int((self._hits_in_bullseye / max(1, self._total_shots)) * 100)
        p.setPen(QColor("#FF5B06"))
        p.drawText(QRectF(stat_x + 8, stat_y + 22, stat_w - 16, 14), Qt.AlignLeft, f"BULLSEYE: {acc}%")

        btn_rect = QRectF(stat_x + 8, stat_y + 38, stat_w - 16, 16)
        p.setBrush(QBrush(QColor(255, 91, 6, 40)))
        p.setPen(QPen(QColor(255, 91, 6, 120), 1))
        p.drawRoundedRect(btn_rect, 3, 3)
        p.setFont(QFont("Orbitron", 7, QFont.Bold))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(btn_rect, Qt.AlignCenter, "CLEAR TARGET")

        # 11. BOTTOM-RIGHT HUD: STATUS BADGE
        badge_w = 200
        badge_h = 24
        badge_x = w - badge_w - 15
        badge_y = h - badge_h - 15
        p.setPen(Qt.NoPen)
        if self._is_firing_active:
            bg_col = QColor(0, 255, 136, 35)
            txt_col = QColor("#00FF88")
        elif self._engine_enabled:
            bg_col = QColor(255, 91, 6, 30)
            txt_col = QColor("#FF5B06")
        else:
            bg_col = QColor(255, 255, 255, 10)
            txt_col = QColor("#777777")

        p.setBrush(QBrush(bg_col))
        p.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 5, 5)

        p.setFont(QFont("Orbitron", 8, QFont.Bold))
        p.setPen(txt_col)
        p.drawText(QRectF(badge_x, badge_y, badge_w, badge_h), Qt.AlignCenter, self._status_text)


class RapidFirePanel(QWidget):
    """
    Universal Rapid-Fire & Dynamic Burst Engine Sub-Panel (Tactical Hub Sub-Page 3).
    Component Name: TacticalRapidFirePanel
    """
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TacticalRapidFirePanel")
        self.controller = RapidFireController(self)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(14)

        # ── 1. HEADER BAR ──────────────────────────────────────
        header_frame = QWidget()
        header_frame.setObjectName("RapidFireHeaderFrame")
        header_frame.setFixedHeight(40)
        header_frame.setStyleSheet("""
            QWidget#RapidFireHeaderFrame {
                background-color: rgba(26, 26, 26, 0.95);
                border: none;
                border-radius: 8px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 0, 10, 0)
        h_layout.setSpacing(8)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("RapidFireBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Tactical Hub")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#RapidFireBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#RapidFireBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.back_clicked)
        h_layout.addWidget(self.back_btn)

        title_lbl = QLabel("UNIVERSAL RAPID-FIRE & DYNAMIC BURST")
        title_lbl.setObjectName("RapidFireHeaderTitle")
        title_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        self.enable_btn = QPushButton("DISABLED")
        self.enable_btn.setObjectName("RapidFireEnableBtn")
        self.enable_btn.setFixedSize(90, 26)
        self.enable_btn.setCursor(Qt.PointingHandCursor)
        self.enable_btn.setStyleSheet("""
            QPushButton#RapidFireEnableBtn {
                background-color: rgba(255, 255, 255, 0.08);
                color: #888888;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0px 8px;
                min-height: 26px;
                max-height: 26px;
            }
        """)
        self.enable_btn.clicked.connect(self.controller.toggle_enable)
        self.controller.enabled_state_changed.connect(self._sync_enable_ui)
        h_layout.addWidget(self.enable_btn)

        main_layout.addWidget(header_frame)

        # ── 2. CONFIGURATION CARDS ROW (3 CARDS) ───────────────
        cfg_layout = QHBoxLayout()
        cfg_layout.setSpacing(12)

        # CARD 1: FIRING MODE & TARGET DISPATCH
        self.card1 = QFrame()
        self.card1.setObjectName("RapidFireModeCard")
        self.card1.setFixedHeight(132)
        self.card1.setStyleSheet("""
            QFrame#RapidFireModeCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        c1_layout = QVBoxLayout(self.card1)
        c1_layout.setContentsMargins(12, 8, 12, 8)
        c1_layout.setSpacing(4)

        c1_title = QLabel("FIRING MODE & TARGET DISPATCH")
        c1_title.setObjectName("RapidFireModeCardTitle")
        c1_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        c1_layout.addWidget(c1_title)

        self.mode_switcher = SlidingSegmentedPill3()
        self.mode_switcher.setObjectName("RapidFireModeTabFrame")
        self.mode_switcher.modeChanged.connect(self._on_mode_changed)
        c1_layout.addWidget(self.mode_switcher)

        # BURST REPEAT DELAY SUB-FRAME (Dynamic visibility: appears above trigger_type_switcher when Burst + Hold)
        self.burst_delay_frame = QFrame()
        self.burst_delay_frame.setObjectName("RapidFireBurstDelayFrame")
        self.burst_delay_frame.setStyleSheet("""
            QFrame#RapidFireBurstDelayFrame {
                background: transparent;
                border: none;
            }
        """)
        bdf_layout = QVBoxLayout(self.burst_delay_frame)
        bdf_layout.setContentsMargins(0, 2, 0, 2)
        bdf_layout.setSpacing(2)

        bdf_head = QHBoxLayout()
        bdf_title = QLabel("BURST REPEAT DELAY")
        bdf_title.setObjectName("RapidFireBurstDelayTitle")
        bdf_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold;")
        bdf_head.addWidget(bdf_title)
        bdf_head.addStretch()

        self.burst_delay_val_lbl = QLabel("200 ms")
        self.burst_delay_val_lbl.setObjectName("RapidFireBurstDelayValLabel")
        self.burst_delay_val_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold;")
        bdf_head.addWidget(self.burst_delay_val_lbl)
        bdf_layout.addLayout(bdf_head)

        self.burst_delay_slider = QSlider(Qt.Horizontal)
        self.burst_delay_slider.setObjectName("RapidFireBurstDelaySlider")
        self.burst_delay_slider.setRange(50, 1000)
        self.burst_delay_slider.setValue(200)
        self.burst_delay_slider.setStyleSheet("""
            QSlider#RapidFireBurstDelaySlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            QSlider#RapidFireBurstDelaySlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 2px;
            }
            QSlider#RapidFireBurstDelaySlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #FF5B06;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
        """)
        self.burst_delay_slider.valueChanged.connect(self._on_burst_delay_changed)
        bdf_layout.addWidget(self.burst_delay_slider)
        c1_layout.addWidget(self.burst_delay_frame)

        # Dynamic Opacity Effect for Burst Delay Frame
        self._burst_opacity_effect = QGraphicsOpacityEffect(self.burst_delay_frame)
        self.burst_delay_frame.setGraphicsEffect(self._burst_opacity_effect)
        self._burst_opacity_effect.setOpacity(0.0)

        self.trigger_type_switcher = SlidingSegmentedPillTriggerType()
        self.trigger_type_switcher.setObjectName("RapidFireTriggerTypeFrame")
        self.trigger_type_switcher.triggerTypeChanged.connect(self._on_trigger_type_changed)
        c1_layout.addWidget(self.trigger_type_switcher)

        self.target_switcher = SlidingSegmentedPillTarget()
        self.target_switcher.setObjectName("RapidFireTargetTabFrame")
        self.target_switcher.targetChanged.connect(self.controller.set_target_button)
        c1_layout.addWidget(self.target_switcher)

        cfg_layout.addWidget(self.card1, 1)

        # CARD 2: CADENCE SPEED & HUMANIZATION
        self.card2 = QFrame()
        self.card2.setObjectName("RapidFireSpeedCard")
        self.card2.setFixedHeight(132)
        self.card2.setStyleSheet("""
            QFrame#RapidFireSpeedCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        c2_layout = QVBoxLayout(self.card2)
        c2_layout.setContentsMargins(12, 8, 12, 8)
        c2_layout.setSpacing(4)

        c2_head = QHBoxLayout()
        c2_title = QLabel("CADENCE SPEED")
        c2_title.setObjectName("RapidFireSpeedTitle")
        c2_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        c2_head.addWidget(c2_title)
        c2_head.addStretch()

        self.speed_val_lbl = QLabel("18 CPS (Fast Auto)")
        self.speed_val_lbl.setObjectName("RapidFireSpeedValLabel")
        self.speed_val_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        c2_head.addWidget(self.speed_val_lbl)
        c2_layout.addLayout(c2_head)

        # Quick Preset Segmented Pill
        self.speed_preset_switcher = SlidingSegmentedPillSpeedPresets()
        self.speed_preset_switcher.setObjectName("RapidFireSpeedPresetTabFrame")
        self.speed_preset_switcher.presetSelected.connect(self._on_speed_preset_selected)
        c2_layout.addWidget(self.speed_preset_switcher)

        # Speed Slider
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setObjectName("RapidFireSpeedSlider")
        self.speed_slider.setRange(5, 35)
        self.speed_slider.setValue(18)
        self.speed_slider.setStyleSheet("""
            QSlider#RapidFireSpeedSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            QSlider#RapidFireSpeedSlider::sub-page:horizontal {
                background: #FF5B06;
                border-radius: 2px;
            }
            QSlider#RapidFireSpeedSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #FF5B06;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
        """)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        c2_layout.addWidget(self.speed_slider)

        # Live Physical Cadence Timing Stats Row
        self.speed_timing_lbl = QLabel("PERIOD: ~55ms | HOLD: ~14ms | CADENCE: 18.0 Hz")
        self.speed_timing_lbl.setObjectName("RapidFireSpeedTimingLabel")
        self.speed_timing_lbl.setStyleSheet("color: #777777; font-family: 'Orbitron', sans-serif; font-size: 8px; font-weight: bold;")
        c2_layout.addWidget(self.speed_timing_lbl)

        self.cb_jitter = AnimatedCheckBox("Gaussian Humanization Jitter")
        self.cb_jitter.setObjectName("RapidFireJitterCb")
        self.cb_jitter.setChecked(True)
        self.cb_jitter.setToolTip("Injects microsecond Gaussian organic timing variation to prevent anti-cheat pattern detection.")
        self.cb_jitter.toggled.connect(self.controller.set_humanize_jitter)
        self.cb_jitter.toggled.connect(self._on_jitter_toggled)
        c2_layout.addWidget(self.cb_jitter)

        cfg_layout.addWidget(self.card2, 1)

        # CARD 3: TRIGGER & ARMING HOTKEYS
        self.card3 = QFrame()
        self.card3.setObjectName("RapidFireHotkeyCard")
        self.card3.setFixedHeight(132)
        self.card3.setStyleSheet("""
            QFrame#RapidFireHotkeyCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        c3_layout = QVBoxLayout(self.card3)
        c3_layout.setContentsMargins(12, 8, 12, 8)
        c3_layout.setSpacing(4)

        c3_title = QLabel("TRIGGER & ARMING HOTKEYS")
        c3_title.setObjectName("RapidFireHotkeyTitle")
        c3_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        c3_layout.addWidget(c3_title)

        c3_sub_row = QHBoxLayout()
        lbl_trig = QLabel("FIRE TRIGGER")
        lbl_trig.setObjectName("RapidFireSubTrigLabel")
        lbl_trig.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 8px; font-weight: bold;")
        c3_sub_row.addWidget(lbl_trig, 1)

        lbl_arm = QLabel("ARM TOGGLE")
        lbl_arm.setObjectName("RapidFireSubArmLabel")
        lbl_arm.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 8px; font-weight: bold;")
        c3_sub_row.addWidget(lbl_arm, 1)
        c3_layout.addLayout(c3_sub_row)

        c3_row = QHBoxLayout()
        c3_row.setSpacing(6)

        self.trigger_input = TacticalInputCatcherButton(default_key="Left Click")
        self.trigger_input.setObjectName("RapidFireTriggerInput")
        self.trigger_input.setFixedHeight(26)
        self.trigger_input.input_captured.connect(self._on_trigger_captured)
        c3_row.addWidget(self.trigger_input, 1)

        self.arm_hotkey_btn = RapidFireHotkeyButton(default_key="F8")
        self.arm_hotkey_btn.setObjectName("RapidFireArmHotkeyBtn")
        self.arm_hotkey_btn.setFixedHeight(26)
        self.arm_hotkey_btn.hotkeyChanged.connect(self._on_arm_hotkey_changed)
        c3_row.addWidget(self.arm_hotkey_btn, 1)

        c3_layout.addLayout(c3_row)

        self.engine_mode_desc_lbl = QLabel("WIN32 POLLING WATCHDOG: 66 HZ")
        self.engine_mode_desc_lbl.setObjectName("RapidFireEngineModeDescLabel")
        self.engine_mode_desc_lbl.setStyleSheet("color: #777777; font-family: 'Orbitron', sans-serif; font-size: 8px; font-weight: bold;")
        c3_layout.addWidget(self.engine_mode_desc_lbl)

        self.cb_sound = AnimatedCheckBox("Audible Tone Feedback")
        self.cb_sound.setObjectName("RapidFireSoundCb")
        self.cb_sound.setChecked(True)
        self.cb_sound.setToolTip("Plays tone chime on engine arm/disarm.")
        self.cb_sound.toggled.connect(self.controller.set_sound_enabled)
        c3_layout.addWidget(self.cb_sound)

        cfg_layout.addWidget(self.card3, 1)
        main_layout.addLayout(cfg_layout)

        # Dynamic Smooth Card Height Animator (240ms OutCubic)
        self._card_anim = QVariantAnimation(self)
        self._card_anim.setDuration(240)
        self._card_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._card_anim.valueChanged.connect(self._on_card_anim_tick)
        self._card_anim.finished.connect(self._on_card_anim_finished)

        # ── 3. INTERACTIVE TARGET CANVAS ───────────────────────
        self.target_canvas = RapidFireTargetCanvas()
        self.target_canvas.setObjectName("RapidFireTargetCanvas")
        self.controller.state_changed.connect(self.target_canvas.set_firing_state)
        self.controller.shot_dispatched.connect(self.target_canvas.record_shot)
        self.controller.enabled_state_changed.connect(self.target_canvas.set_engine_enabled)
        self.target_canvas.set_engine_enabled(self.controller.is_enabled)
        main_layout.addWidget(self.target_canvas, 1)

        # Initialize burst delay slider visibility without animation on boot
        self._update_burst_delay_visibility(animated=False)

    def _update_burst_delay_visibility(self, animated=True):
        is_burst = self.controller.mode in ("burst_3", "burst_5")
        is_hold = self.controller.trigger_type == "hold"
        show_burst_delay = is_burst and is_hold

        target_h = 176 if show_burst_delay else 132
        start_h = self.card1.height()

        if not animated or start_h == target_h:
            self._card_anim.stop()
            self.burst_delay_frame.setVisible(show_burst_delay)
            self._burst_opacity_effect.setOpacity(1.0 if show_burst_delay else 0.0)
            self.burst_delay_frame.setMaximumHeight(48 if show_burst_delay else 0)
            self.card1.setFixedHeight(target_h)
            self.card2.setFixedHeight(target_h)
            self.card3.setFixedHeight(target_h)
            return

        if show_burst_delay:
            self.burst_delay_frame.setVisible(True)

        if self._card_anim.state() == QVariantAnimation.Running:
            self._card_anim.stop()

        self._card_anim.setStartValue(start_h)
        self._card_anim.setEndValue(target_h)
        self._card_anim.start()

    def _on_card_anim_tick(self, val):
        h = int(val)
        self.card1.setFixedHeight(h)
        self.card2.setFixedHeight(h)
        self.card3.setFixedHeight(h)

        # Smooth slide & opacity progress (132 -> 0.0, 176 -> 1.0)
        progress = max(0.0, min(1.0, (h - 132.0) / 44.0))
        self._burst_opacity_effect.setOpacity(progress)
        self.burst_delay_frame.setMaximumHeight(int(48 * progress))

    def _on_card_anim_finished(self):
        is_burst = self.controller.mode in ("burst_3", "burst_5")
        is_hold = self.controller.trigger_type == "hold"
        show_burst_delay = is_burst and is_hold
        if not show_burst_delay:
            self.burst_delay_frame.setVisible(False)
            self._burst_opacity_effect.setOpacity(0.0)
            self.burst_delay_frame.setMaximumHeight(0)
        else:
            self._burst_opacity_effect.setOpacity(1.0)
            self.burst_delay_frame.setMaximumHeight(48)

    def _on_mode_changed(self, mode_str: str):
        self.controller.set_mode(mode_str)
        self.target_canvas.set_mode(mode_str)
        self._update_burst_delay_visibility(animated=True)

    def _on_trigger_type_changed(self, trigger_type: str):
        self.controller.set_trigger_type(trigger_type)
        self._update_burst_delay_visibility(animated=True)

    def _on_burst_delay_changed(self, val: int):
        self.controller.set_burst_delay_ms(val)
        if val >= 1000:
            txt = f"{val/1000.0:.2f} s"
        else:
            txt = f"{val} ms"
        self.burst_delay_val_lbl.setText(txt)

    def _on_jitter_toggled(self, enabled: bool):
        self.target_canvas.set_humanize_jitter(enabled)

    def _on_speed_slider_changed(self, val: int):
        self.controller.set_target_cps(val)
        self.target_canvas.set_target_cps(val)
        self.speed_preset_switcher.set_preset_from_val(val)
        tier = "Slow Tap" if val <= 10 else ("Medium Burst" if val <= 18 else ("Fast Auto" if val <= 26 else "Extreme Rampage"))
        self.speed_val_lbl.setText(f"{val} CPS ({tier})")

        period_ms = int(1000.0 / max(1, val))
        hold_ms = min(14, int(period_ms * 0.4))
        self.speed_timing_lbl.setText(f"PERIOD: ~{period_ms}ms | HOLD: ~{hold_ms}ms | CADENCE: {val:.1f} Hz")

    def _on_speed_preset_selected(self, cps: int):
        self.speed_slider.setValue(cps)

    def _on_trigger_captured(self, key_name: str):
        self.controller.set_trigger_key(key_name)
        print(f"[RapidFire] Trigger Key bound to: {key_name}")

    def _on_arm_hotkey_changed(self, key_name: str):
        self.controller.set_toggle_hotkey(key_name)
        print(f"[RapidFire] Armed Toggle Hotkey bound to: {key_name}")

    def _on_reset_stats(self):
        self.target_canvas.clear_target()

    def _sync_enable_ui(self, active: bool):
        if active:
            self.enable_btn.setText("ACTIVE")
            self.enable_btn.setStyleSheet("""
                QPushButton#RapidFireEnableBtn {
                    background-color: #00FF88;
                    color: #000000;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)
        else:
            self.enable_btn.setText("DISABLED")
            self.enable_btn.setStyleSheet("""
                QPushButton#RapidFireEnableBtn {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #888888;
                    font-family: 'Orbitron', sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 0px 8px;
                    min-height: 26px;
                    max-height: 26px;
                }
            """)

    def _on_back(self):
        self.controller.force_restore()
        self.back_clicked.emit()


class TacticalToolsHubPanel(QWidget):
    """
    Tactical Utilities Hub with 6 Tool Cards.
    
    Component Name: TacticalToolsHubPanel
    """
    tool_selected = Signal(int)  # 1: Sniper Clutch, 2: Clamp, 3: Rapid-Fire, 4: Anti-AFK, 5: Boss Key, 6: Loupe

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TacticalToolsHubPanel")
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

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

        # Tactical Gaming Utilities Group Box
        hub_group = QGroupBox("Tactical Gaming Utilities")
        hub_group.setObjectName("TacticalGamingGroup")
        hub_group.setStyleSheet(_grp_style)
        hub_group_layout = QVBoxLayout(hub_group)
        hub_group_layout.setContentsMargins(16, 20, 16, 16)
        hub_group_layout.setSpacing(12)

        desc_lbl = QLabel("Hardware-Level Pointer Control, Multi-Screen Lockdown & Automation Suite")
        desc_lbl.setObjectName("TacticalHubHeaderDesc")
        desc_lbl.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        hub_group_layout.addWidget(desc_lbl)

        # 6 Cards Grid (2 Rows x 3 Columns)
        cards_container = QWidget()
        cards_container.setObjectName("TacticalCardsContainer")
        cards_grid = QGridLayout(cards_container)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(15)

        # Card 1: Sniper DPI Clutch
        c1 = self._create_card(
            card_id="SniperClutchCard",
            title="Sniper DPI Clutch",
            desc="Dynamic on-hold cursor sensitivity dampener for pixel-perfect sniping.",
            mode_idx=1
        )
        cards_grid.addWidget(c1, 0, 0)

        # Card 2: Cursor Clamp
        c2 = self._create_card(
            card_id="CursorClampCard",
            title="Monitor Cursor Clamp",
            desc="Locks mouse cursor inside primary screen or game window to prevent border leaks.",
            mode_idx=2
        )
        cards_grid.addWidget(c2, 0, 1)

        # Card 3: Universal Rapid-Fire
        c3 = self._create_card(
            card_id="RapidFireCard",
            title="Universal Rapid-Fire",
            desc="High-frequency burst & full-auto trigger with humanized Gaussian timing jitter.",
            mode_idx=3
        )
        cards_grid.addWidget(c3, 0, 2)

        # Card 4: Smart Anti-AFK
        c4 = self._create_card(
            card_id="AntiAfkCard",
            title="Smart Anti-AFK",
            desc="Humanized natural Bezier wander and WASD keeper to avoid idle disconnects.",
            mode_idx=4
        )
        cards_grid.addWidget(c4, 1, 0)

        # Card 5: Instant Boss Key
        c5 = self._create_card(
            card_id="BossKeyCard",
            title="Instant Boss Key",
            desc="Sub-30ms emergency panic trigger to minimize game, mute audio and focus work app.",
            mode_idx=5
        )
        cards_grid.addWidget(c5, 1, 1)

        # Card 6: Crosshair Sniper Loupe
        c6 = self._create_card(
            card_id="SniperLoupeCard",
            title="Crosshair Sniper Loupe",
            desc="Hardware-accelerated 60 FPS transparent floating 2x-5x crosshair zoom lens.",
            mode_idx=6
        )
        cards_grid.addWidget(c6, 1, 2)

        hub_group_layout.addWidget(cards_container)
        main_layout.addWidget(hub_group)
        main_layout.addStretch()

    def _create_card(self, card_id, title, desc, mode_idx):
        card = QFrame()
        card.setObjectName(card_id)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(f"""
            QFrame#{card_id} {{
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 15px;
            }}
            QFrame#{card_id}:hover {{
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(15, 15, 15, 15)
        c_layout.setSpacing(6)

        # Title
        t_lbl = QLabel(title)
        t_lbl.setObjectName(f"{card_id}_Title")
        t_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        t_lbl.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold; background: transparent;")
        c_layout.addWidget(t_lbl)

        # Description
        d_lbl = QLabel(desc)
        d_lbl.setObjectName(f"{card_id}_Desc")
        d_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        d_lbl.setStyleSheet("color: #888888; font-family: 'Orbitron', sans-serif; font-size: 11px; background: transparent;")
        d_lbl.setWordWrap(True)
        c_layout.addWidget(d_lbl)
        c_layout.addStretch()

        card.mousePressEvent = lambda e: self.tool_selected.emit(mode_idx)
        return card


class MacroSettingsPanel(QWidget):
    """
    Settings panel for the macro system (fits in content stack).
    """
    
    macros_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = None  # Will be set lazily
        self._recording = False
        self._recorder = None
        self._player = None
        self._recording_listener = None
        self._current_recording = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._current_macro_events = []
        self.setObjectName("macroPanel")
        
        self._setup_ui()
        
        # Timer for fast UI status updates (macro lists, active markers)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._refresh_macro_status)
        
        # Auto-initialize and start macro bridge (deferred by 1.5s for zero-latency page switch)
        QTimer.singleShot(1500, self._auto_init_macro_system)
        
        # Initialize AutoHotkey (AHK) Plugin Engine Manager
        try:
            from AHKPluginManager import AHKPluginManager
            self._ahk_manager = AHKPluginManager()
            print("[HELXAIRO] AHKPluginManager initialized successfully.")
        except Exception as e:
            print(f"[HELXAIRO] Failed to initialize AHKPluginManager: {e}")
            self._ahk_manager = None
        
        # Universal OS Macro Hook IPC (UDP Socket to port 48123)
        # Reuse the parent GameLauncher's hook socket if available,
        # otherwise create our own as fallback.
        import socket
        import json
        parent = self.parent()
        while parent and not hasattr(parent, '_macro_hook_sock'):
            parent = parent.parent() if hasattr(parent, 'parent') and callable(parent.parent) else None
        
        if parent and hasattr(parent, '_macro_hook_sock'):
            self._macro_sock = parent._macro_hook_sock
            print("[HELXAIRO] Using launcher's macro hook socket (hook already running).")
        else:
            # Fallback: create own socket and start hook (shouldn't happen normally)
            self._macro_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._macro_heartbeat_timer = QTimer(self)
            self._macro_heartbeat_timer.setInterval(1000)
            self._macro_heartbeat_timer.timeout.connect(self._send_macro_heartbeat)
            self._macro_heartbeat_timer.start()
            self._start_universal_macro_engine()
            print("[HELXAIRO] Fallback: Started own macro hook engine.")
        
    def _start_universal_macro_engine(self):
        """Starts the isolated python subprocess for Universal Macro Hooking."""
        import subprocess
        import os
        import sys
        
        script_path = os.path.join(os.path.dirname(__file__), "UniversalMacroHook.py")
        
        # Kill any existing zombie hook processes that might still be bound to the UDP port
        try:
            import socket, json
            kill_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            kill_sock.sendto(json.dumps({'cmd': 'exit'}).encode('utf-8'), ('127.0.0.1', 48123))
            kill_sock.close()
            import time
            time.sleep(0.5)  # Wait for old hook to cleanly unhook and exit
        except Exception:
            pass
        
        # Zero-UAC Integration: Attempt to create and run an elevated Scheduled Task
        try:
            from utils.drive_utils import send_service_command
            import ctypes
            
            # Use PowerShell to dynamically create a Scheduled Task running as the current user but with Highest Privileges (Admin).
            # This completely bypasses UAC if the Zero-UAC Service is active.
            user_name = os.environ.get("USERNAME", "")
            task_name = "HELXAIRO_MacroHook"
            
            # The XML configuration ensures it runs in Session 1 (Interactive) and doesn't get hidden in Session 0.
            # However, schtasks /Create /RU %USERNAME% /RL HIGHEST is easier.
            schtasks_end = f'schtasks.exe /End /TN "{task_name}"'
            schtasks_create = f'schtasks.exe /Create /TN "{task_name}" /TR "\\"\"{sys.executable}\\\" \\\"{script_path}\\\"\\"" /RU "{user_name}" /RL HIGHEST /F'
            schtasks_run = f'schtasks.exe /Run /TN "{task_name}"'
            
            res = send_service_command({
                "action": "exec_batch_commands", 
                "commands": [schtasks_end, schtasks_create, schtasks_run]
            })
            
            if isinstance(res, dict) and res.get("status") == "success":
                print("[HELXAIRO] Spawned UniversalMacroHook process via Zero-UAC Service (Elevated!).")
                return
            else:
                print(f"[HELXAIRO] Zero-UAC Service not available or failed: {res}. Falling back to standard spawn.")
        except ImportError:
            pass
        except Exception as e:
            print(f"[HELXAIRO] Zero-UAC task launch error: {e}")
            
        # Fallback to standard subprocess if Zero-UAC is disabled
        try:
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen([sys.executable, script_path], creationflags=CREATE_NO_WINDOW)
            print("[HELXAIRO] Spawned UniversalMacroHook process (Standard User).")
        except Exception as e:
            print(f"[HELXAIRO] Failed to spawn UniversalMacroHook: {e}")

    def _send_macro_heartbeat(self):
        """Send ping to the isolated macro subprocess to keep it alive."""
        try:
            import json
            payload = json.dumps({'cmd': 'ping'}).encode('utf-8')
            self._macro_sock.sendto(payload, ('127.0.0.1', 48123))
        except Exception:
            pass
        
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
        header.setObjectName("helxairo_headerTitle")
        header.setFont(QFont("Orbitron", 24, QFont.Bold))
        header.setStyleSheet("color: #FF5B06; padding: 0;")
        header_layout.addWidget(header)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # ===== AHK MISSING ENGINE BANNER =====
        self._ahk_banner_container = QWidget()
        self._ahk_banner_container.setObjectName("ahkBannerContainer")
        self._ahk_banner_container.setStyleSheet("""
            QWidget#ahkBannerContainer {
                background: rgba(255, 91, 6, 0.08);
                border: 1px solid rgba(255, 91, 6, 0.35);
                border-radius: 8px;
            }
        """)
        ahk_banner_layout = QHBoxLayout(self._ahk_banner_container)
        ahk_banner_layout.setContentsMargins(14, 8, 14, 8)
        ahk_banner_layout.setSpacing(12)

        # Warning icon/title
        ahk_title = QLabel("AHK Engine Missing")
        ahk_title.setObjectName("ahkBannerTitle")
        ahk_title.setFont(QFont("Orbitron", 12, QFont.Bold))
        ahk_title.setStyleSheet("color: #FF9800;")
        ahk_banner_layout.addWidget(ahk_title)

        # Description text
        self._ahk_status_label = QLabel("AutoHotkey engine is not installed. Download now to enable OS-level macro bindings.")
        self._ahk_status_label.setObjectName("ahkStatusLabel")
        self._ahk_status_label.setFont(QFont("Orbitron", 11))
        self._ahk_status_label.setStyleSheet("color: #cccccc;")
        ahk_banner_layout.addWidget(self._ahk_status_label, 1)

        # Download button
        self._ahk_download_btn = AnimatedButton("Download AHK Engine")
        self._ahk_download_btn.setObjectName("ahkDownloadBtn")
        self._ahk_download_btn.setFont(QFont("Orbitron", 11, QFont.Bold))
        self._ahk_download_btn.setCursor(Qt.PointingHandCursor)
        self._ahk_download_btn.setStyleSheet("""
            QPushButton#ahkDownloadBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FF8A06);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-family: 'Orbitron', sans-serif;
                font-weight: bold;
            }
            QPushButton#ahkDownloadBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7328, stop:1 #FFA028);
            }
            QPushButton#ahkDownloadBtn:disabled {
                background: rgba(100, 100, 100, 0.4);
                color: #888888;
            }
        """)
        self._ahk_download_btn.clicked.connect(self._on_download_ahk_clicked)
        ahk_banner_layout.addWidget(self._ahk_download_btn)

        layout.addWidget(self._ahk_banner_container)
        
        # Check initial AHK status
        QTimer.singleShot(500, self._check_ahk_banner_status)
        
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
        tab_names = ["Home", "Macro", "Benchmark", "Reflex", "Tactical"]
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
        home_tab.setObjectName("macroHomeTab")
        home_main_layout = QHBoxLayout(home_tab)
        home_main_layout.setContentsMargins(20, 20, 20, 20)
        home_main_layout.setSpacing(20)
        
        # ===== LEFT COLUMN - Button Mappings =====
        left_column = QWidget()
        left_column.setObjectName("macroHomeLeftColumn")
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
                menu.setObjectName(f"macroButtonMappingMenu_{i}")
                menu.setStyleSheet(menu_style)
                
                # Store button index for lambda capture
                btn_idx = i
                
                # Buttons submenu
                buttons_menu = menu.addMenu("Buttons")
                buttons_menu.setStyleSheet(menu_style)
                for action in ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]:
                    act = buttons_menu.addAction(action)
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
                # Make clicking anywhere on button open the menu
                btn.clicked.connect(lambda checked, b=btn: b.showMenu())
            
            self._button_mapping_btns.append(btn)
            row.addWidget(btn, 1)
            
            left_layout.addLayout(row)
        
        left_layout.addSpacing(20)
        
        # Debounce Time
        debounce_label = QLabel("Debounce Time")
        debounce_label.setObjectName("macroDebounceLabel")
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
        
        # Anti-Cheat Interference Bypass Toggle
        left_layout.addSpacing(15)
        
        self._anticheat_toggle = QCheckBox("Bypass Anti-Cheat Interference")
        self._anticheat_toggle.setObjectName("helxairo_antiCheatToggle")
        self._anticheat_toggle.setToolTip("Bypasses OS software injection flags blocked by Anti-Cheat (Vanguard, EAC, BattEye).")
        self._anticheat_toggle.setCursor(Qt.PointingHandCursor)
        self._anticheat_toggle.setStyleSheet("""
            QCheckBox#helxairo_antiCheatToggle {
                color: #cccccc;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 500;
                spacing: 8px;
                background-color: rgba(25, 27, 33, 0.7);
                padding: 8px 12px;
                border-radius: 6px;
                border: none;
            }
            QCheckBox#helxairo_antiCheatToggle:hover {
                color: #ffffff;
                background-color: rgba(38, 42, 52, 0.9);
            }
            QCheckBox#helxairo_antiCheatToggle::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                background: #2a2d35;
            }
            QCheckBox#helxairo_antiCheatToggle::indicator:hover {
                background: #3a3e48;
            }
            QCheckBox#helxairo_antiCheatToggle::indicator:checked {
                background: #FF5B06;
            }
        """)
        self._anticheat_toggle.toggled.connect(self._on_anticheat_toggle_changed)
        left_layout.addWidget(self._anticheat_toggle)
        
        # Macro Execution Mode Options
        left_layout.addSpacing(8)
        
        execution_mode_label = QLabel("Macro Execution Mode")
        execution_mode_label.setObjectName("macroExecutionModeLabel")
        execution_mode_label.setStyleSheet("color: #888; font-size: 11px;")
        left_layout.addWidget(execution_mode_label)
        
        # Option A
        self._macro_mode_a = QRadioButton("Option A: Hardware Native (Direct MCU)")
        self._macro_mode_a.setObjectName("helxairo_macroModeA")
        self._macro_mode_a.setToolTip("Writes commands directly to mouse internal flash memory (0ms latency, 100% anti-cheat safe, but limited by firmware).")
        
        # Option B
        self._macro_mode_b = QRadioButton("Option B: AutoHotkey (External Plugin)")
        self._macro_mode_b.setObjectName("helxairo_macroModeB")
        self._macro_mode_b.setToolTip("Uses AutoHotkey to inject keys. Highly robust but risks detection by strict Anti-Cheats (Vanguard, etc).")
        
        # Option C
        self._macro_mode_c = QRadioButton("Option C: Kernel Driver (Interception)")
        self._macro_mode_c.setObjectName("helxairo_macroModeC")
        self._macro_mode_c.setToolTip("Bypasses Anti-Cheat and hardware limits using a custom kernel driver.")
        
        radio_style = """
            QRadioButton {
                color: #cccccc;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 500;
                spacing: 8px;
                background-color: rgba(25, 27, 33, 0.7);
                padding: 8px 12px;
                border-radius: 6px;
                border: none;
            }
            QRadioButton:hover {
                color: #ffffff;
                background-color: rgba(38, 42, 52, 0.9);
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                background: #2a2d35;
                border: 1px solid #3a3e48;
            }
            QRadioButton::indicator:hover {
                background: #3a3e48;
            }
            QRadioButton::indicator:checked {
                background: #FF5B06;
                border: 1px solid #FF5B06;
            }
        """
        
        self._macro_mode_a.setStyleSheet(radio_style)
        self._macro_mode_b.setStyleSheet(radio_style)
        self._macro_mode_c.setStyleSheet(radio_style)
        
        self._macro_mode_a.setCursor(Qt.PointingHandCursor)
        self._macro_mode_b.setCursor(Qt.PointingHandCursor)
        self._macro_mode_c.setCursor(Qt.PointingHandCursor)
        
        self._macro_mode_a.setChecked(True) # Default to Option A
        
        self._macro_mode_a.toggled.connect(lambda checked: self._on_macro_execution_mode_changed("Option A") if checked else None)
        self._macro_mode_b.toggled.connect(lambda checked: self._on_macro_execution_mode_changed("Option B") if checked else None)
        self._macro_mode_c.toggled.connect(lambda checked: self._on_macro_execution_mode_changed("Option C") if checked else None)
        
        left_layout.addWidget(self._macro_mode_a)
        left_layout.addSpacing(2)
        left_layout.addWidget(self._macro_mode_b)
        left_layout.addSpacing(2)
        left_layout.addWidget(self._macro_mode_c)
        
        # Scroll Injection Mode (Sub-Option for Option B)
        self._scroll_injection_combo = QComboBox()
        self._scroll_injection_combo.setObjectName("helxairo_scrollInjectionCombo")
        self._scroll_injection_combo.addItems([
            "Gaming",
            "Safe Browsing (Window Message Injection)"
        ])
        self._scroll_injection_combo.setToolTip("Select the scroll injection method used by Option B.")
        self._scroll_injection_combo.setVisible(False) # Hidden by default
        
        combo_style = """
            QComboBox {
                color: #cccccc;
                background-color: rgba(25, 27, 33, 0.7);
                border: 1px solid #3a3e48;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                margin-left: 20px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox:hover {
                border: 1px solid #FF5B06;
            }
        """
        self._scroll_injection_combo.setStyleSheet(combo_style)
        self._scroll_injection_combo.currentTextChanged.connect(self._on_scroll_injection_mode_changed)
        
        left_layout.addSpacing(4)
        left_layout.addWidget(self._scroll_injection_combo)
        
        left_layout.addStretch()
        home_main_layout.addWidget(left_column)
        
        # ===== CENTER COLUMN - Mouse Diagram with Button Indicators =====
        center_column = QWidget()
        center_column.setObjectName("macroHomeCenterColumn")
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
        
        # Mouse image layout
        mouse_label = QLabel(mouse_container)
        mouse_label.setObjectName("macroHomeMouseLabel")
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
        
        # Button indicator positions (x, y) - mouse layout
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
        right_column.setObjectName("macroHomeRightColumn")
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
        for _ in range(3):
            ph = QWidget()
            ph.setObjectName(f"macroPagePlaceholder_{_}")
            self._page_stack.addWidget(ph)
            
        layout.addWidget(self._page_stack, 1)
        self._page_stack.setCurrentIndex(0)
        self._update_tab_buttons()
        
        # Build remaining tabs deferred on tick 0 for zero-latency page load
        QTimer.singleShot(0, self._build_remaining_tabs)

    def _build_remaining_tabs(self):
        """Build Macro and Benchmark tabs asynchronously on tick 0."""
        # Remove placeholder widgets
        while self._page_stack.count() > 1:
            w = self._page_stack.widget(1)
            self._page_stack.removeWidget(w)
            w.deleteLater()

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
        page_editor.setObjectName("macroEditorPage")
        page_editor_scroll = SmoothScrollArea()
        page_editor_scroll.setObjectName("macroEditorScroll")
        page_editor_scroll.setWidgetResizable(True)
        page_editor_scroll.setStyleSheet(_scroll_style)
        page_editor_content = QWidget()
        page_editor_content.setObjectName("macroEditorContent")
        page_editor_content.setStyleSheet("background: transparent;")
        layout_editor = QVBoxLayout(page_editor_content)
        layout_editor.setContentsMargins(0, 0, 0, 0)
        layout_editor.setSpacing(15)

        # Quick Actions (Auto-Clicker) Card at top of Editor
        quick_group = QGroupBox("Quick Actions")
        quick_group.setObjectName("macroQuickGroup")
        quick_group.setStyleSheet(_grp_style)
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setSpacing(12)
        quick_layout.setAlignment(Qt.AlignVCenter)

        ac_layout = QHBoxLayout()
        ac_layout.setSpacing(10)
        ac_layout.setAlignment(Qt.AlignVCenter)

        # 1. Macro Name Input
        ac_name_lbl = QLabel("Macro Name")
        ac_name_lbl.setObjectName("macroAcNameLabel")
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
        ac_apps_lbl.setObjectName("macroAcAppsLabel")
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
        ac_lbl.setObjectName("macroAcKeyLabel")
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
        self.ac_custom_key.setObjectName("helxairo_acCustomKey")
        self.ac_custom_key.setFixedWidth(80)
        self.ac_custom_key.setFixedHeight(30)
        self.ac_custom_key.setVisible(False)
        ac_layout.addWidget(self.ac_custom_key, 0, Qt.AlignVCenter)

        interval_lbl = QLabel("Interval")
        interval_lbl.setObjectName("macroAcIntervalLabel")
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
        hotkey_lbl.setObjectName("macroAcHotkeyLabel")
        hotkey_lbl.setStyleSheet("color: #e0e0e0;")
        hotkey_lbl.setAlignment(Qt.AlignVCenter)
        ac_layout.addWidget(hotkey_lbl, 0, Qt.AlignVCenter)

        self.ac_hotkey = HotkeyRecordButton("F8")
        self.ac_hotkey.setObjectName("helxairo_acHotkey")
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
        editor_group.setObjectName("macroEditorGroup")
        editor_group.setStyleSheet(_grp_style)
        editor_group_layout = QVBoxLayout(editor_group)
        editor_group_layout.setSpacing(12)

        editor_layout = QHBoxLayout()
        editor_layout.setSpacing(20)

        # Left Column: Macro list
        # Left Column: Unified Macro list
        col1 = QVBoxLayout()
        col1_lbl = QLabel("Macro list")
        col1_lbl.setObjectName("macroCol1Label")
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
        self.editor_new_macro_btn.setObjectName("helxairo_editorNewMacroBtn")
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
        col2_lbl.setObjectName("macroCol2Label")
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
        self.editor_modify_key_btn.setObjectName("helxairo_editorModifyKeyBtn")
        self.editor_modify_key_btn.setFixedHeight(32)
        self.editor_modify_key_btn.setToolTip("Modify selected key action")
        col2_btns.addWidget(self.editor_modify_key_btn)

        self.editor_delete_key_btn = FadeHoverButton("Delete", is_secondary=True)
        self.editor_delete_key_btn.setObjectName("helxairo_editorDeleteKeyBtn")
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
        self.editor_start_record_btn.setObjectName("helxairo_editorStartRecordBtn")
        self.editor_start_record_btn.setFixedHeight(36)
        col3.addWidget(self.editor_start_record_btn)

        col3.addSpacing(15)

        _radio_style = """
            QRadioButton { color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px; spacing: 8px; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; background: #2a2d35; border: none; }
            QRadioButton::indicator:checked { background: #FF5B06; border: none; }
        """
        
        self.rb_auto_delay = QRadioButton("Auto insert delay")
        self.rb_auto_delay.setObjectName("helxairo_rbAutoDelay")
        self.rb_auto_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_auto_delay)

        self.rb_default_delay = QRadioButton("Default delay")
        self.rb_default_delay.setObjectName("helxairo_rbDefaultDelay")
        self.rb_default_delay.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_default_delay)

        self.spin_default_delay = AdaptiveSpinBox()
        self.spin_default_delay.setObjectName("helxairo_spinDefaultDelay")
        self.spin_default_delay.setRange(0, 9999)
        self.spin_default_delay.setValue(10)
        self.spin_default_delay.setAlignment(Qt.AlignCenter)
        self.spin_default_delay.setFixedWidth(85)
        self.spin_default_delay.setStyleSheet(_spinbox_style)
        col3.addWidget(self.spin_default_delay)

        col3.addSpacing(15)

        self.rb_cycle_release = QRadioButton("Cycle until the button is released")
        self.rb_cycle_release.setObjectName("helxairo_rbCycleRelease")
        self.rb_cycle_release.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_release)

        self.rb_cycle_any = QRadioButton("Cycle until any button is pressed")
        self.rb_cycle_any.setObjectName("helxairo_rbCycleAny")
        self.rb_cycle_any.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_any)

        self.rb_cycle_press = QRadioButton("Cycle until the button is pressed")
        self.rb_cycle_press.setObjectName("helxairo_rbCyclePress")
        self.rb_cycle_press.setStyleSheet(_radio_style)
        col3.addWidget(self.rb_cycle_press)

        self.rb_cycle_times = QRadioButton("Cycle Times")
        self.rb_cycle_times.setObjectName("helxairo_rbCycleTimes")
        self.rb_cycle_times.setStyleSheet(_radio_style)
        self.rb_cycle_times.setChecked(True)
        col3.addWidget(self.rb_cycle_times)

        self.spin_cycle_times = AdaptiveSpinBox()
        self.spin_cycle_times.setObjectName("helxairo_spinCycleTimes")
        self.spin_cycle_times.setRange(1, 9999)
        self.spin_cycle_times.setValue(1)
        self.spin_cycle_times.setAlignment(Qt.AlignCenter)
        self.spin_cycle_times.setFixedWidth(85)
        self.spin_cycle_times.setStyleSheet(_spinbox_style)
        col3.addWidget(self.spin_cycle_times)

        col3.addSpacing(15)

        lbl_insert = QLabel("Insert command")
        lbl_insert.setObjectName("macroLblInsert")
        lbl_insert.setStyleSheet("color: #e0e0e0; font-family: 'Orbitron', sans-serif; font-size: 13px;")
        col3.addWidget(lbl_insert)

        self.combo_insert_cmd = QComboBox()
        self.combo_insert_cmd.setObjectName("helxairo_comboInsertCmd")
        self.combo_insert_cmd.setStyleSheet(_combo_style)
        col3.addWidget(self.combo_insert_cmd)

        col3.addStretch()

        self.editor_save_btn = FadeHoverButton("Save", is_secondary=False)
        self.editor_save_btn.setObjectName("helxairo_editorSaveBtn")
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
        page_recorder.setObjectName("macroRecorderPage")
        page_recorder_scroll = SmoothScrollArea()
        page_recorder_scroll.setObjectName("macroRecorderScroll")
        page_recorder_scroll.setWidgetResizable(True)
        page_recorder_scroll.setStyleSheet(_scroll_style)
        page_recorder_content = QWidget()
        page_recorder_content.setObjectName("macroRecorderContent")
        page_recorder_content.setStyleSheet("background: transparent;")
        layout_recorder = QVBoxLayout(page_recorder_content)
        layout_recorder.setContentsMargins(0, 0, 0, 0)
        layout_recorder.setSpacing(15)

        recorder_group = QGroupBox("Record Macro")
        recorder_group.setObjectName("macroRecorderGroup")
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
        self.record_status.setObjectName("helxairo_recordStatus")
        self.record_status.setStyleSheet("color: #888; font-size: 12px;")
        record_controls.addWidget(self.record_status)

        record_controls.addStretch()

        self.action_count_label = QLabel("0 actions")
        self.action_count_label.setObjectName("helxairo_actionCountLabel")
        self.action_count_label.setStyleSheet("color: #A43F96; font-size: 12px; font-weight: bold;")
        record_controls.addWidget(self.action_count_label)

        self.playback_status = QLabel("")
        self.playback_status.setObjectName("helxairo_playbackStatus")
        self.playback_status.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 12px;")
        record_controls.addWidget(self.playback_status)

        recorder_layout.addLayout(record_controls)

        options_row = QHBoxLayout()
        options_row.setSpacing(15)

        self.record_mouse_cb = AnimatedCheckBox("Mouse Clicks")
        self.record_mouse_cb.setObjectName("helxairo_recordMouseCb")
        self.record_mouse_cb.setChecked(True)
        options_row.addWidget(self.record_mouse_cb)

        self.record_movement_cb = AnimatedCheckBox("Mouse Movement")
        self.record_movement_cb.setObjectName("helxairo_recordMovementCb")
        self.record_movement_cb.setChecked(False)
        options_row.addWidget(self.record_movement_cb)

        self.record_keyboard_cb = AnimatedCheckBox("Keyboard")
        self.record_keyboard_cb.setObjectName("helxairo_recordKeyboardCb")
        self.record_keyboard_cb.setChecked(True)
        options_row.addWidget(self.record_keyboard_cb)

        options_row.addStretch()
        recorder_layout.addLayout(options_row)

        playback_row = QHBoxLayout()
        playback_row.setSpacing(10)

        speed_lbl = QLabel("Speed:")
        speed_lbl.setObjectName("macroRecorderSpeedLbl")
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
        loops_lbl.setObjectName("macroRecorderLoopsLbl")
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
        hotkey2_lbl.setObjectName("macroRecorderHotkeyLbl")
        hotkey2_lbl.setStyleSheet("color: #e0e0e0;")
        playback_row.addWidget(hotkey2_lbl)

        self.playback_hotkey = HotkeyRecordButton("F9")
        self.playback_hotkey.setObjectName("helxairo_playbackHotkey")
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
        page_profiles.setObjectName("macroProfilesPage")
        page_profiles_scroll = SmoothScrollArea()
        page_profiles_scroll.setObjectName("macroProfilesScroll")
        page_profiles_scroll.setWidgetResizable(True)
        page_profiles_scroll.setStyleSheet(_scroll_style)
        page_profiles_content = QWidget()
        page_profiles_content.setObjectName("macroProfilesContent")
        page_profiles_content.setStyleSheet("background: transparent;")
        layout_profiles = QVBoxLayout(page_profiles_content)
        layout_profiles.setContentsMargins(0, 0, 0, 0)
        layout_profiles.setSpacing(15)

        profile_group = QGroupBox("Profiles")
        profile_group.setObjectName("macroProfilesGroup")
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
        page_mousetester_scroll.setObjectName("HelxairoMouseTesterScroll")
        page_mousetester_scroll.setWidgetResizable(True)
        page_mousetester_scroll.setStyleSheet(_scroll_style)
        
        page_mousetester_content = QWidget()
        page_mousetester_content.setObjectName("HelxairoMouseTesterContent")
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
        mt_desc.setObjectName("HelxairoMouseTesterDesc")
        mt_desc.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        mt_group_layout.addWidget(mt_desc)

        # Grid of Placeholder Feature Cards
        grid_container = QWidget()
        grid_container.setObjectName("HelxairoMouseTesterGrid")
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
        cps_title.setObjectName("HelxairoCpsTestCardTitle")
        cps_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        cps_sub = QLabel("Real-time Click Per Second (CPS) Speed Test & High-Precision Counter")
        cps_sub.setObjectName("HelxairoCpsTestCardSub")
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
        btn_title.setObjectName("HelxairoButtonTestCardTitle")
        btn_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        btn_sub = QLabel("Interactive mouse button tester, debouncing & chatter detection")
        btn_sub.setObjectName("HelxairoButtonTestCardSub")
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
        scroll_title.setObjectName("HelxairoScrollTestCardTitle")
        scroll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        scroll_sub = QLabel("Scroll direction, delta smoothness & wheel step counter")
        scroll_sub.setObjectName("HelxairoScrollTestCardSub")
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
        poll_title.setObjectName("HelxairoPollingTestCardTitle")
        poll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        poll_sub = QLabel("Hz frequency report, motion smoothness & click latency estimation")
        poll_sub.setObjectName("HelxairoPollingTestCardSub")
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
        hub_scroll.setObjectName("BenchmarkHubScroll")
        hub_scroll.setWidgetResizable(True)
        hub_scroll.setStyleSheet(_scroll_style)
        
        hub_content = QWidget()
        hub_content.setObjectName("BenchmarkHubContent")
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
        hub_desc.setObjectName("MouseTesterDesc")
        hub_desc.setStyleSheet("color: #a0a0a0; font-family: 'Orbitron', sans-serif; font-size: 12px;")
        hub_group_layout.addWidget(hub_desc)

        # 2x2 Grid of Feature Cards
        grid_container = QWidget()
        grid_container.setObjectName("BenchmarkHubGrid")
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
        cps_card_title.setObjectName("CpsCardTitle")
        cps_card_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        cps_card_sub = QLabel("Real-time Click Per Second (CPS) Speed Test & High-Precision Counter")
        cps_card_sub.setObjectName("CpsCardSub")
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
        btn_title.setObjectName("ButtonTestTitle")
        btn_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        btn_sub = QLabel("Interactive mouse button tester, debouncing & chatter detection")
        btn_sub.setObjectName("ButtonTestSub")
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
        scroll_title.setObjectName("ScrollTestTitle")
        scroll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        scroll_sub = QLabel("Scroll direction, delta smoothness & wheel step counter")
        scroll_sub.setObjectName("ScrollTestSub")
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
        
        # Connect click event on Polling Rate test card to switch to Page 4!
        card_poll.mousePressEvent = lambda e: self._benchmark_stack.setCurrentIndex(4)
        poll_layout = QVBoxLayout(card_poll)
        poll_title = QLabel("Polling Rate & Latency")
        poll_title.setObjectName("PollingTestTitle")
        poll_title.setStyleSheet("color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: bold;")
        poll_sub = QLabel("Hz frequency report, motion smoothness & click latency estimation")
        poll_sub.setObjectName("PollingTestSub")
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
        cps_page.setObjectName("BenchmarkCpsPage")
        cps_page_layout = QVBoxLayout(cps_page)
        cps_page_layout.setContentsMargins(12, 10, 12, 10)
        cps_page_layout.setSpacing(8)

        # Active CPS Panel Suite (Back button integrated in header frame)
        self.cps_benchmark_panel = CpsBenchmarkPanel()
        self.cps_benchmark_panel.setObjectName("BenchmarkCpsPanel")
        self.cps_benchmark_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        cps_page_layout.addWidget(self.cps_benchmark_panel, 1)

        self._benchmark_stack.addWidget(cps_page)  # Index 1: CPS Benchmark Suite

        # ── SUB-PAGE 2: DEDICATED DOUBLE CLICK & CHATTER TEST PAGE ──────────
        dc_page = QWidget()
        dc_page.setObjectName("BenchmarkDoubleClickPage")
        dc_page_layout = QVBoxLayout(dc_page)
        dc_page_layout.setContentsMargins(12, 10, 12, 10)
        dc_page_layout.setSpacing(8)

        self.double_click_panel = DoubleClickTestPanel()
        self.double_click_panel.setObjectName("BenchmarkDoubleClickPanel")
        self.double_click_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        dc_page_layout.addWidget(self.double_click_panel, 1)

        self._benchmark_stack.addWidget(dc_page)  # Index 2: Double Click & Chatter Test Suite

        # ── SUB-PAGE 3: DEDICATED SCROLL WHEEL TEST PAGE ──────────
        scroll_page = QWidget()
        scroll_page.setObjectName("BenchmarkScrollWheelPage")
        scroll_page_layout = QVBoxLayout(scroll_page)
        scroll_page_layout.setContentsMargins(12, 10, 12, 10)
        scroll_page_layout.setSpacing(8)

        self.scroll_wheel_panel = ScrollWheelTestPanel()
        self.scroll_wheel_panel.setObjectName("BenchmarkScrollWheelPanel")
        self.scroll_wheel_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        scroll_page_layout.addWidget(self.scroll_wheel_panel, 1)

        self._benchmark_stack.addWidget(scroll_page)  # Index 3: Scroll Wheel Test Suite

        # ── SUB-PAGE 4: DEDICATED POLLING RATE TEST PAGE ──────────
        poll_page = QWidget()
        poll_page.setObjectName("BenchmarkPollingRatePage")
        poll_page_layout = QVBoxLayout(poll_page)
        poll_page_layout.setContentsMargins(12, 10, 12, 10)
        poll_page_layout.setSpacing(8)

        self.polling_rate_panel = PollingRateTestPanel()
        self.polling_rate_panel.setObjectName("BenchmarkPollingRatePanel")
        self.polling_rate_panel.back_clicked.connect(lambda: self._benchmark_stack.setCurrentIndex(0))
        poll_page_layout.addWidget(self.polling_rate_panel, 1)

        self._benchmark_stack.addWidget(poll_page)  # Index 4: Polling Rate Test Suite

        benchmark_layout.addWidget(self._benchmark_stack)
        self._page_stack.addWidget(benchmark_tab)

        # === REFLEX LAB TAB (Main Top Tab Page 4) ===
        reflex_tab = QWidget()
        reflex_tab.setObjectName("ReflexTab")
        reflex_layout = QVBoxLayout(reflex_tab)
        reflex_layout.setContentsMargins(0, 0, 0, 0)

        self._reflex_stack = QStackedWidget()
        self._reflex_stack.setObjectName("ReflexStack")

        # ── SUB-PAGE 0: REFLEX HUB ──
        self.reflex_hub_panel = ReflexHubPanel()
        self.reflex_hub_panel.setObjectName("ReflexHubPanel")
        self.reflex_hub_panel.mode_selected.connect(lambda idx: self._reflex_stack.setCurrentIndex(idx))
        self._reflex_stack.addWidget(self.reflex_hub_panel)  # Index 0: Selection Hub

        # ── SUB-PAGE 1: REACTION TIME TEST ──
        self.reaction_panel = ReactionTimePanel()
        self.reaction_panel.setObjectName("ReflexReactionPanel")
        self.reaction_panel.back_clicked.connect(lambda: self._reflex_stack.setCurrentIndex(0))
        self._reflex_stack.addWidget(self.reaction_panel)    # Index 1: Reaction Test

        # ── SUB-PAGE 2: GRIDSHOT FLICK ARENA ──
        self.gridshot_panel = GridshotArenaPanel()
        self.gridshot_panel.setObjectName("ReflexGridshotPanel")
        self.gridshot_panel.back_clicked.connect(lambda: self._reflex_stack.setCurrentIndex(0))
        self._reflex_stack.addWidget(self.gridshot_panel)    # Index 2: Gridshot Arena

        # ── SUB-PAGE 3: PRECISION TRACKING LAB ──
        self.tracking_panel = PrecisionTrackingPanel()
        self.tracking_panel.setObjectName("ReflexTrackingPanel")
        self.tracking_panel.back_clicked.connect(lambda: self._reflex_stack.setCurrentIndex(0))
        self._reflex_stack.addWidget(self.tracking_panel)    # Index 3: Precision Tracking

        reflex_layout.addWidget(self._reflex_stack)
        self._page_stack.addWidget(reflex_tab)

        # === TACTICAL TOOLS TAB (Main Top Tab Page 5) ===
        tactical_tab = QWidget()
        tactical_tab.setObjectName("TacticalTab")
        tactical_layout = QVBoxLayout(tactical_tab)
        tactical_layout.setContentsMargins(0, 0, 0, 0)

        self._tactical_stack = QStackedWidget()
        self._tactical_stack.setObjectName("TacticalStack")

        # ── SUB-PAGE 0: TACTICAL HUB ──
        self.tactical_hub_panel = TacticalToolsHubPanel()
        self.tactical_hub_panel.setObjectName("TacticalHubPanel")
        self.tactical_hub_panel.tool_selected.connect(lambda idx: self._tactical_stack.setCurrentIndex(idx))
        self._tactical_stack.addWidget(self.tactical_hub_panel)  # Index 0: Hub

        # ── SUB-PAGE 1: SNIPER DPI CLUTCH ──
        self.sniper_clutch_panel = SniperClutchPanel()
        self.sniper_clutch_panel.setObjectName("TacticalSniperClutchPanel")
        self.sniper_clutch_panel.back_clicked.connect(lambda: self._tactical_stack.setCurrentIndex(0))
        self._tactical_stack.addWidget(self.sniper_clutch_panel)  # Index 1: Sniper DPI Clutch

        # ── SUB-PAGE 2: MULTI-MONITOR CURSOR CLAMP ──
        self.cursor_clamp_panel = CursorClampPanel()
        self.cursor_clamp_panel.setObjectName("TacticalCursorClampPanel")
        self.cursor_clamp_panel.back_clicked.connect(lambda: self._tactical_stack.setCurrentIndex(0))
        self._tactical_stack.addWidget(self.cursor_clamp_panel)  # Index 2: Cursor Clamp

        # ── SUB-PAGE 3: UNIVERSAL RAPID-FIRE ──
        self.rapid_fire_panel = RapidFirePanel()
        self.rapid_fire_panel.setObjectName("TacticalRapidFirePanel")
        self.rapid_fire_panel.back_clicked.connect(lambda: self._tactical_stack.setCurrentIndex(0))
        self._tactical_stack.addWidget(self.rapid_fire_panel)  # Index 3: Rapid-Fire

        tactical_layout.addWidget(self._tactical_stack)
        self._page_stack.addWidget(tactical_tab)
        
        # Default to Home tab
        self._page_stack.setCurrentIndex(0)
        self._update_tab_buttons()
        
        # Load and apply saved HELXAIRO settings
        self._apply_saved_helxairo_settings()

    def _switch_tab(self, index: int):
        """Switch to specified tab with latency profiling."""
        try:
            import json, os, time
            appdata = os.getenv("APPDATA", "")
            settings_file = os.path.join(appdata, "HELXAID", "settings.json")
            is_profiling = False
            if os.path.exists(settings_file):
                with open(settings_file, "r") as f:
                    is_profiling = json.load(f).get("calculate_tab_initialize", False)
        except Exception:
            is_profiling = False

        t_start = time.perf_counter() if is_profiling else 0.0

        self._current_tab = index
        self._page_stack.setCurrentIndex(index)
        self._update_tab_buttons()

        if is_profiling:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            tab_names = {
                0: "HELXAIRO - Home",
                1: "HELXAIRO - Macro",
                2: "HELXAIRO - Benchmark",
                3: "HELXAIRO - Reflex",
                4: "HELXAIRO - Tactical",
            }
            tab_label = tab_names.get(index, f"HELXAIRO Tab {index}")
            print(f"[Tab Profiler] {tab_label} initialized in {elapsed_ms:.2f} ms")
            try:
                from launcher import TabInitProfilerWindow
                self._tab_profiler_win = TabInitProfilerWindow(tab_label, elapsed_ms)
                self._tab_profiler_win.show()
                self._tab_profiler_win.raise_()
                self._tab_profiler_win.activateWindow()
            except Exception as pe:
                print(f"[Tab Profiler Error] {pe}")

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

    
    def _show_left_click_protection(self):
        """
        Show protection dialog when user tries to change button 1 (Left Click).
        Left Click must remain assigned to button 1 to prevent lockout.
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
    

    def _check_ahk_banner_status(self):
        """Check if AutoHotkey is installed and toggle missing engine banner visibility."""
        try:
            from integrations.tools_downloader import is_ahk_installed
            installed = is_ahk_installed()
        except Exception:
            installed = False

        if hasattr(self, '_ahk_banner_container'):
            self._ahk_banner_container.setVisible(not installed)

    def _on_download_ahk_clicked(self):
        """Handler for clicking the Download AHK Engine button."""
        if hasattr(self, '_ahk_download_btn'):
            self._ahk_download_btn.setEnabled(False)
            self._ahk_download_btn.setText("Downloading...")
        if hasattr(self, '_ahk_status_label'):
            self._ahk_status_label.setText("Downloading AutoHotkey v1.1 Portable engine...")

        def _download_thread():
            try:
                from integrations.tools_downloader import download_ahk
                success, res = download_ahk()
                
                def _on_done():
                    if success:
                        if hasattr(self, '_ahk_status_label'):
                            self._ahk_status_label.setText("AutoHotkey Engine installed successfully!")
                        if hasattr(self, '_ahk_banner_container'):
                            self._ahk_banner_container.setVisible(False)
                        # Re-initialize AHKPluginManager if needed and sync
                        try:
                            from AHKPluginManager import AHKPluginManager
                            self._ahk_manager = AHKPluginManager()
                        except Exception:
                            pass
                        self._sync_macros_to_hook()
                    else:
                        if hasattr(self, '_ahk_status_label'):
                            self._ahk_status_label.setText(f"Download failed: {res}")
                        if hasattr(self, '_ahk_download_btn'):
                            self._ahk_download_btn.setEnabled(True)
                            self._ahk_download_btn.setText("Retry Download")
                
                QTimer.singleShot(0, _on_done)
            except Exception as e:
                def _on_err():
                    if hasattr(self, '_ahk_status_label'):
                        self._ahk_status_label.setText(f"Download error: {e}")
                    if hasattr(self, '_ahk_download_btn'):
                        self._ahk_download_btn.setEnabled(True)
                        self._ahk_download_btn.setText("Retry Download")
                QTimer.singleShot(0, _on_err)

        import threading
        threading.Thread(target=_download_thread, daemon=True).start()

    def _sync_macros_to_hook(self):
        """Syncs all current button mappings to the AHK Engine and OS Hook after it has initialized."""
        if not hasattr(self, '_button_mappings'):
            return
            
        self._check_ahk_banner_status()

        # 1. Sync via AutoHotkey (AHK) Plugin Engine
        if hasattr(self, '_ahk_manager') and self._ahk_manager:
            try:
                bypass = getattr(self, '_anticheat_bypass_enabled', False)
                mappings_dict = {str(i): mapping for i, mapping in enumerate(self._button_mappings)}
                self._ahk_manager.apply_mappings(mappings_dict, bypass_anticheat=bypass)
                print(f"[HELXAIRO] Synced Macros to AHK Plugin Engine: {mappings_dict}")
            except Exception as e:
                print(f"[HELXAIRO] Failed to sync macro to AHK Plugin Engine: {e}")

        # 2. Legacy Socket Sync (if running)
        if hasattr(self, '_macro_sock'):
            import json
            for i, mapping in enumerate(self._button_mappings):
                try:
                    payload = json.dumps({'cmd': 'map', 'btn_name': str(i), 'macro': mapping})
                    self._macro_sock.sendto(payload.encode('utf-8'), ('127.0.0.1', 48123))
                    print(f"[HELXAIRO] Synced Startup Macro: Button {i+1} -> {mapping}")
                except Exception as e:
                    print(f"[HELXAIRO] Failed to sync macro to Hook: {e}")


    def _save_helxairo_settings(self):
        """Save HELXAIRO settings to file."""
        settings = {
            'button_mappings': getattr(self, '_button_mappings', self._get_default_button_mappings()),
            'bypass_anti_cheat': self._anticheat_toggle.isChecked() if hasattr(self, '_anticheat_toggle') else False,
        }

        # Persist Rapid Fire Settings
        if hasattr(self, 'rapid_fire_panel'):
            rf_ctrl = self.rapid_fire_panel.controller
            settings['rapid_fire'] = {
                'cps': rf_ctrl.target_cps,
                'mode': rf_ctrl.mode,
                'humanize': rf_ctrl.humanize_jitter,
                'target_button': rf_ctrl.target_button,
                'trigger_key': rf_ctrl.trigger_key,
                'toggle_hotkey': rf_ctrl.toggle_hotkey,
                'sound_enabled': rf_ctrl.sound_enabled,
            }

        try:
            with open(self._get_helxairo_settings_path(), 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"[HELXAIRO] Failed to save settings: {e}")
    
    def _load_helxairo_settings(self):
        """Load HELXAIRO settings from file."""
        try:
            with open(self._get_helxairo_settings_path(), 'r') as f:
                settings = json.load(f)
            
            # Load button mappings
            self._button_mappings = settings.get('button_mappings', self._get_default_button_mappings())
            return True
        except FileNotFoundError:
            self._button_mappings = self._get_default_button_mappings()
            return False
        except Exception as e:
            self._button_mappings = self._get_default_button_mappings()
            return False
    
    def _get_default_button_mappings(self):
        """Get default button mappings."""
        return ["Left Click", "Right Click", "Wheel Click", "Forward", "Backward"]
    
    def _on_button_mapping_changed(self, button_index: int, new_action: str):
        """
        Handle button mapping change from dropdown menu.
        Saves to local settings AND sends to Universal OS Hook / AHK Engine.
        
        Args:
            button_index: Button index (0-4)
            new_action: Action name string (e.g., "Left Click", "Right Click", "Macro", etc.)
        """
        if not hasattr(self, '_button_mappings'):
            self._button_mappings = self._get_default_button_mappings()
        
        self._button_mappings[button_index] = new_action
        self._save_helxairo_settings()
        print(f"[HELXAIRO] Button {button_index + 1} mapped to: {new_action}")
        
        # Update AHK Plugin Engine
        if hasattr(self, '_ahk_manager') and self._ahk_manager:
            try:
                bypass = getattr(self, '_anticheat_bypass_enabled', False)
                mappings_dict = {str(i): mapping for i, mapping in enumerate(self._button_mappings)}
                self._ahk_manager.apply_mappings(mappings_dict, bypass_anticheat=bypass)
                print(f"[HELXAIRO] Updated AHK Plugin Engine with new button mappings.")
            except Exception as e:
                print(f"[HELXAIRO] Failed to update AHK Plugin Engine: {e}")

        # Legacy Universal OS Macro Mapping Socket
        try:
            import json
            btn_name = str(button_index)
            payload = json.dumps({
                'cmd': 'map', 
                'btn_name': btn_name, 
                'macro': new_action
            }).encode('utf-8')
            if hasattr(self, '_macro_sock'):
                self._macro_sock.sendto(payload, ('127.0.0.1', 48123))
        except Exception as e:
            print(f"[HELXAIRO] Failed to send macro mapping to Hook Engine: {e}")
    
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

    def _on_anticheat_toggle_changed(self, checked: bool):
        """Handle Anti-Cheat Interference Bypass toggle."""
        import sys
        print(f"[TOGGLE-DEBUG] Anti-Cheat Bypass Mode changed -> {checked}")
        sys.stdout.flush()
        self._anticheat_bypass_enabled = checked
        self._save_helxairo_settings()

        if hasattr(self, '_ahk_manager') and self._ahk_manager:
            try:
                mappings_dict = {str(i): mapping for i, mapping in enumerate(self._button_mappings)}
                self._ahk_manager.apply_mappings(mappings_dict, bypass_anticheat=checked)
                print(f"[HELXAIRO] Applied Anti-Cheat Bypass ({checked}) to AHK Plugin Engine.")
            except Exception as e:
                print(f"[HELXAIRO] Failed to apply Anti-Cheat Bypass to AHK: {e}")

        try:
            import json
            payload = json.dumps({
                'cmd': 'set_anticheat_bypass',
                'enabled': checked
            }).encode('utf-8')
            if hasattr(self, '_macro_sock'):
                self._macro_sock.sendto(payload, ('127.0.0.1', 48123))
            print(f"[HELXAIRO] Anti-Cheat Bypass Mode set to: {checked}")
            sys.stdout.flush()
        except Exception as e:
            print(f"[HELXAIRO] Failed to send Anti-Cheat setting to Hook Engine: {e}")

    def _on_macro_execution_mode_changed(self, mode_str: str):
        """Handle Macro Execution Mode Options (A, B, C) toggle."""
        import sys
        print(f"[TOGGLE-DEBUG] Macro Execution Mode changed -> {mode_str}")
        print(f"[HELXAIRO] {mode_str} triggered")
        sys.stdout.flush()
        
        self._save_helxairo_settings()
        
        # Show sub-options ONLY if Option B is selected (DISABLED FOR AHK)
        if mode_str == "Option B":
            self._scroll_injection_combo.setVisible(False)
        else:
            self._scroll_injection_combo.setVisible(False)
        
        # Re-apply all button mappings to hardware if Option A is chosen
        if mode_str == "Option A":
            if hasattr(self, '_button_mappings'):
                for i, mapping in enumerate(self._button_mappings):
                    print(f"[TOGGLE-DEBUG] Re-applying Button {i+1} to HW -> {mapping} (Hardware Native: True)")
                    sys.stdout.flush()
                    self._send_button_mapping_to_hardware(i, mapping)
                    
        # Send mode selection to hook engine
        try:
            import json
            payload = json.dumps({
                'cmd': 'set_macro_execution_mode',
                'mode': mode_str
            }).encode('utf-8')
            if hasattr(self, '_macro_sock'):
                self._macro_sock.sendto(payload, ('127.0.0.1', 48123))
        except Exception as e:
            print(f"[HELXAIRO] Failed to send Macro Execution Mode setting to Hook Engine: {e}")

    def _on_scroll_injection_mode_changed(self, mode_str: str):
        """Handle Scroll Injection Mode (Gaming / Safe Browsing)."""
        import sys
        print(f"[TOGGLE-DEBUG] Scroll Injection Mode changed -> {mode_str}")
        sys.stdout.flush()
        
        try:
            import json
            payload = json.dumps({
                'cmd': 'set_scroll_injection_mode',
                'mode': mode_str
            }).encode('utf-8')
            if hasattr(self, '_macro_sock'):
                self._macro_sock.sendto(payload, ('127.0.0.1', 48123))
        except Exception as e:
            print(f"[HELXAIRO] Failed to send Scroll Injection Mode setting to Hook Engine: {e}")

    def _apply_saved_helxairo_settings(self):
        """Load and apply saved HELXAIRO settings on startup."""
        self._loading_settings = True
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

            # Apply saved Rapid Fire settings
            try:
                with open(self._get_helxairo_settings_path(), 'r') as f:
                    _saved_data = json.load(f)
                if hasattr(self, 'rapid_fire_panel') and 'rapid_fire' in _saved_data:
                    rf = _saved_data['rapid_fire']
                    rf_p = self.rapid_fire_panel
                    rf_ctrl = rf_p.controller
                    if 'cps' in rf:
                        rf_p.speed_slider.setValue(int(rf['cps']))
                    if 'mode' in rf:
                        rf_p.mode_switcher.set_mode(rf['mode'])
                        rf_ctrl.set_mode(rf['mode'])
                    if 'target_button' in rf:
                        rf_p.target_switcher.set_target(rf['target_button'])
                        rf_ctrl.set_target_button(rf['target_button'])
                    if 'humanize' in rf:
                        rf_p.cb_jitter.setChecked(bool(rf['humanize']))
                        rf_ctrl.set_humanize_jitter(bool(rf['humanize']))
                    if 'trigger_key' in rf:
                        rf_p.trigger_input.set_captured_key(rf['trigger_key'])
                        rf_ctrl.set_trigger_key(rf['trigger_key'])
                    if 'toggle_hotkey' in rf:
                        rf_p.arm_hotkey_btn.set_hotkey(rf['toggle_hotkey'])
                        rf_ctrl.set_toggle_hotkey(rf['toggle_hotkey'])
                    if 'sound_enabled' in rf:
                        rf_p.cb_sound.setChecked(bool(rf['sound_enabled']))
                        rf_ctrl.set_sound_enabled(bool(rf['sound_enabled']))
            except Exception as e:
                print(f"[HELXAIRO] Note restoring Rapid Fire: {e}")
                        
            # Deferred sync to Universal OS Hook to ensure socket is initialized and Hook process is listening
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, self._sync_macros_to_hook)
        finally:
            self._loading_settings = False
    
    def _create_info_label(self, text: str) -> QLabel:
        """Create a styled info label for device info card."""
        label = QLabel(text)
        label.setObjectName("helxairo_infoLabel")
        label.setStyleSheet("color: #888; font-size: 12px; font-weight: 500;")
        label.setFixedWidth(80)
        return label
    
    def _create_stat_widget(self, title: str, value: str) -> QWidget:
        """Create a stat widget with title and value for Quick Stats card."""
        widget = QWidget()
        clean_title = re.sub(r'[^a-zA-Z0-9]', '', title) or "Stat"
        widget.setObjectName(f"helxairo_statWidget_{clean_title}")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)
        
        value_label = QLabel(value)
        value_label.setObjectName(f"helxairo_statValue_{clean_title}")
        value_label.setFont(QFont("Orbitron", 24, QFont.Bold))
        value_label.setStyleSheet("color: #FF5B06;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        title_label = QLabel(title)
        title_label.setObjectName(f"helxairo_statTitle_{clean_title}")
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
        if not hasattr(self, 'active_list'):
            # The UI builder _build_remaining_tabs might not have finished yet, retry soon
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._auto_init_macro_system)
            return
            
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
        menu.setObjectName("macroSortMenu")
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
                    panel2.setObjectName("HelxairoExtremeWarningOverlay")
                    panel2.show()
                    panel2.raise_()
                else:
                    self._ac_warning_ack = True
                    self._do_create_autoclicker(button, interval, hotkey, custom_name, selected, custom_key)
                    self._ac_warning_ack = False

            warn_overlay = HelxairoLowIntervalWarningOverlayPanel(parent_window, on_first_proceed_ac)
            warn_overlay.setObjectName("HelxairoLowIntervalWarningOverlay")
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

