#!/usr/bin/env bash
# One-terminal, camera-based physical red-ball grasp simulation.
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/run_visual_sim.sh" ball --physics "$@"
