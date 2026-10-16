# 夹爪闭合控制核查：先有尺寸、有界低速接触，再判断夹持

2026-10-16 21:44 +08:00。用户看到本次闭爪过快，要求搜索官方资料，考虑目标尺寸、放慢闭合和电流接触判断。本文件是研究与局部修改提案，**尚未修改或部署夹爪控制，也没有再发送运动、开闭、清错或失能命令**。本次对象仍为紫色方块，不把塑料水杯保护效果当作已经验证。

## 官方明确事实

1. 官方 PiPER SDK 的 GripperCtrl / CAN 0x159 给出开口（0.001 mm）、effort（协议标为0.001 N·m）、状态码和零点字段；这个接口没有独立夹爪速度字段。不能把机械臂 ModeCtrl 的整体速度比例或消息发布频率当作已验证的夹爪速度设置。来源：[接口实现](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/interface/piper_interface_v2.py)、[控制帧定义](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/piper_msgs/msg_v2/transmit/arm_gripper_ctrl.py)。
2. 0x2A8 给出行程、effort及状态；effort被协议定义为扭矩，**不是夹爪原始电流或经过标定的指尖夹持力**。过流位是异常标志，不是正常接触开关。六轴高速反馈的电流不能冒充夹爪电流。来源：[官方夹爪反馈定义](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/piper_msgs/msg_v2/feedback/arm_feedback_gripper.py)。
3. ROS 2 Humble 的成熟夹爪控制器区分位置到达、最大effort、低速停滞及持续时间，不把“动了一点”自动等同于抓住。可复用这些语义，但不能把其默认阈值照搬到本机；停滞也可能是卡滞而非物体。来源：[Gripper Action Controller](https://control.ros.org/humble/doc/ros2_controllers/gripper_controllers/doc/userdoc.html)。

以上链接为2026-10-16只读检索的官方当前源码/文档，不是本机已经升级到该SDK的证据。上游README出现V3协议建议，本轮没有升级SDK、更换驱动、刷写、ResetPiper、MasterSlaveConfig或写零点。活动V2软件及本次真实反馈单独以SHA和原CAN记录为准。

## 本机已证实的实现

- 原执行器 CommandRealGripper(false)直接发 gripper_close_value=0；任务张爪100000（100mm）。适配器把一个开口目标作为有界重复帧转发，配置gripper_effort_nm=1.0；驱动换算为1000发给GripperCtrl。**没有开口斜坡或接触闭环，不是慢速力控。**
- 当前适配器和驱动都把effort限制在0.5～3.0 N·m标称范围。因此仅把上层数值写为0.1，并不会真正得到0.1；不能宣称已经低力。1 N·m也不等于1 N指尖力，没有传动/接触位置及效率标定就不能换算。
- WaitForGripperCommand的allow_contact_stop分支只检查开口相对闭爪前变化≥0.001m。没有effort阈值、停滞持续时间或物体存在判断。**变量名写了contact，不代表实现证明了接触**。本次空爪0.4mm后仍进入LIFTING/HOLDING，已证实不能以该状态报成功。
- [原CAN离线统计](gripper_trace_review_v2.json)：本日志有16458条0x2A8。空闭合期间93.4→5.0mm的接收时间差约0.174669s，按反馈算平均约506mm/s；只是主机接收时间下的运动描述，可能受批量接收影响，不是认证物理速度。实际effort原值范围−685～437；**空载加速就有明显峰值**，不能随便选一个绝对阈值就判接触。0x159未被这份candump看到，不否认实际调用；驱动调用日志和ROS命令单独保留。

## 拟进行的最小修改，待用户确认后实施

只改原夹爪命令链，不改靠近算法、TF/TCP、六轴限位或另外建立控制节点：

1. 仍可全开100mm；用目标在两指闭合方向上的投影宽度，加估计误差余量，形成预闭合开口。29mm方块在不同偏航下投影宽度并非恒为29mm，不能简单命令29mm，更不能只靠尺寸证明接触。
2. 复用原适配器唯一发送链，改为小步开口设定值渐变；反馈确认实际速度及滞后。渐变只约束参考值，不冒称底层硬件速度已被严格限制。初始速度/保持effort须在现有有效范围内单独小样验证，不预承诺对薄壁水杯无损。
3. 用新鲜开口差分、空载摩擦/加速effort基线、持续低速和effort上升、预期物宽区间联合形成“接触候选”；异常位独立处理。不能仅凭一个电流/扭矩峰值或“开口动过1mm”放行抬升。
4. 确认接触后把位置目标收敛到实际接触附近并用经验证的轻保持effort，**不再持续追0mm**。仅停止发新消息不一定撤销固件已经锁存的0mm目标。
5. 目标尺寸/夹持区判断和接触反馈相互核对；空爪全闭、反馈陈旧或不合理停滞不得报告“夹到”。此为用户明确要求的夹爪行为修正，不扩展成一串新的靠近门。

本轮没有因这项研究让用户重新摆物体、重启或重复CAN恢复。下一实测先解决夹爪闭合策略，再结合已记录的末段落点偏差安排单变量试验；不能把“下15mm、前15mm、减速、换力矩”同时混改。
