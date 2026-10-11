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


def test_static_entry_waits_for_sampled_tf_before_gripper_or_approach():
    source = EXECUTOR.read_text(encoding="utf-8")
    entry = source[source.index("void PointGraspAndLift()"):
                   source.index("void PointGraspAndLift()") + 1900]
    assert "!WaitForTargetModel()" in entry
    assert "STATIC_TARGET_MODEL_UNAVAILABLE" not in entry
    assert entry.index("!WaitForTargetModel()") < entry.index("CommandRealGripper(true)")
    retry = source[source.index("void RetryFreshTargetTransform()"):
                   source.index("bool CaptureTargetModel(")]
    assert "rclcpp::Time stamp(camera_point.header.stamp)" in retry
    assert "lookupTransform(lift_reference_frame_, frame, stamp)" in retry
    assert "target_reference_received_time_ = received;" in retry
    assert "received != target_point_received_time_" in retry
    assert "target_timeout_s_" in retry
    assert "rclcpp::ok() && !cancel_requested_" in retry
    assert "milliseconds(20)" in retry
    assert "WAITING_FOR_FRESH_TARGET_TF" in retry
    assert "TimePointZero" not in retry
DETECTOR = Path(__file__).parents[1] / "src" / "cup_detector_node.cpp"


def test_visual_preview_is_off_and_strictly_bounded_on_real_default():
    params = yaml.safe_load(CONFIG.read_text())["grasp_lift_executor"]["ros__parameters"]
    assert params["visual_microsteps_enabled"] is False
    assert params["visual_microstep_max_steps"] == 4
    assert params["visual_microstep_m"] <= .005
    assert params["visual_view_recovery_angle_rad"] <= math.radians(1) + 1e-9
    assert params["visual_view_recovery_steps"] <= 3
    assert params.get("visual_jaw_image_roi", []) == []
    assert params["visual_jaw_image_roi_confirmed"] is False
    source = EXECUTOR.read_text()
    body = source[source.index("void VisualMicrostepPreview()"):
                  source.index("void TargetDirectedPointGraspAndLift()")]
    assert "total_travel + travel > .020" in body
    assert "from_start > .020" in body
    assert "travel > .005" in body and "tip_travel > .005" in body
    assert "FinishGraspAndLift" not in body
    assert "VISUAL_PREVIEW_HOLD_NO_CLOSE" in body
    assert "CommandRealGripper" not in body
    assert "RequestReacquire" not in body
    settle = source[source.index("bool ExecuteVisualPose("):
                    source.index("void VisualMicrostepPreview()")]
    assert "PlanArmCartesianFromState(" in settle
    assert "RealTrajectoryWithinLimits(" in settle
    assert "ExecuteArmTrajectory(" in settle
    assert "raw_full_frames_ = 0" in settle
    assert "<= .002" in settle
    association = source[source.index("bool VisualFaceInReference("):
                         source.index("bool ExecuteVisualPose(")]
    assert "raw_box_stamp_ns_ != stamp" in association
    assert "raw_target_projection_.header.stamp" in association


def test_raw_colour_observation_precedes_depth_black_mask_and_is_not_grasp_valid():
    source = DETECTOR.read_text()
    images = source[source.index("void on_images("):source.index("void PublishRawColorObservation(")]
    assert images.index("PublishRawColorObservation(") < images.index("software_register_color_to_depth(")
    raw = source[source.index("void PublishRawColorObservation("):
                 source.index("std::string rgb_topic_")]
    assert "raw_color_bbox" in source
    assert "raw_color_debug" in source
    assert "publish_valid" not in raw
    assert "publish_depth_valid" not in raw
    assert "observation.header = header" in raw
    assert "RAW COLOUR ONLY" in raw

