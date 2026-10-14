# Piper 第三阶段物理仿真：从下载到运行

[English](README.en.md) · [中文阶段报告](../第三步_物理抓取开发与验收.md) · [English stage report](../stage3_physical_grasp_report.en.md)

本指南对应仓库根目录新增的独立 `simulation/`，用于运行小球和实心圆柱体的相机物理取放。使用 Gazebo 接触和摩擦携带物品，松爪后由物品重力完成释放。现有 `brain_robot_arm/` 是历史工作区；本指南所有构建和运行命令都在新 `simulation/` 执行。

## 1. 支持的环境与验收范围

| 项目 | 要求 |
| --- | --- |
| 系统 | Ubuntu 22.04，已验证 22.04.5 amd64 |
| ROS | ROS 2 Humble，系统 Python 3.10 |
| 仿真器 | Gazebo Classic 11；不是 Fortress、Harmonic 或 Jazzy 的 Gazebo 接口 |
| 规划及控制 | MoveIt 2 的 OMPL、MoveIt Servo、ros2_control、Gazebo ROS 插件 |
| 图形 | 本机 Ubuntu 图形桌面，可访问的 `DISPLAY` 和 OpenGL；无窗口模式的 RGB-D 渲染也需要图形环境 |
| 资源 | 本机使用约 8 GB 显存的显卡，但不要求 CUDA；编译默认最多两个任务，运行速度取决于 CPU/图形能力 |

本阶段未接入 YOLO，无需下载网络权重。检测使用红色区域和 RGB-D 已知几何拟合。无需真实机械臂、CAN、实体相机或训练数据。

历史验收：小球和实心圆柱各 20/20 随机物理取放；每组 A/B 各 10 次，抓空、失物和抬升中停止检查通过。两批使用各自保留的版本，不能声称同一二进制完成 40 次。模型采用简化指垫及理想机械臂重力补偿，物品重力开启。详情见阶段报告。

## 2. 安装依赖

使用新的 Ubuntu Bash 终端，退出 Conda，不加载其他机器人工作区。若尚未安装 ROS 2 Humble，先按 [ROS 官方 Ubuntu 安装指南](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) 配置 ROS 软件源并安装 Humble。以下 `apt` 命令由使用者在自己的机器执行，会安装系统依赖；运行脚本不会自动安装软件。

```bash
sudo apt update
sudo apt install -y \
  git build-essential cmake libopencv-dev \
  python3-colcon-common-extensions python3-rosdep \
  python3-numpy python3-opencv python3-scipy python3-yaml python3-pytest python3-tk \
  ros-humble-desktop ros-humble-moveit ros-humble-moveit-servo \
  ros-humble-gazebo-ros-pkgs ros-humble-gazebo-ros2-control \
  ros-humble-ros2-control ros-humble-ros2-controllers \
  ros-humble-rmw-fastrtps-cpp ros-humble-cv-bridge ros-humble-xacro \
  ros-humble-ament-cmake-gtest ros-humble-ament-cmake-pytest
```

先检查 `/opt/ros/humble/setup.bash` 是否存在，再下载：

```bash
test -f /opt/ros/humble/setup.bash
cd ~
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation
```

如本机从未初始化 rosdep，执行一次 `sudo rosdep init`；若提示已经存在 source list，不要重复初始化。随后在 `simulation/` 执行：

```bash
source /opt/ros/humble/setup.bash
rosdep update --rosdistro humble
rosdep install --from-paths src --ignore-src --rosdistro humble -r -y
/usr/bin/python3 -s scripts/check_sim_environment.py
```

最后一条是只读检查，成功时输出 `Environment checks: PASSED`，不启动 ROS 节点或动作。它检查 Python 模块、MoveIt/Gazebo/控制器包以及必需的插件文件。缺少项须补齐后再编译。

不使用 `pip install numpy` 替代 Ubuntu 的 NumPy：本机 Humble `cv_bridge` 二进制使用 NumPy 1.x。入口固定使用系统 Python、`-s` 和 `PYTHONNOUSERSITE=1`，排除用户目录的 NumPy 2/Conda 干扰。已验证的软件版本清单位于 `simulation/validation/physics_grasp/publish_environment_packages.json`；它记录环境，不是需要逐项安装的锁文件。

## 3. 只构建独立仿真工作区

在 `brain-robot-arm/simulation` 执行：

```bash
bash scripts/build_simulation.sh
```

脚本清除其他 ROS overlay 的环境路径，加载 Humble，检查依赖，并以两个编译任务、顺序工作区执行器构建。应出现 `Summary: 7 packages finished`。七个包是：`piper_description`、`piper_msgs`、`piper_gazebo`、两个 Piper MoveIt 配置包、`brain_robot_pick_place`、`brain_robot_ball_pick`。

