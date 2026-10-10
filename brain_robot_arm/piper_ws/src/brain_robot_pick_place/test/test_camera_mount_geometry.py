"""Offline regression for the operator-measured lens/fingertip offset."""
import ast
import importlib.util
import math
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
PROFILE = ROOT / 'brain_robot_ball_pick/config/cube_task_real.yaml'
LAUNCH = ROOT / 'brain_robot_ball_pick/launch/cube_visual_search.launch.py'
spec = importlib.util.spec_from_file_location(
    'camera_mount_review', Path(__file__).with_name('review_camera_mount.py'))
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_measured_tip_matches_single_real_profile_translation():
    profile = yaml.safe_load(PROFILE.read_text(encoding='utf-8'))
    mount = profile['piper_camera_mount_tf']['ros__parameters']
    tip = profile['grasp_lift_executor']['ros__parameters']['gripper_tip_offset_m']
    expected = [0.0, 0.070, 0.105]
    assert mount['operator_tip_optical_m'] == expected
    assert mount['measurement_basis_confirmed'] is True
    assert mount['rotation_calibrated'] is False
    assert mount['horizontal_offset_measured'] is False
    assert review.translation_from_tip(expected, tip, mount['rotation_rpy_rad']) == pytest.approx(
        mount['translation_m'], abs=1e-10)
    assert review.tip_in_camera(mount['translation_m'], tip, mount['rotation_rpy_rad']) == pytest.approx(
        expected, abs=1e-10)


def test_old_mount_is_not_equivalent_to_operator_measurement():
    old_tip = review.tip_in_camera([0.0, -0.05, -0.10], 0.1358, [0, -math.pi / 2, 0])
    assert old_tip == pytest.approx([-0.05, 0, 0.2358])
    assert math.dist(old_tip, [0, 0.070, 0.105]) == pytest.approx(
        math.sqrt(.05 ** 2 + .070 ** 2 + .1308 ** 2), abs=1e-10)


def test_fingertip_outside_depth_fov_is_not_image_center():
    result = review.project([0, 0.070, 0.105],
                            [478.756866, 0, 326.135559, 0, 478.756866, 199.873489, 0, 0, 1],
                            [640, 400])
    assert result['pixel'] == pytest.approx([326.135559, 519.044733], abs=1e-5)
    assert result['inside_image'] is False


def test_launch_uses_profile_and_legacy_yaw_pitch_roll_order():
    tree = ast.parse(LAUNCH.read_text(encoding='utf-8'))
    helper = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == '_camera_mount_arguments')
    namespace = {'math': math}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(LAUNCH), 'exec'), namespace)
    profile = {'piper_camera_mount_tf': {'ros__parameters': {
        'translation_m': [1, 2, 3], 'rotation_rpy_rad': [.1, .2, .3]}}}
    assert namespace['_camera_mount_arguments'](profile) == [
        '1.0', '2.0', '3.0', '0.3', '0.2', '0.1', 'gripper_base', 'camera_link']
    profile['piper_camera_mount_tf']['ros__parameters']['translation_m'][0] = math.nan
    with pytest.raises(RuntimeError):
        namespace['_camera_mount_arguments'](profile)


def test_invalid_measurement_is_not_a_fallback_to_old_mount():
    for point in ([0, math.nan, .105], [0, .070, 0], [0, .070]):
        with pytest.raises(ValueError):
            review.translation_from_tip(point, .1358, [0, -math.pi / 2, 0])
