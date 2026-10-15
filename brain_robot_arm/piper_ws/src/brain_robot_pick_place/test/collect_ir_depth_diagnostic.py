#!/usr/bin/env python3
"""Passive, bounded IR/depth/Info/real-q recorder; no RPCs or control publishers.

Diagnostic only. Streams are paired with their own exact-stamp Info, never with
each other by pixel or assumed hardware time. No image enhancement or hole fill.
"""
import argparse
import json
import math
from pathlib import Path
import time

from native_depth_diagnostic import NativeDepthRecorder


def validate(output, duration_s):
    if output.exists():
        raise FileExistsError('Refusing to overwrite before ROS initialization')
    if not math.isfinite(duration_s) or not 1 <= duration_s <= 26:
        raise ValueError('Duration must be within 1..26 seconds')


def deliver_feedback(recorders, message, now_ns, epoch):
    for recorder in recorders.values():
        recorder.receive('feedback',message,now_ns,epoch)


def process_ready_then_feedback_lost(node, recorders, elapsed_s, spin_once):
    # Do not declare loss before dispatching feedback already ready in this node.
    # Bounded draining changes scheduling, never message time or the 500ms rule.
    for _ in range(32):
        spin_once(node,timeout_sec=0.)
    now_ns=node.get_clock().now().nanoseconds
    return any(r.lost(now_ns,elapsed_s) for r in recorders.values())


def result_code(report):
    complete=(not report.get('error') and not report.get('stop_reason') and
              all(s['saved_frames']>=2 and not s['stop_reason'] for s in report['streams'].values()))
    return 0 if complete else 2


def collect(output, duration_s):
    validate(output,duration_s)
    import rclpy
    from sensor_msgs.msg import Image, CameraInfo, JointState
    from rclpy.qos import qos_profile_sensor_data
    output.mkdir()
    report={'diagnostic_only':True,'motion_commands_sent':False,'RPCs_sent':0,
            'depth_IR_hardware_sync_verified':False,'pixel_alignment_assumed':False,
            'duration_limit_s':duration_s,'error':None,'start_epoch':time.time()}
    recorders={kind:NativeDepthRecorder(output/kind,stream_kind=kind) for kind in ('depth','ir')}
    node=None
    rclpy.init()
    began=time.monotonic()
    try:
        node=rclpy.create_node('calibration_ir_depth_passive')
        subscriptions=[]
        for kind,recorder in recorders.items():
            for tag,msg_type,topic in [(kind,Image,f'/camera/{kind}/image_raw'),
                                      ('info',CameraInfo,f'/camera/{kind}/camera_info')]:
                subscriptions.append(node.create_subscription(msg_type,topic,
                    lambda msg,recorder=recorder,tag=tag: recorder.receive(
                        tag,msg,node.get_clock().now().nanoseconds,time.time()),qos_profile_sensor_data))
        subscriptions.append(node.create_subscription(JointState,'/joint_states_feedback',
            lambda msg:deliver_feedback(recorders,msg,node.get_clock().now().nanoseconds,time.time()),
            qos_profile_sensor_data))
        while rclpy.ok() and time.monotonic()-began<duration_s:
            rclpy.spin_once(node,timeout_sec=.01)
            if process_ready_then_feedback_lost(node,recorders,time.monotonic()-began,rclpy.spin_once):
                report['stop_reason']='feedback_lost_original_500ms_rule'
                break
    except KeyboardInterrupt:
        report['interrupted']=True
    except Exception as exc:
        report['error']=repr(exc)
    finally:
        report['streams']={kind:recorder.finish() for kind,recorder in recorders.items()}
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        report['elapsed_s']=time.monotonic()-began
        report['end_epoch']=time.time()
        with (output/'summary.json').open('x') as stream:
            json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report),flush=True)
    return result_code(report)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration-s',type=float,default=24.)
    args=parser.parse_args()
    raise SystemExit(collect(args.output,args.duration_s))
