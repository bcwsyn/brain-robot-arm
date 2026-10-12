#!/usr/bin/env python3
"""Send one explicit close request through the already-running ROS adapter."""
import json
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import can
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState


def main():
    rclpy.init()
    node = rclpy.create_node("piper_gripper_close_once_20261012")
    pub = node.create_publisher(JointState, "/brain_robot_grasp/gripper_command", 10)
    feedback = []
    commands = []

    def feedback_cb(msg):
        positions = dict(zip(msg.name, msg.position))
        feedback.append((time.monotonic(), positions))

    node.create_subscription(JointState, "/joint_states_feedback", feedback_cb,
                             qos_profile_sensor_data)
    bus = can.interface.Bus(
        channel="can0", interface="socketcan", receive_own_messages=True,
        can_filters=[{"can_id": ident, "can_mask": 0x7FF, "extended": False}
                     for ident in (0x159, 0x3A7)])
    frames = Counter()
    tx_payloads = []
    rx_positions = Counter()
    try:
        start = time.monotonic()
        while time.monotonic() - start < 0.45:
            rclpy.spin_once(node, timeout_sec=0.01)
            packet = bus.recv(timeout=0)
            while packet is not None:
                frames[f"0x{packet.arbitration_id:03X}"] += 1
                if packet.arbitration_id == 0x159:
                    tx_payloads.append(packet.data.hex())
                elif packet.arbitration_id == 0x3A7 and len(packet.data) == 8:
                    rx_positions[(int.from_bytes(packet.data[:4], "big", signed=True),
                                  packet.data[6])] += 1
                packet = bus.recv(timeout=0)

        request = JointState()
        request.position = [0.0]
        request.header.stamp = node.get_clock().now().to_msg()
        pub.publish(request)
        command_sent = time.monotonic()
        deadline = command_sent + 2.5
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.005)
            packet = bus.recv(timeout=0)
            while packet is not None:
                frames[f"0x{packet.arbitration_id:03X}"] += 1
                if packet.arbitration_id == 0x159:
                    tx_payloads.append(packet.data.hex())
                elif packet.arbitration_id == 0x3A7 and len(packet.data) == 8:
                    rx_positions[(int.from_bytes(packet.data[:4], "big", signed=True),
                                  packet.data[6])] += 1
                packet = bus.recv(timeout=0)
        result = {
            "start_asia_shanghai": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_target_m": 0.0,
            "request_target_mm": 0.0,
            "command_sent": True,
            "command_topic": "/brain_robot_grasp/gripper_command",
            "frames": dict(frames),
            "tx_0x159_payloads": tx_payloads,
            "rx_gripper_position_status": [{"position_001mm": key[0],
                                              "status": key[1], "count": count}
                                             for key, count in rx_positions.items()],
            "ros_feedback_count": len(feedback),
            "ros_feedback_before": feedback[0][1] if feedback else None,
            "ros_feedback_after": feedback[-1][1] if feedback else None,
            "physical_commands": 1,
            "six_axis_target_sent": False,
            "zero_written": False
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        node.destroy_node()
        rclpy.shutdown()
        bus.shutdown()


if __name__ == "__main__":
    main()
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
