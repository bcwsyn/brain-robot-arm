#!/usr/bin/env bash
# PiPER 脑控机械臂视觉仿真一键启动器。
# 只连接仿真，不连接 CAN、实体机械臂或头环；机械臂运动必须在终端按 s 授权。

set -Eeuo pipefail

SIMULATION_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

ROS_SETUP="/opt/ros/humble/setup.bash"
PIPER_WS="$SIMULATION_WS"
PIPER_SETUP="$PIPER_WS/install/setup.bash"
APP_WS="$SIMULATION_WS"
APP_SETUP="$APP_WS/install/setup.bash"
SIM_SCRIPT="$SIMULATION_WS/scripts/start_piper_sim.sh"
WAIT_SECONDS="${BRAIN_ROBOT_WAIT_SECONDS:-90}"
QUERY_TIMEOUT="${BRAIN_ROBOT_QUERY_TIMEOUT:-5}"

SIM_PID=""
SIM_PGID=""
SCENE_PID=""
SCENE_PGID=""
DETECTOR_PID=""
DETECTOR_PGID=""
CONTROL_PID=""
CONTROL_PGID=""
VIEWER_PID=""
VIEWER_PGID=""
RECORDED_PGID=""
CLEANING_UP=0

fail() {
    echo "[错误] $*" >&2
    exit 1
}

require_file() {
    local path="$1"
    local description="$2"
    [[ -f "$path" ]] || fail "未找到${description}：$path"
}

group_alive() {
    local pgid="$1"
    [[ -n "$pgid" ]] && kill -0 -- "-$pgid" 2>/dev/null
}

record_process_group() {
    local pid="$1"
    local label="$2"
    local pgid=""

    sleep 0.3
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    [[ -n "$pgid" ]] || fail "$label 启动后立即退出，请查看上方日志。"
    [[ "$pgid" == "$pid" ]] || fail "$label 未建立独立进程组，脚本为避免误关其他程序而停止。"
    RECORDED_PGID="$pgid"
}

signal_group() {
    local label="$1"
    local pgid="$2"
    local signal="$3"

    if group_alive "$pgid"; then
        echo "  - 向 $label 发送 $signal"
        kill -s "$signal" -- "-$pgid" 2>/dev/null || true
    fi
}

cleanup() {
    local exit_code="${1:-0}"

    if (( CLEANING_UP )); then
        exit "$exit_code"
    fi
    CLEANING_UP=1
    # 清理期间忽略重复的 Ctrl+C/TERM，避免用户第二次按键中断子进程回收。
    trap - EXIT
    trap '' INT TERM

    echo
    echo "[关闭] 正在统一停止视觉控制、识别窗口、检测器、场景和仿真..."
    # 后台启动的 Bash 可能继承“忽略 SIGINT”的状态。直接发送 SIGTERM，
    # 让底层脚本进入其 TERM 清理陷阱，并给它足够时间关闭独立的子进程组。
    signal_group "视觉搜索控制" "$CONTROL_PGID" TERM
    signal_group "识别窗口" "$VIEWER_PGID" TERM
    signal_group "红杯检测器" "$DETECTOR_PGID" TERM
    signal_group "桌面场景" "$SCENE_PGID" TERM
    signal_group "底层仿真" "$SIM_PGID" TERM

    local deadline=$((SECONDS + 20))
    while (( SECONDS < deadline )); do
        if ! group_alive "$CONTROL_PGID" &&
           ! group_alive "$VIEWER_PGID" &&
           ! group_alive "$DETECTOR_PGID" &&
           ! group_alive "$SCENE_PGID" &&
           ! group_alive "$SIM_PGID"; then
            break
        fi
        sleep 0.2
    done

    signal_group "视觉搜索控制" "$CONTROL_PGID" KILL
    signal_group "识别窗口" "$VIEWER_PGID" KILL
    signal_group "红杯检测器" "$DETECTOR_PGID" KILL
    signal_group "桌面场景" "$SCENE_PGID" KILL
    signal_group "底层仿真" "$SIM_PGID" KILL

    [[ -n "$CONTROL_PID" ]] && wait "$CONTROL_PID" 2>/dev/null || true
    [[ -n "$VIEWER_PID" ]] && wait "$VIEWER_PID" 2>/dev/null || true
    [[ -n "$DETECTOR_PID" ]] && wait "$DETECTOR_PID" 2>/dev/null || true
    [[ -n "$SCENE_PID" ]] && wait "$SCENE_PID" 2>/dev/null || true
    [[ -n "$SIM_PID" ]] && wait "$SIM_PID" 2>/dev/null || true

    echo "[完成] 本次视觉仿真演示已全部关闭。"
    exit "$exit_code"
}

