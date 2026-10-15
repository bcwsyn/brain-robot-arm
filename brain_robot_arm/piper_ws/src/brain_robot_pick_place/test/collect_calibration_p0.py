#!/usr/bin/env python3
"""Bounded calibration-only batch capture, no motion or CAN recovery.

Requires an already running receive-only telemetry bridge and camera sources.
Each batch retains every raw frame; geometry identity review remains separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from calibration_p0_quality import review_frame, summarize
from collect_static_rgbd import collect
from review_depth_registration import calibration, read_config


def read_can():
    command = ['ip', '-details', '-statistics', '-json', 'link', 'show', 'can0']
    link = json.loads(subprocess.run(command, check=True, capture_output=True,
                                     text=True, timeout=2).stdout)[0]
    return {'up': 'UP' in link['flags'],
            'state': link['linkinfo']['info_data']['state'],
            'rx': link['stats64']['rx']['packets'], 'tx': link['stats64']['tx']['packets']}


def healthy_window(before, after):
    return (all(s['up'] and s['state'] == 'ERROR-ACTIVE' for s in (before, after))
            and after['rx'] > before['rx'])


def read_exposure():
    """GET only; inactive auto-exposure controls are not actual integration time."""
    result = {'epoch': time.time(), 'device': '/dev/video0',
              'scope': 'batch metadata, not synchronized per-frame exposure or measured lux'}
    try:
        command = ['v4l2-ctl', '--device', '/dev/video0', '--list-ctrls']
        raw = subprocess.run(command, capture_output=True, text=True, check=True, timeout=3)
        result['controls_raw'] = raw.stdout
        result['error'] = None
    except (OSError, subprocess.SubprocessError) as exc:
        result['controls_raw'] = None
        result['error'] = repr(exc)
    return result


def capture(output, config, batches=2, frames=60, duration_s=90.,
            can_reader=read_can, collector=collect, reviewer=review_frame, control_reader=None):
    if output.exists():
        raise FileExistsError('Refusing to overwrite before any check/capture')
    if not 1 <= batches <= 2 or not 1 <= frames <= 60 or not 4 <= duration_s <= 120:
        raise ValueError('Capture bounds: 1..2 batches, 1..60 frames, 4..120s/batch')
    params = read_config(config); camera = calibration(params)
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'piper_calibration_p0_capture_v1', 'subscription_only': True,
              'motion_commands_sent': False, 'automatic_CAN_recovery': False,
              'production_tf_modified': False, 'maximum_batches': batches,
              'maximum_seconds_per_batch': duration_s, 'maximum_image_bytes_per_batch': 64 << 20,
              'config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
              'can_checks': [], 'batches': [], 'stop_reason': None,
              'exposure': None, 'gain': None, 'illumination_lux': None,
              'formal_calibration_pair': False}
    report['camera_controls_before'] = control_reader() if control_reader else None
    all_frames = []
    try:
        for index in range(batches):
            if shutil.disk_usage(output).free < 256 << 20:
                report['stop_reason'] = 'less_than_256MiB_free'
                break
            before = can_reader(); time.sleep(.2); after = can_reader()
            check = {'before': before, 'after': after, 'healthy': healthy_window(before, after)}
            report['can_checks'].append(check)
            if not check['healthy']:
                report['stop_reason'] = 'CAN_not_UP_ERROR_ACTIVE_with_RX_growth'
                break
            folder = output / f'batch_{index + 1:02d}'
            rc = collector(folder, duration_s, frames, settle_s=3.,
                           stop_on_feedback_loss=True, max_bytes=64 << 20)
            rows = [json.loads(line) for line in (folder / 'observer.jsonl').read_text().splitlines() if line]
            quality = []
            for row in rows:
                result, _ = reviewer(row, params, camera)
                result['capture_batch'] = index + 1
                quality.append(result)
            all_frames.extend(quality)
            batch_summary = json.loads((folder / 'summary.json').read_text())
            report['batches'].append({'capture': folder.name, 'returncode': rc,
                                      'capture_summary': batch_summary, 'quality': summarize(quality)})
            if all_frames and any(abs(a - b) > .001 for frame in all_frames
                                  for a, b in zip(frame['actual_q_rad'], all_frames[0]['actual_q_rad'])):
                report['stop_reason'] = 'pose_changed_between_batches_keep_separate'
                break
            if batch_summary['stop_reason']:
                report['stop_reason'] = batch_summary['stop_reason']
                break
            if sum(f['good_top_frame'] for f in all_frames) >= 20:
                report['stop_reason'] = 'twenty_top_quality_frames_pending_physical_review'
                break
            # Do not keep collecting merely because top identity needs review.
            # Face candidates are provisional, never relabelled good top frames.
            if sum(f['face_quality_candidate'] for f in all_frames) >= 20:
                report['stop_reason'] = 'twenty_face_candidates_pending_top_review'
                break
            if rc != 0:
                report['stop_reason'] = 'incomplete_batch_do_not_blindly_retry'
                break
        if report['stop_reason'] is None:
            report['stop_reason'] = 'bounded_replenishment_exhausted'
    except KeyboardInterrupt:
        report['stop_reason'] = 'interrupted'
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        report['stop_reason'] = 'capture_or_analysis_error'
        report['error'] = repr(exc)
    finally:
        report['camera_controls_after'] = control_reader() if control_reader else None
        report['summary'] = summarize(all_frames)
        report['frames'] = all_frames
        with (output / 'p0_report.json').open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({'output': str(output), 'stop_reason': report['stop_reason'],
                      'summary': report['summary']}))
    # Raw acquisition success is not geometric/physical calibration approval.
    return 0 if report['summary']['twenty_good_frames_met'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--max-batches', type=int, default=2)
    parser.add_argument('--frames-per-batch', type=int, default=60)
    parser.add_argument('--seconds-per-batch', type=float, default=90.)
    args = parser.parse_args()
    return capture(args.output.resolve(), args.config, args.max_batches,
                   args.frames_per_batch, args.seconds_per_batch, control_reader=read_exposure)


if __name__ == '__main__':
    raise SystemExit(main())
