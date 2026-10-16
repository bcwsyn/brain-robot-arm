"""Fixed local IDs across the five STATIC captures; offline hypothesis only."""
import json,sys
from pathlib import Path
import cv2,numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'))
from board_pose_offline import grid,poses
from partial_board_tracking_check import propagate
review=json.loads((ROOT/'board_target_review.json').read_text())
rows=[json.loads(l) for l in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
images=[cv2.imread(r['images']['rgb']['path']) for r in rows]
gray=[cv2.cvtColor(im,cv2.COLOR_BGR2GRAY) for im in images]
# Seed choice is explicit diagnostic selection, NOT an independent validation set.
seed=min(range(5),key=lambda i:review['frames'][i]['selected_board_RMS_px'])
s=review['frames'][seed];ids=s['retained_real_corner_ids'];obj=grid(tuple(s['grid_shape']))[ids]
tracked={seed:np.array(s['retained_corners_px'],np.float32)};flow=[]
for direction in [-1,1]:
    previous=seed
    for current in range(seed+direction,5 if direction==1 else -1,direction):
        tracks=propagate(gray[previous],gray[current],tracked[previous]);maxfb=max(t['forward_backward_error_px'] for t in tracks)
        assert all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks)
        assert maxfb<=.5
        tracked[current]=np.array([t['position_px'] for t in tracks],np.float32)
        flow.append({'from_snapshot':previous+1,'to_snapshot':current+1,'max_FB_px':maxfb})
        previous=current
cal=json.loads((REPO/'docs/evidence/piper_calibration_p1_20261015/board_observe/portable/calibration.json').read_text())
K=np.diag([*cal['color_capture']['existing_detector_resize_factors'],1.])@np.asarray(cal['color_factory']['K']).reshape(3,3)
D=np.array(cal['color_factory']['CameraInfo_D'])
obs=json.loads((ROOT/'target_observation.json').read_text());world={w['stamp_ns']:w for w in obs['world_points']}
def mat(t):
    p,q=t['transform']['translation'],t['transform']['rotation'];m=np.eye(4)
    m[:3,:3]=Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix();m[:3,3]=[p[k] for k in ['x','y','z']];return m
result=[]
for i,row in enumerate(rows):
    candidates=poses(obj,tracked[i],K,D);best=min((c for c in candidates if c['all_points_positive_depth']),key=lambda c:c['refined_rms_px'])
    CB=np.array(best['T_color_optical_from_local_board']);n=CB[:3,2];origin=CB[:3,3]
    if n@origin>0:n=-n
    w=world[int(row['stamps_ns']['rgb'])];BC=mat(w['base_from_depth'])@np.linalg.inv(mat(w['color_from_depth']))
    u,v=review['frames'][i]['RGB_mask_centroid_px'];ray=np.linalg.solve(K,[u,v,1.])
    ps=[]
    for h in [0,.0145,.029]:
        p=ray*(h+n@origin)/(n@ray);b=(BC@np.r_[p,1])[:3]
        ps.append({'height_m':h,'base_m':b.tolist(),'color_m':p.tolist()})
    result.append({'snapshot':i+1,'fixed_ids':ids,'corners_px':tracked[i].tolist(),
        'all_PnP_candidates':candidates,'rms_px':best['refined_rms_px'],
        'normal_base':(BC[:3,:3]@n).tolist(),'T_base_board':(BC@CB).tolist(),
        'detector_aim_height_m':float(n@(np.array(w['point_color_m'])-origin)),
        'nominal_height_ray_intersections':ps})
middle=np.array([r['nominal_height_ray_intersections'][1]['base_m'] for r in result])
report={'offline_only':True,'production_changed':False,'controller_target_replaced':False,
    'seed_snapshot':seed+1,'seed_selection':'Lowest local reprojection residual in this same static batch; not independent evidence of physical plane accuracy.',
    'local_fixed_IDs_only_not_prior_handeye_IDs':True,'flow':flow,'frames':result,
    'nominal_14_5mm_center_ray_base_median_m':np.median(middle,axis=0).tolist(),
    'nominal_center_ray_peak_to_peak_m':np.ptp(middle,axis=0).tolist(),
    'not_measured_cube_center':True,'not_approved_control_target':True,
    'limitations':['Printed board scale/flatness and original K assumptions remain.',
      'Detected whole-cube silhouette centroid does not independently establish physical cube-center ray.',
      'Temporal repeatability cannot validate absolute height or TCP.',
      'Unfixed per-frame grid fits disagreed; original diagnostic is retained, not silently overwritten.']}
with (ROOT/'fixed_board_plane_review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'seed':seed+1,'maxFB':max(r['max_FB_px'] for r in flow),
    'RMS':[r['rms_px'] for r in result],'detector_heights':[r['detector_aim_height_m'] for r in result],
    'nominal_center_median':report['nominal_14_5mm_center_ray_base_median_m'],
    'nominal_center_spread':report['nominal_center_ray_peak_to_peak_m']},indent=2))
