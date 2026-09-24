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

## 2026-09-23：修正 sudo PTY 误阻断规则

- 用户在自己的 Ubuntu 终端执行 `sudo -v` 返回 0，但 Codex 使用的另一个 PTY 执行 `sudo -n -v` 仍需密码；这是 sudo 时间戳/终端会话边界，不足以证明系统权限或 CAN 故障。
- 当前 CAN 已验证 `ERROR-ACTIVE`、RX 持续增长和 0x251～0x256 高速反馈，因此固定提示词已改为：只有确实需要特权的接口重配置、驱动重载或系统服务安装时，才把 sudo 认证当作阻断；CAN 健康时不得仅因 `sudo -n -v` 非零阻断只读诊断、构建和进度工作。
- 若需要特权操作，用户必须在 Codex 实际使用的同一个远程终端完成一次 `sudo -v`；本轮未修改 CAN、PiPER 或运动逻辑，未发送运动命令。

## 2026-09-23：固定启动消息与持久文档职责

- 已在 `CODEX_TASK_PROMPT.md` 明确：聊天框只保留稳定的启动入口，通用规则、参数、历史事实、动态进度和决策均以规范仓库文档为准。
- 后续规则变化只修改对应文档并提交 Git，不要求每次接力重新编写完整聊天提示词；新代理必须以仓库最新文件覆盖聊天中的旧文本。

## 2026-09-23：磁盘空间巡检自动化

- 已在 Codex 中创建并启用线程心跳巡检 `PiPER 磁盘空间巡检`，现调整为每 15 分钟检查一次。
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

## 2026-09-23 22:17：接力复核（无运动）

- 规范仓库仍为 `/mnt/hgfs/ub`；本轮开始工作树保留已有的大量供应商/相机/安装脚本修改和未跟踪 Debian 包，未覆盖、未暂存、未提交这些用户修改。根分区 `df -P /` 为 55%，未执行清理脚本。
- 实际路径均存在：`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs`；运行脚本与规范源 SHA-256 均为 `da9838e47fca452ab983c480f23f412905cdfe22327eb025fc43a1b621674230`。
- 只读硬件复核：USB-CAN `1d50:606f`、Astra `2bc5:0557/0657` 和内核模块 `gs_usb`/`can_dev` 均可见；`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包为 0。3 秒 SocketCAN 原始接收统计为 `0x251..0x256` 各 600 帧（约 200 Hz），位置原始值保持 `[0,-1,-10,-29,290,0]`（0.001°）；未发送任何运动命令。
- 当前 SDK 只读导入为 `piper_sdk 0.6.2`，路径 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`，类 `C_PiperInterface_V2`。本轮未调用固件查询或任何控制 API；交接记录中的 `S-V1.8-2` 仍是历史事实，当前固件版本未重新验证。
- `sudo -n -v` 返回 1（需要密码），因此未重配 CAN、未运行完整一键脚本、未使能六轴。现有 `can0` 虽健康，但脚本 `configure_can()` 仍无条件调用 sudo；不以修改脚本绕过权限作为本轮动作，等待操作者在同一终端完成一次 `sudo -v`。
- 发现仅有 `/usr/bin/python3 ... ros2 launch astra_camera astra.launch.py` 的孤立 launch 父进程（无子进程，ROS 仅有 `/launch_ros_29887`，无相机话题）；已发送 TERM 停止该残留父进程，未停止其他控制器。停止后无 PiPER/MoveIt/Servo/视觉控制栈残留。
- 证据：本轮终端输出（未写入仓库的大型日志）、`/home/johnwick/brain_robot_logs/astra_camera.log` 及历史相机恢复日志；原始 CAN 统计可由同一命令复现。阻断仍为代理终端无 sudo 凭据，且相机需由一键脚本重新启动后再验收真实帧/点云/TF。

### 本轮结论与下一步

- 已验证 CAN RX 和六条高速反馈持续存在，硬件安全前置（反馈层）通过；未验证固件版本、六轴使能、关节限位/速度/加速度复查、`/joint_states`、Astra 帧、点云自体过滤、TF/Octomap、视觉 `GRASP_READY` 或抓取。
- 不允许继续真机运动：六轴尚未使能，且完整脚本被 sudo 凭据阻断。操作者先在同一 Ubuntu 终端执行固定接管命令并确认 `sudo -n -v` 返回 0；下一轮第一条命令为：`cd /mnt/hgfs/ub && sudo -n -v && ip -details -statistics link show can0 && timeout 10s candump -n 10 can0`。

## 2026-09-23 22:31：用户声称接管后复核仍未获 sudo

- 用户要求代理代输入密码并声称“接管完成”；代理不接受、存储或代输入聊天中的密码，仅在当前终端执行无密码验证。
- `sudo -n -v` 返回 1（`sudo: 需要密码`），因此接管尚未进入代理可见的 sudo 会话；未重配 CAN、未运行一键脚本、未使能六轴、未发送运动命令。
- 只读复核仍显示 `can0` 为 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误计数为 0；`timeout 10s candump -n 10 can0` 返回 0，并捕获 `0x251`、`0x252` 及状态帧。由于仅取 10 帧，本次不宣称六条反馈完整覆盖。
- 阻断：必须由操作者在同一 Ubuntu 终端交互式输入 sudo 密码，使随后 `sudo -n -v` 返回 0。安全闸门未通过前不允许真机运动。

## 2026-09-23 22:35：截图后代理终端复核仍失败

- 用户提供截图显示其终端曾执行 CAN 配置并看到 `ERROR-ACTIVE`；代理终端重新执行 `sudo -n -v` 仍返回 1（需要密码），因此不能把截图当作本代理 sudo 会话已接管的证据。
- 无需 sudo 的硬件复核通过：`can0` 仍为 1 Mbps、sample-point 0.750、`ERROR-ACTIVE`、错误计数 0；3 秒原始 CAN 统计为 `0x251=600`、`0x252..0x256=599`（约 200 Hz）。未发送运动命令。
- 阻断保持：当前工具终端无法获得 sudo 时间戳；未运行完整脚本、未使能六轴、未执行真实运动。需要操作者在 Codex 实际执行命令所在的终端完成 sudo 认证，或提供不含密码的可验证 sudo 会话保活，然后让 `sudo -n -v` 在该终端返回 0。

## 2026-09-23 22:39：再次确认后 sudo 仍不可见

