"""Synthetic known-center and original-packet offline regression, no hardware."""
import ast
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).parent))
import estimate_calibration_cube_center as estimator
from simulate_paired_calibration import run_face_pipeline_simulation
from review_depth_registration import calibration, read_config


def synthetic_face(center=(-.013, .041, .453), edge=.029, tilt=(18., -4., 23.),
                   noise=0., keep=1., seed=17):
    rotation = Rotation.from_euler('xyz', tilt, degrees=True).as_matrix()
    normal = -rotation[:, 2]
    # Outward visible normal from physical center to face center.
    face = np.array(center) + edge / 2. * normal
    axis = np.linspace(-edge / 2., edge / 2., 31)
    x, y = np.meshgrid(axis, axis)
    points = face + np.c_[x.ravel(), y.ravel(), np.zeros(x.size)] @ rotation.T
    rng = np.random.default_rng(seed)
    points += rng.normal(0., noise, points.shape)
    if keep < 1:
        points = points[rng.random(len(points)) < keep]
    return points, normal, face


def test_known_tilted_cube_center_not_optical_ray_half_edge():
    points, normal, face = synthetic_face()
    result = estimator.square_hypothesis(points, .029)
    assert result['cube_center_depth_m'] == pytest.approx([-.013, .041, .453], abs=1e-7)
    assert result['face_center_depth_m'] == pytest.approx(face, abs=1e-7)
    assert result['outward_normal_depth'] == pytest.approx(normal, abs=1e-7)
    assert result['measured_face_sides_m'] == pytest.approx([.029, .029], abs=1e-7)
    assert not result['absolute_center_verified']
    wrong_ray_center = face + .0145 * face / np.linalg.norm(face)
    assert np.linalg.norm(wrong_ray_center - result['cube_center_depth_m']) > .003


def test_depth_color_coordinate_roundtrip_and_mount_not_used():
    points, _, _ = synthetic_face()
    candidate = estimator.square_hypothesis(points, .029)
    camera = {'r': Rotation.from_euler('xyz', [1., -1., .5], degrees=True).as_matrix(),
              't': np.array([-.0298, .0002, .0001])}
    transformed = estimator.transform_hypothesis(candidate, camera)
    assert transformed['C_to_D_roundtrip_error_m'] < 1e-14
    assert transformed['coordinate_frames']['depth'] == 'camera_depth_optical_frame'
    assert np.linalg.norm(np.array(transformed['cube_center_color_m']) - candidate['cube_center_depth_m']) > .015
    assert np.array(transformed['cube_center_color_m']) == pytest.approx(
        camera['r'] @ np.array(candidate['cube_center_depth_m']) + camera['t'])


def test_plane_ransac_rejects_large_depth_outliers():
    points, _, _ = synthetic_face(noise=.00025, keep=.8)
    rng = np.random.default_rng(11)
    outliers = points[:120].copy(); outliers[:, 2] += rng.uniform(.012, .025, len(outliers))
    result = estimator.square_hypothesis(np.vstack((points, outliers)), .029)
    assert np.linalg.norm(np.array(result['cube_center_depth_m']) - [-.013, .041, .453]) < .0015
    assert result['plane_inlier_fraction'] < .95
    assert result['plane_rms_m'] < .001


def test_missing_half_face_is_not_used_to_invent_the_unseen_center():
    points, _, _ = synthetic_face(tilt=(0., 0., 0.))
    partial = points[points[:, 0] > -.013]
    with pytest.raises(ValueError, match='complete nominal square'):
        estimator.square_hypothesis(partial, .029)


@pytest.mark.parametrize('points', [np.zeros((0, 3)), np.zeros((99, 3)),
                                   np.full((150, 3), np.nan), np.zeros((150, 2)),
                                   np.tile(np.linspace(0., 1., 150)[:, None], (1, 3))])
def test_absent_or_degenerate_plane_has_no_fake_normal(points):
    with pytest.raises(ValueError):
        estimator.fit_plane(points)


@pytest.mark.parametrize('edge', [0., np.nan, .2, -.029])
def test_invalid_nominal_dimension_refused(edge):
    points, _, _ = synthetic_face()
    with pytest.raises(ValueError, match='edge'):
        estimator.square_hypothesis(points, edge)


def test_twenty_frame_requirement_not_faked_from_ten_static_candidates():
    points, _, _ = synthetic_face()
    camera = {'r': np.eye(3), 't': np.zeros(3)}
    candidate = estimator.transform_hypothesis(estimator.square_hypothesis(points, .029), camera)
    frames = [{'snapshot': i, 'candidate_by_nominal_edge_mm': {'29': candidate}} for i in range(10)]
    report = estimator.summary(frames, 29., camera)
    assert report['candidates'] == 10
    assert not report['minimum_twenty_high_support_met']
    assert not report['absolute_accuracy_verified'] and not report['formal_pair_fit_allowed']


def test_nominal_size_shift_is_reported_not_stored_as_measured_edge():
    points, _, _ = synthetic_face()
    a = estimator.square_hypothesis(points, .028)
    b = estimator.square_hypothesis(points, .029)
    displacement = np.linalg.norm(np.array(a['cube_center_depth_m']) - b['cube_center_depth_m'])
    assert .0003 < displacement < .0015
    assert a['edge_is_not_confirmed_caliper_measurement']


def test_original_low_coverage_keeps_null_center_and_original_hashes():
    bundle = Path(__file__).resolve().parents[5] / 'docs/evidence/piper_calibration_20261014/pair01'
    params = read_config(bundle / 'detector_config.yaml'); camera = calibration(params)
    capture = bundle / 'pair01_observe_remeasure_20261014_rgbd'
    row = json.loads((capture / 'observer.jsonl').read_text().splitlines()[0])
    hashes = {k: v['sha256'] for k, v in row['images'].items()}
    for image in row['images'].values():
        image['path'] = str(capture / image['path'])
    result = estimator.frame_hypotheses(row, params, camera, [.029])
    assert result['color_pixel_coverage'] < .5
    assert result['candidate_by_nominal_edge_mm'] == {}
    assert not result['camera_center_verified']
    assert result['raw_image_sha256'] == hashes


def test_analysis_has_no_hardware_interfaces_and_overwrite_refused_first(tmp_path):
    tree = ast.parse(Path(estimator.__file__).read_text())
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {'create_publisher', 'create_client', 'send_goal_async', 'JointCtrl', 'GripperCtrl',
                       'ConnectPort', 'EnableArm', 'DisableArm', 'ResetPiper'}
    with pytest.raises(FileExistsError):
        estimator.review_bundle(Path('/no_input_is_read'), tmp_path)


def test_synthetic_face_to_center_to_five_pair_fit_and_one_holdout():
    report = run_face_pipeline_simulation()
    assert report['synthetic_only'] and not report['hardware_or_production_touched']
    assert len(report['trials']) == 10
    assert all(r['rank'] == 9 for r in report['trials'])
    assert report['held_out_error_p95_m'] < .002
    assert report['maximum_camera_center_error_m'] < .002
    assert report['not_a_real_calibration_precision_claim']
