#pragma once

#include <array>
#include <cmath>
#include "brain_robot_pick_place/visual_grasp_feedback.hpp"

namespace brain_robot_pick_place::near_depth
{
// Factory calibration is read from the running detector, not copied into a
// second YAML. All image coordinates below are normalized ORIGINAL RGB.
struct Calibration
{
  double width{}, height{}, fx{}, fy{}, cx{}, cy{};
  bool mirror{};
  std::array<double, 9> rotation{};
  std::array<double, 3> translation{};
};

inline bool Valid(const Calibration & c)
{
  for (double x : {c.width, c.height, c.fx, c.fy, c.cx, c.cy}) {
    if (!std::isfinite(x)) {return false;}
  }
  for (double x : c.rotation) {if (!std::isfinite(x)) {return false;}}
  for (double x : c.translation) {if (!std::isfinite(x)) {return false;}}
  const auto & r = c.rotation;
  const double det = r[0] * (r[4] * r[8] - r[5] * r[7]) -
    r[1] * (r[3] * r[8] - r[5] * r[6]) + r[2] * (r[3] * r[7] - r[4] * r[6]);
  return c.width > 1 && c.height > 1 && c.fx > 0 && c.fy > 0 &&
         std::abs(det - 1.0) < .01;
}

struct Projection {double x{}, y{}, z{};};

// Existing PiPER adapter/SDK command interval is 0..80 mm. An out-of-range
// cache (e.g. 101.9 mm) cannot be evidence of a physical jaw opening.
inline bool PlausibleOpening(double opening)
{
  return std::isfinite(opening) && opening > 0 && opening <= .080;
}

inline bool Project(
  const Calibration & c, const std::array<double, 3> & depth_point,
  int image_width, int image_height, Projection & result)
{
  if (!Valid(c) || image_width <= 1 || image_height <= 1) {return false;}
  for (double x : depth_point) {if (!std::isfinite(x)) {return false;}}
  if (depth_point[2] <= .001) {return false;}
  std::array<double, 3> color = c.translation;
  for (int row = 0; row < 3; ++row) {
    for (int col = 0; col < 3; ++col) {
      color[row] += c.rotation[row * 3 + col] * depth_point[col];
    }
  }
  if (!std::isfinite(color[2]) || color[2] <= .001) {return false;}
  double u = c.fx * color[0] / color[2] + c.cx;
  const double v = c.fy * color[1] / color[2] + c.cy;
  if (c.mirror) {u = c.width - 1 - u;}
  result = {u / (c.width - 1) * (image_width - 1) / image_width,
    v / (c.height - 1) * (image_height - 1) / image_height, color[2]};
  return std::isfinite(result.x) && std::isfinite(result.y) &&
         result.x >= 0 && result.x < 1 && result.y >= 0 && result.y < 1;
}

// Bounds apply only to the missing-depth episode, not to SEARCH or fresh
// measured RGB-D. The seed is a same-image, reliable RGB-D observation of the
// locked target; accepting colour NEVER updates the seed or its timestamp.
struct Seed {visual_grasp::Box box{}; double color_z{}; bool valid{};};
struct Evidence
{
  bool model_locked{}, exact_image_tf{}, fresh_six_axis_feedback{};
  double image_age_s{}, receipt_age_s{}, seed_age_s{}, camera_travel_m{};
};

inline const char * PredictionRejection(
  const Seed & seed, const Evidence & e, const visual_grasp::Box & box,
  const Projection & projection, double timeout_s, double maximum_age_s,
  double maximum_travel_m)
{
  for (double value : {e.image_age_s, e.receipt_age_s, e.seed_age_s, e.camera_travel_m,
    timeout_s, maximum_age_s, maximum_travel_m, projection.x, projection.y, projection.z})
  {
    if (!std::isfinite(value)) {return "NONFINITE_EVIDENCE";}
  }
  if (!e.model_locked || !seed.valid) {return "NO_RELIABLE_RGBD_LOCK";}
  if (!e.exact_image_tf || !e.fresh_six_axis_feedback) {return "FEEDBACK_OR_IMAGE_TF_UNAVAILABLE";}
  if (timeout_s <= 0 || maximum_age_s <= 0 || maximum_travel_m <= 0 ||
    e.image_age_s < 0 || e.receipt_age_s < 0 || e.seed_age_s < 0 || e.camera_travel_m < 0 ||
    e.image_age_s > timeout_s || e.receipt_age_s > timeout_s)
  {return "STALE_RGB";}
  if (e.seed_age_s > maximum_age_s || e.camera_travel_m > maximum_travel_m) {
    return "PREDICTION_RANGE_EXHAUSTED";
  }
  if (!visual_grasp::Valid(box) || !visual_grasp::Valid(seed.box) ||
    !std::isfinite(seed.color_z) || seed.color_z <= .001 || projection.z <= .001)
  {return "COLOR_SHAPE_UNAVAILABLE";}
  const double cx = (box.left + box.right) / 2;
  const double cy = (box.top + box.bottom) / 2;
  if (std::hypot(cx - projection.x, cy - projection.y) > .04 ||
    projection.x < box.left || projection.x > box.right ||
    projection.y < box.top || projection.y > box.bottom)
  {return "LOCKED_TARGET_RGB_MISMATCH";}
  const double growth = seed.color_z / projection.z;
  const double width_ratio = (box.right - box.left) / (seed.box.right - seed.box.left) / growth;
  const double height_ratio = (box.bottom - box.top) / (seed.box.bottom - seed.box.top) / growth;
  if (width_ratio < .65 || width_ratio > 1.5 || height_ratio < .65 || height_ratio > 1.5) {
    return "LOCKED_TARGET_SCALE_MISMATCH";
  }
  return nullptr;
}
}  // namespace brain_robot_pick_place::near_depth
