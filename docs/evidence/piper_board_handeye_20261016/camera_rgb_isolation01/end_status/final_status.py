"""Read-only end status after bounded RGB recovery probes."""
from pathlib import Path
import json,re,subprocess,time
ROOT=Path(__file__).resolve().parent
r={'epoch':time.time(),'commands':[],'motion_or_camera_stream_commands':False}
for argv in [['lsusb','-t'],['lsusb','-d','2bc5:'],['ip','-json','-details','-statistics','link','show','can0'],
             ['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm']]:
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    r['commands'].append({'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
ps=subprocess.run(['ps','-eo','pid,stat,args'],capture_output=True,text=True,timeout=5)
r['robot_or_camera_sources']=[s for s in ps.stdout.splitlines() if re.search(r'cam2image|astra_camera_node|component_container|piper_ctrl_single_node|piper_jog_adapter\.py|visual_search_controller|grasp_lift_executor',s)]
r['video_nodes']=[str(p) for p in Path('/dev').glob('video*')]
tool='/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_calibration_sdk.py'
p=subprocess.run(['/usr/bin/python3',tool,'--output',str(ROOT/'SDK_final.json'),'--duration-s','4'],capture_output=True,text=True,timeout=9)
r['passive_SDK']={'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
(ROOT/'final_status.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'video_nodes':r['video_nodes'],'remaining_robot_or_camera_sources':r['robot_or_camera_sources'],'SDK_rc':p.returncode}))
