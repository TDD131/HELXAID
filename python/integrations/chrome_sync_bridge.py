"""
Chrome Extension Synchronization Bridge for HELXAID.

Component Name: ChromeSyncBridge
Provides zero-dependency RFC 6455 WebSocket communication with custom Chrome Extensions.
Dispatches initial application and stream state upon main initialization / handshake.
"""

import socket
import select
import threading
import hashlib
import base64
import struct
import json
import time
from typing import Optional, Callable, Dict, Any


class ChromeSyncBridge:
    """
    Lightweight zero-dependency WebSocket server (RFC 6455) for Chrome Extension synchronization.
    Runs in a background daemon thread and sends a one-time MAIN_INITIALIZE event
    when the extension connects or when the app completes initial state restoration.
    """
    
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 49152,
        get_init_payload_cb: Optional[Callable[[], Dict[str, Any]]] = None
    ):
        self.host = host
        self.port = port
        self.get_init_payload_cb = get_init_payload_cb
        
        self._server_sock: Optional[socket.socket] = None
        self._clients: set[socket.socket] = set()
        self._clients_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        """Check if the bridge server is running."""
        return self._running

    def start(self):
        """Start the background WebSocket server."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(
            target=self._server_loop,
            daemon=True,
            name="ChromeSyncBridge"
        )
        self._thread.start()
        print(f"[ChromeSyncBridge] Listening on ws://{self.host}:{self.port}")

    def stop(self):
        """Stop the background server and close all client connections."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        with self._clients_lock:
            for client in list(self._clients):
                try:
                    client.close()
                except Exception:
                    pass
            self._clients.clear()
            
        print("[ChromeSyncBridge] Service stopped.")

    def _server_loop(self):
        """Main listener loop running on background thread."""
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
        except Exception as e:
            print(f"[ChromeSyncBridge] Failed to bind {self.host}:{self.port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                r_list, _, _ = select.select([self._server_sock], [], [], 0.5)
                if self._server_sock in r_list:
                    client_sock, addr = self._server_sock.accept()
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_sock, addr),
                        daemon=True,
                        name=f"ChromeSyncClient-{addr[1]}"
                    )
                    client_thread.start()
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket, addr):
        """Handle incoming WebSocket connection, perform handshake, and dispatch initialization."""
        try:
            client_sock.settimeout(3.0)
            request = client_sock.recv(4096).decode('utf-8', errors='ignore')
            if "Upgrade: websocket" not in request and "upgrade: websocket" not in request.lower():
                client_sock.close()
                return

            # Extract Sec-WebSocket-Key
            sec_key = None
            for line in request.split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    sec_key = line.split(":", 1)[1].strip()
                    break

            if not sec_key:
                client_sock.close()
                return

            # RFC 6455 Handshake calculation
            accept_hash = hashlib.sha1((sec_key + self.GUID).encode('utf-8')).digest()
            accept_key = base64.b64encode(accept_hash).decode('utf-8')
            
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
            )
            client_sock.sendall(response.encode('utf-8'))

            with self._clients_lock:
                self._clients.add(client_sock)

            print(f"[ChromeSyncBridge] Chrome Extension connected from {addr}")

            # Dispatch one-time MAIN_INITIALIZE event immediately on handshake!
            self._dispatch_init_to_client(client_sock)

            # Wait on connection / ping-pong loop until client closes
            client_sock.settimeout(None)
            while self._running:
                data = client_sock.recv(1024)
                if not data:
                    break
                # If client sends a close frame (opcode 0x8)
                if len(data) >= 2 and (data[0] & 0x0F) == 0x8:
                    break
        except Exception:
            pass
        finally:
            with self._clients_lock:
                self._clients.discard(client_sock)
            try:
                client_sock.close()
            except Exception:
                pass

    def _dispatch_init_to_client(self, client_sock: socket.socket):
        """Compile and send the MAIN_INITIALIZE event frame to the connected client."""
        payload_data = {}
        if self.get_init_payload_cb:
            try:
                payload_data = self.get_init_payload_cb()
            except Exception as e:
                print(f"[ChromeSyncBridge] Error generating payload: {e}")

        payload = {
            "event": "MAIN_INITIALIZE",
            "version": "1.0",
            "timestamp": time.time(),
            "app": "HELXAID",
            "component": "HELXAIC",
            "data": payload_data or {"action": "RESYNC", "ready": True}
        }
        
        try:
            self._send_frame(client_sock, json.dumps(payload))
            print("[ChromeSyncBridge] Dispatched MAIN_INITIALIZE resync event to Chrome Extension.")
        except Exception as e:
            print(f"[ChromeSyncBridge] Failed to send init frame: {e}")

    def broadcast_event(self, event_name: str, data: Dict[str, Any]):
        """Broadcast an arbitrary event frame to all connected clients."""
        if not self._clients or not self._running:
            return

        payload = json.dumps({
            "event": event_name,
            "timestamp": time.time(),
            "app": "HELXAID",
            "component": "HELXAIC",
            "data": data
        })

        with self._clients_lock:
            for client in list(self._clients):
                try:
                    self._send_frame(client, payload)
                except Exception:
                    self._clients.discard(client)

    def _send_frame(self, sock: socket.socket, message: str):
        """Encode and transmit an RFC 6455 unmasked text frame from server to client."""
        payload_bytes = message.encode('utf-8')
        length = len(payload_bytes)
        
        # Byte 0: FIN (0x80) + Opcode Text (0x01) -> 0x81
        frame_header = bytearray([0x81])
        
        # Payload length encoding (unmasked from server to client)
        if length <= 125:
            frame_header.append(length)
        elif length <= 65535:
            frame_header.append(126)
            frame_header.extend(struct.pack("!H", length))
        else:
            frame_header.append(127)
            frame_header.extend(struct.pack("!Q", length))
            
        sock.sendall(frame_header + payload_bytes)
