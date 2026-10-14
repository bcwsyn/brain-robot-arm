#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>

#include <moveit_msgs/msg/planning_scene.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>
#include <std_msgs/msg/string.hpp>
#include <tf2/exceptions.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Transform.h>
#include <tf2/time.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

namespace brain_robot_pick_place
{
struct VoxelKey
{
  int x;
  int y;
  int z;
  bool operator==(const VoxelKey & other) const {return x == other.x && y == other.y && z == other.z;}
};
struct VoxelKeyHash
{
  std::size_t operator()(const VoxelKey & key) const
  {
    return (static_cast<std::size_t>(static_cast<std::uint32_t>(key.x)) * 73856093U) ^
      (static_cast<std::size_t>(static_cast<std::uint32_t>(key.y)) * 19349663U) ^
      (static_cast<std::size_t>(static_cast<std::uint32_t>(key.z)) * 83492791U);
  }
};
struct VoxelEvidence
{
  std::uint16_t free_observations{0};
  std::uint16_t occupied_observations{0};
  std::chrono::steady_clock::time_point last_seen{};
};

class ActiveScanSupervisor : public rclcpp::Node
{
public:
  explicit ActiveScanSupervisor(const rclcpp::NodeOptions & options)
  : Node("active_scan_supervisor", options), tf_buffer_(get_clock()), tf_listener_(tf_buffer_)
  {
    point_cloud_topic_ = declare_parameter<std::string>("point_cloud_topic", "/camera/depth/points");
    evidence_point_cloud_topic_ = declare_parameter<std::string>(
      "evidence_point_cloud_topic", "/brain_robot_vision/filtered_points");
    joint_state_topic_ = declare_parameter<std::string>("joint_state_topic", "/piper_moveit_joint_states");
    planning_scene_topic_ = declare_parameter<std::string>("planning_scene_topic", "/monitored_planning_scene");
    reference_frame_ = declare_parameter<std::string>("reference_frame", "base_link");
    camera_optical_frame_ = declare_parameter<std::string>("camera_optical_frame", "camera_color_optical_frame");
    map_timeout_s_ = declare_parameter<double>("map_timeout_s", 1.0);
    joint_state_timeout_s_ = declare_parameter<double>("joint_state_timeout_s", 0.3);
    initial_observe_stable_frames_ = declare_parameter<int>("initial_observe_stable_frames", 3);
    voxel_size_m_ = declare_parameter<double>("voxel_size_m", 0.03);
    evidence_window_s_ = declare_parameter<double>("evidence_window_s", 10.0);
    max_evidence_points_per_frame_ = declare_parameter<int>("max_evidence_points_per_frame", 3000);
    if (map_timeout_s_ <= 0.0 || joint_state_timeout_s_ <= 0.0 || initial_observe_stable_frames_ <= 0 ||
      voxel_size_m_ <= 0.0 || evidence_window_s_ <= 0.0 || max_evidence_points_per_frame_ <= 0) {
      throw std::runtime_error("Active scan parameters must be positive.");
    }

    const auto sensor_qos = rclcpp::SensorDataQoS();
    point_cloud_subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      point_cloud_topic_, sensor_qos, [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr message) {
        last_point_cloud_time_ = std::chrono::steady_clock::now();
        ++stable_point_cloud_frames_;
        latest_point_count_ = static_cast<std::size_t>(message->width) * message->height;
      });
    evidence_point_cloud_subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      evidence_point_cloud_topic_, sensor_qos, [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr message) {
        UpdateVoxelEvidence(*message);
      });
    joint_state_subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      joint_state_topic_, sensor_qos, [this](sensor_msgs::msg::JointState::ConstSharedPtr) {
        last_joint_state_time_ = std::chrono::steady_clock::now();
      });
    planning_scene_subscription_ = create_subscription<moveit_msgs::msg::PlanningScene>(
      planning_scene_topic_, rclcpp::QoS(1).reliable(),
      [this](moveit_msgs::msg::PlanningScene::ConstSharedPtr message) {
        last_planning_scene_time_ = std::chrono::steady_clock::now();
        planning_scene_seen_ = true;
        planning_scene_has_octomap_ = !message->world.octomap.octomap.id.empty();
      });
    const auto diagnostic_qos = rclcpp::QoS(1).reliable().transient_local();
    state_publisher_ = create_publisher<std_msgs::msg::String>("/brain_robot_active_scan/state", diagnostic_qos);
    diagnostic_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_active_scan/diagnostic", diagnostic_qos);
    status_timer_ = create_wall_timer(std::chrono::milliseconds(200), [this]() {PublishStatus();});
  }

