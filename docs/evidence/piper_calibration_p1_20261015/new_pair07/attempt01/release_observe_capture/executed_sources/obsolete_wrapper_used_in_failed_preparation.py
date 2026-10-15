"""P1 session wrapper: original installed launch minus grasp executor only."""
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
    if isinstance(entity, Node) and perform_substitutions(LaunchContext(), entity.node_executable) == 'grasp_lift_executor':
        removed += 1
    else:
        entities.append(entity)
assert removed == 1
print('CALIBRATION: original launch, no grasp executor; stop_after_observe set/read before start', flush=True)
service = LaunchService()
service.include_launch_description(LaunchDescription(entities))
raise SystemExit(service.run())
