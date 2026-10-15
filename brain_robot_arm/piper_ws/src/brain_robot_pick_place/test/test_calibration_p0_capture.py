"""Bounded P0 orchestration tests; injected inputs, no ROS/CAN devices."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import subprocess

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import collect_calibration_p0 as p0
from collect_static_rgbd import feedback_lost


@pytest.mark.parametrize('changes', [{'up': False}, {'state': 'BUS-OFF'}, {'state': 'STOPPED'}, {'rx': 10}])
def test_only_existing_active_receiving_link_passes(changes):
    before = {'up': True, 'state': 'ERROR-ACTIVE', 'rx': 10, 'tx': 0}
    after = dict(before, rx=20, **{k: v for k, v in changes.items() if k != 'rx'})
    if 'rx' in changes: after['rx'] = changes['rx']
    assert not p0.healthy_window(before, after)
    assert p0.healthy_window(before, dict(before, rx=21))


def test_loss_is_not_refreshed_by_timer_or_old_receipt():
    assert not feedback_lost([], 10_000_000_000, 2.)
    assert feedback_lost([], 10_000_000_000, 3.)
    assert not feedback_lost([(9_600_000_000, [0.] * 6)], 10_000_000_000, 4.)
    assert feedback_lost([(9_000_000_000, [0.] * 6)], 10_000_000_000, 4.)


@pytest.fixture
def config():
    return Path(__file__).resolve().parents[5] / 'docs/evidence/piper_calibration_20261014/pair01/detector_config.yaml'


def fake_capture(folder, seconds, frames, **kwargs):
    assert kwargs == {'settle_s': 3., 'stop_on_feedback_loss': True, 'max_bytes': 64 << 20}
    folder.mkdir()
    (folder / 'observer.jsonl').write_text(''.join(json.dumps({'snapshot': n}) + '\n' for n in range(frames)))
    (folder / 'summary.json').write_text(json.dumps({'stop_reason': None, 'saved_frames': frames}))
    return 0


def fake_review(row, params, camera):
    return ({'snapshot': row['snapshot'], 'face_quality_candidate': False,
             'good_top_frame': False, 'top_identity_confirmed': False,
             'actual_q_rad': [0.] * 6}, None)


def increasing_can():
    increasing_can.counter += 1
    return {'up': True, 'state': 'ERROR-ACTIVE', 'rx': increasing_can.counter, 'tx': 0}
increasing_can.counter = 0


def test_bad_quality_stops_after_two_batches_and_preserves_every_frame(tmp_path, config, monkeypatch):
    monkeypatch.setattr(p0.time, 'sleep', lambda _: None)
    output = tmp_path / 'new'
    rc = p0.capture(output, config, batches=2, frames=60, duration_s=30,
                    can_reader=increasing_can, collector=fake_capture, reviewer=fake_review)
    report = json.loads((output / 'p0_report.json').read_text())
    assert rc == 2 and len(report['frames']) == 120
    assert report['stop_reason'] == 'bounded_replenishment_exhausted'
    assert len(list(output.glob('batch_*/observer.jsonl'))) == 2


def test_twenty_provisional_faces_stop_capture_but_do_not_pass_top_review(tmp_path, config, monkeypatch):
    monkeypatch.setattr(p0.time, 'sleep', lambda _: None)
    def provisional(*args):
        frame, _ = fake_review(*args)
        return dict(frame, face_quality_candidate=True), None
    output = tmp_path / 'new'
    assert p0.capture(output, config, can_reader=increasing_can,
                      collector=fake_capture, reviewer=provisional) == 2
    report = json.loads((output / 'p0_report.json').read_text())
    assert len(report['batches']) == 1 and report['summary']['good_top_frames'] == 0
    assert report['stop_reason'] == 'twenty_face_candidates_pending_top_review'


def test_down_link_never_calls_collector(tmp_path, config, monkeypatch):
    monkeypatch.setattr(p0.time, 'sleep', lambda _: None)
    def never(*args, **kwargs):
        raise AssertionError('must not collect')
    output = tmp_path / 'new'
    p0.capture(output, config, can_reader=lambda: {'up': False, 'state': 'STOPPED', 'rx': 0, 'tx': 0},
               collector=never)
    assert not list(output.glob('batch_*'))


@pytest.mark.parametrize('options', [{'batches': 3}, {'frames': 61}, {'duration_s': float('nan')}, {'duration_s': 121}])
def test_invalid_bounds_rejected_before_hardware(tmp_path, config, options):
    with pytest.raises(ValueError):
        p0.capture(tmp_path / 'new', config, **options)


def test_existing_evidence_refused_and_no_control_interfaces(tmp_path, config):
    with pytest.raises(FileExistsError):
        p0.capture(tmp_path, config)
    tree = ast.parse(Path(p0.__file__).read_text())
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {'create_publisher', 'create_client', 'send_goal_async', 'EnableArm', 'ResetPiper'}


def test_exposure_is_get_only_batch_metadata_not_guessed_lux(monkeypatch):
    seen = []
    def read(command, **kwargs):
        seen.append(command)
        assert kwargs['timeout'] == 3
        return SimpleNamespace(stdout='gain: value=0\nauto_exposure: value=3\nexposure_time_absolute: value=157 flags=inactive\n')
    monkeypatch.setattr(p0.subprocess, 'run', read)
    result = p0.read_exposure()
    assert seen == [['v4l2-ctl', '--device', '/dev/video0', '--list-ctrls']]
    assert result['error'] is None and 'inactive' in result['controls_raw']
    assert 'not synchronized' in result['scope']


def test_unavailable_exposure_stays_null_and_does_not_change_device(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('v4l2-ctl', 3)
    monkeypatch.setattr(p0.subprocess, 'run', fail)
    result = p0.read_exposure()
    assert result['controls_raw'] is None and 'TimeoutExpired' in result['error']
