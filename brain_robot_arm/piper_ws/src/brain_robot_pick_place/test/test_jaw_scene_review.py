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


def test_mesh_projection_uses_detector_endpoint_resize_and_does_not_fill_missing_image():
    detector = {'color_fx': 100., 'color_fy': 100., 'color_cx': 50., 'color_cy': 50.,
                'color_calibration_width': 101, 'color_calibration_height': 101,
                'color_mirror_horizontal': False}
    triangles = np.array([[[0., 0., 1.], [.1, 0., 1.], [0., .1, 1.]]])
    pixels, mask = review.mesh_projection(triangles, np.eye(4), np.eye(3), np.zeros(3),
                                         detector, 51, 51)
    assert pixels[0] == pytest.approx(np.array([[25., 25.], [30., 25.], [25., 30.]]))
    assert mask.shape == (51, 51) and mask[25, 25] == 255 and mask[0, 0] == 0
    detector['color_mirror_horizontal'] = True
    mirrored, _ = review.mesh_projection(triangles, np.eye(4), np.eye(3), np.zeros(3),
                                         detector, 51, 51)
    assert mirrored[0, 1, 0] == pytest.approx(20.)


def test_mesh_projection_rejects_behind_camera_triangles():
    with pytest.raises(ValueError, match='near plane'):
        review.mesh_projection(np.zeros((1, 3, 3)), np.eye(4), np.eye(3), np.zeros(3), {}, 51, 51)


def test_jaw_hypothesis_refuses_opening_beyond_model_limit_before_mesh_read():
    root = ET.fromstring('''<robot><joint name="joint7"><limit lower="0" upper=".035"/></joint>
      <joint name="joint8"><limit lower="-.035" upper="0"/></joint></robot>''')
    with pytest.raises(ValueError, match='URDF limits'):
        review.jaw_triangles_tool(root, {}, Path('/unused'), .036)


@pytest.mark.parametrize('colour_reference', [False, True])
def test_mount_pitch_hypothesis_preserves_operator_optical_tip_measurement(colour_reference):
    measured = np.array([0., .070, .105])
    tip = np.array([0., 0., .1358, 1.])
    r = review.Rotation.from_euler('y', .005).as_matrix()
    t = np.array([-.030, 0., 0.])
    original = np.eye(4)
    for degrees in (0, 10, 30, 60):
        camera = review.operator_anchored_camera(original, r, t, measured, tip,
                                                np.deg2rad(degrees), colour_reference)
        depth = (np.linalg.inv(camera) @ tip)[:3]
        result = r @ depth + t if colour_reference else depth
        assert result == pytest.approx(measured)
        assert camera[:3, :3].T @ camera[:3, :3] == pytest.approx(np.eye(3))
    assert original == pytest.approx(np.eye(4))  # Hypothesis must not overwrite the source TF.


def test_visible_finger_witnesses_are_reviewed_dark_components_not_grasp_rois():
    rgb = np.full((240, 320, 3), 200, np.uint8)
    rgb[160:240, :40] = 20
    rgb[160:240, 270:] = 20
    rgb[180:220, 120:160] = 20  # A central dark object must not become a finger.
    masks = review.visible_jaw_masks(rgb)
    assert np.count_nonzero(masks['left']) == 80 * 40
    assert np.count_nonzero(masks['right']) == 80 * 50
    assert masks['left'][200, 140] == 0 and masks['right'][200, 140] == 0
    assert review.mask_iou(masks['left'], masks['left']) == 1.
    assert review.mask_iou(masks['left'], masks['right']) == 0.
    with pytest.raises(ValueError, match='missing'):
        review.visible_jaw_masks(np.full((240, 320, 3), 200, np.uint8))


def test_inner_edge_direction_distinguishes_opposite_contours_despite_overlap():
    observed = np.zeros((12, 20), np.uint8)
    predicted = observed.copy()
    for row in range(12):
        observed[row, 4 + row:] = 255
        predicted[row, 15 - row:] = 255
    assert review.mask_iou(observed, predicted) > .4
    assert review.inner_edge_direction(observed, 'right', [2, 5, 8])['du_dv'] == pytest.approx(1.)
    assert review.inner_edge_direction(predicted, 'right', [2, 5, 8])['du_dv'] == pytest.approx(-1.)
    with pytest.raises(ValueError, match='missing'):
        review.inner_edge_direction(np.zeros_like(observed), 'right', [2, 5])


def test_structure_inventory_keeps_contact_depth_steps_separate():
    first = np.array([[0., 0., .100], [.010, 0., .100], [0., 0., .110]])
    second = first + [0., -.002, -.030]
    report = review.finger_structure(np.array([first, second]))
    assert report['extent_m'] == pytest.approx([.010, .002, .040])
    faces = report['y_normal_planar_faces']
    assert [f['y_tool_m'] for f in faces] == pytest.approx([-.002, 0.])
    assert [f['area_m2'] for f in faces] == pytest.approx([.00005, .00005])
    assert not report['physical_contact_face_verified']


def test_structure_inventory_rejects_invalid_mesh_instead_of_assigning_contacts():
    for mesh in (np.empty((0, 3, 3)), np.zeros((1, 2, 3)), np.full((1, 3, 3), np.nan)):
        with pytest.raises(ValueError):
            review.finger_structure(mesh)


def test_distal_end_selection_does_not_include_full_side_or_mounting_plane():
    end = np.array([[0., 0., .1358], [.010, 0., .1358], [0., -.007, .1358]])
    side = np.array([[0., 0., .1358], [.010, 0., .1258], [0., 0., .1258]])
    proximal = end - [0., 0., .070]
    result = review.distal_end_triangles(np.array([end, side, proximal]))
    assert result.shape == (1, 3, 3)
    assert result[0] == pytest.approx(end)
    with pytest.raises(ValueError, match='No planar distal end'):
        review.distal_end_triangles(np.array([side]))


def test_user_free_end_identity_is_bound_to_reviewed_frame_not_future_images():
    digest = '5b695ae3ad08b07f2b8e0895a897cdb7e11edd34057dda5109532b97511e412b'
    assert review.reviewed_free_end_regions(digest, True) == [('A', [95., 311.]), ('B', [513., 315.])]
    assert review.reviewed_free_end_regions('different-frame', False) == []
    with pytest.raises(ValueError, match='reviewed raw RGB frame'):
        review.reviewed_free_end_regions('different-frame', True)
