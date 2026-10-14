"""Regression of the actual wrist-camera cup/finger false positive."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts'))
from cup_perception import select_depth_valid_cup


def frame():
    return np.load(Path(__file__).parent/'data/wrist_cup_and_finger.npz')


@pytest.mark.parametrize('reverse', [False, True])
def test_cup_survives_near_field_finger_detection_in_either_order(reverse):
    data = frame()
    masks = data['masks'][::-1] if reverse else data['masks']
    index, estimate, rejected = select_depth_valid_cup(data['depth_m'], masks, data['k'],
        data['rotation_world_camera'], data['camera_origin_world'], grasp_height_fraction=.6)
    assert index == (1 if reverse else 0)
    assert abs(estimate['diameter_m']-.075) < .002
    assert abs(estimate['observed_height_m']-.2) < .005
    assert len(rejected) == 1


def test_fingers_alone_cannot_start_a_cup_grasp():
    data = frame()
    with pytest.raises(ValueError, match='valid=0'):
        select_depth_valid_cup(data['depth_m'], data['masks'][1:], data['k'],
            data['rotation_world_camera'], data['camera_origin_world'])


def test_duplicate_masks_of_one_cup_are_merged():
    data = frame()
    index, estimate, rejected = select_depth_valid_cup(data['depth_m'], np.repeat(data['masks'][:1], 2, axis=0), data['k'],
        data['rotation_world_camera'], data['camera_origin_world'])
    assert index == 0 and len(rejected) == 1
    assert 'duplicate' in rejected[0]['reason']


def test_distinct_3d_cups_remain_ambiguous_even_with_overlapping_masks(monkeypatch):
    import cup_perception
    data = frame()
    first = cup_perception.estimate_masked_cup(data['depth_m'], data['masks'][0], data['k'],
        data['rotation_world_camera'], data['camera_origin_world'])
    second = dict(first, world_target=[first['world_target'][0]+.075, *first['world_target'][1:]])
    estimates = iter([first, second])
    monkeypatch.setattr(cup_perception, 'estimate_masked_cup', lambda *a, **k: next(estimates))
    with pytest.raises(ValueError, match='valid=2'):
        select_depth_valid_cup(data['depth_m'], np.repeat(data['masks'][:1], 2, axis=0), data['k'],
            data['rotation_world_camera'], data['camera_origin_world'])


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_random_start_duplicate_failure_is_resolved_in_either_order(reverse):
    data = np.load(Path(__file__).parent/'data/wrist_duplicate_cup.npz')
    masks = data['masks'][::-1] if reverse else data['masks']
    index, estimate, rejected = select_depth_valid_cup(data['depth_m'], masks, data['k'],
        data['rotation_world_camera'], data['camera_origin_world'], grasp_height_fraction=.6)
    assert abs(estimate['diameter_m']-.075) < .002
    assert np.linalg.norm(np.array(estimate['world_target'][:2])-[.38428709085839163, -.11245090910348665]) < .002
    assert len(rejected) == 2
