"""Preserve this bounded static recovery check, not a new calibrated sample set."""
import ast,hashlib,json,shutil,subprocess,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_static01'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
report={'epoch':time.time(),'commands':[]}
for argv in [['ip','-json','-details','-statistics','link','show','can0'],['lsusb','-t'],
             ['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm']]:
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    report['commands'].append({'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
ps=subprocess.run(['ps','-eo','pid,comm,args'],capture_output=True,text=True,timeout=5)
needles=['cam2image','astra_camera_node','component_container','piper_ctrl_single_node',
         'piper_jog_adapter.py','visual_search_controller','grasp_lift_executor','calibration_readonly_feedback.py']
report['remaining_sources']=[l for l in ps.stdout.splitlines() if any(n in l for n in needles)]
assert not report['remaining_sources']
state=json.loads(report['commands'][0]['stdout'])[0]
assert state['stats64']['tx']['packets']==0
save(ROOT/'end_status.json',report)
frozen=load(ROOT/'production_SHA_before.json')
assert frozen==load(ROOT/'production_SHA_after.json')
assert all(sha(Path(p))==s for p,s in frozen.items())
offline=load(ROOT/'offline_assessment.json');e=load(ROOT/'execution.json')
assert e['saved_frames']==5 and e['all_owned_sources_exited'] and e['error'] is None
assert load(ROOT/'metadata_followup/execution.json')['factory_rc']==0
OUT.mkdir(exist_ok=False)
assessment={'baseline_commit':'a335162','operator_quote':'我已恢复',
  'scope':'Restored USB3 setting static RGB-D and receive-only CAN comparison; no robot control',
  'actual_paths':{'CAN':'3-2:1.0 / xhci_hcd / 12M','depth':'3-4.1 / xhci_hcd / 480M','RGB':'3-4.2 / xhci_hcd / 480M'},
  'preview_RC':0,'saved_RGBD_pairs':5,'source_camera_elapsed_s':e['camera_elapsed_s'],
  'SDK_full_window_rc':e['SDK_full_window_rc'],'original_static_slice':e['original_static_slice'],
  'actual_last_feedback':load(ROOT/'feedback.json')['actual_last_sample'],
  'CAN':offline['CAN_window'],'end_CAN_stats':state['stats64'],
  'initial_factory_rc':2,'initial_factory_error':load(ROOT/'factory.json')['error'],
  'factory_followup_rc':0,'factory_scope':'Separate original-depth-only getter session; service graph captured, no production edit or RGB reopen',
  'preview_exit_zero_does_not_hide_auxiliary_failures':True,
  'offline_grid':offline['visible_grid'],'interior_points':len(offline['fixed_interior_IDs']),
  'PnP_best_RMS_px':[min(p['refined_rms_px'] for p in f['pose_candidates']) for f in offline['frames']],
  'offline_initial_invocation_error':'First offline audit omitted PYTHONNOUSERSITE=1 and failed on user NumPy2/OpenCV ABI before processing; rerun with existing environment succeeded. No dependency/production changes.',
  'all_owned_sources_exited':True,'production_six_SHA_unchanged':True,'robot_TX_increase':0,
  'established':'Original RGB-D capture succeeds after restoring xHCI, unlike prior EHCI zero-frame probes; simultaneous passive CAN received during this bounded static window.',
  'not_established':offline['not_established'],
  'continuous_board_session_reference':False,'hand_eye_fit_performed':False,'old_board_pose_count':'2/10 retained separately',
  'next':'Use these actual pixels/K/feedback to prepare the existing approved 9fit+1heldout route in a new continuous camera session; do not reuse these sparse stopped-preview IDs or old sample IDs. Static CAN pass is not a permanent/active-control fix. No more USB2 toggles or Windows Camera test needed now.',
  'Git':'Local commit only; previous sync/history publication blocker unchanged'}
save(OUT/'assessment.json',assessment)
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text())
    if p.suffix=='.json':load(p)
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in files:t.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for p in files:
        member=t.extractfile(str(p.relative_to(ROOT)))
        assert hashlib.sha256(member.read()).hexdigest()==sha(p)
save(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),
    'all_member_SHA_readback_verified':True,'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'SHA256':sha(p)} for p in files]})
for p in files:
    if p.suffix in ('.py','.json','.png') or p.name=='observer.jsonl':
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size,'output':str(OUT),'assessment':assessment},ensure_ascii=False))
