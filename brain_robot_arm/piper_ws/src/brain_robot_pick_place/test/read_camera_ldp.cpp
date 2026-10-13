// Camera-only diagnostic: property reads and ordinary depth streaming.
// No property writes, protection overrides, ROS publishers, or arm interfaces.
#include <OpenNI.h>
#include <PS1080.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <iostream>
#include <array>

using nlohmann::json;
static json read_properties(openni::Device & device) {
  json result = json::array();
  const std::array<std::pair<const char *, int>, 7> properties{{
    {"emitter_state", XN_MODULE_PROPERTY_EMITTER_STATE},
    {"emitter_state_v1", XN_MODULE_PROPERTY_EMITTER_STATE_V1},
    {"ldp_enable", XN_MODULE_PROPERTY_LDP_ENABLE},
    {"ldp_status", XN_MODULE_PROPERTY_LDP_STATUS},
    {"ldp_threshold_high_raw_not_mm", XN_MODULE_PROPERTY_LDP_THRES_UP},
    {"ldp_threshold_low_raw_not_mm", XN_MODULE_PROPERTY_LDP_THRES_LOW},
    {"ldp_proximity_raw_not_mm", XN_MODULE_PROPERTY_LDP_PS_DATA}}};
  for (const auto & [name, id] : properties) {
    uint32_t value = 0; int size = sizeof(value);
    const auto rc = device.getProperty(id, &value, &size);
    json row{{"name", name}, {"id", id}, {"status", int(rc)}, {"bytes", size}};
    if (rc == openni::STATUS_OK) {row["raw_value"] = value;}
    else {row["error"] = openni::OpenNI::getExtendedError();}
    result.push_back(row);
  }
  return result;
}

int main() {
  if (openni::OpenNI::initialize() != openni::STATUS_OK) {return 2;}
  int result = 0;
  {
    openni::Device device;
    if (device.open(openni::ANY_DEVICE) != openni::STATUS_OK) {
      std::cerr << openni::OpenNI::getExtendedError(); return 3;
    }
    json report{{"camera_only", true}, {"protection_settings_written", false},
      {"uri", device.getDeviceInfo().getUri()}, {"device_name", device.getDeviceInfo().getName()},
      {"before_stream", read_properties(device)}, {"samples", json::array()}};
    openni::VideoStream depth;
    bool native_mode = false;
    if (depth.create(device, openni::SENSOR_DEPTH) == openni::STATUS_OK) {
      const auto & modes = depth.getSensorInfo().getSupportedVideoModes();
      for (int i = 0; i < modes.getSize(); ++i) {
        const auto & mode = modes[i];
        if (mode.getResolutionX() == 640 && mode.getResolutionY() == 400 &&
          mode.getFps() == 30 && mode.getPixelFormat() == openni::PIXEL_FORMAT_DEPTH_1_MM) {
          // Same ordinary streaming profile as the production camera node;
          // this does not modify laser, LDP, or firmware parameters.
          native_mode = depth.setVideoMode(mode) == openni::STATUS_OK; break;
        }
      }
    }
    report["native_depth_mode"] = {640, 400, 30};
    if (!native_mode || depth.start() != openni::STATUS_OK) {result = 4;}
    else {
      // Bounded by five seconds and an external timeout; never move an object.
      const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(5);
      auto next_sample = std::chrono::steady_clock::now();
      while (std::chrono::steady_clock::now() < end) {
        openni::VideoStream * stream = &depth; int changed = -1;
        if (openni::OpenNI::waitForAnyStream(&stream, 1, &changed, 500) != openni::STATUS_OK) {continue;}
        openni::VideoFrameRef frame;
        if (depth.readFrame(&frame) != openni::STATUS_OK) {continue;}
        if (std::chrono::steady_clock::now() < next_sample) {continue;}
        next_sample = std::chrono::steady_clock::now() + std::chrono::seconds(1);
        const auto * data = static_cast<const openni::DepthPixel *>(frame.getData());
        std::size_t nonzero = 0, pixels = 0;
        for (int y = 0; y < frame.getHeight(); ++y) {
          const auto * line = reinterpret_cast<const openni::DepthPixel *>(
            reinterpret_cast<const char *>(data) + y * frame.getStrideInBytes());
          for (int x = 0; x < frame.getWidth(); ++x) {++pixels; if (line[x]) {++nonzero;}}
        }
        report["samples"].push_back({{"epoch_s", std::chrono::duration<double>(
          std::chrono::system_clock::now().time_since_epoch()).count()},
          {"frame_index", frame.getFrameIndex()}, {"nonzero_pixels", nonzero},
          {"pixels", pixels}, {"properties", read_properties(device)}});
      }
      depth.stop();
      if (report["samples"].empty()) {result = 5;}
    }
    report["exit_code"] = result;
    depth.destroy(); device.close(); std::cout << report.dump(2) << '\n';
  }
  openni::OpenNI::shutdown(); return result;
}
