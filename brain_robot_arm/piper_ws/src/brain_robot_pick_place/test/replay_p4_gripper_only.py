"""Bounded domain78 synthetic-only test. No driver/adapter/CAN APIs or publishers."""
import argparse,json,os,time
from pathlib import Path
assert os.environ.get('ROS_DOMAIN_ID')=='78'
import rclpy
from rclpy.qos import QoSProfile,DurabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String,UInt8,Bool
from std_srvs.srv import Trigger
from rcl_interfaces.srv import GetParameters
from trajectory_msgs.msg import JointTrajectory


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',choices=['empty','object','stale'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    rclpy.init();node=rclpy.create_node('SYNTHETIC_gripper_only_fixture')
    opening=.0004;reference=.0004;max_opening=.0004;states=[];diagnostics=[];commands=[];arm=[];joints=[]
    pub=node.create_publisher(JointState,'/joint_states',10)
    grip=node.create_publisher(JointState,'/piper/gripper_feedback',10)
    status=node.create_publisher(UInt8,'/piper/gripper_status',10)
    stop=node.create_publisher(Bool,'/brain_robot_control/emergency_stop',10)
    def receive_grip(m):
        nonlocal reference
        reference=m.position[0];commands.append({'epoch':time.time(),'reference_m':reference})
    subs=[node.create_subscription(String,'/brain_robot_grasp/state',lambda m:states.append(m.data),
            QoSProfile(depth=20,durability=DurabilityPolicy.TRANSIENT_LOCAL)),
        node.create_subscription(String,'/brain_robot_grasp/diagnostic',lambda m:diagnostics.append(m.data),
            QoSProfile(depth=30,durability=DurabilityPolicy.TRANSIENT_LOCAL)),
        node.create_subscription(JointState,'/brain_robot_grasp/gripper_command',receive_grip,10),
        node.create_subscription(JointTrajectory,'/brain_robot_grasp/arm_trajectory',lambda m:arm.append(1),10),
        node.create_subscription(JointState,'/joint_commands',lambda m:joints.append(1),10)]
    def tick():
        nonlocal opening,max_opening
        opening+=max(-.0002,min(.002,reference-opening))
        if args.scenario=='object' and 'P4_GRIPPER_TEST_CLOSING' in states:opening=max(.037,opening)
        max_opening=max(max_opening,opening)
        m=JointState();m.header.stamp=node.get_clock().now().to_msg()
        m.name=[f'joint{i}' for i in range(1,9)]
        m.position=[-.049872396,1.652784112,-1.009274952,.044953188,.778944376,.088894624,opening/2,-opening/2]
        m.velocity=[0.]*8;pub.publish(m)
        if args.scenario=='stale' and 'P4_GRIPPER_TEST_CLOSING' in states and opening<.09:return
        g=JointState();g.header.stamp=m.header.stamp;g.name=['gripper'];g.position=[opening]
        loaded=args.scenario=='object' and opening<=.037001 and reference<opening-.00025
        g.effort=[-.3 if loaded else -.02];grip.publish(g);status.publish(UInt8(data=0x40))
    timer=node.create_timer(.02,tick)
    def stop_servo(_req,res):res.success=True;res.message='synthetic no Servo';return res
    service=node.create_service(Trigger,'/servo_node/stop_servo',stop_servo)
    def call(name):
        client=node.create_client(Trigger,name)
        assert client.wait_for_service(timeout_sec=2),name
        future=client.call_async(Trigger.Request())
        end=time.monotonic()+3
        while not future.done() and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.02)
        assert future.done(),name
        return future.result()
    result={'domain':78,'synthetic_only':True,'hardware_or_CAN':False,'scenario':args.scenario}
    started=time.monotonic()
    try:
        end=started+35
        while 'P4_READY_FOR_EXPLICIT_EXECUTE' not in states and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.02)
        assert 'P4_READY_FOR_EXPLICIT_EXECUTE' in states
        assert not call('/grasp_lift_executor/execute').success
        assert call('/grasp_lift_executor/test_gentle_gripper').success
        assert not call('/grasp_lift_executor/test_gentle_gripper').success,'busy request accepted'
        end=time.monotonic()+35
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)
            if states[-1].startswith('FAULT_') or states[-1].endswith('_NO_LIFT'):break
        expected={'empty':'P4_GRIPPER_TEST_EMPTY_NO_LIFT',
            'object':'P4_GRIPPER_TEST_CONTACT_CANDIDATE_NO_LIFT',
            'stale':'FAULT_P4_GRIPPER_TEST_CLOSE_UNCONFIRMED'}[args.scenario]
        assert states[-1]==expected,(states,expected)
        assert not arm and not joints and 'LIFTING' not in states and 'HOLDING' not in states
        assert commands[0]['reference_m']==.1
        assert max_opening>=.0995,'Full-open reference reversed before opening finished'
        assert all(c['reference_m']>=.025-1e-8 for c in commands)
        stop.publish(Bool(data=True));end=time.monotonic()+2
        while states[-1]!='FAULT_ESTOP' and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.02)
        assert states[-1]=='FAULT_ESTOP'
        assert not call('/grasp_lift_executor/test_gentle_gripper').success
        result['passed']=True
    except BaseException as exc:result.update(passed=False,error=repr(exc))
    finally:
        result.update(states=states,diagnostics=diagnostics,gripper_commands=commands,
            arm_trajectories=len(arm),joint_commands=len(joints),last_opening_m=opening,max_opening_m=max_opening,
            elapsed_s=time.monotonic()-started,physical_grasp_succeeded=False)
        with args.output.open('x') as f:json.dump(result,f,indent=2)
        node.destroy_node();rclpy.shutdown()
    print(json.dumps({k:v for k,v in result.items() if k not in ['diagnostics','gripper_commands']}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
