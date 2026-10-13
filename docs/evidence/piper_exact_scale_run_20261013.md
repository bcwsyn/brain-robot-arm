# 2026-10-13 19:34–19:47 原一键精确尺度实测

本轮复用已部署的 `60a9895` 诊断执行器，基线 HEAD `2b4e286`。未修改应用代码、YAML、相机安装 TF、TCP、尺度门、轨迹或启动脚本。Git 仅保存本文与交接记录；图像、原始日志、固件及二进制不入 Git。

## 实际执行与收尾

- 用户确认 USB-CAN 已连接虚拟机后，新枚举 `1d50:606f`、`3-1.2:1.0`、can0 ifindex 9；当时 DOWN。一次受限 `sudo -n` 配置 1 Mbps / sample-point 0.75 / txqueuelen 1000 / up 成功，8帧 candump 成功。未 USB reset、模块重载、主从配置、ResetPiper 或刷写。
- 只读 SDK 使用 `can_auto_init=False`、`CreateCanBus`、`ConnectPort(piper_init=False)`；初始 joint stamp 1791891288.030558、high stamp 1288.026543，q约 `[-.035238198,-.002076942,0,.052028265,.284314135,-.129154365]` rad，六轴 enable false。原脚本随后正常使能，不另起 SDK 控制程序。
- 原 `/home/johnwick/start_brain_robot_cube_real.sh`，`BRAIN_ROBOT_AUTO_START=1`、`BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0`、`BRAIN_ROBOT_DEPTH_ONLY_TARGET=0`，日志目录 `view_guard_20261013/scale_reconnected_onekey`；执行 session 31123、主 PID 3804070。入口 SHA `87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0`；binary SHA `79d8d9bad392235a63b99c099a2887cc345a917f5ddabd30ebd6ca73b05b2f62`。
- 原脚本复用持续 RX 的 CAN；只由既有相机恢复机制重启无帧输入，收到 RGB/depth 首帧后完成 `[7/7]`。未手动重启驱动。
- 自动 restart 卡在既有 `timeout 5s ros2 service call /visual_search_controller/stop`：控制器1791891510.218已 STOPPED，但客户端3805756/timeout3805755持续超过160秒。核对精确 PID 后只 `kill -KILL 3805756`，原脚本继续，未改 timeout 代码、未另发运动。这一释放操作不构成永久修复。
- 原 PREPARE 1791891694.191，14路点/49.1秒/max step .08rad；adapter接受。1791891743.026 `SEARCH (OBSERVE_POSE_REACHED)`，1755.615 ALIGN，1757.913 GRASP_READY。
- 初始完整路径预检79个pregrasp + 13个descent，自动靠近40段被adapter接受；初始观察器在边界到期前独立记录25个 `REAL_ARM_TRAJECTORY_FEEDBACK_CONFIRMED`，不能声称完整40段均有采集确认。最后 loop108/cursor69/92，原尺度拒绝触发软件停止。没有进入最终 DESCENT、闭爪、抬升或释放。不要将预检中的 `TARGET_DIRECTED_DESCENT` 当成真实下降执行。
- 主脚本异常退出 rc1，原 cleanup 完成、未发 DisableArm/Reset。控制栈和本轮只读采集均退出，不自动续跑。结束 CAN RX1420323、TX16172，收发 error/drop均0；最后 SDK joint stamp1791891883.445390/200Hz、high1883.446392/100Hz、low20Hz，六轴 enable true、速度0、collision/stall/driver-error均false。实际末点 q=`[-.314665411,1.716094987,-1.294912132,0,.816342851,0]`rad，J5=46.773°；最后 ROS开口99.6mm。使能是本轮新读证据，不仅是 cleanup 文本。
- 根分区86%/约11GB；只执行既有 clean_disk_space.sh，rc0后仍86%，原脚本报可用10840MB，无ENOSPC，不扩删工作区或据此归因 CAN。

## 精确图像与原计算

证据根 `/home/johnwick/brain_robot_logs/view_guard_20261013/`。

