#!/usr/bin/env python3
"""Unit tests for physical trajectory rejection before any command output."""

import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from sensor_msgs.msg import JointState
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


def test_explicit_gripper_frame_carries_vendor_effort_in_bounded_burst():
    adapter = make_adapter()
    adapter.gripper_effort_nm = 1.0
    adapter.pending_gripper_target = 0.05
    adapter.pending_gripper_frames = 5

    for remaining in range(4, -1, -1):
        command = JointState()
        command.name = list(adapter.joint_names)
        command.position = [0.0] * 6
        assert adapter._append_pending_gripper(command) is True
        assert command.name == adapter.joint_names + ['gripper']
        assert list(command.position) == [0.0] * 6 + [0.05]
        assert list(command.effort) == [0.0] * 6 + [1.0]
        assert adapter.pending_gripper_frames == remaining

    assert adapter.pending_gripper_target is None

    arm_only = JointState()
    arm_only.name = list(adapter.joint_names)
    arm_only.position = [0.0] * 6
    assert adapter._append_pending_gripper(arm_only) is False
    assert list(arm_only.effort) == []


def test_full_open_100mm_is_forwarded_without_changing_arm_targets():
    adapter = make_adapter()
    adapter.armed = True
    adapter._state_fresh = lambda: True
    adapter.gripper_command_repeats = 5
    adapter.gripper_effort_nm = 1.0
    adapter.get_logger = lambda: SimpleNamespace(info=lambda _: None, error=lambda _: None)
    request = JointState()
    request.name = ['gripper']
    request.position = [.100]
    adapter._gripper_command(request)
    output = JointState()
    output.name = list(adapter.joint_names)
    output.position = [.01] * 6
    assert adapter._append_pending_gripper(output)
    assert output.position == pytest.approx([.01] * 6 + [.100])
    assert output.effort[-1] == 1.0


@pytest.mark.parametrize('opening', [0.0, .050, .0796, .080, .0996, .100])
def test_actual_total_opening_maps_to_opposed_fingers(opening):
    assert MODULE.measured_finger_positions(opening) == {
        'joint7': opening / 2, 'joint8': -opening / 2}


@pytest.mark.parametrize('opening', [None, -.001, .103001, .104, math.nan, math.inf])
def test_bad_opening_is_not_zeroed_or_clamped(opening):
    assert MODULE.measured_finger_positions(opening) is None


@pytest.mark.parametrize('opening', [.100001, .1015, .103])
def test_authorized_small_mechanical_overrun_only_caps_model(opening):
    assert MODULE.measured_finger_positions(opening) == {'joint7': .05, 'joint8': -.05}


@pytest.mark.parametrize('opening', [.0796, .1015])
def test_filtered_model_uses_same_message_measured_opening_without_arm_command(opening):
    adapter = make_adapter()
    adapter.armed = False
    adapter.targets = {}
    adapter.last_gripper_model_warning = 0.0
    emitted = []
    adapter.filtered_joint_state_publisher = SimpleNamespace(publish=emitted.append)
    adapter.command_publisher = SimpleNamespace(
        publish=lambda _: pytest.fail('Feedback mapping must not command hardware'))
    message = JointState()
    message.header.stamp.sec = 123
    message.name = adapter.joint_names + ['gripper']
    message.position = [.01] * 6 + [opening]
    adapter._joint_state(message)
    assert len(emitted) == 1
    assert emitted[0].header.stamp.sec == 123
    half = min(opening, .100) / 2
    assert emitted[0].position == pytest.approx([.01] * 6 + [half, -half])
    assert message.position == pytest.approx([.01] * 6 + [opening])


