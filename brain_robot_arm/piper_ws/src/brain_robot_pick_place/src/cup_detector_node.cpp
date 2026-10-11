#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <cv_bridge/cv_bridge.h>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/polygon_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <message_filters/synchronizer.h>
#include <opencv2/imgproc.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>

class CupDetectorNode final : public rclcpp::Node
{
public:
  CupDetectorNode()
  : Node("cup_detector")
  {
    rgb_topic_ = declare_parameter<std::string>(
      "rgb_topic", "/wrist_camera/wrist_camera/image_raw");
    depth_topic_ = declare_parameter<std::string>(
      "depth_topic", "/wrist_camera/wrist_camera/depth/image_raw");
    camera_info_topic_ = declare_parameter<std::string>(
      "camera_info_topic", "/wrist_camera/wrist_camera/camera_info");
    camera_optical_frame_ = declare_parameter<std::string>(
      "camera_optical_frame", "wrist_camera_optical_frame");
    debug_topic_ = declare_parameter<std::string>(
      "debug_topic", "/brain_robot_vision/debug_image");
    raw_bbox_publisher_ = create_publisher<geometry_msgs::msg::PolygonStamped>(
      "/brain_robot_vision/raw_color_bbox", rclcpp::QoS(1).reliable());
    raw_debug_publisher_ = create_publisher<sensor_msgs::msg::Image>(
      "/brain_robot_vision/raw_color_debug", rclcpp::QoS(1).reliable());
    raw_target_projection_publisher_ = create_publisher<geometry_msgs::msg::PointStamped>(
      "/brain_robot_vision/raw_target_projection", rclcpp::QoS(1).reliable());
    target_topic_ = declare_parameter<std::string>(
      "target_topic", "/brain_robot_vision/target_pixel");
    target_point_camera_topic_ = declare_parameter<std::string>(
      "target_point_camera_topic", "/brain_robot_vision/target_point_camera");
    target_size_topic_ = declare_parameter<std::string>(
      "target_size_topic", "/brain_robot_vision/target_size");
    error_topic_ = declare_parameter<std::string>(
      "error_topic", "/brain_robot_vision/pixel_error");
    valid_topic_ = declare_parameter<std::string>(
      "valid_topic", "/brain_robot_vision/target_valid");
    candidate_error_topic_ = declare_parameter<std::string>(
      "candidate_error_topic", "/brain_robot_vision/color_candidate_error");
    candidate_valid_topic_ = declare_parameter<std::string>(
      "candidate_valid_topic", "/brain_robot_vision/color_candidate_valid");
    depth_valid_topic_ = declare_parameter<std::string>(
      "depth_valid_topic", "/brain_robot_vision/depth_valid");
    depth_diagnostic_topic_ = declare_parameter<std::string>(
      "depth_diagnostic_topic", "/brain_robot_vision/depth_diagnostic");
    input_reliability_ = declare_parameter<std::string>("input_reliability", "reliable");
    software_registration_enabled_ = declare_parameter<bool>("software_registration_enabled", false);
    color_image_width_ = declare_parameter<int>("color_calibration_width", 640);
    color_image_height_ = declare_parameter<int>("color_calibration_height", 480);
    color_fx_ = declare_parameter<double>("color_fx", 0.0);
    color_fy_ = declare_parameter<double>("color_fy", 0.0);
    color_cx_ = declare_parameter<double>("color_cx", 0.0);
    color_cy_ = declare_parameter<double>("color_cy", 0.0);
    color_mirror_horizontal_ = declare_parameter<bool>("color_mirror_horizontal", false);
    depth_to_color_rotation_ = declare_parameter<std::vector<double>>(
      "depth_to_color_rotation", std::vector<double>{1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0});
    depth_to_color_translation_m_ = declare_parameter<std::vector<double>>(
      "depth_to_color_translation_m", std::vector<double>{0.0, 0.0, 0.0});

    hue_low_1_ = declare_parameter<int>("hue_low_1", 0);
    hue_high_1_ = declare_parameter<int>("hue_high_1", 12);
    hue_low_2_ = declare_parameter<int>("hue_low_2", 168);
    hue_high_2_ = declare_parameter<int>("hue_high_2", 179);
    saturation_min_ = declare_parameter<int>("saturation_min", 90);
    value_min_ = declare_parameter<int>("value_min", 70);
    min_area_px_ = declare_parameter<double>("min_area_px", 350.0);
    candidate_min_area_px_ = declare_parameter<double>("candidate_min_area_px", 40.0);
    candidate_max_aspect_ratio_ = declare_parameter<double>(
      "candidate_max_aspect_ratio", 4.0);
    max_area_px_ = declare_parameter<double>("max_area_px", 0.0);
    min_circularity_ = declare_parameter<double>("min_circularity", 0.0);
    min_rectangularity_ = declare_parameter<double>("min_rectangularity", 0.0);
    shape_use_rotated_rectangle_ = declare_parameter<bool>("shape_use_rotated_rectangle", false);
    min_aspect_ratio_ = declare_parameter<double>("min_aspect_ratio", 1.0);
    max_aspect_ratio_ = declare_parameter<double>("max_aspect_ratio", 0.0);
    target_label_ = declare_parameter<std::string>("target_label", "CUP");
    morphology_kernel_ = declare_parameter<int>("morphology_kernel", 5);
    sync_queue_size_ = declare_parameter<int>("sync_queue_size", 10);
    sync_age_penalty_ = declare_parameter<double>("sync_age_penalty", 0.05);
    min_depth_m_ = declare_parameter<double>("min_depth_m", 0.05);
    max_depth_m_ = declare_parameter<double>("max_depth_m", 3.0);
    min_depth_samples_ = declare_parameter<int>("min_depth_samples", 20);
    depth_erode_px_ = declare_parameter<int>("depth_erode_px", 3);
    max_depth_mad_m_ = declare_parameter<double>("max_depth_mad_m", 0.012);
    max_depth_frame_delta_m_ = declare_parameter<double>("max_depth_frame_delta_m", 0.030);
    required_depth_stable_frames_ = declare_parameter<int>("required_depth_stable_frames", 3);
    require_depth_for_target_valid_ = declare_parameter<bool>(
      "require_depth_for_target_valid", false);
    min_target_size_m_ = declare_parameter<double>("min_target_size_m", 0.0);
    max_target_size_m_ = declare_parameter<double>("max_target_size_m", 0.0);
    max_target_size_aspect_ratio_ = declare_parameter<double>(
      "max_target_size_aspect_ratio", 0.0);
    clamp_parameters();

    const auto output_qos = rclcpp::QoS(rclcpp::KeepLast(1)).reliable();
    debug_publisher_ = create_publisher<sensor_msgs::msg::Image>(debug_topic_, output_qos);
    target_publisher_ = create_publisher<geometry_msgs::msg::PointStamped>(
      target_topic_, output_qos);
    target_point_camera_publisher_ = create_publisher<geometry_msgs::msg::PointStamped>(
      target_point_camera_topic_, output_qos);
    target_size_publisher_ = create_publisher<geometry_msgs::msg::Vector3Stamped>(
      target_size_topic_, output_qos);
    error_publisher_ = create_publisher<geometry_msgs::msg::Vector3Stamped>(
      error_topic_, output_qos);
    valid_publisher_ = create_publisher<std_msgs::msg::Bool>(valid_topic_, output_qos);
    candidate_error_publisher_ = create_publisher<geometry_msgs::msg::Vector3Stamped>(
      candidate_error_topic_, output_qos);
    candidate_valid_publisher_ = create_publisher<std_msgs::msg::Bool>(
      candidate_valid_topic_, output_qos);
    depth_valid_publisher_ = create_publisher<std_msgs::msg::Bool>(
      depth_valid_topic_, output_qos);
    depth_diagnostic_publisher_ = create_publisher<std_msgs::msg::String>(
      depth_diagnostic_topic_, rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local());

    rclcpp::QoS input_qos(rclcpp::KeepLast(10));
    if (input_reliability_ == "best_effort") {
      input_qos.best_effort();
    } else {
      input_qos.reliable();
    }
    rgb_subscription_.subscribe(this, rgb_topic_, input_qos.get_rmw_qos_profile());
    depth_subscription_.subscribe(this, depth_topic_, input_qos.get_rmw_qos_profile());
    camera_info_subscription_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      camera_info_topic_, input_qos,
      [this](const sensor_msgs::msg::CameraInfo::SharedPtr message) {
        if (message->k[0] <= 0.0 || message->k[4] <= 0.0) {
          RCLCPP_WARN_THROTTLE(
            get_logger(), *get_clock(), 2000,
            "Ignoring CameraInfo with invalid focal lengths fx=%.3f fy=%.3f.",
            message->k[0], message->k[4]);
          return;
        }
        camera_fx_ = message->k[0];
        camera_fy_ = message->k[4];
        camera_cx_ = message->k[2];
        camera_cy_ = message->k[5];
        camera_info_ready_ = true;
      });

