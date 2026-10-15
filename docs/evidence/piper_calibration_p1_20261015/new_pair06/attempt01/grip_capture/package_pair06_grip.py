"""Offline only: archive B RGB/SDK, exact installed FK and takeover diagnosis."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import cv2
import numpy as np
import yaml

REPO=Path('/mnt/hgfs/ub');BASE=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
FAIL=BASE/'new_pair06_grip.VMWSMu';CHECK=BASE/'new_pair06_B_passive_check.lYAGoP';RGB=BASE/'new_pair06_B_RGB_only.U8xDq1'
OUT=BASE/'new_pair06_grip_publish';TEST=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TEST))
from collect_calibration_sdk import summarize
from export_calibration_bundle import load_installed_model,base_tool_fk,sdk_review,verify_bundle

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False);portable=OUT/'portable';portable.mkdir();(portable/'images').mkdir()
packet=load(CHECK/'sdk.json');samples=packet['samples'];slices=[]
for i in range(len(samples)):
 for j in range(i+30,len(samples)+1):
    part=samples[i:j]
    if all(r['fresh_after_passive_connection'] for r in part):
        quality=summarize(part)
        if quality['static_three_seconds_and_thirty_samples']:slices.append({'slice':[i,j],'quality':quality})
assert slices,'No original SDK static window; raw B must not be promoted'
accepted=max(slices,key=lambda s:s['slice'][1]-s['slice'][0]);last=load(RGB/'feedback.json')['actual_last_sample'];q=last['q_driver_rad']
assert np.allclose(q,samples[accepted['slice'][0]]['q_driver_rad'],rtol=0,atol=1e-12)
rows=[json.loads(line) for line in (RGB/'capture/frames.jsonl').read_text().splitlines()]
all_rgb=[r for r in rows if r['kind']=='rgb'];valid=[];rejected=[]
for row in all_rgb:
    fb=row.get('latest_feedback_not_image_time');reason=None
    if fb is None:reason='no source feedback'
    else:
        span=abs(row['stamp_ns']-fb['stamp_ns'])/1e9
        age=row['epoch']-min(row['stamp_ns'],fb['stamp_ns'])/1e9
        values=[fb['positions'].get(f'joint{i}') for i in range(1,7)]
        if any(v is None for v in values) or not np.isfinite(values).all():reason='invalid actual q'
        elif span>.12 or age<0 or age>.5:reason='original 120ms/500ms timestamp bounds'
        elif not np.allclose(values,q,rtol=0,atol=.001):reason='actual q changed from SDK static window'
    (rejected if reason else valid).append({'source':row,'reason':reason} if reason else row)
assert len(valid)>=5,'Need five actual fresh B RGB images'
urdf,task_path=load_installed_model();root=ET.fromstring(urdf);task=yaml.safe_load(task_path.read_text())
(portable/'actual_runtime_model.urdf').write_text(urdf)
shutil.copyfile(CHECK/'sdk.json',portable/'sdk_samples.json')
put(portable/'sdk_review.json',sdk_review(packet,root))
shutil.copyfile(FAIL/'factory.json',portable/'camera_factory_from_B_initial_session.json')
shutil.copyfile(task_path,portable/'robot_task_config_snapshot.yaml')
frames=[]
for index in np.linspace(0,len(valid)-1,5,dtype=int):
    row=valid[int(index)];src=Path(row['path']);dst=portable/'images'/src.name
    shutil.copyfile(src,dst);pixels=cv2.imread(str(dst));assert pixels.shape==(240,320,3)
    fb=row['latest_feedback_not_image_time'];values=[fb['positions'][f'joint{i}'] for i in range(1,7)]
    frames.append({'source_frame_index':int(index),'rgb_stamp_ns':str(row['stamp_ns']),
                   'feedback_stamp_ns':str(fb['stamp_ns']),'receipt_epoch':row['epoch'],
                   'span_s':abs(row['stamp_ns']-fb['stamp_ns'])/1e9,
                   'oldest_age_at_receive_s':row['epoch']-min(row['stamp_ns'],fb['stamp_ns'])/1e9,
                   'actual_q_driver_rad':values,'T_base_gripper_base':base_tool_fk(root,values),
                   'image':{'path':'images/'+src.name,'sha256':sha(dst),'size':[320,240]},
                   'configured_frame':'camera_color_optical_frame',
                   'frame_provenance':'cam2image arguments; legacy raw recorder does not retain per-image header frame/encoding',
                   'not_hardware_synchronized':True,'depth_required_for_B':False})
put(portable/'frames.json',{'capture_role':'grip_B_RGB_only','raw_RGB_frames_total':len(all_rgb),'valid_timestamp_q_RGB_frames':len(valid),
                           'rejected_RGB_frames':rejected,'selected_actual_frames':frames,'selection':'five evenly spaced actual valid frames, no interpolation'})
put(portable/'static_window.json',{'SDK_source':'sdk_samples.json','full_original_quality':packet['quality'],
                                  'original_contiguous_window':accepted,'not_simultaneous_with_RGB':True,
                                  'same_actual_q_verified_again_in_RGB_and_last_feedback':True})
put(portable/'frame_and_calibration_provenance.json',{'factory_source':'First B-session official factory GET, not a new RGB-only GET; preserved raw replies',
      'depth_stream_started_in_RGB_session':False,'new_installation_TF_fitted':False,'camera_cube_center_m':None,
      'gripper_base_cube_center_m':None,'physical_contact_provenance':'Operator replied 已完成 to same-position grip request; SDK does not verify contact or calibrated force',
      'RGB_intrinsics_are_not_per_image_CameraInfo':True,'no_fake_depth_or_Info_generated':True})
manifest={'schema':'piper_grip_RGB_only_bundle_v1','pair_id':'new_pair06','capture_role':'grip_B','RGBD_bundle':False,
          'raw_images_modified':False,'SDK_original_static_window_verified':True,'physical_contact_user_confirmed':True,
          'physical_contact_independently_verified':False,'complete_calibration_pair':False,
          'camera_cube_center_m':None,'gripper_base_cube_center_m':None,
          'files':[{'path':p.relative_to(portable).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(portable.rglob('*')) if p.is_file()]}
put(portable/'manifest.json',manifest);verify_bundle(portable,manifest)

# Execute only the original pure clamp function, not the node or ROS callbacks.
adapter=TEST.parent/'scripts/piper_jog_adapter.py';tree=ast.parse(adapter.read_text())
fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_limit_visual_target')
namespace={};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(adapter),'exec'),namespace)
launch=task_path.parent.parent/'launch/cube_visual_search.launch.py';launch_tree=ast.parse(launch.read_text())
deltas=next(ast.literal_eval(v) for n in ast.walk(launch_tree) if isinstance(n,ast.Dict)
            for k,v in zip(n.keys,n.values) if isinstance(k,ast.Constant) and k.value=='visual_joint_max_delta_rad')
grasp=task['grasp_lift_executor']['ros__parameters'];names=[f'joint{i}' for i in range(1,7)]
fake=SimpleNamespace(visual_baseline=dict(zip(names,q)),positions=dict(zip(names,q)),visual_joint_max_delta=deltas,
                     joint_min=grasp['real_trajectory_joint_min'],joint_max=grasp['real_trajectory_joint_max'])
clamped=[namespace['_limit_visual_target'](fake,i,name,q[i]) for i,name in enumerate(names)]
assert abs(clamped[2]-(-1.4))<1e-12 and clamped[2]>q[2]
put(OUT/'takeover_audit.json',{'offline_only':True,'physical_arm_service_called':False,'actual_q':q,
                             'joint_min':fake.joint_min,'joint_max':fake.joint_max,'visual_delta':deltas,
                             'original_stationary_armed_no_trajectory_tick_targets':clamped,
                             'predicted_J3_jump_rad':clamped[2]-q[2],'predicted_J3_jump_deg':float(np.degrees(clamped[2]-q[2])),
                             'not_a_hardware_limit_diagnosis':True,'do_not_repeat_live_arm':True,
                             'adapter_source_sha256':sha(adapter),'effective_launch_sha256':sha(launch),'task_sha256':sha(task_path)})

archive_files=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as archive:
 for label,folder in [('RGBD_initial_incomplete',FAIL),('camera_off_static_check',CHECK),('RGB_only_complete',RGB)]:
    for p in sorted(folder.rglob('*')):
        if not p.is_file():continue
        name=label+'/'+p.relative_to(folder).as_posix();archive.add(p,arcname=name,recursive=False)
        archive_files.append({'path':name,'sha256':sha(p),'bytes':p.stat().st_size})
with tarfile.open(OUT/'runtime_closed.tar.gz') as archive:
 for item in archive_files:assert hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'files':archive_files,'all_SHA_verified':True})
for source,label in [(FAIL,'initial'),(RGB,'RGB_only')]:
    before,after=load(source/'source_SHA_before.json'),load(source/'source_SHA_after.json')
    assert before==after and all(sha(Path(p))==v for p,v in before.items())
    assert load(source/'execution.json')['all_owned_sources_exited']
    assert load(source/'can_before.json')['before']['tx']==load(source/'can_after.json')['tx']
assert load(CHECK/'check.json')['before']['tx']==load(CHECK/'check.json')['after']['tx']
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'expected':v['expected'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
assessment={'pair_id':'new_pair06','grip_capture_complete':True,'complete_pair':False,'formal_A_frames':0,
            'operator_same_position_and_contact_confirmed':True,'operator_quote':'已完成',
            'independent_contact_or_force_verified':False,'gripper_mm':last['gripper_mm'],'q_mdeg':last['q_mdeg'],
            'actual_q_driver_rad':q,'last_fresh_feedback':last,'T_base_gripper_base':base_tool_fk(root,q),
            'raw_RGB_frames':len(all_rgb),'fresh_actual_q_RGB_frames':len(valid),'selected_RGB_frames':5,
            'selected_frame_span_s':(int(frames[-1]['rgb_stamp_ns'])-int(frames[0]['rgb_stamp_ns']))/1e9,
            'SDK_full_window_quality_preserved':packet['quality'],'accepted_original_SDK_window':accepted,
            'RGB_actual_q_spread_rad':np.ptp(np.array([[r['latest_feedback_not_image_time']['positions'][f'joint{i}'] for i in range(1,7)] for r in valid]),axis=0).tolist(),
            'camera_cube_center_m':None,'gripper_base_cube_center_m':None,'model_sha256':hashlib.sha256(urdf.encode()).hexdigest(),
            'first_RGBD_attempt_complete':False,'RGBD_missing_not_relabelled_as_success':True,
            'source_runtime_root':str(RGB),'production_SHA':production,'new_CAN_TX':0,
            'all_sources_exited':True,'no_enable_disable_open_motion':True,'no_new_return_authorization':True,
            'future_motion_blocker':'Actual J3 -1.551364696 rad is below existing -1.4 task bound. Original arm/tick would clamp by +0.151364696 rad; offline reproduced only. Do not repeat live or expand limits/alter production unapproved.'}
put(OUT/'assessment.json',assessment)
put(OUT/'verification.json',{'tests_passed':75,'archive_files_SHA_verified':len(archive_files),
                            'portable_assets_SHA_verified':len(manifest['files']),'raw_RGB_frames':len(all_rgb),
                            'selected_fresh_RGB_frames':5,'original_static_window_verified':True,
                            'original_clamp_offline_reproduced':True,'production_five_SHA_unchanged':True,
                            'complete_formal_pairs_unchanged':1,'new_CAN_TX':0,'GitHub_pushed':False})
print(json.dumps({'archive_files':len(archive_files),'assets':len(manifest['files']),'raw_RGB':len(all_rgb),
                  'selected_RGB':5,'static_window':accepted,'q_mdeg':last['q_mdeg'],'gripper_mm':last['gripper_mm'],
                  'takeover_J3_predicted_jump_deg':float(np.degrees(clamped[2]-q[2]))}),flush=True)
