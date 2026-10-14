# 水杯视觉估径与力反馈取放：中文复现指南

本入口在 Gazebo Classic 内运行虚拟 Piper：相机识别一个无把手、不透明空杯，估计杯身外径，预张开夹爪，以双侧实测接触力闭环夹持，抬升、保持、搬运、松爪、回零。第四步五视角窗口仍用于只读视觉回放；本指南描述新加入的运动集成。

## 1. 目录与环境

本机源码目录为 `/home/young1x/robot_projects/piper_robot/simulation`。GitHub 发布目录为 `brain-robot-arm/simulation_cup_grasp`，与旧 `simulation/`、`simulation_cup/` 分开。下文 `cd` 选择一个目录即可，不要同时构建多个工作区。

验证环境：Ubuntu 22.04.5、ROS 2 Humble、Gazebo Classic 11、MoveIt 2/OMPL、系统 Python 3.10，以及项目内 `.venv-yolo` 的固定 CPU 视觉依赖。无窗口 Gazebo 的深度相机也需要可用的图形渲染环境；本机验证使用桌面 `DISPLAY=:0`。纯 SSH 无图形环境不在已验证范围内。

首次从 GitHub 获取：

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_grasp
```

已经克隆则在仓库根目录先 `git pull --ff-only`，再进入 `simulation_cup_grasp`。不要用旧 `simulation/` 的 install 或已运行节点作为新工作区的环境。

系统依赖安装与 ROS 初始化参见[仿真环境指南](../simulation/README.zh-CN.md)及[视觉环境指南](../cup_simulation/README.zh-CN.md)。先检查当前系统：

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
python3 -s scripts/check_sim_environment.py
```

如正在使用 Conda，先 `conda deactivate`，然后用一个新的 Ubuntu 终端。缺少 ROS/Gazebo/MoveIt、pip 或图形库时按上述环境指南补齐；本项目脚本不会自动安装系统包。

## 2. 构建与配置视觉环境

在选定的水杯工作区内执行：

```bash
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
colcon test --packages-select brain_robot_pick_place
colcon test-result --test-result-base build/brain_robot_pick_place --verbose
```

构建脚本只构建本目录七个包。视觉配置脚本只安装到 `.venv-yolo/`，固定 Torch 2.6.0+cpu、torchvision 0.21.0+cpu 和 `config/cup_vision_requirements.txt` 的版本。无需重新训练，也不要求 GPU。

使用 `models/cup_yolov8n_seg_v2.pt`，SHA-256 为 `8f7afc15dd047edabc3fc0459e539e11220b19adbcc28c2da955aa07043cbeef`。若需核对：

```bash
sha256sum models/cup_yolov8n_seg_v2.pt
```

核心检查应得到 91 项汇总、0 失败/错误/跳过，包含 81 个算法/桥接用例和 10 个 CTest 目标。全工作区 lint 还会检查上游包已有版权/格式问题；完整扫描的 74 项失败和与第四步源码一致的对比证据保存在 `validation/cup_grasp/`，不能把核心测试通过描述为所有上游检查通过。

## 3. 可视化操作：推荐入口

