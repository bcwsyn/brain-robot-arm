"""Actual executor + original planning scene, synthetic feedback only, domain78."""
import importlib.util,os
from pathlib import Path
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    assert os.environ['ROS_DOMAIN_ID']=='78'
    path=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_p4_open_loop.launch.py')
    spec=importlib.util.spec_from_file_location('original_p4_review',path)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    # Original helper intentionally insists on plan-only. Reuse its planning
    # scene/Node definitions, then only replace executor's opt-in parameters.
    os.environ['BRAIN_ROBOT_P4_PLAN_ONLY']='1'
    entities=list(original.generate_launch_description().entities)
    entities.pop()  # executor is the last entity in this reviewed helper
    from ament_index_python.packages import get_package_share_directory
    from moveit_configs_utils import MoveItConfigsBuilder
    import yaml
    share=Path(get_package_share_directory('brain_robot_ball_pick'))
    spec=importlib.util.spec_from_file_location('runtime_original',share/'launch/cube_visual_search.launch.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    os.environ['BRAIN_ROBOT_P4_PLAN_ONLY']='0'
    _,grasp=runtime._p4_overrides(os.environ)
    profile=share/'config/cube_task_real.yaml'
    task=yaml.safe_load(profile.read_text())['grasp_lift_executor']['ros__parameters']
    model=MoveItConfigsBuilder('piper',package_name='piper_with_gripper_moveit').to_moveit_configs()
    model.robot_description['robot_description']=runtime._physical_gripper_description(
        model.robot_description['robot_description'],joint5_upper=task['real_trajectory_joint_max'][4])
    entities.append(Node(package='brain_robot_pick_place',executable='grasp_lift_executor',
        name='grasp_lift_executor',output='screen',parameters=[model.to_dict(),str(profile),grasp],
        arguments=['--ros-args','-p','grasp_lift_executor:auto_release_after_lift:=false',
                   '-p','grasp_lift_executor:gripper_feedback_topic:=/piper/gripper_feedback']))
    return LaunchDescription(entities)
