# 第4位置IR诊断与下一摆位准备（2026-10-15 16:46—16:50）

用户已授权“自行推行，只需要让我进行下一次摆放即可”，本轮完成采集诊断侧的局部实现和有界对照；**不再等待IR启用许可，不扩展为生产控制、曝光/增益/激光设置或整批运动许可**。原位张爪和回观测早已完成，不重复执行。原B `2b1becb`、正式A60帧/0好顶面不覆盖。

## 实测结果（失败和部分成功均保留）

|会话|隔离运行参数差异|相机时长（含退出）|深度/IR落盘|RGB-D诊断图|结果|
|---|---|---:|---:|---:|---|
|unsupported_default|enable_ir=true，沿用旧IR 640×480|26.329s|36/0|0|设备拒绝IR 640×480，日志列出640×400支持模式；RGB源只发1帧，未过原配对静止条件|
|supported_partial|enable_ir=true，ir_height=400|19.125s|0/0|3|SENSOR_DEPTH/IR均启动、真实同戳Info就绪；新诊断器3.928s时触发原500ms反馈时限，连续IR采集未成|
|drained_partial|同上；单反馈订阅、处理就绪回调、先积累3.3s实际q历史|19.101s|4/4|3|4张原始IR及4张深度/同戳Info/静止q保存成功；7.240s时仍触发原500ms时限，不能声称连续调度问题已解决|

所有会话都已退出，CAN保持UP/ERROR-ACTIVE且RX增长，各窗TX均为3070→3070；没有USB/CAN恢复、机械臂运动、使能/失能、开闭夹爪或相机setter。最后一窗RX12020722→12072952。最后新鲜SDK/六true/99.6mm只属于已结束窗口，不是当前持续在线状态。原SDK全窗返回2（速度脉冲等原质量结果）保留，未把它改成通过；原逐帧3秒静止/120ms配对/500ms新鲜度照旧。根分区34GB可用，没有删除资料。

新诊断器曾因“已有≥2张图”而在全局反馈超时后仍返回0。该**诊断退出码问题**已在实测后修复并加3项回归：部分图不能掩盖反馈停止。第三窗原返回0保持不改，`audit.json`明确标记部分/未完成，最终退出码修复仅离线验证，未再开硬件。单订阅/回调处理并未完全消除超时，不推断为CAN物理停流：另一路原采集器随后仍取得新鲜3组RGB-D，接收桥末尾仍有新鲜样本；中间具体时延来源尚不清楚。

## 新证据：IR亮度到顶，同时目标深度缺失

查看第三窗首张**原始**IR后，独立选定方块内部矩形`[x0,y0,x1,y1]=[310,245,350,290]`（1800像素），其余3帧保持相同区域，不针对每帧另选。四张发布的mono8图中，255比例分别91.222%、90.889%、91.000%、91.000%，中位亮度均255；背景有明显投射斑点。这里是**发布的8位图像到顶**，没有原始ADC、线性辐射或曝光单位验证，不能直接等同传感器物理饱和。

四张原生深度的旧3354像素固定目标区域每张100%为0；实际六轴q在保存帧内均不变，与原观测参照仅J5差+0.000627984rad。六组补充RGB-D原质量全部0好顶面，没有相机或夹爪中心坐标可供拟合。

这为“目标回波过亮/深度匹配失效”提供线索，**尚未证明曝光设置、材料、入射角或最小量程中的哪项是根因**。不能把没有IR图流解释为投射器关闭，也不能用改TF或补洞修复原始零值。独立IR矩形与固定D区域分别统计，不假设D→IR像素重合或硬件同步。本机驱动IR Info复用了depth内参，本轮照实记录而不宣称其独立标定准确。GET原值及时间全部保留，仍是驱动回复，单位/底层硬件状态未核验。

## 修改范围和验证

