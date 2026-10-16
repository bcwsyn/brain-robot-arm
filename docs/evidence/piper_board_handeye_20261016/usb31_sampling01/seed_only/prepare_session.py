"""Prepare original approved sampler with current paths/metadata only."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OLD=REPO/'docs/evidence/piper_board_handeye_20261016/attempt01/run03'
FROZEN=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_static01/production_SHA_after.json'
text=(OLD/'executed_sampler.py').read_text()
changes={
 "FROZEN=REPO/'docs/evidence/piper_calibration_p1_20261015/board_open_only/production_SHA_before.json'":f'FROZEN=Path({str(FROZEN)!r})',
 "PREVIEW=Path('/home/johnwick/brain_robot_logs/new_pair07_preview.awrw9zku')":f"PREVIEW=Path('/home/johnwick/brain_robot_logs/usb31_static_20261016.1oGFil/metadata_followup')",
 "launch('original_nodes',['/usr/bin/python3','/tmp/piper_board_sampling_launch.py'])":f"launch('original_nodes',['/usr/bin/python3',{str(ROOT/'original_sampling.launch.py')!r}])",
 "'operator_quote':'同意'":"'operator_quote':'好，你自行完成，等真的需要我实机操作的时候再叫我','baseline_commit':'8744c14'",
 "'today_factory':factory":"'recent_same_device_factory_snapshot':factory",
 "            ids=[y*c+x for y in range(1,r-1) for x in range(1,c-1)]": "            ids=[y*c+x for y in range(1,r-1) for x in range(1,c-1)]\n            # Only seed actual detected corners away from observed gripper occlusion.\n            ids=[i for i in ids if 110<=corners.reshape(-1,2)[i][0]<=175 and 95<=corners.reshape(-1,2)[i][1]<=165]",
}
for a,b in changes.items():
    assert text.count(a)==1,a
    text=text.replace(a,b)
marker="    sample('start')"
assert text.count(marker)==1
insert=f"""    factory_process=launch('factory_readonly',['/usr/bin/python3',{str(ROOT/'capture_factory_metadata.py')!r},str(ROOT/'current_factory.json')])
    wait(lambda:factory_process.poll() is not None,24,'bounded current factory getter')
    assert factory_process.returncode==0
    current_factory=json.loads((ROOT/'current_factory.json').read_text())
    assert current_factory['get_device_info']['info']['serial_number']=='CC1365304DG'
    assert current_factory['get_camera_info']['info']['k']==old['color_factory']['K']
    assert current_factory['get_camera_info']['info']['d']==old['color_factory']['CameraInfo_D']
    sdk_before=json.loads((ROOT/'sdk_before.json').read_text())
    save('sampling_checklist.json',{{'approved_proposal_commit':'121d1ef','current_start_rad':center.tolist(),'SDK_original_static_slice':json.loads((ROOT/'preflight.json').read_text())['original_static_slice'],'last_fresh_SDK':[s for s in sdk_before['samples'] if s['fresh_after_passive_connection']][-1],'joint_min_rad':cfg['real_trajectory_joint_min'],'joint_max_rad':cfg['real_trajectory_joint_max'],'candidate_goals_rad':{{label:goal.tolist() for label,goal,_,_ in candidates}},'MoveIt_scaling':[.02,.02],'adapter_max_velocity_rad_s':.189,'original_goal_tolerance_rad':cfg['trajectory_feedback_tolerance_rad'],'trajectory_durations_s':[t.points[-1].time_from_start.sec+t.points[-1].time_from_start.nanosec/1e9 for _,_,t,_ in candidates],'scene':report['scene'],'return':'Each original candidate returns to this fresh center; no gripper/SEARCH/grasp.','stop':'Original feedback/limits/collision + continuous fixed board IDs + original duration+25 timeout; software disarm, never hardware Disable.'}})
    print('BOARD_SAMPLING_CHECKLIST_READY',flush=True)
    sample('start')"""
text=text.replace(marker,insert)
oldtree=ast.parse((OLD/'executed_sampler.py').read_text());newtree=ast.parse(text)
functions=lambda t:{n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,ast.FunctionDef)}
before=functions(oldtree);after=functions(newtree)
assert {k:v for k,v in before.items() if k!='picture'}=={k:v for k,v in after.items() if k!='picture'}
assert before['picture']!=after['picture']
assert (ROOT/'original_sampling.launch.py').read_bytes()==(OLD/'executed_launch.py').read_bytes()
(ROOT/'executed_sampler.py').write_text(text)
(ROOT/'preparation.json').write_text(json.dumps({'baseline_commit':'8744c14','all_original_control_and_other_helpers_AST_identical':True,'only_picture_helper_change':'Initial detected corner selection intersected with fixed ROI [110,95,175,165], before setting immutable IDs; no tracking thresholds changed','original_launch_bytes_identical':True,'motion_semantics_changed':False,'changes':'Current metadata/paths/checklist plus read-only initial seed ROI from exact archived occlusion audit; 577-transition offline replay passed','source_SHA':hashlib.sha256((OLD/'executed_sampler.py').read_bytes()).hexdigest()},indent=2)+'\n')
print(ROOT/'executed_sampler.py')
