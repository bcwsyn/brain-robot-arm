"""Authorized board sampling: original MoveIt plans -> original adapter only.

No SDK motion methods, gripper commands, Reset, disable or TF/config edits.
Bounded current-session raw RGB/feedback/IDs, no implicit board-origin reset.
"""
import collections,hashlib,json,math,os,signal,subprocess,sys,time
from pathlib import Path
import cv2,numpy as np,yaml
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState,Image
from trajectory_msgs.msg import JointTrajectory
from std_srvs.srv import Trigger
from piper_msgs.srv import Enable
from rcl_interfaces.srv import GetParameters
from moveit_msgs.srv import GetMotionPlan,GetStateValidity,GetPlanningScene
from moveit_msgs.msg import RobotState,Constraints,JointConstraint,PlanningSceneComponents
from rosidl_runtime_py.convert import message_to_ordereddict
from cv_bridge import CvBridge

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/home/johnwick/brain_robot_logs/board_handeye_20261016.N2eAKe')
REPO=Path('/mnt/hgfs/ub');TOOLS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
EVIDENCE=REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'
sys.path[:0]=[str(TOOLS),str(EVIDENCE)]
from collect_calibration_p0 import read_can,healthy_window
from collect_static_rgbd import settled_feedback,stamp_ns,joint_positions
from review_calibration_sampling import checked_trajectory
from partial_board_tracking_check import propagate
from board_pose_offline import grid,poses
TASK=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
cfg=yaml.safe_load(TASK.read_text())['grasp_lift_executor']['ros__parameters']
NAMES=[f'joint{i}' for i in range(1,7)]
FROZEN=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/usb31_static01/production_SHA_after.json')
PREVIEW=Path('/home/johnwick/brain_robot_logs/usb31_static_20261016.1oGFil/metadata_followup')
report={'operator_quote':'好，你自行完成，等真的需要我实机操作的时候再叫我','baseline_commit':'8744c14','approved_proposal_commit':'121d1ef','route':'board9fit1heldout',
    'gripper_commands':0,'reset_or_hardware_disable':False,'search_or_grasp':False,'production_changed':False,
    'events':[],'paths':[],'samples':[],'error':None,'all_owned_sources_exited':False}
jobs=[];latest=None;history=collections.deque(maxlen=4000);armed=False
started=time.monotonic();camera_started=None;last_rgb_receipt=None;flow_error=None
previous_gray=None;previous_stamp=None;fixed_points=None;fixed_ids=None;object_points=None
frames=0;image_bytes=0;latest_frame=None;active_label=None;sample_rows=[];last_sample_ns=0
bridge=CvBridge();stream=None;records=None;seed_written=False
ROOT.joinpath('continuous_rgb').mkdir(exist_ok=False)

def save(name,obj):
    with (ROOT/name).open('x') as f:json.dump(obj,f,indent=2,allow_nan=False)
