"""
DirectStreamPage.py - HELXAIC Unified Direct Streaming & Cloud Accounts Hub
============================================================================
Features:
- Minimalist, High-Craft Spotify / Apple Music / YouTube Music Grade Stream Center
- Top-Right Cyberpunk Cloud Profile Pill with In-Page Panel Switching
- Dedicated Cyberpunk Cloud Streaming Identity & Profile Hub (Zero Emoji, Pure SVG Vector)
- YouTube Music Session Sync: Liked Music (LM), User Playlists, and Mixes
- Spotify OAuth2 PKCE Hub: Liked Songs, Daily Mixes, Top Seeds, and Playlists
- Hybrid Fast Canonical Audio Resolution (<100ms) for Spotify tracks
- Clean Omnisearch with Instant Debounced Search & Genre Chips
- Results View: Hero Master Spotlight Card + 3-Column Alternative Candidates Grid
- 1-Click Stream Playback, Add to Playlist, Save .hxstream, and Downloader Trigger
- Ultra-thin custom dark scrollbar and cohesive dark Cyberpunk Orbitron aesthetics.

Component Name: DirectStreamPage
"""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPolygonF
from YouTubeAccountEngine import SyncYTCookiesWorker
import os
import sys
import re
import json
import time
import threading
import urllib.request
import ssl
import random
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QStackedWidget, QGridLayout,
    QApplication, QSizePolicy, QGraphicsOpacityEffect, QComboBox,
    QMenu, QDialog, QScrollArea, QMainWindow, QProgressBar, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QSize, QSettings, QVariantAnimation, QEasingCurve, QRectF, QPoint, QUrl, QPropertyAnimation
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QLinearGradient, QGradient, QFont, QFontMetrics, QPen, QShortcut, QKeySequence
from PySide6.QtSvg import QSvgRenderer

from CanonicalMetadataEngine import CanonicalSearchEngine, InnertubeSearchClient
from TasteProfileEngine import TasteProfileEngine
from YouTubeAccountEngine import (
    YouTubeAccountEngine, FetchYTLikedMusicWorker, FetchYTMixesWorker, FetchYTPlaylistsWorker
)
from SpotifyAccountEngine import (
    SpotifyAccountEngine, FetchSpotifyLikedSongsWorker, FetchSpotifyPlaylistsWorker, FetchSpotifyAlgorithmicFeedsWorker
)
from AnimatedButton import AnimatedButton, AnimatedCheckBox, FadeHoverButton


# === SVG ASSET STRINGS (Zero Emoji Policy) ===

SVG_GOOGLE = """
<svg viewBox="0 0 24 24" width="20" height="20">
  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
</svg>
"""

SVG_YOUTUBE = """
<svg viewBox="0 0 24 24" width="22" height="22">
  <rect x="2" y="4" width="20" height="16" rx="5" fill="#FF0000"/>
  <polygon points="10,8.5 16,12 10,15.5" fill="#FFFFFF"/>
</svg>
"""

SVG_SPOTIFY = """
<svg viewBox="0 0 24 24" width="22" height="22">
  <circle cx="12" cy="12" r="10" fill="#1DB954"/>
  <path d="M7 9.5c3.2-1 6.8-.8 9.5.8" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" fill="none"/>
  <path d="M7.8 12.2c2.6-.8 5.6-.6 7.8.7" stroke="#FFFFFF" stroke-width="1.5" stroke-linecap="round" fill="none"/>
  <path d="M8.5 14.8c2.1-.6 4.4-.5 6.1.5" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round" fill="none"/>
</svg>
"""

SVG_USER_AVATAR = """
<svg viewBox="0 0 24 24" width="20" height="20">
  <circle cx="12" cy="8" r="4" fill="#FF5B06"/>
  <path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8" fill="none" stroke="#FF5B06" stroke-width="2" stroke-linecap="round"/>
</svg>
"""

SVG_BACK_ARROW = """
<svg viewBox="0 0 24 24" width="16" height="16">
  <path d="M15 19l-7-7 7-7" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

SVG_DATABASE = """
<svg viewBox="0 0 24 24" width="18" height="18">
  <ellipse cx="12" cy="5" rx="9" ry="3" fill="none" stroke="#FF5B06" stroke-width="2"/>
  <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5" fill="none" stroke="#FF5B06" stroke-width="2"/>
  <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6" fill="none" stroke="#FF5B06" stroke-width="2"/>
</svg>
"""

SVG_REFRESH = """
<svg viewBox="0 0 24 24" width="16" height="16">
  <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3L21.5 8M22 12.5a10 10 0 0 1-18.8 4.2L2.5 16" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

SVG_SETTINGS = """
<svg viewBox="0 0 24 24" width="16" height="16">
  <circle cx="12" cy="12" r="3" fill="none" stroke="#FFFFFF" stroke-width="2"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

SVG_SEARCH = """
<svg viewBox="0 0 24 24" width="16" height="16">
  <circle cx="11" cy="11" r="7" fill="none" stroke="#7E849B" stroke-width="2"/>
  <line x1="16.5" y1="16.5" x2="21.5" y2="21.5" stroke="#7E849B" stroke-width="2" stroke-linecap="round"/>
</svg>
"""


def render_svg_pixmap(name_or_data: str, width: int = 20, height: int = 20) -> QPixmap:
    """Render an SVG file from UI Icons or raw SVG string into a crisp antialiased QPixmap."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "UI Icons", name_or_data).replace('\\', '/')
    if os.path.exists(file_path):
        renderer = QSvgRenderer(file_path)
    else:
        renderer = QSvgRenderer(name_or_data.strip().encode('utf-8'))
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    return pix


def render_colored_svg_pixmap(name_or_data: str, width: int = 16, height: int = 16, color_hex: str = "#FFFFFF") -> QPixmap:
    """Render an SVG file or data with a dynamic custom tint color via script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "UI Icons", name_or_data).replace('\\', '/')
    svg_content = ""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                svg_content = f.read()
        except Exception:
            svg_content = ""
    elif os.path.isabs(name_or_data) and os.path.exists(name_or_data):
        try:
            with open(name_or_data, "r", encoding="utf-8") as f:
                svg_content = f.read()
        except Exception:
            svg_content = ""
    else:
        svg_content = name_or_data.strip()

    if color_hex and svg_content:
        import re
        svg_content = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', f'fill="{color_hex}"', svg_content)
        svg_content = re.sub(r'stroke="#[0-9a-fA-F]{3,8}"', f'stroke="{color_hex}"', svg_content)

    renderer = QSvgRenderer(svg_content.encode('utf-8'))
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    return pix


SVG_CHEVRON_LEFT = """
<svg viewBox="0 0 24 24" width="14" height="14">
  <polyline points="15 18 9 12 15 6" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

SVG_CHEVRON_RIGHT = """
<svg viewBox="0 0 24 24" width="14" height="14">
  <polyline points="9 18 15 12 9 6" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

HORIZONTAL_SCROLLBAR_STYLE = """
    QScrollArea#%ID% {
        background: transparent;
        border: none;
    }
    QScrollArea#%ID% > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:horizontal {
        background: transparent;
        height: 10px;
        border-radius: 5px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
        border-radius: 4px;
        min-width: 40px;
        border: 1px solid rgba(253, 169, 3, 0.8);
    }
    QScrollBar::handle:horizontal:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
        border: 1px solid #FFFF00;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px; background: none; border: none;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: transparent;
    }
