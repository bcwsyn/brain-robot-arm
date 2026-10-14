"""Read-only, bounded externally, exact-stamp colour/box capture for scale logs."""
import json
from pathlib import Path
import sys
import time
import os
import math
import cv2
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PolygonStamped, PointStamped
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy

max_seconds = float(os.environ.get('BRAIN_ROBOT_CAPTURE_MAX_SECONDS', '300'))
max_mb = float(os.environ.get('BRAIN_ROBOT_CAPTURE_MAX_MB', '256'))
if not math.isfinite(max_seconds) or not 0 < max_seconds <= 600:
    raise ValueError('Capture duration must be within (0,600] seconds')
if not math.isfinite(max_mb) or not 0 < max_mb <= 512:
    raise ValueError('Capture image budget must be within (0,512] MiB')
max_bytes = int(max_mb * 1048576)
capture_started = time.monotonic()
saved_sizes = {}
saved_bytes = 0
image_budget_exhausted = False


def save_image_with_budget(path, pixels):
    global saved_bytes, image_budget_exhausted
    ok, encoded = cv2.imencode('.png', pixels)
    if not ok:
        raise RuntimeError('Cannot encode capture image')
    size = encoded.size
    total = saved_bytes + size - saved_sizes.get(str(path), 0)
    if total > max_bytes:
        image_budget_exhausted = True
        return False
    path.write_bytes(encoded.tobytes())
    saved_bytes = total
    saved_sizes[str(path)] = size
    return True


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
    if not save_image_with_budget(p, bridge.imgmsg_to_cv2(m, 'bgr8')):
        return
    row = {'kind':'rgb','stamp_ns':k,'path':str(p),'epoch':time.time(),
           'latest_feedback_not_image_time':latest.get('q'), 'state':latest.get('state')}
    if depth is not None and abs(stamp(depth)-k)<40000000:
        d = out/(str(stamp(depth))+'_depth_raw.png')
        if save_image_with_budget(d, bridge.imgmsg_to_cv2(depth, 'passthrough')):
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

def receive_observation(m):
    if len(m.status) == 1:
        emit({'kind':'rgbd_observation','stamp_ns':stamp(m),'frame':m.header.frame_id,
              'qualified':m.status[0].level == m.status[0].OK,
              'values':{v.key:v.value for v in m.status[0].values}})

def receive_debug(m):
    k=stamp(m)
    p=out/(str(k)+'_debug.png')
    if not save_image_with_budget(p, bridge.imgmsg_to_cv2(m,'bgr8')):
        return
    emit({'kind':'debug','stamp_ns':k,'path':str(p)})

for topic,kind,fn,qos in [
    ('/brain_robot_vision/rgbd_observation',DiagnosticArray,receive_observation,10),
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
    while rclpy.ok() and time.monotonic() - capture_started < max_seconds and not image_budget_exhausted and saved_bytes < max_bytes:
        rclpy.spin_once(node, timeout_sec=.1)
    reason = 'image_budget' if image_budget_exhausted or saved_bytes >= max_bytes else 'duration_budget'
    summary = {'kind': 'capture_complete', 'reason': reason, 'image_bytes': saved_bytes,
               'image_limit_bytes': max_bytes, 'max_seconds': max_seconds,
               'note': 'Recording stopped only; no arm control or stop command sent.'}
    emit(summary)
    print(json.dumps(summary), flush=True)
except KeyboardInterrupt:
    pass
finally:
    stream.close()
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
