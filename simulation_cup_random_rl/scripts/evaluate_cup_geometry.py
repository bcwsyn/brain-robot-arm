#!/usr/bin/env python3
"""Replay a Gazebo cup RGB-D fixture capture; no ROS or motion commands."""
import argparse
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'src/brain_robot_pick_place/scripts'))
from cup_width_estimation import fit_local_diameter
from adaptive_gripper_policy import opening_from_measurement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must not exist')
    metadata = json.loads((args.capture/'capture.json').read_text())
    results = []
    for label, view in metadata['views'].items():
        color = cv2.imread(str(args.capture/'images'/f'{label}.png'))
        saved = np.load(args.capture/f'{label}.npz')
        z, k = saved['depth_m'], saved['k']
        mask = (color[:, :, 2] > 90) & (color[:, :, 2] > 1.5*color[:, :, 1].astype(float)) & (color[:, :, 2] > 1.5*color[:, :, 0].astype(float))
        rows, cols = np.where(mask & np.isfinite(z) & (z > .05) & (z < 2))
        cp = np.column_stack(((cols-k[0, 2])*z[rows, cols]/k[0, 0],
            (rows-k[1, 2])*z[rows, cols]/k[1, 1], z[rows, cols]))
        yaw, pitch = view['yaw'], view['pitch']
        forward = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), -math.sin(pitch)])
        right = np.array([math.sin(yaw), -math.cos(yaw), 0.])
        down = np.cross(forward, right)
        world_points = cp@np.column_stack((right, down, forward)).T+view['camera_xyz']
        measurements = {}
        for region, height, truth in [('body', .1, .075), ('mouth', .18, .063)]:
            try:
                estimate = fit_local_diameter(world_points, height, camera_origin_world=view['camera_xyz'])
                plan = opening_from_measurement(estimate.diameter_m, estimate.sigma_m, .1)
                measurements[region] = {**estimate.__dict__, 'absolute_error_m': abs(estimate.diameter_m-truth),
                    'preopening_m': plan.opening_m}
            except ValueError as error:
                measurements[region] = {'rejected': str(error)}
        results.append({'view': label, 'local_diameter': measurements})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'diagnostic_mask': 'red fixture; not YOLO',
        'replayed_existing_rgbd': True, 'force_control_integrated': False,
        'truth_used_as_diameter_prior': False, 'results': results}, indent=2)+'\n')
    estimates = [r for view in results for r in view['local_diameter'].values()]
    valid = [r for r in estimates if 'absolute_error_m' in r]
    print(json.dumps(dict(estimated=len(valid), rejected=len(estimates)-len(valid),
        maximum_error_m=max((r['absolute_error_m'] for r in valid), default=None))), flush=True)
    return 0 if len(valid) == len(estimates) else 1


if __name__ == '__main__':
    raise SystemExit(main())
