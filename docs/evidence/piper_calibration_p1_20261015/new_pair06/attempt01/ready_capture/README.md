# 获准的采集侧修复与单次静止实测（2026-10-15 18:36 +08:00）

## 本轮范围与结论

用户明确“我同意修改，继续执行任务”，接续`469dc08`的采集侧方案：分离就绪/正式采集、补时间证据、先离线验证再单次原地复核。按ROS2/PiPER及surgical-change技能执行；只修改test目录采集工具，不改生产驱动、适配器、搜索/靠近/抓取、限位、模型、TF、DDS或一键脚本，不部署此前adapter候选。

**调度与诊断已实现并通过216项离线测试。真实四源就绪通过、正式采集跑满55秒且未触发反馈超时，但RGB只出首帧，此后不再出帧，因此正式A仍0套。** 不把源就绪叫连续RGB成功，也不把它计入20合格样本。单次源已退出，没有自动重开/新的实体尝试。

## 最小代码改动

- `collect_static_rgbd.py`：每话题最近接收/源戳、ROS/wall/monotonic时间、128条有界记录；触发时解释原失败类别。原`checked_packet`、`feedback_lost`、`settled_feedback`、同步器、原帧保存回调等AST完全不变，仍120ms/500ms/3秒静止/500ms保存节流/原完整深度Info。
- `calibration_readonly_feedback.py`：128条实际SDK源戳/本地采样/转发抑制记录；原parser、`feedback_values`和真实源戳/新鲜度规则不改，不以timer替代源戳。
- `wait_calibration_ready.py`：有界四话题真实点对检查，沿用原`checked_packet`；只订阅，不保存像素或发控制/服务。
- `capture_calibration_session.py`：命令导入预检→只读CAN健康复用→原桥90秒→就绪20秒→原采集60套/55秒；相机总80秒、源各开一次，不自动重开。就绪进程退出后才启动正式采集；工厂GET仅在正式采集结束、有真实已存点对且剩余预算允许时执行，本次未执行。
- 新测试`test_calibration_session.py`覆盖源戳不改、失败分类、原接受/保存逻辑AST一致、就绪未成不采、原反馈失败不重试、超时只清理本会话、原位源只启动一次等。旧用户改动`test_near_depth_wiring.py`不纳入。

## 实际检查与会话结果

1. CAN原有UP/ERROR-ACTIVE，RX增长；直接复用，没有USB/模块/接口恢复。原SDK60/59fresh、q与上次观测完全相同；q波动0但速度字段脉冲，原SDK静止报告不通过，原样保留，不能叫全窗通过。原采集器仍独立按实际位置做3秒静止检查，无运动命令。
2. 原depth先启动、原RGB320×240/5Hz参数不变。原先3秒即结束采集的问题不再阻止启流：相机启动6.447507秒后就绪，收到238反馈/63深度/70Info/1RGB。真实点对跨度85.585641ms、最旧年龄88.352794ms，q仍原观测位置。
3. 就绪进程退出后开始正式采集（就绪结果后约0.197秒）。**原正式采集实际55.001722秒**：2650反馈、1135深度、1338Info、RGB0，matched0、rejected空、stop_reason=null、退出码2（未采满60）。没有再次`feedback_lost`，没有深度质量/面身份/800点/中心/TF或关节门参与拒绝。
4. 原`cam2image`日志只有一次`Publishing image #1`，该帧已到达就绪订阅者；其后到正式采集结束没有第2条发布日志/没有RGB消息。全相机会话63.806536秒，在80秒总预算内；没有用延长预算伪造采集成功。RGB收SIGINT后仍需精确SIGKILL−9，退出细节完整保留；其他本轮源已退出。
5. 原反馈末接收年龄约3.921ms、深度1.366ms、Info1.661ms，桥末实际SDK仍新鲜；q仍`[-.140040432,.936027596,-1.259683572,-.078759660,1.215340924,.094494148]`，六true/37mm。CAN RX26639417→26794141，TX12553全程不增。没有实体使能/arm/开闭/失能/Reset；当前无持续监测，末使能只是最后记录。

## 已定位层级与尚未知的内部原因

本次明确隔离为**RGB首帧之后无法持续供图**，不是此前的启动窗口太短/反馈时限失败。没有第二帧到来，所以不能只通过放宽采集门或要求20套来解决；不扩大到CAN/限位基础巡检。未额外开流，未改变RGB backend/QoS/驱动。

已装`ros-humble-image-tools 0.20.9-1jammy.20260325.222339`。参考[官方Humble实现](https://github.com/ros2/demos/blob/humble/image_tools/src/cam2image.cpp)：同一timer回调依次取帧、检查空帧、写发布日志和调用publish。因此仅有一条发布日志，尚不能区分取帧/空帧路径、timer调度或发布调用阻塞。首帧确实被就绪者收到，但不等于整个回调已返回。该上游分支不冒称与已装二进制逐行相同；精确0.20.9源码URL读取失败已明示，不据参考强行套DDS/相机参数修复。

下一须针对RGB这一层提出最小带调用/帧计数证据的只读复核方案，按用户“改代码前告知同意”的规则再批准。不能直接自动再开相机、替换生产相机发布器/后端/QoS，不能重走机械臂运动。只读采集工具已经具备、不再重复调同一时间预算。

## 数据、磁盘和Git交接

- [assessment.json](assessment.json)：实测阶段、时长、消息数、真实q、原准入AST/生产SHA及未完成项。
- [selected_for_analysis.json](selected_for_analysis.json)：本次可选合格数**0**，不编造20套；没有新图片需要清理。以后原60套只挑20合格进入分析，其余原始数据验收前压缩隔离，本轮无删除。
- [readiness.json](readiness.json)、[capture_summary.json](capture_summary.json)、[feedback.json](feedback.json)：有界真实时戳诊断；就绪像素未保存，不冒充当前目标照片或可导出的RGB-D样本。
- [runtime_manifest.json](runtime_manifest.json)/`runtime_closed.tar.gz`：17份原文件无损压缩、逐一SHA验证；原B/旧预览/两次0帧失败不覆盖。
- [executed_sources](executed_sources)：实际执行的4个采集工具源码与启动前后SHA完全一致；[junit.xml](junit.xml)为216通过的原报告。10个原接受/parser/保存函数AST核验通过。
- [package_offline.py](package_offline.py)只离线归档；源输入路径记录在包中，不能重放会话当自动实体授权。生产五路径SHA及home adapter旧hash均不变，候选未部署；根仍34GB可用。

第五B检查点仍`1a2e633`，方块/支撑物未移动的确认不重问；新正式A0、合格完整1/6、5个位置有原始记录。未做拟合/部署/抓取，未推送GitHub。下一聚焦RGB持续出帧，不再要用户复位/摆放。

离线验证命令在规范仓库：

```bash
source /opt/ros/humble/setup.bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_session.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_static_rgbd.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_readonly_feedback.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_piper_jog_adapter.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_ir_depth_diagnostic.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_native_depth_diagnostic.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_depth_controls_readonly.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_capture.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_quality.py
```

实际附`--junitxml=/tmp/piper_acquisition_ready_20261015.xml`，返回0。实体命令仅本轮已批准的一次`capture_calibration_session.py --output NEW_DIRECTORY`，完整环境/原argv在execution中，不列为可自动重放的一键动作。