trap 'cleanup 130' INT
trap 'cleanup 143' TERM
trap 'cleanup $?' EXIT

graph_contains() {
    local graph_kind="$1"
    local exact_name="$2"
    timeout "$QUERY_TIMEOUT" ros2 "$graph_kind" list 2>/dev/null | grep -Fxq "$exact_name"
}

wait_for_graph_item() {
    local label="$1"
    local graph_kind="$2"
    local exact_name="$3"
    local watched_pid="$4"
    local deadline=$((SECONDS + WAIT_SECONDS))

    while (( SECONDS < deadline )); do
        kill -0 "$watched_pid" 2>/dev/null || fail "$label 就绪前相关进程已经退出。"
        if graph_contains "$graph_kind" "$exact_name"; then
            echo "[就绪] $label"
            return 0
        fi
        sleep 1
    done
    fail "等待${label}超时：$exact_name"
}

wait_for_scene_ready() {
    local deadline=$((SECONDS + WAIT_SECONDS))
    local output=""

    while (( SECONDS < deadline )); do
        kill -0 "$SCENE_PID" 2>/dev/null || fail "桌面场景就绪前已经退出。"
        output="$(timeout "$QUERY_TIMEOUT" ros2 topic echo --once \
          /brain_robot_pick_place/scene_ready 2>/dev/null || true)"
        if grep -Fq 'data: true' <<< "$output"; then
            echo "[就绪] 桌子和红杯场景"
            return 0
        fi
        sleep 1
    done
    fail "等待桌子和红杯场景超时。"
}

echo "=================================================="
echo " PiPER 脑控机械臂视觉仿真一键启动"
echo " 仅仿真：不会连接实体机械臂、Gemini2或头环"
echo "=================================================="

if [[ -n "${CONDA_PREFIX:-}" ]]; then
    fail "当前处于 Conda 环境：$CONDA_PREFIX。请先执行 conda deactivate。"
fi

require_file "$ROS_SETUP" "ROS2 Humble环境"
require_file "$PIPER_SETUP" "PiPER工作空间编译结果"
require_file "$APP_SETUP" "脑控机械臂工作空间编译结果"
require_file "$SIM_SCRIPT" "底层仿真启动脚本"

command -v setsid >/dev/null 2>&1 || fail "系统缺少 setsid 命令。"
command -v timeout >/dev/null 2>&1 || fail "系统缺少 timeout 命令。"

set +u
source "$ROS_SETUP"
source "$PIPER_SETUP"
source "$APP_SETUP"
set -u

ros2 pkg executables brain_robot_pick_place | grep -F 'cup_detector_node' >/dev/null ||
    fail "未找到 C++红杯检测器，请先重新编译 brain_robot_pick_place。"
ros2 pkg executables brain_robot_pick_place | grep -F 'visual_search_controller' >/dev/null ||
    fail "未找到视觉搜索控制器，请先重新编译 brain_robot_pick_place。"
ros2 pkg executables brain_robot_pick_place | grep -F 'grasp_lift_executor' >/dev/null ||
    fail "未找到抓取抬升执行器，请先重新编译 brain_robot_pick_place。"
ros2 pkg executables moveit_servo | grep -F 'servo_node_main' >/dev/null ||
    fail "未找到 MoveIt Servo，请先安装：sudo apt install ros-humble-moveit-servo"
ros2 pkg executables image_view | grep -F 'image_view' >/dev/null ||
    fail "未找到 image_view，请安装 ros-humble-image-view。"

