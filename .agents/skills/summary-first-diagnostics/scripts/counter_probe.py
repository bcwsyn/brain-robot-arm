#!/usr/bin/env python3
"""Bounded counter-only observation. No CAN socket, ROS, recovery or writes."""
import argparse
import json
import math
import os
from pathlib import Path
import stat
import time


def observe(read_snapshot, duration=2., interval=.25, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    window_start = None
    result = {'status': 'unknown', 'scope': 'counter_only', 'receiving': None,
              'requested_s': duration, 'elapsed_s': 0., 'samples': 0,
              'deltas': None, 'reason': None,
              'proves_joint_freshness_or_motion': False}
    try:
        first = previous = read_snapshot()
        window_start = clock()
        result['samples'] = 1
        result['identity'] = first['identity']
        while clock() - window_start < duration:
            sleep(min(interval, max(0., duration - (clock() - window_start))))
            current = read_snapshot()
            result['samples'] += 1
            if current['identity'] != first['identity']:
                result['reason'] = 'identity_changed'
                return result
            if current['values'].keys() != first['values'].keys():
                result['reason'] = 'counter_set_changed'
                return result
            if any(current['values'][key] < previous['values'][key] for key in first['values']):
                result['reason'] = 'counter_decreased_or_reset'
                return result
            previous = current
        result['deltas'] = {key: previous['values'][key] - value
                            for key, value in first['values'].items()}
        result['receiving'] = result['deltas']['rx'] > 0
        result['status'] = 'ok'
        result['reason'] = 'growth_observed' if result['receiving'] else 'no_growth_in_window'
    except (OSError, ValueError, KeyError) as exc:
        result['reason'] = type(exc).__name__ + ': ' + str(exc)[:160]
    except KeyboardInterrupt:
        result['reason'] = 'interrupted'
    finally:
        result['elapsed_s'] = round(clock() - start, 6)
        result['observed_s'] = None if window_start is None else round(clock() - window_start, 6)
    return result


def small_text(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Expected a regular counter/identity file, not a pipe/device')
        value = stream.read(257).decode('ascii')
    if len(value) > 256:
        raise ValueError('Expected a small counter/identity file')
    return value.strip()


def unsigned(path):
    value = small_text(path)
    if not value.isascii() or not value.isdecimal():
        raise ValueError('Counter is not an unsigned integer')
    return int(value)


def net_snapshot(interface, sys_root=Path('/sys/class/net')):
    root = sys_root / interface
    def identity():
        return {'boot_id': small_text('/proc/sys/kernel/random/boot_id'),
                'ifindex': unsigned(root / 'ifindex'), 'interface': interface,
                'netns': str(Path('/proc/self/ns/net').readlink())}
    before = identity()
    values = {key: unsigned(root / 'statistics' / name) for key, name in
              [('rx', 'rx_packets'), ('tx', 'tx_packets'),
               ('rx_errors', 'rx_errors'), ('tx_errors', 'tx_errors')]}
    if before != identity():
        raise ValueError('Interface changed during snapshot')
    return {'identity': before, 'values': values}


def file_snapshot(counter, identity_file):
    identity = small_text(identity_file)
    value = unsigned(counter)
    if identity != small_text(identity_file):
        raise ValueError('Identity changed during snapshot')
    return {'identity': identity, 'values': {'rx': value}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--netdev', help='Existing Linux interface, e.g. can0; never activated')
    source.add_argument('--counter-file', type=Path)
    ap.add_argument('--identity-file', type=Path, help='Required for a generic counter file')
    ap.add_argument('--duration', type=float, default=2.)
    ap.add_argument('--interval', type=float, default=.25)
    args = ap.parse_args()
    if not (math.isfinite(args.duration) and 0 < args.duration <= 3600 and
            math.isfinite(args.interval) and .01 <= args.interval <= 60):
        ap.error('duration must be (0,3600]s and interval [0.01,60]s')
    if args.netdev is not None and (not args.netdev or len(args.netdev) > 64 or '/' in args.netdev or args.netdev in ('.', '..')):
        ap.error('Expected an interface name, not a path')
    if bool(args.counter_file) != bool(args.identity_file):
        ap.error('--counter-file requires --identity-file, and vice versa')
    read = (lambda: net_snapshot(args.netdev)) if args.netdev is not None else (
        lambda: file_snapshot(args.counter_file, args.identity_file))
    result = observe(read, args.duration, args.interval)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')))
    return 0 if result['status'] == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
