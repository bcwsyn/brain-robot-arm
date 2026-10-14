#!/usr/bin/env bash
# Installs only into the project venv; does not use sudo or install system packages.
set -Eeuo pipefail
CUP_VISION_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONNOUSERSITE=1
if ! /usr/bin/python3 -s -m pip --version >/dev/null 2>&1; then
    echo 'System python3-pip is required; install it using the documented prerequisite steps.' >&2
    exit 1
fi
if [[ ! -e "$CUP_VISION_WS/.venv-yolo/bin/python" ]]; then
    /usr/bin/python3 -s -m venv --without-pip --system-site-packages "$CUP_VISION_WS/.venv-yolo"
fi
"$CUP_VISION_WS/.venv-yolo/bin/python" -s -m pip install --index-url https://download.pytorch.org/whl/cpu \
    torch==2.6.0+cpu torchvision==0.21.0+cpu
"$CUP_VISION_WS/.venv-yolo/bin/python" -s -m pip install -r "$CUP_VISION_WS/config/cup_vision_requirements.txt"
mkdir -p "$CUP_VISION_WS/artifacts/yolo/config"
echo 'Private cup vision environment ready.'
