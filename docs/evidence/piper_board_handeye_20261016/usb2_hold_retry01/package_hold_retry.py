"""Offline audit of corrected diagnostic hold; preserve complete raw evidence."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/usb2_hold_retry01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def gaps(rows,key='epoch'):
    values=[{'gap_s':b[key]-a[key],'before':a[key],'after':b[key]} for a,b in zip(rows,rows[1:])]
    return sorted(values,key=lambda v:v['gap_s'],reverse=True)
def summary(rows):
    return {'samples':len(rows),'first_epoch':rows[0]['epoch'] if rows else None,
        'last_epoch':rows[-1]['epoch'] if rows else None,
        'q_spread_rad':[max(r['position'][i] for r in rows)-min(r['position'][i] for r in rows) for i in range(6)] if rows else None,
        'largest_receipt_gaps_s':gaps(rows)[:5],
        'largest_monotonic_gaps_s':gaps(rows,'monotonic')[:5]}

r=load(ROOT/'execution.json')
rows=[json.loads(s) for s in (ROOT/'ROS_messages.jsonl').read_text().splitlines()]
cmd=[s for s in rows if s['topic']=='/joint_commands']
fb=[s for s in rows if s['topic']=='/joint_states_feedback']
start=r.get('hold_start_epoch')
end=r.get('hold_end_epoch')
disarm=next((e['epoch'] for e in r['events'] if e.get('service')=='/piper_jog_adapter/disarm'),None)
def during(rows):return [v for v in rows if start is not None and v['epoch']>=start and (end or disarm) is not None and v['epoch']<=(end or disarm)]
raw=(ROOT/'CAN_receive_epoch_ns_frame16.bin').read_bytes() if (ROOT/'CAN_receive_epoch_ns_frame16.bin').exists() else b''
assert len(raw)%24==0
rawrows=[];ids=collections.Counter();by_id=collections.defaultdict(list)
for offset in range(0,len(raw),24):
    ns,cid=struct.unpack_from('=QI',raw,offset)
    v={'epoch':ns/1e9};key=hex(cid)
    rawrows.append(v);ids[key]+=1;by_id[key].append(v)
rawhold=during(rawrows);fbhold=during(fb);cmdhold=during(cmd)
fb_gaps=gaps(fbhold);raw_gaps=gaps(rawhold)
before=r['CAN_snapshots'][0]['state'];after=r['CAN_snapshots'][-1]['state']
new_kernel=[s for s in r.get('kernel_after','').splitlines() if s not in r.get('kernel_before','').splitlines()]
sdk_before=r['sdk'].get('sdk_before',{});sdk_after=r['sdk'].get('sdk_after',{})
b=sdk_before.get('last_fresh');a=sdk_after.get('last_fresh')
frozen=load(ROOT/'production_SHA_before.json')
assert all(sha(Path(p))==v for p,v in frozen.items())
assert r['all_owned_sources_exited'] and r['six_source_SHA_unchanged']
old=load(REPO/'docs/evidence/piper_board_handeye_20261016/usb2_hold01/assessment.json')
source_SHA={k:{'path':v['path'],'SHA256':sha(Path(v['path']))} for k,v in old['runtime_source_SHA'].items()}
assert source_SHA==old['runtime_source_SHA']
assert (ROOT/'original_adapter_only.py').read_bytes()==(REPO/'docs/evidence/piper_board_handeye_20261016/usb2_hold01/original_adapter_only.py').read_bytes()
assessment={'baseline_commit':'bf18c2c','operator_quote':'同意',
    'scope':r['scope'],'change_only':'Diagnostic wrapper event recording in place of .5s early-abort; production controls unchanged.',
    'offline_tests':load(ROOT/'offline_test_result.json'),
    'hold_completed':r.get('hold_completed',False),'hold_elapsed_s':r.get('hold_elapsed_s'),
    'hold_completed_with_original_watchdogs_and_fresh_end':r['hold_passed'],'execution_error':r['error'],
    'script_exit_rule_result':0 if r['hold_passed'] and r['error'] is None else 2,
    'hold_start_epoch':start,'hold_end_epoch':end,'software_disarm_response_epoch':disarm,
    'loop_feedback_age_gap_events':r.get('feedback_gap_events',[]),'loop_open_gap_at_end':r.get('open_feedback_gap'),
    'feedback_receipt_intervals_all_le_0_5s_during_hold':bool(fbhold) and not any(v['gap_s']>.5 for v in fb_gaps),
    'raw_reader_intervals_all_le_0_5s_during_hold':bool(rawhold) and not any(v['gap_s']>.5 for v in raw_gaps),
    'loop_observer_limit':'Loop age events alone may miss a shared scheduling pause; independent full ROS and raw receive intervals above remain authoritative for observed gaps.',
    'command_summary':summary(cmd),'feedback_summary':summary(fb),
    'command_during_hold':summary(cmdhold),'feedback_during_hold':summary(fbhold),
    'raw_frames':len(raw)//24,'raw_ID_counts':dict(ids),
    'raw_largest_gaps_s':gaps(rawrows)[:5],'raw_hold_largest_gaps_s':raw_gaps[:5],
    'raw_feedback_ID_hold_gaps_s':{key:gaps(during(by_id[key]))[:5] for key in ['0x2a5','0x2a6','0x2a7','0x3a4','0x3a5','0x3a6','0x251','0x256']},
    'raw_format':'24 bytes: native standard uint64 userspace epoch_ns followed by Linux classic CAN frame16. Guest little-endian x86_64; not hardware/kernel timestamps.',
    'CAN_RX_before':before['stats64']['rx']['packets'],'CAN_RX_after':after['stats64']['rx']['packets'],
    'CAN_TX_before':before['stats64']['tx']['packets'],'CAN_TX_after':after['stats64']['tx']['packets'],
    'CAN_end_state':after['linkinfo']['info_data']['state'],'CAN_end_error_counters':after['linkinfo']['info_xstats'],
    'kernel_new_lines':new_kernel,'SDK_before':sdk_before,'SDK_after':sdk_after,
    'SDK_q_before_after_identical':bool(b and a and b['q_mdeg']==a['q_mdeg']),
    'outgoing_ROS_gripper_frames':sum('gripper' in v['name'] for v in cmd),
    'observed_motion_inputs':r['observed_motion_inputs'],
    'no_wrapper_motion_publishers':True,'all_owned_sources_exited':r['all_owned_sources_exited'],
    'six_production_SHA_unchanged':True,'driver_launch_SDK_enum_SHA_unchanged':source_SHA,
    'hardware_disable_reset_or_displaced_target_requested':False,
    'causal_limit':'A bounded idle hold is not movement/calibration/camera/grasp verification or proof of a permanent transport cure. Userspace timestamps alone do not locate any gap to physical CAN, USB, guest scheduling or SDK/ROS.',
    'next_scope':'Finish this specific hold and record. No automatic observation return, SEARCH, camera start, or additional board motions. Do not repeat the successful passive60 or J4.',
    'calibration':'Old board candidates 2/10 unchanged; production TF, approach, detector gates and limits frozen.',
    'Git_sync':'Local only; pre-existing divergent-main/history-review/publication-scope blocker unchanged.'}
OUT.mkdir(exist_ok=False)
put(OUT/'assessment.json',assessment);put(OUT/'production_SHA_after.json',frozen)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),
    'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],
    'all_member_SHA_readback_verified':True})
for p in files:
    if p.suffix in ('.py','.json','.diff'):shutil.copyfile(p,OUT/p.name)
print(json.dumps({k:assessment[k] for k in ['hold_completed','hold_elapsed_s','hold_completed_with_original_watchdogs_and_fresh_end','execution_error','feedback_receipt_intervals_all_le_0_5s_during_hold','raw_reader_intervals_all_le_0_5s_during_hold','CAN_TX_after','SDK_q_before_after_identical','kernel_new_lines']},indent=2))
print('Archived',len(files),'files,',archive.stat().st_size,'bytes')
