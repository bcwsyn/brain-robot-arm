#!/usr/bin/env bash
set -Eeuo pipefail
CUP_GRASP_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CUP_GRASP_WS"
if [[ -n "${CONDA_PREFIX:-}" || ! -f install/setup.bash || ! -x .venv-yolo/bin/python ]]; then
    echo '请退出 Conda，并先构建仿真及配置视觉环境 / Build simulation and set up the private vision environment first.' >&2
    exit 1
fi
export PYTHONNOUSERSITE=1
set +u
source /opt/ros/humble/setup.bash
source "$CUP_GRASP_WS/install/setup.bash"
set -u
export ROS_DOMAIN_ID=85
export ROS_LOCALHOST_ONLY=1
export GAZEBO_MASTER_URI=http://127.0.0.1:11485
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$CUP_GRASP_WS/validation/fastdds_local_udp.xml"
export RMW_FASTRTPS_PUBLICATION_MODE=ASYNCHRONOUS
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
exec /usr/bin/python3 -s "$CUP_GRASP_WS/scripts/cup_grasp_console.py" "$@"
