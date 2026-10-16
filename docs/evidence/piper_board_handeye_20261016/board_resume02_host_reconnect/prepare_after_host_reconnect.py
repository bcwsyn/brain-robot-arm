"""Reuse original observation workflow after the user's host-side USB reconnect.

Only invocation paths/hash baseline and terminal-fault recognition differ.
Fresh SDK static validation, driver admission, goals and thresholds stay original.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'observe_after_host_reconnect'
OUT.mkdir(exist_ok=False)
source = (ROOT/'observe/executed_return.py').read_text()
for name in ('ROOT', 'LAUNCH'):
    old = str(ROOT/'observe' if name == 'ROOT' else ROOT/'observe/original_observe_launch.py')
    new = str(OUT if name == 'ROOT' else OUT/'original_observe_launch.py')
    source = source.replace(repr(old), repr(new))
old = "wait(lambda:'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH' in reason or 'FAILED' in reason,305,'original observation completion')"
new = "wait(lambda:'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH' in reason or 'FAILED' in reason or reason=='PIPER_ADAPTER_DISARMED' or reason.startswith('FAULT'),305,'original observation completion')"
assert source.count(old) == 1
source = source.replace(old, new)
old = "trigger('/visual_search_controller/start')"
new = "print('ORIGINAL_OBSERVE_CHECKLIST',json.dumps({'actual_start_rad':latest['q'],'goal_rad':yaml.safe_load(TASK.read_text())['visual_search_controller']['ros__parameters']['observe_joint_positions'],'enabled':enabled['enabled'],'limits_min':lo,'limits_max':hi,'prepare_velocity_acceleration_scaling':[.01,.01],'adapter_max_rad_s':.189,'timeout_s':300,'stop_after_observe':True,'no_search_gripper_reset_disable':True}),flush=True)\n trigger('/visual_search_controller/start')"
assert source.count(old) == 1
source = source.replace(old, new)
ast.parse(source)
(OUT/'executed_return.py').write_text(source)
shutil.copyfile(ROOT/'observe/original_observe_launch.py', OUT/'original_observe_launch.py')
(OUT/'invocation_changes.json').write_text(json.dumps({
    'user_confirmed': '已完成USB-CAN宿主侧重连',
    'new_interface': 5,
    'original_production_sources_changed': False,
    'fresh_SDK_static_required': True,
    'prior_baseline_reuse_not_used_at_changed_pose': True,
    'motion': 'Original current-to-fixed-observe, stop before SEARCH',
    'wrapper_only_fault_recognition': new,
    'source_sha256': hashlib.sha256(source.encode()).hexdigest()
}, indent=2, ensure_ascii=False)+'\n')
print(OUT/'executed_return.py')
