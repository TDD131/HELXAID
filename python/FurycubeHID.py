"""
FurycubeHID.py - Native USB HID Communication Module for Furycube Mouse

This module handles direct USB HID communication with the Furycube mouse firmware.
Uses the hidapi library for native HID access - NO WEB INVOLVEMENT.

Protocol reverse-engineered from controlhub.top/Furycube WebHID implementation.

HID Protocol Details:
- Report ID: 8
- Packet Size: 16 bytes
- Command Format:
  [0] Service ID (7=Write Flash, 8=Read Flash)
  [1] Reserved (always 0)
  [2-3] Memory Address (Big Endian)
  [4] Data Length
  [5-14] Payload Data
  [15] Checksum = (85 - Sum of Bytes 0-14) - 8

Device Identifiers:
- Vendor ID: 0x3554 (13652)
- Product ID: 0xF5D5 (62933)
- Product Name: "2.4G Wireless Receiver"
"""

import hid
import random
import time
from typing import Optional, List, Tuple, Dict
from enum import IntEnum


class FurycubeVID:
    """
    Furycube USB Vendor ID.
    This is the manufacturer identifier for the Furycube wireless receiver.
    """
    VID = 0x3554  # 13652 in decimal


class FurycubePID:
    """
    Furycube USB Product ID.
    This identifies the specific Furycube mouse model.
    """
    PID = 0xF5D5  # 62933 in decimal (Wireless)
    PID_WIRED = 0xF511  # 62737 in decimal (Wired)


class HIDCommand(IntEnum):
    """
    HID command types for Furycube mouse communication.
    These are the service IDs used in byte 0 of the packet.
    """
    WRITE_FLASH = 0x07  # Write data to flash memory
    READ_FLASH = 0x08
    HANDSHAKE = 0x01  # AKA EncryptionData/Unlock   # Read data from flash memory


class MouseButton(IntEnum):
    """
    Mouse button indices matching the HELXAIRO UI button numbers.
    
    IMPORTANT: For Forward/Backward, the enum value matches UI button (minus 1),
    but the PHYSICAL address is swapped in set_button_mapping():
    - UI Button 4 (FORWARD) → uses addr 112 (physical forward)
    - UI Button 5 (BACKWARD) → uses addr 108 (physical backward)
    """
    LEFT_CLICK = 0       # UI Button 1 → addr 96
    RIGHT_CLICK = 1      # UI Button 2 → addr 100
    MIDDLE_CLICK = 2     # UI Button 3 → addr 104
    FORWARD = 3          # UI Button 4 → addr 112 (SWAPPED in code!)
    BACKWARD = 4         # UI Button 5 → addr 108 (SWAPPED in code!)
    DPI_SWITCH = 5       # UI Button 6 → addr 116


class ButtonAction(IntEnum):
    """
    Available actions that can be assigned to mouse buttons.
    
    Type mapping for HID protocol:
    - Type 0 = Disabled
    - Type 1 = Mouse Key Function (Left, Right, Middle, Forward, Backward)
    - Type 2 = DPI Switch (Loop, Plus, Minus)
    - Type 3 = Horizontal Scroll (Left, Right)
    - Type 11 = Vertical Scroll (Up, Down)
    """
    # Mouse Key Functions (Type 1)
    LEFT_CLICK = 1
    RIGHT_CLICK = 2
    MIDDLE_CLICK = 4
    FORWARD = 16
    BACKWARD = 8
    # DPI Functions (Type 2) - internal values, actual param sent separately
    DPI_PLUS = 100
    DPI_MINUS = 101
    DPI_LOOP = 102
    # Scroll Functions (Type 11 = Vertical, Type 3 = Horizontal)
    SCROLL_UP = 110      # Type 11, param 1
    SCROLL_DOWN = 111    # Type 11, param 2
    SCROLL_LEFT = 112    # Type 3, param 1
    SCROLL_RIGHT = 113   # Type 3, param 2
    # Multimedia Functions (Type 5 = ShortcutKey with HID Consumer Usage IDs)
    MEDIA_PLAY_PAUSE = 120   # 0x00CD
    MEDIA_NEXT = 121         # 0x00B5
    MEDIA_PREV = 122         # 0x00B6
    MEDIA_STOP = 123         # 0x00B7
    MEDIA_MUTE = 124         # 0x00E2
    MEDIA_VOL_UP = 125       # 0x00E9
    MEDIA_VOL_DOWN = 126     # 0x00EA
    # Disabled
    DISABLED = 0


