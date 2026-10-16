"""No hardware: actual executor exercised with explicit synthetic endpoint input.

This is NOT a physics/accuracy/grasp-success demonstration. No PiPER driver,
adapter, camera or CAN API exists in this test. All ROS traffic is domain 78.
"""
import argparse,json,os,time
from pathlib import Path
assert os.environ.get('ROS_DOMAIN_ID')=='78'
import rclpy
from rclpy.qos import QoSProfile,DurabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String,UInt8
from std_srvs.srv import Trigger
from rcl_interfaces.srv import GetParameters
from trajectory_msgs.msg import JointTrajectory

parser=argparse.ArgumentParser()
parser.add_argument('--scenario',choices=['object','empty'],required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
rclpy.init();node=rclpy.create_node('SYNTHETIC_P4_loopback_fixture')
q=[-.143982776,.93491118,-1.259945232,-.071502956,1.212288224,.088824848]
opening=.1;reference=.1;states=[];diagnostics=[];commands=[];trajectories=[];arm_outputs=[]
pub=node.create_publisher(JointState,'/joint_states',10)
grip=node.create_publisher(JointState,'/piper/gripper_feedback',10)
status=node.create_publisher(UInt8,'/piper/gripper_status',10)
def accept_arm(m):
    global q
    # Exact endpoint injection, NOT physically simulated or actual feedback.
    q=[m.points[-1].positions[m.joint_names.index(f'joint{i}')] for i in range(1,7)]
    trajectories.append({'epoch':time.time(),'points':len(m.points),'endpoint':q})
def accept_grip(m):
    global reference
    reference=float(m.position[0]);commands.append({'epoch':time.time(),'opening_reference_m':reference})
subs=[node.create_subscription(String,'/brain_robot_grasp/state',lambda m:states.append(m.data),
    QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)),
    node.create_subscription(String,'/brain_robot_grasp/diagnostic',lambda m:diagnostics.append(m.data),
    QoSProfile(depth=30,durability=DurabilityPolicy.TRANSIENT_LOCAL)),
    node.create_subscription(JointTrajectory,'/brain_robot_grasp/arm_trajectory',accept_arm,10),
    node.create_subscription(JointState,'/brain_robot_grasp/gripper_command',accept_grip,10),
    node.create_subscription(JointState,'/joint_commands',lambda m:arm_outputs.append(1),10)]
def tick():
    global opening
    opening+=max(-.0002,min(.0002,reference-opening))
    if args.scenario=='object':opening=max(.037,opening)
    m=JointState();m.header.stamp=node.get_clock().now().to_msg()
    m.name=[f'joint{i}' for i in range(1,9)];m.position=q+[opening/2,-opening/2]
    m.velocity=[0.]*8;pub.publish(m)
    g=JointState();g.header.stamp=m.header.stamp;g.name=['gripper'];g.position=[opening]
    loaded=args.scenario=='object' and opening<=.037001 and reference<opening-.00025
    g.effort=[-.3 if loaded else -.02];grip.publish(g);status.publish(UInt8(data=0x40))
timer=node.create_timer(.02,tick)
def stop_servo(_request,response):response.success=True;response.message='synthetic no Servo';return response
service=node.create_service(Trigger,'/servo_node/stop_servo',stop_servo)
client=node.create_client(Trigger,'/grasp_lift_executor/execute')
result={'scenario':args.scenario,'domain':78,'synthetic_feedback_only':True,
    'arm_endpoints_injected_NOT_physics_or_actual_feedback':True,
    'hardware_nodes_or_CAN':False,'physical_grasp_succeeded':False}
started=time.monotonic()
try:
    deadline=started+30
    while 'P4_READY_FOR_EXPLICIT_EXECUTE' not in states and time.monotonic()<deadline:
        rclpy.spin_once(node,timeout_sec=.02)
    if 'P4_READY_FOR_EXPLICIT_EXECUTE' not in states:raise RuntimeError('executor not ready')
    if not client.wait_for_service(timeout_sec=2):raise RuntimeError('execute absent')
    pc=node.create_client(GetParameters,'/grasp_lift_executor/get_parameters')
    assert pc.wait_for_service(timeout_sec=2)
    pr=GetParameters.Request();pr.names=['gripper_feedback_topic','auto_release_after_lift']
    pf=pc.call_async(pr)
    deadline=time.monotonic()+3
    while not pf.done() and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.02)
    assert pf.done()
    result['actual_parameters']=[{'string':v.string_value,'bool':v.bool_value} for v in pf.result().values]
    result['executor_subscriptions']=node.get_subscriber_names_and_types_by_node('grasp_lift_executor','/')
    result['executor_processes']=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:argv=p.joinpath('cmdline').read_bytes().decode().split('\0')
        except (OSError,UnicodeError):continue
        if argv and argv[0].endswith('/grasp_lift_executor'):
            result['executor_processes'].append(argv)
    assert result['actual_parameters'][0]['string']=='/piper/gripper_feedback','Wrong P4 feedback topic'
    deadline=time.monotonic()+1
    while time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.02)
    future=client.call_async(Trigger.Request())
    deadline=time.monotonic()+65
    while time.monotonic()<deadline:
        rclpy.spin_once(node,timeout_sec=.02)
        if states and (states[-1]=='HOLDING' or states[-1].startswith('FAULT_')):break
    result.update(states=states,diagnostics=diagnostics,gripper_commands=commands,
        arm_trajectories=trajectories,joint_commands=len(arm_outputs),last_opening_m=opening)
    assert future.done() and future.result().success
    assert commands and min(c['opening_reference_m'] for c in commands)>=.025-1e-8
    assert len(arm_outputs)==0,'No adapter or driver may be present'
    if args.scenario=='object':
        assert states[-1]=='HOLDING' and 'LIFTING' in states
        assert abs(opening-.037)<.001
    else:
        assert states[-1]=='FAULT_P4_GENTLE_CLOSE_NO_CONFIRMED_CONTACT'
        assert 'LIFTING' not in states and 'HOLDING' not in states
    result['passed']=True
except BaseException as exc:result.update(passed=False,error=repr(exc),states=states,diagnostics=diagnostics)
finally:
    result['elapsed_s']=time.monotonic()-started
    with args.output.open('x') as f:json.dump(result,f,indent=2)
    node.destroy_node();rclpy.shutdown()
print(json.dumps({k:v for k,v in result.items() if k not in ['diagnostics','gripper_commands','arm_trajectories']}))
raise SystemExit(0 if result['passed'] else 2)
