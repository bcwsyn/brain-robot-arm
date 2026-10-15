#!/usr/bin/env python3
"""Finite, subscription-only static RGB-D/real-feedback evidence collection.

No controller, enable, planning or motion interfaces. Timestamp pairing is not
hardware synchronization, camera calibration or permission to grasp.
"""
import argparse
from collections import Counter, deque
import hashlib
import json
import math
from pathlib import Path
import time


NAMES = tuple(f'joint{i}' for i in range(1, 7))
SLOP_NS = 120_000_000
MAX_AGE_NS = 500_000_000
TOPICS = ('/camera/color/image_raw', '/camera/depth/image_raw',
          '/camera/depth/camera_info', '/joint_states_feedback')


def stamp_ns(message):
    stamp = message.header.stamp
    if stamp.sec < 0 or not 0 <= stamp.nanosec < 1_000_000_000:
        raise ValueError('invalid timestamp')
    value = stamp.sec * 1_000_000_000 + stamp.nanosec
    if value == 0:
        raise ValueError('zero timestamp')
    return value


def joint_positions(message):
    if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
        raise ValueError('invalid joint names or positions')
    positions = dict(zip(message.name, message.position))
    q = [positions[name] for name in NAMES]
    if not all(math.isfinite(value) for value in q):
        raise ValueError('nonfinite joints')
    return q


def checked_packet(rgb, depth, info, feedback, now_ns):
    stamps = [stamp_ns(message) for message in (rgb, depth, info, feedback)]
    if max(stamps) - min(stamps) > SLOP_NS:
        raise ValueError('timestamp span exceeds 120ms')
    if min(stamps) > now_ns or max(stamps) > now_ns or now_ns - min(stamps) > MAX_AGE_NS:
        raise ValueError('old or future input')
    if stamps[1] != stamps[2]:
        raise ValueError('depth info is not from the same frame')
    if depth.header.frame_id != info.header.frame_id or (depth.width, depth.height) != (info.width, info.height):
        raise ValueError('depth/info frame or size mismatch')
    if rgb.width <= 0 or rgb.height <= 0 or depth.width <= 0 or depth.height <= 0:
        raise ValueError('empty image size')
    if len(info.k) != 9 or not all(math.isfinite(value) for value in info.k) or info.k[0] <= 0 or info.k[4] <= 0:
        raise ValueError('invalid depth intrinsics')
    if depth.encoding not in ('16UC1', 'mono16'):
        raise ValueError('unexpected depth encoding; do not infer units')
    return {'stamps_ns': dict(zip(('rgb', 'depth', 'depth_info', 'feedback'), stamps)),
            'stamp_span_s': (max(stamps) - min(stamps)) / 1e9,
            'oldest_age_s': (now_ns - min(stamps)) / 1e9,
            'q_rad': joint_positions(feedback)}


def settled_feedback(history, q, reference_ns, window_s=.25):
    """Require an observed 250ms static window, not one zero-velocity message."""
    duration_ns = int(window_s * 1e9)
    window = [(stamp, values) for stamp, values in history
              if reference_ns - duration_ns - 50_000_000 <= stamp <= reference_ns]
    return (len(window) >= 3 and window[-1][0] - window[0][0] >= duration_ns
            and all(abs(a - b) <= 0.001 for _, values in window for a, b in zip(values, q)))


def full_camera_info(info):
    """Retain the actual same-depth-frame message, not a factory replacement."""
    return {'stamp_ns': str(stamp_ns(info)), 'frame': info.header.frame_id,
            'size': [info.width, info.height], 'distortion_model': info.distortion_model,
            'k': list(info.k), 'd': list(info.d), 'r': list(info.r), 'p': list(info.p),
            'binning_x': info.binning_x, 'binning_y': info.binning_y,
            'roi': {name: getattr(info.roi, name) for name in
                    ('x_offset', 'y_offset', 'height', 'width', 'do_rectify')}}


def synchronizer(filters):
    from message_filters import ApproximateTimeSynchronizer
    return ApproximateTimeSynchronizer(filters, queue_size=100, slop=SLOP_NS / 1e9,
                                      allow_headerless=False)


def feedback_lost(history, now_ns, elapsed_s):
    """P0 opt-in: allow initialization, then stop on missing/stale source stamps."""
    if elapsed_s < 3.:
        return False
    return not history or now_ns - history[-1][0] > MAX_AGE_NS or history[-1][0] > now_ns


