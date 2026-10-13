"""Replay the frozen terminal snapshot in domain 78; planning only, no execution."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import rclpy
import numpy as np
from scipy.spatial.transform import Rotation
from geometry_msgs.msg import Pose
from moveit_msgs.msg import RobotState
from moveit_msgs.srv import GetCartesianPath, GetPositionFK, GetStateValidity
import yaml

if os.environ.get('ROS_DOMAIN_ID') != '78':
    raise RuntimeError('Isolated ROS domain 78 is mandatory')
log = Path(sys.argv[1]).read_text()
helper = sys.argv[2]
task = yaml.safe_load(Path(sys.argv[3]).read_text())['grasp_lift_executor']['ros__parameters']
names = [f'joint{i}' for i in range(1, 7)]
q = [float(re.search('TARGET_DIRECTED_PREGRASP PLAN_START ' + name + r'=([-\d.]+)',
                     log).group(1)) for name in names]
match = re.search(r'TERMINAL_RGBD_TARGET_FROZEN .*base=\(([^)]+)\)', log)
surface = [float(v) for v in match.group(1).split(',')]
insertion = float(re.search(r'TARGET_DIRECTED_VARIABLE_ATTITUDE .*insertion=([-\d.]+)',
                            log).group(1))
rclpy.init()
node = rclpy.create_node('terminal_depth_snapshot_planning_only')
clients = {name: node.create_client(kind, name) for name, kind in [
    ('/compute_cartesian_path', GetCartesianPath), ('/compute_fk', GetPositionFK),
    ('/check_state_validity', GetStateValidity)]}


def call(name, request):
    client = clients[name]
    if not client.wait_for_service(timeout_sec=12):
        raise RuntimeError(name + ' unavailable')
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=15)
    if not future.done() or future.result() is None:
        raise RuntimeError(name + ' timeout')
    return future.result()


def fk(state):
    request = GetPositionFK.Request()
    request.header.frame_id = 'base_link'
    request.fk_link_names = ['link6']
    request.robot_state = state
    answer = call('/compute_fk', request)
    if answer.error_code.val != 1:
        raise RuntimeError('FK error ' + str(answer.error_code.val))
    return answer.pose_stamped[0].pose


def plan(state, poses):
    request = GetCartesianPath.Request()
    request.header.frame_id = 'base_link'
    request.group_name = 'arm'
    request.link_name = 'link6'
    request.start_state = state
    request.max_step = .005
    request.jump_threshold = 0.
    request.avoid_collisions = True
    for value in poses:
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = value['origin']
        (pose.orientation.x, pose.orientation.y,
         pose.orientation.z, pose.orientation.w) = value['orientation']
        request.waypoints.append(pose)
    answer = call('/compute_cartesian_path', request)
    if answer.error_code.val == -21:
        raise RuntimeError('Cartesian frame unavailable')
    points = answer.solution.joint_trajectory.points
    endpoint = copy.deepcopy(state)
    if points:
        positions = dict(zip(answer.solution.joint_trajectory.joint_names, points[-1].positions))
        endpoint.joint_state.position = [positions.get(name, value) for name, value in
                                        zip(state.joint_state.name, state.joint_state.position)]
    ordered = [[dict(zip(answer.solution.joint_trajectory.joint_names, p.positions))[name]
                for name in names] for p in points]
    bounds_ok = all(task['real_trajectory_joint_min'][i] <= values[i] <=
                    task['real_trajectory_joint_max'][i] for values in ordered for i in range(6))
    maximum_adjacent = max((abs(a-b) for first, second in zip(ordered, ordered[1:])
                            for a, b in zip(first, second)), default=0.)
    return {'fraction': answer.fraction, 'error_code': answer.error_code.val,
            'points': len(points), 'endpoint_q': list(endpoint.joint_state.position[:6]),
            'within_original_task_bounds': bounds_ok,
            'maximum_adjacent_joint_step_rad': maximum_adjacent}, endpoint


state = RobotState()
state.joint_state.name = names + ['joint7', 'joint8']
state.joint_state.position = q + [.0498, -.0498]
valid = GetStateValidity.Request()
valid.group_name = 'arm'
valid.robot_state = state
checked = call('/check_state_validity', valid)
start = fk(state)
report = {'hardware_executed': False, 'domain': 78, 'scene': 'isolated model, not live scene',
          'start_q': q, 'surface': surface, 'start_valid': checked.valid,
          'start_contacts': [[c.contact_body_1, c.contact_body_2] for c in checked.contacts],
          'candidates': []}
for downward in [.5, .25, .1, .75, 1.]:
    values = [start.position.x, start.position.y, start.position.z,
              start.orientation.x, start.orientation.y, start.orientation.z, start.orientation.w,
              *surface, task['gripper_tip_offset_m'],
              task['top_down_pregrasp_clearance_m'] + task['grasp_height_offset_m'],
              insertion - task['grasp_height_offset_m'], .005, downward]
    geometry = json.loads(subprocess.check_output([helper, *map(str, values)], text=True))
    pre, pre_state = plan(state, geometry['pregrasp'])
    row = {'downward_fraction': downward, 'pre_waypoints': len(geometry['pregrasp']),
           'descent_waypoints': len(geometry['descent']), 'pre': pre}
    if pre['fraction'] >= .995:
        descent, _ = plan(pre_state, geometry['descent'])
        row['descent'] = descent
    report['candidates'].append(row)

# Diagnostic counterfactual only: identical terminal capture endpoint/clearance,
# but blend wrist attitude with tip travel instead of the initial in-place aim.
# This is NOT used by the executor and does not send any motion.
values[-1] = .5
geometry = json.loads(subprocess.check_output([helper, *map(str, values)], text=True))
start_rot = Rotation.from_quat([start.orientation.x, start.orientation.y,
                               start.orientation.z, start.orientation.w])
local_tip = np.array([0., 0., task['gripper_tip_offset_m']])
start_tip = np.array([start.position.x, start.position.y, start.position.z]) + start_rot.apply(local_tip)
end_pose = geometry['descent'][-1]
final_rot = Rotation.from_quat(end_pose['orientation'])
end_tip = np.array(end_pose['origin']) + final_rot.apply(local_tip)
pre_tip = np.array(surface) - final_rot.apply(np.array([0., 0.,
    task['top_down_pregrasp_clearance_m'] + task['grasp_height_offset_m']]))


def blended(first_tip, last_tip, first_rot, last_rot):
    turn = (first_rot.inv()*last_rot).as_rotvec()
    count = max(1, int(np.ceil((np.linalg.norm(last_tip-first_tip) +
                              np.linalg.norm(turn)*np.linalg.norm(local_tip))/.005)))
    poses = []
    for i in range(1, count+1):
        s = i/count
        rotation = first_rot*Rotation.from_rotvec(turn*s)
        origin = first_tip+(last_tip-first_tip)*s-rotation.apply(local_tip)
        poses.append({'origin': origin.tolist(), 'orientation': rotation.as_quat().tolist()})
    return poses


pre, pre_state = plan(state, blended(start_tip, pre_tip, start_rot, final_rot))
row = {'diagnostic_only': True, 'strategy': 'blend_turn_and_approach_same_capture_endpoint',
       'pre': pre}
if pre['fraction'] >= .995:
    descent, _ = plan(pre_state, blended(pre_tip, end_tip, final_rot, final_rot))
    row['descent'] = descent
report['counterfactual'] = row
production = json.loads(subprocess.check_output([helper, *map(str, values), '1'], text=True))
pre, pre_state = plan(state, production['pregrasp'])
row = {'strategy': 'approved_shared_cpp_synchronized_geometry',
       'pre_waypoints': len(production['pregrasp']), 'descent_waypoints': len(production['descent']),
       'pre': pre}
if pre['fraction'] >= .995:
    descent, _ = plan(pre_state, production['descent'])
    row['descent'] = descent
report['shared_cpp_synchronized'] = row
print(json.dumps(report, indent=2))
node.destroy_node()
rclpy.shutdown()
