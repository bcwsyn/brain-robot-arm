from launch.actions import SetEnvironmentVariable
import os
import re

import xacro
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, EmitEvent
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch.substitutions import Command
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def remove_comments(text):
    return re.sub(r'<!--(.*?)-->', '', text, flags=re.DOTALL)


def generate_launch_description():
    start_raw_viewer = LaunchConfiguration('start_raw_viewer')
    gui = LaunchConfiguration('gui')
    world = LaunchConfiguration('world')
    package_share = FindPackageShare(
        package='brain_robot_pick_place').find('brain_robot_pick_place')
    xacro_path = os.path.join(
        package_share, 'urdf', 'piper_with_wrist_camera_gazebo.xacro')

    robot_description = {
        'robot_description': ParameterValue(Command(['xacro ', xacro_path,
            ' physics_grasp:=', LaunchConfiguration('physics_grasp'),
            ' physics_jaw_kp:=', LaunchConfiguration('physics_jaw_kp'),
            ' physics_jaw_kd:=', LaunchConfiguration('physics_jaw_kd')]), value_type=str)
    }

    gazebo = ExecuteProcess(
        cmd=[
            'gazebo', '--verbose', world,
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
        ],
        output='screen',
        condition=IfCondition(gui),
    )
    gazebo_debug_server = ExecuteProcess(
        cmd=["gdb", "--batch", "-x", LaunchConfiguration("gdb_script"), "--args",
             "gzserver", "--verbose", world, "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so"],
        output="screen", condition=IfCondition(LaunchConfiguration("debug_server")))
    gazebo_server = ExecuteProcess(
        cmd=['gzserver', '--verbose', world, '-s', 'libgazebo_ros_init.so',
             '-s', 'libgazebo_ros_factory.so', '--ros-args', '--params-file',
             LaunchConfiguration('gazebo_params_file'), '--'],
        output='screen',
        condition=IfCondition(PythonExpression(["'", gui, "' == 'false' and '", LaunchConfiguration("debug_server"), "' == 'false'"])),
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[
            {'use_sim_time': True},
            robot_description,
            {'publish_frequency': ParameterValue(LaunchConfiguration('state_publish_frequency'), value_type=float)},
        ],
        output='screen',
    )

    spawn_robot = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=['-entity', 'piper', '-topic', 'robot_description'],
        output='screen',
    )

    controllers = Node(package='brain_robot_pick_place', executable='sim_controller_bootstrap.py',
                       output='screen')
    load_controllers_after_spawn = RegisterEventHandler(
        OnProcessExit(target_action=spawn_robot, on_exit=[controllers]))

    gripper_mirror = Node(
        package='piper_gazebo',
        executable='joint8_ctrl.py',
        output='screen',
        condition=UnlessCondition(LaunchConfiguration('physics_grasp')),
    )
    camera_viewer = Node(
        package='brain_robot_pick_place',
        executable='wrist_camera_viewer.py',
        name='wrist_camera_viewer',
        output='screen',
        parameters=[{'use_sim_time': True}],
        condition=IfCondition(start_raw_viewer),
    )

    return LaunchDescription([
        SetEnvironmentVariable("RMW_FASTRTPS_PUBLICATION_MODE", "ASYNCHRONOUS"),
        DeclareLaunchArgument('physics_grasp', default_value='false'),
        DeclareLaunchArgument('physics_jaw_kp', default_value='300'),
        DeclareLaunchArgument('physics_jaw_kd', default_value='0.2'),
        DeclareLaunchArgument('state_publish_frequency', default_value='15.0'),
        DeclareLaunchArgument('gazebo_params_file', default_value=os.path.join(package_share, 'config', 'gazebo_clock_default.yaml')),
        DeclareLaunchArgument('debug_server', default_value='false'),
        DeclareLaunchArgument('gdb_script', default_value=''),
        DeclareLaunchArgument('gui', default_value='true',
                              description='Start Gazebo GUI; false runs only gzserver.'),
        DeclareLaunchArgument('world', default_value=os.path.join(
            FindPackageShare(package='gazebo_ros').find('gazebo_ros'),
            'worlds', 'empty.world'), description='Gazebo world file.'),
        DeclareLaunchArgument(
            'start_raw_viewer',
            default_value='false',
            description='Start the legacy Tkinter raw camera viewer.',
        ),
        RegisterEventHandler(OnProcessExit(target_action=gazebo_server,
            on_exit=[EmitEvent(event=Shutdown(reason="Gazebo server exited"))])),
        load_controllers_after_spawn,
        gripper_mirror,
        gazebo,
        gazebo_server,
        gazebo_debug_server,
        robot_state_publisher,
        spawn_robot,
        camera_viewer,
    ])
