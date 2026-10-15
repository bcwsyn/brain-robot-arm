"""Synthetic message/child-process fixtures only; no ROS initialization or devices."""
import ast
from collections import deque
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import collect_static_rgbd as collector
import capture_calibration_session as session
from wait_calibration_ready import wait_ready


def message(ns):
    return NS(header=NS(stamp=NS(sec=ns//10**9, nanosec=ns%10**9)))


def test_diagnostics_keep_actual_source_and_receipt_clocks_bounded():
    trace = collector.ReceiptDiagnostics()
    original = message(1_000_000_000)
    for n in range(150):
        trace.observe('q', original, 2_000_000_000+n, 3_000_000_000+n, 4_000_000_000+n)
    result = trace.snapshot()
    assert len(result['recent_receipts']) == 128
    assert result['latest_by_topic']['q']['source_stamp_ns'] == '1000000000'
    assert result['latest_by_topic']['q']['source_age_at_receipt_ns'] == 1_000_000_149
    assert result['latest_by_topic']['q']['local_interarrival_ns'] == 1
    assert original.header.stamp.sec == 1


@pytest.mark.parametrize('elapsed,stamp,reason,lost', [
    (2.9,None,'initialization_grace',False),
    (3.,None,'missing_feedback_history',True),
    (5.,9_500_000_000,'fresh',False),
    (5.,9_499_999_999,'stale_feedback_source_stamp',True),
    (5.,10_000_000_001,'future_feedback_source_stamp',True)])
def test_failure_category_explains_original_predicate_without_changing_it(elapsed,stamp,reason,lost):
    history = deque([] if stamp is None else [(stamp,[0.]*6)])
    result = collector.feedback_stop_diagnostic(history,10_000_000_000,elapsed,11,12,
                                                collector.ReceiptDiagnostics())
    assert result['category'] == reason and result['original_feedback_lost'] is lost
    assert result['decision_ros_ns'] == '10000000000'
    assert result['decision_wall_ns'] == '11' and result['decision_monotonic_ns'] == '12'


def test_invalid_source_stamp_is_visible_not_repaired():
    trace = collector.ReceiptDiagnostics()
    trace.observe('rgb',message(0),123,124,125)
    row = trace.latest['rgb']
    assert row['source_stamp_ns'] is None and row['timestamp_error']=='zero timestamp'


def test_existing_acceptance_functions_and_frame_saving_callback_unchanged():
    repo = Path(__file__).resolve().parents[5]
    for filename, names in [
        ('collect_static_rgbd.py',['checked_packet','feedback_lost','settled_feedback',
                                  'stamp_ns','joint_positions','full_camera_info','synchronizer','matched']),
        ('calibration_readonly_feedback.py',['feedback_values','install_receive_parser'])]:
        path=Path(__file__).with_name(filename)
        rel=path.relative_to(repo).as_posix()
        old=subprocess.check_output(['git','show',f'469dc08:{rel}'],cwd=repo,text=True)
        before={n.name:n for n in ast.walk(ast.parse(old)) if isinstance(n,ast.FunctionDef)}
        after={n.name:n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef)}
        for name in names:
            assert ast.dump(before[name]) == ast.dump(after[name]), name


def test_fixed_commands_only_allow_stationary_sources_and_original_rules(tmp_path):
    commands = session.commands(tmp_path)
    assert set(commands)=={'bridge','ready','depth','color','capture','factory'}
    assert '55.,60,settle_s=3.,stop_on_feedback_loss=True,max_bytes=64<<20' in commands['capture'][2]
    assert 'sys.path.insert' in commands['capture'][2]
    assert session.capture_window(20.) == 55.
    assert session.capture_window(30.) == 47.
    for filename in ['wait_calibration_ready.py','capture_calibration_session.py']:
        tree=ast.parse(Path(__file__).with_name(filename).read_text())
        attributes={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        assert not attributes & {'create_client','create_publisher','send_goal_async','EnableArm','DisableArm','ResetPiper'}


@pytest.mark.parametrize('duration',[0,21,float('nan')])
def test_readiness_invalid_bounds_refused_without_ros(tmp_path,duration):
    with pytest.raises(ValueError):
        wait_ready(tmp_path/'ready.json',tmp_path/'listening.json',duration)


def test_readiness_existing_evidence_refused_without_ros(tmp_path):
    with pytest.raises(FileExistsError):
        wait_ready(tmp_path,tmp_path/'listening.json')


class FakeClock:
    def __init__(self): self.t=0.
    def monotonic(self): return self.t
    def monotonic_ns(self): return int(self.t*1e9)
    def time(self): return 1_000_000.+self.t
    def sleep(self,seconds): self.t+=seconds


def fake_session(monkeypatch,tmp_path,ready=True,ready_delay=3.,capture_delay=1.,frames=60,can_ok=True):
    clock, children = FakeClock(), []
    monkeypatch.setattr(session,'time',clock)
    monkeypatch.setattr(session.subprocess,'run',lambda *a,**k:NS(returncode=0,stdout='imports verified'))
    count=[0]
    def can():
        count[0]+=1
        return {'up':can_ok,'state':'ERROR-ACTIVE','rx':count[0],'tx':0}
    monkeypatch.setattr(session,'read_can',can)
    class Child:
        def __init__(self,argv,**kwargs):
            self.argv,self.begin,self.returncode=argv,clock.t,None
            self.pid=10000+len(children)
            if 'calibration_readonly_feedback.py' in ' '.join(argv): self.name='bridge'
            elif 'wait_calibration_ready.py' in ' '.join(argv): self.name='ready'
            elif argv[:3]==['ros2','launch','astra_camera']: self.name='depth'
            elif argv[0].endswith('/cam2image'): self.name='color'
            elif '-c' in argv: self.name='capture'
            else: self.name='factory'
            children.append(self)
            if self.name=='ready': (tmp_path/'listening.json').write_text('{}')
            if self.name=='depth':
                kwargs['stdout'].write(b'SENSOR_DEPTH is started\n');kwargs['stdout'].flush()
        def poll(self):
            if self.returncode is not None:return self.returncode
            elapsed=clock.t-self.begin
            if self.name=='ready' and elapsed>=ready_delay:
                (tmp_path/'readiness.json').write_text(json.dumps({'ready':ready}))
                self.returncode=0 if ready else 2
            elif self.name=='capture' and elapsed>=capture_delay:
                folder=tmp_path/'capture';folder.mkdir()
                (folder/'summary.json').write_text(json.dumps({'saved_frames':frames,
                    'stop_reason':None if frames==60 else 'feedback_lost'}))
                self.returncode=0 if frames==60 else 2
            elif self.name=='factory' and elapsed>=.1:
                self.returncode=0
            return self.returncode
        def wait(self,timeout):
            assert self.poll() is not None
            return self.returncode
    monkeypatch.setattr(session.subprocess,'Popen',Child)
    def kill(pid,sig):
        child=next(c for c in children if c.pid==pid)
        child.returncode=-int(sig)
    monkeypatch.setattr(session.os,'killpg',kill)
    return children,clock


def test_success_starts_collector_only_after_real_readiness_fixture(monkeypatch,tmp_path):
    root=tmp_path/'run'
    children,_=fake_session(monkeypatch,root)
    assert session.run(root)==0
    report=json.loads((root/'execution.json').read_text())
    assert report['ready'] and report['raw_acquisition_complete']
    assert not report['quality_or_calibration_accepted']
    ready_child=next(c for c in children if c.name=='ready')
    capture=next(c for c in children if c.name=='capture')
    assert capture.begin>=ready_child.begin+3.
    assert [c.name for c in children].count('color')==1
    assert report['all_owned_sources_exited'] and report['within_camera_budget']


def test_readiness_failure_never_starts_formal_capture(monkeypatch,tmp_path):
    root=tmp_path/'run';children,_=fake_session(monkeypatch,root,ready=False)
    assert session.run(root)==2
    assert not any(c.name=='capture' for c in children)
    report=json.loads((root/'execution.json').read_text())
    assert not report['formal_capture_started'] and report['all_owned_sources_exited']


def test_original_feedback_loss_is_preserved_not_retried(monkeypatch,tmp_path):
    root=tmp_path/'run';children,_=fake_session(monkeypatch,root,frames=0)
    assert session.run(root)==2
    report=json.loads((root/'execution.json').read_text())
    assert report['capture_summary']['stop_reason']=='feedback_lost'
    assert report['capture_summary']['saved_frames']==0
    assert [c.name for c in children].count('capture')==1


def test_camera_timeout_stops_owned_sources_without_automatic_reopen(monkeypatch,tmp_path):
    root=tmp_path/'run';children,clock=fake_session(monkeypatch,root,capture_delay=1000.)
    assert session.run(root)==2
    report=json.loads((root/'execution.json').read_text())
    assert 'deadline' in report['error']
    assert report['all_owned_sources_exited'] and clock.t<80.
    assert len([c for c in children if c.name=='color'])==1


def test_down_can_opens_no_child_or_camera(monkeypatch,tmp_path):
    root=tmp_path/'run';children,_=fake_session(monkeypatch,root,can_ok=False)
    assert session.run(root)==2 and not children


def test_existing_session_refused_before_preflight(monkeypatch,tmp_path):
    monkeypatch.setattr(session.subprocess,'run',lambda *a,**k:pytest.fail('preflight before overwrite refusal'))
    with pytest.raises(FileExistsError):session.run(tmp_path)
