#!/usr/bin/env bash
# Project-only Python dependencies. No system package or hardware changes.
set -Eeuo pipefail
CUP_RL_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONNOUSERSITE=1
if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo 'Deactivate Conda first.' >&2
    exit 1
fi
if [[ ! -x "$CUP_RL_WS/.venv-rl/bin/python" ]]; then
    /usr/bin/python3 -s -m venv --without-pip --system-site-packages "$CUP_RL_WS/.venv-rl"
fi
"$CUP_RL_WS/.venv-rl/bin/python" -s -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu
"$CUP_RL_WS/.venv-rl/bin/python" -s -m pip install -r "$CUP_RL_WS/config/cup_rl_requirements.txt"
echo 'Private CPU RL environment ready; vision environment unchanged.'
