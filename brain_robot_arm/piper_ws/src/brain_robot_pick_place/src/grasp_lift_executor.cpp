#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <future>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/robot_state/conversions.h>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <moveit_msgs/srv/get_position_ik.hpp>
#include <rclcpp/rclcpp.hpp>
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

namespace brain_robot_pick_place
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
using PlanningSceneInterface = moveit::planning_interface::PlanningSceneInterface;

class GraspLiftExecutor : public rclcpp::Node
{
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
    target_point_subscription_ = create_subscription<geometry_msgs::msg::PointStamped>(
      target_point_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::PointStamped::SharedPtr message) {
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
            "Cannot save target in %s for short-horizon approach prediction: %s",
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
    target_size_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      target_size_topic_, rclcpp::QoS(1).reliable(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_size_ = *message;
        target_size_received_time_ = std::chrono::steady_clock::now();
      });
    target_error_subscription_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
      "/brain_robot_vision/pixel_error", rclcpp::SensorDataQoS(),
      [this](const geometry_msgs::msg::Vector3Stamped::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_error_ratio_ = message->vector.z;
        target_error_received_time_ = std::chrono::steady_clock::now();
      });
    target_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      "/brain_robot_vision/target_valid", rclcpp::SensorDataQoS(),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        target_valid_ = message->data;
        target_valid_received_time_ = std::chrono::steady_clock::now();
      });
    depth_valid_subscription_ = create_subscription<std_msgs::msg::Bool>(
      depth_valid_topic_, rclcpp::QoS(1).reliable(),
      [this](const std_msgs::msg::Bool::SharedPtr message) {
        std::lock_guard<std::mutex> lock(target_mutex_);
        depth_valid_ = message->data;
        depth_valid_received_time_ = std::chrono::steady_clock::now();
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
    depth_valid_topic_ = ParameterOr<std::string>(
      "depth_valid_topic", "/brain_robot_vision/depth_valid");
    adaptive_size_enabled_ = ParameterOr<bool>("adaptive_size_enabled", false);
    min_object_size_m_ = ParameterOr<double>("min_object_size_m", 0.01);
    max_object_size_m_ = ParameterOr<double>("max_object_size_m", 0.25);
    target_timeout_s_ = ParameterOr<double>("target_timeout_s", 0.60);
    static_target_lock_ = ParameterOr<bool>("static_target_lock", false);
    grasp_height_offset_m_ = ParameterOr<double>("grasp_height_offset_m", 0.0);
    gripper_tip_offset_m_ = ParameterOr<double>("gripper_tip_offset_m", 0.1358);
    grasp_center_offset_m_ = ParameterOr<double>(
      "grasp_center_offset_m", gripper_tip_offset_m_);
    grasp_contact_tolerance_m_ = ParameterOr<double>("grasp_contact_tolerance_m", 0.025);
    gripper_open_value_ = ParameterOr<int>("gripper_open_value", 50000);
    gripper_close_value_ = ParameterOr<int>("gripper_close_value", 40000);
    gripper_settle_s_ = ParameterOr<double>("gripper_settle_s", 2.0);
    gripper_feedback_topic_ = ParameterOr<std::string>(
      "gripper_feedback_topic", "/joint_states_feedback");
    gripper_feedback_timeout_s_ = ParameterOr<double>("gripper_feedback_timeout_s", 3.0);
    min_gripper_feedback_motion_rad_ = ParameterOr<double>(
      "min_gripper_feedback_motion_rad", 0.001);
    auto_release_after_lift_ = ParameterOr<bool>("auto_release_after_lift", false);
    hold_after_lift_s_ = ParameterOr<double>("hold_after_lift_s", 1.0);
    top_down_pregrasp_clearance_m_ = ParameterOr<double>(
      "top_down_pregrasp_clearance_m", 0.12);
    top_down_grasp_clearance_m_ = ParameterOr<double>(
      "top_down_grasp_clearance_m", 0.005);
    top_down_grasp_yaw_ = ParameterOr<double>("top_down_grasp_yaw", 0.0);
    top_down_yaw_candidates_ = ParameterOr<std::vector<double>>(
      "top_down_yaw_candidates", {0.0, 1.57079632679, -1.57079632679, 3.14159265359});
    top_down_tilt_candidates_ = ParameterOr<std::vector<double>>(
      "top_down_tilt_candidates", {0.0, 0.35, 0.70, 1.00});
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
      lift_distance_m_ > 0.0 &&
      grasp_depth_m_ > 0.0 && pregrasp_standoff_m_ > grasp_depth_m_ &&
      approach_microstep_m_ > 0.0 && approach_max_steps_ > 0 &&
      approach_prediction_horizon_s_ >= 0.0 && approach_max_target_speed_m_s_ > 0.0 &&
      cartesian_eef_step_m_ > 0.0 && grasp_height_offset_m_ >= 0.0 &&
      gripper_tip_offset_m_ > 0.0 && top_down_pregrasp_clearance_m_ > 0.0 &&
      grasp_center_offset_m_ > 0.0 && grasp_contact_tolerance_m_ > 0.0 &&
      top_down_grasp_clearance_m_ >= 0.0 &&
      top_down_pregrasp_clearance_m_ > top_down_grasp_clearance_m_ &&
      !top_down_yaw_candidates_.empty() &&
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
      trajectory_feedback_tolerance_rad_ > 0.0 && trajectory_feedback_timeout_s_ > 0.0 &&
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
    if (!StopServo()) {
      Fail("SERVO_STOP_FAILED");
      return;
    }
    // A tabletop cube is static. Capture its base-frame pose immediately
    // after visual alignment, before opening the gripper can occlude the
    // wrist camera; static mode never reacquires from later image motion.
    if (static_target_lock_ && !CaptureTargetModel()) {
      Fail("STATIC_TARGET_MODEL_UNAVAILABLE");
      return;
    }
    if (!simulation_only_) {
      if (!CommandRealGripper(true) || cancel_requested_) {
        Fail("OPEN_GRIPPER_FAILED");
        return;
      }
      std::this_thread::sleep_for(std::chrono::duration<double>(gripper_settle_s_));
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
    if (diagonal_side_grasp_enabled_) {
      DiagonalSidePointGraspAndLift();
      return;
    }
    if (top_down_grasp_enabled_) {
      TopDownPointGraspAndLift();
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
      if (!BuildTopDownPointGrasp(top_down_grasp_clearance_m_, grasp_target)) {
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
    if (!BuildDiagonalSidePointGrasp(
        diagonal_pregrasp_standoff_m_, diagonal_pregrasp_lift_m_, 0.0, pregrasp_target))
    {
      Fail("DIAGONAL_SIDE_PREGRASP_TARGET_UNAVAILABLE");
      return;
    }
    if (!MoveArmToPose(pregrasp_target, "DIAGONAL_SIDE_PREGRASP") || cancel_requested_) {
      Fail("DIAGONAL_SIDE_PREGRASP_PLAN_FAILED");
      return;
    }
    PublishState("DIAGONAL_SIDE_PREGRASP_REACHED");

    PublishState("DIAGONAL_SIDE_APPROACH_PLANNING");
    geometry_msgs::msg::PoseStamped grasp_target;
    if (!BuildDiagonalSidePointGrasp(
        diagonal_grasp_standoff_m_, diagonal_grasp_lift_m_, 0.0, grasp_target))
    {
      Fail("DIAGONAL_SIDE_GRASP_TARGET_UNAVAILABLE");
      return;
    }
    if (!MoveArmCartesianToPose(grasp_target, "DIAGONAL_SIDE_APPROACH") || cancel_requested_) {
      Fail("DIAGONAL_SIDE_APPROACH_FAILED");
      return;
    }
    FinishGraspAndLift();
  }

  bool BuildDiagonalSidePointGrasp(
    double camera_standoff_m, double vertical_clearance_m,
    double lateral_offset_m, geometry_msgs::msg::PoseStamped & grasp_target)
  {
    geometry_msgs::msg::PointStamped target_point_camera;
    double object_size_m = 0.0;
    {
      std::lock_guard<std::mutex> lock(target_mutex_);
      const double age_s = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - target_point_received_time_).count();
      if (target_point_received_time_ == std::chrono::steady_clock::time_point{} ||
        age_s > target_timeout_s_)
      {
        RCLCPP_ERROR(get_logger(), "Camera target point is missing or stale (age %.3f s).", age_s);
        return false;
      }
      target_point_camera = target_point_camera_;
      if (adaptive_size_enabled_) {
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

    const std::string target_frame = target_point_camera.header.frame_id.empty() ?
      camera_optical_frame_ : target_point_camera.header.frame_id;
    try {
      const auto world_from_target = tf_buffer_->lookupTransform(
        lift_reference_frame_, target_frame, tf2::TimePointZero);
      geometry_msgs::msg::PointStamped object_world;
      tf2::doTransform(target_point_camera, object_world, world_from_target);

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
      const tf2::Vector3 current_camera_position(
        world_from_camera.transform.translation.x,
        world_from_camera.transform.translation.y,
        world_from_camera.transform.translation.z);

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

  void TopDownPointGraspAndLift()
  {
    selected_top_down_yaw_valid_ = false;
    PublishState("TOP_DOWN_PREGRASP_PLANNING");
    geometry_msgs::msg::PoseStamped pregrasp_target;
    if (!BuildTopDownPointGrasp(top_down_pregrasp_clearance_m_, pregrasp_target)) {
      Fail("TOP_DOWN_PREGRASP_TARGET_UNAVAILABLE");
      return;
    }
    if (!MoveArmToPose(pregrasp_target, "TOP_DOWN_PREGRASP") || cancel_requested_) {
      Fail("TOP_DOWN_PREGRASP_PLAN_FAILED");
      return;
    }
    PublishState("TOP_DOWN_PREGRASP_REACHED");

    PublishState("TOP_DOWN_DESCENT_PLANNING");
    geometry_msgs::msg::PoseStamped grasp_target;
    if (!BuildTopDownPointGrasp(top_down_grasp_clearance_m_, grasp_target)) {
      Fail("TOP_DOWN_GRASP_TARGET_UNAVAILABLE");
      return;
    }
    if (!MoveArmCartesianToPose(grasp_target, "TOP_DOWN_DESCENT") || cancel_requested_) {
      Fail("TOP_DOWN_DESCENT_FAILED");
      return;
    }
    FinishGraspAndLift();
  }

  void FinishGraspAndLift()
  {
    geometry_msgs::msg::PoseStamped grasp_pose;
    if (!simulation_only_) {
      grasp_pose = CurrentPoseInFrame(lift_reference_frame_);
      if (grasp_pose.header.frame_id.empty()) {
        Fail("GRASP_POSE_UNAVAILABLE");
        return;
      }
    }
    const double gripper_before_close = LatestGripperPosition();
    PublishState("CLOSING_GRIPPER");
    if (!CommandRealGripper(false) || cancel_requested_) {
      Fail("CLOSE_GRIPPER_FAILED");
      return;
    }
    if (!simulation_only_) {
      std::this_thread::sleep_for(std::chrono::duration<double>(gripper_settle_s_));
      if (!WaitForGripperMotion(gripper_before_close)) {
        Fail("GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED");
        return;
      }
      // PiPER exposes position feedback, not a contact/force measurement. This
      // confirms jaw actuation before lifting; object retention remains an
      // entity-level result to validate on the real cube.
      PublishDiagnostic("GRIPPER_CLOSE_FEEDBACK_CONFIRMED_NO_FORCE_SENSOR");

      PublishState("LIFTING");
      auto lift_target = grasp_pose;
      lift_target.header.stamp = now();
      lift_target.pose.position.z += lift_distance_m_;
      if (!MoveArmToPose(lift_target, "LIFT") || cancel_requested_) {
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

      // Return along the already traversed vertical path and release at the
      // measured grasp pose. This avoids inventing an uncalibrated transfer
      // location, then retreats to the collision-checked lifted pose.
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
      if (!WaitForGripperMotion(gripper_before_open)) {
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
    auto lift_target = CurrentPoseInFrame(lift_reference_frame_);
    if (lift_target.header.frame_id.empty()) {
      Fail("CURRENT_POSE_UNAVAILABLE");
      return;
    }
    lift_target.header.stamp = now();
    lift_target.pose.position.z += lift_distance_m_;
    if (!MoveArmToPose(lift_target, "LIFT") || cancel_requested_) {
      Fail("LIFT_FAILED_HOLDING_CUP");
      return;
    }
    PublishState("HOLDING");
    RCLCPP_INFO(
      get_logger(), "Cup lifted %.3f m and held; no transfer or placement was commanded.",
      lift_distance_m_);
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
    double vertical_clearance_m, geometry_msgs::msg::PoseStamped & grasp_target)
  {
    geometry_msgs::msg::PointStamped object_world;
    if (!PredictedTargetInReference(object_world)) {
      RCLCPP_ERROR(get_logger(), "Locked top-down target is unavailable.");
      return false;
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
    RCLCPP_INFO(
      get_logger(), "Top-down approach selected: tilt=%.3f yaw=%.3f rad.",
      selected_top_down_tilt_, selected_top_down_yaw_);
    return true;
  }

  void PopulateTopDownPose(
    const geometry_msgs::msg::PointStamped & object_world, double vertical_clearance_m,
    double tilt, double yaw, geometry_msgs::msg::PoseStamped & grasp_target)
  {
    const auto orientation = TopDownOrientation(yaw, tilt);
    tf2::Quaternion rotation;
    tf2::fromMsg(orientation, rotation);
    tf2::Vector3 tool_axis = tf2::quatRotate(rotation, tf2::Vector3(0.0, 0.0, 1.0));
    tool_axis.normalize();
    const double tip_distance = gripper_tip_offset_m_ + grasp_height_offset_m_ +
      vertical_clearance_m;
    grasp_target.header.frame_id = lift_reference_frame_;
    grasp_target.header.stamp = now();
    grasp_target.pose.position.x = object_world.point.x - tool_axis.x() * tip_distance;
    grasp_target.pose.position.y = object_world.point.y - tool_axis.y() * tip_distance;
    grasp_target.pose.position.z = object_world.point.z - tool_axis.z() * tip_distance;
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

  bool CaptureTargetModel()
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
      RCLCPP_WARN(get_logger(), "Cannot lock base-frame target model (age %.3f s).", age_s);
      return false;
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
    arm_trajectory_publisher_->publish(trajectory);
    PublishDiagnostic("REAL_ARM_TRAJECTORY_PUBLISHED");
    const auto & final_point = trajectory.points.back();
    const double duration_s = static_cast<double>(final_point.time_from_start.sec) +
      static_cast<double>(final_point.time_from_start.nanosec) * 1e-9;
    const auto earliest_feedback_time = std::chrono::steady_clock::now() +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(duration_s));
    const auto deadline = earliest_feedback_time +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(trajectory_feedback_timeout_s_));
    while (rclcpp::ok() && !cancel_requested_ && std::chrono::steady_clock::now() < deadline) {
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

  bool WaitForGripperMotion(double before_close)
  {
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
          age_s <= target_timeout_s_ && std::isfinite(before_close) && std::isfinite(current) &&
          std::abs(current - before_close) >= min_gripper_feedback_motion_rad_)
        {
          return true;
        }
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
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
    attached.touch_links = gripper_->getLinkNames();
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
    arm_->setPoseReferenceFrame(target.header.frame_id);
    if (!arm_->setPoseTarget(target, end_effector_link_)) {
      RCLCPP_ERROR(get_logger(), "%s rejected the requested end-effector pose.", stage.c_str());
      return false;
    }
    MoveGroupInterface::Plan plan;
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
    if (simulation_only_) {
      return static_cast<bool>(arm_->execute(plan));
    }
    return ExecuteArmTrajectory(plan.trajectory_.joint_trajectory);
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
    arm_->setStartState(*fresh_state);
    arm_->setPoseReferenceFrame(target.header.frame_id);
    std::vector<geometry_msgs::msg::Pose> waypoints{target.pose};
    moveit_msgs::msg::RobotTrajectory trajectory;
    const double previous_velocity_scaling = velocity_scaling_;
    arm_->setMaxVelocityScalingFactor(linear_approach_velocity_scaling_);
    const double fraction = arm_->computeCartesianPath(
      waypoints, cartesian_eef_step_m_, 0.0, trajectory, true);
    arm_->setMaxVelocityScalingFactor(previous_velocity_scaling);
    if (fraction < 0.995 || trajectory.joint_trajectory.points.empty() || cancel_requested_) {
      RCLCPP_ERROR(
        get_logger(), "%s Cartesian path incomplete (fraction=%.3f).", stage.c_str(), fraction);
      return false;
    }
    RCLCPP_INFO(
      get_logger(), "%s Cartesian path has %zu trajectory points.", stage.c_str(),
      trajectory.joint_trajectory.points.size());
    if (simulation_only_) {
      return static_cast<bool>(arm_->execute(trajectory));
    }
    return ExecuteArmTrajectory(trajectory.joint_trajectory);
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
  std::string cup_name_;
  std::string open_target_;
  std::string close_target_;
  std::string lift_reference_frame_;
  std::string camera_optical_frame_;
  std::string target_point_topic_;
  std::string target_size_topic_;
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
  int gripper_close_value_{40000};
  double gripper_settle_s_{2.0};
  std::string gripper_feedback_topic_;
  double gripper_feedback_timeout_s_{3.0};
  double min_gripper_feedback_motion_rad_{0.001};
  bool auto_release_after_lift_{false};
  double hold_after_lift_s_{1.0};
  double top_down_pregrasp_clearance_m_{0.12};
  double top_down_grasp_clearance_m_{0.005};
  double top_down_grasp_yaw_{0.0};
  std::vector<double> top_down_yaw_candidates_;
  std::vector<double> top_down_tilt_candidates_;
  double selected_top_down_yaw_{0.0};
  double selected_top_down_tilt_{0.0};
  bool selected_top_down_yaw_valid_{false};
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
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr reacquire_publisher_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr visual_state_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr target_point_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr target_size_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr target_error_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr target_valid_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr depth_valid_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr gripper_feedback_subscription_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr emergency_stop_subscription_;
  rclcpp::Client<std_srvs::srv::SetBool>::SharedPtr cup_follow_client_;
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr servo_stop_client_;
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

  try {
    auto arm = std::make_shared<brain_robot_pick_place::MoveGroupInterface>(
      node, node->ArmGroup());
    std::shared_ptr<brain_robot_pick_place::MoveGroupInterface> gripper;
    if (node->SimulationOnly()) {
      gripper = std::make_shared<brain_robot_pick_place::MoveGroupInterface>(
        node, node->GripperGroup());
    }
    auto planning_scene =
      std::make_shared<brain_robot_pick_place::PlanningSceneInterface>();
    node->SetMoveItInterfaces(arm, gripper, planning_scene);

    rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
    executor.add_node(node);
    executor.spin();
  } catch (const std::exception & exception) {
    RCLCPP_FATAL(node->get_logger(), "Grasp executor failed: %s", exception.what());
  }
  rclcpp::shutdown();
  return 0;
}
