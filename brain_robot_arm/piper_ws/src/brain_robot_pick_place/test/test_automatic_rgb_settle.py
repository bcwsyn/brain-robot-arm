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
