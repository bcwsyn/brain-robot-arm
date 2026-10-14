#!/usr/bin/env bash
# PiPER 带夹爪与腕部相机 Gazebo + MoveIt2 一键启动脚本
# Ubuntu 使用方法：bash simulation/scripts/start_piper_sim.sh

set -Eeuo pipefail

SIMULATION_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

ROS_SETUP="/opt/ros/humble/setup.bash"
PIPER_WS="$SIMULATION_WS"
WS_SETUP="$PIPER_WS/install/setup.bash"
APP_WS="$SIMULATION_WS"
APP_SETUP="$APP_WS/install/setup.bash"
JOINT8_SCRIPT="$PIPER_WS/src/piper_gazebo/scripts/joint8_ctrl.py"
WAIT_SECONDS="${PIPER_SIM_WAIT_SECONDS:-60}"
QUERY_TIMEOUT="${PIPER_ROS_QUERY_TIMEOUT:-10}"
LOCK_FILE="${PIPER_SIM_LOCK_FILE:-${XDG_RUNTIME_DIR:-/tmp}/piper_brain_robot_sim_$(id -u).lock}"

# The flock process owns the lock, while this script and all ROS children run
# without inheriting the lock descriptor. If this script is killed, orphaned
# Gazebo processes cannot keep the next launch locked out.
if [[ "${PIPER_SIM_LOCKED:-0}" != "1" ]]; then
    command -v flock >/dev/null 2>&1 || {
        echo "[错误] 系统缺少 flock 命令，无法防止重复启动。" >&2
        exit 1
    }
    flock --exclusive --nonblock --close --conflict-exit-code 73 \
        "$LOCK_FILE" env PIPER_SIM_LOCKED=1 bash "$0" "$@" && exit 0
    LOCK_STATUS=$?
    if (( LOCK_STATUS == 73 )); then
        echo "[错误] 已有一套新版 PiPER 仿真正在运行；不会关闭正在使用的实例。" >&2
    fi
    exit "$LOCK_STATUS"
fi

GAZEBO_PID=""
GAZEBO_PGID=""
MOVEIT_PID=""
MOVEIT_PGID=""
RECORDED_PGID=""
CLEANING_UP=0

group_alive() {
    local pgid="$1"
    [[ -n "$pgid" ]] && kill -0 -- "-$pgid" 2>/dev/null
}

stop_group() {
    local label="$1"
    local pgid="$2"
    local signal="$3"

    if group_alive "$pgid"; then
        echo "  - 向 $label 发送 $signal 信号"
        kill -s "$signal" -- "-$pgid" 2>/dev/null || true
    fi
}

cleanup() {
    local exit_code="${1:-0}"

    if (( CLEANING_UP )); then
        exit "$exit_code"
    fi
    CLEANING_UP=1
    trap - INT TERM EXIT

    if [[ -z "$MOVEIT_PGID" && -z "$GAZEBO_PGID" ]]; then
        exit "$exit_code"
    fi

    echo
    echo "[关闭] 正在停止 MoveIt2 和 Gazebo..."
    stop_group "MoveIt2" "$MOVEIT_PGID" INT
    stop_group "Gazebo" "$GAZEBO_PGID" INT

    local deadline=$((SECONDS + 8))
    while (( SECONDS < deadline )); do
        if ! group_alive "$MOVEIT_PGID" && ! group_alive "$GAZEBO_PGID"; then
            break
        fi
        sleep 0.2
    done

    stop_group "MoveIt2" "$MOVEIT_PGID" TERM
    stop_group "Gazebo" "$GAZEBO_PGID" TERM

    deadline=$((SECONDS + 3))
    while (( SECONDS < deadline )); do
        if ! group_alive "$MOVEIT_PGID" && ! group_alive "$GAZEBO_PGID"; then
            break
        fi
        sleep 0.2
    done

    stop_group "MoveIt2" "$MOVEIT_PGID" KILL
    stop_group "Gazebo" "$GAZEBO_PGID" KILL

    [[ -n "$MOVEIT_PID" ]] && wait "$MOVEIT_PID" 2>/dev/null || true
    [[ -n "$GAZEBO_PID" ]] && wait "$GAZEBO_PID" 2>/dev/null || true
    echo "[完成] 本次仿真进程已关闭。"
    exit "$exit_code"
}

trap 'cleanup 130' INT
trap 'cleanup 143' TERM
trap 'cleanup $?' EXIT

