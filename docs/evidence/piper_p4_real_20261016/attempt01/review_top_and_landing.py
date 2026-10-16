"""Offline P4 reference audit and fixed-board witness; never sends commands.

The user's suggested 15 mm offsets are hypotheses, not approved poses.
Keep tracking failures and both planar branches; never reassign board IDs.
"""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
sys.path.insert(0, str(REPO / 'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
sys.path.insert(0, str(REPO / 'docs/evidence/piper_calibration_p1_20261015/board_spec_20261016'))
from board_pose_offline import grid, poses
from export_calibration_bundle import base_tool_fk, load_installed_model
from partial_board_tracking_check import propagate
from review_depth_registration import read_config

urdf, _ = load_installed_model()
assert hashlib.sha256(urdf.encode()).hexdigest() == '0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82'
model = ET.fromstring(urdf)
X = np.array(json.loads((REPO / 'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
params = read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
K = np.diag([319/639, 239/479, 1.]) @ np.array([
    [params['color_fx'], 0, params['color_cx']],
    [0, params['color_fy'], params['color_cy']], [0, 0, 1.]])
samples = [json.loads(s) for s in (ROOT/'real_record/samples.jsonl').read_text().splitlines()]
events = [json.loads(s) for s in (ROOT/'real_record/events.jsonl').read_text().splitlines()]
stage = None
descent_messages = []
for event in events:
    if event['topic_key'] == 'grasp_state':
        stage = event['message']['data']
    if event['topic_key'] == 'arm_trajectory' and stage == 'P4_DESCENT_EXECUTING':
        descent_messages.append(event)
assert len(descent_messages) == 1
# Select by recorded state, not "last N": cleanup also emits a hold trajectory.
descent = descent_messages[0]['message']
q_goal = descent['points'][-1]['positions']
G_goal = np.array(base_tool_fk(model, q_goal))
tip = (G_goal @ [0, 0, .1358, 1])[:3]
axis = G_goal[:3, 2]
surface = np.array(yaml.safe_load((ROOT/'frozen_target.yaml').read_text())['surface_base_m'])
insertion = min(.029*.4, .012)
assert np.linalg.norm(tip - surface - axis*insertion) < .001

fresh = json.loads((ROOT/'fixed_board_plane_review.json').read_text())
T_base_board = np.array(fresh['frames'][2]['T_base_board'])
normal = np.array(fresh['frames'][2]['normal_base'])
center_hypothesis = surface - normal*.0145
heading = np.r_[surface[:2], 0.]
heading /= np.linalg.norm(heading)
offsets = [('unchanged', np.zeros(3)), ('base_down_15mm', np.array([0., 0., -.015])),
           ('base_down_and_radial_out_15mm_HYPOTHESIS', np.array([0., 0., -.015]) + .015*heading)]
candidates = []
for label, delta in offsets:
    p = tip + delta
    candidates.append({'label': label, 'tip_base_m': p.tolist(),
        'signed_distance_to_nominal_board_plane_m': float(normal @ (p-T_base_board[:3, 3])),
        'delta_base_m': delta.tolist(), 'planned_or_executed': False})

# Start after the recorded OBSERVE_POSE_REACHED event. Stage labels alone are
# insufficient: the executor announces readiness while observation is moving.
seed = fresh['frames'][2]
prior = json.loads(Path('/home/johnwick/brain_robot_logs/p4_cube_retry_20261016.wyUEQu/board_target_review.json').read_text())['frames'][2]
ids = np.array(seed['fixed_ids'])
obj = grid(tuple(prior['grid_shape']))[ids]
points = np.array(seed['corners_px'], np.float32)
capture = [json.loads(s) for s in (ROOT/'capture/observer.jsonl').read_text().splitlines()]
previous = cv2.cvtColor(cv2.imread(capture[2]['images']['rgb']['path']), cv2.COLOR_BGR2GRAY)
witness = []
stopped = None
reference = None
for sample in samples[54:]:
    path = Path(sample['images']['rgb']['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sample['images']['rgb']['sha256']
    frame = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2GRAY)
    tracks = propagate(previous, frame, points)
    keep = [i for i, t in enumerate(tracks) if t['forward_status'] and t['reverse_status']
            and t['inside_image'] and t['forward_backward_error_px'] <= .5]
    if len(keep) < 6:
        stopped = {'image': str(path), 'reason': 'fewer_than_six_original_IDs_remain',
                   'remaining_ids': ids[keep].tolist(), 'tracks': tracks}
        break
    ids, obj = ids[keep], obj[keep]
    points = np.array([tracks[i]['position_px'] for i in keep], np.float32)
    candidate_poses = poses(obj, points, K, np.zeros(5))
    positive = [p for p in candidate_poses if p['all_points_positive_depth']]
    if not positive:
        stopped = {'image': str(path), 'reason': 'no_positive_depth_PnP', 'candidates': candidate_poses}
        break
    best = min(positive, key=lambda p: p['refined_rms_px'])
    if best['refined_rms_px'] > 1.:
        stopped = {'image': str(path), 'reason': 'PnP_RMS_above_1px', 'candidates': candidate_poses}
        break
    m = sample['feedback_nearest_received']['joint_states_feedback']['message']
    q = [m['position'][m['name'].index(f'joint{i}')] for i in range(1, 7)]
    B = np.array(base_tool_fk(model, q)) @ X @ np.array(best['T_color_optical_from_local_board'])
    if reference is None:
        reference = B
    angle = np.arccos(np.clip((np.trace(reference[:3,:3].T @ B[:3,:3])-1)/2, -1., 1.))
    witness.append({'image': str(path), 'RGB_stamp_ns': sample['RGB_stamp_ns'], 'stage': sample['stage'],
        'remaining_original_ids': ids.tolist(), 'corners_px': points.tolist(), 'object_points_m': obj.tolist(),
        'max_retained_FB_px': max(tracks[i]['forward_backward_error_px'] for i in keep),
        'all_PnP_candidates': candidate_poses, 'actual_q_rad': q, 'T_base_board': B.tolist(),
        'board_origin_drift_from_first_m': float(np.linalg.norm(B[:3,3]-reference[:3,3])),
        'board_rotation_drift_rad': float(angle)})
    previous = frame

report = {'offline_only': True, 'no_hardware_or_production_changes': True,
    'user_hint': '15mm lower, possibly 15mm forward; direction/physical displacement not measured',
    'code_reference': 'P4OpenLoopGraspAndLift -> TargetDirectedApproach(surface, tip_offset, SurfaceInsertion)',
    'target_is_TOP_surface_NOT_visual_reconstructed_cube_center': True,
    'insertion_along_final_tool_axis_m': insertion, 'surface_base_m': surface.tolist(),
    'nominal_center_from_board_normal_m': center_hypothesis.tolist(),
    'descent_trajectory_receipt_epoch': descent_messages[0]['receipt_epoch'],
    'commanded_model_tip_base_m': tip.tolist(), 'commanded_final_axis_base': axis.tolist(),
    'tip_minus_surface_m': (tip-surface).tolist(),
    'tip_minus_nominal_cube_center_m': (tip-center_hypothesis).tolist(),
    'offset_hypotheses_NOT_new_targets': candidates,
    'board_fixed_ID_replay': witness, 'tracking_stop': stopped,
    'limitations': ['Nominal finger free-end point is not a measured contact-pad center.',
        'The 29mm edge, 32mm grid, plane, camera intrinsics and mounting are assumptions/estimates.',
        'Base-down and radial-out are explicit OFFLINE hypotheses, not an interpretation approved for motion.',
        'Planar ambiguity, repeated-grid ID slips, nonplanar paper and nearest-received q may affect the witness.',
        'Low LK FB/PnP RMS alone cannot prove correct physical board identity or isolate the calibration error.',
        'A board-drift result cannot uniquely separate hand-eye, FK, timing, board geometry and camera model.',
        'No new TCP, TF, placement, motion rule or threshold is adopted.']}
with (ROOT/'top_reference_and_board_replay_opening_seed.json').open('x') as f:
    json.dump(report, f, indent=2, allow_nan=False)
print(json.dumps({'tip_base_m': tip.tolist(), 'tip_minus_nominal_center_m': (tip-center_hypothesis).tolist(),
    'offset_hypotheses': candidates, 'board_replayed_frames': len(witness), 'tracking_stop': stopped,
    'last_board_drift_m': witness[-1]['board_origin_drift_from_first_m'] if witness else None}))
