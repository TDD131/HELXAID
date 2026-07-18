import subprocess
import time
print('Stopping service...')
subprocess.run(['sc.exe', 'stop', 'HELXAIDHelper'])
time.sleep(1)
print('Starting service...')
subprocess.run(['sc.exe', 'start', 'HELXAIDHelper'])
print('Done!')
