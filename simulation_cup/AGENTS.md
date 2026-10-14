# Piper Simulation Workspace

## Mission

This directory contains the Piper robot simulation project.

Target environment:
- Ubuntu 22.04.5 LTS
- ROS 2 Humble
- Gazebo simulation and RViz visualization

## Scope

- Work on files under simulation/ by default.
- Put ROS 2 source packages in simulation/src/.
- Run colcon build from simulation/.
- Keep build/, install/ and log/ as generated outputs.

## Rules

- Start with simulation and mock components.
- Do not connect to real robot hardware.
- Do not use real serial, USB or CAN hardware interfaces.
- Do not modify files under real_robot/ unless explicitly requested.
- Inspect existing code before making changes.
- Explain dependencies and test commands.
- Do not launch long-running simulations without explaining what will start.
