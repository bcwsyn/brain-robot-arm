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

// Current device 0x47E and adapter command interval is 0..100 mm. An out-of-range
// cache (e.g. 101.9 mm) cannot be evidence of a physical jaw opening.
inline bool PlausibleOpening(double opening)
{
  return std::isfinite(opening) && opening > 0 && opening <= .100;
}

inline bool Project(
  const Calibration & c, const std::array<double, 3> & depth_point,
  int image_width, int image_height, Projection & result, bool require_inside = true)
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
         (!require_inside ||
         (result.x >= 0 && result.x < 1 && result.y >= 0 && result.y < 1));
}

// A colour ray at the immutable model range, NOT a new depth measurement.
// Use the exact inverse (factory R is rounded) in both association and control.
inline bool RgbResidual(
  const Calibration & c, const std::array<double, 3> & depth_point,
  const visual_grasp::Box & box, int width, int height,
  std::array<double, 3> & delta)
{
  Projection p;
  if (!visual_grasp::Valid(box) || !Project(c, depth_point, width, height, p, false)) {
    return false;
  }
  double u = (box.left + box.right) * .5 * width * (c.width - 1) / (width - 1);
  const double v = (box.top + box.bottom) * .5 * height * (c.height - 1) / (height - 1);
  if (c.mirror) {u = c.width - 1 - u;}
  std::array<double, 3> difference{(u - c.cx) * p.z / c.fx - c.translation[0],
    (v - c.cy) * p.z / c.fy - c.translation[1], p.z - c.translation[2]};
  const auto & r = c.rotation;
  const std::array<double, 9> adj{r[4]*r[8]-r[5]*r[7], r[2]*r[7]-r[1]*r[8],
    r[1]*r[5]-r[2]*r[4], r[5]*r[6]-r[3]*r[8], r[0]*r[8]-r[2]*r[6],
    r[2]*r[3]-r[0]*r[5], r[3]*r[7]-r[4]*r[6], r[1]*r[6]-r[0]*r[7],
    r[0]*r[4]-r[1]*r[3]};
  const double det = r[0]*adj[0] + r[1]*adj[3] + r[2]*adj[6];
  for (int row = 0; row < 3; ++row) {
    delta[row] = -depth_point[row];
    for (int col = 0; col < 3; ++col) {delta[row] += adj[row*3+col]*difference[col]/det;}
    if (!std::isfinite(delta[row])) {return false;}
  }
  return true;
}

inline bool Cropped(const visual_grasp::Box & b, int width, int height)
{
  return visual_grasp::Valid(b) && width > 1 && height > 1 &&
         (b.left <= 1. / width || b.top <= 1. / height ||
         b.right >= 1 - 1. / width || b.bottom >= 1 - 1. / height);
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
  double maximum_travel_m, double rgb_residual_m, double maximum_association_m,
  bool clipped_recovery = false, int image_width = 320, int image_height = 240,
  bool allow_bounded_compensation = false, bool identity_continuous = true)
{
  for (double value : {e.image_age_s, e.receipt_age_s, e.seed_age_s, e.camera_travel_m,
    timeout_s, maximum_age_s, maximum_travel_m, projection.x, projection.y, projection.z,
    rgb_residual_m, maximum_association_m})
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
  // Correctable error is not loss of identity. Reuse the existing metric
  // association bound, rather than requiring correction to have already worked.
  if (rgb_residual_m < 0 || maximum_association_m <= 0 ||
    (!allow_bounded_compensation && rgb_residual_m > maximum_association_m))
  {return "LOCKED_TARGET_RGB_MISMATCH";}
  if (allow_bounded_compensation && !identity_continuous) {
    return "LOCKED_RGB_IDENTITY_JUMP";
  }
  const double growth = seed.color_z / projection.z;
  const double width_ratio = (box.right - box.left) / (seed.box.right - seed.box.left) / growth;
  const double height_ratio = (box.bottom - box.top) / (seed.box.bottom - seed.box.top) / growth;
  const bool width_clipped = clipped_recovery &&
    (box.left <= 1. / image_width || box.right >= 1 - 1. / image_width);
  const bool height_clipped = clipped_recovery &&
    (box.top <= 1. / image_height || box.bottom >= 1 - 1. / image_height);
  if ((!width_clipped && (width_ratio < .65 || width_ratio > 1.5)) ||
    (!height_clipped && (height_ratio < .65 || height_ratio > 1.5))) {
    return "LOCKED_TARGET_SCALE_MISMATCH";
  }
  return nullptr;
}
}  // namespace brain_robot_pick_place::near_depth