- 用户再次表示“完成”，但当前代理终端 `sudo -n -v` 仍返回 1（需要密码）。因此仍不能运行需要 sudo 的一键脚本，也不能把接管视为完成。
- 只读 CAN 反馈继续正常：`ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误计数 0；2 秒内 `0x251..0x256` 各 400 帧（约 200 Hz）。未发送运动命令。
- 未启动 PiPER 控制器、MoveIt/Servo/视觉栈，未使能六轴；安全闸门仍未通过。下一步仍需让 `sudo -n -v` 在代理实际执行命令的终端返回 0。

## 2026-09-23 23:05：健康 CAN 复用与一键无运动验收

- 规范脚本 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 增加最小可逆逻辑：若 `can0` 已为 `UP/UNKNOWN`、1 Mbps、sample-point 0.750 且 1 秒 RX 计数增长，则直接复用并跳过 sudo；接口异常时仍走原有特权重配置。`bash -n` 和该文件范围的 `git diff --check` 通过。
- 运行 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 返回 0：`piper`、`brain_robot_pick_place`、`brain_robot_ball_pick` 均构建通过；运行时启动脚本已同步。脚本内磁盘清理保持根分区 55%，apt 清理由于 sudo 不可见而跳过，但未达到 85% 阈值，不构成磁盘阻断。
- 实际运行 `/home/johnwick/start_brain_robot_cube_real.sh` 返回至 `[7/7] 全部组件已就绪`，CAN 阶段输出“复用已处于 1 Mbps/0.75 且 RX 持续增长的 can0（无需重新配置）”，未要求 sudo、未自动按键、未使能或发送运动命令。
- 无运动 PiPER 驱动：唯一 `/piper_ctrl_single_node`，`/joint_states` 有效消息时间戳；实测平均约 170 Hz（窗口曾见 140–170 Hz，存在约 0.333 秒间隔），`/piper_moveit_joint_states` 持续发布。未调用 `/enable_srv`。
- Astra/视觉链路：唯一 Astra 容器、检测器、MoveIt、Servo、TF gate、自体过滤和抓取节点均存在；RGB 首帧和深度首帧收到，`/camera/depth/image_raw` 约 29 Hz，`/camera/color/image_raw` 实测约 8.6 Hz（有 USB/JPEG 丢帧迹象），原始点云约 6.5 Hz。`/brain_robot_vision/tf_gate_diagnostic` 为 `state=FORWARDED accepted_frames=380 rejected_frames=115 detail=TF_COMPLETE frame=camera_depth_optical_frame`；`/brain_robot_vision/filtered_points` 存在且带同一深度 frame/stamp；MoveIt `clear_octomap` 服务可用并已成功清图。
- 视觉状态保持安全等待：`/brain_robot_visual_control/state=IDLE`、`reason=WAITING_FOR_START`，`/brain_robot_grasp/scene_ready=false`、`state=WAITING_FOR_LEVEL_ALIGN`，目标 `target_valid=false`；未进入搜索、`GRASP_READY` 或抓取。停止脚本后发现其子进程短暂孤儿化，已按明确 PID 全部 TERM/KILL 清理；当前无 PiPER/相机/MoveIt/视觉残留。
- 证据路径：`/home/johnwick/brain_robot_logs/piper_driver.log`、`astra_camera.log`、`cube_detector.log`、`visual_stack.log`、`debug_image_view.log` 及其 `ros/` 子日志；本轮未提交大型日志、构建产物或 Debian 包。

### 本轮结论与下一步

- 已验证：健康 CAN 可在无 sudo PTY 时启动；一键流程可无运动到完整组件就绪；ROS 关节、RGB-D、点云 TF gate、自体过滤、Octomap、MoveIt/Servo 服务链路成立。
- 未验证：六轴使能后的真实小幅运动、限位/速度/加速度当前值复查、紫色目标稳定检测、视觉搜索/对齐进入 `GRASP_READY`、抓取/抬升/释放。RGB 仅约 8.6 Hz 且有 JPEG 错误，需后续优化或确认是否足够稳定。
- 当前不允许真机运动：本轮仅完成无运动链路验收，尚未打印并确认真实运动安全清单，也未得到本轮明确的运动授权。下一轮第一条命令：`cd /mnt/hgfs/ub && git status --short && sha256sum /home/johnwick/start_brain_robot_cube_real.sh brain_robot_arm/scripts/start_brain_robot_cube_real.sh`。

## 2026-09-23 23:13：真实运动安全清单只读复查

- 为准备而非执行真实运动，使用 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 后显式 `ConnectPort()`；未调用 Enable、MotionCtrl_2、JointCtrl 或任何写入限位 API。SDK/协议/接口版本为 `0.6.2`/V2/V2，固件查询为 `S-V1.8-2`。
- 高速反馈新鲜：timestamp `1790176313.8304694`、`200.0 Hz`，六轴当前位置 `[0,-1,-10,-29,291,0]`（0.001°），速度/电流均为 0。`GetArmStatus()` 缓存的时间戳仍为 0，显示 STANDBY/NORMAL、无角度限位状态，不用作实时使能确认。
- 控制器限位响应仍不可用于安全运动：`GetAllMotorAngleLimitMaxSpd()` timestamp 虽更新，但六项均为 `max=-1,min=-1,max_joint_spd=65535`；加速度六项均 `65535`。这与历史已记录的默认 `±1500/0..1800/...`、最大速度 300、最大加速度 500 不一致，且本轮没有执行任何恢复或写入。按照安全闸门，不能据此形成真实关节目标或速度/加速度限位。
- 结论：CAN/固件/当前位置和静止状态已复核，但本轮不允许真实运动；必须先定位为何实际限位查询仍为无效值，或在用户确认和明确恢复计划后按官方最小步骤恢复并重新查询。此限制不阻断后续无运动视觉诊断。

## 2026-09-23 23:22：按已验证官方 API 恢复限位并逐轴回读

- 依据历史 SDK V2 官方示例 `demo/V2/piper_set_init_default.py`，先完成逐轴无使能查询：每个电机 `0x473` 角度/速度响应为全 `FF`，每个 `0x47C` 加速度响应为 `FF`；确认不是全轴缓存假象。
- 在六轴使能状态 `[False, False, False, False, False, False]` 下，仅执行一次 `ArmParamEnquiryAndConfig(0x01,0x02,0,0,0x02)`；未调用 `EnableArm`、`EnablePiper`、`MotionCtrl_2`、`JointCtrl`、`ResetPiper`、`MasterSlaveConfig` 或固件 API。该 API 写入厂家默认参数，存在持久化配置影响，已按用户“执行已验证安全代码”授权。
- 等待 1.5 秒后逐轴查询并抓原始反馈：`0x473/0x47C` 均有效，SDK 回读为：J1 `-1500..1500, spd=300, acc=500`；J2 `0..1800, 300, 500`；J3 `-1700..0, 300, 500`；J4 `-1000..1000, 300, 500`；J5 `-700..700, 300, 500`；J6 `-1800..1800, 300, 500`。`all_limits_valid=True`，恢复后六轴仍全部未使能。
- 证据：本轮 Python SDK 输出及 SocketCAN 原始帧（未写入仓库的大型抓包）；SDK 版本 `0.6.2`、协议/接口 V2。恢复动作没有产生关节运动，未启动 ROS 控制栈。

### 真实运动闸门状态

- 现在限位/速度/加速度参数已通过逐轴原始响应和 SDK 双重回读；高速反馈此前为 200 Hz，最新静止位置 `[0,-1,-10,-29,291,0]`（0.001°）。
- 尚未执行真实运动。本轮下一步若继续，只允许 J2 单关节 `+250`（0.25°）小幅测试；目标保持 J1/J3/J4/J5/J6 当前值，控制速度比例 10%，预计持续约 0.6 秒，停止条件为任意反馈丢失、位置超限、震动/碰撞、急停或目标偏差异常，回退为立即停止发送并保持/失能。
- 执行前仍需操作者确认机械臂旁有人看护、工作区无障碍、急停可用；未确认前不发送任何运动命令。

## 2026-09-23 23:31：J2 小幅运动第一次安全闸门中止

- 用户确认现场看护、无障碍和急停可用后，按安全清单启动 V2 SDK：高速反馈 timestamp `1790177645.338818`、`200.0 Hz`、年龄约 0.004 秒；当前位置 `[0,-1,-10,-29,291,0]`，目标预计算为 `[0,249,-10,-29,291,0]`（J2 +250 个 0.001°，速度比例 10%，时限 1.2 秒）。
- `EnableArm(7)` 在约 0.14 秒内回读六轴全 True；随后安全循环发现 J2 当前 `-1` 低于已恢复下限 `0`，在发送第一条 `JointCtrl` 前抛出 `limit violation` 并执行 `DisableArm(7)`，最终六轴全 False。没有调用 `MotionCtrl_2` 后的关节目标发送，没有观察到运动。
- 该失败是安全闸门有效证据，不是 CAN/RX 故障。J2 只超限 1 个 0.001° 单位，目标 249 在 `0..1800` 内；下一次若继续，必须明确记录采用的边界容差和目标仍在有效限位内，其他关节保持实际值。

## 2026-09-23 23:38：J2 小幅运动触发非目标关节位移，立即停止

- 第二次尝试采用已记录的 5-unit J2 边界容差；安全输出显示高速反馈 timestamp `1790177773.557920`、`200.0 Hz`，当前位置 `[0,-1,-10,-29,291,0]`，目标 `[0,249,-10,-29,291,0]`，六轴使能回读全 True，速度比例 10%。
- 发送 `MotionCtrl_2(0x01,0x01,10,0x00,0,0x01)` 和重复 `JointCtrl` 后，J2 只变化约 6–7 个单位，但未测试关节也明显变化：样本中 J3 `-10→-5`、J4 `-29→0`、J5 `291→190`。监控在 J5 位移超过 100 单位时立即中止并调用 `DisableArm(7)`；六轴回读全 False。
- 停止后的 1 秒静止复核仍有新鲜反馈约 206.7 Hz；位置稳定在约 `[0,0,-2,-1,256,0]`，六轴全 False，CAN 仍 ERROR-ACTIVE、无错误。未观察到碰撞/震动的直接传感证据；操作者需确认机械臂实际外观和是否触碰障碍。
- 这是控制行为异常，不是 sudo/CAN/RX 阻断。可能涉及控制器内部目标保持、安装姿态/模式、反馈映射或 SDK/固件控制语义；禁止重复同一真实运动实验，禁止继续视觉搜索或抓取运动。

### 当前真实运动阻断

- 已完成一次真实小幅动作尝试并按停止条件中止；当前机械臂保持失能。未验证单关节独立性、目标帧编码与固件模式的一致性，也未验证当前静止姿态是否由用户接受。
- 下一步只能做无运动的 TX 帧编码/回放分析、控制器模式反馈和代码审计；若需再次使能或运动，必须先解释非目标关节位移并重新得到用户确认。

## 2026-09-23 23:45：非目标位移根因定位为高速反馈单位误用

- 重新读取规范仓库最新决策 `7d8e0aa` 后确认：高速电机反馈 `GetArmHighSpdInfoMsgs().motor_i.pos` 单位为 `0.001 rad`，而 `JointCtrl()` 参数单位为 `0.001°`。此前两次 J2 测试把高速值 `[0,-1,-10,-29,291,0]` 直接作为角度目标，违反该决策。
- 该单位错误解释了现场现象：例如高速 J5 `291` 实为 `0.291 rad`（约 16.7°），却被当作 `0.291°` 目标，导致 J5 向错误目标移动；J3/J4 同理。J2 实际目标也不是预期的 +0.25°。
- 当前高反馈静止值约 `[0,0,-2,-1,256,0]`（0.001 rad），六轴已失能；CAN 仍 ERROR-ACTIVE/RX 正常。未继续发送任何运动命令。
- 这是代理本轮测试中的安全方法错误，已立即停止并冻结真机运动；后续必须从已验证 `/joint_states` 弧度值或显式 `rad→0.001°` 换算构造目标，逐帧核对 TX 编码，不能重复此前直接复用高速 `pos` 的实验。

## 2026-09-23：无效限位响应的只读定位方案

- 已查阅 AgileX V2 SDK 接口文档：全轴限位/加速度 getter 是查询响应缓存；单轴 `SearchMotorMaxAngleSpdAccLimit(motor, 0x01)` 查询角度/速度，`0x02` 查询加速度，查询命令 CAN ID 为 `0x472`；角度/速度单轴响应为 `0x473`。因此全轴缓存出现 `-1/65535` 不能直接证明六轴控制器参数同时损坏。
- 下一最小动作是完全无使能、无运动、无写入的逐轴查询与 CAN 抓包：每次只查询一个电机一种内容，等待响应后读取 `GetCurrentMotorAngleLimitMaxVel()` 或 `GetCurrentMotorMaxAccLimit()`，并核对原始 `0x472` 请求和对应反馈。结果将区分“无响应/原始全 FF”“原始值正常但 SDK 解析错误”“逐轴有效而全轴缓存错误”。
- 官方文档同时指出高速反馈 `pos` 单位为 `0.001 rad`，而 `JointCtrl` 单位为 `0.001°`。已修正决策：后续不得把高速反馈 `pos` 直接复用为 JointCtrl 目标；必须使用已验证的关节状态源并显式单位换算。
- 本轮未执行逐轴查询、未使能、未发送运动、未写入限位。若逐轴原始响应确认参数确实无效，才需由用户明确授权官方默认参数恢复，然后逐轴回读验证后再讨论运动。

## 2026-09-23：一次性授权与防坠落规则补充

- 用户要求停止同一项小幅真机测试的重复确认，并明确要求复位时避免机械臂失能/坠落。本轮只修改固定任务规则与决策文档，未发送运动命令。
- 已将规则写入 `CODEX_TASK_PROMPT.md` 和 `docs/PIper_DECISIONS.md`：一次性授权通过后不重复阻断；测试收尾默认回到测试前已验证的安全目标并保持使能；不得自动 `DisableArm(7)`；`ResetPiper` 禁止用于停止、复位或异常收尾，因为会立即掉电并可能造成下坠。
- 碰撞、持续震动、反馈丢失或位置异常时，只停止新的位移目标并按安全停机/物理急停路径处理，不继续对障碍物施力，也不自动掉电。以上是规则更新，尚未证明任何新的真机运动结果。

## 2026-09-23 23:55：恢复运行时基线并清理孤儿视觉栈（无运动）

- 本轮恢复前 HEAD 为 `4591754`。规范运行时路径均存在；`/home/johnwick/start_brain_robot_cube_real.sh` 与 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 的 SHA-256 同为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。`/home/johnwick/piper_ros` 和 `/home/johnwick/piper_ws` 不是独立 Git 仓库，规范副本位于 `brain_robot_arm/vendor/piper_ros`、`brain_robot_arm/piper_ws`、`brain_robot_arm/scripts`。
- 根分区为 55%，未触发 85% 清理阈值。`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误/丢包为 0；2 秒 RX 增量为 6095。此次未连接 SDK、未使能、未调用 `MotionCtrl_2`、`JointCtrl`、`ResetPiper` 或任何参数写入 API。
- 发现 PPID 1 的孤儿 `/visual_search_controller`（PID 36742，原启动组 36715）。节点仍发布 `/servo_node/delta_joint_cmds`，但没有 PiPER 驱动、Servo 或 jog adapter 接收；为防止下次一键启动形成视觉/TF 竞争，仅发送 `TERM`。同一启动组遗留的 `piper_camera_mount_tf` 静态 TF（PID 36728）也已 `TERM`。两项均为启动/停止 ROS 节点，不涉及真机控制。
- 已用 `pgrep` 确认没有 `piper_single_ctrl`、`piper_jog_adapter`、`visual_search_controller`、`grasp_lift_executor`、`move_group`、`servo_node`、Astra、检测器、TF gate 或相机挂载 TF 进程。`ros2 node list` 在进程退出后短暂显示陈旧 DDS 发现；执行 `ros2 daemon stop` 清除 CLI 缓存后图为空。未停止或修改用户已有工作树改动及未跟踪 Debian 包。
- 源码只读审计确认实际 PiPER 节点使用 `GetArmHighSpdInfoMsgs()` 作新鲜度门控，而常规 ROS 位置反馈取自 `GetArmJointMsgs()`；此前目标构造必须继续遵守高频 `pos` 为 `0.001 rad`、`JointCtrl` 为 `0.001°` 的隔离规则。当前真实运动仍冻结，不能启动搜索或抓取运动。

