#include <cmath>
#include <limits>
#include <gtest/gtest.h>
#include "brain_robot_pick_place/grasp_geometry.hpp"
#include "brain_robot_pick_place/target_directed_grasp.hpp"

namespace gg = brain_robot_pick_place::grasp_geometry;

TEST(GraspGeometry, DirectedApproachAimsAtOneTargetWhileAttitudeChanges)
{
  const gg::Point surface{0.43, -0.11, 0.08};
  const gg::Point start{0.29, -0.07, 0.31};
  const auto q = gg::AimTool({0, 0, 0, 1}, {0.5, -0.1, -0.8});
  const auto path = gg::TargetDirectedApproach(start, q, surface, 0.1358, 0.024, 0.012, 0.005);
  ASSERT_FALSE(path.pregrasp.empty());
  ASSERT_FALSE(path.descent.empty());
  EXPECT_EQ(path.pregrasp.front().origin, start);
  auto last = gg::DirectedPose{start, q};
  for (const auto & segment : {path.pregrasp, path.descent}) {
    for (const auto & p : segment) {
      gg::Point delta{};
      for (std::size_t i = 0; i < 3; ++i) {delta[i] = p.origin[i] - last.origin[i];}
      EXPECT_LE(std::sqrt(gg::Dot(delta, delta)), 0.005 + 1e-10);
      EXPECT_LE(gg::QuaternionDistance(p.orientation, last.orientation), 0.020 + 1e-10);
      if (p.origin != start) {
        const auto axis = gg::Rotate(p.orientation, {0, 0, 1});
        const auto ray = gg::Unit({surface[0] - p.origin[0], surface[1] - p.origin[1],
          surface[2] - p.origin[2]});
        EXPECT_NEAR(gg::Dot(axis, ray), 1.0, 1e-10);
      }
      last = p;
    }
  }
  const auto pre = path.pregrasp.back();
  const auto pre_tip = gg::Tip(pre.origin, gg::Rotate(pre.orientation, {0, 0, 1}), 0.1358);
  EXPECT_NEAR(gg::CompareTips(pre_tip, surface,
      gg::Rotate(pre.orientation, {0, 0, 1})).distance_m, 0.024, 1e-10);
  const auto final = path.descent.back();
  const auto final_axis = gg::Rotate(final.orientation, {0, 0, 1});
  const auto final_tip = gg::Tip(final.origin, final_axis, 0.1358);
  EXPECT_NEAR(final_axis[2], -1.0, 1e-12);
  EXPECT_NEAR(final_tip[0], surface[0], 1e-12);
  EXPECT_NEAR(final_tip[1], surface[1], 1e-12);
  EXPECT_NEAR(final_tip[2], surface[2] - 0.012, 1e-12);
  EXPECT_GT(gg::QuaternionDistance(pre.orientation, final.orientation), 0.01);
}

TEST(GraspGeometry, DirectedAimHasNoPresetYawAndHandlesOppositeDirections)
{
  const gg::Quaternion q{0, 0, std::sin(0.4), std::cos(0.4)};
  const auto aimed = gg::AimTool(q, {0, 0, -1});
  EXPECT_NEAR(gg::Rotate(aimed, {0, 0, 1})[2], -1.0, 1e-12);
  const auto unchanged = gg::AimTool(q, {0, 0, 1});
  EXPECT_NEAR(gg::QuaternionDistance(q, unchanged), 0.0, 1e-12);
  gg::Quaternion opposite = q;
  for (double & v : opposite) {v = -v;}
  EXPECT_NEAR(gg::QuaternionDistance(gg::Slerp(q, opposite, 0.5), q), 0.0, 1e-12);
}

