"""Existing-evidence analysis only. Does not import ROS or open any device."""
import bisect
import collections
import hashlib
import json
import re
import time
from pathlib import Path

START = time.monotonic()
ROOT = Path(__file__).resolve().parent
PREVIOUS = Path('/home/johnwick/brain_robot_logs/p4_gripper_only_20261016.CTeKXp/retry01')
rows = [json.loads(line) for line in (PREVIOUS/'real_record/events.jsonl').open()]
closing = next(r['receipt_epoch'] for r in rows if r['topic_key'] == 'grasp_state' and
               r['message']['data'] == 'P4_GRIPPER_TEST_CLOSING')
terminal = next(r['receipt_epoch'] for r in rows if r['topic_key'] == 'grasp_state' and
                r['message']['data'].startswith('FAULT_'))
frames = [r for r in rows if r['topic_key'] == 'actual_gripper_frame' and
          closing <= r['receipt_epoch'] < terminal]
times = [r['receipt_epoch'] for r in frames]
references = [r for r in rows if r['topic_key'] == 'gripper_command' and
              closing <= r['receipt_epoch'] < terminal-.05]
delivered = [r for r in rows if r['topic_key'] == 'joint_commands' and
             'gripper' in r['message']['name']]
delivery_times = [r['receipt_epoch'] for r in delivered]
matches = []
for ref in references:
    t = ref['receipt_epoch']
    index = bisect.bisect_left(delivery_times, t-.01)
    candidates = []
    while index < len(delivered) and delivery_times[index] <= t+.15:
        m = delivered[index]['message']
        if abs(m['position'][m['name'].index('gripper')]-ref['message']['position'][0]) < 2e-6:
            candidates.append(delivery_times[index]-t)
        index += 1
    matches.append(min(candidates, key=abs) if candidates else None)
bins = []
for start in (0, 2, 4, 6, 8, 10, 12, 14, 16, 18):
    f = [r for r in frames if closing+start <= r['receipt_epoch'] < closing+start+2]
    ref = [r for r in references if closing+start <= r['receipt_epoch'] < closing+start+2]
    gaps = []
    for r in ref:
        i = bisect.bisect_right(times, r['receipt_epoch'])-1
        if i >= 0:
            gaps.append((frames[i]['message']['position'][0]-r['message']['position'][0])*1000)
    if f:
        bins.append({'start_s': start, 'actual_mm': [f[0]['message']['position'][0]*1000,
                                                   f[-1]['message']['position'][0]*1000],
                     'actual_frames': len(f), 'references': len(ref),
                     'reference_error_mm': [min(gaps), max(gaps)] if gaps else None})
driver = (PREVIOUS/'onekey_logs/piper_driver.log').read_text()
calls = [(float(t), int(angle)/1000) for t, angle in re.findall(
    r'\[([0-9]+\.[0-9]+)\] \[piper_ctrl_single_node\]: Calling GripperCtrl: angle=(\d+)', driver)]
late = [v for t, v in calls if closing+10 < t < terminal-.05]
nominal_time = ((.0994-(3**.5*.029+.006))/.010 +
                ((3**.5*.029+.006)-.025)/.003 + 5)
report = {'input': str(PREVIOUS),
          'events_sha256': hashlib.sha256((PREVIOUS/'real_record/events.jsonl').read_bytes()).hexdigest(),
          'no_hardware_access': True, 'closing_duration_s': terminal-closing,
          'reference_delivery_within_150ms': {
              'sent': len(matches), 'matched': sum(m is not None for m in matches),
              'unmatched': sum(m is None for m in matches),
              'not_unique_one_to_one_acknowledgement': True},
          'late_driver_calls': len(late), 'late_driver_target_range_mm': [min(late), max(late)],
          'two_second_bins': bins, 'old_nominal_timeout_s': nominal_time,
          'observed_first8s_speed_mm_s': (99.4-90.7)/8,
          'observed_stall_does_not_identify_physical_cause': True,
          'elapsed_analysis_s': time.monotonic()-START}
(ROOT/'response_analysis.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k: v for k, v in report.items() if k != 'two_second_bins'}, indent=2))
