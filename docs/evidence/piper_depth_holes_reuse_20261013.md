# 深度空洞：官方/GitHub复用调研与当前帧数字核对（2026-10-13）

用户没有批准固定23cm，指出高度/尺寸不同也会出空洞，明确要求查官方/GitHub。当前应用仍198f2a5、参数仍20cm；实机栈/采集退出、六轴静止使能。研究期间没有新运动、SDK/驱动安装、固件/激光调整或控制代码修改。新同步几何74回归/共享完整规划的证据保留，实体未触发。

## 官方明确事实与兼容性

| 一手来源 | 明确内容 | 本项目复用边界 |
| --- | --- | --- |
| [Orbbec ROS2 USB规则](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/scripts/56-orbbec-usb.rules) | 2bc5:0657对应dabai dc1别名 | 本轮实际PID0657/序列CC1365304DG/驱动泛称Astra；不套用Gemini330/RealSense专用驱动或仅凭别名认定全部规格 |
| [Orbbec SDK设备矩阵](https://github.com/orbbec/OrbbecSDK)与[后处理例程](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/examples/advanced/09_post_processing.py) | 按设备支持查询可用后处理；不同SDK/协议/型号兼容性不同 | 当前OpenNI链稳定，不为装SDK2/增强滤波而升级固件、换驱动、装Jetson/模型依赖；未确认该型号支持那些接口 |
| [RealSense遮挡/投影官方说明](https://dev.realsenseai.com/docs/projection-texture-mapping-and-occlusion-with-intel-realsense-depth-cameras/)与[occlusion-filter.cpp](https://github.com/realsenseai/librealsense/blob/master/src/proc/occlusion-filter.cpp) | RGB和depth视点不同造成遮挡与错配；通用可见性处理选同RGB像素最近深度。快速横向单调扫描有特定传感器排列假设 | 可复用几何/z-buffer/遮挡分类思路，不能将D415/D435专用扫描/阈值照搬到Dabai。本地当前C2D纹理拷贝未做color-view可见性裁决，仍须实测证明背景复制影响 |
| [librealsense后处理文档](https://github.com/realsenseai/librealsense/blob/master/doc/post-processing-filters.md) | 空间/邻域补洞复制周围值；时间滤波用历史值且会拖影，更适合静态场景 | 机械臂上的相机在移动，不直接复用同像素旧深度；即使补洞用于显示也不把填充值当新实测或把depth_valid设true |
| [ViSP眼在手IBVS例程](https://github.com/lagadic/visp/blob/master/example/servo-universal-robots/servoUniversalRobotsIBVS.cpp) | 从图像角点/目标几何估计姿态，由姿态计算特征Z和图像控制误差；需要相机内外参/模型，例程是UR+AprilTag | 复用模型估计与图像误差控制的结构，不照搬UR接口或要求本项目改贴AprilTag；优先原RgbResidual、真实TF/反馈、MoveIt→piper_jog_adapter，不新建控制入口 |

以上不等于这些SDK可直接替换当前相机，也不证明当前空洞仅因物体高度。对本机硬件兼容仍以真实PID/协议/运行代码为准。RealSense Apache-2.0代码可参考算法，但直接复用需保留许可证/NOTICE并去除特定布局假设；ViSP例程有GPL/商业许可条款，本轮仅参考结构，没有复制实现或增加依赖。

## 本轮证据：局部深度缺失，不是整幅相机失效/目标出FOV

复用原只读test/review_depth_registration.py的color_mask、project_measured、ray_scan/sample_summary；PYTHONNOUSERSITE=1系统Python，从原始PNG/工厂D→C/当前CameraInfo计算，不改图像或控制，不改外参/畸变方向。取同一运行两帧，RGB–depth差9.1ms和8.4ms：

| 指标 | 深度尚可靠6280.183 | 空洞帧6282.184 |
| --- | --- | --- |
| 原RGB方块mask像素 | 1318 | 1461 |
| 原生整图非零比例 | 73.64% | 69.06% |
| 投影到方块mask的样本（腐蚀前/后） | 2134/1811 | 97/36 |
| 腐蚀后median/range(mm) | 227 / 222–263 | 255 / 254–255 |
| 原生腐蚀后支撑bbox | [290,193,350,265] | [299,195,317,196]，仅约2行 |
| 使用最后可靠Z=.227m反投影的FOV覆盖（假设，非当前测量） | 100% | 100% |
| 该假设足迹内原生非零数/原RGBmask数 | 624/1318≈47.3% | 66/1461≈4.5% |

输入精确RGB戳1791906280183270225/1791906282184497764，对应原生depth戳1791906280174165061/1791906282176095564。文件在view_guard_20261013/synchronized_turn_exact，原CameraInfo从本轮observer读取，矩阵476.5287/325.8018/199.8851和当前工厂外参未改。

这只是同帧相机级数字复核，不是新目标坐标；假设反投影没有把估计Z伪装成实测。原RGBmask与正式640×400已配准轮廓不完全同一处理顺序，所以36不是bit-exact复现现场16样本，不谎称全门控回放。支撑从完整区域缩为两行、227→255mm跳变且原生足迹非零大幅下降，证明不能仅靠给debug补色/换固定距离解决。仍不能唯一确定是IR/投影器遮挡、局部测量盲区、材质/角度或工厂配准残差；目标高度可能促成前景遮挡，但不是已证实唯一原因。

正式检测器还在depth.valid时发布raw点/尺寸，稳定/尺寸门由随后独立无header Bool报告；raw点存在不是同帧全质量通过。下一质量模型必须用带时间戳的合格观测，避免仅凭旧Bool接受255mm背景残余。当前未修改这一发布契约。

## 建议的最小后续路线（应用修改仍先确认）

1. 保留原RGB独立轮廓/静止物体身份，采集同帧、完整质量通过的RGB-D点/尺寸，存机器人基座坐标下的最后可靠模型/真实戳/覆盖分布与散度。不给缺失的原生depth像素造新测量；新增带戳合格观测时保留既有search/raw话题契约。
2. 以目标局部深度覆盖、支撑分布、测量一致性/散度的下降触发短暂保持及末段模型冻结，不再强制先到20或23cm。若此时depth已缺失，使用最后经过验证的同一物体模型、真实图像时间TF/当前关节补偿相机自运动；不把depth恢复的背景样本重锁为目标，也不按同像素直接复用上一幅深度。
3. 继续已批准同步转向路径和原RGB纠偏；模型估计只用于预测与规划、明确不标成新实测。保留原完整MoveIt、限位碰撞、adapter/新鲜反馈与最终实际夹持/闭爪，原有预算/身份/反馈丢失处理不删。不是“没depth就任意盲走”，也不是depth缺一帧就永久呆住；对象高度/距离由模型表达而非固定切换数字。
4. 如需配准修复，只做可见性/前景深度簇关联的离线对照；官方z-buffer不会凭空恢复本机原生0像素，因此不先堆填洞算法或新网络。实际外参/TCP尚未标定完成这一剩余限制仍保留，模型本身不保证物理抓取。

优先用现有曝光/点/关节记录做无运动回放，验证支撑下降时切换、固定同一世界物体、零值/255mm背景不当新目标、相机自运动不当物体运动，再就原拥有组件提出具体局部diff获准后部署。此研究不是用户对质量驱动新阶段实现/23cm改动的默认同意；没有重复底层/激光检查或自动重跑已失败深度路径。
