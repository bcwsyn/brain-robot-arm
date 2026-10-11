#!/usr/bin/env python3
"""Read-only jaw/camera review from real snapshots and MoveIt's actual URDF.

--capture-model reads parameters and GetPlanningScene only. No motion publisher,
execution client, enable service or CAN write is created. Rendered results are
model evidence, not a physical calibration or permission to close the gripper.
"""
import argparse
import json
import math
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.spatial.transform import Rotation


def transform(origin):
    result = np.eye(4)
    if origin is not None:
        result[:3, 3] = np.fromstring(origin.get('xyz', '0 0 0'), sep=' ')
        result[:3, :3] = Rotation.from_euler(
            'xyz', np.fromstring(origin.get('rpy', '0 0 0'), sep=' ')).as_matrix()
    return result


def poses(urdf, positions):
    joints = list(urdf.findall('joint'))
    children = {j.find('child').get('link') for j in joints}
    roots = {j.find('parent').get('link') for j in joints} - children
    if len(roots) != 1:
        raise ValueError('Expected one robot root')
    result = {roots.pop(): np.eye(4)}
    while joints:
        progress = False
        for joint in joints[:]:
            parent, child = joint.find('parent').get('link'), joint.find('child').get('link')
            if parent not in result:
                continue
            t = transform(joint.find('origin'))
            kind = joint.get('type')
            if kind != 'fixed':
                value = positions[joint.get('name')]
                axis = np.fromstring(joint.find('axis').get('xyz'), sep=' ')
                axis /= np.linalg.norm(axis)
                motion = np.eye(4)
                if kind == 'prismatic':
                    motion[:3, 3] = value * axis
                elif kind in ('revolute', 'continuous'):
                    motion[:3, :3] = Rotation.from_rotvec(value * axis).as_matrix()
                else:
                    raise ValueError('Unsupported joint type ' + kind)
                t = t @ motion
            result[child] = result[parent] @ t
            joints.remove(joint)
            progress = True
        if not progress:
            raise ValueError('Unresolved robot chain')
    return result


def project(point, k):
    if point[2] <= 0:
        raise ValueError('Point behind camera')
    return [float(k[0, 0] * point[0] / point[2] + k[0, 2]),
            float(k[1, 1] * point[1] / point[2] + k[1, 2])]


def binary_stl(path):
    data = path.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError('Expected binary STL ' + str(path))
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attr', '<u2')])
    return np.frombuffer(data, dtype, count, 84)['vertices'].astype(float)


def jaw_triangles_tool(root, positions, mesh_share, half_open_m):
    """Model opening hypothesis, never an interpretation of gripper feedback."""
    for name, value in (('joint7', half_open_m), ('joint8', -half_open_m)):
        limit = root.find(f"joint[@name='{name}']/limit")
        if limit is None or not float(limit.get('lower')) <= value <= float(limit.get('upper')):
            raise ValueError('Jaw hypothesis outside actual URDF limits')
    hypothetical = dict(positions, joint7=half_open_m, joint8=-half_open_m)
    link = poses(root, hypothetical)
    result = {}
    for name in ('link7', 'link8'):
        visual = root.find(f"link[@name='{name}']/visual")
        mesh = visual.find('geometry/mesh')
        triangles = binary_stl(mesh_share / mesh.get('filename').split('package://piper_description/')[1])
        scale = np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
        pose = np.linalg.inv(link['gripper_base']) @ link[name] @ transform(visual.find('origin'))
        result[name] = (triangles * scale) @ pose[:3, :3].T + pose[:3, 3]
    return result


