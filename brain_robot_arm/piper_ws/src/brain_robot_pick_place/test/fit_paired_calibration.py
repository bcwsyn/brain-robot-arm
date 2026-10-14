#!/usr/bin/env python3
"""Offline point-pair camera installation fit; no ROS, devices or TF writes.

Equation: T_B_G_observe * X_G_D * p_D = T_B_G_grip * c_G.
Only explicitly verified geometric centers may enter. Unknown c_G is estimated
jointly; rank deficiency suppresses the candidate, even with tiny residuals.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def vector(value, size):
    result = np.asarray(value, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f'Expected finite {size}-vector; no missing values may be guessed')
    return result


def transform(value):
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Expected finite complete 4x4 FK transform')
    rotation = matrix[:3, :3]
    if (not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-9, rtol=0) or
            not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0) or
            abs(np.linalg.det(rotation) - 1.) > 1e-6):
        raise ValueError('Invalid rigid transform; do not silently orthogonalize input')
    return matrix


def check_pairs(document):
    if document.get('schema_version') != 1:
        raise ValueError('Expected schema_version=1 point-pair contract, not a legacy surface summary')
    if document.get('frames') != {'base': 'base_link', 'tool': 'gripper_base',
                                  'camera': 'camera_depth_optical_frame'}:
        raise ValueError('Explicit B/G/D frame contract required')
    seen, accepted, excluded = set(), [], []
    for pair in document['pairs']:
        name = pair['pair_id']
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError('Unique nonempty pair_id required')
        seen.add(name)
        if pair['role'] == 'trial':
            excluded.append({'pair_id': name, 'reason': 'Explicit trial, never downweighted into fit'})
            continue
        if pair['role'] not in ('fit', 'validation'):
            raise ValueError('Assign fit/validation/trial before fitting')
        if (pair.get('reference') != 'cube_geometric_center' or
                pair.get('camera_center_verified') is not True or
                pair.get('physical_grip_verified') is not True or
                pair.get('released_without_object_motion_verified') is not True):
            raise ValueError(name + ': missing verified same-center/contact/unmoved evidence')
        p = vector(pair['camera_center_m'], 3)
        if p[2] <= 0:
            raise ValueError(name + ': camera center must be in front of optical frame')
        item = dict(pair, camera_center_m=p,
                    T_base_tool_observe=transform(pair['T_base_tool_observe']),
                    T_base_tool_grip=transform(pair['T_base_tool_grip']))
        accepted.append(item)
    fixed = document.get('known_tool_point')
    if fixed is not None:
        if fixed.get('verified') is not True or not fixed.get('source'):
            raise ValueError('Known tool point must have explicit verification/source, not a tip assumption')
        fixed = vector(fixed['point_m'], 3)
    return accepted, excluded, fixed


def kabsch(source, target):
    a, b = np.asarray(source), np.asarray(target)
    ac, bc = a - a.mean(axis=0), b - b.mean(axis=0)
    u, _, vt = np.linalg.svd(ac.T @ bc)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(vt.T @ u.T)
    r = vt.T @ correction @ u.T
    return r, b.mean(axis=0) - r @ a.mean(axis=0)


def residuals(parameters, pairs, fixed=None):
    r = Rotation.from_rotvec(parameters[:3]).as_matrix()
    translation = parameters[3:6]
    tool_point = parameters[6:9] if fixed is None else fixed
    result = []
    for pair in pairs:
        observed, grip = pair['T_base_tool_observe'], pair['T_base_tool_grip']
        camera_base = observed[:3, :3] @ (r @ pair['camera_center_m'] + translation) + observed[:3, 3]
        grip_base = grip[:3, :3] @ tool_point + grip[:3, 3]
        result.extend(camera_base - grip_base)
    return np.asarray(result)


def jacobian(parameters, pairs, fixed=None):
    # Central differences keep the rank witness independent of the optimizer's
    # finite-difference step/noise. Units are m/rad for rotation, m/m otherwise.
    eps = 1e-6
    columns = []
    for index in range(len(parameters)):
        delta = np.zeros(len(parameters)); delta[index] = eps
        columns.append((residuals(parameters + delta, pairs, fixed) -
                        residuals(parameters - delta, pairs, fixed)) / (2 * eps))
    return np.column_stack(columns)


def excitation(parameters, pairs, fixed=None):
    j = jacobian(parameters, pairs, fixed)
    # Evaluate all directions, including underdetermined prefixes. Relative
    # scale is explicitly fixed, not a rank threshold tuned to the dataset.
    scale = np.ones(len(parameters)); scale[:3] = 10.
    _, singular, vt = np.linalg.svd(j * scale, full_matrices=True)
    complete = np.zeros(len(parameters)); complete[:len(singular)] = singular
    tolerance = complete[0] * 1e-6 if len(complete) and complete[0] else 1e-12
    rank = int(np.count_nonzero(complete > tolerance))
    cameras = np.array([p['camera_center_m'] for p in pairs])
    spans = np.linalg.svd(cameras - cameras.mean(axis=0), compute_uv=False)
    rotations = [p['T_base_tool_grip'][:3, :3] for p in pairs]
    angles = [np.degrees(Rotation.from_matrix(rotations[0].T @ r).magnitude()) for r in rotations]
    return {'rank': rank, 'unknowns': len(parameters), 'fully_identifiable': rank == len(parameters),
        'scaled_singular_values': complete.tolist(),
        'column_scale': scale.tolist(), 'rank_relative_tolerance': 1e-6,
        'condition_number': float(complete[0] / complete[-1]) if rank == len(parameters) else None,
        'camera_position_span_singular_values_m': spans.tolist(),
        'grip_rotation_from_first_deg': angles,
        'null_directions_parameter_units': [(scale * direction).tolist() for direction in vt[rank:]],
        'parameter_order': ['rotation_vector_x', 'rotation_vector_y', 'rotation_vector_z',
                            'mount_tx_m', 'mount_ty_m', 'mount_tz_m'] +
                           ([] if fixed is not None else ['tool_center_x_m', 'tool_center_y_m', 'tool_center_z_m'])}


def errors(parameters, pairs, fixed=None):
    if not pairs:
        return {'pairs': [], 'rms_m': None, 'maximum_m': None}
    xyz = residuals(parameters, pairs, fixed).reshape(-1, 3)
    norms = np.linalg.norm(xyz, axis=1)
    return {'pairs': [{'pair_id': p['pair_id'], 'base_xyz_error_m': v.tolist(), 'norm_m': float(n)}
                     for p, v, n in zip(pairs, xyz, norms)],
            'rms_m': float(np.sqrt(np.mean(norms ** 2))), 'maximum_m': float(norms.max())}


def solve(document):
    pairs, excluded, fixed = check_pairs(document)
    training = [p for p in pairs if p['role'] == 'fit']
    validation = [p for p in pairs if p['role'] == 'validation']
    if len(training) < 3:
        raise ValueError('At least three non-trial training pairs needed; report prefix checks after more samples')
    guessed_point = np.zeros(3) if fixed is None else fixed
    targets = [(np.linalg.inv(p['T_base_tool_observe']) @
                p['T_base_tool_grip'] @ np.r_[guessed_point, 1])[:3] for p in training]
    r, t = kabsch([p['camera_center_m'] for p in training], targets)
    initial = np.r_[Rotation.from_matrix(r).as_rotvec(), t]
    if fixed is None:
        initial = np.r_[initial, guessed_point]
    result = least_squares(lambda x: residuals(x, training, fixed), initial,
                           jac=lambda x: jacobian(x, training, fixed), method='trf',
                           loss='linear', x_scale='jac', max_nfev=2000,
                           ftol=1e-12, xtol=1e-12, gtol=1e-12)
    x = result.x
    audit = excitation(x, training, fixed)
    admissible = bool(result.success and np.isfinite(x).all() and audit['fully_identifiable'])
    candidate = None
    if admissible:
        matrix = np.eye(4)
        matrix[:3, :3] = Rotation.from_rotvec(x[:3]).as_matrix(); matrix[:3, 3] = x[3:6]
        candidate = {'X_tool_from_depth_camera': matrix.tolist(),
                     'cube_center_in_tool_m': (x[6:9] if fixed is None else fixed).tolist(),
                     'not_approved_for_deployment': True}
    report = {'offline_only': True, 'synthetic': bool(document.get('synthetic', False)),
        'production_tf_modified': False, 'candidate': candidate, 'excluded': excluded,
        'equation': 'T_B_G_observe * X_G_D * p_D_center = T_B_G_grip * c_G_center',
        'model': 'joint_unknown_tool_point' if fixed is None else 'verified_known_tool_point',
        'optimizer_success': bool(result.success), 'optimizer_message': str(result.message),
        'training': errors(x, training, fixed), 'held_out_validation': errors(x, validation, fixed),
        'excitation': audit,
        'per_acquired_training_prefix': [dict(excitation(x, training[:i], fixed),
            pair_ids=[p['pair_id'] for p in training[:i]]) for i in range(1, len(training) + 1)],
        'five_plus_one_collection_complete': len(training) >= 5 and len(validation) >= 1,
        'physical_grasp_verified': False,
        'warnings': ['Rank/low residual does not establish ground-truth point definitions or absolute accuracy.',
            'Unmeasured object grip-depth changes violate the constant-tool-point model.',
            'Held-out labels never enter training or initialisation; no automatic outlier deletion.',
            'Synthetic results are never deployable. Physical adoption requires user review.']}
    previous = document.get('previous_X_tool_from_depth_camera')
    if previous is not None and candidate is not None:
        old = transform(previous); new = np.asarray(candidate['X_tool_from_depth_camera'])
        report['previous_mount_comparison'] = {'translation_delta_m': (new[:3, 3] - old[:3, 3]).tolist(),
            'rotation_delta_deg': float(np.degrees(Rotation.from_matrix(old[:3, :3].T @ new[:3, :3]).magnitude()))}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; preserve prior reports')
    document = json.loads(args.pairs.read_text())
    try:
        report = solve(document)
    except (ValueError, KeyError, TypeError) as error:
        report = {'offline_only': True, 'candidate': None, 'input_rejected': str(error),
                  'production_tf_modified': False}
    report['input_sha256'] = hashlib.sha256(args.pairs.read_bytes()).hexdigest()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    ok = report.get('candidate') is not None
    print(json.dumps({'output': str(args.output), 'candidate_available_not_approved': ok,
                      'input_rejected': report.get('input_rejected'), 'synthetic': report.get('synthetic')}))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
