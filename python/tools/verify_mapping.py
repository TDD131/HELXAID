"""Final verification test for button mapping"""
from FurycubeHID import FurycubeHID, MouseButton, ButtonAction
import time
import hid

def verify():
    dev = FurycubeHID()
    if dev.connect():
        print('=== Testing Button Mapping ===')
        print()
        
        # Change to Left Click
        print('Changing Forward button to Left Click...')
        dev.set_button_mapping(MouseButton.FORWARD, ButtonAction.LEFT_CLICK)
        
        dev.disconnect()
        
        # Verify by reading directly
        print()
        print('Verifying via direct read...')
        for d in hid.enumerate(0x3554, 0xF5D5):
            if d.get('usage_page') == 65282:
                rd = hid.device()
                rd.open_path(d['path'])
                rd.set_nonblocking(0)
                
                def cs(x): return (85 - sum(x[:15]) - 8) & 0xFF
                
                addr = 108
                pkt = [0x08, 0, 0, addr, 4] + [0]*10
                pkt.append(cs(pkt))
                rd.write([8] + pkt)
                time.sleep(0.1)
                r = rd.read(64, 500)
                
                codes = {1:'Left Click', 2:'Right Click', 4:'Middle', 8:'Forward', 16:'Backward'}
                action = r[7]
                name = codes.get(action, 'unknown')
                print(f'   Forward button action = {action} ({name})')
                
                if action == 1:
                    print()
                    print('*** SUCCESS! Forward button is now Left Click! ***')
                    print('TRY PRESSING THE FORWARD BUTTON ON YOUR MOUSE!')
                
                rd.close()
                break

if __name__ == '__main__':
    verify()
