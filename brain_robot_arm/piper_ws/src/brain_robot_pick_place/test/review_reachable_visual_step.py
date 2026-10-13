"""Reuse isolated MoveIt FK/state/path services for exact logged visual steps.

Domain 78 only. No driver, motion publisher, execution or enable client.
"""
import argparse
import copy
import itertools
import json
import os
from pathlib import Path
import re

import numpy as np
import rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.msg import RobotState
from moveit_msgs.srv import GetCartesianPath, GetPositionFK, GetStateValidity
from scipy.spatial.transform import Rotation
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--steps', type=int, nargs='+', required=True)
    parser.add_argument('--fractions', type=float, nargs='+',
                        default=[1., .75, .5, .25, 0., -.25, -.5, -.75, -1.],
                        help='Isolated counterfactuals only; does not change production candidates')
    parser.add_argument('--tip-fractions', type=float, nargs='+', default=[1.],
                        help='Isolated translation prefixes; zero rotates about current tip only')
    args = parser.parse_args()
    assert os.environ.get('ROS_DOMAIN_ID') == '78'
    log = args.log.read_text()
    task = yaml.safe_load(args.task.read_text())['grasp_lift_executor']['ros__parameters']
    names = [f'joint{i}' for i in range(1, 7)]
    rclpy.init()
    node = rclpy.create_node('reachable_visual_step_read_only_review')
    clients = {name: node.create_client(kind, name) for name, kind in [
        ('/compute_cartesian_path', GetCartesianPath), ('/compute_fk', GetPositionFK),
        ('/check_state_validity', GetStateValidity)]}

    def call(name, request):
        client = clients[name]
        assert client.wait_for_service(timeout_sec=20), name + ' unavailable'
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=15)
        assert future.done() and future.result() is not None, name + ' timeout'
        return future.result()

    report = {'hardware_executed': False, 'domain': 78,
              'scene': 'isolated current model, not live collision scene', 'stages': []}
    try:
        for step in args.steps:
            stage = 'AUTOMATIC_RGB_STEP_' + str(step)
            q = [float(re.search(stage + r' PLAN_START ' + name + r'=([-\d.]+)', log).group(1))
                 for name in names]
            state = RobotState()
            state.joint_state.name = names + ['joint7', 'joint8']
            state.joint_state.position = q + [.0498, -.0498]
            check = GetStateValidity.Request()
            check.group_name = 'arm'; check.robot_state = state
            valid = call('/check_state_validity', check)
            fk = GetPositionFK.Request()
            fk.header.frame_id = 'base_link'; fk.fk_link_names = ['link6']; fk.robot_state = state
            answer = call('/compute_fk', fk)
            assert answer.error_code.val == 1, 'FK failed'
            current = answer.pose_stamped[0].pose
            base = Rotation.from_quat([current.orientation.x, current.orientation.y,
                                       current.orientation.z, current.orientation.w])
            origin = np.array([current.position.x, current.position.y, current.position.z])
            match = re.search(stage + r' POSE_REQUEST frame=base_link xyz=\(([^)]+)\) q=\(([^)]+)\)', log)
            desired = Rotation.from_quat(list(map(float, match.group(2).split(','))))
            wanted = np.array(list(map(float, match.group(1).split(','))))
            local = np.array([0, 0, task['gripper_tip_offset_m']])
            fixed_tip = wanted + desired.apply(local)
            start_tip = origin + base.apply(local)
            row = {'step': step, 'start_q': q, 'start_valid': valid.valid,
                   'contacts': [[c.contact_body_1, c.contact_body_2] for c in valid.contacts],
                   'requested_tip_step_m': float(np.linalg.norm(fixed_tip-origin-base.apply(local))),
                   'requested_turn_rad': float((base.inv()*desired).magnitude()), 'candidates': []}
            for tip_fraction, fraction in itertools.product(args.tip_fractions, args.fractions):
                # Counterfactual zero turn is analysis only; production still omits it.
                rotation = base*Rotation.from_rotvec((base.inv()*desired).as_rotvec()*fraction)
                candidate_tip = start_tip + tip_fraction*(fixed_tip-start_tip)
                xyz = candidate_tip-rotation.apply(local)
                pose = Pose()
                pose.position.x, pose.position.y, pose.position.z = map(float, xyz)
                (pose.orientation.x, pose.orientation.y,
                 pose.orientation.z, pose.orientation.w) = map(float, rotation.as_quat())
                request = GetCartesianPath.Request()
                request.header.frame_id = 'base_link'; request.group_name = 'arm'; request.link_name = 'link6'
                request.start_state = copy.deepcopy(state); request.waypoints = [pose]
                request.max_step = .005; request.jump_threshold = 0.; request.avoid_collisions = True
                response = call('/compute_cartesian_path', request)
                assert response.error_code.val != -21, 'Cartesian frame unavailable'
                jt = response.solution.joint_trajectory
                values = [dict(zip(jt.joint_names, p.positions)) for p in jt.points]
                within = all(task['real_trajectory_joint_min'][i] <= v[name] <=
                             task['real_trajectory_joint_max'][i] for v in values
                             for i, name in enumerate(names))
                row['candidates'].append({'orientation_fraction': fraction,
                    'tip_fraction': tip_fraction,
                    'absolute_turn_rad': float((base.inv()*rotation).magnitude()),
                    'path_fraction': response.fraction, 'error_code': response.error_code.val,
                    'within_original_task_bounds': within, 'points': len(jt.points),
                    'endpoint': values[-1] if values else {},
                    'tip_preservation_error_m': float(np.linalg.norm(xyz+rotation.apply(local)-candidate_tip))})
            report['stages'].append(row)
        print(json.dumps(report, indent=2))
    finally:
        node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
