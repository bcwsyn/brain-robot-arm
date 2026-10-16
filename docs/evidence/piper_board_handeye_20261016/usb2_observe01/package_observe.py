"""Offline audit of the authorized original observation return and camera inventory."""
from pathlib import Path
import ast
import collections
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tarfile

import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/usb2_observe01'
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from collect_calibration_sdk import summarize
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def gaps(rows,key):
    return sorted([{'gap_s':b[key]-a[key],'before':a[key],'after':b[key]} for a,b in zip(rows,rows[1:])],key=lambda v:v['gap_s'],reverse=True)[:5]

e=load(ROOT/'execution_session.json');inventory=load(ROOT/'camera_inventory.json')
before=load(ROOT/'production_SHA_before.json');after=load(ROOT/'production_SHA_after.json')
assert before==after and all(sha(Path(p))==v for p,v in after.items())
assert e['all_owned_sources_exited']
old=REPO/'docs/evidence/piper_board_handeye_20261016/board_resume03_port_reconnect/observe'
assert (old/'original_observe_launch.py').read_bytes()==(ROOT/'original_observe_launch.py').read_bytes()
functions=lambda p:[ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)]
assert functions(old/'executed_return.py')==functions(ROOT/'executed_return.py')
db=next((ROOT/'motion_witness_bag').glob('*.db3'))
con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
topics=dict(con.execute('select id,name from topics'));counts=collections.Counter()
trajectories=[];reasons=[];states=[];feedback=[];commands=[];names=[f'joint{i}' for i in range(1,7)]
for topic,stamp,data in con.execute('select topic_id,timestamp,data from messages order by timestamp,id'):
    name=topics[topic];counts[name]+=1
    if name=='/brain_robot_grasp/arm_trajectory':
        m=deserialize_message(data,JointTrajectory)
        trajectories.append({'epoch':stamp/1e9,'points':len(m.points),
            'start_q':list(m.points[0].positions),'goal_q':list(m.points[-1].positions),
            'duration_s':m.points[-1].time_from_start.sec+m.points[-1].time_from_start.nanosec/1e9})
    elif name in ('/brain_robot_visual_control/reason','/brain_robot_visual_control/state'):
        (reasons if name.endswith('/reason') else states).append({'epoch':stamp/1e9,'value':deserialize_message(data,String).data})
    elif name in ('/joint_states_feedback','/joint_commands'):
        m=deserialize_message(data,JointState);v=dict(zip(m.name,m.position))
        if all(n in v for n in names):
            if name=='/joint_commands':assert 'gripper' not in v
            (feedback if name=='/joint_states_feedback' else commands).append({'bag_epoch':stamp/1e9,
                'source_stamp_ns':m.header.stamp.sec*10**9+m.header.stamp.nanosec,'q':[v[n] for n in names]})
con.close()
assert counts.get('/brain_robot_grasp/gripper_command',0)==0
cfg=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['visual_search_controller']['ros__parameters']
goal=cfg['observe_joint_positions'];tolerance=cfg['joint_position_tolerance']
completed=[r for r in reasons if r['value']=='OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH']
assert e['observe_reached'] and completed and e['error'] is None
assert not any(s['value'] not in ['IDLE','STOPPED','PREPARE'] for s in states)
assert all(t['start_q']==t['goal_q'] for t in trajectories[1:])
sdk_reports={}
for name in ['sdk_before','sdk_after_enable','sdk_at_observation']:
    p=load(ROOT/(name+'.json'));best=None
    for i in range(len(p['samples'])):
        for j in range(i+30,len(p['samples'])+1):
            sub=p['samples'][i:j]
            if all(s['fresh_after_passive_connection'] for s in sub):
                q=summarize(sub)
                if q['static_three_seconds_and_thirty_samples'] and (best is None or j-i>best['n']):best={'i':i,'j':j,'n':j-i,'quality':q}
    fresh=[s for s in p['samples'] if s['fresh_after_passive_connection']]
    sdk_reports[name]={'whole_quality':p['quality'],'original_static_subwindow':best,
        'last_fresh':fresh[-1] if fresh else None,
        'actual_exit_code':next(v['exit_code'] for v in e['events'] if v.get('name')==name and 'exit_code' in v)}
