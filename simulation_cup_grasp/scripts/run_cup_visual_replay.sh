#!/usr/bin/env bash
# Recompute learned RGB-D estimates, then open a read-only five-view viewer.
set -Eeuo pipefail
CUP_REPLAY_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CUP_REPLAY_WS"
if [[ ! -x .venv-yolo/bin/python ]]; then
    echo "请先运行 / First run: bash scripts/setup_cup_vision_env.sh" >&2
    exit 1
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "需要桌面终端 / A desktop display is required. Headless check: scripts/evaluate_cup_holdout.py" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1
export YOLO_CONFIG_DIR="$CUP_REPLAY_WS/artifacts/yolo/config"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
if ! .venv-yolo/bin/python -s -c 'import tkinter; root = tkinter.Tk(); root.withdraw(); root.destroy()'; then
    echo "请检查桌面 DISPLAY 和 python3-tk / Check the desktop display and python3-tk." >&2
    exit 1
fi
mkdir -p log
CUP_REPLAY_SESSION="$(mktemp -d "$CUP_REPLAY_WS/log/cup_visual_replay.XXXXXX")"
echo "重新运行 YOLO 和 RGB-D 估径 / Running YOLO and RGB-D sizing..."
echo "本次记录 / Session: $CUP_REPLAY_SESSION"
if ! .venv-yolo/bin/python -s scripts/evaluate_cup_holdout.py \
    --capture validation/cup_vision/stepped_cup_probe \
    --model models/cup_yolov8n_seg_v2.pt \
    --output "$CUP_REPLAY_SESSION/inference" > "$CUP_REPLAY_SESSION/evaluation.log" 2>&1; then
    cat "$CUP_REPLAY_SESSION/evaluation.log" >&2
    exit 1
fi
echo "五视角估径通过 / Five views passed. 窗口按 1–5 切换，空格播放，Q 退出。"
exec .venv-yolo/bin/python -s scripts/cup_visual_replay.py \
    --capture validation/cup_vision/stepped_cup_probe \
    --results "$CUP_REPLAY_SESSION/inference" "$@"
