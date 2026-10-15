"""Measured-plane P0 audit regression; synthetic and portable evidence only."""
import ast
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).parent))
import calibration_p0_quality as p0
from test_cube_center_estimation import synthetic_face
from review_depth_registration import calibration, read_config


def test_independent_fit_agrees_on_known_plane_not_optical_axis():
    points, normal, _ = synthetic_face(noise=.0001)
    graph = p0.graph_plane(points)
    assert p0.normal_angle_deg(graph['normal'], normal) < .15
    assert graph['rms_m'] < .0002


def test_relative_plane_angle_cannot_be_fixed_by_mount_rotation():
    a, b = np.array([0., 0., 1.]), Rotation.from_euler('x', 7.5, degrees=True).apply([0., 0., 1.])
    r = Rotation.from_euler('xyz', [20., -70., 35.], degrees=True)
    assert p0.normal_angle_deg(a, b) == pytest.approx(7.5)
    assert p0.normal_angle_deg(r.apply(a), r.apply(b)) == pytest.approx(7.5)
    assert p0.normal_angle_deg(-a, b) == pytest.approx(7.5)


@pytest.mark.parametrize('points', [np.zeros((99, 3)), np.full((100, 3), np.nan),
                                   np.ones((150, 3)), np.zeros((200, 2))])
def test_independent_fit_does_not_invent_missing_plane(points):
    with pytest.raises(ValueError):
        p0.graph_plane(points)


def test_two_methods_recover_known_face_table_difference():
    face, _, center = synthetic_face(tilt=(7.5, 0., 0.), noise=.0001)
    x, y = np.meshgrid(np.linspace(-.1, .1, 50), np.linspace(-.1, .1, 50))
    table = np.c_[x.ravel(), y.ravel(), np.full(x.size, .47)]
    result = p0.plane_pair_audit(face, table, center, .029)
    assert result['normal_difference_A_deg'] == pytest.approx(7.5, abs=.2)
    assert result['normal_difference_B_deg'] == pytest.approx(7.5, abs=.2)
    assert not result['top_identity_confirmed']
    assert not result['mounting_TF_can_change_relative_normal_angle']


def test_top_selection_does_not_require_top_to_dominate_all_cube_faces():
    axis = np.linspace(-.0145, .0145, 31)
    x, y = np.meshgrid(axis, axis)
    top = np.c_[x.ravel(), y.ravel(), np.full(x.size, .441)]
    # More side points than top points; all lower than the top selection band.
    side = np.c_[np.full(2000, .0145), np.linspace(-.0145, .0145, 2000),
                 np.linspace(.450, .470, 2000)]
    tx, ty = np.meshgrid(np.linspace(-.1, .1, 40), np.linspace(-.1, .1, 40))
    table = np.c_[tx.ravel(), ty.ravel(), np.full(tx.size, .470)]
    candidate, points = p0.top_hypothesis(np.vstack((top, side)), table,
                                        {'r': np.eye(3), 't': np.array([-.03, 0., 0.])})
    assert len(points) == 961 and candidate['plane_inliers'] == 961
    assert candidate['cube_center_color_m'] == pytest.approx([-.03, 0., .4555], abs=1e-7)
    assert not candidate['selection']['physical_top_identity_independently_verified']


def test_eight_hundred_samples_are_not_eight_hundred_good_top_points():
    frames = [{'good_top_frame': False, 'face_quality_candidate': True,
               'top_identity_confirmed': False} for _ in range(60)]
    summary = p0.summarize(frames)
    assert summary['face_quality_candidates'] == 60
    assert summary['good_top_frames'] == 0
    assert not summary['twenty_good_frames_met']
    assert summary['top_witness_review_required']


def test_annulus_excludes_cube_and_interior_margin():
    yy, xx = np.mgrid[:100, :100]
    projected = np.stack((xx, yy), axis=-1)
    cube = np.zeros((100, 100), np.uint8); cube[40:60, 40:60] = 255
    selected = p0.table_mask(projected, np.ones((100, 100), bool), cube, [40, 40, 20, 20])
    assert not selected[30:70, 30:70].any()
    assert selected[20, 40] and selected[80, 80]


@pytest.mark.parametrize('box', [None, [0, 10, 20, 20], [10, 0, 20, 20],
                                [300, 20, 20, 20], [20, 220, 20, 20]])
def test_truncated_target_never_relabelled_complete_top(box):
    assert not p0.complete_box(box, (320, 240))
    assert p0.complete_box([100, 90, 20, 20], (320, 240))


def test_original_empty_depth_frame_stays_rejected_not_top():
    bundle = Path(__file__).resolve().parents[5] / 'docs/evidence/piper_calibration_20261014/pair01'
    capture = bundle / 'pair01_observe_remeasure_20261014_rgbd'
    row = json.loads((capture / 'observer.jsonl').read_text().splitlines()[0])
    for image in row['images'].values():
        image['path'] = str(capture / image['path'])
    params = read_config(bundle / 'detector_config.yaml')
    result, witness = p0.review_frame(row, params, calibration(params))
    assert not result['face_quality_candidate'] and not result['good_top_frame']
    assert result['cube_center_color_candidate_m'] is None
    assert result['plane_audit'] is None and result['plane_inliers'] == 0
    assert witness.shape == (240, 320, 3)


def test_no_interfaces_and_overwrite_refused_first(tmp_path):
    tree = ast.parse(Path(p0.__file__).read_text())
    attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not attrs & {'create_publisher', 'create_client', 'send_goal_async', 'ConnectPort', 'EnableArm'}
    with pytest.raises(FileExistsError):
        p0.review(tmp_path / 'not_read', tmp_path)
