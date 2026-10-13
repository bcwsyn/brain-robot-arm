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
  static bool Correction(GraspLiftExecutor & n, Eigen::Vector3d & delta) {
    return n.LockedRgbCorrection(delta);
  }
  static auto ReducedAttitude(const geometry_msgs::msg::PoseStamped & p,
    const Eigen::Isometry3d & current, double fraction) {
    return GraspLiftExecutor::ReducedVisualOrientationAtSameTip(p, current, .1358, fraction);
  }
  static bool RetryAttitude(GraspLiftExecutor & n, const std::string & stage, bool segment) {
    return n.CanRetryVisualOrientation(stage, segment);
  }
  static bool WaypointReached(const grasp_geometry::DirectedPose & current,
    const grasp_geometry::DirectedPose & nominal,
    const grasp_geometry::DirectedPose * completed = nullptr) {
    return GraspLiftExecutor::RgbWaypointReached(current, nominal, .1358, .01, .12, completed);
  }
  static bool ClipJointPrefix(GraspLiftExecutor & n,
    trajectory_msgs::msg::JointTrajectory & trajectory, std::size_t accepted,
    bool automatic_segment = true) {
    return n.ClipCheckedJointPrefix(trajectory, accepted, "AUTOMATIC_RGB_STEP_0", automatic_segment);
  }
  static auto DelayedCamera(GraspLiftExecutor & n, bool old_only = false) {
    n.camera_optical_frame_ = "delayed_camera_fixture";
    geometry_msgs::msg::TransformStamped t;
    t.header.frame_id = "base_link"; t.child_frame_id = n.camera_optical_frame_;
    t.header.stamp = n.qualified_box_message_.header.stamp;
    t.transform.rotation.w = 1;
    if (old_only) {
      t.header.stamp = rclcpp::Time(t.header.stamp)-rclcpp::Duration::from_seconds(.01);
      n.tf_buffer_->setTransform(t, "synthetic_old_only_fixture", false);
    }
    return t;
  }
  static void DeliverCamera(GraspLiftExecutor & n, const geometry_msgs::msg::TransformStamped & t) {
    n.tf_buffer_->setTransform(t, "synthetic_delayed_fixture", true);
  }
  static auto ImageStamp(GraspLiftExecutor & n) {return n.qualified_box_message_.header.stamp;}
  static void AgeFeedback(GraspLiftExecutor & n, double seconds) {
    n.latest_joint_state_.header.stamp = n.now()-rclcpp::Duration::from_seconds(seconds);
    n.joint_state_received_time_ = std::chrono::steady_clock::now()-
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(seconds));
  }
  static void ShiftCameraY(GraspLiftExecutor & n, double value) {
    geometry_msgs::msg::TransformStamped t;
    t.header.frame_id = "base_link"; t.child_frame_id = "camera_depth_optical_frame";
    t.header.stamp = n.now(); t.transform.rotation.w = 1; t.transform.translation.y = value;
    n.tf_buffer_->setTransform(t, "synthetic_offline_fixture", true);
  }
  static void ColourBoxY(GraspLiftExecutor & n, float top, float bottom) {
    auto & p = n.qualified_box_message_.polygon.points;
    p[0].y = p[1].y = top; p[2].y = p[3].y = bottom;
  }
  static void ClippedRaw(GraspLiftExecutor & n) {
    n.qualified_box_message_.polygon.points.clear();
    n.raw_box_ = {.4, .85, .6, 1}; n.raw_box_valid_ = true;
    n.raw_box_stamp_ns_ = n.now().nanoseconds()-1000000;
    n.raw_box_received_ = std::chrono::steady_clock::now();
  }
  static void NoSeed(GraspLiftExecutor & n) {n.near_seed_.valid = false;}
  static void Automatic(GraspLiftExecutor & n) {
    n.automatic_rgb_approach_enabled_ = true;
    n.quality_driven_depth_stage_enabled_ = false;  // Preserve legacy regressions explicitly.
  }
  static void Coarse(GraspLiftExecutor & n) {
    n.coarse_depth_tracking_ = true; n.quality_driven_depth_stage_enabled_ = false;
  }
  static void QualityStage(GraspLiftExecutor & n) {
    n.automatic_rgb_approach_enabled_ = n.coarse_depth_tracking_ = true;
    n.quality_driven_depth_stage_enabled_ = true;
  }
  static void AtomicObservation(GraspLiftExecutor & n, bool qualified = true, double z = .23,
    double coverage = .5, double span = .9, bool color_center_covered = true) {
    rgbd_observation::Snapshot s;
    s.header = n.target_point_camera_.header; s.point = n.target_point_camera_.point;
    s.point.z = z; s.size = n.target_size_.vector; s.size.z = z;
    s.qualified = qualified; s.samples = qualified ? 1800 : 16;
    s.color_center_covered = color_center_covered;
    s.coverage = coverage; s.span = span; s.mad_m = .002;
    n.rgbd_observations_[rclcpp::Time(s.header.stamp).nanoseconds()] =
      {s, std::chrono::steady_clock::now()};
  }
  static void ReliableHistory(GraspLiftExecutor & n, double range = .23) {
    QualityStage(n);
    for (int i = 0; i < 3; ++i) {
      Inputs(n, true); AtomicObservation(n, true, range);
      bool predicted = false; geometry_msgs::msg::PointStamped p;
      ASSERT_TRUE(Observe(n, predicted, p));
    }
  }
  static bool QualityFreeze(GraspLiftExecutor & n) {return n.FreezeReliableDepthModel("TEST_QUALITY_DROP");}
  static auto QualityHistorySize(GraspLiftExecutor & n) {return n.reliable_depth_models_.size();}
  static void CoarseMotion(GraspLiftExecutor & n) {n.coarse_motion_in_progress_ = true;}
  static void OldSeed(GraspLiftExecutor & n, double age_s) {
    n.near_seed_stamp_ns_ = (n.now()-rclcpp::Duration::from_seconds(age_s)).nanoseconds();
  }
  static void MeasurementZ(GraspLiftExecutor & n, double z) {n.target_point_camera_.point.z = z;}
  static void WrongDepthStamp(GraspLiftExecutor & n) {
    n.target_point_camera_.header.stamp = n.now()-rclcpp::Duration::from_seconds(.01);
  }
  static bool TerminalCommit(GraspLiftExecutor & n, double range = .1238,
    const std::string & frame = "base_link") {
    GraspLiftExecutor::LockedRgbView view;
    view.valid = view.measured_rgbd = true; view.box = {.4, .4, .6, .6};
    view.stamp_ns = rclcpp::Time(n.qualified_box_message_.header.stamp).nanoseconds();
    view.measured_color_range_m = range;
    view.measured_size_m = view.measured_min_size_m = .033;
    auto reference = n.locked_target_reference_; reference.header.frame_id = frame;
    return n.CommitTerminalDepthLock(reference, view);
  }
  static void LostRGB(GraspLiftExecutor & n) {n.qualified_box_message_.polygon.points.clear();}
  static void MissingAxis(GraspLiftExecutor & n) {n.latest_joint_state_.name.pop_back();}
  static void BadOpening(GraspLiftExecutor & n) {n.latest_gripper_feedback_.position[0] = .1019;}
  static bool DepthFlag(GraspLiftExecutor & n) {return n.depth_valid_;}
  static auto SeedStamp(GraspLiftExecutor & n) {return n.near_seed_stamp_ns_;}
  static auto SeedImageStamp(GraspLiftExecutor & n) {return n.near_seed_image_stamp_ns_;}
  static void ShiftCameraZ(GraspLiftExecutor & n, double value) {
    geometry_msgs::msg::TransformStamped t;
    t.header.frame_id = "base_link"; t.child_frame_id = "camera_depth_optical_frame";
    t.header.stamp = n.now(); t.transform.rotation.w = 1; t.transform.translation.z = value;
    n.tf_buffer_->setTransform(t, "synthetic_offline_fixture", true);
  }
  static auto Seed(GraspLiftExecutor & n) {return n.near_seed_;}
  static void Travel(GraspLiftExecutor & n, double value) {n.near_camera_travel_m_ = value;}
  static double Travel(GraspLiftExecutor & n) {return n.near_camera_travel_m_;}
  static void ReviewedAllowance(GraspLiftExecutor & n, double path_m) {
    n.near_path_allowance_ready_ = true;
    n.near_path_max_travel_m_ = path_m + n.near_depth_prediction_max_travel_m_;
    n.near_path_max_age_s_ = 100;
  }
  static void MoveObservation(GraspLiftExecutor & n, double x) {n.target_point_camera_.point.x = x;}
  static void ShiftColourBox(GraspLiftExecutor & n, float x) {
    for (auto & p : n.qualified_box_message_.polygon.points) {p.x += x;}
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

TEST_F(NearDepthExecutor, ScaleDiagnosticsExposeOriginalRatiosWithoutChangingRejectionOrSeed)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto seed = NearDepthReplayAccess::Seed(*node);
  const auto stamp = NearDepthReplayAccess::SeedStamp(*node);
  const auto image_stamp = NearDepthReplayAccess::SeedImageStamp(*node);
  EXPECT_GT(image_stamp, 0);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::ShiftCameraZ(*node, .070);
  // This synthetic view change exceeds the normal 30mm episode allowance.
  // Model an already-reviewed path so the ORIGINAL scale branch is reached.
  NearDepthReplayAccess::ReviewedAllowance(*node, .080);
  testing::internal::CaptureStderr();
  const bool accepted = NearDepthReplayAccess::Observe(*node, predicted, p);
  const auto log = testing::internal::GetCapturedStderr();
  EXPECT_FALSE(accepted);
  EXPECT_NE(log.find("NEAR_RGB_SCALE_DETAIL"), std::string::npos);
  const auto ratio_position = log.find("width_ratio=");
  EXPECT_NE(ratio_position, std::string::npos);
  if (ratio_position != std::string::npos) {
    EXPECT_NEAR(std::stod(log.substr(ratio_position+12)), (.1238-.070)/.1238, 1e-12);
  }
  EXPECT_NE(log.find("original_bounds=(0.65,1.5)"), std::string::npos);
  EXPECT_NE(log.find("NEAR_RGB_SCALE_GEOMETRY"), std::string::npos);
  EXPECT_NE(log.find("NOT_IMAGE_TIME_Q"), std::string::npos);
  // The existing generic reject warning is throttled across observations.
  // DETAIL is emitted only by the scale branch; don't depend on that throttle.
  EXPECT_NE(log.find("depth_used=0"), std::string::npos);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedImageStamp(*node), image_stamp);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Seed(*node).color_z, seed.color_z);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
}

