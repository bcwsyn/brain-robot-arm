#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace brain_robot_pick_place::grasp_geometry
{
using Point = std::array<double, 3>;
using Quaternion = std::array<double, 4>;  // x, y, z, w

// Rotate the desired tool attitude about a measured joint axis in the same
// reference frame. This changes the pose goal, never an executed joint point.
inline Quaternion RotateOrientationAboutAxis(
  const Quaternion & orientation, const Point & axis, double angle_rad)
{
  double axis_squared = 0.0;
  double quaternion_squared = 0.0;
  for (const double value : axis) {
    if (!std::isfinite(value)) {throw std::invalid_argument("Non-finite rotation axis");}
    axis_squared += value * value;
  }
  for (const double value : orientation) {
    if (!std::isfinite(value)) {throw std::invalid_argument("Non-finite orientation");}
    quaternion_squared += value * value;
  }
  if (!std::isfinite(angle_rad) || axis_squared < 1e-12 || quaternion_squared < 1e-12) {
    throw std::invalid_argument("Invalid pose rotation");
  }
  const double scale = std::sin(angle_rad * 0.5) / std::sqrt(axis_squared);
  const Quaternion r{axis[0] * scale, axis[1] * scale, axis[2] * scale,
    std::cos(angle_rad * 0.5)};
  const double norm = std::sqrt(quaternion_squared);
  const Quaternion q{orientation[0] / norm, orientation[1] / norm,
    orientation[2] / norm, orientation[3] / norm};
  return {
    r[3] * q[0] + r[0] * q[3] + r[1] * q[2] - r[2] * q[1],
    r[3] * q[1] - r[0] * q[2] + r[1] * q[3] + r[2] * q[0],
    r[3] * q[2] + r[0] * q[1] - r[1] * q[0] + r[2] * q[3],
    r[3] * q[3] - r[0] * q[0] - r[1] * q[1] - r[2] * q[2]};
}

// The detector reports a visible surface, not a reconstructed volume centre.
// This tabletop-cube heuristic puts the fingertips just past that surface.
// It is deliberately bounded by the smaller measured face dimension.
inline double SurfaceInsertion(double face_edge_m, double fraction, double maximum_m)
{
  if (!std::isfinite(face_edge_m) || face_edge_m <= 0.0 ||
    !std::isfinite(fraction) || fraction <= 0.0 || fraction >= 0.5 ||
    !std::isfinite(maximum_m) || maximum_m <= 0.0)
  {
    throw std::invalid_argument("Invalid surface-grasp size/insertion parameters");
  }
  return std::min(face_edge_m * fraction, maximum_m);
}

inline Point ToolOrigin(
  const Point & surface, const Point & unit_axis, double tip_offset_m, double signed_gap_m)
{
  Point result{};
  for (std::size_t i = 0; i < result.size(); ++i) {
    result[i] = surface[i] - unit_axis[i] * (tip_offset_m + signed_gap_m);
  }
  return result;
}

inline Point Tip(const Point & origin, const Point & unit_axis, double tip_offset_m)
{
  Point result{};
  for (std::size_t i = 0; i < result.size(); ++i) {
    result[i] = origin[i] + unit_axis[i] * tip_offset_m;
  }
  return result;
}

struct LandingError
{
  double distance_m;
  double axial_m;
  double lateral_m;
};

inline LandingError CompareTips(
  const Point & actual_tip, const Point & expected_tip, const Point & unit_axis)
{
  double squared = 0.0;
  double axial = 0.0;
  for (std::size_t i = 0; i < actual_tip.size(); ++i) {
    const double delta = actual_tip[i] - expected_tip[i];
    squared += delta * delta;
    axial += delta * unit_axis[i];
  }
  return {std::sqrt(squared), axial, std::sqrt(std::max(0.0, squared - axial * axial))};
}

enum class LandingDecision { ACCEPT, CORRECT_ONCE, REJECT };

// A fresh visible cube-face point is NOT a calibrated volume reconstruction.
// This conservative local-jaw check rejects remote/off-centre faces before
// close. It cannot certify a physically wrong camera-to-tool transform.
inline bool FaceInsideJawCapture(
  const Point & face, double tip_z, double cube_side, double opening,
  double depth_slack = 0.008, double side_margin = 0.002)
{
  for (const double value : {face[0], face[1], face[2], tip_z, cube_side, opening,
    depth_slack, side_margin})
  {
    if (!std::isfinite(value)) {return false;}
  }
  return cube_side > 0.0 && opening > 0.0 && tip_z > 0.0 &&
    depth_slack >= 0.0 && side_margin >= 0.0 &&
    std::abs(face[0]) <= cube_side * 0.5 + depth_slack &&
    std::abs(face[1]) + cube_side * 0.5 + side_margin <= opening * 0.5 &&
    face[2] >= tip_z - cube_side - depth_slack && face[2] <= tip_z + depth_slack;
}

struct LandingLimits
{
  double position_tolerance_m;
  double orientation_tolerance_rad;
  double maximum_correction_m;
  double maximum_correction_angle_rad;
};

inline LandingDecision DecideLanding(
  const LandingError & error, double angle_rad, const LandingLimits & limits,
  bool already_corrected)
{
  if (!std::isfinite(error.distance_m) || !std::isfinite(angle_rad) ||
    error.distance_m < 0.0 || angle_rad < 0.0)
  {
    return LandingDecision::REJECT;
  }
  if (error.distance_m <= limits.position_tolerance_m &&
    angle_rad <= limits.orientation_tolerance_rad)
  {
    return LandingDecision::ACCEPT;
  }
  if (already_corrected || error.distance_m > limits.maximum_correction_m ||
    angle_rad > limits.maximum_correction_angle_rad)
  {
    return LandingDecision::REJECT;
  }
  return LandingDecision::CORRECT_ONCE;
}
}  // namespace brain_robot_pick_place::grasp_geometry
