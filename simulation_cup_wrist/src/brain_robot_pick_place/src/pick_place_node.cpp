#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <future>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/robot_state/conversions.h>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/display_trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/color_rgba.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <visualization_msgs/msg/marker.hpp>

namespace brain_robot_pick_place
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
using PlanningSceneInterface = moveit::planning_interface::PlanningSceneInterface;

class TrajectoryVisualizer
{
public:
  TrajectoryVisualizer(
    const rclcpp::Node::SharedPtr & node,
    const MoveGroupInterface & arm,
    std::string end_effector_link,
    double preview_seconds)
  : node_(node),
    robot_model_(arm.getRobotModel()),
    frame_id_(robot_model_->getModelFrame()),
    end_effector_link_(std::move(end_effector_link)),
    preview_seconds_(preview_seconds)
  {
    display_publisher_ = node_->create_publisher<moveit_msgs::msg::DisplayTrajectory>(
      "/display_planned_path", rclcpp::QoS(1).transient_local());
    marker_publisher_ = node_->create_publisher<visualization_msgs::msg::Marker>(
      "/brain_robot_pick_place/trajectory_marker", rclcpp::QoS(20).transient_local());
  }

  void Clear()
  {
    visualization_msgs::msg::Marker marker;
    marker.header.frame_id = frame_id_;
    marker.header.stamp = node_->now();
    marker.action = visualization_msgs::msg::Marker::DELETEALL;
    marker_publisher_->publish(marker);
    next_marker_id_ = 0;
  }

  void Publish(const MoveGroupInterface::Plan & plan, const std::string & stage)
  {
    moveit_msgs::msg::DisplayTrajectory display;
    display.model_id = robot_model_->getName();
    display.trajectory_start = plan.start_state_;
    display.trajectory.push_back(plan.trajectory_);
    display_publisher_->publish(display);

    moveit::core::RobotState state(robot_model_);
    if (!moveit::core::robotStateMsgToRobotState(plan.start_state_, state)) {
      RCLCPP_WARN(node_->get_logger(), "Could not build RViz path for stage %s.", stage.c_str());
      return;
    }

    visualization_msgs::msg::Marker marker;
    marker.header.frame_id = frame_id_;
    marker.header.stamp = node_->now();
    marker.ns = "pick_place_trajectory";
    marker.id = next_marker_id_++;
    marker.type = visualization_msgs::msg::Marker::LINE_STRIP;
    marker.action = visualization_msgs::msg::Marker::ADD;
    marker.pose.orientation.w = 1.0;
    marker.scale.x = 0.008;
    marker.color = ColorForStage(stage);

    AddEndEffectorPoint(state, marker);
    const auto & joint_trajectory = plan.trajectory_.joint_trajectory;
    for (std::size_t index = 0; index < joint_trajectory.points.size(); ++index) {
      if (moveit::core::jointTrajPointToRobotState(joint_trajectory, index, state)) {
        AddEndEffectorPoint(state, marker);
      }
    }
    if (marker.points.size() >= 2) {
      marker_publisher_->publish(marker);
    }

    RCLCPP_INFO(
      node_->get_logger(), "Published RViz trajectory for %s with %zu path points.",
      stage.c_str(), marker.points.size());
    if (preview_seconds_ > 0.0) {
      std::this_thread::sleep_for(std::chrono::duration<double>(preview_seconds_));
    }
  }

private:
  void AddEndEffectorPoint(
    moveit::core::RobotState & state,
    visualization_msgs::msg::Marker & marker) const
  {
    state.update();
    const auto & transform = state.getGlobalLinkTransform(end_effector_link_);
    geometry_msgs::msg::Point point;
    point.x = transform.translation().x();
    point.y = transform.translation().y();
    point.z = transform.translation().z();
    marker.points.push_back(point);
  }

  static std_msgs::msg::ColorRGBA ColorForStage(const std::string & stage)
  {
    std_msgs::msg::ColorRGBA color;
    color.a = 1.0;
    if (stage == "PREGRASP") {
      color.g = 1.0;
      color.b = 1.0;
    } else if (stage == "ABOVE_CUP") {
      color.r = 0.2;
      color.g = 0.4;
      color.b = 1.0;
    } else if (stage == "DESCEND") {
      color.r = 1.0;
      color.g = 0.8;
    } else if (stage == "LIFT") {
      color.r = 0.1;
      color.g = 1.0;
      color.b = 0.2;
    } else if (stage == "TRANSFER") {
      color.r = 1.0;
      color.b = 1.0;
    } else if (stage == "LOWER") {
      color.r = 1.0;
      color.g = 0.4;
    } else {
      color.r = 1.0;
      color.g = 1.0;
      color.b = 1.0;
    }
    return color;
  }

