#include <functional>
#include <memory>
#include <mutex>
#include <string>

#include <gazebo/common/Events.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo_ros/node.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <rclcpp/rclcpp.hpp>

namespace brain_robot_pick_place
{

class CupPosePlugin : public gazebo::ModelPlugin
{
public:
  void Load(gazebo::physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    model_ = std::move(model);
    ros_node_ = gazebo_ros::Node::Get(sdf);

    std::string topic = "cup_target_pose";
    if (sdf->HasElement("topic")) {
      topic = sdf->GetElement("topic")->Get<std::string>();
    }

    pose_subscription_ = ros_node_->create_subscription<geometry_msgs::msg::Pose>(
      topic, rclcpp::QoS(1).reliable(),
      std::bind(&CupPosePlugin::OnPose, this, std::placeholders::_1));

    update_connection_ = gazebo::event::Events::ConnectWorldUpdateBegin(
      std::bind(&CupPosePlugin::OnUpdate, this, std::placeholders::_1));

    RCLCPP_INFO(
      ros_node_->get_logger(), "Cup pose plugin ready; listening on %s",
      pose_subscription_->get_topic_name());
  }

private:
  void OnPose(const geometry_msgs::msg::Pose::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lock(pose_mutex_);
    target_pose_ = *msg;
    has_target_ = true;
  }

  void OnUpdate(const gazebo::common::UpdateInfo &)
  {
    geometry_msgs::msg::Pose target;
    {
      std::lock_guard<std::mutex> lock(pose_mutex_);
      if (!has_target_) {
        return;
      }
      target = target_pose_;
    }

    ignition::math::Quaterniond rotation(
      target.orientation.w, target.orientation.x,
      target.orientation.y, target.orientation.z);
    rotation.Normalize();

    ignition::math::Pose3d world_pose;
    world_pose.Pos().Set(target.position.x, target.position.y, target.position.z);
    world_pose.Rot() = rotation;
    model_->SetWorldPose(world_pose);
    model_->SetLinearVel(ignition::math::Vector3d::Zero);
    model_->SetAngularVel(ignition::math::Vector3d::Zero);
  }

  gazebo::physics::ModelPtr model_;
  gazebo_ros::Node::SharedPtr ros_node_;
  rclcpp::Subscription<geometry_msgs::msg::Pose>::SharedPtr pose_subscription_;
  gazebo::event::ConnectionPtr update_connection_;
  std::mutex pose_mutex_;
  geometry_msgs::msg::Pose target_pose_;
  bool has_target_{false};
};

GZ_REGISTER_MODEL_PLUGIN(CupPosePlugin)

}  // namespace brain_robot_pick_place
