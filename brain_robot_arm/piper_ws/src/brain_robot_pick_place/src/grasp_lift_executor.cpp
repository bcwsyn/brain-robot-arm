#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <future>
#include <limits>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/polygon_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/robot_state/conversions.h>
#include <moveit/robot_model/revolute_joint_model.h>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <moveit_msgs/srv/get_position_ik.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/parameter_client.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2/LinearMath/Transform.h>
#include <tf2/LinearMath/Vector3.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include "brain_robot_pick_place/target_directed_grasp.hpp"

#include "brain_robot_pick_place/grasp_geometry.hpp"
#include "brain_robot_pick_place/target_model_wait.hpp"
#include "brain_robot_pick_place/visual_grasp_feedback.hpp"
#include "brain_robot_pick_place/near_depth_tracking.hpp"

namespace brain_robot_pick_place
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
using PlanningSceneInterface = moveit::planning_interface::PlanningSceneInterface;

class GraspLiftExecutor : public rclcpp::Node
{
  friend struct NearDepthReplayAccess;  // Isolated tests exercise the actual observation methods.
public:
  explicit GraspLiftExecutor(const rclcpp::NodeOptions & options)
  : Node("grasp_lift_executor", options)
  {
    LoadParameters();
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

    scene_ready_publisher_ = create_publisher<std_msgs::msg::Bool>(
      scene_ready_topic_, rclcpp::QoS(1).transient_local());
    state_publisher_ = create_publisher<std_msgs::msg::String>(
      state_topic_, rclcpp::QoS(1).transient_local());
    target_pose_publisher_ = create_publisher<geometry_msgs::msg::PoseStamped>(
      "/brain_robot_grasp/target_pose", rclcpp::QoS(1).transient_local());
    current_pose_publisher_ = create_publisher<geometry_msgs::msg::PoseStamped>(
      "/brain_robot_grasp/current_pose", rclcpp::QoS(1).transient_local());
    diagnostic_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_grasp/diagnostic", rclcpp::QoS(1).transient_local());
    arm_trajectory_publisher_ = create_publisher<trajectory_msgs::msg::JointTrajectory>(
      "/brain_robot_grasp/arm_trajectory", rclcpp::QoS(1));
    gripper_command_publisher_ = create_publisher<sensor_msgs::msg::JointState>(
      "/brain_robot_grasp/gripper_command", rclcpp::QoS(1));
    software_stop_publisher_ = create_publisher<std_msgs::msg::Bool>(
      emergency_stop_topic_, rclcpp::QoS(10));
    reacquire_publisher_ = create_publisher<std_msgs::msg::Bool>(
      grasp_reacquire_topic_, rclcpp::QoS(10));
    visual_state_subscription_ = create_subscription<std_msgs::msg::String>(
      visual_state_topic_, rclcpp::QoS(1).transient_local(),
      [this](const std_msgs::msg::String::SharedPtr message) {
        {
          std::lock_guard<std::mutex> lock(state_mutex_);
          last_visual_state_ = message->data;
        }
        HandleVisualState(message->data);
      });
    raw_bbox_subscription_ = create_subscription<geometry_msgs::msg::PolygonStamped>(
      "/brain_robot_vision/raw_color_bbox", rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PolygonStamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        const auto & points = message->polygon.points;
        const auto stamp = rclcpp::Time(message->header.stamp);
        if (points.size() != 4 || stamp.nanoseconds() <= 0) {
          raw_box_valid_ = false;
          raw_full_frames_ = 0;
          return;
        }
        const visual_grasp::Box box{points[0].x, points[0].y, points[2].x, points[2].y};
        if (!visual_grasp::Valid(box) || stamp.nanoseconds() <= raw_box_stamp_ns_) {
          raw_full_frames_ = 0;
          return;
        }
        const bool continuous = raw_box_valid_ && visual_grasp::Associated(raw_box_, box);
        raw_full_frames_ = visual_grasp::FullView(box) ? (continuous ? raw_full_frames_ + 1 : 1) : 0;
        raw_box_ = box;
        raw_box_valid_ = true;
        raw_box_stamp_ns_ = stamp.nanoseconds();
        raw_box_received_ = std::chrono::steady_clock::now();
      });
    raw_projection_subscription_ = create_subscription<geometry_msgs::msg::PointStamped>(
      "/brain_robot_vision/raw_target_projection", rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PointStamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        raw_target_projection_ = *message;
      });
    qualified_bbox_subscription_ = create_subscription<geometry_msgs::msg::PolygonStamped>(
      "/brain_robot_vision/qualified_color_bbox", rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PolygonStamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        qualified_box_message_ = *message;  // Empty explicitly invalidates the last shape.
        qualified_box_received_ = std::chrono::steady_clock::now();
      });
    raw_info_subscription_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      "/brain_robot_vision/raw_color_info", rclcpp::QoS(1).reliable(),
      [this](const sensor_msgs::msg::CameraInfo::SharedPtr message) {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        raw_image_info_ = *message;
      });
    if (near_depth_rgb_tracking_enabled_ && !simulation_only_) {
      detector_parameters_ = std::make_shared<rclcpp::AsyncParametersClient>(this, "/cube_detector");
      calibration_timer_ = create_wall_timer(std::chrono::milliseconds(500), [this]() {
          if (calibration_request_pending_ || !detector_parameters_->service_is_ready()) {return;}
          calibration_request_pending_ = true;
          detector_parameters_->get_parameters({"software_registration_enabled",
            "color_calibration_width", "color_calibration_height", "color_fx", "color_fy",
            "color_cx", "color_cy", "color_mirror_horizontal", "depth_to_color_rotation",
            "depth_to_color_translation_m"},
            [this](std::shared_future<std::vector<rclcpp::Parameter>> future) {
              calibration_request_pending_ = false;
              try {
                const auto p = future.get();
                if (p.size() != 10 || !p[0].as_bool()) {return;}
                const auto r = p[8].as_double_array(), t = p[9].as_double_array();
                if (r.size() != 9 || t.size() != 3) {return;}
                near_depth::Calibration c;
                c.width = p[1].as_int(); c.height = p[2].as_int();
                c.fx = p[3].as_double(); c.fy = p[4].as_double();
                c.cx = p[5].as_double(); c.cy = p[6].as_double(); c.mirror = p[7].as_bool();
                std::copy(r.begin(), r.end(), c.rotation.begin());
                std::copy(t.begin(), t.end(), c.translation.begin());
                if (!near_depth::Valid(c)) {return;}
                {
                  std::lock_guard<std::mutex> lock(visual_mutex_);
                  near_calibration_ = c;
                  near_calibration_ready_ = true;
                }
                calibration_timer_->cancel();
                PublishDiagnostic("NEAR_RGB_FACTORY_CALIBRATION_FROM_RUNNING_DETECTOR");
              } catch (const std::exception & error) {
                RCLCPP_WARN(get_logger(), "Cannot read detector calibration: %s", error.what());
              }
            });
        });
    }
    target_point_subscription_ = create_subscription<geometry_msgs::msg::PointStamped>(
      target_point_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PointStamped::SharedPtr message) {
        if (depth_only_target_enabled_) {
          return;
        }
        geometry_msgs::msg::PointStamped target_reference;
        bool target_reference_valid = false;
        const std::string target_frame = message->header.frame_id.empty() ?
          camera_optical_frame_ : message->header.frame_id;
        const auto & source_stamp_msg = message->header.stamp;
        if (source_stamp_msg.sec == 0 && source_stamp_msg.nanosec == 0) {
          RCLCPP_WARN_THROTTLE(
            get_logger(), *get_clock(), 2000,
            "Cannot save target in %s: source=%s has zero stamp; latest-TF fallback disabled",
            lift_reference_frame_.c_str(), target_frame.c_str());
        } else {
          const rclcpp::Time source_stamp(source_stamp_msg);
          try {
            const auto reference_from_target = tf_buffer_->lookupTransform(
              lift_reference_frame_, target_frame, source_stamp);
            tf2::doTransform(*message, target_reference, reference_from_target);
            target_reference_valid = true;
            RCLCPP_INFO_THROTTLE(
              get_logger(), *get_clock(), 5000,
              "TARGET_TF source=%s image_stamp=%.9f tf_stamp=%.9f "
              "camera_xyz=(%.4f,%.4f,%.4f) reference=%s xyz=(%.4f,%.4f,%.4f)",
              target_frame.c_str(), source_stamp.seconds(),
              rclcpp::Time(reference_from_target.header.stamp).seconds(),
              message->point.x, message->point.y, message->point.z,
              lift_reference_frame_.c_str(), target_reference.point.x,
              target_reference.point.y, target_reference.point.z);
          } catch (const tf2::TransformException & exception) {
            RCLCPP_WARN_THROTTLE(
              get_logger(), *get_clock(), 2000,
              "Cannot save target in %s at image_stamp=%.9f from %s; "
              "latest-TF fallback disabled: %s",
              lift_reference_frame_.c_str(), source_stamp.seconds(),
              target_frame.c_str(), exception.what());
          }
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_point_camera_ = *message;
        target_point_received_time_ = std::chrono::steady_clock::now();
        if (target_reference_valid) {
          if (target_reference_received_time_ != std::chrono::steady_clock::time_point{}) {
            previous_target_point_reference_ = target_point_reference_;
            previous_target_reference_received_time_ = target_reference_received_time_;
          }
          target_point_reference_ = target_reference;
          target_reference_received_time_ = target_point_received_time_;
        }
      });
    target_size_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      target_size_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        if (depth_only_target_enabled_) {
          return;
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_size_ = *message;
        target_size_received_time_ = std::chrono::steady_clock::now();
      });
    target_error_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      "/brain_robot_vision/pixel_error", rclcpp::SensorDataQoS(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        if (depth_only_target_enabled_) {
          return;
        }
        target_error_ratio_ = message->vector.z;
        target_error_received_time_ = std::chrono::steady_clock::now();
      });
    target_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      "/brain_robot_vision/target_valid", rclcpp::SensorDataQoS(),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        if (depth_only_target_enabled_) {
          return;
        }
        target_valid_ = message->data;
        target_valid_received_time_ = std::chrono::steady_clock::now();
      });
    depth_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      depth_valid_topic_, rclcpp::QoS(1).reliable(),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        if (depth_only_target_enabled_) {
          return;
        }
        depth_valid_ = message->data;
        depth_valid_received_time_ = std::chrono::steady_clock::now();
      });
    depth_only_point_subscription_ = create_subscription<geometry_msgs::msg::PointStamped>(
      depth_only_point_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PointStamped::SharedPtr message) {
        if (!depth_only_target_enabled_) {
          return;
        }
        geometry_msgs::msg::PointStamped target_reference;
        bool target_reference_valid = false;
        const std::string target_frame = message->header.frame_id.empty() ?
          camera_optical_frame_ : message->header.frame_id;
        try {
          const auto reference_from_target = tf_buffer_->lookupTransform(
            lift_reference_frame_, target_frame, tf2::TimePointZero);
          tf2::doTransform(*message, target_reference, reference_from_target);
          target_reference_valid = true;
        } catch (const tf2::TransformException & exception) {
          RCLCPP_WARN_THROTTLE(
            get_logger(), *get_clock(), 2000,
            "Cannot save depth-only target in %s: %s",
            lift_reference_frame_.c_str(), exception.what());
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_point_camera_ = *message;
        target_point_received_time_ = std::chrono::steady_clock::now();
        if (target_reference_valid) {
          if (target_reference_received_time_ != std::chrono::steady_clock::time_point{}) {
            previous_target_point_reference_ = target_point_reference_;
            previous_target_reference_received_time_ = target_reference_received_time_;
          }
          target_point_reference_ = target_reference;
          target_reference_received_time_ = target_point_received_time_;
        }
      });
    depth_only_size_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      depth_only_size_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        if (!depth_only_target_enabled_) {
          return;
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_size_ = *message;
        target_size_received_time_ = std::chrono::steady_clock::now();
      });
    depth_only_error_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      depth_only_error_topic_, rclcpp::SensorDataQoS(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        if (!depth_only_target_enabled_) {
          return;
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_error_ratio_ = message->vector.z;
        target_error_received_time_ = std::chrono::steady_clock::now();
      });
    depth_only_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      depth_only_valid_topic_, rclcpp::SensorDataQoS(),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        if (!depth_only_target_enabled_) {
          return;
        }
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_valid_ = message->data;
        depth_valid_ = message->data;
        target_valid_received_time_ = std::chrono::steady_clock::now();
        depth_valid_received_time_ = target_valid_received_time_;
      });
    joint_state_subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      "/joint_states", rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::JointState::SharedPtr message) {
        std::lock_guard<std::mutex> lock(feedback_mutex_);
        latest_joint_state_ = *message;
        joint_state_received_time_ = std::chrono::steady_clock::now();
      });
    gripper_feedback_subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      gripper_feedback_topic_, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::JointState::SharedPtr message) {
        std::lock_guard<std::mutex> lock(feedback_mutex_);
        latest_gripper_feedback_ = *message;
        gripper_feedback_received_time_ = std::chrono::steady_clock::now();
      });
    emergency_stop_subscription_ = create_subscription<std_msgs::msg::Bool>(
      emergency_stop_topic_, rclcpp::QoS(10),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        if (!message->data) {
          return;
        }
        cancel_requested_ = true;
        const auto arm = arm_;
        const auto gripper = gripper_;
        if (arm) {
          arm->stop();
        }
        if (gripper) {
          gripper->stop();
        }
        PublishSceneReady(false);
        RestoreUnattachedCup();
        PublishState("FAULT_ESTOP");
      });
    cup_follow_client_ = create_client<std_srvs::srv::SetBool>(cup_follow_service_);
    servo_stop_client_ = create_client<std_srvs::srv::Trigger>(servo_stop_service_);
    adapter_disarm_client_ = create_client<std_srvs::srv::Trigger>("/piper_jog_adapter/disarm");
    compute_ik_client_ = create_client<moveit_msgs::srv::GetPositionIK>("/compute_ik");
    execute_service_ = create_service<std_srvs::srv::Trigger>(
      "~/execute", [this](
        const std_srvs::srv::Trigger::Request::SharedPtr,
        std_srvs::srv::Trigger::Response::SharedPtr response) {
        std::string visual_state;
        {
          std::lock_guard<std::mutex> lock(state_mutex_);
          visual_state = last_visual_state_;
          if (worker_active_) {
            response->success = false;
            response->message = "A grasp sequence is already running.";
            return;
          }
          if (!real_grasp_enabled_ || visual_state != "GRASP_READY") {
            response->success = false;
            response->message =
              "Real grasp requires real_grasp_enabled=true and current state GRASP_READY.";
            return;
          }
          if (!DepthStillTrusted()) {
            response->success = false;
            response->message =
              "Grasp requires a fresh, stable, unclipped RGB-D target; continue visual tracking.";
            return;
          }
          grasp_requested_ = true;
          cancel_requested_ = false;
          prepared_ = true;
        }
        StartWorker();
        response->success = true;
        response->message = "Real grasp sequence started from the camera target.";
      });

    PublishSceneReady(false);
    PublishState("WAITING_FOR_LEVEL_ALIGN");
  }

  ~GraspLiftExecutor() override
  {
    cancel_requested_ = true;
    if (arm_) {
      arm_->stop();
    }
    if (gripper_) {
      gripper_->stop();
    }
    if (worker_.joinable()) {
      worker_.join();
    }
  }

  void SetMoveItInterfaces(
    std::shared_ptr<MoveGroupInterface> arm,
    std::shared_ptr<MoveGroupInterface> gripper,
    std::shared_ptr<PlanningSceneInterface> planning_scene)
  {
    arm_ = std::move(arm);
    gripper_ = std::move(gripper);
    planning_scene_ = std::move(planning_scene);
    ConfigureMoveGroups();
  }

  const std::string & ArmGroup() const {return arm_group_;}
  const std::string & GripperGroup() const {return gripper_group_;}
  bool SimulationOnly() const {return simulation_only_;}

