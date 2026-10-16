"""One bounded original-detector/static capture, no physical control nodes."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/internal_tf_pair01/production_SHA_after.json')
jobs=[];report={'epoch':time.time(),'motion_commands_sent':False,'CAN_recovery':False,'events':[]}
def can():
    p=subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)[0]
def start(name,argv):
    f=(ROOT/(name+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((name,p,f));report['events'].append({'name':name,'argv':argv,'pid':p.pid,'epoch':time.time()});return p
try:
    baseline=json.loads(BASE.read_text());actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
    if actual!=baseline:raise RuntimeError('Production hashes changed before read-only capture')
    report['can_before']=can()
    start('model_tf',['ros2','launch',str(ROOT/'static_mount.launch.py')])
    observer=start('target_observer',['/usr/bin/python3',str(ROOT/'observe_target.py')])
    start('original_detector',['ros2','launch','brain_robot_ball_pick','cube_detector.launch.py'])
    preview=start('original_preview',['/usr/bin/python3',str(ROOT/'executed_preview.py')])
    report['preview_rc']=preview.wait(timeout=52);report['observer_rc']=observer.wait(timeout=4)
except BaseException as exc:report['exception']=repr(exc)
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    end=time.monotonic()+2
    while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    for name,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close();report['events'].append({'name':name,'rc':p.returncode})
    report['can_after']=can();report['end_epoch']=time.time()
    report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
    report['production_unchanged']=actual==baseline
    with (ROOT/'production_SHA_after.json').open('x') as f:json.dump(actual,f,indent=2)
    with (ROOT/'target_execution.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'preview_rc':report.get('preview_rc'),'observer_rc':report.get('observer_rc'),
    'exception':report.get('exception'),'all_exited':report['all_owned_sources_exited'],'production_unchanged':report['production_unchanged']}))
raise SystemExit(0 if report.get('preview_rc')==report.get('observer_rc')==0 and not report.get('exception') else 2)
