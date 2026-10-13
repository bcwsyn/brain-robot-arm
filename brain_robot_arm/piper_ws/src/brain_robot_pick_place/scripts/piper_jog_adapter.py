#!/usr/bin/env python3
"""Guarded JointJog-to-PiPER adapter for the physical arm.

MoveIt Servo publishes velocity-style JointJog messages, while the vendor
PiPER ROS node accepts absolute JointState positions on joint_ctrl_single.
This adapter integrates the velocities at a low rate and refuses to send
anything until the operator explicitly arms it through the Trigger service.
"""

import math
import time

import rclpy
from control_msgs.msg import JointJog
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory


def measured_finger_positions(opening_m):
    """Vendor feedback is TOTAL opening; URDF fingers move by +/- half."""
    if opening_m is None or not math.isfinite(opening_m) or not 0.0 <= opening_m <= 0.080:
        return None
    return {'joint7': opening_m / 2.0, 'joint8': -opening_m / 2.0}


class PiperJogAdapter(Node):
    def __init__(self):
        super().__init__('piper_jog_adapter')
        self.declare_parameter('motion_enabled', False)
        self.declare_parameter('input_topic', '/servo_node/delta_joint_cmds')
        self.declare_parameter('joint_state_topic', '/joint_states')
        self.declare_parameter('filtered_joint_state_topic', '/piper_moveit_joint_states')
        self.declare_parameter('output_topic', '/joint_commands')
        self.declare_parameter('emergency_stop_topic', '/brain_robot_control/emergency_stop')
        self.declare_parameter('armed_status_topic', '/brain_robot_control/adapter_armed')
        self.declare_parameter('command_timeout_s', 0.20)
        self.declare_parameter('joint_state_timeout_s', 0.30)
        self.declare_parameter('publish_rate_hz', 50.0)
        self.declare_parameter('max_velocity_rad_s', 0.035)
        self.declare_parameter('trajectory_start_tolerance_rad', 0.10)
        self.declare_parameter('trajectory_max_joint_step_rad', 0.35)
        self.declare_parameter('gripper_effort_nm', 1.0)
        self.declare_parameter('gripper_command_repeats', 5)
        self.declare_parameter('joint_min', [-1.50, -0.30, -1.40, -0.80, -1.20, -3.14159265359])
        self.declare_parameter('joint_max', [1.50, 3.14159265359, 0.40, 0.80, 1.20, 3.14159265359])
        self.declare_parameter(
            'visual_joint_max_delta_rad', [0.12, 0.02, 0.02, 0.05, 0.10, 0.05])
        self.declare_parameter('arm_trajectory_topic', '/brain_robot_grasp/arm_trajectory')
        self.declare_parameter('gripper_command_topic', '/brain_robot_grasp/gripper_command')

        self.joint_names = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
        self.last_gripper_model_warning = 0.0
        self.motion_enabled = bool(self.get_parameter('motion_enabled').value)
        self.command_timeout_s = float(self.get_parameter('command_timeout_s').value)
        self.joint_state_timeout_s = float(self.get_parameter('joint_state_timeout_s').value)
        self.publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self.max_velocity = float(self.get_parameter('max_velocity_rad_s').value)
        self.trajectory_start_tolerance = float(
            self.get_parameter('trajectory_start_tolerance_rad').value)
        self.trajectory_max_joint_step = float(
            self.get_parameter('trajectory_max_joint_step_rad').value)
        self.gripper_effort_nm = float(self.get_parameter('gripper_effort_nm').value)
        self.gripper_command_repeats = int(
            self.get_parameter('gripper_command_repeats').value)
        self.joint_min = list(self.get_parameter('joint_min').value)
        self.joint_max = list(self.get_parameter('joint_max').value)
        self.visual_joint_max_delta = list(
            self.get_parameter('visual_joint_max_delta_rad').value)
        if len(self.joint_min) != 6 or len(self.joint_max) != 6:
            raise ValueError('joint_min and joint_max must each contain six values')
        if len(self.visual_joint_max_delta) != 6 or any(
                float(value) < 0.0 for value in self.visual_joint_max_delta):
            raise ValueError('visual_joint_max_delta_rad must contain six non-negative values')
        if self.max_velocity <= 0.0 or self.publish_rate_hz <= 0.0:
            raise ValueError('max_velocity_rad_s and publish_rate_hz must be positive')
        if self.trajectory_start_tolerance <= 0.0 or self.trajectory_max_joint_step <= 0.0:
            raise ValueError('trajectory safety tolerances must be positive')
        if not 0.5 <= self.gripper_effort_nm <= 3.0:
            raise ValueError('gripper_effort_nm must stay within the driver range 0.5..3.0')
        if not 1 <= self.gripper_command_repeats <= 100:
            raise ValueError('gripper_command_repeats must stay within 1..100')

        self.positions = {}
        self.targets = {}
        self.visual_baseline = {}
        self.pending_gripper_target = None
        self.pending_gripper_frames = 0
        self.trajectory = None
        self.trajectory_start = 0.0
        self.velocities = {name: 0.0 for name in self.joint_names}
        self.last_state_time = 0.0
        self.last_command_time = 0.0
        self.last_tick = time.monotonic()
        self.armed = False

        qos = 10
        self.create_subscription(
            JointState, str(self.get_parameter('joint_state_topic').value),
            self._joint_state, qos)
        self.create_subscription(
            JointJog, str(self.get_parameter('input_topic').value),
            self._joint_jog, qos)
        self.create_subscription(
            Bool, str(self.get_parameter('emergency_stop_topic').value),
            self._emergency_stop, qos)
        self.create_subscription(
            JointTrajectory, str(self.get_parameter('arm_trajectory_topic').value),
            self._trajectory, qos)
        self.create_subscription(
            JointState, str(self.get_parameter('gripper_command_topic').value),
            self._gripper_command, qos)
        self.command_publisher = self.create_publisher(
            JointState, str(self.get_parameter('output_topic').value), qos)
        self.status_publisher = self.create_publisher(
            Bool, str(self.get_parameter('armed_status_topic').value), qos)
        self.filtered_joint_state_publisher = self.create_publisher(
            JointState, str(self.get_parameter('filtered_joint_state_topic').value), qos)
        self.arm_service = self.create_service(Trigger, '~/arm', self._arm)
        self.disarm_service = self.create_service(Trigger, '~/disarm', self._disarm)
        self.enable_service = self.create_service(Trigger, '~/enable_motion', self._enable_motion)
        self.disable_service = self.create_service(Trigger, '~/disable_motion', self._disable_motion)
        self.create_timer(1.0 / self.publish_rate_hz, self._tick)
        self._publish_armed_status()
        self.get_logger().warn(
            'PiPER physical adapter is disarmed. Set motion_enabled=true and call '
            '/piper_jog_adapter/arm only after the workspace is clear.')

    def _joint_state(self, message):
        count = min(len(message.name), len(message.position))
        filtered = JointState()
        filtered.header = message.header
        for index in range(count):
            name = message.name[index]
            if name in self.joint_names:
                position = float(message.position[index])
                self.positions[name] = position
                filtered.name.append(name)
                filtered.position.append(position)
        if len(filtered.name) == len(self.joint_names):
            opening = next((float(message.position[index]) for index in range(count)
                            if message.name[index] == 'gripper'), None)
            fingers = measured_finger_positions(opening)
            if fingers is not None:
                for name, position in fingers.items():
                    filtered.name.append(name)
                    filtered.position.append(position)
                self.filtered_joint_state_publisher.publish(filtered)
            elif time.monotonic() - self.last_gripper_model_warning > 5.0:
                self.last_gripper_model_warning = time.monotonic()
                self.get_logger().warn(
                    'No valid measured gripper opening; not publishing a fabricated finger state.')
        self.last_state_time = time.monotonic()
        if not self.armed:
            self.targets.update(self.positions)

    def _joint_jog(self, message):
        if not self.armed:
            return
        if not self._state_fresh():
            self._disarm_internal('joint state stale')
            return
        values = {name: 0.0 for name in self.joint_names}
        for index, name in enumerate(message.joint_names):
            if name in values and index < len(message.velocities):
                value = float(message.velocities[index])
                values[name] = max(-self.max_velocity, min(self.max_velocity, value))
        self.velocities = values
        self.last_command_time = time.monotonic()

    def _trajectory(self, message):
        if not self.armed or not self._state_fresh():
            return
        if not message.joint_names or not message.points:
            return
        rejection = self._trajectory_rejection_reason(message)
        if rejection is not None:
            self.get_logger().error(f'Rejecting trajectory: {rejection}')
            self._disarm_internal(f'invalid trajectory: {rejection}')
            return
        self.trajectory = message
        self.trajectory_start = time.monotonic()
        # The prepare trajectory establishes the observation pose. Visual
        # limits must be measured from that pose, not from the pre-arm posture.
        final_point = message.points[-1]
        for index, name in enumerate(message.joint_names):
            if index < len(final_point.positions) and name in self.visual_baseline:
                self.visual_baseline[name] = float(final_point.positions[index])
        self.velocities = {name: 0.0 for name in self.joint_names}
        self.last_command_time = time.monotonic()
        self.get_logger().info(
            f'REAL ARM trajectory accepted: {len(message.points)} points')

    def _trajectory_rejection_reason(self, message):
        if len(set(message.joint_names)) != len(message.joint_names):
            return 'duplicate joint name'
        if any(name not in self.joint_names for name in message.joint_names):
            return 'unknown joint name'

        previous_positions = None
        previous_time = None
        for point_index, point in enumerate(message.points):
            if len(point.positions) != len(message.joint_names):
                return f'point {point_index} position count mismatch'
            point_time = (
                float(point.time_from_start.sec) +
                float(point.time_from_start.nanosec) * 1e-9)
            if not math.isfinite(point_time) or point_time < 0.0:
                return f'point {point_index} invalid time_from_start'
            if previous_time is not None and point_time <= previous_time:
                return f'point {point_index} time_from_start is not strictly increasing'

            current_positions = []
            for index, name in enumerate(message.joint_names):
                position = float(point.positions[index])
                if not math.isfinite(position):
                    return f'point {point_index} non-finite position for {name}'
                joint_index = self.joint_names.index(name)
                if position < self.joint_min[joint_index] or position > self.joint_max[joint_index]:
                    return f'point {point_index} exceeds limit for {name}'
                if point_index == 0:
                    measured = self.positions.get(name)
                    if measured is None or abs(position - measured) > self.trajectory_start_tolerance:
                        return f'point 0 start mismatch for {name}'
                elif abs(position - previous_positions[index]) > self.trajectory_max_joint_step:
                    return f'point {point_index} joint jump for {name}'
                current_positions.append(position)
            previous_positions = current_positions
            previous_time = point_time
        return None


    def _gripper_command(self, message):
        if not message.position:
            self.get_logger().error('Rejected gripper command without a position value')
            return
        if not self.armed:
            self.get_logger().error('Rejected gripper command while adapter is disarmed')
            return
        if not self._state_fresh():
            self.get_logger().error(
                'Rejected gripper command because joint feedback is stale')
            return
        value = float(message.position[0])
        self.pending_gripper_target = max(0.0, min(0.08, value))
        self.pending_gripper_frames = self.gripper_command_repeats
        self.last_command_time = time.monotonic()
        self.get_logger().info(
            f'Accepted bounded gripper command: target={self.pending_gripper_target:.6f} m '
            f'frames={self.pending_gripper_frames}')

    def _state_fresh(self):
        return bool(self.positions) and time.monotonic() - self.last_state_time <= self.joint_state_timeout_s

    def _arm(self, _request, response):
        if not self.motion_enabled:
            response.success = False
            response.message = 'motion_enabled=false; physical motion remains locked.'
            return response
        if not self._state_fresh() or any(name not in self.positions for name in self.joint_names):
            response.success = False
            response.message = 'Fresh feedback for all six joints is required.'
            return response
        self.targets = {name: self.positions[name] for name in self.joint_names}
        self.visual_baseline = {name: self.positions[name] for name in self.joint_names}
        self.velocities = {name: 0.0 for name in self.joint_names}
        # Arming the six-axis motion path must not move the gripper. The grasp
        # executor sends an explicit bounded open/close burst when needed.
        self.pending_gripper_target = None
        self.pending_gripper_frames = 0
        self.last_command_time = 0.0
        self.armed = True
        self._publish_armed_status()
        response.success = True
        response.message = 'Adapter armed; only clamped low-speed JointJog commands are forwarded.'
        self.get_logger().warn('PHYSICAL MOTION ARMED')
        return response

    def _enable_motion(self, _request, response):
        self.motion_enabled = True
        response.success = True
        response.message = 'Motion gate enabled; call /piper_jog_adapter/arm to start output.'
        self.get_logger().warn('PHYSICAL MOTION GATE ENABLED; adapter is still disarmed')
        return response

    def _disable_motion(self, _request, response):
        self.motion_enabled = False
        self._disarm_internal('motion gate disabled')
        response.success = True
        response.message = 'Motion gate disabled and adapter disarmed.'
        return response

    def _disarm(self, _request, response):
        self._disarm_internal('operator disarm')
        response.success = True
        response.message = 'Adapter disarmed; command output is held at feedback.'
        return response

    def _disarm_internal(self, reason):
        self.armed = False
        self.trajectory = None
        self.pending_gripper_target = None
        self.pending_gripper_frames = 0
        self.velocities = {name: 0.0 for name in self.joint_names}
        self.targets.update(self.positions)
        self._publish_armed_status()
        self.get_logger().warn(f'PHYSICAL MOTION DISARMED: {reason}')

    def _publish_armed_status(self):
        if not hasattr(self, 'status_publisher'):
            return
        message = Bool()
        message.data = bool(self.armed)
        self.status_publisher.publish(message)

    def _emergency_stop(self, message):
        if message.data:
            self._disarm_internal('external emergency stop')

    def _tick(self):
        now = time.monotonic()
        dt = max(0.0, min(now - self.last_tick, 0.10))
        self.last_tick = now
        if not self.armed:
            return
        if not self._state_fresh():
            self._disarm_internal('joint state timeout')
            return
        trajectory_active = self.trajectory is not None
        if trajectory_active:
            if not self._apply_trajectory(now, dt):
                self.trajectory = None
                trajectory_active = False
        if not trajectory_active and now - self.last_command_time > self.command_timeout_s:
            self.velocities = {name: 0.0 for name in self.joint_names}
            self.targets.update(self.positions)
        if not trajectory_active:
            for index, name in enumerate(self.joint_names):
                current = self.targets.get(name, self.positions[name])
                target = current + self.velocities[name] * dt
                self.targets[name] = self._limit_visual_target(index, name, target)
        command = JointState()
        command.header.stamp = self.get_clock().now().to_msg()
        command.name = list(self.joint_names)
        command.position = [self.targets[name] for name in self.joint_names]
        self._append_pending_gripper(command)
        self.command_publisher.publish(command)

    def _append_pending_gripper(self, command):
        if self.pending_gripper_target is None or self.pending_gripper_frames <= 0:
            return False
        command.name.append('gripper')
        command.position.append(self.pending_gripper_target)
        # The vendor driver intentionally calls GripperCtrl only when the
        # explicit gripper command also carries a seventh effort entry. Keep
        # ordinary arm-only frames free of gripper data, and provide the
        # configured 1 N.m only during this short bounded burst.
        command.effort = [0.0] * len(self.joint_names) + [self.gripper_effort_nm]
        # Unit tests exercise this pure message helper without constructing
        # the rclpy Node base. Runtime instances always have ``_logger``.
        if hasattr(self, '_logger'):
            self.get_logger().info(
                f'Emitting bounded gripper frame: target={self.pending_gripper_target:.6f} m '
                f'effort={self.gripper_effort_nm:.3f} N.m '
                f'remaining={self.pending_gripper_frames - 1}')
        self.pending_gripper_frames -= 1
        if self.pending_gripper_frames == 0:
            self.pending_gripper_target = None
        return True

    def _limit_visual_target(self, index, name, desired):
        baseline = self.visual_baseline.get(name, self.positions.get(name, desired))
        delta = float(self.visual_joint_max_delta[index])
        lower = max(self.joint_min[index], baseline - delta)
        upper = min(self.joint_max[index], baseline + delta)
        return max(lower, min(upper, desired))

    def _apply_trajectory(self, now, dt):
        points = self.trajectory.points
        elapsed = now - self.trajectory_start
        max_step = self.max_velocity * max(dt, 0.0)

        def limit_target(name, desired):
            # Track the measured physical joint rather than only the previous
            # software target.  During S-V1.9-1 feedback gaps the open-loop
            # target can run ahead of the arm; when feedback resumes the arm
            # then remains short of the trajectory endpoint.  Re-anchoring
            # each bounded step to the latest measured position lets the
            # trajectory converge without increasing speed or bypassing the
            # feedback watchdog.
            current = self.positions.get(name, self.targets.get(name, 0.0))
            delta = max(-max_step, min(max_step, desired - current))
            joint_index = self.joint_names.index(name)
            return max(self.joint_min[joint_index], min(self.joint_max[joint_index], current + delta))

        def point_time(point):
            return float(point.time_from_start.sec) + float(point.time_from_start.nanosec) * 1e-9
        if len(points) == 1:
            point = points[0]
            complete = True
            for index, name in enumerate(self.trajectory.joint_names):
                if index < len(point.positions):
                    desired = float(point.positions[index])
                    self.targets[name] = limit_target(name, desired)
                    if abs(self.targets[name] - desired) > 1e-4:
                        complete = False
            return not complete
        if elapsed >= point_time(points[-1]):
            point = points[-1]
            complete = True
            for index, name in enumerate(self.trajectory.joint_names):
                if index < len(point.positions):
                    desired = float(point.positions[index])
                    self.targets[name] = limit_target(name, desired)
                    if abs(self.targets[name] - desired) > 1e-4:
                        complete = False
            return not complete
        previous = points[0]
        following = points[1]
        for candidate in points[1:]:
            if elapsed <= point_time(candidate):
                following = candidate
                break
            previous = candidate
        t0 = point_time(previous)
        t1 = point_time(following)
        alpha = 0.0 if t1 <= t0 else max(0.0, min(1.0, (elapsed - t0) / (t1 - t0)))
        for index, name in enumerate(self.trajectory.joint_names):
            if index >= len(previous.positions) or index >= len(following.positions):
                continue
            value = float(previous.positions[index]) + alpha * (
                float(following.positions[index]) - float(previous.positions[index]))
            self.targets[name] = limit_target(name, value)
        return True


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = PiperJogAdapter()
        rclpy.spin(node)
    except (KeyboardInterrupt, ValueError) as exc:
        if node is not None:
            node.get_logger().error(str(exc))
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
