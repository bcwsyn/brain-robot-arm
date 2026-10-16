"""Offline evidence audit, without re-running control or recovery."""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tarfile

from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/board_resume03_port_reconnect'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
OUT.mkdir(exist_ok=False)
motion=ROOT/'observe';e=load(motion/'execution_session.json');pre=load(ROOT/'port_preflight.json')
host=load(ROOT/'post_reconnect_failure/host_status.json')
assert not e['observe_reached'] and e['all_owned_sources_exited'] and e['original_contiguous_static_window']['quality']['static_three_seconds_and_thirty_samples']
before=load(motion/'production_SHA_before.json');after=load(motion/'production_SHA_after.json')
assert before==after and all(sha(Path(p))==v for p,v in after.items())
assert host['new_frames']==0 and all(n>0 for n in pre['per_second_frames'])
kernel_after=next(c['stdout'] for c in host['commands'] if c['argv']==['sudo','-n','dmesg','-T'])
echo=lambda s:[line for line in s.splitlines() if re.search(r'gs_usb .*Unexpected (out of range|unused) echo id',line)]
new_echo=[line for line in echo(kernel_after) if line not in echo(pre['kernel_log'])]
db=next((motion/'motion_witness_bag').glob('*.db3'));con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
topics=dict(con.execute('select id,name from topics'));counts={n:0 for n in topics.values()}
trajectories=[];reasons=[];feedback=[];commands=[];names=[f'joint{i}' for i in range(1,7)]
for topic,stamp,data in con.execute('select topic_id,timestamp,data from messages order by timestamp,id'):
    name=topics[topic];counts[name]+=1
    if name=='/brain_robot_grasp/arm_trajectory':
        m=deserialize_message(data,JointTrajectory)
        trajectories.append({'epoch':stamp/1e9,'points':len(m.points),'start_q':list(m.points[0].positions),'goal_q':list(m.points[-1].positions),'duration_s':m.points[-1].time_from_start.sec+m.points[-1].time_from_start.nanosec/1e9})
    elif name=='/brain_robot_visual_control/reason':reasons.append({'epoch':stamp/1e9,'value':deserialize_message(data,String).data})
    elif name in ('/joint_states_feedback','/joint_commands'):
        m=deserialize_message(data,JointState);v=dict(zip(m.name,m.position))
        if all(n in v for n in names):
            if name=='/joint_commands':assert 'gripper' not in v
            (feedback if name=='/joint_states_feedback' else commands).append({'bag_epoch':stamp/1e9,'source_stamp_ns':str(m.header.stamp.sec*10**9+m.header.stamp.nanosec),'q':[v[n] for n in names]})
con.close()
assert trajectories[0]['points']==4
assert all(t['points']==2 and t['start_q']==t['goal_q'] for t in trajectories[1:])
assert counts.get('/brain_robot_grasp/gripper_command',0)==0
assert any(r['value']=='PIPER_ADAPTER_DISARMED' for r in reasons)
first=json.loads(host['commands'][0]['stdout'])[0];last=json.loads(host['commands'][1]['stdout'])[0]
assert first['stats64']['rx']['packets']==last['stats64']['rx']['packets']==156995
cached=subprocess.check_output(['git','rev-list','--left-right','--count','HEAD...origin/main'],cwd=REPO,text=True).strip()
result={'operator_confirmation':load(ROOT/'authorization.json'),
    'new_interface':pre['after']['ifindex'],'USB_device_observed':'003/012',
    'user_reported_physical_port_change':True,'guest_cannot_verify_host_physical_controller_independence':True,
    'initial_passive_frames_5s':pre['passive_frames_5s'],'initial_per_second_frames':pre['per_second_frames'],
    'initial_TX_packets':pre['after']['stats64']['tx']['packets'],
    'SDK_whole_window_exit':next(v['exit_code'] for v in e['events'] if v.get('name')=='sdk_before' and 'exit_code' in v),
    'original_passing_static_window':e['original_contiguous_static_window'],
    'initial_actual_SDK':e['initial_measured'],'observed_goal_reached':False,'board_sampling_started':False,
    'bag_counts':counts,'trajectories':trajectories,'reasons':reasons,
    'last_received_feedback_NOT_current_pose':feedback[-1],
    'last_feedback_after_trajectory_start_s':feedback[-1]['bag_epoch']-trajectories[0]['epoch'],
    'maximum_goal_error_at_last_received_feedback_rad':max(abs(a-b) for a,b in zip(feedback[-1]['q'],trajectories[0]['goal_q'])),
    'first_command_matches_actual_arm_start':e['first_command']['q']==e['feedback_at_arm']['q'],
    'all_owned_sources_exited':e['all_owned_sources_exited'],'wrapper_error_is_failed_completion_not_root_cause':e['error'],
    'new_kernel_echo_events_during_this_attempt':new_echo,
    'no_new_echo_recovery_exception_used':True,'no_USB_reset_module_reload_or_post_fault_CAN_bounce':True,
    'post_fault_new_CAN_frames_3s':host['new_frames'],'post_fault_CAN_state':last['linkinfo']['info_data']['state'],
    'post_fault_RX_fixed':last['stats64']['rx']['packets'],'post_fault_TX_fixed':last['stats64']['tx']['packets'],
    'current_physical_pose_or_enable_status_known':False,
    'no_hardware_disable_reset_gripper_firmware_or_TF_change':True,'camera_was_not_started':True,
    'production_six_SHA_unchanged':True,'old_board_candidates':2,'target_new_cohort':10,
    'established':'A fresh interface and user-reported host port change restored reception; original observation again lost raw CAN reception while commands were active. This attempt has no newly logged illegal echo.',
    'not_established':'No proof which of adapter, host passthrough, guest transport or robot-side transmitter caused the silence. Prior echo343 is historical, not a newly reproduced error. Guest virtual USB path remains xHCI; this does not disprove the user changed a physical port.',
    'next':'No more same-condition motion or reconnect. Need host vmware.log for this interval, optionally USB-controller settings screenshot, before deciding a distinct host-side experiment. No arm movement, reset, disable or power cycle requested.',
    'Git_sync':{'target':'origin/main https://github.com/bcwsyn/brain-robot-arm.git','cached_ahead_behind':cached,'live_remote_not_verified_this_round':True,'full_pending_history_review_incomplete':True,'prior_shared_main_write_authorization_denial_preserved':True,'push_attempted':False,'status':'Local only, not synchronized to GitHub; do not force or auto-merge divergent history.'}}
put(OUT/'assessment.json',result)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],'all_members_readback_SHA_verified':True})
for p in files:
    if p.suffix in ('.py','.json'):
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size,'bag_counts':counts,'last_feedback':feedback[-1],'motion_duration_s':trajectories[0]['duration_s'],'feedback_after_start_s':result['last_feedback_after_trajectory_start_s'],'goal_error_rad':result['maximum_goal_error_at_last_received_feedback_rad'],'new_echo_events':new_echo,'git_cached':cached},indent=2))
