"""Exact runtime BGR->gray replay; preserve earlier imread(gray) diagnostics."""
import json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent
OLD=Path('/home/johnwick/brain_robot_logs/board_usb31_original_20261016.G2lzeV')
INIT=Path('/home/johnwick/brain_robot_logs/board_safe_seed_20261016.7Zjm2l')
sys.path.insert(0,'/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/board_spec_20261016')
from partial_board_tracking_check import propagate
cv2.setNumThreads(1)
seed=json.loads((OLD/'session_seed.json').read_text())
ids=[i for i in seed['fixed_interior_IDs'] if 110<=seed['visible_corners'][i][0]<=175 and 95<=seed['visible_corners'][i][1]<=165]
rows=[json.loads(l) for l in (OLD/'continuous_tracking.jsonl').read_text().splitlines()]
pts=np.asarray(seed['visible_corners'],np.float32)[ids];prev=None;checks=[]
for row in rows+[{'image_path':'failed_rgb.png','index':'failed'}]:
    bgr=cv2.imread(str(OLD/row['image_path']));gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    if prev is not None:
        tracks=propagate(prev,gray,pts)
        err=max(t['forward_backward_error_px'] for t in tracks)
        nxt=np.asarray([t['position_px'] for t in tracks],np.float32)
        step=float(np.linalg.norm(nxt-pts,axis=1).max())
        checks.append({'index':row['index'],'FB_px':err,'step_px':step,
          'pass':all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks) and err<=.5 and step<=6})
        pts=nxt
    prev=gray
last=rows[-1]
tracks=propagate(cv2.cvtColor(cv2.imread(str(OLD/last['image_path'])),cv2.COLOR_BGR2GRAY),
                 cv2.cvtColor(cv2.imread(str(OLD/'failed_rgb.png')),cv2.COLOR_BGR2GRAY),last['corners_px'])
bgr=cv2.imread(str(INIT/'failed_rgb.png'));runtime=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY);other=cv2.imread(str(INIT/'failed_rgb.png'),0)
def detect(gray):
    ok,c,m=cv2.findChessboardCornersSBWithMeta(gray,(3,3),flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_LARGER)
    if not ok:return {'detected':False}
    n,r=m.shape[1],m.shape[0];ids=[y*n+x for y in range(1,r-1) for x in range(1,n-1)]
    ids=[i for i in ids if 110<=c.reshape(-1,2)[i][0]<=175 and 95<=c.reshape(-1,2)[i][1]<=165]
    return {'detected':True,'visible_grid':[n,r],'ROI_corner_count':len(ids)}
result={'offline_only':True,'runtime_gray_definition':'cv2.cvtColor(lossless saved BGR, COLOR_BGR2GRAY)',
 'previous_imread_gray_reports_preserved_as_not_bit_exact':True,
 'exact_last_to_failed_bad_IDs':[i for i,t in zip(last['fixed_IDs'],tracks) if not(t['forward_status'] and t['reverse_status'] and t['inside_image']) or t['forward_backward_error_px']>.5],
 'exact_last_to_failed_max_FB_px':max(t['forward_backward_error_px'] for t in tracks),
 'ROI_replay':{'points':len(ids),'transitions':len(checks),'all_original_checks_pass':all(c['pass'] for c in checks),
     'max_FB_px':max(c['FB_px'] for c in checks),'max_step_px':max(c['step_px'] for c in checks),'failures':[c for c in checks if not c['pass']]},
 'initial_seed_frame_gray_sensitivity':{'max_gray_difference':int(np.abs(runtime.astype(int)-other.astype(int)).max()),
    'differing_pixels':int((runtime!=other).sum()),'exact_runtime_gray_detection':detect(runtime),'imread_gray_detection':detect(other)},
 'no_production_or_control_change':True}
with (ROOT/'exact_gray_audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result))
