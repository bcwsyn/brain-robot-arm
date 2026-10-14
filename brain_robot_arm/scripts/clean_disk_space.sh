#!/usr/bin/env bash
# Safe disk-space cleanup for the PiPER ROS2 VM.
# Does not remove source code, ROS build/install directories, or conda packages.
set -Eeuo pipefail

THRESHOLD_PERCENT="${DISK_CLEAN_THRESHOLD:-85}"
APP_LOG_LIMIT_MB="${DISK_APP_LOG_LIMIT_MB:-20}"
APP_LOG_DIR="${BRAIN_ROBOT_LOG_DIR:-$HOME/brain_robot_logs}"

usage_percent() {
  df --output=pcent / | tail -n 1 | tr -dc '0-9'
}

before="$(usage_percent)"
echo "清理前根分区使用率：${before}%"

echo "[1/4] 清理 ROS 日志..."
rm -rf "${HOME}/.ros/log"/* 2>/dev/null || true
find "$APP_LOG_DIR" -type f -name '*.log' -mtime +3 -delete 2>/dev/null || true
find "$APP_LOG_DIR" -type f \( -name '*.log' -o -name '*.log.*' \) \
  -size +"${APP_LOG_LIMIT_MB}M" -exec truncate -s 0 {} \; 2>/dev/null || true

# User-authorized runtime image retention. Text-log rotation does not cover PNGs.
# This helper is restricted to brain_robot_logs and preserves documented frames,
# all images younger than 24h, and first/last/sparse samples. No source/model deletion.
CAPTURE_IMAGE_PRUNER="/home/johnwick/prune_capture_images.py"
if [[ -f "$CAPTURE_IMAGE_PRUNER" ]]; then
  /usr/bin/python3 "$CAPTURE_IMAGE_PRUNER" \
    --limit-mb "${DISK_CAPTURE_IMAGE_LIMIT_MB:-8192}" --apply || \
    echo "[图片] 保留策略检查失败，未改用递归删除或扩大范围。"
else
  echo "[图片] 未安装受限图片保留助手；仅完成原文本日志清理。"
fi

echo "[2/4] 清理超大的轮转系统日志..."
MAINTENANCE_HELPER="/usr/local/sbin/brain-robot-log-maintenance"
if [[ -x "$MAINTENANCE_HELPER" ]]; then
  if sudo -n "$MAINTENANCE_HELPER"; then
    echo "[系统日志] 已通过受限免密维护助手完成。"
  else
    echo "[系统日志] 维护助手执行失败；本脚本不会改用通用 sudo 或要求输入密码。"
  fi
else
  echo "[系统日志] 未清理：尚未安装受限免密维护，且本脚本不会弹出 sudo 密码输入。"
  echo "[系统日志] 首次执行：~/install_brain_robot_log_maintenance.sh"
fi

echo "[3/4] systemd 日志已包含在上一步受限维护中（若已安装）。"

echo "[4/4] 清理 apt 缓存..."
if sudo -n apt clean; then
  echo "[apt] 已清理缓存。"
else
  echo "[apt] 未清理：apt 缓存不在受限日志维护白名单内；如确有需要请手动执行 sudo apt clean。"
fi

after="$(usage_percent)"
echo "清理后根分区使用率：${after}%"

if (( after >= THRESHOLD_PERCENT )); then
  echo "警告：根分区仍使用 ${after}%，未自动删除 ROS build/install/log 或 Conda 文件。"
  echo "如需进一步处理，请先检查：du -xhd1 /var /home 2>/dev/null | sort -h"
else
  echo "清理完成，当前低于 ${THRESHOLD_PERCENT}% 阈值。"
fi
