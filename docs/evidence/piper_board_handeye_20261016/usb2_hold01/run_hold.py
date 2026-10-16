"""Authorized 30s original driver/adapter idle hold; no new joint/gripper goals."""
import collections
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory
from control_msgs.msg import JointJog
from piper_msgs.srv import Enable
from rcl_interfaces.srv import GetParameters

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
TEST = REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0, str(TEST))
from collect_calibration_sdk import summarize

NAMES = [f'joint{i}' for i in range(1, 7)]
frozen = json.loads((REPO / 'docs/evidence/piper_board_handeye_20261016/usb2_passive01/production_SHA_after.json').read_text())
report = {'baseline_commit': 'd9471e2', 'operator_quote': '好',
          'scope': 'Original driver and adapter idle hold at freshly measured pose for 30s; no displaced target, trajectory, jog or gripper command',
          'events': [], 'jobs': [], 'sdk': {}, 'CAN_snapshots': [], 'error': None,
          'hold_passed': False, 'hold_requested_s': 30,
          'hardware_disable_reset_gripper_commands_requested': False,
          'production_modified': False, 'camera_started': False}
jobs = []
latest = None
feedback_rows = []
command_rows = []
armed_status = None
armed = False
inputs = collections.Counter()
raw_counts = collections.defaultdict(collections.Counter)
raw_error = []
raw_stop = threading.Event()
raw_thread = None
raw_socket = None

def save(name, value):
    with (ROOT / name).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)

