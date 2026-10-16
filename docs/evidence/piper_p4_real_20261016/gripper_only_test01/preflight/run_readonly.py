"""Current image/q/reference audit only, original finite collection helpers.
No physical driver, adapter, executor, Servo or motion APIs are started.
"""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
VERIFY=REPO/'docs/evidence/piper_p4_real_20261016/center_gentle_impl01/raw/final_verification.json'
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
 FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml')
jobs=[];report={'baseline':'4037724','epoch':time.time(),'current_readonly_reference_audit':True,
 'physical_motion_gripper_enable_disable_reset_commands':0,'CAN_recovery':False,'events':[]}
def can():
    return json.loads(subprocess.check_output(['ip','-json','-details','-statistics','link','show','can0'],text=True))[0]
def start(label,argv):
    f=(ROOT/(label+'.log')).open('xb')
    p=subprocess.Popen(argv,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((label,p,f));report['events'].append({'label':label,'argv':argv,'pid':p.pid})
    return p
try:
    expected=json.loads(VERIFY.read_text())
    files={r['active']:r['sha256'] for r in expected['synchronized_sources']}
    files.update(expected['protected_files_unchanged'])
    for rel,active in {
        'brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp':'/home/johnwick/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp',
        'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py':'/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py',
        'brain_robot_arm/scripts/start_brain_robot_cube_real.sh':'/home/johnwick/start_brain_robot_cube_real.sh'}.items():
        files[active]=hashlib.sha256((REPO/rel).read_bytes()).hexdigest()
    actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}
    assert actual==files,'Production changed since approved deployed build'
    report['source_SHA_before']=actual;report['can_before']=can()
    start('model_tf',['ros2','launch',str(ROOT/'static_mount.launch.py')])
    observer=start('target_observer',['/usr/bin/python3',str(ROOT/'observe_target.py')])
    start('original_detector',['ros2','launch','brain_robot_ball_pick','cube_detector.launch.py'])
    preview=start('original_preview',['/usr/bin/python3',str(ROOT/'executed_preview.py')])
    report['preview_rc']=preview.wait(timeout=52)
    report['observer_rc']=observer.wait(timeout=max(4,46-(time.time()-report['epoch'])))
except BaseException as exc:report['exception']=repr(exc)
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    end=time.monotonic()+5
    while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    report['cleanup']=[]
    for label,p,f in jobs:
        forced=p.poll() is None
        if forced:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close()
        report['cleanup'].append({'label':label,'rc':p.returncode,'forced':forced})
    report['can_after']=can();report['end_epoch']=time.time()
    report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['production_SHA_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in files.items())
    with (ROOT/'readonly_execution.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({k:report.get(k) for k in ['preview_rc','observer_rc','exception','cleanup','production_SHA_unchanged']}))
raise SystemExit(0 if report.get('preview_rc')==report.get('observer_rc')==0 and not report.get('exception') else 2)
