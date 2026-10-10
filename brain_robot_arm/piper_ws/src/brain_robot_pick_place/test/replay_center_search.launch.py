"""Isolated real-controller replay: no PiPER, adapter, Servo or grasp executor."""
import importlib.util
import os
from pathlib import Path

import yaml

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    if os.environ.get("ROS_DOMAIN_ID") != "78":
        raise RuntimeError("Center replay requires isolated ROS_DOMAIN_ID=78")
    path = Path(__file__).with_name("review_surface_grasp_plan.launch.py")
    spec = importlib.util.spec_from_file_location("snapshot_planner_launch", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    description = module.generate_launch_description()
    share = get_package_share_directory("brain_robot_ball_pick")
    with open(os.path.join(share, "config", "cube_task_real.yaml")) as stream:
        visual = yaml.safe_load(stream)["visual_search_controller"]["ros__parameters"]
    # Merge the replay override into the same parameter map. A later wildcard
    # map does not reliably override an earlier node-specific YAML entry.
    visual["joint_state_timeout_s"] = 0.5
    model = MoveItConfigsBuilder("piper", package_name="piper_with_gripper_moveit").to_moveit_configs()
    description.add_action(Node(
        package="brain_robot_pick_place", executable="visual_search_controller",
        name="visual_search_controller", output="screen",
        parameters=[model.to_dict(), visual],
    ))
    return description
