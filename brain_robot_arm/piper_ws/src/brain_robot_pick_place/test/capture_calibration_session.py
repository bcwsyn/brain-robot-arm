#!/usr/bin/env python3
"""One authorized stationary acquisition: bounded readiness -> original capture.

Only camera sources, receive-only feedback, subscribers and factory GETs.
Never launches a driver/controller, modifies CAN, or enables/moves a robot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from collect_calibration_p0 import read_can, healthy_window

TESTS = Path(__file__).resolve().parent
FACTORY = Path('/home/johnwick/brain_robot_logs/calibration_stage1_activated_20261014.kfNDAQ/capture_factory_metadata.py')
STARTUP_S, CAPTURE_S, CAMERA_TOTAL_S, BRIDGE_S = 20., 55., 80., 90.
CLEANUP_RESERVE_S = 3.


def commands(root):
    """Fixed scoped child commands; no shell expansion or external controls."""
    prelude = f'import sys; sys.path.insert(0,{str(TESTS)!r}); '
    code = (prelude + 'from pathlib import Path; from collect_static_rgbd import collect; '
            'sys.exit(collect(Path(sys.argv[1]),55.,60,settle_s=3.,'
            'stop_on_feedback_loss=True,max_bytes=64<<20))')
    return {
        'bridge': [sys.executable, str(TESTS/'calibration_readonly_feedback.py'),
                   '--duration-s', '90', '--output', str(root/'feedback.json')],
        'ready': [sys.executable, str(TESTS/'wait_calibration_ready.py'),
                  '--duration-s', '20', '--output', str(root/'readiness.json'),
                  '--listening', str(root/'listening.json')],
        'depth': ['ros2', 'launch', 'astra_camera', 'astra.launch.py'],
        'color': ['/opt/ros/humble/lib/image_tools/cam2image', '--ros-args',
                  '-p', 'burger_mode:=false', '-p', 'device_id:=0', '-p', 'frequency:=5.0',
                  '-p', 'width:=320', '-p', 'height:=240',
                  '-p', 'frame_id:=camera_color_optical_frame', '-r', 'image:=/camera/color/image_raw'],
        'capture': [sys.executable, '-c', code, str(root/'capture')],
        'factory': [sys.executable, str(FACTORY), str(root/'factory.json')],
    }


def capture_window(startup_elapsed_s):
    """Budget calculation only; original per-frame acceptance is untouched."""
    return min(CAPTURE_S, max(0., CAMERA_TOTAL_S-startup_elapsed_s-CLEANUP_RESERVE_S))


def run(output):
    if output.exists():
        raise FileExistsError('Refusing existing session before any imports, ROS or device access')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'piper_stationary_acquisition_session_v1', 'subscription_only': True,
              'motion_commands_sent': False, 'CAN_recovery': False, 'automatic_camera_reopen': False,
              'camera_setters_called': False, 'production_modified': False,
              'startup_budget_s': STARTUP_S, 'formal_capture_budget_s': CAPTURE_S,
              'camera_total_budget_s': CAMERA_TOTAL_S, 'bridge_budget_s': BRIDGE_S,
              'events': [], 'ready': False, 'formal_capture_started': False,
              'factory_started': False, 'error': None}
    argv, jobs, camera_start = commands(output), [], None
    sources = [TESTS/name for name in ['collect_static_rgbd.py', 'calibration_readonly_feedback.py',
                                      'wait_calibration_ready.py', 'capture_calibration_session.py']]

    def save(name, value):
        with (output/name).open('x') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)

    def start(name):
        stream = (output/(name+'.log')).open('xb')
        try:
            process = subprocess.Popen(argv[name], stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except BaseException:
            stream.close()
            raise
        jobs.append((name, process, stream))
        report['events'].append({'name': name, 'argv': argv[name], 'pid': process.pid,
                                 'epoch': time.time(), 'monotonic_ns': str(time.monotonic_ns())})
        return process

    def until(predicate, deadline, label):
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.05)
        raise TimeoutError(label)

    try:
        code = (f'import sys; sys.path.insert(0,{str(TESTS)!r}); '
                'import collect_static_rgbd,wait_calibration_ready; '
                'import cv2,cv_bridge,message_filters,rclpy; print("imports verified; no rclpy.init")')
        preflight = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                   text=True, timeout=8, check=True)
        report['import_preflight'] = {'returncode': preflight.returncode, 'stdout': preflight.stdout}
        save('source_SHA_before.json', {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        before = read_can(); time.sleep(.2); after = read_can()
        save('can_before.json', {'before': before, 'after': after, 'healthy': healthy_window(before,after)})
        if not healthy_window(before, after):
            raise RuntimeError('Existing CAN not UP/ERROR-ACTIVE with RX growth; no recovery')
        start('bridge')
        readiness = start('ready')
        listening_deadline = time.monotonic()+min(5., STARTUP_S)
        until(lambda: (output/'listening.json').exists() or readiness.poll() is not None,
              listening_deadline, 'Readiness subscriber initialization')
        if readiness.poll() is not None:
            raise RuntimeError('Readiness exited before source startup')
        camera_start = time.monotonic()
        report['camera_start_epoch'] = time.time()
        # One launch of each source. Readiness is determined from real messages,
        # never from the log or service discovery alone.
        depth = start('depth')
        depth_warmup_deadline = min(time.monotonic()+4., camera_start+STARTUP_S)
        while time.monotonic() < depth_warmup_deadline and depth.poll() is None:
            if 'SENSOR_DEPTH is started' in (output/'depth.log').read_text(errors='replace'):
                break
            time.sleep(.05)
        report['depth_warmup_log_advisory_only'] = 'SENSOR_DEPTH is started' in (output/'depth.log').read_text(errors='replace')
        start('color')
        until(lambda: readiness.poll() is not None, camera_start+STARTUP_S,
              'Four-source readiness budget exhausted')
        ready = json.loads((output/'readiness.json').read_text())
        report['readiness'] = ready
        if readiness.returncode != 0 or not ready['ready']:
            raise RuntimeError('Four-source readiness not achieved; no formal capture started')
        report['ready'] = True
        report['ready_epoch'] = time.time()
        report['startup_camera_elapsed_s'] = time.monotonic()-camera_start
        # Readiness process is now exited, so its extra subscriptions do not
        # compete with the original collector's independent 3s static history.
        allowed = capture_window(time.monotonic()-camera_start)
        if allowed < CAPTURE_S:
            raise RuntimeError('Insufficient remaining full capture budget; do not silently truncate')
        capture = start('capture')
        report['formal_capture_started'] = True
        report['capture_start_epoch'] = time.time()
        capture_deadline = min(camera_start+CAMERA_TOTAL_S-CLEANUP_RESERVE_S,
                               time.monotonic()+CAPTURE_S+1.)
        until(lambda: capture.poll() is not None, capture_deadline, 'Original formal collector deadline')
        report['capture_returncode'] = capture.returncode
        report['capture_summary'] = json.loads((output/'capture/summary.json').read_text())
        # Metadata GETs follow collection, never run concurrently with it.
        # If insufficient time remains, leave an explicit missing-metadata item.
        remaining = camera_start+CAMERA_TOTAL_S-CLEANUP_RESERVE_S-time.monotonic()
        if report['capture_summary']['saved_frames'] and remaining >= 14. and FACTORY.is_file():
            factory = start('factory')
            report['factory_started'] = True
            until(lambda: factory.poll() is not None, min(time.monotonic()+13.,
                  camera_start+CAMERA_TOTAL_S-CLEANUP_RESERVE_S), 'Factory GET deadline')
            report['factory_returncode'] = factory.returncode
        else:
            report['factory_deferred_reason'] = 'No saved real packet, missing helper, or insufficient reserved time'
    except BaseException as exc:
        report['error'] = repr(exc)
    finally:
        # Stop only owned children, all together; no robot disable/reset calls.
        for _, process, _ in jobs:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
        grace = time.monotonic()+1.5
        while any(p.poll() is None for _,p,_ in jobs) and time.monotonic()<grace:
            time.sleep(.02)
        for name, process, stream in jobs:
            killed = process.poll() is None
            if killed:
                os.killpg(process.pid, signal.SIGKILL)
            report['events'].append({'name': name, 'final_exit_code': process.wait(timeout=1),
                                     'forced_kill': killed, 'epoch': time.time()})
            stream.close()
        report['all_owned_sources_exited'] = all(p.poll() is not None for _,p,_ in jobs)
        report['camera_elapsed_s_including_cleanup'] = None if camera_start is None else time.monotonic()-camera_start
        report['within_camera_budget'] = camera_start is None or report['camera_elapsed_s_including_cleanup']<=CAMERA_TOTAL_S
        if (output/'capture/summary.json').exists():
            report['capture_summary'] = json.loads((output/'capture/summary.json').read_text())
        save('source_SHA_after.json', {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        try:
            save('can_after.json', read_can())
        except Exception as exc:
            report['can_after_error'] = repr(exc)
        report['raw_acquisition_complete'] = (report.get('capture_returncode') == 0 and
             report.get('capture_summary', {}).get('saved_frames') == 60 and report['error'] is None)
        report['quality_or_calibration_accepted'] = False
        save('execution.json', report)
    print(json.dumps(report), flush=True)
    return 0 if report['raw_acquisition_complete'] and report['within_camera_budget'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output.resolve()))
