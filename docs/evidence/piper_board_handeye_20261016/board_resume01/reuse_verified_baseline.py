"""Prepare the same original observe invocation using a verified static baseline.

Do not recapture/relabel failed SDK data or change production/SDK thresholds.
Only reuse 81f8a7e's passing endpoint window when current fresh pose, six-axis
enable status, source hashes and healthy link match the verified baseline.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
sys.path.insert(0, str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from collect_calibration_sdk import summarize

prior = REPO/'docs/evidence/piper_board_handeye_20261016/j4_roundtrip01'
passed = json.loads((prior/'sdk_after.json').read_text())
summary = json.loads((prior/'assessment.json').read_text())['SDK_after_longest_original_static_subwindow']
part = passed['samples'][summary['start_index_inclusive']:summary['end_index_exclusive']]
assert summarize(part)['static_three_seconds_and_thirty_samples']
baseline = [r for r in passed['samples'] if r['fresh_after_passive_connection']][-1]
current = json.loads((ROOT/'observe/sdk_before.json').read_text())
fresh = [r for r in current['samples'] if r['fresh_after_passive_connection']]
assert len(fresh) >= 31 and all(all(r['enabled']) for r in fresh[-31:])
assert fresh[-1]['epoch']-fresh[-31]['epoch'] >= 3.
assert all(max(abs(a-b) for a,b in zip(row['q_driver_rad'], baseline['q_driver_rad'])) <= .001 for row in fresh)
frozen = json.loads((ROOT/'approved_baseline.json').read_text())
assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == value for path,value in frozen.items())
second = ROOT/'observe_reuse_baseline'
second.mkdir(exist_ok=False)
shutil.copyfile(ROOT/'observe/original_observe_launch.py', second/'original_observe_launch.py')
shutil.copyfile(ROOT/'observe/sdk_before.json', second/'sdk_before.json')
certificate = {'rule': 'CODEX_TASK_PROMPT section6: reuse passed P0/P1 baseline unless relevant state/config changes',
               'prior_static_source': str(prior/'sdk_after.json'), 'prior_source_SHA256': hashlib.sha256((prior/'sdk_after.json').read_bytes()).hexdigest(),
               'prior_passing_subwindow': summary, 'SDK_function_or_threshold_changed': False,
               'current_full_window_failure_preserved': current['quality'],
               'current_actual_fresh_samples': len(fresh),
               'six_enabled_last31_samples_span_s': fresh[-1]['epoch']-fresh[-31]['epoch'],
               'initial_partial_low_speed_aggregate_sample_not_used_as_six_axis_enable_proof': not all(fresh[0]['enabled']),
               'maximum_current_pose_delta_from_verified_endpoint_rad': max(abs(a-b) for row in fresh for a,b in zip(row['q_driver_rad'],baseline['q_driver_rad'])),
               'sources_unchanged': True, 'CAN_health_checked_before_original_driver_start': True,
               'scope': 'Observation invocation only; not qualify a new calibration sample or replace SDK raw evidence.'}
(second/'baseline_reuse.json').write_text(json.dumps(certificate, indent=2)+'\n')
source = (ROOT/'observe/executed_return.py').read_text()
source = source.replace(f'ROOT=Path({str(ROOT/"observe")!r})', f'ROOT=Path({str(second)!r})')
source = source.replace(f'LAUNCH=Path({str(ROOT/"observe/original_observe_launch.py")!r})', f'LAUNCH=Path({str(second/"original_observe_launch.py")!r})')
old = "packet,measured=sdk('sdk_before');report['initial_measured']=measured"
new = "packet=json.loads((ROOT/'sdk_before.json').read_text());measured=[s for s in packet['samples'] if s['fresh_after_passive_connection']][-1];report['initial_measured']=measured;report['baseline_reuse']=json.loads((ROOT/'baseline_reuse.json').read_text())"
assert source.count(old) == 1
source = source.replace(old, new)
old = "if not windows:raise RuntimeError('No original continuous >=3s/30-sample static window; no driver or movement started')"
new = "if not windows:report['original_static_baseline_reused_not_current_window_passed']=report['baseline_reuse']['prior_passing_subwindow']"
assert source.count(old) == 1
source = source.replace(old, new)
old = "trigger('/visual_search_controller/start')"
new = "print('ORIGINAL_OBSERVE_CHECKLIST',json.dumps({'high_stamp':measured['sdk_receipt_stamps']['high'],'high_Hz':measured['high_hz'],'enabled':enabled['enabled'],'actual_start_rad':latest['q'],'goal_rad':yaml.safe_load(TASK.read_text())['visual_search_controller']['ros__parameters']['observe_joint_positions'],'limits_min':lo,'limits_max':hi,'prepare_velocity_acceleration_scaling':[.01,.01],'adapter_max_rad_s':.189,'timeout_s':300,'stop':'original stop/disarm; keep enabled; no SEARCH/gripper/Reset'}),flush=True)\n trigger('/visual_search_controller/start')"
assert source.count(old) == 1
source = source.replace(old, new)
ast.parse(source)
(second/'executed_return.py').write_text(source)
print(json.dumps(certificate, indent=2))
