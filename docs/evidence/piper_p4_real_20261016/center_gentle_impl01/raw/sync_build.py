"""Scoped approved deployment/build, with preflight hashes and exact backups.
Does not start ROS nodes, touch CAN, or send commands.
"""
import hashlib,json,shutil,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
BASE='bdfc3cc';PKG='brain_robot_arm/piper_ws/src/brain_robot_pick_place/'
relative=[PKG+p for p in ['src/grasp_lift_executor.cpp','CMakeLists.txt',
    'include/brain_robot_pick_place/target_directed_grasp.hpp',
    'include/brain_robot_pick_place/gentle_gripper.hpp',
    'scripts/prepare_p4_center_target.py','test/test_center_gentle.cpp']]
relative+=['brain_robot_arm/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py',
    'brain_robot_arm/scripts/start_brain_robot_cube_real.sh',
    'brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py']
def active(p):
    if p.startswith('brain_robot_arm/piper_ws/'):return Path('/home/johnwick/piper_ws')/p.removeprefix('brain_robot_arm/piper_ws/')
    if p.startswith('brain_robot_arm/vendor/piper_ros/'):return Path('/home/johnwick/piper_ros')/p.removeprefix('brain_robot_arm/vendor/piper_ros/')
    return Path('/home/johnwick/start_brain_robot_cube_real.sh')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pairs=[]
for p in relative:
    dest=active(p)
    old=subprocess.run(['git','-C',str(REPO),'show',BASE+':'+p],capture_output=True)
    if old.returncode==0:
        expected=hashlib.sha256(old.stdout).hexdigest()
        assert dest.exists() and sha(dest)==expected, str(dest)+' changed outside this task'
    else:assert not dest.exists(), str(dest)+' unexpected existing file'
    pairs.append((p,dest))
old=json.loads((REPO/'docs/evidence/piper_p4_real_20261016/attempt01/final_verification.json').read_text())
for p,expected in old['protected_files_unchanged'].items():assert sha(Path(p))==expected
backup=ROOT/'before';backup.mkdir(exist_ok=False)
binary=Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor')
shutil.copy2(binary,backup/'grasp_lift_executor.bin')
report={'baseline':BASE,'start_epoch':time.time(),'starts_ROS_or_hardware':False,'files':[]}
for p,dest in pairs:
    before=backup/p
    if dest.exists():
        before.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,before)
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(REPO/p,dest)
    assert sha(dest)==sha(REPO/p)
    report['files'].append({'canonical':p,'active':str(dest),'sha256':sha(dest),
        'backup':str(before) if before.exists() else None})
for label,cmd in [('build',['cmake','--build','/home/johnwick/piper_ws/build/brain_robot_pick_place',
        '--target','grasp_lift_executor','center_gentle_test','-j1']),
    ('install',['cmake','--install','/home/johnwick/piper_ws/build/brain_robot_pick_place'])]:
    with (ROOT/(label+'.log')).open('x') as log:
        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    report[label+'_rc']=result.returncode
    if result.returncode:break
report['binary_sha256']=sha(binary);report['end_epoch']=time.time()
with (ROOT/'deployment.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
raise SystemExit(0 if report.get('build_rc')==0 and report.get('install_rc')==0 else 2)
