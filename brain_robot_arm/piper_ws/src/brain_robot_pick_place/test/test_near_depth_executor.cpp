// Controller-free domain-78 tests of the ACTUAL executor methods. Feedback,
// images and TF are synthetic memory inputs; no trajectory/gripper call runs.
#include <cstdlib>
#include <gtest/gtest.h>
#define main unused_grasp_lift_program_main
#include "../src/grasp_lift_executor.cpp"
#undef main

namespace brain_robot_pick_place
{
struct NearDepthReplayAccess
{
  static void Inputs(GraspLiftExecutor & n, bool depth = true)
  {
    const auto receipt = std::chrono::steady_clock::now();
    const auto stamp = n.now() - rclcpp::Duration::from_seconds(.001);
    n.near_calibration_ = {201, 201, 100, 100, 100, 100, false,
      {1, 0, 0, 0, 1, 0, 0, 0, 1}, {0, 0, 0}};
    n.near_calibration_ready_ = true;
    n.target_model_locked_ = true;
    if (n.locked_target_reference_.header.frame_id.empty()) {
      n.locked_target_reference_.header.frame_id = "base_link";
      n.locked_target_reference_.header.stamp = stamp;
      n.locked_target_reference_.point.z = .1238;
    }
    n.locked_object_size_m_ = .033;
    n.qualified_box_message_.header.frame_id = "camera_depth_optical_frame";
    n.qualified_box_message_.header.stamp = stamp;
    n.qualified_box_message_.polygon.points.clear();
    for (const auto & xy : {std::pair<float, float>{.4, .4}, {.6, .4}, {.6, .6}, {.4, .6}}) {
      geometry_msgs::msg::Point32 p; p.x = xy.first; p.y = xy.second;
      n.qualified_box_message_.polygon.points.push_back(p);
    }
    n.qualified_box_received_ = receipt;
    n.raw_image_info_.header = n.qualified_box_message_.header;
    n.raw_image_info_.width = n.raw_image_info_.height = 200;
    n.latest_joint_state_.header.stamp = stamp;
    n.latest_joint_state_.name = {"joint1", "joint2", "joint3", "joint4", "joint5", "joint6"};
    n.latest_joint_state_.position = {0, 0, 0, 0, 0, 0};
    n.joint_state_received_time_ = receipt;
    n.latest_gripper_feedback_.header.stamp = stamp;
    n.latest_gripper_feedback_.name = {"gripper"};
    n.latest_gripper_feedback_.position = {.05};
    n.gripper_feedback_received_time_ = receipt;
    n.target_valid_ = n.depth_valid_ = depth;
    n.target_point_camera_ = n.locked_target_reference_;
    n.target_point_camera_.header = n.qualified_box_message_.header;
    n.target_size_.header = n.qualified_box_message_.header;
    n.target_size_.vector.x = n.target_size_.vector.y = .033;
    n.target_point_received_time_ = n.target_valid_received_time_ =
      n.depth_valid_received_time_ = n.target_size_received_time_ = receipt;
    for (const auto & frame : {"camera_depth_optical_frame", "gripper_base"}) {
      geometry_msgs::msg::TransformStamped transform;
      transform.header.frame_id = "base_link"; transform.child_frame_id = frame;
      transform.header.stamp = stamp; transform.transform.rotation.w = 1;
      n.tf_buffer_->setTransform(transform, "synthetic_offline_fixture", true);
    }
  }

  static bool Observe(GraspLiftExecutor & n, bool & predicted, geometry_msgs::msg::PointStamped & p)
  {
    rclcpp::Time stamp(0, 0, n.get_clock()->get_clock_type());
    return n.ObserveLockedTarget(p, stamp, predicted);
  }
  static bool Capture(GraspLiftExecutor & n) {return n.FreshFaceInsideJaws();}
  static void NoSeed(GraspLiftExecutor & n) {n.near_seed_.valid = false;}
  static void LostRGB(GraspLiftExecutor & n) {n.qualified_box_message_.polygon.points.clear();}
  static void MissingAxis(GraspLiftExecutor & n) {n.latest_joint_state_.name.pop_back();}
  static void BadOpening(GraspLiftExecutor & n) {n.latest_gripper_feedback_.position[0] = .1019;}
  static bool DepthFlag(GraspLiftExecutor & n) {return n.depth_valid_;}
  static void ChangedDepth(GraspLiftExecutor & n) {n.target_point_camera_.point.z += .050;}
  static int64_t SeedStamp(GraspLiftExecutor & n) {return n.near_seed_stamp_ns_;}
  static void ExhaustTravel(GraspLiftExecutor & n) {n.near_camera_travel_m_ = .03001;}
  static void ExhaustAge(GraspLiftExecutor & n) {
    n.near_seed_stamp_ns_ = n.now().nanoseconds() - 31000000000LL;
  }
  static auto Lock(GraspLiftExecutor & n) {return n.locked_target_reference_;}
  static void InvalidateCalibration(GraspLiftExecutor & n) {n.near_calibration_ready_ = false;}
  static bool FactoryLoaded(GraspLiftExecutor & n) {
    std::lock_guard<std::mutex> lock(n.visual_mutex_);
    return n.near_calibration_ready_ && n.near_calibration_.width == 640 &&
      n.near_calibration_.fx == 488.86849976;
  }
};
}  // namespace brain_robot_pick_place

