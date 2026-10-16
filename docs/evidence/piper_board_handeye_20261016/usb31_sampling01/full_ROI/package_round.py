"""Offline portable archive of this round, bounded pieces under 32MiB raw.

No device operations or deletion. Full guest kernel logs remain private home;
only scoped USB/CAN deltas and their source hashes are exported.
"""
import ast,hashlib,json,shutil,tarfile,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01'
RUNS=[('wrapper_preflight',Path('/home/johnwick/brain_robot_logs/board_usb31_sampling_20261016.9ECrHF')),
 ('full30',Path('/home/johnwick/brain_robot_logs/board_usb31_original_20261016.G2lzeV')),
 ('return',Path('/home/johnwick/brain_robot_logs/board_return_20261016.8NDic8')),
 ('seed_only',Path('/home/johnwick/brain_robot_logs/board_safe_seed_20261016.7Zjm2l')),
 ('full_ROI',ROOT)]
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
baseline=load(REPO/'docs/evidence/piper_board_handeye_20261016/usb31_static01/production_SHA_after.json')
assert all(sha(Path(p))==h for p,h in baseline.items())
summary=[];entries=[];private=[]
for label,root in RUNS:
    inv=load(root/'invocation.json');e=load(root/'execution.json') if (root/'execution.json').exists() else None
    assert inv['all_outer_sources_exited']
    if e is not None:
        assert e['all_owned_sources_exited']
        assert load(root/'production_SHA_before.json')==load(root/'production_SHA_after.json')==baseline
    before=load(root/'interface_initial.json');after=load(root/'interface_end.json')
    b=json.loads(before['stdout'])[0];a=json.loads(after['stdout'])[0]
    ts=[float(l.split(')',1)[0][1:]) for l in (root/'candump.log').read_text().splitlines() if l.startswith('(')]
    gaps=np.diff(ts)
    kernel_b=(root/'kernel_before.txt').read_text();kernel_a=(root/'kernel_after.txt').read_text()
    oldlines=set(kernel_b.splitlines())
    delta=[l for l in kernel_a.splitlines() if l not in oldlines and any(s in l.lower() for s in ['usb','xhci','gs_usb','can0','uvc'])]
    save(root/'kernel_scoped_delta.json',{'guest_kernel_source_SHA_before':sha(root/'kernel_before.txt'),
        'guest_kernel_source_SHA_after':sha(root/'kernel_after.txt'),'new_USB_CAN_lines':delta,
        'complete_originals_retained_private_at_runtime':True})
    summary.append({'label':label,'root':str(root),'outer':inv,
       'sampler_error':e.get('error') if e else None,'completed_9fit_1heldout':e.get('completed_9fit_1heldout',False) if e else False,
       'sample_labels':[s['label'] for s in e.get('samples',[])] if e else [],
       'raw_RGB_frames':e.get('raw_RGB_frames',0) if e else 0,
       'final_received_feedback':e.get('final_received_feedback') if e else inv.get('last_fresh_SDK'),
       'CAN':{'recorded_frames':len(ts),'span_s':ts[-1]-ts[0] if ts else 0,
              'max_timestamp_gap_s':float(gaps.max()) if len(gaps) else None,
              'gaps_over_half_second':int((gaps>.5).sum()),'initial_stats':b['stats64'],'end_stats':a['stats64']},
       'kernel_new_USB_CAN_lines':delta,'bag_audit':load(root/'bag_audit.json') if (root/'bag_audit.json').exists() else None})
    for p in sorted(root.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(root)
        if p.name in ['kernel_before.txt','kernel_after.txt']:
            private.append({'runtime_path':str(p),'bytes':p.stat().st_size,'SHA256':sha(p),'reason':'Full unrelated guest kernel history excluded; scoped delta exported'})
            continue
        if '__pycache__' in rel.parts:continue
        if p.suffix=='.py':ast.parse(p.read_text())
        if p.suffix=='.json':load(p)
        entries.append({'source':p,'path':label+'/'+str(rel),'bytes':p.stat().st_size,'SHA256':sha(p)})
OUT.mkdir(exist_ok=False)
parts=[];batch=[];size=0
def archive(items):
    dest=OUT/f'runtime_originals_{len(parts)+1:02d}.tar.gz'
    with tarfile.open(dest,'w:gz') as t:
        for item in items:t.add(item['source'],arcname=item['path'],recursive=False)
    with tarfile.open(dest,'r:gz') as t:
        for item in items:assert hashlib.sha256(t.extractfile(item['path']).read()).hexdigest()==item['SHA256']
    parts.append({'path':dest.name,'bytes':dest.stat().st_size,'SHA256':sha(dest),'files':[{'path':i['path'],'bytes':i['bytes'],'SHA256':i['SHA256']} for i in items]})
for item in entries:
    if batch and size+item['bytes']>32<<20:archive(batch);batch=[];size=0
    batch.append(item);size+=item['bytes']
if batch:archive(batch)
e=load(ROOT/'execution.json');fit=load(ROOT/'handeye_fit_report.json') if (ROOT/'handeye_fit_report.json').exists() else None
save(OUT/'assessment.json',{'baseline_commit':'8744c14','runs':summary,
 'new_continuous_session_complete':e.get('completed_9fit_1heldout',False),
 'new_session_samples':len(e['samples']),'new_session_fit':sum(s['role']=='fit' for s in e['samples']),
 'new_session_heldout':sum(s['role']=='heldout' for s in e['samples']),
 'old_session_7fit_not_pooled':True,'prior_2fit_not_pooled':True,
 'handeye_fit_performed':fit is not None,
 'heldout_10mm_corner_max_consistency_pass':fit['heldout_10mm_corner_max_consistency_pass'] if fit else None,
 'production_TF_deployed':False,'production_six_SHA_unchanged':True,
 'gripper_or_hardware_disable_or_ResetPiper':False,'GitHub_pushed':False,
 'Git_sync_blocker':'Previous shared-main divergence/history publication review unchanged',
 'final_state':load(ROOT/'final_status.json') if (ROOT/'final_status.json').exists() else None,
 'test_result':load(ROOT/'offline_test_result.json') if (ROOT/'offline_test_result.json').exists() else None})
save(OUT/'runtime_manifest.json',{'archives':parts,'all_member_SHA_readback_verified':True,'raw_deleted':False,
 'private_original_kernel_logs':private,'total_exported_original_files':len(entries)})
save(OUT/'production_SHA_after.json',baseline)
for label,root in RUNS:
    for p in sorted(root.iterdir()):
        if p.is_file() and p.suffix in ('.py','.json'):
            dest=OUT/label/p.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
    if e is not None:
        for sample in (load(root/'execution.json').get('samples',[]) if (root/'execution.json').exists() else []):
            for row in sample['frames']:
                p=root/row['image_path'];dest=OUT/label/row['image_path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for name in ['failed_rgb.png','tracking_failure_overlay.png']:
        if (root/name).exists():shutil.copyfile(root/name,OUT/label/name)
print(json.dumps({'output':str(OUT),'files':len(entries),'archives':len(parts),'archive_bytes':sum(p['bytes'] for p in parts),'new_session_samples':len(e['samples']),'fit_available':fit is not None,'complete':e.get('completed_9fit_1heldout',False)}))
