#!/usr/bin/env python3
"""P0-only measured-face selection and independent plane audit; no ROS/control.

Native depth, its zeros and all rejected frames remain unchanged. The automatic
local annulus is a TABLE CANDIDATE, not physical proof. Review the witness before
declaring a face to be the top. No mounting TF is used or modified.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from estimate_calibration_cube_center import (fit_plane, frame_hypotheses,
                                              points_from_mask, square_hypothesis,
                                              transform_hypothesis)
from export_calibration_bundle import bundle_asset, observation_capture, verify_bundle
from review_depth_registration import calibration, color_mask, read_config
from review_pair_sampling import selected_pixels

MIN_TOP_INLIERS = 800
MIN_GOOD_FRAMES = 20


def normal_angle_deg(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != (3,) or b.shape != (3,) or not np.isfinite([a, b]).all():
        raise ValueError('Two finite 3D normals required')
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator < 1e-12:
        raise ValueError('Nonzero normals required')
    return float(np.degrees(np.arccos(np.clip(abs(a @ b) / denominator, 0., 1.))))


def graph_plane(points):
    """Independent robust z(x,y) regression, not RANSAC's selected inliers.

    Intended for a visible, non-edge-on plane. No synthesized points. Centered
    and scaled design avoids falsely treating pixel-sized xy as rank deficient.
    """
    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 100 or not np.isfinite(points).all():
        raise ValueError('At least 100 finite measured points required')
    origin = np.median(points, axis=0)
    scale = np.std(points[:, :2], axis=0)
    if np.any(scale < 1e-4):
        raise ValueError('Insufficient two-axis plane support')
    design = np.c_[(points[:, :2] - origin[:2]) / scale, np.ones(len(points))]
    if np.linalg.matrix_rank(design) < 3:
        raise ValueError('Degenerate plane design')
    initial = np.linalg.lstsq(design, points[:, 2] - origin[2], rcond=None)[0]
    result = least_squares(lambda q: design @ q - (points[:, 2] - origin[2]),
                           initial, loss='soft_l1', f_scale=.001,
                           ftol=1e-10, xtol=1e-10, gtol=1e-10)
    if not result.success:
        raise ValueError('Independent graph plane did not converge')
    normal = np.r_[result.x[:2] / scale, -1.]
    normal /= np.linalg.norm(normal)
    residual = (design @ result.x - (points[:, 2] - origin[2])) / np.sqrt(
        1. + np.sum((result.x[:2] / scale) ** 2))
    return {'normal': normal, 'rms_m': float(np.sqrt(np.mean(residual ** 2))),
            'p95_m': float(np.quantile(np.abs(residual), .95)),
            'method': 'all measured ROI points; independent soft_l1 z(x,y) regression'}


def plane_pair_audit(face_points, table_points, face_center, edge_m):
    """Do not hard-require parallelism: report the suspected 7--8deg discrepancy."""
    face = fit_plane(face_points)
    # Limit RANSAC cost only; the independent regression uses the full ROI.
    table = fit_plane(table_points[::max(1, len(table_points) // 4000)])
    face_alt, table_alt = graph_plane(face_points), graph_plane(table_points)
    height = float((np.asarray(face_center) - table['origin']) @ table['normal'])
    measured_table_inliers = int((np.abs((table_points - table['origin']) @ table['normal']) <= .002).sum())
    return {'method_A': 'separate RANSAC + orthogonal SVD fits',
            'method_B': 'separate all-point robust graph regression',
            'normal_difference_A_deg': normal_angle_deg(face['normal'], table['normal']),
            'normal_difference_B_deg': normal_angle_deg(face_alt['normal'], table_alt['normal']),
            'face_method_disagreement_deg': normal_angle_deg(face['normal'], face_alt['normal']),
            'table_method_disagreement_deg': normal_angle_deg(table['normal'], table_alt['normal']),
            'face_normal_depth_A': face['normal'].tolist(),
            'table_normal_depth_A': table['normal'].tolist(),
            'face_normal_depth_B': face_alt['normal'].tolist(),
            'table_normal_depth_B': table_alt['normal'].tolist(),
            'face_rms_A_m': face['rms_m'], 'table_rms_A_m': table['rms_m'],
            'face_rms_B_m': face_alt['rms_m'], 'table_rms_B_m': table_alt['rms_m'],
            'table_native_samples': len(table_points), 'table_plane_inliers': measured_table_inliers,
            'face_center_height_above_table_candidate_m': height,
            'height_minus_nominal_edge_m': height - edge_m,
            'top_identity_confirmed': False,
            'reason': 'Automatic annulus/table and dominant face require witness review; no normal/height threshold silently declares a top.',
            'mounting_TF_can_change_relative_normal_angle': False}


def table_mask(projected, valid_depth_mask, cube_mask, bbox):
    """Nearby RGB rectangular annulus, excluding cube and a 50% bbox margin."""
    if bbox is None:
        return np.zeros(valid_depth_mask.shape, bool)
    x, y, w, h = bbox
    px, py = projected[..., 0], projected[..., 1]
    outer = ((px >= x - 2 * w) & (px < x + 3 * w) &
             (py >= y - 2 * h) & (py < y + 3 * h))
    inner = ((px >= x - .5 * w) & (px < x + 1.5 * w) &
             (py >= y - .5 * h) & (py < y + 1.5 * h))
    inside = ((px >= 0) & (px < cube_mask.shape[1]) &
              (py >= 0) & (py < cube_mask.shape[0]))
    selected = valid_depth_mask & outer & ~inner & inside
    yy, xx = np.where(selected)
    selected[yy, xx] &= cube_mask[py[yy, xx], px[yy, xx]] == 0
    return selected


def top_hypothesis(cube_points, table_points, camera):
    """Explicit table-supported top hypothesis, not the largest of all faces.

    Assumes the cube rests on the local annulus plane. A +/-6mm height band
    allows depth/nominal-size uncertainty; it is not a parallel-normal filter.
    Full measured-square checks still apply; absent support is never filled.
    """
    table = fit_plane(table_points[::max(1, len(table_points) // 4000)])
    if np.mean(np.abs((table_points - table['origin']) @ table['normal']) <= .002) < .6:
        raise ValueError('Automatic table annulus has no dominant plane')
    heights = (cube_points - table['origin']) @ table['normal']
    selected = np.abs(heights - .029) <= .006
    candidate = transform_hypothesis(square_hypothesis(cube_points[selected], .029), camera)
    candidate['selection'] = {'method': 'measured height over local table candidate, then complete square fit',
                              'height_band_m': [.023, .035],
                              'native_height_selected_points': int(selected.sum()),
                              'assumption': 'Identified local annulus is table; cube rests on it',
                              'physical_top_identity_independently_verified': False}
    return candidate, cube_points[selected]


def complete_box(box, rgb_size):
    return bool(box is not None and min(box[:2]) > 0 and
                box[0] + box[2] < rgb_size[0] and box[1] + box[3] < rgb_size[1])


def review_frame(row, params, camera):
    hypothesis = frame_hypotheses(row, params, camera, [.029])  # original SHA checks
    candidate = hypothesis['candidate_by_nominal_edge_mm'].get('29')
    rgb = cv2.imread(row['images']['rgb']['path'])
    depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
    info = row['latest']['/camera/depth/camera_info']
    if (info['frame'] != 'camera_depth_optical_frame' or
            row['images']['depth']['frame'] != info['frame'] or
            row['images']['rgb']['frame'] != 'camera_color_optical_frame'):
        raise ValueError('Actual D/C optical frame mismatch; never relabel measured points')
    kd = np.asarray(info['k']).reshape(3, 3)
    selected, projected, _, _ = selected_pixels(rgb, depth, info, params, camera)
    mask, _ = color_mask(rgb, params)
    valid = ((depth > 0) & (depth * .001 >= params['min_depth_m']) &
             (depth * .001 <= params['max_depth_m']))
    surrounding = table_mask(projected, valid, mask, hypothesis['rgb_bbox_xywh'])
    top, top_audit, top_error = None, None, None
    cube_points = points_from_mask(depth, kd, selected)
    table_points = points_from_mask(depth, kd, surrounding)
    if hypothesis['color_pixel_coverage'] >= .5 and complete_box(hypothesis['rgb_bbox_xywh'], rgb.shape[1::-1]):
        try:
            top, top_points = top_hypothesis(cube_points, table_points, camera)
            top_audit = plane_pair_audit(top_points, table_points, top['face_center_depth_m'], .029)
        except ValueError as exc:
            top_error = str(exc)
    else:
        top_error = 'Insufficient real coverage or truncated color target; no top extrapolation'
    audit, error = None, None
    if candidate:
        try:
            audit = plane_pair_audit(points_from_mask(depth, kd, selected),
                                     points_from_mask(depth, kd, surrounding),
                                     candidate['face_center_depth_m'], .029)
        except ValueError as exc:
            error = str(exc)
    # A separate sensitivity witness, not a changed selection or a replacement
    # for the original normal. Native-mask erosion removes edge points only.
    core = cv2.erode(selected.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    core_audit = {'native_erosion_radius_px': 2, 'native_samples': int(core.sum()),
                  'used_to_replace_center_or_filter_good_frames': False}
    if candidate and int(core.sum()) >= 100:
        try:
            core_points = points_from_mask(depth, kd, core)
            core_plane, core_graph = fit_plane(core_points), graph_plane(core_points)
            core_audit.update(normal_depth_A=core_plane['normal'].tolist(),
                              normal_depth_B=core_graph['normal'].tolist(),
                              method_disagreement_deg=normal_angle_deg(core_plane['normal'], core_graph['normal']))
            if audit:
                core_audit['difference_from_table_A_deg'] = normal_angle_deg(
                    core_plane['normal'], audit['table_normal_depth_A'])
                core_audit['difference_from_table_B_deg'] = normal_angle_deg(
                    core_graph['normal'], audit['table_normal_depth_B'])
        except ValueError as exc:
            core_audit['error'] = str(exc)
    count = candidate['plane_inliers'] if candidate else 0
    result = {'snapshot': row['snapshot'], 'stamps_ns': hypothesis['stamps_ns'],
              'actual_q_rad': row['q_rad'], 'raw_image_sha256': hypothesis['raw_image_sha256'],
              'native_selected_points': hypothesis['native_selected_points'],
              'color_pixel_coverage': hypothesis['color_pixel_coverage'],
              'plane_inliers': count, 'minimum_800_face_inliers_met': count >= MIN_TOP_INLIERS,
              'face_quality_candidate': bool(candidate and count >= MIN_TOP_INLIERS),
              'good_top_frame': bool(top and top['plane_inliers'] >= MIN_TOP_INLIERS),
              'top_identity_confirmed': False,
              'top_candidate': top, 'top_plane_audit': top_audit, 'top_error': top_error,
              'top_plane_inliers': top['plane_inliers'] if top else 0,
              'good_top_definition': 'Complete measured square at 29+/-6mm above automatic table candidate, >=800 native plane inliers; conditional geometric quality, not physical/calibration approval',
              'cube_center_color_candidate_m': candidate['cube_center_color_m'] if candidate else None,
              'cube_center_depth_candidate_m': candidate['cube_center_depth_m'] if candidate else None,
              'candidate': candidate, 'plane_audit': audit, 'plane_audit_error': error,
              'edge_sensitivity_audit': core_audit,
              'rejected': hypothesis.get('rejected') or hypothesis['rejected_by_nominal_edge_mm'],
              'brightness_mean_bgr': np.mean(rgb, axis=(0, 1)).tolist(),
              'exposure': None, 'gain': None, 'illumination_lux': None,
              'exposure_source': 'Not present in image/CameraInfo; never inferred from brightness'}
    # Separate derived diagnostic; source images are never annotated in place.
    witness = rgb.copy()
    yy, xx = np.where(surrounding)
    witness[projected[yy, xx, 1], projected[yy, xx, 0]] = (255, 255, 0)
    yy, xx = np.where(selected)
    witness[projected[yy, xx, 1], projected[yy, xx, 0]] = (0, 0, 255)
    if top:
        inside = np.abs((top_points - top['plane_origin_depth_m']) @ np.asarray(top['outward_normal_depth'])) <= .002
        measured = top_points[inside]
        native_x = np.rint(measured[:, 0] / measured[:, 2] * kd[0, 0] + kd[0, 2]).astype(int)
        native_y = np.rint(measured[:, 1] / measured[:, 2] * kd[1, 1] + kd[1, 2]).astype(int)
        uv = projected[native_y, native_x]
        witness[uv[:, 1], uv[:, 0]] = (0, 255, 0)
    return result, witness


def summarize(frames):
    good = [f for f in frames if f['good_top_frame']]
    audits = [f['top_plane_audit'] for f in frames if f.get('top_plane_audit')]
    normal_stats = {key: {'minimum': float(np.min([f[key] for f in audits])),
                          'median': float(np.median([f[key] for f in audits])),
                          'maximum': float(np.max([f[key] for f in audits]))}
                    for key in ('normal_difference_A_deg', 'normal_difference_B_deg',
                                'face_method_disagreement_deg', 'table_method_disagreement_deg')} if audits else None
    return {'frames': len(frames), 'face_quality_candidates': sum(f['face_quality_candidate'] for f in frames),
            'good_top_frames': len(good), 'minimum_good_frames': MIN_GOOD_FRAMES,
            'twenty_good_frames_met': len(good) >= MIN_GOOD_FRAMES,
            'automatic_replenishment_needed': len(good) < MIN_GOOD_FRAMES,
            'top_witness_review_required': any((f['face_quality_candidate'] or f['good_top_frame']) and not f['top_identity_confirmed'] for f in frames),
            'top_plane_normal_statistics': normal_stats,
            'formal_calibration_pair': False}


def review(bundle, output, capture=None):
    if output.exists():
        raise FileExistsError('Refusing to overwrite evidence')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    verify_bundle(bundle, manifest)
    capture = observation_capture(bundle, manifest, capture)
    params = read_config(bundle / 'detector_config.yaml'); camera = calibration(params)
    rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line]
    output.mkdir(parents=True, exist_ok=False)
    frames, witnesses = [], []
    for row in rows:
        for item in row['images'].values():
            item['path'] = str(bundle_asset(capture, item['path']))
        result, witness = review_frame(row, params, camera)
        frames.append(result)
        if len(witnesses) < 2 and (result['face_quality_candidate'] or not witnesses):
            name = f'annulus_witness_{row["snapshot"]:04d}.png'
            if not cv2.imwrite(str(output / name), witness):
                raise RuntimeError('Failed to save diagnostic witness')
            witnesses.append(name)
    report = {'schema': 'piper_calibration_p0_quality_v1', 'offline_only': True,
              'motion_commands_sent': False, 'raw_modified': False,
              'capture': capture.name,
              'source_manifest_sha256': hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'fitting_input_frame': 'camera_color_optical_frame',
              'native_depth_frame': 'camera_depth_optical_frame',
              'transform': 'p_C = R_C_D p_D + t_C_D; unchanged factory pinhole/endpoint projection',
              'minimum_top_plane_inliers': MIN_TOP_INLIERS,
              'selection_is_not_a_motion_gate': True,
              'table_ROI': 'cyan = automatic local annulus; red = selected native cube projections; green = measured top-hypothesis plane inliers; physical identity unverified',
              'nominal_cube_edge_m': .029, 'caliper_measurement_confirmed': False,
              'summary': summarize(frames), 'frames': frames, 'witnesses': witnesses}
    with (output / 'report.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report['summary']))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-dir')
    args = parser.parse_args()
    review(args.bundle, args.output, args.capture_dir)


if __name__ == '__main__':
    main()