    synchronizer_ = std::make_shared<Synchronizer>(
      SyncPolicy(static_cast<std::uint32_t>(sync_queue_size_)),
      rgb_subscription_, depth_subscription_);
    synchronizer_->setAgePenalty(sync_age_penalty_);
    synchronizer_->registerCallback(
      std::bind(
        &CupDetectorNode::on_images, this,
        std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(
      get_logger(),
      "Reusable RGB-D %s detector: rgb=%s depth=%s camera_info=%s reliability=%s",
      target_label_.c_str(), rgb_topic_.c_str(), depth_topic_.c_str(),
      camera_info_topic_.c_str(), input_reliability_.c_str());
  }

private:
  void clamp_parameters()
  {
    hue_low_1_ = std::clamp(hue_low_1_, 0, 179);
    hue_high_1_ = std::clamp(hue_high_1_, hue_low_1_, 179);
    hue_low_2_ = std::clamp(hue_low_2_, 0, 179);
    hue_high_2_ = std::clamp(hue_high_2_, hue_low_2_, 179);
    saturation_min_ = std::clamp(saturation_min_, 0, 255);
    value_min_ = std::clamp(value_min_, 0, 255);
    min_area_px_ = std::max(1.0, min_area_px_);
    candidate_min_area_px_ = std::max(1.0, candidate_min_area_px_);
    candidate_max_aspect_ratio_ = std::max(1.0, candidate_max_aspect_ratio_);
    max_area_px_ = std::max(0.0, max_area_px_);
    min_circularity_ = std::clamp(min_circularity_, 0.0, 1.0);
    min_rectangularity_ = std::clamp(min_rectangularity_, 0.0, 1.0);
    min_aspect_ratio_ = std::max(1.0, min_aspect_ratio_);
    max_aspect_ratio_ = std::max(0.0, max_aspect_ratio_);
    if (max_aspect_ratio_ > 0.0 && max_aspect_ratio_ < min_aspect_ratio_) {
      max_aspect_ratio_ = min_aspect_ratio_;
    }
    morphology_kernel_ = std::max(1, morphology_kernel_);
    if (morphology_kernel_ % 2 == 0) {
      ++morphology_kernel_;
    }
    sync_queue_size_ = std::clamp(sync_queue_size_, 2, 100);
    sync_age_penalty_ = std::max(0.0, sync_age_penalty_);
    min_depth_m_ = std::max(0.001, min_depth_m_);
    max_depth_m_ = std::max(min_depth_m_ + 0.001, max_depth_m_);
    min_depth_samples_ = std::max(1, min_depth_samples_);
    depth_erode_px_ = std::max(0, depth_erode_px_);
    max_depth_mad_m_ = std::max(0.0, max_depth_mad_m_);
    max_depth_frame_delta_m_ = std::max(0.0, max_depth_frame_delta_m_);
    required_depth_stable_frames_ = std::max(1, required_depth_stable_frames_);
    min_target_size_m_ = std::max(0.0, min_target_size_m_);
    max_target_size_m_ = std::max(0.0, max_target_size_m_);
    if (max_target_size_m_ > 0.0 && max_target_size_m_ < min_target_size_m_) {
      max_target_size_m_ = min_target_size_m_;
    }
    max_target_size_aspect_ratio_ = std::max(0.0, max_target_size_aspect_ratio_);
    color_image_width_ = std::max(1, color_image_width_);
    color_image_height_ = std::max(1, color_image_height_);
    if (software_registration_enabled_ &&
      (color_fx_ <= 0.0 || color_fy_ <= 0.0 ||
      depth_to_color_rotation_.size() != 9 || depth_to_color_translation_m_.size() != 3))
    {
      RCLCPP_ERROR(
        get_logger(),
        "Invalid software RGB-D registration calibration; target output will remain blocked.");
      software_registration_calibration_valid_ = false;
    }
    if (input_reliability_ != "reliable" && input_reliability_ != "best_effort") {
      RCLCPP_WARN(
        get_logger(), "Unknown input_reliability '%s'; using reliable.",
        input_reliability_.c_str());
      input_reliability_ = "reliable";
    }
  }

  void publish_valid(bool valid)
  {
    std_msgs::msg::Bool message;
    message.data = valid;
    valid_publisher_->publish(message);

    if (!has_previous_validity_ || valid != previous_valid_) {
      RCLCPP_INFO(
        get_logger(), "%s target %s", target_label_.c_str(), valid ? "DETECTED" : "LOST");
      previous_valid_ = valid;
      has_previous_validity_ = true;
    }
  }

  void publish_depth_valid(bool valid) const
  {
    std_msgs::msg::Bool message;
    message.data = valid;
    depth_valid_publisher_->publish(message);
  }

  void publish_depth_diagnostic(const std::string & diagnostic) const
  {
    std_msgs::msg::String message;
    message.data = diagnostic;
    depth_diagnostic_publisher_->publish(message);
  }

  void publish_candidate_valid(bool valid) const
  {
    std_msgs::msg::Bool message;
    message.data = valid;
    candidate_valid_publisher_->publish(message);
  }

  void draw_image_center(cv::Mat & image) const
  {
    const cv::Point center(image.cols / 2, image.rows / 2);
    constexpr int cross_size = 22;
    const cv::Scalar green(0, 255, 0);
    cv::line(
      image, cv::Point(center.x - cross_size, center.y),
      cv::Point(center.x + cross_size, center.y), green, 2);
    cv::line(
      image, cv::Point(center.x, center.y - cross_size),
      cv::Point(center.x, center.y + cross_size), green, 2);
    cv::putText(
      image, "IMAGE CENTER", cv::Point(center.x + 12, center.y - 12),
      cv::FONT_HERSHEY_SIMPLEX, 0.55, green, 2);

  }

  void publish_debug_image(
    const std_msgs::msg::Header & header, const cv::Mat & debug_image) const
  {
    const auto message = cv_bridge::CvImage(
      header, sensor_msgs::image_encodings::BGR8, debug_image).toImageMsg();
    debug_publisher_->publish(*message);
  }

  struct DepthResult
  {
    bool valid{false};
    bool dispersion_valid{false};
    bool frame_delta_valid{false};
    double meters{std::numeric_limits<double>::quiet_NaN()};
    double median_absolute_deviation_m{std::numeric_limits<double>::quiet_NaN()};
    double frame_delta_m{std::numeric_limits<double>::quiet_NaN()};
    std::size_t sample_count{0};
    int stable_frame_count{0};
  };

  DepthResult measure_depth(
    const sensor_msgs::msg::Image::ConstSharedPtr & depth_message,
    const cv::Mat & target_mask,
    const cv::Rect & target_box)
  {
    DepthResult result;
    cv_bridge::CvImageConstPtr depth_image;
    try {
      depth_image = cv_bridge::toCvShare(depth_message);
    } catch (const cv_bridge::Exception & error) {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Depth conversion failed: %s", error.what());
      return result;
    }

    if (depth_image->image.size() != target_mask.size()) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "RGB and depth sizes differ (%dx%d vs %dx%d); use an aligned depth topic.",
        target_mask.cols, target_mask.rows,
        depth_image->image.cols, depth_image->image.rows);
      return result;
    }

