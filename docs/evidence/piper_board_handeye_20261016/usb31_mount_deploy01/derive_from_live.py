"""Compose approved COLOR hand-eye X with actual live camera-internal TF.

Read-only derivation. Historical raw D/C convention is not silently equated
with TF direction; no production files are changed here.
"""
import hashlib,json,sys
from pathlib import Path
import numpy as np,yaml
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent
DATA=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/usb31_sampling01')
sys.path.insert(0,str(DATA/'full_ROI'))
from board_handeye_fit import transform,compare,mean_pose,metrics
fit=json.loads((DATA/'full_ROI/handeye_fit_report.json').read_text())
old_proposal=json.loads((DATA/'full_ROI/candidate_review.json').read_text())
raw=json.loads((ROOT/'internal_tf_actual.json').read_text())
def tf(key):
    v=raw['transforms'][key]['transform'];q=v['rotation'];p=v['translation']
    return transform(Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix(),[p[k] for k in ['x','y','z']])
LC=tf('camera_link<-camera_color_optical_frame');LD=tf('camera_link<-camera_depth_optical_frame')
CD=tf('camera_color_optical_frame<-camera_depth_optical_frame')
X=np.asarray(fit['T_gripperBase_colorOptical_candidate']);proposed=X@np.linalg.inv(LC)
mount=old_proposal['before_mount_config']
oldG=transform(Rotation.from_euler('xyz',mount['rotation_rpy_rad']).as_matrix(),mount['translation_m'])
oldActualX=oldG@LC
oldWrongG=np.asarray(old_proposal['T_gripperBase_cameraLink_proposal'])
samples=fit['samples'];gs=[np.asarray(s['T_base_gripper_mean']) for s in samples];cs=[np.asarray(s['T_color_board_mean']) for s in samples]
train=[i for i,s in enumerate(samples) if s['role']=='fit'];held=[i for i,s in enumerate(samples) if s['role']=='heldout'][0]
W=mean_pose([gs[i]@oldActualX@cs[i] for i in train])
points=np.asarray(json.loads((DATA/'full_ROI/session_seed.json').read_text())['object_points_m'])
detector_path=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml')
d=yaml.safe_load(detector_path.read_text())['cube_detector']['ros__parameters']
configuredCD=transform(np.asarray(d['depth_to_color_rotation']).reshape(3,3),d['depth_to_color_translation_m'])
result={'read_only_derivation':True,'operator_approval':'确认; adopt hand-eye candidate and static verification only',
 'approved_T_gripperBase_colorOptical_unchanged':X.tolist(),
 'formula':'T_gripperBase_cameraLink = approved_X_G_C * inverse(ACTUAL_T_cameraLink_colorOptical)',
 'live_T_cameraLink_colorOptical':LC.tolist(),'live_T_cameraLink_depthOptical':LD.tolist(),
 'live_T_colorOptical_depthOptical':CD.tolist(),'deploy_T_gripperBase_cameraLink':proposed.tolist(),
 'deploy_mount_values':{'translation_m':proposed[:3,3].tolist(),'rotation_rpy_rad':Rotation.from_matrix(proposed[:3,:3]).as_euler('xyz').tolist()},
 'roundtrip_error_to_approved_X':compare(proposed@LC,X),
 'historical_proposal_applied_to_actual_chain_would_error':compare(oldWrongG@LC,X),
 'historical_proposal_NOT_deployed':True,
 'old_configuration_actual_T_gripperBase_colorOptical':oldActualX.tolist(),
 'approved_X_vs_old_ACTUAL_chain':compare(X,oldActualX),
 'old_ACTUAL_chain_independent_heldout':metrics(gs[held],cs[held],oldActualX,W,points),
 'new_approved_independent_heldout_unchanged':fit['heldout'],
 'detector_registration_vs_actual_TF':{'difference':compare(configuredCD,CD),
     'configured_D_to_C':configuredCD.tolist(),'detector_SHA256':hashlib.sha256(detector_path.read_bytes()).hexdigest(),
     'detector_changed':False,'physical_direction_correctness_not_inferred_from_this_inconsistency':True},
 'production_changed':False}
assert result['roundtrip_error_to_approved_X']['translation_m']<1e-12
with (ROOT/'live_composition_review.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps({k:result[k] for k in ['deploy_mount_values','roundtrip_error_to_approved_X','historical_proposal_applied_to_actual_chain_would_error','approved_X_vs_old_ACTUAL_chain','old_ACTUAL_chain_independent_heldout','detector_registration_vs_actual_TF']}))
