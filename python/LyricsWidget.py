"""
Native Qt Lyrics Page Widget for HELXAIC
Interactive synchronized real-time lyric scrolling with Orbitron typography,
ambient glowing highlights, click-to-seek, manual sync offset controls, and smooth easing.

Component Name: LyricsWidget
"""

import os
import bisect
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QSize, QRectF, Property, QPoint
from PySide6.QtGui import QFont, QColor, QCursor, QPainter, QFontMetrics, QAction

from LyricsEngine import LyricData, LyricLine, LyricsCacheManager, LyricsFetchWorker


class LyricLineWidget(QWidget):
    """
    Zero-ghosting custom-painted lyric line item with smooth transitions.
    Renders animated background pills, smooth color/scale interpolation,
    neon glowing highlights, and Orbitron typography via QPainter.
    """
    clicked = Signal(int)  # Emits time_ms

    def __init__(self, index: int, line_data: LyricLine, parent=None):
        super().__init__(parent)
        self.index = index
        self.line_data = line_data
        self.time_ms = line_data.time_ms
        self.text = line_data.text or "♪"
        self.translation = line_data.translation

        self.font_main = QFont("Orbitron", 13, QFont.Bold)
        self.font_sub = QFont("Orbitron", 10, QFont.Normal)

        self.setObjectName(f"lyricLineItem_{index}")
        self.setCursor(QCursor(Qt.PointingHandCursor) if self.time_ms >= 0 else QCursor(Qt.ArrowCursor))
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._is_active = False
        self._is_hovered = False
        self._anim_progress = 0.0
        self._hover_progress = 0.0

        # Active transition animation (0.0 = inactive, 1.0 = active)
        self._active_anim = QPropertyAnimation(self, b"animProgress", self)
        self._active_anim.setDuration(260)
        self._active_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Hover transition animation (0.0 = unhovered, 1.0 = hovered)
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)

    def set_subtext(self, text: Optional[str]):
        """Dynamically update secondary subtext (Romaji / Translation / None)."""
        clean = text.strip() if text else None
        if self.translation != clean:
            self.translation = clean
            self.updateGeometry()
            self.update()

    def get_anim_progress(self) -> float:
        return self._anim_progress

    def set_anim_progress(self, val: float):
        self._anim_progress = max(0.0, min(1.0, float(val)))
        self.update()

    animProgress = Property(float, get_anim_progress, set_anim_progress)

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, val: float):
        self._hover_progress = max(0.0, min(1.0, float(val)))
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def set_active(self, active: bool):
        if self._is_active != active:
            self._is_active = active
            self._active_anim.stop()
            self._active_anim.setStartValue(self._anim_progress)
            self._active_anim.setEndValue(1.0 if active else 0.0)
            self._active_anim.setDuration(260 if active else 220)
            self._active_anim.setEasingCurve(QEasingCurve.OutCubic if active else QEasingCurve.OutQuad)
            self._active_anim.start()

    def enterEvent(self, event):
        self._is_hovered = True
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.time_ms >= 0:
            self.clicked.emit(self.time_ms)
        super().mousePressEvent(event)

    def sizeHint(self) -> QSize:
        w = max(200, self.width() if self.width() > 0 else 600)
        fm = QFontMetrics(self.font_main)
        text_rect = fm.boundingRect(0, 0, w - 48, 2000, Qt.AlignCenter | Qt.TextWordWrap, self.text)
        h = text_rect.height() + 24
        if self.translation:
            sub_fm = QFontMetrics(self.font_sub)
            sub_rect = sub_fm.boundingRect(0, 0, w - 48, 2000, Qt.AlignCenter | Qt.TextWordWrap, self.translation)
            h += sub_rect.height() + 8
        return QSize(w, max(48, h))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        t = self._anim_progress      # 0.0 (inactive) -> 1.0 (active)
        ht = self._hover_progress    # 0.0 (unhovered) -> 1.0 (hovered)

        # 1. Text Bounds (No background color box)
        if self.translation:
            main_h = (h - 12) * 0.6
            main_rect = QRectF(24, 6, w - 48, main_h)
            sub_rect = QRectF(24, 6 + main_h, w - 48, (h - 12) * 0.4)
        else:
            main_rect = QRectF(24, 6, w - 48, h - 12)

        # 2. Main Lyric Typography Interpolation (Smooth RGB + Alpha without font-size snapping)
        base_r = 115 + (255 - 115) * ht
        base_g = 121 + (255 - 121) * ht
        base_b = 144 + (255 - 144) * ht

        cur_r = int(base_r + (255 - base_r) * t)
        cur_g = int(base_g + (91 - base_g) * t)
        cur_b = int(base_b + (6 - base_b) * t)
        cur_a = int(160 + (255 - 160) * max(t, ht * 0.7))

        painter.setFont(self.font_main)

        # Ambient neon glow behind active text
        if t > 0.05:
            glow_alpha = int(70 * t)
            painter.setPen(QColor(255, 91, 6, glow_alpha))
            painter.drawText(main_rect.translated(0, 1), Qt.AlignCenter | Qt.TextWordWrap, self.text)
            painter.drawText(main_rect.translated(0, -1), Qt.AlignCenter | Qt.TextWordWrap, self.text)

        painter.setPen(QColor(cur_r, cur_g, cur_b, cur_a))
        painter.drawText(main_rect, Qt.AlignCenter | Qt.TextWordWrap, self.text)

        # 3. Optional Translation Subtext Interpolation
        if self.translation:
            sub_r = int(100 + (253 - 100) * t)
            sub_g = int(105 + (169 - 105) * t)
            sub_b = int(120 + (3 - 120) * t)
            sub_a = int(140 + (240 - 140) * max(t, ht * 0.6))
            painter.setFont(self.font_sub)
            painter.setPen(QColor(sub_r, sub_g, sub_b, sub_a))
            painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextWordWrap, self.translation)

        painter.end()


