"""Offline audit of raw/SDK receive evidence; no new device access."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
OUT = REPO / 'docs/evidence/piper_board_handeye_20261016/speed_raw_audit01'
sys.path[:0] = [str(REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'),
               '/home/johnwick/.local/lib/python3.10/site-packages']
from collect_calibration_sdk import summarize
import can
from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
from piper_sdk.piper_msgs.msg_v2 import PiperMessage


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    first = load(ROOT / 'raw_assessment.json')
    concurrent = load(ROOT / 'concurrent/raw_assessment.json')
    sdk = load(ROOT / 'sdk_concurrent.json')
    all_samples = sdk['samples']
    passing = []
    for i in range(len(all_samples)):
        for j in range(i+30, len(all_samples)+1):
            quality = summarize(all_samples[i:j])
            if quality['static_three_seconds_and_thirty_samples']:
                passing.append({'start_index_inclusive': i, 'end_index_exclusive': j, 'original_quality': quality})
    assert passing
    longest = max(passing, key=lambda window: window['original_quality']['span_s'])
    parser = C_PiperParserV2()
    frames = [json.loads(line) for line in (ROOT / 'concurrent/raw_receive.jsonl').read_text().splitlines()]
    raw_status = []
    for canid in [0x2a1, 0x2a8, *range(0x261, 0x267)]:
        row = next(r for r in reversed(frames) if r['can_id'] == hex(canid))
        msg = PiperMessage()
        assert parser.DecodeMessage(can.Message(arbitration_id=canid, data=bytes.fromhex(row['data_hex']), is_extended_id=False), msg)
        if canid == 0x2a1:
            status = msg.arm_status_msgs
            assert status.ctrl_mode == 0 and status.arm_status == 0 and status.err_code == 0
        elif canid == 0x2a8:
            status = msg.gripper_feedback
        else:
            status = getattr(msg, 'arm_low_spd_feedback_'+str(canid-0x260))
            assert not status.foc_status.driver_enable_status
        raw_status.append({'raw': row, 'installed_SDK_decode_text': str(status)})
    before = load(REPO / 'docs/evidence/piper_board_handeye_20261016/deploy_j4_validation01/sdk_preflight_10s.json')['samples'][-1]
    now = [s for s in sdk['samples'] if s['fresh_after_passive_connection']][-1]
    assert not any(now['enabled'])
    for report in (first, concurrent):
        assert report['can_before']['stats64']['tx']['packets'] == report['can_after']['stats64']['tx']['packets'] == 13
        assert report['can_after']['stats64']['rx']['packets'] > report['can_before']['stats64']['rx']['packets']
    pulses = [r for r in frames if abs(r.get('independent_speed_raw', 0)) > 1]
    assert len(pulses) == 2 and all(r['joint'] == 5 for r in pulses)
    baseline = load(REPO / 'docs/evidence/piper_board_handeye_20261016/deploy_j4_validation01/assessment.json')['frozen_source_SHA_after']
    assert all(sha(Path(path)) == expected for path, expected in baseline.items())
    result = {'read_only': True, 'ROS_nodes_or_device_commands_started': False,
              'production_source_or_threshold_change': False, 'no_CAN_recovery': True,
              'first_capture': {'high_frames_per_joint': 1200, 'all_speeds_zero': True,
                 'aggregate_angles_unavailable_due_initial_3Ax_only_filter': True,
                 'not_a_proof_of_preceding_or_following_state': True},
              'concurrent_capture': {'raw_frames': len(frames), 'high_frames_per_joint': 1200,
                 'actual_feedback_family': '0x2A1..0x2A8; no 0x3Ax in this window',
                 'SDK_direct_speed_and_pos_decode_matches_every_raw_high_frame': True,
                 'actual_speed_pulses': pulses,
                 'sampling_caveat': '10Hz SDK snapshots missed the brief CAN speed pulses; neither stream is replaced.'},
              'SDK_full_window_quality': sdk['quality'],
              'passing_original_static_subwindows': len(passing),
              'longest_original_static_subwindow': longest,
              'SDK_collect_return_code': 2,
              'raw_collect_return_codes': [0, 0],
              'static_threshold_changed': False,
              'previous_session_last_SDK': before,
              'this_session_last_fresh_SDK': now,
              'q_change_mdeg_from_previous_session': [b-a for a, b in zip(before['q_mdeg'], now['q_mdeg'])],
              'raw_status': raw_status,
              'new_actual_blocker': 'Six axes disabled and pose changed substantially from prior observation. Physical support and cause of transition unknown; no automatic enable or motion.',
              'transition_not_observed_continuously': True,
              'cannot_claim_what_disabled_arm_or_when': True,
              'per_window_CAN_TX_packets_constant': 13,
              'sample_protocol_not_continued': 'No J4 motion, board still 2/10, no new camera/hand-eye result.',
              'official_reference': 'https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD',
              'reference_scope': 'Speed unit .001rad/s only; no vendor claim that these pulses are harmless or physical support confirmed.',
              'next_manual_fact_needed': 'Confirm actual reliable mechanical support and whether manual reset/power action occurred; no request to move/restart/enable.',
              'manual_question_answer': None}
    put(ROOT / 'assessment.json', result)
    names = ['receive_raw.py', 'raw_assessment.json', 'raw_receive.jsonl', 'sdk_concurrent.json',
             'concurrent/raw_assessment.json', 'concurrent/raw_receive.jsonl', 'assessment.json', 'package_audit.py']
    for name in ['receive_raw.py', 'raw_assessment.json', 'sdk_concurrent.json', 'assessment.json', 'package_audit.py']:
        src = ROOT / name
        if src.suffix == '.py':
            ast.parse(src.read_text())
        shutil.copyfile(src, OUT / name)
    shutil.copyfile(ROOT / 'concurrent/raw_assessment.json', OUT / 'concurrent_raw_assessment.json')
    entries = [{'path': n, 'bytes': (ROOT / n).stat().st_size, 'sha256': sha(ROOT / n)} for n in names]
    archive = OUT / 'raw_originals.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in names:
            tar.add(ROOT / name, arcname=name, recursive=False)
    with tarfile.open(archive) as tar:
        for entry in entries:
            assert hashlib.sha256(tar.extractfile(entry['path']).read()).hexdigest() == entry['sha256']
    put(OUT / 'runtime_manifest.json', {'archive_SHA256': sha(archive), 'files': entries, 'all_SHA_readback_verified': True})
    print(json.dumps({'files_verified': len(entries), 'archive_bytes': archive.stat().st_size,
                      'original_static_longest': longest, 'latest_q_mdeg': now['q_mdeg'], 'enabled': now['enabled']}))


if __name__ == '__main__':
    main()
