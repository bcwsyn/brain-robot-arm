#pragma once

#include <vector>
#include "brain_robot_pick_place/grasp_geometry.hpp"

namespace brain_robot_pick_place::grasp_geometry
{
inline double Dot(const Point & a, const Point & b)
{
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

inline Point Cross(const Point & a, const Point & b)
{
  return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]};
}

inline Point Unit(const Point & p)
{
  const double squared = Dot(p, p);
  if (!std::isfinite(squared) || squared < 1e-12) {
    throw std::invalid_argument("Undefined approach direction");
  }
  const double norm = std::sqrt(squared);
  return {p[0] / norm, p[1] / norm, p[2] / norm};
}

inline Quaternion UnitQuaternion(Quaternion q)
{
  double squared = 0.0;
  for (const double v : q) {
    if (!std::isfinite(v)) {throw std::invalid_argument("Invalid approach quaternion");}
    squared += v * v;
  }
  if (!std::isfinite(squared) || squared < 1e-12) {
    throw std::invalid_argument("Undefined approach quaternion");
  }
  for (double & v : q) {v /= std::sqrt(squared);}
  return q;
}

inline Point Rotate(const Quaternion & orientation, const Point & p)
{
  const auto q = UnitQuaternion(orientation);
  const Point xyz{q[0], q[1], q[2]};
  const auto c = Cross(xyz, p);
  const auto cc = Cross(xyz, c);
  return {p[0] + 2 * (q[3] * c[0] + cc[0]),
    p[1] + 2 * (q[3] * c[1] + cc[1]), p[2] + 2 * (q[3] * c[2] + cc[2])};
}

// Shortest swing of the current tool +Z onto the desired direction. This
// preserves wrist twist as closely as possible, rather than choosing cube-edge yaw.
inline Quaternion AimTool(const Quaternion & reference, const Point & direction)
{
  const auto q = UnitQuaternion(reference);
  const auto from = Rotate(q, {0, 0, 1});
  const auto to = Unit(direction);
  const double cosine = std::clamp(Dot(from, to), -1.0, 1.0);
  if (cosine > 1.0 - 1e-12) {return q;}
  const auto axis = cosine < -1.0 + 1e-10 ?
    Rotate(q, {1, 0, 0}) : Unit(Cross(from, to));
  return UnitQuaternion(RotateOrientationAboutAxis(q, axis, std::acos(cosine)));
}

inline Quaternion Slerp(Quaternion a, Quaternion b, double s)
{
  if (!std::isfinite(s) || s < 0.0 || s > 1.0) {
    throw std::invalid_argument("Invalid approach progress");
  }
  a = UnitQuaternion(a);
  b = UnitQuaternion(b);
  double dot = 0.0;
  for (std::size_t i = 0; i < a.size(); ++i) {dot += a[i] * b[i];}
  if (dot < 0.0) {
    for (double & v : b) {v = -v;}
    dot = -dot;
  }
  double wa = 1.0 - s;
  double wb = s;
  if (dot < 1.0 - 1e-8) {
    const double angle = std::acos(std::clamp(dot, -1.0, 1.0));
    wa = std::sin((1.0 - s) * angle) / std::sin(angle);
    wb = std::sin(s * angle) / std::sin(angle);
  }
  Quaternion q{};
  for (std::size_t i = 0; i < q.size(); ++i) {q[i] = wa * a[i] + wb * b[i];}
  return UnitQuaternion(q);
}

inline double QuaternionDistance(const Quaternion & a, const Quaternion & b)
{
  const auto qa = UnitQuaternion(a);
  const auto qb = UnitQuaternion(b);
  double dot = 0.0;
  for (std::size_t i = 0; i < qa.size(); ++i) {dot += qa[i] * qb[i];}
  return 2.0 * std::acos(std::clamp(std::abs(dot), 0.0, 1.0));
}

struct DirectedPose
{
  Point origin;
  Quaternion orientation;
};

struct DirectedApproach
{
  std::vector<DirectedPose> pregrasp;
  std::vector<DirectedPose> descent;
};

// A static visible surface is the same reference throughout this approach.
// First aim the jaws, not the camera, without translating the wrist; then
// smoothly swing toward the tabletop entry direction while closing the gap.
// The wrist is recomputed for every attitude, so the tip remains on a ray to
// this same surface. Final insertion retains a nonzero wrist-to-surface ray.
inline DirectedApproach TargetDirectedApproach(
  const Point & start_origin, const Quaternion & start_orientation,
  const Point & surface, double tip_offset_m, double pregrasp_gap_m,
  double insertion_m, double step_m, double downward_fraction = 1.0)
{
  for (const double v : {tip_offset_m, pregrasp_gap_m, insertion_m, step_m}) {
    if (!std::isfinite(v) || v <= 0.0) {
      throw std::invalid_argument("Invalid directed grasp lengths");
    }
  }
  if (insertion_m >= tip_offset_m || step_m < 1e-4) {
    throw std::invalid_argument("Invalid directed grasp insertion/step");
  }
  if (!std::isfinite(downward_fraction) || downward_fraction <= 0.0 ||
    downward_fraction > 1.0)
  {
    throw std::invalid_argument("Invalid target-directed downward fraction");
  }
  const Point delta{surface[0] - start_origin[0], surface[1] - start_origin[1],
    surface[2] - start_origin[2]};
  const auto ray = Unit(delta);
  const double start_radius = std::sqrt(Dot(delta, delta));
  const double pre_radius = tip_offset_m + pregrasp_gap_m;
  const double final_radius = tip_offset_m - insertion_m;
  if (start_radius <= pre_radius) {
    throw std::invalid_argument("Directed grasp start is inside the pregrasp gap");
  }
  const auto q0 = UnitQuaternion(start_orientation);
  const auto aimed = AimTool(q0, ray);
  // 1 is vertical entry; a smaller fraction is a geometry-derived slanted
  // entry, not a fixed joint angle. Full vertical entry may be unreachable.
  const auto final = Slerp(aimed, AimTool(aimed, {0, 0, -1}), downward_fraction);
  DirectedApproach result;
  const double angular_step = std::min(0.02, step_m / start_radius);
  const auto aim_steps = static_cast<std::size_t>(std::max(
      1.0, std::ceil(QuaternionDistance(q0, aimed) / angular_step)));
  for (std::size_t i = 1; i <= aim_steps; ++i) {
    result.pregrasp.push_back({start_origin, Slerp(q0, aimed, double(i) / aim_steps)});
  }
  const double swing = QuaternionDistance(aimed, final);
  const double total_radius_change = start_radius - final_radius;
  const double pre_progress = (start_radius - pre_radius) / total_radius_change;
  const auto add_segment = [&](double first, double last, std::vector<DirectedPose> & output) {
      const double travel_bound = total_radius_change + start_radius * swing;
      const auto count = static_cast<std::size_t>(std::max(1.0,
          std::ceil((last - first) * std::max(travel_bound / step_m, swing / angular_step))));
      for (std::size_t i = 1; i <= count; ++i) {
        const double s = first + (last - first) * double(i) / count;
        const auto orientation = Slerp(aimed, final, s);
        const auto axis = Rotate(orientation, {0, 0, 1});
        const double radius = start_radius - total_radius_change * s;
        output.push_back({ToolOrigin(surface, axis, tip_offset_m, radius - tip_offset_m),
          orientation});
      }
    };
  add_segment(0.0, pre_progress, result.pregrasp);
  add_segment(pre_progress, 1.0, result.descent);
  return result;
}
}  // namespace brain_robot_pick_place::grasp_geometry
