"""Bounded receive-only CAN/host evidence; no recovery or CAN transmission."""
from pathlib import Path
import json
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'post_reconnect_failure'
OUT.mkdir(exist_ok=False)
def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=8)
    return {'argv':argv,'epoch':time.time(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
report = {'read_only':True,'CAN_transmissions':0,'USB_or_CAN_recovery_attempts':0,'commands':[]}
report['commands'].append(run(['ip','-json','-details','-statistics','link','show','can0']))
s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind(('can0',));s.settimeout(.2)
end = time.monotonic()+3
frames = 0
while time.monotonic()<end:
    try:s.recv(72);frames += 1
    except socket.timeout:pass
s.close()
report['passive_window_s']=3
report['new_frames']=frames
report['commands'].append(run(['ip','-json','-details','-statistics','link','show','can0']))
for argv in (['sudo','-n','dmesg','-T'], ['lsusb','-t'],['lsusb','-d','1d50:606f'], ['uname','-a'], ['modinfo','gs_usb'], ['ps','-eo','pid,stat,args'],['df','-h','/','/mnt/hgfs/ub']):
    report['commands'].append(run(argv))
report['USB_power'] = {str(p):p.read_text().strip() for p in [Path('/sys/bus/usb/devices/3-1.2/power')/n for n in ('control','runtime_status','autosuspend_delay_ms')] if p.exists()}
report['all_control_sources_expected_exited']=True
with (OUT/'host_status.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps({'new_frames':frames,'first_link':json.loads(report['commands'][0]['stdout']),'last_link':json.loads(report['commands'][1]['stdout']),'USB_power':report['USB_power']},indent=2))
