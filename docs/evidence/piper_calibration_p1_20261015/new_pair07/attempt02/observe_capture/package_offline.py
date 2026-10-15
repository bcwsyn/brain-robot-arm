"""Offline evidence package for one new placement; no device or ROS access."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

import cv2
import numpy as np

REPO = Path('/mnt/hgfs/ub')
ROOT = Path('/home/johnwick/brain_robot_logs/new_pair07_attempt02_A.j_rigpw0')
TESTS = REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0, str(TESTS))
from export_calibration_bundle import verify_bundle
from review_calibration_capture import temporal_summary
from review_depth_registration import calibration, read_config

def load(p):
    return json.loads(p.read_text())

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def put(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')

OUT = ROOT/'publish'
OUT.mkdir(exist_ok=False)
s, bundle = ROOT/'session', ROOT/'portable_all60'
execution = load(s/'execution.json')
quality = load(ROOT/'quality/report.json')
assert execution['raw_acquisition_complete'] and execution['all_owned_sources_exited']
assert execution['within_camera_budget'] and execution['error'] is None
assert load(ROOT/'production_SHA_before.json') == load(ROOT/'production_SHA_after.json')
assert load(s/'source_SHA_before.json') == load(s/'source_SHA_after.json')
baseline = load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/release_observe_capture/assessment.json')
for path, v in baseline['production_SHA'].items():
    assert sha(Path(path)) == v['expected']
assert sha(Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')) == baseline['deployed_adapter_sha256']
before, after = load(s/'can_before.json'), load(s/'can_after.json')
assert after['rx'] > before['after']['rx'] and after['tx'] == before['before']['tx']
verify_bundle(bundle, load(bundle/'manifest.json'))
rows = [json.loads(l) for l in (bundle/'capture/observer.jsonl').read_text().splitlines() if l]
frames = quality['frames']
assert len(rows) == len(frames) == 60
assert not np.ptp([r['q_rad'] for r in rows], axis=0).any()
good_ids = {f['snapshot'] for f in frames if f['good_top_frame']}
assert good_ids == {57} and quality['summary']['good_top_frames'] == 1
indices = set(np.rint(np.linspace(0, 59, 20)).astype(int).tolist())
assert len(indices) == 20 and {rows[i]['snapshot'] for i in indices} >= good_ids
chosen = [r for i, r in enumerate(rows) if i in indices]
chosen_ids = {r['snapshot'] for r in chosen}
portable = OUT/'portable_review20'
(portable/'capture/evidence').mkdir(parents=True)
for name in ['sdk_samples.json', 'sdk_review.json', 'camera_factory_current.json',
             'detector_config.yaml', 'robot_task_config_snapshot.yaml', 'calibration.json']:
    shutil.copyfile(bundle/name, portable/name)
for row in chosen:
    assert row['stamps_ns']['depth'] == row['stamps_ns']['depth_info']
    for image in row['images'].values():
        rel = Path(image['path'])
        assert not rel.is_absolute() and '..' not in rel.parts
        assert sha(bundle/'capture'/rel) == image['sha256']
        shutil.copyfile(bundle/'capture'/rel, portable/'capture'/rel)
(portable/'capture/observer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in chosen))
shutil.copyfile(bundle/'capture/summary.json', portable/'capture/source_capture_summary.json')
put(portable/'capture/summary.json', {'derived_review_subset': True, 'source_saved_frames': 60,
    'saved_frames': 20, 'selected_original_good_top_frames': 1, 'good_top_snapshots': sorted(good_ids),
    'source_indices_zero_based': sorted(indices), 'fitting_input': False,
    'source_summary': 'source_capture_summary.json'})
review = load(bundle/'depth_review.json')
review['frames'] = [f for f in review['frames'] if f['snapshot'] in chosen_ids]
review['temporal'] = temporal_summary(review['frames'])
review['high_support_temporal'] = temporal_summary([f for f in review['frames'] if f['color_pixel_coverage'] >= .5])
review['analysis_subset'] = {'source_count': 60, 'selected_count': 20,
    'qualified_top_count': 1, 'fit_approved': False,
    'SDK_scope': 'New passive SDK window after formal image collection, partially overlapping factory/cleanup; not per-image SDK. Each image retains its own actual fresh JointState.'}
put(portable/'depth_review.json', review)
manifest = load(bundle/'manifest.json')
manifest.update(sample_id='new_pair07_attempt02_review20', source_frame_count=60,
    selected_frame_count=20, original_good_top_frames=1,
    selection_profile='20 uniform original diagnostic frames, including sole qualifying snapshot57; NOT20 good frames')
manifest['files'] = [{'path': p.relative_to(portable).as_posix(), 'bytes': p.stat().st_size,
                      'sha256': sha(p)} for p in sorted(portable.rglob('*')) if p.is_file()]
manifest['file_count'] = len(manifest['files'])
manifest['total_bytes'] = sum(v['bytes'] for v in manifest['files'])
put(portable/'manifest.json', manifest)
verify_bundle(portable, manifest)
shutil.copytree(ROOT/'quality', OUT/'quality_all60')
for name in ['execution.json', 'readiness.json', 'feedback.json', 'factory.json',
             'can_before.json', 'can_after.json', 'source_SHA_before.json', 'source_SHA_after.json']:
    shutil.copyfile(s/name, OUT/('A_'+name))
for name in ['production_SHA_before.json', 'production_SHA_after.json', 'junit.xml']:
    shutil.copyfile(ROOT/name, OUT/name)
sources = OUT/'executed_sources'
sources.mkdir()
shutil.copyfile('/tmp/piper_pair07_attempt02_collect_A.py', sources/'piper_pair07_attempt02_collect_A.py')
for name in ['capture_calibration_session.py', 'collect_calibration_sdk.py', 'review_calibration_capture.py',
             'export_calibration_bundle.py', 'calibration_p0_quality.py']:
    shutil.copyfile(TESTS/name, sources/name)

# Derived, static placement guidance only. It does not change any gate or TF.
rgb = cv2.imread(str(bundle/'capture'/rows[0]['images']['rgb']['path']))
guidance = rgb.copy()
cv2.rectangle(guidance, (148, 107), (170, 128), (0, 0, 255), 1)
cv2.drawMarker(guidance, (159, 165), (0, 255, 0), cv2.MARKER_CROSS, 16, 1)
cv2.rectangle(guidance, (143, 149), (175, 181), (0, 255, 0), 1)
cv2.arrowedLine(guidance, (159, 132), (159, 152), (0, 255, 0), 1)
cv2.imwrite(str(OUT/'next_flat_mat_placement.png'),
            cv2.resize(guidance, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST))
camera = calibration(read_config(bundle/'detector_config.yaml'))
# Use the observed top plane for an explicitly conditional ray/plane estimate.
top = frames[0]['top_candidate']
n = np.asarray(top['outward_normal_depth'])
origin = np.asarray(top['face_center_depth_m'])
def same_plane_point(u, v):
    ray_c = np.linalg.inv(camera['k']) @ np.array([
        u*(camera['size'][0]-1)/319., v*(camera['size'][1]-1)/239., 1.])
    ray_d = np.linalg.inv(camera['r']) @ ray_c
    offset_d = -np.linalg.inv(camera['r']) @ camera['t']
    scale = n @ (origin-offset_d)/(n @ ray_d)
    return offset_d+scale*ray_d
current_model = same_plane_point(159, 117.5)
next_model = same_plane_point(159, 165)
assert next_model[2] < current_model[2] and next_model[2] > .15
put(OUT/'placement_guidance.json', {'offline_only': True, 'static_source_snapshot': 1,
    'current_rgb_box_xywh': [148,107,22,21], 'suggested_image_centre_xy': [159,165],
    'meaning': 'Move only cube toward camera-side mat / green cross; no bottle, no arm motion or grip yet',
    'conditional_same_plane_D_z_m': {'current_ray': float(current_model[2]), 'suggested_ray': float(next_model[2])},
    'future_depth_is_measured': False, 'future_depth_or_800_points_guaranteed': False,
    'assumption': 'Same visible top plane extended locally on the flat mat; not a mounting transform or robot motion',
    'original_thresholds_unchanged': True, 'new_position_requires_new_A_and_B': True})

assets = []
with tarfile.open(OUT/'runtime_closed.tar.gz', 'w:gz') as archive:
    for label, path in [('session', s), ('portable_all60', bundle),
                        ('sdk_post_capture.json', ROOT/'sdk_post_capture.json'),
                        ('coordinator.log', ROOT/'coordinator.log')]:
        files = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file())
        for p in files:
            assert not p.is_symlink()
            name = label if path.is_file() else label+'/'+p.relative_to(path).as_posix()
            archive.add(p, arcname=name, recursive=False)
            assets.append({'path': name, 'bytes': p.stat().st_size, 'sha256': sha(p)})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
    for item in assets:
        assert hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest() == item['sha256']
put(OUT/'runtime_manifest.json', {'archive_sha256': sha(OUT/'runtime_closed.tar.gz'),
    'files': assets, 'all_SHA_verified': True, 'raw_deleted': False})
sdk = load(ROOT/'sdk_post_capture.json')
counts = [f['top_plane_inliers'] for f in frames]
depth = load(ROOT/'depth_review.json')
assessment = {'pair_id': 'new_pair07', 'attempt': 2, 'role': 'held_out',
    'operator_new_placement_confirmed': True, 'new_B_captured': False,
    'old_B_must_not_be_paired': '8f8eed6 belongs to old cube position',
    'read_only_A_frames': 60, 'selected_review_frames': 20,
    'top_candidates_with_complete_square': sum(f['top_candidate'] is not None for f in frames),
    'original_good_top_frames': len(good_ids), 'original_good_top_snapshot_ids': sorted(good_ids),
    'original_twenty_good_frames_met': False, 'formal_pair_approved': False,
    'native_top_inliers': {'min': min(counts), 'median': float(np.median(counts)), 'max': max(counts)},
    'RGB_depth_coverage': {'min': min(f['color_pixel_coverage'] for f in frames),
                           'median': float(np.median([f['color_pixel_coverage'] for f in frames])),
                           'max': max(f['color_pixel_coverage'] for f in frames)},
    'actual_A_q_rad': rows[0]['q_rad'], 'A_q_spread_rad': np.ptp([r['q_rad'] for r in rows],axis=0).tolist(),
    'surface_depth_temporal': depth['temporal'], 'normal_statistics': quality['summary']['top_plane_normal_statistics'],
    'SDK_quality': sdk['quality'], 'last_enabled_historical': sdk['samples'][-1]['enabled'],
    'last_gripper_mm_historical': sdk['samples'][-1]['gripper_mm'],
    'capture_elapsed_s': execution['capture_summary']['elapsed_s'],
    'camera_elapsed_s': execution['camera_elapsed_s_including_cleanup'],
    'all_owned_sources_exited': True, 'read_only_CAN_TX_delta': after['tx']-before['before']['tx'],
    'CAN_RX_before': before['before']['rx'], 'CAN_RX_after': after['rx'],
    'production_unchanged': True, 'candidate_adapter_deployed': False,
    'motion_enable_arm_gripper_reset_disable_commands_sent': False, 'CAN_recovery': False,
    'tests_passed': 81, 'runtime_files_SHA_verified': len(assets),
    'portable_assets_SHA_verified': len(manifest['files']), 'raw_data_deleted': False,
    'fit_performed': False, 'TF_deployed': False, 'GitHub_pushed': False,
    'next': 'Need a slightly closer flat-mat placement before another A; no identical-condition60 retry or hand-grip yet. Keep all original criteria.'}
put(OUT/'assessment.json', assessment)
shutil.copyfile(Path(__file__), OUT/'package_offline.py')
print(json.dumps({k:assessment[k] for k in ['read_only_A_frames','original_good_top_frames',
    'native_top_inliers','runtime_files_SHA_verified','portable_assets_SHA_verified','tests_passed']}, ensure_ascii=False))
