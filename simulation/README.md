# Piper Stage 3 Simulation / Piper 第三阶段仿真

[中文安装、构建与运行指南](../docs/simulation/README.zh-CN.md) · [English installation and reproduction guide](../docs/simulation/README.en.md)

[中文阶段报告](../docs/第三步_物理抓取开发与验收.md) · [English stage report](../docs/stage3_physical_grasp_report.en.md)

Independent ROS 2 Humble / Gazebo Classic 11 workspace. Build and run here, not at the repository root. Seven source packages, scene resources, RViz layout, physical/flow entry points and acceptance evidence are included; no build/install/log artifacts are shipped.

这是独立 ROS 2 Humble / Gazebo Classic 11 工作区。请在本目录构建和运行，仓库历史目录包含同名包。包含七个源码包、场景、RViz 配置、物理/流程入口及验收证据，不提供预编译输出。

```bash
# After installing the dependencies in the guide / 先按指南安装依赖
bash scripts/build_simulation.sh
bash scripts/run_ball_physics_sim.sh --seed 20261013
# Quit the ball session with Q before starting the cylinder / Q 退出后再运行圆柱体
bash scripts/run_cylinder_physics_sim.sh --seed 20261013
```

Wait for ready, select 1/2, S starts, R resets, X stops, Q quits; no Enter needed. 等待就绪，1/2 选放置区，S 开始，R 复位，X 停止，Q 退出，无需回车。

Physical simulation uses object gravity/contact/friction, simplified pads and ideal arm gravity compensation. It is not a real-hardware acceptance result. 两种物品各 20/20 历史物理仿真取放通过；两个批次的版本分别保留，不能算作同一二进制的 40 轮。模型与统计边界详见阶段报告。

Primary source / 主要源码: scripts/visual_sim_console.py, src/brain_robot_pick_place/scripts/physics_target_node.py, src/brain_robot_pick_place/src/grasp_lift_executor.cpp. Evidence / 证据: validation/physics_grasp/. System dependency instructions are documented; scripts do not install system packages or load real drivers.
