#!/usr/bin/env python3
"""Pure numerical point-pair calibration simulation; no robot motion or ROS.

Cases are explicitly synthetic. These poses are not executable joint samples.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from fit_paired_calibration import solve


def make_dataset(kind='diverse', noise_m=0., seed=17, known_point=False):
    rng = np.random.default_rng(seed)
    mount = np.eye(4)
    mount[:3, :3] = Rotation.from_euler('xyz', [10., -22., 8.], degrees=True).as_matrix()
    mount[:3, 3] = [-.04, .012, .031]
    center = np.array([.002, -.003, .135])
    observe = np.eye(4); observe[:3, 3] = [.05, -.02, .1]
    coordinates = [[-.10, -.07, .43], [.09, -.06, .47], [-.08, .08, .51],
                   [.1, .09, .40], [.015, -.015, .55], [-.04, .02, .48]]
    tilts = [[0., 0., 0.], [18., -12., 45.], [-20., 14., 85.],
             [12., 22., 140.], [-16., -18., 190.], [15., -15., 250.]]
    pairs = []
    for i, (coordinate, angles) in enumerate(zip(coordinates, tilts)):
        p = np.array(coordinate)
        if kind == 'collinear':
            p = np.array([-.1 + .04 * i, 0., .45])
        grip = np.eye(4)
        if kind == 'yaw_only':
            angles = [0., 0., 40. * i]
        grip[:3, :3] = Rotation.from_euler('xyz', angles, degrees=True).as_matrix()
        base_center = (observe @ mount @ np.r_[p, 1])[:3]
        grip[:3, 3] = base_center - grip[:3, :3] @ center
        measured = p + rng.normal(0., noise_m, 3)
        pairs.append({'pair_id': f'synthetic_{i+1:02d}', 'role': 'validation' if i == 5 else 'fit',
            'reference': 'cube_geometric_center', 'camera_center_verified': True,
            'physical_grip_verified': True, 'released_without_object_motion_verified': True,
            'camera_center_m': measured.tolist(), 'T_base_tool_observe': observe.tolist(),
            'T_base_tool_grip': grip.tolist(), 'synthetic_not_hardware': True})
    document = {'schema_version': 1, 'synthetic': True,
        'frames': {'base': 'base_link', 'tool': 'gripper_base', 'camera': 'camera_depth_optical_frame'},
        'nominal_cube_edge_m_not_a_measurement': .029, 'pairs': pairs}
    if known_point:
        document['known_tool_point'] = {'verified': True, 'point_m': center.tolist(),
                                       'source': 'Synthetic exact point, not real TCP'}
    return document, mount, center


def run_simulation():
    results = {}
    for label, kind, noise, known in [
            ('diverse_exact_joint', 'diverse', 0., False),
            ('yaw_only_unknown_center', 'yaw_only', 0., False),
            ('yaw_only_known_center', 'yaw_only', 0., True),
            ('collinear_known_center', 'collinear', 0., True),
            ('diverse_3mm_noise', 'diverse', .003, False)]:
        data, truth, center = make_dataset(kind, noise, known_point=known)
        result = solve(data)
        result['noise_std_per_axis_m'] = noise
        if result['candidate'] is not None:
            fitted = np.asarray(result['candidate']['X_tool_from_depth_camera'])
            result['synthetic_truth_error'] = {
                'translation_m': float(np.linalg.norm(fitted[:3, 3] - truth[:3, 3])),
                'rotation_deg': float(np.degrees(Rotation.from_matrix(truth[:3, :3].T @ fitted[:3, :3]).magnitude())),
                'tool_center_m': float(np.linalg.norm(np.array(result['candidate']['cube_center_in_tool_m']) - center))}
        results[label] = result
    # A real point cannot be fabricated from an absent center, even with valid
    # FK and otherwise ideal data. Input rejection is expected, not a fit.
    missing, _, _ = make_dataset()
    missing['pairs'][0]['camera_center_m'] = None
    try:
        solve(missing)
    except ValueError as error:
        results['missing_depth_center'] = {'input_rejected': str(error), 'candidate': None}
    else:
        raise AssertionError('Missing point was accepted')
    # Small training residual is not evidence of unbiased generalization.
    shifted, _, _ = make_dataset(known_point=True)
    for pair in shifted['pairs'][:5]:
        pair['camera_center_m'][2] += .025
    results['training_only_25mm_bias'] = solve(shifted)
    noise_trials = []
    for seed in range(20):
        data, _, _ = make_dataset(noise_m=.003, seed=seed)
        result = solve(data)
        noise_trials.append(result['held_out_validation']['maximum_m'])
    assert results['diverse_exact_joint']['synthetic_truth_error']['translation_m'] < 1e-7
    assert results['diverse_exact_joint']['synthetic_truth_error']['rotation_deg'] < 1e-5
    assert results['yaw_only_unknown_center']['candidate'] is None
    assert results['yaw_only_known_center']['candidate'] is not None
    assert results['collinear_known_center']['candidate'] is None
    assert results['training_only_25mm_bias']['held_out_validation']['maximum_m'] > .02
    return {'synthetic_only': True, 'hardware_or_production_touched': False,
        'cases': results, 'twenty_noise_trials': {'per_axis_camera_noise_m': .003,
            'held_out_error_m': noise_trials, 'median_m': float(np.median(noise_trials)),
            'p95_m': float(np.quantile(noise_trials, .95))},
        'not_a_reachable_pose_proposal': True,
        'conclusion': 'Diverse positions plus yaw alone do not identify mount and unknown grip depth; known-tool-point model or additional tilt constraints are necessary.'}


def run_face_pipeline_simulation():
    """Synthetic measured-face clouds -> centers -> 5 fit/1 held-out point.

    Gaussian point noise, depth quantization, sparse missing samples and large
    outliers are synthetic; no sensor/ROS/Gazebo or arm-motion claim is made.
    """
    from estimate_calibration_cube_center import square_hypothesis
    records = []
    for seed in range(10):
        dataset, mount, tool = make_dataset()
        rng = np.random.default_rng(seed)
        errors = []
        for i, pair in enumerate(dataset['pairs']):
            center = np.array(pair['camera_center_m'])
            rotation = Rotation.from_euler('xyz', [12. + i * 2., -5. + i, 15. * i], degrees=True).as_matrix()
            normal = -rotation[:, 2]
            face = center + .029 / 2. * normal
            coordinates = np.linspace(-.029 / 2., .029 / 2., 31)
            xx, yy = np.meshgrid(coordinates, coordinates)
            cloud = face + np.c_[xx.ravel(), yy.ravel(), np.zeros(xx.size)] @ rotation.T
            cloud += rng.normal(0., .0003, cloud.shape)
            cloud[:, 2] = np.round(cloud[:, 2] * 1000.) / 1000.
            cloud = cloud[rng.random(len(cloud)) < .7]
            outliers = cloud[:50].copy(); outliers[:, 2] += .02
            hypothesis = square_hypothesis(np.vstack((cloud, outliers)), .029)
            measured = np.array(hypothesis['cube_center_depth_m'])
            errors.append(float(np.linalg.norm(measured - center)))
            pair['camera_center_m'] = measured.tolist()
            pair['camera_center_source'] = 'Synthetic known-face point cloud; not physical evidence'
        fitted = solve(dataset)
        candidate = fitted['candidate']
        if candidate is None:
            raise AssertionError('Synthetic diverse pose dataset unexpectedly degenerate')
        matrix = np.asarray(candidate['X_tool_from_depth_camera'])
        records.append({'seed': seed, 'camera_center_errors_m': errors,
            'mount_translation_error_m': float(np.linalg.norm(matrix[:3, 3] - mount[:3, 3])),
            'mount_rotation_error_deg': float(np.degrees(Rotation.from_matrix(mount[:3, :3].T @ matrix[:3, :3]).magnitude())),
            'tool_point_error_m': float(np.linalg.norm(np.array(candidate['cube_center_in_tool_m']) - tool)),
            'training_rms_m': fitted['training']['rms_m'],
            'held_out_error_m': fitted['held_out_validation']['maximum_m'],
            'rank': fitted['excitation']['rank']})
    return {'synthetic_only': True, 'hardware_or_production_touched': False,
        'mode': 'Point cloud simulation, not raster RGB-D hardware or physical trajectory simulation',
        'nominal_edge_m': .029, 'point_noise_per_axis_m': .0003,
        'z_quantization_m': .001, 'random_missing_fraction': .3, 'outlier_z_shift_m': .02,
        'trials': records, 'held_out_error_p95_m': float(np.quantile([r['held_out_error_m'] for r in records], .95)),
        'maximum_camera_center_error_m': max(max(r['camera_center_errors_m']) for r in records),
        'not_a_real_calibration_precision_claim': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--face-pipeline', action='store_true', help='Run synthetic noisy-face -> center -> mount fit pipeline')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite a previous simulation')
    result = run_face_pipeline_simulation() if args.face_pipeline else run_simulation()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    if args.face_pipeline:
        print(json.dumps({'output': str(args.output), 'synthetic_only': True,
            'held_out_error_p95_m': result['held_out_error_p95_m'],
            'maximum_camera_center_error_m': result['maximum_camera_center_error_m']}))
    else:
        print(json.dumps({'output': str(args.output), 'synthetic_only': True,
            'exact': result['cases']['diverse_exact_joint']['synthetic_truth_error'],
            'yaw_joint_rank': result['cases']['yaw_only_unknown_center']['excitation']['rank'],
            'noise_validation_p95_m': result['twenty_noise_trials']['p95_m']}))


if __name__ == '__main__':
    main()
