#!/usr/bin/env python3
"""Isolated offline sensitivity audit; never replaces P0/P1 acceptance.

No ROS, CAN or device interfaces. Import unchanged repository geometry only.
Rectangles are manually selected from raw first RGB, fixed for all 28 frames.
Original images, parameters, reports and thresholds must remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np


REGIONS = {
    'pad_left': [142, 86, 166, 116],
    'pad_below': [155, 124, 199, 139],
    'white_desk_right': [218, 55, 235, 108],
}


def stats(values):
    a = np.asarray(values, float)
    return {'n': len(a), 'min': float(a.min()), 'median': float(np.median(a)),
            'max': float(a.max())} if len(a) else None


def rectangle(projected, bounds):
    x0, y0, x1, y1 = bounds
    return ((projected[..., 0] >= x0) & (projected[..., 0] < x1) &
            (projected[..., 1] >= y0) & (projected[..., 1] < y1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--original-quality', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to replace an existing audit')
    test_dir = args.repo / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
    sys.path.insert(0, str(test_dir))
    from export_calibration_bundle import verify_bundle, bundle_asset
    from review_depth_registration import read_config, calibration, color_mask
    from review_pair_sampling import selected_pixels
    from estimate_calibration_cube_center import fit_plane, points_from_mask, square_hypothesis
    from calibration_p0_quality import table_mask, top_hypothesis, normal_angle_deg

    manifest = json.loads((args.bundle / 'manifest.json').read_text())
    verify_bundle(args.bundle, manifest)
    original = json.loads(args.original_quality.read_text())
    baseline = {f['snapshot']: f for f in original['frames']}
    rows = [json.loads(s) for s in (args.bundle / 'batch_01/observer.jsonl').read_text().splitlines()]
    params = read_config(args.bundle / 'detector_config.yaml')
    camera = calibration(params)
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for row in rows:
        images = {k: bundle_asset(args.bundle / 'batch_01', v['path'])
                  for k, v in row['images'].items()}
        rgb = cv2.imread(str(images['rgb']))
        depth = cv2.imread(str(images['depth']), cv2.IMREAD_UNCHANGED)
        assert depth.dtype == np.uint16
        for k, path in images.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['images'][k]['sha256']
        info = row['latest']['/camera/depth/camera_info']
        k = np.asarray(info['k']).reshape(3, 3)
        selected, projected, _, contour = selected_pixels(rgb, depth, info, params, camera)
        mask, _ = color_mask(rgb, params)
        box = list(cv2.boundingRect(contour))
        valid = ((depth > 0) & (depth * .001 >= params['min_depth_m']) &
                 (depth * .001 <= params['max_depth_m']))
        annulus = table_mask(projected, valid, mask, box)
        cube = points_from_mask(depth, k, selected)
        raw_face = square_hypothesis(cube, .029)
        old = baseline[row['snapshot']]
        assert raw_face['plane_inliers'] == old['plane_inliers']
        result = {'snapshot': row['snapshot'], 'rgb_bbox_xywh': box,
                  'original_good_top_frame': old['good_top_frame'],
                  'original_plane_inliers': raw_face['plane_inliers'],
                  'original_cube_samples': len(cube), 'original_top_error': old['top_error'],
                  'regions': {}, 'erosion_zero_diagnostic': None}
        region_masks = {'original_annulus': annulus}
        region_masks.update({name: annulus & rectangle(projected, bounds)
                             for name, bounds in REGIONS.items()})
        for name, selected_table in region_masks.items():
            pts = points_from_mask(depth, k, selected_table)
            item = {'native_table_samples': len(pts)}
            try:
                plane = fit_plane(pts[::max(1, len(pts) // 4000)])
                distances = np.abs((pts - plane['origin']) @ plane['normal'])
                fraction = float(np.mean(distances <= .002))
                item.update(table_plane_support_fraction=fraction,
                            original_60percent_table_dominance_met=fraction >= .6,
                            normal_depth=plane['normal'].tolist(),
                            origin_depth_m=plane['origin'].tolist(),
                            original_face_height_m=float((np.asarray(raw_face['face_center_depth_m']) -
                                                         plane['origin']) @ plane['normal']),
                            normal_difference_from_original_face_deg=normal_angle_deg(
                                plane['normal'], raw_face['outward_normal_depth']))
                top, _ = top_hypothesis(cube, pts, camera)
                item.update(top_plane_inliers=top['plane_inliers'],
                            original_800_rule_would_be_met=top['plane_inliers'] >= 800,
                            candidate_center_C_m=top['cube_center_color_m'],
                            error=None)
            except ValueError as exc:
                item['error'] = str(exc)
            result['regions'][name] = item
        unmodified_depth_params = dict(params, depth_erode_px=0)
        unselected, _, _, _ = selected_pixels(rgb, depth, info, unmodified_depth_params, camera)
        unpts = points_from_mask(depth, k, unselected)
        item = {'native_samples': len(unpts), 'production_parameter_modified': False,
                'diagnostic_selection_only': True}
        try:
            face = square_hypothesis(unpts, .029)
            item.update(plane_inliers=face['plane_inliers'],
                        plane_rms_m=face['plane_rms_m'],
                        face_extent_m=face['measured_face_sides_m'],
                        center_shift_from_original_face_m=float(np.linalg.norm(
                            np.asarray(face['cube_center_depth_m']) - raw_face['cube_center_depth_m'])),
                        error=None)
        except ValueError as exc:
            item['error'] = str(exc)
        result['erosion_zero_diagnostic'] = item
        results.append(result)
        if row['snapshot'] == 1:
            witness = rgb.copy()
            for i, (name, bounds) in enumerate(REGIONS.items()):
                x0, y0, x1, y1 = bounds
                color = [(0, 255, 0), (0, 200, 255), (255, 120, 0)][i]
                cv2.rectangle(witness, (x0, y0), (x1 - 1, y1 - 1), color, 1)
                cv2.putText(witness, name, (max(0, x0 - 20), y1 + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, .24, color, 1)
            assert cv2.imwrite(str(args.output / 'fixed_regions_witness.png'), witness)
        print('reviewed', row['snapshot'], flush=True)
    assert len(results) == 28
    summary = {}
    for name in ['original_annulus', *REGIONS]:
        items = [r['regions'][name] for r in results]
        summary[name] = {
            'support_fraction': stats([v['table_plane_support_fraction'] for v in items
                                       if 'table_plane_support_fraction' in v]),
            'face_height_m': stats([v['original_face_height_m'] for v in items
                                    if 'original_face_height_m' in v]),
            'top_inliers': stats([v['top_plane_inliers'] for v in items if 'top_plane_inliers' in v]),
            'would_meet_original_800': sum(v.get('original_800_rule_would_be_met', False) for v in items),
            'errors': {s: sum(v.get('error') == s for v in items)
                       for s in sorted({v['error'] for v in items if v.get('error')})}}
    report = {'schema': 'piper_P1_fixed_region_sensitivity_v1',
              'offline_only': True, 'hardware_commands_sent': False,
              'raw_or_production_modified': False, 'replacement_qualification': False,
              'source_manifest_sha256': hashlib.sha256((args.bundle / 'manifest.json').read_bytes()).hexdigest(),
              'source_quality_sha256': hashlib.sha256(args.original_quality.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'manual_ROIs_fixed_before_numeric_results': REGIONS,
              'ROIs_scope': 'Intersection with original annulus, not whole-image segmentation; manually labelled from visible raw RGB, not measured physical surface identity',
              'original_frames': len(results), 'original_good_top_frames': 0,
              'original_plane_inliers': stats([r['original_plane_inliers'] for r in results]),
              'erosion0_plane_inliers': stats([r['erosion_zero_diagnostic']['plane_inliers'] for r in results
                                              if 'plane_inliers' in r['erosion_zero_diagnostic']]),
              'erosion0_center_shift_m': stats([r['erosion_zero_diagnostic']['center_shift_from_original_face_m'] for r in results
                                               if 'center_shift_from_original_face_m' in r['erosion_zero_diagnostic']]),
              'regions': summary, 'frames': results,
              'warning': 'Sensitivity only. No new point pair accepted, no change to 800/20 or plane gates; no production camera TF used.'}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    verify_bundle(args.bundle, manifest)
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}))


if __name__ == '__main__':
    main()
