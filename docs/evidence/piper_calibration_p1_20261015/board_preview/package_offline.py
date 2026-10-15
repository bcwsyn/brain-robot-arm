"""Offline board-preview evidence; preserve the original cube datasets."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
REPO=Path('/mnt/hgfs/ub');TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
ROOT=Path('/home/johnwick/brain_robot_logs/piper_board_preview.5cks5pix')
RUN=Path('/home/johnwick/brain_robot_logs/new_pair07_preview.ayb60z6j')
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import verify_bundle
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT=ROOT/'publish';OUT.mkdir(exist_ok=False)
e=load(RUN/'execution.json');sdk=load(RUN/'sdk.json');analysis=load(ROOT/'analysis/report.json')
assert e['error'] is None and e['saved_frames']==5 and e['all_owned_sources_exited'] and e['within_35s_camera_bound']
assert sdk['quality']['static_three_seconds_and_thirty_samples']
assert load(ROOT/'production_SHA_before.json')==load(ROOT/'production_SHA_after.json')
for p,digest in load(ROOT/'production_SHA_before.json').items():assert sha(Path(p))==digest
assert load(RUN/'source_SHA_before.json')==load(RUN/'source_SHA_after.json')
before=load(RUN/'can_before.json');after=load(RUN/'can_after.json')
assert after['tx']==before['before']['tx'] and after['rx']>before['after']['rx']
verify_bundle(RUN/'portable',load(RUN/'portable/manifest.json'))
shutil.copytree(RUN/'portable',OUT/'portable');shutil.copytree(ROOT/'analysis',OUT/'corner_diagnostic')
for name in ['execution.json','can_before.json','can_after.json','feedback.json','readiness.json','source_SHA_before.json','source_SHA_after.json']:
 shutil.copyfile(RUN/name,OUT/name)
for name in ['board_execution.json','production_SHA_before.json','production_SHA_after.json','junit.xml']:
 shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile('/tmp/piper_board_preview.py',OUT/'executed_preview.py')
shutil.copyfile(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/executed_preview.py',OUT/'executed_original_capture.py')
put(OUT/'board_definition.json',{'user_board_laid_quote':'已铺好标定板，并且此时方块的位置也没有改变',
 'user_dimension_quote':'单格32mm','square_length_m':.032,'dimension_source':'operator reported, not caliper-verified',
 'visible_pattern':'plain black-white checkerboard; full pattern outside image',
 'full_square_grid_columns':None,'full_square_grid_rows':None,'full_inner_corner_columns':None,'full_inner_corner_rows':None,
 'board_frame_origin_and_orientation_identified':False,'local3x3_is_not_board_specification':True,
 'cube_position_unchanged_confirmed_by_operator':True,'new_board_preview_does_not_replace_original_cube_AB':True,
 'portable_manifest_cube_edge_mm29_refers_to_existing_cube_NOT_board_square':True})
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for label,path in [('raw_preview',RUN),('invocation',ROOT)]:
  for p in sorted(path.rglob('*')):
   rel=p.relative_to(path)
   if not p.is_file() or rel.parts[0] in ('portable','publish','analysis'):continue
   assert not p.is_symlink();name=label+'/'+rel.as_posix();archive.add(p,arcname=name,recursive=False)
   entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for f in entries:assert hashlib.sha256(archive.extractfile(f['path']).read()).hexdigest()==f['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True,'raw_deleted':False})
fresh=[s for s in sdk['samples'] if s['fresh_after_passive_connection']]
a={'actual_role':'stationary_board_preview_only','board_square_mm_operator_reported':32,
 'original_RGBD_pairs':5,'SDK_quality':sdk['quality'],'actual_q_mdeg':fresh[-1]['q_mdeg'],
 'actual_q_driver_rad':fresh[-1]['q_driver_rad'],'enabled_historical':fresh[-1]['enabled'],
 'gripper_mm_historical':fresh[-1]['gripper_mm'],'single_actual_pose_only':True,
 'camera_elapsed_s':e['camera_elapsed_s'],'all_owned_sources_exited':True,
 'CAN_RX_before':before['before']['rx'],'CAN_RX_after':after['rx'],'CAN_TX_before':before['before']['tx'],'CAN_TX_after':after['tx'],
 'motion_enable_arm_gripper_reset_disable_CAN_recovery':False,'production_changed':False,
 'camera_intrinsics_or_mount_TF_changed':False,'original_cube_AB_modified':False,
 'local3x3_detector_true_frames':sum(f['local_candidate_found'] for f in analysis['frames']),
 'max_local_candidate_spread_px':max(analysis['local_corner_spread_bbox_diagonal_px']),
 'local_homography_rms_px_range':[min(f['local_homography_diagnostic']['rms_px'] for f in analysis['frames']),max(f['local_homography_diagnostic']['rms_px'] for f in analysis['frames'])],
 'whole_board_visible':False,'global_corner_IDs_known':False,'PnP_or_hand_eye_performed':False,
 'calibration_approved':False,'tests_passed':6,'runtime_files_SHA_verified':len(entries),
 'portable_assets_SHA_verified':19,'GitHub_pushed':False,
 'next':'Need explicit original open/observe permission for a full board view; then identify full dimensions and propose any multi-pose board workflow before changing the original calibration plan. No automatic motion.'}
put(OUT/'assessment.json',a);shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:a[k] for k in ['original_RGBD_pairs','camera_elapsed_s','tests_passed','runtime_files_SHA_verified','portable_assets_SHA_verified','max_local_candidate_spread_px']}))
