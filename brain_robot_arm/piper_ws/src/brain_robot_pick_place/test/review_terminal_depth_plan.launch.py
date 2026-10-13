"""Isolated planning only; reuse runtime physical model and original task bounds."""
import importlib.util
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_static_virtual_joint_tfs_launch


def generate_launch_description():
    assert os.environ.get('ROS_DOMAIN_ID') == '78'
    share = get_package_share_directory('brain_robot_ball_pick')
    source = os.path.join(share, 'launch', 'cube_visual_search.launch.py')
    spec = importlib.util.spec_from_file_location('original_visual_launch', source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    with open(os.path.join(share, 'config', 'cube_task_real.yaml')) as stream:
        task = yaml.safe_load(stream)['grasp_lift_executor']['ros__parameters']
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').sensors_3d(
        os.path.join(share, 'config', 'sensors_3d_real.yaml')).to_moveit_configs()
    model.robot_description['robot_description'] = original._physical_gripper_description(
        model.robot_description['robot_description'])
    config = model.to_dict()
    for i in range(6):
        config['robot_description_planning']['joint_limits'][f'joint{i+1}'].update(
            has_position_limits=True, min_position=float(task['real_trajectory_joint_min'][i]),
            max_position=float(task['real_trajectory_joint_max'][i]),
            has_acceleration_limits=True, max_acceleration=1.0)
    nodes = list(generate_static_virtual_joint_tfs_launch(model).entities)
    nodes.append(Node(package='robot_state_publisher', executable='robot_state_publisher',
                      parameters=[model.robot_description, {'use_sim_time': False}], output='screen'))
    nodes.append(Node(package='moveit_ros_move_group', executable='move_group',
                      parameters=[config, {'allow_trajectory_execution': False, 'use_sim_time': False}],
                      output='screen'))
    return LaunchDescription(nodes)
