"""Dedicated cup executor and exclusive force node; no Servo/search writer."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    config = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').planning_pipelines(
        pipelines=['ompl'], default_planning_pipeline='ompl').to_moveit_configs()
    return LaunchDescription([
        DeclareLaunchArgument('params_file'),
        DeclareLaunchArgument('allow_fault_injection', default_value='false'),
        Node(package='brain_robot_pick_place', executable='grasp_lift_executor',
             parameters=[config.to_dict(), LaunchConfiguration('params_file'), {'use_sim_time': True}],
             remappings=[('/brain_robot_vision/target_valid', '/brain_robot_vision/cup_target_valid')],
             output='screen'),
        Node(package='brain_robot_pick_place', executable='cup_force_gripper_node.py',
             parameters=[{'use_sim_time': True,
                          'allow_fault_injection': LaunchConfiguration('allow_fault_injection')}], output='screen'),
    ])
