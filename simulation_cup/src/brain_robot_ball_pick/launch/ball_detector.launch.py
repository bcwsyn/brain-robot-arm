from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    parameters = str(Path(get_package_share_directory('brain_robot_ball_pick')) /
                     'config' / 'ball_detector.yaml')
    return LaunchDescription([
        Node(package='brain_robot_pick_place', executable='cup_detector_node',
             name='ball_detector', output='screen', parameters=[parameters]),
    ])