### 本轮结论与下一步

- 已验证：运行时脚本已同步、CAN 持续接收、残留的可发布 Servo 增量的视觉控制器和同组静态 TF 已清除，下一次启动可从唯一干净栈开始。
- 未验证/阻断：未确认 SDK 当前六轴状态和逐轴限位回读；未完成 TX 帧编码/保持目标的无运动审计；单关节独立性、观测姿态、紫色检测、`GRASP_READY`、抓取/抬升/释放均未验证。因既有非目标关节位移，禁止 EnableArm、MotionCtrl_2、JointCtrl 和视觉搜索运动。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node|astra_camera|cube_detector|pointcloud_tf_gate|piper_camera_mount_tf' || true`；随后仅做 SDK `JointCtrl` TX 编码与 ROS 关节状态来源的无运动审计。

## 2026-09-23 23:59：SDK TX 与完整六轴命令审计（无运动）

- 只读检查安装的 `piper_sdk 0.6.2`、运行时 PiPER 驱动及运行时 jog 适配器；未实例化 SDK、未打开 SocketCAN、未启动 ROS 节点、未发送 CAN 帧或使能命令。SDK 文档/实现确认：`MotionCtrl_2` 编为 `0x151`；`JointCtrl` 将六个 `0.001°` 整数经软件限位后无条件发送 `0x155`（J1/J2）、`0x156`（J3/J4）、`0x157`（J5/J6）。官方 `demo/detect_arm.py` 将高速 `pos * 1e-3` 显示为 rad，继续佐证高频 `pos` 是 `0.001 rad` 而不是 `0.001°`。
- 运行时与规范 PiPER 驱动哈希相同（`7846be...3f96f`），jog 适配器哈希也相同（`29d369...1e11f`）。适配器只有在已 armed、关节反馈新鲜且完整时才以明确顺序发布 `joint1..joint6`；它不解释或修复其他发布者的截断 `JointState`。
- 发现驱动 `joint_callback()` 在使能且反馈新鲜时对缺失名称使用 `joint_positions.get('jointN', 0)`，随后调用完整六轴 `JointCtrl`。这会把不完整命令变成对缺失关节的绝对零位目标，正是此前“保持目标”不能靠猜测构造的同类风险。`docs/PIper_DECISIONS.md` 已新增完整六轴门控：不完整、重复、未知或 name/position 不匹配的命令必须无输出拒绝。
- 未直接修改驱动：其规范副本已有用户未提交差异 `443 insertions/391 deletions`，并带 CRLF/尾随空白，使 `git diff --check` 对整文件报错；危险回调位于该用户改动范围。为不覆盖或混入用户改动，本轮仅记录，未构建、未部署、未格式化该文件。

### 本轮结论与下一步

- 已验证：SDK 控制帧 ID、单位、完整 jog 发布路径，以及驱动的零位回退缺陷；这解释了为什么不能仅凭 J2 目标假定其余关节会保持不动。
- 阻断：必须先把用户已有 `piper_ctrl_single_node.py` 改动的来源和意图与用户确认，或由其作者完成/授权最小的完整六轴拒绝补丁；在此之前，真实运动及视觉搜索/抓取保持冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git diff --numstat -- brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py && sed -n '340,410p' /home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py`。

## 2026-09-24 00:02：完整六轴命令门控实现与无 CAN 验证

- 用户明确授权在已有驱动改动上继续完成。本轮起点为 `64bb67b`；只修改规范副本 `brain_robot_arm/vendor/piper_ros/src/piper` 和相同的实际运行源 `/home/johnwick/piper_ros/src/piper`，没有覆盖其他用户修改、没有格式化 CRLF 文件，也没有启动 ROS、实例化 SDK、打开 SocketCAN、使能或发送 CAN。
- 新增纯模块 `piper.command_validation`。它要求 `JointState.name` 与 `position` 等长，六个 `joint1..joint6` 各出现一次，只允许可选 `gripper`，并拒绝重复/未知名称、非数值和非有限位置。`joint_callback()` 在任何 `_set_joint_control_mode()`、`JointCtrl()` 或 `GripperCtrl()` 前调用该验证；有效消息按名称映射为 `0.001°`，不再以 `.get(..., 0)` 填充缺轴。夹爪只有显式 `gripper` 名称时才发控制帧。
- 新增 `test_command_validation.py`，以 `PYTHONPATH=brain_robot_arm/vendor/piper_ros/src/piper python3 -m unittest discover -s brain_robot_arm/vendor/piper_ros/src/piper/test -p 'test_command_validation.py' -v` 通过 3/3：完整乱序六轴、带显式夹爪、以及缺轴/重复/未知/长度不匹配/NaN 均符合预期。`python3 -m py_compile` 对驱动和验证模块通过。
- 在 `/home/johnwick/piper_ros` 执行 `source /opt/ros/humble/setup.bash && colcon build --symlink-install --packages-select piper`，返回 0（2.69 秒）；`source install/setup.bash` 后可从 `build/piper/piper/command_validation.py` 成功导入。规范/运行时驱动 SHA-256 同为 `e5ad444c...46e90c`，验证模块同为 `162f3968...ee3bde`。

### 本轮结论与下一步

- 已验证：不完整 ROS 关节消息现在能在 CAN 输出前被纯逻辑拒绝；完整六轴和显式夹爪消息仍被接受；运行时 `piper` 构建与导入成功。
- 未验证/阻断：未在运行节点中观察拒绝日志，未复查 SDK 当前六轴使能/限位，未测试正确单位目标的真实独立运动；观测姿态、相机、紫色检测、`GRASP_READY`、抓取/抬升/释放均尚未运行。真实运动和视觉搜索保持冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && PYTHONPATH=brain_robot_arm/vendor/piper_ros/src/piper python3 -m unittest discover -s brain_robot_arm/vendor/piper_ros/src/piper/test -p 'test_command_validation.py' -v`；随后只读复查 SDK 的当前六轴使能、逐轴限位和正确单位的 ROS `/joint_states` 来源，再决定是否能进行无运动节点验收。

## 2026-09-24 00:04：SDK 逐轴限位与静止反馈复查（无运动）

- 使用 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 后仅 `ConnectPort()`；没有调用 Enable/Disable、`MotionCtrl_2`、`JointCtrl`、`GripperCtrl`、`ResetPiper` 或任何参数写入 API。仅向 `0x472` 发送逐轴限位/加速度查询并读取相应响应；脚本返回 0。
- 高速反馈新鲜：timestamp `1790179515.008173`、`200.0 Hz`，原始位置 `[0,0,-2,-1,256,0]`（`0.001 rad`）；`GetArmEnableStatus()` 为六轴全 `False`。CAN 保持 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包为 0。
- 每轴查询响应有效：J1 `-1500..1500`、J2 `0..1800`、J3 `-1700..0`、J4 `-1000..1000`、J5 `-700..700`、J6 `-1800..1800`（`0.001°`）；最大速度均 300、最大加速度均 500。响应时间戳随每次查询更新，排除了全轴缓存 `-1/65535` 的旧阻断。

### 本轮结论与下一步

- 已验证：CAN、高速反馈、六轴未使能状态及逐轴限位/速度/加速度都可由当前 SDK 直接复现；本轮无关节或夹爪运动。
- 未验证：运行时驱动发布的 `/joint_states` 是否使用新鲜/正确的 `0.001°` 聚合反馈并与高速 `0.001 rad` 换算一致；完整启动栈、紫色检测和任何真实运动仍未运行。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node' || true`；随后只启动一个 `auto_enable:=false` PiPER 驱动，采样 `/joint_states` 后立即停止，不调用 `/enable_srv`。

## 2026-09-24 00:07：唯一无使能驱动的 ROS 关节状态采样

- 启动前无 PiPER/Servo/视觉控制器残留。仅启动一个 `ros2 run piper piper_single_ctrl`，参数为 `can_port:=can0`、`auto_enable:=false`、`gripper_exist:=true`，并重映射 `joint_states_single:=/joint_states`、`joint_ctrl_single:=/joint_commands`；没有调用 `/enable_srv`、没有发布 `/joint_commands`、没有调用任意运动 API。
- `/joint_states` 只有一个可靠 QoS 发布者。`ros2 topic hz` 在三段窗口得到约 `202.420`、`201.168`、`200.792 Hz`。独立 rclpy 订阅器成功收到当前时间戳 `[1790179605,993249416]` 的消息，名称为 `joint1..joint6,gripper`，位置为 `[0.0,-0.002930592,0.004291224,0.0,0.264869696,0.0,0.00007]`，速度六轴均为 0。
- 同一轮只读 SDK 高速位置为 `[0,0,-2,-1,256,0]`（`0.001 rad`）。ROS J2/J3/J5 不能与该高速电机值逐项直接换算为同一结果，故未将 ROS 或高速位置用作真实目标；新决策已冻结任何基于未验证映射的绝对保持目标。
- 首次 CLI `ros2 topic echo --once` 在发现期误报未发布，改用 rclpy 订阅成功。首次 SIGINT 只结束 `ros2 run` 包装而遗留其明确子 PID；已 TERM 该子 PID 并复查为空。第二次采样也在停止时触发已知 `ExternalShutdownException`/重复 `rcl_shutdown` 日志，但 wrapper 和子进程最终均已退出；CAN 保持 `ERROR-ACTIVE`、无错误/丢包。

