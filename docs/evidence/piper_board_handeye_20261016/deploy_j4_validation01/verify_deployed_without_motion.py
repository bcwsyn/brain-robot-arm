"""Reuse original sampling helpers, but never arm or publish a trajectory.

The original SDK static criterion did not pass in two bounded captures.
Verify the authorized deployment/runtime and J4 plans without bypassing it.
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

import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
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
from collect_calibration_p0 import read_can

ORIGINAL = REPO / 'docs/evidence/piper_board_handeye_20261016/attempt01/run03'
tree = ast.parse((ORIGINAL / 'executed_sampler.py').read_text())
helpers = {'save', 'launch', 'wait', 'call', 'feedback', 'state', 'valid', 'plan'}
definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in helpers]
assert len(definitions) == len(helpers)
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[])),
             '<unchanged original sampler helpers>', 'exec'), globals())

cfg = yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
NAMES = [f'joint{i}' for i in range(1, 7)]
report = {'mode': 'deployed runtime and original J4 planning only', 'events': [], 'paths': [],
          'error': None, 'SDK_static_passed': False, 'arm_called': False,
          'enable_service_called': False, 'trajectories_published': 0, 'gripper_commands': 0,
          'motion_blocker': 'Two original passive SDK windows have no passing 3s/30 sample static subwindow; do not bypass.'}
jobs = []
latest = None
history = collections.deque(maxlen=4000)
camera_started = None
flow_error = None
started = time.monotonic()
rclpy.init()
node = rclpy.create_node('verify_deployed_adapter_without_motion')
node.create_subscription(JointState, '/joint_states_feedback', feedback, qos_profile_sensor_data)
try:
    save('can_before_runtime.json', read_can())
    launch_file = ROOT / 'original_nodes.launch.py'
    assert launch_file.read_bytes() == (ORIGINAL / 'executed_launch.py').read_bytes()
    launch('driver', ['/usr/bin/python3', '-c', "import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()", '--ros-args', '--log-level', 'WARN', '-p', 'can_port:=can0', '-p', 'auto_enable:=false', '-p', 'gripper_exist:=true', '-r', 'joint_states_single:=/joint_states', '-r', 'joint_ctrl_single:=/joint_commands'])
    launch('original_nodes', ['/usr/bin/python3', str(launch_file)])
    launch('bag', ['ros2', 'bag', 'record', '-o', str(ROOT / 'runtime_bag'),
                   '/joint_states_feedback', '/joint_commands', '/brain_robot_grasp/arm_trajectory',
                   '/brain_robot_grasp/gripper_command', '/brain_robot_control/adapter_armed'])
    wait(lambda: latest is not None and time.time()-latest['epoch'] < .5 and latest['gap_m'] is not None, 20, 'fresh feedback')
    wait(lambda: settled_feedback(history, latest['q'], latest['stamp_ns'], 3.), 8, 'original ROS angle-only static window')
    center = np.asarray(latest['q'])
    opening = latest['gap_m']
    report['actual_start'] = latest.copy()
    report['ROS_angle_only_static_passed_NOT_SDK_speed_pass'] = True
    result = call(GetParameters, '/piper_jog_adapter/get_parameters', GetParameters.Request(names=[
        'motion_enabled', 'max_velocity_rad_s', 'joint_state_timeout_s', 'command_timeout_s',
        'trajectory_start_tolerance_rad', 'joint_min', 'joint_max']))
    report['adapter_parameters'] = message_to_ordereddict(result)
    assert not result.values[0].bool_value
    result = call(GetParameters, '/move_group/get_parameters', GetParameters.Request(names=['allow_trajectory_execution', 'robot_description']))
    assert not result.values[0].bool_value
    report['model_SHA256'] = hashlib.sha256(result.values[1].string_value.encode()).hexdigest()
    assert report['model_SHA256'] == '0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82'
    req = GetPlanningScene.Request()
    req.components.components = PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.OCTOMAP
    scene = call(GetPlanningScene, '/get_planning_scene', req).scene
    report['scene'] = {'world_ids': [o.id for o in scene.world.collision_objects],
                       'octomap_bytes': len(scene.world.octomap.octomap.data),
                       'not_physical_clearance_proof': True}
    goal = center + np.deg2rad([0, 0, 0, 6, 0, 0])
    report['start_validity'] = valid(center)
    report['J4_plus_validity'] = valid(goal)
    assert report['start_validity']['valid'] and report['J4_plus_validity']['valid']
    plan(center, goal, 'J4_plus6_out')
    plan(goal, center, 'J4_plus6_back')
    report['two_original_MoveIt_plans_passed'] = True
    print('DEPLOYED_CANDIDATE_STARTED_DISARMED_TWO_PLANS_PASSED_NO_MOTION', flush=True)
except BaseException as exc:
    report['error'] = repr(exc)
    print('VERIFY_STOP', repr(exc), flush=True)
finally:
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
    report['elapsed_s'] = time.monotonic() - started
    save('can_after_runtime.json', read_can())
    save('runtime_verification.json', report)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
print(json.dumps({'error': report['error'], 'motion_not_started': True, 'all_exited': report['all_owned_sources_exited']}), flush=True)
raise SystemExit(0 if report['error'] is None else 2)
