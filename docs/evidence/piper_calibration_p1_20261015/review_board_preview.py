"""Fixed local3x3 checker-corner diagnostic, never a full-board detector or PnP."""
from pathlib import Path
import hashlib,json,sys
import cv2,numpy as np
REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle

def grid_residual(corners):
    points=np.asarray(corners,dtype=np.float64)
    if points.shape!=(9,2) or not np.isfinite(points).all():raise ValueError('Nine finite local candidate corners required')
    grid=np.mgrid[0:3,0:3].T.reshape(-1,2).astype(np.float64)
    matrix,_=cv2.findHomography(grid,points,0)
    if matrix is None:raise ValueError('Degenerate local diagnostic homography')
    predicted=cv2.perspectiveTransform(grid[None],matrix)[0]
    error=np.linalg.norm(predicted-points,axis=1)
    return {'rms_px':float(np.sqrt(np.mean(error**2))),'max_px':float(error.max()),
            'not_an_intrinsic_or_hand_eye_calibration':True,'formal_pose_estimation_performed':False}

def review(bundle,output):
    if output.exists():raise FileExistsError('Do not overwrite board evidence')
    manifest=json.loads((bundle/'manifest.json').read_text());verify_bundle(bundle,manifest)
    capture=bundle/manifest['observation_capture']
    rows=[json.loads(line) for line in (capture/'observer.jsonl').read_text().splitlines() if line]
    output.mkdir(exist_ok=False);result=[];all_points=[]
    flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE
    for row in rows:
        p=capture/row['images']['rgb']['path'];rgb=cv2.imread(str(p));gray=cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY)
        found,corners=cv2.findChessboardCornersSB(gray,(3,3),flags=flags)
        item={'snapshot':row['snapshot'],'rgb_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'source_stamps_ns':row['stamps_ns'],'local_candidate_found':bool(found),
              'global_board_corner_IDs_known':False,'accepted_for_calibration':False}
        if found:
            points=corners.reshape(-1,2);all_points.append(points);item['local_corners_px']=points.tolist()
            item['local_homography_diagnostic']=grid_residual(points)
            if len(result)==0:
                witness=rgb.copy();cv2.drawChessboardCorners(witness,(3,3),corners,True)
                witness=cv2.resize(witness,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
                cv2.putText(witness,'LOCAL 3x3 CANDIDATES ONLY - NOT FULL BOARD',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
                cv2.imwrite(str(output/'local_candidates_only.png'),witness)
        result.append(item)
    spread=np.linalg.norm(np.ptp(np.asarray(all_points),axis=0),axis=1).tolist() if len(all_points)>1 else None
    report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
        'input_manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
        'opencv_version':cv2.__version__,'fixed_local_pattern_inner_corners':[3,3],
        'fixed_local_pattern_is_NOT_actual_full_board_dimensions':True,'user_reported_square_length_m':.032,
        'square_length_caliper_verified':False,'actual_full_grid_dimensions':None,
        'whole_board_outline_visible':False,'gripper_and_cube_occlude_lower_region':True,
        'detector_true_does_not_prove_correct_global_corners':True,'local_corner_spread_bbox_diagonal_px':spread,
        'PnP_or_hand_eye_performed':False,'production_or_quality_thresholds_modified':False,'frames':result}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'frames':len(rows),'local_candidates_found':sum(f['local_candidate_found'] for f in result),
        'largest_local_corner_spread_px':max(spread) if spread else None,'calibration_performed':False}))

if __name__=='__main__':review(Path(sys.argv[1]),Path(sys.argv[2]))
