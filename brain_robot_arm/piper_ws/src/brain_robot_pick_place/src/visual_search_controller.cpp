#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <future>
#include <iomanip>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include <builtin_interfaces/msg/duration.hpp>
#include <control_msgs/msg/joint_jog.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/int8.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

namespace brain_robot_pick_place
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
using SteadyClock = std::chrono::steady_clock;
using SteadyTime = SteadyClock::time_point;

enum class ControlState
{
  IDLE,
  PREPARE,
  SEARCH,
  LAST_PATH_REACQUIRE,
  LOCAL_SEARCH,
  ALIGN,
  LEVEL_ALIGN,
  LEVEL_RECOVERY,
  FINAL_ALIGN,
  GRASP_READY,
  STOPPED,
  FAULT,
};

enum class FullSearchPhase
{
  DESCEND,
  BOTTOM_SCAN,
  ASCEND,
  TOP_SCAN,
};

const char * StateName(ControlState state)
{
  switch (state) {
    case ControlState::IDLE: return "IDLE";
    case ControlState::PREPARE: return "PREPARE";
    case ControlState::SEARCH: return "SEARCH";
    case ControlState::LAST_PATH_REACQUIRE: return "LAST_PATH_REACQUIRE";
    case ControlState::LOCAL_SEARCH: return "LOCAL_SEARCH";
    case ControlState::ALIGN: return "ALIGN";
    case ControlState::LEVEL_ALIGN: return "LEVEL_ALIGN";
    case ControlState::LEVEL_RECOVERY: return "LEVEL_RECOVERY";
    case ControlState::FINAL_ALIGN: return "FINAL_ALIGN";
    case ControlState::GRASP_READY: return "GRASP_READY";
    case ControlState::STOPPED: return "STOPPED";
    case ControlState::FAULT: return "FAULT";
  }
  return "UNKNOWN";
}

const char * SearchPhaseName(FullSearchPhase phase)
{
  switch (phase) {
    case FullSearchPhase::DESCEND: return "SEARCH_DOWN";
    case FullSearchPhase::BOTTOM_SCAN: return "BOTTOM_SCAN";
    case FullSearchPhase::ASCEND: return "SEARCH_UP";
    case FullSearchPhase::TOP_SCAN: return "TOP_SCAN";
  }
  return "UNKNOWN";
}

class VisualSearchController : public rclcpp::Node
{
public:
  explicit VisualSearchController(const rclcpp::NodeOptions & options)
  : Node("visual_search_controller", options)
  {
    LoadParameters();
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
    CreateRosInterfaces();
    ValidateParameters();
    PublishStateLocked("WAITING_FOR_START");

    RCLCPP_INFO(
      get_logger(),
      "Visual controller ready: backend=%s, auto motion disabled until ~/start is called.",
      backend_.c_str());
  }

  ~VisualSearchController() override
  {
    cancel_requested_ = true;
    search_plan_cancel_ = true;
    if (move_group_) {
      move_group_->stop();
    }
    std::lock_guard<std::mutex> worker_lock(worker_mutex_);
    if (prepare_thread_.joinable()) {
      prepare_thread_.join();
    }
    if (search_plan_thread_.joinable()) {
      search_plan_thread_.join();
    }
  }

  void SetMoveGroup(const std::shared_ptr<MoveGroupInterface> & move_group)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    move_group_ = move_group;
  }

