"""Bounded adopted mount verification with the unchanged original receive-only preview."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
jobs=[];report={'motion_commands_sent':False,'CAN_recovery':False,'events':[],'epoch':time.time()}
def can():
    p=subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)[0]
def start(name,argv):
    f=(ROOT/(name+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((name,p,f));return p
try:
    report['can_before']=can()
    start('static_model',['ros2','launch',str(ROOT/'static_mount.launch.py')])
    verify=start('verify',['/usr/bin/python3',str(ROOT/'verify_live_mount.py')])
    preview=start('original_preview',['/usr/bin/python3',str(ROOT/'executed_preview.py')])
    report['preview_rc']=preview.wait(timeout=52)
    report['verify_rc']=verify.wait(timeout=4)
except BaseException as e:report['error']=repr(e)
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    end=time.monotonic()+2
    while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    for name,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close();report['events'].append({'name':name,'rc':p.returncode})
    report['can_after']=can();report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['end_epoch']=time.time()
    with (ROOT/'deployment_execution.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps(report))
raise SystemExit(0 if report.get('preview_rc')==0 and report.get('verify_rc')==0 and not report.get('error') else 2)
