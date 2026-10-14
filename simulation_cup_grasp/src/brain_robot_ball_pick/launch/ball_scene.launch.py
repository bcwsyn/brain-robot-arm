from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory('brain_robot_ball_pick'))
    parameters = str(share / 'config' / 'ball_scene.yaml')
    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=parameters),
        Node(package='brain_robot_ball_pick', executable='ball_scene_manager_node.py',
             name='ball_scene_manager', output='screen', parameters=[LaunchConfiguration('params_file')]),
        Node(package='brain_robot_ball_pick', executable='ball_follow_node.py',
             name='ball_follow', output='screen', parameters=[LaunchConfiguration('params_file')]),
    ])
