"""Compile old/new ORIGINAL policy against identical synthetic response laws.
No hardware access; neither synthetic plant is identified from hardware.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
REL = 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/include/brain_robot_pick_place/gentle_gripper.hpp'
variants = {'old_5ca2072': subprocess.check_output(['git', '-C', str(REPO), 'show', '5ca2072:'+REL]),
            'new_bounded2mm': (REPO/REL).read_bytes()}
result = {'no_hardware': True, 'models_are_hypotheses_not_device_identification': True,
          'start_epoch': time.time(), 'variants': {}}
for name, header in variants.items():
    folder = ROOT/name
    folder.mkdir(exist_ok=False)
    (folder/'gentle_gripper.hpp').write_bytes(header)
    binary = folder/'compare_policy.bin'
    subprocess.run(['g++', '-std=c++17', '-O2', '-I', str(folder), str(ROOT/'compare_policy.cpp'),
                    '-o', str(binary)], check=True, timeout=30)
    rows = json.loads(subprocess.check_output([str(binary)], text=True, timeout=3))
    result['variants'][name] = {'header_sha256': hashlib.sha256(header).hexdigest(), 'cases': rows}
assert not result['variants']['old_5ca2072']['cases'][0]['empty']
assert result['variants']['new_bounded2mm']['cases'][0]['empty']
assert all(not row['contact'] for item in result['variants'].values() for row in item['cases'])
assert not result['variants']['new_bounded2mm']['cases'][1]['empty']
result['end_epoch'] = time.time()
(ROOT/'policy_comparison.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
