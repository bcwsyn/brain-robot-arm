# P3：彩色手眼TF已部署；静止核验通过，完整RGB-D几何仍有独立不一致

2026-10-16 18:20 +08:00。起点 `b7cbce0`。用户“确认”批准采用既有9fit＋1heldout手眼候选、仅更新相机安装TF并静止核验；随后要求自主推进，只在需要人操作时再叫。本轮没有运行一键AUTO1、SEARCH、靠近、抓取、开闭、使能/失能/复位、CAN恢复或固件操作。

## 实际修改和生效路径

唯一生产修改是 `cube_task_real.yaml` 的 `piper_camera_mount_tf`：XYZ、RPY及 `rotation_calibrated=true`，不改其他配置值。仓库与实际home源字节一致，安装路径是该home源的符号链接：

- 规范：`brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml`。
- 运行：`/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml`。
- 安装：`/home/johnwick/piper_ws/install/brain_robot_ball_pick/share/brain_robot_ball_pick/config/cube_task_real.yaml`。
- 旧SHA `7d0e2c0d8336050de13a387d35bfb534b3577f8ac75f15883e9e6d403322e42a`；新SHA `7811b755b04fb49f06f766cf5c5694cf9eefe0a079fd4e2fbf097081119a80bd`。
- `translation_m=[-.04512779376581344,.004441055999940165,.02867113711249619]`；`rotation_rpy_rad=[.2000810103842787,-1.2695342239562017,-.24293041679986027]`。

原安装launch的 `_camera_mount_arguments` 实际用于验证，按旧接口 **XYZ/YAW/PITCH/ROLL**，未误用RPY顺序。安装模型SHA仍为 `0b41516e87e9bafd2a1e9b2821666ac1f24e5641131b8062134520aae0326d82`。YAML符号链接直接生效，无需/未声称重编C++。仅额外更新相机几何回归测试，历史7cm/10.5cm保留为历史先验，不再用它强迫新的安装标定值；实际TCP未改。

## 为什么部署值不同于上一轮提案

批准的 **`X=T_gripperBase_colorOptical` 完全不变**。先开一次原Astra仅getter/内部TF会话，发现实发 `T_cameraLink_colorOptical` 不能与旧报告按原始数组标签构造的D/C变换混用。真实安装应满足：

`T_G_link = approved_X_G_C * inverse(actual_T_link_C)`。

实测 `T_link_C` 平移为 `[+.000140768886,+.029824851990,-.000228742823]m`。按旧 `candidate_review.json` 单独部署，实际彩色链将差 **59.649754mm**；该旧提案从未部署。本轮先按实发链重组，再核验，见 [live_composition_review.json](live_composition_review.json) 和 [internal_tf_actual.json](internal_tf_actual.json)。

更正 `b7cbce0` 的旧配置对照：批准X相对旧**实际TF链**为 **26.795659mm /17.433461°**，旧链独立留出角点max **18.645371mm**；原69.280mm/19.687mm只对应旧报告的原始数组组合假设，不再作为实际TF链结果。新候选留出max **2.836443mm**、9fit、留出隔离、留一波动结果均不变。历史原件不覆盖。

## 静止实测，不冒充抓取验证

`run_static_verification.py` 只启动原模型RSP、原launch参数生成的安装TF、原Astra、原cam2image及原只读SDK桥；无机械臂驱动、adapter、Servo、MoveIt执行或任务节点。

- 5个**实际RGB消息时间戳**上的 `G←C` 查询通过，未用latest替代、无TF超时；X误差max `1.963e-17m /4.153e-14°`，`base←C = (base←G)*X` 同时核对。此数值只证明配置和发布链一致，**不是物理标定精度**。这5个查询消息只保存头/TF；另一个原采集器保存了稍后5对完整原RGB-D，不能冒称两个集合逐帧相同。
- 原RGB-D采集5/5，原图、16位毫米深度、同帧深度Info、实际q、时间戳及配对跨度在 [capture/observer.jsonl](capture/observer.jsonl)。相机运行18.2415秒，原采集8.4177秒，未改原3秒静止/反馈门。
- 末真实反馈 `q_mdeg=[-8254,53595,-72228,-4099,69496,5092]`，六轴true、夹爪99.6mm；仅末采集事实，不是持续监测。SDK整6秒rc2如实保留（60/59fresh、q波动0，不能说整窗速度条件通过）；原33样本/3.212126秒静止子窗通过。
- CAN RX27292833→27353811、TX **42154→42154**；ERROR-ACTIVE、错误/bus-off0、dropped297不增。健康链直接复用，未重载接口/USB。
- 本轮所有自有源退出；外层TF/核验/预览均0，预览内部SDK原rc2单列，其他源收尾0，不隐藏失败。最终进程清单无相机/控制/TF源。根33GB可用/56%，共享130GB可用/75%，无须删数据，本轮未删除任何文件。
- [deployment_audit.json](deployment_audit.json)：仅批准3配置键变化，其余五生产SHA不变；原模型不变；**36项针对性测试通过**，见 [regression.txt](regression.txt)。松散文本是原regression.log的同SHA别名（原log在完整归档内），不强行提交被忽略的.log。两repo技能使本轮限定真实安装路径及手术式修改，而非改控制/检测门。

