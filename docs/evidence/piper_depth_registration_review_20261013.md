# 原生深度缺失与官方坐标转换核验

2026-10-13，起点d676447。机械臂保持实测q=[-.292187,1.894121852,-1.328657148,0,.888719468,.026305552]rad，夹爪79.6mm。只读分析与相机短时独占取证，没有执行新机械臂轨迹。此前SDK/固件/CAN基线不重复。

## 静止数据说明

当前RGB `/dev/video0` 的by-id为 `usb-Sonix_Technology_Co.__Ltd._Dabai_DC1_CC1365304DG-video-index0`，与深度服务serial一致，排除把另一台彩色相机接入。原入口RGB cam2image为320×240/5Hz，depth为640×400/30Hz；新配置仅在规范仓库，域0检测器仍加载旧值。

证据根目录 `/home/johnwick/brain_robot_logs/jaw_approach_20261013`。`direction_review_capture`静止采集5组，rc0/3.15秒，实际q与上一轮完全一致；frame3原RGB stamp=1791864457533635346ns、depth/info=1791864457527729636ns、反馈=1791864457526081185ns，组跨度7.554ms。RGB SHA256=2053f36f04f1c6002f238a617b181928cbe262079b147c9e99333dc1f6b9de70；depth SHA256=f7e31e81049057d120897b7fd3dc2d0fc63bb27cd17723916aede9582c489599。RGB bbox=[86,158,52,66]，左指局部遮挡；depth全图48196非零/170–193mm。

已实际打开新RGB/depth、`direction_review_live/evidence/0005_debug.png`与深度数值热图。live frame5 RGB/debug stamp1791864676.7554944、depth1791864676.8680804（latest组，不是硬同步），视觉IDLE/WAITING_FOR_START，抓取WAITING_FOR_LEVEL_ALIGN，debug报告INSUFFICIENT_SAMPLES。旧参数在这段采集中target/depth_valid仍会跳变，不能把true当当前相机校准证据。

## 离线配准与视野分离

新增纯离线 `test/review_depth_registration.py`，读取既有采集格式、逐图校验SHA，沿用检测器椭圆核/形状筛选/像素舍入/深度腐蚀；仅输出数值报告和科学热图，不创建ROS或运动接口，不改原图。正式椭圆核结果替代初稿方形核的近似数字：

|数据/假设|原15帧|本轮5帧|
|---|---|---|
|当前设备K/R/T|15/15样本0|5/5样本0|
|旧设备参数|469–589样本|5/5样本0|
|两种工厂畸变顺序|最多6样本|最多2样本|

畸变对目标附近投影影响约0.09–1.24 RGB像素，均不足现有10点要求。以**假设**Z=.186m作射线扫描，本轮frame3有2275/2846个轮廓像素（79.94%）投在depth FOV，其中仅1个原深度非零；约20%底部被裁切不是整个缺失的原因。逆矩阵会取到另一表面的大量点，不能按“样本多”选择方向。Z假设不是测量，不用来规划靠近。

复现（`PYTHONNOUSERSITE=1`系统Python）：

```bash
/usr/bin/python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_depth_registration.py \
  --capture /home/johnwick/brain_robot_logs/jaw_approach_20261013/direction_review_capture \
  --config brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml \
  --old-config /tmp/piper_camera_old_factory_20261013.yaml \
  --factory-evidence docs/evidence/piper_camera_factory_20261013.json \
  --output-dir /home/johnwick/brain_robot_logs/jaw_approach_20261013/direction_review_analysis \
  --heatmap
```

实际rc0。输出目录须为新目录；old-config是7516de1原YAML的只读提取，可省略。完整报告含每帧原整数stamp、原图SHA、参数SHA、所有假设；不把回放或数值图当新实机运动证据。

## 官方SDK与当前设备独立核验

1. `test/review_orbbec_projection.cpp`使用已安装 `/usr/local/lib/libOrbbecSDK.so.1.10.8` 的纯数学接口，不开设备。3个深度点经SDK `ob_calibration_3d_to_{3d,2d}`与手工行主序R·P+t的最大像素差1.518e-5；编译/运行rc0。这仅证明算式。
2. 为独立验证旧OpenNI字段方向，`test/review_openni_coordinates.cpp --stream`通过当前设备`2bc5/0657@3/14`、原生640×400/1mm/30Hz首帧调用原厂 `convertD2CCoordinateByIntrinsic` 与反向接口。6点正反转换均status0。采集首帧前同接口均status1，因此不能只看探针进程rc0。以下输出为工厂640×480彩色像素：