def takeover_adapter(monkeypatch, positions=None):
    """Exercise real callbacks with message sinks, never a ROS node or CAN."""
    adapter = make_adapter()
    adapter.positions.update(positions or {})
    adapter.motion_enabled = True
    adapter.targets = dict(adapter.positions)
    adapter.visual_baseline = dict(adapter.positions)
    adapter.visual_joint_max_delta = [.12, .02, .02, .05, .10, .05]
    adapter.velocities = {name: 0.0 for name in adapter.joint_names}
    adapter.armed = False
    adapter.trajectory = None
    adapter.trajectory_start = 0.0
    adapter.max_velocity = .189
    adapter.last_tick = 99.98
    adapter.last_command_time = 0.0
    adapter.command_timeout_s = .20
    adapter.pending_gripper_target = None
    adapter.pending_gripper_frames = 0
    adapter._state_fresh = lambda: True
    adapter.get_logger = lambda: SimpleNamespace(
        warn=lambda _: None, info=lambda _: None, error=lambda _: None)
    adapter.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(to_msg=lambda: JointState().header.stamp))
    adapter.status_publisher = SimpleNamespace(publish=lambda _: None)
    emitted = []
    adapter.command_publisher = SimpleNamespace(publish=emitted.append)
    monkeypatch.setattr(MODULE.time, 'monotonic', lambda: 100.0)
    return adapter, emitted


def test_recorded_fifth_grip_arm_and_idle_ticks_do_not_clip(monkeypatch):
    audit_path = (Path(__file__).resolve().parents[5] / 'docs/evidence/'
                  'piper_calibration_p1_20261015/new_pair06/attempt01/'
                  'grip_capture/takeover_audit.json')
    audit = json.loads(audit_path.read_text())
    q = dict(zip([f'joint{i}' for i in range(1, 7)], audit['actual_q']))
    adapter, emitted = takeover_adapter(monkeypatch, q)
    adapter.joint_min = audit['joint_min']
    adapter.joint_max = audit['joint_max']
    adapter.visual_joint_max_delta = audit['visual_delta']
    response = adapter._arm(None, SimpleNamespace())
    assert response.success
    for tick in range(100):
        monkeypatch.setattr(MODULE.time, 'monotonic', lambda: 100.0 + tick * .02)
        adapter._tick()
    assert len(emitted) == 100
    for message in emitted:
        assert list(message.position) == audit['actual_q']
        assert list(message.name) == adapter.joint_names
        assert list(message.effort) == []
    assert adapter.joint_min == audit['joint_min']
    assert adapter.joint_max == audit['joint_max']
    # Neither an out-of-bound start nor a >0.10rad start mismatch is waived.
    outside = make_trajectory([(0.0, audit['actual_q'])])
    assert 'exceeds limit for joint3' in adapter._trajectory_rejection_reason(outside)
    inside = list(audit['actual_q'])
    inside[2] = -1.4
    assert adapter._trajectory_rejection_reason(
        make_trajectory([(0.0, inside)])) == 'point 0 start mismatch for joint3'


@pytest.mark.parametrize('joint_index', range(6))
@pytest.mark.parametrize('side', [-1, 1])
@pytest.mark.parametrize('velocity', [0.0, -.189, .189])
def test_outside_feedback_is_held_without_implicit_visual_reentry(
        monkeypatch, joint_index, side, velocity):
    adapter, emitted = takeover_adapter(monkeypatch)
    name = adapter.joint_names[joint_index]
    limit = adapter.joint_min[joint_index] if side < 0 else adapter.joint_max[joint_index]
    adapter.positions[name] = limit + side * .15
    adapter._arm(None, SimpleNamespace())
    adapter.velocities[name] = velocity
    adapter.last_command_time = 100.0
    adapter._tick()
    assert emitted[-1].position[joint_index] == adapter.positions[name]


def test_idle_hold_is_not_a_move_to_visual_envelope(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch, {'joint1': .5})
    adapter._arm(None, SimpleNamespace())
    adapter.visual_baseline['joint1'] = 0.0
    adapter._tick()
    assert emitted[-1].position[0] == .5


def test_old_outside_target_is_not_replayed_after_feedback_reenters(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch, {'joint3': -1.551364696})
    adapter._arm(None, SimpleNamespace())
    adapter.last_command_time = 100.0
    adapter.positions['joint3'] = -1.399
    adapter._tick()
    assert emitted[-1].position[2] == -1.399


def test_in_bounds_jog_still_uses_original_visual_envelope(monkeypatch):
    adapter, _ = takeover_adapter(monkeypatch)
    assert adapter._limit_visual_target(0, 'joint1', .2) == .12
    assert adapter._limit_visual_target(0, 'joint1', -.2) == -.12


