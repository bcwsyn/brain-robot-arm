"""Own bounded domain78 actual executor tests; no real drivers or CAN."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TESTS=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
binary=Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
env=dict(os.environ,ROS_DOMAIN_ID='78',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
 FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
 BRAIN_ROBOT_P4_OPEN_LOOP='1',BRAIN_ROBOT_P4_PLAN_ONLY='0',BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY='1')
reports=[];tag=os.environ.get('P4_TEST_RUN_TAG','')
for scenario in ['empty','object','stale']:
    dest=ROOT/(tag+'isolated_'+scenario);dest.mkdir(exist_ok=False)
    jobs=[];r={'scenario':scenario,'domain':78,'no_hardware':True,'start_epoch':time.time(),
              'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    try:
        for label,argv in [('fixture',['/usr/bin/python3',str(TESTS/'replay_p4_gripper_only.py'),
                '--scenario',scenario,'--output',str(dest/'result.json')]),
                ('nodes',['ros2','launch',str(TESTS/'review_p4_gripper_only.launch.py')])]:
            f=(dest/(label+'.log')).open('x');p=subprocess.Popen(argv,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            jobs.append((label,p,f))
        r['fixture_rc']=jobs[0][1].wait(timeout=80)
    except BaseException as exc:r['error']=repr(exc)
    finally:
        for _,p,_ in jobs:
            if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
        end=time.monotonic()+8
        while any(p.poll() is None for _,p,_ in jobs) and time.monotonic()<end:time.sleep(.05)
        r['cleanup']=[]
        for label,p,f in jobs:
            forced=p.poll() is None
            if forced:os.killpg(p.pid,signal.SIGKILL)
            p.wait(timeout=2);f.close();r['cleanup'].append({'name':label,'rc':p.returncode,'forced':forced})
        r['end_epoch']=time.time()
        with (dest/'execution.json').open('x') as f:json.dump(r,f,indent=2)
    reports.append(r);print(json.dumps(r),flush=True)
    if r.get('fixture_rc')!=0:break
with (ROOT/(tag+'isolated_execution.json')).open('x') as f:json.dump(reports,f,indent=2)
raise SystemExit(0 if len(reports)==3 and all(r.get('fixture_rc')==0 for r in reports) else 2)
