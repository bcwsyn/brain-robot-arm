# 为移走方块执行一次原位张爪：实测37→99.4mm，未回观测

2026-10-15 22:34 +08:00。上一条要求“先授权原位张爪，松开后再拿走方块”，用户回复“好的”。本轮仅执行原位开爪，没有把授权扩大为观测返回/搜索。此为控制动作证据，不是新标定样本；原第六A/B与32mm板预览不改。

## 实际命令与结果

1. 原只读SDK10秒，复用既有任意连续3秒/30样本静止条件，六轴已使能且当前q在原任务范围内；健康CAN直接复用，不重载链路。
2. 原driver以`auto_enable=false`启动；[节点筛选包装器](piper_original_adapter_only_launch.py)从实际安装的`cube_visual_search.launch.py`中只选原adapter Node，所有参数不改，不启动MoveIt/Servo/controller/grasp/camera。
3. 调用原`/enable_srv true`同步**已使能**六轴的驱动本地门，再原adapter `enable_motion/arm`。接管q来自当前反馈，首帧与arm时实测一致，没有六轴观测目标或自写轨迹。
4. 只发1次`/brain_robot_grasp/gripper_command`、`name=['gripper'] position=[0.1]`。原adapter输出80个100mm显式夹爪帧，实际开口37→99.4mm，满足原100±3mm到位判断；随后软件disarm，末被动SDK再次确认99.4mm/六true，源均退出。

原driver日志含clear/enable握手及100000µm开爪，`set_zero=0x00`，不是夹爪写零、ResetPiper、MasterSlaveConfig或固件操作。未调用`enable_srv false`/硬件失能。完整命令与反馈见[execution.json](execution.json)，控制编排[piper_board_open_only.py](piper_board_open_only.py)只是本次原接口调用，不是新增生产一键脚本/控制程序。

## 命令bag及六轴实际变化

[bag_audit.json](bag_audit.json)核对3009条消息：关节指令86/反馈2922/夹爪输入1；其中80指令带100mm夹爪，6条仅持位。**arm_trajectory为0，没有观测/搜索/抓取轨迹**。全部86关节q可在记录窗实际q中找到完全匹配，但这只说明目标来自已有实测，窗口匹配不证明每帧时间因果，也不证明六轴物理绝对不动。

实际末−初：J2+0.042977°、J3+0.315832°、J5+0.048974°，J1/J4/J6为0；J3峰峰0.007832356rad（约0.449°）、J5峰峰0.004308668rad。原因未证，不猜测为任何人/硬件或宣称零运动。原完整SDK/持位指令/反馈皆保留，末6秒SDK原静止条件通过；没有后续自动调角或补偿实验。

CAN RX60649761→60701566，TX15663→16015(+352)。本轮确有使能门同步/持位/夹爪命令，不能称只读或用TX增长推断通信错误；未做链路恢复。六冻结源SHA前后一致，实际home旧adapter未部署候选。driver/原launch依赖SHA仅为执行后快照，见[runtime_dependencies.json](runtime_dependencies.json)，不冒称它们已记录启动前SHA。

## 保存与验证

- [assessment.json](assessment.json)：范围、真实开口/使能、微小六轴变化和待用户移走状态。
- [runtime_closed.tar.gz](runtime_closed.tar.gz)、[runtime_manifest.json](runtime_manifest.json)：18个原文件无损归档，含全部三窗SDK、日志、SQLite命令bag/metadata、原会话执行记录，逐成员SHA回读验证；没有删数据。Git端可解压读取bag，不依赖本机日志路径。
- 原适配器77项回归通过：[junit.xml](junit.xml)，不等于机械臂完整抓取验收。六冻结生产源未变，root33GB可用。
- [audit_board_open_bag.py](audit_board_open_bag.py)只离线解码bag，不初始化ROS/访问CAN；[package_offline.py](package_offline.py)为本轮归档脚本。原本机目录`/home/johnwick/brain_robot_logs/piper_board_open_only.fpc9klxm`；未推送GitHub。

**现在用户可以取走已松开的方块，保持棋盘格固定。** 拿走后再明确授权沿原已有轨迹回观测、SEARCH前停、只拍完整棋盘格。当前没有该返回许可，不自动继续运动、搜索/抓取/失能或手眼标定；原生产/P1验收冻结不变。
