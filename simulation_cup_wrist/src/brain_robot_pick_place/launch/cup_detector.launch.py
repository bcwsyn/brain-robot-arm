import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('brain_robot_pick_place')
    default_params = os.path.join(package_share, 'config', 'cup_detector.yaml')

    rgb_topic = LaunchConfiguration('rgb_topic')
    depth_topic = LaunchConfiguration('depth_topic')
    camera_info_topic = LaunchConfiguration('camera_info_topic')
    camera_optical_frame = LaunchConfiguration('camera_optical_frame')
    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Cup detector parameter file.',
        ),
        DeclareLaunchArgument(
            'rgb_topic',
            default_value='/wrist_camera/wrist_camera/image_raw',
            description='RGB image topic; remap this for Gemini2.',
        ),
        DeclareLaunchArgument(
            'depth_topic',
            default_value='/wrist_camera/wrist_camera/depth/image_raw',
            description='Aligned depth image topic; remap this for Gemini2.',
        ),
        DeclareLaunchArgument(
            'camera_info_topic',
            default_value='/wrist_camera/wrist_camera/camera_info',
            description='RGB CameraInfo topic; remap this for Gemini2.',
        ),
        DeclareLaunchArgument(
            'camera_optical_frame',
            default_value='wrist_camera_optical_frame',
            description='Optical frame that matches RGB and aligned depth pixels.',
        ),
        Node(
            package='brain_robot_pick_place',
            executable='cup_detector_node',
            name='cup_detector',
            output='screen',
            parameters=[
                params_file,
                {
                    'rgb_topic': rgb_topic,
                    'depth_topic': depth_topic,
                    'camera_info_topic': camera_info_topic,
                    'camera_optical_frame': camera_optical_frame,
                },
            ],
        ),
    ])
