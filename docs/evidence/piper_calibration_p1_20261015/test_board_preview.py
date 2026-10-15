"""Synthetic diagnostic regression only, not evidence of real board accuracy."""
import numpy as np
import pytest
from review_board_preview import grid_residual

def points():return np.mgrid[0:3,0:3].T.reshape(-1,2)*30.+[20.,20.]

def test_ideal_local_lattice_has_zero_error_but_never_claims_calibration():
    r=grid_residual(points())
    assert r['rms_px']<1e-8 and not r['formal_pose_estimation_performed']

def test_wrong_occluded_corner_increases_error_without_relabeling_it():
    p=points();p[-1]+=[11.,-5.]
    r=grid_residual(p)
    assert r['rms_px']>1 and not r['formal_pose_estimation_performed']

@pytest.mark.parametrize('bad',[np.zeros((8,2)),np.zeros((9,3)),np.full((9,2),np.nan),np.full((9,2),np.inf)])
def test_invalid_candidates_are_not_silently_repaired(bad):
    with pytest.raises(ValueError):grid_residual(bad)