def mesh_projection(triangles_tool, tool_from_depth, depth_to_colour_r, depth_to_colour_t,
                    detector, width, height):
    """Exact detector resize mapping; silhouette is model evidence, not contact."""
    depth_from_tool = np.linalg.inv(tool_from_depth)
    points = triangles_tool @ depth_from_tool[:3, :3].T + depth_from_tool[:3, 3]
    colour = points @ depth_to_colour_r.T + depth_to_colour_t
    if np.any(colour[:, :, 2] <= 0):
        raise ValueError('Jaw mesh reaches camera near plane; clipping is required')
    u = detector['color_fx'] * colour[:, :, 0] / colour[:, :, 2] + detector['color_cx']
    v = detector['color_fy'] * colour[:, :, 1] / colour[:, :, 2] + detector['color_cy']
    if detector['color_mirror_horizontal']:
        u = detector['color_calibration_width'] - 1 - u
    pixels = np.stack((u * (width - 1) / (detector['color_calibration_width'] - 1),
                       v * (height - 1) / (detector['color_calibration_height'] - 1)), axis=-1)
    mask = np.zeros((height, width), np.uint8)
    for triangle in np.rint(np.clip(pixels, -100000, 100000)).astype(np.int32):
        cv2.fillConvexPoly(mask, triangle, 255)
    return pixels, mask


def operator_anchored_camera(tool_from_depth, r, t, measured_tip, tip_tool, pitch_rad,
                             colour_reference):
    """Rotation hypothesis preserving operator optical Y/Z, not a calibration."""
    tip_depth = r.T @ (measured_tip - t) if colour_reference else measured_tip
    result = tool_from_depth.copy()
    result[:3, :3] = tool_from_depth[:3, :3] @ Rotation.from_euler('x', pitch_rad).as_matrix()
    result[:3, 3] = tip_tool[:3] - result[:3, :3] @ tip_depth
    return result


def visible_jaw_masks(rgb):
    """User-confirmed dark fingers in reviewed image corners, NOT contact pads."""
    height, width = rgb.shape[:2]
    yy, xx = np.indices((height, width))
    dark = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)[:, :, 2] < 45
    result = {}
    for side, region in (('left', xx < width * .25), ('right', xx > width * .72)):
        mask = (dark & region & (yy > height * .58)).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count <= 1:
            raise ValueError('Reviewed visible finger region missing')
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        if stats[largest, cv2.CC_STAT_AREA] < 100:
            raise ValueError('Reviewed finger region too small')
        result[side] = (labels == largest).astype(np.uint8) * 255
    return result


def mask_iou(a, b):
    union = np.count_nonzero((a > 0) | (b > 0))
    return float(np.count_nonzero((a > 0) & (b > 0)) / union) if union else 0.


