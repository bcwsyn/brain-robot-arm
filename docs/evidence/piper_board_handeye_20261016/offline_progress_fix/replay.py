#!/usr/bin/env python3
"""Offline counterfactual command replay; no Node, CAN, or device access."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace

from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
REL = 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py'
PREVIOUS = HERE.parent / 'attempt01'
NAMES = [f'joint{i}' for i in range(1, 7)]


def methods(source):
    cls = next(n for n in ast.parse(source).body
               if isinstance(n, ast.ClassDef) and n.name == 'PiperJogAdapter')
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def load_apply(source):
    node = methods(source)['_apply_trajectory']
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<offline adapter method>', 'exec'), namespace)
    return namespace['_apply_trajectory']


def dummy(trajectory, start, q):
    return SimpleNamespace(
        trajectory=trajectory, trajectory_start=start, max_velocity=.189,
        joint_names=NAMES, joint_min=[-1.5, -.3, -1.4, -.8, -1.2, -3.14159265359],
        joint_max=[1.5, 3.14159265359, .4, .8, 1.22108, 3.14159265359],
        trajectory_start_tolerance=.1, command_timeout_s=.2, joint_state_timeout_s=25.,
        last_state_time=start, positions=dict(zip(NAMES, q)), targets=dict(zip(NAMES, q)))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    canonical = (REPO / REL).read_text()
    baseline = subprocess.check_output(['git', 'show', '20fcd30:' + REL], cwd=REPO).decode()
    deployed_path = Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
    deployed = deployed_path.read_text()
    before, after = methods(baseline), methods(canonical)
    assert before.keys() == after.keys()
    changed = [name for name in before if ast.dump(before[name]) != ast.dump(after[name])]
    assert changed == ['_apply_trajectory']
    original_manifest = json.loads((PREVIOUS / 'evidence_manifest.json').read_text())
    for entry in original_manifest['files']:
        assert sha((PREVIOUS / entry['path']).read_bytes()) == entry['sha256']
    frozen = json.loads((REPO / 'docs/evidence/piper_calibration_p1_20261015/'
                        'board_open_only/production_SHA_before.json').read_text())
    frozen_results = {}
    for path, expected in frozen.items():
        actual = sha(Path(path).read_bytes())
        frozen_results[path] = {'before': expected, 'after': actual,
                                'authorized_candidate_exception': path == str(REPO / REL)}
        if path != str(REPO / REL):
            assert actual == expected
    archive = PREVIOUS / 'closed_sessions.tar.gz'
    with tempfile.TemporaryDirectory(prefix='piper_offline_replay_') as temporary:
        db = Path(temporary) / 'recorded.db3'
        with tarfile.open(archive) as tar:
            member = tar.extractfile('run03/motion_bag/motion_bag_0.db3')
            db.write_bytes(member.read())
        connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
        topics = dict(connection.execute('SELECT id,name FROM topics'))
        events = []
        for topic, stamp, data in connection.execute(
                'SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
            name = topics[topic]
            if name == '/brain_robot_grasp/arm_trajectory':
                events.append((stamp / 1e9, 'trajectory', deserialize_message(data, JointTrajectory)))
            elif name in ('/joint_states_feedback', '/joint_commands'):
                msg = deserialize_message(data, JointState)
                values = dict(zip(msg.name, msg.position))
                if all(n in values for n in NAMES):
                    events.append((stamp / 1e9, 'feedback' if name.endswith('feedback') else 'command',
                                   [values[n] for n in NAMES]))
        connection.close()
    assert sum(kind == 'trajectory' for _, kind, _ in events) == 2
    summaries = {}
    for label, source in [('deployed', deployed), ('canonical_before', baseline), ('candidate', canonical)]:
        apply = load_apply(source)
        count = 0
        q = None
        state_time = None
        previous_tick = None
        outputs = []
        for stamp, kind, value in events:
            if kind == 'feedback':
                q = value
                state_time = stamp
            elif kind == 'trajectory':
                count += 1
                adapter = dummy(value, stamp, q)
                goal = value.points[-1].positions[3]
                outputs = []
                previous_tick = stamp
            elif kind == 'command' and count == 2:
                adapter.positions = dict(zip(NAMES, q))
                adapter.last_state_time = state_time
                dt = max(0., min(stamp - previous_tick, .1))
                previous_tick = stamp
                active = apply(adapter, stamp, dt)
                outputs.append(adapter.targets['joint4'])
        summaries[label] = {'calls': len(outputs), 'goal_J4_rad': goal,
                            'command_min_rad': min(outputs), 'command_max_rad': max(outputs),
                            'last_command_rad': outputs[-1], 'trajectory_active_at_end': active,
                            'closest_command_to_goal_rad': min(abs(v - goal) for v in outputs)}
    assert summaries['candidate']['closest_command_to_goal_rad'] < 1e-12
    assert summaries['deployed']['closest_command_to_goal_rad'] > .04
    assert summaries['candidate']['trajectory_active_at_end']  # Recorded actual feedback never arrived.
    endpoint = JointTrajectory(joint_names=NAMES)
    from trajectory_msgs.msg import JointTrajectoryPoint
    endpoint.points = [JointTrajectoryPoint(positions=[0., 0., 0., -.074293996, 0., 0.])]
    synthetic = {}
    for label, source in [('deployed', deployed), ('canonical_before', baseline), ('candidate', canonical)]:
        adapter = dummy(endpoint, 0., [0.] * 6)
        output = []
        for i in range(50):
            now = (i + 1) * .02
            adapter.last_state_time = now
            load_apply_method = load_apply(source) if i == 0 else load_apply_method
            active = load_apply_method(adapter, now, .02)
            output.append(adapter.targets['joint4'])
        synthetic[label] = {'last_command_rad': output[-1], 'active': active}
    assert abs(synthetic['candidate']['last_command_rad'] + .074293996) < 1e-12
    report = {'offline_only': True, 'ROS_initialized': False, 'hardware_accessed': False,
              'deployed_changed': False, 'changed_method_only': changed,
              'original_evidence_files_SHA_verified': len(original_manifest['files']),
              'archive_SHA256': sha(archive.read_bytes()), 'frozen_sources': frozen_results,
              'recorded_return_counterfactual': summaries, 'synthetic_constant_feedback': synthetic,
              'limitations': ['Bag receipt time approximates callback time; not a bit-exact runtime replay.',
                              'Old actual feedback is held fixed; changed command does not prove physical response.',
                              'Candidate includes earlier fef28d6 takeover changes, not deployed or hardware verified.',
                              'Original arm sampling remains 2/10 poses; no new hand-eye solution.']}
    (HERE / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
