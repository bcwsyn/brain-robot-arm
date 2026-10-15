# 第六留出组新位置A：60/60通过原顶面质量，新B待采

2026-10-15 21:41 +08:00。用户确认方块稍移近后，只读原RGB-D与真实关节反馈。未发送使能/arm/关节/夹爪/失能/Reset/MasterSlaveConfig，未重载CAN、刷写或修改生产源/TF。`new_pair07`仍留出；这只是合格A，不是完整点对/标定验收，没有新B，禁止跨位置复用旧B8f8eed6。

## 结果

- 原采集45.083738秒60套，相机52.969667秒/80秒（含收尾），工厂GET在采集后，全部自有源退出。RGB224/深度683/Info860/反馈2158，原等待3秒静止历史11次/Info不同帧37次原样保留，没改接受规则。
- **60/60原好顶面**：804—892真实内点，中位858，原800/20不改。覆盖97.895%—100%，表面60帧均438mm（静态重复性，不是绝对精度），RGB完整20×21/[151,119,20,21]。桌面参照高度中位28.672mm；法向差A/B中位4.499°/4.983°，仅记录不新增门。已目视原RGB/绿色顶面投影位于方块上表面，原质量报告物理确认字段保留，未将候选中心当已批准绝对坐标。
- 六轴逐帧波动0，实际q(rad)：`[-0.134528128,0.9445053800000002,-1.26041622,-0.07797468,1.216178236,0.09698864]`。每帧自己的新鲜JointState、整数戳、同戳完整Info与实际安装模型FK保存；不拿观测命令角替代实测。
- 补录SDK在全部相机源退出后，60/59fresh、5.821秒、q波动0，但原全窗速度最大11mrads导致原静止false/rc2。**失败原件保留，不声称SDK全窗通过**；也不临时把此全窗条件加为已通过A逐帧静止/新鲜度规则的新门。末鲜六true/99.4mm是历史遥测，不是持续监测/物理接触确认。
- CAN RX53274911→53401931/TX15662不增；直接复用健康链路，无恢复/USB重载。六冻结源SHA前后一致，home实际旧adapter不变，候选fef28d6未部署；81回归通过、根34GB余量。生产/各门冻结遵循ros2-piper-debug与surgical-change技能，本轮只新增采集证据和交接。

## 相机源占用失败没有隐去

首轮实际存在用户预览PID89463（device0/320×240/5Hz/show_camera=true/域0/现有UDP profile）。代理错误地在检查结果返回前启动原coordinator，自有cam2image打开video0失败；就绪20秒反馈955/depth346/Info417/RGB0，正式采集未启动。自有源已按原finally退出，随后尝试只中断已退出PID89607返回无进程，原命令结果保留在进度文档。

现有预览仍只有1个话题publisher，但前窗无RGB；核对参数及ROS环境后，仅精确PID89463按SIGINT→TERM→KILL退出释放相机，见[精确相机源处置](preview_source_replacement.json)。然后原coordinator单一新彩色源会话实际采满；未杀其他进程、未动机器人/改DDS/backend/QoS。不将这归责机械臂/CAN，也不宣称预览为何阻塞的永久根因已修好。[失败摘要](initial_source_conflict.json)和完整原失败会话均入归档。

## 数据及复现

- [portable_good20/manifest.json](portable_good20/manifest.json)：从60个**原合格顶面**中均匀选20原帧，含完整RGB/16位深度/同帧Info/实际q/FK/当前工厂内参与D→C、配置/原SDK，50资产SHA核验。未知安装TF/TCP及物理中心不伪造，工厂镜间外参不当安装标定。
- [quality_all60/report.json](quality_all60/report.json)：完整60逐帧质量与候选/法向/采样计数，SHA`11440888014f3ecbd47551f390822f0377f17e3152819cee1dc82e5f3a0fb3db`。[assessment.json](assessment.json)只是派生状态，B_pending/formal_pair=false。
- [runtime_closed.tar.gz](runtime_closed.tar.gz)：完整60图及原observer/Info/实际反馈/工厂/SDK/所有日志、完整60套便携导出与首轮源占用失败，165实际归档成员。120个重复原PNG不再双存：在[runtime_manifest.json](runtime_manifest.json)逐条列出其同字节成员别名，全部SHA回读验证；没有删除或改写源原件/补深度0。解压后可直接用portable_all60重算，原日志里的绝对路径仅为溯源。
- [A_execution.json](A_execution.json)准确子进程argv/时序/退出码、[review_execution.json](review_execution.json)SDK及离线命令真实rc，[执行脚本](executed_sources)、[打包复现](package_offline.py)、[junit.xml](junit.xml)81测试齐全。本机完整目录`/home/johnwick/brain_robot_logs/new_pair07_attempt03_A.9r_fp1bb`；Git内原件/归档可独立阅读，不依赖本机日志盘。

环境沿既有Humble/piper_ros/piper_ws/ros2_ws overlays及`PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml`。执行仍为原`capture_calibration_session.py --output .../session`；后续原`collect_calibration_sdk.py --duration-s 6`（rc2照存）、`review_calibration_capture.py`、`export_calibration_bundle.py --cube-edge-mm 29`、`calibration_p0_quality.py`，其余rc0。完整argv见review/execution，不改工具。

## 下一步需要用户现场摆持

保持这个方块与桌垫原位，按前几组有支撑示教方式手摆机械臂，让两指实际夹紧方块，仍贴桌、不提起。到位回复后代理仅只读采新B，并确认A→B同物理点。若手摆夹紧带动物体，则不能硬配本A。当前不再移动方块/重复合格A，不自动松爪/返回/搜索/拟合或部署TF。

P1登记质量合格A按组ID计为2（主A的new_pair02+此补采new_pair07），**正式点对批准仍0**；不是六合格点对。未推送GitHub。