fail() {
    echo "[错误] $*" >&2
    exit 1
}

require_file() {
    local path="$1"
    local description="$2"
    [[ -f "$path" ]] || fail "未找到${description}：$path"
}

old_process_pids() {
    local uid
    uid="$(id -u)"

    {
        pgrep -u "$uid" -f '(piper_gazebo|wrist_camera_gazebo)\.launch\.py' || true
        pgrep -u "$uid" -f 'piper_moveit\.launch\.py' || true
        pgrep -u "$uid" -f '/piper_gazebo/joint8_ctrl\.py' || true
        pgrep -u "$uid" -x gzserver || true
        pgrep -u "$uid" -x gzclient || true
    } | sort -un
}

old_process_groups() {
    local own_pgid
    local pid
    local pgid

    own_pgid="$(ps -o pgid= -p "$$" | tr -d '[:space:]')"
    while read -r pid; do
        [[ -n "$pid" ]] || continue
        pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
        [[ -n "$pgid" && "$pgid" != "$own_pgid" ]] || continue
        echo "$pgid"
    done < <(old_process_pids)
}

cleanup_old_processes() {
    local -a old_pgids=()
    local -a remaining_pids=()
    local pgid
    local pid
    local deadline
    local any_alive

    mapfile -t old_pgids < <(old_process_groups | sort -un)
    if (( ${#old_pgids[@]} == 0 )); then
        return
    fi

    echo "[恢复] 检测到上次遗留的 PiPER/Gazebo 仿真进程，正在自动关闭..."
    for pgid in "${old_pgids[@]}"; do
        echo "  - 向旧进程组 $pgid 发送 TERM"
        kill -TERM -- "-$pgid" 2>/dev/null || true
    done

    deadline=$((SECONDS + 8))
    while (( SECONDS < deadline )); do
        any_alive=0
        for pgid in "${old_pgids[@]}"; do
            if group_alive "$pgid"; then
                any_alive=1
                break
            fi
        done
        (( any_alive )) || break
        sleep 0.2
    done

    for pgid in "${old_pgids[@]}"; do
        if group_alive "$pgid"; then
            echo "  - 旧进程组 $pgid 未退出，发送 KILL"
            kill -KILL -- "-$pgid" 2>/dev/null || true
        fi
    done
    sleep 0.5

    mapfile -t remaining_pids < <(old_process_pids)
    if (( ${#remaining_pids[@]} > 0 )); then
        echo "[诊断] 以下仿真进程仍未退出：" >&2
        for pid in "${remaining_pids[@]}"; do
            ps -o pid=,ppid=,pgid=,stat=,etime=,args= -p "$pid" >&2 || true
        done
        fail "自动清理失败，为避免重复控制器，停止启动。"
    fi
    echo "[恢复] 旧仿真进程已清理，继续启动新实例。"
}

record_process_group() {
    local pid="$1"
    local label="$2"
    local pgid=""

    sleep 0.3
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    [[ -n "$pgid" ]] || fail "$label 启动后立即退出，请查看上方日志。"
    [[ "$pgid" == "$pid" ]] || fail "$label 未建立独立进程组，为避免误结束其他程序，脚本已停止。"
    RECORDED_PGID="$pgid"
}

echo "=========================================="
echo " PiPER 带夹爪与腕部相机仿真一键启动"
echo " Gazebo + MoveIt2 / ROS2 Humble"
echo "=========================================="

if [[ -n "${CONDA_PREFIX:-}" ]]; then
    fail "当前处于 Conda 环境：$CONDA_PREFIX。请先执行 conda deactivate，再重新运行脚本。"
fi

require_file "$ROS_SETUP" "ROS2 Humble环境"
require_file "$WS_SETUP" "PiPER工作空间编译结果"
require_file "$APP_SETUP" "脑控机械臂工作空间编译结果"
require_file "$JOINT8_SCRIPT" "夹爪镜像控制脚本"

if [[ ! -x "$JOINT8_SCRIPT" ]]; then
    fail "夹爪脚本没有执行权限。请执行：chmod +x '$JOINT8_SCRIPT'"
fi

if head -n 1 "$JOINT8_SCRIPT" | grep -q $'\r$'; then
    fail "夹爪脚本使用Windows换行，Ubuntu无法识别解释器。请执行：sed -i 's/\\r$//' '$JOINT8_SCRIPT'"
fi

command -v setsid >/dev/null 2>&1 || fail "系统缺少 setsid 命令。"
command -v timeout >/dev/null 2>&1 || fail "系统缺少 timeout 命令。"
command -v pgrep >/dev/null 2>&1 || fail "系统缺少 pgrep 命令。"

# Imported into an isolated workspace: do not kill unrelated Gazebo sessions.
if [[ -n "$(old_process_pids)" ]]; then
    fail "检测到已有 Gazebo/规划进程。请先确认并手动关闭对应实例，再启动本工作区。"
fi

# ROS2生成的环境脚本可能读取尚未定义的变量，加载时暂时关闭nounset。
set +u
source "$ROS_SETUP"
source "$WS_SETUP"
if [[ -f "$APP_SETUP" ]]; then
    source "$APP_SETUP"
fi
set -u

command -v ros2 >/dev/null 2>&1 || fail "加载环境后仍未找到 ros2 命令。"

EN_LOCALE="$(locale -a 2>/dev/null | grep -iE '^en_US\.(UTF-8|utf8)$' | head -n 1 || true)"
export LC_NUMERIC="${EN_LOCALE:-C}"

echo "[1/3] 正在启动带夹爪和腕部相机的 Gazebo..."
setsid ros2 launch brain_robot_pick_place wrist_camera_gazebo.launch.py &
GAZEBO_PID=$!
record_process_group "$GAZEBO_PID" "Gazebo"
GAZEBO_PGID="$RECORDED_PGID"

echo "[2/3] 等待机械臂控制接口就绪（最长 ${WAIT_SECONDS} 秒）..."
REQUIRED_ACTIONS=(
    /arm_controller/follow_joint_trajectory
    /gripper_controller/follow_joint_trajectory
    /gripper8_controller/follow_joint_trajectory
)
ACTION_OUTPUT=""
TOPIC_OUTPUT=""
READY=0
DEADLINE=$((SECONDS + WAIT_SECONDS))

while (( SECONDS < DEADLINE )); do
    kill -0 "$GAZEBO_PID" 2>/dev/null || fail "Gazebo在控制器就绪前退出，请查看上方日志。"

    # 直接检查MoveIt实际使用的动作接口，避免解析list_controllers的表格文字。
    ACTION_OUTPUT="$(timeout "$QUERY_TIMEOUT" ros2 action list 2>/dev/null || true)"
    TOPIC_OUTPUT="$(timeout "$QUERY_TIMEOUT" ros2 topic list 2>/dev/null || true)"
    ALL_READY=1
    for action_name in "${REQUIRED_ACTIONS[@]}"; do
        if ! grep -Fxq "$action_name" <<< "$ACTION_OUTPUT"; then
            ALL_READY=0
            break
        fi
    done

    if ! grep -Fxq '/joint_states' <<< "$TOPIC_OUTPUT"; then
        ALL_READY=0
    fi

    if (( ALL_READY )); then
        READY=1
        break
    fi
    sleep 1
done

if (( ! READY )); then
    echo "[诊断] 当前发现的控制动作接口："
    if [[ -n "$ACTION_OUTPUT" ]]; then
        echo "$ACTION_OUTPUT"
    else
        echo "  尚未发现控制动作接口。"
    fi
    echo "[诊断] /joint_states 话题状态："
    if grep -Fxq '/joint_states' <<< "$TOPIC_OUTPUT"; then
        echo "  已发现 /joint_states"
    else
        echo "  未发现 /joint_states"
    fi
    fail "等待机械臂控制接口超时，MoveIt2不会启动。"
fi

echo "[就绪] 机械臂、夹爪和关节状态接口均已发现。"
echo "[3/3] 正在启动带夹爪的 MoveIt2 / RViz2..."
setsid ros2 launch piper_with_gripper_moveit piper_moveit.launch.py &
MOVEIT_PID=$!
record_process_group "$MOVEIT_PID" "MoveIt2"
MOVEIT_PGID="$RECORDED_PGID"

sleep 3
kill -0 "$MOVEIT_PID" 2>/dev/null || fail "MoveIt2启动后立即退出，请查看上方日志。"

echo
echo "=========================================="
echo " 仿真已启动"
echo " 请保持本终端打开；按 Ctrl+C 统一关闭。"
echo "=========================================="

while true; do
    kill -0 "$GAZEBO_PID" 2>/dev/null || fail "Gazebo意外退出。"
    kill -0 "$MOVEIT_PID" 2>/dev/null || fail "MoveIt2意外退出。"
    sleep 1
done
