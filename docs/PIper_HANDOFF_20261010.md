# 2026-10-10 暂停交接：一键紫色方块实机抓取

## 21:31 更新：活动 RGB-D TF 对齐采样时间戳（仅离线构建，未部署/未实机运行）

用户批准后，规范仓库中的 `grasp_lift_executor.cpp` 仅有两处活动路径 TF 查找改为按目标 `PointStamped.header.stamp` 查询：缓存到参考系的观测点和 `FreshFaceInsideJaws()` 的夹爪坐标变换。新增诊断打印源帧、相机消息时间戳、TF返回时间戳及坐标；时间戳为零或该时刻 TF 不可用时明确失败，禁用 latest-TF 回退。当前真实 YAML 的 depth-only 模式关闭，备用 depth-only 回调没有改。代码尚未同步至或构建在 `/home/johnwick/piper_ws`，没有启动节点/机械臂命令；不能据此宣称坐标链或抓取已修复。

离线验证：Humble `colcon build` 成功，包内6个测试目标通过；临时构建位于 `/tmp/ub_tf_stamp_*`。用户提供的实体观察（尖端还需约5–8cm向下、并沿机械臂当前朝向向后约8–10cm）已作为未标定方向信息保留，不是已换算的机器人坐标位移，本轮未写入运动配置。精确代码提交哈希与 `git revert` 命令在规范仓库 `PIper_PROGRESS.md` 的下一条提交回退记录中。

## 20:50 新增核对：相机帧与工具模型

用户现场报告夹爪尖端距桌面约9cm。模型不是没有夹爪：PiPER URDF有`gripper_base`及`link7/link8`指爪视觉/碰撞网格；但MoveIt arm链终点是`link6`，当前YAML的`end_effector_link=link6`，抓取器通过`gripper_tip_offset_m=0.1358m`换算link6和指尖的目标。上轮`GRASP_LANDING`纠偏后FK给出模型actual_tip z=`0.0830m`、expected_tip z=`0.0757m`、差7.3mm；这不是对桌面的实测距离。需要把桌面高度、目标表面点、link6/TCP及实体动作时刻放到同一坐标/时间核对，不能将模型FK精度当成实物触点证明，也不能直接盲加9cm下降。

为遵循用户要求自行看相机，本轮只启动Astra深度流和脚本既有RGB发布器抓帧，未启动机械臂控制/MoveIt/Servo，无运动命令，采完已关闭。RGB 320×240严重洋红偏色、暗色遮挡显著，当前帧没有清楚辨认出紫色方块/完整夹爪；深度640×400有效点158,368，中位距离244mm（这是相机距离，不是垂直桌高）。图像保存在`/home/johnwick/brain_robot_logs/camera_inspection_20261010_2048/`。这不是上轮抓取时同步的录像，因此不能把当前图与上轮FK做逐帧对应。

## 2026-10-10 20:22 最新重试：观测/搜索/对齐、预抓取和下降均执行，闭爪前检查退出

从规范仓库`8d7a483`运行原默认入口，日志目录`/home/johnwick/brain_robot_logs/onekey_retry_20261010_2021/`。`AUTO_START=1`无需按键，脚本完成`[7/7]→OBSERVE_POSE_REACHED→SEARCH→ALIGN→GRASP_READY`。中心小扫有多个实测到达日志，之后进入FULL_SEARCH并获得目标。本轮未改源码、配置或一键脚本。

目标锁定`base_link (0.433,-0.128,0.085)m`。规划冻结ALIGN时的抓取朝向；抓取器计划末端高度从0.208m降到0.180m，联合关节J5终点数值由+0.291366降至+0.212520rad，J2/J3同步补偿。79点预抓取、8点Cartesian下降及一次5点落点纠偏均交给`piper_jog_adapter`执行。纠偏前模型tip误差18.1mm，纠偏后7.3mm。本轮原始CAN反馈解码得到J5：TARGET_ACQUIRED时约+0.478rad，进入GRASP_READY前升至+0.734rad；实际抓取预抓取中从+0.738降至+0.290rad，下降到+0.2126rad。前一段对应ALIGN视觉伺服（YAML以J5作为vertical_joint，sign=+1），`TARGET_ACQUIRED`仅表示从SEARCH进入ALIGN，不表示完成对齐；之后才是抓取执行器MoveIt轨迹。日志缺ALIGN期间的逐帧像素误差和Jog命令速度，因此不能判定vertical sign是否反了；但可以确认末段笛卡尔下降有J5参与。纠偏前后模型FK结果不能单独证明实体夹持中心正确。

