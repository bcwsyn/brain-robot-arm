"""Project the ORIGINAL installed jaw meshes with current X; no calibration fit."""
import json,sys
from pathlib import Path
import cv2,numpy as np
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import load_installed_model
from review_jaw_scene import jaw_triangles_tool
from review_depth_registration import read_config,calibration
from ament_index_python.packages import get_package_share_directory
urdf,_=load_installed_model();model=ET.fromstring(urdf)
X=np.array(json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
camera=np.linalg.inv(X)
p=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
cam=calibration(p);K=np.diag([319/639,239/479,1.])@cam['k']
row=json.loads((ROOT/'capture/observer.jsonl').read_text().splitlines()[0])
positions={f'joint{i}':v for i,v in enumerate(row['q_rad'],1)}
triangles=jaw_triangles_tool(model,positions,Path(get_package_share_directory('piper_description')),.0002)
im=cv2.imread(row['images']['rgb']['path']);canvas=cv2.resize(im,(640,480),interpolation=cv2.INTER_NEAREST)
report={'read_only':True,'installed_original_meshes':True,'current_opening_m':.0004,
        'original_production_nominal_tip_m':[0,0,.1358],'model_overlay_NOT_ground_truth':True,'jaws':{}}
for i,(name,t) in enumerate(triangles.items()):
    verts=t.reshape(-1,3);pc=verts@camera[:3,:3].T+camera[:3,3]
    uv=pc@K.T;uv=uv[:,:2]/uv[:,2,None]
    zmax=verts[:,2].max();tip=verts[verts[:,2]>=zmax-.0005].mean(axis=0)
    tipc=camera@np.r_[tip,1.];tipuv=K@tipc[:3];tipuv=tipuv[:2]/tipuv[2]
    report['jaws'][name]={'bounds_tool_m':[verts.min(axis=0).tolist(),verts.max(axis=0).tolist()],
        'free_end_zmax_band_mean_tool_m':tip.tolist(),'free_end_projection_px':tipuv.tolist(),
        'visible_vertices':int((pc[:,2]>.001).sum())}
    color=(255,255,0) if i==0 else (0,165,255)
    projected=uv.reshape(-1,3,2)
    z=pc[:,2].reshape(-1,3)
    for tri,depth in zip(projected,z):
        if np.all(depth>.001) and np.max(np.abs(tri))<5000:
            cv2.polylines(canvas,[np.rint(tri*2).astype(np.int32)],True,color,1)
    cv2.drawMarker(canvas,tuple(np.rint(tipuv*2).astype(int)),color,cv2.MARKER_CROSS,18,2)
cv2.putText(canvas,'ORIGINAL CAD + approved X; no fitted correction',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
dest=ROOT/'geometry_review';assert cv2.imwrite(str(dest/'current_original_jaw_mesh_overlay.png'),canvas)
with (dest/'jaw_mesh_report.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps(report,indent=2))
