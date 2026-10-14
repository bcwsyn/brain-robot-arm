#!/usr/bin/env python3
"""Publish a deterministic cup pose that can follow PiPER's gripper frame."""

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


def quaternion_conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def quaternion_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quaternion_normalize(q):
    norm = math.sqrt(sum(value * value for value in q))
    if norm < 1.0e-9:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(value / norm for value in q)


def rotate_vector(q, vector):
    rotated = quaternion_multiply(
        quaternion_multiply(q, (vector[0], vector[1], vector[2], 0.0)),
        quaternion_conjugate(q))
    return rotated[0], rotated[1], rotated[2]


class CupFollow(Node):
    """Convert world-to-gripper TF into a world-frame cup target pose."""

    def __init__(self):
        super().__init__('cup_follow')
        self.declare_parameter('simulation_only', True)
        self.declare_parameter('world_frame', 'world')
        self.declare_parameter('gripper_frame', 'gripper_base')
        self.declare_parameter('update_rate_hz', 30.0)
        self.declare_parameter('cup_x', 0.40)
        self.declare_parameter('cup_y', -0.12)
        self.declare_parameter('cup_z', 0.05)
        self.declare_parameter('physics_grasp', False)

        if not self.get_parameter('simulation_only').value:
            raise RuntimeError(
                'simulation_only=false is forbidden in this package; no real-arm command was sent')
        self.physics_grasp = bool(self.get_parameter('physics_grasp').value)
        if self.physics_grasp:
            self.get_logger().info('physics_grasp=true: cup pose following is disabled')

        self.world_frame = str(self.get_parameter('world_frame').value)
        self.gripper_frame = str(self.get_parameter('gripper_frame').value)
        self.initial_position = (
            float(self.get_parameter('cup_x').value),
            float(self.get_parameter('cup_y').value),
            float(self.get_parameter('cup_z').value),
        )
        self.current_position = self.initial_position
        self.current_orientation = (0.0, 0.0, 0.0, 1.0)
        self.relative_position = (0.0, 0.0, 0.0)
        self.relative_orientation = (0.0, 0.0, 0.0, 1.0)
        self.following = False

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.pose_publisher = self.create_publisher(
            Pose, '/brain_robot_pick_place/cup_target_pose', 1)
        self.follow_service = self.create_service(
            SetBool, '/brain_robot_pick_place/set_cup_follow', self._set_follow)

        ready_qos = QoSProfile(depth=1)
        ready_qos.reliability = ReliabilityPolicy.RELIABLE
        ready_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.scene_ready_subscription = self.create_subscription(
            Bool, '/brain_robot_pick_place/scene_ready',
            self._on_scene_ready, ready_qos)

        update_rate = float(self.get_parameter('update_rate_hz').value)
        if update_rate <= 0.0:
            raise ValueError('update_rate_hz must be positive')
        self.timer = self.create_timer(1.0 / update_rate, self._update)

    def _on_scene_ready(self, message):
        if message.data:
            self.following = False
            self.current_position = self.initial_position
            self.current_orientation = (0.0, 0.0, 0.0, 1.0)

    def _lookup_gripper(self):
        transform = self.tf_buffer.lookup_transform(
            self.world_frame, self.gripper_frame, Time(),
            timeout=Duration(seconds=0.2))
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        position = (translation.x, translation.y, translation.z)
        orientation = quaternion_normalize((
            rotation.x, rotation.y, rotation.z, rotation.w))
        return position, orientation

    def _set_follow(self, request, response):
        if self.physics_grasp and request.data:
            response.success = False
            response.message = 'Following is disabled in physics_grasp mode.'
            return response
        if not request.data:
            self.following = False
            response.success = True
            response.message = 'Cup following disabled; cup stays at its last pose.'
            return response

        try:
            gripper_position, gripper_orientation = self._lookup_gripper()
        except TransformException as exc:
            response.success = False
            response.message = f'Cannot enable following: {exc}'
            return response

        inverse_gripper = quaternion_conjugate(gripper_orientation)
        delta = tuple(
            self.current_position[index] - gripper_position[index]
            for index in range(3))
        self.relative_position = rotate_vector(inverse_gripper, delta)
        self.relative_orientation = quaternion_normalize(quaternion_multiply(
            inverse_gripper, self.current_orientation))
        self.following = True
        response.success = True
        response.message = 'Cup following enabled.'
        return response

    def _update(self):
        if self.physics_grasp or not self.following:
            return
        try:
            gripper_position, gripper_orientation = self._lookup_gripper()
        except TransformException:
            return

        offset = rotate_vector(gripper_orientation, self.relative_position)
        self.current_position = tuple(
            gripper_position[index] + offset[index] for index in range(3))
        self.current_orientation = quaternion_normalize(quaternion_multiply(
            gripper_orientation, self.relative_orientation))

        message = Pose()
        message.position.x, message.position.y, message.position.z = self.current_position
        (message.orientation.x, message.orientation.y,
         message.orientation.z, message.orientation.w) = self.current_orientation
        self.pose_publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CupFollow()
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
