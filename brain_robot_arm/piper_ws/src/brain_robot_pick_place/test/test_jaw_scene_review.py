"""Offline tests for the read-only model review, not hardware calibration."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('jaw_review', Path(__file__).with_name('review_jaw_scene.py'))
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_parallel_fingers_optical_projection_can_be_outside_rgb():
    k = np.array([[244.43425, 0, 155.36526], [0, 244.43425, 104.51883], [0, 0, 1]])
    pixel = review.project([0, .070, .105], k)
    assert pixel[1] > 240
    assert pixel[1] == pytest.approx(267.475, abs=.001)


def test_lens_baseline_changes_horizontal_projection_not_down_forward_measurement():
    k = np.array([[244.43425, 0, 155.36526], [0, 244.43425, 104.51883], [0, 0, 1]])
    colour = np.array([0, .070, .105])
    depth_interpretation = colour + [-.030, 0, 0]
    a, b = review.project(colour, k), review.project(depth_interpretation, k)
    assert a[1] == pytest.approx(b[1])
    assert a[0] - b[0] == pytest.approx(69.838, abs=.001)


def test_fk_includes_fixed_tool_and_both_prismatic_fingers():
    root = ET.fromstring('''<robot><joint name="axis" type="revolute">
      <parent link="base"/><child link="tool"/><axis xyz="0 0 1"/>
      <origin xyz="1 0 0"/></joint><joint name="finger" type="prismatic">
      <parent link="tool"/><child link="pad"/><axis xyz="0 1 0"/>
      <origin xyz="0 0 .1358"/></joint></robot>''')
    result = review.poses(root, {'axis': 0., 'finger': .020})
    assert result['pad'][:3, 3] == pytest.approx([1., .020, .1358])
    with pytest.raises(KeyError):
        review.poses(root, {'axis': 0.})  # Do not fabricate a measured finger state.


def test_projection_refuses_a_point_behind_camera():
    with pytest.raises(ValueError):
        review.project([0, 0, -.1], np.eye(3))


def test_review_has_no_motion_or_enable_client():
    source = Path(__file__).with_name('review_jaw_scene.py').read_text()
    assert 'create_publisher' not in source
    assert 'GetParameters' in source and 'GetPlanningScene' in source
    assert '/enable_srv' not in source and '/joint_commands' not in source
