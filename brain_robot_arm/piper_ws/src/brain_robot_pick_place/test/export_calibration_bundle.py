#!/usr/bin/env python3
"""Export explicitly requested small raw calibration assets; no device access.

Only PNG/JSON/JSONL and the exact detector configuration are copied. Generated
URDF, vendor packages, arbitrary logs and secrets are not included.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import numpy as np
import yaml


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--capture', required=True, nargs='+', type=Path)
    ap.add_argument('--legacy', required=True, type=Path)
    ap.add_argument('--manual', required=True, type=Path)
    ap.add_argument('--sdk', required=True, type=Path)
    ap.add_argument('--pair', required=True, type=Path)
    ap.add_argument('--camera-metadata', required=True, type=Path)
    ap.add_argument('--review', required=True, type=Path)
    ap.add_argument('--detector-config', required=True, type=Path)
    ap.add_argument('--cube-edge-mm', required=True, type=float)
    a = ap.parse_args()
    if not np.isfinite(a.cube_edge_mm) or a.cube_edge_mm <= 0:
        ap.error('Positive measured approximate cube edge required')
    a.output.mkdir(parents=True, exist_ok=False)
    assets, source_map = [], {}

    def copy(source, relative):
        if source.is_symlink() or source.suffix not in ('.png', '.json', '.jsonl', '.yaml'):
            raise ValueError('Unexpected or linked raw asset: ' + str(source))
        size = source.stat().st_size
        if size > 2 * 1024 * 1024 or sum(v['bytes'] for v in assets) + size > 32 * 1024 * 1024:
            raise ValueError('Explicit raw asset export budget exceeded')
        target = a.output / relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        entry = {'path': relative, 'bytes': size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
        assets.append(entry); source_map[str(source)] = relative
        return entry

    for label, folder in [('original_observe', a.legacy), ('manual_grasp', a.manual)]:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.png', '.json', '.jsonl'):
                copy(p, label + '/' + p.name)
    copy(a.sdk, 'manual_grasp/sdk_samples.json')
    copy(a.pair, 'original_pair01.json')
    copy(a.camera_metadata, 'camera_factory_current.json')
    copy(a.detector_config, 'detector_config.yaml')
    for capture in a.capture:
        label = capture.name
        for p in sorted((capture / 'evidence').glob('*.png')):
            copy(p, label + '/evidence/' + p.name)
        copy(capture / 'summary.json', label + '/summary.json')
        rows = [json.loads(line) for line in (capture / 'observer.jsonl').read_text().splitlines() if line]
        for row in rows:
            row['stamps_ns'] = {k: str(v) for k, v in row['stamps_ns'].items()}
            for image in row['images'].values():
                image['path'] = 'evidence/' + Path(image['path']).name
        target = a.output / label / 'observer.jsonl'
        target.write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in rows))

    report = json.loads(a.review.read_text())
    report['captures'] = [p.name for p in a.capture]
    for frame in report['frames']:
        for image in frame['images'].values():
            image['path'] = source_map[image['path']]

    # Generate exactly the installed model for FK; export matrices and hash,
    # never the generated URDF or another robot model.
    from ament_index_python.packages import get_package_share_directory
    from moveit_configs_utils import MoveItConfigsBuilder
    from review_jaw_scene import poses
    share = Path(get_package_share_directory('brain_robot_ball_pick'))
    task_path = share / 'config/cube_task_real.yaml'
    task = yaml.safe_load(task_path.read_text())
    spec = importlib.util.spec_from_file_location('actual_visual_launch', share / 'launch/cube_visual_search.launch.py')
    launch = importlib.util.module_from_spec(spec); spec.loader.exec_module(launch)
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').to_moveit_configs()
    urdf = launch._physical_gripper_description(model.robot_description['robot_description'],
        joint5_upper=task['grasp_lift_executor']['ros__parameters']['real_trajectory_joint_max'][4])
    root = ET.fromstring(urdf)
    for frame in report['frames']:
        q = {f'joint{i+1}': value for i, value in enumerate(frame['actual_q_rad'])}
        q.update(joint7=.05, joint8=-.05)
        links = poses(root, q)
        frame['T_base_tool'] = (np.linalg.inv(links['base_link']) @ links['gripper_base']).tolist()
    report['urdf_sha256'] = hashlib.sha256(urdf.encode()).hexdigest()
    report['task_sha256'] = hashlib.sha256(task_path.read_bytes()).hexdigest()
    report['common_reference'].update({'cube_edge_m': a.cube_edge_mm / 1000,
        'cube_edge_is_approximate_user_measurement': True,
        'camera_cube_center_m': None, 'gripper_base_cube_center_m': None,
        'reason_pending': 'No identified face center/normal or verified physical jaw-centered offset; no fabricated center used.'})
    dump(a.output / 'depth_review.json', report)
    metadata = json.loads(a.camera_metadata.read_text())
    params = metadata['get_camera_params']; raw_d = params['r_k']
    depth_k = report['frames'][0]['depth_info']['k']
    dump(a.output / 'calibration.json', {
        'serial': metadata['get_device_info']['info']['serial_number'],
        'depth': {'size': [640, 400], 'K': depth_k, 'D_factory': params['l_k'],
                  'units': 'millimetres', 'encoding': '16UC1'},
        'color_factory': {'size': [640, 480], 'K': metadata['get_camera_info']['info']['k'],
                          'CameraInfo_D': metadata['get_camera_info']['info']['d'],
                          'raw_factory_D': raw_d,
                          'D_reordered_by_installed_driver': [raw_d[i] for i in (0, 1, 3, 4, 2)]},
        'color_capture': {'size': [320, 240],
            'existing_detector_resize_factors': [319/639, 239/479],
            'distortion_in_existing_detector': 'disabled; raw and driver-reordered coefficients preserved for independent replay'},
        'depth_to_color': {'source_frame': 'camera_depth_optical_frame',
            'target_frame': 'camera_color_optical_frame', 'equation': 'p_color = R * p_depth + t',
            'R_row_major': params['r2l_r'], 't_m': [v*.001 for v in params['r2l_t']],
            't_raw_mm': params['r2l_t'],
            'direction_source': 'Unchanged configured D->C convention corroborated by archived factory extrinsic query; raw field names retained.'},
        'not_robot_camera_mount_calibration': True})
    # All portable files, including generated summaries, get final hashes.
    files = [{'path': str(p.relative_to(a.output)), 'bytes': p.stat().st_size,
              'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(a.output.rglob('*')) if p.is_file()]
    manifest = {'sample_id': 'pair01_20261014', 'portable_relative_paths': True,
        'raw_images_are_not_modified': True, 'raw_sdk_samples': 'manual_grasp/sdk_samples.json',
        'original_pair': 'original_pair01.json', 'review': 'depth_review.json', 'calibration': 'calibration.json',
        'cube_edge_mm_approximate': a.cube_edge_mm, 'geometric_center_reference_confirmed': False,
        'calibration_fit_performed': False, 'files': files,
        'file_count': len(files), 'total_bytes': sum(f['bytes'] for f in files),
        'absolute_accuracy_below_10mm_verified': False}
    dump(a.output / 'manifest.json', manifest)
    print(json.dumps({'files': len(files), 'bytes': manifest['total_bytes'],
                     'high_support': report['high_support_temporal'], 'common_reference_confirmed': False}))


if __name__ == '__main__':
    main()