echo "[1/5] 启动 Gazebo、PiPER、MoveIt2和RViz2..."
setsid bash "$SIM_SCRIPT" &
SIM_PID=$!
record_process_group "$SIM_PID" "底层仿真"
SIM_PGID="$RECORDED_PGID"

wait_for_graph_item "MoveIt2" node /move_group "$SIM_PID"
wait_for_graph_item \
    "腕部相机彩色图像" topic /wrist_camera/wrist_camera/image_raw "$SIM_PID"

echo "[2/5] 加载桌子和红杯场景..."
setsid ros2 launch brain_robot_pick_place scene.launch.py &
SCENE_PID=$!
record_process_group "$SCENE_PID" "桌面场景"
SCENE_PGID="$RECORDED_PGID"
wait_for_scene_ready

echo "[3/5] 启动 C++红杯检测器..."
setsid ros2 launch brain_robot_pick_place cup_detector.launch.py &
DETECTOR_PID=$!
record_process_group "$DETECTOR_PID" "红杯检测器"
DETECTOR_PGID="$RECORDED_PGID"
wait_for_graph_item \
    "红杯标注图像" topic /brain_robot_vision/debug_image "$DETECTOR_PID"

echo "[4/5] 启动MoveIt Servo和视觉搜索控制器..."
setsid ros2 launch brain_robot_pick_place visual_search.launch.py &
CONTROL_PID=$!
record_process_group "$CONTROL_PID" "视觉搜索控制"
CONTROL_PGID="$RECORDED_PGID"
wait_for_graph_item \
    "视觉搜索控制节点" node /visual_search_controller "$CONTROL_PID"
wait_for_graph_item \
    "抓取抬升执行节点" node /grasp_lift_executor "$CONTROL_PID"
wait_for_graph_item \
    "视觉搜索开始服务" service /visual_search_controller/start "$CONTROL_PID"

echo "[5/5] 打开红杯识别画面..."
setsid ros2 run image_view image_view --ros-args \
    -r image:=/brain_robot_vision/debug_image &
VIEWER_PID=$!
record_process_group "$VIEWER_PID" "识别窗口"
VIEWER_PGID="$RECORDED_PGID"

sleep 1
kill -0 "$VIEWER_PID" 2>/dev/null || fail "识别窗口启动后立即退出。"

echo
echo "=================================================="
echo " 视觉仿真演示已就绪"
echo " 已启动：Gazebo + MoveIt2/RViz2 + 场景 + 红杯识别 + 视觉控制"
echo " 默认没有运动授权。请在本终端按 s 开始搜索/对准/接近。"
echo " 运行中按 x 立即停止；按一次 Ctrl+C 统一关闭全部程序。"
echo "=================================================="

while true; do
    kill -0 "$SIM_PID" 2>/dev/null || fail "底层仿真意外退出。"
    kill -0 "$SCENE_PID" 2>/dev/null || fail "桌面场景意外退出。"
    kill -0 "$DETECTOR_PID" 2>/dev/null || fail "红杯检测器意外退出。"
    kill -0 "$CONTROL_PID" 2>/dev/null || fail "视觉搜索控制器意外退出。"
    kill -0 "$VIEWER_PID" 2>/dev/null || fail "识别窗口已关闭。"
    if [[ -t 0 ]] && read -r -s -n 1 -t 1 key; then
        case "$key" in
            s|S)
                echo
                echo "[操作] 请求开始视觉搜索..."
                timeout 12s ros2 service call \
                    /visual_search_controller/start std_srvs/srv/Trigger '{}' ||
                    echo "[错误] 开始请求失败，请查看视觉控制日志。"
                ;;
            x|X)
                echo
                echo "[操作] 请求停止机械臂运动..."
                timeout 5s ros2 service call \
                    /visual_search_controller/stop std_srvs/srv/Trigger '{}' ||
                    echo "[错误] 停止请求失败，请直接按一次 Ctrl+C。"
                ;;
        esac
    else
        sleep 0.1
    fi
done
