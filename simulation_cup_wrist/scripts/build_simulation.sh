#!/usr/bin/env bash
# Build only the independent seven-package simulation workspace.
set -Eeuo pipefail
SIM_BUILD_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo 'Deactivate Conda and use a fresh Ubuntu terminal.' >&2
    exit 1
fi
if [[ ! -f /opt/ros/humble/setup.bash ]]; then
    echo 'ROS 2 Humble is missing. Follow docs/simulation/README.en.md or README.zh-CN.md.' >&2
    exit 1
fi
# Keep another ROS overlay out of the build; retain the user's normal PATH.
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
export PYTHONNOUSERSITE=1
set +u
source /opt/ros/humble/setup.bash
set -u
cd "$SIM_BUILD_WS"
/usr/bin/python3 -s scripts/check_sim_environment.py
export MAKEFLAGS=-j2
export CMAKE_BUILD_PARALLEL_LEVEL=2
colcon build --symlink-install --executor sequential \
    --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
echo 'Build complete. Start scripts/run_cup_grasp_sim.sh, run_ball_physics_sim.sh or run_cylinder_physics_sim.sh.'
