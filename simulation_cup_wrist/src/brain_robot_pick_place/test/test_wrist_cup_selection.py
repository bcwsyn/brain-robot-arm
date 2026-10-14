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


def test_multiple_valid_instances_remain_ambiguous():
    data = frame()
    with pytest.raises(ValueError, match='valid=2'):
        select_depth_valid_cup(data['depth_m'], np.repeat(data['masks'][:1], 2, axis=0), data['k'],
            data['rotation_world_camera'], data['camera_origin_world'])
