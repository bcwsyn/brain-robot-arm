#pragma once

#include <cmath>
#include <opencv2/core.hpp>

namespace brain_robot_pick_place
{
// Retain ONLY measured depth pixels whose factory D->C projection belongs to
// this original colour contour. No resizing, inpainting or synthesized depth.
inline cv::Mat associate_color_mask(
  const cv::Mat & color_mask, const cv::Mat & source_pixels)
{
  CV_Assert(color_mask.type() == CV_8UC1 && source_pixels.type() == CV_32SC2);
  cv::Mat mask = cv::Mat::zeros(source_pixels.size(), CV_8UC1);
  for (int y = 0; y < mask.rows; ++y) {
    for (int x = 0; x < mask.cols; ++x) {
      const auto p = source_pixels.at<cv::Vec2i>(y, x);
      if (p[0] >= 0 && p[0] < color_mask.cols && p[1] >= 0 && p[1] < color_mask.rows) {
        mask.at<unsigned char>(y, x) = color_mask.at<unsigned char>(p[1], p[0]);
      }
    }
  }
  return mask;
}

// A full colour contour's centre may have no depth. Intersect its colour ray
// with the ROBUST MEASURED depth-Z of the associated object, then return that
// point in the original DEPTH optical frame. This is an aim-point estimate,
// not a depth measurement at the missing pixel or a jaw-contact calibration.
inline bool color_center_at_depth_z(
  cv::Point2d pixel, cv::Size image_size, cv::Size calibration_size,
  double fx, double fy, double cx, double cy, bool mirror,
  const cv::Matx33d & depth_to_color, const cv::Vec3d & translation,
  double measured_depth_z, cv::Vec3d & depth_point, double & color_z)
{
  if (image_size.width <= 1 || image_size.height <= 1 ||
    calibration_size.width <= 1 || calibration_size.height <= 1 ||
    !std::isfinite(fx) || !std::isfinite(fy) || fx <= 0 || fy <= 0 ||
    !std::isfinite(cx) || !std::isfinite(cy) ||
    !std::isfinite(pixel.x) || !std::isfinite(pixel.y) ||
    !std::isfinite(measured_depth_z) || measured_depth_z <= .001)
  {
    return false;
  }
  pixel.x *= double(calibration_size.width - 1) / (image_size.width - 1);
  pixel.y *= double(calibration_size.height - 1) / (image_size.height - 1);
  if (mirror) {pixel.x = calibration_size.width - 1 - pixel.x;}
  for (const auto value : depth_to_color.val) {if (!std::isfinite(value)) {return false;}}
  for (const auto value : translation.val) {if (!std::isfinite(value)) {return false;}}
  const double determinant = cv::determinant(depth_to_color);
  if (!std::isfinite(determinant) || std::abs(determinant) < 1e-9) {return false;}
  // Exact inverse also handles the rounding of the published factory rotation.
  const cv::Matx33d inverse = depth_to_color.inv();
  const cv::Vec3d ray = inverse * cv::Vec3d((pixel.x - cx) / fx, (pixel.y - cy) / fy, 1);
  const cv::Vec3d offset = -(inverse * translation);
  if (!std::isfinite(ray[2]) || std::abs(ray[2]) < 1e-9) {return false;}
  color_z = (measured_depth_z - offset[2]) / ray[2];
  depth_point = ray * color_z + offset;
  return std::isfinite(color_z) && color_z > .001 &&
         std::isfinite(depth_point[0]) && std::isfinite(depth_point[1]) &&
         std::isfinite(depth_point[2]) && depth_point[2] > .001;
}
}  // namespace brain_robot_pick_place
