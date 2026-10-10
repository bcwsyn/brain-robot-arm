#!/usr/bin/env python3
"""Read-only camera/fingertip geometry review; no ROS/CAN or file writes."""
import argparse
import json
import math
from pathlib import Path

import yaml


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3))
             for j in range(3)] for i in range(3)]


def optical_to_tool_rotation(rpy):
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]
    ry = [[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]]
    rz = [[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]
    # REP-103: optical X right, Y down, Z forward; camera_link X forward.
    link_from_optical = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
    return multiply(multiply(multiply(rz, ry), rx), link_from_optical)


def translation_from_tip(tip_optical, tip_offset, rpy):
    if len(tip_optical) != 3 or len(rpy) != 3 or not all(
            math.isfinite(v) for v in list(tip_optical) + list(rpy) + [tip_offset]):
        raise ValueError('finite optical XYZ, RPY and tip offset required')
    if tip_optical[2] <= 0 or tip_offset <= 0:
        raise ValueError('tip depth and tool offset must be positive')
    rotation = optical_to_tool_rotation(rpy)
    return [(tip_offset if i == 2 else 0.0) -
            sum(rotation[i][j] * tip_optical[j] for j in range(3))
            for i in range(3)]


def tip_in_camera(translation, tip_offset, rpy):
    rotation = optical_to_tool_rotation(rpy)
    delta = [-translation[0], -translation[1], tip_offset - translation[2]]
    return [sum(rotation[i][j] * delta[i] for i in range(3)) for j in range(3)]


def project(point, k, size):
    if point[2] <= 0:
        raise ValueError('cannot project behind camera')
    pixel = [k[0] * point[0] / point[2] + k[2],
             k[4] * point[1] / point[2] + k[5]]
    return {'pixel': pixel, 'inside_image':
            0 <= pixel[0] < size[0] and 0 <= pixel[1] < size[1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--observation', type=Path)
    args = parser.parse_args()
    profile = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    mount = profile['piper_camera_mount_tf']['ros__parameters']
    tip_offset = profile['grasp_lift_executor']['ros__parameters']['gripper_tip_offset_m']
    derived = translation_from_tip(mount['operator_tip_optical_m'], tip_offset,
                                   mount['rotation_rpy_rad'])
    point = tip_in_camera(mount['translation_m'], tip_offset, mount['rotation_rpy_rad'])
    report = {'derived_camera_origin_tool_m': derived,
              'configured_camera_origin_tool_m': mount['translation_m'],
              'configured_tip_optical_m': point,
              'horizontal_offset_measured': mount['horizontal_offset_measured'],
              'rotation_calibrated': mount['rotation_calibrated'],
              'physical_grasp_verified': False}
    if args.observation:
        observation = json.loads(args.observation.read_text(encoding='utf-8'))
        camera = observation['/camera/depth/camera_info']
        report['tip_projection'] = project(point, camera['k'], camera['size'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
