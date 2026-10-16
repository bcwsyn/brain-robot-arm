"""Record user-confirmed port reconnect; activate only a DOWN can0, receive only."""
from pathlib import Path
import json
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parent
report={'operator_quote':'已完成','context':'After request to change host physical USB-CAN port and reconnect to VM',
    'host_physical_port_not_independently_visible_from_guest':True,
    'motion_or_enable_or_disable_commands':False,'USB_reset_or_module_reload':False,'commands':[]}
def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=8)
    row={'argv':argv,'epoch':time.time(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    report['commands'].append(row)
    if p.returncode:raise RuntimeError(str(row))
    return p.stdout
def save():
    (ROOT/'port_preflight.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
try:
    report['before']=json.loads(run(['ip','-json','-details','-statistics','link','show','can0']))[0]
    run(['lsusb','-d','1d50:606f']);run(['lsusb','-t']);run(['sudo','-n','true'])
    if 'UP' not in report['before']['flags']:
        for argv in (['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],['sudo','-n','ip','link','set','can0','txqueuelen','1000'],['sudo','-n','ip','link','set','can0','up']):run(argv)
    s=socket.socket(socket.AF_CAN,socket.SOCK_RAW,socket.CAN_RAW);s.bind(('can0',));s.settimeout(.2)
    began=time.monotonic();frames=0;per_second=[];previous=0
    while time.monotonic()-began<5:
        try:s.recv(72);frames+=1
        except socket.timeout:pass
        if time.monotonic()-began>=len(per_second)+1:
            per_second.append(frames-previous);previous=frames
    s.close();report['passive_frames_5s']=frames;report['per_second_frames']=per_second
    report['after']=json.loads(run(['ip','-json','-details','-statistics','link','show','can0']))[0]
    report['kernel_log']=run(['sudo','-n','dmesg','-T'])
    report['disk']=run(['df','-h','/','/mnt/hgfs/ub'])
except BaseException as e:report['error']=repr(e)
finally:save()
print(json.dumps({k:report.get(k) for k in ('passive_frames_5s','per_second_frames','error')},indent=2))
raise SystemExit(0 if report.get('passive_frames_5s',0)>0 and not report.get('error') else 2)
