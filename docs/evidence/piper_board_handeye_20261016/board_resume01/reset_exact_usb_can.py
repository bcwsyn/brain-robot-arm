"""One scoped USB-CAN reset, never arm/device CAN commands."""
import json
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parent
device = Path('/sys/bus/usb/devices/3-1.2')
assert (device/'idVendor').read_text().strip() == '1d50'
assert (device/'idProduct').read_text().strip() == '606f'
assert (device/'serial').read_text().strip() == '003F001E5246570520323934'
report = {'target': '/dev/bus/usb/003/007', 'serial': '003F001E5246570520323934',
          'no_arm_motion_enable_disable_or_gripper': True, 'commands': [], 'received_frames': 0}


def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    report['commands'].append({'argv': argv, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    return p


try:
    result = run(['sudo','-n','timeout','-k','2s','5s','/usr/bin/usbreset','003/007'])
    if result.returncode == 0:
        for argv in [
            ['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],
            ['sudo','-n','ip','link','set','can0','txqueuelen','1000'],
            ['sudo','-n','ip','link','set','can0','up'],
        ]:
            if run(argv).returncode:
                break
        state = run(['ip','-json','-details','-statistics','link','show','can0'])
        if state.returncode == 0 and 'UP' in json.loads(state.stdout)[0]['flags']:
            with socket.socket(socket.PF_CAN,socket.SOCK_RAW,socket.CAN_RAW) as receiver:
                receiver.settimeout(.2);receiver.bind(('can0',))
                until = time.monotonic()+3
                while time.monotonic()<until:
                    try:
                        receiver.recv(16);report['received_frames'] += 1
                    except socket.timeout:
                        pass
except Exception as exc:
    report['error'] = repr(exc)
finally:
    run(['ip','-json','-details','-statistics','link','show','can0'])
    (ROOT/'usb_reset_recovery.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['received_frames'] else 2)
