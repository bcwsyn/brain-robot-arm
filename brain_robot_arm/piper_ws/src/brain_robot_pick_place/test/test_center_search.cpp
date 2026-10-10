#include <gtest/gtest.h>

#include <limits>

#include "brain_robot_pick_place/center_search.hpp"

namespace s = brain_robot_pick_place::search;
const s::Bounds bounds{-1.35, 1.35, -0.60, 0.95};

TEST(CenterSearch, FirstImageWindowHasNoSweep)
{
  s::CenterFirstSearch plan;
  plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, 2.0, 10.0);
  for (double now : {10.0, 10.5, 11.99}) {
    const auto action = plan.Tick(now, {0.0, 0.30}, 0.01);
    EXPECT_EQ(action.phase, s::CenterPhase::HOLD);
    EXPECT_DOUBLE_EQ(action.target.horizontal, 0.0);
    EXPECT_DOUBLE_EQ(action.target.vertical, 0.30);
  }
}

TEST(CenterSearch, VisitsBothNearbySidesBeforeReturnAndExpansion)
{
  s::CenterFirstSearch plan;
  plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, 2.0, 0.0);
  auto action = plan.Tick(2.0, {0.0, 0.30}, 0.01);
  EXPECT_EQ(action.phase, s::CenterPhase::LOCAL_SCAN);
  EXPECT_DOUBLE_EQ(action.target.horizontal, 0.08);
  const s::Point expected[] = {{0.08, 0.30}, {-0.08, 0.30}, {0.0, 0.42},
    {0.08, 0.42}, {-0.08, 0.42}, {0.0, 0.18}, {0.08, 0.18}, {-0.08, 0.18}};
  for (const auto & point : expected) {
    EXPECT_NEAR(action.target.horizontal, point.horizontal, 1e-10);
    EXPECT_NEAR(action.target.vertical, point.vertical, 1e-10);
    action = plan.Tick(3.0, point, 0.01);
  }
  EXPECT_EQ(action.phase, s::CenterPhase::RETURN_CENTER);
  EXPECT_TRUE(plan.Active());
  action = plan.Tick(4.0, {0.0, 0.30}, 0.01);
  EXPECT_EQ(action.phase, s::CenterPhase::COMPLETE);
  EXPECT_FALSE(plan.Active());
}

TEST(CenterSearch, ElapsedTimeNeverPretendsWaypointOrReturnWasReached)
{
  s::CenterFirstSearch plan;
  plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, 2.0, 0.0);
  const auto action = plan.Tick(10000.0, {0.0, 0.30}, 0.01);
  EXPECT_EQ(action.phase, s::CenterPhase::LOCAL_SCAN);
  EXPECT_EQ(action.index, 0U);
  EXPECT_EQ(plan.Tick(20000.0, {0.0, 0.30}, 0.01).index, 0U);
}

TEST(CenterSearch, CancellationPreventsLaterExpansion)
{
  s::CenterFirstSearch plan;
  plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, 2.0, 0.0);
  plan.Cancel();  // Target acquisition or the controller's fault/stop path.
  EXPECT_FALSE(plan.Active());
  EXPECT_EQ(plan.Tick(10000.0, {0.0, 0.30}, 0.01).phase, s::CenterPhase::INACTIVE);
}

TEST(CenterSearch, NearbyWaypointsStayInsideOriginalSearchBounds)
{
  s::CenterFirstSearch plan;
  plan.Reset({1.34, 0.94}, bounds, 0.08, 0.12, 0.0, 0.0);
  auto action = plan.Tick(0.0, {1.34, 0.94}, 0.005);
  for (int step = 0; step < 12 && plan.Active(); ++step) {
    EXPECT_LE(action.target.horizontal, bounds.horizontal_max);
    EXPECT_GE(action.target.horizontal, bounds.horizontal_min);
    EXPECT_LE(action.target.vertical, bounds.vertical_max);
    EXPECT_GE(action.target.vertical, bounds.vertical_min);
    action = plan.Tick(0.1 * step, action.target, 0.005);
  }
  EXPECT_EQ(action.phase, s::CenterPhase::COMPLETE);
}

TEST(CenterSearch, FinalPartialStepLandsOnBoundaryRatherThanOvershooting)
{
  EXPECT_DOUBLE_EQ(s::BoundedStep(0.90, 0.95, 0.20), 0.95);
  EXPECT_DOUBLE_EQ(s::BoundedStep(-0.55, -0.60, 0.20), -0.60);
  EXPECT_NEAR(s::BoundedStep(0.0, -1.35, 0.20), -0.20, 1e-12);
  const auto clamped = bounds.Clamp({-2.0, 1.10});
  EXPECT_DOUBLE_EQ(clamped.horizontal, -1.35);
  EXPECT_DOUBLE_EQ(clamped.vertical, 0.95);
}

TEST(CenterSearch, ActualBoundaryCrossingCanReverseWithoutOscillating)
{
  EXPECT_TRUE(s::BoundaryReached(0.97, 0.95, 1, 0.01));
  EXPECT_TRUE(s::BoundaryReached(-1.37, -1.35, -1, 0.01));
  EXPECT_FALSE(s::BoundaryReached(0.90, 0.95, 1, 0.01));
  EXPECT_FALSE(s::BoundaryReached(-1.20, -1.35, -1, 0.01));
}

TEST(CenterSearch, NonFiniteParametersAndFeedbackAreRejected)
{
  s::CenterFirstSearch plan;
  const double nan = std::numeric_limits<double>::quiet_NaN();
  EXPECT_THROW(plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, nan, 0.0), std::invalid_argument);
  plan.Reset({0.0, 0.30}, bounds, 0.08, 0.12, 2.0, 0.0);
  EXPECT_THROW(plan.Tick(0.0, {nan, 0.30}, 0.01), std::invalid_argument);
}
