#ifndef BRAIN_ROBOT_PICK_PLACE__TARGET_MODEL_WAIT_HPP_
#define BRAIN_ROBOT_PICK_PLACE__TARGET_MODEL_WAIT_HPP_

namespace brain_robot_pick_place
{
// Freshness is checked inside each attempt, not a deadline for the whole wait.
// The owner supplies shutdown/cancel handling and a short, interruptible poll.
template<typename Running, typename Attempt, typename Pause>
bool WaitForFreshTargetModel(Running running, Attempt attempt, Pause pause)
{
  while (running()) {
    if (attempt()) {
      return running();
    }
    pause();
  }
  return false;
}
}  // namespace brain_robot_pick_place

#endif  // BRAIN_ROBOT_PICK_PLACE__TARGET_MODEL_WAIT_HPP_
