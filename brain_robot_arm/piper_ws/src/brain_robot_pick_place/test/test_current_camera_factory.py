"""Pin the approved current-device K/R/T update and unchanged depth gates."""
import json
from pathlib import Path

import pytest
import yaml


ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'CODEX_TASK_PROMPT.md').is_file())


def test_current_camera_configuration_matches_read_only_factory_evidence():
    evidence = json.loads((ROOT / 'docs/evidence/piper_camera_factory_20261013.json').read_text())
    config = ROOT / 'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'
    parameters = yaml.safe_load(config.read_text())['cube_detector']['ros__parameters']
    assert evidence['serial'] == 'CC1365304DG'
    assert evidence['read_only'] and not evidence['motion_sent'] and evidence['service_success']
    assert [parameters[name] for name in ('color_calibration_width', 'color_calibration_height')] == evidence['color_size']
    assert [parameters[name] for name in ('color_fx', 'color_fy', 'color_cx', 'color_cy')] == evidence['color_intrinsics']
    assert parameters['depth_to_color_rotation'] == evidence['depth_to_color_rotation']
    assert parameters['depth_to_color_translation_m'] == pytest.approx(
        [value * .001 for value in evidence['depth_to_color_translation_mm']], abs=1e-15)
    assert parameters['color_mirror_horizontal'] is False
    assert parameters['min_depth_samples'] == 10
    assert parameters['max_depth_mad_m'] == .012
    assert parameters['max_depth_frame_delta_m'] == .030
    assert parameters['required_depth_stable_frames'] == 3
    assert parameters['require_depth_for_target_valid'] is True
    assert parameters['min_depth_m'] == .05
    assert parameters['max_depth_m'] == 3.0
