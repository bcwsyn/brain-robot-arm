"""One authorized in-place gripper open through original driver+adapter only."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
import rclpy,yaml
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger
from piper_msgs.srv import Enable
ROOT=Path(tempfile.mkdtemp(prefix='piper_board_open_only.',dir='/home/johnwick/brain_robot_logs'))
REPO=Path('/mnt/hgfs/ub');TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from collect_calibration_p0 import read_can,healthy_window
from collect_calibration_sdk import summarize
NAMES=[f'joint{i}' for i in range(1,7)]
baseline=json.loads((REPO/'docs/evidence/piper_calibration_p1_20261015/board_preview/production_SHA_before.json').read_text())
report={'scope':'authorized_in_place_open_only','operator_quote':'好的',
 'permission_context':'Assistant requested original in-place opening so user can remove cube; no observation return authorized',
 'opened':False,'observe_return_requested':False,'trajectory_published':False,'reset_or_disable_requested':False,
 'production_modified':False,'events':[],'commands':[],'feedback':[],'error':None}
jobs=[];latest=None;armed=False;first=None
def save(name,value):
 with (ROOT/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False)
def hashes():return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
def start(name,argv):
 stream=(ROOT/(name+'.log')).open('xb');process=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 jobs.append((name,process,stream));report['events'].append({'started':name,'pid':process.pid,'argv':argv,'epoch':time.time()})
 return process
def wait(predicate,seconds,label):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  rclpy.spin_once(node,timeout_sec=.03)
  if predicate():return
 raise TimeoutError(label)
def call(path,kind,request):
 client=node.create_client(kind,path)
 try:
  wait(client.service_is_ready,18,path+' discovery')
  future=client.call_async(request);wait(future.done,18,path+' response, not retried')
  response=future.result();report['events'].append({'service':path,'response':str(response),'epoch':time.time()})
  return response
 finally:node.destroy_client(client)
def trigger(path):
 response=call(path,Trigger,Trigger.Request())
 if not response.success:raise RuntimeError(path+':'+response.message)
def sdk(name,duration):
 process=start(name,['/usr/bin/python3',str(TESTS/'collect_calibration_sdk.py'),'--output',str(ROOT/(name+'.json')),'--duration-s',str(duration)])
 wait(lambda:process.poll() is not None,duration+6,name)
 packet=json.loads((ROOT/(name+'.json')).read_text());fresh=[s for s in packet['samples'] if s['fresh_after_passive_connection']]
 report['events'].append({'sdk':name,'returncode':process.returncode,'quality':packet['quality']})
 if not fresh:raise RuntimeError(name+': no actual fresh feedback')
 return packet,fresh[-1]
def feedback(msg):
 global latest
 values=dict(zip(msg.name,msg.position))
 if all(name in values for name in NAMES):
  latest={'epoch':time.time(),'q':[values[name] for name in NAMES],'gap_m':values.get('gripper'),
          'source_stamp_ns':str(msg.header.stamp.sec*10**9+msg.header.stamp.nanosec)}
  if len(report['feedback'])<5000:report['feedback'].append(dict(latest))
def command(msg):
 global first
 values=dict(zip(msg.name,msg.position))
 if all(name in values for name in NAMES):
  row={'epoch':time.time(),'q':[values[name] for name in NAMES],'gap_m':values.get('gripper'),'effort':list(msg.effort)}
  if first is None:first=row
  if len(report['commands'])<3000:report['commands'].append(row)

print(ROOT,flush=True);rclpy.init();node=rclpy.create_node('authorized_board_in_place_open_only')
node.create_subscription(JointState,'/joint_states_feedback',feedback,qos_profile_sensor_data)
node.create_subscription(JointState,'/joint_commands',command,qos_profile_sensor_data)
jaw=node.create_publisher(JointState,'/brain_robot_grasp/gripper_command',10)
try:
 before_hash=hashes();assert before_hash==baseline;save('production_SHA_before.json',before_hash)
 packet,measured=sdk('sdk_before',10);report['initial_measured']=measured
 samples=packet['samples'];windows=[]
 for i in range(len(samples)):
  for j in range(i+30,len(samples)+1):
   part=samples[i:j]
   if all(s['fresh_after_passive_connection'] for s in part):
    quality=summarize(part)
    if quality['static_three_seconds_and_thirty_samples']:windows.append({'indices':[i,j],'quality':quality})
 if not windows:raise RuntimeError('No original3s/30-sample static interval; no driver/adapter started')
 report['original_static_window']=max(windows,key=lambda w:w['indices'][1]-w['indices'][0])
 assert all(measured['enabled']), 'Expected already enabled arm; this limited task does not restore disabled axes'
 params=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())['grasp_lift_executor']['ros__parameters']
 assert all(lo<=q<=hi for lo,q,hi in zip(params['real_trajectory_joint_min'],measured['q_driver_rad'],params['real_trajectory_joint_max']))
 a=read_can();time.sleep(.2);b=read_can();save('can_before.json',{'before':a,'after':b,'healthy':healthy_window(a,b)})
 assert healthy_window(a,b)
 start('driver',['/usr/bin/python3','-c',"import sys;sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages');from piper.piper_ctrl_single_node import main;main()",'--ros-args','--log-level','WARN',
  '-p','can_port:=can0','-p','auto_enable:=false','-p','gripper_exist:=true','-r','joint_states_single:=/joint_states','-r','joint_ctrl_single:=/joint_commands'])
 start('adapter',['/usr/bin/python3','/tmp/piper_original_adapter_only_launch.py'])
 start('bag',['ros2','bag','record','-o',str(ROOT/'open_witness_bag'),'/joint_states_feedback','/joint_commands',
  '/brain_robot_grasp/gripper_command','/brain_robot_grasp/arm_trajectory'])
 wait(lambda:latest is not None and time.time()-latest['epoch']<.5,18,'fresh original driver feedback')
 assert max(abs(x-y) for x,y in zip(latest['q'],measured['q_driver_rad']))<=.001
 response=call('/enable_srv',Enable,Enable.Request(enable_request=True));assert response.enable_response
 report['original_enable_service_sync_for_already_enabled_arm']=True
 _,enabled=sdk('sdk_after_enable',6);report['after_enable_measured']=enabled
 assert all(enabled['enabled']) and max(abs(x-y) for x,y in zip(enabled['q_driver_rad'],measured['q_driver_rad']))<=.001
 wait(lambda:latest is not None and time.time()-latest['epoch']<.5,18,'fresh post-enable feedback')
 trigger('/piper_jog_adapter/enable_motion');report['feedback_at_arm']=dict(latest)
 trigger('/piper_jog_adapter/arm');armed=True
 wait(lambda:first is not None,5,'first original hold command')
 assert max(abs(x-y) for x,y in zip(first['q'],report['feedback_at_arm']['q']))<=.001
 wait(lambda:jaw.get_subscription_count()>0,8,'original gripper subscriber')
 assert max(abs(x-y) for x,y in zip(latest['q'],measured['q_driver_rad']))<=.001
 report['before_open_feedback']=dict(latest)
 message=JointState();message.name=['gripper'];message.position=[.1];jaw.publish(message);sent=time.time()
 report['events'].append({'published':'/brain_robot_grasp/gripper_command','position_m':.1,'epoch':sent})
 print('OPEN_ONLY_100MM_REQUESTED',flush=True)
 wait(lambda:time.time()-sent>=1.7 and latest['gap_m'] is not None and abs(latest['gap_m']-.1)<=.003
      and time.time()-latest['epoch']<.5,15,'original100mm open tolerance and bounded80-frame burst')
 report['opened']=True;report['opened_feedback']=dict(latest)
 trigger('/piper_jog_adapter/disarm');armed=False
 _,final=sdk('sdk_after_open',6);report['final_measured']=final
 report['final_q_delta_rad']=[x-y for x,y in zip(final['q_driver_rad'],measured['q_driver_rad'])]
 assert all(final['enabled']) and abs(final['gripper_mm']-100)<=3
except BaseException as error:
 report['error']=repr(error);print('OPEN_ONLY_STOP:',repr(error),flush=True)
finally:
 if armed:
  try:trigger('/piper_jog_adapter/disarm')
  except BaseException as error:report['events'].append({'software_disarm_error':repr(error)})
 for name,process,stream in reversed(jobs):
  if process.poll() is None:
   os.killpg(process.pid,signal.SIGINT)
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
  stream.close();report['events'].append({'exited':name,'returncode':process.returncode,'epoch':time.time()})
 report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
 report['last_feedback']=latest;save('can_after.json',read_can());save('production_SHA_after.json',hashes())
 save('execution.json',report);node.destroy_node()
 if rclpy.ok():rclpy.shutdown()
print(json.dumps({'root':str(ROOT),'opened':report['opened'],'error':report['error'],'all_exited':report['all_owned_sources_exited']}),flush=True)
raise SystemExit(0 if report['opened'] and report['error'] is None else 2)
