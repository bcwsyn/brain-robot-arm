"""Close the authorized release evidence offline; no further commands."""
from pathlib import Path
import hashlib,json,shutil,tarfile
ROOT=Path('/home/johnwick/brain_robot_logs/piper_board_open_only.fpc9klxm')
OUT=ROOT/'publish';OUT.mkdir(exist_ok=False)
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
e=load(ROOT/'execution.json');audit=load(ROOT/'bag_audit.json')
assert e['opened'] and e['error'] is None and e['all_owned_sources_exited']
assert all(e['final_measured']['enabled']) and abs(e['final_measured']['gripper_mm']-100)<=3
assert not e['observe_return_requested'] and not e['reset_or_disable_requested']
assert audit['arm_trajectory_count']==0 and audit['joint_command_count']==86 and audit['explicit100mm_frames']==80
assert load(ROOT/'production_SHA_before.json')==load(ROOT/'production_SHA_after.json')
for p,digest in load(ROOT/'production_SHA_before.json').items():assert sha(Path(p))==digest
for name in ['execution.json','bag_audit.json','production_SHA_before.json','production_SHA_after.json',
             'can_before.json','can_after.json','sdk_before.json','sdk_after_enable.json','sdk_after_open.json','junit.xml']:
 shutil.copyfile(ROOT/name,OUT/name)
for name in ['piper_board_open_only.py','piper_original_adapter_only_launch.py','audit_board_open_bag.py']:
 shutil.copyfile(Path('/tmp')/name,OUT/name)
dependencies=[Path('/home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py'),
 Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py')]
put(OUT/'runtime_dependencies.json',{'recorded_after_execution_only':True,
 'files':[{'path':str(p),'sha256':sha(p)} for p in dependencies]})
files=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for p in sorted(ROOT.rglob('*')):
  rel=p.relative_to(ROOT)
  if not p.is_file() or rel.parts[0]=='publish':continue
  assert not p.is_symlink();archive.add(p,arcname=rel.as_posix(),recursive=False)
  files.append({'path':rel.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for f in files:assert hashlib.sha256(archive.extractfile(f['path']).read()).hexdigest()==f['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':files,'all_SHA_verified':True,'raw_deleted':False})
before=load(ROOT/'can_before.json')['before'];after=load(ROOT/'can_after.json')
a={'authorized_scope':'in_place_open_only','operator_quote':'好的','opened_verified':True,
 'initial_gap_mm':e['initial_measured']['gripper_mm'],'opened_feedback_gap_mm':e['opened_feedback']['gap_m']*1000,
 'final_passive_gap_mm':e['final_measured']['gripper_mm'],'final_six_enabled':e['final_measured']['enabled'],
 'observe_return_or_search_requested':False,'arm_trajectory_messages':0,
 'original_driver_local_enable_synced_for_already_enabled_arm':True,'hardware_disable_or_reset_requested':False,
 'software_disarmed_after_open':True,'all_owned_sources_exited':True,
 'six_axis_absolute_zero_motion_proven':False,'final_q_delta_rad':e['final_q_delta_rad'],
 'final_q_delta_deg':audit['final_minus_initial_q_deg'],'feedback_peak_to_peak_rad':audit['recorded_feedback_peak_to_peak_rad'],
 'cause_of_small_q_change_proven':False,'command_frames':86,'bounded_explicit_gripper_frames':80,
 'requested_gripper_input_count':1,'CAN_before':before,'CAN_after':after,'CAN_TX_delta':after['tx']-before['tx'],
 'production_unchanged':True,'new_TF_or_calibration_performed':False,'tests_passed':77,
 'runtime_files_SHA_verified':len(files),'raw_deleted':False,'GitHub_pushed':False,
 'next':'User may remove cube; keep checkerboard fixed. No observation return is authorized by this open-only confirmation.'}
put(OUT/'assessment.json',a);shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:a[k] for k in ['opened_verified','final_passive_gap_mm','arm_trajectory_messages','tests_passed','runtime_files_SHA_verified','CAN_TX_delta']}))
