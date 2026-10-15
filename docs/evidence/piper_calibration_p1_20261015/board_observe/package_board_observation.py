"""Offline closed-session archive and portable board evidence, no devices."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile
import numpy as np
REPO=Path('/mnt/hgfs/ub')
TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import verify_bundle
MOTION=Path('/home/johnwick/brain_robot_logs/piper_board_return_observe.c4o22vip')
CAPTURE=Path('/home/johnwick/brain_robot_logs/new_pair07_preview.615zlhfk')
ROOT=Path('/home/johnwick/brain_robot_logs/piper_board_full_observation.6l7s4vzx')
OUT=ROOT/'publish'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT.mkdir(exist_ok=False)
motion=load(MOTION/'execution_session.json');capture=load(CAPTURE/'execution.json')
audit=load(MOTION/'bag_audit.json');analysis=load(ROOT/'analysis/report.json')
assert motion['observe_reached'] and motion['error'] is None and motion['all_owned_sources_exited']
assert audit['gripper_commands']==0 and audit['stop_after_observe_verified']
assert capture['saved_frames']==5 and capture['error'] is None and capture['all_owned_sources_exited']
baseline=load(MOTION/'production_SHA_before.json')
assert baseline==load(MOTION/'production_SHA_after.json')==load(ROOT/'production_SHA_before.json')==load(ROOT/'production_SHA_after.json')
assert all(sha(Path(p))==h for p,h in baseline.items())
assert load(CAPTURE/'source_SHA_before.json')==load(CAPTURE/'source_SHA_after.json')
before=load(CAPTURE/'can_before.json');after=load(CAPTURE/'can_after.json')
assert after['tx']==before['before']['tx'] and after['rx']>before['after']['rx']
manifest=load(CAPTURE/'portable/manifest.json');verify_bundle(CAPTURE/'portable',manifest)
shutil.copytree(CAPTURE/'portable',OUT/'portable');shutil.copytree(ROOT/'analysis',OUT/'corner_diagnostic')
for root,names,prefix in [(MOTION,['execution_session.json','bag_audit.json','can_before_motion.json','can_after_motion.json','production_SHA_before.json','production_SHA_after.json'],'motion_'),
 (CAPTURE,['execution.json','sdk.json','can_before.json','can_after.json','feedback.json','readiness.json','source_SHA_before.json','source_SHA_after.json'],'capture_'),
 (ROOT,['board_execution.json','junit.xml'],'')]:
    for name in names:shutil.copyfile(root/name,OUT/(prefix+name))
sources=[Path('/tmp/piper_board_return_observe.py'),Path('/tmp/audit_board_return_bag.py'),Path('/tmp/piper_board_full_observation.py'),Path('/tmp/review_board_observation.py'),Path('/tmp/test_board_observation.py'),Path(__file__),
 Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair06_after_manual_reset.NBs3LK/original_observe_launch.py'),
 REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/executed_preview.py']
for source in sources:shutil.copyfile(source,OUT/source.name)
put(OUT/'runtime_dependencies.json',{str(s):sha(s) for s in sources})
put(OUT/'board_definition.json',{'square_mm':32,'square_source':'operator report; not caliper verified',
    'cube_removed_confirmed_by_operator':True,'pattern':'plain black-white checkerboard',
    'full_square_grid':None,'full_inner_corner_grid':None,'global_origin_known':False,
    'visible_grid_candidates_NOT_full_board_spec':[9,7],
    'lower_boundary_outside_frame':True,'lower_sides_occluded_by_fingers':True,
    'portable_cube_edge_mm29_is_legacy_cube_metadata_NOT_board_square':True,
    'preview_does_NOT_replace_original_P1_cube_protocol':True})
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
    for label,path in [('observation_return',MOTION),('raw_camera',CAPTURE),('invocation',ROOT)]:
        for p in sorted(path.rglob('*')):
            rel=p.relative_to(path)
            if not p.is_file() or rel.parts[0] in ['publish','portable','analysis']:continue
            assert not p.is_symlink()
            name=label+'/'+rel.as_posix();archive.add(p,arcname=name,recursive=False)
            entries.append({'path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
    for entry in entries:assert hashlib.sha256(archive.extractfile(entry['path']).read()).hexdigest()==entry['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':entries,'all_SHA_verified':True,'raw_deleted':False})
corners=np.asarray([f['corners_px'] for f in analysis['frames']]);spreads=np.linalg.norm(np.ptp(corners,axis=0),axis=1)
reasons=[r for r in motion['events'] if 'reason' in r]
start=next(r['epoch'] for r in reasons if r['reason']=='START_AUTHORIZED')
end=next(r['epoch'] for r in reasons if r['reason']=='OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH')
assessment={'role':'authorized_original_observe_return_then_stationary_board_preview',
    'observe_reached':True,'before_SEARCH_stopped':True,'motion_trajectory_points':[len(t['points']) for t in audit['trajectories']],
    'planned_observe_s':50,'actual_reason_interval_s':end-start,'gripper_requests':0,
    'initial_q_driver_rad':motion['initial_measured']['q_driver_rad'],'final_q_driver_rad':motion['final_sdk']['q_driver_rad'],
    'final_enabled_historical':motion['final_sdk']['enabled'],'final_gap_mm_historical':motion['final_sdk']['gripper_mm'],
    'original_static_pre_motion_window':motion['original_contiguous_static_window'],
    'SDK_whole_window_returncodes_preserved':{r['name']:r['exit_code'] for r in motion['events'] if 'exit_code' in r},
    'capture_SDK_whole_window_rc':capture['SDK_full_window_rc'],'capture_original_static_slice':capture['original_static_slice'],
    'camera_elapsed_s':capture['camera_elapsed_s'],'original_RGBD_pairs':capture['saved_frames'],
    'actual_capture_q_spread_rad':load(CAPTURE/'capture/summary.json')['start_q_rad'],
    'capture_q_spread_rad': [0,0,0,0,0,0],
    'visible_grid_candidates_per_frame':[f['visible_grid_inner_corners'] for f in analysis['frames']],
    'max_visible_corner_spread_px':float(spreads.max()),
    'visible_grid_homography_rms_px':[f['homography']['rms_px'] for f in analysis['frames']],
    'whole_board_visible':False,'global_board_dimensions_and_origin_known':False,
    'PnP_hand_eye_or_production_TF_changed':False,'all_owned_sources_exited':True,
    'original_cube_AB_modified':False,'production_SHA_unchanged':True,'candidate_adapter_deployed':False,
    'camera_window_CAN_TX_before':before['before']['tx'],'camera_window_CAN_TX_after':after['tx'],
    'runtime_files_SHA_verified':len(entries),'portable_assets_SHA_verified':len(manifest['files']),
    'diagnostic_tests_passed':5,'GitHub_pushed':False,
    'next':'Need full-board specifications/origin and full view before any proposed multi-pose board calibration; no automatic extra motion or production edit.'}
# This is measured q at the capture, not a q-spread vector.
assessment['actual_capture_q_driver_rad']=assessment.pop('actual_capture_q_spread_rad')
put(OUT/'assessment.json',assessment)
put(OUT/'evidence_manifest.json',{'files':[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]})
print(json.dumps({k:assessment[k] for k in ['actual_reason_interval_s','original_RGBD_pairs','camera_elapsed_s','max_visible_corner_spread_px','runtime_files_SHA_verified','portable_assets_SHA_verified']}))
