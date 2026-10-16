# 原链当前姿态保持验证：短空窗恢复，诊断提前终止

2026-10-16，起点`d9471e2`。用户“好”批准原driver/adapter当前姿态保持30秒，不改变位移目标或操作夹爪。

## 实际执行与结果

- 复用健康can0/UHCI，未重连/重载/reset。原SDK10秒准入rc0：99fresh/9.839秒、六q波动0、六轴true，原静止条件通过。
- 从原installed launch中只选择原adapter Node（原全部参数），配原driver auto_enable=false；无Servo/MoveIt/任务/相机。原enable_srv true打开软件发送门，再enable_motion/arm；没有发布轨迹、JointJog或夹爪目标。
- 14:16:16.183开始保持。记录982条六轴命令、5135反馈，所有六q完全不变，所有命令均无gripper名称/effort。CAN TX0→2945（含原初始化和服务）；末RX1469076、ERROR-ACTIVE、错误/bus-off0、无新内核日志或非法echo。
- 14:16:35.679—36.357，独立CAN读取有0.678535秒空窗；ROS反馈有0.868145秒空窗，命令接收有0.695443秒间隔。随后原始CAN及ROS反馈自行恢复，未作任何USB/CAN恢复操作。原driver日志记录抑制输出/恢复。
- **30秒验证未完成**：本次诊断包装器在ROS反馈本地age超过0.5秒时断言退出，20.265549秒后软件disarm响应成功。不是原adapter25秒超时触发，也不是此前持续不恢复的接收停流。原脚本rc2及错误保留，不能改写为通过。
- 末SDK整窗rc2、59fresh，原连续50fresh/4.915430秒静止子窗通过；前后六q_mdeg一致`[-8254,51759,-69720,-3692,67818,5017]`，末六true、夹爪99.6mm。只是末次反馈，不宣称持续监测或已到观测。
- 所有自有源退出：adapter0、driver原2秒宽限后−9（原日志照存）。software disarm不等于硬件Disable。无硬件失能、复位、夹爪、搜索或抓取命令，六生产SHA不变，旧板仍2/10。

## 原件与可复核性

`execution.json`为完整执行/原服务/参数回读/命令/SDK质量/内核记录；`assessment.json`为离线统计与结论边界。三个`.py`为本轮诊断与离线归档脚本，不是生产修改。

`runtime_originals.tar.gz`保留13个原文件，包括SDK前后原JSON、driver/adapter日志、全部ROS消息JSONL、CAN二进制和三个脚本。`runtime_manifest.json`逐件SHA/长度，已解包逐件回读比对。home原目录`/home/johnwick/brain_robot_logs/usb2_hold_20261016.gyttMv`亦保留，未删除原始数据。

CAN二进制每条24字节：本机标准端序`=Q`用户态读取epoch_ns（8字节），随后Linux classic CAN frame（16字节）。不是硬件/kernel接收时间戳；因此不能凭读取空窗直接认定总线物理上没帧。observer未收到driver控制帧loopback，不能用缺0x159单独证明无夹爪发送，需结合原ROS六轴命令和未改驱动源。

## 下一步与范围

本轮定位到诊断调用层提前结束，**没有修正它、没有重复保持**。后续可提仅局部调整测试包装器：短空窗只记录，继续保留原driver输出抑制/原adapter25秒超时与终态收尾，再以明确范围做有限30秒保持。不改冻结生产门或相机TF，不自动扩大为一键/观测/采样。

当前不需要操作者重启、重连或挪板。短空窗原因尚未确定：USB缓冲、guest调度、SDK/ROS或真实总线暂停均不能仅此排除；不宣称USB2已永久修好或xHCI一定根因。原60秒被动/J4成功不重复。仅本地Git留证，未推送，既有同步分叉/历史审查/发布范围阻断不变。
