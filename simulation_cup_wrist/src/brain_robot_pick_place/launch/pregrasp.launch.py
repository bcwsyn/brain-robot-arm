from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    moveit_config = MoveItConfigsBuilder(
        'piper', package_name='piper_with_gripper_moveit').planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl").to_moveit_configs()

    execute = DeclareLaunchArgument(
        'execute',
        default_value='false',
        description='Actually execute the trajectory. Keep false for the first test.',
    )
    pregrasp_clearance = DeclareLaunchArgument(
        'pregrasp_clearance',
        default_value='0.12',
        description='Vertical clearance above the top-down grasp pose in metres.',
    )
    require_zero_state = DeclareLaunchArgument(
        'require_zero_state',
        default_value='true',
        description='Require the arm to start near the SRDF zero state.',
    )
    full_sequence = DeclareLaunchArgument(
        'full_sequence',
        default_value='false',
        description='Run grasp, transfer and placement after reaching pregrasp.',
    )

    pregrasp_node = Node(
        package='brain_robot_pick_place',
        executable='pick_place_node',
        name='pick_place_node',
        output='screen',
        parameters=[
            moveit_config.to_dict(),
            {
                'simulation_only': True,
                'execute': ParameterValue(
                    LaunchConfiguration('execute'), value_type=bool),
                'gripper_tip_offset': 0.1358,
                'pregrasp_clearance': ParameterValue(
                    LaunchConfiguration('pregrasp_clearance'), value_type=float),
                'approach_clearance': 0.06,
                'grasp_height_offset': 0.0,
                'lift_clearance': 0.15,
                'grasp_yaw': 0.0,
                'place_x': 0.40,
                'place_y': 0.12,
                'require_zero_state': ParameterValue(
                    LaunchConfiguration('require_zero_state'), value_type=bool),
                'full_sequence': ParameterValue(
                    LaunchConfiguration('full_sequence'), value_type=bool),
                'use_sim_time': True,
            },
        ],
    )

    return LaunchDescription([
        execute,
        pregrasp_clearance,
        require_zero_state,
        full_sequence,
        pregrasp_node,
    ])
