
import hid

VID = 0x3554

print(f"Scanning for devices with VID 0x{VID:04X}...")
try:
    devices = hid.enumerate(VID, 0)
    print(f"Found {len(devices)} devices:")
    seen_pids = set()
    for d in devices:
        pid = d['product_id']
        name = d.get('product_string', 'Unknown')
        usage_page = d.get('usage_page', 0)
        interface = d.get('interface_number', -1)
        print(f"- PID: 0x{pid:04X} | Product: {name} | Interface: {interface} | UsagePage: {usage_page}")
        seen_pids.add(pid)
        
    print("\nUnique PIDs found:", [f"0x{p:04X}" for p in seen_pids])
    
except Exception as e:
    print(f"Error: {e}")
