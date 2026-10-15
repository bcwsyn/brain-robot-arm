"""Read primary quality reports from all six placements; no devices or fitting."""
from pathlib import Path
import hashlib,json,sys
REPO=Path('/mnt/hgfs/ub')
BASE=Path('docs/evidence/piper_calibration_p1_20261015')
sources=[
 ('new_pair02','fit','attempt02/observe_capture/p0_report.json'),
 ('new_pair03','fit','attempt02/observe_capture/p0_report.json'),
 ('new_pair04','fit','attempt01/observe_after_reconnect/p0_report.json'),
 ('new_pair05','fit','attempt01/observe_capture/p0_report.json'),
 ('new_pair06','fit','attempt01/observe_capture/quality_all60/report.json'),
 ('new_pair07','held_out','attempt01/release_observe_capture/quality_all60/report.json')]
out=Path(sys.argv[1])
if out.exists():raise FileExistsError('Refuse overwriting registry evidence')
rows=[]
for pair,role,tail in sources:
 rel=BASE/pair/tail;p=REPO/rel;d=json.loads(p.read_text());s=d['summary']
 rows.append({'pair_id':pair,'role':role,'source':rel.as_posix(),
  'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
  'primary_A_raw_frames':s['frames'],'complete_face_candidates':s['face_quality_candidates'],
  'original_good_top_frames':s['good_top_frames'],'twenty_good_frames_met':s['twenty_good_frames_met'],
  'formal_calibration_pair_approved':s['formal_calibration_pair'],
  'top_identity_witness_review_still_required':s['top_witness_review_required']})
report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'fit_performed':False,
 'raw_placements_with_A_and_B':6,'primary_A_raw_frames_total':sum(r['primary_A_raw_frames'] for r in rows),
 'placements_meeting_original_top_image_quality':sum(r['twenty_good_frames_met'] for r in rows),
 'formal_calibration_pair_approvals':sum(r['formal_calibration_pair_approved'] for r in rows),
 'held_out_id_fixed':'new_pair07','rows':rows,
 'calibration_adoption_or_subcentimeter_accuracy_verified':False,
 'conclusion':'Six placements have raw records, not six qualified calibration pairs. Only one meets original top-image threshold, and that report still requires witness/reference review. Do not fit missing centers, deploy TF or silently lower800/20.'}
out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
print(json.dumps({k:report[k] for k in ['raw_placements_with_A_and_B','primary_A_raw_frames_total',
 'placements_meeting_original_top_image_quality','formal_calibration_pair_approvals']}))
