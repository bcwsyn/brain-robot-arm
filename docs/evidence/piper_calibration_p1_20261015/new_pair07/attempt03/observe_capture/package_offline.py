"""Offline package of a new stationary A, including the source-ownership failure."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
import numpy as np

REPO=Path('/mnt/hgfs/ub')
ROOT=Path('/home/johnwick/brain_robot_logs/new_pair07_attempt03_A.9r_fp1bb')
FAILED=Path('/home/johnwick/brain_robot_logs/new_pair07_attempt03_A.6lpjbicx')
TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import verify_bundle
from review_calibration_capture import temporal_summary
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT=ROOT/'publish';OUT.mkdir(exist_ok=False)
s=ROOT/'session';b=ROOT/'portable_all60';q=load(ROOT/'quality/report.json')
e=load(s/'execution.json');f=load(FAILED/'session/execution.json')
assert e['raw_acquisition_complete'] and e['all_owned_sources_exited'] and e['within_camera_budget']
assert not f['formal_capture_started'] and f['all_owned_sources_exited']
assert load(ROOT/'production_SHA_before.json')==load(ROOT/'production_SHA_after.json')
for path,digest in load(ROOT/'production_SHA_before.json').items():assert sha(Path(path))==digest
assert load(s/'source_SHA_before.json')==load(s/'source_SHA_after.json')
before=load(s/'can_before.json');after=load(s/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
verify_bundle(b,load(b/'manifest.json'))
rows=[json.loads(line) for line in (b/'capture/observer.jsonl').read_text().splitlines() if line]
assert len(rows)==len(q['frames'])==60
assert not np.ptp([r['q_rad'] for r in rows],axis=0).any()
good={r['snapshot'] for r in q['frames'] if r['good_top_frame']}
eligible=[i for i,r in enumerate(rows) if r['snapshot'] in good] if len(good)>=20 else list(range(60))
indices=[eligible[i] for i in np.rint(np.linspace(0,len(eligible)-1,20)).astype(int)]
assert len(set(indices))==20
chosen=[rows[i] for i in indices];ids={r['snapshot'] for r in chosen}
portable=OUT/('portable_good20' if len(good)>=20 else 'portable_review20')
(portable/'capture/evidence').mkdir(parents=True)
for name in ['sdk_samples.json','sdk_review.json','camera_factory_current.json','detector_config.yaml',
             'robot_task_config_snapshot.yaml','calibration.json']:
 shutil.copyfile(b/name,portable/name)
for row in chosen:
 assert row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
 for image in row['images'].values():
  rel=Path(image['path']);assert not rel.is_absolute() and '..' not in rel.parts
  assert sha(b/'capture'/rel)==image['sha256'];shutil.copyfile(b/'capture'/rel,portable/'capture'/rel)
(portable/'capture/observer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in chosen))
shutil.copyfile(b/'capture/summary.json',portable/'capture/source_capture_summary.json')
put(portable/'capture/summary.json',{'derived_subset':True,'source_saved_frames':60,'saved_frames':20,
 'source_indices_zero_based':indices,'selected_original_good_top_frames':len(ids&good),'fitting_input':False,
 'source_summary':'source_capture_summary.json','B_pending':True})
review=load(b/'depth_review.json');review['frames']=[r for r in review['frames'] if r['snapshot'] in ids]
review['temporal']=temporal_summary(review['frames']);review['high_support_temporal']=temporal_summary([
 r for r in review['frames'] if r['color_pixel_coverage']>=.5])
review['analysis_subset']={'source_count':60,'selected_count':20,'original_good_top_count':len(ids&good),
 'fit_approved':False,'SDK_scope':'Actual new six-second passive metadata after all camera sources exited; each image retains independent actual JointState'}
put(portable/'depth_review.json',review)
m=load(b/'manifest.json');m.update(sample_id='new_pair07_attempt03_selected20',source_frame_count=60,
 selected_frame_count=20,original_good_top_frames=len(ids&good),B_pending=True,
 selection_profile='Uniform selection among original good-top frames' if len(good)>=20 else 'Uniform diagnostic original frames; not20 good')
m['files']=[{'path':p.relative_to(portable).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(portable.rglob('*')) if p.is_file()]
m['file_count']=len(m['files']);m['total_bytes']=sum(v['bytes'] for v in m['files'])
put(portable/'manifest.json',m);verify_bundle(portable,m)
shutil.copytree(ROOT/'quality',OUT/'quality_all60')
for name in ['execution.json','readiness.json','feedback.json','factory.json','can_before.json','can_after.json','source_SHA_before.json','source_SHA_after.json']:
 shutil.copyfile(s/name,OUT/('A_'+name))
for name in ['production_SHA_before.json','production_SHA_after.json','review_execution.json','junit.xml']:
 shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile(FAILED/'preview_source_replacement.json',OUT/'preview_source_replacement.json')
put(OUT/'initial_source_conflict.json',{'original_failed_session':str(FAILED),
 'received':load(FAILED/'session/readiness.json')['received'],'error':f['error'],'formal_capture_started':False,
 'extra_color_failed':'Agent started original coordinator despite existing user preview PID89463; duplicate source could not open video0',
 'existing_preview_received_RGB_in20s':0,'not_hardware_or_CAN_fault_proven':True,
 'recovery':'End exact stale camera-only PID, preserve failure, one original single-source session; no DDS/backend/config changes',
 'all_owned_sources_exited':f['all_owned_sources_exited']})
sources=OUT/'executed_sources';sources.mkdir()
for name in ['piper_pair07_attempt03_collect_A.py','piper_pair07_attempt03_review.py']:
 shutil.copyfile(Path('/tmp')/name,sources/name)
for name in ['capture_calibration_session.py','collect_calibration_sdk.py','review_calibration_capture.py','export_calibration_bundle.py','calibration_p0_quality.py']:
 shutil.copyfile(TESTS/name,sources/name)
entries=[];aliases=[]
# Source PNG bytes are already present in portable_all60; archive them once.
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as tar:
 for label,path in [('session',s),('portable_all60',b),('first_source_conflict',FAILED),
                    ('sdk_post_capture.json',ROOT/'sdk_post_capture.json'),('coordinator.log',ROOT/'coordinator.log')]:
  for p in ([path] if path.is_file() else sorted(v for v in path.rglob('*') if v.is_file())):
   assert not p.is_symlink();name=label if path.is_file() else label+'/'+p.relative_to(path).as_posix()
   if label=='session' and p.parent==s/'capture/evidence' and p.suffix=='.png':
    target='portable_all60/capture/evidence/'+p.name
    assert sha(p)==sha(b/'capture/evidence'/p.name)
    aliases.append({'original_path':name,'identical_bytes_member':target,'sha256':sha(p)});continue
   tar.add(p,arcname=name,recursive=False);entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as tar:
 for entry in entries:assert hashlib.sha256(tar.extractfile(entry['path']).read()).hexdigest()==entry['sha256']
 for alias in aliases:assert hashlib.sha256(tar.extractfile(alias['identical_bytes_member']).read()).hexdigest()==alias['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,
 'identical_raw_image_aliases':aliases,'all_SHA_verified':True,'raw_deleted':False})
d=load(ROOT/'depth_review.json');sdk=load(ROOT/'sdk_post_capture.json');counts=[r['top_plane_inliers'] for r in q['frames']]
a={'pair_id':'new_pair07','attempt':3,'role':'held_out','operator_new_placement_confirmed':True,
 'raw_A_frames':60,'original_good_top_frames':len(good),'original_good_snapshot_ids':sorted(good),
 'selected_frames':20,'selected_good_frames':len(ids&good),'original_twenty_good_frames_met':len(good)>=20,
 'new_B_captured':False,'same_point_with_new_B_confirmed':None,'formal_pair_approved':False,
 'old_B_reuse_allowed':False,'fit_performed':False,'TF_deployed':False,'GitHub_pushed':False,
 'native_top_inliers':{'min':min(counts),'median':float(np.median(counts)),'max':max(counts)},
 'surface_depth_temporal':d['temporal'],'actual_A_q_rad':rows[0]['q_rad'],
 'A_q_spread_rad':np.ptp([r['q_rad'] for r in rows],axis=0).tolist(),
 'normal_statistics':q['summary']['top_plane_normal_statistics'],'SDK_quality':sdk['quality'],
 'last_enabled_historical':sdk['samples'][-1]['enabled'],'last_gripper_mm_historical':sdk['samples'][-1]['gripper_mm'],
 'capture_elapsed_s':e['capture_summary']['elapsed_s'],'camera_elapsed_s':e['camera_elapsed_s_including_cleanup'],
 'read_only_CAN_TX_delta':after['tx']-before['before']['tx'],'CAN_RX_before':before['before']['rx'],'CAN_RX_after':after['rx'],
 'all_owned_sources_exited':True,'production_unchanged':True,'candidate_adapter_deployed':False,
 'motion_enable_arm_gripper_reset_disable_commands_sent':False,'CAN_recovery':False,
 'runtime_files_SHA_verified':len(entries),'raw_image_aliases_SHA_verified':len(aliases),
 'portable_assets_SHA_verified':len(m['files']),'tests_passed':81,'raw_data_deleted':False,
 'next':'Operator hand-grip at unchanged position, then receive-only new B' if len(good)>=20 else 'Offline inspect quality; no identical blind60 retry or manual grip yet'}
put(OUT/'assessment.json',a);shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:a[k] for k in ['raw_A_frames','original_good_top_frames','native_top_inliers','runtime_files_SHA_verified','portable_assets_SHA_verified']}))
