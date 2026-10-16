"""Offline audit of actual USB3-restored images/CAN, not hand-eye fitting."""
import ast,hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
TOOLS=REPO/'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'
sys.path.insert(0,str(TOOLS))
from partial_board_tracking_check import propagate
from board_pose_offline import grid,poses
def read(p):return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False)
execution=read(ROOT/'execution.json');meta=read(ROOT/'metadata_followup/factory.json')
old=read(REPO/'docs/evidence/piper_calibration_p1_20261015/board_observe/portable/calibration.json')
assert meta['get_device_info']['info']['serial_number']==old['serial']=='CC1365304DG'
assert meta['get_camera_info']['info']['k']==old['color_factory']['K']
assert meta['get_camera_info']['info']['d']==old['color_factory']['CameraInfo_D']
before=read(ROOT/'can_active.json');after=read(ROOT/'can_final.json')
assert before['stats64']['tx']['packets']==after['stats64']['tx']['packets']==0
assert read(ROOT/'production_SHA_before.json')==read(ROOT/'production_SHA_after.json')
assert read(ROOT/'source_SHA_before.json')==read(ROOT/'source_SHA_after.json')
assert execution['all_owned_sources_exited'] and execution['error'] is None
rows=[json.loads(l) for l in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
assert len(rows)==5
frames=[];previous=None;points=None;first_points=None
K=np.diag([*old['color_capture']['existing_detector_resize_factors'],1.])@np.asarray(meta['get_camera_info']['info']['k']).reshape(3,3)
D=np.asarray(meta['get_camera_info']['info']['d'])
report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'robot_moved':False,
        'new_static_preview_not_continuous_sampling_reference':True,'board_fit_pose_count':0,
        'factory_followup_matches_archived_color_K_D_and_serial':True,
        'K_D_scope':'Approved old endpoint resize/zero-D baseline; not newly calibrated',
        'K':K.tolist(),'D':D.tolist(),'square_m_user_reported':.032,'frames':frames}
for row in rows:
    for label,img in row['images'].items():
        p=Path(img['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==img['sha256']
    gray=cv2.imread(row['images']['rgb']['path'],cv2.IMREAD_GRAYSCALE)
    dep=cv2.imread(row['images']['depth']['path'],cv2.IMREAD_UNCHANGED)
    assert gray.shape==(240,320) and dep.shape==(400,640) and dep.dtype==np.uint16
    if previous is None:
        found,corners,meta_grid=cv2.findChessboardCornersSBWithMeta(gray,(3,3),flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_LARGER)
        if not found:raise RuntimeError('No actual seed in restored preview')
        c,r=meta_grid.shape[1],meta_grid.shape[0]
        ids=[y*c+x for y in range(1,r-1) for x in range(1,c-1)]
        points=corners.reshape(-1,2)[ids].astype(np.float32);first_points=points.copy()
        objects=grid((c,r))[ids]
        report.update(visible_grid=[c,r],fixed_interior_IDs=ids,object_points_m=objects.tolist(),
                      board_origin='Arbitrary first visible subgrid, not global or prior-session IDs')
        err=0.
        overlay=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        for i,xy in zip(ids,points):
            cv2.circle(overlay,tuple(np.rint(xy).astype(int)),2,(0,255,0),1)
        cv2.imwrite(str(ROOT/'board_seed_overlay.png'),overlay)
    else:
        tracks=propagate(previous,gray,points)
        assert all(t['forward_status'] and t['reverse_status'] and t['inside_image'] for t in tracks)
        err=max(t['forward_backward_error_px'] for t in tracks)
        assert err<=.5
        points=np.asarray([t['position_px'] for t in tracks],np.float32)
    frames.append({'snapshot':row['snapshot'],'stamps_ns':row['stamps_ns'],'q_driver_rad':row['q_rad'],
                   'point_count':len(points),'fixed_points_px':points.tolist(),
                   'max_forward_reverse_error_px':err,'pose_candidates':poses(objects,points,K,D)})
    previous=gray
times=[]
for line in (ROOT/'candump.log').read_text().splitlines():
    if line.startswith('('):times.append(float(line.split(')',1)[0][1:]))
assert len(times)>1000
t=np.asarray(times);gaps=np.diff(t)
q=np.asarray([r['q_rad'] for r in rows])
report.update(CAN_window={'frames':len(t),'span_s':float(t[-1]-t[0]),'max_timestamp_gap_s':float(gaps.max()),
                         'gaps_over_half_second':int((gaps>.5).sum()),
                         'clock_scope':'candump receive timestamps; not hardware/per-motor freshness',
                         'before_stats':before['stats64'],'after_stats':after['stats64'],
                         'drop_counter_note':'rx.dropped preserved, including intervals without receive sockets; not assumed physical loss or ignored'},
              saved_q_peak_to_peak_rad=np.ptp(q,axis=0).tolist())
report['all_saved_frames_max_stamp_span_s']=max(r['stamp_span_s'] for r in rows)
report['max_static_corner_displacement_px']=float(np.linalg.norm(points-first_points,axis=1).max())
report['not_established']=['Permanent CAN fix or stability under control commands',
    'USB3.1 hardware requirement; restored xHCI success only',
    'Hand-eye calibration, printed-board flatness, or mount accuracy',
    'Continuous board identity across stopped camera sessions']
save(ROOT/'offline_assessment.json',report)
print(json.dumps({'static_RGBD_pairs':len(rows),'interior_points':len(points),'raw_CAN':report['CAN_window'],
                  'PnP_RMS_px':[min(p['refined_rms_px'] for p in f['pose_candidates']) for f in frames]},ensure_ascii=False))
