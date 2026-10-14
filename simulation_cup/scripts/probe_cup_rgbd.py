#!/usr/bin/env python3
"""Capture five fixed Gazebo RGB-D views of the hollow stepped cup, without a robot.

Run after sourcing the simulation overlay with /usr/bin/python3 -s. Red masks
are diagnostic fixtures for geometry checks; YOLO qualification is separate.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'src/brain_robot_pick_place/scripts'))
from cup_geometry import CupSpec, write_model
from cup_width_estimation import fit_local_diameter


def make_world(output, spec=CupSpec(), camera_xyzs=None):
    root = ET.Element('sdf', version='1.7')
    world = ET.SubElement(root, 'world', name='cup_geometry_probe')
    ET.SubElement(world, 'gravity').text = '0 0 -9.81'
    physics = ET.SubElement(world, 'physics', type='ode')
    ET.SubElement(physics, 'max_step_size').text = '.001'
    ET.SubElement(physics, 'real_time_update_rate').text = '1000'
    world.append(ET.fromstring('''<light name="sun" type="directional"><pose>0 0 5 0 0 0</pose>
      <diffuse>.9 .9 .9 1</diffuse><direction>-.4 .1 -1</direction></light>'''))
    world.append(ET.fromstring('''<model name="probe_table"><static>true</static><link name="top">
      <pose>.4 0 -.01 0 0 0</pose><collision name="surface"><geometry><box><size>1 1 .02</size></box></geometry></collision>
      <visual name="surface"><geometry><box><size>1 1 .02</size></box></geometry>
      <material><ambient>.55 .55 .55 1</ambient><diffuse>.7 .7 .7 1</diffuse></material></visual></link></model>'''))
    model = ET.parse(write_model(output/'cup_model', spec)).getroot().find('model')
    ET.SubElement(model, 'pose').text = f'.4 0 {spec.height_m/2} 0 0 0'
    world.append(model)
    views = {}
    camera_xyzs = camera_xyzs or [(.08, -.30, .24), (.05, 0., .28), (.10, .25, .24),
                                 (.35, -.32, .35), (.12, -.05, .45)]
    for index, xyz in enumerate(camera_xyzs, 1):
        label = f'view{index}'
        direction = [.4-xyz[0], -xyz[1], .12-xyz[2]]
        yaw = math.atan2(direction[1], direction[0])
        pitch = -math.atan2(direction[2], math.hypot(direction[0], direction[1]))
        camera = ET.fromstring(f'''<model name="{label}"><static>true</static>
          <pose>{xyz[0]} {xyz[1]} {xyz[2]} 0 {pitch} {yaw}</pose><link name="camera">
          <sensor name="rgbd" type="depth"><always_on>true</always_on><update_rate>5</update_rate>
          <camera><horizontal_fov>1.0471975512</horizontal_fov>
          <image><width>640</width><height>480</height><format>R8G8B8</format></image>
          <clip><near>.05</near><far>2</far></clip></camera>
          <plugin name="{label}_rgbd" filename="libgazebo_ros_camera.so">
          <ros><namespace>/cup_probe/{label}</namespace></ros><camera_name>camera</camera_name>
          <frame_name>{label}_optical</frame_name><min_depth>.05</min_depth><max_depth>2</max_depth>
          </plugin></sensor></link></model>''')
        world.append(camera)
        views[label] = dict(camera_xyz=list(xyz), yaw=yaw, pitch=pitch)
    ET.indent(root)
    path = output/'probe.world'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path, views


def capture(output, views, process, *, fit_geometry=True):
    import cv2
    import numpy as np
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image, CameraInfo
    rclpy.init()
    node = rclpy.create_node('cup_rgbd_probe')
    images, info, saved, subscriptions = {}, {}, {}, []
    for label in views:
        images[label] = {'rgb': {}, 'depth': {}}
        def receive(msg, label=label, kind='rgb'):
            stamp = msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            images[label][kind][stamp] = msg
            while len(images[label][kind]) > 10:
                del images[label][kind][next(iter(images[label][kind]))]
        for kind, suffix in [('rgb', 'image_raw'), ('depth', 'depth/image_raw')]:
            subscriptions.append(node.create_subscription(Image, f'/cup_probe/{label}/camera/{suffix}',
                lambda msg, label=label, kind=kind: receive(msg, label, kind), qos_profile_sensor_data))
        subscriptions.append(node.create_subscription(CameraInfo, f'/cup_probe/{label}/camera/camera_info',
            lambda msg, label=label: info.__setitem__(label, msg), qos_profile_sensor_data))
    deadline = time.monotonic()+90
    try:
        while len(saved) < len(views) and time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Gazebo exited with {process.returncode}; inspect gazebo.log')
            rclpy.spin_once(node, timeout_sec=.1)
            for label, data in images.items():
                common = set(data['rgb']) & set(data['depth'])
                if label in saved or label not in info or not common:
                    continue
                stamp = max(common)
                if stamp < 10**9:  # allow the empty cup to settle on the table
                    continue
                rgb, depth = data['rgb'][stamp], data['depth'][stamp]
                if rgb.encoding not in ('rgb8', 'bgr8') or depth.encoding != '32FC1':
                    raise RuntimeError('unexpected RGB-D encodings')
                color = np.ndarray((rgb.height, rgb.width, 3), np.uint8, buffer=bytes(rgb.data), strides=(rgb.step, 3, 1)).copy()
                if rgb.encoding == 'rgb8':
                    color = color[:, :, ::-1]
                z = np.ndarray((depth.height, depth.width), '<f4', buffer=bytes(depth.data), strides=(depth.step, 4)).copy()
                k = np.array(info[label].k).reshape(3, 3)
                cv2.imwrite(str(output/'images'/f'{label}.png'), color)
                np.savez_compressed(output/f'{label}.npz', depth_m=z, k=k, image_stamp_ns=stamp)
                # Fixture mask is used only to assess the sizing component.
                mask = (color[:, :, 2] > 90) & (color[:, :, 2] > 1.5*color[:, :, 1].astype(float)) & (color[:, :, 2] > 1.5*color[:, :, 0].astype(float))
                rows, cols = np.where(mask & np.isfinite(z) & (z > .05) & (z < 2))
                camera_points = np.column_stack(((cols-k[0, 2])*z[rows, cols]/k[0, 0],
                    (rows-k[1, 2])*z[rows, cols]/k[1, 1], z[rows, cols]))
                yaw, pitch = views[label]['yaw'], views[label]['pitch']
                forward = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), -math.sin(pitch)])
                right = np.array([math.sin(yaw), -math.cos(yaw), 0.])
                down = np.cross(forward, right)
                world_points = camera_points@np.column_stack((right, down, forward)).T + views[label]['camera_xyz']
                results = {}
                for region, height, truth in ([('body', .1, .075), ('mouth', .18, .063)] if fit_geometry else []):
                    try:
                        estimate = fit_local_diameter(world_points, height,
                            camera_origin_world=views[label]['camera_xyz'])
                        results[region] = {**estimate.__dict__, 'error_m': estimate.diameter_m-truth}
                    except ValueError as error:
                        results[region] = {'rejected': str(error)}
                saved[label] = {**views[label], 'image_stamp_ns': stamp,
                    'diagnostic_mask': 'red fixture, not YOLO', 'local_diameter': results}
                print(f'Captured {label}: '+json.dumps(results), flush=True)
        if len(saved) != len(views):
            raise RuntimeError('timed out waiting for synchronized RGB-D images: '+str(list(saved)))
        (output/'capture.json').write_text(json.dumps({'scope': 'fixed-camera component probe; no robot motion',
            'specimen_truth_used_as_fit_prior': False, 'views': saved}, indent=2)+'\n')
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '84' or os.environ.get('GAZEBO_MASTER_URI') != 'http://127.0.0.1:11484':
        parser.error('Set ROS_DOMAIN_ID=84, ROS_LOCALHOST_ONLY=1 and GAZEBO_MASTER_URI=http://127.0.0.1:11484')
    output = args.output.resolve()
    if output.exists():
        parser.error('output must be a new directory')
    (WS/'log').mkdir(exist_ok=True)
    with (WS/'log/cup_probe.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 11484))
        output.mkdir(parents=True)
        (output/'images').mkdir()
        world, views = make_world(output)
        with (output/'gazebo.log').open('w') as log:
            process = subprocess.Popen(['gzserver', '--verbose', str(world), '-s', 'libgazebo_ros_init.so'],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                capture(output, views, process)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGINT)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
