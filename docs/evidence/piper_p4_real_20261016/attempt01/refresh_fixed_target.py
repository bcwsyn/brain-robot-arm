"""Read-only fresh target using prior real-corner identities, not prior 3D points."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
PRIOR=Path('/home/johnwick/brain_robot_logs/p4_cube_retry_20261016.wyUEQu')
sys.path.insert(0,str(REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'))
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from board_pose_offline import grid,poses
from partial_board_tracking_check import propagate
from review_depth_registration import color_mask,read_config
prior=json.loads((PRIOR/'fixed_board_plane_review.json').read_text())
seed=prior['seed_snapshot']-1
seed_review=json.loads((PRIOR/'board_target_review.json').read_text())['frames'][seed]
oldrows=[json.loads(l) for l in (PRIOR/'capture/observer.jsonl').read_text().splitlines()]
rows=[json.loads(l) for l in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
oldimage=Path(oldrows[seed]['images']['rgb']['path'])
assert hashlib.sha256(oldimage.read_bytes()).hexdigest()==oldrows[seed]['images']['rgb']['sha256']
previous=cv2.cvtColor(cv2.imread(str(oldimage)),cv2.COLOR_BGR2GRAY)
points=np.asarray(seed_review['retained_corners_px'],np.float32)
obj=grid(tuple(seed_review['grid_shape']))[seed_review['retained_real_corner_ids']]
params=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
K=np.diag([319/639,239/479,1.])@np.array([[params['color_fx'],0,params['color_cx']],
 [0,params['color_fy'],params['color_cy']],[0,0,1.]])
world={w['stamp_ns']:w for w in json.loads((ROOT/'target_observation.json').read_text())['world_points']}
def mat(t):
    p,q=t['transform']['translation'],t['transform']['rotation'];m=np.eye(4)
    m[:3,:3]=Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix();m[:3,3]=[p[k] for k in ['x','y','z']];return m
frames=[];flow=[]
for i,row in enumerate(rows):
    image=cv2.imread(row['images']['rgb']['path']);gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    tracks=propagate(previous,gray,points)
    assert all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks)
    assert max(t['forward_backward_error_px'] for t in tracks)<=.5
    new=np.array([t['position_px'] for t in tracks],np.float32)
    flow.append({'from':'prior_static_snapshot3' if i==0 else i,'to_snapshot':i+1,
      'max_FB_px':max(t['forward_backward_error_px'] for t in tracks),
      'max_corner_displacement_px':float(np.linalg.norm(new-points,axis=1).max())})
    candidates=poses(obj,new,K,np.zeros(5))
    best=min((c for c in candidates if c['all_points_positive_depth']),key=lambda c:c['refined_rms_px'])
    CB=np.array(best['T_color_optical_from_local_board']);n=CB[:3,2];origin=CB[:3,3]
    if n@origin>0:n=-n
    w=world[int(row['stamps_ns']['rgb'])];BC=mat(w['base_from_depth'])@np.linalg.inv(mat(w['color_from_depth']))
    mask,contour=color_mask(image,params);mom=cv2.moments(contour)
    u,v=mom['m10']/mom['m00'],mom['m01']/mom['m00'];ray=np.linalg.solve(K,[u,v,1.])
    hypotheses=[]
    for h in [0.,.0145,.029]:
        p=ray*(h+n@origin)/(n@ray)
        hypotheses.append({'height_m':h,'base_m':(BC@np.r_[p,1])[:3].tolist(),'color_m':p.tolist()})
    frames.append({'snapshot':i+1,'source_stamps_ns':row['stamps_ns'],'q_rad':row['q_rad'],
      'fixed_ids':seed_review['retained_real_corner_ids'],'corners_px':new.tolist(),
      'all_PnP_candidates':candidates,'rms_px':best['refined_rms_px'],
      'normal_base':(BC[:3,:3]@n).tolist(),'T_base_board':(BC@CB).tolist(),
      'RGB_mask_centroid_px':[u,v],'nominal_height_ray_intersections':hypotheses})
    if i==0:
        witness=image.copy()
        for p in new:cv2.circle(witness,tuple(np.round(p).astype(int)),2,(0,255,0),-1)
        cv2.imwrite(str(ROOT/'fresh_corner_witness.png'),witness)
    points=new;previous=gray
report={'fresh_five_image_target_review':True,'motion_commands_sent':False,
 'seed_source':str(oldimage),'seed_image_SHA256':hashlib.sha256(oldimage.read_bytes()).hexdigest(),
 'prior_used_for_corner_identity_NOT_old_3D_coordinates':True,
 'flow':flow,'frames':frames,'assumptions':[
 'Repeated checker pattern identity also checked against unchanged full RGB layout; FB alone cannot prove IDs.',
 'Same approved 32mm board, original K/zero-D, 29mm nominal TOP ray, and model TCP assumptions.'],
 'previous_redetection_failure':'SB returned a small local grid with fewer than four retained internal unoccluded points; no target exported from failed analysis.'}
with (ROOT/'fixed_board_plane_review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'RMS_px':[f['rms_px'] for f in frames],'flow':flow,
 'fresh_surface_base_median':np.median([f['nominal_height_ray_intersections'][2]['base_m'] for f in frames],axis=0).tolist()}))
