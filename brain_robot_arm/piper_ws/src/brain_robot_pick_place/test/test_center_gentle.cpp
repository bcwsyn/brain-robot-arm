#include <gtest/gtest.h>
#include "brain_robot_pick_place/target_directed_grasp.hpp"
#include "brain_robot_pick_place/gentle_gripper.hpp"

namespace gg = brain_robot_pick_place::grasp_geometry;
using Policy = brain_robot_pick_place::GentleGripper;

TEST(CenterCapture, ActualLocalReferenceLandsAtCenterWithoutSurfaceInsertion)
{
  const gg::Point center{.345, -.01, .03}, local{.023, -.012, .135};
  const auto path = gg::CenterDirectedApproach({.2, 0, .3}, {.1, .93, 0, .35},
    center, local, .024, .005, .5);
  ASSERT_FALSE(path.pregrasp.empty()); ASSERT_FALSE(path.descent.empty());
  const auto end = path.descent.back();
  const auto reference = gg::Rotate(end.orientation, local);
  for (int i = 0; i < 3; ++i) {EXPECT_NEAR(end.origin[i]+reference[i], center[i], 1e-12);}
  const auto tip = gg::Tip(end.origin, gg::Rotate(end.orientation, {0, 0, 1}), .1358);
  EXPECT_GT(gg::CompareTips(tip, center, gg::Rotate(end.orientation, {0, 0, 1})).distance_m, .01);
  auto previous = gg::DirectedPose{{.2, 0, .3}, gg::UnitQuaternion({.1, .93, 0, .35})};
  for (const auto & part : {path.pregrasp, path.descent}) {
    for (const auto & p : part) {
      gg::Point delta{p.origin[0]-previous.origin[0], p.origin[1]-previous.origin[1],
        p.origin[2]-previous.origin[2]};
      EXPECT_LE(std::sqrt(gg::Dot(delta, delta)), .005+1e-9);
      previous = p;
    }
  }
}

TEST(GentleGripper, EmptyJawStopsAtSizeFloorNotZeroOrLift)
{
  Policy policy(.029, .1);
  double actual = .1, last = .1;
  Policy::Result result = Policy::Result::MOVING;
  for (int i = 0; i < 2000 && result == Policy::Result::MOVING; ++i) {
    actual = last;  // ideal no-object plant, not real feedback
    result = policy.Update(1+i*.02, actual, .02);
    EXPECT_GE(policy.Reference(), .025-1e-10);
    EXPECT_LE(last-policy.Reference(), .000201);
    last = policy.Reference();
  }
  EXPECT_EQ(result, Policy::Result::EMPTY);
}

TEST(GentleGripper, OnlyPersistentLoadedStopWithinSizeWindowIsContactCandidate)
{
  Policy policy(.029, .1);
  double actual = .1;
  Policy::Result result = Policy::Result::MOVING;
  for (int i = 0; i < 2000 && result == Policy::Result::MOVING; ++i) {
    // Explicit synthetic 37mm object, NOT hardware contact/force evidence.
    actual = std::max(.037, policy.Reference());
    result = policy.Update(10+i*.02, actual, actual <= .037001 ? .3 : .02);
  }
  EXPECT_EQ(result, Policy::Result::CONTACT_CANDIDATE);
  EXPECT_NEAR(policy.Reference(), .0368, 1e-9);
}

TEST(GentleGripper, FreeMotionTorquePeaksDoNotProveContact)
{
  Policy policy(.029, .1);
  auto result = Policy::Result::MOVING;
  for (int i = 0; i < 1500 && result == Policy::Result::MOVING; ++i) {
    const double effort = i%20 < 2 ? .8 : .02;
    result = policy.Update(1+i*.02, policy.Reference(), effort);
    EXPECT_NE(result, Policy::Result::CONTACT_CANDIDATE);
  }
  EXPECT_EQ(result, Policy::Result::EMPTY);
}

TEST(GentleGripper, ARemoteStallCannotAccumulateAZeroReference)
{
  Policy policy(.029, .1);
  for (int i = 0; i < 100; ++i) {
    EXPECT_EQ(policy.Update(1+i*.02, .1, .8), Policy::Result::MOVING);
    EXPECT_GE(policy.Reference(), .1-Policy::ReferenceLeadLimit()-1e-10);
  }
}

TEST(GentleGripper, QuantizedStallCannotBecomeFalseContactOrEmpty)
{
  // Deliberately pessimistic synthetic plant: round physical travel itself.
  // A residual stall must remain unconfirmed, not become synthetic success.
  Policy policy(.029, .0994);
  double actual = .0994;
  auto result = Policy::Result::MOVING;
  double elapsed = 0.;
  for (; elapsed < policy.Timeout(.0994) && result == Policy::Result::MOVING;
    elapsed += .02)
  {
    const double error = std::max(0., actual-policy.Reference()-.00015);
    const double travel = std::min(.010*.02, 4.*error*.02);
    actual = std::round((actual-travel)/.0001)*.0001;
    result = policy.Update(1.+elapsed, actual, -.02);
    EXPECT_GE(policy.Reference(), .025-1e-10);
    EXPECT_LE(actual-policy.Reference(), Policy::ReferenceLeadLimit()+1e-10);
  }
  EXPECT_EQ(result, Policy::Result::MOVING);
  EXPECT_GT(actual, .0253);
  EXPECT_GE(elapsed, policy.Timeout(.0994));
  EXPECT_LT(policy.Timeout(.1), 40.);
}

TEST(GentleGripper, SlowPlantWithQuantizedFeedbackReachesFloorWithinTimeout)
{
  // Synthetic first-order response with quantized SENSOR output. Physical
  // state is continuous. This is not an identified real-device model.
  Policy policy(.029, .0994);
  double physical = .0994, measured = physical, elapsed = 0.;
  auto result = Policy::Result::MOVING;
  for (; elapsed < policy.Timeout(.0994) && result == Policy::Result::MOVING;
    elapsed += .02)
  {
    const double error = std::max(0., physical-policy.Reference()-.00015);
    physical -= std::min(.010*.02, 4.*error*.02);
    measured = std::round(physical/.0001)*.0001;
    result = policy.Update(1.+elapsed, measured, -.02);
    EXPECT_GE(policy.Reference(), .025-1e-10);
    EXPECT_LE(measured-policy.Reference(), Policy::ReferenceLeadLimit()+1e-10);
  }
  EXPECT_EQ(result, Policy::Result::EMPTY);
  EXPECT_LE(measured, .0253);
  EXPECT_LT(elapsed, policy.Timeout(.0994));
}

TEST(GentleGripper, DuplicateOrNonfiniteFeedbackDoesNotAdvance)
{
  Policy policy(.029, .1);
  EXPECT_EQ(policy.Update(1, .1, .02), Policy::Result::MOVING);
  EXPECT_EQ(policy.Update(1, .09, .5), Policy::Result::INVALID);
  EXPECT_EQ(policy.Update(2, NAN, .5), Policy::Result::INVALID);
}