TEST_F(NearDepthExecutor, AutomaticScaleMismatchContinuesVisualCorrectionWithoutRelockOrClose)
{
  // Exercise the owning executor, not only the standalone scale-policy helper.
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed = NearDepthReplayAccess::Seed(*node);
  const auto stamp = NearDepthReplayAccess::SeedStamp(*node);
  const auto image_stamp = NearDepthReplayAccess::SeedImageStamp(*node);
  NearDepthReplayAccess::Automatic(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::ShiftCameraZ(*node, .070);
  NearDepthReplayAccess::ReviewedAllowance(*node, .080);
  NearDepthReplayAccess::ShiftColourBox(*node, .03f);
  Eigen::Vector3d correction;
  testing::internal::CaptureStderr();
  const bool accepted = NearDepthReplayAccess::Correction(*node, correction);
  const auto log = testing::internal::GetCapturedStderr();
  EXPECT_TRUE(accepted);
  EXPECT_GT(correction.norm(), .001);  // Live colour residual still reaches correction.
  EXPECT_NE(log.find("NEAR_RGB_SCALE_ADVISORY_CONTINUE_VISUAL_CORRECTION"), std::string::npos);
  EXPECT_NE(log.find("NEAR_RGB_SCALE_DETAIL"), std::string::npos);
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Lock(*node).point.z, locked.point.z);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedImageStamp(*node), image_stamp);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Seed(*node).color_z, seed.color_z);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));  // Final jaw decision unchanged.
  NearDepthReplayAccess::LostRGB(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Correction(*node, correction));
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::MissingAxis(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Correction(*node, correction));
}