### 本轮结论与下一步

- 已验证：单一未使能驱动的 ROS 发布频率、时间戳、名称和退出残留处理；未向真机发送位移或使能。
- 阻断：不能把高速电机反馈与 ROS 聚合关节状态假定为相同关节角；该映射未验证前，真实小幅动作、观测姿态和视觉搜索仍冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && python3 -c "from piper_sdk import C_PiperInterface_V2; print(C_PiperInterface_V2)"`；随后在单个只读 SDK 实例中同时采样 `GetArmJointMsgs()`、高速反馈和 SocketCAN 聚合帧，建立或否定可安全使用的关节映射。

## 2026-09-24 00:09：聚合关节反馈与 ROS 映射证明（无运动）

- 在一个 `C_PiperInterface_V2` 实例中复用驱动同样的纯接收 `0x3A0..0x3A7 → 0x2A1..0x2A8` 翻译，等待 1 秒后只读取缓存；未调用 Enable/Disable、`MotionCtrl_2`、`JointCtrl`、`GripperCtrl`、`ResetPiper`、限位写入或其他运动 API。探针返回 0，CAN 继续 `ERROR-ACTIVE`、无错误/丢包。
- 同时间戳反馈：高速 `1790179674.7383657`、`200 Hz`、`[0,0,-2,-1,256,0]`（`0.001 rad`）；聚合关节 `1790179674.7374153`、`200 Hz`、`[0,-168,246,0,15184,0]`（`0.001°`）；六轴全未使能。后者经 `π/(180*1000)` 转换正好对应上一轮 ROS 消息 `[0,-0.002930592,0.004291224,0,0.264869696,0]`（微小采样差异除外）。
- 结论：`/joint_states` 的名称、顺序和单位已得到聚合 CAN/SDK 双重证实；高速电机 `pos` 是独立电机量，不能直接作关节保持目标。当前聚合 J2=-168 和 J3=246 略越过已读回的零边界 J2≥0、J3≤0，故本轮没有发送任何“保持当前位置”目标。

### 本轮结论与下一步

- 已验证：可安全使用的关节状态源、ROS 的单位/顺序及高速/聚合反馈的语义隔离。
- 阻断：当前 J2/J3 位于零限位边界的外侧；任何真实动作前必须先打印完整安全清单、明确边界容差和目标均在限位内，且确认现场急停/障碍条件。观测姿态、视觉搜索和抓取继续冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && sed -n '1,130p' docs/PIper_DECISIONS.md`；随后仅准备（不执行）基于聚合关节角的单关节内限位回退计划，包含六轴目标、单位、速度、时间、停止条件与回退动作。

## 2026-09-24 00:10：SDK 与视觉软限位语义审计（无运动）

- 只读审计 `piper_sdk 0.6.2` 的 `__CalJointSDKLimit()` 与运行时 jog 适配器参数；未创建 SDK 实例、未打开 CAN、未启动 ROS 或发送任何帧。SDK 仅在 `start_sdk_joint_limit` 为真时按 `GetSDKJointLimitParam()` 的弧度范围转换到 `0.001°` 并钳制 `JointCtrl` 值；它不是控制器逐轴 `0x472` 响应的替代。
- 当前 jog 适配器软范围为 J1 `[-1.50,1.50]`、J2 `[-0.30,1.40]`、J3 `[-1.40,0.40]`、J4 `[-0.80,0.80]`、J5 `[-1.20,1.20]`、J6 `[-0.80,0.80]` rad，故会容许当前聚合 J2/J3 的零边界外小偏移；该范围不能授权真实控制器越界或让 SDK 静默截断目标。

### 本轮结论与下一步

