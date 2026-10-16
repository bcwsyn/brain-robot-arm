"""Own isolated domain-78 planning nodes and remove them after read-only calls."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PKG=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place')
env=dict(os.environ,ROS_DOMAIN_ID='78',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
report={'epoch':time.time(),'domain':78,'motion_commands_sent':False,'events':[]};jobs=[]
try:
    argv=['g++','-std=c++17','-O2','-I'+str(PKG/'include'),str(PKG/'test/review_target_directed_geometry.cpp'),'-o',str(ROOT/'shared_geometry')]
    p=subprocess.run(argv,capture_output=True,text=True,timeout=20)
    report['compile']={'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr,
        'shared_header_SHA256':hashlib.sha256((PKG/'include/brain_robot_pick_place/target_directed_grasp.hpp').read_bytes()).hexdigest()}
    if p.returncode:raise RuntimeError('Shared geometry compile failed')
    for label,argv in [('planning_nodes',['ros2','launch',str(PKG/'test/review_terminal_depth_plan.launch.py')]),
        ('planner',['/usr/bin/python3',str(ROOT/'plan_frozen_candidates.py')])]:
        f=(ROOT/(label+'.log')).open('xb');p=subprocess.Popen(argv,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        jobs.append((label,p,f))
    report['planner_rc']=jobs[-1][1].wait(timeout=100)
except BaseException as exc:report['exception']=repr(exc)
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    end=time.monotonic()+2
    while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.03)
    for label,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close();report['events'].append({'name':label,'rc':p.returncode})
    report['end_epoch']=time.time();report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    with (ROOT/'planning_execution.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
