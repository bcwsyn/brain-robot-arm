# 第五位置A60补齐，20完整面候选隔离（2026-10-15 18:50 +08:00）

用户授权代理自行处理采集侧，只在需第六次实体摆放时参与。此次按ROS2/PiPER及局部修改技能核对真实源、进程、图像与调用证据，**未修改生产或采集接受代码**；只做有界相机对照、原只读采集和离线归档。原B检查点`1a2e633`与操作者“方块及支撑物始终未移动”确认保留，不重采/覆盖。

## 实测与未解决项

1. `RGB_only`：原cam2image参数320×240/5Hz，14秒含启动，strace记录系统调用；发布40帧，退出0。此条件未开深度，不能代替RGB-D验证。
2. `RGB_depth`：原Astra深度先开4秒，再原RGB，同一被动图像记录器保持订阅。RGB发布51帧；实际原图`probes/RGB_depth/original_first_rgb.png`可见完整方块位于黑色抬高支撑物上。RGB与记录器退出0，深度清理需−9，原日志保留。未运行机器人SDK或控制。
3. 原`capture_calibration_session.py --output NEW_DIRECTORY`：无参数/接受逻辑变化，附外部监视，只在RGB单帧停滞时才对精确自有PID取栈。**此次没停帧，没有实际gdb附加**。原四源就绪后44.549931秒保存60/60套，收到2134实际反馈/711depth/898Info/218RGB；197同步匹配，13次原3秒静止不足及42次原非同帧Info拒绝如实保留。相机总53.045509秒，小于原80秒；正式结束后工厂GET成功，当前序列`CC1365304DG`。

因此当前连续RGB与原始60套采集已成功，但**历史“RGB只首帧”的内部根因仍未知，不能称已修好或归咎CAN/磁盘/操作者**。三个不同条件的日志、argv、退出码与执行探针源码都保存；没有换后端/QoS/DDS、刷新接口、重载USB、扩大时限/阈值或重跑机械臂观测。此次cam2image实际日志包含GStreamer路径，不能仅按历史口头“内核V4L2”推断已显式选CAP_V4L2；未修改该路径。

## 数据质量与20套的含义

- 60帧实际q六轴波动0，仍原观测位置；原同戳深度Info、120ms配对/500ms新鲜/3秒静止/原uint16零值均保留。表面深度中位60帧均281mm，是静态表面量，不是验证过的方块中心或毫米绝对精度。
- 原完整面候选60/60，原生平面内点2033—2112；**原自动好顶面0**。原环带判据假定方块直接放在所选局部桌面，当前抬高支撑不满足这一前提。原报告不改，不将主面候选冒充顶面或合格点对。
- `portable_review20`均匀选原60中的20套完整面候选，原RGB/深度字节与SHA不变，含逐帧真实q、完整Info、实际模型FK、当前工厂D→C/内参/安装配置快照。`capture/summary.json`明确为派生子集；原60套摘要在`source_capture_summary.json`，不伪装新采20或凑满20好顶面。便携manifest含50资产，全部核验。
- 便携`raw_sdk_samples`明确复用不可变的**夹持B SDK原件**，不是本次A新SDK采样；A真实反馈在各observer记录中，桥末真实状态在`feedback.json`。两侧未知中心仍未确认，不能凭方块看似静止或面拟合稳定就填真值。
- 严格质量合格完整仍1/6；已有五位置原始记录不等于五个合格拟合组。后续独立面身份/法向/参考点审阅保留，不自动解算或部署TF。第六位置预定留出。

## 归档与复现

- `all_raw_closed.tar.gz`及`raw_manifest.json`：229原文件，包含本次60完整原始点对、原始日志/反馈/相机工厂数据和两个探针（含全部已录原图/系统调用）；逐文件SHA及archive SHA核验。全部原始数据仍在，未删除坏帧/零深度或不可逆清理。原40套未入20审阅子集，压缩隔离而非混入分析。
- `quality_all60/report.json`：60帧原判据；`selected_for_review.json`明确原60索引、20候选及0好顶面。
- `execution.json`、`readiness.json`、`feedback.json`、CAN前后、`factory.json`为本次原输出；执行源前后SHA同一，五生产SHA及实际home adapter旧SHA不变，未部署`fef28d6`候选。
- `executed_probes/`为实际执行的三个临时无运动包装器，**归档不是今后的自动实体运行授权**；`package_offline.py`只做离线导出，在全新输出目录运行，默认固定原输入路径，异机先解压并修正明确路径，不覆盖旧输出。
- `junit.xml`：216项回归返回0，覆盖采集/session/反馈/适配器/深度诊断/原质量。不把单元通过叫抓取或标定成功。

运行环境沿原ROS Humble和三个home overlay、原FastDDS profile；无用户site混入，`PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1`。原采集命令与所有argv见execution；不要照归档自动运动。原始完整数据离线重审可用：解出`formal_A/capture`，沿现`review_calibration_capture.py`/`export_calibration_bundle.py`先重建完整便携包再执行`calibration_p0_quality.py`；原输入SHA在manifest中，生产相机TF不参与此取样评审。

本轮无运动/使能/arm/开闭/Reset/硬件失能、CAN恢复，TX不增加，RX持续增长；全部自有源已退出。末次SDK六true/37mm/q仍观测是末次实测，不是此刻持续监测。根34GB可用，未删除资料，无GitHub推送。

下一仅需用户第六次实体摆放：先只摆同一方块到新位置、机械臂保持不动，当前静止视野预览后再安排同点夹持B，见[第六位置准备](../../../new_pair07/README.md)。不再重复本次已成60套或重返观测。
