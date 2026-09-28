#!/usr/bin/env python3
"""Unit tests for physical trajectory rejection before any command output."""

import importlib.util
import math
from pathlib import Path

from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


SCRIPT = Path(__file__).parents[1] / 'scripts' / 'piper_jog_adapter.py'
SPEC = importlib.util.spec_from_file_location('piper_jog_adapter', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_adapter():
    adapter = object.__new__(MODULE.PiperJogAdapter)
    adapter.joint_names = [f'joint{index}' for index in range(1, 7)]
    adapter.joint_min = [-1.5, -0.3, -1.4, -0.8, -1.2, -0.8]
    adapter.joint_max = [1.5, 1.4, 0.4, 0.8, 1.2, 0.8]
    adapter.positions = {name: 0.0 for name in adapter.joint_names}
    adapter.trajectory_start_tolerance = 0.10
    adapter.trajectory_max_joint_step = 0.35
    return adapter


def make_trajectory(samples):
    trajectory = JointTrajectory()
    trajectory.joint_names = [f'joint{index}' for index in range(1, 7)]
    for seconds, positions in samples:
        point = JointTrajectoryPoint()
        point.positions = positions
        whole_seconds = int(seconds)
        point.time_from_start.sec = whole_seconds
        point.time_from_start.nanosec = int(round((seconds - whole_seconds) * 1e9))
        trajectory.points.append(point)
    return trajectory


def test_accepts_continuous_bounded_trajectory():
    adapter = make_adapter()
    trajectory = make_trajectory([
        (0.0, [0.0] * 6),
        (0.5, [0.05, 0.04, -0.03, 0.02, 0.01, 0.0]),
    ])
    assert adapter._trajectory_rejection_reason(trajectory) is None


def test_rejects_start_mismatch():
    adapter = make_adapter()
    trajectory = make_trajectory([(0.0, [0.11, 0.0, 0.0, 0.0, 0.0, 0.0])])
    assert adapter._trajectory_rejection_reason(trajectory) == 'point 0 start mismatch for joint1'


def test_rejects_non_monotonic_time():
    adapter = make_adapter()
    trajectory = make_trajectory([(0.0, [0.0] * 6), (0.0, [0.01] * 6)])
    assert 'not strictly increasing' in adapter._trajectory_rejection_reason(trajectory)


def test_rejects_joint_jump():
    adapter = make_adapter()
    trajectory = make_trajectory([(0.0, [0.0] * 6), (0.5, [0.36, 0.0, 0.0, 0.0, 0.0, 0.0])])
    assert adapter._trajectory_rejection_reason(trajectory) == 'point 1 joint jump for joint1'


def test_rejects_limit_violation():
    adapter = make_adapter()
    trajectory = make_trajectory([(0.0, [0.0] * 6), (0.5, [0.0, -0.31, 0.0, 0.0, 0.0, 0.0])])
    assert adapter._trajectory_rejection_reason(trajectory) == 'point 1 exceeds limit for joint2'


def test_rejects_nonfinite_or_wrong_dimension():
    adapter = make_adapter()
    nonfinite = make_trajectory([(0.0, [0.0] * 6), (0.5, [math.nan] + [0.0] * 5)])
    assert 'non-finite position' in adapter._trajectory_rejection_reason(nonfinite)
    malformed = make_trajectory([(0.0, [0.0] * 5)])
    assert adapter._trajectory_rejection_reason(malformed) == 'point 0 position count mismatch'
