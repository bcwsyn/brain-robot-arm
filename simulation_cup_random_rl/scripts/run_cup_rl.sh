#!/usr/bin/env bash
set -Eeuo pipefail
CUP_RL_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CUP_RL_WS"
if [[ ! -x .venv-rl/bin/python || ! -f rl/assets/piper_cup.xml ]]; then
    echo 'Run setup_cup_rl_env.sh and build_cup_rl_model.py first.' >&2
    exit 1
fi
export PYTHONNOUSERSITE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
exec .venv-rl/bin/python -s scripts/train_cup_rl.py "$@"
