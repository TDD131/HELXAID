"""
FirebaseAuthEngine.py - (Deprecated / Retired)
==============================================
The Google OAuth2 & Firebase Authentication features have been retired.
Local sync daemon server functionality for the Chrome Extension has been permanently
migrated to YouTubeAccountEngine.py (Port 8889).

This stub is retained solely for legacy binary/import compatibility.
Component Name: firebaseAuthEngine
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal


class FirebaseAuthEngine(QObject):
    """
    Deprecated Stub Engine.
    Component Name: firebaseAuthEngine
    """
    authStatusChanged = Signal(bool, dict)
    profileUpdated = Signal(dict)
    authError = Signal(str)
    syncCompleted = Signal(str)
    cookiesReceived = Signal(dict)

    _instance: Optional["FirebaseAuthEngine"] = None

    @classmethod
    def get_instance(cls) -> "FirebaseAuthEngine":
        if cls._instance is None:
            cls._instance = FirebaseAuthEngine()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("firebaseAuthEngine")

    def is_authenticated(self) -> bool:
        return False

    def get_user_profile(self) -> Dict[str, Any]:
        return {}

    def get_display_name(self) -> str:
        return ""

    def get_email(self) -> str:
        return ""

    def get_photo_url(self) -> str:
        return ""

    def get_uid(self) -> str:
        return ""

    def start_google_login(self, port: int = 8889):
        pass

    def logout(self):
        pass
