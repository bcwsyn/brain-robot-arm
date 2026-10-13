"""Focused wiring regressions; numerical/shape behavior is tested in C++."""
from pathlib import Path
import yaml

PACKAGE = Path(__file__).parents[1]
EXECUTOR = PACKAGE / 'src/grasp_lift_executor.cpp'


def test_near_depth_is_in_original_executor_and_search_depth_contract_unchanged():
    p = yaml.safe_load((PACKAGE.parent / 'brain_robot_ball_pick/config/cube_task_real.yaml').read_text())
    grasp = p['grasp_lift_executor']['ros__parameters']
    assert not grasp['near_depth_rgb_tracking_enabled'] or grasp['automatic_rgb_approach_enabled']
    assert grasp['static_target_lock'] and grasp['fresh_jaw_capture_required']
    assert not grasp['preserve_aligned_grasp_orientation']
    assert not grasp['visual_microsteps_enabled']
    d = yaml.safe_load((PACKAGE.parent / 'brain_robot_ball_pick/config/cube_detector.yaml').read_text())
    assert d['cube_detector']['ros__parameters']['require_depth_for_target_valid']


def test_prediction_retains_lock_and_measurement_stamp_and_uses_exact_tf():
    s = EXECUTOR.read_text()
    body = s[s.index('bool ObserveLockedTarget('):s.index('bool ReadVisualBox(')]
    # The approved coarse RGB-D stage may refresh the same identity; RGB
    # prediction after the deliberate terminal commit must remain immutable.
    coarse_start = body.index('if (coarse_depth_tracking_ && !coarse_motion_in_progress_) {')
    coarse_end = body.index('geometry_msgs::msg::PointStamped camera;', coarse_start)
    assert 'locked_target_reference_ = reference;' in body[coarse_start:coarse_end]
    assert 'locked_target_reference_ =' not in body[:coarse_start] + body[coarse_end:]
    assert 'measured_same_image = !terminal_target_frozen_' in body
    assert 'depth_valid_ =' not in body and 'target_valid_ =' not in body
    assert 'tf2::TimePointZero' not in body
    assert 'image_time,' in body
    assert 'latest_joint_state_' in body
    assert 'near_seed_stamp_ns_ = rclcpp::Time(reference.header.stamp).nanoseconds()' in body
    assert 'if (!near_seed_.valid || (coarse_depth_tracking_ && !coarse_motion_in_progress_))' in body
    seed = body.index('near_seed_stamp_ns_ =')
    assert body.index('if (measured_same_image)') < seed < body.index('if (!measured_same_image)', seed)
    assert 'return reject("MEASURED_TARGET_CHANGED")' in body
    assert 'near_depth::PredictionRejection' in body
    # A clipped raw contour can only RECOVER an already qualified identity;
    # it cannot seed a new lock or supply a fabricated colour/depth centroid.
    assert 'near_last_full_rgb_view_.valid && raw_box_valid_' in body
    assert 'near_depth::Cropped(raw_box_' in body
    assert 'view.recovering = recovering' in body
    commit = s[s.index('bool CommitTerminalDepthLock('):s.index('bool RemeasureTerminalTarget(')]
    assert '!coarse_depth_tracking_ || terminal_target_frozen_' in commit
    assert 'coarse_depth_tracking_ = false;' in commit
    assert 'terminal_target_frozen_ = true;' in commit


def test_actual_adapter_stop_and_final_capture_checks_remain():
    s = EXECUTOR.read_text()
    execute = s[s.index('bool ExecuteArmTrajectory('):s.index('bool TrajectoryFeedbackReached(')]
    assert execute.index('if (!observation_ok())') < execute.index('arm_trajectory_publisher_->publish')
    assert 'adapter_disarm_client_->async_send_request' in execute
    assert 'response->success' in execute
    assert execute.index('software_stop_publisher_->publish(stop)') < execute.index(
        'adapter_disarm_client_->async_send_request')
    assert 'DisableArm(' not in execute and 'ResetPiper(' not in execute
    capture = s[s.index('bool FreshFaceInsideJaws()'):s.index('bool WaitForGripperCommand(')]
    assert 'ObserveLockedTarget(face, capture_stamp, predicted)' in capture
    assert 'FaceInsideJawCapture(' in capture
    assert 'opening = JointPosition(latest_gripper_feedback_' in capture
    assert 'measurement_stamp=' in capture and 'MODEL_MOUNT_NOT_EXTERNAL_CALIBRATION' in capture
    finish = s[s.index('void FinishGraspAndLift('):s.index('bool VerifyGraspContact(')]
    assert finish.index('!FreshFaceInsideJaws()') < finish.index('near_depth_tracking_active_ = false')
    assert finish.index('near_depth_tracking_active_ = false') < finish.index('CommandRealGripper(false)')
