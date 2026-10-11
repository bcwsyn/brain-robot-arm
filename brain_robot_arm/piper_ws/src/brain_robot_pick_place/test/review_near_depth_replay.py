#!/usr/bin/env python3
"""Offline recorded RGB/FK review using the compiled production policy helpers.

No ROS/node/robot output. Source timestamps are archived; freshness inputs are
explicitly simulated, NOT evidence that old images are fresh on the real arm.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import yaml
from review_calibration_sampling import tool_pose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-root', type=Path, required=True)
    parser.add_argument('--policy-bin', type=Path, required=True)
    parser.add_argument('--urdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refuse to overwrite evidence')
    args.output.mkdir()
    package = Path(__file__).parents[1]
    config_dir = package.parent / 'brain_robot_ball_pick/config'
    detector = yaml.safe_load((config_dir / 'cube_detector.yaml').read_text())['cube_detector']['ros__parameters']
    mount = yaml.safe_load((config_dir / 'cube_task_real.yaml').read_text())['piper_camera_mount_tf']['ros__parameters']
    review = json.loads((args.capture_root / 'locked_rgb_projection_review.json').read_text())
    model = args.urdf.read_bytes()
    assert hashlib.sha256(model).hexdigest() == review['source_urdf_sha256']
    root = ET.fromstring(model)
    optical = np.eye(4)
    optical[:3, :3] = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
    camera = np.eye(4)
    camera[:3, 3] = mount['translation_m']
    camera[:3, :3] = Rotation.from_euler('xyz', mount['rotation_rpy_rad']).as_matrix()
    tool_from_depth = camera @ optical
    camera_start = tool_pose(root, review['actual_feedback_start_q']) @ tool_from_depth
    locked = camera_start @ np.r_[review['locked_depth_camera_point_m'], 1.]
    calibration = [detector[k] for k in ('color_calibration_width', 'color_calibration_height',
        'color_fx', 'color_fy', 'color_cx', 'color_cy', 'color_mirror_horizontal')]
    calibration += detector['depth_to_color_rotation'] + detector['depth_to_color_translation_m']
    shape = [detector[k] for k in ('min_area_px', 'max_area_px', 'min_circularity',
        'min_rectangularity', 'min_aspect_ratio', 'max_aspect_ratio', 'shape_use_rotated_rectangle',
        'hue_low_1', 'hue_high_1', 'saturation_min', 'value_min', 'morphology_kernel')]

    def policy(path, point, seed, evidence):
        values = calibration + seed + evidence + list(point) + shape
        encoded = ' '.join(str(int(x)) if isinstance(x, bool) else str(x) for x in values)
        reply = subprocess.run([str(args.policy_bin), str(path)], input=encoded,
                               text=True, check=True, capture_output=True, timeout=5)
        words = reply.stdout.split()
        return {'decision': words[0], 'box': list(map(float, words[1:5])),
                'projection': list(map(float, words[5:8]))}

    packets = []
    for stage in ('image_aim_after', 'image_forward_after'):
        packets.extend((stage, json.loads(line)) for line in
                       (args.capture_root / stage / 'observer.jsonl').read_text().splitlines())
    first = packets[0][1]
    first_point = np.linalg.inv(tool_pose(root, first['q_rad']) @ tool_from_depth) @ locked
    first_result = policy(first['images']['rgb']['path'], first_point[:3], [0, 0, 0, 0, .15, False],
                          [True, True, True, .05, .02, 0, 0])
    seed = first_result['box'] + [first_result['projection'][2], True]
    outputs = []
    for stage, row in packets:
        current_camera = tool_pose(root, row['q_rad']) @ tool_from_depth
        point = np.linalg.inv(current_camera) @ locked
        travel = np.linalg.norm(current_camera[:3, 3] - camera_start[:3, 3])
        result = policy(row['images']['rgb']['path'], point[:3], seed,
                        [True, True, True, .05, .02, 3., float(travel)])
        assert result['decision'] == 'ASSOCIATED_LOCKED_RGB', (stage, row['snapshot'], result)
        outputs.append({'stage': stage, 'snapshot': row['snapshot'], 'source_stamps_ns': row['stamps_ns'],
                        'q_actual_rad': row['q_rad'], 'model_depth_point_m': point[:3].tolist(), **result})
    last = packets[-1][1]
    rgb = cv2.imread(last['images']['rgb']['path'])
    point = outputs[-1]['model_depth_point_m']
    normal = [True, True, True, .05, .02, 3., .012]
    negative = {}
    for name, evidence, bad_seed in [
            ('no_initial_depth_lock', normal, seed[:-1] + [False]),
            ('feedback_missing', [True, True, False, .05, .02, 3., .012], seed),
            ('image_tf_missing', [True, False, True, .05, .02, 3., .012], seed),
            ('stale_rgb', [True, True, True, .61, .02, 3., .012], seed),
            ('age_exhausted', [True, True, True, .05, .02, 30.01, .012], seed),
            ('travel_exhausted', [True, True, True, .05, .02, 3., .03001], seed)]:
        result = policy(last['images']['rgb']['path'], point, bad_seed, evidence)
        assert result['decision'] != 'ASSOCIATED_LOCKED_RGB', name
        negative[name] = result
    for name in ('no_color', 'thin_purple', 'purple_background'):
        image = np.zeros_like(rgb)
        if name == 'thin_purple':
            image[150:155, 70:220] = [180, 40, 150]
        elif name == 'purple_background':
            image[10:85, 15:90] = [180, 40, 150]
        path = args.output / f'{name}.png'
        assert cv2.imwrite(str(path), image)
        result = policy(path, point, seed, normal)
        assert result['decision'] != 'ASSOCIATED_LOCKED_RGB', name
        negative[name] = result
    report = {'offline_only': True, 'robot_interfaces_used': False,
              'freshness_evidence_simulated_not_live': True,
              'source_timestamps_retained_not_refreshed_on_robot': True,
              'mount_calibrated_or_jaw_contact_proved': False,
              'depth_measurement_created': False,
              'sources': {'urdf_sha256': hashlib.sha256(model).hexdigest(),
                          'policy_bin_sha256': hashlib.sha256(args.policy_bin.read_bytes()).hexdigest(),
                          'projection_review_sha256': hashlib.sha256(
                              (args.capture_root / 'locked_rgb_projection_review.json').read_bytes()).hexdigest()},
              'accepted_recorded_shapes': outputs, 'negative_cases': negative}
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'accepted_recorded_shapes': len(outputs),
                      'negative_cases': {k: v['decision'] for k, v in negative.items()},
                      'freshness_simulated_not_live': True}, indent=2))


if __name__ == '__main__':
    main()
