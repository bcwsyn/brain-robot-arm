"""2026-10-10 surface-grasp snapshot review, not physical grasp proof.

Run with ROS_DOMAIN_ID=78 and review_surface_grasp_plan.launch.py.
PIPER_REVIEW_START=observe selects the calibrated observation start; otherwise
use the recorded six-axis endpoint from the latest unsuccessful real grasp.
The cube pose/size use configured camera TF and are not external calibration.
No execution client or physical command publisher is created.
"""
import math
import os
import copy
import argparse
import json
import subprocess
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, Quaternion
from moveit_msgs.msg import Constraints, PositionConstraint, OrientationConstraint, RobotState
from moveit_msgs.srv import GetMotionPlan, GetCartesianPath, GetPositionFK, GetPositionIK
from shape_msgs.msg import SolidPrimitive
from sensor_msgs.msg import JointState

if os.environ.get('ROS_DOMAIN_ID') != '78':
    raise RuntimeError('Use isolated ROS domain 78')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, default=Path(
    '/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'))
parser.add_argument('--snapshot', type=Path)
parser.add_argument('--orientation', choices=['top_down', 'measured', 'target_directed'], default='top_down')
parser.add_argument('--geometry-helper', type=Path,
                    help='Compiled read-only C++ target-directed geometry helper')
args = parser.parse_args()
with args.config.open() as f:
    P = yaml.safe_load(f)['grasp_lift_executor']['ros__parameters']
Q = ([-0.0, 0.98, -0.75, 0.0, 0.30, 0.0]
     if os.environ.get('PIPER_REVIEW_START') == 'observe' else
     [-.481960276,1.256700648,-.931352604,.186301920,1.027259716,-.553219016])
OBJECT = [.260, -.092, .136]
FACE_EDGE = .032  # Recorded static cube face estimate; not a new live sample.
MODEL_OPENING = .0462
if args.snapshot:
    snapshot = json.loads(args.snapshot.read_text(encoding='utf-8'))
    if snapshot['snapshot_kind'] != 'historical_not_live' or snapshot['frame'] != 'base_link':
        raise RuntimeError('Only a historical base_link snapshot is accepted')
    Q = snapshot['joint_positions_rad']
    OBJECT = snapshot['target_surface_m']
    FACE_EDGE = min(snapshot['face_size_m'])
    MODEL_OPENING = snapshot['model_gripper_opening_m']
    if len(Q) != 6 or len(OBJECT) != 3 or not all(
            math.isfinite(v) for v in Q + OBJECT + [FACE_EDGE, MODEL_OPENING]):
        raise RuntimeError('Invalid snapshot dimensions/values')
    if not 0 < MODEL_OPENING <= .070 or FACE_EDGE <= 0:
        raise RuntimeError('Invalid hypothetical model gripper opening/cube size')
    if not all(lo <= q <= hi for q, lo, hi in zip(
            Q, P['real_trajectory_joint_min'], P['real_trajectory_joint_max'])):
        raise RuntimeError('Snapshot start violates unchanged task limits')
if args.orientation in ('measured', 'target_directed') and not args.snapshot:
    raise RuntimeError('Measured orientation review requires an explicit frozen snapshot')
INSERTION = min(FACE_EDGE * P['surface_insertion_fraction'], P['surface_insertion_max_m'])
NAMES = [f'joint{i}' for i in range(1,7)]
MEASURED_ORIENTATION = None

def pose(clearance, tilt, yaw):
    # Same PopulateTopDownPose/TopDownOrientation formula as the executor.
    pitch = math.pi - tilt
    result = Pose()
    result.orientation = Quaternion(x=-math.sin(yaw/2)*math.sin(pitch/2),
        y=math.cos(yaw/2)*math.sin(pitch/2), z=math.sin(yaw/2)*math.cos(pitch/2),
        w=math.cos(yaw/2)*math.cos(pitch/2))
    axis = [math.cos(yaw)*math.sin(pitch),math.sin(yaw)*math.sin(pitch),math.cos(pitch)]
    if MEASURED_ORIENTATION is not None:
        result.orientation = copy.deepcopy(MEASURED_ORIENTATION)
        q = result.orientation
        axis = [2*(q.x*q.z+q.w*q.y),2*(q.y*q.z-q.w*q.x),1-2*(q.x*q.x+q.y*q.y)]
    d = P.get('gripper_tip_offset_m',.1358)+P.get('grasp_height_offset_m',0.)+clearance
    result.position.x,result.position.y,result.position.z = [v-a*d for v,a in zip(OBJECT,axis)]
    return result

