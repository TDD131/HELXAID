"""
Component Inspector Dialog for HELXAID
A lightweight, native runtime inspector for exploring Qt widget trees and properties.
Maintains 100% fidelity to HELXAID's signature cyberpunk UI aesthetic while supporting
clean text selection, universal Ctrl+C copying across all modifier states (including NumLock),
right-click context menu, and one-click 'Copy Info'.

Component Name: ComponentInspectorDialog
"""

import os
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, QTimer, QSize, QByteArray, QPoint, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QColor, QPainter, QPixmap, QKeySequence, QShortcut, QTextCursor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QWidget, QApplication, QSizePolicy, QMenu,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
try:
    from AnimatedButton import FadeHoverButton, AnimatedButton
except ImportError:
    from python.AnimatedButton import FadeHoverButton, AnimatedButton


# Native-styled Vector Blue Info Badge SVG
INFO_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36" width="36" height="36">
  <circle cx="18" cy="18" r="18" fill="#0078d4"/>
  <circle cx="18" cy="10.5" r="2.2" fill="#ffffff"/>
  <rect x="16" y="14.5" width="4" height="13" rx="1.5" fill="#ffffff"/>
</svg>"""


def _svg_to_pixmap(svg_string: str, size: QSize = QSize(34, 34)) -> QPixmap:
    """Renders an inline SVG string into a high-DPI QPixmap."""
    renderer = QSvgRenderer(QByteArray(svg_string.encode("utf-8")))
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def inspect_widget(widget: QWidget, main_window: Optional[QWidget] = None) -> Dict[str, Any]:
    """
    Extracts runtime metadata and hierarchy from any QWidget instance.
    """
    if not widget:
        return {}

    widget_type = widget.__class__.__name__
    object_name = widget.objectName() or ""
    accessible_name = widget.accessibleName() or ""
    tooltip = widget.toolTip() or ""

    # Build parent hierarchy
    hierarchy: List[str] = []
    w: Optional[QWidget] = widget
    while w:
        name = w.objectName() or "(no name)"
        hierarchy.append(f"{w.__class__.__name__}#{name}")
        w = w.parent()

    # Detect friendly component name and code reference
    component_name = "Unknown"
    code_ref = ""

    if main_window:
        # Check game buttons
        game_buttons = getattr(main_window, "game_buttons", [])
        if widget_type == "AnimatedGameButton" and game_buttons:
            for idx, item in enumerate(game_buttons):
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    btn, game = item[0], item[1]
                    if btn == widget:
                        component_name = f"Game Button: \"{game.get('name', 'Unknown')}\""
                        code_ref = f"self.game_buttons[{idx}]"
                        break

        # Check known MainWindow attributes
        named_attributes = [
            ("settings_btn", "Settings Button"),
            ("add_btn", "Add Game Button"),
            ("refresh_btn", "Refresh Button"),
            ("discord_btn", "Discord Button"),
            ("search_input", "Search Input"),
            ("sort_combo", "Sort Dropdown"),
            ("filter_combo", "Filter Dropdown"),
            ("games_container", "Games Container (Grid Background)"),
            ("games_scroll", "Games Scroll Area"),
            ("music_panel", "Music Panel (HELXAIC)"),
            ("taskbar_toolbar", "Taskbar Media Widget"),
        ]
        for attr_name, label in named_attributes:
            if widget == getattr(main_window, attr_name, None):
                component_name = label
                code_ref = f"self.{attr_name}"
                break

    # Fallback dynamic resolution
    if component_name == "Unknown":
        if hasattr(widget, "text") and callable(widget.text) and widget.text():
            text_preview = widget.text().strip()
            if len(text_preview) > 35:
                text_preview = text_preview[:32] + "..."
            component_name = f"{widget_type}: \"{text_preview}\""
        elif accessible_name:
            component_name = accessible_name
        elif object_name:
            component_name = object_name
        elif tooltip:
            tt_preview = tooltip.strip()
            if len(tt_preview) > 35:
                tt_preview = tt_preview[:32] + "..."
            component_name = f"{widget_type} ({tt_preview})"
        else:
            component_name = widget_type

    # Stylesheet selector recommendation
    if object_name:
        selector = f"{widget_type}#{object_name}"
    else:
        selector = f"<{widget_type}: set objectName first>"

    # Positions and geometry
    size_str = f"{widget.width()} x {widget.height()}"

    # Build formatted text report (100% faithful to HELXAID signature layout)
    report_lines = [
        "Component Inspector",
        "",
        f"Component: {component_name}",
        f"Widget Type: {widget_type}",
        f"Object Name: {object_name if object_name else '(not set)'}",
    ]

    if accessible_name:
        report_lines.append(f"Accessible Name: {accessible_name}")
    
    report_lines.append(f"Size: {size_str}")

    if code_ref:
        report_lines.append(f"Code Reference: {code_ref}")

    report_lines.append("")
    report_lines.append("Hierarchy (child → parent):")
    for i, h in enumerate(hierarchy[:6]):
        report_lines.append(f"  {i}. {h}")

    report_lines.append("")
    report_lines.append("Stylesheet Selector:")
    report_lines.append(f"  {selector}")

    full_text_report = "\n".join(report_lines)

    return {
        "widget": widget,
        "widget_type": widget_type,
        "object_name": object_name,
        "accessible_name": accessible_name,
        "component_name": component_name,
        "code_ref": code_ref,
        "selector": selector,
        "size_str": size_str,
        "hierarchy": hierarchy,
        "full_text_report": full_text_report,
    }


class InspectorTextEdit(QPlainTextEdit):
    """
    Custom read-only text viewer with robust clipboard handling.
    Ensures Ctrl+C copies strictly the selected text regardless of keyboard modifier states.
    """
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setObjectName("inspectorTextEditor")
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def keyPressEvent(self, event):
        # Universal Ctrl+C detection using bitwise & for modifier mask compatibility
        is_ctrl_c = (event.key() == Qt.Key_C and bool(event.modifiers() & Qt.ControlModifier))
        if is_ctrl_c or event.matches(QKeySequence.Copy):
            self.copy_selection_or_full()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection_or_full(self):
        """Copies active text selection or falls back to full content."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText().replace("\u2029", "\n")
            QApplication.clipboard().setText(selected)
        else:
            parent_dlg = self.window()
            if hasattr(parent_dlg, "widget_info") and "full_text_report" in parent_dlg.widget_info:
                QApplication.clipboard().setText(parent_dlg.widget_info["full_text_report"])
            else:
                QApplication.clipboard().setText(self.toPlainText())

    def contextMenuEvent(self, event):
        """Context menu with Orbitron dark aesthetic."""
        menu = self.createStandardContextMenu()
        menu.setObjectName("inspectorContextMenu")
        menu.setStyleSheet("""
            QMenu#inspectorContextMenu {
                background-color: #0c0d12;
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #ffffff;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 12px;
                padding: 4px;
            }
            QMenu#inspectorContextMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu#inspectorContextMenu::item:selected {
                background-color: #e65100;
                color: #ffffff;
            }
        """)
        menu.exec(event.globalPos())


