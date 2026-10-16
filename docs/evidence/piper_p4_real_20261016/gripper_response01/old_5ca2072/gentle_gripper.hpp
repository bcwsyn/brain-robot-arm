#pragma once

#include <algorithm>
#include <cmath>
#include <deque>
#include <stdexcept>
#include <utility>
#include <vector>

namespace brain_robot_pick_place
{
// Reference rates / torque thresholds are initial test settings, NOT certified
// fingertip speed or force. Input effort is protocol N.m, not raw current.
class GentleGripper
{
public:
  enum class Result { MOVING, CONTACT_CANDIDATE, EMPTY, INVALID };
  explicit GentleGripper(double edge, double initial_opening)
  : reference_(initial_opening),
    minimum_(std::max(.002, edge - .004)),
    preclose_(std::min(.095, std::sqrt(3.) * edge + .006))
  {
    if (!std::isfinite(edge) || edge < .01 || edge > .05 ||
      !std::isfinite(initial_opening) || initial_opening < 0 || initial_opening > .103)
    {
      throw std::invalid_argument("Invalid cube size or measured gripper opening");
    }
    reference_ = std::min(.100, reference_);
  }
  double Reference() const {return reference_;}
  double Minimum() const {return minimum_;}
  double Preclose() const {return preclose_;}
  double Timeout(double initial) const
  {
    return std::max(0., initial-preclose_)/.010 +
           std::max(0., preclose_-minimum_)/.003 + 5.;
  }
  Result Update(double stamp, double opening, double effort)
  {
    if (!std::isfinite(stamp) || !std::isfinite(opening) || !std::isfinite(effort) ||
      opening < 0 || opening > .103)
    {
      return Result::INVALID;
    }
    if (started_ && stamp <= previous_stamp_) {return Result::INVALID;}
    const double dt = started_ ? std::min(.10, stamp-previous_stamp_) : 0.;
    started_ = true;
    previous_stamp_ = stamp;
    samples_.emplace_back(stamp, opening);
    while (samples_.size() > 1 && stamp-samples_[1].first >= .20) {samples_.pop_front();}
    const double span = stamp-samples_.front().first;
    const double speed = span >= .18 ?
      std::abs(opening-samples_.front().second)/span : INFINITY;
    if (opening > preclose_+.003 && std::isfinite(effort)) {
      baseline_.push_back(std::abs(effort));
      if (baseline_.size() > 30) {baseline_.pop_front();}
    }
    std::vector<double> sorted(baseline_.begin(), baseline_.end());
    std::sort(sorted.begin(), sorted.end());
    const double baseline = sorted.empty() ? 0. : sorted[sorted.size()/2];
    const bool supported = sorted.size() >= 5;
    const bool near_object = opening >= minimum_+.001 && opening <= preclose_;
    const bool contact = supported && near_object && speed <= .001 &&
      reference_ <= opening-.0003 && std::abs(effort) >= baseline+.12;
    if (contact) {
      if (contact_since_ < 0) {contact_since_ = stamp;}
      if (stamp-contact_since_ >= .25) {
        reference_ = std::clamp(opening-.0002, 0., .100);
        return Result::CONTACT_CANDIDATE;
      }
    } else {contact_since_ = -1.;}
    if (reference_ <= minimum_+1e-9 && std::abs(opening-reference_) <= .0003) {
      if (empty_since_ < 0) {empty_since_ = stamp;}
      if (stamp-empty_since_ >= .25) {return Result::EMPTY;}
    } else {empty_since_ = -1.;}
    const double rate = reference_ > preclose_ ? .010 : .003;
    // Only a short reference lead is permitted. A stalled/slow device cannot
    // accumulate a remote closed-endpoint command behind it.
    reference_ = std::clamp(std::max({minimum_, reference_-rate*dt, opening-.0005}),
      0., .100);
    return Result::MOVING;
  }
private:
  double reference_, minimum_, preclose_;
  bool started_{false};
  double previous_stamp_{0}, contact_since_{-1}, empty_since_{-1};
  std::deque<std::pair<double, double>> samples_;
  std::deque<double> baseline_;
};
}  // namespace brain_robot_pick_place
