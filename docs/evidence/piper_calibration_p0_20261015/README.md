# P0新版准备与真实静止空跑（2026-10-15）

**最新收尾（10:03 +08:00）：P0工具空跑和分区/边缘独立复核已交付，158测试通过，详见 [P0_CLOSEOUT.md](P0_CLOSEOUT.md)。** 物理根因与10mm精度未验证，P0待阶段审阅、不自动进入P1。以下为首批152测试和60帧空跑历史；其中“下一分区复核”已完成，不再重复采零位图。

当前范围见 [P0—P5任务页](../../PIper_CALIBRATION_TASK_20261014.md)。本包是采集/离线方法验收，不是正式点对、手眼标定或成功抓取。未移动/使能/失能/开闭机械臂，未改生产代码、TF、限位或原入口。

## 本轮结果

- **软件：152 passed，0 skipped，rc0**。两项新P0工具、两项测试及原六组回归；使用Humble系统Python、`PYTHONNOUSERSITE=1`、`PYTHONDONTWRITEBYTECODE=1`、`OPENBLAS_NUM_THREADS=1`，没有安装依赖。
- **真实字段空跑：60/60帧，43.893133秒，9,316,586原图bytes**。六轴实际q波动全0；逐帧深度/Info同戳，RGB/真实反馈跨度仍≤120ms、年龄≤0.5s，静止窗3秒。217次匹配，10次未静止、59次不同戳Info仍被拒绝，没有放宽。
- **顶面自动筛选：60/60条件性好帧，顶面平面内点1148—1245/帧**。旧整物体“最大支撑面”算法60帧都失败，因为同一颜色区域含多个面；改为仅在P0离线按桌面高度分离顶面，再用原完整方形面拟合。没有修改生产检测器。
- **法向风险未关闭**：分离后的顶面/自动桌面夹角，方法A（RANSAC+正交SVD）中位5.5223°，方法B（独立全部ROI软L1图平面回归）中位8.8685°。顶面两方法差中位1.4979°，桌面两方法差中位1.9497°。不是一个已知、可直接写进TF的固定7—8°修正；不声称已定位深度系统误差。下一用已有数据做空间分区/边界敏感性复核，报告后审阅P0，再进入正式P1。
- 旧pair01：30帧中仅4帧达到800实际顶面内点，仍未夹紧/不计正式组。旧“10高覆盖帧”不等于10个达标顶面，不回写旧数据。

已实际查看本轮第一/最后原RGB及派生叠图：绿色落在可见方块顶面，青色环带跨过黑色垫与白色桌面区域，不能未经分区就把这些点当成同一物理平面。此观察支持下一步做空间分区对照，但**没有证明它是全部法向差的唯一原因**。新顶面条件性中心在逐帧`top_candidate.cube_center_color_m`；旧整物体`candidate`为空仍原样保留，不能把新候选说成已确认中心或成功标定。

## 证据目录

- `portable/manifest.json`：129资产、9,848,941B（不含manifest），完整60对原RGB/原生uint16深度、每帧完整CameraInfo/实际q/整数纳秒戳、工厂D→C和彩色Info/内部光学TF、实际模型FK/hash、配置快照、原SDK。原图内容未变，不填零、不去噪、不标注原图。
- `current_quality/report.json`：新版顶面分离、逐帧选择/拒绝及三维C/D中心候选、两个法向方法、原图SHA和源脚本SHA；图中**青色=自动桌面环带、红色=整物体原生深度投影、绿色=顶面假设的实际平面内点**。叠图是单独派生图，原图在portable中。
- `pair01_quality/report.json`：引用旧pair01的manifest/hash，重现旧30帧；不重复存旧原图。
- `live_diagnostics/`：首次RGB零输入失败、第二次启动顺序对照的采集摘要、两次只读桥、当前工厂元数据。`ordered_capture_p0_report.json`是**分离顶面前**的不可变现场报告（当时全0），`current_quality`是随后对同一原始60帧的离线分析；两者不可混称实时筛选结果。

SDK六秒窗发生在首次相机会话：60样本/59新鲜、5.818470秒、六轴q波动0；不把这个窗的使能/夹爪状态冒充后面每张图的同步状态。SDK记录q_mdeg `[-8947,-119,-1479,3433,25200,-4330]`，原换算q_rad `[-.156071468,-.002075836,-.025799676,.059885252,.4395888,-.07553252]`，该窗enabled六false、速度0、开口101.5mm；代理没有执行失能。每张图使用自己的实时ROS反馈/FK；第二次桥末端反馈另外留证。此姿态不是已批准观测目标，更不自动回放。

