# ub Workspace

2026-10-14 最新倾角更新 / Latest camera-tilt update: `simulation_cup_wrist/` now tilts the wrist camera19.81° towards the gripper centre (70.19° to flange plane). [中文报告](docs/第五步补充_腕部相机倾角修正与验证.md) / [English report](docs/stage5_wrist_camera_tilt_update.en.md). 未倾斜版本由原标签保留；四个更早的工作区完整保留。

## Latest: single wrist-mounted Gemini 2 / 最新：单腕部相机

New independent [simulation_cup_wrist/](simulation_cup_wrist/README.md) uses one moving wrist RGB-D camera for cup detection, sizing and physical force-feedback grasp simulation. The camera mount follows the supplied approximately 30 mm flange / 105 mm tip spacing. [English guide](docs/wrist_camera/README.en.md) · [Report](docs/stage5_wrist_camera_update.en.md).

最新版本使用单台Gemini 2腕部相机，已调整安装位置并统一所有水杯视觉输入。[中文复现](docs/wrist_camera/README.zh-CN.md) · [中文补充报告](docs/第五步补充_单腕部Gemini2相机安装与视觉接入.md)。固定代码75 mm A/B两轮通过、96项核心检查通过；其他尺寸/故障批次尚待腕部重验。此前 `simulation_cup_grasp/`、`simulation_cup/`、`simulation/`、`brain_robot_arm/` 都完整保留。

## Stage 5 fixed-camera release / 第五步固定相机保留版本

New independent [simulation_cup_grasp/](simulation_cup_grasp/README.md) connects learned RGB-D sizing, adaptive preopening and measured-force physical cup pick-and-place. Start with the [English guide](docs/cup_grasp/README.en.md) and [stage report](docs/stage5_cup_grasp_report.en.md).

最新版本新增独立 [simulation_cup_grasp/](simulation_cup_grasp/README.md)：相机估计杯身外径、保守预张开、双侧反馈夹持、物理取放与回零。[中文复现操作](docs/cup_grasp/README.zh-CN.md) / [第五步报告](docs/第五步_水杯视觉估径与力反馈抓取开发与验收.md)。原 `brain_robot_arm/`、第三步 `simulation/` 和第四步 `simulation_cup/` 完整保留；只构建所选工作区。


## Stage 3 physical simulation / 第三阶段物理仿真（保留版本）

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


## 2026-10-14: Cup training and RGB-D sizing / 水杯训练与视觉估径

New independent workspace: `simulation_cup/`. Previous `simulation/` and `brain_robot_arm/` remain available without source replacement. 已新增独立工作区，原目录和历史版本保留。

[中文复现指南](docs/cup_simulation/README.zh-CN.md) · [English guide](docs/cup_simulation/README.en.md) · [中文阶段报告](docs/第四步_水杯训练与自适应夹持基础验证.md) · [English report](docs/stage4_cup_training_report.en.md). Trained weights, both dataset/training revisions, raw RGB-D, checkpoints and checksummed archives are included. Integrated force-controlled cup pick-and-place remains pending. 完整水杯力控取放尚待集成，当前已验证训练、视觉估径、只读 ROS 接口和离线夹持策略。
