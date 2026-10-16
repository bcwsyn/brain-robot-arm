"""Offline, independent evidence package for the confirmed host reconnection."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile

from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/board_resume02_host_reconnect'
TOOLS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TOOLS))
from collect_calibration_sdk import summarize
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def best_window(packet):
    s=packet['samples'];best=None
    for i in range(len(s)):
        for j in range(i+30,len(s)+1):
            q=summarize(s[i:j])
            if q['static_three_seconds_and_thirty_samples'] and (best is None or j-i>best['samples']):best={'start':i,'end':j,'samples':j-i,'quality':q}
    return best

OUT.mkdir(exist_ok=True)
assert not any(OUT.iterdir()), 'Refuse to overwrite an existing evidence package'
motion=ROOT/'observe_after_host_reconnect'
e=load(motion/'execution_session.json')
assert e['all_owned_sources_exited'] and not e['observe_reached']
assert load(motion/'production_SHA_before.json')==load(motion/'production_SHA_after.json')==load(ROOT/'approved_baseline.json')
assert all(sha(Path(p))==v for p,v in load(ROOT/'approved_baseline.json').items())
db=next((motion/'motion_witness_bag').glob('*.db3'))
c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
topics=dict(c.execute('select id,name from topics'))
counts={name:0 for name in topics.values()};trajectories=[];reasons=[];states=[];feedback=[];commands=[]
names=[f'joint{i}' for i in range(1,7)]
for topic,stamp,data in c.execute('select topic_id,timestamp,data from messages order by timestamp,id'):
    name=topics[topic];counts[name]+=1
    if name=='/brain_robot_grasp/arm_trajectory':
        m=deserialize_message(data,JointTrajectory)
        trajectories.append({'epoch':stamp/1e9,'points':len(m.points),'start':list(m.points[0].positions),'goal':list(m.points[-1].positions),'duration_s':m.points[-1].time_from_start.sec+m.points[-1].time_from_start.nanosec/1e9})
    elif name in ('/brain_robot_visual_control/state','/brain_robot_visual_control/reason'):
        row={'epoch':stamp/1e9,'value':deserialize_message(data,String).data}
        (reasons if name.endswith('reason') else states).append(row)
    elif name in ('/joint_states_feedback','/joint_commands'):
        m=deserialize_message(data,JointState);v=dict(zip(m.name,m.position))
        if all(n in v for n in names):
            if name=='/joint_commands':assert 'gripper' not in v
            (feedback if name=='/joint_states_feedback' else commands).append({'bag_epoch':stamp/1e9,'source_stamp_ns':str(m.header.stamp.sec*10**9+m.header.stamp.nanosec),'q':[v[n] for n in names]})
c.close()
assert len(trajectories)==3 and trajectories[0]['points']==8
assert all(t['points']==2 and t['start']==t['goal'] for t in trajectories[1:])
assert counts.get('/brain_robot_grasp/gripper_command',0)==0
assert any(r['value']=='PIPER_ADAPTER_DISARMED' for r in reasons)
host=load(ROOT/'post_reconnect_failure/host_status.json')
link0=json.loads(host['commands'][0]['stdout'])[0];link1=json.loads(host['commands'][1]['stdout'])[0]
assert host['new_frames']==0 and link0['stats64']['rx']['packets']==link1['stats64']['rx']['packets']==544487
recovery=load(ROOT/'post_reconnect_failure/new_echo_single_interface_recovery.json')
assert recovery['commands'][-1]['returncode']==2 and 'No such device' in recovery['commands'][-1]['stderr']
initial=load(ROOT/'host_reconnect/sdk.json')
sdk=load(motion/'sdk_before.json')
static=best_window(sdk);assert static
result={
    'user_confirmed_host_reconnect':'已完成USB-CAN宿主侧重连',
    'initial_feedback_restored':True,'initial_interface':5,
    'initial_passive_SDK_quality':initial['quality'],'initial_last_complete_SDK':initial['samples'][-1],
    'initial_whole_speed_window_failed_not_hidden':True,
    'new_actual_pose_original_static_subwindow':static,
    'old_near_zero_baseline_not_reused_for_changed_pose':True,
    'observation_reached':False,'board_sampling_started':False,'old_board_pose_candidates':2,'required_new_cohort':10,
    'primary_failure':'CAN reception ceased during the original 8-point current-to-observe trajectory; original guards stopped output and software-disarmed.',
    'wrapper_fault_recognition_worked':True,'wrapper_error':e['error'],
    'bag_counts':counts,'trajectories':trajectories,'reasons':reasons,'states':states,
    'last_received_feedback_NOT_current_physical_state':feedback[-1],
    'last_feedback_after_trajectory_start_s':feedback[-1]['bag_epoch']-trajectories[0]['epoch'],
    'maximum_observe_goal_error_at_last_received_feedback_rad':max(abs(a-b) for a,b in zip(feedback[-1]['q'],trajectories[0]['goal'])),
    'first_command_matches_arm_feedback':max(abs(a-b) for a,b in zip(e['first_command']['q'],e['feedback_at_arm']['q']))<=.001,
    'new_kernel_evidence':'2026-10-16 12:59:08 gs_usb 3-1.2:1.0 can0: Unexpected out of range echo id 343',
    'kernel_version':'6.8.0-138-generic',
    'USB_power':host['USB_power'],'autosuspend_already_disabled_no_write':True,
    'post_fault_passive_frames_3s':host['new_frames'],'RX_fixed':544487,'TX_packets_fixed':2643,
    'bus_off_or_CAN_error_counter_increments_seen':False,
    'one_new_echo_policy_recovery_done':True,'recovery_UP_errno':'ENODEV','current_interface_state':'DOWN/STOPPED, netdev still listed',
    'no_repeat_motion_USB_reset_module_reload_after_second_failure':True,
    'hardware_disable_reset_or_gripper_commands':False,'all_owned_sources_exited':True,
    'production_sources_SHA_unchanged':True,'current_enabled_or_pose_known_after_stall':False,
    'official_fact':'Upstream Linux v6.8 gs_usb uses ten TX contexts; an echo343 is out of range and this receive callback logs/discards that echo and resubmits its URB.',
    'inference_limits':'This proves an invalid USB-CAN echo was seen, not its origin or that this one echo caused all subsequent silence. Cannot distinguish adapter, host passthrough, kernel interaction, or physical link from this log alone. Upstream v6.8 is a reference, not a claimed exact source of Ubuntu 6.8.0-138 binary.',
    'old_echo_marker_issue':'Persisted marker is Sep28 count1; current boot also count1. Count alone is not boot-aware. Production frozen, no marker/script change; current event recovery tracked in its own boot-ID report.',
    'next_required_external_change':'Change the host USB-CAN data path (prefer a different direct physical port without an external hub), reconnect to this VM; do not move/power-cycle/disable the arm. No blind repeat of same host-only reconnect. Host VMware log can distinguish further.',
    'official_sources':[
        'https://raw.githubusercontent.com/torvalds/linux/v6.8/drivers/net/can/usb/gs_usb.c',
        'https://github.com/candle-usb/candleLight_fw/blob/master/src/can_common.c',
        'https://knowledge.broadcom.com/external/article/307966'],
    'metadata_note':'invocation_changes.wrapper_only_fault_recognition mistakenly stores checklist replacement string; executed_return.py is authoritative and comparison proves only the terminal-fault wait plus printed checklist changed.'
    ,'package_first_assertion_failure_not_hardware_failure':'Initial offline packaging expected one constant hold; bag contains two (fault and USER_STOP cleanup). Corrected only audit expectation after reading all three trajectories; raw bag unchanged.'
}
put(OUT/'assessment.json',result)
files=[]
for d in ('host_reconnect','observe_after_host_reconnect','post_reconnect_failure'):
    files.extend(p for p in (ROOT/d).rglob('*') if p.is_file())
files.extend(ROOT/n for n in ('prepare_after_host_reconnect.py','capture_post_reconnect_failure.py','recover_new_echo_once.py','package_host_reconnect.py'))
files=sorted(set(files));archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'archive_SHA256':sha(archive),'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],'all_members_readback_SHA_verified':True})
for d in ('host_reconnect','observe_after_host_reconnect','post_reconnect_failure'):
    for p in (ROOT/d).rglob('*.json'):
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for p in (ROOT/d).glob('*.py'):
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
for p in files:
    if p.parent==ROOT:shutil.copyfile(p,OUT/p.name)
print(json.dumps({'assessment':str(OUT/'assessment.json'),'original_files':len(files),'archive_bytes':archive.stat().st_size,'last_feedback':feedback[-1],'static_window':static,'bag_counts':counts},indent=2))
