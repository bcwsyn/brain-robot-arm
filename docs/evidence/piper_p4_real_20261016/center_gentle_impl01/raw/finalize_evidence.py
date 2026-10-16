"""Verify exact approved deployment, archive logs (no binaries), no hardware."""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
DEST=REPO/'docs/evidence/piper_p4_real_20261016/center_gentle_impl01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def active(p):
    if p.startswith('brain_robot_arm/piper_ws/'):return Path('/home/johnwick/piper_ws')/p.removeprefix('brain_robot_arm/piper_ws/')
    if p.startswith('brain_robot_arm/vendor/piper_ros/'):return Path('/home/johnwick/piper_ros')/p.removeprefix('brain_robot_arm/vendor/piper_ros/')
    return Path('/home/johnwick/start_brain_robot_cube_real.sh')
report={'baseline':'bdfc3cc','verified_epoch':time.time(),
        'deployed_not_physically_tested':True,'physical_grasp_succeeded':False,
        'this_turn_hardware_CAN_camera_or_motion_commands':False,
        'git_publication':'local only; existing main divergence/history review unchanged'}
initial=json.loads((ROOT/'deployment.json').read_text())
report['synchronized_sources']=[]
for r in initial['files']:
    p=r['canonical'];a=active(p)
    assert sha(REPO/p)==sha(a),p
    report['synchronized_sources'].append({'canonical':p,'active':str(a),'sha256':sha(a)})
previous=json.loads((REPO/'docs/evidence/piper_p4_real_20261016/attempt01/final_verification.json').read_text())
report['protected_files_unchanged']=previous['protected_files_unchanged']
for p,h in report['protected_files_unchanged'].items():assert sha(Path(p))==h,p
report['additional_unchanged']={}
for p,pinned in [
    ('/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp',None),
    ('/home/johnwick/ros2_ws/install/astra_camera/lib/libastra_camera.so',None),
    ('/home/johnwick/piper_ws/install/piper_description/share/piper_description/urdf/piper_description.urdf',None)]:
    path=Path(p)
    if path.is_file():report['additional_unchanged'][p]=sha(path)
report['executor_binary_sha256']=sha(Path('/home/johnwick/piper_ws/build/brain_robot_pick_place/grasp_lift_executor'))
report['source_install_links']={p:str(Path(p).resolve()) for p in [
    '/home/johnwick/piper_ws/install/brain_robot_pick_place/lib/brain_robot_pick_place/grasp_lift_executor',
    '/home/johnwick/piper_ros/install/piper/lib/python3.10/site-packages/piper/piper_ctrl_single_node.py']}
report['tests']={}
for name in ['final_focused_pytest.xml','regression_pytest.xml','canonical_geometry.xml','installed_center_gentle.xml']:
    r=ET.parse(ROOT/name).getroot()
    suites=list(r) if r.tag=='testsuites' else [r]
    totals={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert not totals['failures'] and not totals['errors']
    report['tests'][name]=totals
report['isolated_integrations']={}
for scenario in ['empty','object']:
    r=json.loads((ROOT/f'v5_loopback_{scenario}/result.json').read_text());assert r['passed']
    report['isolated_integrations'][scenario]={'passed':r['passed'],'states':r['states'],
        'arm_trajectories':len(r['arm_trajectories']),'gripper_commands':len(r['gripper_commands']),
        'last_opening_m':r['last_opening_m'],'joint_commands':r['joint_commands'],
        'physical_grasp_succeeded':False}
    ex=json.loads((ROOT/f'v5_loopback_{scenario}/execution.json').read_text())
    assert ex['executor_sha256_start']==ex['executor_sha256_end']==report['executor_binary_sha256']
    assert all(not j['forced'] for j in ex['jobs'])
report['preview']=json.loads((ROOT/'preview_center_01/preview_result.json').read_text())
report['remaining_geometry_issue']='Old manual reference candidate projects outside visible clamped cube under current X; no validated current center/reference target for hardware yet.'
report['all_owned_test_parents_exited']=True
with (ROOT/'final_verification.json').open('x') as f:json.dump(report,f,indent=2)
DEST.mkdir(exist_ok=False)
manifest=[];excluded=[]
for src in sorted(ROOT.rglob('*')):
    if not src.is_file() or '__pycache__' in src.parts:continue
    data=src.read_bytes()
    if data[:4]==b'\x7fELF':excluded.append(str(src));continue
    rel=src.relative_to(ROOT)
    dst=DEST/'raw'/rel
    if dst.suffix=='.log':dst=dst.with_suffix('.txt')
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    assert sha(src)==sha(dst)
    manifest.append({'source':str(src),'archive':str(dst.relative_to(DEST)),
                     'bytes':dst.stat().st_size,'sha256':sha(dst)})
with (DEST/'manifest.json').open('x') as f:json.dump({'assets':manifest,'ELF_excluded_home_only':excluded},f,indent=2)
print(json.dumps({'destination':str(DEST),'files':len(manifest),'bytes':sum(r['bytes'] for r in manifest),
                  'executor_sha256':report['executor_binary_sha256'],'tests':report['tests'],
                  'integrations':report['isolated_integrations']},indent=2))
