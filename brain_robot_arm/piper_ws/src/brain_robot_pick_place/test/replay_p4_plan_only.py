#!/usr/bin/env python3
"""Domain-78 synthetic telemetry replay of actual executor. NEVER hardware data.

The old real q is an immutable geometry fixture, stamped now only inside this
isolated test. No driver/adapter is launched. Subscriptions count any unintended
command output, which fails the test even if MoveIt planning succeeded.
"""
import argparse
import json
import os
from pathlib import Path
import time

import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '78'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    row = json.loads(args.capture.read_text().splitlines()[0])
    rclpy.init()
    node = rclpy.create_node('p4_SYNTHETIC_plan_only_fixture')
    counts = dict(arm=0, gripper=0, joint_commands=0, emergency_stop=0)
    states = []
    subscribers = []
    for name, topic, kind in [
        ('arm', '/brain_robot_grasp/arm_trajectory', JointTrajectory),
        ('gripper', '/brain_robot_grasp/gripper_command', JointState),
        ('joint_commands', '/joint_commands', JointState),
        ('emergency_stop', '/brain_robot_control/emergency_stop', Bool),
    ]:
        def count(_message, key=name):
            counts[key] += 1
        subscribers.append(node.create_subscription(kind, topic, count, 10))
    subscribers.append(node.create_subscription(String, '/brain_robot_grasp/state',
        lambda message: states.append(message.data),
        QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
    pub = node.create_publisher(JointState, '/joint_states', 10)
    legacy = node.create_publisher(String, '/brain_robot_visual_control/state',
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    stop = node.create_publisher(Bool, '/brain_robot_control/emergency_stop', 10)

    def feedback():
        message = JointState()
        message.header.stamp = node.get_clock().now().to_msg()
        message.name = [f'joint{i}' for i in range(1, 9)]
        message.position = row['q_rad'] + [.0498, -.0498]
        message.velocity = [0.] * 8
        pub.publish(message)

    timer = node.create_timer(.02, feedback)
    client = node.create_client(Trigger, '/grasp_lift_executor/execute')
    result = {'domain': 78, 'synthetic_telemetry_only': True, 'hardware_execution': False,
              'source_q_snapshot': row['q_rad'], 'commands': counts, 'states': states}
    try:
        deadline = time.monotonic() + 40
        while 'P4_READY_FOR_EXPLICIT_EXECUTE' not in states and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
        if 'P4_READY_FOR_EXPLICIT_EXECUTE' not in states:
            raise RuntimeError('Actual executor interfaces not ready')
        # Legacy readiness must not auto-start the new mode.
        result['legacy_state_matched_subscribers'] = legacy.get_subscription_count()
        if result['legacy_state_matched_subscribers'] < 1:
            raise RuntimeError('Legacy-state fixture did not match the actual subscriber')
        legacy.publish(String(data='GRASP_READY'))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        if 'P4_FROZEN_TARGET_PLANNING' in states or any(counts.values()):
            raise RuntimeError('P4 was incorrectly started by the legacy state')
        if not client.wait_for_service(timeout_sec=3):
            raise RuntimeError('Execute service absent')
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
            if 'P4_PLAN_READY_NO_EXECUTION' in states or any(s.startswith('FAULT_') for s in states):
                break
        if not future.done() or not future.result().success:
            raise RuntimeError('Explicit execute request rejected')
        result['service_reply'] = future.result().message
        if 'P4_PLAN_READY_NO_EXECUTION' not in states or any(counts.values()):
            raise RuntimeError('Planning failed or a command was emitted')
        result['planning_commands_before_test_estop'] = dict(counts)
        # Synthetic stop: ~/execute must not clear the existing stop intent.
        stop.publish(Bool(data=True))
        deadline = time.monotonic() + 2
        while 'FAULT_ESTOP' not in states and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        if 'FAULT_ESTOP' not in states:
            raise RuntimeError('Actual executor did not acknowledge test E-stop')
        retry = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(node, retry, timeout_sec=3)
        result['test_injected_estop_messages'] = 1
        result['execute_after_estop_rejected'] = retry.done() and not retry.result().success
        if not result['execute_after_estop_rejected'] or any(counts[k] for k in ('arm', 'gripper', 'joint_commands')):
            raise RuntimeError('P4 cleared test E-stop or sent a command')
        result['passed'] = True
    except Exception as error:
        result.update(passed=False, error=repr(error))
    finally:
        node.destroy_timer(timer)
        node.destroy_node()
        rclpy.shutdown()
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2)
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 2)


if __name__ == '__main__':
    main()
