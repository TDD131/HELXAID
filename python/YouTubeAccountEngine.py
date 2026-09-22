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
import re
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
# Dynamically resolve AES cipher (Cryptodome / Crypto) to avoid static IDE unresolved import warnings
AES = None
try:
    import importlib
    for _pkg in ("Cryptodome.Cipher.AES", "Crypto.Cipher.AES"):
        try:
            _mod = importlib.import_module(_pkg)
            AES = getattr(_mod, "AES", _mod)
            if AES is not None:
                break
        except Exception:
            continue
except Exception:
    AES = None
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any, Optional, Tuple, Callable
from PySide6.QtCore import QObject, Signal, QThread, QSettings, QTimer


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REDIRECT_URI = "http://127.0.0.1:8888/callback"
GOOGLE_YOUTUBE_SCOPES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube"


class YouTubeSyncLoopbackHandler(BaseHTTPRequestHandler):
    """Handles Chrome Extension sync and status checks for YouTube session."""

    def log_message(self, format, *args):
        # Suppress noisy standard HTTP logs
        return

    def do_OPTIONS(self):
        """CORS Preflight handler for Chrome Extension."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # 1. Health check endpoint for Chrome Extension
        if parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            is_yt = False
            user_name = ""
            try:
                yt = YouTubeAccountEngine.get_instance()
                yt.reload_session()
                is_yt = yt.is_authenticated()
                user_name = yt.get_user_name() if is_yt else ""
            except Exception:
                pass
            res_obj = {
                "status": "ok",
                "app": "HELXAID",
                "version": "1.0.0",
                "youtube_synced": is_yt,
                "user_name": user_name
            }
            self.wfile.write(json.dumps(res_obj).encode("utf-8"))
            return

        # 1b. Disconnect endpoint for extension
        if parsed.path == "/api/disconnect_youtube":
            try:
                YouTubeAccountEngine.get_instance().disconnect()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"success":true,"message":"Disconnected YouTube session"}')
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # 2. Chrome Extension Cookie Sync endpoint
        if parsed.path == "/api/sync_cookies":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8"))
                cookies = data.get("cookies", {})
                browser = data.get("browser", "Chrome Extension")
                
                if cookies and isinstance(cookies, dict):
                    account_name = (data.get("account_name") or data.get("user_name") or "").strip()
                    email = (data.get("email") or "").strip()
                    if account_name and email:
                        user_name = f"{account_name} ({email})"
                    elif account_name:
                        user_name = account_name
                    elif email:
                        user_name = email
                    else:
                        user_name = f"Google / YouTube User ({browser})"

                    yt_eng = YouTubeAccountEngine.get_instance()
                    ok, msg = yt_eng.import_cookies_dict(cookies, user_name)
                    if ok:
                        yt_eng.fetch_account_info(async_call=True)
                        yt_eng.cookiesReceived.emit(cookies)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "success": True,
                            "message": "YouTube Music session synchronized to HELXAID!",
                            "user_name": yt_eng.get_user_name()
                        }).encode("utf-8"))
                        return
            except Exception as e:
                print(f"[YouTubeSyncServer] Error processing cookies: {e}")

            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"success":false,"message":"Failed to import YouTube cookies"}')
            return

        self.send_response(404)
        self.end_headers()


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


def _bcrypt_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> Optional[bytes]:
    """
    Decrypt AES-256-GCM using Windows native CNG (bcrypt.dll).
    Zero external dependencies required (built into Windows 10/11).
    """
    try:
        import ctypes
        from ctypes import wintypes

        bcrypt = ctypes.WinDLL("bcrypt.dll")

        BCRYPT_AES_ALGORITHM = "AES"
        BCRYPT_CHAINING_MODE = "ChainingMode"
        BCRYPT_CHAIN_MODE_GCM = "ChainingModeGCM"
        BCRYPT_AUTH_MODE_INFO_VERSION = 1

        class BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("dwInfoVersion", wintypes.ULONG),
                ("pbNonce", ctypes.c_void_p),
                ("cbNonce", wintypes.ULONG),
                ("pbAuthData", ctypes.c_void_p),
                ("cbAuthData", wintypes.ULONG),
                ("pbTag", ctypes.c_void_p),
                ("cbTag", wintypes.ULONG),
                ("pbMacContext", ctypes.c_void_p),
                ("cbMacContext", wintypes.ULONG),
                ("cbAAD", wintypes.ULONG),
                ("cbData", ctypes.c_ulonglong),
                ("dwFlags", wintypes.ULONG),
            ]

        hAlg = wintypes.HANDLE()
        hKey = wintypes.HANDLE()

        # Open AES provider
        if bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(hAlg), ctypes.c_wchar_p(BCRYPT_AES_ALGORITHM), None, 0) != 0:
            return None

        try:
            # Set chaining mode to GCM
            chain_mode_buf = ctypes.create_unicode_buffer(BCRYPT_CHAIN_MODE_GCM)
            if bcrypt.BCryptSetProperty(
                hAlg,
                ctypes.c_wchar_p(BCRYPT_CHAINING_MODE),
                ctypes.cast(chain_mode_buf, ctypes.c_char_p),
                ctypes.sizeof(chain_mode_buf),
                0
            ) != 0:
                return None

            # Generate symmetric key
            key_buf = (ctypes.c_ubyte * len(key)).from_buffer_copy(key)
            if bcrypt.BCryptGenerateSymmetricKey(hAlg, ctypes.byref(hKey), None, 0, key_buf, len(key), 0) != 0:
                return None

            try:
                # Setup authenticated cipher mode info
                nonce_buf = (ctypes.c_ubyte * len(nonce)).from_buffer_copy(nonce)
                tag_buf = (ctypes.c_ubyte * len(tag)).from_buffer_copy(tag)

                auth_info = BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
                auth_info.cbSize = ctypes.sizeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
                auth_info.dwInfoVersion = BCRYPT_AUTH_MODE_INFO_VERSION
                auth_info.pbNonce = ctypes.cast(nonce_buf, ctypes.c_void_p)
                auth_info.cbNonce = len(nonce)
                auth_info.pbTag = ctypes.cast(tag_buf, ctypes.c_void_p)
                auth_info.cbTag = len(tag)

                cipher_buf = (ctypes.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
                plain_buf = (ctypes.c_ubyte * len(ciphertext))()
                cbResult = wintypes.ULONG(0)

                status = bcrypt.BCryptDecrypt(
                    hKey,
                    cipher_buf,
                    len(ciphertext),
                    ctypes.byref(auth_info),
                    None,
                    0,
                    plain_buf,
                    len(ciphertext),
                    ctypes.byref(cbResult),
                    0
                )
                if status == 0:
                    return bytes(plain_buf[:cbResult.value])
            finally:
                bcrypt.BCryptDestroyKey(hKey)
        finally:
            bcrypt.BCryptCloseAlgorithmProvider(hAlg, 0)
    except Exception:
        pass
    return None


def _decrypt_chromium_cookie_val(enc_val: bytes, aes_key: Optional[bytes] = None) -> Optional[str]:
    """
    Decrypts Chromium cookie value supporting both v10/v11 AES-256-GCM and legacy DPAPI.
    Uses dynamic Cryptodome/Crypto, dynamic cryptography, or Windows native BCrypt fallback.
    """
    if not enc_val:
        return None

    # Modern Chromium v10 / v11 AES-GCM
    if aes_key and len(enc_val) >= 31 and (enc_val.startswith(b'v10') or enc_val.startswith(b'v11')):
        nonce = enc_val[3:15]
        ciphertext = enc_val[15:-16]
        tag = enc_val[-16:]

        # 1. Cryptodome (standard in HELXAID) or Crypto (resolved dynamically to avoid static IDE unresolved import warnings)
        global AES
        if AES is None:
            try:
                import importlib
                for _pkg in ("Cryptodome.Cipher.AES", "Crypto.Cipher.AES"):
                    try:
                        _mod = importlib.import_module(_pkg)
                        AES = getattr(_mod, "AES", _mod)
                        if AES is not None:
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if AES is not None:
            try:
                cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
                dec = cipher.decrypt(ciphertext)
                if dec:
                    return dec.decode('utf-8', errors='ignore')
            except Exception:
                pass

        # 2. Dynamic cryptography fallback (imported dynamically to avoid static IDE unresolved import warnings)
        try:
            import importlib
            mod = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
            aesgcm_cls = getattr(mod, "AESGCM", None)
            if aesgcm_cls:
                aesgcm = aesgcm_cls(aes_key)
                dec = aesgcm.decrypt(nonce, enc_val[15:], None)
                if dec:
                    return dec.decode('utf-8', errors='ignore')
        except Exception:
            pass

        # 3. Windows Native CNG (bcrypt.dll) fallback (Zero external dependencies)
        try:
            dec_bytes = _bcrypt_gcm_decrypt(aes_key, nonce, ciphertext, tag)
            if dec_bytes:
                return dec_bytes.decode('utf-8', errors='ignore')
        except Exception:
            pass

    # Legacy DPAPI decryption
    dec_bytes = _dpapi_decrypt(enc_val)
    if dec_bytes:
        try:
            return dec_bytes.decode('utf-8', errors='ignore')
        except Exception:
            pass

    # Plaintext fallback
    try:
        dec_str = enc_val.decode('utf-8')
        if all(ord(c) < 128 or ord(c) > 31 for c in dec_str):
            return dec_str
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
    accountDetailsUpdated = Signal(dict)  # (session_data)
    errorOccurred = Signal(str)
    cookiesReceived = Signal(dict)

    CACHE_DIR = os.path.join(os.getenv("APPDATA", ""), "HELXAID", "cloud_cache")
    _instance: Optional['YouTubeAccountEngine'] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("TDD131", "HELXAID")
        self.session_data: Dict[str, Any] = self._load_persisted_session()
        self.current_verifier: Optional[str] = None
        self.current_state: Optional[str] = None
        self._playlist_tracks_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._account_fetch_lock = threading.Lock()
        self._daemon_server: Optional[HTTPServer] = None
        self._daemon_thread: Optional[threading.Thread] = None
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        # Start persistent local sync server for Chrome Extension on port 8889
        self._start_sync_daemon()

        if self.is_authenticated():
            # If account metadata is missing or still uses generic placeholder, resolve in background
            if not self.session_data.get("account_name") or "Google / YouTube User" in self.session_data.get("user_name", ""):
                QTimer.singleShot(500, lambda: self.fetch_account_info(async_call=True))

    def reload_session(self):
        """Reload session from persistent storage."""
        self.session_data = self._load_persisted_session()

    def _start_sync_daemon(self, port: int = 8889):
        """Start the persistent local sync daemon server on http://127.0.0.1:8889 for Chrome Extension."""
        try:
            class ReusableHTTPServer(HTTPServer):
                allow_reuse_address = True

            self._daemon_server = ReusableHTTPServer(("127.0.0.1", port), YouTubeSyncLoopbackHandler)
            self._daemon_thread = threading.Thread(target=self._daemon_server.serve_forever, daemon=True, name="YouTubeSyncDaemon")
            self._daemon_thread.start()
            print(f"[YouTubeAccountEngine] Local sync server active on http://127.0.0.1:{port}")
        except Exception as e:
            print(f"[YouTubeAccountEngine] Daemon server notice: {e}")

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
                # Auto-heal account metadata if missing or generic
                if self.is_authenticated():
                    if not self.session_data.get("account_name") or "Google / YouTube User" in self.session_data.get("user_name", ""):
                        self.fetch_account_info(async_call=True)
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

    def get_account_name(self) -> str:
        """Return the resolved user or channel name."""
        return self.session_data.get("account_name", "")

    def get_account_email(self) -> str:
        """Return the resolved Google account email if available."""
        return self.session_data.get("email", "")

    def get_account_handle(self) -> str:
        """Return the resolved YouTube channel handle (e.g. @username) if available."""
        return self.session_data.get("handle", "")

    def get_account_display_str(self) -> str:
        """Return a formatted account string: 'Name (@handle • email)' or best available combination."""
        acc_name = (self.session_data.get("account_name") or "").strip()
        email = (self.session_data.get("email") or "").strip()
        handle = (self.session_data.get("handle") or "").strip()

        # Clean generic placeholder names
        if acc_name in ("Google / YouTube User", "YouTube Music User", "YouTube User"):
            acc_name = ""

        parts = []
        if acc_name:
            parts.append(acc_name)
        if handle:
            h_str = handle if handle.startswith("@") else f"@{handle}"
            if h_str != acc_name:
                parts.append(h_str)
        if email:
            parts.append(f"({email})" if parts else email)

        if parts:
            return " ".join(parts)
        return self.get_user_name()

    def fetch_account_info(self, async_call: bool = True) -> None:
        """
        Resolve genuine YouTube/Google account metadata (Channel Name, Email, Handle, Avatar)
        via YouTube Innertube API and local browser profile discovery.
        """
        if not self.is_authenticated():
            return

        if async_call:
            threading.Thread(target=self._fetch_account_info_sync, daemon=True).start()
        else:
            self._fetch_account_info_sync()

    def _fetch_account_info_sync(self) -> None:
        """Background worker to extract genuine account name, handle, and email."""
        if not self.is_authenticated():
            return

        with self._account_fetch_lock:
            if not self.is_authenticated():
                return
            try:
                acc_name = (self.session_data.get("account_name") or "").strip()
                email = ""
                handle = (self.session_data.get("handle") or "").strip()
                avatar_url = (self.session_data.get("avatar_url") or "").strip()

                if acc_name in ("Google / YouTube User", "YouTube Music User", "YouTube User"):
                    acc_name = ""

                # 1. Tier 1: Authoritative Innertube account_menu API (Direct from YouTube Session)
                try:
                    headers = self.get_auth_headers(origin="https://music.youtube.com")
                    if headers.get("Authorization") or headers.get("Cookie"):
                        clients = [
                            ("https://music.youtube.com/youtubei/v1/account/account_menu?prettyPrint=false", "WEB_REMIX", "1.20240901.01.00", "https://music.youtube.com"),
                            ("https://www.youtube.com/youtubei/v1/account/account_menu?prettyPrint=false", "WEB", "2.20240901.01.00", "https://www.youtube.com")
                        ]
                        for endpoint, c_name, c_ver, orig in clients:
                            try:
                                auth_h = self.get_auth_headers(origin=orig)
                                payload = {
                                    "context": {
                                        "client": {
                                            "clientName": c_name,
                                            "clientVersion": c_ver,
                                            "hl": "en",
                                            "gl": "US"
                                        }
                                    }
                                }
                                ctx = ssl._create_unverified_context()
                                req = urllib.request.Request(
                                    endpoint,
                                    data=json.dumps(payload).encode("utf-8"),
                                    headers=auth_h,
                                    method="POST"
                                )
                                with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                                    if resp.status == 200:
                                        res_json = json.loads(resp.read().decode("utf-8"))
                                        
                                        def _find_active_header(node):
                                            if isinstance(node, dict):
                                                if "activeAccountHeaderRenderer" in node:
                                                    return node["activeAccountHeaderRenderer"]
                                                for v in node.values():
                                                    res = _find_active_header(v)
                                                    if res:
                                                        return res
                                            elif isinstance(node, list):
                                                for item in node:
                                                    res = _find_active_header(item)
                                                    if res:
                                                        return res
                                            return None

                                        hdr = _find_active_header(res_json)
                                        if hdr:
                                            def _extract_text(obj):
                                                if not obj or not isinstance(obj, dict):
                                                    return ""
                                                if "simpleText" in obj:
                                                    return str(obj["simpleText"]).strip()
                                                runs = obj.get("runs", [])
                                                if runs and isinstance(runs, list):
                                                    return "".join([r.get("text", "") for r in runs if isinstance(r, dict)]).strip()
                                                return ""

                                            yt_name = _extract_text(hdr.get("accountName"))
                                            yt_handle = _extract_text(hdr.get("channelHandle"))
                                            yt_email = _extract_text(hdr.get("email"))

                                            if yt_name:
                                                acc_name = yt_name
                                            if yt_handle:
                                                handle = yt_handle
                                            if yt_email and "@" in yt_email:
                                                email = yt_email

                                            thumbs = hdr.get("accountPhoto", {}).get("thumbnails", [])
                                            if thumbs and isinstance(thumbs, list):
                                                avatar_url = thumbs[-1].get("url", "")

                                            if acc_name or handle:
                                                break
                            except Exception:
                                continue
                except Exception as api_err:
                    print(f"[YouTubeAccountEngine] Account menu API notice: {api_err}")

                # 2. Tier 2: Local browser profile inspection - ONLY if profile strictly matches the account
                if not email and acc_name:
                    try:
                        profiles = self.get_discovered_browser_profiles()
                        clean_acc = acc_name.lower().strip()
                        clean_handle = handle.replace("@", "").lower().strip()
                        for prof in profiles:
                            p_name = (prof.get("name") or "").lower().strip()
                            p_email = (prof.get("email") or "").lower().strip()
                            # Strict match check: profile name or email username must match acc_name or channel handle
                            if (clean_acc and clean_acc == p_name) or (clean_handle and clean_handle in p_email):
                                email = prof.get("email", "").strip()
                                break
                    except Exception as prof_err:
                        print(f"[YouTubeAccountEngine] Local profile strict match notice: {prof_err}")

                # 3. Save resolved account data if any information was identified
                if acc_name or handle or email:
                    display_parts = []
                    if acc_name:
                        display_parts.append(acc_name)
                    if handle and handle != acc_name:
                        display_parts.append(handle if handle.startswith("@") else f"@{handle}")
                    if email:
                        display_parts.append(f"({email})")

                    best_user_name = " ".join(display_parts) if display_parts else (acc_name or self.get_user_name())

                    self.session_data["user_name"] = best_user_name
                    self.session_data["account_name"] = acc_name
                    self.session_data["email"] = email
                    self.session_data["handle"] = handle
                    if avatar_url:
                        self.session_data["avatar_url"] = avatar_url

                    # Abort if user logged out or session invalidated while network call was in flight
                    if not self.is_authenticated():
                        print("[YouTubeAccountEngine] Session invalidated during fetch_account_info; aborting save.")
                        return

                    self._save_session_data(self.session_data)
                    self.sessionChanged.emit(True, best_user_name)
                    self.accountDetailsUpdated.emit(self.session_data)
                    print(f"[YouTubeAccountEngine] Account metadata successfully resolved: name='{acc_name}', handle='{handle}', email='{email}'")
            except Exception as e:
                print(f"[YouTubeAccountEngine] fetch_account_info notice: {e}")

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
        self.fetch_account_info(async_call=True)
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
                    elif enc_val:
                        dec = _decrypt_chromium_cookie_val(enc_val, aes_key)
                        if dec:
                            cookies[name] = dec
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
                self.fetch_account_info(async_call=True)
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
            self.fetch_account_info(async_call=True)
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
            self.fetch_account_info(async_call=True)
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
            self.fetch_account_info(async_call=True)
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

    def get_auth_headers(self, origin: str = "https://music.youtube.com") -> Dict[str, str]:
        """Generate official YouTube SAPISIDHASH or Bearer Authorization Headers for Innertube."""
        client_name = "1" if "www.youtube.com" in origin else "67"
        client_version = "2.20240901.01.00" if "www.youtube.com" in origin else "1.20240901.01.00"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "X-YouTube-Client-Name": client_name,
            "X-YouTube-Client-Version": client_version,
            "X-Origin": origin,
            "Origin": origin,
            "Referer": f"{origin}/",
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

        if continuation:
            endpoint = f"https://music.youtube.com/youtubei/v1/browse?continuation={urllib.parse.quote(continuation)}&ctoken={urllib.parse.quote(continuation)}&prettyPrint=false"
        else:
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
        if len(clean_id) == 11 and not clean_id.startswith(("PL", "RD", "VL", "MP", "FE", "LM", "OL", "UC")):
            video_id = clean_id
            clean_id = f"RD{clean_id}"
            is_radio = True

        tracks: List[Dict[str, Any]] = []

        # Tier 0: Artist Channel Radio & Discography Handling (UC...)
        if clean_id.startswith("UC"):
            try:
                # 1. Try artist radio queue (RDEM + channel_id)
                next_data = self.execute_innertube_next(playlist_id=f"RDEM{clean_id}")
                if next_data:
                    tracks = self._parse_playlist_panel_tracks(next_data, default_badge="ARTIST MIX")
                    if tracks and on_first_batch:
                        on_first_batch(list(tracks))
            except Exception:
                pass

            if not tracks:
                try:
                    data_raw = self.execute_innertube_browse(clean_id)
                    if data_raw:
                        tracks = FetchYTLikedMusicWorker._parse_music_tracks(data_raw, default_badge="TRACK")
                        if tracks and on_first_batch:
                            on_first_batch(list(tracks))
                except Exception:
                    pass

        # Tier 0b: Liked Music Handling (LM / VLLM / FEmusic_liked_videos)
        elif clean_id in ("LM", "VLLM", "FEmusic_liked_videos"):
            try:
                data_lm = self.execute_innertube_browse("FEmusic_liked_videos") or self.execute_innertube_browse("VLLM")
                if data_lm:
                    tracks = FetchYTLikedMusicWorker._parse_music_tracks(data_lm, default_badge="FAVORITES")
                    if tracks and on_first_batch:
                        on_first_batch(list(tracks))
            except Exception:
                pass

        is_radio_id = is_radio or clean_id == "RDMM" or clean_id.startswith("RD") or clean_id.startswith("RDTMAK5uy_")

        # 1. Tier 1: Try Innertube v1/next Radio Queue if it's a radio station
        if not tracks and is_radio_id:
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
            # 1. First fetch directly from FEmusic_mixed_for_you (contains the complete algorithmic mixes)
            data = self.engine.execute_innertube_browse("FEmusic_mixed_for_you")
            if data:
                mixes = self._parse_mixes(data)

            # 2. Fallback to FEmusic_home if empty
            if not mixes:
                home_data = self.engine.execute_innertube_browse("FEmusic_home")
                if home_data:
                    mixes = self._parse_mixes(home_data)
                    if not mixes:
                        tok = self.engine._extract_continuation_token(home_data)
                        if tok:
                            c_data = self.engine.execute_innertube_browse(continuation=tok)
                            if c_data:
                                mixes = self._parse_mixes(c_data)

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
                "title": "Replay Mix",
                "description": "Your favorite tracks on repeat",
                "track_count": 50,
                "thumbnail_url": "https://i.ytimg.com/vi/36YnV9STBqc/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "REPLAY"
            },
            {
                "id": "VLRDCLAK5uy_m0wlRoNn5iCTTgBedfoOQ19Jq9P3XTLIA",
                "title": "New Release Mix",
                "description": "Fresh tracks from your favorite artists",
                "track_count": 50,
                "thumbnail_url": "https://i.ytimg.com/vi/60ItHLz5WEA/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "NEW RELEASE"
            },
            {
                "id": "VLRDCLAK5uy_lgUiRZLoEefwv4IdQBJfoXEgHiSKXctEM",
                "title": "My Mix 1",
                "description": "Personalized mix curated for you",
                "track_count": 50,
                "thumbnail_url": "https://i.ytimg.com/vi/4xDzrJKXOOY/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "MY MIX 1"
            },
            {
                "id": "VLRDCLAK5uy_mX4JK0m7lhZ8Egv1E7bbXox_e0k6rGejo",
                "title": "My Mix 2",
                "description": "Personalized mix curated for you",
                "track_count": 50,
                "thumbnail_url": "https://i.ytimg.com/vi/sPxXiXucYcM/hqdefault.jpg",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "MY MIX 2"
            }
        ]

    def _parse_mixes(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        bucket_supermix: Optional[Dict[str, Any]] = None
        bucket_replay: List[Dict[str, Any]] = []
        bucket_new_release: List[Dict[str, Any]] = []
        bucket_my_mixes: List[Tuple[int, Dict[str, Any]]] = []
        seen_ids = set()

        def traverse(node):
            nonlocal bucket_supermix
            if isinstance(node, dict):
                if 'musicTwoRowItemRenderer' in node:
                    item = node['musicTwoRowItemRenderer']
                    t_runs = item.get('title', {}).get('runs', [])
                    title = "".join([x.get('text', '') for x in t_runs]).strip()
                    s_runs = item.get('subtitle', {}).get('runs', [])
                    subtitle = " • ".join([x.get('text', '') for x in s_runs]).strip()
                    nav = item.get('navigationEndpoint', {})
                    pl_id = nav.get('watchEndpoint', {}).get('playlistId', '') or nav.get('browseEndpoint', {}).get('browseId', '')
                    vid = nav.get('watchEndpoint', {}).get('videoId', '')
                    t_low = title.lower().strip()
                    sub_low = subtitle.lower().strip()

                    # Strict filter against single songs / view counts
                    if "views" in sub_low or "ditonton" in sub_low or "penayangan" in sub_low or "tayang" in sub_low:
                        return
                    if pl_id.startswith("RDAMVM") or pl_id.startswith("RDAMPL") or pl_id.startswith("RDAM"):
                        return

                    thumb_url = ""
                    thumbs = item.get('thumbnailRenderer', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                    if thumbs:
                        thumb_url = thumbs[-1].get('url', '')
                        if "=w120-h120" in thumb_url:
                            thumb_url = thumb_url.replace("=w120-h120", "=w544-h544")
                        elif "=s120" in thumb_url:
                            thumb_url = thumb_url.replace("=s120", "=s544")

                    if pl_id and title and pl_id not in seen_ids:
                        item_obj = {
                            "id": pl_id,
                            "title": title,
                            "description": subtitle or "Personalized YouTube Music Station",
                            "track_count": 50,
                            "thumbnail_url": thumb_url,
                            "source": "youtube",
                            "is_algorithmic": True,
                            "badge": "MIX",
                            "seed_video_id": vid
                        }

                        # Slot 1: Supermix
                        if "supermix" in t_low or "favorit saya" in t_low or pl_id == "RDMM" or pl_id.startswith("RDMM"):
                            if "my supermix" in t_low or t_low == "supermix" or pl_id == "RDMM" or not bucket_supermix:
                                seen_ids.add(pl_id)
                                item_obj["badge"] = "SUPERMIX"
                                bucket_supermix = item_obj
                        # Slot 2: Replay Mix
                        elif "replay" in t_low or "putar ulang" in t_low or "on repeat" in t_low or "repeat" in t_low:
                            seen_ids.add(pl_id)
                            item_obj["badge"] = "REPLAY"
                            bucket_replay.append(item_obj)
                        # Slot 3: New Release Mix
                        elif "new release" in t_low or "rilis baru" in t_low or "rilis terbaru" in t_low:
                            seen_ids.add(pl_id)
                            item_obj["badge"] = "NEW RELEASE"
                            bucket_new_release.append(item_obj)
                        # Slot 4..10: My Mix 1 to 7 (Strict: only matches My Mix / Mix 1..7)
                        elif re.search(r'^\s*(?:my\s*mix|mix\s*saya|campuran|mix)\s*([1-7])\s*$', t_low):
                            seen_ids.add(pl_id)
                            m = re.search(r'([1-7])', t_low)
                            num = int(m.group(1)) if m else 99
                            item_obj["badge"] = f"MY MIX {num}"
                            bucket_my_mixes.append((num, item_obj))

                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for it in node:
                    traverse(it)

        traverse(data)

        # Sort My Mixes numerically (1 through 7)
        bucket_my_mixes.sort(key=lambda x: x[0])
        sorted_my_mixes = [it for _, it in bucket_my_mixes]

        defaults = self._get_default_5_mixes()
        final_list: List[Dict[str, Any]] = []

        # Slot 1: Supermix
        if bucket_supermix:
            final_list.append(bucket_supermix)
        elif defaults:
            final_list.append(dict(defaults[0]))

        # Slot 2: Replay Mix
        final_list.extend(bucket_replay)

        # Slot 3: New Release Mix
        final_list.extend(bucket_new_release)

        # Slots 4-10: My Mix 1..7
        final_list.extend(sorted_my_mixes)

        # Deduplicate preserving order
        unique_list: List[Dict[str, Any]] = []
        final_seen = set()
        for it in final_list:
            iid = it.get("id")
            if iid and iid not in final_seen:
                final_seen.add(iid)
                unique_list.append(it)

        # If zero mixes were parsed from live API (unauthenticated or offline), use defaults
        if not unique_list and defaults:
            unique_list = list(defaults)

        return unique_list[:12]


class FetchYTPlaylistsWorker(QThread):
    """Async worker to fetch user's personalized Discovery Feeds, Artist Radios, and Cloud Playlists."""
    playlistsLoaded = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    @staticmethod
    def _sanitize_feed_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sanitizes, filters out junk (podcasts, user profile channels), and converts artist entities to algorithmic Artist Mixes."""
        if not isinstance(item, dict):
            return None

        raw_id = item.get("id", "")
        raw_title = str(item.get("title", "")).strip()
        raw_desc = str(item.get("description", "") or item.get("subtitle", "")).strip()
        thumb = item.get("thumbnail_url", "")

        t_low = raw_title.lower()
        d_low = raw_desc.lower()

        # Filter 1: Junk / Podcasts / Queues / Non-music aggregations
        EXCLUDE_TERMS = [
            "episodes for later", "queued episodes", "episode untuk nanti",
            "podcast", "episodes", "episode", "your queued episodes",
            "feplaylist_aggregation", "femusic_library_corpus_podcasts",
            "femusic_library_corpus_episodes"
        ]
        if any(term in t_low or term in d_low or term in raw_id.lower() for term in EXCLUDE_TERMS):
            return None

        # Filter 2: Non-artist user profile channels (e.g., "Profile • @kezelve-z0c" or raw @handles)
        if d_low.startswith("profile • @") or (d_low.startswith("profile") and "@" in d_low) or d_low.startswith("@"):
            return None

        # Transform 1: Liked Music / Favorites Auto-Mix
        if raw_id in ("LM", "VLLM", "FEmusic_liked_videos") or "liked music" in t_low or "musik yang disukai" in t_low or "lagu yang disukai" in t_low:
            return {
                "id": "LM",
                "title": "Liked Music",
                "description": "Auto-Mix • Your Liked Tracks",
                "track_count": item.get("track_count") or 50,
                "thumbnail_url": thumb or "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "FAVORITES"
            }

        # Transform 2: Subscribed Artist Entities -> Live Algorithmic Artist Radios / Mixes
        is_artist = "artist" in d_low or "artis" in d_low or (raw_id.startswith("UC") and "profile" not in d_low)
        if is_artist:
            clean_name = raw_title
            if not (clean_name.endswith("Mix") or clean_name.endswith("Radio") or clean_name.endswith("Station")):
                clean_title = f"{clean_name} Mix"
            else:
                clean_title = clean_name

            if "artist •" in d_low or "artis •" in d_low:
                clean_desc = raw_desc.replace("Artist •", "Artist Radio •").replace("artist •", "Artist Radio •").replace("Artis •", "Artist Radio •").replace("artis •", "Artist Radio •")
            elif raw_desc:
                clean_desc = f"Artist Radio • {raw_desc}"
            else:
                clean_desc = f"Artist Radio • Top Tracks & Mix"

            return {
                "id": raw_id,
                "title": clean_title,
                "description": clean_desc,
                "track_count": item.get("track_count") or 50,
                "thumbnail_url": thumb,
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "ARTIST MIX",
                "artist_name": clean_name
            }

        # Transform 3: Standard Playlists / Discovery Feeds / Trending
        badge = item.get("badge") or "PLAYLIST"
        if "supermix" in t_low:
            badge = "SUPERMIX"
        elif "discover" in t_low:
            badge = "DISCOVER"
        elif "top 50" in t_low or "hits" in t_low or "charts" in t_low or "trending" in t_low:
            badge = "TOP 50"
        elif "mix" in t_low or "radio" in t_low:
            badge = "MIX"

        return {
            "id": raw_id,
            "title": raw_title,
            "description": raw_desc or "Cloud Feed",
            "track_count": item.get("track_count") or 0,
            "thumbnail_url": thumb,
            "source": "youtube",
            "is_algorithmic": (badge in ("SUPERMIX", "DISCOVER", "MIX", "TOP 50", "ARTIST MIX", "SIMILAR", "RADIO", "REPLAY")),
            "badge": badge
        }

    def _parse_discovery_shelves(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract genuine algorithmic discovery shelves (Similar to..., Recommended radios, Forgotten favorites, Speed dial)."""
        discovery_items: List[Dict[str, Any]] = []
        seen_ids = set()

        DISCOVERY_KEYWORDS = ["similar to", "mirip dengan", "recommended", "rekomendasi", "forgotten", "favorit lama", "listen again", "putar lagi", "speed dial", "quick picks", "pilihan cepat", "from your library", "radio"]

        def traverse(node, current_shelf_title=""):
            if isinstance(node, dict):
                if 'musicCarouselShelfRenderer' in node:
                    shelf = node['musicCarouselShelfRenderer']
                    header = shelf.get('header', {})
                    shelf_title = "".join([run.get("text", "") for run in header.get("musicCarouselShelfBasicHeaderRenderer", {}).get("title", {}).get("runs", [])]).lower()
                    for item in shelf.get('contents', []):
                        traverse(item, shelf_title)
                    return

                if 'musicTwoRowItemRenderer' in node:
                    item = node['musicTwoRowItemRenderer']
                    nav_ep = item.get('navigationEndpoint', {})
                    watch_ep = nav_ep.get('watchEndpoint', {})
                    browse_id = nav_ep.get('browseEndpoint', {}).get('browseId', '') or watch_ep.get('playlistId', '')
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

                    if browse_id and title:
                        is_discovery_shelf = any(dk in current_shelf_title for dk in DISCOVERY_KEYWORDS)
                        if is_discovery_shelf:
                            badge = "DISCOVER"
                            if "similar" in current_shelf_title or "mirip" in current_shelf_title:
                                badge = "SIMILAR"
                            elif "radio" in current_shelf_title or "stasiun" in current_shelf_title:
                                badge = "RADIO"
                            elif "forgotten" in current_shelf_title or "favorit lama" in current_shelf_title:
                                badge = "REPLAY"
                            elif "listen again" in current_shelf_title or "putar lagi" in current_shelf_title:
                                badge = "LISTEN AGAIN"

                            raw_item = {
                                "id": browse_id,
                                "title": title,
                                "description": subtitle or current_shelf_title.title(),
                                "thumbnail_url": thumb_url,
                                "source": "youtube",
                                "badge": badge,
                                "is_algorithmic": True
                            }
                            sanitized = self._sanitize_feed_item(raw_item)
                            if sanitized and sanitized.get("id") not in seen_ids:
                                seen_ids.add(sanitized.get("id"))
                                discovery_items.append(sanitized)

                for v in node.values():
                    traverse(v, current_shelf_title)
            elif isinstance(node, list):
                for item in node:
                    traverse(item, current_shelf_title)

        traverse(data)
        return discovery_items

    def run(self):
        if self._is_cancelled:
            return

        cache_file = os.path.join(self.engine.CACHE_DIR, "yt_playlists.json")
        playlists: List[Dict[str, Any]] = []

        try:
            # 1. Fetch genuine algorithmic discovery feeds from FEmusic_home (Similar to..., Recommended radios, Forgotten favorites, Listen again)
            home_data = self.engine.execute_innertube_browse("FEmusic_home")
            if home_data:
                home_discovery = self._parse_discovery_shelves(home_data)
                for it in home_discovery:
                    if it.get("id") not in [p.get("id") for p in playlists]:
                        playlists.append(it)

            # 2. Fetch user's saved playlists & subscribed artist feeds from FEmusic_library_landing
            lib_data = self.engine.execute_innertube_browse("FEmusic_library_landing")
            if lib_data:
                lib_items = self._parse_playlists(lib_data)
                for it in lib_items:
                    if it.get("id") not in [p.get("id") for p in playlists]:
                        playlists.append(it)

            # 3. Fallback to FEmusic_library_playlists if empty
            if not playlists:
                data3 = self.engine.execute_innertube_browse("FEmusic_library_playlists")
                if data3:
                    playlists = self._parse_playlists(data3)

            # 4. Enrich with Explore / Discovery Mixes if user has few items
            if len(playlists) < 12:
                try:
                    exp_data = self.engine.execute_innertube_browse("FEmusic_explore")
                    if exp_data:
                        exp_items = self._parse_playlists(exp_data)
                        existing_ids = {p.get("id") for p in playlists}
                        for it in exp_items:
                            if it.get("id") not in existing_ids:
                                playlists.append(it)
                                existing_ids.add(it.get("id"))
                except Exception:
                    pass

            # 5. Prepend Liked Music auto-playlist at Slot 0
            liked_music_item = {
                "id": "LM",
                "title": "Liked Music",
                "description": "Auto-Mix • Your Liked Tracks",
                "track_count": 50,
                "thumbnail_url": "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png",
                "source": "youtube",
                "is_algorithmic": True,
                "badge": "FAVORITES"
            }

            has_lm = any(p.get("id") in ("LM", "FEmusic_liked_videos", "VLLM") or "liked music" in p.get("title", "").lower() for p in playlists)
            if not has_lm:
                playlists.insert(0, liked_music_item)
            else:
                for i, p in enumerate(playlists):
                    if p.get("id") in ("LM", "FEmusic_liked_videos", "VLLM") or "liked music" in p.get("title", "").lower():
                        lm = playlists.pop(i)
                        lm.update(liked_music_item)
                        playlists.insert(0, lm)
                        break

            if playlists:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(playlists[:12], f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    raw_cache = json.load(f)
                    playlists = [self._sanitize_feed_item(it) for it in raw_cache if self._sanitize_feed_item(it)]

            if not self._is_cancelled:
                self.playlistsLoaded.emit(playlists[:12])
        except Exception as e:
            if not self._is_cancelled:
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            raw_cache = json.load(f)
                            playlists = [self._sanitize_feed_item(it) for it in raw_cache if self._sanitize_feed_item(it)]
                        self.playlistsLoaded.emit(playlists[:12])
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

                    if browse_id and title:
                        raw_item = {
                            "id": browse_id,
                            "title": title,
                            "description": subtitle,
                            "thumbnail_url": thumb_url,
                            "source": "youtube"
                        }
                        sanitized = self._sanitize_feed_item(raw_item)
                        if sanitized and sanitized.get("id") not in seen_ids:
                            seen_ids.add(sanitized.get("id"))
                            playlists.append(sanitized)

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

                    if browse_id and title:
                        raw_item = {
                            "id": browse_id,
                            "title": title,
                            "description": subtitle,
                            "thumbnail_url": thumb_url,
                            "source": "youtube"
                        }
                        sanitized = self._sanitize_feed_item(raw_item)
                        if sanitized and sanitized.get("id") not in seen_ids:
                            seen_ids.add(sanitized.get("id"))
                            playlists.append(sanitized)

                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(data)
        return playlists


class FetchYouTubeHomeFeedWorker(QThread):
    """Async worker to fetch authentic personalized music recommendations from YouTube Music (FEmusic_home)."""
    feedLoaded = Signal(list, list, str)  # (mixes, tracks, continuation_token)
    moreFeedLoaded = Signal(list, str)    # (tracks, next_continuation_token)
    chipsLoaded = Signal(list)            # (chips: [{"title": str, "params": str}])
    errorOccurred = Signal(str)

    def __init__(self, continuation: Optional[str] = None, params: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.continuation = continuation
        self.params = params
        self.engine = YouTubeAccountEngine.get_instance()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        cache_key = f"yt_music_feed_{self.params or 'all'}.json"
        cache_file = os.path.join(self.engine.CACHE_DIR, cache_key)
        is_continuation = bool(self.continuation)

        BATCH_SIZE = 28

        try:
            if self.continuation:
                accumulated_tracks = []
                current_token = self.continuation
                # Loop continuation up to 3 pages if needed to ensure a rich batch of playable tracks
                for _ in range(3):
                    if self._is_cancelled or not current_token:
                        break
                    data = self.engine.execute_innertube_browse(continuation=current_token)
                    if not data:
                        break
                    m, t, c, next_token = self._parse_ytm_home_feed(data)
                    valid_tracks = [x for x in t if x.get("video_id") and not self._is_mix_or_station(x.get("title", ""), x.get("playlist_id", ""), x.get("video_id", ""))]
                    accumulated_tracks.extend(valid_tracks)
                    current_token = next_token
                    if len(accumulated_tracks) >= 16:
                        break

                tracks = accumulated_tracks
                next_token = current_token

                if len(tracks) >= BATCH_SIZE:
                    tracks = tracks[:BATCH_SIZE]
                elif len(tracks) >= 4:
                    valid_count = (len(tracks) // 4) * 4
                    tracks = tracks[:valid_count]

                if not self._is_cancelled:
                    self.moreFeedLoaded.emit(tracks, next_token)
                return
            else:
                data = self.engine.execute_innertube_browse("FEmusic_home", params=self.params)

            if data:
                mixes, tracks, chips, next_token = self._parse_ytm_home_feed(data)

                # Snap tracks to 28 (or clean multiple of 4) for 4-column layout
                if len(tracks) >= BATCH_SIZE:
                    tracks = tracks[:BATCH_SIZE]
                elif len(tracks) >= 4:
                    valid_count = (len(tracks) // 4) * 4
                    tracks = tracks[:valid_count]

                # Snap mixes to clean multiple of 4
                if len(mixes) >= 4:
                    mixes = mixes[:(len(mixes) // 4) * 4]

                if not is_continuation and (tracks or mixes):
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump({"mixes": mixes, "tracks": tracks, "chips": chips, "token": next_token}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                if not self._is_cancelled:
                    if not tracks and not mixes:
                        fallback_tracks, next_token = self._get_fallback_feed()
                        tracks = fallback_tracks
                    if chips:
                        self.chipsLoaded.emit(chips)
                    self.feedLoaded.emit(mixes, tracks, next_token)
                    return

            if not is_continuation:
                self._load_fallback_or_cache(cache_file)
            else:
                if not self._is_cancelled:
                    self.errorOccurred.emit("Failed to load more music recommendations.")
        except Exception as e:
            if self._is_cancelled:
                return
            if not is_continuation:
                self._load_fallback_or_cache(cache_file)
            else:
                self.errorOccurred.emit(str(e))

    def _load_fallback_or_cache(self, cache_file: str):
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    if isinstance(cached, dict) and (cached.get("tracks") or cached.get("videos")):
                        if cached.get("chips"):
                            self.chipsLoaded.emit(cached["chips"])
                        m_list = cached.get("mixes", [])
                        t_list = cached.get("tracks") or cached.get("videos", [])
                        self.feedLoaded.emit(m_list, t_list, cached.get("token", ""))
                        return
                    elif isinstance(cached, list) and cached:
                        self.feedLoaded.emit([], cached, "")
                        return
            except Exception:
                pass
        fallback_videos, token = self._get_fallback_feed()
        self.feedLoaded.emit([], fallback_videos, token)

    @staticmethod
    def _is_mix_or_station(title: str, pl_id: str, vid: str) -> bool:
        if not vid:
            return True
        t_low = (title or "").lower()
        if "my mix" in t_low or "supermix" in t_low or "station" in t_low or "radio" in t_low:
            return True
        if pl_id and (pl_id.startswith("VLRD") or pl_id.startswith("RDCLAK") or pl_id.startswith("RDTMAK")):
            return True
        return False

    def _parse_ytm_home_feed(self, data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, str]], str]:
        mixes: List[Dict[str, Any]] = []
        tracks: List[Dict[str, Any]] = []
        chips: List[Dict[str, str]] = [{"title": "All", "params": ""}]
        seen_ids = set()
        continuation_token = ""

        def traverse(node):
            nonlocal continuation_token
            if isinstance(node, dict):
                # Continuation Tokens
                if 'continuationCommand' in node and 'token' in node['continuationCommand']:
                    t = node['continuationCommand']['token']
                    if t and not continuation_token:
                        continuation_token = t

                if 'nextContinuationData' in node:
                    t = node['nextContinuationData'].get('continuation')
                    if t and not continuation_token:
                        continuation_token = t

                if 'reloadContinuationData' in node:
                    t = node['reloadContinuationData'].get('continuation')
                    if t and not continuation_token:
                        continuation_token = t

                if 'continuationItemRenderer' in node:
                    ep = node['continuationItemRenderer'].get('continuationEndpoint', {})
                    cmd = ep.get('continuationCommand', {})
                    token = cmd.get('token')
                    if token and not continuation_token:
                        continuation_token = token

                # Dynamic YouTube Music Mood / Activity Chips
                if 'chipCloudChipRenderer' in node:
                    c = node['chipCloudChipRenderer']
                    ctext = c.get('text', {}).get('runs', [{}])[0].get('text', '')
                    cparams = c.get('navigationEndpoint', {}).get('browseEndpoint', {}).get('params', '')
                    if ctext and not any(ch['title'].lower() == ctext.lower() for ch in chips):
                        chips.append({'title': ctext, 'params': cparams})

                # Music Two Row Item (Tracks, Mixes, Albums, Recommended Singles)
                if 'musicTwoRowItemRenderer' in node:
                    item = self._extract_ytm_two_row_item(node['musicTwoRowItemRenderer'], seen_ids)
                    if item:
                        if self._is_mix_or_station(item.get('title', ''), item.get('playlist_id', ''), item.get('video_id', '')):
                            mixes.append(item)
                        else:
                            tracks.append(item)
                    return

                # Music Responsive List Item (Quick Picks, Stream Tracks)
                if 'musicResponsiveListItemRenderer' in node:
                    item = self._extract_ytm_responsive_item(node['musicResponsiveListItemRenderer'], seen_ids)
                    if item:
                        if self._is_mix_or_station(item.get('title', ''), item.get('playlist_id', ''), item.get('video_id', '')):
                            mixes.append(item)
                        else:
                            tracks.append(item)
                    return

                # Lockup View Model fallback
                if 'lockupViewModel' in node:
                    item = self._extract_lockup_item(node['lockupViewModel'], seen_ids)
                    if item:
                        if self._is_mix_or_station(item.get('title', ''), item.get('playlist_id', ''), item.get('video_id', '')):
                            mixes.append(item)
                        else:
                            tracks.append(item)
                    return

                # Video Renderer fallback
                if 'videoRenderer' in node:
                    self._extract_video_item(node['videoRenderer'], tracks, seen_ids)
                    return

                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(data)
        return mixes, tracks, chips, continuation_token

    def _optimize_thumbnail_url(self, url: str) -> str:
        if not url:
            return ""
        # 1. Google user content / YTM album art: upgrade small resolutions to crystal clear high-res (w800-h800)
        if "googleusercontent.com" in url or "ggpht.com" in url:
            url = re.sub(r'=w\d+-h\d+[^?&]*', '=w800-h800-l90-rj', url)
            url = re.sub(r'=s\d+[^?&]*', '=s800', url)
            return url
        # 2. YouTube image CDN: strip low-res sqp compression query parameter to get full HD 1280x720
        if "i.ytimg.com" in url:
            return url.split("?")[0]
        return url

    def _extract_ytm_two_row_item(self, r: dict, seen_ids: set) -> Optional[Dict[str, Any]]:
        title_runs = r.get("title", {}).get("runs", [])
        title = title_runs[0].get("text", "") if title_runs else ""

        sub_runs = r.get("subtitle", {}).get("runs", [])
        sub_texts = [x.get("text", "").strip() for x in sub_runs if x.get("text", "").strip() and x.get("text", "").strip() != "•"]

        channel_name = sub_texts[0] if sub_texts else "YouTube Music"
        views_or_type = sub_texts[1] if len(sub_texts) > 1 else ""
        pub_or_extra = sub_texts[2] if len(sub_texts) > 2 else ""

        # Check endpoints (both navigationEndpoint and thumbnailOverlay play button)
        nav = r.get("navigationEndpoint", {})
        watch_ep = nav.get("watchEndpoint", {})
        browse_ep = nav.get("browseEndpoint", {})

        overlay_btn = r.get("thumbnailOverlay", {}).get("musicItemThumbnailOverlayRenderer", {}).get("content", {}).get("musicPlayButtonRenderer", {})
        play_watch_ep = overlay_btn.get("playNavigationEndpoint", {}).get("watchEndpoint", {})

        vid = watch_ep.get("videoId", "") or play_watch_ep.get("videoId", "")
        pl_id = watch_ep.get("playlistId", "") or play_watch_ep.get("playlistId", "") or browse_ep.get("browseId", "")

        thumb_renderer = r.get("thumbnailRenderer", {}).get("musicThumbnailRenderer", {})
        thumbs = thumb_renderer.get("thumbnail", {}).get("thumbnails", [])
        thumb_url = thumbs[-1].get("url") if thumbs else ""

        if not thumb_url:
            if vid:
                thumb_url = f"https://i.ytimg.com/vi/{vid}/hq720.jpg"
            else:
                thumb_url = "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png"

        thumb_url = self._optimize_thumbnail_url(thumb_url)

        item_id = vid or pl_id
        if not item_id or item_id in seen_ids:
            return None

        seen_ids.add(item_id)
        return {
            "video_id": vid,
            "playlist_id": pl_id,
            "title": title or "Music Track",
            "channel_name": channel_name,
            "channel_id": browse_ep.get("browseId", ""),
            "channel_avatar": "",
            "thumbnail_url": thumb_url,
            "duration_text": "Track",
            "view_count_text": views_or_type,
            "published_time_text": pub_or_extra,
            "is_live": False,
            "source": "youtube"
        }

    def _extract_ytm_responsive_item(self, r: dict, seen_ids: set) -> Optional[Dict[str, Any]]:
        cols = r.get("flexColumns", [])
        title = ""
        channel_name = "YouTube Music"
        views_text = ""
        pub_text = ""
        duration_text = ""

        if len(cols) > 0:
            runs = cols[0].get("musicResponsiveListItemFlexColumnRenderer", {}).get("text", {}).get("runs", [])
            title = runs[0].get("text", "") if runs else ""

        if len(cols) > 1:
            runs = cols[1].get("musicResponsiveListItemFlexColumnRenderer", {}).get("text", {}).get("runs", [])
            sub_texts = [x.get("text", "").strip() for x in runs if x.get("text", "").strip() and x.get("text", "").strip() != "•"]
            if len(sub_texts) > 0:
                channel_name = sub_texts[0]
            if len(sub_texts) > 1:
                views_text = sub_texts[1]
            if len(sub_texts) > 2:
                pub_text = sub_texts[2]

        fixed_cols = r.get("fixedColumns", [])
        if fixed_cols:
            f_runs = fixed_cols[0].get("musicResponsiveListItemFixedColumnRenderer", {}).get("text", {}).get("runs", [])
            if f_runs:
                duration_text = f_runs[0].get("text", "")

        overlay_nav = r.get("overlay", {}).get("musicItemThumbnailOverlayRenderer", {}).get("content", {}).get("musicPlayButtonRenderer", {})
        play_nav = overlay_nav.get("playNavigationEndpoint", {})
        watch_ep = play_nav.get("watchEndpoint", {})
        vid = watch_ep.get("videoId", "")
        pl_id = watch_ep.get("playlistId", "")

        thumbs = r.get("thumbnail", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])
        thumb_url = thumbs[-1].get("url") if thumbs else ""

        if not thumb_url:
            if vid:
                thumb_url = f"https://i.ytimg.com/vi/{vid}/hq720.jpg"
            else:
                thumb_url = "https://www.gstatic.com/youtube/media/ytm/images/pbg/liked-music-@576.png"

        thumb_url = self._optimize_thumbnail_url(thumb_url)

        item_id = vid or pl_id
        if not item_id or item_id in seen_ids:
            return None

        seen_ids.add(item_id)
        return {
            "video_id": vid,
            "playlist_id": pl_id,
            "title": title or "Music Track",
            "channel_name": channel_name,
            "channel_id": "",
            "channel_avatar": "",
            "thumbnail_url": thumb_url,
            "duration_text": duration_text or "Track",
            "view_count_text": views_text,
            "published_time_text": pub_text,
            "is_live": False,
            "source": "youtube"
        }

    def _extract_lockup_item(self, lockup: dict, seen_ids: set) -> Optional[Dict[str, Any]]:
        vid = lockup.get("contentId", "")
        if not vid:
            on_tap = lockup.get("rendererContext", {}).get("commandContext", {}).get("onTap", {}).get("innertubeCommand", {})
            vid = on_tap.get("watchEndpoint", {}).get("videoId", "")
        if not vid or vid in seen_ids:
            return None

        meta = lockup.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = meta.get("title", {}).get("content", "")

        channel_name = ""
        channel_avatar = ""
        view_text = ""
        pub_text = ""

        # Channel avatar image
        image_obj = meta.get("image", {})
        if image_obj and "sources" in image_obj and image_obj["sources"]:
            channel_avatar = image_obj["sources"][-1].get("url", "")

        # Metadata rows (Channel name, views, publish time)
        content_meta = meta.get("metadata", {}).get("contentMetadataViewModel", {})
        rows = content_meta.get("metadataRows", [])
        if len(rows) > 0:
            parts = rows[0].get("metadataParts", [])
            if parts:
                channel_name = parts[0].get("text", {}).get("content", "")
        if len(rows) > 1:
            parts = rows[1].get("metadataParts", [])
            if len(parts) > 0:
                view_text = parts[0].get("text", {}).get("content", "")
            if len(parts) > 1:
                pub_text = parts[1].get("text", {}).get("content", "")

        thumb_url = f"https://i.ytimg.com/vi/{vid}/hq720.jpg" if vid else ""
        duration_text = ""
        is_live = False

        content_image = lockup.get("contentImage", {})
        thumb_vm = content_image.get("thumbnailViewModel") or content_image.get("collectionThumbnailViewModel", {}).get("primaryThumbnail", {}).get("thumbnailViewModel", {})

        if thumb_vm:
            sources = thumb_vm.get("image", {}).get("sources", [])
            if sources:
                thumb_url = sources[-1].get("url", thumb_url)
            overlays = thumb_vm.get("overlays", [])
            for ov in overlays:
                bottom_ov = ov.get("thumbnailBottomOverlayViewModel", {})
                badges = bottom_ov.get("badges", [])
                for b in badges:
                    b_vm = b.get("thumbnailBadgeViewModel", {})
                    b_text = b_vm.get("text", "")
                    if "LIVE" in b_text.upper():
                        is_live = True
                        duration_text = "LIVE"
                    elif b_text and not duration_text:
                        duration_text = b_text

                badge_ov = ov.get("thumbnailOverlayBadgeViewModel", {})
                for b in badge_ov.get("thumbnailBadges", []):
                    b_text = b.get("thumbnailBadgeViewModel", {}).get("text", "")
                    if "LIVE" in b_text.upper():
                        is_live = True
                        duration_text = "LIVE"
                    elif b_text and not duration_text:
                        duration_text = b_text

                time_status = ov.get("thumbnailOverlayTimeStatusRenderer", {})
                if time_status:
                    ts_text = time_status.get("text", {}).get("simpleText", "")
                    if "LIVE" in ts_text.upper():
                        is_live = True
                        duration_text = "LIVE"
                    elif ts_text and not duration_text:
                        duration_text = ts_text

        thumb_url = self._optimize_thumbnail_url(thumb_url)
        seen_ids.add(vid)
        return {
            "video_id": vid,
            "title": title or "YouTube Video",
            "channel_name": channel_name or "YouTube Creator",
            "channel_id": "",
            "channel_avatar": channel_avatar,
            "thumbnail_url": thumb_url,
            "duration_text": duration_text or ("LIVE" if is_live else ""),
            "view_count_text": view_text,
            "published_time_text": pub_text,
            "is_live": is_live,
            "source": "youtube"
        }

    def _extract_video_item(self, v_renderer: dict, videos: list, seen_ids: set):
        vid = v_renderer.get('videoId', '')
        if not vid or vid in seen_ids:
            return

        title = ""
        title_obj = v_renderer.get('title', {})
        if 'runs' in title_obj and title_obj['runs']:
            title = title_obj['runs'][0].get('text', '')
        elif 'simpleText' in title_obj:
            title = title_obj['simpleText']

        channel_name = ""
        channel_id = ""
        owner_obj = v_renderer.get('ownerText') or v_renderer.get('shortBylineText') or {}
        if 'runs' in owner_obj and owner_obj['runs']:
            channel_name = owner_obj['runs'][0].get('text', '')
            nav_ep = owner_obj['runs'][0].get('navigationEndpoint', {})
            channel_id = nav_ep.get('browseEndpoint', {}).get('browseId', '')

        channel_avatar = ""
        avatar_obj = v_renderer.get('channelThumbnailSupportedRenderers', {}).get('channelThumbnailWithLinkRenderer', {}).get('thumbnail', {})
        if avatar_obj and 'thumbnails' in avatar_obj and avatar_obj['thumbnails']:
            channel_avatar = avatar_obj['thumbnails'][-1].get('url', '')

        thumb_url = f"https://i.ytimg.com/vi/{vid}/hq720.jpg" if vid else ""
        thumb_obj = v_renderer.get('thumbnail', {})
        if thumb_obj and 'thumbnails' in thumb_obj and thumb_obj['thumbnails']:
            thumb_url = thumb_obj['thumbnails'][-1].get('url', thumb_url)
        thumb_url = self._optimize_thumbnail_url(thumb_url)

        duration_text = ""
        len_obj = v_renderer.get('lengthText', {})
        if 'simpleText' in len_obj:
            duration_text = len_obj['simpleText']
        elif 'runs' in len_obj and len_obj['runs']:
            duration_text = len_obj['runs'][0].get('text', '')

        view_text = ""
        view_obj = v_renderer.get('shortViewCountText') or v_renderer.get('viewCountText') or {}
        if 'simpleText' in view_obj:
            view_text = view_obj['simpleText']
        elif 'runs' in view_obj and view_obj['runs']:
            view_text = "".join([r.get('text', '') for r in view_obj['runs']])

        pub_text = ""
        pub_obj = v_renderer.get('publishedTimeText', {})
        if 'simpleText' in pub_obj:
            pub_text = pub_obj['simpleText']
        elif 'runs' in pub_obj and pub_obj['runs']:
            pub_text = "".join([r.get('text', '') for r in pub_obj['runs']])

        is_live = False
        badges = v_renderer.get('badges', [])
        for b in badges:
            b_text = b.get('metadataBadgeRenderer', {}).get('label', '').upper()
            if 'LIVE' in b_text:
                is_live = True
                break

        seen_ids.add(vid)
        videos.append({
            "video_id": vid,
            "title": title or "YouTube Video",
            "channel_name": channel_name or "YouTube Creator",
            "channel_id": channel_id,
            "channel_avatar": channel_avatar,
            "thumbnail_url": thumb_url,
            "duration_text": duration_text or ("LIVE" if is_live else ""),
            "view_count_text": view_text,
            "published_time_text": pub_text,
            "is_live": is_live,
            "source": "youtube"
        })

    def _get_fallback_feed(self) -> Tuple[List[Dict[str, Any]], str]:
        """Dynamically fetch trending global music for unauthenticated / cold-start fallback."""
        try:
            from CanonicalMetadataEngine import InnertubeSearchClient
            live_results = InnertubeSearchClient.search("Top 50 Global Music Hits Official", limit=25, live_only=False)
            if live_results:
                items = []
                for r in live_results:
                    vid_id = r.get("id", "")
                    if not vid_id:
                        continue
                    items.append({
                        "video_id": vid_id,
                        "title": r.get("title", "Unknown Track"),
                        "channel_name": r.get("uploader", "YouTube Artist"),
                        "channel_id": "",
                        "channel_avatar": "",
                        "thumbnail_url": r.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                        "duration_text": str(int(r.get("duration", 0) // 60)) + ":" + f"{int(r.get('duration', 0) % 60):02d}" if r.get("duration") else "3:30",
                        "view_count_text": "Trending",
                        "published_time_text": "Recent",
                        "is_live": r.get("is_live", False),
                        "source": "youtube"
                    })
                if items:
                    return items, ""
        except Exception as ex:
            print(f"[YouTubeAccountEngine] Dynamic fallback fetch notice: {ex}")

        return [], ""


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



