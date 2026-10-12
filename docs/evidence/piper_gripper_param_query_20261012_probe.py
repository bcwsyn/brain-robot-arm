#!/usr/bin/env python3
"""Single metadata query, opt-in; never instantiate a control SDK interface."""
import argparse
import json
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import can
from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
from piper_sdk.piper_msgs.msg_v2 import (
    ArmMsgParamEnquiryAndConfig, ArmMsgType, PiperMessage)


def main():
    options = argparse.ArgumentParser()
    options.add_argument("--query-once", action="store_true")
    args = options.parse_args()
    parser = C_PiperParserV2()
    request = PiperMessage()
    request.type_ = ArmMsgType.PiperMsgParamEnquiryAndConfig
    request.arm_param_enquiry_and_config = ArmMsgParamEnquiryAndConfig(
        param_enquiry=0x04, param_setting=0,
        data_feedback_0x48x=0, end_load_param_setting_effective=0,
        set_end_load=0x03)
    tx = can.Message(is_extended_id=False)
    parser.EncodeMessage(request, tx)
    assert tx.arbitration_id == 0x477
    assert bytes(tx.data) == bytes.fromhex("0400000003000000")
    result = {"start_asia_shanghai": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
              "query_id": "0x477", "query_payload": bytes(tx.data).hex(),
              "query_count": 0, "settings_written": False,
              "physical_motion_commands": 0, "opt_in": args.query_once}
    if not args.query_once:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    ids = (0x47E, 0x477, 0x3A7, 0x3A4, 0x3A5, 0x3A6, 0x159)
    counts = Counter()
    before = {}
    after = {}
    replies = []
    gripper = Counter()
    bus = can.interface.Bus(
        channel="can0", interface="socketcan", receive_own_messages=True,
        can_filters=[{"can_id": ident, "can_mask": 0x7FF, "extended": False}
                     for ident in ids])

    def observe(duration, positions, allow_reply=False):
        end_at = time.monotonic() + duration
        while time.monotonic() < end_at:
            packet = bus.recv(timeout=0.02)
            if packet is None:
                continue
            counts[f"0x{packet.arbitration_id:03X}"] += 1
            if packet.arbitration_id in (0x3A4, 0x3A5, 0x3A6) and len(packet.data) == 8:
                base = (packet.arbitration_id - 0x3A4) * 2 + 1
                positions[f"joint{base}"] = int.from_bytes(packet.data[:4], "big", signed=True)
                positions[f"joint{base + 1}"] = int.from_bytes(packet.data[4:], "big", signed=True)
            elif packet.arbitration_id == 0x3A7 and len(packet.data) == 8:
                gripper[(int.from_bytes(packet.data[:4], "big", signed=True),
                         packet.data[6])] += 1
            elif packet.arbitration_id == 0x47E and allow_reply:
                decoded = PiperMessage()
                assert parser.DecodeMessage(packet, decoded)
                fields = decoded.arm_gripper_teaching_param_feedback
                replies.append({"raw": packet.data.hex(), "timestamp": packet.timestamp,
                                "teaching_range_per": fields.teaching_range_per,
                                "max_range_config_mm": fields.max_range_config,
                                "teaching_friction": fields.teaching_friction})

    try:
        observe(0.3, before)
        if len(before) != 6 or not gripper:
            raise RuntimeError("Fresh passive arm/gripper feedback absent; query not sent")
        result["query_sent_wall_time_s"] = time.time()
        bus.send(tx, timeout=0.1)
        result["query_count"] = 1
        observe(1.5, after, allow_reply=True)
        result.update({
            "frame_counts": dict(counts), "replies": replies,
            "arm_before_001deg": before, "arm_after_001deg": after,
            "arm_delta_001deg": {name: after.get(name, before[name]) - before[name]
                                 for name in before},
            "gripper_position_status": [{"position_001mm": key[0],
                                          "status": key[1], "count": count}
                                         for key, count in gripper.items()],
            "query_echo_note": "0x477 is SocketCAN local echo, not proof of device ACK",
            "real_open_close_verified": False})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
