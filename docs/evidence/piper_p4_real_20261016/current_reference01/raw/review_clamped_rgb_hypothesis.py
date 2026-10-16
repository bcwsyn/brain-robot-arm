"""Read-only RGB square-face hypothesis from operator-confirmed clamped pair02.
ANNOTATED rounded image corners +/-2px are hypotheses, not metrology.
No heldout07, robot FK, depth filling, motion target or production change.
"""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'))
from board_pose_offline import poses
K=np.array([[488.808654785*319/639,0,315.50680542*319/639],
            [0,488.808654785*239/479,214.381820679*239/479],[0,0,1.]])
source=REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair02/attempt02/grip_capture/portable/grip_candidate_rgbd/evidence/0001_rgb.png'
image=cv2.imread(str(source))
image_points=np.array([[138,162],[200,162],[210,187],[131,187]],float)
s=.029/2
object_points=np.array([[-s,-s,0],[s,-s,0],[s,s,0],[-s,s,0]])
X=np.array(json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
def evaluate(pixels):
    out=[]
    for p in poses(object_points,pixels,K,np.zeros(5)):
        T=np.array(p['T_color_optical_from_local_board'])
        n=T[:3,2]
        if n@T[:3,3]>0:n=-n
        center=T[:3,3]-n*s
        uv=K@center;uv=uv[:2]/uv[2]
        p.update(face_center_color_m=T[:3,3].tolist(),outward_normal_color=n.tolist(),
            cube_center_color_candidate_m=center.tolist(),candidate_center_pixel=uv.tolist(),
            local_tool_candidate_m=(X@np.r_[center,1.])[:3].tolist())
        out.append(p)
    return out
candidates=evaluate(image_points)
rng=np.random.default_rng(23);sensitivity=[]
for i in range(100):
    candidates_noisy=evaluate(image_points+rng.uniform(-2,2,(4,2)))
    sensitivity.extend({'trial':i,'branch':j,'center_color_m':c['cube_center_color_candidate_m'],
        'rms_px':c['refined_rms_px']} for j,c in enumerate(candidates_noisy))
canvas=cv2.resize(image,(640,480),interpolation=cv2.INTER_NEAREST)
cv2.polylines(canvas,[np.rint(image_points*2).astype(int)],True,(0,255,255),2)
for i,(u,v) in enumerate(image_points):
    cv2.putText(canvas,str(i),tuple(np.rint([u*2+4,v*2-4]).astype(int)),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
for i,c in enumerate(candidates):
    color=(0,255,0) if i==0 else (0,165,255)
    cv2.drawMarker(canvas,tuple(np.rint(np.array(c['candidate_center_pixel'])*2).astype(int)),color,cv2.MARKER_CROSS,16,2)
cv2.putText(canvas,'ANNOTATED face / both PnP branches / NOT TCP',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.47,(255,255,255),1)
out=ROOT/'geometry_review';assert cv2.imwrite(str(out/'clamped02_annotated_square_hypothesis.png'),canvas)
report={'read_only':True,'reference_pair':'new_pair02','heldout_used':False,
 'uses_robot_FK_for_RGB_center':False,'image_source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'nominal_edge_m':.029,'image_points_ANNOTATED_not_exact_CAD_or_caliper':image_points.tolist(),
 'corner_uncertainty_test_uniform_plus_minus_px':2,'camera_K':K.tolist(),
 'all_branches':candidates,'sensitivity_trials':sensitivity,'not_deployed_or_exported_as_motion_target':True,
 'official_reference_url':'https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html',
 'limitations':['Rounded/blurred top-face corners are approximate image annotations.',
 'Both planar branches retained; low pixel error does not certify actual TCP/metric accuracy.',
 'Old/current camera installation identity and physical contact depth are not independently measured.',
 'This independent image-only candidate does not authorize production TF/TCP or actual motion.']}
with (out/'clamped_rgb_hypothesis_v2.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'branches':[{'rms_px':c['refined_rms_px'],'center_color':c['cube_center_color_candidate_m'],
 'pixel':c['candidate_center_pixel'],'local_tool_candidate':c['local_tool_candidate_m']} for c in candidates],
 'sensitivity_center_ptp_mm':(np.ptp([r['center_color_m'] for r in sensitivity],axis=0)*1000).tolist()}))