LAUNCH = ROOT / "brain_robot_ball_pick" / "launch" / "cube_visual_search.launch.py"
DETECTOR_CONFIG = ROOT / "brain_robot_ball_pick" / "config" / "cube_detector.yaml"
START_SCRIPT_CANDIDATES = [
    Path(__file__).parents[4] / "scripts" / "start_brain_robot_cube_real.sh",
    Path.home() / "start_brain_robot_cube_real.sh",
]
ASTRA_PARAMS = (
    Path(__file__).parents[4] / "ros2_ws" / "src" / "ros2_astra_camera" /
    "astra" / "src" / "astra_camera" / "params" / "astra_params.yaml"
)


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
    assert visual["stop_after_observe"] is False
    assert visual["stop_after_target_acquired"] is False
    assert visual["initial_search_center_first"] is True
    assert visual["initial_search_hold_s"] == 2.0
    controller = CONTROLLER.read_text(encoding="utf-8")
    hold_gate = controller.index('ParameterOr<bool>("stop_after_observe", false)')
    hold_state = controller.index("OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH")
    search_transition = controller.index('SetStateLocked(ControlState::SEARCH, "OBSERVE_POSE_REACHED")')
    assert hold_gate < hold_state < search_transition
    prepare = controller[controller.index("void PrepareWorker()"):
                         controller.index("bool CallServoService(")]
    assert 'center_first_search_.Reset(' in prepare
    assert 'PublishHoldTrajectoryLocked();' in prepare
    search_handler = controller[controller.index("void HandleSearchLocked(bool local)"):
                                controller.index("void HandleLastPathReacquireLocked()")]
    assert search_handler.index("TargetFreshLocked()") < search_handler.index("StepCenterFirstSearchLocked()")
    assert "CENTER_SEARCH_NOT_REACHED_NO_FULL_SWEEP" in search_handler
    assert "search::BoundedStep(" in controller
    assert "move_group->setPathConstraints(hold_constraints)" in controller
    assert "search::MakeHoldBand(anchor, measured, joint_position_tolerance_)" in controller
    assert "move_group->setStartState(*measured_state)" in controller
    assert "constraint.tolerance_above = band->above" in controller
    assert "SEARCH_HOLD_AXIS_DRIFT_EXCEEDED_" in controller
    assert "std::min(joint_position_tolerance_, 0.0001)" in controller
    assert "CENTER_RETURN_CONFIRMED_EXPAND_EXISTING_FULL_SEARCH" in controller
    acquired_gate = 'ParameterOr<bool>("stop_after_target_acquired", false)'
    acquired_reason = '"TARGET_ACQUIRED_STOPPED_BEFORE_ALIGN"'
    for handler in ("HandleSearchLocked", "HandleLastPathReacquireLocked"):
        start = controller.index(f"void {handler}(")
        end = controller.find("\n  void ", start + 1)
        body = controller[start:end]
        assert body.index(acquired_gate) < body.index("ControlState::ALIGN")
        assert acquired_reason in body
    assert visual["direct_grasp_after_align"] is True
    assert visual["depth_only_target_enabled"] is False
    assert visual["depth_only_direct_grasp_after_lock"] is True
    assert visual["freeze_grasp_tracking"] is True
    assert grasp["real_grasp_enabled"] is True
    assert grasp["auto_execute"] is True
    assert grasp["depth_only_target_enabled"] is False
    assert grasp["static_target_lock"] is True
    assert grasp["target_directed_grasp_enabled"] is True
    assert grasp["preserve_aligned_grasp_orientation"] is False
    assert grasp["gripper_open_value"] == 50000
    assert abs(0.0462 - grasp["gripper_open_value"] / 1e6) > grasp["gripper_position_tolerance_m"]
    assert grasp["gripper_close_value"] == 0
    assert grasp["gripper_position_tolerance_m"] == 0.003
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