@pytest.mark.parametrize('desired, expected', [(.503, .5), (.497, .497)])
def test_visual_envelope_cannot_reverse_or_enlarge_a_step(monkeypatch, desired, expected):
    adapter, _ = takeover_adapter(monkeypatch, {'joint1': .5})
    adapter.visual_baseline['joint1'] = 0.0
    assert adapter._limit_visual_target(0, 'joint1', desired) == expected


def test_expired_feedback_still_disarms_without_command(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch)
    adapter._arm(None, SimpleNamespace())
    adapter._state_fresh = lambda: False
    adapter._tick()
    assert not adapter.armed
    assert not emitted


def test_arm_still_requires_enabled_gate_and_fresh_six_axis_feedback(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch)
    adapter.motion_enabled = False
    assert not adapter._arm(None, SimpleNamespace()).success
    adapter.motion_enabled = True
    adapter._state_fresh = lambda: False
    assert not adapter._arm(None, SimpleNamespace()).success
    adapter._state_fresh = lambda: True
    del adapter.positions['joint6']
    assert not adapter._arm(None, SimpleNamespace()).success
    assert not adapter.armed
    assert not emitted


def test_authorized_gripper_burst_does_not_clip_outside_arm_hold(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch, {'joint3': -1.551364696})
    adapter._arm(None, SimpleNamespace())
    adapter.gripper_command_repeats = 5
    adapter.gripper_effort_nm = 1.0
    request = JointState()
    request.name = ['gripper']
    request.position = [.100]
    adapter._gripper_command(request)
    for _ in range(6):
        adapter._tick()
    for message in emitted:
        assert message.position[2] == -1.551364696
    assert all(message.position[-1] == .100 for message in emitted[:5])
    assert list(emitted[-1].name) == adapter.joint_names


@pytest.mark.parametrize('side', [-1, 1])
def test_accepted_near_boundary_trajectory_cannot_jump_after_rate_limit(monkeypatch, side):
    adapter, _ = takeover_adapter(monkeypatch)
    bound = adapter.joint_min[2] if side < 0 else adapter.joint_max[2]
    adapter.positions['joint3'] = bound + side * .05
    desired = [0.0] * 6
    desired[2] = bound
    adapter.trajectory = make_trajectory([(0.0, desired)])
    assert adapter._trajectory_rejection_reason(adapter.trajectory) is None
    active = adapter._apply_trajectory(100.0, .02)
    assert active
    assert abs(adapter.targets['joint3'] - adapter.positions['joint3']) <= .189 * .02 + 1e-12
    assert adapter.targets['joint3'] == pytest.approx(bound + side * (.05 - .189 * .02))


@pytest.mark.parametrize('side', [-1, 1])
@pytest.mark.parametrize('single_point', [True, False])
def test_final_bounded_step_is_not_overwritten_by_idle_hold(monkeypatch, side, single_point):
    adapter, emitted = takeover_adapter(monkeypatch)
    bound = adapter.joint_min[2] if side < 0 else adapter.joint_max[2]
    adapter.positions['joint3'] = bound + side * .001
    adapter._arm(None, SimpleNamespace())
    desired = [0.0] * 6
    desired[2] = bound
    samples = [(0.0, desired)] if single_point else [(0.0, desired), (.5, desired)]
    adapter._trajectory(make_trajectory(samples))
    monkeypatch.setattr(MODULE.time, 'monotonic', lambda: 101.0)
    adapter._tick()
    assert emitted[-1].position[2] == bound
    assert adapter.trajectory is None
    # Model a delivered final command and feedback, without simulating CAN.
    adapter.positions['joint3'] = bound
    adapter._tick()
    assert emitted[-1].position[2] == bound


def test_rearming_discards_old_trajectory_without_running_it(monkeypatch):
    adapter, emitted = takeover_adapter(monkeypatch)
    adapter.trajectory = make_trajectory([(0.0, [.05] * 6)])
    adapter._arm(None, SimpleNamespace())
    assert adapter.trajectory is None
    adapter._tick()
    assert list(emitted[-1].position) == [0.0] * 6