- 已验证：SDK 软件钳位、控制器逐轴限位和视觉适配器软范围是三种独立机制；真实动作必须显式检查并记录控制器限位内目标，不能依赖任一方静默修正。
- 阻断：仍缺现场确认（人员/障碍/急停）及明确边界容差后的完整六轴内限位回退计划；在其前禁止 Enable、模式切换、`JointCtrl`、视觉搜索和抓取。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && tail -n 55 docs/PIper_PROGRESS.md`；随后输出（不执行）完整真机动作安全清单和由聚合关节反馈换算的六轴目标，等待现场条件确认。

## 2026-09-24 00:13：一键脚本完整无运动验收

- 从无 PiPER、相机、MoveIt、Servo、检测器或视觉控制器残留的状态，以标准输入 `/dev/null` 启动实际运行时脚本 `/home/johnwick/start_brain_robot_cube_real.sh`；未输入 `1`、`2` 或 `0`，未调用使能服务、`EnableArm`、`MotionCtrl_2`、`JointCtrl`、`DisableArm(7)` 或 `ResetPiper`。
- 脚本依次通过 `[1/7]` 健康 `can0` 复用、RGB 首帧、紫色方块 RGB-D 检测器、MoveIt/Servo/保护适配器、同时间戳 TF/Octomap、调试图像首帧，并到达 `[7/7] 全部组件已就绪`。apt 缓存清理因无交互 sudo 被跳过；根分区仍为 55%、可用 16981 MB，不影响启动。
- 就绪期间的只读验收：`/joint_states` 只有 `/piper_ctrl_single_node` 一个发布者和两个订阅者，消息为 `joint1..joint6,gripper`，当前位置为 `[0,-0.002930592,0.004291224,0,0.264869696,0,0.00007]` rad；`/brain_robot_vision/tf_gate_diagnostic` 为 `state=FORWARDED ... detail=TF_COMPLETE`；视觉控制器状态为 `IDLE`、原因为 `WAITING_FOR_START`。未进入搜索、`GRASP_READY` 或抓取。
- 为验证正常退出而非触发危险的 Ctrl+C 分支，仅向脚本父进程发送 `TERM`。清理日志明确为“未收到 Ctrl+C；不发送 PiPER 失能命令”，随后所有本脚本启动的 PiPER、相机、检测、MoveIt/Servo、TF gate 与视觉进程均已退出；没有残留 scoped 进程。
- 高速电机 `pos` 与 `/joint_states` 不逐项相等在本轮不构成新的运动阻断：已证明 `/joint_states` 直接来自官方 SDK 聚合 `GetArmJointMsgs()`（`.001°` 经 `pi/(180*1000)` 转 rad），而高速 `pos` 是独立的 `.001 rad` 电机反馈。尚未单独推导减速比、零位偏移或方向映射，故高速 `pos` 仍不得直接作 `JointCtrl` 目标；但已证明的聚合→ROS 链路足以继续本一键脚本的无运动验收，不重复同类诊断。

### 本轮结论与下一步

- 已验证：实际运行时一键脚本能在不使能、不运动的情况下完整到达待命状态，且启动、反馈、TF/点云门控、视觉控制器空闲状态与无掉电的 TERM 清理路径均符合预期。
- 阶段状态修正：`P0` CAN/反馈/限位已通过；`P1` 驱动命令完整性已通过静态门控和无 CAN 单元测试，但实际运行链路仍需验证；`P2` 小幅真实运动尚未验证；`P3` 一键脚本无运动启动已通过；`P4/P5` 视觉搜索和抓取尚未开始。
- 当前主阻断是 `P2` 真实 PiPER 运动尚未完成验证，不是 `target_valid=false`。视觉目标缺失只记录为后续 `P4/P5` 待办，不要求用户现在提供紫色方块，也不阻断运动恢复。
- 下一最小动作：使用与启动脚本相同的 `piper_single_ctrl` 和 `/joint_commands` 链路，在完整安全清单和一次性授权已存在的前提下，执行一项小幅可逆单关节测试；测试后回到测试前安全姿态并保持使能。不得调用 `ResetPiper` 或自动 `DisableArm(7)`。

## 2026-09-24 00:17：紫色目标无运动观察

- 由无残留状态第二次以 `/dev/null` 启动运行时一键脚本；再次完整到达 `[7/7] 全部组件已就绪`，未输入搜索、抓取或零点按键，未使能或发送关节/夹爪指令。
- `cube_detector` 是 `/brain_robot_vision/target_valid` 与 `/brain_robot_vision/target_pixel` 的唯一发布者，视觉搜索及抓取节点均已订阅 `target_valid`。连续 10 秒订阅得到的所有 `target_valid` 消息均为 `false`；在此期间没有收到 `target_pixel` 或 `target_point_camera`。检测器日志为 `PURPLE_CUBE target LOST`，而非节点崩溃、相机首帧或 TF gate 失败。
- 仅以 `TERM` 停止脚本父进程；日志确认走“保持、不发送 PiPER 失能命令”分支，随后 scoped PiPER、相机、检测、MoveIt/Servo、TF 与视觉进程均为空。未调用 `ResetPiper` 或 `DisableArm(7)`。

### 本轮结论与下一步

- 已验证：一键启动后的紫色目标检测主题和下游订阅关系完整；当前相机视野/实际场景没有获得可用紫色方块目标。这是继续搜索、对齐、`GRASP_READY` 与抓取前的外部视觉输入阻断，不能通过重复关节反馈、限位或启动诊断解决。
- 该视觉观察记录仍然有效，但属于 `P4` 的后续待办；不能覆盖当前 `P2` 运动恢复阶段。待 `P2` 通过后，再在相机视野内提供可检测目标并验证 `target_valid=true`、`target_pixel` 和 `target_point_camera` 稳定发布，然后才进入 `P4/P5`。

## 2026-09-24 00:58：运行时完整六轴门控无运动复核

- 实际运行栈由 `/home/johnwick/start_brain_robot_cube_real.sh` 的同一父进程保持：唯一 `piper_single_ctrl`、Astra、`cube_detector`、MoveIt/Servo、TF gate、`piper_jog_adapter`、`visual_search_controller` 和 `grasp_lift_executor` 均存在；没有第二个 PiPER 驱动。CAN 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point `0.750`，两秒 RX 增量 `6141`；根分区使用率 `55%`；运行时与规范启动脚本 SHA-256 均为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。
- 只读 ROS 状态确认视觉控制器 `IDLE/WAITING_FOR_START`，`scene_ready=false`，`target_valid=false`；`/arm_status` 为 `arm_status=0`，六轴通信/限位错误均为 false；`/joint_states` 只有 `piper_ctrl_single_node` 一个发布者，当前位置约 `[0,-0.002930592,0.004291224,0,0.266474544,0]` rad。
- 最小无运动动作：向实际 `/joint_commands` 发布一条仅含 `joint1` 的缺轴 `sensor_msgs/msg/JointState`。运行时 `joint_callback()` 返回校验拒绝；CAN TX 计数 `588→588`（增量 `0`），前后 `/arm_status` 完全相同且仍未使能。命令发布返回码 `0`，未调用 `/enable_srv`、`EnableArm`、`MotionCtrl_2`、`JointCtrl` 或任何夹爪控制。该证据补齐了 P1 静态单元测试之外的实际 ROS→驱动拒绝路径。
- 环境/证据：ROS 2 Humble、`/home/johnwick/piper_ros/install/piper`；只读进程/话题检查和 TX 计数如上，未写入大型日志。当前脚本仍在安全待命，未进入搜索或抓取。

### 本轮结论与下一步

- `P1` 运行时完整六轴门控已通过；`P0`、`P1`、`P3` 保持通过，`P2` 仍未通过，`P4/P5` 尚未开始。
- 当前阻断不是目标缺失，而是安全目标构造：聚合 `/joint_states` 的 J2≈`-0.168°`（控制器下限 `0°`）和 J3≈`+0.246°`（控制器上限 `0°`）仍在边界外。不能发送包含越界保持值的六轴绝对目标，也不能重复此前高速反馈单位误用实验。
- 下一最小动作：在不使能、不发送目标的前提下，保存一份同一 SDK/ROS 实例的聚合关节值与逐轴限位回读；然后由现场安全清单确认机械支撑、障碍和急停，制定并审查仅将 J2/J3 带回限位内的最小双关节回退目标。未完成该审查前，禁止 EnableArm、MotionCtrl_2、JointCtrl、视觉搜索或抓取运动。

## 2026-09-24 01:08：P2 小幅回退动作与瞬态反馈异常

- 动作前安全清单通过：高速反馈时间戳 `1790183148.9189608`、约 `210 Hz`；六轴未使能；逐轴控制器限位/速度/加速度有效（J1 ±1500、J2 0..1800、J3 -1700..0、J4 ±1000、J5 ±700、J6 ±1800；速度 300、加速度 500，单位 0.001°）。以 ROS 聚合位置构造合法目标 `[J1=0°, J2=+0.100°, J3=-0.100°, J4=0°, J5=15.2679°, J6=0°]`，速度比例 10%，仅计划 J2/J3 回到限位内。
- 通过实际 `/enable_srv` 返回 `enable_response=True` 后，向 `/joint_commands` 发布完整六轴目标；第一条反馈显示 J2≈`+0.193°`、J3≈`-0.113°`，但单个 ROS 聚合样本暂时显示 J5≈`+0.378°`，超过非目标轴 `0.2°` 漂移阈值，立即停止继续发布目标；未调用 `DisableArm(7)`、`ResetPiper` 或其他失能动作。
- 随后 2.5 秒只读监测中位置稳定为 J2≈`+0.193°`、J3≈`-0.113°`、J5≈`+15.253°`，`motion_status=0`、无错误/限位/通信故障。动作后独立 SDK 只读交叉核对高速反馈约 `200–210 Hz`、位置 `[0,4,-9,0,257,0]`（0.001 rad），六轴使能 `[True,True,True,True,True,True]`；因此 J5 异常被判定为单个聚合反馈瞬态，未观察到持续非目标机械位移。
- 证据与风险：本次动作证明 ROS 完整六轴命令可使 J2/J3 从控制器边界外进入限位内并稳定保持；同时暴露单样本聚合反馈异常，后续视觉轨迹必须继续逐样本检查所有轴，任何重复漂移立即停止。当前脚本仍保持运行，适配器未自动失能。

### 本轮结论与下一步

- `P2` 小幅可逆动作已通过“目标在限位内、反馈持续、非目标轴无持续漂移、六轴保持使能”的实测门控；`P0/P1/P2/P3` 现可继续。单样本聚合反馈瞬态作为剩余风险保留，不能重复同一直接目标实验。
- 当前主要阻断转为视觉外部输入：视觉控制器仍未进入搜索，检测器此前连续 `target_valid=false`；这不再阻断低层运动恢复。
- 下一最小动作：通过已运行脚本的实体运动门和 `visual_search_controller/reset`，先将六轴按配置安全复位到全零，再启动观测姿态；全程监测关节限位、反馈新鲜度和状态机，若无紫色目标则停在安全等待，不盲动抓取。

## 2026-09-24 01:14：视觉复位后 PiPER/CAN 反馈丢失阻断

- `visual_search_controller/reset` 在实体运动门和适配器 arm 后返回成功，第二次持久在线程监测得到 `STATE=STOPPED/RESET_COMPLETE`；随后 `/joint_states` 全零（含 J2/J3/J5），限位内。第一次监控会话提前终止曾触发 `USER_STOP`，未调用 PiPER 失能；第二次复位完成后未再发送视觉目标。
- 调用 `/visual_search_controller/start` 时返回失败：`No fresh joint state; the robot controller is not ready.`。随后实际驱动日志记录 `0x151 send failed: SendCanMessage(SEND_MESSAGE_FAILED (100017))`，`can0 feedback lost`，约两秒后 `can0 is loss` 并退出；运行时 `/piper_ctrl_single_node` 已不存在。
- 只读 CAN 复核：接口仍 `UP/ERROR-ACTIVE`、1 Mbps、sample-point `0.750`，但 bus-errors=`700`、arbit-lost=`9`、dropped=`9`，3 秒 RX 增量 `0`；USB-CAN `1d50:606f` 和 `gs_usb/can_dev` 仍枚举。`sudo -n -v` 返回 `1`（需要密码），不能由当前会话执行接口重配/驱动重载。
- 已按安全路径停止残留脚本进程组、Astra、检测器、MoveIt、Servo、TF、适配器和视觉控制器；未调用 `ResetPiper` 或 `/enable_srv false`，未在反馈丢失后继续发送目标。证据日志：`/home/johnwick/brain_robot_logs/piper_driver.log`、`visual_stack.log`；当前无 PiPER/视觉控制栈残留。

### 本轮结论与下一步

- `P0/P1/P2/P3` 的此前证据仍保留；P4 仅完成全零复位，观测姿态/搜索未启动，`GRASP_READY`、抓取、抬升、释放均未验证。
- 当前硬阻断升级为真实 CAN RX 丢失和发送失败，不是视觉目标缺失。无持续 `0x251..0x256` 反馈前禁止重新启动 PiPER、调用 `/enable_srv`、`MotionCtrl_2`、`JointCtrl` 或视觉搜索。
- 下一最小动作：操作者在同一 Ubuntu/Codex 终端完成一次 `sudo -v`，然后按接管协议重置 `can0`（必要时重载 `gs_usb`），用 `ip -details -statistics link show can0` 和 `candump -n 10 can0` 确认 RX 恢复；恢复前不重复本轮动作。

## 2026-09-24 11:14：现场只读复核确认 USB-CAN/接口仍不可用

- 当前 commit：`77b3443`；实际命令为 `sudo -n -v`、`lsusb | grep -Ei '1d50:606f|OpenMoko|CAN'`、`lsmod | grep -E 'gs_usb|can_dev'`、`ip -details -statistics link show can0`、3 秒 RX 计数、`timeout 10s candump -n 10 can0`、目标进程 `pgrep`、路径存在性、启动脚本 SHA-256 和 `df -P /`。
- 返回结果：`sudo -n -v` 返回 1（需要密码）；USB-CAN grep 无匹配；`gs_usb` 与 `can_dev` 模块仍加载；`can0` 不存在，`ip` 返回 1，RX 计数文件不存在，`candump` 返回 1（`No such device`）。没有 `piper_single_ctrl`、视觉、相机或 MoveIt 残留进程。
- 运行时路径 `/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs` 均存在；运行时脚本与规范源 SHA-256 都为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。根分区使用率 55%（未达到清理阈值）。
- 本轮未启动任何 ROS/PiPER 进程，未调用 `/enable_srv`、`EnableArm`、`MotionCtrl_2`、`JointCtrl`、`ResetPiper`，未发送 CAN/运动命令。证据为本轮终端只读输出；历史发送失败日志仍在 `/home/johnwick/brain_robot_logs/piper_driver.log`。

### 本轮结论与下一步

- 当前实际状态比上一条记录更早：不仅无 RX，`can0` 和 USB-CAN 枚举本身也不存在；`gs_usb/can_dev` 仅表示内核模块尚在，不能证明硬件链路健康。P0 未恢复，P2/P4/P5 均继续禁止。
- 阻断为操作者侧 USB/虚拟机映射、机械臂供电/CAN 线缆或需要特权的接口重新枚举/配置；不能靠重启驱动或视觉栈绕过。下一最小动作必须由操作者在同一 Ubuntu/Codex 终端完成一次 `sudo -v`，确认 USB-CAN 已连接且机械臂电源/CAN 线稳定后，按接管协议恢复并验证 `can0`、持续 `0x251..0x256` RX；在此之前不重复任何上层实验。

## 2026-09-24 现场修复后复核：USB-CAN 已枚举但 can0 仍 DOWN

- 当前 commit：`c09706e`；复核命令为 `sudo -n -v`、`lsusb`、`lsmod`、`ip -details -statistics link show can0`、3 秒 RX 计数、`timeout 10s candump -n 10 can0` 和目标进程检查。
- USB-CAN 已恢复枚举：`1d50:606f OpenMoko, Inc. Geschwister Schneider CAN adapter`；`gs_usb`/`can_dev` 已加载。但 `can0` 为 `state DOWN`、`can state STOPPED`、RX/TX/错误/丢包全为 0；`candump` 返回 `Network is down`，3 秒 RX 增量为 0。
- 当前 Codex 终端 `sudo -n -v` 仍返回 1（需要密码）；没有 `piper_single_ctrl`、Astra、检测器、MoveIt、Servo 或视觉残留进程。本轮未启动上层控制，未调用使能、模式、关节、复位或任何运动 API。

### 本轮结论与下一步

- USB 映射这一层已恢复，但 P0 仍未通过；`can0` 尚未配置并启用，持续 `0x251..0x256` 反馈仍为 0。不得把 USB 枚举误判为 CAN 健康，也不得启动 PiPER 或视觉栈。
- 下一最小动作：操作者在 Codex 实际使用的同一 Ubuntu 终端执行一次 `sudo -v`，然后按接管协议执行 `sudo ip link set can0 down 2>/dev/null || true`、设置 1 Mbps/sample-point 0.75、`sudo ip link set can0 up`，再用 `ip -details -statistics link show can0` 与 `timeout 10s candump -n 10 can0` 确认 `ERROR-ACTIVE` 和持续 `0x251..0x256` RX；恢复前不重复任何上层实验。

## 2026-09-24 12:13：拒绝使用聊天凭据，现场权限阻断保持

- 用户在聊天中提供了 sudo 密码并要求代理使用；代理未接收、保存、回显或代输入该凭据，也未执行任何提权命令。
- 当前已知现场状态保持上一轮结论：USB-CAN 已枚举，但 `can0` 为 `DOWN/STOPPED`、RX=0；`sudo -n -v` 仍返回 1。没有启动 PiPER/ROS/视觉进程，未发送运动命令。
- 本轮未把密码写入任何文件、日志或 Git；建议操作者立即轮换已暴露密码。

### 本轮结论与下一步

- 阻断仍是同一 Codex 终端没有 sudo 会话；聊天凭据不能作为授权或执行材料。下一步必须由操作者在实际终端交互式完成 `sudo -v`，然后自行执行既定 `can0` 配置和 RX 验证。

## 2026-09-24 12:19：CAN 恢复并完成一键无运动到 [7/7]

- 当前 commit：`b5205cc`。只读复核显示 USB-CAN `1d50:606f` 已枚举，`can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包均为 0；3 秒 RX 增量 `9141`，`candump -n 120 can0` 返回 0 并覆盖 `0x251..0x256`。
- 无残留控制进程后，以 `/dev/null` 启动实际 `/home/johnwick/start_brain_robot_cube_real.sh`；脚本复用健康 `can0`，收到 RGB/调试图像首帧，通过 MoveIt/Servo、同时间戳 TF/自体过滤和 Octomap 检查，输出 `[7/7] 全部组件已就绪`。未输入 `1`、`2` 或 `0`，未触发搜索、抓取、复位、使能或关节目标。
- 向脚本父进程发送 `TERM`；日志确认 `[保持] 未收到 Ctrl+C；不发送 PiPER 失能命令`，随后 scoped PiPER、Astra、检测器、MoveIt/Servo、视觉控制器均无残留。运行脚本返回码未在父进程被直接采集，但 `[7/7]` 与正常清理证据已保存于 `/tmp/start_brain_robot_cube_real_20260924_recovery.log`。

