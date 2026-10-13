#include <gtest/gtest.h>
#include "brain_robot_pick_place/rgbd_observation.hpp"
namespace ro = brain_robot_pick_place::rgbd_observation;

ro::Snapshot Good()
{
  ro::Snapshot s; s.header.frame_id = "camera_depth_optical_frame"; s.header.stamp.sec = 1;
  s.qualified = true; s.point.z = .227; s.size.x = s.size.y = .037; s.size.z = .227;
  s.samples = 1811; s.coverage = .473; s.span = .9; s.mad_m = .002; return s;
}

TEST(RgbdObservation, RoundTripKeepsAtomicStampMeasurementAndQuality)
{
  const auto original = Good(); ro::Snapshot parsed;
  ASSERT_TRUE(ro::Decode(ro::Encode(original), parsed));
  EXPECT_EQ(parsed.header, original.header); EXPECT_EQ(parsed.point, original.point);
  EXPECT_EQ(parsed.size, original.size); EXPECT_DOUBLE_EQ(parsed.coverage, original.coverage);
  EXPECT_DOUBLE_EQ(parsed.samples, 1811); EXPECT_TRUE(parsed.qualified);
}

TEST(RgbdObservation, InvalidDepthCannotBecomeQualifiedBecauseRawPointStillExists)
{
  auto s = Good(); s.qualified = false; s.point.z = .255; s.samples = 16;
  ro::Snapshot parsed; ASSERT_TRUE(ro::Decode(ro::Encode(s), parsed));
  EXPECT_FALSE(parsed.qualified); EXPECT_DOUBLE_EQ(parsed.point.z, .255);
  EXPECT_TRUE(ro::Declined(parsed, {Good(), Good(), Good()}));
}

TEST(RgbdObservation, RelativeSupportLossSwitchesWithoutFixedRangeOrObjectSize)
{
  auto bad = Good(); bad.samples = 36; bad.coverage = .045; bad.span = .03;
  bad.point.z = .255;  // May look perfectly stable while only background remains.
  EXPECT_TRUE(ro::Declined(bad, {Good(), Good(), Good()}));
  bad.point.z = .8; bad.size.x = bad.size.y = .08;
  EXPECT_TRUE(ro::Declined(bad, {Good(), Good(), Good()}));
  auto good = Good(); good.point.z = .1; good.samples *= 4;
  EXPECT_FALSE(ro::Declined(good, {Good(), Good(), Good()}));
}

TEST(RgbdObservation, PartialOrInvalidHistoryDoesNotAuthorizeModelHandoff)
{
  auto bad = Good(); bad.qualified = false;
  EXPECT_FALSE(ro::Declined(bad, {Good(), Good()}));
  EXPECT_FALSE(ro::Declined(bad, {Good(), bad, Good()}));
}

TEST(RgbdObservation, DecoderRejectsIncompleteContradictoryOrNonfiniteRecords)
{
  auto message = ro::Encode(Good()); ro::Snapshot parsed;
  message.status[0].values.pop_back(); EXPECT_FALSE(ro::Decode(message, parsed));
  message = ro::Encode(Good()); message.status[0].level = message.status[0].WARN;
  EXPECT_FALSE(ro::Decode(message, parsed));
  message = ro::Encode(Good()); message.status[0].values[1].value = "nan";
  EXPECT_FALSE(ro::Decode(message, parsed));
  message = ro::Encode(Good()); message.status[0].values.push_back(message.status[0].values[0]);
  EXPECT_FALSE(ro::Decode(message, parsed));
  message = ro::Encode(Good()); message.header.stamp.sec = 0;
  EXPECT_FALSE(ro::Decode(message, parsed));
}
