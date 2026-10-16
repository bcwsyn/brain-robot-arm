"""Offline fixed-subset replay through all archived motion frames + failed frame.

No threshold change or fabricated image/point; no hardware use.
"""
import json,sys,time
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/board_spec_20261016')
from partial_board_tracking_check import propagate
cv2.setNumThreads(1)
seed=json.loads((ROOT/'session_seed.json').read_text())
ids=[i for i in seed['fixed_interior_IDs'] if 110<=seed['visible_corners'][i][0]<=175 and 95<=seed['visible_corners'][i][1]<=165]
assert len(ids)>=9
rows=[json.loads(l) for l in (ROOT/'continuous_tracking.jsonl').read_text().splitlines()]
pts=np.asarray(seed['visible_corners'],np.float32)[ids]
prev=None;checks=[];start=time.monotonic()
for i,row in enumerate(rows+[{'image_path':'failed_rgb.png','index':'failed'}]):
    img=cv2.imread(str(ROOT/row['image_path']),cv2.IMREAD_GRAYSCALE)
    if prev is not None:
        tracks=propagate(prev,img,pts)
        good=all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks)
        err=max(t['forward_backward_error_px'] for t in tracks)
        nxt=np.asarray([t['position_px'] for t in tracks],np.float32)
        step=float(np.linalg.norm(nxt-pts,axis=1).max())
        checks.append({'index':row['index'],'all_status_inside':good,'max_FB_error_px':err,'max_step_px':step,
                       'original_checks_pass':good and err<=.5 and step<=6})
        pts=nxt
    prev=img
result={'offline_only':True,'camera_or_robot_started':False,'source_session':str(ROOT),
 'seed_ROI_pixels':[110,95,175,165],'subset_fixed_original_IDs':ids,'points':len(ids),
 'checked_transitions':len(checks),'all_original_thresholds_pass':all(c['original_checks_pass'] for c in checks),
 'max_FB_error_px':max(c['max_FB_error_px'] for c in checks),'max_step_px':max(c['max_step_px'] for c in checks),
 'thresholds_unchanged':{'forward_reverse_px':.5,'step_px':6},
 'failures':[c for c in checks if not c['original_checks_pass']], 'elapsed_s':time.monotonic()-start,
 'future_unrecorded_pose_visibility_NOT_proven':True,'old_data_relabelled_or_accepted_as_complete':False}
with (ROOT/'safe_seed_replay.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result))