TEST(GraspGeometry, SynchronizedTurnTranslatesImmediatelyAndPreservesCaptureEndpoint)
{
  const gg::Point start{.232925, -.070458, .213741};
  const gg::Point surface{.413131, -.113936, .062490};
  const gg::Quaternion q{.139338, .936617, -.047305, .317957};
  const auto old_path = gg::TargetDirectedApproach(start, q, surface, .1358, .024, .012, .005, .5);
  const auto path = gg::TargetDirectedApproach(start, q, surface, .1358, .024, .012, .005, .5, true);
  ASSERT_FALSE(path.pregrasp.empty()); ASSERT_FALSE(path.descent.empty());
  EXPECT_NE(path.pregrasp.front().origin, start);
  EXPECT_GT(gg::QuaternionDistance(path.pregrasp.front().orientation, q), 1e-5);
  const auto final = path.descent.back();
  for (std::size_t i = 0; i < 3; ++i) {
    EXPECT_NEAR(final.origin[i], old_path.descent.back().origin[i], 1e-12);
  }
  EXPECT_NEAR(gg::QuaternionDistance(final.orientation, old_path.descent.back().orientation), 0, 1e-7);
  auto last = gg::DirectedPose{start, q};
  for (const auto & segment : {path.pregrasp, path.descent}) {
    for (const auto & p : segment) {
      const gg::Point delta{p.origin[0]-last.origin[0], p.origin[1]-last.origin[1],
        p.origin[2]-last.origin[2]};
      EXPECT_LE(std::sqrt(gg::Dot(delta, delta)), .005+1e-10);
      EXPECT_LE(gg::QuaternionDistance(p.orientation, last.orientation), .02+1e-10);
      last = p;
    }
  }
  const auto pre = path.pregrasp.back();
  const auto pre_axis = gg::Rotate(pre.orientation, {0, 0, 1});
  EXPECT_NEAR(gg::CompareTips(gg::Tip(pre.origin, pre_axis, .1358), surface,
    pre_axis).axial_m, -.024, 1e-12);
  const auto axis = gg::Rotate(final.orientation, {0, 0, 1});
  EXPECT_NEAR(gg::CompareTips(gg::Tip(final.origin, axis, .1358), surface, axis).axial_m, .012, 1e-12);
}

TEST(GraspGeometry, DirectedSlantedEntryStillAimsAtTargetWithNoFixedAttitude)
{
  const gg::Point start{0.17, -0.05, 0.29};
  const gg::Point surface{0.43, -0.11, 0.08};
  const gg::Quaternion q{0.126, 0.932, -0.045, 0.335};
  const auto path = gg::TargetDirectedApproach(start, q, surface, .1358, .024, .012, .005, .5);
  const auto & p = path.descent.back();
  const auto axis = gg::Rotate(p.orientation, {0, 0, 1});
  const auto ray = gg::Unit({surface[0] - start[0], surface[1] - start[1],
    surface[2] - start[2]});
  EXPECT_GT(axis[2], -1.0);
  EXPECT_LT(axis[2], ray[2]);
  EXPECT_NEAR(gg::Dot(axis, gg::Unit({surface[0] - p.origin[0],
      surface[1] - p.origin[1], surface[2] - p.origin[2]})), 1.0, 1e-12);
  EXPECT_GT(gg::QuaternionDistance(path.pregrasp.back().orientation, p.orientation), .01);
  const auto tip = gg::Tip(p.origin, axis, .1358);
  EXPECT_NEAR(gg::CompareTips(tip, surface, axis).axial_m, .012, 1e-12);
  EXPECT_THROW(gg::TargetDirectedApproach(start, q, surface, .1358, .024, .012, .005, 0.0),
    std::invalid_argument);
}

TEST(GraspGeometry, DirectedApproachRejectsUndefinedGeometry)
{
  const gg::Point p{0, 0, 0};
  const gg::Quaternion q{0, 0, 0, 1};
  EXPECT_THROW(gg::TargetDirectedApproach(p, q, p, .1358, .024, .012, .005),
    std::invalid_argument);
  EXPECT_THROW(gg::TargetDirectedApproach(p, q, {0, 0, .14}, .1358, .024, .012, .005),
    std::invalid_argument);
  EXPECT_THROW(gg::TargetDirectedApproach(p, q, {0, 0, .30}, .1358, .024, .14, .005),
    std::invalid_argument);
  EXPECT_THROW(gg::TargetDirectedApproach(p, q, {0, 0, .30}, .1358, .024, .012, NAN),
    std::invalid_argument);
  EXPECT_THROW(gg::AimTool(q, {0, 0, 0}), std::invalid_argument);
  EXPECT_THROW(gg::AimTool({0, 0, 0, 0}, {0, 0, -1}), std::invalid_argument);
}

