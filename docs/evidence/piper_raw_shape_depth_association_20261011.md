# 原彩色形状与实测深度关联修复（2026-10-11）

## 事实与范围

起点2473f22。新批准J5 +6°实际恢复完整视野的记录在最新进度；本修复不发送机械臂/夹爪命令。旧原安装检测器在相同五组原始配对图上target_valid/depth_valid全部false，诊断TARGET_LOST；不是目标实际不在彩色视野，而是注册到深度网格后的残片被形状门拒绝。

只改cup_detector_node及其纯OpenCV几何辅助头/测试。原HSV、面积/矩形/长宽比、深度样本/腐蚀/MAD/帧间跳变/三稳定帧、物理尺寸/裁切阈值不改，未添新的抓取门。软件配准分支的形状在完整原RGB判断，像素面积阈值因此按原RGB像素解释；旧320×240/640×400尺寸不同，不能称所有远距灵敏度完全不变。原已配准/仿真分支不改形状源。

原工厂D→C逐个实测非零深度投影同时保存原RGB像素索引；只属于所选原RGB轮廓的深度进入原中值/MAD/稳定性计算。不填黑洞、不合并不同轮廓、不插入相机中心或用户70/105mm当深度。不依注册残片中心确定落点，而以完整原RGB形状中心射线和同轮廓实测中值Depth-Z，经工厂变换精确逆矩阵求深度光学坐标。该点是同物体测深约束下的瞄准估计，**不声称缺失中心像素有真实深度或实际夹持区已标定**；表面斜率/遮挡造成的误差仍可能存在。

target_point_camera仍camera_depth_optical_frame，target_pixel/pixel_error仍原640×400深度网格、原header时刻和单位；不是把320×240彩色误差直接塞进旧控制增益。target_size在软件配准时由完整彩色bbox与相应Color-Z/缩放内参估计，避免残片宽高影响尺寸门。注册debug仍可有黑洞：黄框是实测支持区域，青色十字是完整RGB中心的深度网格投影，二者不必同心。原只读raw_color_debug/bbox/projection保留（此前规范已有、部署未含）。不改启动入口/执行器/TF/TCP/相机/YAML/驱动。

## 资料与项目推断分开

- [OpenCV 4.5.4 calib3d](https://docs.opencv.org/4.5.4/d9/d0c/group__calib3d.html)明确针孔投影与R/t坐标变换公式。这里复用系统4.5.4/OpenCV矩阵逆，不新增依赖或重新拟合手眼。
- [官方 librealsense 投影参考](https://github.com/realsenseai/librealsense/wiki/Projection-in-RealSense-SDK-2.0?language=en_US)说明像素反投影、流间外参和零深度无测量；只用这些通用RGB-D几何原则，不把RealSense接口/测距范围套到本项目Astra。
- “原RGB形状+映射的同目标深度+完整形状瞄准点”是根据本项目A/B证据选择的实现，不称供应商现成完整抓取方案，也不证明当前相机到机械臂TF正确。

## 可复现验证

构建（只两个目标，不安装整个包）：

```bash
source /opt/ros/humble/setup.bash
cmake -S /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place \
  -B /tmp/piper_rgbd_shape_build_20261011.fygBnq -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/piper_rgbd_shape_build_20261011.fygBnq \
  --target cup_detector_node rgbd_shape_geometry_test -j2
/tmp/piper_rgbd_shape_build_20261011.fygBnq/rgbd_shape_geometry_test
```

全部exit0，6项通过：不造缺失深度、唯一轮廓/索引边界、完整中心而非残片中心、真实工厂正反投影/镜像/端点缩放/Depth-Z保持、无效深度拒绝、无效标定拒绝。

域78只运行一个detector与review_rgbd_shape_replay.py，沿实际cube_detector.yaml和原五配对包；工具仅发布三相机输入，图检查无机械臂/adapter/Servo/MoveIt/执行器，90秒界限，数据时刻整体平移保留相对间隔。每例10输入，最后5帧作为稳态对照；原同步器会有一帧延迟，不把过渡帧伪装稳定结果。

```bash
ROS_DOMAIN_ID=78 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml \
  /tmp/piper_rgbd_shape_build_20261011.fygBnq/cup_detector_node --ros-args \
  -r __node:=cube_detector --params-file /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml
# 在同一隔离域启动只读回放（输出必须为新目录）
PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=78 \
  /usr/bin/python3 /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_rgbd_shape_replay.py \
  --capture /home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu/capture1 \
  --output /home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu/new_detector_replay --negative-cases
```

新回放26.427秒/exit0。captured最后5帧target/depth均true/DEPTH_GRASP_ALLOWED，Depth-Z .151m，MAD约.001m，末图4169样本，原RGB形状AR1.14/rect.89，完整尺寸约.037×.044m；点(.00894,.03494,.151)m(depth光学)，原RGB回投影约(119.82,160.28)，误差仍DEP网格(34,111)px。已实际查看captured_debug.png。四个合成否定例最后5帧target/depth均false：zero_depth=REGISTRATION_UNAVAILABLE、no_color/thin_color=TARGET_LOST、high_depth_mad=HIGH_MEDIAN_ABSOLUTE_DEVIATION。MAD拒绝仍可能发布观察点，消费者必须继续依既有valid门，未更改这一协议。

旧二进制原同YAML/同五包7.677秒/exit0，最后5帧target/depth均false/TARGET_LOST，保留old_detector_same_packets输出；此A/B不再运动或改变曝光，证明本次差异来自检测算法。整个验证没有实体发布者/闭爪/使能操作。

全部原输出在/home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu：new_detector_replay/{summary.json,messages.jsonl,*_debug.png}、old_detector_same_packets/summary.json、两个节点log。新源SHA2deb634fb542ae2b1a1953771c86ae68c4afeac03cb4a543894e6bddaf24d22f，新二进制SHA099969f9bff0ccf0d320448c8b8fbd2313705b9735523d61b118b9c0876fc7b1。二进制/PNG/大日志不进Git。

下一：只部署这一个已测detector及所需头/实际CMake include，保留旧source/bin独立备份，不全包build/install影响已有executor或YAML。机械臂静止，仅原两相机+原cube_detector.launch.py和有界观察核实时target/depth/点/原RGB。后续真实几何/耦合靠近与接触区仍需实际证据，不能凭DEPTH_GRASP_ALLOWED宣称已抓住或继续扩大J5。
