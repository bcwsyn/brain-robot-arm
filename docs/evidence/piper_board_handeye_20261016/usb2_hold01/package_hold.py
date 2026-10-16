"""Offline audit and archive; never opens ROS or a CAN device."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
OUT = REPO / 'docs/evidence/piper_board_handeye_20261016/usb2_hold01'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def put(p, value): p.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
r = load(ROOT / 'execution.json')
rows = [json.loads(l) for l in (ROOT/'ROS_messages.jsonl').read_text().splitlines()]
cmds = [s for s in rows if s['topic'] == '/joint_commands']
fb = [s for s in rows if s['topic'] == '/joint_states_feedback']
disarm = next(e['epoch'] for e in r['events'] if e.get('service') == '/piper_jog_adapter/disarm')
start = r['hold_start_epoch']
def gap(rows, key='epoch'):
    pairs = [(b[key]-a[key], a[key], b[key]) for a,b in zip(rows,rows[1:])]
    return [{'gap': dt, 'before': a, 'after': b} for dt,a,b in sorted(pairs,reverse=True)[:5]]
def span(rows):
    return [max(s['position'][i] for s in rows)-min(s['position'][i] for s in rows) for i in range(6)]
def ros_summary(selected):
    return {'count':len(selected),'first_epoch':selected[0]['epoch'],'last_epoch':selected[-1]['epoch'],
            'six_q_spread_rad':span(selected),'largest_receipt_gaps_s':gap(selected),
            'largest_monotonic_gaps_s':gap(selected,'monotonic')}
raw = (ROOT/'CAN_receive_epoch_ns_frame16.bin').read_bytes()
assert len(raw)%24 == 0
times = []; by_id = collections.defaultdict(list); ids = collections.Counter()
for offset in range(0,len(raw),24):
    epoch_ns, can_id = struct.unpack_from('=QI', raw, offset)
    t = epoch_ns/1e9
    ids[hex(can_id)] += 1; by_id[hex(can_id)].append({'epoch':t})
    times.append({'epoch':t})
hold_raw = [x for x in times if start <= x['epoch'] <= disarm]
hold_fb = [x for x in fb if start <= x['epoch'] <= disarm]
allrawgaps = gap(times)
longgap = gap(hold_raw)[0]
recovered_fb = next(s for s in fb if s['epoch'] > longgap['after'])
before = r['CAN_snapshots'][0]['state']; after = r['CAN_snapshots'][-1]['state']
before_sdk = r['sdk']['sdk_before']['last_fresh']; after_sdk = r['sdk']['sdk_after']['last_fresh']
source_files = {
    'driver':Path('/home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py'),
    'installed_launch':Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py'),
    'SDK_CAN_enum':Path('/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk/piper_msgs/msg_v2/can_id.py')}
assert r['all_owned_sources_exited'] and r['six_source_SHA_unchanged']
assert span(cmds) == [0]*6 and span(fb) == [0]*6
assert all(s['name'] == [f'joint{i}' for i in range(1,7)] and not s['effort'] for s in cmds)
assert before_sdk['q_mdeg'] == after_sdk['q_mdeg'] and all(after_sdk['enabled'])
kernel_new = [line for line in r['kernel_after'].splitlines() if line not in r['kernel_before'].splitlines()]
a = {'baseline_commit':'d9471e2','operator_quote':'好','approved_scope':r['scope'],
     'script_exit_code':2,'original_execution_error':r['error'],
     'thirty_second_trial_passed':False,
     'active_start_epoch':start,'software_disarm_response_epoch':disarm,
     'active_start_to_disarm_response_s':disarm-start,
     'command_summary':ros_summary(cmds),'feedback_summary':ros_summary(fb),
     'feedback_during_hold_summary':ros_summary(hold_fb),
     'raw_record_format':'native standard-endian (= on this little-endian x86_64 guest): uint64 userspace receive epoch_ns + Linux classic CAN frame16; 24 bytes/record. Not hardware or kernel receive timestamps.',
     'raw_frames':len(raw)//24,'raw_ID_counts':dict(ids),'raw_global_largest_gaps_s':allrawgaps,
     'raw_during_hold_largest_gap':longgap,
     'raw_feedback_ID_largest_gaps_s':{k:gap(by_id[k]) for k in ['0x2a5','0x2a6','0x2a7','0x251','0x256']},
     'first_received_ROS_feedback_after_raw_resume_epoch':recovered_fb['epoch'],
     'recovered_without_USB_or_CAN_reconfiguration':True,
     'CAN_RX_before':before['stats64']['rx']['packets'],'CAN_RX_after':after['stats64']['rx']['packets'],
     'CAN_TX_before':before['stats64']['tx']['packets'],'CAN_TX_after':after['stats64']['tx']['packets'],
     'CAN_end_state':after['linkinfo']['info_data']['state'],
     'CAN_end_error_counters':after['linkinfo']['info_xstats'],
     'kernel_new_lines':kernel_new,
     'SDK_before':r['sdk']['sdk_before'],'SDK_after':r['sdk']['sdk_after'],
     'SDK_q_before_after_identical':True,'ROS_q_spreads_zero':True,
     'observed_gripper_or_trajectory_or_jog_inputs':r['observed_motion_inputs'],
     'outgoing_ROS_arm_frames_with_gripper_name':sum('gripper' in s['name'] for s in cmds),
     'raw_command_loopback_limit':'The observer did not receive the driver joint-control CAN IDs although interface TX rose; do not use absence of raw 0x159 to prove no gripper CAN output. ROS arm messages and unchanged driver source establish no explicit gripper target here.',
     'production_six_SHA_unchanged':True,'runtime_source_SHA':{k:{'path':str(p),'SHA256':sha(p)} for k,p in source_files.items()},
     'all_owned_sources_exited':True,'hardware_disable_reset_or_displaced_target_requested':False,
     'causal_limit':'Both raw-reader and ROS command receipt have a ~0.68s gap, followed by spontaneous recovery. Userspace timestamps cannot distinguish physical CAN silence, USB buffering, guest scheduling, or SDK/ROS delay. Not the earlier persistent stall and not proof of a root cause.',
     'harness_limit':'The diagnostic wrapper aborted when local ROS feedback age exceeded 0.5s; this is NOT the original adapter 25s watchdog. The original driver suppressed output and logged recovery. This early abort is retained, not called a 30s success or a permanent disconnect.',
     'next':'No operator reconnect/reboot or automatic movement. Offline review first. If another active hold is chosen, state a scoped diagnostic-wrapper correction (record transient gaps, retain original production suppress/25s rules) before a fresh authorized 30s test; do not silently alter production gates or rerun here.',
     'calibration':'Old board candidates 2/10, unchanged; no new image, hand-eye fit, TF or grasp.',
     'Git_sync':'Local only; pre-existing divergent-main/history-review/publication-scope blocker unchanged.'}
OUT.mkdir(exist_ok=False)
put(OUT/'assessment.json',a)
frozen=load(ROOT/'production_SHA_before.json')
assert all(sha(Path(p))==s for p,s in frozen.items())
put(OUT/'production_SHA_after.json',frozen)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),
    'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],
    'all_member_SHA_readback_verified':True})
for p in files:
    if p.suffix in ('.py','.json'):shutil.copyfile(p,OUT/p.name)
print(json.dumps({k:a[k] for k in ['thirty_second_trial_passed','active_start_to_disarm_response_s','raw_frames','raw_during_hold_largest_gap','CAN_TX_after','kernel_new_lines','SDK_q_before_after_identical','all_owned_sources_exited']},indent=2))
print('Archived',len(files),'files;',archive.stat().st_size,'bytes; six SHA unchanged')
