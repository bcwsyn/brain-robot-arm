"""One bounded gripper-only run via the ORIGINAL entry; recorder only observes.
No alternative motion publisher, no arm target, no reset/disable/lift.
"""
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
TESTS = REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
env = dict(os.environ, ROS_DOMAIN_ID='0', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
    FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
    BRAIN_ROBOT_AUTO_START='1', BRAIN_ROBOT_P4_OPEN_LOOP='1', BRAIN_ROBOT_P4_PLAN_ONLY='0',
    BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY='1', BRAIN_ROBOT_P4_TARGET_CONFIG='',
    BRAIN_ROBOT_DEPTH_ONLY_TARGET='0', BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED='0',
    BRAIN_ROBOT_LOG_DIR=str(ROOT/'onekey_logs'), DISPLAY=os.environ.get('DISPLAY', ':0'))
jobs = []
report = {'baseline': '5ca2072', 'original_entry': '/home/johnwick/start_brain_robot_cube_real.sh',
    'authorization': 'User requested autonomous progress, call only for necessary physical operations; announced only bounded gripper lead/time correction before code changes.',
    'arm_target_candidate_adopted': False, 'start_epoch': time.time()}


def can():
    return json.loads(subprocess.check_output(
        ['ip', '-json', '-details', '-statistics', 'link', 'show', 'can0'], text=True))[0]


try:
    deployment = json.loads((ROOT/'deployment.json').read_text())
    assert deployment['build_rc'] == deployment['deployed_cpp_test_rc'] == 0
    binary = Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
    report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert report['binary_sha256'] == deployment['binary_after_sha256']
    for scenario in ('empty', 'object', 'stale'):
        result = json.loads((ROOT/f'isolated_{scenario}/result.json').read_text())
        assert result['passed'] and result['arm_trajectories'] == result['joint_commands'] == 0
    report['can_before'] = can()
    assert report['can_before']['linkinfo']['info_data']['state'] == 'ERROR-ACTIVE'
    with (ROOT/'immediate_sdk.txt').open('x') as f:
        result = subprocess.run(['/usr/bin/python3', str(TESTS/'collect_calibration_sdk.py'),
            '--duration-s', '4', '--output', str(ROOT/'immediate_sdk.json')],
            env=env, stdout=f, stderr=subprocess.STDOUT, timeout=10)
    packet = json.loads((ROOT/'immediate_sdk.json').read_text())
    fresh = [r for r in packet['samples'] if r['fresh_after_passive_connection']]
    assert fresh and all(fresh[-1]['enabled'])
    sample = fresh[-1]
    report['immediate_SDK_rc'] = result.returncode
    task = yaml.safe_load((REPO/'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
    q = sample['q_driver_rad']
    assert all(a <= v <= b for a, v, b in zip(task['real_trajectory_joint_min'], q, task['real_trajectory_joint_max']))
    assert 0 <= sample['gripper_mm'] <= 103
    brief = {'actual_feedback': sample, 'SDK_full_quality': packet['quality'],
        'original_entry': report['original_entry'], 'arm_target_rad_UNCHANGED': q,
        'joint_min_rad': task['real_trajectory_joint_min'],
        'joint_max_rad': task['real_trajectory_joint_max'], 'moving_arm_joints': [],
        'arm_velocity_acceleration_target': 0, 'retained_adapter_velocity_cap_rad_s': .189,
        'retained_model_acceleration_rad_s2': 1., 'gripper_open_m': .100,
        'gripper_empty_floor_m': .025, 'reference_rate_mm_s': [10, 3],
        'reference_lead_limit_mm': 2, 'nominal_effort_Nm': .5,
        'not_calibrated_fingertip_force_or_speed': True,
        'test_duration_after_ready_s': 'approximately 2s open + at most35s close; original shell bound60s',
        'stop': 'Original fresh/fault/estop/finite deadline; measured-opening hold on timeout. No arm trajectory/lift/reset/DisableArm.'}
    (ROOT/'motion_brief.json').write_text(json.dumps(brief, indent=2)+'\n')
    print(json.dumps({'fresh_q_rad': q, 'six_enabled': sample['enabled'],
        'current_gripper_mm': sample['gripper_mm'], 'joint_min_rad': brief['joint_min_rad'],
        'joint_max_rad': brief['joint_max_rad'], 'arm_target_UNCHANGED': True,
        'gripper_motion': 'open100mm then bounded2mm-lead slow close, floor25mm; nominal0.5Nm',
        'stop': brief['stop'], 'full_motion_brief': str(ROOT/'motion_brief.json')}), flush=True)
    for label, argv in [('recorder', ['/usr/bin/python3', str(ROOT/'record_gripper.py')]),
                        ('original_entry', [report['original_entry']])]:
        child = dict(env)
        if label == 'original_entry':
            child['PYTHONPATH'] = '/usr/lib/python3/dist-packages:'+env.get('PYTHONPATH', '')+':/home/johnwick/.local/lib/python3.10/site-packages'
        f = (ROOT/(label+'.txt')).open('x')
        p = subprocess.Popen(argv, env=child, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        jobs.append((label, p, f))
        if label == 'recorder':
            time.sleep(1)
    entry = jobs[-1][1]
    deadline = time.monotonic()+240
    position = 0
    while entry.poll() is None and time.monotonic() < deadline:
        events = ROOT/'real_record/events.jsonl'
        if events.exists():
            with events.open() as f:
                f.seek(position)
                while True:
                    before = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        f.seek(before)
                        break
                    if row.get('topic_key') == 'arm_trajectory':
                        raise RuntimeError('Unexpected arm trajectory during gripper-only run')
                position = f.tell()
        time.sleep(.2)
    if entry.poll() is None:
        raise TimeoutError('Original entry240s bound')
    report['entry_rc'] = entry.returncode
except BaseException as exc:
    report['exception'] = repr(exc)
finally:
    for label, p, _ in reversed(jobs):
        if label == 'original_entry' and p.poll() is None:
            os.killpg(p.pid, signal.SIGINT)
            try:
                p.wait(timeout=40)
            except subprocess.TimeoutExpired:
                report['entry_cleanup_timeout'] = True
    report['end_epoch'] = time.time()
    report['can_after'] = can()
    (ROOT/'real_finished.json').write_text(json.dumps(report, indent=2)+'\n')
    report['jobs'] = []
    for label, p, f in jobs:
        if label == 'recorder' and p.poll() is None:
            try:
                p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGINT)
                p.wait(timeout=4)
        f.close()
        report['jobs'].append({'label': label, 'pid': p.pid, 'rc': p.poll()})
    (ROOT/'actual_execution.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('can_before', 'can_after')}, indent=2))
raise SystemExit(0 if report.get('entry_rc') == 0 and not report.get('exception') else 2)
