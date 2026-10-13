#include <cstdlib>
#include <iomanip>
#include <iostream>
#include "brain_robot_pick_place/target_directed_grasp.hpp"

// Read-only offline helper: share the exact executor geometry, output JSON.
int main(int argc, char ** argv)
{
  if (argc != 15 && argc != 16 && argc != 17) {return 2;}
  try {
    double v[14];
    for (int i = 0; i < 14; ++i) {v[i] = std::stod(argv[i + 1]);}
    const auto path = brain_robot_pick_place::grasp_geometry::TargetDirectedApproach(
      {v[0], v[1], v[2]}, {v[3], v[4], v[5], v[6]}, {v[7], v[8], v[9]},
      v[10], v[11], v[12], v[13], argc >= 16 ? std::stod(argv[15]) : 1.0,
      argc == 17 && std::stoi(argv[16]) != 0);
    const auto print = [](const auto & poses) {
        std::cout << '[';
        for (std::size_t i = 0; i < poses.size(); ++i) {
          if (i) {std::cout << ',';}
          const auto & p = poses[i];
          std::cout << "{\"origin\":[" << p.origin[0] << ',' << p.origin[1] << ',' << p.origin[2]
                    << "],\"orientation\":[" << p.orientation[0] << ',' << p.orientation[1] << ','
                    << p.orientation[2] << ',' << p.orientation[3] << "]}";
        }
        std::cout << ']';
      };
    std::cout << std::setprecision(17) << "{\"pregrasp\":";
    print(path.pregrasp);
    std::cout << ",\"descent\":";
    print(path.descent);
    std::cout << "}\n";
    return 0;
  } catch (const std::exception & error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
