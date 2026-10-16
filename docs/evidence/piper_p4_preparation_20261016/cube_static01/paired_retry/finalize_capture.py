"""Offline data/TF/geometry audit and evidence package; no controller writes."""
import ast,hashlib,json,subprocess,tarfile,shutil
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent
FAIL=Path('/home/johnwick/brain_robot_logs/p4_cube_static_20261016.Fqi9XH')
REPO=Path('/mnt/hgfs/ub');DEST=REPO/'docs/evidence/piper_p4_preparation_20261016/cube_static01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
v=json.loads((ROOT/'target_observation.json').read_text());e=json.loads((ROOT/'target_execution.json').read_text());preview=json.loads((ROOT/'execution.json').read_text())
diag={int(stamp):{kv['key']:float(kv['value']) for kv in values['rgbd_observation']['status'][0]['values']}
      for stamp,values in v['stamped_observations'].items() if 'rgbd_observation' in values}
qualified=[w for w in v['world_points'] if diag[w['stamp_ns']]['qualified']==1]
xyz=np.asarray([w['point_base_m'] for w in qualified]);coverage=[d['coverage'] for d in diag.values()]
baseline=json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/internal_tf_pair01/production_SHA_after.json').read_text())
actual={p:sha(Path(p)) for p in baseline};assert actual==baseline
assert sha(Path('/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp'))=='e916a45172dd6fc413a9652b61a438fe20049eda73ea5fbfd26865f5a080969b'
assert sha(Path('/home/johnwick/ros2_ws/build/astra_camera/libastra_camera.so'))=='7dfeab6f3d61e27355abb5fdeebcde4d84f59c463ac54d23201deab8ac384911'
planning=json.loads((ROOT/'isolated_planning.json').read_text());fixed=json.loads((ROOT/'fixed_board_plane_review.json').read_text())
b=fixed['frames'][2];n=np.array(b['normal_base']);origin=np.array(b['T_base_board'])[:3,3];landings=[]
for candidate in planning['candidates']:
    p=candidate['last_descent_pose'];tip=np.array(p['origin'])+Rotation.from_quat(p['orientation']).apply([0,0,.1358])
    landings.append({'label':candidate['label'],'nominal_tip_base_m':tip.tolist(),
        'nominal_tip_height_above_local_board_m':float(n@(tip-origin)),
        'both_stages_complete':candidate['pregrasp']['fraction']==candidate['descent']['fraction']==1,
        'original_bounds_pass':candidate['pregrasp']['all_original_joint_bounds'] and candidate['descent']['all_original_joint_bounds'],
        'not_physical_clearance_or_capture_proof':True})
for w in v['world_points']:
    def mat(t):
        q=t['transform']['rotation'];p=t['transform']['translation'];M=np.eye(4)
        M[:3,:3]=Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix();M[:3,3]=[p[k] for k in ['x','y','z']];return M
    assert np.linalg.norm((mat(w['base_from_depth'])@np.r_[w['point_depth_m'],1])[:3]-w['point_base_m'])<1e-12
    assert np.linalg.norm((mat(w['color_from_depth'])@np.r_[w['point_depth_m'],1])[:3]-w['point_color_m'])<1e-12