```bash
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

等待终端完成五步加载并显示 `[就绪]`。程序打开 Gazebo 和 RViz。RViz 显示机器人/碰撞场景与固定 RGB-D 相机图；独立的大幅“Cup Detection and Grip Force”画面显示YOLO掩膜、实际夹爪开口和双侧接触力，可拖动窗口位置。RGB 图中的建议点来自相机；接触力来自 Gazebo，单位为 N。

**按键在启动程序的终端输入，不是在 Gazebo/RViz 窗口输入；不用回车。**

| 按键 | 操作 |
| --- | --- |
| `1` / `2` | 就绪时选 A/B 放置区；坐标分别为 (0.43, 0.12)、(0.44, 0.16) m |
| `S` | 开始一次视觉估径与物理取放 |
| `R` | 完成或停止后重新加载本次水杯仿真，产生新的随机起点；需要重新等待加载 |
| `X` | 运行中停止机械臂，冻结夹爪命令；过载卸载仍会有界继续 |
| `Q` / `Ctrl+C` | 退出并清理本入口拥有的进程 |

初次操作建议：等待就绪 → `1` → `S` → 等待 `[完成]` → `R` → 再次就绪 → `2` → `S` → 完成后 `Q`。运行中拒绝重复开始、换放置区或复位；停止/故障后先 `R` 重建。

对 75 mm 样品，视觉外径约 75 mm，预张开约 83 mm；实际闭合开口接近杯身直径，双侧力稳定在 2.5–3.5 N。命令开口可能小于实际开口，这是位置 PID 建立接触预压的需要，不能将命令开口误认为杯子被压缩后的直径。完成必须包括实际抬升、至少 3 秒仿真保持、搬运、松爪、落稳和回零。

水杯离桌或被机械臂遮挡后，单杯直立桌面估径可能拒绝新画面；执行器使用接近前锁定的有效包，力反馈持续工作，界面保留最近有效估径。这不代表在线追踪任意运动杯子。

为了避开 Gazebo 在复合杯模型热删除时出现的堆错误，水杯模式的 `R` 完整重启本入口拥有的仿真进程。它是预定下一轮的复位，不会自动重试失败动作。

## 4. 不同直径与自动验收

只改变场景样品尺寸，目标外径仍由视觉估计；不会把命令行直径喂给估径器。

```bash
bash scripts/run_cup_grasp_sim.sh --diameter-mm 55 --seed 20261016
bash scripts/run_cup_grasp_sim.sh --diameter-mm 85 --seed 20261017
```

两个命令依次运行，先退出前一个入口。当前试验杯高均为 200 mm，杯口外径为杯身的 84%，假设质量 80 g、壁厚 2 mm。验收尺寸是 55、75、85 mm；35–95 mm 命令行范围不等于每个尺寸均已验证。外径 + 不确定度裕量 + 6 mm 超过 100 mm 时拒绝动作。

无窗口的单轮重现：

```bash
bash scripts/run_cup_grasp_sim.sh --headless --seed 20261015 --batch-trials 1
```

完整固定计划会依次运行三个直径组的 9 次取放，以及 5 种故障/拒绝场景。它自动启动仿真运动，所有案例串行；失败后立即停止，并保留已完成和失败的结果。

```bash
python3 scripts/verify_cup_grasp_suite.py --case all
```

只测一个组可用 `--case main`、`--case 55`、`--case 85`。输出保存在新的 `validation/cup_grasp/acceptance_时间/`，可查看 `results.json`、固定源码哈希、固定计划和各组终端日志。重复时自动选择新目录，不覆盖之前数据。

## 5. 故障场景

以下动作仅对仿真试验开启，平时的注入服务拒绝请求：

```bash
python3 scripts/verify_cup_grasp_suite.py --case miss
python3 scripts/verify_cup_grasp_suite.py --case feedback-loss
python3 scripts/verify_cup_grasp_suite.py --case overforce
python3 scripts/verify_cup_grasp_suite.py --case stop
python3 scripts/verify_cup_grasp_suite.py --case oversize
```

`miss` 验证偏离杯身后没有合格双侧夹持就不能抬升。反馈丢失和 6 N 合成过载信号在已夹住、正在抬升时注入，检查机械臂停止；合成信号不冒充实际物理过载测量。`stop` 在抬升中请求停止。`oversize` 用 105 mm 场景杯检验视觉尺寸策略拒绝，抓取执行器不会启动。

内部运动负测常以进程退出码 1 结束，表示取放被中止；上面的验收脚本会检查是否是预期故障、是否没有完成以及停止后关节漂移，再给出该负测的通过/失败，不能只按退出码判断。

## 6. 数据和排查

每个会话在 `log/visual_sim/cup-时间/` 保存：

- `session.json`：实际物品轨迹、关节轨迹、双侧力、实际/命令开口、保持/放置/回零指标。
- `events.jsonl`：视觉包、执行状态、力状态、故障和控制诊断。
- `locked_frames/`：实际锁定图像时刻的 RGB、深度、掩膜、内参、相机外参及拟合结果，附模型哈希。
- `source_snapshot.tar.gz` / `source_hashes.json`：执行代码版本。
- `01-gazebo.log`、`01-task.log`、MoveIt/YOLO/场景日志及生成的场景/任务参数。

先查看终端最后一个故障码和对应日志。`CUP_PREOPEN_FAILED` 要核查新鲜图像包与轨迹反馈；`PHYSICAL_OBJECT_LOST_OR_FEEDBACK_STALE` 要核查力/接触新鲜度与物品高度；Cartesian path incomplete 表示规划拒绝，不要绕过碰撞检查。加载失败先运行环境自检。端口 11485 被占用时在已有入口终端 `Q` 退出，不用宽泛的 `pkill`。

发布包的完整会话以分段归档保存，恢复方法见本目录的归档说明及阶段报告；训练数据继续保存在旧 `simulation_cup/validation/cup_vision/archives/`，历史版本不删除。

## 7. 当前适用范围

这是中空刚性杯的仿真视觉—力反馈闭环。相机固定标定、桌面 z=0、一个直立不透明杯、空杯、理想机械臂重力补偿、简化指垫和假设摩擦参数是当前前提。它没有建立真实塑料变形/压坏模型，也没有实机力传感器标定、实机相机安装标定、多杯选择、装水搬运或脑机控制。

当前 100 mm 行程与用户指定大夹爪一致；其余模型动力学/接触参数不等于原厂实测。真实 SDK 的 effort/torque 不能直接解释为本轮的 N。下一阶段需要真实相机图像、相机与机械臂标定、实际夹爪反馈接口和受监督的实机验证。