private:
  static double AgeSeconds(const std::chrono::steady_clock::time_point & time)
  {
    return time == std::chrono::steady_clock::time_point{} ? -1.0 :
      std::chrono::duration<double>(std::chrono::steady_clock::now() - time).count();
  }
  VoxelKey ToVoxel(const tf2::Vector3 & point) const
  {
    return {static_cast<int>(std::floor(point.x() / voxel_size_m_)),
      static_cast<int>(std::floor(point.y() / voxel_size_m_)),
      static_cast<int>(std::floor(point.z() / voxel_size_m_))};
  }
  static bool HasXyzFields(const sensor_msgs::msg::PointCloud2 & cloud)
  {
    bool x = false, y = false, z = false;
    for (const auto & field : cloud.fields) {
      x = x || field.name == "x"; y = y || field.name == "y"; z = z || field.name == "z";
    }
    return x && y && z;
  }
  void MarkFreeRay(const tf2::Vector3 & origin, const tf2::Vector3 & endpoint,
    const std::chrono::steady_clock::time_point & now)
  {
    const tf2::Vector3 delta = endpoint - origin;
    const int steps = static_cast<int>(std::floor(delta.length() / voxel_size_m_));
    for (int i = 0; i < steps; ++i) {
      auto & evidence = voxel_evidence_[ToVoxel(origin + delta * (static_cast<double>(i) / steps))];
      if (evidence.free_observations < UINT16_MAX) {
        ++evidence.free_observations;
      }
      evidence.last_seen = now;
    }
  }
  void UpdateVoxelEvidence(const sensor_msgs::msg::PointCloud2 & cloud)
  {
    if (cloud.header.frame_id.empty() || !HasXyzFields(cloud)) return;
    geometry_msgs::msg::TransformStamped transform;
    try {
      transform = tf_buffer_.lookupTransform(
        reference_frame_, cloud.header.frame_id, rclcpp::Time(cloud.header.stamp),
        tf2::durationFromSec(0.05));
    }
    catch (const tf2::TransformException &) {return;}
    tf2::Transform base_from_cloud;
    base_from_cloud.setOrigin(tf2::Vector3(
        transform.transform.translation.x,
        transform.transform.translation.y,
        transform.transform.translation.z));
    base_from_cloud.setRotation(tf2::Quaternion(
        transform.transform.rotation.x,
        transform.transform.rotation.y,
        transform.transform.rotation.z,
        transform.transform.rotation.w));
    const auto now = std::chrono::steady_clock::now();
    const auto origin = base_from_cloud.getOrigin();
    const std::size_t points = static_cast<std::size_t>(cloud.width) * cloud.height;
    const std::size_t stride = std::max<std::size_t>(1, points / max_evidence_points_per_frame_);
    std::size_t accepted = 0;
    try {
      sensor_msgs::PointCloud2ConstIterator<float> x(cloud, "x"), y(cloud, "y"), z(cloud, "z");
      for (std::size_t i = 0; x != x.end(); ++x, ++y, ++z, ++i) {
        if (i % stride || !std::isfinite(*x) || !std::isfinite(*y) || !std::isfinite(*z)) continue;
        const auto endpoint = base_from_cloud * tf2::Vector3(*x, *y, *z);
        if ((endpoint - origin).length() < voxel_size_m_) continue;
        MarkFreeRay(origin, endpoint, now);
        auto & evidence = voxel_evidence_[ToVoxel(endpoint)];
        if (evidence.occupied_observations < UINT16_MAX) {
          ++evidence.occupied_observations;
        }
        evidence.last_seen = now;
        ++accepted;
      }
    } catch (const std::runtime_error &) {return;}
    latest_evidence_point_count_ = accepted;
    last_evidence_time_ = now;
    PruneEvidence(now);
  }
  void PruneEvidence(const std::chrono::steady_clock::time_point & now)
  {
    const auto window = std::chrono::duration<double>(evidence_window_s_);
    for (auto it = voxel_evidence_.begin(); it != voxel_evidence_.end();) {
      it = now - it->second.last_seen > window ? voxel_evidence_.erase(it) : std::next(it);
    }
  }
  bool CameraTransformAvailable(std::string & detail)
  {
    try {
      const auto transform = tf_buffer_.lookupTransform(reference_frame_, camera_optical_frame_, tf2::TimePointZero);
      std::ostringstream out; out.setf(std::ios::fixed); out.precision(3);
      out << "base<-camera=(" << transform.transform.translation.x << ',' << transform.transform.translation.y << ',' << transform.transform.translation.z << ')';
      detail = out.str(); return true;
    } catch (const tf2::TransformException & error) {detail = error.what(); return false;}
  }
  void PublishStatus()
  {
    const double cloud_age = AgeSeconds(last_point_cloud_time_);
    const double joint_age = AgeSeconds(last_joint_state_time_);
    const double scene_age = AgeSeconds(last_planning_scene_time_);
    const double evidence_age = AgeSeconds(last_evidence_time_);
    std::string tf_detail, state;
    if (cloud_age < 0.0 || cloud_age > map_timeout_s_) {stable_point_cloud_frames_ = 0; state = "WAITING_FOR_POINTCLOUD";}
    else if (joint_age < 0.0 || joint_age > joint_state_timeout_s_) state = "WAITING_FOR_JOINT_FEEDBACK";
    else if (!CameraTransformAvailable(tf_detail)) state = "WAITING_FOR_CAMERA_TF";
    else if (!planning_scene_seen_) state = "WAITING_FOR_PLANNING_SCENE";
    else if (stable_point_cloud_frames_ < initial_observe_stable_frames_) state = "INITIAL_STILL_OBSERVE";
    else if (evidence_age < 0.0 || evidence_age > map_timeout_s_) state = "WAITING_FOR_SELF_FILTERED_POINTCLOUD";
    else state = "MAP_INPUT_READY";
    std::size_t free = 0, occupied = 0;
    for (const auto & entry : voxel_evidence_) entry.second.occupied_observations ? ++occupied : ++free;
    std_msgs::msg::String message; message.data = state; state_publisher_->publish(message);
    std::ostringstream out; out.setf(std::ios::fixed); out.precision(3);
    out << "state=" << state << " point_cloud_age_s=" << cloud_age << " point_count=" << latest_point_count_
      << " stable_frames=" << stable_point_cloud_frames_ << " evidence_age_s=" << evidence_age
      << " evidence_points=" << latest_evidence_point_count_ << " free_voxels=" << free << " occupied_voxels=" << occupied
      << " joint_state_age_s=" << joint_age << " planning_scene_age_s=" << scene_age
      << " planning_scene_octomap_payload=" << (planning_scene_has_octomap_ ? "true" : "false") << " tf=" << tf_detail;
    message.data = out.str(); diagnostic_publisher_->publish(message);
  }
  std::string point_cloud_topic_, evidence_point_cloud_topic_, joint_state_topic_, planning_scene_topic_, reference_frame_, camera_optical_frame_;
  double map_timeout_s_{1.0}, joint_state_timeout_s_{0.3}, voxel_size_m_{0.03}, evidence_window_s_{10.0};
  int max_evidence_points_per_frame_{3000}, initial_observe_stable_frames_{3};
  std::size_t latest_point_count_{0}, latest_evidence_point_count_{0};
  int stable_point_cloud_frames_{0};
  bool planning_scene_seen_{false}, planning_scene_has_octomap_{false};
  std::chrono::steady_clock::time_point last_point_cloud_time_{}, last_joint_state_time_{}, last_evidence_time_{}, last_planning_scene_time_{};
  tf2_ros::Buffer tf_buffer_; tf2_ros::TransformListener tf_listener_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr point_cloud_subscription_, evidence_point_cloud_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_subscription_;
  rclcpp::Subscription<moveit_msgs::msg::PlanningScene>::SharedPtr planning_scene_subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_, diagnostic_publisher_;
  rclcpp::TimerBase::SharedPtr status_timer_;
  std::unordered_map<VoxelKey, VoxelEvidence, VoxelKeyHash> voxel_evidence_;
};
}  // namespace brain_robot_pick_place
int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<brain_robot_pick_place::ActiveScanSupervisor>(rclcpp::NodeOptions()));
  rclcpp::shutdown();
  return 0;
}
