import os
import yaml
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    if os.environ.get('ROS_DOMAIN_ID') != '78':
        raise RuntimeError('This snapshot planner must run in isolated ROS domain 78')
    share = get_package_share_directory('brain_robot_ball_pick')
    with open(os.path.join(share, 'config', 'cube_task_real.yaml')) as f:
        params = yaml.safe_load(f)['grasp_lift_executor']['ros__parameters']
    model = MoveItConfigsBuilder('piper', package_name='piper_with_gripper_moveit').sensors_3d(
        os.path.join(share, 'config', 'sensors_3d_real.yaml')).to_moveit_configs()
    config = model.to_dict()
    for i in range(6):
        limit = config['robot_description_planning']['joint_limits'][f'joint{i+1}']
        limit.update(has_position_limits=True,
                     min_position=float(params['real_trajectory_joint_min'][i]),
                     max_position=float(params['real_trajectory_joint_max'][i]),
                     has_acceleration_limits=True, max_acceleration=1.0)
    return LaunchDescription([
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[model.robot_description, {'use_sim_time': False}], output='screen'),
        Node(package='moveit_ros_move_group', executable='move_group', name='move_group',
             parameters=[config, {'allow_trajectory_execution': False, 'use_sim_time': False}],
             output='screen')])
