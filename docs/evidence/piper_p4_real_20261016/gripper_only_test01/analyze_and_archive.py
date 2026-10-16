"""Read existing finite evidence only; no ROS/device/control access.

Generate exact-byte archival copies (gzip for streams), plus honest summaries.
Run after the owned physical control processes have exited.
"""
import argparse
import collections
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def summarize(base):
    events = [json.loads(line) for line in (base/'real_record/events.jsonl').open()]
    states = [r for r in events if r['topic_key'] == 'grasp_state']
    opening = next(r['receipt_epoch'] for r in states
                   if r['message']['data'] == 'P4_GRIPPER_TEST_OPENING')
    closing = next((r['receipt_epoch'] for r in states
                    if r['message']['data'] == 'P4_GRIPPER_TEST_CLOSING'), None)
    frames = [r for r in events if r['topic_key'] == 'actual_gripper_frame']
    active = [r for r in events if r['receipt_epoch'] >= opening]
    joints = [r['message']['position'][:6] for r in active
              if r['topic_key'] == 'joint_states_feedback']
    trajectories = [r for r in events if r['topic_key'] == 'arm_trajectory']
    holds = []
    for r in trajectories:
        points = r['message']['points']
        holds.append(bool(points) and all(p['positions'] == points[0]['positions']
                                        for p in points))
    result = {
        'states': states,
        'diagnostics': [r for r in events if r['topic_key'] == 'grasp_diagnostic'],
        'topic_counts': dict(collections.Counter(r['topic_key'] for r in events)),
        'actual_gripper_first_mm': frames[0]['message']['position'][0]*1000,
        'actual_gripper_max_mm': max(r['message']['position'][0]*1000 for r in frames),
        'actual_gripper_last_mm': frames[-1]['message']['position'][0]*1000,
        'joint_spread_rad_from_test_opening': [max(v)-min(v) for v in zip(*joints)],
        'arm_trajectory_count': len(trajectories),
        'arm_trajectory_each_is_identical_position_hold': holds,
        'actual_status_counts': dict(collections.Counter(
            r['message']['data'] for r in events if r['topic_key'] == 'gripper_status')),
        'execution': json.loads((base/'actual_execution.json').read_text()),
        'closing_two_second_bins': [],
    }
    if closing:
        terminal = states[-1]['receipt_epoch']
        result['closing_duration_s'] = terminal-closing
        for i in range(0, int(terminal-closing)+1, 2):
            f = [r for r in frames if closing+i <= r['receipt_epoch'] <
                 min(closing+i+2, terminal)]
            refs = [r['message']['position'][0]*1000 for r in events
                    if r['topic_key'] == 'gripper_command' and
                    closing+i <= r['receipt_epoch'] < min(closing+i+2, terminal)]
            if f:
                stamps = [r['message']['header']['stamp']['sec'] +
                          r['message']['header']['stamp']['nanosec']/1e9 for r in f]
                result['closing_two_second_bins'].append({
                    'start_after_closing_s': i, 'actual_frames': len(f),
                    'source_span_s': stamps[-1]-stamps[0],
                    'actual_first_last_mm': [f[0]['message']['position'][0]*1000,
                                             f[-1]['message']['position'][0]*1000],
                    'reference_min_max_mm': [min(refs), max(refs)] if refs else None,
                    'effort_min_max_Nm': [min(r['message']['effort'][0] for r in f),
                                          max(r['message']['effort'][0] for r in f)],
                    'max_receipt_minus_source_s': max(r['receipt_epoch']-t
                                                     for r, t in zip(f, stamps))})
    driver = (base/'onekey_logs/piper_driver.log').read_text()
    calls = re.findall(r'Calling GripperCtrl: angle=(\d+) effort=(\d+) code=([^ ]+) set_zero=(\S+)', driver)
    result['driver'] = {
        'gripper_call_count': len(calls),
        'nominal_effort_counts': sorted(set(int(c[1]) for c in calls)),
        'last_calls': calls[-5:],
        'suppressed_by_output_gate': driver.count('suppressed by output gate'),
        'not_direct_bus_transmit_confirmation': True}
    # CAN sockets do not necessarily receive another local socket's TX frames.
    # Absence of 0x159 in candump does NOT establish that driver sent no command.
    can_path = base/'onekey_logs/gripper_can.log'
    ids = collections.Counter()
    frames159 = []
    for line in can_path.open():
        m = re.match(r'\(([^)]+)\) can0 ([0-9A-Fa-f]+)#([0-9A-Fa-f]+)', line)
        if not m:
            continue
        ids[m[2].upper()] += 1
        if m[2].upper() == '159':
            frames159.append({'epoch': float(m[1]), 'payload_hex': m[3]})
    result['CAN_receive_log'] = {'id_counts': dict(ids), 'observed_159': frames159,
        'limitations': 'Receive socket log, not independent TX acknowledgement; zero observed159 is inconclusive about local TX.'}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    report = {'baseline_control_commit': '4037724',
              'HEAD_before_archive': subprocess.check_output(
                  ['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
              'first_attempt': summarize(ROOT), 'retry01': summarize(ROOT/'retry01'),
              'physical_grasp_success': False, 'arm_target_candidate_adopted': False,
              'no_new_physical_experiment_for_this_analysis': True}
    save(ROOT/'actual_analysis.json', report)
    source_pairs = {
        'brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp':
            '/home/johnwick/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp',
        'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py':
            '/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py',
        'brain_robot_arm/scripts/start_brain_robot_cube_real.sh':
            '/home/johnwick/start_brain_robot_cube_real.sh'}
    deployment = {'source_pairs': [], 'protected_sources': []}
    for rel, active in source_pairs.items():
        row = {'canonical': rel, 'active': active,
               'canonical_sha256': sha((REPO/rel).read_bytes()),
               'active_sha256': sha(Path(active).read_bytes())}
        assert row['canonical_sha256'] == row['active_sha256']
        deployment['source_pairs'].append(row)
    protected = [
        ('brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml',
         '/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'),
        ('brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml',
         '/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'),
        ('brain_robot_arm/piper_ws/src/brain_robot_moveit/scripts/piper_jog_adapter.py',
         '/home/johnwick/piper_ws/src/brain_robot_moveit/scripts/piper_jog_adapter.py')]
    # Discover canonical adapter rather than inventing an alternative path.
    adapter = list(REPO.glob('brain_robot_arm/piper_ws/src/**/piper_jog_adapter.py'))
    assert len(adapter) == 1
    protected[-1] = (str(adapter[0].relative_to(REPO)),
                    str(Path('/home/johnwick/piper_ws/src') /
                        adapter[0].relative_to(REPO/'brain_robot_arm/piper_ws/src')))
    for rel, active in protected:
        before = subprocess.check_output(['git', '-C', str(REPO), 'show', '4037724:'+rel])
        canonical = (REPO/rel).read_bytes()
        live = Path(active).read_bytes()
        assert before == canonical == live, rel
        deployment['protected_sources'].append({'path': rel, 'active': active,
                                                'unchanged_sha256': sha(live)})
    driver = Path('/home/johnwick/piper_ros/build/piper/piper/piper_ctrl_single_node.py')
    deployment['driver_sha256'] = sha(driver.read_bytes())
    assert deployment['driver_sha256'] == '3a79681fd372e04bfc2b16eac14595c318abfaa89af1ac35d98243eb1192e45a'
    binary = Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
    deployment['binary_sha256'] = sha(binary.read_bytes())
    assert deployment['binary_sha256'] == 'c3cf4eaac062300a590e14a20a70e396d4baee9b5c5bc3ac36fafd30e87867d1'
    save(ROOT/'final_deployment.json', deployment)
    args.archive.mkdir(parents=True, exist_ok=False)
    manifest = []
    for src in sorted(ROOT.rglob('*')):
        if not src.is_file() or 'before' in src.relative_to(ROOT).parts:
            continue
        if '__pycache__' in src.parts or src.suffix in ('.pyc', '.bin'):
            continue
        rel = src.relative_to(ROOT)
        original = src.read_bytes()
        compress = src.suffix == '.jsonl' or src.name == 'gripper_can.log'
        out_rel = Path(str(rel)+'.gz') if compress else (
            rel.with_suffix('.txt') if src.suffix == '.log' else rel)
        out = args.archive/out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = gzip.compress(original, mtime=0) if compress else original
        out.write_bytes(payload)
        recovered = gzip.decompress(out.read_bytes()) if compress else out.read_bytes()
        assert recovered == original
        manifest.append({'archive_path': str(out_rel), 'original_runtime_path': str(src),
                         'raw_bytes': len(original), 'raw_sha256': sha(original),
                         'archive_bytes': len(payload), 'archive_sha256': sha(payload),
                         'gzip_exact_raw_bytes': compress})
    save(args.archive/'manifest.json', {'files': manifest,
        'excluded': 'before/ backups and ELF binaries retained only in runtime; no files deleted',
        'files_count': len(manifest), 'archive_bytes': sum(r['archive_bytes'] for r in manifest)})
    print(json.dumps({'files': len(manifest),
                      'archive_bytes': sum(r['archive_bytes'] for r in manifest),
                      'retry': {k: report['retry01'][k] for k in (
                          'actual_gripper_max_mm', 'actual_gripper_last_mm',
                          'joint_spread_rad_from_test_opening', 'arm_trajectory_count')},
                      'binary_sha256': deployment['binary_sha256']}, indent=2))


if __name__ == '__main__':
    main()
