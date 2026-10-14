#include <gtest/gtest.h>
#include "brain_robot_pick_place/visual_grasp_feedback.hpp"

namespace vg = brain_robot_pick_place::visual_grasp;
namespace gg = brain_robot_pick_place::grasp_geometry;

TEST(VisualGrasp, CroppedPurpleIsNotFullView)
{
  EXPECT_FALSE(vg::FullView({101.0 / 320, 212.0 / 240, 151.0 / 320, 1}));
  EXPECT_TRUE(vg::FullView({.3, .65, .5, .9}));
  EXPECT_FALSE(vg::FullView({NAN, .2, .5, .8}));
  EXPECT_FALSE(vg::FullView({.5, .2, .3, .8}));
}

TEST(VisualGrasp, BackgroundJumpDoesNotAssociate)
{
  EXPECT_TRUE(vg::Associated({.3, .7, .5, 1}, {.3, .6, .5, .9}));
  EXPECT_FALSE(vg::Associated({.3, .7, .5, 1}, {.7, .1, .9, .3}));
}

TEST(VisualGrasp, ImageCentreIsNotJawCapture)
{
  const vg::Box jaws{.2, .6, .8, .95};
  EXPECT_FALSE(vg::InsideImageJaws({.45, .4, .55, .55}, jaws));
  EXPECT_TRUE(vg::InsideImageJaws({.3, .7, .5, .9}, jaws));
  EXPECT_FALSE(vg::InsideImageJaws({.3, .7, .5, 1}, jaws));
  EXPECT_FALSE(vg::InsideImageJaws({.3, .7, .5, .9}, {0, 0, 0, 0}));
}

TEST(VisualGrasp, TipAndAttitudeMicrostepsAreBoundedTogether)
{
  const gg::DirectedPose start{{.2, 0, .2}, {0, 0, 0, 1}};
  const auto next = vg::TipMicrostep(start, {.3, -.02, .35}, .1358, .012, .005, .01745);
  const auto before = gg::Tip(start.origin, gg::Rotate(start.orientation, {0, 0, 1}), .1358);
  const auto after = gg::Tip(next.origin, gg::Rotate(next.orientation, {0, 0, 1}), .1358);
  const auto error = gg::CompareTips(after, before, {0, 0, 1});
  EXPECT_LE(error.distance_m, .005 + 1e-12);
  EXPECT_LE(gg::QuaternionDistance(start.orientation, next.orientation), .01745 + 1e-12);
  EXPECT_GT(gg::QuaternionDistance(start.orientation, next.orientation), .01);
  EXPECT_NE(start.origin, next.origin);
}

TEST(VisualGrasp, NoOvershootAtNearContact)
{
  const gg::DirectedPose start{{0, 0, 0}, {0, 0, 0, 1}};
  const auto next = vg::TipMicrostep(start, {0, 0, .1258}, .1358, .012, .005, .01745);
  const auto tip = gg::Tip(next.origin, {0, 0, 1}, .1358);
  EXPECT_NEAR(tip[2], .1378, 1e-12);
  EXPECT_THROW(vg::TipMicrostep(start, {0, 0, .2}, .1358, .012, NAN, .02),
    std::invalid_argument);
}
