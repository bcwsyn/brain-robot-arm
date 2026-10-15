"""Offline packaging and integrity checks after one completed camera session."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import cv2
import numpy as np

BASE=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
SRC=BASE/'new_pair05_continuous_metadata.c2zQ7a'
OUT=BASE/'new_pair05_continuous_metadata_publish'
REPO=Path('/mnt/hgfs/ub')
TEST=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TEST))
from export_calibration_bundle import verify_bundle

def load(p):
    return json.loads(p.read_text())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,obj):
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
for name in ['portable','quality']:
    shutil.copytree(SRC/name,OUT/name)
for name in ['execution.json','depth_controls.json','factory.json','feedback.json','can_before.json','can_after.json']:
    shutil.copyfile(SRC/name,OUT/name)
assets=[]
# Closed raw runtime only; derived portable/review reports are separate assets.
raws=[p for p in sorted(SRC.iterdir()) if p.is_file() and p.name!='review.json']
raws+=sorted((SRC/'capture').rglob('*'))
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
    for p in raws:
        if not p.is_file():
            continue
        assert not p.is_symlink()
        relative=p.relative_to(SRC).as_posix()
        assets.append({'path':relative,'bytes':p.stat().st_size,'sha256':sha(p)})
        archive.add(p,arcname=relative,recursive=False)
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
    assert len(archive.getnames())==len(assets)
    for item in assets:
        assert hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'schema':'piper_closed_runtime_v1','source_runtime':str(SRC),'files':assets,'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'all_archived_original_files_SHA_verified':True})
manifest=load(OUT/'portable/manifest.json')
verify_bundle(OUT/'portable',manifest)
controls=load(SRC/'depth_controls.json')
execution=load(SRC/'execution.json')
summary=load(SRC/'capture/summary.json')
after=load(SRC/'can_after.json')
before=load(SRC/'can_before.json')['before']
per_service={}
for name in controls['fixed_services']:
    rows=[r for r in controls['records'] if r['service']==name]
    replies=[r for r in rows if r['raw_response'] is not None]
    per_service[name]={'requests':sum(r['request_epoch'] is not None for r in rows),'replies':len(replies),
                       'reported_raw_values':dict(Counter(str(r['raw_response']['data']) for r in replies)),
                       'errors':dict(Counter(str(r['error']) for r in rows if r['error'])),
                       'all_reply_success_flags':all(r['raw_response']['success'] for r in replies),
                       'hardware_property_status_verified':False,'physical_units':None}
raw_row=json.loads((SRC/'capture/observer.jsonl').read_text().splitlines()[0])
assert summary['saved_frames']==1
d=cv2.imread(raw_row['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
reference=REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/offline_native_depth_audit'
maskfile=reference/'fixed_native_regions.npz'
m=np.load(maskfile)['reference_footprint']
assert d.dtype==np.uint16 and d.shape==m.shape
same=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'expected':e['expected'],'actual':sha(Path(p))} for p,e in same['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
last=load(SRC/'feedback.json')['actual_last_sample']
assert before['tx']==after['tx']==3070 and after['rx']>before['rx']
assert execution['all_owned_sources_exited'] and execution['within_30s_camera_bound']
assert all(not r['hardware_property_status_verified'] and r['physical_value'] is None for r in controls['records'])
assessment={'schema':'piper_continuous_depth_metadata_diagnostic_v1','motion_commands_sent':False,'camera_setters_called':False,
            'single_camera_session_s':execution['camera_session_upper_bound_s'],'within_30_seconds':True,
            'raw_GET_requests':controls['requests_sent'],'raw_GET_replies':controls['raw_replies_received'],
            'depth_controls':per_service,'native_depth_physical_exposure_gain_verified':False,
            'raw_capture_summary':summary,'paired_frames':1,'good_top_frames':load(OUT/'quality/report.json')['summary']['good_top_frames'],
            'continuous_RGBD_comparison_complete':False,
            'current_blocker':'RGB publisher emitted one frame; original RGB-paired collector saved one of 30 requested frames (rc2), despite continuous depth/Info/feedback arrivals. No restart attempted.',
            'ordering_limit':'This runtime started depth and RGB concurrently. The relation of startup order to RGB one-frame stall is unverified; do not claim a cause.',
            'fixed_native_reference':{'source_mask_sha256':sha(maskfile),'pixels':int(m.sum()),'zeros':int((d[m]==0).sum()),'zero_fraction':float((d[m]==0).mean()),'remaining_samples':int(np.count_nonzero(d[m])),'remaining_samples_median_mm':float(np.median(d[m][d[m]>0])),'remaining_samples_are_not_cube_center':True},
            'actual_q_rad':raw_row['q_rad'],'same_as_previous_observation':raw_row['q_rad']==same['last_fresh_feedback']['q_driver_rad'],
            'last_fresh_feedback':last,'last_feedback_not_current_monitoring':True,
            'CAN_before':before,'CAN_after':after,'new_CAN_TX':after['tx']-before['tx'],
            'all_sources_exited':True,'formal_A_previous_60_not_overwritten':True,'this_is_supplementary_diagnostic_not_new_formal_pair':True,
            'qualified_complete_pairs':1,'physical_centers_still_null':True,'production_five_SHA':production,'GitHub_pushed':False}
put(OUT/'assessment.json',assessment)
put(OUT/'verification.json',{'portable_assets':len(manifest['files']),'raw_archive_files':len(assets),'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'original_and_archived_SHA_verified':True,'all_portable_SHA_verified':True,'camera_bound_passed':True,'logger_fixed_GET_only':True,'logger_test_and_capture_quality_regressions_passed':44,'production_five_SHA_unchanged':True,'no_hardware_or_camera_parameter_write':True,'diagnosis_complete':False,'no_second_camera_session_run':True})
print(json.dumps({'portable_assets':len(manifest['files']),'archive_files':len(assets),'single_session_s':assessment['single_camera_session_s'],'per_service':per_service,'native_reference':assessment['fixed_native_reference'],'paired_frames':1,'good_top_frames':0,'new_CAN_TX':0},indent=2))
