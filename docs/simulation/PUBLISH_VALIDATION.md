# GitHub publication verification / GitHub 发布复现检查

Date / 日期：2026-10-14。Original stage acceptance / 原阶段验收：2026-10-13。

## What was verified / 验证范围

The published source was copied into a fresh checkout under `/tmp/piper-stage3-publish/simulation`, initially without `build/`, `install/` or `log/`. Every published package was compiled there with the existing system Humble dependencies. No original robot-workspace overlay was sourced during build or smoke tests. This checks source/resource completeness and relocation on the validated machine; it is not a fresh OS installation or a guarantee for arbitrary graphics drivers or ROS versions.

发布源码放入新的仓库检出目录，最初没有 build/install/log；仅使用现有系统 Humble 依赖，重新编译全部七个包。构建和试运行未加载原机器人工作区。验证证明当前机器上的源码、资源和路径完整性，不等同于重装系统测试，也不对任意驱动/ROS 版本作无条件保证。

| Check / 检查 | Result / 结果 | Evidence / 证据 |
| --- | --- | --- |
| Fresh seven-package build / 七包干净构建 | Passed, approximately 1 min 51 s / 通过，约 1 分 51 秒 | [build](../../simulation/validation/physics_grasp/publish_clean_build.txt) |
| Dependencies after manifest cleanup / 依赖声明修复后 | rosdep: all dependencies satisfied / 全部满足 | [rosdep](../../simulation/validation/physics_grasp/publish_rosdep_check.txt) |
| Manifest rebuild / 依赖声明重构建 | Seven packages passed / 七包通过 | [rebuild](../../simulation/validation/physics_grasp/publish_manifest_build.txt) |
| Algorithm cases / 算法用例 | 45 GTest + 4 Python, zero failures / 49 个全部通过 | [49-case summary](../../simulation/validation/physics_grasp/publish_algorithm_summary.txt) |
| CTest-inclusive total / 含 CTest 汇总 | 56, zero errors/failures/skips / 全部通过 | [56-result summary](../../simulation/validation/physics_grasp/publish_algorithm_summary_full.txt) |
| Relocated ball physics / 新目录小球物理取放 | 1/1; lift 14.30 cm, place error 0.51 mm, sampled hold 3.20 simulated seconds | [results](../../simulation/validation/physics_grasp/publish_smoke_results.json) |
| Relocated cylinder physics / 新目录圆柱物理取放 | 1/1; lift 14.47 cm, place error 20.06 mm, sampled hold 3.10 simulated seconds | [results](../../simulation/validation/physics_grasp/publish_smoke_results.json) |
| GUI ball, R reset, Q / 小球窗口取放及复位退出 | 1/1; lift 14.04 cm, place error 0.38 mm; new random scene ready; parent exit 0 and groups cleaned | [results](../../simulation/validation/physics_grasp/publish_smoke_results.json) |
| Final environment / 最终环境自检 | Passed; local package prefixes resolve to publication install/ / 全部通过 | [preflight](../../simulation/validation/physics_grasp/publish_final_preflight.txt) |

The ball headless smoke preserved one pre-motion fresh-joint refusal. No moving trial was retried. These three publication trials are supplemental and do not increase either historical twenty-trial acceptance denominator. Detailed publication sessions are in `simulation/validation/physics_grasp/publish_raw_sessions.tar.gz`; the original eight sessions are in `raw_sessions.tar.gz`.

新目录小球无窗口试验保留了一次运动前新鲜关节反馈拒绝，没有重试已运动试验。三轮发布回归与历史两组各 20 轮分别统计。发布原始会话与历史会话使用不同归档，不能混合成功率。

## Changes for reproduction / 为复现增加的改动

- Read-only environment preflight: system Python/NumPy, ROS packages, Gazebo plugins, local overlay, display and session port. Startup reports failed prerequisites before launching the simulation.
- Isolated sequential build script with two compilation jobs and explicit system Humble sourcing.
- Explicit Fast DDS selection in the launcher, matching the validated runtime's default middleware.
- Corrected Gazebo/controller runtime dependencies. Removed the mandatory legacy MongoDB plugin from the two MoveIt manifests; the optional warehouse launch still needs separate database setup.
- Full seven-package source, both camera modes, the world/UDP profile/RViz resources, bilingual guides and stage reports, CSVs and versioned raw evidence.

对应中文说明：只读自检、隔离构建、明确 Fast DDS、补齐 Gazebo 控制器依赖、移出可选数据库插件，以及完整源码/场景/图形配置/双语报告/验收证据。没有更改本阶段抓取执行器或几何拟合算法；历史源码和二进制哈希仍描述各自验收版本。

Historical content under `brain_robot_arm/` remains intact. The new workspace does not contain or launch real drivers. No system packages were installed, no `/etc` or system networking was changed, and no physical robot was operated during publication verification.

原仓库历史目录保留；新增工作区没有真实驱动。本次发布验证未安装系统依赖、修改 `/etc` 或系统网络，也未控制真实机械臂。
