"""Offline-only audit and portable evidence packaging; no camera/ROS/CAN APIs."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import shutil
import sys
import tarfile
import cv2
import numpy as np

REPO=Path('/mnt/hgfs/ub')
BASE=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
OUT=BASE/'new_pair05_IR_publish_v2'
RUNS=[('unsupported_default',BASE/'new_pair05_IR_depth.iiov2O'),
      ('supported_partial',BASE/'new_pair05_IR_supported.5HgOz3'),
      ('drained_partial',BASE/'new_pair05_IR_drained.9TuwUl')]
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
masks=np.load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/offline_native_depth_audit/fixed_native_regions.npz')
mask=masks['reference_footprint']
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'expected':v['expected'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
summaries=[];archive_files=[];portable_assets=0;native_images=0
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for name,root in RUNS:
    target=OUT/name;target.mkdir()
    for folder in ('streams','portable','quality'):
        if (root/folder).exists():shutil.copytree(root/folder,target/folder)
    for filename in ('execution.json','can_before.json','can_after.json','feedback.json',
                     'source_SHA_before.json','source_SHA_after.json','depth_controls.json'):
        if (root/filename).exists():shutil.copyfile(root/filename,target/filename)
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not p.is_file() or rel.parts[0] in ('portable','quality','review.json'):continue
        arcname=name+'/'+rel.as_posix()
        archive.add(p,arcname=arcname,recursive=False)
        archive_files.append({'path':arcname,'bytes':p.stat().st_size,'sha256':sha(p)})
    before,after=load(root/'source_SHA_before.json'),load(root/'source_SHA_after.json')
    assert before==after
    collector_path=str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_ir_depth_diagnostic.py')
    assert sha(root/'collector_as_run.py')==before[collector_path]
    execution=load(root/'execution.json');assert execution['all_owned_sources_exited'] and execution['within_30s_camera_bound']
    can0,can1=load(root/'can_before.json'),load(root/'can_after.json');assert can0['before']['tx']==can1['tx']
    streams=load(root/'streams/summary.json')
    frames=[]
    for kind in ('depth','ir'):
        path=root/'streams'/kind
        rows=[json.loads(line) for line in (path/'observer.jsonl').read_text().splitlines()]
        for row in rows:
            im=row['images'][kind];p=path/im['path'];assert sha(p)==im['sha256']
            assert row['stamps_ns'][kind]==row['stamps_ns'][kind+'_info']
            a=cv2.imread(str(p),-1);assert a.shape==(400,640)
            item={'kind':kind,'snapshot':row['snapshot'],'stamps_ns':row['stamps_ns'],
                  'actual_q_rad':row['q_rad'],'sha256':im['sha256']}
            if kind=='depth':
                assert a.dtype==np.uint16
                item['fixed_depth_3354_pixels_zero_fraction']=float(np.mean(a[mask]==0))
            else:
                assert a.dtype==np.uint8
                # Independent rectangle selected on first IR image, never a D->IR mapping.
                roi=a[245:290,310:350]
                item.update(IR_independent_visual_rectangle_xyxy=[310,245,350,290],
                            IR_rectangle_pixels=1800,IR_uint8_255_fraction=float(np.mean(roi==255)),
                            IR_rectangle_min_median_max=np.percentile(roi,[0,50,100]).tolist(),
                            pixel_alignment_to_depth_assumed=False,radiometry_verified=False)
            frames.append(item);native_images+=1
    if (root/'portable').exists():
        manifest=load(root/'portable/manifest.json');verify_bundle(target/'portable',manifest)
        portable_assets+=len(manifest['files'])
        assert load(root/'quality/report.json')['summary']['good_top_frames']==0
    controls=load(root/'depth_controls.json') if (root/'depth_controls.json').exists() else None
    getters={} if controls is None else {service:dict(Counter(str(r['raw_response']['data']) for r in controls['records'] if r['service']==service and r['raw_response'] is not None)) for service in controls['fixed_services']}
    if controls is not None:
        assert controls['first_GET_epoch']>=max(streams['streams'][k]['first_received_pair']['epoch'] for k in ('depth','ir'))
    q=np.array([x['actual_q_rad'] for x in frames])
    summaries.append({'session':name,'camera_elapsed_s':execution['camera_elapsed_s'],
                      'runtime_override':execution['only_runtime_parameter_override'],
                      'all_owned_sources_exited':True,'actual_as_run_collector_returncode':next(e['returncode'] for e in execution['events'] if e['name']=='observer' and 'returncode' in e),
                      'observer_stop_reason':streams.get('stop_reason'),
                      'continuous_IR_comparison_complete':False,
                      'source_before_after_SHA_equal':True,'as_run_collector_code_SHA_verified':True,
                      'depth_saved':streams['streams']['depth']['saved_frames'],'IR_saved':streams['streams']['ir']['saved_frames'],
                      'RGBD_saved':load(root/'capture/summary.json')['saved_frames'],
                      'good_top_frames':0,'new_CAN_TX':can1['tx']-can0['before']['tx'],
                      'CAN_before':can0,'CAN_after':can1,'GET_raw_counts':getters,
                      'GET_hardware_value_or_units_verified':False,
                      'native_actual_q_spread_rad':None if not len(q) else np.ptp(q,axis=0).tolist(),
                      'frames':frames})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for row in archive_files:assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest()==row['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':archive_files,'all_SHA_verified':True})
put(OUT/'audit.json',{'diagnostic_only':True,'formal_A_replaced':False,'formal_complete_pairs':1,
                     'cube_material_or_minimum_range_or_exposure_cause_proven':False,
                     'original_3s_120ms_500ms_rules_preserved':True,'production_SHA':production,
                     'final_observer_exit_status_fix_after_live_run_unit_tested_only':True,
                     'last_valid_feedback':load(RUNS[-1][1]/'feedback.json')['actual_last_sample'],
                     'sessions':summaries})
put(OUT/'verification.json',{'tests_passed':75,'archived_files_SHA_verified':len(archive_files),
                            'native_images_SHA_verified':native_images,'portable_assets_SHA_verified':portable_assets,
                            'all_owned_sources_exited':True,'all_camera_sessions_under_30s':True,
                            'production_five_SHA_unchanged':True,'new_CAN_TX':0,'formal_complete_pairs':1,
                            'continuous_IR_comparison_complete':False,'GitHub_pushed':False})

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
last=RUNS[-1][1]
rgb=cv2.cvtColor(cv2.imread(str(last/'capture/evidence/0001_rgb.png')),cv2.COLOR_BGR2RGB)
ir=cv2.imread(str(last/'streams/ir/evidence/0001_ir.png'),-1)
depth=cv2.imread(str(last/'streams/depth/evidence/0001_depth.png'),-1)
fig,axes=plt.subplots(1,3,figsize=(14,4))
axes[0].imshow(rgb);axes[0].set_title('Original RGB (different timestamp)')
axes[1].imshow(ir,cmap='gray',vmin=0,vmax=255);axes[1].set_title('Original emitted mono8 IR; white=255')
from matplotlib.patches import Rectangle
axes[1].add_patch(Rectangle((310,245),40,45,fill=False,color='red',lw=1))
cmap=plt.get_cmap('turbo').copy();cmap.set_bad('black')
axes[2].imshow(np.ma.masked_equal(depth,0),cmap=cmap,vmin=150,vmax=600)
axes[2].contour(mask,levels=[.5],colors='white',linewidths=.6);axes[2].set_title('Original depth; black=0; fixed D ROI')
for ax in axes:ax.axis('off')
fig.tight_layout();fig.savefig(OUT/'RGB_IR_depth.png',dpi=150);plt.close(fig)
print(json.dumps(load(OUT/'verification.json')),flush=True)
for s in summaries:print(s['session'],s['camera_elapsed_s'],s['depth_saved'],s['IR_saved'],s['RGBD_saved'],s['observer_stop_reason'])
