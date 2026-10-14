"""Read-only image/time-TF evidence collection from the running simulation."""
from pathlib import Path
import json
import time

import cv2
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener

output = Path(__file__).resolve().parent/'motion_frames'/str(time.time_ns())
output.mkdir(parents=True, exist_ok=False)
rclpy.init()
node = rclpy.create_node('wrist_camera_motion_evidence')
buffer = Buffer()
listener = TransformListener(buffer, node)
state, samples = 'OBSERVING', {}


def on_state(message):
    global state
    state = message.data


def on_image(message):
    if state in samples or message.header.frame_id != 'wrist_camera_optical_frame':
        return
    stamp = rclpy.time.Time.from_msg(message.header.stamp)
    if not buffer.can_transform('world', message.header.frame_id, stamp):
        return
    transform = buffer.lookup_transform('world', message.header.frame_id, stamp).transform
    frame = np.ndarray((message.height, message.width, 3), np.uint8,
                       buffer=bytes(message.data), strides=(message.step, 3, 1)).copy()
    if message.encoding == 'rgb8':
        frame = frame[:, :, ::-1]
    cv2.imwrite(str(output/(state+'.png')), frame)
    samples[state] = dict(image_stamp_ns=stamp.nanoseconds, frame_id=message.header.frame_id,
        camera_world_xyz_m=[transform.translation.x, transform.translation.y, transform.translation.z],
        camera_world_quaternion_xyzw=[transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w])
    (output/'image_time_tf.json').write_text(json.dumps(samples, indent=2)+'\n')


node.create_subscription(String, '/brain_robot_grasp/state', on_state, 10)
node.create_subscription(Image, '/wrist_camera/wrist_camera/image_raw', on_image, qos_profile_sensor_data)
deadline = time.monotonic()+200
while time.monotonic() < deadline and 'COMPLETE' not in samples:
    rclpy.spin_once(node, timeout_sec=.1)
print('Captured states:', list(samples))
node.destroy_node()
rclpy.shutdown()
