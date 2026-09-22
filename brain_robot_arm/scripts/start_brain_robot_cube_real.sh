#!/usr/bin/env bash
# Protected real-arm purple-cube visual search.
set -Eeuo pipefail

ROS_SETUP=/opt/ros/humble/setup.bash
PIPER_WS="${PIPER_ROS_WS:-$HOME/piper_ros}"
APP_WS="${BRAIN_ROBOT_WS:-$HOME/piper_ws}"
CAMERA_WS="${BRAIN_ROBOT_CAMERA_WS:-$HOME/ros2_ws}"
LOG_DIR="${BRAIN_ROBOT_LOG_DIR:-$HOME/brain_robot_logs}"
LOG_MAX_MB="${BRAIN_ROBOT_LOG_MAX_MB:-20}"
LOG_TOTAL_MAX_MB="${BRAIN_ROBOT_LOG_TOTAL_MAX_MB:-100}"
MIN_FREE_MB="${BRAIN_ROBOT_MIN_FREE_MB:-2048}"
WAIT_SECONDS="${BRAIN_ROBOT_WAIT_SECONDS:-45}"
PIDS=()
LOG_GUARD_PID=""
CAMERA_HEALTH_PID=""
DISABLE_REQUESTED=0
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

fail() { echo "[错误] $*" >&2; exit 1; }
cleanup() {
  trap - EXIT INT TERM
  if (( DISABLE_REQUESTED )); then
    echo; echo "[关闭] Ctrl+C 已请求，关闭实体运动门并失能 PiPER..."
    timeout 5s ros2 service call /visual_search_controller/stop std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
    timeout 5s ros2 service call /piper_jog_adapter/disarm std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
    timeout 5s ros2 service call /piper_jog_adapter/disable_motion std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
    timeout 8s ros2 service call /enable_srv piper_msgs/srv/Enable \
      '{enable_request: false}' >/dev/null 2>&1 || true
  else
    echo; echo "[保持] 未收到 Ctrl+C；不发送 PiPER 失能命令。"
  fi
  echo "[关闭] 停止本脚本启动的视觉、相机和驱动进程..."
  if [[ -n "$CAMERA_HEALTH_PID" ]]; then
    kill "$CAMERA_HEALTH_PID" 2>/dev/null || true
  fi
  stop_astra_camera || true
  for pid in "${PIDS[@]:-}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  sleep 1
  for pid in "${PIDS[@]:-}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  if [[ -n "$LOG_GUARD_PID" ]]; then
    kill "$LOG_GUARD_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  echo "[完成] 一键流程已停止。"
}
trap cleanup EXIT
trap 'DISABLE_REQUESTED=1; exit 130' INT
trap 'exit 143' TERM
if [[ -n "${CONDA_PREFIX:-}" ]] && command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  while [[ -n "${CONDA_PREFIX:-}" ]]; do conda deactivate; done
fi
[[ -f "$ROS_SETUP" && -f "$PIPER_WS/install/setup.bash" && -f "$APP_WS/install/setup.bash" ]] ||
  fail "ROS2、PiPER 或应用工作空间尚未就绪。"
set +u
source "$ROS_SETUP"
source "$PIPER_WS/install/setup.bash"
source "$APP_WS/install/setup.bash"
if [[ -f "$CAMERA_WS/install/setup.bash" ]]; then
  source "$CAMERA_WS/install/setup.bash"
fi
set -u

wait_for() {
  local kind="$1" name="$2" deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    timeout 5s ros2 "$kind" list 2>/dev/null | grep -Fxq "$name" && return 0
    sleep 1
  done
  fail "等待 $name 超时。"
}

wait_for_tf_validated_pointcloud() {
  local deadline=$((SECONDS + WAIT_SECONDS)) result
  while (( SECONDS < deadline )); do
    result=$(timeout 3s ros2 topic echo --once \
      --qos-reliability reliable \
      --qos-durability transient_local \
      /brain_robot_vision/tf_gate_diagnostic 2>&1) || result=""
    if grep -Fq 'state=FORWARDED' <<<"$result"; then
      return 0
    fi
    sleep 1
  done
  fail "未收到具有完整同时间戳机器人 TF 的深度点云；未建立 Octomap。请查看 /brain_robot_vision/tf_gate_diagnostic。"
}