不要从整个仓库根目录运行 colcon：历史目录含同名包，会产生重复包或加载错误模型。每个工作区维护自己的 `build/`、`install/`、`log/`。下载包内没有预编译安装目录，必须在本机编译。

历史的 `warehouse_db.launch.py` 需要另行配置 `warehouse_ros_mongo`/MongoDB，不属于当前仿真入口。本次发布将它从必需依赖中移出，补齐 Gazebo 控制器依赖；上述 rosdep 步骤不需要安装数据库插件。

算法检查命令：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon test --packages-select brain_robot_pick_place --event-handlers console_direct+
colcon test-result --verbose
```

预期 45 个 GTest、4 个 Python 几何拟合用例通过，共 7 个 CTest 目标；colcon 汇总 56 项，0 错误/失败/跳过。若只统计该包的 `test_results/`，会显示 49 个算法用例；56 包含另外 7 个 CTest 目标，不是 56 个不同算法用例。这里只测试已验收的算法包；上游模型包的历史 lint 不纳入此数字。

## 4. 单终端观看物理取放

在图形桌面打开终端，进入 `simulation/`，以下两个入口择一运行：

```bash
bash scripts/run_ball_physics_sim.sh --seed 20261013
```

圆柱体：

```bash
bash scripts/run_cylinder_physics_sim.sh --seed 20261013
```

程序会自动加载本工作区、Gazebo、MoveIt、RViz 相机画面、场景、检测和中心拟合，并等待按键。默认不会自动运动。终端中的环境自检和 1/5 到 5/5 加载步骤完成后，应出现 `[就绪]`；Gazebo 中有机械臂、桌面和红色物品，RViz 显示机器人及相机画面。

| 按键（无需回车） | 行为 |
| --- | --- |
| `1` / `2` | 选择 A / B 放置区；默认 A |
| `S` | 开始一轮相机搜索、定位、抓取、搬运、释放和回零 |
| `R` | 正常完成后随机摆放新物品；停止/故障后重载本次仿真 |
| `X` | 请求停止当前动作，等待进入已停止状态 |
| `Q` / `Ctrl+C` | 停止并回收本程序启动的进程，恢复终端 |

不要把终端里的加载提示误当成已经就绪。运动中重复开始、复位或改变区域会被拒绝。按 `S` 后通常约 45–60 秒完成；较慢机器可能更久，单轮有 200 秒上限。成功应看到 `COMPLETE`、`GRASP_CONTROL_RELEASED` 和 `[完成]`，最后机械臂回零，物品实际位于所选区。

物理模式应出现双侧接触、`LIFTING_PHYSICAL_OBJECT`、`HOLDING_PHYSICAL_OBJECT`、搬运和真实释放检查。仅在画面里看到抬升，或仅收到 COMPLETE，不足以替代保存的数据判据。

原 `run_ball_visual_sim.sh` / `run_cylinder_visual_sim.sh` 是跟随式流程演示：物品重力关闭，不能算物理抓取。所有入口明确选择 Fast DDS、域 83、Gazebo 端口 11483和共享冲突检查；一次运行一个，不会终止他人的进程。

## 5. 无窗口自动试验和数据导出

以下会自动执行虚拟机械臂动作。第一次先各运行一轮；两个命令必须顺序执行：

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1
bash scripts/run_cylinder_physics_sim.sh --headless --seed 20261013 --batch-trials 1
```

`--headless` 只省略 Gazebo/RViz 窗口，深度相机仍需可用的图形渲染环境。这里验证的是本机图形桌面下的无窗口运行；没有将纯 SSH、无 X server 的服务器列为已验证环境。

完整重复计划：

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 20
bash scripts/run_cylinder_physics_sim.sh --headless --seed 20261013 --batch-trials 20
```

每组约 15–20 分钟，不保证跨机器耗时一致。随机起点位于 x=[0.38,0.42]、y=[-0.12,-0.08] m，A=(0.38,0.12)、B=(0.42,0.12) m 交替。运动失败立即停止整组并保留数据；只允许运动前“无新鲜关节反馈”的明确拒绝有界等待，绝不自动重试已失败的抓取。

每轮门槛：目标双侧接触；实际抬升至少 5 cm；保持采样覆盖至少 3 秒仿真时间；释放、退离后无指接触且落稳；最终位置距放置区小于 3 cm；六轴回零最大误差小于 0.02 rad；COMPLETE、控制权释放及无竞争非零 jog。

本次运行目录在启动时打印，格式为 `log/visual_sim/ball-时间/` 或 `cylinder-时间/`。其中 `session.json` 保存实际轨迹、接触、仿真时间和每轮结果，`events.jsonl` 保存状态；每个 `scene-NNN.yaml`、任务 YAML 和图像快照用于复现。`log/` 不进入 Git。

导出时替换会话目录，输出目录需不存在：

```bash
/usr/bin/python3 -s scripts/analyze_physics_grasp.py \
  log/visual_sim/实际小球会话目录 log/visual_sim/实际圆柱体会话目录 \
  --output validation/physics_grasp/新统计目录
