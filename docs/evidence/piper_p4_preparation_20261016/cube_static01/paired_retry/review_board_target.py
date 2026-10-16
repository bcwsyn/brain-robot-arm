"""Offline independent board-plane witness, not a production target replacement."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'))
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from board_pose_offline import grid,poses
from review_depth_registration import calibration,color_mask,project_measured,read_config
factory=json.loads((ROOT/'factory.json').read_text())['get_camera_params']
params=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
K=np.array([[params['color_fx'],0,params['color_cx']],[0,params['color_fy'],params['color_cy']],[0,0,1.]])
K=np.diag([319/639,239/479,1])@K
obs=json.loads((ROOT/'target_observation.json').read_text())
world={w['stamp_ns']:w for w in obs['world_points']}
rows=[]
def matrix(t):
    q,p=t['transform']['rotation'],t['transform']['translation'];M=np.eye(4)
    M[:3,:3]=Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix();M[:3,3]=[p[k] for k in ['x','y','z']];return M
for line in (ROOT/'capture/observer.jsonl').read_text().splitlines():
    row=json.loads(line);rgb=cv2.imread(row['images']['rgb']['path']);gray=cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY)
    mask,contour=color_mask(rgb,params);mom=cv2.moments(contour)
    u,v=mom['m10']/mom['m00'],mom['m01']/mom['m00'];ray=np.linalg.solve(K,[u,v,1.])
    ok,corners,meta=cv2.findChessboardCornersSBWithMeta(gray,(3,3),flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_LARGER)
    if not ok:raise RuntimeError('No metric grid in actual image')
    c,r=meta.shape[1],meta.shape[0];points=corners.reshape(-1,2)
    exclusion=cv2.dilate(mask,np.ones((17,17),np.uint8))
    ids=[y*c+x for y in range(1,r-1) for x in range(1,c-1)
         if meta[y,x]>0 and 0<=points[y*c+x][0]<320 and 0<=points[y*c+x][1]<240
         and exclusion[int(points[y*c+x][1]),int(points[y*c+x][0])]==0]
    candidates=poses(grid((c,r))[ids],points[ids],K,np.zeros(5))
    best=min([p for p in candidates if p['all_points_positive_depth']],key=lambda p:p['refined_rms_px'])
    CB=np.array(best['T_color_optical_from_local_board']);n=CB[:3,2];origin=CB[:3,3]
    if n@origin>0:n=-n
    w=world[int(row['stamps_ns']['rgb'])]
    BD=matrix(w['base_from_depth']);CD=matrix(w['color_from_depth']);BC=BD@np.linalg.inv(CD)
    surface=np.array(w['point_color_m']);height=float(n@(surface-origin))
    hypotheses=[]
    for h in [0,.0145,.029]:
        z=(h+n@origin)/(n@ray);p=ray*z;b=(BC@np.r_[p,1])[:3]
        hypotheses.append({'height_above_board_m':h,'color_point_m':p.tolist(),'base_point_m':b.tolist(),
            'hypothesis_not_measured_cube_center':True})
    depth=cv2.imread(row['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
    kd=np.array(row['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
    uv,pix,valid=project_measured(depth,kd,calibration(params),(320,240),params)
    yy,xx=np.where(valid);chosen=np.zeros(depth.shape,bool);chosen[yy,xx]=mask[pix[yy,xx,1],pix[yy,xx,0]]>0
    y,x=np.where(chosen);z=depth[chosen]*.001
    xyz=np.stack([(x-kd[0,2])*z/kd[0,0],(y-kd[1,2])*z/kd[1,1],z],axis=-1)
    cam=calibration(params);color=xyz@cam['r'].T+cam['t']
    heights=(color-origin)@n
    rows.append({'snapshot':row['snapshot'],'source_stamps_ns':row['stamps_ns'],'nominal_grid_m':.032,
        'local_origin_is_arbitrary_no_cross_frame_ID_claim':True,'grid_shape':[c,r],
        'retained_real_corner_ids':ids,'retained_corners_px':points[ids].tolist(),'all_PnP_candidates':candidates,
        'selected_board_RMS_px':best['refined_rms_px'],'board_normal_color_toward_camera':n.tolist(),
        'board_normal_base':(BC[:3,:3]@n).tolist(),'board_origin_base_m':(BC@np.r_[origin,1])[:3].tolist(),
        'detector_aim_height_above_board_m':height,'detector_point_base_m':w['point_base_m'],
        'native_projected_samples':len(heights),'native_height_quantiles_m':np.quantile(heights,[.05,.5,.95]).tolist(),
        'native_samples_above_15mm':int((heights>.015).sum()),
        'RGB_mask_centroid_px':[u,v],'plane_height_hypotheses':hypotheses})
    if row['snapshot']==1:
        plot=rgb.copy()
        for i in ids:cv2.circle(plot,tuple(np.round(points[i]).astype(int)),2,(0,255,0),-1)
        cv2.circle(plot,(round(u),round(v)),2,(0,0,255),-1)
        assert cv2.imwrite(str(ROOT/'board_corner_witness.png'),plot)
report={'offline_only':True,'motion_commands_sent':False,'production_changed':False,
    'reference':'Independent per-image board plane from actual 32mm grid; original baseline zero-D/endpoint K and unchanged hand-eye X.',
    'assumptions':['Nominal 32mm planar board, not externally surveyed.','29mm cube edge is operator nominal, not caliper proof.',
        'Whole RGB silhouette centroid ray need not pass through the exact cube center. Height hypotheses are NOT an adopted control target.'],
    'frames':rows,'new_handeye_fit':False,'replacement_target_deployed':False}
with (ROOT/'board_target_review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps([{k:r[k] for k in ['snapshot','selected_board_RMS_px','detector_aim_height_above_board_m','native_height_quantiles_m','native_samples_above_15mm','plane_height_hypotheses']} for r in rows],indent=2))
