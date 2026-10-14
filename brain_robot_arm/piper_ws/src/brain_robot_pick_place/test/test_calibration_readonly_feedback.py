"""Receive translation and telemetry only; no real CAN/ROS endpoints in tests."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import calibration_readonly_feedback as bridge


@pytest.mark.parametrize('can_id', list(range(0x3A0, 0x3A8)) + [0x2A5, 0x251, 0x472])
def test_parser_installed_preserves_source_and_never_sends(can_id):
    received, bus = [], NS(callback_function=None)
    piper = NS(GetCanBus=lambda: bus, ParseCANFrame=received.append)
    message = NS(arbitration_id=can_id, data=bytes(range(8)), timestamp=123.,
                 is_extended_id=False, is_remote_frame=False, is_error_frame=False,
                 channel='fixture', dlc=8)
    bridge.install_receive_parser(piper)
    bus.callback_function(message)
    assert message.arbitration_id == can_id
    expected = can_id - 0xFF if 0x3A0 <= can_id <= 0x3A7 else can_id
    assert received[0].arbitration_id == expected
    assert {k: v for k, v in vars(received[0]).items() if k != 'arbitration_id'} == {
            k: v for k, v in vars(message).items() if k != 'arbitration_id'}


def sample():
    return {'fresh_after_passive_connection': True,
            'sdk_receipt_stamps': {'joint': '10.025'},
            'q_driver_rad': [.017444, .034888, -.017444, 0., 1., 0.],
            'speed_millirad_s': [10, -10, 0, 0, 0, 0]}


def test_telemetry_uses_named_joints_original_conversion_and_receipt_stamp():
    result = bridge.feedback_values(sample(), 0)
    assert result['names'] == [f'joint{i}' for i in range(1, 7)]
    assert result['positions'] == sample()['q_driver_rad']
    assert result['velocities'] == [.01, -.01, 0., 0., 0., 0.]
    assert result['stamp_ns'] == 10_025_000_000
    assert 'not hardware' in result['stamp_scope']


@pytest.mark.parametrize('fault', ['stale', 'duplicate', 'older', 'missing', 'nan'])
def test_missing_stale_or_repeated_data_never_gets_new_timer_stamp(fault):
    row, previous = sample(), 0
    if fault == 'stale': row['fresh_after_passive_connection'] = False
    if fault == 'duplicate': previous = 10_025_000_000
    if fault == 'older': previous = 10_026_000_000
    if fault == 'missing': row['q_driver_rad'] = []
    if fault == 'nan': row['q_driver_rad'][0] = float('nan')
    assert bridge.feedback_values(row, previous) is None


def test_can_down_preflight_opens_no_device_or_ros_and_preserves_null(tmp_path):
    output = tmp_path / 'down.json'
    assert bridge.run_bridge(output, 1., lambda **_: pytest.fail('Opened device while DOWN'), lambda: False) == 2
    result = json.loads(output.read_text())
    assert result['published'] == 0 and result['actual_last_sample'] is None
    assert not result['motion_commands_sent']
    assert 'no activation' in result['error']


def test_existing_output_refused_before_link_check(tmp_path):
    existing = tmp_path / 'existing.json'; existing.write_text('{}')
    with pytest.raises(FileExistsError):
        bridge.run_bridge(existing, 2., link_reader=lambda: pytest.fail('Checked link before overwrite refusal'))


@pytest.mark.parametrize('duration', [0, 121, float('nan')])
def test_unbounded_duration_refused_before_device(tmp_path, duration):
    with pytest.raises(ValueError):
        bridge.run_bridge(tmp_path / 'raw.json', duration, link_reader=lambda: pytest.fail('Opened device'))


def test_no_control_interfaces_and_one_literal_telemetry_topic():
    source = Path(bridge.__file__).read_text()
    calls = {n.func.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)}
    assert not calls & {'create_subscription', 'create_client', 'create_service', 'send_goal_async',
        'JointCtrl', 'GripperCtrl', 'EnableArm', 'DisableArm', 'ResetPiper', 'MasterSlaveConfig',
        'MotionCtrl_1', 'MotionCtrl_2', 'send', 'SendCanMessage'}
    assert bridge.TOPIC == '/joint_states_feedback'
    assert 'ConnectPort(piper_init=False)' in source
    assert source.index('install_receive_parser(piper)\n        piper.ConnectPort') > 0


def test_sdk_capture_installs_same_parser_before_connect():
    source = Path(bridge.__file__).with_name('collect_calibration_sdk.py').read_text()
    assert source.index('install_receive_parser(piper)\n        piper.ConnectPort') > 0
