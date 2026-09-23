# PiPER 调试进度

## 2026-09-23：重新拾起任务

- 规范仓库：`/mnt/hgfs/ub`；恢复前 HEAD：`a195b6d`（`docs: define durable Codex handoff workflow`）。
- 已按恢复协议读取 `git status`、最近 30 条提交、reflog、HEAD 摘要和 `CODEX_HANDOFF.md`。`docs/PIper_PROGRESS.md` 与 `docs/PIper_DECISIONS.md` 原先不存在。
- 现有工作树有大量用户已有修改及未跟踪 Debian 包；本轮不覆盖、不清理、不提交这些内容。

### 现场检查

- 实际运行路径：`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs`。
- 发现上一轮残留的 `cube_visual_search` 子进程（`pointcloud_tf_gate`、`active_scan_supervisor` 等），但没有 `piper_single_ctrl`；`/joint_states` 发布者为 0，符合交接文件记录的视觉适配器 `joint state timeout` 链路。
- 已停止该残留视觉进程组，避免第二套 MoveIt/Servo/视觉控制栈竞争。
- 运行时 SDK 为 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`；`C_PiperInterface_V2` 的 `MotionCtrl_2`/`JointCtrl` 最终调用 `C_STD_CAN.SendCanMessage`。本轮未在无高速反馈时发送关节目标。
- 重新启动 Astra 后，RGB/深度实际帧可收到，现场 `ros2 topic hz` 测得约 15–30 Hz（受 DDS/USB 负载波动）；深度帧时间戳为当前 ROS 时间。点云频率需要在唯一 PiPER 驱动和 TF 完整后重新测量，不能用残留实例的数据验收。
- 运行时 `can0` 显示 1 Mbps、sample-point 0.750、`ERROR-ACTIVE`，但探针前后 RX 计数均为 `27105303`，SDK 高速反馈时间戳/Hz 为 0；因此当前没有真实 CAN 反馈，未进行任何运动测试。
- `sudo -n -v` 失败（需要当前用户密码）。试跑 `/home/johnwick/start_brain_robot_cube_real.sh` 在 `[1/7]` 的 CAN 配置阶段停止，原因是无法执行 `sudo ip link set can0 ...`。这是当前硬阻断；还不能把无反馈归因于 SDK、ROS 或视觉代码。
- 已确认此前启动脚本失败清理会停止复用的 Astra；规范仓库脚本尚未应用修复。本轮将把清理改为只停止本轮启动的相机，并在启动前清理遗留 PiPER 驱动/检测器。

### 最小下一步

1. 用户在 Ubuntu 终端执行 `sudo -v`，确认机械臂电源、CANH/CANL、USB-CAN 透传和 Astra USB 占用状态。
2. 重新配置 `can0` 后先验证 RX 持续增长和 `0x251..0x256` 高速反馈，再按 `ConnectPort → 新鲜反馈 → EnableArm(7)/六轴使能 → MotionCtrl_2 → 当前位置+250 (0.25°) 的 J2 JointCtrl` 顺序做受护的小幅测试。
3. 只有 `/joint_states` 持续更新且唯一驱动存在时，才启动 MoveIt/Servo/TF gate；再验收紫色方块搜索、`GRASP_READY` 和抓取。

## 2026-09-23：本轮规范化提交

- 本文件与 `docs/PIper_DECISIONS.md` 首次创建，作为跨账号/重启后的唯一进度来源。
- 代码/测试提交后在此追加 commit、命令、结果和剩余风险；不提交密码、巨大日志、构建产物或临时抓包。
