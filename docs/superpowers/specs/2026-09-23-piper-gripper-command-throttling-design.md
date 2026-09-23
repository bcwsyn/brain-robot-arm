# PiPER 夹爪命令按需发送设计

## 已验证故障机制

PiPER 一键流程能够完成 CAN、相机、MoveIt 和视觉栈启动，保护适配器也曾成功进入 `PHYSICAL MOTION ARMED`。随后 PiPER 驱动日志出现 `GripperCtrl send failed: SendCanMessage(SEND_MESSAGE_FAILED)`，SDK 的 CAN 接收状态失效，驱动因 `isOk()` 返回 false 主动退出。退出后 `/joint_states` 没有发布者，保护适配器检测到关节反馈超时并自动 disarm。

故障发生后，Linux 的 `can0` 已恢复为 `ERROR-ACTIVE`，且 3 秒 RX 增量为 9143 帧。这说明物理反馈总线仍能工作，但已退出的 ROS 驱动不会自动恢复。官方 SDK 的 `isOk()` 用于判断 CAN 接收线程是否持续工作，因此不能删除或绕过该保护。

当前 `piper_jog_adapter` 在每次 arm 时把夹爪目标设为 0.05 m，此后以 50 Hz 发布包含夹爪的完整 `JointState`。PiPER 驱动会对每一帧调用一次 `GripperCtrl`，所以即使夹爪目标没有变化，零点复位、观测姿态和视觉搜索期间也会持续发送夹爪控制帧。这些阶段并不需要夹爪动作。

## 目标

1. 适配器 arm 时不自动驱动夹爪。
2. 六轴保持、复位、观测和视觉搜索继续以现有 50 Hz 工作。
3. 仅在抓取执行器明确请求打开或闭合夹爪时发送夹爪命令。
4. 保留所有 CAN、关节反馈、运动门和失能保护。

## 修改设计

仅修改 `piper_jog_adapter.py` 及其直接启动参数：

- 删除 `initial_gripper_position` 参数及对应读取和校验。
- `_arm()` 将夹爪待发送状态清空，不再生成自动打开命令。
- `_gripper_command()` 收到抓取执行器的明确命令时，保存一次待发送的夹爪目标。
- `_tick()` 在下一帧六轴命令中附加该夹爪目标；成功发布 ROS 消息后立即清空待发送状态。后续保持帧只包含六个机械臂关节。
- 从 `cube_visual_search.launch.py` 删除已经失效的 `initial_gripper_position` 参数。

ROS 话题使用可靠 QoS，且适配器采用单线程 executor；订阅回调和定时器回调不会同时修改待发送值。因此一次待发送状态不会在清空过程中与新命令竞争。PiPER 控制器会保持最近一次夹爪目标，不要求持续重复同一个目标。

## 不采用的方案

- 不降低整个适配器的发布频率，以免改变六轴轨迹平滑性和现有速度边界。
- 不忽略 SDK `isOk()`，因为反馈线程失效后继续使用缓存关节值不安全。
- 不在运动中自动重启 PiPER 驱动或 CAN；自动恢复可能重新接入已经过期的运动命令。
- 不修改抓取的打开值、闭合值、力矩或候选抓取逻辑。

## 验收标准

1. Python 语法检查通过。
2. arm 后的普通 `_tick()` 消息只包含 `joint1` 至 `joint6`。
3. 收到一次夹爪命令后，仅下一帧包含 `gripper`，再下一帧恢复为六轴消息。
4. disarm 会清除尚未发送的夹爪命令。
5. 抓取执行器仍通过 `/brain_robot_grasp/gripper_command` 请求打开和闭合夹爪。
6. 真机复测时，按 `1` 进入零点复位和观测姿态期间不再出现持续的 `GripperCtrl` 调用；PiPER 驱动和 `/joint_states` 应保持存活。