TEST(GraspGeometry, PosePitchRotationComposesInReferenceFrameAndZeroRestores)
{
  const double angle = 5.0 * std::acos(-1.0) / 180.0;
  const auto pitched = gg::RotateOrientationAboutAxis({0, 0, 0, 1}, {0, 2, 0}, angle);
  EXPECT_NEAR(pitched[0], 0.0, 1e-12);
  EXPECT_NEAR(pitched[1], std::sin(angle / 2), 1e-12);
  EXPECT_NEAR(pitched[2], 0.0, 1e-12);
  EXPECT_NEAR(pitched[3], std::cos(angle / 2), 1e-12);
  const gg::Quaternion yaw{0, 0, std::sin(0.4), std::cos(0.4)};
  const auto unchanged = gg::RotateOrientationAboutAxis(yaw, {1, 0, 0}, 0.0);
  for (std::size_t i = 0; i < yaw.size(); ++i) {
    EXPECT_NEAR(unchanged[i], yaw[i], 1e-12);
  }
  const auto composed = gg::RotateOrientationAboutAxis(yaw, {0, 1, 0}, angle);
  EXPECT_NEAR(composed[0], std::sin(angle / 2) * yaw[2], 1e-12);
  EXPECT_NEAR(composed[1], std::sin(angle / 2) * yaw[3], 1e-12);
}

TEST(GraspGeometry, PosePitchRotationRejectsUndefinedInputs)
{
  EXPECT_THROW(gg::RotateOrientationAboutAxis({0, 0, 0, 1}, {0, 0, 0}, 0.1),
    std::invalid_argument);
  EXPECT_THROW(gg::RotateOrientationAboutAxis({0, 0, 0, 0}, {0, 1, 0}, 0.1),
    std::invalid_argument);
  EXPECT_THROW(gg::RotateOrientationAboutAxis({0, 0, 0, 1}, {0, 1, 0}, NAN),
    std::invalid_argument);
}

TEST(GraspGeometry, FreshJawCaptureRejectsRemoteOrOffCentreCube)
{
  EXPECT_FALSE(gg::FaceInsideJawCapture({0.0, 0.0, 0.2858}, 0.1358, 0.033, 0.050));
  EXPECT_FALSE(gg::FaceInsideJawCapture({0.0434, 0.02735, 0.108}, 0.1358, 0.040, 0.0462));
  EXPECT_FALSE(gg::FaceInsideJawCapture({0.0, 0.015, 0.1238}, 0.1358, 0.033, 0.050));
}

TEST(GraspGeometry, FreshJawCaptureNeedsOpeningAndFiniteMeasuredFace)
{
  EXPECT_TRUE(gg::FaceInsideJawCapture({0.0, 0.0, 0.1238}, 0.1358, 0.033, 0.050));
  EXPECT_FALSE(gg::FaceInsideJawCapture({0.0, 0.0, 0.1238}, 0.1358, 0.050, 0.0462));
  EXPECT_FALSE(gg::FaceInsideJawCapture({NAN, 0.0, 0.1238}, 0.1358, 0.033, 0.050));
}

TEST(GraspGeometry, InsertionUsesSmallerFaceAndCapsTravel)
{
  EXPECT_DOUBLE_EQ(gg::SurfaceInsertion(0.020, 0.4, 0.012), 0.008);
  EXPECT_DOUBLE_EQ(gg::SurfaceInsertion(0.038, 0.4, 0.012), 0.012);
  EXPECT_THROW(gg::SurfaceInsertion(0.0, 0.4, 0.012), std::invalid_argument);
  EXPECT_THROW(gg::SurfaceInsertion(0.030, 0.5, 0.012), std::invalid_argument);
  EXPECT_THROW(gg::SurfaceInsertion(NAN, 0.4, 0.012), std::invalid_argument);
}

