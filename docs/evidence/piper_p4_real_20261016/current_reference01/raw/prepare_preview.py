"""Planning-only candidate data; NO production files/TF/TCP or motion writes."""
import hashlib,json,shutil
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent
geometry=ROOT/'geometry_review/report.json'
reference=ROOT/'geometry_review/clamped_rgb_hypothesis_v2.json'
data=json.loads(geometry.read_text());ref=json.loads(reference.read_text())
dest=ROOT/'center_preview';dest.mkdir(exist_ok=False)
candidate={'schema':'p4_cube_center_v1','target_kind':'cube_center','frame_id':'base_link',
 'center_base_m':data['center_base_median_m'],'cube_edge_m':.029,
 'grasp_center_tool_m':ref['all_branches'][0]['local_tool_candidate_m'],
 'provenance':'CURRENT_5_NATIVE_DEPTH_FACE_FITS; ISOLATED_PREVIEW_ONLY_NOT_HARDWARE_APPROVED',
 'grasp_reference_provenance':'pair02_clamped_RGB_annotated29mm_face_IPPE_branch0; CANDIDATE_NOT_TCP',
 'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [geometry,reference]},
 'assumptions':ref['limitations'],
 'hardware_adoption_approved':False}
with (dest/'frozen_target.yaml').open('x') as f:yaml.safe_dump(candidate,f,sort_keys=False)
old=Path('/home/johnwick/brain_robot_logs/p4_center_gentle_20261016.nR3gYk/preview_center_01/run_preview.py')
# Reuse exact original isolated runner, only select this current q snapshot.
text=old.read_text().replace('/mnt/hgfs/ub/docs/evidence/piper_p4_preparation_20261016/cube_static01/paired_retry/capture/observer.jsonl',str(ROOT/'capture/observer.jsonl'))
with (dest/'run_preview.py').open('x') as f:f.write(text)
print(json.dumps({'preview_target':candidate,'physical_motion':False},indent=2))
