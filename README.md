# ub Workspace

## Latest: Stage 3 physical simulation / 最新：第三阶段物理仿真

The independent [simulation/](simulation/README.md) workspace contains the latest camera-guided ball/cylinder physical grasp implementation. Start with the [English installation and reproduction guide](docs/simulation/README.en.md) and [English acceptance report](docs/stage3_physical_grasp_report.en.md).

新增独立 [simulation/](simulation/README.md) 工作区，包含最新的小球/圆柱体相机物理取放；请按[中文安装与运行指南](docs/simulation/README.zh-CN.md)构建，验收与模型边界见[第三步阶段报告](docs/第三步_物理抓取开发与验收.md)。从 `simulation/` 构建；仓库根目录及下方历史目录含同名包。The historical workspace below is preserved; do not build both trees together.

This repository is the complete `C:\ub` workspace snapshot. The main project is under `brain_robot_arm/` and contains PiPER robotic-arm experiments, ROS 2 workspaces, camera and vision components, simulation demos, real-arm control scripts, and related design documents.

## Main directories

- `brain_robot_arm/`: robotic-arm project source, ROS 2 packages, scripts, and documentation.
- `tmp/`: workspace experiment and rendering artifacts retained from the original workspace snapshot.
- `.agents/`: workspace-local agent configuration, when present.

## Safety

Simulation, vision, and real-arm control must remain separately validated. Before operating a physical arm, verify camera extrinsics, joint limits, speed limits, workspace limits, emergency stop behavior, and explicit operator confirmation. Do not unlock an unattended full grasp sequence based only on simulation success.

## Repository scope

Git metadata, local caches, Python bytecode, ROS 2 build output, runtime logs, and the local Conda installer are excluded. Third-party source and license files under `brain_robot_arm/vendor/` are retained with the workspace snapshot.
