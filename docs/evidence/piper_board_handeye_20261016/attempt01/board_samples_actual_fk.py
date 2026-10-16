"""Offline actual-FK enrichment; preserve raw samples and do not fit hand-eye."""
import hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
REPO=Path('/mnt/hgfs/ub');sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import load_installed_model,base_tool_fk
from collect_calibration_sdk import summarize
ROOT=Path('/home/johnwick/brain_robot_logs/board_handeye_20261016.2dE1Aj')
e=json.loads((ROOT/'execution.json').read_text());urdf,_=load_installed_model();model=ET.fromstring(urdf)
assert hashlib.sha256(urdf.encode()).hexdigest()==e['model_SHA256']
samples=[]
for sample in e['samples']:
    rows=[]
    for row in sample['frames']:
        q=row['actual_feedback']['q'];t=base_tool_fk(model,q)
        rows.append({'rgb_index':row['index'],'rgb_source_stamp_ns':row['rgb_source_stamp_ns'],
            'feedback_source_stamp_ns':str(row['actual_feedback']['stamp_ns']),
            'actual_q_driver_rad':q,'T_base_gripper_base':t,
            'T_color_local_board_candidates':row['pose_candidates']})
    samples.append({'label':sample['label'],'role':sample['role'],'frames':rows})
first=np.asarray(samples[0]['frames'][0]['T_base_gripper_base']);second=np.asarray(samples[1]['frames'][0]['T_base_gripper_base'])
relative=first[:3,:3].T@second[:3,:3];system=np.eye(3)-relative
packet=json.loads((ROOT/'sdk_after_stop.json').read_text());windows=[]
for i in range(len(packet['samples'])):
    for j in range(i+30,len(packet['samples'])+1):
        part=packet['samples'][i:j]
        if all(r['fresh_after_passive_connection'] for r in part):
            quality=summarize(part)
            if quality['static_three_seconds_and_thirty_samples']:windows.append({'indices':[i,j],'quality':quality})
result={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'URDF_SHA256':e['model_SHA256'],
    'samples':samples,'qualified_pose_samples':len(samples),'fit_pose_samples':sum(s['role']=='fit' for s in samples),
    'heldout_pose_samples':sum(s['role']=='heldout' for s in samples),
    'single_relative_tool_rotation_deg':float(np.rad2deg(Rotation.from_matrix(relative).magnitude())),
    'relative_translation_subproblem_rank':int(np.linalg.matrix_rank(system,tol=1e-9)),
    'full_hand_eye_observable':False,'hand_eye_solver_called':False,
    'reason':'Only two measured poses and one rotation axis; 9fit+1heldout protocol incomplete.',
    'final_SDK_full_window_pass':packet['quality']['static_three_seconds_and_thirty_samples'],
    'final_original_static_subwindow':max(windows,key=lambda x:x['indices'][1]-x['indices'][0]) if windows else None}
with (ROOT/'actual_sample_FK.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps({k:result[k] for k in ['qualified_pose_samples','fit_pose_samples','heldout_pose_samples','single_relative_tool_rotation_deg','relative_translation_subproblem_rank','final_SDK_full_window_pass','final_original_static_subwindow']}))
