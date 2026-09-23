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

## 2026-09-23 21:20：恢复后复查

- 按固定恢复顺序重新读取规范仓库状态、最近提交、reflog、`CODEX_HANDOFF.md`、本进度文件和决策文件；当前 HEAD 为 `a283d2d`。
- 现场只发现 Astra 启动进程，没有 `piper_single_ctrl`、视觉控制器或 MoveIt 控制栈。
- USB 枚举正常：Geschwister Schneider CAN adapter `1d50:606f`，Astra 彩色/深度设备 `2bc5:0557`、`2bc5:0657`。
- `ip -details link show can0` 显示 `state DOWN`、`can state STOPPED`；RX/TX/error/dropped 全为 0；`candump -n 12 can0` 返回 `Network is down`。
- `sudo -n -v` 仍返回需要密码，因此当前无法由 Codex 重新配置并启动 `can0`。这仍是硬阻断，不是 SDK、ROS、TF 或视觉算法故障证据。
- 未发送任何使能或关节目标。恢复后下一最小动作仍是：先由操作者完成 sudo 认证并将 `can0` 配置为 1 Mbps/sample-point 0.75，确认 `ERROR-ACTIVE` 和 `0x251..0x256` 持续反馈，再检查唯一驱动和 `/joint_states`。

## 2026-09-23 21:34：固定提示词后的无运动证据检查

