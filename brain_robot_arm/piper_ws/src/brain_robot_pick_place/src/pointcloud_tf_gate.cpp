#include <chrono>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <std_msgs/msg/string.hpp>
#include <tf2/exceptions.h>
#include <tf2/time.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

namespace brain_robot_pick_place
{
class PointCloudTfGate : public rclcpp::Node
{
public:
  explicit PointCloudTfGate(const rclcpp::NodeOptions & options)
  : Node("pointcloud_tf_gate", options), tf_buffer_(get_clock()), tf_listener_(tf_buffer_)
  {
    input_topic_ = declare_parameter<std::string>("input_topic", "/camera/depth/points");
    output_topic_ = declare_parameter<std::string>(
      "output_topic", "/brain_robot_vision/tf_validated_points");
    reference_frame_ = declare_parameter<std::string>("reference_frame", "base_link");
    required_frames_ = declare_parameter<std::vector<std::string>>(
      "required_frames", {"base_link", "link1", "link2", "link3", "link4", "link5", "link6",
        "gripper_base", "link7", "link8"});
    transform_timeout_s_ = declare_parameter<double>("transform_timeout_s", 0.05);
    if (input_topic_.empty() || output_topic_.empty() || reference_frame_.empty() ||
      required_frames_.empty() || transform_timeout_s_ <= 0.0)
    {
      throw std::runtime_error("Point-cloud TF gate parameters are invalid.");
    }

    const auto sensor_qos = rclcpp::SensorDataQoS();
    output_publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_topic_, sensor_qos);
    diagnostic_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_vision/tf_gate_diagnostic", rclcpp::QoS(1).reliable().transient_local());
    input_subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      input_topic_, sensor_qos,
      [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr cloud) {HandleCloud(*cloud);});
  }

private:
  void PublishDiagnostic(const std::string & state, const std::string & detail)
  {
    std_msgs::msg::String message;
    std::ostringstream out;
    out << "state=" << state << " accepted_frames=" << accepted_frames_
        << " rejected_frames=" << rejected_frames_ << " detail=" << detail;
    message.data = out.str();
    diagnostic_publisher_->publish(message);
  }

  bool HasTransformsForCloud(
    const sensor_msgs::msg::PointCloud2 & cloud, std::string & detail, bool & used_latest)
  {
    used_latest = false;
    if (cloud.header.frame_id.empty()) {
      detail = "POINTCLOUD_FRAME_EMPTY";
      return false;
    }
    const rclcpp::Time stamp(cloud.header.stamp);
    std::unordered_set<std::string> frames;
    frames.insert(cloud.header.frame_id);
    for (const auto & frame : required_frames_) {
      if (!frame.empty() && frame != reference_frame_) {
        frames.insert(frame);
      }
    }
    for (const auto & frame : frames) {
      try {
        tf_buffer_.lookupTransform(
          reference_frame_, frame, stamp, tf2::durationFromSec(transform_timeout_s_));
      } catch (const tf2::TransformException & error) {
        // Astra depth frames can arrive several seconds behind the ROS clock
        // after a VM/USB scheduling pause.  The real-arm launch does not feed
        // this cloud into an Octomap; for the freshness heartbeat, use the
        // latest available robot transform and stamp the forwarded sample now.
        try {
          tf_buffer_.lookupTransform(reference_frame_, frame, tf2::TimePointZero);
          used_latest = true;
        } catch (const tf2::TransformException & latest_error) {
          detail = "MISSING_TF " + reference_frame_ + "<-" + frame +
            " at_cloud_stamp: " + error.what() + "; latest: " + latest_error.what();
          return false;
        }
      }
    }
    detail = used_latest ? "TF_LATEST frame=" + cloud.header.frame_id :
      "TF_COMPLETE frame=" + cloud.header.frame_id;
    return true;
  }

  void HandleCloud(const sensor_msgs::msg::PointCloud2 & cloud)
  {
    std::string detail;
    bool used_latest = false;
    if (!HasTransformsForCloud(cloud, detail, used_latest)) {
      ++rejected_frames_;
      PublishDiagnostic("REJECTED", detail);
      return;
    }
    ++accepted_frames_;
    if (used_latest) {
      auto forwarded = cloud;
      forwarded.header.stamp = now();
      output_publisher_->publish(forwarded);
    } else {
      output_publisher_->publish(cloud);
    }
    PublishDiagnostic("FORWARDED", detail);
  }

  std::string input_topic_;
  std::string output_topic_;
  std::string reference_frame_;
  std::vector<std::string> required_frames_;
  double transform_timeout_s_{0.05};
  std::size_t accepted_frames_{0};
  std::size_t rejected_frames_{0};
  tf2_ros::Buffer tf_buffer_;
  tf2_ros::TransformListener tf_listener_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr input_subscription_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr output_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr diagnostic_publisher_;
};
}  // namespace brain_robot_pick_place

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<brain_robot_pick_place::PointCloudTfGate>(rclcpp::NodeOptions()));
  rclcpp::shutdown();
  return 0;
}