TEST_F(NearDepthExecutor, DelayedExactTfRecoversSameFrameWithoutRelock)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto lock = NearDepthReplayAccess::Lock(*node);
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::Automatic(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  const auto image_stamp = NearDepthReplayAccess::ImageStamp(*node);
  const auto t = NearDepthReplayAccess::DelayedCamera(*node);
  std::thread arrival([this, t]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(330));
    NearDepthReplayAccess::DeliverCamera(*node, t);
  });
  Eigen::Vector3d correction;
  testing::internal::CaptureStderr();
  const bool accepted = NearDepthReplayAccess::Correction(*node, correction);
  arrival.join();
  const auto log = testing::internal::GetCapturedStderr();
  EXPECT_TRUE(accepted);
  EXPECT_NE(log.find("NEAR_RGB_EXACT_TF_WAIT"), std::string::npos);
  EXPECT_NE(log.find("NEAR_RGB_EXACT_TF_RECOVERED"), std::string::npos);
  EXPECT_NE(log.find("image_stamp="+std::to_string(rclcpp::Time(image_stamp).nanoseconds())), std::string::npos);
  EXPECT_EQ(NearDepthReplayAccess::ImageStamp(*node), image_stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, lock.header.stamp);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
}

TEST_F(NearDepthExecutor, OldLatestTfCannotSubstituteForExactImageAfterFiniteRetries)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Automatic(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::DelayedCamera(*node, true);
  Eigen::Vector3d correction;
  testing::internal::CaptureStderr();
  const bool accepted = NearDepthReplayAccess::Correction(*node, correction);
  const auto log = testing::internal::GetCapturedStderr();
  EXPECT_FALSE(accepted);
  EXPECT_NE(log.find("attempt=3"), std::string::npos);
  EXPECT_NE(log.find("NEAR_RGB_EXACT_TF_FAILED"), std::string::npos);
  EXPECT_NE(log.find("error="), std::string::npos);
  EXPECT_EQ(log.find("NEAR_RGB_EXACT_TF_RECOVERED"), std::string::npos);
}

