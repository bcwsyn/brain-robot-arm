"""Reuse the original bounded read-only capture after a new cube placement."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

repo = Path('/mnt/hgfs/ub')
tests = repo/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
root = Path(tempfile.mkdtemp(prefix='new_pair07_attempt03_A.', dir='/home/johnwick/brain_robot_logs'))
print(root, flush=True)
paths = list(json.loads((repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt02/observe_capture/production_SHA_before.json').read_text()))
def hashes():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
before = hashes()
expected = json.loads((repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt02/observe_capture/production_SHA_before.json').read_text())
assert before == expected, 'Production changed; stop before device access'
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
