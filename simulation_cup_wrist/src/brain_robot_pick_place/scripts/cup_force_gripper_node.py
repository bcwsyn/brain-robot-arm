#!/usr/bin/env python3
"""Exclusive Gazebo jaw command owner for the cup task; force feedback is in N."""
import json
import math
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from control_msgs.msg import JointTrajectoryControllerState
from gazebo_msgs.msg import ContactsState
from geometry_msgs.msg import Vector3Stamped
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from adaptive_gripper_policy import ContactForcePolicy, opening_from_measurement
from contact_force_feedback import target_normal_force, target_axis_force
from tf2_ros import Buffer, TransformListener


class CupForceGripper(Node):
    def __init__(self):
        super().__init__('cup_force_gripper')
        if os.environ.get('ROS_DOMAIN_ID') != '85' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
            raise RuntimeError('Cup force integration requires isolated localhost ROS domain 85')
        if not self.get_parameter('use_sim_time').value:
            raise RuntimeError('Gazebo use_sim_time=true is required')
        self.model = self.declare_parameter('target_model', 'medicine_cup').value
        self.policy = ContactForcePolicy(
            minimum_force_n=self.declare_parameter('minimum_force_n', 2.5).value,
            maximum_force_n=self.declare_parameter('maximum_force_n', 3.5).value,
            hard_force_limit_n=self.declare_parameter('hard_force_limit_n', 5.0).value)
        self.mode, self.request_id, self.state = 'IDLE', 0, 'IDLE'
        self.command = .100
        self.center_offset = 0.
        self.previous_targets = None
        self.open_sent = False
        self.last_open_send = -1.
        self.positions, self.position_time = [0., 0.], [0., 0.]
        self.forces, self.force_time = [0., 0.], [0., 0.]
        self.force_error = ['', '']
        self.gross_forces, self.axis_age = [0., 0.], [0., 0.]
        self.tf = Buffer()
        self.tf_listener = TransformListener(self.tf, self)
        self.width, self.width_time = None, 0.
        self.last_clock, self.started, self.stable_since = 0., 0., 0.
        self.low_force_since = None
        self.allow_fault_injection = self.declare_parameter('allow_fault_injection', False).value
        self.injected_fault = ''
        self.injection_time = 0.
        self.pending_overforce = False
        self.relief_started = 0.
        self.healthy = self.create_publisher(Bool, '/cup_gripper/healthy', 1)
        self.status = self.create_publisher(String, '/cup_gripper/status', 10)
        self.diagnostic = self.create_publisher(String, '/cup_gripper/diagnostic', 10)
        self.jaw_publishers, self.feedback_subscriptions = [], []
        for index, controller in enumerate(('gripper_controller', 'gripper8_controller')):
            self.jaw_publishers.append(self.create_publisher(JointTrajectory, f'/{controller}/joint_trajectory', 1))
            self.feedback_subscriptions.append(self.create_subscription(JointTrajectoryControllerState,
                f'/{controller}/controller_state', lambda msg, i=index: self.on_position(msg, i), 10))
            self.feedback_subscriptions.append(self.create_subscription(ContactsState,
                f'/brain_robot_physics/link{index+7}_contacts', lambda msg, i=index: self.on_force(msg, i),
                qos_profile_sensor_data))
        self.create_subscription(Vector3Stamped, '/cup_task/locked_width', self.on_width, 10)
        self.command_services = [self.create_service(Trigger, f'/cup_gripper/{mode}',
            lambda req, res, mode=mode: self.request(mode, res)) for mode in ('open', 'preopen', 'capture', 'stop')]
        self.command_services.extend(self.create_service(Trigger, f'/cup_gripper/inject_{fault}',
            lambda req, res, fault=fault: self.inject(fault, res))
            for fault in ('feedback_loss', 'overforce'))
        self.create_timer(.025, self.tick)

    def on_position(self, msg, index):
        if len(msg.feedback.positions) == 1 and math.isfinite(msg.feedback.positions[0]):
            self.positions[index] = msg.feedback.positions[0]
            self.position_time[index] = time.monotonic()

    def on_force(self, msg, index):
        if self.injected_fault == 'feedback_loss' and index == 0:
            return
        try:
            if msg.header.frame_id != 'world':
                raise ValueError('world-frame Gazebo contact feedback is required')
            self.gross_forces[index], points = target_normal_force(msg, self.model, require_step_time=True)
            if points:
                stamp = rclpy.time.Time.from_msg(msg.header.stamp)
                sample = stamp if self.tf.can_transform('world', f'link{index+7}', stamp) else rclpy.time.Time()
                transform = self.tf.lookup_transform('world', f'link{index+7}', sample)
                age = (rclpy.time.Time.from_msg(msg.header.stamp) -
                       rclpy.time.Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
                if not -.02 <= age <= .15:
                    raise ValueError('jaw-axis transform is stale')
                q = transform.transform.rotation
                length = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
                x, y, z, w = [v/length for v in (q.x, q.y, q.z, q.w)]
                axis = (2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y))
                self.forces[index], _ = target_axis_force(msg, self.model, axis)
                self.axis_age[index] = age
            else:
                self.forces[index] = 0.
            self.force_error[index] = ''
        except Exception as error:
            self.force_error[index] = str(error)
        self.force_time[index] = time.monotonic()

    def on_width(self, msg):
        self.width, self.width_time = msg, time.monotonic()

    def request(self, mode, response):
        if mode == 'stop' and self.mode == 'RELIEF':
            # Arm cancellation must not cancel bounded overload relief.
            response.success, response.message = True, 'Overload relief continues; task remains faulted'
            return response
        if mode == 'capture' and (self.mode != 'PREOPEN' or self.state != 'PREOPEN_COMPLETE'):
            response.success, response.message = False, 'Capture requires completed measured preopening'
            return response
        if mode == 'preopen' and self.mode not in ('IDLE', 'OPEN', 'STOP'):
            response.success, response.message = False, 'Preopening requires idle/open state'
            return response
        self.request_id += 1
        self.mode, self.state = mode.upper(), 'STARTING'
        self.started, self.stable_since = time.monotonic(), 0.
        self.last_clock = self.get_clock().now().nanoseconds / 1e9
        if mode == 'preopen':
            self.width = None
            self.state = 'AWAITING_WIDTH'
        if mode == 'open':
            self.command = .100
        if mode in ('open', 'preopen'):
            self.center_offset = 0.
            self.open_sent = False
            self.last_open_send = -1.
            self.previous_targets = None
        response.success, response.message = True, str(self.request_id)
        return response

    def inject(self, fault, response):
        response.success = self.allow_fault_injection and self.mode == 'HOLD'
        response.message = 'Simulation fault injected' if response.success else 'Fault injection disabled or no held object'
        if response.success:
            self.injected_fault, self.injection_time = fault, time.monotonic()
            self.pending_overforce = fault == 'overforce'
        return response

    def publish_command(self):
        # The stock parallel gripper has one opening command. Keep symmetric
        # jaw commands; do not invent independently translated hardware jaws.
        self.center_offset = 0.
        targets = [self.command / 2 * (1 if i == 0 else -1) for i in range(2)]
        for index, publisher in enumerate(self.jaw_publishers):
            trajectory = JointTrajectory()
            trajectory.joint_names = [f'joint{index+7}']
            start = JointTrajectoryPoint()
            # Streaming a single endpoint lets the controller restart from
            # blocked measured position, repeatedly erasing PID preload.
            # Explicitly continue from the previous commanded endpoint.
            start.positions = [self.previous_targets[index] if self.previous_targets is not None
                               else self.positions[index]]
            point = JointTrajectoryPoint()
            point.positions = [targets[index]]
            point.time_from_start.nanosec = 600_000_000 if self.mode in ('OPEN', 'PREOPEN') else 25_000_000
            trajectory.points = [start, point]
            publisher.publish(trajectory)
        self.previous_targets = targets

    def tick(self):
        wall = time.monotonic()
        clock = self.get_clock().now().nanoseconds / 1e9
        dt = min(.1, max(.001, clock - self.last_clock))
        self.last_clock = clock
        healthy = self.mode == 'HOLD'
        if self.mode not in ('IDLE', 'STOP', 'FAULT'):
            fault = ''
            if any(self.count_publishers(p.topic_name) != 1 for p in self.jaw_publishers):
                fault = 'MULTIPLE_JAW_COMMAND_OWNERS'
            elif max(wall - t for t in self.position_time) > .5:
                fault = 'STALE_JAW_FEEDBACK'
            elif self.mode in ('CAPTURE', 'HOLD', 'RELIEF') and max(wall - t for t in self.force_time) > .2:
                fault = 'STALE_FORCE_FEEDBACK'
            elif self.mode in ('CAPTURE', 'HOLD', 'RELIEF') and any(self.force_error):
                fault = 'INVALID_FORCE_FEEDBACK'
            if fault:
                self.mode, self.state, healthy = 'FAULT', 'FAULT_' + fault, False
            elif self.mode in ('OPEN', 'PREOPEN'):
                if self.mode == 'PREOPEN' and self.state == 'AWAITING_WIDTH':
                    try:
                        if self.width is None or wall - self.width_time > .5:
                            raise ValueError('missing fresh locked width')
                        age = (self.get_clock().now() - rclpy.time.Time.from_msg(self.width.header.stamp)).nanoseconds / 1e9
                        self.command = opening_from_measurement(self.width.vector.x,
                            self.width.vector.y, age).opening_m
                        if abs(self.command - self.width.vector.z) > 1e-6:
                            raise ValueError('inconsistent opening packet')
                        self.state = 'MOVING'
                    except ValueError as error:
                        if wall - self.started > 5:
                            self.mode, self.state = 'FAULT', 'FAULT_WIDTH_' + str(error)
                if self.mode != 'FAULT' and self.state != 'AWAITING_WIDTH':
                    if self.state not in ("OPEN_COMPLETE", "PREOPEN_COMPLETE") and (
                            not self.open_sent or clock - self.last_open_send >= .2):
                        if all(p.get_subscription_count() > 0 for p in self.jaw_publishers):
                            self.publish_command()
                            self.open_sent, self.last_open_send = True, clock
                    measured = self.positions[0] - self.positions[1]
                    if wall - self.started > .3 and abs(measured - self.command) < .001:
                        self.state = self.mode + '_COMPLETE'
                    elif wall - self.started > 8:
                        self.mode, self.state = 'FAULT', 'FAULT_OPENING_TIMEOUT'
            elif self.mode in ('CAPTURE', 'HOLD'):
                if self.pending_overforce:
                    self.forces[0] = max(6., self.forces[0])
                    self.pending_overforce = False
                if self.mode == 'HOLD' and min(self.forces) < .3:
                    self.low_force_since = self.low_force_since or clock
                    if clock - self.low_force_since > .15:
                        self.mode, self.state, healthy = 'FAULT', 'FAULT_LOST_BILATERAL_FORCE', False
                        self.healthy.publish(Bool(data=False))
                        self.status.publish(String(data=f'{self.request_id}:{self.state}'))
                        return
                else:
                    self.low_force_since = None
                decision = self.policy.step(self.command, *self.forces,
                    max(wall - t for t in self.force_time), dt)
                self.command = decision.next_opening_m
                if decision.force_in_band:
                    # Regulate near the middle of the accepted band rather
                    # than resting just above its lower edge after capture.
                    target = (self.policy.minimum_force_n + self.policy.maximum_force_n) / 2
                    error = target - sum(self.forces) / 2
                    if abs(error) > .05:
                        change = max(-self.policy.closing_speed_m_s * dt,
                                     min(self.policy.closing_speed_m_s * dt, .001 * error * dt))
                        self.command = max(0., min(.100, self.command - change))
                self.publish_command()
                if decision.fault:
                    self.mode = 'RELIEF' if decision.state == 'BACKOFF_OVERFORCE' else 'FAULT'
                    self.relief_started = clock
                    self.state, healthy = 'FAULT_' + decision.state, False
                elif decision.force_in_band:
                    if not self.stable_since:
                        self.stable_since = clock
                    if clock - self.stable_since >= .5:
                        self.mode, self.state, healthy = 'HOLD', 'FORCE_STABLE', True
                else:
                    self.stable_since = 0.
                    self.state = decision.state
                if self.mode == 'CAPTURE' and wall - self.started > 20:
                    self.mode, self.state = 'FAULT', 'FAULT_CONTACT_TIMEOUT'
            elif self.mode == 'RELIEF':
                healthy = False
                if max(self.forces) <= self.policy.maximum_force_n:
                    self.mode, self.state = 'FAULT', 'FAULT_OVERFORCE_RELIEVED'
                elif clock - self.relief_started > 2.:
                    self.mode, self.state = 'FAULT', 'FAULT_RELIEF_TIMEOUT'
                else:
                    self.command = min(.100, self.command + self.policy.closing_speed_m_s * dt)
                    self.publish_command()
            # STOP freezes the last command; it never silently releases a held cup.
        self.healthy.publish(Bool(data=healthy))
        self.status.publish(String(data=f'{self.request_id}:{self.state}'))
        self.diagnostic.publish(String(data=json.dumps(dict(request_id=self.request_id,
            mode=self.mode, state=self.state, sim_time_s=clock, force_n=self.forces,
            command_opening_m=self.command, measured_opening_m=self.positions[0] - self.positions[1],
            command_center_offset_m=self.center_offset,
            gross_point_normal_load_n=self.gross_forces, jaw_axis_tf_age_s=self.axis_age,
            force_feedback_errors=self.force_error,
            force_age_s=[wall - t for t in self.force_time], healthy=healthy,
            ready_for_commands=(max(wall - t for t in self.position_time) <= .25
                and max(wall - t for t in self.force_time) <= .15
                and all(self.count_publishers(p.topic_name) == 1 and p.get_subscription_count() > 0
                        for p in self.jaw_publishers)),
            injected_fault=self.injected_fault,
            width_stamp_ns=(rclpy.time.Time.from_msg(self.width.header.stamp).nanoseconds if self.width else None)))))


def main():
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = CupForceGripper()
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
