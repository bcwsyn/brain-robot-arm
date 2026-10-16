"""Authorized original observation return after cube removal; no gripper command."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
import rclpy,yaml
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from std_srvs.srv import Trigger
from piper_msgs.srv import Enable
from rcl_interfaces.srv import SetParameters,GetParameters
from rcl_interfaces.msg import Parameter,ParameterValue,ParameterType

ROOT=Path(__file__).resolve().parent
TESTS=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
FROZEN=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/usb2_hold_retry01/production_SHA_after.json')
TASK=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
LAUNCH=ROOT/'original_observe_launch.py'
ADAPTER=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
sys.path.insert(0,str(TESTS))
from collect_calibration_p0 import read_can,healthy_window
from collect_calibration_sdk import summarize
NAMES=[f'joint{i}' for i in range(1,7)]
report={'role':'board_full_observation_return','baseline_commit':'4e44326','cube_removed_historical_fact_not_new_confirmation':True,'operator_return_permission':True,
 'operator_quote':'好，你自行完成，等真的需要我实机操作的时候再叫我','approved_scope':'Original observation return stopped before SEARCH, then camera inspection; no gripper or production edits','gripper_command_published':False,'observe_reached':False,
 'reset_or_disable_requested':False,'production_modified':False,'candidate_deployed':True,
 'camera_during_motion':False,'events':[],'commands':[],'error':None}
jobs=[];latest=None;first=None;reason='';armed=False
def save(name,o):
 with (ROOT/name).open('x') as f:json.dump(o,f,indent=2,allow_nan=False)
def start(name,argv):
 f=(ROOT/(name+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 jobs.append((name,p,f));report['commands'].append({'name':name,'argv':argv,'pid':p.pid,'epoch':time.time()})
 return p
def wait(predicate,seconds,label):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  rclpy.spin_once(node,timeout_sec=.03)
  if predicate():return
 raise TimeoutError(label)
def call(path,kind,request):
 client=node.create_client(kind,path)
 try:
  wait(client.service_is_ready,18,path+' discovery')
  f=client.call_async(request);wait(f.done,18,path+' response; not retried')
  response=f.result();report['events'].append({'service':path,'response':str(response),'epoch':time.time()})
  return response
 finally:node.destroy_client(client)
def trigger(path):
 result=call(path,Trigger,Trigger.Request())
 if not result.success:raise RuntimeError(path+':'+result.message)
def sdk(name):
 duration='10' if name=='sdk_before' else '6'
 p=start(name,['/usr/bin/python3',str(TESTS/'collect_calibration_sdk.py'),'--output',str(ROOT/(name+'.json')),'--duration-s',duration])
 wait(lambda:p.poll() is not None,16,name)
 report['events'].append({'name':name,'exit_code':p.returncode,'epoch':time.time()})
 packet=json.loads((ROOT/(name+'.json')).read_text());actual=[r for r in packet['samples'] if r['fresh_after_passive_connection']]
 if not actual:raise RuntimeError(name+':no actual fresh SDK feedback')
 return packet,actual[-1]
def feedback(msg):
 global latest
 values=dict(zip(msg.name,msg.position))
 if all(n in values for n in NAMES):latest={'epoch':time.time(),'q':[values[n] for n in NAMES],
   'gap_m':values.get('gripper'),'source_stamp_ns':str(msg.header.stamp.sec*10**9+msg.header.stamp.nanosec)}
def command(msg):
 global first
 values=dict(zip(msg.name,msg.position))
 if first is None and all(n in values for n in NAMES):first={'epoch':time.time(),'q':[values[n] for n in NAMES]}
def event(msg):
 global reason
 reason=msg.data;report['events'].append({'reason':reason,'epoch':time.time()});print('CONTROLLER:',reason,flush=True)

print(ROOT,flush=True)
rclpy.init();node=rclpy.create_node('calibration_board_authorized_observe_return')
node.create_subscription(JointState,'/joint_states_feedback',feedback,qos_profile_sensor_data)
node.create_subscription(JointState,'/joint_commands',command,qos_profile_sensor_data)
node.create_subscription(String,'/brain_robot_visual_control/reason',event,10)
try:
 report['adapter_sha256']=hashlib.sha256(ADAPTER.read_bytes()).hexdigest()
 assert report['adapter_sha256']=='5c1c1be24b4519705ae1e58a31e26085a9c1832cdd7626e93f6c6392b621a172'
 frozen=json.loads(FROZEN.read_text());save('production_SHA_before.json',frozen)
 for p,v in frozen.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==v
 report['kernel_before']=subprocess.run(['sudo','-n','dmesg','-T'],capture_output=True,text=True,check=True,timeout=5).stdout
 report['CAN_full_before']=json.loads(subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,check=True,timeout=3).stdout)
 start('raw_CAN',['timeout','-k','2s','330s','candump','-L','can0'])
 packet,measured=sdk('sdk_before');report['initial_measured']=measured
 # Reuse the repository's original contiguous-window rule, unchanged.
 # Full-window failure and pulse samples remain in the original SDK report.
 samples=packet['samples'];windows=[]
 for i in range(len(samples)):
  for j in range(i+30,len(samples)+1):
   part=samples[i:j]
   if all(s['fresh_after_passive_connection'] for s in part):
    quality=summarize(part)
    if quality['static_three_seconds_and_thirty_samples']:windows.append({'indices':[i,j],'quality':quality})
 report['original_contiguous_static_window']=max(windows,key=lambda r:r['indices'][1]-r['indices'][0]) if windows else None
 if not windows:raise RuntimeError('No original continuous >=3s/30-sample static window; no driver or movement started')
 assert all(measured['enabled'])
 params=yaml.safe_load(TASK.read_text())['grasp_lift_executor']['ros__parameters']
 lo,hi=params['real_trajectory_joint_min'],params['real_trajectory_joint_max']
 assert all(a<=v<=c for a,v,c in zip(lo,measured['q_driver_rad'],hi))
 before=read_can();time.sleep(.2);after=read_can()
 save('can_before_motion.json',{'before':before,'after':after,'healthy':healthy_window(before,after)})
 assert healthy_window(before,after)
 start('driver',['/usr/bin/python3','-c',"import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()",'--ros-args','--log-level','WARN',
  '-p','can_port:=can0','-p','auto_enable:=false','-p','gripper_exist:=true','-r','joint_states_single:=/joint_states','-r','joint_ctrl_single:=/joint_commands'])
 start('visual',['/usr/bin/python3',str(LAUNCH)])
 start('bag',['ros2','bag','record','-o',str(ROOT/'motion_witness_bag'),'/joint_states_feedback','/joint_commands',
  '/brain_robot_grasp/arm_trajectory','/brain_robot_grasp/gripper_command','/brain_robot_visual_control/state',
  '/brain_robot_visual_control/reason','/brain_robot_control/adapter_armed'])
 wait(lambda:latest is not None and time.time()-latest['epoch']<.5,18,'fresh original driver feedback')
 assert max(abs(a-v) for a,v in zip(latest['q'],measured['q_driver_rad']))<=.001
 result=call('/visual_search_controller/set_parameters',SetParameters,SetParameters.Request(parameters=[Parameter(name='stop_after_observe',value=ParameterValue(type=ParameterType.PARAMETER_BOOL,bool_value=True))]))
 assert result.results[0].successful
 result=call('/visual_search_controller/get_parameters',GetParameters,GetParameters.Request(names=['stop_after_observe']))
 assert result.values[0].bool_value;report['stop_after_observe_readback']=True
 result=call('/enable_srv',Enable,Enable.Request(enable_request=True));report['original_enable_true_requested']=True
 assert result.enable_response
 _,enabled=sdk('sdk_after_enable');report['enabled_measured']=enabled
 assert all(enabled['enabled']) and max(abs(a-v) for a,v in zip(enabled['q_driver_rad'],measured['q_driver_rad']))<=.001
 wait(lambda:latest is not None and time.time()-latest['epoch']<.5,20,'post-enable feedback')
 trigger('/piper_jog_adapter/enable_motion');report['feedback_at_arm']=dict(latest)
 trigger('/piper_jog_adapter/arm');armed=True
 wait(lambda:first is not None,5,'first original adapter command');report['first_command']=first
 assert max(abs(a-v) for a,v in zip(first['q'],report['feedback_at_arm']['q']))<=.001
 print('ORIGINAL_OBSERVE_CHECKLIST',json.dumps({'actual_start_rad':latest['q'],'goal_rad':yaml.safe_load(TASK.read_text())['visual_search_controller']['ros__parameters']['observe_joint_positions'],'enabled':enabled['enabled'],'limits_min':lo,'limits_max':hi,'prepare_velocity_acceleration_scaling':[.01,.01],'adapter_max_rad_s':.189,'timeout_s':300,'stop_after_observe':True,'no_search_gripper_reset_disable':True}),flush=True)
 trigger('/visual_search_controller/start')
 wait(lambda:'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH' in reason or 'FAILED' in reason or reason=='PIPER_ADAPTER_DISARMED' or reason.startswith('FAULT'),305,'original observation completion')
 assert 'OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH' in reason
 report['observe_reached']=True;report['observe_feedback']=dict(latest)
 trigger('/piper_jog_adapter/disarm');armed=False
 _,report['final_sdk']=sdk('sdk_at_observation')
except BaseException as e:
 report['error']=repr(e);print('SESSION STOP:',repr(e),flush=True)
finally:
 if armed:
  for path in ['/visual_search_controller/stop','/piper_jog_adapter/disarm']:
   try:trigger(path)
   except BaseException as e:report['events'].append({'stop_service':path,'error':repr(e)})
 for name,p,f in reversed(jobs):
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGINT)
   try:p.wait(timeout=2)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
  f.close();report['events'].append({'name':name,'final_exit_code':p.returncode,'epoch':time.time()})
 report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
 report['last_received_feedback']=latest;save('can_after_motion.json',read_can())
 report['kernel_after']=subprocess.run(['sudo','-n','dmesg','-T'],capture_output=True,text=True,timeout=5).stdout
 report['CAN_full_after']=json.loads(subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,check=True,timeout=3).stdout)
 save('production_SHA_after.json',{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in json.loads(FROZEN.read_text())})
 save('execution_session.json',report);node.destroy_node()
 if rclpy.ok():rclpy.shutdown()
print(json.dumps({'root':str(ROOT),'gripper_command_published':report['gripper_command_published'],'observe_reached':report['observe_reached'],
 'error':report['error'],'all_exited':report['all_owned_sources_exited']}),flush=True)
raise SystemExit(0 if report['observe_reached'] and report['error'] is None else 2)
