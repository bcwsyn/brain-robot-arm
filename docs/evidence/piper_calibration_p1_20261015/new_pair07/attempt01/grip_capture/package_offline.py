"""Offline B closeout: verified SDK, original RGB-D/FK, user contact witness.

No device access, node startup or control interfaces. Depth is not required B.
The preview wrapper label is preserved rather than rewriting source execution.
"""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
import numpy as np
import yaml
REPO=Path('/mnt/hgfs/ub')
ROOT=Path('/home/johnwick/brain_robot_logs/new_pair07_preview.ddo9bxtf')
OUT=ROOT/'publish'
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT.mkdir(exist_ok=False)
e=load(ROOT/'execution.json');sdk=load(ROOT/'sdk.json')
cap=load(ROOT/'capture/summary.json');review=load(ROOT/'portable/depth_review.json')
assert e['error'] is None and e['all_owned_sources_exited'] and e['within_35s_camera_bound']
assert sdk['error'] is None and sdk['quality']['static_three_seconds_and_thirty_samples']
assert sdk['quality']['samples']==60 and sdk['quality']['fresh_samples']==59
assert cap['saved_frames']==5 and cap['stop_reason'] is None
assert load(ROOT/'source_SHA_before.json')==load(ROOT/'source_SHA_after.json')
for p,s in load(ROOT/'source_SHA_before.json').items():assert sha(Path(p))==s
before=load(ROOT/'can_before.json');after=load(ROOT/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
actual=[r for r in sdk['samples'] if r['fresh_after_passive_connection']]
q=actual[-1]['q_driver_rad'];assert not np.ptp([r['q_driver_rad'] for r in actual],axis=0).any()
assert all(r['actual_q_rad']==q for r in review['frames'])
assert not any(review['joint_spread_rad'])
frames=[json.loads(line) for line in (ROOT/'capture/observer.jsonl').read_text().splitlines() if line]
for r in frames:
 assert r['stamps_ns']['depth']==r['stamps_ns']['depth_info']
 assert r['q_rad']==q and r['stamp_span_s']<=.12
manifest=load(ROOT/'portable/manifest.json');verify_bundle(ROOT/'portable',manifest)
shutil.copytree(ROOT/'portable',OUT/'portable');shutil.copytree(ROOT/'quality',OUT/'quality')
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair06/attempt01/observe_capture/assessment.json')
production={p:{'expected':v['actual'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['actual']==v['expected'] for v in production.values())
deployed=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
assert sha(deployed)==baseline['deployed_adapter_sha256']
task=yaml.safe_load((ROOT/'portable/robot_task_config_snapshot.yaml').read_text())
params=task['grasp_lift_executor']['ros__parameters']
lo=params['real_trajectory_joint_min'];hi=params['real_trajectory_joint_max']
inside=all(a<=v<=b for a,v,b in zip(lo,q,hi))
assert inside
confirmation={'pair_id':'new_pair07','role':'held_out','operator_quote':'已实际夹紧，仍在原支撑物上',
 'actual_contact_confirmed_by_operator':True,'still_on_original_support_not_lifted':True,
 'independent_force_or_contact_verified_by_SDK':False,'confirmation_scope':'This new sixth placement only; no same-point A acquired yet'}
put(OUT/'operator_confirmation.json',confirmation)
assessment={'pair_id':'new_pair07','attempt':'01','role':'held_out','grip_B_capture_complete':True,
 'formal_A_frames':0,'complete_pair':False,'formal_complete_pairs_unchanged':1,
 'source_wrapper_called_preview_not_observation_proof':True,
 'actual_role_from_RGB_and_q_and_operator_confirmation':'grip_B',
 'operator_contact_confirmed':True,'physical_contact_verified_by_sdk':False,
 'q_mdeg':actual[-1]['q_mdeg'],'actual_q_driver_rad':q,'gripper_mm':actual[-1]['gripper_mm'],
 'gripper_mm_is_feedback_not_caliper_verified_cube_size':True,
 'SDK_quality':sdk['quality'],'last_fresh_feedback':load(ROOT/'feedback.json')['actual_last_sample'],
 'RGB_frames':5,'RGBD_frames_saved':5,'B_requires_target_depth':False,
 'camera_target_surface_valid_frames':review['temporal']['usable_frames'],
 'camera_cube_center_m':None,'gripper_base_cube_center_m':None,
 'T_base_gripper_base':review['frames'][0]['T_base_tool'],'model_sha256':review['urdf_sha256'],
 'actual_q_in_original_task_bounds':inside,'task_lower_rad':lo,'task_upper_rad':hi,
 'limits_were_not_changed':True,'movement_or_retakeover_authorized_by_this_offline_check':False,
 'reference_q_changed_since_previous_observation':True,'who_or_when_changed_q_not_inferred':True,
 'original_observation_q_rad':baseline['actual_observation_q_rad'],
 'camera_elapsed_s':e['camera_elapsed_s'],'all_owned_sources_exited':True,
 'no_motion_enable_arm_gripper_reset_disable_CAN_recovery':True,'read_only_CAN_TX_delta':after['tx']-before['before']['tx'],
 'production_SHA':production,'deployed_adapter_sha256':sha(deployed),'candidate_adapter_deployed':False,
 'portable_assets_SHA_verified':len(manifest['files']),'tests_passed':216,
 'next':'Save immutable B checkpoint; obtain per-group release/observe permission and fresh q before original path. No SEARCH/ALIGN/grasp/TF deployment.',
 'GitHub_pushed':False}
put(OUT/'assessment.json',assessment)
for name in ['execution.json','can_before.json','can_after.json','feedback.json','readiness.json']:
 shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile('/tmp/piper_pair07_preview.py',OUT/'executed_preview.py')
shutil.copyfile('/tmp/pair07_grip_tests.xml',OUT/'junit.xml')
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for p in sorted(ROOT.rglob('*')):
  rel=p.relative_to(ROOT)
  if not p.is_file() or rel.parts[0] in ('publish','portable','quality'):continue
  assert not p.is_symlink()
  archive.add(p,arcname=rel.as_posix(),recursive=False)
  entries.append({'path':rel.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for r in entries:assert hashlib.sha256(archive.extractfile(r['path']).read()).hexdigest()==r['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True})
shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({'B_capture_complete':True,'A_frames':0,'raw_files_SHA_verified':len(entries),
 'portable_assets_SHA_verified':len(manifest['files']),'q_in_original_limits':inside,
 'no_motion':True,'TX_delta':0,'SDK_quality':sdk['quality']}))
