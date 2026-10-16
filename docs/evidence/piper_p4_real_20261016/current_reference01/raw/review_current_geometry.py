"""Current original images, native depth/face center and frozen X; no controls."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from estimate_calibration_cube_center import frame_hypotheses,preview
from review_depth_registration import read_config,calibration,color_mask
from export_calibration_bundle import load_installed_model,base_tool_fk
import xml.etree.ElementTree as ET
params=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
cam=calibration(params)
handeye=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json'
X=np.array(json.loads(handeye.read_text())['T_gripperBase_colorOptical_candidate'])
urdf,_=load_installed_model();model=ET.fromstring(urdf)
rows=[json.loads(l) for l in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
manual=json.loads((REPO/'docs/evidence/piper_p4_real_20261016/attempt01/manual_pair_geometry_review.json').read_text())
world={r['stamp_ns']:r for r in json.loads((ROOT/'target_observation.json').read_text())['world_points']}
output=ROOT/'geometry_review';output.mkdir(exist_ok=False)
frames=[]
for row in rows:
    f=frame_hypotheses(row,params,cam,[.029])
    image=cv2.imread(row['images']['rgb']['path'])
    BG=base_tool_fk(model,row['q_rad']);BC=BG@X
    k=np.diag([(image.shape[1]-1)/(cam['size'][0]-1),(image.shape[0]-1)/(cam['size'][1]-1),1.])@cam['k']
    mask,contour=color_mask(image,params)
    canvas=cv2.resize(image,(640,480),interpolation=cv2.INTER_NEAREST)
    f['local_reference_projections']={}
    refs=[('nominal_tip',[0,0,.1358],(255,255,0)),
          ('manual02_candidate',manual['pairs'][0]['implied_tool_center_m_under_NEW_X'],(0,0,255))]
    for i,(name,p,color) in enumerate(refs):
        pc=np.linalg.inv(X)@np.r_[p,1.];uv=k@pc[:3];uv=uv[:2]/uv[2]
        f['local_reference_projections'][name]={'color_m':pc[:3].tolist(),'pixel':uv.tolist()}
        cv2.drawMarker(canvas,tuple(np.rint(uv*2).astype(int)),color,cv2.MARKER_CROSS,14,2)
        cv2.putText(canvas,name,(8,22+22*i),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
    c=f['candidate_by_nominal_edge_mm'].get('29')
    if c:
        f['candidate_center_base_m']=(BC@np.r_[c['cube_center_color_m'],1.])[:3].tolist()
        f['candidate_center_tool_m_CURRENT_NOT_a_clamped_reference']=(X@np.r_[c['cube_center_color_m'],1.])[:3].tolist()
    f['same_stamp_original_detector']=world.get(int(row['stamps_ns']['rgb']))
    f['current_actual_q_rad']=row['q_rad']
    cv2.putText(canvas,'NO CONTROL / candidate projection only',(8,465),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
    assert cv2.imwrite(str(output/f'{row["snapshot"]:04d}_reference_overlay.png'),canvas)
    assert cv2.imwrite(str(output/f'{row["snapshot"]:04d}_face_center.png'),preview(image,f,cam,'29'))
    d=cv2.imread(row['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
    heat=cv2.applyColorMap(np.clip((d.astype(float)-100)/200*255,0,255).astype(np.uint8),cv2.COLORMAP_TURBO)
    heat[d==0]=0
    assert cv2.imwrite(str(output/f'{row["snapshot"]:04d}_native_depth_100_300mm.png'),heat)
    frames.append(f)
good=[r for r in frames if r.get('candidate_center_base_m')]
report={'baseline':'3e65b08','current_capture':str(ROOT/'capture'),'read_only':True,
 'no_TF_TCP_limits_or_control_changed':True,'original_center_estimator_reused':True,
 'target_is_not_in_gripper':True,'gripper_feedback_mm':.4,
 'handeye_source_sha256':hashlib.sha256(handeye.read_bytes()).hexdigest(),
 'model_sha256':hashlib.sha256(urdf.encode()).hexdigest(),'frames':frames,
 'measured_face_center_candidates':len(good),
 'center_base_median_m':np.median([f['candidate_center_base_m'] for f in good],axis=0).tolist() if good else None,
 'limits':['A face-fit center is inferred from nominal29mm geometry, not directly measured interior.',
           'A current cube location is not a new clamped local reference.',
           'Historical local references remain unverified, no motion target exported.']}
with (output/'report.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'frames':len(frames),'coverage':[f['color_pixel_coverage'] for f in frames],
 'candidates':len(good),'center_base_median_m':report['center_base_median_m'],
 'rejections':[f.get('rejected',f['rejected_by_nominal_edge_mm']) for f in frames]}))
