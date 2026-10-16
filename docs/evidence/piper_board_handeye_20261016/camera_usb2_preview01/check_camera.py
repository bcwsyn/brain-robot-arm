"""Read-only camera passthrough inventory, no device reset or camera startup."""
from pathlib import Path
import json
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parent
out=ROOT/'camera_inventory.json'
assert not out.exists(), 'Do not overwrite inventory'
commands=[]
for argv in [['lsusb','-t'],['lsusb','-d','2bc5:']]:
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    commands.append({'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
devices=[]
for p in Path('/sys/bus/usb/devices').glob('*'):
    if (p/'idVendor').is_file() and (p/'idVendor').read_text().strip()=='2bc5':
        devices.append({'sysfs':str(p.resolve()),**{k:(p/k).read_text().strip() if (p/k).exists() else None for k in ['idVendor','idProduct','product','manufacturer','serial','speed']}})
videos=[str(p) for p in Path('/dev').glob('video*')]
ps=subprocess.run(['ps','-eo','pid,stat,args'],capture_output=True,text=True,check=True,timeout=5)
sources=[s for s in ps.stdout.splitlines() if re.search(r'piper_ctrl_single_node|piper_jog_adapter\.py|visual_search_controller|grasp_lift_executor|move_group|cam2image|astra_camera_node',s)]
result={'epoch':time.time(),'read_only':True,'commands':commands,'Orbbec_devices':devices,'video_nodes':videos,
    'matching_robot_or_camera_sources':sources,
    'camera_start_reset_motion_or_gripper_commands':False,
    'camera_RGB_depth_passthrough_missing':not devices and not videos,
    'host_manual_step_if_missing':'Only connect Orbbec/Dabai DC1 depth and RGB camera devices (2bc5:0657 and 2bc5:0557) to this VM through VMware removable devices; do not change USB compatibility, reconnect CAN, restart VM/arm, or move board.',
    'camera_USB2_stream_compatibility_established':False,
    'calibration_capture_started':False}
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
