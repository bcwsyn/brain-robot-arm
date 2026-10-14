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


def _load_yaml(path):
    with open(path, encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def generate_launch_description():
    ball_share = get_package_share_directory('brain_robot_ball_pick')
    base_share = get_package_share_directory('brain_robot_pick_place')
    params_file = LaunchConfiguration('params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    backend = LaunchConfiguration('backend')
    moveit = MoveItConfigsBuilder(
        'piper', package_name='piper_with_gripper_moveit').planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl").to_moveit_configs()
    servo_params = {'moveit_servo': _load_yaml(os.path.join(base_share, 'config', 'piper_servo_sim.yaml'))}
    common_time = {'use_sim_time': ParameterValue(use_sim_time, value_type=bool)}
    return LaunchDescription([
        SetEnvironmentVariable("RMW_FASTRTPS_PUBLICATION_MODE", "ASYNCHRONOUS"),
        DeclareLaunchArgument('params_file', default_value=os.path.join(ball_share, 'config', 'ball_task_sim.yaml')),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('backend', default_value='simulation'),
        Node(package='moveit_servo', executable='servo_node_main', name='servo_node', output='screen',
             parameters=[servo_params, moveit.robot_description, moveit.robot_description_semantic,
                         moveit.robot_description_kinematics, common_time]),
        Node(package='brain_robot_pick_place', executable='visual_search_controller',
             name='visual_search_controller', output='screen',
             parameters=[moveit.to_dict(), params_file, {'backend': backend}, common_time]),
        Node(package='brain_robot_pick_place', executable='grasp_lift_executor',
             name='grasp_lift_executor', output='screen',
             parameters=[moveit.to_dict(), params_file, common_time]),
    ])
