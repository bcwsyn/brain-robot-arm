#!/usr/bin/env python3
"""Read-only checks for the published Humble/Gazebo Classic simulation."""
import argparse
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


LOCAL_PACKAGES = (
    'brain_robot_pick_place', 'brain_robot_ball_pick', 'piper_description',
    'piper_msgs', 'piper_gazebo', 'piper_with_gripper_moveit',
    'piper_no_gripper_moveit',
)
ROS_PACKAGES = (
    'ament_cmake', 'ament_cmake_gtest', 'ament_cmake_pytest', 'cv_bridge',
    'gazebo_dev', 'gazebo_ros', 'gazebo_plugins', 'gazebo_ros2_control',
    'controller_manager', 'controller_manager_msgs', 'joint_state_broadcaster',
    'joint_trajectory_controller', 'control_msgs', 'gazebo_msgs',
    'moveit_ros_move_group', 'moveit_configs_utils', 'moveit_servo',
    'moveit_kinematics', 'moveit_planners_ompl', 'moveit_ros_visualization',
    'robot_state_publisher', 'rviz2', 'xacro', 'tf2_ros',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true',
                        help='Also check the local overlay, rendering display and port')
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1]
    errors = []

    def check(condition, description):
        print(('PASS ' if condition else 'FAIL ') + description)
        if not condition:
            errors.append(description)

    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines()
                   if '=' in line)
    check(release.get('ID', '').strip('"') == 'ubuntu' and
          release.get('VERSION_ID', '').strip('"') == '22.04', 'Ubuntu 22.04')
    check(os.environ.get('ROS_DISTRO') == 'humble', 'ROS_DISTRO=humble (source Humble first)')
    check(not os.environ.get('CONDA_PREFIX'), 'Conda is inactive')
    check(sys.version_info[:2] == (3, 10), 'System Python 3.10')
    check(bool(sys.flags.no_user_site), 'Python user site disabled (use python3 -s)')
    for executable in ('colcon', 'cmake', 'ros2', 'xacro', 'gazebo', 'gzserver', 'gzclient', 'rviz2'):
        check(bool(shutil.which(executable)), 'Executable: ' + executable)
    for module in ('numpy', 'scipy', 'cv2', 'yaml', 'cv_bridge', 'rclpy',
                   'tf2_ros', 'ament_index_python', 'launch_ros'):
        try:
            imported = importlib.import_module(module)
            check(True, 'Python module: ' + module)
            if module == 'numpy':
                check(int(imported.__version__.split('.')[0]) == 1,
                      'NumPy 1.x for the Ubuntu Humble cv_bridge binary')
        except Exception as exc:
            check(False, 'Python module: ' + module + ' (' + str(exc) + ')')
    try:
        from ament_index_python.packages import get_package_prefix
        for package in ROS_PACKAGES:
            try:
                get_package_prefix(package)
                check(True, 'ROS package: ' + package)
            except LookupError:
                check(False, 'ROS package: ' + package)
        for library in ('libgazebo_ros_state.so', 'libgazebo_ros_bumper.so',
                        'libgazebo_ros_init.so', 'libgazebo_ros_factory.so',
                        'libgazebo_ros2_control.so'):
            check(Path('/opt/ros/humble/lib', library).is_file(), 'Plugin: ' + library)
        if args.runtime:
            for package in LOCAL_PACKAGES:
                try:
                    prefix = Path(get_package_prefix(package)).resolve()
                    check(prefix.is_relative_to(workspace / 'install'),
                          'Local overlay: ' + package + ' -> ' + str(prefix))
                except LookupError:
                    check(False, 'Local overlay missing: ' + package + ' (build first)')
    except ImportError:
        check(False, 'ament_index_python: source /opt/ros/humble/setup.bash')
    for relative in ('validation/grasp_validation.world', 'validation/fastdds_local_udp.xml',
                     'config/visual_grasp.rviz'):
        check((workspace / relative).is_file(), 'Resource: ' + relative)
    if args.runtime:
        display = os.environ.get('DISPLAY', '')
        check(bool(display), 'DISPLAY available (RGB-D rendering needs a display, even --headless)')
        if display and shutil.which('xdpyinfo'):
            result = subprocess.run(['xdpyinfo'], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=10)
            check(result.returncode == 0, 'X display accessible')
        import socket
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 11483))
            check(True, 'Gazebo session port 11483 available')
        except OSError:
            check(False, 'Gazebo port 11483 occupied; quit the other session')
    print('\nEnvironment checks: ' + ('PASSED' if not errors else 'FAILED'))
    print('No packages were installed and no hardware or motion was started.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
