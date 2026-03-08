"""
Test script for Furycube HID communication.
Tries all interfaces to find which one works for sending commands.
"""
import hid

def test_all_interfaces():
    """Test write() on all available Furycube interfaces."""
    devices = hid.enumerate(0x3554, 0xF5D5)
    print(f"Found {len(devices)} Furycube interfaces\n")
    
    # Test packet: Set button 3 (Forward) to Left Click (action=1)
    # Address 108 = 96 + (3 * 4)
    packet = [8,  # Report ID
              7,  # Write Flash command
              0,  # Reserved
              0, 108,  # Address (Big Endian)
              4,  # Length
              1, 0, 1, 85,  # Payload: [type, param_high, param_low, sub_checksum]
              0, 0, 0, 0, 0, 0,  # Padding
              127]  # Checksum placeholder
    
    for i, d in enumerate(devices):
        usage_page = d.get('usage_page')
        interface = d.get('interface_number')
        print(f"[{i}] Testing interface {interface} (usage_page={usage_page})")
        
        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)
            
            # Try write()
            try:
                result = dev.write(packet)
                print(f"    write() = {result}")
                if result > 0:
                    print(f"    SUCCESS! Interface {interface} accepts writes")
            except Exception as e:
                print(f"    write() error: {e}")
            
            dev.close()
        except Exception as e:
            print(f"    Open error: {e}")
    
    print("\n" + "="*50)
    print("Test complete!")

if __name__ == "__main__":
    test_all_interfaces()
