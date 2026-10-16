"""Preserve authorized deployment and blocked-motion evidence; no device API."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
DEST = REPO / 'docs/evidence/piper_board_handeye_20261016/deploy_j4_validation01'
sys.path.insert(0, str(REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from collect_calibration_sdk import summarize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def main():
    deployment = json.loads((ROOT / 'authorization.json').read_text())
    deployed = Path(deployment['deployed_path'])
    assert sha(deployed) == deployment['deployed_candidate_SHA256']
    assert sha(ROOT / 'piper_jog_adapter.before.py') == deployment['backup_SHA256']
    result = json.loads((ROOT / 'runtime_verification.json').read_text())
    assert result['all_owned_sources_exited'] and result['two_original_MoveIt_plans_passed']
    windows = []
    for name in ('sdk_preflight.json', 'sdk_preflight_10s.json'):
        data = json.loads((ROOT / name).read_text())
        run, best = [], []
        for sample in data['samples']:
            if sample['fresh_after_passive_connection'] and max(abs(v) for v in sample['speed_millirad_s']) <= 1:
                run.append(sample)
            else:
                run = []
            if len(run) > len(best):
                best = list(run)
        summary = summarize(best)
        assert not summary['static_three_seconds_and_thirty_samples']
        windows.append({'source': name, 'original_full_window_quality': data['quality'],
                        'longest_contiguous_original_static_subwindow': summary,
                        'speed_outside_original_1_millirad_s_count': sum(
                            max(abs(v) for v in s['speed_millirad_s']) > 1 for s in data['samples']),
                        'last_fresh_sample': [s for s in data['samples'] if s['fresh_after_passive_connection']][-1]})
    db = next((ROOT / 'runtime_bag').glob('*.db3'))
    connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
    counts = dict(connection.execute('SELECT topics.name, count(messages.id) FROM topics LEFT JOIN messages ON topics.id=messages.topic_id GROUP BY topics.id'))
    connection.close()
    assert counts.get('/joint_commands', 0) == 0
    assert counts.get('/brain_robot_grasp/arm_trajectory', 0) == 0
    assert counts.get('/brain_robot_grasp/gripper_command', 0) == 0
    frozen = json.loads((REPO / 'docs/evidence/piper_calibration_p1_20261015/board_open_only/production_SHA_before.json').read_text())
    hashes = {p: sha(Path(p)) for p in frozen}
    exceptions = [p for p, old in frozen.items() if hashes[p] != old]
    assert set(exceptions) == {str(deployed), str(REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')}
    assert all(hashes[p] == deployment['deployed_candidate_SHA256'] for p in exceptions)
    audit = {'operator_scope': deployment['approved_scope'], 'deployment_completed': True,
             'candidate_runtime_started_disarmed': True, 'two_original_plans_passed': True,
             'SDK_windows': windows, 'actual_J4_out_and_back_executed': False,
             'reason': 'Original passive SDK 3-second/30-sample speed+angle static window failed; no threshold change.',
             'bag_message_counts': counts, 'trajectory_and_gripper_absent_topics_counted_as_zero': True,
             'driver_initialization_CAN_TX_delta': 13, 'CAN_TX_not_zero_despite_no_motion_commands': True,
             'all_owned_sources_exited': True, 'exit_details': [e for e in result['events'] if 'source' in e],
             'frozen_source_SHA_after': hashes, 'approved_candidate_paths_changed_from_old_baseline': exceptions,
             'board_pose_count_unchanged': 2, 'hand_eye_solved': False, 'production_TF_changed': False,
             'physical_speed_pulse_cause_not_diagnosed': True,
             'ROS_angle_only_static_pass_NOT_substituted_for_SDK_speed_check': True,
             'next': 'Read-only check speed-feedback pulses versus measured angle; keep existing limited J4 authorization, do not ask for same approval/restart or auto-continue other poses.',
             'GitHub_pushed': False}
    put(ROOT / 'assessment.json', audit)
    names = ['authorization.json', 'sdk_preflight.json', 'sdk_preflight_10s.json',
             'runtime_verification.json', 'can_before_runtime.json', 'can_after_runtime.json',
             'piper_jog_adapter.before.py', 'verify_deployed_without_motion.py',
             'original_nodes.launch.py', 'assessment.json', 'package_validation.py']
    for name in names:
        src = ROOT / name
        if src.suffix == '.py':
            ast.parse(src.read_text())
        shutil.copyfile(src, DEST / name)
    members = [ROOT / n for n in names] + [ROOT / n for n in ('driver.log', 'original_nodes.log', 'bag.log')]
    members += sorted(p for p in (ROOT / 'runtime_bag').iterdir() if p.is_file())
    entries = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in members]
    archive = DEST / 'runtime_originals.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for p in members:
            tar.add(p, arcname=p.relative_to(ROOT).as_posix(), recursive=False)
    with tarfile.open(archive) as tar:
        for item in entries:
            assert hashlib.sha256(tar.extractfile(item['path']).read()).hexdigest() == item['sha256']
    put(DEST / 'runtime_manifest.json', {'archive_SHA256': sha(archive), 'readback_SHA_verified': True, 'files': entries})
    print(json.dumps({'deploy_verified': True, 'no_motion_bag_counts': counts,
                      'original_members_SHA_verified': len(entries), 'archive_bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