TEST_F(NearDepthExecutor, FeedbackAgingDuringExactTfWaitStillBlocksCorrection)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Automatic(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::AgeFeedback(*node, .4);
  const auto t = NearDepthReplayAccess::DelayedCamera(*node);
  std::thread arrival([this, t]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(330));
    NearDepthReplayAccess::DeliverCamera(*node, t);
  });
  Eigen::Vector3d correction;
  const bool accepted = NearDepthReplayAccess::Correction(*node, correction);
  arrival.join();
  EXPECT_FALSE(accepted);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
}

TEST_F(NearDepthExecutor, ReducedVisualAttitudesPreserveTipAndKeepTurningTowardTarget)
{
  Eigen::Isometry3d current = Eigen::Isometry3d::Identity();
  current.translation() = Eigen::Vector3d(.35, -.12, .26);
  geometry_msgs::msg::PoseStamped target;
  target.header.frame_id = "base_link"; target.header.stamp = node->now();
  target.pose.position.x = .356; target.pose.position.y = -.116; target.pose.position.z = .255;
  const Eigen::Quaterniond desired(Eigen::AngleAxisd(.01745329252, Eigen::Vector3d::UnitY()));
  target.pose.orientation.x = desired.x(); target.pose.orientation.y = desired.y();
  target.pose.orientation.z = desired.z(); target.pose.orientation.w = desired.w();
  const Eigen::Vector3d local_tip(0, 0, .1358);
  const Eigen::Vector3d tip = Eigen::Vector3d(.356, -.116, .255) + desired * local_tip;
  for (double fraction : {.75, .50, .25}) {
    const auto p = NearDepthReplayAccess::ReducedAttitude(target, current, fraction);
    const Eigen::Quaterniond q(p.pose.orientation.w, p.pose.orientation.x,
      p.pose.orientation.y, p.pose.orientation.z);
    const Eigen::Vector3d point(p.pose.position.x, p.pose.position.y, p.pose.position.z);
    EXPECT_LT((point + q * local_tip - tip).norm(), 1e-12);
    EXPECT_NEAR(Eigen::Quaterniond(current.rotation()).angularDistance(q),
      fraction * .01745329252, 1e-12);
    EXPECT_GT(Eigen::Quaterniond(current.rotation()).angularDistance(q), 0);
    EXPECT_EQ(p.header.frame_id, target.header.frame_id);
    EXPECT_EQ(p.header.stamp, target.header.stamp);
  }
}

TEST_F(NearDepthExecutor, ReducedVisualAttitudeRejectsZeroFractionAndInvalidQuaternion)
{
  geometry_msgs::msg::PoseStamped p;
  p.pose.orientation.w = 1;
  const auto current = Eigen::Isometry3d::Identity();
  EXPECT_THROW(NearDepthReplayAccess::ReducedAttitude(p, current, 0), std::invalid_argument);
  EXPECT_THROW(NearDepthReplayAccess::ReducedAttitude(p, current, 1), std::invalid_argument);
  EXPECT_THROW(NearDepthReplayAccess::ReducedAttitude(p, current, -1.01), std::invalid_argument);
  p.pose.orientation.w = 0;
  EXPECT_THROW(NearDepthReplayAccess::ReducedAttitude(p, current, .5), std::invalid_argument);
}

TEST_F(NearDepthExecutor, ReverseVisualAttitudesPreserveTipAndStayWithinRequestedAngularStep)
{
  Eigen::Isometry3d current = Eigen::Isometry3d::Identity();
  const Eigen::Quaterniond start(Eigen::AngleAxisd(.6, Eigen::Vector3d::UnitX()));
  current.linear() = start.toRotationMatrix();
  current.translation() = Eigen::Vector3d(.35, -.12, .26);
  geometry_msgs::msg::PoseStamped target;
  target.header.frame_id = "base_link"; target.header.stamp = node->now();
  const Eigen::Vector3d origin(.356, -.116, .255), local_tip(0, 0, .1358);
  const Eigen::Quaterniond desired = start * Eigen::Quaterniond(
    Eigen::AngleAxisd(.01745329252, Eigen::Vector3d::UnitY()));
  target.pose.position.x = origin.x(); target.pose.position.y = origin.y();
  target.pose.position.z = origin.z();
  target.pose.orientation.x = desired.x(); target.pose.orientation.y = desired.y();
  target.pose.orientation.z = desired.z(); target.pose.orientation.w = desired.w();
  for (double fraction : {-.25, -.50, -.75, -1.0}) {
    const auto p = NearDepthReplayAccess::ReducedAttitude(target, current, fraction);
    const Eigen::Quaterniond q(p.pose.orientation.w, p.pose.orientation.x,
      p.pose.orientation.y, p.pose.orientation.z);
    const Eigen::Vector3d position(p.pose.position.x, p.pose.position.y, p.pose.position.z);
    EXPECT_LT((position + q * local_tip - origin - desired * local_tip).norm(), 1e-12);
    EXPECT_NEAR(start.angularDistance(q), -fraction * .01745329252, 1e-12);
    EXPECT_LE(start.angularDistance(q), .01745329252 + 1e-12);
    EXPECT_LT((start.conjugate() * q).vec().dot(Eigen::Vector3d::UnitY()), 0);
    EXPECT_EQ(p.header.frame_id, target.header.frame_id);
    EXPECT_EQ(p.header.stamp, target.header.stamp);
  }
}

