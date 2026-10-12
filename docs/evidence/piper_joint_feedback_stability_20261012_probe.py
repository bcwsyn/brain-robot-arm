#!/usr/bin/env python3
import json
import time
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState

def main():
    rclpy.init()
    node = rclpy.create_node('piper_joint_feedback_stability_20261012')
    samples = []
    def cb(msg):
        now = time.monotonic()
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        samples.append((now, stamp, dict(zip(msg.name, msg.position))))
    node.create_subscription(JointState, '/joint_states_feedback', cb, qos_profile_sensor_data)
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.01)
    now = time.monotonic()
    intervals = [b[0] - a[0] for a, b in zip(samples, samples[1:])]
    result = {
        'duration_s': 3.0,
        'samples': len(samples),
        'frequency_hz': (len(samples) - 1) / (samples[-1][0] - samples[0][0]) if len(samples) > 1 else None,
        'max_inter_sample_gap_ms': max(intervals) * 1000 if intervals else None,
        'last_age_ms': (now - samples[-1][0]) * 1000 if samples else None,
        'last_position': samples[-1][2] if samples else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
