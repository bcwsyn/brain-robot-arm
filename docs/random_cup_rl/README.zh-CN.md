# 随机起终点水杯抓放与强化学习复现

本阶段同时提供两条独立入口：Gazebo 腕部视觉取放基准，以及 MuJoCo 三维状态输入的 SAC+HER 训练环境。两者成绩分别统计。强化学习目前是环境和训练管线验证，不能把脚本控制器的成功或 Gazebo 基准的成功当成学习策略成功。

## 1. 获取代码与环境

GitHub：[bcwsyn/brain-robot-arm](https://github.com/bcwsyn/brain-robot-arm)。本阶段发布目录为 `simulation_cup_random_rl/`；此前各版本保留。

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_random_rl
```

本机开发目录是 `/home/young1x/robot_projects/piper_robot/simulation`。后文命令均从上述工作区目录执行。使用 Ubuntu 22.04 / ROS 2 Humble / Python 3.10；关闭 Conda，不叠加 `real_robot/` 或其他版本的 ROS 工作区。

只参考旧指南中的环境依赖，不切换到旧版本目录；构建和启动请执行本页命令。Gazebo 依赖说明沿用[腕部相机指南](../wrist_camera/README.zh-CN.md)。强化学习仅需 Python 私有环境，运行时不需要 ROS 或 Gazebo。

## 2. 可视化随机取放基准

```bash
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal
```

启动 Gazebo、MoveIt、RViz 和唯一的 Gemini2 腕部 RGB-D / YOLO 节点。等到 `[就绪]`，在启动终端按 **S** 执行；完成后按 **R** 重建下一轮随机场景，再按 S；**X** 停止，**Q** 退出并清理本入口启动的进程。随机模式中 1/2 都对应本轮同一个已采样终点，不能在任务执行中改终点。

当前杯身外径75 mm、高160 mm，杯口外径63 mm、高40 mm，总高200 mm；空杯80 g、壁厚2 mm仍为仿真假设。相机保留19.81°向夹爪中心偏转、105 mm轴向指尖距离及150 mm最小有效深度。没有新增外部视觉相机。

起点 `x∈[0.38,0.42], y∈[-0.12,-0.08]`；终点 `x∈[0.42,0.44], y∈[0.10,0.16]`，单位米、坐标系 `world`、同一水平桌面。该区域比执行器的参数门禁更小，给高杯预留空间；不代表整个机械臂工作空间均已验证。

指定一个坐标而非随机终点：

```bash
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14
```

这是世界坐标输入，尚没有图像点击选点；超出上述区域、NaN/Inf 会在启动前拒绝。

## 3. 无界面的正式批次

需要可用的图形渲染环境，`--headless` 只省去 Gazebo/RViz 窗口，Gazebo 相机仍需渲染。每轮重建仿真，20轮可能耗时数十分钟；不能同时占用 ROS domain 85 / Gazebo端口11485。

```bash
bash scripts/run_cup_grasp_sim.sh --headless --seed 2026101510 --batch-trials 20 --random-goal
```

启动时输出 `log/visual_sim/cup-<时间戳>`。将真实目录代入：

```bash
python3 scripts/analyze_random_cup_session.py log/visual_sim/cup-实际时间戳 \
  --output validation/my_random_baseline.json
```

`random_task_plan.json` 在运动前保存每轮起终点；`session.json`、组件日志、源码快照、锁定 RGB-D 帧和力反馈记录保留。独立分析重新核对初始位置、目标坐标与实际落点。失败立即结束批次，不自动重试运动，不丢掉失败轮次。

基准验收包含实际抬升≥50 mm、保持≥3仿真秒、保持双侧力2.5–3.5 N、松爪落稳且无指垫接触、杯子倾角<0.12 rad、三维放置误差<30 mm、回零误差<0.02 rad。实际测得的毫米级误差不等于将验收门限改成毫米级。

## 4. 配置独立强化学习环境

```bash
bash scripts/setup_cup_rl_env.sh
```

只安装到 `.venv-rl/`，不改变 `.venv-yolo/`，不安装系统软件。固定 CPU Torch 2.6.0、Gymnasium 1.1.1、Stable-Baselines3 2.6.0、MuJoCo 3.3.2；完整本机环境清单保存在阶段验证目录。

发布包含可直接加载的 `rl/assets/piper_cup.xml`，网格路径相对于工作区。重新从当前 URDF 生成时：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
.venv-rl/bin/python -s scripts/build_cup_rl_model.py
```

首次生成需要已经构建 ROS 工作区，以便 xacro 找到描述包。生成器使用当前带物理指垫/腕部相机的 URDF，保留运动学、质量/惯量、关节范围和100 mm夹爪；不使用旧的 `mujoco_py` 控制器或旧 MJCF。杯子在 MuJoCo 中用中空台阶壳体近似，接触模型与 Gazebo 不等价，尚未做实机动力学标定。

## 5. 验证环境与训练

```bash
.venv-rl/bin/python -s -m pytest -q rl/tests
.venv-rl/bin/python -s scripts/verify_cup_rl_env.py \
  --output validation/my_rl_environment --episodes 3 --seed 100
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 \
  --output artifacts/cup_rl/my_smoke
```

输出目录必须不存在，防止覆盖历史数据。第一条验证接口/物理语义；第二条包含脚本控制器的取放验证，不是RL结果；第三条真正执行SAC+HER采样和优化，5000步仅用于确认管线可以训练。

模型输入为33维三维状态、7维当前目标状态和7维期望目标状态。输入包含仿真杯子真值、机器人状态和双侧接触力；**没有摄像头图像输入**。每次重置随机生成杯子位置和终点，并用逆运动学初始化到该杯的预抓取位；尚不包含从固定观察位搜索杯子的学习过程。

动作4维：XYZ每步最大±4 mm，以及夹爪开/合/保持请求。倾角固定1.2 rad，工具朝向根据当前XY采用径向先验；不是任意6D姿态策略。每步推进20个2 ms物理步，即25 Hz；机械臂目标关节变化按整体比例限速至0.3 rad/s，夹爪独立限幅100 mm、目标力2.5–3.5 N、过力5 N终止。

成功需双侧接触下实际抬升≥50 mm，之后在目标15 mm内松爪、直立、低速且无指垫接触，并连续稳定10步。杯子不会在步进时被强行附着或改变位姿。碰撞、倾倒/跌落、过力会终止；最多2000步后超时。正常步奖励−1，落稳奖励0，碰撞/过力等故障奖励−200，并在HER重标目标时保留故障信息；失败也保存；短训练不保证收敛。

更长训练和可选质量/摩擦随机化：

```bash
bash scripts/run_cup_rl.sh --steps 200000 --seed 20261015 \
  --output artifacts/cup_rl/my_long_run --randomize-dynamics
```

随机化为空杯质量±20%、摩擦系数±20%；当前杯尺寸仍固定。先测训练速度，再据实际曲线决定训练量，不承诺固定步数即可抓放成功。

## 6. 独立评价、保存与继续训练

```bash
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run artifacts/cup_rl/my_smoke --episodes 20 --seed 2026101600 \
  --output validation/my_policy_evaluation
```

使用独立种子，记录全部成功/失败、坐标、误差、结束原因和轨迹。评价器核对模型与环境源码，避免用变化后的环境解释旧模型。0/20也是有效评价结果，不能只展示成功例。

训练保存 `model.zip`、`replay_buffer.pkl`、`training_config.json`、`training_result.json`、`episodes.jsonl`、源码哈希与快照。每10000步另存checkpoint。Ctrl+C会尽量保存当前模型和缓冲；停止后的新一轮训练：

```bash
bash scripts/run_cup_rl.sh --steps 3000 --seed 20261015 \
  --resume artifacts/cup_rl/my_smoke --output artifacts/cup_rl/my_resumed
```

保持同一模型、环境源码和随机化设置；恢复启用了随机化的训练时也需传 `--randomize-dynamics`。这是权重与经验缓冲恢复，环境会重新重置，不声称逐物理步完全相同的断点续跑。

## 7. 可视化轨迹回放

环境验证或学习策略评价都有轨迹。图形桌面运行：

```bash
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_rl_environment --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_policy_evaluation --episode 1
```

窗口关闭后退出。回放展示已经保存的位姿，不计为新的物理试验。第三人称窗口仅用于观察轨迹，未用于视觉识别或模型输入。保存视频或腕部画面：

```bash
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --video validation/scripted_replay.mp4
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --wrist --video validation/wrist_replay.mp4
```

`egl`需要可用的EGL驱动；失败时使用图形桌面的窗口回放，不需要修改系统显卡配置。腕部视频没有构成Gemini2深度标定或视觉策略验收。

本阶段结果、归档及后续任务见[阶段验收报告](../第六步_随机起终点抓放基准与强化学习环境验收.md) / [English guide](README.en.md)。

## 8. 恢复本阶段全部数据

GitHub保留6个最大45 MiB的分段；无需下载或复制本机的单个大tar.gz文件。以下命令重组并逐文件核验到新目录：

```bash
python3 scripts/restore_random_rl_stage.py \
  --archive-directory validation/stage6_random_rl/archives --output recovered_stage6
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run recovered_stage6/artifacts/cup_rl/stage6_final_policy --episodes 20 --seed 2026101600 \
  --output validation/recovered_policy_evaluation
```

该冻结模型原验收为0/20；命令用于复核管线和结果，不代表训练好的可用抓放模型。旧原型分别保留，使用当前环境时会拒绝源码/模型不一致的旧权重。
