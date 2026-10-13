"""Regression for the observed first-step stall; no hardware commands."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'brain_robot_pick_place/src/grasp_lift_executor.cpp'
PROFILE = ROOT / 'brain_robot_ball_pick/config/cube_task_real.yaml'


def test_automatic_approach_uses_original_endpoint_tolerance():
    source = SOURCE.read_text()
    method = source[source.index('  bool ExecuteVisualPose('):
                    source.index('  void VisualMicrostepPreview(')]
    assert 'completed ? trajectory_feedback_tolerance_rad_ : .002' in method
    assert 'end.positions[i]) <= endpoint_tolerance' in method
    assert 'settled_positions[i]) > .002' in method
    assert 'settled).count() >= .5' in method
    assert 'raw_full_frames_ = 0' in method
    assert 'if (!completed)' in method  # Three-frame wait retained for preview, not automatic.


def test_observed_j6_error_is_inside_original_not_preview_tolerance():
    parameters = yaml.safe_load(PROFILE.read_text())['grasp_lift_executor']['ros__parameters']
    actual_j6 = 0.0
    commanded_j6 = -0.0114086
    error = abs(actual_j6 - commanded_j6)
    assert error > .002
    assert error <= parameters['trajectory_feedback_tolerance_rad']
    # Final closure/landing checks are independent and remain unchanged.
    assert parameters['fresh_jaw_capture_required']
    assert parameters['grasp_landing_feedback_tolerance_rad'] == .010


def test_prepublication_rejections_report_metrics_without_new_bounds():
    source = SOURCE.read_text()
    method = source[source.index('  bool ExecuteVisualPose('):
                    source.index('  void VisualMicrostepPreview(')]
    assert '_POSE_STEP_BOUND_REJECTED' in method
    assert '_START_FEEDBACK_CHANGED' in method
    assert 'wrist=%.9f/%.9f tip=%.9f/%.9f angle=%.9f/%.9f' in method
    assert '> wrist_limit + 1e-9' in method
    assert '> tip_limit + 1e-9' in method
    assert 'Eigen::Quaterniond(pose.rotation())) > angle_limit' in method
    assert 'state->getVariablePosition(name)) > (completed ? trajectory_feedback_tolerance_rad_ : .002)' in method


def test_automatic_angle_comparison_ignores_observed_solver_roundoff_only():
    source = SOURCE.read_text()
    assert 'angle_limit + (completed ? 1e-6 : 0.0)' in source
    limit = .017453293
    observed = .017453373
    assert observed > limit
    assert observed <= limit + 1e-6
    assert limit + 2e-6 > limit + 1e-6


def test_rgb_correction_reuses_observation_snapshot_across_tf_wait():
    source = SOURCE.read_text()
    observe = source[source.index('  bool ObserveLockedTarget('):
                     source.index('  bool ReadVisualBox(')]
    assert observe.index('*observed_box = message') < observe.index('lookupTransform(')
    assert '*observed_info = info' in observe
    assert '*observed_calibration = calibration' in observe
    correction = source[source.index('  bool LockedRgbCorrection('):
                        source.index('  void AutomaticRgbApproach(')]
    assert 'ObserveLockedTarget(locked, image_time, predicted, &box, &info, &c, &snapshot)' in correction
    assert 'box = qualified_box_message_' not in correction
    assert 'info = raw_image_info_' not in correction
    assert 'rclcpp::Time(box.header.stamp) != image_time' in correction


def test_automatic_waypoints_use_existing_real_landing_tolerances():
    source = SOURCE.read_text()
    automatic = source[source.index('  void AutomaticRgbApproach('):
                       source.index('  void TargetDirectedPointGraspAndLift(')]
    assert 'std::sqrt(gap_squared) <= grasp_landing_tolerance_m_' in automatic
    assert 'grasp_landing_orientation_tolerance_rad_' in automatic
    assert '!FreshFaceInsideJaws()' in automatic
    assert '!EnsureRealTopDownLanding(last_goal, last_trajectory)' in automatic
    parameters = yaml.safe_load(PROFILE.read_text())['grasp_lift_executor']['ros__parameters']
    assert .006872936 <= parameters['trajectory_feedback_tolerance_rad']
    assert parameters['grasp_landing_tolerance_m'] == .010
    assert parameters['grasp_landing_orientation_tolerance_rad'] == .12


def test_automatic_uses_distinct_fresh_frame_and_tip_preserving_view_guard():
    source = SOURCE.read_text()
    automatic = source[source.index('  void AutomaticRgbApproach('):
                       source.index('  void TargetDirectedPointGraspAndLift(')]
    assert 'if (!WaitApproachVisualBox())' in automatic
    assert 'GuardApproachView(nominal, tool_to_camera, view)' in automatic
    assert 'if (recovery) {nominal = current;}' in automatic
    assert 'near_last_command_image_stamp_ns_ = view.valid ? view.stamp_ns' in automatic
    wait = source[source.index('  bool WaitApproachVisualBox('):
                  source.index('  bool VisualFaceInReference(')]
    assert 'raw_box_stamp_ns_ > near_last_command_image_stamp_ns_' in wait
    assert 'qualified_same_frame || clipped_known_frame' in wait
    guard = source[source.index('  bool GuardApproachView('):
                   source.index('  void AutomaticRgbApproach(')]
    assert 'AimCameraAtFixedTip' in guard
    assert 'JointCtrl' not in guard and 'joint_commands' not in guard