- 按 `CODEX_TASK_PROMPT.md` 重新执行规范仓库恢复顺序；根目录仍为 `/mnt/hgfs/ub`，本轮开始 HEAD 为 `fab94d2`。用户已有未提交的供应商/相机/安装脚本修改和未跟踪 Debian 包保持不变。
- 运行时脚本 `/home/johnwick/start_brain_robot_cube_real.sh` 的 SHA-256 为 `fe0da5c...ba0eb5`，与规范源 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 的 `da9838...674230` 不同；因此最新的规范脚本尚未安装到实际运行路径，不能把运行时脚本当作本轮 `2e9bee8` 修复已生效的证据。
- USB-CAN、`gs_usb`/`can_dev`、`can0` 均正常：`ERROR-ACTIVE`、1 Mbps、sample-point 0.750、无 CAN 错误；5 秒 RX 增量 `15215`，`candump` 读取到 `0x251..0x253` 与 `0x3A0..0x3A7`。SDK `C_PiperInterface_V2` 导入路径为 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk/interface/piper_interface_v2.py`。
- 无运动 SDK 检查：高速反馈 timestamp `1790170155.000394`、`200.0 Hz`，当前位置 `[0, -1, -10, -29, 290, 0]`；六轴使能均为 `False`，`GetArmJointMsgs()` 仍为 timestamp/Hz 0，符合既有缓存限制。
- 临时启动唯一的 `piper_single_ctrl`（`auto_enable:=false`，无 `/joint_commands` 发布者）后，`/joint_states` 只有一个发布者，实测约 `190--205 Hz`，消息时间戳更新；随后停止该未使能诊断进程，CAN 仍保持 `ERROR-ACTIVE` 且 RX 增长。没有调用 `/enable_srv`，没有发送 `MotionCtrl_2` 或 `JointCtrl`。
- 停止驱动时出现已知 rclpy 清理异常：publisher context invalid，随后 `rcl_shutdown already called`；这是退出路径缺陷，未伴随 CAN 反馈丢失。下一轮启动前当前没有 PiPER、MoveIt、Servo 或视觉控制栈残留，只有 Astra。
- `sudo -n -v` 仍要求密码，但当前接口已正确启动，因此本轮不把它当作 CAN 硬阻断；若需要重新配置 CAN，仍必须先由操作者完成 `sudo -v`。

### 本轮结论与下一步

- CAN、SDK 高速反馈和 ROS `/joint_states` 三条基础链路均已验证；真机运动安全闸门尚未通过，因为本轮用户没有明确允许运动，且尚未重新查询并记录实际关节限位/速度/加速度。
- 下一步先把规范脚本通过 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 安装到 `/home/johnwick`（先保留并比较运行时差异），重新验证脚本哈希；随后在用户明确允许运动后，按固定安全清单查询限位、确认六轴使能和当前目标，执行仅 J2 `+250`（0.25°）的小幅反馈测试。

## 2026-09-23：磁盘空间巡检自动化

- 已在 Codex 中创建启用的线程心跳巡检 `PiPER 磁盘空间巡检`，频率为每天一次。
- 巡检只在根分区使用率达到 85% 或出现明确磁盘空间不足错误时执行 `/home/johnwick/clean_disk_space.sh`；空间正常时不执行清理，不修改 CAN、PiPER、ROS 或启动脚本。
- 巡检执行前后必须记录 `df` 使用率、脚本返回码和结果到本文件，并只提交本次进度记录。当前自动化 ID 为 `piper`；若虚拟机不可访问、sudo 失效或清理失败，记录阻断，不扩大操作范围。

## 2026-09-23 21:36：本轮收尾

- 无运动基础链路证据和下一步已记录于本文件；对应运行时基线决策提交为 `ef31689`。本轮未部署启动脚本、未启用机械臂、未发送关节命令。

## 2026-09-23 21:46：清理、安装与一键脚本阻断

- 按用户要求执行 `/home/johnwick/clean_disk_space.sh`；根分区 `df -P /` 清理前后均为 55%（`40453376` 总块、`21021780` 已用、`17344480` 可用），脚本返回码 `0`。ROS/受限系统日志清理完成；apt 缓存因 sudo 密码未缓存而跳过。未使用临时 `rm -rf`，未删除源码、工作区或 `.git`。
- 运行 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 返回码 `0`：`piper` 构建约 1.94 秒，`brain_robot_pick_place` 与 `brain_robot_ball_pick` 构建通过；运行时启动脚本与规范源 SHA-256 均为 `da9838e47c...674230`，V2 驱动源/构建源均为 `7846be3719...3f96f`。
- 只读 SDK 查询：`C_PiperInterface_V2` 高速反馈时间戳持续更新、`200.0 Hz`，位置 `[0,-1,-10,-29,290,0]`（0.001°）；六轴使能 `[False,False,False,False,False,False]`。SDK 软件角度范围为 J1 ±2.6179、J2 0..3.14、J3 -2.967..0、J4 ±1.745、J5 ±1.22、J6 ±2.09439 rad；原始 `GetAllMotorAngleLimitMaxSpd()` / `GetAllMotorMaxAccLimit()` 返回仍为 `-1/65535`，仅执行查询未写入参数。
- 无运动启动单一 `piper_single_ctrl` 验证通过：`/joint_states` 一个发布者、约 `200 Hz`，`/enable_srv` 存在；随后已停止，未调用使能服务、未发送 `MotionCtrl_2`/`JointCtrl`。探针日志仅有启动瞬间约 `0.08s` 的反馈门控恢复。
- 实际运行 `/home/johnwick/start_brain_robot_cube_real.sh` 返回码 `1`，在 `[1/7]` 的 `sudo ip link set can0 ...` 处停止；脚本清理完成且没有残留 PiPER/MoveIt/视觉控制器。阻断证据日志：`/tmp/start_brain_robot_cube_real_20260923.log`。当前 `can0` 仍 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750，RX 持续增长。

### 本轮结论与接管动作

- 磁盘清理和规范安装已完成；启动脚本版本差异已消除。当前硬阻断是脚本需要 sudo 重新配置 can0，而非已观察到的 USB-CAN RX 故障。
- 用户需要在同一个 Ubuntu 终端自行执行一次 `sudo -v`（不要把密码发送给代理），然后回复“接管已完成，继续按固定提示词闭环”。在此之前不运行完整视觉栈、不使能机械臂、不发送真实运动命令。

## 2026-09-23 21:51：接管凭据仍未进入代理终端

- 用户回复已完成接管后，重新执行 `sudo -n -v` 仍返回码 `1`（需要密码）；因此代理终端没有可用 sudo 时间戳。未读取或代输入密码。
- 只读硬件复核通过：3 秒 `can0` RX 增量 `9136`，状态 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误计数为 0；当前无 PiPER、MoveIt、Servo 或视觉控制器残留。
- 未重复运行必然在 CAN 配置阶段失败的一键脚本，未启用机械臂、未发送运动命令。下一步仍需在代理可见的同一终端完成 `sudo -v`，并用 `sudo -n -v` 验证返回码 0 后再运行脚本。