用户明确以实物形态为运动方向依据：手臂由弯曲变直表示现场观察到上抬/远离；不能单凭joint5数值正负把该现象翻译成上/下，也不能用角度数值否定用户的实体观察。控制链代码区分视觉ALIGN和抓取MoveGroup：ALIGN按像素误差发布JointJog给Servo；达到稳定帧后进入GRASP_READY并停止Servo；之后才由抓取执行器规划到预抓取位并执行Cartesian下降。TARGET_ACQUIRED是SEARCH发现目标后进入ALIGN，不是最终对齐完成。因此若上抬发生在这一状态窗口，应先诊断ALIGN误差/方向；若发生在GRASP_READY后的79点MoveGroup轨迹，则核对预抓取Pose、物理模型与实际动作。不能仅用某个关节符号直接改下移量。

退出前命中`FAULT_FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，没有闭爪、抬升或释放。代码中的`FreshFaceInsideJaws()`将无新鲜RGB-D、夹爪反馈陈旧、目标尺寸异常/TF错误及目标面点在两指捕获区外都映射为false；现有日志没有具体子原因。检测器在接近过程中记录target LOST，后续没有再次记录DETECTED；这可能导致新鲜度分支失败，但不证明目标3D位置一定错误。现在无法仅凭该轮选择“MoveIt路径错误”或“目标坐标错误”。需要同步保存细分诊断、图像和关节/末端反馈。

50mm张爪请求的实体反馈仍为0.1021m不变；当前实体YAML允许在张爪反馈未确认时继续approach。该问题尚未被本轮闭爪测试验证。脚本以退出码1退出，已清理一键栈，未发`DisableArm`/`ResetPiper`；脚本报告PiPER保持使能。末态没有退出后的新反馈独立复核。代码改动必须先由用户批准；建议的下一项仅为非行为性诊断日志：ALIGN期间记录`error_y_px`、J5命令速度和实际反馈；闭爪检查记录拒绝子因、目标变换到`gripper_base`的坐标、RGB-D年龄和开口，不改轨迹、配置门或执行顺序。

## 2026-10-10 20:18 最新复测：在[5/7]就绪阶段被CAN反馈停滞中止，未运动

现行代码仍是按用户要求撤销颜色候选丢失停止门后的版本（commit `c7a86e9`）。本轮默认`AUTO_START=1`一键实测日志在`/home/johnwick/brain_robot_logs/onekey_reverify_host_20261010_2018/`：深度/RGB首帧通过、MoveIt加载、检测器报告过方块候选；卡在`[5/7]`完整MoveIt反馈/自体过滤TF检查，未到`[6/7]`、`[7/7]`，没有到观测、搜索或抓取运动阶段。

主直接事件为`can_health.log`的`CAN_RX_STALLED_3S`；PiPER驱动记录反馈中断并抑制输出，5.37秒后恢复，adapter收到外部急停并转FAULT。深度探测同时报告camera-depth到`base_link` TF连接缺失或时间年龄超限。运行期具体阻断及命令见`docs/PIper_PROGRESS.md`首节。脚本清理后控制/相机进程已退出；事后`can0`仍UP/ERROR-ACTIVE、1Mbps/.750、1秒RX增加2334、错误/丢帧0；这个事后快照不代表运行中没有发生停滞。没有ResetPiper/DisableArm或运动目标。本轮未做第二次重跑。

下一步先用该目录的`can_health.log`、`piper_driver.log`、`visual_stack.log`和相机日志确定RX停滞与TF不可用的触发情况，再继续同一默认入口；不可声称本轮已到观测姿态，也不要把目标检测到等同于SEARCH/抓取。

## 2026-10-10 20:14 最新状态：已按用户要求撤销颜色候选丢失停止门

用户明确要求撤销`eed71ff`新增的“颜色候选丢失即停止”门并回到上一版。本轮已从规范源码及一键实际工作区`/home/johnwick/piper_ws`移除候选订阅/轮询/adapter disarm分支和实体YAML开关。规范/运行源码一致，并与`eed71ff`父版本哈希一致（执行器`9df895cfb6f05eaff96178e9d7ddb932f3b6778886cf4f73bccc1bb6a77e9f5c`；YAML`907e3d0608c8e7c6faf81482c9d4817dc67cf6ab5c14df2bebdb67705ecfb05c`）。两个ROS包重新构建成功，install执行器指向新构建版本；没有启动一键脚本，没有发送实体运动/夹爪命令。

因此，20:00实测中途停车仍是旧版本的有效历史记录，但现行执行器不再因颜色候选短暂丢失而截断预抓取/下降。下一步应按原流程复测同一一键抓取主线，观察是否走完既定预抓取与下降；本轮不再加门、不另建路线。夹爪102.1mm反馈异常仍为已有独立记录。

## 2026-10-10 19:17阶段历史：颜色可见性停车曾构建，未重跑实体

用户确认紫色方块位于夹爪正下方，并指出相机应能同时看见夹爪及被夹物。本轮仅做代码/离线几何与构建，没有向实机关节或夹爪发布命令；最近可追溯实体静止反馈仍是18:43:54六轴速度0、使能true、夹爪102.1mm。

唯一真实YAML现启用`approach_visibility_required=true`。实体抓取执行器在长预抓取、末段下降及一次落点纠偏期间检查可靠的颜色候选topic；深度valid消失但紫色仍在图像中不触发停车。候选缺失超过0.20s则调用已存在的`/piper_jog_adapter/disarm`，停止适配器正在执行的余下轨迹并保持反馈姿态；不会闭爪、复位或DisableArm。开始发送这类轨迹前，要求候选新鲜且停车服务在线。颜色候选不是两指捕获证明，原RGB-D、落点及闭爪反馈门仍在。

规范、实际源码和唯一YAML已同步。含“轨迹终点再检查一次候选可见性”的最终版本由`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick`成功构建；executor SHA`f29503399d63a30462c2eb50bb2670b784b6c0217d85f9494560dfcb045a4b6a`，YAML SHA`1758895ad5dd7e769c33d3907abcc71412a694e9d4134e1e0a6727709cd21e96`，install二进制SHA`47280eea8694021d2ea429595ff223b1f4de181c29e66d106db818edb81249d9`。未运行测试套件。本轮ROS域78重启隔离MoveIt复核被sandbox拒绝DDS UDP socket，进程退出；这是模型工具可用性限制，不是机器人/IK结果。

按URDF，夹爪张合沿link6±Y，finger主体从link6约z=0.1358m沿负Z伸出；link7/8 STL局部边界分别约`x±28mm,y=-76.5..0mm,z=0..26.5mm`。当前点目标的近似FK在link6为`[+1.9,+0.6,+123.9]mm`，离手指根部z=135.8mm约12mm；仅说明模型里它靠近两指中心，未在规划场景加入方块做碰撞计算，也未完成外部相机旋转/水平标定。直接J5+0.10rad的模型会将目标link6-X改为约-19.6mm、TCP也移动约厘米级，尽管像素投影朝画面上方回移；故不执行裸J5增量。下一步在用户已恢复的自动流程授权下，用已构建版本运行唯一默认一键入口，实测颜色消失时是否及时停车；再继续做“保持抓取点、由其他关节补偿”的有限J5姿态候选，隔离规划未可用前不凭像素直接下发。

本轮不改变既有夹爪断点：50mm张开命令反馈仍102.1mm无变化，尚未有闭爪、抬升、释放证据。最新实机失败、图像与关节仍见本文件下方18:40节及`docs/evidence/piper_onekey_20261010/aligned_real_run.txt`。

J5的逐值FK、TCP和RGB像素推算见[`j5_projection_review.md`](evidence/piper_onekey_20261010/j5_projection_review.md)；它解释了为什么裸加J5虽能让近似目标像素上移，却会同时造成link6-X偏移和TCP移动。不得将表格数据当成可执行实机关节目标。

本轮改动已提交为 `eed71ff fix: stop grasp approach when target leaves camera view`，精确包含进度首节列出的7个文件，`git show --check`通过且这些路径现已干净。普通沙箱报 `.git/index: Read-only file system` 的原因是当前执行视图将 `/mnt/hgfs` 以 `vmhgfs-fuse ro` 挂载，虽然索引权限位为777；之前以及本次成功提交均通过 `require_escalated` 执行Git写操作，不是修改chmod。其他vendor/reference脏改未暂存，保持原样。

## 最新实机更新：18:40–18:44（优先于下方暂停/离线历史）

用户要求先实际运行一键流程，已执行默认AUTO_START=1、RGB紫色模式、完整抓取路径，日志目录`/home/johnwick/brain_robot_logs/onekey_aligned_retry_20261010`。实际参数三个true：preserve_aligned_grasp_orientation/static_target_lock/initial_search_center_first。下节SHA仍是本次实际部署版本。

实际链：观测（18:41:23）→中心8点/确认回中心→既有full找到目标→ALIGN（18:41:55）→GRASP_READY（18:41:57）→79点预抓取→9点末段→一次5点落点纠偏。此前IK -31未复现；本次停止于18:42:15的`FAULT_FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，没有闭爪/抬升/释放。模型FK6.6mm不是实物落点证明。夹爪50mm命令后反馈仍102.1mm，未验证响应。

