"""Nominal joint-limit/FK sampling candidates; no ROS initialization or motion."""
import hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np,yaml
from scipy.spatial.transform import Rotation
REPO=Path('/mnt/hgfs/ub');TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import load_installed_model,base_tool_fk
BOARD=REPO/'docs/evidence/piper_calibration_p1_20261015/board_observe'
row=json.loads((BOARD/'portable/capture/observer.jsonl').read_text().splitlines()[0])
q=np.asarray(row['q_rad']);urdf,path=load_installed_model();root=ET.fromstring(urdf)
baseline=json.loads((BOARD/'portable/depth_review.json').read_text())
assert hashlib.sha256(urdf.encode()).hexdigest()==baseline['urdf_sha256']
params=yaml.safe_load(path.read_text())['grasp_lift_executor']['ros__parameters']
lo=np.asarray(params['real_trajectory_joint_min']);hi=np.asarray(params['real_trajectory_joint_max'])
t0=np.asarray(base_tool_fk(root,q));assert np.max(np.abs(t0-baseline['frames'][0]['T_base_tool']))<1e-12
offsets=[('start',0,0,0),('J4_plus',6,0,0),('J4_minus',-6,0,0),
 ('J6_plus',0,0,8),('J6_minus',0,0,-8),('J5_minus',0,-4,0),
 ('J4plus_J5minus',6,-4,0),('J4minus_J5minus',-6,-4,0),
 ('J5minus_J6plus',0,-8,8),('combined_holdout',4,-6,-6)]
samples=[];vectors=[];systems=[]
for name,j4,j5,j6 in offsets:
    delta=np.deg2rad([0,0,0,j4,j5,j6]);candidate=q+delta
    inside=bool(((candidate>=lo)&(candidate<=hi)).all())
    t=np.asarray(base_tool_fk(root,candidate));relative=t0[:3,:3].T@t[:3,:3]
    vector=Rotation.from_matrix(relative).as_rotvec()
    if name!='combined_holdout' and np.linalg.norm(vector)>1e-8:
        vectors.append(vector);systems.append(np.eye(3)-relative)
    samples.append({'id':name,'role':'nominal_pose_holdout' if name=='combined_holdout' else 'nominal_pose_fit',
        'offset_J4_J5_J6_deg':[j4,j5,j6],'candidate_q_driver_rad':candidate.tolist(),
        'within_original_task_joint_limits':inside,'gripper_base_FK_translation_delta_m':(t[:3,3]-t0[:3,3]).tolist(),
        'gripper_base_FK_rotation_delta_deg':float(np.rad2deg(np.linalg.norm(vector))),
        'rotation_vector_in_start_tool_rad':vector.tolist()})
sv=np.linalg.svd(np.vstack(systems),compute_uv=False);vsv=np.linalg.svd(np.asarray(vectors),compute_uv=False)
assert all(s['within_original_task_joint_limits'] for s in samples)
print(json.dumps({'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
    'source_actual_q_is_historical_not_current':True,'historical_source_stamps_ns':row['stamps_ns'],
    'same_actual_model_SHA256':hashlib.sha256(urdf.encode()).hexdigest(),'same_archived_start_FK_reproduced':True,
    'original_joint_min_rad':lo.tolist(),'original_joint_max_rad':hi.tolist(),
    'do_not_apply_candidate_q_until_fresh_start_and_original_planning_checks':True,
    'proposed_sequence':'start -> candidate -> start for every non-start candidate; board fixed, gripper unchanged',
    'continuous_RGB_ID_tracking_needed_between_stopped_pose_samples':True,
    'non_start_pose_limit_and_FK_candidates':samples,'relative_rotation_axis_span_singular_values':vsv.tolist(),
    'relative_translation_linear_system_singular_values':sv.tolist(),
    'nominal_holdout_excluded_from_excitation_check':True,
    'relative_translation_linear_system_rank':int(np.linalg.matrix_rank(np.vstack(systems))),
    'relative_translation_linear_system_condition':float(sv[0]/sv[-1]),
    'view_visibility_self_collision_table_clearance_and_path_feasibility_checked':False,
    'candidate_model_variation_is_NOT_actual_arm_test_or_full_calibration_identifiability':True,
    'original_cube_5plus1_protocol_replaced':False,'new_board_motion_or_route_approved':False},indent=2))
