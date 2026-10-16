"""One bounded original-Astra getter-only session for deployment composition."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
jobs=[];report={'epoch':time.time(),'motion_commands_sent':False,'CAN_TX_commands':False,'events':[]}
def start(label,argv):
    f=(ROOT/(label+'.log')).open('xb');p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((label,p,f));return p
try:
    start('internal_depth',['ros2','launch','astra_camera','astra.launch.py'])
    p=start('internal_tf',['/usr/bin/python3',str(ROOT/'read_internal_tf.py')]);report['tf_rc']=p.wait(timeout=16)
    p=start('internal_factory',['/usr/bin/python3',str(ROOT/'capture_factory_metadata.py'),str(ROOT/'factory_before.json')])
    report['factory_rc']=p.wait(timeout=23)
except BaseException as e:report['error']=repr(e)
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    end=time.monotonic()+2
    while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    for name,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close();report['events'].append({'name':name,'rc':p.returncode})
    report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
    report['end_epoch']=time.time()
    with (ROOT/'internal_execution.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps(report))
