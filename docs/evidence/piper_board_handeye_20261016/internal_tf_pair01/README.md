# 相机内部TF与安装TF成对修正：已部署，静止RGB-D坐标链核验通过

2026-10-16 18:50 +08:00；起点 `e50224a`。用户已同意上一轮明确提出的“仅修正相机内部TF并同步重组安装TF、保持批准手眼结果、先离线及静止验证”，并要求只在需要现场操作时再叫。本轮完成该范围，**没有发送机械臂运动、使能/失能、夹爪、复位或CAN恢复命令**。

## 改动、实际路径和回退

只修改内部TF的平移求逆，复用既有转置旋转：`t_inverse=-R^T*t`。原代码反向使用旋转，却原样使用正向平移；本机现有工厂D→C配准、30对原始图像和本轮同戳TF核验支持这一局部修正。没有改原始工厂数组、相机内参、D→C检测器、曝光/分辨率/QoS、点云/Octomap、靠近/门/TCP/模型/限位或原一键入口。

| 项目 | 实际生效与SHA |
| --- | --- |
| Astra活动源 | `/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp`，旧 `b9b5eaa380f8eb8ef714378a5e465092af81646aa255d35902aab0c235c620b1` → 新 `e916a45172dd6fc413a9652b61a438fe20049eda73ea5fbfd26865f5a080969b` |
| 规范源 | `brain_robot_arm/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/src/ob_camera_node.cpp`，与活动源字节相同 |
| 实际库 | `/home/johnwick/ros2_ws/install/astra_camera/lib/libastra_camera.so` → `/home/johnwick/ros2_ws/build/astra_camera/libastra_camera.so`，新 `7dfeab6f3d61e27355abb5fdeebcde4d84f59c463ac54d23201deab8ac384911` |
| 安装mount | 规范与home `cube_task_real.yaml`、installed符号链接相同，旧 `7811b755b04fb49f06f766cf5c5694cf9eefe0a079fd4e2fbf097081119a80bd` → 新 `524f7c0ec64deba485c572c75739bdec936ee79304041c3dc3910f07835c52b9` |

**不要编错相机副本**：`CMakeCache.txt` 的 `CMAKE_HOME_DIRECTORY` 是 `/home/johnwick/ros2_ws/src/astra_camera`；home另一个 `src/ros2_astra_camera/astra/src/astra_camera` 是未参与此构建的旧副本，本轮不顺手覆盖。上一轮两副本字节相同，本轮活动副本与规范源同步，非活动副本仍旧SHA。

定向构建命令 `cmake --build /home/johnwick/ros2_ws/build/astra_camera --target astra_camera -j2`，rc0、约15.98秒，只重编 `ob_camera_node.cpp.o` 并链接库。静止采集时 `/proc/8982/maps` 确认实际加载该新库，不仅是源码/启动成功。完整 [build.json](build.json)、[build.txt](build.txt)。没有全量升级依赖或修改CMake/launch。

安装mount同步变为 XYZ `[-.041971548734476324,.06391288457018547,.032022636009455124]m`、RPY `[.20008101038427822,-1.269534223956201,-.24293041679986016]rad`，**批准的 `X=T_gripperBase_colorOptical` 完全不变**。值来自编译实际C++计算前缀及原Eigen/TF2转换helper，再组合原有color_frame←color_optical边，不是手改轴角或直接套原始数组标签。仅mount的XYZ/RPY值变化，其余配置值完全不变，见 [paired_mount_prediction.json](paired_mount_prediction.json)。

回退必须**成对**：停止相机/TF源后，恢复 [ob_camera_node.active.before.cpp](ob_camera_node.active.before.cpp) 到活动源、[ob_camera_node.canonical.before.cpp](ob_camera_node.canonical.before.cpp) 到规范源，并恢复 [cube_task_real.before.yaml](cube_task_real.before.yaml) 到home实际及规范配置；恢复或从旧源定向重建相机库。原库本地备份 `/home/johnwick/brain_robot_logs/internal_tf_pair_20261016.VKGL5c/libastra_camera.before.so`，SHA `42775163791283bb8e9a58af2d4e280e12fe5ec36b9590678c0b34af951ad8de`，**构建产物不入Git/归档**。旧源与Git e50224a原字节、旧配置SHA均已核验；当前没有在活动配置上执行回退/重部署循环。不要只退mount或只退库，不牵连其他用户未提交修改。

## 离线验证和失败留痕

- 新4项测试会把**实际C++函数计算前缀及原旋转helper**编译运行，核对该设备工厂数组、零平移及带多轴旋转的正/负平移，不是只比Python公式。原发布轴映射也受断言保护。新增1项原mount测试核对内部TF与未改检测器的配准一致；合计 **41项测试通过**，[regression.txt](regression.txt)。未新增物理运动停止门；数值容差只用于float32变换回归。
- 首次新测试fixture遗漏原有的color_frame←color_optical边，4 failed/rc1，在任何相机/机械臂会话前发现；只修fixture补该边，生产公式/运动规则不因测试而变，后4项与完整41项通过。见 [preflight_failure.json](preflight_failure.json)，没有隐藏失败。
- 全部30对旧pair01原RGB-D复算，固定先前已公开约440mm表面的425—450mm样本范围、不搜索范围/不补洞/不改原图。修正实发TF与原检测器在**每一帧**的覆盖率完全相同；原实发TF全部为0。原10高支撑子集中位76.89095%，低覆盖20帧也留在全30结果，不隐藏选择偏差。
- [pair01_corrected_TF_replay.json](pair01_corrected_TF_replay.json) 含逐帧原件SHA及全部结果；[对照叠图](pair01_TF_comparison.png) 显示高支撑第2帧的原TF表面在方块右侧，修正后落回方块；低支撑第1帧仍缺该表面深度。**修正TF不等于修好材料/近距缺深度**，不改变标定原数据或独立留出结果。

