# PiPER 夹爪 CPV/SDK 复核（2026-10-12）

起点提交：`a50db1c`。本轮只使用现有 SDK 和 `/tmp` 临时脚本；没有启动 ROS、视觉、MoveIt、适配器或一键抓取流程，没有发送 `JointCtrl`，也没有调用 `ResetPiper`、`MasterSlaveConfig` 或固件升级。

## 现场基线

- `can0`：`UP/LOWER_UP`，1 Mbps，sample-point 0.750，`ERROR-ACTIVE`；累计 error、dropped、bus error、arbit-lost 均为 0。
- 最终只读 1 秒收到 2422 帧，其中 `0x3A7=200`、`0x251..0x256` 各 100、`0x261..0x266` 各 20；无控制进程残留。
- 最终 `0x3A7` 原始帧为 `0000000000000000`：位置 0、状态 0（夹爪失能）；六轴低速反馈仍显示六个驱动使能位为真。

## 已执行动作及结果

1. 参数恢复：`GripperTeachingPendantParamConfig(100,100,1)`，随后查询回读 `teaching=100, max_range=100, friction=1`。这是恢复此前只读查询到的 100 mm 量程，不是新的几何标定。
2. `EnableArm(7)` 三次 + `MotionCtrl_2(0x01,0x01,50,0)`，六轴低速反馈由仅 J1 使能变为六轴全部使能；没有关节目标。
3. 按本机 SDK `piper_set_joint_zero_cpv.py` 的夹爪 CPV 分支执行：失能、`MotionCtrl_2(0x01,0x05,30,0)`、原始 CAN `0x187 / 77 65 65 65 00 00 00`、回到普通 CAN 模式；随后在用户已确认的闭合位置按官方示例失能等待 1.5 秒，再发 `GripperCtrl(0,1000,0x00,0xAE)`。发送返回 `SEND_MESSAGE_SUCCESS`。
4. CPV 后分别测试 `0x02→100ms→0x01`、重新 `EnableArm(7)` 后再使能、单帧 `GripperCtrl(50000,1000,0x03,0)`、以及 `0x03` 角度 0 后保持 50 mm 目标约 2 秒。

上述每次反馈均保持 `angle=0`、`effort=0`、`status=0`，没有 0x3A7 位移；因此“发送成功”只证明 SocketCAN 接受了帧，不证明执行器接受目标。

## 结论与边界

官方 SDK 的 CPV 分支已实际复现，但不能把它等同于厂商 issue 所说的 ArmRobotUA“CPV 复位”。官方 issue #128 的回复要求使用最新版上位机，进入 CPV（密码 `agx123`），完成 CPV 复位后重新闭合并设置零点；当前 Linux 环境没有该 Windows 上位机运行链。本轮没有执行危险的 `ResetPiper`，也没有继续洪泛控制帧。

当前阻断是：CPV 操作后夹爪保持失能，普通 `0x159` 使能/目标帧不再改变反馈；需要实体断电重启或官方 ArmRobotUA CPV 复位流程来恢复控制器状态，然后再由闭合位置重新写零并复核开合。六轴 CAN 接收和使能不是当前夹爪无位移的证据。

复现脚本均为临时文件：`/tmp/piper_gripper_restore100_enable7_20261012.py`、`/tmp/piper_gripper_cpv_zero_open_20261012.py`、`/tmp/piper_gripper_enable_timing_open_20261012.py`、`/tmp/piper_gripper_enable_arm7_after_cpv_20261012.py`、`/tmp/piper_gripper_enable03_open_after_cpv_20261012.py`、`/tmp/piper_gripper_enable03_then_target_20261012.py`。

