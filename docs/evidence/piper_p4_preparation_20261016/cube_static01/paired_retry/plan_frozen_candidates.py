"""Isolated original-model/shared-C++ planning ONLY; no execution client."""
import copy,json,os,subprocess,sys
from pathlib import Path
import numpy as np,yaml,rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.msg import RobotState
from moveit_msgs.srv import GetCartesianPath,GetPositionFK,GetStateValidity
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
assert os.environ.get('ROS_DOMAIN_ID')=='78'
P=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
ob=json.loads((ROOT/'target_observation.json').read_text());plane=json.loads((ROOT/'fixed_board_plane_review.json').read_text())
rows=[json.loads(l) for l in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
sdk=json.loads((ROOT/'feedback.json').read_text())['actual_last_sample']
surfaces=[('detector_surface_as_published',np.median([w['point_base_m'] for w in ob['world_points']],axis=0).tolist()),
 ('board_29mm_top_centroid_ray_HYPOTHESIS',np.median([r['nominal_height_ray_intersections'][2]['base_m'] for r in plane['frames']],axis=0).tolist())]
rclpy.init();node=rclpy.create_node('frozen_cube_candidates_NO_EXECUTION')
clients={name:node.create_client(kind,name) for name,kind in [('/compute_fk',GetPositionFK),('/compute_cartesian_path',GetCartesianPath),('/check_state_validity',GetStateValidity)]}
def call(name,request):
    if not clients[name].wait_for_service(timeout_sec=15):raise RuntimeError(name+' unavailable')
    future=clients[name].call_async(request);rclpy.spin_until_future_complete(node,future,timeout_sec=20)
    if not future.done() or future.result() is None:raise RuntimeError(name+' timeout')
    return future.result()
state=RobotState();state.joint_state.name=[f'joint{i}' for i in range(1,9)]
opening=min(.1,sdk['gripper_mm']*.001)
state.joint_state.position=rows[0]['q_rad']+[opening/2,-opening/2]
report={'isolated_domain':78,'hardware_executed':False,'no_CAN_or_command_publisher':True,
 'scene':'Original physical model/self collision; isolated world is not physical table/clearance proof.',
 'start_q_actual_snapshot':rows[0]['q_rad'],'opening_m':opening,'candidates':[],'exception':None}
def plan(start,poses):
    req=GetCartesianPath.Request();req.header.frame_id='base_link';req.group_name='arm';req.link_name=P['end_effector_link']
    req.start_state=start;req.max_step=.005;req.jump_threshold=0.;req.avoid_collisions=True
    for v in poses:
        p=Pose();p.position.x,p.position.y,p.position.z=v['origin']
        p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w=v['orientation'];req.waypoints.append(p)
    a=call('/compute_cartesian_path',req);trajectory=a.solution.joint_trajectory
    q=list(start.joint_state.position);points=[]
    for pt in trajectory.points:
        values=dict(zip(trajectory.joint_names,pt.positions))
        ordered=[values[name] for name in state.joint_state.name[:6]];points.append(ordered)
    endpoint=copy.deepcopy(start)
    if points:endpoint.joint_state.position=points[-1]+q[6:]
    return {'fraction':a.fraction,'error_code':a.error_code.val,'waypoint_count':len(poses),
        'trajectory_points':len(points),'q_path':points,
        'all_original_joint_bounds':all(lo<=x<=hi for row in points for lo,x,hi in zip(P['real_trajectory_joint_min'],row,P['real_trajectory_joint_max']))},endpoint
try:
    req=GetPositionFK.Request();req.header.frame_id='base_link';req.fk_link_names=[P['end_effector_link']];req.robot_state=state
    fk=call('/compute_fk',req)
    if fk.error_code.val!=1:raise RuntimeError('Actual snapshot FK failed')
    p=fk.pose_stamped[0].pose
    report['start_link6_pose']={'xyz':[p.position.x,p.position.y,p.position.z],
        'quat':[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]}
    req=GetStateValidity.Request();req.group_name='arm';req.robot_state=state
    checked=call('/check_state_validity',req);report['start_valid']=checked.valid
    report['start_contacts']=[[c.contact_body_1,c.contact_body_2] for c in checked.contacts]
    for label,surface in surfaces:
        insertion=min(.029*P['surface_insertion_fraction'],P['surface_insertion_max_m'])
        values=[p.position.x,p.position.y,p.position.z,p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w,
            *surface,P['gripper_tip_offset_m'],P['top_down_pregrasp_clearance_m']+P['grasp_height_offset_m'],
            insertion-P['grasp_height_offset_m'],.005,P['target_directed_downward_fraction'],1]
        geometry=json.loads(subprocess.check_output([str(ROOT/'shared_geometry'),*map(str,values)],text=True,timeout=3))
        pre,end=plan(state,geometry['pregrasp']);row={'label':label,'surface_base_m':surface,
            'insertion_m':insertion,'pregrasp':pre,'last_descent_pose':geometry['descent'][-1],
            'nominal_TCP_only_not_physical_grasp_validation':True}
        if pre['fraction']>=.995:row['descent'],_=plan(end,geometry['descent'])
        report['candidates'].append(row)
except BaseException as exc:report['exception']=repr(exc)
finally:
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'isolated_planning.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'exception':report['exception'],'start_valid':report.get('start_valid'),
    'candidates':[{k:v for k,v in c.items() if k not in ['pregrasp','descent','last_descent_pose']}|
        {'pregrasp_fraction':c['pregrasp']['fraction'],'descent_fraction':c.get('descent',{}).get('fraction')} for c in report['candidates']]},indent=2))
raise SystemExit(0 if report['exception'] is None else 2)
