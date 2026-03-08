"""
Debug Console Window Widget

A floating window that displays print() output when running as .exe.
Can be toggled with F12.

Component Name: DebugConsoleWidget
"""

import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont, QTextCursor


class OutputRedirector(QObject):
    """Redirects stdout/stderr to a signal."""
    text_written = Signal(str)
    
    def __init__(self, original_stream):
        super().__init__()
        self.original_stream = original_stream
    
    def write(self, text):
        if text.strip():  # Only emit non-empty text
            self.text_written.emit(text)
        # Also write to original stream
        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except:
                pass
    
    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except:
                pass


class DebugConsoleWidget(QWidget):
    """
    Debug Console Window for viewing print output in .exe mode.
    
    Component Name: DebugConsoleWidget
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Debug Console - HELXAID")
        self.setObjectName("DebugConsoleWidget")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(600, 400)
        self.resize(800, 500)
        
        self._setup_ui()
        self._setup_redirector()
        
        # Start hidden
        self.hide()
    
    def _setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Text display
        self.console = QTextEdit()
        self.console.setObjectName("debugConsole")
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        self.console.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.console)
        
        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
        
        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("debugClearBtn")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_console)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background: #444;
                border-color: #FF5B06;
            }
        """)
        btn_layout.addWidget(clear_btn)
        
        # Auto-scroll toggle
        self.auto_scroll_btn = QPushButton("Auto-Scroll: ON")
        self.auto_scroll_btn.setObjectName("debugAutoScrollBtn")
        self.auto_scroll_btn.setCursor(Qt.PointingHandCursor)
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        self.auto_scroll_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background: #444;
            }
            QPushButton:checked {
                background: #FF5B06;
                color: #fff;
                border-color: #FF5B06;
            }
        """)
        btn_layout.addWidget(self.auto_scroll_btn)
        
        btn_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close (F11)")
        close_btn.setObjectName("debugCloseBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background: #c0392b;
                border-color: #c0392b;
            }
        """)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # Window styling
        self.setStyleSheet("""
            QWidget#DebugConsoleWidget {
                background: #252526;
            }
        """)
    
    def _setup_redirector(self):
        """Setup stdout/stderr redirection."""
        self._stdout_redirector = OutputRedirector(sys.stdout)
        self._stderr_redirector = OutputRedirector(sys.stderr)
        
        self._stdout_redirector.text_written.connect(self._append_text)
        self._stderr_redirector.text_written.connect(lambda t: self._append_text(t, error=True))
        
        sys.stdout = self._stdout_redirector
        sys.stderr = self._stderr_redirector
    
    def _append_text(self, text, error=False):
        """Append text to the console."""
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if error:
            # Red color for errors
            self.console.setTextColor("#f44336")
        else:
            # Default color
            self.console.setTextColor("#d4d4d4")
        
        cursor.insertText(text)
        
        # Auto-scroll if enabled
        if self.auto_scroll_btn.isChecked():
            self.console.setTextCursor(cursor)
            self.console.ensureCursorVisible()
    
    def _toggle_auto_scroll(self, checked):
        """Toggle auto-scroll."""
        self.auto_scroll_btn.setText(f"Auto-Scroll: {'ON' if checked else 'OFF'}")
    
    def clear_console(self):
        """Clear the console."""
        self.console.clear()
    
    def toggle_visibility(self):
        """Toggle window visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def keyPressEvent(self, event):
        """Handle key press."""
        if event.key() == Qt.Key_F11:
            self.hide()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Handle close - just hide instead."""
        event.ignore()
        self.hide()


# Singleton instance
_debug_console = None

def get_debug_console(parent=None):
    """Get or create the debug console singleton."""
    global _debug_console
    if _debug_console is None:
        _debug_console = DebugConsoleWidget(parent)
    return _debug_console

def toggle_debug_console():
    """Toggle the debug console visibility."""
    if _debug_console:
        _debug_console.toggle_visibility()
