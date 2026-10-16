"""Bounded getter-only service discovery follow-up, no RGB reopening or arm TX."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
report={'epoch':time.time(),'getter_only':True,'motion_commands_sent':False,'events':[]}
jobs=[]
def start(label,argv):
    f=(ROOT/(label+'.log')).open('xb')
    p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    jobs.append((label,p,f));return p
try:
    start('depth',['ros2','launch','astra_camera','astra.launch.py'])
    end=time.monotonic()+6
    while time.monotonic()<end:
        if 'SENSOR_DEPTH is started' in (ROOT/'depth.log').read_text(errors='replace'):break
        time.sleep(.05)
    # Direct graph query, no daemon reset or transport settings.
    code="import rclpy,time,json;rclpy.init();n=rclpy.create_node('readonly_camera_service_graph');end=time.monotonic()+3\nwhile time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.1)\nprint(json.dumps(n.get_service_names_and_types()));n.destroy_node();rclpy.shutdown()"
    p=subprocess.run(['/usr/bin/python3','-c',code],capture_output=True,text=True,timeout=6)
    report['service_graph']={'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    p=start('factory',['/usr/bin/python3',str(ROOT/'capture_factory_metadata.py'),str(ROOT/'factory.json')])
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
    (ROOT/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
