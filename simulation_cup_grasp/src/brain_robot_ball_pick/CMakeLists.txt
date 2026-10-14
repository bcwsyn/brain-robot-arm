cmake_minimum_required(VERSION 3.8)
project(brain_robot_ball_pick)

find_package(ament_cmake REQUIRED)

install(PROGRAMS
  scripts/ball_scene_manager_node.py
  scripts/ball_follow_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch models
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
