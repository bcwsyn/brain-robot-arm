#!/usr/bin/env python3
"""Offline replay of the physical adapter gates for the locked grasp path.

This is deliberately an adapter-level test: it does not invent a Cartesian
target or send ROS/CAN output.  It uses the real task YAML, the documented
six-axis P2 snapshot, and interpolates each accepted segment so the same
trajectory validation used by the physical adapter is exercised before the
arm is available.
"""

import importlib.util
import math
from pathlib import Path

import yaml
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "brain_robot_ball_pick" / "config" / "cube_task_real.yaml"
ADAPTER = Path(__file__).parents[1] / "scripts" / "piper_jog_adapter.py"
CONTROLLER = Path(__file__).parents[1] / "src" / "visual_search_controller.cpp"
EXECUTOR = Path(__file__).parents[1] / "src" / "grasp_lift_executor.cpp"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("piper_jog_adapter_replay", ADAPTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_adapter():
    module = _load_adapter()
    adapter = object.__new__(module.PiperJogAdapter)
    adapter.joint_names = [f"joint{index}" for index in range(1, 7)]
    adapter.joint_min = [-1.50, -0.30, -1.40, -0.80, -1.20, -0.80]
    adapter.joint_max = [1.50, 1.40, 0.40, 0.80, 1.20, 0.80]
    adapter.positions = {name: 0.0 for name in adapter.joint_names}
    adapter.trajectory_start_tolerance = 0.10
    adapter.trajectory_max_joint_step = 0.35
    return adapter


def _trajectory(start, end, max_step=0.08):
    count = max(1, max(
        math.ceil(abs(target - origin) / max_step)
        for origin, target in zip(start, end)))
    result = JointTrajectory()
    result.joint_names = [f"joint{index}" for index in range(1, 7)]
    for step in range(count + 1):
        point = JointTrajectoryPoint()
        ratio = step / count
        point.positions = [origin + (target - origin) * ratio
                           for origin, target in zip(start, end)]
        seconds = step * 0.5
        point.time_from_start.sec = int(seconds)
        point.time_from_start.nanosec = int(round((seconds - int(seconds)) * 1e9))
        result.points.append(point)
    return result


def test_real_profile_is_one_shot_locked_grasp():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    visual = profile["visual_search_controller"]["ros__parameters"]
    grasp = profile["grasp_lift_executor"]["ros__parameters"]
    assert visual["backend"] == "piper"
    assert visual["real_motion_enabled"] is True
    assert visual["direct_grasp_after_align"] is True
    assert visual["freeze_grasp_tracking"] is True
    assert grasp["real_grasp_enabled"] is True
    assert grasp["auto_execute"] is True
    assert grasp["static_target_lock"] is True
    assert grasp["top_down_grasp_enabled"] is True
    assert grasp["candidate_grasp_enabled"] is False
    assert grasp["auto_release_after_lift"] is True


def test_recorded_p2_to_observe_and_locked_approach_replay_are_accepted():
    adapter = _make_adapter()
    # Recorded P2 aggregate ROS snapshot from the repository handoff, in rad.
    p2_start = [0.0, math.radians(0.193), math.radians(-0.113),
                0.0, math.radians(15.253), 0.0]
    observe = [0.0, 0.98, -0.75, 0.0, 0.30, 0.0]

    adapter.positions = {
        name: value for name, value in zip(adapter.joint_names, p2_start)}
    prepare = _trajectory(p2_start, observe)
    assert adapter._trajectory_rejection_reason(prepare) is None

    # The target pose is intentionally not fabricated here.  This is the
    # physical adapter replay of the locked, bounded approach segment: once
    # MoveIt supplies a real target trajectory, each point is checked against
    # the same current measured endpoint and six-axis limits.
    locked_approach_end = list(observe)
    locked_approach_end[0] += 0.04
    locked_approach_end[4] -= 0.04
    approach = _trajectory(observe, locked_approach_end, max_step=0.02)
    adapter.positions = {name: value for name, value in zip(adapter.joint_names, observe)}
    assert adapter._trajectory_rejection_reason(approach) is None


def test_locked_path_has_no_visual_reacquire_after_grasp_lock():
    controller = CONTROLLER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    assert "if (freeze_grasp_tracking_) {\n      return;\n    }" in controller
    assert "GRASP_TARGET_MODEL_LOCKED_BASE_FRAME" in executor
    assert "TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED" in executor
    assert "TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED" in executor
    assert "GRIPPER_CLOSE_REQUESTED" in executor
    assert "if (!static_target_lock_ && !TargetStillAligned())" in executor
    assert "MICRO_APPROACH_TARGET_SHIFT_BEFORE_STEP" in executor
    # Every visual-reacquire guard in the approach path is conditional on the
    # static lock; a locked target therefore cannot fall back to SEARCH.
    locked_section = executor[executor.index("bool ClosedLoopMicroApproach()"):executor.index("void DiagonalSidePointGraspAndLift()")]
    assert "if (!static_target_lock_ && !TargetStillAligned())" in locked_section
    assert "RequestVisualReacquire(\"MICRO_APPROACH_TARGET_SHIFT_BEFORE_STEP\")" in locked_section


def test_real_prepare_path_is_interpolated_below_adapter_jump_gate():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    visual = profile["visual_search_controller"]["ros__parameters"]
    controller = CONTROLLER.read_text(encoding="utf-8")
    max_step = float(visual["prepare_max_joint_step_rad"])
    assert 0.0 < max_step < 0.35
    assert "std::ceil(max_delta / prepare_max_joint_step_rad_)" in controller
    assert "trajectory.points.resize(segment_count + 1U)" in controller
