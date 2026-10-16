"""Bounded subscription-only actual-run evidence. No publishers or services."""
import collections,hashlib,json,signal,time
from pathlib import Path
import cv2,numpy as np,rclpy
from cv_bridge import CvBridge
from rclpy.qos import QoSProfile,DurabilityPolicy,qos_profile_sensor_data
from rosidl_runtime_py.convert import message_to_ordereddict
from sensor_msgs.msg import Image,JointState,CameraInfo
from std_msgs.msg import String,Bool,UInt8
from trajectory_msgs.msg import JointTrajectory
ROOT=Path(__file__).resolve().parent/'real_record';ROOT.mkdir(exist_ok=False)
rclpy.init();node=rclpy.create_node('p4_real_subscription_recorder');bridge=CvBridge()
stop=False
def stopped(*_):
    global stop;stop=True
signal.signal(signal.SIGINT,stopped);signal.signal(signal.SIGTERM,stopped)
events=(ROOT/'events.jsonl').open('x');samples=(ROOT/'samples.jsonl').open('x')
counts=collections.Counter();subs=[];latest={};images={};last_feedback={};last_rgb=0;last_saved=None
total_bytes=0;saved=0;stage='STARTING';started=time.monotonic()
saved_rgb_snapshots={}
def stamp(m):return m.header.stamp.sec*10**9+m.header.stamp.nanosec
def write(stream,obj):stream.write(json.dumps(obj,allow_nan=False)+'\n');stream.flush()
def image_receive(m,name):
    global total_bytes
    counts[name]+=1;cache=images.setdefault(name,collections.OrderedDict());cache[stamp(m)]=m
    while len(cache)>16:cache.popitem(last=False)
    if name in ('debug','color_debug') and stamp(m) in saved_rgb_snapshots:
        path=ROOT/f'{saved_rgb_snapshots[stamp(m)]:04d}_{name}.png'
        if not path.exists() and total_bytes<8<<20:
            ok,b=cv2.imencode('.png',bridge.imgmsg_to_cv2(m,'bgr8'));assert ok
            raw=b.tobytes()
            if total_bytes+len(raw)<=8<<20:
                path.write_bytes(raw);total_bytes+=len(raw)
                write(events,{'receipt_epoch':time.time(),'topic_key':'same_stamp_'+name,
                  'message':{'path':str(path),'stamp_ns':stamp(m),'sha256':hashlib.sha256(raw).hexdigest()}})
def receive(m,name):
    global stage
    counts[name]+=1;wall=time.time();data=message_to_ordereddict(m)
    if name in ('joint_states','joint_states_feedback','model_states'):
        latest[name]={'receipt_epoch':wall,'message':data}
        if wall-last_feedback.get(name,0)<.05:return
        last_feedback[name]=wall
    if name=='grasp_state':stage=m.data
    write(events,{'receipt_epoch':wall,'topic_key':name,'message':data})
sensor=[(JointState,'joint_states','/joint_states'),(JointState,'joint_states_feedback','/joint_states_feedback'),
 (JointState,'model_states','/piper_moveit_joint_states'),(CameraInfo,'depth_info','/camera/depth/camera_info'),
 (JointState,'actual_gripper_frame','/piper/gripper_feedback')]
for kind,name,topic in sensor:
    if name=='depth_info':
        def info(m):latest['depth_info']=m
        subs.append(node.create_subscription(kind,topic,info,qos_profile_sensor_data))
    else:subs.append(node.create_subscription(kind,topic,lambda m,n=name:receive(m,n),qos_profile_sensor_data))
for name,topic in [('rgb','/camera/color/image_raw'),('depth','/camera/depth/image_raw'),
 ('debug','/brain_robot_vision/debug_image'),('color_debug','/brain_robot_vision/raw_color_debug')]:
    subs.append(node.create_subscription(Image,topic,lambda m,n=name:image_receive(m,n),qos_profile_sensor_data))
for kind,name,topic,durable in [
 (String,'grasp_state','/brain_robot_grasp/state',True),
 (String,'grasp_diagnostic','/brain_robot_grasp/diagnostic',True),
 (String,'visual_state','/brain_robot_visual_control/state',True),
 (String,'visual_reason','/brain_robot_visual_control/reason',True),
 (JointTrajectory,'arm_trajectory','/brain_robot_grasp/arm_trajectory',False),
 (JointState,'gripper_command','/brain_robot_grasp/gripper_command',False),
 (JointState,'joint_commands','/joint_commands',False),
 (Bool,'software_stop','/brain_robot_control/emergency_stop',False)]:
    qos=QoSProfile(depth=20,durability=DurabilityPolicy.TRANSIENT_LOCAL) if durable else QoSProfile(depth=30)
    subs.append(node.create_subscription(kind,topic,lambda m,n=name:receive(m,n),qos))
subs.append(node.create_subscription(UInt8,'/piper/gripper_status',lambda m:receive(m,'gripper_status'),qos_profile_sensor_data))
try:
    while rclpy.ok() and not stop and time.monotonic()-started<240:
        rclpy.spin_once(node,timeout_sec=.03)
        if (ROOT.parent/'real_finished.json').exists() and time.monotonic()-started>3:break
        if not images.get('rgb'):continue
        t,rgb=next(reversed(images['rgb'].items()))
        if t==last_rgb or (t-last_rgb<3_000_000_000 and stage==last_saved):continue
        if total_bytes>=8<<20 or saved>=120:continue
        record={'RGB_stamp_ns':t,'receipt_epoch':time.time(),'stage':stage,
          'feedback_nearest_received':dict(latest),'images':{}}
        info=record['feedback_nearest_received'].get('depth_info')
        if info is not None:record['feedback_nearest_received']['depth_info']=message_to_ordereddict(info)
        chosen={'rgb':rgb}
        if images.get('depth'):
            td=min(images['depth'],key=lambda s:abs(s-t))
            if abs(td-t)<=120_000_000:chosen['depth']=images['depth'][td]
        for name in ('debug','color_debug'):
            if t in images.get(name,{}):chosen[name]=images[name][t]
        encoded=[]
        for name,m in chosen.items():
            arr=bridge.imgmsg_to_cv2(m,'passthrough' if name=='depth' else 'bgr8')
            ok,b=cv2.imencode('.png',arr);assert ok
            encoded.append((name,m,b.tobytes()))
        if total_bytes+sum(len(b) for _,_,b in encoded)>8<<20:continue
        saved+=1
        saved_rgb_snapshots[t]=saved
        for name,m,b in encoded:
            path=ROOT/f'{saved:04d}_{name}.png';path.write_bytes(b);total_bytes+=len(b)
            record['images'][name]={'path':str(path),'stamp_ns':stamp(m),'encoding':m.encoding,
              'sha256':hashlib.sha256(b).hexdigest()}
        write(samples,record);last_rgb=t;last_saved=stage
finally:
    summary={'receive_only':True,'counts':dict(counts),'saved_snapshots':saved,'image_bytes':total_bytes,
      'max_image_bytes':8<<20,'last_stage':stage,'elapsed_s':time.monotonic()-started,
      'images_timestamp_paired_not_hardware_synchronized':True,'motion_commands_sent_by_recorder':False}
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2));events.close();samples.close()
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
print(json.dumps(summary))
