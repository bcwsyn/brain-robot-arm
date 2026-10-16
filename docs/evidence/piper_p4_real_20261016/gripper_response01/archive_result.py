"""Archive existing evidence after all control sources exited. No devices."""
import collections
import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
DEST = REPO/'docs/evidence/piper_p4_real_20261016/gripper_response01'
helper = Path('/home/johnwick/brain_robot_logs/p4_gripper_only_20261016.CTeKXp/analyze_and_archive.py')
spec = importlib.util.spec_from_file_location('existing_finite_analysis', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
report = module.summarize(ROOT)
rows = [json.loads(line) for line in (ROOT/'real_record/events.jsonl').open()]
states = [r for r in rows if r['topic_key'] == 'grasp_state']
close = next(r['receipt_epoch'] for r in states if r['message']['data'] == 'P4_GRIPPER_TEST_CLOSING')
fault = next(r['receipt_epoch'] for r in states if r['message']['data'] == 'FAULT_P4_GRIPPER_TEST_CLOSE_UNCONFIRMED')
report['closing_to_primary_fault_s'] = fault-close
report['closing_duration_s_in_inherited_summary_includes_later_estop'] = report.pop('closing_duration_s')
actual = [r for r in rows if r['topic_key'] == 'actual_gripper_frame' and r['receipt_epoch'] >= close]
reference = [r for r in rows if r['topic_key'] == 'gripper_command' and r['receipt_epoch'] < fault]
report['last_fresh_gripper'] = actual[-1]
report['last_reference_before_FAULT'] = reference[-1]
report['no_new_grasp_or_lift'] = True
report['not_timeout'] = True
report['last_known_pose_not_current_enable_proof_after_stall'] = True
report['post_stall_readonly'] = json.loads((ROOT/'post_actual_readonly.json').read_text())
report['guard'] = (ROOT/'onekey_logs/can_health.log').read_text()
report['freshness_diagnostic'] = [r for r in rows if r['topic_key'] == 'grasp_diagnostic' and
                                 'STALE' in r['message']['data']]
log = (ROOT/'onekey_logs/piper_driver.log').read_text()
report['last_driver_calls'] = re.findall(
    r'\[([0-9]+\.[0-9]+)\] \[piper_ctrl_single_node\]: Calling GripperCtrl: angle=(\d+) effort=(\d+)', log)[-3:]
report['actual_opening_26mm_or_less'] = {
    'n': sum(r['message']['position'][0] <= .026 for r in actual),
    'insufficient_to_prove_final_empty_or_contact': True}
(ROOT/'actual_analysis.json').write_text(json.dumps(report, indent=2)+'\n')
protected = json.loads((REPO/'docs/evidence/piper_p4_real_20261016/gripper_only_test01/final_deployment.json').read_text())
checks = []
for item in protected['source_pairs']:
    c = REPO/item['canonical']
    live = Path(item['active'])
    assert c.read_bytes() == live.read_bytes()
    assert hashlib.sha256(c.read_bytes()).hexdigest() == item['canonical_sha256']
    checks.append({'path': str(c), 'sha256': item['canonical_sha256'], 'unchanged': True})
for item in protected['protected_sources']:
    c = REPO/item['path']
    live = Path(item['active'])
    assert c.read_bytes() == live.read_bytes()
    assert hashlib.sha256(c.read_bytes()).hexdigest() == item['unchanged_sha256']
    checks.append({'path': str(c), 'sha256': item['unchanged_sha256'], 'unchanged': True})
driver = Path('/home/johnwick/piper_ros/build/piper/piper/piper_ctrl_single_node.py')
assert hashlib.sha256(driver.read_bytes()).hexdigest() == protected['driver_sha256']
(ROOT/'protected_sha.json').write_text(json.dumps({'checks': checks, 'driver_sha256': protected['driver_sha256']}, indent=2)+'\n')
DEST.mkdir(exist_ok=False)
manifest = []
for src in sorted(ROOT.rglob('*')):
    if not src.is_file() or 'before' in src.relative_to(ROOT).parts or '__pycache__' in src.parts:
        continue
    raw = src.read_bytes()
    if src.suffix in ('.bin', '.pyc') or raw[:4] == b'\x7fELF':
        continue
    rel = src.relative_to(ROOT)
    compress = src.suffix == '.jsonl' or src.name == 'gripper_can.log'
    archived = Path(str(rel)+'.gz') if compress else (rel.with_suffix('.txt') if src.suffix == '.log' else rel)
    out = DEST/archived
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(raw, mtime=0) if compress else raw
    out.write_bytes(payload)
    recovered = gzip.decompress(out.read_bytes()) if compress else out.read_bytes()
    assert recovered == raw
    manifest.append({'path': str(archived), 'runtime_original': str(src),
        'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
        'archive_sha256': hashlib.sha256(payload).hexdigest(), 'archive_bytes': len(payload),
        'gzip_lossless': compress})
(DEST/'manifest.json').write_text(json.dumps({'files': manifest,
    'count': len(manifest), 'bytes': sum(r['archive_bytes'] for r in manifest),
    'excluded': 'before/ backups and all ELF/binaries retained at runtime only; no data deleted'}, indent=2)+'\n')
print(json.dumps({'artifact_count': len(manifest), 'archive_bytes': sum(r['archive_bytes'] for r in manifest),
    'actual_last_mm': report['actual_gripper_last_mm'],
    'arm_trajectory_count': report['arm_trajectory_count'],
    'joint_spread_rad': report['joint_spread_rad_from_test_opening'],
    'last_reference_before_FAULT': report['last_reference_before_FAULT']['message']['position'],
    'last_driver_calls': report['last_driver_calls'],
    'needs_host_USB_CAN_reconnect': True}, indent=2))
