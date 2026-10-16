"""Offline portable evidence for approved board sampling; no devices/deletion."""
from pathlib import Path
import ast,hashlib,json,shutil,tarfile
BASE=Path('/home/johnwick/brain_robot_logs')
RUNS=[BASE/'board_handeye_20261016.N2eAKe',BASE/'board_handeye_20261016.1qwbf1',BASE/'board_handeye_20261016.2dE1Aj']
ROOT=RUNS[-1];PREVIEW=BASE/'new_pair07_preview.awrw9zku';INVOKE=BASE/'piper_board_full_observation.j3jmj6gu'
REPO=Path('/mnt/hgfs/ub');OUT=ROOT/'publish';OUT.mkdir(exist_ok=False)
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
baseline=load(RUNS[0]/'production_SHA_before.json')
for root in RUNS:
    e=load(root/'execution.json');assert e['all_owned_sources_exited']
    assert load(root/'production_SHA_before.json')==load(root/'production_SHA_after.json')==baseline
    assert load(root/'bag_audit.json')['gripper_requests']==0
assert all(sha(Path(p))==h for p,h in baseline.items())
portable=OUT/'portable';portable.mkdir();(portable/'continuous_rgb').mkdir()
e=load(ROOT/'execution.json')
for name in ['session_seed.json','camera_metadata.json','sample_start.json','sample_J4_plus.json','actual_sample_FK.json']:
    shutil.copyfile(ROOT/name,portable/name)
for sample in e['samples']:
    for row in sample['frames']:
        src=ROOT/row['image_path'];assert sha(src)==row['image_SHA256']
        shutil.copyfile(src,portable/row['image_path'])
put(portable/'manifest.json',{'board_protocol':'9fit+1heldout','completed_fit_poses':2,'completed_heldout_poses':0,
    'source_one_continuous_session_only':str(ROOT),'initial_failed_attempt_start_not_pooled':True,
    'raw_RGB_not_changed':True,'fixed_grid_units':'metres; 32mm operator-reported square',
    'files':[{'path':p.relative_to(portable).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(portable.rglob('*')) if p.is_file()]})
attempts=[]
for i,root in enumerate(RUNS,1):
    dest=OUT/f'run{i:02d}';dest.mkdir()
    for name in ['execution.json','bag_audit.json','can_before.json','can_after.json','planning_before_motion.json','production_SHA_before.json','production_SHA_after.json']:
        shutil.copyfile(root/name,dest/name)
    for name in ['executed_sampler.py','executed_launch.py']:
        shutil.copyfile(root/name,dest/name);ast.parse((dest/name).read_text())
    record=load(root/'execution.json');audit=load(root/'bag_audit.json')
    attempts.append({'run':i,'source':str(root),'error':record['error'],'sample_labels':audit['sample_labels'],
        'trajectories_published':audit['trajectory_count'],'raw_RGB_frames':record['raw_RGB_frames'],
        'raw_RGB_bytes':record['raw_RGB_bytes'],'all_owned_sources_exited':record['all_owned_sources_exited']})
for name in ['sdk_after_stop.json','adapter_endpoint_replay.json','actual_sample_FK.json']:
    shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile(RUNS[0]/'sdk_preflight.json',OUT/'sdk_preflight.json')
shutil.copyfile(PREVIEW/'execution.json',OUT/'today_preview_execution.json')
shutil.copyfile(PREVIEW/'capture/evidence/0001_rgb.png',OUT/'today_preview_first_raw_RGB.png')
sources=[Path(__file__),Path('/tmp/audit_board_sampling_bag.py'),Path('/tmp/board_adapter_progress_replay.py'),Path('/tmp/board_samples_actual_fk.py')]
for p in sources:shutil.copyfile(p,OUT/p.name)
put(OUT/'authorization.json',{'operator_reply':'同意','proposal_commit':'121d1ef','scope':'fixed-board9fit1heldout; planned bounded J4/J5/J6 offsets via original MoveIt/adapter; gripper unchanged',
    'original_cube_six_groups_preserved':True,'TF_or_production_adapter_changes_approved':False})
entries=[]
with tarfile.open(OUT/'closed_sessions.tar.gz','w:gz') as archive:
    for label,path in [(f'run{i:02d}',p) for i,p in enumerate(RUNS,1)]+[('today_preview',PREVIEW),('today_preview_invocation',INVOKE)]:
        for p in sorted(path.rglob('*')):
            rel=p.relative_to(path)
            if not p.is_file() or rel.parts[0]=='publish':continue
            assert not p.is_symlink();name=label+'/'+rel.as_posix();archive.add(p,arcname=name,recursive=False)
            entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'closed_sessions.tar.gz') as archive:
    for f in entries:assert hashlib.sha256(archive.extractfile(f['path']).read()).hexdigest()==f['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'closed_sessions.tar.gz'),'files':entries,'SHA_readback_verified':True,'raw_deleted':False})
fresh=[s for s in load(ROOT/'sdk_after_stop.json')['samples'] if s['fresh_after_passive_connection']]
final=fresh[-1]
report={'route_approved':True,'runs':attempts,'qualified_pose_samples_current_session':2,'fit_pose_samples':2,'heldout_pose_samples':0,
    '9plus1_complete':False,'hand_eye_solver_called':False,'rank_one_relative_axis_translation_subproblem':2,
    'final_q_mdeg':final['q_mdeg'],'final_q_driver_rad':final['q_driver_rad'],'final_enabled':final['enabled'],'final_gap_mm':final['gripper_mm'],
    'final_SDK_full_window_pass':load(ROOT/'sdk_after_stop.json')['quality']['static_three_seconds_and_thirty_samples'],
    'returned_to_original_start':False,'hardware_disabled':False,'gripper_commands':0,'reset_or_firmware_or_CAN_recovery':False,
    'controlled_plan_state_validity_passed':True,'all_18_nominal_paths_original_MoveIt_passed':True,
    'collision_world_ids':e['scene']['world_ids'],'physical_table_clearance_NOT_proven_by_empty_scene':True,
    'actual_continuous_RGB_frames':e['raw_RGB_frames'],'actual_RGB_bytes':e['raw_RGB_bytes'],'fixed_interior_points':len(load(ROOT/'session_seed.json')['fixed_interior_IDs']),
    'flow_identity_error_reported':e['flow_error_at_stop'],'source_exit_details':[v for v in e['events'] if 'source' in v],
    'deployed_adapter_endpoint_AST_replay_passed':True,'production_SHA_unchanged':True,'candidate_adapter_deployed':False,
    'runtime_files_SHA_verified':len(entries),'portable_assets_SHA_verified':len(load(portable/'manifest.json')['files']),
    'next':'Need approval for a narrowly scoped ORIGINAL adapter trajectory-progress offline fix; preserve limits/velocity/feedback-gap protections; no deployment/motion authorized by this request.',
    'GitHub_pushed':False}
put(OUT/'assessment.json',report)
put(OUT/'evidence_manifest.json',{'files':[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]})
print(json.dumps({k:report[k] for k in ['qualified_pose_samples_current_session','actual_continuous_RGB_frames','fixed_interior_points','final_q_mdeg','final_enabled','final_gap_mm','runtime_files_SHA_verified','portable_assets_SHA_verified']}))
