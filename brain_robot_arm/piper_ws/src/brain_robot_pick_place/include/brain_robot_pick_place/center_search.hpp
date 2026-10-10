#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace brain_robot_pick_place::search
{
struct Point
{
  double horizontal;
  double vertical;
};

struct Bounds
{
  double horizontal_min;
  double horizontal_max;
  double vertical_min;
  double vertical_max;

  Point Clamp(Point point) const
  {
    return {std::clamp(point.horizontal, horizontal_min, horizontal_max),
      std::clamp(point.vertical, vertical_min, vertical_max)};
  }
};

inline double BoundedStep(double current, double target, double maximum_step)
{
  return current + std::clamp(target - current, -maximum_step, maximum_step);
}

inline bool BoundaryReached(double current, double boundary, int direction, double tolerance)
{
  return direction > 0 ? current >= boundary - tolerance : current <= boundary + tolerance;
}

enum class CenterPhase {INACTIVE, HOLD, LOCAL_SCAN, RETURN_CENTER, COMPLETE};

inline const char * PhaseName(CenterPhase phase)
{
  switch (phase) {
    case CenterPhase::HOLD: return "CENTER_HOLD";
    case CenterPhase::LOCAL_SCAN: return "CENTER_LOCAL_SCAN";
    case CenterPhase::RETURN_CENTER: return "CENTER_RETURN";
    case CenterPhase::COMPLETE: return "CENTER_COMPLETE";
    default: return "CENTER_INACTIVE";
  }
}

struct CenterAction
{
  CenterPhase phase;
  Point target;
  std::size_t index;
};

// Only the prefix to the existing full-search pattern. The caller checks fresh
// feedback and target acquisition FIRST, and plans every move through MoveIt.
class CenterFirstSearch
{
public:
  void Reset(Point center, Bounds bounds, double horizontal_range, double vertical_range,
    double hold_seconds, double now)
  {
    const double values[] = {center.horizontal, center.vertical, bounds.horizontal_min,
      bounds.horizontal_max, bounds.vertical_min, bounds.vertical_max, horizontal_range,
      vertical_range, hold_seconds, now};
    for (double value : values) {
      if (!std::isfinite(value)) {
        throw std::invalid_argument("Non-finite center search parameter");
      }
    }
    if (bounds.horizontal_min >= bounds.horizontal_max ||
      bounds.vertical_min >= bounds.vertical_max || horizontal_range <= 0.0 ||
      vertical_range <= 0.0 || hold_seconds < 0.0)
    {
      throw std::invalid_argument("Invalid center search bounds/range/hold");
    }
    center_ = bounds.Clamp(center);
    const double h = horizontal_range;
    const double v = vertical_range;
    // Both horizontal sides close to center, then the two nearby vertical
    // rows. A separate final CENTER_RETURN must be measured, not timed out.
    points_ = {{center_.horizontal + h, center_.vertical},
      {center_.horizontal - h, center_.vertical},
      {center_.horizontal, center_.vertical + v},
      {center_.horizontal + h, center_.vertical + v},
      {center_.horizontal - h, center_.vertical + v},
      {center_.horizontal, center_.vertical - v},
      {center_.horizontal + h, center_.vertical - v},
      {center_.horizontal - h, center_.vertical - v}};
    for (auto & point : points_) {
      point = bounds.Clamp(point);
    }
    index_ = 0;
    hold_until_ = now + hold_seconds;
    phase_ = CenterPhase::HOLD;
  }

  bool Active() const
  {
    return phase_ == CenterPhase::HOLD || phase_ == CenterPhase::LOCAL_SCAN ||
           phase_ == CenterPhase::RETURN_CENTER;
  }

  void Cancel() {phase_ = CenterPhase::INACTIVE;}

  CenterAction Tick(double now, Point measured, double tolerance)
  {
    if (!std::isfinite(now) || !std::isfinite(measured.horizontal) ||
      !std::isfinite(measured.vertical) || !std::isfinite(tolerance) || tolerance <= 0.0)
    {
      throw std::invalid_argument("Invalid measured center search state");
    }
    if (phase_ == CenterPhase::HOLD && now >= hold_until_) {
      phase_ = CenterPhase::LOCAL_SCAN;
    }
    if (phase_ == CenterPhase::LOCAL_SCAN && Reached(measured, points_[index_], tolerance)) {
      if (++index_ == points_.size()) {
        phase_ = CenterPhase::RETURN_CENTER;
      }
    }
    if (phase_ == CenterPhase::RETURN_CENTER && Reached(measured, center_, tolerance)) {
      phase_ = CenterPhase::COMPLETE;
    }
    return {phase_, phase_ == CenterPhase::LOCAL_SCAN ? points_[index_] : center_, index_};
  }

private:
  static bool Reached(Point actual, Point target, double tolerance)
  {
    return std::abs(actual.horizontal - target.horizontal) <= tolerance &&
           std::abs(actual.vertical - target.vertical) <= tolerance;
  }
  CenterPhase phase_{CenterPhase::INACTIVE};
  Point center_{0.0, 0.0};
  std::vector<Point> points_;
  std::size_t index_{0};
  double hold_until_{0.0};
};
}  // namespace brain_robot_pick_place::search
