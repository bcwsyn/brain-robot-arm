#pragma once

#include "brain_robot_pick_place/target_directed_grasp.hpp"

namespace brain_robot_pick_place::visual_grasp
{
// Normalized coordinates in ORIGINAL colour image, never registered depth pixels.
struct Box {double left, top, right, bottom;};

// Keep the existing Servo gain's pixel scale while using the ORIGINAL RGB
// centre. Depth registration is for range association, not ALIGN's reference.
inline grasp_geometry::Point RgbAlignmentError(double x, double y,
  double rgb_width, double rgb_height, double command_width, double command_height)
{
  for (double value : {x, y, rgb_width, rgb_height, command_width, command_height}) {
    if (!std::isfinite(value)) {throw std::invalid_argument("Invalid RGB alignment grid");}
  }
  if (rgb_width <= 1 || rgb_height <= 1 || command_width <= 1 || command_height <= 1) {
    throw std::invalid_argument("Invalid RGB alignment dimensions");
  }
  const double dx = x / rgb_width - .5, dy = y / rgb_height - .5;
  return {dx * command_width, dy * command_height, std::max(std::abs(dx), std::abs(dy))};
}

// FK solver roundoff is not physical overtravel. Preview remains unchanged.
inline bool DistanceStepWithin(double distance, double limit, bool automatic)
{
  return std::isfinite(distance) && std::isfinite(limit) && distance >= 0 && limit > 0 &&
         distance <= limit + (automatic ? 1e-6 : 1e-9);
}

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
  // A large view-restoration angle must not throttle a valid tip descent.
  // Both limits remain unchanged; MoveIt checks the resulting pose/path.
  const double tip_fraction = distance > maximum_tip_step ? maximum_tip_step / distance : 1.;
  const double angle_fraction = angle > maximum_angle ? maximum_angle / angle : 1.;
  const auto q = gg::Slerp(current.orientation, nominal_goal.orientation, angle_fraction);
  const auto axis = gg::Rotate(q, {0, 0, 1});
  gg::Point origin{};
  for (std::size_t i = 0; i < 3; ++i) {
    origin[i] = old_tip[i] + delta[i] * tip_fraction - axis[i] * tip_offset;
  }
  return {origin, q};
}

// Rotate the tool/camera about the desired TIP, not about the wrist. Solve the
// camera lever-arm geometry before changing attitude; impossible rays leave the
// original pose untouched (they are not permission to displace the capture tip).
inline bool AimCameraAtFixedTip(
  grasp_geometry::DirectedPose & goal,
  const grasp_geometry::DirectedPose & tool_from_camera,
  const grasp_geometry::Point & target, const grasp_geometry::Point & camera_ray,
  double tip_offset)
{
  namespace gg = grasp_geometry;
  const auto tip = gg::Tip(goal.origin, gg::Rotate(goal.orientation, {0, 0, 1}), tip_offset);
  const gg::Point lever{tool_from_camera.origin[0], tool_from_camera.origin[1],
    tool_from_camera.origin[2] - tip_offset};
  const auto bearing = gg::Rotate(tool_from_camera.orientation, gg::Unit(camera_ray));
  const gg::Point wanted{target[0] - tip[0], target[1] - tip[1], target[2] - tip[2]};
  const double ab = gg::Dot(lever, bearing);
  const double discriminant = ab*ab - gg::Dot(lever, lever) + gg::Dot(wanted, wanted);
  if (!std::isfinite(discriminant) || discriminant < -1e-12) {return false;}
  const double root = std::sqrt(std::max(0., discriminant));
  const double range = -ab + root > 0 ? -ab + root : -ab - root;
  if (range <= .001 || gg::Dot(wanted, wanted) < 1e-12) {return false;}
  const gg::Point local{lever[0] + range*bearing[0], lever[1] + range*bearing[1],
    lever[2] + range*bearing[2]};
  const auto from = gg::Unit(gg::Rotate(goal.orientation, local));
  const auto to = gg::Unit(wanted);
  const double angle = std::acos(std::clamp(gg::Dot(from, to), -1., 1.));
  if (angle > 1e-8) {
    auto axis = gg::Cross(from, to);
    if (gg::Dot(axis, axis) < 1e-12) {axis = gg::Rotate(goal.orientation, {1, 0, 0});}
    goal.orientation = gg::UnitQuaternion(gg::RotateOrientationAboutAxis(
      goal.orientation, gg::Unit(axis), angle));
  }
  const auto axis = gg::Rotate(goal.orientation, {0, 0, 1});
  for (int i = 0; i < 3; ++i) {goal.origin[i] = tip[i] - tip_offset*axis[i];}
  return true;
}

