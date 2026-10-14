# Piper 仿真工作区

2026-10-15 第六步随机起终点水杯取放20/20通过，最大三维误差1.331 mm；新增独立SAC+HER物理训练环境，19项RL检查通过。5000步冻结策略独立评价0/20，尚未收敛。最新范围、测试结果与模型尚未收敛的边界见[中文阶段报告](../docs/第六步_随机起终点抓放基准与强化学习环境验收.md)；[中文复现](../docs/random_cup_rl/README.zh-CN.md) / [English guide](../docs/random_cup_rl/README.en.md)。

最新倾角修正：Gemini 2 光轴朝夹爪中心偏转约19.81°，与法兰参考平面约70.19°，观察位关节5改为0.15 rad；75 mm A/B两轮通过，96项核心检查通过。详见[倾角报告](../docs/第五步补充_腕部相机倾角修正与验证.md)。

2026-10-14 最新安装与视觉更新：本入口使用单台 Gemini 2 腕部相机，法兰前约 30 mm、距指尖轴向 105 mm；Gazebo/MoveIt 共用安装模型，水杯 RGB、深度、YOLO 和估径全部来自腕部。固定代码 75 mm 水杯 A/B 两轮通过，96 项核心检查通过。GitHub 新发布目录为 `simulation_cup_wrist/`，固定相机版本保留在 `simulation_cup_grasp/`。请按[中文复现指南](../docs/wrist_camera/README.zh-CN.md) / [English guide](../docs/wrist_camera/README.en.md) 操作；[补充报告](../docs/第五步补充_单腕部Gemini2相机安装与视觉接入.md)说明近距离深度盲区与未重新验收范围。

[水杯中文复现指南](../docs/cup_simulation/README.zh-CN.md) · [Cup reproduction guide](../docs/cup_simulation/README.en.md) · [Cup stage report](../docs/stage4_cup_training_report.en.md)。原第三步说明见[物理仿真指南](../docs/simulation/README.zh-CN.md)。`scripts/build_simulation.sh` 提供工作区隔离构建，启动入口自动执行只读环境自检。

2026-10-14 水杯训练与视觉估径组件已验证：杯身 75 mm × 160 mm、杯口外径 63 mm × 40 mm，空、不透明、无把手；默认夹爪按用户确认的官方大夹爪版本修正为 100 mm。已完成两轮 YOLO 训练、学习掩膜 RGB-D 估径、只读 ROS 接口及自适应夹持策略离线测试。**第四步当时尚未完成完整水杯力控取放验收**；最新集成状态见上方说明。本机目录为 `simulation/`，GitHub 独立发布为 `simulation_cup/`，旧版保持原目录。详见[第四步报告](../docs/第四步_水杯训练与自适应夹持基础验证.md)、[中文指南](../docs/cup_simulation/README.zh-CN.md)与[English guide](../docs/cup_simulation/README.en.md)。推荐权重已保存在 `models/`，全部数据与训练修订有校验归档。

2026-10-13 独立 `physics_grasp` 模式已验收：小球和圆柱体各 20/20 随机物理取放通过，依靠物品重力、接触和摩擦完成夹持及释放；新增接触、实际保持和失物检查。采用简化指垫与理想机械臂重力补偿，范围和版本记录见[第三步报告](../docs/第三步_物理抓取开发与验收.md)。此前小球 10/10、圆柱体 10/10 的随机跟随式流程记录见[第二步报告](../docs/第二步_随机视觉取放开发与验收.md)。

源码来自 `brain-robot-arm@6ebd0c53ca83`，已分类导入。2026-10-11 已完成 7 个包构建、39 个算法单元测试和默认小球/圆柱体运行检查，当时默认抓取流程未通过验收。2026-10-12 已修复控制交接并实现完整取放，四个静态起点的小球 20/20、圆柱体 20/20 跟随式流程试验通过。失败处理与详细结果见[第一步开发与验收](../docs/第一步_单物品闭环开发与验收.md)。目标为 ROS 2 Humble；当前配置使用 **Gazebo Classic**，不能直接按 Fortress 插件启动。

## 内容

