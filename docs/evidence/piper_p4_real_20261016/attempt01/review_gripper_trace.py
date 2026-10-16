"""Read existing raw CAN and ROS records only; no SDK or CAN connection."""
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
events = [json.loads(s) for s in (ROOT/'real_record/events.jsonl').read_text().splitlines()]
closing = next(e['receipt_epoch'] for e in events
    if e['topic_key'] == 'grasp_state' and e['message']['data'] == 'CLOSING_GRIPPER')
lifting = next(e['receipt_epoch'] for e in events
    if e['topic_key'] == 'grasp_state' and e['message']['data'] == 'LIFTING')
source = ROOT/'onekey_logs/gripper_can.log'
pattern = re.compile(r'^\(([0-9.]+)\)\s+\S+\s+([0-9a-fA-F]+)#([0-9a-fA-F]{16})$')
counts = collections.Counter()
feedback = []
commands = []
for line in source.read_text().splitlines():
    match = pattern.match(line)
    if not match:
        continue
    t, aid, raw = float(match[1]), int(match[2], 16), bytes.fromhex(match[3])
    if aid not in (0x159, 0x2A8, 0x3A7):
        continue
    counts[hex(aid)] += 1
    item = {'CAN_receive_epoch': t, 'CAN_ID': hex(aid), 'payload_hex': raw.hex(),
        'opening_mm': int.from_bytes(raw[:4], 'big', signed=True)/1000,
        'effort_raw': int.from_bytes(raw[4:6], 'big', signed=(aid != 0x159)),
        'status_code': raw[6], 'last_byte': raw[7]}
    if aid == 0x159:
        commands.append(item)
    elif closing-.5 <= t <= lifting+1.:
        feedback.append(item)

families = collections.Counter(row['CAN_ID'] for row in feedback)
family = families.most_common(1)[0][0]
window = [r for r in feedback if r['CAN_ID'] == family and closing <= r['CAN_receive_epoch'] <= lifting]
above95 = next((r for r in window if r['opening_mm'] <= 95), None)
below5 = next((r for r in window if r['opening_mm'] <= 5), None)
transit = (below5['CAN_receive_epoch']-above95['CAN_receive_epoch']) if above95 and below5 else None
rates = []
for i, row in enumerate(window):
    later = next((r for r in window[i+1:] if r['CAN_receive_epoch']-row['CAN_receive_epoch'] >= .05), None)
    if later is not None:
        dt = later['CAN_receive_epoch']-row['CAN_receive_epoch']
        if dt <= .10:
            rates.append(abs(later['opening_mm']-row['opening_mm'])/dt)
report = {'offline_only': True, 'no_new_motion_or_gripper_command': True,
    'source': str(source), 'source_SHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'CAN_ID_counts': dict(counts), 'closing_state_receipt_epoch': closing,
    'lifting_state_receipt_epoch': lifting, 'feedback_family_used': family,
    'first_opening_95_or_less': above95, 'first_opening_5_or_less': below5,
    'observed_95_to_5_transit_s': transit,
    'observed_endpoint_delta_mm': above95['opening_mm']-below5['opening_mm'] if above95 and below5 else None,
    'observed_endpoint_mean_mm_s': (above95['opening_mm']-below5['opening_mm'])/transit if transit and transit > 0 else None,
    'maximum_observed_50_to_100ms_secant_mm_s': max(rates) if rates else None,
    'close_window_effort_raw_range': [min(r['effort_raw'] for r in window), max(r['effort_raw'] for r in window)],
    'close_window_opening_range_mm': [min(r['opening_mm'] for r in window), max(r['opening_mm'] for r in window)],
    'all_gripper_commands': commands, 'closing_feedback_raw': feedback,
    'limitations': ['Timestamps are host candump receive times, not motor-synchronized.',
        'Finite-difference speed is descriptive, not a certified motor limit.',
        'Protocol labels effort as torque (0.001 N.m), not raw current or fingertip force.',
        'A no-object closure cannot calibrate contact threshold or a safe cup force.',
        'Driver overcurrent bit is a fault indication, not a normal contact sensor.',
        'No low-effort, speed-ramp or contact-detection change is implemented by this analysis.']}
with (ROOT/'gripper_trace_review_v2.json').open('x') as f:
    json.dump(report, f, indent=2, allow_nan=False)
print(json.dumps({k:v for k,v in report.items() if k not in ('closing_feedback_raw','all_gripper_commands')}))
