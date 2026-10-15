"""Preserve the completed one-shot session; no device/ROS initialization."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'new_pair06_ready_capture_publish'
REPO=Path('/mnt/hgfs/ub')
TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'


def load(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,obj):
    with path.open('x') as stream: json.dump(obj,stream,ensure_ascii=False,indent=2,allow_nan=False)


OUT.mkdir(exist_ok=False)
folder=ROOT/'session'
execution=load(folder/'execution.json')
ready=load(folder/'readiness.json')
capture=load(folder/'capture/summary.json')
feedback=load(folder/'feedback.json')
assert execution['all_owned_sources_exited'] and execution['within_camera_budget']
assert execution['ready'] and ready['ready']
assert capture['saved_frames']==0 and capture['stop_reason'] is None
assert capture['received'].get('/camera/color/image_raw',0)==0
assert capture['received']['/joint_states_feedback']==2650
assert capture['received']['/camera/depth/image_raw']==1135
assert capture['received']['/camera/depth/camera_info']==1338
log=(folder/'color.log').read_text(errors='replace')
assert log.count('Publishing image #')==1
before,after=load(folder/'can_before.json'),load(folder/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
sources=load(folder/'source_SHA_before.json')
assert sources==load(folder/'source_SHA_after.json')
assert all(sha(Path(p))==v for p,v in sources.items())
preserved={}
for filename,names in [
    ('collect_static_rgbd.py',['checked_packet','feedback_lost','settled_feedback','matched',
                             'full_camera_info','stamp_ns','joint_positions','synchronizer']),
    ('calibration_readonly_feedback.py',['feedback_values','install_receive_parser'])]:
    path=TESTS/filename
    original=subprocess.check_output(['git','show',f'469dc08:{path.relative_to(REPO)}'],cwd=REPO,text=True)
    left={n.name:ast.dump(n) for n in ast.walk(ast.parse(original)) if isinstance(n,ast.FunctionDef)}
    right={n.name:ast.dump(n) for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef)}
    for name in names:
        assert left[name]==right[name]
    preserved[filename]=names
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair06/attempt01/manual_reset_observe/assessment.json')
production={name:{'expected':row['actual'],'actual':sha(Path(name))} for name,row in baseline['production_SHA'].items()}
assert all(row['expected']==row['actual'] for row in production.values())
deployed=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
assert sha(deployed)==baseline['deployed_adapter_sha256']
pre=load(ROOT/'pre_sdk.json')
latest=feedback['actual_last_sample']
assert latest['q_driver_rad']==baseline['last_fresh_feedback']['q_driver_rad']
color_event=next(e for e in execution['events'] if e['name']=='color' and 'argv' in e)
capture_event=next(e for e in execution['events'] if e['name']=='capture' and 'argv' in e)
assessment={
    'pair_id':'new_pair06','B_checkpoint':'1a2e633','user_approved_acquisition_change_and_one_static_session':True,
    'production_control_TF_limits_changed':False,'production_SHA':production,
    'deployed_adapter_sha256':sha(deployed),'candidate_adapter_fix_deployed':False,
    'motion_enable_disable_reset_gripper_commands_sent':False,'CAN_recovery':False,
    'all_owned_sources_exited':True,'original_acceptance_AST_verified':preserved,
    'pre_SDK_whole_quality':pre['quality'],'readiness_passed_real_four_source_packet':True,
    'readiness_does_not_prove_continuous_RGB':True,'readiness_received':ready['received'],
    'readiness_packet':ready['ready_packet'],'camera_elapsed_s':execution['camera_elapsed_s_including_cleanup'],
    'startup_camera_elapsed_s':execution['startup_camera_elapsed_s'],
    'RGB_start_to_first_packet_s':int(ready['ready_packet']['stamps_ns']['rgb'])/1e9-color_event['epoch'],
    'formal_collector_started_after_readiness_s':capture_event['epoch']-ready['ready_epoch'],
    'formal_collector_elapsed_s':capture['elapsed_s'],'formal_collector_received':capture['received'],
    'formal_collector_rejected':capture['rejected'],'formal_collector_matched_packets':capture['matched_packets'],
    'formal_collector_feedback_lost':capture['stop_reason']=='feedback_lost',
    'formal_collector_stop_reason':capture['stop_reason'],'formal_collector_returncode':execution['capture_returncode'],
    'cam2image_actual_Publishing_log_count':1,'formal_A_saved_RGBD_frames':0,'selected_qualified_samples':0,
    'raw_images_saved':0,'readiness_RGB_pixels_not_saved':True,
    'latest_collector_receipt_timing':capture['receipt_diagnostics']['latest_by_topic'],
    'latest_feedback':latest,'actual_q_matches_previous_observe':True,
    'current_continuous_monitoring':False,'factory_GET_started':False,
    'CAN_before':before,'CAN_after':after,'read_only_CAN_TX_delta':after['tx']-before['before']['tx'],
    'production_and_session_source_SHA_unchanged_during_real_run':True,
    'tests_passed':216,'formal_complete_pairs_unchanged':1,'formal_pair_complete':False,
    'new_proven_failure_layer':'RGB source published once during readiness; no subsequent RGB reached formal subscriber. '
                               'Not a feedback timeout, depth-quality gate, target geometry, TF or joint-limit failure.',
    'unproven_internal_cause':'Cannot yet distinguish VideoCapture read/empty-frame path, timer/executor or publish blockage. '
                              'One log before publish does not prove all later statements returned.',
    'source_reference':'https://github.com/ros2/demos/blob/humble/image_tools/src/cam2image.cpp',
    'reference_scope':'Upstream humble branch, not asserted binary-identical to installed 0.20.9 package; '
                      'version0.20.9 exact source URL fetch failed. No speculative QoS/DDS or backend change.',
    'next_step':'Review RGB-only capture/publish stall with explicit scoped evidence/approval. '
                'Do not repeat movement, auto-reopen, old startup budget test or lower data rules.',
    'GitHub_pushed':False}
put(OUT/'assessment.json',assessment)
put(OUT/'selected_for_analysis.json',{'pair_id':'new_pair06','selected_count':0,'qualified_samples':[],
    'reason':'No original RGB-D saved; do not fabricate20 good samples or count readiness as recorded images.',
    'unselected_data_policy':'Archive separately before acceptance; no deletions this round.'})
for name,path in [('execution.json',folder/'execution.json'),('readiness.json',folder/'readiness.json'),
                  ('capture_summary.json',folder/'capture/summary.json'),('feedback.json',folder/'feedback.json'),
                  ('pre_sdk.json',ROOT/'pre_sdk.json'),('can_before.json',folder/'can_before.json'),
                  ('can_after.json',folder/'can_after.json')]:shutil.copyfile(path,OUT/name)
snap=OUT/'executed_sources';snap.mkdir()
for path in sources:
    shutil.copyfile(path,snap/Path(path).name)
    assert sha(snap/Path(path).name)==sources[path]
shutil.copyfile('/tmp/piper_acquisition_ready_20261015.xml',OUT/'junit.xml')
shutil.copyfile(ROOT/'package_offline.py',OUT/'package_offline.py')
entries=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():continue
        assert not path.is_symlink()
        name=path.relative_to(ROOT).as_posix()
        archive.add(path,arcname=name,recursive=False)
        entries.append({'path':name,'sha256':sha(path),'bytes':path.stat().st_size})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
    for row in entries:assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest()==row['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),
    'files':entries,'all_SHA_verified':True})
put(OUT/'verification.json',{'raw_files_SHA_verified':len(entries),'executed_source_files_SHA_verified':len(sources),
    'original_acceptance_function_AST_checks':sum(map(len,preserved.values())),
    'tests_passed':216,'all_sources_exited':True,'production_unchanged':True,
    'formal_A0':True,'formal_complete_pairs':1,'GitHub_pushed':False})
print(json.dumps({k:assessment[k] for k in ['readiness_passed_real_four_source_packet','camera_elapsed_s',
    'startup_camera_elapsed_s','formal_collector_elapsed_s','formal_collector_received',
    'formal_collector_feedback_lost','formal_A_saved_RGBD_frames','read_only_CAN_TX_delta']},ensure_ascii=False))
print('verified',len(entries),'raw files;',len(sources),'source hashes')
