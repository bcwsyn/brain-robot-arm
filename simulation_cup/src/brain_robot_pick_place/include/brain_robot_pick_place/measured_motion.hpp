#pragma once
#include <cmath>
#include <algorithm>
#include <vector>

namespace brain_robot_pick_place
{
// For Gazebo's position interface: estimate speed from two actual position
// samples, rather than the velocity cached before the last SetPosition call.
inline bool PositionSamplesSettled(
  const std::vector<double> & previous, const std::vector<double> & current, double dt)
{
  if (previous.size() != 6 || current.size() != 6 || !std::isfinite(dt) || dt <= .001 || dt > .25) {
    return false;
  }
  for (std::size_t i = 0; i < 6; ++i) {
    if (!std::isfinite(previous[i]) || !std::isfinite(current[i])) {return false;}
    const double delta = std::abs(current[i] - previous[i]);
    if (delta > .001 || delta / dt > .02) {return false;}
  }
  return true;
}
// Reject a short approach that flips an IK branch or sweeps a wrist through
// a large angle. Check intermediate points, not just equal-looking endpoints.
inline bool BoundedJointExcursion(const std::vector<std::vector<double>> & points, double limit)
{
  if (points.empty() || !std::isfinite(limit) || limit <= 0) {return false;}
  std::vector<double> lower(6, INFINITY), upper(6, -INFINITY);
  for (const auto & point : points) {
    if (point.size() != 6) {return false;}
    for (std::size_t i = 0; i < 6; ++i) {
      if (!std::isfinite(point[i])) {return false;}
      lower[i] = std::min(lower[i], point[i]); upper[i] = std::max(upper[i], point[i]);
      if (upper[i] - lower[i] > limit) {return false;}
    }
  }
  return true;
}

}
