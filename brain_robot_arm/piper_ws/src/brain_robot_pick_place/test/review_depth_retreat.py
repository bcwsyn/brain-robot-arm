#!/usr/bin/env python3
"""Read-only 10 mm depth-camera backward LIN planning; never execute."""
import argparse
from collections import deque
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import cv2
from cv_bridge import CvBridge
import numpy as np
import rclpy
import yaml
from moveit_msgs.msg import Constraints, OrientationConstraint, PositionConstraint
from moveit_msgs.srv import GetMotionPlan, GetPositionFK
from rcl_interfaces.srv import GetParameters
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.convert import message_to_ordereddict
from scipy.spatial.transform import Rotation
from sensor_msgs.msg import Image, JointState
from shape_msgs.msg import SolidPrimitive
from tf2_ros import Buffer, TransformListener
from review_calibration_sampling import NAMES, checked_trajectory, tool_pose
from review_camera_jaw_alignment import wait_for_tf_initialization, wait_for_stamped_transform


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refuse to overwrite evidence')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    task_path = Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
    task_bytes = task_path.read_bytes()
    task = yaml.safe_load(task_bytes)['grasp_lift_executor']['ros__parameters']
    report = {'read_only': True, 'hardware_executed': False, 'validated': False,
              'uses_target_depth': False, 'purpose': 'Review camera-view recovery by 10mm optical -Z retreat',
              'task_path': str(task_path), 'task_sha256': hashlib.sha256(task_bytes).hexdigest(),
              'allowed_service_calls': ['/move_group/get_parameters', '/compute_fk', '/plan_kinematic_path'],
              'velocity_scaling': .005, 'acceleration_scaling': .005,
              'maximum_tip_path_m': .015, 'camera_delta_requested_m': [0., 0., -.010],
              'physical_clearance_verified': False, 'execution_authorized': False}
    rclpy.init()
    node = rclpy.create_node('read_only_depth_retreat_review')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    latest, receipts = {}, {}
    history = deque(maxlen=100)

    def receive(message, label):
        latest[label], receipts[label] = message, time.monotonic()
        if label == 'feedback':
            history.append(message)

    subscriptions = [
        node.create_subscription(JointState, '/joint_states_feedback',
            lambda message: receive(message, 'feedback'), qos_profile_sensor_data),
        node.create_subscription(Image, '/camera/color/image_raw',
            lambda message: receive(message, 'rgb'), qos_profile_sensor_data)]

    def call(kind, service, request):
        if service not in report['allowed_service_calls']:
            raise RuntimeError('Forbidden service')
        client = node.create_client(kind, service)
        try:
            if not client.wait_for_service(timeout_sec=8):
                raise RuntimeError('Missing ' + service)
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=10)
            if not future.done() or future.result() is None:
                raise RuntimeError('Timeout ' + service)
            return future.result()
        finally:
            node.destroy_client(client)

    def qmap(message):
        if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
            raise RuntimeError('Invalid physical feedback names/positions')
        result = dict(zip(message.name, message.position))
        if not all(math.isfinite(result[name]) for name in NAMES + ['gripper']):
            raise RuntimeError('Nonfinite physical feedback')
        return result

    try:
        wait_for_tf_initialization(buffer, 'base_link', 'camera_depth_optical_frame',
            lambda: rclpy.spin_once(node, timeout_sec=.025))
        latest.clear(); receipts.clear(); history.clear()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.025)
            if len(latest) == 2 and len(history) >= 50 and all(
                    time.monotonic() - value < .6 for value in receipts.values()):
                break
        if len(latest) != 2 or len(history) < 50:
            raise RuntimeError('Missing new RGB or 50 physical feedback samples')
        rgb, feedback = latest['rgb'], latest['feedback']
        measured = qmap(feedback)
        q = [measured[name] for name in NAMES]
        stamp = rclpy.time.Time.from_msg(rgb.header.stamp)
        feedback_stamp = rclpy.time.Time.from_msg(feedback.header.stamp)
        now_ns = node.get_clock().now().nanoseconds
        image_age = (now_ns - stamp.nanoseconds) / 1e9
        feedback_age = (now_ns - feedback_stamp.nanoseconds) / 1e9
        if not 0 <= image_age <= .6 or not 0 <= feedback_age <= .2:
            raise RuntimeError('Stale/future image or feedback')
        if rgb.header.frame_id != 'camera_color_optical_frame' or rgb.width < 1 or rgb.height < 1:
            raise RuntimeError('Unexpected raw RGB frame or size')
        histories = [qmap(message) for message in history]
        spreads = [max(h[name] for h in histories) - min(h[name] for h in histories) for name in NAMES]
        if max(spreads) > .001:
            raise RuntimeError('Physical start not stationary')
        opening = measured['gripper']
        if not 0 <= opening <= .080:
            raise RuntimeError('Invalid physical gripper opening')
        fingers = [opening / 2., -opening / 2.]
        transform = wait_for_stamped_transform(buffer, 'base_link', 'camera_depth_optical_frame',
            stamp, lambda: rclpy.spin_once(node, timeout_sec=.01))
        values = call(GetParameters, '/move_group/get_parameters', GetParameters.Request(
            names=['robot_description', 'allow_trajectory_execution'])).values
        if len(values) != 2 or values[1].type != 1 or values[1].bool_value:
            raise RuntimeError('MoveIt execution must remain disabled')
        root = ET.fromstring(values[0].string_value)
        finger_limits = {}
        for name, position in zip(['joint7', 'joint8'], fingers):
            limit = root.find(f"joint[@name='{name}']/limit")
            if limit is None or not float(limit.get('lower')) <= position <= float(limit.get('upper')):
                raise RuntimeError('Measured opening outside loaded finger model: ' + name)
            finger_limits[name] = [float(limit.get('lower')), float(limit.get('upper'))]
        fk = GetPositionFK.Request()
        fk.header.frame_id = 'base_link'
        fk.fk_link_names = ['link6']
        fk.robot_state.joint_state.name = NAMES + ['joint7', 'joint8']
        fk.robot_state.joint_state.position = q + fingers
        fk.robot_state.joint_state.header = copy.deepcopy(feedback.header)
        answer = call(GetPositionFK, '/compute_fk', fk)
        if answer.error_code.val != 1 or not answer.pose_stamped:
            raise RuntimeError('Measured-start FK failed')
        pose = copy.deepcopy(answer.pose_stamped[0].pose)
        start_pose = copy.deepcopy(pose)
        rotation = transform.transform.rotation
        camera_rotation = Rotation.from_quat([rotation.x, rotation.y, rotation.z, rotation.w])
        delta = camera_rotation.apply([0., 0., -.010])
        pose.position.x += float(delta[0]); pose.position.y += float(delta[1]); pose.position.z += float(delta[2])
        motion = GetMotionPlan.Request()
        m = motion.motion_plan_request
        m.group_name = 'arm'; m.pipeline_id = task['real_pose_planning_pipeline']; m.planner_id = 'LIN'
        m.start_state = fk.robot_state; m.num_planning_attempts = 1; m.allowed_planning_time = 2.
        m.max_velocity_scaling_factor = .005; m.max_acceleration_scaling_factor = .005
        pc = PositionConstraint(); pc.header.frame_id = 'base_link'; pc.link_name = 'link6'; pc.weight = 1.
        pc.constraint_region.primitives = [SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[.00002] * 3)]
        pc.constraint_region.primitive_poses = [pose]
        oc = OrientationConstraint(); oc.header.frame_id = 'base_link'; oc.link_name = 'link6'
        oc.orientation = pose.orientation; oc.weight = 1.
        oc.absolute_x_axis_tolerance = oc.absolute_y_axis_tolerance = oc.absolute_z_axis_tolerance = .0001
        constraint = Constraints(); constraint.position_constraints = [pc]; constraint.orientation_constraints = [oc]
        m.goal_constraints = [constraint]
        rgb_path = args.output.with_name(args.output.stem + '_rgb.png')
        if rgb_path.exists() or not cv2.imwrite(str(rgb_path), CvBridge().imgmsg_to_cv2(rgb, 'bgr8')):
            raise RuntimeError('Cannot preserve the exact planning RGB evidence')
        report.update(start_q_rad=q, start_q_deg=np.degrees(q).tolist(),
            feedback_age_s=feedback_age, feedback_stamp_ns=str(feedback_stamp.nanoseconds),
            image_age_s=image_age, image_stamp_ns=str(stamp.nanoseconds),
            rgb_frame=rgb.header.frame_id, rgb_size=[rgb.width, rgb.height],
            rgb_path=str(rgb_path), rgb_sha256=hashlib.sha256(rgb_path.read_bytes()).hexdigest(),
            stationary_samples=len(history), stationary_spread_rad=spreads,
            measured_gripper_opening_m=opening, planning_finger_positions_m=fingers,
            loaded_finger_limits_m=finger_limits,
            urdf_sha256=hashlib.sha256(values[0].string_value.encode()).hexdigest(),
            delta_base_m=delta.tolist(), start_link6_pose=message_to_ordereddict(start_pose),
            goal_link6_pose=message_to_ordereddict(pose),
            camera_to_base_transform=message_to_ordereddict(transform), request=message_to_ordereddict(motion))
        response = call(GetMotionPlan, '/plan_kinematic_path', motion).motion_plan_response
        report['response'] = message_to_ordereddict(response)
        if response.error_code.val != 1 or not response.trajectory.joint_trajectory.points:
            raise RuntimeError('LIN planning failed: ' + str(response.error_code.val))
        jt = response.trajectory.joint_trajectory
        order = [jt.joint_names.index(name) for name in NAMES]
        ordered_positions = [[point.positions[index] for index in order] for point in jt.points]
        goal_q = ordered_positions[-1]
        checks = checked_trajectory(jt.joint_names, [point.positions for point in jt.points], q, goal_q, task)
        tip = np.array([0., 0., task['gripper_tip_offset_m'], 1.])
        tips = np.array([(tool_pose(root, positions) @ tip)[:3] for positions in ordered_positions])
        path_length = float(np.linalg.norm(np.diff(tips, axis=0), axis=1).sum())
        displacement = float(np.linalg.norm(tips - tips[0], axis=1).max())
        duration = jt.points[-1].time_from_start.sec + jt.points[-1].time_from_start.nanosec / 1e9
        if path_length > .015 or displacement > .015:
            raise RuntimeError('Tip path or displacement exceeds 15mm')
        latest_q = qmap(latest['feedback'])
        if max(abs(latest_q[name] - value) for name, value in zip(NAMES, q)) > .001:
            raise RuntimeError('Actual pose changed while planning')
        report.update(validated=True, goal_q_rad=goal_q, goal_q_deg=np.degrees(goal_q).tolist(),
            joint_delta_deg=np.degrees(np.asarray(goal_q) - q).tolist(), validation=checks,
            model_tip_arc_m=path_length, max_model_tip_displacement_m=displacement,
            model_tip_delta_base_m=(tips[-1] - tips[0]).tolist(), duration_s=duration,
            max_trajectory_velocity_rad_s=max(abs(v) for p in jt.points for v in p.velocities),
            max_trajectory_acceleration_rad_s2=max(abs(v) for p in jt.points for v in p.accelerations))
        print(json.dumps({key: value for key, value in report.items() if key not in
            ('request', 'response', 'camera_to_base_transform')}, indent=2))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()


if __name__ == '__main__':
    main()
