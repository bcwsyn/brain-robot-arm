"""Archive this closed session without changing raw data or production code."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'new_pair06_manual_reset_publish'
REPO = Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import load_installed_model, base_tool_fk


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def put(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


OUT.mkdir(exist_ok=False)
session, motion = load(ROOT/'execution_session.json'), load(ROOT/'motion_review.json')
retry = ROOT/'A_invocation_retry.qBjuiK'
A1, A2 = load(ROOT/'A_execution.json'), load(retry/'A_execution.json')
assert session['observe_reached'] and session['all_owned_sources_exited']
assert A1['all_owned_sources_exited'] and A2['all_owned_sources_exited']
assert A2['capture_summary']['saved_frames'] == 0
assert A2['capture_summary']['stop_reason'] == 'feedback_lost'
assert motion['topic_counts']['/brain_robot_grasp/gripper_command'] == 0
assert motion['no_search_or_align_in_bag'] and motion['first_arm_command_matches_real_feedback']
assert load(ROOT/'same_point_confirmation.json')['same_point_operator_confirmed']
for folder in [ROOT,retry]:
    assert load(folder/'A_source_SHA_before.json') == load(folder/'A_source_SHA_after.json')

before, after = load(ROOT/'can_before_motion.json')[0],load(ROOT/'can_after_motion.json')[0]
assert A2['capture_summary']['received']['/camera/depth/image_raw'] == 39
assert load(retry/'A_can_before.json')['before']['tx'] == load(retry/'A_can_after.json')['tx']
baseline = load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production = {}
for name, row in baseline['production_SHA'].items():
    # The approved fef28d6 candidate lives only in the canonical repository.
    expected = row['expected']
    if name.endswith('scripts/piper_jog_adapter.py'):
        expected = '47c8b7864c714de2ff85b9bea7ae722d57152c349fa235665f1b8830bf0c2b18'
    production[name] = {'expected_this_turn':expected,'actual':sha(Path(name))}
    assert production[name]['actual'] == expected, name
deployed = Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
assert sha(deployed) == 'a5074c614fcc1b7f57854e2693e689337577567dde0ca7765470df52fa1347d8'
urdf, task_path = load_installed_model()
with (OUT/'actual_runtime_model.urdf').open('x') as stream:
    stream.write(urdf)
shutil.copyfile(task_path,OUT/'robot_task_config_snapshot.yaml')
model = ET.fromstring(urdf)
last = load(retry/'A_bridge.json')['actual_last_sample']
first = next(e['epoch'] for e in session['events'] if e.get('reason') == 'START_AUTHORIZED')
reached = next(e['epoch'] for e in session['events'] if e.get('reason') == 'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH')
assessment = {
    'pair_id':'new_pair06','grip_checkpoint_commit':'1a2e633',
    'operator_manual_reset_confirmed':True,'same_point_operator_confirmed':True,
    'independent_same_point_or_contact_measurement':False,
    'original_observation_return_succeeded':True,'stopped_before_SEARCH':True,
    'motion_duration_START_to_REACHED_s':reached-first,
    'original_prepare_points':17,'original_stop_hold_points':2,
    'first_command_matches_real_feedback':True,
    'gripper_commands_sent':False,'reset_or_disable_sent_by_agent':False,
    'candidate_adapter_fix_deployed':False,'deployed_adapter_sha256':sha(deployed),
    'production_modified_this_turn':False,'production_SHA':production,
    'initial_after_manual_reset_q_rad':session['initial_measured']['q_driver_rad'],
    'last_fresh_feedback':last,'current_continuous_feedback':False,
    'T_base_link_gripper_base_at_last_feedback':base_tool_fk(model,last['q_driver_rad']),
    'FK_tool_origin_not_measured_cube_center':True,'camera_cube_center_m':None,
    'gripper_base_cube_center_m':None,'URDF_sha256':hashlib.sha256(urdf.encode()).hexdigest(),
    'SDK_after_enable_original_static_passed':True,
    'SDK_at_observation_original_whole_window_static_passed':False,
    'SDK_at_observation_original_contiguous_static_window':None,
    'actual_A_RGBD_frames_saved':0,'actual_A_good_top_frames':0,
    'A_failures':[
      {'camera_elapsed_s':A1['camera_elapsed_s_including_cleanup'],'raw_images_saved':0,
       'cause':'Temporary child command omitted module search path; ModuleNotFoundError. Corrected only temporary invocation.'},
      {'camera_elapsed_s':A2['camera_elapsed_s_including_cleanup'],'raw_images_saved':0,
       'original_stop_reason':A2['capture_summary']['stop_reason'],
       'received':A2['capture_summary']['received'],
       'cause':'Original 500ms source-age rule fired. RGB published0; open failure reported at SIGINT cleanup, causal ordering unresolved.'}],
    'camera_factory_GET_started':False,'no_old_factory_data_relabelled_as_new':True,
    'no_raw_depth_filled_or_images_fabricated':True,
    'CAN_motion_before_RX':before['stats64']['rx']['packets'],
    'CAN_motion_after_RX':after['stats64']['rx']['packets'],
    'CAN_motion_before_TX':before['stats64']['tx']['packets'],
    'CAN_motion_after_TX':after['stats64']['tx']['packets'],
    'A_last_CAN':load(retry/'A_can_after.json'),
    'CAN_reception_did_not_stop_in_recorded_windows':True,
    'original_full_SDK_failure_and_shutdown_failures_preserved':True,
    'shutdown_move_group_exit_minus11':motion['shutdown_move_group_exit_minus11_in_original_log'],
    'driver_shutdown_needed_SIGKILL':motion['driver_final_exit_minus9'],
    'all_owned_sources_exited':True,'formal_pair_completed':False,
    'formal_complete_pairs_unchanged':1,'placements_with_raw_data':5,
    'next_step':'Offline acquisition callback/startup review only; stop additional real camera sessions after two failures. No repeat movement, CAN recovery, limit changes or silent quality waiver.',
    'GitHub_pushed':False}
put(OUT/'assessment.json',assessment)
for name in ['execution_session.json','motion_review.json','same_point_confirmation.json',
             'sdk_after_manual_reset.json','sdk_after_enable.json','sdk_at_observation.json']:
    shutil.copyfile(ROOT/name,OUT/name)
shutil.copyfile(retry/'A_execution.json',OUT/'A_retry_execution.json')
shutil.copyfile(retry/'A_bridge.json',OUT/'A_retry_bridge.json')
shutil.copyfile(ROOT/'package_offline.py',OUT/'package_offline.py')
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        assert not path.is_symlink()
        relative=path.relative_to(ROOT).as_posix()
        archive.add(path,arcname=relative,recursive=False)
        entries.append({'path':relative,'sha256':sha(path),'bytes':path.stat().st_size})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
    for row in entries:
        assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest() == row['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),
    'files':entries,'all_archive_SHA_verified':True})
put(OUT/'verification.json',{'original_runtime_files_verified':len(entries),'all_archive_SHA_verified':True,
    'tests_passed':152,'raw_images_saved':0,'production_unchanged_this_turn':True,
    'formal_complete_pairs':1,'formal_pair_completed':False,'GitHub_pushed':False})
print(json.dumps(assessment,ensure_ascii=False),flush=True)
print('VERIFIED archive files:',len(entries),flush=True)
