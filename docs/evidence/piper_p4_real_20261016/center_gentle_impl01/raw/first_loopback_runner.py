"""Own two bounded domain-78 synthetic full-executor tests, no hardware."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
env=dict(os.environ,ROS_DOMAIN_ID='78',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
    FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
    BRAIN_ROBOT_P4_OPEN_LOOP='1',BRAIN_ROBOT_P4_PLAN_ONLY='0',
    BRAIN_ROBOT_P4_TARGET_CONFIG=str(ROOT/'HISTORICAL_center_fixture.yaml'))
reports=[]
for scenario in ['empty','object']:
    dest=ROOT/('loopback_'+scenario);dest.mkdir(exist_ok=False)
    report={'scenario':scenario,'domain':78,'no_hardware':True,'start_epoch':time.time()};jobs=[]
    try:
        for label,argv in [('fixture',['/usr/bin/python3',str(ROOT/'loopback_fixture.py'),
            '--scenario',scenario,'--output',str(dest/'result.json')]),
            ('nodes',['ros2','launch',str(ROOT/'full_loop.launch.py')])]:
            stream=(dest/(label+'.log')).open('x')
            p=subprocess.Popen(argv,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            jobs.append((label,p,stream))
        report['fixture_rc']=jobs[0][1].wait(timeout=100)
    except BaseException as exc:report['error']=repr(exc)
    finally:
        for _,p,_ in jobs:
            if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
        deadline=time.monotonic()+8
        while any(p.poll() is None for _,p,_ in jobs) and time.monotonic()<deadline:time.sleep(.05)
        report['jobs']=[]
        for label,p,f in jobs:
            forced=p.poll() is None
            if forced:os.killpg(p.pid,signal.SIGKILL)
            p.wait(timeout=3);f.close()
            report['jobs'].append({'name':label,'rc':p.returncode,'forced':forced})
        report['end_epoch']=time.time()
        with (dest/'execution.json').open('x') as f:json.dump(report,f,indent=2)
    reports.append(report)
    print(json.dumps(report),flush=True)
    if report.get('fixture_rc')!=0:break
with (ROOT/'loopback_execution.json').open('x') as f:json.dump(reports,f,indent=2)
raise SystemExit(0 if len(reports)==2 and all(r.get('fixture_rc')==0 for r in reports) else 2)
