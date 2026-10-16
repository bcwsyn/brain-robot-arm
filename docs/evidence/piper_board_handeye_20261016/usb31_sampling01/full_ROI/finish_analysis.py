"""Post-session passive status and offline audits. Never start a controller."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub');TOOLS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
def read(p):return json.loads(p.read_text())
def save(n,x):
    with (ROOT/n).open('x') as f:json.dump(x,f,indent=2,allow_nan=False)
e=read(ROOT/'execution.json');assert e['all_owned_sources_exited']
report={'epoch':time.time(),'post_session_only':True,'motion_commands_sent':False,'audits':[]}
ps=subprocess.run(['ps','-eo','pid,comm,args'],capture_output=True,text=True,timeout=4)
needles=['cam2image','component_container','piper_ctrl_single_node','piper_jog_adapter.py','visual_search_controller','grasp_lift_executor','calibration_readonly_feedback.py']
report['remaining_sources']=[l for l in ps.stdout.splitlines() if any(n in l for n in needles)]
assert not report['remaining_sources']
p=subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,timeout=4)
report['CAN_before_passive']=json.loads(p.stdout)[0]
if report['CAN_before_passive']['linkinfo']['info_data']['state']=='ERROR-ACTIVE':
    p=subprocess.run(['/usr/bin/python3',str(TOOLS/'collect_calibration_sdk.py'),'--output',str(ROOT/'sdk_final.json'),'--duration-s','4'],capture_output=True,text=True,timeout=9)
    report['SDK_final']={'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    packet=read(ROOT/'sdk_final.json');fresh=[s for s in packet['samples'] if s['fresh_after_passive_connection']]
    report['actual_last_SDK']=fresh[-1] if fresh else None
for root in [Path('/home/johnwick/brain_robot_logs/board_return_20261016.8NDic8'),
             Path('/home/johnwick/brain_robot_logs/board_safe_seed_20261016.7Zjm2l'),ROOT]:
    p=subprocess.run(['/usr/bin/python3',str(ROOT/'audit_bag.py'),str(root)],capture_output=True,text=True,timeout=45)
    report['audits'].append({'root':str(root),'rc':p.returncode,'stderr':p.stderr})
    if p.returncode:raise RuntimeError('Bag audit failed '+str(root)+': '+p.stderr)
p=subprocess.run(['/usr/bin/python3','-m','unittest','discover','-s',str(ROOT),'-p','test_board_handeye_fit.py','-v'],capture_output=True,text=True,timeout=15)
(ROOT/'offline_tests.txt').write_text(p.stdout+p.stderr)
save('offline_test_result.json',{'rc':p.returncode,'test_cases':6,'log':'offline_tests.txt'})
assert p.returncode==0
if e.get('completed_9fit_1heldout'):
    p=subprocess.run(['/usr/bin/python3',str(ROOT/'board_handeye_fit.py'),str(ROOT)],capture_output=True,text=True,timeout=35)
    (ROOT/'fit_stdout.txt').write_text(p.stdout+p.stderr)
    report['fit_rc']=p.returncode
else:report['fit_skipped']='Original 9+1 incomplete; no held-out acceptance'
frozen=read(REPO/'docs/evidence/piper_board_handeye_20261016/usb31_static01/production_SHA_after.json')
report['production_SHA_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in frozen.items())
assert report['production_SHA_unchanged']
p=subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,timeout=4)
report['CAN_after_passive']=json.loads(p.stdout)[0]
report['end_epoch']=time.time();save('final_status.json',report)
print(json.dumps({'audits':report['audits'],'fit_rc':report.get('fit_rc'),'fit_skipped':report.get('fit_skipped'),
                  'SDK_final_rc':report.get('SDK_final',{}).get('rc'),'actual_last_SDK':report.get('actual_last_SDK'),'production_unchanged':report['production_SHA_unchanged']}),flush=True)
