"""Offline statistics/geometry only; no ROS or device calls."""
import numpy as np
import pytest

from review_calibration_capture import cube_center_from_face, temporal_summary


def test_temporal_median_is_per_frame_not_weighted_by_point_count():
    frames = [{'surface_z_m': .438, 'native_depth_samples': 1000}] * 29 + [
        {'surface_z_m': .454, 'native_depth_samples': 1000000}]
    r = temporal_summary(frames)
    assert r['median_z_m'] == pytest.approx(.438)
    assert r['peak_to_peak_m'] == pytest.approx(.016)
    assert r['thirty_frame_requirement_met']
    assert not r['accuracy_verified']


def test_missing_depth_does_not_become_zero_or_filled_measurement():
    r = temporal_summary([{'surface_z_m': None}] * 30)
    assert r['median_z_m'] is None and r['usable_frames'] == 0
    assert not r['thirty_frame_requirement_met']


def test_seven_frames_do_not_satisfy_thirty_frame_requirement():
    assert not temporal_summary([{'surface_z_m': .438}] * 7)['thirty_frame_requirement_met']


def test_cube_center_uses_face_normal_not_line_of_sight():
    p = np.array([.1, .0, .4]); outward = np.array([0., -.6, -.8])
    c = np.array(cube_center_from_face(p, outward, .028))
    assert np.linalg.norm(c - p) == pytest.approx(.014)
    assert c == pytest.approx([.1, .0084, .4112])
    assert not np.allclose(c, p + .014 * p / np.linalg.norm(p))


@pytest.mark.parametrize('normal,edge', [([0, 0, 0], .028), ([0, 0, 1], 0), ([0, 0, 1], float('nan'))])
def test_invalid_geometry_is_not_reported_as_center(normal, edge):
    with pytest.raises(ValueError):
        cube_center_from_face([0, 0, .4], normal, edge)
