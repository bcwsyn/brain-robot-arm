#include <limits>
#include <gtest/gtest.h>
#include "brain_robot_pick_place/measured_motion.hpp"
using brain_robot_pick_place::PositionSamplesSettled;
TEST(MeasuredMotion, StationaryPositionsAreSettled) {
  std::vector<double> positions{0., .98, -.75, 0., .3, 0.};
  EXPECT_TRUE(PositionSamplesSettled(positions, positions, .02));
}
TEST(MeasuredMotion, SmallButFastMovementIsRejected) {
  std::vector<double> previous(6, 0.), current(6, 0.);
  current[4] = .0008;
  EXPECT_FALSE(PositionSamplesSettled(previous, current, .02));
}
TEST(MeasuredMotion, DriftIsRejected) {
  std::vector<double> previous(6, 0.), current(6, .0011);
  EXPECT_FALSE(PositionSamplesSettled(previous, current, .1));
}
TEST(MeasuredMotion, MissingNonfiniteAndStaleSamplesAreRejected) {
  std::vector<double> p(6, 0.);
  EXPECT_FALSE(PositionSamplesSettled({}, p, .02));
  EXPECT_FALSE(PositionSamplesSettled(p, p, 0.));
  EXPECT_FALSE(PositionSamplesSettled(p, p, .3));
  EXPECT_FALSE(PositionSamplesSettled(p, p, std::numeric_limits<double>::quiet_NaN()));
  p[2] = std::numeric_limits<double>::infinity();
  EXPECT_FALSE(PositionSamplesSettled(p, p, .02));
}

TEST(ApproachMotion, ShortSmoothApproachIsAccepted) {
  EXPECT_TRUE(brain_robot_pick_place::BoundedJointExcursion({std::vector<double>(6, .0), std::vector<double>(6, .3)}, 1.2));
}
TEST(ApproachMotion, MidpathWristFlipIsRejectedEvenWithMatchingEndpoints) {
  std::vector<double> initial(6, 0), middle(6, 0); middle[3] = 2.;
  EXPECT_FALSE(brain_robot_pick_place::BoundedJointExcursion({initial, middle, initial}, 1.2));
}
