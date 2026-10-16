"""Read actual camera-internal transforms; no robot nodes or camera setters."""
import json,time
from pathlib import Path
import rclpy
from tf2_ros import Buffer,TransformListener
from rosidl_runtime_py.convert import message_to_ordereddict
ROOT=Path(__file__).resolve().parent
rclpy.init();node=rclpy.create_node('read_camera_internal_tf_before_deployment')
buffer=Buffer();listener=TransformListener(buffer,node)
report={'read_only':True,'epoch':time.time(),'motion_commands_sent':False,'transforms':{},'error':None}
pairs=[('camera_link','camera_depth_optical_frame'),('camera_link','camera_color_optical_frame'),
       ('camera_depth_optical_frame','camera_color_optical_frame'),('camera_color_optical_frame','camera_depth_optical_frame')]
try:
    end=time.monotonic()+12
    while time.monotonic()<end:
        rclpy.spin_once(node,timeout_sec=.05)
        for parent,child in pairs:
            if buffer.can_transform(parent,child,rclpy.time.Time()):
                report['transforms'][parent+'<-'+child]=message_to_ordereddict(buffer.lookup_transform(parent,child,rclpy.time.Time()))
        if len(report['transforms'])==len(pairs):break
    if len(report['transforms'])!=len(pairs):raise RuntimeError('Incomplete actual internal TF chain')
except BaseException as e:report['error']=repr(e)
finally:
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'internal_tf_actual.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'pairs':list(report['transforms']),'error':report['error']}))
raise SystemExit(0 if report['error'] is None else 2)
