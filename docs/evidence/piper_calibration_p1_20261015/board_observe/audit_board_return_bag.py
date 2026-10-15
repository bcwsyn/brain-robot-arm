"""Offline witness for the authorized existing observation return."""
from pathlib import Path
import json, sqlite3
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
ROOT=Path('/home/johnwick/brain_robot_logs/piper_board_return_observe.c4o22vip')
db=next((ROOT/'motion_witness_bag').glob('*.db3'))
connection=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
topics={i:(n,get_message(t)) for i,n,t in connection.execute('SELECT id,name,type FROM topics')}
counts={n:0 for n,_ in topics.values()};trajectories=[];states=[];reasons=[]
for topic,stamp,data in connection.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
    name,kind=topics[topic];counts[name]+=1
    if name not in ['/brain_robot_grasp/arm_trajectory','/brain_robot_visual_control/state','/brain_robot_visual_control/reason']:continue
    msg=deserialize_message(data,kind)
    if name=='/brain_robot_grasp/arm_trajectory':
        trajectories.append({'record_stamp_ns':str(stamp),'joint_names':list(msg.joint_names),'points':[{'positions':list(p.positions),'time_s':p.time_from_start.sec+p.time_from_start.nanosec/1e9} for p in msg.points]})
    elif name.endswith('/state'):states.append(msg.data)
    else:reasons.append(msg.data)
connection.close()
execution=json.loads((ROOT/'execution_session.json').read_text())
assert execution['observe_reached'] and execution['error'] is None and execution['stop_after_observe_readback']
assert counts.get('/brain_robot_grasp/gripper_command',0)==0
assert 'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH' in reasons
assert not any(s in ['SEARCH','ALIGN','GRASP_READY','GRASP','LIFT'] for s in states)
result={'offline_only':True,'message_counts':counts,'trajectories':trajectories,'states':states,'reasons':reasons,
        'gripper_commands':0,'stop_after_observe_verified':True,'all_owned_sources_exited':execution['all_owned_sources_exited'],
        'initial_q_driver_rad':execution['initial_measured']['q_driver_rad'],'observation_actual_q_driver_rad':execution['observe_feedback']['q'],
        'final_sdk':execution.get('final_sdk'),'production_unchanged':json.loads((ROOT/'production_SHA_before.json').read_text())==json.loads((ROOT/'production_SHA_after.json').read_text()),
        'services':[v for v in execution['events'] if 'service' in v]}
(ROOT/'bag_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'message_counts':counts,'trajectory_points':[len(t['points']) for t in trajectories],'states':states,'reasons':reasons,'production_unchanged':result['production_unchanged']}))
