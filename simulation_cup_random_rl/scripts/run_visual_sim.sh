#!/usr/bin/env bash
set -Eeuo pipefail
SIM_VISUAL_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f /opt/ros/humble/setup.bash || ! -f "$SIM_VISUAL_WS/install/setup.bash" ]]; then
    echo "[错误] 尚未找到 Humble 或 simulation/install/setup.bash，请先完成仿真工作区构建。" >&2
    exit 1
fi
if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo "[错误] 请先 conda deactivate，再启动本程序。" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1
set +u
source /opt/ros/humble/setup.bash
source "$SIM_VISUAL_WS/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 -s "$SIM_VISUAL_WS/scripts/check_sim_environment.py" --runtime
export ROS_DOMAIN_ID=83
export ROS_LOCALHOST_ONLY=1
export GAZEBO_MASTER_URI=http://127.0.0.1:11483
export FASTRTPS_DEFAULT_PROFILES_FILE="$SIM_VISUAL_WS/validation/fastdds_local_udp.xml"
export RMW_FASTRTPS_PUBLICATION_MODE=ASYNCHRONOUS
exec /usr/bin/python3 -s "$SIM_VISUAL_WS/scripts/visual_sim_console.py" "$@"
