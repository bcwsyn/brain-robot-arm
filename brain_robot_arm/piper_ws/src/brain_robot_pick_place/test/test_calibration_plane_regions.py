"""Offline sensitivity diagnostics, never motion or threshold tuning."""
import ast
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).parent))
import audit_calibration_plane_regions as audit


def plane():
    x, y = np.meshgrid(np.linspace(-.05, .05, 35), np.linspace(-.05, .05, 35))
    return np.c_[x.ravel(), y.ravel(), (.45 + .1 * x + .2 * y).ravel()]


def test_independent_and_same_support_methods_agree_on_true_plane():
    result = audit.compare_planes(plane())
    assert result['A_vs_B_deg'] < 1e-5
    assert result['A_vs_B_same_support_deg'] < 1e-5
    assert result['A_inliers'] == 1225
    assert result['B_same_support_is_not_an_independent_support_test']


def test_boundary_contamination_changes_full_roi_not_truth():
    points = plane()
    contaminated = points.copy()
    contaminated[:220, 2] += .010
    result = audit.compare_planes(contaminated)
    assert result['A_inliers'] < len(points)
    assert result['A_vs_B_deg'] > .05
    assert result['A_vs_B_same_support_deg'] < .01


def test_half_edge_difference_is_not_whole_calibration_accuracy():
    a = np.array([0., 0., -1.])
    b = Rotation.from_euler('x', 8., degrees=True).apply(a)
    assert audit.half_edge_shift(a, b) == pytest.approx(.029 * np.sin(np.radians(4.)))
    assert audit.half_edge_shift(a, -a) == pytest.approx(0.)


def test_regions_are_fixed_disjoint_subsets_of_original_annulus():
    yy, xx = np.mgrid[:120, :120]
    projected = np.stack((xx, yy), axis=-1)
    available = np.ones((120, 120), bool)
    available[30:80, 30:80] = False
    patches = audit.regions(projected, available, [40, 40, 20, 20])
    assert np.array_equal(patches.pop('original_ring'), available)
    counts = np.sum(list(patches.values()), axis=0)
    assert counts.max() <= 1
    assert all(not np.any(patch & ~available) for patch in patches.values())


def test_missing_plane_is_reported_not_created():
    with pytest.raises(ValueError):
        audit.compare_planes(np.zeros((99, 3)))


def test_no_control_interfaces_and_existing_evidence_refused(tmp_path):
    calls = {n.func.attr for n in ast.walk(ast.parse(Path(audit.__file__).read_text()))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {'ConnectPort', 'create_publisher', 'create_client', 'send_goal_async', 'EnableArm'}
    with pytest.raises(FileExistsError):
        audit.audit(tmp_path / 'not_read', tmp_path)
