#!/usr/bin/env python3
"""Offline P0 closeout: fixed spatial regions and top-edge sensitivity.

Does not tune collection thresholds, alter raw points, deploy TF or access ROS.
The original top point set is fixed while table regions are compared. Boundary
erosion is a labelled sensitivity experiment, never a replacement good frame.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from calibration_p0_quality import graph_plane, normal_angle_deg, table_mask, top_hypothesis
from estimate_calibration_cube_center import fit_plane, points_from_mask
from export_calibration_bundle import bundle_asset, observation_capture, verify_bundle
from review_depth_registration import calibration, color_mask, read_config
from review_pair_sampling import selected_pixels


def regions(projected, surrounding, box):
    """Predeclared equal-scale patches, without selecting by fitted angle."""
    x, y, w, h = box
    u, v = projected[..., 0], projected[..., 1]
    across = (u >= x - .5 * w) & (u < x + 1.5 * w)
    beside = (v >= y - .25 * h) & (v < y + 1.25 * h)
    return {
        'original_ring': surrounding.copy(),
        'local_left': surrounding & beside & (u >= x - 1.5 * w) & (u < x - .5 * w),
        'local_right': surrounding & beside & (u >= x + 1.5 * w) & (u < x + 2.5 * w),
        'local_above': surrounding & across & (v >= y - 1.5 * h) & (v < y - .5 * h),
        'local_below': surrounding & across & (v >= y + 1.5 * h) & (v < y + 2.5 * h)}


def compare_planes(points):
    """Report independent all-point B and a separate same-support diagnostic."""
    a = fit_plane(points[::max(1, len(points) // 4000)])
    b = graph_plane(points)
    inliers = np.abs((points - a['origin']) @ a['normal']) <= .002
    b_same = graph_plane(points[inliers])
    return {'native_points': len(points), 'A_inliers': int(inliers.sum()),
            'normal_A': a['normal'].tolist(), 'normal_B': b['normal'].tolist(),
            'origin_A_m': a['origin'].tolist(),
            'normal_B_on_A_support': b_same['normal'].tolist(),
            'A_vs_B_deg': normal_angle_deg(a['normal'], b['normal']),
            'A_vs_B_same_support_deg': normal_angle_deg(a['normal'], b_same['normal']),
            'rms_A_m': a['rms_m'], 'rms_B_m': b['rms_m'],
            'B_same_support_is_not_an_independent_support_test': True}


def aligned_normal(normal, reference):
    normal = np.asarray(normal, float)
    normal /= np.linalg.norm(normal)
    return normal if normal @ reference >= 0 else -normal


def half_edge_shift(normal_a, normal_b, edge_m=.029):
    a = np.asarray(normal_a, float)
    a /= np.linalg.norm(a)
    b = aligned_normal(normal_b, a)
    # Face center held fixed; excludes depth, boundary and TCP errors.
    return float(np.linalg.norm((a - b) * edge_m / 2.))


def audit_frame(row, params, camera):
    rgb = cv2.imread(row['images']['rgb']['path'])
    depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
    info = row['latest']['/camera/depth/camera_info']
    if depth.dtype != np.uint16 or info['frame'] != 'camera_depth_optical_frame':
        raise ValueError('Native uint16 D optical points required')
    kd = np.asarray(info['k']).reshape(3, 3)
    selected, projected, _, contour = selected_pixels(rgb, depth, info, params, camera)
    if contour is None:
        raise ValueError('Missing cube contour; no region guessed')
    box = list(cv2.boundingRect(contour))
    mask, _ = color_mask(rgb, params)
    valid = (depth > 0) & (depth * .001 >= params['min_depth_m']) & (depth * .001 <= params['max_depth_m'])
    surrounding = table_mask(projected, valid, mask, box)
    top, top_points = top_hypothesis(points_from_mask(depth, kd, selected),
                                    points_from_mask(depth, kd, surrounding), camera)
    top_fit = compare_planes(top_points)
    patch_fits = {}
    patches = regions(projected, surrounding, box)
    for label, patch in patches.items():
        try:
            fit = compare_planes(points_from_mask(depth, kd, patch))
            fit['top_vs_region_A_deg'] = normal_angle_deg(top_fit['normal_A'], fit['normal_A'])
            fit['top_vs_region_B_deg'] = normal_angle_deg(top_fit['normal_B'], fit['normal_B'])
            fit['top_face_height_over_region_A_m'] = float(
                (np.asarray(top['face_center_depth_m']) - fit['origin_A_m']) @ np.asarray(fit['normal_A']))
            patch_fits[label] = fit
        except ValueError as exc:
            patch_fits[label] = {'error': str(exc), 'native_points': int(patch.sum())}
    # Recover the exact measured native support; erosion removes, never fills.
    top_mask = np.zeros(depth.shape, np.uint8)
    x = np.rint(top_points[:, 0] / top_points[:, 2] * kd[0, 0] + kd[0, 2]).astype(int)
    y = np.rint(top_points[:, 1] / top_points[:, 2] * kd[1, 1] + kd[1, 2]).astype(int)
    top_mask[y, x] = 1
    edges = []
    for radius in (0, 1, 2, 3):
        eroded = cv2.erode(top_mask, np.ones((2 * radius + 1,) * 2, np.uint8)) > 0
        item = {'removed_native_boundary_radius_px': radius, 'native_points': int(eroded.sum())}
        try:
            fit = compare_planes(points_from_mask(depth, kd, eroded))
            item.update(fit)
            item['A_change_from_original_deg'] = normal_angle_deg(top_fit['normal_A'], fit['normal_A'])
            item['B_change_from_original_deg'] = normal_angle_deg(top_fit['normal_B'], fit['normal_B'])
            item['normal_only_center_shift_A_m'] = half_edge_shift(top_fit['normal_A'], fit['normal_A'])
            if 'normal_A' in patch_fits['local_below']:
                item['top_vs_local_below_A_deg'] = normal_angle_deg(fit['normal_A'], patch_fits['local_below']['normal_A'])
        except ValueError as exc:
            item['error'] = str(exc)
        edges.append(item)
    # Non-overlapping patches drawn on a NEW witness, not on original RGB.
    witness = rgb.copy()
    colors = {'local_left': (255, 0, 0), 'local_right': (0, 128, 255),
              'local_above': (255, 255, 0), 'local_below': (255, 0, 255)}
    for label, color in colors.items():
        yy, xx = np.where(patches[label])
        uv = projected[yy, xx]
        witness[uv[:, 1], uv[:, 0]] = color
    return {'snapshot': row['snapshot'], 'actual_q_rad': row['q_rad'], 'stamps_ns': row['stamps_ns'],
            'raw_sha256': {name: item['sha256'] for name, item in row['images'].items()},
            'rgb_box_xywh': box, 'original_top_fit': top_fit, 'table_regions': patch_fits,
            'top_edge_sensitivity': edges,
            'normal_only_A_vs_B_center_shift_m': half_edge_shift(top_fit['normal_A'], top_fit['normal_B']),
            'normal_only_shift_caveat': 'Fixed face center, inward nominal14.5mm offset only; not total center uncertainty or absolute accuracy'}, witness


def summary(frames):
    result = {}
    for region in ('original_ring', 'local_left', 'local_right', 'local_above', 'local_below'):
        good = [f['table_regions'][region] for f in frames if 'error' not in f['table_regions'][region]]
        result[region] = {'usable_frames': len(good)}
        for key in ('A_vs_B_deg', 'A_vs_B_same_support_deg', 'top_vs_region_A_deg',
                    'top_vs_region_B_deg', 'top_face_height_over_region_A_m'):
            values = [p[key] for p in good]
            result[region][key] = ({'minimum': float(np.min(values)), 'median': float(np.median(values)),
                                   'maximum': float(np.max(values))} if values else None)
    return {'table_regions': result,
            'maximum_normal_only_A_vs_B_center_shift_m': max(
                f['normal_only_A_vs_B_center_shift_m'] for f in frames) if frames else None,
            'physical_table_or_cube_orthogonality_verified': False,
            'camera_depth_systematic_error_excluded': False,
            'calibration_or_TF_adoption_approved': False}


def audit(bundle, output):
    if output.exists():
        raise FileExistsError('Refusing to overwrite evidence')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    verify_bundle(bundle, manifest)
    capture = observation_capture(bundle, manifest)
    params = read_config(bundle / 'detector_config.yaml'); camera = calibration(params)
    rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line]
    if len(rows) < 6:
        raise ValueError('Six representative frames required; no repeated samples invented')
    indices = np.rint(np.linspace(0, len(rows) - 1, 6)).astype(int).tolist()
    output.mkdir(parents=True, exist_ok=False)
    frames = []
    for index in indices:
        row = rows[index]
        for item in row['images'].values():
            item['path'] = str(bundle_asset(capture, item['path']))
        result, witness = audit_frame(row, params, camera)
        frames.append(result)
        if index == indices[0]:
            if not cv2.imwrite(str(output / 'region_witness.png'), witness):
                raise RuntimeError('Derived witness write failed')
    dependencies = [Path(__file__), Path(__file__).with_name('calibration_p0_quality.py'),
                    Path(__file__).with_name('estimate_calibration_cube_center.py')]
    report = {'schema': 'piper_p0_plane_regions_v1', 'offline_only': True,
              'raw_modified': False, 'motion_commands_sent': False, 'production_parameters_modified': False,
              'source_manifest_sha256': hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest(),
              'dependency_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},
              'frame_selection': 'six equally spaced recorded indices, not selected for favorable residual',
              'source_frame_indices_zero_based': indices,
              'top_point_set_fixed_during_table_comparisons': True,
              'region_geometry': 'relative to RGB bbox x,y,w,h; same original valid native-depth annulus',
              'witness_legend': 'left blue/right orange/above cyan/below magenta; raw RGB separately preserved',
              'no_changes_to_quality_thresholds_or_good_frame_count': True,
              'frames': frames, 'summary': summary(frames)}
    with (output / 'report.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report['summary']))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.bundle, args.output)


if __name__ == '__main__':
    main()
