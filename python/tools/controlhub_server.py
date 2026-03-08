"""
Local HTTP Server untuk ControlHub (Furycube Mouse Config)
Menjalankan website ControlHub secara offline untuk konfigurasi mouse.

Cara pakai:
1. Jalankan script ini: python controlhub_server.py
2. Buka browser ke http://localhost:8080
3. Klik Connect dan pilih mouse
4. Konfigurasi button mapping

PENTING: WebHID hanya work di browser yang support (Chrome, Edge)
dan memerlukan HTTPS atau localhost.
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
