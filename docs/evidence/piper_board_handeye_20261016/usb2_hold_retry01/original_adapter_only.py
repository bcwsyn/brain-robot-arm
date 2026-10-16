"""Select the unchanged installed adapter Node; no autonomous controllers."""
import importlib.util
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription, LaunchService, LaunchContext
from launch_ros.actions import Node
from launch.utilities import perform_substitutions

p = Path(get_package_share_directory('brain_robot_ball_pick')) / 'launch/cube_visual_search.launch.py'
spec = importlib.util.spec_from_file_location('original_hold_launch', p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
selected = []
for entity in module.generate_launch_description().entities:
    if isinstance(entity, Node):
        executable = entity.node_executable
        if not isinstance(executable, str):
            executable = perform_substitutions(LaunchContext(), executable)
        if executable == 'piper_jog_adapter.py':
            selected.append(entity)
assert len(selected) == 1
print('Original installed adapter Node and parameters only; no Servo/task/MoveIt/camera', flush=True)
service = LaunchService()
service.include_launch_description(LaunchDescription(selected))
raise SystemExit(service.run())
