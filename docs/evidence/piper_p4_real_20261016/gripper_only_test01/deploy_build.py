"""Backup and sync ONLY the approved original executor/launch/entry, no ROS."""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
paths={
 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp':'/home/johnwick/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp',
 'brain_robot_arm/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py':'/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py',
 'brain_robot_arm/scripts/start_brain_robot_cube_real.sh':'/home/johnwick/start_brain_robot_cube_real.sh'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report={'baseline':'4037724','start_epoch':time.time(),'starts_ROS_CAN_or_hardware':False,'files':[]}
before=ROOT/'before';before.mkdir(exist_ok=False)
for rel,active in paths.items():
    dest=Path(active);old=subprocess.check_output(['git','-C',str(REPO),'show','4037724:'+rel])
    assert sha(dest)==hashlib.sha256(old).hexdigest(),active+' changed outside this task'
    backup=before/rel;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,backup)
    report['files'].append({'canonical':rel,'active':active,'before_sha256':sha(dest)})
binary=Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
shutil.copy2(binary,before/'grasp_lift_executor.bin');report['binary_before_sha256']=sha(binary)
for rel,active in paths.items():
    shutil.copy2(REPO/rel,active);assert sha(REPO/rel)==sha(Path(active))
for label,argv in [('build',['cmake','--build','/home/johnwick/piper_ws/build/brain_robot_pick_place',
                             '--target','grasp_lift_executor','-j1'])]:
    with (ROOT/(label+'.log')).open('x') as f:r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=300)
    report[label+'_rc']=r.returncode
report['binary_after_sha256']=sha(binary);report['end_epoch']=time.time()
for row in report['files']:row['after_sha256']=sha(Path(row['active']))
with (ROOT/'deployment.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report,indent=2))
raise SystemExit(report['build_rc'])
