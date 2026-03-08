import hid

VID, PID = 0x3554, 0xF5D5

print('All Furycube interfaces:')
for d in hid.enumerate(VID, PID):
    iface = d.get('interface_number')
    usage_page = d.get('usage_page')
    usage = d.get('usage')
    print(f'  Interface {iface}: usage_page={usage_page} usage={usage}')
