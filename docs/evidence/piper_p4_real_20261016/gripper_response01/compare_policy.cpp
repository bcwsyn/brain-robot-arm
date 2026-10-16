#include <cmath>
#include <iostream>
#include "gentle_gripper.hpp"

int main()
{
  using Policy = brain_robot_pick_place::GentleGripper;
  std::cout << "[";
  for (int quantize_physical = 0; quantize_physical <= 1; ++quantize_physical) {
    Policy policy(.029, .0994);
    double physical = .0994, elapsed = 0.;
    auto result = Policy::Result::MOVING;
    for (; elapsed < policy.Timeout(.0994) && result == Policy::Result::MOVING;
      elapsed += .02)
    {
      const double error = std::max(0., physical-policy.Reference()-.00015);
      physical -= std::min(.010*.02, 4.*error*.02);
      const double measured = std::round(physical/.0001)*.0001;
      if (quantize_physical) {physical = measured;}
      result = policy.Update(1.+elapsed, measured, -.02);
    }
    if (quantize_physical) {std::cout << ",";}
    std::cout << "{\"quantize_physical_state\":" << quantize_physical
              << ",\"elapsed_s\":" << elapsed
              << ",\"finite_timeout_s\":" << policy.Timeout(.0994)
              << ",\"last_actual_mm\":" << physical*1000
              << ",\"last_reference_mm\":" << policy.Reference()*1000
              << ",\"empty\":" << (result == Policy::Result::EMPTY ? "true" : "false")
              << ",\"contact\":" << (result == Policy::Result::CONTACT_CANDIDATE ? "true" : "false") << "}";
  }
  std::cout << "]\n";
}