wait_for_filtered_pointcloud() {
  local deadline=$((SECONDS + WAIT_SECONDS)) result
  while (( SECONDS < deadline )); do
    result=$(timeout 5s ros2 topic echo --once \
      /brain_robot_vision/filtered_points \
      --qos-reliability best_effort 2>&1) || result=""
    if grep -Fq 'header:' <<<"$result"; then
      return 0
    fi
    sleep 1
  done
  fail "未收到 MoveIt 自体过滤后的点云；拒绝开始使用可能含有机械臂自体点的 Octomap。"
}

trim_application_logs() {
  find "$LOG_DIR" -type f -name '*.log' -mtime +3 -delete 2>/dev/null || true
  find "$LOG_DIR" -type f \( -name '*.log' -o -name '*.log.*' \) \
    -size +"${LOG_MAX_MB}M" -exec truncate -s 0 {} \; 2>/dev/null || true
  local total_kb
  total_kb=$(du -sk "$LOG_DIR" 2>/dev/null | awk '{print $1}')
  while [[ "${total_kb:-0}" -gt $((LOG_TOTAL_MAX_MB * 1024)) ]]; do
    local oldest
    # Do not use `head` here: with pipefail enabled it can make `sort` fail
    # with SIGPIPE after the first record has been consumed, which would abort
    # this whole startup script under `set -e`.
    oldest=$(find "$LOG_DIR" -type f -name '*.log*' -printf '%T@ %p\n' 2>/dev/null |
      sort -n | sed -n '1{s/^[^ ]* //;p;}')
    [[ -n "$oldest" ]] || break
    # Do not unlink a process' current log: an unlinked-but-open file still
    # occupies disk space. Truncation preserves the inode and releases space.
    truncate -s 0 -- "$oldest" 2>/dev/null || break
    total_kb=$(du -sk "$LOG_DIR" 2>/dev/null | awk '{print $1}')
  done
}

prepare_logs() {
  mkdir -p "$LOG_DIR"
  export ROS_LOG_DIR="$LOG_DIR/ros"
  mkdir -p "$ROS_LOG_DIR"
  # Keep startup logs useful without allowing repeated ROS output to consume
  # the VM disk.  The cleanup utility performs the same maintenance on demand.
  trim_application_logs
}

start_log_guard() {
  (
    while true; do
      trim_application_logs
      # System logs are maintained only by the fixed no-argument helper
      # installed by install_brain_robot_log_maintenance.sh.
      if [[ -x /usr/local/sbin/brain-robot-log-maintenance ]]; then
        sudo -n /usr/local/sbin/brain-robot-log-maintenance >/dev/null 2>&1 || true
      fi
      sleep 30
    done
  ) &
  LOG_GUARD_PID="$!"
}

available_root_mb() {
  df --output=avail -BM / | tail -n 1 | tr -dc '0-9'
}

check_disk_headroom() {
  local available_mb usage
  available_mb=$(available_root_mb)
  usage=$(df --output=pcent / | tail -n 1 | tr -dc '0-9')
  if (( available_mb < MIN_FREE_MB )); then
    echo "[错误] 根分区仅剩 ${available_mb} MB（使用率 ${usage}%）；至少需要 ${MIN_FREE_MB} MB 才启动。"
    echo "[提示] 先运行 ~/clean_disk_space.sh；如提示系统日志未清理，首次运行 ~/install_brain_robot_log_maintenance.sh。"
    exit 1
  fi
  echo "[磁盘] 根分区可用 ${available_mb} MB（使用率 ${usage}%）。"
}

start_group() {
  local tag="$1"
  shift
  local logfile="$LOG_DIR/${tag}.log"
  : > "$logfile"
  setsid "$@" >"$logfile" 2>&1 &
  PIDS+=("$!")
  echo "[后台] ${tag} 日志：${logfile}"
}

astra_process_exists() {
  pgrep -f 'ros2 launch astra_camera astra\.launch\.py' >/dev/null 2>&1 ||
    pgrep -f 'component_container.*__node:=astra_camera_container' >/dev/null 2>&1
}