class ComponentInspectorFloatingPanel(QFrame):
    """
    Modern Glassmorphism Floating Panel for HELXAID Component Inspector.
    
    Component Name: ComponentInspectorFloatingPanel
    """
    def __init__(self, widget_info: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("ComponentInspectorFloatingPanel")
        self.setFixedSize(500, 480)

        self._is_dragging = False
        self._drag_start_pos = QPoint()
        self.widget_info = widget_info

        self._init_ui()
        self._setup_shortcuts()
        self._apply_styling()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Custom In-App Titlebar
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("inspectorTitleBar")
        self.title_bar.setFixedHeight(42)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(14, 0, 10, 0)
        tb_layout.setSpacing(10)

        # App/Launcher Icon
        icon_lbl = QLabel(self.title_bar)
        icon_lbl.setObjectName("inspectorTitleIcon")
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setScaledContents(True)
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "launcher-icon.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.path.dirname(__file__), "UI Icons", "player-icon.png")
            if os.path.exists(icon_path):
                icon_lbl.setPixmap(QPixmap(icon_path))
            else:
                icon_lbl.setPixmap(_svg_to_pixmap(INFO_ICON_SVG, QSize(18, 18)))
        except Exception:
            icon_lbl.setPixmap(_svg_to_pixmap(INFO_ICON_SVG, QSize(18, 18)))
        tb_layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)

        title_lbl = QLabel("COMPONENT INSPECTOR (F12)", self.title_bar)
        title_lbl.setObjectName("inspectorTitleLabel")
        tb_layout.addWidget(title_lbl, stretch=1, alignment=Qt.AlignVCenter)

        main_layout.addWidget(self.title_bar)

        # 2. Main Content Row (Icon + Seamless Text Editor)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(18, 14, 18, 8)
        content_layout.setSpacing(16)
        content_layout.setAlignment(Qt.AlignTop)

        # Left Info Icon Badge
        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("inspectorInfoIcon")
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setPixmap(_svg_to_pixmap(INFO_ICON_SVG, QSize(34, 34)))
        content_layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        # Seamless Read-Only Text Area
        self.text_editor = InspectorTextEdit(self.widget_info.get("full_text_report", ""), self)
        self.text_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.text_editor, 1)

        main_layout.addLayout(content_layout, 1)

        # 3. Footer Button Row (Matching settingsOkButton & settingsCancelButton)
        btn_container = QWidget(self)
        btn_container.setObjectName("inspectorFooterContainer")
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(18, 4, 18, 16)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_ok = FadeHoverButton("OK", is_secondary=False, border_radius=6.0)
        self.btn_ok.setObjectName("settingsOkButton")
        self.btn_ok.setFixedSize(85, 34)
        self.btn_ok.clicked.connect(self.close_panel)
        btn_layout.addWidget(self.btn_ok)

        self.btn_copy = FadeHoverButton("Copy Info", is_secondary=False, border_radius=6.0)
        self.btn_copy.setObjectName("settingsCopyButton")
        self.btn_copy.setFixedSize(100, 34)
        self.btn_copy.setToolTip("Copy complete inspection details to clipboard")
        self.btn_copy.clicked.connect(self._on_copy_all)
        btn_layout.addWidget(self.btn_copy)

        main_layout.addWidget(btn_container)

        # 4. Entrance & Exit Fade Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

    def _setup_shortcuts(self):
        """Sets up window-level shortcuts for Ctrl+C and standard keys."""
        self.copy_shortcut = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_C), self)
        self.copy_shortcut.setContext(Qt.WindowShortcut)
        self.copy_shortcut.activated.connect(self._on_shortcut_copy)

    def _on_shortcut_copy(self):
        if hasattr(self, "text_editor"):
            self.text_editor.copy_selection_or_full()

    def keyPressEvent(self, event):
        """
        Universal fallback key handler on the panel level.
        """
        is_ctrl_c = (event.key() == Qt.Key_C and bool(event.modifiers() & Qt.ControlModifier))
        if is_ctrl_c or event.matches(QKeySequence.Copy):
            self._on_shortcut_copy()
            event.accept()
            return
        elif event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.close_panel()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_copy_all(self):
        """Copies the entire text report and provides visual feedback."""
        report = self.widget_info.get("full_text_report", "")
        if report:
            QApplication.clipboard().setText(report)
            self.btn_copy.setText("Copied!")
            QTimer.singleShot(1200, self._reset_copy_button)

    def _reset_copy_button(self):
        self.btn_copy.setText("Copy Info")

    def _on_anim_finished(self):
        if self.anim.direction() == QPropertyAnimation.Backward:
            self.deleteLater()

    def show_panel(self):
        """Position centered in parent and display with smooth fade in."""
        if self.parent():
            parent_rect = self.parent().rect()
            x = max(0, (parent_rect.width() - self.width()) // 2)
            y = max(0, (parent_rect.height() - self.height()) // 2)
            self.move(x, y)
        self.show()
        self.raise_()
        self.anim.setDirection(QPropertyAnimation.Forward)
        self.anim.start()
        self.text_editor.setFocus()

    def close_panel(self):
        """Close panel with smooth fade-out and cleanup."""
        self.anim.setDirection(QPropertyAnimation.Backward)
        self.anim.start()

    def exec_(self):
        """Compatibility helper to show panel."""
        self.show_panel()

    def exec(self):
        """Compatibility helper to show panel."""
        self.show_panel()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.title_bar.geometry().contains(event.pos()):
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
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()

    def _apply_styling(self):
        self.setStyleSheet("""
            QFrame#ComponentInspectorFloatingPanel {
                background-color: rgba(12, 12, 16, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QWidget#inspectorTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#inspectorTitleLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 1px;
            }
            QLabel#inspectorInfoIcon {
                background: transparent;
                border: none;
            }
            QPlainTextEdit#inspectorTextEditor {
                background: transparent;
                color: #ffffff;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.35;
                border: none;
                padding: 0px;
                margin: 0px;
                selection-background-color: #ffffff;
                selection-color: #000000;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #e65100;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)


# Compatibility Alias
ComponentInspectorDialog = ComponentInspectorFloatingPanel
