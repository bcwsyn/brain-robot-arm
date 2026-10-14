#!/usr/bin/env bash
# Red-ball simulation only.  It never opens CAN, Gemini2, or a physical PiPER driver.
set -Eeuo pipefail

SIMULATION_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

ROS_SETUP=/opt/ros/humble/setup.bash
PIPER_WS="$SIMULATION_WS"
APP_WS="$SIMULATION_WS"
SIM_SCRIPT="$SIMULATION_WS/scripts/start_piper_sim.sh"
WAIT_SECONDS="${BRAIN_ROBOT_WAIT_SECONDS:-90}"
PIDS=()

fail() { echo "[错误] $*" >&2; exit 1; }
cleanup() {
  trap - EXIT INT TERM
  echo; echo "[关闭] 正在停止红球场景、视觉控制和仿真..."
  for pid in "${PIDS[@]:-}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  sleep 2
  for pid in "${PIDS[@]:-}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  echo "[完成] 红球演示已关闭。"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ -z "${CONDA_PREFIX:-}" ]] || fail "请先执行 conda deactivate。"
[[ -f "$ROS_SETUP" && -f "$PIPER_WS/install/setup.bash" && -f "$APP_WS/install/setup.bash" ]] ||
  fail "ROS2、PiPER 或应用工作空间尚未就绪。"
[[ -x "$SIM_SCRIPT" ]] || fail "未找到当前仿真工作区启动脚本。"
set +u
source "$ROS_SETUP"
source "$PIPER_WS/install/setup.bash"
source "$APP_WS/install/setup.bash"
set -u
ros2 pkg executables brain_robot_ball_pick | grep -F 'ball_scene_manager_node.py' >/dev/null ||
  fail "未安装红球工程，请先在 simulation/ 中完成依赖审查与构建。"

wait_for() {
  local kind="$1" name="$2" deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    timeout 5s ros2 "$kind" list 2>/dev/null | grep -Fxq "$name" && return 0
    sleep 1
  done
  fail "等待 $name 超时。"
}
wait_scene() {
  local deadline=$((SECONDS + WAIT_SECONDS)) output
  while (( SECONDS < deadline )); do
    output="$(timeout 5s ros2 topic echo --once /brain_robot_ball_pick/scene_ready 2>/dev/null || true)"
    grep -Fq 'data: true' <<<"$output" && return 0
    sleep 1
  done
  fail "等待红球场景就绪超时。"
}
start_group() { setsid "$@" & PIDS+=("$!"); }

echo "=================================================="
echo " PiPER 红色小球视觉抓取仿真"
echo " 仅仿真：不会连接实体 PiPER、Gemini2 或头环"
echo "=================================================="
echo "[1/5] 启动 Gazebo、PiPER、MoveIt2 和 RViz2..."
start_group bash "$SIM_SCRIPT"
wait_for node /move_group
wait_for topic /wrist_camera/wrist_camera/image_raw
echo "[2/5] 加载桌面和红色小球..."
start_group ros2 launch brain_robot_ball_pick ball_scene.launch.py
wait_scene
echo "[3/5] 启动红色小球 RGB-D 检测..."
start_group ros2 launch brain_robot_ball_pick ball_detector.launch.py
wait_for topic /brain_robot_vision/debug_image
echo "[4/5] 启动 MoveIt Servo 和直接点位抓取控制..."
start_group ros2 launch brain_robot_ball_pick ball_visual_search.launch.py
wait_for service /visual_search_controller/start
echo "[5/5] 打开红色小球识别窗口..."
start_group ros2 run image_view image_view --ros-args -r image:=/brain_robot_vision/debug_image
echo
echo "已就绪：按 s 开始‘搜球 -> 视觉居中 -> 点位抓取 -> 抬升’；按 x 停止；按一次 Ctrl+C 全部关闭。"
while true; do
  if [[ -t 0 ]] && read -r -s -n 1 -t 1 key; then
    case "$key" in
      s|S) timeout 12s ros2 service call /visual_search_controller/start std_srvs/srv/Trigger '{}' || true ;;
      x|X) timeout 8s ros2 service call /visual_search_controller/stop std_srvs/srv/Trigger '{}' || true ;;
    esac
  fi
done