- 仅test目录：原native记录器增加可选mono8 IR分支，深度默认格式/原始uint16/零值/Info/时戳/q规则不变；新增被动IR+depth记录器和针对性测试。
- 诊断器没有控制发布器、RPC客户端、使能或夹爪接口。每路最多60图/32MiB、各64缓存、0.5秒保存间隔；原3秒静止、120ms跨度、500ms新鲜和0.001rad姿态一致性不改。反馈订阅合并，最多32次非阻塞就绪回调处理，不替换时间戳、不放宽超时。
- 隔离launch从原部署参数读取，仅临时加IR流、修正设备已列出的IR高度；生产launch、参数、深度和彩色模式不改。第一窗旧默认不支持的情况照实保留，不再重试640×480。
- **75项离线测试通过**（8项IR/边界/无控制接口测试、3项调度测试、3项退出码测试及原61项相关用例）；五生产文件SHA不变。

测试复现（仓库根，不启动设备）：

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_ir_depth_diagnostic.py \
 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_native_depth_diagnostic.py \
 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_depth_controls_readonly.py \
 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_capture.py \
 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_quality.py
```

## 数据、原始字节与复现

- `RGB_IR_depth.png`：原RGB/IR/depth并排展示，拍摄戳不同；未当成同步配准图。红框是独立IR矩形，白线是原固定D区；原PNG没有改变。
- 三个会话目录：完整`streams/`含各路PNG、observer、Info/q、summary/ready；后两窗`portable/`含RGB-D/原SDK/FK/K-D-R-P/本次工厂D→C/配置快照，15+15资产，中心仍null。
- `audit.json`：44张native图（40深度+4IR）逐帧统计、实际q、整数戳、SHA和每窗失败/退出时序；`verification.json`记录75测试、141原文件和30便携资产SHA核验。
- `runtime_closed.tar.gz`与`runtime_manifest.json`：141个本轮原文件无损归档，包含全部日志、实际命令、隔离launch、SDK元数据、来源hash、实际执行版本代码。较早版本代码快照由本轮补丁精确还原，并与执行前记录SHA逐字节匹配；来源不冒称当时已额外采集。归档执行脚本只供审计，**不得自动续跑实体**。
- `package_ir_diagnostic.py`：纯离线统计/打包代码，路径按本机写明；异机复现先解归档，修改BASE/REPO/SRC与全新OUT即可，不导入设备接口。第一次打包因读取quality报告层级错误失败，已修为`summary.good_top_frames`，另用新目录成功，未改任何原始文件。

官方事实参考：[Orbbec旧Astra ROS2驱动说明](https://github.com/orbbec/ros2_astra_camera/blob/master/README.MD)提供IR流及曝光/增益接口，但接口示例不能证明本机具体量程、物理值或故障根因。本轮未执行手动曝光示例或任何激光/LDP操作。额外官方资料搜索超时取消，没有引用其未返回内容。

## 下一步：新位置先预览，不再先摆夹持侧再碰运气

P1仍**4个位置有原始记录，1/6个合格完整组**，标定未通过，冻结生产运动/门/TF/TCP/模型/一键入口。当前第4位置缺合格A，原B和坏A继续封存，不拿补充诊断充当正式A。

接下来请用户只把方块放到**比第4位置离当前相机稍远、远离桌垫边缘**的新位置；暂不手摆机械臂或夹紧。我先在机械臂当前静止观测处用原depth+RGB链做有界预览，核真实深度和原完整顶面质量，再通知夹持采B；不能继续在当前IR亮度到顶/零深度位置重复60帧。新位置是`new_pair06`（预定fit）；只读预览不需要回观测、搜索/ALIGN或运动。旧位置B绝不与新位置A混配。第7位置仍预定留出，不用其调参。

较远摆放是有针对性的取样条件变化，不是已证明“距离就是唯一原因”或精度保证。若新位置仍不合格，保留诊断与具体原因，不降质量门、不伪造可拟合点。Git本地提交不等于已推送GitHub。
