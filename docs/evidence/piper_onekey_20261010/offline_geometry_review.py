import json,math,xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
import yaml
from pathlib import Path
cfg=yaml.safe_load(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml').read_text())
p=cfg['grasp_lift_executor']['ros__parameters'];lo=np.array(p['real_trajectory_joint_min']);hi=np.array(p['real_trajectory_joint_max'])
root=ET.parse('/home/johnwick/piper_ros/install/piper_description/share/piper_description/urdf/piper_description.urdf').getroot()
chain=[]
for i in range(1,7):
 j=root.find(f"joint[@name='joint{i}']"); o=j.find('origin');t=np.eye(4)
 t[:3,3]=np.fromstring(o.get('xyz','0 0 0'),sep=' ')
 t[:3,:3]=Rotation.from_euler('xyz',np.fromstring(o.get('rpy','0 0 0'),sep=' ')).as_matrix()
 axis=np.fromstring(j.find('axis').get('xyz'),sep=' ');chain.append((t,axis))
def fk(q):
 t=np.eye(4)
 for qi,(origin,axis)in zip(q,chain):
  a=np.eye(4);a[:3,:3]=Rotation.from_rotvec(qi*axis).as_matrix();t=t@origin@a
 return t
rows=[json.loads(l) for l in Path('/tmp/piper_onekey_test_20261010_observer.jsonl').read_text().splitlines() if l.startswith('{')]
row=next(r for r in rows if 'snapshot'in r and r['latest'].get('/brain_robot_visual_control/state')=='GRASP_READY')
q=np.array([row['latest']['/joint_states']['positions'][f'joint{i}'] for i in range(1,7)])
# Reconstruct target with the deployed rigid camera mount and Astra optical transform.
mount=cfg['piper_camera_mount_tf']['ros__parameters'];m=np.eye(4);m[:3,3]=mount['translation_m'];m[:3,:3]=Rotation.from_euler('xyz',mount['rotation_rpy_rad']).as_matrix()
opt=np.eye(4);opt[:3,:3]=Rotation.from_euler('xyz',[-math.pi/2,0,-math.pi/2]).as_matrix()
point=row['latest']['/brain_robot_vision/target_point_camera']['xyz'];ob=(fk(q)@m@opt@np.r_[point,1])[:3]
print(json.dumps({'review':'OFFLINE_MODEL_ONLY_NO_CONTROL','sample_epoch':row['epoch'],'q_rad':q.tolist(),'target_base_from_sample':ob.tolist(),'tool_z_base':fk(q)[:3,2].tolist()}),flush=True)
# Use the execution log's rounded locked point for matching the 24 exact-pose tests.
ob=np.array([.432,-.127,.081]);rng=np.random.default_rng(10)
seeds=[q]+[rng.uniform(lo+.001,hi-.001) for _ in range(3)]
def solve(r,pos):
 def error(x):
  f=fk(x);return np.r_[f[:3,3]-pos,.15*Rotation.from_matrix(r.T@f[:3,:3]).as_rotvec()]
 best=None
 for seed in seeds:
  s=least_squares(error,seed,bounds=(lo+.00001,hi-.00001),max_nfev=120,ftol=1e-9,xtol=1e-9,gtol=1e-9)
  f=fk(s.x);pe=np.linalg.norm(f[:3,3]-pos);re=Rotation.from_matrix(r.T@f[:3,:3]).magnitude()
  b={'q':s.x.tolist(),'position_error_m':float(pe),'orientation_error_rad':float(re),'reachable':bool(pe<.001 and re<.01)}
  if best is None or np.linalg.norm(error(s.x))<best[0]:best=(np.linalg.norm(error(s.x)),b)
  if b['reachable']:return b
 return best[1]
for tilt in p['top_down_tilt_candidates']:
 for yaw in p['top_down_yaw_candidates']:
  r=Rotation.from_euler('xyz',[0,math.pi-tilt,yaw]).as_matrix();pos=ob-r[:,2]*(p['gripper_tip_offset_m']+p['top_down_pregrasp_clearance_m'])
  print(json.dumps({'candidate':'top_down','tilt':tilt,'yaw':yaw,**solve(r,pos)}),flush=True)
r=fk(q)[:3,:3];pos=ob-r[:,2]*(p['gripper_tip_offset_m']+p['top_down_pregrasp_clearance_m'])
print(json.dumps({'candidate':'measured_orientation_diagnostic_only',**solve(r,pos)}),flush=True)
