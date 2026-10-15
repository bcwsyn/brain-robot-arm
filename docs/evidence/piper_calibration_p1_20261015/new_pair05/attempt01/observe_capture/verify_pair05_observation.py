"""Offline checks; all inputs already saved, no live device or ROS graph."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sqlite3
import sys
import cv2
import numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

BASE = Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
OUT = BASE/'new_pair05_published_observation'
CAP = BASE/'new_pair05_A_batch60.3MFdVm'
SER = BASE/'new_pair05_serialized_return.eaPC4t'
TEST = Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
sys.path.insert(0,str(TEST))
from collect_calibration_sdk import summarize

def load(p):
    return json.loads(p.read_text())
def put(p,obj):
    p.write_text(json.dumps(obj,indent=2,allow_nan=False,default=lambda x:list(x))+'\n')

bag=[]
con=sqlite3.connect('file:'+str(next((SER/'motion_witness_bag').glob('*.db3')))+'?mode=ro',uri=True)
topics={i:(name,typ) for i,name,typ in con.execute('select id,name,type from topics')}
counts={name:con.execute('select count(*) from messages where topic_id=?',(i,)).fetchone()[0] for i,(name,typ) in topics.items()}
for i,(name,typ) in topics.items():
    if name not in ['/brain_robot_grasp/arm_trajectory','/brain_robot_grasp/gripper_command','/brain_robot_visual_control/state','/brain_robot_visual_control/reason']:
        continue
    for stamp,data in con.execute('select timestamp,data from messages where topic_id=? order by timestamp',(i,)):
        msg=deserialize_message(data,get_message(typ))
        row={'topic':name,'receipt_stamp_ns':str(stamp)}
        if name.endswith('arm_trajectory'):
            row['joint_names']=list(msg.joint_names)
            row['points']=[{'positions':list(p.positions),'time_from_start_s':p.time_from_start.sec+p.time_from_start.nanosec*1e-9} for p in msg.points]
        elif hasattr(msg,'data'):
            row['data']=msg.data if isinstance(msg.data,(str,int,float,bool)) else list(msg.data)
        elif hasattr(msg,'position'):
            row['position']=msg.position if isinstance(msg.position,(int,float)) else list(msg.position)
        bag.append(row)
con.close()
put(OUT/'bag_review.json',{'offline_only':True,'topic_counts':counts,'selected_messages':bag,'stationary_stop_holds_are_not_observe_trajectories':True})

static={}
for label,root,file in [('recovered',BASE/'new_pair05_recovered_readonly.nCsypV','sdk_static.json'),('after_observe',SER,'sdk_observe.json'),('before_batch60',CAP,'sdk_static.json')]:
    p=root/('sdk_recovered.json' if label=='recovered' else file)
    if not p.exists():
        matches=list(root.glob('*sdk*.json'))
        if len(matches)!=1:
            static[label]={'file_not_resolved':str(p),'candidates':[x.name for x in matches]}
            continue
        p=matches[0]
    packet=load(p)
    best=None
    samples=packet['samples']
    for start in range(len(samples)):
        for end in range(start+30,len(samples)+1):
            chosen=samples[start:end]
            if not all(x['fresh_after_passive_connection'] for x in chosen):
                continue
            q=summarize(chosen)
            if q['static_three_seconds_and_thirty_samples'] and (best is None or end-start>best['end_exclusive']-best['start']):
                best={'start':start,'end_exclusive':end,'original_summary':q}
    static[label]={'source':str(p),'full_window_quality_unchanged':packet['quality'],'passing_contiguous_slice':best}

rows=[json.loads(s) for s in (CAP/'observation/batch_01/observer.jsonl').read_text().splitlines()]
depths=[]
for row in rows:
    dep=Path(row['images']['depth']['path'])
    if not dep.is_absolute():
        dep=CAP/'observation/batch_01'/dep
    d=cv2.imread(str(dep),cv2.IMREAD_UNCHANGED)
    depths.append({'snapshot':row['snapshot'],'dtype':str(d.dtype),'shape':list(d.shape),'nonzero_pixels':int(np.count_nonzero(d))})
source=load(SER/'execution_session.json')
bridge=load(CAP/'A_bridge.json')
last=bridge['actual_last_sample']
can=load(CAP/'A_can_after.json')[0]
quality=load(OUT/'p0_report.json')
assert len(rows)==len(quality['frames'])
for row,frame in zip(rows,quality['frames']):
    assert row['snapshot']==frame['snapshot']
    row['actual_q_rad']=frame['actual_q_rad']
frozen={
'/home/johnwick/start_brain_robot_cube_real.sh':'87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0',
'/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml':'7d0e2c0d8336050de13a387d35bfb534b3577f8ac75f15883e9e6d403322e42a',
'/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml':'154938b0e22d22546cedceb56e2bb3484fd79988c5786d13aca5aa3bc48c6675',
'/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp':'2144f2237150106a5e0e7e8d01a8112821b5e1f291396ce5e22e78f132281e33',
'/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py':'a5074c614fcc1b7f57854e2693e689337577567dde0ca7765470df52fa1347d8'}
sha={p:{'expected':h,'actual':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p,h in frozen.items()}
assert all(x['actual']==x['expected'] for x in sha.values())
verification={'schema':'piper_pair05_observe_verification_v1','same_point_operator_confirmed':True,'same_point_user_quote':'仍在原位，没有被带动或重摆','same_point_confirmation_scope':'Operator statement after open and return; not independent metric proof','B_checkpoint':'2b1becb','release_and_observe_completed':source['opened'] and source['observe_reached'],'stop_before_search':source['stop_after_observe_readback'],'last_fresh_feedback':last,'last_fresh_is_not_continuous_monitoring':True,'raw_A_frames':len(rows),'good_top_frames':quality['summary']['good_top_frames'],'q_spread_rad':np.ptp([r['actual_q_rad'] for r in rows],axis=0).tolist(),'same_stamp_depth_Info_all':all(str(r['stamps_ns']['depth'])==str(r['stamps_ns']['depth_info']) for r in rows),'raw_depth_checks':depths,'sdk_static_checks':static,'CAN_after':{'ifindex':can['ifindex'],'rx':can['stats64']['rx']['packets'],'tx':can['stats64']['tx']['packets'],'state':can['linkinfo']['info_data']['state'],'rx_errors':can['stats64']['rx']['errors'],'tx_errors':can['stats64']['tx']['errors']},'readonly_CAN_TX_before':quality['can_checks'][0]['before']['tx'],'production_SHA':sha,'all_task_sources_exited':source['all_owned_sources_exited'] and load(CAP/'A_execution.json')['all_owned_sources_exited'],'no_hardware_disable_reset_or_firmware_operation':True,'complete_pair':False,'qualified_pairs':1,'positions_with_raw_B_and_some_A':4,'GitHub_pushed':False,'archive':{k:v for k,v in load(OUT/'runtime_manifest.json').items() if k!='files'}}
put(OUT/'verification.json',verification)
print(json.dumps({k:v for k,v in verification.items() if k not in ['raw_depth_checks','production_SHA','sdk_static_checks']},indent=2))
print('STATIC',json.dumps(static))
print('BAG_COUNTS',json.dumps(counts))
print('TRAJECTORIES',json.dumps([r for r in bag if r['topic'].endswith('arm_trajectory')]))
