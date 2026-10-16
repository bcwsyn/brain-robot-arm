"""Offline board9fit+1heldout fit. No ROS initialization, CAN or TF writes.

Convention: G_i=T_base_gripper, C_i=T_colorOptical_board, X=T_gripper_colorOptical.
G_i X C_i = W (fixed board in base). Never use held-out pose to fit X or W.
"""
import hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import cv2,numpy as np,yaml
from scipy.spatial.transform import Rotation

def transform(rot=None,xyz=None):
    t=np.eye(4)
    if rot is not None:t[:3,:3]=rot
    if xyz is not None:t[:3,3]=np.asarray(xyz).reshape(3)
    return t

def mean_pose(ts):
    ts=np.asarray(ts)
    return transform(Rotation.from_matrix(ts[:,:3,:3]).mean().as_matrix(),ts[:,:3,3].mean(axis=0))

def excitation(gs):
    base=np.asarray(gs[0]);rel=[np.linalg.inv(base)@g for g in gs[1:]]
    a=np.vstack([t[:3,:3]-np.eye(3) for t in rel])
    v=np.asarray([Rotation.from_matrix(t[:3,:3]).as_rotvec() for t in rel])
    sv=np.linalg.svd(a,compute_uv=False)
    return {'translation_rank':int(np.linalg.matrix_rank(a,tol=1e-9)),
            'axis_span_rank':int(np.linalg.matrix_rank(v,tol=1e-9)),
            'translation_singular_values':sv.tolist(),
            'translation_condition':float(sv[0]/sv[-1]) if sv[-1]>1e-12 else None}

def solve(gs,cs,method=cv2.CALIB_HAND_EYE_PARK):
    if len(gs)!=len(cs) or len(gs)<3:raise ValueError('At least three matching poses')
    ex=excitation(gs)
    if ex['translation_rank']<3 or ex['axis_span_rank']<2:raise ValueError('Nonparallel rotations required')
    r,t=cv2.calibrateHandEye([g[:3,:3] for g in gs],[g[:3,3] for g in gs],
                            [c[:3,:3] for c in cs],[c[:3,3] for c in cs],method=method)
    x=transform(r,t)
    if not np.isfinite(x).all() or abs(np.linalg.det(r)-1)>1e-6:raise ValueError('Invalid hand-eye solution')
    return x,mean_pose([g@x@c for g,c in zip(gs,cs)])

def compare(a,b):
    return {'translation_m':float(np.linalg.norm(a[:3,3]-b[:3,3])),
            'rotation_deg':float(np.rad2deg(Rotation.from_matrix(a[:3,:3].T@b[:3,:3]).magnitude()))}

def metrics(g,c,x,w,points):
    actual=g@x@c
    p=np.column_stack([points,np.ones(len(points))])
    dist=np.linalg.norm((actual@p.T-w@p.T)[:3],axis=0)
    return {**compare(actual,w),'board_corner_RMS_m':float(np.sqrt(np.mean(dist**2))),
            'board_corner_max_m':float(dist.max()),'T_base_board_from_observation':actual.tolist()}

def synthetic(gs):
    x=transform(Rotation.from_euler('xyz',[12,-25,7],degrees=True).as_matrix(),[-.04,.01,.03])
    w=transform(Rotation.from_euler('xyz',[7,-13,9],degrees=True).as_matrix(),[.3,-.12,.05])
    cs=[np.linalg.inv(g@x)@w for g in gs]
    estimated,board=solve(gs,cs)
    err=compare(estimated,x)
    return {'synthetic_not_hardware':True,'X_error':err,'W_error':compare(board,w),
            'passed':err['translation_m']<1e-7 and err['rotation_deg']<1e-5}

