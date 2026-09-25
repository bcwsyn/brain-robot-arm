#!/usr/bin/env bash
# Install a deliberately narrow passwordless helper and its persistent timer.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HELPER_SOURCE="${SCRIPT_DIR}/brain_robot_log_maintenance_root.sh"
SERVICE_SOURCE="${SCRIPT_DIR}/brain-robot-log-maintenance.service"
TIMER_SOURCE="${SCRIPT_DIR}/brain-robot-log-maintenance.timer"
HELPER_TARGET="/usr/local/sbin/brain-robot-log-maintenance"
SUDOERS_TARGET="/etc/sudoers.d/brain-robot-log-maintenance"
SERVICE_TARGET="/etc/systemd/system/brain-robot-log-maintenance.service"
TIMER_TARGET="/etc/systemd/system/brain-robot-log-maintenance.timer"
ACCOUNT_NAME="${USER}"

[[ -f "$HELPER_SOURCE" && -f "$SERVICE_SOURCE" && -f "$TIMER_SOURCE" ]] || {
  echo "[错误] 未找到维护脚本或 systemd 模板：$SCRIPT_DIR" >&2
  exit 1
}
[[ "$ACCOUNT_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || {
  echo "[错误] 当前账户名不符合 sudoers 安全格式。" >&2
  exit 1
}

echo "[说明] 安装固定路径的日志维护助手和每 10 分钟运行的 systemd timer。"
sudo -n install -o root -g root -m 0755 "$HELPER_SOURCE" "$HELPER_TARGET"
printf '%s ALL=(root) NOPASSWD: %s ""\n' "$ACCOUNT_NAME" "$HELPER_TARGET" |
  sudo -n tee "$SUDOERS_TARGET" >/dev/null
sudo -n chmod 0440 "$SUDOERS_TARGET"
sudo -n chown root:root "$SUDOERS_TARGET"
sudo -n visudo -cf "$SUDOERS_TARGET"
sudo -n install -o root -g root -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
sudo -n install -o root -g root -m 0644 "$TIMER_SOURCE" "$TIMER_TARGET"
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now brain-robot-log-maintenance.timer
sudo -n "$HELPER_TARGET"
echo "[完成] 已安装受限免密日志维护和持久 timer：brain-robot-log-maintenance.timer。"
