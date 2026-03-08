"""
Discord Rich Presence integration for HELXAID Music Player.

Shows current playing track in Discord status.

Component Name: DiscordPresence
"""

import time
import threading
from typing import Optional

# Discord RPC library (pypresence)
try:
    from pypresence import Presence, InvalidID, DiscordNotFound
    DISCORD_RPC_AVAILABLE = True
except ImportError:
    DISCORD_RPC_AVAILABLE = False
    print("[Discord] pypresence not installed. Run: pip install pypresence")


class DiscordPresence:
    """
    Discord Rich Presence manager for music player.
    
    Usage:
        discord = DiscordPresence()
        discord.connect()
        discord.update("Song Title", "Artist Name")
        discord.clear()
        discord.disconnect()
    """
    
    # Discord Application ID - Create your own at https://discord.com/developers/applications
    # This is a placeholder - you should create your own app for production
    CLIENT_ID = "1320772842135539844"  # HELXAID Music Player App ID
    
    def __init__(self):
        self._rpc: Optional[Presence] = None
        self._connected = False
        self._enabled = True
        self._current_track = None
        self._start_time = None
        
    @property
    def is_available(self) -> bool:
        """Check if Discord RPC library is available."""
        return DISCORD_RPC_AVAILABLE
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Discord."""
        return self._connected
    
    @property
    def enabled(self) -> bool:
        """Check if Discord presence is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        """Enable or disable Discord presence."""
        self._enabled = value
        if not value and self._connected:
            self.clear()
    
    def connect(self) -> bool:
        """Connect to Discord RPC."""
        if not DISCORD_RPC_AVAILABLE:
            print("[Discord] pypresence library not available")
            return False
        
        if self._connected:
            return True
        
        try:
            self._rpc = Presence(self.CLIENT_ID)
            self._rpc.connect()
            self._connected = True
            print("[Discord] Connected to Discord RPC")
            return True
        except DiscordNotFound:
            print("[Discord] Discord is not running")
            return False
        except InvalidID:
            print("[Discord] Invalid Discord Application ID")
            return False
        except Exception as e:
            print(f"[Discord] Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Discord RPC."""
        if self._rpc and self._connected:
            try:
                self._rpc.close()
            except Exception:
                pass
            self._connected = False
            print("[Discord] Disconnected from Discord RPC")
    
    def update(self, title: str, artist: str = "", album: str = "", 
               duration: float = 0, position: float = 0, is_playing: bool = True):
        """
        Update Discord presence with current track info.
        
        Args:
            title: Track title
            artist: Artist name
            album: Album name
            duration: Total duration in seconds
            position: Current position in seconds
            is_playing: Whether track is playing or paused
        """
        if not self._enabled or not self._connected:
            return
        
        if not self._rpc:
            return
        
        try:
            # Build details and state
            details = title[:128] if title else "Unknown Track"
            state = artist[:128] if artist else None
            
            # Activity buttons (optional)
            # buttons = [{"label": "Open HELXAID", "url": "https://helxaid.com"}]
            
            # Timestamps for progress
            if duration > 0 and is_playing:
                now = time.time()
                end_time = now + (duration - position)
                timestamps = {"end": int(end_time)}
            else:
                timestamps = None
            
            # Large image (album art placeholder or app icon)
            large_image = "helxaid_logo"  # Must be uploaded to Discord Developer Portal
            large_text = album if album else "HELXAID Music Player"
            
            # Small image for play/pause state
            small_image = "playing" if is_playing else "paused"
            small_text = "Playing" if is_playing else "Paused"
            
            self._rpc.update(
                details=details,
                state=state,
                start=int(self._start_time) if self._start_time and is_playing else None,
                end=timestamps.get("end") if timestamps else None,
                large_image=large_image,
                large_text=large_text,
                small_image=small_image,
                small_text=small_text
            )
            
            self._current_track = title
            
        except Exception as e:
            print(f"[Discord] Update error: {e}")
    
    def set_playing(self, title: str, artist: str = ""):
        """Set track as now playing (resets start time)."""
        self._start_time = time.time()
        self.update(title, artist, is_playing=True)
    
    def set_paused(self, title: str = "", artist: str = ""):
        """Set track as paused."""
        title = title or self._current_track or "Paused"
        self.update(title, artist, is_playing=False)
    
    def clear(self):
        """Clear Discord presence."""
        if self._rpc and self._connected:
            try:
                self._rpc.clear()
                self._current_track = None
                self._start_time = None
            except Exception:
                pass


# Global instance (lazy initialization)
_discord: Optional[DiscordPresence] = None


def get_discord() -> DiscordPresence:
    """Get the global Discord presence instance."""
    global _discord
    if _discord is None:
        _discord = DiscordPresence()
    return _discord


def connect_discord() -> bool:
    """Connect to Discord RPC (convenience function)."""
    return get_discord().connect()


def update_discord(title: str, artist: str = "", **kwargs):
    """Update Discord presence (convenience function)."""
    discord = get_discord()
    if not discord.is_connected:
        discord.connect()
    discord.update(title, artist, **kwargs)


def clear_discord():
    """Clear Discord presence (convenience function)."""
    get_discord().clear()


# Test
if __name__ == "__main__":
    print("Testing Discord Rich Presence...")
    
    if not DISCORD_RPC_AVAILABLE:
        print("Install pypresence: pip install pypresence")
        exit(1)
    
    discord = DiscordPresence()
    
    if discord.connect():
        print("Connected! Updating presence...")
        discord.set_playing("Garden", "Fujii Kaze")
        
        print("Presence set. Check Discord! (waiting 10 seconds...)")
        time.sleep(10)
        
        print("Clearing presence...")
        discord.clear()
        discord.disconnect()
    else:
        print("Could not connect to Discord")
