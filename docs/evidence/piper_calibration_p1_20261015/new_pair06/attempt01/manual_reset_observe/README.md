# 第五位置：人工复位后原流程返回观测成功，A采集0帧（2026-10-15 18:07 +08:00）

## 本轮授权与结果

用户提出人工失能/复位后由代理回观测、记录，随后确认“已复位”；本轮按此只做原驱动使能→原观测轨迹→SEARCH前停止。用户又明确回答方块与支撑物“始终未移动”，见[same_point_confirmation.json](same_point_confirmation.json)，旧B检查点`1a2e633`继续保留，不重采、不与新位置混配。此确认不是独立接触/中心测量，也不批准抬高支撑物的顶面身份或P2。

**实际返回成功；新观测A仍0帧，本组尚未完成、合格完整仍1/6。** 原B和之前5帧观测预览不覆盖。没有SEARCH/ALIGN/抓取，没有本代理张爪、SDK Reset或硬件失能；其他生产冻结。本轮使用ROS2/PiPER技能核真实路径和反馈，只纠正临时采集调用，不改生产代码/限位/TF。

## 实体运动事实

- 复位后原SDK60样本/59fresh、3秒静止通过；q_mdeg `[-3500,0,0,-27973,18595,41139]`，六轴false，全部在现有任务边界内。不是用“用户已复位”代替真实起点。
- 原`/enable_srv true`后，59fresh/原静止通过、六轴true、q完全不变。原arm首条命令与真实反馈完全一致，没有重演旧J3裁剪；**没有部署`fef28d6`候选，也不是实机验证了候选**。
- 原一键所用launch，经已有P1会话包装去掉抓取executor；原controller运行前设/回读`stop_after_observe=true`。原17点轨迹计划63.4621442秒，START→REACHED实际63.068682秒，原到位容差通过；不是另写基础运动程序。
- 实际理由`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`。bag仅IDLE→PREPARE→STOPPED，无SEARCH/ALIGN；16021条原反馈/3155条命令。轨迹topic包含17点prepare及原`StopLocked→PublishHoldTrajectoryLocked`的2点同姿态持位，不把后者当另一段运动；夹爪topic0条。
- 原软件disarm成功，它停止输出，不是硬件失能。最后有效SDK q_rad `[-0.140040432,0.936027596,-1.259683572,-0.078759660,1.215340924,0.094494148]`、六true/37.0mm。现在所有源退出，无持续监测，不把历史使能值称实时状态。
- 到位后SDK原全窗静止报告rc2、没有连续3秒通过窗，尽管q波动0；J6速度+109/−107、J2−5、J5−11mrad/s脉冲保留。不降原速度条件或把它写成60样本全合格。

见[execution_session.json](execution_session.json)、[motion_review.json](motion_review.json)及完整原bag归档。bag离线分析初版错误假定只有1条轨迹而断言失败；核实原StopLocked持位源码后修正为17点+2点恒值持位，结果可复现，不改实体控制。

## 两次采集失败：不是再次运动失败

1. 首次临时子命令漏了模块搜索路径，`ModuleNotFoundError: collect_static_rgbd`，采集未启动。相机会话2.168255秒，RGB-D0帧；不归咎硬件。原错误argv/日志完整保存，修复仅在临时调用中显式加入test目录，并先离线导入验证。
2. 原位第二次有界会话6.062149秒：原采集器收到302反馈、43同类Info消息、39深度消息、RGB0；原500ms源时间戳规则以`feedback_lost`退出，RGB-D仍0帧。原只读桥308次发布、最后SDK仍新鲜、q与观测一致。RGB在SIGINT收尾同时报告GStreamer无法开流/退出−6，不能仅凭收尾日志断言相机先失败或其唯一根因。

CAN持续ERROR-ACTIVE、RX增长，运动TX3071→12553，两个只读窗TX不增；第二窗末RX22631584/TX12553。不是已证明USB-CAN持续停流，不重载/重启接口。SDK局部反馈或订阅调度时限的具体差异未逐条落盘，仍待离线启动/时戳证据补全。两次无图后按阶段规则停止追加实体相机会话，不第三次盲重开，不再回位。

**没有原图，因此不能评价当前方块是否完整入画/深度是否空洞，也没有新的CameraInfo配对或工厂GET。** 不用旧工厂值冒充本次读值，不补深度或编造方块中心。`actual_runtime_model.urdf`/FK只描述最后真实q的工具原点，不是测得的方块几何中心。

## 退出与验证

运动主包装返回0表示到位/受控退出，但原MoveIt在SIGINT收尾exit−11、原driver需精确SIGKILL（−9），均原样留存，不称全部进程干净退出或已解决其原因。全部本轮进程实际已退出，无自动失能；之后没有继续实体试验。

152项原适配器/采集/质量测试重新通过，生产五路径SHA（候选adapter以本轮起点`fef28d6`为准）与运行副本旧SHA均核验不变。实际model SHA `0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82`。根仍34GB可用，无本轮删除、无固件包提交、未推送GitHub。

- [assessment.json](assessment.json)：运动、采集、实际q/FK、边界与未完成项。
- [runtime_manifest.json](runtime_manifest.json)：42个原文件及压缩包SHA；`runtime_closed.tar.gz`约1.1MB，含原bag/SDK/所有失败日志/有界临时调度源。全部解包逐文件hash验证，不需访问/home目录。
- [verification.json](verification.json)：归档和测试核验。原SDK和[same_point_confirmation.json](same_point_confirmation.json)亦以便携JSON保存。
- 临时运动脚本仅是本组服务调度记录，**禁止直接重放它**；重新运动必须核当时真实状态与当前授权。可只读重放包内`analyse_motion_offline.py`，不得执行运动包装。

## 下一步

机械臂已经到观测，无需用户再次复位/摆放，也不再以旧B的J3越界作为当前阻断。先离线核采集订阅启动/反馈时间戳与RGB启流，提出只改采集调度或诊断字段的针对性方案，获准后才做下一次有界静止采集。原500ms/静止/800内点/20帧合同、生产TF和靠近逻辑不放宽。抬高支撑物顶面身份仍独立待核；第五B不丢弃，但整组不能虚报通过。
