"""Known scene geometry mode: launch then call /grasp_lift_executor/execute."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    share = Path(get_package_share_directory('brain_robot_pick_place'))
    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=str(share / "config" / "known_task_sim.yaml")),
        IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(share / 'launch' / 'visual_search.launch.py')),
        launch_arguments={'params_file': LaunchConfiguration('params_file')}.items())])
