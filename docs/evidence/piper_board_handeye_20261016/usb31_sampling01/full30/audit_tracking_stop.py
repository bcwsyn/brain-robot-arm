"""Offline exact last-good to failed frame optical-flow diagnostic."""
import json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/board_spec_20261016')
from partial_board_tracking_check import propagate
rows=[json.loads(s) for s in (ROOT/'continuous_tracking.jsonl').read_text().splitlines()]
last=rows[-1];before=cv2.imread(str(ROOT/last['image_path']),cv2.IMREAD_GRAYSCALE)
failed=cv2.imread(str(ROOT/'failed_rgb.png'),cv2.IMREAD_GRAYSCALE)
tracks=propagate(before,failed,last['corners_px'])
result={'offline_only':True,'last_good_frame':last['index'],'fixed_ID_count':len(tracks),
 'last_good_source_stamp_ns':last['rgb_source_stamp_ns'],
 'failed_frame':json.loads((ROOT/'failed_frame.json').read_text()),'tracks':[],
 'original_threshold_px':.5,'threshold_changed':False}
overlay=cv2.cvtColor(failed,cv2.COLOR_GRAY2BGR)
for id,t in zip(last['fixed_IDs'],tracks):
    bad=not(t['forward_status'] and t['reverse_status'] and t['inside_image']) or t['forward_backward_error_px']>.5
    result['tracks'].append({'fixed_ID':id,'original_would_reject':bad,**t})
    xy=tuple(np.rint(t['position_px']).astype(int));color=(0,0,255) if bad else (0,255,0)
    cv2.circle(overlay,xy,3,color,1);cv2.putText(overlay,str(id),xy,cv2.FONT_HERSHEY_SIMPLEX,.25,color,1)
result['bad_IDs']=[t['fixed_ID'] for t in result['tracks'] if t['original_would_reject']]
result['max_FB_error_px']=max(t['forward_backward_error_px'] for t in tracks)
cv2.imwrite(str(ROOT/'tracking_failure_overlay.png'),overlay)
with (ROOT/'tracking_stop_audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps({'last_frame':last['index'],'bad_IDs':result['bad_IDs'],'max_FB_error_px':result['max_FB_error_px'],'bad_details':[t for t in result['tracks'] if t['original_would_reject']]}))