  rclcpp::Node::SharedPtr node_;
  moveit::core::RobotModelConstPtr robot_model_;
  std::string frame_id_;
  std::string end_effector_link_;
  double preview_seconds_;
  int next_marker_id_{0};
  rclcpp::Publisher<moveit_msgs::msg::DisplayTrajectory>::SharedPtr display_publisher_;
  rclcpp::Publisher<visualization_msgs::msg::Marker>::SharedPtr marker_publisher_;
};

template<typename T>
T ParameterOr(const rclcpp::Node::SharedPtr & node, const std::string & name, const T & fallback)
{
  T value = fallback;
  node->get_parameter_or(name, value, fallback);
  return value;
}

bool WaitForSceneObjects(
  const rclcpp::Node::SharedPtr & node,
  PlanningSceneInterface & planning_scene,
  const std::vector<std::string> & required_names,
  double wait_seconds)
{
  const auto wait_duration = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
    std::chrono::duration<double>(wait_seconds));
  const auto deadline = std::chrono::steady_clock::now() + wait_duration;

  while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline) {
    const auto known_names = planning_scene.getKnownObjectNames();
    const bool all_found = std::all_of(
      required_names.begin(), required_names.end(),
      [&known_names](const std::string & name) {
        return std::find(known_names.begin(), known_names.end(), name) != known_names.end();
      });
    if (all_found) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  RCLCPP_ERROR(node->get_logger(), "Timed out waiting for care_table and medicine_cup.");
  return false;
}

bool IsNearZero(
  const rclcpp::Node::SharedPtr & node,
  MoveGroupInterface & arm,
  double tolerance)
{
  const auto joint_values = arm.getCurrentJointValues();
  if (joint_values.empty()) {
    RCLCPP_ERROR(node->get_logger(), "No current arm joint state was received.");
    return false;
  }

  const auto largest = std::max_element(
    joint_values.begin(), joint_values.end(),
    [](double left, double right) {return std::abs(left) < std::abs(right);});
  const double maximum_error = std::abs(*largest);
  if (maximum_error > tolerance) {
    RCLCPP_ERROR(
      node->get_logger(),
      "Arm is not at the zero state (largest joint error %.3f rad, limit %.3f rad).",
      maximum_error, tolerance);
    return false;
  }
  return true;
}

bool MoveGripper(
  const rclcpp::Node::SharedPtr & node,
  MoveGroupInterface & gripper,
  const std::string & target_name)
{
  RCLCPP_INFO(node->get_logger(), "Gripper stage: %s.", target_name.c_str());
  gripper.setStartStateToCurrentState();
  if (!gripper.setNamedTarget(target_name)) {
    RCLCPP_ERROR(
      node->get_logger(), "The gripper group has no valid named target '%s'.",
      target_name.c_str());
    return false;
  }

  MoveGroupInterface::Plan plan;
  if (!static_cast<bool>(gripper.plan(plan))) {
    RCLCPP_ERROR(
      node->get_logger(), "Failed to plan gripper target '%s'.", target_name.c_str());
    return false;
  }
  if (!static_cast<bool>(gripper.execute(plan))) {
    RCLCPP_ERROR(
      node->get_logger(), "Failed to execute gripper target '%s'.", target_name.c_str());
    return false;
  }
  return true;
}

