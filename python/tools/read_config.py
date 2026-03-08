"""Read button config to verify write"""
import hid
import time

VID, PID = 0x3554, 0xF5D5

def cs(d): 
    return (85 - sum(d[:15]) - 8) & 0xFF

dev = None
for d in hid.enumerate(VID, PID):
    if d.get('usage_page') == 65282:
        dev = hid.device()
        dev.open_path(d['path'])
        dev.set_nonblocking(0)
        break

if not dev:
    print("No device")
    exit(1)

# Read button 3 config
addr = 108
pkt = [8, 0x08, 0, 0, addr, 4] + [0]*10
pkt.append(cs(pkt[1:]))
dev.write(pkt)
time.sleep(0.1)
r = dev.read(64, 500)

codes = {1:'Left', 2:'Right', 4:'Middle', 8:'Forward', 16:'Backward'}
p = r[5:9]
action_name = codes.get(p[2], 'unknown')
print(f'Button 3 config: {bytes(p).hex()}')
print(f'Type={p[0]} ParamH={p[1]} ParamL={p[2]} InnerCS={p[3]:02x}')
print(f'Action: {action_name}')

dev.close()