```

历史结果 CSV、计划和摘要已提交到 `validation/physics_grasp/acceptance/`。压缩原始会话在 `validation/physics_grasp/raw_sessions.tar.gz`，包含两个正向批次、三个负向测试及补充 GUI/流程回归；解压审查不会启动动作：

```bash
mkdir -p /tmp/piper-stage3-evidence
tar -xzf validation/physics_grasp/raw_sessions.tar.gz -C /tmp/piper-stage3-evidence
```

解压后的相对目录保持 `log/visual_sim/<会话>/`。历史源码归档不含完整预编译环境；二进制哈希是本机证据，不要求重编译产生相同二进制哈希。

## 6. 故障处理验证

以下只用于单轮无窗口小球物理仿真，依次运行。它们故意制造失败，预期退出码为 **1**，不能计为正常取放成功：

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative miss
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative drop
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative stop
```

分别检查偏离 60 mm 时拒绝抬升、持物后松爪检测失物、实际抬升中停止。保存停止后连续关节位置样本，不能仅凭一条日志认定停止性能；本阶段没有宣称真实急停延迟。

## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| 找不到 `install/setup.bash` | 确认在新的 simulation/ 执行完整构建，看到七包完成 |
| 依赖或插件 FAIL | 依照第 2 节补依赖；运行系统 Python 的自检，不加载其他工作区 |
| NumPy / cv_bridge ABI 错误 | 退出 Conda、使用系统 Python 和 `-s`，不要向 ROS 的 Python 环境装 NumPy 2 |
| 检出外部 overlay | 新终端运行本目录 build 脚本；启动脚本会检查七个本地包都来自本目录 install/ |
| DISPLAY 缺失或不可访问 | 在登录后的 Ubuntu 图形桌面终端运行；不要伪造 DISPLAY 值 |
| GLX / RViz 渲染错误 | 入口为 RViz 单独选择 Mesa 软件渲染；检查系统图形会话及驱动。仍失败时保留窗口日志，先在相同桌面试无窗口一轮 |
| 端口 11483 或域 83 已占用 | 在对应仿真启动终端 Q 退出，等待清理；不批量 kill 所有 ROS/Gazebo 进程 |
| 开始时 `No fresh joint state` | 属于运动前拒绝；交互模式稍后再次 S，批量模式仅对此明确原因有界等待 |
| 规划失败、接触丢失或超时 | 保留完整会话，X 停止；R 重载后再诊断，不跳过碰撞/接触条件 |
| Q 后组件输出清理异常 | 父程序应完成回收；检查是否仍有其进程。部分旧 MoveIt 组件关闭时会输出异常，不等于正常取放通过 |

## 8. 模型、代码与后续工作

小球：直径 35 mm、15 g；物理圆柱：直径 50 mm、高 100 mm、80 g，实心近似。双指碰撞垫为简化长方体，机械臂理想重力补偿。已知尺寸、固定桌面及有限随机区域是当前假设；圆柱最大放置误差约 20.68 mm，仍有改进空间。

源码入口：`scripts/visual_sim_console.py`（会话与数据）、`src/brain_robot_pick_place/scripts/physics_target_node.py`（RGB-D 中心拟合）、`src/brain_robot_pick_place/src/grasp_lift_executor.cpp`（规划与物理验证）、两个 Gazebo Xacro（动力学、接触与相机）。MoveIt 附着只影响碰撞规划，不驱动 Gazebo 物品。

Gazebo Classic 与现代 Gazebo 的插件不同，参见 [Humble gazebo_ros2_control 文档](https://control.ros.org/humble/doc/gazebo_ros2_control/doc/index.html)。本指南固定当前基线，迁移仿真器需要单独开发。后续 YOLO、多类别规则、脑机语义指令和真实设备验证均未混入本次发布。

发布前的干净目录构建、依赖检查、无窗口和窗口试验见[双语发布核验](PUBLISH_VALIDATION.md)。
