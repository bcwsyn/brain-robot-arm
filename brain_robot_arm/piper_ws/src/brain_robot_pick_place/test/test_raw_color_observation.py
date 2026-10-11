"""Optional isolated ROS replay; no arm node or motion publisher is created.

ROS_DOMAIN_ID=78 PIPER_RAW_DETECTOR_BIN=<isolated-build>/cup_detector_node
PYTHONNOUSERSITE=1 python3 -m pytest -q -p no:cacheprovider this_file.py
"""
import os
from pathlib import Path
import subprocess
import time

import pytest


@pytest.mark.skipif(not os.environ.get("PIPER_RAW_DETECTOR_BIN"),
                    reason="Requires explicit isolated detector binary")
def test_raw_rgb_survives_zero_depth_and_clipped_bbox_is_distinct():
    assert os.environ.get("ROS_DOMAIN_ID") == "78", "Never replay in the real control domain"
    import cv2
    import numpy as np
    import rclpy
    from cv_bridge import CvBridge
    from geometry_msgs.msg import PointStamped, PolygonStamped
    from sensor_msgs.msg import CameraInfo, Image
    from std_msgs.msg import Bool

    config = Path(__file__).parents[2] / "brain_robot_ball_pick/config/cube_detector.yaml"
    child = subprocess.Popen([
        os.environ["PIPER_RAW_DETECTOR_BIN"], "--ros-args", "--log-level", "WARN",
        "-r", "__node:=cube_detector", "--params-file", str(config),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rclpy.init()
    node = rclpy.create_node("raw_colour_zero_depth_replay")
    bridge = CvBridge()
    rows, debug, valid, projection, qualified, stamps = [], [], [], [], [], set()
    subscriptions = [
        node.create_subscription(PolygonStamped, "/brain_robot_vision/raw_color_bbox",
                                 lambda m: rows.append(m), 10),
        node.create_subscription(Image, "/brain_robot_vision/raw_color_debug",
                                 lambda m: debug.append(m), 10),
        node.create_subscription(Bool, "/brain_robot_vision/target_valid",
                                 lambda m: valid.append(m.data), 10),
        node.create_subscription(PointStamped, "/brain_robot_vision/raw_target_projection",
                                 lambda m: projection.append(m), 10),
        node.create_subscription(PolygonStamped, "/brain_robot_vision/qualified_color_bbox",
                                 lambda m: qualified.append(m), 10),
    ]
    rgb_pub = node.create_publisher(Image, "/camera/color/image_raw", 10)
    depth_pub = node.create_publisher(Image, "/camera/depth/image_raw", 10)
    info_pub = node.create_publisher(CameraInfo, "/camera/depth/camera_info", 10)
    try:
        for clipped in [True, False]:
            rows.clear(); debug.clear(); valid.clear(); qualified.clear(); stamps.clear()
            image = np.zeros((240, 320, 3), np.uint8)
            image[210 if clipped else 155:240 if clipped else 220, 100:160] = [180, 40, 150]
            assert 125 <= cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[215, 125, 0] <= 160
            deadline, sent_at = time.monotonic() + 12, 0
            while time.monotonic() < deadline:
                assert child.poll() is None, "Detector terminated"
                if time.monotonic() - sent_at >= .2:
                    sent_at = time.monotonic()
                    stamp = node.get_clock().now().to_msg()
                    stamps.add((stamp.sec, stamp.nanosec))
                    rgb = bridge.cv2_to_imgmsg(image, "bgr8")
                    rgb.header.frame_id = "camera_color_optical_frame"
                    rgb.header.stamp = stamp
                    depth = bridge.cv2_to_imgmsg(np.zeros((400, 640), np.uint16), "16UC1")
                    depth.header.frame_id = "camera_depth_optical_frame"
                    depth.header.stamp = stamp
                    info = CameraInfo(width=640, height=400)
                    info.header = depth.header
                    info.k = [478.756866, 0., 326.135559, 0., 478.756866, 199.873489, 0., 0., 1.]
                    info_pub.publish(info); rgb_pub.publish(rgb); depth_pub.publish(depth)
                rclpy.spin_once(node, timeout_sec=.02)
                current = [m for m in rows if (m.header.stamp.sec, m.header.stamp.nanosec) in stamps]
                if len(current) >= 3 and debug and valid and qualified:
                    rows[:] = current
                    break
            assert len(rows) >= 3 and debug and valid
            assert not any(valid), "Colour-only replay must not authorize real ALIGN/grasp"
            points = rows[-1].polygon.points
            assert len(points) == 4
            assert abs(points[0].x - 100 / 320) < .02
            assert abs(points[2].x - 160 / 320) < .02
            assert (points[2].y >= .98) == clipped
            assert rows[-1].header.frame_id == "camera_color_optical_frame"
            observed = [m for m in qualified if (m.header.stamp.sec, m.header.stamp.nanosec) in stamps]
            assert observed and bool(observed[-1].polygon.points) == (not clipped)
            assert debug[-1].width == 320 and debug[-1].height == 240
            raw = bridge.imgmsg_to_cv2(debug[-1], "bgr8")
            assert np.array_equal(raw[215, 125], [180, 40, 150])
            print("RAW_REPLAY", "CLIPPED" if clipped else "FULL", len(rows),
                  "bbox", [(p.x, p.y) for p in points], "target_valid=false depth=all_zero")
        # A registered target uses the original RGB grid, not 640x400 debug pixels.
        rows.clear(); projection.clear(); valid.clear(); stamps.clear()
        image = np.zeros((240, 320, 3), np.uint8)
        image[90:130, 100:140] = [180, 40, 150]
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            stamp = node.get_clock().now().to_msg()
            stamps.add((stamp.sec, stamp.nanosec))
            rgb = bridge.cv2_to_imgmsg(image, "bgr8")
            rgb.header.frame_id = "camera_color_optical_frame"; rgb.header.stamp = stamp
            depth = bridge.cv2_to_imgmsg(np.full((400, 640), 300, np.uint16), "16UC1")
            depth.header.frame_id = "camera_depth_optical_frame"; depth.header.stamp = stamp
            info.header = depth.header
            info_pub.publish(info); rgb_pub.publish(rgb); depth_pub.publish(depth)
            until = time.monotonic() + .2
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=.02)
            if projection and any(valid):
                break
        current = [m for m in projection if (m.header.stamp.sec, m.header.stamp.nanosec) in stamps]
        assert current and any(valid), "Valid synthetic depth should exercise projection association"
        p = current[-1]
        box = next(m for m in reversed(rows) if m.header.stamp == p.header.stamp)
        assert box.polygon.points[0].x <= p.point.x <= box.polygon.points[2].x
        assert box.polygon.points[0].y <= p.point.y <= box.polygon.points[2].y
        assert p.point.z > .25 and p.point.z < .35
        print("RAW_REPLAY ASSOCIATED_RGBD", p.point.x, p.point.y, p.point.z)
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(timeout=5)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    assert subscriptions  # Retain subscriptions throughout the replay.
