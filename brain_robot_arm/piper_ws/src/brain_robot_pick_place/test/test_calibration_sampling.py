"""Read-only review regression tests; no real-arm or calibration accuracy claim."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('sampling', Path(__file__).with_name('review_calibration_sampling.py'))
sampling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampling)


def params():
    return {'real_trajectory_joint_min': [-2.] * 6, 'real_trajectory_joint_max': [2.] * 6}


def test_sample_sequence_changes_only_j4_or_j5_and_preserves_start():
    q = np.array([.1, .2, .3, .4, .5, .6])
    original = q.copy()
    states = sampling.sample_states(q, 6.)
    assert len(states) == 5
    assert states[0][1] == pytest.approx(original)
    assert q == pytest.approx(original)
    for (_, target), axis, sign in zip(states[1:], [3, 3, 4, 4], [-1, 1, -1, 1]):
        delta = np.zeros(6)
        delta[axis] = sign * np.deg2rad(6)
        assert target - q == pytest.approx(delta)


@pytest.mark.parametrize('start,angle', [([0.] * 5, 6), ([np.nan] * 6, 6),
                                      ([0.] * 6, 0), ([0.] * 6, 7), ([0.] * 6, np.inf)])
def test_invalid_input_refused(start, angle):
    with pytest.raises(ValueError):
        sampling.sample_states(start, angle)


def test_checked_trajectory_maps_joint_names_not_array_order():
    start, goal = [0.] * 6, [0., 0., 0., .1, 0., 0.]
    names = sampling.NAMES[::-1]
    result = sampling.checked_trajectory(names, [start[::-1], goal[::-1]], start, goal, params())
    assert result == {'points': 2, 'task_limits_passed': True, 'max_adjacent_step_rad': .1}


@pytest.mark.parametrize('names,points', [
    (sampling.NAMES[:-1], [[0.] * 5]),
    (sampling.NAMES, []),
    (sampling.NAMES, [[0.] * 5]),
    (sampling.NAMES, [[np.nan] * 6]),
    (sampling.NAMES, [[3.] * 6]),
    (sampling.NAMES, [[1.] * 6])])
def test_invalid_or_wrong_endpoint_trajectory_refused(names, points):
    with pytest.raises(ValueError):
        sampling.checked_trajectory(names, points, [0.] * 6, [0.] * 6, params())


def test_plan_refuses_production_domain_before_ros_import(monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '0')
    with pytest.raises(RuntimeError, match='isolated'):
        sampling.plan_report({}, {}, '')
    monkeypatch.setenv('ROS_DOMAIN_ID', '78')
    sampling.require_isolated_domain()


def test_two_axis_known_transform_roundtrip_not_hardware_calibration():
    poses = []
    for angles in ([0., 0., 0.], [.1, 0., 0.], [-.1, 0., 0.], [0., .1, 0.], [0., -.1, 0.]):
        t = np.eye(4)
        t[:3, :3] = Rotation.from_euler('xyz', angles).as_matrix()
        poses.append(t)
    result = sampling.synthetic_convention_check(poses)
    assert result['synthetic_not_hardware_calibration']
    assert result['finite_solution']
    assert result['translation_error_m'] < 1e-8
    assert result['rotation_error_deg'] < 1e-5


def test_single_axis_control_does_not_invent_a_valid_calibration():
    transforms = []
    for angle in (0., -.1, .1):
        t = np.eye(4)
        t[:3, :3] = Rotation.from_rotvec([0., angle, 0.]).as_matrix()
        transforms.append(t)
    assert not sampling.synthetic_convention_check(transforms)['finite_solution']


def test_source_has_only_model_state_publisher_and_read_only_services():
    source = Path(sampling.__file__).read_text()
    tree = ast.parse(source)
    publishers = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == 'create_publisher']
    assert len(publishers) == 1
    assert publishers[0].args[1].value == '/joint_states'
    for forbidden in ('ActionClient', '/joint_commands', '/enable_srv', 'JointCtrl', 'DisableArm'):
        assert forbidden not in source


def test_geometry_refuses_urdf_limit_violation_before_fk():
    root = ET.fromstring('<robot>' + ''.join(
        f'<joint name="joint{i}"><limit lower="-.1" upper=".1"/></joint>'
        for i in range(1, 7)) + '</robot>')
    with pytest.raises(ValueError, match='URDF'):
        sampling.geometry_report(root, params(), [0.] * 6, 6.)


@pytest.mark.parametrize('error,expected', [(RuntimeError('planning failed'), 2),
                                         (KeyboardInterrupt(), 130)])
def test_failed_or_interrupted_plan_retains_partial_report(monkeypatch, tmp_path, error, expected):
    output = tmp_path / 'partial.json'
    args = SimpleNamespace(urdf=Path('/fixture/model'), config=Path('/fixture/config'),
                           start_evidence=Path('/fixture/start'), angle_deg=6.,
                           plan=True, output=output)
    inputs = {'model': b'<robot/>', 'config': b'grasp_lift_executor: {ros__parameters: {}}',
              'start': b'{"static_capture":{"q_feedback_rad":[0,0,0,0,0,0]}}'}
    monkeypatch.setenv('ROS_DOMAIN_ID', '78')
    monkeypatch.setattr(sampling.argparse.ArgumentParser, 'parse_args', lambda _: args)
    monkeypatch.setattr(Path, 'read_bytes', lambda path: inputs[path.name])
    monkeypatch.setattr(sampling, 'geometry_report', lambda *_: {
        'mode': 'OFFLINE_REVIEW_NO_HARDWARE_COMMANDS', 'segments': [{}] * 8})

    def failed(report, *_):
        report['live_review'] = {'complete_planning_responses': [{'label': 'completed_segment'}]}
        raise error

    monkeypatch.setattr(sampling, 'plan_report', failed)
    assert sampling.main() == expected
    saved = json.loads(output.read_text())
    assert len(saved['live_review']['complete_planning_responses']) == 1
    assert 'live_review_error' in saved
    assert not saved['live_review'].get('all_segments_planned', False)


def test_output_overwrite_refused_before_inputs_or_ros(monkeypatch, tmp_path):
    args = SimpleNamespace(output=tmp_path / 'existing.json')
    monkeypatch.setattr(sampling.argparse.ArgumentParser, 'parse_args', lambda _: args)
    monkeypatch.setattr(Path, 'exists', lambda _: True)
    with pytest.raises(SystemExit) as error:
        sampling.main()
    assert error.value.code == 2
