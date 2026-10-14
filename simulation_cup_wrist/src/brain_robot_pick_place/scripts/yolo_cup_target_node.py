#!/usr/bin/env python3
"""Read-only cup segmentation/RGB-D target publisher with image-time TF.

Use the isolated YOLO Python interpreter. This node never commands a robot or
reads Gazebo object truth; connecting a grasp executor is a separate task.
"""
import json
from copy import deepcopy
from pathlib import Path
import time
import hashlib
from collections import OrderedDict

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, Vector3Stamped
from std_msgs.msg import Bool, String
from message_filters import Subscriber, ApproximateTimeSynchronizer
from tf2_ros import Buffer, TransformListener

from cup_perception import select_depth_valid_cup


class CupTarget(Node):
    def __init__(self):
        super().__init__('yolo_cup_target')
        model_path = self.declare_parameter('model', '').value
        if not Path(model_path).is_file():
            raise ValueError('model parameter must point to a saved cup segmentation model')
        from ultralytics import YOLO
        import torch
        torch.set_num_threads(4)
        self.model = YOLO(model_path)
        self.model_sha256 = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
        directory = self.declare_parameter('evidence_directory', '').value
        self.evidence_directory = Path(directory) if directory else None
        self.frames = OrderedDict()
        if self.evidence_directory:
            self.evidence_directory.mkdir(parents=True, exist_ok=True)
            self.create_subscription(Vector3Stamped, '/cup_task/locked_width', self.save_locked_frame, 10)
        self.cup_ids = [index for index, label in self.model.names.items() if label == 'cup']
        if self.model.task != 'segment' or len(self.cup_ids) != 1:
            raise ValueError('expected cup instance-segmentation weights')
        rgb = self.declare_parameter('rgb_topic', '/wrist_camera/wrist_camera/image_raw').value
        depth = self.declare_parameter('depth_topic', '/wrist_camera/wrist_camera/depth/image_raw').value
        info = self.declare_parameter('camera_info_topic', '/wrist_camera/wrist_camera/camera_info').value
        self.grasp_height_fraction = self.declare_parameter('grasp_height_fraction', .55).value
        self.info, self.pending = None, None
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        # Gazebo camera output and the replay fixture offer reliable images.
        # Use shallow input queues and consume only the newest paired frame.
        camera_qos = QoSProfile(depth=3, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(CameraInfo, info, lambda msg: setattr(self, 'info', msg), camera_qos)
        self.rgb = Subscriber(self, Image, rgb, qos_profile=camera_qos)
        self.depth = Subscriber(self, Image, depth, qos_profile=camera_qos)
        self.sync = ApproximateTimeSynchronizer([self.rgb, self.depth], 3, .025)
        self.sync.registerCallback(lambda rgb, depth: setattr(self, 'pending', (time.monotonic(), rgb, depth)))
        prefix = '/brain_robot_vision/'
        self.point = self.create_publisher(PointStamped, prefix+'cup_grasp_point', 1)
        self.width = self.create_publisher(Vector3Stamped, prefix+'grasp_width', 1)
        self.valid = self.create_publisher(Bool, prefix+'cup_target_valid', 1)
        self.diagnostic = self.create_publisher(String, prefix+'cup_diagnostic', 1)
        self.debug = self.create_publisher(Image, prefix+'cup_debug_image', 1)
        self.last_good = 0.
        self.create_timer(.05, self.process)

    def process(self):
        if self.pending is None or self.info is None:
            if time.monotonic()-self.last_good > .5:
                self.valid.publish(Bool(data=False))
            return
        received, rgb, depth = self.pending
        if time.monotonic()-received > .3:
            self.pending = None
            self.valid.publish(Bool(data=False))
            return
        stamp = rclpy.time.Time.from_msg(rgb.header.stamp)
        if not self.tf.can_transform('world', rgb.header.frame_id, stamp):
            return
        self.pending = None
        debug = None
        try:
            if rgb.encoding not in ('rgb8', 'bgr8') or depth.encoding != '32FC1' or rgb.width != depth.width or rgb.height != depth.height:
                raise ValueError('registered rgb8/bgr8 and 32FC1 depth are required')
            if self.info.header.frame_id != rgb.header.frame_id or depth.header.frame_id != rgb.header.frame_id:
                raise ValueError('RGB, depth and calibration frame IDs must match')
            if not 0 <= (self.get_clock().now()-stamp).nanoseconds/1e9 <= .5:
                raise ValueError('image timestamp is stale or in the future')
            color = np.ndarray((rgb.height, rgb.width, 3), np.uint8, buffer=bytes(rgb.data), strides=(rgb.step, 3, 1)).copy()
            if rgb.encoding == 'rgb8':
                color = color[:, :, ::-1]
            result = self.model.predict(color, imgsz=320, conf=.25, classes=self.cup_ids,
                device='cpu', retina_masks=True, verbose=False)[0]
            debug = Image()
            debug.header = rgb.header
            debug.height, debug.width, debug.encoding = rgb.height, rgb.width, 'bgr8'
            debug.step = rgb.width*3
            debug.data = result.plot().tobytes()
            if not len(result.boxes) or result.masks is None:
                raise ValueError('no cup segmentation instance')
            masks = result.masks.data.cpu().numpy() > .5
            z = np.ndarray((depth.height, depth.width), '<f4', buffer=bytes(depth.data), strides=(depth.step, 4))
            transform = self.tf.lookup_transform('world', rgb.header.frame_id, stamp)
            q = transform.transform.rotation
            x, y, zz, w = q.x, q.y, q.z, q.w
            rotation = np.array([[1-2*(y*y+zz*zz), 2*(x*y-zz*w), 2*(x*zz+y*w)],
                [2*(x*y+zz*w), 1-2*(x*x+zz*zz), 2*(y*zz-x*w)],
                [2*(x*zz-y*w), 2*(y*zz+x*w), 1-2*(x*x+y*y)]])
            t = transform.transform.translation
            selected, estimate, rejected = select_depth_valid_cup(z, masks,
                np.array(self.info.k).reshape(3, 3), rotation, [t.x, t.y, t.z],
                grasp_height_fraction=self.grasp_height_fraction)
            mask = masks[selected]
            estimate.update(selected_instance_index=selected,
                            detected_instances=len(result.boxes), rejected_instances=rejected)
            debug.data = result[selected].plot().tobytes()
            self.debug.publish(debug)
            point = PointStamped()
            # ROS Python messages retain assigned objects by reference.
            # Changing the output frame must not modify the incoming image.
            point.header = deepcopy(rgb.header)
            point.header.frame_id = 'world'
            point.point.x, point.point.y, point.point.z = estimate['world_target']
            size = Vector3Stamped()
            size.header = deepcopy(point.header)
            size.vector.x, size.vector.y, size.vector.z = estimate['diameter_m'], estimate['sigma_m'], estimate['preopening_m']
            if self.evidence_directory:
                self.frames[stamp.nanoseconds] = (color.copy(), z.copy(), mask.copy(),
                    np.array(self.info.k).reshape(3, 3), rotation.copy(), np.array([t.x, t.y, t.z]), estimate)
                while len(self.frames) > 12:
                    self.frames.popitem(last=False)
            self.point.publish(point)
            self.width.publish(size)
            self.valid.publish(Bool(data=True))
            self.last_good = time.monotonic()
            self.diagnostic.publish(String(data=json.dumps(dict(status='VALID', class_id=self.cup_ids[0],
                image_stamp_ns=stamp.nanoseconds, image_frame=rgb.header.frame_id, **estimate))))
            if rejected:
                self.get_logger().debug(f'Rejected unsupported YOLO masks: {rejected}')
        except Exception as error:
            if debug is not None:
                self.debug.publish(debug)
            self.valid.publish(Bool(data=False))
            self.diagnostic.publish(String(data=json.dumps(dict(status='REJECTED',
                image_frame=rgb.header.frame_id, reason=str(error)))))

    def save_locked_frame(self, width):
        stamp = rclpy.time.Time.from_msg(width.header.stamp).nanoseconds
        if stamp not in self.frames or not self.evidence_directory:
            return
        directory = self.evidence_directory / str(stamp)
        if directory.exists():
            return
        directory.mkdir()
        color, depth, mask, k, rotation, origin, estimate = self.frames[stamp]
        np.savez_compressed(directory / 'rgbd_mask_calibration.npz', bgr=color, depth_m=depth,
            mask=mask, k=k, rotation_world_camera=rotation, camera_origin_world=origin)
        cv2.imwrite(str(directory / 'rgb.png'), color)
        cv2.imwrite(str(directory / 'mask.png'), mask.astype('uint8') * 255)
        overlay = color.copy()
        overlay[mask] = (.6 * overlay[mask] + .4 * np.array([40, 210, 60])).astype('uint8')
        cv2.circle(overlay, tuple(int(v) for v in estimate['pixel']), 6, (0, 220, 255), 2)
        cv2.imwrite(str(directory / 'overlay.png'), overlay)
        (directory / 'estimate.json').write_text(json.dumps(dict(image_stamp_ns=stamp,
            model_sha256=self.model_sha256, source='learned mask and registered RGB-D',
            **estimate), indent=2) + '\n')


def main():
    rclpy.init()
    node = CupTarget()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
