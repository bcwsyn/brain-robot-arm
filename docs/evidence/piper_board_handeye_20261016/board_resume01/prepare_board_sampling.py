"""Reuse approved original 9fit+1heldout sampling after actual observe return."""
from pathlib import Path
import ast
import json
import shutil

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
observe = ROOT/'observe_reuse_baseline'
execution = json.loads((observe/'execution_session.json').read_text())
assert execution['observe_reached'] and execution['error'] is None and execution['all_owned_sources_exited']
sample = ROOT/'board_sampling'
sample.mkdir(exist_ok=False)
old = REPO/'docs/evidence/piper_board_handeye_20261016/attempt01/run03'
shutil.copyfile(old/'executed_launch.py', sample/'original_sampling.launch.py')
text = (old/'executed_sampler.py').read_text()
frozen_old = "FROZEN=REPO/'docs/evidence/piper_calibration_p1_20261015/board_open_only/production_SHA_before.json'"
assert text.count(frozen_old) == 1
text = text.replace(frozen_old, f'FROZEN=Path({str(ROOT/"approved_baseline.json")!r})')
launch_old = "launch('original_nodes',['/usr/bin/python3','/tmp/piper_board_sampling_launch.py'])"
assert text.count(launch_old) == 1
text = text.replace(launch_old, f"launch('original_nodes',['/usr/bin/python3',{str(sample/'original_sampling.launch.py')!r}])")
text = text.replace("'today_factory':factory", "'reused_same_camera_factory_snapshot_not_new_query':factory")
marker = "    sample('start')"
addition = f"""    factory_process=launch('factory_readonly',['/usr/bin/python3','/home/johnwick/brain_robot_logs/calibration_stage1_activated_20261014.kfNDAQ/capture_factory_metadata.py',str(ROOT/'current_factory.json')])
    wait(lambda:factory_process.poll() is not None,15,'bounded current read-only factory verification')
    assert factory_process.returncode==0
    current_factory=json.loads((ROOT/'current_factory.json').read_text())
    assert current_factory['get_device_info']['info']['serial_number']=='CC1365304DG'
    save('current_camera_identity_verified.json',{{'serial_number':'CC1365304DG','read_epoch':current_factory['read_epoch'],'pose_K_D_still_approved_unchanged_baseline':True,'mount_TF_unchanged':True}})
    recorded=json.loads(Path({str(observe/'sdk_at_observation.json')!r}).read_text())
    last_SDK=[s for s in recorded['samples'] if s['fresh_after_passive_connection']][-1]
    checklist={{'recorded_SDK_source':{str(observe/'sdk_at_observation.json')!r},'last_SDK_high_stamp':last_SDK['sdk_receipt_stamps']['high'],'last_SDK_high_Hz':last_SDK['high_hz'],'last_SDK_enabled':last_SDK['enabled'],'current_fresh_driver_start_rad':center.tolist(),'goal_q_rad':{{label:goal.tolist() for label,goal,_,_ in candidates}},'joint_min':cfg['real_trajectory_joint_min'],'joint_max':cfg['real_trajectory_joint_max'],'MoveIt_velocity_acceleration_scaling':[.02,.02],'original_adapter_max_velocity_rad_s':.189,'path_durations_s':[t.points[-1].time_from_start.sec+t.points[-1].time_from_start.nanosec/1e9 for _,_,t,_ in candidates],'stop':'Original feedback/limits/collision + continuous fixed board IDs + duration+25 timeout; software disarm, no hardware disable.','return':'Each bounded pose returns to this session measured center; no gripper/SEARCH/grasp/TF deployment.'}}
    save('sampling_checklist.json',checklist);print('BOARD_SAMPLING_CHECKLIST',json.dumps(checklist),flush=True)
    sample('start')"""
assert text.count(marker) == 1
text = text.replace(marker, addition)
ast.parse(text)
(sample/'executed_sampler.py').write_text(text)
print(sample/'executed_sampler.py')
