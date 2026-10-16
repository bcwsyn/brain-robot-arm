"""Select unchanged original model/MoveIt/adapter nodes, no autonomous task."""
import importlib.util
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription,LaunchService,LaunchContext
from launch_ros.actions import Node
from launch.utilities import perform_substitutions
p=Path(get_package_share_directory('brain_robot_ball_pick'))/'launch/cube_visual_search.launch.py'
spec=importlib.util.spec_from_file_location('original_board_launch',p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=module.generate_launch_description();selected=[];executables=[]
allowed={'robot_state_publisher','static_transform_publisher','move_group','piper_jog_adapter.py'}
for entity in original.entities:
    if isinstance(entity,Node):
        name=entity.node_executable
        if not isinstance(name,str):name=perform_substitutions(LaunchContext(),name)
        if name in allowed:selected.append(entity);executables.append(name)
    else:selected.append(entity)
assert executables.count('piper_jog_adapter.py')==executables.count('move_group')==1
print('Original unchanged sampling nodes:',executables,flush=True)
service=LaunchService();service.include_launch_description(LaunchDescription(selected))
raise SystemExit(service.run())
