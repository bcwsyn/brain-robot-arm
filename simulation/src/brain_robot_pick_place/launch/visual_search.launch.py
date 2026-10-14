from launch.actions import SetEnvironmentVariable
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def generate_launch_description():
    package_share = get_package_share_directory('brain_robot_pick_place')
    default_controller_params = os.path.join(
        package_share, 'config', 'visual_search_sim.yaml')
    servo_path = os.path.join(
        package_share, 'config', 'piper_servo_sim.yaml')

    params_file = LaunchConfiguration('params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    backend = LaunchConfiguration('backend')
    moveit_config = MoveItConfigsBuilder(
        'piper', package_name='piper_with_gripper_moveit').planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl").to_moveit_configs()
    servo_params = {'moveit_servo': load_yaml(servo_path)}

    servo_node = Node(
        package='moveit_servo',
        executable='servo_node_main',
        name='servo_node',
        output='screen',
        parameters=[
            servo_params,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            {'use_sim_time': ParameterValue(use_sim_time, value_type=bool)},
        ],
    )

    controller_node = Node(
        package='brain_robot_pick_place',
        executable='visual_search_controller',
        name='visual_search_controller',
        output='screen',
        parameters=[
            moveit_config.to_dict(),
            params_file,
            {
                'backend': backend,
                'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
            },
        ],
    )

    grasp_executor_node = Node(
        package='brain_robot_pick_place',
        executable='grasp_lift_executor',
        name='grasp_lift_executor',
        output='screen',
        parameters=[
            moveit_config.to_dict(),
            params_file,
            {
                'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
            },
        ],
    )

    return LaunchDescription([
        SetEnvironmentVariable("RMW_FASTRTPS_PUBLICATION_MODE", "ASYNCHRONOUS"),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_controller_params,
            description='Visual controller parameter profile.',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use Gazebo clock.',
        ),
        DeclareLaunchArgument(
            'backend',
            default_value='simulation',
            description='simulation or piper; physical profile remains locked by default.',
        ),
        servo_node,
        controller_node,
        grasp_executor_node,
    ])