def command(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    report['events'].append({'argv': argv, 'rc': p.returncode, 'stdout': p.stdout,
                             'stderr': p.stderr, 'epoch': time.time()})
    if p.returncode:
        raise RuntimeError(f'Command rc={p.returncode}: {argv}')
    return p.stdout

def can_state(label):
    s = json.loads(command(['ip', '-json', '-details', '-statistics', 'link', 'show', 'can0']))[0]
    report['CAN_snapshots'].append({'label': label, 'epoch': time.time(), 'state': s})
    return s

def launch(name, argv):
    f = (ROOT / (name + '.log')).open('xb')
    p = subprocess.Popen(argv, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    jobs.append((name, p, f))
    report['jobs'].append({'name': name, 'argv': argv, 'pid': p.pid, 'epoch': time.time()})
    return p

def wait(predicate, seconds, label):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        rclpy.spin_once(node, timeout_sec=.02)
        if predicate():
            return
    raise TimeoutError(label)

def call(kind, path, req):
    client = node.create_client(kind, path)
    try:
        wait(client.service_is_ready, 15, path + ' discovery')
        future = client.call_async(req)
        wait(future.done, 12, path + ' response; not retried')
        result = future.result()
        report['events'].append({'service': path, 'response': str(result), 'epoch': time.time()})
        return result
    finally:
        node.destroy_client(client)

def trigger(path):
    result = call(Trigger, path, Trigger.Request())
    if not result.success:
        raise RuntimeError(path + ': ' + result.message)

def sdk(label, duration):
    p = launch(label, ['/usr/bin/python3', str(TEST / 'collect_calibration_sdk.py'),
                       '--output', str(ROOT / (label + '.json')), '--duration-s', str(duration)])
    wait(lambda: p.poll() is not None, duration + 5, label)
    data = json.loads((ROOT / (label + '.json')).read_text())
    rows = data['samples']
    best = None
    for i in range(len(rows)):
        for j in range(i + 30, len(rows) + 1):
            q = summarize(rows[i:j])
            if q['static_three_seconds_and_thirty_samples'] and (best is None or j-i > best['samples']):
                best = {'indices': [i, j], 'samples': j-i, 'quality': q}
    fresh = [r for r in rows if r['fresh_after_passive_connection']]
    report['sdk'][label] = {'rc': p.returncode, 'quality': data['quality'],
                           'original_static_subwindow': best, 'last_fresh': fresh[-1] if fresh else None}
    if not fresh:
        raise RuntimeError(label + ': no fresh data')
    return fresh[-1], best

telemetry = (ROOT / 'ROS_messages.jsonl').open('x')

def record(topic, msg):
    row = {'topic': topic, 'epoch': time.time(), 'monotonic': time.monotonic(),
           'stamp_ns': msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
           'name': list(msg.name), 'position': list(msg.position),
           'velocity': list(msg.velocity), 'effort': list(msg.effort)}
    telemetry.write(json.dumps(row, allow_nan=False) + '\n')
    return row

def feedback(msg):
    global latest
    row = record('/joint_states_feedback', msg)
    q = dict(zip(msg.name, msg.position))
    if all(n in q for n in NAMES):
        latest = dict(row, q=[q[n] for n in NAMES])
        feedback_rows.append(latest)

def output(msg):
    row = record('/joint_commands', msg)
    q = dict(zip(msg.name, msg.position))
    row['q'] = [q[n] for n in NAMES] if all(n in q for n in NAMES) else None
    command_rows.append(row)

def status(msg):
    global armed_status
    armed_status = bool(msg.data)
    report['events'].append({'adapter_armed': armed_status, 'epoch': time.time()})

def unexpected(topic, msg):
    inputs[topic] += 1

def receive_raw():
    try:
        with (ROOT / 'CAN_receive_epoch_ns_frame16.bin').open('xb') as f:
            while not raw_stop.is_set():
                try:
                    frame = raw_socket.recv(16)
                except socket.timeout:
                    continue
                if len(frame) != 16:
                    raise RuntimeError('Unexpected nonclassic CAN record')
                epoch_ns = time.time_ns()
                f.write(struct.pack('=Q', epoch_ns) + frame)
                raw_counts[epoch_ns // 10**9][hex(struct.unpack_from('=I', frame)[0])] += 1
    except BaseException as e:
        raw_error.append(repr(e))

rclpy.init()
node = rclpy.create_node('authorized_original_chain_idle_hold')
node.create_subscription(JointState, '/joint_states_feedback', feedback, qos_profile_sensor_data)
node.create_subscription(JointState, '/joint_commands', output, qos_profile_sensor_data)
node.create_subscription(Bool, '/brain_robot_control/adapter_armed', status, 10)
for topic, kind in [('/brain_robot_grasp/arm_trajectory', JointTrajectory),
                    ('/brain_robot_grasp/gripper_command', JointState),
                    ('/servo_node/delta_joint_cmds', JointJog)]:
    node.create_subscription(kind, topic, lambda msg, t=topic: unexpected(t, msg), 10)

try:
    assert not (ROOT / 'execution.json').exists(), 'Never overwrite or repeat'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == s for p, s in frozen.items())
    save('production_SHA_before.json', frozen)
    device = Path('/sys/class/net/can0/device').resolve()
    assert device.name == '1-2.1:1.0'
    report['USB_actual_path'] = str(device)
    report['kernel_before'] = command(['sudo', '-n', 'dmesg', '-T'])
    a = can_state('preflight'); time.sleep(.2); b = can_state('preflight_next')
    assert 'UP' in b['flags'] and b['linkinfo']['info_data']['state'] == 'ERROR-ACTIVE'
    assert b['stats64']['rx']['packets'] > a['stats64']['rx']['packets']
    # No interface/USB activation or recovery is performed by this wrapper.
    raw_socket = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    raw_socket.bind(('can0',)); raw_socket.settimeout(.05)
    raw_thread = threading.Thread(target=receive_raw)
    raw_thread.start()
    measured, static = sdk('sdk_before', 10)
    assert static is not None, 'Original static window absent; no active stack started'
    assert all(measured['enabled']), 'Current feedback must already show all six enabled'
    launch('driver', ['/usr/bin/python3', '-c', "import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()",
                     '--ros-args', '--log-level', 'WARN', '-p', 'can_port:=can0', '-p', 'auto_enable:=false',
                     '-p', 'gripper_exist:=true', '-r', 'joint_states_single:=/joint_states', '-r', 'joint_ctrl_single:=/joint_commands'])
    launch('adapter', ['/usr/bin/python3', str(ROOT / 'original_adapter_only.py')])
    wait(lambda: latest is not None and time.time()-latest['epoch'] < .5 and armed_status is False, 20, 'Fresh driver/adapter startup')
    assert max(abs(a-b) for a,b in zip(latest['q'], measured['q_driver_rad'])) <= .001
    params = call(GetParameters, '/piper_jog_adapter/get_parameters', GetParameters.Request(names=[
        'motion_enabled', 'joint_state_timeout_s', 'publish_rate_hz', 'max_velocity_rad_s', 'joint_min', 'joint_max']))
    report['adapter_parameters_readback'] = str(params)
    assert not params.values[0].bool_value and params.values[1].double_value == 25.
    for topic in ['/brain_robot_grasp/arm_trajectory', '/brain_robot_grasp/gripper_command', '/servo_node/delta_joint_cmds']:
        assert node.count_publishers(topic) == 0, 'External motion input publisher: ' + topic
    assert node.count_publishers('/joint_commands') == 1
    result = call(Enable, '/enable_srv', Enable.Request(enable_request=True))
    assert result.enable_response
    trigger('/piper_jog_adapter/enable_motion')
    report['at_arm'] = dict(latest)
    trigger('/piper_jog_adapter/arm'); armed = True
    wait(lambda: armed_status is True and bool(command_rows), 5, 'Original idle output starts')
    assert command_rows[0]['q'] is not None
    assert max(abs(a-b) for a,b in zip(command_rows[0]['q'], report['at_arm']['q'])) <= .001
    report['hold_start_epoch'] = time.time()
    began = time.monotonic()
    report['hold_start_feedback'] = dict(latest)
    report['CAN_hold_start'] = can_state('hold_start')
    print('ORIGINAL_IDLE_HOLD_STARTED', json.dumps({'q': latest['q'], 'duration_s': 30, 'no_jog_trajectory_gripper': True}), flush=True)
    while time.monotonic()-began < 30:
        rclpy.spin_once(node, timeout_sec=.02)
        assert not raw_error, str(raw_error)
        assert all(p.poll() is None for name,p,f in jobs if name in ('driver','adapter'))
        assert armed_status is True, 'Original adapter disarmed'
        assert time.time()-latest['epoch'] <= .5, 'Driver feedback ceased during hold'
        assert max(abs(a-b) for a,b in zip(latest['q'], report['hold_start_feedback']['q'])) <= .04, 'Actual pose left original arrival tolerance during hold'
        assert not inputs, 'Unexpected motion/gripper input observed'
    report['hold_elapsed_s'] = time.monotonic()-began
    report['hold_end_epoch'] = time.time()
    report['hold_end_feedback'] = dict(latest)
    report['CAN_hold_end'] = can_state('hold_end')
    assert report['CAN_hold_end']['stats64']['tx']['packets'] > report['CAN_hold_start']['stats64']['tx']['packets']
    report['hold_passed'] = True
    print('ORIGINAL_IDLE_HOLD_30S_COMPLETE', flush=True)
except BaseException as e:
    report['error'] = repr(e)
    print('HOLD_STOP', repr(e), flush=True)
finally:
    if armed:
        try:
            trigger('/piper_jog_adapter/disarm'); armed = False
            report['software_disarm_succeeded'] = True
        except BaseException as e:
            report['events'].append({'software_disarm_error': repr(e)})
    if any(name == 'driver' and p.poll() is None for name,p,f in jobs):
        try:
            sdk('sdk_after', 6)
        except BaseException as e:
            report['events'].append({'post_SDK_error': repr(e)})
    for name,p,f in reversed(jobs):
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGINT)
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL); p.wait(timeout=2)
        f.close()
        report['events'].append({'source': name, 'exit_code': p.returncode, 'epoch': time.time()})
    raw_stop.set()
    if raw_thread:
        raw_thread.join(timeout=2)
    if raw_socket:
        raw_socket.close()
    telemetry.close()
    report['all_owned_sources_exited'] = all(p.poll() is not None for _,p,_ in jobs) and (raw_thread is None or not raw_thread.is_alive())
    report['raw_errors'] = raw_error
    report['raw_counts_per_epoch_second'] = {str(k):dict(v) for k,v in sorted(raw_counts.items())}
    report['feedback_count'] = len(feedback_rows)
    report['command_count'] = len(command_rows)
    report['observed_motion_inputs'] = dict(inputs)
    report['last_received_feedback'] = latest
    try:
        can_state('after_sources_exit')
        report['kernel_after'] = command(['sudo', '-n', 'dmesg', '-T'])
    except BaseException as e:
        report['events'].append({'final_read_error': repr(e)})
    report['six_source_SHA_unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == s for p,s in frozen.items())
    save('execution.json', report)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
print(json.dumps({k: report.get(k) for k in ('hold_passed','hold_elapsed_s','error','feedback_count','command_count','all_owned_sources_exited','six_source_SHA_unchanged')}), flush=True)
raise SystemExit(0 if report['hold_passed'] and report['error'] is None else 2)
