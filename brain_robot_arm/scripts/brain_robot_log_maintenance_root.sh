#!/usr/bin/env bash
# Root-only helper. It deliberately accepts no arguments so its sudoers entry
# cannot be repurposed to operate on arbitrary files.
set -Eeuo pipefail

if (( $# != 0 )); then
  echo "This maintenance helper accepts no arguments." >&2
  exit 2
fi

ROTATED_LOG_LIMIT_MB=200
JOURNAL_LIMIT_MB=200
APP_LOG_DIR=/home/johnwick/brain_robot_logs
APP_LOG_LIMIT_MB=20
APP_LOG_RETENTION_DAYS=3

# The timer and the startup guard may overlap.  A non-blocking lock makes the
# helper idempotent and prevents two vacuum/truncate passes from racing.
exec 9>/run/lock/brain-robot-log-maintenance.lock
flock -n 9 || exit 0

find /var/log -maxdepth 1 -type f \
  \( -name 'syslog*' -o -name 'kern.log*' \) \
  -size "+${ROTATED_LOG_LIMIT_MB}M" -exec truncate -s 0 {} \;
journalctl --vacuum-size="${JOURNAL_LIMIT_MB}M"
journalctl --vacuum-time=14d

# Keep the fixed robot application log directory bounded even when the robot
# launcher is not running.  This path is deliberately not user-controlled.
if [[ -d "$APP_LOG_DIR" ]]; then
  find "$APP_LOG_DIR" -xdev -type f -name '*.log' \
    -mtime "+${APP_LOG_RETENTION_DAYS}" -delete
  find "$APP_LOG_DIR" -xdev -type f \( -name '*.log' -o -name '*.log.*' \) \
    -size "+${APP_LOG_LIMIT_MB}M" -exec truncate -s 0 {} \;
fi
