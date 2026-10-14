#!/usr/bin/env python3
"""Fit a known sphere or upright cylinder from camera pixels only.

Gazebo object positions are deliberately not subscribed to. Model dimensions
are explicit priors; XY comes from the masked RGB-D points and image-time TF.
"""
import numpy as np
import time
from collections import deque
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped
from std_msgs.msg import String
from message_filters import Subscriber, ApproximateTimeSynchronizer
from tf2_ros import Buffer, TransformListener


def fit_center(points, shape, radius, height):
    """Robust fixed-radius least squares; reject sparse or inconsistent clouds."""
    if shape == 'cylinder':
        sides = points[(points[:, 2] > .005) & (points[:, 2] < height - .005)]
        if len(sides) >= 60:
            data = sides[:, :2]
        else:
            # From above, the camera may see only the circular top cap.
            top = points[np.abs(points[:, 2]-height) < .003, :2]
            if len(top) < 100:
                raise ValueError('insufficient cylinder side or top samples')
            lower, upper = np.quantile(top, [.01, .99], axis=0)
            if np.any(upper-lower < 1.6*radius) or np.any(upper-lower > 2.2*radius):
                raise ValueError('top cap does not span a complete cylinder diameter')
            estimate = (lower+upper)/2
            distance = np.linalg.norm(top-estimate, axis=1)
            data = top[(distance > .9*radius) & (distance < 1.1*radius)]
    else:
        data = points
    dimensions = data.shape[1]
    if len(data) < (30 if shape == 'cylinder' else 60):
        raise ValueError('insufficient object surface samples')
    # Center the algebraic system to avoid cancellation at world coordinates.
    origin = data.mean(axis=0)
    local = data - origin
    solution = np.linalg.lstsq(np.column_stack((2 * local, np.ones(len(local)))),
                               (local * local).sum(axis=1), rcond=None)[0]
    center = origin + solution[:dimensions]
    for _ in range(12):
        delta = center - data
        distance = np.linalg.norm(delta, axis=1)
        residual = distance - radius
        weights = np.minimum(1., .002 / np.maximum(np.abs(residual), 1e-9))
        jacobian = delta / np.maximum(distance[:, None], 1e-9)
        step = np.linalg.lstsq(jacobian * weights[:, None], -residual * weights,
                              rcond=None)[0]
        center += step
        if np.linalg.norm(step) < 1e-7:
            break
    residual = np.abs(np.linalg.norm(data - center, axis=1) - radius)
    if not np.isfinite(center).all() or np.quantile(residual, .9) > .003:
        raise ValueError('shape fit residual exceeds 3 mm')
    if shape == 'cylinder':
        center = np.r_[center, height / 2]
    if not .05 < center[0] < .7 or not -.3 < center[1] < .3:
        raise ValueError('fitted center outside tabletop bounds')
    return center, float(np.quantile(residual, .9)), len(data)


class PhysicsTarget(Node):
    def __init__(self):
        super().__init__('physics_target')
        self.shape = self.declare_parameter('shape', 'sphere').value
        self.radius = self.declare_parameter('radius', .0175).value
        self.height = self.declare_parameter('height', .1).value
        if self.shape not in ('sphere', 'cylinder') or not 0 < self.radius < .035:
            raise ValueError('unsupported physical sample shape/radius')
        self.info = None
        self.last_warning = 0.0
        self.pending = deque(maxlen=6)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.create_subscription(CameraInfo, '/wrist_camera/wrist_camera/camera_info',
                                 lambda message: setattr(self, 'info', message), qos_profile_sensor_data)
        self.publisher = self.create_publisher(PointStamped, '/brain_robot_vision/physics_center', 1)
        self.diagnostic = self.create_publisher(String, '/brain_robot_vision/physics_fit', 1)
        self.rgb = Subscriber(self, Image, '/wrist_camera/wrist_camera/image_raw',
                              qos_profile=qos_profile_sensor_data)
        self.depth = Subscriber(self, Image, '/wrist_camera/wrist_camera/depth/image_raw',
                                qos_profile=qos_profile_sensor_data)
        self.sync = ApproximateTimeSynchronizer([self.rgb, self.depth], 10, .04)
        self.sync.registerCallback(self.on_images)
        self.create_timer(.025, self.process_pending)

    def on_images(self, rgb, depth):
        self.pending.append((time.monotonic(), rgb, depth))

    def process_pending(self):
        while self.pending:
            received, rgb, depth = self.pending[0]
            if time.monotonic()-received > .3:
                self.pending.popleft()
                continue
            if not self.tf.can_transform('world', rgb.header.frame_id,
                                         rclpy.time.Time.from_msg(rgb.header.stamp)):
                return
            self.pending.popleft()
            self.process_images(rgb, depth)

    def process_images(self, rgb, depth):
        if self.info is None or rgb.encoding not in ('rgb8', 'bgr8') or depth.encoding != '32FC1':
            return
        try:
            color = np.ndarray((rgb.height, rgb.width, 3), np.uint8, buffer=bytes(rgb.data),
                               strides=(rgb.step, 3, 1))
            if rgb.encoding == 'bgr8':
                color = color[:, :, ::-1]
            mask = (color[:, :, 0] > 90) & (color[:, :, 0] > 1.5 * color[:, :, 1].astype(float)) \
                & (color[:, :, 0] > 1.5 * color[:, :, 2].astype(float))
            z = np.ndarray((depth.height, depth.width), '<f4', buffer=bytes(depth.data),
                           strides=(depth.step, 4))
            rows, cols = np.where(mask & np.isfinite(z) & (z > .05) & (z < .8))
            rows, cols = rows[::3], cols[::3]
            if len(rows) < 60:
                raise ValueError('red depth support below 60 points: ' + str(len(rows)))
            k = self.info.k
            points = np.column_stack(((cols-k[2])*z[rows, cols]/k[0],
                                      (rows-k[5])*z[rows, cols]/k[4], z[rows, cols]))
            transform = self.tf.lookup_transform('world', rgb.header.frame_id,
                                                rclpy.time.Time.from_msg(rgb.header.stamp))
            q = transform.transform.rotation
            x, y, zz, w = q.x, q.y, q.z, q.w
            rotation = np.array([[1-2*(y*y+zz*zz), 2*(x*y-zz*w), 2*(x*zz+y*w)],
                                 [2*(x*y+zz*w), 1-2*(x*x+zz*zz), 2*(y*zz-x*w)],
                                 [2*(x*zz-y*w), 2*(y*zz+x*w), 1-2*(x*x+y*y)]])
            t = transform.transform.translation
            points = points @ rotation.T + [t.x, t.y, t.z]
            center, residual, count = fit_center(points, self.shape, self.radius, self.height)
            message = PointStamped()
            message.header = rgb.header
            message.header.frame_id = 'world'
            message.point.x, message.point.y, message.point.z = map(float, center)
            self.publisher.publish(message)
            self.diagnostic.publish(String(data=f'{self.shape} samples={count} p90_residual_m={residual:.6f}'))
        except Exception as error:
            if time.monotonic()-self.last_warning > 2:
                self.last_warning = time.monotonic()
                self.get_logger().warning(str(error))


def main():
    rclpy.init()
    node = PhysicsTarget()
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
