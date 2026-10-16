"""Authorized J4 +6deg and return through original MoveIt/adapter helpers.

No direct SDK control, gripper, hardware disable/reset, other sampling or TF edit.
"""
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
from std_srvs.srv import Trigger
from piper_msgs.srv import Enable
from rcl_interfaces.srv import GetParameters
from moveit_msgs.srv import GetMotionPlan, GetStateValidity, GetPlanningScene
from moveit_msgs.msg import RobotState, Constraints, JointConstraint, PlanningSceneComponents
from rosidl_runtime_py.convert import message_to_ordereddict
import yaml

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
TEST = REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0, str(TEST))
from collect_static_rgbd import joint_positions, stamp_ns, settled_feedback
from review_calibration_sampling import checked_trajectory
from collect_calibration_p0 import read_can, healthy_window

ORIGINAL = REPO / 'docs/evidence/piper_board_handeye_20261016/attempt01/run03'
tree = ast.parse((ORIGINAL / 'executed_sampler.py').read_text())
helpers = {'save', 'launch', 'wait', 'call', 'trigger', 'feedback', 'state', 'valid', 'plan', 'execute'}
definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in helpers]
assert len(definitions) == len(helpers)
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[])),
             '<unchanged original sampling helpers>', 'exec'), globals())

cfg = yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
NAMES = [f'joint{i}' for i in range(1, 7)]
frozen = json.loads((REPO / 'docs/evidence/piper_board_handeye_20261016/deploy_j4_validation01/assessment.json').read_text())['frozen_source_SHA_after']
sdk = json.loads((ROOT / 'sdk_before.json').read_text())
assert sdk['quality']['static_three_seconds_and_thirty_samples']
report = {'operator_confirmation': '我刚刚把机械臂断电重启了，现在在零点位置安全',
          'prior_specific_J4_and_candidate_deployment_authorization_preserved': True,
          'scope': 'J4 relative +6 degrees and return to this session actual start only',
          'events': [], 'paths': [], 'arrivals': [], 'error': None, 'enable_service_called': False,
          'gripper_commands': 0, 'hardware_disable_or_reset': False, 'camera_started': False,
          'other_board_poses_or_search_or_grasp': False, 'production_code_changed': False,
          'SDK_before': sdk['samples'][-1], 'SDK_original_static_full_window_passed': True}
