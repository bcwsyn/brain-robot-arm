"""Preserve every stage 5 simulation session and validation record with hashes."""
from pathlib import Path
import hashlib
import json
import tarfile

ws=Path(__file__).resolve().parents[2]
published=Path('/tmp/piper-stage5-publish-20261014/simulation_cup_grasp')
dest=ws/'validation/cup_grasp/archives'
if dest.exists():raise RuntimeError('Archive destination exists; preserve it')
dest.mkdir()
files={}
for label,base in [('local',ws),('publication',published)]:
 for session in sorted((base/'log/visual_sim').glob('cup-*')):
  for p in session.rglob('*'):
   if p.is_file() and not p.is_symlink():files[f'sessions/{label}/{session.name}/{p.relative_to(session)}']=p
regression=json.loads((ws/'validation/cup_grasp/final_regression_and_publication_smoke.json').read_text())
for trial in regression:
 if trial['name'] not in ('ball','cylinder'):continue
 session=Path(trial['session'])
 for p in session.rglob('*'):
  if p.is_file() and not p.is_symlink():files[f'sessions/regression/{session.name}/{p.relative_to(session)}']=p
for p in (ws/'validation/cup_grasp').rglob('*'):
 if p.is_file() and not p.is_symlink() and dest not in p.parents:
  files['validation/'+str(p.relative_to(ws/'validation/cup_grasp'))]=p
spool=ws/'artifacts/cup_grasp_backups'
spool.mkdir(parents=True,exist_ok=True)
archive=spool/'all_sessions_and_validation.tar.gz'
if archive.exists():raise RuntimeError('Backup exists')
manifest=dict(version=1,description='All stage 5 development/failed/frozen/GUI/publication sessions and validation evidence',files_sha256={},parts=[])
with tarfile.open(archive,'w:gz',compresslevel=6) as target:
 for name,p in sorted(files.items()):
  manifest['files_sha256'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
  target.add(p,arcname=name,recursive=False)
manifest['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
with archive.open('rb') as stream:
 index=0
 while data:=stream.read(45*1024*1024):
  name=f'all_sessions_and_validation.tar.gz.part{index:03d}'
  (dest/name).write_bytes(data)
  manifest['parts'].append(dict(file=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()));index+=1
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(dest/'SHA256SUMS').write_text(''.join(part['sha256']+'  '+part['file']+'\n' for part in manifest['parts']))
print('Archived',len(files),'files,',archive.stat().st_size,'bytes,',len(manifest['parts']),'parts')