    cv::Mat sampling_mask = target_mask.clone();
    if (depth_erode_px_ > 0) {
      const int kernel_size = depth_erode_px_ * 2 + 1;
      const cv::Mat kernel = cv::getStructuringElement(
        cv::MORPH_ELLIPSE, cv::Size(kernel_size, kernel_size));
      cv::erode(sampling_mask, sampling_mask, kernel);
    }

    std::vector<double> valid_depths;
    valid_depths.reserve(static_cast<std::size_t>(target_box.area()));
    const bool is_float_meters =
      depth_message->encoding == sensor_msgs::image_encodings::TYPE_32FC1;
    const bool is_uint16_millimeters =
      depth_message->encoding == sensor_msgs::image_encodings::TYPE_16UC1;

    if (!is_float_meters && !is_uint16_millimeters) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Unsupported depth encoding '%s'; expected 32FC1 or 16UC1.",
        depth_message->encoding.c_str());
      return result;
    }

    for (int row = target_box.y; row < target_box.y + target_box.height; ++row) {
      for (int col = target_box.x; col < target_box.x + target_box.width; ++col) {
        if (sampling_mask.at<std::uint8_t>(row, col) == 0) {
          continue;
        }

        double meters = 0.0;
        if (is_float_meters) {
          meters = static_cast<double>(depth_image->image.at<float>(row, col));
        } else {
          const auto millimeters = depth_image->image.at<std::uint16_t>(row, col);
          if (millimeters == 0) {
            continue;
          }
          meters = static_cast<double>(millimeters) * 0.001;
        }

        if (std::isfinite(meters) && meters >= min_depth_m_ && meters <= max_depth_m_) {
          valid_depths.push_back(meters);
        }
      }
    }

    result.sample_count = valid_depths.size();
    if (valid_depths.size() < static_cast<std::size_t>(min_depth_samples_)) {
      return result;
    }

    const auto middle = valid_depths.begin() +
      static_cast<std::ptrdiff_t>(valid_depths.size() / 2);
    std::nth_element(valid_depths.begin(), middle, valid_depths.end());
    result.meters = *middle;
    result.valid = true;
    std::vector<double> absolute_deviations;
    absolute_deviations.reserve(valid_depths.size());
    for (const double meters : valid_depths) {
      absolute_deviations.push_back(std::abs(meters - result.meters));
    }
    const auto deviation_middle = absolute_deviations.begin() +
      static_cast<std::ptrdiff_t>(absolute_deviations.size() / 2);
    std::nth_element(
      absolute_deviations.begin(), deviation_middle, absolute_deviations.end());
    result.median_absolute_deviation_m = *deviation_middle;
    result.dispersion_valid = result.median_absolute_deviation_m <= max_depth_mad_m_;
    return result;
  }

  void update_depth_temporal_quality(DepthResult & depth)
  {
    if (!depth.valid) {
      previous_depth_valid_ = false;
      depth_stable_frame_count_ = 0;
      return;
    }

    depth.frame_delta_m = previous_depth_valid_ ?
      std::abs(depth.meters - previous_depth_m_) : 0.0;
    depth.frame_delta_valid = !previous_depth_valid_ ||
      depth.frame_delta_m <= max_depth_frame_delta_m_;
    previous_depth_m_ = depth.meters;
    previous_depth_valid_ = true;
    if (depth.dispersion_valid && depth.frame_delta_valid) {
      ++depth_stable_frame_count_;
    } else {
      depth_stable_frame_count_ = 0;
    }
    depth.stable_frame_count = depth_stable_frame_count_;
  }

  void reset_depth_temporal_quality()
  {
    previous_depth_valid_ = false;
    depth_stable_frame_count_ = 0;
  }

  std::string depth_quality_reason(
    const DepthResult & depth, bool clipped, bool camera_info_ready) const
  {
    if (!depth.valid) {
      return "DEPTH_REJECTED_INSUFFICIENT_SAMPLES";
    }
    if (!depth.dispersion_valid) {
      return "DEPTH_REJECTED_HIGH_MEDIAN_ABSOLUTE_DEVIATION";
    }
    if (!depth.frame_delta_valid) {
      return "DEPTH_REJECTED_FRAME_TO_FRAME_JUMP";
    }
    if (depth.stable_frame_count < required_depth_stable_frames_) {
      return "DEPTH_REJECTED_WAITING_FOR_STABLE_FRAMES";
    }
    if (clipped) {
      return "DEPTH_REJECTED_TARGET_CLIPPED";
    }
    if (!camera_info_ready) {
      return "DEPTH_REJECTED_CAMERA_INFO_UNAVAILABLE";
    }
    return "DEPTH_GRASP_ALLOWED";
  }

  bool software_register_color_to_depth(
    const sensor_msgs::msg::Image::ConstSharedPtr & depth_message,
    const cv::Mat & source_image, cv::Mat & registered_image)
  {
    if (!software_registration_calibration_valid_ || !camera_info_ready_) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Software RGB-D registration is waiting for valid calibration and depth CameraInfo.");
      return false;
    }

    cv_bridge::CvImageConstPtr depth_image;
    try {
      depth_image = cv_bridge::toCvShare(depth_message);
    } catch (const cv_bridge::Exception & error) {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Depth conversion for software registration failed: %s", error.what());
      return false;
    }
    const bool depth_is_float =
      depth_message->encoding == sensor_msgs::image_encodings::TYPE_32FC1;
    const bool depth_is_uint16 =
      depth_message->encoding == sensor_msgs::image_encodings::TYPE_16UC1;
    if (!depth_is_float && !depth_is_uint16) {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Unsupported depth encoding '%s' for software registration.",
        depth_message->encoding.c_str());
      return false;
    }

    registered_image = cv::Mat::zeros(
      static_cast<int>(depth_message->height), static_cast<int>(depth_message->width), CV_8UC3);
    std::size_t mapped_pixels = 0;
    for (int row = 0; row < registered_image.rows; ++row) {
      for (int col = 0; col < registered_image.cols; ++col) {
        double depth_m = 0.0;
        if (depth_is_float) {
          depth_m = static_cast<double>(depth_image->image.at<float>(row, col));
        } else {
          const auto depth_mm = depth_image->image.at<std::uint16_t>(row, col);
          depth_m = static_cast<double>(depth_mm) * 0.001;
        }
        if (!std::isfinite(depth_m) || depth_m < min_depth_m_ || depth_m > max_depth_m_) {
          continue;
        }

        const double depth_x =
          (static_cast<double>(col) - camera_cx_) * depth_m / camera_fx_;
        const double depth_y =
          (static_cast<double>(row) - camera_cy_) * depth_m / camera_fy_;
        const auto & r = depth_to_color_rotation_;
        const auto & t = depth_to_color_translation_m_;
        const double color_x =
          r[0] * depth_x + r[1] * depth_y + r[2] * depth_m + t[0];
        const double color_y =
          r[3] * depth_x + r[4] * depth_y + r[5] * depth_m + t[1];
        const double color_z =
          r[6] * depth_x + r[7] * depth_y + r[8] * depth_m + t[2];
        if (!std::isfinite(color_z) || color_z <= 0.001) {
          continue;
        }
        double full_color_x = color_fx_ * color_x / color_z + color_cx_;
        const double full_color_y = color_fy_ * color_y / color_z + color_cy_;
        if (color_mirror_horizontal_) {
          full_color_x = static_cast<double>(color_image_width_ - 1) - full_color_x;
        }
        const int source_x = static_cast<int>(std::lround(
          full_color_x * static_cast<double>(source_image.cols - 1) /
          static_cast<double>(std::max(1, color_image_width_ - 1))));
        const int source_y = static_cast<int>(std::lround(
          full_color_y * static_cast<double>(source_image.rows - 1) /
          static_cast<double>(std::max(1, color_image_height_ - 1))));
        if (source_x < 0 || source_x >= source_image.cols ||
          source_y < 0 || source_y >= source_image.rows)
        {
          continue;
        }
        registered_image.at<cv::Vec3b>(row, col) =
          source_image.at<cv::Vec3b>(source_y, source_x);
        ++mapped_pixels;
      }
    }

    if (!rgb_alignment_reported_) {
      RCLCPP_INFO(
        get_logger(),
        "RGB_DEPTH_SOFTWARE_ALIGNED source=%dx%d depth=%dx%d mapped=%zu mirror_x=%s",
        source_image.cols, source_image.rows, registered_image.cols, registered_image.rows,
        mapped_pixels, color_mirror_horizontal_ ? "true" : "false");
      rgb_alignment_reported_ = true;
    }
    return mapped_pixels > 0;
  }

  void on_images(
    const sensor_msgs::msg::Image::ConstSharedPtr & rgb_message,
    const sensor_msgs::msg::Image::ConstSharedPtr & depth_message)
  {
    cv_bridge::CvImagePtr bridge_image;
    try {
      bridge_image = cv_bridge::toCvCopy(
        rgb_message, sensor_msgs::image_encodings::BGR8);
    } catch (const cv_bridge::Exception & error) {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000, "Image conversion failed: %s", error.what());
      publish_valid(false);
      publish_depth_valid(false);
      return;
    }

    // Observe original RGB BEFORE depth registration. Missing depth pixels must
    // not turn visible colour into a black occlusion or hide a cropped candidate.
    PublishRawColorObservation(bridge_image->image, rgb_message->header);
    cv::Mat processing_image;
    if (software_registration_enabled_) {
      if (!software_register_color_to_depth(
          depth_message, bridge_image->image, processing_image))
      {
        publish_valid(false);
        publish_depth_valid(false);
        publish_depth_diagnostic("DEPTH_REJECTED_SOFTWARE_REGISTRATION_UNAVAILABLE");
        return;
      }
    } else {
      processing_image = bridge_image->image;
    }
    const cv::Size depth_size(
      static_cast<int>(depth_message->width), static_cast<int>(depth_message->height));
    if (depth_size.width <= 0 || depth_size.height <= 0) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000, "Depth image reports an invalid size.");
      publish_valid(false);
      publish_depth_valid(false);
      return;
    }
    if (!software_registration_enabled_ && processing_image.size() != depth_size) {
      // The DaBai DC1 can stream its UVC interface together with OpenNI depth
      // only at the lower-bandwidth 320x240 mode in this VM. This resize is a
      // temporary image-grid normalization; calibrated colour-to-depth mapping
      // below is responsible for metric depth association. The aspect crop is
      // retained as a defensive fallback for negotiated resolutions.
      const double target_aspect =
        static_cast<double>(depth_size.width) / static_cast<double>(depth_size.height);
      const double source_aspect =
        static_cast<double>(processing_image.cols) /
        static_cast<double>(processing_image.rows);
      cv::Rect crop(0, 0, processing_image.cols, processing_image.rows);
      if (source_aspect < target_aspect) {
        crop.height = std::max(
          1, static_cast<int>(std::lround(processing_image.cols / target_aspect)));
        crop.y = (processing_image.rows - crop.height) / 2;
      } else if (source_aspect > target_aspect) {
        crop.width = std::max(
          1, static_cast<int>(std::lround(processing_image.rows * target_aspect)));
        crop.x = (processing_image.cols - crop.width) / 2;
      }
      cv::Mat aligned_image;
      cv::resize(processing_image(crop), aligned_image, depth_size, 0.0, 0.0, cv::INTER_LINEAR);
      processing_image = aligned_image;
      if (!rgb_alignment_reported_) {
        RCLCPP_INFO(
          get_logger(),
          "RGB_DEPTH_GRID_ALIGNED source=%dx%d crop=(%d,%d %dx%d) output=%dx%d",
          bridge_image->image.cols, bridge_image->image.rows,
          crop.x, crop.y, crop.width, crop.height, depth_size.width, depth_size.height);
        rgb_alignment_reported_ = true;
      }
    }

    cv::Mat debug_image = processing_image.clone();
    draw_image_center(debug_image);

    cv::Mat hsv_image;
    cv::cvtColor(processing_image, hsv_image, cv::COLOR_BGR2HSV);

    cv::Mat low_hue_mask;
    cv::Mat high_hue_mask;
    cv::inRange(
      hsv_image,
      cv::Scalar(hue_low_1_, saturation_min_, value_min_),
      cv::Scalar(hue_high_1_, 255, 255), low_hue_mask);
    if (hue_high_2_ > hue_low_2_) {
      cv::inRange(
        hsv_image,
        cv::Scalar(hue_low_2_, saturation_min_, value_min_),
        cv::Scalar(hue_high_2_, 255, 255), high_hue_mask);
    } else {
      high_hue_mask = cv::Mat::zeros(hsv_image.size(), CV_8UC1);
    }

    cv::Mat target_mask = low_hue_mask | high_hue_mask;
    const cv::Mat kernel = cv::getStructuringElement(
      cv::MORPH_ELLIPSE, cv::Size(morphology_kernel_, morphology_kernel_));
    cv::morphologyEx(target_mask, target_mask, cv::MORPH_OPEN, kernel);
    cv::morphologyEx(target_mask, target_mask, cv::MORPH_CLOSE, kernel);

    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(target_mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    // Keep a color-only candidate stream for fast reacquisition. It is never
    // used as the confirmed grasp target; shape checks below control target_valid
    // and the independent depth quality gate controls grasp authorization.
    double candidate_area = 0.0;
    std::vector<cv::Point> candidate_contour;
    for (const auto & contour : contours) {
      const double area = cv::contourArea(contour);
      const cv::Rect box = cv::boundingRect(contour);
      const double aspect_ratio = static_cast<double>(std::max(box.width, box.height)) /
        static_cast<double>(std::max(1, std::min(box.width, box.height)));
      if (area >= candidate_min_area_px_ &&
        aspect_ratio <= candidate_max_aspect_ratio_ && area > candidate_area)
      {
        candidate_area = area;
        candidate_contour = contour;
      }
    }
    if (!candidate_contour.empty()) {
      const cv::Moments candidate_moments = cv::moments(candidate_contour);
      if (std::abs(candidate_moments.m00) > 1e-6) {
        const int candidate_x = static_cast<int>(std::lround(
          candidate_moments.m10 / candidate_moments.m00));
        const int candidate_y = static_cast<int>(std::lround(
          candidate_moments.m01 / candidate_moments.m00));
        const cv::Point image_center(debug_image.cols / 2, debug_image.rows / 2);
        geometry_msgs::msg::Vector3Stamped candidate_message;
        candidate_message.header = rgb_message->header;
        candidate_message.vector.x = candidate_x - image_center.x;
        candidate_message.vector.y = candidate_y - image_center.y;
        candidate_message.vector.z = std::max(
          std::abs(candidate_message.vector.x) / static_cast<double>(debug_image.cols),
          std::abs(candidate_message.vector.y) / static_cast<double>(debug_image.rows));
        candidate_error_publisher_->publish(candidate_message);
        publish_candidate_valid(true);
      } else {
        publish_candidate_valid(false);
      }
    } else {
      publish_candidate_valid(false);
    }

    double largest_area = 0.0;
    double selected_rectangularity = 0.0;
    double selected_aspect_ratio = 0.0;
    std::vector<cv::Point> largest_contour;
    for (const auto & contour : contours) {
      const double area = cv::contourArea(contour);
      const double perimeter = cv::arcLength(contour, true);
      const double circularity = perimeter > 1e-6 ?
        4.0 * CV_PI * area / (perimeter * perimeter) : 0.0;
      const cv::Rect box = cv::boundingRect(contour);
      // A tilted square occupies only about half its axis-aligned box.
      // Measure shape in its own orientation; retain the pixel box for depth ROI.
      const cv::Size2f shape_size = shape_use_rotated_rectangle_ ?
        cv::minAreaRect(contour).size : cv::Size2f(box.width, box.height);
      const double box_area = static_cast<double>(shape_size.width) * shape_size.height;
      const double rectangularity = box_area > 0.0 ? area / box_area : 0.0;
      const double aspect_ratio = static_cast<double>(std::max(shape_size.width, shape_size.height)) /
        std::max(1.0, static_cast<double>(std::min(shape_size.width, shape_size.height)));
      if (area >= min_area_px_ &&
        (max_area_px_ <= 0.0 || area <= max_area_px_) &&
        circularity >= min_circularity_ && rectangularity >= min_rectangularity_ &&
        aspect_ratio >= min_aspect_ratio_ &&
        (max_aspect_ratio_ <= 0.0 || aspect_ratio <= max_aspect_ratio_) &&
        area > largest_area)
      {
        largest_area = area;
        selected_rectangularity = rectangularity;
        selected_aspect_ratio = aspect_ratio;
        largest_contour = contour;
      }
    }

    if (largest_contour.empty()) {
      publish_valid(false);
      publish_depth_valid(false);
      reset_depth_temporal_quality();
      publish_depth_diagnostic("DEPTH_REJECTED_TARGET_LOST");
      cv::putText(
        debug_image, "TARGET LOST", cv::Point(20, 35),
        cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 0, 255), 2);
      publish_debug_image(rgb_message->header, debug_image);
      return;
    }

    const cv::Moments moments = cv::moments(largest_contour);
    if (std::abs(moments.m00) < 1e-6) {
      publish_valid(false);
      publish_depth_valid(false);
      reset_depth_temporal_quality();
      publish_depth_diagnostic("DEPTH_REJECTED_INVALID_TARGET_MOMENT");
      publish_debug_image(rgb_message->header, debug_image);
      return;
    }

    const cv::Point target_center(
      static_cast<int>(std::lround(moments.m10 / moments.m00)),
      static_cast<int>(std::lround(moments.m01 / moments.m00)));
    const cv::Rect target_box = cv::boundingRect(largest_contour);
    const cv::Point image_center(debug_image.cols / 2, debug_image.rows / 2);
    const int dx = target_center.x - image_center.x;
    const int dy = target_center.y - image_center.y;
    const double normalized_error = std::max(
      std::abs(static_cast<double>(dx)) / static_cast<double>(debug_image.cols),
      std::abs(static_cast<double>(dy)) / static_cast<double>(debug_image.rows));
    const bool clipped = target_box.x <= 1 || target_box.y <= 1 ||
      target_box.x + target_box.width >= debug_image.cols - 1 ||
      target_box.y + target_box.height >= debug_image.rows - 1;

    cv::Mat selected_mask = cv::Mat::zeros(target_mask.size(), CV_8UC1);
    std::vector<std::vector<cv::Point>> selected_contours{largest_contour};
    cv::drawContours(selected_mask, selected_contours, 0, cv::Scalar(255), cv::FILLED);
    DepthResult depth = measure_depth(depth_message, selected_mask, target_box);
    update_depth_temporal_quality(depth);
    const bool depth_grasp_allowed = depth.valid && depth.dispersion_valid &&
      depth.frame_delta_valid && depth.stable_frame_count >= required_depth_stable_frames_ &&
      !clipped && camera_info_ready_;
    const std::string depth_reason = depth_quality_reason(depth, clipped, camera_info_ready_);
    double target_width_m = 0.0;
    double target_height_m = 0.0;
    bool target_size_valid = false;
    if (depth.valid && camera_info_ready_) {
      target_width_m = static_cast<double>(target_box.width) * depth.meters / camera_fx_;
      target_height_m = static_cast<double>(target_box.height) * depth.meters / camera_fy_;
      const double largest_size_m = std::max(target_width_m, target_height_m);
      const double smallest_size_m = std::max(1e-6, std::min(target_width_m, target_height_m));
      const double size_aspect_ratio = largest_size_m / smallest_size_m;
      target_size_valid = largest_size_m >= min_target_size_m_ &&
        (max_target_size_m_ <= 0.0 || largest_size_m <= max_target_size_m_) &&
        (max_target_size_aspect_ratio_ <= 0.0 ||
        size_aspect_ratio <= max_target_size_aspect_ratio_);
    }
    const bool target_confirmed = !require_depth_for_target_valid_ ||
      (depth_grasp_allowed && target_size_valid);

    geometry_msgs::msg::PointStamped target_message;
    target_message.header = rgb_message->header;
    target_message.point.x = static_cast<double>(target_center.x);
    target_message.point.y = static_cast<double>(target_center.y);
    target_message.point.z = depth.meters;
    target_publisher_->publish(target_message);

    if (depth.valid && camera_info_ready_) {
      geometry_msgs::msg::PointStamped target_point_camera;
      target_point_camera.header = rgb_message->header;
      target_point_camera.header.frame_id = camera_optical_frame_;
      target_point_camera.point.x =
        (static_cast<double>(target_center.x) - camera_cx_) * depth.meters / camera_fx_;
      target_point_camera.point.y =
        (static_cast<double>(target_center.y) - camera_cy_) * depth.meters / camera_fy_;
      target_point_camera.point.z = depth.meters;
      target_point_camera_publisher_->publish(target_point_camera);

      if (software_registration_enabled_ && software_registration_calibration_valid_) {
        const auto & r = depth_to_color_rotation_;
        const auto & t = depth_to_color_translation_m_;
        const auto & p = target_point_camera.point;
        const double x = r[0] * p.x + r[1] * p.y + r[2] * p.z + t[0];
        const double y = r[3] * p.x + r[4] * p.y + r[5] * p.z + t[1];
        const double z = r[6] * p.x + r[7] * p.y + r[8] * p.z + t[2];
        if (std::isfinite(z) && z > .001) {
          geometry_msgs::msg::PointStamped projection;
          projection.header = rgb_message->header;
          double u = color_fx_ * x / z + color_cx_;
          if (color_mirror_horizontal_) {u = static_cast<double>(color_image_width_ - 1) - u;}
          projection.point.x = u * static_cast<double>(bridge_image->image.cols - 1) /
            static_cast<double>(std::max(1, color_image_width_ - 1)) / bridge_image->image.cols;
          projection.point.y = (color_fy_ * y / z + color_cy_) *
            static_cast<double>(bridge_image->image.rows - 1) /
            static_cast<double>(std::max(1, color_image_height_ - 1)) / bridge_image->image.rows;
          projection.point.z = z;
          // Observation only: ties the chosen RGB-D point to original RGB pixels.
          raw_target_projection_publisher_->publish(projection);
        }
      }

      geometry_msgs::msg::Vector3Stamped target_size;
      target_size.header = target_point_camera.header;
      target_size.vector.x = static_cast<double>(target_box.width) * depth.meters / camera_fx_;
      target_size.vector.y = static_cast<double>(target_box.height) * depth.meters / camera_fy_;
      target_size.vector.z = depth.meters;
      target_size_publisher_->publish(target_size);
    } else if (depth.valid) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Target depth is valid but CameraInfo has not arrived; point grasp remains blocked.");
    }

    geometry_msgs::msg::Vector3Stamped error_message;
    error_message.header = rgb_message->header;
    error_message.vector.x = static_cast<double>(dx);
    error_message.vector.y = static_cast<double>(dy);
    // z carries the resolution-independent largest image-axis error ratio.
    error_message.vector.z = normalized_error;
    error_publisher_->publish(error_message);
    publish_valid(target_confirmed);
    // The physical profile requires depth-stable, size-consistent geometry before
    // target_valid may command ALIGN. Colour-only candidates stay on their separate
    // reacquisition topic and cannot move the real arm.
    publish_depth_valid(depth_grasp_allowed);
    publish_depth_diagnostic(depth_reason);

    const cv::Scalar yellow(0, 255, 255);
    const cv::Scalar cyan(255, 255, 0);
    cv::rectangle(debug_image, target_box, yellow, 3);
    cv::drawMarker(
      debug_image, target_center, cyan, cv::MARKER_CROSS, 24, 3);
    cv::line(debug_image, image_center, target_center, cyan, 2);

    const std::string pixel_status =
      target_label_ + " dx=" + std::to_string(dx) + " dy=" + std::to_string(dy) +
      (clipped ? " CLIPPED" : "");
    cv::putText(
      debug_image, pixel_status, cv::Point(20, 35),
      cv::FONT_HERSHEY_SIMPLEX, 0.7, clipped ? cv::Scalar(0, 165, 255) : yellow, 2);
    std::ostringstream shape_status;
    shape_status << std::fixed << std::setprecision(2)
                 << "RECT=" << selected_rectangularity
                 << " AR=" << selected_aspect_ratio;
    cv::putText(
      debug_image, shape_status.str(), cv::Point(20, 90),
      cv::FONT_HERSHEY_SIMPLEX, 0.55, yellow, 2);

    std::ostringstream depth_status;
    if (depth.valid) {
      depth_status << std::fixed << std::setprecision(3)
                   << "DEPTH=" << depth.meters << " m"
                   << " samples=" << depth.sample_count
                   << " MAD=" << depth.median_absolute_deviation_m
                   << " dZ=" << depth.frame_delta_m
                   << " stable=" << depth.stable_frame_count << "/"
                   << required_depth_stable_frames_;
    } else {
      depth_status << "DEPTH INVALID samples=" << depth.sample_count;
    }
    cv::putText(
      debug_image, depth_status.str(), cv::Point(20, 65),
      cv::FONT_HERSHEY_SIMPLEX, 0.65,
      depth_grasp_allowed ? cv::Scalar(0, 255, 0) : cv::Scalar(0, 165, 255), 2);
    if (!depth_grasp_allowed) {
      cv::putText(
        debug_image, depth_reason, cv::Point(20, 140),
        cv::FONT_HERSHEY_SIMPLEX, 0.45, cv::Scalar(0, 0, 255), 1);
    }
    if (depth.valid && camera_info_ready_) {
      std::ostringstream size_status;
      size_status << std::fixed << std::setprecision(3)
                  << "SIZE=" << (static_cast<double>(target_box.width) * depth.meters / camera_fx_)
                  << "x" << (static_cast<double>(target_box.height) * depth.meters / camera_fy_)
                  << " m";
      cv::putText(
        debug_image, size_status.str(), cv::Point(20, 115),
        cv::FONT_HERSHEY_SIMPLEX, 0.55, cv::Scalar(0, 255, 0), 2);
    }
    publish_debug_image(rgb_message->header, debug_image);
  }

  void PublishRawColorObservation(const cv::Mat & image, const std_msgs::msg::Header & header)
  {
    cv::Mat hsv, mask, second;
    cv::cvtColor(image, hsv, cv::COLOR_BGR2HSV);
    cv::inRange(hsv, cv::Scalar(hue_low_1_, saturation_min_, value_min_),
      cv::Scalar(hue_high_1_, 255, 255), mask);
    if (hue_high_2_ > hue_low_2_) {
      cv::inRange(hsv, cv::Scalar(hue_low_2_, saturation_min_, value_min_),
        cv::Scalar(hue_high_2_, 255, 255), second);
      mask |= second;
    }
    cv::morphologyEx(mask, mask, cv::MORPH_OPEN,
      cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(3, 3)));
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
    cv::Rect selected;
    double best = 0;
    for (const auto & contour : contours) {
      const auto box = cv::boundingRect(contour);
      const double area = cv::contourArea(contour);
      if (area >= 10 && area > best) {best = area; selected = box;}
    }
    geometry_msgs::msg::PolygonStamped observation;
    observation.header = header;
    cv::Mat debug = image.clone();
    if (best > 0) {
      const float l = float(selected.x) / image.cols;
      const float t = float(selected.y) / image.rows;
      const float r = float(selected.x + selected.width) / image.cols;
      const float b = float(selected.y + selected.height) / image.rows;
      for (const auto & xy : {std::pair<float, float>{l, t}, {r, t}, {r, b}, {l, b}}) {
        geometry_msgs::msg::Point32 p;
        p.x = xy.first; p.y = xy.second;
        observation.polygon.points.push_back(p);
      }
      cv::rectangle(debug, selected, cv::Scalar(0, 255, 255), 1);
    }
    cv::putText(debug, "RAW COLOUR ONLY - NOT GRASP VALIDATION", cv::Point(4, 14),
      cv::FONT_HERSHEY_SIMPLEX, .3, cv::Scalar(0, 255, 255), 1);
    raw_bbox_publisher_->publish(observation);  // Empty polygon explicitly invalidates old colour.
    raw_debug_publisher_->publish(*cv_bridge::CvImage(header, "bgr8", debug).toImageMsg());
  }

  rclcpp::Publisher<geometry_msgs::msg::PolygonStamped>::SharedPtr raw_bbox_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::PointStamped>::SharedPtr raw_target_projection_publisher_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr raw_debug_publisher_;
  std::string rgb_topic_;
  std::string depth_topic_;
  std::string camera_info_topic_;
  std::string camera_optical_frame_;
  std::string debug_topic_;
  std::string target_topic_;
  std::string target_point_camera_topic_;
  std::string target_size_topic_;
  std::string error_topic_;
  std::string valid_topic_;
  std::string candidate_error_topic_;
  std::string candidate_valid_topic_;
  std::string depth_valid_topic_;
  std::string depth_diagnostic_topic_;
  std::string input_reliability_;
  bool software_registration_enabled_;
  bool software_registration_calibration_valid_{true};
  int color_image_width_;
  int color_image_height_;
  double color_fx_;
  double color_fy_;
  double color_cx_;
  double color_cy_;
  bool color_mirror_horizontal_;
  std::vector<double> depth_to_color_rotation_;
  std::vector<double> depth_to_color_translation_m_;

  int hue_low_1_;
  int hue_high_1_;
  int hue_low_2_;
  int hue_high_2_;
  int saturation_min_;
  int value_min_;
  int morphology_kernel_;
  double min_area_px_;
  double candidate_min_area_px_;
  double candidate_max_aspect_ratio_;
  double max_area_px_;
  double min_circularity_;
  double min_rectangularity_;
  bool shape_use_rotated_rectangle_;
  double min_aspect_ratio_;
  double max_aspect_ratio_;
  std::string target_label_;
  int sync_queue_size_;
  double sync_age_penalty_;
  double min_depth_m_;
  double max_depth_m_;
  int min_depth_samples_;
  int depth_erode_px_;
  double max_depth_mad_m_;
  double max_depth_frame_delta_m_;
  int required_depth_stable_frames_;
  bool require_depth_for_target_valid_;
  double min_target_size_m_;
  double max_target_size_m_;
  double max_target_size_aspect_ratio_;
  double camera_fx_{0.0};
  double camera_fy_{0.0};
  double camera_cx_{0.0};
  double camera_cy_{0.0};
  bool camera_info_ready_{false};
  bool rgb_alignment_reported_{false};
  double previous_depth_m_{0.0};
  bool previous_depth_valid_{false};
  int depth_stable_frame_count_{0};

  bool has_previous_validity_{false};
  bool previous_valid_{false};

  using SyncPolicy = message_filters::sync_policies::ApproximateTime<
    sensor_msgs::msg::Image, sensor_msgs::msg::Image>;
  using Synchronizer = message_filters::Synchronizer<SyncPolicy>;

  message_filters::Subscriber<sensor_msgs::msg::Image> rgb_subscription_;
  message_filters::Subscriber<sensor_msgs::msg::Image> depth_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr camera_info_subscription_;
  std::shared_ptr<Synchronizer> synchronizer_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr debug_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::PointStamped>::SharedPtr target_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::PointStamped>::SharedPtr target_point_camera_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::Vector3Stamped>::SharedPtr target_size_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::Vector3Stamped>::SharedPtr error_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr valid_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::Vector3Stamped>::SharedPtr candidate_error_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr candidate_valid_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr depth_valid_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr depth_diagnostic_publisher_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CupDetectorNode>());
  rclcpp::shutdown();
  return 0;
}