jobs = []
latest = None
history = collections.deque(maxlen=4000)
camera_started = None
flow_error = None
armed = False
started = time.monotonic()
rclpy.init()
node = rclpy.create_node('authorized_bounded_J4_roundtrip')
node.create_subscription(JointState, '/joint_states_feedback', feedback, qos_profile_sensor_data)
trajectory = node.create_publisher(JointTrajectory, '/brain_robot_grasp/arm_trajectory', 10)
try:
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in frozen}
    assert hashes == frozen
    save('production_SHA_before.json', hashes)
    first = read_can()
    time.sleep(.2)
    second = read_can()
    assert healthy_window(first, second)
    save('can_before.json', {'before': first, 'after': second})
    launch_file = ROOT / 'original_nodes.launch.py'
    assert launch_file.read_bytes() == (ORIGINAL / 'executed_launch.py').read_bytes()
    launch('driver', ['/usr/bin/python3', '-c', "import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()", '--ros-args', '--log-level', 'WARN', '-p', 'can_port:=can0', '-p', 'auto_enable:=false', '-p', 'gripper_exist:=true', '-r', 'joint_states_single:=/joint_states', '-r', 'joint_ctrl_single:=/joint_commands'])
    launch('original_nodes', ['/usr/bin/python3', str(launch_file)])
    launch('bag', ['ros2', 'bag', 'record', '-o', str(ROOT / 'motion_bag'),
                   '/joint_states_feedback', '/joint_commands', '/brain_robot_grasp/arm_trajectory',
                   '/brain_robot_grasp/gripper_command', '/brain_robot_control/adapter_armed', '/arm_status'])
    wait(lambda: latest is not None and time.time()-latest['epoch'] < .5 and latest['gap_m'] is not None, 20, 'fresh feedback')
    wait(lambda: settled_feedback(history, latest['q'], latest['stamp_ns'], 3.), 10, 'original static angle window')
    center = np.asarray(latest['q'])
    opening = latest['gap_m']
    report['actual_start'] = latest.copy()
    response = call(GetParameters, '/move_group/get_parameters', GetParameters.Request(names=['allow_trajectory_execution', 'robot_description']))
    assert not response.values[0].bool_value
    xml = response.values[1].string_value
    report['model_SHA256'] = hashlib.sha256(xml.encode()).hexdigest()
    assert report['model_SHA256'] == '0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82'
    model = ET.fromstring(xml)
    req = GetPlanningScene.Request()
    req.components.components = PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.OCTOMAP
    scene = call(GetPlanningScene, '/get_planning_scene', req).scene
    report['scene'] = {'world_ids': [o.id for o in scene.world.collision_objects],
                       'octomap_bytes': len(scene.world.octomap.octomap.data), 'not_physical_clearance_proof': True}
    goal = center + np.deg2rad([0, 0, 0, 6, 0, 0])
    report['start_validity'] = valid(center)
    report['goal_validity'] = valid(goal)
    assert report['start_validity']['valid'] and report['goal_validity']['valid']
    out = plan(center, goal, 'J4_plus6_out')
    back = plan(goal, center, 'J4_plus6_back_precheck')
    duration = out.points[-1].time_from_start.sec + out.points[-1].time_from_start.nanosec/1e9
    checklist = {'SDK_high_stamp': sdk['samples'][-1]['sdk_receipt_stamps']['high'],
                 'SDK_high_Hz': sdk['samples'][-1]['high_hz'],
                 'six_enabled_before_enable': sdk['samples'][-1]['enabled'],
                 'enabling_requested_as_existing_control_step': True,
                 'start_rad': center.tolist(), 'out_goal_rad': goal.tolist(),
                 'return_goal_rad': center.tolist(), 'only_joint4_requested_delta_deg': 6,
                 'task_joint_min': cfg['real_trajectory_joint_min'], 'task_joint_max': cfg['real_trajectory_joint_max'],
                 'model_joint_limits': {n: model.find("joint[@name='"+n+"']/limit").attrib for n in NAMES},
                 'MoveIt_velocity_scaling': .02, 'MoveIt_acceleration_scaling': .02,
                 'original_adapter_max_velocity_rad_s': .189, 'original_out_duration_s': duration,
                 'stop': 'Original driver suppresses stale feedback; adapter original watchdog; execute original duration+25s timeout -> software disarm, no hardware disable.',
                 'normal_return': 'Original checked trajectory to fresh session start then software disarm, remain enabled.',
                 'physical_support_source': 'User explicitly confirmed rebooted zero pose safe; not inferred from q.'}
    report['checklist'] = checklist
    save('planning_before_motion.json', report)
    print('REAL_J4_CHECKLIST', json.dumps(checklist), flush=True)
    enabled = call(Enable, '/enable_srv', Enable.Request(enable_request=True))
    report['enable_service_called'] = True
    assert enabled.enable_response
    report['after_enable_received_feedback'] = latest.copy()
    trigger('/piper_jog_adapter/enable_motion')
    trigger('/piper_jog_adapter/arm')
    armed = True
    report['arm_received_feedback'] = latest.copy()
    print('EXECUTE_J4_OUT', flush=True)
    execute(out, goal, 'J4_plus6_out')
    wait(lambda: settled_feedback(history, latest['q'], latest['stamp_ns'], 3.), 12, 'out actual settled')
    report['arrivals'].append({'label': 'out', 'actual_feedback': latest.copy(), 'goal_q': goal.tolist()})
    print('J4_OUT_ACTUAL', json.dumps(latest), flush=True)
    # Use actual fresh arrival for the return start, not nominal +6 degrees.
    back = plan(np.asarray(latest['q']), center, 'J4_back_actual_start')
    print('EXECUTE_J4_RETURN', flush=True)
    execute(back, center, 'J4_return')
    wait(lambda: settled_feedback(history, latest['q'], latest['stamp_ns'], 3.), 12, 'return actual settled')
    report['arrivals'].append({'label': 'return', 'actual_feedback': latest.copy(), 'goal_q': center.tolist()})
    report['roundtrip_original_tolerance_and_settled_passed'] = True
    print('J4_RETURN_ACTUAL', json.dumps(latest), flush=True)
except BaseException as exc:
    report['error'] = repr(exc)
    print('ROUNDTRIP_STOP', repr(exc), flush=True)
finally:
    if armed:
        try:
            trigger('/piper_jog_adapter/disarm')
            armed = False
            report['software_disarm_succeeded'] = True
        except BaseException as exc:
            report['events'].append({'software_disarm_error': repr(exc)})
    for name, process, stream in reversed(jobs):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
        stream.close()
        report['events'].append({'source': name, 'exit_code': process.returncode})
    report['all_owned_sources_exited'] = all(p.poll() is not None for _, p, _ in jobs)
    report['last_received_feedback'] = latest
    report['elapsed_s'] = time.monotonic()-started
    save('can_after.json', read_can())
    save('production_SHA_after.json', {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in frozen})
    save('execution.json', report)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
print(json.dumps({'error': report['error'], 'roundtrip_passed': report.get('roundtrip_original_tolerance_and_settled_passed', False), 'all_exited': report['all_owned_sources_exited']}), flush=True)
raise SystemExit(0 if report.get('roundtrip_original_tolerance_and_settled_passed') and report['error'] is None else 2)
