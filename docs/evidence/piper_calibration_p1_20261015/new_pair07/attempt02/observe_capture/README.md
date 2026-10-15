# 第六留出补采 attempt02：A60采成，深度恢复，原好顶面仅1/60

2026-10-15 21:31 +08:00。用户“已完成”确认新的平整黑垫摆位，仅执行一次只读A，不移动/使能/arm/开闭夹爪/失能/Reset或CAN恢复。`new_pair07`仍固定held-out。**没有新B，此位置不能与旧B8f8eed6配对；未拟合、未部署TF、未推送GitHub。**

## 实际结果与阻断

- 原采集器43.872200秒保存60/60，相机总53.451966秒（含清理，预算80秒），四源就绪6.230秒、factory GET在正式采集之后；所有自有源退出，原depth需SIGKILL的退出状态保存。RGB连续216/depth813/Info970/反馈2106；15次等待原3秒静止历史、40次Info不同帧拒绝，不改接受条件。
- 原始彩色方块完整22×21、框[148,107,22,21]，放在黑垫，无瓶子支撑。真实D→C投影覆盖96.4029%—99.3080%；60帧表面深度449—450mm、时变中位绝对偏差0、逐帧六轴波动全0。**本位置深度已恢复，不再是旧全目标空洞。** 这是静态重复性，不是绝对精度。
- 60帧都能得到完整方形顶面候选，但真实顶面内点748—814，中位772.5；只有snapshot57的814点≥原800，因此原好帧1/60，未达到20。没有降低800/20、拼帧或将完整候选数量冒充合格数量；[完整原质量报告](quality_all60/report.json)保持原算法输出。
- 自动桌面参照下，候选顶面高27.733—28.292mm/中位28.054mm；RANSAC/SVD法向差中位3.465°（范围2.398—4.708°），独立graph法中位4.159°。原框内确有方块，绿色顶面见证覆盖其上表面；这些是条件几何候选，未用法向新增阻断或冒认物理绝对中心。原图像门仍只有1组通过，正式点对批准0。
- 实际A q(rad)：`[-0.134528128,0.9445053800000002,-1.26041622,-0.07797468,1.216178236,0.09698864]`。各帧保留其真实反馈、整数时间戳、完整同戳Info及实际模型FK，不以旧观测命令角替代。
- 新SDK60/59fresh/5.831秒，全窗原静止通过，末有效六轴使能true/夹爪99.4mm。SDK窗在正式图采集后，与factory/收尾部分重叠；不是逐帧SDK，A每帧自己的JointState是主反馈。SDK没有接触/夹持确认，本组没有B。
- CAN RX51445481→51574953、TX15662不变，无恢复。根34GB/共享138GB可用。六冻结源/实际home旧adapter SHA前后一致；候选fef28d6未部署，未改运动、TF、模型、限位、检测或筛帧规则。按ros2-piper-debug与surgical-change技能限定实际路径核验和证据范围，没有新增生产修复。

## 数据在哪里

- [portable_review20](portable_review20/manifest.json)：20均匀代表原始RGB+uint16深度，含唯一好帧57，**不是20好帧**；其余19是低于800但有完整面候选的审阅帧。包含每帧Info/实际q/FK、当前工厂D→C/内参、SDK、配置快照、表面测量和SHA；50资产逐SHA验证。D光学点/C光学点明确区分，工厂镜间外参不冒充机器人安装TF。
- [runtime_closed.tar.gz](runtime_closed.tar.gz)：完整原60套、原observer/summary、相机及反馈/就绪日志、工厂GET、SDK原始窗口与完整60套便携导出，269文件无损归档；[runtime_manifest.json](runtime_manifest.json)含每个归档成员大小/SHA及归档SHA，逐成员回读验证。未删原图/补0值，普通分析仅20代表帧，全60仍可在Git中解压重算。
- [quality_all60/report.json](quality_all60/report.json)：60逐帧原完整面/顶面、法向、点数与全部失败/候选信息。[assessment.json](assessment.json)是本轮派生判断，不覆盖源记录。[A_execution.json](A_execution.json)含准确命令、开始/结束/退出码；[执行源快照](executed_sources)及[离线打包复现脚本](package_offline.py)保留。
- 本机完整运行目录`/home/johnwick/brain_robot_logs/new_pair07_attempt02_A.j_rigpw0`；Git便携原件和归档不依赖本机绝对路径才能读取。归档内原日志保留历史绝对路径是溯源，不是Git端分析入口。
- [junit.xml](junit.xml)：81项通过，范围为原采集会话/静止配对/只读反馈桥/顶面质量；没有改生产源。全部SHA核验见各manifest，原质量SHA `a50bf7c17c5bc6437bae9be8d3f0eb3284a35488e238ceffc54260116be964f1`。

## 命令与复现

使用`/usr/bin/python3`及既有Humble/piper_ros/piper_ws/ros2_ws overlays，`PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 ROS_LOCALHOST_ONLY=0 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml`，未换backend/DDS/QoS。

```text
capture_calibration_session.py --output /home/johnwick/brain_robot_logs/new_pair07_attempt02_A.j_rigpw0/session  # rc0
collect_calibration_sdk.py --output .../sdk_post_capture.json --duration-s 6  # rc0，仅被动接收
review_calibration_capture.py --capture .../session/capture --config /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml --output .../depth_review.json  # rc0
export_calibration_bundle.py --output .../portable_all60 --capture .../session/capture --sample-id new_pair07_attempt02_observe --sdk .../sdk_post_capture.json --camera-metadata .../session/factory.json --review .../depth_review.json --detector-config /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml --cube-edge-mm 29  # rc0
calibration_p0_quality.py --bundle .../portable_all60 --output .../quality  # rc0是工具完成，不代表原质量通过
python3 -m pytest -q -p no:cacheprovider test_calibration_session.py test_static_rgbd.py test_calibration_readonly_feedback.py test_calibration_p0_quality.py --junitxml=.../junit.xml  # 81 passed
```

## 下一步：稍移近方块，不先手摆机械臂

不盲重复同位置60，也不要求先手摆新B。请只把方块沿平整黑垫稍移近相机这一侧，参考[基于本轮真图的静态指引](next_flat_mat_placement.png)绿色十字(159,165)附近；红框是本次实际位置。机械臂不动、不垫瓶子、暂不夹紧。这样预期增大原图中顶面的取样面积，下一仍须实测原20/800，不保证成功。

[placement_guidance.json](placement_guidance.json)约418mm是“把当前顶面向局部延伸”的条件估算，**不是未来测深/标定结果/运动轨迹或新门**。下次新位置应独立存新attempt，不覆盖本次原件；先新A合格，再用户手摆新B及确认同点。旧位置B绝不能跨位置配对。
