"""Record passive SDK quality, then use the ORIGINAL approved sampler checks.

No retry, interface recovery, direct SDK movement, or production edits.
"""
import json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TOOLS=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
sys.path.insert(0,str(TOOLS))
from collect_calibration_sdk import summarize
report={'baseline_commit':'8744c14','epoch':time.time(),'CAN_recovery':False,'USB_reset':False,'gripper_commands':0,
        'wrapper_added_static_speed_admission_removed':True,'SDK_quality_not_relabelled':True,
        'original_sampler_helpers_or_production_gates_changed':False,
        'previous_wrapper_failure':'/home/johnwick/brain_robot_logs/board_usb31_sampling_20261016.9ECrHF/invocation.json'}
jobs=[]
def save(n,v):
    with (ROOT/n).open('x') as f:json.dump(v,f,indent=2,allow_nan=False)
def start(n,argv):
    f=(ROOT/(n+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((n,p,f));return p
def snapshot():
    p=subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,timeout=4)
    return {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'epoch':time.time()}
try:
    save('interface_initial.json',snapshot())
    k=subprocess.run(['sudo','-n','dmesg','--color=never'],capture_output=True,text=True,timeout=5)
    (ROOT/'kernel_before.txt').write_text(k.stdout)
    start('candump',['candump','-L','can0'])
    p=start('sdk_before',['/usr/bin/python3',str(TOOLS/'collect_calibration_sdk.py'),'--output',str(ROOT/'sdk_before.json'),'--duration-s','4'])
    report['SDK_before_rc']=p.wait(timeout=16)
    rows=json.loads((ROOT/'sdk_before.json').read_text())['samples']
    original=None
    for i in range(len(rows)):
        for j in range(i+30,len(rows)+1):
            if all(s['fresh_after_passive_connection'] for s in rows[i:j]):
                quality=summarize(rows[i:j])
                if quality['static_three_seconds_and_thirty_samples']:
                    if original is None or j-i>original['indices'][1]-original['indices'][0]:original={'indices':[i,j],'quality':quality}
    report['original_static_slice']=original
    fresh=[s for s in rows if s['fresh_after_passive_connection']]
    # The approved sampler owns live freshness, original 3s q-settling,
    # limits/planning and feedback stop checks. Do not add a second speed gate.
    if len(fresh)<30:raise RuntimeError('No current receive-only SDK data; no control startup')
    report['last_fresh_SDK']=fresh[-1]
    if not all(fresh[-1]['enabled']):raise RuntimeError('Changed enabled state; do not implicitly take over')
    save('preflight.json',report.copy())
    p=start('sampler',['/usr/bin/python3',str(ROOT/'executed_sampler.py'),str(ROOT)])
    report['sampler_rc']=p.wait(timeout=690)
except BaseException as e:report['error']=repr(e)
finally:
    for _,p,_ in reversed(jobs):
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    until=time.monotonic()+8
    while time.monotonic()<until and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    for n,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close()
    save('interface_end.json',snapshot())
    k=subprocess.run(['sudo','-n','dmesg','--color=never'],capture_output=True,text=True,timeout=5)
    (ROOT/'kernel_after.txt').write_text(k.stdout)
    report['all_outer_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['end_epoch']=time.time();save('invocation.json',report)
print(json.dumps({'root':str(ROOT),'sampler_rc':report.get('sampler_rc'),'error':report.get('error'),'all_outer_sources_exited':report['all_outer_sources_exited']}),flush=True)