## 一次真实静止会话

复用原只读SDK桥、原模型/原launch的mount参数生成、原Astra和原cam2image；没有实体driver、adapter、Servo、MoveIt执行、SEARCH或抓取节点。新会话 `/home/johnwick/brain_robot_logs/internal_tf_pair_20261016.VKGL5c`：

- 相机14.322482秒；原采集5.575999秒，5/5原RGB-D，保留原16位毫米深度、同帧Info、RGB/深度原戳、实际q、原图SHA。原3秒静止等待拒绝15次原样留证，不改门。
- 验证器**使用这同5对归档图像的原戳**查询（本轮不再是“早先5消息＋稍后5归档图”两集合）。逐对查询 `G←C`、`base←C`、`C←D`、`G←D`、`base←D` 与对应 `base←G`，无latest替代、5/5通过；每对另取5个真实有效深度点，保留原像素/毫米值与两路基座坐标。
- 批准彩色X平移误差max `3.180e-17m`、旋转 `1.572e-14°`；内部TF与未改工厂配准的平移数值差 `1.56044e-9m`、旋转 `1.36938e-7°`，25个真实深度点两路变换差max `1.43303e-8m`。这些是float32/刚体链的**数值一致性**，绝不表示物理达到纳米/毫米绝对精度。完整 [live_mount_verification.json](live_mount_verification.json)。
- 工厂serial CC1365304DG，K/D/R/T getter逐项与上一轮相同；检测器SHA `154938b0…` 未变。原模型SHA `0b41516e…`、其他五生产SHA不变，见 [final_audit.json](final_audit.json)。
- CAN RX31617157→31667893、TX **42154→42154**，ERROR-ACTIVE、错误/bus-off0、dropped297未增；未重载、USB重置或重复基础巡检。SDK整6秒rc2原样保留，原37样本/3.612913秒静止子窗通过；末q_mdeg仍 `[-8254,53595,-72228,-4099,69496,5092]`、六true/99.6mm。这只是末反馈，不是持续监测/新的接触证明。
- 外层TF/核验/预览均rc0，内部SDK原rc2单列、其他源0收尾，全部自有源退出，后实际进程检查无相机/TF/控制残留。**0运动/0夹爪/0使能失能/0复位**；没调用ResetPiper/MasterSlaveConfig或刷固件。
- 当前原RGB可见棋盘格/左右夹指，**没有紫色方块**；深度存在、原缺失像素保留为0。[当前RGB与原生深度可视化](static_RGB_depth_preview.png)只设显示色标，原PNG字节不变，不把原生图像视差说成镜像或未配准失败。

## 参考依据及结论边界

审阅[Orbbec当前Astra源码](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/src/ob_camera_node.cpp)及[官方坐标/TF说明](https://orbbec.github.io/OrbbecSDK_ROS2/en/source/camera_devices/4_application_guide/coordinate_and_tf.html)。当前上游也有原平移写法；**没有假称“上游已修复”、盲目升级或把新版SDK接口直接套本机旧OpenNI实现**。本轮修正依据是该安装的原始工厂配准语义、原图投影以及新库实发TF的闭合核验；对其他设备/SDK组合不作未经验证的通用结论。

P3已完成的范围：批准手眼X保持、部署来源/回退可追溯、RGB-D配准与机器人TF局部一致。既有9fit＋1heldout独立角点max2.836mm不变，不重拟合/重采。未证明全工作区绝对精度、实际TCP或成功抓取，低支撑/近距深度空洞也没被本补丁治愈。

**下一步真正需要操作者的只有放回紫色方块**：放到当前相机完整可见、远离夹指遮挡的桌面区域，保持机械臂和相机支架不动，回复放好。随后先只读保存新目标及统一后的基座坐标，再准备原入口P4开环粗抓；当前不自动AUTO1/靠近/闭爪，不新增门或改冻结靠近逻辑。

完整58原件/1,893,399B、归档1,301,974B，48松散资产，全部SHA归档回读通过，见 [manifest.json](manifest.json)。本地旧库和编译测试临时产物明确排除，原件未删除。沿用预览包装器中的a335162/旧角色和用户引文只是历史包装器元数据；当前基线/范围以本页、final_audit、deployment_execution为准。Git仅本地，既有共享main分叉/积压发布审查不变，不自动推送。

离线复核入口（无需相机/机械臂，需已有Eigen/TF2头文件和g++）：

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_camera_mount_geometry.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_astra_internal_tf_geometry.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_readonly_feedback.py \
  docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/test_board_handeye_fit.py
```
