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

TEST(VisualGrasp, AutomaticFkRoundoffIsNotPhysicalOvertravel)
{
  EXPECT_TRUE(vg::DistanceStepWithin(.008000002, .008, true));
  EXPECT_FALSE(vg::DistanceStepWithin(.008000002, .008, false));
  EXPECT_FALSE(vg::DistanceStepWithin(.008002, .008, true));
  EXPECT_FALSE(vg::DistanceStepWithin(NAN, .008, true));
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

TEST(VisualGrasp, AutomaticRgbPoseCorrectionsConvergeWithoutJointCommands)
{
  gg::DirectedPose current{{0, 0, 0}, {0, 0, 0, 1}};
  const gg::DirectedPose goal{{.06, .01, -.02}, {0, std::sin(.1), 0, std::cos(.1)}};
  const gg::Point correction{.004, -.002, 0};
  for (int iteration = 0; iteration < 80; ++iteration) {
    const auto before = gg::Tip(current.origin, gg::Rotate(current.orientation, {0, 0, 1}), .1358);
    const auto next = vg::CorrectedPoseStep(current, goal, correction, .1358, .008, .01745, .030);
    const auto after = gg::Tip(next.origin, gg::Rotate(next.orientation, {0, 0, 1}), .1358);
    EXPECT_LE(gg::CompareTips(after, before, {0, 0, 1}).distance_m, .008 + 1e-12);
    EXPECT_LE(gg::QuaternionDistance(current.orientation, next.orientation), .01745 + 1e-12);
    current = next;
  }
  auto expected = gg::Tip(goal.origin, gg::Rotate(goal.orientation, {0, 0, 1}), .1358);
  for (int i = 0; i < 3; ++i) {expected[i] += correction[i];}
  const auto actual = gg::Tip(current.origin, gg::Rotate(current.orientation, {0, 0, 1}), .1358);
  EXPECT_LT(gg::CompareTips(actual, expected, {0, 0, 1}).distance_m, 1e-10);
  EXPECT_LT(gg::QuaternionDistance(current.orientation, goal.orientation), 1e-10);
  EXPECT_THROW(vg::CorrectedPoseStep(current, goal, {NAN, 0, 0}, .1358, .008, .01745, .03),
    std::invalid_argument);
}

TEST(VisualGrasp, CameraGazeRestoresLowerTargetWithoutMovingCaptureTip)
{
  gg::DirectedPose goal{{0, 0, 0}, {0, 0, 0, 1}};
  const gg::DirectedPose camera{{.03, 0, .03}, {0, 0, 0, 1}};
  const gg::Point target{.03, .10, .25};
  const auto before = gg::Tip(goal.origin, {0, 0, 1}, .1358);
  ASSERT_TRUE(vg::AimCameraAtFixedTip(goal, camera, target, {0, .2, 1}, .1358));
  const auto after = gg::Tip(goal.origin, gg::Rotate(goal.orientation, {0, 0, 1}), .1358);
  EXPECT_LT(gg::CompareTips(after, before, {0, 0, 1}).distance_m, 1e-12);
  const auto camera_offset = gg::Rotate(goal.orientation, camera.origin);
  const gg::Point camera_world{goal.origin[0]+camera_offset[0], goal.origin[1]+camera_offset[1],
    goal.origin[2]+camera_offset[2]};
  const auto q = goal.orientation;
  const auto ray = gg::Rotate({-q[0], -q[1], -q[2], q[3]},
    {target[0]-camera_world[0], target[1]-camera_world[1], target[2]-camera_world[2]});
  EXPECT_NEAR(ray[0]/ray[2], 0, 1e-10);
  EXPECT_NEAR(ray[1]/ray[2], .2, 1e-10);
  const gg::DirectedPose actual{{0, 0, 0}, {0, 0, 0, 1}};
  const auto step = vg::CorrectedPoseStep(actual, goal, {0, 0, 0}, .1358, .008, .01745, .03);
  EXPECT_LE(gg::QuaternionDistance(actual.orientation, step.orientation), .01745+1e-12);
  const auto step_tip = gg::Tip(step.origin, gg::Rotate(step.orientation, {0, 0, 1}), .1358);
  EXPECT_LT(gg::CompareTips(step_tip, before, {0, 0, 1}).distance_m, 1e-12);
}

TEST(VisualGrasp, ImpossibleFixedTipCameraRayDoesNotDisplaceTipToChaseImageCentre)
{
  gg::DirectedPose goal{{0, 0, 0}, {0, 0, 0, 1}};
  const auto before = goal;
  EXPECT_FALSE(vg::AimCameraAtFixedTip(goal, {{.2, 0, 0}, {0, 0, 0, 1}},
    {0, 0, .1358}, {0, 0, 1}, .1358));
  EXPECT_EQ(goal.origin, before.origin);
  EXPECT_EQ(goal.orientation, before.orientation);
}