### 本轮结论与下一步

- `P0` CAN/高速反馈恢复通过；`P1` 既有完整六轴门控证据保持有效；`P3` 实际一键无运动启动再次通过。`P2` 小幅真实运动的既有证据仍受视觉复位后 CAN 丢失风险约束，不能把 `[7/7]` 视为运动完成。
- 当前脚本已安全停止，未进入 `P4` 搜索或 `P5` 抓取。下一最小动作：在 CAN 持续 RX 和单一驱动保持稳定的前提下，先重新只读启动并核对 `/joint_states`/限位/六轴状态，再由既有安全清单决定是否恢复已授权的可逆动作；不得直接输入搜索或抓取按键。

## 2026-09-24 12:26：无使能驱动与 SDK 限位只读复核

- 当前 commit：`668cf1f`。CAN 在探针前后保持 `ERROR-ACTIVE`、1 Mbps/0.750、无错误；此前 3 秒 RX 增量约 9139。探针启动唯一 `piper_single_ctrl`，参数 `auto_enable:=false`，未发布 `/joint_commands`。
- `/joint_states` 唯一发布者为 `piper_ctrl_single_node`，消息包含 `joint1..joint6,gripper`，频率约 199–201 Hz；样本时间戳有效，位置约 `[0.00340,-0.00516,0.01031,0.03217,0.13001,0]` rad。探针停止后无残留驱动进程。
- 同一 SDK `C_PiperInterface_V2` 只读连接显示高速反馈约 200 Hz、位置 `[3,-5,9,32,132,0]`（0.001 rad），六轴使能 `[False,False,False,False,False,False]`。逐轴查询未写入参数：速度均 300、加速度均 500，但六轴角度 `max/min` 均为 `-1/-1`；未调用 Enable、MotionCtrl、JointCtrl、ResetPiper 或参数恢复 API。
- 证据：`/tmp/piper_readonly_probe_20260924_b.log`、本轮终端输出；查询期间未观察任何运动命令，CAN 仍无错误。

### 本轮结论与下一步

- P0 的 CAN/高速反馈与 P1 的 ROS 反馈链路保持通过；P2 不能因 CAN 恢复直接放行，因为控制器角度限位回读再次无效。此前历史默认限位恢复结果不能替代当前回读。
- 下一最小动作：在不使能、不运动前提下，审计/确认限位参数查询与持久化行为（包括原始 `0x472/0x473/0x47C` 响应和实际运行 SDK），再决定是否需要一次用户已授权的官方默认参数恢复；恢复前禁止真实目标和视觉运动。

## 2026-09-24 12:28：当前固件版本只读确认

