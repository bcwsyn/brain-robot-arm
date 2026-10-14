#!/usr/bin/env python3
"""Bounded receive-only calibration telemetry, never a robot controller.

Reuse the deployed driver's 0x3A0..0x3A7 receive-side ID translation before
starting SDK threads. Only /joint_states_feedback may be published. No motor
queries, services, command topics, interface activation or automatic recovery.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import time

TOPIC = '/joint_states_feedback'
NAMES = [f'joint{i}' for i in range(1, 7)]


def install_receive_parser(piper):
    def receive(message):
        if 0x3A0 <= message.arbitration_id <= 0x3A7:
            # Equivalent to the deployed receive-only Message reconstruction;
            # preserve flags/payload/timestamp and do not mutate the input.
            message = copy.copy(message)
            message.arbitration_id -= 0xFF
        piper.ParseCANFrame(message)
    piper.GetCanBus().callback_function = receive
    return receive


def feedback_values(sample, previous_stamp_ns):
    """No repeated timer stamps: header uses the actual SDK joint receipt."""
    if not sample['fresh_after_passive_connection']:
        return None
    stamp_ns = round(float(sample['sdk_receipt_stamps']['joint']) * 1e9)
    if stamp_ns <= previous_stamp_ns:
        return None
    positions = sample['q_driver_rad']
    speeds = sample['speed_millirad_s']
    if len(positions) != 6 or len(speeds) != 6 or not all(
            math.isfinite(v) for v in positions + speeds):
        return None
    return {'stamp_ns': stamp_ns, 'names': list(NAMES), 'positions': list(positions),
            'velocities': [v * .001 for v in speeds],
            'stamp_scope': 'SDK aggregate joint receipt float; not hardware or per-motor time'}


def can_link_is_up():
    try:
        return bool(int(Path('/sys/class/net/can0/flags').read_text().strip(), 16) & 1)
    except (OSError, ValueError):
        return False


def run_bridge(output, duration_s, interface_factory=None, link_reader=can_link_is_up):
    if output.exists():
        raise FileExistsError('Refusing to overwrite before opening ROS or CAN')
    if not math.isfinite(duration_s) or not 1 <= duration_s <= 120:
        raise ValueError('Finite bounded duration 1..120 seconds required')
    report = {'receive_only': True, 'piper_init': False, 'motion_commands_sent': False,
        'command_topics_or_services': False, 'topic': TOPIC, 'duration_limit_s': duration_s,
        'feedback_id_mapping': 'receive-only 0x3A0..0x3A7 -> id - 0xFF; original driver',
        'samples': 0, 'published': 0, 'suppressed_stale_or_duplicate': 0,
        'actual_last_sample': None, 'error': None}
    if not link_reader():
        report['error'] = 'can0 is missing or DOWN; no activation or recovery attempted'
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
        print(json.dumps(report, allow_nan=False))
        return 2
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from collect_calibration_sdk import snapshot
    if interface_factory is None:
        sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages')
        from piper_sdk import C_PiperInterface_V2
        interface_factory = C_PiperInterface_V2
    piper = None
    node = None
    started, began, previous = time.time(), time.monotonic(), 0
    rclpy.init()
    try:
        node = rclpy.create_node('piper_calibration_readonly_feedback')
        publisher = node.create_publisher(JointState, TOPIC, qos_profile_sensor_data)
        piper = interface_factory(can_name='can0', judge_flag=False, can_auto_init=False)
        piper.CreateCanBus('can0', judge_flag=False)
        install_receive_parser(piper)
        piper.ConnectPort(piper_init=False)
        while rclpy.ok() and time.monotonic() - began < duration_s:
            sample = snapshot(piper, time.time(), started)
            values = feedback_values(sample, previous)
            report['samples'] += 1
            if values is None:
                report['suppressed_stale_or_duplicate'] += 1
            else:
                message = JointState()
                message.header.stamp.sec, message.header.stamp.nanosec = divmod(values['stamp_ns'], 1_000_000_000)
                message.name = values['names']
                message.position = values['positions']
                message.velocity = values['velocities']
                publisher.publish(message)
                previous = values['stamp_ns']
                report['published'] += 1
                report['actual_last_sample'] = sample
            rclpy.spin_once(node, timeout_sec=.02)
    except KeyboardInterrupt:
        report['interrupted'] = True
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if piper is not None:
            piper.DisconnectPort()
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        report['elapsed_s'] = time.monotonic() - began
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
        print(json.dumps(report, allow_nan=False))
    return 0 if report['error'] is None and report['published'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--duration-s', type=float, default=15)
    args = parser.parse_args()
    return run_bridge(args.output, args.duration_s)


if __name__ == '__main__':
    raise SystemExit(main())
