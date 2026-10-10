#!/usr/bin/env bash
# Install the purple-cube detector and protected physical visual-search profile.
set -Eeuo pipefail

SHARED_ROOT="${BRAIN_ROBOT_SHARED_ROOT:-/mnt/hgfs/ub/brain_robot_arm}"
APP_WS="${BRAIN_ROBOT_WS:-$HOME/piper_ws}"
PIPER_WS="${PIPER_ROS_WS:-$HOME/piper_ros}"
BASE_SOURCE="$SHARED_ROOT/piper_ws/src/brain_robot_pick_place"
TASK_SOURCE="$SHARED_ROOT/piper_ws/src/brain_robot_ball_pick"
PIPER_DRIVER_SOURCE="$SHARED_ROOT/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py"
PIPER_DRIVER_REQUIREMENTS="$SHARED_ROOT/vendor/piper_ros/requirements-piper-driver.txt"
START_SOURCE="$SHARED_ROOT/scripts/start_brain_robot_cube_real.sh"
CLEAN_SOURCE="$SHARED_ROOT/scripts/clean_disk_space.sh"
LOG_HELPER_SOURCE="$SHARED_ROOT/scripts/brain_robot_log_maintenance_root.sh"
LOG_SETUP_SOURCE="$SHARED_ROOT/scripts/install_brain_robot_log_maintenance.sh"

fail() { echo "[错误] $*" >&2; exit 1; }
[[ -z "${CONDA_PREFIX:-}" ]] || fail "请先执行 conda deactivate。"
[[ -f /opt/ros/humble/setup.bash ]] || fail "未找到 ROS2 Humble。"
[[ -f "$PIPER_WS/install/setup.bash" ]] || fail "请先编译 ~/piper_ros。"
[[ -f "$BASE_SOURCE/package.xml" && -f "$TASK_SOURCE/package.xml" ]] || fail "共享文件夹缺少工程源文件。"
[[ -f "$PIPER_DRIVER_SOURCE" && -f "$PIPER_DRIVER_REQUIREMENTS" ]] ||
  fail "共享文件夹缺少 V2 PiPER 驱动源文件或 SDK 版本约束。"
[[ -f "$START_SOURCE" ]] || fail "共享文件夹缺少实体紫色方块启动脚本。"
[[ -f "$CLEAN_SOURCE" ]] || fail "共享文件夹缺少磁盘清理脚本。"
[[ -f "$LOG_HELPER_SOURCE" && -f "$LOG_SETUP_SOURCE" ]] ||
  fail "共享文件夹缺少受限日志维护脚本。"

mkdir -p "$APP_WS/src/brain_robot_pick_place" "$APP_WS/src/brain_robot_ball_pick"
cp -a "$BASE_SOURCE/." "$APP_WS/src/brain_robot_pick_place/"
cp -a "$TASK_SOURCE/." "$APP_WS/src/brain_robot_ball_pick/"
find "$APP_WS/src/brain_robot_pick_place" "$APP_WS/src/brain_robot_ball_pick" -type f -exec touch {} +
chmod +x "$APP_WS/src/brain_robot_pick_place/scripts/"*.py

set +u
source /opt/ros/humble/setup.bash
source "$PIPER_WS/install/setup.bash"
set -u
ros2 pkg executables moveit_servo | grep -F 'servo_node_main' >/dev/null ||
  fail "缺少 MoveIt Servo；先执行 sudo apt install ros-humble-moveit-servo"

echo "[1/3] 同步 V2 PiPER 驱动并固定 piper_sdk 版本..."
[[ -f "$PIPER_WS/src/piper/piper/piper_ctrl_single_node.py" ]] ||
  fail "未找到 ~/piper_ros/src/piper；请先准备官方 piper_ros 工作空间。"
cp "$PIPER_DRIVER_SOURCE" "$PIPER_WS/src/piper/piper/piper_ctrl_single_node.py"
python3 -m pip install --user --upgrade -r "$PIPER_DRIVER_REQUIREMENTS"
cd "$PIPER_WS"
colcon build --symlink-install --packages-select piper

cd "$APP_WS"
echo "[2/3] 编译紫色方块检测器、真机保护适配器和通用控制组件..."
colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick
echo "[3/3] 安装实体紫色方块启动脚本..."
cp "$START_SOURCE" "$HOME/start_brain_robot_cube_real.sh"
chmod +x "$HOME/start_brain_robot_cube_real.sh"
cp "$CLEAN_SOURCE" "$HOME/clean_disk_space.sh"
chmod +x "$HOME/clean_disk_space.sh"
cp "$LOG_HELPER_SOURCE" "$HOME/brain_robot_log_maintenance_root.sh"
chmod +x "$HOME/brain_robot_log_maintenance_root.sh"
cp "$LOG_SETUP_SOURCE" "$HOME/install_brain_robot_log_maintenance.sh"
chmod +x "$HOME/install_brain_robot_log_maintenance.sh"
echo "[完成] 启动、清理和日志维护脚本已更新。"
echo "[首次可选配置] 如需清理 syslog/kern.log 且以后不输密码，执行：~/install_brain_robot_log_maintenance.sh"
