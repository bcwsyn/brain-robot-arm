#!/usr/bin/env python3
"""Export an explicit CENTER snapshot from the EXISTING face-fit report.

Offline only: no camera/SDK/ROS init, controls, hole filling or TCP deployment.
A selected manual reference is an uncertainty-bearing P4 task candidate, not
a newly calibrated physical TCP. The held-out group is not used for fitting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
import yaml


def make_target(review, reference, pair, edge, base_tool_fk, color_mount):
    if pair == 'new_pair07':
        raise ValueError('The fixed held-out manual group is validation-only')
    choices = [r for r in reference['pairs'] if r['pair'] == pair]
    if len(choices) != 1:
        raise ValueError('Select exactly one recorded manual task reference; do not average TCPs')
    chosen = choices[0]
    local = np.asarray(chosen['implied_tool_center_m_under_NEW_X'], float)
    if local.shape != (3,) or not np.isfinite(local).all() or np.any(np.abs(local) > .25):
        raise ValueError('Invalid explicit local capture reference')
    if not np.isfinite(edge) or not .01 <= edge <= .05:
        raise ValueError('Explicit cube edge in 10..50mm required')
    centers, sources = [], []
    for row in review['frames']:
        candidate = row.get('candidate_by_nominal_edge_mm', {}).get(f'{edge*1000:g}')
        if candidate is None and row.get('good_top_frame'):
            candidate = row.get('top_candidate')
        if candidate is None:
            continue
        p = np.asarray(candidate['cube_center_color_m'], float)
        q = row['actual_q_rad']
        if p.shape != (3,) or not np.isfinite(p).all() or len(q) != 6:
            raise ValueError('Invalid original measured-face center/q')
        base = np.asarray(base_tool_fk(q)) @ color_mount @ np.r_[p, 1.]
        centers.append(base[:3])
        sources.append({'snapshot': row.get('snapshot'), 'actual_q_rad': q,
            'stamps_ns': row.get('stamps_ns', row.get('source_stamps_ns')),
            'cube_center_color_m': p.tolist(), 'cube_center_base_m': base[:3].tolist(),
            'raw_image_sha256': row.get('raw_image_sha256')})
    if not centers:
        raise ValueError('No measured-face center candidate; missing depth stays missing')
    points = np.asarray(centers)
    return {'schema': 'p4_cube_center_v1', 'target_kind': 'cube_center', 'frame_id': 'base_link',
        'center_base_m': np.median(points, axis=0).tolist(), 'cube_edge_m': float(edge),
        'grasp_center_tool_m': local.tolist(),
        'provenance': 'existing_measured_face_square_fit_inward_half_edge; STATIC_SNAPSHOT',
        'grasp_reference_provenance': f'single_manual_task_candidate:{pair}; NOT_CALIBRATED_TCP',
        'grasp_reference_source': chosen, 'grasp_reference_is_candidate': True,
        'source_frames': sources, 'temporal_center_peak_to_peak_m': np.ptp(points, axis=0).tolist(),
        'assumptions': [
            'A reliable full measured face and nominal cube size are required by the existing estimator.',
            'Snapshots are not live; do not use an old location as the current object position.',
            'Reference assumes camera mounting unchanged and absorbs FK/hand-eye/manual errors.',
            'This does not modify production TF/TCP or promise absolute accuracy.',
            'CENTER input: do NOT add the old surface insertion or half-edge again.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--manual-review', type=Path, required=True)
    parser.add_argument('--reference-pair', required=True)
    parser.add_argument('--handeye', type=Path, required=True)
    parser.add_argument('--edge-mm', type=float, default=29.)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tools-dir', type=Path,
        help='Existing read-only calibration/FK helpers; no ROS/device initialization')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite a prior snapshot')
    # Same installed physical model helper as the existing calibration export.
    choices = [args.tools_dir] if args.tools_dir else [
        Path(__file__).resolve().parents[1]/'test',
        Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')]
    tools = next((p for p in choices if p and (p/'export_calibration_bundle.py').is_file()), None)
    if tools is None:
        parser.error('Original calibration/FK helpers missing; specify --tools-dir')
    sys.path.insert(0, str(tools))
    from export_calibration_bundle import load_installed_model, base_tool_fk
    urdf, _ = load_installed_model()
    model = ET.fromstring(urdf)
    inputs = {name: json.loads(path.read_text()) for name, path in
              [('review', args.review), ('manual', args.manual_review), ('handeye', args.handeye)]}
    result = make_target(inputs['review'], inputs['manual'], args.reference_pair, args.edge_mm/1000,
        lambda q: base_tool_fk(model, q),
        np.array(inputs['handeye']['T_gripperBase_colorOptical_candidate']))
    result['source_SHA256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [args.review, args.manual_review, args.handeye]}
    result['model_URDF_SHA256'] = hashlib.sha256(urdf.encode()).hexdigest()
    with args.output.open('x') as stream:
        yaml.safe_dump(result, stream, allow_unicode=True, sort_keys=False)
    print(json.dumps({'output': str(args.output), 'center_base_m': result['center_base_m'],
                     'read_only_export_no_hardware': True}))


if __name__ == '__main__':
    main()
