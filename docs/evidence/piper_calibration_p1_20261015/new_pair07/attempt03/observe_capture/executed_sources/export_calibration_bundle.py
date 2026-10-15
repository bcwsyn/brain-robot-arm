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
import re
import shutil
import xml.etree.ElementTree as ET

import numpy as np
import yaml


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def bundle_asset(bundle, relative):
    """Resolve only portable, non-linked assets within this evidence bundle."""
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('Non-portable bundle path: ' + str(relative))
    path = bundle / relative
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != bundle.parent):
        raise ValueError('Linked bundle asset: ' + str(relative))
    if not path.resolve().is_relative_to(bundle.resolve()):
        raise ValueError('Asset escapes bundle: ' + str(relative))
    return path


def verify_bundle(bundle, manifest):
    for asset in manifest['files']:
        path = bundle_asset(bundle, asset['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('Bundle SHA mismatch: ' + asset['path'])


def observation_capture(bundle, manifest, explicit=None):
    """Use declared capture or the single hashed observer, not a pair01 name."""
    candidates = [str(Path(f['path']).parent) for f in manifest['files']
                  if Path(f['path']).name == 'observer.jsonl']
    selected = explicit or manifest.get('observation_capture')
    if selected is None:
        if len(candidates) != 1:
            raise ValueError('Select one observation capture explicitly; do not mix poses')
        selected = candidates[0]
    if str(selected) not in candidates:
        raise ValueError('Observation capture must be listed in the hashed manifest')
    return bundle_asset(bundle, selected)


def load_installed_model():
    # Build the exact installed description without starting any ROS node.
    from ament_index_python.packages import get_package_share_directory
    from moveit_configs_utils import MoveItConfigsBuilder
    share = Path(get_package_share_directory('brain_robot_ball_pick'))
    task_path = share / 'config/cube_task_real.yaml'
    task = yaml.safe_load(task_path.read_text())
    spec = importlib.util.spec_from_file_location('actual_visual_launch', share / 'launch/cube_visual_search.launch.py')
    launch = importlib.util.module_from_spec(spec); spec.loader.exec_module(launch)
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').to_moveit_configs()
    urdf = launch._physical_gripper_description(model.robot_description['robot_description'],
        joint5_upper=task['grasp_lift_executor']['ros__parameters']['real_trajectory_joint_max'][4])
    return urdf, task_path


def base_tool_fk(root, values):
    from review_jaw_scene import poses
    if len(values) != 6 or not np.isfinite(values).all():
        raise ValueError('Six finite actual joint values required')
    q = {f'joint{i+1}': value for i, value in enumerate(values)}
    q.update(joint7=.05, joint8=-.05)
    links = poses(root, q)
    return (np.linalg.inv(links['base_link']) @ links['gripper_base']).tolist()


def sdk_review(packet, root):
    """Keep the source untouched; never turn stale SDK defaults into actual FK."""
    current = 'quality' in packet
    samples = []
    for row in packet['samples']:
        fresh = row.get('fresh_after_passive_connection') is True if current else None
        q = [v / 1000. * .017444 for v in row['q_mdeg']]
        if fresh:
            stamps = row['sdk_receipt_stamps']
            fresh = (all(0 < float(stamps[k]) <= row['epoch'] and
                         row['epoch'] - float(stamps[k]) <= .5
                         for k in ('joint', 'high', 'low', 'gripper')) and row['high_hz'] > 0)
            if fresh and row.get('q_driver_rad') != q:
                raise ValueError('SDK rad values differ from the deployed driver conversion')
        samples.append({'epoch': row['epoch'], 'feedback_fresh': fresh,
            'q_driver_rad': q if fresh else None,
            'T_base_tool': base_tool_fk(root, q) if fresh else None})
    return {'source_schema': 'current_passive_capture' if current else 'legacy_receipt_capture',
        'quality': packet.get('quality'), 'samples': samples,
        'legacy_all_stream_freshness_verified': False,
        'physical_contact_verified': False, 'gripper_base_cube_center_m': None,
        'warning': 'Legacy raw values are retained but not promoted to fully fresh feedback. FK is a tool reference, not a verified cube center.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--capture', required=True, nargs='+', type=Path)
    ap.add_argument('--sample-id', help='Explicit new group or stationary dry-run identifier')
    ap.add_argument('--observation-capture', help='Name of one --capture used for center analysis')
    ap.add_argument('--legacy', type=Path)
    ap.add_argument('--manual', type=Path)
    ap.add_argument('--sdk', required=True, type=Path)
    ap.add_argument('--pair', type=Path, help='Optional original physical-pair record; absent for dry-run')
    ap.add_argument('--camera-metadata', required=True, type=Path)
    ap.add_argument('--review', required=True, type=Path)
    ap.add_argument('--detector-config', required=True, type=Path)
    ap.add_argument('--cube-edge-mm', required=True, type=float)
    a = ap.parse_args()
    export_bundle(a)


def export_bundle(a):
    if not np.isfinite(a.cube_edge_mm) or a.cube_edge_mm <= 0:
        raise ValueError('Positive approximate cube edge required')
    sample_id = a.sample_id or ('pair01_20261014' if a.legacy else None)
    if not sample_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', sample_id):
        raise ValueError('Explicit portable sample identifier required for new captures')
    labels = [p.name for p in a.capture]
    if not labels or len(set(labels)) != len(labels) or any(
            label in ('original_observe', 'manual_grasp') for label in labels):
        raise ValueError('Unique non-reserved capture directory names required')
    selected = a.observation_capture or (labels[0] if len(labels) == 1 else None)
    if selected not in labels:
        raise ValueError('Select one --observation-capture when exporting multiple captures')
    a.output.mkdir(parents=True, exist_ok=False)
    assets, source_map, capture_rows = [], {}, {}

    def copy(source, relative):
        if source.is_symlink() or source.suffix not in ('.png', '.json', '.jsonl', '.yaml'):
            raise ValueError('Unexpected or linked raw asset: ' + str(source))
        size = source.stat().st_size
        if size > 2 * 1024 * 1024 or sum(v['bytes'] for v in assets) + size > 32 * 1024 * 1024:
            raise ValueError('Explicit raw asset export budget exceeded')
        target = bundle_asset(a.output, relative); target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError('Refusing duplicate export target: ' + relative)
        shutil.copyfile(source, target)
        entry = {'path': relative, 'bytes': size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
        assets.append(entry); source_map[str(source)] = relative
        return entry

    for label, folder in [('original_observe', a.legacy), ('manual_grasp', a.manual)]:
        if folder is None:
            continue
        for p in sorted(folder.iterdir()):
            if p != a.sdk and p.is_file() and p.suffix in ('.png', '.json', '.jsonl'):
                copy(p, label + '/' + p.name)
    sdk_path = 'manual_grasp/sdk_samples.json' if a.manual else 'sdk_samples.json'
    copy(a.sdk, sdk_path)
    pair_path = ('original_pair01.json' if a.legacy else 'pair_record.json') if a.pair else None
    if pair_path:
        copy(a.pair, pair_path)
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
                source = Path(image['path'])
                if not source.is_absolute():
                    source = capture / source
                copied = source_map[str(source)]
                if not copied.startswith(label + '/') or image['sha256'] != next(
                        asset['sha256'] for asset in assets if asset['path'] == copied):
                    raise ValueError('Capture image does not match its copied raw evidence')
                image['path'] = 'evidence/' + Path(image['path']).name
        if not rows:
            raise ValueError('No paired observations in capture: ' + label)
        capture_rows[label] = rows
        target = a.output / label / 'observer.jsonl'
        target.write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in rows))

    report = json.loads(a.review.read_text())
    report['captures'] = [p.name for p in a.capture]
    for frame in report['frames']:
        for image in frame['images'].values():
            image['path'] = source_map[image['path']]

    # Generate exactly the installed model for FK; export matrices and hash,
    # never the generated URDF or another robot model.
    urdf, task_path = load_installed_model()
    root = ET.fromstring(urdf)
    for frame in report['frames']:
        frame['T_base_tool'] = base_tool_fk(root, frame['actual_q_rad'])
    report['urdf_sha256'] = hashlib.sha256(urdf.encode()).hexdigest()
    report['task_sha256'] = hashlib.sha256(task_path.read_bytes()).hexdigest()
    # Colcon symlink-install is expected for this explicitly loaded config;
    # resolve only this known model input, not arbitrary raw image/SDK assets.
    copy(task_path.resolve(strict=True), 'robot_task_config_snapshot.yaml')
    report['common_reference'].update({'cube_edge_m': a.cube_edge_mm / 1000,
        'cube_edge_is_approximate_user_measurement': True,
        'camera_cube_center_m': None, 'gripper_base_cube_center_m': None,
        'reason_pending': 'No identified face center/normal or verified physical jaw-centered offset; no fabricated center used.'})
    dump(a.output / 'depth_review.json', report)
    dump(a.output / 'sdk_review.json', sdk_review(json.loads(a.sdk.read_text()), root))
    metadata = json.loads(a.camera_metadata.read_text())
    params = metadata['get_camera_params']; raw_d = params['r_k']
    selected_row = capture_rows[selected][0]
    depth_info = selected_row['latest']['/camera/depth/camera_info']
    depth_k = depth_info['k']
    # Older rows did not store image dimensions; measure the original PNG,
    # never guess 320x240 or rewrite its bytes to match a template.
    import cv2
    color = cv2.imread(str(a.output / selected / selected_row['images']['rgb']['path']))
    if color is None:
        raise ValueError('Cannot read original RGB dimensions')
    color_size = list(color.shape[1::-1])
    declared_size = selected_row['images']['rgb'].get('size')
    if declared_size is not None and declared_size != color_size:
        raise ValueError('RGB size metadata does not match the original image')
    factory_info = metadata['get_camera_info']['info']
    factory_size = [factory_info['width'], factory_info['height']]
    dump(a.output / 'calibration.json', {
        'serial': metadata['get_device_info']['info']['serial_number'],
        'depth': {'size': depth_info['size'], 'K': depth_k, 'D_factory': params['l_k'],
                  'units': 'millimetres', 'encoding': '16UC1'},
        'color_factory': {'size': factory_size, 'K': metadata['get_camera_info']['info']['k'],
                          'CameraInfo_D': metadata['get_camera_info']['info']['d'],
                          'raw_factory_D': raw_d,
                          'D_reordered_by_installed_driver': [raw_d[i] for i in (0, 1, 3, 4, 2)]},
        'color_capture': {'size': color_size,
            'existing_detector_resize_factors': [(v - 1) / (f - 1) for v, f in zip(color_size, factory_size)],
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
    manifest = {'sample_id': sample_id, 'portable_relative_paths': True,
        'captures': labels, 'observation_capture': selected,
        'raw_images_are_not_modified': True, 'raw_sdk_samples': sdk_path,
        'sdk_review': 'sdk_review.json', 'original_pair': pair_path,
        'physical_pair_record_present': pair_path is not None,
        'review': 'depth_review.json', 'calibration': 'calibration.json',
        'cube_edge_mm_approximate': a.cube_edge_mm, 'geometric_center_reference_confirmed': False,
        'calibration_fit_performed': False, 'files': files,
        'file_count': len(files), 'total_bytes': sum(f['bytes'] for f in files),
        'absolute_accuracy_below_10mm_verified': False}
    dump(a.output / 'manifest.json', manifest)
    print(json.dumps({'files': len(files), 'bytes': manifest['total_bytes'],
                     'high_support': report['high_support_temporal'], 'common_reference_confirmed': False}))
    return manifest


if __name__ == '__main__':
    main()
