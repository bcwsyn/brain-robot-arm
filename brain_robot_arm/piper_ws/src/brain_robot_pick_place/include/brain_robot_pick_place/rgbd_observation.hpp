#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <sstream>
#include <iomanip>
#include <string>
#include <vector>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/vector3.hpp>

namespace brain_robot_pick_place::rgbd_observation
{
// A single stamped standard diagnostic carries the observation AND its quality.
// Existing raw point, Bool and SEARCH interfaces remain unchanged.
struct Snapshot
{
  std_msgs::msg::Header header;
  bool qualified{false};
  bool color_center_covered{false};  // Original RGB contour; independent of depth quality.
  geometry_msgs::msg::Point point;
  geometry_msgs::msg::Vector3 size;
  double samples{0}, coverage{0}, span{0}, mad_m{0};
};

inline diagnostic_msgs::msg::DiagnosticArray Encode(const Snapshot & s)
{
  diagnostic_msgs::msg::DiagnosticArray message;
  message.header = s.header;
  diagnostic_msgs::msg::DiagnosticStatus status;
  status.name = "purple_cube_rgbd_observation/v2";
  status.level = s.qualified ? status.OK : status.WARN;
  status.message = s.qualified ? "QUALIFIED_SAME_FRAME_RGBD" : "RGBD_NOT_QUALIFIED";
  for (const auto & entry : std::vector<std::pair<std::string, double>>{
    {"qualified", s.qualified ? 1. : 0.}, {"x", s.point.x}, {"y", s.point.y}, {"z", s.point.z},
    {"color_center_covered", s.color_center_covered ? 1. : 0.},
    {"size_x", s.size.x}, {"size_y", s.size.y}, {"size_z", s.size.z},
    {"samples", s.samples}, {"coverage", s.coverage}, {"span", s.span}, {"mad_m", s.mad_m}})
  {
    diagnostic_msgs::msg::KeyValue value;
    value.key = entry.first;
    std::ostringstream text; text << std::setprecision(17) << entry.second;
    value.value = text.str(); status.values.push_back(value);
  }
  message.status.push_back(status);
  return message;
}

inline bool Decode(const diagnostic_msgs::msg::DiagnosticArray & m, Snapshot & out)
{
  if (m.status.size() != 1 || m.status[0].name != "purple_cube_rgbd_observation/v2" ||
    m.header.frame_id.empty() || (m.header.stamp.sec == 0 && m.header.stamp.nanosec == 0))
  {return false;}
  std::map<std::string, double> values;
  try {
    for (const auto & entry : m.status[0].values) {
      std::size_t end = 0;
      const double number = std::stod(entry.value, &end);
      if (end != entry.value.size() || !std::isfinite(number) ||
        !values.emplace(entry.key, number).second) {return false;}
    }
    Snapshot s; s.header = m.header;
    const double qualified = values.at("qualified");
    if (qualified != 0 && qualified != 1) {return false;}
    s.qualified = qualified == 1;
    const double center = values.at("color_center_covered");
    if (center != 0 && center != 1) {return false;}
    s.color_center_covered = center == 1;
    if (m.status[0].level != (s.qualified ? m.status[0].OK : m.status[0].WARN)) {return false;}
    s.point.x = values.at("x"); s.point.y = values.at("y"); s.point.z = values.at("z");
    s.size.x = values.at("size_x"); s.size.y = values.at("size_y"); s.size.z = values.at("size_z");
    s.samples = values.at("samples"); s.coverage = values.at("coverage");
    s.span = values.at("span"); s.mad_m = values.at("mad_m");
    if (s.samples < 0 || s.coverage < 0 || s.coverage > 1 || s.span < 0 || s.span > 1 ||
      s.mad_m < 0 || (s.qualified && (s.point.z <= 0 || s.size.x <= 0 ||
      s.size.y <= 0 || s.samples <= 0 || s.coverage <= 0 || s.span <= 0))) {return false;}
    out = s; return true;
  } catch (const std::exception &) {return false;}
}

// A decline requests a MODEL/RGB handoff, not a new motion-stop threshold.
// Ratios are relative to the same object's three latest qualified observations;
// no fixed distance, pixel count or cube size is used for this transition.
inline bool Declined(const Snapshot & current, const std::vector<Snapshot> & history)
{
  if (history.size() < 3) {return false;}
  std::array<double, 3> coverage{}, span{};
  for (std::size_t i = 0; i < 3; ++i) {
    if (!history[history.size()-3+i].qualified || history[history.size()-3+i].coverage <= 0 ||
      history[history.size()-3+i].span <= 0) {return false;}
    coverage[i] = history[history.size()-3+i].coverage;
    span[i] = history[history.size()-3+i].span;
  }
  if (!current.qualified) {return true;}
  std::sort(coverage.begin(), coverage.end()); std::sort(span.begin(), span.end());
  return current.coverage < .65*coverage[1] || current.span < .65*span[1];
}
}  // namespace brain_robot_pick_place::rgbd_observation
