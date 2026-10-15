#!/usr/bin/env python3
"""Replay immutable B evidence with AST-extracted methods; no ROS/CAN import."""

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[6]
SOURCE = 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py'
BASELINE = 'be7c7c0'


def methods(source):
    tree = ast.parse(source)
    return {node.name: node for cls in tree.body if isinstance(cls, ast.ClassDef)
            and cls.name == 'PiperJogAdapter' for node in cls.body
            if isinstance(node, ast.FunctionDef)}


def load_method(nodes, name):
    namespace = {'math': math}
    exec(compile(ast.Module(body=[nodes[name]], type_ignores=[]), SOURCE, 'exec'), namespace)
    return namespace[name]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    raw = subprocess.check_output(['git', 'show', f'{BASELINE}:{SOURCE}'], cwd=REPO)
    candidate = (REPO / SOURCE).read_bytes()
    old, new = methods(raw.decode()), methods(candidate.decode())
    unchanged = ['_trajectory_rejection_reason', '_state_fresh', '_joint_jog',
                 '_gripper_command', '_append_pending_gripper', '_disarm_internal']
    for name in unchanged:
        assert ast.dump(old[name]) == ast.dump(new[name]), name
    audit = json.loads((Path(__file__).parent.parent / 'grip_capture/takeover_audit.json').read_text())
    names = [f'joint{i}' for i in range(1, 7)]
    positions = dict(zip(names, audit['actual_q']))
    adapter = SimpleNamespace(
        joint_names=names, joint_min=audit['joint_min'], joint_max=audit['joint_max'],
        positions=positions, targets=dict(positions), visual_baseline=dict(positions),
        visual_joint_max_delta=audit['visual_delta'], max_velocity=.189,
        trajectory_start_tolerance=.10, trajectory_max_joint_step=.35)
    old_hold = [load_method(old, '_limit_visual_target')(adapter, i, name, positions[name])
                for i, name in enumerate(names)]
    new_hold = [load_method(new, '_limit_visual_target')(adapter, i, name, positions[name])
                for i, name in enumerate(names)]
    assert new_hold == audit['actual_q']
    assert old_hold == audit['original_stationary_armed_no_trajectory_tick_targets']

    def trajectory(q):
        return SimpleNamespace(joint_names=names, points=[SimpleNamespace(
            positions=q, time_from_start=SimpleNamespace(sec=0, nanosec=0))])

    reject = load_method(new, '_trajectory_rejection_reason')
    outside_reason = reject(adapter, trajectory(audit['actual_q']))
    boundary_q = list(audit['actual_q'])
    boundary_q[2] = -1.4
    boundary_reason = reject(adapter, trajectory(boundary_q))
    assert outside_reason == 'point 0 exceeds limit for joint3'
    assert boundary_reason == 'point 0 start mismatch for joint3'
    # The original validator accepts this smaller 0.05rad start mismatch.
    adapter.positions = dict(positions, joint3=-1.45)
    adapter.targets = dict(adapter.positions)
    adapter.trajectory = trajectory(boundary_q)
    adapter.trajectory_start = 0.0
    assert reject(adapter, adapter.trajectory) is None
    load_method(old, '_apply_trajectory')(adapter, 1.0, .02)
    old_step = adapter.targets['joint3'] - adapter.positions['joint3']
    load_method(new, '_apply_trajectory')(adapter, 1.0, .02)
    new_step = adapter.targets['joint3'] - adapter.positions['joint3']
    assert abs(new_step) <= .189 * .02 + 1e-12
    return {
        'offline_only': True, 'baseline_commit': BASELINE,
        'baseline_adapter_sha256': sha(raw), 'candidate_adapter_sha256': sha(candidate),
        'ROS_initialized': False, 'CAN_accessed': False, 'deployed': False,
        'hardware_commands_sent': False, 'actual_grip_q_rad': audit['actual_q'],
        'original_idle_target_rad': old_hold, 'fixed_idle_target_rad': new_hold,
        'original_J3_idle_jump_rad': old_hold[2] - positions['joint3'],
        'fixed_J3_idle_jump_rad': new_hold[2] - positions['joint3'],
        'unchanged_method_AST_checks': unchanged,
        'actual_grip_start_rejected': outside_reason,
        'nearest_in_bounds_start_rejected': boundary_reason,
        'previously_accepted_near_boundary_case': {
            'measured_J3_rad': -1.45, 'requested_J3_rad': -1.4, 'dt_s': .02,
            'max_velocity_rad_s': .189, 'original_step_rad': old_step,
            'fixed_step_rad': new_step, 'allowed_step_rad': .189 * .02},
        'interpretation': 'No implicit boundary jump. No new recovery trajectory admission. '
                          'Fifth grip cannot yet return through original validator.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(verify(), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text, end='')
