#!/usr/bin/env python3
"""Bounded receive-only gripper evidence; no SDK interface or CAN transmit."""
import json
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import can
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
from piper_sdk.piper_msgs.msg_v2 import PiperMessage


def main():
    started = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    parser = C_PiperParserV2()
    bus = can.interface.Bus(
        channel="can0", interface="socketcan", receive_own_messages=False,
        can_filters=[{"can_id": ident, "can_mask": 0x7FF, "extended": False}
                     for ident in (0x3A7, 0x2A8, 0x159)])
    rclpy.init()
    node = rclpy.create_node("piper_gripper_passive_20261012")
    frames = Counter()
    raw_values = Counter()
    rows = []
    feedback = []
    command_messages = []
    decode_mismatches = []

    def on_feedback(msg):
        feedback.append((time.monotonic(),
                         msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
                         dict(zip(msg.name, msg.position))))

    def on_command(msg):
        command_messages.append({"name": list(msg.name),
                                 "position": list(msg.position)})

    node.create_subscription(JointState, "/joint_states_feedback", on_feedback,
                             qos_profile_sensor_data)
    node.create_subscription(JointState, "/joint_commands", on_command,
                             qos_profile_sensor_data)
    end_at = time.monotonic() + 8.0
    try:
        while time.monotonic() < end_at:
            rclpy.spin_once(node, timeout_sec=0.002)
            packet = bus.recv(timeout=0)
            while packet is not None:
                frames[f"0x{packet.arbitration_id:03X}"] += 1
                if packet.arbitration_id in (0x3A7, 0x2A8) and len(packet.data) == 8:
                    raw_position = int.from_bytes(packet.data[:4], "big", signed=True)
                    raw_effort = int.from_bytes(packet.data[4:6], "big", signed=True)
                    status = packet.data[6]
                    raw_values[(raw_position, raw_effort, status)] += 1
                    parsed = PiperMessage()
                    mapped = can.Message(arbitration_id=0x2A8, data=packet.data,
                                         is_extended_id=False, timestamp=packet.timestamp)
                    decoded = parser.DecodeMessage(mapped, parsed)
                    sdk = parsed.gripper_feedback
                    if not decoded or (sdk.grippers_angle, sdk.grippers_effort,
                                       sdk.status_code) != (raw_position, raw_effort, status):
                        decode_mismatches.append(packet.data.hex())
                    rows.append((time.monotonic(), packet.timestamp,
                                 packet.data.hex(), raw_position, raw_effort, status))
                packet = bus.recv(timeout=0)

        now = time.monotonic()
        arm_names = [f"joint{i}" for i in range(1, 7)]
        spans = {name: max(row[2][name] for row in feedback if name in row[2]) -
                        min(row[2][name] for row in feedback if name in row[2])
                 for name in arm_names if any(name in row[2] for row in feedback)}
        raw_last = rows[-1] if rows else None
        status = raw_last[5] if raw_last else None
        result = {
            "start_asia_shanghai": started,
            "operation": "receive-only socketcan + pure SDK parser + ROS subscriptions",
            "duration_s": 8,
            "can_frame_counts": dict(frames),
            "raw_gripper_unique": [{"position_001mm": key[0],
                                    "effort_001Nm": key[1], "status": key[2],
                                    "count": count} for key, count in raw_values.items()],
            "raw_last_payload": raw_last[2] if raw_last else None,
            "raw_feedback_age_ms": (now - raw_last[0]) * 1000 if raw_last else None,
            "raw_interval_frequency_hz": ((len(rows) - 1) / (rows[-1][1] - rows[0][1]))
                                         if len(rows) > 1 else None,
            "sdk_decode_mismatches": decode_mismatches,
            "status_interpretation_sdk": {
                "fault_bits_0_to_5": status & 0x3F,
                "enabled": bool(status & 0x40),
                "homing_bit": bool(status & 0x80)
            } if status is not None else None,
            "ros_feedback_count": len(feedback),
            "ros_feedback_last": feedback[-1][2] if feedback else None,
            "ros_feedback_age_ms": (now - feedback[-1][0]) * 1000 if feedback else None,
            "ros_feedback_frequency_hz": ((len(feedback) - 1) * 10**9 /
                                           (feedback[-1][1] - feedback[0][1]))
                                          if len(feedback) > 1 else None,
            "ros_arm_spans_rad": spans,
            "observed_joint_command_count": len(command_messages),
            "joint_command_publishers": [x.node_name for x in
                                           node.get_publishers_info_by_topic("/joint_commands")],
            "enable_topic_publishers": [x.node_name for x in
                                         node.get_publishers_info_by_topic("/enable_flag")],
            "nodes": [name for name, namespace in node.get_node_names_and_namespaces()]
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        node.destroy_node()
        rclpy.shutdown()
        bus.shutdown()


if __name__ == "__main__":
    main()
