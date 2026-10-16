"""Offline evidence audit for the executed, bounded original J4 roundtrip."""
from pathlib import Path
import ast
import hashlib
import json
import math
import shutil
import sqlite3
import sys
import tarfile

import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
OUT = REPO / 'docs/evidence/piper_board_handeye_20261016/j4_roundtrip01'
sys.path.insert(0, str(REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from collect_calibration_sdk import summarize
NAMES = [f'joint{i}' for i in range(1, 7)]


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    execution = load(ROOT / 'execution.json')
    assert execution['error'] is None and execution['roundtrip_original_tolerance_and_settled_passed']
    assert execution['all_owned_sources_exited'] and execution['software_disarm_succeeded']
    assert load(ROOT / 'production_SHA_before.json') == load(ROOT / 'production_SHA_after.json')
    assert all(sha(Path(p)) == value for p, value in load(ROOT / 'production_SHA_after.json').items())
    before = load(ROOT / 'sdk_before.json')
    after = load(ROOT / 'sdk_after.json')
    assert before['quality']['static_three_seconds_and_thirty_samples']
    windows = []
    for i in range(len(after['samples'])):
        for j in range(i+30, len(after['samples'])+1):
            quality = summarize(after['samples'][i:j])
            if quality['static_three_seconds_and_thirty_samples']:
                windows.append({'start_index_inclusive': i, 'end_index_exclusive': j, 'quality': quality})
    assert windows
    final = [s for s in after['samples'] if s['fresh_after_passive_connection']][-1]
    assert all(final['enabled']) and final['gripper_mm'] == 99.6
    connection = sqlite3.connect('file:'+str(next((ROOT / 'motion_bag').glob('*.db3')))+'?mode=ro', uri=True)
    topics = dict(connection.execute('SELECT id,name FROM topics'))
    counts = {name: 0 for name in topics.values()}
    trajectory_rows, commands, feedback = [], [], []
    for topic, stamp, data in connection.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
        name = topics[topic]
        counts[name] += 1
        if name == '/brain_robot_grasp/arm_trajectory':
            message = deserialize_message(data, JointTrajectory)
            trajectory_rows.append({'epoch': stamp/1e9, 'points': len(message.points),
                                    'joint_names': list(message.joint_names),
                                    'start_q': list(message.points[0].positions),
                                    'goal_q': list(message.points[-1].positions)})
        elif name in ('/joint_commands', '/joint_states_feedback'):
            message = deserialize_message(data, JointState)
            values = dict(zip(message.name, message.position))
            if all(n in values for n in NAMES):
                if name == '/joint_commands':
                    assert 'gripper' not in values and len(message.name) == 6
                (commands if name == '/joint_commands' else feedback).append({'epoch': stamp/1e9, 'q': [values[n] for n in NAMES]})
    connection.close()
    assert len(trajectory_rows) == 2 and len(commands) == 748
    assert counts.get('/brain_robot_grasp/gripper_command', 0) == 0
    phases = []
    for index, trajectory in enumerate(trajectory_rows):
        upper = trajectory_rows[index+1]['epoch'] if index+1 < len(trajectory_rows) else float('inf')
        rows = [c for c in commands if trajectory['epoch'] <= c['epoch'] < upper]
        q = np.asarray([r['q'] for r in rows])
        actual = execution['arrivals'][index]['actual_feedback']['q']
        goal = trajectory['goal_q']
        error = np.asarray(actual)-goal
        assert np.abs(error).max() <= .04
        assert np.abs(q[:, 3]-goal[3]).min() < 1e-12
        phases.append({'phase': 'out' if index == 0 else 'return', 'trajectory': trajectory,
                       'command_count': len(rows), 'command_q_min': q.min(axis=0).tolist(),
                       'command_q_max': q.max(axis=0).tolist(), 'actual_arrival_q': actual,
                       'actual_minus_planned_goal_rad': error.tolist(),
                       'J4_actual_goal_error_deg': math.degrees(error[3]),
                       'complete_J4_goal_was_commanded': True})
    all_feedback = np.asarray([r['q'] for r in feedback])
    start = np.asarray(execution['actual_start']['q'])
    report = {'specific_J4_roundtrip_hardware_verified': True,
              'operator_power_cycle_and_safe_zero_confirmed': execution['operator_confirmation'],
              'no_historical_start_replayed': True, 'production_source_thresholds_changed': False,
              'bag_message_counts': counts, 'gripper_input_messages': 0, 'command_frames_with_gripper': 0,
              'phases': phases,
              'actual_out_J4_delta_deg': math.degrees(execution['arrivals'][0]['actual_feedback']['q'][3]-start[3]),
              'actual_return_J4_error_deg': math.degrees(final['q_driver_rad'][3]-start[3]),
              'all_axes_actual_max_deviation_from_start_rad': np.abs(all_feedback-start).max(axis=0).tolist(),
              'all_axes_final_minus_start_rad': (np.asarray(final['q_driver_rad'])-start).tolist(),
              'other_axes_not_claimed_exactly_stationary': True,
              'SDK_before_full_window': before['quality'], 'SDK_after_full_window': after['quality'],
              'SDK_after_longest_original_static_subwindow': max(windows, key=lambda row: row['quality']['span_s']),
              'final_SDK_fresh_sample': final,
              'software_disarmed_not_hardware_disabled': True, 'all_owned_sources_exited': True,
              'process_exit_details': [e for e in execution['events'] if 'source' in e],
              'MoveIt_child_shutdown_minus11_logged': 'exit code -11' in (ROOT / 'original_nodes.log').read_text(errors='replace'),
              'shutdown_child_fault_not_concealed_by_launch_exit0': True,
              'driver_shutdown_required_SIGKILL_after_original2s_grace': True,
              'only_J4_validation_executed_no_auto_other_poses': True,
              'board_pose_samples_unchanged': 2, 'hand_eye_solved_or_TF_updated': False,
              'next': 'Prepare existing observation/board9fit1heldout resumption from new actual pose; do not automatically expand this limited J4 run into a larger observation trajectory.',
              'GitHub_pushed': False}
    put(ROOT / 'assessment.json', report)
    names = ['run_j4_roundtrip.py', 'original_nodes.launch.py', 'sdk_before.json', 'sdk_after.json',
             'production_SHA_before.json', 'production_SHA_after.json', 'can_before.json', 'can_after.json',
             'planning_before_motion.json', 'execution.json', 'assessment.json', 'package_roundtrip.py']
    for name in names:
        if name.endswith('.py'):
            ast.parse((ROOT/name).read_text())
        shutil.copyfile(ROOT/name, OUT/name)
    names += ['driver.log', 'original_nodes.log', 'bag.log']
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'motion_bag').iterdir()) if p.is_file()]
    entries = [{'path': name, 'bytes': (ROOT/name).stat().st_size, 'sha256': sha(ROOT/name)} for name in names]
    archive = OUT/'runtime_originals.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in names:
            tar.add(ROOT/name, arcname=name, recursive=False)
    with tarfile.open(archive) as tar:
        for entry in entries:
            assert hashlib.sha256(tar.extractfile(entry['path']).read()).hexdigest() == entry['sha256']
    put(OUT/'runtime_manifest.json', {'archive_SHA256': sha(archive), 'files': entries, 'all_SHA_readback_verified': True})
    print(json.dumps({'hardware_J4_roundtrip_passed': True, 'messages': counts, 'phases': phases,
                      'final_enabled': final['enabled'], 'archive_members_verified': len(entries),
                      'archive_bytes': archive.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
