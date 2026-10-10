# 2026-10-10 暂停交接：一键紫色方块实机抓取

更新时间：2026-10-10 18:24（北京时间）。用户要求在合适位置暂停，交给此前参与项目的老师傅；实机工作已停止。唯一规范仓库 `/mnt/hgfs/ub`；本轮起始代码提交 `4db88e3`。本轮仅撤回上轮未部署的配置试改并记录实机证据，没有加入新的抓取策略。

## 接手时先看这里

- 当前没有一键脚本、PiPER/MoveIt/Servo/视觉/抓取控制进程，本轮只读采集器也已退出。18:23:39 被动 CAN 核实六轴速度全0、使能全true，实际关节为 `[-0.278956,0.979583,-0.749008,0,0.741241,0] rad`；夹爪反馈 `0.102100 m`。没有回零、DisableArm、ResetPiper或0xAE。机械臂保持当前位置和使能。
- `can0` 为1 Mbps/sample-point .750、ERROR-ACTIVE；运行期及结束后无bus error/drop。暂停之后不得自动重启运动；用户或接手者明确恢复执行后，再从新鲜实际状态开始。
- 用户的实体测量已确认准确：镜头中心、沿相机光学方向，两指尖中心向下70 mm、向前105 mm。这两个分量不再要求用户重测。现有模型仍假定水平偏移0、保留未标定安装旋转，不能把数值优化/FK误差当外部TCP标定。

## 唯一实际入口与版本

```bash
BRAIN_ROBOT_AUTO_START=1 \
BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 \
BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 \
/home/johnwick/start_brain_robot_cube_real.sh
```

主链：脚本 → `cube_visual_search.launch.py` → `cube_task_real.yaml` → `visual_search_controller` → `piper_jog_adapter` → `grasp_lift_executor`。

- 实际脚本 SHA256：`e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`。
- 规范、实际源码、实际install三份实体YAML一致，SHA256：`6bd95d17828279b842e4404118d1137112b01504b686ca3fdaa673fe784c7460`。`top_down_grasp_enabled=true`、`allow_open_feedback_unconfirmed_for_approach=true`、张开50000、闭合0。上轮未部署的top_down=false试改已准确撤回，无本轮配置diff。
- 当前相机平移 `[-0.070,0,0.0308] m`、RPY `[0,-pi/2,0]`，指尖模型偏移 `.1358 m`；`rotation_calibrated=false`、`horizontal_offset_measured=false`。
- 执行器源码规范/实际SHA：`f815e6e8af19b4226e318c274cd33c9f0e1fc39113389aaffaaeaffc6b89755c`；当前安装二进制包含张爪未确认仍继续接近分支。驱动源码规范/实际SHA：`f2631dfe941abaaa1ad2839f20ef22666c138b23d66275a7fd476c65d2cf8edc`。

## 历史成功阶段和本轮失败须分开

历史 `/tmp/piper_real_run_20261010_settled_fix.log` 属于外参修正前12:42–12:53的运行：观测→中心扫描→ALIGN→GRASP_READY→76点预抓取→9点下降→一次落点纠偏→闭爪；闭爪反馈46.2 mm不变，失败于 `FAULT_GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED`。这条靠近/下降证据有效，不能说历史从未靠近过。

本轮18:19–18:21实际测试同一入口，使用当前已部署的实测相机偏移，额外仅用 `BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/onekey_test_20261010` 隔离日志：

| 时间（北京时间） | 实际证据 |
| --- | --- |
| 18:19:48.919 | PREPARE，适配器接受7点/22.5秒观测轨迹 |
| 18:20:11.043 | SEARCH / OBSERVE_POSE_REACHED |
| 18:20:42.543 | ALIGN / TARGET_ACQUIRED |
| 18:20:44.494 | GRASP_READY / DIRECT_VISUAL_ALIGN_ACQUIRED |
| 18:20:49.516 | 张爪未确认但继续TOP_DOWN_PREGRASP_PLANNING |
| 18:21:13.698 | 24个预置候选全部IK -31，FAULT_TOP_DOWN_PREGRASP_PLAN_FAILED |

脚本工具实测退出1，保护清理完成。本轮没有发出预抓取/下降轨迹，没有闭爪/抬升/释放。当前目标锁定约 `[0.432,-0.127,0.081] m`（依赖部署TF的模型值）；调试图约dx=9、dy=-4、深度303 mm、面宽约36×40 mm。原始RGB和调试叠加已查看，图像居中仅说明视觉对齐。

驱动正确处理启动夹爪缓存102100并保持存活，张爪目标调用50000/1000，首帧0x03、后续0x01；反馈仍102.1 mm。本轮139.3秒抓包中0x3A7共27590帧均102100；0x251..256各约13793帧。未抓到0x159回显，SDK local_loopback=false，不能据此断言没有发送。102.1 mm超出驱动0..80 mm范围与历史46.2 mm不同，不能认定为完全张开，也不能认定夹爪标定已修复。

## 证据路径

[一键输出](evidence/piper_onekey_20261010/onekey_run.txt)和小型离线诊断已另存入规范仓库 [docs/evidence/piper_onekey_20261010](evidence/piper_onekey_20261010)，可随Git交接；大体积CAN/节点日志和画面仅保留在下面的实机路径。离线脚本依赖同机安装URDF、配置及原始observer快照，异机接手需按记录补齐输入，不自动启动实体控制。

- 本轮一键输出：`/tmp/piper_onekey_test_20261010.log`。
- 本轮节点日志和CAN：`/home/johnwick/brain_robot_logs/onekey_test_20261010/`，重点 `visual_stack.log`、`piper_driver.log`、`gripper_can.log`。
- 状态、目标、真实关节和图像时间线：`/tmp/piper_onekey_test_20261010_observer.jsonl`。
- 画面：`/tmp/piper_onekey_test_20261010_images/`，优先 `0005_debug.png`（启动时目标）、`0023_rgb.png`（观测位）、`0036_rgb.png`及`0036_debug.png`（对齐后）。退出后采集器末尾重复保存最后帧，须按图片stamp识别，不能视为新鲜画面。
- 离线诊断：`/tmp/piper_onekey_geometry_review_20261010.py`和`.jsonl`，无ROS/CAN/控制发布者。安装URDF、相同六轴边界，24个预置顶抓姿态每个4个种子均未找到误差<1 mm且<.01 rad解；这只是有限数值搜索，不证明数学上绝无解。使用对齐后的实测末端朝向，找到模型内解 `[-.289806,1.690820,-1.002264,.024986,.282857,-.032500] rad`。尚未做MoveIt碰撞规划、最终夹入/下降、夹持区或实体动作验证；禁止把该解直接发送给机械臂。

## 接手后的第一步

先执行 `cd /mnt/hgfs/ub && git status --short` 并阅读本文件及固定四份任务/进度/决策文档；工作树有既有供应商/Astra修改及未跟踪手册/deb，保持不动。

建议下一最小动作是复核本轮静态锁定点、实际link6朝向与预置top-down姿态之间的差异，在ROS_DOMAIN_ID=78、禁止轨迹执行的隔离MoveIt中验证实测朝向对应的预抓取和下降路径；不要再原样重复24个失败候选、盲切侧抓或改回旧外参。实际闭爪反馈仍是独立未解决问题，禁止增加历史已证伪的发送帧数或未知基准0xAE。继续看真实原始RGB/深度/调试画面并查阅仓库/官方资料，每轮状态→最小动作→文档→Git→报告。