for p in list(ROOT.glob('*.py'))+list(FAIL.glob('*.py')):ast.parse(p.read_text())
can=json.loads(subprocess.run(['ip','-json','-details','-statistics','link','show','can0'],capture_output=True,text=True,check=True).stdout)[0]
assert can['stats64']['tx']['packets']==e['can_before']['stats64']['tx']['packets']==e['can_after']['stats64']['tx']['packets']==42154
report={'baseline_commit':'822416a','read_only':True,'production_unchanged':True,
 'raw_pairs_saved':5,'exact_stamp_debug_assets':len(v['exact_stamp_debug_assets']),
 'stamped_detector_RGBD_observations':len(diag),'original_detector_qualified':len(qualified),
 'transformed_world_points':len(v['world_points']),'exact_stamp_TF_timeouts':v['transform_timeouts'],
 'qualified_detector_base_median_m':np.median(xyz,axis=0).tolist(),
 'qualified_detector_base_peak_to_peak_m':np.ptp(xyz,axis=0).tolist(),
 'RGBD_coverage_range':[min(coverage),max(coverage)],
 'point_reference':'Detector center ray at observed median surface depth, NOT independently measured cube center.',
 'fixed_board_diagnostic':{'seed':fixed['seed_snapshot'],
     'nominal_center_ray_base_median_m':fixed['nominal_14_5mm_center_ray_base_median_m'],
     'temporal_peak_to_peak_m':fixed['nominal_center_ray_peak_to_peak_m'],
     'detector_height_range_m':[min(r['detector_aim_height_m'] for r in fixed['frames']),max(r['detector_aim_height_m'] for r in fixed['frames'])],
     'not_absolute_reference_or_approved_control_target':True},
 'isolated_shared_geometry_landings':landings,
 'isolated_model_does_not_contain_live_table':True,
 'MoveIt_child_cleanup_exit_code':-11,
 'cleanup_note':'Planning parent and client returned 0, original MoveIt child crashed during SIGINT destructor; retained logs, not hidden as graceful exit or motion failure.',
 'SDK_full_window_rc':preview['SDK_full_window_rc'],'SDK_static_slice':preview['original_static_slice'],
 'last_feedback':json.loads((ROOT/'feedback.json').read_text())['actual_last_sample'],
 'CAN_final':can,'motion_commands_sent':False,'grasp_executed':False,
 'first_pair_capture_failed':True,'one_original_backend_RGB_only_case_passed':True,
 'alternative_backend_was_NOT_run':True,'production_backend_changed':False,
 'camera_root_cause_not_proven':True,'paired_retry_success':True,
 'next_change_requires_scope_approval':'P4 opt-in open-loop mode in original entry, using a reviewed RGB/board/nominal-size frozen point instead of the current low-support depth range; no production implementation or motion yet.'}
with (ROOT/'capture_assessment.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
members=[];archive=DEST/'session_originals.tar.gz'
if archive.exists():raise FileExistsError(archive)
with tarfile.open(archive,'w:gz') as tar:
    for label,folder in [('initial_failed',FAIL),('paired_retry',ROOT)]:
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.name=='shared_geometry' or p.suffix in ['.o','.so','.pyc']:continue
            name=label+'/'+str(p.relative_to(folder));members.append({'path':name,'bytes':p.stat().st_size,'SHA256':sha(p)})
            tar.add(p,arcname=name,recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    for item in members:assert hashlib.sha256(tar.extractfile(item['path']).read()).hexdigest()==item['SHA256']
assets=[]
for folder,label in [(FAIL,'initial_failed'),(ROOT,'paired_retry')]:
    for p in sorted(folder.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix not in ['.json','.jsonl','.png','.py']:continue
        name=label+'/'+str(p.relative_to(folder));target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():raise FileExistsError(target)
        shutil.copyfile(p,target);assert sha(target)==sha(p)
        assets.append({'path':name,'bytes':p.stat().st_size,'SHA256':sha(p)})
with (DEST/'manifest.json').open('x') as f:json.dump({'archive':{'path':archive.name,'bytes':archive.stat().st_size,
    'SHA256':sha(archive),'members':members,'all_SHA256_readback_verified':True},'loose_assets':assets,
    'raw_images_or_depth_modified':False,'deleted_files':[],'build_binary_excluded':str(ROOT/'shared_geometry')},f,indent=2)
print(json.dumps({'qualified':len(qualified),'pairs':5,'debug_assets':len(v['exact_stamp_debug_assets']),
 'landings':landings,'archive_members':len(members),'archive_bytes':archive.stat().st_size,'loose_assets':len(assets)},indent=2))
