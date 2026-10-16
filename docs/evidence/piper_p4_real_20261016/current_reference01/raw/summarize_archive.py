"""Save current audit and portable raw assets; no hardware/control or binaries."""
import hashlib,json,shutil,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
DEST=REPO/'docs/evidence/piper_p4_real_20261016/current_reference01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
g=json.loads((ROOT/'geometry_review/report.json').read_text())
capture=json.loads((ROOT/'capture/summary.json').read_text())
exec_report=json.loads((ROOT/'readonly_execution.json').read_text())
preview=json.loads((ROOT/'center_preview/preview_result.json').read_text())
sdk=json.loads((ROOT/'sdk.json').read_text())
feedback=json.loads((ROOT/'feedback.json').read_text())
centers=np.array([f['candidate_center_base_m'] for f in g['frames']])
refs=json.loads((ROOT/'geometry_review/clamped_rgb_hypothesis_v2.json').read_text())
samples=np.array([r['center_color_m'] for r in refs['sensitivity_trials'] if r['branch']==0])
assert capture['saved_frames']==5 and len(centers)==5
assert preview['passed'] and all(preview['commands'][k]==0 for k in ['arm','gripper','joint_commands'])
assert exec_report['production_SHA_unchanged']
assert exec_report['can_before']['stats64']['tx']['packets']==exec_report['can_after']['stats64']['tx']['packets']
files=exec_report['source_SHA_before']
assert all(sha(Path(p))==h for p,h in files.items())
summary={'baseline':'3e65b08','epoch':time.time(),'physical_motion_or_gripper_commands':0,
 'production_source_config_TF_TCP_or_limits_changed':False,
 'current_capture':{'frames':5,'stamp_paired_not_hardware_sync':True,
  'color_resolution':[320,240],'depth_resolution':[640,400],'depth_encoding':'16UC1 mm; zeros preserved',
  'coverage':[f['color_pixel_coverage'] for f in g['frames']],
  'rgb_stamps_ns':[f['stamps_ns']['rgb'] for f in g['frames']],
  'center_base_median_m':g['center_base_median_m'],
  'center_temporal_peak_to_peak_mm':(np.ptp(centers,axis=0)*1000).tolist(),
  'face_plane_RMS_mm':[f['candidate_by_nominal_edge_mm']['29']['plane_rms_m']*1000 for f in g['frames']],
  'center_vs_face':'inward along measured normal by nominal14.5mm, not optical-z guess'},
 'last_actual_feedback':feedback['actual_last_sample'],
 'SDK_full_window_rc':2,'SDK_quality':sdk['quality'],
 'SDK_original_velocity_outliers':[{'index':i,'speed_millirad_s':r['speed_millirad_s']} for i,r in enumerate(sdk['samples']) if max(map(abs,r['speed_millirad_s']))>1],
 'SDK_strict_static_gate_not_passed_NOT_overridden':True,
 'camera_capture_static_q_check_separate':True,
 'CAN':{k:[exec_report['can_before']['stats64'][k]['packets'],exec_report['can_after']['stats64'][k]['packets']] for k in ['rx','tx']},
 'old_clamped_RGB_reference':{'nominal_edge_mm':29,'hypothesis_only_not_adopted':True,
  'pair07_used_for_fit_or_selection':False,'both_PnP_branches_preserved':True,
  'branch0_rms_px':refs['all_branches'][0]['refined_rms_px'],
  'branch0_center_color_m':refs['all_branches'][0]['cube_center_color_candidate_m'],
  'branch0_local_tool_m':refs['all_branches'][0]['local_tool_candidate_m'],
  'branch0_center_pixel':refs['all_branches'][0]['candidate_center_pixel'],
  'branch0_2px_annotation_sensitivity_ptp_mm':(np.ptp(samples,axis=0)*1000).tolist(),
  'does_not_bound_old_mount_identity_systematic_error':True},
 'isolated_planning':preview,'no_hardware_adoption':True,
 'remaining':'Current center has native support. Actual jaw model/X mismatch remains; RGB-only local reference is an annotated hypothesis, needs approved limited validation, not a verified TCP.',
 'next_proposed_scope_NOT_IMPLEMENTED':'Original P4 executor optional gripper-only test endpoint reusing GentleCloseGripper, no arm trajectory; after independent validation, original P4 current-center/reference candidate real attempt.',
 'git':'local only; prior main divergence and history review unresolved'}
with (ROOT/'current_summary.json').open('x') as f:json.dump(summary,f,indent=2,allow_nan=False)
DEST.mkdir(exist_ok=False);manifest=[]
for src in sorted(ROOT.rglob('*')):
    if not src.is_file() or '__pycache__' in src.parts:continue
    assert src.read_bytes()[:4]!=b'\x7fELF'
    rel=src.relative_to(ROOT);dst=DEST/'raw'/rel
    if dst.suffix=='.log':dst=dst.with_suffix('.txt')
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);assert sha(src)==sha(dst)
    manifest.append({'source':str(src),'archive':str(dst.relative_to(DEST)),'sha256':sha(dst),'bytes':dst.stat().st_size})
with (DEST/'manifest.json').open('x') as f:json.dump({'files':manifest,'unchanged_original_bytes':True,'logs_extension_only_changed_to_txt':True},f,indent=2)
print(json.dumps({'archive':str(DEST),'files':len(manifest),'bytes':sum(r['bytes'] for r in manifest),'summary':summary},indent=2))
