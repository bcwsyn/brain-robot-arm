"""Own an isolated, command-monitored actual-executor preview, no hardware."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

root = Path(__file__).resolve().parent
pkg = Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place')
env = dict(os.environ, ROS_DOMAIN_ID='78', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
           FASTRTPS_DEFAULT_PROFILES_FILE='/home/johnwick/fastdds_udp_only.xml',
           BRAIN_ROBOT_P4_OPEN_LOOP='1', BRAIN_ROBOT_P4_PLAN_ONLY='1',
           BRAIN_ROBOT_P4_TARGET_CONFIG=str(root / 'frozen_target.yaml'))
report = {'start_epoch': time.time(), 'domain': 78, 'no_hardware_nodes': True, 'jobs': []}
jobs = []
try:
    for label, argv in [
        ('fixture', ['/usr/bin/python3', str(pkg / 'test/replay_p4_plan_only.py'),
                     '--capture', '/mnt/hgfs/ub/docs/evidence/piper_p4_preparation_20261016/cube_static01/paired_retry/capture/observer.jsonl',
                     '--output', str(root / 'preview_result.json')]),
        ('nodes', ['ros2', 'launch', str(pkg / 'test/review_p4_open_loop.launch.py')]),
    ]:
        stream = (root / (label + '.log')).open('x')
        process = subprocess.Popen(argv, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        jobs.append((label, process, stream, argv))
    report['fixture_rc'] = jobs[0][1].wait(timeout=100)
except BaseException as error:
    report['exception'] = repr(error)
finally:
    for _, process, _, _ in jobs:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
    deadline = time.monotonic() + 8
    while any(p.poll() is None for _, p, _, _ in jobs) and time.monotonic() < deadline:
        time.sleep(.05)
    for label, process, stream, argv in jobs:
        forced = process.poll() is None
        if forced:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        stream.close()
        report['jobs'].append({'name': label, 'argv': argv, 'rc': process.returncode,
                               'forced_kill': forced})
    report['end_epoch'] = time.time()
    report['all_owned_parents_exited'] = all(p.poll() is not None for _, p, _, _ in jobs)
    with (root / 'execution.json').open('x') as stream:
        json.dump(report, stream, indent=2)
print(json.dumps(report))
raise SystemExit(0 if report.get('fixture_rc') == 0 and 'exception' not in report else 2)
