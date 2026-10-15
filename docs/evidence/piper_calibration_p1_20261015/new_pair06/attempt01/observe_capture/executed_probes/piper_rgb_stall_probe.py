"""Bounded camera-only evidence; no robot/control interfaces."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

root = Path(tempfile.mkdtemp(prefix='new_pair06_rgb_stall.', dir='/home/johnwick/brain_robot_logs'))
cmd = ['/opt/ros/humble/lib/image_tools/cam2image', '--ros-args',
       '-p','burger_mode:=false','-p','device_id:=0','-p','frequency:=5.0',
       '-p','width:=320','-p','height:=240','-p','frame_id:=camera_color_optical_frame',
       '-r','image:=/camera/color/image_raw']
report = {'argv': cmd, 'no_motion':True,'depth_started':False, 'epoch':time.time()}
with (root/'color.log').open('wb') as out:
    p = subprocess.Popen(['strace','-f','-tt','-T','-e','trace=ioctl,poll,ppoll,futex',
                          '-o',str(root/'syscalls.txt')]+cmd,
                         stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    report['strace_pid']=p.pid
    print(root,flush=True)
    try:
        time.sleep(14)
        report['published_logs']=(root/'color.log').read_text(errors='replace').count('Publishing image #')
        report['children']=subprocess.run(['ps','--ppid',str(p.pid),'-o','pid,stat,wchan:30,args'],capture_output=True,text=True).stdout
    finally:
        os.killpg(p.pid,signal.SIGINT)
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
        report['returncode']=p.returncode
        report['end_epoch']=time.time()
        (root/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
