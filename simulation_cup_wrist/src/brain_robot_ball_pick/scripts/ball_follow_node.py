#!/usr/bin/env python3
"""Keep the simulation ball fixed to PiPER's gripper only after a successful grasp."""

import math

import rclpy
from geometry_msgs.msg import Pose
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import Bool
from std_srvs.srv import SetBool
from tf2_ros import Buffer, TransformException, TransformListener


def _mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _conjugate(q):
    return -q[0], -q[1], -q[2], q[3]


def _normalize(q):
    norm = math.sqrt(sum(value * value for value in q))
    return (0.0, 0.0, 0.0, 1.0) if norm < 1e-9 else tuple(value / norm for value in q)


def _rotate(q, vector):
    value = _mul(_mul(q, (vector[0], vector[1], vector[2], 0.0)), _conjugate(q))
    return value[:3]


class BallFollow(Node):
    def __init__(self):
        super().__init__('ball_follow')
        for name, value in (('simulation_only', True), ('world_frame', 'world'),
                            ('gripper_frame', 'gripper_base'), ('update_rate_hz', 30.0),
                            ('ball_x', 0.40), ('ball_y', -0.12), ('ball_z', 0.0175)):
            self.declare_parameter(name, value)
        self.declare_parameter('physics_grasp', False)
        if not self.get_parameter('simulation_only').value:
            raise RuntimeError('simulation_only=false is forbidden; no real-arm command was sent')
        self.physics_grasp = bool(self.get_parameter('physics_grasp').value)
        if self.physics_grasp:
            self.get_logger().info('physics_grasp=true: ball pose following is disabled')
        self.world_frame = str(self.get_parameter('world_frame').value)
        self.gripper_frame = str(self.get_parameter('gripper_frame').value)
        self.initial = tuple(float(self.get_parameter(name).value) for name in ('ball_x', 'ball_y', 'ball_z'))
        self.position, self.orientation = self.initial, (0.0, 0.0, 0.0, 1.0)
        self.relative_position, self.relative_orientation = (0.0, 0.0, 0.0), self.orientation
        self.following = False
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.publisher = self.create_publisher(Pose, '/brain_robot_ball_pick/ball_target_pose', 1)
        self.create_service(SetBool, '/brain_robot_ball_pick/set_ball_follow', self._set_follow)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(Bool, '/brain_robot_ball_pick/scene_ready', self._scene_ready, qos)
        rate = float(self.get_parameter('update_rate_hz').value)
        if rate <= 0.0:
            raise ValueError('update_rate_hz must be positive')
        self.create_timer(1.0 / rate, self._update)

    def _scene_ready(self, message):
        if message.data:
            self.following = False
            self.position, self.orientation = self.initial, (0.0, 0.0, 0.0, 1.0)

    def _gripper(self):
        transform = self.tf_buffer.lookup_transform(self.world_frame, self.gripper_frame, Time(),
                                                    timeout=Duration(seconds=0.2)).transform
        return ((transform.translation.x, transform.translation.y, transform.translation.z),
                _normalize((transform.rotation.x, transform.rotation.y,
                            transform.rotation.z, transform.rotation.w)))

    def _set_follow(self, request, response):
        if self.physics_grasp and request.data:
            response.success, response.message = False, 'Following is disabled in physics_grasp mode.'
            return response
        if not request.data:
            self.following = False
            response.success, response.message = True, 'Ball following disabled.'
            return response
        try:
            position, orientation = self._gripper()
        except TransformException as exc:
            response.success, response.message = False, f'Cannot enable ball following: {exc}'
            return response
        inverse = _conjugate(orientation)
        self.relative_position = _rotate(inverse, tuple(self.position[index] - position[index] for index in range(3)))
        self.relative_orientation = _normalize(_mul(inverse, self.orientation))
        self.following = True
        response.success, response.message = True, 'Ball following enabled.'
        return response

    def _update(self):
        if self.physics_grasp or not self.following:
            return
        try:
            position, orientation = self._gripper()
        except TransformException:
            return
        offset = _rotate(orientation, self.relative_position)
        self.position = tuple(position[index] + offset[index] for index in range(3))
        self.orientation = _normalize(_mul(orientation, self.relative_orientation))
        message = Pose()
        message.position.x, message.position.y, message.position.z = self.position
        message.orientation.x, message.orientation.y, message.orientation.z, message.orientation.w = self.orientation
        self.publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BallFollow()
        rclpy.spin(node)
    except (KeyboardInterrupt, RuntimeError, ValueError) as exc:
        if node is not None:
            node.get_logger().error(str(exc))
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
