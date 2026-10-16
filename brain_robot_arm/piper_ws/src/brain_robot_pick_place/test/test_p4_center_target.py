"""Explicit center/surface distinction and old-data isolation; no ROS imports."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from test_p4_open_loop import launch_helpers

PKG = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p4_center', PKG/'scripts/prepare_p4_center_target.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sources():
    return {'frames': [{'snapshot': 1, 'actual_q_rad': [0.]*6, 'stamps_ns': {'rgb': 12},
        'candidate_by_nominal_edge_mm': {'29': {'cube_center_color_m': [.2, .1, .3]}}}]}, {
        'pairs': [{'pair': 'new_pair02', 'implied_tool_center_m_under_NEW_X': [.02, -.01, .13]}]}


def test_measured_center_is_not_treated_as_surface_or_given_another_insertion(tmp_path):
    import yaml
    review, refs = sources()
    target = module.make_target(review, refs, 'new_pair02', .029, lambda q: np.eye(4), np.eye(4))
    assert target['center_base_m'] == [.2, .1, .3]
    assert 'surface_base_m' not in target
    assert target['grasp_center_tool_m'] == [.02, -.01, .13]
    path = tmp_path/'center.yaml'
    path.write_text(yaml.safe_dump(target))
    _, grasp = launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1',
        'BRAIN_ROBOT_P4_TARGET_CONFIG': str(path)})
    assert grasp['p4_plan_only'] is True
    assert grasp['p4_target_kind'] == 'cube_center'
    assert grasp['p4_center_base_m'] == [.2, .1, .3]
    assert 'p4_surface_base_m' not in grasp


def test_missing_depth_or_face_does_not_create_a_center():
    review, refs = sources()
    review['frames'][0]['candidate_by_nominal_edge_mm'] = {}
    with pytest.raises(ValueError, match='No measured-face'):
        module.make_target(review, refs, 'new_pair02', .029, lambda q: np.eye(4), np.eye(4))


def test_heldout_is_not_repurposed_as_fit_or_an_averaged_tcp():
    review, refs = sources()
    with pytest.raises(ValueError, match='held-out'):
        module.make_target(review, refs, 'new_pair07', .029, lambda q: np.eye(4), np.eye(4))


def test_same_actual_q_is_used_to_transform_each_measurement():
    review, refs = sources()
    q = [.01, 0, 0, 0, 0, 0]
    review['frames'][0]['actual_q_rad'] = q
    def fk(actual):
        assert actual == q
        t = np.eye(4); t[0, 3] = .12
        return t
    target = module.make_target(review, refs, 'new_pair02', .029, fk, np.eye(4))
    assert target['center_base_m'] == pytest.approx([.32, .1, .3])
