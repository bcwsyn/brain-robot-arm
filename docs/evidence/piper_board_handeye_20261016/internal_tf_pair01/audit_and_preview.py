"""Offline final scope/rollback/test audit plus a clearly labeled static depth plot."""
import copy,hashlib,json,os,subprocess,time
from pathlib import Path
import cv2,numpy as np,yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
PRIOR=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_mount_deploy01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runtime=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
canonical=REPO/'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'
installed=Path('/home/johnwick/piper_ws/install/brain_robot_ball_pick/share/brain_robot_ball_pick/config/cube_task_real.yaml')
active_cpp=Path('/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp')
canonical_cpp=REPO/'brain_robot_arm/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/src/ob_camera_node.cpp'
assert runtime.read_bytes()==canonical.read_bytes()==installed.read_bytes()
assert active_cpp.read_bytes()==canonical_cpp.read_bytes()
old=yaml.safe_load((ROOT/'cube_task_real.before.yaml').read_text());current=yaml.safe_load(runtime.read_text());expected=copy.deepcopy(old)
for k in ['translation_m','rotation_rpy_rad']:expected['piper_camera_mount_tf']['ros__parameters'][k]=current['piper_camera_mount_tf']['ros__parameters'][k]
assert expected==current
baseline=json.loads((PRIOR/'production_SHA_after.json').read_text())
after={p:sha(Path(p)) for p in baseline};changed=[p for p in baseline if baseline[p]!=after[p]]
assert changed==[str(runtime)]
before_cpp=(ROOT/'ob_camera_node.active.before.cpp').read_bytes()
assert before_cpp==(ROOT/'ob_camera_node.canonical.before.cpp').read_bytes()
git_before=subprocess.run(['git','show','e50224a:brain_robot_arm/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/src/ob_camera_node.cpp'],cwd=REPO,capture_output=True,check=True).stdout
assert git_before==before_cpp
assert sha(ROOT/'cube_task_real.before.yaml')==baseline[str(runtime)]
argv=['/usr/bin/python3','-m','pytest','-q','-p','no:cacheprovider',
 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_camera_mount_geometry.py',
 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_astra_internal_tf_geometry.py',
 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_readonly_feedback.py',
 'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/test_board_handeye_fit.py']
p=subprocess.run(argv,cwd=REPO,env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=45)
with (ROOT/'regression.txt').open('x') as f:f.write(p.stdout+p.stderr)
assert p.returncode==0,p.stdout+p.stderr
v=json.loads((ROOT/'live_mount_verification.json').read_text());e=json.loads((ROOT/'deployment_execution.json').read_text());preview=json.loads((ROOT/'execution.json').read_text())
oldfactory=json.loads((PRIOR/'factory.json').read_text())['get_camera_params']
factory=json.loads((ROOT/'factory.json').read_text())['get_camera_params']
assert factory==oldfactory,'Raw factory arrays changed'
sdk=json.loads((ROOT/'feedback.json').read_text())['actual_last_sample']
sample=json.loads((ROOT/'capture/observer.jsonl').read_text().splitlines()[0])
rgb=cv2.imread(sample['images']['rgb']['path']);depth=cv2.imread(sample['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
masked=np.ma.masked_where(depth==0,depth*.001);cmap=plt.get_cmap('turbo').copy();cmap.set_bad('black')
fig,axes=plt.subplots(1,2,figsize=(10,4))
axes[0].imshow(cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB));axes[0].set_title('Original RGB 320x240: board/fingers, no cube')
im=axes[1].imshow(masked,cmap=cmap,vmin=.15,vmax=1.0);axes[1].set_title('Native depth 640x400: black = missing')
fig.colorbar(im,ax=axes[1],label='meters, display only; original uint16 unchanged')
fig.tight_layout();fig.savefig(ROOT/'static_RGB_depth_preview.png',dpi=120);plt.close(fig)
for name,pth in [('ob_camera_node.deployed.cpp',active_cpp),('cube_task_real.deployed.yaml',runtime)]:
    with (ROOT/name).open('xb') as f:f.write(pth.read_bytes())
report={'baseline_commit':'e50224a','epoch':time.time(),'approval':'User agreed to paired internal TF/mount correction, offline and static only.',
 'production_changed_paths':changed,'production_SHA_before':baseline,'production_SHA_after':after,
 'only_two_mount_values_changed':True,'canonical_runtime_installed_mount_identical':True,
 'canonical_active_Astra_source_identical':True,'active_source':str(active_cpp),'active_source_SHA256':sha(active_cpp),
 'before_active_source_SHA256':hashlib.sha256(before_cpp).hexdigest(),
 'inactive_nested_clone_changed':False,'inactive_nested_clone_path':'/home/johnwick/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/src/ob_camera_node.cpp',
 'old_source_backup_matches_git_e50224a':True,'old_mount_backup_matches_e50224a':True,
 'binary_rollback_local_only':{'path':str(ROOT/'libastra_camera.before.so'),'SHA256':sha(ROOT/'libastra_camera.before.so'),'excluded_from_Git':True},
 'rollback_requires_source_binary_AND_mount_together':True,'active_rollback_cycle_performed':False,
 'factory_K_D_R_T_unchanged':True,'detector_unchanged':True,'approach_gates_TCP_limits_unchanged':True,
 'regression_argv':argv,'regression_rc':p.returncode,'regression_stdout':p.stdout,
 'same_archived_RGBD_pairs_verified':len(v['samples']),'live_verified':v['verified'],
 'maximum_errors':{k:{a:max(x['errors'][k][a] for x in v['samples']) for a in v['samples'][0]['errors'][k]} for k in v['samples'][0]['errors']},
 'max_real_depth_point_path_difference_m':max(pt['path_difference_m'] for x in v['samples'] for pt in x['real_depth_point_path_comparison']),
 'CAN_TX_before':e['can_before']['stats64']['tx']['packets'],'CAN_TX_after':e['can_after']['stats64']['tx']['packets'],
 'SDK_full_window_rc':preview['SDK_full_window_rc'],'SDK_original_static_slice':preview['original_static_slice'],
 'last_actual_feedback':sdk,'camera_elapsed_s':preview['camera_elapsed_s'],
 'all_owned_sources_exited':e['all_owned_sources_exited'] and preview['all_owned_sources_exited'],
 'motion_commands_sent':False,'grasp_completed':False,'physical_TCP_verified':False,
 'global_absolute_accuracy_verified':False,'current_view_cube_present':False,
 'static_preview':{'RGB_sha256':sha(Path(sample['images']['rgb']['path'])),'depth_sha256':sha(Path(sample['images']['depth']['path'])),
 'native_depth_valid_fraction':float((depth>0).mean()),'display_limits_m':[.15,1.0],'zero_depth_not_filled':True},
 'next':'P3 local TF/registration consistency passes. Need operator to return the purple cube into the current complete static field of view before read-only target validation/P4 preparation. No automatic motion.'}
assert report['CAN_TX_before']==report['CAN_TX_after']==42154
with (ROOT/'final_audit.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
with (ROOT/'production_SHA_after.json').open('x') as f:json.dump(after,f,indent=2)
print(json.dumps({'tests':p.stdout,'live_verified':v['verified'],'motion_commands_sent':False,'all_sources_exited':report['all_owned_sources_exited']}))
