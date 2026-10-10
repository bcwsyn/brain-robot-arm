cmake_minimum_required(VERSION 3.8)
project(brain_robot_pick_place)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(control_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(gazebo_dev REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(message_filters REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(OpenCV REQUIRED)

link_directories(${gazebo_dev_LIBRARY_DIRS})

add_library(cup_pose_plugin SHARED src/cup_pose_plugin.cpp)
ament_target_dependencies(cup_pose_plugin
  gazebo_dev
  gazebo_ros
  geometry_msgs
  rclcpp
)

add_executable(pick_place_node src/pick_place_node.cpp)
ament_target_dependencies(pick_place_node
  geometry_msgs
  moveit_core
  moveit_ros_planning_interface
  moveit_msgs
  rclcpp
  std_srvs
  tf2_geometry_msgs
  visualization_msgs
)

add_executable(cup_detector_node src/cup_detector_node.cpp)
target_include_directories(cup_detector_node PRIVATE ${OpenCV_INCLUDE_DIRS})
ament_target_dependencies(cup_detector_node
  cv_bridge
  geometry_msgs
  message_filters
  rclcpp
  sensor_msgs
  std_msgs
)
target_link_libraries(cup_detector_node ${OpenCV_LIBRARIES})

add_executable(visual_search_controller src/visual_search_controller.cpp)
ament_target_dependencies(visual_search_controller
  control_msgs
  geometry_msgs
  moveit_core
  moveit_ros_planning_interface
  rclcpp
  sensor_msgs
  std_msgs
  std_srvs
  trajectory_msgs
  tf2
  tf2_geometry_msgs
  tf2_ros
)

add_executable(grasp_lift_executor src/grasp_lift_executor.cpp)
target_include_directories(grasp_lift_executor PRIVATE include)
ament_target_dependencies(grasp_lift_executor
  geometry_msgs
  moveit_core
  moveit_msgs
  moveit_ros_planning_interface
  rclcpp
  sensor_msgs
  std_msgs
  std_srvs
  trajectory_msgs
  tf2
  tf2_geometry_msgs
  tf2_ros
)

add_executable(active_scan_supervisor src/active_scan_supervisor.cpp)
ament_target_dependencies(active_scan_supervisor
  geometry_msgs
  moveit_msgs
  rclcpp
  sensor_msgs
  std_msgs
  tf2
  tf2_ros
)

add_executable(pointcloud_tf_gate src/pointcloud_tf_gate.cpp)
ament_target_dependencies(pointcloud_tf_gate
  rclcpp
  sensor_msgs
  std_msgs
  tf2
  tf2_ros
)

install(TARGETS cup_pose_plugin
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS pick_place_node cup_detector_node visual_search_controller grasp_lift_executor active_scan_supervisor pointcloud_tf_gate
  DESTINATION lib/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/scene_manager_node.py
  scripts/cup_follow_node.py
  scripts/wrist_camera_viewer.py
  scripts/runtime_monitor.py
  scripts/piper_jog_adapter.py
  scripts/depth_cube_probe.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch models urdf
  DESTINATION share/${PROJECT_NAME}
)

ament_environment_hooks(
  "${CMAKE_CURRENT_SOURCE_DIR}/env-hooks/gazebo_plugin_path.dsv.in"
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(grasp_geometry_test test/test_grasp_geometry.cpp)
  target_include_directories(grasp_geometry_test PRIVATE include)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    piper_jog_adapter_test
    test/test_piper_jog_adapter.py
  )
  ament_add_pytest_test(
    real_grasp_replay_test
    test/test_real_grasp_replay.py
  )
endif()

ament_package()
