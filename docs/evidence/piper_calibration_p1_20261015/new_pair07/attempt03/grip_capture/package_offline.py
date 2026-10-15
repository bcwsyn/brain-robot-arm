"""Offline new-B packet and immutable A/B links; no fit, ROS or controls."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
import numpy as np
import yaml
REPO=Path('/mnt/hgfs/ub')
RUN=Path('/home/johnwick/brain_robot_logs/new_pair07_preview.hbtyou_k')
ROOT=Path('/home/johnwick/brain_robot_logs/new_pair07_attempt03_B.rblyf2rg')
A=REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt03/observe_capture'
TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import verify_bundle
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT=ROOT/'publish';OUT.mkdir(exist_ok=False)
e=load(RUN/'execution.json');sdk=load(RUN/'sdk.json');b=RUN/'portable';review=load(b/'depth_review.json')
assert e['error'] is None and e['all_owned_sources_exited'] and e['within_35s_camera_bound']
assert sdk['quality']['static_three_seconds_and_thirty_samples'] and e['SDK_full_window_rc']==0
assert e['saved_frames']==5 and load(RUN/'capture/summary.json')['stop_reason'] is None
assert load(RUN/'source_SHA_before.json')==load(RUN/'source_SHA_after.json')
for p,h in load(RUN/'source_SHA_before.json').items():assert sha(Path(p))==h
assert load(ROOT/'production_SHA_before.json')==load(ROOT/'production_SHA_after.json')==load(A/'production_SHA_before.json')
for p,h in load(ROOT/'production_SHA_after.json').items():assert sha(Path(p))==h
before=load(RUN/'can_before.json');after=load(RUN/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
actual=[r for r in sdk['samples'] if r['fresh_after_passive_connection']]
q=actual[-1]['q_driver_rad'];assert not np.ptp([r['q_driver_rad'] for r in actual],axis=0).any()
assert all(row['actual_q_rad']==q for row in review['frames'])
assert not any(review['joint_spread_rad'])
verify_bundle(b,load(b/'manifest.json'));verify_bundle(A/'portable_good20',load(A/'portable_good20/manifest.json'))
shutil.copytree(b,OUT/'portable')
for name in ['execution.json','can_before.json','can_after.json','feedback.json','readiness.json','source_SHA_before.json','source_SHA_after.json']:
 shutil.copyfile(RUN/name,OUT/name)
for name in ['B_execution.json','production_SHA_before.json','production_SHA_after.json','junit.xml']:
 shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile('/tmp/piper_pair07_attempt03_collect_B.py',OUT/'executed_collect_B.py')
shutil.copyfile(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/executed_preview.py',OUT/'executed_original_capture.py')
confirmation={'pair_id':'new_pair07','attempt':3,'operator_completion_quote':'已完成',
 'reply_context':'Asked to keep cube/mat at A position and manually grip on table without lift',
 'explicit_same_point_confirmed':None,'actual_contact_explicitly_confirmed':None,
 'still_on_table_explicitly_confirmed':None,'physical_contact_verified_by_sdk':False,
 'question_sent':True,'status':'Awaiting precise A-to-B same-point/contact confirmation; never infer zero movement from RGB or joint data'}
put(OUT/'operator_confirmation.json',confirmation)
ar=load(A/'portable_good20/depth_review.json');aq=load(A/'quality_all60/report.json')
ids={f['snapshot'] for f in ar['frames']};cal=load(A/'portable_good20/calibration.json')
assert cal==load(b/'calibration.json') and ar['urdf_sha256']==review['urdf_sha256']
rot=np.asarray(cal['depth_to_color']['R_row_major']).reshape(3,3);trans=np.asarray(cal['depth_to_color']['t_m'])
centres=[]
for frame in aq['frames']:
 if frame['snapshot'] not in ids:continue
 assert frame['good_top_frame']
 top=frame['top_candidate'];face=np.asarray(top['face_center_depth_m'])
 normal=np.asarray(top['outward_normal_depth']);table=np.asarray(frame['top_plane_audit']['table_normal_depth_A'])
 if table@normal<0:table=-table
 via_face=rot@(face-.0145*normal)+trans;via_table=rot@(face-.0145*table)+trans
 assert np.allclose(via_face,top['cube_center_color_m'],atol=1e-12,rtol=0)
 centres.append({'snapshot':frame['snapshot'],'frame':'camera_color_optical_frame',
  'top_normal_center_candidate_m':via_face.tolist(),'table_normal_sensitivity_candidate_m':via_table.tolist(),
  'normal_choice_difference_m':float(np.linalg.norm(via_face-via_table)),
  'source_stamps_ns':frame['stamps_ns'],'raw_image_sha256':frame['raw_image_sha256']})
values=np.asarray([r['top_normal_center_candidate_m'] for r in centres]);median=np.median(values,axis=0)
put(OUT/'A_center_normal_sensitivity.json',{'offline_only':True,'fit_performed':False,'reference':'candidate geometric centre, not raw surface',
 'nominal_edge_mm_approximate':29,'caliper_verified':False,'input_good_frames':20,
 'top_center_componentwise_median_color_m':median.tolist(),
 'max_distance_from_temporal_median_m':float(np.linalg.norm(values-median,axis=1).max()),
 'normal_choice_difference_m_range':[min(v['normal_choice_difference_m'] for v in centres),max(v['normal_choice_difference_m'] for v in centres)],
 'absolute_accuracy_verified':False,'does_not_replace_original_top_normal_or_filter':True,'frames':centres})
task=yaml.safe_load((b/'robot_task_config_snapshot.yaml').read_text())['grasp_lift_executor']['ros__parameters']
inside=all(lo<=v<=hi for lo,v,hi in zip(task['real_trajectory_joint_min'],q,task['real_trajectory_joint_max']))
put(OUT/'paired_sources.json',{'pair_id':'new_pair07','attempt':3,'role':'held_out','A_git_checkpoint':'7399d18',
 'A_evidence_relative_to_repo':str(A.relative_to(REPO)),'A_manifest_sha256':sha(A/'portable_good20/manifest.json'),
 'A_quality_sha256':sha(A/'quality_all60/report.json'),'A_raw_frames':60,'A_original_good_top_frames':60,
 'A_T_base_gripper_base':ar['frames'][0]['T_base_tool'],'B_T_base_gripper_base':review['frames'][0]['T_base_tool'],
 'same_actual_model_sha256':review['urdf_sha256'],'same_factory_calibration':True,
 'B_original_manifest_sha256':sha(b/'manifest.json'),'A_B_same_physical_point_confirmed':None,
 'camera_cube_center_reference':'20 full-top geometric centre candidates in camera_color_optical_frame; not an approved exact centre',
 'gripper_base_cube_center_offset_m':None,'tool_offset_joint_estimation_deferred_to_P2':True,
 'point_pair_formally_approved':False,'fit_performed':False,'production_TF_modified':False,
 'old_B8f8eed6_used':False})
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for label,path in [('raw_capture',RUN),('invocation',ROOT)]:
  for p in sorted(path.rglob('*')):
   rel=p.relative_to(path)
   if not p.is_file() or rel.parts[0] in ('publish','portable'):continue
   assert not p.is_symlink();name=label+'/'+rel.as_posix()
   archive.add(p,arcname=name,recursive=False);entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for item in entries:assert hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True,'raw_deleted':False})
a={'pair_id':'new_pair07','attempt':3,'role':'held_out','B_raw_capture_complete':True,'A_raw_frames':60,'A_original_good_top_frames':60,
 'operator_same_point_confirmed':None,'operator_contact_explicitly_confirmed':None,'formal_pair_approved':False,
 'SDK_quality':sdk['quality'],'actual_q_mdeg':actual[-1]['q_mdeg'],'actual_q_driver_rad':q,
 'enabled_historical':actual[-1]['enabled'],'gripper_mm_historical':actual[-1]['gripper_mm'],
 'gripper_feedback_is_not_caliper_verified_width_or_contact_force':True,'B_RGBD_frames':5,'B_requires_target_depth':False,
 'B_target_depth_usable_frames':review['temporal']['usable_frames'],'actual_q_in_original_task_bounds':inside,
 'not_a_motion_authorization':True,'camera_elapsed_s':e['camera_elapsed_s'],'all_owned_sources_exited':True,
 'CAN_RX_before':before['before']['rx'],'CAN_RX_after':after['rx'],'CAN_TX_before':before['before']['tx'],'CAN_TX_after':after['tx'],
 'B_window_TX_delta':0,'A_last_recorded_TX':load(A/'A_can_after.json')['tx'],
 'between_sessions_TX_delta_not_attributed':before['before']['tx']-load(A/'A_can_after.json')['tx'],
 'no_motion_enable_arm_gripper_reset_disable_CAN_recovery':True,'production_unchanged':True,'candidate_adapter_deployed':False,
 'runtime_files_SHA_verified':len(entries),'portable_assets_SHA_verified':len(load(b/'manifest.json')['files']),
 'tests_passed':72,'fit_performed':False,'TF_deployed':False,'raw_data_deleted':False,'GitHub_pushed':False,
 'next':'Confirm physical same-point/contact, then offline P1 cohort review only; no automatic open/observe/search or old B reuse'}
put(OUT/'assessment.json',a);shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:a[k] for k in ['B_raw_capture_complete','A_original_good_top_frames','B_RGBD_frames','runtime_files_SHA_verified','portable_assets_SHA_verified','B_window_TX_delta']}))
