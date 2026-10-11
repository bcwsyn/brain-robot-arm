---
name: ros2-piper-debug
description: Use when diagnosing or changing ROS 2 Humble nodes, topics, QoS, TF, MoveIt, Servo, or the PiPER runtime in this repository. Prefer repository evidence over generic ROS recipes.
---

# ROS 2 and PiPER debugging

Use this only for ROS 2/runtime work. It does not replace the repository's handoff, progress, safety, or Git rules in `AGENTS.md`, `CODEX_TASK_PROMPT.md`, and `CODEX_HANDOFF.md`.

1. Trace the exact runtime path before editing: launch script, sourced overlays, package source, installed executable/config, process arguments, ROS graph, and relevant logs. Distinguish canonical repository files from deployed files under `/home/johnwick`; verify hashes when synchronization matters.
2. State the observed failure and the evidence that would distinguish likely causes. Inspect the smallest useful set of node logs, topic publisher/subscriber/QoS data, message timestamps/frame IDs, TF availability at the message timestamp, and process state. A stale or transient CLI discovery result alone does not establish runtime failure.
3. For TF, compare sensor message stamp, lookup time, and latest transform. Preserve exact sensor timestamps where required; do not silently substitute latest TF or change clock/QoS behavior just to make a gate pass.
4. For point clouds and MoveIt, establish actual input/output topics, publishers, QoS, frame IDs, and whether filtering/Octomap consumers are alive. A node or service existing does not prove valid data flow.
5. Treat RMW/DDS, QoS, ROS domain IDs, daemon restarts, and transport variables as project-specific. Read current launch/config and `docs/PIper_DECISIONS.md`. Never apply a generic CycloneDDS/FastDDS, localhost-only, QoS, or daemon-reset recipe without evidence it addresses this failure.
6. Make the smallest change addressing the evidenced cause. Prefer existing conventions and focused tests/builds; do not broaden into unrelated graph cleanup or architecture work.
7. Report verification at its actual level: syntax/build, node startup, live message flow, timestamp-complete TF, filtered cloud/Octomap, and end-to-end behavior are distinct. Record command, return code, evidence path, and unverified items in `docs/PIper_PROGRESS.md`.

For real-arm behavior, follow repository authorization, feedback, limit, support, and stop requirements. A successful ROS service response or planned trajectory alone is not proof of safe or successful movement.

## Source

Informed by the ROS 2 skill in [robotics-agent-skills](https://github.com/arpitg1304/robotics-agent-skills/tree/main/skills/ros2), narrowed to this project's ROS 2 Humble/PiPER evidence and decisions. Not a verbatim copy.
