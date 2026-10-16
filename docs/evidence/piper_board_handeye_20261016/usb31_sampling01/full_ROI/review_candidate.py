"""Offline candidate frame composition and old-vs-new fixed-board comparison.

Produce proposal only; never write runtime or canonical production parameters.
"""
import hashlib,json
from pathlib import Path
import numpy as np,yaml
from scipy.spatial.transform import Rotation
from board_handeye_fit import transform,mean_pose,metrics,compare
ROOT=Path(__file__).resolve().parent
fit=json.loads((ROOT/'handeye_fit_report.json').read_text())
X=np.asarray(fit['T_gripperBase_colorOptical_candidate']);oldX=np.asarray(fit['T_gripperBase_colorOptical_old_config_chain'])
samples=fit['samples'];seed=json.loads((ROOT/'session_seed.json').read_text());points=np.asarray(seed['object_points_m'])
gs=[np.asarray(s['T_base_gripper_mean']) for s in samples];cs=[np.asarray(s['T_color_board_mean']) for s in samples]
train=[i for i,s in enumerate(samples) if s['role']=='fit'];test=[i for i,s in enumerate(samples) if s['role']=='heldout']
oldW=mean_pose([gs[i]@oldX@cs[i] for i in train]);newW=np.asarray(fit['T_base_localBoard_fit'])
rows=[{'label':s['label'],'role':s['role'],'old':metrics(g,c,oldX,oldW,points),
       'candidate':metrics(g,c,X,newW,points)} for s,g,c in zip(samples,gs,cs)]
factory=json.loads((ROOT/'current_factory.json').read_text())
t=factory['camera_link_from_depth_optical']['transform'];q=t['rotation'];v=t['translation']
LD=transform(Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix(),[v[k] for k in ['x','y','z']])
cal=json.loads(Path('/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/board_observe/portable/calibration.json').read_text())
d=cal['depth_to_color'];CD=transform(np.asarray(d['R_row_major']).reshape(3,3),d['t_m'])
Glink=X@CD@np.linalg.inv(LD)
recomposed=Glink@LD@np.linalg.inv(CD)
assert np.max(np.abs(recomposed-X))<1e-12
task=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
before=yaml.safe_load(task.read_text())['piper_camera_mount_tf']['ros__parameters']
after={'translation_m':Glink[:3,3].tolist(),'rotation_rpy_rad':Rotation.from_matrix(Glink[:3,:3]).as_euler('xyz').tolist()}
result={'offline_only':True,'production_TF_written':False,'candidate_adopted':False,
 'chain':'X_G_C = T_G_cameraLink * T_cameraLink_D * inverse(T_C_D)',
 'proposal_chain':'T_G_cameraLink = X_G_C_candidate * T_C_D * inverse(T_cameraLink_D)',
 'composition_roundtrip_max_abs':float(np.max(np.abs(recomposed-X))),
 'actual_production_task':str(task),'actual_production_task_SHA256':hashlib.sha256(task.read_bytes()).hexdigest(),
 'before_mount_config':before,'proposal_only_after_mount':after,'T_gripperBase_cameraLink_proposal':Glink.tolist(),
 'all_pose_comparison':rows,'independent_heldout':rows[test[0]],
 'leave_one_fit_pose_out_max_parameter_change':{
     'translation_m':max(r['X_change_from_nine_fit']['translation_m'] for r in fit['leave_one_fit_pose_out']),
     'rotation_deg':max(r['X_change_from_nine_fit']['rotation_deg'] for r in fit['leave_one_fit_pose_out'])},
 'leave_one_fit_pose_out_max_corner_error_m':max(r['omitted_pose_error']['board_corner_max_m'] for r in fit['leave_one_fit_pose_out']),
 'deployment_approval_required':True,'rollback':'Restore exactly the before_mount_config values in the same actual task path; original SHA and full task remain untouched now.',
 'limits':['Comparison fits one independent board pose W for each old/candidate X on the nine fit poses only; heldout never enters fit.',
           'The small-angle sampled range does not establish global absolute accuracy; parameter LOO variation is reported, not hidden.',
           'This is a proposal, not authorization or proof of a grasp.']}
with (ROOT/'candidate_review.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps({'proposal_only_after_mount':after,'heldout_old':rows[test[0]]['old'],
                  'heldout_candidate':rows[test[0]]['candidate'],'parameter_LOO':result['leave_one_fit_pose_out_max_parameter_change']}))
