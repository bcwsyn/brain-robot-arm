#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace brain_robot_pick_place::grasp_geometry
{
using Point = std::array<double, 3>;

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
