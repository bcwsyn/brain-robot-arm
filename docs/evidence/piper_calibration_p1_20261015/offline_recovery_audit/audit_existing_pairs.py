"""Offline salvage/excitation audit. No ROS, device APIs, fitting or TF writes."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
TOOLS=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
sys.path.insert(0,str(TOOLS))
from estimate_calibration_cube_center import fit_plane,points_from_mask,square_hypothesis,transform_hypothesis
from export_calibration_bundle import verify_bundle
from fit_paired_calibration import transform
from review_depth_registration import calibration,read_config
from review_pair_sampling import selected_pixels
from calibration_p0_quality import top_hypothesis

REPO=Path('/mnt/hgfs/ub');BASE=REPO/'docs/evidence/piper_calibration_p1_20261015'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())

def translation_excitation(observe,grip):
    """Necessary pose-only identifiability for mount t and unknown grip c.

    Derived from t - R_A.T R_B c = R_A.T(b-a) - R_X p_C.
    Treating R_X as known makes this optimistic, not full hand-eye rank.
    """
    if not observe or len(observe)!=len(grip):raise ValueError('Matching nonempty actual pose lists required')
    h=np.vstack([np.c_[np.eye(3),-transform(a)[:3,:3].T@transform(b)[:3,:3]] for a,b in zip(observe,grip)])
    _,sv,vt=np.linalg.svd(h,full_matrices=True)
    complete=np.zeros(6);complete[:len(sv)]=sv
    rank=int(np.sum(complete>complete[0]*1e-6))
    return {'parameter_order':['mount_tx','mount_ty','mount_tz','tool_center_x','tool_center_y','tool_center_z'],
        'rank':rank,'unknowns':6,'singular_values':complete.tolist(),
        'condition_number':float(complete[0]/complete[-1]) if rank==6 else None,
        'weakest_parameter_direction':vt[-1].tolist(),
        'optimistic_known_mount_rotation_only':True,'full_hand_eye_identifiability_proven':False}

def two_face_check(points,edge=.029):
    """Original single-face checks on dominant and remaining measured support.

    Removing measured dominant inliers does not fill holes or approve a face.
    A second complete orthogonal face is corroboration only, not a new gate.
    """
    plane=fit_plane(points);primary=square_hypothesis(points,edge)
    residual=points[~plane['inliers']]
    report={'primary':primary,'remaining_native_samples':len(residual),
        'secondary':None,'secondary_error':None,'calibration_input_approved':False}
    try:report['secondary']=square_hypothesis(residual,edge)
    except ValueError as e:report['secondary_error']=str(e)
    if report['secondary']:
        secondary=report['secondary']
        a=np.asarray(primary['outward_normal_depth']);b=np.asarray(secondary['outward_normal_depth'])
        report['plane_angle_deg']=float(np.degrees(np.arccos(np.clip(abs(a@b),0,1))))
        report['two_independent_face_center_difference_m']=float(np.linalg.norm(
            np.array(primary['cube_center_depth_m'])-secondary['cube_center_depth_m']))
    return report,plane['inliers']

def support_patch_probe(depth,kd,projected,cube_points,camera):
    # Fixed from the original RGB before comparing numeric results. Keep ALL
    # four results, including failures; no search for a patch that passes.
    patches={'front_cap':[187,51,216,58],'left_cap':[176,38,187,50],
             'right_cap':[220,34,228,48],'mat_control':[150,150,175,175]}
    results=[]
    for label,box in patches.items():
        x0,y0,x1,y1=box
        mask=((depth>0)&(projected[...,0]>=x0)&(projected[...,0]<x1)&
              (projected[...,1]>=y0)&(projected[...,1]<y1))
        points=points_from_mask(depth,kd,mask)
        row={'region':label,'RGB_ROI_xyxy':box,'native_points':len(points),
             'physical_support_identity_not_verified':True,'quality_rule_changed':False}
        try:
            plane=fit_plane(points)
            row.update(plane_inlier_fraction=float(plane['inliers'].mean()),
                median_z_mm=float(np.median(points[:,2])*1000),normal=plane['normal'].tolist())
            top,_=top_hypothesis(cube_points,points,camera)
            row['original_top_rule_inliers']=top['plane_inliers']
        except ValueError as e:row['error']=str(e)
        results.append(row)
    return results

def main(output):
    output.mkdir(exist_ok=False)
    registry=load(BASE/'P1_registry.json');inputs={str((BASE/'P1_registry.json').relative_to(REPO)):sha(BASE/'P1_registry.json')}
    observe=[];grips=[];pair_rows=[]
    for row in registry['rows']:
        pair=row['pair_id'];q=load(REPO/row['source']);assert sha(REPO/row['source'])==row['source_sha256']
        inputs[row['source']]=row['source_sha256']
        if pair in ('new_pair02','new_pair03'):
            bundle=BASE/pair/'attempt02/observe_capture/portable';grip=BASE/pair/'attempt02/grip_capture/portable'
        elif pair=='new_pair04':
            bundle=BASE/pair/'attempt01/observe_after_reconnect/portable';grip=BASE/pair/'attempt01/grip_capture/portable'
        elif pair=='new_pair05':
            bundle=BASE/pair/'attempt01/observe_capture/portable';grip=BASE/pair/'attempt01/grip_capture/portable'
        elif pair=='new_pair06':
            bundle=BASE/pair/'attempt01/observe_capture/portable_review20';grip=BASE/pair/'attempt01/grip_capture/portable'
        else:
            bundle=BASE/pair/'attempt01/release_observe_capture/portable_diagnostic20';grip=BASE/pair/'attempt01/grip_capture/portable'
        verify_bundle(bundle,load(bundle/'manifest.json'));verify_bundle(grip,load(grip/'manifest.json'))
        for folder in (bundle,grip):inputs[str((folder/'manifest.json').relative_to(REPO))]=sha(folder/'manifest.json')
        review=load(bundle/'depth_review.json');first=review['frames'][0]
        g=load(grip/'sdk_review.json')
        fresh=next(s for s in g['samples'] if s['feedback_fresh'])
        a,b=transform(first['T_base_tool']),transform(fresh['T_base_tool'])
        if row['role']=='fit':observe.append(a);grips.append(b)
        frames=q.get('frames',[])
        if not isinstance(frames,list):frames=[]
        candidates=[f['candidate'] for f in frames if f.get('candidate')]
        centres=np.asarray([c['cube_center_depth_m'] for c in candidates])
        item={'pair_id':pair,'role':row['role'],'original_quality_summary':row,
            'actual_T_base_tool_observe':a.tolist(),'actual_T_base_tool_grip':b.tolist(),
            'available_original_dominant_face_candidates':len(candidates),
            'fitting_input_approved':False,'verified_camera_center':None,
            'raw_selected_samples_range':([min(f['native_selected_points'] for f in frames),max(f['native_selected_points'] for f in frames)] if frames and 'native_selected_points' in frames[0] else None)}
        if len(centres):
            median=np.median(centres,axis=0)
            item['candidate_centre_summary']={'median_depth_frame_m':median.tolist(),
                'maximum_temporal_deviation_m':float(np.linalg.norm(centres-median,axis=1).max()),
                'std_m':np.std(centres,axis=0).tolist(),'temporal_precision_is_not_absolute_accuracy':True}
        pair_rows.append(item)
    excitation=translation_excitation(observe,grips)
    bundle=BASE/'new_pair06/attempt01/observe_capture/portable_review20'
    row=json.loads((bundle/'capture/observer.jsonl').read_text().splitlines()[0])
    rgb=cv2.imread(str(bundle/'capture'/row['images']['rgb']['path']))
    depth=cv2.imread(str(bundle/'capture'/row['images']['depth']['path']),-1)
    params=read_config(bundle/'detector_config.yaml');camera=calibration(params)
    selected,projected,_,_=selected_pixels(rgb,depth,row['latest']['/camera/depth/camera_info'],params,camera)
    kd=np.asarray(row['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
    check,inliers=two_face_check(points_from_mask(depth,kd,selected))
    assert check['primary']['plane_inliers']==2033
    witness=rgb.copy();yy,xx=np.where(selected);pixels=projected[yy,xx]
    witness[pixels[inliers,1],pixels[inliers,0]]=(255,255,0)
    witness[pixels[~inliers,1],pixels[~inliers,0]]=(255,0,255)
    cv2.imwrite(str(output/'fifth_measured_support_witness.png'),cv2.resize(witness,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST))
    (output/'fifth_two_face_check.json').write_text(json.dumps(check,indent=2,allow_nan=False))
    patches=support_patch_probe(depth,kd,projected,points_from_mask(depth,kd,selected),camera)
    (output/'fixed_support_patch_probe.json').write_text(json.dumps(patches,indent=2,allow_nan=False))
    result={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
        'production_or_quality_threshold_changed':False,'fit_performed':False,'input_SHA':inputs,
        'pairs':pair_rows,'training_only_pose_excitation':excitation,'held_out_excluded_from_excitation':True,
        'fifth_full_face_needs_review_not_relabelled_top':True,
        'existing_pending_P2_frame_work':'Known deferred work: fit_paired_calibration accepts D optical only, while P0 plan requests C optical. Do not relabel C points as D; explicit equivalent-frame support/conversion remains P2, not implemented or run early here.',
        'all_original_quality_approvals_unchanged':True}
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'pose_translation_rank':excitation['rank'],'pose_translation_condition':excitation['condition_number'],
        'fifth_remaining_points':check['remaining_native_samples'],'second_face_supported':check['secondary'] is not None,
        'second_face_error':check['secondary_error'],'fit_performed':False}))

if __name__=='__main__':main(Path(sys.argv[1]))
