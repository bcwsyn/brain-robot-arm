"""Focused wiring regressions; numerical/shape behavior is tested in C++."""
from pathlib import Path
import yaml

PACKAGE = Path(__file__).parents[1]
EXECUTOR = PACKAGE / 'src/grasp_lift_executor.cpp'


def test_near_depth_is_in_original_executor_and_search_depth_contract_unchanged():
    p = yaml.safe_load((PACKAGE.parent / 'brain_robot_ball_pick/config/cube_task_real.yaml').read_text())
    grasp = p['grasp_lift_executor']['ros__parameters']
    assert grasp['near_depth_rgb_tracking_enabled']
    assert grasp['static_target_lock'] and grasp['fresh_jaw_capture_required']
    assert not grasp['preserve_aligned_grasp_orientation']
    assert not grasp['visual_microsteps_enabled']
    d = yaml.safe_load((PACKAGE.parent / 'brain_robot_ball_pick/config/cube_detector.yaml').read_text())
    assert d['cube_detector']['ros__parameters']['require_depth_for_target_valid']


def test_prediction_retains_lock_and_measurement_stamp_and_uses_exact_tf():
    s = EXECUTOR.read_text()
    body = s[s.index('bool ObserveLockedTarget('):s.index('bool ReadVisualBox(')]
    assert 'locked_target_reference_ =' not in body
    assert 'depth_valid_ =' not in body and 'target_valid_ =' not in body
    assert 'tf2::TimePointZero' not in body
    assert 'image_time,' in body
    assert 'latest_joint_state_' in body
    assert 'near_seed_stamp_ns_ = image_time.nanoseconds()' in body
    seed = body.index('near_seed_stamp_ns_ =')
    assert body.index('if (measured_same_image)') < seed < body.index('} else {', seed)
    assert 'return reject("MEASURED_TARGET_CHANGED")' in body
    assert 'near_depth::PredictionRejection' in body
    assert 'raw_box_' not in body


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