| 项目 | 初始 seed | 尺度拒绝帧 |
|---|---|---|
| RGB stamp（ns） | 1791891758007141583 | 1791891817006498016 |
| 路径子目录 | scale_reconnected_exact | scale_reconnected_exact_motion |
| 原框 L,T,R,B | .396874994040,.375,.487500011921,.504166662693 | .303124994040,.737500011921,.418749988079,.916666686535 |
| 模型 color Z（m） | .304045673662 | .154489430242 |
| RGB SHA256 | dfe05af06b347f2688f01a0efd18cde6ab0b155953346d20e2adfd5e583476b1 | e8953a3ed3110abc3550f080fbad3e4e370754f6de93ea6c14c96ac4a5c87a32 |

两目录中的 `<stamp>_rgb.png` 与 `<stamp>_debug.png` 已实际查看：初始方块接近十字中心，拒绝帧仍完整，位于十字下方/略左、两指可见；不能据此声称已在实际闭合夹持区。原生深度 `scale_reconnected_exact_motion/1791891816996200883_depth_raw.png` 已查看，RGB前10.297ms，uint16/640×400，182324/256000像素非零；并非整图黑/全零。拒绝帧 debug 报 depth .216m、2869样本、MAD .000、dZ .001。另观察器0091（静止）及0135（靠近）RGB/depth/debug三图均已查看。

原门实际值：growth=1.968067803638、width_ratio=.648281400211、height_ratio=.704801367020、width/height clipped=0、recovery=0；宽度低于原 .65 下限，触发 `LOCKED_TARGET_SCALE_MISMATCH`。紧接外部软件stop/adapter disarm、`FAULT_AUTOMATIC_RGB_STEP_EXECUTION_FAILED`。本轮没有新设门；MoveIt该段已规划并被adapter接受，不能归为本次IK失败。

精确查询 `camera_depth_optical_frame <- base_link`（与失败RGB同stamp）：t=`[-.000000748094,.501847863647,.050996555409]`，q(xyzw)=`[-.574387671171,.790769955065,-.171179918420,-.124334697101]`。冻结base点=`[.443266845697,-.132558362764,.096856472514]`；TF复算depth点=`[-.011014720069,.040667198103,.154095917434]`，与日志一致，不是复算中误用latest TF。

拒绝时执行器日志所见raw点是前一RGB帧（1816806876479，.217m），`raw_same_stamp=0/depth_used=0`。**只读采集器随后完整保存了拒绝帧同stamp点**：depth optical=`[-.011551916195,.081714647347,.216]`，框也与执行器一致；不能把它说成执行器当时已经使用的样本。

按未改的当前工厂 D→C 转换，该同帧raw color Z=.216510174925m，相对模型差62.020744682mm；三维raw-model残差74.278510401mm（深度轴差61.904mm、画面竖直轴差41.047mm）。同一个精确TF把raw反算到base为 `[.432238146663,-.128407724098,.023518643913]`，相对冻结点主要Z低73.34mm；这反映当前坐标/观测一致性问题，**不能认定方块实际动了73mm**。

仅离线反事实：不改seed框或原门，把尺度公式当前距离暂取上述实测color Z，宽/高比=.908538008978/.987748268746，均在原范围。这支持“距离预测不一致足以导致本次误拒绝”，不证明哪项安装外参、运动学或表面测量为唯一根因，不将raw点、距离或反算base写回运动目标。

末点旧归档URDF + 新SDK q纯FK得到指尖Z≈.1283265m，只作近似模型说明（URDF不是本轮现场重新导出），不当作实物尺量、同帧TF或两指包围证据。

## 交接与下一步

原日志 `scale_reconnected_onekey/visual_stack.log` SHA `2b4ea95cf977e1280ebab294fcb4432f6166b93c96f2f6c41bb557da5c8b834e`；精确续采 `scale_reconnected_exact_motion/frames.jsonl` SHA `cf8400de904f15983cb5646be09b7dd8026333361120986609bd68cd92054cb0`。console、相机/驱动/can_health日志和两批观察器一并留在证据根。

下一优先离线用此次准确seed/同帧框/TF/测量校核安装变换及模型预测，不重复 CAN/固件基线，不仅扩大.65门、盲增J5或把已有深度离群点直接重锁为新目标。任何应用代码/TF/运动规则或启动硬超时修改仍需先说明范围并获用户确认；用户“已连接/已恢复”不是该修改授权。Git仅本地，origin/main既有历史推送审查阻断未解除，不重试推送。
