#!/usr/bin/env bash
# Starts the installed, read-only ROS2 runtime monitor in a second terminal.
set -Eeuo pipefail

SIMULATION_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
PIPER_SETUP="$SIMULATION_WS/install/setup.bash"
APP_SETUP="$SIMULATION_WS/install/setup.bash"

for required in "$ROS_SETUP" "$PIPER_SETUP" "$APP_SETUP"; do
    [[ -f "$required" ]] || {
        echo "[错误] 缺少 ROS2/PiPER/项目环境文件：$required" >&2
        exit 1
    }
done

set +u
source "$ROS_SETUP"
source "$PIPER_SETUP"
source "$APP_SETUP"
set -u

echo "=================================================="
echo " PiPER 脑控机械臂只读运行监控"
echo " 不发布关节命令，不调用开始/停止服务，不修改参数"
echo " 按 Ctrl+C 仅退出本监控终端"
echo "=================================================="
echo "当前门槛（来自 /visual_search_controller 参数）："
for parameter in target_acquire_frames align_stable_frames target_acquire_error_ratio \
    target_timeout_s joint_state_timeout_s; do
    ros2 param get /visual_search_controller "$parameter" 2>/dev/null || true
done
echo
exec ros2 run brain_robot_pick_place runtime_monitor.py