"""


def create_section_nav_button(object_name: str, is_next: bool = False, parent=None) -> QPushButton:
    btn = QPushButton(parent)
    btn.setObjectName(object_name)
    btn.setFixedSize(26, 26)
    btn.setCursor(Qt.PointingHandCursor)
    svg = SVG_CHEVRON_RIGHT if is_next else SVG_CHEVRON_LEFT
    btn.setIcon(QIcon(render_svg_pixmap(svg, 14, 14)))
    btn.setIconSize(QSize(14, 14))
    btn.setStyleSheet("""
        QPushButton {
            background-color: rgba(255, 255, 255, 0.06);
            border: none;
            border-radius: 13px;
            padding: 0px;
        }
        QPushButton:hover {
            background-color: #FF5B06;
        }
        QPushButton:pressed {
            background-color: #E04E00;
        }
    """)
    return btn


def scroll_horizontal_by_items(scroll_area: QScrollArea, direction: int, item_width: int, spacing: int = 12, count: int = 2):
    """Smooth animated horizontal scroll by N items (direction: -1 for Prev, 1 for Next)."""
    if not scroll_area or not scroll_area.horizontalScrollBar():
        return
    bar = scroll_area.horizontalScrollBar()
    step = (item_width + spacing) * count
    start_val = bar.value()
    end_val = max(bar.minimum(), min(bar.maximum(), start_val + (step * direction)))

    anim = QPropertyAnimation(bar, b"value", scroll_area)
    anim.setDuration(260)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.setStartValue(start_val)
    anim.setEndValue(end_val)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    scroll_area._scroll_anim = anim


class SvgHoverButton(QPushButton):
    """
    Component Name: svgHoverButton
    Dynamic button that changes its SVG icon tint color and background smoothly on idle vs hover.
    """
    def __init__(self, svg_name: str, size: int = 26, icon_size: int = 16,
                 idle_color: str = "#555968", hover_color: str = "#FFFFFF",
                 idle_bg: str = "#141722", hover_bg: str = "#222634", parent=None):
        super().__init__(parent)
        self.setObjectName("svgHoverButton")
        self.svg_name = svg_name
        self.icon_size = icon_size
        self.idle_color = idle_color
        self.hover_color = hover_color
        self.idle_bg = idle_bg
        self.hover_bg = hover_bg
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._update_state(False)

    def _update_state(self, is_hover: bool):
        color = self.hover_color if is_hover else self.idle_color
        bg = self.hover_bg if is_hover else self.idle_bg
        pix = render_colored_svg_pixmap(self.svg_name, self.icon_size, self.icon_size, color)
        self.setIcon(QIcon(pix))
        self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border-radius: 6px;
                border: none;
                padding: 0;
            }}
        """)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._update_state(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._update_state(False)


def make_pixmap_from_bytes(data_bytes: bytes, max_w: int = 360, max_h: int = 360) -> Optional[QPixmap]:
    """Safely construct a lightweight QPixmap from raw downloaded image bytes."""
    if not data_bytes:
        return None
    try:
        from ImageCacheEngine import ImageCacheEngine
        data_bytes = ImageCacheEngine.get_instance().downscale_image_bytes(data_bytes, max_w, max_h)
    except Exception:
        pass
    pix = QPixmap()
    if pix.loadFromData(data_bytes) and not pix.isNull():
        if pix.width() > max_w or pix.height() > max_h:
            pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return pix
    return None


def _safe_set_card_pixmap(card_widget, data_bytes: bytes, max_w: int = 360, max_h: int = 360):
    """Safely apply downscaled pixmap from downloaded bytes to a card widget even if it was deleted."""
    try:
        if card_widget is None:
            return
        # Test if C++ object is alive
        _ = card_widget.width()
        pix = make_pixmap_from_bytes(data_bytes, max_w, max_h)
        if pix:
            card_widget.set_pixmap(pix)
    except (RuntimeError, AttributeError):
        pass
    except Exception:
        pass





class AsyncImageLoader(QThread):
    """Bounded asynchronous thumbnail downloader utilizing C++ WIC / WinHTTP with 0% GIL locking."""
    loaded = Signal(str, bytes)
    _pool_semaphore = threading.Semaphore(3)  # Max 3 concurrent network requests to prevent thread explosion

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled or not self.url:
            return

        # 1. Tier 0/1: Instant Memory & Disk Cache Check (<1ms, no semaphore needed)
        try:
            from ImageCacheEngine import ImageCacheEngine
            cached = ImageCacheEngine.get_instance().get_bytes(self.url)
            if cached and not self._is_cancelled:
                self.loaded.emit(self.url, cached)
                return
        except Exception:
            pass

        # 2. Bounded Concurrency: Only 3 workers active simultaneously
        with AsyncImageLoader._pool_semaphore:
            if self._is_cancelled:
                return

            # Check cache again in case another worker already cached it
            try:
                from ImageCacheEngine import ImageCacheEngine
                cached = ImageCacheEngine.get_instance().get_bytes(self.url)
                if cached and not self._is_cancelled:
                    self.loaded.emit(self.url, cached)
                    return
            except Exception:
                pass

            # 3. Fast C++ WinHTTP download + WIC hardware downscale if native module available
            try:
                import image_cache_native
                downscaled = image_cache_native.fetch_and_downscale(self.url, 360, 360)
                if downscaled and not self._is_cancelled:
                    try:
                        from ImageCacheEngine import ImageCacheEngine
                        ImageCacheEngine.get_instance().put_bytes(self.url, downscaled)
                    except Exception:
                        pass
                    self.loaded.emit(self.url, downscaled)
                    return
            except Exception:
                pass

            # 4. Resilient Python Network Fallback
            try:
                req = urllib.request.Request(
                    self.url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=6.0, context=ctx) as resp:
                    data = resp.read()
                    if not self._is_cancelled and data:
                        try:
                            from ImageCacheEngine import ImageCacheEngine
                            ImageCacheEngine.get_instance().put_bytes(self.url, data)
                            downscaled = ImageCacheEngine.get_instance().get_bytes(self.url) or data
                        except Exception:
                            downscaled = data
                        self.loaded.emit(self.url, downscaled)
            except Exception:
                pass


class RecommendationWorker(QThread):
    """Background worker that resolves on-device taste queries into 4 real, active YouTube LIVE streams."""
    recommendationsReady = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        try:
            target_count = 8
            if hasattr(self.parent(), 'featured_video_cards') and self.parent().featured_video_cards:
                target_count = len(self.parent().featured_video_cards)

            if TasteProfileEngine.is_cache_fresh():
                cached = TasteProfileEngine.load_cached_recommendations()
                if cached and len(cached) == target_count and not self._is_cancelled:
                    self.recommendationsReady.emit(cached)
                    return

            queries = TasteProfileEngine.get_user_taste_queries()
            results = []
            seen_ids = set()

            for q_obj in queries:
                if self._is_cancelled:
                    return
                query = q_obj.get("query", "")
                artist_name = q_obj.get("artist", "")
                preset = q_obj.get("preset_data")

                resolved_item = None
                try:
                    # 1. First try finding active live stream for artist
                    candidates = InnertubeSearchClient.search(f"{query} live stream", limit=3, live_only=True)
                    if not candidates:
                        # 2. Then try finding official video / performance (live_only=False)
                        candidates = InnertubeSearchClient.search(f"{query}", limit=4, live_only=False)
                    if not candidates:
                        candidates = InnertubeSearchClient.search(f"{artist_name} official", limit=4, live_only=False)

                    for cand in candidates:
                        vid_id = cand.get("id", "")
                        if vid_id and vid_id not in seen_ids:
                            seen_ids.add(vid_id)
                            is_live = cand.get("is_live", False)
                            resolved_item = {
                                "title": cand.get("title", query),
                                "artist": cand.get("uploader", artist_name or "Featured"),
                                "subtitle": cand.get("uploader", "YouTube Video"),
                                "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                "video_id": vid_id,
                                "thumbnail_url": cand.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                                "duration": cand.get("duration", 0),
                                "badge": "LIVE" if is_live else q_obj.get("badge", "RECOMMENDED"),
                                "bg_colors": q_obj.get("bg_colors", ["#1e1f29", "#2a2b38"]),
                                "is_online": True,
                                "is_stream": True,
                                "is_live": is_live
                            }
                            break
                except Exception:
                    pass

                if not resolved_item and preset:
                    preset_query = preset.get("original_url", "")
                    try:
                        fallback_cands = InnertubeSearchClient.search(preset_query, limit=3, live_only=False)
                        for cand in fallback_cands:
                            vid_id = cand.get("id", "")
                            if vid_id and vid_id not in seen_ids:
                                seen_ids.add(vid_id)
                                is_live = cand.get("is_live", False)
                                resolved_item = {
                                    "title": cand.get("title", preset.get("title", "Featured Music")),
                                    "artist": cand.get("uploader", preset.get("artist", "Featured")),
                                    "subtitle": cand.get("uploader", preset.get("subtitle", "YouTube Stream")),
                                    "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                    "video_id": vid_id,
                                    "thumbnail_url": cand.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                                    "duration": cand.get("duration", 0),
                                    "badge": "LIVE" if is_live else preset.get("badge", "FEATURED"),
                                    "bg_colors": preset.get("bg_colors", ["#1e1f29", "#2a2b38"]),
                                    "is_online": True,
                                    "is_stream": True,
                                    "is_live": is_live
                                }
                                break
                    except Exception:
                        pass

                if not resolved_item and preset:
                    resolved_item = dict(preset)

                if resolved_item:
                    results.append(resolved_item)

            if results and not self._is_cancelled:
                TasteProfileEngine.save_cached_recommendations(results)
                self.recommendationsReady.emit(results)
        except Exception:
            pass


class StreamSearchWorker(QThread):
    """Non-blocking background search worker executing Canonical + Innertube search."""
    resultsReady = Signal(int, dict, list)
    searchFailed = Signal(int, str)

    def __init__(self, query: str, seq_id: int, parent=None):
        super().__init__(parent)
        self.query = query.strip()
        self.seq_id = seq_id
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled or not self.query:
            return

        try:
            results = InnertubeSearchClient.search(self.query, limit=10)
            if self._is_cancelled:
                return

            if not results:
                self.searchFailed.emit(self.seq_id, 'No search results found')
                return

            hero_data = results[0]
            candidates = results[1:]

            if self._is_cancelled:
                return

            self.resultsReady.emit(self.seq_id, hero_data, candidates)
        except Exception as e:
            if not self._is_cancelled:
                self.searchFailed.emit(self.seq_id, str(e))






class YouTubeCookieImportDialog(QDialog):
    """
    Modal Cyberpunk Dialog for importing Netscape cookies.txt or pasting raw cookie strings.
    Component Name: youtubeCookieImportDialog
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("youtubeCookieImportDialog")
        self.setWindowTitle("Import YouTube Cookies - HELXAID")
        self.setFixedSize(540, 460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog#youtubeCookieImportDialog {
                background-color: #12141D;
                border-radius: 12px;
            }
        """)
        self._detected_file_path = None
        self._setup_ui()
        QTimer.singleShot(150, self._auto_detect_sources)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setObjectName("ytCookieDialogIcon")
        icon_lbl.setPixmap(render_svg_pixmap(SVG_YOUTUBE, 22, 22))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("IMPORT YOUTUBE COOKIES", self)
        title_lbl.setObjectName("ytCookieDialogTitle")
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        desc = QLabel("Auto-detects cookies from Clipboard & Downloads, or select your cookies.txt:", self)
        desc.setObjectName("ytCookieDialogDesc")
        desc.setStyleSheet("color: #8C90A0; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Smart Auto-Load Banner Button (shown when file in Downloads is found)
        self.auto_file_btn = QPushButton("⚡ Auto-Load Cookie File from Downloads", self)
        self.auto_file_btn.setObjectName("ytCookieAutoFileBtn")
        self.auto_file_btn.setFixedHeight(34)
        self.auto_file_btn.setCursor(Qt.PointingHandCursor)
        self.auto_file_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E676, stop:1 #00B0FF);
                color: #0A120D;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
                padding: 4px 12px;
            }
            QPushButton:hover { background: #00E676; color: #000000; }
        """)
        self.auto_file_btn.clicked.connect(self._load_detected_file)
        self.auto_file_btn.hide()
        layout.addWidget(self.auto_file_btn)

        # File Import Row
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        file_btn = QPushButton("📁 Browse cookies.txt...", self)
        file_btn.setObjectName("ytCookieBrowseBtn")
        file_btn.setFixedHeight(34)
        file_btn.setCursor(Qt.PointingHandCursor)
        file_btn.setStyleSheet("""
            QPushButton {
                background-color: #181B26;
                color: #00E5FF;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                border: 1px solid rgba(0, 229, 255, 0.3);
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #222738; }
        """)
        file_btn.clicked.connect(self._browse_cookie_file)
        file_row.addWidget(file_btn, stretch=1)

        auto_scan_btn = QPushButton("⚡ Auto-Scan", self)
        auto_scan_btn.setObjectName("ytCookieAutoScanBtn")
        auto_scan_btn.setFixedHeight(34)
        auto_scan_btn.setCursor(Qt.PointingHandCursor)
        auto_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A2030;
                color: #FFFFFF;
                font-family: 'Orbitron';
                font-size: 9px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #262E44; color: #00E676; }
        """)
        auto_scan_btn.clicked.connect(self._auto_detect_sources)
        file_row.addWidget(auto_scan_btn)
        layout.addLayout(file_row)

        or_lbl = QLabel("— OR PASTE RAW COOKIE HEADER / JSON —", self)
        or_lbl.setObjectName("ytCookieOrLabel")
        or_lbl.setAlignment(Qt.AlignCenter)
        or_lbl.setStyleSheet("color: #555968; font-size: 9px; font-weight: bold;")
        layout.addWidget(or_lbl)

        from PySide6.QtWidgets import QTextEdit
        self.cookie_text = QTextEdit(self)
        self.cookie_text.setObjectName("ytCookieTextEdit")
        self.cookie_text.setPlaceholderText("Paste cookies (e.g. SAPISID=...; SID=...) or JSON array from Cookie-Editor extension...")
        self.cookie_text.setStyleSheet("""
            QTextEdit {
                background-color: #161822;
                color: #E0E2EC;
                font-family: monospace;
                font-size: 10px;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                padding: 6px;
            }
            QTextEdit:focus {
                border: 1px solid #FF0000;
            }
        """)
        layout.addWidget(self.cookie_text, stretch=1)

        self.status_lbl = QLabel("", self)
        self.status_lbl.setObjectName("ytCookieStatusLabel")
        self.status_lbl.setStyleSheet("color: #FFA726; font-size: 10px;")
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        import_btn = QPushButton("Link Session", self)
        import_btn.setObjectName("ytCookieSubmitBtn")
        import_btn.setFixedHeight(32)
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF0000, stop:1 #CC0000);
                color: #FFFFFF;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background: #FF1A1A; }
        """)
        import_btn.clicked.connect(self._import_pasted_cookies)
        btn_row.addWidget(import_btn, stretch=1)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("ytCookieCancelBtn")
        cancel_btn.setFixedHeight(32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("background-color: #181B26; color: #8C90A0; font-size: 10px; border-radius: 6px; border: none;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _auto_detect_sources(self):
        """Auto-detect YouTube cookies from active browsers, Clipboard, or recent downloads."""
        # 1. Direct 1-Click extraction from installed desktop browsers (Chrome, Edge, Brave)
        try:
            from utils.cookie_exporter import CookieExporter
            exporter = CookieExporter()
            ok, browser, cookies_dict = exporter.auto_import_youtube_cookies()
            if ok and cookies_dict:
                user_name = f"Google / YouTube User ({browser.capitalize()})"
                yt_eng = YouTubeAccountEngine.get_instance()
                success, msg = yt_eng.import_cookies_dict(cookies_dict, user_name)
                if success:
                    yt_eng.fetch_account_info(async_call=True)
                    self.status_lbl.setStyleSheet("color: #00E676; font-weight: bold; font-size: 11px;")
                    self.status_lbl.setText(f"✓ Successfully auto-synced YouTube session from {browser.capitalize()}!")
                    QTimer.singleShot(400, self.accept)
                    return
        except Exception:
            pass

        # 2. Check Windows Clipboard
        try:
            from PySide6.QtGui import QGuiApplication
            clip_txt = QGuiApplication.clipboard().text().strip()
            if clip_txt and ("SAPISID" in clip_txt or "SID" in clip_txt or ("[" in clip_txt and "youtube.com" in clip_txt)):
                self.cookie_text.setPlainText(clip_txt)
                self.status_lbl.setStyleSheet("color: #00E676; font-weight: bold; font-size: 11px;")
                self.status_lbl.setText("✓ Auto-detected YouTube cookies from Clipboard! Click 'Link Session'.")
                return
        except Exception:
            pass

        # 3. Check Downloads folder for recent cookie exports
        try:
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                candidate_files = []
                for fname in os.listdir(downloads_dir):
                    if fname.lower().endswith((".txt", ".json")) and any(k in fname.lower() for k in ["cookie", "youtube", "music"]):
                        fpath = os.path.join(downloads_dir, fname)
                        if os.path.isfile(fpath):
                            candidate_files.append((os.path.getmtime(fpath), fpath))

                if candidate_files:
                    candidate_files.sort(key=lambda x: x[0], reverse=True)
                    latest_mtime, latest_path = candidate_files[0]
                    if (time.time() - latest_mtime) < 86400 * 3:
                        self._detected_file_path = latest_path
                        self.auto_file_btn.setText(f"⚡ Auto-Load: {os.path.basename(latest_path)}")
                        self.auto_file_btn.show()
                        self.status_lbl.setStyleSheet("color: #00E5FF; font-size: 11px;")
                        self.status_lbl.setText(f"Found exported cookie file in Downloads: {os.path.basename(latest_path)}")
                        return
        except Exception:
            pass

        self.status_lbl.setStyleSheet("color: #8C90A0; font-size: 10px;")
        self.status_lbl.setText("Tip: Copy cookie from Cookie-Editor extension or browse your cookies.txt.")

    def _load_detected_file(self):
        if self._detected_file_path and os.path.exists(self._detected_file_path):
            ok, msg = YouTubeAccountEngine.get_instance().import_cookies_txt(self._detected_file_path)
            if ok:
                self.accept()
            else:
                self.status_lbl.setStyleSheet("color: #FFA726; font-size: 10px;")
                self.status_lbl.setText(f"⚠️ {msg}")

    def _browse_cookie_file(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt file", "", "Text Files (*.txt);;All Files (*.*)")
        if path:
            ok, msg = YouTubeAccountEngine.get_instance().import_cookies_txt(path)
            if ok:
                self.accept()
            else:
                self.status_lbl.setStyleSheet("color: #FFA726; font-size: 10px;")
                self.status_lbl.setText(f"⚠️ {msg}")

    def _import_pasted_cookies(self):
        txt = self.cookie_text.toPlainText().strip()
        if not txt:
            self.status_lbl.setStyleSheet("color: #FFA726; font-size: 10px;")
            self.status_lbl.setText("⚠️ Please paste cookie string or choose a file.")
            return
        ok, msg = YouTubeAccountEngine.get_instance().import_raw_cookie_string(txt)
        if ok:
            self.accept()
        else:
            self.status_lbl.setStyleSheet("color: #FFA726; font-size: 10px;")
            self.status_lbl.setText(f"⚠️ {msg}")



class GoogleCredentialsDialog(QDialog):
    """
    Modal Cyberpunk Dialog for configuring Google / YouTube OAuth2 Application Credentials.
    Component Name: googleCredentialsDialog
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("googleCredentialsDialog")
        self.setWindowTitle("Google / YouTube API Configuration")
        self.setFixedSize(540, 430)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog#googleCredentialsDialog {
                background-color: #12141D;
                border-radius: 12px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setObjectName("googleDialogIcon")
        icon_lbl.setPixmap(render_svg_pixmap(SVG_YOUTUBE, 24, 24))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("GOOGLE / YOUTUBE API CREDENTIALS", self)
        title_lbl.setObjectName("googleDialogTitle")
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 900; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        desc_lbl = QLabel("Enter your Google Cloud OAuth2 Client ID to enable 1-Click Browser Login for YouTube Music.", self)
        desc_lbl.setObjectName("googleDialogDesc")
        desc_lbl.setStyleSheet("color: #8C90A0; font-size: 11px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Instruction Box
        guide_box = QFrame(self)
        guide_box.setObjectName("googleDialogGuideBox")
        guide_box.setStyleSheet("background: #181B26; border-radius: 8px; padding: 10px;")
        g_layout = QVBoxLayout(guide_box)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(3)

        g_title = QLabel("HOW TO GET YOUR GOOGLE OAUTH CLIENT ID (1 MINUTE):", guide_box)
        g_title.setObjectName("googleGuideTitle")
        g_title.setStyleSheet("color: #FF5252; font-family: 'Orbitron'; font-size: 9px; font-weight: bold;")
        g_layout.addWidget(g_title)

        steps = [
            "1. Open Google Cloud Console (Credentials).",
            "2. Click 'Create Credentials' -> 'OAuth client ID' -> Type: 'Web application'.",
            "3. Add Authorized Redirect URI: http://127.0.0.1:8888/callback",
            "4. Copy your Client ID and Client Secret, and paste them below."
        ]
        for s in steps:
            s_lbl = QLabel(s, guide_box)
            s_lbl.setObjectName("googleGuideStep")
            s_lbl.setStyleSheet("color: #A0A4B5; font-size: 10px;")
            g_layout.addWidget(s_lbl)
        layout.addWidget(guide_box)

        # Input Fields
        input_col = QVBoxLayout()
        input_col.setSpacing(6)

        cid_lbl = QLabel("GOOGLE CLIENT ID:", self)
        cid_lbl.setObjectName("googleCidLabel")
        cid_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 9px; font-weight: bold;")
        input_col.addWidget(cid_lbl)

        self.cid_edit = QLineEdit(self)
        self.cid_edit.setObjectName("googleCidEdit")
        self.cid_edit.setFixedHeight(32)
        self.cid_edit.setPlaceholderText("e.g. 123456789-abc.apps.googleusercontent.com")
        curr_id = YouTubeAccountEngine.get_instance().get_client_id()
        if curr_id:
            self.cid_edit.setText(curr_id)
        self.cid_edit.setStyleSheet("background: #181B26; color: #FFFFFF; border-radius: 6px; padding: 4px 10px; font-size: 11px; border: none;")
        input_col.addWidget(self.cid_edit)

        sec_lbl = QLabel("GOOGLE CLIENT SECRET (OPTIONAL):", self)
        sec_lbl.setObjectName("googleSecretLabel")
        sec_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 9px; font-weight: bold;")
        input_col.addWidget(sec_lbl)

        self.sec_edit = QLineEdit(self)
        self.sec_edit.setObjectName("googleSecretEdit")
        self.sec_edit.setFixedHeight(32)
        self.sec_edit.setPlaceholderText("e.g. GOCSPX-...")
        curr_sec = YouTubeAccountEngine.get_instance().get_client_secret()
        if curr_sec:
            self.sec_edit.setText(curr_sec)
        self.sec_edit.setStyleSheet("background: #181B26; color: #FFFFFF; border-radius: 6px; padding: 4px 10px; font-size: 11px; border: none;")
        input_col.addWidget(self.sec_edit)

        layout.addLayout(input_col)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        dash_btn = QPushButton("Open Cloud Console", self)
        dash_btn.setObjectName("googleOpenDashBtn")
        dash_btn.setFixedHeight(32)
        dash_btn.setCursor(Qt.PointingHandCursor)
        dash_btn.setStyleSheet("background: #1F2230; color: #8C90A0; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 4px 12px; border: none;")
        dash_btn.clicked.connect(lambda: os.startfile("https://console.cloud.google.com/apis/credentials") if hasattr(os, 'startfile') else None)
        btn_row.addWidget(dash_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("googleDialogCancelBtn")
        cancel_btn.setFixedHeight(32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("background: #181B24; color: #8C90A0; font-size: 10px; border-radius: 6px; padding: 4px 12px; border: none;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save & Login", self)
        save_btn.setObjectName("googleDialogSaveBtn")
        save_btn.setFixedHeight(32)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF0000, stop:1 #CC0000); color: #FFFFFF; font-family: 'Orbitron'; font-size: 10px; font-weight: bold; border-radius: 6px; padding: 4px 18px; border: none;")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self):
        cid = self.cid_edit.text().strip()
        sec = self.sec_edit.text().strip()
        if not cid:
            self.cid_edit.setPlaceholderText("Please enter a valid Google Client ID!")
            return
        YouTubeAccountEngine.get_instance().set_client_credentials(cid, sec)
        self.accept()
        YouTubeAccountEngine.get_instance().start_oauth_flow()


class SpotifyCredentialsDialog(QDialog):
    """
    Modal Cyberpunk Dialog for configuring Spotify Developer Application Credentials.
    Component Name: spotifyCredentialsDialog
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("spotifyCredentialsDialog")
        self.setWindowTitle("Spotify API Configuration")
        self.setFixedSize(520, 390)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog#spotifyCredentialsDialog {
                background-color: #12141D;
                border-radius: 12px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setObjectName("spotifyDialogIcon")
        icon_lbl.setPixmap(render_svg_pixmap("spotify-icon.svg", 24, 24))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("SPOTIFY API CREDENTIALS", self)
        title_lbl.setObjectName("spotifyDialogTitle")
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: 900; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        desc_lbl = QLabel("Enter your Spotify Developer Client ID to enable 1-Click OAuth2 PKCE sync. Streaming works with high-speed unthrottled resolution.", self)
        desc_lbl.setObjectName("spotifyDialogDesc")
        desc_lbl.setStyleSheet("color: #8C90A0; font-size: 11px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Instruction Box
        guide_box = QFrame(self)
        guide_box.setObjectName("spotifyDialogGuideBox")
        guide_box.setStyleSheet("background: #181B26; border-radius: 8px; padding: 10px;")
        g_layout = QVBoxLayout(guide_box)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(4)

        g_title = QLabel("HOW TO GET YOUR FREE CLIENT ID (1 MINUTE):", guide_box)
        g_title.setObjectName("spotifyGuideTitle")
        g_title.setStyleSheet("color: #1DB954; font-family: 'Orbitron'; font-size: 9px; font-weight: bold;")
        g_layout.addWidget(g_title)

        steps = [
            "1. Open Spotify Developer Dashboard and log in.",
            "2. Click 'Create App' -> Name: HELXAIC -> Check 'Web API'.",
            "3. Set Redirect URI to: http://127.0.0.1:8888/callback",
            "4. Copy your Client ID and paste it below."
        ]
        for s in steps:
            s_lbl = QLabel(s, guide_box)
            s_lbl.setObjectName("spotifyGuideStep")
            s_lbl.setStyleSheet("color: #A0A4B5; font-size: 10px;")
            g_layout.addWidget(s_lbl)
        layout.addWidget(guide_box)

        # Input Field
        input_col = QVBoxLayout()
        input_col.setSpacing(4)
        cid_lbl = QLabel("SPOTIFY CLIENT ID:", self)
        cid_lbl.setObjectName("spotifyCidLabel")
        cid_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 9px; font-weight: bold;")
        input_col.addWidget(cid_lbl)

        self.cid_edit = QLineEdit(self)
        self.cid_edit.setObjectName("spotifyCidEdit")
        self.cid_edit.setFixedHeight(34)
        self.cid_edit.setPlaceholderText("e.g. 0d2c94380ec843c08e5be2d5a1b32d20...")
        curr_id = SpotifyAccountEngine.get_instance().get_client_id()
        if curr_id:
            self.cid_edit.setText(curr_id)
        self.cid_edit.setStyleSheet("""
            QLineEdit#spotifyCidEdit {
                background: #181B26;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                border: none;
            }
            QLineEdit#spotifyCidEdit:focus {
                background: #1C202E;
            }
        """)
        input_col.addWidget(self.cid_edit)
        layout.addLayout(input_col)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        dash_btn = QPushButton("Open Dashboard", self)
        dash_btn.setObjectName("spotifyOpenDashBtn")
        dash_btn.setFixedHeight(32)
        dash_btn.setCursor(Qt.PointingHandCursor)
        dash_btn.setStyleSheet("""
            QPushButton#spotifyOpenDashBtn {
                background: #1F2230;
                color: #8C90A0;
                font-family: 'Orbitron';
                font-size: 9px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 12px;
                border: none;
            }
            QPushButton#spotifyOpenDashBtn:hover {
                color: #FFFFFF;
                background: #282C3D;
            }
        """)
        dash_btn.clicked.connect(lambda: os.startfile("https://developer.spotify.com/dashboard") if hasattr(os, 'startfile') else None)
        btn_row.addWidget(dash_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("spotifyDialogCancelBtn")
        cancel_btn.setFixedHeight(32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton#spotifyDialogCancelBtn {
                background: #181B24;
                color: #8C90A0;
                font-size: 10px;
                border-radius: 6px;
                padding: 4px 12px;
                border: none;
            }
            QPushButton#spotifyDialogCancelBtn:hover { color: #FFFFFF; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save & Connect", self)
        save_btn.setObjectName("spotifyDialogSaveBtn")
        save_btn.setFixedHeight(32)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton#spotifyDialogSaveBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1DB954, stop:1 #179E45);
                color: #FFFFFF;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 18px;
                border: none;
            }
            QPushButton#spotifyDialogSaveBtn:hover { background: #1ED760; }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self):
        cid = self.cid_edit.text().strip()
        if not cid:
            self.cid_edit.setPlaceholderText("Please enter a valid Spotify Client ID!")
            return
        SpotifyAccountEngine.get_instance().set_client_id(cid)
        self.accept()
        SpotifyAccountEngine.get_instance().start_oauth_flow()


class CloudProfileView(QWidget):
    """
    Dedicated Cyberpunk Cloud Streaming Identity & Profile Hub.
    Component Name: cloudProfileView
    """
    backClicked = Signal()
    accountsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cloudProfileView")
        self.setStyleSheet("QWidget#cloudProfileView { background: transparent; }")
        self._yt_sync_worker: Optional[SyncYTCookiesWorker] = None
        YouTubeAccountEngine.get_instance().cookiesReceived.connect(self._on_extension_cookies_received)
        YouTubeAccountEngine.get_instance().sessionChanged.connect(lambda ok, u: self.refresh_state())
        YouTubeAccountEngine.get_instance().accountDetailsUpdated.connect(lambda d: self.refresh_state())
        self._setup_ui()

    def _on_extension_cookies_received(self, cookies: dict):
        print("[CloudProfileView] YouTube session synchronized in real-time from Chrome Extension!")
        self.refresh_state()
        self.accountsChanged.emit()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 14, 0)
        layout.setSpacing(20)

        # 1. Top Navigation Bar
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        back_btn = QPushButton(self)
        back_btn.setObjectName("profileBackBtn")
        back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            back_btn.setIcon(QIcon(back_icon_path))
            back_btn.setIconSize(QSize(15, 15))
        else:
            back_btn.setIcon(QIcon(render_svg_pixmap(SVG_BACK_ARROW, 15, 15)))
            back_btn.setIconSize(QSize(15, 15))
        back_btn.setToolTip("Back to Direct Stream")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton#profileBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#profileBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        back_btn.clicked.connect(self.backClicked.emit)
        nav_row.addWidget(back_btn)

        title_lbl = QLabel("STREAMING IDENTITY & CLOUD HUB", self)
        title_lbl.setObjectName("profileHeaderTitle")
        title_lbl.setStyleSheet("""
            QLabel#profileHeaderTitle {
                color: #FFFFFF;
                font-family: 'Orbitron', sans-serif;
                font-size: 17px;
                font-weight: 900;
                letter-spacing: 1px;
            }
        """)
        nav_row.addWidget(title_lbl)
        nav_row.addStretch()

        self.global_status_pill = QLabel("AUTHENTICATION STATUS", self)
        self.global_status_pill.setObjectName("profileGlobalStatus")
        self.global_status_pill.setStyleSheet("""
            QLabel#profileGlobalStatus {
                background: #161822;
                color: #8C90A0;
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        nav_row.addWidget(self.global_status_pill)

        layout.addLayout(nav_row)

        # 2. Hero Identity Overview Card
        self.hero_card = QFrame(self)
        self.hero_card.setObjectName("cloudHeroBanner")
        self.hero_card.setStyleSheet("""
            QFrame#cloudHeroBanner {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #181B26, stop:1 #11131A);
                border-radius: 12px;
            }
        """)
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(14)

        self.hero_avatar_lbl = QLabel(self.hero_card)
        self.hero_avatar_lbl.setObjectName("cloudHeroAvatar")
        self.hero_avatar_lbl.setPixmap(render_svg_pixmap(SVG_USER_AVATAR, 42, 42))
        self.hero_avatar_lbl.setFixedSize(48, 48)
        self.hero_avatar_lbl.setAlignment(Qt.AlignCenter)
        self.hero_avatar_lbl.setStyleSheet("background: #0E1017; border-radius: 24px;")
        hero_layout.addWidget(self.hero_avatar_lbl)

        hero_info = QVBoxLayout()
        hero_info.setSpacing(3)

        self.hero_user_name = QLabel("HELXAIC STREAMING IDENTITY", self.hero_card)
        self.hero_user_name.setObjectName("cloudHeroUserName")
        self.hero_user_name.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: 900;")
        hero_info.addWidget(self.hero_user_name)

        self.hero_user_desc = QLabel("Sync YouTube Music or Spotify below to unlock cloud feeds, supermixes, and playlists.", self.hero_card)
        self.hero_user_desc.setObjectName("cloudHeroUserDesc")
        self.hero_user_desc.setStyleSheet("color: #BAC0D4; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 500;")
        hero_info.addWidget(self.hero_user_desc)

        hero_layout.addLayout(hero_info, stretch=1)

        # Status Pill
        hero_actions = QHBoxLayout()
        hero_actions.setSpacing(8)

        self.hero_status_pill = QLabel("SESSION STATUS", self.hero_card)
        self.hero_status_pill.setObjectName("cloudHeroStatusPill")
        self.hero_status_pill.setStyleSheet("background: #141722; color: #8C90A0; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        hero_actions.addWidget(self.hero_status_pill)

        hero_layout.addLayout(hero_actions)
        layout.addWidget(self.hero_card)

        # 3. Two Cloud Service Cards (Side-by-Side)
        cards_grid = QGridLayout()
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(12)

        # --- Card A: YouTube Music Hub ---
        self.yt_card = QFrame(self)
        self.yt_card.setObjectName("ytCloudCard")
        self.yt_card.setStyleSheet("""
            QFrame#ytCloudCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E0D0D, stop:0.4 #181419, stop:1 #111319);
                border-radius: 12px;
            }
        """)
        yt_layout = QVBoxLayout(self.yt_card)
        yt_layout.setContentsMargins(14, 14, 14, 14)
        yt_layout.setSpacing(12)

        yt_header_row = QHBoxLayout()
        yt_icon_lbl = QLabel(self.yt_card)
        yt_icon_lbl.setObjectName("ytCloudCardIcon")
        yt_icon_lbl.setPixmap(render_svg_pixmap(SVG_YOUTUBE, 22, 22))
        yt_header_row.addWidget(yt_icon_lbl)

        yt_title = QLabel("YOUTUBE MUSIC", self.yt_card)
        yt_title.setObjectName("ytCloudCardTitle")
        yt_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 900; letter-spacing: 0.5px;")
        yt_header_row.addWidget(yt_title)
        yt_header_row.addStretch()

        self.yt_badge = QLabel("UNLINKED", self.yt_card)
        self.yt_badge.setObjectName("ytCloudCardBadge")
        self.yt_badge.setFixedHeight(22)
        self.yt_badge.setAlignment(Qt.AlignCenter)
        self.yt_badge.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); color: #7A7E8F; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
        yt_header_row.addWidget(self.yt_badge)

        self.yt_options_btn = SvgHoverButton(
            "more-vertical.svg",
            size=26,
            icon_size=16,
            idle_color="#555968",
            hover_color="#FFFFFF",
            idle_bg="#141722",
            hover_bg="#222634",
            parent=self.yt_card
        )
        self.yt_options_btn.setObjectName("ytCloudOptionsBtn")
        self.yt_options_btn.setToolTip("Advanced Options (Browser Selection, Cookie Import)")
        self.yt_options_btn.clicked.connect(self._show_yt_options_menu)
        yt_header_row.addWidget(self.yt_options_btn)

        yt_layout.addLayout(yt_header_row)

        self.yt_status_lbl = QLabel("1-Click Smart Google sync from active browser session.", self.yt_card)
        self.yt_status_lbl.setObjectName("ytCloudCardStatus")
        self.yt_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
        self.yt_status_lbl.setWordWrap(True)
        yt_layout.addWidget(self.yt_status_lbl)

        # Synced Account Information Box (Shown when authenticated)
        self.yt_account_box = QFrame(self.yt_card)
        self.yt_account_box.setObjectName("ytCloudAccountBox")
        self.yt_account_box.setStyleSheet("""
            QFrame#ytCloudAccountBox {
                background-color: #0E1017;
                border-radius: 6px;
            }
        """)
        yt_acc_layout = QHBoxLayout(self.yt_account_box)
        yt_acc_layout.setContentsMargins(10, 8, 10, 8)
        yt_acc_layout.setSpacing(10)

        self.yt_account_avatar_lbl = QLabel(self.yt_account_box)
        self.yt_account_avatar_lbl.setObjectName("ytCloudAccountAvatar")
        self.yt_account_avatar_lbl.setPixmap(render_svg_pixmap(SVG_USER_AVATAR, 20, 20))
        yt_acc_layout.addWidget(self.yt_account_avatar_lbl)

        yt_acc_info_layout = QVBoxLayout()
        yt_acc_info_layout.setSpacing(2)
        self.yt_account_name_lbl = QLabel("SYNCED ACCOUNT", self.yt_account_box)
        self.yt_account_name_lbl.setObjectName("ytCloudAccountName")
        self.yt_account_name_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")

        self.yt_account_sub_lbl = QLabel("Session active and synchronized", self.yt_account_box)
        self.yt_account_sub_lbl.setObjectName("ytCloudAccountSub")
        self.yt_account_sub_lbl.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 11px; font-weight: 600; letter-spacing: 0.3px;")

        yt_acc_info_layout.addWidget(self.yt_account_name_lbl)
        yt_acc_info_layout.addWidget(self.yt_account_sub_lbl)
        yt_acc_layout.addLayout(yt_acc_info_layout, stretch=1)

        self.yt_account_box.hide()
        yt_layout.addWidget(self.yt_account_box)

        # Feature pills
        yt_features = QHBoxLayout()
        yt_features.setSpacing(6)
        for idx, feat in enumerate(["Liked Songs (LM)", "Playlists", "Supermix"]):
            f_lbl = QLabel(feat, self.yt_card)
            f_lbl.setObjectName(f"ytCloudFeaturePill_{idx}")
            f_lbl.setStyleSheet("background: #0E1015; color: #9DA3B8; font-family: 'Orbitron'; font-size: 10px; font-weight: 600; border-radius: 4px; padding: 4px 8px;")
            yt_features.addWidget(f_lbl)
        yt_features.addStretch()
        yt_layout.addLayout(yt_features)

        yt_actions = QHBoxLayout()
        yt_actions.setSpacing(8)

        self.yt_sync_btn = QPushButton("Sync YouTube Music", self.yt_card)
        self.yt_sync_btn.setObjectName("ytCloudSyncBtn")
        self.yt_sync_btn.setFixedHeight(32)
        self.yt_sync_btn.setCursor(Qt.PointingHandCursor)
        self.yt_sync_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF0000, stop:1 #CC0000);
                color: #FFFFFF;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 18px;
                border: none;
            }
            QPushButton:hover { background: #FF1A1A; }
            QPushButton:disabled { background: #3A1515; color: #8C8080; }
        """)
        self.yt_sync_btn.clicked.connect(self._auto_sync_browser)
        yt_actions.addWidget(self.yt_sync_btn, stretch=1)

        self.yt_import_btn = QPushButton("Manual / File", self.yt_card)
        self.yt_import_btn.setObjectName("ytCloudImportCookiesBtn")
        self.yt_import_btn.setFixedHeight(32)
        self.yt_import_btn.setCursor(Qt.PointingHandCursor)
        self.yt_import_btn.setStyleSheet("""
            QPushButton {
                background: #181B26;
                color: #00E5FF;
                font-family: 'Orbitron';
                font-size: 9px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 14px;
                border: 1px solid rgba(0, 229, 255, 0.3);
            }
            QPushButton:hover { background: #222738; }
            QPushButton:disabled { background: #1B202A; color: #555A6B; }
        """)
        self.yt_import_btn.clicked.connect(self._open_youtube_cookie_dialog)
        yt_actions.addWidget(self.yt_import_btn)

        self.yt_disc_btn = QPushButton("Disconnect", self.yt_card)
        self.yt_disc_btn.setObjectName("ytCloudLogoutBtn")
        self.yt_disc_btn.setFixedHeight(32)
        self.yt_disc_btn.setCursor(Qt.PointingHandCursor)
        self.yt_disc_btn.setStyleSheet("""
            QPushButton {
                background: #1A1D27;
                color: #A4A9BD;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 600;
                border-radius: 6px;
                padding: 4px 10px;
                border: none;
            }
            QPushButton:hover { color: #FF5252; background: #222634; }
        """)
        self.yt_disc_btn.clicked.connect(self._disconnect_youtube)
        self.yt_disc_btn.hide()
        yt_actions.addWidget(self.yt_disc_btn)

        yt_layout.addLayout(yt_actions)
        cards_grid.addWidget(self.yt_card, 0, 0)

        # --- Card B: Spotify Hub ---
        self.sp_card = QFrame(self)
        self.sp_card.setObjectName("spCloudCard")
        self.sp_card.setStyleSheet("""
            QFrame#spCloudCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0D1E12, stop:0.4 #13151D, stop:1 #111319);
                border-radius: 12px;
            }
        """)
        sp_layout = QVBoxLayout(self.sp_card)
        sp_layout.setContentsMargins(14, 14, 14, 14)
        sp_layout.setSpacing(12)

        sp_header_row = QHBoxLayout()
        sp_icon_lbl = QLabel(self.sp_card)
        sp_icon_lbl.setObjectName("spCloudCardIcon")
        sp_icon_lbl.setPixmap(render_svg_pixmap("spotify-icon.svg", 22, 22))
        sp_header_row.addWidget(sp_icon_lbl)

        sp_title = QLabel("SPOTIFY HUB", self.sp_card)
        sp_title.setObjectName("spCloudCardTitle")
        sp_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 900; letter-spacing: 0.5px;")
        sp_header_row.addWidget(sp_title)
        sp_header_row.addStretch()

        self.sp_badge = QLabel("UNLINKED", self.sp_card)
        self.sp_badge.setObjectName("spCloudCardBadge")
        self.sp_badge.setFixedHeight(22)
        self.sp_badge.setAlignment(Qt.AlignCenter)
        self.sp_badge.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); color: #7A7E8F; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
        sp_header_row.addWidget(self.sp_badge)

        self.sp_settings_btn = SvgHoverButton(
            SVG_SETTINGS,
            size=26,
            icon_size=14,
            idle_color="#555968",
            hover_color="#FFFFFF",
            idle_bg="#141722",
            hover_bg="#222634",
            parent=self.sp_card
        )
        self.sp_settings_btn.setObjectName("spCloudSettingsBtn")
        self.sp_settings_btn.setToolTip("Configure Spotify API Client ID")
        self.sp_settings_btn.clicked.connect(self._open_spotify_settings)
        sp_header_row.addWidget(self.sp_settings_btn)

        sp_layout.addLayout(sp_header_row)

        self.sp_status_lbl = QLabel("1-Click OAuth2 PKCE connection.", self.sp_card)
        self.sp_status_lbl.setObjectName("spCloudCardStatus")
        self.sp_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
        self.sp_status_lbl.setWordWrap(True)
        sp_layout.addWidget(self.sp_status_lbl)

        # Feature pills
        sp_features = QHBoxLayout()
        sp_features.setSpacing(6)
        for idx, feat in enumerate(["Liked Songs", "Top Seeds", "Hybrid Stream (<100ms)"]):
            f_lbl = QLabel(feat, self.sp_card)
            f_lbl.setObjectName(f"spCloudFeaturePill_{idx}")
            f_lbl.setStyleSheet("background: #0E1015; color: #9DA3B8; font-family: 'Orbitron'; font-size: 10px; font-weight: 600; border-radius: 4px; padding: 4px 8px;")
            sp_features.addWidget(f_lbl)
        sp_features.addStretch()
        sp_layout.addLayout(sp_features)

        sp_actions = QHBoxLayout()
        sp_actions.setSpacing(8)

        self.sp_connect_btn = QPushButton("Connect Spotify Account", self.sp_card)
        self.sp_connect_btn.setObjectName("spCloudConnectBtn")
        self.sp_connect_btn.setFixedHeight(32)
        self.sp_connect_btn.setCursor(Qt.PointingHandCursor)
        self.sp_connect_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1DB954, stop:1 #179E45);
                color: #FFFFFF;
                font-family: 'Orbitron';
                font-size: 10px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 18px;
                border: none;
            }
            QPushButton:hover { background: #1ED760; }
        """)
        self.sp_connect_btn.clicked.connect(self._connect_spotify)
        sp_actions.addWidget(self.sp_connect_btn, stretch=1)

        self.sp_disc_btn = QPushButton("Logout", self.sp_card)
        self.sp_disc_btn.setObjectName("spCloudLogoutBtn")
        self.sp_disc_btn.setFixedHeight(32)
        self.sp_disc_btn.setCursor(Qt.PointingHandCursor)
        self.sp_disc_btn.setStyleSheet("""
            QPushButton {
                background: #1A1D27;
                color: #A4A9BD;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 600;
                border-radius: 6px;
                padding: 4px 10px;
                border: none;
            }
            QPushButton:hover { color: #FFFFFF; background: #222634; }
        """)
        self.sp_disc_btn.clicked.connect(self._disconnect_spotify)
        sp_actions.addWidget(self.sp_disc_btn)

        sp_layout.addLayout(sp_actions)
        cards_grid.addWidget(self.sp_card, 0, 1)

        layout.addLayout(cards_grid)

        # 4. Telemetry & Cache Bar
        telemetry_card = QFrame(self)
        telemetry_card.setObjectName("cloudTelemetryBar")
        telemetry_card.setStyleSheet("""
            QFrame#cloudTelemetryBar {
                background: #12141D;
                border-radius: 10px;
            }
        """)
        t_layout = QHBoxLayout(telemetry_card)
        t_layout.setContentsMargins(14, 12, 14, 12)
        t_layout.setSpacing(12)

        db_icon = QLabel(telemetry_card)
        db_icon.setObjectName("cloudTelemetryIcon")
        db_icon.setPixmap(render_svg_pixmap(SVG_DATABASE, 20, 20))
        t_layout.addWidget(db_icon)

        t_info = QVBoxLayout()
        t_info.setSpacing(2)
        t_title = QLabel("Cloud Metadata & Audio Resolver Engine", telemetry_card)
        t_title.setObjectName("cloudTelemetryTitle")
        t_title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        t_info.addWidget(t_title)

        cache_path = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
        self.cache_lbl = QLabel(f"Storage Cache: {cache_path}", telemetry_card)
        self.cache_lbl.setObjectName("cloudTelemetryCachePath")
        self.cache_lbl.setStyleSheet("color: #707584; font-size: 10px;")
        t_info.addWidget(self.cache_lbl)

        t_layout.addLayout(t_info, stretch=1)

        clear_btn = QPushButton("Clear Cache", telemetry_card)
        clear_btn.setObjectName("cloudTelemetryClearBtn")
        clear_btn.setFixedHeight(30)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #181A24;
                color: #A0A4B4;
                font-family: 'Orbitron';
                font-size: 9px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 14px;
                border: none;
            }
            QPushButton:hover { color: #FFFFFF; background: #FF5B06; }
        """)
        clear_btn.clicked.connect(self._clear_cache)
        t_layout.addWidget(clear_btn)

        layout.addWidget(telemetry_card)
        layout.addStretch()

        self.refresh_state()

    def refresh_state(self):
        yt = YouTubeAccountEngine.get_instance()
        sp = SpotifyAccountEngine.get_instance()

        yt_active = yt.is_authenticated()
        sp_active = sp.is_authenticated()

        # Update Hero Card based on active music services
        if yt_active and sp_active:
            yt_name = yt.get_user_name()
            sp_name = sp.get_display_name()
            self.hero_user_name.setText(f"{yt_name.upper()} • {sp_name.upper()}")
            self.hero_user_desc.setText("YouTube Music & Spotify Active • Lossless Hybrid Stream Resolver Ready")
            self.hero_avatar_lbl.setPixmap(render_svg_pixmap(SVG_USER_AVATAR, 42, 42))
            self.hero_status_pill.setText("ALL SERVICES ACTIVE")
            self.hero_status_pill.setStyleSheet("background: #0E2B18; color: #00E676; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        elif yt_active:
            display_str = yt.get_account_display_str()
            self.hero_user_name.setText(f"YOUTUBE: {display_str.upper()}")
            self.hero_user_desc.setText("Active YouTube Music session synchronized via Chrome Extension")
            self.hero_avatar_lbl.setPixmap(render_svg_pixmap("lighting-adaptive.svg", 42, 42))
            self.hero_status_pill.setText("YOUTUBE SYNCED")
            self.hero_status_pill.setStyleSheet("background: #2B1212; color: #FF5252; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        elif sp_active:
            sp_name = sp.get_display_name()
            self.hero_user_name.setText(f"SPOTIFY: {sp_name.upper()}")
            self.hero_user_desc.setText("Active Spotify session synchronized via OAuth2 PKCE")
            self.hero_avatar_lbl.setPixmap(render_svg_pixmap("spotify-icon.svg", 42, 42))
            self.hero_status_pill.setText("SPOTIFY LINKED")
            self.hero_status_pill.setStyleSheet("background: #0E2B18; color: #1DB954; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        else:
            self.hero_user_name.setText("STANDALONE STREAMING MODE")
            self.hero_user_desc.setText("Sync your YouTube Music or Spotify account below to unlock playlists, liked songs, and algorithmic mixes.")
            self.hero_avatar_lbl.setPixmap(render_svg_pixmap(SVG_USER_AVATAR, 42, 42))
            self.hero_status_pill.setText("OFFLINE / UNLINKED")
            self.hero_status_pill.setStyleSheet("background: #161822; color: #8C90A0; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 14px;")

        # Update YouTube Card
        if yt_active:
            name = yt.get_user_name()
            acc_name = yt.get_account_name()
            acc_email = yt.get_account_email()
            acc_handle = yt.get_account_handle()
            display_str = yt.get_account_display_str()
            browser_raw = (yt.session_data.get("browser") or "chrome").lower()
            if "google_web" in browser_raw or "chrome" in browser_raw or "extension" in browser_raw:
                browser_str = "Google Chrome"
            elif "edge" in browser_raw:
                browser_str = "Microsoft Edge"
            elif "brave" in browser_raw:
                browser_str = "Brave Browser"
            elif "cookies_txt" in browser_raw:
                browser_str = "Cookie Import"
            else:
                browser_str = yt.session_data.get("browser", "Browser").replace("_", " ").title()

            self.yt_badge.setText("LINKED")
            self.yt_badge.setStyleSheet("background-color: rgba(0, 230, 118, 0.12); color: #00E676; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
            self.yt_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
            self.yt_status_lbl.setText(f"Connected as {display_str}. Session active and synchronized.")

            if hasattr(self, 'yt_account_box'):
                primary_name = acc_name or name
                self.yt_account_name_lbl.setText(f"SYNCED: {primary_name.upper()}")

                sub_items = []
                if acc_handle:
                    h_clean = acc_handle if acc_handle.startswith("@") else f"@{acc_handle}"
                    sub_items.append(h_clean)
                if acc_email and acc_email != primary_name and "@" in acc_email:
                    sub_items.append(acc_email)
                sub_items.append(browser_str)

                self.yt_account_sub_lbl.setText(" • ".join(sub_items))
                self.yt_account_box.show()

            self.yt_sync_btn.hide()
            self.yt_import_btn.hide()
            self.yt_disc_btn.show()
        else:
            self.yt_badge.setText("UNLINKED")
            self.yt_badge.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); color: #7A7E8F; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
            self.yt_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
            self.yt_status_lbl.setText("1-Click Auto-Sync YouTube algorithms from your active browser session.")
            if hasattr(self, 'yt_account_box'):
                self.yt_account_box.hide()
            self.yt_sync_btn.show()
            self.yt_import_btn.show()
            self.yt_disc_btn.hide()

        # Update Spotify Card
        if sp_active:
            name = sp.get_display_name()
            self.sp_badge.setText("LINKED")
            self.sp_badge.setStyleSheet("background-color: rgba(29, 185, 84, 0.15); color: #1DB954; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
            self.sp_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
            self.sp_status_lbl.setText(f"Connected as {name}. Lossless hybrid stream resolver ready.")
            self.sp_connect_btn.hide()
            self.sp_disc_btn.show()
        else:
            self.sp_badge.setText("UNLINKED")
            self.sp_badge.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); color: #7A7E8F; font-family: 'Orbitron'; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 0 8px;")
            self.sp_status_lbl.setStyleSheet("color: #D2D6E6; font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.4;")
            self.sp_status_lbl.setText("1-Click OAuth2 PKCE login. Spotify tracks are streamed in pristine quality.")
            self.sp_connect_btn.show()
            self.sp_disc_btn.hide()

        # Update Global Status
        total_linked = sum([1 for x in [yt_active, sp_active] if x])
        if total_linked == 2:
            self.global_status_pill.setText("ALL SERVICES LINKED (2/2)")
            self.global_status_pill.setStyleSheet("background: #0E2B18; color: #00E676; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 12px;")
        elif total_linked > 0:
            self.global_status_pill.setText(f"SERVICES LINKED ({total_linked}/2)")
            self.global_status_pill.setStyleSheet("background: #182032; color: #00E5FF; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 12px;")
        else:
            self.global_status_pill.setText("STANDALONE MODE (0/2)")
            self.global_status_pill.setStyleSheet("background: #161822; color: #8C90A0; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 6px; padding: 6px 12px;")

    def _load_remote_avatar(self, url: str):
        def _fetch():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    raw_data = resp.read()
                if raw_data:
                    QTimer.singleShot(0, lambda d=raw_data: self._apply_avatar_bytes(d))
            except Exception:
                pass
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

    def _apply_avatar_bytes(self, data: bytes):
        try:
            pix = QPixmap()
            if pix.loadFromData(data):
                size = 48
                scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                out = QPixmap(size, size)
                out.fill(Qt.transparent)
                p = QPainter(out)
                p.setRenderHint(QPainter.Antialiasing)
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                path = QPainterPath()
                path.addEllipse(0, 0, size, size)
                p.setClipPath(path)
                p.drawPixmap(0, 0, scaled)
                p.end()
                self.hero_avatar_lbl.setPixmap(out)
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.backClicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)



    def _show_yt_options_menu(self):
        menu = QMenu(self)
        menu.setObjectName("ytCloudOptionsMenu")
        menu.setStyleSheet("""
            QMenu#ytCloudOptionsMenu {
                background-color: #161923;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 6px;
                font-size: 11px;
                border: none;
            }
            QMenu#ytCloudOptionsMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu#ytCloudOptionsMenu::item:selected {
                background-color: #252A3C;
                color: #FF5252;
            }
            QMenu#ytCloudOptionsMenu::separator {
                height: 1px;
                background: #222636;
                margin: 4px 8px;
            }
        """)

        act_sync = menu.addAction("🔄 1-Click Auto-Sync from Browser")
        act_sync.triggered.connect(self._auto_sync_browser)

        act_ext = menu.addAction("🧩 Open HELXAID Chrome Extension Folder...")
        act_ext.triggered.connect(self._open_chrome_extension_helper)

        act_cookie = menu.addAction("🍪 Import Cookies (.txt / JSON)...")
        act_cookie.triggered.connect(self._open_youtube_cookie_dialog)

        menu.addSeparator()

        act_logout = menu.addAction("🚪 Disconnect YouTube")
        act_logout.triggered.connect(self._disconnect_youtube)

        pos = self.yt_options_btn.mapToGlobal(QPoint(0, self.yt_options_btn.height() + 4))
        menu.exec(pos)

    def _open_chrome_extension_helper(self):
        """Open the Chrome Extension folder and chrome://extensions page."""
        ext_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_extension")
        if os.path.exists(ext_dir):
            try:
                import webbrowser
                webbrowser.open("chrome://extensions/")
                os.startfile(ext_dir)
            except Exception as e:
                print(f"[DirectStreamPage] Error opening extension folder: {e}")

    def _auto_sync_browser(self):
        """1-Click Auto-Extract and Sync YouTube Session Cookies from Google Chrome in background."""
        def _sync_task():
            try:
                from utils.cookie_exporter import CookieExporter
                exporter = CookieExporter()
                try:
                    cookie_file = exporter.export_cookies('chrome', domains=['.youtube.com', '.google.com'])
                    if cookie_file and os.path.exists(cookie_file):
                        ok, msg = YouTubeAccountEngine.get_instance().import_cookies_txt(cookie_file)
                        exporter.cleanup()
                        if ok:
                            print("[DirectStreamPage] Auto-synced YouTube cookies from Chrome!")
                            QTimer.singleShot(0, self._on_auto_sync_success)
                            return
                except Exception as b_err:
                    print(f"[DirectStreamPage] Chrome direct cookie export notice: {b_err}")
            except Exception as e:
                print(f"[DirectStreamPage] Auto-sync error: {e}")
            QTimer.singleShot(0, self._open_chrome_extension_helper)

        import threading
        threading.Thread(target=_sync_task, daemon=True).start()

    def _on_auto_sync_success(self):
        self.refresh_state()
        self.accountsChanged.emit()

    def _open_web_login(self):
        self._open_youtube_cookie_dialog()

    def _open_google_settings(self):
        dialog = GoogleCredentialsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_state()
            self.accountsChanged.emit()

    def _open_youtube_cookie_dialog(self):
        dialog = YouTubeCookieImportDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_state()
            self.accountsChanged.emit()

    def _disconnect_youtube(self):
        YouTubeAccountEngine.get_instance().disconnect()
        self.refresh_state()
        self.accountsChanged.emit()

    def _connect_spotify(self):
        sp = SpotifyAccountEngine.get_instance()
        if not sp.has_valid_client_id():
            self._open_spotify_settings()
            return
        sp.start_oauth_flow()

    def _open_spotify_settings(self):
        dialog = SpotifyCredentialsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_state()
            self.accountsChanged.emit()

    def _disconnect_spotify(self):
        SpotifyAccountEngine.get_instance().disconnect()
        self.refresh_state()
        self.accountsChanged.emit()

    def _clear_cache(self):
        cache_dir = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
        if os.path.exists(cache_dir):
            import shutil
            try:
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                pass
        self.accountsChanged.emit()