def launch(name,argv):
    f=(ROOT/(name+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((name,p,f));report['events'].append({'launch':name,'pid':p.pid,'argv':argv,'epoch':time.time()});return p
def wait(predicate,seconds,label):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        rclpy.spin_once(node,timeout_sec=.02)
        if camera_started is not None:
            if flow_error:raise RuntimeError('Board identity/capture: '+flow_error)
            if time.monotonic()-camera_started>600:raise RuntimeError('600s bounded camera session complete')
            if last_rgb_receipt is not None and time.monotonic()-last_rgb_receipt>2:raise RuntimeError('RGB stopped; no automatic restart')
        if predicate():return
    raise TimeoutError(label)
def call(kind,name,request):
    c=node.create_client(kind,name)
    try:
        wait(c.service_is_ready,20,name+' discovery');future=c.call_async(request)
        wait(future.done,12,name+' response; not retried')
        result=future.result();report['events'].append({'service':name,'epoch':time.time()})
        return result
    finally:node.destroy_client(c)
def trigger(name):
    a=call(Trigger,name,Trigger.Request())
    if not a.success:raise RuntimeError(name+': '+a.message)
def feedback(msg):
    global latest
    try:q=joint_positions(msg);stamp=stamp_ns(msg)
    except (ValueError,KeyError):return
    values=dict(zip(msg.name,msg.position));latest={'epoch':time.time(),'stamp_ns':stamp,'q':q,'gap_m':values.get('gripper')}
    history.append((stamp,q))
def state(q):
    s=RobotState();s.joint_state.name=NAMES+['joint7','joint8']
    s.joint_state.position=list(map(float,q))+[opening/2,-opening/2];s.is_diff=False;return s
def valid(q):
    a=call(GetStateValidity,'/check_state_validity',GetStateValidity.Request(robot_state=state(q),group_name='arm'))
    return {'valid':a.valid,'contacts':[{'body1':c.contact_body_1,'body2':c.contact_body_2} for c in a.contacts]}
def plan(start,goal,label):
    request=GetMotionPlan.Request();m=request.motion_plan_request
    m.group_name='arm';m.pipeline_id=cfg['real_pose_planning_pipeline'];m.planner_id=cfg['real_pose_planner_id']
    m.start_state=state(start);m.num_planning_attempts=1;m.allowed_planning_time=3.
    m.max_velocity_scaling_factor=.02;m.max_acceleration_scaling_factor=.02
    c=Constraints()
    for n,q in zip(NAMES,goal):c.joint_constraints.append(JointConstraint(joint_name=n,position=float(q),tolerance_above=1e-5,tolerance_below=1e-5,weight=1.))
    m.goal_constraints=[c]
    a=call(GetMotionPlan,'/plan_kinematic_path',request).motion_plan_response
    row={'label':label,'response':message_to_ordereddict(a)};report['paths'].append(row)
    if a.error_code.val!=1:raise RuntimeError(label+' plan failed '+str(a.error_code.val))
    t=a.trajectory.joint_trajectory
    row['validation']=checked_trajectory(list(t.joint_names),[list(p.positions) for p in t.points],start,goal,cfg)
    return t
def picture(msg):
    global previous_gray,previous_stamp,fixed_points,fixed_ids,object_points,frames,image_bytes,latest_frame,last_rgb_receipt,flow_error,seed_written,last_sample_ns
    last_rgb_receipt=time.monotonic()
    if flow_error:return
    try:
        now=node.get_clock().now().nanoseconds;stamp=stamp_ns(msg)
        if now<stamp or now-stamp>500_000_000:raise ValueError('RGB source stale/future')
        rgb=bridge.imgmsg_to_cv2(msg,'bgr8');gray=cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY)
        if gray.shape!=(240,320):raise ValueError('Unexpected actual RGB size')
        if previous_gray is None:
            found,corners,meta=cv2.findChessboardCornersSBWithMeta(gray,(3,3),flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_LARGER)
            if not found:raise ValueError('No actual visible grid seed')
            c,r=meta.shape[1],meta.shape[0]
            if not ((c<=11 and r<=7) or (c<=7 and r<=11)):raise ValueError('Visible grid inconsistent with known board')
            ids=[y*c+x for y in range(1,r-1) for x in range(1,c-1)]
            if len(ids)<9:raise ValueError('Insufficient interior seed points')
            fixed_ids=ids;fixed_points=corners.reshape(-1,2)[ids].astype(np.float32);object_points=grid((c,r))[ids]
            save('session_seed.json',{'visible_grid':[c,r],'visible_corners':corners.reshape(-1,2).tolist(),'fixed_interior_IDs':ids,'object_points_m':object_points.tolist(),'source_stamp_ns':str(stamp),
                'frame':msg.header.frame_id,'single_session_reference_not_old_global_origin':True,'square_mm_user_reported':32})
            seed_written=True
        else:
            if stamp-previous_stamp>800_000_000:raise ValueError('Image gap prevents verified continuous ID propagation')
            tracks=propagate(previous_gray,gray,fixed_points)
            if not all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks):raise ValueError('Tracked interior point lost; origin not reset')
            if max(t['forward_backward_error_px'] for t in tracks)>.5:raise ValueError('Interior optical-flow inconsistency')
            nxt=np.asarray([t['position_px'] for t in tracks],dtype=np.float32)
            if np.linalg.norm(nxt-fixed_points,axis=1).max()>6:raise ValueError('Potential repeated-grid ID slip; no reseed')
            fixed_points=nxt
        previous_gray=gray;previous_stamp=stamp;frames+=1
        ok,encoded=cv2.imencode('.png',rgb)
        if not ok:raise ValueError('Cannot preserve original RGB')
        if frames>1200 or image_bytes+encoded.nbytes>160<<20:raise ValueError('Bounded raw image budget reached')
        p=ROOT/'continuous_rgb'/f'{frames:05d}.png'
        with p.open('xb') as f:f.write(encoded.tobytes())
        image_bytes+=encoded.nbytes
        current=latest.copy() if latest is not None else None
        row={'index':frames,'rgb_source_stamp_ns':str(stamp),'frame':msg.header.frame_id,'image_path':str(p.relative_to(ROOT)),
            'image_SHA256':hashlib.sha256(encoded.tobytes()).hexdigest(),'fixed_IDs':fixed_ids,'corners_px':fixed_points.tolist(),'actual_feedback':current,'label':active_label}
        records.write(json.dumps(row,allow_nan=False)+'\n');records.flush();latest_frame=row
        if active_label is not None and current is not None and abs(stamp-current['stamp_ns'])<=120_000_000 and now-current['stamp_ns']<=500_000_000:
            static=settled_feedback(history,current['q'],current['stamp_ns'],3.)
            count=sum(current['stamp_ns']-3_000_000_000<=t<=current['stamp_ns'] for t,_ in history)
            if static and count>=30 and stamp-last_sample_ns>=500_000_000:
                copied=dict(row);copied['pose_candidates']=poses(object_points,fixed_points,K,D);sample_rows.append(copied);last_sample_ns=stamp
    except BaseException as e:
        flow_error=repr(e)
        if 'rgb' in locals():
            ok,encoded=cv2.imencode('.png',rgb)
            if ok:
                with (ROOT/'failed_rgb.png').open('xb') as failed:failed.write(encoded.tobytes())
        save('failed_frame.json',{'error':flow_error,'source_stamp_ns':str(stamp) if 'stamp' in locals() else None,'latest_actual_feedback':latest})
