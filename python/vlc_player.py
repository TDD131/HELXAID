"""
VLC Player Wrapper for Qt Integration

Provides a VLC-based video player with:
- Hardware decoding (D3D11VA/DXVA2)
- Audio pitch correction at playback speed changes
- All codec support
- Qt widget integration

Requirements:
    pip install python-vlc

Note: VLC must be installed separately (libVLC.dll required)
"""

import os
import sys
import logging
from typing import Optional, Callable, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# VLC availability check
_VLC_AVAILABLE = False
_vlc_module = None

try:
    import vlc
    _VLC_AVAILABLE = True
    _vlc_module = vlc
except ImportError:
    logger.warning("python-vlc not installed. VLC player not available.")
except OSError as e:
    logger.warning(f"VLC library not found: {e}")


class VLCPlayerState:
    """VLC player states matching Qt MediaPlayer states."""
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2
    BUFFERING = 3
    ERROR = 4
    LOADING = 5


class VLCPlayer:
    """
    VLC Media Player Wrapper.
    
    Provides a Pythonic interface to libVLC with:
    - Hardware decoding configuration
    - Audio pitch correction at speed changes
    - Qt integration helpers
    
    Example:
        player = VLCPlayer()
        player.set_hardware_decoding(True)
        player.set_file("video.mp4")
        player.play()
        player.set_playback_rate(2.0)  # 2x speed with pitch correction
    """
    
    def __init__(self, hardware_decoding: bool = True):
        """
        Initialize VLC player.
        
        Args:
            hardware_decoding: Enable hardware decoding (D3D11VA/DXVA2)
        """
        self._instance: Optional[vlc.Instance] = None
        self._player: Optional[vlc.MediaPlayer] = None
        self._media: Optional[vlc.Media] = None
        self._state = VLCPlayerState.STOPPED
        self._duration = 0
        self._position = 0
        self._volume = 100
        self._playback_rate = 1.0
        self._hardware_decoding = hardware_decoding
        self._file_path: Optional[str] = None
        
        # Callbacks
        self._on_state_changed: Optional[Callable[[int], None]] = None
        self._on_position_changed: Optional[Callable[[float], None]] = None
        self._on_duration_changed: Optional[Callable[[int], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._on_end_reached: Optional[Callable[[], None]] = None
        
        # Initialize VLC
        self._init_vlc()
    
    def _init_vlc(self):
        """Initialize VLC instance with optimal settings."""
        if not _VLC_AVAILABLE:
            return
        
        try:
            # VLC arguments for hardware decoding and optimal playback
            vlc_args = [
                # Hardware decoding
                '--avcodec-hw=d3d11va,dxva2',
                
                # Audio pitch correction at speed changes (time-stretch)
                '--audio-time-stretch',
                
                # Disable VLC's internal logging (we handle our own)
                '--no-video-title-show',
                '--no-stats',
                '--no-osd',
                
                # Network caching for smooth streaming
                '--network-caching=1000',
                
                # File caching
                '--file-caching=1000',
                
                # Live media caching
                '--live-caching=1000',
                
                # Disable hardware decoding if requested
                '--no-avcodec-hw' if not self._hardware_decoding else '',
            ]
            
            # Filter empty strings
            vlc_args = [arg for arg in vlc_args if arg]
            
            # Create VLC instance
            self._instance = vlc.Instance(' '.join(vlc_args))
            
            if self._instance:
                self._player = self._instance.media_player_new()
                self._setup_event_handlers()
                logger.info("[VLC] Initialized with hardware decoding enabled")
            else:
                logger.error("[VLC] Failed to create VLC instance")
                
        except Exception as e:
            logger.error(f"[VLC] Initialization failed: {e}")
    
    def _setup_event_handlers(self):
        """Set up VLC event handlers."""
        if not self._player:
            return
        
        try:
            event_manager = self._player.event_manager()
            
            # State changes
            event_manager.event_attach(
                vlc.EventType.MediaPlayerStateChanged,
                self._on_vlc_state_changed
            )
            
            # Position changes
            event_manager.event_attach(
                vlc.EventType.MediaPlayerPositionChanged,
                self._on_vlc_position_changed
            )
            
            # End reached
            event_manager.event_attach(
                vlc.EventType.MediaPlayerEndReached,
                self._on_vlc_end_reached
            )
            
            # Errors
            event_manager.event_attach(
                vlc.EventType.MediaPlayerEncounteredError,
                self._on_vlc_error
            )
            
            # Length/duration changes
            event_manager.event_attach(
                vlc.EventType.MediaPlayerLengthChanged,
                self._on_vlc_length_changed
            )
            
        except Exception as e:
            logger.error(f"[VLC] Event handler setup failed: {e}")
    
    def _on_vlc_state_changed(self, event):
        """Handle VLC state changes."""
        vlc_state = event.u.new_state
        
        state_map = {
            vlc.State.NothingSpecial: VLCPlayerState.STOPPED,
            vlc.State.Opening: VLCPlayerState.LOADING,
            vlc.State.Buffering: VLCPlayerState.BUFFERING,
            vlc.State.Playing: VLCPlayerState.PLAYING,
            vlc.State.Paused: VLCPlayerState.PAUSED,
            vlc.State.Stopped: VLCPlayerState.STOPPED,
            vlc.State.Ended: VLCPlayerState.STOPPED,
            vlc.State.Error: VLCPlayerState.ERROR,
        }
        
        self._state = state_map.get(vlc_state, VLCPlayerState.STOPPED)
        
        if self._on_state_changed:
            self._on_state_changed(self._state)
    
    def _on_vlc_position_changed(self, event):
        """Handle position changes."""
        self._position = event.u.new_position
        
        if self._on_position_changed:
            self._on_position_changed(self._position)
    
    def _on_vlc_end_reached(self, event):
        """Handle end of media."""
        self._state = VLCPlayerState.STOPPED
        
        if self._on_end_reached:
            self._on_end_reached()
    
    def _on_vlc_error(self, event):
        """Handle VLC errors."""
        self._state = VLCPlayerState.ERROR
        
        if self._on_error:
            self._on_error("VLC playback error")
    
    def _on_vlc_length_changed(self, event):
        """Handle duration changes."""
        self._duration = event.u.new_length
        
        if self._on_duration_changed:
            self._on_duration_changed(self._duration)
    
    def set_hardware_decoding(self, enabled: bool):
        """
        Enable or disable hardware decoding.
        
        Note: This requires reinitializing the player.
        
        Args:
            enabled: True for hardware decoding (D3D11VA/DXVA2)
        """
        if enabled != self._hardware_decoding:
            self._hardware_decoding = enabled
            # Reinitialize VLC with new settings
            self._init_vlc()
    
    def set_file(self, file_path: str) -> bool:
        """
        Set the media file to play.
        
        Args:
            file_path: Path to media file
            
        Returns:
            True if file loaded successfully
        """
        if not self._instance or not self._player:
            logger.error("[VLC] Player not initialized")
            return False
        
        if not os.path.exists(file_path):
            logger.error(f"[VLC] File not found: {file_path}")
            return False
        
        try:
            # Create media
            self._media = self._instance.media_new(file_path)
            self._player.set_media(self._media)
            self._file_path = file_path
            
            logger.info(f"[VLC] Loaded: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[VLC] Failed to load file: {e}")
            return False
    
    def set_mrl(self, mrl: str) -> bool:
        """
        Set media by MRL (Media Resource Locator).
        
        Supports URLs, device paths, etc.
        
        Args:
            mrl: Media Resource Locator string
            
        Returns:
            True if media loaded successfully
        """
        if not self._instance or not self._player:
            return False
        
        try:
            self._media = self._instance.media_new(mrl)
            self._player.set_media(self._media)
            self._file_path = mrl
            return True
        except Exception as e:
            logger.error(f"[VLC] Failed to load MRL: {e}")
            return False
    
    def play(self) -> bool:
        """
        Start or resume playback.
        
        Returns:
            True if playback started successfully
        """
        if not self._player:
            return False
        
        result = self._player.play()
        return result == 0
    
    def pause(self):
        """Pause playback."""
        if self._player:
            self._player.pause()
    
    def stop(self):
        """Stop playback."""
        if self._player:
            self._player.stop()
    
    def toggle_pause(self):
        """Toggle between play and pause."""
        if self._player:
            self._player.pause()
    
    def set_position(self, position: float):
        """
        Set playback position (0.0 to 1.0).
        
        Args:
            position: Position as fraction of total duration
        """
        if self._player:
            self._player.set_position(max(0.0, min(1.0, position)))
    
    def set_time(self, time_ms: int):
        """
        Set playback time in milliseconds.
        
        Args:
            time_ms: Time in milliseconds
        """
        if self._player:
            self._player.set_time(time_ms)
    
    def get_time(self) -> int:
        """
        Get current playback time in milliseconds.
        
        Returns:
            Current time in milliseconds
        """
        if self._player:
            return self._player.get_time()
        return 0
    
    def get_duration(self) -> int:
        """
        Get total duration in milliseconds.
        
        Returns:
            Duration in milliseconds
        """
        if self._player:
            return self._player.get_length()
        return 0
    
    def set_volume(self, volume: int):
        """
        Set volume level.
        
        Args:
            volume: Volume level (0-100, can exceed 100 for amplification)
        """
        if self._player:
            self._player.audio_set_volume(volume)
            self._volume = volume
    
    def get_volume(self) -> int:
        """
        Get current volume level.
        
        Returns:
            Volume level (0-100+)
        """
        if self._player:
            return self._player.audio_get_volume()
        return self._volume
    
    def set_mute(self, mute: bool):
        """
        Set mute state.
        
        Args:
            mute: True to mute, False to unmute
        """
        if self._player:
            self._player.audio_set_mute(mute)
    
    def is_muted(self) -> bool:
        """
        Check if audio is muted.
        
        Returns:
            True if muted
        """
        if self._player:
            return self._player.audio_get_mute()
        return False
    
    def set_playback_rate(self, rate: float) -> bool:
        """
        Set playback rate with audio pitch correction.
        
        VLC's --audio-time-stretch option preserves pitch at different speeds.
        
        Args:
            rate: Playback rate (0.25 to 4.0 typically supported)
            
        Returns:
            True if rate was set successfully
        """
        if not self._player:
            return False
        
        try:
            # VLC uses float for playback rate
            result = self._player.set_rate(rate)
            if result == 0:
                self._playback_rate = rate
                logger.debug(f"[VLC] Playback rate set to {rate}x")
                return True
            return False
        except Exception as e:
            logger.error(f"[VLC] Failed to set playback rate: {e}")
            return False
    
    def get_playback_rate(self) -> float:
        """
        Get current playback rate.
        
        Returns:
            Current playback rate
        """
        if self._player:
            return self._player.get_rate()
        return self._playback_rate
    
    def get_state(self) -> int:
        """
        Get current player state.
        
        Returns:
            VLCPlayerState constant
        """
        return self._state
    
    def is_playing(self) -> bool:
        """
        Check if currently playing.
        
        Returns:
            True if playing
        """
        if self._player:
            return self._player.is_playing()
        return False
    
    def get_fps(self) -> float:
        """
        Get video frame rate.
        
        Returns:
            Frames per second
        """
        if self._player:
            return self._player.get_fps() or 0.0
        return 0.0
    
    def get_video_size(self) -> Tuple[int, int]:
        """
        Get video dimensions.
        
        Returns:
            Tuple of (width, height)
        """
        if self._player:
            # VLC returns (width, height) tuple
            return self._player.video_get_size()
        return (0, 0)
    
    def set_video_callbacks(self, lock, unlock, display, data=None):
        """
        Set video callbacks for custom rendering.
        
        Used for OpenGL/D3D integration.
        
        Args:
            lock: Callback to lock video memory
            unlock: Callback to unlock video memory
            display: Callback to display frame
            data: User data passed to callbacks
        """
        if self._player:
            self._player.video_set_callbacks(lock, unlock, display, data)
    
    def set_video_format(self, chroma: str, width: int, height: int, pitch: int):
        """
        Set video output format.
        
        Args:
            chroma: FourCC chroma format (e.g., 'RV32', 'RGBA')
            width: Video width
            height: Video height
            pitch: Bytes per line
        """
        if self._player:
            self._player.video_set_format(chroma, width, height, pitch)
    
    def set_window(self, window_id):
        """
        Set the window handle for video output.
        
        Args:
            window_id: Platform-specific window handle (HWND on Windows)
        """
        if self._player:
            if sys.platform == 'win32':
                self._player.set_hwnd(window_id)
            elif sys.platform == 'linux':
                self._player.set_xwindow(window_id)
            elif sys.platform == 'darwin':
                self._player.set_nsobject(window_id)
    
    def take_snapshot(self, file_path: str, width: int = 0, height: int = 0) -> bool:
        """
        Take a snapshot of the current video frame.
        
        Args:
            file_path: Path to save snapshot
            width: Snapshot width (0 for video width)
            height: Snapshot height (0 for video height)
            
        Returns:
            True if snapshot was taken successfully
        """
        if self._player:
            result = self._player.video_take_snapshot(0, file_path, width, height)
            return result == 0
        return False
    
    def set_callbacks(
        self,
        on_state_changed: Callable[[int], None] = None,
        on_position_changed: Callable[[float], None] = None,
        on_duration_changed: Callable[[int], None] = None,
        on_error: Callable[[str], None] = None,
        on_end_reached: Callable[[], None] = None
    ):
        """
        Set callback functions for player events.
        
        Args:
            on_state_changed: Called when player state changes
            on_position_changed: Called when playback position changes
            on_duration_changed: Called when duration is known
            on_error: Called when an error occurs
            on_end_reached: Called when playback reaches end
        """
        self._on_state_changed = on_state_changed
        self._on_position_changed = on_position_changed
        self._on_duration_changed = on_duration_changed
        self._on_error = on_error
        self._on_end_reached = on_end_reached
    
    def add_subtitle(self, subtitle_path: str, select: bool = True) -> bool:
        """
        Add a subtitle file.
        
        Args:
            subtitle_path: Path to subtitle file
            select: Whether to select this subtitle track
            
        Returns:
            True if subtitle was added successfully
        """
        if not self._player:
            return False
        
        try:
            self._player.add_slave(vlc.MediaSlave.subtitle, subtitle_path, select)
            return True
        except Exception as e:
            logger.error(f"[VLC] Failed to add subtitle: {e}")
            return False
    
    def set_subtitle_track(self, track_id: int):
        """
        Set the active subtitle track.
        
        Args:
            track_id: Track ID (from video_get_spu_description)
        """
        if self._player:
            self._player.video_set_spu(track_id)
    
    def get_subtitle_tracks(self) -> List[Tuple[int, str]]:
        """
        Get available subtitle tracks.
        
        Returns:
            List of (track_id, track_name) tuples
        """
        if not self._player:
            return []
        
        tracks = []
        try:
            # Get track descriptions
            description = self._player.video_get_spu_description()
            if description:
                for track in description:
                    tracks.append((track[0], track[1]))
        except Exception:
            pass
        
        return tracks
    
    def set_audio_track(self, track_id: int):
        """
        Set the active audio track.
        
        Args:
            track_id: Track ID
        """
        if self._player:
            self._player.audio_set_track(track_id)
    
    def get_audio_tracks(self) -> List[Tuple[int, str]]:
        """
        Get available audio tracks.
        
        Returns:
            List of (track_id, track_name) tuples
        """
        if not self._player:
            return []
        
        tracks = []
        try:
            description = self._player.audio_get_track_description()
            if description:
                for track in description:
                    tracks.append((track[0], track[1]))
        except Exception:
            pass
        
        return tracks
    
    def cleanup(self):
        """Clean up VLC resources."""
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None
        
        if self._media:
            self._media.release()
            self._media = None
        
        # Note: Don't release instance as it may be shared
        self._instance = None
    
    def __del__(self):
        """Destructor - cleanup VLC resources."""
        self.cleanup()


def is_vlc_available() -> bool:
    """
    Check if VLC is available.
    
    Returns:
        True if VLC is installed and python-vlc is available
    """
    return _VLC_AVAILABLE


def get_vlc_version() -> str:
    """
    Get VLC version string.
    
    Returns:
        Version string or "N/A" if not available
    """
    if _VLC_AVAILABLE:
        try:
            return vlc.libvlc_get_version().decode('utf-8')
        except Exception:
            return "Unknown"
    return "N/A"


# Module info
__all__ = [
    'VLCPlayer',
    'VLCPlayerState',
    'is_vlc_available',
    'get_vlc_version',
]
