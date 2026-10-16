"""Offline old clamped RGB vs local reference projection; no control or fitting.

Visible mask centroid is NOT a measured 3D cube center. Assumes current approved
camera mount also held in the old hand-placed sessions; test that assumption.
"""
import hashlib,json
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
e=REPO/'docs/evidence'
manual=e/'piper_p4_real_20261016/attempt01/manual_pair_geometry_review.json'
handeye=e/'piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json'
review=json.loads(manual.read_text())
X=np.array(json.loads(handeye.read_text())['T_gripperBase_colorOptical_candidate'])
inv=np.linalg.inv(X)
K=np.array([[488.808654785*319/639,0,315.50680542*319/639],
            [0,488.808654785*239/479,214.381820679*239/479],[0,0,1.]])
out=ROOT/'manual_projection';out.mkdir(exist_ok=False)
paths=[('new_pair02','new_pair02/attempt02/grip_capture/portable/grip_candidate_rgbd'),
       ('new_pair07','new_pair07/attempt03/grip_capture/portable/capture')]
report={'offline_only':True,'changes_TF_TCP_or_motion':False,
        'current_mount_assumed_same_as_old_manual_sessions':True,
        'heldout07_validation_only_no_fit_selection':True,
        'visible_mask_centroid_NOT_3D_center':True,'K_320x240':K.tolist(),
        'sources_sha256':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [manual,handeye]},'frames':[]}
for pair,folder in paths:
    source=e/'piper_calibration_p1_20261015'/folder/'evidence/0001_rgb.png'
    im=cv2.imread(str(source));assert im.shape[:2]==(240,320)
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.array([125,35,20]),np.array([160,255,255]))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    c=max(contours,key=cv2.contourArea);m=cv2.moments(c)
    centroid=[m['m10']/m['m00'],m['m01']/m['m00']]
    row={'pair':pair,'source':str(source.relative_to(REPO)),
         'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'visible_purple_bbox_xywh':list(cv2.boundingRect(c)),
         'visible_purple_centroid_px':centroid,'points':{}}
    overlay=cv2.resize(im,(640,480),interpolation=cv2.INTER_NEAREST)
    cv2.drawContours(overlay,[c*2],-1,(0,255,0),1)
    refs=[('nominal_tip',[0,0,.1358],(255,255,0)),
          ('manual02_candidate',review['pairs'][0]['implied_tool_center_m_under_NEW_X'],(0,0,255)),
          ('manual07_validation',review['pairs'][1]['implied_tool_center_m_under_NEW_X'],(0,165,255))]
    for i,(label,p,color) in enumerate(refs):
        pc=inv@np.r_[p,1.];assert pc[2]>0
        uv=K@pc[:3];uv=uv[:2]/uv[2]
        row['points'][label]={'tool_m':p,'color_optical_m':pc[:3].tolist(),
            'pixel':uv.tolist(),'signed_mask_distance_px':cv2.pointPolygonTest(c,tuple(uv),True),
            'visible_centroid_distance_px':float(np.linalg.norm(uv-centroid))}
        pt=tuple(np.rint(uv*2).astype(int))
        cv2.drawMarker(overlay,pt,color,cv2.MARKER_CROSS,14,2)
        cv2.putText(overlay,label,(10,20+22*i),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
    cv2.putText(overlay,'OFFLINE: candidate projection, NOT ground truth',(8,466),
                cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1)
    assert cv2.imwrite(str(out/(pair+'_overlay.png')),overlay)
    report['frames'].append(row)
report['conclusion']='Manual-derived local candidates project outside the visible clamped cube. Do not adopt as verified TCP or use historical fixture for current hardware; inspect mount/FK/reference consistency first.'
with (out/'report.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report,indent=2))