def sample(label):
    global active_label,sample_rows,last_sample_ns
    active_label=label;sample_rows=[];last_sample_ns=0
    wait(lambda:len(sample_rows)>=5,18,'five settled fixed-ID RGB samples '+label)
    active_label=None;entry={'label':label,'role':'heldout' if label=='combined_holdout' else 'fit','frames':sample_rows[:5]}
    report['samples'].append(entry);save('sample_'+label+'.json',entry);print('SAMPLED',label,flush=True)
def execute(t,goal,label):
    if latest is None or time.time()-latest['epoch']>.5:raise RuntimeError('No fresh actual start '+label)
    actual=np.asarray(latest['q']);planned={n:q for n,q in zip(t.joint_names,t.points[0].positions)}
    if max(abs(actual[i]-planned[n]) for i,n in enumerate(NAMES))>.04:
        t=plan(actual,goal,label+'_fresh_start_replan')
    # Recording tools are subscribers too; readiness is not exclusive ownership.
    wait(lambda:trajectory.get_subscription_count()>=1,5,'original adapter trajectory subscriber ready')
    trajectory.publish(t);report['events'].append({'trajectory_published':label,'epoch':time.time()})
    duration=t.points[-1].time_from_start.sec+t.points[-1].time_from_start.nanosec/1e9
    began=time.monotonic()
    wait(lambda:time.monotonic()-began>=duration and latest is not None and time.time()-latest['epoch']<.5 and max(abs(a-b) for a,b in zip(latest['q'],goal))<=cfg['trajectory_feedback_tolerance_rad'],duration+25,'actual goal '+label)

