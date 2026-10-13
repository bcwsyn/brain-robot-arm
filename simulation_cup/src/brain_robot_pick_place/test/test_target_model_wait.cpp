#include <gtest/gtest.h>
#include "brain_robot_pick_place/target_model_wait.hpp"

using brain_robot_pick_place::WaitForFreshTargetModel;

TEST(TargetModelWait, RetriesDelayedTransformWithoutFault)
{
  int tick = 0;
  EXPECT_TRUE(WaitForFreshTargetModel(
      []() {return true;}, [&]() {return tick >= 3;}, [&]() {++tick;}));
  EXPECT_EQ(tick, 3);
}

TEST(TargetModelWait, WholeWaitCanExceedFrameFreshness)
{
  int tick = 0;
  int frame_received = 0;
  EXPECT_TRUE(WaitForFreshTargetModel(
      []() {return true;},
      [&]() {return tick - frame_received <= 6 && tick >= 15;},
      [&]() {++tick; if (tick == 14) {frame_received = tick;}}));
  EXPECT_EQ(tick, 15);  // Fresh new frame after a longer wait, not stale reuse.
}

TEST(TargetModelWait, StaleFrameNeverLocksAndCancellationEndsWait)
{
  int tick = 0;
  EXPECT_FALSE(WaitForFreshTargetModel(
      [&]() {return tick < 20;},
      [&]() {return tick <= 6 && tick >= 10;}, [&]() {++tick;}));
  EXPECT_EQ(tick, 20);
}

TEST(TargetModelWait, AlreadyCancelledDoesNotAttempt)
{
  int attempts = 0;
  EXPECT_FALSE(WaitForFreshTargetModel(
      []() {return false;}, [&]() {++attempts; return true;}, []() {}));
  EXPECT_EQ(attempts, 0);
}

TEST(TargetModelWait, CancelAtLockDoesNotContinueToMotion)
{
  bool running = true;
  EXPECT_FALSE(WaitForFreshTargetModel(
      [&]() {return running;}, [&]() {running = false; return true;}, []() {}));
}
