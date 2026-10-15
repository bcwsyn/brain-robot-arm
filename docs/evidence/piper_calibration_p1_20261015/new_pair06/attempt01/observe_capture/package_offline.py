"""Offline-only fifth A closeout. No ROS initialization/device/control APIs.

Creates a new output under the runtime root, never overwrites source evidence.
Twenty face candidates are REVIEW inputs, not approved top/calibration points.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tarfile
import numpy as np

REPO=Path('/mnt/hgfs/ub')
ROOT=Path('/home/johnwick/brain_robot_logs/new_pair06_instrumented_A.5nuc8469')
SINGLE=Path('/home/johnwick/brain_robot_logs/new_pair06_rgb_stall.xq2gviz4')
DUAL=Path('/home/johnwick/brain_robot_logs/new_pair06_rgb_dual.4owrbozt')
OUT=ROOT/'publish'
TESTS=REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'
sys.path.insert(0,str(TESTS))
from export_calibration_bundle import verify_bundle
from review_calibration_capture import temporal_summary

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def manifest(folder):
    return [{'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='manifest.json']

OUT.mkdir(exist_ok=False)
session=ROOT/'session'; bundle=ROOT/'portable_all60'
exe=load(session/'execution.json'); cap=load(session/'capture/summary.json')
quality=load(ROOT/'quality/report.json'); original=load(bundle/'manifest.json')
verify_bundle(bundle,original)
assert exe['raw_acquisition_complete'] and exe['all_owned_sources_exited'] and exe['within_camera_budget']
assert cap['saved_frames']==60 and cap['stop_reason'] is None
assert quality['summary']['face_quality_candidates']==60
assert quality['summary']['good_top_frames']==0
assert load(session/'source_SHA_before.json')==load(session/'source_SHA_after.json')
for name,digest in load(session/'source_SHA_before.json').items():assert sha(Path(name))==digest
before=load(session/'can_before.json');after=load(session/'can_after.json')
assert after['rx']>before['after']['rx'] and after['tx']==before['before']['tx']
baseline=load(REPO/'docs/evidence/piper_calibration_p1_20261015/new_pair06/attempt01/ready_capture/assessment.json')
production={p:{'expected':v['actual'],'actual':sha(Path(p))} for p,v in baseline['production_SHA'].items()}
assert all(v['expected']==v['actual'] for v in production.values())
deployed=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
assert sha(deployed)==baseline['deployed_adapter_sha256']

rows=[json.loads(line) for line in (bundle/'capture/observer.jsonl').read_text().splitlines() if line]
assert len(rows)==60
q=np.array([r['q_rad'] for r in rows]);assert not np.ptp(q,axis=0).any()
ids=np.rint(np.linspace(0,59,20)).astype(int).tolist()
selected=[rows[i] for i in ids]
chosen={r['snapshot'] for r in selected}
assert len(chosen)==20
portable=OUT/'portable_review20';(portable/'capture/evidence').mkdir(parents=True)
for rel in ['sdk_samples.json','sdk_review.json','camera_factory_current.json','detector_config.yaml',
            'robot_task_config_snapshot.yaml','calibration.json']:
    shutil.copyfile(bundle/rel,portable/rel)
for row in selected:
    assert row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
    for image in row['images'].values():
        rel=Path(image['path'])
        assert not rel.is_absolute() and '..' not in rel.parts
        source=bundle/'capture'/rel
        assert sha(source)==image['sha256']
        shutil.copyfile(source,portable/'capture'/rel)
(portable/'capture/observer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in selected))
shutil.copyfile(bundle/'capture/summary.json',portable/'capture/source_capture_summary.json')
put(portable/'capture/summary.json',{'derived_subset_not_a_new_capture':True,'saved_frames':20,
    'source_saved_frames':60,'source_summary':'source_capture_summary.json',
    'source_summary_sha256':sha(bundle/'capture/summary.json'),
    'source_zero_based_indices':ids,'qualification':'face review only; 0 accepted good-top frames'})
review=load(bundle/'depth_review.json')
review['frames']=[f for f in review['frames'] if f['snapshot'] in chosen]
review['temporal']=temporal_summary(review['frames'])
review['high_support_temporal']=temporal_summary(review['frames'])
review['analysis_subset']={'source_count':60,'selected_count':20,'fit_approved':False,
    'selection':'equally spaced recorded indices; all 60 had original complete-face candidates',
    'sdk_source':'Immutable grip B checkpoint1a2e633, not newly sampled observation SDK; A feedback is in each observer row'}
put(portable/'depth_review.json',review)
m=dict(original);m.update(sample_id='new_pair06_attempt01_review20',files=manifest(portable),
    selection_profile='20 complete-face candidates for review, not approved good-top calibration points',
    physical_pair_record_present=False,source_frame_count=60,selected_frame_count=20,
    original_good_top_frames=0,calibration_fit_performed=False)
m['file_count']=len(m['files']);m['total_bytes']=sum(r['bytes'] for r in m['files'])
put(portable/'manifest.json',m);verify_bundle(portable,m)

shutil.copytree(ROOT/'quality',OUT/'quality_all60')
for name in ['execution.json','feedback.json','readiness.json','can_before.json','can_after.json','factory.json']:
    shutil.copyfile(session/name,OUT/name)
probes=OUT/'probes';probes.mkdir()
for label,path in [('RGB_only',SINGLE),('RGB_depth',DUAL)]:
    folder=probes/label;folder.mkdir()
    for name in ['color.log','report.json']:
        shutil.copyfile(path/name,folder/name)
    if label=='RGB_depth':
        image=sorted((path/'images').glob('*_rgb.png'))[0]
        shutil.copyfile(image,folder/'original_first_rgb.png')
sources=OUT/'executed_probes';sources.mkdir()
for name in ['piper_rgb_stall_probe.py','piper_rgb_dual_probe.py','piper_pair06_capture_probe.py']:
    shutil.copyfile(Path('/tmp')/name,sources/name)
entries=[]
with tarfile.open(OUT/'all_raw_closed.tar.gz','w:gz') as archive:
    for label,path in [('formal_A',session),('RGB_only',SINGLE),('RGB_depth',DUAL)]:
        for p in sorted(path.rglob('*')):
            if not p.is_file():continue
            assert not p.is_symlink()
            rel=f'{label}/{p.relative_to(path).as_posix()}'
            archive.add(p,arcname=rel,recursive=False)
            entries.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size})
with tarfile.open(OUT/'all_raw_closed.tar.gz') as archive:
    for row in entries:
        assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest()==row['sha256']
put(OUT/'raw_manifest.json',{'archive_sha256':sha(OUT/'all_raw_closed.tar.gz'),'files':entries,
    'all_files_SHA_verified':True,'raw_source_files_deleted':False,
    'restore_note':'formal_A/capture contains all60 original pairs; portable_review20 is derived, do not count it as a separate capture'})
quality_selected=[f for f in quality['frames'] if f['snapshot'] in chosen]
assert len(quality_selected)==20 and all(f['face_quality_candidate'] for f in quality_selected)
put(OUT/'selected_for_review.json',{'selected_count':20,'source_count':60,'indices_zero_based':ids,
    'source_snapshot_ids':sorted(chosen),'raw_images_unchanged':True,'complete_face_candidates_selected':20,
    'original_good_top_frames_selected':0,'selected_for_calibration_fit':False,
    'automatic_annulus_assumption_failed':'Cube on elevated support, not directly on surrounding table',
    'all_original_acceptance_thresholds_unchanged':True})
assessment={'pair_id':'new_pair06','B_checkpoint':'1a2e633','operator_same_point_confirmation_already_recorded':True,
    'user_latest_approved_autonomous_collection_scope_until_sixth_placement':True,
    'new_A_raw_frames':60,'selected_complete_face_review_frames':20,'original_good_top_frames':0,
    'pair_raw_A_B_present':True,'formal_complete_pairs_unchanged':1,'calibration_pair_approved':False,
    'selected_review_is_not_twenty_approved_top_samples':True,
    'source_capture_elapsed_s':cap['elapsed_s'],'camera_elapsed_including_cleanup_s':exe['camera_elapsed_s_including_cleanup'],
    'q_spread_rad':np.ptp(q,axis=0).tolist(),'actual_observation_q_rad':q[0].tolist(),
    'native_surface_z_m_range':[min(f['surface_z_m'] for f in load(ROOT/'review.json')['frames']),
                                 max(f['surface_z_m'] for f in load(ROOT/'review.json')['frames'])],
    'dominant_plane_inlier_range':[min(f['plane_inliers'] for f in quality['frames']),max(f['plane_inliers'] for f in quality['frames'])],
    'original_top_errors':sorted({f['top_error'] for f in quality['frames']}),
    'RGB_only_probe':load(SINGLE/'report.json'),'RGB_depth_probe':load(DUAL/'report.json'),
    'RGB_stall_not_reproduced_in_these_bounded_conditions':True,'RGB_stall_root_cause_fixed':False,
    'backend_QoS_DDS_camera_or_production_code_changed':False,'gdb_attach_performed':False,
    'no_motion_enable_disable_gripper_reset_CAN_recovery':True,'read_only_CAN_TX_delta':after['tx']-before['before']['tx'],
    'all_owned_sources_exited':exe['all_owned_sources_exited'],'production_SHA':production,
    'deployed_adapter_sha256':sha(deployed),'candidate_adapter_deployed':False,
    'fresh_factory_serial':load(session/'factory.json')['get_device_info']['info']['serial_number'],
    'raw_archive_files_SHA_verified':len(entries),'review20_assets_SHA_verified':len(m['files']),
    'raw_data_deleted':False,'GitHub_pushed':False,
    'next':'Request sixth physical placement new_pair07 (held out), preview at current static observation before manual grip. Do not deploy TF or run approach/grasp.'}
put(OUT/'assessment.json',assessment)
shutil.copyfile('/tmp/pair06_rgb_recovery_tests.xml',OUT/'junit.xml')
shutil.copyfile(Path(__file__),OUT/'package_offline.py')
print(json.dumps({k:assessment[k] for k in ['new_A_raw_frames','selected_complete_face_review_frames',
    'original_good_top_frames','source_capture_elapsed_s','dominant_plane_inlier_range',
    'read_only_CAN_TX_delta','raw_archive_files_SHA_verified','review20_assets_SHA_verified']}))
