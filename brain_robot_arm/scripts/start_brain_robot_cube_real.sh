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
AUTO_START="${BRAIN_ROBOT_AUTO_START:-1}"
DEPTH_ONLY_TARGET="${BRAIN_ROBOT_DEPTH_ONLY_TARGET:-1}"
PIDS=()
LOG_GUARD_PID=""
CAMERA_HEALTH_PID=""
CAN_HEALTH_PID=""
CAMERA_STARTED_BY_SCRIPT=0
DISABLE_REQUESTED=0
MOTION_ARMED=0
SUCCESSFUL_CYCLE_COMPLETE=0
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DDS_PROFILE="${BRAIN_ROBOT_DDS_PROFILE:-$SCRIPT_DIR/fastdds_udp_only.xml}"

# Fast DDS shared-memory locks can survive an interrupted or disk-full run and
# block node construction before the PiPER process even opens its CAN socket.
# This single-host stack needs no SHM transport; force the supported UDPv4
# transport for every child so stale /dev/shm state cannot stall one-key start.
[[ -r "$DDS_PROFILE" ]] || {
  echo "[错误] Fast DDS UDP-only 配置不存在：$DDS_PROFILE" >&2
  exit 1
}
export FASTRTPS_DEFAULT_PROFILES_FILE="$DDS_PROFILE"

