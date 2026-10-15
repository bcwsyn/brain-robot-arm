"""Offline diagnostic: fixed assumed ray footprints, NOT measured cube depth.

No mount TF/IK/ROS/device access. Reads all original native-zero PNG values.
"""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,'/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
from review_depth_registration import calibration,color_mask,read_config,ray_scan,make_heatmap

def audit(root):
    output=root/'footprint_audit';output.mkdir(exist_ok=False)
    rows=[json.loads(s) for s in (root/'session/capture/observer.jsonl').read_text().splitlines() if s]
    capture=root/'session/capture';first=rows[0]
    rgb=cv2.imread(str(capture/first['images']['rgb']['path']))
    depth=cv2.imread(str(capture/first['images']['depth']['path']),-1)
    p=read_config(root/'portable_all60/detector_config.yaml');camera=calibration(p)
    mask,_=color_mask(rgb,p)
    kd=np.asarray(first['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
    results,outlines=ray_scan(mask,depth,kd,camera,[.12,.15,.18,.20,.23,.28,.35,.50])
    fixed=np.zeros(depth.shape,np.uint8)
    for z,hull in outlines:
        if .18<=z<=.50:cv2.fillConvexPoly(fixed,np.rint(hull).astype(np.int32),1)
    fixed=fixed>0
    frames=[]
    for row in rows:
        path=capture/row['images']['depth']['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['images']['depth']['sha256']
        a=cv2.imread(str(path),-1);assert a.dtype==np.uint16 and a.shape==depth.shape
        assert row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
        frames.append({'snapshot':row['snapshot'],'depth_stamp_ns':str(row['stamps_ns']['depth']),
            'fixed_assumed_footprint_raw_zero_fraction':float(np.mean(a[fixed]==0)),
            'whole_native_nonzero_fraction':float(np.mean(a>0))})
    report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'raw_modified':False,
        'assumed_depths_are_not_measurements':True,'fixed_footprint_rule':'First RGB mask projected assuming D.Z=.18,.20,.23,.28,.35,.50m; union of hulls clipped to actual depth image; not a confirmed physical cube region',
        'frame_count':len(rows),'fixed_diagnostic_native_pixels':int(fixed.sum()),'ray_results':results,'frames':frames,
        'all_original_measured_projections_in_cube_mask':0,
        'conclusion':'RGB target complete; under the unchanged factory pinhole convention about25% of mask rays lie below native depth FOV. In-FOV assumed footprints also have missing raw depth; cropping alone does not explain all missing support.',
        'not_proven':'True cube depth, material/IR/occlusion/near-range cause, physical movement, or absolute calibration accuracy. No missing depth synthesized.'}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    np.savez_compressed(output/'fixed_assumed_native_footprint.npz',diagnostic_mask=fixed)
    make_heatmap(output/'native_depth_assumed_rays.png',depth,outlines,'Sixth A: raw zeros; assumed rays are NOT measured cube depth')
    print(json.dumps({'frames':len(rows),'assumed_native_pixels':int(fixed.sum()),
        'raw_zero_fraction_range':[min(f['fixed_assumed_footprint_raw_zero_fraction'] for f in frames),max(f['fixed_assumed_footprint_raw_zero_fraction'] for f in frames)],
        'hypothesis_not_cube_depth':True}))

if __name__=='__main__':audit(Path(sys.argv[1]))
