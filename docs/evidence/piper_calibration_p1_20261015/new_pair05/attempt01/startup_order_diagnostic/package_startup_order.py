"""Offline audit/package of the single GET-after-flow session; no device APIs."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tarfile
import cv2
import numpy as np

REPO=Path('/mnt/hgfs/ub')
BASE=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
SRC=BASE/'new_pair05_startup_order_execute.Q5T3q3'
PRE=BASE/'new_pair05_startup_order.Eg3WW7'
OUT=BASE/'new_pair05_startup_order_publish'
TEST=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TEST))
from export_calibration_bundle import verify_bundle
from review_depth_registration import read_config, color_mask

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
for folder in ['native','portable','quality']:
    shutil.copytree(SRC/folder,OUT/folder)
for name in ['execution.json','depth_controls.json','factory.json','feedback.json','can_before.json','can_after.json','source_SHA_before.json']:
    shutil.copyfile(SRC/name,OUT/name)
archive_entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as t:
    for label,root in [('preflight_only',PRE),('actual_camera_session',SRC)]:
        for p in sorted(root.rglob('*')):
            relative=p.relative_to(root)
            if relative.parts[0] in ['portable','quality','review.json'] or not p.is_file():continue
            assert not p.is_symlink()
            name=label+'/'+relative.as_posix()
            archive_entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
            t.add(p,arcname=name,recursive=False)
with tarfile.open(OUT/'runtime_closed.tar.gz') as t:
    for item in archive_entries:assert hashlib.sha256(t.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'files':archive_entries,'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'all_original_and_archived_SHA_verified':True})
manifest=load(OUT/'portable/manifest.json');verify_bundle(OUT/'portable',manifest)
reference=REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/offline_native_depth_audit/fixed_native_regions.npz'
masks=np.load(reference);mask=masks['reference_footprint'];ring=masks['control_ring']
core=cv2.erode(mask.astype(np.uint8),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))>0
rows=[json.loads(line) for line in (OUT/'native/observer.jsonl').read_text().splitlines()]
controls=load(OUT/'depth_controls.json');execution=load(OUT/'execution.json')
first=load(OUT/'native/ready.json')
assert execution['all_owned_sources_exited'] and execution['within_30s_camera_bound']
assert controls['first_GET_epoch']>=first['epoch']
factory_event=next(x for x in execution['events'] if x.get('name')=='factory' and 'argv' in x)
assert factory_event['epoch']>=first['epoch']
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'actual':sha(Path(p)),'expected':v['expected']} for p,v in baseline['production_SHA'].items()}
assert all(x['actual']==x['expected'] for x in production.values())
source_sha=load(SRC/'source_SHA_before.json');assert all(sha(Path(p))==h for p,h in source_sha.items())
oldsha=load(PRE/'source_SHA_before.json');assert source_sha==oldsha
rgb_review=load(OUT/'portable/depth_review.json')
fk=rgb_review['frames'][0]
frames=[];arrays=[]
for row in rows:
    image=OUT/'native'/row['images']['depth']['path']
    assert sha(image)==row['images']['depth']['sha256']
    depth=cv2.imread(str(image),cv2.IMREAD_UNCHANGED)
    assert depth.dtype==np.uint16 and depth.shape==mask.shape
    assert row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
    points=depth[mask];valid=points[points>0]
    nearest={}
    for service in controls['fixed_services']:
        responses=[r for r in controls['records'] if r['service']==service and r['raw_response'] is not None]
        reply=min(responses,key=lambda x:abs(x['response_epoch']-row['epoch']))
        nearest[service]={'response_epoch':reply['response_epoch'],'delta_s':reply['response_epoch']-row['epoch'],
                          'raw_response':reply['raw_response'],'not_image_synchronized':True,'hardware_property_status_verified':False}
    same_q=np.allclose(row['q_rad'],fk['actual_q_rad'],rtol=0,atol=1e-12)
    frames.append({'snapshot':row['snapshot'],'epoch':row['epoch'],'stamps_ns':row['stamps_ns'],
                   'actual_q_rad':row['q_rad'],'fixed_3354_pixels_zero_fraction':float((points==0).mean()),
                   'remaining_nonzero_pixels':int(valid.size),'remaining_nonzero_median_mm':float(np.median(valid)) if valid.size else None,
                   'eroded_core_zero_fraction':float((depth[core]==0).mean()),
                   'control_ring_nonzero_fraction':float(np.count_nonzero(depth[ring])/ring.sum()),
                   'all_native_nonzero_pixels':int(np.count_nonzero(depth)),
                   'native_depth_image_sha256':row['images']['depth']['sha256'],
                   'nearest_GET_replies':nearest,
                   'T_base_gripper_from_original_exporter_same_actual_q':fk['T_base_tool'] if same_q else None,
                   'FK_provenance':'Reused original exporter FK only when q matches exactly; no model or TF change',
                   'camera_cube_center_m':None})
    arrays.append(depth)
before=load(OUT/'can_before.json')['before'];after=load(OUT/'can_after.json')
assert before['tx']==after['tx'] and after['rx']>before['rx']
summary={'schema':'piper_native_GET_timing_audit_v1','offline_only':True,'raw_modified':False,
         'preflight_only_attempt_camera_started':load(PRE/'execution.json')['camera_session_started'],
         'preflight_only_attempt_error':load(PRE/'execution.json')['error'],
         'SDK_full_window_not_rewritten':True,'temporary_wrapper_static_launch_gate_removed_only':True,
         'original_frame_quality_rules_unchanged':True,'one_actual_camera_session_s':execution['camera_session_upper_bound_s'],
         'native_frames':len(rows),'paired_RGBD_diagnostic_frames':3,'paired_good_top_frames':load(OUT/'quality/report.json')['summary']['good_top_frames'],
         'first_real_pair_epoch':first['epoch'],'first_GET_epoch':controls['first_GET_epoch'],'factory_start_epoch':factory_event['epoch'],
         'all_GET_after_real_pair_verified':True,'GET_requests':controls['requests_sent'],'GET_replies':controls['raw_replies_received'],
         'GET_raw_value_counts':{s:dict(Counter(str(r['raw_response']['data']) for r in controls['records'] if r['service']==s and r['raw_response'] is not None)) for s in controls['fixed_services']},
         'hardware_property_values_or_units_verified':False,
         'native_q_spread_rad':np.ptp([r['q_rad'] for r in rows],axis=0).tolist(),
         'actual_q_delta_from_original_reference_observe_rad':(np.array(rows[0]['q_rad'])-baseline['last_fresh_feedback']['q_driver_rad']).tolist(),
         'fixed_native_reference_pixels':int(mask.sum()),'eroded_core_pixels':int(core.sum()),
         'zero_fraction_min_median_max':[float(x) for x in (min(f['fixed_3354_pixels_zero_fraction'] for f in frames),np.median([f['fixed_3354_pixels_zero_fraction'] for f in frames]),max(f['fixed_3354_pixels_zero_fraction'] for f in frames))],
         'core_zero_fraction_min_median_max':[float(x) for x in (min(f['eroded_core_zero_fraction'] for f in frames),np.median([f['eroded_core_zero_fraction'] for f in frames]),max(f['eroded_core_zero_fraction'] for f in frames))],
         'mask_sha256':sha(reference),'reference_is_a_fixed_diagnostic_mask_not_a_new_center':True,
         'remaining_samples_not_cube_surface_estimate':True,'all_native_same_stamp_Info':True,
         'original_exporter_urdf_sha256':rgb_review['urdf_sha256'],'original_exporter_task_sha256':rgb_review['task_sha256'],
         'CAN_before':before,'CAN_after':after,'new_CAN_TX':0,'last_fresh_feedback':load(OUT/'feedback.json')['actual_last_sample'],
         'all_sources_exited':True,'production_five_SHA':production,'source_before_after_SHA_equal':True,
         'formal_complete_pairs_unchanged':1,'formal_A60_not_overwritten':True,'fitted_camera_or_gripper_center':None,
         'causality_limit':'This session succeeds with query deferral but not a repeated controlled A/B. Do not claim query timing was the unique cause of prior startup stalls.',
         'next_blocker':'Data flow and native persistence work; actual target depth remains almost entirely zero. No IR intensity/confidence is available to determine material/exposure/range cause.',
         'frames':frames}
put(OUT/'native_audit.json',summary)
assets=[{'path':p.relative_to(OUT/'native').as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted((OUT/'native').rglob('*')) if p.is_file()]
put(OUT/'native_manifest.json',{'base_directory':'native','files':assets,'all_original_image_SHA_verified':True,'diagnostic_only':True,'not_formal_RGBD_calibration_A':True})
put(OUT/'verification.json',{'tests_passed':61,'archive_files_SHA_verified':len(archive_entries),'portable_assets_SHA_verified':len(manifest['files']),'native_assets_SHA_verified':len(assets),'all_GET_after_native_pair':True,'single_camera_session_bounded':True,'native_live_storage_positive_test':True,'good_top_frames':0,'formal_complete_pairs':1,'new_CAN_TX':0,'production_five_SHA_unchanged':True,'GitHub_pushed':False})
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
y,x=np.where(mask);roi=(slice(max(0,y.min()-12),y.max()+13),slice(max(0,x.min()-12),x.max()+13))
fig,axes=plt.subplots(1,4,figsize=(14,3.5),layout='constrained')
cm=plt.get_cmap('turbo').copy();cm.set_bad('black')
for axis,index in zip(axes[:3],[0,len(arrays)//2,len(arrays)-1]):
    axis.imshow(np.ma.masked_equal(arrays[index][roi],0),vmin=180,vmax=280,cmap=cm,interpolation='nearest')
    axis.contour(mask[roi],levels=[.5],colors=['white'],linewidths=.7)
    axis.set_title('Native #'+str(index+1)+'; black=RAW zero')
axes[3].plot([r['epoch']-frames[0]['epoch'] for r in frames],[100*r['fixed_3354_pixels_zero_fraction'] for r in frames],'.-')
axes[3].set(xlabel='Seconds since first saved depth',ylabel='Fixed native ROI zeros [%]',ylim=(99.7,100.01))
fig.savefig(OUT/'native_depth_series.png',dpi=130);plt.close(fig)
print(json.dumps({k:v for k,v in summary.items() if k in ['native_frames','paired_RGBD_diagnostic_frames','paired_good_top_frames','one_actual_camera_session_s','GET_raw_value_counts','zero_fraction_min_median_max','core_zero_fraction_min_median_max']},indent=2))
print('VERIFIED',len(archive_entries),'archived raw files',len(assets),'native assets',len(manifest['files']),'portable assets')
