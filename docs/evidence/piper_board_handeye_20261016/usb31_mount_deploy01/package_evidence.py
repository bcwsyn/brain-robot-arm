"""Preserve this bounded static session and verify every archived byte."""
import hashlib,json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/usb31_mount_deploy01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runtime=Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml')
if not (ROOT/'cube_task_real.deployed.yaml').exists():shutil.copyfile(runtime,ROOT/'cube_task_real.deployed.yaml')
vendor=Path('/home/johnwick/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/src')
if not (ROOT/'vendor_internal_tf_source_review.json').exists():
    review={'read_only':True,'physical_ground_truth_not_inferred_from_published_TF':True,'sources':[]}
    for name,start,end in [('ob_camera_node.cpp',351,429),('utils.cpp',37,47)]:
        p=vendor/name
        review['sources'].append({'path':str(p),'SHA256':sha(p),'lines_1_based':[start,end],
            'excerpt':'\n'.join(p.read_text().splitlines()[start-1:end])})
    with (ROOT/'vendor_internal_tf_source_review.json').open('x') as f:json.dump(review,f,indent=2)
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
archive=DEST/'static_session_originals.tar.gz'
if archive.exists():raise FileExistsError('Refuse overwriting an evidence archive')
members=[]
with tarfile.open(archive,'w:gz') as tar:
    for p in files:
        name=str(p.relative_to(ROOT));members.append({'path':name,'bytes':p.stat().st_size,'SHA256':sha(p)})
        tar.add(p,arcname=name,recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    for row in members:
        blob=tar.extractfile(row['path']).read()
        assert len(blob)==row['bytes'] and hashlib.sha256(blob).hexdigest()==row['SHA256']
loose=['deployment_audit.json','deployment_execution.json','live_mount_verification.json',
    'installed_launch_resolution.json','live_composition_review.json',
    'recorded_rgbd_direction_check.json','internal_registration_followup_proposal.json',
    'internal_tf_actual.json','factory_before.json','factory.json',
    'cube_task_real.canonical.before.yaml','cube_task_real.runtime.before.yaml',
    'cube_task_real.deployed.yaml','production_SHA_after.json','regression.log',
    'vendor_internal_tf_source_review.json','execution.json','sdk.json',
    'capture/summary.json','capture/observer.jsonl']
loose += [str(p.relative_to(ROOT)) for p in (ROOT/'capture/evidence').glob('*.png')]
loose += [str(p.relative_to(ROOT)) for p in ROOT.glob('*.py')]
published=[]
for name in loose:
    target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise FileExistsError(target)
    shutil.copyfile(ROOT/name,target);assert sha(ROOT/name)==sha(target)
    published.append({'path':name,'bytes':target.stat().st_size,'SHA256':sha(target)})
manifest={'source_runtime':str(ROOT),'raw_archive':{'path':archive.name,'bytes':archive.stat().st_size,
    'SHA256':sha(archive),'members':members,'all_members_SHA256_readback_verified':True},
    'loose_assets':published,'raw_images_or_depth_modified':False,'deleted_files':[]}
with (DEST/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2,allow_nan=False)
print(json.dumps({'original_files':len(members),'original_bytes':sum(r['bytes'] for r in members),
    'archive_bytes':archive.stat().st_size,'loose_assets':len(published),'all_members_verified':True}))
