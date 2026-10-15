"""Passive SDK metadata followed by original offline review/export/quality."""
import json
from pathlib import Path
import subprocess
import time

root = Path('/home/johnwick/brain_robot_logs/new_pair07_attempt03_A.9r_fp1bb')
tests = Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
execution = json.loads((root/'session/execution.json').read_text())
assert execution['raw_acquisition_complete'] and execution['all_owned_sources_exited']
config = '/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'
commands = [
    ['collect_calibration_sdk.py', '--output', str(root/'sdk_post_capture.json'), '--duration-s', '6'],
    ['review_calibration_capture.py', '--capture', str(root/'session/capture'), '--config', config,
     '--output', str(root/'depth_review.json')],
    ['export_calibration_bundle.py', '--output', str(root/'portable_all60'), '--capture',
     str(root/'session/capture'), '--sample-id', 'new_pair07_attempt03_observe', '--sdk',
     str(root/'sdk_post_capture.json'), '--camera-metadata', str(root/'session/factory.json'),
     '--review', str(root/'depth_review.json'), '--detector-config', config, '--cube-edge-mm', '29'],
    ['calibration_p0_quality.py', '--bundle', str(root/'portable_all60'), '--output', str(root/'quality')],
]
events = []
for command in commands:
    argv = ['/usr/bin/python3', str(tests/command[0]), *command[1:]]
    start = time.time()
    with (root/(command[0]+'.log')).open('xb') as stream:
        result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    events.append({'argv': argv, 'returncode': result.returncode, 'start_epoch': start,
                   'end_epoch': time.time()})
    print(json.dumps(events[-1]), flush=True)
    (root/'review_execution.json').write_text(json.dumps(events, indent=2))
    if result.returncode and not (command[0]=='collect_calibration_sdk.py' and result.returncode==2):
        raise SystemExit(result.returncode)
print(json.dumps(json.loads((root/'quality/report.json').read_text())['summary']), flush=True)