TEST_F(NearDepthExecutor, ReducedAttitudeRetryIsOnlyAutomaticApproachPlanning)
{
  EXPECT_FALSE(NearDepthReplayAccess::RetryAttitude(*node, "AUTOMATIC_RGB_STEP_107", true));
  NearDepthReplayAccess::Automatic(*node);
  EXPECT_TRUE(NearDepthReplayAccess::RetryAttitude(*node, "AUTOMATIC_RGB_STEP_107", true));
  EXPECT_FALSE(NearDepthReplayAccess::RetryAttitude(*node, "AUTOMATIC_RGB_STEP_107", false));
  EXPECT_FALSE(NearDepthReplayAccess::RetryAttitude(*node, "VISUAL_PREVIEW", true));
  EXPECT_FALSE(NearDepthReplayAccess::RetryAttitude(*node, "TARGET_DIRECTED_DESCENT", true));
}

TEST_F(NearDepthExecutor, CompletedReachableAttitudeAdvancesAtOriginalNominalTip)
{
  namespace gg = brain_robot_pick_place::grasp_geometry;
  const gg::DirectedPose nominal{{.3, -.1, .2}, {0, std::sin(.3/2), 0, std::cos(.3/2)}};
  const auto tip = gg::Tip(nominal.origin, gg::Rotate(nominal.orientation, {0, 0, 1}), .1358);
  gg::DirectedPose completed{{tip[0], tip[1], tip[2]-.1358}, {0, 0, 0, 1}};
  auto measured = completed;
  measured.origin[0] += .0008;  // Actual stuck-step feedback was within 0.5--0.8 mm.
  EXPECT_FALSE(NearDepthReplayAccess::WaypointReached(measured, nominal));
  EXPECT_TRUE(NearDepthReplayAccess::WaypointReached(measured, nominal, &completed));
}

TEST_F(NearDepthExecutor, ReachableAttitudeCannotSkipAnUnreachedTipOrChangedCorrection)
{
  namespace gg = brain_robot_pick_place::grasp_geometry;
  gg::DirectedPose nominal{{.3, -.1, .2}, {0, 0, 0, 1}};
  const auto completed = nominal;
  auto measured = completed; measured.origin[2] += .0101;
  EXPECT_FALSE(NearDepthReplayAccess::WaypointReached(measured, nominal, &completed));
  measured = completed; nominal.origin[0] += .02;
  EXPECT_FALSE(NearDepthReplayAccess::WaypointReached(measured, nominal, &completed));
}

TEST_F(NearDepthExecutor, ReachableAttitudeStillRequiresActualOrientationArrival)
{
  namespace gg = brain_robot_pick_place::grasp_geometry;
  const gg::DirectedPose completed{{.3, -.1, .2}, {0, 0, 0, 1}};
  auto measured = completed;
  measured.orientation = {0, std::sin(.13/2), 0, std::cos(.13/2)};
  const auto axis = gg::Rotate(measured.orientation, {0, 0, 1});
  const auto tip = gg::Tip(completed.origin, {0, 0, 1}, .1358);
  for (int i = 0; i < 3; ++i) {measured.origin[i] = tip[i] - axis[i]*.1358;}
  EXPECT_FALSE(NearDepthReplayAccess::WaypointReached(measured, completed, &completed));
}

TEST_F(NearDepthExecutor, WithoutCompletedCandidateOriginalOrientationRuleRemains)
{
  namespace gg = brain_robot_pick_place::grasp_geometry;
  const gg::DirectedPose nominal{{.3, -.1, .2}, {0, 0, 0, 1}};
  EXPECT_TRUE(NearDepthReplayAccess::WaypointReached(nominal, nominal));
  auto measured = nominal; measured.origin[0] += .011;
  EXPECT_FALSE(NearDepthReplayAccess::WaypointReached(measured, nominal));
}

