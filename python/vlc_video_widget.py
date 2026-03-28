"""
VLC Video Widget for Qt Integration

Provides a QWidget that embeds VLC video output.
Supports hardware rendering and proper overlay handling.
"""

import os
import sys
import logging
from typing import Optional, Callable

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from PySide6.QtGui import QPaintEvent, QResizeEvent

logger = logging.getLogger(__name__)

# Check VLC availability
try:
    import vlc
    _VLC_AVAILABLE = True
except ImportError:
    _VLC_AVAILABLE = False


class VLCVideoWidget(QWidget):
    """
    Qt Widget for VLC video output.
    
    Embeds VLC's video output into a QWidget using platform-specific
    window handle embedding (HWND on Windows).
    
    Features:
    - Hardware rendering support
    - Automatic resize handling
    - Proper focus and event handling
    
    Example:
        player = VLCPlayer()
        video_widget = VLCVideoWidget()
        player.set_window(video_widget.winId())
        player.set_file("video.mp4")
        player.play()
    """
    
    # Signals
    clicked = Signal()
    doubleClicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize VLC video widget.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Widget properties
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        
        # Size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(1, 1)
        
        # Enable mouse tracking for hover events
        self.setMouseTracking(True)
        
        # Focus policy for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Background color (black for video)
        self.setStyleSheet("background-color: black;")
        
        # Player reference (set externally)
        self._player = None
        
        # Resize timer (debounce resize events)
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        
        logger.debug("[VLCWidget] Initialized")
    
    def set_player(self, player):
        """
        Set the VLC player instance.
        
        This automatically connects the player to this widget's window.
        
        Args:
            player: VLCPlayer instance
        """
        self._player = player
        
        if player and _VLC_AVAILABLE:
            # Set window handle for video output
            win_id = int(self.winId())
            
            if sys.platform == 'win32':
                player._player.set_hwnd(win_id)
            elif sys.platform == 'linux':
                player._player.set_xwindow(win_id)
            elif sys.platform == 'darwin':
                player._player.set_nsobject(win_id)
            
            logger.debug(f"[VLCWidget] Connected player to window {win_id}")
    
    def winId(self):
        """
        Get the window ID for VLC embedding.
        
        Overrides to ensure we get a valid native window handle.
        
        Returns:
            Platform-specific window handle
        """
        # Ensure we have a native window
        if not self.testAttribute(Qt.WA_NativeWindow):
            self.setAttribute(Qt.WA_NativeWindow, True)
        
        return super().winId()
    
    def paintEvent(self, event: QPaintEvent):
        """
        Handle paint events.
        
        VLC handles its own painting, so we just ensure
        the widget background is black.
        """
        # VLC paints directly to the window, so we don't paint anything
        # Just ensure the background is black if no video is playing
        pass
    
    def resizeEvent(self, event: QResizeEvent):
        """
        Handle resize events.
        
        Debounces resize events to avoid excessive VLC updates.
        """
        super().resizeEvent(event)
        
        # Debounce resize events
        self._resize_timer.start(50)
    
    def _on_resize_timeout(self):
        """Handle debounced resize."""
        if self._player and hasattr(self._player, '_player') and self._player._player:
            # Notify VLC of size change
            # On Windows, VLC automatically handles resize via HWND
            pass
    
    def mousePressEvent(self, event):
        """Handle mouse press events."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle mouse double-click events."""
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
    
    def event(self, event: QEvent):
        """Handle all events."""
        # Ensure we have a native window for VLC
        if event.type() == QEvent.WinIdChange:
            # Window ID changed, need to re-attach VLC
            if self._player and hasattr(self._player, '_player') and self._player._player:
                win_id = int(self.winId())
                if sys.platform == 'win32':
                    self._player._player.set_hwnd(win_id)
        
        return super().event(event)
    
    def showEvent(self, event):
        """Handle show events."""
        super().showEvent(event)
        
        # Re-attach VLC player when widget is shown
        if self._player and hasattr(self._player, '_player') and self._player._player:
            win_id = int(self.winId())
            if sys.platform == 'win32':
                self._player._player.set_hwnd(win_id)
    
    def clear(self):
        """Clear the video display."""
        # Force a repaint with black background
        self.update()


class VLCVideoContainer(QWidget):
    """
    Container widget for VLC video with controls layout.
    
    Provides a complete video container with:
    - VLC video widget
    - Proper layout management
    - Aspect ratio handling
    
    Example:
        container = VLCVideoContainer()
        container.set_player(vlc_player)
        layout.addWidget(container)
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize VLC video container.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        
        # Video widget
        self._video_widget = VLCVideoWidget(self)
        self._layout.addWidget(self._video_widget)
        
        # Player reference
        self._player = None
        
        # Aspect ratio (0 = auto)
        self._aspect_ratio = 0.0
    
    def set_player(self, player):
        """
        Set the VLC player instance.
        
        Args:
            player: VLCPlayer instance
        """
        self._player = player
        self._video_widget.set_player(player)
    
    def video_widget(self) -> VLCVideoWidget:
        """
        Get the video widget.
        
        Returns:
            VLCVideoWidget instance
        """
        return self._video_widget
    
    def set_aspect_ratio(self, ratio: float):
        """
        Set video aspect ratio.
        
        Args:
            ratio: Aspect ratio (width/height), 0 for auto
        """
        self._aspect_ratio = ratio
        
        if self._player and hasattr(self._player, '_player') and self._player._player:
            # VLC aspect ratio format: "width:height" or "" for auto
            if ratio > 0:
                # Calculate ratio string
                ar_str = f"{ratio:.4f}:1"
                self._player._player.video_set_aspect_ratio(ar_str)
            else:
                self._player._player.video_set_aspect_ratio("")
    
    def clear(self):
        """Clear the video display."""
        self._video_widget.clear()


# Module exports
__all__ = ['VLCVideoWidget', 'VLCVideoContainer']
