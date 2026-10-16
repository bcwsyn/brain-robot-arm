"""Offline package of USB2 pure-receive result, without device access."""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import sys
import tarfile

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/usb2_passive01'
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from collect_calibration_sdk import summarize
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

OUT.mkdir(exist_ok=False)
r=load(ROOT/'result.json')
sdk=load(ROOT/'sdk.json') if (ROOT/'sdk.json').exists() else None
best=None
if sdk:
    rows=sdk['samples']
    for i in range(len(rows)):
        for j in range(i+30,len(rows)+1):
            q=summarize(rows[i:j])
            if q['static_three_seconds_and_thirty_samples'] and (best is None or j-i>best['n']):best={'i':i,'j':j,'n':j-i,'quality':q}
fresh=[s for s in sdk['samples'] if s['fresh_after_passive_connection']] if sdk else []
frozen=load(REPO/'docs/evidence/piper_board_handeye_20261016/board_resume03_port_reconnect/observe/production_SHA_after.json')
assert all(sha(Path(p))==value for p,value in frozen.items())
echo=lambda s:[line for line in s.splitlines() if re.search(r'gs_usb .*Unexpected (out of range|unused) echo id',line)]
old_echo=echo(r.get('kernel_before',''));new_echo=[line for line in echo(r.get('kernel_after','')) if line not in old_echo]
result={'trial_authorization_commit':'1cf2bf9','latest_operator_confirmation':'已完成',
    'actual_USB_route':r.get('actual_USB_route'),
    'fixed_CAN_activation_commands':[c for c in r['commands'] if c['argv'][:4]==['sudo','-n','ip','link']],
    'passive_trial_passed':r['passive_trial_passed'],'trial_error':r['error'],
    'receive_elapsed_s':r.get('receive_elapsed_s'),'frames':r.get('received_frames'),
    'per_second_frames':[w['frames'] for w in r['windows']],
    'frames_every_second':r.get('new_frames_every_second'),
    'maximum_interframe_gap_s':r.get('maximum_observed_interframe_gap_s'),
    'trailing_no_frame_s':r.get('trailing_no_frame_s'),
    'CAN_after':r.get('after'),'TX_packets_unchanged':r.get('TX_packets_unchanged'),
    'new_kernel_echo_events':new_echo,
    'SDK_exit_code':r.get('SDK_exit_code'),'SDK_quality':sdk['quality'] if sdk else None,
    'SDK_fresh_samples':len(fresh),'SDK_last_fresh_not_continuous_monitoring':fresh[-1] if fresh else None,
    'SDK_original_passing_static_subwindow':best,'SDK_original_thresholds_changed':False,
    'SDK_receipt_times_are_aggregate_not_per_motor':True,
    'robot_control_gripper_enable_disable_reset_commands_sent':False,
    'camera_or_production_driver_started':False,'USB_reset_module_reload':False,
    'all_owned_receivers_exited':r['no_owned_receiver_or_SDK_left_running'],
    'production_six_SHA_unchanged':True,
    'verification_scope':'Passive receive only on actual UHCI USB2-compatible path. Does not prove active TX, controller/adapter admission, movement, image capture, hand-eye calibration or grasp success.',
    'causal_limit':'One passive window cannot establish xHCI as root cause; previous xHCI observations primarily failed while robot commands were active. Conditions are not an active-motion A/B comparison.',
    'next_scope':'If passive checks pass, prepare an explicitly scoped original-driver/adapter current-pose hold TX/feedback check before any displacement; do not repeat successful J4 or automatically launch observation/grasp. Camera pass-through and RGB-D remain separately unverified.',
    'old_board_candidates':'2/10, unchanged','Git_sync':'Local only; existing divergent main/pending history publication review and scope blocker unchanged.'}
put(OUT/'assessment.json',result);put(OUT/'production_SHA_after.json',frozen)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],'all_member_SHA_readback_verified':True})
for p in files:
    if p.suffix in ('.py','.json'):shutil.copyfile(p,OUT/p.name)
print(json.dumps({'assessment':str(OUT/'assessment.json'),'files':len(files),'archive_bytes':archive.stat().st_size,
    'passive_passed':r['passive_trial_passed'],'SDK_quality':result['SDK_quality'],'SDK_last_fresh':result['SDK_last_fresh_not_continuous_monitoring'],
    'SDK_static_subwindow':best,'new_echo_events':new_echo},indent=2))
