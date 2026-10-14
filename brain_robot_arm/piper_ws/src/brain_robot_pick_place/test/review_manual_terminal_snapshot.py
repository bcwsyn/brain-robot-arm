"""Bounded camera/CAN read-only snapshot; no publisher or control calls."""
import sys, time, json, math, hashlib, importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import cv2, numpy as np, yaml, rclpy
from scipy.spatial.transform import Rotation
from cv_bridge import CvBridge
from sensor_msgs.msg import Image, CameraInfo
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.qos import qos_profile_sensor_data
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder
sys.path.append('/home/johnwick/.local/lib/python3.10/site-packages')
from piper_sdk import C_PiperInterface_V2
sys.path.insert(0, '/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
from review_jaw_scene import poses, transform, jaw_triangles_tool, mesh_projection

out=Path(sys.argv[1]); out.mkdir(exist_ok=False, parents=True)
bridge=CvBridge(); latest={}; joint_rows=[]; rgb_rows=[]
p=C_PiperInterface_V2(can_name='can0',judge_flag=False,can_auto_init=False)
p.CreateCanBus(can_name='can0',judge_flag=False); p.ConnectPort(piper_init=False)
def snap():
 j=p.GetArmJointMsgs(); h=p.GetArmHighSpdInfoMsgs(); l=p.GetArmLowSpdInfoMsgs(); g=p.GetArmGripperMsgs()
 return {'epoch':time.time(),'joint_stamp':j.time_stamp,'low_stamp':l.time_stamp,'high_hz':h.Hz,
 'q_mdeg':[getattr(j.joint_state,'joint_'+str(i)) for i in range(1,7)],
 'speed_millirad_s':[getattr(h,'motor_'+str(i)).motor_speed for i in range(1,7)],
 'enabled':[getattr(l,'motor_'+str(i)).foc_status.driver_enable_status for i in range(1,7)],
 'gripper_mm':g.gripper_state.grippers_angle/1000,
 'gripper_enabled':g.gripper_state.foc_status.driver_enable_status}
def stamp(m):return m.header.stamp.sec*10**9+m.header.stamp.nanosec
rclpy.init(); node=rclpy.create_node('read_only_manual_terminal_capture')
def receive_rgb(m):
 q=snap(); rgb_rows.append({'stamp_ns':str(stamp(m)),'receive_epoch':time.time(),'feedback':q})
 latest['rgb']=m; latest['rgb_feedback']=q
subs=[]
for topic,kind,label in [('/camera/depth/image_raw',Image,'depth'),('/camera/depth/camera_info',CameraInfo,'depth_info'),('/camera/color/camera_info',CameraInfo,'color_info'),('/brain_robot_vision/rgbd_observation',DiagnosticArray,'observation')]:
 subs.append(node.create_subscription(kind,topic,lambda m,label=label:latest.update({label:m}),qos_profile_sensor_data if kind!=DiagnosticArray else 10))
subs.append(node.create_subscription(Image,'/camera/color/image_raw',receive_rgb,qos_profile_sensor_data))
try:
 end=time.monotonic()+5
 while time.monotonic()<end:
  rclpy.spin_once(node,timeout_sec=.025); joint_rows.append(snap())
 if 'rgb' not in latest: raise RuntimeError('No fresh RGB received in bounded window')
 rgb=latest['rgb']; q=latest['rgb_feedback']; image=bridge.imgmsg_to_cv2(rgb,'bgr8')
 rgb_path=out/(str(stamp(rgb))+'_rgb.png'); cv2.imwrite(str(rgb_path),image)
 report={'read_only':True,'motion_commands_sent':False,'rgb_stamp_ns':str(stamp(rgb)),'rgb_frame':rgb.header.frame_id,
 'rgb_path':str(rgb_path),'rgb_sha256':hashlib.sha256(rgb_path.read_bytes()).hexdigest(),
 'rgb_size':[rgb.width,rgb.height],'feedback_at_rgb_receive':q,'feedback_stamp_minus_rgb_s':q['joint_stamp']-stamp(rgb)/1e9,
 'rgb_received':len(rgb_rows),'sdk_samples':len(joint_rows),'camera_info':{},'physical_grasp_verified':False}
 fresh=[s for s in joint_rows if s['epoch']-s['joint_stamp']<.2 and s['high_hz']>0]
 if not fresh:raise RuntimeError('No fresh physical feedback samples')
 report['fresh_sdk_samples']=len(fresh)
 report['stationary_spread_deg']=[(max(s['q_mdeg'][i] for s in fresh)-min(s['q_mdeg'][i] for s in fresh))/1000 for i in range(6)]
 report['max_speed_rad_s']=[max(abs(s['speed_millirad_s'][i]) for s in fresh)/1000 for i in range(6)]
 if 'depth' in latest:
  d=latest['depth']; arr=bridge.imgmsg_to_cv2(d,'passthrough'); dp=out/(str(stamp(d))+'_depth_raw.png'); cv2.imwrite(str(dp),arr)
  report['depth']={'stamp_ns':str(stamp(d)),'rgb_delta_s':(stamp(d)-stamp(rgb))/1e9,'frame':d.header.frame_id,'path':str(dp),'nonzero':int(np.count_nonzero(arr)),'size':[d.width,d.height]}
 for label in ['depth_info','color_info']:
  if label in latest:
   m=latest[label]; report['camera_info'][label]={'stamp_ns':str(stamp(m)),'frame':m.header.frame_id,'size':[m.width,m.height],'k':list(m.k),'d':list(m.d)}
 if 'observation' in latest:
  m=latest['observation']; report['detector_observation']={'stamp_ns':str(stamp(m)),'frame':m.header.frame_id,'status':[{'name':s.name,'level':s.level,'message':s.message,'values':{v.key:v.value for v in s.values}} for s in m.status]}
 share=Path(get_package_share_directory('brain_robot_ball_pick'))
 task_path=share/'config/cube_task_real.yaml'; detector_path=share/'config/cube_detector.yaml'
 task=yaml.safe_load(task_path.read_text()); det=yaml.safe_load(detector_path.read_text())['cube_detector']['ros__parameters']
 spec=importlib.util.spec_from_file_location('actual_visual_launch',share/'launch/cube_visual_search.launch.py'); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 model=MoveItConfigsBuilder('piper',package_name='piper_with_gripper_moveit').to_moveit_configs()
 urdf=mod._physical_gripper_description(model.robot_description['robot_description']); root=ET.fromstring(urdf)
 (out/'actual_runtime_model.urdf').write_text(urdf)
 positions={f'joint{i+1}':v/1000*.017444 for i,v in enumerate(q['q_mdeg'])}
 positions.update(joint7=q['gripper_mm']/2000,joint8=-q['gripper_mm']/2000)
 link=poses(root,positions); mount=task['piper_camera_mount_tf']['ros__parameters']; grasp=task['grasp_lift_executor']['ros__parameters']
 tool_from_depth=np.eye(4); tool_from_depth[:3,3]=mount['translation_m']
 tool_from_depth[:3,:3]=Rotation.from_euler('xyz',mount['rotation_rpy_rad']).as_matrix()@np.array([[0,0,1],[-1,0,0],[0,-1,0]])
 r=np.array(det['depth_to_color_rotation']).reshape(3,3); t=np.array(det['depth_to_color_translation_m'])
 tip=np.array([0.,0.,grasp['gripper_tip_offset_m'],1.]); tip_depth=np.linalg.inv(tool_from_depth)@tip; tip_color=r@tip_depth[:3]+t
 def project_color(pt):
  return [(det['color_fx']*pt[0]/pt[2]+det['color_cx'])*(rgb.width-1)/(det['color_calibration_width']-1),(det['color_fy']*pt[1]/pt[2]+det['color_cy'])*(rgb.height-1)/(det['color_calibration_height']-1)]
 mesh_share=Path(get_package_share_directory('piper_description'))
 meshes=jaw_triangles_tool(root,positions,mesh_share,q['gripper_mm']/2000)
 overlay=image.copy(); projections={}
 for name,tri in meshes.items():
  try:
   pixels,mask=mesh_projection(tri,tool_from_depth,r,t,det,rgb.width,rgb.height)
   projections[name]={'pixel_bounds':[pixels.min(axis=(0,1)).tolist(),pixels.max(axis=(0,1)).tolist()],'in_frame_mask_pixels':int(np.count_nonzero(mask))}
   contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);cv2.drawContours(overlay,contours,-1,(255,255,0),1)
  except ValueError as e:projections[name]={'error':str(e)}
 centre=[rgb.width//2,rgb.height//2];cv2.drawMarker(overlay,tuple(centre),(0,255,0),cv2.MARKER_CROSS,12,1)
 pixel=project_color(tip_color)
 if 0<=pixel[0]<rgb.width and 0<=pixel[1]<rgb.height:cv2.circle(overlay,tuple(map(lambda v:int(round(v)),pixel)),4,(0,0,255),1)
 report['model']={'source':'Current installed launch/config and generated physical URDF, offline FK; no live dynamic TF claimed',
 'q_ros_rad':[positions[f'joint{i}'] for i in range(1,7)],'q_exact_pi_rad':[v*math.pi/180000 for v in q['q_mdeg']],
 'finger_positions_m':[positions['joint7'],positions['joint8']],'urdf_sha256':hashlib.sha256(urdf.encode()).hexdigest(),
 'gripper_base_transform':link['gripper_base'].tolist(),'tip_base_xyz_m':(link['gripper_base']@tip)[:3].tolist(),
 'tip_depth_xyz_m':tip_depth[:3].tolist(),'tip_color_xyz_m':tip_color.tolist(),'tip_rgb_pixel':pixel,'jaw_projection':projections,
 'installation_rotation_calibrated':mount['rotation_calibrated'],'task_sha256':hashlib.sha256(task_path.read_bytes()).hexdigest()}
 cv2.imwrite(str(out/'model_jaw_overlay.png'),overlay)
 (out/'rgb_feedback.json').write_text(json.dumps(rgb_rows,indent=2));(out/'sdk_samples.json').write_text(json.dumps(joint_rows,indent=2))
 encode=lambda v:v.decode('utf-8',errors='replace') if isinstance(v,bytes) else float(v)
 (out/'report.json').write_text(json.dumps(report,indent=2,default=encode));print(json.dumps(report,indent=2,default=encode),flush=True)
finally:
 node.destroy_node()
 if rclpy.ok():rclpy.shutdown()
 p.DisconnectPort()