def is_instrumental_line(text: Optional[str]) -> bool:
    """Check if text is an instrumental placeholder or music note marker."""
    if not text:
        return True
    t = text.strip()
    if not t:
        return True
    t_lower = t.lower()
    return t in ("♪", "♫", "♬", "---", "--", "...", "…") or t_lower in (
        "(instrumental)", "[instrumental]", "instrumental",
        "(music)", "[music]", "music",
        "(solo)", "[solo]", "solo",
        "(interlude)", "[interlude]", "interlude",
        "(intro)", "[intro]", "(outro)", "[outro]"
    )


class LyricsWidget(QWidget):
    """Main Lyrics Page placed in the MusicPanelWidget stack."""
    seekRequested = Signal(int)  # Emits target ms to QMediaPlayer
    closeRequested = Signal()  # Emitted when user clicks close/collapse button on lyrics panel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LyricsWidget")
        self.cache_mgr = LyricsCacheManager()
        self.current_data: Optional[LyricData] = None
        self.current_worker: Optional[LyricsFetchWorker] = None
        self.current_track: Dict[str, Any] = {}
        self.active_index = -1
        self.request_id_counter = 0
        self.active_request_id = 0
        self.line_widgets: List[LyricLineWidget] = []
        self.timestamps: List[int] = []
        self.user_offset_ms = 0
        self.subtext_line_offset = 0
        self._user_scrolling_paused = False
        self.selected_provider = "auto"
        self.subtext_mode = "auto"

        self._setup_ui()

        # Smooth persistent scrollbar animator (prevents overlapping animations / jitter)
        self._scroll_anim = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(280)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Scroll resume timer (resumes auto-scroll 4s after manual user scroll)
        self.scroll_resume_timer = QTimer(self)
        self.scroll_resume_timer.setSingleShot(True)
        self.scroll_resume_timer.setInterval(4000)
        self.scroll_resume_timer.timeout.connect(self._resume_auto_scroll)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # === Top Header (Minimalist Title & Close Button) ===
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(4, 2, 4, 2)
        header_bar.setSpacing(8)

        self.title_label = QLabel("LYRICS")
        self.title_label.setObjectName("lyricsHeaderTitle")
        self.title_label.setStyleSheet("""
            QLabel#lyricsHeaderTitle {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
                background: transparent;
            }
        """)
        header_bar.addWidget(self.title_label, stretch=1)

        # Close / Collapse Button
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("lyricsCloseBtn")
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setToolTip("Close Lyrics Panel")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet("""
            QPushButton#lyricsCloseBtn {
                font-family: 'Orbitron', sans-serif;
                font-size: 12px;
                font-weight: bold;
                color: #8c92a4;
                background-color: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 6px;
            }
            QPushButton#lyricsCloseBtn:hover {
                color: #ffffff;
                background-color: rgba(255, 60, 60, 0.35);
            }
        """)
        self.btn_close.clicked.connect(self.closeRequested.emit)
        header_bar.addWidget(self.btn_close)

        main_layout.addLayout(header_bar)

        # === Center Scroll Area (Takes Maximum Vertical Space) ===
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("lyricsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea#lyricsScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 91, 6, 0.35);
                border-radius: 2px;
                min-height: 25px;
            }
            QScrollBar::handle:vertical:hover {
                background: #FF5B06;
            }
        """)

        # Container inside scroll area
        self.container = QWidget()
        self.container.setObjectName("lyricsContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self.container.setStyleSheet("QWidget#lyricsContainer { background: transparent; }")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 40, 10, 80)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignHCenter)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # Detect manual user scrolling
        self.scroll_area.verticalScrollBar().sliderMoved.connect(self._on_user_scroll)

        # === Expandable Bottom Bar Widget (Single Unified Card) ===
        self.bottom_bar = QFrame(self)
        self.bottom_bar.setObjectName("lyricsBottomBar")
        self.bottom_bar.setStyleSheet("""
            QFrame#lyricsBottomBar {
                background: rgba(15, 15, 28, 0.75);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 2px;
            }
        """)
        bottom_layout = QVBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(6, 4, 6, 4)
        bottom_layout.setSpacing(4)

        # 1. Top Row: Source Pill, Subtext Pill, and Expand/Collapse Toggle Button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.setAlignment(Qt.AlignVCenter)

        # Source Pill Badge (Clickable to switch provider)
        self.source_pill = QLabel("IDLE")
        self.source_pill.setObjectName("lyricsSourcePill")
        self.source_pill.setAlignment(Qt.AlignCenter)
        self.source_pill.setCursor(QCursor(Qt.PointingHandCursor))
        self.source_pill.setFixedHeight(18)
        self.source_pill.mousePressEvent = self._on_source_pill_clicked
        self._set_source_badge("IDLE", "#FDA903", "rgba(253, 169, 3, 0.15)", "Click to switch lyrics provider")
        top_row.addWidget(self.source_pill, 0, Qt.AlignVCenter)

        # Subtext Pill Badge (Clickable to switch subtext: Romaji / Translation / Off)
        self.subtext_pill = QLabel("SUB: AUTO")
        self.subtext_pill.setObjectName("lyricsSubtextPill")
        self.subtext_pill.setAlignment(Qt.AlignCenter)
        self.subtext_pill.setCursor(QCursor(Qt.PointingHandCursor))
        self.subtext_pill.setFixedHeight(18)
        self.subtext_pill.mousePressEvent = self._on_subtext_pill_clicked
        self._set_subtext_badge("SUB: AUTO", "#00E5FF", "rgba(0, 229, 255, 0.15)", "Click to switch subtext stream (Romaji / Translation / Off)")
        top_row.addWidget(self.subtext_pill, 0, Qt.AlignVCenter)

        top_row.addStretch(1)

        # Expand / Collapse Button (Top Right of Bottom Bar)
        self.btn_expand = QPushButton("▼")
        self.btn_expand.setObjectName("lyricsExpandBtn")
        self.btn_expand.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_expand.setToolTip("Toggle lyrics timing & offset controls")
        self.btn_expand.setFixedSize(22, 18)
        self.btn_expand.setStyleSheet("""
            QPushButton#lyricsExpandBtn {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 8.5px;
                font-weight: bold;
                color: #8c92a4;
                background-color: rgba(255, 255, 255, 0.07);
                border: none;
                border-radius: 5px;
                padding: 0;
                margin: 0;
                min-height: 18px;
                max-height: 18px;
                min-width: 22px;
                max-width: 22px;
            }
            QPushButton#lyricsExpandBtn:hover {
                color: #ffffff;
                background-color: rgba(255, 91, 6, 0.28);
            }
        """)
        self.btn_expand.clicked.connect(self._toggle_offset_controls)
        top_row.addWidget(self.btn_expand, 0, Qt.AlignVCenter)

        bottom_layout.addLayout(top_row)

        # 2. Bottom Row: Timing & Sub Controls (Placed directly BELOW pills on 1 sleek row)
        self.offset_widget = QWidget(self.bottom_bar)
        self.offset_widget.setObjectName("lyricsOffsetControlsContainer")
        offset_layout = QHBoxLayout(self.offset_widget)
        offset_layout.setContentsMargins(0, 2, 0, 2)
        offset_layout.setSpacing(4)

        self.btn_offset_minus = QPushButton("-0.5s")
        self.btn_offset_minus.setObjectName("lyricOffsetMinusBtn")
        self.btn_offset_minus.setToolTip("Shift lyrics earlier by 0.5s")

        self.btn_offset_plus = QPushButton("+0.5s")
        self.btn_offset_plus.setObjectName("lyricOffsetPlusBtn")
        self.btn_offset_plus.setToolTip("Shift lyrics later by 0.5s")

        self.btn_offset_reset = QPushButton("Sync")
        self.btn_offset_reset.setObjectName("lyricOffsetResetBtn")
        self.btn_offset_reset.setToolTip("Reset sync offset to 0s")

        self.btn_reload = QPushButton("↻")
        self.btn_reload.setObjectName("lyricReloadBtn")
        self.btn_reload.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_reload.setToolTip("Re-fetch lyrics for current track")

        for b in (self.btn_offset_minus, self.btn_offset_plus, self.btn_offset_reset, self.btn_reload):
            b.setCursor(QCursor(Qt.PointingHandCursor))
            b.setStyleSheet("""
                QPushButton {
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    font-size: 9.5px;
                    font-weight: 600;
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #b0b4c3;
                    border: none;
                    border-radius: 4px;
                    padding: 3px 8px;
                    min-height: 20px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 91, 6, 0.30);
                    color: #ffffff;
                }
            """)
            offset_layout.addWidget(b)

        self.btn_offset_minus.clicked.connect(lambda: self.adjust_offset(-500))
        self.btn_offset_plus.clicked.connect(lambda: self.adjust_offset(500))
        self.btn_offset_reset.clicked.connect(lambda: self.adjust_offset(0, reset=True))
        self.btn_reload.clicked.connect(self.reload_current_track)

        # Subtle separator
        sep = QFrame(self.offset_widget)
        sep.setObjectName("lyricsOffsetSeparator")
        sep.setFixedSize(1, 14)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.12); border: none;")
        offset_layout.addWidget(sep)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow_path = os.path.join(script_dir, "UI Icons", "up-arrow-triangle.svg").replace("\\", "/")
        down_arrow_path = os.path.join(script_dir, "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")

        # Sub Offset Label + QSpinBox (Styled identically to HELXAIRO helxairo_acInterval)
        self.sub_offset_label = QLabel("Sub")
        self.sub_offset_label.setObjectName("lyricsSubOffsetLabel")
        self.sub_offset_label.setStyleSheet("""
            QLabel#lyricsSubOffsetLabel {
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 10.5px;
                font-weight: bold;
                color: #00E5FF;
                background: transparent;
                padding-left: 2px;
            }
        """)
        offset_layout.addWidget(self.sub_offset_label)

        self.sub_offset_spin = QSpinBox(self.offset_widget)
        self.sub_offset_spin.setObjectName("lyricsSubOffsetSpinBox")
        self.sub_offset_spin.setRange(-20, 20)
        self.sub_offset_spin.setValue(0)
        self.sub_offset_spin.setPrefix(" ")
        self.sub_offset_spin.setSuffix(" L")
        self.sub_offset_spin.setToolTip("Shift subtext/romaji alignment by lines (-20 to +20)")
        self.sub_offset_spin.setFixedWidth(70)
        self.sub_offset_spin.setFixedHeight(24)
        self.sub_offset_spin.setStyleSheet(f"""
            QSpinBox#lyricsSubOffsetSpinBox {{
                background-color: rgba(30, 30, 30, 0.85);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0px 17px 0px 4px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
            }}
            QSpinBox#lyricsSubOffsetSpinBox QLineEdit {{
                background: transparent;
                color: #e0e0e0;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Orbitron', sans-serif;
                font-size: 10px;
                font-weight: bold;
                selection-background-color: #FF5B06;
            }}
            QSpinBox#lyricsSubOffsetSpinBox:hover {{
                background-color: rgba(40, 40, 40, 0.95);
                border-color: #FF5B06;
                color: #ffffff;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-top-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox#lyricsSubOffsetSpinBox::up-arrow {{
                image: url('{up_arrow_path}');
                width: 7px;
                height: 7px;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-button {{
                width: 15px;
                background: rgba(60, 64, 72, 0.8);
                border: none;
                border-bottom-right-radius: 5px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-button:hover {{
                background: rgba(255, 91, 6, 0.4);
            }}
            QSpinBox#lyricsSubOffsetSpinBox::down-arrow {{
                image: url('{down_arrow_path}');
                width: 7px;
                height: 7px;
            }}
        """)
        self.sub_offset_spin.valueChanged.connect(self._on_sub_spin_changed)
        offset_layout.addWidget(self.sub_offset_spin)

        offset_layout.addStretch(1)

        # Collapsed by default with smooth height animation
        self._offset_expanded = False
        self._offset_anim = QPropertyAnimation(self.offset_widget, b"maximumHeight", self)
        self._offset_anim.finished.connect(self._on_offset_anim_finished)
        self.offset_widget.setMaximumHeight(0)
        self.offset_widget.setVisible(False)
        bottom_layout.addWidget(self.offset_widget)

        main_layout.addWidget(self.bottom_bar)

    def _toggle_offset_controls(self):
        """Toggle expand/collapse of lyrics offset controls with buttery smooth cubic animation."""
        self._offset_expanded = not getattr(self, "_offset_expanded", False)
        target_h = max(28, self.offset_widget.sizeHint().height())

        self._offset_anim.stop()

        if self._offset_expanded:
            self.offset_widget.setVisible(True)
            self._offset_anim.setDuration(260)
            self._offset_anim.setStartValue(self.offset_widget.height())
            self._offset_anim.setEndValue(target_h)
            self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._offset_anim.start()

            self.btn_expand.setText("▲")
            self.btn_expand.setToolTip("Collapse lyrics timing controls")
            self.btn_expand.setStyleSheet("""
                QPushButton#lyricsExpandBtn {
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    font-size: 8.5px;
                    font-weight: bold;
                    color: #FF5B06;
                    background-color: rgba(255, 91, 6, 0.22);
                    border: none;
                    border-radius: 5px;
                    padding: 0;
                    margin: 0;
                    min-height: 18px;
                    max-height: 18px;
                    min-width: 22px;
                    max-width: 22px;
                }
                QPushButton#lyricsExpandBtn:hover {
                    background-color: rgba(255, 91, 6, 0.35);
                    color: #ffffff;
                }
            """)
        else:
            self._offset_anim.setDuration(200)
            self._offset_anim.setStartValue(self.offset_widget.height())
            self._offset_anim.setEndValue(0)
            self._offset_anim.setEasingCurve(QEasingCurve.OutQuad)
            self._offset_anim.start()

            self.btn_expand.setText("▼")
            self.btn_expand.setToolTip("Expand lyrics timing controls")
            self.btn_expand.setStyleSheet("""
                QPushButton#lyricsExpandBtn {
                    font-family: 'Orbitron', 'Segoe UI', sans-serif;
                    font-size: 8.5px;
                    font-weight: bold;
                    color: #8c92a4;
                    background-color: rgba(255, 255, 255, 0.07);
                    border: none;
                    border-radius: 5px;
                    padding: 0;
                    margin: 0;
                    min-height: 18px;
                    max-height: 18px;
                    min-width: 22px;
                    max-width: 22px;
                }
                QPushButton#lyricsExpandBtn:hover {
                    color: #ffffff;
                    background-color: rgba(255, 91, 6, 0.28);
                }
            """)

    def _on_offset_anim_finished(self):
        """Cleanly hide widget when collapse animation reaches 0 height."""
        if not getattr(self, "_offset_expanded", False):
            self.offset_widget.setVisible(False)

    def _set_source_badge(self, text: str, color: str, bg_color: str, tooltip: str = ""):
        """Set branded styling and informative tooltip on the source pill without text clipping."""
        self.source_pill.setText(text)
        self.source_pill.setToolTip(tooltip or text)
        self.source_pill.setStyleSheet(f"""
            QLabel#lyricsSourcePill {{
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 9.5px;
                font-weight: bold;
                color: {color};
                background-color: {bg_color};
                padding: 0px 7px;
                border: none;
                border-radius: 5px;
                min-height: 18px;
                max-height: 18px;
            }}
            QLabel#lyricsSourcePill:hover {{
                background-color: rgba(255, 255, 255, 0.18);
            }}
        """)

    def _set_subtext_badge(self, text: str, color: str, bg_color: str, tooltip: str = ""):
        """Set branded styling and informative tooltip on the subtext pill."""
        self.subtext_pill.setText(text)
        self.subtext_pill.setToolTip(tooltip or text)
        self.subtext_pill.setStyleSheet(f"""
            QLabel#lyricsSubtextPill {{
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 9.5px;
                font-weight: bold;
                color: {color};
                background-color: {bg_color};
                padding: 0px 7px;
                border: none;
                border-radius: 5px;
                min-height: 18px;
                max-height: 18px;
            }}
            QLabel#lyricsSubtextPill:hover {{
                background-color: rgba(255, 255, 255, 0.18);
            }}
        """)

    def _on_source_pill_clicked(self, event):
        """Handle click on source pill to pop up provider selection menu."""
        if event.button() == Qt.LeftButton:
            self._show_provider_menu()

    def _on_subtext_pill_clicked(self, event):
        """Handle click on subtext pill to pop up subtitle stream selection menu."""
        if event.button() == Qt.LeftButton:
            self._show_subtext_menu()

    def _show_provider_menu(self):
        """Open sleek menu to switch lyrics provider, styled identically to musicMenuBar."""
        menu = QMenu(self)
        menu.setObjectName("lyricsProviderMenu")
        menu.setStyleSheet("""
            QMenu#lyricsProviderMenu {
                background: rgba(25, 25, 35, 0.98);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu#lyricsProviderMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QMenu#lyricsProviderMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QMenu#lyricsProviderMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)

        providers = [
            ("auto", "Auto (Cascade Priority)"),
            ("musixmatch", "Musixmatch (Spotify Provider)"),
            ("netease", "NetEase Cloud (Asian & Romaji)"),
            ("lrclib", "LRCLIB (Open LRC Database)"),
            ("local", "Local File / Embedded Tags"),
        ]

        cur_pref = getattr(self, "selected_provider", "auto")

        for key, label in providers:
            prefix = "●  " if cur_pref == key else "    "
            act = QAction(f"{prefix}{label}", self)
            act.triggered.connect(lambda checked=False, p=key: self._set_provider_and_fetch(p))
            menu.addAction(act)

        menu_h = menu.sizeHint().height()
        pos = self.source_pill.mapToGlobal(QPoint(0, -menu_h - 4))
        menu.exec(pos)

    def _show_subtext_menu(self):
        """Open sleek menu to switch subtext stream, styled identically to musicMenuBar."""
        menu = QMenu(self)
        menu.setObjectName("lyricsSubtextMenu")
        menu.setStyleSheet("""
            QMenu#lyricsSubtextMenu {
                background: rgba(25, 25, 35, 0.98);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu#lyricsSubtextMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QMenu#lyricsSubtextMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QMenu#lyricsSubtextMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)

        options = [
            ("auto", "Auto (Best Available Romaji)"),
            ("google", "Google Romaji (AI Transliteration)"),
            ("genius", "Genius (Community Romanized)"),
            ("netease", "NetEase (Timed Romaji)"),
            ("romaji", "General Romaji"),
            ("translation", "Translation (NetEase Chinese)"),
            ("none", "Off (Original Lyrics Only)"),
        ]

        cur_mode = getattr(self, "subtext_mode", "auto")

        for key, label in options:
            prefix = "●  " if cur_mode == key else "    "
            act = QAction(f"{prefix}{label}", self)
            act.triggered.connect(lambda checked=False, m=key: self._set_subtext_mode(m))
            menu.addAction(act)

        menu_h = menu.sizeHint().height()
        pos = self.subtext_pill.mapToGlobal(QPoint(0, -menu_h - 4))
        menu.exec(pos)

    def _set_subtext_mode(self, mode: str):
        """Change active subtext mode and dynamically update line widgets."""
        self.subtext_mode = mode
        # If user explicitly selected google and current_data lacks google_romaji, trigger on-demand background fetch
        if mode == "google" and self.current_data and not getattr(self.current_data, 'has_google_romaji', False):
            from LyricsEngine import GoogleRomajiClient
            import threading
            def _bg_manual_google():
                success = GoogleRomajiClient.enrich_lyrics(self.current_data)
                if success:
                    if self.current_track:
                        title = self.current_track.get('title', '')
                        artist = self.current_track.get('artist', '')
                        duration = self.current_track.get('duration', 0.0)
                        self.cache_mgr.put(title, artist, duration, self.current_data)
                    QTimer.singleShot(0, self._apply_subtext_mode)
            threading.Thread(target=_bg_manual_google, daemon=True).start()

        self._apply_subtext_mode()

    def _apply_subtext_mode(self):
        """Apply active subtext mode across all displayed lyric line items with subtext_line_offset support and instrumental skipping."""
        mode = getattr(self, "subtext_mode", "auto")
        sub_offset = getattr(self, "subtext_line_offset", 0)
        has_any_sub = False
        has_google = False
        has_genius = False
        has_netease = False
        has_roma = False
        has_trans = False

        # 1. Identify vocal line widgets and extract their raw subtexts (skip instrumental markers like '♪')
        vocal_line_widgets = []
        raw_vocal_subtexts = []

        for lw in self.line_widgets:
            ld = lw.line_data
            if getattr(ld, 'google_romaji', None):
                has_google = True
            if getattr(ld, 'genius_romaji', None):
                has_genius = True
            if getattr(ld, 'netease_romaji', None):
                has_netease = True
            if getattr(ld, 'romaji', None):
                has_roma = True
            if getattr(ld, 'raw_translation', None):
                has_trans = True

            # If this line is an instrumental marker (e.g. '♪' / music icon), clear subtext and skip
            if is_instrumental_line(lw.text):
                lw.set_subtext(None)
                continue

            vocal_line_widgets.append(lw)

            if mode == "google":
                target = getattr(ld, 'google_romaji', None) or ""
            elif mode == "genius":
                target = getattr(ld, 'genius_romaji', None) or ""
            elif mode == "netease":
                target = getattr(ld, 'netease_romaji', None) or ""
            elif mode == "romaji":
                target = (
                    getattr(ld, 'google_romaji', None)
                    or getattr(ld, 'romaji', None)
                    or getattr(ld, 'genius_romaji', None)
                    or getattr(ld, 'netease_romaji', None)
                    or ""
                )
            elif mode == "translation":
                target = getattr(ld, 'raw_translation', None) or ""
            elif mode == "none":
                target = ""
            else:  # auto
                target = (
                    getattr(ld, 'google_romaji', None)
                    or getattr(ld, 'genius_romaji', None)
                    or getattr(ld, 'netease_romaji', None)
                    or getattr(ld, 'romaji', None)
                    or getattr(ld, 'raw_translation', None)
                    or ld.translation
                    or ""
                )
            clean_sub = target.strip() if target else None
            if is_instrumental_line(clean_sub):
                clean_sub = None
            raw_vocal_subtexts.append(clean_sub)

        # 2. Map subtexts strictly across vocal lines respecting subtext_line_offset
        num_vocal = len(vocal_line_widgets)
        for i, lw in enumerate(vocal_line_widgets):
            source_idx = i + sub_offset
            clean = raw_vocal_subtexts[source_idx] if 0 <= source_idx < num_vocal else None
            lw.set_subtext(clean)
            if clean:
                has_any_sub = True

        # Update subtext pill badge UI
        if mode == "google":
            label = "SUB: G-ROMA"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "genius":
            label = "SUB: GENIUS"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "netease":
            label = "SUB: NETEASE"
            color = "#00FF9D"
            bg = "rgba(0, 255, 157, 0.15)"
        elif mode == "romaji":
            label = "SUB: ROMA"
            color = "#00E5FF"
            bg = "rgba(0, 229, 255, 0.15)"
        elif mode == "translation":
            label = "SUB: TRANS"
            color = "#A78BFA"
            bg = "rgba(167, 139, 250, 0.15)"
        elif mode == "none":
            label = "SUB: OFF"
            color = "#8c92a4"
            bg = "rgba(255, 255, 255, 0.08)"
        else:  # auto
            if has_google:
                label = "SUB: G-ROMA"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_genius:
                label = "SUB: GENIUS"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_netease or has_roma:
                label = "SUB: ROMA"
                color = "#00E5FF"
                bg = "rgba(0, 229, 255, 0.15)"
            elif has_trans:
                label = "SUB: TRANS"
                color = "#A78BFA"
                bg = "rgba(167, 139, 250, 0.15)"
            else:
                label = "SUB: AUTO"
                color = "#00E5FF" if has_any_sub else "#8c92a4"
                bg = "rgba(0, 229, 255, 0.15)" if has_any_sub else "rgba(255, 255, 255, 0.08)"

        tooltip = f"Subtext Stream: {label.replace('SUB: ', '')} (Click to switch)"
        if getattr(self.current_data, 'genius_url', ''):
            tooltip += f" | Genius: {self.current_data.genius_url}"
        self._set_subtext_badge(label, color, bg, tooltip)

    def _set_provider_and_fetch(self, provider_key: str):
        """Update provider preference and re-fetch lyrics for the active track."""
        self.selected_provider = provider_key
        if self.current_track:
            title = self.current_track.get('title', '')
            artist = self.current_track.get('artist', '')
            duration = self.current_track.get('duration', 0.0)
            if provider_key != "auto":
                self.cache_mgr.delete(title, artist, duration)
            self.load_track(self.current_track, provider=provider_key)

    def _on_user_scroll(self):
        self._user_scrolling_paused = True
        self.scroll_resume_timer.start()

    def _resume_auto_scroll(self):
        self._user_scrolling_paused = False
        if self.active_index >= 0:
            self._scroll_to_index(self.active_index)
        elif self.timestamps and self.current_data and self.current_data.is_synced:
            vbar = self.scroll_area.verticalScrollBar()
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(vbar.value())
            self._scroll_anim.setEndValue(0)
            self._scroll_anim.start()

    def load_track(self, track: Dict[str, Any], provider: Optional[str] = None):
        """Load lyrics for a newly selected track with optional provider override."""
        if not track:
            return

        chosen_provider = provider or getattr(self, 'selected_provider', 'auto')
        self.current_track = track
        self.request_id_counter += 1
        self.active_request_id = self.request_id_counter
        self.active_index = -1
        self.user_offset_ms = 0
        self.subtext_line_offset = 0
        self.btn_offset_reset.setText("Sync")
        if hasattr(self, 'sub_offset_spin'):
            self.sub_offset_spin.blockSignals(True)
            self.sub_offset_spin.setValue(0)
            self.sub_offset_spin.blockSignals(False)

        from LyricsEngine import LRCLibClient
        raw_title = track.get('title', 'Unknown Track')
        raw_artist = track.get('artist', '')
        c_title = LRCLibClient.clean_query_title(raw_title)
        c_artist = LRCLibClient.clean_query_artist(raw_artist)
        cand_artist, cand_title = LRCLibClient.split_artist_title(c_title)

        disp_title = cand_title if cand_title else (c_title or raw_title)
        disp_artist = cand_artist if cand_artist else c_artist

        if disp_artist:
            self.title_label.setText(f"{disp_title}  —  {disp_artist}")
        else:
            self.title_label.setText(disp_title)

        provider_tag = f" ({chosen_provider.upper()})" if chosen_provider != "auto" else ""
        self._set_source_badge(f"SEARCHING{provider_tag}...", "#FDA903", "rgba(253, 169, 3, 0.15)", f"Searching via {chosen_provider.upper()}... Click to switch")

        self._clear_lines()

        # Stop previous worker if active
        if self.current_worker and self.current_worker.isRunning():
            try:
                self.current_worker.disconnect()
            except Exception:
                pass

        # Launch background worker
        self.current_worker = LyricsFetchWorker(self.active_request_id, track, self.cache_mgr, provider=chosen_provider, parent=self)
        self.current_worker.lyricsReady.connect(self._on_lyrics_ready)
        self.current_worker.start()

    def reload_current_track(self):
        """Force re-fetch lyrics for current track and delete cache."""
        if self.current_track:
            title = self.current_track.get('title', '')
            artist = self.current_track.get('artist', '')
            duration = self.current_track.get('duration', 0.0)
            self.cache_mgr.delete(title, artist, duration)
            self.load_track(self.current_track, provider=getattr(self, 'selected_provider', 'auto'))

    def _on_lyrics_ready(self, req_id: int, data: LyricData):
        if req_id != self.active_request_id:
            return  # Ignore outdated responses from fast track skips

        self.current_data = data
        source_raw = (data.source or "NONE").upper()
        
        # Clean & shorten source brand name for the badge
        if "MUSIXMATCH" in source_raw:
            source_brand = "MUSIXMATCH"
            pill_color = "#1DB954"
            pill_bg = "rgba(29, 185, 84, 0.18)"
        elif "NETEASE" in source_raw:
            source_brand = "NETEASE"
            pill_color = "#00E5FF"
            pill_bg = "rgba(0, 229, 255, 0.18)"
        elif "LRCLIB" in source_raw:
            source_brand = "LRCLIB"
            pill_color = "#FF5B06"
            pill_bg = "rgba(255, 91, 6, 0.18)"
        elif "LOCAL" in source_raw:
            source_brand = "LOCAL LRC"
            pill_color = "#FDA903"
            pill_bg = "rgba(253, 169, 3, 0.18)"
        elif "TAG" in source_raw or "EMBEDDED" in source_raw:
            source_brand = "EMBEDDED"
            pill_color = "#FDA903"
            pill_bg = "rgba(253, 169, 3, 0.18)"
        elif "CACHE" in source_raw:
            source_brand = "CACHED"
            pill_color = "#A78BFA"
            pill_bg = "rgba(167, 139, 250, 0.18)"
        else:
            source_brand = source_raw.replace("ONLINE", "").strip() or "UNKNOWN"
            pill_color = "#8c92a4"
            pill_bg = "rgba(255, 255, 255, 0.08)"

        tooltip_text = f"Source: {data.source} (Click to switch provider)" if data.source else "No lyrics (Click to switch provider)"

        if data.is_synced:
            self._set_source_badge(f"SYNCED • {source_brand}", pill_color, pill_bg, tooltip_text)
        elif data.plain_text and data.source != "none":
            self._set_source_badge(f"PLAIN • {source_brand}", pill_color, pill_bg, tooltip_text)
        else:
            self._set_source_badge("NO LYRICS", "#8c92a4", "rgba(255, 255, 255, 0.08)", "No lyrics available (Click to switch provider)")

        # If data has title/artist from tags or LRCLIB, update header title
        if data.title:
            if data.artist:
                self.title_label.setText(f"{data.title}  —  {data.artist}")
            else:
                self.title_label.setText(data.title)

        self._render_lyrics(data)

    def _clear_lines(self):
        if hasattr(self, '_scroll_anim'):
            self._scroll_anim.stop()
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.line_widgets.clear()
        self.timestamps.clear()

    def _render_lyrics(self, data: LyricData):
        self._clear_lines()
        for idx, line in enumerate(data.lines):
            item_widget = LyricLineWidget(idx, line, self.container)
            item_widget.clicked.connect(self.seekRequested.emit)
            self.container_layout.addWidget(item_widget)
            self.line_widgets.append(item_widget)
            if line.time_ms >= 0:
                self.timestamps.append(line.time_ms)
        self._apply_subtext_mode()

    def on_position_changed(self, pos_ms: int):
        """Update active lyric line based on current player position."""
        if not self.current_data or not self.current_data.is_synced or not self.timestamps:
            return

        effective_pos = pos_ms + self.user_offset_ms

        # 1. Pre-vocal intro period: before the first synchronized lyric cue
        if effective_pos < self.timestamps[0]:
            if self.active_index != -1:
                if 0 <= self.active_index < len(self.line_widgets):
                    self.line_widgets[self.active_index].set_active(False)
                self.active_index = -1
                if not self._user_scrolling_paused:
                    vbar = self.scroll_area.verticalScrollBar()
                    self._scroll_anim.stop()
                    self._scroll_anim.setStartValue(vbar.value())
                    self._scroll_anim.setEndValue(0)
                    self._scroll_anim.start()
            return

        # 2. Active vocal period: binary search for the active cue line
        idx = bisect.bisect_right(self.timestamps, effective_pos) - 1
        idx = max(0, min(idx, len(self.line_widgets) - 1))

        if idx != self.active_index:
            if 0 <= self.active_index < len(self.line_widgets):
                self.line_widgets[self.active_index].set_active(False)
            self.active_index = idx
            if 0 <= idx < len(self.line_widgets):
                self.line_widgets[idx].set_active(True)
                if not self._user_scrolling_paused:
                    self._scroll_to_index(idx)

    def _scroll_to_index(self, idx: int):
        if 0 <= idx < len(self.line_widgets):
            target_widget = self.line_widgets[idx]
            vbar = self.scroll_area.verticalScrollBar()
            viewport_h = self.scroll_area.viewport().height()
            target_y = target_widget.pos().y() + (target_widget.height() // 2) - (viewport_h // 2)
            clamped_y = max(0, min(target_y, vbar.maximum()))

            # Stop existing scroll animation and smoothly transition from current value
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(vbar.value())
            self._scroll_anim.setEndValue(clamped_y)
            self._scroll_anim.start()

    def adjust_offset(self, delta_ms: int, reset: bool = False):
        """Adjust or reset lyric sync offset."""
        if reset:
            self.user_offset_ms = 0
        else:
            self.user_offset_ms += delta_ms
        sec = self.user_offset_ms / 1000.0
        self.btn_offset_reset.setText(f"Offset {sec:+.1f}s")
        if self.active_index >= 0 and not self._user_scrolling_paused:
            self._scroll_to_index(self.active_index)

    def _on_sub_spin_changed(self, value: int):
        """Handle subtext line alignment change from QSpinBox."""
        self.subtext_line_offset = value
        self._apply_subtext_mode()

    def adjust_sub_offset(self, delta_lines: int, reset: bool = False):
        """Adjust or reset subtext line alignment offset."""
        if reset:
            self.subtext_line_offset = 0
        else:
            self.subtext_line_offset = getattr(self, "subtext_line_offset", 0) + delta_lines
            
        if hasattr(self, 'sub_offset_spin'):
            self.sub_offset_spin.blockSignals(True)
            self.sub_offset_spin.setValue(self.subtext_line_offset)
            self.sub_offset_spin.blockSignals(False)
        self._apply_subtext_mode()
