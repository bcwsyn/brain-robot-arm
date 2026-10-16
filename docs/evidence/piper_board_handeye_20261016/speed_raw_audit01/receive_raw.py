"""Receive-only per-CAN-frame speed/angle audit, bounded to 12s/40000 frames."""
from pathlib import Path
import hashlib
import json
import socket
import struct
import sys
import time

sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages')
import can
from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
from piper_sdk.piper_msgs.msg_v2 import PiperMessage

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent


def link():
    import subprocess
    return json.loads(subprocess.check_output(['ip', '-details', '-statistics', '-json', 'link', 'show', 'can0']))[0]


def main():
    before = link()
    assert 'UP' in before['flags'] and before['linkinfo']['info_data']['state'] == 'ERROR-ACTIVE'
    parser = C_PiperParserV2()
    rows = []
    with socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as receiver:
        receiver.settimeout(.2)
        receiver.bind(('can0',))
        began = time.monotonic()
        while time.monotonic()-began < 12 and len(rows) < 40000:
            try:
                payload = receiver.recv(16)
            except socket.timeout:
                continue
            stamp = time.time_ns()
            canid, length, data = struct.unpack('=IB3x8s', payload)
            if canid & ~0x7ff or length != 8:
                continue
            row = {'receipt_epoch_ns': str(stamp), 'elapsed_s': time.monotonic()-began,
                   'can_id': hex(canid), 'data_hex': data.hex()}
            if 0x251 <= canid <= 0x256:
                row['joint'] = canid-0x250
                row['independent_speed_raw'] = int.from_bytes(data[:2], 'big', signed=True)
                row['independent_motor_pos_raw'] = int.from_bytes(data[4:8], 'big', signed=True)
                decoded = PiperMessage()
                assert parser.DecodeMessage(can.Message(arbitration_id=canid, data=data, is_extended_id=False), decoded)
                motor = getattr(decoded, 'arm_high_spd_feedback_'+str(row['joint']))
                row['SDK_speed_raw'] = motor.motor_speed
                row['SDK_motor_pos_raw'] = motor.pos
                assert row['SDK_speed_raw'] == row['independent_speed_raw']
                assert row['SDK_motor_pos_raw'] == row['independent_motor_pos_raw']
            elif canid in (0x2a5, 0x2a6, 0x2a7, 0x3a4, 0x3a5, 0x3a6):
                first = 0x2a5 if canid < 0x300 else 0x3a4
                row['joint_pair'] = [2*(canid-first)+1, 2*(canid-first)+2]
                row['aggregate_joint_mdeg'] = [int.from_bytes(data[:4], 'big', signed=True), int.from_bytes(data[4:8], 'big', signed=True)]
            rows.append(row)
    after = link()
    assert before['stats64']['tx']['packets'] == after['stats64']['tx']['packets']
    report = {'receive_only': True, 'socket_send_or_SDK_connect_called': False,
              'local_receipt_not_hardware_timestamps': True, 'can_before': before, 'can_after': after,
              'rows': len(rows), 'elapsed_s': rows[-1]['elapsed_s'], 'joints': []}
    from collections import Counter
    report['all_received_standard_ID_counts'] = dict(Counter(r['can_id'] for r in rows))
    for joint in range(1, 7):
        high = [r for r in rows if r.get('joint') == joint]
        angles = [r['aggregate_joint_mdeg'][r['joint_pair'].index(joint)] for r in rows if joint in r.get('joint_pair', [])]
        pulse = [r for r in high if abs(r['independent_speed_raw']) > 1]
        report['joints'].append({'joint': joint, 'high_frames': len(high), 'all_SDK_independent_decode_agree': True,
            'speed_min_max_raw': [min(r['SDK_speed_raw'] for r in high), max(r['SDK_speed_raw'] for r in high)],
            'speed_outside_original_static_threshold_frames': len(pulse),
            'motor_pos_min_max_raw': [min(r['SDK_motor_pos_raw'] for r in high), max(r['SDK_motor_pos_raw'] for r in high)],
            'aggregate_angle_min_max_mdeg': [min(angles), max(angles)] if angles else None,
            'first_five_pulses': pulse[:5]})
    raw = ''.join(json.dumps(r, separators=(',', ':'))+'\n' for r in rows).encode()
    with (ROOT/'raw_receive.jsonl').open('xb') as stream:
        stream.write(raw)
    report['raw_SHA256'] = hashlib.sha256(raw).hexdigest()
    (ROOT/'raw_assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('rows', 'elapsed_s', 'joints')}, indent=2))


if __name__ == '__main__':
    main()
