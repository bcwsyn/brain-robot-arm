"""Offline late-seed comparison; approximate FK, no ROS/hardware interfaces."""
import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation
from review_jaw_scene import poses

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--capture', type=Path, required=True)
p.add_argument('--log', type=Path, required=True)
p.add_argument('--urdf', type=Path, required=True)
p.add_argument('--policy-bin', type=Path, required=True)
a = p.parse_args()
config = Path(__file__).parents[2] / 'brain_robot_ball_pick/config'
d = yaml.safe_load((config / 'cube_detector.yaml').read_text())['cube_detector']['ros__parameters']
mount = yaml.safe_load((config / 'cube_task_real.yaml').read_text())['piper_camera_mount_tf']['ros__parameters']
model = ET.fromstring(a.urdf.read_text())
log = a.log.read_text()
locked = np.array([float(v) for v in re.search(
    r'TARGET_DIRECTED_VARIABLE_ATTITUDE surface=\(([^)]+)\)', log)[1].split(',')] + [1.])
seed_log = re.search(r'NEAR_RGB_SCALE_SEED image_stamp=(\d+).*?box=\(([^)]+)\) color_z=([\d.]+)', log)
original_seed = [float(v) for v in seed_log[2].split(',')] + [float(seed_log[3]), True]
fault = re.search(r'\[(\d+\.\d+)\] \[grasp_lift_executor\]: Grasp sequence stopped', log)
if fault is None:
    raise RuntimeError('No terminal grasp boundary in recorded log')
end_stamp = int(Decimal(fault[1]) * 1000000000)
rows = [json.loads(s) for s in (a.capture / 'frames.jsonl').read_text().splitlines()]
indexed = {kind: {r['stamp_ns']: r for r in rows if r['kind'] == kind}
           for kind in ('rgb', 'raw_point', 'qualified_box')}
optical = np.eye(4); optical[:3, :3] = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
camera = np.eye(4)
camera[:3, :3] = Rotation.from_euler('xyz', mount['rotation_rpy_rad']).as_matrix()
camera[:3, 3] = mount['translation_m']
tool_depth = camera @ optical
rdc = np.array(d['depth_to_color_rotation']).reshape(3, 3)
tdc = np.array(d['depth_to_color_translation_m'])
calibration = [d[k] for k in ('color_calibration_width', 'color_calibration_height',
    'color_fx', 'color_fy', 'color_cx', 'color_cy', 'color_mirror_horizontal')]
calibration += d['depth_to_color_rotation'] + d['depth_to_color_translation_m']
shape = [d[k] for k in ('min_area_px', 'max_area_px', 'min_circularity',
    'min_rectangularity', 'min_aspect_ratio', 'max_aspect_ratio', 'shape_use_rotated_rectangle',
    'hue_low_1', 'hue_high_1', 'saturation_min', 'value_min', 'morphology_kernel')]
samples = []
for stamp, image in sorted(indexed['rgb'].items()):
    if stamp < int(seed_log[1]) or stamp > end_stamp:
        continue  # Recorded seed-to-fault interval, no cleanup cache.
    raw, box = indexed['raw_point'].get(stamp), indexed['qualified_box'].get(stamp)
    feedback = image.get('latest_feedback_not_image_time')
    if raw is None or box is None or feedback is None or len(box['corners']) != 4:
        continue
    if abs(feedback['stamp_ns'] - stamp) > 20000000:
        continue
    q = dict(feedback['positions']); opening = q['gripper']
    q['joint7'], q['joint8'] = opening / 2, -opening / 2
    base_depth = poses(model, q)['link6'] @ tool_depth
    point = np.array(raw['xyz']); color_z = float((rdc @ point + tdc)[2])
    xs, ys = zip(*[(v[0], v[1]) for v in box['corners']])
    samples.append({'stamp': stamp, 'image': image['path'], 'q': np.array([q[f'joint{i}'] for i in range(1, 7)]),
        'base_depth': base_depth, 'point': point, 'color_z': color_z,
        'box': [min(xs), min(ys), max(xs), max(ys)],
        'feedback_offset_ns': feedback['stamp_ns'] - stamp})

# Candidate stability is replay evidence, not the actual controller's settle state.
window = None
for i in range(len(samples) - 2):
    group = samples[i:i+3]
    span = (group[-1]['stamp'] - group[0]['stamp']) * 1e-9
    if all(.20 <= s['color_z'] <= .22 for s in group) and .35 <= span <= .65 and \
            np.ptp(np.stack([s['q'] for s in group]), axis=0).max() <= .002:
        window = group; break
if window is None:
    raise RuntimeError('No three-frame near-20cm low-motion candidate; do not fake a late seed')
late_base = np.median(np.stack([s['base_depth'] @ np.r_[s['point'], 1.] for s in window]), axis=0)
first = window[-1]
late_seed = first['box'] + [first['color_z'], True]
results = []
for s in samples:
    if s['stamp'] < first['stamp']:
        continue
    row = {'stamp_ns': s['stamp'], 'measured_color_z': s['color_z'],
           'feedback_offset_ns_not_interpolated': s['feedback_offset_ns']}
    for name, base, seed in [('original', locked, original_seed), ('late_candidate', late_base, late_seed)]:
        point = (np.linalg.inv(s['base_depth']) @ base)[:3]
        values = calibration + seed + [True, True, True, .05, .02, 3., 0.] + list(point) + shape
        encoded = ' '.join(str(int(v)) if isinstance(v, bool) else str(v) for v in values)
        reply = subprocess.run([str(a.policy_bin), s['image'], '--scale-details'], input=encoded,
            text=True, capture_output=True, check=True, timeout=8).stdout.splitlines()
        words = reply[0].split(); model_z = float(words[7])
        ratios = list(map(float, reply[1].split()[1:]))
        row[name] = {'decision': words[0], 'model_color_z': model_z,
                     'absolute_range_error_m_approx': abs(model_z - s['color_z']),
                     'scale_growth_width_height': ratios}
    results.append(row)
report = {'offline_only': True, 'hardware_executed': False, 'actual_late_lock_executed': False,
    'freshness_identity_path_allowance_simulated': True, 'exact_image_tf_available': False,
    'latest_feedback_within_20ms_not_interpolated': True, 'urdf_earlier_archive': str(a.urdf),
    'camera_rotation_calibrated': mount['rotation_calibrated'],
    'candidate_window_stamps': [s['stamp'] for s in window],
    'candidate_low_motion_is_not_controller_settle_confirmation': True,
    'candidate_base_point_not_applied': late_base[:3].tolist(), 'frames': results,
    'summary': {name: {'frames': len(results),
       'range_error_median_m_approx': float(np.median([s[name]['absolute_range_error_m_approx'] for s in results])),
       'range_error_max_m_approx': float(max(s[name]['absolute_range_error_m_approx'] for s in results)),
       'scale_passes': sum(all(.65 <= v <= 1.5 for v in s[name]['scale_growth_width_height'][1:]) for s in results)}
       for name in ('original', 'late_candidate')}}
print(json.dumps(report, indent=2))
