"""Receive original detector outputs and exact-stamp TF; no publishing/control."""
import collections,hashlib,json,time
from pathlib import Path
import cv2,numpy as np
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import PointStamped,PolygonStamped,Vector3Stamped
from sensor_msgs.msg import Image
from std_msgs.msg import Bool,String
from tf2_ros import Buffer,TransformListener
from rosidl_runtime_py.convert import message_to_ordereddict
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parent
rclpy.init();node=rclpy.create_node('cube_target_readonly_observer')
buffer=Buffer();listener=TransformListener(buffer,node)
records=[];pending=[];world=[];debug={};subs=[];saved=set();matched={}
def stamp(m):return m.header.stamp.sec*10**9+m.header.stamp.nanosec
def receive(m,name):
    if isinstance(m,Image):
        debug.setdefault(name,collections.OrderedDict())[stamp(m)]=m
        while len(debug[name])>45:debug[name].popitem(last=False)
        return
    value=message_to_ordereddict(m)
    records.append({'topic':name,'received_wall_ns':time.time_ns(),'message':value})
    if name=='target_point_camera':pending.append((m,time.monotonic()))
    if hasattr(m,'header'):
        matched.setdefault(str(stamp(m)),{})[name]=value
def matrix(m):
    p,q=m.transform.translation,m.transform.rotation
    out=np.eye(4);out[:3,:3]=Rotation.from_quat([q.x,q.y,q.z,q.w]).as_matrix();out[:3,3]=[p.x,p.y,p.z]
    return out
for kind,name in [(DiagnosticArray,'rgbd_observation'),(PointStamped,'target_point_camera'),
    (PointStamped,'target_pixel'),(PointStamped,'raw_target_projection'),
    (PolygonStamped,'qualified_color_bbox'),(PolygonStamped,'raw_color_bbox'),
    (Vector3Stamped,'target_size'),(Bool,'target_valid'),(Bool,'depth_valid'),
    (String,'depth_diagnostic'),(Image,'debug_image'),(Image,'raw_color_debug')]:
    subs.append(node.create_subscription(kind,'/brain_robot_vision/'+name,
        lambda m,name=name:receive(m,name),30))
report={'epoch':time.time(),'receive_only':True,'motion_commands_sent':False,
    'latest_TF_fallback':False,'world_points':world,'exact_stamp_debug_assets':[],
    'transform_timeouts':[],'exception':None}
try:
    end=time.monotonic()+42
    completed_at=None
    while rclpy.ok() and time.monotonic()<end:
        rclpy.spin_once(node,timeout_sec=.02)
        while pending:
            m,received=pending[0];t=rclpy.time.Time.from_msg(m.header.stamp)
            if not buffer.can_transform('base_link',m.header.frame_id,t):
                if time.monotonic()-received>2:
                    report['transform_timeouts'].append({'stamp_ns':stamp(m),'frame':m.header.frame_id});pending.pop(0)
                    continue
                break
            tf=buffer.lookup_transform('base_link',m.header.frame_id,t)
            C=buffer.lookup_transform('camera_color_optical_frame',m.header.frame_id,t)
            G=buffer.lookup_transform('base_link','gripper_base',t)
            p=np.array([m.point.x,m.point.y,m.point.z,1.]);b=matrix(tf)@p;c=matrix(C)@p
            world.append({'stamp_ns':stamp(m),'source_frame':m.header.frame_id,
                'point_depth_m':p[:3].tolist(),'point_color_m':c[:3].tolist(),
                'point_base_m':b[:3].tolist(),'base_from_depth':message_to_ordereddict(tf),
                'color_from_depth':message_to_ordereddict(C),'base_from_gripper':message_to_ordereddict(G),
                'point_semantics':'Original detector center ray at measured median surface depth; not a calibrated cube geometric center/TCP.'})
            pending.pop(0)
        observer=ROOT/'capture/observer.jsonl'
        if observer.exists():
            for line in observer.read_text().splitlines():
                try:row=json.loads(line)
                except json.JSONDecodeError:continue
                key=int(row['stamps_ns']['rgb'])
                for name in ['debug_image','raw_color_debug']:
                    pair=(key,name)
                    if pair in saved or key not in debug.get(name,{}):continue
                    m=debug[name][key]
                    channels=3 if m.encoding in ['bgr8','rgb8'] else 1
                    arr=np.frombuffer(bytes(m.data),np.uint8).reshape(m.height,m.step)[:,:m.width*channels]
                    if channels==3:arr=arr.reshape(m.height,m.width,3)
                    if m.encoding=='rgb8':arr=cv2.cvtColor(arr,cv2.COLOR_RGB2BGR)
                    path=ROOT/f'{row["snapshot"]:04d}_{name}.png'
                    if path.exists():raise FileExistsError(path)
                    assert cv2.imwrite(str(path),arr)
                    report['exact_stamp_debug_assets'].append({'snapshot':row['snapshot'],'RGB_stamp_ns':key,
                        'topic':name,'path':str(path),'SHA256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'size':[m.width,m.height],'encoding':m.encoding})
                    saved.add(pair)
            if len(observer.read_text().splitlines())==5:
                if completed_at is None:completed_at=time.monotonic()
                if time.monotonic()-completed_at>=1.:break
except BaseException as exc:report['exception']=repr(exc)
finally:
    report['end_epoch']=time.time();report['records']=records;report['stamped_observations']=matched
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'target_observation.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'world_points':len(world),'debug_assets':len(saved),'exception':report['exception']}))
raise SystemExit(0 if report['exception'] is None else 2)
