#include <libobsensor/h/Utils.h>
#include <libobsensor/h/Error.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <string>

// Offline math only. No context, device, pipeline, stream, or ROS is created.
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  std::ifstream input(argv[1]);
  nlohmann::json factory;
  input >> factory;
  const auto intr = factory.at("color_intrinsics").get<std::array<double, 4>>();
  const auto rot = factory.at("depth_to_color_rotation").get<std::array<double, 9>>();
  const auto trans = factory.at("depth_to_color_translation_mm").get<std::array<double, 3>>();
  OBCalibrationParam calibration{};
  calibration.intrinsics[OB_SENSOR_COLOR] = {
    static_cast<float>(intr[0]), static_cast<float>(intr[1]),
    static_cast<float>(intr[2]), static_cast<float>(intr[3]), 640, 480};
  auto &extrinsics = calibration.extrinsics[OB_SENSOR_DEPTH][OB_SENSOR_COLOR];
  for (int i = 0; i < 9; ++i) extrinsics.rot[i] = static_cast<float>(rot[i]);
  for (int i = 0; i < 3; ++i) extrinsics.trans[i] = static_cast<float>(trans[i]);
  const std::array<std::array<double, 3>, 3> points_m = {{{0, 0, .186},
    {-.0018, .0659, .186}, {0, 0, .35}}};
  nlohmann::json report = {
    {"device_opened", false}, {"ros_initialized", false}, {"motion_sent", false},
    {"library", "/usr/local/lib/libOrbbecSDK.so.1.10.8"},
    {"factory_source", argv[1]}, {"serial", factory.at("serial")},
    {"scope", "Verify row-major R*P+t projection against installed official pure functions; not independent proof of raw OpenNI r2l direction."},
    {"distortion", "Zero coefficients to match the present detector projection."},
    {"sdk_length_unit", "mm"}, {"output_image_size", {640, 480}},
    {"samples", nlohmann::json::array()}};
  double max_pixel_error = 0;
  bool all_ok = true;
  for (const auto &point : points_m) {
    const OBPoint3f source{static_cast<float>(point[0] * 1000),
      static_cast<float>(point[1] * 1000), static_cast<float>(point[2] * 1000)};
    OBPoint3f sdk_color{};
    OBPoint2f sdk_pixel{};
    ob_error *error3d = nullptr, *error2d = nullptr;
    const bool ok3d = ob_calibration_3d_to_3d(calibration, source, OB_SENSOR_DEPTH,
      OB_SENSOR_COLOR, &sdk_color, &error3d);
    const bool ok2d = ob_calibration_3d_to_2d(calibration, source, OB_SENSOR_DEPTH,
      OB_SENSOR_COLOR, &sdk_pixel, &error2d);
    std::array<double, 3> manual_color{};
    for (int row = 0; row < 3; ++row) {
      manual_color[row] = trans[row];
      for (int col = 0; col < 3; ++col)
        manual_color[row] += rot[3 * row + col] * point[col] * 1000;
    }
    const std::array<double, 2> manual_pixel = {
      intr[0] * manual_color[0] / manual_color[2] + intr[2],
      intr[1] * manual_color[1] / manual_color[2] + intr[3]};
    const double pixel_error = std::hypot(sdk_pixel.x - manual_pixel[0],
      sdk_pixel.y - manual_pixel[1]);
    max_pixel_error = std::max(max_pixel_error, pixel_error);
    nlohmann::json sample = {
      {"depth_point_m", point}, {"sdk_input_point_mm", {source.x, source.y, source.z}},
      {"sdk_3d_success", ok3d}, {"sdk_2d_success", ok2d},
      {"sdk_color_point_mm", {sdk_color.x, sdk_color.y, sdk_color.z}},
      {"manual_color_point_mm", manual_color},
      {"sdk_color_pixel", {sdk_pixel.x, sdk_pixel.y}},
      {"manual_color_pixel", manual_pixel}, {"pixel_error_norm", pixel_error}};
    if (error3d) { sample["sdk_3d_error"] = ob_error_message(error3d); ob_delete_error(error3d); }
    if (error2d) { sample["sdk_2d_error"] = ob_error_message(error2d); ob_delete_error(error2d); }
    all_ok = all_ok && ok3d && ok2d && pixel_error < .001;
    report["samples"].push_back(sample);
  }
  report["max_pixel_error_norm"] = max_pixel_error;
  report["pass_under_0_001_pixel"] = all_ok;
  std::cout << report.dump(2) << '\n';
  return all_ok ? 0 : 1;
}