print(ROOT,flush=True);rclpy.init();node=rclpy.create_node('authorized_board_handeye_sampling')
node.create_subscription(JointState,'/joint_states_feedback',feedback,qos_profile_sensor_data)
node.create_subscription(Image,'/camera/color/image_raw',picture,qos_profile_sensor_data)
trajectory=node.create_publisher(JointTrajectory,'/brain_robot_grasp/arm_trajectory',10)
records=(ROOT/'continuous_tracking.jsonl').open('x')
try:
    frozen=json.loads(FROZEN.read_text());before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in frozen}
    assert before==frozen;save('production_SHA_before.json',before)
    a=read_can();time.sleep(.2);b=read_can();save('can_before.json',{'before':a,'after':b,'healthy':healthy_window(a,b)})
    assert healthy_window(a,b)
    factory=json.loads((PREVIEW/'factory.json').read_text());assert factory['get_device_info']['info']['serial_number']=='CC1365304DG'
    old=json.loads((REPO/'docs/evidence/piper_calibration_p1_20261015/board_observe/portable/calibration.json').read_text())
    K=np.diag([*old['color_capture']['existing_detector_resize_factors'],1.])@np.asarray(old['color_factory']['K']).reshape(3,3)
    D=np.asarray(old['color_factory']['CameraInfo_D'])
    save('camera_metadata.json',{'recent_same_device_factory_snapshot':factory,'pose_K':K.tolist(),'pose_D':D.tolist(),'K_D_interpretation':'unchanged endpoint/zero-D baseline, not newly calibrated','source_calibration':old})
    launch('driver',['/usr/bin/python3','-c',"import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()",'--ros-args','--log-level','WARN','-p','can_port:=can0','-p','auto_enable:=false','-p','gripper_exist:=true','-r','joint_states_single:=/joint_states','-r','joint_ctrl_single:=/joint_commands'])
    launch('original_nodes',['/usr/bin/python3','/home/johnwick/brain_robot_logs/board_usb31_original_20261016.G2lzeV/original_sampling.launch.py'])
    launch('bag',['ros2','bag','record','-o',str(ROOT/'motion_bag'),'/joint_states_feedback','/joint_commands','/brain_robot_grasp/arm_trajectory','/brain_robot_grasp/gripper_command','/brain_robot_control/adapter_armed'])
    wait(lambda:latest is not None and time.time()-latest['epoch']<.5 and latest['gap_m'] is not None,20,'fresh actual driver feedback')
    center=np.asarray(latest['q']);opening=latest['gap_m'];report['actual_start']=dict(latest)
    response=call(GetParameters,'/move_group/get_parameters',GetParameters.Request(names=['allow_trajectory_execution','robot_description']))
    assert response.values[0].type==1 and not response.values[0].bool_value
    model_sha=hashlib.sha256(response.values[1].string_value.encode()).hexdigest();report['model_SHA256']=model_sha
    assert model_sha=='0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82'
    req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.WORLD_OBJECT_NAMES|PlanningSceneComponents.OCTOMAP
    scene=call(GetPlanningScene,'/get_planning_scene',req).scene
    report['scene']={'world_ids':[o.id for o in scene.world.collision_objects],'octomap_bytes':len(scene.world.octomap.octomap.data),'physical_clearance_NOT_proven_by_empty_world':True}
    report['start_validity']=valid(center);assert report['start_validity']['valid']
    offsets=json.loads((EVIDENCE/'nominal_sampling_candidates.json').read_text())['non_start_pose_limit_and_FK_candidates']
    candidates=[]
    for row in offsets[1:]:
        goal=center+np.deg2rad([0,0,0,*row['offset_J4_J5_J6_deg']]);check=valid(goal)
        report['events'].append({'candidate':row['id'],'validity':check});assert check['valid']
        out=plan(center,goal,row['id']+'_out');back=plan(goal,center,row['id']+'_back')
        candidates.append((row['id'],goal,out,back))
    save('planning_before_motion.json',report);print('ALL_18_ORIGINAL_MOVEIT_PATHS_CHECKED',report['scene'],flush=True)
    camera_started=time.monotonic()
    # Reuse today's proven original Astra->RGB startup profile. Depth is not
    # used for board pose and the unchanged wrist-cloud Octomap input is off.
    report['camera_startup_profile']='original astra depth first, then same cam2image; board uses RGB only'
    launch('depth',['ros2','launch','astra_camera','astra.launch.py'])
    until=time.monotonic()+4
    while time.monotonic()<until:
        rclpy.spin_once(node,timeout_sec=.03)
        if 'SENSOR_DEPTH is started' in (ROOT/'depth.log').read_text(errors='replace'):break
    launch('color',['/opt/ros/humble/lib/image_tools/cam2image','--ros-args','-p','burger_mode:=false','-p','device_id:=0','-p','frequency:=5.0','-p','width:=320','-p','height:=240','-p','frame_id:=camera_color_optical_frame','-r','image:=/camera/color/image_raw'])
    wait(lambda:seed_written and frames>=5,18,'live board seed and consecutive original RGB')
    factory_process=launch('factory_readonly',['/usr/bin/python3','/home/johnwick/brain_robot_logs/board_usb31_original_20261016.G2lzeV/capture_factory_metadata.py',str(ROOT/'current_factory.json')])
    wait(lambda:factory_process.poll() is not None,24,'bounded current factory getter')
    assert factory_process.returncode==0
    current_factory=json.loads((ROOT/'current_factory.json').read_text())
    assert current_factory['get_device_info']['info']['serial_number']=='CC1365304DG'
    assert current_factory['get_camera_info']['info']['k']==old['color_factory']['K']
    assert current_factory['get_camera_info']['info']['d']==old['color_factory']['CameraInfo_D']
    sdk_before=json.loads((ROOT/'sdk_before.json').read_text())
    save('sampling_checklist.json',{'approved_proposal_commit':'121d1ef','current_start_rad':center.tolist(),'SDK_original_static_slice':json.loads((ROOT/'preflight.json').read_text())['original_static_slice'],'last_fresh_SDK':[s for s in sdk_before['samples'] if s['fresh_after_passive_connection']][-1],'joint_min_rad':cfg['real_trajectory_joint_min'],'joint_max_rad':cfg['real_trajectory_joint_max'],'candidate_goals_rad':{label:goal.tolist() for label,goal,_,_ in candidates},'MoveIt_scaling':[.02,.02],'adapter_max_velocity_rad_s':.189,'original_goal_tolerance_rad':cfg['trajectory_feedback_tolerance_rad'],'trajectory_durations_s':[t.points[-1].time_from_start.sec+t.points[-1].time_from_start.nanosec/1e9 for _,_,t,_ in candidates],'scene':report['scene'],'return':'Each original candidate returns to this fresh center; no gripper/SEARCH/grasp.','stop':'Original feedback/limits/collision + continuous fixed board IDs + original duration+25 timeout; software disarm, never hardware Disable.'})
    print('BOARD_SAMPLING_CHECKLIST_READY',flush=True)
    sample('start')
    result=call(Enable,'/enable_srv',Enable.Request(enable_request=True));assert result.enable_response
    trigger('/piper_jog_adapter/enable_motion');trigger('/piper_jog_adapter/arm');armed=True
    for label,goal,out,back in candidates:
        print('EXECUTE',label,flush=True);execute(out,goal,label+'_out');sample(label)
        execute(back,center,label+'_back')
        wait(lambda:latest is not None and settled_feedback(history,latest['q'],latest['stamp_ns'],3.),12,'returned and settled start')
    trigger('/piper_jog_adapter/disarm');armed=False;report['completed_9fit_1heldout']=len(report['samples'])==10
except BaseException as e:
    report['error']=repr(e);print('SAMPLING STOP:',repr(e),flush=True)
finally:
    report['flow_error_at_stop']=flow_error
    if armed:
        # Do not let an image-quality exception prevent software disarm.
        camera_started=None;flow_error=None
        try:trigger('/piper_jog_adapter/disarm');armed=False
        except BaseException as e:report['events'].append({'disarm_error':repr(e)})
    for name,p,f in reversed(jobs):
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
        f.close();report['events'].append({'source':name,'exit_code':p.returncode})
    records.close();report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['final_received_feedback']=latest;report['raw_RGB_frames']=frames;report['raw_RGB_bytes']=image_bytes
    report['elapsed_s']=time.monotonic()-started;report['last_RGB_flow_error']=flow_error
    save('can_after.json',read_can())
    save('production_SHA_after.json',{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in json.loads(FROZEN.read_text())})
    save('execution.json',report);node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
print(json.dumps({'samples':len(report['samples']),'error':report['error'],'all_exited':report['all_owned_sources_exited']}),flush=True)
raise SystemExit(0 if report.get('completed_9fit_1heldout') and report['error'] is None else 2)
