#!/usr/bin/env python3
"""Immutable archive timing comparison + labelled synthetic rule checks only.

No rclpy initialization, camera/SDK/CAN access, motion or production changes.
"""
import argparse
import ast
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SOURCE = ROOT/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_static_rgbd.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(label):
    folder = BASE/label
    manifest = json.loads((folder/'runtime_manifest.json').read_text())
    raw = (folder/'runtime_closed.tar.gz').read_bytes()
    assert sha(raw) == manifest['archive_sha256']
    contents = {}
    with tarfile.open(folder/'runtime_closed.tar.gz') as stream:
        for row in manifest['files']:
            data = stream.extractfile(row['path']).read()
            assert sha(data) == row['sha256']
            contents[row['path']] = data
    return contents, {'archive_sha256': sha(raw), 'raw_files_SHA_verified': len(contents)}


def load(files, name):
    return json.loads(files[name])


def event(events, name):
    return next(row for row in events if row.get('name') == name and 'argv' in row)


def log_epoch(text, pattern):
    for line in text.splitlines():
        if pattern in line:
            return float(re.search(r'\[(\d{10}\.\d+)\]', line).group(1))
    return None


def main():
    grip, grip_verified = archive('grip_capture')
    preview, preview_verified = archive('preview')
    current, current_verified = archive('manual_reset_observe')
    b = load(grip, 'RGB_only_complete/execution.json')
    b_start = event(b['events'], 'color')['epoch']
    b_first = log_epoch(grip['RGB_only_complete/color.log'].decode(), 'Publishing image #1')
    assert b_first is not None
    p = load(preview, 'execution.json')
    p_start = event(p['events'], 'color')['epoch']
    p_first = log_epoch(preview['color.log'].decode(), 'Publishing image #1')
    a = load(current, 'A_invocation_retry.qBjuiK/A_execution.json')
    a_start = event(a['events'], 'A_color')['epoch']
    a_log = current['A_invocation_retry.qBjuiK/A_color.log'].decode()
    a_signal = log_epoch(a_log, 'signal_handler')
    a_open_error = log_epoch(a_log, 'Could not open video stream')
    assert log_epoch(a_log, 'Publishing image #') is None
    assert a_signal is not None and a_open_error >= a_signal

    # Extract and exercise only the original pure predicate; do not import ROS.
    source = SOURCE.read_text()
    tree = ast.parse(source)
    predicate = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'feedback_lost')
    ns = {'MAX_AGE_NS': 500_000_000}
    exec(compile(ast.Module(body=[predicate], type_ignores=[]), str(SOURCE), 'exec'), ns)
    rule = ns['feedback_lost']
    q, now = [0.0]*6, 10_000_000_000
    scenarios = [
        ('initialization_only', [], now, 2.9, False),
        ('no_history_after_grace', [], now, 3.0, True),
        ('fresh_at_exact_500ms', [(now-500_000_000,q)], now, 7.0, False),
        ('stale_by_one_nanosecond', [(now-500_000_001,q)], now, 7.0, True),
        ('future_by_one_nanosecond', [(now+1,q)], now, 7.0, True),
        ('fresh', [(now-1_000_000,q)], now, 7.0, False)]
    examples = []
    for name, history, time_ns, elapsed, expected in scenarios:
        result = rule(deque(history), time_ns, elapsed)
        assert result is expected
        examples.append({'synthetic':True,'name':name,'predicate_result':result,
                         'last_feedback_age_ns':None if not history else time_ns-history[-1][0]})
    # The save throttle is read from the owning AST, not guessed from RGB FPS.
    collect = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'collect')
    comparisons = [node for node in ast.walk(collect) if isinstance(node, ast.Compare)
                   and isinstance(node.left, ast.BinOp)
                   and isinstance(node.left.right, ast.Name)
                   and node.left.right.id == 'latest_saved_ns']
    assert len(comparisons) == 1
    interval = ast.literal_eval(comparisons[0].comparators[0])
    assert interval == 500_000_000
    ideal_saved, last_saved = [], None
    for stamp in range(0, 60_000_000_001, 200_000_000):
        if last_saved is None or stamp-last_saved >= interval:
            ideal_saved.append(stamp)
            last_saved = stamp
        if len(ideal_saved) == 60:
            break
    assert ideal_saved[-1] == 35_400_000_000
    a_wrapper = current['read_only_A.py'].decode()
    assert '43.,60' in a_wrapper and 'camera_start < 39.' in a_wrapper
    b_delay = b_first-b_start
    a_budget = a_signal-a_start
    projected_seconds = (a_start-a['camera_start_epoch'])+b_delay+ideal_saved[-1]/1e9
    projected_preview_seconds = (a_start-a['camera_start_epoch'])+(p_first-p_start)+ideal_saved[-1]/1e9
    result = {
        'offline_only':True,'ROS_initialized':False,'devices_accessed':False,
        'production_or_capture_source_changed':False,
        'archives_verified':{'B':grip_verified,'preview':preview_verified,'current':current_verified},
        'collector_SHA':sha(source.encode()),
        'observed':{
            'B_RGB_only_success_start_epoch':b_start,'B_first_publication_epoch':b_first,
            'B_start_to_first_publication_s':b_delay,
            'preview_RGBD_start_to_first_RGB_publication_s':p_first-p_start,
            'A_RGB_start_epoch':a_start,'A_RGB_SIGINT_epoch':a_signal,
            'A_RGB_start_to_SIGINT_s':a_budget,
            'A_SIGINT_to_open_error_s':a_open_error-a_signal,
            'A_received':a['capture_summary']['received'],
            'A_matched_packets':a['capture_summary']['matched_packets'],
            'A_stop_reason':a['capture_summary']['stop_reason'],
            'A_raw_RGBD_saved':a['capture_summary']['saved_frames']},
        'strict_existing_feedback_rule_synthetic_checks':examples,
        'timing_budget':{
            'original_minimum_save_interval_s':interval/1e9,
            'absolute_lower_bound_60_frames_after_first_s':59*interval/1e9,
            'synthetic_ideal_5Hz_60_saved_span_s':ideal_saved[-1]/1e9,
            'current_camera_deadline_s':39.0,'current_collector_duration_s':43.0,
            'synthetic_using_A_launch_gap_and_historical_B_startup_total_s':projected_seconds,
            'synthetic_using_A_launch_gap_and_historical_RGBD_preview_startup_total_s':projected_preview_seconds,
            'synthetic_would_fit_39s_camera_window':projected_seconds<=39.0,
            'not_a_measurement_of_current_future_camera_startup':True},
        'conclusions':[
            'RGB source was terminated before the earlier successful RGB-only startup delay; '
            'conditions differ (depth off/on), so not proof of unique root cause.',
            'The Could not open log follows SIGINT; cannot use it alone as evidence of prior device failure.',
            'Same feedback_lost boolean covers missing, stale and future stamps. '
            'Raw stop-time source/arrival/clock trace was not saved, so the actual category is unknown.',
            '60 raw sets do not take12s at5Hz: original save throttle requires at least29.5s '
            'and ideally35.4s at exact5Hz. Current39s whole-camera budget can be insufficient.'],
        'proposal_not_implemented':{
            'scope':'Acquisition-only bounded orchestration/readiness + diagnostic timestamps; no motion or production changes.',
            'startup_budget_s':20,'original_collector_duration_s':55,
            'original_collector_frames':60,'camera_total_budget_including_cleanup_s':80,
            'bridge_duration_s':90,
            'readiness':'Observe real RGB/depth/same-stamp Info/fresh actual joints before starting formal collector. '
                        'Original collector still independently requires3s static history and original120ms/500ms rules.',
            'diagnostics':'Store source stamps, local receipt/ROS/monotonic times and exact existing stop predicate reason; '
                          'do not refresh stamps or lower original quality requirements.',
            'requires_user_approval_before_change_or_real_session':True},
        'current_formal_A_frames':0,'current_qualified_pairs':1,'B_checkpoint':'1a2e633'}
    return result


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    result=main()
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text,end='')