using brain_robot_pick_place::GraspLiftExecutor;
using brain_robot_pick_place::NearDepthReplayAccess;

class NearDepthExecutor : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    ASSERT_NE(std::getenv("ROS_DOMAIN_ID"), nullptr);
    ASSERT_STREQ(std::getenv("ROS_DOMAIN_ID"), "78");
    rclcpp::init(0, nullptr);
  }
  static void TearDownTestSuite() {rclcpp::shutdown();}
  void SetUp() override
  {
    auto options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true);
    options.parameter_overrides({{"simulation_only", false}, {"auto_execute", false},
      {"real_grasp_enabled", false}, {"near_depth_rgb_tracking_enabled", true},
      {"static_target_lock", true}, {"lift_reference_frame", "base_link"},
      {"camera_optical_frame", "camera_depth_optical_frame"}});
    node = std::make_shared<GraspLiftExecutor>(options);
    NearDepthReplayAccess::Inputs(*node);
  }
  std::shared_ptr<GraspLiftExecutor> node;
};

TEST_F(NearDepthExecutor, RealMethodsSwitchToRGBPredictionWithoutRefreshingDepthOrLock)
{
  geometry_msgs::msg::PointStamped p;
  bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_FALSE(predicted);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(predicted);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
  EXPECT_EQ(p.header.stamp, locked.header.stamp);
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
  EXPECT_DOUBLE_EQ(p.point.z, locked.point.z);
}

TEST_F(NearDepthExecutor, NoInitialDepthCannotBootstrapPrediction)
{
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::NoSeed(*node);
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
}

TEST_F(NearDepthExecutor, InconsistentDepthUsesBoundedPredictionWithoutRefreshingSeed)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  for (int i = 0; i < 6; ++i) {
    NearDepthReplayAccess::Inputs(*node);
    NearDepthReplayAccess::ChangedDepth(*node);
    ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
    EXPECT_TRUE(predicted);
    EXPECT_TRUE(NearDepthReplayAccess::DepthFlag(*node));  // Raw detector flag is untouched.
    EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
    EXPECT_EQ(p.header.stamp, locked.header.stamp);
    EXPECT_DOUBLE_EQ(p.point.z, locked.point.z);
  }
  NearDepthReplayAccess::ExhaustTravel(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
}

TEST_F(NearDepthExecutor, InconsistentDepthCannotExtendAgeOrBootstrapMissingSeed)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Inputs(*node);
  NearDepthReplayAccess::ChangedDepth(*node);
  NearDepthReplayAccess::ExhaustAge(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::NoSeed(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
}

TEST_F(NearDepthExecutor, ActualLostRGBAndMissingAxisAreRejected)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::LostRGB(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::MissingAxis(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
}

TEST_F(NearDepthExecutor, ActualJawCheckSupportsBothModesButRejectsImpossibleOpening)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));  // Fresh measured branch.
  NearDepthReplayAccess::Inputs(*node, false);
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));  // Associated prediction branch.
  NearDepthReplayAccess::BadOpening(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
}

TEST_F(NearDepthExecutor, FactoryCalibrationReadThroughStandardROSParameterService)
{
  NearDepthReplayAccess::InvalidateCalibration(*node);
  auto detector = std::make_shared<rclcpp::Node>("cube_detector");
  detector->declare_parameter("software_registration_enabled", true);
  detector->declare_parameter("color_calibration_width", 640);
  detector->declare_parameter("color_calibration_height", 480);
  detector->declare_parameter("color_fx", 488.86849976);
  detector->declare_parameter("color_fy", 488.86849976);
  detector->declare_parameter("color_cx", 310.73052979);
  detector->declare_parameter("color_cy", 209.03765869);
  detector->declare_parameter("color_mirror_horizontal", false);
  detector->declare_parameter("depth_to_color_rotation",
    std::vector<double>{1, 0, 0, 0, 1, 0, 0, 0, 1});
  detector->declare_parameter("depth_to_color_translation_m", std::vector<double>{0, 0, 0});
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node); executor.add_node(detector);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!NearDepthReplayAccess::FactoryLoaded(*node) && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  EXPECT_TRUE(NearDepthReplayAccess::FactoryLoaded(*node));
}
