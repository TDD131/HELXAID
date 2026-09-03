"""
YouTubeAccountEngine.py - Authenticated YouTube Music Session & Feed Engine for HELXAIC
======================================================================================
Features:
- Windows-Safe Browser Cookie Shadow Extraction (Chrome, Edge, Brave, Firefox, Opera, Vivaldi)
- SAPISIDHASH Authorization Generator for Innertube Private APIs
- High-Performance Async Data Fetching for Liked Music (LM/LL), User Playlists, and Algorithmic Mixes
- Real-time Algorithmic Recommendation Parser (FEmusic_home & FEmusic_mixed_for_you)
- Tier-1 Disk Caching with Offline Fallback

Component Name: YouTubeAccountEngine
"""

import os
import sys
import json
import time
import ssl
import hashlib
import tempfile
import secrets
import base64
import threading
import sqlite3
import urllib.request
import urllib.parse
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any, Optional, Tuple, Callable
from PySide6.QtCore import QObject, Signal, QThread, QSettings


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REDIRECT_URI = "http://127.0.0.1:8888/callback"
GOOGLE_YOUTUBE_SCOPES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube"


class GoogleAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles OAuth redirect callback from browser for Google authentication."""
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
    <title>HELXAIC - Google Connected</title>
    <style>
        body { background: #0d0f14; color: #ffffff; font-family: 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .card { background: #141720; border: 1px solid #FF0000; border-radius: 16px; padding: 40px; text-align: center; box-shadow: 0 0 35px rgba(255, 0, 0, 0.25); max-width: 420px; }
        h1 { color: #FF5252; font-size: 22px; margin-bottom: 12px; font-weight: 800; }
        p { color: #9ba1b4; font-size: 14px; line-height: 1.5; }
        .tag { display: inline-block; background: rgba(255, 0, 0, 0.15); color: #FF5252; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-top: 18px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>GOOGLE ACCOUNT CONNECTED</h1>
        <p>Your YouTube Music session is now linked with <strong>HELXAIC</strong>. You can safely close this browser window and return to HELXAID.</p>
        <div class="tag">SYNCHRONIZED</div>
    </div>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def _dpapi_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """Decrypt Windows DPAPI protected data using win32crypt or ctypes fallback."""
    if not encrypted_data:
        return None
    try:
        import win32crypt
        unprotected = win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)
        if unprotected and len(unprotected) > 1 and unprotected[1]:
            return unprotected[1]
    except Exception:
        pass

    try:
        import ctypes
        from ctypes import wintypes

        class _LocalDataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

        raw_buf = ctypes.create_string_buffer(encrypted_data, len(encrypted_data))
        in_blob = _LocalDataBlob(len(encrypted_data), ctypes.cast(raw_buf, ctypes.c_void_p))
        out_blob = _LocalDataBlob(0, None)

        crypt32 = ctypes.WinDLL("crypt32.dll")
        crypt32.CryptUnprotectData.restype = wintypes.BOOL

        if crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
            return decrypted
    except Exception:
        pass
    return None


def _copy_locked_file_win32(src_path: str, dst_path: str) -> bool:
    """Copy a file on Windows even if locked by an active browser process using backup semantics."""
    if not os.path.exists(src_path):
        return False
    # Try normal copy first
    try:
        import shutil
        shutil.copy2(src_path, dst_path)
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
            return True
    except Exception:
        pass

    try:
        import ctypes
        from ctypes import wintypes
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        FILE_SHARE_DELETE = 0x00000004
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
        FILE_ATTRIBUTE_NORMAL = 0x80
        FLAGS = FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_SEQUENTIAL_SCAN | FILE_ATTRIBUTE_NORMAL

        k32 = ctypes.windll.kernel32
        k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
        ]
        k32.CreateFileW.restype = wintypes.HANDLE

        handle = k32.CreateFileW(
            src_path,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FLAGS,
            None
        )
        if handle == wintypes.HANDLE(-1).value or handle == -1 or not handle:
            return False

        k32.ReadFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
        ]
        k32.ReadFile.restype = wintypes.BOOL

        with open(dst_path, "wb") as dst_f:
            buf_size = 64 * 1024
            buf = ctypes.create_string_buffer(buf_size)
            bytes_read = wintypes.DWORD(0)
            while True:
                ok = k32.ReadFile(handle, buf, buf_size, ctypes.byref(bytes_read), None)
                if not ok or bytes_read.value == 0:
                    break
                dst_f.write(buf.raw[:bytes_read.value])

        k32.CloseHandle(handle)
        return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
    except Exception:
        return False


class YouTubeAccountEngine(QObject):
    """Singleton Controller for YouTube / YouTube Music Authentication & Feed Retrieval."""

    sessionChanged = Signal(bool, str)  # (is_authenticated, user_display_name)
    errorOccurred = Signal(str)

    CACHE_DIR = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
    _instance: Optional['YouTubeAccountEngine'] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("TDD131", "HELXAID")
        self.session_data: Dict[str, Any] = self._load_persisted_session()
        self.current_verifier: Optional[str] = None
        self.current_state: Optional[str] = None
        self._playlist_tracks_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    def get_cached_playlist_tracks(self, browse_id: str, max_age_sec: int = 86400) -> Optional[List[Dict[str, Any]]]:
        """Instant 0ms memory or <1ms persistent disk retrieval for playlists/mixes (TTL 24 hours)."""
        if not browse_id:
            return None
        clean_id = browse_id[3:] if browse_id.startswith("yt_") else browse_id
        
        # 1. Tier 0: RAM Cache
        if clean_id in getattr(self, '_playlist_tracks_cache', {}):
            ts, tracks = self._playlist_tracks_cache[clean_id]
            if time.time() - ts < max_age_sec and tracks:
                return list(tracks)

        # 2. Tier 1: Persistent Disk Cache
        try:
            pl_cache_dir = os.path.join(self.CACHE_DIR, "playlist_tracks")
            fpath = os.path.join(pl_cache_dir, f"{clean_id}.json")
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict):
                    ts = payload.get("timestamp", 0)
                    tracks = payload.get("tracks", [])
                    if tracks and (time.time() - ts < max_age_sec):
                        self._playlist_tracks_cache[clean_id] = (ts, list(tracks))
                        return list(tracks)
        except Exception:
            pass

        return None

    def save_cached_playlist_tracks(self, clean_id: str, tracks: List[Dict[str, Any]]):
        """Atomically persist playlist/mix tracks to RAM and Disk."""
        if not clean_id or not tracks:
            return
        ts = time.time()
        self._playlist_tracks_cache[clean_id] = (ts, list(tracks))
        try:
            pl_cache_dir = os.path.join(self.CACHE_DIR, "playlist_tracks")
            os.makedirs(pl_cache_dir, exist_ok=True)
            fpath = os.path.join(pl_cache_dir, f"{clean_id}.json")
            tmp_path = fpath + f".{os.getpid()}_{int(ts*1000)}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": ts, "tracks": tracks}, f, ensure_ascii=False, indent=2)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            os.replace(tmp_path, fpath)
        except Exception as e:
            print(f"[YouTubeAccountEngine] Failed to persist playlist tracks: {e}")

    @classmethod
    def get_instance(cls) -> 'YouTubeAccountEngine':
        if cls._instance is None:
            cls._instance = YouTubeAccountEngine()
        return cls._instance

    @classmethod
    def _get_session_disk_path(cls) -> str:
        appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
        d = os.path.join(appdata, "HELXAID")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "youtube_session.json")

    def _save_session_data(self, data: Dict[str, Any]):
        self.session_data = data
        try:
            self.settings.setValue("YouTubeAccount/session", json.dumps(data))
            self.settings.sync()
        except Exception as e:
            print(f"[YouTubeAccountEngine] Settings sync notice: {e}")
            
        try:
            path = self._get_session_disk_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Also preserve a Last Known Good Session (LKGS) snapshot
            if data.get("cookies") or data.get("access_token"):
                backup_path = path.replace(".json", "_last_good.json")
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[YouTubeAccountEngine] Disk session save notice: {e}")

    def _load_persisted_session(self) -> Dict[str, Any]:
        data = {}
        # 1. Primary: Read from QSettings registry
        raw = self.settings.value("YouTubeAccount/session", "{}")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict) and (parsed.get("cookies") or parsed.get("access_token")):
                data = parsed
        except Exception:
            pass

        # 2. Secondary fallback: Read from persistent disk file in LocalAppData
        if not data:
            try:
                path = self._get_session_disk_path()
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        disk_data = json.load(f)
                    if isinstance(disk_data, dict) and (disk_data.get("cookies") or disk_data.get("access_token")):
                        data = disk_data
                        # Self-heal QSettings from disk file
                        self.settings.setValue("YouTubeAccount/session", json.dumps(data))
                        self.settings.sync()
            except Exception:
                pass

        # 3. Tertiary fallback: Last Known Good Session backup
        if not data:
            try:
                backup_path = self._get_session_disk_path().replace(".json", "_last_good.json")
                if os.path.exists(backup_path):
                    with open(backup_path, "r", encoding="utf-8") as f:
                        bk_data = json.load(f)
                    if isinstance(bk_data, dict) and (bk_data.get("cookies") or bk_data.get("access_token")):
                        data = bk_data
                        self._save_session_data(data)
            except Exception:
                pass

        return data

    def reload_session(self) -> bool:
        """Reload persisted session from QSettings and disk file into memory."""
        data = self._load_persisted_session()
        if data and isinstance(data, dict):
            cookies = data.get("cookies", {})
            sapisid = data.get("sapisid") or cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")
            if sapisid or data.get("access_token"):
                changed = (data.get("sapisid") != self.session_data.get("sapisid"))
                self.session_data = data
                if changed:
                    user_name = self.get_user_name()
                    self.sessionChanged.emit(self.is_authenticated(), user_name)
                return self.is_authenticated()
        return False

    def get_client_id(self) -> str:
        return self.settings.value("YouTubeAccount/client_id", "") or ""

    def get_client_secret(self) -> str:
        return self.settings.value("YouTubeAccount/client_secret", "") or ""

    def set_client_credentials(self, client_id: str, client_secret: str = ""):
        self.settings.setValue("YouTubeAccount/client_id", client_id.strip())
        self.settings.setValue("YouTubeAccount/client_secret", client_secret.strip())

    def has_valid_client_id(self) -> bool:
        cid = self.get_client_id()
        return bool(cid and len(cid) >= 16)

    def is_oauth_authenticated(self) -> bool:
        return bool(self.session_data.get("access_token") and self.session_data.get("refresh_token"))

    def is_authenticated(self) -> bool:
        if self.is_oauth_authenticated():
            return True
        cookies = self.session_data.get("cookies", {})
        sapisid = self.session_data.get("sapisid") or cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")
        return bool(cookies and sapisid)

    def get_auth_type(self) -> str:
        if self.is_oauth_authenticated():
            return "oauth2"
        if self.session_data.get("sapisid") or self.session_data.get("cookies"):
            return "cookies"
        return "none"

    def get_user_name(self) -> str:
        return self.session_data.get("user_name") or self.session_data.get("display_name") or "YouTube Music User"

    def get_avatar_url(self) -> str:
        return self.session_data.get("avatar_url", "")

    def get_access_token(self) -> str:
        """Return valid access token, silently refreshing if expired or near expiry."""
        if not self.is_oauth_authenticated():
            return ""
        expires_at = self.session_data.get("expires_at", 0)
        if time.time() >= (expires_at - 120):
            self.refresh_access_token()
        return self.session_data.get("access_token", "")

    def refresh_access_token(self) -> bool:
        """Silently refresh expired Google OAuth2 access token."""
        refresh_token = self.session_data.get("refresh_token")
        client_id = self.get_client_id() or self.session_data.get("client_id", "")
        client_secret = self.get_client_secret() or self.session_data.get("client_secret", "")

        if not refresh_token or not client_id:
            return False

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }
        if client_secret:
            payload["client_secret"] = client_secret

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            self.session_data["access_token"] = res["access_token"]
            self.session_data["expires_at"] = int(time.time()) + res.get("expires_in", 3600)
            self.settings.setValue("YouTubeAccount/session", json.dumps(self.session_data))
            return True
        except Exception as e:
            print(f"[YouTubeAccountEngine] Token refresh notice: {e}")
            return False

    def start_oauth_flow(self) -> bool:
        """Initiate 1-Click Google OAuth2 Login with local loopback server."""
        client_id = self.get_client_id()
        if not client_id:
            self.errorOccurred.emit("Please enter your Google OAuth Client ID first.")
            return False

        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        state = secrets.token_hex(16)

        self.current_verifier = verifier
        self.current_state = state

        # Start Local Loopback Server
        try:
            server = HTTPServer(("127.0.0.1", 8888), GoogleAuthCallbackHandler)
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
                    self.errorOccurred.emit(f"Google Login Denied: {res['error']}")

            threading.Thread(target=_run_server, daemon=True, name="GoogleAuthLoopback").start()
        except Exception as e:
            self.errorOccurred.emit(f"Could not bind local callback port 8888: {e}")
            return False

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": GOOGLE_YOUTUBE_SCOPES,
            "access_type": "offline",
            "prompt": "consent"
        }
        url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        import webbrowser
        webbrowser.open(url)
        return True

    def _exchange_code_for_token(self, code: str, verifier: str):
        """Exchange authorization code + verifier for Google access & refresh tokens."""
        client_id = self.get_client_id()
        client_secret = self.get_client_secret()

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier
        }
        if client_secret:
            payload["client_secret"] = client_secret

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))

            self.session_data = {
                "auth_type": "oauth2",
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", ""),
                "expires_at": int(time.time()) + token_data.get("expires_in", 3600),
                "client_id": client_id,
                "client_secret": client_secret,
                "user_name": "Google / YouTube User",
                "avatar_url": ""
            }

            # Fetch Channel Profile Info
            try:
                prof_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
                prof_req = urllib.request.Request(
                    prof_url,
                    headers={"Authorization": f"Bearer {token_data['access_token']}"}
                )
                with urllib.request.urlopen(prof_req, timeout=6) as presp:
                    pdata = json.loads(presp.read().decode("utf-8"))
                    items = pdata.get("items", [])
                    if items:
                        snippet = items[0].get("snippet", {})
                        self.session_data["user_name"] = snippet.get("title") or "YouTube User"
                        thumbs = snippet.get("thumbnails", {}).get("default", {})
                        if thumbs:
                            self.session_data["avatar_url"] = thumbs.get("url", "")
            except Exception as e:
                print(f"[YouTubeAccountEngine] Channel profile fetch notice: {e}")

            self.settings.setValue("YouTubeAccount/session", json.dumps(self.session_data))
            self.sessionChanged.emit(True, self.session_data["user_name"])
        except Exception as e:
            err = f"Failed to exchange Google token: {e}"
            self.errorOccurred.emit(err)

    def import_cookies_dict(self, cookies: Dict[str, str], user_name: str = "") -> Tuple[bool, str]:
        """Directly import a dictionary of captured cookies from Google Web Login."""
        if not cookies:
            return False, "No cookies captured."
        
        sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
        if not sapisid:
            return False, "Missing critical authentication token (SAPISID/SID)."

        if not user_name:
            user_name = cookies.get("ACCOUNT_NAME") or cookies.get("LOGIN_INFO") or "Google / YouTube User"
            if len(user_name) > 30:
                user_name = "Google / YouTube User"

        self.session_data = {
            "browser": "google_web_login",
            "cookies": cookies,
            "sapisid": sapisid,
            "synced_at": int(time.time()),
            "user_name": user_name,
            "auth_type": "google_web"
        }
        self._save_session_data(self.session_data)
        self.sessionChanged.emit(True, user_name)
        return True, f"Successfully authenticated as {user_name}!"

    @staticmethod
    def get_discovered_browser_profiles() -> List[Dict[str, Any]]:
        """
        Scan all installed browsers (Chrome, Edge, Brave, Opera, Vivaldi, Firefox)
        for genuine user profiles and signed-in Google accounts.
        """
        results: List[Dict[str, Any]] = []
        seen_keys = set()

        browser_configs = [
            ("Google Chrome", "chrome", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"), "chrome.png"),
            ("Microsoft Edge", "edge", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"), "edge.png"),
            ("Brave Browser", "brave", os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"), "brave.png"),
            ("Opera", "opera", os.path.expandvars(r"%APPDATA%\Opera Software\Opera Stable"), "opera.png"),
            ("Opera GX", "opera", os.path.expandvars(r"%APPDATA%\Opera Software\Opera GX Stable"), "opera.png"),
            ("Vivaldi", "vivaldi", os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\User Data"), "vivaldi.png")
        ]

        for b_name, b_code, b_dir, icon_file in browser_configs:
            if not os.path.exists(b_dir):
                continue

            ls_path = os.path.join(b_dir, "Local State")
            found_any = False
            if os.path.exists(ls_path):
                try:
                    with open(ls_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    info_cache = data.get("profile", {}).get("info_cache", {})
                    for prof_dir, prof_data in info_cache.items():
                        email = (prof_data.get("user_name", "") or "").strip()
                        gaia_name = (prof_data.get("gaia_name", "") or "").strip()
                        prof_name = (prof_data.get("name", "") or "").strip()

                        # Prefer Google Account Name > Profile Name > Email Prefix
                        name = gaia_name or prof_name
                        if not name and email:
                            name = email.split("@")[0].title()
                        if not name:
                            name = prof_dir

                        dedup_key = f"{b_code}:{prof_dir}"
                        if dedup_key not in seen_keys:
                            seen_keys.add(dedup_key)
                            found_any = True
                            results.append({
                                "browser": b_name,
                                "browser_code": b_code,
                                "profile_dir": prof_dir,
                                "name": name,
                                "email": email,
                                "icon_file": icon_file,
                                "is_signed_in": bool(email or gaia_name)
                            })
                except Exception:
                    pass

            if not found_any:
                dedup_key = f"{b_code}:Default"
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    results.append({
                        "browser": b_name,
                        "browser_code": b_code,
                        "profile_dir": "Default",
                        "name": f"{b_name} (Default)",
                        "email": "",
                        "icon_file": icon_file,
                        "is_signed_in": False
                    })

        # Discover Firefox profiles
        ff_root = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox")
        ff_ini = os.path.join(ff_root, "profiles.ini")
        if os.path.exists(ff_ini):
            try:
                import configparser
                cfg = configparser.ConfigParser()
                cfg.read(ff_ini)
                for sec in cfg.sections():
                    if sec.startswith("Profile"):
                        p_name = cfg.get(sec, "Name", fallback="Default")
                        p_path = cfg.get(sec, "Path", fallback="")
                        dedup_key = f"firefox:{p_name}"
                        if dedup_key not in seen_keys:
                            seen_keys.add(dedup_key)
                            results.append({
                                "browser": "Mozilla Firefox",
                                "browser_code": "firefox",
                                "profile_dir": p_path or p_name,
                                "name": f"Firefox - {p_name}",
                                "email": "",
                                "icon_file": "firefox.png",
                                "is_signed_in": False
                            })
            except Exception:
                pass

        # Sort: Signed-in accounts first, then by browser name
        results.sort(key=lambda x: (not x["is_signed_in"], x["browser"], x["name"]))
        return results

    def _extract_chromium_cookies_direct(self, browser_code: str, profile_dir: Optional[str] = "Default") -> Dict[str, str]:
        """
        Directly extracts and decrypts YouTube/Google cookies from Chromium browsers on Windows,
        bypassing file lock issues even when the browser is actively open and playing audio.
        """
        import base64
        import sqlite3
        import tempfile
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except Exception:
            AESGCM = None

        browser_paths = {
            "chrome": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
            "edge": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
            "brave": os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
            "opera": os.path.expandvars(r"%APPDATA%\Opera Software\Opera Stable"),
            "vivaldi": os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\User Data")
        }

        user_data = browser_paths.get((browser_code or "").lower())
        if not user_data or not os.path.exists(user_data):
            return {}

        local_state_path = os.path.join(user_data, "Local State")
        if not os.path.exists(local_state_path):
            return {}

        # 1. Decrypt Master Key via DPAPI
        aes_key = None
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
            if encrypted_key_b64:
                encrypted_key = base64.b64decode(encrypted_key_b64)
                if encrypted_key[:5] == b'DPAPI':
                    encrypted_key = encrypted_key[5:]
                aes_key = _dpapi_decrypt(encrypted_key)
        except Exception:
            pass

        # 2. Candidate profile folders to check
        folders_to_try = []
        if profile_dir and profile_dir.lower() not in ("none", ""):
            folders_to_try.append(profile_dir)
        for fallback_f in ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]:
            if fallback_f not in folders_to_try:
                folders_to_try.append(fallback_f)

        for prof_folder in folders_to_try:
            cookie_db_path = os.path.join(user_data, prof_folder, "Network", "Cookies")
            if not os.path.exists(cookie_db_path):
                cookie_db_path = os.path.join(user_data, prof_folder, "Cookies")
            if not os.path.exists(cookie_db_path):
                continue

            temp_id = f"helxaid_ck_{browser_code}_{int(time.time()*1000)}"
            temp_cookie_db = os.path.join(tempfile.gettempdir(), f"{temp_id}.db")
            temp_wal = os.path.join(tempfile.gettempdir(), f"{temp_id}.db-wal")
            temp_shm = os.path.join(tempfile.gettempdir(), f"{temp_id}.db-shm")

            copied = _copy_locked_file_win32(cookie_db_path, temp_cookie_db)
            if not copied:
                continue

            # Also copy WAL and SHM files if present for SQLite journal consistency
            if os.path.exists(cookie_db_path + "-wal"):
                _copy_locked_file_win32(cookie_db_path + "-wal", temp_wal)
            if os.path.exists(cookie_db_path + "-shm"):
                _copy_locked_file_win32(cookie_db_path + "-shm", temp_shm)

            cookies = {}
            try:
                conn = sqlite3.connect(temp_cookie_db)
                cursor = conn.cursor()
                cursor.execute("SELECT name, value, encrypted_value FROM cookies WHERE host_key LIKE '%youtube.com%' OR host_key LIKE '%google.com%'")
                rows = cursor.fetchall()
                for name, val, enc_val in rows:
                    if val:
                        cookies[name] = val
                    elif enc_val and aes_key and AESGCM:
                        try:
                            if enc_val[:3] in (b'v10', b'v11'):
                                nonce = enc_val[3:15]
                                ciphertext = enc_val[15:]
                                aesgcm = AESGCM(aes_key)
                                dec = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8', errors='ignore')
                                if dec:
                                    cookies[name] = dec
                        except Exception:
                            pass
                    elif enc_val:
                        dec = _dpapi_decrypt(enc_val)
                        if dec:
                            try:
                                cookies[name] = dec.decode('utf-8', errors='ignore')
                            except Exception:
                                pass
                conn.close()
            except Exception:
                pass
            finally:
                for tf in [temp_cookie_db, temp_wal, temp_shm]:
                    if os.path.exists(tf):
                        try:
                            os.remove(tf)
                        except Exception:
                            pass

            # Check if this profile has active login tokens
            sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
            if sapisid:
                return cookies

        return {}

    def _extract_single_browser(self, browser_clean: str, profile_dir: Optional[str] = None) -> Tuple[bool, str, Dict[str, str], str]:
        """Try extracting YouTube cookies from a single browser and optional profile."""
        cookies: Dict[str, str] = {}

        # 1. Try direct unlocked extraction for Chromium browsers first
        if browser_clean in ("chrome", "edge", "brave", "opera", "vivaldi"):
            try:
                cookies = self._extract_chromium_cookies_direct(browser_clean, profile_dir)
            except Exception:
                cookies = {}

        # 2. Try utils.cookie_exporter if not found
        sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
        if not sapisid and browser_clean in ("chrome", "edge", "brave"):
            try:
                from utils.cookie_exporter import get_cookie_exporter
                exporter = get_cookie_exporter()
                cookie_list = exporter.get_cookies_for_browser(browser_clean, domains=["youtube.com", "google.com"])
                for c in cookie_list:
                    cookies[c.name] = c.value
            except Exception:
                pass

        # 3. If direct extraction didn't find session tokens, fallback to yt-dlp
        sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
        if not sapisid:
            try:
                import yt_dlp.cookies
                kwargs = {}
                if profile_dir and profile_dir.lower() not in ("default", "none", ""):
                    kwargs["profile"] = profile_dir

                cookie_jar = yt_dlp.cookies.extract_cookies_from_browser(browser_clean, **kwargs)
                for cookie in cookie_jar:
                    domain = getattr(cookie, 'domain', '') or ''
                    if "youtube.com" in domain or "google.com" in domain:
                        cookies[cookie.name] = cookie.value
            except Exception as e:
                err_str = str(e)
                if "could not copy" in err_str.lower() or "used by another process" in err_str.lower():
                    return False, f"Could not access {browser_clean.title()} cookie file. Please close {browser_clean.title()} or use 'Import cookies.txt'.", {}, ""
                if not cookies:
                    return False, err_str, {}, ""

        if not cookies:
            return False, f"No YouTube cookies found in {browser_clean.title()}.", {}, ""

        sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
        if not sapisid:
            return False, f"No active YouTube login session found in {browser_clean.title()}.", {}, ""

        user_name = ""
        profiles = YouTubeAccountEngine.get_discovered_browser_profiles()
        for prof in profiles:
            if prof.get("browser_code") == browser_clean:
                if profile_dir and prof.get("profile_dir") == profile_dir:
                    user_name = prof.get("name") or prof.get("email")
                    break
                elif not profile_dir and prof.get("name"):
                    user_name = prof.get("name")
                    break

        if not user_name:
            user_name = cookies.get("ACCOUNT_NAME") or cookies.get("LOGIN_INFO") or f"{browser_clean.title()} Account"

        return True, "", cookies, user_name

    def sync_from_browser(self, browser_name: str = "auto", profile_dir: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Extract YouTube cookies safely from a specific browser profile or automatically.
        Returns: (success: bool, message: str, active_browser: str)
        """
        browser_clean = (browser_name or "auto").strip().lower()

        # If specific browser is requested
        if browser_clean != "auto":
            ok, err, cookies, user_name = self._extract_single_browser(browser_clean, profile_dir)
            if ok:
                sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
                self.session_data = {
                    "browser": browser_clean,
                    "profile_dir": profile_dir or "Default",
                    "cookies": cookies,
                    "sapisid": sapisid,
                    "synced_at": int(time.time()),
                    "user_name": user_name
                }
                self._save_session_data(self.session_data)
                self.sessionChanged.emit(True, user_name)
                return True, f"Successfully synced YouTube session ({user_name})!", browser_clean
            elif profile_dir:
                self.errorOccurred.emit(err or "Failed to extract session from selected profile.")
                return False, err or "Failed to extract session.", browser_clean

        # Strictly try Chrome only to avoid accidental cross-browser profile poisoning
        ok, err, cookies, user_name = self._extract_single_browser("chrome")
        if ok:
            sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
            self.session_data = {
                "browser": "chrome",
                "profile_dir": "Default",
                "cookies": cookies,
                "sapisid": sapisid,
                "synced_at": int(time.time()),
                "user_name": user_name
            }
            self._save_session_data(self.session_data)
            self.sessionChanged.emit(True, user_name)
            return True, f"Successfully synced YouTube session from Google Chrome ({user_name})!", "chrome"

        err_msg = "Google Chrome session database is locked while Chrome is running. Please use the HELXAID Chrome Extension to sync instantly!"
        self.errorOccurred.emit(err_msg)
        return False, err_msg, browser_clean

    def import_cookies_txt(self, file_path: str) -> Tuple[bool, str]:
        """Import Netscape format cookies.txt file exported from browser extension."""
        if not os.path.exists(file_path):
            return False, "Selected cookie file does not exist."
        try:
            cookies: Dict[str, str] = {}
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        domain = parts[0]
                        name = parts[5]
                        value = parts[6]
                        if "youtube.com" in domain or "google.com" in domain:
                            cookies[name] = value

            if not cookies:
                return False, "No YouTube or Google cookies found in the selected file."

            sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
            if not sapisid:
                return False, "File missing required YouTube authentication token (SAPISID/SID)."

            user_name = cookies.get("ACCOUNT_NAME") or "YouTube User (Imported)"
            self.session_data = {
                "browser": "cookies_txt",
                "cookies": cookies,
                "sapisid": sapisid,
                "synced_at": int(time.time()),
                "user_name": user_name
            }
            self._save_session_data(self.session_data)
            self.sessionChanged.emit(True, user_name)
            return True, f"Successfully imported YouTube session from {os.path.basename(file_path)}!"
        except Exception as e:
            return False, f"Failed to parse cookies.txt: {e}"

    def import_raw_cookie_string(self, raw_str: str) -> Tuple[bool, str]:
        """Import raw cookie header string (e.g. SAPISID=...; SID=...) or JSON cookie array."""
        if not raw_str:
            return False, "Cookie string is empty."
        try:
            raw_str = raw_str.strip()
            cookies: Dict[str, str] = {}
            
            # Check if JSON array format (from Cookie-Editor extension)
            if raw_str.startswith("[") and raw_str.endswith("]"):
                try:
                    items = json.loads(raw_str)
                    for it in items:
                        if isinstance(it, dict) and "name" in it and "value" in it:
                            domain = it.get("domain", "")
                            if not domain or "youtube.com" in domain or "google.com" in domain:
                                cookies[it["name"]] = it["value"]
                except Exception:
                    pass

            # Standard Key=Value HTTP header format
            if not cookies:
                for item in raw_str.split(";"):
                    item = item.strip()
                    if "=" in item:
                        k, v = item.split("=", 1)
                        cookies[k.strip()] = v.strip()

            sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("SID")
            if not sapisid:
                return False, "Missing SAPISID or SID in the pasted cookies. Make sure you exported from youtube.com."

            user_name = cookies.get("ACCOUNT_NAME") or "YouTube User (Imported)"
            self.session_data = {
                "browser": "manual_cookie",
                "cookies": cookies,
                "sapisid": sapisid,
                "synced_at": int(time.time()),
                "user_name": user_name
            }
            self._save_session_data(self.session_data)
            self.sessionChanged.emit(True, user_name)
            return True, "Successfully imported YouTube session cookies!"
        except Exception as e:
            return False, f"Failed to parse cookie string: {e}"

    def disconnect(self):
        """Clear YouTube session data."""
        self.session_data = {}
        self.settings.remove("YouTubeAccount/session")
        try:
            self.settings.sync()
        except Exception:
            pass
        try:
            path = self._get_session_disk_path()
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        self.sessionChanged.emit(False, "")

    def get_auth_headers(self) -> Dict[str, str]:
        """Generate official YouTube SAPISIDHASH or Bearer Authorization Headers for Innertube."""
        origin = "https://music.youtube.com"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "X-YouTube-Client-Name": "67",  # YouTube Music Web
            "X-YouTube-Client-Version": "1.20240901.01.00",
            "X-Origin": origin,
            "Origin": origin,
            "Referer": "https://music.youtube.com/",
            "X-Goog-AuthUser": "0",
            "Content-Type": "application/json"
        }

        if self.is_oauth_authenticated():
            token = self.get_access_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            return headers

        cookies = self.session_data.get("cookies", {})
        sapisid = self.session_data.get("sapisid", "")
        if not sapisid:
            sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID") or cookies.get("__Secure-1PAPISID") or ""

        now = int(time.time())
        if sapisid:
            hash_input = f"{now} {sapisid} {origin}"
            sapisid_hash = hashlib.sha1(hash_input.encode("utf-8")).hexdigest()
            headers["Authorization"] = f"SAPISIDHASH {now}_{sapisid_hash}"

        if cookies:
            headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookies.items()])

        return headers

    def execute_innertube_browse(self, browse_id: str = "", continuation: Optional[str] = None, params: Optional[str] = None) -> Dict[str, Any]:
        """Execute authenticated request to music.youtube.com Innertube Browse API."""
        # Suppress known authenticated-only browse requests if not authenticated
        private_endpoints = {"FEmusic_library_playlists", "FEmusic_liked_videos", "LM", "FEmusic_library_landing"}
        if browse_id in private_endpoints and not self.is_authenticated():
            return {}

        endpoint = "https://music.youtube.com/youtubei/v1/browse?prettyPrint=false"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB_REMIX",
                    "clientVersion": "1.20240901.01.00",
                    "hl": "en",
                    "gl": "US"
                }
            }
        }
        if browse_id:
            payload["browseId"] = browse_id
        if continuation:
            payload["continuation"] = continuation
        if params:
            payload["params"] = params

        headers = self.get_auth_headers()
        ctx = ssl._create_unverified_context()
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass

        return {}

    def execute_innertube_next(self, playlist_id: str = "", video_id: str = "", continuation: Optional[str] = None, params: Optional[str] = None) -> Dict[str, Any]:
        """Execute authenticated request to music.youtube.com Innertube Next/Radio API."""
        endpoint = "https://music.youtube.com/youtubei/v1/next?prettyPrint=false"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB_REMIX",
                    "clientVersion": "1.20240901.01.00",
                    "hl": "en",
                    "gl": "US"
                }
            },
            "isAudioOnly": True,
            "enablePersistentPlaylistPanel": True
        }
        if playlist_id:
            payload["playlistId"] = playlist_id
        if video_id:
            payload["videoId"] = video_id
        if continuation:
            payload["continuation"] = continuation
        if params:
            payload["params"] = params

        headers = self.get_auth_headers()
        ctx = ssl._create_unverified_context()
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass

        return {}

    @staticmethod
    def _extract_continuation_token(data: Dict[str, Any]) -> Optional[str]:
        """Extract pagination continuation token from Innertube next/browse response."""
        if not data or not isinstance(data, dict):
            return None

        def find_token(node):
            if isinstance(node, dict):
                if 'nextRadioContinuationData' in node:
                    return node['nextRadioContinuationData'].get('continuation')
                if 'nextContinuationData' in node:
                    return node['nextContinuationData'].get('continuation')
                if 'reloadContinuationData' in node:
                    return node['reloadContinuationData'].get('continuation')
                if 'continuationCommand' in node:
                    return node['continuationCommand'].get('token')
                if 'continuationEndpoint' in node:
                    return node['continuationEndpoint'].get('continuationCommand', {}).get('token')
                for v in node.values():
                    res = find_token(v)
                    if res:
                        return res
            elif isinstance(node, list):
                for item in node:
                    res = find_token(item)
                    if res:
                        return res
            return None

        return find_token(data)

    @staticmethod
    def _parse_playlist_panel_tracks(data: Dict[str, Any], default_badge: str = "MIX") -> List[Dict[str, Any]]:
        """Extract genuine radio tracks from Innertube v1/next response (playlistPanelRenderer / musicQueueRenderer)."""
        tracks: List[Dict[str, Any]] = []
        seen_vids = set()

        def traverse(node):
            if isinstance(node, dict):
                if 'playlistPanelVideoRenderer' in node:
                    item = node['playlistPanelVideoRenderer']
                    try:
                        vid_id = item.get('videoId', '')
                        title_runs = item.get('title', {}).get('runs', [])
                        title = "".join([r.get('text', '') for r in title_runs]) if title_runs else "Unknown Track"

                        # Extract artist and album from byline
                        sub_runs = item.get('longBylineText', {}).get('runs', []) or item.get('shortBylineText', {}).get('runs', [])
                        artist = "Unknown Artist"
                        album = "Personalized Station"
                        if sub_runs:
                            non_sep = [r.get('text', '') for r in sub_runs if r.get('text') and r.get('text').strip() != '•']
                            if non_sep:
                                artist = non_sep[0]
                            if len(non_sep) > 1:
                                album = non_sep[1]

                        # Duration parsing
                        dur_text = "".join([r.get('text', '') for r in item.get('lengthText', {}).get('runs', [])])
                        duration = 0.0
                        if dur_text and ':' in dur_text:
                            parts = dur_text.split(':')
                            if len(parts) == 2:
                                duration = float(int(parts[0]) * 60 + int(parts[1]))
                            elif len(parts) == 3:
                                duration = float(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]))

                        # Thumbnail extraction
                        thumb_url = ""
                        thumbs = item.get('thumbnail', {}).get('thumbnails', [])
                        if thumbs:
                            thumb_url = thumbs[-1].get('url', '')
                        if not thumb_url and vid_id:
                            thumb_url = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

                        if vid_id and vid_id not in seen_vids:
                            seen_vids.add(vid_id)
                            tracks.append({
                                "id": f"yt_{vid_id}",
                                "video_id": vid_id,
                                "title": title,
                                "artist": artist,
                                "album": album,
                                "duration": duration,
                                "thumbnail_url": thumb_url,
                                "source": "youtube",
                                "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                "badge": "TRACK",
                                "is_stream": True,
                                "is_online": True,
                                "is_playlist": False,
                                "is_single_track": True
                            })
                    except Exception:
                        pass
                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(data)
        return tracks

    def _create_temp_cookiefile(self) -> Optional[str]:
        """Create a temporary Netscape cookies file from authenticated session for yt-dlp."""
        cookies = self.session_data.get("cookies", {})
        if not cookies:
            return None
        try:
            fd, cookie_path = tempfile.mkstemp(suffix='.txt', prefix='helxaid_cookie_')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write('# Netscape HTTP Cookie File\n')
                for k, v in cookies.items():
                    domain = '.youtube.com' if any(x in k for x in ['LOGIN', 'VISITOR', 'SAPISID', 'SID', 'APISID', 'HSID', 'SSID', 'PREF', 'YSC']) else '.google.com'
                    f.write(f'{domain}\tTRUE\t/\tTRUE\t2147483647\t{k}\t{v}\n')
            return cookie_path
        except Exception:
            return None

    def fetch_playlist_tracks(
        self,
        browse_id: str,
        is_radio: bool = False,
        video_id: Optional[str] = None,
        on_first_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_more_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all tracks for a YouTube Music playlist, mix, or radio station with instant memory caching and progressive streaming."""
        if not browse_id:
            return []

        # Sanitize browse_id: strip 'yt_' prefix if present
        clean_id = browse_id[3:] if browse_id.startswith("yt_") else browse_id

        # 0. Check instant memory cache (0ms instant response)
        cached = self.get_cached_playlist_tracks(clean_id)
        if cached:
            if on_first_batch:
                on_first_batch(list(cached))
            return cached

        # If clean_id is an 11-char video ID (e.g. Hcq9RRxQErQ), treat as radio station
        if len(clean_id) == 11 and not clean_id.startswith(("PL", "RD", "VL", "MP", "FE", "LM", "OL")):
            video_id = clean_id
            clean_id = f"RD{clean_id}"
            is_radio = True

        tracks: List[Dict[str, Any]] = []
        is_radio_id = is_radio or clean_id == "RDMM" or clean_id.startswith("RD") or clean_id.startswith("RDTMAK5uy_")

        # 1. Tier 1: Try Innertube v1/next Radio Queue if it's a radio station
        if is_radio_id:
            try:
                vid = video_id or ""
                next_data = self.execute_innertube_next(playlist_id=clean_id, video_id=vid)
                if next_data:
                    tracks = self._parse_playlist_panel_tracks(next_data, default_badge="MIX")
                    if tracks and on_first_batch:
                        on_first_batch(list(tracks))

                    # Paginate via continuation tokens in background
                    cont_token = self._extract_continuation_token(next_data)
                    max_cont_pages = 4
                    while cont_token and max_cont_pages > 0 and len(tracks) < 150:
                        cont_data = self.execute_innertube_next(continuation=cont_token)
                        if not cont_data:
                            break
                        more_tracks = self._parse_playlist_panel_tracks(cont_data, default_badge="MIX")
                        if not more_tracks:
                            break
                        existing_ids = {t["video_id"] for t in tracks}
                        unique_more = []
                        for mt in more_tracks:
                            if mt["video_id"] not in existing_ids:
                                tracks.append(mt)
                                unique_more.append(mt)
                                existing_ids.add(mt["video_id"])
                        if unique_more and on_more_batch:
                            on_more_batch(list(unique_more))
                        cont_token = self._extract_continuation_token(cont_data)
                        max_cont_pages -= 1
            except Exception as e:
                print(f"[YouTubeAccountEngine] Radio v1/next notice: {e}")

        # 2. Tier 1b: Try Innertube Browse with VL prefix
        if not tracks:
            try:
                clean_browse_id = clean_id if clean_id.startswith(("VL", "FE", "PL", "RD", "MP", "OL")) else ("VL" + clean_id)
                data = self.execute_innertube_browse(clean_browse_id)
                if data:
                    tracks = FetchYTLikedMusicWorker._parse_music_tracks(data, default_badge="PLAYLIST")
                    if tracks and on_first_batch:
                        on_first_batch(list(tracks))

                    cont_token = self._extract_continuation_token(data)
                    max_cont_pages = 4
                    while cont_token and max_cont_pages > 0 and len(tracks) < 150:
                        cont_data = self.execute_innertube_browse(continuation=cont_token)
                        if not cont_data:
                            break
                        more_tracks = FetchYTLikedMusicWorker._parse_music_tracks(cont_data, default_badge="PLAYLIST")
                        if not more_tracks:
                            break
                        existing_ids = {t["video_id"] for t in tracks}
                        unique_more = []
                        for mt in more_tracks:
                            if mt["video_id"] not in existing_ids:
                                tracks.append(mt)
                                unique_more.append(mt)
                                existing_ids.add(mt["video_id"])
                        if unique_more and on_more_batch:
                            on_more_batch(list(unique_more))
                        cont_token = self._extract_continuation_token(cont_data)
                        max_cont_pages -= 1

                if not tracks and clean_browse_id != clean_id:
                    data_raw = self.execute_innertube_browse(clean_id)
                    if data_raw:
                        tracks = FetchYTLikedMusicWorker._parse_music_tracks(data_raw, default_badge="PLAYLIST")
                        if tracks and on_first_batch:
                            on_first_batch(list(tracks))
            except Exception as e:
                print(f"[YouTubeAccountEngine] Browse fallback notice: {e}")

        # 3. Tier 2: Authenticated yt-dlp flat extraction with browser cookies or Netscape cookiefile
        if not tracks:
            temp_cf = None
            try:
                import yt_dlp
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': True,
                    'no_warnings': True,
                    'socket_timeout': 5,
                }
                VALID_YTDLP_BROWSERS = {'brave', 'chrome', 'chromium', 'edge', 'firefox', 'opera', 'safari', 'vivaldi', 'whale'}
                browser = (self.session_data.get("browser") or "").lower()
                if browser in VALID_YTDLP_BROWSERS:
                    try:
                        ydl_opts['cookiesfrombrowser'] = (browser,)
                    except Exception:
                        pass
                elif self.session_data.get("cookies"):
                    temp_cf = self._create_temp_cookiefile()
                    if temp_cf:
                        ydl_opts['cookiefile'] = temp_cf

                pl_url = f"https://music.youtube.com/playlist?list={clean_id}"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(pl_url, download=False)
                    if info and 'entries' in info:
                        for entry in info['entries']:
                            if not entry:
                                continue
                            vid_id = entry.get('id', '')
                            title = entry.get('title', 'Unknown Track')
                            artist = entry.get('uploader') or entry.get('artist') or 'YouTube Music'
                            duration = float(entry.get('duration') or 0.0)
                            tracks.append({
                                "id": f"yt_{vid_id}",
                                "video_id": vid_id,
                                "title": title,
                                "artist": artist,
                                "album": "Personalized Station",
                                "duration": duration,
                                "thumbnail_url": f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                                "source": "youtube",
                                "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                "badge": "TRACK",
                                "is_stream": True,
                                "is_online": True,
                                "is_playlist": False,
                                "is_single_track": True
                            })
                        if tracks and on_first_batch:
                            on_first_batch(list(tracks))
            except Exception as e:
                print(f"[YouTubeAccountEngine] yt-dlp playlist extraction notice: {e}")
            finally:
                if temp_cf and os.path.exists(temp_cf):
                    try:
                        os.remove(temp_cf)
                    except Exception:
                        pass

        # Save to memory and persistent disk cache for instant future loads
        if tracks and clean_id:
            self.save_cached_playlist_tracks(clean_id, tracks)

        return tracks


class FetchYTLikedMusicWorker(QThread):
    """Async worker to fetch user's Liked Music tracks with fallback parsing."""
    tracksLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        tracks: List[Dict[str, Any]] = []
        cache_file = os.path.join(self.engine.CACHE_DIR, "yt_liked_music.json")

        try:
            # 1. Try Authenticated Innertube Browse for LM (Liked Music)
            data = self.engine.execute_innertube_browse("FEmusic_liked_videos")
            if not data:
                data = self.engine.execute_innertube_browse("LM")

            tracks = self._parse_music_tracks(data, default_badge="LIKED")

            # 2. Fallback to flat yt-dlp extraction if Innertube browse had alternative schema
            if not tracks and self.engine.is_authenticated():
                temp_cf = None
                try:
                    import yt_dlp
                    ydl_opts = {
                        'quiet': True,
                        'extract_flat': True,
                        'no_warnings': True,
                        'socket_timeout': 5,
                    }
                    VALID_YTDLP_BROWSERS = {'brave', 'chrome', 'chromium', 'edge', 'firefox', 'opera', 'safari', 'vivaldi', 'whale'}
                    browser = (self.engine.session_data.get("browser") or "").lower()
                    if browser in VALID_YTDLP_BROWSERS:
                        ydl_opts['cookiesfrombrowser'] = (browser,)
                    elif self.engine.session_data.get("cookies"):
                        temp_cf = self.engine._create_temp_cookiefile()
                        if temp_cf:
                            ydl_opts['cookiefile'] = temp_cf

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info("https://music.youtube.com/playlist?list=LM", download=False)
                        if info and 'entries' in info:
                            for entry in info['entries']:
                                if not entry:
                                    continue
                                vid_id = entry.get('id', '')
                                title = entry.get('title', 'Unknown Track')
                                artist = entry.get('uploader') or entry.get('artist') or 'YouTube Music'
                                duration = float(entry.get('duration') or 0.0)
                                tracks.append({
                                    "id": f"yt_{vid_id}",
                                    "video_id": vid_id,
                                    "title": title,
                                    "artist": artist,
                                    "album": "Liked Music",
                                    "duration": duration,
                                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                                    "source": "youtube",
                                    "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                    "badge": "TRACK",
                                    "is_stream": True,
                                    "is_online": True,
                                    "is_playlist": False,
                                    "is_single_track": True
                                })
                except Exception as e:
                    print(f"[YouTubeAccountEngine] yt-dlp Liked Music extraction notice: {e}")
                finally:
                    if temp_cf and os.path.exists(temp_cf):
                        try:
                            os.remove(temp_cf)
                        except Exception:
                            pass

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

    @staticmethod
    def _parse_music_tracks(data: Dict[str, Any], default_badge: str = "LIKED") -> List[Dict[str, Any]]:
        tracks: List[Dict[str, Any]] = []

        def traverse(node):
            if isinstance(node, dict):
                if 'musicResponsiveListItemRenderer' in node:
                    item = node['musicResponsiveListItemRenderer']
                    try:
                        nav = item.get('navigationEndpoint', {})
                        watch = nav.get('watchEndpoint', {})
                        vid_id = watch.get('videoId', '')
                        # Fallback for video id
                        if not vid_id:
                            play_nav = item.get('overlay', {}).get('musicItemThumbnailOverlayRenderer', {}).get('content', {}).get('musicPlayButtonRenderer', {}).get('playNavigationEndpoint', {})
                            vid_id = play_nav.get('watchEndpoint', {}).get('videoId', '')

                        flex_cols = item.get('flexColumns', [])
                        title = "Unknown Track"
                        artist = "Unknown Artist"
                        album = "Cloud Playlist"
                        duration = 0.0

                        if len(flex_cols) >= 1:
                            runs = flex_cols[0].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                            if runs:
                                title = runs[0].get('text', title)
                                if not vid_id:
                                    vid_id = runs[0].get('navigationEndpoint', {}).get('watchEndpoint', {}).get('videoId', '')

                        if len(flex_cols) >= 2:
                            artist_runs = flex_cols[1].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                            if artist_runs:
                                artist = artist_runs[0].get('text', artist)

                        # Duration parsing
                        fixed_cols = item.get('fixedColumns', [])
                        if fixed_cols:
                            dur_text = fixed_cols[0].get('musicResponsiveListItemFixedColumnRenderer', {}).get('text', {}).get('runs', [{}])[0].get('text', '')
                            if dur_text and ':' in dur_text:
                                parts = dur_text.split(':')
                                if len(parts) == 2:
                                    duration = float(int(parts[0]) * 60 + int(parts[1]))
                                elif len(parts) == 3:
                                    duration = float(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]))

                        thumb_url = ""
                        thumbs = item.get('thumbnail', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                        if thumbs:
                            thumb_url = thumbs[-1].get('url', '')
                        if not thumb_url and vid_id:
                            thumb_url = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

                        if vid_id:
                            tracks.append({
                                "id": f"yt_{vid_id}",
                                "video_id": vid_id,
                                "title": title,
                                "artist": artist,
                                "album": album,
                                "duration": duration,
                                "thumbnail_url": thumb_url,
                                "source": "youtube",
                                "original_url": f"https://www.youtube.com/watch?v={vid_id}",
                                "badge": "TRACK",
                                "is_stream": True,
                                "is_online": True,
                                "is_playlist": False,
                                "is_single_track": True
                            })
                    except Exception:
                        pass
                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(data)
        return tracks


class FetchYTMixesWorker(QThread):
    """Async worker to fetch personalized algorithmic mixes (Your Mix, Supermix, Discover Mix) from FEmusic_home."""
    mixesLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "yt_mixes.json")
        mixes: List[Dict[str, Any]] = []

        try:
            data = self.engine.execute_innertube_browse("FEmusic_home")
            mixes = self._parse_mixes(data)

            if not mixes:
                mixes = self._get_default_5_mixes()

            # Ensure all mixes have valid high-res cover artwork
            for m in mixes:
                if not m.get("thumbnail_url"):
                    pl_id = m.get("id") or ""
                    vid = m.get("seed_video_id") or ""
                    if vid:
                        m["thumbnail_url"] = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                    elif pl_id:
                        try:
                            t_data = self.engine.execute_innertube_next(playlist_id=pl_id)
                            if t_data:
                                t_tracks = self.engine._parse_playlist_panel_tracks(t_data)
                                if t_tracks and t_tracks[0].get("thumbnail_url"):
                                    m["thumbnail_url"] = t_tracks[0]["thumbnail_url"]
                                    if not m.get("seed_video_id") and t_tracks[0].get("video_id"):
                                        m["seed_video_id"] = t_tracks[0]["video_id"]
                        except Exception:
                            pass

            if mixes:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(mixes, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            if not self._is_cancelled:
                self.mixesLoaded.emit(mixes)
        except Exception as e:
            if not self._is_cancelled:
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            mixes = json.load(f)
                        self.mixesLoaded.emit(mixes)
                        return
                    except Exception:
                        pass
                self.mixesLoaded.emit(self._get_default_5_mixes())

    def _get_default_5_mixes(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "RDMM",
                "title": "My Supermix",
                "description": "Endless personalized mix of your favorite tracks and top hits",
                "track_count": 50,
                "thumbnail_url": "https://i.ytimg.com/vi/4NRXx6U8ABQ/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "SUPERMIX"
            },
            {
                "id": "VLRDCLAK5uy_n4jtH1BoYT7FxNFJAGmJw5WQFF_ZzBTBM",
                "title": "Indo Indie On Repeat",
                "description": "Bernadya, Hindia, Nadin Amizah, idgitaf",
                "track_count": 89,
                "thumbnail_url": "https://i.ytimg.com/vi/36YnV9STBqc/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "MIX"
            },
            {
                "id": "VLRDCLAK5uy_lgUiRZLoEefwv4IdQBJfoXEgHiSKXctEM",
                "title": "Indo Indie",
                "description": "Aku Jeje, Batas Senja, idgitaf, Feby Putri",
                "track_count": 100,
                "thumbnail_url": "https://i.ytimg.com/vi/4xDzrJKXOOY/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "MIX"
            },
            {
                "id": "VLRDCLAK5uy_m0wlRoNn5iCTTgBedfoOQ19Jq9P3XTLIA",
                "title": "Feel-Good Pop & Rock",
                "description": "Ed Sheeran, Imagine Dragons, 5 Seconds of Summer, HAIM",
                "track_count": 100,
                "thumbnail_url": "https://i.ytimg.com/vi/60ItHLz5WEA/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "MIX"
            },
            {
                "id": "VLRDCLAK5uy_mX4JK0m7lhZ8Egv1E7bbXox_e0k6rGejo",
                "title": "Chill R&B",
                "description": "Ariana Grande, Drake, Bruno Mars, Jason Derulo",
                "track_count": 100,
                "thumbnail_url": "https://i.ytimg.com/vi/sPxXiXucYcM/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "CHILL"
            }
        ]

    def _parse_mixes(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        mixes: List[Dict[str, Any]] = []
        seen_ids = set()

        PERSONAL_KEYWORDS = ["mixed for you", "made for you", "listen again", "similar to", "quick picks", "my mix", "supermix", "favorit saya", "discover", "replay", "radar", "chill", "focus", "energy", "favorites", "kemarau chill"]
        EXCLUDE_SHELVES = ["trending community playlists", "charts", "top music videos"]

        def traverse_shelves(node, current_shelf_title=""):
            if isinstance(node, dict):
                if 'musicCarouselShelfRenderer' in node:
                    shelf = node['musicCarouselShelfRenderer']
                    header = shelf.get('header', {})
                    shelf_title = "".join([run.get("text", "") for run in header.get("musicCarouselShelfBasicHeaderRenderer", {}).get("title", {}).get("runs", [])]).lower()
                    for item in shelf.get('contents', []):
                        traverse_shelves(item, shelf_title)
                    return

                if 'musicTwoRowItemRenderer' in node:
                    item = node['musicTwoRowItemRenderer']
                    nav_ep = item.get('navigationEndpoint', {})
                    watch_ep = nav_ep.get('watchEndpoint', {})
                    playlist_id = watch_ep.get('playlistId', '') or nav_ep.get('browseEndpoint', {}).get('browseId', '')
                    seed_video_id = watch_ep.get('videoId', '')

                    title = ""
                    title_runs = item.get('title', {}).get('runs', [])
                    if title_runs:
                        title = title_runs[0].get('text', '')

                    subtitle = ""
                    sub_runs = item.get('subtitle', {}).get('runs', [])
                    if sub_runs:
                        subtitle = " • ".join([r.get('text', '') for r in sub_runs if r.get('text')])

                    thumb_url = ""
                    thumbs = item.get('thumbnailRenderer', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                    if thumbs:
                        thumb_url = thumbs[-1].get('url', '')

                    t_low = title.lower()
                    is_excluded = any(ex in current_shelf_title for ex in EXCLUDE_SHELVES)
                    is_personal_shelf = any(pk in current_shelf_title for pk in PERSONAL_KEYWORDS)
                    is_algo_id = playlist_id.startswith("RDTMAK5uy_") or playlist_id.startswith("RDCLAK5uy_") or playlist_id.startswith("VLRDCLAK5uy_") or playlist_id.startswith("RD")
                    is_algo_title = any(pk in t_low for pk in ["supermix", "favorit saya", "my mix", "discover", "chill", "focus", "energy", "replay", "radio", "indie", "pop", "r&b", "kemarau"])

                    if playlist_id and title and playlist_id not in seen_ids:
                        if (is_personal_shelf or is_algo_id or is_algo_title) and not (is_excluded and not (is_algo_id or is_algo_title)):
                            seen_ids.add(playlist_id)
                            badge = "MIX"
                            if "supermix" in t_low or "favorit saya" in t_low or "my mix" in t_low:
                                badge = "SUPERMIX"
                            elif "discover" in t_low:
                                badge = "DISCOVER"
                            elif "chill" in t_low or "focus" in t_low or "kemarau" in t_low or "r&b" in t_low:
                                badge = "CHILL"
                            elif "energy" in t_low or "rock" in t_low:
                                badge = "ENERGY"
                            elif "replay" in t_low or "repeat" in t_low:
                                badge = "REPLAY"

                            mixes.append({
                                "id": playlist_id,
                                "title": title,
                                "description": subtitle or "Personalized YouTube Music Station",
                                "track_count": 50,
                                "thumbnail_url": thumb_url,
                                "source": "youtube",
                                "is_algorithmic": True,
                                "badge": badge,
                                "seed_video_id": seed_video_id
                            })
                for v in node.values():
                    traverse_shelves(v, current_shelf_title)
            elif isinstance(node, list):
                for item in node:
                    traverse_shelves(item, current_shelf_title)

        traverse_shelves(data)

        defaults = self._get_default_5_mixes()
        final_list = []

        # Slot 1 is always the official YouTube Music RDMM station (My Supermix / Mix Favorit Saya)
        # Use the REAL dynamic ID + seed_video_id from the live API response if available
        supermix_card = dict(defaults[0])
        for m in mixes:
            if m.get("badge") == "SUPERMIX" or "favorit saya" in m.get("title", "").lower() or "supermix" in m.get("title", "").lower() or "my mix" in m.get("title", "").lower():
                supermix_card["id"] = m.get("id") or supermix_card["id"]
                supermix_card["title"] = m.get("title") or supermix_card["title"]
                supermix_card["description"] = m.get("description") or supermix_card["description"]
                if m.get("thumbnail_url"):
                    supermix_card["thumbnail_url"] = m["thumbnail_url"]
                if m.get("seed_video_id"):
                    supermix_card["seed_video_id"] = m["seed_video_id"]
                break
        final_list.append(supermix_card)

        # Slots 2 through 5: Genuine live mood/genre mix stations from FEmusic_home (Indo Indie, Chill R&B, etc.)
        for m in mixes:
            if m.get("id") and m.get("id") != "RDMM" and m.get("id") not in [x.get("id") for x in final_list]:
                final_list.append(m)
                if len(final_list) >= 5:
                    break

        # If less than 5 live mixes found, fill with fallback defaults
        idx = 1
        while len(final_list) < 5 and idx < len(defaults):
            if defaults[idx].get("id") not in [x.get("id") for x in final_list]:
                final_list.append(defaults[idx])
            idx += 1

        return final_list[:5]


class FetchYTPlaylistsWorker(QThread):
    """Async worker to fetch user's saved & created playlists from FEmusic_library_playlists."""
    playlistsLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "yt_playlists.json")
        playlists: List[Dict[str, Any]] = []

        try:
            # Try modern YouTube Music library landing first, then fallback endpoints
            data = self.engine.execute_innertube_browse("FEmusic_library_landing")
            playlists = self._parse_playlists(data) if data else []

            if not playlists:
                data2 = self.engine.execute_innertube_browse("FEmusic_liked_videos")
                if data2:
                    playlists = self._parse_playlists(data2)

            if not playlists:
                data3 = self.engine.execute_innertube_browse("FEmusic_library_playlists")
                if data3:
                    playlists = self._parse_playlists(data3)

            # Prepend Liked Music auto-playlist
            liked_music_item = {
                "id": "LM",
                "title": "Liked Music",
                "description": "Auto-Playlist • All your liked tracks",
                "track_count": 50,
                "thumbnail_url": "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png",
                "source": "youtube",
                "is_algorithmic": False,
                "badge": "LIKED"
            }
            has_lm = any(p.get("id") in ("LM", "FEmusic_liked_videos", "VLLM") for p in playlists)
            if not has_lm:
                playlists.insert(0, liked_music_item)

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

    def _parse_playlists(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        playlists: List[Dict[str, Any]] = []
        seen_ids = set()

        def traverse(node):
            if isinstance(node, dict):
                # 1. Two Row Renderer
                if 'musicTwoRowItemRenderer' in node:
                    item = node['musicTwoRowItemRenderer']
                    nav_ep = item.get('navigationEndpoint', {})
                    browse_id = nav_ep.get('browseEndpoint', {}).get('browseId', '') or nav_ep.get('watchPlaylistEndpoint', {}).get('playlistId', '')
                    title = ""
                    title_runs = item.get('title', {}).get('runs', [])
                    if title_runs:
                        title = title_runs[0].get('text', '')

                    subtitle = ""
                    sub_runs = item.get('subtitle', {}).get('runs', [])
                    if sub_runs:
                        subtitle = " • ".join([r.get('text', '') for r in sub_runs if r.get('text')])

                    thumb_url = ""
                    thumbs = item.get('thumbnailRenderer', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                    if thumbs:
                        thumb_url = thumbs[-1].get('url', '')

                    if browse_id and title and browse_id not in seen_ids and browse_id != "FEplaylist_aggregation":
                        seen_ids.add(browse_id)
                        playlists.append({
                            "id": browse_id,
                            "title": title,
                            "description": subtitle or "User Playlist",
                            "track_count": 0,
                            "thumbnail_url": thumb_url,
                            "source": "youtube",
                            "is_algorithmic": False,
                            "badge": "PLAYLIST"
                        })
                # 2. Responsive List Item Renderer
                elif 'musicResponsiveListItemRenderer' in node:
                    item = node['musicResponsiveListItemRenderer']
                    nav_ep = item.get('navigationEndpoint', {})
                    browse_id = nav_ep.get('browseEndpoint', {}).get('browseId', '') or nav_ep.get('watchPlaylistEndpoint', {}).get('playlistId', '')
                    flex_cols = item.get('flexColumns', [])
                    title = ""
                    if flex_cols:
                        runs = flex_cols[0].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                        if runs:
                            title = runs[0].get('text', '')
                    subtitle = ""
                    if len(flex_cols) > 1:
                        runs = flex_cols[1].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                        if runs:
                            subtitle = " • ".join([r.get('text', '') for r in runs if r.get('text')])
                    thumb_url = ""
                    thumbs = item.get('thumbnail', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                    if thumbs:
                        thumb_url = thumbs[-1].get('url', '')

                    if browse_id and title and browse_id not in seen_ids and browse_id != "FEplaylist_aggregation":
                        seen_ids.add(browse_id)
                        playlists.append({
                            "id": browse_id,
                            "title": title,
                            "description": subtitle or "User Playlist",
                            "track_count": 0,
                            "thumbnail_url": thumb_url,
                            "source": "youtube",
                            "is_algorithmic": False,
                            "badge": "PLAYLIST"
                        })

                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(data)
        return playlists


class SyncYTCookiesWorker(QThread):
    """Asynchronous background worker to extract browser cookies without locking UI."""
    syncCompleted = Signal(bool, str, str)  # (success, message, detected_browser)

    def __init__(self, browser_name: str = "auto", profile_dir: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.browser_name = browser_name
        self.profile_dir = profile_dir
        self.engine = YouTubeAccountEngine.get_instance()

    def run(self):
        ok, msg, detected_b = self.engine.sync_from_browser(self.browser_name, self.profile_dir)
        self.syncCompleted.emit(ok, msg, detected_b)


