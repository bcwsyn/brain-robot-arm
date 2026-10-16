"""Isolated actual P4 executor replay. No driver, adapter, Servo or hardware."""
import importlib.util
import os
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def generate_launch_description():
    assert os.environ.get('ROS_DOMAIN_ID') == '78'
    # Reuse the reviewed original-model planning-only scene.
    planning = module(Path(__file__).with_name('review_terminal_depth_plan.launch.py'), 'p4_scene')
    entities = list(planning.generate_launch_description().entities)
    share = Path(get_package_share_directory('brain_robot_ball_pick'))
    original = module(share / 'launch/cube_visual_search.launch.py', 'p4_original')
    visual, grasp = original._p4_overrides(os.environ)
    assert visual == {'stop_after_observe': True} and grasp['p4_plan_only'] is True
    profile = share / 'config/cube_task_real.yaml'
    task = yaml.safe_load(profile.read_text())['grasp_lift_executor']['ros__parameters']
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').to_moveit_configs()
    model.robot_description['robot_description'] = original._physical_gripper_description(
        model.robot_description['robot_description'], joint5_upper=task['real_trajectory_joint_max'][4])
    entities.append(Node(package='brain_robot_pick_place', executable='grasp_lift_executor',
                         name='grasp_lift_executor', output='screen',
                         parameters=[model.to_dict(), str(profile), grasp]))
    return LaunchDescription(entities)
