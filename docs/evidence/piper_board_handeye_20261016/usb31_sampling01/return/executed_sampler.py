"""Return after capture stop to original session start, original helpers only.

No camera, SEARCH, gripper or SDK control. Not a repeat of J4 validation.
"""
import ast,collections,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
import numpy as np,yaml,rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
from std_srvs.srv import Trigger
from piper_msgs.srv import Enable
from rcl_interfaces.srv import GetParameters
from moveit_msgs.srv import GetMotionPlan,GetStateValidity
from moveit_msgs.msg import RobotState,Constraints,JointConstraint
from rosidl_runtime_py.convert import message_to_ordereddict
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
TOOLS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TOOLS))
from collect_static_rgbd import joint_positions,stamp_ns,settled_feedback
from collect_calibration_p0 import read_can,healthy_window
from review_calibration_sampling import checked_trajectory
OLD=REPO/'docs/evidence/piper_board_handeye_20261016/attempt01/run03/executed_sampler.py'
names={'save','launch','wait','call','trigger','feedback','state','valid','plan','execute'}
defs=[n for n in ast.parse(OLD.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(defs)==len(names)
exec(compile(ast.fix_missing_locations(ast.Module(body=defs,type_ignores=[])),'<unchanged original helpers>','exec'),globals())
cfg=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
NAMES=[f'joint{i}' for i in range(1,7)]
frozen=json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_static01/production_SHA_after.json').read_text())
prior=json.loads(Path('/home/johnwick/brain_robot_logs/board_usb31_original_20261016.G2lzeV/execution.json').read_text())
goal=np.asarray(prior['actual_start']['q'])
report={'scope':'Already-approved return to original session actual start after capture stop','events':[],'paths':[],
 'error':None,'gripper_commands':0,'hardware_disable_or_reset':False,'camera_started':False,'arrivals':[]}
jobs=[];latest=None;history=collections.deque(maxlen=4000);camera_started=None;flow_error=None;armed=False
started=time.monotonic();rclpy.init();node=rclpy.create_node('original_board_return_after_capture_stop')
node.create_subscription(JointState,'/joint_states_feedback',feedback,qos_profile_sensor_data)
trajectory=node.create_publisher(JointTrajectory,'/brain_robot_grasp/arm_trajectory',10)
try:
    before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in frozen};assert before==frozen
    save('production_SHA_before.json',before)
    a=read_can();time.sleep(.2);b=read_can();assert healthy_window(a,b)
    save('can_before.json',{'before':a,'after':b})
    launch('driver',['/usr/bin/python3','-c',"import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()",'--ros-args','--log-level','WARN','-p','can_port:=can0','-p','auto_enable:=false','-p','gripper_exist:=true','-r','joint_states_single:=/joint_states','-r','joint_ctrl_single:=/joint_commands'])
    launch('original_nodes',['/usr/bin/python3',str(ROOT/'original_sampling.launch.py')])
    launch('bag',['ros2','bag','record','-o',str(ROOT/'motion_bag'),'/joint_states_feedback','/joint_commands','/brain_robot_grasp/arm_trajectory','/brain_robot_grasp/gripper_command','/brain_robot_control/adapter_armed'])
    wait(lambda:latest is not None and time.time()-latest['epoch']<.5 and latest['gap_m'] is not None,20,'fresh driver feedback')
    wait(lambda:settled_feedback(history,latest['q'],latest['stamp_ns'],3.),10,'original q static condition')
    center=np.asarray(latest['q']);opening=latest['gap_m'];report['actual_start']=latest.copy()
    response=call(GetParameters,'/move_group/get_parameters',GetParameters.Request(names=['allow_trajectory_execution','robot_description']))
    assert not response.values[0].bool_value
    report['model_SHA256']=hashlib.sha256(response.values[1].string_value.encode()).hexdigest()
    assert report['model_SHA256']==prior['model_SHA256']
    assert valid(center)['valid'] and valid(goal)['valid']
    path=plan(center,goal,'return_original_session_start')
    report['checklist']={'last_fresh_SDK':json.loads((ROOT/'preflight.json').read_text())['last_fresh_SDK'],
       'current_start_rad':center.tolist(),'goal_rad':goal.tolist(),'min_rad':cfg['real_trajectory_joint_min'],
       'max_rad':cfg['real_trajectory_joint_max'],'scaling':[.02,.02],'adapter_max_velocity_rad_s':.189,
       'stop':'Original stale-feedback suppression / adapter watchdog and duration+25; software disarm only',
       'return':'This original session actual start; no further automatic motion in this invocation'}
    save('planning_before_motion.json',report);print('RETURN_CHECKLIST',json.dumps(report['checklist']),flush=True)
    result=call(Enable,'/enable_srv',Enable.Request(enable_request=True));assert result.enable_response
    trigger('/piper_jog_adapter/enable_motion');trigger('/piper_jog_adapter/arm');armed=True
    execute(path,goal,'return_original_session_start')
    wait(lambda:settled_feedback(history,latest['q'],latest['stamp_ns'],3.),12,'returned q settled')
    report['arrivals'].append({'actual_feedback':latest.copy(),'goal_rad':goal.tolist()});report['return_completed']=True
except BaseException as e:report['error']=repr(e)
finally:
    if armed:
        try:trigger('/piper_jog_adapter/disarm');armed=False
        except BaseException as e:report['events'].append({'disarm_error':repr(e)})
    for n,p,f in reversed(jobs):
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
        f.close();report['events'].append({'source':n,'rc':p.returncode})
    report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['final_received_feedback']=latest;report['elapsed_s']=time.monotonic()-started
    save('can_after.json',read_can());save('production_SHA_after.json',{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in frozen})
    save('execution.json',report);node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
print(json.dumps({'return_completed':report.get('return_completed',False),'error':report['error']}),flush=True)
raise SystemExit(0 if report.get('return_completed') and report['error'] is None else 2)
