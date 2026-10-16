"""Offline fixed-ID tracking diagnostic; no ROS, CAN, PnP or production edits.

The initial visible subgrid defines an arbitrary FIXED board frame. Global
paper-edge IDs are not required if physical point identities remain fixed.
This tests only five static real frames and explicit synthetic small warps;
it does not validate tracking during actual robot motion or solve hand-eye.
"""
import hashlib,json
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent.parent/'board_observe'

def propagate(first,second,points):
    """Return diagnostic tracks and original IDs, never re-detect/renumber."""
    p=np.asarray(points,dtype=np.float32).reshape(-1,1,2)
    nxt,status,_=cv2.calcOpticalFlowPyrLK(first,second,p,None,winSize=(15,15),maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    back,reverse_status,_=cv2.calcOpticalFlowPyrLK(second,first,nxt,None,winSize=(15,15),maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    fb=np.linalg.norm(back.reshape(-1,2)-p.reshape(-1,2),axis=1)
    result=[]
    for i,(xy,ok,rev,err) in enumerate(zip(nxt.reshape(-1,2),status.ravel(),reverse_status.ravel(),fb)):
        inside=bool(0<=xy[0]<second.shape[1] and 0<=xy[1]<second.shape[0])
        result.append({'initial_id':i,'position_px':xy.tolist(),'forward_status':bool(ok),
            'reverse_status':bool(rev),'inside_image':inside,'forward_backward_error_px':float(err)})
    return result

def main():
    manifest=json.loads((ROOT/'portable/manifest.json').read_text())
    assert all(hashlib.sha256((ROOT/'portable'/f['path']).read_bytes()).hexdigest()==f['sha256'] for f in manifest['files'])
    detections=json.loads((ROOT/'corner_diagnostic/report.json').read_text())['frames']
    capture=ROOT/'portable/capture'
    rows=[json.loads(l) for l in (capture/'observer.jsonl').read_text().splitlines() if l]
    images=[cv2.imread(str(capture/r['images']['rgb']['path']),cv2.IMREAD_GRAYSCALE) for r in rows]
    seed=np.asarray(detections[0]['corners_px'],dtype=np.float32)
    points=seed.copy();actual=[]
    for i in range(1,len(images)):
        tracks=propagate(images[i-1],images[i],points)
        points=np.asarray([t['position_px'] for t in tracks],dtype=np.float32)
        independent=np.asarray(detections[i]['corners_px'])
        actual.append({'from_snapshot':rows[i-1]['snapshot'],'to_snapshot':rows[i]['snapshot'],
            'original_ID_count':len(tracks),'forward_and_reverse_success_count':sum(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks),
            'max_forward_backward_error_px':max(t['forward_backward_error_px'] for t in tracks),
            'max_same_index_distance_to_prior_independent_detections_px':float(np.linalg.norm(points-independent,axis=1).max()),
            'failed_original_ids':[t['initial_id'] for t in tracks if not (t['forward_status'] and t['reverse_status'] and t['inside_image'])]})
    synthetic=[]
    for label,degrees,dx,dy in [('translation',0,3,-2),('rotate_plus',3,0,0),('rotate_minus',-3,0,0)]:
        transform=cv2.getRotationMatrix2D((160,120),degrees,1.)
        transform[:,2]+=[dx,dy]
        altered=cv2.warpAffine(images[0],transform,(320,240))
        expected=cv2.transform(seed[None],transform)[0]
        tracks=propagate(images[0],altered,seed)
        measured=np.asarray([t['position_px'] for t in tracks])
        valid=np.asarray([t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks])
        errors=np.linalg.norm(measured-expected,axis=1)
        synthetic.append({'label':label,'synthetic_image_not_actual_motion':True,'degrees':degrees,'translation_px':[dx,dy],
            'original_ID_count':len(seed),'successful_inside_count':int(valid.sum()),
            'max_known_transform_error_px':float(errors[valid].max()) if valid.any() else None,
            'median_known_transform_error_px':float(np.median(errors[valid])) if valid.any() else None})
    print(json.dumps({'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
        'method':'OpenCV calcOpticalFlowPyrLK forward/reverse; seed fixed IDs, no per-frame redetection/renumbering',
        'opencv_version':cv2.__version__,'seed_visible_grid':[9,7],'fixed_seed_ID_count':len(seed),'square_length_m_operator_reported':.032,
        'seed_local_frame_arbitrary_but_must_remain_same_physical_points':True,
        'seed_ids_are_NOT_whole_board_global_IDs':True,
        'real_frames_same_static_pose_only':True,'actual_motion_tracking_validated':False,
        'real_frame_checks':actual,'synthetic_checks':synthetic,
        'limitations':['Optical flow on repeated checker patterns may slip by a square; low forward/reverse error alone does not prove correct physical identity.',
            'Synthetic image warps cannot reproduce real 3D motion, blur, lighting or occlusion.',
            'If identity is lost, do not silently reset the board origin; record that sample as unassociated.',
            'This does not establish board flatness, printed scale, camera intrinsics or hand-eye accuracy.'],
        'PnP_hand_eye_or_production_TF_changed':False},indent=2,allow_nan=False))

if __name__=='__main__':main()
