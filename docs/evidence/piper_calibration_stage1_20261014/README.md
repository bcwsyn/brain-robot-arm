# 阶段1工具补齐与真实静止空跑（2026-10-14 22:07 +08:00）

**最新结果（22:36 +08:00）：阶段1真实静止空跑已通过。** 用户后续授权固定CAN激活后，57新鲜SDK样本、5个完整配对帧、相机工厂及内部TF、实际模型FK/配置/哈希已保存，120项测试通过。入口见 [成功静止数据包](activated_stationary/README.md)。下面0fresh/接口DOWN结果保留为前一批历史，不再作为当前阻断；成功数据也不是正式标定组。生产继续冻结，无运动/使能/失能/夹爪命令。

用户批准了三个工具的局部修改和静止采集。**工具验证通过，阶段1真实完整空跑尚未通过；没有采成新正式点对。** 靠近算法、各道门、生产TF/TCP、模型和原入口保持冻结。

## 后续获准补齐（22:22 +08:00）

用户随后明确同意“补齐只读采集反馈”。新增 `calibration_readonly_feedback.py`，SDK采集器共享其接收ID映射：复制接收帧并保留全部其他字段，0x3A0—0x3A7减0xFF后仅交SDK解析，安装回调先于ConnectPort(piper_init=False)。不发送查询/控制，不激活CAN；只发布 `/joint_states_feedback` 六轴遥测，保留原 `.017444` 换算、速度单位和SDK关节接收戳，不用计时器新戳刷新旧数据。SDK无新鲜/重复戳不发布，不虚构夹爪速度/effort。

新增 `test_calibration_readonly_feedback.py` 与原五文件合计 **119 passed/0 skipped/rc0**；额外实际安装SDK纯协议解析CLI正确解出三帧合成0x3A4/5/6的六轴整数，未构造SDK接口、未打开CAN，不冒称实机反馈成功。接口在两批之间从索引3变6，当前DOWN/RX0/TX0，原因未追溯、不归责硬件或操作者。新桥真实CLI启动前检查 **rc2/published0/actual_last_sample=null**，不打开ROS/CAN、不恢复接口；结果 `readonly_feedback_bridge_preflight.json`（SHA d120e55f7a712612dbc73ddf22219efe64ae7e5277f7206a9d4287d4a3eebb27）。没有再重复6秒无帧采集或启动相机。

采集侧的软件接入缺口已经补代码，真实有流发布仍未验证。下一仅在接口恢复或获准固定参数激活后，运行只读桥和原静止采集器，完成真实完整数据包；不开始六组或运动。上一节95项及下述“尚未复用”的描述是前一批结果，不覆盖本节。

## 本轮实现

- `export_calibration_bundle.py`：显式 `--sample-id`，旧观测/手动/配对记录可选，清单注明选中的观测目录；支持现行被动SDK格式，保存源数据、新鲜度和工具FK，陈旧样本不生成实际q/FK。旧SDK缺全流新鲜度字段不冒充新版证据。保留缺项null/接触未验证；实际尺寸由原PNG及同帧Info读取，不猜固定分辨率，另保存实际task配置快照。
- `review_pair_sampling.py`、`estimate_calibration_cube_center.py`：从哈希清单选择观测目录，允许显式 `--capture-dir`；不再绑定旧pair01目录。多目录不自动混不同姿态；旧单目录manifest自动兼容。原配准、相机中心估计数学和离线质量标准没有改变；全高支撑组不要求虚构低帧，对照差为空。
- 新测试 `test_calibration_bundle_groups.py`：新组、当前/旧SDK、清单/哈希/相对路径/覆盖拒绝/无控制接口、全高组、空采集拒绝及旧原始资产回归。测试fixture明确不是新实机点对。
- 最终五文件pytest：**95 passed / 0 skipped / rc0**。初次43项中的5个兼容/状态分支失败已修复：旧图像记录无size时读原PNG，陈旧标志不继续校验新鲜q。没有修改系统依赖，测试使用 `PYTHONNOUSERSITE=1` 和Humble环境。

## 原始数据离线CLI验证

