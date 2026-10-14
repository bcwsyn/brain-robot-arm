# 水杯训练与视觉估径：中文复现指南

本版为独立 `simulation_cup/`，保留仓库原有 `simulation/` 第三步版本和 `brain_robot_arm/`。本机研发目录仍为 `simulation/`。以下命令以 GitHub 下载后的目录为准。

本轮可以复现：模型加载、五视角 YOLO 分割与 RGB-D 估径、只读 ROS 接口、数据恢复和训练，以及原球/圆柱物理仿真。**尚无可验收的水杯力闭环自动取放入口。** 预张开和接触力调节策略已写好并经离线测试，尚未接管夹爪控制器。详见[阶段报告](../第四步_水杯训练与自适应夹持基础验证.md)。

## 1. 环境与下载

已验证环境：Ubuntu 22.04.5、ROS 2 Humble、Gazebo Classic 11、系统 Python 3.10。本项目不适用于把 Gazebo Classic 插件直接放进 Fortress/Garden。训练使用 CPU，不需要更改 CUDA 或显卡驱动。

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup
```

如果目录已下载，进入现有 `simulation_cup/`；不要在原 `simulation/` 混合构建。本机开发者进入 `/home/young1x/robot_projects/piper_robot/simulation` 即可使用同一套脚本。

系统 ROS / MoveIt / Gazebo 的安装与排错见[第三步中文环境指南](../simulation/README.zh-CN.md)。其中工作区目录要换成 `simulation_cup/`。本轮没有安装系统软件；下面的系统包命令仅供缺少依赖的读者自行执行：

```bash
sudo apt update
sudo apt install python3-pip python3-venv python3-tk
```

不要使用 Conda 终端，也不要同时 source `real_robot/install/setup.bash`。此版本不包含可自动操作实机的驱动入口。

## 2. 独立构建与算法检查

先关闭占用本项目端口 11483 的旧仿真，再从新目录构建：

```bash
bash scripts/build_simulation.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
colcon test --packages-select brain_robot_pick_place
colcon test-result --verbose
```

本轮测试为 69 个算法用例、9 个 CTest 目标，colcon 汇总 78，0 失败/错误/跳过。colcon 汇总包含测试目标数量，不代表 78 个独立算法场景。七个 ROS 包应分别构建在此工作区的 `build/install/log`。

## 3. 创建项目内视觉环境

脚本仅安装到 `.venv-yolo/`，不用 sudo，不修改系统 Python：

```bash
bash scripts/setup_cup_vision_env.sh
export PYTHONNOUSERSITE=1
export YOLO_CONFIG_DIR="$PWD/artifacts/yolo/config"
.venv-yolo/bin/python -s -c 'import torch, numpy, cv2, ultralytics; print(torch.__version__, numpy.__version__, cv2.__version__, ultralytics.__version__)'
```

期望主要版本：Torch 2.6.0+cpu、NumPy 1.24.4、OpenCV 4.11.0、Ultralytics 8.3.203。完整实际依赖清单在 `validation/cup_vision/python_environment_freeze.txt`。`-s` 和 `PYTHONNOUSERSITE=1` 用于排除用户目录的 NumPy 2，避免与 Humble 的 Python 组件冲突。

首次安装需要联网下载 Python 包。权重已经随仓库提供，运行不需要再从第三方下载模型：

| 文件 | 用途 |
| --- | --- |
| `models/cup_yolov8n_seg_v2.pt` | 推荐的已训练单类模型，cup = 0 |
| `models/yolov8n_seg_coco.pt` | 原官方 COCO 模型，cup = 41，保留作初始化/失败对照 |
| `models/cup_model_provenance.json` | 来源、SHA-256、范围和许可证引用 |

YOLO 工具按名称查询 cup 编号。不要把单类模型误用成 COCO 的编号 41。

## 4. 可视化回放与模型检查

### 4.1 一个终端打开水杯视觉窗口

完成第 3 节的私有环境配置后，在 Ubuntu 桌面终端运行：

```bash
bash scripts/run_cup_visual_replay.sh
```

不需要先构建 ROS 工作区。脚本使用随仓库提供的五视角 RGB-D 和 v2 权重，**重新运行 YOLO 分割与深度估径**后打开交互窗口，而不是仅展示历史预测图片。启动一般需要数秒，终端会打印本次记录目录。

窗口从左到右显示原始 RGB、YOLO 掩膜叠加图、配准深度伪彩色图。黄色十字是建议的杯身抓取点。下方显示估计外径、建议预张开、可见杯高、抓取高度和不确定度参数。五个视角应各识别一个杯子，估计外径约 74.86–74.88 mm，建议开口约 82.86–82.88 mm，可见杯高约 200 mm。

| 操作（先点击回放窗口） | 效果 |
| --- | --- |
| `1`–`5` 或对应按钮 | 切换五个相机视角 |
| `←` / `→` | 前后切换 |
| 空格或播放/暂停按钮 | 每 2 秒自动切换，或暂停 |
| 保存图 / Save | 保存当前三联图和数值 |
| `Q` / `Esc` / 退出按钮 / 关闭窗口 | 退出并保存会话记录 |

每次新建 `log/cup_visual_replay.XXXXXX/`，其中 `inference/` 保存叠加图、掩膜和 `results.json`，`evaluation.log` 保存推理日志，`screenshots/` 保存点击“保存图”得到的图片，`viewer_session.json` 保存浏览视角与退出记录。再次运行不会覆盖上一轮。

可选择启动后自动播放：

```bash
bash scripts/run_cup_visual_replay.sh --autoplay
```

**这是保存画面的视觉组件回放，不是实时相机，也没有执行夹爪预张开、机械臂动作或反馈力控。** 完整水杯取放仍待下一轮集成。要观看已实现的机械臂运动，请使用第 9 节的球/圆柱入口。

![水杯视觉回放窗口](cup_visual_replay.png)

### 4.2 不打开窗口的检查

这一步读取仓库已保存的五视角 RGB-D，不启动 Gazebo、机械臂或任何运动。**所有 `--output` 必须指向尚不存在的目录；重复检查请换名字。**

```bash
PYTHONNOUSERSITE=1 .venv-yolo/bin/python -s scripts/evaluate_cup_holdout.py \
  --capture validation/cup_vision/stepped_cup_probe \
  --model models/cup_yolov8n_seg_v2.pt \
  --output log/my-cup-model-check
