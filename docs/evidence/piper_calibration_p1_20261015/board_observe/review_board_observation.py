"""Read-only enlarged visible-grid diagnostic, NOT global board pose or calibration."""
from pathlib import Path
import hashlib, json, sys
import cv2
import numpy as np

def fit_grid(points, shape):
    columns,rows=map(int,shape)
    p=np.asarray(points,dtype=np.float64)
    if columns<3 or rows<3 or p.shape!=(rows*columns,2) or not np.isfinite(p).all():
        raise ValueError('Finite rectangular visible grid required')
    grid=np.mgrid[0:columns,0:rows].T.reshape(-1,2).astype(np.float64)
    h,_=cv2.findHomography(grid,p,0)
    if h is None:raise ValueError('Degenerate grid')
    residual=np.linalg.norm(cv2.perspectiveTransform(grid[None],h)[0]-p,axis=1)
    return {'rms_px':float(np.sqrt(np.mean(residual**2))),'max_px':float(residual.max())}

def main(capture,output):
    output.mkdir(exist_ok=False)
    rows=[json.loads(l) for l in (capture/'observer.jsonl').read_text().splitlines() if l]
    flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_LARGER
    frames=[]
    for row in rows:
        p=capture/row['images']['rgb']['path'];rgb=cv2.imread(str(p))
        if rgb is None:raise ValueError('Cannot read original RGB')
        found,corners,meta=cv2.findChessboardCornersSBWithMeta(cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY),(3,3),flags=flags)
        item={'snapshot':row['snapshot'],'rgb_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'source_stamps_ns':row['stamps_ns'],'visible_candidate_found':bool(found),
              'global_board_corner_IDs_known':False,'accepted_for_calibration':False}
        if found:
            shape=(meta.shape[1],meta.shape[0]);points=corners.reshape(-1,2)
            item.update(visible_grid_inner_corners=list(shape),corners_px=points.tolist(),homography=fit_grid(points,shape))
            witness=rgb.copy();cv2.drawChessboardCorners(witness,shape,corners,True)
            cv2.imwrite(str(output/(str(row['snapshot'])+'_visible_candidates.png')),witness)
        frames.append(item)
    report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
            'opencv_version':cv2.__version__,'seed_inner_corners':[3,3],'CALIB_CB_LARGER':True,
            'seed_and_detected_visible_grid_are_NOT_full_board_dimensions':True,
            'visual_review_whole_board_visible':False,'visual_review_missing':'lower board boundary outside image; fingers occlude lower sides',
            'full_board_dimensions':None,'square_mm_operator_reported':32,
            'global_board_coordinate_origin_known':False,'PnP_or_hand_eye_performed':False,'frames':frames}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'frames':len(frames),'visible_candidates':[{'found':f['visible_candidate_found'],'grid':f.get('visible_grid_inner_corners'),'homography':f.get('homography')} for f in frames],'full_board_known':False,'calibration_performed':False}))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
