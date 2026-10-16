"""Offline partial-board pose/FK diagnostics; not mount calibration or motion.

Reuse archived raw pixels, fixed-ID LK and factory metadata. Preserve both
planar pose solutions. Alternative intrinsics are sensitivity hypotheses,
not an automatic update of production intrinsics or TF.
"""
import hashlib,json,sys
from pathlib import Path
import cv2
import numpy as np
from partial_board_tracking_check import propagate

ROOT=Path(__file__).resolve().parent.parent/'board_observe'

def grid(shape=(9,7),spacing=.032):
    c,r=shape
    if c<2 or r<2 or spacing<=0:raise ValueError('Invalid metric grid')
    result=np.zeros((c*r,3),dtype=np.float64)
    result[:,:2]=np.mgrid[0:c,0:r].T.reshape(-1,2)*spacing
    return result

def poses(object_points,image_points,k,d):
    obj=np.asarray(object_points,dtype=np.float64);img=np.asarray(image_points,dtype=np.float64)
    if obj.ndim!=2 or obj.shape[1]!=3 or img.shape!=(len(obj),2) or len(obj)<4:
        raise ValueError('At least four matching 3D/2D points required')
    if not np.isfinite(obj).all() or not np.isfinite(img).all():raise ValueError('Non-finite points')
    if np.linalg.matrix_rank(obj-obj.mean(axis=0))!=2:raise ValueError('A non-degenerate planar grid is required')
    found,rvecs,tvecs,_=cv2.solvePnPGeneric(obj,img,k,d,flags=cv2.SOLVEPNP_IPPE)
    if not found:raise ValueError('No planar pose candidates')
    result=[]
    for r,t in zip(rvecs,tvecs):
        initial=np.eye(4);initial[:3,:3]=cv2.Rodrigues(r)[0];initial[:3,3]=t.ravel()
        raw,_=cv2.projectPoints(obj,r,t,k,d)
        unrefined_rms=float(np.sqrt(np.mean(np.sum((raw.reshape(-1,2)-img)**2,axis=1))))
        rr,tt=cv2.solvePnPRefineLM(obj,img,k,d,r.copy(),t.copy())
        rot,_=cv2.Rodrigues(rr);matrix=np.eye(4);matrix[:3,:3]=rot;matrix[:3,3]=tt.ravel()
        z=(obj@rot.T+tt.reshape(1,3))[:,2]
        projected,_=cv2.projectPoints(obj,rr,tt,k,d)
        residual=np.linalg.norm(projected.reshape(-1,2)-img,axis=1)
        result.append({'unrefined_IPPE_T_color_optical_from_local_board':initial.tolist(),
            'T_color_optical_from_local_board':matrix.tolist(),'all_points_positive_depth':bool((z>0).all()),
            'unrefined_IPPE_rms_px':unrefined_rms,'refined_rms_px':float(np.sqrt(np.mean(residual**2))),
            'refined_max_px':float(residual.max()),'minimum_point_depth_m':float(z.min())})
    return result

def main():
    calibration=json.loads((ROOT/'portable/calibration.json').read_text())
    manifest=json.loads((ROOT/'portable/manifest.json').read_text())
    assert all(hashlib.sha256((ROOT/'portable'/f['path']).read_bytes()).hexdigest()==f['sha256'] for f in manifest['files'])
    rows=[json.loads(l) for l in (ROOT/'portable/capture/observer.jsonl').read_text().splitlines() if l]
    frames=json.loads((ROOT/'corner_diagnostic/report.json').read_text())['frames']
    k_full=np.asarray(calibration['color_factory']['K']).reshape(3,3)
    scales={'existing_endpoint_resize':calibration['color_capture']['existing_detector_resize_factors'],
        'half_resolution_hypothesis':[.5,.5]}
    distortions={'reported_CameraInfo_zero':calibration['color_factory']['CameraInfo_D'],
        'installed_driver_reordered_factory_hypothesis':calibration['color_factory']['D_reordered_by_installed_driver']}
    model=[]
    for scale_label,(sx,sy) in scales.items():
        for distortion_label,d in distortions.items():
            k=np.diag([sx,sy,1.])@k_full
            model.append({'label':scale_label+'/'+distortion_label,'K':k.tolist(),'D':d,
                'candidates':poses(grid(),frames[0]['corners_px'],k,np.asarray(d))})
    k=np.asarray(model[0]['K']);d=np.asarray(model[0]['D'])
    fixed=np.asarray(frames[0]['corners_px'],dtype=np.float32);previous=None;actual=[]
    for i,row in enumerate(rows):
        image=cv2.imread(str(ROOT/'portable/capture'/row['images']['rgb']['path']),cv2.IMREAD_GRAYSCALE)
        if previous is not None:
            tracks=propagate(previous,image,fixed)
            if not all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks):
                raise ValueError('Unassociated points: no implicit reference reset')
            fixed=np.asarray([t['position_px'] for t in tracks],dtype=np.float32)
        actual.append({'snapshot':row['snapshot'],'source_stamps_ns':row['stamps_ns'],'actual_q_driver_rad':row['q_rad'],
            'point_count':len(fixed),'candidates':poses(grid(),fixed,k,d)})
        previous=image
    review=json.loads((ROOT/'portable/depth_review.json').read_text())
    assert all(np.max(np.abs(np.asarray(r['q_rad'])-rows[0]['q_rad']))==0 for r in rows)
    tbase=review['frames'][0]['T_base_tool']
    best=[min(a['candidates'],key=lambda c:c['refined_rms_px']) for a in actual]
    translations=np.asarray([p['T_color_optical_from_local_board'] for p in best])[:,:3,3]
    print(json.dumps({'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
        'opencv_version':cv2.__version__,'camera_frame':'camera_color_optical_frame','camera_axes':'x right, y down, z forward',
        'pose_equation':'p_color_optical = T_color_optical_from_local_board * p_local_board',
        'T_base_from_gripper_base_archived_actual_FK':tbase,'model_URDF_SHA256':review['urdf_sha256'],
        'local_board_origin':'seed ID0; arbitrary fixed visible corner, not whole-board top left',
        'object_points_m':grid().tolist(),'actual_static_frame_diagnostics':actual,'intrinsics_sensitivity_first_frame':model,
        'static_translation_peak_to_peak_m_lowest_residual_diagnostic_only':np.ptp(translations,axis=0).tolist(),
        'raw_factory_D_preserved_not_interpreted_as_new_truth':calibration['color_factory']['raw_factory_D'],
        'resize_or_distortion_hypothesis_adopted':False,'true_3D_board_planarity_verified':False,
        'PnP_executed_offline_only':True,'hand_eye_fit_performed':False,'mount_TF_deployed':False,
        'real_multi_pose_count':1,'hand_eye_samples_fabricated':False,
        'limitations':['Grid scale and planar model are nominal assumptions, not measured proof.',
            'Low reprojection residual does not verify metric accuracy, intrinsics or physical board flatness.',
            'Both planar candidate branches are preserved; refinement may converge them to the same minimum.',
            'No camera mount transform can be inferred from these five same-pose images alone.']},indent=2,allow_nan=False))

if __name__=='__main__':main()