rclpy.init()
n = Node('snapshot_grasp_plan_review')
pub = n.create_publisher(JointState,'/joint_states',10)
state = RobotState()
state.joint_state.name = NAMES+['joint7','joint8']
state.joint_state.position = Q+[MODEL_OPENING / 2, -MODEL_OPENING / 2]
def publish():
    state.joint_state.header.stamp = n.get_clock().now().to_msg()
    pub.publish(state.joint_state)
n.create_timer(.05,publish)
plan = n.create_client(GetMotionPlan,'/plan_kinematic_path')
cart = n.create_client(GetCartesianPath,'/compute_cartesian_path')
fk = n.create_client(GetPositionFK,'/compute_fk')
ik = n.create_client(GetPositionIK, '/compute_ik')

def call(client, request):
    if not client.wait_for_service(timeout_sec=12.):
        raise RuntimeError('Planning service unavailable')
    future = client.call_async(request)
    rclpy.spin_until_future_complete(n,future,timeout_sec=15.)
    if not future.done() or future.result() is None:
        raise RuntimeError('Planning service timeout')
    return future.result()

def checked(trajectory):
    if not trajectory.points:
        return False
    for pt in trajectory.points:
        for name,x in zip(trajectory.joint_names,pt.positions):
            i = NAMES.index(name)
            if not math.isfinite(x) or not P['real_trajectory_joint_min'][i]<=x<=P['real_trajectory_joint_max'][i]:
                return False
    return all(max(abs(x-y) for x,y in zip(a.positions,b.positions)) <= .35
               for a,b in zip(trajectory.points,trajectory.points[1:]))


