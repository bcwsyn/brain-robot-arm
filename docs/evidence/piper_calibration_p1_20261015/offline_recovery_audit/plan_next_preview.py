"""Offline common optical-FOV guidance, not a motion plan or depth estimate."""
import json,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,'/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
from review_depth_registration import calibration,read_config

def common_field(camera,kd,depth_size,rgb_size,assumed_depths):
    if not assumed_depths or any(not np.isfinite(z) or z<=0 for z in assumed_depths):
        raise ValueError('Positive finite explicit assumed depths required')
    width,height=rgb_size;yy,xx=np.mgrid[:height,:width]
    u=xx*(camera['size'][0]-1)/(width-1)
    if camera['mirror']:u=camera['size'][0]-1-u
    rays=np.stack([u,yy*(camera['size'][1]-1)/(height-1),np.ones_like(u)],axis=-1)
    rays=rays@np.linalg.inv(camera['k']).T@np.linalg.inv(camera['r']).T
    offset=-np.linalg.inv(camera['r'])@camera['t'];mask=np.ones((height,width),bool)
    for z in assumed_depths:
        scale=(z-offset[2])/rays[...,2]
        p=rays*scale[...,None]+offset
        uv=(p@kd.T)[...,:2]/p[...,2,None]
        mask&=(np.isfinite(uv).all(axis=-1)&(scale>0)&(uv[...,0]>=0)&(uv[...,0]<=depth_size[0]-1)&
               (uv[...,1]>=0)&(uv[...,1]<=depth_size[1]-1))
    return mask

def main(output):
    output.mkdir(exist_ok=False)
    base=Path('/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/release_observe_capture/portable_diagnostic20')
    row=json.loads((base/'capture/observer.jsonl').read_text().splitlines()[0])
    rgb=cv2.imread(str(base/'capture'/row['images']['rgb']['path']))
    info=row['latest']['/camera/depth/camera_info'];kd=np.array(info['k']).reshape(3,3)
    c=calibration(read_config(base/'detector_config.yaml'));zs=[.15,.18,.20,.23,.28,.35,.50]
    mask=common_field(c,kd,info['size'],list(rgb.shape[1::-1]),zs)
    # A 72px box is illustrative placement guidance only, not an added data gate.
    centres=cv2.erode(mask.astype(np.uint8),np.ones((73,73),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0)>0
    y,x=np.where(centres)
    if not len(x):raise ValueError('No common field for declared illustrative box; do not invent guidance')
    # Lower part of the common field: a flat-mat target need not be moved to
    # the far top of the scene (past data already had too few native samples).
    # This is image placement guidance, not an inferred robot-space distance.
    target=np.rint([np.median(x),np.quantile(y,.9)]).astype(int)
    witness=rgb.copy();layer=witness.copy();layer[centres]=(0,200,0)
    witness=cv2.addWeighted(witness,.7,layer,.3,0)
    cv2.drawContours(witness,cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],-1,(0,255,255),1)
    cv2.rectangle(witness,tuple(target-36),tuple(target+36),(0,255,0),1)
    cv2.drawMarker(witness,tuple(target),(0,255,0),cv2.MARKER_CROSS,12,1)
    cv2.rectangle(witness,(99,179),(139,219),(0,0,255),1)
    cv2.imwrite(str(output/'next_cube_placement_guidance.png'),cv2.resize(witness,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST))
    np.savez_compressed(output/'conditional_common_fov.npz',common_field=mask,illustrative_box_centres=centres)
    report={'offline_only':True,'robot_motion_planned_or_sent':False,'ROS_initialized':False,'CAN_accessed':False,
        'assumed_depths_m_not_measurements':zs,'factory_pinhole_convention_unchanged':True,
        'common_field_fraction':float(mask.mean()),'illustrative_box_width_px':72,
        'illustrative_cube_centre_rgb_xy':target.tolist(),'current_cube_bbox_xywh':[99,179,40,40],
        'placement_surface':'Flat black mat, not the elevated bottle/support; this is a NEW placement requiring a new paired B',
        'guidance_is_not_new_collection_or_motion_gate':True,'depth_validity_guaranteed':False,
        'requires_new_physical_cube_placement':True,'robot_stays_at_observation':True,
        'next_acquisition_protocol':['Operator moves cube/support only; no manual arm/grip yet',
            'Single continuous RGB-D source; bounded original read-only acquisition first',
            'Require original >=20 good-top frames with >=800 measured inliers before asking manual grip',
            'If not met, stop and inspect; no same-condition repeated60 or guessed depth',
            'Capture new manual B for this same new placement; never pair new A with old B'],
        'held_out_id_remains_new_pair07':True,'not_a_reachable_joint_trajectory_proposal':True}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'guidance_centre':target.tolist(),'common_field_fraction':float(mask.mean()),'depth_is_still_unknown':True}))

if __name__=='__main__':main(Path(sys.argv[1]))
