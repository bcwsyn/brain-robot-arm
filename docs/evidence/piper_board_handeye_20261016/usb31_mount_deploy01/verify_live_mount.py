"""Verify the approved COLOR optical X at original image stamps, never latest TF."""
import json, time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, JointState
from tf2_ros import Buffer, TransformListener
from rosidl_runtime_py.convert import message_to_ordereddict

ROOT = Path(__file__).resolve().parent
EXPECTED = np.array(json.loads((ROOT / 'live_composition_review.json').read_text())[
    'approved_T_gripperBase_colorOptical_unchanged'])
def matrix(t):
    p, q = t.transform.translation, t.transform.rotation
    out = np.eye(4)
    out[:3,:3] = Rotation.from_quat([q.x,q.y,q.z,q.w]).as_matrix()
    out[:3,3] = [p.x,p.y,p.z]
    return out
def error(a,b):
    return {'translation_m':float(np.linalg.norm(a[:3,3]-b[:3,3])),
        'rotation_deg':float(Rotation.from_matrix(a[:3,:3].T@b[:3,:3]).magnitude()*180/np.pi)}

rclpy.init(); node = rclpy.create_node('verify_adopted_handeye_no_control')
buffer = Buffer(); listener = TransformListener(buffer,node)
pending = []; qrows = []; samples = []; errors = []
def image(m):
    if len(pending)<12:
        pending.append((m.header.stamp, m.header.frame_id, time.monotonic(),m.width,m.height))
def joints(m):
    qrows.append({'header':message_to_ordereddict(m.header),'name':list(m.name),
        'position':list(m.position),'velocity':list(m.velocity)})
node.create_subscription(Image,'/camera/color/image_raw',image,qos_profile_sensor_data)
node.create_subscription(JointState,'/joint_states_feedback',joints,qos_profile_sensor_data)
report={'read_only':True,'uses_actual_image_stamp':True,'latest_fallback':False,
    'motion_commands_sent':False,'samples':samples,'errors':errors,'epoch':time.time()}
try:
    deadline = time.monotonic()+40
    while rclpy.ok() and time.monotonic()<deadline and len(samples)<5:
        rclpy.spin_once(node,timeout_sec=.02)
        if not pending: continue
        stamp,frame,arrived,width,height = pending[0]
        when = rclpy.time.Time.from_msg(stamp)
        pairs=[('gripper_base',frame),('camera_link',frame),('base_link','gripper_base'),('base_link',frame)]
        if not all(buffer.can_transform(a,b,when) for a,b in pairs):
            if time.monotonic()-arrived>2:
                errors.append({'stamp':message_to_ordereddict(stamp),'reason':'exact-stamp TF unavailable after 2s'})
                pending.pop(0)
            continue
        transforms={a+'<-'+b:buffer.lookup_transform(a,b,when) for a,b in pairs}
        got=matrix(transforms['gripper_base<-'+frame])
        base_g=matrix(transforms['base_link<-gripper_base'])
        base_c=matrix(transforms['base_link<-'+frame])
        e=error(got,EXPECTED); chain=error(base_c,base_g@EXPECTED)
        row={'image_stamp':message_to_ordereddict(stamp),'image_frame':frame,
            'width':width,'height':height,'X_error':e,'base_chain_error':chain,
            'transforms':{k:message_to_ordereddict(v) for k,v in transforms.items()},
            'joint_feedback_latest_received':qrows[-1] if qrows else None,
            'joint_note':'Recorded actual received feedback; TF interpolation uses the image stamp, not this latest sample.'}
        samples.append(row);pending.pop(0)
        if e['translation_m']>1e-8 or e['rotation_deg']>1e-5 or chain['translation_m']>1e-8:
            raise RuntimeError('Published TF does not reproduce the approved X')
    report['verified']=len(samples)==5 and bool(qrows) and not errors
except BaseException as exc:
    report['exception']=repr(exc);report['verified']=False
finally:
    report['feedback_messages']=len(qrows);report['end_epoch']=time.time()
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'live_mount_verification.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'verified':report['verified'],'samples':len(samples),'errors':errors}))
raise SystemExit(0 if report['verified'] else 2)
