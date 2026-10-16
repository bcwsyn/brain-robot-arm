"""Deploy only the approved original P4 gripper policy and its focused test.
No ROS, CAN or physical control calls. Preserve exact baseline backups.
"""
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
PREFIX = 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/'
FILES = ['include/brain_robot_pick_place/gentle_gripper.hpp', 'test/test_center_gentle.cpp']
report = {'baseline': '5ca2072', 'no_hardware_access': True, 'start_epoch': time.time(), 'files': []}
backup = ROOT/'before'
backup.mkdir(exist_ok=False)
for rel in FILES:
    source = REPO/PREFIX/rel
    active = Path('/home/johnwick/piper_ws/src/brain_robot_pick_place')/rel
    old = subprocess.check_output(['git', '-C', str(REPO), 'show', '5ca2072:'+PREFIX+rel])
    assert active.read_bytes() == old, str(active)+' changed independently'
    out = backup/rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(active, out)
    shutil.copy2(source, active)
    assert active.read_bytes() == source.read_bytes()
    report['files'].append({'canonical': str(source), 'active': str(active),
                            'before_sha256': hashlib.sha256(old).hexdigest(),
                            'after_sha256': hashlib.sha256(active.read_bytes()).hexdigest()})
binary = Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
shutil.copy2(binary, backup/'grasp_lift_executor.bin')
report['binary_before_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
assert report['binary_before_sha256'] == 'c3cf4eaac062300a590e14a20a70e396d4baee9b5c5bc3ac36fafd30e87867d1'
started = time.monotonic()
with (ROOT/'build.txt').open('x') as f:
    r = subprocess.run(['cmake', '--build', '/home/johnwick/piper_ws/build/brain_robot_pick_place',
                        '--target', 'grasp_lift_executor', 'center_gentle_test', '-j1'],
                       stdout=f, stderr=subprocess.STDOUT, timeout=300)
report['build_rc'] = r.returncode
report['build_elapsed_s'] = time.monotonic()-started
report['binary_after_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
if r.returncode == 0:
    with (ROOT/'deployed_cpp_test.txt').open('x') as f:
        r = subprocess.run(['/home/johnwick/piper_ws/build/brain_robot_pick_place/center_gentle_test',
                            '--gtest_output=xml:'+str(ROOT/'deployed_cpp_test.xml')],
                           stdout=f, stderr=subprocess.STDOUT, timeout=15)
    report['deployed_cpp_test_rc'] = r.returncode
report['end_epoch'] = time.time()
(ROOT/'deployment.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
raise SystemExit(r.returncode)
