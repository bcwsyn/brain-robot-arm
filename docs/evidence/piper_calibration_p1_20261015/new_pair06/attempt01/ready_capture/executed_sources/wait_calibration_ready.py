#!/usr/bin/env python3
"""Bounded four-source readiness; subscription only, no image saving or motion."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from collect_static_rgbd import (TOPICS, ReceiptDiagnostics, checked_packet,
                                synchronizer)


def wait_ready(output, listening, duration_s=20.):
    if output.exists() or listening.exists():
        raise FileExistsError('Refusing to overwrite readiness evidence before ROS initialization')
    if not 1 <= duration_s <= 20:
        raise ValueError('Readiness duration must be 1..20 seconds')
    import message_filters
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image, JointState
    report = {'subscription_only': True, 'motion_commands_sent': False, 'ready': False,
              'max_duration_s': duration_s, 'received': {}, 'rejected': {}, 'error': None}
    counts, rejected, diagnostics = Counter(), Counter(), ReceiptDiagnostics()
    rclpy.init()
    node = rclpy.create_node('calibration_four_source_readiness')
    began = time.monotonic()

    def receive(message, topic):
        counts[topic] += 1
        diagnostics.observe(topic, message, node.get_clock().now().nanoseconds,
                            time.time_ns(), time.monotonic_ns())

    def matched(rgb, depth, info, joints):
        try:
            packet = checked_packet(rgb, depth, info, joints, node.get_clock().now().nanoseconds)
            report.update(ready=True, ready_packet=packet, ready_epoch=time.time(),
                          ready_monotonic_ns=str(time.monotonic_ns()))
        except (ValueError, KeyError) as exc:
            rejected[str(exc)] += 1

    try:
        subscribers = [message_filters.Subscriber(node, kind, topic, qos_profile=qos_profile_sensor_data)
                       for kind, topic in zip((Image, Image, CameraInfo, JointState), TOPICS)]
        for subscriber, topic in zip(subscribers, TOPICS):
            subscriber.registerCallback(receive, topic)
        sync = synchronizer(subscribers)
        sync.registerCallback(matched)
        with listening.open('x') as stream:
            json.dump({'subscribers_created': True, 'not_proof_of_messages': True,
                       'epoch': time.time()}, stream)
        while rclpy.ok() and not report['ready'] and time.monotonic()-began < duration_s:
            rclpy.spin_once(node, timeout_sec=.05)
    except KeyboardInterrupt:
        report['interrupted'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        report.update(received=dict(counts), rejected=dict(rejected), elapsed_s=time.monotonic()-began,
                      receipt_diagnostics=diagnostics.snapshot())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        with output.open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report), flush=True)
    return 0 if report['ready'] and report['error'] is None else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--listening', type=Path, required=True)
    parser.add_argument('--duration-s', type=float, default=20.)
    args = parser.parse_args()
    raise SystemExit(wait_ready(args.output, args.listening, args.duration_s))