## 实际命令及有界性

复用实际ROS环境：`FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml`、`ROS_LOCALHOST_ONLY=0`及原Humble/ros2_ws overlays，没有改DDS。

1. 读原can0：UP/ERROR-ACTIVE/1Mbps/.75，窗口RX 94,127,895→94,128,367，TX0；不sudo、不激活、不重载。SDK只收CAN，`ConnectPort(piper_init=False)`，原0x3Ax接收映射。只读桥各110秒，实际发布5237、5254条，无查询/控制。
2. 原`ros2 launch astra_camera astra.launch.py`（深度640×400@30Hz、原生mm、Astra彩色关闭），原`ros2 run image_tools cam2image`（device0、320×240@5Hz、`camera_color_optical_frame`、remap原RGB话题），各`timeout -s INT -k 3s`上限110/100秒。只结束自建源，未退出用户原detector。
3. 首次较接近同时启动，相机RGB仅报告#1；45秒收到2157真实关节/840深度/1076Info、**RGB0/配对0**，rc2。只读检查设备存在且无其他占用，不重载USB。第二次先深度后RGB，连续RGB恢复并完成60帧；仅证明此顺序对照成功，不断言唯一故障原因。
4. `collect_calibration_p0.py --output NEW --config ACTUAL/cube_detector.yaml --max-batches 1 --frames-per-batch 60 --seconds-per-batch 45`。默认正式采集准备最多两批，各≤120秒/≤60帧/图片≤64MiB，剩余空间不足256MiB停止；断流、姿态改变或不完整批停止，全部已采数据保留。自动筛选不足20则最多再一批，不无限补采。
5. 现有只读`review_calibration_capture.py`、`export_calibration_bundle.py`及新`calibration_p0_quality.py`离线分析。导出model/FK不启动MoveIt/控制栈。

V4L2 GET元数据已保存：gain=0，auto_exposure=3，`exposure_time_absolute=157 flags=inactive`。这是批前/批后控制读数，不是逐帧实际曝光，也不解释为实测照度；lux为null。光照确实能在原RGB看到，但不猜物理照度。

## 点定义、坐标与尚未批准项

29mm仍是名义边长，未卡尺确认。条件性顶面取法：工厂D→C将真实深度关联到颜色mask，自动局部桌面环带上方29±6mm的**实测点**中拟合完整面，再沿外法线向内14.5mm。±6mm是离线显式高度先验，不是移动/闭爪门。原整物体面拟合、边缘敏感性对照仍保留；不以小时间方差证明绝对准确。

原生D坐标保留；新拟合输入必须为完整工厂变换后的`camera_color_optical_frame`。逐帧C/D候选、法线、roundtrip均在report，不能把D改标签当C。现有历史`fit_paired_calibration.py`明确只接受D；**P2进入前需显式补C输入/报告和宽松工具先验，不能直接把本C数据喂旧接口**。这不是已完成P2。先报告不带先验的数据秩，不能用先验掩盖不可辨识。

实际接触、释放原位、工具内几何中心尚未确认；camera center只是条件假设，未写回历史pair01的null中心。未采六组、未拟合/部署TF、未执行开环。下一P0空间分区复核/报告审阅；随后操作者准备同一方块，实际夹紧/释放原位，逐组授权原回观测。无整批运动许可。

本轮全部自建相机/桥已按自身时限退出；CAN保持有效、TX仍0（最后RX95,749,399）。五个冻结运行路径的SHA与本轮前完全一致，明细见`frozen_runtime_paths.json`。根剩35GB（54%占用）、HGFS最后剩137GB（73%占用），无需清盘；采集容量受限，不删历史/用户文件。

### 复现离线质量报告

```bash
cd /mnt/hgfs/ub
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
/usr/bin/python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/calibration_p0_quality.py \
  --bundle docs/evidence/piper_calibration_p0_20261015/portable --output /tmp/NEW_P0_REVIEW
```

输出路径必须不存在。manifest校验先行，全部原始hash不变；分析中缺失/疑问留null，不把来源不明的数据变成正式标定点。
