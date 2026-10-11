"""Collector-only regression: no devices, publishers, services or motion."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collect_static_rgbd.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def message(stamp, **fields):
    return NS(header=NS(stamp=NS(sec=stamp // 1_000_000_000, nanosec=stamp % 1_000_000_000),
                        frame_id='camera_depth_optical_frame'), **fields)


def packet():
    return [message(10_000_000_000, width=320, height=240),
            message(10_020_000_000, width=640, height=400, encoding='16UC1'),
            message(10_020_000_000, width=640, height=400, k=[478., 0., 326., 0., 478., 200., 0., 0., 1.]),
            message(10_030_000_000, name=list(collector.NAMES)[::-1], position=[6., 5., 4., 3., 2., 1.])]


def test_timestamp_pairing_preserves_named_joints_and_records_span():
    result = collector.checked_packet(*packet(), 10_100_000_000)
    assert result['stamp_span_s'] == pytest.approx(.03)
    assert result['oldest_age_s'] == pytest.approx(.1)
    assert result['q_rad'] == [1., 2., 3., 4., 5., 6.]


@pytest.mark.parametrize('fault', ['old', 'future', 'span', 'info_stamp', 'size', 'frame', 'encoding', 'k', 'nan', 'missing', 'duplicate', 'zero'])
def test_bad_packet_refused_without_loosening_threshold(fault):
    data = packet()
    now = 10_100_000_000
    if fault == 'old': now = 11_000_000_000
    elif fault == 'future': now = 9_900_000_000
    elif fault == 'span': data[0].header.stamp.nanosec = 200_000_000
    elif fault == 'info_stamp': data[2].header.stamp.nanosec += 1
    elif fault == 'size': data[2].height += 1
    elif fault == 'frame': data[2].header.frame_id = 'wrong'
    elif fault == 'encoding': data[1].encoding = '32FC1'
    elif fault == 'k': data[2].k[0] = float('nan')
    elif fault == 'nan': data[3].position[0] = float('nan')
    elif fault == 'missing': data[3].name[0] = 'not_a_joint'
    elif fault == 'duplicate': data[3].name[0] = data[3].name[1]
    elif fault == 'zero': data[0].header.stamp.sec = 0
    with pytest.raises((ValueError, KeyError)):
        collector.checked_packet(*data, now)


def test_settle_requires_time_window_and_actual_static_positions():
    q = [0.] * 6
    history = [(stamp, q.copy()) for stamp in range(10_000_000_000, 10_301_000_000, 10_000_000)]
    assert collector.settled_feedback(history, q, 10_300_000_000)
    assert not collector.settled_feedback(history[-2:], q, 10_300_000_000)
    history[15][1][4] = .002
    assert not collector.settled_feedback(history, q, 10_300_000_000)


def test_official_synchronizer_uses_buffered_frames_not_latest():
    filters = pytest.importorskip('message_filters')
    from sensor_msgs.msg import CameraInfo, Image, JointState
    sources = [filters.SimpleFilter() for _ in range(4)]
    sync = collector.synchronizer(sources)
    paired = []
    sync.registerCallback(lambda *messages: paired.append([collector.stamp_ns(m) for m in messages]))

    def send(index, ns):
        msg = (Image, Image, CameraInfo, JointState)[index]()
        msg.header.stamp.sec = ns // 1_000_000_000
        msg.header.stamp.nanosec = ns % 1_000_000_000
        sources[index].signalMessage(msg)

    for index, ns in [(1, 10_020_000_000), (2, 10_020_000_000), (3, 10_030_000_000),
                      (1, 10_160_000_000), (2, 10_160_000_000), (3, 10_170_000_000)]:
        send(index, ns)
    send(0, 10_000_000_000)
    assert paired == [[10_000_000_000, 10_020_000_000, 10_020_000_000, 10_030_000_000]]
    # The old latest tuple would exceed the unchanged 120ms limit.
    assert .170 > collector.SLOP_NS / 1e9
    send(0, 11_000_000_000)
    assert len(paired) == 1


def test_existing_evidence_directory_is_refused_before_node_init(tmp_path, monkeypatch):
    ros = pytest.importorskip('rclpy')
    initialized = []
    monkeypatch.setattr(ros, 'init', lambda: initialized.append(True))
    with pytest.raises(FileExistsError):
        collector.collect(tmp_path, 1, 1)
    assert initialized == []


@pytest.mark.parametrize('options', [['--duration-s', 'nan'], ['--duration-s', '121'],
                                   ['--frames', '0'], ['--frames', '61']])
def test_unbounded_or_invalid_cli_refused_without_ros(options, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'argv', ['collector', '--output', '/unused'] + options)
    monkeypatch.setattr(collector, 'collect', lambda *_: pytest.fail('invalid CLI initialized collection'))
    with pytest.raises(SystemExit) as error:
        collector.main()
    assert error.value.code == 2


def test_collector_has_no_motion_or_service_interfaces():
    tree = ast.parse(Path(collector.__file__).read_text())
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {'create_publisher', 'create_client', 'call_async', 'send_goal_async',
                        'JointCtrl', 'GripperCtrl', 'EnableArm', 'DisableArm', 'ResetPiper'}
    assert collector.TOPICS[-1] == '/joint_states_feedback'
    assert '/joint_commands' not in collector.TOPICS