private:
  template<typename T>
  T ParameterOr(const std::string & name, const T & fallback)
  {
    T value = fallback;
    get_parameter_or(name, value, fallback);
    return value;
  }

  void LoadParameters()
  {
    simulation_only_ = ParameterOr<bool>("simulation_only", true);
    real_grasp_enabled_ = ParameterOr<bool>("real_grasp_enabled", false);
    auto_execute_ = ParameterOr<bool>("auto_execute", true);
    prepare_on_grasp_ready_ = ParameterOr<bool>("prepare_on_grasp_ready", false);
    candidate_grasp_enabled_ = ParameterOr<bool>("candidate_grasp_enabled", false);
    candidate_grasp_order_ = ParameterOr<std::vector<std::string>>(
      "candidate_grasp_order", {"TOP_DOWN", "DIAGONAL_LEFT", "DIAGONAL_RIGHT"});
    top_down_grasp_enabled_ = ParameterOr<bool>("top_down_grasp_enabled", false);
    diagonal_side_grasp_enabled_ = ParameterOr<bool>("diagonal_side_grasp_enabled", false);
    grasp_contact_check_enabled_ = ParameterOr<bool>("grasp_contact_check_enabled", false);
    arm_group_ = ParameterOr<std::string>("arm_group", "arm");
    gripper_group_ = ParameterOr<std::string>("gripper_group", "gripper");
    end_effector_link_ = ParameterOr<std::string>("end_effector_link", "gripper_base");
    gripper_touch_links_ = ParameterOr<std::vector<std::string>>(
      "gripper_touch_links", {"link6", "gripper_base", "link7", "link8"});
    cup_name_ = ParameterOr<std::string>("cup_name", "medicine_cup");
    open_target_ = ParameterOr<std::string>("open_target", "open");
    close_target_ = ParameterOr<std::string>("close_target", "close");
    lift_reference_frame_ = ParameterOr<std::string>("lift_reference_frame", "world");
    camera_optical_frame_ = ParameterOr<std::string>(
      "camera_optical_frame", "wrist_camera_optical_frame");
    target_point_topic_ = ParameterOr<std::string>(
      "target_point_topic", "/brain_robot_vision/target_point_camera");
    target_size_topic_ = ParameterOr<std::string>(
      "target_size_topic", "/brain_robot_vision/target_size");
    depth_only_target_enabled_ = ParameterOr<bool>("depth_only_target_enabled", false);
    depth_only_valid_topic_ = ParameterOr<std::string>(
      "depth_only_valid_topic", "/brain_robot_vision/depth_candidate_valid");
    depth_only_point_topic_ = ParameterOr<std::string>(
      "depth_only_point_topic", "/brain_robot_vision/depth_candidate_point");
    depth_only_size_topic_ = ParameterOr<std::string>(
      "depth_only_size_topic", "/brain_robot_vision/depth_candidate_size");
    depth_only_error_topic_ = ParameterOr<std::string>(
      "depth_only_error_topic", "/brain_robot_vision/depth_candidate_error");
    depth_valid_topic_ = ParameterOr<std::string>(
      "depth_valid_topic", "/brain_robot_vision/depth_valid");
    adaptive_size_enabled_ = ParameterOr<bool>("adaptive_size_enabled", false);
    min_object_size_m_ = ParameterOr<double>("min_object_size_m", 0.01);
    max_object_size_m_ = ParameterOr<double>("max_object_size_m", 0.25);
    target_timeout_s_ = ParameterOr<double>("target_timeout_s", 0.60);
    static_target_lock_ = ParameterOr<bool>("static_target_lock", false);
    preserve_aligned_grasp_orientation_ = ParameterOr<bool>(
      "preserve_aligned_grasp_orientation", false);
    target_directed_grasp_enabled_ = ParameterOr<bool>("target_directed_grasp_enabled", false);
    target_directed_downward_fraction_ = ParameterOr<double>(
      "target_directed_downward_fraction", 0.5);
    aligned_grasp_pitch_down_rad_ = ParameterOr<double>("aligned_grasp_pitch_down_rad", 0.0);
    grasp_height_offset_m_ = ParameterOr<double>("grasp_height_offset_m", 0.0);
    gripper_tip_offset_m_ = ParameterOr<double>("gripper_tip_offset_m", 0.1358);
    grasp_center_offset_m_ = ParameterOr<double>(
      "grasp_center_offset_m", gripper_tip_offset_m_);
    grasp_contact_tolerance_m_ = ParameterOr<double>("grasp_contact_tolerance_m", 0.025);
    gripper_open_value_ = ParameterOr<int>("gripper_open_value", 50000);
    allow_open_feedback_unconfirmed_for_approach_ = ParameterOr<bool>(
      "allow_open_feedback_unconfirmed_for_approach", false);
    gripper_close_value_ = ParameterOr<int>("gripper_close_value", 40000);
    gripper_settle_s_ = ParameterOr<double>("gripper_settle_s", 2.0);
    fresh_jaw_capture_required_ = ParameterOr<bool>("fresh_jaw_capture_required", false);
    near_depth_rgb_tracking_enabled_ = ParameterOr<bool>("near_depth_rgb_tracking_enabled", false);
    automatic_rgb_approach_enabled_ = ParameterOr<bool>("automatic_rgb_approach_enabled", false);
    terminal_depth_stage_enabled_ = ParameterOr<bool>("terminal_depth_stage_enabled", true);
    terminal_depth_lock_range_m_ = ParameterOr<double>("terminal_depth_lock_range_m", .20);
    near_depth_prediction_max_age_s_ = ParameterOr<double>("near_depth_prediction_max_age_s", 30.0);
    near_depth_prediction_max_travel_m_ = ParameterOr<double>(
      "near_depth_prediction_max_travel_m", .030);
    visual_microsteps_enabled_ = ParameterOr<bool>("visual_microsteps_enabled", false);
    visual_microstep_m_ = ParameterOr<double>("visual_microstep_m", .005);
    visual_microstep_angle_rad_ = ParameterOr<double>("visual_microstep_angle_rad", .01745329252);
    visual_view_recovery_angle_rad_ = ParameterOr<double>("visual_view_recovery_angle_rad", .01745329252);
    visual_view_recovery_steps_ = ParameterOr<int>("visual_view_recovery_steps", 3);
    visual_microstep_max_steps_ = ParameterOr<int>("visual_microstep_max_steps", 4);
    visual_target_association_m_ = ParameterOr<double>("visual_target_association_m", .04);
    near_rgb_association_bad_frames_ = ParameterOr<int>(
      "near_rgb_association_bad_frames", 5);
    visual_jaw_image_roi_ = ParameterOr<std::vector<double>>("visual_jaw_image_roi", {});
    visual_jaw_image_roi_confirmed_ = ParameterOr<bool>("visual_jaw_image_roi_confirmed", false);
    gripper_feedback_topic_ = ParameterOr<std::string>(
      "gripper_feedback_topic", "/joint_states_feedback");
    gripper_feedback_timeout_s_ = ParameterOr<double>("gripper_feedback_timeout_s", 3.0);
    min_gripper_feedback_motion_rad_ = ParameterOr<double>(
      "min_gripper_feedback_motion_rad", 0.001);
    gripper_position_tolerance_m_ = ParameterOr<double>(
      "gripper_position_tolerance_m", 0.003);
    auto_release_after_lift_ = ParameterOr<bool>("auto_release_after_lift", false);
    hold_after_lift_s_ = ParameterOr<double>("hold_after_lift_s", 1.0);
    top_down_pregrasp_clearance_m_ = ParameterOr<double>(
      "top_down_pregrasp_clearance_m", 0.12);
    top_down_pregrasp_clearance_candidates_m_ = ParameterOr<std::vector<double>>(
      "top_down_pregrasp_clearance_candidates_m", {top_down_pregrasp_clearance_m_});
    top_down_grasp_clearance_m_ = ParameterOr<double>(
      "top_down_grasp_clearance_m", 0.005);
    top_down_surface_grasp_enabled_ = ParameterOr<bool>("top_down_surface_grasp_enabled", false);
    surface_insertion_fraction_ = ParameterOr<double>("surface_insertion_fraction", 0.4);
    surface_insertion_max_m_ = ParameterOr<double>("surface_insertion_max_m", 0.012);
    grasp_landing_tolerance_m_ = ParameterOr<double>("grasp_landing_tolerance_m", 0.008);
    grasp_landing_orientation_tolerance_rad_ = ParameterOr<double>(
      "grasp_landing_orientation_tolerance_rad", 0.05);
    grasp_landing_max_correction_m_ = ParameterOr<double>("grasp_landing_max_correction_m", 0.020);
    grasp_landing_feedback_tolerance_rad_ = ParameterOr<double>(
      "grasp_landing_feedback_tolerance_rad", 0.010);
    grasp_landing_feedback_timeout_s_ = ParameterOr<double>(
      "grasp_landing_feedback_timeout_s", 8.0);
    top_down_grasp_yaw_ = ParameterOr<double>("top_down_grasp_yaw", 0.0);
    top_down_yaw_candidates_ = ParameterOr<std::vector<double>>(
      "top_down_yaw_candidates", {0.0, 1.57079632679, -1.57079632679, 3.14159265359});
    top_down_tilt_candidates_ = ParameterOr<std::vector<double>>(
      "top_down_tilt_candidates", {0.0, 0.35, 0.70, 1.00});
    real_pose_planning_pipeline_ = ParameterOr<std::string>(
      "real_pose_planning_pipeline", "pilz_industrial_motion_planner");
    real_pose_planner_id_ = ParameterOr<std::string>("real_pose_planner_id", "PTP");
    diagonal_pregrasp_standoff_m_ = ParameterOr<double>(
      "diagonal_pregrasp_standoff_m", 0.17);
    diagonal_grasp_standoff_m_ = ParameterOr<double>(
      "diagonal_grasp_standoff_m", 0.045);
    diagonal_pregrasp_lift_m_ = ParameterOr<double>(
      "diagonal_pregrasp_lift_m", 0.10);
    diagonal_grasp_lift_m_ = ParameterOr<double>(
      "diagonal_grasp_lift_m", 0.04);
    diagonal_lateral_offset_m_ = ParameterOr<double>("diagonal_lateral_offset_m", 0.06);
    pregrasp_standoff_m_ = ParameterOr<double>("pregrasp_standoff_m", 0.16);
    grasp_depth_m_ = ParameterOr<double>("grasp_depth_m", 0.08);
    approach_microstep_m_ = ParameterOr<double>("approach_microstep_m", 0.008);
    approach_max_steps_ = ParameterOr<int>("approach_max_steps", 20);
    approach_prediction_horizon_s_ = ParameterOr<double>(
      "approach_prediction_horizon_s", 0.08);
    approach_max_target_speed_m_s_ = ParameterOr<double>(
      "approach_max_target_speed_m_s", 0.30);
    cartesian_eef_step_m_ = ParameterOr<double>("cartesian_eef_step_m", 0.005);
    cartesian_max_joint_step_rad_ = ParameterOr<double>(
      "cartesian_max_joint_step_rad", 0.35);
    linear_approach_velocity_scaling_ = ParameterOr<double>(
      "linear_approach_velocity_scaling", 0.025);
    lift_distance_m_ = ParameterOr<double>("lift_distance_m", 0.10);
    planning_time_s_ = ParameterOr<double>("grasp_planning_time_s", 8.0);
    planning_attempts_ = ParameterOr<int>("grasp_planning_attempts", 10);
    velocity_scaling_ = ParameterOr<double>("grasp_velocity_scaling", 0.05);
    acceleration_scaling_ = ParameterOr<double>("grasp_acceleration_scaling", 0.05);
    position_tolerance_ = ParameterOr<double>("grasp_position_tolerance", 0.01);
    orientation_tolerance_ = ParameterOr<double>("grasp_orientation_tolerance", 0.05);
    scene_wait_s_ = ParameterOr<double>("grasp_scene_wait_s", 10.0);
    trajectory_feedback_tolerance_rad_ = ParameterOr<double>(
      "trajectory_feedback_tolerance_rad", 0.04);
    trajectory_feedback_timeout_s_ = ParameterOr<double>(
      "trajectory_feedback_timeout_s", 12.0);
    real_trajectory_joint_min_ = ParameterOr<std::vector<double>>(
      "real_trajectory_joint_min", {-1.50, -0.30, -1.40, -0.80, -1.20, -3.14159265359});
    real_trajectory_joint_max_ = ParameterOr<std::vector<double>>(
      "real_trajectory_joint_max", {1.50, 3.14159265359, 0.40, 0.80, 1.20, 3.14159265359});
    real_trajectory_limit_margin_rad_ = ParameterOr<double>(
      "real_trajectory_limit_margin_rad", 0.005);
    joint_state_wait_timeout_s_ = ParameterOr<double>(
      "joint_state_wait_timeout_s", 25.0);
    visual_state_topic_ = ParameterOr<std::string>(
      "visual_state_topic", "/brain_robot_visual_control/state");
    scene_ready_topic_ = ParameterOr<std::string>(
      "grasp_scene_ready_topic", "/brain_robot_grasp/scene_ready");
    state_topic_ = ParameterOr<std::string>("grasp_state_topic", "/brain_robot_grasp/state");
    emergency_stop_topic_ = ParameterOr<std::string>(
      "emergency_stop_topic", "/brain_robot_control/emergency_stop");
    grasp_reacquire_topic_ = ParameterOr<std::string>(
      "grasp_reacquire_topic", "/brain_robot_grasp/reacquire");
    grasp_alignment_error_ratio_ = ParameterOr<double>(
      "grasp_alignment_error_ratio", 0.05);
    cup_follow_service_ = ParameterOr<std::string>(
      "cup_follow_service", "/brain_robot_pick_place/set_cup_follow");
    servo_stop_service_ = ParameterOr<std::string>(
      "servo_stop_service", "/servo_node/stop_servo");

    configuration_ok_ = (simulation_only_ ? auto_execute_ : real_grasp_enabled_) &&
      (!automatic_rgb_approach_enabled_ || (near_depth_rgb_tracking_enabled_ &&
      static_target_lock_ && target_directed_grasp_enabled_ && fresh_jaw_capture_required_ &&
      !visual_microsteps_enabled_ && std::isfinite(approach_microstep_m_) &&
      approach_microstep_m_ > 0 && approach_microstep_m_ <= .010)) &&
      (!near_depth_rgb_tracking_enabled_ ||
      (static_target_lock_ && !depth_only_target_enabled_ &&
      std::isfinite(near_depth_prediction_max_age_s_) && near_depth_prediction_max_age_s_ > 0 &&
      near_depth_prediction_max_age_s_ <= 30 &&
      std::isfinite(near_depth_prediction_max_travel_m_) &&
      near_depth_prediction_max_travel_m_ > 0 && near_depth_prediction_max_travel_m_ <= .030 &&
      near_rgb_association_bad_frames_ > 0 && near_rgb_association_bad_frames_ <= 10)) &&
      (!visual_microsteps_enabled_ ||
      (target_directed_grasp_enabled_ && static_target_lock_ && !depth_only_target_enabled_ &&
      std::isfinite(visual_microstep_m_) && visual_microstep_m_ > 0 && visual_microstep_m_ <= .005 &&
      std::isfinite(visual_microstep_angle_rad_) && visual_microstep_angle_rad_ > 0 &&
      visual_microstep_angle_rad_ <= .017453293 &&
      std::isfinite(visual_view_recovery_angle_rad_) && visual_view_recovery_angle_rad_ > 0 &&
      visual_view_recovery_angle_rad_ <= .017453293 && visual_view_recovery_steps_ >= 0 &&
      visual_view_recovery_steps_ <= 3 && visual_microstep_max_steps_ > 0 &&
      visual_microstep_max_steps_ <= 4 && std::isfinite(visual_target_association_m_) &&
      visual_target_association_m_ > 0 && visual_target_association_m_ <= .04 &&
      (!visual_jaw_image_roi_confirmed_ || (visual_jaw_image_roi_.size() == 4 &&
      visual_grasp::Valid({visual_jaw_image_roi_[0], visual_jaw_image_roi_[1],
        visual_jaw_image_roi_[2], visual_jaw_image_roi_[3]}))))) &&
      lift_distance_m_ > 0.0 &&
      grasp_depth_m_ > 0.0 && pregrasp_standoff_m_ > grasp_depth_m_ &&
      approach_microstep_m_ > 0.0 && approach_max_steps_ > 0 &&
      approach_prediction_horizon_s_ >= 0.0 && approach_max_target_speed_m_s_ > 0.0 &&
      cartesian_eef_step_m_ > 0.0 && cartesian_max_joint_step_rad_ > 0.0 &&
      grasp_height_offset_m_ >= 0.0 &&
      std::isfinite(aligned_grasp_pitch_down_rad_) && aligned_grasp_pitch_down_rad_ >= 0.0 &&
      (!target_directed_grasp_enabled_ ||
      (top_down_surface_grasp_enabled_ && !preserve_aligned_grasp_orientation_ &&
      std::isfinite(target_directed_downward_fraction_) &&
      target_directed_downward_fraction_ > 0.0 && target_directed_downward_fraction_ <= 1.0)) &&
      gripper_tip_offset_m_ > 0.0 && top_down_pregrasp_clearance_m_ > 0.0 &&
      grasp_center_offset_m_ > 0.0 && grasp_contact_tolerance_m_ > 0.0 &&
      top_down_grasp_clearance_m_ >= 0.0 &&
      (!top_down_surface_grasp_enabled_ ||
      (top_down_grasp_enabled_ && !candidate_grasp_enabled_ &&
      static_target_lock_ && adaptive_size_enabled_ &&
      grasp_height_offset_m_ == 0.0 && surface_insertion_fraction_ > 0.0 &&
      surface_insertion_fraction_ < 0.5 && surface_insertion_max_m_ > 0.0 &&
      std::isfinite(surface_insertion_max_m_))) &&
      (simulation_only_ || !top_down_grasp_enabled_ ||
      (grasp_landing_tolerance_m_ > 0.0 &&
      grasp_landing_orientation_tolerance_rad_ > 0.0 &&
      grasp_landing_orientation_tolerance_rad_ <= orientation_tolerance_ &&
      grasp_landing_max_correction_m_ >= grasp_landing_tolerance_m_ &&
      std::isfinite(grasp_landing_max_correction_m_))) &&
      top_down_pregrasp_clearance_m_ > top_down_grasp_clearance_m_ &&
      !top_down_pregrasp_clearance_candidates_m_.empty() &&
      std::all_of(
        top_down_pregrasp_clearance_candidates_m_.begin(),
        top_down_pregrasp_clearance_candidates_m_.end(),
        [this](double clearance) {
          return clearance > top_down_grasp_clearance_m_;
        }) &&
      !top_down_yaw_candidates_.empty() &&
      (simulation_only_ ||
      (!real_pose_planning_pipeline_.empty() && !real_pose_planner_id_.empty())) &&
      (!candidate_grasp_enabled_ || !candidate_grasp_order_.empty()) &&
      diagonal_pregrasp_standoff_m_ > diagonal_grasp_standoff_m_ &&
      diagonal_grasp_standoff_m_ > 0.0 && diagonal_pregrasp_lift_m_ >= 0.0 &&
      diagonal_grasp_lift_m_ >= 0.0 && diagonal_lateral_offset_m_ >= 0.0 &&
      target_timeout_s_ > 0.0 &&
      min_object_size_m_ > 0.0 && max_object_size_m_ >= min_object_size_m_ &&
      planning_time_s_ > 0.0 && planning_attempts_ > 0 && velocity_scaling_ > 0.0 &&
      velocity_scaling_ <= 1.0 && acceleration_scaling_ > 0.0 &&
      acceleration_scaling_ <= 1.0 && linear_approach_velocity_scaling_ > 0.0 &&
      linear_approach_velocity_scaling_ <= velocity_scaling_ && gripper_settle_s_ > 0.0 &&
      hold_after_lift_s_ >= 0.0 &&
      gripper_feedback_timeout_s_ > 0.0 && min_gripper_feedback_motion_rad_ >= 0.0 &&
      gripper_position_tolerance_m_ > 0.0 &&
      trajectory_feedback_tolerance_rad_ > 0.0 && trajectory_feedback_timeout_s_ > 0.0 &&
      real_trajectory_joint_min_.size() == 6U && real_trajectory_joint_max_.size() == 6U &&
      std::equal(
        real_trajectory_joint_min_.begin(), real_trajectory_joint_min_.end(),
        real_trajectory_joint_max_.begin(),
        [this](double lower, double upper) {
          return lower + real_trajectory_limit_margin_rad_ <
                 upper - real_trajectory_limit_margin_rad_;
        }) &&
      real_trajectory_limit_margin_rad_ >= 0.0 &&
      joint_state_wait_timeout_s_ > 0.0;
    if (!configuration_ok_) {
      RCLCPP_ERROR(
        get_logger(),
        "Grasp execution is locked. Enable the selected simulation/real profile and all motion parameters.");
    }
  }

  void ConfigureMoveGroups()
  {
    if (!arm_ || (simulation_only_ && !gripper_)) {
      return;
    }
    arm_->setPlanningTime(planning_time_s_);
    arm_->setNumPlanningAttempts(static_cast<unsigned int>(planning_attempts_));
    arm_->setMaxVelocityScalingFactor(velocity_scaling_);
    arm_->setMaxAccelerationScalingFactor(acceleration_scaling_);
    arm_->setGoalPositionTolerance(position_tolerance_);
    if (!arm_->setEndEffectorLink(end_effector_link_)) {
      configuration_ok_ = false;
      RCLCPP_ERROR(
        get_logger(), "Grasp execution is locked: end-effector link %s is invalid for group %s.",
        end_effector_link_.c_str(), arm_group_.c_str());
      return;
    }
    arm_->setGoalOrientationTolerance(orientation_tolerance_);
    if (gripper_) {
      gripper_->setPlanningTime(planning_time_s_);
      gripper_->setMaxVelocityScalingFactor(velocity_scaling_);
      gripper_->setMaxAccelerationScalingFactor(acceleration_scaling_);
    }
  }

  void HandleVisualState(const std::string & visual_state)
  {
    if (!configuration_ok_ || !arm_ || !planning_scene_ ||
      (simulation_only_ && !gripper_)) {
      return;
    }
    if (visual_state == "LEVEL_ALIGN") {
      bool start_worker = false;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        if (!prepared_ && !worker_active_) {
          grasp_requested_ = false;
          cancel_requested_ = false;
          start_worker = true;
        }
      }
      if (start_worker) {
        StartWorker();
      }
      return;
    }
    if (visual_state == "GRASP_READY") {
      if (!auto_execute_) {
        return;
      }
      bool start_worker = false;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        grasp_requested_ = true;
        cancel_requested_ = false;
        start_worker = !worker_active_ && (prepared_ || prepare_on_grasp_ready_);
      }
      if (start_worker) {
        StartWorker();
      }
      return;
    }
    if (visual_state == "FAULT" || visual_state == "STOPPED") {
      cancel_requested_ = true;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        grasp_requested_ = false;
      }
      PublishSceneReady(false);
      RestoreUnattachedCup();
    }
  }

  void StartWorker()
  {
    if (worker_.joinable()) {
      worker_.join();
    }
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      if (worker_active_) {
        return;
      }
      worker_active_ = true;
    }
    worker_ = std::thread([this]() {
      bool needs_prepare = false;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        needs_prepare = !prepared_;
      }
      if (needs_prepare && simulation_only_) {
        PrepareScene();
      } else if (needs_prepare) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        prepared_ = true;
      }
      bool prepared = false;
      bool grasp_requested = false;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        prepared = prepared_;
        grasp_requested = grasp_requested_;
      }
      if (prepared && grasp_requested && !cancel_requested_) {
        PointGraspAndLift();
      }
      std::lock_guard<std::mutex> lock(state_mutex_);
      worker_active_ = false;
    });
  }

  void PrepareScene()
  {
    PublishSceneReady(false);
    PublishState("OPENING_GRIPPER");
    if (!MoveGripper(open_target_) || cancel_requested_) {
      Fail("OPEN_GRIPPER_FAILED");
      return;
    }
    if (!WaitForCup()) {
      Fail("CUP_SCENE_OBJECT_MISSING");
      return;
    }

    const auto objects = planning_scene_->getObjects({cup_name_});
    const auto found = objects.find(cup_name_);
    if (found == objects.end() || found->second.primitive_poses.empty()) {
      Fail("CUP_GEOMETRY_OR_POSE_MISSING");
      return;
    }
    cached_cup_ = found->second;
    auto remove_cup = cached_cup_;
    remove_cup.operation = moveit_msgs::msg::CollisionObject::REMOVE;
    if (!planning_scene_->applyCollisionObject(remove_cup)) {
      Fail("CUP_COLLISION_REMOVE_FAILED");
      return;
    }

    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      prepared_ = true;
    }
    PublishSceneReady(true);
    PublishState("PREPARED");
    RCLCPP_INFO(
      get_logger(),
      "Gripper is open and the cup collision object is cached for direct point grasp.");
  }

  void PointGraspAndLift()
  {
    approach_locked_ = false;
    target_model_locked_ = false;
    near_seed_ = {};
    near_rgb_association_bad_frames_seen_ = 0;
    near_last_bad_association_stamp_ns_ = 0;
    near_seed_stamp_ns_ = near_last_image_stamp_ns_ = 0;
    near_seed_image_stamp_ns_ = 0;  // Diagnostic provenance only, never an age gate.
    near_last_command_image_stamp_ns_ = 0;
    near_last_full_rgb_view_ = {};
    near_last_visible_rgb_box_ = {};
    near_view_recovery_ = false;
    near_camera_travel_m_ = 0;
    near_path_allowance_ready_ = false;
    near_last_mode_predicted_ = false;
    near_depth_tracking_active_ = false;
    coarse_depth_tracking_ = false;
    coarse_motion_in_progress_ = false;
    terminal_target_frozen_ = false;
    struct TrackingScope
    {
      bool & active;
      ~TrackingScope() {active = false;}
    } tracking_scope{near_depth_tracking_active_};
    if (!StopServo()) {
      Fail("SERVO_STOP_FAILED");
      return;
    }
    // Hold after ALIGN until a fresh observation has its exact sampled TF.
    // Do not turn normal TF publication latency into a terminal fault, or
    // open the gripper before the static base-frame target has been locked.
    if (static_target_lock_ && !WaitForTargetModel()) {
      return;
    }
    if (near_depth_rgb_tracking_enabled_ && !simulation_only_) {
      geometry_msgs::msg::PointStamped observed;
      bool predicted = false;
      rclcpp::Time image_time(0, 0, get_clock()->get_clock_type());
      // Capture the same-image shape/depth seed BEFORE gripper/pregrasp output.
      // Boundedly tolerate normal callback/TF ordering, never substitute latest TF.
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(600);
      while (rclcpp::ok() && !cancel_requested_ && !near_seed_.valid &&
        std::chrono::steady_clock::now() < deadline)
      {
        ObserveLockedTarget(observed, image_time, predicted);
        if (!near_seed_.valid) {std::this_thread::sleep_for(std::chrono::milliseconds(20));}
      }
      if (!near_seed_.valid) {Fail("NEAR_RGB_RELIABLE_SEED_UNAVAILABLE"); return;}
      near_depth_tracking_active_ = true;
    }
    if (!simulation_only_) {
      const double gripper_before_open = LatestGripperPosition();
      if (!CommandRealGripper(true) || cancel_requested_) {
        Fail("OPEN_GRIPPER_FAILED");
        return;
      }
      std::this_thread::sleep_for(std::chrono::duration<double>(gripper_settle_s_));
      if (!WaitForGripperCommand(
          gripper_before_open, gripper_open_value_, false, "GRIPPER_OPEN") &&
        !allow_open_feedback_unconfirmed_for_approach_)
      {
        Fail("OPEN_GRIPPER_FEEDBACK_UNCONFIRMED");
        return;
      }
      if (allow_open_feedback_unconfirmed_for_approach_ &&
        std::abs(LatestGripperPosition() - static_cast<double>(gripper_open_value_) / 1000000.0) >
        gripper_position_tolerance_m_)
      {
        PublishDiagnostic("OPEN_GRIPPER_FEEDBACK_UNCONFIRMED_PROCEED_TO_APPROACH");
      }
    }
    if (!static_target_lock_) {
      if (!TargetStillAligned()) {
        RequestVisualReacquire("GRASP_TARGET_SHIFT_BEFORE_PREGRASP");
        return;
      }
      if (!CaptureTargetModel()) {
        RequestVisualReacquire("GRASP_TARGET_MODEL_UNAVAILABLE");
        return;
      }
    }
    if (candidate_grasp_enabled_) {
      CandidatePointGraspAndLift();
      return;
    }
    if (top_down_grasp_enabled_) {
      TopDownPointGraspAndLift();
      return;
    }
    if (diagonal_side_grasp_enabled_) {
      DiagonalSidePointGraspAndLift();
      return;
    }
    PublishState("ALIGNED_PREGRASP_PLANNING");
    geometry_msgs::msg::PoseStamped pregrasp_target;
    if (!BuildAlignedPointGrasp(pregrasp_standoff_m_, pregrasp_target)) {
      RequestVisualReacquire("ALIGNED_PREGRASP_TARGET_UNAVAILABLE");
      return;
    }
    bool pregrasp_reached = false;
    // Once the base-frame model is locked, a failed execution must not clear
    // that model and re-enter wrist-camera ALIGN: camera parallax can produce
    // a different Z estimate and an IK failure. Retry the same fixed target
    // from the latest measured state once, then fail safely if it still does
    // not converge.
    for (int attempt = 1; attempt <= 2 && !cancel_requested_; ++attempt) {
      if (MoveArmToPose(pregrasp_target, "ALIGNED_PREGRASP")) {
        pregrasp_reached = true;
        break;
      }
      if (attempt < 2) {
        RCLCPP_WARN(
          get_logger(), "ALIGNED_PREGRASP execution did not converge; retrying locked target.");
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
      }
    }
    if (!pregrasp_reached || cancel_requested_) {
      if (!cancel_requested_) {
        Fail("ALIGNED_PREGRASP_EXECUTION_FAILED_LOCKED_TARGET");
      }
      return;
    }
    PublishState("ALIGNED_PREGRASP_REACHED");
    approach_locked_ = true;

    if (!static_target_lock_ && !TargetStillAligned()) {
      RequestVisualReacquire("GRASP_TARGET_SHIFT_AFTER_PREGRASP");
      return;
    }

    if (!ClosedLoopMicroApproach()) {
      return;
    }
    FinishGraspAndLift();
  }

  void CandidatePointGraspAndLift()
  {
    for (const auto & candidate : candidate_grasp_order_) {
      if (!TargetStillAligned()) {
        RequestVisualReacquire("GRASP_TARGET_SHIFT_DURING_CANDIDATE_SELECTION");
        return;
      }

      bool accepted = false;
      if (candidate == "TOP_DOWN") {
        accepted = TryTopDownCandidate();
      } else if (candidate == "DIAGONAL_LEFT") {
        accepted = TryDiagonalCandidate(candidate, diagonal_lateral_offset_m_);
      } else if (candidate == "DIAGONAL_RIGHT") {
        accepted = TryDiagonalCandidate(candidate, -diagonal_lateral_offset_m_);
      } else {
        PublishDiagnostic("CANDIDATE_REJECTED_UNKNOWN_" + candidate);
      }

      if (cancel_requested_) {
        return;
      }
      if (accepted) {
        PublishDiagnostic("CANDIDATE_SELECTED_" + candidate);
        FinishGraspAndLift();
        return;
      }
    }
    PublishState("ALL_GRASP_CANDIDATES_FAILED");
    PublishDiagnostic("ALL_GRASP_CANDIDATES_FAILED");
  }

  bool TryTopDownCandidate()
  {
    const std::string name = "TOP_DOWN";
    for (const double yaw : top_down_yaw_candidates_) {
      selected_top_down_yaw_ = yaw;
      selected_top_down_yaw_valid_ = true;
      PublishDiagnostic("CANDIDATE_TOP_DOWN_YAW_" + std::to_string(yaw));
      PublishState("CANDIDATE_" + name + "_PREGRASP_PLANNING");
      geometry_msgs::msg::PoseStamped pregrasp_target;
      if (!BuildTopDownPointGrasp(top_down_pregrasp_clearance_m_, pregrasp_target)) {
        PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_TARGET_UNAVAILABLE");
        break;
      }
      if (!MoveArmToPose(pregrasp_target, "CANDIDATE_" + name + "_PREGRASP")) {
        PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_PREGRASP_PLAN_FAILED");
        continue;
      }
      PublishState("CANDIDATE_" + name + "_PREGRASP_REACHED");
      if (!TargetStillAligned()) {
        RequestVisualReacquire("GRASP_TARGET_SHIFT_AFTER_" + name + "_PREGRASP");
        return false;
      }
      PublishState("CANDIDATE_" + name + "_APPROACH_PLANNING");
      geometry_msgs::msg::PoseStamped grasp_target;
      if (!BuildTopDownPointGrasp(top_down_grasp_clearance_m_, grasp_target, true)) {
        PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_APPROACH_TARGET_UNAVAILABLE");
        break;
      }
      if (!MoveArmCartesianToPose(grasp_target, "CANDIDATE_" + name + "_APPROACH")) {
        PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_APPROACH_FAILED");
        continue;
      }
      return true;
    }
    selected_top_down_yaw_valid_ = false;
    return false;
  }

  bool TryDiagonalCandidate(const std::string & name, double pregrasp_lateral_offset_m)
  {
    PublishState("CANDIDATE_" + name + "_PREGRASP_PLANNING");
    geometry_msgs::msg::PoseStamped pregrasp_target;
    if (!BuildDiagonalSidePointGrasp(
        diagonal_pregrasp_standoff_m_, diagonal_pregrasp_lift_m_,
        pregrasp_lateral_offset_m, pregrasp_target))
    {
      PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_TARGET_UNAVAILABLE");
      return false;
    }
    if (!MoveArmToPose(pregrasp_target, "CANDIDATE_" + name + "_PREGRASP")) {
      PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_PREGRASP_PLAN_FAILED");
      return false;
    }
    PublishState("CANDIDATE_" + name + "_PREGRASP_REACHED");
    if (!TargetStillAligned()) {
      RequestVisualReacquire("GRASP_TARGET_SHIFT_AFTER_" + name + "_PREGRASP");
      return false;
    }
    PublishState("CANDIDATE_" + name + "_APPROACH_PLANNING");
    geometry_msgs::msg::PoseStamped grasp_target;
    if (!BuildDiagonalSidePointGrasp(
        diagonal_grasp_standoff_m_, diagonal_grasp_lift_m_, 0.0, grasp_target))
    {
      PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_APPROACH_TARGET_UNAVAILABLE");
      return false;
    }
    if (!MoveArmCartesianToPose(grasp_target, "CANDIDATE_" + name + "_APPROACH")) {
      PublishDiagnostic("CANDIDATE_REJECTED_" + name + "_APPROACH_FAILED");
      return false;
    }
    return true;
  }

  bool ClosedLoopMicroApproach()
  {
    double standoff_m = pregrasp_standoff_m_;
    for (int step = 1; step <= approach_max_steps_; ++step) {
      if (!static_target_lock_ && !TargetStillAligned()) {
        RequestVisualReacquire("MICRO_APPROACH_TARGET_SHIFT_BEFORE_STEP");
        return false;
      }
      const double next_standoff_m = std::max(
        grasp_depth_m_, standoff_m - approach_microstep_m_);
      PublishState("MICRO_APPROACH_STEP_" + std::to_string(step));
      geometry_msgs::msg::PoseStamped desired_target;
      if (!BuildAlignedPointGrasp(next_standoff_m, desired_target)) {
        RequestVisualReacquire("MICRO_APPROACH_TARGET_UNAVAILABLE");
        return false;
      }
      geometry_msgs::msg::PoseStamped bounded_target;
      if (!BuildBoundedMicrostep(desired_target, bounded_target)) {
        RequestVisualReacquire("MICRO_APPROACH_STEP_TARGET_UNAVAILABLE");
        return false;
      }
      if (!MoveArmCartesianToPose(
          bounded_target, "MICRO_APPROACH_STEP_" + std::to_string(step)) ||
        cancel_requested_)
      {
        if (!cancel_requested_) {
          RequestVisualReacquire("MICRO_APPROACH_STEP_PLAN_OR_FEEDBACK_FAILED");
        }
        return false;
      }
      if (!static_target_lock_ && !TargetStillAligned()) {
        RequestVisualReacquire("MICRO_APPROACH_TARGET_SHIFT_AFTER_STEP");
        return false;
      }
      if (next_standoff_m <= grasp_depth_m_) {
        PublishState("MICRO_APPROACH_COMPLETE");
        return true;
      }
      standoff_m = next_standoff_m;
    }
    RequestVisualReacquire("MICRO_APPROACH_STEP_LIMIT_REACHED");
    return false;
  }

  bool BuildBoundedMicrostep(
    const geometry_msgs::msg::PoseStamped & desired_target,
    geometry_msgs::msg::PoseStamped & bounded_target)
  {
    const auto current = CurrentPoseInFrame(desired_target.header.frame_id);
    if (current.header.frame_id.empty()) {
      return false;
    }
    const double dx = desired_target.pose.position.x - current.pose.position.x;
    const double dy = desired_target.pose.position.y - current.pose.position.y;
    const double dz = desired_target.pose.position.z - current.pose.position.z;
    const double distance_m = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (!std::isfinite(distance_m)) {
      return false;
    }
    bounded_target = desired_target;
    if (distance_m <= approach_microstep_m_) {
      return true;
    }
    const double scale = approach_microstep_m_ / distance_m;
    bounded_target.pose.position.x = current.pose.position.x + dx * scale;
    bounded_target.pose.position.y = current.pose.position.y + dy * scale;
    bounded_target.pose.position.z = current.pose.position.z + dz * scale;
    bounded_target.pose.orientation = current.pose.orientation;
    target_pose_publisher_->publish(bounded_target);
    PublishDiagnostic("MICRO_APPROACH_STEP_CLAMPED_TO_" +
      std::to_string(approach_microstep_m_) + "M");
    return true;
  }

  void DiagonalSidePointGraspAndLift()
  {
    PublishState("DIAGONAL_SIDE_PREGRASP_PLANNING");
    geometry_msgs::msg::PoseStamped pregrasp_target;
    MoveGroupInterface::Plan pregrasp_plan;
    moveit_msgs::msg::RobotTrajectory approach_plan;
    bool plan_found = false;
    std::vector<double> lateral_offsets{0.0};
    const std::vector<double> side_tilts{0.35, 0.75, 0.95, 1.10};
    const std::vector<double> side_yaws{0.0, 0.78539816339, -0.78539816339, 1.57079632679, -1.57079632679, 3.14159265359};
    if (diagonal_lateral_offset_m_ > 0.0) {
      lateral_offsets.push_back(diagonal_lateral_offset_m_);
      lateral_offsets.push_back(-diagonal_lateral_offset_m_);
    }
    for (const double lateral_offset : lateral_offsets) {
      for (const double side_tilt : side_tilts) {
        for (const double side_yaw : side_yaws) {
      geometry_msgs::msg::PoseStamped candidate_pregrasp;
      const auto candidate_orientation = TopDownOrientation(side_yaw, side_tilt);
      if (!BuildDiagonalSidePointGrasp(
          diagonal_pregrasp_standoff_m_, diagonal_pregrasp_lift_m_,
          lateral_offset, candidate_pregrasp, &candidate_orientation))
      {
        continue;
      }
      MoveGroupInterface::Plan candidate_pregrasp_plan;
      const std::string candidate_stage =
        "DIAGONAL_SIDE_PREGRASP_LATERAL_" + std::to_string(lateral_offset) +
        "_TILT_" + std::to_string(side_tilt) + "_YAW_" + std::to_string(side_yaw);
      if (!PlanArmToPose(candidate_pregrasp, candidate_stage, candidate_pregrasp_plan)) {
        PublishDiagnostic(candidate_stage + ":PREGRASP_PLAN_RETURNED_FALSE");
        continue;
      }
      std::string rejection;
      if (!simulation_only_ && !RealTrajectoryWithinLimits(
          candidate_pregrasp_plan.trajectory_.joint_trajectory, rejection))
      {
        PublishDiagnostic(candidate_stage + ":REAL_LIMIT_REJECTED:" + rejection);
        RCLCPP_WARN(
          get_logger(), "%s rejected before adapter output: %s.",
          candidate_stage.c_str(), rejection.c_str());
        continue;
      }
      geometry_msgs::msg::PoseStamped candidate_grasp;
      if (!BuildDiagonalSidePointGrasp(
          diagonal_grasp_standoff_m_, diagonal_grasp_lift_m_, 0.0, candidate_grasp,
          &candidate_orientation))
      {
        continue;
      }
      auto predicted_pregrasp_state = StateAtTrajectoryEnd(
        candidate_pregrasp_plan.trajectory_.joint_trajectory,
        candidate_stage + "_APPROACH_START");
      if (!predicted_pregrasp_state) {
        continue;
      }
      moveit_msgs::msg::RobotTrajectory candidate_approach_plan;
      const std::string approach_stage = candidate_stage + "_APPROACH";
      if (!PlanArmCartesianFromState(
          candidate_grasp, approach_stage, predicted_pregrasp_state,
          candidate_approach_plan))
      {
        continue;
      }
      if (!simulation_only_ && !RealTrajectoryWithinLimits(
          candidate_approach_plan.joint_trajectory, rejection))
      {
        PublishDiagnostic(approach_stage + ":REAL_LIMIT_REJECTED:" + rejection);
        RCLCPP_WARN(
          get_logger(), "%s rejected before adapter output: %s.",
          approach_stage.c_str(), rejection.c_str());
        continue;
      }
      pregrasp_target = candidate_pregrasp;
      pregrasp_plan = std::move(candidate_pregrasp_plan);
      approach_plan = std::move(candidate_approach_plan);
      plan_found = true;
      break;
        }
      }
    }
    if (!plan_found || cancel_requested_) {
      Fail("DIAGONAL_SIDE_PREGRASP_PLAN_FAILED");
      return;
    }
    const bool pregrasp_executed = simulation_only_ ?
      static_cast<bool>(arm_->execute(pregrasp_plan)) :
      ExecuteArmTrajectory(pregrasp_plan.trajectory_.joint_trajectory);
    if (!pregrasp_executed || cancel_requested_) {
      Fail("DIAGONAL_SIDE_PREGRASP_EXECUTION_FAILED");
      return;
    }
    PublishDiagnostic("DIAGONAL_SIDE_PREGRASP_TRAJECTORY_ACCEPTED");
    PublishState("DIAGONAL_SIDE_PREGRASP_REACHED");

    PublishState("DIAGONAL_SIDE_APPROACH_EXECUTING");
    const bool approach_executed = simulation_only_ ?
      static_cast<bool>(arm_->execute(approach_plan)) :
      ExecuteArmTrajectory(approach_plan.joint_trajectory);
    if (!approach_executed || cancel_requested_) {
      Fail("DIAGONAL_SIDE_APPROACH_FAILED");
      return;
    }
    PublishDiagnostic("DIAGONAL_SIDE_APPROACH_TRAJECTORY_ACCEPTED");
    FinishGraspAndLift(pregrasp_target);
  }

  bool BuildDiagonalSidePointGrasp(
    double camera_standoff_m, double vertical_clearance_m,
    double lateral_offset_m, geometry_msgs::msg::PoseStamped & grasp_target,
    const geometry_msgs::msg::Quaternion * requested_orientation = nullptr)
  {
    geometry_msgs::msg::PointStamped object_world;
    if (!PredictedTargetInReference(object_world)) {
      RCLCPP_ERROR(get_logger(), "Locked base-frame target is unavailable for side grasp.");
      return false;
    }
    double object_size_m = 0.0;
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      if (adaptive_size_enabled_ && target_model_locked_) {
        object_size_m = locked_object_size_m_;
      } else if (adaptive_size_enabled_) {
        const double size_age_s = std::chrono::duration<double>(
          std::chrono::steady_clock::now() - target_size_received_time_).count();
        const double width_m = std::max(target_size_.vector.x, target_size_.vector.y);
        if (target_size_received_time_ == std::chrono::steady_clock::time_point{} ||
          size_age_s > target_timeout_s_ || !std::isfinite(width_m) ||
          width_m < min_object_size_m_ || width_m > max_object_size_m_)
        {
          RCLCPP_ERROR(
            get_logger(),
            "Adaptive cube size is missing, stale, or outside the safe range "
            "[%.3f, %.3f] m.", min_object_size_m_, max_object_size_m_);
          return false;
        }
        object_size_m = width_m;
      }
    }

    const double size_margin = adaptive_size_enabled_ ? object_size_m * 0.5 : 0.0;
    const double effective_standoff = camera_standoff_m + size_margin;
    const double effective_clearance = vertical_clearance_m + size_margin;

    try {
      const auto world_from_camera = tf_buffer_->lookupTransform(
        lift_reference_frame_, camera_optical_frame_, tf2::TimePointZero);
      tf2::Quaternion camera_orientation;
      tf2::fromMsg(world_from_camera.transform.rotation, camera_orientation);
      tf2::Vector3 camera_forward = tf2::quatRotate(
        camera_orientation, tf2::Vector3(0.0, 0.0, 1.0));
      if (camera_forward.length2() < 1e-4) {
        RCLCPP_ERROR(get_logger(), "Camera optical axis is invalid for a diagonal side grasp.");
        return false;
      }
      camera_forward.normalize();
      tf2::Vector3 camera_left = tf2::quatRotate(
        camera_orientation, tf2::Vector3(-1.0, 0.0, 0.0));
      if (camera_left.length2() < 1e-4) {
        RCLCPP_ERROR(get_logger(), "Camera lateral axis is invalid for a diagonal side grasp.");
        return false;
      }
      camera_left.normalize();

      // The wrist camera and jaws share a forward direction.  Retreating along
      // -forward and adding world-Z clearance gives a reachable, slanted approach.
      tf2::Vector3 desired_camera_position(
        object_world.point.x - camera_forward.x() * effective_standoff,
        object_world.point.y - camera_forward.y() * effective_standoff,
        object_world.point.z - camera_forward.z() * effective_standoff +
        grasp_height_offset_m_ + effective_clearance);
      desired_camera_position += camera_left * lateral_offset_m;
      const auto current_gripper = CurrentPoseInFrame(lift_reference_frame_);
      const tf2::Vector3 current_gripper_position(
        current_gripper.pose.position.x, current_gripper.pose.position.y,
        current_gripper.pose.position.z);
      tf2::Quaternion current_gripper_orientation;
      tf2::fromMsg(current_gripper.pose.orientation, current_gripper_orientation);
      const tf2::Vector3 current_camera_position(
        world_from_camera.transform.translation.x,
        world_from_camera.transform.translation.y,
        world_from_camera.transform.translation.z);
      const tf2::Vector3 camera_offset_gripper = tf2::quatRotate(
        current_gripper_orientation.inverse(), current_camera_position - current_gripper_position);
      const auto target_orientation = requested_orientation ?
        *requested_orientation : current_gripper.pose.orientation;
      tf2::Quaternion target_orientation_tf;
      tf2::fromMsg(target_orientation, target_orientation_tf);
      const tf2::Vector3 target_camera_offset_world = tf2::quatRotate(
        target_orientation_tf, camera_offset_gripper);
      const tf2::Vector3 desired_gripper_position =
        desired_camera_position - target_camera_offset_world;

      grasp_target.header.frame_id = lift_reference_frame_;
      grasp_target.header.stamp = now();
      grasp_target.pose.position.x = desired_gripper_position.x();
      grasp_target.pose.position.y = desired_gripper_position.y();
      grasp_target.pose.position.z = desired_gripper_position.z();
      grasp_target.pose.orientation = target_orientation;
      target_pose_publisher_->publish(grasp_target);
      RCLCPP_INFO(
        get_logger(),
        "Diagonal side grasp target: object=(%.3f, %.3f, %.3f), stand-off=%.3f m, "
        "vertical-clearance=%.3f m, lateral-offset=%.3f m; gripper_base=(%.3f, %.3f, %.3f).",
        object_world.point.x, object_world.point.y, object_world.point.z,
        effective_standoff, effective_clearance, lateral_offset_m,
        grasp_target.pose.position.x, grasp_target.pose.position.y, grasp_target.pose.position.z);
      return true;
    } catch (const tf2::TransformException & exception) {
      RCLCPP_ERROR(get_logger(), "Cannot construct diagonal side grasp target: %s", exception.what());
      return false;
    }
  }

  struct LockedRgbView
  {
    bool valid{false}, recovering{false};
    bool measured_rgbd{false};
    double measured_color_range_m{0}, measured_size_m{0}, measured_min_size_m{0};
    visual_grasp::Box box{};
    near_depth::Calibration calibration{};
    int width{}, height{};
    std::int64_t stamp_ns{};
    Eigen::Vector3d target_reference{Eigen::Vector3d::Zero()};
    Eigen::Vector3d correction{Eigen::Vector3d::Zero()};
  };

  bool ObserveLockedTarget(
    geometry_msgs::msg::PointStamped & reference, rclcpp::Time & image_time,
    bool & predicted,
    geometry_msgs::msg::PolygonStamped * observed_box = nullptr,
    sensor_msgs::msg::CameraInfo * observed_info = nullptr,
    near_depth::Calibration * observed_calibration = nullptr,
    LockedRgbView * observed_view = nullptr, bool allow_bounded_compensation = false)
  {
    predicted = false;
    if (!near_depth_rgb_tracking_enabled_ || !static_target_lock_ ||
      !target_model_locked_ || depth_only_target_enabled_) {return false;}
    geometry_msgs::msg::PolygonStamped message;
    sensor_msgs::msg::CameraInfo info;
    near_depth::Calibration calibration;
    bool recovering = false;
    std::chrono::steady_clock::time_point received;
    {
      std::lock_guard<std::mutex> lock(visual_mutex_);
      if (!near_calibration_ready_) {return false;}
      message = qualified_box_message_; info = raw_image_info_;
      received = qualified_box_received_; calibration = near_calibration_;
      // A clipped raw contour may recover an ALREADY qualified identity. Never
      // bootstrap from it, use its truncated centre as depth, or authorize close.
      if (message.polygon.points.empty() && near_seed_.valid &&
        near_last_full_rgb_view_.valid && raw_box_valid_ &&
        near_depth::Cropped(raw_box_, info.width, info.height) &&
        visual_grasp::Associated(near_last_visible_rgb_box_, raw_box_))
      {
        message.header = info.header;
        message.header.stamp = rclcpp::Time(raw_box_stamp_ns_);
        for (const auto & xy : {std::pair<double, double>{raw_box_.left, raw_box_.top},
          {raw_box_.right, raw_box_.top}, {raw_box_.right, raw_box_.bottom},
          {raw_box_.left, raw_box_.bottom}})
        {
          geometry_msgs::msg::Point32 point;
          point.x = xy.first; point.y = xy.second; message.polygon.points.push_back(point);
        }
        received = raw_box_received_; recovering = true;
      }
      if (observed_box) {*observed_box = message;}
      if (observed_info) {*observed_info = info;}
      if (observed_calibration) {*observed_calibration = calibration;}
    }
    const auto steady = std::chrono::steady_clock::now();
    const auto reject = [this](const char * reason) {
        RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000, "NEAR_RGB_REJECTED:%s", reason);
        return false;
      };
    if (message.polygon.points.size() != 4 || received == std::chrono::steady_clock::time_point{} ||
      info.width <= 1 || info.height <= 1 || info.header.frame_id != message.header.frame_id)
    {return reject("COLOR_SHAPE_UNAVAILABLE");}
    image_time = rclcpp::Time(message.header.stamp, get_clock()->get_clock_type());
    const double image_age = (now() - image_time).seconds();
    const double receipt_age = std::chrono::duration<double>(steady - received).count();
    if (image_time.nanoseconds() <= 0 || image_age < 0 || image_age > target_timeout_s_ ||
      receipt_age > target_timeout_s_) {return reject("STALE_RGB");}
    if (image_time.nanoseconds() < near_last_image_stamp_ns_) {
      return reject("OUT_OF_ORDER_RGB");
    }
    const auto & p = message.polygon.points;
    const visual_grasp::Box box{p[0].x, p[0].y, p[2].x, p[2].y};
    if (!visual_grasp::Valid(box)) {return reject("COLOR_SHAPE_UNAVAILABLE");}
    const bool identity_continuous = !near_seed_.valid ||
      visual_grasp::Associated(near_last_visible_rgb_box_, box, .12 + 1e-6);
    if (allow_bounded_compensation && !identity_continuous) {
      return reject("LOCKED_RGB_IDENTITY_JUMP");
    }
    // /joint_states contains physical feedback, not the planned endpoint.
    const auto feedback_fresh = [&]() {
      std::lock_guard<std::mutex> lock(feedback_mutex_);
      const auto & q = latest_joint_state_;
      const auto current = std::chrono::steady_clock::now();
      const double q_age = (now() - rclcpp::Time(q.header.stamp, get_clock()->get_clock_type())).seconds();
      if (joint_state_received_time_ == std::chrono::steady_clock::time_point{} ||
        std::chrono::duration<double>(current - joint_state_received_time_).count() > target_timeout_s_ ||
        q_age < 0 || q_age > target_timeout_s_) {return reject("STALE_ACTUAL_FEEDBACK");}
      for (int axis = 1; axis <= 6; ++axis) {
        if (!std::isfinite(JointPosition(q, "joint" + std::to_string(axis)))) {
          return reject("INCOMPLETE_ACTUAL_FEEDBACK");
        }
      }
      return true;
    };
    if (!feedback_fresh()) {return false;}
    geometry_msgs::msg::PointStamped measured;
    geometry_msgs::msg::Vector3Stamped measured_size;
    bool measured_same_image = false;
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      reference = locked_target_reference_;  // Immutable after the deliberate terminal commit.
      measured = target_point_camera_;
      measured_size = target_size_;
      const auto fresh = [&](const auto & t) {
          return t != std::chrono::steady_clock::time_point{} &&
                 std::chrono::duration<double>(steady - t).count() <= target_timeout_s_;
        };
      measured_same_image = !terminal_target_frozen_ && !recovering && target_valid_ && depth_valid_ && fresh(target_point_received_time_) &&
        fresh(target_valid_received_time_) && fresh(depth_valid_received_time_) &&
        fresh(target_size_received_time_) && measured.header.stamp == message.header.stamp &&
        target_size_.header.stamp == message.header.stamp;
    }
    if (coarse_depth_tracking_ && !coarse_motion_in_progress_ &&
      (!measured_same_image || !identity_continuous)) {
      return reject("COARSE_APPROACH_WAITING_FOR_SAME_IMAGE_DEPTH");
    }
    try {
      // Exact image-time TF comes from actual feedback. Allow normal TF delivery
      // latency; do not use latest or the trajectory's planned terminal joints.
      const auto exact_transform = [&](const std::string & target, const std::string & source) {
          const auto started = std::chrono::steady_clock::now();
          const bool retry_allowed = automatic_rgb_approach_enabled_ && allow_bounded_compensation;
          for (unsigned attempt = 1; ; ++attempt) {
            try {
              auto transform = tf_buffer_->lookupTransform(target, source, image_time,
                rclcpp::Duration::from_seconds(attempt == 1 ? .3 : 0.0));
              if (attempt > 1) {
                RCLCPP_INFO(get_logger(),
                  "NEAR_RGB_EXACT_TF_RECOVERED target=%s source=%s image_stamp=%ld "
                  "attempt=%u elapsed_s=%.6f",
                  target.c_str(), source.c_str(), image_time.nanoseconds(), attempt,
                  std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count());
              }
              return transform;
            } catch (const tf2::TransformException & error) {
              RCLCPP_WARN(get_logger(),
                "NEAR_RGB_EXACT_TF_WAIT target=%s source=%s image_stamp=%ld "
                "attempt=%u image_age_s=%.6f elapsed_s=%.6f error=%s",
                target.c_str(), source.c_str(), image_time.nanoseconds(), attempt,
                (now()-image_time).seconds(),
                std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count(),
                error.what());
              const double age = (now()-image_time).seconds();
              const double received_age = std::chrono::duration<double>(
                std::chrono::steady_clock::now()-received).count();
              if (!retry_allowed || attempt >= 3 || age < 0 || age > target_timeout_s_ ||
                received_age > target_timeout_s_ || !feedback_fresh()) {throw;}
              PublishDiagnostic("NEAR_RGB_EXACT_TF_WAIT_RETRY_SAME_IMAGE");
              // Preserve this exact RGB/box/measurement snapshot. Two explicit
              // 50ms waits supplement the original 300ms lookup, never latest TF.
              std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
          }
        };
      const auto camera_from_reference = exact_transform(camera_optical_frame_, lift_reference_frame_);
      if ((now()-image_time).seconds() < 0 || (now()-image_time).seconds() > target_timeout_s_ ||
        std::chrono::duration<double>(std::chrono::steady_clock::now()-received).count() >
        target_timeout_s_) {return reject("STALE_RGB");}
      if (!feedback_fresh()) {return false;}
      if (coarse_depth_tracking_ && !coarse_motion_in_progress_) {
        const double width = std::max(measured_size.vector.x, measured_size.vector.y);
        const double edge = std::min(measured_size.vector.x, measured_size.vector.y);
        if (!std::isfinite(width) || !std::isfinite(edge) || width < min_object_size_m_ ||
          width > max_object_size_m_ || edge < min_object_size_m_ ||
          width < locked_object_size_m_ * .5 || width > locked_object_size_m_ * 1.5) {
          return reject("COARSE_APPROACH_CUBE_SIZE_CHANGED");
        }
        const auto reference_from_measurement = exact_transform(lift_reference_frame_,
          measured.header.frame_id.empty() ? camera_optical_frame_ : measured.header.frame_id);
        tf2::doTransform(measured, reference, reference_from_measurement);
        if (!std::isfinite(reference.point.x) || !std::isfinite(reference.point.y) ||
          !std::isfinite(reference.point.z)) {return reject("INVALID_COARSE_RGBD_POINT");}
        // Only the depth-guided first stage refreshes the SAME continuous RGB identity.
        // The terminal commit below freezes one new target for all subsequent motion.
        std::lock_guard<std::mutex> lock(target_mutex_);
        locked_target_reference_ = reference;
      }
      geometry_msgs::msg::PointStamped camera;
      tf2::doTransform(reference, camera, camera_from_reference);
      near_depth::Projection projection;
      if (!near_depth::Project(calibration, {camera.point.x, camera.point.y, camera.point.z},
          info.width, info.height, projection, false)) {return reject("LOCKED_TARGET_OUT_OF_VIEW");}
      tf2::Transform camera_transform;
      tf2::fromMsg(camera_from_reference.transform, camera_transform);
      const auto camera_origin = camera_transform.inverse().getOrigin();
      std::array<double, 3> rgb_delta{};
      if (recovering) {
        // Propagate the last COMPLETE colour ray with exact ego-motion TF.
        // Its range remains a model estimate. Do not use the clipped centroid.
        const auto & cached = near_last_full_rgb_view_;
        const auto ray = camera_transform * tf2::Vector3(cached.target_reference.x(),
          cached.target_reference.y(), cached.target_reference.z());
        near_depth::Projection expected;
        if (!near_depth::Project(calibration, {ray.x(), ray.y(), ray.z()},
            info.width, info.height, expected, false)) {return reject("COLOR_SHAPE_UNAVAILABLE");}
        const double growth = near_seed_.color_z / expected.z;
        const double half_w = (near_seed_.box.right - near_seed_.box.left)*growth/2;
        const double half_h = (near_seed_.box.bottom - near_seed_.box.top)*growth/2;
        if (box.right < expected.x - half_w || box.left > expected.x + half_w ||
          box.bottom < expected.y - half_h || box.top > expected.y + half_h)
        {return reject("CLIPPED_RGB_IDENTITY_MISMATCH");}
        rgb_delta = {ray.x()-camera.point.x, ray.y()-camera.point.y, ray.z()-camera.point.z};
      } else if (!near_depth::RgbResidual(calibration,
          {camera.point.x, camera.point.y, camera.point.z}, box, info.width, info.height, rgb_delta))
      {return reject("INVALID_RGB_CORRECTION");}
      const auto delta = camera_transform.getBasis().transpose() *
        tf2::Vector3(rgb_delta[0], rgb_delta[1], rgb_delta[2]);
      const Eigen::Vector3d correction(delta.x(), delta.y(), delta.z());
      if (!allow_bounded_compensation && correction.norm() > visual_target_association_m_)
      {return reject("LOCKED_TARGET_RGB_MISMATCH");}
      if (measured_same_image) {
        geometry_msgs::msg::PointStamped observed_reference;
        const std::string frame = measured.header.frame_id.empty() ?
          camera_optical_frame_ : measured.header.frame_id;
        const auto reference_from_measurement = exact_transform(lift_reference_frame_, frame);
        if ((now()-image_time).seconds() < 0 || (now()-image_time).seconds() > target_timeout_s_ ||
          std::chrono::duration<double>(std::chrono::steady_clock::now()-received).count() >
          target_timeout_s_) {return reject("STALE_RGB");}
        if (!feedback_fresh()) {return false;}
        tf2::doTransform(measured, observed_reference, reference_from_measurement);
        const double association_distance = std::hypot(
          std::hypot(observed_reference.point.x - reference.point.x,
            observed_reference.point.y - reference.point.y),
          observed_reference.point.z - reference.point.z);
        if (association_distance > visual_target_association_m_) {
          if (allow_bounded_compensation && near_seed_.valid) {
            // A recovered near-range sample is not allowed to replace the
            // frozen object. Keep the same RGB identity and original model.
            measured_same_image = false;
            PublishDiagnostic("RECOVERED_DEPTH_OUTLIER_IGNORED_STATIC_RGB_LOCK_RETAINED");
          } else {
            if (image_time.nanoseconds() != near_last_bad_association_stamp_ns_) {
              ++near_rgb_association_bad_frames_seen_;
              near_last_bad_association_stamp_ns_ = image_time.nanoseconds();
            }
            RCLCPP_WARN(
              get_logger(),
              "NEAR_RGB_TARGET_ASSOCIATION distance=%.4f threshold=%.4f "
              "locked=(%.4f,%.4f,%.4f) measured=(%.4f,%.4f,%.4f) image_stamp=%.9f",
              association_distance, visual_target_association_m_,
              reference.point.x, reference.point.y, reference.point.z,
              observed_reference.point.x, observed_reference.point.y, observed_reference.point.z,
              image_time.seconds());
            if (near_rgb_association_bad_frames_seen_ < near_rgb_association_bad_frames_) {
              PublishDiagnostic(
                "NEAR_RGB_ASSOCIATION_TRANSIENT_TOLERATED count=" +
                std::to_string(near_rgb_association_bad_frames_seen_));
              return true;
            }
            return reject("MEASURED_TARGET_CHANGED");
          }
        }
        if (measured_same_image) {
          near_rgb_association_bad_frames_seen_ = 0;
          near_last_bad_association_stamp_ns_ = 0;
          geometry_msgs::msg::PointStamped measured_camera;
          tf2::doTransform(observed_reference, measured_camera, camera_from_reference);
          near_depth::Projection measured_projection;
          if (!near_depth::Project(calibration,
              {measured_camera.point.x, measured_camera.point.y, measured_camera.point.z},
              info.width, info.height, measured_projection))
          {return reject("INVALID_MEASURED_RGBD_SEED");}
          if (!near_seed_.valid || (coarse_depth_tracking_ && !coarse_motion_in_progress_)) {
            // Each depth-guided step starts from its fresh measured seed. Once
            // terminal-frozen, recovery only verifies the immutable seed and
            // never replenishes its age/travel allowance.
            near_seed_ = {box, projection.z, true};
            near_seed_image_stamp_ns_ = image_time.nanoseconds();
            near_seed_stamp_ns_ = rclcpp::Time(reference.header.stamp).nanoseconds();
            RCLCPP_INFO(get_logger(),
              "NEAR_RGB_SCALE_SEED image_stamp=%ld lock_stamp=%ld "
              "box=(%.12f,%.12f,%.12f,%.12f) color_z=%.12f",
              near_seed_image_stamp_ns_, near_seed_stamp_ns_, box.left, box.top,
              box.right, box.bottom, projection.z);
            near_last_camera_origin_ = camera_origin;
            near_last_image_stamp_ns_ = image_time.nanoseconds();
            near_camera_travel_m_ = 0;
          }
        }
      }
      if (!measured_same_image) {
        if (!near_seed_.valid) {return reject("NO_RELIABLE_RGBD_LOCK");}
        const double increment = image_time.nanoseconds() > near_last_image_stamp_ns_ ?
          (camera_origin - near_last_camera_origin_).length() : 0;
        near_depth::Evidence evidence{true, true, true, image_age, receipt_age,
          (now().nanoseconds() - near_seed_stamp_ns_) * 1e-9, near_camera_travel_m_ + increment};
        if (const auto reason = near_depth::PredictionRejection(near_seed_, evidence, box, projection,
            target_timeout_s_,
            near_path_allowance_ready_ ? near_path_max_age_s_ : near_depth_prediction_max_age_s_,
            near_path_allowance_ready_ ? near_path_max_travel_m_ : near_depth_prediction_max_travel_m_,
            correction.norm(), visual_target_association_m_, recovering, info.width, info.height,
            allow_bounded_compensation, identity_continuous))
        {
          const bool scale_mismatch = std::string(reason) == "LOCKED_TARGET_SCALE_MISMATCH";
          const bool scale_advisory = scale_mismatch && automatic_rgb_approach_enabled_ &&
            allow_bounded_compensation && identity_continuous;
          if (scale_mismatch && (!scale_advisory ||
              image_time.nanoseconds() > near_last_image_stamp_ns_)) {
            // Keep the original scale evidence. During automatic approach a
            // continuous live RGB identity can still supply visual correction;
            // model scale alone must not abort it. Final capture stays strict.
            const double growth = near_seed_.color_z / projection.z;
            const double wr = (box.right-box.left) /
              (near_seed_.box.right-near_seed_.box.left) / growth;
            const double hr = (box.bottom-box.top) /
              (near_seed_.box.bottom-near_seed_.box.top) / growth;
            const bool wc = recovering &&
              (box.left <= 1./info.width || box.right >= 1-1./info.width);
            const bool hc = recovering &&
              (box.top <= 1./info.height || box.bottom >= 1-1./info.height);
            RCLCPP_WARN(get_logger(),
              "NEAR_RGB_SCALE_DETAIL image_stamp=%ld seed_image_stamp=%ld lock_stamp=%ld "
              "seed_box=(%.12f,%.12f,%.12f,%.12f) seed_color_z=%.12f "
              "box=(%.12f,%.12f,%.12f,%.12f) model_color_z=%.12f growth=%.12f "
              "width_ratio=%.12f height_ratio=%.12f width_clipped=%d height_clipped=%d "
              "recovery=%d image_size=(%u,%u) original_bounds=(0.65,1.5)",
              image_time.nanoseconds(), near_seed_image_stamp_ns_, near_seed_stamp_ns_,
              near_seed_.box.left, near_seed_.box.top, near_seed_.box.right,
              near_seed_.box.bottom, near_seed_.color_z, box.left, box.top, box.right,
              box.bottom, projection.z, growth, wr, hr, wc, hc, recovering,
              info.width, info.height);
            const auto & t = camera_from_reference.transform;
            RCLCPP_WARN(get_logger(),
              "NEAR_RGB_SCALE_GEOMETRY image_stamp=%ld tf_stamp=%ld tf_parent=%s "
              "tf_child=%s tf_xyz=(%.12f,%.12f,%.12f) tf_q=(%.12f,%.12f,%.12f,%.12f) "
              "locked_base=(%.12f,%.12f,%.12f) model_depth=(%.12f,%.12f,%.12f) "
              "raw_point_stamp=%ld raw_point_frame=%s raw_point=(%.12f,%.12f,%.12f) "
              "depth_used=%d raw_same_stamp=%d",
              image_time.nanoseconds(), rclcpp::Time(camera_from_reference.header.stamp).nanoseconds(),
              camera_from_reference.header.frame_id.c_str(), camera_from_reference.child_frame_id.c_str(),
              t.translation.x, t.translation.y, t.translation.z, t.rotation.x, t.rotation.y,
              t.rotation.z, t.rotation.w, reference.point.x, reference.point.y, reference.point.z,
              camera.point.x, camera.point.y, camera.point.z,
              rclcpp::Time(measured.header.stamp).nanoseconds(), measured.header.frame_id.c_str(),
              measured.point.x, measured.point.y, measured.point.z, measured_same_image,
              measured.header.stamp == message.header.stamp);
            {
              std::lock_guard<std::mutex> lock(feedback_mutex_);
              const auto & q = latest_joint_state_;
              RCLCPP_WARN(get_logger(),
                "NEAR_RGB_SCALE_LATEST_FEEDBACK_NOT_IMAGE_TIME_Q stamp=%ld "
                "q=(%.12f,%.12f,%.12f,%.12f,%.12f,%.12f)",
                rclcpp::Time(q.header.stamp).nanoseconds(), JointPosition(q, "joint1"),
                JointPosition(q, "joint2"), JointPosition(q, "joint3"),
                JointPosition(q, "joint4"), JointPosition(q, "joint5"), JointPosition(q, "joint6"));
            }
          }
          if (scale_advisory) {
            if (image_time.nanoseconds() > near_last_image_stamp_ns_) {
              PublishDiagnostic("NEAR_RGB_SCALE_ADVISORY_CONTINUE_VISUAL_CORRECTION");
              RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                "NEAR_RGB_SCALE_ADVISORY_CONTINUE_VISUAL_CORRECTION: "
                "same live RGB identity retained; frozen target and final jaw check unchanged.");
            }
          } else {
            return reject(reason);
          }
        }
        predicted = true;  // depth_valid is still false; old measurement stamp is retained.
      }
      // Account actual motion on distinct RGB frames in both modes. New
      // measured depth must not reset a frozen target's path consumption.
      if (image_time.nanoseconds() > near_last_image_stamp_ns_) {
        near_camera_travel_m_ += (camera_origin - near_last_camera_origin_).length();
        near_last_camera_origin_ = camera_origin;
        near_last_image_stamp_ns_ = image_time.nanoseconds();
      }
      if (predicted != near_last_mode_predicted_) {
        PublishDiagnostic(predicted ? "NEAR_RGB_LOCKED_3D_PREDICTION_NOT_MEASURED_DEPTH" :
          "NEAR_RGB_MEASURED_DEPTH_RESTORED_STATIC_TARGET_UNCHANGED");
        near_last_mode_predicted_ = predicted;
      }
      LockedRgbView view;
      view.valid = true; view.recovering = recovering; view.box = box;
      view.measured_rgbd = measured_same_image;
      if (measured_same_image) {
        geometry_msgs::msg::PointStamped measured_camera;
        const auto reference_from_measurement = exact_transform(lift_reference_frame_,
          measured.header.frame_id.empty() ? camera_optical_frame_ : measured.header.frame_id);
        geometry_msgs::msg::PointStamped measured_reference;
        tf2::doTransform(measured, measured_reference, reference_from_measurement);
        tf2::doTransform(measured_reference, measured_camera, camera_from_reference);
        near_depth::Projection raw_projection;
        if (!near_depth::Project(calibration,
            {measured_camera.point.x, measured_camera.point.y, measured_camera.point.z},
            info.width, info.height, raw_projection, false)) {return reject("INVALID_MEASURED_RANGE");}
        view.measured_color_range_m = raw_projection.z;
        view.measured_size_m = std::max(measured_size.vector.x, measured_size.vector.y);
        view.measured_min_size_m = std::min(measured_size.vector.x, measured_size.vector.y);
      }
      view.calibration = calibration; view.width = info.width; view.height = info.height;
      view.stamp_ns = image_time.nanoseconds(); view.correction = correction;
      view.target_reference = Eigen::Vector3d(reference.point.x, reference.point.y,
        reference.point.z) + correction;
      near_view_recovery_ = recovering;
      near_last_visible_rgb_box_ = box;
      if (!recovering) {near_last_full_rgb_view_ = view;}
      if (observed_view) {*observed_view = view;}
      return true;
    } catch (const tf2::TransformException & error) {
      RCLCPP_WARN(get_logger(), "NEAR_RGB_EXACT_TF_FAILED image_stamp=%ld error=%s",
        image_time.nanoseconds(), error.what());
      return reject("EXACT_IMAGE_TF_UNAVAILABLE");
    }
  }

  bool ReadVisualBox(visual_grasp::Box & box, bool full = false)
  {
    std::lock_guard<std::mutex> lock(visual_mutex_);
    const double age = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - raw_box_received_).count();
    const double image_age = (now().nanoseconds() - raw_box_stamp_ns_) * 1e-9;
    if (!raw_box_valid_ || age > target_timeout_s_ || image_age < -.1 ||
      image_age > target_timeout_s_ || (full && raw_full_frames_ < 3)) {return false;}
    box = raw_box_;
    if (visual_locked_box_valid_ && !visual_grasp::Associated(visual_locked_box_, box)) {
      return false;
    }
    visual_locked_box_ = box;
    visual_locked_box_valid_ = true;
    return true;
  }

  bool WaitFullVisualBox()
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(2500);
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      visual_grasp::Box box{};
      if (ReadVisualBox(box, true)) {return true;}
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return false;
  }

  bool WaitApproachVisualBox()
  {
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration<double>(target_timeout_s_);
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      visual_grasp::Box box{};
      if (ReadVisualBox(box, false)) {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        const bool qualified_same_frame = qualified_box_message_.polygon.points.size() == 4 &&
          rclcpp::Time(qualified_box_message_.header.stamp).nanoseconds() == raw_box_stamp_ns_;
        const bool clipped_known_frame = qualified_box_message_.polygon.points.empty() &&
          near_last_full_rgb_view_.valid && near_depth::Cropped(raw_box_,
          raw_image_info_.width, raw_image_info_.height);
        if (raw_box_stamp_ns_ > near_last_command_image_stamp_ns_ &&
          (qualified_same_frame || clipped_known_frame)) {return true;}
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return false;
  }

  bool VisualFaceInReference(geometry_msgs::msg::PointStamped & result)
  {
    geometry_msgs::msg::PointStamped face, locked;
    const auto steady = std::chrono::steady_clock::now();
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      const auto fresh = [&](const auto & stamp) {
          return stamp != std::chrono::steady_clock::time_point{} &&
                 std::chrono::duration<double>(steady - stamp).count() <= target_timeout_s_;
        };
      if (!target_valid_ || !depth_valid_ || !fresh(target_point_received_time_) ||
        !fresh(target_valid_received_time_) || !fresh(depth_valid_received_time_) ||
        !fresh(target_size_received_time_)) {return false;}
      const double size = std::max(target_size_.vector.x, target_size_.vector.y);
      if (!std::isfinite(size) || size < min_object_size_m_ || size > max_object_size_m_ ||
        size < locked_object_size_m_ * .5 || size > locked_object_size_m_ * 1.5) {return false;}
      face = target_point_camera_; locked = locked_target_reference_;
    }
    if (rclcpp::Time(face.header.stamp).nanoseconds() <= 0) {return false;}
    {
      std::lock_guard<std::mutex> lock(visual_mutex_);
      const auto stamp = rclcpp::Time(face.header.stamp).nanoseconds();
      const auto & p = raw_target_projection_.point;
      if (!raw_box_valid_ || raw_box_stamp_ns_ != stamp ||
        rclcpp::Time(raw_target_projection_.header.stamp).nanoseconds() != stamp ||
        !std::isfinite(p.x) || !std::isfinite(p.y) || p.x < raw_box_.left - .01 ||
        p.x > raw_box_.right + .01 || p.y < raw_box_.top - .01 || p.y > raw_box_.bottom + .01)
      {return false;}
    }
    try {
      const auto transform = tf_buffer_->lookupTransform(lift_reference_frame_,
        face.header.frame_id.empty() ? camera_optical_frame_ : face.header.frame_id,
        rclcpp::Time(face.header.stamp));  // Same image time, not latest TF.
      tf2::doTransform(face, result, transform);
      const double distance = std::hypot(std::hypot(result.point.x - locked.point.x,
        result.point.y - locked.point.y), result.point.z - locked.point.z);
      return std::isfinite(distance) && distance <= visual_target_association_m_;
    } catch (const tf2::TransformException &) {return false;}
  }

  static geometry_msgs::msg::PoseStamped ReducedVisualOrientationAtSameTip(
    const geometry_msgs::msg::PoseStamped & target, const Eigen::Isometry3d & current,
    double tip_offset, double fraction)
  {
    const Eigen::Quaterniond desired(target.pose.orientation.w, target.pose.orientation.x,
      target.pose.orientation.y, target.pose.orientation.z);
    const Eigen::Vector3d origin(target.pose.position.x, target.pose.position.y, target.pose.position.z);
    if (!std::isfinite(fraction) || fraction == 0 || fraction < -1 || fraction >= 1 ||
      !std::isfinite(tip_offset) || tip_offset <= 0 || !origin.allFinite() ||
      !desired.coeffs().allFinite() || desired.norm() < 1e-12 || !current.matrix().allFinite())
    {throw std::invalid_argument("Invalid reduced visual attitude");}
    const Eigen::Vector3d local_tip(0, 0, tip_offset);
    const Eigen::Vector3d fixed_tip = origin + desired.normalized() * local_tip;
    const auto orientation = Eigen::Quaterniond(current.rotation()).slerp(
      fraction, desired.normalized()).normalized();
    const Eigen::Vector3d reduced_origin = fixed_tip - orientation * local_tip;
    auto result = target;
    result.pose.position.x = reduced_origin.x(); result.pose.position.y = reduced_origin.y();
    result.pose.position.z = reduced_origin.z();
    result.pose.orientation.x = orientation.x(); result.pose.orientation.y = orientation.y();
    result.pose.orientation.z = orientation.z(); result.pose.orientation.w = orientation.w();
    return result;
  }

  bool CanRetryVisualOrientation(const std::string & stage, bool automatic_segment) const
  {
    return automatic_rgb_approach_enabled_ && automatic_segment &&
           stage.rfind("AUTOMATIC_RGB_STEP_", 0) == 0;
  }

  bool ClipCheckedJointPrefix(trajectory_msgs::msg::JointTrajectory & trajectory,
    std::size_t accepted_points, const std::string & stage, bool automatic_segment)
  {
    if (!CanRetryVisualOrientation(stage, automatic_segment) || accepted_points < 2 ||
      accepted_points >= trajectory.points.size()) {return false;}
    trajectory.points.resize(accepted_points);
    PublishDiagnostic(stage + "_CHECKED_JOINT_PREFIX_CLIPPED_REPLAN_NEXT_FRAME");
    return true;
  }

  bool ExecuteVisualPose(
    const geometry_msgs::msg::PoseStamped & target,
    const std::shared_ptr<moveit::core::RobotState> & state, const std::string & stage,
    double tip_limit = .005, double angle_limit = .017453293,
    trajectory_msgs::msg::JointTrajectory * completed = nullptr,
    geometry_msgs::msg::PoseStamped * selected_goal = nullptr)
  {
    moveit_msgs::msg::RobotTrajectory plan;
    // Analysis topic only: expose the EXACT requested pose before planning.
    // It is not an adapter command and cannot execute a failed path.
    target_pose_publisher_->publish(target);
    RCLCPP_INFO(get_logger(),
      "%s POSE_REQUEST frame=%s xyz=(%.12f,%.12f,%.12f) q=(%.12f,%.12f,%.12f,%.12f)",
      stage.c_str(), target.header.frame_id.c_str(), target.pose.position.x,
      target.pose.position.y, target.pose.position.z, target.pose.orientation.x,
      target.pose.orientation.y, target.pose.orientation.z, target.pose.orientation.w);
    auto planned_goal = target;
    bool planned = PlanArmCartesianFromState(target, stage, state, plan);
    std::string rejection;
    if (planned && !RealTrajectoryWithinLimits(plan.joint_trajectory, rejection)) {
      PublishDiagnostic(stage + ":" + rejection); planned = false;
    }
    if (!planned && CanRetryVisualOrientation(stage, completed != nullptr)) {
      const Eigen::Isometry3d current = state->getGlobalLinkTransform(target.header.frame_id).inverse() *
        state->getGlobalLinkTransform(end_effector_link_);
      // Try smaller toward-target turns first, then bounded reverse turns.
      // All candidates preserve the requested capture tip; no joint edits.
      for (const double fraction : {.75, .50, .25, -.25, -.50, -.75, -1.0}) {
        const auto candidate = ReducedVisualOrientationAtSameTip(
          target, current, gripper_tip_offset_m_, fraction);
        const auto candidate_stage = stage + "_ORIENTATION_" +
          std::to_string(static_cast<int>(fraction * 100));
        target_pose_publisher_->publish(candidate);
        RCLCPP_INFO(get_logger(),
          "%s POSE_REQUEST frame=%s xyz=(%.12f,%.12f,%.12f) "
          "q=(%.12f,%.12f,%.12f,%.12f) SAME_TIP_REPLAN_NO_PARTIAL_EXECUTION",
          candidate_stage.c_str(), candidate.header.frame_id.c_str(), candidate.pose.position.x,
          candidate.pose.position.y, candidate.pose.position.z, candidate.pose.orientation.x,
          candidate.pose.orientation.y, candidate.pose.orientation.z, candidate.pose.orientation.w);
        moveit_msgs::msg::RobotTrajectory candidate_plan;
        if (!PlanArmCartesianFromState(candidate, candidate_stage, state, candidate_plan)) {continue;}
        if (!RealTrajectoryWithinLimits(candidate_plan.joint_trajectory, rejection)) {
          PublishDiagnostic(candidate_stage + ":" + rejection); continue;
        }
        plan = std::move(candidate_plan); planned_goal = candidate; planned = true;
        RCLCPP_INFO(get_logger(), "%s REACHABLE_VISUAL_ATTITUDE fraction=%.2f "
          "SAME_TIP_FULL_PATH_ORIGINAL_LIMITS", stage.c_str(), fraction);
        break;
      }
    }
    if (!planned) {return false;}
    const auto start_pose = state->getGlobalLinkTransform(end_effector_link_);
    const Eigen::Vector3d local_tip(0, 0, gripper_tip_offset_m_);
    std::size_t accepted_points = 0;
    for (const auto & point : plan.joint_trajectory.points) {
      moveit::core::RobotState planned(*state);
      bool joint_travel_rejected = false;
      for (std::size_t i = 0; i < plan.joint_trajectory.joint_names.size(); ++i) {
        if (std::abs(point.positions[i] - state->getVariablePosition(
            plan.joint_trajectory.joint_names[i])) > .08) {
          joint_travel_rejected = true; break;
        }
        planned.setVariablePosition(plan.joint_trajectory.joint_names[i], point.positions[i]);
      }
      if (joint_travel_rejected) {
        // The full Cartesian path and all retained earlier points passed the
        // original checks. Replan after that bounded prefix from measured state.
        if (ClipCheckedJointPrefix(plan.joint_trajectory, accepted_points, stage, completed != nullptr)) {
          break;
        }
        PublishDiagnostic(stage + "_JOINT_TRAVEL_LIMIT"); return false;
      }
      planned.update();
      const auto & pose = planned.getGlobalLinkTransform(end_effector_link_);
      const double wrist_limit = completed ?
        tip_limit + 2 * gripper_tip_offset_m_ * std::sin(angle_limit / 2) : .005;
      if (!visual_grasp::DistanceStepWithin(
          (pose.translation() - start_pose.translation()).norm(), wrist_limit, completed != nullptr) ||
        !visual_grasp::DistanceStepWithin(
          (pose * local_tip - start_pose * local_tip).norm(), tip_limit, completed != nullptr) ||
        Eigen::Quaterniond(start_pose.rotation()).angularDistance(
          Eigen::Quaterniond(pose.rotation())) > angle_limit + (completed ? 1e-6 : 0.0)) {
        RCLCPP_WARN(get_logger(),
          "%s bounds: wrist=%.9f/%.9f tip=%.9f/%.9f angle=%.9f/%.9f",
          stage.c_str(), (pose.translation() - start_pose.translation()).norm(), wrist_limit,
          (pose * local_tip - start_pose * local_tip).norm(), tip_limit,
          Eigen::Quaterniond(start_pose.rotation()).angularDistance(
            Eigen::Quaterniond(pose.rotation())), angle_limit);
        if (completed && accepted_points >= 2) {
          // Execute only the already collision-checked prefix, then replan
          // from actual feedback/new RGB. Never publish the oversized suffix.
          plan.joint_trajectory.points.resize(accepted_points);
          PublishDiagnostic(stage + "_CHECKED_PREFIX_CLIPPED_REPLAN_NEXT_FRAME");
          break;
        }
        PublishDiagnostic(stage + "_POSE_STEP_BOUND_REJECTED"); return false;
      }
      ++accepted_points;
    }
    const auto before_output = FreshMeasuredState(stage + "_BEFORE_OUTPUT");
    if (!before_output) {return false;}
    for (const auto & name : plan.joint_trajectory.joint_names) {
      if (std::abs(before_output->getVariablePosition(name) -
          state->getVariablePosition(name)) > (completed ? trajectory_feedback_tolerance_rad_ : .002)) {
        RCLCPP_WARN(get_logger(), "%s start changed: %s planned=%.9f measured=%.9f",
          stage.c_str(), name.c_str(), state->getVariablePosition(name),
          before_output->getVariablePosition(name));
        PublishDiagnostic(stage + "_START_FEEDBACK_CHANGED"); return false;
      }
    }
    if (selected_goal) {*selected_goal = planned_goal;}
    if (!ExecuteArmTrajectory(plan.joint_trajectory)) {return false;}
    const auto & end = plan.joint_trajectory.points.back();
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration<double>(trajectory_feedback_timeout_s_);
    auto settled = std::chrono::steady_clock::time_point{};
    const double endpoint_tolerance = completed ? trajectory_feedback_tolerance_rad_ : .002;
    std::vector<double> settled_positions;
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      const auto measured = FreshMeasuredState(stage + "_SETTLE");
      if (!measured) {return false;}
      bool reached = true;
      for (std::size_t i = 0; i < plan.joint_trajectory.joint_names.size(); ++i) {
        reached = reached && std::abs(measured->getVariablePosition(
          plan.joint_trajectory.joint_names[i]) - end.positions[i]) <= endpoint_tolerance;
        if (completed && settled != std::chrono::steady_clock::time_point{} &&
          std::abs(measured->getVariablePosition(plan.joint_trajectory.joint_names[i]) -
          settled_positions[i]) > .002) {settled = {};}
      }
      if (!reached) {settled = {};}
      else if (settled == std::chrono::steady_clock::time_point{}) {
        settled = std::chrono::steady_clock::now();
        settled_positions.clear();
        for (const auto & name : plan.joint_trajectory.joint_names) {
          settled_positions.push_back(measured->getVariablePosition(name));
        }
      } else if (std::chrono::duration<double>(
          std::chrono::steady_clock::now() - settled).count() >= .5)
      {
        std::lock_guard<std::mutex> lock(visual_mutex_);
        if (!completed) {
          raw_full_frames_ = 0;  // Independent preview still requires three post-settle frames.
          raw_box_stamp_ns_ = std::max(raw_box_stamp_ns_, now().nanoseconds());
        }
        if (completed) {*completed = plan.joint_trajectory;}
        PublishDiagnostic(stage + "_MEASURED_SETTLING_CONFIRMED");
        return true;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    PublishDiagnostic(stage + "_MEASURED_SETTLING_TIMEOUT");
    return false;
  }

  // Offline/opt-in limited preview only. Default real YAML explicitly disables
  // this branch. Four steps and 20 mm total tool-origin travel, including recovery;
  // enabling any physical preview needs its own explicitly bounded authorization.
  void VisualMicrostepPreview()
  {
    namespace gg = grasp_geometry;
    {
      std::lock_guard<std::mutex> lock(visual_mutex_);
      visual_locked_box_valid_ = false;
    }
    gg::Point start_origin{};
    double total_travel = 0;
    int recoveries = 0;
    for (int step = 0; step < visual_microstep_max_steps_ && !cancel_requested_; ++step) {
      const bool full = WaitFullVisualBox();
      const auto state = FreshMeasuredState("VISUAL_MICROSTEP");
      if (!state || state->getRobotModel()->getModelFrame() != lift_reference_frame_) {
        Fail("VISUAL_MEASURED_STATE_UNAVAILABLE"); return;
      }
      const auto & fk = state->getGlobalLinkTransform(end_effector_link_);
      const Eigen::Quaterniond q(fk.rotation());
      const gg::DirectedPose current{{fk.translation().x(), fk.translation().y(), fk.translation().z()},
        {q.x(), q.y(), q.z(), q.w()}};
      if (step == 0) {start_origin = current.origin;}
      gg::DirectedPose next = current;
      visual_grasp::Box box{};
      if (!ReadVisualBox(box)) {Fail("VISUAL_SAME_COLOUR_UNAVAILABLE_NO_CLOSE"); return;}
      if (!full) {
        if (recoveries >= visual_view_recovery_steps_ || box.bottom < .98 ||
          box.top <= .02 || box.left <= .02 || box.right >= .98) {
          Fail("VISUAL_FULL_VIEW_UNCONFIRMED_NO_CLOSE"); return;
        }
        const auto * joint = state->getRobotModel()->getJointModel("joint5");
        if (!joint || joint->getType() != moveit::core::JointModel::REVOLUTE) {
          Fail("VISUAL_VIEW_AXIS_UNAVAILABLE"); return;
        }
        const auto * revolute = static_cast<const moveit::core::RevoluteJointModel *>(joint);
        const auto & pivot = state->getGlobalLinkTransform(joint->getChildLinkModel());
        const Eigen::Vector3d axis = pivot.rotation() * revolute->getAxis();
        const Eigen::Vector3d position = pivot.translation() +
          Eigen::AngleAxisd(visual_view_recovery_angle_rad_, axis.normalized()) *
          (fk.translation() - pivot.translation());
        next.origin = {position.x(), position.y(), position.z()};
        next.orientation = gg::RotateOrientationAboutAxis(current.orientation,
          {axis.x(), axis.y(), axis.z()}, visual_view_recovery_angle_rad_);
        ++recoveries;
        PublishState("VISUAL_VIEW_RECOVERY");
      } else {
        geometry_msgs::msg::PointStamped face;
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(2500);
        while (!VisualFaceInReference(face) && rclcpp::ok() && !cancel_requested_ &&
          std::chrono::steady_clock::now() < deadline) {
          std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        if (cancel_requested_ || !VisualFaceInReference(face) || !ReadVisualBox(box, true)) {
          Fail("VISUAL_ASSOCIATED_RGBD_UNAVAILABLE_NO_CLOSE"); return;
        }
        const double insertion = gg::SurfaceInsertion(
          locked_object_min_size_m_, surface_insertion_fraction_, surface_insertion_max_m_);
        const auto axis = gg::Rotate(current.orientation, {0, 0, 1});
        const auto tip = gg::Tip(current.origin, axis, gripper_tip_offset_m_);
        const double gap = std::hypot(std::hypot(face.point.x + axis[0] * insertion - tip[0],
          face.point.y + axis[1] * insertion - tip[1]), face.point.z + axis[2] * insertion - tip[2]);
        RCLCPP_INFO(get_logger(), "VISUAL_STEP=%d gap=%.4f raw_bbox=(%.3f,%.3f,%.3f,%.3f)",
          step, gap, box.left, box.top, box.right, box.bottom);
        if (gap <= .002) {
          // Surface + insertion is a model hypothesis, not the physical pad
          // volume. Even perfect model convergence can NEVER close in preview.
          PublishDiagnostic("VISUAL_PREVIEW_MODEL_CONTACT_NOT_ENTITY_CAPTURE_NO_CLOSE");
          PublishState("VISUAL_PREVIEW_HOLD_NO_CLOSE"); return;
        }
        try {
          next = visual_grasp::TipMicrostep(current, {face.point.x, face.point.y, face.point.z},
            gripper_tip_offset_m_, insertion, visual_microstep_m_, visual_microstep_angle_rad_);
        } catch (const std::invalid_argument &) {Fail("VISUAL_STEP_GEOMETRY_INVALID"); return;}
        PublishState("VISUAL_GRASP_MICROSTEP");
      }
      const double travel = std::hypot(std::hypot(next.origin[0] - current.origin[0],
        next.origin[1] - current.origin[1]), next.origin[2] - current.origin[2]);
      const double from_start = std::hypot(std::hypot(next.origin[0] - start_origin[0],
        next.origin[1] - start_origin[1]), next.origin[2] - start_origin[2]);
      const auto old_tip = gg::Tip(current.origin, gg::Rotate(current.orientation, {0, 0, 1}),
        gripper_tip_offset_m_);
      const auto new_tip = gg::Tip(next.origin, gg::Rotate(next.orientation, {0, 0, 1}),
        gripper_tip_offset_m_);
      const double tip_travel = std::hypot(std::hypot(new_tip[0] - old_tip[0],
        new_tip[1] - old_tip[1]), new_tip[2] - old_tip[2]);
      if (!std::isfinite(travel) || travel > .005 || tip_travel > .005 + 1e-9 ||
        gg::QuaternionDistance(current.orientation, next.orientation) > .017453293 ||
        total_travel + travel > .020 || from_start > .020) {
        Fail("VISUAL_PREVIEW_20MM_BUDGET_EXHAUSTED_NO_CLOSE"); return;
      }
      geometry_msgs::msg::PoseStamped target;
      target.header.frame_id = lift_reference_frame_; target.header.stamp = now();
      target.pose.position.x = next.origin[0]; target.pose.position.y = next.origin[1];
      target.pose.position.z = next.origin[2]; target.pose.orientation.x = next.orientation[0];
      target.pose.orientation.y = next.orientation[1]; target.pose.orientation.z = next.orientation[2];
      target.pose.orientation.w = next.orientation[3];
      if (!ExecuteVisualPose(target, state, "VISUAL_STEP_" + std::to_string(step))) {
        Fail("VISUAL_MICROSTEP_EXECUTION_FAILED"); return;
      }
      total_travel += travel;
    }
    Fail("VISUAL_PREVIEW_STEP_BUDGET_EXHAUSTED_NO_CLOSE");
  }

  bool LockedRgbCorrection(Eigen::Vector3d & correction, LockedRgbView * view = nullptr)
  {
    geometry_msgs::msg::PointStamped locked;
    rclcpp::Time image_time(0, 0, get_clock()->get_clock_type());
    bool predicted = false;
    near_depth::Calibration c;
    geometry_msgs::msg::PolygonStamped box;
    sensor_msgs::msg::CameraInfo info;
    LockedRgbView snapshot;
    if (!ObserveLockedTarget(locked, image_time, predicted, &box, &info, &c, &snapshot,
        automatic_rgb_approach_enabled_)) {return false;}
    if (near_rgb_association_bad_frames_seen_ != 0) {
      // Preserve the existing bounded outlier tolerance while advancing the
      // original lock. Suspect depth must never generate an RGB correction.
      correction.setZero(); if (view) {*view = {};}
      return true;
    }
    if (box.polygon.points.size() != 4 ||
      rclcpp::Time(box.header.stamp) != image_time) {
      PublishDiagnostic("LOCKED_RGB_SNAPSHOT_INVALID"); return false;
    }
    correction = snapshot.correction;
    if (view) {*view = snapshot;}
    return snapshot.valid && correction.allFinite() &&
           (automatic_rgb_approach_enabled_ || correction.norm() <= visual_target_association_m_);
  }

  bool GuardApproachView(grasp_geometry::DirectedPose & nominal,
    const Eigen::Isometry3d & tool_to_depth, const LockedRgbView & view)
  {
    if (!view.valid) {return false;}  // Existing transient-depth tolerance: no new correction.
    const auto & c = view.calibration;
    Eigen::Matrix3d r;
    r << c.rotation[0], c.rotation[1], c.rotation[2], c.rotation[3], c.rotation[4],
      c.rotation[5], c.rotation[6], c.rotation[7], c.rotation[8];
    Eigen::Isometry3d depth_to_color = Eigen::Isometry3d::Identity();
    depth_to_color.linear() = r.inverse();
    depth_to_color.translation() = -r.inverse()*Eigen::Vector3d(
      c.translation[0], c.translation[1], c.translation[2]);
    const Eigen::Isometry3d tool_to_color = tool_to_depth * depth_to_color;
    const Eigen::Quaterniond q_camera(tool_to_color.linear());
    const grasp_geometry::DirectedPose camera_pose{{tool_to_color.translation().x(),
      tool_to_color.translation().y(), tool_to_color.translation().z()},
      {q_camera.x(), q_camera.y(), q_camera.z(), q_camera.w()}};
    Eigen::Isometry3d candidate = Eigen::Isometry3d::Identity();
    candidate.linear() = Eigen::Quaterniond(nominal.orientation[3], nominal.orientation[0],
      nominal.orientation[1], nominal.orientation[2]).normalized().toRotationMatrix();
    candidate.translation() = Eigen::Vector3d(nominal.origin[0], nominal.origin[1], nominal.origin[2]);
    const auto color = (candidate * tool_to_color).inverse() * view.target_reference;
    if (color.z() <= .001) {return false;}
    double u = c.fx*color.x()/color.z() + c.cx;
    const double v = c.fy*color.y()/color.z() + c.cy;
    if (c.mirror) {u = c.width - 1 - u;}
    const double x = u/(c.width-1)*(view.width-1)/view.width;
    const double y = v/(c.height-1)*(view.height-1)/view.height;
    // Begin recovery one half-box BEFORE the original 2% full-view margin.
    // This is a geometry-derived look-ahead, not a new acceptance threshold.
    const double inset_x = .02 + view.box.right - view.box.left;
    const double inset_y = .02 + view.box.bottom - view.box.top;
    const double desired_x = inset_x < .5 ? std::clamp(x, inset_x, 1-inset_x) : .5;
    const double desired_y = inset_y < .5 ? std::clamp(y, inset_y, 1-inset_y) : .5;
    if (std::hypot(desired_x-x, desired_y-y) < 1e-8) {return false;}
    double ray_u = desired_x*view.width*(c.width-1)/(view.width-1);
    const double ray_v = desired_y*view.height*(c.height-1)/(view.height-1);
    if (c.mirror) {ray_u = c.width - 1 - ray_u;}
    const bool aimed = visual_grasp::AimCameraAtFixedTip(nominal, camera_pose,
      {view.target_reference.x(), view.target_reference.y(), view.target_reference.z()},
      {(ray_u-c.cx)/c.fx, (ray_v-c.cy)/c.fy, 1}, gripper_tip_offset_m_);
    PublishDiagnostic(aimed ? "RGB_VIEW_GUARD_TIP_PRESERVED" :
      "RGB_VIEW_GUARD_RAY_INFEASIBLE_TIP_NOT_DISPLACED");
    return aimed;
  }

  void AutomaticRgbApproach(
    const std::vector<geometry_msgs::msg::Pose> & pre_waypoints,
    const std::vector<geometry_msgs::msg::Pose> & descent_waypoints,
    const moveit_msgs::msg::RobotTrajectory & pre_plan,
    const moveit_msgs::msg::RobotTrajectory & descent_plan,
    const std::shared_ptr<moveit::core::RobotState> & start)
  {
    namespace gg = grasp_geometry;
    if (!near_seed_.valid || !near_depth_tracking_active_ ||
      pre_waypoints.empty() || descent_waypoints.empty()) {
      Fail("AUTOMATIC_RGB_INITIAL_LOCK_UNAVAILABLE"); return;
    }
    std::vector<geometry_msgs::msg::Pose> waypoints = pre_waypoints;
    waypoints.insert(waypoints.end(), descent_waypoints.begin(), descent_waypoints.end());
    const double angle_limit = .01745329252;
    double camera_arc = 0, tip_arc = 0, angle_arc = 0, planned_seconds = 0;
    Eigen::Isometry3d tool_to_camera = Eigen::Isometry3d::Identity();
    try {
      // Only derive an allowance from the two already limit/collision-checked
      // plans. Fixed 30mm remains the finite extra correction allowance.
      const auto camera_from_tool = tf_buffer_->lookupTransform(
        end_effector_link_, camera_optical_frame_, tf2::TimePointZero);
      tf2::Transform camera_tf;
      tf2::fromMsg(camera_from_tool.transform, camera_tf);
      for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
          tool_to_camera.linear()(row, col) = camera_tf.getBasis()[row][col];
        }
        tool_to_camera.translation()[row] = camera_tf.getOrigin()[row];
      }
      moveit::core::RobotState state(*start);
      const Eigen::Vector3d local_tip(0, 0, gripper_tip_offset_m_);
      auto previous = state.getGlobalLinkTransform(end_effector_link_);
      for (const auto * plan : {&pre_plan, &descent_plan}) {
        const auto & jt = plan->joint_trajectory;
        if (jt.points.empty()) {throw std::invalid_argument("Empty checked plan");}
        for (const auto & point : jt.points) {
          for (std::size_t i = 0; i < jt.joint_names.size(); ++i) {
            state.setVariablePosition(jt.joint_names[i], point.positions.at(i));
          }
          state.update();
          const Eigen::Isometry3d current = state.getGlobalLinkTransform(end_effector_link_);
          camera_arc += ((current * tool_to_camera).translation() -
            (previous * tool_to_camera).translation()).norm();
          tip_arc += (current * local_tip - previous * local_tip).norm();
          angle_arc += Eigen::Quaterniond(previous.rotation()).angularDistance(
            Eigen::Quaterniond(current.rotation()));
          previous = current;
        }
        const auto & duration = jt.points.back().time_from_start;
        planned_seconds += duration.sec + duration.nanosec * 1e-9;
      }
    } catch (const std::exception & error) {
      RCLCPP_ERROR(get_logger(), "Cannot review automatic RGB path: %s", error.what());
      Fail("AUTOMATIC_RGB_PATH_REVIEW_FAILED"); return;
    }
    const double extra = near_depth_prediction_max_travel_m_;
    const double iterations = waypoints.size() + std::ceil((tip_arc + extra) /
      approach_microstep_m_) + std::ceil(angle_arc / angle_limit) + 2;
    const double age = planned_seconds + iterations *
      (planning_time_s_ + trajectory_feedback_timeout_s_ + target_timeout_s_ + .5);
    if (!std::isfinite(iterations) || !std::isfinite(age) || !std::isfinite(camera_arc) ||
      iterations < 1 || camera_arc < 0 || age <= 0) {
      Fail("AUTOMATIC_RGB_PATH_BUDGET_INVALID"); return;
    }
    near_path_max_travel_m_ = near_camera_travel_m_ + camera_arc + extra;
    near_path_max_age_s_ = std::max(near_depth_prediction_max_age_s_, age +
      (now().nanoseconds() - near_seed_stamp_ns_) * 1e-9);
    near_path_allowance_ready_ = true;
    RCLCPP_INFO(get_logger(),
      "AUTOMATIC_RGB_CHECKED_PATH camera_arc=%.4f tip_arc=%.4f extra=%.4f max_steps=%.0f",
      camera_arc, tip_arc, extra, iterations);
    std::size_t cursor = 0;
    trajectory_msgs::msg::JointTrajectory last_trajectory;
    geometry_msgs::msg::PoseStamped last_goal;
    for (std::size_t step = 0; rclcpp::ok() && !cancel_requested_ &&
      step < static_cast<std::size_t>(iterations) && cursor < waypoints.size(); ++step)
    {
      if (!WaitApproachVisualBox()) {Fail("AUTOMATIC_RGB_FRESH_TARGET_UNAVAILABLE"); return;}
      const auto state = FreshMeasuredState("AUTOMATIC_RGB_APPROACH");
      Eigen::Vector3d correction;
      LockedRgbView view;
      if (!state || !LockedRgbCorrection(correction, &view)) {
        Fail("AUTOMATIC_RGB_LOCKED_OBSERVATION_UNAVAILABLE"); return;
      }
      const auto & fk = state->getGlobalLinkTransform(end_effector_link_);
      const Eigen::Quaterniond q(fk.rotation());
      const gg::DirectedPose current{{fk.translation().x(), fk.translation().y(), fk.translation().z()},
        {q.x(), q.y(), q.z(), q.w()}};
      const auto & pose = waypoints[cursor];
      gg::DirectedPose nominal{{pose.position.x, pose.position.y, pose.position.z},
        {pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w}};
      const double scale = correction.norm() > extra ? extra / correction.norm() : 1.;
      if (scale < 1) {
        RCLCPP_INFO(get_logger(), "RGB_CORRECTION_CLAMPED estimate=%.6f applied=%.6f "
          "REPLAN_FROM_ACTUAL_NEXT_FRAME", correction.norm(), extra);
      }
      const bool recovery = view.valid &&
        (view.recovering || !visual_grasp::FullView(view.box));
      if (recovery) {nominal = current;}  // Restore view, not blind forward motion.
      else {
        for (int i = 0; i < 3; ++i) {nominal.origin[i] += correction[i]*scale;}
      }
      const bool gaze = GuardApproachView(nominal, tool_to_camera, view);
      gg::DirectedPose goal;
      try {
        goal = visual_grasp::CorrectedPoseStep(current, nominal,
          {0, 0, 0}, gripper_tip_offset_m_,
          approach_microstep_m_, angle_limit, extra);
      } catch (const std::invalid_argument &) {
        Fail("AUTOMATIC_RGB_CORRECTION_INVALID"); return;
      }
      const auto current_tip = gg::Tip(current.origin, gg::Rotate(current.orientation, {0, 0, 1}),
        gripper_tip_offset_m_);
      auto expected_tip = gg::Tip(nominal.origin, gg::Rotate(nominal.orientation, {0, 0, 1}),
        gripper_tip_offset_m_);
      double gap_squared = 0;
      for (int i = 0; i < 3; ++i) {
        gap_squared += std::pow(expected_tip[i] - current_tip[i], 2);
      }
      if (std::sqrt(gap_squared) <= grasp_landing_tolerance_m_ &&
        gg::QuaternionDistance(current.orientation, nominal.orientation) <=
        grasp_landing_orientation_tolerance_rad_) {
        if (!recovery) {++cursor;}
        else {near_last_command_image_stamp_ns_ = view.stamp_ns;}
        continue;
      }
      last_goal.header.frame_id = lift_reference_frame_; last_goal.header.stamp = now();
      last_goal.pose.position.x = goal.origin[0]; last_goal.pose.position.y = goal.origin[1];
      last_goal.pose.position.z = goal.origin[2]; last_goal.pose.orientation.x = goal.orientation[0];
      last_goal.pose.orientation.y = goal.orientation[1]; last_goal.pose.orientation.z = goal.orientation[2];
      last_goal.pose.orientation.w = goal.orientation[3];
      PublishState(cursor < pre_waypoints.size() ?
        "AUTOMATIC_RGB_PREGRASP" : "AUTOMATIC_RGB_DESCENT");
      RCLCPP_INFO(get_logger(), "AUTOMATIC_RGB_STEP=%zu waypoint=%zu/%zu correction=%.4f "
        "LOCKED_RANGE_ESTIMATE_NOT_NEW_DEPTH", step, cursor, waypoints.size(), correction.norm());
      RCLCPP_INFO(get_logger(), "RGB_VIEW image_stamp=%ld box=(%.3f,%.3f,%.3f,%.3f) "
        "gaze=%s recovery=%s", view.stamp_ns, view.box.left, view.box.top,
        view.box.right, view.box.bottom, gaze ? "true" : "false", recovery ? "true" : "false");
      near_last_command_image_stamp_ns_ = view.valid ? view.stamp_ns : near_last_image_stamp_ns_;
      if (!ExecuteVisualPose(last_goal, state, "AUTOMATIC_RGB_STEP_" + std::to_string(step),
        approach_microstep_m_, angle_limit, &last_trajectory, &last_goal)) {
        Fail("AUTOMATIC_RGB_STEP_EXECUTION_FAILED"); return;
      }
    }
    if (cancel_requested_) {return;}
    if (cursor != waypoints.size() || last_trajectory.points.empty() ||
      !WaitFullVisualBox() || !FreshFaceInsideJaws() ||
      !EnsureRealTopDownLanding(last_goal, last_trajectory)) {
      Fail("AUTOMATIC_RGB_CAPTURE_UNCONFIRMED_NO_CLOSE"); return;
    }
    geometry_msgs::msg::PoseStamped retreat;
    retreat.header = last_goal.header; retreat.pose = pre_waypoints.back();
    PublishDiagnostic("AUTOMATIC_RGB_MODEL_CAPTURE_CONFIRMED");
    FinishGraspAndLift(retreat);
  }

  bool WaitCoarseDepthView(geometry_msgs::msg::PointStamped & reference, LockedRgbView & view)
  {
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration<double>(target_timeout_s_);
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      bool predicted = false;
      rclcpp::Time stamp(0, 0, get_clock()->get_clock_type());
      if (ObserveLockedTarget(reference, stamp, predicted, nullptr, nullptr, nullptr, &view, true) &&
        view.measured_rgbd && !predicted && !view.recovering &&
        view.stamp_ns > near_last_command_image_stamp_ns_) {return true;}
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return false;
  }

  bool CommitTerminalDepthLock(const geometry_msgs::msg::PointStamped & reference,
    const LockedRgbView & view)
  {
    if (!automatic_rgb_approach_enabled_ || !coarse_depth_tracking_ || terminal_target_frozen_ ||
      !view.valid || !view.measured_rgbd || view.recovering ||
      !visual_grasp::FullView(view.box) || reference.header.frame_id != lift_reference_frame_ ||
      !std::isfinite(reference.point.x) || !std::isfinite(reference.point.y) ||
      !std::isfinite(reference.point.z) || view.stamp_ns <= 0 ||
      !std::isfinite(view.measured_color_range_m) || view.measured_color_range_m <= .001 ||
      view.measured_color_range_m > terminal_depth_lock_range_m_ + grasp_landing_tolerance_m_ ||
      !std::isfinite(view.measured_size_m) || !std::isfinite(view.measured_min_size_m) ||
      view.measured_size_m < min_object_size_m_ || view.measured_size_m > max_object_size_m_ ||
      view.measured_min_size_m < min_object_size_m_) {return false;}
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      locked_target_reference_ = reference;
      locked_target_reference_.header.stamp = rclcpp::Time(view.stamp_ns);
      locked_object_size_m_ = view.measured_size_m;
      locked_object_min_size_m_ = view.measured_min_size_m;
    }
    // Exactly one deliberate late-stage refresh. Later measurements cannot
    // replenish this seed or replace the target, even when depth is available.
    near_seed_ = {view.box, view.measured_color_range_m, true};
    near_seed_stamp_ns_ = near_seed_image_stamp_ns_ = view.stamp_ns;
    near_last_image_stamp_ns_ = near_last_command_image_stamp_ns_ = view.stamp_ns;
    near_camera_travel_m_ = 0;
    near_path_allowance_ready_ = false;
    near_rgb_association_bad_frames_seen_ = 0;
    near_last_bad_association_stamp_ns_ = 0;
    coarse_depth_tracking_ = false;
    terminal_target_frozen_ = true;
    PublishDiagnostic("TERMINAL_RGBD_TARGET_FROZEN_RGB_CORRECTION_ONLY");
    RCLCPP_INFO(get_logger(),
      "TERMINAL_RGBD_TARGET_FROZEN image_stamp=%ld range=%.6f "
      "base=(%.9f,%.9f,%.9f) size=%.6f NO_LATER_DEPTH_RELOCK",
      view.stamp_ns, view.measured_color_range_m, reference.point.x, reference.point.y,
      reference.point.z, view.measured_size_m);
    return true;
  }

  bool RemeasureTerminalTarget()
  {
    PublishState("TERMINAL_DEPTH_REMEASURE_HOLDING");
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(2500);
    std::vector<geometry_msgs::msg::PointStamped> points;
    std::vector<LockedRgbView> views;
    std::shared_ptr<moveit::core::RobotState> previous_state;
    auto after_stamp = now().nanoseconds();  // Only post-hold observations.
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      geometry_msgs::msg::PointStamped point;
      LockedRgbView view;
      if (!WaitCoarseDepthView(point, view)) {continue;}
      if (view.stamp_ns <= after_stamp ||
        view.measured_color_range_m > terminal_depth_lock_range_m_ + grasp_landing_tolerance_m_)
      {continue;}
      after_stamp = view.stamp_ns;
      const auto measured = FreshMeasuredState("TERMINAL_DEPTH_REMEASURE");
      if (!measured) {return false;}
      bool stationary = true;
      if (previous_state) {
        for (int axis = 1; axis <= 6; ++axis) {
          const auto name = "joint" + std::to_string(axis);
          stationary &= std::abs(measured->getVariablePosition(name) -
            previous_state->getVariablePosition(name)) <= .002;
        }
      }
      previous_state = measured;
      if (!points.empty()) {
        stationary &= std::hypot(std::hypot(point.point.x-points.back().point.x,
          point.point.y-points.back().point.y), point.point.z-points.back().point.z) <=
          visual_target_association_m_;
      }
      if (!stationary) {points.clear(); views.clear();}
      points.push_back(point); views.push_back(view);
      if (points.size() < 3) {continue;}
      const auto median = [](double a, double b, double c) {
          std::array<double, 3> values{a, b, c}; std::sort(values.begin(), values.end());
          return values[1];
        };
      auto reference = points.back();
      reference.point.x = median(points[0].point.x, points[1].point.x, points[2].point.x);
      reference.point.y = median(points[0].point.y, points[1].point.y, points[2].point.y);
      reference.point.z = median(points[0].point.z, points[1].point.z, points[2].point.z);
      view.measured_color_range_m = median(views[0].measured_color_range_m,
        views[1].measured_color_range_m, views[2].measured_color_range_m);
      view.measured_size_m = median(views[0].measured_size_m,
        views[1].measured_size_m, views[2].measured_size_m);
      view.measured_min_size_m = median(views[0].measured_min_size_m,
        views[1].measured_min_size_m, views[2].measured_min_size_m);
      return CommitTerminalDepthLock(reference, view);
    }
    PublishDiagnostic("TERMINAL_DEPTH_REMEASURE_UNAVAILABLE_NO_CLOSE");
    return false;
  }

  bool DepthApproachAndFreezeTerminal()
  {
    if (!std::isfinite(terminal_depth_lock_range_m_) || terminal_depth_lock_range_m_ <= .15 ||
      !near_depth_tracking_active_ || !near_seed_.valid) {return false;}
    coarse_depth_tracking_ = true;
    struct CoarseScope {bool & active; ~CoarseScope() {active = false;}} scope{coarse_depth_tracking_};
    PublishState("DEPTH_GUIDED_COARSE_APPROACH");
    geometry_msgs::msg::PointStamped reference;
    LockedRgbView view;
    if (!WaitCoarseDepthView(reference, view)) {return false;}
    const double initial_gap = std::max(0.0, view.measured_color_range_m-terminal_depth_lock_range_m_);
    const auto max_steps = static_cast<std::size_t>(32 + 8*std::ceil(initial_gap/approach_microstep_m_));
    const auto mount = tf_buffer_->lookupTransform(end_effector_link_, camera_optical_frame_, tf2::TimePointZero);
    tf2::Transform mount_tf; tf2::fromMsg(mount.transform, mount_tf);
    Eigen::Isometry3d tool_to_camera = Eigen::Isometry3d::Identity();
    for (int row = 0; row < 3; ++row) {
      for (int col = 0; col < 3; ++col) {tool_to_camera.linear()(row, col) = mount_tf.getBasis()[row][col];}
      tool_to_camera.translation()[row] = mount_tf.getOrigin()[row];
    }
    for (std::size_t step = 0; rclcpp::ok() && !cancel_requested_ && step < max_steps; ++step) {
      if (step != 0 && !WaitCoarseDepthView(reference, view)) {return false;}
      RCLCPP_INFO(get_logger(), "COARSE_DEPTH_STEP=%zu measured_color_range=%.6f target_range=%.3f",
        step, view.measured_color_range_m, terminal_depth_lock_range_m_);
      if (view.measured_color_range_m <= terminal_depth_lock_range_m_ + grasp_landing_tolerance_m_) {
        return RemeasureTerminalTarget();
      }
      const auto state = FreshMeasuredState("COARSE_DEPTH_APPROACH");
      if (!state) {return false;}
      const auto & fk = state->getGlobalLinkTransform(end_effector_link_);
      const Eigen::Quaterniond q(fk.rotation());
      const grasp_geometry::DirectedPose current{{fk.translation().x(), fk.translation().y(), fk.translation().z()},
        {q.x(), q.y(), q.z(), q.w()}};
      auto nominal = current;
      const auto ray = Eigen::Vector3d(reference.point.x, reference.point.y, reference.point.z) -
        (fk * tool_to_camera).translation();
      if (!ray.allFinite() || ray.norm() <= .001) {return false;}
      // Move along the measured ray, not a long-range guessed grasp landing.
      const auto shift = ray.normalized() * std::max(0.0, ray.norm()-terminal_depth_lock_range_m_);
      for (int i = 0; i < 3; ++i) {nominal.origin[i] += shift[i];}
      GuardApproachView(nominal, tool_to_camera, view);
      const auto step_pose = visual_grasp::CorrectedPoseStep(current, nominal, {0, 0, 0},
        gripper_tip_offset_m_, approach_microstep_m_, .01745329252, near_depth_prediction_max_travel_m_);
      geometry_msgs::msg::PoseStamped target;
      target.header.frame_id = lift_reference_frame_; target.header.stamp = now();
      target.pose.position.x = step_pose.origin[0]; target.pose.position.y = step_pose.origin[1];
      target.pose.position.z = step_pose.origin[2];
      target.pose.orientation.x = step_pose.orientation[0]; target.pose.orientation.y = step_pose.orientation[1];
      target.pose.orientation.z = step_pose.orientation[2]; target.pose.orientation.w = step_pose.orientation[3];
      trajectory_msgs::msg::JointTrajectory completed;
      near_last_command_image_stamp_ns_ = view.stamp_ns;
      // Freeze this step's measured point during planning/output monitoring.
      // RGB and depth callbacks are asynchronous; depth is required for the
      // NEXT step, not for every tick of a trajectory already being executed.
      coarse_motion_in_progress_ = true;
      struct MotionScope {bool & active; ~MotionScope() {active = false;}}
        motion_scope{coarse_motion_in_progress_};
      if (!ExecuteVisualPose(target, state, "AUTOMATIC_RGB_STEP_COARSE_"+std::to_string(step),
          approach_microstep_m_, .01745329252, &completed)) {return false;}
    }
    return false;
  }

  void TargetDirectedPointGraspAndLift()
  {
    if (!simulation_only_ && automatic_rgb_approach_enabled_ && terminal_depth_stage_enabled_ &&
      !terminal_target_frozen_) {
      bool frozen = false;
      try {frozen = DepthApproachAndFreezeTerminal();}
      catch (const std::exception & error) {
        RCLCPP_ERROR(get_logger(), "Terminal depth stage failed: %s", error.what());
      }
      if (!frozen) {Fail("TERMINAL_DEPTH_STAGE_FAILED"); return;}
    }
    PublishState("TARGET_DIRECTED_PREGRASP_PLANNING");
    if (!static_target_lock_ || !target_model_locked_) {
      Fail("TARGET_DIRECTED_STATIC_MODEL_UNAVAILABLE");
      return;
    }
    geometry_msgs::msg::PointStamped surface;
    const auto state = FreshMeasuredState("TARGET_DIRECTED_START");
    if (!state || !PredictedTargetInReference(surface)) {
      Fail("TARGET_DIRECTED_START_UNAVAILABLE");
      return;
    }
    const auto start = CurrentPoseInFrame(lift_reference_frame_);
    if (start.header.frame_id.empty()) {
      Fail("TARGET_DIRECTED_START_POSE_UNAVAILABLE");
      return;
    }
    std::vector<geometry_msgs::msg::Pose> pre_waypoints;
    std::vector<geometry_msgs::msg::Pose> descent_waypoints;
    try {
      const double insertion = grasp_geometry::SurfaceInsertion(
        locked_object_min_size_m_, surface_insertion_fraction_, surface_insertion_max_m_);
      const bool synchronized_turn = !simulation_only_ && automatic_rgb_approach_enabled_ &&
        terminal_target_frozen_;
      const auto path = grasp_geometry::TargetDirectedApproach(
        {start.pose.position.x, start.pose.position.y, start.pose.position.z},
        {start.pose.orientation.x, start.pose.orientation.y, start.pose.orientation.z,
          start.pose.orientation.w},
        {surface.point.x, surface.point.y, surface.point.z}, gripper_tip_offset_m_,
        top_down_pregrasp_clearance_m_ + grasp_height_offset_m_,
        insertion - grasp_height_offset_m_, cartesian_eef_step_m_,
        target_directed_downward_fraction_, synchronized_turn);
      const auto convert = [](const auto & poses, auto & waypoints) {
          for (const auto & p : poses) {
            geometry_msgs::msg::Pose pose;
            pose.position.x = p.origin[0];
            pose.position.y = p.origin[1];
            pose.position.z = p.origin[2];
            pose.orientation.x = p.orientation[0];
            pose.orientation.y = p.orientation[1];
            pose.orientation.z = p.orientation[2];
            pose.orientation.w = p.orientation[3];
            waypoints.push_back(pose);
          }
        };
      convert(path.pregrasp, pre_waypoints);
      convert(path.descent, descent_waypoints);
      RCLCPP_INFO(get_logger(),
        "TARGET_DIRECTED_VARIABLE_ATTITUDE surface=(%.4f,%.4f,%.4f) insertion=%.4f "
        "pre_waypoints=%zu descent_waypoints=%zu downward_fraction=%.3f synchronized_turn=%d "
        "NO_JOINT_TRAJECTORY_EDIT",
        surface.point.x, surface.point.y, surface.point.z, insertion,
        pre_waypoints.size(), descent_waypoints.size(), target_directed_downward_fraction_,
        synchronized_turn);
    } catch (const std::invalid_argument & error) {
      RCLCPP_ERROR(get_logger(), "Target-directed geometry rejected: %s", error.what());
      Fail("TARGET_DIRECTED_GEOMETRY_UNAVAILABLE");
      return;
    }
    moveit_msgs::msg::RobotTrajectory pre_plan;
    moveit_msgs::msg::RobotTrajectory descent_plan;
    if (!PlanArmCartesianWaypointsFromState(
        pre_waypoints, lift_reference_frame_, "TARGET_DIRECTED_PREGRASP", state, pre_plan))
    {
      Fail("TARGET_DIRECTED_PREGRASP_PLAN_FAILED");
      return;
    }
    const auto predicted_pre = StateAtTrajectoryEnd(
      pre_plan.joint_trajectory, "TARGET_DIRECTED_DESCENT_START");
    if (!PlanArmCartesianWaypointsFromState(
        descent_waypoints, lift_reference_frame_, "TARGET_DIRECTED_DESCENT",
        predicted_pre, descent_plan))
    {
      Fail("TARGET_DIRECTED_DESCENT_PLAN_FAILED");
      return;
    }
    std::string rejection;
    if (!simulation_only_ &&
      (!RealTrajectoryWithinLimits(pre_plan.joint_trajectory, rejection) ||
      !RealTrajectoryWithinLimits(descent_plan.joint_trajectory, rejection)))
    {
      PublishDiagnostic("TARGET_DIRECTED_REAL_LIMIT_REJECTED:" + rejection);
      Fail("TARGET_DIRECTED_REAL_LIMIT_REJECTED");
      return;
    }
    // Keep the original full-path preflight. Approved visual execution uses new
    // measured states and short Cartesian pose goals, never edits those joint points.
    if (!simulation_only_ && visual_microsteps_enabled_) {
      VisualMicrostepPreview();
      return;
    }
    if (!simulation_only_ && automatic_rgb_approach_enabled_) {
      AutomaticRgbApproach(pre_waypoints, descent_waypoints, pre_plan, descent_plan, state);
      return;
    }
    // Both changing-attitude segments must be planned before any adapter output.
    const auto execute = [this](const auto & plan) {
        return simulation_only_ ? static_cast<bool>(arm_->execute(plan)) :
               ExecuteArmTrajectory(plan.joint_trajectory);
      };
    if (!execute(pre_plan) || cancel_requested_) {
      Fail("TARGET_DIRECTED_PREGRASP_EXECUTION_FAILED");
      return;
    }
    PublishState("TOP_DOWN_PREGRASP_REACHED");
    PublishState("TOP_DOWN_DESCENT_EXECUTING");
    if (!execute(descent_plan) || cancel_requested_) {
      Fail("TARGET_DIRECTED_DESCENT_EXECUTION_FAILED");
      return;
    }
    geometry_msgs::msg::PoseStamped final_target;
    final_target.header.frame_id = lift_reference_frame_;
    final_target.header.stamp = now();
    final_target.pose = descent_waypoints.back();
    target_pose_publisher_->publish(final_target);
    if (!simulation_only_ && !EnsureRealTopDownLanding(
        final_target, descent_plan.joint_trajectory)) {
      Fail("GRASP_LANDING_UNCONFIRMED_NO_CLOSE");
      return;
    }
    geometry_msgs::msg::PoseStamped retreat;
    retreat.header = final_target.header;
    retreat.pose = pre_waypoints.back();
    FinishGraspAndLift(retreat);
  }

  void TopDownPointGraspAndLift()
  {
    selected_top_down_yaw_valid_ = false;
    locked_approach_orientation_valid_ = false;
    if (target_directed_grasp_enabled_) {
      TargetDirectedPointGraspAndLift();
      return;
    }
    if (preserve_aligned_grasp_orientation_) {
      if (!static_target_lock_ || !target_model_locked_ ||
        !WaitForFreshJointState("ALIGNED_ORIENTATION_LOCK"))
      {
        Fail("ALIGNED_ORIENTATION_LOCK_UNAVAILABLE");
        return;
      }
      const auto measured_pose = CurrentPoseInFrame(lift_reference_frame_);
      tf2::Quaternion orientation;
      tf2::fromMsg(measured_pose.pose.orientation, orientation);
      if (measured_pose.header.frame_id.empty() || !std::isfinite(orientation.length2()) ||
        orientation.length2() < 1e-8)
      {
        Fail("ALIGNED_ORIENTATION_LOCK_INVALID");
        return;
      }
      orientation.normalize();
      if (aligned_grasp_pitch_down_rad_ > 0.0) {
        // Use the real model's positive J5 axis, not a guessed world pitch or
        // a change to trajectory joint5 values. MoveIt coordinates all axes.
        const auto state = FreshMeasuredState("ALIGNED_PITCH_DOWN");
        if (!state) {
          Fail("ALIGNED_ORIENTATION_LOCK_UNAVAILABLE");
          return;
        }
        const auto * joint = state->getRobotModel()->getJointModel("joint5");
        if (!joint || joint->getType() != moveit::core::JointModel::REVOLUTE) {
          Fail("ALIGNED_ORIENTATION_LOCK_INVALID");
          return;
        }
        const auto * revolute = static_cast<const moveit::core::RevoluteJointModel *>(joint);
        const Eigen::Vector3d model_axis =
          state->getGlobalLinkTransform(joint->getChildLinkModel()).rotation() *
          revolute->getAxis();
        tf2::Vector3 axis(model_axis.x(), model_axis.y(), model_axis.z());
        if (state->getRobotModel()->getModelFrame() != lift_reference_frame_) {
          try {
            const auto transform = tf_buffer_->lookupTransform(
              lift_reference_frame_, state->getRobotModel()->getModelFrame(), tf2::TimePointZero);
            tf2::Quaternion rotation;
            tf2::fromMsg(transform.transform.rotation, rotation);
            axis = tf2::quatRotate(rotation, axis);
          } catch (const tf2::TransformException & error) {
            RCLCPP_ERROR(get_logger(), "Pitch-down axis frame conversion failed: %s", error.what());
            Fail("ALIGNED_ORIENTATION_LOCK_UNAVAILABLE");
            return;
          }
        }
        const auto adjusted = grasp_geometry::RotateOrientationAboutAxis(
          {orientation.x(), orientation.y(), orientation.z(), orientation.w()},
          {axis.x(), axis.y(), axis.z()}, aligned_grasp_pitch_down_rad_);
        orientation = tf2::Quaternion(adjusted[0], adjusted[1], adjusted[2], adjusted[3]);
        RCLCPP_INFO(get_logger(),
          "ALIGNED_GRASP_PITCH_DOWN radians=%.6f positive_J5_axis=(%.6f,%.6f,%.6f) "
          "POSE_GOAL_ONLY_NO_JOINT_TRAJECTORY_EDIT",
          aligned_grasp_pitch_down_rad_, axis.x(), axis.y(), axis.z());
      }
      locked_approach_orientation_ = tf2::toMsg(orientation);
      locked_approach_orientation_valid_ = true;
      PublishDiagnostic("ALIGNED_ORIENTATION_LOCKED_FIXED_APPROACH");
      RCLCPP_INFO(get_logger(),
        "Aligned approach orientation locked q=(%.6f,%.6f,%.6f,%.6f); "
        "reuse pregrasp/descent planning, do not enumerate preset wrist angles.",
        orientation.x(), orientation.y(), orientation.z(), orientation.w());
    }
    PublishState("TOP_DOWN_PREGRASP_PLANNING");
    geometry_msgs::msg::PoseStamped pregrasp_target;
    MoveGroupInterface::Plan pregrasp_plan;
    moveit_msgs::msg::RobotTrajectory descent_plan;
    geometry_msgs::msg::PoseStamped final_grasp_target;
    bool pregrasp_plan_found = false;
    const auto tilts = locked_approach_orientation_valid_ ?
      std::vector<double>{0.0} : top_down_tilt_candidates_;
    const auto yaws = locked_approach_orientation_valid_ ?
      std::vector<double>{0.0} : top_down_yaw_candidates_;
    for (const double clearance : top_down_pregrasp_clearance_candidates_m_) {
      for (const double tilt : tilts) {
        for (const double yaw : yaws) {
        selected_top_down_tilt_ = tilt;
        selected_top_down_yaw_ = yaw;
        selected_top_down_yaw_valid_ = true;
        if (!BuildTopDownPointGrasp(clearance, pregrasp_target) ||
          !TopDownPoseHasIk(pregrasp_target))
        {
          continue;
        }
        MoveGroupInterface::Plan candidate_plan;
        const std::string candidate_stage =
          "TOP_DOWN_PREGRASP_CLEARANCE_" + std::to_string(clearance) +
          "_TILT_" + std::to_string(tilt) +
          "_YAW_" + std::to_string(yaw);
        if (!PlanArmToPose(pregrasp_target, candidate_stage, candidate_plan)) {
          continue;
        }
        std::string rejection;
        if (!simulation_only_ && !RealTrajectoryWithinLimits(
            candidate_plan.trajectory_.joint_trajectory, rejection))
        {
          PublishDiagnostic(candidate_stage + ":REAL_LIMIT_REJECTED:" + rejection);
          RCLCPP_WARN(
            get_logger(), "%s rejected before adapter output: %s.",
            candidate_stage.c_str(), rejection.c_str());
          continue;
        }
        geometry_msgs::msg::PoseStamped candidate_grasp_target;
        if (!BuildTopDownPointGrasp(top_down_grasp_clearance_m_, candidate_grasp_target, true)) {
          continue;
        }
        auto predicted_pregrasp_state = StateAtTrajectoryEnd(
          candidate_plan.trajectory_.joint_trajectory, candidate_stage + "_DESCENT_START");
        if (!predicted_pregrasp_state) {
          continue;
        }
        moveit_msgs::msg::RobotTrajectory candidate_descent_plan;
        const std::string descent_stage = candidate_stage + "_DESCENT";
        if (!PlanArmCartesianFromState(
            candidate_grasp_target, descent_stage, predicted_pregrasp_state,
            candidate_descent_plan))
        {
          continue;
        }
        if (!simulation_only_ && !RealTrajectoryWithinLimits(
            candidate_descent_plan.joint_trajectory, rejection))
        {
          PublishDiagnostic(descent_stage + ":REAL_LIMIT_REJECTED:" + rejection);
          RCLCPP_WARN(
            get_logger(), "%s rejected before adapter output: %s.",
            descent_stage.c_str(), rejection.c_str());
          continue;
        }
        pregrasp_plan = std::move(candidate_plan);
        descent_plan = std::move(candidate_descent_plan);
        final_grasp_target = candidate_grasp_target;
        pregrasp_plan_found = true;
        break;
      }
      if (pregrasp_plan_found) {
        break;
      }
    }
    if (pregrasp_plan_found) {
      break;
    }
  }
    if (!pregrasp_plan_found || cancel_requested_) {
      Fail("TOP_DOWN_PREGRASP_PLAN_FAILED");
      return;
    }
    const bool pregrasp_executed = simulation_only_ ?
      static_cast<bool>(arm_->execute(pregrasp_plan)) :
      ExecuteArmTrajectory(pregrasp_plan.trajectory_.joint_trajectory);
    if (!pregrasp_executed || cancel_requested_) {
      Fail("TOP_DOWN_PREGRASP_EXECUTION_FAILED");
      return;
    }
    PublishDiagnostic("TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED");
    PublishState("TOP_DOWN_PREGRASP_REACHED");

    PublishState("TOP_DOWN_DESCENT_EXECUTING");
    const bool descent_executed = simulation_only_ ?
      static_cast<bool>(arm_->execute(descent_plan)) :
      ExecuteArmTrajectory(descent_plan.joint_trajectory);
    if (!descent_executed || cancel_requested_) {
      Fail("TOP_DOWN_DESCENT_FAILED");
      return;
    }
    PublishDiagnostic("TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED");
    // Joint endpoints are not proof that the fingertips reached the intended
    // grasp region. Check FK from fresh measured joints, with one bounded
    // fixed-pose Cartesian correction, before issuing any close command.
    if (!simulation_only_ && !EnsureRealTopDownLanding(
        final_grasp_target, descent_plan.joint_trajectory)) {
      Fail("GRASP_LANDING_UNCONFIRMED_NO_CLOSE");
      return;
    }
    FinishGraspAndLift(pregrasp_target);
  }

  bool WaitForStrictLandingFeedback(const trajectory_msgs::msg::JointTrajectory & trajectory)
  {
    if (trajectory.joint_names.empty() || trajectory.points.empty()) {
      PublishDiagnostic("GRASP_LANDING_STRICT_FEEDBACK_TRAJECTORY_INVALID");
      return false;
    }
    const auto & endpoint = trajectory.points.back();
    if (endpoint.positions.size() != trajectory.joint_names.size()) {
      PublishDiagnostic("GRASP_LANDING_STRICT_FEEDBACK_ENDPOINT_INVALID");
      return false;
    }
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(grasp_landing_feedback_timeout_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      const auto state = FreshMeasuredState("GRASP_LANDING_STRICT_FEEDBACK");
      bool reached = static_cast<bool>(state);
      if (reached) {
        for (std::size_t index = 0; index < trajectory.joint_names.size(); ++index) {
          const auto * joint = state->getRobotModel()->getJointModel(
            trajectory.joint_names[index]);
          if (!joint || !std::isfinite(endpoint.positions[index])) {
            reached = false;
            break;
          }
          reached = reached && std::abs(
            state->getVariablePosition(trajectory.joint_names[index]) - endpoint.positions[index]) <=
            grasp_landing_feedback_tolerance_rad_;
        }
      }
      if (reached) {
        PublishDiagnostic("GRASP_LANDING_STRICT_FEEDBACK_CONFIRMED");
        return true;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    PublishDiagnostic("GRASP_LANDING_STRICT_FEEDBACK_TIMEOUT");
    return false;
  }

  bool EnsureRealTopDownLanding(
    const geometry_msgs::msg::PoseStamped & expected,
    const trajectory_msgs::msg::JointTrajectory & descent_trajectory)
  {
    if (expected.header.frame_id.empty() || !arm_) {
      return false;
    }
    if (!WaitForStrictLandingFeedback(descent_trajectory)) {
      return false;
    }
    tf2::Transform expected_transform;
    tf2::fromMsg(expected.pose, expected_transform);
    const auto expected_axis = tf2::quatRotate(
      expected_transform.getRotation(), tf2::Vector3(0.0, 0.0, 1.0));
    const auto expected_tip = expected_transform * tf2::Vector3(0.0, 0.0, gripper_tip_offset_m_);
    for (int attempt = 0; attempt < 2 && !cancel_requested_; ++attempt) {
      const auto state = FreshMeasuredState("GRASP_LANDING");
      if (!state) {
        PublishDiagnostic("GRASP_LANDING_MEASURED_STATE_UNAVAILABLE");
        return false;
      }
      const auto & fk = state->getGlobalLinkTransform(end_effector_link_);
      const Eigen::Quaterniond rotation(fk.rotation());
      geometry_msgs::msg::PoseStamped measured;
      measured.header.frame_id = arm_->getRobotModel()->getModelFrame();
      measured.header.stamp = now();
      measured.pose.position.x = fk.translation().x();
      measured.pose.position.y = fk.translation().y();
      measured.pose.position.z = fk.translation().z();
      measured.pose.orientation.x = rotation.x();
      measured.pose.orientation.y = rotation.y();
      measured.pose.orientation.z = rotation.z();
      measured.pose.orientation.w = rotation.w();
      if (measured.header.frame_id != expected.header.frame_id) {
        try {
          const auto transform = tf_buffer_->lookupTransform(
            expected.header.frame_id, measured.header.frame_id, tf2::TimePointZero);
          geometry_msgs::msg::PoseStamped transformed;
          tf2::doTransform(measured, transformed, transform);
          measured = transformed;
        } catch (const tf2::TransformException & error) {
          RCLCPP_ERROR(get_logger(), "Grasp landing frame conversion failed: %s", error.what());
          return false;
        }
      }
      tf2::Transform actual;
      tf2::fromMsg(measured.pose, actual);
      const auto actual_tip = actual * tf2::Vector3(0.0, 0.0, gripper_tip_offset_m_);
      const auto error = grasp_geometry::CompareTips(
        {actual_tip.x(), actual_tip.y(), actual_tip.z()},
        {expected_tip.x(), expected_tip.y(), expected_tip.z()},
        {expected_axis.x(), expected_axis.y(), expected_axis.z()});
      const double angle = actual.getRotation().angleShortestPath(expected_transform.getRotation());
      RCLCPP_INFO(
        get_logger(),
        "GRASP_LANDING frame=%s expected_tip=(%.4f,%.4f,%.4f) actual_tip=(%.4f,%.4f,%.4f) "
        "distance=%.4f axial=%.4f lateral=%.4f angle=%.4f attempt=%d.",
        expected.header.frame_id.c_str(), expected_tip.x(), expected_tip.y(), expected_tip.z(),
        actual_tip.x(), actual_tip.y(), actual_tip.z(), error.distance_m, error.axial_m,
        error.lateral_m, angle, attempt);
      const auto decision = grasp_geometry::DecideLanding(
        error, angle,
        {grasp_landing_tolerance_m_, grasp_landing_orientation_tolerance_rad_,
          grasp_landing_max_correction_m_, orientation_tolerance_}, attempt != 0);
      if (decision == grasp_geometry::LandingDecision::ACCEPT) {
        PublishDiagnostic("GRASP_LANDING_FK_CONFIRMED_NOT_EXTERNAL_TCP_CALIBRATION");
        return true;
      }
      if (decision == grasp_geometry::LandingDecision::REJECT) {
        PublishDiagnostic("GRASP_LANDING_TOO_FAR_OR_UNCONFIRMED_NO_CLOSE");
        return false;
      }
      PublishState("GRASP_LANDING_SINGLE_CORRECTION");
      // Same base-frame model, same tilt/yaw: never re-enter pixel ALIGN here.
      if (!MoveArmCartesianToPose(expected, "GRASP_LANDING_CORRECTION")) {
        return false;
      }
    }
    return false;
  }

  void FinishGraspAndLift(
    const geometry_msgs::msg::PoseStamped & postgrasp_retreat = geometry_msgs::msg::PoseStamped())
  {
    if (!simulation_only_ && fresh_jaw_capture_required_ && !FreshFaceInsideJaws()) {
      Fail("FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE");
      return;
    }
    near_depth_tracking_active_ = false;  // Tabletop association ends before closing/lifting.
    geometry_msgs::msg::PoseStamped grasp_pose;
    grasp_pose = CurrentPoseInFrame(lift_reference_frame_);
    if (grasp_pose.header.frame_id.empty()) {
      Fail("GRASP_POSE_UNAVAILABLE");
      return;
    }
    const double gripper_before_close = LatestGripperPosition();
    PublishState("CLOSING_GRIPPER");
    PublishDiagnostic("GRIPPER_CLOSE_REQUESTED");
    if (!CommandRealGripper(false) || cancel_requested_) {
      Fail("CLOSE_GRIPPER_FAILED");
      return;
    }
    if (!simulation_only_) {
      std::this_thread::sleep_for(std::chrono::duration<double>(gripper_settle_s_));
      if (!WaitForGripperCommand(
          gripper_before_close, gripper_close_value_, true, "GRIPPER_CLOSE"))
      {
        Fail("GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED");
        return;
      }
      // PiPER exposes position feedback, not a contact/force measurement. This
      // confirms jaw actuation before lifting; object retention remains an
      // entity-level result to validate on the real cube.
      PublishDiagnostic("GRIPPER_CLOSE_FEEDBACK_CONFIRMED_NO_FORCE_SENSOR");

      PublishState("LIFTING");
      auto lift_target = postgrasp_retreat;
      std::string lift_stage = "POSTGRASP_RETREAT";
      if (lift_target.header.frame_id.empty()) {
        lift_target = grasp_pose;
        lift_target.pose.position.z += lift_distance_m_;
        lift_stage = "LIFT";
      } else {
        PublishDiagnostic("LIFT_USING_REVERSE_APPROACH");
      }
      lift_target.header.stamp = now();
      if (!MoveArmCartesianToPose(lift_target, lift_stage) || cancel_requested_) {
        Fail("LIFT_FAILED_HOLDING_CUBE");
        return;
      }
      PublishState("HOLDING");
      if (!auto_release_after_lift_) {
        return;
      }
      if (hold_after_lift_s_ > 0.0) {
        std::this_thread::sleep_for(std::chrono::duration<double>(hold_after_lift_s_));
      }

      // Return along the already traversed post-grasp retreat path and release at the
      // measured grasp pose. This avoids inventing an uncalibrated transfer
      // location, then retreats to the collision-checked retreat pose.
      PublishState("RELEASE_LOWERING");
      grasp_pose.header.stamp = now();
      if (!MoveArmCartesianToPose(grasp_pose, "RELEASE_LOWER") || cancel_requested_) {
        Fail("RELEASE_LOWER_FAILED_HOLDING_CUBE");
        return;
      }
      const double gripper_before_open = LatestGripperPosition();
      PublishState("RELEASING");
      if (!CommandRealGripper(true) || cancel_requested_) {
        Fail("RELEASE_GRIPPER_OPEN_FAILED");
        return;
      }
      std::this_thread::sleep_for(std::chrono::duration<double>(gripper_settle_s_));
      if (!WaitForGripperCommand(
          gripper_before_open, gripper_open_value_, false, "GRIPPER_RELEASE_OPEN"))
      {
        Fail("RELEASE_GRIPPER_FEEDBACK_UNCONFIRMED");
        return;
      }
      PublishState("RELEASED");
      PublishState("RELEASE_RETREATING");
      lift_target.header.stamp = now();
      if (!MoveArmCartesianToPose(lift_target, "RELEASE_RETREAT") || cancel_requested_) {
        Fail("RELEASE_RETREAT_FAILED");
        return;
      }
      PublishState("RELEASE_COMPLETE_HOLDING_SAFE_RETREAT");
      return;
    }
    PublishState("VERIFYING_GRASP_CONTACT");
    if (!VerifyGraspContact()) {
      Fail("GRASP_MISSED");
      return;
    }
    if (!AttachCup()) {
      Fail("ATTACH_CUP_FAILED");
      return;
    }
    if (!SetCupFollowing(true)) {
      Fail("GAZEBO_CUP_FOLLOW_FAILED");
      return;
    }

    PublishState("LIFTING");
    auto lift_target = postgrasp_retreat;
    std::string lift_stage = "POSTGRASP_RETREAT";
    if (lift_target.header.frame_id.empty()) {
      lift_target = CurrentPoseInFrame(lift_reference_frame_);
      if (lift_target.header.frame_id.empty()) {
        Fail("CURRENT_POSE_UNAVAILABLE");
        return;
      }
      lift_target.pose.position.z += lift_distance_m_;
      lift_stage = "LIFT";
    } else {
      PublishDiagnostic("LIFT_USING_REVERSE_APPROACH");
    }
    lift_target.header.stamp = now();
    if (!MoveArmCartesianToPose(lift_target, lift_stage) || cancel_requested_) {
      Fail("LIFT_FAILED_HOLDING_CUP");
      return;
    }
    PublishState("HOLDING");
    if (!auto_release_after_lift_) {
      RCLCPP_INFO(get_logger(), "Cup post-grasp retreat completed and held.");
      return;
    }
    if (hold_after_lift_s_ > 0.0) {
      std::this_thread::sleep_for(std::chrono::duration<double>(hold_after_lift_s_));
    }

    PublishState("RELEASE_LOWERING");
    grasp_pose.header.stamp = now();
    if (!MoveArmCartesianToPose(grasp_pose, "RELEASE_LOWER") || cancel_requested_) {
      Fail("RELEASE_LOWER_FAILED_HOLDING_CUP");
      return;
    }
    PublishState("RELEASING");
    if (!SetCupFollowing(false)) {
      Fail("GAZEBO_CUP_UNFOLLOW_FAILED");
      return;
    }
    if (!MoveGripper(open_target_) || cancel_requested_) {
      Fail("RELEASE_GRIPPER_OPEN_FAILED");
      return;
    }
    PublishState("RELEASED");
    PublishState("RELEASE_RETREATING");
    lift_target.header.stamp = now();
    if (!MoveArmCartesianToPose(lift_target, "RELEASE_RETREAT") || cancel_requested_) {
      Fail("RELEASE_RETREAT_FAILED");
      return;
    }
    if (!DetachCupToWorld()) {
      Fail("DETACH_CUP_FAILED");
      return;
    }
    PublishSceneReady(false);
    PublishState("RELEASE_COMPLETE_HOLDING_SAFE_RETREAT");
    RCLCPP_INFO(get_logger(), "Cup release and safe retreat completed.");
  }

  bool VerifyGraspContact()
  {
    if (!grasp_contact_check_enabled_) {
      return true;
    }
    if (cached_cup_.primitive_poses.empty()) {
      PublishDiagnostic("GRASP_CONTACT_OBJECT_GEOMETRY_MISSING");
      return false;
    }
    const auto gripper_pose = CurrentPoseInFrame(lift_reference_frame_);
    if (gripper_pose.header.frame_id.empty()) {
      PublishDiagnostic("GRASP_CONTACT_GRIPPER_POSE_MISSING");
      return false;
    }
    try {
      geometry_msgs::msg::PoseStamped object_pose;
      object_pose.header = cached_cup_.header;
      object_pose.pose = cached_cup_.primitive_poses.front();
      if (cached_cup_.pose.position.x != 0.0 || cached_cup_.pose.position.y != 0.0 ||
        cached_cup_.pose.position.z != 0.0 || cached_cup_.pose.orientation.w != 1.0)
      {
        tf2::Transform object_transform;
        tf2::Transform primitive_transform;
        tf2::fromMsg(cached_cup_.pose, object_transform);
        tf2::fromMsg(cached_cup_.primitive_poses.front(), primitive_transform);
        const tf2::Transform combined_transform = object_transform * primitive_transform;
        const tf2::Vector3 origin = combined_transform.getOrigin();
        object_pose.pose.position.x = origin.x();
        object_pose.pose.position.y = origin.y();
        object_pose.pose.position.z = origin.z();
        const tf2::Quaternion rotation = combined_transform.getRotation();
        object_pose.pose.orientation.x = rotation.x();
        object_pose.pose.orientation.y = rotation.y();
        object_pose.pose.orientation.z = rotation.z();
        object_pose.pose.orientation.w = rotation.w();
      }
      if (object_pose.header.frame_id != lift_reference_frame_) {
        const auto transform = tf_buffer_->lookupTransform(
          lift_reference_frame_, object_pose.header.frame_id, tf2::TimePointZero);
        geometry_msgs::msg::PoseStamped transformed;
        tf2::doTransform(object_pose, transformed, transform);
        object_pose = transformed;
      }

      tf2::Transform gripper_transform;
      tf2::fromMsg(gripper_pose.pose, gripper_transform);
      const tf2::Vector3 grasp_center = gripper_transform *
        tf2::Vector3(0.0, 0.0, grasp_center_offset_m_);
      const tf2::Vector3 object_center(
        object_pose.pose.position.x, object_pose.pose.position.y, object_pose.pose.position.z);
      const double error_m = (object_center - grasp_center).length();
      current_pose_publisher_->publish(gripper_pose);
      PublishDiagnostic(
        "GRASP_CONTACT distance_m=" + std::to_string(error_m) +
        " tolerance_m=" + std::to_string(grasp_contact_tolerance_m_));
      if (error_m > grasp_contact_tolerance_m_) {
        RCLCPP_ERROR(
          get_logger(),
          "Grasp missed: object-to-jaw-center distance %.3f m exceeds %.3f m.",
          error_m, grasp_contact_tolerance_m_);
        return false;
      }
      RCLCPP_INFO(
        get_logger(), "Grasp contact accepted: object-to-jaw-center distance %.3f m.", error_m);
      return true;
    } catch (const tf2::TransformException & exception) {
      RCLCPP_ERROR(get_logger(), "Cannot verify grasp contact: %s", exception.what());
      PublishDiagnostic("GRASP_CONTACT_TF_FAILED");
      return false;
    }
  }

  bool BuildTopDownPointGrasp(
    double vertical_clearance_m, geometry_msgs::msg::PoseStamped & grasp_target,
    bool final_grasp = false)
  {
    geometry_msgs::msg::PointStamped object_world;
    if (!PredictedTargetInReference(object_world)) {
      RCLCPP_ERROR(get_logger(), "Locked top-down target is unavailable.");
      return false;
    }
    if (final_grasp && top_down_surface_grasp_enabled_) {
      try {
        vertical_clearance_m = -grasp_geometry::SurfaceInsertion(
          locked_object_min_size_m_, surface_insertion_fraction_, surface_insertion_max_m_);
      } catch (const std::invalid_argument & error) {
        RCLCPP_ERROR(get_logger(), "Surface grasp geometry unavailable: %s", error.what());
        return false;
      }
      RCLCPP_INFO(
        get_logger(), "SURFACE_GRASP edge=%.4f insertion=%.4f m (size-derived heuristic).",
        locked_object_min_size_m_, -vertical_clearance_m);
    }
    if (!selected_top_down_yaw_valid_) {
      for (const double tilt : top_down_tilt_candidates_) {
        for (const double yaw : top_down_yaw_candidates_) {
          PopulateTopDownPose(object_world, vertical_clearance_m, tilt, yaw, grasp_target);
          if (TopDownPoseHasIk(grasp_target)) {
            selected_top_down_yaw_ = yaw;
            selected_top_down_tilt_ = tilt;
            selected_top_down_yaw_valid_ = true;
            break;
          }
        }
        if (selected_top_down_yaw_valid_) {
          break;
        }
      }
      if (!selected_top_down_yaw_valid_) {
        RCLCPP_ERROR(get_logger(), "No top-down/tilted yaw candidate has an IK solution.");
        return false;
      }
    }
    PopulateTopDownPose(
      object_world, vertical_clearance_m, selected_top_down_tilt_,
      selected_top_down_yaw_, grasp_target);
    target_pose_publisher_->publish(grasp_target);
    RCLCPP_INFO(
      get_logger(),
      "Top-down grasp target: object=(%.3f, %.3f, %.3f), clearance=%.3f m, "
      "gripper_base=(%.3f, %.3f, %.3f).",
      object_world.point.x, object_world.point.y, object_world.point.z,
      vertical_clearance_m, grasp_target.pose.position.x, grasp_target.pose.position.y,
      grasp_target.pose.position.z);
    if (!locked_approach_orientation_valid_) {
      RCLCPP_INFO(
        get_logger(), "Top-down approach selected: tilt=%.3f yaw=%.3f rad.",
        selected_top_down_tilt_, selected_top_down_yaw_);
    }
    return true;
  }

  void PopulateTopDownPose(
    const geometry_msgs::msg::PointStamped & object_world, double vertical_clearance_m,
    double tilt, double yaw, geometry_msgs::msg::PoseStamped & grasp_target)
  {
    const auto orientation = locked_approach_orientation_valid_ ?
      locked_approach_orientation_ : TopDownOrientation(yaw, tilt);
    tf2::Quaternion rotation;
    tf2::fromMsg(orientation, rotation);
    tf2::Vector3 tool_axis = tf2::quatRotate(rotation, tf2::Vector3(0.0, 0.0, 1.0));
    tool_axis.normalize();
    const double tip_distance = gripper_tip_offset_m_ + grasp_height_offset_m_ +
      vertical_clearance_m;
    grasp_target.header.frame_id = lift_reference_frame_;
    grasp_target.header.stamp = now();
    const auto origin = grasp_geometry::ToolOrigin(
      {object_world.point.x, object_world.point.y, object_world.point.z},
      {tool_axis.x(), tool_axis.y(), tool_axis.z()}, gripper_tip_offset_m_,
      tip_distance - gripper_tip_offset_m_);
    grasp_target.pose.position.x = origin[0];
    grasp_target.pose.position.y = origin[1];
    grasp_target.pose.position.z = origin[2];
    grasp_target.pose.orientation = orientation;
  }

  geometry_msgs::msg::Quaternion TopDownOrientation(double yaw, double tilt) const
  {
    tf2::Quaternion orientation;
    orientation.setRPY(0.0, std::acos(-1.0) - tilt, yaw);
    orientation.normalize();
    return tf2::toMsg(orientation);
  }

  bool TopDownPoseHasIk(const geometry_msgs::msg::PoseStamped & target)
  {
    if (!compute_ik_client_->wait_for_service(std::chrono::seconds(2))) {
      return false;
    }
    if (!WaitForFreshJointState("TOP_DOWN_IK")) {
      return false;
    }
    const auto current_state = FreshMeasuredState("CURRENT_STATE_IK");
    if (!current_state) {
      return false;
    }
    auto request = std::make_shared<moveit_msgs::srv::GetPositionIK::Request>();
    request->ik_request.group_name = arm_group_;
    request->ik_request.ik_link_name = end_effector_link_;
    request->ik_request.pose_stamped = target;
    request->ik_request.avoid_collisions = false;
    request->ik_request.timeout.sec = 1;
    moveit::core::robotStateToRobotStateMsg(*current_state, request->ik_request.robot_state);
    auto future = compute_ik_client_->async_send_request(request);
    if (future.wait_for(std::chrono::seconds(2)) != std::future_status::ready) {
      RCLCPP_WARN(get_logger(), "Top-down IK request timed out for link %s.", end_effector_link_.c_str());
      return false;
    }
    const auto response = future.get();
    if (response->error_code.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
      RCLCPP_WARN(
        get_logger(),
        "Top-down IK rejected link=%s frame=%s pose=(%.3f, %.3f, %.3f) code=%d.",
        end_effector_link_.c_str(), target.header.frame_id.c_str(),
        target.pose.position.x, target.pose.position.y, target.pose.position.z,
        response->error_code.val);
      return false;
    }
    return true;
  }

  bool BuildAlignedPointGrasp(
    double camera_standoff_m, geometry_msgs::msg::PoseStamped & grasp_target)
  {
    geometry_msgs::msg::PointStamped cup_world;
    if (!PredictedTargetInReference(cup_world)) {
      return false;
    }
    try {
      const auto world_from_camera_message = tf_buffer_->lookupTransform(
        lift_reference_frame_, camera_optical_frame_, tf2::TimePointZero);
      tf2::Quaternion current_camera_orientation;
      tf2::fromMsg(world_from_camera_message.transform.rotation, current_camera_orientation);
      tf2::Vector3 forward = tf2::quatRotate(
        current_camera_orientation, tf2::Vector3(0.0, 0.0, 1.0));
      forward.setZ(0.0);
      if (forward.length2() < 1e-4) {
        RCLCPP_ERROR(
          get_logger(), "Camera optical axis is not horizontal enough for a side grasp.");
        return false;
      }
      forward.normalize();
      const tf2::Vector3 desired_camera_position(
        cup_world.point.x - forward.x() * camera_standoff_m,
        cup_world.point.y - forward.y() * camera_standoff_m,
        cup_world.point.z + grasp_height_offset_m_);
      const auto current_gripper = CurrentPoseInFrame(lift_reference_frame_);
      const tf2::Vector3 current_camera_position(
        world_from_camera_message.transform.translation.x,
        world_from_camera_message.transform.translation.y,
        world_from_camera_message.transform.translation.z);

      grasp_target.header.frame_id = lift_reference_frame_;
      grasp_target.header.stamp = now();
      grasp_target.pose.position.x = current_gripper.pose.position.x +
        desired_camera_position.x() - current_camera_position.x();
      grasp_target.pose.position.y = current_gripper.pose.position.y +
        desired_camera_position.y() - current_camera_position.y();
      grasp_target.pose.position.z = current_gripper.pose.position.z +
        desired_camera_position.z() - current_camera_position.z();
      grasp_target.pose.orientation = current_gripper.pose.orientation;
      target_pose_publisher_->publish(grasp_target);
      RCLCPP_INFO(
        get_logger(),
        "Aligned grasp target: cup=(%.3f, %.3f, %.3f), stand-off=%.3f m, "
        "height-offset=%.3f m; preserving reached gripper orientation, "
        "gripper=(%.3f, %.3f, %.3f), quaternion=(%.3f, %.3f, %.3f, %.3f).",
        cup_world.point.x, cup_world.point.y, cup_world.point.z, camera_standoff_m,
        grasp_height_offset_m_,
        grasp_target.pose.position.x, grasp_target.pose.position.y, grasp_target.pose.position.z,
        grasp_target.pose.orientation.x, grasp_target.pose.orientation.y,
        grasp_target.pose.orientation.z, grasp_target.pose.orientation.w);
      return true;
    } catch (const tf2::TransformException & exception) {
      RCLCPP_ERROR(get_logger(), "Cannot construct horizontal grasp target: %s", exception.what());
      return false;
    }
  }

  bool PredictedTargetInReference(geometry_msgs::msg::PointStamped & predicted_target)
  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    if (target_model_locked_) {
      predicted_target = locked_target_reference_;
      return true;
    }
    const auto now = std::chrono::steady_clock::now();
    const double age_s = std::chrono::duration<double>(now - target_reference_received_time_).count();
    if (target_reference_received_time_ == std::chrono::steady_clock::time_point{} ||
      age_s > target_timeout_s_)
    {
      RCLCPP_ERROR(get_logger(), "Reference-frame target is missing or stale (age %.3f s).", age_s);
      return false;
    }
    predicted_target = target_point_reference_;
    const double sample_dt_s = std::chrono::duration<double>(
      target_reference_received_time_ - previous_target_reference_received_time_).count();
    if (previous_target_reference_received_time_ == std::chrono::steady_clock::time_point{} ||
      sample_dt_s <= 0.001 || sample_dt_s > target_timeout_s_)
    {
      return true;
    }
    const double vx = (target_point_reference_.point.x - previous_target_point_reference_.point.x) /
      sample_dt_s;
    const double vy = (target_point_reference_.point.y - previous_target_point_reference_.point.y) /
      sample_dt_s;
    const double vz = (target_point_reference_.point.z - previous_target_point_reference_.point.z) /
      sample_dt_s;
    const double speed_m_s = std::sqrt(vx * vx + vy * vy + vz * vz);
    if (!std::isfinite(speed_m_s) || speed_m_s > approach_max_target_speed_m_s_) {
      PublishDiagnostic("MICRO_APPROACH_PREDICTION_SKIPPED_UNSTABLE_TARGET_VELOCITY");
      return true;
    }
    predicted_target.point.x += vx * approach_prediction_horizon_s_;
    predicted_target.point.y += vy * approach_prediction_horizon_s_;
    predicted_target.point.z += vz * approach_prediction_horizon_s_;
    PublishDiagnostic("MICRO_APPROACH_SHORT_HORIZON_TARGET_PREDICTION");
    return true;
  }

  bool WaitForCup()
  {
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(scene_wait_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      const auto names = planning_scene_->getKnownObjectNames();
      if (std::find(names.begin(), names.end(), cup_name_) != names.end()) {
        return true;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    return false;
  }

  bool TargetStillAligned()
  {
    if (static_target_lock_ && target_model_locked_) {
      return true;
    }
    if (approach_locked_) {
      // Once the pregrasp is reached, the arm is moving relative to a static
      // base-frame target model. Do not let wrist-camera parallax or a transient
      // colour/depth drop restart visual ALIGN/SEARCH.
      return target_model_locked_;
    }
    std::lock_guard<std::mutex> lock(target_mutex_);
    const auto now = std::chrono::steady_clock::now();
    const auto target_age = std::chrono::duration<double>(now - target_point_received_time_).count();
    const auto error_age = std::chrono::duration<double>(now - target_error_received_time_).count();
    const auto valid_age = std::chrono::duration<double>(now - target_valid_received_time_).count();
    const auto depth_valid_age = std::chrono::duration<double>(now - depth_valid_received_time_).count();
    return target_point_received_time_ != std::chrono::steady_clock::time_point{} &&
           target_error_received_time_ != std::chrono::steady_clock::time_point{} &&
           target_valid_received_time_ != std::chrono::steady_clock::time_point{} &&
           depth_valid_received_time_ != std::chrono::steady_clock::time_point{} &&
           target_age <= target_timeout_s_ && error_age <= target_timeout_s_ &&
           valid_age <= target_timeout_s_ && depth_valid_age <= target_timeout_s_ &&
           target_valid_ && depth_valid_ &&
           target_error_ratio_ <= grasp_alignment_error_ratio_;
  }

  bool DepthStillTrusted()
  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    const auto now = std::chrono::steady_clock::now();
    const auto age_s = std::chrono::duration<double>(now - depth_valid_received_time_).count();
    return depth_valid_received_time_ != std::chrono::steady_clock::time_point{} &&
      age_s <= target_timeout_s_ && depth_valid_;
  }

  void RetryFreshTargetTransform()
  {
    if (depth_only_target_enabled_) {
      return;
    }
    geometry_msgs::msg::PointStamped camera_point;
    std::chrono::steady_clock::time_point received;
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      camera_point = target_point_camera_;
      received = target_point_received_time_;
    }
    if (received == std::chrono::steady_clock::time_point{} ||
      std::chrono::duration<double>(std::chrono::steady_clock::now() - received).count() >
      target_timeout_s_ ||
      (camera_point.header.stamp.sec == 0 && camera_point.header.stamp.nanosec == 0))
    {
      return;
    }
    const std::string frame = camera_point.header.frame_id.empty() ?
      camera_optical_frame_ : camera_point.header.frame_id;
    const rclcpp::Time stamp(camera_point.header.stamp);
    try {
      const auto transform = tf_buffer_->lookupTransform(lift_reference_frame_, frame, stamp);
      geometry_msgs::msg::PointStamped reference_point;
      tf2::doTransform(camera_point, reference_point, transform);
      std::lock_guard<std::mutex> lock(target_mutex_);
      // A newer callback may have arrived during lookup: never replace it
      // with an older point, or rejuvenate the original receipt timestamp.
      if (received != target_point_received_time_ ||
        std::chrono::duration<double>(std::chrono::steady_clock::now() - received).count() >
        target_timeout_s_ || received <= target_reference_received_time_)
      {
        return;
      }
      previous_target_point_reference_ = target_point_reference_;
      previous_target_reference_received_time_ = target_reference_received_time_;
      target_point_reference_ = reference_point;
      target_reference_received_time_ = received;
      RCLCPP_INFO(
        get_logger(), "TARGET_TF_RETRY image_stamp=%.9f tf_stamp=%.9f age=%.3f "
        "reference=%s xyz=(%.4f,%.4f,%.4f)", stamp.seconds(),
        rclcpp::Time(transform.header.stamp).seconds(),
        std::chrono::duration<double>(std::chrono::steady_clock::now() - received).count(),
        lift_reference_frame_.c_str(), reference_point.point.x,
        reference_point.point.y, reference_point.point.z);
    } catch (const tf2::TransformException &) {
      // Leave callbacks free to supply TF/new observations; no latest fallback.
    }
  }

  bool WaitForTargetModel()
  {
    PublishState("WAITING_FOR_FRESH_TARGET_TF");
    PublishDiagnostic("WAITING_FOR_FRESH_TARGET_TF_HOLDING");
    const bool locked = WaitForFreshTargetModel(
      [this]() {return rclcpp::ok() && !cancel_requested_;},
      [this]() {
        RetryFreshTargetTransform();
        return CaptureTargetModel(false);
      },
      []() {std::this_thread::sleep_for(std::chrono::milliseconds(20));});
    if (!locked) {
      RCLCPP_INFO(get_logger(), "Target-model wait cancelled; no gripper/arm command issued.");
    }
    return locked;
  }

  bool CaptureTargetModel(bool log_unavailable = true)
  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    const auto now = std::chrono::steady_clock::now();
    const auto age_s = std::chrono::duration<double>(now - target_reference_received_time_).count();
    if (target_reference_received_time_ == std::chrono::steady_clock::time_point{} ||
      age_s > target_timeout_s_ || !target_valid_ || !depth_valid_ ||
      !std::isfinite(target_point_reference_.point.x) ||
      !std::isfinite(target_point_reference_.point.y) ||
      !std::isfinite(target_point_reference_.point.z))
    {
      if (log_unavailable) {
        RCLCPP_WARN(get_logger(), "Cannot lock base-frame target model (age %.3f s).", age_s);
      }
      return false;
    }
    if (adaptive_size_enabled_) {
      const double size_age_s = std::chrono::duration<double>(
        now - target_size_received_time_).count();
      const double width_m = std::max(target_size_.vector.x, target_size_.vector.y);
      const double face_edge_m = std::min(target_size_.vector.x, target_size_.vector.y);
      if (target_size_received_time_ == std::chrono::steady_clock::time_point{} ||
        size_age_s > target_timeout_s_ || !std::isfinite(width_m) ||
        width_m < min_object_size_m_ || width_m > max_object_size_m_ ||
        !std::isfinite(face_edge_m) || face_edge_m < min_object_size_m_)
      {
        if (log_unavailable) {
          RCLCPP_WARN(get_logger(), "Cannot lock cube size (age %.3f s).", size_age_s);
        }
        return false;
      }
      locked_object_size_m_ = width_m;
      locked_object_min_size_m_ = face_edge_m;
    }
    locked_target_reference_ = target_point_reference_;
    target_model_locked_ = true;
    PublishDiagnostic("GRASP_TARGET_MODEL_LOCKED_BASE_FRAME");
    RCLCPP_INFO(
      get_logger(), "Locked base-frame target model: (%.3f, %.3f, %.3f).",
      locked_target_reference_.point.x, locked_target_reference_.point.y,
      locked_target_reference_.point.z);
    return true;
  }

  void RequestVisualReacquire(const std::string & reason)
  {
    approach_locked_ = false;
    target_model_locked_ = false;
    locked_object_size_m_ = 0.0;
    locked_object_min_size_m_ = 0.0;
    cancel_requested_ = true;
    PublishDiagnostic(reason);
    std_msgs::msg::Bool message;
    message.data = true;
    reacquire_publisher_->publish(message);
    RCLCPP_WARN(get_logger(), "Returning to visual ALIGN: %s.", reason.c_str());
  }

  bool MoveGripper(const std::string & target_name)
  {
    gripper_->setStartStateToCurrentState();
    if (!gripper_->setNamedTarget(target_name)) {
      RCLCPP_ERROR(get_logger(), "Unknown gripper target '%s'.", target_name.c_str());
      return false;
    }
    MoveGroupInterface::Plan plan;
    return static_cast<bool>(gripper_->plan(plan)) && !cancel_requested_ &&
           static_cast<bool>(gripper_->execute(plan));
  }

  bool CommandRealGripper(bool open)
  {
    if (simulation_only_) {
      return MoveGripper(open ? open_target_ : close_target_);
    }
    sensor_msgs::msg::JointState command;
    command.header.stamp = now();
    command.name = {"gripper"};
    command.position = {static_cast<double>(
        open ? gripper_open_value_ : gripper_close_value_) / 1000000.0};
    RCLCPP_INFO(
      get_logger(), "Publishing real gripper %s command %.6f m to %zu subscriber(s).",
      open ? "open" : "close", command.position.front(),
      gripper_command_publisher_->get_subscription_count());
    gripper_command_publisher_->publish(command);
    PublishDiagnostic(std::string("GRIPPER_COMMAND_") + (open ? "OPEN_" : "CLOSE_") +
      std::to_string(open ? gripper_open_value_ : gripper_close_value_));
    return true;
  }

  bool ExecuteArmTrajectory(const trajectory_msgs::msg::JointTrajectory & trajectory)
  {
    if (simulation_only_) {
      return false;
    }
    if (trajectory.joint_names.empty() || trajectory.points.empty()) {
      return false;
    }
    const auto observation_ok = [this]() {
        if (!near_depth_tracking_active_) {return true;}
        geometry_msgs::msg::PointStamped target;
        rclcpp::Time stamp(0, 0, get_clock()->get_clock_type());
        bool predicted = false;
        return ObserveLockedTarget(target, stamp, predicted, nullptr, nullptr, nullptr,
          nullptr, automatic_rgb_approach_enabled_);
      };
    if (!observation_ok()) {
      PublishDiagnostic("LOCKED_RGB_OBSERVATION_UNAVAILABLE_BEFORE_ARM_OUTPUT"); return false;
    }
    const auto & final_point = trajectory.points.back();
    const double duration_s = static_cast<double>(final_point.time_from_start.sec) +
      static_cast<double>(final_point.time_from_start.nanosec) * 1e-9;
    std::ostringstream endpoint;
    endpoint << "duration_s=" << duration_s;
    for (std::size_t index = 0;
      index < trajectory.joint_names.size() && index < final_point.positions.size(); ++index)
    {
      endpoint << " " << trajectory.joint_names[index] << "=" << final_point.positions[index];
    }
    RCLCPP_INFO(
      get_logger(), "Real arm trajectory endpoint: %s.", endpoint.str().c_str());
    arm_trajectory_publisher_->publish(trajectory);
    PublishDiagnostic("REAL_ARM_TRAJECTORY_PUBLISHED");
    const auto earliest_feedback_time = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(duration_s));
    const auto deadline = earliest_feedback_time +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(trajectory_feedback_timeout_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      if (!observation_ok()) {
        // Stop the ORIGINAL adapter's output and hold enabled. MoveGroup::stop()
        // alone cannot cancel a trajectory published to this separate adapter.
        std_msgs::msg::Bool stop;
        stop.data = true;
        software_stop_publisher_->publish(stop);  // Existing software stop, never DisableArm.
        bool stopped = false;
        if (adapter_disarm_client_->service_is_ready()) {
          auto future = adapter_disarm_client_->async_send_request(
            std::make_shared<std_srvs::srv::Trigger::Request>());
          if (future.wait_for(std::chrono::milliseconds(600)) == std::future_status::ready) {
            const auto response = future.get(); stopped = response && response->success;
          }
        }
        cancel_requested_ = true;
        PublishDiagnostic(stopped ? "LOCKED_RGB_LOST_ADAPTER_DISARM_CONFIRMED_HOLD_ENABLED" :
          "LOCKED_RGB_LOST_ADAPTER_DISARM_UNCONFIRMED");
        return false;
      }
      if (std::chrono::steady_clock::now() >= earliest_feedback_time &&
        TrajectoryFeedbackReached(trajectory.joint_names, final_point.positions))
      {
        PublishDiagnostic("REAL_ARM_TRAJECTORY_FEEDBACK_CONFIRMED");
        return true;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    if (!cancel_requested_) {
      PublishDiagnostic("REAL_ARM_TRAJECTORY_FEEDBACK_TIMEOUT_OR_DEVIATION");
      sensor_msgs::msg::JointState joint_state;
      double feedback_age_s = std::numeric_limits<double>::infinity();
      {
        std::lock_guard<std::mutex> lock(feedback_mutex_);
        if (joint_state_received_time_ != std::chrono::steady_clock::time_point{}) {
          feedback_age_s = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - joint_state_received_time_).count();
        }
        joint_state = latest_joint_state_;
      }
      std::ostringstream deviations;
      deviations << "feedback_age_s=" << feedback_age_s;
      for (std::size_t target_index = 0;
        target_index < trajectory.joint_names.size() &&
        target_index < final_point.positions.size(); ++target_index)
      {
        const auto state_index = std::find(
          joint_state.name.begin(), joint_state.name.end(), trajectory.joint_names[target_index]);
        if (state_index == joint_state.name.end()) {
          deviations << " " << trajectory.joint_names[target_index] << "=MISSING";
          continue;
        }
        const std::size_t index = static_cast<std::size_t>(
          std::distance(joint_state.name.begin(), state_index));
        if (index >= joint_state.position.size()) {
          deviations << " " << trajectory.joint_names[target_index] << "=MISSING";
          continue;
        }
        const double measured = joint_state.position[index];
        const double target = final_point.positions[target_index];
        deviations << " " << trajectory.joint_names[target_index]
                   << "_measured=" << measured
                   << "_target=" << target
                   << "_error=" << std::abs(measured - target);
      }
      RCLCPP_ERROR(
        get_logger(), "Real arm trajectory feedback timeout: %s.",
        deviations.str().c_str());
    }
    return false;
  }

  bool TrajectoryFeedbackReached(
    const std::vector<std::string> & joint_names, const std::vector<double> & target_positions)
  {
    if (joint_names.size() != target_positions.size()) {
      return false;
    }
    sensor_msgs::msg::JointState joint_state;
    {
      std::lock_guard<std::mutex> lock(feedback_mutex_);
      const auto age_s = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - joint_state_received_time_).count();
      if (joint_state_received_time_ == std::chrono::steady_clock::time_point{} ||
        age_s > target_timeout_s_)
      {
        return false;
      }
      joint_state = latest_joint_state_;
    }
    for (std::size_t target_index = 0; target_index < joint_names.size(); ++target_index) {
      const auto state_index = std::find(
        joint_state.name.begin(), joint_state.name.end(), joint_names[target_index]);
      if (state_index == joint_state.name.end()) {
        return false;
      }
      const std::size_t index = static_cast<std::size_t>(
        std::distance(joint_state.name.begin(), state_index));
      if (index >= joint_state.position.size() ||
        std::abs(joint_state.position[index] - target_positions[target_index]) >
        trajectory_feedback_tolerance_rad_)
      {
        return false;
      }
    }
    return true;
  }

  double LatestGripperPosition()
  {
    std::lock_guard<std::mutex> lock(feedback_mutex_);
    return JointPosition(latest_gripper_feedback_, "gripper");
  }

  bool FreshFaceInsideJaws()
  {
    geometry_msgs::msg::PointStamped face;
    double size = 0.0;
    const auto now_steady = std::chrono::steady_clock::now();
    bool fresh_rgbd = false;
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      const auto fresh = [&](const auto & received) {
          return received != std::chrono::steady_clock::time_point{} &&
                 std::chrono::duration<double>(now_steady - received).count() <= target_timeout_s_;
        };
      fresh_rgbd = target_valid_ && depth_valid_ && fresh(target_point_received_time_) &&
        fresh(target_valid_received_time_) && fresh(depth_valid_received_time_) &&
        fresh(target_size_received_time_);
      if (fresh_rgbd) {
        face = target_point_camera_;
        size = std::max(target_size_.vector.x, target_size_.vector.y);
      }
    }
    bool predicted = false;
    rclcpp::Time capture_stamp(0, 0, get_clock()->get_clock_type());
    if (near_depth_rgb_tracking_enabled_) {
      // Use one autonomous identity check for BOTH fresh-depth and RGB-only
      // modes. A newly detected purple point cannot replace the locked cube
      // at the final closure decision.
      if (!ObserveLockedTarget(face, capture_stamp, predicted) || near_view_recovery_ ||
        near_rgb_association_bad_frames_seen_ != 0)
      {
        PublishDiagnostic("JAW_CAPTURE_LOCKED_OBJECT_UNCONFIRMED_NO_CLOSE");
        return false;
      }
      std::lock_guard<std::mutex> lock(target_mutex_);
      size = locked_object_size_m_;
    } else if (!fresh_rgbd) {
      PublishDiagnostic("JAW_CAPTURE_FRESH_RGBD_AND_LOCKED_RGB_UNAVAILABLE_NO_CLOSE");
      return false;
    } else {
      capture_stamp = rclcpp::Time(face.header.stamp, get_clock()->get_clock_type());
    }
    double opening = 0.0;
    {
      std::lock_guard<std::mutex> lock(feedback_mutex_);
      if (gripper_feedback_received_time_ == std::chrono::steady_clock::time_point{} ||
        std::chrono::duration<double>(now_steady - gripper_feedback_received_time_).count() >
        target_timeout_s_)
      {
        return false;
      }
      opening = JointPosition(latest_gripper_feedback_, "gripper");
    }
    if (!near_depth::PlausibleOpening(opening)) {
      PublishDiagnostic("JAW_CAPTURE_OPENING_OUTSIDE_EXISTING_PIPER_RANGE_NO_CLOSE");
      return false;
    }
    if (!std::isfinite(size) || size < min_object_size_m_ || size > max_object_size_m_) {
      return false;
    }
    const auto & source_stamp_msg = face.header.stamp;
    const std::string source_frame = face.header.frame_id.empty() ?
      camera_optical_frame_ : face.header.frame_id;
    if (source_stamp_msg.sec == 0 && source_stamp_msg.nanosec == 0) {
      PublishDiagnostic("JAW_CAPTURE_TF_ZERO_STAMP_NO_CLOSE");
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Fresh jaw-capture check rejected: source=%s has zero stamp; latest-TF fallback disabled",
        source_frame.c_str());
      return false;
    }
    const rclcpp::Time source_stamp = capture_stamp;
    try {
      const auto transform = tf_buffer_->lookupTransform(
        "gripper_base", source_frame, source_stamp);
      geometry_msgs::msg::PointStamped local;
      tf2::doTransform(face, local, transform);
      const bool inside = grasp_geometry::FaceInsideJawCapture(
        {local.point.x, local.point.y, local.point.z}, gripper_tip_offset_m_, size, opening);
      RCLCPP_INFO(get_logger(),
        "JAW_CAPTURE mode=%s source=%s measurement_stamp=%.9f image_stamp=%.9f tf_stamp=%.9f "
        "face=(%.4f,%.4f,%.4f) tip_z=%.4f size=%.4f opening=%.4f inside=%s "
        "MODEL_MOUNT_NOT_EXTERNAL_CALIBRATION",
        predicted ? "LOCKED_3D_FRESH_RGB_PREDICTION" : "FRESH_RGBD",
        source_frame.c_str(), rclcpp::Time(face.header.stamp).seconds(), source_stamp.seconds(),
        rclcpp::Time(transform.header.stamp).seconds(),
        local.point.x, local.point.y, local.point.z, gripper_tip_offset_m_, size,
        opening, inside ? "true" : "false");
      // Model jaw geometry/opening checks are identical in both modes. A
      // prediction is not a fresh depth measurement or external calibration.
      return inside;
    } catch (const tf2::TransformException & error) {
      RCLCPP_ERROR(get_logger(),
        "Fresh jaw-capture transform unavailable: gripper_base<- %s at image_stamp=%.9f; "
        "latest-TF fallback disabled: %s",
        source_frame.c_str(), source_stamp.seconds(), error.what());
      return false;
    }
  }

  bool WaitForGripperCommand(
    double before_command, int target_value, bool allow_contact_stop,
    const std::string & stage)
  {
    const double target_m = static_cast<double>(target_value) / 1000000.0;
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(gripper_feedback_timeout_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      {
        std::lock_guard<std::mutex> lock(feedback_mutex_);
        const auto age_s = std::chrono::duration<double>(
          std::chrono::steady_clock::now() - gripper_feedback_received_time_).count();
        const double current = JointPosition(latest_gripper_feedback_, "gripper");
        if (gripper_feedback_received_time_ != std::chrono::steady_clock::time_point{} &&
          age_s <= target_timeout_s_ && std::isfinite(before_command) && std::isfinite(current))
        {
          const bool target_reached =
            std::abs(current - target_m) <= gripper_position_tolerance_m_;
          const bool contact_motion_confirmed = allow_contact_stop &&
            std::abs(current - before_command) >= min_gripper_feedback_motion_rad_;
          if (target_reached || contact_motion_confirmed) {
            PublishDiagnostic(
              stage + "_FEEDBACK_CONFIRMED before_m=" + std::to_string(before_command) +
              " current_m=" + std::to_string(current) +
              " target_m=" + std::to_string(target_m));
            return true;
          }
        }
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    const double current = LatestGripperPosition();
    RCLCPP_ERROR(
      get_logger(),
      "%s feedback unconfirmed: before=%.6f m current=%.6f m target=%.6f m "
      "tolerance=%.6f m minimum_motion=%.6f m contact_stop=%s.",
      stage.c_str(), before_command, current, target_m, gripper_position_tolerance_m_,
      min_gripper_feedback_motion_rad_, allow_contact_stop ? "true" : "false");
    return false;
  }

  static double JointPosition(const sensor_msgs::msg::JointState & state, const std::string & name)
  {
    const auto iterator = std::find(state.name.begin(), state.name.end(), name);
    if (iterator == state.name.end()) {
      return std::numeric_limits<double>::quiet_NaN();
    }
    const std::size_t index = static_cast<std::size_t>(
      std::distance(state.name.begin(), iterator));
    return index < state.position.size() ? state.position[index] :
      std::numeric_limits<double>::quiet_NaN();
  }

  bool AttachCup()
  {
    geometry_msgs::msg::PoseStamped gripper_pose = CurrentPoseInFrame(
      cached_cup_.header.frame_id.empty() ? lift_reference_frame_ : cached_cup_.header.frame_id);
    if (gripper_pose.header.frame_id.empty() || cached_cup_.primitive_poses.empty()) {
      return false;
    }

    tf2::Transform object_transform;
    tf2::Transform primitive_transform;
    tf2::Transform gripper_transform;
    tf2::fromMsg(cached_cup_.pose, object_transform);
    tf2::fromMsg(cached_cup_.primitive_poses.front(), primitive_transform);
    tf2::fromMsg(gripper_pose.pose, gripper_transform);
    const tf2::Transform cup_relative =
      gripper_transform.inverse() * object_transform * primitive_transform;

    moveit_msgs::msg::AttachedCollisionObject attached;
    attached.link_name = end_effector_link_;
    attached.touch_links = gripper_touch_links_;
    for (const auto & link_name : gripper_->getLinkNames()) {
      if (std::find(attached.touch_links.begin(), attached.touch_links.end(), link_name) ==
        attached.touch_links.end())
      {
        attached.touch_links.push_back(link_name);
      }
    }
    if (std::find(
        attached.touch_links.begin(), attached.touch_links.end(), end_effector_link_) ==
      attached.touch_links.end())
    {
      attached.touch_links.push_back(end_effector_link_);
    }
    attached.object = cached_cup_;
    attached.object.header.frame_id = end_effector_link_;
    attached.object.pose = geometry_msgs::msg::Pose();
    attached.object.pose.orientation.w = 1.0;
    tf2::toMsg(cup_relative, attached.object.primitive_poses.front());
    attached.object.operation = moveit_msgs::msg::CollisionObject::ADD;
    if (!planning_scene_->applyAttachedCollisionObject(attached)) {
      return false;
    }
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      attached_ = true;
    }
    return true;
  }

  bool DetachCupToWorld()
  {
    moveit_msgs::msg::AttachedCollisionObject detached;
    detached.link_name = end_effector_link_;
    detached.object.id = cached_cup_.id;
    detached.object.operation = moveit_msgs::msg::CollisionObject::REMOVE;
    if (!planning_scene_->applyAttachedCollisionObject(detached)) {
      return false;
    }
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      attached_ = false;
    }

    // The simulation release returns to the measured grasp pose, which is the
    // cached world-object pose. Restore it after retreat so MoveIt keeps the
    // released object in the world scene instead of losing it.
    auto released = cached_cup_;
    released.operation = moveit_msgs::msg::CollisionObject::ADD;
    if (!planning_scene_->applyCollisionObject(released)) {
      return false;
    }
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      prepared_ = false;
    }
    return true;
  }

  geometry_msgs::msg::PoseStamped CurrentPoseInFrame(const std::string & frame)
  {
    auto pose = arm_->getCurrentPose(end_effector_link_);
    if (pose.header.frame_id.empty() || frame.empty() || pose.header.frame_id == frame) {
      return pose;
    }
    try {
      const auto transform = tf_buffer_->lookupTransform(
        frame, pose.header.frame_id, tf2::TimePointZero);
      geometry_msgs::msg::PoseStamped transformed;
      tf2::doTransform(pose, transformed, transform);
      return transformed;
    } catch (const tf2::TransformException & exception) {
      RCLCPP_ERROR(get_logger(), "Pose transform failed: %s", exception.what());
      return geometry_msgs::msg::PoseStamped();
    }
  }

  bool MoveArmToPose(
    const geometry_msgs::msg::PoseStamped & target, const std::string & stage)
  {
    MoveGroupInterface::Plan plan;
    if (!PlanArmToPose(target, stage, plan)) {
      return false;
    }
    std::string rejection;
    if (!simulation_only_ && !RealTrajectoryWithinLimits(
        plan.trajectory_.joint_trajectory, rejection))
    {
      PublishDiagnostic(stage + ":REAL_LIMIT_REJECTED:" + rejection);
      RCLCPP_WARN(
        get_logger(), "%s rejected before adapter output: %s.",
        stage.c_str(), rejection.c_str());
      return false;
    }
    if (simulation_only_) {
      return static_cast<bool>(arm_->execute(plan));
    }
    return ExecuteArmTrajectory(plan.trajectory_.joint_trajectory);
  }

  bool PlanArmToPose(
    const geometry_msgs::msg::PoseStamped & target, const std::string & stage,
    MoveGroupInterface::Plan & plan)
  {
    if (!WaitForFreshJointState(stage)) {
      RCLCPP_WARN(get_logger(), "%s skipped: no fresh joint state for planning.", stage.c_str());
      return false;
    }
    // Capture the freshly observed state into the request.  Calling
    // setStartStateToCurrentState() makes MoveGroup query its monitor again
    // during planning; a USB/firmware feedback gap can then replace the valid
    // state with a stale/default zero state while RRT is sampling.
    const auto fresh_state = FreshMeasuredState(stage);
    if (!fresh_state) {
      RCLCPP_WARN(get_logger(), "%s skipped: MoveIt current state became stale before planning.", stage.c_str());
      return false;
    }
    arm_->setStartState(*fresh_state);
    if (!simulation_only_) {
      arm_->setPlanningPipelineId(real_pose_planning_pipeline_);
      arm_->setPlannerId(real_pose_planner_id_);
    }
    arm_->setPoseReferenceFrame(target.header.frame_id);
    if (!arm_->setPoseTarget(target, end_effector_link_)) {
      RCLCPP_ERROR(get_logger(), "%s rejected the requested end-effector pose.", stage.c_str());
      return false;
    }
    const bool planned = static_cast<bool>(arm_->plan(plan));
    arm_->clearPoseTargets();
    if (!planned || cancel_requested_) {
      const auto current = arm_->getCurrentPose(end_effector_link_);
      current_pose_publisher_->publish(current);
      if (!planned) {
        const auto diagnosis = DiagnoseIk(target);
        PublishDiagnostic(stage + ":" + diagnosis);
        RCLCPP_WARN(
          get_logger(), "%s planning diagnosis: %s", stage.c_str(), diagnosis.c_str());
      }
      RCLCPP_ERROR(
        get_logger(),
        "%s planning failed: current=(%.3f, %.3f, %.3f), target=(%.3f, %.3f, %.3f), "
        "target_quaternion=(%.3f, %.3f, %.3f, %.3f).",
        stage.c_str(), current.pose.position.x, current.pose.position.y, current.pose.position.z,
        target.pose.position.x, target.pose.position.y, target.pose.position.z,
        target.pose.orientation.x, target.pose.orientation.y,
        target.pose.orientation.z, target.pose.orientation.w);
      return false;
    }
    RCLCPP_INFO(
      get_logger(), "%s planned with %zu trajectory points.", stage.c_str(),
      plan.trajectory_.joint_trajectory.points.size());
    return true;
  }

  bool RealTrajectoryWithinLimits(
    const trajectory_msgs::msg::JointTrajectory & trajectory, std::string & reason) const
  {
    static const std::vector<std::string> joint_names = {
      "joint1", "joint2", "joint3", "joint4", "joint5", "joint6"};
    if (trajectory.joint_names.empty() || trajectory.points.empty()) {
      reason = "empty trajectory";
      return false;
    }
    for (std::size_t point_index = 0; point_index < trajectory.points.size(); ++point_index) {
      const auto & point = trajectory.points[point_index];
      if (point.positions.size() != trajectory.joint_names.size()) {
        reason = "point " + std::to_string(point_index) + " position count mismatch";
        return false;
      }
      for (std::size_t trajectory_index = 0;
        trajectory_index < trajectory.joint_names.size(); ++trajectory_index)
      {
        const auto found = std::find(
          joint_names.begin(), joint_names.end(), trajectory.joint_names[trajectory_index]);
        if (found == joint_names.end()) {
          reason = "unknown joint " + trajectory.joint_names[trajectory_index];
          return false;
        }
        const auto joint_index = static_cast<std::size_t>(
          std::distance(joint_names.begin(), found));
        const double position = point.positions[trajectory_index];
        if (!std::isfinite(position) || position < real_trajectory_joint_min_[joint_index] ||
          position > real_trajectory_joint_max_[joint_index])
        {
          std::ostringstream stream;
          stream << "point " << point_index << " " << *found << "=" << position
                 << " outside [" << real_trajectory_joint_min_[joint_index] << ","
                 << real_trajectory_joint_max_[joint_index] << "]"
                 << " start=" << trajectory.points.front().positions[trajectory_index]
                 << " end=" << trajectory.points.back().positions[trajectory_index];
          reason = stream.str();
          return false;
        }
      }
    }
    return true;
  }


  std::shared_ptr<moveit::core::RobotState> StateAtTrajectoryEnd(
    const trajectory_msgs::msg::JointTrajectory & trajectory, const std::string & stage)
  {
    static const std::vector<std::string> arm_joint_names = {
      "joint1", "joint2", "joint3", "joint4", "joint5", "joint6"};
    auto state = FreshMeasuredState(stage);
    if (!state || trajectory.joint_names.empty() || trajectory.points.empty()) {
      return nullptr;
    }
    const auto & final_point = trajectory.points.back();
    if (final_point.positions.size() != trajectory.joint_names.size()) {
      RCLCPP_WARN(get_logger(), "%s trajectory endpoint dimensions are invalid.", stage.c_str());
      return nullptr;
    }
    for (std::size_t index = 0; index < trajectory.joint_names.size(); ++index) {
      if (std::find(
          arm_joint_names.begin(), arm_joint_names.end(), trajectory.joint_names[index]) ==
        arm_joint_names.end() ||
        !std::isfinite(final_point.positions[index]))
      {
        RCLCPP_WARN(
          get_logger(), "%s trajectory endpoint contains invalid joint %s.",
          stage.c_str(), trajectory.joint_names[index].c_str());
        return nullptr;
      }
      state->setVariablePosition(trajectory.joint_names[index], final_point.positions[index]);
    }
    state->update();
    return state;
  }

  bool CartesianTrajectoryContinuous(
    const trajectory_msgs::msg::JointTrajectory & trajectory, const std::string & stage)
  {
    if (trajectory.joint_names.empty() || trajectory.points.empty()) {
      PublishDiagnostic(stage + ":CARTESIAN_TRAJECTORY_EMPTY");
      return false;
    }
    double max_delta_rad = 0.0;
    for (std::size_t point_index = 0; point_index < trajectory.points.size(); ++point_index) {
      const auto & point = trajectory.points[point_index];
      if (point.positions.size() != trajectory.joint_names.size()) {
        PublishDiagnostic(stage + ":CARTESIAN_TRAJECTORY_DIMENSION_MISMATCH");
        return false;
      }
      for (const double position : point.positions) {
        if (!std::isfinite(position)) {
          PublishDiagnostic(stage + ":CARTESIAN_TRAJECTORY_NONFINITE");
          return false;
        }
      }
      if (point_index == 0) {
        continue;
      }
      const auto & previous = trajectory.points[point_index - 1];
      for (std::size_t joint_index = 0; joint_index < point.positions.size(); ++joint_index) {
        max_delta_rad = std::max(
          max_delta_rad, std::abs(point.positions[joint_index] - previous.positions[joint_index]));
      }
    }
    RCLCPP_INFO(
      get_logger(), "%s Cartesian maximum adjacent joint step is %.6f rad.",
      stage.c_str(), max_delta_rad);
    if (max_delta_rad > cartesian_max_joint_step_rad_) {
      PublishDiagnostic(stage + ":CARTESIAN_JOINT_JUMP_REJECTED");
      RCLCPP_ERROR(
        get_logger(), "%s Cartesian path rejected: adjacent joint step %.6f rad exceeds %.6f rad.",
        stage.c_str(), max_delta_rad, cartesian_max_joint_step_rad_);
      return false;
    }
    return true;
  }

  bool MoveArmCartesianToPose(
    const geometry_msgs::msg::PoseStamped & target, const std::string & stage)
  {
    if (!WaitForFreshJointState(stage)) {
      RCLCPP_WARN(get_logger(), "%s skipped: no fresh joint state for Cartesian planning.", stage.c_str());
      return false;
    }
    const auto fresh_state = FreshMeasuredState(stage);
    if (!fresh_state) {
      RCLCPP_WARN(get_logger(), "%s skipped: MoveIt current state became stale before Cartesian planning.", stage.c_str());
      return false;
    }
    moveit_msgs::msg::RobotTrajectory trajectory;
    if (!PlanArmCartesianFromState(target, stage, fresh_state, trajectory)) {
      return false;
    }
    std::string rejection;
    if (!simulation_only_ && !RealTrajectoryWithinLimits(trajectory.joint_trajectory, rejection)) {
      PublishDiagnostic(stage + ":REAL_LIMIT_REJECTED:" + rejection);
      RCLCPP_WARN(
        get_logger(), "%s rejected before adapter output: %s.", stage.c_str(), rejection.c_str());
      return false;
    }
    if (simulation_only_) {
      return static_cast<bool>(arm_->execute(trajectory));
    }
    return ExecuteArmTrajectory(trajectory.joint_trajectory);
  }

  bool PlanArmCartesianFromState(
    const geometry_msgs::msg::PoseStamped & target, const std::string & stage,
    const std::shared_ptr<moveit::core::RobotState> & start_state,
    moveit_msgs::msg::RobotTrajectory & trajectory)
  {
    return PlanArmCartesianWaypointsFromState(
      {target.pose}, target.header.frame_id, stage, start_state, trajectory);
  }

  bool PlanArmCartesianWaypointsFromState(
    const std::vector<geometry_msgs::msg::Pose> & waypoints, const std::string & frame,
    const std::string & stage, const std::shared_ptr<moveit::core::RobotState> & start_state,
    moveit_msgs::msg::RobotTrajectory & trajectory)
  {
    if (!start_state || waypoints.empty()) {
      return false;
    }
    arm_->setStartState(*start_state);
    arm_->setPoseReferenceFrame(frame);
    const double previous_velocity_scaling = velocity_scaling_;
    arm_->setMaxVelocityScalingFactor(linear_approach_velocity_scaling_);
    moveit_msgs::msg::MoveItErrorCodes planning_error;
    const double fraction = arm_->computeCartesianPath(
      waypoints, cartesian_eef_step_m_, 0.0, trajectory, true, &planning_error);
    arm_->setMaxVelocityScalingFactor(previous_velocity_scaling);
    if (fraction < 0.995 || trajectory.joint_trajectory.points.empty() || cancel_requested_) {
      RCLCPP_ERROR(
        get_logger(), "%s Cartesian path incomplete (fraction=%.3f error_code=%d).",
        stage.c_str(), fraction, planning_error.val);
      const auto * group = start_state->getRobotModel()->getJointModelGroup(arm_group_);
      if (group) {
        for (const auto & name : group->getVariableNames()) {
          RCLCPP_ERROR(get_logger(), "%s PLAN_START %s=%.12f", stage.c_str(), name.c_str(),
            start_state->getVariablePosition(name));
        }
      }
      return false;
    }
    if (!CartesianTrajectoryContinuous(trajectory.joint_trajectory, stage)) {
      return false;
    }
    RCLCPP_INFO(
      get_logger(), "%s Cartesian path has %zu trajectory points.", stage.c_str(),
      trajectory.joint_trajectory.points.size());
    return true;
  }

  std::string DiagnoseIk(const geometry_msgs::msg::PoseStamped & target)
  {
    if (!compute_ik_client_->wait_for_service(std::chrono::seconds(2))) {
      return "IK_SERVICE_UNAVAILABLE";
    }
    if (!WaitForFreshJointState("IK_DIAGNOSTIC")) {
      return "IK_CURRENT_STATE_STALE";
    }
    const auto current_state = FreshMeasuredState("CURRENT_STATE_IK");
    if (!current_state) {
      return "IK_CURRENT_STATE_UNAVAILABLE";
    }
    auto request = std::make_shared<moveit_msgs::srv::GetPositionIK::Request>();
    request->ik_request.group_name = arm_group_;
    request->ik_request.ik_link_name = end_effector_link_;
    request->ik_request.pose_stamped = target;
    request->ik_request.avoid_collisions = false;
    request->ik_request.timeout.sec = 1;
    moveit::core::robotStateToRobotStateMsg(*current_state, request->ik_request.robot_state);
    auto future = compute_ik_client_->async_send_request(request);
    if (future.wait_for(std::chrono::seconds(2)) != std::future_status::ready) {
      return "IK_TIMEOUT";
    }
    const auto response = future.get();
    if (response->error_code.val == moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
      return "IK_OK_PLAN_FAILED";
    }
    return "IK_ERROR_CODE_" + std::to_string(response->error_code.val);
  }

  bool WaitForFreshJointState(const std::string & stage)
  {
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(joint_state_wait_timeout_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
      {
        std::lock_guard<std::mutex> lock(feedback_mutex_);
        if (joint_state_received_time_ != std::chrono::steady_clock::time_point{}) {
          const double age_s = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - joint_state_received_time_).count();
          if (age_s <= 1.0) {
            return true;
          }
        }
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    RCLCPP_WARN(
      get_logger(), "%s waiting for fresh joint feedback timed out after %.1f s.",
      stage.c_str(), joint_state_wait_timeout_s_);
    return false;
  }

  std::shared_ptr<moveit::core::RobotState> FreshMeasuredState(const std::string & stage)
  {
    sensor_msgs::msg::JointState measured;
    {
      std::lock_guard<std::mutex> lock(feedback_mutex_);
      if (joint_state_received_time_ == std::chrono::steady_clock::time_point{}) {
        return nullptr;
      }
      const double age_s = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - joint_state_received_time_).count();
      if (age_s > 1.0) {
        RCLCPP_WARN(get_logger(), "%s measured joint state is %.3f s old.", stage.c_str(), age_s);
        return nullptr;
      }
      measured = latest_joint_state_;
    }
    if (!arm_ || !arm_->getRobotModel()) {
      return nullptr;
    }
    auto state = std::make_shared<moveit::core::RobotState>(arm_->getRobotModel());
    state->setToDefaultValues();
    std::size_t found = 0;
    for (std::size_t i = 0; i < measured.name.size() && i < measured.position.size(); ++i) {
      if (measured.name[i] == "joint1" || measured.name[i] == "joint2" ||
        measured.name[i] == "joint3" || measured.name[i] == "joint4" ||
        measured.name[i] == "joint5" || measured.name[i] == "joint6")
      {
        state->setVariablePosition(measured.name[i], measured.position[i]);
        ++found;
      }
    }
    if (found != 6) {
      RCLCPP_WARN(get_logger(), "%s measured state has only %zu/6 arm joints.", stage.c_str(), found);
      return nullptr;
    }
    state->update();
    return state;
  }

  bool SetCupFollowing(bool enabled)
  {
    if (!cup_follow_client_->wait_for_service(std::chrono::seconds(3))) {
      return false;
    }
    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = enabled;
    auto future = cup_follow_client_->async_send_request(request);
    if (future.wait_for(std::chrono::seconds(3)) != std::future_status::ready) {
      return false;
    }
    return future.get()->success;
  }

  bool StopServo()
  {
    if (!servo_stop_client_->wait_for_service(std::chrono::seconds(3))) {
      return false;
    }
    auto future = servo_stop_client_->async_send_request(
      std::make_shared<std_srvs::srv::Trigger::Request>());
    if (future.wait_for(std::chrono::seconds(3)) != std::future_status::ready) {
      return false;
    }
    const auto response = future.get();
    if (!response->success) {
      RCLCPP_ERROR(
        get_logger(), "Servo stop request was rejected: %s", response->message.c_str());
      return false;
    }
    return true;
  }

  void RestoreUnattachedCup()
  {
    bool restore_cup = false;
    moveit_msgs::msg::CollisionObject cached;
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      restore_cup = prepared_ && !attached_ && !worker_active_ && !cached_cup_.id.empty();
      if (restore_cup) {
        prepared_ = false;
        cached = cached_cup_;
      }
    }
    if (!restore_cup) {
      return;
    }
    cached.operation = moveit_msgs::msg::CollisionObject::ADD;
    if (!planning_scene_->applyCollisionObject(cached)) {
      RCLCPP_ERROR(get_logger(), "Failed to restore cup collision object after visual abort.");
    }
  }

  void Fail(const std::string & reason)
  {
    bool restore_cup = false;
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      restore_cup = prepared_ && !attached_ && !cached_cup_.id.empty();
      if (restore_cup) {
        prepared_ = false;
      }
    }
    if (restore_cup) {
      auto restored = cached_cup_;
      restored.operation = moveit_msgs::msg::CollisionObject::ADD;
      if (!planning_scene_->applyCollisionObject(restored)) {
        RCLCPP_ERROR(get_logger(), "Failed to restore the cup collision object after abort.");
      }
    }
    PublishSceneReady(false);
    PublishState("FAULT_" + reason);
    RCLCPP_ERROR(get_logger(), "Grasp sequence stopped: %s.", reason.c_str());
  }

  void PublishSceneReady(bool ready)
  {
    std_msgs::msg::Bool message;
    message.data = ready;
    scene_ready_publisher_->publish(message);
  }

  void PublishState(const std::string & state)
  {
    std_msgs::msg::String message;
    message.data = state;
    state_publisher_->publish(message);
  }

  void PublishDiagnostic(const std::string & diagnostic)
  {
    std_msgs::msg::String message;
    message.data = diagnostic;
    diagnostic_publisher_->publish(message);
  }

  bool simulation_only_{true};
  bool real_grasp_enabled_{false};
  bool auto_execute_{true};
  bool prepare_on_grasp_ready_{false};
  bool candidate_grasp_enabled_{false};
  std::vector<std::string> candidate_grasp_order_;
  bool top_down_grasp_enabled_{false};
  bool diagonal_side_grasp_enabled_{false};
  bool grasp_contact_check_enabled_{false};
  bool configuration_ok_{false};
  std::string arm_group_;
  std::string gripper_group_;
  std::string end_effector_link_;
  std::vector<std::string> gripper_touch_links_;
  std::string cup_name_;
  std::string open_target_;
  std::string close_target_;
  std::string lift_reference_frame_;
  std::string camera_optical_frame_;
  std::string target_point_topic_;
  std::string target_size_topic_;
  bool depth_only_target_enabled_{false};
  std::string depth_only_valid_topic_;
  std::string depth_only_point_topic_;
  std::string depth_only_size_topic_;
  std::string depth_only_error_topic_;
  std::string depth_valid_topic_;
  bool adaptive_size_enabled_{false};
  double min_object_size_m_{0.01};
  double max_object_size_m_{0.25};
  double target_timeout_s_{0.60};
  bool static_target_lock_{false};
  double grasp_height_offset_m_{0.0};
  double gripper_tip_offset_m_{0.1358};
  double grasp_center_offset_m_{0.1358};
  double grasp_contact_tolerance_m_{0.025};
  int gripper_open_value_{50000};
  bool allow_open_feedback_unconfirmed_for_approach_{false};
  int gripper_close_value_{40000};
  double gripper_settle_s_{2.0};
  bool fresh_jaw_capture_required_{false};
  bool near_depth_rgb_tracking_enabled_{false};
  bool automatic_rgb_approach_enabled_{false};
  bool terminal_depth_stage_enabled_{true};
  double terminal_depth_lock_range_m_{.20};
  bool coarse_depth_tracking_{false}, coarse_motion_in_progress_{false};
  bool terminal_target_frozen_{false};
  bool near_path_allowance_ready_{false};
  double near_path_max_age_s_{0};
  double near_path_max_travel_m_{0};
  bool near_depth_tracking_active_{false};
  double near_depth_prediction_max_age_s_{30.0};
  double near_depth_prediction_max_travel_m_{.030};
  near_depth::Seed near_seed_{};
  LockedRgbView near_last_full_rgb_view_{};
  visual_grasp::Box near_last_visible_rgb_box_{};
  bool near_view_recovery_{false};
  int64_t near_last_command_image_stamp_ns_{0};
  int64_t near_seed_stamp_ns_{0};
  int64_t near_last_image_stamp_ns_{0};
  tf2::Vector3 near_last_camera_origin_{0, 0, 0};
  double near_camera_travel_m_{0};
  bool near_last_mode_predicted_{false};
  geometry_msgs::msg::PolygonStamped qualified_box_message_;
  sensor_msgs::msg::CameraInfo raw_image_info_;
  std::chrono::steady_clock::time_point qualified_box_received_{};
  near_depth::Calibration near_calibration_{};
  bool near_calibration_ready_{false};
  std::atomic_bool calibration_request_pending_{false};
  std::shared_ptr<rclcpp::AsyncParametersClient> detector_parameters_;
  rclcpp::TimerBase::SharedPtr calibration_timer_;
  bool visual_microsteps_enabled_{false};
  double visual_microstep_m_{.005};
  double visual_microstep_angle_rad_{.01745329252};
  double visual_view_recovery_angle_rad_{.01745329252};
  int visual_view_recovery_steps_{3};
  int visual_microstep_max_steps_{4};
  double visual_target_association_m_{.04};
  int near_rgb_association_bad_frames_{5};
  int near_rgb_association_bad_frames_seen_{0};
  int64_t near_last_bad_association_stamp_ns_{0};
  int64_t near_seed_image_stamp_ns_{0};  // Metadata; terminal seed age is immutable.
  std::vector<double> visual_jaw_image_roi_;
  bool visual_jaw_image_roi_confirmed_{false};
  std::mutex visual_mutex_;
  visual_grasp::Box raw_box_{};
  geometry_msgs::msg::PointStamped raw_target_projection_;
  visual_grasp::Box visual_locked_box_{};
  bool raw_box_valid_{false};
  bool visual_locked_box_valid_{false};
  int raw_full_frames_{0};
  int64_t raw_box_stamp_ns_{0};
  std::chrono::steady_clock::time_point raw_box_received_{};
  std::string gripper_feedback_topic_;
  double gripper_feedback_timeout_s_{3.0};
  double min_gripper_feedback_motion_rad_{0.001};
  double gripper_position_tolerance_m_{0.003};
  bool auto_release_after_lift_{false};
  double hold_after_lift_s_{1.0};
  double top_down_pregrasp_clearance_m_{0.12};
  std::vector<double> top_down_pregrasp_clearance_candidates_m_;
  double top_down_grasp_clearance_m_{0.005};
  bool top_down_surface_grasp_enabled_{false};
  double surface_insertion_fraction_{0.4};
  double surface_insertion_max_m_{0.012};
  double grasp_landing_tolerance_m_{0.008};
  double grasp_landing_orientation_tolerance_rad_{0.05};
  double grasp_landing_max_correction_m_{0.020};
  double grasp_landing_feedback_tolerance_rad_{0.010};
  double grasp_landing_feedback_timeout_s_{8.0};
  double top_down_grasp_yaw_{0.0};
  std::vector<double> top_down_yaw_candidates_;
  std::vector<double> top_down_tilt_candidates_;
  std::string real_pose_planning_pipeline_;
  std::string real_pose_planner_id_;
  double selected_top_down_yaw_{0.0};
  double selected_top_down_tilt_{0.0};
  bool selected_top_down_yaw_valid_{false};
  bool preserve_aligned_grasp_orientation_{false};
  double aligned_grasp_pitch_down_rad_{0.0};
  bool locked_approach_orientation_valid_{false};
  bool target_directed_grasp_enabled_{false};
  double target_directed_downward_fraction_{0.5};
  geometry_msgs::msg::Quaternion locked_approach_orientation_;
  double diagonal_pregrasp_standoff_m_{0.17};
  double diagonal_grasp_standoff_m_{0.045};
  double diagonal_pregrasp_lift_m_{0.10};
  double diagonal_grasp_lift_m_{0.04};
  double diagonal_lateral_offset_m_{0.06};
  double pregrasp_standoff_m_{0.16};
  double grasp_depth_m_{0.08};
  double approach_microstep_m_{0.008};
  int approach_max_steps_{20};
  double approach_prediction_horizon_s_{0.08};
  double approach_max_target_speed_m_s_{0.30};
  double cartesian_eef_step_m_{0.005};
  double cartesian_max_joint_step_rad_{0.35};
  double linear_approach_velocity_scaling_{0.025};
  double lift_distance_m_{0.10};
  double planning_time_s_{8.0};
  int planning_attempts_{10};
  double velocity_scaling_{0.05};
  double acceleration_scaling_{0.05};
  double position_tolerance_{0.01};
  double orientation_tolerance_{0.05};
  double scene_wait_s_{10.0};
  double trajectory_feedback_tolerance_rad_{0.04};
  double trajectory_feedback_timeout_s_{12.0};
  std::vector<double> real_trajectory_joint_min_;
  std::vector<double> real_trajectory_joint_max_;
  double real_trajectory_limit_margin_rad_{0.005};
  double joint_state_wait_timeout_s_{25.0};
  std::string visual_state_topic_;
  std::string scene_ready_topic_;
  std::string state_topic_;
  std::string emergency_stop_topic_;
  std::string grasp_reacquire_topic_;
  std::string cup_follow_service_;
  std::string servo_stop_service_;
  double grasp_alignment_error_ratio_{0.05};

  std::mutex state_mutex_;
  std::mutex target_mutex_;
  std::mutex feedback_mutex_;
  std::thread worker_;
  std::atomic_bool cancel_requested_{false};
  bool worker_active_{false};
  bool prepared_{false};
  bool grasp_requested_{false};
  bool attached_{false};
  moveit_msgs::msg::CollisionObject cached_cup_;
  geometry_msgs::msg::PointStamped target_point_camera_;
  geometry_msgs::msg::PointStamped target_point_reference_;
  geometry_msgs::msg::PointStamped previous_target_point_reference_;
  geometry_msgs::msg::PointStamped locked_target_reference_;
  geometry_msgs::msg::Vector3Stamped target_size_;
  std::chrono::steady_clock::time_point target_point_received_time_{};
  std::chrono::steady_clock::time_point target_size_received_time_{};
  std::chrono::steady_clock::time_point target_error_received_time_{};
  std::chrono::steady_clock::time_point target_valid_received_time_{};
  std::chrono::steady_clock::time_point depth_valid_received_time_{};
  std::chrono::steady_clock::time_point target_reference_received_time_{};
  std::chrono::steady_clock::time_point previous_target_reference_received_time_{};
  std::chrono::steady_clock::time_point joint_state_received_time_{};
  std::chrono::steady_clock::time_point gripper_feedback_received_time_{};
  double target_error_ratio_{1.0};
  double locked_object_size_m_{0.0};
  double locked_object_min_size_m_{0.0};
  bool target_valid_{false};
  bool depth_valid_{false};
  std::atomic_bool approach_locked_{false};
  std::atomic_bool target_model_locked_{false};
  sensor_msgs::msg::JointState latest_joint_state_;
  sensor_msgs::msg::JointState latest_gripper_feedback_;

  std::shared_ptr<MoveGroupInterface> arm_;
  std::shared_ptr<MoveGroupInterface> gripper_;
  std::shared_ptr<PlanningSceneInterface> planning_scene_;
  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr scene_ready_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr target_pose_publisher_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr current_pose_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr diagnostic_publisher_;
  rclcpp::Publisher<trajectory_msgs::msg::JointTrajectory>::SharedPtr arm_trajectory_publisher_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr gripper_command_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr software_stop_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr reacquire_publisher_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr visual_state_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PolygonStamped>::SharedPtr raw_bbox_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr raw_projection_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PolygonStamped>::SharedPtr qualified_bbox_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr raw_info_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr target_point_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr target_size_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr target_error_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr target_valid_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr depth_valid_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr depth_only_point_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr depth_only_size_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr depth_only_error_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr depth_only_valid_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr gripper_feedback_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr emergency_stop_subscription_;
  rclcpp::Client<std_srvs::srv::SetBool>::SharedPtr cup_follow_client_;
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr servo_stop_client_;
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr adapter_disarm_client_;
  rclcpp::Client<moveit_msgs::srv::GetPositionIK>::SharedPtr compute_ik_client_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr execute_service_;
  std::string last_visual_state_;
};

}  // namespace brain_robot_pick_place

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  const auto options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true);
  const auto node = std::make_shared<brain_robot_pick_place::GraspLiftExecutor>(options);

  std::shared_ptr<rclcpp::Node> gripper_interface_node;
  if (node->SimulationOnly()) {
    // The launch-level __node remap applies to every node created in this
    // process. Disable global arguments here so the auxiliary interface keeps
    // a distinct graph name instead of colliding with the executor node.
    auto gripper_options = rclcpp::NodeOptions()
      .automatically_declare_parameters_from_overrides(true)
      .use_global_arguments(false);
    gripper_interface_node = std::make_shared<rclcpp::Node>(
      "grasp_lift_executor_gripper_interface", gripper_options);
  }
  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
  executor.add_node(node);
  if (gripper_interface_node) {
    executor.add_node(gripper_interface_node);
  }
  std::thread executor_thread([&executor]() {executor.spin();});

  try {
    // Spin before constructing MoveGroupInterface. Keep the simulation gripper
    // interface on its own node: two interfaces sharing one node can block the
    // second constructor while MoveIt action/parameter callbacks are pending.
    auto arm = std::make_shared<brain_robot_pick_place::MoveGroupInterface>(
      node, node->ArmGroup());
    std::shared_ptr<brain_robot_pick_place::MoveGroupInterface> gripper;
    if (node->SimulationOnly()) {
      gripper = std::make_shared<brain_robot_pick_place::MoveGroupInterface>(
        gripper_interface_node, node->GripperGroup());
    }
    auto planning_scene =
      std::make_shared<brain_robot_pick_place::PlanningSceneInterface>();
    node->SetMoveItInterfaces(arm, gripper, planning_scene);
    executor_thread.join();
  } catch (const std::exception & exception) {
    RCLCPP_FATAL(node->get_logger(), "Grasp executor failed: %s", exception.what());
    executor.cancel();
    if (executor_thread.joinable()) {
      executor_thread.join();
    }
  }
  rclcpp::shutdown();
  return 0;
}
