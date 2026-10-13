"""Read-only, bounded externally, exact-stamp colour/box capture for scale logs."""
import json
from pathlib import Path
import sys
import time
import cv2
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PolygonStamped, PointStamped
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
stream = (out/'frames.jsonl').open('w')
rclpy.init()
node = rclpy.create_node('read_only_scale_frame_capture')
bridge = CvBridge()
latest = {}
depth = None
saved_rgb = set()
subscriptions = []

def stamp(m):
    return m.header.stamp.sec*10**9+m.header.stamp.nanosec

def emit(row):
    stream.write(json.dumps(row)+'\n')
    stream.flush()

def receive_rgb(m):
    k = stamp(m)
    if k in saved_rgb:
        return
    saved_rgb.add(k)
    p = out/(str(k)+'_rgb.png')
    cv2.imwrite(str(p), bridge.imgmsg_to_cv2(m, 'bgr8'))
    row = {'kind':'rgb','stamp_ns':k,'path':str(p),'epoch':time.time(),
           'latest_feedback_not_image_time':latest.get('q'), 'state':latest.get('state')}
    if depth is not None and abs(stamp(depth)-k)<40000000:
        d = out/(str(stamp(depth))+'_depth_raw.png')
        cv2.imwrite(str(d), bridge.imgmsg_to_cv2(depth, 'passthrough'))
        row.update(depth_path=str(d), depth_stamp_ns=stamp(depth))
    emit(row)

def receive_depth(m):
    global depth
    depth = m

def receive_box(m):
    emit({'kind':'qualified_box','stamp_ns':stamp(m),'frame':m.header.frame_id,
          'corners':[[p.x,p.y] for p in m.polygon.points]})

def receive_point(m):
    emit({'kind':'raw_point','stamp_ns':stamp(m),'frame':m.header.frame_id,
          'xyz':[m.point.x,m.point.y,m.point.z]})

def receive_feedback(m):
    latest['q']={'stamp_ns':stamp(m),'positions':dict(zip(m.name,m.position))}

def receive_state(m):
    latest['state']=m.data
    emit({'kind':'state','epoch':time.time(),'state':m.data})

def receive_debug(m):
    k=stamp(m)
    p=out/(str(k)+'_debug.png')
    cv2.imwrite(str(p),bridge.imgmsg_to_cv2(m,'bgr8'))
    emit({'kind':'debug','stamp_ns':k,'path':str(p)})

for topic,kind,fn,qos in [
    ('/camera/color/image_raw',Image,receive_rgb,qos_profile_sensor_data),
    ('/camera/depth/image_raw',Image,receive_depth,qos_profile_sensor_data),
    ('/joint_states_feedback',JointState,receive_feedback,qos_profile_sensor_data),
    ('/brain_robot_vision/qualified_color_bbox',PolygonStamped,receive_box,10),
    ('/brain_robot_vision/target_point_camera',PointStamped,receive_point,10),
    ('/brain_robot_vision/debug_image',Image,receive_debug,qos_profile_sensor_data),
    ('/brain_robot_grasp/state',String,receive_state,
     QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL))]:
    subscriptions.append(node.create_subscription(kind,topic,fn,qos))
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    stream.close()
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
