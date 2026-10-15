#!/usr/bin/env python3
"""Bounded GET-only camera metadata companion; no camera or arm setters.

Replies are NOT verified hardware properties: the deployed source ignores the
underlying getProperty status. Preserve zeros and failures, never invent units.
"""
import argparse
import json
import math
from pathlib import Path
import time

SERVICES = ('/camera/get_depth_exposure', '/camera/get_depth_gain')


def validate(output, duration_s):
    if output.exists():
        raise FileExistsError('Refusing to overwrite before ROS initialization')
    if not math.isfinite(duration_s) or not 1 <= duration_s <= 30:
        raise ValueError('Duration must be finite and within 1..30 seconds')


def response_record(service, response, sent_epoch, received_epoch, error=None):
    if service not in SERVICES:
        raise ValueError('Only the two fixed read-only depth getters are allowed')
    return {'service': service, 'request': {}, 'request_epoch': sent_epoch,
            'response_epoch': received_epoch,
            'raw_response': None if response is None else {
                'data': int(response.data), 'success': bool(response.success),
                'message': str(response.message)},
            'error': error, 'hardware_property_status_verified': False,
            'physical_value': None, 'physical_units': None,
            'provenance': 'Driver GetInt32 reply only; underlying device getProperty status not propagated. A zero/success reply is not verified exposure/gain.'}


def collect(output, duration_s):
    validate(output, duration_s)
    import rclpy
    from astra_camera_msgs.srv import GetInt32
    report = {'schema': 'piper_depth_controls_readonly_v1', 'read_only': True,
              'motion_commands_sent': False, 'camera_setters_called': False,
              'fixed_services': list(SERVICES), 'duration_limit_s': duration_s,
              'maximum_requests': 60, 'round_interval_s': 1.,
              'per_request_timeout_s': .8, 'records': [], 'error': None,
              'start_epoch': time.time(), 'hardware_property_status_verified': False,
              'not_image_synchronized': True}
    rclpy.init()
    node = None
    began = time.monotonic()
    pending = {}
    sent = 0
    try:
        node = rclpy.create_node('calibration_depth_controls_readonly')
        clients = {name: node.create_client(GetInt32, name) for name in SERVICES}
        deadline, next_round = began + duration_s, began
        while rclpy.ok() and time.monotonic() < deadline:
            now = time.monotonic()
            for name, (future, epoch, monotonic_sent) in list(pending.items()):
                if future.done():
                    try:
                        response = future.result()
                        report['records'].append(response_record(name, response, epoch, time.time(),
                            None if response is not None else 'empty_response'))
                    except Exception as exc:
                        report['records'].append(response_record(name, None, epoch, time.time(), repr(exc)))
                    del pending[name]
                elif now - monotonic_sent >= .8:
                    future.cancel()
                    report['records'].append(response_record(name, None, epoch, time.time(), 'response_timeout'))
                    del pending[name]
            if now >= next_round and sent < 60:
                next_round = now + 1.
                for name, client in clients.items():
                    if name in pending:
                        continue
                    if not client.service_is_ready():
                        report['records'].append(response_record(name, None, None, time.time(), 'service_not_ready'))
                        continue
                    epoch = time.time()
                    pending[name] = (client.call_async(GetInt32.Request()), epoch, time.monotonic())
                    sent += 1
            rclpy.spin_once(node, timeout_sec=max(0., min(.03, deadline-time.monotonic())))
    except KeyboardInterrupt:
        report['interrupted'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        for name, (future, epoch, _) in pending.items():
            future.cancel()
            report['records'].append(response_record(name, None, epoch, time.time(), 'observer_deadline_or_shutdown'))
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        report['end_epoch'] = time.time()
        report['elapsed_s'] = time.monotonic() - began
        report['requests_sent'] = sent
        report['raw_replies_received'] = sum(r['raw_response'] is not None for r in report['records'])
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))
    return 0 if report['raw_replies_received'] and report['error'] is None else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration-s', type=float, default=24.)
    args = parser.parse_args()
    return collect(args.output, args.duration_s)


if __name__ == '__main__':
    raise SystemExit(main())
