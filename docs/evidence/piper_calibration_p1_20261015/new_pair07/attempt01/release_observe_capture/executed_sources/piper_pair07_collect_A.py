"""One original bounded stationary A session after approved observation return."""
import json,subprocess,tempfile,time
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='new_pair07_A.',dir='/home/johnwick/brain_robot_logs'))
tool='/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/capture_calibration_session.py'
print(root,flush=True)
started=time.time()
with (root/'coordinator.log').open('wb') as out:
 p=subprocess.run(['/usr/bin/python3',tool,'--output',str(root/'session')],stdout=out,stderr=subprocess.STDOUT,timeout=105)
print(json.dumps({'root':str(root),'returncode':p.returncode,'elapsed_s':time.time()-started}),flush=True)
raise SystemExit(p.returncode)
