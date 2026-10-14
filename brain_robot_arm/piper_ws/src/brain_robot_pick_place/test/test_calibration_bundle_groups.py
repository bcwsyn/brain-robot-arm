"""Portable multi-group export regressions; fixtures are NOT new physical pairs."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import export_calibration_bundle as exporter
import estimate_calibration_cube_center as estimator
import review_pair_sampling as sampling

ORIGINAL = Path(__file__).resolve().parents[5] / 'docs/evidence/piper_calibration_20261014/pair01'


@pytest.fixture
def export_args(tmp_path, monkeypatch):
    """Rename selected archived images; mock only the installed robot model."""
    capture = tmp_path / 'fixture_new_pair02_observe'
    (capture / 'evidence').mkdir(parents=True)
    original_capture = ORIGINAL / 'pair01_observe_remeasure_20261014_rgbd'
    rows = [json.loads(line) for line in (original_capture / 'observer.jsonl').read_text().splitlines()[:3]]
    frames = copy.deepcopy(json.loads((ORIGINAL / 'depth_review.json').read_text())['frames'][:3])
    for row, frame in zip(rows, frames):
        for name, image in row['images'].items():
            source = original_capture / image['path']
            target = capture / 'evidence' / source.name
            shutil.copyfile(source, target)
            image['path'] = str(target)
            frame['images'][name]['path'] = str(target)
    (capture / 'observer.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (capture / 'summary.json').write_text(json.dumps({'test_fixture_only': True, 'saved_frames': 3}))
    review_path = tmp_path / 'review.json'
    review_path.write_text(json.dumps({'frames': frames, 'common_reference': {}, 'high_support_temporal': {},
                                     'test_fixture_only': True}))
    sdk_samples = []
    for i in range(31):
        epoch = 1000. + .1 * i
        sdk_samples.append({'epoch': epoch, 'q_mdeg': [1000, 2000, -3000, 0, 4000, 0],
            'sdk_receipt_stamps': {k: str(epoch - .01) for k in ('joint', 'high', 'low', 'gripper')},
            'high_hz': 100., 'fresh_after_passive_connection': True})
        sdk_samples[-1]['q_driver_rad'] = [v / 1000. * .017444 for v in sdk_samples[-1]['q_mdeg']]
    sdk_samples.append({'epoch': 1004., 'q_mdeg': [0] * 6, 'fresh_after_passive_connection': False})
    sdk = tmp_path / 'sdk.json'
    sdk.write_text(json.dumps({'samples': sdk_samples, 'quality': {'test_fixture_only': True},
                               'motion_commands_sent': False}))
    task = tmp_path / 'synthetic_task.yaml'
    task.write_text('test_fixture_only: true\n')
    monkeypatch.setattr(exporter, 'load_installed_model', lambda: (
        '<robot name="test_fixture_only"><link name="base_link"/><link name="gripper_base"/>'
        '<joint name="fixed" type="fixed"><parent link="base_link"/><child link="gripper_base"/>'
        '</joint></robot>', task))
    return SimpleNamespace(output=tmp_path / 'portable_bundle', capture=[capture],
        sample_id='fixture_new_pair02', observation_capture=None, legacy=None, manual=None,
        sdk=sdk, pair=None, camera_metadata=ORIGINAL / 'camera_factory_current.json',
        review=review_path, detector_config=ORIGINAL / 'detector_config.yaml', cube_edge_mm=29.)


def test_new_group_exports_current_sdk_without_requiring_a_legacy_pair(export_args):
    original_hash = hashlib.sha256(export_args.sdk.read_bytes()).hexdigest()
    manifest = exporter.export_bundle(export_args)
    exporter.verify_bundle(export_args.output, manifest)
    assert manifest['sample_id'] == 'fixture_new_pair02'
    assert manifest['observation_capture'] == export_args.capture[0].name
    assert manifest['original_pair'] is None and not manifest['physical_pair_record_present']
    assert not manifest['geometric_center_reference_confirmed']
    assert hashlib.sha256((export_args.output / manifest['raw_sdk_samples']).read_bytes()).hexdigest() == original_hash
    sdk = json.loads((export_args.output / 'sdk_review.json').read_text())
    assert sdk['source_schema'] == 'current_passive_capture'
    assert all(r['T_base_tool'] is not None for r in sdk['samples'][:31])
    assert sdk['samples'][-1]['q_driver_rad'] is None and sdk['samples'][-1]['T_base_tool'] is None
    assert sdk['gripper_base_cube_center_m'] is None and not sdk['physical_contact_verified']
    rows = [json.loads(line) for line in (exporter.observation_capture(export_args.output, manifest) /
                                        'observer.jsonl').read_text().splitlines()]
    assert len(rows) == 3
    assert all(isinstance(v, str) for r in rows for v in r['stamps_ns'].values())
    for source_row, result in zip(json.loads(export_args.review.read_text())['frames'], rows):
        for name, image in result['images'].items():
            raw = export_args.output / export_args.capture[0].name / image['path']
            assert hashlib.sha256(raw.read_bytes()).hexdigest() == source_row['images'][name]['sha256']
    calibration = json.loads((export_args.output / 'calibration.json').read_text())
    assert calibration['depth']['size'] == rows[0]['latest']['/camera/depth/camera_info']['size']
    raw_rgb = cv2.imread(str(export_args.output / export_args.capture[0].name / rows[0]['images']['rgb']['path']))
    assert calibration['color_capture']['size'] == list(raw_rgb.shape[1::-1])


def test_new_name_works_for_sampling_and_center_analysis_without_raw_changes(export_args):
    manifest = exporter.export_bundle(export_args)
    before = {f['path']: f['sha256'] for f in manifest['files']}
    sample_result = sampling.review(export_args.output, export_args.output.parent / 'sampling')
    center_result = estimator.review_bundle(export_args.output, export_args.output.parent / 'center', (29.,))
    assert sample_result['sample_id'] == center_result['sample_id'] == 'fixture_new_pair02'
    assert sample_result['groups']['high']['frames'] == 2
    assert sample_result['groups']['low']['frames'] == 1
    assert center_result['summaries']['29']['candidates'] == 2
    assert not center_result['summaries']['29']['minimum_twenty_high_support_met']
    assert not center_result['summaries']['29']['formal_pair_fit_allowed']
    assert center_result['frames'][0]['candidate_by_nominal_edge_mm'] == {}
    exporter.verify_bundle(export_args.output, manifest)
    assert before == {f['path']: hashlib.sha256((export_args.output / f['path']).read_bytes()).hexdigest()
                      for f in manifest['files']}


def test_all_high_group_does_not_require_fabricating_a_low_frame(export_args):
    source = export_args.capture[0] / 'observer.jsonl'
    source.write_text('\n'.join(source.read_text().splitlines()[1:]) + '\n')
    review = json.loads(export_args.review.read_text()); review['frames'] = review['frames'][1:]
    export_args.review.write_text(json.dumps(review))
    exporter.export_bundle(export_args)
    result = sampling.review(export_args.output, export_args.output.parent / 'all_high')
    assert result['groups']['high']['frames'] == 2
    assert result['groups']['low']['frames'] == 0
    assert result['group_surface_separation_m'] is None and len(result['previews']) == 1


def test_legacy_manifest_finds_single_observer_without_hardcoded_name():
    manifest = json.loads((ORIGINAL / 'manifest.json').read_text())
    assert exporter.observation_capture(ORIGINAL, manifest).name == 'pair01_observe_remeasure_20261014_rgbd'
    exporter.verify_bundle(ORIGINAL, manifest)


def test_legacy_export_options_and_raw_sdk_remain_compatible(export_args):
    export_args.legacy = export_args.output.parent / 'legacy'
    export_args.manual = export_args.output.parent / 'manual'
    export_args.legacy.mkdir(); export_args.manual.mkdir()
    export_args.sdk = ORIGINAL / 'manual_grasp/sdk_samples.json'
    export_args.pair = ORIGINAL / 'original_pair01.json'
    export_args.sample_id = None
    manifest = exporter.export_bundle(export_args)
    assert manifest['sample_id'] == 'pair01_20261014'
    assert manifest['original_pair'] == 'original_pair01.json'
    assert (export_args.output / manifest['original_pair']).read_bytes() == export_args.pair.read_bytes()
    sdk = json.loads((export_args.output / 'sdk_review.json').read_text())
    assert sdk['source_schema'] == 'legacy_receipt_capture'
    assert all(r['feedback_fresh'] is None and r['T_base_tool'] is None for r in sdk['samples'])


@pytest.mark.parametrize('path', ['../outside.png', '/absolute.png', 'one/../../outside.png'])
def test_nonportable_asset_paths_are_refused(tmp_path, path):
    with pytest.raises(ValueError, match='Non-portable'):
        exporter.bundle_asset(tmp_path, path)


def test_symlink_and_bad_hash_refused(tmp_path):
    (tmp_path / 'target').write_text('raw')
    (tmp_path / 'link').symlink_to(tmp_path / 'target')
    with pytest.raises(ValueError, match='Linked'):
        exporter.bundle_asset(tmp_path, 'link')
    with pytest.raises(ValueError, match='SHA mismatch'):
        exporter.verify_bundle(tmp_path, {'files': [{'path': 'target', 'sha256': 'wrong'}]})


def test_multiple_captures_need_explicit_selection(tmp_path):
    manifest = {'files': [{'path': 'one/observer.jsonl'}, {'path': 'two/observer.jsonl'}]}
    with pytest.raises(ValueError, match='Select one'):
        exporter.observation_capture(tmp_path, manifest)
    assert exporter.observation_capture(tmp_path, manifest, 'two') == tmp_path / 'two'
    with pytest.raises(ValueError, match='hashed manifest'):
        exporter.observation_capture(tmp_path, manifest, 'not_listed')


def test_export_refuses_overwrite_before_model_loading(export_args, monkeypatch):
    export_args.output.mkdir()
    monkeypatch.setattr(exporter, 'load_installed_model', lambda: pytest.fail('Model loaded before overwrite rejection'))
    with pytest.raises(FileExistsError):
        exporter.export_bundle(export_args)


def test_empty_real_capture_cannot_be_exported_as_a_complete_packet(export_args, monkeypatch):
    (export_args.capture[0] / 'observer.jsonl').write_text('')
    monkeypatch.setattr(exporter, 'load_installed_model', lambda: pytest.fail('Empty capture reached model loading'))
    with pytest.raises(ValueError, match='No paired observations'):
        exporter.export_bundle(export_args)


def test_actual_task_symlink_install_snapshots_exact_target_not_raw_links(export_args, monkeypatch):
    urdf, original_task = exporter.load_installed_model()
    installed = original_task.parent / 'installed_task.yaml'
    installed.symlink_to(original_task)
    monkeypatch.setattr(exporter, 'load_installed_model', lambda: (urdf, installed))
    manifest = exporter.export_bundle(export_args)
    exporter.verify_bundle(export_args.output, manifest)
    snapshot = export_args.output / 'robot_task_config_snapshot.yaml'
    assert not snapshot.is_symlink() and snapshot.read_bytes() == original_task.read_bytes()


@pytest.mark.parametrize('sample_id', ['', '../group', 'a b', '/root', 'a' * 81])
def test_invalid_group_id_refused_before_export(export_args, sample_id):
    export_args.sample_id = sample_id
    with pytest.raises(ValueError, match='identifier'):
        exporter.export_bundle(export_args)
    assert not export_args.output.exists()


def test_false_fresh_flag_cannot_publish_a_stale_zero_fk():
    root = None
    packet = {'quality': {}, 'samples': [{'q_mdeg': [0] * 6, 'epoch': 1000.,
        'fresh_after_passive_connection': True, 'high_hz': 0.,
        'sdk_receipt_stamps': {k: '0' for k in ('joint', 'high', 'low', 'gripper')}}]}
    review = exporter.sdk_review(packet, root)
    assert review['samples'][0]['feedback_fresh'] is False
    assert review['samples'][0]['q_driver_rad'] is None and review['samples'][0]['T_base_tool'] is None


def test_three_tools_do_not_acquire_hardware_or_send_control_commands():
    prohibited = {'create_publisher', 'create_client', 'send_goal_async', 'ConnectPort',
                  'JointCtrl', 'GripperCtrl', 'EnableArm', 'DisableArm', 'ResetPiper', 'MasterSlaveConfig'}
    for module in (exporter, sampling, estimator):
        tree = ast.parse(Path(module.__file__).read_text())
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)}
        assert not calls & prohibited