def main(root):
    repo=Path('/mnt/hgfs/ub');sys.path.insert(0,str(repo/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
    from export_calibration_bundle import load_installed_model,base_tool_fk
    e=json.loads((root/'execution.json').read_text())
    if not e.get('completed_9fit_1heldout') or e['error'] is not None:raise ValueError('Incomplete session; no acceptance fit')
    if len(e['samples'])!=10:raise ValueError('Original 9+1 sample count required')
    urdf,task_path=load_installed_model();sha=hashlib.sha256(urdf.encode()).hexdigest()
    assert sha==e['model_SHA256'];model=ET.fromstring(urdf)
    seed=json.loads((root/'session_seed.json').read_text());points=np.asarray(seed['object_points_m'])
    samples=[];gs=[];cs=[]
    for sample in e['samples']:
        pose_frames=[];frame_gs=[];frame_cs=[]
        for row in sample['frames']:
            assert row['fixed_IDs']==seed['fixed_interior_IDs']
            assert hashlib.sha256((root/row['image_path']).read_bytes()).hexdigest()==row['image_SHA256']
            candidates=[p for p in row['pose_candidates'] if p['all_points_positive_depth']]
            if not candidates:raise ValueError('No positive-depth board candidate')
            choice=min(candidates,key=lambda p:p['refined_rms_px'])
            g=np.asarray(base_tool_fk(model,row['actual_feedback']['q']))
            c=np.asarray(choice['T_color_optical_from_local_board'])
            frame_gs.append(g);frame_cs.append(c)
            pose_frames.append({'rgb_index':row['index'],'actual_q_driver_rad':row['actual_feedback']['q'],
                'source_rgb_stamp_ns':row['rgb_source_stamp_ns'],'source_feedback_stamp_ns':str(row['actual_feedback']['stamp_ns']),
                'T_base_gripper':g.tolist(),'T_color_board_selected':c.tolist(),
                'selected_PnP_RMS_px':choice['refined_rms_px'],
                'all_PnP_candidates_preserved_in_raw_sample':True})
        g=mean_pose(frame_gs);c=mean_pose(frame_cs)
        gs.append(g);cs.append(c);samples.append({'label':sample['label'],'role':sample['role'],
            'frames':pose_frames,'T_base_gripper_mean':g.tolist(),'T_color_board_mean':c.tolist()})
    fit=[i for i,s in enumerate(samples) if s['role']=='fit'];held=[i for i,s in enumerate(samples) if s['role']=='heldout']
    assert len(fit)==9 and len(held)==1 and samples[held[0]]['label']=='combined_holdout'
    fgs=[gs[i] for i in fit];fcs=[cs[i] for i in fit]
    synth=synthetic(fgs);assert synth['passed']
    x,w=solve(fgs,fcs);hx,hw=solve(fgs,fcs,cv2.CALIB_HAND_EYE_HORAUD)
    for i,s in enumerate(samples):s['evaluation']=metrics(gs[i],cs[i],x,w,points)
    loo=[]
    for omitted in fit:
        ids=[i for i in fit if i!=omitted]
        xx,ww=solve([gs[i] for i in ids],[cs[i] for i in ids])
        loo.append({'omitted':samples[omitted]['label'],'X_change_from_nine_fit':compare(xx,x),
                    'omitted_pose_error':metrics(gs[omitted],cs[omitted],xx,ww,points)})
    # Explicit old G->camera_link->depthOptical->colorOptical chain; do not
    # compare different optical frames or deploy X directly as camera_link TF.
    task=yaml.safe_load(task_path.read_text());mount=task['piper_camera_mount_tf']['ros__parameters']
    factory=json.loads((root/'current_factory.json').read_text())
    t=factory['camera_link_from_depth_optical']['transform'];tr=t['translation'];q=t['rotation']
    link_D=transform(Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix(),[tr[k] for k in ['x','y','z']])
    old=json.loads((repo/'docs/evidence/piper_calibration_p1_20261015/board_observe/portable/calibration.json').read_text())
    cd=old['depth_to_color'];C_D=transform(np.asarray(cd['R_row_major']).reshape(3,3),cd['t_m'])
    G_link=transform(Rotation.from_euler('xyz',mount['rotation_rpy_rad']).as_matrix(),mount['translation_m'])
    oldX=G_link@link_D@np.linalg.inv(C_D)
    result={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'production_TF_deployed':False,
        'convention':'G_i X C_i = W; X=T_gripperBase_colorOptical, W=T_base_localBoard',
        'official_source':'https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html',
        'opencv_version':cv2.__version__,'model_URDF_SHA256':sha,'fit_count':9,'heldout_count':1,
        'heldout_never_used_for_X_or_W_fit':True,'equal_weight_per_pose_no_pruning':True,
        'PnP_branch_rule':'Lowest refined RMS among positive-depth candidates; alternatives remain in raw frames',
        'synthetic_actual_FK_convention_check':synth,'excitation':excitation(fgs),
        'T_gripperBase_colorOptical_candidate':x.tolist(),'T_base_localBoard_fit':w.tolist(),
        'PARK_vs_HORAUD':compare(x,hx),'T_gripperBase_colorOptical_old_config_chain':oldX.tolist(),
        'candidate_vs_old_config':compare(x,oldX),'samples':samples,'leave_one_fit_pose_out':loo,
        'heldout':samples[held[0]]['evaluation'],
        'heldout_10mm_corner_max_consistency_pass':samples[held[0]]['evaluation']['board_corner_max_m']<=.01,
        'limitations':['Consistency validation, not independent absolute ground truth or successful grasp.',
          'Only this small-angle wrist range; 32mm square scale/operator report and planar board are assumptions.',
          'Factory intrinsics/zero-D/resize remain unchanged; pixel/model bias is not removed by low fit residual.',
          'No deployment approval implied; candidate optical transform requires explicit frame composition.']}
    with (root/'handeye_fit_report.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ['fit_count','heldout_count','synthetic_actual_FK_convention_check','excitation','heldout','heldout_10mm_corner_max_consistency_pass','candidate_vs_old_config']}))

if __name__=='__main__':main(Path(sys.argv[1]))
