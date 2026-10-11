#!/usr/bin/env python3
"""Review proposed hand-eye samples; never execute them or calibrate production TF.

Inputs are an archived actual URDF, actual task YAML and explicit historical
static-capture evidence. --plan optionally uses the existing isolated domain-78
MoveIt review launch. It records complete responses rather than terminal excerpts.
No execution client, physical command publisher, CAN or driver operation exists.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from review_jaw_scene import poses


NAMES = [f'joint{i}' for i in range(1, 7)]


def sample_states(start, angle_deg):
    q = np.asarray(start, dtype=float)
    if q.shape != (6,) or not np.isfinite(q).all():
        raise ValueError('An explicit finite six-axis historical start is required')
    if not math.isfinite(angle_deg) or not 0 < angle_deg <= 6:
        raise ValueError('Review the defined proposal only: 0 < angle <= 6 degrees')
    states = [('centre', q.copy())]
    for axis in (3, 4):
        for sign in (-1, 1):
            target = q.copy()
            target[axis] += sign * math.radians(angle_deg)
            states.append((f'J{axis + 1}{sign * angle_deg:+g}deg', target))
    return states


def task_limits(params):
    lo = np.asarray(params['real_trajectory_joint_min'], dtype=float)
    hi = np.asarray(params['real_trajectory_joint_max'], dtype=float)
    if lo.shape != (6,) or hi.shape != (6,) or not np.isfinite([lo, hi]).all() or np.any(lo > hi):
        raise ValueError('Invalid unchanged task joint limits')
    return lo, hi


def tool_pose(root, q):
    positions = dict(zip(NAMES, map(float, q)))
    # Match the archived model placeholder, not a measured physical opening.
    positions.update(joint7=0.0, joint8=0.0)
    return poses(root, positions)['gripper_base']


def synthetic_convention_check(transforms):
    """Known-transform sanity check only; never return a deployable calibration."""
    x, fixed = np.eye(4), np.eye(4)
    x[:3, :3] = Rotation.from_euler('xyz', [12, -25, 7], degrees=True).as_matrix()
    x[:3, 3] = [-.04, .01, .03]
    fixed[:3, :3] = Rotation.from_euler('xyz', [7, -13, 9], degrees=True).as_matrix()
    fixed[:3, 3] = [.3, -.12, .05]
    camera = [np.linalg.inv(t @ x) @ fixed for t in transforms]
    rotation, translation = cv2.calibrateHandEye(
        [t[:3, :3] for t in transforms], [t[:3, 3] for t in transforms],
        [t[:3, :3] for t in camera], [t[:3, 3] for t in camera],
        method=cv2.CALIB_HAND_EYE_PARK)
    result = {'synthetic_not_hardware_calibration': True,
              'finite_solution': bool(np.isfinite(rotation).all() and np.isfinite(translation).all())}
    if result['finite_solution']:
        result.update(rotation_error_deg=float(math.degrees(
            Rotation.from_matrix(rotation.T @ x[:3, :3]).magnitude())),
            translation_error_m=float(np.linalg.norm(translation.ravel() - x[:3, 3])))
    return result


def geometry_report(root, params, start, angle_deg):
    states = sample_states(start, angle_deg)
    lo, hi = task_limits(params)
    for label, q in states:
        if np.any(q < lo) or np.any(q > hi):
            raise ValueError(f'{label} violates unchanged task limits')
        for name, value in zip(NAMES, q):
            joint = root.find(f"joint[@name='{name}']")
            if joint is None or joint.find('limit') is None:
                raise ValueError(f'Missing URDF joint/limits for {name}')
            bounds = joint.find('limit').attrib
            if not float(bounds['lower']) <= value <= float(bounds['upper']):
                raise ValueError(f'{label}/{name} violates URDF limits')
    tip_offset = float(params['gripper_tip_offset_m'])
    if not math.isfinite(tip_offset) or tip_offset <= 0:
        raise ValueError('Invalid existing model tip offset')
    tip = np.array([0., 0., tip_offset, 1.])
    transforms = [tool_pose(root, q) for _, q in states]
    segments, translation_rows, vectors = [], [], []
    for (label, q), target in zip(states[1:], transforms[1:]):
        relative = transforms[0][:3, :3].T @ target[:3, :3]
        translation_rows.append(relative - np.eye(3))
        vectors.append(Rotation.from_matrix(relative).as_rotvec())
        curve = [tool_pose(root, states[0][1] + f * (q - states[0][1]))
                 for f in np.linspace(0, 1, 51)]
        tips = np.array([(t @ tip)[:3] for t in curve])
        length = float(np.linalg.norm(np.diff(tips, axis=0), axis=1).sum())
        displacement = float(np.linalg.norm(tips - tips[0], axis=1).max())
        for backwards in (False, True):
            segments.append({'label': f'{label}->centre' if backwards else f'centre->{label}',
                             'start_q_rad': (q if backwards else states[0][1]).tolist(),
                             'goal_q_rad': (states[0][1] if backwards else q).tolist(),
                             'model_tip_arc_length_m': length,
                             'model_tip_max_distance_from_centre_m': displacement})
    singular = np.linalg.svd(np.vstack(translation_rows), compute_uv=False)
    a, b = vectors[1], vectors[3]
    cosine = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return {'mode': 'OFFLINE_REVIEW_NO_HARDWARE_COMMANDS',
            'historical_not_live_start': True, 'model_gripper_placeholder': True,
            'physical_opening_or_table_clearance_verified': False,
            'samples': [{'label': label, 'q_rad': q.tolist(), 'base_from_tool': t.tolist()}
                        for (label, q), t in zip(states, transforms)],
            'segments': segments,
            'model_tip_total_arc_length_m': sum(s['model_tip_arc_length_m'] for s in segments),
            'excitation': {'translation_singular_values': singular.tolist(),
                           'translation_condition_number': float(singular[0] / singular[-1])
                           if singular[-1] > 1e-10 else None,
                           'axis_angle_deg': math.degrees(math.acos(float(np.clip(cosine, -1, 1))))},
            'synthetic_convention_check': synthetic_convention_check(transforms)}


def checked_trajectory(joint_names, points, start, goal, params):
    if len(joint_names) != 6 or set(joint_names) != set(NAMES) or not points:
        raise ValueError('Planning response must contain all six axes and nonempty points')
    raw = np.asarray(points, dtype=float)
    if raw.shape != (len(points), 6) or not np.isfinite(raw).all():
        raise ValueError('Invalid/nonfinite trajectory positions')
    order = [joint_names.index(name) for name in NAMES]
    values = raw[:, order]
    lo, hi = task_limits(params)
    if np.any(values < lo) or np.any(values > hi):
        raise ValueError('Trajectory violates unchanged task limits')
    if np.max(np.abs(values[0] - start)) > 1e-4 or np.max(np.abs(values[-1] - goal)) > 1e-4:
        raise ValueError('Planned trajectory endpoint differs from explicit sample')
    return {'points': len(points), 'task_limits_passed': True,
            'max_adjacent_step_rad': float(np.abs(np.diff(values, axis=0)).max())
            if len(points) > 1 else 0.0}


def require_isolated_domain():
    if os.environ.get('ROS_DOMAIN_ID') != '78':
        raise RuntimeError('--plan requires the existing isolated review domain 78')


def plan_report(report, params, urdf_sha256):
    # Guard before importing/initializing ROS; no production graph interaction.
    require_isolated_domain()
    import rclpy
    from moveit_msgs.msg import Constraints, JointConstraint, PlanningSceneComponents, RobotState
    from moveit_msgs.srv import GetMotionPlan, GetPlanningScene
    from rcl_interfaces.msg import ParameterType
    from rcl_interfaces.srv import GetParameters
    from rosidl_runtime_py.convert import message_to_ordereddict
    from sensor_msgs.msg import JointState

    rclpy.init()
    node = rclpy.create_node('read_only_calibration_sampling_review')
    try:
        def call(kind, service, request):
            client = node.create_client(kind, service)
            try:
                if not client.wait_for_service(timeout_sec=5):
                    raise RuntimeError(f'Missing review service {service}')
                future = client.call_async(request)
                rclpy.spin_until_future_complete(node, future, timeout_sec=5)
                if not future.done() or future.result() is None:
                    raise RuntimeError(f'Review service timeout {service}')
                return future.result()
            finally:
                node.destroy_client(client)

        request = GetParameters.Request()
        request.names = ['allow_trajectory_execution', 'robot_description']
        response = call(GetParameters, '/move_group/get_parameters', request)
        if (len(response.values) != 2 or response.values[0].type != ParameterType.PARAMETER_BOOL
                or response.values[0].bool_value):
            raise RuntimeError('Review MoveIt must explicitly disable execution')
        if hashlib.sha256(response.values[1].string_value.encode()).hexdigest() != urdf_sha256:
            raise RuntimeError('Live review model differs from explicit archived URDF')
        request = GetPlanningScene.Request()
        request.components.components = (PlanningSceneComponents.WORLD_OBJECT_NAMES |
                                         PlanningSceneComponents.WORLD_OBJECT_GEOMETRY |
                                         PlanningSceneComponents.OCTOMAP)
        scene = call(GetPlanningScene, '/get_planning_scene', request).scene
        report['live_review'] = {'allow_trajectory_execution': False,
                                'scene_world_ids': [o.id for o in scene.world.collision_objects],
                                'scene_octomap_bytes': len(scene.world.octomap.octomap.data),
                                'physical_environment_verified': False,
                                'complete_planning_responses': []}
        publisher = node.create_publisher(JointState, '/joint_states', 10)
        state = RobotState()
        state.joint_state.name = NAMES + ['joint7', 'joint8']
        state.joint_state.position = report['samples'][0]['q_rad'] + [0., 0.]

        def heartbeat():
            state.joint_state.header.stamp = node.get_clock().now().to_msg()
            publisher.publish(state.joint_state)

        node.create_timer(.05, heartbeat)
        for segment in report['segments']:
            state.joint_state.position = segment['start_q_rad'] + [0., 0.]
            heartbeat()
            request = GetMotionPlan.Request()
            motion = request.motion_plan_request
            motion.group_name = 'arm'
            motion.pipeline_id = params['real_pose_planning_pipeline']
            motion.planner_id = 'PTP'
            motion.num_planning_attempts = 1
            motion.allowed_planning_time = 2.
            motion.max_velocity_scaling_factor = .02
            motion.max_acceleration_scaling_factor = .02
            motion.start_state = state
            goal = Constraints()
            for name, value in zip(NAMES, segment['goal_q_rad']):
                goal.joint_constraints.append(JointConstraint(
                    joint_name=name, position=value, tolerance_above=1e-5,
                    tolerance_below=1e-5, weight=1.))
            motion.goal_constraints = [goal]
            answer = call(GetMotionPlan, '/plan_kinematic_path', request).motion_plan_response
            record = {'label': segment['label'], 'response': message_to_ordereddict(answer)}
            report['live_review']['complete_planning_responses'].append(record)
            if answer.error_code.val != 1:
                raise RuntimeError(f"Planning failed: {segment['label']}, code {answer.error_code.val}")
            trajectory = answer.trajectory.joint_trajectory
            record['validation'] = checked_trajectory(
                trajectory.joint_names, [p.positions for p in trajectory.points],
                segment['start_q_rad'], segment['goal_q_rad'], params)
        report['live_review']['all_segments_planned'] = True
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urdf', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--start-evidence', required=True, type=Path)
    parser.add_argument('--angle-deg', type=float, default=6.)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--output', required=True, type=Path, help='New JSON artifact; refuses overwrite')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; preserve the previous evidence')
    if args.plan:
        require_isolated_domain()
    inputs = {'urdf': args.urdf, 'config': args.config, 'start_evidence': args.start_evidence}
    data = {name: path.read_bytes() for name, path in inputs.items()}
    params = yaml.safe_load(data['config'])['grasp_lift_executor']['ros__parameters']
    start = json.loads(data['start_evidence'])['static_capture']['q_feedback_rad']
    report = geometry_report(ET.fromstring(data['urdf']), params, start, args.angle_deg)
    report['sources'] = {name: {'path': str(path.resolve()),
                               'sha256': hashlib.sha256(data[name]).hexdigest()}
                         for name, path in inputs.items()}
    result = 0
    if args.plan:
        try:
            plan_report(report, params, report['sources']['urdf']['sha256'])
        except (RuntimeError, ValueError) as error:
            report['live_review_error'] = str(error)
            result = 2
        except KeyboardInterrupt:
            report['live_review_error'] = 'Interrupted; completed planning responses retained, no execution'
            result = 130
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    with args.output.open('x', encoding='utf-8') as output:
        output.write(payload)
    print(json.dumps({'output': str(args.output), 'mode': report['mode'],
                      'segments': len(report['segments']), 'exit_code': result,
                      'all_segments_planned': report.get('live_review', {}).get('all_segments_planned', False)}))
    return result


if __name__ == '__main__':
    raise SystemExit(main())