class StreamProfilePillButton(QPushButton):
    """
    Top-Right Profile Pill Button displaying active account status.
    Component Name: streamProfilePillButton
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamProfilePillButton")
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont("Orbitron", 9, QFont.Bold))
        self.update_status()

    def update_status(self, is_active_panel: bool = False):
        yt_auth = YouTubeAccountEngine.get_instance().is_authenticated()
        sp_auth = SpotifyAccountEngine.get_instance().is_authenticated()

        active_border = "border: 1px solid #FF5B06; background: #242838;" if is_active_panel else ""

        if yt_auth and sp_auth:
            self.setIcon(QIcon(render_svg_pixmap(SVG_USER_AVATAR, 16, 16)))
            self.setText("  Accounts: 2 Active  ")
            self.setStyleSheet(f"""
                QPushButton#streamProfilePillButton {{
                    background: #181B24; color: #FFFFFF; border: 1px solid rgba(255, 91, 6, 0.4); border-radius: 15px; padding: 4px 12px;
                    {active_border}
                }}
                QPushButton#streamProfilePillButton:hover {{ background: #202430; border: 1px solid #FF5B06; }}
            """)
        elif yt_auth:
            self.setIcon(QIcon(render_svg_pixmap("lighting-adaptive.svg", 16, 16)))
            name = YouTubeAccountEngine.get_instance().get_user_name()
            short_name = (name[:12] + "..") if len(name) > 14 else name
            self.setText(f"  YT: {short_name}  ")
            self.setStyleSheet(f"""
                QPushButton#streamProfilePillButton {{
                    background: #181B24; color: #FFFFFF; border: 1px solid rgba(255, 0, 0, 0.4); border-radius: 15px; padding: 4px 12px;
                    {active_border}
                }}
                QPushButton#streamProfilePillButton:hover {{ background: #202430; border: 1px solid #FF0000; }}
            """)
        elif sp_auth:
            self.setIcon(QIcon(render_svg_pixmap("spotify-icon.svg", 16, 16)))
            name = SpotifyAccountEngine.get_instance().get_display_name()
            short_name = (name[:12] + "..") if len(name) > 14 else name
            self.setText(f"  Spotify: {short_name}  ")
            self.setStyleSheet(f"""
                QPushButton#streamProfilePillButton {{
                    background: #181B24; color: #FFFFFF; border: 1px solid rgba(29, 185, 84, 0.4); border-radius: 15px; padding: 4px 12px;
                    {active_border}
                }}
                QPushButton#streamProfilePillButton:hover {{ background: #202430; border: 1px solid #1DB954; }}
            """)
        else:
            self.setIcon(QIcon(render_svg_pixmap(SVG_USER_AVATAR, 16, 16)))
            self.setText("  Link Accounts  ")
            self.setStyleSheet(f"""
                QPushButton#streamProfilePillButton {{
                    background: #14161F; color: #A0A4B4; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 15px; padding: 4px 12px;
                    {active_border}
                }}
                QPushButton#streamProfilePillButton:hover {{ background: #1B1E2B; color: #FFFFFF; border: 1px solid rgba(255, 91, 6, 0.4); }}
            """)


class StreamPasteIconButton(QPushButton):
    """
    Icon-only transparent Paste button with dynamic illumination on hover.
    Component Name: streamPasteBtn
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamPasteBtn")
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Paste URL or Search Query from Clipboard")
        self.setStyleSheet("""
            QPushButton#streamPasteBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self._idle_pixmap = render_colored_svg_pixmap("paste-icon.svg", 16, 16, "#7E849B")
        self._hover_pixmap = render_colored_svg_pixmap("paste-icon.svg", 16, 16, "#FFFFFF")
        self._pressed_pixmap = render_colored_svg_pixmap("paste-icon.svg", 16, 16, "#FF5B06")
        self.setIcon(QIcon(self._idle_pixmap))
        self.setIconSize(QSize(16, 16))

    def enterEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(QIcon(self._idle_pixmap))
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setIcon(QIcon(self._pressed_pixmap))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap if self.underMouse() else self._idle_pixmap))
        super().mouseReleaseEvent(event)


class StreamOmniSearchBar(QFrame):
    """
    Sleek, minimalist Omnisearch bar for direct title and URL resolution.
    Component Name: StreamOmniSearchBar
    """
    searchTriggered = Signal(str)
    genreChipClicked = Signal(str)
    profileClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamOmniSearchBar")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        header_row.setAlignment(Qt.AlignVCenter)

        title_lbl = QLabel("DIRECT STREAM", self)
        title_lbl.setObjectName("streamHubTitle")
        title_lbl.setAlignment(Qt.AlignVCenter)
        title_lbl.setStyleSheet("""
            QLabel#streamHubTitle {
                font-family: 'Orbitron', sans-serif; font-size: 17px; font-weight: 900; color: #FFFFFF; letter-spacing: 1px;
            }
        """)
        header_row.addWidget(title_lbl, 0, Qt.AlignVCenter)

        sub_title = QLabel("Instant Cloud & Online Audio Engine", self)
        sub_title.setObjectName("streamHubSubtitle")
        sub_title.setAlignment(Qt.AlignVCenter)
        sub_title.setStyleSheet("color: #70727e; font-size: 12px; margin-left: 8px; font-weight: 500;")
        header_row.addWidget(sub_title, 0, Qt.AlignVCenter)
        header_row.addStretch()

        self.profile_btn = StreamProfilePillButton(self)
        self.profile_btn.clicked.connect(self.profileClicked.emit)
        header_row.addWidget(self.profile_btn, 0, Qt.AlignVCenter)

        layout.addLayout(header_row)

        # Search Input Box
        search_box = QFrame(self)
        search_box.setObjectName("streamSearchBox")
        search_box.setStyleSheet("""
            QFrame#streamSearchBox {
                background: #14161F; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QFrame#streamSearchBox:focus-within {
                border: 1px solid #FF5B06; background: #181A22;
            }
        """)
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 4, 12, 4)
        search_layout.setSpacing(8)
        search_layout.setAlignment(Qt.AlignVCenter)

        self.icon_lbl = QLabel(search_box)
        self.icon_lbl.setObjectName("streamSearchIcon")
        self.icon_lbl.setFixedSize(16, 16)
        pix = render_colored_svg_pixmap("search.svg", 16, 16, "#7E849B")
        if pix and not pix.isNull():
            self.icon_lbl.setPixmap(pix)
        else:
            self.icon_lbl.setPixmap(render_svg_pixmap(SVG_SEARCH, 16, 16))
        search_layout.addWidget(self.icon_lbl, 0, Qt.AlignVCenter)

        self.input_edit = QLineEdit(search_box)
        self.input_edit.setObjectName("streamSearchInput")
        self.input_edit.setPlaceholderText("Search songs, artists, playlists, or paste direct URL / video ID...")
        self.input_edit.setFixedHeight(24)
        self.input_edit.setStyleSheet("""
            QLineEdit#streamSearchInput {
                background: transparent; border: none; color: #FFFFFF; font-size: 11px;
                font-family: 'Orbitron', sans-serif; font-weight: bold; selection-background-color: #FF5B06;
                padding: 0px;
            }
        """)
        self.input_edit.returnPressed.connect(self._on_enter_pressed)
        search_layout.addWidget(self.input_edit, 1, Qt.AlignVCenter)

        self.clear_btn = QPushButton("✕", search_box)
        self.clear_btn.setObjectName("streamClearBtn")
        self.clear_btn.setFixedSize(20, 20)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet("background: transparent; color: #70727e; font-size: 12px; font-weight: bold; border: none; border-radius: 10px; padding: 0px;")
        self.clear_btn.clicked.connect(self.clear_search)
        self.clear_btn.hide()
        search_layout.addWidget(self.clear_btn, 0, Qt.AlignVCenter)

        self.paste_btn = StreamPasteIconButton(search_box)
        self.paste_btn.clicked.connect(self._on_paste_clicked)
        search_layout.addWidget(self.paste_btn, 0, Qt.AlignVCenter)

        layout.addWidget(search_box)

        # Genre Chips
        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 4, 0, 4)
        chips_row.setSpacing(6)

        chips = [
            ("Lofi 24/7", "Lofi Girl 24/7 chill beats"),
            ("Synthwave", "Synthwave 24/7 live stream"),
            ("City Pop", "Japanese City Pop live"),
            ("Cyberpunk", "Cyberpunk Industrial Dark Electro"),
            ("Phonk", "Drift Phonk Gaming Mix"),
            ("Anime OST", "Anime Opening Hits")
        ]

        font = QFont("Orbitron")
        font.setBold(True)
        font.setPixelSize(9)
        fm = QFontMetrics(font)
        for label, query in chips:
            chip_btn = AnimatedButton(label, self)
            chip_btn.setObjectName(f"streamGenreChip_{label.replace(' ', '_')}")
            chip_btn.setStyleSheet("border: none; background: transparent; padding: 0;")
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.setHoverGradient(['#3A3D45', '#4A4D55'])
            chip_btn.setHoverMode("fade")
            chip_btn.setBorderRadius(4.0)
            chip_btn.setFontSize(9)
            chip_btn.setFixedHeight(24)
            chip_width = fm.horizontalAdvance(label) + 24
            chip_btn.setFixedWidth(chip_width)
            chip_btn.clicked.connect(lambda _, q=query: self._on_chip_clicked(q))
            chips_row.addWidget(chip_btn)

        chips_row.addStretch()
        layout.addLayout(chips_row)

    def _on_enter_pressed(self):
        text = self.input_edit.text().strip()
        if text:
            self.searchTriggered.emit(text)

    def _on_paste_clicked(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.input_edit.setText(text)
            self.searchTriggered.emit(text)

    def _on_chip_clicked(self, query: str):
        self.input_edit.setText(query)
        self.searchTriggered.emit(query)

    def clear_search(self):
        self.input_edit.clear()
        self.clear_btn.hide()
        self.searchTriggered.emit("")


class CardDarkPlayOverlay(QFrame):
    """
    Dark Overlay covering the entire thumbnail image preview on card hover,
    with an enlarged centered vector play icon.
    Component Name: cardDarkPlayOverlay
    """
    def __init__(self, icon_size: int = 36, parent=None):
        super().__init__(parent)
        self.setObjectName("cardDarkPlayOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("""
            QFrame#cardDarkPlayOverlay {
                background-color: rgba(0, 0, 0, 0.58);
                border-radius: 7px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setObjectName("cardDarkPlayOverlayIcon")
        self.icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(render_colored_svg_pixmap("right-arrow-triangle.svg", icon_size, icon_size, "#FFFFFF"))
        layout.addWidget(self.icon_lbl)