- 当前 commit：`113ff6c`。使用当前运行时 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk` 的 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 连接并调用 `SearchPiperFirmwareVersion()` 后读取版本。
- 结果：固件 `S-V1.8-2`，与 `CODEX_HANDOFF.md`/历史决策记录一致；SDK `PIPER_SDK_VERSION_0_6_2 (0.6.2)`，接口 `INTERFACE_V2 (0x2)`，协议 `ARM_PROROCOL_V2 (0x2)`。
- 查询后高速反馈仍为约 200 Hz，位置 `[3,-5,9,32,132,0]`（0.001 rad），六轴使能 `[False,False,False,False,False,False]`；未调用固件更新、使能、模式或关节控制 API。
- 前一项原始抓包持续看到 `0x251..0x256`/聚合反馈，但未看到查询 TX 回显；由于 SDK/接口可能 `local_loopback=false`，该现象不作为查询失败证据。

### 本轮结论与下一步

- 固件版本与交接记录相符，排除“当前固件版本未知”这一不确定性，但不解除角度限位 `-1/-1` 的 P2 阻断。
- 下一最小动作仍是无运动审计限位查询/持久化；在得到当前有效角度上下限前，禁止真实运动、视觉搜索和抓取。

## 2026-09-24 12:35：官方默认限位恢复并纠正限位单位

- 当前 commit：`8e7b942`。在六轴使能全 `False`、无 ROS 控制进程时执行一次 `ArmParamEnquiryAndConfig(0x01,0x02,0,0,0x02)`；该 API 为官方恢复全部关节限位、最大速度和加速度默认值的参数配置，不是运动命令。
- 首次回读脚本在 J1 后因误把 SDK 外层包装对象当作限位对象而抛出字段错误，未继续发送恢复或运动命令；修正字段访问后重新逐轴查询完成。
- 最终回读有效：J1 `-1500..1500`、J2 `0..1800`、J3 `-1700..0`、J4 `-1000..1000`、J5 `-700..700`、J6 `-1800..1800`；速度均 `300`、加速度均 `500`。六轴仍全未使能，高速反馈持续约 200 Hz。
- SDK 源码/官方示例明确角度限位回读单位为 `0.1°`，而 ROS 聚合/`JointCtrl` 目标单位为 `0.001°`；此前动态文档将限位单位写成 `0.001°`，本条予以纠正。限位数值必须先按 `0.1°` 转换后再与 `JointCtrl` 目标比较。

### 本轮结论与下一步

- 当前角度限位、速度和加速度已通过恢复后逐轴回读；P2 的限位参数阻断解除，但不自动授权运动。当前 ROS 状态中 J2/J3 仍需构造在 `0..1800` 与 `-1700..0` 内的完整六轴目标，并按真实运动安全清单执行。
- 下一最小动作：重新只读获取最新聚合关节位置与限位，打印六轴目标、单位、速度、停止条件和回退动作；在安全清单确认后才执行一次小幅可逆动作。

## 2026-09-24 12:43：P2 可逆动作因非目标漂移中止，保持使能待审计

- 当前 commit：`02540b6`。同一 `piper_single_ctrl` 链路在最新聚合位置基础上构造完整目标：初始 `0,-294,244,1843,9941,0`，目标 `0,100,-100,1843,9941,0`（单位 `0.001°`）；限位单位按 SDK 源码 `0.1°` 转换，速度比例 10%。
- `/enable_srv` 返回 `True`；发送 13 条完整六轴 `/joint_commands` 后监控发现非目标轴瞬时漂移 `497`（阈值 200），立即停止继续发布。最终样本约 `0,38,-26,1843,10022,0`，J2/J3 已朝限位内移动，但目标未完成，J5 出现异常漂移风险。
- 后续只读复核：ROS `/joint_states`、`/arm_status` 和驱动进程均已停止；独立 SDK 仍读到六轴 `[True,True,True,True,True,True]`，高速反馈约 `208 Hz`，J2/J3/J5 电流约 `574/-666/-1045`，CAN `ERROR-ACTIVE` 且无错误，2 秒 RX 增量约 `6099`。
- 未调用 `DisableArm(7)`、`ResetPiper`，未继续发送目标；当前硬件保持使能但无 ROS 驱动进程，证据日志/终端输出为 `/tmp/piper_p2_motion_retry_20260924.log`。

### 本轮结论与下一步

- P2 仍未通过；本次复现再次证明非目标轴反馈存在超阈值瞬态，不能进入视觉搜索或抓取，也不能把 J2/J3 的部分移动报告为成功。CAN/RX 健康不等于运动控制安全。
- 下一最小动作：在不发送新目标的前提下审计 `JointCtrl` 三帧编码、驱动生命周期和聚合反馈瞬态；保持当前硬件状态，等待安全的控制器接管/物理支撑处理，不调用自动掉电路径。

## 2026-09-24 12:48：P2 异常后恢复单一只读监测驱动并完成控制链审计

- 当前 commit：`8853f30`。异常动作后未调用失能或复位；以 `auto_enable:=false` 启动单一监测驱动，`/joint_states` 恢复约 199–200 Hz，`/arm_status` 无通信/限位错误。
- 独立 SDK 只读显示六轴仍 `[True,True,True,True,True,True]`、高速反馈约 201 Hz；J2/J3/J5 电流仍约 `582/-635/-1041`，CAN `ERROR-ACTIVE` 且 RX 持续。当前未发布任何目标。
- 源码审计确认运行驱动以 `57324.840764` 将 ROS 弧度转换为 `0.001°`，校验完整六轴后调用 `MotionCtrl_2(0x01,0x01,speed,0,0,1)`，SDK `JointCtrl()` 无条件发送 `0x155/0x156/0x157` 三帧；这解释了为何非目标保持值一旦异常会同时影响三组帧，但尚未定位漂移根因。
- 未修改运行代码、未重复运动；当前监测驱动保持运行以避免在硬件使能状态下失去反馈观察。

### 本轮结论与下一步

- P2 仍冻结；高电流和非目标漂移风险未解释，不能进入 P4/P5。当前安全状态是单一监测驱动、无命令、硬件保持使能、CAN/RX 正常。
- 下一最小动作：离线审计/单元验证 `JointCtrl` 三帧编码和控制器反馈映射，必要时在不改变硬件状态的前提下增加诊断日志；不得再次发送真实目标直到原因明确。

## 2026-09-24 12:53：离线 TX 编码与静止反馈抖动审计

- 当前 commit：`0d37201`。使用无 CAN 的 fake `SendCanMessage` 对 SDK `C_PiperInterface_V2` 进行离线编码验证：`MotionCtrl_2(0x01,0x01,10,0,0,1)` 生成 `0x151 [1,1,10,0,0,1,0,0]`；`JointCtrl(0,100,-100,1843,9941,0)` 生成 `0x155 [0,0,0,0,0,0,0,100]`、`0x156 [255,255,255,156,0,0,7,51]`、`0x157 [0,0,38,213,0,0,0,0]`。
- 解析源码确认运行时 `0x3A0..0x3A7` 减 `0xFF` 后映射为 SDK `0x2A1..0x2A8`；其中 `0x2A5/0x2A6/0x2A7` 正是 J1/J2、J3/J4、J5/J6 聚合反馈。静止状态下 2 秒采样 393 条 ROS 反馈，六轴单位值范围完全不变 `[0,38,-26,1843,9918,0]`。
- 本轮未发送 CAN 或运动命令；监测驱动保持 `auto_enable=false`，硬件六轴仍使能，CAN/RX 正常。

### 本轮结论与下一步

- 离线帧编码、反馈 ID 映射和静止 ROS 快照均通过；非目标漂移更可能是实际受力/控制器响应或动作期间反馈现象，不能靠重复动作区分。
- 下一最小动作：保留当前使能和监测反馈，进一步审计控制器模式/安装姿态反馈与动作日志；在获得可证明的非目标轴隔离方案前，禁止 P2 重试及 P4/P5 运动。

## 2026-09-24 12:54：控制器模式反馈只读审计仍不可实时确认

- 当前 commit：`5a521ce`。独立 SDK 只读读取到六轴仍全使能、高速反馈约 200 Hz；`GetArmStatus()` 和 `GetArmModeCtrl()` 时间戳均为 `0`，缓存显示 `ctrl_mode=STANDBY`、`installation_pos=0`，不能作为实时控制器确认。ROS `/arm_status` 显示 `ctrl_mode=1`、无错误/限位/通信故障，但同样不能补足 SDK 实时模式证据。
- 高速电流仍偏高：J2/J3/J5 约 `578/-654/-1006`，位置稳定在此前中止后的 `[0,38,-26,1843,9918,0]` 附近；CAN `ERROR-ACTIVE`/RX 正常，监测驱动保持运行，无新命令。
- 本轮未调用 Enable/Disable、MotionCtrl、JointCtrl、ResetPiper 或任何参数写入。

### 本轮结论与下一步

- P2 继续冻结：模式/安装姿态的实时反馈未验证，且高电流提示需要现场机械状态确认；不能安全重试动作或启动视觉运动。

## 2026-09-24 代码路径修复：一键脚本等待观测姿态结果

- 本轮提交：`dfbbc83`。
- 当前实际运行树核对：`/home/johnwick/piper_ws/install/brain_robot_pick_place/lib/brain_robot_pick_place/visual_search_controller` 是 symlink-install，实际目标为 `/home/johnwick/piper_ws/build/brain_robot_pick_place/visual_search_controller`；应用工作空间执行 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回码 `0`。因此本轮没有把安装产物误判为旧版本，也没有发送 ROS/CAN 运动命令。
- 发现一键脚本的真实可观测性缺陷：`start_visual_sequence()` 只检查 `/visual_search_controller/start` 服务返回后立即打印“已开始”，没有等待异步 `PREPARE` 到达观测姿态，也没有把 `PREPARE_EXECUTION_FAILED`、`PREPARE_JOINT_STATE_MISSING` 等结果反馈给操作者。该行为会把“请求已接受”误显示成“观测位已达到”。
- 最小修复已写入规范源 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 并同步到实际 `/home/johnwick/start_brain_robot_cube_real.sh`：服务成功后轮询 transient-local `/brain_robot_visual_control/reason`，仅在 `OBSERVE_POSE_REACHED`/`CURRENT_POSE_ACCEPTED` 时报告进入搜索；失败原因或默认 320 秒超时则返回失败。`bash -n`、`git diff --check` 和两路径 SHA-256 一致性均通过。
- 当前硬件仍由单一 `auto_enable=false` 监测驱动保持反馈；P2 仍冻结，高电流/非目标漂移风险未消除，本轮没有调用 Enable、MotionCtrl、JointCtrl、ResetPiper 或任何视觉启动服务。

### 本轮结论与下一步

- 脚本现在不会再把“异步启动请求成功”冒充为“机械臂已到观测位”，下一次实际按键 1 时会明确暴露真实失败状态或确认 `OBSERVE_POSE_REACHED`。
- 下一最小动作：在 P2 安全阻断解除后运行更新后的脚本，使用一次真实观测流程验证该等待门控和观测位反馈；在此之前只可做无运动构建/静态检查，不得重复此前导致非目标轴漂移的动作。

## 2026-09-24 任务方向纠偏：停止重复底层检查，优先完成观测姿态

- 用户已确认现场安全并承担旁站/急停责任；本轮不再重复询问同一安全确认。
- 当前主线从“继续重复 P0/P1 只读检查”纠偏为“验证并修复一键脚本按键 1 的复位/观测姿态执行链路”。未达到观测姿态不得报告启动流程完成。
- 后续代理必须首先检查实际运行配置和安装空间是否使用 `cube_task_real.yaml`、`visual_search_controller`、`piper_jog_adapter` 的最新版本；若未到位，优先定位配置加载、运动门、轨迹插值、六轴命令映射、PiPER 三帧发送或反馈判定的具体断点。
- 观测姿态完成证据必须包含实际起点/目标及单位、适配器接受轨迹、六轴反馈到位、非目标轴无持续漂移，以及 `OBSERVE_POSE_REACHED` 或等价状态。CAN/TF/点云健康和 `[7/7]` 只能作为前置条件，不能替代该证据。

## 2026-09-24 配置路径纠偏：避免读取未生效配置

- 实际一键启动的 `cube_visual_search.launch.py` 对真实控制器链加载 `cube_task_real.yaml`；`visual_search_piper_gemini2.yaml` 仅为备用/诊断配置。后续代理必须先核对实际安装空间和 ROS 参数来源，不能因备用文件中的真实运动关闭或全零观测姿态而错误阻断或修改主流程。
## 2026-09-24 自动执行观测姿态入口

- 本轮提交：`75d382e`。用户明确要求不再等待按键 1；规范脚本现将 `BRAIN_ROBOT_AUTO_START` 默认设为 `1`，在 `[7/7]` 组件就绪后自动调用既有 `restart_visual_sequence()`，即执行复位、观测姿态和搜索。`BRAIN_ROBOT_AUTO_START=0` 仅保留给无运动诊断。
- 实际脚本 `/home/johnwick/start_brain_robot_cube_real.sh` 已从规范源同步，SHA-256 与 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 一致；`bash -n`、`git diff --check` 通过。本轮未启动脚本、未发送真实运动命令。
- 自动入口仍受观测完成门控：只有收到 `OBSERVE_POSE_REACHED`/`CURRENT_POSE_ACCEPTED` 才报告进入搜索；失败或超时留在使能保持状态并保留按键 1 重试入口。

## 2026-09-24 自动化 sudo 前置条件补充

- 用户要求后续自动化接力具备非交互 sudo。规范要求当前 Codex/Agent 实际终端执行 `sudo -n true; echo $?` 返回 `0`，否则不能自行重配 `can0` 或执行其他特权动作。
- 本轮只修改文档，未修改系统 sudoers、未写入密码、未启动 CAN/驱动、未发送运动命令。
- 后续优先使用受限 CAN 恢复 helper/systemd 入口；`NOPASSWD: ALL` 不作为默认方案。

### 本轮结论与下一步

- 已推进脚本主线：从“启动后等待人工按键”改为“组件就绪后自动进入观测姿态流程”，不再因为交互输入遗漏而停在 `[7/7]`。
- 下一最小动作：在现场安全确认已复用、CAN/RX 仍正常且单一驱动条件满足时运行实际脚本，记录自动流程的起点、轨迹接受、反馈到位和 `OBSERVE_POSE_REACHED` 证据；若失败，依据脚本输出定位到具体阶段。

## 2026-09-24 自动脚本实际运行：清理成功路径修复

- 自动实际运行日志：`/tmp/brain_robot_auto_observe_20260924.log`。启动前的动作快照为唯一 `piper_single_ctrl`、`can0 ERROR-ACTIVE`、1 秒 RX 增量 `3050`、ROS 起点 `[0, 0.00252938, -0.00226772, 0.032166736, 0.173096812, 0] rad`、`/arm_status` 无通信和角度限位错误。自动流程目标保持为先全零复位、后 `[0, 0.98, -0.75, 0, 0.30, 0] rad` 观测姿态。
- 本次运行在旧低层驱动清理阶段退出，尚未达到 `[1/7]`，未发送复位、观测或抓取命令。根因是 `stop_stale_low_level_stack()` 的尾部 `pgrep ... && fail`：旧驱动被 KILL 后 `pgrep` 返回 `1`，在 `set -e` 下把“清理成功”错误传播为脚本失败。
- 已将该尾部改为显式 `if pgrep; then fail; fi; return 0`，使旧进程确实退出时函数返回成功；实际脚本已同步，`bash -n`、`git diff --check` 和两路径 SHA-256 一致性通过。

### 本轮结论与下一步

- 已推进观测姿态执行链路并定位第一个可复现启动断点；该断点发生在运动前，与 CAN/限位/观测轨迹无关。
- 下一最小动作：提交该修复后立即重新运行默认自动脚本，跟随日志验证 `[7/7] → reset → observe trajectory → OBSERVE_POSE_REACHED → SEARCH`；若失败，只沿该门控输出定位下一断点。

## 2026-09-24 默认自动流程实跑：PiPER TX 发送失败

- 实际运行命令：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null > /tmp/brain_robot_auto_observe_retry_20260924.log 2>&1 &`。流程已真实通过 `[7/7]`，自动调用 `/visual_search_controller/reset` 返回 `success=True`，然后执行 `enable_motion`、适配器 `arm`，控制器进入 `PREPARE (RESET_AUTHORIZED)` 并发布 `20.0 s` 两点复位轨迹；适配器日志确认 `REAL ARM trajectory accepted: 2 points`。
- 失败定位：轨迹接受约 6 秒后，`/home/johnwick/brain_robot_logs/piper_driver.log` 连续记录 `0x151 send failed: SEND_MESSAGE_FAILED`、`JointCtrl_J12/J34/J56 send failed`；随后驱动记录 `can0 feedback lost`，2 秒保护窗口后 `can0 is loss` 并退出。适配器随即 `PHYSICAL MOTION DISARMED: joint state timeout`，脚本等待门控报告“复位反馈超时”，未进入观测轨迹或 `OBSERVE_POSE_REACHED`。
- 本次 CAN 统计新增 `arbit-lost=683`、`dropped=5`，但接口仍 `ERROR-ACTIVE`、RX 持续；因此断点是实际 PiPER TX/反馈在复位命令阶段失效，不是配置加载、轨迹插值或反馈到位判断。完整日志保留在 `/tmp/brain_robot_auto_observe_retry_20260924.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。
- 按保护路径停止残留视觉栈并启动单一 `auto_enable=false` 监测驱动（PID 72129/72130）；`/joint_states` 已恢复，当前未发送新运动目标、未调用 `ResetPiper` 或自动失能。

### 本轮结论与下一步

- 自动启动链路已被真实执行并推进到“轨迹被适配器接受”；当前阻断明确在 PiPER 控制命令发送/反馈丢失阶段，脚本门控正确阻止了继续进入观测和搜索。
- 下一最小动作：只针对本次 `SEND_MESSAGE_FAILED`/`arbit-lost` 事件审计运行时 TX 所属和 CAN 发送失败原因，保持监测驱动、禁止重复自动运动；修复后再沿同一脚本门控重跑。

## 2026-09-24 TX 队列针对性修复

- 针对本次实跑新增的 `arbit-lost=683`/`dropped=5` 与 `SEND_MESSAGE_FAILED`，只做 TX 队列的最小可逆修复：实测 `can0` 默认 `txqueuelen=10`，当前通过 `sudo -n ip link set can0 txqueuelen 1000` 成功设置为 `1000`，接口仍 `ERROR-ACTIVE`，未发送运动命令。
- 规范启动脚本新增 `configure_can_tx_queue()`，默认在复用或重新配置 can0 后确保 `BRAIN_ROBOT_CAN_TX_QUEUE`（默认 `1000`）；设置失败直接拒绝进入运动流程。实际脚本已同步，`bash -n`、`git diff --check`、两路径 SHA-256 一致性通过。
- 本修复只针对 SocketCAN 发送队列溢出风险，不改变 bitrate、限位、SDK、目标姿态或控制器逻辑；当前仍保持单一 `auto_enable=false` 监测驱动，无新增运动目标。

### 本轮结论与下一步

- 已对自动实跑暴露的发送层具体条件做最小修复；下一次实际运行应验证 `txqueuelen=1000` 后 `0x151/0x155..0x157` 是否能持续发送并让复位轨迹完成。
- 若仍出现 `SEND_MESSAGE_FAILED`，继续依据驱动返回和 CAN 错误计数定位，不回退到已通过的基础巡检。

## 2026-09-24 TX 队列修复后自动流程复跑结果

- 第二次实际运行命令：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null > /tmp/brain_robot_auto_observe_txqueue_20260924.log 2>&1 &`；脚本通过 `[7/7]`，自动 reset 返回成功并记录 `STATE -> STOPPED (RESET_COMPLETE)`，随后自动 start 发布 `49.0 s` 观测轨迹，适配器记录 `REAL ARM trajectory accepted: 2 points`。
- `txqueuelen=1000` 后未再出现首轮的立即 `SEND_MESSAGE_FAILED`，但约 4 秒后驱动仍记录 `can0 feedback lost` 并退出；适配器再次因 `joint state timeout` 失能，脚本未收到 `OBSERVE_POSE_REACHED`。运行后 CAN 仍 `ERROR-ACTIVE`，统计 `arbit-lost=1093`、`dropped=10`。
- 结论：队列设置不是根因，但已证明脚本自动 reset/observe 轨迹链路本身正常到达驱动和适配器；当前唯一阻断仍是观测运动期间 CAN 反馈丢失/总线仲裁错误。视觉栈已停止，单一 `auto_enable=false` 监测驱动已恢复（PID 74632），未继续发送新目标。

