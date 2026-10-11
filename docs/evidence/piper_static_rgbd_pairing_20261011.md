# 时间配对静止采集：真实接入结果（2026-10-11 19:55）

起点 `8943c04`。本轮实现只读工具，不改默认抓取控制；没有关节、夹爪、使能、复位、失能或 CAN 发送接口。目标未完成。ROS2技能约束真实 overlay/话题/时间证据，surgical-change约束最小工具所有者变更；未修改 vendor/reference、默认 YAML/TF/TCP 或 executor。

## 可复用实现及官方事实

新增 `brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_static_rgbd.py`，SHA256 `059b11660289a8b42526b52296638c566a54cc9d9aee39508383d3e7d22bc62b`。21项新测试，CMake仅登记pytest，无默认安装/启动修改。

复用已安装 message_filters **4.3.19** 的 Subscriber / ApproximateTimeSynchronizer，不自写同步队列或用到达时刻伪造header。固定订阅原RGB/depth/depth CameraInfo/真实joint_states_feedback，sensor QoS，队列100/slop120ms；额外核 depth/info 原stamp/frame/尺寸一致，按名字六轴，250ms静止历史/0.001rad差、图像年龄≤500ms。接受包保存原PNG/stamp/K/q/跨度/SHA，不填洞或补造彩色内参。最多120秒/60组、输出目录必须新建，中断/运行错误保留已完成数量及拒绝理由。这只限制分析数据，不是正常抓取新增门。

[官方 Humble 源码](https://raw.githubusercontent.com/ros2/message_filters/humble/src/message_filters/__init__.py)明确按header时间戳队列及slop配对，不提供硬件同步或手眼标定保证。官方文档本轮被Anubis拦截，已读官方源码及本机实际实现，未套旧ROS1搜索结果。本机实现 `/opt/ros/humble/local/lib/python3.10/dist-packages/message_filters/__init__.py`，SHA256 `235c6d6374edc9b83e59ea53441e653a39f3f9abf793542090d84a20a35dcbdd`，上游当前分支不当已安装版本。

## 针对性验证

source ROS Humble 后，`PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider` 执行同一test目录的 test_static_rgbd.py / test_startup_script.py / test_jaw_scene_review.py / test_calibration_sampling.py，最终 **69项通过**，其中新21项。

真实官方同步器用SimpleFilter/消息对象作内存回放，不启动DDS：RGB10.000时latest depth/info10.160、feedback10.170超阈值，但历史10.020/10.030配成30ms合法包，随后错时RGB无假包。另测旧/未来/零stamp、depth/info错帧/尺寸、非法K/编码、缺轴/重名/NaN、停稳窗口、无界CLI、已有目录在ROS初始化前拒绝、无控制/service接口。测试SHA256 `853542fe757d645ad77cb3afb499a817eac970760ba3476cd1392898a6ecee19`。无工作区整体构建或原抓取重跑。

## 有限真实接入

新目录 `/home/johnwick/brain_robot_logs/static_sync_20261011.a1GWut`。仅启动原脚本相同的两条相机命令，不起MoveIt/adapter/Servo/detector/controller/executor、不替换47043反馈驱动。source顺序仍ROS/piper_ros/piper_ws/ros2_ws，复用现fastdds_udp_only.xml，不试新DDS。Astra/cam2image各setsid、45秒timeout，EXIT仅TERM/KILL自有组及wait，无广泛pkill或机械臂命令：

```bash
ros2 launch astra_camera astra.launch.py
ros2 run image_tools cam2image --ros-args -p burger_mode:=false -p device_id:=0 \
  -p frequency:=5.0 -p width:=320 -p height:=240 \
  -p frame_id:=camera_color_optical_frame -r image:=/camera/color/image_raw
timeout -k 3s -s INT 35s python3 \
  /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_static_rgbd.py \
  --duration-s 30 --frames 15 \
  --output /home/johnwick/brain_robot_logs/static_sync_20261011.a1GWut/capture
```

实际exit0，14.048977秒保存15组；收到RGB49/depth196/info236/feedback2725。匹配44包，其中10包非同stamp的info拒绝，其余合法包部分因0.5秒保存间隔不保存。15组跨度最大72.845321ms/年龄74.401461ms、六轴范围全0；q=[-0.262724084,1.888278112,-1.280686148,0.0095942,0.836928232,0]，J5≈47.952455°。一个静止姿态15次测量，不是15个标定姿态；不证明唯一AX=XB或全链绝不掉线。

首组stamps_ns RGB1791719201192565139、depth/info1791719201189454720、feedback1791719201191259526；末组RGB1791719210791605784、depth/info1791719210782917209、feedback1791719210790990626。保存纳秒整数避免浮点边界。Astra确认1mm/640×400@30Hz，RGB320×240；数据量不冒充达名义帧率。相机启前SDK有2.39秒恢复、启动近窗0.19秒恢复；本14秒窗无新增报警，但不能否定旧长窗间隙。

已实际查看末组原RGB：两指可见、紫块仍触下沿。按同一实际detector factory K/D→C/端点保持映射离线核15组：bbox x94..97/y168/w56..60/h72均裁切，紫色相关深度2354..2437样本、每组中值0.155m。没起检测器，不把离线统计称实时target_valid；不是合法抓取点或两指捕获。

只作新图诊断的可见角点ROI中心(46,154)/(254,157)、半径5px，左170..198样本/.176m、右158..170/.204m；ROI未核CAD身份且跨边界，深度可能背景，不当指尖三维点或替代70/105mm。旧用户A/B身份仍绑定原SHA，未直接套到新图。相机→夹持区矛盾尚未解决。

证据SHA256：

- `capture/summary.json`：`229f109185f55811078bce037f5bb2bf5024675731e30220adb4343a3b05788b`。
- `capture/observer.jsonl`：`f5528943c933fadc5492c724fbd6b320633ff877a9837c939ee49ce5e932c24a`。
- `astra.log`：`bbd164d3acb54baa99da6621a110d63145d24c8de8d454e804017b5b85e9f06e`。
- `rgb.log`：`9487c1cc01666cdf975385e9d392aaf96ad064539bf01f75835513a481f3b303`。
- 首/末RGB：`5c6232d498c0b955e3506a7c8fc0e9c0d2549d91f0835c9bd6cd7042ed462ad4` / `00bf2b05a6d1138482e93d609364cd4391bb3a8530810ce1534e7eaae74caee0`。
- 首/末depth：`a1de2848fb4a60a6fd19496c6dec61e337b1e4aa657d9b9e33eeb2e5cd3ad9fe` / `68f9ac8d8b41ee698e81f4304fc1143e4319fb70c5d1d218606e0f146e2db8a7`。

收尾主机仅47043/PGID47039反馈及非控制daemon47019；本次相机/采集器全退出。原入口0e976b0a…/executor源码107ce501…/cube_task75612194…不变，未重建/同步控制包、失能或运动。原始图/日志留机器，不提交大数据，工具不装成第二入口。

下一项用此采集器取得可信非平行姿态并独立验证实际夹持区。不能拿同姿态15帧凑标定，不能复活旧26°/敏感候选或硬增J5盲闭爪。±6°超既有4段20mm（已用1段），未自动执行；其余小段也需先核真实轨迹/反馈及累计范围。当前仍无唯一通过的新TF、完整方块视野或实际抓取。