重要现场纠正：用户确认相机能看见夹爪，也应能看见夹持的物体；物体看不见要排查超前/越过目标，不以正常FOV丢失解释。原始RGB方块由v≈105→145→231（320×240）移出下边缘，0019以后看不到；拒绝实际发生在新鲜RGB-D前置门，未计算inside=false。J5对齐.736835→末段.206293，确实参与但只是维持朝向；用户建议末段向下夹入，下一步应核对方向/重投影/两指位置再修有限末段，不盲重跑原路径或删除可见性门。

脚本实测退出1，实体栈和采集器全部退出；最后ROS关节[-.284442,1.808768,-1.049396,-.031748,.206293,.039354]rad。18:43:54被动2秒核对六轴速度全0、使能全true，无回零/失能。本次CAN没有断联，磁盘33%。原暂停位置已经不是当前起点。

Git内小证据：[实际一键输出/执行器关键行](evidence/piper_onekey_20261010/aligned_real_run.txt)、[原始RGB像素迁移](evidence/piper_onekey_20261010/aligned_real_image_trace.csv)。原始采集`/tmp/piper_onekey_aligned_retry_20261010_observer.jsonl`；画面`/tmp/piper_onekey_aligned_retry_20261010_images`，看0014..0021 RGB/对应debug。只读采集需`PYTHONNOUSERSITE=1 /usr/bin/python3`隔离用户NumPy2；末尾重复旧stamp不要当新帧。完整命令、判断和下一步见PIper_PROGRESS首节。

