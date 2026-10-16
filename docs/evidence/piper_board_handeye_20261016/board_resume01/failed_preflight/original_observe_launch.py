"""Reuse the original installed launch, with no grasp executor for P1 capture."""
import importlib.util
from launch import LaunchDescription, LaunchService, LaunchContext
from launch_ros.actions import Node
from launch.utilities import perform_substitutions
from ament_index_python.packages import get_package_share_directory
from pathlib import Path

path = Path(get_package_share_directory('brain_robot_ball_pick')) / 'launch/cube_visual_search.launch.py'
spec = importlib.util.spec_from_file_location('original_visual_launch', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module.generate_launch_description()
entities, removed = [], 0
for entity in original.entities:
    executable = entity.node_executable if isinstance(entity, Node) else None
    if executable is not None and not isinstance(executable, str):
        executable = perform_substitutions(LaunchContext(), executable)
    if executable == 'grasp_lift_executor':
        removed += 1
    else:
        entities.append(entity)
assert removed == 1
print('P1: original launch minus grasp executor; STOP_BEFORE_SEARCH set/read before START', flush=True)
service = LaunchService()
service.include_launch_description(LaunchDescription(entities))
raise SystemExit(service.run())