def compare_pitch_opening_candidates(root, positions, mesh_share, rgb, tool_from_depth,
                                     r, t, detector, measured_tip, tip_tool, output, holdout):
    """Restricted silhouette comparison. Unknown X/roll/yaw prevent calibration."""
    observed = visible_jaw_masks(rgb)
    height, width = rgb.shape[:2]
    rows = []
    meshes = {half_open: jaw_triangles_tool(root, positions, mesh_share, half_open)
              for half_open in np.linspace(.010, .035, 11)}
    for half_open, triangles in meshes.items():
        for degrees in range(16, 45, 2):
            camera = operator_anchored_camera(tool_from_depth, r, t, measured_tip, tip_tool,
                                             math.radians(degrees), True)
            masks = {name: mesh_projection(mesh, camera, r, t, detector, width, height)[1]
                     for name, mesh in triangles.items()}
            left, right = mask_iou(masks['link8'], observed['left']), mask_iou(masks['link7'], observed['right'])
            rows.append({'mount_pitch_degrees': degrees, 'model_opening_m': 2 * half_open,
                         'left_iou': left, 'right_iou': right, 'mean_iou': (left + right) / 2,
                         'tool_from_depth_optical_candidate': camera.tolist()})
    rows.sort(key=lambda row: row['mean_iou'], reverse=True)
    best = rows[0]
    camera = np.array(best['tool_from_depth_optical_candidate'])
    triangles = jaw_triangles_tool(root, positions, mesh_share, best['model_opening_m'] / 2)
    images = [('current', rgb)]
    if holdout is not None:
        other = cv2.imread(str(holdout))
        if other is None or other.shape != rgb.shape:
            raise ValueError('Holdout raw RGB is missing or has a different size')
        images.append(('earlier raw RGB, same rigid gripper', other))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(images), figsize=(6 * len(images), 5), squeeze=False)
    scores = {}
    for index, (label, frame) in enumerate(images):
        witness = visible_jaw_masks(frame)
        ax = axes[0, index]
        ax.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        scores[label] = {}
        for name, side in (('link7', 'right'), ('link8', 'left')):
            _, mask = mesh_projection(triangles[name], camera, r, t, detector, width, height)
            if np.any(mask) and np.any(mask == 0):
                ax.contour(mask, levels=[127], colors=['cyan'], linewidths=1.5)
            ax.contour(witness[side], levels=[127], colors=['red'], linewidths=1)
            scores[label][side] = mask_iou(mask, witness[side])
        ax.set(xlim=(-.5, width - .5), ylim=(height - .5, -.5), title=label)
    fig.suptitle(f'RESTRICTED MODEL CANDIDATE, NOT CALIBRATED: mount {best["mount_pitch_degrees"]} deg, '
                 f'opening {best["model_opening_m"] * 1000:.0f} mm\n'
                 'red: observed dark fingers; cyan: predicted model; 70/105 mm preserved')
    fig.tight_layout()
    fig.savefig(output / 'jaw_candidate_comparison.png', dpi=150)
    plt.close(fig)
    report = {'evidence': 'RESTRICTED_SILHOUETTE_COMPARISON_NOT_PHYSICAL_CALIBRATION',
              'assumptions': ['colour lens', 'unmeasured horizontal tip component zero',
                              'only mount pitch varies, roll/yaw not fitted',
                              'model opening is a hypothesis, not gripper feedback',
                              'dark visible outlines are not identified pad contact landmarks'],
              'operator_optical_tip_m_preserved': measured_tip.tolist(),
              'camera_calibrated': False, 'physical_capture_verified': False,
              'production_config_modified': False, 'motion_sent': False,
              'candidate_count': len(rows), 'top_candidates': rows[:5],
              'holdout_path': str(holdout) if holdout else None,
              'mask_scores': scores,
              'holdout_only_tests_visible_mask_agreement_not_independent_metric_geometry': True}
    (output / 'jaw_candidate_comparison.json').write_text(json.dumps(report, indent=2))


