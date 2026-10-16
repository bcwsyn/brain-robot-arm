"""Only the installed model and mount TF; no controller or command interfaces."""
import hashlib
import runpy
from pathlib import Path
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder

ROOT = Path(__file__).resolve().parent

def generate_launch_description():
    share = Path(get_package_share_directory('brain_robot_ball_pick'))
    original = runpy.run_path(str(share / 'launch/cube_visual_search.launch.py'))
    config = share / 'config/cube_task_real.yaml'
    profile = yaml.safe_load(config.read_text())
    upper = profile['grasp_lift_executor']['ros__parameters']['real_trajectory_joint_max'][4]
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').sensors_3d(
        str(share / 'config/sensors_3d_real.yaml')).to_moveit_configs()
    description = original['_physical_gripper_description'](
        model.robot_description['robot_description'], joint5_upper=upper)
    sha = hashlib.sha256(description.encode()).hexdigest()
    if sha != '0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82':
        raise RuntimeError('Installed robot model changed: ' + sha)
    import json
    with (ROOT / 'installed_launch_resolution.json').open('x') as stream:
        json.dump({'config': str(config), 'resolved_config': str(config.resolve()),
            'config_SHA256': hashlib.sha256(config.read_bytes()).hexdigest(),
            'model_SHA256': sha, 'mount_arguments': original['_camera_mount_arguments'](profile),
            'no_controller_nodes': True, 'joint_source': '/joint_states_feedback'}, stream, indent=2)
    return LaunchDescription([
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             name='calibration_static_model', parameters=[{'robot_description': description,
             'use_sim_time': False}], remappings=[('/joint_states', '/joint_states_feedback')]),
        Node(package='tf2_ros', executable='static_transform_publisher',
             name='piper_camera_mount_tf', arguments=original['_camera_mount_arguments'](profile)),
    ])
