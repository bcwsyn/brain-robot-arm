# 第六attempt03夹持B已只读保存，A→B同点确认待答

2026-10-15 21:53 +08:00。用户回应手摆要求“已完成”，原图可见方块位于两指之间。本次只读SDK及5对原RGB-D，没有任何使能/arm/运动/开闭/失能/复位/CAN恢复。B与[合格A](../observe_capture/README.md)检查点7399d18链接，**不复用旧位置B8f8eed6**；`new_pair07`固定留出，不拟合/部署/推送。

## 记录与验证

- 被动SDK6秒60样本/59fresh，跨度5.827703秒，六轴波动0，原速度≤1/3秒/30样本规则全窗通过、rc0。实际q_mdeg=`[-6689,111368,-68208,-6043,44307,11363]`；原驱动rad=`[-.116682916,1.942703392,-1.189820352,-.105414092,.772891308,.198216172]`；六true/夹爪37mm。毫米反馈未卡尺核验/不等于接触力，SDK不证明实际抓住。
- 原采集5帧8.325984秒、相机17.382289秒/35秒，真实反馈297/RGB34/depth54/Info73，原静止历史6次/Info非同帧4次拒绝照存。五原RGB与uint16深度、完整同戳Info、整数源戳、实际q/FK及CC1365304DG工厂数据保留，源全部退出。**B不要求目标深度**，5帧目标深度0不阻夹持侧记录，原RGB下沿裁切不改/不冒充A。
- 实际模型SHA与A同为`0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82`，工厂内参/D→C完全相同。B的base→gripper_base平移约[358.281,−48.736,144.552]mm，是模型工具参考，不是未经验证的方块中心。q在原任务限位内仅为只读信息，**不是新轨迹/回位授权**。
- B测量窗RX54924980→54964896/TX15663不变；A末15662→B前15663之间+1未解码/未归因，不声称跨会话全程无发送。六冻结源SHA前后一致，home旧adapter未部署候选。未启动驱动/控制器/SEARCH/抓取或改生产TF，根34GB可用。
- 72项原反馈/配对/导出回归通过，[junit.xml](junit.xml)。便携19资产与原始归档35成员逐SHA验证，原始数据未删、未填深度0。[runtime_manifest.json](runtime_manifest.json)可核验归档，[portable/manifest.json](portable/manifest.json)是Git端直接读取入口，不依赖本机日志盘。

## 配对状态不能猜测

已异步询问“A拍照到B手摆期间，方块是否始终原位、未带动或重摆，且现在真夹紧仍贴桌”。当前尚未明确答复，见[operator_confirmation.json](operator_confirmation.json)的null字段；用户“已完成”及其前置指令上下文保留，但不凭照片/q推断零移动或接触力。原SDK/图像永不回写。确认后只改独立派生确认/链接，不需要重采这次B；若方块确实移动，不硬配本A。

[paired_sources.json](paired_sources.json)保留A的commit/manifest/质量SHA、两侧实际FK矩阵、同一模型/工厂校验及未知夹持偏移null；只有原件齐全，不等于点对批准或六合格。P1仍仅2个组ID有原质量合格A，正式点对批准0；其余旧数据问题不靠此留出组凑数。

## 法向差离线参考（不阻采集）

[A_center_normal_sensitivity.json](A_center_normal_sensitivity.json)针对A已选20好帧，保持29mm约量/原配准，分别沿原顶面法向和桌面法向从同一个面中心内推14.5mm，并统一到彩色光学坐标系。两种中心相差0.845—1.441mm；原顶面法中心候选中位[3.045,43.015,450.937]mm、相对中位最大时变1.388mm。它只是法向选择敏感性，不是绝对误差保证/机器人相机安装标定，不改变原筛帧或换用桌面法向，不进入P2拟合。

## 执行与复现

[executed_collect_B.py](executed_collect_B.py)在冻结SHA核验后运行[旧成功五帧采集器原样副本](executed_original_capture.py)。旧wrapper里的preview/Afalse/Bfalse标签保留；实际B角色在本次调用及assessment说明，不静默改原标签。SDK→只读反馈桥→真实四源就绪→原5帧采集→工厂GET→退出，总无自动重开/运动。环境仍既有Humble/piper_ros/piper_ws/ros2_ws overlays和现有UDP profile/域0，无backend/QoS/DDS改动。

之后原`review_calibration_capture.py`/`export_calibration_bundle.py --sample-id new_pair07_attempt03_grip --cube-edge-mm 29`生成实际FK/便携包（rc0）；完整命令见[B_execution.json](B_execution.json)、[execution.json](execution.json)和[package_offline.py](package_offline.py)。本机原会话`/home/johnwick/brain_robot_logs/new_pair07_preview.hbtyou_k`、调用`/home/johnwick/brain_robot_logs/new_pair07_attempt03_B.rblyf2rg`，完整原图/SDK/日志也在[runtime_closed.tar.gz](runtime_closed.tar.gz)。

下一仅待明确同点/接触事实，再离线审阅P1；没有新松爪/返回授权，当前不动机械臂，不重复已采A/B，不自动搜索/闭爪/失能。
