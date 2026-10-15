"""Inspect closed original ROS bags and SDK evidence; never initialize ROS/CAN."""
from collections import Counter
import json,sqlite3,sys
from pathlib import Path
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
sys.path.insert(0,'/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
from collect_calibration_sdk import summarize

def static_windows(path):
    p=json.loads(path.read_text());rows=p['samples'];windows=[]
    for i in range(len(rows)):
        for j in range(i+30,len(rows)+1):
            part=rows[i:j]
            if all(s['fresh_after_passive_connection'] for s in part):
                quality=summarize(part)
                if quality['static_three_seconds_and_thirty_samples']:
                    windows.append({'indices':[i,j],'quality':quality})
    return {'original_whole_quality':p['quality'],
        'longest_original_contiguous':max(windows,key=lambda r:r['indices'][1]-r['indices'][0]) if windows else None}

def review(folder):
    db=next((folder/'motion_witness_bag').glob('*.db3'))
    c=sqlite3.connect(f'file:{db}?mode=ro',uri=True)
    topics={i:(n,get_message(t)) for i,n,t in c.execute('select id,name,type from topics')}
    counts=Counter();states=[];trajectories=[];grippers=[];first=last=feedback=None;previous=None;steps=[0.]*6
    for topic,stamp,data in c.execute('select topic_id,timestamp,data from messages order by timestamp,id'):
        name,kind=topics[topic];counts[name]+=1
        m=deserialize_message(data,kind)
        if name in ('/joint_commands','/joint_states_feedback'):
            values=dict(zip(m.name,m.position));names=[f'joint{i}' for i in range(1,7)]
            if not all(n in values for n in names):continue
            row={'bag_stamp_ns':str(stamp),'q_rad':[values[n] for n in names],'gripper_m':values.get('gripper')}
            if name=='/joint_commands':
                first=first or row;last=row
                if previous is not None:steps=[max(a,abs(b-v)) for a,b,v in zip(steps,row['q_rad'],previous)]
                previous=row['q_rad']
            else:feedback=row
        elif name in ('/brain_robot_visual_control/state','/brain_robot_visual_control/reason'):
            states.append({'topic':name,'data':m.data,'bag_stamp_ns':str(stamp)})
        elif name=='/brain_robot_grasp/gripper_command':
            grippers.append({'bag_stamp_ns':str(stamp),'names':list(m.name),'position_m':list(m.position)})
        elif name=='/brain_robot_grasp/arm_trajectory':
            trajectories.append({'bag_stamp_ns':str(stamp),'names':list(m.joint_names),'points':len(m.points),
                'first_q':list(m.points[0].positions),'last_q':list(m.points[-1].positions),
                'duration_s':m.points[-1].time_from_start.sec+m.points[-1].time_from_start.nanosec*1e-9})
    c.close();e=json.loads((folder/'execution_session.json').read_text())
    assert all(s['data'] not in ('SEARCH','ALIGN','FINAL_ALIGN','GRASP_READY') for s in states if s['topic'].endswith('/state'))
    assert len(grippers)==1 and grippers[0]['names']==['gripper'] and grippers[0]['position_m']==[.1]
    assert len(trajectories)==2 and trajectories[0]['points']==6 and trajectories[0]['duration_s']==20
    assert trajectories[1]['points']==2 and trajectories[1]['first_q']==trajectories[1]['last_q']
    assert first['q_rad']==e['feedback_at_arm']['q']
    return {'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'source_bag':str(db),
        'counts':dict(counts),'states':states,'gripper_commands':grippers,'trajectories':trajectories,
        'first_command':first,'last_command':last,'last_feedback':feedback,'max_adjacent_command_step_rad':steps,
        'first_command_matches_actual_arm_feedback':True,'SEARCH_ALIGN_grasp_absent':True,
        'hold_identity':'Original StopLocked constant 2-point hold, not another movement',
        'SDK':{n:static_windows(folder/n) for n in ('sdk_before.json','sdk_after_enable.json','sdk_at_observation.json')},
        'source_exits':[r for r in e['events'] if 'final_exit_code' in r]}

if __name__=='__main__':
    root=Path(sys.argv[1]);result=review(root)
    with (root/'motion_review.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({'motion_review_complete':True,'topics':result['counts'],'no_search_or_grasp':True}))