stop_astra_camera() {
  local pid pgid attempt
  pid=$(pgrep -fo 'ros2 launch astra_camera astra\.launch\.py' 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
    # Only signal a process group when Astra was launched in its own session.
    # Otherwise, terminating the group could also terminate a user shell.
    if [[ "$pgid" == "$pid" ]]; then
      kill -TERM -- "-$pgid" 2>/dev/null || true
    else
      kill -TERM "$pid" 2>/dev/null || true
    fi
  fi
  pkill -TERM -f 'component_container.*__node:=astra_camera_container' \
    2>/dev/null || true
  for attempt in {1..10}; do
    astra_process_exists || return 0
    sleep 1
  done
  pkill -KILL -f 'ros2 launch astra_camera astra\.launch\.py' 2>/dev/null || true
  pkill -KILL -f 'component_container.*__node:=astra_camera_container' \
    2>/dev/null || true
}

start_astra_camera() {
  start_group astra_camera ros2 launch astra_camera astra.launch.py
}

camera_has_rgb_frame() {
  # A Publisher can exist before Orbbec SDK has opened the USB device.  A
  # successful one-shot subscription proves that an actual RGB frame arrived.
  timeout 4s ros2 topic echo --once /camera/color/image_raw >/dev/null 2>&1
}

wait_for_actual_frame() {
  local topic="$1" label="$2" next_report=$((SECONDS + 10))
  echo "[等待] 等待 ${label} 首帧；收到真实图像后才继续启动..."
  while true; do
    if timeout 4s ros2 topic echo --once "$topic" >/dev/null 2>&1; then
      echo "[就绪] 已收到 ${label} 首帧。"
      return 0
    fi
    if (( SECONDS >= next_report )); then
      echo "[等待] ${label} 尚未收到首帧；相机自动恢复仍在运行。"
      next_report=$((SECONDS + 10))
    fi
    sleep 1
  done
}

start_camera_health_guard() {
  local logfile="$LOG_DIR/camera_health.log"
  : > "$logfile"
  (
    local missing_frames=0 restart_backoff_s=3
    while true; do
      if camera_has_rgb_frame; then
        if (( restart_backoff_s > 3 )); then
          echo "[$(date '+%F %T')] CAMERA_FRAMES_RECOVERED"
        fi
        missing_frames=0
        restart_backoff_s=3
        sleep 5
        continue
      fi

      ((missing_frames += 1))
      if (( missing_frames < 2 )); then
        sleep 5
        continue
      fi

      echo "[$(date '+%F %T')] CAMERA_NO_FRAMES: restarting Astra after ${restart_backoff_s}s"
      stop_astra_camera
      sleep "$restart_backoff_s"
      start_astra_camera
      missing_frames=0
      restart_backoff_s=$((restart_backoff_s * 2))
      if (( restart_backoff_s > 30 )); then
        restart_backoff_s=30
      fi
      sleep 5
    done
  ) >>"$logfile" 2>&1 &
  CAMERA_HEALTH_PID="$!"
  echo "[相机] 已启用无帧自动恢复；仅重启 Astra，不影响机械臂控制栈。"
}

configure_can() {
  command -v ip >/dev/null 2>&1 || fail "未找到 ip 命令。"
  ip link show can0 >/dev/null 2>&1 || fail "未找到 can0；请确认 USB-CAN 已连接。"
  echo "[CAN] 重载 gs_usb 并配置 can0 为 1 Mbps..."
  sudo ip link set can0 down 2>/dev/null || true
  sudo modprobe -r gs_usb 2>/dev/null || true
  sudo modprobe gs_usb || fail "无法加载 gs_usb 驱动。"
  sleep 1
  sudo ip link set can0 down 2>/dev/null || true
  sudo ip link set can0 type can bitrate 1000000 2>/dev/null ||
    fail "无法配置 can0；请检查 USB-CAN 连接。"
  sudo ip link set can0 up || fail "无法启动 can0。"
  ip -details link show can0 | grep -E 'state (UP|UNKNOWN)|bitrate 1000000' >/dev/null ||
    fail "can0 未处于 1 Mbps 工作状态。"
}

node_exists() {
  timeout 5s ros2 node list 2>/dev/null | grep -Fxq "$1"
}

visual_stack_processes_exist() {
  # Use process identities rather than `ros2 node list`: DDS discovery can
  # retain nodes from a just-terminated launch for longer than this script's
  # startup window. Match executable paths, not service-client arguments.
  pgrep -f \
    'ros2 launch brain_robot_ball_pick cube_visual_search\.launch\.py|/brain_robot_pick_place/(piper_jog_adapter\.py|visual_search_controller|grasp_lift_executor|active_scan_supervisor)([[:space:]]|$)|/moveit_servo/servo_node_main([[:space:]]|$)|/moveit_ros_move_group/move_group([[:space:]]|$)' \
    >/dev/null 2>&1
}

stop_stale_visual_stack() {
  if ! visual_stack_processes_exist; then
    return 0
  fi

  echo "[清理] 检测到上一轮遗留的 MoveIt/Servo/视觉控制栈，正在停止..."
  timeout 5s ros2 service call /visual_search_controller/stop \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  timeout 5s ros2 service call /servo_node/stop_servo \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true

  # A terminated ros2 launch normally stops every child. The following
  # process-specific fallbacks handle a launch parent that was interrupted
  # before it could forward SIGINT to its children.
  pkill -TERM -f 'ros2 launch brain_robot_ball_pick cube_visual_search.launch.py' \
    2>/dev/null || true
  sleep 2
  if visual_stack_processes_exist; then
    pkill -TERM -f '/brain_robot_pick_place/(piper_jog_adapter.py|visual_search_controller|grasp_lift_executor|active_scan_supervisor)' \
      2>/dev/null || true
    pkill -TERM -f '/moveit_servo/servo_node_main' 2>/dev/null || true
    pkill -TERM -f '/moveit_ros_move_group/move_group' 2>/dev/null || true
  fi

  local deadline=$((SECONDS + 15))
  while (( SECONDS < deadline )); do
    if ! visual_stack_processes_exist; then
      echo "[清理] 旧控制栈已退出。"
      return 0
    fi
    sleep 1
  done
  fail "旧 MoveIt/Servo/视觉控制栈未完全退出；拒绝启动第二套控制器。"
}

topic_exists() {
  timeout 5s ros2 topic list 2>/dev/null | grep -Fxq "$1"
}

enable_physical_motion() {
  local result
  result=$(timeout 8s ros2 service call /enable_srv piper_msgs/srv/Enable \
    '{enable_request: true}' 2>&1) || result=""
  if ! grep -Eq 'enable_response=True' <<<"$result"; then
    # The arm may already be physically enabled.  The driver can return
    # false for a repeated enable request; that must not prevent key 1 from
    # attempting the reset path.
    echo "[警告] PiPER 重复使能未返回 True；继续尝试运动门和适配器。"
  fi
  local attempt
  for attempt in 1 2 3; do
    result=$(timeout 5s ros2 service call /piper_jog_adapter/enable_motion \
      std_srvs/srv/Trigger '{}' 2>&1) || result=""
    if grep -Eq 'success=True' <<<"$result"; then
      result=$(timeout 5s ros2 service call /piper_jog_adapter/arm \
        std_srvs/srv/Trigger '{}' 2>&1) || result=""
      if grep -Eq 'success=True' <<<"$result"; then
        return 0
      fi
    fi
    echo "[重试] 运动门/适配器 arm 第 ${attempt}/3 次未完成。"
    sleep 1
  done
  echo "[错误] 运动门和适配器 arm 均未成功；未发送复位轨迹。"
  return 1
}

start_visual_sequence() {
  echo "[启动] 从零点移动到观测姿态..."
  local result
  result=$(timeout 8s ros2 service call /visual_search_controller/start \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  if ! grep -Eq 'success=True' <<<"$result"; then
    echo "[错误] 视觉复位/搜索启动失败。"
    return 1
  fi
  echo "[启动] 已开始观测姿态复位；完成后自动进入紫色方块搜索。"
}

wait_for_zero_reset() {
  local deadline=$((SECONDS + 120)) result
  while (( SECONDS < deadline )); do
    result=$(timeout 3s ros2 topic echo --once \
      --qos-reliability reliable \
      --qos-durability transient_local \
      /brain_robot_visual_control/reason 2>&1) || result=""
    if grep -Fq 'RESET_COMPLETE' <<<"$result"; then
      echo "[复位] 六轴已到达软件零点。"
      return 0
    fi
    sleep 1
  done
  echo "[复位] 等待六轴零点反馈超时，未进入后续流程。"
  return 1
}

request_zero_reset() {
  local result
  result=$(timeout 8s ros2 service call /visual_search_controller/reset \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  echo "$result"
  if ! grep -Eq 'success=True' <<<"$result"; then
    echo "[复位] 零点复位请求失败。"
    return 1
  fi
  wait_for_zero_reset
}

restart_visual_sequence() {
  echo "[重启] 停止当前视觉流程，先执行六轴零点复位..."
  timeout 5s ros2 service call /visual_search_controller/stop \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  timeout 5s ros2 service call /servo_node/stop_servo \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  enable_physical_motion || return 1
  request_zero_reset || return 1
  start_visual_sequence
}

execute_grasp_sequence() {
  echo "[抓取] 请求抓取；当前状态必须为 GRASP_READY..."
  local result
  result=$(timeout 10s ros2 service call /grasp_lift_executor/execute \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  echo "$result"
  if ! grep -Eq 'success=True' <<<"$result"; then
    if grep -Fq 'already running' <<<"$result"; then
      echo "[抓取] 抓取序列已在运行；保持当前使能和当前流程。"
      return 0
    fi
    echo "[抓取] 未启动：请确认视觉状态已经进入 GRASP_READY。"
    return 1
  fi
}

stop_motion_hold_enabled() {
  echo "[停止] 停止视觉和 Servo，保持 PiPER 使能与当前位置..."
  timeout 5s ros2 service call /visual_search_controller/stop \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  timeout 5s ros2 service call /servo_node/stop_servo \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
}

reset_zero_sequence() {
  echo "[复位] 停止当前视觉运动，立即开始六轴零点复位..."
  timeout 5s ros2 service call /visual_search_controller/stop \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  timeout 5s ros2 service call /servo_node/stop_servo \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  enable_physical_motion || return 1
  request_zero_reset
}

echo "=================================================="
echo " PiPER 实体紫色方块视觉抓取（一键保护模式）"
echo " 自动启动 CAN、PiPER 驱动、相机、MoveIt、Servo 和检测器"
echo "=================================================="
prepare_logs
bash "$SCRIPT_DIR/clean_disk_space.sh" || true
check_disk_headroom
start_log_guard
echo "[1/7] 检查并初始化实体 CAN/机械臂..."
configure_can
if ! node_exists /piper_ctrl_single_node; then
  start_group piper_driver ros2 run piper piper_single_ctrl \
    --ros-args \
    --log-level WARN \
    -p can_port:=can0 \
    -p auto_enable:=false \
    -p gripper_exist:=true \
    -r joint_states_single:=/joint_states \
    -r joint_ctrl_single:=/joint_commands
else
  echo "[复用] 已检测到 /piper_ctrl_single_node"
fi
wait_for topic /joint_states
wait_for service /enable_srv

echo "[2/7] 检查并启动 RGB-D 相机..."
if ! node_exists /camera/camera; then
  start_astra_camera
else
  echo "[复用] 已检测到 /camera/camera"
fi
wait_for topic /camera/color/image_raw
wait_for topic /camera/depth/image_raw
start_camera_health_guard
wait_for_actual_frame /camera/color/image_raw "RGB 图像"

echo "[3/7] 启动紫色方块 RGB-D 检测..."
start_group cube_detector ros2 launch brain_robot_ball_pick cube_detector.launch.py
wait_for topic /brain_robot_vision/debug_image

echo "[4/7] 启动 MoveIt、Servo 和真机保护适配器..."
stop_stale_visual_stack
start_group visual_stack ros2 launch brain_robot_ball_pick cube_visual_search.launch.py
wait_for node /move_group
wait_for node /servo_node
wait_for node /piper_jog_adapter
wait_for node /grasp_lift_executor
wait_for node /pointcloud_tf_gate
wait_for service /piper_jog_adapter/arm
wait_for service /visual_search_controller/reset
wait_for service /grasp_lift_executor/execute

echo "[5/7] 检查完整 MoveIt 反馈和自体过滤 TF..."
wait_for topic /piper_moveit_joint_states
wait_for topic /brain_robot_vision/tf_gate_diagnostic
wait_for_tf_validated_pointcloud
wait_for_filtered_pointcloud
wait_for service /clear_octomap
timeout 5s ros2 service call /clear_octomap std_srvs/srv/Empty '{}' >/dev/null 2>&1 ||
  fail "无法清除旧 Octomap；拒绝使用可能含有机械臂自体点的地图。"
echo "[地图] 已验证同时间戳 TF，并清除旧 Octomap；开始建立当前环境地图。"
echo "[6/7] 打开识别窗口..."
start_group debug_image_view ros2 run image_view image_view --ros-args -r image:=/brain_robot_vision/debug_image
wait_for_actual_frame /brain_robot_vision/debug_image "调试图像"
echo "[7/7] 全部组件已就绪。"
echo
echo "操作：按 1 从六轴零点开始搜索/对齐；2=GRASP_READY 后抓取；0=仅零点复位；Ctrl+C=失能并退出。"
while true; do
  if [[ -t 0 ]] && read -r -s -n 1 -t 1 key; then
    case "$key" in
      1)
        if ! restart_visual_sequence; then
          echo "[保持] 搜索启动失败；PiPER 保持当前使能状态。"
        fi
        ;;
      2)
        if ! execute_grasp_sequence; then
          echo "[保持] 抓取请求未被接受；PiPER 保持当前使能状态。"
        fi
        ;;
      0)
        if ! reset_zero_sequence; then
          echo "[保持] 零点复位请求失败；PiPER 保持当前使能状态。"
        fi
        ;;
    esac
  fi
done