def collect(output, duration_s, frames, settle_s=.25, stop_on_feedback_loss=False,
            max_bytes=None):
    import cv2
    from cv_bridge import CvBridge
    import message_filters
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image, JointState

    output.mkdir(parents=True, exist_ok=False)
    evidence = output / 'evidence'
    evidence.mkdir()
    summary = {'subscription_only': True, 'hardware_synchronized': False,
               'camera_calibration': False, 'topics': list(TOPICS),
               'message_filters_file': message_filters.__file__,
               'slop_s': SLOP_NS / 1e9, 'max_age_s': MAX_AGE_NS / 1e9,
               'requested_frames': frames, 'saved_frames': 0,
               'static_window_s': settle_s, 'full_same_frame_depth_info': True,
               'received': {}, 'rejected': {}, 'matched_packets': 0,
               'stop_on_feedback_loss': stop_on_feedback_loss,
               'image_byte_limit': max_bytes, 'image_bytes': 0, 'stop_reason': None}
    received, rejected, history = Counter(), Counter(), deque(maxlen=1000)
    start_q, latest_saved_ns = None, 0
    bridge = CvBridge()
    rclpy.init()
    node = rclpy.create_node('piper_static_rgbd_evidence')
    stream = (output / 'observer.jsonl').open('x', encoding='utf-8')

    def receive(message, topic):
        received[topic] += 1
        if topic == TOPICS[3]:
            try:
                history.append((stamp_ns(message), joint_positions(message)))
            except (ValueError, KeyError):
                rejected['bad_feedback'] += 1

    def matched(rgb, depth, info, feedback):
        nonlocal start_q, latest_saved_ns
        summary['matched_packets'] += 1
        try:
            packet = checked_packet(rgb, depth, info, feedback, node.get_clock().now().nanoseconds)
            if not settled_feedback(history, packet['q_rad'], packet['stamps_ns']['feedback'], settle_s):
                raise ValueError(f'feedback not settled for {settle_s:g}s')
            if start_q is not None and any(abs(a - b) > 0.001 for a, b in zip(start_q, packet['q_rad'])):
                raise ValueError('static pose changed')
            if packet['stamps_ns']['rgb'] - latest_saved_ns < 500_000_000:
                return
            row = {'epoch': time.time(), 'snapshot': summary['saved_frames'] + 1,
                   'timestamp_paired_not_hardware_sync': True, **packet,
                   'latest': {TOPICS[3]: {'stamp': packet['stamps_ns']['feedback'] / 1e9,
                                         'positions': dict(zip(NAMES, packet['q_rad'])),
                                         'raw_names': list(feedback.name),
                                         'raw_positions': list(feedback.position),
                                         'raw_velocity': list(feedback.velocity),
                                         'raw_effort': list(feedback.effort),
                                         'frame': feedback.header.frame_id},
                              TOPICS[2]: dict(full_camera_info(info),
                                  stamp=packet['stamps_ns']['depth_info'] / 1e9)},
                   'images': {}}
            encoded_images = []
            for label, message, encoding in (('rgb', rgb, 'bgr8'), ('depth', depth, 'passthrough')):
                ok, encoded = cv2.imencode('.png', bridge.imgmsg_to_cv2(message, encoding))
                if not ok:
                    raise RuntimeError('image encoding failed')
                encoded_images.append((label, message, encoded))
            if max_bytes is not None and summary['image_bytes'] + sum(e.nbytes for _, _, e in encoded_images) > max_bytes:
                summary['stop_reason'] = 'image_byte_limit'
                return
            for label, message, encoded in encoded_images:
                path = evidence / f"{row['snapshot']:04d}_{label}.png"
                with path.open('xb') as image_stream:
                    image_stream.write(encoded.tobytes())
                summary['image_bytes'] += encoded.nbytes
                row['images'][label] = {'path': str(path), 'stamp': packet['stamps_ns'][label] / 1e9,
                                        'frame': message.header.frame_id,
                                        'source_encoding': message.encoding,
                                        'size': [message.width, message.height],
                                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            stream.write(json.dumps(row, allow_nan=False) + '\n')
            stream.flush()
            start_q = packet['q_rad']
            latest_saved_ns = packet['stamps_ns']['rgb']
            summary['saved_frames'] += 1
        except (ValueError, KeyError) as error:
            rejected[str(error)] += 1

    subscribers = [message_filters.Subscriber(node, kind, topic, qos_profile=qos_profile_sensor_data)
                   for kind, topic in zip((Image, Image, CameraInfo, JointState), TOPICS)]
    for subscriber, topic in zip(subscribers, TOPICS):
        subscriber.registerCallback(receive, topic)
    sync = synchronizer(subscribers)
    sync.registerCallback(matched)
    started = time.monotonic()
    try:
        while rclpy.ok() and time.monotonic() - started < duration_s and summary['saved_frames'] < frames:
            rclpy.spin_once(node, timeout_sec=0.05)
            if stop_on_feedback_loss and feedback_lost(history, node.get_clock().now().nanoseconds,
                                                       time.monotonic() - started):
                summary['stop_reason'] = 'feedback_lost'
            if summary['stop_reason'] is not None:
                break
    except KeyboardInterrupt:
        summary['interrupted'] = True
    except Exception as error:
        summary['error'] = repr(error)
        raise
    finally:
        summary.update({'received': dict(received), 'rejected': dict(rejected),
                        'elapsed_s': time.monotonic() - started, 'start_q_rad': start_q})
        stream.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        with (output / 'summary.json').open('x', encoding='utf-8') as handle:
            json.dump(summary, handle, indent=2, allow_nan=False)
        print(json.dumps(summary, allow_nan=False))
    return 0 if summary['saved_frames'] == frames else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new, nonexistent evidence directory')
    parser.add_argument('--duration-s', type=float, default=30)
    parser.add_argument('--frames', type=int, default=15)
    parser.add_argument('--settle-s', type=float, default=.25,
                        help='static evidence window; use 3 for new calibration datasets')
    args = parser.parse_args()
    if not math.isfinite(args.duration_s) or not 1 <= args.duration_s <= 120 or not 1 <= args.frames <= 60:
        parser.error('finite duration must be 1..120s and frames 1..60')
    if not math.isfinite(args.settle_s) or not .25 <= args.settle_s <= 5:
        parser.error('static evidence window must be .25..5s')
    return collect(args.output.resolve(), args.duration_s, args.frames, args.settle_s)


if __name__ == '__main__':
    raise SystemExit(main())