原pair01全部30帧在当前实际安装模型下重新分析/导出，显式标为 `offline_pair01_reexport_NOT_NEW_PAIR`；69文件/4,730,045B为配置快照补齐前的CLI输出，仅留home，不重复把这些旧PNG提交Git。三工具CLI均rc0，10高/20低、表面层差24.766897mm，29mm名义D中心[-13.009035682,40.973508676,453.481896494]mm与阶段0一致，仍不允许正式拟合。最终配置快照补齐有完整回归覆盖。

这不是新采集、新硬件精度、成功抓取或当前安装外参解算。旧115资产全部SHA复核通过。

## 一次真实静止采集结果

- 现有can0 UP/ERROR-ACTIVE/1Mbps；本轮读取前后RX都为 **5,262,717**，TX都为 **31,359**，因此采样窗内无新接收帧且未增加CAN发送计数。没有重载CAN/USB、查询固件、ResetPiper、MasterSlaveConfig或使能/失能/运动/夹爪命令。
- 原 `collect_calibration_sdk.py --duration-s 6`：60样本、0新鲜、静止有效窗口不满足、error=null。原始源文件在本目录。原复合shell末尾ip命令rc0不是SDK质量成功；采集器源代码在此质量条件下返回2。默认零值和false使能不是实际姿态/失能证明。
- 只启动原Astra和原低带宽cam2image；复用实际已运行节点的FastDDS profile/localhost值，没有改DDS配置。Astra日志确认当前相机CC1365304DG、640×400/30Hz/mm深度；RGB320×240/5Hz。没有启动PiPER驱动、MoveIt、Servo、搜索或抓取。
- 原 `collect_static_rgbd.py --duration-s 8 --frames 1 --settle-s 3`：rc2，收到RGB40、深度169、depth Info204，**关节反馈0、匹配包0、有效保存帧0**，start_q=null。真实相机输入已证实，完整配对尚未完成，不能放松新鲜度/同步条件来生成有效帧。
- 原相机只读采集器另以4秒/4MiB上限保留相机证据，rc0/image_budget/4,169,372B。仅选一对原RGB/native深度入Git：相差25,858,381ns，**未配真实关节/完整同帧Info，不是正式点对**。已实际查看RGB：桌上完整紫色方块、两侧夹指可见；不从照片推当前真实q/TCP。
- 本轮两个相机进程都用其独立会话SIGINT退出；RGB rc0、Astra rc0且宿主确认container/cam2image未留。Astra关闭时有undeclare参数错误，但已停止深度并退出，不当作采集期间故障。用户原残留detector/debug viewer没有管理或退出。

## 前一批识别的缺口（软件接入随后已获准补齐，真实反馈仍缺）

实际 `/joint_states_feedback` 没有采集专用来源；被动SDK工具本身不发布ROS话题。生产driver有控制订阅/服务，不能为了此话题把整个控制驱动启动为“只读源”。另外当前安装SDK只按0x2Ax解码，原实际driver已有0x3A0—0x3A7接收侧映射；采集侧尚未复用。**本次CAN无新帧，不能把零反馈唯一归因于解析器；补软件接入也不能证明链路恢复。**

此方案随后已获得用户明确同意并按上节完成代码/离线验证。生产驱动/运动链仍不改，接口DOWN时不自动重试采集或发起六组/回观测/抓取。

完整home工作目录 `/home/johnwick/brain_robot_logs/calibration_stage1_20261014.vxGdfP` 约11MiB。根54%/35G可用，共享72%/141G可用，未触发清理、未删除证据。以下有限归档含四原始/诊断文件和可读/机器记录，不包含重复旧bundle或其他用户dirty；仅本地提交，不假称已上线GitHub。

## 重现工具命令

```bash
source /opt/ros/humble/setup.bash
# pytest不启动设备；实际安装模型CLI另需原piper_ros/piper_ws/ros2_ws overlays
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_bundle_groups.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_cube_center_estimation.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_paired_calibration.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_static_rgbd.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_capture_review.py
```

新导出必填 `--sample-id`；单观测目录从manifest自动取，多目录用 `--observation-capture` 明确一个。之后叠图/中心工具可用 `--capture-dir` 指向清单内目录。采集包为空时导出拒绝；不会把失败静止空跑转成正式组。
