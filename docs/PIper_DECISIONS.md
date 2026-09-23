# PiPER 调试决策

## 已确认

1. `/mnt/hgfs/ub` 是唯一规范 Git 仓库；`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws` 和 `/home/johnwick` 下的副本是运行时路径，不能替代规范仓库的进度文件。
2. 低层控制必须遵守：`ConnectPort`，等待新鲜 `GetArmHighSpdInfoMsgs()`，发送 `EnableArm(7)`/确认六轴使能，再发送 `MotionCtrl_2(0x01,0x01,...,installation_pos=0x01)` 和持续 `JointCtrl`。`GetArmStatus()`、`GetArmJointMsgs()`、`GetArmModeCtrl()` 的零时间戳不作为实时确认。
3. 单关节诊断使用当前高速反馈构造目标：保持 J1/J3/J4/J5/J6 当前值，只给 J2 增加 250 个 `0.001°` 单位（0.25°）。没有新鲜反馈时禁止发送目标。
4. 不再反复执行 `MasterSlaveConfig(0xFA/0xFC)`，不执行 `ResetPiper`，不执行固件升级/降级；单臂官方顺序不需要主从配置。
5. 必须保证每轮只有一个 `piper_single_ctrl`、一个检测器和一个视觉控制栈；不能只停止 launch 父进程而留下子节点。CAN 高速反馈、ROS `/joint_states`、视觉适配器状态是独立验收链路。
6. 点云/TF 验收必须同时检查 cloud stamp、TF stamp、`frame_id`、`/clock`、`use_sim_time`、QoS 和旧 `pointcloud_tf_gate` 实例；当前时间能查到 TF 不代表历史 cloud stamp 一定可查。
7. Fast DDS 共享内存错误优先按旧 ROS 进程、共享内存锁文件和重复环境处理，不直接判定 PiPER 或相机硬件故障；先确认进程树与服务，再判断通信故障。
8. 真实抓取完成的条件是：一键脚本通过 CAN/驱动/相机/检测器/MoveIt/TF gate 检查，视觉离开 `PREPARE`，进入 `GRASP_READY` 后抓取、抬升、释放实际完成，并保存关键日志。

## 当前阻断决策

- 2026-09-23 现场 `can0` 虽为 `ERROR-ACTIVE`，但 RX 不增长、SDK 高速反馈为 0；在恢复硬件反馈前停止运动诊断。
- 当前 sudo 凭据缓存失效，启动脚本不能重新配置 CAN。先由操作者在 Ubuntu 终端完成 `sudo -v`，再继续最小验证；不通过重复 `/enable_srv` 或视觉启动来绕过此阻断。

## 2026-09-23 运行时基线更新

- CAN RX、高速 SDK 反馈和单一驱动的 `/joint_states` 已恢复并通过无运动验证；`sudo -n` 失败仍是重新配置接口时的权限限制，不等同于当前 CAN 断链。
- 规范启动脚本与 `/home/johnwick/start_brain_robot_cube_real.sh` 当前不一致。在未通过安装脚本同步并验证哈希前，不将规范脚本的清理修复视为运行时已部署。
- 本轮未获得明确真机运动指令；后续仅在明确允许、限位/速度/加速度重新读取、六轴使能确认和目标/停止条件已记录后，执行单关节小幅验证。

## 2026-09-23 清理与一键启动阻断

- 已执行规范磁盘清理脚本，根分区使用率 55%→55%，返回码 0；不因低于阈值而删除源码或工作区。
- 已通过规范安装脚本同步启动脚本并构建 `piper`、视觉检测和抓取包；运行时脚本哈希已与规范源一致。
- 一键脚本实跑在 CAN 配置阶段因非交互 sudo 凭据缺失返回 1；保留现有 `can0` 的 ERROR-ACTIVE/RX 事实，不把该权限错误误判为硬件断链。待操作者完成一次 `sudo -v` 后再继续。
- 2026-09-23 21:51 复核发现代理终端的 `sudo -n -v` 仍返回 1；在返回 0 前不重复启动完整流程，不把权限状态误判为 CAN/机械臂硬件故障。

## 2026-09-23 健康 CAN 复用决策

- 一键脚本在 `can0` 已为 1 Mbps、sample-point 0.750 且 RX 持续增长时直接复用接口，不因 Codex PTY 的 `sudo -n -v` 非零阻断启动；只有接口异常时才执行原有 sudo 重配置。
- 该复用路径不发送 PiPER 控制帧、不使能机械臂，仅读取接口状态和 RX 计数；任何真实运动仍须独立通过高速反馈、六轴使能、限位和停止条件安全闸门。
