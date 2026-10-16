"""Approved TF-only build; preserve local binary rollback, never run hardware."""
import hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
test=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_astra_internal_tf_geometry.py'
spec=importlib.util.spec_from_file_location('tf_math',test);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
factory=json.loads(module.FACTORY.read_text())['get_camera_params']
(ROOT/'compiled_math').mkdir()
LC,raw=module.compile_tf_math(ROOT/'compiled_math',factory['r2l_r'],factory['r2l_t'])
X=np.array(json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
GL=X@np.linalg.inv(LC)
predicted={'approved_X_G_color_unchanged':X.tolist(),'predicted_actual_T_link_color':LC.tolist(),
 'compiled_prefix_output_link_colorFrame_XYZ_quat':raw,'paired_mount':{
 'translation_m':GL[:3,3].tolist(),'rotation_rpy_rad':Rotation.from_matrix(GL[:3,:3]).as_euler('xyz').tolist()},
 'recomposed_X_max_abs_difference':float(np.max(np.abs(GL@LC-X))),
 'factory_translation_mm_unchanged':factory['r2l_t'],'method':'Compile actual source prefix and original Eigen/TF2 helper, then compose unchanged colorFrame<-colorOptical edge'}
with (ROOT/'paired_mount_prediction.json').open('x') as f:json.dump(predicted,f,indent=2,allow_nan=False)
binary=Path('/home/johnwick/ros2_ws/build/astra_camera/libastra_camera.so')
report={'epoch':time.time(),'argv':['cmake','--build','/home/johnwick/ros2_ws/build/astra_camera','--target','astra_camera','-j2'],
 'cwd':'/home/johnwick/ros2_ws','motion_commands_sent':False,'hardware_opened':False,
 'binary_before_SHA256':hashlib.sha256(binary.read_bytes()).hexdigest()}
with (ROOT/'build.txt').open('x') as f:
    p=subprocess.run(report['argv'],cwd=report['cwd'],stdout=f,stderr=subprocess.STDOUT,timeout=240)
report['rc']=p.returncode;report['end_epoch']=time.time();report['binary_after_SHA256']=hashlib.sha256(binary.read_bytes()).hexdigest()
report['installed_binary_resolves_to']=str(Path('/home/johnwick/ros2_ws/install/astra_camera/lib/libastra_camera.so').resolve())
with (ROOT/'build.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps({'prediction':predicted['paired_mount'],'build':report},indent=2))
raise SystemExit(p.returncode)
