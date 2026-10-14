"""Replay real good/hole RGB-D frames into one domain-78 detector. No robot topics."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

import cv2
from cv_bridge import CvBridge
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Vector3Stamped
import rclpy
from sensor_msgs.msg import CameraInfo, Image
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detector-bin', required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--good-stamp', type=int, default=1791906280183270225)
    parser.add_argument('--hole-stamp', type=int, default=1791906282184497764)
    parser.add_argument('--check-rgb-error', action='store_true')
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '78' or args.output.exists():
        parser.error('Domain 78 and a new output directory are required')
    rows = [json.loads(s) for s in (args.capture/'frames.jsonl').read_text().splitlines()]
    info = next(json.loads(s)['latest']['/camera/depth/camera_info']
                for s in args.observer.read_text().splitlines()
                if '"snapshot"' in s and '"/camera/depth/camera_info"' in s)
    inputs = {label: next(r for r in rows if r['kind'] == 'rgb' and r['stamp_ns'] == stamp)
              for label, stamp in [('good', args.good_stamp), ('hole', args.hole_stamp)]}
    args.output.mkdir()
    rclpy.init()
    node = rclpy.create_node('offline_same_frame_quality_replay')
    bridge = CvBridge()
    rgb_pub = node.create_publisher(Image, '/camera/color/image_raw', 10)
    depth_pub = node.create_publisher(Image, '/camera/depth/image_raw', 10)
    info_pub = node.create_publisher(CameraInfo, '/camera/depth/camera_info', 10)
    labels, observations = {}, {'good': [], 'hole': []}
    errors, expected_errors = {'good': [], 'hole': []}, {}

    def receive(message):
        stamp = message.header.stamp.sec*10**9+message.header.stamp.nanosec
        if stamp in labels and len(message.status) == 1:
            record = {'stamp_ns': stamp, 'qualified': message.status[0].level == message.status[0].OK,
                      'values': {v.key: float(v.value) for v in message.status[0].values}}
            observations[labels[stamp]].append(record)

    subscription = node.create_subscription(DiagnosticArray,
                                            '/brain_robot_vision/rgbd_observation', receive, 10)
    def receive_error(message):
        stamp = message.header.stamp.sec*10**9+message.header.stamp.nanosec
        if stamp in labels:
            errors[labels[stamp]].append([message.vector.x, message.vector.y, message.vector.z])
    error_subscription = node.create_subscription(Vector3Stamped,
        '/brain_robot_vision/pixel_error', receive_error, 10)
    config = Path(__file__).parents[2]/'brain_robot_ball_pick/config/cube_detector.yaml'
    detector = yaml.safe_load(config.read_text())['cube_detector']['ros__parameters']
    with (args.output/'detector.log').open('x') as logfile:
        child = subprocess.Popen([args.detector_bin, '--ros-args', '-r', '__node:=cube_detector',
                                  '--params-file', str(config)], stdout=logfile, stderr=logfile)
        try:
            deadline = time.monotonic()+10
            while time.monotonic() < deadline and not rgb_pub.get_subscription_count():
                rclpy.spin_once(node, timeout_sec=.1)
            assert rgb_pub.get_subscription_count(), 'Detector RGB subscription unavailable'
            for label, row in inputs.items():
                rgb = cv2.imread(row['path'], cv2.IMREAD_COLOR)
                depth = cv2.imread(row['depth_path'], cv2.IMREAD_UNCHANGED)
                assert rgb is not None and depth is not None
                if args.check_rgb_error:
                    # Independent original-image centroid; not registered-depth support.
                    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv, (detector['hue_low_1'], detector['saturation_min'],
                        detector['value_min']), (detector['hue_high_1'], 255, 255))
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                        (detector['morphology_kernel'], detector['morphology_kernel']))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    moments = cv2.moments(max(contours, key=cv2.contourArea))
                    dx = moments['m10']/moments['m00']/rgb.shape[1]-.5
                    dy = moments['m01']/moments['m00']/rgb.shape[0]-.5
                    expected_errors[label] = [dx*depth.shape[1], dy*depth.shape[0], max(abs(dx), abs(dy))]
                for _ in range(12):
                    stamp = node.get_clock().now().to_msg()
                    number = stamp.sec*10**9+stamp.nanosec; labels[number] = label
                    color = bridge.cv2_to_imgmsg(rgb, 'bgr8'); color.header.stamp = stamp
                    color.header.frame_id = 'camera_color_optical_frame'
                    raw = bridge.cv2_to_imgmsg(depth, '16UC1'); raw.header.stamp = stamp
                    raw.header.frame_id = info['frame']
                    camera = CameraInfo(); camera.header = raw.header
                    camera.width, camera.height = info['size']; camera.k = info['k']
                    info_pub.publish(camera); depth_pub.publish(raw); rgb_pub.publish(color)
                    until = time.monotonic()+.3
                    while time.monotonic() < until:
                        rclpy.spin_once(node, timeout_sec=.02)
            until = time.monotonic()+1
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=.05)
            assert child.poll() is None
            (args.output/'observations.json').write_text(json.dumps(observations, indent=2))
            good = [r for r in observations['good'] if r['qualified']]
            assert len(good) >= 3, 'Need three genuinely qualified observations'
            good_coverage = statistics.median(r['values']['coverage'] for r in good[-3:])
            good_span = statistics.median(r['values']['span'] for r in good[-3:])
            assert observations['hole'], 'No stamped hole-frame diagnostic'
            for row in observations['hole']:
                v = row['values']
                assert (not row['qualified'] or v['coverage'] < .65*good_coverage or
                        v['span'] < .65*good_span), 'Hole must request last-model handoff'
            if args.check_rgb_error:
                for label in inputs:
                    assert errors[label], 'No same-frame RGB alignment error: '+label
                    for actual in errors[label]:
                        assert all(abs(a-b) < 1e-6 for a, b in zip(actual, expected_errors[label])), (
                            label, actual, expected_errors[label])
            report = {'domain': 78, 'hardware_motion_sent': False,
                      'timestamps_rebased_for_isolated_replay_not_live': True,
                      'input_frames': inputs, 'observations': observations,
                      'pixel_errors': errors, 'expected_original_rgb_errors': expected_errors,
                      'good_coverage_median': good_coverage, 'good_span_median': good_span,
                      'hole_frames_request_quality_handoff': True}
            (args.output/'report.json').write_text(json.dumps(report, indent=2))
            print(json.dumps({'qualified_good_frames': len(good),
                              'hole_records': len(observations['hole']), 'replay_passed': True}))
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
            node.destroy_subscription(subscription)
            node.destroy_subscription(error_subscription)
            node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
