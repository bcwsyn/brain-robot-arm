"""Read-only command/feedback audit of the three bounded sampling attempts."""
import json,sqlite3,sys
from pathlib import Path
import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
NAMES=[f'joint{i}' for i in range(1,7)]

def audit(root):
    e=json.loads((root/'execution.json').read_text());db=next((root/'motion_bag').glob('*.db3'))
    con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    topics=dict(con.execute('SELECT id,name FROM topics'));counts={n:0 for n in topics.values()}
    commands=[];feedback=[];trajectories=[];jaw=[]
    for topic,stamp,data in con.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
        name=topics[topic];counts[name]+=1
        if name=='/brain_robot_grasp/arm_trajectory':
            m=deserialize_message(data,JointTrajectory)
            trajectories.append({'epoch':stamp/1e9,'joint_names':list(m.joint_names),'points':len(m.points),
                'start_q':list(m.points[0].positions),'goal_q':list(m.points[-1].positions)})
        elif name in ['/joint_commands','/joint_states_feedback','/brain_robot_grasp/gripper_command']:
            m=deserialize_message(data,JointState);v=dict(zip(m.name,m.position))
            if name=='/brain_robot_grasp/gripper_command':jaw.append({'names':list(m.name),'q':list(m.position)})
            elif all(n in v for n in NAMES):
                (commands if name=='/joint_commands' else feedback).append({'epoch':stamp/1e9,'q':[v[n] for n in NAMES],'gripper_field_present':'gripper' in v})
    con.close();assert not jaw and all(not c['gripper_field_present'] for c in commands)
    windows=[]
    for i,t in enumerate(trajectories):
        end=trajectories[i+1]['epoch'] if i+1<len(trajectories) else float('inf')
        cmd=[c for c in commands if t['epoch']<=c['epoch']<end]
        fb=[f for f in feedback if t['epoch']<=f['epoch']<end]
        if not cmd or not fb:continue
        cq=np.asarray([c['q'] for c in cmd]);fq=np.asarray([f['q'] for f in fb])
        tail=[c for c in cmd if c['epoch']>=cmd[-1]['epoch']-10]
        lastfb=[f for f in fb if f['epoch']>=cmd[-1]['epoch']-10]
        windows.append({'trajectory_index':i,'duration_s':cmd[-1]['epoch']-t['epoch'],'published_trajectory':t,
            'command_count':len(cmd),'feedback_count':len(fb),'command_q_min':cq.min(axis=0).tolist(),'command_q_max':cq.max(axis=0).tolist(),
            'feedback_q_min':fq.min(axis=0).tolist(),'feedback_q_max':fq.max(axis=0).tolist(),
            'last_10s_J4_command_range_rad':[min(c['q'][3] for c in tail),max(c['q'][3] for c in tail)],
            'last_10s_J4_feedback_range_rad':[min(f['q'][3] for f in lastfb),max(f['q'][3] for f in lastfb)]})
    result={'offline_only':True,'root':str(root),'message_counts':counts,'trajectory_count':len(trajectories),'gripper_requests':0,
        'command_frames_with_gripper_field':0,'windows':windows,'error':e['error'],'sample_labels':[s['label'] for s in e['samples']],
        'all_owned_sources_exited':e['all_owned_sources_exited'],'production_SHA_unchanged':json.loads((root/'production_SHA_before.json').read_text())==json.loads((root/'production_SHA_after.json').read_text())}
    with (root/'bag_audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':audit(Path(sys.argv[1]))
