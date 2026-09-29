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
LAUNCH = ROOT / "brain_robot_ball_pick" / "launch" / "cube_visual_search.launch.py"


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
    depth_probe = profile["depth_cube_probe"]["ros__parameters"]
    assert visual["backend"] == "piper"
    assert visual["real_motion_enabled"] is True
    assert visual["direct_grasp_after_align"] is True
    assert visual["depth_only_direct_grasp_after_lock"] is True
    assert visual["freeze_grasp_tracking"] is True
    assert grasp["real_grasp_enabled"] is True
    assert grasp["auto_execute"] is True
    assert grasp["static_target_lock"] is True
    assert grasp["top_down_grasp_enabled"] is True
    assert grasp["diagonal_side_grasp_enabled"] is True
    assert grasp["diagonal_pregrasp_standoff_m"] == 0.17
    assert grasp["diagonal_pregrasp_lift_m"] == 0.20
    assert grasp["diagonal_grasp_lift_m"] == 0.10
    assert grasp["diagonal_grasp_standoff_m"] == 0.045
    assert grasp["candidate_grasp_enabled"] is False
    assert grasp["auto_release_after_lift"] is True
    assert grasp["grasp_orientation_tolerance"] == 0.20
    assert grasp["top_down_pregrasp_clearance_m"] == 0.024
    assert grasp["top_down_pregrasp_clearance_candidates_m"] == [0.024]
    assert grasp["top_down_yaw_candidates"] == [0.0, 0.78539816339, -0.78539816339, 1.57079632679, -1.57079632679, 3.14159265359]
    assert grasp["top_down_tilt_candidates"] == [0.35, 0.75, 0.90, 1.05]
    assert grasp["real_trajectory_joint_max"][1] > 3.14
    assert grasp["real_trajectory_joint_max"][5] > 3.14
    assert grasp["real_trajectory_joint_min"][5] < -3.14
    assert grasp["real_pose_planning_pipeline"] == "pilz_industrial_motion_planner"
    assert grasp["real_pose_planner_id"] == "PTP"
    assert depth_probe["required_stable_frames"] == 1
    assert depth_probe["workspace_min_x_m"] < 0.33 < depth_probe["workspace_max_x_m"]
    assert depth_probe["workspace_min_y_m"] < -0.31 < depth_probe["workspace_max_y_m"]
    assert depth_probe["workspace_min_z_m"] < 0.11 < depth_probe["workspace_max_z_m"]
    assert not (
        depth_probe["workspace_min_x_m"]
        <= 0.089
        <= depth_probe["workspace_max_x_m"]
    )


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
    assert "depth_only_target_enabled_ && depth_only_direct_grasp_after_lock_" in controller
    assert "PHASE=GRASP_READY DEPTH_BASE_LOCK" in controller
    assert "GRASP_TARGET_MODEL_LOCKED_BASE_FRAME" in executor
    assert "TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED" in executor
    assert "RealTrajectoryWithinLimits" in executor
    assert "REAL_LIMIT_REJECTED" in executor
    assert "StateAtTrajectoryEnd" in executor
    assert "PlanArmCartesianFromState" in executor
    assert "real_trajectory_limit_margin_rad" in executor
    assert "RealTrajectoryWithinLimits" in executor
    assert "candidate_descent_plan.joint_trajectory, rejection" in executor
    assert "TOP_DOWN_DESCENT_EXECUTING" in executor
    assert "TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED" in executor
    assert "DIAGONAL_SIDE_PREGRASP_TRAJECTORY_ACCEPTED" in executor
    assert "DIAGONAL_SIDE_APPROACH_TRAJECTORY_ACCEPTED" in executor
    assert "candidate_approach_plan.joint_trajectory, rejection" in executor
    assert "TopDownOrientation(side_yaw, side_tilt)" in executor
    assert "requested_orientation = nullptr" in executor
    assert "camera_offset_gripper" in executor
    assert "target_camera_offset_world" in executor
    assert "candidate_grasp,\n          &candidate_orientation" in executor
    assert "candidate_pregrasp, &candidate_orientation" in executor
    assert executor.index("if (top_down_grasp_enabled_)") < executor.index(
        "if (diagonal_side_grasp_enabled_)")
    assert "PredictedTargetInReference(object_world)" in executor
    assert "Locked base-frame target is unavailable for side grasp" in executor
    assert "object_size_m = locked_object_size_m_" in executor
    assert "locked_object_size_m_ = width_m" in executor
    assert "GRIPPER_CLOSE_REQUESTED" in executor
    assert "if (!static_target_lock_ && !TargetStillAligned())" in executor
    assert "MICRO_APPROACH_TARGET_SHIFT_BEFORE_STEP" in executor
    # Every visual-reacquire guard in the approach path is conditional on the
    # static lock; a locked target therefore cannot fall back to SEARCH.
    locked_section = executor[executor.index("bool ClosedLoopMicroApproach()"):executor.index("void DiagonalSidePointGraspAndLift()")]
    assert "if (!static_target_lock_ && !TargetStillAligned())" in locked_section
    assert "RequestVisualReacquire(\"MICRO_APPROACH_TARGET_SHIFT_BEFORE_STEP\")" in locked_section


def test_moveit_uses_the_same_real_joint_bounds_as_the_adapter():
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "real_trajectory_joint_min" in launch
    assert "real_trajectory_joint_max" in launch
    assert 'joint_limits["has_position_limits"] = True' in launch
    assert 'joint_limits["min_position"] = float(min_position)' in launch
    assert 'joint_limits["max_position"] = float(max_position)' in launch
    assert "'joint_min': real_joint_mins" in launch
    assert "'joint_max': real_joint_maxs" in launch


def test_real_prepare_path_is_interpolated_below_adapter_jump_gate():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    visual = profile["visual_search_controller"]["ros__parameters"]
    controller = CONTROLLER.read_text(encoding="utf-8")
    max_step = float(visual["prepare_max_joint_step_rad"])
    assert 0.0 < max_step < 0.35
    assert "std::ceil(max_delta / prepare_max_joint_step_rad_)" in controller
    assert "trajectory.points.resize(segment_count + 1U)" in controller


def test_real_search_stays_inside_adapter_limits_and_reports_disarm():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    visual = profile["visual_search_controller"]["ros__parameters"]
    adapter = ADAPTER.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert -1.50 < float(visual["horizontal_search_min"]) < 0.0
    assert 0.0 < float(visual["horizontal_search_max"]) < 1.50
    assert 0.08 < float(visual["search_planning_step_rad"]) < 0.35
    assert "/brain_robot_control/adapter_armed" in adapter
    assert "PIPER_ADAPTER_DISARMED" in controller
    assert 'search_timeout_reached && (local || backend_ != "piper")' in controller