class FurycubeHID:
    """
    Native USB HID interface for Furycube mouse hardware communication.
    
    This class provides direct USB HID access to read/write mouse configuration
    including button mappings, DPI settings, lighting effects, and macros.
    
    All communication happens over USB HID protocol - NO WEB OR NETWORK INVOLVED.
    
    Usage:
        hid_device = FurycubeHID()
        if hid_device.connect():
            hid_device.set_button_mapping(MouseButton.FORWARD, ButtonAction.LEFT_CLICK)
            hid_device.disconnect()
    """
    
    # Memory addresses for button configuration in flash storage
    # Button config starts at address 96, each button uses 4 bytes
    BUTTON_CONFIG_BASE_ADDR = 96
    BUTTON_CONFIG_SIZE = 4
    
    # ShortcutKey memory area - stores 32-byte shortcut payloads per button
    # Used by multimedia keys (Type 5) which need Press+Release event data
    SHORTCUT_KEY_BASE_ADDR = 256
    SHORTCUT_KEY_SLOT_SIZE = 32
    
    # DPI configuration addresses
    # DPI settings are stored in flash memory with specific addresses
    DPI_MAX_STAGES_ADDR = 2      # Number of active DPI stages (1-8)
    DPI_CURRENT_STAGE_ADDR = 4   # Currently active DPI stage (0-indexed)
    DPI_VALUES_BASE_ADDR = 12    # Base address for DPI values (4 bytes per stage)
    DPI_COLORS_BASE_ADDR = 44    # Base address for DPI colors (4 bytes per color)
    DPI_VALUE_SIZE = 4           # Bytes per DPI stage
    DPI_MIN = 50                 # Minimum DPI value
    DPI_MAX = 22000              # Maximum DPI value  
    DPI_STEP = 50                # DPI step size
    
    # Sensor Settings Addresses
    DPI_CURRENT_STAGE_ADDR_ALT = 7 # Sometimes used?
    LOD_ADDR = 10             # Lift Off Distance (1=1mm, 2=2mm)
    RIPPLE_ADDR = 177         # Ripple Control (0=Off, 1=On)
    ANGLE_SNAP_ADDR = 175     # Angle Snapping (0=Off, 1=On)
    MOTION_SYNC_ADDR = 171    # Motion Sync (0=Off, 1=On)
    HIGHEST_PERF_ADDR = 181   # Highest Performance (0=Off, 1=On)
    SENSOR_MODE_ADDR = 185    # Sensor Mode (0=LP/Office, 1=HP/Gaming)
    PERF_TIME_ADDR = 183      # Performance Time/Stage (Default 6)
    
    # DPI Lighting Addresses (Reverse engineered from app.js)
    DPI_EFFECT_MODE_ADDR = 76       # Effect Mode (0=Off, 1=Steady, 2=Breathing, etc.)
    DPI_EFFECT_BRIGHTNESS_ADDR = 78 # Brightness (Non-linear mapping 1-10 -> 16-255)
    DPI_EFFECT_SPEED_ADDR = 80      # Speed (1-10?)
    DPI_EFFECT_STATE_ADDR = 82      # Effect State (0=Off, 1=On)
    
    # Report ID used for all HID communication
    REPORT_ID = 8
    
    # Packet size for HID reports (excluding report ID)
    PACKET_SIZE = 16
    
    def __init__(self):
        """
        Initialize the Furycube HID interface.
        
        Sets up internal state but does not connect to the device.
        Call connect() to establish USB HID connection.
        """
        self._device: Optional[hid.device] = None
        self._connected: bool = False
        self._device: Optional[hid.device] = None
        self._connected: bool = False
        self._device_info: Optional[Dict] = None
        self._connection_type: str = "unknown"  # 'wireless' or 'wired'
        
    @property
    def connection_type(self) -> str:
        """Get current connection type: 'wireless', 'wired', or 'unknown'."""
        return self._connection_type
        
    def enumerate_devices(self) -> List[Dict]:
        """
        Enumerate all connected Furycube devices.
        
        Scans USB for devices matching the Furycube VID/PID.
        
        Returns:
            List of device info dictionaries containing:
            - path: Device path for opening
            - vendor_id: USB vendor ID
            - product_id: USB product ID
            - serial_number: Device serial (if available)
            - release_number: Device version
            - manufacturer_string: Manufacturer name
            - product_string: Product name
            - usage_page: HID usage page
            - usage: HID usage
            - interface_number: USB interface number
        """
        devices = []
        # Check Wireless
        devices.extend(hid.enumerate(FurycubeVID.VID, FurycubePID.PID))
        # Check Wired
        devices.extend(hid.enumerate(FurycubeVID.VID, FurycubePID.PID_WIRED))
        
        print(f"[FurycubeHID] Found {len(devices)} Furycube device(s)")
        for i, dev in enumerate(devices):
            pid = dev.get('product_id', 0)
            type_str = "Wired" if pid == FurycubePID.PID_WIRED else "Wireless"
            print(f"  [{i}] {dev.get('product_string', 'Unknown')} ({type_str}) "
                  f"(interface {dev.get('interface_number', '?')})")
        return devices
        
    def connect(self, device_path: Optional[str] = None) -> bool:
        """
        Connect to a Furycube mouse via USB HID.
        
        Establishes native USB HID connection for direct firmware communication.
        If no path specified, connects to the first available device.
        
        Args:
            device_path: Optional specific device path from enumerate_devices().
                        If None, connects to first available Furycube device.
        
        Returns:
            True if connection successful, False otherwise.
            
        Note:
            On Windows, you may need to run as Administrator for HID access.
            Some antivirus software may block direct HID communication.
        """
        try:
            self._device = hid.device()
            
            if device_path:
                # Connect to specific device by path
                self._device.open_path(device_path)
            else:
                # Connect to first available Furycube device
                devices = self.enumerate_devices()
                if not devices:
                    print("[FurycubeHID] ERROR: No Furycube device found")
                    return False
                
                # Prioritize usage_page=65282 (0xFF02) which is confirmed working
                # This is the correct vendor-specific interface for configuration
                target_usage_page = 65282  # 0xFF02
                priority_devices = [d for d in devices if d.get('usage_page') == target_usage_page]
                other_vendor = [d for d in devices if d.get('usage_page', 0) >= 0xFF00 and d.get('usage_page') != target_usage_page]
                standard = [d for d in devices if d.get('usage_page', 0) < 0xFF00]
                
                # Try priority first, then other vendor-specific, then standard
                sorted_devices = priority_devices + other_vendor + standard
                
                # Further sort to prioritize Wired PID (0xF511) if present
                # This ensures we pick the wired connection even if dongle is plugged in
                sorted_devices.sort(key=lambda x: 0 if x.get('product_id') == FurycubePID.PID_WIRED else 1)
                
                print(f"[FurycubeHID] Found {len(priority_devices)} devices with usage_page=65282")
                    
                for dev in sorted_devices:
                    try:
                        self._device.open_path(dev['path'])
                        self._device_info = dev
                        
                        # Set connection type based on PID
                        pid = dev.get('product_id', 0)
                        if pid == FurycubePID.PID_WIRED:
                            self._connection_type = "wired"
                        elif pid == FurycubePID.PID:
                            self._connection_type = "wireless"
                        else:
                            self._connection_type = "unknown"
                            
                        print(f"[FurycubeHID] Opened interface {dev.get('interface_number')} "
                              f"(usage_page={dev.get('usage_page')}) [{self._connection_type}]")
                        break
                    except Exception as e:
                        print(f"[FurycubeHID] Could not open interface {dev.get('interface_number')}: {e}")
                        continue
                        
            # Use BLOCKING mode for reliable flash writes
            # Non-blocking mode causes write timing issues with flash memory
            self._device.set_nonblocking(0)
            self._connected = True
            print(f"[FurycubeHID] Connected to {self._device_info.get('product_string', 'Furycube Mouse')}")
            
            # Send handshake to unlock the device for writing
            if self._send_handshake():
                print("[FurycubeHID] Handshake successful - device unlocked")
            else:
                print("[FurycubeHID] WARNING: Handshake failed - device may be read-only")
                
            return True
            
        except Exception as e:
            print(f"[FurycubeHID] Connection failed: {e}")
            self._connected = False
            return False
            
    def disconnect(self):
        """
        Disconnect from the Furycube mouse.
        
        Cleanly closes the USB HID connection and releases the device.
        Safe to call even if not connected.
        """
        if self._device:
            try:
                self._device.close()
                print("[FurycubeHID] Disconnected")
            except Exception as e:
                print(f"[FurycubeHID] Disconnect error: {e}")
        self._device = None
        self._connected = False
        self._device_info = None
        
    @property
    def is_connected(self) -> bool:
        """
        Check if device is currently connected.
        
        Returns:
            True if USB HID connection is active, False otherwise.
        """
        return self._connected and self._device is not None
        
    def _calculate_checksum(self, data: List[int]) -> int:
        """
        Calculate the Furycube protocol checksum for a packet.
        
        The checksum algorithm is: (85 - Sum of Bytes 0-14) - 8
        This ensures packet integrity during USB transmission.
        
        Args:
            data: List of 15 bytes (bytes 0-14 of packet, excluding checksum)
            
        Returns:
            Single byte checksum value (0-255)
        """
        byte_sum = sum(data[:15]) & 0xFF
        checksum = (85 - byte_sum - 8) & 0xFF
        return checksum
        
    def _build_packet(self, command: int, address: int, length: int, 
                      payload: List[int]) -> bytes:
        """
        Build a 16-byte HID packet for Furycube protocol.
        
        Constructs a properly formatted packet with header, payload, and checksum.
        
        Args:
            command: HID command type (HIDCommand.WRITE_FLASH or READ_FLASH)
            address: 16-bit memory address in flash storage
            length: Number of data bytes in payload (max 10)
            payload: List of data bytes to write (padded to 10 bytes)
            
        Returns:
            16-byte packet ready for transmission via sendReport()
        """
        packet = [0] * 16
        
        # Byte 0: Command/Service ID
        packet[0] = command
        
        # Byte 1: Reserved (always 0)
        packet[1] = 0
        
        # Bytes 2-3: Address (Big Endian)
        packet[2] = (address >> 8) & 0xFF  # High byte
        packet[3] = address & 0xFF          # Low byte
        
        # Byte 4: Data length
        packet[4] = length
        
        # Bytes 5-14: Payload data (padded with zeros)
        for i, byte in enumerate(payload[:10]):
            packet[5 + i] = byte
            
        # Byte 15: Checksum
        packet[15] = self._calculate_checksum(packet)
        
        return bytes(packet)
        
    def _send_packet(self, packet: bytes) -> bool:
        """
        Send a raw HID packet to the mouse.
        
        Transmits the packet using Report ID 8.
        
        Args:
            packet: 16-byte packet to send
            
        Returns:
            True if send successful, False otherwise.
        """
        if not self.is_connected:
            print("[FurycubeHID] ERROR: Not connected")
            return False
            
        try:
            # Prepend report ID to packet
            report = bytes([self.REPORT_ID]) + packet
            bytes_written = self._device.write(report)
            # print(f"[FurycubeHID] Sent {bytes_written} bytes: {packet.hex()}")
            return bytes_written > 0
        except Exception as e:
            print(f"[FurycubeHID] Send failed: {e}")
            return False

    def _send_handshake(self) -> bool:
        """
        Send the initial handshake (Magic Packet) to unlock the device.
        
        The device expects command 0x01 with 4 random bytes + 4 zeros.
        Without this, write commands (DPI, Polling Rate) are ignored.
        
        Returns:
            True if handshake sent successfully.
        """
        try:
            # Generate 4 random bytes (0-255)
            rand_bytes = [random.randint(0, 255) for _ in range(4)]
            # Remaining 4 bytes are zero
            payload = rand_bytes + [0, 0, 0, 0]
            
            # Command 0x01, Address 0x0000, Length 8
            packet = self._build_packet(
                command=HIDCommand.HANDSHAKE,
                address=0x0000,
                length=8,
                payload=payload
            )
            
            # Send packet
            return self._send_packet(packet)
            
        except Exception as e:
            print(f"[FurycubeHID] Handshake error: {e}")
            return False
            
            
    def _receive_packet(self, timeout_ms: int = 100, expected_cmd: int = None) -> Optional[bytes]:
        """
        Receive a HID packet from the mouse.
        
        Reads response data from the device with timeout.
        
        Args:
            timeout_ms: Maximum time to wait for response in milliseconds
            expected_cmd: Optional. If set, ignores packets with different Command ID.
            
        Returns:
            Received packet bytes, or None if no response/error.
        """
        if not self.is_connected:
            return None
            
        try:
            start_time = time.time()
            while True:
                # Calculate remaining timeout
                elapsed = (time.time() - start_time) * 1000
                remaining = max(1, int(timeout_ms - elapsed))
                if elapsed > timeout_ms:
                    return None
                    
                data = self._device.read(64, remaining)
                if data:
                    pkt = bytes(data)
                    # If we expect a specific command (e.g. READ_FLASH=8) and get something else 
                    # (e.g. STATUS_CHANGED=10), ignore and retry.
                    if expected_cmd is not None and len(pkt) > 0 and pkt[0] != expected_cmd:
                        # print(f"[FurycubeHID] Ignored unexpected packet cmd={pkt[0]}, expected={expected_cmd}")
                        continue
                    return pkt
                else:
                    # Timeout on read
                    return None
        except Exception as e:
            print(f"[FurycubeHID] Receive failed: {e}")
            return None
            
    def _flush_input(self):
        """Consume all pending input reports to clear the buffer."""
        if not self.is_connected:
            return
        
        try:
            # Read until empty with short timeout
            while True:
                data = self._device.read(64, timeout_ms=5)
                if not data:
                    break
        except:
            pass

    def set_button_mapping(self, button: MouseButton, action: ButtonAction) -> bool:
        """
        Set the action for a specific mouse button.
        
        Writes the button configuration to the mouse's flash memory.
        Changes take effect immediately on the hardware.
        
        Args:
            button: Which button to configure (MouseButton enum)
            action: The action to assign (ButtonAction enum)
            
        Returns:
            True if command sent successfully, False otherwise.
            
        Example:
            hid.set_button_mapping(MouseButton.FORWARD, ButtonAction.LEFT_CLICK)
        """
        import time
        
        # Calculate memory address for this button
        # IMPORTANT: Forward and Backward addresses are SWAPPED in firmware!
        # UI Button 4 (Forward) maps to physical Forward at addr 112
        # UI Button 5 (Backward) maps to physical Backward at addr 108
        BUTTON_ADDRESS_MAP = {
            MouseButton.LEFT_CLICK: 96,
            MouseButton.RIGHT_CLICK: 100,
            MouseButton.MIDDLE_CLICK: 104,
            MouseButton.FORWARD: 112,    # UI Btn 4 → addr 112 (Physical Front)
            MouseButton.BACKWARD: 108,   # UI Btn 5 → addr 108 (Physical Back)
            MouseButton.DPI_SWITCH: 116,
        }
        
        if button in BUTTON_ADDRESS_MAP:
            address = BUTTON_ADDRESS_MAP[button]
        else:
            # Fallback for unknown buttons
            address = self.BUTTON_CONFIG_BASE_ADDR + (button * self.BUTTON_CONFIG_SIZE)
        
        # Build payload based on action type
        # Format: [type, param_low, param_high, inner_checksum]
        # Inner Checksum = (85 - type - param_low - param_high) & 0xFF
        
        # Determine key type and param based on action
        # Type 0 = Disabled
        # Type 1 = MouseKey function (click actions)
        # Type 2 = DPISwitch function (DPI actions)
        # Type 3 = LeftRightRoll (Horizontal Scroll)
        # Type 11 = UpDownRoll (Vertical Scroll)
        if action in (ButtonAction.DPI_LOOP, ButtonAction.DPI_PLUS, ButtonAction.DPI_MINUS):
            # DPI functions use Type 2
            key_type = 2
            # DPI param values: Loop=1, Plus=2, Minus=3
            if action == ButtonAction.DPI_LOOP:
                param = 1
            elif action == ButtonAction.DPI_PLUS:
                param = 2
            else:  # DPI_MINUS
                param = 3
        elif action in (ButtonAction.SCROLL_UP, ButtonAction.SCROLL_DOWN):
            # Vertical scroll uses Type 11
            key_type = 11
            # Scroll Up=1, Scroll Down=2
            if action == ButtonAction.SCROLL_UP:
                param = 1
            else:  # SCROLL_DOWN
                param = 2
        elif action in (ButtonAction.SCROLL_LEFT, ButtonAction.SCROLL_RIGHT):
            # Horizontal scroll uses Type 3
            key_type = 3
            # Scroll Left=1, Scroll Right=2
            if action == ButtonAction.SCROLL_LEFT:
                param = 1
            else:  # SCROLL_RIGHT
                param = 2
        elif action in (ButtonAction.MEDIA_PLAY_PAUSE, ButtonAction.MEDIA_NEXT, 
                        ButtonAction.MEDIA_PREV, ButtonAction.MEDIA_STOP,
                        ButtonAction.MEDIA_MUTE, ButtonAction.MEDIA_VOL_UP, 
                        ButtonAction.MEDIA_VOL_DOWN):
            # Multimedia requires TWO writes:
            # 1. Write 8-byte shortcut payload to ShortcutKey memory (addr 256 + btn*32)
            # 2. Write button config with Type 5, param 0 (addr 96 + btn*4)
            
            # HID Consumer Usage ID mappings
            media_usage_ids = {
                ButtonAction.MEDIA_PLAY_PAUSE: 0x00CD,
                ButtonAction.MEDIA_NEXT: 0x00B5,
                ButtonAction.MEDIA_PREV: 0x00B6,
                ButtonAction.MEDIA_STOP: 0x00B7,
                ButtonAction.MEDIA_MUTE: 0x00E2,
                ButtonAction.MEDIA_VOL_UP: 0x00E9,
                ButtonAction.MEDIA_VOL_DOWN: 0x00EA,
            }
            usage_id = media_usage_ids[action]
            usage_low = usage_id & 0xFF
            usage_high = (usage_id >> 8) & 0xFF
            
            # Step 1: Build 8-byte shortcut payload
            # Format: [event_count, press_type, usage_low, usage_high, 
            #          release_type, usage_low, usage_high, checksum]
            # 0x82 = Press Media Key event
            # 0x42 = Release Media Key event
            shortcut_data = [0x02, 0x82, usage_low, usage_high, 0x42, usage_low, usage_high]
            shortcut_checksum = (85 - sum(shortcut_data)) & 0xFF
            shortcut_data.append(shortcut_checksum)
            
            # Write shortcut payload to ShortcutKey memory area
            # Use the PHYSICAL button index derived from config address
            # This ensures Forward/Backward swap is consistent
            physical_btn_index = (address - self.BUTTON_CONFIG_BASE_ADDR) // self.BUTTON_CONFIG_SIZE
            shortcut_addr = self.SHORTCUT_KEY_BASE_ADDR + (physical_btn_index * self.SHORTCUT_KEY_SLOT_SIZE)
            
            print(f"[FurycubeHID] Multimedia Step 1: Writing shortcut to addr {shortcut_addr} (btn_idx={physical_btn_index})")
            print(f"[FurycubeHID]   Shortcut data: {[hex(b) for b in shortcut_data]}")
            
            shortcut_packet = self._build_packet(
                command=HIDCommand.WRITE_FLASH,
                address=shortcut_addr,
                length=8,
                payload=shortcut_data
            )
            self._send_packet(shortcut_packet)
            
            # Read response to confirm write completed before sending next command
            if self._device:
                resp = self._device.read(64, timeout_ms=200)
                if resp:
                    print(f"[FurycubeHID]   Shortcut write response: cmd={resp[1] if len(resp) > 1 else '?'}")
            
            time.sleep(0.15)
            
            # Step 2: Write button config with Type 5, param 0
            # The mouse firmware uses the button index to find the shortcut slot
            key_type = 5
            param_low = 0
            param_high = 0
            inner_checksum = (85 - key_type - param_low - param_high) & 0xFF
            config_payload = [key_type, param_low, param_high, inner_checksum]
            
            print(f"[FurycubeHID] Multimedia Step 2: Writing config to addr {address}")
            print(f"[FurycubeHID]   Config data: {[hex(b) for b in config_payload]}")
            
            config_packet = self._build_packet(
                command=HIDCommand.WRITE_FLASH,
                address=address,
                length=4,
                payload=config_payload
            )
            self._send_packet(config_packet)
            
            # Read response to confirm config write
            if self._device:
                resp = self._device.read(64, timeout_ms=200)
                if resp:
                    print(f"[FurycubeHID]   Config write response: cmd={resp[1] if len(resp) > 1 else '?'}")
            
            time.sleep(0.1)
            
            print(f"[FurycubeHID] Button {button.name} mapped to {action.name} (type=5, usage=0x{usage_id:04X})")
            return True
            
        elif action == ButtonAction.DISABLED:
            # Disabled uses Type 0 with param 0
            key_type = 0
            param = 0
        else:
            # Mouse button actions use Type 1
            key_type = 1
            param = action  # 1=Left, 2=Right, 4=Middle, 8=Backward, 16=Forward
        
        param_low = param & 0xFF
        param_high = (param >> 8) & 0xFF
        inner_checksum = (85 - key_type - param_low - param_high) & 0xFF
        
        payload = [key_type, param_low, param_high, inner_checksum]
        
        # Build write packet
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=address,
            length=4,
            payload=payload
        )
        
        # Send write command
        self._send_packet(packet)
        time.sleep(0.1)
        
        print(f"[FurycubeHID] Button {button.name} mapped to {action.name} (type={key_type}, param={param})")
        return True
        
    def get_button_mapping(self, button: MouseButton) -> Optional[int]:
        """
        Read the current action assigned to a mouse button.
        
        Queries the mouse flash memory to get current configuration.
        
        Args:
            button: Which button to query (MouseButton enum)
            
        Returns:
            Current action value, or None if read failed.
        """
        address = self.BUTTON_CONFIG_BASE_ADDR + (button * self.BUTTON_CONFIG_SIZE)
        
        # Build read command packet
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=address,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        # Read response
        response = self._receive_packet(timeout_ms=100)
        if response and len(response) >= 8:
            # Parse button config from response
            # Bytes 5-8 contain: [type, param_high, param_low, sub_checksum]
            return response[7]  # param_low is the action value
        return None
        
    # ===== BATTERY =====
    
    # Battery voltage-to-percentage lookup table (21 points: 0% to 100% in 5% steps)
    # Extracted from ControlHub app.js - used for accurate battery level calculation
    BATTERY_VOLTAGE_TABLE = [
        3050, 3420, 3480, 3540, 3600, 3660, 3720, 3760, 3800, 3840,
        3880, 3920, 3940, 3960, 3980, 4000, 4020, 4040, 4060, 4080, 4110
    ]
    
    def get_battery_level(self) -> Optional[Tuple[int, bool]]:
        """
        Get battery level from the mouse using Command ID 4.
        
        Sends Command ID 4 to request battery status. Response contains:
        - Byte 5: Raw battery percentage (not used, voltage is more accurate)
        - Byte 6: Charging status (1=Charging, 0=Not Charging)
        - Bytes 7-8: Voltage in mV (Big Endian)
        
        The voltage is converted to percentage using a 21-point lookup table
        extracted from the official ControlHub web app for accuracy.
        
        Includes resilience against transient HID errors:
        - Flushes stale input data before sending request
        - Retries on exception with short delay (handles temporary device locks)
        - Tracks consecutive errors for caller-side backoff
        
        Returns:
            Tuple of (percentage: int, is_charging: bool), or None if failed.
        """
        if not self.is_connected:
            return None
        
        import time
        
        # Retry the entire send+read cycle on exception (transient HID errors)
        # This handles cases where the device buffer is dirty or temporarily locked
        max_exception_retries = 2
        for exc_attempt in range(max_exception_retries):
            try:
                # Flush any stale input data before sending battery request
                # This prevents reading old/queued responses from previous commands
                self._flush_input()
                
                # Build battery request packet (Command ID 4)
                packet = [0] * 16
                packet[0] = 4  # Command ID for battery
                
                # Checksum: (85 - sum(packet[0:15]) - 8) % 256
                pkt_sum = sum(packet[:15]) & 0xFF
                packet[15] = (85 - pkt_sum - 8) & 0xFF
                
                # Send with Report ID 8
                data_to_send = [self.REPORT_ID] + packet
                self._device.write(data_to_send)
                
                time.sleep(0.02)
                
                # Read response with retry (device may send StatusChanged notifications)
                # Note: Response includes Report ID at byte 0, so indices are shifted
                # [0]=ReportID, [1]=CmdID, [5]=?, [6]=RawBattery%, [7]=Charging, [8-9]=Voltage
                max_retries = 3
                for attempt in range(max_retries):
                    response = self._device.read(64, timeout_ms=200)
                    if response and len(response) >= 10:
                        # Command ID is at byte 1 (byte 0 is Report ID)
                        if response[1] == 4:
                            raw_percentage = response[6]  # Raw battery percentage
                            voltage_mv = (response[8] << 8) + response[9]  # Voltage in mV
                            
                            # Charging status: 1 = charging, 0 = not charging
                            # NOTE: When battery is full (~4160mV), charging becomes 0 even on dock
                            # because the battery is no longer actively drawing current
                            is_charging = response[7] == 1
                            
                            # Use voltage-based percentage for accuracy (same as ControlHub)
                            percentage = self._voltage_to_percentage(voltage_mv, is_charging)
                            print(f"[Battery] {voltage_mv}mV -> {percentage}%, charging={is_charging}")
                            
                            # Reset consecutive error counter on success
                            self._battery_error_count = 0
                            return (percentage, is_charging)
                        elif response[1] == 10:
                            # StatusChanged notification - device is telling us something changed
                            # Try reading again to get actual battery response
                            print(f"[Battery] Got StatusChanged notification, retrying ({attempt+1}/{max_retries})")
                            continue
                        else:
                            # Other command response, retry
                            print(f"[Battery] Wrong cmd: got {response[1]}, expected 4, retrying ({attempt+1}/{max_retries})")
                            continue
                    elif response:
                        print(f"[Battery] Short response: {len(response)} bytes, retrying ({attempt+1}/{max_retries})")
                        continue
                    else:
                        # Timeout/no response
                        print(f"[Battery] No response (attempt {attempt+1}/{max_retries})")
                        continue
                
                # All read retries exhausted
                print("[Battery] Failed after max retries")
                self._battery_error_count = getattr(self, '_battery_error_count', 0) + 1
                return None
                
            except Exception as e:
                # Transient HID error (device busy, buffer dirty, etc.)
                # Wait briefly and retry the entire cycle
                if exc_attempt < max_exception_retries - 1:
                    print(f"[FurycubeHID] Battery read error: {e}, retrying ({exc_attempt+1}/{max_exception_retries})")
                    time.sleep(0.05)
                    continue
                else:
                    # Final attempt also failed - track error for backoff
                    self._battery_error_count = getattr(self, '_battery_error_count', 0) + 1
                    print(f"[FurycubeHID] Battery read error: {e} (consecutive errors: {self._battery_error_count})")
                    return None
        
        return None
            
    def _voltage_to_percentage(self, voltage_mv: int, is_charging: bool) -> int:
        """
        Convert battery voltage (mV) to percentage using ControlHub lookup table.
        
        Uses linear interpolation between the 21 calibration points (5% steps).
        The table maps voltage ranges from 3050mV (0%) to 4110mV (100%).
        
        Args:
            voltage_mv: Battery voltage in millivolts
            is_charging: Whether the battery is currently charging
            
        Returns:
            Battery percentage (0-100)
        """
        C = self.BATTERY_VOLTAGE_TABLE
        
        # Handle out-of-range values
        if voltage_mv > C[-1]:
            return 99 if is_charging else 100
        if voltage_mv < C[0]:
            return 0
        
        # Linear interpolation between table points
        for i in range(1, len(C)):
            if voltage_mv < C[i]:
                lower = C[i - 1]
                upper = C[i]
                step_size = (upper - lower) / 5.0
                percentage = ((voltage_mv - lower) / step_size) + (5 * (i - 1))
                return min(100, max(0, round(percentage)))
                
        return 100

    def set_dpi(self, stage: int, dpi_value: int) -> bool:
        """
        Set the DPI value for a specific DPI stage.
        
        The mouse supports up to 8 DPI stages, each can have a different DPI value.
        
        Args:
            stage: DPI stage index (0-7)
            dpi_value: DPI value (50-22000, must be divisible by 50)
            
        Returns:
            True if command sent successfully, False otherwise.
            
        Example:
            # Set stage 1 to 800 DPI
            hid.set_dpi(0, 800)
            
            # Set stage 2 to 1600 DPI
            hid.set_dpi(1, 1600)
        """
        import time
        
        # Validate inputs
        if not 0 <= stage <= 7:
            print(f"[FurycubeHID] Error: Invalid DPI stage {stage} (must be 0-7)")
            return False
            
        if not self.DPI_MIN <= dpi_value <= self.DPI_MAX:
            print(f"[FurycubeHID] Error: DPI value {dpi_value} out of range ({self.DPI_MIN}-{self.DPI_MAX})")
            return False
            
        if dpi_value % self.DPI_STEP != 0:
            dpi_value = (dpi_value // self.DPI_STEP) * self.DPI_STEP
            print(f"[FurycubeHID] Warning: DPI rounded to {dpi_value}")
        
        # Calculate raw value: v = DPI / 50
        raw_value = dpi_value // self.DPI_STEP
        
        # Calculate address for this stage
        address = self.DPI_VALUES_BASE_ADDR + (stage * self.DPI_VALUE_SIZE)
        
        # Build DPI payload (4 bytes based on 'It' function in app.js):
        # The DPI Write function uses 'ct' (buffer write) not 'ut' (byte write)
        # Byte 0: Low 8 bits
        # Byte 1: Duplicate of Byte 0
        # Byte 2: High bits packed: (high << 2) | (high << 6) | dpiEx
        # Byte 3: Checksum
        low_byte = raw_value & 0xFF
        high_bits = (raw_value >> 8) & 0x03
        
        # Standard range (dpiEx=0)
        packed_high = ((high_bits << 2) | (high_bits << 6)) & 0xFF
        
        inner_checksum = (85 - low_byte - low_byte - packed_high) & 0xFF
        
        payload = [low_byte, low_byte, packed_high, inner_checksum]
        
        # Build write packet (Length 4)
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=address,
            length=4,
            payload=payload
        )
        
        # Send write command
        self._send_packet(packet)
        time.sleep(0.01)
        
        print(f"[FurycubeHID] DPI stage {stage} set to {dpi_value} (Raw: {raw_value})")
        return True

    def set_dpi_color(self, stage: int, r: int, g: int, b: int) -> bool:
        """
        Set the LED color for a specific DPI stage.
        
        Args:
            stage: DPI stage index (0-7)
            r, g, b: RGB color values (0-255)
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        if not 0 <= stage <= 7:
            print(f"[FurycubeHID] Error: Invalid DPI stage {stage}")
            return False
            
        # Address calculation: 44 (0x2C) + stage * 4
        DPI_COLOR_BASE_ADDR = 44
        address = DPI_COLOR_BASE_ADDR + (stage * 4)
        
        # Payload: [R, G, B, Checksum]
        # Checksum = 85 - (R + G + B)
        byte_sum = (r + g + b) & 0xFF
        checksum = (85 - byte_sum) & 0xFF
        
        payload = [r, g, b, checksum]
        
        # Build packet (Length 4)
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=address,
            length=4,
            payload=payload
        )
        
        if self._send_packet(packet):
            print(f"[FurycubeHID] DPI stage {stage} color set to RGB({r}, {g}, {b})")
            time.sleep(0.01)
            return True
            
        return False

    def get_dpi(self, stage: int) -> Optional[int]:
        """
        Read the DPI value for a specific stage.
        
        Args:
            stage: DPI stage index (0-7)
            
        Returns:
            DPI value, or None if read failed.
        """
        if not 0 <= stage <= 7:
            return None
            
        address = self.DPI_VALUES_BASE_ADDR + (stage * self.DPI_VALUE_SIZE)
        
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=address,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 8:
            # Parse DPI from response
            # Bytes 6-7 contain low byte repeated
            low_byte = response[6]
            packed_high = response[8] if len(response) > 8 else 0
            high_bits = (packed_high >> 2) & 0x03
            raw_value = (high_bits << 8) | low_byte
            dpi_value = (raw_value + 1) * self.DPI_STEP
            return dpi_value
        return None

    def set_current_dpi_stage(self, stage: int) -> bool:
        """
        Set the currently active DPI stage.
        
        Args:
            stage: DPI stage index (0-7)
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        if not 0 <= stage <= 7:
            print(f"[FurycubeHID] Error: Invalid DPI stage {stage}")
            return False
        
        # Payload for current stage: [stage, 85-stage] from HIDHandle.js
        val = stage & 0xFF
        inv_val = (85 - val) & 0xFF
        payload = [val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_CURRENT_STAGE_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        
        print(f"[FurycubeHID] Active DPI stage set to {stage}")
        return True

    def get_current_dpi_stage(self) -> Optional[int]:
        """
        Get the currently active DPI stage.
        
        Returns:
            Current stage index (0-7), or None if read failed.
        """
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.DPI_CURRENT_STAGE_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 7:
            return response[6]  # Stage index
        return None

    def set_dpi_stages_count(self, count: int) -> bool:
        """
        Set the number of active DPI stages (1-8).
        
        Args:
            count: Number of stages to enable (1-8)
            
        Returns:
            True if command sent successfully.
        """
        import time
        if not 1 <= count <= 8:
            print(f"[FurycubeHID] Error: Invalid stage count {count}")
            return False
            
        # Payload: [count, 85-count] from HIDHandle.js
        val = count & 0xFF
        inv_val = (85 - val) & 0xFF
        payload = [val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_MAX_STAGES_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        
        print(f"[FurycubeHID] Active DPI stages set to {count}")
        return True

    def get_dpi_stages_count(self) -> Optional[int]:
        """Get the number of active DPI stages."""
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.DPI_MAX_STAGES_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 7:
            count = response[6]
            return count if 1 <= count <= 8 else 6
        return None

    def set_polling_rate(self, rate_hz: int) -> bool:
        """
        Set the mouse polling rate.
        
        Args:
            rate_hz: Polling rate in Hz (125, 250, 500, 1000)
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        # Protocol mapping:
        # 125Hz  = 8
        # 250Hz  = 4
        # 500Hz  = 2
        # 1000Hz = 1
        rate_map = {
            125: 8,
            250: 4,
            500: 2,
            1000: 1,
            2000: 32,
            4000: 64,
            8000: 128
        }
        
        if rate_hz not in rate_map:
            print(f"[FurycubeHID] Error: Invalid polling rate {rate_hz}Hz")
            return False
            
        value = rate_map[rate_hz]
        
        # Address 0, Payload: [value, 85-value] from HIDHandle.js
        inv_val = (85 - value) & 0xFF
        payload = [value, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=0,  # Polling rate address
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        
        print(f"[FurycubeHID] Polling rate set to {rate_hz}Hz")
        return True

    def get_polling_rate(self) -> Optional[int]:
        """Get current polling rate in Hz."""
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=0,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 7:
            val = response[6]
            # Reverse mapping
            val_map = {
                8: 125, 4: 250, 2: 500, 1: 1000,
                32: 2000, 64: 4000, 128: 8000
            }
            return val_map.get(val, 1000)
        return None


        return None


    DEBOUNCE_TIME_ADDR = 169

    def set_debounce_time(self, ms: int) -> bool:
        """
        Set the key response debounce time.
        
        Args:
            ms: Time in milliseconds (0-30).
            
        Returns:
            True if successful.
        """
        import time
        
        # Validation
        if not 0 <= ms <= 30:
            print(f"[FurycubeHID] Warning: Debounce {ms}ms out of typical range (0-30)")
            
        # Payload logic verified from app.js
        # Byte 0: 0x07 (Write Flash) - handled by _build_packet
        # Byte 4: 0x02 (Sub-command/Length) - handled by length param
        # Byte 5: Value
        # Byte 6: Verify (0x55 - Value)
        # Byte 7: Constant 0x4D (77)
        
        verify = (0x55 - ms) & 0xFF
        constant = 0x4D
        
        # We pass length=2 to set Byte 4 to 0x02
        # We include the constant in payload so it gets written to Byte 7
        payload = [ms, verify, constant]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DEBOUNCE_TIME_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Debounce set to {ms}ms")
        return True

    def set_lod(self, lod_value: int) -> bool:
        """
        Set Lift Off Distance (LOD).
        
        Args:
            lod_value: 1 for 1mm, 2 for 2mm.
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        if lod_value not in [1, 2]:
            print(f"[FurycubeHID] Error: Invalid LOD value {lod_value}")
            return False
            
        # Address 10 (0x0A) for LOD
        # Value 1 = 1mm, Value 2 = 2mm
        # Payload: [Value, 05, 01, Checksum]
        # Checksum = 85 - (Value + 05 + 01)
        
        verify = 5
        constant = 1
        
        payload = [lod_value, verify, constant]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.LOD_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] LOD set to {lod_value}mm")
        return True

    def set_ripple(self, enabled: bool) -> bool:
        """
        Set Ripple Control.
        
        Args:
            enabled: True to enable, False to disable.
        """
        import time
        value = 1 if enabled else 0
        inv_val = (85 - value) & 0xFF
        payload = [value, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.RIPPLE_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Ripple set to {'On' if enabled else 'Off'}")
        return True

    def set_angle_snapping(self, enabled: bool) -> bool:
        """
        Set Angle Snapping.
        
        Args:
            enabled: True to enable, False to disable.
        """
        import time
        value = 1 if enabled else 0
        inv_val = (85 - value) & 0xFF
        payload = [value, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.ANGLE_SNAP_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Angle Snapping set to {'On' if enabled else 'Off'}")
        return True

    def set_motion_sync(self, enabled: bool) -> bool:
        """
        Set Motion Sync.
        
        Args:
            enabled: True to enable, False to disable.
        """
        import time
        value = 1 if enabled else 0
        inv_val = (85 - value) & 0xFF
        payload = [value, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.MOTION_SYNC_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Motion Sync set to {'On' if enabled else 'Off'}")
        return True

    def set_highest_performance(self, enabled: bool) -> bool:
        """
        Set Highest Performance Mode (Peak Performance).
        
        Args:
            enabled: True for On (Peak), False for Off (Standard).
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        # Address 181 (0xB5)
        val = 1 if enabled else 0
        verify = (0x55 - val) & 0xFF
        constant = 0x4D
        
        payload = [val, verify, constant]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.HIGHEST_PERF_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Highest Performance set to {'On' if enabled else 'Off'}")
        return True

    def set_sensor_mode(self, mode: int) -> bool:
        """
        Set Sensor Mode (LP vs HP).
        
        Args:
            mode: 0 for LP (Low Power/Office), 1 for HP (High Power/Gaming).
            
        Returns:
            True if command sent successfully.
        """
        import time
        
        if mode not in [0, 1]:
            print(f"[FurycubeHID] Error: Invalid Sensor Mode {mode}")
            return False
            
        # Address 185 (0xB9)
        val = mode
        verify = (0x55 - val) & 0xFF
        constant = 0x4D
        
        payload = [val, verify, constant]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.SENSOR_MODE_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        mode_str = "HP (Gaming)" if mode == 1 else "LP (Office)"
        print(f"[FurycubeHID] Sensor Mode set to {mode_str}")
        return True


    def get_sensor_mode(self) -> Optional[int]:
        """
        Get Sensor Mode.
        
        Returns:
            0 for LP, 1 for HP.
        """
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.SENSOR_MODE_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 7:
            return response[5]
        return None

    def get_highest_performance(self) -> Optional[bool]:
        """
        Get Highest Performance Mode.
        
        Returns:
            True if On, False if Off.
        """
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.HIGHEST_PERF_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=500)
        if response and len(response) >= 7:
            return response[5] == 1
        return None

    def set_performance_time(self, minutes: int) -> bool:
        """
        Set Performance Time (Sleep time?).
        
        Args:
            minutes:
                1 = 10s
                2 = 30s
                3 = 1min
                4 = 2min
                5 = 5min
                6 = 10min
                (Mapping based on common mouse behavior, value is likely an index)
        """
        import time
        
        if not 1 <= minutes <= 6:
            print(f"[FurycubeHID] Error: Invalid perf time index {minutes}")
            return False
            
        # Address 183
        val = minutes
        verify = (0x55 - val) & 0xFF
        constant = 0x4D
        
        payload = [val, verify, constant]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.PERF_TIME_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] Performance Time index set to {val}")
        return True

    def get_performance_time(self) -> Optional[int]:
        """Get Performance Time index (1-6)."""
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.PERF_TIME_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=100)
        if response and len(response) >= 7:
            return response[5]
        return None

    

    def set_dpi_stage_value(self, stage_index: int, dpi: int) -> bool:
        """
        Set DPI value for a specific stage.
        Writes to flash memory Address 12 + (index * 4).
        Uses PAW3311 Logic (Sensor with Lookup Table).
        """
        import time
        if not 0 <= stage_index <= 7:
            return False
            
        # PAW3311 Lookup Table (Extracted from sensor.json)
        # Values skipped (e.g. 7, 13, 20...) are invalid for this sensor register.
        PAW3311_VALUES = [
            1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 27, 28, 29, 
            30, 31, 32, 34, 35, 36, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 50, 51, 52, 54, 55, 56, 
            57, 58, 59, 61, 62, 63, 64, 65, 67, 68, 69, 70, 71, 72, 74, 75, 76, 77, 78, 79, 81, 82, 83, 
            84, 85, 87, 88, 89, 90, 91, 92, 94, 95, 96, 97, 98, 99, 101, 102, 103, 104, 105, 107, 108, 
            109, 110, 111, 112, 114, 115, 116, 117, 118, 119, 121, 122, 123, 124, 125, 127, 128, 129, 
            130, 131, 132, 134, 135, 136, 137, 138, 139, 141, 142, 143, 144, 145, 147, 148, 149, 150, 
            151, 152, 154, 155, 156, 157, 158, 159, 161, 162, 163, 164, 165, 167, 168, 169, 170, 171, 
            172, 174, 175, 176, 177, 178, 179, 181, 182, 183, 184, 185, 187, 188, 189, 190, 191, 192, 
            194, 195, 196, 197, 198, 199, 201, 202, 203, 204, 205, 207, 208, 209, 210, 211, 212, 214, 
            215, 216, 217, 218, 219, 221, 222, 223, 224, 225, 227, 228, 229, 230, 231, 232, 234, 235
        ]

        val = 0
        dpi_ex = 0
        
        # Range Determination & Calculation
        # Range 1: 50-10000, Step 50, Div 1, DPIEx 0
        if dpi <= 10000:
            divisor = 1
            step = 50
            dpi_ex = 0
            # Calc index
            s = dpi // divisor
            idx = (s - 50) // 50
            if 0 <= idx < len(PAW3311_VALUES):
                val = PAW3311_VALUES[idx]
            else:
                val = max(1, s // 50) # Fallback
                
        # Range 2: 10100-12000, Step 100, Div 2, DPIex: 34 (0x22)
        elif dpi <= 12000:
            divisor = 2
            step = 100
            dpi_ex = 34 # 0x22
            s = dpi // divisor
            idx = (s - 50) // 50
            if 0 <= idx < len(PAW3311_VALUES):
                val = PAW3311_VALUES[idx]
            else:
                val = PAW3311_VALUES[-1]
                
        # Range 3: 12100-20000, Step 100, Div 2, DPIex: 17 (0x11)
        elif dpi <= 20000:
            divisor = 2
            step = 100
            dpi_ex = 17 # 0x11
            s = dpi // divisor
            idx = (s - 50) // 50
            if 0 <= idx < len(PAW3311_VALUES):
                val = PAW3311_VALUES[idx]
            else:
                val = PAW3311_VALUES[-1]
                
        # Range 4: 20200-24000+, Step 200, Div 4, DPIex: 51 (0x33)
        elif dpi > 20000:
            divisor = 4
            step = 200
            dpi_ex = 51 # 0x33
            s = dpi // divisor
            idx = (s - 50) // 50
            if 0 <= idx < len(PAW3311_VALUES):
                val = PAW3311_VALUES[idx]
            else:
                val = PAW3311_VALUES[-1]

        # Construct 4-byte payload (Standard Furycube Payload Logic)
        p0 = val & 0xFF
        p1 = val & 0xFF
        n = (val >> 8) & 0xFF
        p2 = ((n << 2) | (n << 6)) & 0xFF
        p2 |= dpi_ex
        
        checksum_sum = (p0 + p1 + p2) & 0xFF
        p3 = (85 - checksum_sum) & 0xFF
        
        payload = [p0, p1, p2, p3]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_VALUES_BASE_ADDR + (stage_index * 4),
            length=4,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] DPI Stage {stage_index+1} Value set to {dpi} (PAW3311 Val: {val}, Ex: {dpi_ex})")
        return True

    def set_dpi_color(self, stage_index: int, r: int, g: int, b: int) -> bool:
        """
        Set LED color for a specific DPI stage.
        
        Args:
            stage_index: DPI stage index (0-7)
            r, g, b: RGB color values (0-255)
            
        Returns:
            True if command sent successfully.
        """
        import time
        if not 0 <= stage_index <= 7:
            return False
            
        # Color format: [R, G, B, (85 - R - G - B) & 0xFF]
        inner_checksum = (85 - r - g - b) & 0xFF
        payload = [r, g, b, inner_checksum]
        
        address = self.DPI_COLORS_BASE_ADDR + (stage_index * 4)
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=address,
            length=4,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] DPI Stage {stage_index+1} Color set to ({r}, {g}, {b})")
        return True

    def get_active_dpi_stage(self) -> Optional[int]:
        """Get currently active DPI stage index (0-7)."""
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.DPI_CURRENT_STAGE_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        # Filter for READ_FLASH response (Command 8) to avoid reading Status Changed (Command 10)
        # reports that might come from button presses.
        response = self._receive_packet(timeout_ms=100, expected_cmd=HIDCommand.READ_FLASH)
        if response and len(response) >= 6:
            # Usually index 5 contains the data at offset 0
            return response[5]
        return None
    
    def set_sleep_time(self, index: int) -> bool:
        """
        Set Sleep Time.
        Placeholder: Address unknown.
        """
        print(f"[FurycubeHID] Set Sleep Time to index {index} (Not Implemented)")
        return True

    def set_long_distance_mode(self, enabled: bool) -> bool:
        """
        Set Long Distance Mode.
        Placeholder: Address unknown.
        """
        print(f"[FurycubeHID] Set Long Distance Mode to {enabled} (Not Implemented)")
        return True

    def set_dpi_effect_mode(self, mode: int) -> bool:
        """
        Set the DPI lighting effect mode.
        
        Args:
            mode: Effect mode index (0-10)
            
        Returns:
            True if command sent successfully.
        """
        import time
        val = mode & 0xFF
        inv_val = (85 - val) & 0xFF
        payload = [val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_EFFECT_MODE_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        
        if mode > 0:
            self.set_dpi_effect_state(True)
            
        print(f"[FurycubeHID] DPI Effect Mode set to {mode}")
        return True

    def set_dpi_effect_state(self, enabled: bool) -> bool:
        """Set DPI lighting effect state (On/Off)."""
        import time
        val = 1 if enabled else 0
        inv_val = (85 - val) & 0xFF
        payload = [val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_EFFECT_STATE_ADDR,
            length=2,
            payload=payload
        )
        self._send_packet(packet)
        time.sleep(0.01)
        return True

    def _brightness_to_byte(self, level: int) -> int:
        """Map brightness level 1-10 to byte value."""
        mapping = {
            1: 16,
            2: 30,
            3: 60,
            4: 90,
            5: 128, 
            6: 150,
            7: 180,
            8: 210,
            9: 230,
            10: 255
        }
        return mapping.get(level, 128)

    def set_dpi_effect_brightness(self, level: int) -> bool:
        """Set DPI lighting brightness (1-5)."""
        import time
        if not 1 <= level <= 5:
            level = 3
            
        byte_val = self._brightness_to_byte(level)
        inv_val = (85 - byte_val) & 0xFF
        
        # Payload only needs value and complement, zero padded by _build_packet
        payload = [byte_val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_EFFECT_BRIGHTNESS_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] DPI Brightness set to {level} (Val: {byte_val})")
        return True

    def get_dpi_effect_brightness(self) -> Optional[int]:
        """Get current DPI lighting brightness (1-10)."""
        packet = self._build_packet(
            command=HIDCommand.READ_FLASH,
            address=self.DPI_EFFECT_BRIGHTNESS_ADDR,
            length=4,
            payload=[]
        )
        
        if not self._send_packet(packet):
            return None
            
        response = self._receive_packet(timeout_ms=100)
        if response and len(response) >= 7:
            val = response[6]
            # Reverse map byte to level
            mapping = {
                16: 1, 30: 2, 60: 3, 90: 4, 128: 5,
                150: 6, 180: 7, 210: 8, 230: 9, 255: 10
            }
            # Find closest match if exact not found
            if val not in mapping:
                return 5
            return mapping[val]
        return None

    def set_dpi_effect_speed(self, speed: int) -> bool:
        """
        Set DPI lighting speed (1-5).
        
        Sends the speed value directly to firmware.
        Firmware uses internal lookup table for actual delay values.
        
        Args:
            speed: 1-5 (1=Slowest, 5=Fastest)
            
        Note:
            Firmware only supports 1-5. Values 6-10 cause unpredictable behavior.
        """
        import time
        if not 1 <= speed <= 5:
            speed = 3  # Default to middle speed
        
        # Send speed value directly to firmware.
        # Payload format: [value, 85-value] (complement rule).
        val = speed & 0xFF
        inv_val = (85 - val) & 0xFF
        payload = [val, inv_val]
        
        packet = self._build_packet(
            command=HIDCommand.WRITE_FLASH,
            address=self.DPI_EFFECT_SPEED_ADDR,
            length=2,
            payload=payload
        )
        
        self._send_packet(packet)
        time.sleep(0.01)
        print(f"[FurycubeHID] DPI Speed set to {speed}")
        return True


# Convenience function for quick testing
def test_connection():
    """
    Quick test function to verify Furycube HID communication.
    
    Attempts to connect to the mouse and read battery level.
    Useful for debugging and verifying driver compatibility.
    """
    print("="*50)
    print("Furycube HID Connection Test")
    print("="*50)
    
    device = FurycubeHID()
    
    # List all devices
    devices = device.enumerate_devices()
    if not devices:
        print("\nNo Furycube device found!")
        print("Make sure the 2.4G wireless receiver is plugged in.")
        return
        
    # Try to connect
    if device.connect():
        print("\nConnection successful!")
        
        # Try reading battery
        battery = device.get_battery_level()
        if battery is not None:
            print(f"Battery level: {battery}%")
        else:
            print("Could not read battery level")
            
        device.disconnect()
    else:
        print("\nConnection failed!")
        print("Try running as Administrator on Windows.")


def test_button_mapping():
    """
    Test button mapping functionality on the mouse.
    
    Changes button 3 (Forward) to Left Click and back.
    """
    print("=" * 50)
    print("Furycube Button Mapping Test")
    print("=" * 50)
    
    device = FurycubeHID()
    
    if device.connect():
        print("\nSetting Forward button (3) to Left Click...")
        success = device.set_button_mapping(MouseButton.FORWARD, ButtonAction.LEFT_CLICK)
        
        if success:
            print("\nSUCCESS! Command sent to mouse.")
            print("Try pressing the Forward button - it should now act as Left Click!")
            print("\nPress Enter to restore original mapping...")
            input()
            
            print("Restoring Forward button to original function...")
            device.set_button_mapping(MouseButton.FORWARD, ButtonAction.FORWARD)
            print("Done!")
        else:
            print("Failed to send command")
            
        device.disconnect()
    else:
        print("\nConnection failed!")




if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "button":
        test_button_mapping()
    else:
        test_connection()

