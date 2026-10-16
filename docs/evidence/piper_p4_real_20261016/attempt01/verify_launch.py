"""Read back actual original-launch P4 parameters in isolated domain 78."""
import json,os,signal,subprocess,time
from pathlib import Path
os.environ['ROS_DOMAIN_ID']='78'
import rclpy
from rcl_interfaces.srv import GetParameters
ROOT=Path(__file__).resolve().parent
env=dict(os.environ,BRAIN_ROBOT_P4_OPEN_LOOP='1',BRAIN_ROBOT_P4_PLAN_ONLY='1',
 BRAIN_ROBOT_P4_TARGET_CONFIG=str(ROOT/'frozen_target.yaml'))
stream=(ROOT/'launch_parameter_probe.log').open('x')
p=subprocess.Popen(['ros2','launch','brain_robot_ball_pick','cube_visual_search.launch.py'],
 env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
report={'isolated_domain':78,'original_full_launch':True,'driver_or_CAN_started':False,
 'motion_enable_or_start_or_execute_called':False,'values':{},'passed':False}
rclpy.init();node=rclpy.create_node('P4_readonly_parameter_probe')
try:
    expected={'visual_search_controller':{'stop_after_observe':True},
      'grasp_lift_executor':{'auto_release_after_lift':False,'p4_open_loop_enabled':True,'p4_plan_only':True}}
    for name,wanted in expected.items():
        client=node.create_client(GetParameters,'/'+name+'/get_parameters')
        if not client.wait_for_service(timeout_sec=25):raise RuntimeError(name+' parameter service absent')
        request=GetParameters.Request();request.names=list(wanted)
        f=client.call_async(request);rclpy.spin_until_future_complete(node,f,timeout_sec=5)
        if not f.done() or f.result() is None:raise RuntimeError(name+' readback timed out')
        got={key:value.bool_value for key,value in zip(request.names,f.result().values)}
        report['values'][name]=got
        if got!=wanted:raise RuntimeError(name+' wrong runtime parameters')
    report['passed']=True
except BaseException as error:report['error']=repr(error)
finally:
    node.destroy_node();rclpy.shutdown()
    if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    try:p.wait(timeout=6)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
    stream.close();report['launch_parent_rc']=p.returncode
    with (ROOT/'launch_parameter_probe.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
raise SystemExit(0 if report['passed'] else 2)
