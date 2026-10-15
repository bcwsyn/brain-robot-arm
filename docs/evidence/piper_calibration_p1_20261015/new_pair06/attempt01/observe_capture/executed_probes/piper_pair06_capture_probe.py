"""Run original bounded stationary acquisition, inspect owned stalled RGB PID."""
import json, subprocess, tempfile, time
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='new_pair06_instrumented_A.',dir='/home/johnwick/brain_robot_logs'))
tool=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/capture_calibration_session.py')
print(root,flush=True)
with (root/'coordinator.log').open('wb') as log:
    p=subprocess.Popen(['/usr/bin/python3',str(tool),'--output',str(root/'session')],stdout=log,stderr=subprocess.STDOUT)
    sampled=False; start=time.monotonic()
    while p.poll() is None and time.monotonic()-start<100:
        color=root/'session/color.log'
        if not sampled and color.exists() and color.read_text(errors='replace').count('Publishing image #')==1:
            time.sleep(3)
            if color.read_text(errors='replace').count('Publishing image #')==1:
                children=subprocess.check_output(['ps','--ppid',str(p.pid),'-o','pid=,args='],text=True)
                candidates=[int(line.split()[0]) for line in children.splitlines() if '/opt/ros/humble/lib/image_tools/cam2image --ros-args' in line]
                if len(candidates)==1:
                    with (root/'RGB_stacks.txt').open('wb') as f:
                        r=subprocess.run(['timeout','-k','2s','8s','sudo','-n','gdb','-batch',
                            '-ex','set pagination off','-ex','thread apply all bt','-p',str(candidates[0])],stdout=f,stderr=subprocess.STDOUT)
                    (root/'probe.json').write_text(json.dumps({'PID':candidates[0],'gdb_rc':r.returncode,'epoch':time.time(),'no_motion':True},indent=2))
                sampled=True
        time.sleep(.2)
    if p.poll() is None:raise RuntimeError('Original coordinator exceeded 100s; inspect owned children')
    print(json.dumps({'root':str(root),'coordinator_rc':p.returncode,'elapsed':time.monotonic()-start,'stack_sampled':sampled}),flush=True)
