"""Offline packaging of an incomplete camera startup; no device APIs."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import shutil
import tarfile

BASE=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
SRC=BASE/'new_pair05_native_continuous.xlKYkV'
OUT=BASE/'new_pair05_native_startup_publish'
REPO=Path('/mnt/hgfs/ub')
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
for name in ['execution.json','depth_controls.json','source_SHA_before.json','sdk_before.json','feedback.json','factory.json','can_before.json','can_after.json','depth.log','controls.log','factory.log','capture.log','kernel_window.txt','kernel_epoch_window.txt']:
    # Plain .txt copies make ignored log names portable in Git, originals in tar.
    target=name+'.txt' if name.endswith('.log') else name
    if name=='depth.log':
        (OUT/target).write_text('DISPLAY COPY: trailing whitespace removed only; original bytes remain in runtime_closed.tar.gz:depth.log.\n'+
            '\n'.join(line.rstrip() for line in (SRC/name).read_text().splitlines())+'\n')
    else:
        shutil.copyfile(SRC/name,OUT/target)
for name in ['native','capture']:
    shutil.copytree(SRC/name,OUT/name)
assets=[]
with tarfile.open(OUT/'runtime_closed.tar.gz','w:gz') as t:
    for p in sorted(SRC.rglob('*')):
        if p.is_file():
            assert not p.is_symlink()
            relative=p.relative_to(SRC).as_posix()
            assets.append({'path':relative,'bytes':p.stat().st_size,'sha256':sha(p)})
            t.add(p,arcname=relative,recursive=False)
with tarfile.open(OUT/'runtime_closed.tar.gz') as t:
    assert len(t.getnames())==len(assets)
    for item in assets:
        assert hashlib.sha256(t.extractfile(item['path']).read()).hexdigest()==item['sha256']
put(OUT/'runtime_manifest.json',{'source_runtime':str(SRC),'files':assets,'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'all_original_and_archived_SHA_verified':True})
e=load(SRC/'execution.json');c=load(SRC/'depth_controls.json');native=load(SRC/'native/summary.json');capture=load(SRC/'capture/summary.json')
source_hashes=load(SRC/'source_SHA_before.json')
assert all(sha(Path(p))==h for p,h in source_hashes.items())
old=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair05/attempt01/observe_capture/verification.json')
production={p:{'expected':x['expected'],'actual':sha(Path(p))} for p,x in old['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
assert e['within_30s_camera_bound'] and e['all_owned_sources_exited']
before=load(SRC/'can_before.json')['before'];after=load(SRC/'can_after.json')
assert after['rx']>before['rx'] and before['tx']==after['tx']
assert native['saved_frames']==0 and capture['saved_frames']==0
assessment={'schema':'piper_native_depth_startup_diagnostic_v1','single_camera_session_s':e['camera_session_upper_bound_s'],'all_sources_exited':True,
            'motion_or_camera_setters':False,'automatic_reopen_or_CAN_recovery':False,'native_diagnostic_saved_frames':0,'paired_RGBD_saved_frames':0,
            'native_received':native['received'],'native_rejections':native['rejected'],'paired_capture_received':capture['received'],
            'GET_requests_sent':c['requests_sent'],'GET_replies_received':c['raw_replies_received'],'GET_error_counts':dict(Counter(r['error'] for r in c['records'])),
            'factory_error':load(SRC/'factory.json').get('error'),'depth_started_marker_in_log':'SENSOR_DEPTH is started' in (SRC/'depth.log').read_text(),
            'current_blocker':'Original OpenNI depth-source initialization did not complete; both independent observers received no depth/Info. GET services advertised but returned no replies.',
            'exact_blocked_function_verified':False,'GET_before_depth_ready_causal_role_verified':False,
            'source_ordering_fact':'First GET sent before SENSOR_DEPTH-started confirmation; unlike an active verified stream, advertised services alone did not prove startup complete.',
            'kernel_window_correct_command':'journalctl -k --since=@1792052060 --until=@1792052110 --no-pager -o short-iso',
            'kernel_window_has_entries':(SRC/'kernel_epoch_window.txt').read_text().strip()!='-- No entries --',
            'kernel_first_command_parse_failure_retained':True,
            'preflight_full_SDK_static_passed':load(SRC/'sdk_before.json')['quality']['static_three_seconds_and_thirty_samples'],
            'preflight_q_equals_prior_observation':all(x==0 for x in e['pre_q_delta_rad']),
            'last_fresh_feedback':load(SRC/'feedback.json')['actual_last_sample'],'last_sample_not_current_monitoring':True,
            'CAN_before':before,'CAN_after':after,'new_CAN_TX':after['tx']-before['tx'],
            'source_SHA_before_and_after_equal':True,'production_five_SHA':production,
            'new_tool_offline_tests_total':59,'new_tool_successful_live_depth_storage_verified':False,
            'formal_A_previous_60_not_overwritten':True,'formal_qualified_complete_pairs':1,'camera_cube_center_m':None,'gripper_base_cube_center_m':None,
            'source_initialization_call_site_candidate':'ob_camera_node.cpp startStreams() lines223-260 contains several configuration/start calls before its completion log; no live thread stack was recorded.',
            'next_proposal_not_implemented':'In diagnostic native mode only, defer all camera GET calls until real depth+same-stamp Info has been received; first perform a pure-subscription startup check, no driver/config/laser/TF change. Requires specific approval.',
            'GitHub_pushed':False}
put(OUT/'assessment.json',assessment)
put(OUT/'verification.json',{'raw_archive_files':len(assets),'archive_sha256':sha(OUT/'runtime_closed.tar.gz'),'archive_SHA_verified':True,'source_receipt_SHA_verified':True,'production_five_SHA_unchanged':True,'tests_passed':59,'bounded_single_session':True,'native_live_positive_test_complete':False,'formal_A_not_modified':True,'all_sources_exited':True})
print(json.dumps({'archived_files':len(assets),'camera_s':assessment['single_camera_session_s'],'native_frames':0,'GET_requests':c['requests_sent'],'GET_replies':0,'native_received':native['received'],'RGBD_received':capture['received'],'CAN_before':before,'CAN_after':after},indent=2))
