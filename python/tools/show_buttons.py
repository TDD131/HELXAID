"""Show all button configs"""
import hid
import time

VID, PID = 0x3554, 0xF5D5

dev = None
for d in hid.enumerate(VID, PID):
    if d.get('usage_page') == 65282:
        dev = hid.device()
        dev.open_path(d['path'])
        dev.set_nonblocking(0)
        break

def cs(d): return (85 - sum(d[:15]) - 8) & 0xFF

actions = {1:'Left', 2:'Right', 4:'Middle', 8:'Fwd', 16:'Back'}

for btn in range(6):
    addr = 96 + (btn * 4)
    pkt = [8, 0x08, 0, 0, addr, 4] + [0]*10
    pkt.append(cs(pkt[1:]))
    dev.write(pkt)
    time.sleep(0.1)
    r = dev.read(64, 500)
    data = r[6:10]
    act = data[1]
    name = actions.get(act, f'?{act}')
    print(f'Btn{btn} addr{addr}: {name}')

dev.close()
