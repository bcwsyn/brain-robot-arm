"""Exact-stamp TF verification on the same five archived RGB-D pairs; no control."""
import hashlib,json,time
from pathlib import Path
import cv2,numpy as np,yaml
from scipy.spatial.transform import Rotation
import rclpy
from tf2_ros import Buffer,TransformListener
from rosidl_runtime_py.convert import message_to_ordereddict
ROOT=Path(__file__).resolve().parent
X=np.asarray(json.loads((ROOT/'paired_mount_prediction.json').read_text())['approved_X_G_color_unchanged'])
params=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml').read_text())['cube_detector']['ros__parameters']
CD=np.eye(4);CD[:3,:3]=np.array(params['depth_to_color_rotation']).reshape(3,3);CD[:3,3]=params['depth_to_color_translation_m']
binary=Path('/home/johnwick/ros2_ws/build/astra_camera/libastra_camera.so')
def matrix(t):
    p,q=t.transform.translation,t.transform.rotation
    out=np.eye(4);out[:3,:3]=Rotation.from_quat([q.x,q.y,q.z,q.w]).as_matrix();out[:3,3]=[p.x,p.y,p.z]
    return out
def error(a,b):
    return {'translation_m':float(np.linalg.norm(a[:3,3]-b[:3,3])),
        'rotation_deg':float(Rotation.from_matrix(a[:3,:3].T@b[:3,:3]).magnitude()*180/np.pi),
        'max_matrix_difference':float(np.max(np.abs(a-b)))}
rclpy.init();node=rclpy.create_node('verify_paired_rgbd_geometry_no_control')
buffer=Buffer();listener=TransformListener(buffer,node)
report={'epoch':time.time(),'read_only':True,'motion_commands_sent':False,
 'exact_archived_RGBD_stamps':True,'latest_fallback':False,'samples':[],
 'loaded_camera_libraries':[],'exception':None,'verified':False}
try:
    deadline=time.monotonic()+40
    while rclpy.ok() and time.monotonic()<deadline and len(report['samples'])<5:
        rclpy.spin_once(node,timeout_sec=.02)
        observer=ROOT/'capture/observer.jsonl'
        if not observer.exists():continue
        lines=observer.read_text().splitlines()
        if len(lines)<=len(report['samples']):continue
        try:row=json.loads(lines[len(report['samples'])])
        except json.JSONDecodeError:continue
        rgbtime=rclpy.time.Time(nanoseconds=int(row['stamps_ns']['rgb']))
        depthtime=rclpy.time.Time(nanoseconds=int(row['stamps_ns']['depth']))
        pairs=[('gripper_base','camera_color_optical_frame',rgbtime),
               ('base_link','camera_color_optical_frame',rgbtime),
               ('base_link','gripper_base',rgbtime),
               ('camera_color_optical_frame','camera_depth_optical_frame',depthtime),
               ('gripper_base','camera_depth_optical_frame',depthtime),
               ('base_link','camera_depth_optical_frame',depthtime),
               ('base_link','camera_color_optical_frame',depthtime),
               ('base_link','gripper_base',depthtime),
               ('camera_link','camera_color_optical_frame',depthtime)]
        if not all(buffer.can_transform(a,b,t) for a,b,t in pairs):continue
        actual=[buffer.lookup_transform(a,b,t) for a,b,t in pairs];m=[matrix(t) for t in actual]
        errors={'color_X':error(m[0],X),'RGB_base_chain':error(m[1],m[2]@X),
            'internal_color_from_depth':error(m[3],CD),'gripper_depth_chain':error(m[4],X@CD),
            'depth_base_chain':error(m[5],m[7]@X@CD)}
        if errors['color_X']['translation_m']>1e-8 or errors['color_X']['rotation_deg']>1e-5:
            raise RuntimeError('Approved color hand-eye X not preserved')
        if errors['internal_color_from_depth']['translation_m']>2e-9 or errors['internal_color_from_depth']['max_matrix_difference']>1e-7:
            raise RuntimeError('Internal TF still disagrees with detector factory registration')
        if max(errors[k]['translation_m'] for k in ['RGB_base_chain','gripper_depth_chain','depth_base_chain'])>1e-8:
            raise RuntimeError('End-to-end depth/base chain mismatch')
        depth=cv2.imread(row['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
        valid=np.argwhere((depth>150)&(depth<1000))
        chosen=valid[np.linspace(0,len(valid)-1,5,dtype=int)]
        kd=np.array(row['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
        points=[]
        for y,x in chosen:
            z=depth[y,x]*.001;p=np.array([(x-kd[0,2])*z/kd[0,0],(y-kd[1,2])*z/kd[1,1],z,1])
            a=m[5]@p;b=m[6]@CD@p
            points.append({'native_pixel_xy':[int(x),int(y)],'depth_m':z,
                'depth_point_m':p[:3].tolist(),'base_via_depth_m':a[:3].tolist(),
                'base_via_color_factory_m':b[:3].tolist(),'path_difference_m':float(np.linalg.norm(a[:3]-b[:3]))})
        report['samples'].append({'snapshot':row['snapshot'],'RGB_stamp_ns':row['stamps_ns']['rgb'],
            'depth_stamp_ns':row['stamps_ns']['depth'],'q_rad':row['q_rad'],'images':row['images'],
            'errors':errors,'real_depth_point_path_comparison':points,
            'transforms':[message_to_ordereddict(t) for t in actual]})
        if not report['loaded_camera_libraries']:
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    maps=(proc/'maps').read_text()
                    loaded=sorted(set(line.split()[-1] for line in maps.splitlines() if 'libastra_camera.so' in line))
                    if loaded:report['loaded_camera_libraries'].append({'pid':int(proc.name),'mapped_paths':loaded,
                        'expected_binary_SHA256':hashlib.sha256(binary.read_bytes()).hexdigest()})
                except (OSError,UnicodeError):pass
    report['verified']=len(report['samples'])==5 and bool(report['loaded_camera_libraries'])
except BaseException as exc:report['exception']=repr(exc)
finally:
    report['end_epoch']=time.time();node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'live_mount_verification.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'verified':report['verified'],'samples':len(report['samples']),'exception':report['exception']}))
raise SystemExit(0 if report['verified'] else 2)
