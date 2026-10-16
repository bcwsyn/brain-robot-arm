"""One bounded static RGB-D comparison after operator-restored USB3 setting.

Only existing approved CAN activation if DOWN; no robot transmit interfaces.
"""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FROZEN=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/camera_rgb_isolation01/production_SHA_after.json')
report={'operator_quote':'我已恢复','epoch':time.time(),'commands':[],
        'robot_control_started':False,'USB_reset':False,'CAN_activation':False}
jobs=[]
def save(name,obj):
    with (ROOT/name).open('x') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
def run(argv,timeout=5):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    r={'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    report['commands'].append(r)
    return p
def can():
    p=run(['ip','-json','-details','-statistics','link','show','can0'])
    if p.returncode:raise RuntimeError('No can0')
    return json.loads(p.stdout)[0]
try:
    baseline=json.loads(FROZEN.read_text())
    sha={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
    save('production_SHA_before.json',sha)
    if sha!=baseline:raise RuntimeError('Production baseline differs; no stream started')
    for a in [['lsusb','-t'],['lsusb'],['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm']]:run(a)
    state=can();save('can_initial.json',state)
    if 'UP' not in state['flags']:
        for a in [['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],
                  ['sudo','-n','ip','link','set','can0','txqueuelen','1000'],
                  ['sudo','-n','ip','link','set','can0','up']]:
            if run(a).returncode:raise RuntimeError('One approved CAN activation failed')
        report['CAN_activation']=True
    save('can_active.json',can())
    f=(ROOT/'candump.log').open('xb')
    p=subprocess.Popen(['candump','-L','can0'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append(('candump',p,f))
    f=(ROOT/'preview_stdout.txt').open('xb')
    p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'executed_preview.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append(('preview',p,f))
    report['preview_rc']=p.wait(timeout=52)
except BaseException as e:
    report['error']=repr(e)
finally:
    for _,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
        f.close()
    report['end_epoch']=time.time()
    try:save('can_final.json',can())
    except Exception as e:report['can_final_error']=repr(e)
    try:
        sha={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
        save('production_SHA_after.json',sha);report['production_unchanged']=sha==baseline
    except Exception as e:report['sha_error']=repr(e)
    save('static_report.json',report)
print(json.dumps({'root':str(ROOT),'preview_rc':report.get('preview_rc'),'error':report.get('error'),'production_unchanged':report.get('production_unchanged')}),flush=True)