| 路径 | 用途 |
| --- | --- |
| src/piper_description | 机器人 URDF/Xacro、网格、坐标与可视化资源 |
| src/piper_msgs | Piper 消息与服务定义 |
| src/piper_with_gripper_moveit | 带夹爪 MoveIt 配置 |
| src/piper_no_gripper_moveit | 不带夹爪 MoveIt 配置 |
| src/piper_gazebo | Gazebo 控制器和夹爪镜像脚本 |
| src/brain_robot_pick_place | 桌面场景、固定取放、RGB-D 检测、视觉搜索和抓取执行 |
| src/brain_robot_ball_pick | 红球仿真场景与检测/搜索配置 |
| scripts/ | 已将默认路径改为当前工作区的仿真启动与只读监控脚本 |
| optional_src/ | MuJoCo 参考包，由 `COLCON_IGNORE` 排除，暂不参与构建 |

此工作区没有 Piper CAN 驱动、真机 jog 适配器或实体相机驱动。控制器与抓取执行器副本会拒绝选择真实硬件后端；`physics_grasp` 仍使用 Gazebo 虚拟控制器。依然应与真实机器人使用独立终端/ROS 会话，不能连接或加载真实驱动。

## 第五步：水杯视觉估径与力反馈物理取放

在已构建并配置 `.venv-yolo` 的本工作区运行 `bash scripts/run_cup_grasp_sim.sh --seed 20261015`。启动 Gazebo/RViz 和大幅力反馈画面；在启动终端按 `1/2` 选区、`S` 开始、完成后 `R` 重建下一随机场景、`X` 停止、`Q` 退出，不用回车。

相机估计未知局部外径并决定预张开，单开口对称夹爪根据每侧 2.5–3.5 N 的仿真接触反馈闭合/保持。支持 55/75/85 mm 样品试验、锁定 RGB-D/掩膜/标定存档和故障验证。骨干控制与桥接检查 91 项汇总通过；最终固定批次及发布核验见[第五步报告](../docs/第五步_水杯视觉估径与力反馈抓取开发与验收.md)，[中文操作指南](../docs/cup_grasp/README.zh-CN.md) / [English guide](../docs/cup_grasp/README.en.md)。

GitHub 新版本位于独立 `simulation_cup_grasp/`；原 `simulation/`、`simulation_cup/` 和 `brain_robot_arm/` 保留。不要在多个同名包工作区之间混合构建或 source。

## 水杯视觉回放：一个终端观看识别与估径

已有 `.venv-yolo/` 时运行 `bash scripts/run_cup_visual_replay.sh`。首次配置先执行 `bash scripts/setup_cup_vision_env.sh`，桌面需有 `python3-tk`。此入口无需构建 ROS：重新计算五视角 YOLO 掩膜和 RGB-D 外径，窗口显示原图、掩膜、深度、抓取点及建议开口。`1–5` 或方向键切换视角，空格播放/暂停，保存按钮导出图，`Q/Esc` 退出。每次结果保存于新的 `log/cup_visual_replay.XXXXXX/`。