bool MoveArmToPose(
  const rclcpp::Node::SharedPtr & node,
  MoveGroupInterface & arm,
  const geometry_msgs::msg::PoseStamped & target,
  const std::string & end_effector_link,
  const std::string & stage,
  TrajectoryVisualizer & trajectory_visualizer)
{
  RCLCPP_INFO(
    node->get_logger(),
    "Arm stage %s target (%.3f, %.3f, %.3f).",
    stage.c_str(), target.pose.position.x, target.pose.position.y, target.pose.position.z);

  arm.setStartStateToCurrentState();
  arm.setPoseReferenceFrame(target.header.frame_id);
  if (!arm.setPoseTarget(target, end_effector_link)) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt rejected arm stage %s.", stage.c_str());
    return false;
  }

  MoveGroupInterface::Plan plan;
  const bool planned = static_cast<bool>(arm.plan(plan));
  arm.clearPoseTargets();
  if (!planned) {
    RCLCPP_ERROR(node->get_logger(), "Planning failed at arm stage %s.", stage.c_str());
    return false;
  }

  RCLCPP_INFO(
    node->get_logger(), "Arm stage %s planned with %zu trajectory points.",
    stage.c_str(), plan.trajectory_.joint_trajectory.points.size());
  trajectory_visualizer.Publish(plan, stage);
  if (!static_cast<bool>(arm.execute(plan))) {
    RCLCPP_ERROR(node->get_logger(), "Execution failed at arm stage %s.", stage.c_str());
    return false;
  }
  return true;
}

bool SetCupFollowing(const rclcpp::Node::SharedPtr & node, bool enabled)
{
  auto client = node->create_client<std_srvs::srv::SetBool>(
    "/brain_robot_pick_place/set_cup_follow");
  if (!client->wait_for_service(std::chrono::seconds(3))) {
    RCLCPP_ERROR(node->get_logger(), "Cup-follow service is unavailable.");
    return false;
  }

  auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
  request->data = enabled;
  auto future = client->async_send_request(request);
  if (future.wait_for(std::chrono::seconds(3)) != std::future_status::ready) {
    RCLCPP_ERROR(node->get_logger(), "Cup-follow service timed out.");
    return false;
  }

  const auto response = future.get();
  if (!response->success) {
    RCLCPP_ERROR(node->get_logger(), "Cup-follow service rejected request: %s", response->message.c_str());
    return false;
  }
  RCLCPP_INFO(node->get_logger(), "%s", response->message.c_str());
  return true;
}

