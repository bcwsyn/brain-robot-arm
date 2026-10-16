"""Offline pair01 surface correspondence; no camera, ROS, CAN or configuration writes.

Both transforms are tested on ALL 30 immutable frames. Surface slab is fixed
from the previously published 0.440m high-support surface, not optimized here.
This tests local correspondence, not globally calibrated depth accuracy.
"""
import copy,hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from review_depth_registration import calibration,color_mask,project_measured,read_config
SOURCE=REPO/'docs/evidence/piper_calibration_20261014/pair01'
CAPTURE=SOURCE/'pair01_observe_remeasure_20261014_rgbd'
PARAMS=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
configured=calibration(PARAMS)
live=copy.deepcopy(configured)
T=np.array(json.loads((ROOT/'live_composition_review.json').read_text())['live_T_colorOptical_depthOptical'])
live['r'],live['t']=T[:3,:3],T[:3,3]
old=json.loads((SOURCE/'depth_review.json').read_text())
strata={r['snapshot']:r['color_pixel_coverage']>=.5 for r in old['frames']}
rows=[]
for line in (CAPTURE/'observer.jsonl').read_text().splitlines():
    item=json.loads(line);i=item['snapshot']
    rgb_path=CAPTURE/'evidence'/f'{i:04d}_rgb.png';dep_path=CAPTURE/'evidence'/f'{i:04d}_depth.png'
    rgb=cv2.imread(str(rgb_path));depth=cv2.imread(str(dep_path),cv2.IMREAD_UNCHANGED)
    kd=np.array(item['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
    mask,contour=color_mask(rgb,PARAMS)
    row={'snapshot':i,'prior_high_support':strata[i],
         'raw_rgb_SHA256':hashlib.sha256(rgb_path.read_bytes()).hexdigest(),
         'raw_depth_SHA256':hashlib.sha256(dep_path.read_bytes()).hexdigest(),
         'surface_slab_m':[.425,.450],'comparison':{}}
    for label,c in [('unchanged_detector',configured),('actual_camera_internal_TF',live)]:
        uv,pixel,valid=project_measured(depth,kd,c,(rgb.shape[1],rgb.shape[0]),PARAMS)
        selected=valid&(depth>=425)&(depth<=450)
        px=pixel[selected]
        hit=np.zeros(mask.shape,np.uint8)
        if len(px):hit[px[:,1],px[:,0]]=1
        inside=(mask>0)&(hit>0)
        row['comparison'][label]={'native_slab_points':int(selected.sum()),
            'native_slab_points_inside_cube_mask':int((mask[px[:,1],px[:,0]]>0).sum()),
            'unique_slab_pixels_inside_cube_mask':int(inside.sum()),
            'cube_pixels':int((mask>0).sum()),
            'cube_mask_coverage_by_slab':float(inside.sum()/max(1,(mask>0).sum()))}
    rows.append(row)
summary={}
for label in ['unchanged_detector','actual_camera_internal_TF']:
    summary[label]={}
    for name,group in [('all_30',rows),('prior_high_support_10',[r for r in rows if r['prior_high_support']])]:
        vals=[r['comparison'][label]['cube_mask_coverage_by_slab'] for r in group]
        summary[label][name]={'frames':len(vals),'min':min(vals),'median':float(np.median(vals)),'max':max(vals)}
report={'offline_only':True,'production_changed':False,'surface_slab_chosen_from_prior_published_surface_not_optimized':True,
        'all_30_included':True,'summary':summary,'frames':rows,
        'scope':'Immutable pair01 local cube/surface correspondence; not an absolute depth or TCP calibration. Prior high-support stratum was defined with the old registration and is explicitly selection-biased; all-30 results are also reported.',
        'conclusion':'Do not substitute the observed internal TF for detector registration merely because it is published. Compare actual image correspondence before changing any frozen depth consumer.'}
with (ROOT/'recorded_rgbd_direction_check.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps(summary,indent=2))
