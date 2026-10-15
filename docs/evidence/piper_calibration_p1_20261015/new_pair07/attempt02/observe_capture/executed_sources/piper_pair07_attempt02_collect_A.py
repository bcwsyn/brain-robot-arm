"""One approved read-only A capture after the operator's new flat-mat placement."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

repo = Path('/mnt/hgfs/ub')
tests = repo/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
root = Path(tempfile.mkdtemp(prefix='new_pair07_attempt02_A.', dir='/home/johnwick/brain_robot_logs'))
print(root, flush=True)
paths = [Path('/home/johnwick/start_brain_robot_cube_real.sh'),
         Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'),
         Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'),
         repo/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp',
         repo/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py',
         Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')]
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before = hashes()
(root/'production_SHA_before.json').write_text(json.dumps(before, indent=2))
start = time.time()
with (root/'coordinator.log').open('xb') as stream:
    result = subprocess.run(['/usr/bin/python3', str(tests/'capture_calibration_session.py'),
                             '--output', str(root/'session')], stdout=stream,
                            stderr=subprocess.STDOUT, timeout=105)
after = hashes()
(root/'production_SHA_after.json').write_text(json.dumps(after, indent=2))
print(json.dumps({'root': str(root), 'returncode': result.returncode,
                  'elapsed_s': time.time()-start, 'production_unchanged': before==after}), flush=True)
raise SystemExit(result.returncode)
