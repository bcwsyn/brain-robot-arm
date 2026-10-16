"""Offline package of original observation attempt and scoped link recovery."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile

import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
OUT = REPO/'docs/evidence/piper_board_handeye_20261016/board_resume01'
NAMES = [f'joint{i}' for i in range(1, 7)]


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    observe = ROOT/'observe_reuse_baseline'
    e = load(observe/'execution_session.json')
    assert not e['observe_reached'] and e['all_owned_sources_exited']
    before, after = load(observe/'production_SHA_before.json'), load(observe/'production_SHA_after.json')
    assert before == after and all(sha(Path(p)) == value for p,value in after.items())
    db = next((observe/'motion_witness_bag').glob('*.db3'))
    con = sqlite3.connect('file:'+str(db)+'?mode=ro', uri=True)
    topics = dict(con.execute('SELECT id,name FROM topics'))
    counts = {name: 0 for name in topics.values()}
    trajectories, reasons, states, commands, feedback = [], [], [], [], []
    for topic, stamp, data in con.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
        name = topics[topic];counts[name] += 1
        if name == '/brain_robot_grasp/arm_trajectory':
            m = deserialize_message(data, JointTrajectory)
            trajectories.append({'epoch': stamp/1e9, 'points': len(m.points), 'joint_names': list(m.joint_names),
                                 'start_q': list(m.points[0].positions), 'goal_q': list(m.points[-1].positions),
                                 'duration_s': m.points[-1].time_from_start.sec+m.points[-1].time_from_start.nanosec/1e9})
        elif name in ('/brain_robot_visual_control/reason', '/brain_robot_visual_control/state'):
            row = {'epoch': stamp/1e9, 'value': deserialize_message(data, String).data}
            (reasons if name.endswith('reason') else states).append(row)
        elif name in ('/joint_commands', '/joint_states_feedback'):
            m = deserialize_message(data, JointState);values = dict(zip(m.name, m.position))
            if all(n in values for n in NAMES):
                if name == '/joint_commands':
                    assert 'gripper' not in values
                (commands if name == '/joint_commands' else feedback).append({'epoch': stamp/1e9, 'q': [values[n] for n in NAMES]})
    con.close()
    assert len(trajectories) == 2 and trajectories[0]['points'] == 17
    assert trajectories[1]['start_q'] == trajectories[1]['goal_q']
    assert any(r['value'] == 'FAULT' for r in states)
    assert any(r['value'] == 'PIPER_ADAPTER_DISARMED' for r in reasons)
    assert counts.get('/brain_robot_grasp/gripper_command', 0) == 0
    frozen = load(ROOT/'approved_baseline.json')
    assert frozen == after
    reset = load(ROOT/'usb_reset_recovery.json')
    assert reset['commands'][0]['returncode'] == 0 and reset['received_frames'] == 0
    latest_link = json.loads(reset['commands'][-1]['stdout'])[0]
    result = {'operator_authorization': load(ROOT/'authorization.json'),
              'original_observation_reached': False, 'new_board_sampling_started': False,
              'primary_failure': 'Original CAN feedback ceased during the observation trajectory; original driver suppressed output and adapter timed out/disarmed.',
              'wrapper_final_error_is_cleanup_not_primary_failure': e['error'],
              'initial_preflight_failed_no_driver_or_motion': load(ROOT/'observe/execution_session.json')['error'],
              'baseline_reuse_certificate': load(observe/'baseline_reuse.json'),
              'SDK_thresholds_or_production_guards_changed': False,
              'invocation_initial_partial_low_speed_enable_assertion_failed_then_corrected': True,
              'explanation': 'Only first aggregate SDK low-speed sample was incomplete; following99 samples six enabled. Latest31/3.009s enabled and pose matched verified static baseline within1.7444e-5rad.',
              'bag_counts': counts, 'trajectories': trajectories, 'states': states, 'reasons': reasons,
              'first_command_matches_arm_feedback': e['first_command']['q'] == e['feedback_at_arm']['q'],
              'last_valid_feedback': e['last_received_feedback'], 'last_valid_is_not_current_state': True,
              'actual_feedback_after_trajectory_start_s': feedback[-1]['epoch']-trajectories[0]['epoch'],
              'maximum_last_valid_goal_error_rad': float(np.max(np.abs(np.asarray(feedback[-1]['q'])-trajectories[0]['goal_q']))),
              'controller_hold_trajectory_not_extra_return': True,
              'wrapper_wait_missed_FAULT_because_checked_only_FAILED_string': True,
              'verified_owned_wrapper_SIGINT_for_cleanup_PID': 5492,
              'no_hardware_disable_or_reset_or_gripper': True,
              'all_owned_sources_exited': True,
              'original_frozen_sources_unchanged': True,
              'initial_stalled_RX_packets': 4796101,
              'interface_only_recovery_result': {'first_script_error': 'OSError: [Errno 100] Network is down',
                   'initial_command_results_not_written_due_unhandled_receive_exception': True,
                   'subsequent_UP_stderr_observed': 'RTNETLINK answers: No such device'},
              'one_exact_USB_reset_result': reset,
              'latest_CAN_ifindex': latest_link['ifindex'],
              'latest_CAN_state': latest_link['linkinfo']['info_data']['state'],
              'latest_CAN_RX': latest_link['stats64']['rx']['packets'],
              'current_arm_pose_and_enable_unknown_until_new_frames': True,
              'hardware_CAN_failure_cause_not_proven': True,
              'next_manual_action': 'Only detach and reconnect candleLight USB-CAN1d50:606f to this VM via VMware Removable Devices; do not move/powercycle/disable arm or camera.',
              'no_more_same_software_recovery_loop': True,
              'board_pose_count_unchanged': 2, 'hand_eye_or_TF_deployment': False, 'GitHub_pushed': False}
    put(ROOT/'assessment.json', result)
    selected = ['assessment.json','authorization.json','approved_baseline.json','prepare_existing_invocations.py',
                'reuse_verified_baseline.py','prepare_board_sampling.py','recover_existing_can.py','reset_exact_usb_can.py',
                'usb_reset_recovery.json','package_resume.py']
    for name in selected:
        shutil.copyfile(ROOT/name, OUT/name)
    for label, source in [('failed_preflight', ROOT/'observe'), ('observe_attempt', observe)]:
        destination = OUT/label;destination.mkdir(exist_ok=False)
        for p in source.iterdir():
            if p.is_file() and p.suffix in ('.json','.py'):
                shutil.copyfile(p, destination/p.name)
    members = [p for p in sorted(ROOT.rglob('*')) if p.is_file()]
    entries = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in members]
    archive = OUT/'runtime_originals.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for p in members:
            tar.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
    with tarfile.open(archive) as tar:
        for entry in entries:
            assert hashlib.sha256(tar.extractfile(entry['path']).read()).hexdigest() == entry['sha256']
    put(OUT/'runtime_manifest.json', {'archive_SHA256': sha(archive), 'files': entries, 'all_SHA_readback_verified': True})
    print(json.dumps({'members_verified':len(entries),'archive_bytes':archive.stat().st_size,'bag_counts':counts,
                      'latest_CAN_RX':result['latest_CAN_RX'],'observation_reached':False},indent=2))


if __name__ == '__main__':
    main()
