"""Offline scope, rollback, regression and package audit. No hardware imports."""
import ast,copy,hashlib,json,os,subprocess,time
from pathlib import Path
import numpy as np,yaml
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
DATA=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01'
RUNTIME=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
CANONICAL=REPO/'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'
INSTALLED=Path('/home/johnwick/piper_ws/install/brain_robot_ball_pick/share/brain_robot_ball_pick/config/cube_task_real.yaml')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((DATA/'production_SHA_after.json').read_text())
after={p:sha(Path(p)) for p in baseline}
before=yaml.safe_load((ROOT/'cube_task_real.runtime.before.yaml').read_text())
current=yaml.safe_load(RUNTIME.read_text())
expected=copy.deepcopy(before)
for key in ['translation_m','rotation_rpy_rad','rotation_calibrated']:
    expected['piper_camera_mount_tf']['ros__parameters'][key]=current['piper_camera_mount_tf']['ros__parameters'][key]
assert expected==current,'Out-of-scope configuration key changed'
assert RUNTIME.read_bytes()==CANONICAL.read_bytes()==INSTALLED.read_bytes()
assert INSTALLED.resolve()==RUNTIME
assert sha(ROOT/'cube_task_real.runtime.before.yaml')==baseline[str(RUNTIME)]
assert (ROOT/'cube_task_real.runtime.before.yaml').read_bytes()==(ROOT/'cube_task_real.canonical.before.yaml').read_bytes()
head=subprocess.run(['git','show','b7cbce0:brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml'],cwd=REPO,capture_output=True,check=True).stdout
assert head==(ROOT/'cube_task_real.runtime.before.yaml').read_bytes()
changed=[p for p in baseline if after[p]!=baseline[p]]
assert changed==[str(RUNTIME)],changed
for p in ROOT.glob('*.py'):ast.parse(p.read_text())
argv=['/usr/bin/python3','-m','pytest','-q','-p','no:cacheprovider',
    'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_camera_mount_geometry.py',
    'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_readonly_feedback.py',
    str(DATA/'full_ROI/test_board_handeye_fit.py')]
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
test=subprocess.run(argv,cwd=REPO,env=env,capture_output=True,text=True,timeout=45)
(ROOT/'regression.log').write_text(test.stdout+test.stderr)
assert test.returncode==0,test.stdout+test.stderr
execution=json.loads((ROOT/'deployment_execution.json').read_text())
verify=json.loads((ROOT/'live_mount_verification.json').read_text())
preview=json.loads((ROOT/'execution.json').read_text())
review=json.loads((ROOT/'live_composition_review.json').read_text())
X=np.array(review['approved_T_gripperBase_colorOptical_unchanged'])
CD=np.array(review['detector_registration_vs_actual_TF']['configured_D_to_C'])
LD=np.array(review['live_T_cameraLink_depthOptical'])
# Unapplied paired correction proposal: only meaningful if internal TF is
# also reconciled with the image-supported factory registration.
corrected_LC=LD@np.linalg.inv(CD)
proposed_GL=X@np.linalg.inv(corrected_LC)
proposal={'applied':False,'requires_explicit_scope_approval':True,
    'do_not_deploy_mount_alone':True,'actual_color_X_must_remain_approved':X.tolist(),
    'image_supported_T_color_depth':CD.tolist(),
    'paired_internal_T_cameraLink_colorOptical_proposal':corrected_LC.tolist(),
    'paired_T_gripperBase_cameraLink_proposal':proposed_GL.tolist(),
    'mount_values_if_and_only_if_internal_TF_is_corrected':{
        'translation_m':proposed_GL[:3,3].tolist(),
        'rotation_rpy_rad':Rotation.from_matrix(proposed_GL[:3,:3]).as_euler('xyz').tolist()},
    'recomposed_color_X_max_abs_error':float(np.max(np.abs(proposed_GL@corrected_LC-X))),
    'scope_note':'Read-only proposal, not permission to change Astra, detector, approach or run a grasp.'}
with (ROOT/'internal_registration_followup_proposal.json').open('x') as f:json.dump(proposal,f,indent=2,allow_nan=False)
report={'baseline_commit':'b7cbce0','epoch':time.time(),'allowed_configuration_keys':[
    'piper_camera_mount_tf.ros__parameters.'+k for k in ['translation_m','rotation_rpy_rad','rotation_calibrated']],
    'only_allowed_keys_changed':True,'production_changed_paths':changed,
    'production_SHA_before':baseline,'production_SHA_after':after,
    'canonical_runtime_installed_bytes_identical':True,'installed_symlink_target':str(INSTALLED.resolve()),
    'rollback_backup_matches_git_b7cbce0':True,'rollback_SHA256':sha(ROOT/'cube_task_real.runtime.before.yaml'),
    'rollback_not_executed_on_active_configuration':True,'binary_build_required':False,
    'build_reason':'YAML-only production change; installed launch consumes a symlink to the verified source.',
    'regression_argv':argv,'regression_rc':test.returncode,'regression_stdout':test.stdout,
    'live_color_mount_verified':verify['verified'],'exact_image_stamp_samples':len(verify['samples']),
    'max_color_X_translation_error_m':max(r['X_error']['translation_m'] for r in verify['samples']),
    'max_color_X_rotation_error_deg':max(r['X_error']['rotation_deg'] for r in verify['samples']),
    'CAN_TX_before':execution['can_before']['stats64']['tx']['packets'],
    'CAN_TX_after':execution['can_after']['stats64']['tx']['packets'],
    'SDK_full_window_rc':preview['SDK_full_window_rc'],
    'SDK_original_static_slice':preview['original_static_slice'],
    'all_owned_sources_exited':execution['all_owned_sources_exited'] and preview['all_owned_sources_exited'],
    'full_RGBD_robot_geometry_validated':False,'grasp_completed':False,
    'remaining_issue':'Image-supported detector D->C and observed internal camera TF disagree by 59.65mm; do not start depth-driven grasp on this inconsistent chain.',
    'internal_TF_or_detector_changed':False}
assert report['CAN_TX_before']==report['CAN_TX_after']==42154
with (ROOT/'deployment_audit.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
with (ROOT/'production_SHA_after.json').open('x') as f:json.dump(after,f,indent=2)
print(json.dumps({k:report[k] for k in ['only_allowed_keys_changed','regression_stdout','live_color_mount_verified','CAN_TX_before','CAN_TX_after','all_owned_sources_exited','full_RGBD_robot_geometry_validated']},indent=2))
