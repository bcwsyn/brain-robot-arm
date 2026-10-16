"""One authorized interface-only recovery after newly confirmed RX stall."""
import json
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parent


def state():
    return json.loads(subprocess.check_output(['ip','-json','-details','-statistics','link','show','can0']))[0]


report = {'new_fault': 'RX fixed at 4796101 after observation stopped receiving; original software disarmed.',
          'motion_or_enable_or_disable_commands': False, 'USB_or_module_reload': False, 'commands': []}
report['before'] = state()
subprocess.run(['sudo','-n','true'], check=True)
for command in [
    ['sudo','-n','ip','link','set','can0','down'],
    ['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],
    ['sudo','-n','ip','link','set','can0','txqueuelen','1000'],
    ['sudo','-n','ip','link','set','can0','up'],
]:
    result = subprocess.run(command, capture_output=True, text=True)
    report['commands'].append({'argv': command, 'returncode': result.returncode, 'stderr': result.stderr})
    if result.returncode:
        break
with socket.socket(socket.PF_CAN,socket.SOCK_RAW,socket.CAN_RAW) as receiver:
    receiver.settimeout(.2)
    receiver.bind(('can0',))
    start = time.monotonic()
    received = 0
    while time.monotonic()-start < 3:
        try:
            receiver.recv(16)
            received += 1
        except socket.timeout:
            pass
report['after'] = state()
report['passive_frames_in_3s'] = received
report['feedback_restored'] = received > 0
(ROOT/'interface_recovery.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passive_frames_in_3s':received,'feedback_restored':received>0,
                  'can_state':report['after']['linkinfo']['info_data']['state']},indent=2))
raise SystemExit(0 if received else 2)
