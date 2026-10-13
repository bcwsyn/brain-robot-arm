#!/usr/bin/env bash
# One-terminal, camera-based cylinder simulation.
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/run_visual_sim.sh" cylinder "$@"
