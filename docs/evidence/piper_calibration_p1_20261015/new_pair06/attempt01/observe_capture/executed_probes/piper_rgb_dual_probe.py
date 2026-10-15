"""Camera-only dual-stream controlled contrast; capture and stacks, no robot."""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='new_pair06_rgb_dual.',dir='/home/johnwick/brain_robot_logs'))
tests=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
jobs=[]; report={'no_robot_interfaces':True,'epoch':time.time(),'events':[]}
def start(name,cmd,env=None):
    f=(root/(name+'.log')).open('wb')
    p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env=env)
    jobs.append((name,p,f)); report['events'].append({'name':name,'pid':p.pid,'argv':cmd,'epoch':time.time()})
    return p
print(root,flush=True)
try:
    env=dict(os.environ,BRAIN_ROBOT_CAPTURE_MAX_SECONDS='25',BRAIN_ROBOT_CAPTURE_MAX_MB='8')
    start('images',['/usr/bin/python3',str(tests/'capture_scale_frames.py'),str(root/'images')],env)
    start('depth',['ros2','launch','astra_camera','astra.launch.py'])
    time.sleep(4)
    rgb=start('color',['/opt/ros/humble/lib/image_tools/cam2image','--ros-args','-p','burger_mode:=false',
      '-p','device_id:=0','-p','frequency:=5.0','-p','width:=320','-p','height:=240',
      '-p','frame_id:=camera_color_optical_frame','-r','image:=/camera/color/image_raw'])
    time.sleep(10)
    report['published_at_10s']=(root/'color.log').read_text(errors='replace').count('Publishing image #')
    if report['published_at_10s']<3 and rgb.poll() is None:
        with (root/'stacks.txt').open('wb') as f:
            result=subprocess.run(['timeout','-k','2s','6s','sudo','-n','gdb','-batch','-ex','set pagination off',
                                  '-ex','thread apply all bt','-p',str(rgb.pid)],stdout=f,stderr=subprocess.STDOUT)
            report['gdb_rc']=result.returncode
    time.sleep(4)
    report['published_final']=(root/'color.log').read_text(errors='replace').count('Publishing image #')
finally:
    for _,p,_ in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
    until=time.monotonic()+2
    while time.monotonic()<until and any(p.poll() is None for _,p,_ in jobs):time.sleep(.05)
    for name,p,f in jobs:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=2);f.close();report.setdefault('exits',{})[name]=p.returncode
    report['end_epoch']=time.time();(root/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
