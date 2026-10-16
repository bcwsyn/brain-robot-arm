"""Approved ONE gripper-only actual run via ORIGINAL one-key entry.
No alternate actuator publishers. A receive-only recorder watches for any
unexpected arm trajectory; abnormal output stops the original entry/adapter.
"""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub');TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
env=dict(os.environ,ROS_DOMAIN_ID='0',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
 FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
 BRAIN_ROBOT_AUTO_START='1',BRAIN_ROBOT_P4_OPEN_LOOP='1',BRAIN_ROBOT_P4_PLAN_ONLY='0',
 BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY='1',BRAIN_ROBOT_P4_TARGET_CONFIG='',
 BRAIN_ROBOT_DEPTH_ONLY_TARGET='0',BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED='0',
 BRAIN_ROBOT_LOG_DIR=str(ROOT/'onekey_logs'),DISPLAY=os.environ.get('DISPLAY',':0'))
jobs=[];report={'baseline':'4037724','original_entry':'/home/johnwick/start_brain_robot_cube_real.sh',
 'actual_authorization':'User confirmed original-executor gripper-only endpoint and independent real open/slow-close test.',
 'P4_GRIPPER_TEST_ONLY':True,'arm_grasp_target_provided':False,'start_epoch':time.time()}
def can():return json.loads(subprocess.check_output(['ip','-json','-details','-statistics','link','show','can0'],text=True))[0]
try:
    for scenario in ['empty','object','stale']:
        r=json.loads((ROOT/f'final_isolated_{scenario}/result.json').read_text())
        assert r['passed'] and r['arm_trajectories']==0 and r['joint_commands']==0
    report['can_before']=can()
    with (ROOT/'immediate_sdk.log').open('x') as f:
        s=subprocess.run(['/usr/bin/python3',str(TESTS/'collect_calibration_sdk.py'),
          '--duration-s','4','--output',str(ROOT/'immediate_sdk.json')],env=env,stdout=f,stderr=subprocess.STDOUT,timeout=10)
    packet=json.loads((ROOT/'immediate_sdk.json').read_text());fresh=[r for r in packet['samples'] if r['fresh_after_passive_connection']]
    assert fresh and all(fresh[-1]['enabled']),'Fresh enabled six-axis state absent'
    sample=fresh[-1];report['immediate_SDK_rc']=s.returncode
    task=yaml.safe_load((REPO/'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
    q=sample['q_driver_rad']
    assert all(a<=v<=b for a,v,b in zip(task['real_trajectory_joint_min'],q,task['real_trajectory_joint_max']))
    assert 0<=sample['gripper_mm']<=3,'Expected initially empty closed jaw state changed'
    brief={'actual_feedback':sample,'SDK_full_quality':packet['quality'],
      'actual_entry':report['original_entry'],'arm_target_rad_UNCHANGED':q,
      'joint_min_rad':task['real_trajectory_joint_min'],'joint_max_rad':task['real_trajectory_joint_max'],
      'expected_moving_arm_joints':[],'arm_velocity_acceleration_target':0,
      'retained_adapter_velocity_cap_rad_s':.189,'retained_model_acceleration_rad_s2':1.0,
      'gripper_open_target_m':.100,'gripper_empty_floor_m':.025,
      'gripper_reference_rates_mm_s':[10,3],'reference_lead_max_mm':.5,'full_open_settle_s':2,
      'gripper_nominal_effort_Nm':.5,'not_calibrated_fingertip_force':True,
      'expected_test_duration_s':'~20-25 after startup; original worker bounded, outer entry240',
      'stop_conditions':'original stale/fault/estop/timeout; no arm trajectory expected',
      'stop_and_rollback':'stop original entry/adapter output, preserve enable; no reset, disable, or blind return',
      'current_image_evidence':str(ROOT/'preflight/capture/observer.jsonl')}
    with (ROOT/'motion_brief.json').open('x') as f:json.dump(brief,f,indent=2)
    print(json.dumps(brief,indent=2),flush=True)
    for label,argv in [('recorder',['/usr/bin/python3',str(ROOT/'record_gripper.py')]),
                       ('original_entry',[report['original_entry']])]:
        child=dict(env)
        if label=='original_entry':
            child['PYTHONPATH']='/usr/lib/python3/dist-packages:'+env.get('PYTHONPATH','')+':/home/johnwick/.local/lib/python3.10/site-packages'
        f=(ROOT/(label+'.log')).open('x');p=subprocess.Popen(argv,env=child,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        jobs.append((label,p,f))
        if label=='recorder':time.sleep(1)
    entry=jobs[-1][1];deadline=time.monotonic()+240
    while entry.poll() is None and time.monotonic()<deadline:
        events=ROOT/'real_record/events.jsonl'
        if events.exists():
            # Small finite test file; a partial last line is ignored.
            for line in events.read_text().splitlines():
                try:r=json.loads(line)
                except json.JSONDecodeError:continue
                if r.get('topic_key')=='arm_trajectory':
                    raise RuntimeError('Unexpected arm trajectory during gripper-only test')
        time.sleep(.2)
    if entry.poll() is None:raise TimeoutError('Original entry240s bound')
    report['entry_rc']=entry.returncode
except BaseException as exc:report['exception']=repr(exc)
finally:
    for label,p,f in reversed(jobs):
        if label=='original_entry' and p.poll() is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=40)
            except subprocess.TimeoutExpired:report['entry_cleanup_timeout']=True
    report['end_epoch']=time.time();report['can_after']=can()
    with (ROOT/'real_finished.json').open('x') as f:json.dump(report,f,indent=2)
    report['jobs']=[]
    for label,p,f in jobs:
        if label=='recorder' and p.poll() is None:
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGINT);p.wait(timeout=4)
        f.close();report['jobs'].append({'label':label,'pid':p.pid,'rc':p.poll()})
    with (ROOT/'actual_execution.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report,indent=2),flush=True)
raise SystemExit(0 if report.get('entry_rc')==0 and not report.get('exception') else 2)
