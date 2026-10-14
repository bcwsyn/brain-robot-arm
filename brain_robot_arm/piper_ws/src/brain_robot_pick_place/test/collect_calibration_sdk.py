#!/usr/bin/env python3
"""Finite passive SDK capture for calibration; no queries or motor commands.

ConnectPort(piper_init=False) starts receive threads only. Output includes stale
samples with explicit quality flags; they are never presented as actual zeros.
SDK times are aggregate receipt times, not exact per-motor hardware timestamps.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time


def snapshot(piper, now, started):
    joints = piper.GetArmJointMsgs()
    q = [getattr(joints.joint_state, f'joint_{i}') for i in range(1, 7)]
    high = piper.GetArmHighSpdInfoMsgs()
    speed = [getattr(high, f'motor_{i}').motor_speed for i in range(1, 7)]
    low = piper.GetArmLowSpdInfoMsgs()
    enabled = [bool(getattr(low, f'motor_{i}').foc_status.driver_enable_status) for i in range(1, 7)]
    gripper = piper.GetArmGripperMsgs()
    stamps = {'joint': float(joints.time_stamp), 'high': float(high.time_stamp),
              'low': float(low.time_stamp), 'gripper': float(gripper.time_stamp)}
    fresh = all(math.isfinite(t) and started < t <= now and now - t <= .5 for t in stamps.values())
    finite = all(math.isfinite(float(v)) for v in q + speed)
    row = {'epoch': now, 'sdk_receipt_stamps': {k: repr(t) for k, t in stamps.items()},
        'timestamp_scope': 'SDK aggregate receipt times; no per-motor time is invented',
        'high_hz': float(high.Hz), 'joint_hz': float(joints.Hz), 'q_mdeg': q,
        'q_driver_rad': [v / 1000. * .017444 for v in q],
        'driver_unit_conversion': 'q_mdeg / 1000 * 0.017444; original deployed driver',
        'speed_millirad_s': speed, 'enabled': enabled,
        'gripper_raw_micrometers': gripper.gripper_state.grippers_angle,
        'gripper_mm': gripper.gripper_state.grippers_angle / 1000.,
        'gripper_effort_raw': gripper.gripper_state.grippers_effort,
        'gripper_status': str(gripper.gripper_state.foc_status),
        'fresh_after_passive_connection': bool(fresh and finite and high.Hz > 0),
        'physical_contact_verified_by_sdk': False}
    return row


def summarize(samples):
    usable = [r for r in samples if r['fresh_after_passive_connection']]
    report = {'samples': len(samples), 'fresh_samples': len(usable), 'span_s': 0.,
              'static_three_seconds_and_thirty_samples': False,
              'freshness_not_per_motor_verified': True}
    if usable:
        columns = list(zip(*(r['q_mdeg'] for r in usable)))
        spread = [max(v) - min(v) for v in columns]
        span = usable[-1]['epoch'] - usable[0]['epoch']
        report.update(span_s=span, q_spread_mdeg=spread,
            static_three_seconds_and_thirty_samples=bool(len(usable) >= 30 and span >= 3. and
                max(spread) / 1000. * .017444 <= .001 and
                all(max(abs(v) for v in r['speed_millirad_s']) <= 1 for r in usable)))
    return report


def collect(output, duration_s, interface_factory=None):
    if output.exists():
        raise FileExistsError('Refusing to overwrite SDK evidence before opening any device')
    if interface_factory is None:
        # Append, not prepend: preserve system packages under PYTHONNOUSERSITE=1.
        sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages')
        from piper_sdk import C_PiperInterface_V2
        interface_factory = C_PiperInterface_V2
    samples = []
    started, begin = time.time(), time.monotonic()
    piper = interface_factory(can_name='can0', judge_flag=False, can_auto_init=False)
    error = None
    try:
        piper.CreateCanBus('can0', judge_flag=False)
        piper.ConnectPort(piper_init=False)
        while time.monotonic() - begin < duration_s:
            samples.append(snapshot(piper, time.time(), started))
            time.sleep(.1)
    except (OSError, RuntimeError, ConnectionError) as caught:
        error = repr(caught)
    finally:
        piper.DisconnectPort()
    report = {'read_only': True, 'piper_init': False, 'motion_commands_sent': False,
              'samples': samples, 'quality': summarize(samples), 'error': error}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({'output': str(output), 'quality': report['quality'], 'error': error}))
    return 0 if error is None and report['quality']['static_three_seconds_and_thirty_samples'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--duration-s', default=6., type=float)
    args = parser.parse_args()
    if not math.isfinite(args.duration_s) or not 4 <= args.duration_s <= 10:
        parser.error('Finite capture duration must be 4..10 seconds')
    return collect(args.output, args.duration_s)


if __name__ == '__main__':
    raise SystemExit(main())