## 18:30之后接手更新（先读此节，下面保留暂停时历史事实）

用户已要求继续接手项目，当前项目工作恢复，但本轮未自动续跑实体控制。复用原两段抓取规划：冻结对齐时实测朝向，在域78/执行禁用的MoveIt中规划通过79点预抓取+9点末段，fraction=1.0、原包络与连续性检查通过。

已将`preserve_aligned_grasp_orientation=true`接入原执行器/唯一YAML，保留原规划、适配器和反馈门；构建部署通过，六套/49项测试无失败。当前executor源码SHA为`9df895cfb6f05eaff96178e9d7ddb932f3b6778886cf4f73bccc1bb6a77e9f5c`、实体YAML SHA为`907e3d0608c8e7c6faf81482c9d4817dc67cf6ab5c14df2bebdb67705ecfb05c`，规范/实际/install一致。下面旧SHA仅代表暂停时版本。

新输入及复现过程：[REPLAY.md](evidence/piper_onekey_20261010/REPLAY.md)、[冻结快照](evidence/piper_onekey_20261010/locked_grasp_snapshot.json)、[MoveIt结果](evidence/piper_onekey_20261010/measured_orientation_moveit_result.txt)。不再依赖原/tmp observer即可重做模型检查；模型开口50mm不是已验证的实际开口。

尚无新实体靠近/闭爪/抬升证据。102.1mm夹爪异常反馈，以及进入指尖时目标可能离开深度FOV的闭爪门可见性仍待验证。测试节点已退出，未发失能/复位。下一轮从此处继续，不重跑24个旧失败候选、不从CAN基线重新开始；完整命令/风险/下一步见进度文档最新首节。

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