class YTMusicVideoCard(QFrame):
    """16:9 Widescreen Stream Card with live thumbnail, gradient placeholder, and animated play overlay."""
    playClicked = Signal(dict)

    def __init__(self, title: str, artist: str, subtitle: str, query: str, bg_gradient_colors: List[str], parent=None):
        super().__init__(parent)
        self.setObjectName("ytMusicVideoCard")
        self._raw_pixmap: Optional[QPixmap] = None
        self._hover_progress: float = 0.0
        self.track_data = {
            'title': title,
            'artist': artist,
            'album': 'Featured Stream',
            'duration': 0,
            'original_url': query,
            'is_online': True,
            'is_stream': True
        }
        self.subtitle = subtitle
        self._bg_colors = bg_gradient_colors
        self._setup_ui()

    def _format_two_line_title(self, text: str, max_width: int = 295) -> str:
        if not text:
            return ""
        font = getattr(self, 'title_lbl', None).font() if hasattr(self, 'title_lbl') and self.title_lbl else QFont("Orbitron", 10, QFont.Bold)
        fm = QFontMetrics(font)
        words = text.split()
        if not words:
            return ""

        line1 = []
        idx = 0
        while idx < len(words):
            test = " ".join(line1 + [words[idx]])
            if fm.horizontalAdvance(test) <= max_width:
                line1.append(words[idx])
                idx += 1
            else:
                break

        if not line1 and idx < len(words):
            line1 = [fm.elidedText(words[idx], Qt.ElideRight, max_width)]
            idx += 1

        remaining = " ".join(words[idx:])
        if remaining:
            line2_elided = fm.elidedText(remaining, Qt.ElideRight, max_width)
            return " ".join(line1) + "\n" + line2_elided
        return " ".join(line1)

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(236)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#ytMusicVideoCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QFrame#ytMusicVideoCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.thumb_frame = QFrame(self)
        self.thumb_frame.setObjectName("ytVideoThumb")
        self.thumb_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.thumb_frame.setFixedHeight(150)
        self._apply_gradient_bg()

        self.thumb_img_lbl = QLabel(self.thumb_frame)
        self.thumb_img_lbl.setObjectName("ytVideoThumbImg")
        self.thumb_img_lbl.setGeometry(0, 0, 299, 150)
        self.thumb_img_lbl.setScaledContents(False)
        self.thumb_img_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_img_lbl.hide()

        self.badge_lbl = QLabel(self.thumb_frame)
        self.badge_lbl.setObjectName("ytVideoBadge")
        self.badge_lbl.hide()

        self.play_overlay = CardDarkPlayOverlay(icon_size=38, parent=self.thumb_frame)
        self.play_opacity = QGraphicsOpacityEffect(self.play_overlay)
        self.play_overlay.setGraphicsEffect(self.play_opacity)
        self.play_opacity.setOpacity(0.0)

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_step)

        layout.addWidget(self.thumb_frame)

        init_title = self._format_two_line_title(self.track_data['title'], 295)
        self.title_lbl = QLabel(init_title, self)
        self.title_lbl.setObjectName("ytVideoTitle")
        self.title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold; line-height: 1.25; background: transparent;")
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setFixedHeight(30)
        self.title_lbl.setToolTip(self.track_data['title'])
        layout.addWidget(self.title_lbl)

        sub_text = f"{self.track_data['artist']} • {self.subtitle}" if self.subtitle and self.subtitle.strip().lower() != self.track_data['artist'].strip().lower() else self.track_data['artist']
        self.sub_lbl = QLabel(sub_text, self)
        self.sub_lbl.setObjectName("ytVideoSubtitle")
        self.sub_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.sub_lbl.setStyleSheet("color: #888892; font-family: 'Orbitron', sans-serif; font-size: 9px; background: transparent;")
        self.sub_lbl.setFixedHeight(18)
        layout.addWidget(self.sub_lbl)
        layout.addStretch()

    def _on_hover_step(self, val: float):
        try:
            self._hover_progress = val
            self.play_opacity.setOpacity(val)
            w = max(40, self.thumb_frame.width() if self.thumb_frame.width() > 40 else 299)
            h = max(24, self.thumb_frame.height() if self.thumb_frame.height() > 24 else 150)
            self.play_overlay.setGeometry(0, 0, w, h)
            self._apply_gradient_bg()
        except Exception:
            pass

    def set_data(self, data: Dict[str, Any]):
        raw_title = data.get('title', self.track_data['title'])
        artist = data.get('artist', self.track_data['artist'])
        self.track_data.update({
            'title': raw_title,
            'artist': artist,
            'original_url': data.get('original_url', self.track_data['original_url']),
            'duration': data.get('duration', 0),
            'is_online': True,
            'is_stream': True
        })
        formatted_title = self._format_two_line_title(raw_title, max_width=295)
        self.title_lbl.setText(formatted_title)
        self.title_lbl.setToolTip(raw_title)
        self.setToolTip(f"{raw_title}\n{artist}")

        subtitle = data.get('subtitle', '')
        if not subtitle or subtitle.strip().lower() == artist.strip().lower():
            sub_text = artist
        else:
            sub_text = f"{artist} • {subtitle}"

        fm_sub = QFontMetrics(self.sub_lbl.font())
        elided_sub = fm_sub.elidedText(sub_text, Qt.ElideRight, 295)
        self.sub_lbl.setText(elided_sub)
        self.sub_lbl.setToolTip(sub_text)

        self.badge_lbl.hide()
        if 'bg_colors' in data and data['bg_colors']:
            self._bg_colors = data['bg_colors']
            self._apply_gradient_bg()

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        if not pixmap or pixmap.isNull():
            return
        if pixmap.width() > 360:
            pixmap = pixmap.scaledToWidth(360, Qt.SmoothTransformation)
        self._raw_pixmap = pixmap
        self._render_thumbnail()

    def _render_thumbnail(self):
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            return

        w = max(40, self.thumb_frame.width() if self.thumb_frame.width() > 40 else 299)
        h = max(24, self.thumb_frame.height() if self.thumb_frame.height() > 24 else 150)
        scaled = self._raw_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        crop_x = max(0, (scaled.width() - w) // 2)
        crop_y = max(0, (scaled.height() - h) // 2)
        cropped = scaled.copy(crop_x, crop_y, w, h)

        rounded = QPixmap(w, h)
        rounded.fill(Qt.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 7, 7)
        p.setClipPath(path)
        p.drawPixmap(0, 0, cropped)
        p.end()

        self.thumb_img_lbl.setGeometry(0, 0, w, h)
        self.thumb_img_lbl.setPixmap(rounded)
        self.thumb_img_lbl.show()
        self.badge_lbl.raise_()
        self.play_overlay.raise_()

    def _apply_gradient_bg(self):
        c0 = self._bg_colors[0] if len(self._bg_colors) > 0 else "#1e1f29"
        c1 = self._bg_colors[1] if len(self._bg_colors) > 1 else "#2a2b38"
        self.thumb_frame.setStyleSheet(f"""
            QFrame#ytVideoThumb {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c0}, stop:1 {c1});
                border-radius: 7px;
            }}
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        card_w = self.width()
        if card_w > 40:
            thumb_w = card_w - 20
            thumb_h = max(24, int(thumb_w * 9 / 16))
            if self.thumb_frame.height() != thumb_h:
                self.thumb_frame.setFixedHeight(thumb_h)
            tot_h = thumb_h + 74
            if self.height() != tot_h:
                self.setFixedHeight(tot_h)
            self.thumb_img_lbl.setGeometry(0, 0, thumb_w, thumb_h)
            self.play_overlay.setGeometry(0, 0, thumb_w, thumb_h)
            if self._raw_pixmap and not self._raw_pixmap.isNull():
                self._render_thumbnail()

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.playClicked.emit(self.track_data)
        super().mousePressEvent(event)


class YTQuickPickThumbWidget(QWidget):
    """42x42px interactive thumbnail widget with animated dark overlay & centered play button on hover."""
    playClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ytQuickPickThumb")
        self.setFixedSize(42, 42)
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap: Optional[QPixmap] = None
        self._hover_progress: float = 0.0

        self._svg_pix: Optional[QPixmap] = None
        svg_path = os.path.join(os.path.dirname(__file__), "UI Icons", "right-arrow-triangle.svg")
        if os.path.exists(svg_path):
            renderer = QSvgRenderer(svg_path)
            pix = QPixmap(14, 14)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p)
            p.end()
            self._svg_pix = pix

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.valueChanged.connect(self._on_anim_step)

    def _on_anim_step(self, val: float):
        self._hover_progress = val
        self.update()

    def set_hovered(self, hovered: bool):
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(1.0 if hovered else 0.0)
        self._anim.start()

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        try:
            if pixmap and not pixmap.isNull():
                w = self.width() if self.width() > 10 else 42
                h = self.height() if self.height() > 10 else 42
                target_dim = max(w, h) * 2
                scaled = pixmap.scaled(target_dim, target_dim, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                crop_x = max(0, (scaled.width() - target_dim) // 2)
                crop_y = max(0, (scaled.height() - target_dim) // 2)
                self._pixmap = scaled.copy(crop_x, crop_y, target_dim, target_dim)
            else:
                self._pixmap = None
            self.update()
        except (RuntimeError, AttributeError):
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.playClicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 6, 6)
        p.setClipPath(path)

        # 1. Base Cover Art or Placeholder
        if self._pixmap and not self._pixmap.isNull():
            p.drawPixmap(0, 0, w, h, self._pixmap)
        else:
            p.fillRect(0, 0, w, h, QColor("#1c1d24"))

        # 2. Dark Overlay on hover (matching ytVideoThumbImg overlay)
        if self._hover_progress > 0.01:
            overlay_alpha = int(150 * self._hover_progress)
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, overlay_alpha))

            # 3. Play Icon (Vector right-arrow-triangle, centered directly on dark overlay)
            if self._svg_pix and not self._svg_pix.isNull():
                ix = int((w - self._svg_pix.width()) / 2.0 + 1)
                iy = int((h - self._svg_pix.height()) / 2.0)
                p.setOpacity(self._hover_progress)
                p.drawPixmap(ix, iy, self._svg_pix)

        p.end()


class YTMoreMenuButton(QPushButton):
    """Button that emits menuRequested on both left-click and right-click."""
    menuRequested = Signal(QPoint)

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            global_pos = self.mapToGlobal(QPoint(0, self.height() + 2))
            self.menuRequested.emit(global_pos)
            event.accept()
            return
        super().mousePressEvent(event)


class YTTrackCreditsDialog(QDialog):
    """Cyberpunk modal dialog displaying full song credits and streaming metadata."""
    def __init__(self, track_data: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ytTrackCreditsDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(480, 360)
        self.track_data = track_data
        self._setup_ui()

    def _setup_ui(self):
        container = QFrame(self)
        container.setObjectName("creditsContainer")
        container.setGeometry(0, 0, 480, 360)
        container.setStyleSheet("""
            QFrame#creditsContainer {
                background: rgba(25, 25, 35, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header Row
        hdr = QHBoxLayout()
        icon_lbl = QLabel(container)
        icon_lbl.setPixmap(render_svg_pixmap("menu-credits.svg", 18, 18))
        hdr.addWidget(icon_lbl)

        title = QLabel("SONG CREDITS & METADATA", container)
        title.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron'; font-size: 13px; font-weight: 900; letter-spacing: 1px;")
        hdr.addWidget(title)
        hdr.addStretch()

        close_btn = QPushButton("✕", container)
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #8C90A0; font-size: 13px; font-weight: bold; border: none; }
            QPushButton:hover { color: #FFFFFF; }
        """)
        close_btn.clicked.connect(self.accept)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        sep = QFrame(container)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255, 255, 255, 0.08);")
        layout.addWidget(sep)

        # Metadata rows
        dur_val = self.track_data.get('duration', 0)
        dur_str = f"{int(dur_val) // 60}:{int(dur_val) % 60:02d}" if dur_val > 0 else "Stream"
        orig_url = self.track_data.get('original_url') or self.track_data.get('title', 'N/A')

        fields = [
            ("Track Title", self.track_data.get('title', 'Unknown Title')),
            ("Artist / Channel", self.track_data.get('artist', 'Unknown Artist')),
            ("Album / Collection", self.track_data.get('album', 'Cloud Stream')),
            ("Duration", dur_str),
            ("Audio Engine", "HELXAIC Canonical Stream Engine"),
            ("Direct Source", "YouTube Music" if "youtube" in str(orig_url) or self.track_data.get('is_stream') else "Spotify Stream"),
            ("Canonical ID / URL", str(orig_url)),
        ]

        grid = QGridLayout()
        grid.setSpacing(8)
        for row, (k, v) in enumerate(fields):
            k_lbl = QLabel(k, container)
            k_lbl.setStyleSheet("color: #8C90A0; font-family: 'Orbitron'; font-size: 10px; font-weight: bold;")
            v_lbl = QLabel(str(v), container)
            v_lbl.setStyleSheet("color: #E0E2EC; font-size: 11px;")
            v_lbl.setWordWrap(True)
            v_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(k_lbl, row, 0)
            grid.addWidget(v_lbl, row, 1)
            grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()

        # Footer Actions
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("Copy Info", container)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.12); color: #E0E2EC; font-family: 'Orbitron'; font-size: 10px; font-weight: bold; border-radius: 6px; padding: 6px 16px; border: none;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.22); color: #FFFFFF; }
        """)
        copy_btn.clicked.connect(self._copy_info)
        btn_row.addWidget(copy_btn)

        done_btn = QPushButton("Close", container)
        done_btn.setCursor(Qt.PointingHandCursor)
        done_btn.setStyleSheet("""
            QPushButton {
                background: #181A24; color: #8C90A0; font-family: 'Orbitron'; font-size: 10px; font-weight: bold; border-radius: 6px; padding: 6px 16px; border: none;
            }
            QPushButton:hover { color: #FFFFFF; background: #202330; }
        """)
        done_btn.clicked.connect(self.accept)
        btn_row.addWidget(done_btn)

        layout.addLayout(btn_row)

    def _copy_info(self):
        txt = (
            f"Title: {self.track_data.get('title')}\n"
            f"Artist: {self.track_data.get('artist')}\n"
            f"Album: {self.track_data.get('album')}\n"
            f"URL: {self.track_data.get('original_url')}"
        )
        try:
            QApplication.clipboard().setText(txt)
        except Exception:
            pass
        self.accept()


class YTQuickPickItem(QFrame):
    """Compact Quick Pick item for 3x4 grid with 42x42px thumbnail, hover play overlay & 9-action context menu."""
    playClicked = Signal(dict)
    infoClicked = Signal(dict)
    playNextRequested = Signal(dict)
    addToQueueRequested = Signal(dict)
    downloadRequested = Signal(str, str)
    addToPlaylistRequested = Signal(dict)
    searchRequested = Signal(str)
    notInterestedRequested = Signal(dict)
    blockArtistRequested = Signal(str)

    def __init__(self, track_data: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ytQuickPickItem")
        self.track_data = track_data
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#ytQuickPickItem {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
            QFrame#ytQuickPickItem:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)

        # Interactive Thumbnail with Dark Overlay & Centered Play Button on Hover
        self.thumb_widget = YTQuickPickThumbWidget(self)
        self.thumb_widget.playClicked.connect(lambda: self.playClicked.emit(self.track_data))
        layout.addWidget(self.thumb_widget, 0, Qt.AlignVCenter)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignVCenter)

        title_lbl = QLabel(self.track_data.get('title', 'Unknown Track'), self)
        title_lbl.setObjectName("ytQuickPickTitle")
        title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_layout.addWidget(title_lbl)

        sub_lbl = QLabel(f"{self.track_data.get('artist', 'Unknown')} • {self.track_data.get('album', 'Cloud Stream')}", self)
        sub_lbl.setObjectName("ytQuickPickSub")
        sub_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        sub_lbl.setStyleSheet("color: #888892; font-family: 'Orbitron', sans-serif; font-size: 10px; background: transparent;")
        sub_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_layout.addWidget(sub_lbl)

        layout.addLayout(info_layout, stretch=1)

        # Info button on the right corner (appears on hover, responds to left/right click)
        self.info_btn = YTMoreMenuButton(self)
        self.info_btn.setObjectName("ytQuickPickInfoBtn")
        self.info_btn.setIcon(QIcon(render_svg_pixmap("more-vertical.svg", 16, 16)))
        self.info_btn.setIconSize(QSize(16, 16))
        self.info_btn.setFixedSize(26, 26)
        self.info_btn.setCursor(Qt.PointingHandCursor)
        self.info_btn.setToolTip(f"{self.track_data.get('title', '')}\nArtist: {self.track_data.get('artist', '')}\nAlbum: {self.track_data.get('album', '')}")
        self.info_btn.setStyleSheet("""
            QPushButton#ytQuickPickInfoBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#ytQuickPickInfoBtn:hover {
                background: transparent;
            }
        """)
        self.info_btn.menuRequested.connect(self._show_quick_menu)
        self.info_btn.hide()
        layout.addWidget(self.info_btn, 0, Qt.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.playClicked.emit(self.track_data)
            event.accept()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self._show_quick_menu(event.globalPos())
        event.accept()

    def _show_quick_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.setObjectName("ytQuickPickContextMenu")
        menu.setStyleSheet("""
            QMenu#ytQuickPickContextMenu {
                background: rgba(25, 25, 35, 0.98);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
            }
            QMenu#ytQuickPickContextMenu::item {
                padding: 8px 20px 8px 10px;
                border-radius: 4px;
                color: #e0e0e0;
                background: transparent;
            }
            QMenu#ytQuickPickContextMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QMenu#ytQuickPickContextMenu::icon {
                padding-left: 6px;
                padding-right: 4px;
            }
            QMenu#ytQuickPickContextMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)

        # 1. Play next
        act_next = menu.addAction(QIcon(render_svg_pixmap("menu-play-next.svg", 16, 16)), "Play next")
        act_next.triggered.connect(lambda: self.playNextRequested.emit(self.track_data))

        # 2. Add to queue
        act_queue = menu.addAction(QIcon(render_svg_pixmap("menu-add-queue.svg", 16, 16)), "Add to queue")
        act_queue.triggered.connect(lambda: self.addToQueueRequested.emit(self.track_data))

        menu.addSeparator()

        # 3. Download
        act_dl = menu.addAction(QIcon(render_svg_pixmap("menu-download.svg", 16, 16)), "Download")
        act_dl.triggered.connect(self._on_download_action)

        # 4. Save to playlist
        act_pl = menu.addAction(QIcon(render_svg_pixmap("playlist-icon.svg", 16, 16)), "Save to playlist")
        act_pl.triggered.connect(lambda: self.addToPlaylistRequested.emit(self.track_data))

        menu.addSeparator()

        # 5. Open album
        album_name = self.track_data.get('album', '')
        if album_name and album_name != 'Cloud Stream':
            act_alb = menu.addAction(QIcon(render_svg_pixmap("menu-album.svg", 16, 16)), "Open album")
            act_alb.triggered.connect(lambda: self.searchRequested.emit(f"album:{album_name}"))

        # 6. Open artist page
        artist_name = self.track_data.get('artist', '')
        if artist_name and artist_name != 'Unknown':
            act_art = menu.addAction(QIcon(render_svg_pixmap("menu-artist.svg", 16, 16)), "Open artist page")
            act_art.triggered.connect(lambda: self.searchRequested.emit(artist_name))

        # 7. View song credits
        act_credits = menu.addAction(QIcon(render_svg_pixmap("menu-credits.svg", 16, 16)), "View song credits")
        act_credits.triggered.connect(self._show_credits_dialog)

        # 8. Share
        act_share = menu.addAction(QIcon(render_svg_pixmap("menu-share.svg", 16, 16)), "Share")
        act_share.triggered.connect(self._on_share_action)

        menu.addSeparator()

        # 9. Not interested
        act_dismiss = menu.addAction(QIcon(render_svg_pixmap("menu-ban.svg", 16, 16)), "Not interested")
        act_dismiss.triggered.connect(lambda: self.notInterestedRequested.emit(self.track_data))

        # 10. Don't recommend artist
        if artist_name and artist_name != 'Unknown':
            act_blk = menu.addAction(QIcon(render_svg_pixmap("menu-ban.svg", 16, 16)), f"Don't recommend {artist_name}")
            act_blk.triggered.connect(lambda: self.blockArtistRequested.emit(artist_name))

        menu.exec(global_pos)

    def _show_credits_dialog(self):
        dlg = YTTrackCreditsDialog(self.track_data, self)
        dlg.exec()

    def _on_share_action(self):
        url = self.track_data.get('original_url') or self.track_data.get('title', '')
        if url:
            try:
                QApplication.clipboard().setText(str(url))
            except Exception:
                pass

    def _on_download_action(self):
        url = self.track_data.get('original_url') or ''
        title = self.track_data.get('title') or 'track'
        self.downloadRequested.emit(url, title)

    def enterEvent(self, event):
        self.thumb_widget.set_hovered(True)
        self.info_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.thumb_widget.set_hovered(False)
        self.info_btn.hide()
        super().leaveEvent(event)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        try:
            if not pixmap or pixmap.isNull():
                return
            if hasattr(self, 'thumb_widget') and self.thumb_widget:
                self.thumb_widget.set_pixmap(pixmap)
        except (RuntimeError, AttributeError):
            pass


class CloudMediaCard(QFrame):
    """Versatile Cyberpunk Card for Playlists, Mixes, and Cloud Tracks with unified 1:1 square geometry."""
    playClicked = Signal(dict)
    saveClicked = Signal(dict)

    def __init__(self, item_data: dict, accent_color: str = "#FF5B06", parent=None):
        super().__init__(parent)
        self.setObjectName("cloudMediaCard")
        self.item_data = item_data
        self.accent_color = accent_color
        self._raw_pixmap: Optional[QPixmap] = None
        self._hover_progress: float = 0.0
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(260)
        self.setFixedHeight(236)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#cloudMediaCard {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QFrame#cloudMediaCard:hover {
                background-color: rgba(255, 91, 6, 0.08);
                border-color: rgba(255, 91, 6, 0.5);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.thumb_frame = QFrame(self)
        self.thumb_frame.setObjectName("cloudMediaCardThumbFrame")
        self.thumb_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.thumb_frame.setFixedHeight(150)
        self.thumb_frame.setStyleSheet("""
            QFrame#cloudMediaCardThumbFrame {
                background: #0E1015;
                border-radius: 7px;
            }
        """)
        t_layout = QVBoxLayout(self.thumb_frame)
        t_layout.setContentsMargins(6, 6, 6, 6)

        self.thumb_img = QLabel(self.thumb_frame)
        self.thumb_img.setObjectName("cloudMediaCardThumbImg")
        self.thumb_img.setStyleSheet("background: transparent; border-radius: 7px;")
        self.thumb_img.setAlignment(Qt.AlignCenter)
        self.thumb_img.setGeometry(0, 0, 299, 150)
        self.thumb_img.hide()

        self.badge_lbl = QLabel(self.thumb_frame)
        self.badge_lbl.setObjectName("cloudMediaCardBadge")
        self.badge_lbl.hide()
        t_layout.addStretch()

        # Hover Play Overlay (Full Thumbnail Dark Cover)
        self.play_overlay = CardDarkPlayOverlay(icon_size=38, parent=self.thumb_frame)
        self.play_opacity = QGraphicsOpacityEffect(self.play_overlay)
        self.play_opacity.setOpacity(0.0)
        self.play_overlay.setGraphicsEffect(self.play_opacity)

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_step)

        layout.addWidget(self.thumb_frame)

        title_lbl = QLabel(self.item_data.get("title", "Unknown Title"), self)
        title_lbl.setObjectName("cloudMediaCardTitle")
        title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold; line-height: 1.2; background: transparent;")
        title_lbl.setWordWrap(True)
        title_lbl.setFixedHeight(30)
        layout.addWidget(title_lbl)

        sub_text = self.item_data.get("artist") or self.item_data.get("description") or f"{self.item_data.get('track_count', 0)} Tracks"
        sub_lbl = QLabel(str(sub_text), self)
        sub_lbl.setObjectName("cloudMediaCardSub")
        sub_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        sub_lbl.setStyleSheet("color: #888892; font-family: 'Orbitron', sans-serif; font-size: 9px; background: transparent;")
        sub_lbl.setFixedHeight(18)
        layout.addWidget(sub_lbl)
        layout.addStretch()

    def _on_hover_step(self, val: float):
        try:
            self._hover_progress = val
            self.play_opacity.setOpacity(val)
            w = max(40, self.thumb_frame.width() if self.thumb_frame.width() > 40 else 299)
            h = max(40, self.thumb_frame.height() if self.thumb_frame.height() > 40 else 150)
            self.play_overlay.setGeometry(0, 0, w, h)
        except (RuntimeError, Exception):
            pass

    def _render_thumbnail(self):
        try:
            if not self._raw_pixmap or self._raw_pixmap.isNull():
                return
            w = max(40, self.thumb_frame.width() if self.thumb_frame.width() > 40 else 299)
            h = max(40, self.thumb_frame.height() if self.thumb_frame.height() > 40 else 150)
            scaled = self._raw_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            crop_x = max(0, (scaled.width() - w) // 2)
            crop_y = max(0, (scaled.height() - h) // 2)
            cropped = scaled.copy(crop_x, crop_y, w, h)

            rounded = QPixmap(w, h)
            rounded.fill(Qt.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            path = QPainterPath()
            path.addRoundedRect(0, 0, w, h, 7, 7)
            p.setClipPath(path)
            p.drawPixmap(0, 0, cropped)
            p.end()

            self.thumb_img.setGeometry(0, 0, w, h)
            self.thumb_img.setPixmap(rounded)
            self.thumb_img.show()
            self.badge_lbl.raise_()
            self.play_overlay.raise_()
        except (RuntimeError, Exception):
            pass

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        try:
            if not pixmap or pixmap.isNull():
                return
            if pixmap.width() > 360:
                pixmap = pixmap.scaledToWidth(360, Qt.SmoothTransformation)
            self._raw_pixmap = pixmap
            self._render_thumbnail()
        except (RuntimeError, Exception):
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
            w = self.thumb_frame.width()
            h = self.thumb_frame.height()
            if w > 20 and h > 20:
                self.thumb_img.setGeometry(0, 0, w, h)
                self.play_overlay.setGeometry(0, 0, w, h)
                if self._raw_pixmap and not self._raw_pixmap.isNull():
                    self._render_thumbnail()
        except (RuntimeError, Exception):
            pass

    def enterEvent(self, event):
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_progress)
            self._hover_anim.setEndValue(1.0)
            self._hover_anim.start()
            super().enterEvent(event)
        except (RuntimeError, Exception):
            pass

    def leaveEvent(self, event):
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_progress)
            self._hover_anim.setEndValue(0.0)
            self._hover_anim.start()
            super().leaveEvent(event)
        except (RuntimeError, Exception):
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.playClicked.emit(self.item_data)
        super().mousePressEvent(event)


class StreamTrackRowWidget(QFrame):
    """
    Component Name: streamTrackRowWidget
    Sleek, hover-interactive tracklist row for playlist/mix detail view.
    """
    trackClicked = Signal(dict)
    trackDoubleClicked = Signal(dict)

    def __init__(self, index: int, track_data: dict, accent_color: str = "#FF0000", parent=None):
        super().__init__(parent)
        self.setObjectName("streamTrackRowWidget")
        self.index = index
        self.track_data = track_data
        self.accent_color = accent_color
        self._is_hovered = False
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#streamTrackRowWidget {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 0px;
            }
            QFrame#streamTrackRowWidget:hover {
                background: rgba(255, 255, 255, 0.06);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(14)

        # 1. Track Number / Play Icon
        self.num_lbl = QLabel(str(self.index), self)
        self.num_lbl.setObjectName("trackRowNumLbl")
        self.num_lbl.setFixedWidth(26)
        self.num_lbl.setAlignment(Qt.AlignCenter)
        self.num_lbl.setStyleSheet("color: #7E849B; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.num_lbl)

        # Pre-render Cyberpunk SVG Play Icon
        self._play_pixmap = QPixmap(14, 14)
        self._play_pixmap.fill(Qt.transparent)
        svg_path = os.path.join(os.path.dirname(__file__), "UI Icons", "right-arrow-triangle.svg")
        if os.path.exists(svg_path):
            renderer = QSvgRenderer(svg_path)
            painter = QPainter(self._play_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(self._play_pixmap.rect(), QColor(self.accent_color))
            painter.end()
        else:
            painter = QPainter(self._play_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(self.accent_color))
            painter.setPen(Qt.NoPen)
            poly = QPolygonF([QPointF(2, 2), QPointF(12, 7), QPointF(2, 12)])
            painter.drawPolygon(poly)
            painter.end()

        # 2. Track Title & Artist
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.title_lbl = QLabel(self.track_data.get("title", "Unknown Track"), self)
        self.title_lbl.setObjectName("trackRowTitleLbl")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        self.title_lbl.setTextInteractionFlags(Qt.NoTextInteraction)

        sub_info = self.track_data.get("artist") or self.track_data.get("album") or "YouTube Music"
        self.artist_lbl = QLabel(str(sub_info), self)
        self.artist_lbl.setObjectName("trackRowArtistLbl")
        self.artist_lbl.setStyleSheet("color: #7E849B; font-size: 10px;")
        self.artist_lbl.setTextInteractionFlags(Qt.NoTextInteraction)

        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.artist_lbl)
        layout.addLayout(text_col, stretch=1)

        # 3. Duration
        dur_sec = self.track_data.get("duration", 0)
        dur_str = "--:--"
        if dur_sec:
            m, s = divmod(int(dur_sec), 60)
            dur_str = f"{m}:{s:02d}"

        self.dur_lbl = QLabel(dur_str, self)
        self.dur_lbl.setObjectName("trackRowDurLbl")
        self.dur_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.dur_lbl.setFixedWidth(60)
        self.dur_lbl.setStyleSheet("color: #7E849B; font-family: 'Orbitron', sans-serif; font-size: 10px;")
        layout.addWidget(self.dur_lbl)

    def enterEvent(self, event):
        self._is_hovered = True
        self.num_lbl.clear()
        self.num_lbl.setPixmap(self._play_pixmap)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.num_lbl.clear()
        self.num_lbl.setText(str(self.index))
        self.num_lbl.setStyleSheet("color: #7E849B; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            payload = dict(self.track_data)
            payload["is_single_track"] = True
            payload["is_playlist"] = False
            self.trackClicked.emit(payload)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            payload = dict(self.track_data)
            payload["is_single_track"] = True
            payload["is_playlist"] = False
            self.trackDoubleClicked.emit(payload)
        super().mouseDoubleClickEvent(event)


class FetchPlaylistDetailWorker(QThread):
    """Async QThread worker to safely fetch and marshal playlist/mix tracks to GUI main thread with progressive streaming."""
    tracksReady = Signal(list)
    moreTracksReady = Signal(list)

    def __init__(self, browse_id: str, playlist_data: dict, parent=None):
        super().__init__(parent)
        self.browse_id = browse_id
        self.playlist_data = playlist_data
        self._is_cancelled = False
        self._initial_emitted = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        tracks = []
        is_radio = self.playlist_data.get("is_algorithmic", False) or self.browse_id == "RDMM" or self.browse_id.startswith("RD") or self.browse_id.startswith("RDTMAK5uy_")
        seed_vid = self.playlist_data.get("seed_video_id") or None

        def _on_first_batch(initial_tracks):
            if not self._is_cancelled and initial_tracks and not self._initial_emitted:
                self._initial_emitted = True
                self.tracksReady.emit(list(initial_tracks))

        def _on_more_batch(more_tracks):
            if not self._is_cancelled and more_tracks:
                self.moreTracksReady.emit(list(more_tracks))

        try:
            yt_engine = YouTubeAccountEngine.get_instance()
            tracks = yt_engine.fetch_playlist_tracks(
                self.browse_id,
                is_radio=is_radio,
                video_id=seed_vid,
                on_first_batch=_on_first_batch,
                on_more_batch=_on_more_batch
            )
        except Exception as e:
            print(f"[FetchPlaylistDetailWorker] Notice: {e}")

        if self._is_cancelled:
            return

        # Smart On-Device Fallback via TasteProfileEngine tailored to Tristan's actual listening history
        if not tracks and not self._initial_emitted:
            try:
                badge = self.playlist_data.get("badge", "MIX")
                title = self.playlist_data.get("title", "")
                cat = badge if badge and badge != "MIX" else title
                tracks = TasteProfileEngine.generate_dynamic_mix(cat, count=30)
            except Exception as e:
                print(f"[FetchPlaylistDetailWorker] TasteProfileEngine fallback error: {e}")

        if not self._is_cancelled and not self._initial_emitted and tracks:
            self._initial_emitted = True
            self.tracksReady.emit(tracks)


class DetailOptIconButton(QPushButton):
    """
    Icon-only transparent options button with dynamic illumination on hover.
    Component Name: detailOptBtn
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailOptBtn")
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Playlist & Mix Options")
        self.setStyleSheet("""
            QPushButton#detailOptBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#detailOptBtn:hover {
                background: transparent;
                border: none;
            }
        """)
        self._idle_pixmap = render_colored_svg_pixmap("more-horizontal.svg", 18, 18, "#7E849B")
        self._hover_pixmap = render_colored_svg_pixmap("more-horizontal.svg", 18, 18, "#FFFFFF")
        self._pressed_pixmap = render_colored_svg_pixmap("more-horizontal.svg", 18, 18, "#FF5B06")
        self.setIcon(QIcon(self._idle_pixmap))
        self.setIconSize(QSize(18, 18))

    def enterEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(QIcon(self._idle_pixmap))
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setIcon(QIcon(self._pressed_pixmap))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap if self.underMouse() else self._idle_pixmap))
        super().mouseReleaseEvent(event)


class DetailSaveIconButton(QPushButton):
    """
    Icon-only transparent save button with dynamic illumination on hover.
    Component Name: detailSaveBtn
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailSaveBtn")
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Save as Stream Collection")
        self.setStyleSheet("""
            QPushButton#detailSaveBtn {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#detailSaveBtn:hover {
                background: transparent;
                border: none;
            }
        """)
        self._idle_pixmap = render_colored_svg_pixmap("save-floppy.svg", 18, 18, "#7E849B")
        self._hover_pixmap = render_colored_svg_pixmap("save-floppy.svg", 18, 18, "#FFFFFF")
        self._pressed_pixmap = render_colored_svg_pixmap("save-floppy.svg", 18, 18, "#FF5B06")
        self.setIcon(QIcon(self._idle_pixmap))
        self.setIconSize(QSize(18, 18))

    def enterEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(QIcon(self._idle_pixmap))
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setIcon(QIcon(self._pressed_pixmap))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIcon(QIcon(self._hover_pixmap if self.underMouse() else self._idle_pixmap))
        super().mouseReleaseEvent(event)


class SaveStreamFloatingPanel(QFrame):
    """
    In-App Cyberpunk Floating Modal/Panel (QFrame) for saving Stream Collections (.hxstream).
    Features a draggable custom title bar matching ComponentInspectorFloatingPanel, destination
    folder selector, file preview, browse button, and user preference checkbox.
    Component Name: saveStreamFloatingPanel
    """
    saveConfirmed = Signal(dict, str)  # track_data, destination_folder

    def __init__(self, track_data: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("saveStreamFloatingPanel")
        self.track_data = track_data
        self.settings = QSettings("TDD131", "HELXAID")

        # Window & Geometry Settings
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(520, 345)

        # Dragging state
        self._is_dragging = False
        self._has_been_dragged = False
        self._drag_start_pos = QPoint()

        # Retrieve persisted default save folder
        default_dir = os.path.join(os.path.expanduser("~/Music"), "Streams")
        self.current_folder = self.settings.value("MusicSettings/stream_save_folder", default_dir, type=str)
        if not self.current_folder:
            self.current_folder = default_dir

        # Entrance & Exit Fade Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame#saveStreamFloatingPanel {
                background-color: rgba(12, 12, 16, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QWidget#saveStreamTitleBar {
                background-color: rgba(6, 6, 8, 0.85);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#saveStreamTitleLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                background: transparent;
                letter-spacing: 1px;
            }
        """)

        # Drop shadow for floating effect
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Custom In-App Titlebar (Draggable Header)
        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("saveStreamTitleBar")
        self.title_bar.setFixedHeight(42)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(10)

        icon_lbl = QLabel(self.title_bar)
        icon_lbl.setObjectName("saveStreamTitleIcon")
        icon_lbl.setPixmap(render_colored_svg_pixmap("save-floppy.svg", 18, 18, "#FF5B06"))
        tb_layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)

        title_lbl = QLabel("SAVE STREAM COLLECTION", self.title_bar)
        title_lbl.setObjectName("saveStreamTitleLabel")
        tb_layout.addWidget(title_lbl, stretch=1, alignment=Qt.AlignVCenter)

        main_layout.addWidget(self.title_bar)

        # 2. Body Container
        body_widget = QWidget(self)
        body_widget.setObjectName("saveStreamBodyWidget")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(14)

        # Stream Info Card
        title = self.track_data.get("title", "Unknown Stream")
        clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip() + ".hxstream"

        info_frame = QFrame(body_widget)
        info_frame.setObjectName("saveStreamInfoCard")
        info_frame.setStyleSheet("background-color: #0E1015; border-radius: 8px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(6)

        stream_lbl = QLabel(f"Collection: {title}", info_frame)
        stream_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 800; letter-spacing: 0.3px;")
        info_layout.addWidget(stream_lbl)

        file_preview_lbl = QLabel(f"File: {clean_name}", info_frame)
        file_preview_lbl.setStyleSheet("color: #A0A4B4; font-family: 'Orbitron', monospace; font-size: 11px; font-weight: 500;")
        info_layout.addWidget(file_preview_lbl)

        body_layout.addWidget(info_frame)

        # Destination Path Selector
        path_box = QVBoxLayout()
        path_box.setSpacing(6)

        path_lbl = QLabel("SAVE DESTINATION FOLDER", body_widget)
        path_lbl.setStyleSheet("color: #9EA4B8; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        path_box.addWidget(path_lbl)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.path_input = QLineEdit(self.current_folder, body_widget)
        self.path_input.setObjectName("saveStreamPathInput")
        self.path_input.setReadOnly(True)
        self.path_input.setFixedHeight(36)
        self.path_input.setStyleSheet("""
            QLineEdit#saveStreamPathInput {
                background-color: #0E1015;
                color: #FFFFFF;
                font-family: 'Orbitron', monospace;
                font-size: 11px;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        path_row.addWidget(self.path_input, stretch=1)

        browse_btn = FadeHoverButton("Browse...", is_secondary=True, border_radius=6.0, font_size=11, parent=body_widget)
        browse_btn.setObjectName("saveStreamBrowseBtn")
        browse_btn.setFixedHeight(36)
        browse_btn.setFixedWidth(95)
        browse_btn.clicked.connect(self._on_browse_folder)
        path_row.addWidget(browse_btn)

        path_box.addLayout(path_row)
        body_layout.addLayout(path_box)

        # Checkbox to Save User Preference
        self.remember_cb = AnimatedCheckBox("Save My Preference", body_widget)
        self.remember_cb.setObjectName("saveStreamRememberCheckbox")
        cb_font = QFont("Orbitron", 9)
        cb_font.setBold(True)
        cb_font.setPixelSize(11)
        self.remember_cb.setFont(cb_font)
        self.remember_cb.setStyleSheet("color: #E0E0E0; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 600;")
        self.remember_cb.setFixedHeight(26)
        is_remembered = self.settings.value("MusicSettings/stream_save_remember", True, type=bool)
        self.remember_cb.setChecked(is_remembered)
        body_layout.addWidget(self.remember_cb)

        # Bottom Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 0)
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = FadeHoverButton("Cancel", is_secondary=True, border_radius=6.0, font_size=11, parent=body_widget)
        cancel_btn.setObjectName("saveStreamCancelBtn")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setFixedWidth(95)
        cancel_btn.clicked.connect(self.close_panel)
        btn_row.addWidget(cancel_btn)

        confirm_btn = FadeHoverButton("Save Stream", is_secondary=False, border_radius=6.0, font_size=12, parent=body_widget)
        confirm_btn.setObjectName("saveStreamConfirmBtn")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setFixedWidth(145)
        confirm_btn.clicked.connect(self._on_confirm_save)
        btn_row.addWidget(confirm_btn)

        body_layout.addLayout(btn_row)
        main_layout.addWidget(body_widget, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if hasattr(self, 'title_bar') and self.title_bar.geometry().contains(event.pos()):
                self._is_dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_is_dragging', False) and event.buttons() & Qt.LeftButton:
            self._has_been_dragged = True
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                new_pos = QPoint(new_x, new_y)
            self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close_panel()
            event.accept()
            return
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_confirm_save()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Stream Save Folder",
            self.current_folder,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.current_folder = folder
            self.path_input.setText(folder)

    def _on_confirm_save(self):
        folder = self.current_folder or os.path.join(os.path.expanduser("~/Music"), "Streams")
        os.makedirs(folder, exist_ok=True)
        remember = self.remember_cb.isChecked()
        self.settings.setValue("MusicSettings/stream_save_folder", folder)
        self.settings.setValue("MusicSettings/stream_save_always", remember)
        self.saveConfirmed.emit(self.track_data, folder)
        self.close_panel()

    def show_centered(self):
        if not getattr(self, '_has_been_dragged', False) and self.parentWidget():
            pw = self.parentWidget().width()
            ph = self.parentWidget().height()
            self.move(max(10, (pw - self.width()) // 2), max(10, (ph - self.height()) // 2))
        self.show()
        self.raise_()
        if hasattr(self, 'anim'):
            self.anim.stop()
            self.anim.setDirection(QPropertyAnimation.Forward)
            self.anim.start()

    def close_panel(self):
        if hasattr(self, 'anim'):
            self.anim.stop()
            self.anim.setDirection(QPropertyAnimation.Backward)
            self.anim.start()
        else:
            self.hide()
            self.deleteLater()

    def _on_anim_finished(self):
        if hasattr(self, 'anim') and self.anim.direction() == QPropertyAnimation.Backward:
            self.hide()
            self.deleteLater()


class StreamPlaylistDetailView(QWidget):
    """
    Component Name: streamPlaylistDetailView
    Dedicated Full-Page Mix & Playlist Detail Panel (Image 1 Style).
    Two-column architecture:
    - Left Column: Large Cover Art, Title, Subtitle, Bookmark/Play/Options Buttons
    - Right Column: Scrollable interactive tracklist with index numbers and durations
    """
    backClicked = Signal()
    playTrackRequested = Signal(dict)
    playAllRequested = Signal(dict)
    savePlaylistRequested = Signal(dict)
    addToQueueRequested = Signal(dict)
    downloadPlaylistRequested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamPlaylistDetailView")
        self.setStyleSheet("QWidget#streamPlaylistDetailView { background: transparent; }")
        self._playlist_data: Dict[str, Any] = {}
        self._tracks: List[Dict[str, Any]] = []
        self._image_loader: Optional[AsyncImageLoader] = None
        self._fetch_worker: Optional[FetchPlaylistDetailWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 14, 0)
        main_layout.setSpacing(14)

        # 1. Top Navigation Bar
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(10)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        back_icon_path = os.path.join(script_dir, "UI Icons", "back-arrow-white.svg").replace('\\', '/')

        self.back_btn = QPushButton(self)
        self.back_btn.setObjectName("detailBackBtn")
        self.back_btn.setFixedSize(30, 26)
        if os.path.exists(back_icon_path):
            self.back_btn.setIcon(QIcon(back_icon_path))
            self.back_btn.setIconSize(QSize(15, 15))
        else:
            self.back_btn.setIcon(QIcon(render_svg_pixmap(SVG_BACK_ARROW, 15, 15)))
            self.back_btn.setIconSize(QSize(15, 15))
        self.back_btn.setToolTip("Back to Direct Stream")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton#detailBackBtn {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 6px;
                padding: 0px;
                min-width: 30px;
                max-width: 30px;
                min-height: 26px;
                max-height: 26px;
            }
            QPushButton#detailBackBtn:hover {
                background-color: #FF5B06;
            }
        """)
        self.back_btn.clicked.connect(self.backClicked.emit)
        nav_row.addWidget(self.back_btn)

        self.breadcrumb_lbl = QLabel("DISCOVER & PLAYLISTS", self)
        self.breadcrumb_lbl.setObjectName("detailBreadcrumbLbl")
        self.breadcrumb_lbl.setStyleSheet("color: #7E849B; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        nav_row.addWidget(self.breadcrumb_lbl)
        nav_row.addStretch()

        main_layout.addLayout(nav_row)

        # 2. Main Two-Column Container
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(24)

        # --- Left Column: Hero Cover & Controls ---
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(12)

        # Cover Frame
        self.cover_frame = QFrame(self)
        self.cover_frame.setObjectName("detailCoverFrame")
        self.cover_frame.setFixedSize(210, 210)
        self.cover_frame.setStyleSheet("""
            QFrame#detailCoverFrame {
                background: #12151F;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        c_layout = QVBoxLayout(self.cover_frame)
        c_layout.setContentsMargins(0, 0, 0, 0)

        self.cover_img = QLabel(self.cover_frame)
        self.cover_img.setObjectName("detailCoverImg")
        self.cover_img.setAlignment(Qt.AlignCenter)
        self.cover_img.setFixedSize(210, 210)
        c_layout.addWidget(self.cover_img)
        left_col.addWidget(self.cover_frame)

        # Title
        self.title_lbl = QLabel("Mix Title", self)
        self.title_lbl.setObjectName("detailTitleLbl")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 15px; font-weight: 900; line-height: 1.2;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setFixedWidth(210)
        left_col.addWidget(self.title_lbl)

        # Subtitle / Metadata
        self.meta_lbl = QLabel("Playlist • 50 tracks", self)
        self.meta_lbl.setObjectName("detailMetaLbl")
        self.meta_lbl.setStyleSheet("color: #7E849B; font-size: 11px; line-height: 1.3;")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setFixedWidth(210)
        left_col.addWidget(self.meta_lbl)

        # Actions Row: Bookmark, Big Play, Options
        act_frame = QFrame(self)
        act_frame.setObjectName("detailActFrame")
        act_frame.setFixedWidth(210)
        act_frame.setStyleSheet("background: transparent; border: none;")

        act_row = QHBoxLayout(act_frame)
        act_row.setContentsMargins(0, 8, 0, 0)
        act_row.setSpacing(14)
        act_row.setAlignment(Qt.AlignCenter)

        self.save_btn = DetailSaveIconButton(act_frame)
        self.save_btn.clicked.connect(self._on_save_clicked)
        act_row.addWidget(self.save_btn, 0, Qt.AlignVCenter)

        # Big Round Play Button
        self.play_all_btn = QPushButton(act_frame)
        self.play_all_btn.setObjectName("detailPlayAllBtn")
        self.play_all_btn.setFixedSize(46, 46)
        self.play_all_btn.setCursor(Qt.PointingHandCursor)
        self.play_all_btn.setStyleSheet("""
            QPushButton#detailPlayAllBtn {
                background: #FFFFFF;
                border: none;
                border-radius: 23px;
            }
            QPushButton#detailPlayAllBtn:hover {
                background: #E0E0E0;
            }
        """)
        play_svg = '<svg viewBox="0 0 24 24" width="20" height="20"><polygon points="8,5 19,12 8,19" fill="#0B0D13"/></svg>'
        self.play_all_btn.setIcon(QIcon(render_svg_pixmap(play_svg, 18, 18)))
        self.play_all_btn.setIconSize(QSize(18, 18))
        self.play_all_btn.clicked.connect(self._on_play_all_clicked)
        act_row.addWidget(self.play_all_btn, 0, Qt.AlignVCenter)

        # Options Button
        self.opt_btn = DetailOptIconButton(act_frame)
        self.opt_btn.clicked.connect(self._show_options_menu)
        act_row.addWidget(self.opt_btn, 0, Qt.AlignVCenter)

        left_col.addWidget(act_frame)
        left_col.addStretch()

        content_row.addLayout(left_col)

        # --- Right Column: Tracklist Table ---
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        # Table Header Frame with bottom separator line
        tbl_hdr_frame = QFrame(self)
        tbl_hdr_frame.setObjectName("detailTableHdrFrame")
        tbl_hdr_frame.setStyleSheet("""
            QFrame#detailTableHdrFrame {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        tbl_hdr = QHBoxLayout(tbl_hdr_frame)
        tbl_hdr.setContentsMargins(12, 0, 12, 6)
        tbl_hdr.setSpacing(14)

        h_num = QLabel("#", tbl_hdr_frame)
        h_num.setFixedWidth(26)
        h_num.setAlignment(Qt.AlignCenter)
        h_num.setStyleSheet("color: #555968; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        tbl_hdr.addWidget(h_num)

        h_title = QLabel("TITLE", tbl_hdr_frame)
        h_title.setStyleSheet("color: #555968; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold; letter-spacing: 0.8px;")
        tbl_hdr.addWidget(h_title, stretch=1)

        h_dur = QLabel("DURATION", tbl_hdr_frame)
        h_dur.setFixedWidth(60)
        h_dur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h_dur.setStyleSheet("color: #555968; font-family: 'Orbitron', sans-serif; font-size: 10px; font-weight: bold;")
        tbl_hdr.addWidget(h_dur)

        right_col.addWidget(tbl_hdr_frame)

        # Tracklist Container Widget inside dynamic smooth scroll area
        from smooth_scroll import SmoothScrollArea
        self.track_scroll = SmoothScrollArea(self)
        self.track_scroll.setObjectName("detailTrackScroll")
        self.track_scroll.setWidgetResizable(True)
        self.track_scroll.setFrameShape(QFrame.NoFrame)
        self.track_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.track_scroll.setMinimumHeight(150)
        self.track_scroll.setStyleSheet("""
            QScrollArea#detailTrackScroll { background: transparent; border: none; }
            QScrollArea#detailTrackScroll > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.03);
                width: 14px;
                border-radius: 7px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 5px;
                min-height: 40px;
                border: none;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: none;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; background: none; border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        if self.track_scroll.viewport():
            self.track_scroll.viewport().setStyleSheet("background: transparent;")

        self.track_container = QWidget()
        self.track_container.setObjectName("detailTrackContainer")
        self.track_container.setStyleSheet("QWidget#detailTrackContainer { background: transparent; }")
        self.track_layout = QVBoxLayout(self.track_container)
        self.track_layout.setContentsMargins(0, 0, 0, 0)
        self.track_layout.setSpacing(2)
        self.track_layout.addStretch()

        self.track_scroll.setWidget(self.track_container)
        right_col.addWidget(self.track_scroll, stretch=1)

        content_row.addLayout(right_col, stretch=1)
        main_layout.addLayout(content_row, stretch=1)

    def set_data(self, playlist_data: dict):
        self._playlist_data = playlist_data
        title = playlist_data.get("title", "Unknown Playlist")
        self.title_lbl.setText(title)
        self.breadcrumb_lbl.setText(f"MIX / {title.upper()}")

        # Metadata
        source = playlist_data.get("source", "youtube").capitalize()
        badge = playlist_data.get("badge") or "MIX"
        desc = playlist_data.get("description", "")
        self.meta_lbl.setText(f"{badge} • {source}\n{desc}")

        # Render Thumbnail (0ms instant cache check)
        thumb = playlist_data.get("thumbnail_url") or playlist_data.get("thumbnail") or ""
        if thumb:
            cached_bytes = None
            try:
                from ImageCacheEngine import ImageCacheEngine
                cached_bytes = ImageCacheEngine.get_instance().get_bytes(thumb)
            except Exception:
                pass

            if cached_bytes:
                self._apply_cover(thumb, cached_bytes)
            else:
                if self._image_loader and self._image_loader.isRunning():
                    self._image_loader.cancel()
                    self._image_loader.wait(50)
                self._image_loader = AsyncImageLoader(thumb, self)
                self._image_loader.loaded.connect(self._apply_cover)
                self._image_loader.start()
        else:
            self.cover_img.setText("NO COVER")

        # Instant memory/disk cache check (0ms instant open)
        clean_id = playlist_data.get("id", "")
        cached = YouTubeAccountEngine.get_instance().get_cached_playlist_tracks(clean_id)
        if cached:
            self._render_tracks(cached)
            return

        # Populate Tracks
        tracks = playlist_data.get("tracks", [])
        if tracks:
            self._render_tracks(tracks)
        else:
            # Fetch safely via QThread worker with progressive streaming
            if self._fetch_worker and self._fetch_worker.isRunning():
                self._fetch_worker.cancel()
                self._fetch_worker.wait(50)
            self._fetch_worker = FetchPlaylistDetailWorker(clean_id, playlist_data, self)
            self._fetch_worker.tracksReady.connect(self._render_tracks)
            self._fetch_worker.moreTracksReady.connect(self._append_progressive_tracks)
            self._fetch_worker.start()

    def _apply_cover(self, url: str, data_bytes: bytes):
        pix = make_pixmap_from_bytes(data_bytes)
        if pix and not pix.isNull():
            scaled = pix.scaled(210, 210, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            crop_x = max(0, (scaled.width() - 210) // 2)
            crop_y = max(0, (scaled.height() - 210) // 2)
            cropped = scaled.copy(crop_x, crop_y, 210, 210)

            rounded = QPixmap(210, 210)
            rounded.fill(Qt.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 210, 210, 10, 10)
            p.setClipPath(path)
            p.drawPixmap(0, 0, cropped)
            p.end()

            self.cover_img.setPixmap(rounded)

    def _render_tracks(self, tracks: List[dict]):
        self._tracks = list(tracks)
        self.track_container.setUpdatesEnabled(False)
        try:
            while self.track_layout.count() > 1:
                item = self.track_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            accent = "#FF0000" if self._playlist_data.get("source") == "youtube" else "#FF5B06"
            for idx, tr in enumerate(tracks):
                row = StreamTrackRowWidget(idx + 1, tr, accent_color=accent, parent=self.track_container)
                row.trackClicked.connect(self._on_track_clicked)
                row.trackDoubleClicked.connect(self._on_track_clicked)
                row.show()
                self.track_layout.insertWidget(idx, row)
        finally:
            self.track_container.setUpdatesEnabled(True)

        self.track_container.adjustSize()
        self.track_container.updateGeometry()
        if hasattr(self, 'track_scroll') and self.track_scroll:
            self.track_scroll.updateGeometry()
        self.track_container.update()

        count = len(tracks)
        tot_sec = sum(t.get("duration", 0) for t in tracks)
        m, s = divmod(int(tot_sec), 60)
        h, m = divmod(m, 60)
        dur_text = f"{h}h {m}m" if h > 0 else f"{m} min"
        badge = self._playlist_data.get("badge") or "PLAYLIST"
        self.meta_lbl.setText(f"{badge} • {count} tracks • {dur_text}\n{self._playlist_data.get('description', '')}")

        # Automatically pre-warm stream URLs for unplayed tracks in background
        if tracks:
            try:
                from fast_stream_resolver import prefetch_batch
                prefetch_batch(tracks, limit=8)
            except Exception:
                pass

        # Dynamically resolve cover art from first genuine track if current cover is generic Rick Astley
        current_thumb = self._playlist_data.get("thumbnail_url", "")
        if tracks and tracks[0].get("thumbnail_url") and (not current_thumb or "dQw4w9WgXcQ" in current_thumb):
            first_thumb = tracks[0]["thumbnail_url"]
            cached_first = None
            try:
                from ImageCacheEngine import ImageCacheEngine
                cached_first = ImageCacheEngine.get_instance().get_bytes(first_thumb)
            except Exception:
                pass
            if cached_first:
                self._apply_cover(first_thumb, cached_first)
            else:
                if self._image_loader and self._image_loader.isRunning():
                    self._image_loader.cancel()
                self._image_loader = AsyncImageLoader(first_thumb, self)
                self._image_loader.loaded.connect(self._apply_cover)
                self._image_loader.start()

    def _append_progressive_tracks(self, new_tracks: List[dict]):
        if not new_tracks:
            return

        existing_vids = {t.get("video_id") for t in self._tracks if t.get("video_id")}
        unique_new = [t for t in new_tracks if t.get("video_id") not in existing_vids]
        if not unique_new:
            return

        self.track_container.setUpdatesEnabled(False)
        start_idx = len(self._tracks)
        accent = "#FF0000" if self._playlist_data.get("source") == "youtube" else "#FF5B06"

        try:
            for i, tr in enumerate(unique_new):
                row = StreamTrackRowWidget(start_idx + i + 1, tr, accent_color=accent, parent=self.track_container)
                row.trackClicked.connect(self._on_track_clicked)
                row.trackDoubleClicked.connect(self._on_track_clicked)
                row.show()
                # Insert before trailing stretch item
                self.track_layout.insertWidget(start_idx + i, row)
            self._tracks.extend(unique_new)
        finally:
            self.track_container.setUpdatesEnabled(True)

        self.track_container.adjustSize()
        self.track_container.updateGeometry()
        if hasattr(self, 'track_scroll') and self.track_scroll:
            self.track_scroll.updateGeometry()
        self.track_container.update()

        count = len(self._tracks)
        tot_sec = sum(t.get("duration", 0) for t in self._tracks)
        m, s = divmod(int(tot_sec), 60)
        h, m = divmod(m, 60)
        dur_text = f"{h}h {m}m" if h > 0 else f"{m} min"
        badge = self._playlist_data.get("badge") or "PLAYLIST"
        self.meta_lbl.setText(f"{badge} • {count} tracks • {dur_text}\n{self._playlist_data.get('description', '')}")

    def _on_track_clicked(self, track: dict):
        self.playTrackRequested.emit(track)

    def _on_play_all_clicked(self):
        if self._tracks:
            payload = dict(self._playlist_data)
            payload["tracks"] = self._tracks
            self.playAllRequested.emit(payload)

    def _on_save_clicked(self):
        settings = QSettings("TDD131", "HELXAID")
        always_save = settings.value("MusicSettings/stream_save_always", False, type=bool)
        saved_folder = settings.value("MusicSettings/stream_save_folder", "", type=str)
        if always_save and saved_folder and os.path.isdir(saved_folder):
            # User set "Always save without asking" -> execute immediately
            self._on_floating_save_confirmed(self._playlist_data, saved_folder)
            return

        if hasattr(self, '_save_floating_panel') and self._save_floating_panel:
            try:
                self._save_floating_panel.close_panel()
            except Exception:
                pass
            self._save_floating_panel = None

        top_window = self.window() or self
        self._save_floating_panel = SaveStreamFloatingPanel(self._playlist_data, top_window)
        self._save_floating_panel.saveConfirmed.connect(self._on_floating_save_confirmed)
        self._save_floating_panel.show_centered()

    def _on_floating_save_confirmed(self, track_data: dict, folder: str):
        payload = dict(track_data)
        if self._tracks:
            payload["tracks"] = self._tracks
        self.savePlaylistRequested.emit(payload)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_save_floating_panel') and self._save_floating_panel and self._save_floating_panel.isVisible():
            self._save_floating_panel.show_centered()

    def _show_options_menu(self):
        """Displays the Cyberpunk Context Menu anchored beneath detailOptBtn."""
        menu = QMenu(self)
        menu.setObjectName("detailOptionsMenu")
        menu.setStyleSheet("""
            QMenu#detailOptionsMenu {
                background: rgba(25, 25, 35, 0.98);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
                font-family: 'Orbitron', 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu#detailOptionsMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
                color: #e0e0e0;
                background: transparent;
            }
            QMenu#detailOptionsMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
            QMenu#detailOptionsMenu::icon {
                padding-left: 6px;
                padding-right: 4px;
            }
            QMenu#detailOptionsMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 5px 10px;
            }
        """)

        # 1. Shuffle Play
        act_shuffle = menu.addAction(QIcon(render_colored_svg_pixmap("shuffle.svg", 16, 16, "#e0e0e0")), "Shuffle Play")
        act_shuffle.triggered.connect(self._on_shuffle_play)

        # 2. Add to Queue
        act_queue = menu.addAction(QIcon(render_colored_svg_pixmap("menu-add-queue.svg", 16, 16, "#e0e0e0")), "Add All to Queue")
        act_queue.triggered.connect(self._on_add_to_queue)

        menu.addSeparator()

        # 3. Download All Tracks
        act_download = menu.addAction(QIcon(render_colored_svg_pixmap("menu-download.svg", 16, 16, "#e0e0e0")), "Download Collection")
        act_download.triggered.connect(self._on_download_all)

        # 4. Copy Stream Link
        act_copy = menu.addAction(QIcon(render_colored_svg_pixmap("menu-share.svg", 16, 16, "#e0e0e0")), "Copy Stream URL")
        act_copy.triggered.connect(self._on_copy_stream_url)

        menu.addSeparator()

        # 5. Open in Browser
        act_browser = menu.addAction(QIcon(render_colored_svg_pixmap("open-browser.svg", 16, 16, "#e0e0e0")), "Open in Browser")
        act_browser.triggered.connect(self._on_open_in_browser)

        # 6. Refresh Mix
        act_refresh = menu.addAction(QIcon(render_colored_svg_pixmap("refresh.svg", 16, 16, "#e0e0e0")), "Refresh Mix")
        act_refresh.triggered.connect(self._on_refresh_mix)

        # Positioning: Anchored 4px below opt_btn
        pos = self.opt_btn.mapToGlobal(QPoint(0, self.opt_btn.height() + 4))
        menu.exec(pos)

    def _on_shuffle_play(self):
        if not self._tracks:
            return
        shuffled = random.sample(self._tracks, len(self._tracks))
        payload = dict(self._playlist_data)
        payload["tracks"] = shuffled
        payload["is_shuffle"] = True
        self.playAllRequested.emit(payload)

    def _on_add_to_queue(self):
        if not self._tracks:
            return
        payload = dict(self._playlist_data)
        payload["tracks"] = self._tracks
        self.addToQueueRequested.emit(payload)

    def _on_download_all(self):
        url = self._playlist_data.get("original_url") or self._playlist_data.get("url") or ""
        title = self._playlist_data.get("title", "Online Playlist")
        if not url and self._tracks and len(self._tracks) > 0:
            url = self._tracks[0].get("original_url") or self._tracks[0].get("url") or ""
        if not url:
            browse_id = self._playlist_data.get("id") or ""
            if browse_id:
                url = f"https://www.youtube.com/playlist?list={browse_id}"
        if url:
            self.downloadPlaylistRequested.emit(url, title)

    def _on_copy_stream_url(self):
        url = self._playlist_data.get("original_url") or self._playlist_data.get("url") or ""
        if not url:
            browse_id = self._playlist_data.get("id") or ""
            if browse_id:
                url = f"https://www.youtube.com/playlist?list={browse_id}"
        if url:
            QApplication.clipboard().setText(url)

    def _on_open_in_browser(self):
        url = self._playlist_data.get("original_url") or self._playlist_data.get("url") or ""
        if not url:
            browse_id = self._playlist_data.get("id") or ""
            if browse_id:
                url = f"https://www.youtube.com/playlist?list={browse_id}"
        if url:
            import webbrowser
            webbrowser.open(url)

    def _on_refresh_mix(self):
        if hasattr(self, '_playlist_data') and self._playlist_data:
            self.set_data(self._playlist_data)


class StreamHeroCard(QFrame):
    """Refined Hero Spotlight Card for #1 Top Match."""
    playClicked = Signal(dict)
    playlistClicked = Signal(dict)
    saveClicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamHeroCard")
        self._track_data: Optional[Dict[str, Any]] = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("QFrame#streamHeroCard { background: rgba(24, 25, 32, 0.95); border-radius: 10px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)

        self.art_lbl = QLabel(self)
        self.art_lbl.setObjectName("heroArtLabel")
        self.art_lbl.setFixedSize(110, 110)
        self.art_lbl.setAlignment(Qt.AlignCenter)
        self.art_lbl.setStyleSheet("QLabel#heroArtLabel { background: #121318; border-radius: 8px; }")
        layout.addWidget(self.art_lbl)

        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 0, 0, 0)
        meta_col.setSpacing(4)

        tag_row = QHBoxLayout()
        self.badge_lbl = QLabel("CANONICAL TOP MATCH", self)
        self.badge_lbl.setObjectName("heroBadgeLabel")
        self.badge_lbl.setStyleSheet("background: #FF5B06; color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: 900; border-radius: 3px; padding: 2px 8px;")
        tag_row.addWidget(self.badge_lbl)

        self.score_lbl = QLabel("MATCH SCORE: 98%", self)
        self.score_lbl.setObjectName("heroScoreLabel")
        self.score_lbl.setStyleSheet("color: #00E676; font-size: 10px; font-weight: bold; margin-left: 8px;")
        tag_row.addWidget(self.score_lbl)
        tag_row.addStretch()
        meta_col.addLayout(tag_row)

        self.title_lbl = QLabel("Title Placeholder", self)
        self.title_lbl.setObjectName("heroTitleLabel")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 15px; font-weight: bold;")
        meta_col.addWidget(self.title_lbl)

        self.artist_lbl = QLabel("Artist • Album", self)
        self.artist_lbl.setObjectName("heroArtistLabel")
        self.artist_lbl.setStyleSheet("color: #a0a2ac; font-size: 12px;")
        meta_col.addWidget(self.artist_lbl)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 0)
        btn_row.setSpacing(8)

        self.play_btn = QPushButton("PLAY NOW", self)
        self.play_btn.setObjectName("heroPlayBtn")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background: #FF5B06; color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; border-radius: 5px; padding: 6px 16px; border: none;
            }
            QPushButton:hover { background: #FF7026; }
        """)
        self.play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self.play_btn)

        self.add_btn = QPushButton("+ Add to Queue", self)
        self.add_btn.setObjectName("heroAddQueueBtn")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("background: rgba(255, 255, 255, 0.06); color: #FFFFFF; font-size: 11px; border-radius: 5px; padding: 6px 12px; border: none;")
        self.add_btn.clicked.connect(self._on_playlist)
        btn_row.addWidget(self.add_btn)

        self.save_btn = QPushButton("Save .hxstream", self)
        self.save_btn.setObjectName("heroSaveStreamBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet("background: rgba(255, 255, 255, 0.06); color: #FFFFFF; font-size: 11px; border-radius: 5px; padding: 6px 12px; border: none;")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        btn_row.addStretch()
        meta_col.addLayout(btn_row)

        layout.addLayout(meta_col, stretch=1)

    def set_data(self, data: Dict[str, Any]):
        self._track_data = data
        self.title_lbl.setText(data.get('title', 'Unknown Title'))
        artist = data.get('artist', 'Unknown Artist')
        album = data.get('album', '')
        self.artist_lbl.setText(f"{artist} • {album}" if album else artist)
        score = data.get('score', 95)
        self.score_lbl.setText(f"MATCH: {int(score)}%")

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        if not pixmap or pixmap.isNull():
            return
        scaled = pixmap.scaled(110, 110, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rounded = QPixmap(110, 110)
        rounded.fill(Qt.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 110, 110, 8, 8)
        p.setClipPath(path)
        p.drawPixmap(0, 0, scaled)
        p.end()
        self.art_lbl.setPixmap(rounded)

    def _on_play(self):
        if self._track_data:
            self.playClicked.emit(self._track_data)

    def _on_playlist(self):
        if self._track_data:
            self.playlistClicked.emit(self._track_data)

    def _on_save(self):
        if self._track_data:
            self.saveClicked.emit(self._track_data)


class StreamCandidateCard(QFrame):
    """Compact Alternative Stream Candidate Card."""
    playClicked = Signal(dict)
    playlistClicked = Signal(dict)
    saveClicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamCandidateCard")
        self._item_data: Optional[Dict[str, Any]] = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(82)
        self.setStyleSheet("""
            QFrame#streamCandidateCard {
                background: #14161D; border-radius: 8px;
            }
            QFrame#streamCandidateCard:hover {
                background: #191B24;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.thumb_lbl = QLabel(self)
        self.thumb_lbl.setObjectName("candThumbLabel")
        self.thumb_lbl.setFixedSize(90, 64)
        self.thumb_lbl.setStyleSheet("background: #0E1015; border-radius: 4px;")
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.thumb_lbl)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(2)

        self.title_lbl = QLabel("Candidate Title", self)
        self.title_lbl.setObjectName("candTitleLabel")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold;")
        self.title_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_col.addWidget(self.title_lbl)

        self.channel_lbl = QLabel("Channel • 0:00", self)
        self.channel_lbl.setObjectName("candChannelLabel")
        self.channel_lbl.setStyleSheet("color: #888892; font-size: 9px;")
        self.channel_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_col.addWidget(self.channel_lbl)

        act_row = QHBoxLayout()
        act_row.setSpacing(4)

        play_btn = QPushButton("Play", self)
        play_btn.setObjectName("candPlayBtn")
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #FF5B06; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; border-radius: 3px; padding: 2px 8px; border: none;
            }
            QPushButton:hover { background: #FF5B06; color: #FFFFFF; }
        """)
        play_btn.clicked.connect(self._on_play)
        act_row.addWidget(play_btn)

        add_btn = QPushButton("+", self)
        add_btn.setObjectName("candAddBtn")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet("background: rgba(255,255,255,0.04); color: #c0c0c0; border-radius: 3px; padding: 2px 6px; border: none;")
        add_btn.clicked.connect(self._on_playlist)
        act_row.addWidget(add_btn)

        act_row.addStretch()
        info_col.addLayout(act_row)

        layout.addLayout(info_col, stretch=1)

    def set_data(self, item: Dict[str, Any]):
        self._item_data = item
        title = item.get('title', 'Unknown Title')
        channel = item.get('uploader', 'Unknown Artist')
        dur = item.get('duration', 0)
        dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur > 0 else "Stream"
        self.title_lbl.setText(title)
        self.channel_lbl.setText(f"{channel} • {dur_str}")

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        if not pixmap or pixmap.isNull():
            return
        w, h = 90, 64
        scaled = pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rounded = QPixmap(w, h)
        rounded.fill(Qt.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 4, 4)
        p.setClipPath(path)
        p.drawPixmap(0, 0, scaled)
        p.end()
        self.thumb_lbl.setPixmap(rounded)

    def _on_play(self):
        if self._item_data:
            self.playClicked.emit(self._item_data)

    def _on_playlist(self):
        if self._item_data:
            self.playlistClicked.emit(self._item_data)


class DirectStreamSyncWarningOverlayPanel(QWidget):
    """
    Floating overlay panel warning user when streaming on fallback/unsynced extension session.
    Matching HELXAIRO / helxairo_acCreateBtn floating modal aesthetic.
    
    Component Name: directStreamSyncWarningOverlay
    """
    closed = Signal()

    def __init__(self, parent_window, on_proceed_callback=None, on_proceed=None):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.on_proceed_callback = on_proceed if on_proceed is not None else on_proceed_callback
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("directStreamSyncWarningOverlay")
        
        if parent_window:
            self.setGeometry(0, 0, parent_window.width(), parent_window.height())
        
        self._setup_ui()
        
        # Shortcut Esc to proceed & close
        self._esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._esc_shortcut.activated.connect(self._on_proceed)

        # Opacity & animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _setup_ui(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        warning_icon_path = os.path.join(script_dir, "UI Icons", "warning-icon.svg").replace('\\', '/')

        self.setStyleSheet("""
            QWidget#directStreamSyncWarningOverlay {
                background-color: rgba(0, 0, 0, 0.65);
            }
            QFrame#directStreamWarningCard {
                background-color: rgba(18, 20, 27, 0.98);
                border-radius: 14px;
            }
            QWidget#directStreamWarningTitleBar {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("directStreamWarningCard")
        self.card.setFixedSize(500, 270)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 18)
        card_layout.setSpacing(14)

        # 1. Title Bar
        title_bar = QWidget()
        title_bar.setObjectName("directStreamWarningTitleBar")
        title_bar.setFixedHeight(46)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 16, 0)
        title_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("directStreamWarningIcon")
        icon_lbl.setFixedSize(20, 20)
        if os.path.exists(warning_icon_path):
            icon_lbl.setPixmap(QPixmap(warning_icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_lbl.setStyleSheet("background: transparent;")
        title_layout.addWidget(icon_lbl)

        title_lbl = QLabel("EXTENSION NOT SYNCHRONIZED")
        title_lbl.setObjectName("directStreamWarningTitle")
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: 900; letter-spacing: 0.5px; background: transparent;")
        title_layout.addWidget(title_lbl)

        # Amber Badge
        badge_lbl = QLabel("OFFLINE CACHE")
        badge_lbl.setObjectName("directStreamWarningBadge")
        badge_lbl.setStyleSheet("background-color: rgba(255, 91, 6, 0.15); color: #FF9100; font-family: 'Orbitron', sans-serif; font-size: 9px; font-weight: bold; border-radius: 4px; padding: 3px 8px; border: none;")
        title_layout.addWidget(badge_lbl)

        title_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("directStreamWarningCloseBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton#directStreamWarningCloseBtn {
                background: transparent; color: #7A7E8F; font-size: 14px; font-weight: bold; border: none; border-radius: 13px;
            }
            QPushButton#directStreamWarningCloseBtn:hover {
                background: rgba(255, 255, 255, 0.08); color: #FFFFFF;
            }
        """)
        close_btn.clicked.connect(self._on_proceed)
        title_layout.addWidget(close_btn)

        card_layout.addWidget(title_bar)

        # 2. Body Message
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(22, 4, 22, 4)
        body_layout.setSpacing(8)

        msg_title = QLabel("Running on Last Known Saved State")
        msg_title.setObjectName("directStreamWarningSubheader")
        msg_title.setStyleSheet("color: #FDA903; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; background: transparent;")
        body_layout.addWidget(msg_title)

        msg_body = QLabel(
            "HELXAID is currently streaming using your previously cached session because the Chrome Extension is offline or not yet connected in this run.\n\n"
            "Public streams will play smoothly. To sync your live liked songs, personal playlists, and latest recommendations, please sync via the Chrome Extension."
        )
        msg_body.setObjectName("directStreamWarningBody")
        msg_body.setWordWrap(True)
        msg_body.setStyleSheet("color: #A0A4B5; font-size: 11px; line-height: 1.45; background: transparent;")
        body_layout.addWidget(msg_body)

        card_layout.addWidget(body_widget, 1)

        # 3. Footer Action Buttons
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(22, 0, 22, 0)
        action_layout.setSpacing(12)

        open_ext_btn = FadeHoverButton("Open Extension", is_secondary=True, border_radius=6.0)
        open_ext_btn.setObjectName("directStreamOpenExtBtn")
        open_ext_btn.setFixedHeight(34)
        open_ext_btn.setFixedWidth(140)
        open_ext_btn.clicked.connect(self._open_extension)
        action_layout.addWidget(open_ext_btn)

        action_layout.addStretch()

        proceed_btn = FadeHoverButton("Continue Playing", is_secondary=False, border_radius=6.0, color_mode="default")
        proceed_btn.setObjectName("directStreamProceedBtn")
        proceed_btn.setFixedHeight(34)
        proceed_btn.setFixedWidth(145)
        proceed_btn.clicked.connect(self._on_proceed)
        action_layout.addWidget(proceed_btn)

        card_layout.addLayout(action_layout)
        outer_layout.addWidget(self.card)

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self._opacity_effect.setOpacity(0.0)
        self._fade_anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent_window:
            self.setGeometry(0, 0, self.parent_window.width(), self.parent_window.height())

    def _open_extension(self):
        try:
            import webbrowser
            ext_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_extension")
            webbrowser.open("chrome://extensions/")
            if os.path.exists(ext_dir):
                os.startfile(ext_dir)
        except Exception:
            pass
        self._on_proceed()

    def _on_proceed(self):
        self.close()
        self.closed.emit()
        if callable(self.on_proceed_callback):
            self.on_proceed_callback()


class DirectStreamPage(QWidget):
    """
    Master Page for HELXAIC Dedicated Direct Streaming & Cloud Accounts Hub.
    Component Name: DirectStreamPage
    """
    playStreamRequested = Signal(dict)
    addToPlaylistRequested = Signal(dict)
    saveStreamRequested = Signal(dict, str)
    downloadRequested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DirectStreamPage")
        self.setStyleSheet("QWidget#DirectStreamPage { background: transparent; }")
        from PySide6.QtGui import QPixmapCache
        QPixmapCache.setCacheLimit(16384)
        self._seq_id = 0
        self._unsynced_warning_shown = False
        self._live_extension_synced = False
        self._search_worker: Optional[StreamSearchWorker] = None
        self._recom_worker: Optional[RecommendationWorker] = None
        self._image_loaders: List[AsyncImageLoader] = []
        self._recent_history: List[Dict[str, Any]] = []
        self.featured_video_cards: List[YTMusicVideoCard] = []

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(350)
        self._debounce_timer.timeout.connect(self._exec_debounced_search)

        self._init_ui()
        self._load_history()
        self._load_cloud_feeds()

        YouTubeAccountEngine.get_instance().sessionChanged.connect(self._on_accounts_state_changed)
        YouTubeAccountEngine.get_instance().accountDetailsUpdated.connect(lambda d: self._on_accounts_state_changed())
        YouTubeAccountEngine.get_instance().cookiesReceived.connect(self._on_extension_cookies_received)
        SpotifyAccountEngine.get_instance().authStatusChanged.connect(self._on_accounts_state_changed)

    def _init_ui(self):
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(18, 14, 18, 14)
        master_layout.setSpacing(14)

        # 1. Omnisearch Bar at Top (Includes Top-Right Profile Pill)
        self.search_bar = StreamOmniSearchBar(self)
        self.search_bar.searchTriggered.connect(self._on_search_query_changed)
        self.search_bar.genreChipClicked.connect(self._on_search_query_changed)
        self.search_bar.profileClicked.connect(self._toggle_profile_panel)
        master_layout.addWidget(self.search_bar)

        # 2. Main Stack (Index 0: Unified Home View, Index 1: Search Results View, Index 2: Cloud Profile View)
        self.view_stack = QStackedWidget(self)
        self.view_stack.setObjectName("streamViewStack")
        self.view_stack.setStyleSheet("QStackedWidget#streamViewStack { background: transparent; }")

        # --- View 0: Unified Home View ---
        self.home_view = QWidget()
        self.home_view.setObjectName("streamHomeView")
        self.home_view.setStyleSheet("QWidget#streamHomeView { background: transparent; }")
        home_layout = QVBoxLayout(self.home_view)
        home_layout.setContentsMargins(0, 4, 14, 0)
        home_layout.setSpacing(12)

        # Section 1: Featured Live Streams & Videos
        vid_section_hdr = QHBoxLayout()
        vid_section_lbl = QLabel("MUSIC VIDEOS & LIVE STATIONS", self.home_view)
        vid_section_lbl.setObjectName("streamMusicVideosSectionTitle")
        vid_section_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        vid_section_hdr.addWidget(vid_section_lbl)
        vid_section_hdr.addStretch()

        vid_nav_layout = QHBoxLayout()
        vid_nav_layout.setSpacing(6)
        self.featured_prev_btn = create_section_nav_button("streamFeaturedPrevBtn", is_next=False, parent=self.home_view)
        self.featured_prev_btn.setToolTip("Previous items")
        self.featured_prev_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.featured_scroll, -1, 319, 12, 2))
        vid_nav_layout.addWidget(self.featured_prev_btn)

        self.featured_next_btn = create_section_nav_button("streamFeaturedNextBtn", is_next=True, parent=self.home_view)
        self.featured_next_btn.setToolTip("Next items")
        self.featured_next_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.featured_scroll, 1, 319, 12, 2))
        vid_nav_layout.addWidget(self.featured_next_btn)
        vid_section_hdr.addLayout(vid_nav_layout)
        home_layout.addLayout(vid_section_hdr)

        # Dedicated Horizontal Scroll Area for Featured Videos
        self.featured_scroll = QScrollArea(self.home_view)
        self.featured_scroll.setObjectName("featuredHorizontalScrollArea")
        self.featured_scroll.setWidgetResizable(True)
        self.featured_scroll.setFrameShape(QFrame.NoFrame)
        self.featured_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.featured_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.featured_scroll.setFixedHeight(264)
        self.featured_scroll.setStyleSheet(HORIZONTAL_SCROLLBAR_STYLE.replace("%ID%", "featuredHorizontalScrollArea"))

        self.featured_container = QWidget()
        self.featured_container.setObjectName("featuredContainerWidget")
        self.featured_container.setStyleSheet("QWidget#featuredContainerWidget { background: transparent; }")
        self.featured_layout = QHBoxLayout(self.featured_container)
        self.featured_layout.setContentsMargins(0, 0, 0, 0)
        self.featured_layout.setSpacing(12)
        self.featured_layout.addStretch()

        self.featured_video_cards = []
        presets = TasteProfileEngine.DEFAULT_PRESETS
        for i in range(len(presets)):
            preset = presets[i]
            card = YTMusicVideoCard(
                preset["title"], preset["artist"], preset["subtitle"],
                preset["original_url"], preset["bg_colors"], self.featured_container
            )
            card.setFixedSize(319, 236)
            card.badge_lbl.setText(preset["badge"])
            card.playClicked.connect(self._on_play_track)
            self.featured_layout.insertWidget(i, card)
            self.featured_video_cards.append(card)

        self.featured_scroll.setWidget(self.featured_container)
        home_layout.addWidget(self.featured_scroll)

        # Gap between Section 1 and Section 2
        home_layout.addSpacing(28)

        # Section 2: Algorithmic Mixes & Cloud Discoveries
        mix_hdr = QHBoxLayout()
        mix_lbl = QLabel("PERSONALIZED MIXES & DISCOVERIES", self.home_view)
        mix_lbl.setObjectName("streamPersonalizedMixesSectionTitle")
        mix_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        mix_hdr.addWidget(mix_lbl)
        mix_hdr.addStretch()

        mix_nav_layout = QHBoxLayout()
        mix_nav_layout.setSpacing(6)
        self.mixes_prev_btn = create_section_nav_button("streamMixesPrevBtn", is_next=False, parent=self.home_view)
        self.mixes_prev_btn.setToolTip("Previous mixes")
        self.mixes_prev_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.mixes_scroll, -1, 319, 12, 2))
        mix_nav_layout.addWidget(self.mixes_prev_btn)

        self.mixes_next_btn = create_section_nav_button("streamMixesNextBtn", is_next=True, parent=self.home_view)
        self.mixes_next_btn.setToolTip("Next mixes")
        self.mixes_next_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.mixes_scroll, 1, 319, 12, 2))
        mix_nav_layout.addWidget(self.mixes_next_btn)
        mix_hdr.addLayout(mix_nav_layout)
        home_layout.addLayout(mix_hdr)

        # Dedicated Horizontal Scroll Area for Mix Cards
        self.mixes_scroll = QScrollArea(self.home_view)
        self.mixes_scroll.setObjectName("mixesHorizontalScrollArea")
        self.mixes_scroll.setWidgetResizable(True)
        self.mixes_scroll.setFrameShape(QFrame.NoFrame)
        self.mixes_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mixes_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mixes_scroll.setFixedHeight(264)
        self.mixes_scroll.setStyleSheet(HORIZONTAL_SCROLLBAR_STYLE.replace("%ID%", "mixesHorizontalScrollArea"))

        self.mixes_container = QWidget()
        self.mixes_container.setObjectName("mixesContainerWidget")
        self.mixes_container.setStyleSheet("QWidget#mixesContainerWidget { background: transparent; }")
        self.cloud_mixes_layout = QHBoxLayout(self.mixes_container)
        self.cloud_mixes_layout.setContentsMargins(0, 0, 0, 0)
        self.cloud_mixes_layout.setSpacing(12)
        self.cloud_mixes_layout.addStretch()

        self.mixes_scroll.setWidget(self.mixes_container)
        home_layout.addWidget(self.mixes_scroll)

        # Gap between Section 2 and Section 3
        home_layout.addSpacing(28)

        # Section 3: Cloud Playlists & Liked Songs
        pl_hdr = QHBoxLayout()
        pl_lbl = QLabel("YOUR CLOUD PLAYLISTS & LIKED MUSIC", self.home_view)
        pl_lbl.setObjectName("streamCloudPlaylistsSectionTitle")
        pl_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        pl_hdr.addWidget(pl_lbl)
        pl_hdr.addStretch()

        pl_nav_layout = QHBoxLayout()
        pl_nav_layout.setSpacing(6)
        self.playlists_prev_btn = create_section_nav_button("streamPlaylistsPrevBtn", is_next=False, parent=self.home_view)
        self.playlists_prev_btn.setToolTip("Previous playlists")
        self.playlists_prev_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.playlists_scroll, -1, 319, 12, 2))
        pl_nav_layout.addWidget(self.playlists_prev_btn)

        self.playlists_next_btn = create_section_nav_button("streamPlaylistsNextBtn", is_next=True, parent=self.home_view)
        self.playlists_next_btn.setToolTip("Next playlists")
        self.playlists_next_btn.clicked.connect(lambda: scroll_horizontal_by_items(self.playlists_scroll, 1, 319, 12, 2))
        pl_nav_layout.addWidget(self.playlists_next_btn)
        pl_hdr.addLayout(pl_nav_layout)
        home_layout.addLayout(pl_hdr)

        # Dedicated Horizontal Scroll Area for Cloud Playlists
        self.playlists_scroll = QScrollArea(self.home_view)
        self.playlists_scroll.setObjectName("playlistsHorizontalScrollArea")
        self.playlists_scroll.setWidgetResizable(True)
        self.playlists_scroll.setFrameShape(QFrame.NoFrame)
        self.playlists_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.playlists_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.playlists_scroll.setFixedHeight(264)
        self.playlists_scroll.setStyleSheet(HORIZONTAL_SCROLLBAR_STYLE.replace("%ID%", "playlistsHorizontalScrollArea"))

        self.playlists_container = QWidget()
        self.playlists_container.setObjectName("playlistsContainerWidget")
        self.playlists_container.setStyleSheet("QWidget#playlistsContainerWidget { background: transparent; }")
        self.cloud_playlists_layout = QHBoxLayout(self.playlists_container)
        self.cloud_playlists_layout.setContentsMargins(0, 0, 0, 0)
        self.cloud_playlists_layout.setSpacing(12)
        self.cloud_playlists_layout.addStretch()

        self.playlists_scroll.setWidget(self.playlists_container)
        home_layout.addWidget(self.playlists_scroll)

        # Gap between Section 3 and Section 4
        home_layout.addSpacing(28)

        # Section 4: Quick Picks & Recent Plays
        quick_hdr = QHBoxLayout()
        quick_lbl = QLabel("QUICK PICKS & RECENT PLAYS", self.home_view)
        quick_lbl.setObjectName("streamQuickPicksSectionTitle")
        quick_lbl.setStyleSheet("color: #FFFFFF; font-family: 'Orbitron', sans-serif; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        quick_hdr.addWidget(quick_lbl)
        quick_hdr.addStretch()

        clear_hist_btn = QPushButton("Clear History", self.home_view)
        clear_hist_btn.setObjectName("streamClearHistoryBtn")
        clear_hist_btn.setCursor(Qt.PointingHandCursor)
        clear_hist_btn.setStyleSheet("background: transparent; color: #70727e; font-size: 10px; border: none;")
        clear_hist_btn.clicked.connect(self._clear_history)
        quick_hdr.addWidget(clear_hist_btn)

        home_layout.addLayout(quick_hdr)

        self.quick_picks_grid = QGridLayout()
        self.quick_picks_grid.setContentsMargins(0, 0, 0, 0)
        self.quick_picks_grid.setSpacing(8)
        self.quick_picks_grid.setColumnStretch(0, 1)
        self.quick_picks_grid.setColumnStretch(1, 1)
        self.quick_picks_grid.setColumnStretch(2, 1)
        home_layout.addLayout(self.quick_picks_grid)
        home_layout.addSpacing(20)
        home_layout.addStretch()

        # Wrap Home View in dedicated smooth scroll area
        from smooth_scroll import SmoothScrollArea
        self.home_scroll = SmoothScrollArea(self)
        self.home_scroll.setObjectName("streamHomeScroll")
        self.home_scroll.setFrameShape(QFrame.NoFrame)
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.home_scroll.setStyleSheet("""
            QScrollArea#streamHomeScroll { background: transparent; border: none; }
            QScrollArea#streamHomeScroll > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 16px;
                border-radius: 8px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                border-radius: 7px;
                min-height: 40px;
                border: 2px solid rgba(253, 169, 3, 0.8);
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                border: 2px solid #FFFF00;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; background: none; border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        if self.home_scroll.viewport():
            self.home_scroll.viewport().setStyleSheet("background: transparent;")
        self.home_scroll.setWidget(self.home_view)
        self.view_stack.addWidget(self.home_scroll)  # Index 0
        self.scroll_area = self.home_scroll

        # --- View 1: Search Results ---
        self.results_view = QWidget()
        self.results_view.setObjectName("streamResultsView")
        self.results_view.setStyleSheet("QWidget#streamResultsView { background: transparent; }")
        results_layout = QVBoxLayout(self.results_view)
        results_layout.setContentsMargins(0, 4, 14, 0)
        results_layout.setSpacing(14)

        self.hero_card = StreamHeroCard(self.results_view)
        self.hero_card.playClicked.connect(self._on_play_track)
        self.hero_card.playlistClicked.connect(self._on_add_playlist)
        self.hero_card.saveClicked.connect(self._on_save_stream)
        results_layout.addWidget(self.hero_card)

        alt_lbl = QLabel("ALTERNATIVE CANDIDATES & MULTI-MATCHES", self.results_view)
        alt_lbl.setObjectName("streamAltCandidatesSectionTitle")
        alt_lbl.setStyleSheet("color: #a0a2ac; font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        results_layout.addWidget(alt_lbl)

        self.cand_grid_layout = QGridLayout()
        self.cand_grid_layout.setSpacing(10)
        self.candidate_cards: List[StreamCandidateCard] = []

        for i in range(6):
            card = StreamCandidateCard(self.results_view)
            card.playClicked.connect(self._on_play_track)
            card.playlistClicked.connect(self._on_add_playlist)
            card.saveClicked.connect(self._on_save_stream)
            self.candidate_cards.append(card)
            row, col = divmod(i, 3)
            self.cand_grid_layout.addWidget(card, row, col)

        results_layout.addLayout(self.cand_grid_layout)
        results_layout.addStretch()

        self.view_stack.addWidget(self.results_view)  # Index 1

        # --- View 2: Cloud Profile & Accounts Panel (Lazy-loaded on first click) ---
        self.profile_view = None
        self.profile_scroll = None
        self._profile_placeholder = QWidget()
        self.view_stack.addWidget(self._profile_placeholder)  # Index 2

        # --- View 3: Mix & Playlist Detail Panel (Lazy-loaded on first click) ---
        self.playlist_detail_view = None
        self._playlist_placeholder = QWidget()
        self.view_stack.addWidget(self._playlist_placeholder)  # Index 3

        # Add View Stack directly to Master Layout with stretch
        master_layout.addWidget(self.view_stack, stretch=1)
        self.view_stack.currentChanged.connect(self._on_view_changed)

    def _on_view_changed(self, idx: int):
        pass

    def _ensure_profile_view(self):
        if self.profile_view is None:
            self.profile_view = CloudProfileView(self)
            self.profile_view.backClicked.connect(self._show_home_panel)
            self.profile_view.accountsChanged.connect(self._on_accounts_state_changed)

            from smooth_scroll import SmoothScrollArea
            self.profile_scroll = SmoothScrollArea(self)
            self.profile_scroll.setObjectName("streamProfileScroll")
            self.profile_scroll.setFrameShape(QFrame.NoFrame)
            self.profile_scroll.setWidgetResizable(True)
            self.profile_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.profile_scroll.setStyleSheet("""
                QScrollArea#streamProfileScroll { background: transparent; border: none; }
                QScrollArea#streamProfileScroll > QWidget > QWidget { background: transparent; }
                QScrollBar:vertical {
                    background: transparent;
                    width: 16px;
                    border-radius: 8px;
                    margin: 4px;
                }
                QScrollBar::handle:vertical {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:0.5 #FDA903, stop:1 #FF5B06);
                    border-radius: 7px;
                    min-height: 40px;
                    border: 2px solid rgba(253, 169, 3, 0.8);
                }
                QScrollBar::handle:vertical:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FDA903, stop:0.5 #FFFF00, stop:1 #FDA903);
                    border: 2px solid #FFFF00;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px; background: none; border: none;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: transparent;
                }
            """)
            if self.profile_scroll.viewport():
                self.profile_scroll.viewport().setStyleSheet("background: transparent;")
            self.profile_scroll.setWidget(self.profile_view)
            if self._profile_placeholder:
                self.view_stack.removeWidget(self._profile_placeholder)
                self._profile_placeholder.deleteLater()
                self._profile_placeholder = None
            self.view_stack.insertWidget(2, self.profile_scroll)

    def _ensure_playlist_detail_view(self):
        if self.playlist_detail_view is None:
            self.playlist_detail_view = StreamPlaylistDetailView(self)
            self.playlist_detail_view.backClicked.connect(self._show_home_panel)
            self.playlist_detail_view.playTrackRequested.connect(self._on_play_track)
            self.playlist_detail_view.playAllRequested.connect(self._on_play_track)
            self.playlist_detail_view.savePlaylistRequested.connect(self._on_save_stream)
            self.playlist_detail_view.addToQueueRequested.connect(self._on_add_playlist)
            self.playlist_detail_view.downloadPlaylistRequested.connect(lambda u, t: self.downloadRequested.emit(u, t))
            if self._playlist_placeholder:
                self.view_stack.removeWidget(self._playlist_placeholder)
                self._playlist_placeholder.deleteLater()
                self._playlist_placeholder = None
            self.view_stack.insertWidget(3, self.playlist_detail_view)

    def _toggle_profile_panel(self):
        """Toggle between Home view (Index 0) and Cloud Profile panel (Index 2)."""
        self._ensure_profile_view()
        if self.view_stack.currentIndex() == 2:
            self._show_home_panel()
        else:
            self.search_bar.input_edit.clear()
            self.search_bar.clear_btn.hide()
            self.search_bar.hide()
            self.profile_view.refresh_state()
            if hasattr(self, 'scroll_area') and self.scroll_area and self.scroll_area.verticalScrollBar():
                self.scroll_area.verticalScrollBar().setValue(0)
            self.view_stack.setCurrentIndex(2)
            self.search_bar.profile_btn.update_status(is_active_panel=True)

    def _on_extension_cookies_received(self, cookies: dict):
        print("[DirectStreamPage] Real-time session sync received from Chrome extension!")
        self._live_extension_synced = True
        self._on_accounts_state_changed()

    def _is_extension_synced(self) -> bool:
        """Check if session is currently live-synchronized from Chrome extension."""
        if getattr(self, '_live_extension_synced', False):
            return True
        yt = YouTubeAccountEngine.get_instance()
        if yt.is_authenticated():
            synced_at = yt.session_data.get("synced_at", 0)
            if synced_at and (time.time() - synced_at < 7200):
                return True
        return False

    def _emit_play_stream(self, payload: dict):
        """Internal dispatcher for stream playback with first-play unsynced extension notification."""
        if not getattr(self, '_unsynced_warning_shown', False) and not self._is_extension_synced():
            self._unsynced_warning_shown = True
            parent_win = self.window()
            if parent_win:
                overlay = DirectStreamSyncWarningOverlayPanel(parent_win, on_proceed=lambda: self.playStreamRequested.emit(payload))
                overlay.show()
                overlay.raise_()
                return

        self.playStreamRequested.emit(payload)

    def on_page_activated(self):
        """Lifecycle hook invoked whenever user navigates to or loads the Direct Stream page."""
        is_profile_active = (self.view_stack.currentIndex() == 2)
        if hasattr(self, 'search_bar') and hasattr(self.search_bar, 'profile_btn'):
            self.search_bar.profile_btn.update_status(is_active_panel=is_profile_active)
        if hasattr(self, 'profile_view') and self.profile_view:
            self.profile_view.refresh_state()

        # Re-verify live authentication from disk cache in case session was synced while on another tab
        yt_engine = YouTubeAccountEngine.get_instance()
        persisted = yt_engine._load_persisted_session()
        if persisted and isinstance(persisted, dict):
            cookies = persisted.get("cookies", {})
            sapisid = persisted.get("sapisid") or cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")
            if sapisid or persisted.get("access_token"):
                if not yt_engine.session_data or yt_engine.session_data.get("sapisid") != sapisid:
                    yt_engine.session_data = persisted
                    self._on_accounts_state_changed()
                    return

        # If authenticated, ensure cloud feeds are genuinely loaded
        if yt_engine.is_authenticated():
            self._load_cloud_feeds()

    def showEvent(self, event):
        super().showEvent(event)
        self.on_page_activated()

    def _show_home_panel(self):
        self.search_bar.show()
        self.view_stack.setCurrentIndex(0)
        self.search_bar.profile_btn.update_status(is_active_panel=False)

    def _on_accounts_state_changed(self):
        is_profile_active = (self.view_stack.currentIndex() == 2)
        self.search_bar.profile_btn.update_status(is_active_panel=is_profile_active)
        if hasattr(self, 'profile_view') and self.profile_view:
            self.profile_view.refresh_state()
        self._load_cloud_feeds()
        self._load_recommendations()

    def _load_cloud_feeds(self):
        yt_engine = YouTubeAccountEngine.get_instance()
        if yt_engine.is_authenticated():
            if hasattr(self, "_yt_mixes_worker") and self._yt_mixes_worker and self._yt_mixes_worker.isRunning():
                self._yt_mixes_worker.cancel()
            self._yt_mixes_worker = FetchYTMixesWorker(self)
            self._yt_mixes_worker.mixesLoaded.connect(self._on_cloud_mixes_loaded)
            self._yt_mixes_worker.start()

            if hasattr(self, "_yt_pl_worker") and self._yt_pl_worker and self._yt_pl_worker.isRunning():
                self._yt_pl_worker.cancel()
            self._yt_pl_worker = FetchYTPlaylistsWorker(self)
            self._yt_pl_worker.playlistsLoaded.connect(self._on_cloud_playlists_loaded)
            self._yt_pl_worker.start()
        else:
            fallback_mixes = [
                {
                    "id": "RDTMAK5uy_n_eQ6L28892s923kdkf023",
                    "title": "Discover Mix",
                    "description": "Fresh tracks and new discoveries tailored for you every Wednesday",
                    "track_count": 50,
                    "thumbnail_url": "https://i.ytimg.com/vi/4NRXx6U8ABQ/hqdefault.jpg",
                    "source": "youtube",
                    "is_algorithmic": True,
                    "badge": "DISCOVER"
                }
            ]
            self._on_cloud_mixes_loaded(fallback_mixes)

            fallback_playlists = [
                {
                    "id": "yt_pl1",
                    "title": "Global Top 50 Hits",
                    "description": "Worldwide trending music & chart toppers",
                    "track_count": 12,
                    "thumbnail_url": "https://i.ytimg.com/vi/sPxXiXucYcM/hqdefault.jpg",
                    "source": "youtube",
                    "badge": "TOP 50",
                    "is_playlist": True,
                    "original_url": "https://www.youtube.com/watch?v=sPxXiXucYcM",
                    "tracks": [
                        {"title": "Houdini", "artist": "Dua Lipa", "duration": 186, "original_url": "https://www.youtube.com/watch?v=suAR1PYFNYA", "is_stream": True, "is_online": True},
                        {"title": "Blinding Lights", "artist": "The Weeknd", "duration": 200, "original_url": "https://www.youtube.com/watch?v=4NRXx6U8ABQ", "is_stream": True, "is_online": True},
                        {"title": "Sunflower", "artist": "Post Malone, Swae Lee", "duration": 158, "original_url": "https://www.youtube.com/watch?v=ApXoWvfEYVU", "is_stream": True, "is_online": True},
                        {"title": "Old Town Road", "artist": "Lil Nas X", "duration": 157, "original_url": "https://www.youtube.com/watch?v=w2Ov5jzm3j8", "is_stream": True, "is_online": True},
                        {"title": "As It Was", "artist": "Harry Styles", "duration": 167, "original_url": "https://www.youtube.com/watch?v=H5v3kku4y6Q", "is_stream": True, "is_online": True},
                        {"title": "Birds of a Feather", "artist": "Billie Eilish", "duration": 198, "original_url": "https://www.youtube.com/watch?v=d5gf9dXbPi0", "is_stream": True, "is_online": True},
                        {"title": "Espresso", "artist": "Sabrina Carpenter", "duration": 175, "original_url": "https://www.youtube.com/watch?v=eVli-tstM5E", "is_stream": True, "is_online": True},
                        {"title": "Die With A Smile", "artist": "Lady Gaga, Bruno Mars", "duration": 252, "original_url": "https://www.youtube.com/watch?v=kPa7bsKwL-c", "is_stream": True, "is_online": True},
                        {"title": "Lose Control", "artist": "Teddy Swims", "duration": 211, "original_url": "https://www.youtube.com/watch?v=GZ3zL7kT6_c", "is_stream": True, "is_online": True},
                        {"title": "Beautiful Things", "artist": "Benson Boone", "duration": 180, "original_url": "https://www.youtube.com/watch?v=Oa_RSwwpPaA", "is_stream": True, "is_online": True},
                        {"title": "Cruel Summer", "artist": "Taylor Swift", "duration": 178, "original_url": "https://www.youtube.com/watch?v=ic8j13U_FS8", "is_stream": True, "is_online": True},
                        {"title": "Not Like Us", "artist": "Kendrick Lamar", "duration": 274, "original_url": "https://www.youtube.com/watch?v=H58vbez_m4E", "is_stream": True, "is_online": True}
                    ]
                },
                {
                    "id": "yt_pl2",
                    "title": "Cyberpunk 2077 Night City",
                    "description": "Futuristic electronic & darksynth vibes",
                    "track_count": 11,
                    "thumbnail_url": "https://i.ytimg.com/vi/BnnbP7pCIvQ/hqdefault.jpg",
                    "source": "youtube",
                    "badge": "CYBER",
                    "is_playlist": True,
                    "original_url": "https://www.youtube.com/watch?v=BnnbP7pCIvQ",
                    "tracks": [
                        {"title": "Let You Down", "artist": "Dawid Podsiadło", "duration": 230, "original_url": "https://www.youtube.com/watch?v=BnnbP7pCIvQ", "is_stream": True, "is_online": True},
                        {"title": "I Really Want to Stay at Your House", "artist": "Rosa Walton", "duration": 246, "original_url": "https://www.youtube.com/watch?v=KvMY1uzSC1E", "is_stream": True, "is_online": True},
                        {"title": "Spoiler (Original Mix)", "artist": "Hyper", "duration": 345, "original_url": "https://www.youtube.com/watch?v=9ayYeLLT8Yy", "is_stream": True, "is_online": True},
                        {"title": "Major Crimes", "artist": "Health", "duration": 245, "original_url": "https://www.youtube.com/watch?v=QjHw7b7O3z0", "is_stream": True, "is_online": True},
                        {"title": "Chippin' In", "artist": "SAMURAI (Refused)", "duration": 213, "original_url": "https://www.youtube.com/watch?v=Igq3d6XA75Y", "is_stream": True, "is_online": True},
                        {"title": "Never Fade Away", "artist": "SAMURAI (Refused)", "duration": 190, "original_url": "https://www.youtube.com/watch?v=P4bKxWpG44I", "is_stream": True, "is_online": True},
                        {"title": "The Ballad of Buck Ravers", "artist": "SAMURAI (Refused)", "duration": 267, "original_url": "https://www.youtube.com/watch?v=7gX_mZJgG1U", "is_stream": True, "is_online": True},
                        {"title": "Black Dog", "artist": "SAMURAI (Refused)", "duration": 262, "original_url": "https://www.youtube.com/watch?v=1uN3H6Z0_9s", "is_stream": True, "is_online": True},
                        {"title": "The Rebel Path (Cello Version)", "artist": "P.T. Adamczyk", "duration": 251, "original_url": "https://www.youtube.com/watch?v=5rT_2xT8Nq4", "is_stream": True, "is_online": True},
                        {"title": "Gr4ves", "artist": "Konrad OldMoney", "duration": 170, "original_url": "https://www.youtube.com/watch?v=5L5YJ0x9W9s", "is_stream": True, "is_online": True},
                        {"title": "Violence", "artist": "Le Destroy", "duration": 282, "original_url": "https://www.youtube.com/watch?v=4xDzrJKXOOY", "is_stream": True, "is_online": True}
                    ]
                },
                {
                    "id": "yt_pl3",
                    "title": "Epic Gaming & Boss Themes",
                    "description": "Adrenaline-fueled OSTs & orchestrations",
                    "track_count": 12,
                    "thumbnail_url": "https://i.ytimg.com/vi/r7qovpFAGrQ/hqdefault.jpg",
                    "source": "youtube",
                    "badge": "GAMING",
                    "is_playlist": True,
                    "original_url": "https://www.youtube.com/watch?v=r7qovpFAGrQ",
                    "tracks": [
                        {"title": "The Only Thing They Fear Is You", "artist": "Mick Gordon", "duration": 413, "original_url": "https://www.youtube.com/watch?v=kpnW68QNrLg", "is_stream": True, "is_online": True},
                        {"title": "Bury the Light", "artist": "Casey Edwards", "duration": 582, "original_url": "https://www.youtube.com/watch?v=Jrg9KxGNeJY", "is_stream": True, "is_online": True},
                        {"title": "Rivers in the Desert", "artist": "Shoji Meguro, Lyn", "duration": 315, "original_url": "https://www.youtube.com/watch?v=sdDiHZMms-s", "is_stream": True, "is_online": True},
                        {"title": "BFG Division", "artist": "Mick Gordon", "duration": 506, "original_url": "https://www.youtube.com/watch?v=QHRuTYtSbJQ", "is_stream": True, "is_online": True},
                        {"title": "Rules of Nature", "artist": "Jamie Christopherson", "duration": 150, "original_url": "https://www.youtube.com/watch?v=N3472Q6kvg0", "is_stream": True, "is_online": True},
                        {"title": "Elden Ring Main Theme", "artist": "Tsukasa Saitoh", "duration": 220, "original_url": "https://www.youtube.com/watch?v=r7qovpFAGrQ", "is_stream": True, "is_online": True},
                        {"title": "Devil Trigger", "artist": "Casey Edwards", "duration": 405, "original_url": "https://www.youtube.com/watch?v=YV5IheNfKWB", "is_stream": True, "is_online": True},
                        {"title": "MEGALOVANIA", "artist": "Toby Fox", "duration": 156, "original_url": "https://www.youtube.com/watch?v=wDgQdr8ZkTw", "is_stream": True, "is_online": True},
                        {"title": "Soul of Cinder", "artist": "Yuka Kitamura", "duration": 353, "original_url": "https://www.youtube.com/watch?v=Z9dNrmGD7mU", "is_stream": True, "is_online": True},
                        {"title": "Sogno di Volare", "artist": "Geoff Knorr", "duration": 232, "original_url": "https://www.youtube.com/watch?v=WQYN2P3E06s", "is_stream": True, "is_online": True},
                        {"title": "Baba Yetu", "artist": "Christopher Tin", "duration": 210, "original_url": "https://www.youtube.com/watch?v=IJiHDmyhE1A", "is_stream": True, "is_online": True},
                        {"title": "Halo Theme Mjolnir Mix", "artist": "Martin O'Donnell", "duration": 251, "original_url": "https://www.youtube.com/watch?v=sCxv2daOwjQ", "is_stream": True, "is_online": True}
                    ]
                },
                {
                    "id": "yt_pl4",
                    "title": "Deep Focus / Code Beats",
                    "description": "Ambient, lo-fi & chill electronic",
                    "track_count": 10,
                    "thumbnail_url": "https://i.ytimg.com/vi/f02mOEt11OQ/hqdefault.jpg",
                    "source": "youtube",
                    "badge": "FOCUS",
                    "is_playlist": True,
                    "original_url": "https://www.youtube.com/watch?v=f02mOEt11OQ",
                    "tracks": [
                        {"title": "Synthwave Radio Chill Beats", "artist": "Lofi Girl", "duration": 240, "original_url": "https://www.youtube.com/watch?v=4xDzrJKXOOY", "is_stream": True, "is_online": True},
                        {"title": "Blurred", "artist": "Kiasmos", "duration": 305, "original_url": "https://www.youtube.com/watch?v=as_1_b3v8jA", "is_stream": True, "is_online": True},
                        {"title": "Awake", "artist": "Tycho", "duration": 283, "original_url": "https://www.youtube.com/watch?v=2fRk5nF_n0s", "is_stream": True, "is_online": True},
                        {"title": "Singularity", "artist": "Jon Hopkins", "duration": 389, "original_url": "https://www.youtube.com/watch?v=1H3pA4X-nrU", "is_stream": True, "is_online": True},
                        {"title": "Kerala", "artist": "Bonobo", "duration": 237, "original_url": "https://www.youtube.com/watch?v=S0Q4gqBUs7c", "is_stream": True, "is_online": True},
                        {"title": "Wet Hands", "artist": "C418", "duration": 90, "original_url": "https://www.youtube.com/watch?v=51oxZ3A8Oq4", "is_stream": True, "is_online": True},
                        {"title": "Sol", "artist": "Solar Fields", "duration": 502, "original_url": "https://www.youtube.com/watch?v=f02mOEt11OQ", "is_stream": True, "is_online": True},
                        {"title": "World of Sleepers", "artist": "Carbon Based Lifeforms", "duration": 315, "original_url": "https://www.youtube.com/watch?v=0k50e0Yt9wA", "is_stream": True, "is_online": True},
                        {"title": "Soon It Will Be Cold Enough", "artist": "Emancipator", "duration": 265, "original_url": "https://www.youtube.com/watch?v=xQ4MAGHmMw4", "is_stream": True, "is_online": True},
                        {"title": "Says", "artist": "Nils Frahm", "duration": 518, "original_url": "https://www.youtube.com/watch?v=dIwwjy4slI8", "is_stream": True, "is_online": True}
                    ]
                }
            ]
            self._on_cloud_playlists_loaded(fallback_playlists)

        sp_engine = SpotifyAccountEngine.get_instance()
        if sp_engine.is_authenticated():
            self._sp_recs_worker = FetchSpotifyAlgorithmicFeedsWorker(self)
            self._sp_recs_worker.recommendationsLoaded.connect(self._on_spotify_recs_loaded)
            self._sp_recs_worker.start()

            self._sp_pl_worker = FetchSpotifyPlaylistsWorker(self)
            self._sp_pl_worker.playlistsLoaded.connect(self._on_cloud_playlists_loaded)
            self._sp_pl_worker.start()

    def _show_playlist_detail(self, item_data: dict):
        """Open the full-page Album/Playlist/Mix detail view (Image 1 Style)."""
        self._ensure_playlist_detail_view()
        if self.playlist_detail_view:
            self.playlist_detail_view.set_data(item_data)
            if hasattr(self.playlist_detail_view, 'track_scroll') and self.playlist_detail_view.track_scroll:
                self.playlist_detail_view.track_scroll.verticalScrollBar().setValue(0)
            self.view_stack.setCurrentIndex(3)
            self.search_bar.profile_btn.update_status(is_active_panel=False)

    def _on_cloud_mixes_loaded(self, mixes: list):
        while self.cloud_mixes_layout.count() > 1:
            child = self.cloud_mixes_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for idx, item in enumerate(mixes[:12]):
            accent = "#FF0000" if item.get("source") == "youtube" else "#FF5B06"
            card = CloudMediaCard(item, accent_color=accent, parent=self.mixes_container)
            card.setFixedSize(319, 236)
            card.playClicked.connect(self._show_playlist_detail)
            self.cloud_mixes_layout.insertWidget(idx, card)

            thumb = item.get("thumbnail_url")
            if not thumb:
                from fast_stream_resolver import extract_youtube_video_id
                vid = item.get("seed_video_id") or extract_youtube_video_id(item.get("original_url") or "")
                if vid:
                    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                elif item.get("tracks") and len(item["tracks"]) > 0:
                    thumb = item["tracks"][0].get("thumbnail_url")

            if thumb:
                cached_bytes = None
                try:
                    from ImageCacheEngine import ImageCacheEngine
                    cached_bytes = ImageCacheEngine.get_instance().get_bytes(thumb)
                except Exception:
                    pass

                if cached_bytes:
                    _safe_set_card_pixmap(card, cached_bytes)
                else:
                    loader = AsyncImageLoader(thumb, self)
                    loader.loaded.connect(lambda u, b, c=card: _safe_set_card_pixmap(c, b))
                    loader.finished.connect(lambda l=loader: (self._image_loaders.remove(l) if l in self._image_loaders else None, l.deleteLater()))
                    self._image_loaders.append(loader)
                    loader.start()

    def _on_spotify_recs_loaded(self, recs: list):
        # Dedicated to Spotify Cloud Playlists/Feeds without overriding the 5 signature mixes
        pass

    def _on_cloud_playlists_loaded(self, playlists: list):
        while self.cloud_playlists_layout.count() > 1:
            child = self.cloud_playlists_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not playlists:
            is_yt = YouTubeAccountEngine.get_instance().is_authenticated()
            is_sp = SpotifyAccountEngine.get_instance().is_authenticated()
            if is_yt or is_sp:
                playlists = [{
                    "id": "LM",
                    "title": "Liked Music",
                    "description": "Auto-Playlist • All your liked tracks",
                    "track_count": 50,
                    "thumbnail_url": "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png",
                    "source": "youtube" if is_yt else "spotify",
                    "is_algorithmic": False,
                    "badge": "LIKED"
                }]
            else:
                prompt_card = QFrame(self.playlists_container)
                prompt_card.setObjectName("streamCloudPromptCard")
                prompt_card.setStyleSheet("background: #12141D; border-radius: 8px; padding: 16px;")
                p_layout = QHBoxLayout(prompt_card)
                p_lbl = QLabel("Connect YouTube or Spotify via the top-right profile button to sync your private playlists.", prompt_card)
                p_lbl.setObjectName("streamCloudPromptDesc")
                p_lbl.setStyleSheet("color: #8C90A0; font-size: 11px;")
                p_layout.addWidget(p_lbl)
                p_layout.addStretch()

                link_btn = QPushButton("Link Accounts", prompt_card)
                link_btn.setObjectName("streamCloudPromptLinkBtn")
                link_btn.setCursor(Qt.PointingHandCursor)
                link_btn.setStyleSheet("background: #FF5B06; color: #FFFFFF; font-family: 'Orbitron'; font-size: 9px; font-weight: bold; border-radius: 4px; padding: 4px 12px; border: none;")
                link_btn.clicked.connect(self._toggle_profile_panel)
                p_layout.addWidget(link_btn)
                self.cloud_playlists_layout.insertWidget(0, prompt_card)
                return

        for idx, item in enumerate(playlists[:12]):
            accent = "#1DB954" if item.get("source") == "spotify" else "#FF0000"
            card = CloudMediaCard(item, accent_color=accent, parent=self.playlists_container)
            card.setFixedSize(319, 236)
            card.playClicked.connect(self._show_playlist_detail)
            self.cloud_playlists_layout.insertWidget(idx, card)

            thumb = item.get("thumbnail_url")
            if not thumb:
                from fast_stream_resolver import extract_youtube_video_id
                vid = extract_youtube_video_id(item.get("original_url") or "")
                if vid:
                    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

            if thumb:
                cached_bytes = None
                try:
                    from ImageCacheEngine import ImageCacheEngine
                    cached_bytes = ImageCacheEngine.get_instance().get_bytes(thumb)
                except Exception:
                    pass

                if cached_bytes:
                    _safe_set_card_pixmap(card, cached_bytes)
                else:
                    loader = AsyncImageLoader(thumb, self)
                    loader.loaded.connect(lambda u, b, c=card: _safe_set_card_pixmap(c, b))
                    loader.finished.connect(lambda l=loader: (self._image_loaders.remove(l) if l in self._image_loaders else None, l.deleteLater()))
                    self._image_loaders.append(loader)
                    loader.start()

    def _on_search_query_changed(self, text: str):
        query = text.strip()
        if not query:
            self._debounce_timer.stop()
            if self._search_worker and self._search_worker.isRunning():
                self._search_worker.cancel()
            self._show_home_panel()
            return

        self.search_bar.clear_btn.show()
        self._debounce_timer.start()

    def _exec_debounced_search(self):
        query = self.search_bar.input_edit.text().strip()
        if not query:
            self._show_home_panel()
            return

        self._seq_id += 1
        current_seq = self._seq_id

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait(50)

        for loader in self._image_loaders:
            loader.cancel()
        self._image_loaders.clear()

        self._search_worker = StreamSearchWorker(query, current_seq, parent=self)
        self._search_worker.resultsReady.connect(self._on_search_results_ready)
        self._search_worker.searchFailed.connect(self._on_search_failed)
        self._search_worker.start()

    def _on_search_results_ready(self, seq_id: int, hero_data: dict, candidates: list):
        if seq_id != self._seq_id:
            return

        self.hero_card.set_data(hero_data)
        art_url = hero_data.get('artwork_url')
        if art_url:
            loader = AsyncImageLoader(art_url, self)
            loader.loaded.connect(lambda url, b: self._apply_hero_image(b))
            self._image_loaders.append(loader)
            loader.start()

        valid_cands = [c for c in candidates if isinstance(c, dict) and c.get('id') != hero_data.get('video_id')]
        for idx, card in enumerate(self.candidate_cards):
            if idx < len(valid_cands):
                c_data = valid_cands[idx]
                card.set_data(c_data)
                card.show()
                thumb = c_data.get('thumbnail')
                if thumb:
                    c_loader = AsyncImageLoader(thumb, self)
                    c_loader.loaded.connect(lambda u, b, c=card: _safe_set_card_pixmap(c, b))
                    self._image_loaders.append(c_loader)
                    c_loader.start()
            else:
                card.hide()

        self.view_stack.setCurrentIndex(1)

    def _on_search_failed(self, seq_id: int, err_msg: str):
        if seq_id != self._seq_id:
            return
        self._show_home_panel()

    def _apply_hero_image(self, data_bytes: bytes):
        pix = make_pixmap_from_bytes(data_bytes)
        if pix:
            self.hero_card.set_pixmap(pix)

    def _on_play_track(self, track_data: dict):
        if not track_data:
            return

        # If it is a single track (from playlist detail view, search, or recommendation)
        if track_data.get("is_single_track") or (track_data.get("video_id") and not track_data.get("is_playlist")):
            payload = dict(track_data)
            payload["is_single_track"] = True
            payload["is_playlist"] = False
            self._record_history(payload)
            self._emit_play_stream(payload)
            return

        # If it's a playlist or station that needs resolving into tracks
        if track_data.get("is_playlist") or (not track_data.get("original_url") and not track_data.get("video_id")):
            if track_data.get("tracks"):
                self._record_history(track_data)
                self._emit_play_stream(track_data)
                return

            browse_id = track_data.get("id", "")
            yt_engine = YouTubeAccountEngine.get_instance()
            if yt_engine.is_authenticated():
                tracks = []
                if browse_id in ("LM", "FEmusic_liked_videos", "VLLM"):
                    tracks = yt_engine.fetch_playlist_tracks("FEmusic_liked_videos")
                    if not tracks:
                        tracks = yt_engine.fetch_playlist_tracks("LM")
                elif browse_id:
                    is_radio = track_data.get("is_algorithmic", False) or browse_id == "RDMM" or browse_id.startswith("RD") or browse_id.startswith("RDTMAK5uy_")
                    seed_vid = track_data.get("seed_video_id") or None
                    tracks = yt_engine.fetch_playlist_tracks(browse_id, is_radio=is_radio, video_id=seed_vid)

                if tracks:
                    payload = {
                        "title": track_data.get("title", "YouTube Playlist"),
                        "thumbnail": track_data.get("thumbnail") or track_data.get("thumbnail_url") or "",
                        "thumbnail_url": track_data.get("thumbnail_url") or track_data.get("thumbnail") or "",
                        "is_playlist": True,
                        "tracks": tracks
                    }
                    self._record_history(payload)
                    self._emit_play_stream(payload)
                    return

        self._record_history(track_data)
        self._emit_play_stream(track_data)

    def _on_play_spotify_track(self, track_data: dict):
        title = track_data.get("title", "")
        artist = track_data.get("artist", "")
        clean_query = f"{artist} - {title}" if artist else title
        res = CanonicalSearchEngine.resolve_target(clean_query)
        thumb = track_data.get("thumbnail_url") or track_data.get("thumbnail") or ""
        if res.get("success"):
            play_payload = {
                "title": title,
                "artist": artist,
                "album": track_data.get("album", "Spotify Track"),
                "thumbnail": thumb or res.get("thumbnail_url") or "",
                "thumbnail_url": thumb or res.get("thumbnail_url") or "",
                "duration": track_data.get("duration", res.get("duration", 0)),
                "original_url": res.get("video_url") or f"https://www.youtube.com/watch?v={res.get('video_id')}",
                "resolved_url": res.get("video_url"),
                "stream_url": res.get("stream_url", ""),
                "is_stream": True,
                "is_online": True
            }
            self._on_play_track(play_payload)
        else:
            self._on_play_track(track_data)

    def _on_add_playlist(self, track_data: dict):
        self._record_history(track_data)
        self.addToPlaylistRequested.emit(track_data)

    def _on_save_stream(self, track_data: dict):
        settings = QSettings("TDD131", "HELXAID")
        default_folder = settings.value(
            "MusicSettings/stream_save_folder",
            os.path.join(os.path.expanduser("~/Music"), "Streams"),
            type=str
        )
        self.saveStreamRequested.emit(track_data, default_folder)

    def _on_play_all_featured(self):
        if hasattr(self, 'featured_video_cards') and self.featured_video_cards:
            tracks = []
            for c in self.featured_video_cards:
                if hasattr(c, 'track_data') and c.track_data:
                    tracks.append(c.track_data)
            if tracks:
                payload = {
                    'title': 'Featured Music Videos & Live Stations',
                    'is_playlist': True,
                    'tracks': tracks
                }
                self._emit_play_stream(payload)

    def _apply_featured_card_image(self, card: YTMusicVideoCard, data_bytes: bytes):
        try:
            if card is None:
                return
            _ = card.width()
            pix = make_pixmap_from_bytes(data_bytes)
            if pix:
                card.set_pixmap(pix)
        except (RuntimeError, AttributeError):
            pass

    def _apply_recommendations(self, items: List[Dict[str, Any]]):
        target_count = len(self.featured_video_cards) if hasattr(self, 'featured_video_cards') and self.featured_video_cards else 8
        for idx, item in enumerate(items[:target_count]):
            if idx < len(self.featured_video_cards):
                card = self.featured_video_cards[idx]
                card.set_data(item)
                thumb = item.get('thumbnail_url')
                if thumb:
                    loader = AsyncImageLoader(thumb, self)
                    loader.loaded.connect(lambda u, b, c=card: self._apply_featured_card_image(c, b))
                    self._image_loaders.append(loader)
                    loader.start()

        # Eager prefetch disabled on page load to prevent ~100MB RAM spike from yt-dlp.
        # Tracks resolve on-demand in <150ms when played.
        pass

    def _load_recommendations(self):
        target_count = len(self.featured_video_cards) if hasattr(self, 'featured_video_cards') and self.featured_video_cards else 8
        cached = TasteProfileEngine.load_cached_recommendations()
        if cached and len(cached) == target_count:
            self._apply_recommendations(cached)

        if self._recom_worker and self._recom_worker.isRunning():
            self._recom_worker.cancel()
            self._recom_worker.wait(50)

        self._recom_worker = RecommendationWorker(self)
        self._recom_worker.recommendationsReady.connect(self._apply_recommendations)
        self._recom_worker.start()

    def _load_history(self):
        settings = QSettings("TDD131", "HELXAID")
        hist_str = settings.value("DirectStream/recent_history", "[]", type=str)
        try:
            self._recent_history = json.loads(hist_str)
        except Exception:
            self._recent_history = []
        self._refresh_history_ui()
        self._load_recommendations()

    def _record_history(self, track: dict):
        if not track or not track.get('title'):
            return

        thumb = track.get('thumbnail') or track.get('thumbnail_url') or track.get('artwork_url') or track.get('thumb') or ''
        if not thumb:
            from fast_stream_resolver import extract_youtube_video_id
            vid = extract_youtube_video_id(track.get('original_url') or track.get('resolved_url') or track.get('path') or '')
            if vid:
                thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        if not thumb and track.get('id') in ("LM", "FEmusic_liked_videos"):
            thumb = "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png"

        clean_track = {
            'title': track.get('title'),
            'artist': track.get('artist', 'Unknown Artist'),
            'album': track.get('album', ''),
            'duration': track.get('duration', 0),
            'thumbnail': thumb,
            'thumbnail_url': thumb,
            'original_url': track.get('original_url') or track.get('resolved_url', ''),
            'resolved_url': track.get('resolved_url', ''),
            'id': track.get('id', ''),
            'badge': track.get('badge', ''),
            'is_playlist': track.get('is_playlist', False),
            'source': track.get('source', 'youtube'),
            'is_online': True,
            'is_stream': True
        }
        if track.get('tracks'):
            clean_track['tracks'] = track.get('tracks')

        self._recent_history = [t for t in self._recent_history if t.get('title') != clean_track['title']]
        self._recent_history.insert(0, clean_track)
        self._recent_history = self._recent_history[:12]

        settings = QSettings("TDD131", "HELXAID")
        settings.setValue("DirectStream/recent_history", json.dumps(self._recent_history))
        self._refresh_history_ui()

    def _clear_history(self):
        self._recent_history = []
        settings = QSettings("TDD131", "HELXAID")
        settings.setValue("DirectStream/recent_history", "[]")
        self._refresh_history_ui()

    def _refresh_history_ui(self):
        while self.quick_picks_grid.count():
            child = self.quick_picks_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        default_presets = [
            {"title": "CASANOVA POSSE", "artist": "ALI", "album": "Single", "original_url": "https://www.youtube.com/watch?v=sPxXiXucYcM", "is_online": True, "is_stream": True},
            {"title": "Tabiji (旅路)", "artist": "Fujii Kaze", "album": "HELP EVER HURT NEVER", "original_url": "https://www.youtube.com/watch?v=29p8FvT_puU", "is_online": True, "is_stream": True},
            {"title": "AIZO (愛蔵)", "artist": "King Gnu", "album": "THE GREATEST UNKNOWN", "original_url": "https://www.youtube.com/watch?v=0fxU_XmgvaM", "is_online": True, "is_stream": True},
            {"title": "Voyaging Star's Farewell", "artist": "Wuthering Waves", "album": "OST", "original_url": "https://www.youtube.com/watch?v=0HrdRGuF2Y8", "is_online": True, "is_stream": True},
            {"title": "Yoake no Uta (よあけのうた)", "artist": "jo0ji", "album": "Single", "original_url": "https://www.youtube.com/watch?v=ufcDIOS1HRo", "is_online": True, "is_stream": True},
            {"title": "Bad", "artist": "Michael Jackson", "album": "Bad", "original_url": "https://www.youtube.com/watch?v=zeMywJ-rsWo", "is_online": True, "is_stream": True},
            {"title": "Bubble Pop Electric", "artist": "Gwen Stefani", "album": "L.A.M.B.", "original_url": "https://www.youtube.com/watch?v=xIF0Me8j0dg", "is_online": True, "is_stream": True},
            {"title": "Hatsukoi (はつこい)", "artist": "Nakano Sisters", "album": "5-toubun", "original_url": "https://www.youtube.com/watch?v=VXtBkcvh2Sg", "is_online": True, "is_stream": True},
            {"title": "Charlie's Inferno", "artist": "That Handsome Devil", "album": "A City Dressed in Dynamite", "original_url": "https://www.youtube.com/watch?v=HkSUnEiSVYM", "is_online": True, "is_stream": True},
            {"title": "Brainrot Giga Choir", "artist": "devvey", "album": "Mix", "original_url": "https://www.youtube.com/watch?v=kJBiOVMkCHQ", "is_online": True, "is_stream": True},
            {"title": "It's Not Like I Like You!!", "artist": "Static-P", "album": "Single", "original_url": "https://www.youtube.com/watch?v=gKHsp9iiQvY", "is_online": True, "is_stream": True},
            {"title": "AEAO", "artist": "Dynamicduo & DJ Premier", "album": "A Giant Step", "original_url": "https://www.youtube.com/watch?v=DYz-LjtiVOc", "is_online": True, "is_stream": True},
        ]

        seen_titles = set()
        combined_items: List[Dict[str, Any]] = []

        for track in self._recent_history:
            t = track.get('title')
            if t and t not in seen_titles:
                seen_titles.add(t)
                combined_items.append(track)

        for track in default_presets:
            t = track.get('title')
            if t and t not in seen_titles:
                seen_titles.add(t)
                combined_items.append(track)

        for idx, track in enumerate(combined_items[:12]):
            item_card = YTQuickPickItem(track, self.home_view)
            item_card.playClicked.connect(self._on_play_track)
            item_card.playNextRequested.connect(self._on_play_next)
            item_card.addToQueueRequested.connect(self._on_add_to_queue)
            item_card.downloadRequested.connect(self._on_download_track)
            item_card.addToPlaylistRequested.connect(self._on_add_playlist)
            item_card.searchRequested.connect(self._on_quick_search_requested)
            item_card.notInterestedRequested.connect(self._on_track_dismissed)
            item_card.blockArtistRequested.connect(self._on_artist_blocked)
            row = idx % 4
            col = idx // 4
            self.quick_picks_grid.addWidget(item_card, row, col)

            # Load live YouTube thumbnail for quick pick item
            from fast_stream_resolver import extract_youtube_video_id
            vid = extract_youtube_video_id(track.get('original_url') or track.get('resolved_url') or track.get('path') or '')
            thumb_url = track.get('thumbnail') or track.get('thumbnail_url') or track.get('artwork_url') or track.get('thumb') or ''
            if not thumb_url and vid:
                thumb_url = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            if not thumb_url and track.get('id') in ("LM", "FEmusic_liked_videos"):
                thumb_url = "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png"

            if thumb_url:
                loader = AsyncImageLoader(thumb_url, self)
                loader.loaded.connect(lambda u, b, c=item_card: _safe_set_card_pixmap(c, b))
                loader.finished.connect(lambda l=loader: (self._image_loaders.remove(l) if l in self._image_loaders else None, l.deleteLater()))
                self._image_loaders.append(loader)
                loader.start()

        # Eager prefetch disabled on page load to preserve ~100MB RAM.
        pass

    def _on_play_next(self, track_data: dict):
        self._record_history(track_data)
        self._emit_play_stream(track_data)

    def _on_add_to_queue(self, track_data: dict):
        self._record_history(track_data)
        self.addToPlaylistRequested.emit(track_data)

    def _on_download_track(self, url: str, title: str):
        if hasattr(self, 'downloadRequested'):
            self.downloadRequested.emit(url, title)

    def _on_quick_search_requested(self, query: str):
        self.search_bar.input_edit.setText(query)
        self._on_search_query_changed(query)

    def _on_track_dismissed(self, track_data: dict):
        title = track_data.get('title')
        self._recent_history = [t for t in self._recent_history if t.get('title') != title]
        settings = QSettings("TDD131", "HELXAID")
        settings.setValue("DirectStream/recent_history", json.dumps(self._recent_history))
        self._refresh_history_ui()

    def _on_artist_blocked(self, artist: str):
        self._recent_history = [t for t in self._recent_history if t.get('artist') != artist]
        settings = QSettings("TDD131", "HELXAID")
        settings.setValue("DirectStream/recent_history", json.dumps(self._recent_history))
        self._refresh_history_ui()

    def keyPressEvent(self, event):
        from PySide6.QtWidgets import QApplication, QLineEdit
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit):
            super().keyPressEvent(event)
            return

        key = event.key()
        parent_mp = self.parent()
        while parent_mp:
            if hasattr(parent_mp, '_toggle_play'):
                if key == Qt.Key_Space:
                    parent_mp._toggle_play()
                    event.accept()
                    return
                elif key == Qt.Key_N:
                    parent_mp._next_track(force_wrap=True)
                    event.accept()
                    return
                elif key == Qt.Key_P:
                    parent_mp._prev_track(force_wrap=True)
                    event.accept()
                    return
            parent_mp = parent_mp.parent()

        super().keyPressEvent(event)