raw=[];ids=collections.Counter();unparsed=[]
for line in (ROOT/'raw_CAN.log').read_text().splitlines():
    m=re.fullmatch(r'\((\d+\.\d+)\)\s+can0\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)',line)
    if m:raw.append({'epoch':float(m[1])});ids[m[2].lower()]+=1
    elif line:unparsed.append(line)
motion_start=trajectories[0]['epoch'];motion_end=completed[0]['epoch']
motion_feedback=[s for s in feedback if motion_start<=s['bag_epoch']<=motion_end]
motion_raw=[s for s in raw if motion_start<=s['epoch']<=motion_end]
last=e['final_sdk'];arrival=e['observe_feedback']['q']
arrival_error=max(abs(a-b) for a,b in zip(arrival,goal))
assert arrival_error<=tolerance and all(last['enabled'])
new_kernel=[line for line in e['kernel_after'].splitlines() if line not in e['kernel_before'].splitlines()]
ca=e['CAN_full_after'][0]
assessment={'baseline_commit':'4e44326','operator_quote':e['operator_quote'],'scope':e['approved_scope'],
    'original_control_helpers_and_launch_unchanged':True,'script_exit_code':0,
    'observe_reached_stopped_before_search':True,'stop_after_observe_readback':e['stop_after_observe_readback'],
    'target_q_rad':goal,'original_observe_tolerance_rad':tolerance,
    'arrival_q_rad':arrival,'arrival_maximum_goal_error_rad':arrival_error,
    'actual_control_interval_s':motion_end-motion_start,
    'trajectory_nominal_duration_s':trajectories[0]['duration_s'],
    'goal_is_reached_with_original_tolerance_not_exact_nominal_final_point':True,
    'trajectories':trajectories,'bag_counts':dict(counts),'reasons':reasons,'states':states,
    'last_bag_feedback':feedback[-1],'actual_end_SDK':last,'SDK_checks':sdk_reports,
    'motion_feedback_maximum_receipt_gaps_s':gaps(motion_feedback,'bag_epoch'),
    'raw_CAN_frames':len(raw),'raw_CAN_ID_counts':dict(ids),'raw_nonframe_lines':unparsed,
    'raw_motion_largest_timestamp_gaps_s':gaps(motion_raw,'epoch'),
    'raw_time_scope':'candump socket-provided timestamps, preserved as emitted; not asserted to be motor hardware timestamps.',
    'CAN_before':e['CAN_full_before'][0],'CAN_after':ca,
    'kernel_new_lines':new_kernel,'camera_inventory':inventory,
    'camera_capture_started':False,'new_board_reference_established':False,'old_board_candidates':'2/10 unchanged',
    'six_production_SHA_unchanged':True,'all_owned_sources_exited':True,
    'no_hardware_disable_reset_gripper_search_or_grasp':True,
    'next':'Actual host operation required: connect Orbbec depth and RGB to this VM. Keep USB2 setting, CAN, arm pose and board unchanged; no robot reboot. Agent then checks actual enumeration and bounded original RGB-D capture, establishes a new continuous board reference. No old-board ID mixing or production TF change.',
    'causal_limit':'This original observation return succeeded on the present UHCI path; not proof of permanent transport stability or xHCI root cause. Missing camera enumeration does not establish USB2 incompatibility.',
    'Git_sync':'Local only; existing divergent-main/history-review/publication-scope blocker unchanged.'}
OUT.mkdir(exist_ok=False)
put(OUT/'assessment.json',assessment)
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
    if p.suffix in ('.py','.json'):
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
print(json.dumps({k:assessment[k] for k in ['observe_reached_stopped_before_search','actual_control_interval_s','arrival_maximum_goal_error_rad','bag_counts','raw_CAN_frames','raw_motion_largest_timestamp_gaps_s','kernel_new_lines']},indent=2))
print('SDK static subwindows:',json.dumps({k:v['original_static_subwindow'] for k,v in sdk_reports.items()},indent=2))
print('Archive:',len(files),'members,',archive.stat().st_size,'bytes')
