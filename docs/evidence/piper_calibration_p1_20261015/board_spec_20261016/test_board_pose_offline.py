import cv2
import numpy as np
import pytest
from board_pose_offline import grid,poses

K=np.array([[244.,0,157.],[0,244.,107.],[0,0,1.]])
RVEC=np.array([.25,-.18,.12]);TVEC=np.array([-.12,-.08,.65])

@pytest.mark.parametrize('distortion',[np.zeros(5),np.array([.07,-.09,.0003,-.0001,0.])])
def test_known_metric_pose(distortion):
    obj=grid();image,_=cv2.projectPoints(obj,RVEC,TVEC,K,distortion)
    solutions=poses(obj,image.reshape(-1,2),K,distortion)
    best=min(solutions,key=lambda p:p['refined_rms_px'])
    assert len(solutions)==2 and best['all_points_positive_depth']
    assert best['refined_rms_px']<1e-5
    matrix=np.asarray(best['T_color_optical_from_local_board'])
    assert np.linalg.norm(matrix[:3,3]-TVEC)<1e-6
    assert np.linalg.norm(matrix[:3,:3]-cv2.Rodrigues(RVEC)[0])<1e-6

def test_arbitrary_fixed_origin_is_valid():
    obj=grid();offset=np.array([.032,.064,0.]);image,_=cv2.projectPoints(obj,RVEC,TVEC,K,None)
    best=min(poses(obj-offset,image.reshape(-1,2),K,np.zeros(5)),key=lambda p:p['refined_rms_px'])
    matrix=np.asarray(best['T_color_optical_from_local_board']);rot=cv2.Rodrigues(RVEC)[0]
    assert np.linalg.norm(matrix[:3,3]-(TVEC+rot@offset))<1e-6

@pytest.mark.parametrize('obj,img',[(np.zeros((3,3)),np.zeros((3,2))),
    (np.zeros((5,3)),np.zeros((4,2))),(np.full((4,3),np.nan),np.zeros((4,2))),
    (np.zeros((4,3)),np.zeros((4,2)))])
def test_invalid_geometry_rejected(obj,img):
    with pytest.raises(ValueError):poses(obj,img,K,np.zeros(5))
