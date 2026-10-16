"""One existing-policy recovery for this new, proven gs_usb echo event only.

Not a repeat RX-only recovery. No USB reset, module reload, robot commands.
The exclusive attempt marker prevents repeating this invocation after failure.
"""
from pathlib import Path
import json
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'post_reconnect_failure'
REPORT = OUT/'new_echo_single_interface_recovery.json'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
host = json.loads((OUT/'host_status.json').read_text())
kernel = next(x['stdout'] for x in host['commands'] if x['argv']==['sudo','-n','dmesg','-T'])
assert '[Fri Oct 16 12:59:08 2026] gs_usb 3-1.2:1.0 can0: Unexpected out of range echo id 343' in kernel
assert json.loads((ROOT/'observe_after_host_reconnect/execution_session.json').read_text())['all_owned_sources_exited']
def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=8)
    return {'argv':argv,'epoch':time.time(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
report={'policy':'PIper_DECISIONS 2026-09-28 new unhandled gs_usb echo exception; one interface rebuild with all sources stopped',
    'boot_id':boot,'new_event':'2026-10-16 12:59:08 echo343',
    'robot_or_motion_commands':False,'USB_reset_or_module_reload':False,'commands':[],
    'old_counter_marker_text':Path('/home/johnwick/brain_robot_logs/gs_usb_echo_errors.handled').read_text(),
    'old_counter_marker_mtime':Path('/home/johnwick/brain_robot_logs/gs_usb_echo_errors.handled').stat().st_mtime,
    'marker_not_updated_without_boot_aware_production_change':True}
with REPORT.open('x') as f:json.dump(report,f,indent=2)
try:
    report['before']=run(['ip','-json','-details','-statistics','link','show','can0'])
    for argv in (
        ['sudo','-n','ip','link','set','can0','down'],
        ['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],
        ['sudo','-n','ip','link','set','can0','txqueuelen','1000'],
        ['sudo','-n','ip','link','set','can0','up']):
        result=run(argv);report['commands'].append(result)
        if result['returncode']:raise RuntimeError('Original fixed CAN activation failed: '+str(result))
    s=socket.socket(socket.AF_CAN,socket.SOCK_RAW,socket.CAN_RAW)
    s.bind(('can0',));s.settimeout(.2)
    end=time.monotonic()+4;frames=0
    while time.monotonic()<end:
        try:s.recv(72);frames+=1
        except socket.timeout:pass
    s.close();report['passive_frames_4s']=frames
except BaseException as e:
    report['error']=repr(e)
finally:
    report['after']=run(['ip','-json','-details','-statistics','link','show','can0'])
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report.get('passive_frames_4s',0)>0 else 2)
