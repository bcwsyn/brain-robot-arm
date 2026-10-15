# 启流后再查询：单次原生深度诊断（2026-10-15）

## 结果与边界

用户“自行推进”批准上一轮提出的诊断启动顺序局部修复和一次不超过30秒的验证。本次**启流与独立保存已实测通过，目标深度仍不合格**，不是标定或抓取成功。P1仍为4个位置有原始B/部分A，只有1/6个满足原合同的完整组。原正式A60/0好帧、B `2b1becb`、物体未移动的用户确认均不覆盖、不重问。

- 唯一实际相机会话25.617775秒，36张原始640×400 uint16深度PNG，另3对RGB-D诊断图；后者原质量检查0个好顶面。
- 第一对真实深度/同戳Info/新鲜反馈到达epoch `1792052805.8326852`，随后factory启动 `1792052805.8457472`、首个曝光/增益GET `1792052806.5011148`。44请求/44回复，曝光原值6000×22、增益1556×22。底层硬件读取状态未传播，单位和物理值未核验，不据此断言自动增益或曝光是原因。
- 原首个高质量预览固定3354像素区，本次36帧原始零值比例99.8509%—100%，中位99.9702%；向内收缩3像素的2124像素核心区每帧100%为0。固定区用于诊断，不是新分割或中心估计；本次与原参照仅J5相差+0.000627984rad。少量边缘非零点不冒充方块表面。
- 36帧六轴q波动均0；Info与depth原始整数戳逐帧相等，完整K/D/R/P、反馈原始值、速度/effort和SHA均保存。FK仅在实际q与原导出器计算姿态完全相等时复用，GET按最近回复关联但明确**不是图像同步测量**。
- CAN已UP/ERROR-ACTIVE，RX8654822→8714890，TX3070→3070，没有CAN恢复或新增发送。最后新鲜反馈仅属于已结束会话，不能冒称现在仍在线监测。
- 全部本轮源已退出；无运动、使能/失能、开闭夹爪、相机setter、激光/LDP改变、驱动/USB重载或生产修改。根分区34GB可用，本轮没有删除数据。

这一次正向结果不能唯一证明“提前GET”就是上一轮启动失败的原因：启动调度及临时包装器也有变化，没有受控重复A/B。它足以验证工具真实保存能力，并排除“只因RGB停流而没有独立深度证据”的缺口。

## 实现范围与保留的失败

只修改test目录两个诊断工具、两个测试：native诊断先收到真实深度/同戳Info/新鲜q才创建ready.json；查询器见到这个就绪事实才发固定两个GET。服务发现不等于启流。ready不等于静止/好顶面通过，原3秒静止、120ms配对、500ms新鲜、0.001rad姿态要求、60帧/32MiB上限和正式采集原规则不变；非native的原GET-only模式保持兼容。

之前还有一次**仅SDK预检**：60个新鲜样本但速度脉冲使原全窗静止rc2且找不到原规则的连续合格窗，旧临时包装器assert提前退出，未启动相机、未发GET。失败原样保留在归档preflight_only。随后只去掉临时无运动相机调度器的SDK静止启动断言，保留SDK质量结果、不篡改原summarize或逐帧质量规则；实际会话SDK全窗同样rc2，原连续[1:41]40样本/3.915397秒通过，两者分别保留。原逐帧静止规则才决定是否落盘，未把速度脉冲解释成实体移动或通过。

## 数据位置与复核

- `native/`：36原始深度、observer.jsonl、完整summary与ready。
- `native_manifest.json`：39个native资产哈希，路径以`base_directory: native`为根；`native_audit.json`：36帧区域统计、完整时序、实际q/FK和GET关联边界。
- `native_depth_series.png`：第1/19/36帧裁切对照和全部零值趋势；黑色是原始深度0，白线为固定诊断区域，不是补洞图。原PNG未修改。
- `portable/`：3对RGB-D及实际q、模型FK、相机内参/本次工厂D→C、配置快照，共15资产。
- `quality/`：原工具质量报告和叠图，0好顶面。
- `runtime_closed.tar.gz`与`runtime_manifest.json`：SDK预检失败+唯一实际相机会话，共72个原文件无损SHA归档，含原命令、临时包装器、启动/退出日志、全部原始数据。无须访问本机旧目录即可审阅。**归档脚本仅为as-run证据，不可自动续跑实体。**
- `verification.json`：61针对性测试通过、72+39+15资产SHA通过、五个生产文件SHA不变、未推送GitHub。
- `package_startup_order.py`：离线打包/统计复现代码；运行前应将SRC/PRE改为从归档提取的对应目录，REPO指向规范仓库，OUT指定全新路径。不导入设备API、不发ROS/CAN命令；包含现场绝对路径以保持可追溯性，不伪称免配置通用CLI。

测试命令（仓库根执行，测试已通过，不启动设备）：

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_native_depth_diagnostic.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_depth_controls_readonly.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_capture.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_quality.py
```

## 判断及下一步

已证实是源端目标区域缺深度，不是机器人TF/IK删点；本轮连续反馈和深度流正常。尚不能区分弱/过强红外回波、材料/入射角、近距条件或设备内部匹配状态。不从USB PID软件别名推断具体量程，也不把旧正常帧/少量边缘点当当前有效中心。

不再按同条件盲采60帧、不重复观测运动、不放宽800点/20帧、不补洞或改生产TF。下一有信息增益的实验建议：**仅增加一轮有界IR强度图像观察**，与现有深度区域比较；新增IR流属于相机配置变化，须先说明并获批，尚未执行。优先核部署版本支持的流组合，不套新SDK参数或自动设置曝光/增益/激光。

官方参考：[Orbbec旧Astra ROS2驱动说明](https://github.com/orbbec/ros2_astra_camera/blob/master/README.MD)说明IR图像及曝光/增益接口；这些接口的存在不证明当前固件的具体量程、单位或故障原因。手动曝光示例还要求先处理自动曝光，但本轮**没有执行任何setter**。新版SDK文档仅背景，不能直接套到本机OpenNI驱动。
