#!/usr/bin/env python3
"""Verify the read-only YOLO ROS node with recorded RGB-D and calibrated static TF."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import cv2
import numpy as np
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import TransformStamped, Vector3Stamped
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import Bool, String
from tf2_ros import StaticTransformBroadcaster

WS = Path(__file__).resolve().parents[1]


def matrix_quaternion(matrix):
    # scipy is already supplied by the ROS system environment.
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(matrix).as_quat().tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '84' or args.output.exists():
        parser.error('requires domain 84 and a new output directory')
    metadata = json.loads((args.capture/'capture.json').read_text())
    args.output.mkdir(parents=True)
    rclpy.init()
    node = rclpy.create_node('cup_ros_replay_check')
    image_qos = QoSProfile(depth=3, reliability=ReliabilityPolicy.RELIABLE)
    info_pub = node.create_publisher(CameraInfo, '/cup_replay/info', image_qos)
    rgb_pub = node.create_publisher(Image, '/cup_replay/rgb', image_qos)
    depth_pub = node.create_publisher(Image, '/cup_replay/depth', image_qos)
    diagnostics, widths, valid = [], [], []
    subscriptions = [
        node.create_subscription(String, '/brain_robot_vision/cup_diagnostic', lambda msg: diagnostics.append(json.loads(msg.data)), 1),
        node.create_subscription(Vector3Stamped, '/brain_robot_vision/grasp_width',
            lambda msg: widths.append([msg.vector.x, msg.vector.y, msg.vector.z]), 1),
        node.create_subscription(Bool, '/brain_robot_vision/cup_target_valid', lambda msg: valid.append(msg.data), 1)]
    broadcaster = StaticTransformBroadcaster(node)
    transforms = []
    for label, view in metadata['views'].items():
        yaw, pitch = view['yaw'], view['pitch']
        f = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), -math.sin(pitch)])
        right = np.array([math.sin(yaw), -math.cos(yaw), 0.])
        rotation = np.column_stack((right, np.cross(f, right), f))
        transform = TransformStamped()
        transform.header.frame_id = 'world'
        transform.header.stamp = node.get_clock().now().to_msg()
        transform.child_frame_id = label+'_optical'
        t, q = transform.transform.translation, transform.transform.rotation
        t.x, t.y, t.z = map(float, view['camera_xyz'])
        q.x, q.y, q.z, q.w = matrix_quaternion(rotation)
        transforms.append(transform)
    broadcaster.sendTransform(transforms)
    environment = dict(os.environ, PYTHONNOUSERSITE='1', ROS_LOG_DIR=str(args.output/'ros_logs'),
                       YOLO_CONFIG_DIR=str(WS/'artifacts/yolo/config'), OPENBLAS_NUM_THREADS='1',
                       OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
    command = [str(WS/'.venv-yolo/bin/python'), '-s', str(WS/'src/brain_robot_pick_place/scripts/yolo_cup_target_node.py'),
        '--ros-args', '-p', 'model:='+str(args.model.resolve()), '-p', 'rgb_topic:=/cup_replay/rgb',
        '-p', 'depth_topic:=/cup_replay/depth', '-p', 'camera_info_topic:=/cup_replay/info']
    results = []
    with (args.output/'node.log').open('w') as log:
        process = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic()+30
            while 'yolo_cup_target' not in node.get_node_names() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('YOLO node exited; inspect node.log')
                rclpy.spin_once(node, timeout_sec=.1)
            if 'yolo_cup_target' not in node.get_node_names():
                raise RuntimeError('YOLO node discovery timed out')
            # Model loading follows node creation; wait for actual endpoints.
            until = time.monotonic()+20
            while not (rgb_pub.get_subscription_count() and depth_pub.get_subscription_count() and info_pub.get_subscription_count()):
                if time.monotonic() > until or process.poll() is not None:
                    raise RuntimeError('camera subscription discovery timed out')
                rclpy.spin_once(node, timeout_sec=.1)
            cases = [(label, 'positive') for label in metadata['views']]+[('view1', 'blank'), ('view1', 'stale_image')]
            for label, kind in cases:
                color = cv2.imread(str(args.capture/'images'/f'{label}.png'))
                saved = np.load(args.capture/f'{label}.npz')
                z, k = saved['depth_m'], saved['k']
                if kind == 'blank':
                    color[:] = 100
                first, successes = len(diagnostics), 0
                deadline = time.monotonic()+20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('perception process exited during a check')
                    stamp = node.get_clock().now()
                    if kind == 'stale_image':
                        stamp = stamp-rclpy.duration.Duration(seconds=2)
                    rgb, depth, info = Image(), Image(), CameraInfo()
                    for msg in (rgb, depth, info):
                        msg.header.stamp = stamp.to_msg()
                        msg.header.frame_id = label+'_optical'
                        msg.width, msg.height = color.shape[1], color.shape[0]
                    rgb.encoding, rgb.step, rgb.data = 'bgr8', color.shape[1]*3, color.tobytes()
                    depth.encoding, depth.step, depth.data = '32FC1', z.shape[1]*4, z.astype('<f4').tobytes()
                    info.k = k.ravel().tolist()
                    info_pub.publish(info)
                    rgb_pub.publish(rgb)
                    depth_pub.publish(depth)
                    until = time.monotonic()+.30
                    while time.monotonic() < until:
                        rclpy.spin_once(node, timeout_sec=.01)
                    observed = [d for d in diagnostics[first:] if d.get('image_frame') == label+'_optical']
                    expected = 'VALID' if kind == 'positive' else 'REJECTED'
                    successes = sum(d['status'] == expected for d in observed)
                    if successes >= 3:
                        results.append(dict(view=label, case=kind, passed=True, diagnostics=observed[-3:]))
                        print(f'{label} {kind}: passed', flush=True)
                        break
                else:
                    results.append(dict(view=label, case=kind, passed=False, diagnostics=diagnostics[first:][-3:]))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    report = dict(mode='recorded RGB-D over ROS; static calibrated TF; no robot motion',
        cases=results, passed=all(r['passed'] for r in results), widths_published=len(widths))
    (args.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