```

期望 `successful_sizing: 5`。输出包含每个视角的叠加图、预测掩膜、直径/高度/预张开建议和 JSON。最终参考指标在 `validation/cup_vision/trained_cup_diagnostic_v2/results.json`：五图各一个实例，IoU 约 0.961–0.977，理想仿真中杯身直径误差最大约 0.137 mm。该精度不代表真实相机。

可单独检查分割预测：

```bash
PYTHONNOUSERSITE=1 .venv-yolo/bin/python -s scripts/evaluate_cup_model.py \
  --images validation/cup_vision/stepped_cup_probe/images \
  --model models/cup_yolov8n_seg_v2.pt \
  --output log/my-cup-segmentation-check
```

此工具只输出预测，不能用它单独计算识别准确率。

## 5. 实际 ROS 节点回放检查

这一步会启动只读 ROS 感知节点，送入保存的 RGB-D 和标定 TF，不启动机械臂。域 84 与旧物理仿真的域 83 分开。使用新终端，并进入本工作区：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
export ROS_DOMAIN_ID=84
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/validation/fastdds_local_udp.xml"
export RMW_FASTRTPS_PUBLICATION_MODE=ASYNCHRONOUS
/usr/bin/python3 -s scripts/verify_cup_ros_replay.py \
  --capture validation/cup_vision/stepped_cup_probe \
  --model models/cup_yolov8n_seg_v2.pt \
  --output log/my-cup-ros-check
```

期望五个 positive、一个 blank、一个 stale_image 均 `passed`，进程退出码 0。节点日志和结果位于输出目录；脚本只停止自己启动的节点。

接口约定：

| 话题 | 消息/字段 |
| --- | --- |
| `/brain_robot_vision/cup_grasp_point` | `PointStamped`，图像时刻、world 坐标 |
| `/brain_robot_vision/grasp_width` | `Vector3Stamped`，x = 局部直径 m，y = 不确定度参数 m，z = 预张开建议 m |
| `/brain_robot_vision/cup_target_valid` | `Bool`，当前观测是否可用 |
| `/brain_robot_vision/cup_diagnostic` | `String` JSON，有效/拒绝理由、样本数、估径和高度 |
| `/brain_robot_vision/cup_debug_image` | 分割叠加图 |

节点拒绝多个杯子、过期图像、无对应时刻 TF、无有效深度、外壁不可观测和超行程目标。默认输入为旧仿真的腕部 RGB-D 话题，当前这些独立输出尚未连接运动执行器。

输入使用 reliable QoS，与当前 Gazebo 和回放发布者一致；真实相机的 QoS 及标定需要另行匹配。回放会等待实际图像订阅端点，并按帧名关联结果，避免把上一视角的结果算到下一视角。

## 6. 重新生成 Gazebo 杯子画面

这一步启动独立 Gazebo 服务器、桌面、中空杯和五个固定 RGB-D 相机，不加载机械臂。需要可用图形渲染环境，即使不显示窗口也需要深度渲染。延续上一节终端环境，再设置专用端口：

```bash
export GAZEBO_MASTER_URI=http://127.0.0.1:11484
/usr/bin/python3 -s scripts/probe_cup_rgbd.py --output log/my-fresh-cup-probe
```

