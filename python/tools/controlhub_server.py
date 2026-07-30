"""
Local HTTP Server for ControlHub (Furycube Mouse Config)
Runs the ControlHub website offline for mouse configuration.

Usage:
1. Run this script: python controlhub_server.py
2. Open browser to http://localhost:8080
3. Click Connect and select mouse
4. Configure button mapping

IMPORTANT: WebHID only works in supported browsers (Chrome, Edge)
and requires HTTPS or localhost.
"""

import http.server
import socketserver
import webbrowser
import os
import threading

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(__file__), "controlhub")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers for WebHID
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

def open_browser():
    """Open browser after short delay to let server start"""
    import time
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    print(f"ControlHub Offline Server")
    print(f"========================")
    print(f"Directory: {DIRECTORY}")
    print(f"URL: http://localhost:{PORT}")
    print()
    
    # Start browser in background
    threading.Thread(target=open_browser, daemon=True).start()
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Server running on port {PORT}...")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