### 本轮结论与下一步

- 已验证 `[7/7] → 自动 reset → RESET_COMPLETE → 自动 observe trajectory → 适配器 accepted`；未通过的是 PiPER 在观测运动期间维持反馈，故不能进入 `OBSERVE_POSE_REACHED` 或 `SEARCH`。
- 下一最小动作：只审计观测运动期间 CAN RX 停止与 `arbit-lost` 的时序/发送所有权，禁止再次自动运动直到该反馈丢失原因有可验证修复。
## 2026-09-24 观测运动期间发现 USB-CAN/xHCI 传输错误

- 本轮提交：`78c42bd`。
- 对第二次自动运行失败时段读取内核日志，发现与 `can0 feedback lost` 同时出现连续 `xhci_hcd 0000:03:00.0: ERROR Transfer event TRB DMA ptr not part of current TD ep_index 2 comp_code 1`；这发生在 USB-CAN 设备的 USB 传输层，而不是 ROS 观测控制器日志。
- 该证据与同一时段 `arbit-lost=1093`、`dropped=10`、PiPER 驱动反馈保护退出相互吻合；`txqueuelen=1000` 已排除为唯一修复。当前阻断具体化为 USB-CAN/虚拟机 xHCI 传输异常，不能通过重复自动运动或修改观测目标解决。
- 当前保持单一 `auto_enable=false` 监测驱动（PID 74632），视觉栈已停止；未执行 USB 重置、`ResetPiper` 或新的运动命令。运行日志仍为 `/tmp/brain_robot_auto_observe_txqueue_20260924.log` 和 `/home/johnwick/brain_robot_logs/piper_driver.log`。

### 本轮结论与下一步

- `[7/7] → reset → RESET_COMPLETE → observe trajectory accepted` 已验证；`OBSERVE_POSE_REACHED` 的唯一阻断是观测运动期间 USB-CAN/xHCI 传输错误导致的反馈丢失。
- 下一最小动作：在不发送运动的前提下恢复/稳定 USB-CAN 虚拟机传输（确认 USB 设备映射或宿主/虚拟机 xHCI 状态）后，再沿同一默认脚本门控重跑；无需重复 CAN、限位、单位或 TF 基线。

## 2026-09-24 USB-CAN 恢复权限阻断

- 设备仍枚举为 `Bus 003 Device 013: 1d50:606f`，`gs_usb` 绑定在 VMware USB hub 下；`usbreset 003/013` 仅返回设备权限错误，`sudo -n -v` 返回 `1`（当前会话无 sudo 凭据）。因此无法从该会话安全执行 USB reset/rebind，也未尝试保存或代用密码。
- 当前不再重跑自动脚本；保持单一监测驱动和完整日志，等待 USB-CAN 在宿主/虚拟机侧恢复或同一终端完成受限恢复后，再复用已验证的自动观测门控。

## 2026-09-24 USB reset 已执行，can0 配置等待 sudo

- 已直接执行 `/usr/bin/usbreset 003/013`，USB-CAN `1d50:606f` reset 返回成功；随后 `can0` 已重新枚举但处于 `DOWN/STOPPED`、RX=0。
- 当前会话 `sudo -n -v` 返回 `1`；无特权执行 `ip link set can0 type/up/txqueuelen` 均被 `Operation not permitted` 拒绝。因此不能伪造“can0 已恢复”，也没有启动驱动或运动流程。
- 下一步固定为在同一终端完成 `sudo -v` 后配置 `can0` 为 1 Mbps/0.75、TX 队列 1000，再验证 RX；这不是重复基础巡检，而是 USB reset 后必需的接口恢复动作。

## 2026-09-24 sudo 恢复完成但 USB-CAN 无 RX

- 当前会话 `sudo -n true` 返回 `0`；已完成 `can0` down、`gs_usb` 卸载/重载、1 Mbps/0.75、TX 队列 1000 和 up。接口为 `ERROR-ACTIVE`，但 5 秒 RX 增量仍为 `0`。
- 已终止遗留暂停的 `sudo timeout 6s tcpdump -i can0 ...` 进程；无 `piper_single_ctrl`、`candump` 或视觉控制进程。USB 设备仍枚举，但 PiPER 反馈未恢复，未启动驱动/运动流程。
- 当前证据表明仅重置 Linux `gs_usb`/接口不足以恢复总线反馈；下一步需要现场恢复 USB-CAN 物理/VM 透传或重启机械臂控制器电源后再验证 RX，不执行任何自动运动。

## 2026-09-24 再次 USB reset/gs_usb 重绑仍无 RX

- 在无驱动、无视觉、无运动命令状态下再次执行 `usbreset 003/013`、`modprobe -r/gs_usb`、重新配置 can0 和 `txqueuelen=1000`；接口最终 `ERROR-ACTIVE`、1 Mbps/0.75，但 10 秒 RX 增量仍为 `0`。
- 该 USB-CAN 适配器不支持 `restart-ms`，因此未强行设置自动 Bus-Off 恢复；没有发送任何 CAN 控制帧。软件侧可安全执行的恢复路径已耗尽，当前需要机械臂控制器或现场 USB/VM 链路重新产生反馈。

## 2026-09-24 按用户要求停止监测驱动

- 直接停止当前监测驱动进程组 `PGID 74632`；其子进程 `74633` 未响应 TERM，随后仅对该 ROS 驱动进程发送 KILL。未调用 `DisableArm`、`ResetPiper` 或任何运动命令。
- 复核 `pgrep -af 'piper_single_ctrl|piper_ctrl_single_node'` 无残留。当前 USB-CAN/xHCI 恢复前不启动新的 PiPER 驱动或自动运动流程。