TEST(GraspGeometry, LegacyPositiveGapLeavesFingertipsOutsideObject)
{
  const gg::Point surface{0.260, -0.092, 0.136};
  const gg::Point axis{std::sin(0.35), 0.0, -std::cos(0.35)};
  const auto wrist = gg::ToolOrigin(surface, axis, 0.1358, 0.018);
  const auto tip = gg::Tip(wrist, axis, 0.1358);
  const auto error = gg::CompareTips(tip, surface, axis);
  EXPECT_NEAR(error.axial_m, -0.018, 1e-12);
  EXPECT_NEAR(error.lateral_m, 0.0, 1e-9);
  EXPECT_GT(tip[2], surface[2]);
}

TEST(GraspGeometry, CorrectedApproachCrossesSurfaceWithFixedOrientation)
{
  const gg::Point surface{0.260, -0.092, 0.136};
  const gg::Point axis{std::sin(0.35), 0.0, -std::cos(0.35)};
  const double insertion = gg::SurfaceInsertion(0.032, 0.4, 0.012);
  const auto pre = gg::ToolOrigin(surface, axis, 0.1358, 0.024);
  const auto final = gg::ToolOrigin(surface, axis, 0.1358, -insertion);
  const auto tip = gg::Tip(final, axis, 0.1358);
  const auto error = gg::CompareTips(tip, surface, axis);
  EXPECT_NEAR(error.axial_m, insertion, 1e-12);
  EXPECT_NEAR(error.lateral_m, 0.0, 1e-9);
  EXPECT_LT(tip[2], surface[2]);
  EXPECT_NEAR(gg::CompareTips(final, pre, axis).distance_m, 0.036, 1e-12);
}

TEST(GraspGeometry, FarOrSidewaysLandingIsNotAnAcceptedEndpoint)
{
  const gg::Point expected{0.26, -0.09, 0.124};
  const gg::Point axis{0.0, 0.0, -1.0};
  const auto far = gg::CompareTips({0.26, -0.09, 0.224}, expected, axis);
  EXPECT_NEAR(far.distance_m, 0.1, 1e-12);
  EXPECT_NEAR(far.axial_m, -0.1, 1e-12);
  EXPECT_GT(far.distance_m, 0.020);
  const auto sideways = gg::CompareTips({0.29, -0.09, 0.124}, expected, axis);
  EXPECT_NEAR(sideways.lateral_m, 0.03, 1e-12);
  EXPECT_GT(sideways.distance_m, 0.008);
}

TEST(GraspGeometry, CloseOnlyAfterLandingAndAtMostOneCorrection)
{
  const gg::LandingLimits limits{0.008, 0.12, 0.020, 0.20};
  EXPECT_EQ(gg::DecideLanding({0.004, 0.0, 0.004}, 0.01, limits, false),
    gg::LandingDecision::ACCEPT);
  EXPECT_EQ(gg::DecideLanding({0.010, 0.0, 0.010}, 0.01, limits, false),
    gg::LandingDecision::CORRECT_ONCE);
  EXPECT_EQ(gg::DecideLanding({0.010, 0.0, 0.010}, 0.01, limits, true),
    gg::LandingDecision::REJECT);
  EXPECT_EQ(gg::DecideLanding({0.100, -0.100, 0.0}, 0.01, limits, false),
    gg::LandingDecision::REJECT);
  EXPECT_EQ(gg::DecideLanding({0.003, 0.0, 0.003}, 0.40, limits, false),
    gg::LandingDecision::REJECT);
  EXPECT_EQ(gg::DecideLanding({NAN, 0.0, 0.0}, 0.0, limits, false),
    gg::LandingDecision::REJECT);
}