TEST_F(NearDepthExecutor, JointTravelReplansAfterOnlyTheAlreadyCheckedMovingPrefix)
{
  NearDepthReplayAccess::Automatic(*node);
  trajectory_msgs::msg::JointTrajectory trajectory;
  trajectory.joint_names = {"joint1"};
  for (double angle : {0., .04, .081, .12}) {
    trajectory_msgs::msg::JointTrajectoryPoint p; p.positions = {angle};
    p.time_from_start.sec = trajectory.points.size(); trajectory.points.push_back(p);
  }
  const auto original = trajectory;
  ASSERT_TRUE(NearDepthReplayAccess::ClipJointPrefix(*node, trajectory, 2));
  ASSERT_EQ(trajectory.points.size(), 2u);
  EXPECT_EQ(trajectory.joint_names, original.joint_names);
  EXPECT_EQ(trajectory.points[0], original.points[0]);
  EXPECT_EQ(trajectory.points[1], original.points[1]);
  EXPECT_LE(std::abs(trajectory.points.back().positions[0]), .08);
}

TEST_F(NearDepthExecutor, JointTravelCannotClipPreviewOrAnInsufficientCheckedPrefix)
{
  NearDepthReplayAccess::Automatic(*node);
  trajectory_msgs::msg::JointTrajectory trajectory;
  trajectory.joint_names = {"joint1"}; trajectory.points.resize(4);
  const auto original = trajectory;
  EXPECT_FALSE(NearDepthReplayAccess::ClipJointPrefix(*node, trajectory, 2, false));
  EXPECT_FALSE(NearDepthReplayAccess::ClipJointPrefix(*node, trajectory, 1));
  EXPECT_FALSE(NearDepthReplayAccess::ClipJointPrefix(*node, trajectory, 4));
  EXPECT_FALSE(NearDepthReplayAccess::ClipJointPrefix(*node, trajectory, 5));
  EXPECT_EQ(trajectory, original);
}

TEST_F(NearDepthExecutor, CoarseDepthRefreshesSameIdentityDespiteLongRangeModelBias)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  NearDepthReplayAccess::MeasurementZ(*node, .22);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_FALSE(predicted);
  EXPECT_DOUBLE_EQ(reference.point.z, .22);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Lock(*node).point.z, .22);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Seed(*node).color_z, .22);
}

TEST_F(NearDepthExecutor, CoarseDepthCannotAdvanceWithoutSameFrameDepthOrContinuousIdentity)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  NearDepthReplayAccess::Inputs(*node, true); NearDepthReplayAccess::WrongDepthStamp(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  NearDepthReplayAccess::Inputs(*node, true); NearDepthReplayAccess::ShiftColourBox(*node, .3f);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
}

TEST_F(NearDepthExecutor, TerminalCommitOnceIgnoresLaterDepthWithoutChangingTheLock)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  ASSERT_TRUE(NearDepthReplayAccess::TerminalCommit(*node));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::Inputs(*node, true); NearDepthReplayAccess::MeasurementZ(*node, .35);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_TRUE(predicted);  // The control point is frozen, not a new depth claim.
  EXPECT_EQ(reference, locked);
  EXPECT_TRUE(NearDepthReplayAccess::DepthFlag(*node));
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed);
  EXPECT_FALSE(NearDepthReplayAccess::TerminalCommit(*node));
}

TEST_F(NearDepthExecutor, CoarseMotionKeepsStepPointAndAllowsAsynchronousDepth)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::CoarseMotion(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_TRUE(predicted); EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
  NearDepthReplayAccess::Inputs(*node, true); NearDepthReplayAccess::MeasurementZ(*node, .14);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
}

TEST_F(NearDepthExecutor, FreshCoarseDepthRefreshesOnlyItsOwnStepPredictionAllowance)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  NearDepthReplayAccess::OldSeed(*node, 31);
  NearDepthReplayAccess::Travel(*node, .04);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Travel(*node), 0);
  EXPECT_EQ(NearDepthReplayAccess::SeedImageStamp(*node),
    rclcpp::Time(NearDepthReplayAccess::ImageStamp(*node)).nanoseconds());
  NearDepthReplayAccess::CoarseMotion(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_TRUE(predicted);
}

TEST_F(NearDepthExecutor, FrozenTerminalUsesRGBWithoutDepthButStillRequiresActualFeedback)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  geometry_msgs::msg::PointStamped reference; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  ASSERT_TRUE(NearDepthReplayAccess::TerminalCommit(*node));
  NearDepthReplayAccess::Inputs(*node, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, reference));
  EXPECT_TRUE(predicted); EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
  NearDepthReplayAccess::MissingAxis(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, reference));
}

