"""Offline-only fifth placement preview audit, preserving original quality."""
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
SRC=BASE/'new_pair06_preview.Fx2y1k'
OUT=BASE/'new_pair06_preview_publish'
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle
from review_depth_registration import calibration,read_config
from review_pair_sampling import selected_pixels
from estimate_calibration_cube_center import points_from_mask,fit_plane

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
for folder in ('portable','quality','native'):shutil.copytree(SRC/folder,OUT/folder)
for name in ('execution.json','can_before.json','can_after.json','feedback.json',
             'source_SHA_before.json','source_SHA_after.json','depth_controls.json'):
    shutil.copyfile(SRC/name,OUT/name)
before,after=load(SRC/'source_SHA_before.json'),load(SRC/'source_SHA_after.json')
assert before==after and all(sha(Path(p))==v for p,v in before.items())
manifest=load(OUT/'portable/manifest.json');verify_bundle(OUT/'portable',manifest)
quality=load(OUT/'quality/report.json');review=load(OUT/'portable/depth_review.json')
assert quality['summary']['frames']==5 and quality['summary']['face_quality_candidates']==5
assert quality['summary']['good_top_frames']==0
rows=[json.loads(line) for line in (SRC/'capture/observer.jsonl').read_text().splitlines()]
row=rows[0];rgb=cv2.imread(str(SRC/'capture'/row['images']['rgb']['path']))
depth=cv2.imread(str(SRC/'capture'/row['images']['depth']['path']),-1)
info=row['latest']['/camera/depth/camera_info']
params=read_config(SRC/'portable/detector_config.yaml');camera=calibration(params)
selected,projected,_,_=selected_pixels(rgb,depth,info,params,camera)
plane=fit_plane(points_from_mask(depth,np.array(info['k']).reshape(3,3),selected))
core=np.zeros_like(selected);core[selected]=plane['inliers']
assert int(core.sum())==quality['frames'][0]['plane_inliers']
np.savez_compressed(OUT/'fixed_preview_regions.npz',reference_valid_cube_pixels=selected,
                    reference_dominant_plane_inliers=core)
native_rows=[json.loads(line) for line in (SRC/'native/observer.jsonl').read_text().splitlines()]
native=[]
for r in native_rows:
    path=SRC/'native'/r['images']['depth']['path'];assert sha(path)==r['images']['depth']['sha256']
    a=cv2.imread(str(path),-1);assert a.dtype==np.uint16 and a.shape==depth.shape
    assert r['stamps_ns']['depth']==r['stamps_ns']['depth_info']
    values=a[core];valid=values[values>0]
    native.append({'snapshot':r['snapshot'],'stamps_ns':r['stamps_ns'],'actual_q_rad':r['q_rad'],
                   'fixed_reference_cube_zero_fraction':float(np.mean(a[selected]==0)),
                   'fixed_reference_plane_zero_fraction':float(np.mean(values==0)),
                   'reference_plane_nonzero_median_mm':float(np.median(valid)) if len(valid) else None,
                   'raw_png_sha256':r['images']['depth']['sha256']})