int RunPregrasp(const rclcpp::Node::SharedPtr & node)
{
  const bool simulation_only = ParameterOr(node, "simulation_only", true);
  const bool execute = ParameterOr(node, "execute", false);
  const bool full_sequence = ParameterOr(node, "full_sequence", false);
  const bool require_zero = ParameterOr(node, "require_zero_state", true);
  const std::string arm_group = ParameterOr<std::string>(node, "arm_group", "arm");
  const std::string gripper_group = ParameterOr<std::string>(node, "gripper_group", "gripper");
  const std::string end_effector_link =
    ParameterOr<std::string>(node, "end_effector_link", "gripper_base");
  const std::string cup_name = ParameterOr<std::string>(node, "cup_name", "medicine_cup");
  const double gripper_tip_offset = ParameterOr(node, "gripper_tip_offset", 0.1358);
  const double pregrasp_clearance = ParameterOr(node, "pregrasp_clearance", 0.12);
  const double approach_clearance = ParameterOr(node, "approach_clearance", 0.06);
  const double grasp_height_offset = ParameterOr(node, "grasp_height_offset", 0.0);
  const double lift_clearance = ParameterOr(node, "lift_clearance", 0.15);
  const double grasp_yaw = ParameterOr(node, "grasp_yaw", 0.0);
  const double place_x = ParameterOr(node, "place_x", 0.40);
  const double place_y = ParameterOr(node, "place_y", 0.12);
  const double observation_pause_seconds =
    ParameterOr(node, "observation_pause_seconds", 0.0);
  const double trajectory_preview_seconds =
    ParameterOr(node, "trajectory_preview_seconds", 0.0);
  const double zero_tolerance = ParameterOr(node, "zero_state_tolerance", 0.08);
  const double planning_time = ParameterOr(node, "planning_time", 5.0);
  const int64_t planning_attempts = ParameterOr<int64_t>(node, "planning_attempts", 10);
  const double velocity_scaling = ParameterOr(node, "velocity_scaling", 0.10);
  const double acceleration_scaling = ParameterOr(node, "acceleration_scaling", 0.10);
  const double position_tolerance = ParameterOr(node, "position_tolerance", 0.01);
  const double orientation_tolerance = ParameterOr(node, "orientation_tolerance", 0.05);
  const double object_wait_seconds = ParameterOr(node, "object_wait_seconds", 10.0);

  if (!simulation_only) {
    RCLCPP_ERROR(
      node->get_logger(),
      "simulation_only=false is forbidden; no trajectory was planned or executed.");
    return 2;
  }
  if (gripper_tip_offset <= 0.0 || pregrasp_clearance <= 0.0 ||
    approach_clearance <= 0.0 || approach_clearance >= pregrasp_clearance ||
    grasp_height_offset < 0.0 || lift_clearance <= pregrasp_clearance ||
    observation_pause_seconds < 0.0 || trajectory_preview_seconds < 0.0 ||
    planning_time <= 0.0 ||
    planning_attempts < 1 || velocity_scaling <= 0.0 || velocity_scaling > 1.0 ||
    acceleration_scaling <= 0.0 || acceleration_scaling > 1.0)
  {
    RCLCPP_ERROR(node->get_logger(), "Invalid motion parameter; refusing to plan.");
    return 2;
  }

  RCLCPP_INFO(
    node->get_logger(), "Starting simulation %s in %s mode.",
    full_sequence ? "pick-and-place" : "pregrasp",
    execute ? "EXECUTE" : "PLAN-ONLY");

  PlanningSceneInterface planning_scene;
  if (!WaitForSceneObjects(node, planning_scene, {"care_table", cup_name}, object_wait_seconds)) {
    return 3;
  }

  MoveGroupInterface arm(node, arm_group);
  MoveGroupInterface gripper(node, gripper_group);
  arm.setPlanningTime(planning_time);
  arm.setNumPlanningAttempts(static_cast<unsigned int>(planning_attempts));
  arm.setMaxVelocityScalingFactor(velocity_scaling);
  arm.setMaxAccelerationScalingFactor(acceleration_scaling);
  arm.setGoalPositionTolerance(position_tolerance);
  arm.setGoalOrientationTolerance(orientation_tolerance);
  arm.allowReplanning(false);

  if (!arm.setEndEffectorLink(end_effector_link)) {
    RCLCPP_ERROR(
      node->get_logger(), "MoveIt rejected end-effector link '%s'.", end_effector_link.c_str());
    return 4;
  }
  if (require_zero && !IsNearZero(node, arm, zero_tolerance)) {
    RCLCPP_ERROR(
      node->get_logger(), "Use RViz Stored State 'zero', then run the pregrasp test again.");
    return 4;
  }

  TrajectoryVisualizer trajectory_visualizer(
    node, arm, end_effector_link, trajectory_preview_seconds);
  trajectory_visualizer.Clear();

  const auto cup_objects = planning_scene.getObjects({cup_name});
  const auto cup_iterator = cup_objects.find(cup_name);
  if (cup_iterator == cup_objects.end() || cup_iterator->second.primitive_poses.empty()) {
    RCLCPP_ERROR(node->get_logger(), "Cup geometry or pose is missing from the planning scene.");
    return 5;
  }

  const auto & cup_object = cup_iterator->second;
  tf2::Transform object_transform;
  tf2::Transform primitive_transform;
  tf2::fromMsg(cup_object.pose, object_transform);
  tf2::fromMsg(cup_object.primitive_poses.front(), primitive_transform);
  const tf2::Transform cup_transform = object_transform * primitive_transform;
  geometry_msgs::msg::Pose cup_pose;
  tf2::toMsg(cup_transform, cup_pose);
  const auto current_gripper_pose = arm.getCurrentPose(end_effector_link);
  if (current_gripper_pose.header.frame_id.empty()) {
    RCLCPP_ERROR(node->get_logger(), "Current gripper pose is unavailable.");
    return 5;
  }

  geometry_msgs::msg::PoseStamped target;
  target.header.frame_id = cup_object.header.frame_id.empty() ?
    arm.getPlanningFrame() : cup_object.header.frame_id;
  if (current_gripper_pose.header.frame_id != target.header.frame_id) {
    RCLCPP_ERROR(
      node->get_logger(), "Frame mismatch: current gripper is in '%s', cup is in '%s'.",
      current_gripper_pose.header.frame_id.c_str(), target.header.frame_id.c_str());
    return 5;
  }
  target.header.stamp = node->now();
  tf2::Quaternion top_down_orientation;
  top_down_orientation.setRPY(0.0, std::acos(-1.0), grasp_yaw);
  top_down_orientation.normalize();
  target.pose.orientation = tf2::toMsg(top_down_orientation);
  target.pose.position.x = cup_pose.position.x;
  target.pose.position.y = cup_pose.position.y;
  const double grasp_base_z =
    cup_pose.position.z + gripper_tip_offset + grasp_height_offset;
  target.pose.position.z = grasp_base_z + pregrasp_clearance;

  auto target_publisher = node->create_publisher<geometry_msgs::msg::PoseStamped>(
    "/brain_robot_pick_place/pregrasp_target", rclcpp::QoS(1).transient_local());
  target_publisher->publish(target);

  RCLCPP_INFO(
    node->get_logger(),
    "Top-down grasp: cup center (%.3f, %.3f, %.3f); pregrasp target (%.3f, %.3f, %.3f).",
    cup_pose.position.x, cup_pose.position.y, cup_pose.position.z,
    target.pose.position.x, target.pose.position.y, target.pose.position.z);

  if (execute && !MoveGripper(node, gripper, "open")) {
    return 6;
  }

  arm.setStartStateToCurrentState();
  arm.setPoseReferenceFrame(target.header.frame_id);
  if (!arm.setPoseTarget(target, end_effector_link)) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt rejected the pregrasp pose target.");
    return 7;
  }

  MoveGroupInterface::Plan plan;
  if (!static_cast<bool>(arm.plan(plan))) {
    RCLCPP_ERROR(
      node->get_logger(), "Pregrasp planning failed; no trajectory was executed.");
    arm.clearPoseTargets();
    return 7;
  }
  arm.clearPoseTargets();

  RCLCPP_INFO(
    node->get_logger(), "Pregrasp plan succeeded with %zu trajectory points.",
    plan.trajectory_.joint_trajectory.points.size());
  trajectory_visualizer.Publish(plan, "PREGRASP");
  if (!execute) {
    RCLCPP_WARN(
      node->get_logger(),
      "PLAN-ONLY finished: the arm did not move. Re-run with execute:=true only after checking this target.");
    return 0;
  }

  if (!static_cast<bool>(arm.execute(plan))) {
    RCLCPP_ERROR(node->get_logger(), "Pregrasp execution failed or was rejected.");
    return 8;
  }

  RCLCPP_INFO(node->get_logger(), "PREGRASP reached.");
  if (!full_sequence) {
    RCLCPP_INFO(node->get_logger(), "Stopping before cup contact.");
    return 0;
  }

  geometry_msgs::msg::PoseStamped above_target = target;
  above_target.header.stamp = node->now();
  above_target.pose.position.z = grasp_base_z + approach_clearance;
  if (!MoveArmToPose(
      node, arm, above_target, end_effector_link, "ABOVE_CUP", trajectory_visualizer))
  {
    return 9;
  }

  auto remove_cup = cup_object;
  remove_cup.operation = moveit_msgs::msg::CollisionObject::REMOVE;
  if (!planning_scene.applyCollisionObject(remove_cup)) {
    RCLCPP_ERROR(node->get_logger(), "Could not temporarily remove cup collision object.");
    return 10;
  }

  geometry_msgs::msg::PoseStamped grasp_target = above_target;
  grasp_target.header.stamp = node->now();
  grasp_target.pose.position.z = grasp_base_z;
  if (!MoveArmToPose(
      node, arm, grasp_target, end_effector_link, "DESCEND", trajectory_visualizer))
  {
    return 11;
  }
  if (observation_pause_seconds > 0.0) {
    RCLCPP_INFO(
      node->get_logger(), "Holding at DESCEND for %.1f seconds.",
      observation_pause_seconds);
    std::this_thread::sleep_for(std::chrono::duration<double>(observation_pause_seconds));
  }
  if (!MoveGripper(node, gripper, "close")) {
    return 12;
  }
  if (observation_pause_seconds > 0.0) {
    RCLCPP_INFO(
      node->get_logger(), "Holding after gripper close for %.1f seconds.",
      observation_pause_seconds);
    std::this_thread::sleep_for(std::chrono::duration<double>(observation_pause_seconds));
  }

  const auto grasp_gripper_pose = arm.getCurrentPose(end_effector_link);
  if (grasp_gripper_pose.header.frame_id != target.header.frame_id) {
    RCLCPP_ERROR(node->get_logger(), "Cannot attach cup because the gripper frame changed.");
    return 13;
  }
  tf2::Transform grasp_gripper_transform;
  tf2::fromMsg(grasp_gripper_pose.pose, grasp_gripper_transform);
  const tf2::Transform cup_relative_transform = grasp_gripper_transform.inverse() * cup_transform;

  moveit_msgs::msg::AttachedCollisionObject attached_cup;
  attached_cup.link_name = end_effector_link;
  attached_cup.touch_links = gripper.getLinkNames();
  if (std::find(
      attached_cup.touch_links.begin(), attached_cup.touch_links.end(), end_effector_link) ==
    attached_cup.touch_links.end())
  {
    attached_cup.touch_links.push_back(end_effector_link);
  }
  attached_cup.object = cup_object;
  attached_cup.object.header.frame_id = end_effector_link;
  attached_cup.object.pose = geometry_msgs::msg::Pose();
  attached_cup.object.pose.orientation.w = 1.0;
  tf2::toMsg(cup_relative_transform, attached_cup.object.primitive_poses.front());
  attached_cup.object.operation = moveit_msgs::msg::CollisionObject::ADD;
  if (!planning_scene.applyAttachedCollisionObject(attached_cup)) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt could not attach the cup to the gripper.");
    return 13;
  }
  if (!SetCupFollowing(node, true)) {
    return 14;
  }

  geometry_msgs::msg::PoseStamped lift_target = grasp_target;
  lift_target.header.stamp = node->now();
  lift_target.pose.position.z = grasp_base_z + lift_clearance;
  if (!MoveArmToPose(
      node, arm, lift_target, end_effector_link, "LIFT", trajectory_visualizer))
  {
    return 15;
  }

  geometry_msgs::msg::PoseStamped transfer_target = lift_target;
  transfer_target.header.stamp = node->now();
  transfer_target.pose.position.x = place_x;
  transfer_target.pose.position.y = place_y;
  if (!MoveArmToPose(
      node, arm, transfer_target, end_effector_link, "TRANSFER", trajectory_visualizer))
  {
    return 16;
  }

  geometry_msgs::msg::PoseStamped place_target = transfer_target;
  place_target.header.stamp = node->now();
  place_target.pose.position.z = grasp_base_z;
  if (!MoveArmToPose(
      node, arm, place_target, end_effector_link, "LOWER", trajectory_visualizer))
  {
    return 17;
  }

  if (!SetCupFollowing(node, false)) {
    return 18;
  }
  const auto place_gripper_pose = arm.getCurrentPose(end_effector_link);
  tf2::Transform place_gripper_transform;
  tf2::fromMsg(place_gripper_pose.pose, place_gripper_transform);
  const tf2::Transform placed_cup_transform =
    place_gripper_transform * cup_relative_transform;

  auto detached_cup = attached_cup;
  detached_cup.object.operation = moveit_msgs::msg::CollisionObject::REMOVE;
  if (!planning_scene.applyAttachedCollisionObject(detached_cup)) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt could not detach the cup.");
    return 19;
  }

  if (!MoveGripper(node, gripper, "open")) {
    return 20;
  }

  auto placed_cup = cup_object;
  placed_cup.header.frame_id = target.header.frame_id;
  placed_cup.pose = geometry_msgs::msg::Pose();
  placed_cup.pose.orientation.w = 1.0;
  tf2::toMsg(placed_cup_transform, placed_cup.primitive_poses.front());
  placed_cup.operation = moveit_msgs::msg::CollisionObject::ADD;
  if (!planning_scene.applyCollisionObject(placed_cup)) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt could not restore the placed cup.");
    return 21;
  }

  geometry_msgs::msg::PoseStamped retreat_target = place_target;
  retreat_target.header.stamp = node->now();
  retreat_target.pose.position.z = grasp_base_z + lift_clearance;
  if (!MoveArmToPose(
      node, arm, retreat_target, end_effector_link, "RETREAT", trajectory_visualizer))
  {
    return 22;
  }

  RCLCPP_INFO(
    node->get_logger(),
    "SIMULATION PICK-AND-PLACE completed: cup moved from (%.3f, %.3f) to (%.3f, %.3f).",
    cup_pose.position.x, cup_pose.position.y, place_x, place_y);
  return 0;
}

}  // namespace brain_robot_pick_place

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  const auto options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true);
  const auto node = rclcpp::Node::make_shared("pick_place_node", options);

  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  std::thread spin_thread([&executor]() {executor.spin();});

  int result = 1;
  try {
    result = brain_robot_pick_place::RunPregrasp(node);
  } catch (const std::exception & exception) {
    RCLCPP_ERROR(node->get_logger(), "Pregrasp node failed: %s", exception.what());
  }

  rclcpp::shutdown();
  spin_thread.join();
  return result;
}