TEST_F(NearDepthExecutor, TerminalCommitRejectsWrongFrameOrOutsideTheStagingRange)
{
  NearDepthReplayAccess::Automatic(*node); NearDepthReplayAccess::Coarse(*node);
  EXPECT_FALSE(NearDepthReplayAccess::TerminalCommit(*node, .25));
  EXPECT_FALSE(NearDepthReplayAccess::TerminalCommit(*node, .1238, "other_reference"));
}

TEST_F(NearDepthExecutor, AtomicQualityRejectsAdjacentFrameBoolAndKeepsLastWorldModel)
{
  NearDepthReplayAccess::ReliableHistory(*node);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::Inputs(*node, true);  // Stale Bool/raw may still claim validity.
  NearDepthReplayAccess::AtomicObservation(*node, false, .255, .04, .03);
  bool predicted = false; geometry_msgs::msg::PointStamped p;
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
  ASSERT_TRUE(NearDepthReplayAccess::QualityFreeze(*node));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed);  // Never turn old depth into fresh depth.
  EXPECT_TRUE(NearDepthReplayAccess::DepthFlag(*node));
}

TEST_F(NearDepthExecutor, QualifiedButShrunkenDepthStripCannotReplaceTarget)
{
  NearDepthReplayAccess::ReliableHistory(*node);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, true);
  NearDepthReplayAccess::AtomicObservation(*node, true, .255, .04, .03);
  bool predicted = false; geometry_msgs::msg::PointStamped p;
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
  ASSERT_TRUE(NearDepthReplayAccess::QualityFreeze(*node));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
}

TEST_F(NearDepthExecutor, QualityFreezeCompensatesCameraMotionAndDoesNotRequireTwentyCm)
{
  NearDepthReplayAccess::ReliableHistory(*node, .3);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::AtomicObservation(*node, false, .33, .02, .03);
  NearDepthReplayAccess::ShiftCameraZ(*node, .005);
  ASSERT_TRUE(NearDepthReplayAccess::QualityFreeze(*node));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
  EXPECT_NEAR(NearDepthReplayAccess::Travel(*node), .005, 1e-9);
  bool predicted = false; geometry_msgs::msg::PointStamped p;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(predicted); EXPECT_EQ(p, locked);
}

TEST_F(NearDepthExecutor, QualityFreezeStillNeedsLiveSameObjectAndActualSixAxisFeedback)
{
  NearDepthReplayAccess::ReliableHistory(*node);
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false); NearDepthReplayAccess::LostRGB(*node);
  EXPECT_FALSE(NearDepthReplayAccess::QualityFreeze(*node));
  NearDepthReplayAccess::Inputs(*node, false); NearDepthReplayAccess::MissingAxis(*node);
  EXPECT_FALSE(NearDepthReplayAccess::QualityFreeze(*node));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node), locked);
}

TEST_F(NearDepthExecutor, MissingAtomicObservationCannotUseRawBoolToBuildReliableHistory)
{
  NearDepthReplayAccess::QualityStage(*node);
  bool predicted = false; geometry_msgs::msg::PointStamped p;
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_EQ(NearDepthReplayAccess::QualityHistorySize(*node), 0u);
  EXPECT_FALSE(NearDepthReplayAccess::QualityFreeze(*node));
}

TEST_F(NearDepthExecutor, ChangingSilhouetteCentreDoesNotRelockOrStopSurfacePointInsideCube)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::ShiftColourBox(*node, .05f);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(predicted);
  EXPECT_EQ(p.header.stamp, locked.header.stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
  NearDepthReplayAccess::ShiftColourBox(*node, .2f);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
}

TEST_F(NearDepthExecutor, DepthRecoveryDoesNotReplaceTargetOrRefreshSeed)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  const auto seed = NearDepthReplayAccess::Seed(*node);
  NearDepthReplayAccess::Travel(*node, .012);
  NearDepthReplayAccess::Inputs(*node, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  ASSERT_TRUE(predicted);
  NearDepthReplayAccess::Inputs(*node, true);
  NearDepthReplayAccess::MoveObservation(*node, .001);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_FALSE(predicted);
  EXPECT_DOUBLE_EQ(p.point.x, locked.point.x);
  EXPECT_EQ(p.header.stamp, locked.header.stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Seed(*node).color_z, seed.color_z);
  EXPECT_DOUBLE_EQ(NearDepthReplayAccess::Travel(*node), .012);
}

TEST_F(NearDepthExecutor, FreshDepthCannotBypassLockedIdentityAtClosure)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Inputs(*node, true);
  NearDepthReplayAccess::MoveObservation(*node, .06);
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
}