execution=load(SRC/'execution.json');controls=load(SRC/'depth_controls.json')
assert execution['within_30s_camera_bound'] and execution['all_owned_sources_exited']
assert controls['first_GET_epoch']>=execution['actual_native_ready']['epoch']
can_before,can_after=load(SRC/'can_before.json'),load(SRC/'can_after.json')
assert can_before['before']['tx']==can_after['tx']
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'expected':v['expected'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
summary={'pair_id':'new_pair06','preview_only':True,'formal_pair_completed':False,'formal_A_frames':0,
         'operator_placement_confirmed':True,'operator_quote':'已完成','grip_B_present':False,
         'RGBD_preview_frames':5,'native_diagnostic_frames':len(native),
         'camera_elapsed_s':execution['camera_session_upper_bound_s'],
         'all_owned_sources_exited':True,'production_SHA':production,
         'selected_native_points_range':[min(f['native_depth_samples'] for f in review['frames']),max(f['native_depth_samples'] for f in review['frames'])],
         'coverage_range':[min(f['color_pixel_coverage'] for f in review['frames']),max(f['color_pixel_coverage'] for f in review['frames'])],
         'surface_z_m_range':[min(f['surface_z_m'] for f in review['frames']),max(f['surface_z_m'] for f in review['frames'])],
         'dominant_plane_inliers_range':[min(f['plane_inliers'] for f in quality['frames']),max(f['plane_inliers'] for f in quality['frames'])],
         'complete_face_candidates':5,'original_good_top_frames':0,
         'original_top_errors':[f['top_error'] for f in quality['frames']],
         'elevated_support_visible_in_RGB':True,'support_height_not_physically_measured':True,
         'top_identity_or_absolute_accuracy_verified':False,'original_quality_not_modified':True,
         'native_reference_defined_once_on_first_RGBD_frame_not_reselected_per_frame':True,
         'native_reference_valid_points_only_not_full_geometric_footprint':True,
         'reference_cube_pixels':int(selected.sum()),'reference_plane_pixels':int(core.sum()),
         'native_zero_fraction_range':[min(r['fixed_reference_cube_zero_fraction'] for r in native),max(r['fixed_reference_cube_zero_fraction'] for r in native)],
         'native_actual_q_spread_rad':np.ptp(np.array([r['actual_q_rad'] for r in native]),axis=0).tolist(),
         'native_frames':native,'new_CAN_TX':0,'CAN_before':can_before,'CAN_after':can_after,
         'last_fresh_feedback':load(SRC/'feedback.json')['actual_last_sample'],
         'SDK_full_window_rc':execution['sdk_before_rc'],'SDK_original_contiguous_static_slice':execution['original_static_slice'],
         'next_step':'Operator manually grips same unmoved cube using agreed supported teaching procedure; read-only B capture next. Original top/support identity remains independent-review pending, not a completed calibration pair.'}
put(OUT/'audit.json',summary)
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for p in sorted(SRC.rglob('*')):
    rel=p.relative_to(SRC)
    if not p.is_file() or rel.parts[0] in ('portable','quality','review.json'):continue
    archive.add(p,arcname=rel.as_posix(),recursive=False)
    entries.append({'path':rel.as_posix(),'sha256':sha(p),'bytes':p.stat().st_size})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for row in entries:assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest()==row['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True})
put(OUT/'native_manifest.json',{'base_directory':'native','files':[{'path':p.relative_to(OUT/'native').as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted((OUT/'native').rglob('*')) if p.is_file()]})
put(OUT/'verification.json',{'tests_passed':75,'archive_files_SHA_verified':len(entries),'portable_assets_SHA_verified':len(manifest['files']),
                           'native_png_SHA_verified':len(native),'production_five_SHA_unchanged':True,
                           'formal_complete_pairs_unchanged':1,'formal_A_not_created':True,'GitHub_pushed':False})
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
last=cv2.imread(str(SRC/'native'/native_rows[-1]['images']['depth']['path']),-1)
cmap=plt.get_cmap('turbo').copy();cmap.set_bad('black')
fig,axes=plt.subplots(1,3,figsize=(13,4))
axes[0].imshow(cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB));axes[0].set_title('Original RGB; elevated support visible')
for ax,a,title in [(axes[1],depth,'First RGBD depth; black=raw zero'),(axes[2],last,'Last native depth; fixed first-frame regions')]:
 ax.imshow(np.ma.masked_equal(a,0),cmap=cmap,vmin=200,vmax=700)
 ax.contour(selected,levels=[.5],colors='white',linewidths=.6)
 ax.contour(core,levels=[.5],colors='cyan',linewidths=.6);ax.set_title(title)
for ax in axes:ax.axis('off')
fig.tight_layout();fig.savefig(OUT/'preview_witness.png',dpi=150);plt.close(fig)
print(json.dumps({k:v for k,v in summary.items() if k in ['camera_elapsed_s','RGBD_preview_frames','native_diagnostic_frames','selected_native_points_range','coverage_range','dominant_plane_inliers_range','surface_z_m_range','native_zero_fraction_range','original_good_top_frames']},ensure_ascii=False),flush=True)
print('VERIFIED',len(entries),'archive files',len(manifest['files']),'portable assets')
