#!/usr/bin/env python3
"""Bounded recorded RGB-D replay against ONE detector in isolated domain 78.

Publishes only recorded camera inputs, never robot commands or joint states.
Negative cases are labelled synthetic; timestamps are rebased, not live data.
"""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-cases', action='store_true')
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '78':
        parser.error('Only isolated domain 78 is allowed')
    import cv2
    import numpy as np
    import rclpy
    from cv_bridge import CvBridge
    from geometry_msgs.msg import PointStamped, PolygonStamped, Vector3Stamped
    from sensor_msgs.msg import CameraInfo, Image
    from std_msgs.msg import Bool, String

    rows = [json.loads(line) for line in (args.capture / 'observer.jsonl').read_text().splitlines()]
    if not rows or len(rows) > 60:
        parser.error('Expected 1..60 captured packets')
    args.output.mkdir(parents=True, exist_ok=False)
    rclpy.init()
    node = rclpy.create_node('isolated_rgbd_shape_review')
    bridge = CvBridge()
    inputs = [(Image, '/camera/color/image_raw'), (Image, '/camera/depth/image_raw'),
              (CameraInfo, '/camera/depth/camera_info')]
    pubs = [node.create_publisher(kind, topic, 10) for kind, topic in inputs]
    records, subscriptions = [], []
    current = {'case': 'discovery', 'packet': None}
    debug = {}

    def receive(message, topic):
        if isinstance(message, Image):
            debug[current['case']] = message
            return
        if isinstance(message, PolygonStamped):
            value = {'stamp_ns': message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
                     'frame': message.header.frame_id,
                     'corners': [[p.x, p.y] for p in message.polygon.points]}
            records.append({**current, 'topic': topic, 'value': value})
            return
        value = message.data if hasattr(message, 'data') else {
            'frame': message.header.frame_id,
            'stamp_ns': message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
            'xyz': [getattr(message, 'point', getattr(message, 'vector', None)).x,
                    getattr(message, 'point', getattr(message, 'vector', None)).y,
                    getattr(message, 'point', getattr(message, 'vector', None)).z]}
        records.append({**current, 'topic': topic, 'value': value})

    for kind, topic in [(Bool, 'target_valid'), (Bool, 'depth_valid'),
                       (PolygonStamped, 'qualified_color_bbox'),
                       (String, 'depth_diagnostic'), (PointStamped, 'target_point_camera'),
                       (PointStamped, 'raw_target_projection'),
                       (PointStamped, 'target_pixel'), (Vector3Stamped, 'pixel_error'),
                       (Vector3Stamped, 'target_size'), (Image, 'debug_image')]:
        subscriptions.append(node.create_subscription(kind, '/brain_robot_vision/' + topic,
            lambda message, topic=topic: receive(message, topic), 30))

    def spin_for(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.025)

    started = time.monotonic()
    try:
        spin_for(3.)
        graph = node.get_node_names()
        forbidden = ('piper', 'visual_search', 'grasp_lift', 'servo', 'move_group')
        if any(any(word in name for word in forbidden) for name in graph):
            raise RuntimeError(f'Controller present in replay domain: {graph}')
        if any(pub.get_subscription_count() != 1 for pub in pubs):
            raise RuntimeError('Each recorded camera input must have exactly one detector subscriber')
        cases = ['captured']
        if args.negative_cases:
            cases += ['zero_depth', 'no_color', 'thin_color', 'high_depth_mad']
        outcomes = {}
        for case in cases:
            current['case'] = case
            for iteration in range(10):
                if time.monotonic() - started > 90:
                    raise RuntimeError('Replay exceeded 90 seconds')
                row = rows[iteration % len(rows)]
                current['packet'] = iteration
                rgb_array = cv2.imread(row['images']['rgb']['path'])
                depth_array = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
                if rgb_array is None or depth_array is None or depth_array.dtype != np.uint16:
                    raise RuntimeError('Missing original RGB/16-bit depth')
                if case == 'zero_depth':
                    depth_array[:] = 0
                elif case == 'no_color':
                    rgb_array[:] = 0
                elif case == 'thin_color':
                    purple = rgb_array[160, 120].copy()
                    rgb_array[:] = 0
                    rgb_array[130:140, 80:200] = purple
                elif case == 'high_depth_mad':
                    # Synthetic measurement spread; original calibration/shape unchanged.
                    y, x = np.indices(depth_array.shape)
                    values = np.array([120, 180, 240], dtype=np.uint16)
                    depth_array = np.where(depth_array > 0, values[(x + y) % 3], 0).astype(np.uint16)
                rgb = bridge.cv2_to_imgmsg(rgb_array, encoding='bgr8')
                depth = bridge.cv2_to_imgmsg(depth_array, encoding='16UC1')
                info = CameraInfo()
                original_info = row['latest']['/camera/depth/camera_info']
                info.width, info.height = original_info['size']
                info.k = original_info['k']
                original = row['stamps_ns']
                shift = node.get_clock().now().nanoseconds - max(original.values())
                for message, label in ((rgb, 'rgb'), (depth, 'depth'), (info, 'depth_info')):
                    message.header.frame_id = row['images']['rgb' if label == 'rgb' else 'depth']['frame']
                    stamp = original[label] + shift
                    message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp, 10**9)
                pubs[2].publish(info)
                pubs[0].publish(rgb)
                pubs[1].publish(depth)
                spin_for(.45)
            # Ignore transition frames and delayed final synchronizer input.
            tail = [record for record in records if record['case'] == case and record['packet'] >= 5]
            outcomes[case] = {
                topic: [r['value'] for r in tail if r['topic'] == topic]
                for topic in ('target_valid', 'depth_valid', 'depth_diagnostic',
                              'target_point_camera', 'raw_target_projection', 'qualified_color_bbox',
                              'pixel_error', 'target_size')}
            if case in debug:
                cv2.imwrite(str(args.output / f'{case}_debug.png'),
                            bridge.imgmsg_to_cv2(debug[case], 'bgr8'))
        result = {'captured_replay_not_live': True, 'domain': 78, 'graph': graph,
                  'relative_timestamp_deltas_preserved': True,
                  'robot_interfaces_used': False, 'elapsed_s': time.monotonic() - started,
                  'outcomes': outcomes}
        (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        (args.output / 'messages.jsonl').write_text(
            ''.join(json.dumps(record) + '\n' for record in records))
        print(json.dumps({'elapsed_s': result['elapsed_s'], 'graph': graph,
            'cases': {case: {'target_valid': outcome['target_valid'],
                            'depth_valid': outcome['depth_valid'],
                            'diagnostics': sorted(set(outcome['depth_diagnostic']))}
                      for case, outcome in outcomes.items()}}, indent=2))
        if args.negative_cases:
            for case, outcome in outcomes.items():
                for topic in ('target_valid', 'depth_valid'):
                    values = outcome[topic]
                    if not values or any(value != (case == 'captured') for value in values):
                        raise RuntimeError(f'{case} {topic}: {values}')
            projections = outcomes['captured']['raw_target_projection']
            if not projections:
                raise RuntimeError('No colour-ray projection evidence')
            if any(point['frame'] != 'camera_depth_optical_frame'
                   for point in outcomes['captured']['target_point_camera']):
                raise RuntimeError('Target changed optical frame')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
