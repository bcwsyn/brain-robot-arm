#!/usr/bin/env python3
"""Depth-only tabletop-cube geometry gate.

The probe never publishes arm commands.  Its stable plane/protrusion/size
candidate is consumed by the existing visual and grasp state machines when
the real profile enables depth-only targeting; RGB colour is diagnostic only.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import rclpy
from geometry_msgs.msg import PointStamped, Vector3Stamped
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from scipy import ndimage
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool, String
from tf2_geometry_msgs import do_transform_point
from tf2_ros import Buffer, TransformException, TransformListener


class DepthCubeProbe(Node):
    def __init__(self) -> None:
        super().__init__("depth_cube_probe")
        self.depth_topic = self.declare_parameter(
            "depth_topic", "/camera/depth/image_raw"
        ).value
        self.camera_info_topic = self.declare_parameter(
            "camera_info_topic", "/camera/depth/camera_info"
        ).value
        self.frame_stride = max(1, int(self.declare_parameter("frame_stride", 6).value))
        self.sample_stride = max(2, int(self.declare_parameter("sample_stride", 8).value))
        self.border_px = max(1, int(self.declare_parameter("border_px", 12).value))
        self.min_plane_samples = max(
            100, int(self.declare_parameter("min_plane_samples", 500).value)
        )
        self.plane_inlier_m = max(
            0.001, float(self.declare_parameter("plane_inlier_m", 0.006).value)
        )
        self.min_height_m = max(
            0.005, float(self.declare_parameter("min_height_m", 0.015).value)
        )
        self.max_height_m = max(
            self.min_height_m,
            float(self.declare_parameter("max_height_m", 0.120).value),
        )
        self.min_area_px = max(10, int(self.declare_parameter("min_area_px", 40).value))
        self.min_fill_ratio = min(
            1.0, max(0.1, float(self.declare_parameter("min_fill_ratio", 0.45).value))
        )
        self.min_size_m = max(
            0.005, float(self.declare_parameter("min_size_m", 0.015).value)
        )
        self.max_size_m = max(
            self.min_size_m, float(self.declare_parameter("max_size_m", 0.120).value)
        )
        self.max_aspect_ratio = max(
            1.0, float(self.declare_parameter("max_aspect_ratio", 1.45).value)
        )
        self.required_stable_frames = max(
            1, int(self.declare_parameter("required_stable_frames", 3).value)
        )
        self.max_center_delta_px = max(
            1.0, float(self.declare_parameter("max_center_delta_px", 16.0).value)
        )
        self.max_depth_delta_m = max(
            0.001, float(self.declare_parameter("max_depth_delta_m", 0.030).value)
        )
        self.stability_reference_frame = str(
            self.declare_parameter("stability_reference_frame", "base_link").value
        )
        self.max_reference_delta_m = max(
            0.001,
            float(self.declare_parameter("max_reference_delta_m", 0.025).value),
        )
        self.transform_timeout_s = max(
            0.001, float(self.declare_parameter("transform_timeout_s", 0.05).value)
        )
        self.max_transform_age_s = max(
            self.transform_timeout_s,
            float(self.declare_parameter("max_transform_age_s", 0.10).value),
        )

        sensor_qos = QoSProfile(depth=10)
        sensor_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        diagnostic_qos = QoSProfile(depth=1)
        diagnostic_qos.reliability = ReliabilityPolicy.RELIABLE
        diagnostic_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.valid_pub = self.create_publisher(
            Bool, "/brain_robot_vision/depth_candidate_valid", 1
        )
        self.point_pub = self.create_publisher(
            PointStamped, "/brain_robot_vision/depth_candidate_point", 1
        )
        self.size_pub = self.create_publisher(
            Vector3Stamped, "/brain_robot_vision/depth_candidate_size", 1
        )
        self.error_pub = self.create_publisher(
            Vector3Stamped, "/brain_robot_vision/depth_candidate_error", 1
        )
        self.diagnostic_pub = self.create_publisher(
            String, "/brain_robot_vision/depth_candidate_diagnostic", diagnostic_qos
        )
        self.create_subscription(CameraInfo, self.camera_info_topic, self.on_info, sensor_qos)
        self.create_subscription(Image, self.depth_topic, self.on_depth, sensor_qos)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.fx = self.fy = self.cx = self.cy = 0.0
        self.frame_count = 0
        self.stable_frames = 0
        self.previous_candidate_reference: Optional[Tuple[float, float, float]] = None
        self.last_diagnostic = ""
        self.publish_invalid("DEPTH_PROBE_WAITING_FOR_CAMERA_INFO")

    def on_info(self, msg: CameraInfo) -> None:
        if msg.k[0] > 0.0 and msg.k[4] > 0.0:
            self.fx, self.fy = float(msg.k[0]), float(msg.k[4])
            self.cx, self.cy = float(msg.k[2]), float(msg.k[5])

    @staticmethod
    def image_to_meters(msg: Image) -> Optional[np.ndarray]:
        if msg.encoding in ("16UC1", "mono16"):
            dtype = np.dtype(">u2" if msg.is_bigendian else "<u2")
            row_values = msg.step // dtype.itemsize
            raw = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, row_values)
            return raw[:, : msg.width].astype(np.float64) * 0.001
        if msg.encoding == "32FC1":
            dtype = np.dtype(">f4" if msg.is_bigendian else "<f4")
            row_values = msg.step // dtype.itemsize
            raw = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, row_values)
            return raw[:, : msg.width].astype(np.float64)
        return None

    def publish_invalid(self, reason: str) -> None:
        self.valid_pub.publish(Bool(data=False))
        error = Vector3Stamped()
        error.header.stamp = self.get_clock().now().to_msg()
        error.vector.z = 1.0
        self.error_pub.publish(error)
        if reason != self.last_diagnostic:
            self.diagnostic_pub.publish(String(data=reason))
            self.get_logger().info(reason)
            self.last_diagnostic = reason

    def fit_table_plane(
        self, depth: np.ndarray, valid: np.ndarray
    ) -> Tuple[Optional[np.ndarray], int]:
        height, width = depth.shape
        rows = np.arange(self.border_px, height - self.border_px, self.sample_stride)
        cols = np.arange(self.border_px, width - self.border_px, self.sample_stride)
        vv, uu = np.meshgrid(rows, cols, indexing="ij")
        sampled_depth = depth[vv, uu]
        sampled_valid = valid[vv, uu]
        if int(np.count_nonzero(sampled_valid)) < self.min_plane_samples:
            return None, 0
        z = sampled_depth[sampled_valid]
        un = uu[sampled_valid].astype(np.float64) / float(width)
        vn = vv[sampled_valid].astype(np.float64) / float(height)
        design = np.column_stack((un, vn, np.ones_like(un)))
        keep = np.ones(z.shape, dtype=bool)
        coefficients = None
        for _ in range(3):
            if int(np.count_nonzero(keep)) < self.min_plane_samples:
                return None, int(np.count_nonzero(keep))
            coefficients, *_ = np.linalg.lstsq(design[keep], 1.0 / z[keep], rcond=None)
            denominator = design @ coefficients
            predicted = np.divide(
                1.0,
                denominator,
                out=np.full_like(denominator, np.nan),
                where=denominator > 1e-6,
            )
            keep = np.isfinite(predicted) & (np.abs(predicted - z) <= self.plane_inlier_m)
        return coefficients, int(np.count_nonzero(keep))

    def on_depth(self, msg: Image) -> None:
        self.frame_count += 1
        if self.frame_count % self.frame_stride:
            return
        if self.fx <= 0.0 or self.fy <= 0.0:
            self.publish_invalid("DEPTH_PROBE_WAITING_FOR_CAMERA_INFO")
            return
        depth = self.image_to_meters(msg)
        if depth is None:
            self.publish_invalid(f"DEPTH_PROBE_UNSUPPORTED_ENCODING={msg.encoding}")
            return
        height, width = depth.shape
        valid = np.isfinite(depth) & (depth >= 0.05) & (depth <= 3.0)
        coefficients, plane_inliers = self.fit_table_plane(depth, valid)
        if coefficients is None:
            self.stable_frames = 0
            self.previous_candidate_reference = None
            self.publish_invalid(f"DEPTH_PROBE_NO_TABLE_PLANE inliers={plane_inliers}")
            return

        vv, uu = np.indices(depth.shape)
        denominator = (
            coefficients[0] * uu / float(width)
            + coefficients[1] * vv / float(height)
            + coefficients[2]
        )
        expected_depth = np.divide(
            1.0,
            denominator,
            out=np.full(depth.shape, np.nan, dtype=np.float64),
            where=denominator > 1e-6,
        )
        protrusion = expected_depth - depth
        mask = (
            valid
            & np.isfinite(expected_depth)
            & (protrusion >= self.min_height_m)
            & (protrusion <= self.max_height_m)
        )
        mask[: self.border_px, :] = False
        mask[-self.border_px :, :] = False
        mask[:, : self.border_px] = False
        mask[:, -self.border_px :] = False
        mask = ndimage.binary_opening(mask, structure=np.ones((3, 3), dtype=bool))
        mask = ndimage.binary_closing(mask, structure=np.ones((5, 5), dtype=bool))
        labels, label_count = ndimage.label(mask)

        best = None
        for label_id in range(1, label_count + 1):
            ys, xs = np.nonzero(labels == label_id)
            area = int(xs.size)
            if area < self.min_area_px:
                continue
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            box_area = max(1, (x1 - x0) * (y1 - y0))
            fill_ratio = area / float(box_area)
            if fill_ratio < self.min_fill_ratio:
                continue
            component_depth = depth[ys, xs]
            median_depth = float(np.median(component_depth))
            size_x = (x1 - x0) * median_depth / self.fx
            size_y = (y1 - y0) * median_depth / self.fy
            largest_size = max(size_x, size_y)
            smallest_size = max(1e-6, min(size_x, size_y))
            aspect_ratio = largest_size / smallest_size
            if (
                largest_size < self.min_size_m
                or largest_size > self.max_size_m
                or aspect_ratio > self.max_aspect_ratio
            ):
                continue
            candidate = (
                area,
                float(np.mean(xs)),
                float(np.mean(ys)),
                median_depth,
                size_x,
                size_y,
                float(np.median(protrusion[ys, xs])),
                fill_ratio,
                plane_inliers,
            )
            if best is None or candidate[0] > best[0]:
                best = candidate

        if best is None:
            self.stable_frames = 0
            self.previous_candidate_reference = None
            self.publish_invalid(
                f"DEPTH_PROBE_NO_CUBE_CANDIDATE plane_inliers={plane_inliers}"
            )
            return

        area, center_x, center_y, z, size_x, size_y, object_height, fill, inliers = best
        point = PointStamped()
        point.header = msg.header
        point.point.x = (center_x - self.cx) * z / self.fx
        point.point.y = (center_y - self.cy) * z / self.fy
        point.point.z = z
        image_time = Time.from_msg(point.header.stamp)
        transform_age_s = 0.0
        try:
            transform = self.tf_buffer.lookup_transform(
                self.stability_reference_frame,
                point.header.frame_id,
                image_time,
                timeout=Duration(seconds=0.0),
            )
        except TransformException as exact_exc:
            # The probe spins in one executor thread.  If the image is only a
            # few milliseconds newer than the newest joint TF, blocking here
            # prevents the listener from receiving the very TF being awaited.
            # Use the latest buffered transform only inside a strict age gate.
            try:
                transform = self.tf_buffer.lookup_transform(
                    self.stability_reference_frame,
                    point.header.frame_id,
                    Time(),
                    timeout=Duration(seconds=0.0),
                )
                transform_time = Time.from_msg(transform.header.stamp)
                if transform_time.nanoseconds > 0:
                    transform_age_s = abs(
                        image_time.nanoseconds - transform_time.nanoseconds
                    ) * 1.0e-9
                if transform_age_s > self.max_transform_age_s:
                    raise TransformException(
                        f"latest transform age {transform_age_s:.3f}s exceeds "
                        f"{self.max_transform_age_s:.3f}s; exact lookup: {exact_exc}"
                    )
            except TransformException as latest_exc:
                self.stable_frames = 0
                self.previous_candidate_reference = None
                self.publish_invalid(
                    "DEPTH_PROBE_STABILITY_TF_UNAVAILABLE "
                    f"{point.header.frame_id}->{self.stability_reference_frame}: "
                    f"{latest_exc}"
                )
                return
        reference_point = do_transform_point(point, transform)

        current_reference = (
            reference_point.point.x,
            reference_point.point.y,
            reference_point.point.z,
        )
        reference_delta = 0.0
        if self.previous_candidate_reference is not None:
            reference_delta = math.dist(
                current_reference, self.previous_candidate_reference
            )
            if reference_delta <= self.max_reference_delta_m:
                self.stable_frames += 1
            else:
                self.stable_frames = 1
        else:
            self.stable_frames = 1
        self.previous_candidate_reference = current_reference

        self.point_pub.publish(point)
        size = Vector3Stamped()
        size.header = msg.header
        size.vector.x = size_x
        size.vector.y = size_y
        size.vector.z = object_height
        self.size_pub.publish(size)
        error = Vector3Stamped()
        error.header = msg.header
        error.vector.x = center_x - self.cx
        error.vector.y = center_y - self.cy
        error.vector.z = max(
            abs(error.vector.x) / max(1.0, width * 0.5),
            abs(error.vector.y) / max(1.0, height * 0.5),
        )
        self.error_pub.publish(error)

        stable = self.stable_frames >= self.required_stable_frames
        self.valid_pub.publish(Bool(data=stable))
        state = "DEPTH_CUBE_CANDIDATE_VALID" if stable else "DEPTH_CUBE_WAIT_STABLE"
        diagnostic = (
            f"{state} stable={self.stable_frames}/{self.required_stable_frames} "
            f"pixel=({center_x:.1f},{center_y:.1f}) camera_m="
            f"({point.point.x:.3f},{point.point.y:.3f},{z:.3f}) "
            f"{self.stability_reference_frame}_m=({reference_point.point.x:.3f},"
            f"{reference_point.point.y:.3f},{reference_point.point.z:.3f}) "
            f"reference_delta_m={reference_delta:.3f} tf_age_s={transform_age_s:.3f} "
            f"size_m=({size_x:.3f},{size_y:.3f}) height_m={object_height:.3f} "
            f"area_px={area} fill={fill:.3f} plane_inliers={inliers}"
        )
        self.diagnostic_pub.publish(String(data=diagnostic))
        if diagnostic != self.last_diagnostic:
            self.get_logger().info(diagnostic)
            self.last_diagnostic = diagnostic


def main() -> None:
    rclpy.init()
    node = DepthCubeProbe()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
