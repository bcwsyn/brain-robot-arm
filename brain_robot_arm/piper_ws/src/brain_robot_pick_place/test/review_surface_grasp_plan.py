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
import yaml
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, Quaternion
from moveit_msgs.msg import Constraints, PositionConstraint, OrientationConstraint, RobotState
from moveit_msgs.srv import GetMotionPlan, GetCartesianPath, GetPositionFK
from shape_msgs.msg import SolidPrimitive
from sensor_msgs.msg import JointState

if os.environ.get('ROS_DOMAIN_ID') != '78':
    raise RuntimeError('Use isolated ROS domain 78')
with open('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml') as f:
    P = yaml.safe_load(f)['grasp_lift_executor']['ros__parameters']
Q = ([-0.0, 0.98, -0.75, 0.0, 0.30, 0.0]
     if os.environ.get('PIPER_REVIEW_START') == 'observe' else
     [-.481960276,1.256700648,-.931352604,.186301920,1.027259716,-.553219016])
OBJECT = [.260, -.092, .136]
FACE_EDGE = .032  # Recorded static cube face estimate; not a new live sample.
INSERTION = min(FACE_EDGE * P['surface_insertion_fraction'], P['surface_insertion_max_m'])
NAMES = [f'joint{i}' for i in range(1,7)]

def pose(clearance, tilt, yaw):
    # Same PopulateTopDownPose/TopDownOrientation formula as the executor.
    pitch = math.pi - tilt
    result = Pose()
    result.orientation = Quaternion(x=-math.sin(yaw/2)*math.sin(pitch/2),
        y=math.cos(yaw/2)*math.sin(pitch/2), z=math.sin(yaw/2)*math.cos(pitch/2),
        w=math.cos(yaw/2)*math.cos(pitch/2))
    axis = [math.cos(yaw)*math.sin(pitch),math.sin(yaw)*math.sin(pitch),math.cos(pitch)]
    d = P.get('gripper_tip_offset_m',.1358)+P.get('grasp_height_offset_m',0.)+clearance
    result.position.x,result.position.y,result.position.z = [v-a*d for v,a in zip(OBJECT,axis)]
    return result

rclpy.init()
n = Node('snapshot_grasp_plan_review')
pub = n.create_publisher(JointState,'/joint_states',10)
state = RobotState()
state.joint_state.name = NAMES+['joint7','joint8']
state.joint_state.position = Q+[.0231,-.0231]
def publish():
    state.joint_state.header.stamp = n.get_clock().now().to_msg()
    pub.publish(state.joint_state)
n.create_timer(.05,publish)
plan = n.create_client(GetMotionPlan,'/plan_kinematic_path')
cart = n.create_client(GetCartesianPath,'/compute_cartesian_path')
fk = n.create_client(GetPositionFK,'/compute_fk')

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

try:
    found = False
    for tilt in P['top_down_tilt_candidates']:
        for yaw in P['top_down_yaw_candidates']:
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
            pc.constraint_region.primitives = [SolidPrimitive(type=SolidPrimitive.SPHERE,dimensions=[.01])]
            region = Pose()
            region.position = pre.position
            region.orientation.w = 1.
            pc.constraint_region.primitive_poses = [region]
            oc = OrientationConstraint()
            oc.header.frame_id = 'base_link'
            oc.link_name = 'link6'
            oc.orientation = pre.orientation
            oc.weight = 1.
            oc.absolute_x_axis_tolerance=oc.absolute_y_axis_tolerance=oc.absolute_z_axis_tolerance=.20
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
                print('SNAPSHOT_PREGRASP_AND_DESCENT_PLANNED_NO_EXECUTION',flush=True)
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
