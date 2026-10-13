#include <limits>
#include <gtest/gtest.h>
#include "brain_robot_pick_place/rgbd_shape_geometry.hpp"

using brain_robot_pick_place::associate_color_mask;
using brain_robot_pick_place::color_center_at_depth_z;

TEST(RgbdShape, MissingDepthDoesNotCreateMeasurements)
{
  cv::Mat raw(10, 10, CV_8UC1, cv::Scalar(255));
  cv::Mat map(20, 20, CV_32SC2, cv::Scalar(-1, -1));
  map.at<cv::Vec2i>(3, 4) = {5, 6};
  const auto mask = associate_color_mask(raw, map);
  EXPECT_EQ(cv::countNonZero(mask), 1);
  EXPECT_EQ(mask.at<unsigned char>(3, 4), 255);
  EXPECT_EQ(mask.at<unsigned char>(10, 10), 0);
}

TEST(RgbdShape, OnlySelectedContourAndInBoundsPixelsAreAssociated)
{
  cv::Mat raw = cv::Mat::zeros(10, 10, CV_8UC1);
  raw.at<unsigned char>(5, 4) = 255;
  cv::Mat map(1, 5, CV_32SC2, cv::Scalar(-1, -1));
  map.at<cv::Vec2i>(0, 0) = {4, 5};
  map.at<cv::Vec2i>(0, 1) = {8, 5};  // different colour object/background
  map.at<cv::Vec2i>(0, 2) = {10, 5};
  map.at<cv::Vec2i>(0, 3) = {-1, 5};
  EXPECT_EQ(cv::countNonZero(associate_color_mask(raw, map)), 1);
}

TEST(RgbdShape, IdentityUsesFullColorCentreNotDepthFragmentCentre)
{
  cv::Vec3d point;
  double z;
  ASSERT_TRUE(color_center_at_depth_z({120, 160}, {320, 240}, {640, 480},
    500, 500, 310, 210, false, cv::Matx33d::eye(), {0, 0, 0}, .16, point, z));
  EXPECT_NEAR(point[0], (120. * 639 / 319 - 310) * .16 / 500, 1e-12);
  EXPECT_NEAR(point[1], (160. * 479 / 239 - 210) * .16 / 500, 1e-12);
  EXPECT_NEAR(point[2], .16, 1e-12);
}

TEST(RgbdShape, FactoryTransformRoundTripsAndPreservesMeasuredDepthZ)
{
  const cv::Matx33d r(.99998426437, .00078827410, -.00555561949,
    -.00080088340, .99999713898, -.00226784474,
    .00555381598, .00227225851, .99998199940);
  const cv::Vec3d t(-.02993771553, .00001795782, -.00032919908);
  for (const bool mirror : {false, true}) {
    cv::Vec3d point;
    double z;
    ASSERT_TRUE(color_center_at_depth_z({119.69, 160.56}, {320, 240}, {640, 480},
      488.8685, 488.8685, 310.7305, 209.0377, mirror, r, t, .155, point, z));
    const auto color = r * point + t;
    double u = 488.8685 * color[0] / color[2] + 310.7305;
    if (mirror) {u = 639 - u;}
    const double v = 488.8685 * color[1] / color[2] + 209.0377;
    EXPECT_NEAR(u * 319 / 639, 119.69, 1e-10);
    EXPECT_NEAR(v * 239 / 479, 160.56, 1e-10);
    EXPECT_NEAR(point[2], .155, 1e-12);
    EXPECT_NEAR(color[2], z, 1e-12);
  }
}

TEST(RgbdShape, InvalidDepthCannotGenerateThreeDimensionalTarget)
{
  cv::Vec3d point;
  double z;
  for (const auto depth : {0., -.1, std::numeric_limits<double>::quiet_NaN(),
      std::numeric_limits<double>::infinity()})
  {
    EXPECT_FALSE(color_center_at_depth_z({120, 160}, {320, 240}, {640, 480},
      500, 500, 310, 210, false, cv::Matx33d::eye(), {0, 0, 0}, depth, point, z));
  }
}

TEST(RgbdShape, InvalidCalibrationIsRejected)
{
  cv::Vec3d point;
  double z;
  EXPECT_FALSE(color_center_at_depth_z({120, 160}, {1, 240}, {640, 480},
    500, 500, 310, 210, false, cv::Matx33d::eye(), {0, 0, 0}, .16, point, z));
  EXPECT_FALSE(color_center_at_depth_z({120, 160}, {320, 240}, {640, 480},
    0, 500, 310, 210, false, cv::Matx33d::eye(), {0, 0, 0}, .16, point, z));
  EXPECT_FALSE(color_center_at_depth_z({120, 160}, {320, 240}, {640, 480},
    500, 500, 310, 210, false, cv::Matx33d::zeros(), {0, 0, 0}, .16, point, z));
}
