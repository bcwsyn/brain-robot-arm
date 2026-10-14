#!/usr/bin/env python3
"""Offline dominant-face cube-center hypotheses from real native depth.

Uses existing RGB selection and factory D->C, never robot mounting TF. Missing
depth remains missing. A face/nominal-size hypothesis is not physical ground
truth, even with a low temporal standard deviation. No ROS/device interfaces.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from review_calibration_capture import cube_center_from_face, frame_review
from review_depth_registration import calibration, color_mask, project_measured, read_config
from review_pair_sampling import selected_pixels


def fit_plane(points, threshold_m=.002, seed=17):
    points = np.asarray(points, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 100 or
            not np.isfinite(points).all() or not .0005 <= threshold_m <= .004):
        raise ValueError('At least 100 finite measured points and explicit 0.5..4mm plane threshold required')
    rng = np.random.default_rng(seed)
    best, best_error = np.zeros(len(points), bool), np.inf
    for _ in range(256):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal)
        if length < 1e-8:
            continue
        normal /= length
        distances = np.abs((points - a) @ normal)
        inside = distances <= threshold_m
        error = float(np.median(distances[inside])) if inside.any() else np.inf
        if inside.sum() > best.sum() or (inside.sum() == best.sum() and error < best_error):
            best, best_error = inside, error
    if best.sum() < 100:
        raise ValueError('No supported plane; never fabricate a face normal')
    for _ in range(4):
        origin = points[best].mean(axis=0)
        _, singular, vectors = np.linalg.svd(points[best] - origin, full_matrices=False)
        if singular[1] < .005:
            raise ValueError('Degenerate line/point support cannot define a face')
        normal = vectors[2]
        next_inside = np.abs((points - origin) @ normal) <= threshold_m
        if next_inside.sum() < 100:
            raise ValueError('Refined plane lost measured support')
        if np.array_equal(next_inside, best):
            break
        best = next_inside
    origin = points[best].mean(axis=0)
    _, singular, vectors = np.linalg.svd(points[best] - origin, full_matrices=False)
    normal = vectors[2]
    if normal @ origin > 0:
        normal = -normal  # outward visible normal points towards optical origin
    axis0 = vectors[0]
    axes = np.vstack((axis0, np.cross(normal, axis0)))
    distances = np.abs((points[best] - origin) @ normal)
    return {'origin': origin, 'normal': normal, 'axes': axes, 'inliers': best,
            'rms_m': float(np.sqrt(np.mean(distances ** 2))),
            'p95_m': float(np.quantile(distances, .95)),
            'singular_values_m': singular.tolist(), 'threshold_m': threshold_m}


def square_hypothesis(points, edge_m, threshold_m=.002):
    if not np.isfinite(edge_m) or not .01 <= edge_m <= .10:
        raise ValueError('Explicit nominal edge 10..100mm required; not a caliper measurement')
    plane = fit_plane(points, threshold_m)
    if np.mean(plane['inliers']) < .6:
        raise ValueError('No dominant face: less than 60% measured plane support')
    uv = (points[plane['inliers']] - plane['origin']) @ plane['axes'].T
    rect = cv2.minAreaRect(uv.astype(np.float32))
    measured_sides = np.array(rect[1], dtype=float)
    if np.any(measured_sides < .8 * edge_m) or np.any(measured_sides > 1.2 * edge_m):
        raise ValueError('Measured face extent inconsistent with complete nominal square')
    hull = cv2.convexHull(uv.astype(np.float32)).reshape(-1, 2).astype(float)
    fill = cv2.contourArea(hull.astype(np.float32)) / np.prod(measured_sides)
    if fill < .7:
        raise ValueError('Incomplete face hull; no center extrapolation across missing support')
    angle = np.radians(rect[2])
    initial = np.r_[rect[0], angle]

    def boundary_residual(parameters):
        center, theta = parameters[:2], parameters[2]
        rotation = np.array([[np.cos(theta), -np.sin(theta)],
                             [np.sin(theta), np.cos(theta)]])
        local = (hull - center) @ rotation
        # Each hull vertex supports a measured square boundary, not a filled
        # interior pixel. Its signed distance to the nearest edge is explicit.
        return np.max(np.abs(local), axis=1) - edge_m / 2.

    bound_center = .2 * edge_m
    fitted = least_squares(boundary_residual, initial, loss='soft_l1', f_scale=.001,
        bounds=(initial - [bound_center, bound_center, np.radians(15)],
                initial + [bound_center, bound_center, np.radians(15)]),
        ftol=1e-11, xtol=1e-11, gtol=1e-11)
    square_residual = boundary_residual(fitted.x)
    boundary_rms = float(np.sqrt(np.mean(square_residual ** 2)))
    if not fitted.success or boundary_rms > .0025:
        raise ValueError('Nominal-square boundary fit not supported within 2.5mm')
    face_center = plane['origin'] + fitted.x[:2] @ plane['axes']
    center = np.array(cube_center_from_face(face_center, plane['normal'], edge_m))
    rotation = np.array([[np.cos(fitted.x[2]), -np.sin(fitted.x[2])],
                         [np.sin(fitted.x[2]), np.cos(fitted.x[2])]])
    corners_uv = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * edge_m / 2.
    corners = plane['origin'] + (corners_uv @ rotation.T + fitted.x[:2]) @ plane['axes']
    return {'method': 'measured dominant plane + nominal square hull fit + inward half-edge normal',
        'nominal_edge_m': edge_m, 'edge_is_not_confirmed_caliper_measurement': True,
        'face_center_depth_m': face_center.tolist(), 'cube_center_depth_m': center.tolist(),
        'outward_normal_depth': plane['normal'].tolist(), 'face_corners_depth_m': corners.tolist(),
        'plane_origin_depth_m': plane['origin'].tolist(),
        'measured_rectangle_center_depth_m': (plane['origin'] + np.array(rect[0]) @ plane['axes']).tolist(),
        'measured_face_sides_m': sorted(measured_sides.tolist()),
        'plane_inliers': int(plane['inliers'].sum()), 'plane_inlier_fraction': float(np.mean(plane['inliers'])),
        'plane_threshold_m': threshold_m, 'plane_rms_m': plane['rms_m'], 'plane_p95_m': plane['p95_m'],
        'square_boundary_rms_m': boundary_rms, 'face_hull_fill_ratio': float(fill),
        'absolute_center_verified': False,
        'assumptions': ['Selected dominant plane is one full physical cube face.',
            'Nominal edge is approximate; depth registration and boundary selection can be systematically biased.',
            'A high-support candidate is not an approved calibration pair.']}


def transform_hypothesis(hypothesis, camera):
    result = dict(hypothesis)
    r, t = camera['r'], camera['t']
    result['coordinate_frames'] = {'depth': 'camera_depth_optical_frame', 'color': 'camera_color_optical_frame'}
    result['cube_center_color_m'] = (r @ np.array(result['cube_center_depth_m']) + t).tolist()
    result['face_center_color_m'] = (r @ np.array(result['face_center_depth_m']) + t).tolist()
    result['outward_normal_color'] = (r @ np.array(result['outward_normal_depth'])).tolist()
    result['D_to_C_equation'] = 'p_C = R_DC * p_D + t_DC; factory transform, not robot mounting TF'
    result['C_to_D_roundtrip_error_m'] = float(np.linalg.norm(
        np.linalg.solve(r, np.array(result['cube_center_color_m']) - t) - result['cube_center_depth_m']))
    return result


def points_from_mask(depth, k, selected):
    y, x = np.where(selected & (depth > 0))
    z = depth[y, x].astype(float) * .001
    return np.column_stack(((x - k[0, 2]) * z / k[0, 0], (y - k[1, 2]) * z / k[1, 1], z))


def frame_hypotheses(row, params, camera, edges):
    review = frame_review(row, params, camera)  # verifies original SHA and native uint16
    rgb = cv2.imread(row['images']['rgb']['path'])
    depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
    info = review['depth_info']; k = np.array(info['k']).reshape(3, 3)
    selected, _, _, _ = selected_pixels(rgb, depth, info, params, camera)
    points = points_from_mask(depth, k, selected)
    result = {'snapshot': row['snapshot'], 'stamps_ns': review['stamps_ns'],
        'actual_q_rad': row['q_rad'], 'color_pixel_coverage': review['color_pixel_coverage'],
        'native_selected_points': len(points), 'rgb_bbox_xywh': review['rgb_bbox_xywh'],
        'depth_surface_median_m': review['surface_componentwise_median_xyz_m'],
        'candidate_by_nominal_edge_mm': {}, 'rejected_by_nominal_edge_mm': {},
        'raw_image_sha256': {name: item['sha256'] for name, item in row['images'].items()},
        'camera_center_verified': False}
    if result['color_pixel_coverage'] < .5 or len(points) < 100:
        result['rejected'] = 'Insufficient measured face coverage; edge/background samples do not define cube center'
        return result
    box = result['rgb_bbox_xywh']
    if box is None or min(box[:2]) <= 0 or box[0] + box[2] >= rgb.shape[1] or box[1] + box[3] >= rgb.shape[0]:
        result['rejected'] = 'Color target truncated; no complete-face center claim'
        return result
    for edge in edges:
        label = f'{edge * 1000:g}'
        try:
            result['candidate_by_nominal_edge_mm'][label] = transform_hypothesis(square_hypothesis(points, edge), camera)
        except ValueError as error:
            result['rejected_by_nominal_edge_mm'][label] = str(error)
    return result


def summary(frames, edge_mm, camera):
    candidates = [(r['snapshot'], r['candidate_by_nominal_edge_mm'].get(f'{edge_mm:g}')) for r in frames]
    candidates = [(i, c) for i, c in candidates if c is not None]
    if not candidates:
        return {'candidates': 0, 'camera_cube_center_depth_m': None, 'absolute_accuracy_verified': False}
    points = np.array([c['cube_center_depth_m'] for _, c in candidates])
    color = np.array([c['cube_center_color_m'] for _, c in candidates])
    depth_median = np.median(points, axis=0)
    return {'candidates': len(candidates), 'snapshots': [i for i, _ in candidates],
        'nominal_edge_mm': edge_mm, 'cube_center_depth_median_m': np.median(points, axis=0).tolist(),
        'cube_center_color_of_depth_median_m': (camera['r'] @ depth_median + camera['t']).tolist(),
        'independent_color_componentwise_median_m': np.median(color, axis=0).tolist(),
        'median_warning': 'Rotating componentwise medians is not the same as componentwise median after rotation; use the explicitly transformed D median as the same physical candidate.',
        'temporal_center_std_m': np.std(points, axis=0).tolist(),
        'temporal_center_min_max_m': [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
        'measured_face_sides_median_m': np.median([c['measured_face_sides_m'] for _, c in candidates], axis=0).tolist(),
        'plane_rms_median_m': float(np.median([c['plane_rms_m'] for _, c in candidates])),
        'minimum_twenty_high_support_met': len(candidates) >= 20,
        'absolute_accuracy_verified': False, 'formal_pair_fit_allowed': False}


def preview(rgb, row, camera, label):
    output = cv2.resize(rgb, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    hypothesis = row['candidate_by_nominal_edge_mm'].get(label)
    if hypothesis:
        points = np.array(hypothesis['face_corners_depth_m'] + [hypothesis['cube_center_depth_m']])
        transformed = points @ camera['r'].T + camera['t']
        uv = (transformed @ camera['k'].T)[:, :2] / transformed[:, 2, None]
        if camera['mirror']:
            uv[:, 0] = camera['size'][0] - 1 - uv[:, 0]
        uv *= [(rgb.shape[1] - 1) / (camera['size'][0] - 1), (rgb.shape[0] - 1) / (camera['size'][1] - 1)]
        pixels = np.rint(uv * 3).astype(int)
        cv2.polylines(output, [pixels[:4]], True, (0, 255, 255), 2)
        cv2.drawMarker(output, tuple(pixels[4]), (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
        text = 'YELLOW: nominal face / GREEN: inferred cube center (not contact truth)'
    else:
        text = 'REJECTED: missing native face support; no center inferred'
    cv2.putText(output, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1)
    return output


def review_bundle(bundle, output, edges_mm=(28., 29.)):
    if output.exists():
        raise FileExistsError('Refusing to overwrite prior evidence')
    if not edges_mm or not all(np.isfinite(v) and 10 <= v <= 100 for v in edges_mm):
        raise ValueError('Finite explicit nominal edge lengths required')
    manifest_path = bundle / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for asset in manifest['files']:
        path = bundle / asset['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('Original bundle SHA mismatch: ' + asset['path'])
    capture = bundle / 'pair01_observe_remeasure_20261014_rgbd'
    params = read_config(bundle / 'detector_config.yaml'); camera = calibration(params)
    rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line]
    frames = []
    for row in rows:
        for image in row['images'].values():
            image['path'] = str(capture / image['path'])
        frames.append(frame_hypotheses(row, params, camera, [edge * .001 for edge in edges_mm]))
    output.mkdir(parents=True, exist_ok=False)
    witnesses = []
    for group, condition in [('candidate', lambda r: bool(r['candidate_by_nominal_edge_mm'])),
                             ('rejected', lambda r: not r['candidate_by_nominal_edge_mm'])]:
        indices = [i for i, f in enumerate(frames) if condition(f)]
        if indices:
            i = indices[0]; name = f'{group}_snapshot_{frames[i]["snapshot"]:04d}.png'
            rgb = cv2.imread(rows[i]['images']['rgb']['path'])
            if not cv2.imwrite(str(output / name), preview(rgb, frames[i], camera, f'{edges_mm[-1]:g}')):
                raise RuntimeError('Diagnostic preview write failed')
            witnesses.append(name)
    factory = json.loads((bundle / 'calibration.json').read_text())
    result = {'offline_only': True, 'raw_modified': False, 'motion_commands_sent': False,
        'robot_mounting_tf_used': False, 'camera_serial': factory['serial'],
        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'source_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'factory_calibration_sha256': hashlib.sha256((bundle / 'calibration.json').read_bytes()).hexdigest(),
        'library_versions': {'numpy': np.__version__, 'opencv': cv2.__version__},
        'registration': 'Original production pinhole factory D->C, no distortion, endpoint resize',
        'center_reference': 'hypothesized geometric cube center from dominant measured face',
        'nominal_edge_assumptions_mm': list(edges_mm), 'summaries': {f'{e:g}': summary(frames, e, camera) for e in edges_mm},
        'frames': frames, 'previews': witnesses,
        'not_claude_source_reproduction': True, 'not_approved_for_calibration_or_tf_deployment': True,
        'limitations': ['No physical cube-center ground truth or caliper measurement in pair01.',
            'Eroded color support and missing face boundary can systematically shift a stable estimate.',
            'No source-image depth hole has been filled. The green marker is inference, not a measured interior point.',
            'Pair01 gripper was not closed; this camera-side hypothesis does not make it fit-ready.']}
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(output), 'summaries': result['summaries']}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--edge-mm', nargs='+', type=float, default=[28., 29.])
    args = parser.parse_args()
    review_bundle(args.bundle, args.output, args.edge_mm)


if __name__ == '__main__':
    main()
