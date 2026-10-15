import importlib.util
from pathlib import Path
import cv2
import numpy as np
import pytest
spec=importlib.util.spec_from_file_location('board_review',Path(__file__).with_name('review_board_observation.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def projected_grid(shape):
    c,r=shape;grid=np.mgrid[0:c,0:r].T.reshape(-1,2).astype(np.float64)
    return cv2.perspectiveTransform(grid[None],np.array([[17.,2.,40.],[1.,15.,30.],[.001,.002,1.]]))[0]

def test_rectangular_projective_grid():
    assert mod.fit_grid(projected_grid((7,8)),(7,8))['rms_px']<1e-4

def test_wrong_corner_is_not_hidden():
    p=projected_grid((7,8));p[20]+=[5.,-4.]
    assert mod.fit_grid(p,(7,8))['max_px']>4.

@pytest.mark.parametrize('points,shape',[(np.zeros((9,2)),(2,4)),(np.zeros((8,2)),(3,3)),(np.full((9,2),np.nan),(3,3))])
def test_reject_incomplete_or_invalid(points,shape):
    with pytest.raises(ValueError):mod.fit_grid(points,shape)