def test_real_profile_uses_low_bandwidth_rgb_with_depth_geometry():
    detector = DETECTOR.read_text(encoding="utf-8")
    detector_config = yaml.safe_load(DETECTOR_CONFIG.read_text(encoding="utf-8"))
    detector_params = detector_config["cube_detector"]["ros__parameters"]
    astra_params = yaml.safe_load(ASTRA_PARAMS.read_text(encoding="utf-8"))
    start_script_path = next(path for path in START_SCRIPT_CANDIDATES if path.is_file())
    start_script = start_script_path.read_text(encoding="utf-8")
    assert 'BRAIN_ROBOT_DEPTH_ONLY_TARGET:-0' in start_script
    assert 'ros2 run image_tools cam2image' in start_script
    assert '-p width:=320' in start_script
    assert '-p height:=240' in start_script
    assert '-p frequency:=5.0' in start_script
    assert 'RGB_DEPTH_GRID_ALIGNED' in detector
    assert 'cv::resize(processing_image(crop), aligned_image, depth_size' in detector
    assert 'RGB_DEPTH_SOFTWARE_ALIGNED' in detector
    assert detector_params["rgb_topic"] == "/camera/color/image_raw"
    assert detector_params["depth_topic"] == "/camera/depth/image_raw"
    assert detector_params["camera_info_topic"] == "/camera/depth/camera_info"
    assert detector_params["camera_optical_frame"] == "camera_depth_optical_frame"
    assert detector_params["require_depth_for_target_valid"] is True
    assert detector_params["saturation_min"] == 35
    assert detector_params["software_registration_enabled"] is True
    assert detector_params["color_mirror_horizontal"] is False
    assert len(detector_params["depth_to_color_rotation"]) == 9
    assert len(detector_params["depth_to_color_translation_m"]) == 3
    assert detector_params["depth_to_color_translation_m"][0] < -0.02
    assert astra_params["depth_align"] is False
    assert astra_params["enable_color"] is False
    assert astra_params["uvc_camera.enable"] is False


def test_top_down_surface_landing_is_checked_before_close():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    params = profile["grasp_lift_executor"]["ros__parameters"]
    assert params["top_down_surface_grasp_enabled"] is True
    assert params["top_down_grasp_clearance_m"] == 0.0
    assert 0.0 < params["surface_insertion_fraction"] < 0.5
    assert params["surface_insertion_max_m"] == 0.012
    assert params["grasp_landing_tolerance_m"] == 0.010
    assert params["grasp_landing_max_correction_m"] == 0.020
    source = EXECUTOR.read_text(encoding="utf-8")
    start = source.index("void TopDownPointGraspAndLift()")
    end = source.index("bool EnsureRealTopDownLanding(", start)
    body = source[start:end]
    assert "candidate_grasp_target, true" in body
    assert body.index("EnsureRealTopDownLanding(final_grasp_target)") < body.index(
        "FinishGraspAndLift(pregrasp_target)")
    check = source[end:source.index("void FinishGraspAndLift(", end)]
    assert 'FreshMeasuredState("GRASP_LANDING")' in check
    assert "attempt < 2" in check
    assert "grasp_geometry::DecideLanding(" in check
    assert "grasp_geometry::LandingDecision::REJECT" in check
    assert 'MoveArmCartesianToPose(expected, "GRASP_LANDING_CORRECTION")' in check
    assert "CommandRealGripper" not in check
    assert "TargetStillAligned" not in check


def test_aligned_orientation_is_captured_once_before_both_planned_segments():
    source = EXECUTOR.read_text(encoding="utf-8")
    body = source[source.index("void TopDownPointGraspAndLift()"):
                  source.index("bool EnsureRealTopDownLanding(")]
    assert body.count("CurrentPoseInFrame(lift_reference_frame_)") == 1
    assert body.index("locked_approach_orientation_ =") < body.index("for (const double clearance")
    assert 'WaitForFreshJointState("ALIGNED_ORIENTATION_LOCK")' in body
    assert "!static_target_lock_ || !target_model_locked_" in body
    assert "std::vector<double>{0.0} : top_down_tilt_candidates_" in body
    assert "std::vector<double>{0.0} : top_down_yaw_candidates_" in body
    assert body.index("PlanArmCartesianFromState(") < body.index("ExecuteArmTrajectory(")
    geometry = source[source.index("void PopulateTopDownPose("):
                      source.index("bool TopDownPoseHasIk(")]
    assert "locked_approach_orientation_ : TopDownOrientation(yaw, tilt)" in geometry
    assert "grasp_geometry::ToolOrigin(" in geometry


