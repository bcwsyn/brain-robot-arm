#pragma once

#include "brain_robot_pick_place/target_directed_grasp.hpp"

namespace brain_robot_pick_place::visual_grasp
{
// Normalized coordinates in ORIGINAL colour image, never registered depth pixels.
struct Box {double left, top, right, bottom;};

inline bool Valid(const Box & b)
{
  return std::isfinite(b.left) && std::isfinite(b.top) &&
    std::isfinite(b.right) && std::isfinite(b.bottom) &&
    b.left >= 0 && b.top >= 0 && b.right <= 1 && b.bottom <= 1 &&
    b.left < b.right && b.top < b.bottom;
}

inline bool FullView(const Box & b, double margin = .02)
{
  return Valid(b) && std::isfinite(margin) && margin >= 0 && margin < .5 &&
    b.left > margin && b.top > margin && b.right < 1 - margin && b.bottom < 1 - margin;
}

inline bool Associated(const Box & a, const Box & b, double maximum_shift = .12)
{
  if (!Valid(a) || !Valid(b) || !std::isfinite(maximum_shift) || maximum_shift <= 0) {
    return false;
  }
  const double dx = (a.left + a.right - b.left - b.right) / 2;
  const double dy = (a.top + a.bottom - b.top - b.bottom) / 2;
  return std::hypot(dx, dy) <= maximum_shift;
}

inline bool InsideImageJaws(const Box & object, const Box & measured_jaw_region)
{
  return FullView(object) && Valid(measured_jaw_region) &&
    object.left >= measured_jaw_region.left && object.right <= measured_jaw_region.right &&
    object.top >= measured_jaw_region.top && object.bottom <= measured_jaw_region.bottom;
}

// Change the pose goal, not joint output. Bound TIP travel and attitude independently;
// wrist translation includes the change in tool offset when its attitude changes.
inline grasp_geometry::DirectedPose TipMicrostep(
  const grasp_geometry::DirectedPose & current, const grasp_geometry::Point & face,
  double tip_offset, double insertion, double maximum_tip_step, double maximum_angle)
{
  namespace gg = grasp_geometry;
  for (double v : {tip_offset, insertion, maximum_tip_step, maximum_angle}) {
    if (!std::isfinite(v) || v <= 0) {throw std::invalid_argument("Invalid visual microstep");}
  }
  if (insertion >= tip_offset || maximum_angle > .035) {
    throw std::invalid_argument("Unbounded visual microstep");
  }
  const gg::Point ray{face[0] - current.origin[0], face[1] - current.origin[1],
    face[2] - current.origin[2]};
  const auto aimed = gg::AimTool(current.orientation, ray);
  const double angle = gg::QuaternionDistance(current.orientation, aimed);
  const auto q = gg::Slerp(current.orientation, aimed,
    angle > maximum_angle ? maximum_angle / angle : 1.0);
  const auto old_axis = gg::Rotate(current.orientation, {0, 0, 1});
  const auto axis = gg::Rotate(q, {0, 0, 1});
  const auto tip = gg::Tip(current.origin, old_axis, tip_offset);
  gg::Point delta{};
  for (std::size_t i = 0; i < 3; ++i) {delta[i] = face[i] + axis[i] * insertion - tip[i];}
  const double distance = std::sqrt(gg::Dot(delta, delta));
  if (!std::isfinite(distance)) {throw std::invalid_argument("Non-finite visual face");}
  const double scale = distance > maximum_tip_step ? maximum_tip_step / distance : 1;
  gg::Point origin{};
  for (std::size_t i = 0; i < 3; ++i) {
    origin[i] = tip[i] + delta[i] * scale - axis[i] * tip_offset;
  }
  return {origin, q};
}

// Advance a checked pose path using an ORIGINAL-RGB lateral correction.
// The correction is an estimate at the locked model range, not new depth.
inline grasp_geometry::DirectedPose CorrectedPoseStep(
  const grasp_geometry::DirectedPose & current,
  const grasp_geometry::DirectedPose & nominal_goal,
  const grasp_geometry::Point & correction, double tip_offset,
  double maximum_tip_step, double maximum_angle, double maximum_correction)
{
  namespace gg = grasp_geometry;
  for (double value : {tip_offset, maximum_tip_step, maximum_angle, maximum_correction}) {
    if (!std::isfinite(value) || value <= 0) {
      throw std::invalid_argument("Invalid RGB pose-step bounds");
    }
  }
  for (double value : correction) {
    if (!std::isfinite(value)) {throw std::invalid_argument("Invalid RGB correction");}
  }
  const auto old_tip = gg::Tip(current.origin, gg::Rotate(current.orientation, {0, 0, 1}), tip_offset);
  auto goal_tip = gg::Tip(nominal_goal.origin, gg::Rotate(nominal_goal.orientation, {0, 0, 1}), tip_offset);
  const double correction_length = std::sqrt(gg::Dot(correction, correction));
  const double bounded = correction_length > maximum_correction ?
    maximum_correction / correction_length : 1.;
  gg::Point delta{};
  for (std::size_t i = 0; i < 3; ++i) {
    goal_tip[i] += correction[i] * bounded;
    delta[i] = goal_tip[i] - old_tip[i];
  }
  const double distance = std::sqrt(gg::Dot(delta, delta));
  const double angle = gg::QuaternionDistance(current.orientation, nominal_goal.orientation);
  double fraction = 1.;
  if (distance > maximum_tip_step) {fraction = maximum_tip_step / distance;}
  if (angle > maximum_angle) {fraction = std::min(fraction, maximum_angle / angle);}
  const auto q = gg::Slerp(current.orientation, nominal_goal.orientation, fraction);
  const auto axis = gg::Rotate(q, {0, 0, 1});
  gg::Point origin{};
  for (std::size_t i = 0; i < 3; ++i) {
    origin[i] = old_tip[i] + delta[i] * fraction - axis[i] * tip_offset;
  }
  return {origin, q};
}
}  // namespace brain_robot_pick_place::visual_grasp