private:
  struct TargetHistorySample
  {
    geometry_msgs::msg::PointStamped camera_point;
    geometry_msgs::msg::PointStamped reference_point;
    std::unordered_map<std::string, double> joint_positions;
    double error_x_px{0.0};
    double error_y_px{0.0};
    double error_ratio{1.0};
    SteadyTime received_time{};
  };

  template<typename T>
  T ParameterOr(const std::string & name, const T & fallback)
  {
    T value = fallback;
    get_parameter_or(name, value, fallback);
    return value;
  }

  void LoadParameters()
  {
    backend_ = ParameterOr<std::string>("backend", "simulation");
    real_motion_enabled_ = ParameterOr<bool>("real_motion_enabled", false);
    observe_pose_calibrated_ = ParameterOr<bool>("observe_pose_calibrated", true);
    execute_prepare_ = ParameterOr<bool>("execute_prepare", true);
    skip_prepare_ = ParameterOr<bool>("skip_prepare", false);

    joint_names_ = ParameterOr<std::vector<std::string>>(
      "joint_names", {"joint1", "joint2", "joint3", "joint4", "joint5", "joint6"});
    observe_joint_positions_ = ParameterOr<std::vector<double>>(
      "observe_joint_positions", {0.0, 0.98, -0.75, 0.0, 0.30, 0.0});
    reset_joint_positions_ = ParameterOr<std::vector<double>>(
      "reset_joint_positions", {0.0, 0.0, 0.0, 0.0, 0.0, 0.0});
    horizontal_joint_ = ParameterOr<std::string>("horizontal_joint", "joint1");
    vertical_joint_ = ParameterOr<std::string>("vertical_joint", "joint5");
    alignment_assist_enabled_ = ParameterOr<bool>("alignment_assist_enabled", false);
    alignment_assist_horizontal_joint_ = ParameterOr<std::string>(
      "alignment_assist_horizontal_joint", "joint2");
    alignment_assist_vertical_joint_ = ParameterOr<std::string>(
      "alignment_assist_vertical_joint", "joint3");
    horizon_lock_enabled_ = ParameterOr<bool>("horizon_lock_enabled", true);
    if (horizon_lock_enabled_) {
      horizon_joint_names_ = ParameterOr<std::vector<std::string>>(
        "horizon_joint_names", {"joint4", "joint6"});
      horizon_lock_positions_ = ParameterOr<std::vector<double>>(
        "horizon_lock_positions", {0.0, 0.0});
    }
    level_align_enabled_ = ParameterOr<bool>("level_align_enabled", false);
    direct_grasp_after_align_ = ParameterOr<bool>("direct_grasp_after_align", false);
    freeze_grasp_tracking_ = ParameterOr<bool>("freeze_grasp_tracking", false);
    level_joint2_name_ = ParameterOr<std::string>("level_joint2_name", "joint2");
    level_joint3_name_ = ParameterOr<std::string>("level_joint3_name", "joint3");
    level_joint2_target_ = ParameterOr<double>("level_joint2_target", 1.35);
    level_joint3_target_ = ParameterOr<double>("level_joint3_target", -0.18);
    level_joint5_target_ = ParameterOr<double>("level_joint5_target", -1.10);
    level_joint2_speed_ = ParameterOr<double>("level_joint2_speed", 0.08);
    level_joint3_speed_ = ParameterOr<double>("level_joint3_speed", 0.30);
    level_joint5_speed_ = ParameterOr<double>("level_joint5_speed", 0.36);
    level_target_lost_joint5_speed_ = ParameterOr<double>(
      "level_target_lost_joint5_speed", 0.40);
    level_joint2_vertical_sign_ = ParameterOr<double>("level_joint2_vertical_sign", 1.0);
    level_joint3_vertical_sign_ = ParameterOr<double>("level_joint3_vertical_sign", -1.0);
    level_joint23_vertical_kp_ = ParameterOr<double>("level_joint23_vertical_kp", 0.00015);
    final_j5_negative_min_ = ParameterOr<double>("final_j5_negative_min", -1.18);
    final_j5_negative_max_ = ParameterOr<double>("final_j5_negative_max", -0.95);

    horizontal_error_sign_ = ParameterOr<double>("horizontal_error_sign", 1.0);
    vertical_error_sign_ = ParameterOr<double>("vertical_error_sign", 1.0);

    horizontal_search_min_ = ParameterOr<double>("horizontal_search_min", -0.90);
    horizontal_search_max_ = ParameterOr<double>("horizontal_search_max", 0.90);
    vertical_search_min_ = ParameterOr<double>("vertical_search_min", -0.60);
    vertical_search_max_ = ParameterOr<double>("vertical_search_max", 0.95);
    search_bounds_relative_to_start_ = ParameterOr<bool>(
      "search_bounds_relative_to_start", false);
    full_search_horizontal_range_ = ParameterOr<double>(
      "full_search_horizontal_range", 0.12);
    full_search_vertical_range_ = ParameterOr<double>(
      "full_search_vertical_range", 0.10);
    local_horizontal_range_ = ParameterOr<double>("local_horizontal_range", 0.08);
    local_vertical_range_ = ParameterOr<double>("local_vertical_range", 0.06);
    last_path_prediction_horizon_s_ = ParameterOr<double>(
      "last_path_prediction_horizon_s", 0.25);
    last_path_prediction_max_speed_m_s_ = ParameterOr<double>(
      "last_path_prediction_max_speed_m_s", 0.40);
    last_path_reacquire_max_joint_step_rad_ = ParameterOr<double>(
      "last_path_reacquire_max_joint_step_rad", 0.60);
    last_path_reacquire_max_steps_ = ParameterOr<int>(
      "last_path_reacquire_max_steps", 2);
    last_path_min_predicted_depth_m_ = ParameterOr<double>(
      "last_path_min_predicted_depth_m", 0.05);
    horizontal_search_speed_ = ParameterOr<double>("horizontal_search_speed", 0.12);
    vertical_search_speed_ = ParameterOr<double>("vertical_search_speed", 0.08);
    joint_position_tolerance_ = ParameterOr<double>("joint_position_tolerance", 0.01);
    search_timeout_s_ = ParameterOr<double>("search_timeout_s", 75.0);
    local_search_timeout_s_ = ParameterOr<double>("local_search_timeout_s", 5.0);
    search_planning_step_rad_ = ParameterOr<double>("search_planning_step_rad", 0.08);
    search_planning_time_s_ = ParameterOr<double>("search_planning_time_s", 0.50);
    search_planning_attempts_ = ParameterOr<int>("search_planning_attempts", 2);
    search_planning_velocity_scaling_ = ParameterOr<double>(
      "search_planning_velocity_scaling", 0.05);
    search_planning_acceleration_scaling_ = ParameterOr<double>(
      "search_planning_acceleration_scaling", 0.05);
    search_segment_timeout_s_ = ParameterOr<double>("search_segment_timeout_s", 12.0);

    target_timeout_s_ = ParameterOr<double>("target_timeout_s", 0.60);
    target_loss_grace_s_ = ParameterOr<double>("target_loss_grace_s", 0.80);
    joint_state_timeout_s_ = ParameterOr<double>("joint_state_timeout_s", 0.50);
    target_acquire_frames_ = ParameterOr<int>("target_acquire_frames", 3);
    align_stable_frames_ = ParameterOr<int>("align_stable_frames", 5);
    target_acquire_error_ratio_ = ParameterOr<double>("target_acquire_error_ratio", 0.20);
    horizontal_kp_ = ParameterOr<double>("horizontal_kp", 0.0008);
    vertical_kp_ = ParameterOr<double>("vertical_kp", 0.0008);
    align_joint_speed_limit_ = ParameterOr<double>("align_joint_speed_limit", 0.08);
    alignment_assist_horizontal_ratio_ = ParameterOr<double>(
      "alignment_assist_horizontal_ratio", 0.20);
    alignment_assist_vertical_ratio_ = ParameterOr<double>(
      "alignment_assist_vertical_ratio", 0.20);
    alignment_assist_horizontal_sign_ = ParameterOr<double>(
      "alignment_assist_horizontal_sign", 1.0);
    alignment_assist_vertical_sign_ = ParameterOr<double>(
      "alignment_assist_vertical_sign", 1.0);
    alignment_assist_speed_limit_ = ParameterOr<double>(
      "alignment_assist_speed_limit", 0.03);
    horizon_lock_kp_ = ParameterOr<double>("horizon_lock_kp", 1.0);
    horizon_lock_speed_limit_ = ParameterOr<double>("horizon_lock_speed_limit", 0.05);
    horizon_lock_tolerance_ = ParameterOr<double>("horizon_lock_tolerance", 0.02);

    control_rate_hz_ = ParameterOr<double>("control_rate_hz", 20.0);
    prepare_velocity_scaling_ = ParameterOr<double>("prepare_velocity_scaling", 0.05);
    prepare_acceleration_scaling_ = ParameterOr<double>("prepare_acceleration_scaling", 0.05);
    prepare_planning_time_s_ = ParameterOr<double>("prepare_planning_time_s", 10.0);
    prepare_execution_timeout_s_ = ParameterOr<double>("prepare_execution_timeout_s", 45.0);
    prepare_max_joint_step_rad_ = ParameterOr<double>("prepare_max_joint_step_rad", 0.08);

    error_topic_ = ParameterOr<std::string>(
      "error_topic", "/brain_robot_vision/pixel_error");
    target_valid_topic_ = ParameterOr<std::string>(
      "target_valid_topic", "/brain_robot_vision/target_valid");
    target_point_topic_ = ParameterOr<std::string>(
      "target_point_topic", "/brain_robot_vision/target_point_camera");
    target_history_reference_frame_ = ParameterOr<std::string>(
      "target_history_reference_frame", "base_link");
    target_history_topic_ = ParameterOr<std::string>(
      "target_history_topic", "/brain_robot_visual_control/target_history");
    target_history_window_s_ = ParameterOr<double>("target_history_window_s", 0.40);
    candidate_error_topic_ = ParameterOr<std::string>(
      "candidate_error_topic", "/brain_robot_vision/color_candidate_error");
    candidate_valid_topic_ = ParameterOr<std::string>(
      "candidate_valid_topic", "/brain_robot_vision/color_candidate_valid");
    joint_state_topic_ = ParameterOr<std::string>("joint_state_topic", "/joint_states");
    filtered_point_cloud_topic_ = ParameterOr<std::string>(
      "filtered_point_cloud_topic", "/brain_robot_vision/filtered_points");
    planning_scene_timeout_s_ = ParameterOr<double>("planning_scene_timeout_s", 2.5);
    require_fresh_planning_scene_ = ParameterOr<bool>(
      "require_fresh_planning_scene", true);
    joint_command_topic_ = ParameterOr<std::string>(
      "joint_command_topic", "/servo_node/delta_joint_cmds");
    servo_status_topic_ = ParameterOr<std::string>(
      "servo_status_topic", "/servo_node/status");
    servo_start_service_ = ParameterOr<std::string>(
      "servo_start_service", "/servo_node/start_servo");
    servo_stop_service_ = ParameterOr<std::string>(
      "servo_stop_service", "/servo_node/stop_servo");
    emergency_stop_topic_ = ParameterOr<std::string>(
      "emergency_stop_topic", "/brain_robot_control/emergency_stop");
    adapter_armed_topic_ = ParameterOr<std::string>(
      "adapter_armed_topic", "/brain_robot_control/adapter_armed");
    grasp_reacquire_topic_ = ParameterOr<std::string>(
      "grasp_reacquire_topic", "/brain_robot_grasp/reacquire");
  }

  void CreateRosInterfaces()
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    error_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      error_topic_, sensor_qos,
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        error_x_px_ = message->vector.x;
        error_y_px_ = message->vector.y;
        target_error_ratio_ = message->vector.z;
        error_received_time_ = SteadyClock::now();
        if ((state_ == ControlState::ALIGN || state_ == ControlState::LEVEL_ALIGN ||
          state_ == ControlState::FINAL_ALIGN) && target_valid_ &&
          target_error_ratio_ <= target_acquire_error_ratio_)
        {
          ++aligned_frames_;
        } else if (state_ == ControlState::ALIGN || state_ == ControlState::LEVEL_ALIGN ||
          state_ == ControlState::FINAL_ALIGN)
        {
          aligned_frames_ = 0;
        }
      });
    target_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      target_valid_topic_, sensor_qos,
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        bool record_history = false;
        {
          std::lock_guard<std::mutex> lock(mutex_);
          target_valid_ = message->data;
          if (target_valid_) {
            ++target_valid_frames_;
            last_target_valid_time_ = SteadyClock::now();
            record_history = Fresh(target_point_received_time_, target_timeout_s_) &&
              Fresh(error_received_time_, target_timeout_s_);
          } else {
            target_valid_frames_ = 0;
            aligned_frames_ = 0;
          }
        }
        if (record_history) {
          RecordTargetHistorySample();
        }
      });
    target_point_subscription_ = create_subscription<geometry_msgs::msg::PointStamped>(
      target_point_topic_, sensor_qos,
      [this](const geometry_msgs::msg::PointStamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        target_point_camera_ = *message;
        target_point_received_time_ = SteadyClock::now();
      });
    candidate_error_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      candidate_error_topic_, sensor_qos,
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        candidate_error_x_px_ = message->vector.x;
        candidate_error_y_px_ = message->vector.y;
        candidate_error_ratio_ = message->vector.z;
        candidate_error_received_time_ = SteadyClock::now();
      });
    candidate_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      candidate_valid_topic_, sensor_qos,
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        candidate_valid_ = message->data;
        if (!candidate_valid_) {
          candidate_error_received_time_ = SteadyTime{};
        }
      });
    joint_state_subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      joint_state_topic_, sensor_qos,
      [this](const sensor_msgs::msg::JointState::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        const std::size_t count = std::min(message->name.size(), message->position.size());
        for (std::size_t index = 0; index < count; ++index) {
          joint_positions_[message->name[index]] = message->position[index];
        }
        joint_state_time_ = SteadyClock::now();
      });
    filtered_point_cloud_subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      filtered_point_cloud_topic_, sensor_qos,
      [this](const sensor_msgs::msg::PointCloud2::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        point_cloud_received_time_ = SteadyClock::now();
        point_cloud_count_ = static_cast<std::size_t>(message->width) *
          static_cast<std::size_t>(message->height);
        planning_scene_stale_reported_ = false;
      });
    servo_status_subscription_ = create_subscription<std_msgs::msg::Int8>(
      servo_status_topic_, rclcpp::SystemDefaultsQoS(),
      [this](const std_msgs::msg::Int8::SharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        servo_status_seen_ = true;
        servo_status_ = message->data;
      });
    emergency_stop_subscription_ = create_subscription<std_msgs::msg::Bool>(
      emergency_stop_topic_, rclcpp::QoS(10),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        if (!message->data) {
          return;
        }
        {
          std::lock_guard<std::mutex> lock(mutex_);
          StopLocked(ControlState::FAULT, "EOG_OR_EXTERNAL_EMERGENCY_STOP");
        }
        cancel_requested_ = true;
        if (move_group_) {
          move_group_->stop();
        }
      });
    adapter_armed_subscription_ = create_subscription<std_msgs::msg::Bool>(
      adapter_armed_topic_, rclcpp::QoS(10),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        bool stop_move_group = false;
        {
          std::lock_guard<std::mutex> lock(mutex_);
          if (message->data) {
            adapter_was_armed_ = true;
            return;
          }
          if (backend_ == "piper" && adapter_was_armed_ &&
            state_ != ControlState::IDLE && state_ != ControlState::STOPPED &&
            state_ != ControlState::FAULT)
          {
            StopLocked(ControlState::FAULT, "PIPER_ADAPTER_DISARMED");
            stop_move_group = true;
          }
        }
        if (stop_move_group) {
          cancel_requested_ = true;
          if (move_group_) {
            move_group_->stop();
          }
        }
      });
    grasp_reacquire_subscription_ = create_subscription<std_msgs::msg::Bool>(
      grasp_reacquire_topic_, rclcpp::QoS(10),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        if (!message->data) {
          return;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        if (state_ != ControlState::GRASP_READY && state_ != ControlState::FAULT) {
          return;
        }
        aligned_frames_ = 0;
        cancel_requested_ = false;
        if (servo_start_client_->service_is_ready()) {
          servo_start_client_->async_send_request(
            std::make_shared<std_srvs::srv::Trigger::Request>());
        }
        PublishControlDetailLocked("PHASE=ALIGN REACQUIRE_AFTER_GRASP_TARGET_SHIFT");
        SetStateLocked(ControlState::ALIGN, "GRASP_TARGET_SHIFT_REACQUIRE");
      });
    joint_command_publisher_ = create_publisher<control_msgs::msg::JointJog>(
      joint_command_topic_, rclcpp::QoS(10));
    arm_trajectory_publisher_ = create_publisher<trajectory_msgs::msg::JointTrajectory>(
      "/brain_robot_grasp/arm_trajectory", rclcpp::QoS(1));
    state_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_visual_control/state", rclcpp::QoS(1).transient_local());
    reason_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_visual_control/reason", rclcpp::QoS(1).transient_local());
    search_direction_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_visual_control/search_direction", rclcpp::QoS(1).transient_local());
    target_history_publisher_ = create_publisher<std_msgs::msg::String>(
      target_history_topic_, rclcpp::QoS(1).transient_local());
    command_diagnostic_publisher_ = create_publisher<std_msgs::msg::String>(
      "/brain_robot_visual_control/command_diagnostic", rclcpp::QoS(1).transient_local());

    servo_start_client_ = create_client<std_srvs::srv::Trigger>(servo_start_service_);
    servo_stop_client_ = create_client<std_srvs::srv::Trigger>(servo_stop_service_);
    start_service_ = create_service<std_srvs::srv::Trigger>(
      "~/start",
      [this](
        const std_srvs::srv::Trigger::Request::SharedPtr,
        std_srvs::srv::Trigger::Response::SharedPtr response)
      {
        HandleStart(response);
      });
    stop_service_ = create_service<std_srvs::srv::Trigger>(
      "~/stop",
      [this](
        const std_srvs::srv::Trigger::Request::SharedPtr,
        std_srvs::srv::Trigger::Response::SharedPtr response)
      {
        {
          std::lock_guard<std::mutex> lock(mutex_);
          reset_requested_ = false;
          StopLocked(ControlState::STOPPED, "USER_STOP");
        }
        cancel_requested_ = true;
        if (move_group_) {
          move_group_->stop();
        }
        response->success = true;
        response->message = "Visual motion stopped.";
      });
    reset_service_ = create_service<std_srvs::srv::Trigger>(
      "~/reset",
      [this](
        const std_srvs::srv::Trigger::Request::SharedPtr,
        std_srvs::srv::Trigger::Response::SharedPtr response)
      {
        {
          std::lock_guard<std::mutex> lock(mutex_);
          if (!configuration_ok_ || !move_group_ || !real_motion_enabled_ ||
            !JointStateFreshLocked()) {
            response->success = false;
            response->message = "Controller is not ready for reset.";
            return;
          }
          cancel_requested_ = false;
          reset_requested_ = true;
          target_valid_frames_ = 0;
          aligned_frames_ = 0;
          SetStateLocked(ControlState::PREPARE, "RESET_AUTHORIZED");
        }
        LaunchPrepareWorker();
        response->success = true;
        response->message = "Zero reset started; the arm will stop at all joint angles 0 rad.";
      });

    const auto control_period = std::chrono::duration<double>(1.0 / control_rate_hz_);
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(control_period),
      [this]() {ControlTick();});
  }

  void ValidateParameters()
  {
    configuration_ok_ = true;
    if (joint_names_.size() != observe_joint_positions_.size() ||
      joint_names_.size() != reset_joint_positions_.size() || joint_names_.empty()) {
      RCLCPP_ERROR(
        get_logger(),
        "joint_names, observe_joint_positions and reset_joint_positions must have equal non-zero length.");
      configuration_ok_ = false;
    }
    const auto contains_joint = [this](const std::string & name) {
        return std::find(joint_names_.begin(), joint_names_.end(), name) != joint_names_.end();
      };
    if (!contains_joint(horizontal_joint_) || !contains_joint(vertical_joint_) ||
      !contains_joint(level_joint2_name_) || !contains_joint(level_joint3_name_))
    {
      RCLCPP_ERROR(get_logger(), "Search joint mapping contains an unknown joint name.");
      configuration_ok_ = false;
    }
    if (horizon_joint_names_.size() != horizon_lock_positions_.size())
    {
      RCLCPP_ERROR(
        get_logger(), "horizon_joint_names and horizon_lock_positions must have equal length.");
      configuration_ok_ = false;
    }
    std::vector<std::string> controlled_joints{horizontal_joint_, vertical_joint_};
    for (const auto & joint_name : horizon_joint_names_) {
      if (!contains_joint(joint_name)) {
        RCLCPP_ERROR(get_logger(), "Horizon lock contains an unknown joint name: %s.",
          joint_name.c_str());
        configuration_ok_ = false;
      }
      controlled_joints.push_back(joint_name);
    }
    std::sort(controlled_joints.begin(), controlled_joints.end());
    if (std::adjacent_find(controlled_joints.begin(), controlled_joints.end()) !=
      controlled_joints.end())
    {
      RCLCPP_ERROR(get_logger(), "Horizontal, vertical and horizon-lock joints must be distinct.");
      configuration_ok_ = false;
    }
    if (alignment_assist_enabled_ &&
      (alignment_assist_horizontal_joint_ == alignment_assist_vertical_joint_ ||
      alignment_assist_horizontal_joint_ == horizontal_joint_ ||
      alignment_assist_horizontal_joint_ == vertical_joint_ ||
      alignment_assist_vertical_joint_ == horizontal_joint_ ||
      alignment_assist_vertical_joint_ == vertical_joint_ ||
      alignment_assist_horizontal_ratio_ < 0.0 || alignment_assist_vertical_ratio_ < 0.0 ||
      alignment_assist_speed_limit_ <= 0.0))
    {
      RCLCPP_ERROR(get_logger(), "Alignment-assist joint mapping or speed is invalid.");
      configuration_ok_ = false;
    }
    if (level_joint2_name_ == level_joint3_name_ || level_joint2_name_ == horizontal_joint_ ||
      level_joint3_name_ == horizontal_joint_ || level_joint2_name_ == vertical_joint_ ||
      level_joint3_name_ == vertical_joint_ || level_joint2_speed_ <= 0.0 ||
      level_joint3_speed_ <= 0.0 || level_joint5_speed_ <= 0.0 ||
      level_target_lost_joint5_speed_ <= 0.0 ||
      level_joint23_vertical_kp_ < 0.0 || final_j5_negative_min_ >= final_j5_negative_max_ ||
      final_j5_negative_max_ >= 0.0 || level_joint5_target_ < final_j5_negative_min_ ||
      level_joint5_target_ > final_j5_negative_max_)
    {
      RCLCPP_ERROR(get_logger(), "Level-align joint mapping or speed is invalid.");
      configuration_ok_ = false;
    }
    if (control_rate_hz_ <= 0.0 ||
      horizontal_search_min_ >= horizontal_search_max_ ||
      vertical_search_min_ >= vertical_search_max_ ||
      local_horizontal_range_ <= 0.0 || local_vertical_range_ <= 0.0 ||
      full_search_horizontal_range_ <= 0.0 || full_search_vertical_range_ <= 0.0 ||
      horizontal_search_speed_ <= 0.0 || vertical_search_speed_ <= 0.0 ||
      prepare_execution_timeout_s_ <= 0.0 || prepare_max_joint_step_rad_ <= 0.0 ||
      target_acquire_error_ratio_ <= 0.0 || target_acquire_error_ratio_ > 1.0 ||
      align_stable_frames_ < 1 || target_history_window_s_ <= 0.0 ||
      last_path_prediction_horizon_s_ < 0.0 ||
      last_path_prediction_max_speed_m_s_ <= 0.0 ||
      last_path_reacquire_max_joint_step_rad_ <= 0.0 ||
      last_path_reacquire_max_steps_ < 1 ||
      last_path_min_predicted_depth_m_ <= 0.0 ||
      target_loss_grace_s_ < 0.0 ||
      search_planning_step_rad_ <= 0.0 || search_planning_time_s_ <= 0.0 ||
      search_planning_attempts_ < 1 || search_planning_velocity_scaling_ <= 0.0 ||
      search_planning_velocity_scaling_ > 1.0 ||
      search_planning_acceleration_scaling_ <= 0.0 ||
      search_planning_acceleration_scaling_ > 1.0 || search_segment_timeout_s_ <= 0.0 ||
      filtered_point_cloud_topic_.empty() || planning_scene_timeout_s_ <= 0.0 ||
      target_history_reference_frame_.empty() || target_history_topic_.empty())
    {
      RCLCPP_ERROR(
        get_logger(), "Search bounds, speeds, target history, rate or target-acquisition ratio are invalid.");
      configuration_ok_ = false;
    }
    if (backend_ != "simulation" && backend_ != "piper") {
      RCLCPP_ERROR(get_logger(), "backend must be simulation or piper.");
      configuration_ok_ = false;
    }
  }

  void HandleStart(const std_srvs::srv::Trigger::Response::SharedPtr & response)
  {
    JoinCompletedSearchPlanThread();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (!configuration_ok_) {
        response->success = false;
        response->message = "Controller parameters are invalid; see the node log.";
        return;
      }
      if (!move_group_) {
        response->success = false;
        response->message = "MoveGroup interface is not ready.";
        return;
      }
      if (backend_ == "piper" && (!real_motion_enabled_ || !observe_pose_calibrated_)) {
        response->success = false;
        response->message =
          "Physical motion remains locked: calibrate the observation pose and enable real motion.";
        return;
      }
      if (state_ == ControlState::PREPARE || state_ == ControlState::SEARCH ||
        state_ == ControlState::LOCAL_SEARCH || state_ == ControlState::ALIGN ||
        state_ == ControlState::LEVEL_ALIGN || state_ == ControlState::FINAL_ALIGN)
      {
        response->success = false;
        response->message = "Visual motion is already active.";
        return;
      }
      if (!JointStateFreshLocked()) {
        response->success = false;
        response->message = "No fresh joint state; the robot controller is not ready.";
        return;
      }

      cancel_requested_ = false;
      full_search_retries_ = 0;
      target_valid_frames_ = 0;
      aligned_frames_ = 0;
      SetStateLocked(ControlState::PREPARE, "START_AUTHORIZED");
    }

    LaunchPrepareWorker();
    response->success = true;
    response->message = "PREPARE started; J2/J3 will move to the configured observation pose.";
  }

  void LaunchPrepareWorker()
  {
    std::lock_guard<std::mutex> worker_lock(worker_mutex_);
    if (prepare_thread_.joinable()) {
      prepare_thread_.join();
    }
    prepare_thread_ = std::thread([this]() {PrepareWorker();});
  }

  void PrepareWorker()
  {
    // The PiPER adapter executes the fixed reset/observation trajectory
    // directly.  Humble Servo's legacy stop service can accept a request but
    // never reply, so it must not hold up the real-arm preparation sequence.
    if (backend_ != "piper") {
      CallServoService(servo_stop_client_, "stop", false);
    }
    if (cancel_requested_) {
      return;
    }

    if (skip_prepare_) {
      if (
        backend_ != "piper" &&
        !CallServoService(servo_start_client_, "start", true))
      {
        FailPrepare("SERVO_START_FAILED");
        return;
      }
      std::lock_guard<std::mutex> lock(mutex_);
      if (cancel_requested_ || state_ != ControlState::PREPARE) {
        return;
      }
      servo_status_seen_ = false;
      servo_status_ = -1;
      const auto horizontal = CurrentJointLocked(horizontal_joint_);
      const auto vertical = CurrentJointLocked(vertical_joint_);
      if (!horizontal || !vertical) {
        StopLocked(ControlState::FAULT, "SEARCH_JOINT_STATE_MISSING");
        return;
      }
      InitializeSearchLocked(false, *horizontal, *vertical);
      SetStateLocked(ControlState::SEARCH, "CURRENT_POSE_ACCEPTED");
      return;
    }

    bool zero_reset = false;
    std::vector<double> prepare_positions;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      zero_reset = reset_requested_;
      prepare_positions = zero_reset ? reset_joint_positions_ : observe_joint_positions_;
    }
    std::map<std::string, double> target;
    for (std::size_t index = 0; index < joint_names_.size(); ++index) {
      target[joint_names_[index]] = prepare_positions[index];
    }

    if (backend_ == "piper") {
      // The real adapter is the physical trajectory executor.  Do not block
      // on MoveIt's planning/execution services for the fixed simulation
      // observation pose; publish a slow, explicit current->target trajectory.
      trajectory_msgs::msg::JointTrajectory trajectory;
      trajectory.joint_names = joint_names_;
      double max_delta = 0.0;
      bool missing_joint_state = false;
      std::vector<double> current_positions;
      {
        std::lock_guard<std::mutex> lock(mutex_);
        for (std::size_t index = 0; index < joint_names_.size(); ++index) {
          const auto current = CurrentJointLocked(joint_names_[index]);
          if (!current) {
            missing_joint_state = true;
            break;
          }
          current_positions.push_back(*current);
          max_delta = std::max(max_delta,
            std::abs(prepare_positions[index] - *current));
        }
      }
      if (missing_joint_state) {
        FailPrepare("PREPARE_JOINT_STATE_MISSING");
        return;
      }
      const double duration_s = std::max(20.0, max_delta / 0.02);
      auto make_duration = [](double seconds) {
        builtin_interfaces::msg::Duration duration;
        duration.sec = static_cast<int32_t>(std::floor(seconds));
        duration.nanosec = static_cast<uint32_t>(
          std::llround((seconds - static_cast<double>(duration.sec)) * 1e9));
        if (duration.nanosec >= 1000000000U) {
          ++duration.sec;
          duration.nanosec -= 1000000000U;
        }
        return duration;
      };
      const std::size_t segment_count = std::max<std::size_t>(
        1U, static_cast<std::size_t>(std::ceil(max_delta / prepare_max_joint_step_rad_)));
      trajectory.points.resize(segment_count + 1U);
      for (std::size_t step = 0; step <= segment_count; ++step) {
        const double ratio = static_cast<double>(step) / static_cast<double>(segment_count);
        auto & point = trajectory.points[step];
        point.positions.reserve(joint_names_.size());
        for (std::size_t index = 0; index < joint_names_.size(); ++index) {
          point.positions.push_back(
            current_positions[index] +
            (prepare_positions[index] - current_positions[index]) * ratio);
        }
        point.time_from_start = make_duration(duration_s * ratio);
      }

      arm_trajectory_publisher_->publish(trajectory);
      PublishTrajectoryDiagnostic(
        zero_reset ? "ZERO_RESET_TRAJECTORY" : "OBSERVE_PREPARE_TRAJECTORY", trajectory);
      RCLCPP_INFO(
        get_logger(),
        "Published direct real-arm prepare trajectory (%0.1f s, %zu points, max step %.3f rad).",
        duration_s, trajectory.points.size(), prepare_max_joint_step_rad_);

      const auto deadline = SteadyClock::now() +
        std::chrono::duration<double>(prepare_execution_timeout_s_);
      bool reached = false;
      while (!cancel_requested_ && SteadyClock::now() < deadline) {
        {
          std::lock_guard<std::mutex> lock(mutex_);
          reached = true;
          for (std::size_t index = 0; index < joint_names_.size(); ++index) {
            const auto current = CurrentJointLocked(joint_names_[index]);
            if (!current || std::abs(*current - prepare_positions[index]) >
              joint_position_tolerance_)
            {
              reached = false;
              break;
            }
          }
        }
        if (reached) {
          break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
      if (!reached || cancel_requested_) {
        double max_error = 0.0;
        std::string worst_joint = "none";
        {
          std::lock_guard<std::mutex> lock(mutex_);
          for (std::size_t index = 0; index < joint_names_.size(); ++index) {
            const auto current = CurrentJointLocked(joint_names_[index]);
            if (!current) {
              continue;
            }
            const double error = std::abs(*current - prepare_positions[index]);
            if (error > max_error) {
              max_error = error;
              worst_joint = joint_names_[index];
            }
          }
        }
        RCLCPP_ERROR(
          get_logger(),
          "Prepare execution did not converge: max_joint_error=%.6f rad worst_joint=%s",
          max_error, worst_joint.c_str());
        FailPrepare(cancel_requested_ ? "PREPARE_CANCELLED" : "PREPARE_EXECUTION_FAILED");
        return;
      }
      if (zero_reset) {
        std::lock_guard<std::mutex> lock(mutex_);
        reset_requested_ = false;
        SetStateLocked(ControlState::STOPPED, "RESET_COMPLETE");
        return;
      }
    } else {
      const auto move_group = move_group_;
      if (!move_group) {
        FailPrepare("MOVE_GROUP_NOT_READY");
        return;
      }
      move_group->setStartStateToCurrentState();
      move_group->setPlanningTime(prepare_planning_time_s_);
      move_group->setMaxVelocityScalingFactor(prepare_velocity_scaling_);
      move_group->setMaxAccelerationScalingFactor(prepare_acceleration_scaling_);
      if (!move_group->setJointValueTarget(target)) {
        FailPrepare("OBSERVE_POSE_REJECTED");
        return;
      }
      MoveGroupInterface::Plan plan;
      const bool planned = static_cast<bool>(move_group->plan(plan));
      if (!planned || cancel_requested_) {
        FailPrepare(cancel_requested_ ? "PREPARE_CANCELLED" : "PREPARE_PLAN_FAILED");
        return;
      }
      RCLCPP_INFO(get_logger(), "PREPARE plan succeeded with %zu points.",
        plan.trajectory_.joint_trajectory.points.size());
      if (!execute_prepare_) {
        FailPrepare("PREPARE_PLAN_ONLY_COMPLETE");
        return;
      }
      if (!static_cast<bool>(move_group->execute(plan)) || cancel_requested_) {
        FailPrepare(cancel_requested_ ? "PREPARE_CANCELLED" : "PREPARE_EXECUTION_FAILED");
        return;
      }
    }

    if (
      backend_ != "piper" &&
      !CallServoService(servo_start_client_, "start", true))
    {
      FailPrepare("SERVO_START_FAILED");
      return;
    }

    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (cancel_requested_ || state_ != ControlState::PREPARE) {
        return;
      }
      servo_status_seen_ = false;
      servo_status_ = -1;
      const auto horizontal = CurrentJointLocked(horizontal_joint_);
      const auto vertical = CurrentJointLocked(vertical_joint_);
      if (!horizontal || !vertical) {
        StopLocked(ControlState::FAULT, "SEARCH_JOINT_STATE_MISSING");
        return;
      }
      InitializeSearchLocked(false, *horizontal, *vertical);
      SetStateLocked(ControlState::SEARCH, "OBSERVE_POSE_REACHED");
    }
  }

  bool CallServoService(
    const rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr & client,
    const char * action,
    bool require_success)
  {
    if (!client->wait_for_service(std::chrono::seconds(5))) {
      RCLCPP_ERROR(get_logger(), "Servo %s service is unavailable.", action);
      return false;
    }
    auto future = client->async_send_request(std::make_shared<std_srvs::srv::Trigger::Request>());
    if (future.wait_for(std::chrono::seconds(5)) != std::future_status::ready) {
      RCLCPP_ERROR(get_logger(), "Servo %s service timed out.", action);
      return false;
    }
    const auto response = future.get();
    if (require_success && !response->success) {
      RCLCPP_ERROR(
        get_logger(), "Servo %s request failed: %s", action, response->message.c_str());
      return false;
    }
    return true;
  }

  void FailPrepare(const std::string & reason)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (state_ == ControlState::PREPARE) {
      StopLocked(
        reason == "PREPARE_PLAN_ONLY_COMPLETE" ? ControlState::STOPPED : ControlState::FAULT,
        reason);
    }
  }

  void ControlTick()
  {
    JoinCompletedSearchPlanThread();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (!IsMotionState(state_)) {
        return;
      }
      if (state_ == ControlState::PREPARE) {
        return;
      }
      if (!JointStateFreshLocked()) {
        StopLocked(ControlState::FAULT, "JOINT_STATE_TIMEOUT");
        return;
      }
      if (servo_status_seen_ && (servo_status_ == 2 || servo_status_ == 4 || servo_status_ == 5)) {
        StopLocked(ControlState::FAULT, "MOVEIT_SERVO_HARD_STOP_" + std::to_string(servo_status_));
        return;
      }

      switch (state_) {
        case ControlState::SEARCH:
          HandleSearchLocked(false);
          break;
        case ControlState::LAST_PATH_REACQUIRE:
          HandleLastPathReacquireLocked();
          break;
        case ControlState::LOCAL_SEARCH:
          HandleSearchLocked(true);
          break;
        case ControlState::ALIGN:
          HandleAlignLocked();
          break;
        case ControlState::GRASP_READY:
          HandleGraspReadyLocked();
          break;
        case ControlState::LEVEL_ALIGN:
          HandleLevelAlignLocked();
          break;
        case ControlState::LEVEL_RECOVERY:
          HandleLevelRecoveryLocked();
          break;
        case ControlState::FINAL_ALIGN:
          HandleFinalAlignLocked();
          break;
        default:
          break;
      }
    }
  }

  void JoinCompletedSearchPlanThread()
  {
    if (!search_plan_done_.load()) {
      return;
    }
    std::lock_guard<std::mutex> worker_lock(worker_mutex_);
    if (search_plan_thread_.joinable() && search_plan_done_.load()) {
      search_plan_thread_.join();
    }
  }

  bool RequestPlannedSearchLocked(
    double desired_horizontal, double desired_vertical, const std::string & source)
  {
    if (backend_ != "piper" || !real_motion_enabled_) {
      return false;
    }
    if (!search_plan_done_.load()) {
      return true;
    }
    if (require_fresh_planning_scene_ &&
      (point_cloud_count_ == 0U || !Fresh(point_cloud_received_time_, planning_scene_timeout_s_))) {
      PublishZeroLocked();
      if (!planning_scene_stale_reported_) {
        PublishControlDetailLocked("SEARCH_HOLD_PLANNING_SCENE_STALE");
        planning_scene_stale_reported_ = true;
      }
      return true;
    }
    if (search_plan_active_ || search_trajectory_active_) {
      return true;
    }
    if (SteadyClock::now() < search_plan_retry_time_) {
      PublishZeroLocked();
      return true;
    }
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "SEARCH_JOINT_STATE_MISSING");
      return true;
    }
    const double horizontal_delta = std::clamp(
      desired_horizontal - *horizontal, -search_planning_step_rad_, search_planning_step_rad_);
    const double vertical_delta = std::clamp(
      desired_vertical - *vertical, -search_planning_step_rad_, search_planning_step_rad_);
    const double target_horizontal = *horizontal + horizontal_delta;
    const double target_vertical = *vertical + vertical_delta;
    if (Reached(*horizontal, target_horizontal) && Reached(*vertical, target_vertical)) {
      return true;
    }

    const auto move_group = move_group_;
    if (!move_group) {
      StopLocked(ControlState::FAULT, "SEARCH_MOVE_GROUP_NOT_READY");
      return true;
    }
    std::unordered_map<std::string, double> start_positions = joint_positions_;
    search_plan_active_ = true;
    search_plan_done_ = false;
    search_plan_cancel_ = false;
    const std::string plan_source = source;
    search_plan_thread_ = std::thread(
      [this, move_group, start_positions, target_horizontal, target_vertical, plan_source]() {
        PlanSearchSegment(
          move_group, start_positions, target_horizontal, target_vertical, plan_source);
      });
    return true;
  }

  void PlanSearchSegment(
    const std::shared_ptr<MoveGroupInterface> & move_group,
    const std::unordered_map<std::string, double> & start_positions,
    double target_horizontal, double target_vertical, const std::string & source)
  {
    bool success = false;
    bool scene_fresh = false;
    trajectory_msgs::msg::JointTrajectory trajectory;
    std::string failure_reason = "SEARCH_PLAN_FAILED";
    if (!search_plan_cancel_ && move_group) {
      std::map<std::string, double> target;
      bool complete_start = true;
      for (const auto & joint_name : joint_names_) {
        const auto found = start_positions.find(joint_name);
        if (found == start_positions.end() || !std::isfinite(found->second)) {
          complete_start = false;
          break;
        }
        target[joint_name] = found->second;
      }
      if (complete_start) {
        target[horizontal_joint_] = target_horizontal;
        target[vertical_joint_] = target_vertical;
        move_group->setStartStateToCurrentState();
        move_group->setPlanningTime(search_planning_time_s_);
        move_group->setNumPlanningAttempts(search_planning_attempts_);
        move_group->setMaxVelocityScalingFactor(search_planning_velocity_scaling_);
        move_group->setMaxAccelerationScalingFactor(search_planning_acceleration_scaling_);
        move_group->setGoalJointTolerance(joint_position_tolerance_);
        if (move_group->setJointValueTarget(target)) {
          MoveGroupInterface::Plan plan;
          if (static_cast<bool>(move_group->plan(plan)) && !search_plan_cancel_ &&
            !plan.trajectory_.joint_trajectory.points.empty())
          {
            const auto & planned = plan.trajectory_.joint_trajectory;
            trajectory.joint_names = joint_names_;
            bool compatible = true;
            for (const auto & point : planned.points) {
              trajectory_msgs::msg::JointTrajectoryPoint filtered;
              filtered.time_from_start = point.time_from_start;
              for (const auto & joint_name : joint_names_) {
                const auto found = std::find(
                  planned.joint_names.begin(), planned.joint_names.end(), joint_name);
                if (found == planned.joint_names.end()) {
                  compatible = false;
                  break;
                }
                const auto index = static_cast<std::size_t>(
                  std::distance(planned.joint_names.begin(), found));
                if (index >= point.positions.size()) {
                  compatible = false;
                  break;
                }
                filtered.positions.push_back(point.positions[index]);
              }
              if (!compatible) {
                break;
              }
              trajectory.points.push_back(std::move(filtered));
            }
            success = compatible && !trajectory.points.empty();
            if (!success) {
              failure_reason = "SEARCH_PLAN_JOINT_SET_INVALID";
            }
          }
        } else {
          failure_reason = "SEARCH_PLAN_TARGET_REJECTED";
        }
      } else {
        failure_reason = "SEARCH_PLAN_JOINT_STATE_MISSING";
      }
    } else {
      failure_reason = search_plan_cancel_ ? "SEARCH_PLAN_CANCELLED" : "SEARCH_MOVE_GROUP_NOT_READY";
    }

    {
      std::lock_guard<std::mutex> lock(mutex_);
      scene_fresh = point_cloud_count_ > 0U &&
        Fresh(point_cloud_received_time_, planning_scene_timeout_s_);
    }
    const bool scene_usable = !require_fresh_planning_scene_ || scene_fresh;
    if (success && !search_plan_cancel_ && scene_usable) {
      arm_trajectory_publisher_->publish(trajectory);
      const std::string diagnostic_source = require_fresh_planning_scene_ ?
        "COLLISION_CHECKED_" + source : "COLLISION_CHECKED_STATIC_SCENE_" + source;
      PublishTrajectoryDiagnostic(diagnostic_source, trajectory);
    } else if (success && require_fresh_planning_scene_ && !scene_fresh) {
      success = false;
      failure_reason = "SEARCH_PLAN_PLANNING_SCENE_STALE";
    }
    {
      std::lock_guard<std::mutex> lock(mutex_);
      search_plan_active_ = false;
      if (success && !search_plan_cancel_ && IsSearchState(state_)) {
        search_segment_horizontal_target_ = target_horizontal;
        search_segment_vertical_target_ = target_vertical;
        search_trajectory_active_ = true;
        const double duration_s = trajectory.points.empty() ? 0.0 :
          static_cast<double>(trajectory.points.back().time_from_start.sec) +
          static_cast<double>(trajectory.points.back().time_from_start.nanosec) * 1e-9;
        const auto segment_timeout = std::chrono::duration_cast<SteadyClock::duration>(
          std::chrono::duration<double>(
            std::max(search_segment_timeout_s_, duration_s * 2.0 + 1.0)));
        search_segment_deadline_ = SteadyClock::now() + segment_timeout;
        PublishControlDetailLocked("SEARCH_PLAN_ACCEPTED source=" + source);
      } else if (!success && !search_plan_cancel_ && IsSearchState(state_)) {
        search_plan_retry_time_ = SteadyClock::now() + std::chrono::milliseconds(500);
        search_horizontal_direction_ *= -1;
        PublishControlDetailLocked(failure_reason);
      }
    }
    search_plan_done_ = true;
  }

  bool IsSearchState(ControlState state) const
  {
    return state == ControlState::SEARCH || state == ControlState::LOCAL_SEARCH ||
           state == ControlState::LAST_PATH_REACQUIRE;
  }

  void PublishHoldTrajectoryLocked()
  {
    if (!arm_trajectory_publisher_) {
      return;
    }
    trajectory_msgs::msg::JointTrajectory trajectory;
    trajectory.joint_names = joint_names_;
    trajectory.points.resize(2);
    for (const auto & joint_name : joint_names_) {
      const auto current = CurrentJointLocked(joint_name);
      if (!current) {
        return;
      }
      trajectory.points[0].positions.push_back(*current);
      trajectory.points[1].positions.push_back(*current);
    }
    trajectory.points[1].time_from_start.sec = 0;
    trajectory.points[1].time_from_start.nanosec = 100000000U;
    arm_trajectory_publisher_->publish(trajectory);
    PublishTrajectoryDiagnostic("SEARCH_HOLD", trajectory);
  }

  void CancelPlannedSearchLocked()
  {
    search_plan_cancel_ = true;
    search_plan_active_ = false;
    search_trajectory_active_ = false;
    PublishHoldTrajectoryLocked();
  }

  void HandleSearchLocked(bool local)
  {
    if (TargetFreshLocked() && target_valid_frames_ >= target_acquire_frames_) {
      CancelPlannedSearchLocked();
      PublishZeroLocked();
      aligned_frames_ = 0;
      PublishControlDetailLocked("PHASE=ALIGN J1/J5=VISION_CENTER");
      SetStateLocked(
        ControlState::ALIGN,
        local ? "TARGET_REACQUIRED" : "TARGET_ACQUIRED");
      return;
    }

    const double timeout = local ? local_search_timeout_s_ : search_timeout_s_;
    const double elapsed = std::chrono::duration<double>(SteadyClock::now() - search_start_time_).count();
    if (backend_ == "piper" && real_motion_enabled_) {
      if (search_plan_active_) {
        return;
      }
      if (search_trajectory_active_) {
        const auto horizontal = CurrentJointLocked(horizontal_joint_);
        const auto vertical = CurrentJointLocked(vertical_joint_);
        if (horizontal && vertical &&
          Reached(*horizontal, search_segment_horizontal_target_) &&
          Reached(*vertical, search_segment_vertical_target_))
        {
          search_trajectory_active_ = false;
        } else if (SteadyClock::now() >= search_segment_deadline_) {
          // A reachable target that stalls must not leave the real arm parked
          // at one search angle.  Continue the bounded sweep only while the
          // six-axis feedback itself is fresh; stale feedback still faults and
          // the adapter's watchdog remains the final motion stop.
          if (!JointStateFreshLocked()) {
            CancelPlannedSearchLocked();
            StopLocked(ControlState::FAULT, "SEARCH_SEGMENT_FEEDBACK_TIMEOUT");
            return;
          }
          search_trajectory_active_ = false;
          search_horizontal_direction_ *= -1;
          search_plan_retry_time_ = SteadyClock::now() + std::chrono::milliseconds(100);
          PublishControlDetailLocked("SEARCH_SEGMENT_TIMEOUT_CONTINUE");
          return;
        } else {
          return;
        }
      }
    }
    const bool search_complete = elapsed >= timeout || StepSearchLocked();
    if (!search_complete) {
      return;
    }

    PublishZeroLocked();
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "SEARCH_JOINT_STATE_MISSING");
      return;
    }
    if (local) {
      // Match the simulation behavior: a failed local scan expands directly
      // into the full scan from the current pose; never reset the arm here.
      InitializeSearchLocked(false, *horizontal, *vertical);
      SetStateLocked(ControlState::SEARCH, "LOCAL_SEARCH_FAILED_CONTINUE_FULL_SCAN");
    } else {
      // Keep searching continuously.  A completed sweep starts another one
      // from the current pose instead of returning to PREPARE.
      InitializeSearchLocked(false, *horizontal, *vertical);
      SetStateLocked(ControlState::SEARCH, "FULL_SEARCH_CYCLE_RESTART");
    }
  }

  void HandleLastPathReacquireLocked()
  {
    if (TargetFreshLocked() && target_valid_frames_ >= target_acquire_frames_) {
      CancelPlannedSearchLocked();
      PublishZeroLocked();
      aligned_frames_ = 0;
      PublishControlDetailLocked("PHASE=ALIGN TARGET_REACQUIRED_ON_LAST_PATH");
      SetStateLocked(ControlState::ALIGN, "TARGET_REACQUIRED_ON_LAST_PATH");
      return;
    }
    if (backend_ == "piper" && real_motion_enabled_) {
      if (search_plan_active_) {
        return;
      }
      if (search_trajectory_active_) {
        const auto current_horizontal = CurrentJointLocked(horizontal_joint_);
        const auto current_vertical = CurrentJointLocked(vertical_joint_);
        if (current_horizontal && current_vertical &&
          Reached(*current_horizontal, search_segment_horizontal_target_) &&
          Reached(*current_vertical, search_segment_vertical_target_))
        {
          search_trajectory_active_ = false;
        } else if (SteadyClock::now() >= search_segment_deadline_) {
          // A reachable target that stalls must not leave the real arm parked
          // at one search angle.  Continue the bounded sweep only while the
          // six-axis feedback itself is fresh; stale feedback still faults and
          // the adapter's watchdog remains the final motion stop.
          if (!JointStateFreshLocked()) {
            CancelPlannedSearchLocked();
            StopLocked(ControlState::FAULT, "SEARCH_SEGMENT_FEEDBACK_TIMEOUT");
            return;
          }
          search_trajectory_active_ = false;
          search_horizontal_direction_ *= -1;
          search_plan_retry_time_ = SteadyClock::now() + std::chrono::milliseconds(100);
          PublishControlDetailLocked("SEARCH_SEGMENT_TIMEOUT_CONTINUE");
          return;
        } else {
          return;
        }
      }
    }
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "LAST_PATH_JOINT_STATE_MISSING");
      return;
    }
    if (Reached(*horizontal, last_path_horizontal_target_) &&
      Reached(*vertical, last_path_vertical_target_))
    {
      if (last_path_reacquire_steps_ < last_path_reacquire_max_steps_) {
        if (UpdatePredictedReacquireTargetLocked()) {
          return;
        }
        if (state_ == ControlState::FAULT) {
          return;
        }
      }
      BeginLocalSearchLocked("LAST_PATH_REACQUIRE_FAILED");
      return;
    }
    if (RequestPlannedSearchLocked(
        last_path_horizontal_target_, last_path_vertical_target_, "LAST_PATH_REACQUIRE")) {
      return;
    }
    PublishJointLocked(
      VelocityToward(*horizontal, last_path_horizontal_target_, horizontal_search_speed_),
      VelocityToward(*vertical, last_path_vertical_target_, vertical_search_speed_));
  }

  bool StepSearchLocked()
  {
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "SEARCH_JOINT_STATE_MISSING");
      return false;
    }

    if (search_is_local_) {
      StepLocalSearchLocked(*horizontal, *vertical);
    } else {
      StepFullSearchLocked(*horizontal, *vertical);
    }
    return false;
  }

  void StepLocalSearchLocked(double horizontal, double vertical)
  {
    double horizontal_target = search_horizontal_direction_ > 0 ?
      search_horizontal_limit_max_ : search_horizontal_limit_min_;
    double vertical_target = search_vertical_direction_ > 0 ?
      search_vertical_limit_max_ : search_vertical_limit_min_;
    bool direction_changed = false;

    if (Reached(horizontal, horizontal_target)) {
      search_horizontal_direction_ *= -1;
      horizontal_target = search_horizontal_direction_ > 0 ?
        search_horizontal_limit_max_ : search_horizontal_limit_min_;
      direction_changed = true;
    }
    if (Reached(vertical, vertical_target)) {
      search_vertical_direction_ *= -1;
      vertical_target = search_vertical_direction_ > 0 ?
        search_vertical_limit_max_ : search_vertical_limit_min_;
      direction_changed = true;
    }

    if (direction_changed) {
      PublishSearchDirectionLocked();
    }
    if (RequestPlannedSearchLocked(horizontal_target, vertical_target, "LOCAL_SEARCH")) {
      return;
    }
    PublishJointLocked(
      VelocityToward(horizontal, horizontal_target, horizontal_search_speed_),
      VelocityToward(vertical, vertical_target, vertical_search_speed_));
  }

  void StepFullSearchLocked(double horizontal, double vertical)
  {
    double horizontal_target = search_horizontal_direction_ > 0 ?
      search_horizontal_limit_max_ : search_horizontal_limit_min_;
    bool horizontal_boundary_hit = false;
    int horizontal_boundary_direction = 0;

    if (Reached(horizontal, horizontal_target)) {
      horizontal_boundary_hit = true;
      horizontal_boundary_direction = search_horizontal_direction_;
      search_horizontal_direction_ *= -1;
      horizontal_target = search_horizontal_direction_ > 0 ?
        search_horizontal_limit_max_ : search_horizontal_limit_min_;
    }

    double vertical_velocity = 0.0;
    bool phase_changed = false;
    switch (full_search_phase_) {
      case FullSearchPhase::DESCEND:
        search_vertical_direction_ = 1;
        if (Reached(vertical, search_vertical_limit_max_)) {
          full_search_phase_ = FullSearchPhase::BOTTOM_SCAN;
          search_vertical_direction_ = 0;
          ResetFullSearchCoverageLocked();
          phase_changed = true;
        } else {
          vertical_velocity = VelocityToward(
            vertical, search_vertical_limit_max_, vertical_search_speed_);
        }
        break;

      case FullSearchPhase::BOTTOM_SCAN:
        search_vertical_direction_ = 0;
        RecordFullSearchBoundaryLocked(
          horizontal_boundary_hit, horizontal_boundary_direction);
        if (FullSearchCoverageCompleteLocked()) {
          full_search_phase_ = FullSearchPhase::ASCEND;
          search_vertical_direction_ = -1;
          ResetFullSearchCoverageLocked();
          vertical_velocity = VelocityToward(
            vertical, search_vertical_limit_min_, vertical_search_speed_);
          phase_changed = true;
        }
        break;

      case FullSearchPhase::ASCEND:
        search_vertical_direction_ = -1;
        if (Reached(vertical, search_vertical_limit_min_)) {
          full_search_phase_ = FullSearchPhase::TOP_SCAN;
          search_vertical_direction_ = 0;
          ResetFullSearchCoverageLocked();
          phase_changed = true;
        } else {
          vertical_velocity = VelocityToward(
            vertical, search_vertical_limit_min_, vertical_search_speed_);
        }
        break;

      case FullSearchPhase::TOP_SCAN:
        search_vertical_direction_ = 0;
        RecordFullSearchBoundaryLocked(
          horizontal_boundary_hit, horizontal_boundary_direction);
        if (FullSearchCoverageCompleteLocked()) {
          full_search_phase_ = FullSearchPhase::DESCEND;
          search_vertical_direction_ = 1;
          ResetFullSearchCoverageLocked();
          vertical_velocity = VelocityToward(
            vertical, search_vertical_limit_max_, vertical_search_speed_);
          phase_changed = true;
        }
        break;
    }

    if (horizontal_boundary_hit || phase_changed) {
      PublishSearchDirectionLocked();
    }
    const double planned_vertical_target = vertical_velocity == 0.0 ?
      vertical : vertical + (vertical_velocity > 0.0 ? search_planning_step_rad_ :
      -search_planning_step_rad_);
    if (RequestPlannedSearchLocked(horizontal_target, planned_vertical_target, "FULL_SEARCH")) {
      return;
    }
    PublishJointLocked(
      VelocityToward(horizontal, horizontal_target, horizontal_search_speed_),
      vertical_velocity);
  }

  void RecordFullSearchBoundaryLocked(bool boundary_hit, int boundary_direction)
  {
    if (!boundary_hit) {
      return;
    }
    if (boundary_direction > 0) {
      full_search_right_seen_ = true;
    } else if (boundary_direction < 0) {
      full_search_left_seen_ = true;
    }
  }

  bool FullSearchCoverageCompleteLocked() const
  {
    return full_search_left_seen_ && full_search_right_seen_;
  }

  void ResetFullSearchCoverageLocked()
  {
    full_search_left_seen_ = false;
    full_search_right_seen_ = false;
  }

  void HandleAlignLocked()
  {
    const bool confirmed = TargetFreshLocked();
    if (!confirmed) {
      if (align_target_lost_since_ == SteadyTime{}) {
        align_target_lost_since_ = SteadyClock::now();
      }
      const double lost_s = std::chrono::duration<double>(
        SteadyClock::now() - align_target_lost_since_).count();
      if (lost_s <= target_loss_grace_s_) {
        // A wrist-camera frame can briefly fail while the arm is moving. Hold
        // the aligned pose during this grace period; immediately reversing
        // into LAST_PATH_REACQUIRE turns detector flicker into a retreat loop.
        PublishZeroLocked();
        return;
      }
      BeginLastPathReacquireLocked("TARGET_LOST_DURING_ALIGN");
      return;
    }
    align_target_lost_since_ = SteadyTime{};
    const double error_x = error_x_px_;
    const double error_y = error_y_px_;
    const double horizontal_velocity = std::clamp(
      horizontal_error_sign_ * horizontal_kp_ * error_x,
      -align_joint_speed_limit_, align_joint_speed_limit_);
    const double vertical_velocity = std::clamp(
      vertical_error_sign_ * vertical_kp_ * error_y,
      -align_joint_speed_limit_, align_joint_speed_limit_);
    PublishAlignmentJointLocked(horizontal_velocity, vertical_velocity);

    if (aligned_frames_ >= align_stable_frames_) {
      if (direct_grasp_after_align_) {
        aligned_frames_ = 0;
        PublishZeroLocked();
        RequestServoStopLocked();
        PublishControlDetailLocked("PHASE=GRASP_READY DIRECT_VISUAL_ALIGN");
        SetStateLocked(ControlState::GRASP_READY, "DIRECT_VISUAL_ALIGN_ACQUIRED");
        return;
      }
      if (!level_align_enabled_) {
        StopLocked(ControlState::FAULT, "LEVEL_ALIGN_NOT_CALIBRATED");
        return;
      }
      aligned_frames_ = 0;
      PublishControlDetailLocked(
        "PHASE=LEVEL_ALIGN J1=HOLD J2/J3=VISION J5=TO_NEGATIVE_ONLY");
      SetStateLocked(ControlState::LEVEL_ALIGN, "TARGET_ACQUIRED_LEVELING");
    }
  }

  void HandleGraspReadyLocked()
  {
    if (freeze_grasp_tracking_) {
      return;
    }
    // GRASP_READY is externally visible to the grasp executor, but it must
    // not freeze visual tracking.  Keep Servo stopped while the target stays
    // inside the acquisition tolerance; resume closed-loop alignment as soon
    // as a fresh target moves outside it.
    if (!TargetFreshLocked()) {
      ResumeServoLocked();
      BeginLastPathReacquireLocked("TARGET_LOST_AFTER_GRASP_READY");
      return;
    }
    if (target_error_ratio_ > target_acquire_error_ratio_) {
      aligned_frames_ = 0;
      ResumeServoLocked();
      PublishControlDetailLocked("PHASE=ALIGN TARGET_SHIFT_AFTER_GRASP_READY");
      SetStateLocked(ControlState::ALIGN, "GRASP_READY_TARGET_SHIFT");
    }
  }

  void HandleLevelAlignLocked()
  {
    if (!TargetFreshLocked()) {
      PublishControlDetailLocked(
        "PHASE=LEVEL_RECOVERY J1=HOLD J2=UP J3=TO_ZERO J5=FAST_TO_NEGATIVE");
      SetStateLocked(ControlState::LEVEL_RECOVERY, "TARGET_LOST_DURING_LEVEL_ALIGN");
      return;
    }
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    const auto joint2 = CurrentJointLocked(level_joint2_name_);
    const auto joint3 = CurrentJointLocked(level_joint3_name_);
    if (!horizontal || !vertical || !joint2 || !joint3) {
      StopLocked(ControlState::FAULT, "LEVEL_ALIGN_JOINT_STATE_MISSING");
      return;
    }

    // During the J5 positive-to-negative flip, J1 must hold its detected
    // angle. J2/J3 are the only image-compensation joints in this phase.
    const double horizontal_velocity = 0.0;
    const double level_vertical_velocity = VelocityToward(
      *vertical, level_joint5_target_, level_joint5_speed_);
    const double shoulder_vertical_correction =
      level_joint23_vertical_kp_ * error_y_px_;
    PublishLevelJointLocked(
      horizontal_velocity,
      level_vertical_velocity,
      std::clamp(
        VelocityToward(*joint2, level_joint2_target_, level_joint2_speed_) +
        level_joint2_vertical_sign_ * shoulder_vertical_correction,
        -level_joint2_speed_, level_joint2_speed_),
      std::clamp(
        VelocityToward(*joint3, level_joint3_target_, level_joint3_speed_) +
        level_joint3_vertical_sign_ * shoulder_vertical_correction,
        -level_joint3_speed_, level_joint3_speed_));

    if (Reached(*vertical, level_joint5_target_))
    {
      aligned_frames_ = 0;
      PublishControlDetailLocked("PHASE=FINAL_ALIGN J1=VISION J2/J3=VISION J5=NEGATIVE_ONLY");
      SetStateLocked(ControlState::FINAL_ALIGN, "J5_NEGATIVE_LEVEL_REACHED");
    }
  }

  void HandleLevelRecoveryLocked()
  {
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    const auto joint2 = CurrentJointLocked(level_joint2_name_);
    const auto joint3 = CurrentJointLocked(level_joint3_name_);
    if (!horizontal || !vertical || !joint2 || !joint3) {
      StopLocked(ControlState::FAULT, "LEVEL_RECOVERY_JOINT_STATE_MISSING");
      return;
    }

    // The target is unavailable. Finish the requested safe posture transition
    // without using stale image error: hold J1, raise J2, bring J3 toward zero,
    // and complete the J5 negative flip at the faster recovery speed.
    PublishLevelJointLocked(
      0.0,
      VelocityToward(*vertical, level_joint5_target_, level_target_lost_joint5_speed_),
      VelocityToward(*joint2, level_joint2_target_, level_joint2_speed_),
      VelocityToward(*joint3, level_joint3_target_, level_joint3_speed_));

    if (!Reached(*vertical, level_joint5_target_)) {
      return;
    }
    if (TargetFreshLocked()) {
      aligned_frames_ = 0;
      PublishControlDetailLocked("PHASE=FINAL_ALIGN J1=VISION J2/J3=VISION J5=NEGATIVE_ONLY");
      SetStateLocked(ControlState::FINAL_ALIGN, "TARGET_REACQUIRED_AFTER_LEVEL_RECOVERY");
      return;
    }
    BeginLocalSearchLocked("TARGET_NOT_REACQUIRED_AFTER_LEVEL_RECOVERY");
  }

  void HandleFinalAlignLocked()
  {
    if (!TargetFreshLocked()) {
      BeginLocalSearchLocked("TARGET_LOST_DURING_FINAL_ALIGN");
      return;
    }
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    const auto joint2 = CurrentJointLocked(level_joint2_name_);
    const auto joint3 = CurrentJointLocked(level_joint3_name_);
    if (!horizontal || !vertical || !joint2 || !joint3) {
      StopLocked(ControlState::FAULT, "FINAL_ALIGN_JOINT_STATE_MISSING");
      return;
    }

    const double horizontal_velocity = std::clamp(
      horizontal_error_sign_ * horizontal_kp_ * error_x_px_,
      -align_joint_speed_limit_, align_joint_speed_limit_);
    double vertical_velocity = std::clamp(
      vertical_error_sign_ * vertical_kp_ * error_y_px_,
      -align_joint_speed_limit_, align_joint_speed_limit_);
    if ((*vertical <= final_j5_negative_min_ && vertical_velocity < 0.0) ||
      (*vertical >= final_j5_negative_max_ && vertical_velocity > 0.0))
    {
      vertical_velocity = 0.0;
    }
    const double shoulder_vertical_correction =
      level_joint23_vertical_kp_ * error_y_px_;
    PublishLevelJointLocked(
      horizontal_velocity,
      vertical_velocity,
      std::clamp(
        VelocityToward(*joint2, level_joint2_target_, level_joint2_speed_) +
        level_joint2_vertical_sign_ * shoulder_vertical_correction,
        -level_joint2_speed_, level_joint2_speed_),
      std::clamp(
        VelocityToward(*joint3, level_joint3_target_, level_joint3_speed_) +
        level_joint3_vertical_sign_ * shoulder_vertical_correction,
        -level_joint3_speed_, level_joint3_speed_));

    if (aligned_frames_ >= align_stable_frames_) {
      PublishZeroLocked();
      RequestServoStopLocked();
      PublishControlDetailLocked("PHASE=GRASP_READY SERVO=STOPPED");
      SetStateLocked(ControlState::GRASP_READY, "FINAL_NEGATIVE_POSTURE_ALIGNED");
    }
  }

  void BeginLocalSearchLocked(const std::string & reason)
  {
    CancelPlannedSearchLocked();
    PublishZeroLocked();
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "LOCAL_SEARCH_JOINT_STATE_MISSING");
      return;
    }
    target_valid_frames_ = 0;
    aligned_frames_ = 0;
    InitializeSearchLocked(true, *horizontal, *vertical);
    SetStateLocked(ControlState::LOCAL_SEARCH, reason);
  }

  void BeginLastPathReacquireLocked(const std::string & reason)
  {
    CancelPlannedSearchLocked();
    target_valid_frames_ = 0;
    aligned_frames_ = 0;
    last_path_prediction_valid_ = false;
    last_path_reacquire_steps_ = 0;
    if (!InitializePredictedReacquireLocked()) {
      BeginLocalSearchLocked("LAST_TARGET_HISTORY_UNAVAILABLE");
      return;
    }
    if (!UpdatePredictedReacquireTargetLocked()) {
      if (state_ != ControlState::FAULT) {
        BeginLocalSearchLocked("LAST_TARGET_HISTORY_UNAVAILABLE");
      }
      return;
    }
    SetStateLocked(ControlState::LAST_PATH_REACQUIRE, reason);
  }

  bool InitializePredictedReacquireLocked()
  {
    if (target_history_.size() < 2U) {
      return false;
    }
    const auto & oldest = target_history_.front();
    const auto & latest = target_history_.back();
    const double latest_age_s = std::chrono::duration<double>(
      SteadyClock::now() - latest.received_time).count();
    const double elapsed_s = std::chrono::duration<double>(
      latest.received_time - oldest.received_time).count();
    if (latest_age_s > target_timeout_s_ || elapsed_s <= 1e-3 ||
      latest.camera_point.header.frame_id.empty())
    {
      return false;
    }

    double velocity_x = (latest.reference_point.point.x - oldest.reference_point.point.x) / elapsed_s;
    double velocity_y = (latest.reference_point.point.y - oldest.reference_point.point.y) / elapsed_s;
    double velocity_z = (latest.reference_point.point.z - oldest.reference_point.point.z) / elapsed_s;
    const double speed = std::sqrt(
      velocity_x * velocity_x + velocity_y * velocity_y + velocity_z * velocity_z);
    if (speed > last_path_prediction_max_speed_m_s_) {
      const double scale = last_path_prediction_max_speed_m_s_ / speed;
      velocity_x *= scale;
      velocity_y *= scale;
      velocity_z *= scale;
    }

    last_path_prediction_target_ = latest.reference_point;
    last_path_prediction_target_.point.x += velocity_x * last_path_prediction_horizon_s_;
    last_path_prediction_target_.point.y += velocity_y * last_path_prediction_horizon_s_;
    last_path_prediction_target_.point.z += velocity_z * last_path_prediction_horizon_s_;
    last_path_camera_frame_ = latest.camera_point.header.frame_id;
    last_path_prediction_valid_ = true;
    return true;
  }

  bool UpdatePredictedReacquireTargetLocked()
  {
    if (!last_path_prediction_valid_) {
      return false;
    }
    const auto horizontal = CurrentJointLocked(horizontal_joint_);
    const auto vertical = CurrentJointLocked(vertical_joint_);
    if (!horizontal || !vertical) {
      StopLocked(ControlState::FAULT, "LAST_PATH_JOINT_STATE_MISSING");
      return false;
    }

    geometry_msgs::msg::PointStamped predicted_camera_point;
    try {
      const auto transform = tf_buffer_->lookupTransform(
        last_path_camera_frame_, target_history_reference_frame_, tf2::TimePointZero);
      tf2::doTransform(last_path_prediction_target_, predicted_camera_point, transform);
    } catch (const tf2::TransformException & exception) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Predicted target transform to '%s' failed: %s",
        last_path_camera_frame_.c_str(), exception.what());
      return false;
    }
    if (!std::isfinite(predicted_camera_point.point.x) ||
      !std::isfinite(predicted_camera_point.point.y) ||
      !std::isfinite(predicted_camera_point.point.z) ||
      predicted_camera_point.point.z < last_path_min_predicted_depth_m_)
    {
      return false;
    }

    const double horizontal_delta = std::clamp(
      horizontal_error_sign_ * std::atan2(
        predicted_camera_point.point.x, predicted_camera_point.point.z),
      -last_path_reacquire_max_joint_step_rad_, last_path_reacquire_max_joint_step_rad_);
    const double vertical_delta = std::clamp(
      vertical_error_sign_ * std::atan2(
        predicted_camera_point.point.y, predicted_camera_point.point.z),
      -last_path_reacquire_max_joint_step_rad_, last_path_reacquire_max_joint_step_rad_);
    if (std::abs(horizontal_delta) <= joint_position_tolerance_ &&
      std::abs(vertical_delta) <= joint_position_tolerance_)
    {
      return false;
    }

    last_path_horizontal_target_ = std::clamp(
      *horizontal + horizontal_delta, horizontal_search_min_, horizontal_search_max_);
    last_path_vertical_target_ = std::clamp(
      *vertical + vertical_delta, vertical_search_min_, vertical_search_max_);
    ++last_path_reacquire_steps_;
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(3)
           << "PHASE=LAST_PATH_REACQUIRE step=" << last_path_reacquire_steps_
           << "/" << last_path_reacquire_max_steps_
           << " predicted_" << target_history_reference_frame_ << "_m=("
           << last_path_prediction_target_.point.x << ","
           << last_path_prediction_target_.point.y << ","
           << last_path_prediction_target_.point.z << ")";
    PublishControlDetailLocked(stream.str());
    return true;
  }

  void InitializeSearchLocked(bool local, double horizontal_center, double vertical_center)
  {
    search_is_local_ = local;
    if (local) {
      const double clamped_horizontal_center = std::clamp(
        horizontal_center, horizontal_search_min_, horizontal_search_max_);
      const double clamped_vertical_center = std::clamp(
        vertical_center, vertical_search_min_, vertical_search_max_);
      search_horizontal_limit_min_ = std::max(
        horizontal_search_min_, clamped_horizontal_center - local_horizontal_range_);
      search_horizontal_limit_max_ = std::min(
        horizontal_search_max_, clamped_horizontal_center + local_horizontal_range_);
      search_vertical_limit_min_ = std::max(
        vertical_search_min_, clamped_vertical_center - local_vertical_range_);
      search_vertical_limit_max_ = std::min(
        vertical_search_max_, clamped_vertical_center + local_vertical_range_);
    } else {
      if (search_bounds_relative_to_start_) {
        // Keep a real-arm full scan around the manually verified start pose.
        search_horizontal_limit_min_ = std::max(
          horizontal_search_min_, horizontal_center - full_search_horizontal_range_);
        search_horizontal_limit_max_ = std::min(
          horizontal_search_max_, horizontal_center + full_search_horizontal_range_);
        search_vertical_limit_min_ = std::max(
          vertical_search_min_, vertical_center - full_search_vertical_range_);
        search_vertical_limit_max_ = std::min(
          vertical_search_max_, vertical_center + full_search_vertical_range_);
      } else {
        search_horizontal_limit_min_ = horizontal_search_min_;
        search_horizontal_limit_max_ = horizontal_search_max_;
        search_vertical_limit_min_ = vertical_search_min_;
        search_vertical_limit_max_ = vertical_search_max_;
      }
    }
    if (local) {
      search_horizontal_direction_ =
        horizontal_center >= search_horizontal_limit_max_ ? -1 : 1;
      search_vertical_direction_ = vertical_center >= search_vertical_limit_max_ ? -1 : 1;
    } else {
      // Start a full scan toward negative J1; target alignment uses pixel error instead.
      search_horizontal_direction_ = -1;
      full_search_phase_ = FullSearchPhase::DESCEND;
      search_vertical_direction_ = 1;
      ResetFullSearchCoverageLocked();
    }
    search_start_time_ = SteadyClock::now();
    PublishSearchDirectionLocked();
  }

  void PublishSearchDirectionLocked()
  {
    std_msgs::msg::String message;
    const std::string j1_direction = search_horizontal_direction_ > 0 ?
      "POSITIVE" : "NEGATIVE";
    if (search_is_local_) {
      message.data = std::string("PHASE=LOCAL_SEARCH J1=") + j1_direction +
        " J5=" + (search_vertical_direction_ > 0 ? "DOWN" : "UP");
    } else {
      const char * j5_direction = "HOLD";
      if (search_vertical_direction_ > 0) {
        j5_direction = "DOWN";
      } else if (search_vertical_direction_ < 0) {
        j5_direction = "UP";
      } else if (full_search_phase_ == FullSearchPhase::BOTTOM_SCAN) {
        j5_direction = "HOLD_DOWN";
      } else if (full_search_phase_ == FullSearchPhase::TOP_SCAN) {
        j5_direction = "HOLD_UP";
      }
      message.data = std::string("PHASE=") + SearchPhaseName(full_search_phase_) +
        " J1=" + j1_direction + " J5=" + j5_direction;
    }
    PublishControlDetailLocked(message.data);
  }

  void PublishControlDetailLocked(const std::string & detail)
  {
    std_msgs::msg::String message;
    message.data = detail;
    search_direction_publisher_->publish(message);
    RCLCPP_INFO(get_logger(), "Control detail: %s.", message.data.c_str());
  }

  void PublishJointLocked(
    double horizontal_velocity, double vertical_velocity, bool lock_horizon = true)
  {
    control_msgs::msg::JointJog command;
    command.header.stamp = now();
    command.joint_names = {horizontal_joint_, vertical_joint_};
    command.velocities = {horizontal_velocity, vertical_velocity};
    const std::size_t lock_count = std::min(
      horizon_joint_names_.size(), horizon_lock_positions_.size());
    for (std::size_t index = 0; index < lock_count; ++index) {
      command.joint_names.push_back(horizon_joint_names_[index]);
      command.velocities.push_back(lock_horizon ? HorizonLockVelocityLocked(index) : 0.0);
    }
    joint_command_publisher_->publish(command);
    PublishCommandDiagnosticLocked("VISUAL_JOINT_JOG", command);
  }

  void PublishAlignmentJointLocked(double horizontal_velocity, double vertical_velocity)
  {
    if (!alignment_assist_enabled_) {
      PublishJointLocked(horizontal_velocity, vertical_velocity);
      return;
    }
    control_msgs::msg::JointJog command;
    command.header.stamp = now();
    command.joint_names = {
      horizontal_joint_, vertical_joint_, alignment_assist_horizontal_joint_,
      alignment_assist_vertical_joint_};
    command.velocities = {
      horizontal_velocity, vertical_velocity,
      std::clamp(
        alignment_assist_horizontal_sign_ * alignment_assist_horizontal_ratio_ *
        horizontal_velocity, -alignment_assist_speed_limit_, alignment_assist_speed_limit_),
      std::clamp(
        alignment_assist_vertical_sign_ * alignment_assist_vertical_ratio_ * vertical_velocity,
        -alignment_assist_speed_limit_, alignment_assist_speed_limit_)};
    const std::size_t lock_count = std::min(
      horizon_joint_names_.size(), horizon_lock_positions_.size());
    for (std::size_t index = 0; index < lock_count; ++index) {
      command.joint_names.push_back(horizon_joint_names_[index]);
      command.velocities.push_back(HorizonLockVelocityLocked(index));
    }
    joint_command_publisher_->publish(command);
    PublishCommandDiagnosticLocked("VISUAL_ALIGNMENT_JOG", command);
  }

  void PublishLevelJointLocked(
    double horizontal_velocity, double vertical_velocity,
    double joint2_velocity, double joint3_velocity)
  {
    control_msgs::msg::JointJog command;
    command.header.stamp = now();
    command.joint_names = {
      horizontal_joint_, vertical_joint_, level_joint2_name_, level_joint3_name_};
    command.velocities = {
      horizontal_velocity, vertical_velocity, joint2_velocity, joint3_velocity};
    const std::size_t lock_count = std::min(
      horizon_joint_names_.size(), horizon_lock_positions_.size());
    for (std::size_t index = 0; index < lock_count; ++index) {
      command.joint_names.push_back(horizon_joint_names_[index]);
      command.velocities.push_back(HorizonLockVelocityLocked(index));
    }
    joint_command_publisher_->publish(command);
    PublishCommandDiagnosticLocked("LEVEL_ALIGNMENT_JOG", command);
  }

  void PublishZeroLocked()
  {
    PublishJointLocked(0.0, 0.0, false);
  }

  double HorizonLockVelocityLocked(std::size_t index) const
  {
    const auto current = CurrentJointLocked(horizon_joint_names_[index]);
    if (!current) {
      return 0.0;
    }
    const double error = horizon_lock_positions_[index] - *current;
    if (std::abs(error) <= horizon_lock_tolerance_) {
      return 0.0;
    }
    return std::clamp(
      horizon_lock_kp_ * error, -horizon_lock_speed_limit_, horizon_lock_speed_limit_);
  }

  double VelocityToward(double current, double target, double limit) const
  {
    const double error = target - current;
    if (std::abs(error) <= joint_position_tolerance_) {
      return 0.0;
    }
    return std::copysign(std::min(limit, std::abs(error) * 2.0), error);
  }

  bool Reached(double current, double target) const
  {
    return std::abs(current - target) <= joint_position_tolerance_;
  }

  std::optional<double> CurrentJointLocked(const std::string & name) const
  {
    const auto found = joint_positions_.find(name);
    if (found == joint_positions_.end()) {
      return std::nullopt;
    }
    return found->second;
  }

  bool TargetFreshLocked() const
  {
    return target_valid_ && Fresh(last_target_valid_time_, target_timeout_s_) &&
           Fresh(error_received_time_, target_timeout_s_);
  }

  bool CandidateFreshLocked() const
  {
    return candidate_valid_ && Fresh(candidate_error_received_time_, target_timeout_s_);
  }

  bool JointStateFreshLocked() const
  {
    return Fresh(joint_state_time_, joint_state_timeout_s_);
  }

  bool Fresh(const SteadyTime & time, double timeout_s) const
  {
    if (time == SteadyTime{}) {
      return false;
    }
    return std::chrono::duration<double>(SteadyClock::now() - time).count() <= timeout_s;
  }

  void RecordTargetHistorySample()
  {
    TargetHistorySample sample;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (!target_valid_ || !Fresh(target_point_received_time_, target_timeout_s_) ||
        !Fresh(error_received_time_, target_timeout_s_))
      {
        return;
      }
      sample.camera_point = target_point_camera_;
      sample.joint_positions = joint_positions_;
      sample.error_x_px = error_x_px_;
      sample.error_y_px = error_y_px_;
      sample.error_ratio = target_error_ratio_;
      sample.received_time = SteadyClock::now();
    }

    if (sample.camera_point.header.frame_id.empty() ||
      !std::isfinite(sample.camera_point.point.x) ||
      !std::isfinite(sample.camera_point.point.y) ||
      !std::isfinite(sample.camera_point.point.z))
    {
      return;
    }
    try {
      const auto transform = tf_buffer_->lookupTransform(
        target_history_reference_frame_, sample.camera_point.header.frame_id,
        tf2::TimePointZero);
      tf2::doTransform(sample.camera_point, sample.reference_point, transform);
    } catch (const tf2::TransformException & exception) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Target history transform to '%s' failed: %s",
        target_history_reference_frame_.c_str(), exception.what());
      return;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    target_history_.push_back(std::move(sample));
    while (!target_history_.empty() &&
      std::chrono::duration<double>(SteadyClock::now() -
      target_history_.front().received_time).count() > target_history_window_s_)
    {
      target_history_.pop_front();
    }
    PublishTargetHistoryLocked();
  }

  void PublishTargetHistoryLocked()
  {
    if (!target_history_publisher_ || target_history_.empty()) {
      return;
    }
    const auto & latest = target_history_.back();
    const double age_s = std::chrono::duration<double>(
      SteadyClock::now() - latest.received_time).count();
    double velocity_x = 0.0;
    double velocity_y = 0.0;
    double velocity_z = 0.0;
    if (target_history_.size() >= 2U) {
      const auto & oldest = target_history_.front();
      const double elapsed_s = std::chrono::duration<double>(
        latest.received_time - oldest.received_time).count();
      if (elapsed_s > 1e-3) {
        velocity_x = (latest.reference_point.point.x - oldest.reference_point.point.x) / elapsed_s;
        velocity_y = (latest.reference_point.point.y - oldest.reference_point.point.y) / elapsed_s;
        velocity_z = (latest.reference_point.point.z - oldest.reference_point.point.z) / elapsed_s;
      }
    }
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(3)
           << "samples=" << target_history_.size()
           << " age_s=" << age_s
           << " camera_m=(" << latest.camera_point.point.x << ","
           << latest.camera_point.point.y << "," << latest.camera_point.point.z << ")"
           << " " << target_history_reference_frame_ << "_m=("
           << latest.reference_point.point.x << "," << latest.reference_point.point.y << ","
           << latest.reference_point.point.z << ")"
           << " velocity_m_s=(" << velocity_x << "," << velocity_y << ","
           << velocity_z << ")"
           << " error_px=(" << latest.error_x_px << "," << latest.error_y_px << ")"
           << " error_ratio=" << latest.error_ratio
           << " joint_count=" << latest.joint_positions.size();
    std_msgs::msg::String message;
    message.data = stream.str();
    target_history_publisher_->publish(message);
  }

  static bool IsMotionState(ControlState state)
  {
    return state == ControlState::PREPARE || state == ControlState::SEARCH ||
           state == ControlState::LAST_PATH_REACQUIRE ||
           state == ControlState::LOCAL_SEARCH || state == ControlState::ALIGN ||
           state == ControlState::LEVEL_ALIGN || state == ControlState::LEVEL_RECOVERY ||
           state == ControlState::FINAL_ALIGN || state == ControlState::GRASP_READY;
  }

  void ResumeServoLocked()
  {
    servo_status_seen_ = false;
    servo_status_ = -1;
    if (servo_start_client_->service_is_ready()) {
      servo_start_client_->async_send_request(
        std::make_shared<std_srvs::srv::Trigger::Request>());
    }
  }

  void StopLocked(ControlState final_state, const std::string & reason)
  {
    CancelPlannedSearchLocked();
    PublishZeroLocked();
    SetStateLocked(final_state, reason);
    RequestServoStopLocked();
  }

  void RequestServoStopLocked()
  {
    if (servo_stop_client_->service_is_ready()) {
      servo_stop_client_->async_send_request(
        std::make_shared<std_srvs::srv::Trigger::Request>());
    }
  }

  void SetStateLocked(ControlState state, const std::string & reason)
  {
    const bool changed = state_ != state || last_reason_ != reason;
    state_ = state;
    last_reason_ = reason;
    PublishStateLocked(reason);
    if (changed) {
      RCLCPP_INFO(get_logger(), "STATE -> %s (%s)", StateName(state_), reason.c_str());
    }
  }

  void PublishStateLocked(const std::string & reason)
  {
    if (!state_publisher_ || !reason_publisher_) {
      return;
    }
    std_msgs::msg::String state_message;
    state_message.data = StateName(state_);
    state_publisher_->publish(state_message);
    std_msgs::msg::String reason_message;
    reason_message.data = reason;
    reason_publisher_->publish(reason_message);
  }

  void PublishCommandDiagnosticLocked(
    const std::string & source, const control_msgs::msg::JointJog & command)
  {
    if (!command_diagnostic_publisher_) {
      return;
    }
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(3)
           << "source=" << source << " state=" << StateName(state_) << " joints=";
    for (std::size_t index = 0; index < command.joint_names.size(); ++index) {
      if (index > 0U) {
        stream << ",";
      }
      stream << command.joint_names[index] << ":";
      if (index < command.velocities.size()) {
        stream << command.velocities[index];
      } else {
        stream << "missing";
      }
    }
    std_msgs::msg::String message;
    message.data = stream.str();
    command_diagnostic_publisher_->publish(message);
  }

  void PublishTrajectoryDiagnostic(
    const std::string & source, const trajectory_msgs::msg::JointTrajectory & trajectory)
  {
    if (!command_diagnostic_publisher_ || trajectory.points.empty()) {
      return;
    }
    const auto & final_point = trajectory.points.back();
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(3) << "source=" << source << " joints=";
    for (std::size_t index = 0; index < trajectory.joint_names.size(); ++index) {
      if (index > 0U) {
        stream << ",";
      }
      stream << trajectory.joint_names[index] << ":";
      if (index < final_point.positions.size()) {
        stream << final_point.positions[index];
      } else {
        stream << "missing";
      }
    }
    std_msgs::msg::String message;
    message.data = stream.str();
    command_diagnostic_publisher_->publish(message);
  }

  std::mutex mutex_;
  std::mutex worker_mutex_;
  std::thread prepare_thread_;
  std::thread search_plan_thread_;
  std::atomic_bool cancel_requested_{false};
  std::atomic_bool search_plan_cancel_{false};
  std::atomic_bool search_plan_done_{true};
  std::shared_ptr<MoveGroupInterface> move_group_;

  ControlState state_{ControlState::IDLE};
  std::string last_reason_;
  bool configuration_ok_{false};
  bool adapter_was_armed_{false};

  std::string backend_;
  bool real_motion_enabled_{false};
  bool observe_pose_calibrated_{true};
  bool execute_prepare_{true};
  bool skip_prepare_{false};
  std::vector<std::string> joint_names_;
  std::vector<double> observe_joint_positions_;
  std::vector<double> reset_joint_positions_;
  std::string horizontal_joint_;
  std::string vertical_joint_;
  bool alignment_assist_enabled_{false};
  std::string alignment_assist_horizontal_joint_;
  std::string alignment_assist_vertical_joint_;
  std::vector<std::string> horizon_joint_names_;
  std::vector<double> horizon_lock_positions_;
  bool horizon_lock_enabled_{true};
  bool level_align_enabled_{false};
  bool direct_grasp_after_align_{false};
  bool freeze_grasp_tracking_{false};
  std::string level_joint2_name_;
  std::string level_joint3_name_;
  double level_joint2_target_{1.35};
  double level_joint3_target_{-0.18};
  double level_joint5_target_{-1.10};
  double level_joint2_speed_{0.08};
  double level_joint3_speed_{0.30};
  double level_joint5_speed_{0.36};
  double level_target_lost_joint5_speed_{0.40};
  double level_joint2_vertical_sign_{1.0};
  double level_joint3_vertical_sign_{-1.0};
  double level_joint23_vertical_kp_{0.00015};
  double final_j5_negative_min_{-1.18};
  double final_j5_negative_max_{-0.95};
  double horizontal_error_sign_{1.0};
  double vertical_error_sign_{1.0};

  double horizontal_search_min_{-0.90};
  double horizontal_search_max_{0.90};
  double vertical_search_min_{-0.60};
  double vertical_search_max_{0.95};
  bool search_bounds_relative_to_start_{false};
  double full_search_horizontal_range_{0.12};
  double full_search_vertical_range_{0.10};
  double local_horizontal_range_{0.08};
  double local_vertical_range_{0.06};
  double last_path_prediction_horizon_s_{0.25};
  double last_path_prediction_max_speed_m_s_{0.40};
  double last_path_reacquire_max_joint_step_rad_{0.60};
  int last_path_reacquire_max_steps_{2};
  double last_path_min_predicted_depth_m_{0.05};
  double target_loss_grace_s_{0.80};
  double horizontal_search_speed_{0.12};
  double vertical_search_speed_{0.08};
  double joint_position_tolerance_{0.01};
  double search_timeout_s_{75.0};
  double local_search_timeout_s_{5.0};
  double search_planning_step_rad_{0.08};
  double search_planning_time_s_{0.50};
  int search_planning_attempts_{2};
  double search_planning_velocity_scaling_{0.05};
  double search_planning_acceleration_scaling_{0.05};
  double search_segment_timeout_s_{12.0};
  bool search_plan_active_{false};
  bool search_trajectory_active_{false};
  double search_segment_horizontal_target_{0.0};
  double search_segment_vertical_target_{0.0};
  SteadyTime search_segment_deadline_{};
  SteadyTime search_plan_retry_time_{};
  double last_path_horizontal_target_{0.0};
  double last_path_vertical_target_{0.0};
  geometry_msgs::msg::PointStamped last_path_prediction_target_;
  std::string last_path_camera_frame_;
  bool last_path_prediction_valid_{false};
  int last_path_reacquire_steps_{0};
  SteadyTime align_target_lost_since_{};
  double target_timeout_s_{0.60};
  double target_history_window_s_{0.40};
  double joint_state_timeout_s_{0.50};
  int target_acquire_frames_{3};
  int align_stable_frames_{5};
  double target_acquire_error_ratio_{0.20};
  double horizontal_kp_{0.0008};
  double vertical_kp_{0.0008};
  double align_joint_speed_limit_{0.08};
  double alignment_assist_horizontal_ratio_{0.20};
  double alignment_assist_vertical_ratio_{0.20};
  double alignment_assist_horizontal_sign_{1.0};
  double alignment_assist_vertical_sign_{1.0};
  double alignment_assist_speed_limit_{0.03};
  double horizon_lock_kp_{1.0};
  double horizon_lock_speed_limit_{0.05};
  double horizon_lock_tolerance_{0.02};
  double control_rate_hz_{20.0};
  double prepare_velocity_scaling_{0.05};
  double prepare_acceleration_scaling_{0.05};
  double prepare_planning_time_s_{10.0};
  double prepare_execution_timeout_s_{45.0};
  double prepare_max_joint_step_rad_{0.08};

  std::string error_topic_;
  std::string target_valid_topic_;
  std::string target_point_topic_;
  std::string target_history_reference_frame_;
  std::string target_history_topic_;
  std::string candidate_error_topic_;
  std::string candidate_valid_topic_;
  std::string joint_state_topic_;
  std::string filtered_point_cloud_topic_;
  double planning_scene_timeout_s_{2.5};
  bool require_fresh_planning_scene_{true};
  std::string joint_command_topic_;
  std::string servo_status_topic_;
  std::string servo_start_service_;
  std::string servo_stop_service_;
  std::string emergency_stop_topic_;
  std::string adapter_armed_topic_;
  std::string grasp_reacquire_topic_;

  std::unordered_map<std::string, double> joint_positions_;
  SteadyTime joint_state_time_{};
  SteadyTime point_cloud_received_time_{};
  std::size_t point_cloud_count_{0U};
  bool planning_scene_stale_reported_{false};
  SteadyTime error_received_time_{};
  SteadyTime last_target_valid_time_{};
  SteadyTime target_point_received_time_{};
  SteadyTime candidate_error_received_time_{};
  bool target_valid_{false};
  bool candidate_valid_{false};
  bool reset_requested_{false};
  double error_x_px_{0.0};
  double error_y_px_{0.0};
  double target_error_ratio_{1.0};
  double candidate_error_x_px_{0.0};
  double candidate_error_y_px_{0.0};
  double candidate_error_ratio_{1.0};
  geometry_msgs::msg::PointStamped target_point_camera_;
  std::deque<TargetHistorySample> target_history_;
  int target_valid_frames_{0};
  int aligned_frames_{0};
  bool servo_status_seen_{false};
  int8_t servo_status_{-1};

  double search_horizontal_limit_min_{0.0};
  double search_horizontal_limit_max_{0.0};
  double search_vertical_limit_min_{0.0};
  double search_vertical_limit_max_{0.0};
  int search_horizontal_direction_{1};
  int search_vertical_direction_{1};
  bool search_is_local_{false};
  FullSearchPhase full_search_phase_{FullSearchPhase::DESCEND};
  bool full_search_left_seen_{false};
  bool full_search_right_seen_{false};
  int full_search_retries_{0};
  SteadyTime search_start_time_{};

  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr error_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr target_valid_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr target_point_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr candidate_error_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr candidate_valid_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr filtered_point_cloud_subscription_;
  rclcpp::Subscription<std_msgs::msg::Int8>::SharedPtr servo_status_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr emergency_stop_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr adapter_armed_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr grasp_reacquire_subscription_;
  rclcpp::Publisher<control_msgs::msg::JointJog>::SharedPtr joint_command_publisher_;
  rclcpp::Publisher<trajectory_msgs::msg::JointTrajectory>::SharedPtr arm_trajectory_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr reason_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr search_direction_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr target_history_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr command_diagnostic_publisher_;
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr servo_start_client_;
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr servo_stop_client_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr start_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr stop_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr reset_service_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
};

}  // namespace brain_robot_pick_place

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  const auto options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true);
  const auto node = std::make_shared<brain_robot_pick_place::VisualSearchController>(options);

  try {
    const auto move_group = std::make_shared<brain_robot_pick_place::MoveGroupInterface>(node, "arm");
    node->SetMoveGroup(move_group);

    rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
    executor.add_node(node);
    executor.spin();
  } catch (const std::exception & exception) {
    RCLCPP_FATAL(node->get_logger(), "Visual controller failed: %s", exception.what());
  }

  rclcpp::shutdown();
  return 0;
}
