import math
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_static_virtual_joint_tfs_launch


def _load_yaml(path):
    with open(path, encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def _camera_mount_arguments(task_profile):
    mount = task_profile['piper_camera_mount_tf']['ros__parameters']
    xyz = mount['translation_m']
    rpy = mount['rotation_rpy_rad']
    if len(xyz) != 3 or len(rpy) != 3 or not all(
            math.isfinite(float(value)) for value in xyz + rpy):
        raise RuntimeError('camera mount must contain finite XYZ and RPY triples')
    # The legacy positional interface expects yaw, pitch, roll (not RPY).
    return [str(float(value)) for value in xyz + [rpy[2], rpy[1], rpy[0]]] + [
        'gripper_base', 'camera_link']


def generate_launch_description():
    cube_share = get_package_share_directory('brain_robot_ball_pick')
    base_share = get_package_share_directory('brain_robot_pick_place')
    task_config_path = os.path.join(cube_share, 'config', 'cube_task_real.yaml')
    task_profile = _load_yaml(task_config_path)
    grasp_parameters = task_profile['grasp_lift_executor']['ros__parameters']
    real_joint_mins = grasp_parameters['real_trajectory_joint_min']
    real_joint_maxs = grasp_parameters['real_trajectory_joint_max']
    if len(real_joint_mins) != 6 or len(real_joint_maxs) != 6:
        raise RuntimeError('real grasp limits must contain exactly six joints')
    # The Astra is mounted on the gripper. Feeding its depth cloud into
    # MoveIt's world-geometry updater makes the moving gripper part of the
    # obstacle map whenever camera/joint timestamps are skewed, which can
    # produce collision-planning oscillation on the physical arm. The
    # detector still consumes RGB-D; the corresponding sensor configuration
    # keeps the updater loaded but disconnects the wrist cloud from Octomap.
    moveit = MoveItConfigsBuilder(
        'piper', package_name='piper_with_gripper_moveit').sensors_3d(
            os.path.join(cube_share, 'config', 'sensors_3d_real.yaml')).to_moveit_configs()
    moveit_parameters = moveit.to_dict()
    for joint_name, min_position, max_position in zip(
            ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6"),
            real_joint_mins, real_joint_maxs):
        joint_limits = moveit_parameters["robot_description_planning"]["joint_limits"][joint_name]
        joint_limits["has_position_limits"] = True
        joint_limits["min_position"] = float(min_position)
        joint_limits["max_position"] = float(max_position)
        joint_limits["has_acceleration_limits"] = True
        joint_limits["max_acceleration"] = 1.0
    servo_params = {'moveit_servo': _load_yaml(
        os.path.join(base_share, 'config', 'piper_servo_real.yaml'))}
    move_group_params = [
        moveit_parameters,
        {
            # This process is only the state/planning-scene authority for the
            # protected visual path.  Physical trajectories remain disabled;
            # piper_jog_adapter is the sole arm-command output path.
            'allow_trajectory_execution': False,
            'publish_robot_description_semantic': True,
            'publish_planning_scene': True,
            'publish_geometry_updates': True,
            'publish_state_updates': True,
            'publish_transforms_updates': True,
            'monitor_dynamics': False,
            'use_sim_time': False,
            # Keep the depth-camera occupancy map in the robot base frame so
            # MoveIt can check candidate grasp paths against the environment.
            'octomap_frame': 'base_link',
            'octomap_resolution': 0.02,
        },
    ]
    robot_state_publisher = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        name='robot_state_publisher', output='screen',
        parameters=[moveit.robot_description, {'use_sim_time': False}],
        remappings=[('/joint_states', '/piper_moveit_joint_states')])
    # Physical wrist mount: camera optical +Z looks along gripper_base +Z,
    # the jaw/tool centreline defined by joint7/joint8 in the PiPER URDF.
    # camera_link +X is the optical-frame +Z axis, so rotate camera_link -90
    # degrees about gripper_base Y.  Keeping both frames parallel incorrectly
    # maps camera depth onto gripper +X and places tabletop targets behind the
    # wrist in base_link.
    camera_mount_tf = Node(
        package='tf2_ros', executable='static_transform_publisher',
        name='piper_camera_mount_tf', output='screen',
        arguments=_camera_mount_arguments(task_profile))
    static_virtual_joint_tfs = generate_static_virtual_joint_tfs_launch(moveit)
    return LaunchDescription(static_virtual_joint_tfs.entities + [
        robot_state_publisher,
        camera_mount_tf,
        Node(package='brain_robot_pick_place', executable='pointcloud_tf_gate',
             name='pointcloud_tf_gate', output='screen', parameters=[
                 task_config_path,
                 {'use_sim_time': False}]),
        Node(package='moveit_ros_move_group', executable='move_group', name='move_group',
             output='screen', parameters=move_group_params,
             remappings=[('/joint_states', '/piper_moveit_joint_states')]),
        Node(package='moveit_servo', executable='servo_node_main', name='servo_node',
             output='screen', parameters=[servo_params, moveit.robot_description,
             moveit.robot_description_semantic, moveit.robot_description_kinematics,
             {'use_sim_time': False}]),
        Node(package='brain_robot_pick_place', executable='piper_jog_adapter.py',
             name='piper_jog_adapter', output='screen', parameters=[{
                 'motion_enabled': False,
                 'input_topic': '/servo_node/delta_joint_cmds',
                 'joint_state_topic': '/joint_states',
                 'filtered_joint_state_topic': '/piper_moveit_joint_states',
                 'output_topic': '/joint_commands',
                 'emergency_stop_topic': '/brain_robot_control/emergency_stop',
                 'max_velocity_rad_s': 0.189,
                 'trajectory_start_tolerance_rad': 0.10,
                 'trajectory_max_joint_step_rad': 0.35,
                 'gripper_effort_nm': 1.0,
                 # The vendor driver subscribes with queue depth one. Repeat
                 # the explicit frame for only 100 ms so a following arm-only
                 # frame cannot overwrite it before the callback runs.
                 # The official SDK gripper example holds each target for
                 # about 1.5 s. Keep this bounded at 80 x 20 ms so a vendor
                 # callback cannot lose the command before the motor reacts.
                 'gripper_command_repeats': 80,
                 'joint_min': real_joint_mins,
                 'joint_max': real_joint_maxs,
                 # The VM can briefly delay ROS subscription callbacks even
                 # while the driver is still publishing feedback.  Keep a
                 # bounded but realistic timeout for the physical adapter.
                 # S-V1.9-1 can pause feedback for about 18 s while switching
                 # 0x2Ax -> 0x3Ax on the first motion transition.  The driver
                 # suppresses output during that bounded window; do not disarm
                 # the adapter before the verified transition can complete.
                 'joint_state_timeout_s': 25.0,
                 # Expanded real-arm J1 envelope; J1/J5 scan the configured
                 # bounds while J2/J3/J4/J6 retain their existing limits.
                 'visual_joint_max_delta_rad': [1.50, 0.20, 0.20, 0.05, 0.95, 0.05],
             }]),
        Node(package='brain_robot_pick_place', executable='visual_search_controller',
             name='visual_search_controller', output='screen', parameters=[
                 moveit_parameters,
                 task_config_path,
                 {'backend': 'piper', 'use_sim_time': False}]),
        Node(package='brain_robot_pick_place', executable='grasp_lift_executor',
             name='grasp_lift_executor', output='screen', parameters=[
                 moveit_parameters,
                 task_config_path,
                 {'use_sim_time': False}],
             remappings=[('/joint_states', '/piper_moveit_joint_states')]),
        # Depth geometry gate. It publishes only candidate geometry/validity;
        # the existing controller and grasp executor remain the sole motion
        # command paths.
        Node(package='brain_robot_pick_place', executable='depth_cube_probe.py',
             name='depth_cube_probe', output='screen', parameters=[
                 task_config_path,
                 {'use_sim_time': False}]),
        # This node only reports whether the current session has fresh RGB-D,
        # joint, TF and Planning Scene inputs. It publishes no arm command.
        Node(package='brain_robot_pick_place', executable='active_scan_supervisor',
             name='active_scan_supervisor', output='screen', parameters=[
                 task_config_path,
                 {'use_sim_time': False}]),
    ])
