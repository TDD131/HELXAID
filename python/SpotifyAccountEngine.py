"""
SpotifyAccountEngine.py - Spotify OAuth2 PKCE & Algorithmic Discovery Engine for HELXAIC
=======================================================================================
Features:
- Zero-Secret PKCE (Proof Key for Code Exchange) OAuth2 Authorization Flow
- Local Loopback Callback Server (http://127.0.0.1:8888/callback) with Auto-Teardown
- Automatic Background Token Refresh with Secure QSettings Session Caching
- Endpoints: Liked Songs (/v1/me/tracks), Playlists (/v1/me/playlists),
  Top Tracks & Artists (/v1/me/top), and Algorithmic Seed Recommendations (/v1/recommendations)
- Tier-1 Disk Caching with Offline Fallback

Component Name: SpotifyAccountEngine
"""

import os
import sys
import json
import time
import base64
import hashlib
import secrets
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any, Optional, Tuple
from PySide6.QtCore import QObject, Signal, QThread, QSettings


# Default HELXAIC Spotify PKCE Public Client ID
SPOTIFY_DEFAULT_CLIENT_ID = "0d2c94380ec843c08e5be2d5a1b32d20"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative user-top-read user-read-recently-played"


class SpotifyAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles OAuth redirect callback from browser with Cyberpunk UI response."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            self.server.auth_result = {"code": code, "state": state, "error": error}

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()

            html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>HELXAIC - Spotify Connected</title>
    <style>
        body {
            background: #0d0f14;
            color: #ffffff;
            font-family: 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .card {
            background: #141720;
            border: 1px solid #1DB954;
            border-radius: 16px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 0 35px rgba(29, 185, 84, 0.25);
            max-width: 420px;
        }
        h1 {
            color: #1DB954;
            font-size: 22px;
            margin-bottom: 12px;
            font-weight: 800;
            letter-spacing: 1px;
        }
        p {
            color: #9ba1b4;
            font-size: 14px;
            line-height: 1.5;
        }
        .tag {
            display: inline-block;
            background: rgba(29, 185, 84, 0.15);
            color: #1DB954;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-top: 18px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>CONNECTION SUCCESSFUL</h1>
        <p>Your Spotify account is now linked with <strong>HELXAIC</strong>. You can safely close this browser window and return to HELXAID.</p>
        <div class="tag">SYNCHRONIZED</div>
    </div>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress server terminal logs


class SpotifyAccountEngine(QObject):
    """Singleton Controller for Spotify Authentication & Data Extraction."""

    authStatusChanged = Signal(bool, str)  # (is_connected, display_name)
    errorOccurred = Signal(str)

    CACHE_DIR = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
    _instance: Optional['SpotifyAccountEngine'] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("TDD131", "HELXAID")
        self.session_data: Dict[str, Any] = self._load_persisted_session()
        self.current_verifier: Optional[str] = None
        self.current_state: Optional[str] = None
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    @classmethod
    def get_instance(cls) -> 'SpotifyAccountEngine':
        if cls._instance is None:
            cls._instance = SpotifyAccountEngine()
        return cls._instance

    def _load_persisted_session(self) -> Dict[str, Any]:
        raw = self.settings.value("SpotifyAccount/session", "{}")
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return {}

    def is_authenticated(self) -> bool:
        return bool(self.session_data.get("access_token") and self.session_data.get("refresh_token"))

    def get_display_name(self) -> str:
        return self.session_data.get("display_name", "Spotify User")

    def get_client_id(self) -> str:
        cid = self.settings.value("SpotifyAccount/client_id", "") or ""
        return cid if cid != SPOTIFY_DEFAULT_CLIENT_ID else ""

    def set_client_id(self, client_id: str):
        self.settings.setValue("SpotifyAccount/client_id", client_id.strip())

    def has_valid_client_id(self) -> bool:
        cid = self.get_client_id()
        return bool(cid and len(cid) >= 16)

    def start_oauth_flow(self) -> bool:
        """Initiate OAuth PKCE flow in default web browser. Returns False if Client ID is needed."""
        client_id = self.get_client_id()
        if not client_id:
            self.errorOccurred.emit("Please set your Spotify Developer Client ID first.")
            return False

        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        state = secrets.token_hex(16)

        self.current_verifier = verifier
        self.current_state = state

        # Start Local Loopback Server
        try:
            server = HTTPServer(("127.0.0.1", 8888), SpotifyAuthCallbackHandler)
            server.auth_result = None
            server.timeout = 120

            def _run_server():
                while server.auth_result is None:
                    server.handle_request()
                server.server_close()

                res = server.auth_result
                if res and res.get("code"):
                    self._exchange_code_for_token(res["code"], verifier)
                elif res and res.get("error"):
                    self.errorOccurred.emit(f"Spotify Login Denied: {res['error']}")

            threading.Thread(target=_run_server, daemon=True, name="SpotifyAuthLoopback").start()
        except Exception as e:
            self.errorOccurred.emit(f"Could not bind local callback port 8888: {e}")
            return False

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": SCOPES
        }
        url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
        import webbrowser
        webbrowser.open(url)
        return True

    def _exchange_code_for_token(self, code: str, verifier: str):
        """Exchange authorization code + code_verifier for access and refresh tokens."""
        client_id = self.settings.value("SpotifyAccount/client_id", SPOTIFY_DEFAULT_CLIENT_ID) or SPOTIFY_DEFAULT_CLIENT_ID
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))

            self.session_data = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", ""),
                "expires_at": int(time.time()) + token_data.get("expires_in", 3600),
                "client_id": client_id,
                "display_name": "Spotify User",
                "avatar_url": ""
            }

            # Fetch User Profile
            try:
                profile = self.fetch_api("/me")
                if profile:
                    self.session_data["display_name"] = profile.get("display_name") or "Spotify User"
                    images = profile.get("images", [])
                    if images:
                        self.session_data["avatar_url"] = images[0].get("url", "")
            except Exception:
                pass

            self.settings.setValue("SpotifyAccount/session", json.dumps(self.session_data))
            self.authStatusChanged.emit(True, self.session_data["display_name"])
        except Exception as e:
            err = f"Failed to exchange Spotify token: {e}"
            self.errorOccurred.emit(err)

    def refresh_access_token(self) -> bool:
        """Silently refresh expired access token."""
        refresh_token = self.session_data.get("refresh_token")
        client_id = self.session_data.get("client_id", SPOTIFY_DEFAULT_CLIENT_ID) or SPOTIFY_DEFAULT_CLIENT_ID
        if not refresh_token:
            return False

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            self.session_data["access_token"] = res["access_token"]
            self.session_data["expires_at"] = int(time.time()) + res.get("expires_in", 3600)
            if "refresh_token" in res:
                self.session_data["refresh_token"] = res["refresh_token"]
            self.settings.setValue("SpotifyAccount/session", json.dumps(self.session_data))
            return True
        except Exception as e:
            print(f"[SpotifyAccountEngine] Token refresh notice: {e}")
            return False

    def disconnect(self):
        """Clear Spotify session data."""
        self.session_data = {}
        self.settings.remove("SpotifyAccount/session")
        self.authStatusChanged.emit(False, "")

    def fetch_api(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute authenticated Spotify Web API request with auto token renewal."""
        if time.time() > self.session_data.get("expires_at", 0) - 180:
            self.refresh_access_token()

        url = f"{SPOTIFY_API_BASE}{endpoint}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        token = self.session_data.get("access_token", "")
        if not token:
            return {}

        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "HELXAID-Client/1.0"
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            if he.code == 401:
                # Retry once after force refresh
                if self.refresh_access_token():
                    token = self.session_data.get("access_token", "")
                    req = urllib.request.Request(url, headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    })
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        return json.loads(resp.read().decode("utf-8"))
            print(f"[SpotifyAccountEngine] API Error ({endpoint}): {he}")
        except Exception as e:
            print(f"[SpotifyAccountEngine] Request exception ({endpoint}): {e}")

        return {}


class FetchSpotifyLikedSongsWorker(QThread):
    """Async worker to fetch user's saved Spotify tracks (/v1/me/tracks)."""
    tracksLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = SpotifyAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "sp_liked_tracks.json")
        tracks: List[Dict[str, Any]] = []

        try:
            res = self.engine.fetch_api("/me/tracks", {"limit": 50})
            items = res.get("items", [])
            for item in items:
                t = item.get("track", {})
                if not t:
                    continue
                sp_id = t.get("id", "")
                title = t.get("name", "Unknown Track")
                artists = ", ".join([a.get("name", "") for a in t.get("artists", []) if a.get("name")])
                album_data = t.get("album", {})
                album_name = album_data.get("name", "Spotify Track")
                duration = float(t.get("duration_ms", 0)) / 1000.0
                images = album_data.get("images", [])
                thumb_url = images[0].get("url", "") if images else ""
                isrc = t.get("external_ids", {}).get("isrc", "")

                tracks.append({
                    "id": f"sp_{sp_id}",
                    "spotify_id": sp_id,
                    "title": title,
                    "artist": artists or "Unknown Artist",
                    "album": album_name,
                    "duration": duration,
                    "thumbnail_url": thumb_url,
                    "source": "spotify",
                    "original_url": f"https://open.spotify.com/track/{sp_id}",
                    "isrc": isrc,
                    "badge": "LIKED",
                    "is_stream": True,
                    "is_online": True
                })

            if tracks:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(tracks, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    tracks = json.load(f)

            if not self._is_cancelled:
                self.tracksLoaded.emit(tracks)
        except Exception as e:
            if not self._is_cancelled:
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            tracks = json.load(f)
                        self.tracksLoaded.emit(tracks)
                        return
                    except Exception:
                        pass
                self.errorOccurred.emit(str(e))


class FetchSpotifyPlaylistsWorker(QThread):
    """Async worker to fetch user's Spotify playlists (/v1/me/playlists)."""
    playlistsLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = SpotifyAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "sp_playlists.json")
        playlists: List[Dict[str, Any]] = []

        try:
            res = self.engine.fetch_api("/me/playlists", {"limit": 50})
            items = res.get("items", [])
            for item in items:
                if not item:
                    continue
                p_id = item.get("id", "")
                title = item.get("name", "Unknown Playlist")
                desc = item.get("description", "Spotify Playlist")
                tracks_count = item.get("tracks", {}).get("total", 0)
                images = item.get("images", [])
                thumb_url = images[0].get("url", "") if images else ""

                playlists.append({
                    "id": f"sp_p_{p_id}",
                    "playlist_id": p_id,
                    "title": title,
                    "description": desc or "Spotify Playlist",
                    "track_count": tracks_count,
                    "thumbnail_url": thumb_url,
                    "source": "spotify",
                    "original_url": f"https://open.spotify.com/playlist/{p_id}",
                    "is_algorithmic": False,
                    "badge": "SPOTIFY"
                })

            if playlists:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(playlists, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    playlists = json.load(f)

            if not self._is_cancelled:
                self.playlistsLoaded.emit(playlists)
        except Exception as e:
            if not self._is_cancelled:
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            playlists = json.load(f)
                        self.playlistsLoaded.emit(playlists)
                        return
                    except Exception:
                        pass
                self.errorOccurred.emit(str(e))


class FetchSpotifyAlgorithmicFeedsWorker(QThread):
    """Async worker to fetch Spotify personalized algorithmic recommendations & daily mixes."""
    recommendationsLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = SpotifyAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "sp_recommendations.json")
        rec_cards: List[Dict[str, Any]] = []

        try:
            # 1. Fetch User Top Artists & Tracks for Seeds
            top_artists_res = self.engine.fetch_api("/me/top/artists", {"limit": 3})
            top_tracks_res = self.engine.fetch_api("/me/top/tracks", {"limit": 2})

            seed_artists = [a.get("id") for a in top_artists_res.get("items", []) if a.get("id")]
            seed_tracks = [t.get("id") for t in top_tracks_res.get("items", []) if t.get("id")]

            # 2. Fetch Algorithmic Seed Recommendations
            if seed_artists or seed_tracks:
                params = {"limit": 20}
                if seed_artists:
                    params["seed_artists"] = ",".join(seed_artists[:2])
                if seed_tracks:
                    params["seed_tracks"] = ",".join(seed_tracks[:2])

                recs_res = self.engine.fetch_api("/recommendations", params)
                for t in recs_res.get("tracks", []):
                    sp_id = t.get("id", "")
                    title = t.get("name", "Recommendation")
                    artists = ", ".join([a.get("name", "") for a in t.get("artists", []) if a.get("name")])
                    album_data = t.get("album", {})
                    album_name = album_data.get("name", "Recommended Track")
                    duration = float(t.get("duration_ms", 0)) / 1000.0
                    images = album_data.get("images", [])
                    thumb_url = images[0].get("url", "") if images else ""
                    isrc = t.get("external_ids", {}).get("isrc", "")

                    rec_cards.append({
                        "id": f"sp_rec_{sp_id}",
                        "spotify_id": sp_id,
                        "title": title,
                        "artist": artists or "Spotify Algorithm",
                        "album": album_name,
                        "duration": duration,
                        "thumbnail_url": thumb_url,
                        "source": "spotify",
                        "original_url": f"https://open.spotify.com/track/{sp_id}",
                        "isrc": isrc,
                        "badge": "DISCOVERY",
                        "is_stream": True,
                        "is_online": True,
                        "is_algorithmic": True
                    })

            if rec_cards:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(rec_cards, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    rec_cards = json.load(f)

            if not self._is_cancelled:
                self.recommendationsLoaded.emit(rec_cards)
        except Exception as e:
            if not self._is_cancelled:
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            rec_cards = json.load(f)
                        self.recommendationsLoaded.emit(rec_cards)
                        return
                    except Exception:
                        pass
                self.errorOccurred.emit(str(e))
