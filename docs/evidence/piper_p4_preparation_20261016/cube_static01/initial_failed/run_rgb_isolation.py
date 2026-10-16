"""Default backend first; if stalled, one process-local V4L2 diagnostic. No CAN."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
result={'epoch':time.time(),'production_environment_changed':False,'motion_commands_sent':False,'CAN_opened':False,'cases':[]}
for name,overrides in [('default_backend',{}),('process_local_V4L2',{'OPENCV_VIDEOIO_PRIORITY_GSTREAMER':'0'})]:
    if result['cases'] and result['cases'][-1].get('frames')==6:break
    folder=ROOT/name;folder.mkdir()
    jobs=[];row={'name':name,'child_environment_only':dict(overrides,OPENCV_VIDEOIO_DEBUG='1')}
    try:
        env=dict(os.environ,**row['child_environment_only'])
        f=(folder/'receiver.log').open('xb');p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'read_color_only.py'),str(folder)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True);jobs.append(('receiver',p,f))
        end=time.monotonic()+3
        while not (folder/'listening.json').exists() and p.poll() is None and time.monotonic()<end:time.sleep(.03)
        f=(folder/'publisher.log').open('xb');color=subprocess.Popen(['/opt/ros/humble/lib/image_tools/cam2image','--ros-args',
            '-p','burger_mode:=false','-p','device_id:=0','-p','frequency:=5.0',
            '-p','width:=320','-p','height:=240','-p','frame_id:=camera_color_optical_frame',
            '-r','image:=/camera/color/image_raw'],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        jobs.append(('publisher',color,f));row['receiver_rc']=p.wait(timeout=13)
        row['frames']=json.loads((folder/'color_result.json').read_text())['frames']
    except BaseException as e:row['exception']=repr(e)
    finally:
        for _,p,_ in jobs:
            if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
        end=time.monotonic()+2
        while time.monotonic()<end and any(p.poll() is None for _,p,_ in jobs):time.sleep(.03)
        row['exits']=[]
        for label,p,f in jobs:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
            p.wait(timeout=2);f.close();row['exits'].append({'name':label,'rc':p.returncode})
    result['cases'].append(row)
result['end_epoch']=time.time()
with (ROOT/'rgb_isolation.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
