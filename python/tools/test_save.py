"""Test write + save sequence for Furycube HID"""
import hid
import time

VID, PID = 0x3554, 0xF5D5
REPORT_ID = 8

def cs(d): return (85 - sum(d[:15]) - 8) & 0xFF

dev = None
for d in hid.enumerate(VID, PID):
    if d.get('usage_page') == 65282:
        dev = hid.device()
        dev.open_path(d['path'])
        dev.set_nonblocking(0)
        break

if not dev:
    print("ERROR: No device found with usage_page=65282")
    exit(1)

print('=== Testing Write + Save Sequence ===')

# Button 3 (Forward) at address 108
addr = 108
read_pkt = [0x08, 0, 0, addr, 4] + [0]*10
read_pkt.append(cs(read_pkt))

# Read before
dev.write([REPORT_ID] + read_pkt)
time.sleep(0.1)
r = dev.read(64, 500)
print(f'Before: {bytes(r[5:9]).hex()} (action={r[7]})')

# Write new config - Type=4, sub=1, action=1 (Left Click), padding=0
write_pkt = [0x07, 0, 0, addr, 4, 4, 1, 1, 0] + [0]*6
write_pkt.append(cs(write_pkt))
print(f'Write packet: {bytes([REPORT_ID] + write_pkt).hex()}')
dev.write([REPORT_ID] + write_pkt)
time.sleep(0.2)
r = dev.read(64, 500)
if r:
    print(f'Write response: {bytes(r).hex()}')

# Try each save command and check result
print('\nTrying save commands:')
for cmd in [0x06, 0x09, 0x0A, 0x0B, 0x0C]:
    save_pkt = [cmd] + [0]*14
    save_pkt.append(cs(save_pkt))
    dev.write([REPORT_ID] + save_pkt)
    time.sleep(0.15)
    
    # Read back
    dev.write([REPORT_ID] + read_pkt)
    time.sleep(0.1)
    r = dev.read(64, 500)
    if r:
        action = r[7]
        status = 'CHANGED!' if action == 1 else 'unchanged'
        print(f'  Cmd 0x{cmd:02X} -> action={action} ({status})')
        if action == 1:
            print('\n*** SUCCESS! Forward button now set to Left Click! ***')
            break

dev.close()
print('\nDone - try pressing Forward button on mouse!')
