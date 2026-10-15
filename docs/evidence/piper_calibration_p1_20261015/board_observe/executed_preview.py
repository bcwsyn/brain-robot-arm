"""Sixth placement: bounded read-only preview, no robot control interfaces."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(tempfile.mkdtemp(prefix='new_pair07_preview.',dir='/home/johnwick/brain_robot_logs'))
TESTS=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
sys.path.insert(0,str(TESTS))
from collect_calibration_p0 import read_can,healthy_window
from collect_calibration_sdk import summarize
jobs=[];camera_start=None
report={'pair_id':'new_pair07','role':'held_out','operator_new_placement_confirmed':True,
 'operator_quote':'已完成','preview_only':True,'formal_A':False,'B_present':False,
 'motion_commands_sent':False,'camera_setters_called':False,'CAN_recovery':False,
 'automatic_reopen':False,'events':[],'error':None}
def save(name,obj):
 with (ROOT/name).open('x') as f:json.dump(obj,f,indent=2,allow_nan=False)
def start(name,argv):
 f=(ROOT/(name+'.log')).open('xb')
 p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 jobs.append((name,p,f));report['events'].append({'name':name,'pid':p.pid,'argv':argv,'epoch':time.time()})
 return p
print(ROOT,flush=True)
sources=[TESTS/n for n in ['collect_static_rgbd.py','wait_calibration_ready.py',
 'calibration_readonly_feedback.py','collect_calibration_sdk.py']]
try:
 save('source_SHA_before.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
 sdk=start('sdk',['/usr/bin/python3',str(TESTS/'collect_calibration_sdk.py'),'--output',str(ROOT/'sdk.json'),'--duration-s','6'])
 report['SDK_full_window_rc']=sdk.wait(timeout=10)
 packet=json.loads((ROOT/'sdk.json').read_text());rows=packet['samples']
 fresh=[r for r in rows if r['fresh_after_passive_connection']]
 if len(fresh)<30:raise RuntimeError('Insufficient actual fresh SDK feedback; no camera started')
 report['actual_pre_sample']=fresh[-1]
 slices=[]
 for i in range(len(rows)):
  for j in range(i+30,len(rows)+1):
   if all(r['fresh_after_passive_connection'] for r in rows[i:j]):
    q=summarize(rows[i:j])
    if q['static_three_seconds_and_thirty_samples']:slices.append({'indices':[i,j],'quality':q})
 report['original_static_slice']=max(slices,key=lambda r:r['indices'][1]-r['indices'][0]) if slices else None
 before=read_can();time.sleep(.2);after=read_can()
 save('can_before.json',{'before':before,'after':after,'healthy':healthy_window(before,after)})
 if not healthy_window(before,after):raise RuntimeError('Existing CAN not active receiving; no recovery')
 start('bridge',['/usr/bin/python3',str(TESTS/'calibration_readonly_feedback.py'),'--duration-s','50','--output',str(ROOT/'feedback.json')])
 ready=start('ready',['/usr/bin/python3',str(TESTS/'wait_calibration_ready.py'),'--duration-s','15',
  '--output',str(ROOT/'readiness.json'),'--listening',str(ROOT/'listening.json')])
 until=time.monotonic()+5
 while not (ROOT/'listening.json').exists() and ready.poll() is None and time.monotonic()<until:time.sleep(.05)
 if not (ROOT/'listening.json').exists():raise RuntimeError('Readiness initialization failed')
 camera_start=time.monotonic();report['camera_start_epoch']=time.time()
 start('depth',['ros2','launch','astra_camera','astra.launch.py'])
 until=time.monotonic()+4
 while time.monotonic()<until:
  if 'SENSOR_DEPTH is started' in (ROOT/'depth.log').read_text(errors='replace'):break
  time.sleep(.05)
 start('color',['/opt/ros/humble/lib/image_tools/cam2image','--ros-args','-p','burger_mode:=false',
  '-p','device_id:=0','-p','frequency:=5.0','-p','width:=320','-p','height:=240',
  '-p','frame_id:=camera_color_optical_frame','-r','image:=/camera/color/image_raw'])
 ready.wait(timeout=max(.1,15-(time.monotonic()-camera_start)))
 r=json.loads((ROOT/'readiness.json').read_text())
 if ready.returncode or not r['ready']:raise RuntimeError('No real four-source readiness')
 prelude=f'import sys;sys.path.insert(0,{str(TESTS)!r});'
 code=prelude+'from pathlib import Path;from collect_static_rgbd import collect;sys.exit(collect(Path(sys.argv[1]),15.,5,settle_s=3.,stop_on_feedback_loss=True,max_bytes=4<<20))'
 capture=start('capture',['/usr/bin/python3','-c',code,str(ROOT/'capture')])
 capture.wait(timeout=min(17,max(.1,32-(time.monotonic()-camera_start))))
 report['capture_rc']=capture.returncode
 c=json.loads((ROOT/'capture/summary.json').read_text());report['saved_frames']=c['saved_frames']
 if c['saved_frames'] and time.monotonic()-camera_start<25:
  factory=start('factory',['/usr/bin/python3','/home/johnwick/brain_robot_logs/calibration_stage1_activated_20261014.kfNDAQ/capture_factory_metadata.py',str(ROOT/'factory.json')])
  factory.wait(timeout=max(.1,32-(time.monotonic()-camera_start)))
  report['factory_rc']=factory.returncode
except BaseException as e:report['error']=repr(e)
finally:
 for _,p,_ in jobs:
  if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
 until=time.monotonic()+1.5
 while time.monotonic()<until and any(p.poll() is None for _,p,_ in jobs):time.sleep(.02)
 for name,p,f in jobs:
  if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
  p.wait(timeout=1);f.close();report['events'].append({'name':name,'exit_code':p.returncode,'epoch':time.time()})
 report['all_owned_sources_exited']=all(p.poll() is not None for _,p,_ in jobs)
 report['camera_elapsed_s']=None if camera_start is None else time.monotonic()-camera_start
 report['within_35s_camera_bound']=camera_start is None or report['camera_elapsed_s']<=35
 save('source_SHA_after.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
 save('can_after.json',read_can());save('execution.json',report)
print(json.dumps({'root':str(ROOT),'saved_frames':report.get('saved_frames',0),'error':report['error'],
 'all_exited':report['all_owned_sources_exited'],'camera_elapsed_s':report['camera_elapsed_s']}),flush=True)
raise SystemExit(0 if report['error'] is None and report.get('saved_frames')==5 and report['within_35s_camera_bound'] else 2)
