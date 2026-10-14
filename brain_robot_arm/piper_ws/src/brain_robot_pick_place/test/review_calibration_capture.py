#!/usr/bin/env python3
"""Offline, reproducible RGB-D calibration evidence review; never sends motion.

Reuse the existing registration audit. Per-frame surface medians and their
temporal dispersion are measurements, not cube centers or accuracy guarantees.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from review_depth_registration import calibration, color_mask, project_measured, read_config


def temporal_summary(frames, minimum_frames=30):
    usable = [f for f in frames if f.get('surface_z_m') is not None]
    values = np.array([f['surface_z_m'] for f in usable], dtype=float)
    if not len(values):
        return {'usable_frames': 0, 'requested_frames': minimum_frames, 'median_z_m': None,
                'thirty_frame_requirement_met': False, 'accuracy_verified': False}
    median = float(np.median(values))
    return {'usable_frames': len(values), 'requested_frames': minimum_frames,
            'median_z_m': median, 'temporal_mad_m': float(np.median(np.abs(values - median))),
            'p05_p95_z_m': np.quantile(values, [.05, .95]).tolist(),
            'minimum_maximum_z_m': [float(values.min()), float(values.max())],
            'peak_to_peak_m': float(np.ptp(values)),
            'thirty_frame_requirement_met': len(values) >= minimum_frames,
            'accuracy_verified': False,
            'warning': 'Static precision is not absolute accuracy. No low-coverage frame is silently removed.'}


def cube_center_from_face(face_center, outward_normal, edge_m):
    """Only valid for an identified physical face CENTER, not any surface sample."""
    point, normal = np.asarray(face_center, float), np.asarray(outward_normal, float)
    if point.shape != (3,) or normal.shape != (3,) or not np.isfinite(point).all() or not np.isfinite(normal).all():
        raise ValueError('Expected finite 3D face center and outward normal')
    norm = np.linalg.norm(normal)
    if not np.isfinite(edge_m) or edge_m <= 0 or norm < 1e-12:
        raise ValueError('Invalid cube edge or face normal')
    return (point - float(edge_m) / 2 * normal / norm).tolist()


def frame_review(row, params, camera):
    paths = {k: Path(v['path']) for k, v in row['images'].items()}
    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['images'][name]['sha256']:
            raise ValueError('Image SHA mismatch: ' + str(path))
    rgb, depth = cv2.imread(str(paths['rgb'])), cv2.imread(str(paths['depth']), cv2.IMREAD_UNCHANGED)
    if rgb is None or depth is None or depth.dtype != np.uint16 or depth.ndim != 2:
        raise ValueError('Expected native uint16 millimetre depth, not a visualization')
    info = row['latest']['/camera/depth/camera_info']
    if list(depth.shape[::-1]) != info['size']:
        raise ValueError('Depth/CameraInfo size differs')
    kd = np.array(info['k']).reshape(3, 3)
    mask, contour = color_mask(rgb, params)
    erosion = int(params['depth_erode_px'])
    mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erosion + 1,) * 2))
    _, pixel, valid = project_measured(depth, kd, camera, rgb.shape[1::-1], params)
    selected = np.zeros(depth.shape, bool)
    yy, xx = np.where(valid)
    selected[yy, xx] = mask[pixel[yy, xx, 1], pixel[yy, xx, 0]] > 0
    y, x = np.where(selected)
    z = depth[selected].astype(float) * .001
    occupied = np.zeros(mask.shape, np.uint8)
    occupied[pixel[y, x, 1], pixel[y, x, 0]] = 255
    count_mask = int(np.count_nonzero(mask))
    xyz = np.column_stack(((x - kd[0, 2]) * z / kd[0, 0],
                           (y - kd[1, 2]) * z / kd[1, 1], z))
    result = {'snapshot': row['snapshot'],
              'stamps_ns': {k: str(v) for k, v in row['stamps_ns'].items()},
              'stamp_span_s': row['stamp_span_s'], 'actual_q_rad': row['q_rad'],
              'rgb_bbox_xywh': list(cv2.boundingRect(contour)) if contour is not None else None,
              'native_depth_samples': len(z), 'eroded_color_pixels': count_mask,
              'color_pixel_coverage': float(np.count_nonzero(occupied) / count_mask) if count_mask else 0.,
              'coverage_definition': 'Unique RGB mask pixels hit by real depth projections / eroded RGB mask pixels; differs from production diagnostic coverage',
              'surface_z_m': float(np.median(z)) if len(z) else None,
              'surface_mad_m': float(np.median(np.abs(z - np.median(z)))) if len(z) else None,
              'surface_componentwise_median_xyz_m': np.median(xyz, axis=0).tolist() if len(z) else None,
              'surface_not_cube_center': True,
              'histogram_mm': {str(int(mm)): int(count) for mm, count in zip(*np.unique(depth[selected], return_counts=True))},
              'depth_info': info, 'images': row['images']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path, nargs='+')
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing analysis')
    params = read_config(args.config)
    camera = calibration(params)
    frames = []
    for capture in args.capture:
        rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line.strip()]
        for row in rows:
            for image in row['images'].values():
                if not Path(image['path']).is_absolute():
                    image['path'] = str(capture / image['path'])
            frames.append(dict(frame_review(row, params, camera), capture_id=capture.name))
    qs = np.array([f['actual_q_rad'] for f in frames])
    report = {'offline_only': True, 'motion_commands_sent': False,
              'captures': [str(c) for c in args.capture], 'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
              'depth_units': 'uint16 millimetres; zero means missing, not a zero-distance sample',
              'registration_mode': 'Unchanged production pinhole D->C R/T, endpoint resize, no distortion correction',
              'raw_samples_never_filled': True, 'target_reference': 'visible surface, not cube center',
              'joint_spread_rad': np.ptp(qs, axis=0).tolist() if len(qs) else None,
              'temporal': temporal_summary(frames),
              'high_support_temporal': temporal_summary([
                  f for f in frames if f['color_pixel_coverage'] >= .5 and f['native_depth_samples'] >= 10]),
              'high_support_definition': 'Offline statistical stratum: >=50% color-mask projection coverage and >=10 measured depth points. All other frames remain in report.',
              'frames': frames,
              'common_reference': {'desired': 'cube geometric center', 'confirmed': False,
                  'camera_method': 'Identify one face center and its outward normal; center = face_center - normal * edge/2',
                  'gripper_method': 'Record verified cube-center coordinates in gripper_base, or jointly estimate a constant offset from multiple non-degenerate manual poses',
                  'do_not': 'Do not add half an edge along the optical ray or assume the configured finger tip is the cube center'}}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'frames': len(frames), 'joint_spread_rad': report['joint_spread_rad'],
                     'temporal': report['temporal'], 'high_support_temporal': report['high_support_temporal']}))


if __name__ == '__main__':
    main()
