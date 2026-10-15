"""Offline serialized-message audit for the authorized original open-only action."""
from pathlib import Path
import json,sqlite3
import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
ROOT=Path('/home/johnwick/brain_robot_logs/piper_board_open_only.fpc9klxm')
database=ROOT/'open_witness_bag/open_witness_bag_0.db3'
connection=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True)
topics=dict(connection.execute('SELECT id,name FROM topics'))
counts={name:0 for name in topics.values()};feedback=[];commands=[];jaw=[]
names=[f'joint{i}' for i in range(1,7)]
for topic,stamp,data in connection.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
 name=topics[topic];counts[name]+=1
 if name not in ['/joint_states_feedback','/joint_commands','/brain_robot_grasp/gripper_command']:continue
 message=deserialize_message(data,JointState);values=dict(zip(message.name,message.position))
 if name=='/brain_robot_grasp/gripper_command':jaw.append({'stamp_ns':str(stamp),'names':list(message.name),'positions':list(message.position)})
 elif all(n in values for n in names):
  row={'stamp_ns':str(stamp),'q':[values[n] for n in names],'gap_m':values.get('gripper')}
  (feedback if name=='/joint_states_feedback' else commands).append(row)
connection.close()
assert len(jaw)==1 and jaw[0]['names']==['gripper'] and jaw[0]['positions']==[.1]
assert counts.get('/brain_robot_grasp/arm_trajectory',0)==0
assert len(commands)==86 and sum(c['gap_m'] is not None for c in commands)==80
assert all(c['gap_m'] is None or c['gap_m']==.1 for c in commands)
q=np.asarray([r['q'] for r in feedback]);command_q=np.asarray([r['q'] for r in commands])
observed_match=[float(np.max(np.abs(q-np.asarray(c['q'])),axis=1).min()) for c in commands]
e=json.loads((ROOT/'execution.json').read_text())
report={'offline_only':True,'ROS_initialized':False,'message_counts':counts,
 'explicit_gripper_requests':jaw,'arm_trajectory_count':0,'joint_command_count':len(commands),
 'explicit100mm_frames':80,'every_command_matches_some_recorded_actual_q':max(observed_match)<1e-12,
 'comparison_is_recorded_window_match_not_proof_of_zero_physical_motion':True,
 'max_q_distance_to_nearest_recorded_feedback_rad':max(observed_match),
 'recorded_feedback_peak_to_peak_rad':np.ptp(q,axis=0).tolist(),
 'command_peak_to_peak_rad':np.ptp(command_q,axis=0).tolist(),
 'final_minus_initial_q_rad':e['final_q_delta_rad'],
 'final_minus_initial_q_deg':np.degrees(e['final_q_delta_rad']).tolist(),
 'physical_six_axis_zero_displacement_proven':False,
 'original_services':[v['service'] for v in e['events'] if 'service' in v],
 'no_disable_reset_or_search_service_called':True,'observe_or_search_requested':False}
with (ROOT/'bag_audit.json').open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
print(json.dumps(report))
