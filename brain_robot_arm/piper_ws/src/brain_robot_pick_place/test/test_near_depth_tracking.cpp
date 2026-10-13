#include <limits>
#include <gtest/gtest.h>
#include "brain_robot_pick_place/near_depth_tracking.hpp"
#include "brain_robot_pick_place/grasp_geometry.hpp"

namespace nd = brain_robot_pick_place::near_depth;
using brain_robot_pick_place::visual_grasp::Box;

static nd::Calibration Factory()
{
  return {640, 480, 488.86849976, 488.86849976, 310.73052979, 209.03765869, false,
    {.99998426437, .00078827410, -.00555561949, -.00080088340, .99999713898,
      -.00226784474, .00555381598, .00227225851, .99998199940},
    {-.02993771553, .00001795782, -.00032919908}};
}

TEST(NearDepth, ActualFeedbackProjectionMatchesRecordedReview)
{
  nd::Projection p;
  ASSERT_TRUE(nd::Project(Factory(), {.0273996760089357, .03124879082799753,
    .14251473272302967}, 320, 240, p));
  EXPECT_NEAR(p.x * 320, 149.45708810273555, 1e-8);
  EXPECT_NEAR(p.y * 240, 157.26532001447436, 1e-8);
  EXPECT_LT(p.z, .149);  // Model prediction, NOT a fresh sensor measurement.
}

struct Example
{
  nd::Seed seed{{90. / 320, 125. / 240, 151. / 320, 196. / 240}, .1517, true};
  nd::Evidence evidence{true, true, true, .05, .02, 3, .012};
  Box box{120. / 320, 126. / 240, 184. / 320, 201. / 240};
  nd::Projection projection{149.457 / 320, 157.265 / 240, .1424};
  const char * reject() const {
    return nd::PredictionRejection(seed, evidence, box, projection, .6, 30, .030);
  }
};

TEST(NearDepth, ZeroDepthCanUseLockedModelAndFreshAssociatedRGB)
{
  Example e;
  EXPECT_EQ(e.reject(), nullptr);
  EXPECT_DOUBLE_EQ(e.evidence.seed_age_s, 3);  // Colour acceptance does not refresh depth age.
}

TEST(NearDepth, NoInitialReliableLockNeverBecomesDepthOnlyGrasp)
{
  Example e; e.seed.valid = false;
  EXPECT_STREQ(e.reject(), "NO_RELIABLE_RGBD_LOCK");
  e.seed.valid = true; e.evidence.model_locked = false;
  EXPECT_STREQ(e.reject(), "NO_RELIABLE_RGBD_LOCK");
}

TEST(NearDepth, LockedSurfacePointMayStayInsideChangingSilhouetteAwayFromCentre)
{
  Example e;
  e.box.left += .055; e.box.right += .055;
  ASSERT_GT(std::hypot((e.box.left + e.box.right) / 2 - e.projection.x,
    (e.box.top + e.box.bottom) / 2 - e.projection.y), .04);
  EXPECT_EQ(e.reject(), nullptr);
}

TEST(NearDepth, SmallCentreErrorDoesNotAllowProjectionOutsideCube)
{
  Example e;
  e.box = {e.projection.x + .001, e.projection.y - .02,
    e.projection.x + .04, e.projection.y + .02};
  EXPECT_STREQ(e.reject(), "LOCKED_TARGET_RGB_MISMATCH");
}

TEST(NearDepth, FeedbackAndExactImageTFRequired)
{
  Example e; e.evidence.exact_image_tf = false;
  EXPECT_STREQ(e.reject(), "FEEDBACK_OR_IMAGE_TF_UNAVAILABLE");
  e.evidence.exact_image_tf = true; e.evidence.fresh_six_axis_feedback = false;
  EXPECT_STREQ(e.reject(), "FEEDBACK_OR_IMAGE_TF_UNAVAILABLE");
}

TEST(NearDepth, StaleFutureAndLostRGBRejected)
{
  Example e; e.evidence.image_age_s = .601;
  EXPECT_STREQ(e.reject(), "STALE_RGB");
  e.evidence.image_age_s = -.01;
  EXPECT_STREQ(e.reject(), "STALE_RGB");
  e.evidence.image_age_s = .05; e.evidence.receipt_age_s = .601;
  EXPECT_STREQ(e.reject(), "STALE_RGB");
  e.evidence.receipt_age_s = .02; e.box = {};
  EXPECT_STREQ(e.reject(), "COLOR_SHAPE_UNAVAILABLE");
}

TEST(NearDepth, PurpleBackgroundCannotReplaceLockedObject)
{
  Example e; e.box = {.02, .03, .22, .3};
  EXPECT_STREQ(e.reject(), "LOCKED_TARGET_RGB_MISMATCH");
  e.box = {.2, .2, .8, .95};
  EXPECT_NE(e.reject(), nullptr);  // Large same-colour background is not the cube.
}

TEST(NearDepth, SameCentreWrongSizeRejected)
{
  Example e;
  e.box = {e.projection.x - .01, e.projection.y - .01,
    e.projection.x + .01, e.projection.y + .01};
  EXPECT_STREQ(e.reject(), "LOCKED_TARGET_SCALE_MISMATCH");
}

TEST(NearDepth, PredictionHasFiniteAgeAndTravel)
{
  Example e; e.evidence.seed_age_s = 30.001;
  EXPECT_STREQ(e.reject(), "PREDICTION_RANGE_EXHAUSTED");
  e.evidence.seed_age_s = 3; e.evidence.camera_travel_m = .030001;
  EXPECT_STREQ(e.reject(), "PREDICTION_RANGE_EXHAUSTED");
}

TEST(NearDepth, NonfiniteGeometryAndBadCalibrationRejected)
{
  nd::Projection p;
  auto c = Factory(); c.fx = NAN;
  EXPECT_FALSE(nd::Project(c, {0, 0, .15}, 320, 240, p));
  EXPECT_FALSE(nd::Project(Factory(), {NAN, 0, .15}, 320, 240, p));
  EXPECT_FALSE(nd::Project(Factory(), {0, 0, -.15}, 320, 240, p));
  c = Factory(); c.rotation = {};
  EXPECT_FALSE(nd::Project(c, {0, 0, .15}, 320, 240, p));
  Example e; e.evidence.camera_travel_m = NAN;
  EXPECT_STREQ(e.reject(), "NONFINITE_EVIDENCE");
}

TEST(NearDepth, OriginalJawGeometryNeedsPlausibleActualOpening)
{
  namespace gg = brain_robot_pick_place::grasp_geometry;
  EXPECT_FALSE(gg::FaceInsideJawCapture({0, 0, .25}, .1358, .04, .05));
  // Generic geometry alone accepts an impossible PiPER cache. The executor
  // must validate the existing SDK range before interpreting it as an opening.
  EXPECT_TRUE(gg::FaceInsideJawCapture({0, 0, .1238}, .1358, .04, .1019));
  EXPECT_FALSE(nd::PlausibleOpening(.1019));
  EXPECT_FALSE(nd::PlausibleOpening(NAN));
  EXPECT_TRUE(nd::PlausibleOpening(.05));
  EXPECT_TRUE(nd::PlausibleOpening(.100));
  EXPECT_FALSE(nd::PlausibleOpening(.100001));
  EXPECT_TRUE(gg::FaceInsideJawCapture({0, 0, .1238}, .1358, .04, .05));
}
