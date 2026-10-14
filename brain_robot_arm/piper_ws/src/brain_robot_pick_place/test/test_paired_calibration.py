"""Offline contract, degeneracy and acquisition serialization regressions."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import collect_calibration_sdk as sdk
import collect_static_rgbd as collector
import fit_paired_calibration as fit
import simulate_paired_calibration as simulation
from review_pair_sampling import selected_pixels
from review_depth_registration import calibration, read_config


def test_exact_full_parameter_recovery_and_prefix_excitation():
    data, truth, center = simulation.make_dataset()
    result = fit.solve(data)
    candidate = result['candidate']
    assert np.array(candidate['X_tool_from_depth_camera']) == pytest.approx(truth, abs=1e-8)
    assert candidate['cube_center_in_tool_m'] == pytest.approx(center, abs=1e-8)
    assert candidate['not_approved_for_deployment']
    assert result['synthetic'] and result['excitation']['rank'] == 9
    assert result['five_plus_one_collection_complete']
    assert result['per_acquired_training_prefix'][0]['rank'] <= 3
    assert result['held_out_validation']['maximum_m'] < 1e-8


def test_yaw_only_joint_point_gauge_is_not_hidden_by_small_residual():
    data, _, _ = simulation.make_dataset('yaw_only')
    result = fit.solve(data)
    assert result['training']['rms_m'] < 1e-8
    assert result['excitation']['rank'] == 8
    assert result['candidate'] is None
    assert len(result['excitation']['null_directions_parameter_units']) == 1


def test_known_tool_point_changes_identifiability_not_a_motion_proposal():
    data, truth, _ = simulation.make_dataset('yaw_only', known_point=True)
    result = fit.solve(data)
    assert result['excitation']['rank'] == 6
    assert np.array(result['candidate']['X_tool_from_depth_camera']) == pytest.approx(truth, abs=1e-8)


def test_collinear_camera_points_cannot_determine_complete_mount():
    data, _, _ = simulation.make_dataset('collinear', known_point=True)
    result = fit.solve(data)
    assert result['candidate'] is None
    assert result['excitation']['rank'] < 6


@pytest.mark.parametrize('field,value', [('camera_center_m', None),
    ('camera_center_verified', False), ('physical_grip_verified', False),
    ('released_without_object_motion_verified', False), ('reference', 'visible_surface'),
    ('camera_center_m', [0., 0., float('nan')]), ('camera_center_m', [0., 0., -.2])])
def test_missing_or_unverified_physical_center_never_enters_fit(field, value):
    data, _, _ = simulation.make_dataset()
    data['pairs'][0][field] = value
    with pytest.raises(ValueError):
        fit.solve(data)


def test_validation_does_not_influence_fit_or_initialisation():
    data, _, _ = simulation.make_dataset()
    before = fit.solve(data)
    data['pairs'][-1]['camera_center_m'][0] += .1
    after = fit.solve(data)
    assert before['candidate'] == after['candidate']
    assert after['held_out_validation']['maximum_m'] > .09


def test_trial_missing_point_is_explicitly_excluded_not_downweighted():
    data, _, _ = simulation.make_dataset()
    data['pairs'].append({'pair_id': 'pair01_trial', 'role': 'trial', 'camera_center_m': None})
    result = fit.solve(data)
    assert result['candidate'] is not None
    assert result['excluded'][0]['pair_id'] == 'pair01_trial'


def test_duplicate_pair_ids_and_unverified_fixed_tip_are_refused():
    data, _, _ = simulation.make_dataset()
    data['pairs'][-1]['pair_id'] = data['pairs'][0]['pair_id']
    with pytest.raises(ValueError, match='Unique'):
        fit.solve(data)
    data, _, _ = simulation.make_dataset(known_point=True)
    data['known_tool_point']['verified'] = False
    with pytest.raises(ValueError, match='Known tool'):
        fit.solve(data)


def test_reflection_matrix_is_not_silently_turned_into_a_rotation():
    bad = np.eye(4); bad[0, 0] = -1
    with pytest.raises(ValueError, match='rigid'):
        fit.transform(bad)


def test_noise_missing_data_and_training_bias_simulation():
    results = simulation.run_simulation()
    assert results['synthetic_only'] and not results['hardware_or_production_touched']
    assert results['cases']['missing_depth_center']['candidate'] is None
    assert results['cases']['training_only_25mm_bias']['training']['rms_m'] < 1e-8
    assert results['cases']['training_only_25mm_bias']['held_out_validation']['maximum_m'] > .02
    assert len(results['twenty_noise_trials']['held_out_error_m']) == 20


def test_full_actual_depth_info_serializes_without_replacing_it_with_factory_values():
    info = NS(header=NS(stamp=NS(sec=1791972000, nanosec=987654321), frame_id='actual_depth'),
        width=640, height=400, distortion_model='plumb_bob', k=list(np.eye(3).ravel()),
        d=[.1, .2, .3, .4, .5], r=list(np.eye(3).ravel()), p=list(range(12)),
        binning_x=0, binning_y=0,
        roi=NS(x_offset=0, y_offset=0, width=0, height=0, do_rectify=False))
    saved = json.loads(json.dumps(collector.full_camera_info(info)))
    assert saved['stamp_ns'] == '1791972000987654321'
    assert saved['d'] == info.d and saved['p'] == info.p
    assert saved['frame'] == 'actual_depth'


def test_calibration_three_second_static_window_not_a_production_gate_change():
    q = [0.] * 6
    history = [(i, q) for i in range(10_000_000_000, 13_010_000_000, 10_000_000)]
    assert collector.settled_feedback(history, q, 13_000_000_000, 3.)
    assert not collector.settled_feedback(history[-100:], q, 13_000_000_000, 3.)


def fake_sdk(stamp=10.9):
    joints = NS(time_stamp=stamp, Hz=100., joint_state=NS(**{f'joint_{i}': i * 1000 for i in range(1, 7)}))
    high = NS(time_stamp=stamp, Hz=100., **{f'motor_{i}': NS(motor_speed=0) for i in range(1, 7)})
    low = NS(time_stamp=stamp, **{f'motor_{i}': NS(foc_status=NS(driver_enable_status=True)) for i in range(1, 7)})
    grip = NS(time_stamp=stamp, gripper_state=NS(grippers_angle=29000, grippers_effort=1500, foc_status='fixture'))
    return NS(GetArmJointMsgs=lambda: joints, GetArmHighSpdInfoMsgs=lambda: high,
              GetArmLowSpdInfoMsgs=lambda: low, GetArmGripperMsgs=lambda: grip)


def test_sdk_snapshot_missing_receipt_time_is_not_actual_zero_pose():
    invalid = sdk.snapshot(fake_sdk(0.), 11., 10.)
    assert not invalid['fresh_after_passive_connection']
    valid = sdk.snapshot(fake_sdk(), 11., 10.)
    assert valid['fresh_after_passive_connection'] and valid['gripper_mm'] == 29.
    assert valid['q_driver_rad'][0] == pytest.approx(.017444)
    assert not valid['physical_contact_verified_by_sdk']
    assert not sdk.summarize([invalid])['static_three_seconds_and_thirty_samples']


def test_collection_schema_dry_run_is_explicitly_synthetic_not_physical():
    samples = []
    for i in range(35):
        now = 11. + .1 * i
        samples.append(sdk.snapshot(fake_sdk(now - .01), now, 10.))
    artifact = json.loads(json.dumps({'synthetic': True, 'samples': samples,
                                      'quality': sdk.summarize(samples)}))
    assert artifact['quality']['static_three_seconds_and_thirty_samples']
    assert artifact['samples'][0]['enabled'] == [True] * 6
    assert len(artifact['samples'][0]['q_mdeg']) == 6
    assert len(artifact['samples'][0]['speed_millirad_s']) == 6
    assert not artifact['samples'][0]['physical_contact_verified_by_sdk']


def test_sdk_existing_output_refused_before_interface_constructor(tmp_path):
    existing = tmp_path / 'raw.json'; existing.write_text('{}')
    with pytest.raises(FileExistsError):
        sdk.collect(existing, 6, lambda **_: pytest.fail('opened device before overwrite check'))


def test_analysis_tools_have_no_control_interfaces_or_production_writes():
    for module in (sdk, fit, simulation):
        tree = ast.parse(Path(module.__file__).read_text())
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not calls & {'create_publisher', 'create_client', 'send_goal_async',
                           'JointCtrl', 'GripperCtrl', 'EnableArm', 'DisableArm', 'ResetPiper', 'MasterSlaveConfig'}
    source = Path(sdk.__file__).read_text()
    assert 'ConnectPort(piper_init=False)' in source


def test_native_missing_samples_are_not_created_by_registration():
    root = Path(__file__).resolve().parents[5]
    config = root / 'docs/evidence/piper_calibration_20261014/pair01/detector_config.yaml'
    if not config.exists():
        pytest.skip('Only canonical repo contains pair01 witness')
    params = read_config(config)
    rgb = np.zeros((240, 320, 3), np.uint8)
    depth = np.zeros((400, 640), np.uint16)
    selected, _, _, _ = selected_pixels(rgb, depth, {'k': [476., 0, 325., 0, 476., 199., 0, 0, 1]}, params, calibration(params))
    assert not selected.any() and not depth.any()