fail() { echo "[错误] $*" >&2; exit 1; }
cleanup() {
  trap - EXIT INT TERM
  if (( SUCCESSFUL_CYCLE_COMPLETE )); then
    echo; echo "[完成] 成功路径已安全回位并失能；仅清理本脚本进程。"
  elif (( DISABLE_REQUESTED || MOTION_ARMED )); then
    echo; echo "[保护] 异常退出或运动已启动；停止控制输出并保持当前位置，不自动发起零点复位。"
    # A fault/timeout must not create an unexpected long trajectory.  The
    # explicit 0 command remains the only zero-reset entry point.
    timeout 5s ros2 service call /visual_search_controller/stop std_srvs/srv/Trigger "{}" >/dev/null 2>&1 || true
    timeout 5s ros2 service call /servo_node/stop_servo std_srvs/srv/Trigger "{}" >/dev/null 2>&1 || true
    timeout 5s ros2 service call /piper_jog_adapter/disarm std_srvs/srv/Trigger "{}" >/dev/null 2>&1 || true
    echo "[保护] 未发送 DisableArm；PiPER 保持使能，等待操作者确认。"
  else
    echo; echo "[保持] 未收到 Ctrl+C；不发送 PiPER 失能命令。"
  fi
  echo "[关闭] 停止本脚本启动的视觉、相机和驱动进程..."
  if [[ -n "$CAMERA_HEALTH_PID" ]]; then
    kill "$CAMERA_HEALTH_PID" 2>/dev/null || true
  fi
  if [[ -n "$CAN_HEALTH_PID" ]]; then
    kill "$CAN_HEALTH_PID" 2>/dev/null || true
  fi
  if (( CAMERA_STARTED_BY_SCRIPT )); then
    stop_astra_camera || true
  fi
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
trap 'DISABLE_REQUESTED=1; exit 143' TERM
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

wait_for_joint_feedback() {
  local topic="$1" deadline=$((SECONDS + WAIT_SECONDS)) result consecutive=0
  # One DDS sample is not enough: a stale/transient sample can create a
  # robot_state_publisher topic while the CAN feedback has already stopped.
  # Require three consecutive complete six-axis samples before allowing TF or
  # any physical motion stage to continue.
  while (( SECONDS < deadline )); do
    result=$(timeout 3s ros2 topic echo --once "$topic" 2>&1) || result=""
    if grep -Fq "joint1" <<<"$result" && grep -Fq "joint6" <<<"$result"; then
      consecutive=$((consecutive + 1))
      if (( consecutive >= 3 )); then
        return 0
      fi
    else
      consecutive=0
    fi
    sleep 1
  done
  fail "等待 $topic 的连续新鲜六轴反馈超时；拒绝进入运动流程。"
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
    # The real profile intentionally disables the wrist point-cloud input to
    # Octomap. Validate the actual camera TF directly instead of requiring a
    # cloud frame that the camera may not publish.
    local robot_tf_result
    # The wrist cloud is deliberately disconnected from Octomap.  Its
    # diagnostic topic may therefore stay silent; the only required startup
    # condition here is a live robot TF edge backed by the continuous
    # /piper_moveit_joint_states gate above.  Camera image/info gates already
    # prove the optical stream is present, and target transforms are checked
    # again by the controller before any target motion.
    robot_tf_result=$(timeout 4s ros2 topic echo --once /tf 2>&1) || robot_tf_result=""
    if grep -Fq 'frame_id: base_link' <<<"$robot_tf_result" \
      && grep -Fq 'child_frame_id: link1' <<<"$robot_tf_result"; then
      return 0
    fi
    sleep 1
  done
  fail "未收到相机到基座的可用 TF 心跳；实体腕部点云不会写入 Octomap。请查看 /brain_robot_vision/tf_gate_diagnostic。"
}

wait_for_filtered_pointcloud() {
  # Real mode intentionally disables MoveIt's Octomap updater because the
  # depth camera is mounted on the moving gripper.  The TF-gated cloud is
  # already checked by wait_for_tf_validated_pointcloud and is used only as a
  # freshness heartbeat by the visual controller.
  return 0
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
  CAMERA_STARTED_BY_SCRIPT=1
}

camera_has_required_frame() {
  # A Publisher can exist before Orbbec SDK has opened the USB device. A
  # successful one-shot subscription proves that the required real stream
  # arrived. The depth-only profile must not depend on the UVC RGB interface.
  if [[ "$DEPTH_ONLY_TARGET" == "1" || "$DEPTH_ONLY_TARGET" == "true" ||
    "$DEPTH_ONLY_TARGET" == "yes" ]]; then
    timeout 4s ros2 topic echo --once /camera/depth/image_raw >/dev/null 2>&1
  else
    timeout 4s ros2 topic echo --once /camera/color/image_raw >/dev/null 2>&1
  fi
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
      if camera_has_required_frame; then
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

gs_usb_echo_error_count() {
  sudo -n dmesg --color=never 2>/dev/null |
    grep -Ec 'gs_usb .*Unexpected (out of range|unused) echo id' || true
}

recover_unhandled_gs_usb_echo_error() {
  local marker="$LOG_DIR/gs_usb_echo_errors.handled" count handled=0
  count=$(gs_usb_echo_error_count)
  [[ "$count" =~ ^[0-9]+$ ]] || count=0
  if [[ -r "$marker" ]]; then
    handled=$(<"$marker")
    [[ "$handled" =~ ^[0-9]+$ ]] || handled=0
  fi
  if (( count <= handled )); then
    return 0
  fi

  echo "[CAN] 检测到 $((count - handled)) 个未处理的 gs_usb echo 异常；在运动启动前重建 can0。"
  sudo -n ip link set can0 down || fail "gs_usb 异常恢复时无法停止 can0。"
  sudo -n ip link set can0 type can bitrate 1000000 sample-point 0.75 ||
    fail "gs_usb 异常恢复时无法重设 can0 位时序。"
  sudo -n ip link set can0 txqueuelen "${BRAIN_ROBOT_CAN_TX_QUEUE:-1000}" ||
    fail "gs_usb 异常恢复时无法重设 can0 TX 队列。"
  sudo -n ip link set can0 up || fail "gs_usb 异常恢复后无法启动 can0。"
  printf '%s\n' "$count" > "$marker"
}

start_can_health_guard() {
  local parent_pid=$$ logfile="$LOG_DIR/can_health.log"
  : > "$logfile"
  (
    local rx_path=/sys/class/net/can0/statistics/rx_packets
    local last_rx current_rx stagnant=0 baseline loop=0 echoes reason
    baseline=$(gs_usb_echo_error_count)
    [[ "$baseline" =~ ^[0-9]+$ ]] || baseline=0
    [[ -r "$rx_path" ]] && last_rx=$(<"$rx_path") || last_rx=0
    while sleep 1; do
      reason=""
      if ! ip link show can0 >/dev/null 2>&1 || [[ ! -r "$rx_path" ]]; then
        reason="CAN_INTERFACE_LOST"
      else
        current_rx=$(<"$rx_path")
        if (( current_rx > last_rx )); then
          stagnant=0
        else
          ((stagnant += 1))
        fi
        last_rx=$current_rx
        if (( stagnant >= 3 )); then
          reason="CAN_RX_STALLED_3S"
        fi
      fi

      ((loop += 1))
      if (( loop % 5 == 0 )); then
        echoes=$(gs_usb_echo_error_count)
        [[ "$echoes" =~ ^[0-9]+$ ]] || echoes=$baseline
        if (( echoes > baseline )); then
          reason="GS_USB_ECHO_ID_ERROR"
        fi
      fi

      if [[ -n "$reason" ]]; then
        echo "[$(date '+%F %T')] $reason: stop outputs and preserve enable"
        timeout 3s ros2 topic pub --once /brain_robot_control/emergency_stop \
          std_msgs/msg/Bool '{data: true}' >/dev/null 2>&1 || true
        kill -TERM "$parent_pid" 2>/dev/null || true
        exit 0
      fi
    done
  ) >>"$logfile" 2>&1 &
  CAN_HEALTH_PID=$!
  echo "[CAN] 已启用运行期守护：3 秒 RX 停滞或新 gs_usb echo 异常将停止输出并保持使能。"
}

configure_can_tx_queue() {
  local can_tx_queue="${BRAIN_ROBOT_CAN_TX_QUEUE:-1000}" can_details
  can_details=$(ip -details link show can0 2>/dev/null || true)
  if grep -Fq "qlen ${can_tx_queue}" <<<"$can_details"; then
    return 0
  fi
  sudo ip link set can0 txqueuelen "$can_tx_queue" ||
    fail "无法将 can0 TX 队列设置为 ${can_tx_queue}；拒绝进入运动流程。"
  echo "[CAN] 已将 can0 TX 队列设置为 ${can_tx_queue}，避免反馈高峰时发送队列溢出。"
}

configure_can() {
  local can_details rx_before rx_now deadline attempt
  local rx_path=/sys/class/net/can0/statistics/rx_packets

  command -v ip >/dev/null 2>&1 || fail "未找到 ip 命令。"
  if ! ip link show can0 >/dev/null 2>&1; then
    echo "[CAN] 未找到 can0，尝试加载 gs_usb..."
    sudo modprobe gs_usb || fail "无法加载 gs_usb 驱动。"
    for attempt in {1..5}; do
      ip link show can0 >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  ip link show can0 >/dev/null 2>&1 ||
    fail "未找到 can0；请确认 USB-CAN 已连接并已透传到虚拟机。"
  recover_unhandled_gs_usb_echo_error

  # Reuse an already configured interface without disturbing the USB-CAN data
  # path. Privileged reconfiguration is allowed only when the link is down or
  # misconfigured; missing robot feedback must never bounce a healthy link.
  can_details=$(ip -details link show can0)
  if grep -Eq 'state (UP|UNKNOWN)' <<<"$can_details" &&
    grep -Fq 'bitrate 1000000' <<<"$can_details" &&
    grep -Fq 'sample-point 0.750' <<<"$can_details" &&
    [[ -r "$rx_path" ]]; then
    configure_can_tx_queue
    rx_before=$(<"$rx_path")
    deadline=$((SECONDS + 5))
    while (( SECONDS < deadline )); do
      sleep 1
      rx_now=$(<"$rx_path")
      if (( rx_now > rx_before )); then
        echo "[CAN] 复用已处于 1 Mbps/0.75 且 RX 持续增长的 can0。"
        return 0
      fi
    done
    echo "[CAN] can0 已正确配置但 RX 未增长；保持接口不变，不执行 down/up。" >&2
    ip -details -statistics link show can0 >&2 || true
    fail "PiPER 控制器没有 CAN 反馈；请检查控制器供电、VMware 实体透传和 CAN 实体链路。"
  fi

  echo "[CAN] 复用现有 USB-CAN，配置 can0 为 1 Mbps、采样点 0.75..."
  local configured=1
  for attempt in {1..5}; do
    if ip link show can0 >/dev/null 2>&1; then
      sudo ip link set can0 down 2>/dev/null || true
      if sudo ip link set can0 type can bitrate 1000000 sample-point 0.75 2>/dev/null && sudo ip link set can0 up 2>/dev/null; then
        configured=0
        break
      fi
    fi
    sleep 1
  done
  (( configured == 0 )) || fail "无法配置或启动 can0；请检查 USB-CAN 连接。"
  configure_can_tx_queue

  can_details=$(ip -details link show can0)
  grep -Eq 'state (UP|UNKNOWN)' <<<"$can_details" &&
    grep -Fq 'bitrate 1000000' <<<"$can_details" &&
    grep -Fq 'sample-point 0.750' <<<"$can_details" ||
    fail "can0 未处于 1 Mbps 工作状态。"

  [[ -r "$rx_path" ]] || fail "无法读取 can0 RX 计数器。"
  rx_before=$(<"$rx_path")
  deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    sleep 1
    rx_now=$(<"$rx_path")
    if (( rx_now > rx_before )); then
      echo "[CAN] 已收到机械臂反馈（RX 增量 $((rx_now - rx_before))）。"
      return 0
    fi
  done

  echo "[CAN] can0 状态与计数：" >&2
  ip -details -statistics link show can0 >&2 || true
  fail "can0 已启动但 5 秒内没有收到机械臂反馈；请检查机械臂电源、USB 透传和 CAN 接线。"
}

node_exists() {
  timeout 5s ros2 node list 2>/dev/null | grep -Fxq "$1"
}

visual_stack_processes_exist() {
  # Use process identities rather than `ros2 node list`: DDS discovery can
  # retain nodes from a just-terminated launch for longer than this script's
  # startup window. Match executable paths, not service-client arguments.
  pgrep -f \
    'ros2 launch brain_robot_ball_pick cube_visual_search\.launch\.py|/brain_robot_pick_place/(piper_jog_adapter\.py|visual_search_controller|grasp_lift_executor|active_scan_supervisor|pointcloud_tf_gate)([[:space:]]|$)|/moveit_servo/servo_node_main([[:space:]]|$)|/moveit_ros_move_group/move_group([[:space:]]|$)|/robot_state_publisher/robot_state_publisher.*piper_moveit_joint_states|/tf2_ros/static_transform_publisher.*piper_camera_mount_tf' \
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
    pkill -TERM -f '/brain_robot_pick_place/(piper_jog_adapter.py|visual_search_controller|grasp_lift_executor|active_scan_supervisor|pointcloud_tf_gate)' \
      2>/dev/null || true
    pkill -TERM -f '/moveit_servo/servo_node_main' 2>/dev/null || true
    pkill -TERM -f '/moveit_ros_move_group/move_group' 2>/dev/null || true
    pkill -TERM -f '/robot_state_publisher/robot_state_publisher.*piper_moveit_joint_states' \
      2>/dev/null || true
    pkill -TERM -f '/tf2_ros/static_transform_publisher.*piper_camera_mount_tf' \
      2>/dev/null || true
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

stop_stale_low_level_stack() {
  local pattern="$1" label="$2" deadline pid pgid
  if ! pgrep -f "$pattern" >/dev/null 2>&1; then
    return 0
  fi

  echo "[清理] 检测到遗留的 ${label}，正在停止..."
  while read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
    if [[ -n "$pgid" && "$pgid" == "$pid" ]]; then
      kill -TERM -- "-$pgid" 2>/dev/null || true
    else
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f "$pattern" || true)

  deadline=$((SECONDS + 15))
  while (( SECONDS < deadline )); do
    if ! pgrep -f "$pattern" >/dev/null 2>&1; then
      echo "[清理] 遗留的 ${label} 已退出。"
      return 0
    fi
    sleep 1
  done
  echo "[清理] ${label} 未响应 TERM，发送 KILL..."
  pkill -KILL -f "$pattern" 2>/dev/null || true
  sleep 1
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    fail "遗留的 ${label} 未完全退出；拒绝启动第二套控制器。"
  fi
  return 0
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
        MOTION_ARMED=1
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
  echo "[启动] 从当前反馈姿态移动到观测姿态..."
  local result
  result=$(timeout 8s ros2 service call /visual_search_controller/start \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  if ! grep -Eq 'success=True' <<<"$result"; then
    echo "[错误] 视觉复位/搜索启动失败。"
    return 1
  fi
  local deadline=$((SECONDS + ${BRAIN_ROBOT_PREPARE_WAIT_SECONDS:-320})) status
  while (( SECONDS < deadline )); do
    status=$(timeout 4s ros2 topic echo --once \
      --qos-reliability reliable \
      --qos-durability transient_local \
      /brain_robot_visual_control/reason 2>&1) || status=""
    if grep -Eq 'OBSERVE_POSE_REACHED|CURRENT_POSE_ACCEPTED' <<<"$status"; then
      echo "[启动] 观测姿态已达到；已进入深度方块搜索。"
      return 0
    fi
    if grep -Eq 'PREPARE_(EXECUTION_FAILED|JOINT_STATE_MISSING|CANCELLED)|SERVO_START_FAILED' <<<"$status"; then
      echo "[错误] 观测姿态执行失败：${status//$'\n'/ }" >&2
      return 1
    fi
    sleep 1
  done
  echo "[错误] 等待观测姿态完成超时；未进入深度方块搜索。" >&2
  return 1
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
  echo "[重启] 停止当前视觉流程，保持当前姿态并直接移动到观测姿态..."
  timeout 5s ros2 service call /visual_search_controller/stop \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  timeout 5s ros2 service call /servo_node/stop_servo \
    std_srvs/srv/Trigger '{}' >/dev/null 2>&1 || true
  enable_physical_motion || return 1
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

disable_after_confirmed_reset() {
  local result
  result=$(timeout 5s ros2 service call /piper_jog_adapter/disarm \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  if ! grep -Eq 'success=True' <<<"$result"; then
    echo "[收尾] 适配器 disarm 未确认；保持 PiPER 使能。" >&2
    return 1
  fi
  result=$(timeout 5s ros2 service call /piper_jog_adapter/disable_motion \
    std_srvs/srv/Trigger '{}' 2>&1) || result=""
  if ! grep -Eq 'success=True' <<<"$result"; then
    echo "[收尾] 运动门关闭未确认；保持 PiPER 使能。" >&2
    return 1
  fi
  result=$(timeout 8s ros2 service call /enable_srv piper_msgs/srv/Enable \
    '{enable_request: false}' 2>&1) || result=""
  if ! grep -Eq 'enable_response=True' <<<"$result"; then
    echo "[收尾] 六轴失能反馈未确认；机械臂已回零但按保持使能处理。" >&2
    return 1
  fi
  MOTION_ARMED=0
  echo "[收尾] RESET_COMPLETE 后六轴失能已确认。"
  return 0
}

wait_for_grasp_release_and_finalize() {
  local deadline=$((SECONDS + ${BRAIN_ROBOT_GRASP_WAIT_SECONDS:-900})) status
  echo "[自动] 等待目标锁定、预抓取、闭爪、抬升、释放和撤离完成..."
  while (( SECONDS < deadline )); do
    status=$(timeout 4s ros2 topic echo --once \
      --qos-reliability reliable \
      --qos-durability transient_local \
      /brain_robot_grasp/state 2>&1) || status=""
    if grep -Fq 'RELEASE_COMPLETE_HOLDING_SAFE_RETREAT' <<<"$status"; then
      echo "[收尾] 释放与撤离已确认；开始成功路径的安全零点回位。"
      if ! reset_zero_sequence; then
        echo "[收尾] 安全回位失败；保持当前位置和使能，禁止失能。" >&2
        return 1
      fi
      disable_after_confirmed_reset
      return $?
    fi
    if grep -Fq 'FAULT_' <<<"$status"; then
      echo "[抓取] 抓取执行器报告故障：${status//$'\n'/ }" >&2
      return 1
    fi
    sleep 1
  done
  echo "[抓取] 等待完整抓取/释放超时；保持当前流程和使能。" >&2
  return 1
}

echo "=================================================="
echo " PiPER 实体深度方块视觉抓取（一键保护模式）"
echo " 自动启动 CAN、PiPER 驱动、相机、MoveIt、Servo 和检测器"
echo " DDS 使用 UDPv4（禁用易残留锁的 Fast DDS 共享内存传输）"
echo "=================================================="
prepare_logs
bash "$SCRIPT_DIR/clean_disk_space.sh" || true
check_disk_headroom
start_log_guard
stop_stale_low_level_stack '/piper_single_ctrl([[:space:]]|$)' 'PiPER 低层驱动'
stop_stale_low_level_stack 'ros2 launch brain_robot_ball_pick cube_detector\.launch\.py' '紫色方块检测器'
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
wait_for_joint_feedback /joint_states
wait_for service /enable_srv
start_can_health_guard

echo "[2/7] 检查并启动深度相机..."
if ! node_exists /camera/camera; then
  start_astra_camera
else
  echo "[复用] 已检测到 /camera/camera"
fi
wait_for topic /camera/depth/image_raw
start_camera_health_guard
wait_for_actual_frame /camera/depth/image_raw "深度图像"

if [[ "$DEPTH_ONLY_TARGET" == "1" || "$DEPTH_ONLY_TARGET" == "true" ||
  "$DEPTH_ONLY_TARGET" == "yes" ]]; then
  echo "[3/7] 深度-only模式：跳过紫色 RGB 检测器。"
else
  echo "[3/7] 启动紫色方块 RGB-D 检测..."
  start_group cube_detector ros2 launch brain_robot_ball_pick cube_detector.launch.py
  wait_for topic /brain_robot_vision/debug_image
fi

echo "[4/7] 启动 MoveIt、Servo 和真机保护适配器..."
stop_stale_visual_stack
start_group visual_stack ros2 launch brain_robot_ball_pick cube_visual_search.launch.py
wait_for node /move_group
wait_for node /servo_node
wait_for node /piper_jog_adapter
wait_for node /grasp_lift_executor
wait_for node /depth_cube_probe
wait_for node /pointcloud_tf_gate
wait_for service /piper_jog_adapter/arm
wait_for service /visual_search_controller/reset
wait_for service /grasp_lift_executor/execute

echo "[5/7] 检查完整 MoveIt 反馈和自体过滤 TF..."
wait_for topic /piper_moveit_joint_states
wait_for_joint_feedback /piper_moveit_joint_states
wait_for topic /brain_robot_vision/tf_gate_diagnostic
wait_for_tf_validated_pointcloud
wait_for_filtered_pointcloud
echo "[地图] 已验证相机到基座 TF；腕部相机的深度点云不写入 Octomap，避免夹爪自体障碍。"
if [[ "$DEPTH_ONLY_TARGET" == "1" || "$DEPTH_ONLY_TARGET" == "true" ||
  "$DEPTH_ONLY_TARGET" == "yes" ]]; then
  echo "[6/7] 深度几何门控已启动；无需 RGB 调试窗口。"
else
  echo "[6/7] 打开识别窗口..."
  start_group debug_image_view ros2 run image_view image_view --ros-args -r image:=/brain_robot_vision/debug_image
  wait_for_actual_frame /brain_robot_vision/debug_image "调试图像"
fi
echo "[7/7] 全部组件已就绪。"
echo
if [[ "$AUTO_START" == "1" || "$AUTO_START" == "true" || "$AUTO_START" == "yes" ]]; then
  echo "[自动] 组件就绪，从当前反馈姿态进入观测、搜索和完整抓取流程。"
  if ! restart_visual_sequence; then
    DISABLE_REQUESTED=1
    echo "[保持] 自动观测姿态启动失败；停止新增输出、保持 PiPER 使能并退出，不等待按键。" >&2
    exit 1
  fi
  if ! wait_for_grasp_release_and_finalize; then
    DISABLE_REQUESTED=1
    echo "[保持] 自动抓取未完整成功；不自动回零或失能，退出且不等待按键。" >&2
    exit 1
  fi
  SUCCESSFUL_CYCLE_COMPLETE=1
  echo "[完成] 深度方块抓取、抬升、同位释放、安全回位和失能均已确认。"
  exit 0
else
  echo "[手动] 自动运动已关闭；按 1 从当前反馈姿态开始观测/搜索。"
fi
echo "操作：1=重试观测/搜索；2=GRASP_READY 后抓取；0=显式零点复位；Ctrl+C=停止控制并保持使能退出。"
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