def render_anchored_pitch_hypotheses(root, positions, mesh_share, rgb, tool_from_depth,
                                     r, t, detector, measured_tip, tip_tool, output):
    """The mount rotates in the model only; no physical joints are changed."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    height, width = rgb.shape[:2]
    fig, axes = plt.subplots(2, 7, figsize=(21, 7))
    report = {'evidence': 'OPERATOR_YZ_ANCHORED_MOUNT_PITCH_HYPOTHESES_NOT_CALIBRATION',
              'rotation_changed_in_model_only': True, 'model_half_open_m': .035,
              'horizontal_zero_unmeasured': True, 'opening_not_measured': True,
              'camera_extrinsic_fitted': False, 'motion_sent': False, 'hypotheses': []}
    triangles = jaw_triangles_tool(root, positions, mesh_share, .035)
    for row, colour_reference in enumerate((False, True)):
        basis = 'colour lens' if colour_reference else 'depth lens'
        for column, degrees in enumerate((0, 10, 20, 30, 40, 50, 60)):
            camera = operator_anchored_camera(tool_from_depth, r, t, measured_tip, tip_tool,
                                             math.radians(degrees), colour_reference)
            ax = axes[row, column]
            ax.imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
            entry = {'lens_basis': basis, 'camera_mount_pitch_hypothesis_degrees': degrees,
                     'tool_from_depth_optical': camera.tolist(), 'jaws': {}}
            for name, colour in (('link7', 'cyan'), ('link8', 'yellow')):
                pixels, mask = mesh_projection(triangles[name], camera, r, t, detector, width, height)
                if np.any(mask) and np.any(mask == 0):
                    ax.contour(mask, levels=[127], colors=[colour], linewidths=1)
                entry['jaws'][name] = {
                    'unclipped_vertex_pixel_bounds': [pixels.min(axis=(0, 1)).tolist(),
                                                      pixels.max(axis=(0, 1)).tolist()],
                    'in_frame_silhouette_pixels': int(np.count_nonzero(mask))}
            ax.set(xlim=(-.5, width - .5), ylim=(height - .5, -.5),
                   title=f'{basis}, mount tilt {degrees} deg\n70/105 mm preserved; opening assumed 70 mm')
            report['hypotheses'].append(entry)
    fig.suptitle('RAW RGB + mount-tilt hypotheses, NOT arm J5 motions or fitted camera TF')
    fig.tight_layout()
    fig.savefig(output / 'operator_anchored_pitch_hypotheses.png', dpi=140)
    plt.close(fig)
    (output / 'operator_anchored_pitch_hypotheses.json').write_text(json.dumps(report, indent=2))


def render_jaw_hypotheses(root, positions, mesh_share, rgb, tool_from_depth, r, t,
                          detector, colour_lens_origin, output):
    """Show all hypotheses, not an image-based calibration or measured opening."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    height, width = rgb.shape[:2]
    fig, axes = plt.subplots(2, 4, figsize=(16, 7))
    report = {'evidence': 'UNFITTED_MODEL_SILHOUETTE_HYPOTHESES_ONLY',
              'physical_contact_landmarks_identified': False,
              'camera_extrinsic_fitted': False, 'motion_sent': False, 'hypotheses': []}
    for row, lens in enumerate(('configured_depth_reference', 'colour_reference_unmeasured_x_zero')):
        camera = tool_from_depth.copy()
        if row:
            camera[:3, 3] = colour_lens_origin
        for column, half_open in enumerate((0., .010, .020, .035)):
            ax = axes[row, column]
            ax.imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
            entry = {'lens_hypothesis': lens, 'model_half_open_m': half_open, 'jaws': {}}
            triangles = jaw_triangles_tool(root, positions, mesh_share, half_open)
            for name, colour in (('link7', 'cyan'), ('link8', 'yellow')):
                pixels, mask = mesh_projection(triangles[name], camera, r, t, detector, width, height)
                if np.any(mask) and np.any(mask == 0):
                    ax.contour(mask, levels=[127], colors=[colour], linewidths=1)
                entry['jaws'][name] = {
                    'unclipped_vertex_pixel_bounds': [pixels.min(axis=(0, 1)).tolist(),
                                                      pixels.max(axis=(0, 1)).tolist()],
                    'in_frame_silhouette_pixels': int(np.count_nonzero(mask))}
            ax.set(xlim=(-.5, width - .5), ylim=(height - .5, -.5),
                   title=f'{lens}\nmodel opening {2 * half_open * 1000:.0f} mm, NOT measured')
            if all(jaw['in_frame_silhouette_pixels'] == 0 for jaw in entry['jaws'].values()):
                ax.text(.03, .04, 'MODEL SILHOUETTES OUTSIDE IMAGE', color='red',
                        transform=ax.transAxes, fontsize=8, bbox={'facecolor': 'white', 'alpha': .8})
            report['hypotheses'].append(entry)
    fig.suptitle('Real raw RGB + actual URDF jaw silhouettes; no contact ROI or calibration fitted')
    fig.tight_layout()
    fig.savefig(output / 'raw_rgb_jaw_hypotheses.png', dpi=150)
    plt.close(fig)
    (output / 'jaw_hypotheses.json').write_text(json.dumps(report, indent=2))


