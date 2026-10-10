#include <cmath>
#include <limits>
#include <gtest/gtest.h>
#include "brain_robot_pick_place/grasp_geometry.hpp"

namespace gg = brain_robot_pick_place::grasp_geometry;

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