## 新发现：深度配准和内部TF不能同时当成同一条物理链

这是独立于安装X的消费链不一致，不是又一个新运动门。检测器配置的 `T_colorOptical_depthOptical` 与Astra实发同名查询相差 **59.649753mm**，旋转几乎相同。配置原值及SHA **未改**。

为不只凭矩阵标签猜测，`check_recorded_rgbd_directions.py` 对旧pair01 **全部30对不变原图**回放，复用原掩膜/投影/内参，不补深度。固定使用此前已公布约440mm表面的425—450mm样本范围，**没有搜索优化范围**：

| 投影候选 | 全30帧方块覆盖中位/最大 | 原10个高支撑帧覆盖中位 |
| --- | --- | --- |
| 未改检测器工厂数组 | 0.00575 /0.78134 | 0.76891 |
| 实发相机内部TF | 0 /0 | 0 |

低覆盖20帧没有被删除；高支撑子集本来按旧配准选，具有选择偏差，故也公开全部30帧结果及逐帧SHA。此旧局部影像支持保留检测器配准，**不能因为某TF已发布就反过来改检测器追它**。这不是绝对深度/TCP精度或所有位置的证明，见 [recorded_rgbd_direction_check.json](recorded_rgbd_direction_check.json)。安装Astra源码的转置/平移发布实现及SHA见 [vendor_internal_tf_source_review.json](vendor_internal_tf_source_review.json)，把源码事实和物理推断分开。

所以当前：**彩色安装X部署/发布核验完成，但完整RGB-D机器人几何不能验收，更不能直接自动深度抓取。** 这不是需要重启机械臂、再采9＋1或再调J5的问题。当前原图只有棋盘格/夹指，没有紫色方块；尚不要求用户挪方块。

已生成 [internal_registration_followup_proposal.json](internal_registration_followup_proposal.json)，只作离线提案：将内部TF与现有有影像支持的工厂D→C统一，**同步**重组安装mount，保证批准彩色X保持不变；不能单独部署任一半。该提案不改检测器/相机内参/TCP/靠近/门/限位，尚未应用。需要对这处相机内部TF的局部解冻明确批准，再离线验证和静止核对；当前TF-only批准不自动扩成改Astra/重新运动。

## 回退和接手

回退原件 [cube_task_real.runtime.before.yaml](cube_task_real.runtime.before.yaml) 与 [cube_task_real.canonical.before.yaml](cube_task_real.canonical.before.yaml) 完全相同，SHA已与 `git show b7cbce0:brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml` 的原字节核对。当前部署副本为 [cube_task_real.deployed.yaml](cube_task_real.deployed.yaml)。本轮**未在活动配置上执行回退/重部署循环**。获准回退时，将两个before分别原样恢复到home实际源及规范源，核旧SHA；installed符号链接会随home源变化；不得趁机回退其他用户改动。

原会话 `/home/johnwick/brain_robot_logs/handeye_deploy_20261016.9NoweY`。完整62原文件（1,353,639B）压缩为814,213B归档，逐件SHA回读通过，41松散资产便于审阅；见 [manifest.json](manifest.json)。`execution.json` 来自逐字复用的旧预览包装器，其a335162/旧角色/旧用户引文只是历史包装器元数据，**当前授权/基线/任务以deployment_execution、deployment_audit及本页为准**。原始图像/日志不修改。

复现离线检查（无需ROS/机械臂；从规范仓库运行）：

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_camera_mount_geometry.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_readonly_feedback.py \
  docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/test_board_handeye_fit.py
```

本地Git留证，不自动推共享main；既有分叉/积压发布审查范围阻断不变，不是本次机械臂通信故障。下一是审阅上述**内部TF成对修正**范围，非重做标定或新增靠近保护。开环模式/抓取仍未实现或验收。