def capture_model(output):
    import rclpy
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene
    from rcl_interfaces.srv import GetParameters
    from tf2_ros import Buffer, TransformListener
    from geometry_msgs.msg import PolygonStamped
    from sensor_msgs.msg import Image, JointState
    from std_msgs.msg import Bool
    from rclpy.qos import qos_profile_sensor_data
    from cv_bridge import CvBridge
    rclpy.init()
    node = rclpy.create_node('read_only_jaw_model_review')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    observations, frames, subscriptions = {}, {}, []

    def receive_box(message):
        observations['raw_bbox'] = {'frame': message.header.frame_id,
                                   'stamp': message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
                                   'points': [[p.x, p.y] for p in message.polygon.points]}

    def receive_joints(message):
        observations['feedback'] = {'stamp': message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
                                    'positions': dict(zip(message.name, message.position))}

    subscriptions.extend([
        node.create_subscription(PolygonStamped, '/brain_robot_vision/raw_color_bbox', receive_box, 10),
        node.create_subscription(JointState, '/joint_states_feedback', receive_joints, qos_profile_sensor_data),
        node.create_subscription(Image, '/brain_robot_vision/raw_color_debug',
                                 lambda m: frames.update(debug=m), qos_profile_sensor_data),
        node.create_subscription(Bool, '/brain_robot_vision/target_valid',
                                 lambda m: observations.update(target_valid=m.data), 10),
    ])
    try:
        parameters = node.create_client(GetParameters, '/move_group/get_parameters')
        scene = node.create_client(GetPlanningScene, '/get_planning_scene')
        if not parameters.wait_for_service(timeout_sec=5) or not scene.wait_for_service(timeout_sec=5):
            raise RuntimeError('Actual MoveIt read-only services unavailable')
        request = GetParameters.Request()
        request.names = ['robot_description', 'allow_trajectory_execution']
        future = parameters.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5)
        if not future.done() or future.result() is None:
            raise RuntimeError('Actual model read timed out')
        values = future.result().values
        if not values[0].string_value or values[1].bool_value:
            raise RuntimeError('Missing URDF or MoveIt execution unexpectedly enabled')
        (output / 'move_group.urdf').write_text(values[0].string_value)
        request = GetPlanningScene.Request()
        request.components.components = (PlanningSceneComponents.ROBOT_STATE |
                                         PlanningSceneComponents.WORLD_OBJECT_GEOMETRY |
                                         PlanningSceneComponents.OCTOMAP)
        future = scene.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5)
        if not future.done() or future.result() is None:
            raise RuntimeError('Actual scene read timed out')
        state = future.result().scene.robot_state.joint_state
        world = future.result().scene.world
        report = {'read_epoch': time.time(), 'allow_trajectory_execution': False,
                  'model_source': '/move_group robot_description',
                  'joint_stamp': state.header.stamp.sec + state.header.stamp.nanosec * 1e-9,
                  'joint_positions': dict(zip(state.name, state.position)),
                  'world_object_ids': [o.id for o in world.collision_objects],
                  'octomap_bytes': len(world.octomap.octomap.data)}
        static_frames = {}
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.02)
            for frame in ('camera_link', 'camera_depth_optical_frame', 'camera_color_optical_frame'):
                try:
                    # Static mount/optical relationships only, NOT a target's
                    # dynamic base transform or a latest-TF grasp fallback.
                    stamped = buffer.lookup_transform('gripper_base', frame, rclpy.time.Time())
                    p, q = stamped.transform.translation, stamped.transform.rotation
                    static_frames[frame] = {'translation': [p.x, p.y, p.z],
                                            'quaternion_xyzw': [q.x, q.y, q.z, q.w]}
                except Exception:
                    continue
            if len(static_frames) == 3:
                break
        report['live_static_tool_from_optical'] = static_frames
        # A short additional read window exercises newly added observation topics.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.02)
        if 'debug' in frames:
            cv2.imwrite(str(output / 'live_raw_colour_debug.png'),
                        CvBridge().imgmsg_to_cv2(frames['debug'], 'bgr8'))
        report['live_observations'] = observations
        (output / 'move_group_scene.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'actual_move_group_read': report}), flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def review(args):
    rows = [json.loads(line) for line in args.observer.read_text().splitlines() if line.startswith('{')]
    row = next(r for r in reversed(rows) if 'snapshot' in r and
               {'rgb', 'depth'} <= r.get('images', {}).keys() and
               any(topic in r['latest'] for topic in ('/joint_states_feedback', '/joint_states')))
    latest = row['latest']
    cfg = yaml.safe_load(args.task.read_text())
    detector = yaml.safe_load(args.detector.read_text())['cube_detector']['ros__parameters']
    mount = cfg['piper_camera_mount_tf']['ros__parameters']
    grasp = cfg['grasp_lift_executor']['ros__parameters']
    feedback_topic = '/joint_states_feedback' if '/joint_states_feedback' in latest else '/joint_states'
    joints = latest[feedback_topic]['positions']
    model_directory = args.model_directory or args.output
    scene = json.loads((model_directory / 'move_group_scene.json').read_text())
    # Use actual MoveIt jaw joints, not an invalid gripper cache as a jaw opening.
    positions = dict(scene['joint_positions'])
    positions.update({f'joint{i}': joints[f'joint{i}'] for i in range(1, 7)})
    root = ET.fromstring((model_directory / 'move_group.urdf').read_text())
    link = poses(root, positions)
    optical = np.eye(4)
    optical[:3, :3] = np.array([[0, 0, 1], [-1, 0, 0], [0, -1, 0]])
    camera = np.eye(4)
    camera[:3, 3] = mount['translation_m']
    camera[:3, :3] = Rotation.from_euler('xyz', mount['rotation_rpy_rad']).as_matrix()
    tool_from_depth = camera @ optical
    r = np.array(detector['depth_to_color_rotation']).reshape(3, 3)
    t = np.array(detector['depth_to_color_translation_m'])
    rgb = cv2.imread(row['images']['rgb']['path'])
    depth = cv2.imread(row['images']['depth']['path'], cv2.IMREAD_UNCHANGED)
    height, width = rgb.shape[:2]
    k = np.array([[detector['color_fx'], 0, detector['color_cx']],
                  [0, detector['color_fy'], detector['color_cy']], [0, 0, 1.]])
    k[0] *= width / detector['color_calibration_width']
    k[1] *= height / detector['color_calibration_height']
    kd = np.array(latest['/camera/depth/camera_info']['k']).reshape(3, 3)
    tip_tool = np.array([0., 0., grasp['gripper_tip_offset_m'], 1.])
    model_depth_tip = (np.linalg.inv(tool_from_depth) @ tip_tool)[:3]
    model_color_tip = r @ model_depth_tip + t
    # Operator measurement is from the lens along optical axes. Its colour-lens
    # interpretation is tested directly; depth-lens interpretation separately.
    measured_tip = np.array(mount['operator_tip_optical_m'])
    measured_rgb_pixel = project(measured_tip, k)
    model_rgb_pixel = project(model_color_tip, k)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (detector['hue_low_1'], detector['saturation_min'], detector['value_min']),
                       (detector['hue_high_1'], 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea) if contours else None
    bbox = list(cv2.boundingRect(contour)) if contour is not None else None
    # Reproduce calibrated forward registration without filling missing depths.
    yy, xx = np.nonzero(depth > 0)
    z = depth[yy, xx].astype(float) * .001
    points = np.vstack(((xx - kd[0, 2]) * z / kd[0, 0],
                        (yy - kd[1, 2]) * z / kd[1, 1], z))
    colour = r @ points + t[:, None]
    good = colour[2] > 0
    # Match the detector's endpoint-preserving resize exactly, not width/640.
    full_u = detector['color_fx'] * colour[0, good] / colour[2, good] + detector['color_cx']
    full_v = detector['color_fy'] * colour[1, good] / colour[2, good] + detector['color_cy']
    if detector['color_mirror_horizontal']:
        full_u = detector['color_calibration_width'] - 1 - full_u
    u = np.floor(full_u * (width - 1) / (detector['color_calibration_width'] - 1) + .5).astype(int)
    v = np.floor(full_v * (height - 1) / (detector['color_calibration_height'] - 1) + .5).astype(int)
    inside = (u >= 0) & (u < width) & (v >= 0) & (v < height)
    mapped_purple = mask[v[inside], u[inside]] > 0
    samples = z[good][inside][mapped_purple]
    contact_points = [[0., 0., grasp['gripper_tip_offset_m'] - d, 1.] for d in (0., .010, .020)]
    contact_pixels = [project(r @ (np.linalg.inv(tool_from_depth) @ p)[:3] + t, k)
                      for p in contact_points]
    colour_lens_depth_tip = r.T @ (measured_tip - t)
    colour_lens_origin_tool = tip_tool[:3] - tool_from_depth[:3, :3] @ colour_lens_depth_tip
    jaw_bounds = {}
    for name in ('link7', 'link8'):
        element = root.find(f"link[@name='{name}']/visual")
        mesh = element.find('geometry/mesh')
        triangles = binary_stl(args.mesh_share / mesh.get('filename').split('package://piper_description/')[1])
        pose = np.linalg.inv(link['gripper_base']) @ link[name] @ transform(element.find('origin'))
        vertices = triangles.reshape(-1, 3) @ pose[:3, :3].T + pose[:3, 3]
        jaw_bounds[name] = {'min_xyz_m': vertices.min(axis=0).tolist(),
                            'max_xyz_m': vertices.max(axis=0).tolist()}
    report = {'evidence': 'MODEL_PLUS_MEASURED_OPTICAL_YZ_NOT_CALIBRATED_CAPTURE',
              'snapshot': row['snapshot'], 'image_stamps': row['images'],
              'joint_stamp': latest[feedback_topic]['stamp'], 'feedback_topic': feedback_topic,
              'model_directory': str(model_directory),
              'model_capture_epoch': scene.get('read_epoch'),
              'model_read_from_archive_this_run': args.model_directory is not None,
              'rgb_depth_stamp_delta_s': abs(row['images']['rgb']['stamp'] - row['images']['depth']['stamp']),
              'rgb_joint_stamp_delta_s': abs(row['images']['rgb']['stamp'] - latest[feedback_topic]['stamp']),
              'q_rad': [joints[f'joint{i}'] for i in range(1, 7)],
              'q_degrees': [math.degrees(joints[f'joint{i}']) for i in range(1, 7)],
              'gripper_cache_m_not_opening_proof': joints.get('gripper'),
              'moveit_prismatic_joints': {n: positions[n] for n in ('joint7', 'joint8')},
              'model_only_jaw_mesh_tool_bounds_not_physical_measurement': jaw_bounds,
              'camera_rotation_calibrated': mount['rotation_calibrated'],
              'raw_rgb_size': [width, height], 'depth_size': list(depth.shape[::-1]),
              'raw_purple_bbox_candidate_only': bbox,
              'raw_purple_pixels': int(np.count_nonzero(mask)),
              'registered_valid_depth_samples_on_raw_purple': len(samples),
              'purple_depth_median_m': float(np.median(samples)) if len(samples) else None,
              'model_tip_depth_optical_m': model_depth_tip.tolist(),
              'model_tip_colour_optical_m': model_color_tip.tolist(),
              'model_tip_rgb_pixel': model_rgb_pixel,
              'operator_tip_as_colour_lens_rgb_pixel': measured_rgb_pixel,
              'colour_lens_hypothesis_camera_origin_tool_m_NOT_DEPLOYED': colour_lens_origin_tool.tolist(),
              'colour_lens_hypothesis_origin_delta_m': (colour_lens_origin_tool - camera[:3, 3]).tolist(),
              'horizontal_tip_component_measured': mount['horizontal_offset_measured'],
              'model_contact_axis_pixels_tip_then_10mm_20mm_behind': contact_pixels,
              'tool_base_xyz_m': link['gripper_base'][:3, 3].tolist(),
              'tool_tip_base_xyz_m': (link['gripper_base'] @ tip_tool)[:3].tolist(),
              'physical_capture_verified': False, 'motion_sent': False}
    (args.output / 'jaw_review.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    render(root, link, args.mesh_share, args.output, k, model_rgb_pixel, contact_pixels, bbox,
           width, height, link['gripper_base'] @ tool_from_depth)
    if args.overlay_jaw_hypotheses:
        render_jaw_hypotheses(root, positions, args.mesh_share, rgb, tool_from_depth, r, t,
                             detector, colour_lens_origin_tool, args.output)
    if args.operator_anchored_pitch_hypotheses:
        render_anchored_pitch_hypotheses(root, positions, args.mesh_share, rgb, tool_from_depth,
                                        r, t, detector, measured_tip, tip_tool, args.output)
    if args.compare_pitch_opening:
        compare_pitch_opening_candidates(root, positions, args.mesh_share, rgb, tool_from_depth,
                                         r, t, detector, measured_tip, tip_tool, args.output,
                                         args.holdout_rgb)


def render(root, link, mesh_share, output, k, tip_pixel, contact_pixels, bbox, width, height, base_camera):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(12, 6))
    ax = fig.add_subplot(121, projection='3d')
    for element in root.findall('link'):
        name = element.get('name')
        visual = element.find('visual')
        mesh = visual.find('geometry/mesh') if visual is not None else None
        if mesh is None or name not in link:
            continue
        path = mesh_share / mesh.get('filename').split('package://piper_description/')[1]
        triangles = binary_stl(path)
        scale = np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
        pose = link[name] @ transform(visual.find('origin'))
        triangles = (triangles * scale) @ pose[:3, :3].T + pose[:3, 3]
        # Downsample display only; never use this figure as a collision result.
        triangles = triangles[::max(1, len(triangles) // 650)]
        ax.add_collection3d(Poly3DCollection(triangles, alpha=.40,
                                            facecolor='orange' if name in ('link7', 'link8') else 'steelblue'))
    origin = base_camera[:3, 3]
    for i, color in enumerate(('r', 'g', 'b')):
        vector = base_camera[:3, i] * .07
        ax.quiver(*origin, *vector, color=color)
    ax.scatter(*origin, color='red', label='configured depth camera')
    ax.set(xlim=(-.1, .5), ylim=(-.3, .3), zlim=(0, .6), xlabel='base X (m)',
           ylabel='base Y (m)', zlabel='base Z (m)', title='Actual MoveIt URDF + measured six axes\nJaw opening NOT physically verified')
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev=22, azim=-65)
    ax = fig.add_subplot(122)
    ax.add_patch(plt.Rectangle((0, 0), width, height, fill=False, color='black', label='raw RGB boundary'))
    if bbox:
        x, y, w, h = bbox
        ax.add_patch(plt.Rectangle((x, y), w, h, fill=False, color='purple', label='colour candidate ONLY'))
    ax.scatter(*tip_pixel, color='red', label='model fingertip plane centre')
    ax.plot(*np.array(contact_pixels).T, 'o-', color='orange', label='model 0 / 10 / 20 mm behind tip')
    ax.scatter(k[0, 2], k[1, 2], marker='+', color='green', label='colour optical centre')
    ax.set(xlim=(-50, width + 50), ylim=(max(height + 100, max(p[1] for p in contact_pixels) + 20), -20),
           xlabel='original RGB u (px)', ylabel='original RGB v (px)',
           title='Separate projection diagnostic, NOT a calibrated jaw ROI')
    ax.legend(fontsize=8); ax.grid(True)
    fig.tight_layout(); fig.savefig(output / 'moveit_jaw_projection.png', dpi=130); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-model', action='store_true')
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--detector', type=Path, required=True)
    parser.add_argument('--mesh-share', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model-directory', type=Path,
                        help='Previously captured actual model; no live MoveIt startup required')
    parser.add_argument('--overlay-jaw-hypotheses', action='store_true',
                        help='Compare raw RGB with unopened/open model silhouettes, NOT calibration')
    parser.add_argument('--operator-anchored-pitch-hypotheses', action='store_true',
                        help='Compare mount-tilt hypotheses preserving measured optical Y/Z; no motion')
    parser.add_argument('--compare-pitch-opening', action='store_true',
                        help='Restricted visible silhouette comparison, NOT extrinsic calibration')
    parser.add_argument('--holdout-rgb', type=Path, help='Earlier raw RGB for mask-only comparison')
    args = parser.parse_args()
    if args.capture_model and args.model_directory and args.model_directory.resolve() != args.output.resolve():
        parser.error('--capture-model must review its newly captured output, not a different archived model')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.capture_model:
        capture_model(args.output)
    review(args)


if __name__ == '__main__':
    main()
