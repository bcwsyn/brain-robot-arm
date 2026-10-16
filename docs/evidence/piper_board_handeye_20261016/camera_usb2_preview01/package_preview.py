"""Offline package of original RGB-D preview; retain zero-RGB failure."""
import ast,hashlib,json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/camera_usb2_preview01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
e=load(ROOT/'execution.json');ready=load(ROOT/'readiness.json')
frozen=load(REPO/'docs/evidence/piper_board_handeye_20261016/usb2_hold_retry01/production_SHA_after.json')
assert all(sha(Path(p))==v for p,v in frozen.items())
assert load(ROOT/'source_SHA_before.json')==load(ROOT/'source_SHA_after.json')
before=load(ROOT/'can_before.json')['after'];after=load(ROOT/'can_after.json')
assert before['tx']==after['tx'] and after['rx']>before['rx'] and e['all_owned_sources_exited']
OUT.mkdir(exist_ok=False)
put(OUT/'assessment.json',{'baseline_commit':'4e44326','operator_camera_restored':True,'inventory':load(ROOT/'camera_inventory.json'),
    'original_preview_exit_code':2,'error':e['error'],'saved_frames':e.get('saved_frames',0),
    'readiness_received':ready['received'],'readiness_ready':ready['ready'],
    'original_preview_camera_elapsed_s':e['camera_elapsed_s'],'CAN_before':before,'CAN_after':after,
    'motion_TX_increase':after['tx']-before['tx'],'all_owned_sources_exited':True,'production_six_SHA_unchanged':True,
    'established':'Both cameras enumerated on EHCI/480M and depth+camera_info+joint feedback were received. RGB source delivered zero frames in this bounded run.',
    'not_established':'USB2 incompatibility, sensor hardware fault, DDS fault, or hand-eye accuracy. Wrapper readiness TimeoutExpired is retained separately from actual zero-RGB counts.',
    'next':'Autonomously isolate original RGB/UVC startup and actual native capture format; no motion, new TF, thresholds, CAN recovery, host setting changes, or repeated same-condition full preview.',
    'new_calibration_reference':False,'old_board_candidates':'2/10 unchanged','Git_sync':'Local only; existing sync blocker unchanged.'})
put(OUT/'production_SHA_after.json',frozen)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:assert hashlib.sha256(t.extractfile(str(p.relative_to(ROOT))).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files],'all_member_SHA_readback_verified':True})
for p in files:
    if p.suffix in ('.py','.json'):shutil.copyfile(p,OUT/p.name)
print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size,'received':ready['received'],'TX_increase':after['tx']-before['tx']}))
