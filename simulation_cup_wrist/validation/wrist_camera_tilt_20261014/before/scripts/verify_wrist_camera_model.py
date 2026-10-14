#!/usr/bin/env python3
"""Expand both robot models and check the physical wrist-camera coordinate contract."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import yaml

WS = Path(__file__).resolve().parents[1]


def rotation(origin):
    roll, pitch, yaw = [float(v) for v in origin.get('rpy', '0 0 0').split()]
    sr, cr, sp, cp, sy, cy = math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw), math.cos(yaw)
    return np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                     [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr], [-sp, cp*sr, cp*cr]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or WS/'validation'/('wrist_model_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    models = {}
    paths = dict(gazebo='src/brain_robot_pick_place/urdf/piper_with_wrist_camera_gazebo.xacro',
                 moveit='src/piper_with_gripper_moveit/config/piper.urdf.xacro')
    for kind, path in paths.items():
        command = ['xacro', str(WS/path)]
        if kind == 'moveit':
            command.append('initial_positions_file:=' + str(WS/'src/piper_with_gripper_moveit/config/initial_positions.yaml'))
        expanded = subprocess.check_output(command)
        # gazebo_ros2_control passes robot_description through the ROS YAML
        # argument parser. A colon-space in an XML comment breaks that parser.
        assert isinstance(yaml.safe_load(expanded), str), 'Expanded URDF must survive the Gazebo ROS argument parser'
        (output/(kind+'_robot.urdf')).write_bytes(expanded)
        root = ET.fromstring(expanded)
        joint = root.find("joint[@name='gripper_to_wrist_camera']")
        origin = joint.find('origin')
        xyz = [float(v) for v in origin.get('xyz').split()]
        optical = root.find("joint[@name='wrist_camera_optical_joint']/origin")
        orientation = rotation(origin) @ rotation(optical)
        camera = root.find("link[@name='wrist_camera_link']")
        tip = float(root.find("joint[@name='joint7']/origin").get('xyz').split()[2])
        dims = [float(v) for v in camera.find('collision/geometry/box').get('size').split()]
        assert abs(tip-xyz[2]-.105) < 1e-9, 'Camera front must be 105 mm behind the model tip'
        assert np.allclose(orientation @ [0, 0, 1], [0, 0, 1], atol=1e-9), 'Optical +Z must point towards the fingers'
        assert np.isclose(np.linalg.det(orientation), 1), 'Optical transform must preserve handedness'
        assert dims == [.03, .09, .025], 'Camera collision envelope must match Gemini 2 dimensions'
        models[kind] = dict(parent=joint.find('parent').get('link'), front_xyz_m=xyz,
                            tip_axial_m=tip, front_to_tip_m=tip-xyz[2], body_depth_width_height_m=dims,
                            optical_forward_gripper=(orientation @ [0, 0, 1]).tolist())
        if kind == 'gazebo':
            sensor = root.find("gazebo[@reference='wrist_camera_link']/sensor")
            minimum = float(sensor.find('plugin/min_depth').text)
            assert minimum == .15, 'Do not simulate usable Gemini 2 depth inside its 150 mm minimum'
            assert sensor.find('plugin/frame_name').text == 'wrist_camera_optical_frame'
    assert models['gazebo'] == models['moveit'], 'Planning and simulation must use the same camera mounting'
    report = dict(passed=True, models=models, minimum_depth_m=minimum,
                  side_offset_is_assumed=True, extrinsics_are_not_hand_eye_calibrated=True)
    (output/'model_verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Wrist-camera model verification passed:', output)


if __name__ == '__main__':
    main()
