"""Offline sixth A/motion archive; 20 diagnostic frames, not fitting samples."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
import numpy as np
REPO=Path('/mnt/hgfs/ub');BASE=Path('/home/johnwick/brain_robot_logs')
ROOT=BASE/'new_pair07_A._lk19a5t';MOTION=BASE/'new_pair07_release_observe.muxfhlfs'
FAILS=[BASE/n for n in ['new_pair07_release_observe.ij_8_3nq','new_pair07_release_observe.64k5sjro','new_pair07_release_observe.t6rezhgb']]
OUT=ROOT/'publish'
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle
from review_calibration_capture import temporal_summary
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT.mkdir(exist_ok=False)
s=ROOT/'session';b=ROOT/'portable_all60';exe=load(s/'execution.json');e=load(MOTION/'execution_session.json')
assert exe['raw_acquisition_complete'] and exe['all_owned_sources_exited'] and exe['within_camera_budget']
assert e['opened'] and e['observe_reached'] and e['all_owned_sources_exited'] and e['error'] is None
cap=load(s/'capture/summary.json');q=load(ROOT/'quality/report.json')
assert cap['saved_frames']==60 and cap['stop_reason'] is None
assert q['summary']['good_top_frames']==q['summary']['face_quality_candidates']==0
assert load(s/'source_SHA_before.json')==load(s/'source_SHA_after.json')
for p,v in load(s/'source_SHA_before.json').items():assert sha(Path(p))==v
before=load(s/'can_before.json');after=load(s/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
verify_bundle(b,load(b/'manifest.json'))
rows=[json.loads(l) for l in (b/'capture/observer.jsonl').read_text().splitlines() if l]
assert len(rows)==60 and not np.ptp([r['q_rad'] for r in rows],axis=0).any()
indices=np.rint(np.linspace(0,59,20)).astype(int).tolist();chosen=[rows[i] for i in indices]
ids={r['snapshot'] for r in chosen};portable=OUT/'portable_diagnostic20'
(portable/'capture/evidence').mkdir(parents=True)
for name in ['sdk_samples.json','sdk_review.json','camera_factory_current.json','detector_config.yaml','robot_task_config_snapshot.yaml','calibration.json']:
 shutil.copyfile(b/name,portable/name)
for row in chosen:
 assert row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
 for image in row['images'].values():
  rel=Path(image['path']);assert not rel.is_absolute() and '..' not in rel.parts
  source=b/'capture'/rel;assert sha(source)==image['sha256']
  shutil.copyfile(source,portable/'capture'/rel)
(portable/'capture/observer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in chosen))
shutil.copyfile(b/'capture/summary.json',portable/'capture/source_capture_summary.json')
put(portable/'capture/summary.json',{'derived_diagnostic_subset':True,'source_saved_frames':60,'saved_frames':20,
 'source_indices_zero_based':indices,'source_summary':'source_capture_summary.json',
 'qualified_face_frames':0,'qualified_top_frames':0,'fitting_input':False})
r=load(b/'depth_review.json');r['frames']=[f for f in r['frames'] if f['snapshot'] in ids]
r['temporal']=temporal_summary(r['frames']);r['high_support_temporal']=temporal_summary([])
r['analysis_subset']={'source_count':60,'selected_count':20,'only_diagnostic':True,'fit_approved':False,
 'SDK_scope':'Actual post-observation SDK window from this motion session; full-window failure retained, per-image A feedback is authoritative'}
put(portable/'depth_review.json',r)
m=load(b/'manifest.json');m.update(sample_id='new_pair07_attempt01_diagnostic20',
 selection_profile='20 uniform raw diagnostic frames, not complete-face or calibration samples',
 source_frame_count=60,selected_frame_count=20,original_good_top_frames=0,calibration_fit_performed=False)
m['files']=[{'path':p.relative_to(portable).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(portable.rglob('*')) if p.is_file()]
m['file_count']=len(m['files']);m['total_bytes']=sum(f['bytes'] for f in m['files'])
put(portable/'manifest.json',m);verify_bundle(portable,m)
shutil.copytree(ROOT/'quality',OUT/'quality_all60');shutil.copytree(ROOT/'footprint_audit',OUT/'footprint_audit')
for name in ['execution.json','readiness.json','feedback.json','factory.json','can_before.json','can_after.json']:
 shutil.copyfile(s/name,OUT/('A_'+name))
for name in ['execution_session.json','motion_review.json']:
 shutil.copyfile(MOTION/name,OUT/name)
sources=OUT/'executed_sources';sources.mkdir()
for name in ['piper_pair07_release_observe.py','piper_pair07_collect_A.py']:
 shutil.copyfile(Path('/tmp')/name,sources/name)
shutil.copyfile('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair06_after_manual_reset.NBs3LK/original_observe_launch.py',sources/'successful_original_launch_wrapper.py')
shutil.copyfile('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair05_release_observe.wA33Uw/original_observe_launch.py',sources/'obsolete_wrapper_used_in_failed_preparation.py')
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/assessment.json')
production={p:{'expected':v['expected'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
adapter=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
assert sha(adapter)==baseline['deployed_adapter_sha256']
failures=[]
for i,path in enumerate(FAILS):
 f=load(path/'execution_session.json');assert not f['opened'] and not f['observe_reached']
 assert not any(x.get('service') in ['/enable_srv','/piper_jog_adapter/arm','/visual_search_controller/start'] for x in f['events'])
 failures.append({'directory':str(path),'error':f['error'],'all_sources_exited':f['all_owned_sources_exited'],
 'original_SDK_quality':load(path/'sdk_before.json')['quality'],'CAN_after':load(path/'can_after_motion.json'),
 'cause':['Temporary wrapper incorrectly required whole6s static instead of existing contiguous window',
          'Agent reused obsolete launch wrapper; str/substitution AttributeError before nodes, while driver startup TX increased13; no arm/open/start API',
          'Agent-added ending-at-latest extra condition rejected an original79-sample7.830564s static interval; this condition was removed'][i]})
put(OUT/'failed_preparations.json',{'failures':failures,'not_hardware_fault_proven':True,
 'temporary_orchestrator_versions':'Final successful wrapper only is snapshotted; old variants reconstructed from differences described here, not falsely claimed binary-identical snapshots',
 'production_code_changed':False})
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for label,path in [('A',s),('motion_success',MOTION),*[(f'preparation_{i+1}',p) for i,p in enumerate(FAILS)]]:
  for p in sorted(path.rglob('*')):
   if not p.is_file():continue
   assert not p.is_symlink();name=f'{label}/{p.relative_to(path).as_posix()}'
   archive.add(p,arcname=name,recursive=False);entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for item in entries:assert hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True,'raw_deleted':False})
confirmation=load(ROOT/'same_point_confirmation.json') if (ROOT/'same_point_confirmation.json').exists() else None
put(OUT/'same_point_confirmation.json',confirmation or {'operator_post_release_same_point_confirmed':None,'reason':'Question sent; no answer yet. Do not infer same physical point from joint data.'})
motion=load(MOTION/'motion_review.json')
start=next(x['epoch'] for x in e['events'] if x.get('reason')=='START_AUTHORIZED')
finish=next(x['epoch'] for x in e['events'] if x.get('reason')=='OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH')
a={'pair_id':'new_pair07','role':'held_out','B_checkpoint':'8f8eed6','operator_motion_permission_recorded':True,
 'operator_post_release_same_point_confirmed':confirmation.get('operator_post_release_same_point_confirmed') if confirmation else None,
 'raw_A_frames':60,'diagnostic_selected_frames':20,'complete_face_candidates':0,'original_good_top_frames':0,
 'formal_complete_pairs_unchanged':1,'formal_pair_accepted':False,'calibration_performed':False,
 'original_open_feedback':e['opened_feedback'],'observation_feedback':e['observe_feedback'],
 'START_to_REACHED_s':finish-start,'original_prepare_points':6,'original_prepare_duration_s':20,
 'first_command_matches_actual_arm_feedback':True,'stopped_before_SEARCH':True,'no_grasp_reset_disable':True,
 'A_elapsed_s':cap['elapsed_s'],'A_camera_elapsed_s':exe['camera_elapsed_s_including_cleanup'],
 'actual_A_q_rad':rows[0]['q_rad'],'A_q_spread_rad':np.ptp([row['q_rad'] for row in rows],axis=0).tolist(),
 'A_target_depth_samples_all_zero':True,'whole_depth_empty':False,
 'partial_depth_FOV_loss_does_not_explain_all_missing_support':True,'physical_depth_failure_cause_proven':False,
 'read_only_A_CAN_TX_delta':after['tx']-before['before']['tx'],
 'all_owned_sources_exited':True,'production_SHA':production,'deployed_adapter_sha256':sha(adapter),
 'candidate_adapter_deployed':False,'runtime_files_SHA_verified':len(entries),'portable_assets_SHA_verified':len(m['files']),
 'tests_passed':216,'raw_data_deleted':False,'GitHub_pushed':False,
 'next':'Keep current pose/cube, no repeated same-condition60 or motion. Offline compare native-depth/FOV/quality across all six; no fitting/TF deployment from missing centers.'}
put(OUT/'assessment.json',a)
shutil.copyfile('/tmp/pair07_grip_tests.xml',OUT/'junit.xml')
shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:a[k] for k in ['raw_A_frames','diagnostic_selected_frames','original_good_top_frames','START_to_REACHED_s',
 'A_elapsed_s','runtime_files_SHA_verified','portable_assets_SHA_verified','read_only_A_CAN_TX_delta']}))
