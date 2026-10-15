# 第三位置：重连后只读采A，28原始帧／0合格

2026-10-15 14:35 +08:00。本轮已恢复CAN和原观测姿态反馈，没有再次运动、使能、开闭或进入SEARCH；P1完整仍1/6。原B检查点84d8552不覆盖，物体同一点关系尚未确认。

## 实际执行

新can0 ifindex12最初DOWN/STOPPED，sudo -n true=0。只执行既定1Mbps、sample-point .75、queue1000、UP，没有模块/USB重载。RX41→727340，TX始终0，末UP/ERROR-ACTIVE/error0。预SDK60/60fresh、5.924秒、六q波动0、速度0，六true/64.5mm；q与上次观测末反馈完全一致，因此不重复原观测轨迹。最后SDK仍是同一q/六true/64.5mm，时间戳1792046041.9900477，退出后不宣称持续监测。

首个45秒采集0帧：实际收到2155反馈、869深度、1061内参，但RGB0。cam2image仅发布第一张，其V4L2线程等待；单一设备占用，未查明底层根因。只精确结束PID66855，原参数重开一次RGB后连续发布恢复，没有修改DDS、相机参数或代码。第一只读桥120秒5717条后正常退出，第二桥90秒4327条后正常退出。

重采一批目标60帧，实际28帧/45.019秒。诊断和RGB重开耗掉深度进程180秒预算，深度按预设时限退出，代理没有为后续采集预留足够源寿命；这是本次调度不足，不归为新CAN/USB掉线。即使补齐60张也不能据此宣称通过下列质量问题，因此未再同条件重采。

## 本次质量问题与旧深度空洞不同

28帧目标覆盖96.81%—97.66%，选中879—942个原生深度点；主面内点692—736，尚未满足原800顶面内点。所有帧另报自动桌面环带无主导平面。原始首/末RGB都已查看：方块在画面右上方桌垫边缘附近；已查看的[环带叠图](witness_review/annulus_witness_0001.png)显示自动环带横跨黑垫和白色桌面，不能把混合区域任意称为单一桌面。当前只能定位取样/几何质量，不能据此证明相机或材料故障，不能用表面中位数替代真实中心。原始[p0_report.json](p0_report.json)及[独立回放](witness_review/report.json)均为0好帧；不改原800规则、不补洞、不伪造中心。

预SDK原全窗静止通过；采集中59/60fresh原全窗rc2（速度24、−31mrad/s脉冲），采后全窗也因原速度脉冲不通过，全部保留。不把q波动0改写为所有速度0、不拼散点。每张图仍有原工具核过的3秒q静止窗、同帧深度Info、实际q/FK。当前不是合格A或可拟合点对。

## 可复核文件与停点

复现入口（均复用原脚本，无源码修改）：

- `collect_calibration_sdk.py --output <本轮新文件> --duration-s 6`；预/中/后分别保存，失败不覆盖。
- `calibration_readonly_feedback.py --duration-s 120 --output bridge.json`；第一桥正常退出后才以90秒新输出续采。
- `timeout -s INT -k 2s 180s ros2 launch astra_camera astra.launch.py`。
- `timeout -s INT -k 2s 180s ros2 run image_tools cam2image --ros-args -p burger_mode:=false -p device_id:=0 -p frequency:=5.0 -p width:=320 -p height:=240 -p frame_id:=camera_color_optical_frame -r image:=/camera/color/image_raw`；只重开一次、限90秒，参数相同。
- `collect_calibration_p0.py --output <各自新目录> --config /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml --max-batches 2 --frames-per-batch 60 --seconds-per-batch 45`；首批缺RGB原样退出，恢复RGB后仅一批（`--max-batches 1`）。
- 原`review_calibration_capture.py`→`export_calibration_bundle.py`→`calibration_p0_quality.py`只离线回放；使用既定ROS overlays、`PYTHONNOUSERSITE=1`、原FastDDS配置。独立临时读图探针曾漏此环境变量，触发用户NumPy2/系统cv2 ABI错误，按现有系统环境重跑通过，没有安装或修改依赖。

[portable/manifest.json](portable/manifest.json)含65项资产、4,483,884B：28对原RGB/整幅uint16深度/零值、同帧完整Info及实际q、实际模型FK、SDK全窗、现读CC1365304DG工厂内参/完整D→C/内部光学TF和配置快照。manifest SHA-256：
`2f53a21f814d1662a597fd9cc70f16237b8b2c3be35e34a1d3140b7eeeab648f`。

[runtime_closed.tar.gz](runtime_closed.tar.gz)无损保存83原文件，含首批0帧、重采、SDK失败旗标、相机/桥/采集原日志；压缩3,941,411B，SHA-256 `09cf5ebefc6bb90320f20c40fffc41e4afaafc2739671b9bad3913e05c2d26c6`。逐项原文件与压缩包SHA回读通过，原runtime未删。
[执行记录](execution.json)、[验证](verification.json)、[逐项清单](runtime_manifest.json)分开记录事实/推断/不足。

所有本轮源已退出，没有生产控制栈/Disable/Reset，生产五SHA不变。根34GB/共享136GB可用，无数据删除。Git为本地归档，未推送GitHub。

下一：先用本批现有数据离线核对桌面取样和面点数，再提出一次有针对性的采集调整；改姿态、场景或参数需说明并获准。不再重复已完成的使能/回观测，不套旧CAN停流阻断；若方块已移位，必须新A配新B，不能复用旧84d8552。
