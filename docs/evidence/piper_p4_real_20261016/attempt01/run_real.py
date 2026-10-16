"""Run ONLY the approved original entry, plus a bounded receive-only recorder."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
 FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
 BRAIN_ROBOT_AUTO_START='1',BRAIN_ROBOT_P4_OPEN_LOOP='1',BRAIN_ROBOT_P4_PLAN_ONLY='0',
 BRAIN_ROBOT_P4_TARGET_CONFIG=str(ROOT/'frozen_target.yaml'),
 BRAIN_ROBOT_DEPTH_ONLY_TARGET='0',BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED='0',
 BRAIN_ROBOT_LOG_DIR=str(ROOT/'onekey_logs'),BRAIN_ROBOT_GRASP_WAIT_SECONDS='500',
 DISPLAY=os.environ.get('DISPLAY',':0'))
jobs=[];report={'baseline_commit':subprocess.check_output(['git','-C','/mnt/hgfs/ub','rev-parse','--short','HEAD'],text=True).strip(),'P4_PLAN_ONLY':False,'original_entry':'/home/johnwick/start_brain_robot_cube_real.sh',
 'frozen_target_SHA256':hashlib.sha256((ROOT/'frozen_target.yaml').read_bytes()).hexdigest(),'start_epoch':time.time()}
try:
    for label,argv in [('recorder',['/usr/bin/python3',str(ROOT/'record_p4.py')]),
      ('original_entry',['/home/johnwick/start_brain_robot_cube_real.sh'])]:
        child_env=dict(env)
        if label=='original_entry':
            # Driver dependencies live in user site, while cv_bridge requires
            # system NumPy. Explicit system-first resolution, not pip/install
            # or changes to any production source or global shell settings.
            child_env['PYTHONPATH']='/usr/lib/python3/dist-packages:'+env.get('PYTHONPATH','')+':/home/johnwick/.local/lib/python3.10/site-packages'
        f=(ROOT/(label+'.log')).open('x');p=subprocess.Popen(argv,env=child_env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        jobs.append((label,p,f));report[label+'_pid']=p.pid
        if label=='recorder':time.sleep(1)
    report['entry_rc']=jobs[-1][1].wait(timeout=620)
except BaseException as exc:report['exception']=repr(exc)
finally:
    # Original entry owns its normal stop/disarm/hold-enabled cleanup.
    for label,p,f in reversed(jobs):
        if label=='original_entry' and p.poll() is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=35)
            except subprocess.TimeoutExpired:report['original_entry_cleanup_timeout']=True
    report['end_epoch']=time.time()
    with (ROOT/'real_finished.json').open('x') as f:json.dump(report,f,indent=2)
    for label,p,f in jobs:
        if label=='recorder' and p.poll() is None:
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGINT)
                p.wait(timeout=3)
        f.close()
print(json.dumps(report))
raise SystemExit(0 if report.get('entry_rc')==0 else 2)