TEST_F(NearDepthExecutor, ProgramComputesRgbCorrectionWhenCurrentDepthIsMissing)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  Eigen::Vector3d correction;
  ASSERT_TRUE(NearDepthReplayAccess::Correction(*node, correction));
  EXPECT_TRUE(correction.allFinite());
  EXPECT_NEAR(correction.z(), 0, 1e-12);
  EXPECT_FALSE(NearDepthReplayAccess::DepthFlag(*node));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
}

TEST_F(NearDepthExecutor, ProjectionOutsideSilhouetteCanActuallyProduceBoundedCorrection)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::ShiftColourBox(*node, .12f);
  Eigen::Vector3d correction;
  ASSERT_TRUE(NearDepthReplayAccess::Correction(*node, correction));
  EXPECT_GT(correction.x(), .025);
  EXPECT_LT(correction.norm(), .04);
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
}

TEST_F(NearDepthExecutor, LargeRgbCorrectionContinuesSameIdentityWithoutRelocking)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::Automatic(*node);
  Eigen::Vector3d correction;
  for (float shift : {.10f, .20f}) {
    NearDepthReplayAccess::Inputs(*node, false);
    NearDepthReplayAccess::ShiftColourBox(*node, shift);
    ASSERT_TRUE(NearDepthReplayAccess::Correction(*node, correction));
  }
  EXPECT_GT(correction.norm(), .04);
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
  NearDepthReplayAccess::Inputs(*node, false);
  EXPECT_FALSE(NearDepthReplayAccess::Correction(*node, correction));  // Identity jump, not magnitude.
}

TEST_F(NearDepthExecutor, RecoveredDepthOutlierDoesNotAbortRgbApproachOrAuthorizeClose)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto locked = NearDepthReplayAccess::Lock(*node);
  NearDepthReplayAccess::Automatic(*node);
  NearDepthReplayAccess::Inputs(*node, true);
  NearDepthReplayAccess::MoveObservation(*node, .06);
  Eigen::Vector3d correction;
  EXPECT_TRUE(NearDepthReplayAccess::Correction(*node, correction));
  EXPECT_EQ(NearDepthReplayAccess::Lock(*node).header.stamp, locked.header.stamp);
  EXPECT_TRUE(NearDepthReplayAccess::DepthFlag(*node));  // Do not falsify detector flags.
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
}

TEST_F(NearDepthExecutor, PartialViewRecoversKnownIdentityButCannotAuthorizeClose)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::ReviewedAllowance(*node, .15);
  NearDepthReplayAccess::ShiftCameraY(*node, -.10);
  NearDepthReplayAccess::ColourBoxY(*node, .78f, .98f);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  const auto seed_stamp = NearDepthReplayAccess::SeedStamp(*node);
  NearDepthReplayAccess::ClippedRaw(*node);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(predicted);
  EXPECT_EQ(NearDepthReplayAccess::SeedStamp(*node), seed_stamp);
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
}

TEST_F(NearDepthExecutor, CheckedPathAllowanceCanExceed30mmButRemainsFinite)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::Travel(*node, .05);
  NearDepthReplayAccess::Inputs(*node, false);
  EXPECT_FALSE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::ReviewedAllowance(*node, .10);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_TRUE(predicted);
  NearDepthReplayAccess::Travel(*node, .131);
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
  NearDepthReplayAccess::AtomicObservation(*node);
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));  // Fresh measured branch.
  NearDepthReplayAccess::Inputs(*node, false);
  NearDepthReplayAccess::AtomicObservation(*node, false);
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));  // Associated prediction branch.
  NearDepthReplayAccess::BadOpening(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
}

TEST_F(NearDepthExecutor, FinalCenterIsNecessaryButDoesNotBlockIntermediateRgbObservation)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  NearDepthReplayAccess::AtomicObservation(*node, true, .1238, .5, .9, false);
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
  NearDepthReplayAccess::AtomicObservation(*node, true, .1238, .5, .9, true);
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));
  NearDepthReplayAccess::BadOpening(*node);
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));  // Centre alone is not enough.
}

TEST_F(NearDepthExecutor, FinalCenterRequiresExactFrameRatherThanAnOlderTrueFlag)
{
  geometry_msgs::msg::PointStamped p; bool predicted = false;
  ASSERT_TRUE(NearDepthReplayAccess::Observe(*node, predicted, p));
  NearDepthReplayAccess::AtomicObservation(*node);
  NearDepthReplayAccess::Inputs(*node, false);  // New image, no matching centre record.
  EXPECT_FALSE(NearDepthReplayAccess::Capture(*node));
  NearDepthReplayAccess::Inputs(*node, false);  // The bounded wait expired the previous RGB frame.
  NearDepthReplayAccess::AtomicObservation(*node, false, .1238, .5, .9, true);
  EXPECT_TRUE(NearDepthReplayAccess::Capture(*node));  // RGB works without new depth.
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