期望采集五个视角并退出。RGB 位于 `images/`，深度/内参位于各视角 `.npz`，位姿与治具几何结果位于 `capture.json`。生成的杯子默认按用户几何，壁厚 2 mm、质量 80 g 为假设。历史 SDF 的 mesh URI 含原机器路径；使用脚本重新生成，不直接运行历史 world。

## 7. 恢复全部原始数据

归档位于 `validation/cup_vision/archives/`。每段最大 45 MiB，`archive_manifest.json` 和 `SHA256SUMS` 保存分段与合并哈希。先在新检出目录或没有同名数据的目录恢复：

```bash
/usr/bin/python3 -s scripts/restore_cup_archives.py
```

默认恢复到 `artifacts/cup_training/`，包括 `dataset_v1`、`dataset_v2`、`final_test_v2`、`train_v1`、`train_v2`、`physics_sessions` 和 `published_sessions`。已有同名目录会拒绝覆盖。可用 `--bundle dataset_v2 --bundle train_v1` 选择需要的部分，或用 `--destination log/my-restored-data` 恢复到另一目录。

两轮训练的失败预测、参数、loss/指标 CSV、曲线、最佳/末轮权重、定期 checkpoint、验证图，以及每组原始 RGB-D、相机标定和网格均保留。v1 的错误标签不能用作推荐模型，但保留供审查。

## 8. 复现训练

先按上一节恢复数据。第二轮数据 YAML 不含采集机器绝对根路径，移动目录后仍可解析。以下命令重新训练到新目录，不覆盖已保存运行：

```bash
PYTHONNOUSERSITE=1 OMP_NUM_THREADS=6 .venv-yolo/bin/python -s scripts/train_cup_model.py \
  --data artifacts/cup_training/dataset_v2/data.yaml \
  --model artifacts/cup_training/train_v1/weights/best.pt \
  --output log/my-cup-training \
  --epochs 12
```

原 v2 从 v1 最佳权重开始。想从官方权重开始，可把 `--model` 换成 `models/yolov8n_seg_coco.pt` 并增加训练轮数；这会成为新的试验，不应冒充原 v2。固定种子帮助复现，软件/硬件变化仍可能改变数值结果。

`final_test_v2` 只用于冻结模型的最终评估，禁止作为训练或调参数据。用户样品的五视角已用于开发诊断，因此也不作为完全未触碰的最终测试集。

## 9. 原物理仿真与力策略

完成第 2 节构建后，在本工作区运行下列一个入口，会打开 Gazebo 和 RViz 并等待开始：

```bash
bash scripts/run_ball_physics_sim.sh
```

或者退出小球演示后运行圆柱：

```bash
bash scripts/run_cylinder_physics_sim.sh
```

**在启动终端按键，无需回车**：`1/2` 选择放置区，`S` 开始取放，`R` 在结束后随机复位，`X` 停止，`Q` 统一退出。夹爪默认总行程现为 100 mm，但两种旧样品仍使用已知直径的位置预压，不是水杯闭环力控演示；圆柱也不是用户指定的中空台阶杯。

策略用法在 `src/brain_robot_pick_place/scripts/adaptive_gripper_policy.py`：预张开由测量直径、不确定度和余量计算；闭合命令根据两侧法向力改变。默认每侧 1.2–2.5 N、过力 5 N 是仿真调试参数，尚未验证它在实际 Gazebo 杯子抓取中收敛，更不是实机参数。SDK effort 单位是扭矩 N·m，不能直接传给要求 N 的策略。

## 10. 常见问题

| 现象 | 处理 |
| --- | --- |
| `No module named pip` | 确认系统 `python3-pip`；环境脚本使用 `venv --without-pip --system-site-packages` |
| NumPy 2 / cv_bridge 错误 | 关闭 Conda，设置 `PYTHONNOUSERSITE=1` 并使用命令中的 `-s` |
| 找不到模型 | 使用已提供的 `models/cup_yolov8n_seg_v2.pt`，不是只存在于开发机的 artifacts 路径 |
| 输出目录已存在 | 换一个新目录；工具有意拒绝覆盖原始结果 |
| 回放窗口无法打开 | 从本机桌面终端启动；确认 `DISPLAY` 可用且有 `python3-tk`，纯 SSH 无显示时用第 4.2 节的无窗口检查 |
| ROS 回放节点提前退出 | 查看输出目录 `node.log`；确认 `.venv-yolo` 依赖及 ROS overlay 都已加载 |
| Gazebo 端口占用 | 退出对应自己的仿真；脚本不会终止别人的进程 |
| 合成识别高分，真实杯子失败 | 当前只验收合成视觉组件；采集真实相机独立测试数据后再评估/适配 |
| 水杯怎么自动抓取 | 本版尚未完成力控取放集成；不要把新感知话题直接映射到旧已知样品执行器 |

依赖与权重许可来源见 `models/cup_model_provenance.json` 和 `models/LICENSE-ultralytics.txt`；上游机器人源码归属沿用 `UPSTREAM_PROVENANCE.md`。