|输入depth(u,v,z毫米)|原厂D→C(u,v)|当前R·P+t整数截断|
|---|---|---|
|(326,200,186)|(244,213)|(244,213)|
|(320,368,186)|(240,385)|(240,385)|
|(350,340,186)|(270,356)|(270,356)|
|(160,350,188)|(77,368)|(77,368)|
|(326,200,350)|(280,213)|(280,213)|
|(250,250,300)|(196,265)|(196,265)|

每轴浮点差小于1像素，符合原厂整数截断；反向R/T假设横向相差约70–143像素。**当前D→C方向得到设备独立支持，不能翻转R/T来填补深度。** 原始日志 `openni_coordinate_probe{,_stream}.txt`保留原厂信息及完整K/R/T。构建链接当前SDK的 `include/openni2`、`openni2_redist/x64/libOpenNI2.so`，无刷写/标定写入/机械臂接口。

设备独占过程仅暂停相机健康守护3619125并停止其唯一Astra进程组，EXIT恢复守护；机械臂主栈/驱动/adapter未停止。前两次采集切换被退出检查误判（父守护暂停后留下Z僵尸，USB已释放）而跳过探针，未并发开设备；修正只统计非Z存活进程后执行成功。日志12:22:28确认原RGB-D已恢复。此过程使用相机瞬时流设置，没有开启硬件D2C、改外参或增加运动。

## 镜头TF的独立问题

实测color←depth TF旋转与工厂R相同，但平移为[+.029815618274,-.000557594469,-.000558507571]m；检测器使用[-.029824851990,+.000228742823,+.000140768886]m。同一点两路相差59.6498mm。源码wrapper把R转置后生成四元数，同时将原t作为depth父/color子的平移；与刚验证的D2C不一致。相关官方源码：[utils.cpp](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/src/utils.cpp)、[ob_camera_node.cpp](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/src/ob_camera_node.cpp)。本轮未改该TF或相机安装TF。

影响范围须分清：当前 `ObserveLockedTarget` 用depth TF与检测器R/T，cube_task_real.yaml的color TF项属于active_scan_supervisor（TF可用性/位置诊断），所以不能把59.65mm直接认定为历史50mm近距关联失败的原因。

服务D=0来自wrapper分配后未复制畸变，不能证明原UVC已去畸变；官方旧扩展文档与当前头文件畸变顺序不同，已数值比较两种。官方原厂参考：[OpenNI扩展接口文档](https://github.com/orbbec/OpenNI_SDK/blob/main/Doc/English/Orbbec-OpenNI2%20Extended%20API%20Instruction.pdf)、[Orbbec坐标计算实现](https://github.com/orbbec/OrbbecSDK_v2/blob/main/src/shared/utils/CoordinateUtil.cpp)。没有找到可核验的本型号最小量程，不套用其他Astra/DCW规格。

## 结论和接续

当前设备参数方向与计算已核实，方块预测区域缺少原生深度；具体近距量程/红外遮挡/材质原因尚未从单姿态分离。不能通过换旧参数、反转矩阵、放宽门或补零来获得抓取点。

`test/review_depth_retreat.py`复用既有TF初始化/严格图像stamp、MoveIt FK/LIN与轨迹检查，仅订阅真实RGB/关节和调用参数/FK/规划服务。当前只读计划 `plan/depth_retreat_review.json` rc0/validated=true/hardware_executed=false：图stamp1791865577140989839ns、66个静止反馈样本spread0、反馈年龄1.089ms；实际半开口±39.8mm且加载描述±40mm。

计划沿depth optical -Z退10mm、保持当前姿态，基座位移[-1.938,+.583,+9.793]mm（即升高约9.8mm）。26点/2.444秒、速度/加速度缩放均.005、model tip路径10.00000014mm，现有限位检查通过。J2 108.525188°→107.422485°，J3 -76.126447°→-76.836223°，J5 50.919875°→52.732354°；J1/J4/J6基本不变。目标q=[-.2921868971,1.8748760475,-1.3410450755,-.0000000262,.9203532000,.0263056687]rad。

这是恢复深度视野的候选，未保证1cm就恢复深度，也不是靠近/夹持到位。`execution_authorized=false`，没有发轨迹。批准后必须重新读起点、取新图、重新规划，再经原adapter单段执行；停稳看三图/真实反馈，不直接用陈旧计划闭爪。相机探针后额外3组新鲜配对采集rc0/3.70秒，q不变，证据 `after_official_probe_capture`。实机运行检测器仍旧参数，任何基于新深度的后续靠近前要部署已批准的新设备YAML并核对实际加载值。
