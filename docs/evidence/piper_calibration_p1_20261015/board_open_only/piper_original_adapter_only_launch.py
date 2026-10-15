"""Select only the unchanged adapter Node from the actual installed launch."""
import importlib.util
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext,LaunchDescription,LaunchService
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
path=Path(get_package_share_directory('brain_robot_ball_pick'))/'launch/cube_visual_search.launch.py'
spec=importlib.util.spec_from_file_location('original_visual_launch',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
selected=[]
for entity in module.generate_launch_description().entities:
    executable=entity.node_executable if isinstance(entity,Node) else None
    if executable is not None and not isinstance(executable,str):
        executable=perform_substitutions(LaunchContext(),executable)
    if executable=='piper_jog_adapter.py':selected.append(entity)
assert len(selected)==1
print('Original adapter Node only; all original parameters unchanged. No controller/MoveIt/Servo/grasp nodes.',flush=True)
service=LaunchService();service.include_launch_description(LaunchDescription(selected))
raise SystemExit(service.run())
