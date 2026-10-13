#!/usr/bin/env python3
"""Offline numeric audit of recorded RGB/depth association; no ROS imports.

Reads collect_static_rgbd.py evidence and existing detector parameters. Alternate
transform directions and distortion orders are labeled hypotheses, never motion
targets. A greater sample count does not establish the correct transform.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import yaml


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_config(path):
    document = yaml.safe_load(path.read_text())
    return document['cube_detector']['ros__parameters']


def calibration(parameters):
    p = parameters
    return dict(k=np.array([[p['color_fx'], 0, p['color_cx']],
                            [0, p['color_fy'], p['color_cy']], [0, 0, 1.0]]),
                r=np.array(p['depth_to_color_rotation']).reshape(3, 3),
                t=np.array(p['depth_to_color_translation_m']),
                size=(int(p['color_calibration_width']), int(p['color_calibration_height'])),
                mirror=bool(p['color_mirror_horizontal']))


def color_mask(rgb, p):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (p['hue_low_1'], p['saturation_min'], p['value_min']),
                       (p['hue_high_1'], 255, 255))
    if p['hue_high_2'] > p['hue_low_2']:
        mask |= cv2.inRange(hsv, (p['hue_low_2'], p['saturation_min'], p['value_min']),
                            (p['hue_high_2'], 255, 255))
    n = int(p['morphology_kernel'])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    selected, largest = None, 0.0
    for contour in contours:
        if len(contour) < 3:
            continue
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        circularity = 4 * np.pi * area / perimeter ** 2 if perimeter > 1e-6 else 0
        _, _, w, h = cv2.boundingRect(contour)
        if p['shape_use_rotated_rectangle']:
            w, h = cv2.minAreaRect(contour)[1]
        rectangularity = area / (w * h) if w * h > 0 else 0
        aspect = max(w, h) / max(1, min(w, h))
        if (area >= p['min_area_px'] and (p['max_area_px'] <= 0 or area <= p['max_area_px'])
                and circularity >= p['min_circularity']
                and rectangularity >= p['min_rectangularity']
                and aspect >= p['min_aspect_ratio']
                and (p['max_aspect_ratio'] <= 0 or aspect <= p['max_aspect_ratio'])
                and area > largest):
            selected, largest = contour, area
    mask[:] = 0
    if selected is not None:
        cv2.drawContours(mask, [selected], 0, 255, cv2.FILLED)
    return mask, selected


def project_measured(depth, kd, c, rgb_size, p, distortion=None):
    y, x = np.mgrid[:depth.shape[0], :depth.shape[1]]
    z = depth * .001
    xyz = np.stack([(x - kd[0, 2]) * z / kd[0, 0],
                    (y - kd[1, 2]) * z / kd[1, 1], z], axis=-1)
    color = xyz @ c['r'].T + c['t']
    if distortion is None:
        with np.errstate(divide='ignore', invalid='ignore'):
            uv = (color @ c['k'].T)[..., :2] / color[..., 2, None]
    else:
        uv, _ = cv2.projectPoints(color.reshape(-1, 3), np.zeros(3), np.zeros(3),
                                   c['k'], distortion)
        uv = uv.reshape(*depth.shape, 2)
    if c['mirror']:
        uv[..., 0] = c['size'][0] - 1 - uv[..., 0]
    uv *= np.array([(rgb_size[0] - 1) / (c['size'][0] - 1),
                    (rgb_size[1] - 1) / (c['size'][1] - 1)])
    finite = np.isfinite(uv).all(axis=-1)
    safe_uv = np.where(np.isfinite(uv), uv, -1e6)
    # Match std::lround, including negative half-integers.
    pixel = np.copysign(np.floor(np.abs(safe_uv) + .5), safe_uv).astype(np.int64)
    valid = (finite & (z >= p['min_depth_m']) & (z <= p['max_depth_m'])
             & (color[..., 2] > .001) & (pixel[..., 0] >= 0)
             & (pixel[..., 0] < rgb_size[0]) & (pixel[..., 1] >= 0)
             & (pixel[..., 1] < rgb_size[1]))
    return uv, pixel, valid


def sample_summary(mask, depth):
    y, x = np.where(mask)
    values = depth[mask]
    median = float(np.partition(values, len(values) // 2)[len(values) // 2]) if len(values) else None
    return dict(count=len(values), bbox_xyxy=[int(x.min()), int(y.min()), int(x.max()), int(y.max())]
                if len(values) else None, median_mm=median,
                range_mm=[int(values.min()), int(values.max())] if len(values) else None)


def ray_scan(mask, depth, kd, c, depths):
    y, x = np.where(mask > 0)
    if not len(x):
        return [], []
    full_x = x * (c['size'][0] - 1) / (mask.shape[1] - 1)
    if c['mirror']:
        full_x = c['size'][0] - 1 - full_x
    rays = np.stack([full_x, y * (c['size'][1] - 1) / (mask.shape[0] - 1), np.ones(len(x))], axis=-1)
    rays = rays @ np.linalg.inv(c['k']).T @ np.linalg.inv(c['r']).T
    offset = -np.linalg.inv(c['r']) @ c['t']
    results, outlines = [], []
    for depth_z in depths:
        color_z = (depth_z - offset[2]) / rays[:, 2]
        xyz = rays * color_z[:, None] + offset
        uv = (xyz @ kd.T)[:, :2] / xyz[:, 2, None]
        pixel = np.copysign(np.floor(np.abs(uv) + .5), uv).astype(np.int64)
        inside = ((pixel[:, 0] >= 0) & (pixel[:, 0] < depth.shape[1])
                  & (pixel[:, 1] >= 0) & (pixel[:, 1] < depth.shape[0]))
        samples = depth[pixel[inside, 1], pixel[inside, 0]]
        nonzero = samples[samples > 0]
        results.append(dict(assumed_depth_z_m=depth_z, assumption_not_measurement=True,
                            depth_bbox_xyxy=[float(uv[:, 0].min()), float(uv[:, 1].min()),
                                             float(uv[:, 0].max()), float(uv[:, 1].max())],
                            rgb_mask_pixel_count=len(x), in_depth_fov_count=int(inside.sum()),
                            in_depth_fov_fraction=float(inside.mean()),
                            in_fov_nonzero_sample_count=len(nonzero),
                            nonzero_median_mm=float(np.median(nonzero)) if len(nonzero) else None,
                            nonzero_range_mm=[int(nonzero.min()), int(nonzero.max())] if len(nonzero) else None))
        outlines.append((depth_z, cv2.convexHull(uv.astype(np.float32)).reshape(-1, 2)))
    return results, outlines


def make_heatmap(path, depth, outlines, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    values = depth[depth > 0]
    if not len(values):
        return
    colormap = plt.get_cmap('viridis').copy()
    colormap.set_bad('black')
    for axis in axes:
        image = axis.imshow(np.ma.masked_equal(depth, 0), cmap=colormap,
                            vmin=float(values.min()), vmax=float(values.max()),
                            interpolation='nearest', origin='upper')
        axis.set_xlabel('Native depth u [pixels]')
        axis.set_ylabel('Native depth v [pixels]')
    axes[0].set_title('Measured 16UC1 depth; black = zero')
    for z, outline in outlines:
        closed = np.vstack([outline, outline[0]])
        axes[1].plot(closed[:, 0], closed[:, 1], label=f'Assumed Z = {z:.3f} m')
    axes[1].axhline(depth.shape[0] - 1, color='red', linestyle='--', label='Last depth row')
    axes[1].set_title('Current forward-R/T RGB ray hypotheses')
    axes[1].legend(fontsize=6)
    fig.colorbar(image, ax=axes.tolist(), label='Raw depth [mm]', shrink=.8)
    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--old-config', type=Path)
    parser.add_argument('--factory-evidence', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path, help='New directory; never overwrite evidence')
    parser.add_argument('--depth-z-m', nargs='+', type=float, default=[.10, .15, .156, .186, .20, .25, .30, .40])
    parser.add_argument('--heatmap', action='store_true')
    args = parser.parse_args()
    if any(not np.isfinite(z) or z <= 0 for z in args.depth_z_m):
        parser.error('assumed depth Z values must be finite and positive')
    p = read_config(args.config)
    current = calibration(p)
    factory = json.loads(args.factory_evidence.read_text())
    distortion = np.array(factory['get_camera_params_color_distortion'], dtype=float)
    if distortion.shape != (5,):
        parser.error('expected five factory color distortion coefficients')
    inverse = dict(current, r=np.linalg.inv(current['r']),
                   t=-np.linalg.inv(current['r']) @ current['t'])
    modes = [('current', current, None, 'existing production forward-R/T convention'),
             ('factory_distortion_order_hypothesis', current, distortion, 'k1,k2,p1,p2,k3 hypothesis'),
             ('driver_reordered_distortion_hypothesis', current, distortion[[0, 1, 3, 4, 2]], 'reorder 0,1,3,4,2 hypothesis'),
             ('inverse_transform_hypothesis', inverse, None, 'inverse R/T hypothesis; not selected by sample count')]
    if args.old_config:
        modes.insert(0, ('old', calibration(read_config(args.old_config)), None, 'prior configuration'))
    rows_path = args.capture / 'observer.jsonl'
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    if not rows:
        parser.error('capture has no frames')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = dict(offline_only=True, motion_sent=False, input_capture=str(args.capture.resolve()),
                  input_observer_sha256=sha256(rows_path), config_sha256=sha256(args.config),
                  factory_evidence_sha256=sha256(args.factory_evidence),
                  old_config_sha256=sha256(args.old_config) if args.old_config else None,
                  factory_serial=factory.get('serial'),
                  factory_camera_info_distortion=factory.get('get_camera_info_distortion'),
                  hypothesis_warning='Counts do not prove transform direction, physical occluder identity or grasp position.',
                  comparison_scope='Original RGB shape/morphology and depth erosion match detector configuration; no temporal grasp-valid simulation.',
                  distortion_coefficients={'factory_order':distortion.tolist(),
                                           'driver_reordered':distortion[[0, 1, 3, 4, 2]].tolist()}, frames=[])
    erosion = int(p['depth_erode_px'])
    eroder = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erosion + 1, 2 * erosion + 1))
    for index, row in enumerate(rows):
        for entry in row['images'].values():
            if sha256(entry['path']) != entry['sha256']:
                raise ValueError(f"Image SHA mismatch: {entry['path']}")
        rgb = cv2.imread(row['images']['rgb']['path'], cv2.IMREAD_COLOR)
        depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
        if rgb is None or depth is None or depth.dtype != np.uint16 or depth.ndim != 2:
            raise ValueError('Expected RGB image and unmodified 16UC1 depth')
        info = row['latest']['/camera/depth/camera_info']
        if list(depth.shape[::-1]) != info['size']:
            raise ValueError('Depth image size differs from saved CameraInfo')
        kd = np.array(info['k']).reshape(3, 3)
        mask, contour = color_mask(rgb, p)
        frame = dict(snapshot=row['snapshot'], stamps_ns=row['stamps_ns'], images=row['images'],
                     stamp_span_s=row['stamp_span_s'], q_rad=row['q_rad'],
                     rgb_bbox=list(cv2.boundingRect(contour)) if contour is not None else None,
                     depth_size=list(depth.shape[::-1]), depth_nonzero=int(np.count_nonzero(depth)),
                     depth_range_mm=[int(depth[depth > 0].min()), int(depth.max())] if np.any(depth) else None,
                     modes={})
        reference_uv = None
        for name, cal, dist, interpretation in modes:
            uv, pixel, valid = project_measured(depth, kd, cal, rgb.shape[1::-1], p, dist)
            selected = np.zeros(depth.shape, np.uint8)
            selected[valid] = mask[pixel[..., 1][valid], pixel[..., 0][valid]]
            eroded = cv2.erode(selected, eroder) if erosion else selected
            frame['modes'][name] = dict(interpretation=interpretation,
                                        before_erosion=sample_summary(selected > 0, depth),
                                        after_erosion=sample_summary(eroded > 0, depth))
            if name == 'current':
                reference_uv = uv
            if dist is not None and contour is not None:
                x, y, w, h = cv2.boundingRect(contour)
                near = (valid & (reference_uv[..., 0] >= x - 15) & (reference_uv[..., 0] <= x + w + 15)
                        & (reference_uv[..., 1] >= y - 15) & (reference_uv[..., 1] <= y + h + 15))
                shift = np.linalg.norm(uv - reference_uv, axis=-1)[near]
                frame['modes'][name]['shift_near_target_rgb_px'] = dict(
                    count=len(shift), min=float(shift.min()) if len(shift) else None,
                    median=float(np.median(shift)) if len(shift) else None,
                    max=float(shift.max()) if len(shift) else None)
        frame['ray_depth_hypotheses'], outlines = ray_scan(mask, depth, kd, current, args.depth_z_m)
        report['frames'].append(frame)
        if args.heatmap and index == len(rows) // 2:
            heatmap = args.output_dir / 'depth_numeric_heatmap.png'
            make_heatmap(heatmap, depth, outlines, f'{args.capture.name}: original depth frame {row["snapshot"]}')
            if heatmap.exists():
                report['heatmap'] = dict(path=str(heatmap.resolve()), sha256=sha256(heatmap),
                                         description='Scientific plot of original depth numbers; no edited RGB image')
    report_path = args.output_dir / 'report.json'
    with report_path.open('x') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps(dict(report=str(report_path.resolve()), frames=len(rows),
                          counts_after_erosion={name:[frame['modes'][name]['after_erosion']['count']
                                                      for frame in report['frames']]
                                                for name, *_ in modes}), allow_nan=False))


if __name__ == '__main__':
    main()
