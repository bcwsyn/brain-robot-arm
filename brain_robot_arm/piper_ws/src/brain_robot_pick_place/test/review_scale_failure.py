#!/usr/bin/env python3
"""Offline scale review of archived RGB/q; no ROS or hardware interfaces.

Historical exact seed/TF were not recorded. Candidate seeds and snapshot FK
are explicitly approximate, never substituted for runtime measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import yaml
from scipy.spatial.transform import Rotation
from review_jaw_scene import poses


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--urdf', type=Path, required=True)
    p.add_argument('--policy-bin', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Refuse to overwrite evidence')
    cfg = Path(__file__).parents[2] / 'brain_robot_ball_pick/config'
    d = yaml.safe_load((cfg / 'cube_detector.yaml').read_text())['cube_detector']['ros__parameters']
    mount = yaml.safe_load((cfg / 'cube_task_real.yaml').read_text())['piper_camera_mount_tf']['ros__parameters']
    log = a.log.read_text()
    match = re.search(r'TARGET_DIRECTED_VARIABLE_ATTITUDE surface=\(([^)]+)\)', log)
    if not match:
        raise RuntimeError('No logged frozen surface')
    locked = np.array([float(x) for x in match[1].split(',')] + [1.])
    rows = [json.loads(x) for x in (a.capture / 'observer.jsonl').read_text().splitlines()]
    snapshots = {r['snapshot']: r for r in rows if 'snapshot' in r}
    model = ET.fromstring(a.urdf.read_bytes())
    optical = np.eye(4)
    optical[:3, :3] = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
    tool_camera = np.eye(4)
    tool_camera[:3, :3] = Rotation.from_euler('xyz', mount['rotation_rpy_rad']).as_matrix()
    tool_camera[:3, 3] = mount['translation_m']
    tool_depth = tool_camera @ optical
    rdc = np.array(d['depth_to_color_rotation']).reshape(3, 3)
    tdc = np.array(d['depth_to_color_translation_m'])
    calibration = [d[k] for k in ('color_calibration_width', 'color_calibration_height',
        'color_fx', 'color_fy', 'color_cx', 'color_cy', 'color_mirror_horizontal')]
    calibration += d['depth_to_color_rotation'] + d['depth_to_color_translation_m']
    shape = [d[k] for k in ('min_area_px', 'max_area_px', 'min_circularity',
        'min_rectangularity', 'min_aspect_ratio', 'max_aspect_ratio', 'shape_use_rotated_rectangle',
        'hue_low_1', 'hue_high_1', 'saturation_min', 'value_min', 'morphology_kernel')]

    def review(number, seed):
        row = snapshots[number]
        packet = row['latest']['/joint_states_feedback']
        q = dict(packet['positions'])
        q['joint7'], q['joint8'] = q['gripper']/2, -q['gripper']/2
        tool = poses(model, q)['link6']
        point = (np.linalg.inv(tool @ tool_depth) @ locked)[:3]
        # Freshness/identity/path allowance are simulated for scale inspection.
        # --scale-details is an offline-only flag; entity policy is unchanged.
        values = calibration + seed + [True, True, True, .05, .02, 3., 0.] + list(point) + shape
        encoded = ' '.join(str(int(x)) if isinstance(x, bool) else str(x) for x in values)
        image = row['images']['rgb']
        reply = subprocess.run([str(a.policy_bin), image['path'], '--scale-details'],
            input=encoded, text=True, capture_output=True, check=True, timeout=8).stdout.splitlines()
        words = reply[0].split()
        result = {'snapshot': number, 'rgb_stamp': image['stamp'], 'q_stamp': packet['stamp'],
            'rgb_minus_q_s': image['stamp']-packet['stamp'],
            'raw_rgb_sha256': hashlib.sha256(Path(image['path']).read_bytes()).hexdigest(),
            'decision': words[0], 'box': list(map(float, words[1:5])),
            'projection': list(map(float, words[5:8])),
            'model_depth_point_approx': point.tolist(),
            'model_tip_base_approx': (tool @ np.array([0, 0, .1358, 1]))[:3].tolist()}
        if len(reply) > 1:
            result['scale_growth_width_height'] = list(map(float, reply[1].split()[1:]))
        measured = row['latest'].get('/brain_robot_vision/target_point_camera')
        if measured:
            color_z = float((rdc @ np.array(measured['xyz']) + tdc)[2])
            result['raw_point_stamp'] = measured['stamp']
            result['raw_point_minus_rgb_s'] = measured['stamp']-image['stamp']
            result['measured_color_z'] = color_z
            result['range_difference_m_approx'] = color_z-result['projection'][2]
            if seed[-1] and color_z > .001:
                b = result['box']
                alt_growth = seed[4]/color_z
                alt = [(b[2]-b[0])/(seed[2]-seed[0])/alt_growth,
                    (b[3]-b[1])/(seed[3]-seed[1])/alt_growth]
                result['counterfactual_measured_range_scale_only_not_new_seed'] = alt
                result['counterfactual_scale_passes_only'] = all(.65 <= x <= 1.5 for x in alt)
        return result

    outputs = []
    for candidate in (55, 56, 57, 58):
        first = review(candidate, [0, 0, 0, 0, .3, False])
        seed = first['box'] + [first['projection'][2], True]
        if seed[0] >= seed[2] or seed[1] >= seed[3]:
            raise RuntimeError('Invalid candidate colour box')
        outputs.append({'candidate_seed_not_exact_historical_seed': first,
            'seed': seed, 'frames': [review(n, seed) for n in (58, 61, 64, 67, 70, 71, 72)]})
    report = {'offline_only': True, 'hardware_executed': False,
        'exact_historical_seed_available': False, 'exact_image_time_tf_available': False,
        'freshness_identity_path_allowance_simulated': True,
        'loaded_urdf_from_earlier_archive_not_recaptured': str(a.urdf),
        'camera_rotation_calibrated': mount['rotation_calibrated'],
        'lock_base_rounded_four_decimal_log': locked[:3].tolist(),
        'source_sha256': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in
            (a.log, a.urdf, cfg/'cube_detector.yaml', cfg/'cube_task_real.yaml', a.policy_bin)},
        'original_scale_bounds_unchanged': [.65, 1.5], 'candidate_replays': outputs}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    for case in outputs:
        final = case['frames'][-1]
        print(json.dumps({'candidate': case['candidate_seed_not_exact_historical_seed']['snapshot'],
            'final': final}, ensure_ascii=False))


if __name__ == '__main__':
    main()