该入口回放保存的相机数据，尚未执行水杯夹持或显示闭环接触力。完整命令及窗口截图见[中文指南第 4 节](../docs/cup_simulation/README.zh-CN.md#4-可视化回放与模型检查)和[English guide](../docs/cup_simulation/README.en.md#4-visual-replay-and-model-checks)。

## 球/圆柱物理演示：一个终端观看相机取放

在本目录直接运行 `./scripts/run_ball_physics_sim.sh`（小球）或 `./scripts/run_cylinder_physics_sim.sh`（圆柱体）。程序自动加载环境、Gazebo、MoveIt、RViz 相机画面、接触传感器、几何中心估计和视觉任务，等待按键开始；不需要另外开终端或安装依赖。原 `run_ball_visual_sim.sh`、`run_cylinder_visual_sim.sh` 继续提供关闭物品重力的跟随式流程演示。

目标起点随机生成；`1/2` 选择 A/B 放置区，`S` 开始，`R` 在完成后随机复位再抓，`X` 停止，`Q` 或 `Ctrl+C` 统一退出，不用回车。运行中不允许改放置区、复位或重复开始；停止/故障后 `R` 会重新加载本次仿真。一次只运行一个入口，日志位于 `log/visual_sim/`。

物理模式操作、状态说明和复现方法见[第三步报告第 5 节](../docs/第三步_物理抓取开发与验收.md#5-一个终端如何操作)。流程模式的多终端调试说明见[第一步报告第 5.2 节](../docs/第一步_单物品闭环开发与验收.md#52-推荐一个终端按键完成整套可视化仿真)。

使用 `--seed 20261013` 可重现本次物理验收的随机起点顺序。两个物理入口支持 `--headless --batch-trials 20`，会自动执行虚拟机械臂动作，必须依次运行。物理记录位于 `validation/physics_grasp/`，使用 `scripts/analyze_physics_grasp.py` 导出；旧流程定位/验收见[随机视觉取放报告](../docs/第二步_随机视觉取放开发与验收.md)及 `validation/visual_randomization/`。两个模式不可混用统计工具。

## 构建与验证

主要依赖包括 ROS 2 Humble、MoveIt 2/Servo、ros2_control/轨迹控制器、Gazebo Classic 的 ROS 插件、OpenCV、cv_bridge、TF 和消息同步。已有依赖能完成编译和启动，但本机 Pilz 与 MoveIt 核心版本不一致、CHOMP 缺库；存在 Python 用户目录 NumPy 2 与 ROS cv_bridge 的兼容问题。现已明确仅启用 OMPL。历史失败与修复验收见下方报告，未安装或修改系统依赖。

安装依赖需另行批准。准备就绪后，仅在本目录构建：

```bash
cd /home/young1x/robot_projects/piper_robot/simulation
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

已有检查命令：`colcon test --packages-select brain_robot_pick_place`、`colcon test-result --test-result-base build/brain_robot_pick_place --verbose`。第四步历史为 69 个算法用例/9 个 CTest、汇总78项；第五步当前为81个算法/桥接用例及10个CTest，汇总91项、0失败/错误/跳过。全工作区上游版权/格式检查的已知失败另行记录。原球/圆柱控制交接、实测起点重算、物理接触保持及释放回零已实现；水杯端到端结果以第五步固定物理验收和原始数据为准。

`start_piper_sim.sh` 将加载虚拟控制器、Gazebo 与 MoveIt；`start_brain_robot_demo.sh` 增加红杯场景、检测与搜索；红球演示在另一个脚本中。原验收使用单独的有界验证脚本；当前交互演示优先使用上方两个新入口。启动前应说明具体程序与运动效果；历史脚本的宽泛旧进程自动清理调用已改为检测冲突后退出。

`scripts/validate_sim_grasp.py` 支持 `ball`、`cup-known`、`cup-vision`，原始基线记录在 `validation/runs/`，第一步开发与验收记录在 `validation/step1/`。支持 `--repetitions`、`--scene-params-file` 和 `--negative-case`；`run_step1_trials.py` 按保存的计划重复测试，遇到失败立即停下并保留结果。`validation/grasp_validation.world` 提供实际物品状态观测；小球冻结跟踪配置仅用于对照，不覆盖默认配置。无窗口入口为 `wrist_camera_gazebo.launch.py gui:=false` 和 `piper_moveit.launch.py start_rviz:=false`；默认仍显示窗口。无窗口 Gazebo 的 RGB-D 渲染仍需可用的图形渲染环境。

第一步实现、验收判据和新复现命令见[第一步开发与验收](../docs/第一步_单物品闭环开发与验收.md)。历史基线、证据链接与后续分阶段研发任务见[仿真验证及下一步规划](../docs/小球与圆柱体仿真验证及下一步规划.md)。

包内原 README 与 `UPSTREAM_SIM_README.md` 保留上游说明，旧路径和命令仅供参考，以本工作区说明为准。`flow_demo` 与 `physics_grasp` 必须恰好开启一个；物理场景禁止启动跟随。本轮物理样品为直径 35 mm/15 g 小球及直径 50 mm、高 100 mm/80 g 实心圆柱；流程圆柱体仍为 70 mm。位置 PID 参数仅用于当前仿真模型。

源码来源与适配说明见[源码归属记录](UPSTREAM_PROVENANCE.md)，后续任务见[仿真规划](../docs/小球与圆柱体仿真验证及下一步规划.md)。