def test_approved_pitch_down_changes_pose_goal_not_joint_trajectory():
    params = yaml.safe_load(CONFIG.read_text())["grasp_lift_executor"]["ros__parameters"]
    assert math.isclose(params["aligned_grasp_pitch_down_rad"], math.radians(5))
    source = EXECUTOR.read_text()
    body = source[source.index("void TopDownPointGraspAndLift()"):
                  source.index("bool EnsureRealTopDownLanding(")]
    assert 'getJointModel("joint5")' in body
    assert "grasp_geometry::RotateOrientationAboutAxis(" in body
    assert body.index("RotateOrientationAboutAxis(") < body.index("for (const double clearance")
    assert "POSE_GOAL_ONLY_NO_JOINT_TRAJECTORY_EDIT" in body


def test_target_directed_grasp_uses_variable_pose_waypoints_and_original_finish():
    params = yaml.safe_load(CONFIG.read_text())["grasp_lift_executor"]["ros__parameters"]
    assert params["target_directed_grasp_enabled"] is True
    assert params["preserve_aligned_grasp_orientation"] is False
    source = EXECUTOR.read_text()
    owner = source[source.index("void TargetDirectedPointGraspAndLift()"):
                   source.index("void TopDownPointGraspAndLift()")]
    assert "grasp_geometry::TargetDirectedApproach(" in owner
    assert owner.count("PlanArmCartesianWaypointsFromState(") == 2
    assert owner.index("predicted_pre, descent_plan") < owner.index("if (!execute(pre_plan)")
    assert owner.index("RealTrajectoryWithinLimits(") < owner.index("if (!execute(pre_plan)")
    assert owner.index("EnsureRealTopDownLanding(final_target)") < owner.index(
        "FinishGraspAndLift(retreat)")
    assert "locked_approach_orientation_ =" not in owner
    assert "CommandRealGripper" not in owner
    assert "top_down_tilt_candidates_" not in owner
    entry = source[source.index("void TopDownPointGraspAndLift()"):
                   source.index("bool EnsureRealTopDownLanding(")]
    assert entry.index("TargetDirectedPointGraspAndLift();") < entry.index(
        "if (preserve_aligned_grasp_orientation_)")


def test_real_close_needs_fresh_face_inside_jaw_capture_not_only_locked_fk():
    profile = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert profile["grasp_lift_executor"]["ros__parameters"]["fresh_jaw_capture_required"] is True
    source = EXECUTOR.read_text(encoding="utf-8")
    body = source[source.index("void FinishGraspAndLift("):source.index("bool VerifyGraspContact(")]
    assert body.index("!FreshFaceInsideJaws()") < body.index('PublishState("CLOSING_GRIPPER")')
    assert 'Fail("FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE")' in body
    check = source[source.index("bool FreshFaceInsideJaws()"):source.index("bool WaitForGripperCommand(")]
    assert "face = target_point_camera_" in check
    assert "grasp_geometry::FaceInsideJawCapture(" in check
    assert "locked_target_reference_ =" not in check
    assert "MoveArm" not in check and "CommandRealGripper" not in check


def test_one_click_supports_opt_in_search_only_stop_without_waiting_for_key():
    start_script_path = next(path for path in START_SCRIPT_CANDIDATES if path.is_file())
    start_script = start_script_path.read_text(encoding="utf-8")
    assert 'AUTO_START="${BRAIN_ROBOT_AUTO_START:-1}"' in start_script
    assert 'STOP_AFTER_TARGET_ACQUIRED="${BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED:-0}"' in start_script
    set_guard = start_script.index(
        "ros2 param set /visual_search_controller stop_after_target_acquired true")
    auto_start = start_script.index('if [[ "$AUTO_START" == "1"')
    assert start_script.index('echo "[7/7] 全部组件已就绪。"') < set_guard < auto_start
    assert 'restart_visual_sequence' in start_script[auto_start:]


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
    assert "Real arm trajectory endpoint:" in executor
    assert "Real arm trajectory feedback timeout:" in executor
    assert '<< "_measured=" << measured' in executor
    assert '<< "_target=" << target' in executor
    assert '<< "_error=" << std::abs(measured - target)' in executor
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
    assert "OPEN_GRIPPER_FEEDBACK_UNCONFIRMED" in executor
    assert "WaitForGripperCommand(" in executor
    assert "contact_motion_confirmed" in executor
    assert "GRIPPER_RELEASE_OPEN" in executor
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
