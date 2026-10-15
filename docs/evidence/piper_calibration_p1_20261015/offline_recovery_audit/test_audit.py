"""Synthetic-only regression for the offline audit, not calibration evidence."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from audit_existing_pairs import translation_excitation,two_face_check
from plan_next_preview import common_field

def poses(angles):
    result=[]
    for angle in angles:
        t=np.eye(4);t[:3,:3]=Rotation.from_euler('xyz',angle,degrees=True).as_matrix()
        result.append(t)
    return result

def test_fixed_orientation_cannot_separate_mount_and_tool_translation():
    identity=[np.eye(4)]*5
    assert translation_excitation(identity,identity)['rank']==3

def test_yaw_only_has_vertical_translation_gauge():
    grip=poses([[0,0,z] for z in [0,40,80,120,160]])
    result=translation_excitation([np.eye(4)]*5,grip)
    assert result['rank']==5 and result['condition_number'] is None
    assert not result['full_hand_eye_identifiability_proven']

def test_diverse_realistic_rotations_pass_necessary_translation_condition_only():
    grip=poses([[0,0,0],[15,-10,40],[-20,15,80],[10,20,120],[-15,-20,170]])
    result=translation_excitation([np.eye(4)]*5,grip)
    assert result['rank']==6 and result['condition_number']>1
    assert result['optimistic_known_mount_rotation_only']
    assert not result['full_hand_eye_identifiability_proven']

def test_invalid_or_unmatched_poses_are_not_silently_fixed():
    with pytest.raises(ValueError):translation_excitation([],[])
    with pytest.raises(ValueError):translation_excitation([np.eye(4)],[])
    bad=np.eye(4);bad[0,0]=-1
    with pytest.raises(ValueError):translation_excitation([bad],[np.eye(4)])

def top_cloud():
    x,y=np.meshgrid(np.linspace(-.0145,.0145,33),np.linspace(-.0145,.0145,33))
    return np.c_[x.ravel()+.05,y.ravel(),np.full(x.size,.30)]

def test_single_plane_does_not_invent_second_face():
    result,_=two_face_check(top_cloud())
    assert result['secondary'] is None and result['secondary_error']
    assert result['remaining_native_samples']==0
    assert not result['calibration_input_approved']

def test_two_known_synthetic_faces_are_corroboration_not_deployment_approval():
    y,z=np.meshgrid(np.linspace(-.0145,.0145,23),np.linspace(.30,.329,23))
    side=np.c_[np.full(y.size,.0355),y.ravel(),z.ravel()]
    result,_=two_face_check(np.vstack([top_cloud(),side]))
    assert result['secondary'] is not None
    assert result['plane_angle_deg']>85
    assert result['two_independent_face_center_difference_m']<.004
    assert not result['calibration_input_approved']

def test_common_fov_identity_and_baseline_intersection():
    k=np.array([[100.,0,2.],[0,100.,2.],[0,0,1.]])
    c={'k':k,'r':np.eye(3),'t':np.zeros(3),'size':(5,5),'mirror':False}
    assert common_field(c,k,(5,5),(5,5),[1.,2.]).all()
    c['t']=np.array([.01,0,0])
    m=common_field(c,k,(5,5),(5,5),[1.,2.])
    assert not m[:,0].any() and m[:,1:].all()

def test_common_fov_is_geometry_not_a_missing_depth_fill():
    k=np.eye(3);c={'k':k,'r':k,'t':np.zeros(3),'size':(5,5),'mirror':False}
    with pytest.raises(ValueError):common_field(c,k,(5,5),(5,5),[0.])
    with pytest.raises(ValueError):common_field(c,k,(5,5),(5,5),[])
