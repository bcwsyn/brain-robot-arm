"""Isolated read-only planning to a measured manual posture; never execute."""
import os, time, json, hashlib, copy
from pathlib import Path
import rclpy, yaml
from moveit_msgs.srv import GetMotionPlan, GetStateValidity, GetPlanningScene
from moveit_msgs.msg import JointConstraint, Constraints, PlanningSceneComponents
from rcl_interfaces.srv import GetParameters
assert os.environ.get('ROS_DOMAIN_ID')=='78'
reference=json.loads(Path('/mnt/hgfs/ub/docs/evidence/piper_manual_terminal_snapshot_20261014.json').read_text())
task_path=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
task=yaml.safe_load(task_path.read_text());cfg=task['grasp_lift_executor']['ros__parameters']
names=task['visual_search_controller']['ros__parameters']['joint_names']
observe=task['visual_search_controller']['ros__parameters']['observe_joint_positions']
manual=reference['model']['q_ros_rad']
rclpy.init();node=rclpy.create_node('read_only_manual_endpoint_plan')
allowed={'/move_group/get_parameters','/check_state_validity','/plan_kinematic_path','/get_planning_scene'}
def call(kind,name,req):
 assert name in allowed
 c=node.create_client(kind,name)
 try:
  if not c.wait_for_service(timeout_sec=8):raise RuntimeError('Missing '+name)
  f=c.call_async(req);rclpy.spin_until_future_complete(node,f,timeout_sec=12)
  if not f.done() or f.result() is None:raise RuntimeError('Timeout '+name)
  return f.result()
 finally:node.destroy_client(c)
def state(q,opening):
 from moveit_msgs.msg import RobotState
 s=RobotState();s.joint_state.name=names+['joint7','joint8'];s.joint_state.position=list(q)+[opening/2,-opening/2];s.is_diff=False
 return s
def valid(q,opening):
 req=GetStateValidity.Request();req.robot_state=state(q,opening);req.group_name='arm'
 a=call(GetStateValidity,'/check_state_validity',req)
 return {'valid':a.valid,'contacts':[{'body1':c.contact_body_1,'body2':c.contact_body_2} for c in a.contacts]}
report={'read_only':True,'motion_sent':False,'domain':78,'source_rgb_stamp_ns':reference['rgb_stamp_ns'],
 'source_joint_stamp':reference['feedback_at_rgb_receive']['joint_stamp'],'source_task_sha256':hashlib.sha256(task_path.read_bytes()).hexdigest(),
 'manual_q_ros_rad':manual,'observe_q_ros_rad':observe,'queries':[],
 'warning':'PTP model feasibility only; neither physical clearance, cube contact, nor a full approach/grasp test. 100mm opening is the existing task target, not a new measurement.'}
try:
 a=call(GetParameters,'/move_group/get_parameters',GetParameters.Request(names=['allow_trajectory_execution','robot_description'])).values
 if len(a)!=2 or a[0].type!=1 or a[0].bool_value:raise RuntimeError('Execution is not disabled')
 report['allow_trajectory_execution']=False;report['loaded_urdf_sha256']=hashlib.sha256(a[1].string_value.encode()).hexdigest()
 if report['loaded_urdf_sha256']!=reference['model']['urdf_sha256']:raise RuntimeError('Runtime model mismatch')
 req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.WORLD_OBJECT_NAMES|PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS|PlanningSceneComponents.OCTOMAP
 sc=call(GetPlanningScene,'/get_planning_scene',req).scene
 report['scene']={'world_object_ids':[o.id for o in sc.world.collision_objects],'attached_object_ids':[o.object.id for o in sc.robot_state.attached_collision_objects],'octomap_bytes':len(sc.world.octomap.octomap.data)}
 for label,start,goal,opening in [('observe_to_manual_measured_opening',observe,manual,.0368),('observe_to_manual_original_full_opening',observe,manual,.100),('manual_to_observe_measured_opening',manual,observe,.0368)]:
  row={'label':label,'opening_m':opening,'start_validity':valid(start,opening),'goal_validity':valid(goal,opening)}
  req=GetMotionPlan.Request();m=req.motion_plan_request;m.group_name='arm';m.pipeline_id=cfg['real_pose_planning_pipeline'];m.planner_id=cfg['real_pose_planner_id'];m.start_state=state(start,opening);m.num_planning_attempts=1;m.allowed_planning_time=3.;m.max_velocity_scaling_factor=.01;m.max_acceleration_scaling_factor=.01
  c=Constraints()
  for n,q in zip(names,goal):c.joint_constraints.append(JointConstraint(joint_name=n,position=float(q),tolerance_above=.0001,tolerance_below=.0001,weight=1.))
  m.goal_constraints=[c];response=call(GetMotionPlan,'/plan_kinematic_path',req).motion_plan_response;trajectory=response.trajectory.joint_trajectory
  row.update(error_code=response.error_code.val,point_count=len(trajectory.points),joint_names=list(trajectory.joint_names),planning_time_s=response.planning_time)
  points=[];within=True
  for pt in trajectory.points:
   qm=dict(zip(trajectory.joint_names,pt.positions));q=[qm[n] for n in names]
   within=within and all(lo-1e-9<=v<=hi+1e-9 for v,lo,hi in zip(q,cfg['real_trajectory_joint_min'],cfg['real_trajectory_joint_max']))
   points.append({'q_rad':q,'time_s':pt.time_from_start.sec+pt.time_from_start.nanosec/1e9})
  row['within_original_task_limits']=within if points else False
  row['endpoint_error_rad']=max(abs(v-g) for v,g in zip(points[-1]['q_rad'],goal)) if points else None
  row['complete_to_measured_goal']=response.error_code.val==1 and bool(points) and row['within_original_task_limits'] and row['endpoint_error_rad']<=.0001
  row['planning_duration_s']=points[-1]['time_s'] if points else None
  # No publisher, execution client, adapter service or control process exists.
  report['queries'].append(row)
 print(json.dumps(report,indent=2),flush=True)
finally:
 node.destroy_node();rclpy.shutdown()
