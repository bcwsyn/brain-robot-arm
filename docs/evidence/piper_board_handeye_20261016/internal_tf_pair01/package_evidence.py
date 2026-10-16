"""Archive static-only evidence, excluding local binaries/build artifacts."""
import hashlib,json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/internal_tf_pair01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and 'compiled_math' not in p.parts
    and '__pycache__' not in p.parts and p.suffix not in ['.so','.o','.pyc'])
archive=DEST/'static_originals.tar.gz'
members=[]
if archive.exists():raise FileExistsError(archive)
with tarfile.open(archive,'w:gz') as tar:
    for p in files:
        name=str(p.relative_to(ROOT));members.append({'path':name,'bytes':p.stat().st_size,'SHA256':sha(p)})
        tar.add(p,arcname=name,recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    for row in members:
        blob=tar.extractfile(row['path']).read()
        assert len(blob)==row['bytes'] and hashlib.sha256(blob).hexdigest()==row['SHA256']
names=[str(p.relative_to(ROOT)) for p in files if p.suffix in ['.json','.jsonl','.yaml','.py','.cpp','.png','.txt']]
published=[]
for name in names:
    target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise FileExistsError(target)
    shutil.copyfile(ROOT/name,target);assert sha(ROOT/name)==sha(target)
    published.append({'path':name,'bytes':target.stat().st_size,'SHA256':sha(target)})
manifest={'source_runtime':str(ROOT),'archive':{'path':archive.name,'bytes':archive.stat().st_size,
    'SHA256':sha(archive),'members':members,'all_members_SHA256_readback_verified':True},
    'loose_assets':published,'excluded_local_only':[
        {'path':str(ROOT/'libastra_camera.before.so'),'SHA256':sha(ROOT/'libastra_camera.before.so'),
         'reason':'Local rollback binary; build artifacts must not be committed'},
        {'path':str(ROOT/'compiled_math'),'reason':'Generated offline test executable/build scratch'}],
    'raw_images_modified':False,'depth_holes_filled':False,'deleted_files':[]}
with (DEST/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2,allow_nan=False)
print(json.dumps({'original_files':len(members),'original_bytes':sum(r['bytes'] for r in members),
    'archive_bytes':archive.stat().st_size,'loose_assets':len(published),'all_members_verified':True}))