def review_target_directed():
    if not args.geometry_helper or not P.get('target_directed_grasp_enabled'):
        raise RuntimeError('Target-directed review requires its configured mode and C++ helper')
    request = GetPositionFK.Request()
    request.header.frame_id = 'base_link'
    request.fk_link_names = ['link6']
    request.robot_state = copy.deepcopy(state)
    start_fk = call(fk, request)
    if start_fk.error_code.val != 1 or not start_fk.pose_stamped:
        raise RuntimeError('Frozen start FK unavailable')
    start = start_fk.pose_stamped[0].pose
    q = start.orientation
    tip_offset = P['gripper_tip_offset_m']
    numbers = [start.position.x, start.position.y, start.position.z,
               q.x, q.y, q.z, q.w] + OBJECT + [tip_offset,
               P['top_down_pregrasp_clearance_m'] + P.get('grasp_height_offset_m', 0.),
               INSERTION - P.get('grasp_height_offset_m', 0.), P.get('cartesian_eef_step_m', .005),
               P.get('target_directed_downward_fraction', .5)]
    path = json.loads(subprocess.check_output(
        [str(args.geometry_helper.resolve())] + [str(v) for v in numbers], text=True))
    print('TARGET_DIRECTED_EXACT_CPP_GEOMETRY_NO_EXECUTION',
          'frozen_start', Q, 'surface', OBJECT, 'start_pose', start, flush=True)
    for stage in ('pregrasp', 'descent'):
        waypoints = []
        for item in path[stage]:
            p = Pose()
            p.position.x, p.position.y, p.position.z = item['origin']
            p.orientation = Quaternion(**dict(zip(('x', 'y', 'z', 'w'), item['orientation'])))
            waypoints.append(p)
        cart_request = GetCartesianPath.Request()
        cart_request.header.frame_id = 'base_link'
        cart_request.group_name = 'arm'
        cart_request.link_name = 'link6'
        cart_request.start_state = copy.deepcopy(state)
        cart_request.max_step = P.get('cartesian_eef_step_m', .005)
        cart_request.jump_threshold = 0.
        cart_request.avoid_collisions = True
        cart_request.waypoints = waypoints
        result = call(cart, cart_request)
        jt = result.solution.joint_trajectory
        max_step = max((max(abs(x-y) for x, y in zip(a.positions, b.positions))
                        for a, b in zip(jt.points, jt.points[1:])), default=0.)
        print('TARGET_DIRECTED_CARTESIAN', stage, 'fraction', result.fraction,
              'code', result.error_code.val, 'requested_waypoints', len(waypoints),
              'points', len(jt.points), 'limits', checked(jt), 'max_joint_step', max_step, flush=True)
        if (result.error_code.val != 1 or result.fraction < .995 or not checked(jt) or
                max_step > P.get('cartesian_max_joint_step_rad', .35)):
            print('PARTIAL_LAST_JOINTS', dict(zip(jt.joint_names,
                  jt.points[-1].positions)) if jt.points else {}, flush=True)
            index = min(len(waypoints) - 1, int(result.fraction * len(waypoints)))
            print('FAILED_WAYPOINT_APPROX_INDEX', index, 'pose', waypoints[index], flush=True)
            for collide, candidate in ((False, waypoints[index]), (True, waypoints[index]),
                                       (False, path['descent'][-1])):
                test = GetPositionIK.Request()
                test.ik_request.group_name = 'arm'
                test.ik_request.ik_link_name = 'link6'
                test.ik_request.pose_stamped.header.frame_id = 'base_link'
                if isinstance(candidate, dict):
                    test.ik_request.pose_stamped.pose.position.x, test.ik_request.pose_stamped.pose.position.y, test.ik_request.pose_stamped.pose.position.z = candidate['origin']
                    test.ik_request.pose_stamped.pose.orientation = Quaternion(**dict(zip(
                        ('x', 'y', 'z', 'w'), candidate['orientation'])))
                else:
                    test.ik_request.pose_stamped.pose = candidate
                test.ik_request.robot_state = copy.deepcopy(state)
                if jt.points:
                    last = dict(zip(jt.joint_names, jt.points[-1].positions))
                    test.ik_request.robot_state.joint_state.position = [last.get(name, x)
                        for name, x in zip(state.joint_state.name, state.joint_state.position)]
                test.ik_request.timeout.sec = 1
                test.ik_request.avoid_collisions = collide
                answer = call(ik, test)
                print('FAILED_WAYPOINT_IK', 'avoid_collisions', collide,
                      'final_endpoint', isinstance(candidate, dict),
                      'code', answer.error_code.val, 'joints', answer.solution.joint_state.position,
                      flush=True)
            raise RuntimeError('Target-directed path incomplete/limited; no execution permitted')
        values = dict(zip(jt.joint_names, jt.points[-1].positions))
        state.joint_state.position = [values.get(name, x) for name, x in
            zip(state.joint_state.name, state.joint_state.position)]
        j5 = jt.joint_names.index('joint5')
        print('JOINT5_MODEL_ONLY_DEGREES', stage,
              [round(math.degrees(p.positions[j5]), 3) for p in jt.points], flush=True)
        request.robot_state = copy.deepcopy(state)
        end_fk = call(fk, request)
        if end_fk.error_code.val != 1 or not end_fk.pose_stamped:
            raise RuntimeError('Segment endpoint FK unavailable')
        measured = end_fk.pose_stamped[0].pose
        q = measured.orientation
        axis = [2*(q.x*q.z+q.w*q.y), 2*(q.y*q.z-q.w*q.x), 1-2*(q.x*q.x+q.y*q.y)]
        tip = [v+a*tip_offset for v, a in zip(
            [measured.position.x, measured.position.y, measured.position.z], axis)]
        goal = waypoints[-1]
        gq = goal.orientation
        goal_axis = [2*(gq.x*gq.z+gq.w*gq.y), 2*(gq.y*gq.z-gq.w*gq.x),
                     1-2*(gq.x*gq.x+gq.y*gq.y)]
        expected = [v+a*tip_offset for v, a in zip(
            [goal.position.x, goal.position.y, goal.position.z], goal_axis)]
        error = math.sqrt(sum((a-b)**2 for a, b in zip(tip, expected)))
        print('TARGET_DIRECTED_ENDPOINT_MODEL_ONLY', stage, 'joints', values,
              'axis', axis, 'tip', tip, 'tip_error_m', error, flush=True)
        if error > P['grasp_landing_tolerance_m']:
            raise RuntimeError('Target-directed model landing failed')
    print('TARGET_DIRECTED_BOTH_SEGMENTS_PLANNED_NO_EXECUTION', flush=True)

