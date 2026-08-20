"""
Windows System Media Transport Controls (SMTC) Service for HELXAIC

Provides native Windows 10/11 SMTC integration to support:
- Bluetooth AVRCP media controls (TWS earbuds, wireless headphones, headsets, smartwatches)
- Windows Lock Screen playback controls
- Windows Volume flyout (overlay) with media metadata (track title, artist, album art)
- Background & minimized media control without requiring window focus

Component Name: WindowsSMTCService
"""

import os
import time
from PySide6.QtCore import QObject, Signal


class WindowsSMTCService(QObject):
    """
    Windows 10/11 System Media Transport Controls (SMTC) Service.
    
    Bridges HELXAIC playback engine with the Windows Media Subsystem via WinRT.
    Dispatches media button press events across thread boundaries to PySide6
    via automatically queued Qt signals.
    
    Component Name: WindowsSMTCService
    """

    # Signals emitted when Windows OS / Bluetooth sends a media control request.
    # Safe to connect directly to PySide6 GUI slots.
    play_requested = Signal()
    pause_requested = Signal()
    toggle_play_requested = Signal()
    next_requested = Signal()
    prev_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("windowsSMTCService")
        self.is_available = False
        self._player = None
        self._smtc = None
        self._token = None
        self._last_action_time = 0.0
        self._debounce_gap = 0.25  # 250ms cooldown to prevent double-tap jitter
        self._current_title = ""
        self._current_artist = ""
        self._current_album = ""
        self._current_thumb = ""
        self._is_playing = False

        self._init_smtc()

    def _init_smtc(self):
        """Initialize WinRT MediaPlayer and SystemMediaTransportControls."""
        try:
            import winrt.windows.media as wm
            import winrt.windows.media.playback as wmp
            import winrt.windows.foundation as wf

            # Use MediaPlayer's native SMTC handle
            self._player = wmp.MediaPlayer()
            # Disable default media player command manager so we receive raw SMTC events directly
            self._player.command_manager.is_enabled = False
            
            self._smtc = self._player.system_media_transport_controls
            self._smtc.is_enabled = True
            self._smtc.is_play_enabled = True
            self._smtc.is_pause_enabled = True
            self._smtc.is_next_enabled = True
            self._smtc.is_previous_enabled = True
            self._smtc.is_stop_enabled = True
            self._smtc.playback_status = wm.MediaPlaybackStatus.STOPPED

            # Register button pressed event listener
            self._token = self._smtc.add_button_pressed(self._on_button_pressed)
            self.is_available = True
            print("[SMTC] Windows System Media Transport Controls initialized successfully (Bluetooth AVRCP ready)")
        except ImportError as e:
            self.is_available = False
            print(f"[SMTC] WinRT packages not available: {e}. Falling back to low-level keyboard hook.")
        except Exception as e:
            self.is_available = False
            print(f"[SMTC] Failed to initialize Windows SMTC: {e}. Falling back to low-level keyboard hook.")

    def _on_button_pressed(self, sender, args):
        """
        Callback invoked by Windows Media Subsystem when an AVRCP or SMTC button is pressed.
        Runs in a Windows threadpool background thread. Emits Qt signals safely.
        """
        try:
            import winrt.windows.media as wm
            btn = args.button

            # Monotonic debounce check (250ms) to prevent double-fire
            now = time.monotonic()
            if now - self._last_action_time < self._debounce_gap:
                return
            self._last_action_time = now

            if btn == wm.SystemMediaTransportControlsButton.PLAY:
                print("[SMTC] Event: PLAY requested")
                self.play_requested.emit()
            elif btn == wm.SystemMediaTransportControlsButton.PAUSE:
                print("[SMTC] Event: PAUSE requested")
                self.pause_requested.emit()
            elif btn == wm.SystemMediaTransportControlsButton.NEXT:
                print("[SMTC] Event: NEXT requested")
                self.next_requested.emit()
            elif btn == wm.SystemMediaTransportControlsButton.PREVIOUS:
                print("[SMTC] Event: PREVIOUS requested")
                self.prev_requested.emit()
            elif btn == wm.SystemMediaTransportControlsButton.STOP:
                print("[SMTC] Event: STOP requested")
                self.stop_requested.emit()
        except Exception as e:
            print(f"[SMTC] Error processing button event: {e}")

    def update_metadata(self, title="Unknown Track", artist="HELXAIC", album="", thumbnail_path=None):
        """
        Update the track metadata displayed in the Windows Volume Flyout and Lock Screen.
        
        Args:
            title: Song title string.
            artist: Artist / Creator name string.
            album: Album title string.
            thumbnail_path: Optional absolute file path to the album art image.
        """
        if not self.is_available or not self._smtc:
            return

        try:
            import winrt.windows.media as wm
            import winrt.windows.foundation as wf
            import winrt.windows.storage.streams as wss

            self._current_title = str(title or "Unknown Track")
            self._current_artist = str(artist or "HELXAIC")
            self._current_album = str(album or "")

            updater = self._smtc.display_updater
            updater.type = wm.MediaPlaybackType.MUSIC
            updater.music_properties.title = self._current_title
            updater.music_properties.artist = self._current_artist
            updater.music_properties.album_artist = self._current_artist
            if self._current_album:
                updater.music_properties.album_title = self._current_album

            # Set album art thumbnail if valid file path provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    norm_path = os.path.abspath(thumbnail_path).replace("\\", "/")
                    uri = wf.Uri(f"file:///{norm_path}")
                    updater.thumbnail = wss.RandomAccessStreamReference.create_from_uri(uri)
                    self._current_thumb = norm_path
                except Exception as thumb_err:
                    print(f"[SMTC] Could not attach thumbnail: {thumb_err}")

            updater.update()
        except Exception as e:
            print(f"[SMTC] Failed to update metadata: {e}")

    def set_playback_status(self, is_playing: bool, is_stopped: bool = False):
        """
        Update Windows SMTC playback state (Playing, Paused, Stopped).
        
        Args:
            is_playing: True if currently playing audio/video.
            is_stopped: True if playback is fully stopped.
        """
        if not self.is_available or not self._smtc:
            return

        try:
            import winrt.windows.media as wm
            self._is_playing = is_playing and not is_stopped

            if is_stopped:
                self._smtc.playback_status = wm.MediaPlaybackStatus.STOPPED
            elif is_playing:
                self._smtc.playback_status = wm.MediaPlaybackStatus.PLAYING
            else:
                self._smtc.playback_status = wm.MediaPlaybackStatus.PAUSED
        except Exception as e:
            print(f"[SMTC] Failed to update playback status: {e}")

    def cleanup(self):
        """Unregister event listener tokens and disable SMTC on application shutdown."""
        if not self.is_available:
            return

        try:
            if self._smtc and self._token:
                self._smtc.remove_button_pressed(self._token)
                self._smtc.is_enabled = False
                self._token = None
        except Exception as e:
            print(f"[SMTC] Cleanup error: {e}")
        finally:
            self._player = None
            self._smtc = None
            self.is_available = False
            print("[SMTC] Windows SMTC service stopped cleanly.")
