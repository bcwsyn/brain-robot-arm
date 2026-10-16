"""Offline compare fixed base target projections with the same visible cube."""
import hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import cv2,numpy as np,yaml
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import load_installed_model,base_tool_fk
from review_depth_registration import color_mask,read_config
urdf,_=load_installed_model();model=ET.fromstring(urdf)
assert hashlib.sha256(urdf.encode()).hexdigest()=='0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82'
X=np.array(json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
params=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
K=np.diag([319/639,239/479,1.])@np.array([[params['color_fx'],0,params['color_cx']],
 [0,params['color_fy'],params['color_cy']],[0,0,1.]])
target=np.r_[yaml.safe_load((ROOT/'frozen_target.yaml').read_text())['surface_base_m'],1.]
def project(p):return (K@p[:3]/p[2])[:2]
rows=[]
for line in (ROOT/'real_record/samples.jsonl').read_text().splitlines():
    r=json.loads(line);image=cv2.imread(r['images']['rgb']['path'])
    try:mask,contour=color_mask(image,params)
    except (ValueError,TypeError):continue
    if contour is None:continue
    mom=cv2.moments(contour)
    if mom['m00']<=0:continue
    raw=r['feedback_nearest_received'].get('joint_states_feedback')
    if raw is None:continue
    m=raw['message'];q=[m['position'][m['name'].index(f'joint{i}')] for i in range(1,7)]
    G=np.array(base_tool_fk(model,q));camera=np.linalg.inv(G@X)@target
    predicted=project(camera);actual=np.array([mom['m10']/mom['m00'],mom['m01']/mom['m00']])
    feedback_ns=m['header']['stamp']['sec']*10**9+m['header']['stamp']['nanosec']
    rows.append({'image':r['images']['rgb']['path'],'RGB_stamp_ns':r['RGB_stamp_ns'],'stage':r['stage'],
      'q_rad':q,'feedback_minus_RGB_s':(feedback_ns-r['RGB_stamp_ns'])/1e9,
      'observed_cube_centroid_px':actual.tolist(),'frozen_top_ray_projected_px':predicted.tolist(),
      'pixel_residual_norm':float(np.linalg.norm(actual-predicted)),
      'projected_target_depth_m':float(camera[2]),'no_target_update_or_control':True})
nominal_tip=np.linalg.inv(X)@np.array([0,0,.1358,1])
summary={}
for stage in sorted({r['stage'] for r in rows}):
    subset=[r for r in rows if r['stage']==stage]
    summary[stage]={'frames':len(subset),'residual_range_px':[min(r['pixel_residual_norm'] for r in subset),max(r['pixel_residual_norm'] for r in subset)],
      'last_actual_centroid':subset[-1]['observed_cube_centroid_px'],'last_prediction':subset[-1]['frozen_top_ray_projected_px']}
report={'offline_only':True,'physical_grasp_succeeded':False,'real_entry_exit_zero_is_NOT_object_retention':True,
 'basis':'same frozen top-ray point, approved color X, original FK/K, nearest RECEIVED actual q, no latest TF fabrication',
 'nominal_tip_model_point_color_m':nominal_tip[:3].tolist(),'nominal_tip_model_projection_px':project(nominal_tip).tolist(),
 'stage_summary':summary,'frames':rows,'limitations':[
 'RGB silhouette centroid is not necessarily the same top-face physical point as viewpoint changes.',
 'Nearest feedback stamp is reported, not hardware synchronized. Stationary HOLDING isolates motion-time skew.',
 'Projection mismatch alone does not uniquely separate TCP, hand-eye extrapolation, FK/model, or surface-ray bias.',
 'No production transform, TCP, thresholds, target, or motion changed by this review.']}
with (ROOT/'actual_landing_review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'stage_summary':summary,'nominal_tip_projection_px':report['nominal_tip_model_projection_px']}))