try:
    if args.orientation == 'target_directed':
        review_target_directed()
        raise SystemExit(0)
    if args.orientation == 'measured':
        start_fk = GetPositionFK.Request()
        start_fk.header.frame_id = 'base_link'
        start_fk.fk_link_names = ['link6']
        start_fk.robot_state = copy.deepcopy(state)
        current_fk = call(fk, start_fk)
        if current_fk.error_code.val != 1 or not current_fk.pose_stamped:
            raise RuntimeError('Snapshot measured-orientation FK unavailable')
        MEASURED_ORIENTATION = current_fk.pose_stamped[0].pose.orientation
        print('MEASURED_ORIENTATION_MODEL_ONLY', MEASURED_ORIENTATION, flush=True)
        pitch_down = P.get('aligned_grasp_pitch_down_rad', 0.0)
        if pitch_down > 0.0:
            # joint5 is revolute about link5's local +Z in the installed URDF.
            # Match the executor's reference-frame axis-angle composition.
            axis_fk = copy.deepcopy(start_fk)
            axis_fk.fk_link_names = ['link5']
            axis_result = call(fk, axis_fk)
            if axis_result.error_code.val != 1 or not axis_result.pose_stamped:
                raise RuntimeError('Positive J5 axis FK unavailable')
            a = axis_result.pose_stamped[0].pose.orientation
            axis = [2*(a.x*a.z+a.w*a.y), 2*(a.y*a.z-a.w*a.x),
                    1-2*(a.x*a.x+a.y*a.y)]
            scale = math.sin(pitch_down / 2)
            x, y, z = [v * scale for v in axis]
            w = math.cos(pitch_down / 2)
            q = MEASURED_ORIENTATION
            MEASURED_ORIENTATION = Quaternion(
                x=w*q.x+x*q.w+y*q.z-z*q.y,
                y=w*q.y-x*q.z+y*q.w+z*q.x,
                z=w*q.z+x*q.y-y*q.x+z*q.w,
                w=w*q.w-x*q.x-y*q.y-z*q.z)
            print('ALIGNED_GRASP_PITCH_DOWN_MODEL_ONLY', pitch_down,
                  'positive_J5_axis', axis, 'orientation', MEASURED_ORIENTATION, flush=True)
        print('FROZEN_TARGET_NO_CAMERA_CHASING', OBJECT,
              'ACTUAL_GRIPPER_NOT_VERIFIED', snapshot['actual_gripper_feedback_m'], flush=True)
    found = False
    for tilt in ([0.0] if MEASURED_ORIENTATION is not None else P['top_down_tilt_candidates']):
        for yaw in ([0.0] if MEASURED_ORIENTATION is not None else P['top_down_yaw_candidates']):
            pre = pose(P['top_down_pregrasp_clearance_m'],tilt,yaw)
            request = GetMotionPlan.Request()
            m = request.motion_plan_request
            m.start_state = copy.deepcopy(state)
            m.group_name = 'arm'
            m.pipeline_id = P['real_pose_planning_pipeline']
            m.planner_id = P['real_pose_planner_id']
            m.allowed_planning_time = 8.
            m.max_velocity_scaling_factor = .05
            m.max_acceleration_scaling_factor = .05
            c = Constraints()
            pc = PositionConstraint()
            pc.header.frame_id = 'base_link'
            pc.link_name = 'link6'
            pc.weight = 1.
            pc.constraint_region.primitives = [SolidPrimitive(type=SolidPrimitive.SPHERE,dimensions=[
                .001 if MEASURED_ORIENTATION is not None else .01])]
            region = Pose()
            region.position = pre.position
            region.orientation.w = 1.
            pc.constraint_region.primitive_poses = [region]
            oc = OrientationConstraint()
            oc.header.frame_id = 'base_link'
            oc.link_name = 'link6'
            oc.orientation = pre.orientation
            oc.weight = 1.
            oc.absolute_x_axis_tolerance=oc.absolute_y_axis_tolerance=oc.absolute_z_axis_tolerance=(
                .01 if MEASURED_ORIENTATION is not None else .20)
            c.position_constraints=[pc]
            c.orientation_constraints=[oc]
            m.goal_constraints=[c]
            response = call(plan,request).motion_plan_response
            trajectory = response.trajectory.joint_trajectory
            print(f'tilt={tilt:.3f} yaw={yaw:.3f} pregrasp_code={response.error_code.val} points={len(trajectory.points)}',flush=True)
            if response.error_code.val != 1 or not checked(trajectory):
                continue
            descent = GetCartesianPath.Request()
            descent.header.frame_id='base_link'
            descent.group_name='arm'
            descent.link_name='link6'
            descent.start_state=copy.deepcopy(state)
            end = dict(zip(trajectory.joint_names,trajectory.points[-1].positions))
            descent.start_state.joint_state.position=[end.get(name,x) for name,x in zip(state.joint_state.name,state.joint_state.position)]
            descent.max_step=P.get('cartesian_eef_step_m',.005)
            descent.jump_threshold=0.
            descent.avoid_collisions=True
            descent.waypoints=[pose(-INSERTION,tilt,yaw)]
            result=call(cart,descent)
            jt=result.solution.joint_trajectory
            print(f'descent_code={result.error_code.val} fraction={result.fraction:.6f} points={len(jt.points)} limits_continuity={checked(jt)}',flush=True)
            if result.fraction >= .995 and checked(jt):
                print('SNAPSHOT_PREGRASP_AND_DESCENT_PLANNED_NO_EXECUTION',
                      'orientation_mode='+args.orientation, flush=True)
                print('pregrasp_end',end,'descent_end',dict(zip(jt.joint_names,jt.points[-1].positions)),flush=True)
                request_fk = GetPositionFK.Request()
                request_fk.header.frame_id = 'base_link'
                request_fk.fk_link_names = ['link6']
                request_fk.robot_state = copy.deepcopy(state)
                landed = dict(zip(jt.joint_names,jt.points[-1].positions))
                request_fk.robot_state.joint_state.position = [landed.get(name,x)
                    for name,x in zip(state.joint_state.name,state.joint_state.position)]
                actual = call(fk, request_fk)
                if actual.error_code.val != 1 or not actual.pose_stamped:
                    raise RuntimeError('Final FK unavailable')
                measured = actual.pose_stamped[0].pose
                q = measured.orientation
                axis = [2*(q.x*q.z+q.w*q.y),2*(q.y*q.z-q.w*q.x),1-2*(q.x*q.x+q.y*q.y)]
                tip = [x+a*P.get('gripper_tip_offset_m',.1358)
                    for x,a in zip([measured.position.x,measured.position.y,measured.position.z],axis)]
                goal = descent.waypoints[0]
                q = goal.orientation
                expected_axis = [2*(q.x*q.z+q.w*q.y),2*(q.y*q.z-q.w*q.x),1-2*(q.x*q.x+q.y*q.y)]
                expected_tip = [v+a*INSERTION for v,a in zip(OBJECT,expected_axis)]
                error = math.sqrt(sum((a-b)**2 for a,b in zip(tip,expected_tip)))
                print('SURFACE_INSERTION_MODEL',INSERTION,'expected_tip',expected_tip,
                      'fk_tip',tip,'tip_error_m',error,flush=True)
                if error > P['grasp_landing_tolerance_m']:
                    raise RuntimeError('Planned endpoint failed fingertip landing tolerance')
                found=True
                break
        if found:
            break
    if not found:
        print('SNAPSHOT_NO_COMPLETE_TOP_DOWN_PATH',flush=True)
        raise SystemExit(2)
finally:
    n.destroy_node()
    rclpy.shutdown()
