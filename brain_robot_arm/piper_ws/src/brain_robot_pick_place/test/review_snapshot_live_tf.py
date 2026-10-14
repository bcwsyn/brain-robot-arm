"""Read-only, bounded companion to review_manual_terminal_snapshot.py.

Start before the snapshot. Preserve its exact RGB stamp and query buffered TF
at that stamp; missing transforms/targets remain missing, never latest fallbacks.
No publisher, motor interface or execution client is constructed.
"""
import json
import sys
import time
from pathlib import Path

import rclpy
from rclpy.time import Time
from sensor_msgs.msg import JointState
from geometry_msgs.msg import PointStamped, PolygonStamped
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from tf2_ros import Buffer, TransformListener


def stamp(message):
    return str(message.header.stamp.sec * 10**9 + message.header.stamp.nanosec)


def main():
    report_path = Path(sys.argv[1])
    output = report_path.with_name('live_tf_and_target.json')
    if output.exists():
        raise RuntimeError('Refusing to overwrite previous acquisition')
    rclpy.init()
    node = rclpy.create_node('read_only_snapshot_live_tf')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    points, boxes, diagnostics, joints, states = [], [], [], [], []
    subscriptions = [
        node.create_subscription(PointStamped, '/brain_robot_vision/target_point_camera',
                                 points.append, 10),
        node.create_subscription(PolygonStamped, '/brain_robot_vision/qualified_color_bbox',
                                 boxes.append, 10),
        node.create_subscription(DiagnosticArray, '/brain_robot_vision/rgbd_observation',
                                 diagnostics.append, 10),
        node.create_subscription(JointState, '/joint_states_feedback',
                                 joints.append, qos_profile_sensor_data),
        node.create_subscription(String, '/brain_robot_visual_control/reason',
                                 lambda m: states.append(m.data),
                                 QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
    ]
    try:
        deadline = time.monotonic() + 25
        ready_at = None
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
            if report_path.exists():
                if ready_at is None:
                    ready_at = time.monotonic()
                if time.monotonic() - ready_at >= 1:
                    break
        if not report_path.exists():
            raise RuntimeError('Snapshot report missing within bounded window')
        report = json.loads(report_path.read_text())
        rgb_stamp = report['rgb_stamp_ns']
        at = Time(nanoseconds=int(rgb_stamp))
        result = {'read_only': True, 'rgb_stamp_ns': rgb_stamp,
                  'tf_policy': 'Exact image time only, no latest fallback',
                  'tf': {}, 'target_points': [], 'qualified_boxes': [],
                  'visual_reason': states[-1] if states else None}
        for frame in ('camera_color_optical_frame', 'camera_depth_optical_frame', 'gripper_base'):
            try:
                value = buffer.lookup_transform('base_link', frame, at)
                t, q = value.transform.translation, value.transform.rotation
                result['tf'][frame] = {'stamp_ns': stamp(value),
                                      'translation_m': [t.x, t.y, t.z],
                                      'quaternion_xyzw': [q.x, q.y, q.z, q.w]}
            except Exception as error:
                result['tf'][frame] = {'available': False, 'error': str(error)}
        for value in points:
            if stamp(value) == rgb_stamp:
                result['target_points'].append({'stamp_ns': stamp(value),
                    'frame': value.header.frame_id,
                    'xyz_m': [value.point.x, value.point.y, value.point.z]})
        for value in boxes:
            if stamp(value) == rgb_stamp:
                result['qualified_boxes'].append({'stamp_ns': stamp(value),
                    'frame': value.header.frame_id,
                    'corners': [[p.x, p.y, p.z] for p in value.polygon.points]})
        result['same_stamp_diagnostic_count'] = sum(stamp(v) == rgb_stamp for v in diagnostics)
        if joints:
            value = min(joints, key=lambda m: abs(int(stamp(m)) - int(rgb_stamp)))
            result['nearest_feedback_not_interpolated'] = {
                'stamp_ns': stamp(value), 'positions': dict(zip(value.name, value.position))}
        result['sample_counts'] = {'points': len(points), 'boxes': len(boxes),
                                  'diagnostics': len(diagnostics), 'joints': len(joints)}
        output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2), flush=True)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
