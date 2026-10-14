#!/usr/bin/env python3
"""Offline pixel witnesses for all recorded high/low depth-support frames.

Uses unchanged production registration, never fills zeros or solves robot TF.
Generated previews are separate artifacts, not replacements of raw images.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from review_calibration_capture import frame_review
from review_depth_registration import calibration, color_mask, project_measured, read_config


def selected_pixels(rgb, depth, info, params, camera):
    mask, contour = color_mask(rgb, params)
    radius = int(params['depth_erode_px'])
    eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1,) * 2))
    _, projected, valid = project_measured(depth, np.array(info['k']).reshape(3, 3),
                                          camera, rgb.shape[1::-1], params)
    y, x = np.where(valid)
    keep = eroded[projected[y, x, 1], projected[y, x, 0]] > 0
    selected = np.zeros(depth.shape, bool)
    selected[y[keep], x[keep]] = True
    return selected, projected, eroded, contour


def bbox(mask):
    y, x = np.where(mask)
    return [int(x.min()), int(y.min()), int(x.max()), int(y.max())] if len(x) else None


def panel(rgb, depth, selected, projected, mask, witness):
    # Raw RGB is scaled with nearest neighbours; cyan is the eroded color mask,
    # red pixels are projections of actually selected native depth samples.
    overlay = rgb.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (255, 255, 0), 1)
    y, x = np.where(selected)
    overlay[projected[y, x, 1], projected[y, x, 0]] = (0, 0, 255)
    b = bbox(mask)
    if b is None:
        raise ValueError('No cube color mask for diagnostic preview')
    x0, y0, x1, y1 = b
    rgb_crop = overlay[max(0, y0 - 12):y1 + 13, max(0, x0 - 12):x1 + 13]
    # Common native depth ROI, determined from the high-support representative.
    dx0, dy0, dx1, dy1 = witness
    native = depth[dy0:dy1 + 1, dx0:dx1 + 1]
    measured = native > 0
    scaled = np.clip((native.astype(float) - 420.) / 60. * 255., 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    heat[~measured] = 0  # black means missing, no hole filling
    borders, _ = cv2.findContours(selected[dy0:dy1 + 1, dx0:dx1 + 1].astype(np.uint8),
                                  cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(heat, borders, -1, (255, 255, 255), 1)
    tiles = [cv2.resize(rgb, (320, 240), interpolation=cv2.INTER_NEAREST),
             cv2.resize(rgb_crop, (320, 240), interpolation=cv2.INTER_NEAREST),
             cv2.resize(heat, (320, 240), interpolation=cv2.INTER_NEAREST)]
    header = np.zeros((55, 960, 3), np.uint8)
    for index, label in enumerate(('Unchanged raw RGB', 'Color mask + measured D projections',
                                   'Native depth: black=0; white=selected')):
        cv2.putText(header, label, (index * 320 + 5, 21), cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 255, 255), 1)
    cv2.putText(header, 'Depth colormap fixed 420..480mm; shared native ROI; NOT cube-center calibration',
                (5, 45), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
    return np.vstack((header, np.hstack(tiles)))


def review(bundle, output):
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing audit')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    for item in manifest['files']:
        asset = bundle / item['path']
        if hashlib.sha256(asset.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Bundle hash mismatch: ' + item['path'])
    capture = bundle / 'pair01_observe_remeasure_20261014_rgbd'
    params = read_config(bundle / 'detector_config.yaml')
    camera = calibration(params)
    rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line]
    frames, arrays = [], []
    for row in rows:
        for image in row['images'].values():
            image['path'] = str(capture / image['path'])
        result = frame_review(row, params, camera)
        rgb = cv2.imread(row['images']['rgb']['path'])
        depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
        selected, projected, mask, _ = selected_pixels(rgb, depth, result['depth_info'], params, camera)
        result['selected_native_bbox_xyxy'] = bbox(selected)
        result['group'] = 'high' if result['color_pixel_coverage'] >= .5 else 'low'
        frames.append(result)
        arrays.append((rgb, depth, selected, projected, mask))
    high_ids = [i for i, frame in enumerate(frames) if frame['group'] == 'high']
    low_ids = [i for i, frame in enumerate(frames) if frame['group'] == 'low']
    if not high_ids or not low_ids:
        raise ValueError('Both support populations required for this audit')
    ref = high_ids[0]
    high_support = arrays[ref][2]
    x0, y0, x1, y1 = bbox(high_support)
    witness = [max(0, x0 - 8), max(0, y0 - 8), min(639, x1 + 8), min(399, y1 + 8)]
    for frame, (_, depth, selected, _, _) in zip(frames, arrays):
        measured = depth[high_support] > 0
        values = depth[high_support][measured]
        frame['same_high_frame_native_footprint'] = {
            'reference_snapshot': frames[ref]['snapshot'], 'pixel_count': int(high_support.sum()),
            'nonzero_count': int(measured.sum()), 'zero_fraction': float(1 - measured.mean()),
            'nonzero_median_mm': float(np.median(values)) if len(values) else None,
            'selected_intersection_pixels': int(np.count_nonzero(selected & high_support)),
            'comparison_roi_not_new_measurement_or_filled_depth': True}
        for asset in frame['images'].values():
            asset['path'] = str(Path(asset['path']).relative_to(bundle))
    groups = {}
    for name, ids in [('high', high_ids), ('low', low_ids)]:
        groups[name] = {'frames': len(ids), 'snapshots': [frames[i]['snapshot'] for i in ids],
            'median_surface_xyz_m': np.median([frames[i]['surface_componentwise_median_xyz_m'] for i in ids], axis=0).tolist(),
            'median_same_footprint_zero_fraction': float(np.median([
                frames[i]['same_high_frame_native_footprint']['zero_fraction'] for i in ids]))}
    separation = float(np.linalg.norm(np.array(groups['high']['median_surface_xyz_m']) -
                                      groups['low']['median_surface_xyz_m']))
    output.mkdir(parents=True, exist_ok=False)
    previews = []
    for index in (ref, low_ids[0]):
        name = f"{frames[index]['group']}_snapshot_{frames[index]['snapshot']:04d}.png"
        if not cv2.imwrite(str(output / name), panel(*arrays[index], witness)):
            raise RuntimeError('Failed diagnostic PNG write')
        previews.append(name)
    report = {'offline_only': True, 'synthetic': False, 'raw_modified': False,
        'production_configuration_changed': False, 'manifest_sha256': hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest(),
        'registration': 'Unchanged production pinhole D->C; no inverse/distortion candidate chosen by sample count',
        'groups': groups, 'group_surface_separation_m': separation,
        'shared_native_preview_roi_xyxy': witness, 'previews': previews,
        'conclusion_limits': ['The same native footprint can directly reveal depth holes independently of robot TF.',
            'Different selected sample locations/surface depths are not independent random repeats of one cube center.',
            'No evidence here uniquely identifies sensor processing, occlusion, frame phase or registration as root cause.',
            'Neither high coverage nor a surface median establishes geometric cube center. Pair01 remains trial only.'],
        'frames': frames}
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'groups': groups, 'separation_mm': separation * 1000., 'output': str(output)}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.bundle, args.output)


if __name__ == '__main__':
    main()
