#!/usr/bin/env python3
"""Read-only ONE camera-plane alignment plan using real original ROS inputs.

No execution client, arm/gripper publisher or enable service is created.
The visible jaw line is a screen aim reference, NEVER contact calibration.
No camera translation/hand-eye calibration is inferred or changed here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import PointStamped, PolygonStamped
from moveit_msgs.msg import Constraints, OrientationConstraint, PositionConstraint
from moveit_msgs.srv import GetMotionPlan, GetPositionFK
from rcl_interfaces.srv import GetParameters
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.convert import message_to_ordereddict
from scipy.spatial.transform import Rotation
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformListener

from review_calibration_sampling import NAMES, checked_trajectory, tool_pose


def color_plane_translation(pixel, goal, color_z, image_size, params, maximum_m, forward_m=0.):
    if (not np.isfinite(list(pixel) + list(goal) + [color_z, maximum_m, forward_m]).all() or
            color_z <= .001 or not 0 < maximum_m <= .015 or not 0 <= forward_m <= .010 or
            color_z - forward_m <= .001):
        raise ValueError('Invalid camera-plane alignment inputs')
    width, height = image_size
    if width <= 1 or height <= 1:
        raise ValueError('Invalid source image size')
    # Translate the camera from the measured object ray toward the desired
    # image ray at the slightly smaller depth. This controls image aim and
    # distance together; no arbitrary wrist swing or joint-angle edits.
    full_pixel = np.array(pixel, dtype=float) * [
        (params['color_calibration_width'] - 1) / (width - 1),
        (params['color_calibration_height'] - 1) / (height - 1)]
    full_goal = np.array(goal, dtype=float) * [
        (params['color_calibration_width'] - 1) / (width - 1),
        (params['color_calibration_height'] - 1) / (height - 1)]
    if params['color_mirror_horizontal']:
        full_pixel[0] = params['color_calibration_width'] - 1 - full_pixel[0]
        full_goal[0] = params['color_calibration_width'] - 1 - full_goal[0]
    centre = np.array([params['color_cx'], params['color_cy']])
    focal = np.array([params['color_fx'], params['color_fy']])
    delta_xy = (full_pixel - centre) / focal * color_z - (
        full_goal - centre) / focal * (color_z - forward_m)
    delta = np.r_[delta_xy, forward_m]
    norm = np.linalg.norm(delta)
    if not np.isfinite(norm) or norm <= 1e-6:
        raise ValueError('No meaningful alignment displacement')
    delta *= min(1., maximum_m / norm)
    rotation = np.array(params['depth_to_color_rotation']).reshape(3, 3)
    return np.linalg.solve(rotation, delta)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--goal-pixel', type=float, nargs=2, required=True)
    parser.add_argument('--image-size', type=int, nargs=2, default=[320, 240])
    parser.add_argument('--maximum-m', type=float, default=.015)
    parser.add_argument('--forward-m', type=float, default=0.,
                        help='Optional single <=10mm forward component; still <=15mm total')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refuse to overwrite evidence')
    task = yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
    detector = yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml').read_text())['cube_detector']['ros__parameters']
    rclpy.init()
    node = rclpy.create_node('read_only_camera_jaw_alignment_plan')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    latest, receipts, feedback = {}, {}, []

    def receive(message, topic):
        latest[topic] = message
        receipts[topic] = time.monotonic()
        if topic == 'feedback':
            feedback.append(message)
            del feedback[:-100]

    subscriptions = []
    for kind, name, topic, qos in [
        (JointState, 'feedback', '/joint_states_feedback', qos_profile_sensor_data),
        (PointStamped, 'projection', '/brain_robot_vision/raw_target_projection', 10),
        (PointStamped, 'target', '/brain_robot_vision/target_point_camera', 10),
        (PolygonStamped, 'bbox', '/brain_robot_vision/raw_color_bbox', 10),
        (Bool, 'target_valid', '/brain_robot_vision/target_valid', 10),
        (Bool, 'depth_valid', '/brain_robot_vision/depth_valid', 10)]:
        subscriptions.append(node.create_subscription(kind, topic,
            lambda message, name=name: receive(message, name), qos))

    def call(kind, name, request):
        client = node.create_client(kind, name)
        try:
            if not client.wait_for_service(timeout_sec=8):
                raise RuntimeError('Missing ' + name)
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=10)
            if not future.done() or future.result() is None:
                raise RuntimeError('Timeout ' + name)
            return future.result()
        finally:
            node.destroy_client(client)

    report = {'read_only': True, 'hardware_executed': False,
              'jaw_goal_is_image_reference_not_contact_calibration': True, 'validated': False}
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.025)
            if len(latest) == 6 and len(feedback) >= 50 and all(
                    time.monotonic() - t < .6 for t in receipts.values()):
                if latest['target_valid'].data and latest['depth_valid'].data:
                    break
        if len(latest) != 6 or not latest['target_valid'].data or not latest['depth_valid'].data:
            raise RuntimeError('No live complete associated target')
        if any(time.monotonic() - t > .6 for t in receipts.values()):
            raise RuntimeError('Stale input')
        qmap = dict(zip(latest['feedback'].name, latest['feedback'].position))
        q = [qmap[name] for name in NAMES]
        age_s = (node.get_clock().now().nanoseconds -
                 rclpy.time.Time.from_msg(latest['feedback'].header.stamp).nanoseconds) / 1e9
        if age_s > .2 or age_s < 0 or len(feedback) < 50:
            raise RuntimeError('Fresh physical start unavailable')
        histories = [dict(zip(m.name, m.position)) for m in feedback]
        if any(max(m[name] for m in histories) - min(m[name] for m in histories) > .001
               for name in NAMES):
            raise RuntimeError('Start not stationary')
        point, bbox, projection = (latest[n] for n in ('target', 'bbox', 'projection'))
        stamp = rclpy.time.Time.from_msg(point.header.stamp)
        if any(rclpy.time.Time.from_msg(m.header.stamp).nanoseconds != stamp.nanoseconds
               for m in (bbox, projection)):
            raise RuntimeError('Shape and measured point are not the same image')
        if (node.get_clock().now().nanoseconds - stamp.nanoseconds) / 1e9 > .6:
            raise RuntimeError('Image is stale')
        if len(bbox.polygon.points) != 4 or any(
                p.x <= .02 or p.x >= .98 or p.y <= .02 or p.y >= .98
                for p in bbox.polygon.points):
            raise RuntimeError('Original shape not completely visible for diagnostic alignment')
        transform = buffer.lookup_transform('base_link', point.header.frame_id, stamp)
        values = call(GetParameters, '/move_group/get_parameters', GetParameters.Request(
            names=['robot_description', 'allow_trajectory_execution'])).values
        if len(values) != 2 or values[1].type != 1 or values[1].bool_value:
            raise RuntimeError('MoveIt execution must remain disabled')
        root = ET.fromstring(values[0].string_value)
        request = GetPositionFK.Request()
        request.header.frame_id = 'base_link'
        request.fk_link_names = ['link6']
        request.robot_state.joint_state.name = NAMES + ['joint7', 'joint8']
        request.robot_state.joint_state.position = q + [0., 0.]
        start_state = request.robot_state
        answer = call(GetPositionFK, '/compute_fk', request)
        if answer.error_code.val != 1 or not answer.pose_stamped:
            raise RuntimeError('Measured start FK unavailable')
        pose = answer.pose_stamped[0].pose
        raw_pixel = [projection.point.x * args.image_size[0], projection.point.y * args.image_size[1]]
        delta_depth = color_plane_translation(raw_pixel, args.goal_pixel,
            projection.point.z, args.image_size, detector, args.maximum_m, args.forward_m)
        rotation = transform.transform.rotation
        delta_base = Rotation.from_quat([rotation.x, rotation.y, rotation.z, rotation.w]).apply(delta_depth)
        motion = GetMotionPlan.Request()
        m = motion.motion_plan_request
        m.group_name = 'arm'
        m.pipeline_id = task['real_pose_planning_pipeline']
        m.planner_id = 'LIN'
        m.start_state = start_state
        m.num_planning_attempts = 1
        m.allowed_planning_time = 2.
        m.max_velocity_scaling_factor = .005
        m.max_acceleration_scaling_factor = .005
        constraint = Constraints()
        pc = PositionConstraint()
        pc.header.frame_id = 'base_link'
        pc.link_name = 'link6'
        pc.weight = 1.
        pc.constraint_region.primitives = [SolidPrimitive(type=SolidPrimitive.BOX,
                                                         dimensions=[.00002] * 3)]
        pose.position.x += float(delta_base[0])
        pose.position.y += float(delta_base[1])
        pose.position.z += float(delta_base[2])
        pc.constraint_region.primitive_poses = [pose]
        oc = OrientationConstraint()
        oc.header.frame_id = 'base_link'
        oc.link_name = 'link6'
        oc.orientation = pose.orientation
        oc.absolute_x_axis_tolerance = oc.absolute_y_axis_tolerance = oc.absolute_z_axis_tolerance = .0001
        oc.weight = 1.
        constraint.position_constraints = [pc]
        constraint.orientation_constraints = [oc]
        m.goal_constraints = [constraint]
        report.update(start_q_rad=q, feedback_age_s=age_s,
                      raw_pixel=raw_pixel, goal_pixel=args.goal_pixel,
                      forward_component_requested_m=args.forward_m,
                      delta_depth_m=delta_depth.tolist(), delta_base_m=delta_base.tolist(),
                      camera_to_base_transform=message_to_ordereddict(transform),
                      urdf_sha256=hashlib.sha256(values[0].string_value.encode()).hexdigest(),
                      request=message_to_ordereddict(motion))
        response = call(GetMotionPlan, '/plan_kinematic_path', motion).motion_plan_response
        report['response'] = message_to_ordereddict(response)
        if response.error_code.val != 1 or not response.trajectory.joint_trajectory.points:
            raise RuntimeError('LIN planning failed: ' + str(response.error_code.val))
        jt = response.trajectory.joint_trajectory
        goal_q = jt.points[-1].positions
        checks = checked_trajectory(jt.joint_names, [p.positions for p in jt.points], q, goal_q, task)
        tip = np.array([0., 0., task['gripper_tip_offset_m'], 1.])
        tips = np.array([(tool_pose(root, p.positions) @ tip)[:3] for p in jt.points])
        displacement = np.linalg.norm(tips - tips[0], axis=1)
        path_m = float(np.linalg.norm(np.diff(tips, axis=0), axis=1).sum())
        report.update(goal_q_rad=list(goal_q), validation=checks,
                      model_tip_arc_m=path_m, max_model_tip_displacement_m=float(displacement.max()))
        if path_m > .016 or displacement.max() > .016:
            raise RuntimeError('Planned camera-plane segment exceeds its 15mm aim displacement')
        report['validated'] = True
        print(json.dumps({k: v for k, v in report.items() if k not in
                          ('response', 'request', 'camera_to_base_transform')}, indent=2))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