// If the camera lever arm makes a fixed-tip ray impossible, recover with a
// bounded attitude change AND lateral translation. This is a pose estimate,
// not a replacement target or a joint command. CorrectedPoseStep and MoveIt
// still bound/check the actually requested motion.
inline bool AimCameraWithTranslation(
  grasp_geometry::DirectedPose & goal,
  const grasp_geometry::DirectedPose & tool_from_camera,
  const grasp_geometry::Point & target, const grasp_geometry::Point & camera_ray,
  double tip_offset, double maximum_angle, double maximum_translation,
  bool & translated)
{
  namespace gg = grasp_geometry;
  translated = false;
  if (!std::isfinite(maximum_angle) || maximum_angle <= 0 ||
    !std::isfinite(maximum_translation) || maximum_translation <= 0) {
    throw std::invalid_argument("Invalid camera recovery bounds");
  }
  if (AimCameraAtFixedTip(goal, tool_from_camera, target, camera_ray, tip_offset)) {return true;}
  const auto original = goal;
  const auto tip = gg::Tip(goal.origin, gg::Rotate(goal.orientation, {0, 0, 1}), tip_offset);
  const auto camera_offset = gg::Rotate(goal.orientation, tool_from_camera.origin);
  const gg::Point wanted{target[0]-goal.origin[0]-camera_offset[0],
    target[1]-goal.origin[1]-camera_offset[1], target[2]-goal.origin[2]-camera_offset[2]};
  const auto bearing = gg::Rotate(tool_from_camera.orientation, gg::Unit(camera_ray));
  const auto from = gg::Rotate(goal.orientation, bearing), to = gg::Unit(wanted);
  const double angle = std::acos(std::clamp(gg::Dot(from, to), -1., 1.));
  if (angle > 1e-8) {
    auto axis = gg::Cross(from, to);
    if (gg::Dot(axis, axis) < 1e-12) {axis = gg::Rotate(goal.orientation, {1, 0, 0});}
    goal.orientation = gg::UnitQuaternion(gg::RotateOrientationAboutAxis(
      goal.orientation, gg::Unit(axis), std::min(angle, maximum_angle)));
  }
  const auto tool_axis = gg::Rotate(goal.orientation, {0, 0, 1});
  for (int i = 0; i < 3; ++i) {goal.origin[i] = tip[i]-tip_offset*tool_axis[i];}
  const auto offset = gg::Rotate(goal.orientation, tool_from_camera.origin);
  const gg::Point world_ray{target[0]-goal.origin[0]-offset[0],
    target[1]-goal.origin[1]-offset[1], target[2]-goal.origin[2]-offset[2]};
  const auto q = goal.orientation, cq = tool_from_camera.orientation;
  const auto tool_ray = gg::Rotate({-q[0], -q[1], -q[2], q[3]}, world_ray);
  const auto color = gg::Rotate({-cq[0], -cq[1], -cq[2], cq[3]}, tool_ray);
  if (!std::isfinite(color[2]) || color[2] <= .001 || camera_ray[2] <= .001) {
    goal = original; return false;
  }
  const gg::Point lateral{color[0]-color[2]*camera_ray[0]/camera_ray[2],
    color[1]-color[2]*camera_ray[1]/camera_ray[2], 0};
  const auto shift = gg::Rotate(q, gg::Rotate(cq, lateral));
  const double distance = std::sqrt(gg::Dot(shift, shift));
  const double scale = distance > maximum_translation ? maximum_translation/distance : 1.;
  for (int i = 0; i < 3; ++i) {goal.origin[i] += shift[i]*scale;}
  translated = distance > 1e-8;
  return translated || gg::QuaternionDistance(original.orientation, goal.orientation) > 1e-8;
}
}  // namespace brain_robot_pick_place::visual_grasp
