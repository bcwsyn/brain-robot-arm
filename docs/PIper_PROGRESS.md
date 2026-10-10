# PiPER 调试进度

### 2026-10-10 20:14–20:15：按用户要求撤销颜色候选丢失停止门，恢复上一版抓取执行路径

- 用户明确要求撤销我在`eed71ff`加入的“颜色候选丢失即中断预抓取/下降”门并回到上一步。本轮只撤销这一项：从`grasp_lift_executor.cpp`移除颜色候选订阅、可见性轮询与adapter disarm分支；从唯一实体`cube_task_real.yaml`移除`approach_visibility_required`。对齐锁定、MoveIt预抓取/下降、`piper_jog_adapter`、已有落点/夹爪反馈流程未改；本次没有启动机械臂或发实体命令。
- 规范源码与一键脚本使用的`/home/johnwick/piper_ws`源码SHA一致：执行器`9df895cfb6f05eaff96178e9d7ddb932f3b6778886cf4f73bccc1bb6a77e9f5c`，YAML`907e3d0608c8e7c6faf81482c9d4817dc67cf6ab5c14df2bebdb67705ecfb05c`；均与`eed71ff`父版本相同。`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick`通过（2包，50.2秒）；运行入口所用install执行器链接到新构建产物，二进制中不含候选丢失停车标记，install YAML SHA与源码一致。
- 20:00历史实测仍如实保留：当时的旧版本确实在预抓取中途因颜色候选丢失停止，未到预抓取终点、未执行下降和闭爪。撤销的是代码门，不是这条历史事实；20:00记录中“应保留该门”的建议已被用户本轮明确指令取代。下一步按原一键主线复测预抓取是否完成，不另加候选丢失门或其他新流程。

### 2026-10-10 20:00–20:03：默认一键实机运行到 GRASP_READY；颜色可见门在预抓取途中提前停车

- 起始规范仓库 HEAD `0986a75`；运行入口 `/home/johnwick/start_brain_robot_cube_real.sh` 与规范脚本 SHA-256 同为 `e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`。开始前无 PiPER/视觉/MoveIt 栈残留；根分区 33%，`sudo -n true` 返回0；can0 为 1 Mbps/sample-point 0.750、ERROR-ACTIVE，2秒 RX `63335095→63339957`（+4862），errors/dropped=0；USB-CAN 与 Astra RGB/深度设备枚举正常。
- 只读 SDK 当前反馈（无运动/使能/复位/夹爪命令）：高速约100Hz、数据年龄8ms，初始 `q=[-0.284,1.794,-1.056,-0.031,0.198,0.039] rad`、各轴速度0；低速约20Hz，六轴均使能，状态码均`0x40`，collision/error/stall均false。单次官方限位查询为六轴`-1700..1700`（0.1°单位，即±170°）、速度300（0.001rad/s）、加速度500（0.001rad/s²）；当前实体控制器限位读取独立于MoveIt适配器的更紧动作包络。
- 实际命令：`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/onekey_live_20261010_200016 /home/johnwick/start_brain_robot_cube_real.sh`。脚本复用健康can0，深度与RGB均收到首帧，通过`[7/7]`；真实自动从当前位置启动到观测姿态，12点、最大相邻步长0.08rad、规划时长41.4s，实测到达`OBSERVE_POSE_REACHED`并进入SEARCH。
- 搜索实际符合中心优先代码：观测位中心保持→J1约`-0.08↔+0.08rad`、J5围绕观测值约`±0.12rad`的8个中心小扫段（每段均有`SEARCH_SEGMENT_REACHED`实测反馈）→反馈确认回中心→`CENTER_COMPLETE`→才开始既有`FULL_SEARCH`。随后目标在full搜索中变为DETECTED并进入`ALIGN→GRASP_READY`。首个全搜索方向J1负/J5下；这不是只发轨迹而无实动。
- 抓取执行器锁定目标`base_link=(0.430,-0.128,0.080)m`，发出50mm张爪目标，但夹爪反馈仍为`102.1mm`，日志`GRIPPER_OPEN feedback unconfirmed`。其后MoveIt成功规划78点预抓取，计算了8点笛卡尔下降路径（尺寸启发式插入12mm）；预抓取轨迹估时7.675s，适配器于`1791633776.875`接受78点。
- 颜色候选于`1791633769.667` DETECTED，`1791633781.672` LOST；约0.26s后（超过配置连续丢失0.20s）执行器调用adapter `/disarm`，日志确认`hold acknowledged=true`，并停止为`APPROACH_TARGET_LOST_HOLD_NO_CLOSE`。这是预抓取78点轨迹执行约5.1s时中止，**预抓取未到计划终点，8点下降未执行、未闭爪/抬升/释放**。因此用户看到“离方块仍有距离”与日志相符；并非已到达抓取点后才停车，也不是MoveIt规划失败、CAN失联或机械臂碰撞。
- 该门只根据`/brain_robot_vision/color_candidate_valid`是否新鲜且为true停车，不含目标到夹爪的距离/路径进度判断。它成功阻止了继续盲走，但本次实测证明“检测器候选丢失”不能单独证明机械臂已经越过方块：没有保存颜色/RGB关键帧，无法区分真实目标离开FOV、夹爪遮挡/视角变化和检测器瞬时假阴性；不能据此直接删除门或放宽时限。RGB-D检测日志在同一秒报告`PURPLE_CUBE target LOST`，还需同步图像确认。
- 脚本以1退出是保护门阻断后的预期失败路径。收尾后无PiPER/视觉/MoveIt控制进程残留；can0仍ERROR-ACTIVE、无错误。停止后高速反馈新鲜100Hz，`q=[-0.288,1.291,-0.952,-0.011,0.475,0.011]rad`；首次短读J1速度0.035rad/s，2秒后六轴速度均0，六轴仍使能且无collision/error/stall。没有调用`DisableArm`、`ResetPiper`，不失能、不回零。完整日志在`/home/johnwick/brain_robot_logs/onekey_live_20261010_200016/`，未提交大型日志。
- 下一步不重跑同一无影像记录的全流程：给现有测试采集器增加同步稀疏证据（RGB/调试图、`color_candidate_valid`、RGB-D `target_valid`、锁定base目标与六轴反馈时间线），只在一轮受控运行中确定丢失时方块是否仍在原始RGB且预抓取进度/末端离目标距离；按结果修复检测保持/相机投影或预抓取路径。张爪反馈102.1mm未变化仍是独立问题，不把当前停止归咎于它，也不得绕开新鲜夹持区/闭爪反馈门。

### 2026-10-10 19:17–19:30：接入“目标还在画面内才继续接近”门，并核算J5候选

- 以最新一次实机反馈和图像为基准：末态关节 `[-.284442,1.808768,-1.049396,-.031748,.206293,.039354] rad`；18:42左右紫色候选中心从 `v=105→145→231→画面外`。用户明确方块在夹爪正下方且正确抓住时相机应能看到它。上次因RGB-D有效性/深度门停止，不是几何程序已测得`inside=false`；本轮未把旧锁定点误当成可闭爪证据。
- 已在唯一实体执行链增加 `approach_visibility_required=true`：`grasp_lift_executor`订阅检测器现有可靠话题`/brain_robot_vision/color_candidate_valid`。预抓取、下降及唯一落点微调发轨迹前要求颜色候选新鲜；执行期间每20ms轮询，连续丢失0.20s则调用现有`/piper_jog_adapter/disarm`，截断适配器剩余轨迹并以适配器最后关节反馈保持；不闭爪、不ResetPiper、不DisableArm。发轨迹前还要求该停止服务可用。仍保留RGB-D目标、落点和闭爪前鲜帧门；颜色候选可见不等同目标已在两指内。
- 以URDF `joint7/joint8` 与指爪STL几何核对：张合方向是link6的±Y，指爪主体沿link6的负Z伸出；原始link7/8网格边界相同，局部X约±28mm、Y约-76.5..0mm、Z约0..26.5mm。按本次相机TF假设与上一帧锁定表面点，当前模型目标在link6约 `[+1.9,+0.6,+123.9] mm`，与±Y张合中心接近，且离指根z=135.8mm约12mm；这只是模型坐标，未在MoveIt中加入方块做实体碰撞/夹持验证，旋转/水平外参也未标定。直接增加J5 `+0.10 rad`的纯关节假设会把模型目标link6-X移至约`-19.6 mm`，并令末端基座坐标约移至`[.4223,-.1257,.0612] m`；相机投影趋势`v≈293→238`，同时发生约厘米级侧向偏移。J5不是单独竖直下降轴；不将未补偿的J5增量发送到实机。
- 代码/唯一YAML已同步到规范仓库与实际工作区。加入“轨迹终点刚好收到关节到点反馈时，再确认一次颜色候选”的末端竞态门后，最终执行 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 成功（两包，约91秒）；C++源码规范/运行SHA均为`f29503399d63a30462c2eb50bb2670b784b6c0217d85f9494560dfcb045a4b6a`，实体YAML规范/运行/install SHA均为`1758895ad5dd7e769c33d3907abcc71412a694e9d4134e1e0a6727709cd21e96`，新执行器二进制SHA=`47280eea8694021d2ea429595ff223b1f4de181c29e66d106db818edb81249d9`；源码规范/运行逐字一致，`git diff --check`通过。未运行测试套件。
- 本轮又尝试在`ROS_DOMAIN_ID=78`启动`allow_trajectory_execution=false`的隔离MoveIt复核；DDS UDP socket被当前执行沙箱拒绝，两个规划进程随即退出，因此该次复核没有得到规划结果，不能记成IK/碰撞失败。此前已提交的79点+9点离线规划结果仍是历史模型证据，不是当前J5方案或实机结果。没有发送新的实机关节/夹爪命令。
- 逐轴FK投影的完整输入/输出表及坐标假设已保存为[`j5_projection_review.md`](evidence/piper_onekey_20261010/j5_projection_review.md)，可与真实像素轨迹CSV对照。
- 首次普通沙箱 `git add` 被拒绝，系统证据显示 `/mnt/hgfs` 在该执行上下文以 `vmhgfs-fuse ro` 挂载；`.git/index` 权限位为777，因此问题不是chmod可修复的文件mode。随后用此前成功提交所用的 `require_escalated` 执行方式，只暂存本节所列7个文件并成功提交 `eed71ff fix: stop grasp approach when target leaves camera view`；`git show --check`通过，指定7个路径提交后干净。其他vendor/reference改动没有暂存或覆盖。
- 当前仍未完成闭爪/抬升/释放；实机夹爪反馈停留`102.1 mm`且50mm开口命令无反馈变化，是独立阻断。下一步用本轮已构建的保护代码运行同一默认一键入口，观察目标移出画面时适配器是否及时停止；同时只在隔离MoveIt恢复可用后规划“保持抓取点、由其它关节补偿的小J5姿态变化”，不发裸J5步进，不重复完整盲接近。最终仍需新鲜两指可见/闭爪反馈再继续抓取。

### 2026-10-10 18:40–18:44：按用户要求先实跑一键流程；靠近恢复，目标移出下边缘，禁止把轨迹结束当已夹住

- 用户明确要求先实验默认一键流程再依据现象处理；最新授权恢复实体运行，18:24暂停及18:30只做离线的限制属于历史阶段。确认无实体控制进程后，直接执行 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/onekey_aligned_retry_20261010 /home/johnwick/start_brain_robot_cube_real.sh`。入口未改，使用上一节已构建的新模式/唯一YAML；实际节点只读确认`preserve_aligned_grasp_orientation`、`static_target_lock`、`initial_search_center_first`均true。无等待按键、固件/主从/ResetPiper/零点写入、接口重载或底层巡检。
- 脚本自行完成日志维护，磁盘33%、可用51317MB；CAN RX增长直接复用。18:41:02.206 PREPARE，7点/22秒轨迹接受；18:41:23.882 SEARCH/OBSERVE_POSE_REACHED，实测约[-.004623,.979062,-.748609,0,.309509,0]rad。中心8点实际到达、18:41:51.822 CENTER_RETURN_CONFIRMED后进入既有full，18:41:55.325 ALIGN，18:41:57.323 GRASP_READY；观测与搜索没有再次阻断，也不是只停在固定角度。
- 锁定目标约[.433,-.128,.083]m；50mm张爪命令已调用，反馈102.1mm始终不变，既有明确approach override继续靠近但不称张爪成功。18:42:02.351锁定当前四元数[.138143,.930759,-.049704,.334863]；79点PTP/9点Cartesian规划通过并经原adapter真实执行，18:42:13.466预抓取到达，18:42:15.362一次5点落点纠偏。模型FK距离17.1→6.6mm，仅是模型内计算，不证明物体已在指间；未出现此前IK -31。
- 18:42:15.769明确故障`FAULT_FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，没有发闭爪/抬升/释放。此处不是已算出几何inside=false：目标/深度valid在18:42:07.110已false，`FreshFaceInsideJaws`的新鲜RGB-D前置分支拒绝，未进入`FRESH_JAW_CAPTURE face=...`计算。因此故障名称不能误读为已外部量测确认夹爪与方块距离。
- 同步查看原始RGB/调试图：0015/16仍见方块，0018落在彩色画面下边缘、0019以后原始RGB也看不到，不只是深度黑区。用与现有配置相同HSV125..160/S>=35/V>=45、area>=40离线提取最大色块（仅图像证据，非完整检测器判定）：320×240原图中心v约105→145→231→无候选；对应18:42:02/05/08/11。这证明物体随靠近移出画面，尚不能仅凭RGB/FK确定实物是否被越过或哪个外参错误。
- 用户新增现场事实：相机能看到夹爪，正确夹住时也能看见方块；若看不到方块，需按夹爪超前/越过目标排查。该条件优先于此前“末端必然离开FOV”的模型推断，禁止把丢失当正常、撤掉可见性门或用旧锁定模型盲闭爪。用户建议J5向下有助夹入：实测J5从对齐.736835降到末段.206293rad，确实受控，但目的是J2/J3补偿/保持link6朝向，未以相机中的两指夹持位置闭环下俯；锁定朝向可规划不等于实体抓取方向正确。此前0014→15 J5约.614744→.736835，方块v153→105（J1也少量改变），提示J5下俯方向需用实图核验，不盲目宣称关节正负与现场“向下”等价。
- 实测脚本退出1，保护清理结束，无控制栈/采集器残留、未回零/失能；最后新鲜ROS反馈18:42:26.060为[-.284442,1.808768,-1.049396,-.031748,.206293,.039354]rad。18:43:54仅被动2秒高速/低速反馈，六轴speed_raw全0、使能全true、每轴200帧；RX52219923、errors/drop/bus-error0。本轮没有断联，不能用CAN或磁盘解释本次抓取停止。
- 小型真实输出及像素迁移已入`docs/evidence/piper_onekey_20261010/aligned_real_run.txt`、`aligned_real_image_trace.csv`；大日志`/home/johnwick/brain_robot_logs/onekey_aligned_retry_20261010/`，脚本输出`/tmp/piper_onekey_aligned_retry_20261010.log`、采集`..._observer.jsonl`、画面`..._images/0014..0021_rgb.png`。采集器首次因用户NumPy2与系统cv2不兼容退出；改用`PYTHONNOUSERSITE=1 /usr/bin/python3`后正常，仅只读采集问题，不是控制链故障。收尾SIGINT采集PID203309，rclpy重复shutdown异常不代表实机失能；末尾复用旧stamp的图片/快照不能当新鲜数据。
- 下一步不重跑相同路径或旧24候选：用本次图像/真实关节比较锁定目标重投影与实际色块轨迹，验证相机安装旋转/TCP和J5下俯方向；复用原MoveIt/adapter把接近调整为保留方块在两指可见夹持区的有限末段，而不是按同一错误FK继续。保留用户已确认的YZ测量，不重问。102.1mm夹爪反馈/开闭响应仍是独立阻断；未宣称最终抓取完成。

### 2026-10-10 18:30后接手：保持对齐朝向的完整模型路径通过，接入原执行器

- 起始HEAD `ec26e1d`，已核对规范Git状态、后续提交及暂停交接`docs/PIper_HANDOFF_20261010.md`，保留全部既有供应商/Astra修改、手册/升级包/deb；用户要求恢复项目工作并以历史经验为主、将接力输入持久化。本轮没有重新启动默认实机脚本，也没有重复CAN/固件/限位/USB基线实验；观测/搜索已通过的证据直接沿用。
- 新的最小动作只针对现有断点：复用历史靠近所用`review_surface_grasp_plan.launch.py/.py`，把18:20的实测关节和锁定点保存为`docs/evidence/piper_onekey_20261010/locked_grasp_snapshot.json`；加入`--snapshot`与`--orientation measured`，FK取得该快照link6朝向，冻结同一目标 `[.432,-.127,.081] m`，不再重复24个已失败的预设姿态，也不恢复旧外参。姿态四元数约 `[.130845,.932497,-.046782,.333377]`。
- 实際命令：source ROS/PiPER/app安装空间，`ROS_DOMAIN_ID=78 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml ros2 launch /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_surface_grasp_plan.launch.py`；同域调用复核脚本，`--config /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml --snapshot /mnt/hgfs/ub/docs/evidence/piper_onekey_20261010/locked_grasp_snapshot.json --orientation measured`。运行参数核实`allow_trajectory_execution=False`，无实体驱动/适配器/Servo/抓取执行器；只有FK/规划/笛卡尔服务和隔离历史joint_states，无实机命令。
- 工具实测返回0：Pilz PTP预抓取79点，末段Cartesian9点、fraction=1.000000，原限位及≤.35rad相邻跳变检查通过，未扩大包络；目标容差1mm/.01rad。预抓取末端关节约[-.289806,1.690819,-1.002263,.024991,.282856,-.032505]，末段约[-.289009,1.813758,-1.046209,.031950,.203877,-.039179]rad。沿用24mm预间隙/最多12mm夹入，末段保持同一朝向；FK误差2.25e-9m只证明模型一致性，不证明实物精度/桌面碰撞/夹持成功。模型开口50mm是假设，实际102.1mm反馈未验证，不能因此闭爪。结果与独立复现步骤已保存`measured_orientation_moveit_result.txt`/`REPLAY.md`；新工具不依赖原/tmp observer。
- 已实施最小应用修复：唯一实体YAML `preserve_aligned_grasp_orientation=true`。原TopDownPointGraspAndLift在静态目标锁定及新鲜关节门通过后，只捕获一次当前末端四元数；两个姿态目标均使用它，不枚举预设yaw/tilt。复用原预抓取+末段完整预规划、适配器、限位/碰撞/落点纠偏/闭爪/抬升反馈；其他profile默认false，保留历史行为，不另写基础运动程序。PTP中间姿态不承诺严格不变；既有TOP_DOWN状态名保留，新增`ALIGNED_ORIENTATION_LOCKED_FIXED_APPROACH`标识实际策略。
- 规范/实际源与install配置一致：executor SHA `9df895cfb6f05eaff96178e9d7ddb932f3b6778886cf4f73bccc1bb6a77e9f5c`；实体YAML SHA `907e3d0608c8e7c6faf81482c9d4817dc67cf6ab5c14df2bebdb67705ecfb05c`。`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick`返回0/47.3秒；`colcon test --packages-select brain_robot_pick_place`返回0，六套全通过，`colcon test-result`49 tests/0 errors/0 failures。额外规范源码的抓取/相机/启动pytest25项通过；py_compile和限定文件diff检查通过。二进制含新增锁定日志。
- 收尾精确SIGINT测试launch PID200584；子进程200613/200615已退出，已知MoveIt2.5.9析构-11再次出现，发生在成功规划之后，不是规划失败或实体CAN故障。未发Enable/Disable/Reset/MasterSlave/0xAE，未发真实预抓取/闭爪/抬升；保留机械臂先前使能/静止状态。
- 剩余两个具体问题不能掩盖：真实夹爪反馈102.1mm超出已知接口范围，且张爪无响应；当前闭爪门要求新鲜面点在夹持区，按已确认光学YZ偏移，物体进入指尖附近时可能处于深度画面下方之外，须处理固定3D目标的可见性而非重入搜索或删除门控。用户YZ测量不再重问，未标定旋转/水平偏移仍保留。新模式尚未实体复跑，总目标未完成。
- 下一轮第一条可复现命令见`docs/evidence/piper_onekey_20261010/REPLAY.md`；新鲜实机数据采集可用唯一脚本`BRAIN_ROBOT_AUTO_START=0`，不按1/2、不启用运动，只针对当前夹爪反馈与末段投影采图。之后才在同一主链验证新模式真实靠近/落点，并取得有效夹爪响应；不得把本模型路径直接当可发关节序列。所有权/部署/真机与模型证据均已更新接手记录。

> 当前状态（2026-10-10 18:24）：按用户要求已暂停实机工作，交给此前参与项目的老师傅。最新一键测试到GRASP_READY后预抓取IK失败；详细证据及下一步见 [暂停交接记录](PIper_HANDOFF_20261010.md)，本轮记录追加在文件末尾。

### 2026-10-10：按镜头实测指尖偏移修正外参，禁止把画面中心当作夹持区

- 用户确认实体尺寸的测量基准：从相机镜头中心，沿相机光学方向，夹爪尖端约在画面向下`0.070 m`、镜头向前`0.105 m`；这是本轮新增的现场证据，不是由旧TF反推。按ROS REP-103，相机光学轴为X右、Y下、Z前（参考 https://www.ros.org/reps/rep-0103.html）。
- 旧启动外参`gripper_base -> camera_link = [0,-0.05,-0.10] m, RPY=[0,-pi/2,0]`把模型指尖算为camera-optical `[-0.05,0,0.2358] m`；新测量在保留旋转未标定假设、未测水平偏移取0的条件下，推得平移`[-0.070,0,0.0308] m`，模型指尖重投影为`[0,0.070,0.105] m`。二者相距约`0.156552 m`，解释了“已经对齐但夹爪仍离方块很远”的量级；这仍是近似安装测量，不是完整六自由度手眼标定。
- 当前深度内参`fx=fy=478.756866,cx=326.135559,cy=199.873489,size=640x400`下，新指尖投影`u=326.14,v=519.04`，落在图像下方之外。该矛盾说明画面中心不能直接证明两指已经包住目标，且实物“下方”与光学Y方向虽已确认仍需用可见指尖/目标的同帧验证；没有据此盲目向下增加`0.156 m`运动。
- 将唯一生效的`cube_task_real.yaml`加入`piper_camera_mount_tf`测量记录，启动文件改为从该配置读取平移/旋转并检查有限值；规范与`/home/johnwick/piper_ws`运行文件SHA一致。新增只读`review_camera_mount.py`和5项外参回归测试，验证旧外参差异、测量反投影和启动参数顺序；实际结果5/5通过，连同抓取/驱动回归共21项通过。
- 将`gripper_open_value`恢复为官方50mm命令基线。此前静态`46.2mm`反馈不是“完全张开”的证据，新的实测闭爪前门控不得把它当作成功；本轮没有发送夹爪、六轴或失能命令。之前的`0x01`开爪实机复核仍只有命令进入链路、反馈未变化，未知夹爪零点保持未解决。
- 本轮没有运行自动脚本、没有启动实体控制栈、没有修改/写入夹爪零点；CAN及已有控制进程状态沿用前一轮证据，未重复底层巡检。当前阻断从“模型末端位置与现场不符”转为“相机旋转/水平偏移和指尖可见性仍未完成外部标定，且真实夹爪开合反馈未验证”。
- 下一步：先在静止、无运动条件下用真实图像同时核对指尖和方块投影/TF（或取得一组手眼标定对应点），再离线重算预抓取/下降；只有新鲜目标确实落在两指几何门内且夹爪反馈发生位移，才允许继续闭爪、抬升和释放。第一条命令为`PYTHONDONTWRITEBYTECODE=1 python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_camera_mount.py --config brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml --observation /tmp/piper_stationary_geometry_review.json`。本轮不允许真机运动。

### 2026-10-10 12:42–12:53：恢复后实机中心扫描/锁定/下降通过，修复保持约束，阻断转为夹爪

- 起始HEAD `f90e6ef`。用户明确没有碰机械臂、已恢复接口；不把先前运行期冻结归因于用户干预。内核12:40:59/12:41:09断开、12:41:05/29新枚举USB-CAN device19/20，接口索引9 DOWN/STOPPED，sudo非交互0。仅固定`sudo -n ip link set can0 type can bitrate 1000000 sample-point 0.75; sudo -n ip link set can0 txqueuelen 1000; sudo -n ip link set can0 up`一次，3秒RX41→7027，无错误；之后两次启动均直接复用链路。
- 增加不发送CAN帧的/tmp被动时间线`piper_rx_timeline_20261010.py`，每秒记录ID计数、RX/TX/errors及停流时最后帧，限600秒，不提交脚本/原始日志。连续251..256每轴约100Hz、3A0..3A7约200Hz、低速约20Hz。加载只读`usbmon`后仅捕获003/020设备URB事件计数/状态/长度、不记录其他USB数据或payload，限300秒，证据`/tmp/piper_usb20_timeline_20261010.log`。Linux官方 https://docs.kernel.org/usb/usbmon.html 明确它记录驱动/HCD请求，不保证错误HCD下等同物理总线事务。
- 第一默认自动运行`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`，证据`/tmp/piper_real_run_20261010_1243.log`，实际返回1。起点约[-.019921,-.005181,.016816,.149896,.229232,-.182098]rad，目标[0,.98,-.75,0,.30,0]rad；14点观测轨迹接受，1791607492.426实机SEARCH(OBSERVE_POSE_REACHED)、CENTER_HOLD。观测实测[0,.971055,-.743428,0,.299234,0]在0.01rad门内，随后首个中心小扫规划两次失败，不是CAN中断。日志明确J3实际-.743428、锚点-.741928，差.0015超过上轮固定±.001路径保持约束；FixStartStatePathConstraints尝试过渡但最终路径被拒。保护退出未回零/失能，原始RX持续。失败日志已保留`/tmp/piper_center_first_physical_failure_20261010.log`和`...driver...log`，不把新软件问题写成硬件错。
- 修复现有PlanSearchSegment：getCurrentState取得同一实测快照，setStartState明确使用它；非搜索轴目标仍固定初始化锚点，路径带同时包含锚点与实测起点并留1mrad余量，但绝不超既有0.01rad反馈包络。起点漂移超过0.01或非有限时拒绝，打印具体SEARCH_HOLD_AXIS_DRIFT_EXCEEDED轴；不逐段重置锚点累积漂移、不篡改已规划轨迹、不绕过MoveIt/适配器/碰撞。官方setStartState参考 https://moveit.picknik.ai/main/api/html/classMoveGroupInterface.html ，本次具体原因依据本地日志，非网页推断。
- 同步规范/运行源码SHA`2c6bf032292687055a5b159e6f8823dca9e6a2287ea09599e0728cd5eabb72a6`。单包colcon构建返回0/约53秒；CTest5套全通过（新增2个保持带gtest，实际40项），18项抓取/脚本pytest单独通过。隔离ROS域78四场景全通过：原双侧/中心目标优先/过期反馈禁止扩扫，加J3在CENTER_HOLD后偏差1.5mrad仍首扫规划通过且回固定锚点。证据`/tmp/piper_center_settled_replay_result.log`。仍是假反馈、无实体驱动/Servo/适配器，不能当物理执行证明；确切测试launch PID146778 SIGINT退出，既有MoveIt析构-11再现，所有测试控制进程退出后再实体复跑。
- 修复后同一默认脚本复跑证据`/tmp/piper_real_run_20261010_settled_fix.log`，1791607794.126观测实测就位；中心8点均真实SEARCH_SEGMENT_REACHED，1791607821.556实际CENTER_RETURN_CONFIRMED，再展开原full。两段full后1791607828.806目标有效→ALIGN、7829.807 GRASP_READY。RGB实帧可见泡沫台面紫色方块；15秒采样RGB75/深度445/反馈2893，target/depth_valid true、DEPTH_GRASP_ALLOWED。没有重新启用腕部Octomap或盲扩大扫描。
- 实体抓取进一步通过：76点预抓取+9点下降，SURFACE_GRASP小边33.3mm、夹入12mm；1791607845.376落点距离8.1mm，执行一次5点纠偏后7845.815模型FK误差2.8mm、姿态.0128rad。该FK不是外部TCP标定；没有现场外部量测就不宣称指尖实体绝对误差2.8mm。
- 真实闭爪阻断：0mm/1Nm命令通过adapter和驱动调用GripperCtrl，当前steady code仍0x03；7845.82开始闭爪，7850.826等待5秒后反馈仍46.2mm→46.2mm，FAULT_GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED。没有抬升/释放/自动回位/失能。脚本实测退出1，收尾无控制栈残留。CAN到12:52仍增长至1384928，TX18567、errors/dropped0，USB bulk IN/OUT成功完成；本轮**没有复发断联**，不能声称历史冻结根因已解决。
- 下一步只验证新的官方实现差异，而不重复相同80帧闭爪：当前官方V2 demo https://raw.githubusercontent.com/agilexrobotics/piper_sdk/master/piper_sdk/demo/V2/piper_ctrl_gripper.py 在一次0x02→0x01后steady使用0x01；现有joint_callback每帧0x03=使能并清错。0x03在官方接口合法，不据此预断它必然导致无位移；可按同一适配器链改steady01作一次有真实反馈的验证。未知机械完全闭合基准仍禁止0xAE，不刷写/主从/ResetPiper。总目标仍未完成。

### 2026-10-10 12:38–12:41：按授权实际运行新版默认脚本，反馈门在[1/7]拒绝运动

- 起始HEAD `2a1de70`，用户明确要求“开始实机验证”。读取规范Git状态和最新进度/决策，保留既有供应商/Astra未提交修改。实际宿主权限检查`sudo -n true`返回0；运行/规范一键脚本SHA-256均`e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`，不是旧脚本或备用YAML。
- 12:38:50真实主机`ip -details -statistics link show can0; sleep 3; ip -statistics link show can0`：索引7、UP/LOWER_UP、ERROR-ACTIVE、1Mbps/.750、qlen1000；RX946260→946260、TX21139、errors/dropped0。无PiPER/适配器/视觉/相机/MoveIt控制进程残留。没有把接口UP当作新鲜反馈，也没有将沙箱网络隔离误认为实体断联。
- 本轮最小可验证动作：直接执行`set -o pipefail; BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh 2>&1 | tee /tmp/piper_real_verification_20261010_1241.log`。该证据文件名仅为标签，实际运行时间约12:39。脚本自带磁盘维护完成，根分区33%/可用51601MB，清理前后使用率不变；系统日志vacuum释放0B，未删除源码/依赖/Git，不能把本次阻断解释成磁盘满。
- 实际输出到`[1/7]`后，既有5秒RX门给出“can0已正确配置但RX未增长；保持接口不变，不执行down/up”及“PiPER控制器没有CAN反馈”，随即执行保护清理。**没有到[7/7]、没有新的观测到达、CENTER_HOLD/中心小扫、ALIGN或抓取证据**；没有启动驱动、发送使能/运动/闭爪/失能/ResetPiper/标定/固件命令。脚本错误路径`fail`定义退出1；外层工具会话收尾状态尚未返回时不把推断退出码冒充工具实测。
- 12:39:43退出输出后的实际RX仍946260、TX21139，无上述控制进程。内核echo异常计数0，已处理marker为1，不存在“新增未处理echo错误”的一次恢复条件；无12:12之后的新USB断开/枚举。12:35:24仅新增`gs_usb_timestamp_work ... hogged CPU >10000us`警告，它本身不证明RX冻结原因。未重复历史无效guest USB reset/xHCI重建/重刷/主从/普通限位检查。
- 本轮回答“是否推进观测”：已实际运行新版默认启动并验证启动拒绝路径，但未推进实体观测或抓取，因为未取得任何新鲜关节反馈。中心搜索离线通过与当前实体可执行性必须分开。当前确切阻断仍是接收流停滞，尚不能凭计数区分VMware透传、USB-CAN内部状态或机械臂控制器端；不武断归为硬件故障或视觉算法问题。
- 12:40工具会话完成返回**实测退出码1**，与启动反馈门拒绝一致；本轮两份文档的限定范围`git diff HEAD^ HEAD --check -- docs/PIper_PROGRESS.md docs/PIper_DECISIONS.md`返回0。全工作树diff检查曾报告既有供应商CRLF/尾空格，不属于本轮修改，未修整或提交它们。
- 下一步需要恢复真实反馈链（历史有效动作是宿主VMware把USB-CAN断开后重新连接到此虚拟机，代理当前仅有guest入口，不能代操作宿主）。恢复后的首条命令仍`ip -statistics link show can0`并做短差分；若新枚举接口DOWN且sudo可用，仅固定1Mbps/.75/qlen1000/up一次；RX持续增长后直接运行上面同一默认命令，不等待按键、不重复已完成基线，验证CENTER_HOLD→目标立即ALIGN或中心小扫→实测回中心→双侧full，再核验落点、真实闭爪、抬升、释放及先回位后失能。连续实机授权有效，但总目标未完成。

### 2026-10-10 12:16–12:34：实施中心优先搜索与分段边界修复，完成隔离控制器回放

- 起始HEAD`74991a1`，用户确认修改搜索顺序。保留唯一实体`cube_task_real.yaml`、既有MoveIt搜索分段与`piper_jog_adapter`，不另建运动程序、不混备用YAML、不扩大关节搜索范围、不改颜色/深度授权、不启用腕部Octomap。开始/收尾真实主机2秒RX均946260→946260，TX21139、errors/dropped0；本轮无新鲜实体反馈，因此**未再次实机到观测位或发送实体运动**，没有复位/失能/刷固件/主从/未知夹爪零点写入。
- 实体YAML启用`initial_search_center_first=true`、`initial_search_hold_s=2.0`。观测完成后先保持六轴当前位置、给RGB-D稳定识别窗口；有效目标判断始终优先，可立即取消搜索转ALIGN，不强制先扫。仍无有效目标才访问中心附近J1±0.08rad、J5±0.12rad的8个小范围点（必要时按原0.20rad分段）；然后`CENTER_RETURN`回到同一实测中心，确认到达后才`CENTER_RETURN_CONFIRMED_EXPAND_EXISTING_FULL_SEARCH`。搜索大范围仍J1[-1.35,1.35]/J5[-0.60,0.95]，左右只是现场视角，不擅自等同关节正负方向。新的中心阶段不受旧local 5秒超时提前扩扫；规划失败只做原有次数内重试，未到达/未回中心不能靠超时假称完成，停止于明确CENTER_SEARCH故障。
- 分段修复：先限制desired目标到本次搜索区域，再按最大步长接近；full阶段的J5目标设为真实上下边界，不再current±0.20越界折返。边界覆盖按实测到达/跨过方向判定，不因随机GOAL误差停在边界外反复等待。新增每段target_J1/J5及实测REACHED日志，不把trajectory accepted当成双侧覆盖。
- 第一次隔离回放真实控制器发现已有额外缺口：普通RRT使用0.01rad goal tolerance，首个中心规划终点J1≈0.08838/J5≈0.29120，非搜索轴也变动，回放失败`Non-search axis moved`。据此在**规划请求**增加J2/J3/J4/J6保持路径约束±0.001rad，搜索goal tolerance收紧到min(反馈到达容差,0.0001rad)，以每次搜索初始化实测位置作为非搜索轴锚点；规划后清除约束，不篡改已规划轨迹来绕过碰撞检查。这些是模型规划容差，不宣称实体具有0.0001rad跟踪精度；实际反馈到达门仍0.01rad。
- 一键脚本新增抓取尚未启动前的visual FAULT门，直接报告控制器reason并保护退出，避免中心搜索失败但grasp还在IDLE时空等900秒；支持FAULT字符串的单双引号。正常释放路径仍先回位后失能，新增9项启动脚本测试包含故障不回位/不失能、成功先回位再失能。
- 构建/同步：`source /opt/ros/humble/setup.bash; source /home/johnwick/piper_ros/install/setup.bash; PYTHONNOUSERSITE=1 colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release`最终两包返回0。规范/运行控制器SHA`5e89ddeee132568e181f2ec681abc78482720de24a66d2746448c2e0ec65c0b5`；已安装/规范YAML SHA`3528397f3c0f6b0e047b9227cb642de7aa46a7f9a2ed833403d47310090fd17a`；运行/规范一键脚本SHA`e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`，安装二进制含CENTER_*日志。
- 验证：`bash -n`与指定/tmp缓存的py_compile返回0；CTest5套全部通过（5项抓取几何、8项中心搜索gtest，7项适配器/9项抓取回放/9项脚本pytest），`colcon test-result --test-result-base build/brain_robot_pick_place --verbose`汇总41 tests、0 errors/failures/skipped（含结果包装，实际38项）。无实体测试不会证明紫色方块检测/物理执行成功。
- 新增可复现`test/replay_center_search{.py,.launch.py}`，复用已有`review_surface_grasp_plan.launch.py`的MoveIt/URDF/实体限位；硬要求ROS_DOMAIN_ID=78、allow_trajectory_execution=false，域内禁止PiPER/适配器/Servo/抓取执行器。仅发布合成/joint_states、合成target_valid/pixel_error并捕获控制器轨迹；没有joint_commands发布者、CAN或真实相机。假反馈瞬时跟踪端点，**不模拟真实动力学/电机跟踪/实体桌面碰撞**。完整回放通过：中心小扫→实测回中心→原full扫描，J1端点约-1.349951到+1.350011rad、J5约0.950rad，无旧1.10目标；中心合成有效目标在任何非零扫动前转TARGET_ACQUIRED；反馈冻结转JOINT_STATE_TIMEOUT而不进入full。
- 第二次回放先通过双侧覆盖/目标优先，但过期反馈场景止于CENTER_SEARCH_NOT_REACHED而非预期0.5秒超时；原因是测试launch的后置wildcard覆盖没有替换node-specific YAML的25秒值。已修正**测试配置合并**并回读参数`0.5,true,2.0`，生产25秒值未更改；最终三个场景全部通过、回放返回0。最终证据`/tmp/piper_center_search_replay_verified.log`含三个PASS和ALL_PASS，旧部分结果保留`/tmp/piper_center_search_replay.log`；ROS日志`/home/johnwick/.ros/log/2026-10-10-12-31-23-917776-johnwick-virtual-machine-143194/`。三次隔离MoveIt在SIGINT析构时仍有既有2.5.9退出-11，控制器/robot_state_publisher正常退出，收尾无相关进程残留；不把它误写为规划失败或实体故障。
- 下一步首条命令在真实主机`ip -statistics link show can0`并作短RX差分，只有恢复持续反馈后直接运行默认`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`，核对CENTER_HOLD→目标立即ALIGN或CENTER_LOCAL_SCAN→CENTER_RETURN→full实际轨迹；再验证已部署表面夹入/落点/夹爪闭合。无需重复已完成基线或另等按键授权。总目标尚未完成，CAN冻结、实体检测及夹爪46.2mm响应仍独立待验证。

### 2026-10-10：启动修复通过，复发RX停滞与单侧搜索逻辑核对

- 在`50c33fe`修正版同一默认自动命令下，`1791605387.558474302`进入PREPARE，12点40.4秒轨迹被接受；`1791605427.564144755`实际`SEARCH(OBSERVE_POSE_REACHED)`。启动确认窗口修复已通过实体运行，不再把已接受轨迹误判为服务失败。随后适配器连续接受41/42点FULL_SEARCH段；未进入ALIGN/GRASP_READY，故本轮没有新表面下降、闭爪、抬升或释放的实机证据。
- 新RX事件：`12:12:01`守护报告`CAN_RX_STALLED_3S`，控制器日志`1791605522.771074208 FAULT(EOG_OR_EXTERNAL_EMERGENCY_STOP)`，这是脚本守护发布的emergency_stop而非可断言用户按了急停。脚本退出143，停止本轮输出/进程，不发送DisableArm/ResetPiper。退出后的2秒计数RX946260→946260、TX21139不变，errors/dropped0，无实体控制/视觉/相机节点残留。内核无同时间的新USB断开或echo异常；较早12:05:54存在uvcvideo resubmit URB(-1)，不据此断言当前冻结根因。继续不重复已无效guest reset/USB重建。
- 相机事实：RGB明显泛白、均值约209..226。安装`v4l-utils 1.22.1-2build1`（两包约2.3MB，返回0），仅读取控制而不启动第二个采集源：brightness=64（最大、默认0），gain=100（最大、默认0），auto_exposure=3，exposure_time_absolute=1000。一次恢复brightness=0/gain=0成功，保留自动曝光/白平衡，未更改HSV/深度门；后续RGB均值约99..105、画面恢复细节，但该帧未见有效方块。曝光时间保持1000，不假称已自动回157。参考Linux官方控制文档 https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-camera.html 。这是相机状态修复，不是CAN恢复证据，当前脚本尚无持久化相机控制初始化。
- 用户指出“观测时看到方块，却向右且没有先在中间小幅搜索”。源码证实`PrepareWorker()`观测完成直接`InitializeSearchLocked(false,...)`，选择全范围而非local；`search_bounds_relative_to_start=false`、J1[-1.35,1.35]、J5[-0.60,0.95]，full初始化J1方向固定-1、DESCEND/J5正方向。本次日志首阶段`PHASE=SEARCH_DOWN J1=NEGATIVE J5=DOWN`。不能把J1负方向未经现场定义说成实体左/右；用户现场对应的是右侧。local ±0.08/±0.12rad参数存在但不在初始流程使用，故当前实现确实不符合用户“中心→小范围→左右扩展”的顺序。
- “看得见”与本次软件检测分别记录：检测器整个本次日志只有LOST，75帧窗口target/depth_valid=false，所以HandleSearchLocked的目标有效转ALIGN门未触发；不否定用户看见方块，也不以此合理化立刻大扫。过曝和深度配准零区均可削弱检测，但不能仅用LOST区分具体颜色/形状/深度拒绝原因。
- 另定位真实代码缺口：`StepFullSearchLocked()`vertical目标用current±0.20rad而不截在搜索上下界，`RequestPlannedSearchLocked()`只限制每步差值、没限制区域；`Reached()`要求绝对误差≤0.01。例如J5=0.90→1.10会越过上界0.95，之后回到0.90附近，可能无法切换BOTTOM_SCAN。本次实测J5=1.076888/1.074899，已超搜索0.95（仍在适配器轴范围内），日志5466.689/5485.739/5500.940/5520.139多次`SEARCH_SEGMENT_TIMEOUT_CONTINUE`翻转J1方向。因此连续接受轨迹不能证明已完成正负两侧覆盖；现有样本J1=-1.156363及末值-0.754610，不声称已扫到正侧。
- 当前动作范围：本轮问题按用户最新请求作代码/日志解释，尚未更改搜索策略或再次执行运动。下一步实现中心静止优先检测、继而中心小范围，再回中心展开左右；给搜索末步正确夹到边界并记录方向/目标/实测覆盖，不盲增范围、不降低目标门。实机前先解决本次RX冻结；单侧搜索代码缺口与CAN冻结分别存在，不能相互掩盖。总目标仍未完成。

### 2026-10-10 12:05–12:12：新USB枚举后的CAN恢复与启动确认超时修复

- 起始HEAD `34fbd80`，针对当前反馈停滞检查真实主机（提升执行权限避免沙箱设备隔离误判）。内核记录12:02:08/17断开、12:02:14/31新枚举USB-CAN（device 17/18），can0索引7、DOWN/STOPPED、计数0；这是新的外部枚举事实，不推断是谁操作。`sudo -n true`成功。
- 仅执行`sudo -n ip link set can0 type can bitrate 1000000 sample-point 0.75`、`txqueuelen 1000`、`up`，均成功；5秒RX 41→11661，251..256和3A7持续收到，ERROR-ACTIVE且错误/丢弃0。根分区33%、可用51GB。未重复guest USB reset/xHCI重建/固件/主从/ResetPiper实验。
- 运行`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`，通过[7/7]；15秒收到RGB76、深度412、检测输出75、关节2665，末六轴[-0.127480752,0.029968792,-0.038725680,0.522046588,0.438960816,-0.543572484]rad、夹爪46.2mm。原始RGB能看见方块但局部过曝；当时target/depth_valid=false，不据此放宽门。
- 新阻断是启动请求确认竞态：`1791605194.856623556`控制器PREPARE(START_AUTHORIZED)，14点49.1s轨迹被适配器接受；约100ms后服务日志`failed to send response ... client will not receive response`，脚本8秒CLI外层已结束并误判启动失败，返回1/保护清理；本次没有完成观测/搜索/抓取。退出后无本轮实体节点残留，RX228890继续增长，不是CAN再次冻结。
- 最小修复：唯一脚本start服务确认deadline 8→30秒，覆盖CLI发现/启动负载；不重发start、不以旧topic当确认，不改变关节反馈新鲜度、运动完成等待或故障门。同步运行脚本，SHA均`cb2c34fd1c453caa1b1678bff2e80ba1e57533a33290d2f07563f831779eefb4`。额外修复已有日志守护的证据损坏：start_group先清空后用O_APPEND打开；否则守护原inode截断时，旧writer偏移会在后续CAN日志中生成大段NUL稀疏空洞。该日志修复不宣称能恢复CAN。
- `bash -n`返回0；新增不连接ROS/CAN的4项pytest全部通过，验证30秒只发一次请求、服务拒绝/轨迹失败不能当成功、截断后append不产生NUL。命令`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_startup_script.py`。下一步直接修正版默认自动运行，核对观测后表面夹入/落点及真实闭爪；持续授权不反复询问。未失能/复位/标定零点，最终目标仍未完成。

### 2026-10-10：修正表面抓取的提前闭爪逻辑，完成离线落点验证

- 起始提交 `fe90ad8`，用户确认修正提前闭爪/落点。观测与SEARCH已有本日实机证据，本轮不重新运动；优先修改现有`grasp_lift_executor`与唯一生效`cube_task_real.yaml`，不新增基础控制程序、不绕过适配器、不改固件/零点/失能策略。
- 明确目标语义：检测器给的是可见表面点，不是体积中心。实体配置启用`top_down_surface_grasp_enabled=true`；预抓取保留表面外24mm，最终沿同一工具轴夹入`min(较小实测面尺寸×0.4,12mm)`，取消原来的最终+18mm间隙。对记录的32×38mm方块，插入12mm，末段从6mm改为36mm。此为桌面方块的**尺寸启发式**，不是官方给定夹持深度，也未证明独立实测TCP/相机外参正确；不自动推断完整体积中心。
- 新增真机`EnsureRealTopDownLanding()`：从新鲜实测六轴状态做link6 FK，计算当前/目标指尖与轴向、横向、姿态误差并输出`GRASP_LANDING`。允许位置≤8mm/姿态≤0.12rad进入闭爪；小偏差只允许一次≤20mm、保持同一目标tilt/yaw的笛卡尔修正。超过范围、反馈过期、修正失败或修正后仍不达标，停止在`GRASP_LANDING_UNCONFIRMED_NO_CLOSE`，不发闭爪。该FK核验不是独立外部测量，无法单独识别错误实体外参，日志明确标识`NOT_EXTERNAL_TCP_CALIBRATION`。
- 复用主线PTP预抓取、笛卡尔末段、六轴限位、适配器和静态base_link目标；没有恢复反复像素ALIGN，也没有根据J1/J5盲目扩大搜索。新增纯C++几何/落点决策函数及5项gtest，覆盖旧+18mm仍停在表面外、新夹入跨越表面、尺寸上限、远处不闭爪和仅一次纠偏。Python回归共16项通过。
- 构建：`cd /home/johnwick/piper_ws; source /opt/ros/humble/setup.bash; source /home/johnwick/piper_ros/install/setup.bash; PYTHONNOUSERSITE=1 colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release` 返回0（两包）；更新后再增量构建返回0。CTest三组全部通过，`colcon test-result --test-result-base build/brain_robot_pick_place --verbose` 返回0，汇总24 tests、0 errors/failures/skipped（包含CTest包装，实际5项gtest+16项pytest）。一次colcon test外层在CTest完成后收尾等待，后续中断已结束；直接CTest和结果文件用于验收。规范/运行executor SHA一致`6d268d76cfc1e14e735d6bb25b03e298108c8ceb954ae9bd81d12e11321bf5e1`，生效YAML SHA一致`674200e3b435e9f1da8d48284b171f2b748580f87dcadaeeed9660f150752e50`，运行二进制含新增落点/夹入日志。
- 无运动规划复核复用既有`/tmp/piper_plan_review.launch.py`与`/tmp/piper_review_plan.py`，已保存可复现版本到规范`brain_robot_pick_place/test/review_surface_grasp_plan{.py,.launch.py}`。隔离域`ROS_DOMAIN_ID=78`，`allow_trajectory_execution=false`，无PiPER/适配器/抓取执行器/实体命令发布者。记录目标surface=(0.260,-0.092,0.136)m、面宽假设0.032m；从本次记录六轴姿态和标准观测姿态分别得到16/82点PTP与9点末段，`fraction=1.000000`、限位/连续性通过，tilt=0.35/yaw=0未变。新终点J2=1.313876rad；模型指尖=(0.264115,-0.092,0.124728)m与预期一致，FK误差约3.4e-9m仅为模型计算一致性，不是实体毫米级精度证明，也不代表真实桌面碰撞/抓住已验证。
- 隔离move_group在全部规划成功后SIGINT析构退出-11（MoveIt 2.5.9关闭栈），robot_state_publisher正常退出；没有残留本轮离线规划/测试或实体输出进程。未把关闭异常当作规划失败或硬件故障。一次py_compile在只读规范目录写缓存失败，改`PYTHONPYCACHEPREFIX=/tmp/piper_surface_pycache`后验证；不改源码权限、不提交缓存。
- 本轮实机条件：针对上次RX停滞的最小2秒计数复核仍为RX199339361/TX423161、errors/dropped0；无新鲜反馈，不执行一键运动或重复80帧闭爪。未发送Enable/Disable/Reset/MasterSlave/0xAE，保持此前使能状态。目标未完成，实体TCP/相机外参、夹持落点以及夹爪真实响应仍未验证。
- 下一步：第一条针对实际故障命令`ip -statistics link show can0`并作短间隔RX差分，若已恢复，直接复用修正版默认一键脚本，核对`SURFACE_GRASP -> TOP_DOWN_DESCENT -> GRASP_LANDING -> CLOSING_GRIPPER`的真实落点/夹爪位移；若仍冻结，不再重复搜索/闭爪/既有无效USB与固件实验。离线复现：source三工作区、`ROS_DOMAIN_ID=78 ros2 launch /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_surface_grasp_plan.launch.py`；同域运行对应`.py`，`PIPER_REVIEW_START=observe`选择观测起点。该域只规划，无实体执行。

### 2026-10-10：恢复灯光后的实机抓取尝试与黑色配准区域核对

- 用户最新实体观察为“夹爪离方块仍很远即闭爪”，不能用规划轨迹完成反驳。核对发现闭爪触发只是`ExecuteArmTrajectory()`等待轨迹时间结束且六轴角度在容差内；真机没有直接验证物体已进入两指夹持区。更具体的几何缺口：检测器发布的是像素中心处深度表面点，不是重建后的实体中心；`PopulateTopDownPose()`却直接把它当object_world，并在最终抓取保持tip_offset+0.018m距离，预抓取0.024到抓取0.018只推进6mm。不能把正的表面间隙当成夹持深度，也不能未经实测断定这18mm足以解释用户观察的全部远距离。下一步需核对真实TCP/表面点→夹持中心/进入深度，不能仅增加闭爪命令或放宽反馈。
- 用户说此前实体曾能闭爪，这是用户现场观察，应保留而不以“没有历史日志”否定。当前日志只能证明本次0mm命令进入驱动且3A7反馈一直46.2mm，尚不能单凭它区分实体未动、机械受阻或反馈/映射异常；不宣称夹爪已损坏或不可能曾闭合。本轮无新实体运动。

- 进一步对应用户“对齐后偏移、没有再调整就停住”的观察：`TopDownPointGraspAndLift()` 执行预抓取和下降后直接调用 `FinishGraspAndLift()`；真机分支读取当前末端姿态，但没有将夹持中心对锁定目标做独立落点核对/修正，就发闭爪。现有 `VerifyGraspContact()` 调用在后面的仿真分支，不能当作真机已验证中心。`static_target_lock=true` 避免追逐相机自运动像素，却也不提供末段TCP纠偏；这是代码缺口，与本次46.2mm闭爪无位移停止分别存在。下一步应优先让已锁定base_link目标与真实夹持中心关联，在预抓取后作一次有界几何核对/必要修正再固定姿态靠近；不要以持续视觉追逐替代，也不声称用户看到的偏移已量化/消除。本轮仅代码和历史日志检查，无新实体运动。

- 后续故障定向只读检查：2秒间隔can0 RX均为199339361，TX423161，errors/dropped均0，证实RX已停止（ERROR-ACTIVE本身不代表反馈持续）。脚本退出仍残留本轮进程组129552/129505/129346/130080/129335/129241；按已核对PID精确发送TERM并确认退出，未发送实体控制/失能。最后可见3A7为`0000B47800094000`（角度46200）。
- 用户追问J1/J6偏移的代码原因：当前检测器只取旋转矩形尺寸用于形状门控，并未发布方块边缘朝向；抓取执行器按固定tilt/yaw候选顺序选首个完整可行规划。本次选tilt=0.350rad、yaw=0rad，锁定对象base_link=(0.260,-0.092,0.136)m；预抓取link6原点=(0.205,-0.092,0.286)m，下降终点=(0.207,-0.092,0.280)m。J1/J6变化是六轴IK/PTP姿态变换的结果，**不是识别方块边后主动抓角**。默认tip_offset=0.1358m用于原点到指尖补偿；本次日志并不能独立证明实体夹持中心已经正确落在目标中心，不能用“IK可行”掩盖用户观察的偏移。后续应核对TCP/相机外参、方块朝向与夹持中心，且最后靠近保留固定姿态直线段；本次无新运动。

- 起始 HEAD `1747932`；先前自动运行通过观测和 SEARCH，但等待抓取超时。纠正本轮口头误判：`RGB_DEPTH_SOFTWARE_ALIGNED` 受 `rgb_alignment_reported_` 控制仅首次打印，`target LOST/DETECTED` 仅状态变化打印；日志只有一条 LOST **不能证明同步器只处理一帧**，不据此修改同步算法或放宽 RGB-D 门控。
- 本次宿主权限执行成功，`sudo -n true` 返回 0；can0 为 ERROR-ACTIVE/1Mbps/0.750，已有链路直接复用，无重载。命令 `BRAIN_ROBOT_AUTO_START=0 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`，在 `[7/7]` 后先读取 15 秒数据，再由代理向同一脚本输入 `1`（不要求用户按键）。
- 无运动窗口实际收到 RGB 76、depth 430、debug/target_valid/depth_valid 各74条、关节反馈2945条；末值 target_valid/depth_valid=true、`DEPTH_GRASP_ALLOWED`。原始 RGB 图可见桌上紫色方块；配准图检测深度约0.356m、尺寸0.032×0.038m。RGB-D 同步持续正常，灯光已恢复。
- 六轴初始反馈 `[0.128230844,-0.005163424,0,-0.012071248,0.295483916,-0.046784808] rad`；观测配置 `[0,0.98,-0.75,0,0.30,0] rad`。适配器接受14点/49.1秒观测轨迹，`1791601390.435686679` 实际进入 `SEARCH (OBSERVE_POSE_REACHED)`，随后持续接受41/42点搜索轨迹；`1791601433.470934668` ALIGN，短暂丢失后重获，`1791601440.470644986` GRASP_READY。
- 本次真实抓取执行器规划并发送68点预抓取、5点下降；闭爪0mm/1N.m经适配器与驱动持续发送。`1791601458.802633079` 再次停止于 `GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED`：before=current=0.046200m，target=0m，无≥1mm闭合位移。未抬升/释放，不能声称抓取完成；不继续重复已证伪的延长闭爪窗口或未知基准0xAE。
- 用户指出配准窗口的大块黑区而原始彩色无黑区。代码 `software_register_color_to_depth()` 先 `cv::Mat::zeros`，对无效/超量程深度、非正投影Z、超出彩色FOV的映射直接continue，故黑色是**未映射像素**，不是实体黑影/碰撞障碍/夹爪的充分证据。HSV/矩形检测在这张配准图上运行，缺深度确实可能切碎目标轮廓；本次仍通过GRASP_READY，黑区不是本次闭爪失败原因。未用补色或虚构深度伪造目标。
- `11:04:39` 守护日志新报 `CAN_RX_STALLED_3S`，驱动此前提示feedback lost；脚本返回1并清理本轮节点，未发送DisableArm/ResetPiper/MasterSlaveConfig。当前新出现的反馈中断与较早闭爪无位移分别记录，不倒置因果。
- 证据：`/home/johnwick/brain_robot_logs/{visual_stack,piper_driver,cube_detector,can_health}.log`；原始/配准图 `/tmp/piper_current_{rgb,debug}.png` 为临时诊断产物，不提交。下一步只针对新反馈中断取最小实际计数；恢复后优先取得夹爪真实响应/实体基准证据，不再次重复整段搜索或80帧闭爪实验。黑区的进一步改进应把原始RGB外观与有效深度明确区分，不把无效像素误当环境障碍。

### 2026-10-10：灯光外部阻断隔离与夹爪反馈只读复核

- 用户确认现场当前无灯光；本轮将 RGB 紫色目标识别视为外部输入阻断，不再启动视觉搜索或用黑色画面反复调整检测参数。未把“无目标”误写成机械臂或碰撞逻辑故障。
- 清理并确认没有残留 Astra、`visual_search_controller`、MoveIt、适配器或 PiPER 进程后，启动唯一 `piper_single_ctrl` 的 `auto_enable=false` 接收实例；随后只调用一次已有 `/enable_srv true` 以读取夹爪驱动状态，未发送关节轨迹、`ResetPiper`、`MasterSlaveConfig` 或 `0xAE`。
- 通过 ROS `/joint_states_feedback` 读到六轴反馈新鲜、夹爪 `0.045900 m`；用与 S-V1.9-1 运行驱动相同的 `0x3A0..0x3A7 -> 0x2A1..0x2A8` 只读映射复核官方 SDK，得到夹爪角度 `45900`、力矩 `0`、状态码 `0x40`、反馈约 `200 Hz`。`0x40` 表示夹爪驱动使能且无错误位，但尚未归零；它不是 CAN/RX 断联证据。
- 最近一次实际日志同时记录适配器接受 `0.000000 m` 闭爪目标、驱动连续调用 `GripperCtrl(angle=0, effort=1000, code=0x03, set_zero=0x00)`，但反馈仍为 `0.045900 m`。因此“命令未到达驱动”已排除；当前夹爪阻断是实体角度不响应/闭合基准未确认，不能用静态反馈放宽抓取门。
- 当前保持驱动使能和实体当前位置，不自动失能；下一次有灯光后只需从同一干净栈复跑视觉，夹爪仍必须以真实角度变化或明确接触位移通过 `GRIPPER_CLOSE_FEEDBACK_CONFIRMED`，继续禁止未知位置执行 `0xAE`。
- 收尾检查曾发现两组相同的接收实例，已按 PID 只终止较早的一组；最终仅保留一组 `piper_single_ctrl`，无适配器、视觉或 MoveIt 残留。

### 2026-10-10：自动搜索复核与夹爪“曾经闭合”说法的证据边界

- 实际运行 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh` 通过 `[7/7]`、当前姿态到观测姿态、`OBSERVE_POSE_REACHED -> SEARCH`；搜索阶段持续接受 41/42 点的 `FULL_SEARCH` 轨迹并多次改变 J1/J5 搜索相位。脚本在其 900 秒抓取等待门超时后按保护路径停止搜索并 disarm 适配器，未调用 `DisableArm`、`ResetPiper` 或抓取命令。
- 深度探针在运行中多次发布 `DEPTH_CUBE_CANDIDATE_VALID stable=1/1`，例如 `base_link=(0.212,-0.215,0.143) m`、尺寸约 `0.022x0.030 m`；但实体默认配置明确 `depth_only_target_enabled=false`，这些候选只作诊断，不会越过紫色/矩形 RGB 目标门。因此本轮没有 `GRASP_READY`，也没有闭爪反馈可供验收。
- 检查 `/home/johnwick/brain_robot_logs/cube_detector.log`：检测器启动后只报告一次 `PURPLE_CUBE target LOST`。独立保存的真实 `/dev/video0` RGB 帧为 `320x240`，BGR 均值约 `(32.1,32.8,32.3)`、像素范围约 `14..71`，画面接近全黑；`/dev/video1` 明确不是 capture 节点。Astra 日志同时显示 OpenNI 彩色流未启用。由此本轮的视觉阻断是 RGB 输入未提供可分割的紫色场景，不是夹爪碰撞或搜索轨迹未执行；未凭黑图修改镜像参数。
- 夹爪实际反馈仍为 `0.045900 m`（45.9 mm）、状态字 `0x40`（驱动使能、未标记归零），用户最新确认“未完全闭合”。历史记录中没有 `GRIPPER_CLOSE_FEEDBACK_CONFIRMED`；所谓“之前能闭合”只对应早期适配器/SDK 调用或驱动曾崩溃前后的命令路径，并无实体角度从 45.9 mm 到 0 mm 的反馈证据。当前不能写入 `0xAE`，也不能把未发生的抓取动作解释成夹爪曾经闭合。
- 本轮静态相机采样进程已停止；保留以上日志和数值作为下一次最小动作的基线。下一步先修复/确认 RGB 视频数据面（不启动运动），再用同一默认 RGB-D 门控复跑；夹爪只在真正到达闭爪阶段后重新核对反馈，不再重复延长闭爪帧或写未知零点。

### 2026-10-09：第二次实体完整链路到闭爪门，准备延长官方命令保持

### 2026-10-09：80帧闭爪保持复核仍无位移

- 提交6c6c726后的第三次完整默认运行再次通过[7/7]、OBSERVE_POSE_REACHED、SEARCH、ALIGN、GRASP_READY、63点预抓取和4点下降；张爪45000通过。适配器随后连续发送80个约20ms周期的0mm/1N.m/0x03闭爪帧（约1.6秒），驱动日志记录连续`Calling GripperCtrl`。
- 抓取执行器仍报告`FAULT_GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED`：before/current均0.045900m，target=0，未发生≥1mm接触位移；因此没有抬升、释放、回位或失能。异常清理保持使能。
- 被动全CAN日志收到完整反馈族（3A0..3A7约21318帧、251..256约10659帧）且错误/丢帧为0；3A7角度仍45900、状态0x40。SocketCAN设备不回显TX，日志没有159不能否定SDK发送；驱动无SendCanMessage错误，TX总计继续增加。延长保持没有改变反馈，重复洪泛停止。
- 结论：视觉/轨迹/适配器门已实机通过，当前唯一阻断是夹爪执行机构未对0mm命令产生反馈位移，且用户确认升级后未做或不确定闭合零点标定。官方0xAE只把当前位置设为零点，不能在未知机械闭合位置自动调用；需要现场确认/校准实体夹爪基准或检查夹爪驱动/线缆。目标保持未完成。
- 异常收尾后未调用DisableArm；已恢复PID78903的`auto_enable=false`仅反馈驱动。当前新鲜反馈Q=[-0.268184056,1.466988068,-1.148198968,0.107123604,1.001320488,-0.308636692]rad、夹爪0.0459m、六轴速度0；can0 RX持续、错误/丢帧0。视觉/运动节点已退出，实体保持当前抓取位并等待新的夹爪基准证据。
- 用户随后答复“已确认”，但未说明是“夹爪已完全闭合”“已完成官方零点标定”还是仅确认问题；当前新鲜反馈仍为45.9mm、状态0x40，不能把该短答当作零点写入许可。已用假CAN离线单元检查运行时SDK编码：45000/0x03生成`0x159#0000AFC803E80300`，0/0x03生成`0x159#0000000003E80300`，未打开CAN、未发送实体帧；结论为编码层正确，实体响应仍待明确标定状态。
- 用户进一步确认“未完全闭合”，所以不执行0xAE。依据官方V2夹爪示例先`GripperCtrl(0,1000,0x02,0)`再持续`0x03`，把PiPER驱动的`/enable_srv true`路径改为夹爪一次失能清错、等待100ms、再使能；不ResetPiper、不改六轴零点。规范/运行驱动SHA一致`cb4f53e52f54ef56e155ae8082633118232402ddc53c08f25122c4959244c927`，piper构建成功。下一步同一一键流程验证清错后0mm闭爪是否产生反馈位移。

- 复跑提交d563eeb后，默认脚本再次通过[7/7]、观测、SEARCH、ALIGN、GRASP_READY、63点预抓取和4点下降；张爪45000通过。闭爪0仍反馈before=current=0.045900m，停止于`FAULT_GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED`，未抬升、释放或失能。机械臂异常清理保持使能。
- 新的被动全CAN日志统计到3A0..3A7、251..256及其他反馈帧，但没有可见159回环帧；驱动日志明确调用0x03/angle0五次。由于USB-CAN当前不回显TX，缺少159不能单独证明没发送；SDK `SendCanMessage`无错误日志，需结合TX计数或驱动发送状态判断。3A7仍为角度45900、状态40。
- 依据官方SDK `piper_ctrl_gripper.py`持续每5ms发送约1.5秒的示例，适配器夹爪帧从5（100ms）扩为80（约1.6s），上限由1..10扩为1..100；规范/运行源SHA分别`2f9723809a9418873275de434454abaa9e077087d5cc58c8fcd5aa99af9ae80a`，launch源SHA`7fafad5125d7b165e0579698dbe0ad73c929f5557144cd35db9249fe65056b14`。构建成功，17 tests、0 errors/failures/skipped。
- 下一步用同一脚本复核80帧保持是否让3A7角度变化；若仍完全不变，证据将指向夹爪零点/实体驱动或控制回路，而不是视觉或预抓取路径。未知闭合基准仍禁止写0xAE。

## 2026-09-23：重新拾起任务

- 规范仓库：`/mnt/hgfs/ub`；恢复前 HEAD：`a195b6d`（`docs: define durable Codex handoff workflow`）。
- 已按恢复协议读取 `git status`、最近 30 条提交、reflog、HEAD 摘要和 `CODEX_HANDOFF.md`。`docs/PIper_PROGRESS.md` 与 `docs/PIper_DECISIONS.md` 原先不存在。
- 现有工作树有大量用户已有修改及未跟踪 Debian 包；本轮不覆盖、不清理、不提交这些内容。

### 现场检查

- 实际运行路径：`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs`。
- 发现上一轮残留的 `cube_visual_search` 子进程（`pointcloud_tf_gate`、`active_scan_supervisor` 等），但没有 `piper_single_ctrl`；`/joint_states` 发布者为 0，符合交接文件记录的视觉适配器 `joint state timeout` 链路。
- 已停止该残留视觉进程组，避免第二套 MoveIt/Servo/视觉控制栈竞争。
- 运行时 SDK 为 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`；`C_PiperInterface_V2` 的 `MotionCtrl_2`/`JointCtrl` 最终调用 `C_STD_CAN.SendCanMessage`。本轮未在无高速反馈时发送关节目标。
- 重新启动 Astra 后，RGB/深度实际帧可收到，现场 `ros2 topic hz` 测得约 15–30 Hz（受 DDS/USB 负载波动）；深度帧时间戳为当前 ROS 时间。点云频率需要在唯一 PiPER 驱动和 TF 完整后重新测量，不能用残留实例的数据验收。
- 运行时 `can0` 显示 1 Mbps、sample-point 0.750、`ERROR-ACTIVE`，但探针前后 RX 计数均为 `27105303`，SDK 高速反馈时间戳/Hz 为 0；因此当前没有真实 CAN 反馈，未进行任何运动测试。
- `sudo -n -v` 失败（需要当前用户密码）。试跑 `/home/johnwick/start_brain_robot_cube_real.sh` 在 `[1/7]` 的 CAN 配置阶段停止，原因是无法执行 `sudo ip link set can0 ...`。这是当前硬阻断；还不能把无反馈归因于 SDK、ROS 或视觉代码。
- 已确认此前启动脚本失败清理会停止复用的 Astra；规范仓库脚本尚未应用修复。本轮将把清理改为只停止本轮启动的相机，并在启动前清理遗留 PiPER 驱动/检测器。

### 最小下一步

1. 用户在 Ubuntu 终端执行 `sudo -v`，确认机械臂电源、CANH/CANL、USB-CAN 透传和 Astra USB 占用状态。
2. 重新配置 `can0` 后先验证 RX 持续增长和 `0x251..0x256` 高速反馈，再按 `ConnectPort → 新鲜反馈 → EnableArm(7)/六轴使能 → MotionCtrl_2 → 当前位置+250 (0.25°) 的 J2 JointCtrl` 顺序做受护的小幅测试。
3. 只有 `/joint_states` 持续更新且唯一驱动存在时，才启动 MoveIt/Servo/TF gate；再验收紫色方块搜索、`GRASP_READY` 和抓取。

## 2026-09-23：本轮规范化提交

- 本文件与 `docs/PIper_DECISIONS.md` 首次创建，作为跨账号/重启后的唯一进度来源。
- 代码/测试提交后在此追加 commit、命令、结果和剩余风险；不提交密码、巨大日志、构建产物或临时抓包。

## 2026-09-23 21:20：恢复后复查

- 按固定恢复顺序重新读取规范仓库状态、最近提交、reflog、`CODEX_HANDOFF.md`、本进度文件和决策文件；当前 HEAD 为 `a283d2d`。
- 现场只发现 Astra 启动进程，没有 `piper_single_ctrl`、视觉控制器或 MoveIt 控制栈。
- USB 枚举正常：Geschwister Schneider CAN adapter `1d50:606f`，Astra 彩色/深度设备 `2bc5:0557`、`2bc5:0657`。
- `ip -details link show can0` 显示 `state DOWN`、`can state STOPPED`；RX/TX/error/dropped 全为 0；`candump -n 12 can0` 返回 `Network is down`。
- `sudo -n -v` 仍返回需要密码，因此当前无法由 Codex 重新配置并启动 `can0`。这仍是硬阻断，不是 SDK、ROS、TF 或视觉算法故障证据。
- 未发送任何使能或关节目标。恢复后下一最小动作仍是：先由操作者完成 sudo 认证并将 `can0` 配置为 1 Mbps/sample-point 0.75，确认 `ERROR-ACTIVE` 和 `0x251..0x256` 持续反馈，再检查唯一驱动和 `/joint_states`。

## 2026-09-23 21:34：固定提示词后的无运动证据检查

- 按 `CODEX_TASK_PROMPT.md` 重新执行规范仓库恢复顺序；根目录仍为 `/mnt/hgfs/ub`，本轮开始 HEAD 为 `fab94d2`。用户已有未提交的供应商/相机/安装脚本修改和未跟踪 Debian 包保持不变。
- 运行时脚本 `/home/johnwick/start_brain_robot_cube_real.sh` 的 SHA-256 为 `fe0da5c...ba0eb5`，与规范源 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 的 `da9838...674230` 不同；因此最新的规范脚本尚未安装到实际运行路径，不能把运行时脚本当作本轮 `2e9bee8` 修复已生效的证据。
- USB-CAN、`gs_usb`/`can_dev`、`can0` 均正常：`ERROR-ACTIVE`、1 Mbps、sample-point 0.750、无 CAN 错误；5 秒 RX 增量 `15215`，`candump` 读取到 `0x251..0x253` 与 `0x3A0..0x3A7`。SDK `C_PiperInterface_V2` 导入路径为 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk/interface/piper_interface_v2.py`。
- 无运动 SDK 检查：高速反馈 timestamp `1790170155.000394`、`200.0 Hz`，当前位置 `[0, -1, -10, -29, 290, 0]`；六轴使能均为 `False`，`GetArmJointMsgs()` 仍为 timestamp/Hz 0，符合既有缓存限制。
- 临时启动唯一的 `piper_single_ctrl`（`auto_enable:=false`，无 `/joint_commands` 发布者）后，`/joint_states` 只有一个发布者，实测约 `190--205 Hz`，消息时间戳更新；随后停止该未使能诊断进程，CAN 仍保持 `ERROR-ACTIVE` 且 RX 增长。没有调用 `/enable_srv`，没有发送 `MotionCtrl_2` 或 `JointCtrl`。
- 停止驱动时出现已知 rclpy 清理异常：publisher context invalid，随后 `rcl_shutdown already called`；这是退出路径缺陷，未伴随 CAN 反馈丢失。下一轮启动前当前没有 PiPER、MoveIt、Servo 或视觉控制栈残留，只有 Astra。
- `sudo -n -v` 仍要求密码，但当前接口已正确启动，因此本轮不把它当作 CAN 硬阻断；若需要重新配置 CAN，仍必须先由操作者完成 `sudo -v`。

### 本轮结论与下一步

- CAN、SDK 高速反馈和 ROS `/joint_states` 三条基础链路均已验证；真机运动安全闸门尚未通过，因为本轮用户没有明确允许运动，且尚未重新查询并记录实际关节限位/速度/加速度。
- 下一步先把规范脚本通过 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 安装到 `/home/johnwick`（先保留并比较运行时差异），重新验证脚本哈希；随后在用户明确允许运动后，按固定安全清单查询限位、确认六轴使能和当前目标，执行仅 J2 `+250`（0.25°）的小幅反馈测试。

## 2026-09-23：修正 sudo PTY 误阻断规则

- 用户在自己的 Ubuntu 终端执行 `sudo -v` 返回 0，但 Codex 使用的另一个 PTY 执行 `sudo -n -v` 仍需密码；这是 sudo 时间戳/终端会话边界，不足以证明系统权限或 CAN 故障。
- 当前 CAN 已验证 `ERROR-ACTIVE`、RX 持续增长和 0x251～0x256 高速反馈，因此固定提示词已改为：只有确实需要特权的接口重配置、驱动重载或系统服务安装时，才把 sudo 认证当作阻断；CAN 健康时不得仅因 `sudo -n -v` 非零阻断只读诊断、构建和进度工作。
- 若需要特权操作，用户必须在 Codex 实际使用的同一个远程终端完成一次 `sudo -v`；本轮未修改 CAN、PiPER 或运动逻辑，未发送运动命令。

## 2026-09-23：固定启动消息与持久文档职责

- 已在 `CODEX_TASK_PROMPT.md` 明确：聊天框只保留稳定的启动入口，通用规则、参数、历史事实、动态进度和决策均以规范仓库文档为准。
- 后续规则变化只修改对应文档并提交 Git，不要求每次接力重新编写完整聊天提示词；新代理必须以仓库最新文件覆盖聊天中的旧文本。

## 2026-09-23：磁盘空间巡检自动化

- 已在 Codex 中创建并启用线程心跳巡检 `PiPER 磁盘空间巡检`，现调整为每 15 分钟检查一次。
- 巡检只在根分区使用率达到 85% 或出现明确磁盘空间不足错误时执行 `/home/johnwick/clean_disk_space.sh`；空间正常时不执行清理，不修改 CAN、PiPER、ROS 或启动脚本。
- 巡检执行前后必须记录 `df` 使用率、脚本返回码和结果到本文件，并只提交本次进度记录。当前自动化 ID 为 `piper`；若虚拟机不可访问、sudo 失效或清理失败，记录阻断，不扩大操作范围。

## 2026-09-23 21:36：本轮收尾

- 无运动基础链路证据和下一步已记录于本文件；对应运行时基线决策提交为 `ef31689`。本轮未部署启动脚本、未启用机械臂、未发送关节命令。

## 2026-09-23 21:46：清理、安装与一键脚本阻断

- 按用户要求执行 `/home/johnwick/clean_disk_space.sh`；根分区 `df -P /` 清理前后均为 55%（`40453376` 总块、`21021780` 已用、`17344480` 可用），脚本返回码 `0`。ROS/受限系统日志清理完成；apt 缓存因 sudo 密码未缓存而跳过。未使用临时 `rm -rf`，未删除源码、工作区或 `.git`。
- 运行 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 返回码 `0`：`piper` 构建约 1.94 秒，`brain_robot_pick_place` 与 `brain_robot_ball_pick` 构建通过；运行时启动脚本与规范源 SHA-256 均为 `da9838e47c...674230`，V2 驱动源/构建源均为 `7846be3719...3f96f`。
- 只读 SDK 查询：`C_PiperInterface_V2` 高速反馈时间戳持续更新、`200.0 Hz`，位置 `[0,-1,-10,-29,290,0]`（0.001°）；六轴使能 `[False,False,False,False,False,False]`。SDK 软件角度范围为 J1 ±2.6179、J2 0..3.14、J3 -2.967..0、J4 ±1.745、J5 ±1.22、J6 ±2.09439 rad；原始 `GetAllMotorAngleLimitMaxSpd()` / `GetAllMotorMaxAccLimit()` 返回仍为 `-1/65535`，仅执行查询未写入参数。
- 无运动启动单一 `piper_single_ctrl` 验证通过：`/joint_states` 一个发布者、约 `200 Hz`，`/enable_srv` 存在；随后已停止，未调用使能服务、未发送 `MotionCtrl_2`/`JointCtrl`。探针日志仅有启动瞬间约 `0.08s` 的反馈门控恢复。
- 实际运行 `/home/johnwick/start_brain_robot_cube_real.sh` 返回码 `1`，在 `[1/7]` 的 `sudo ip link set can0 ...` 处停止；脚本清理完成且没有残留 PiPER/MoveIt/视觉控制器。阻断证据日志：`/tmp/start_brain_robot_cube_real_20260923.log`。当前 `can0` 仍 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750，RX 持续增长。

### 本轮结论与接管动作

- 磁盘清理和规范安装已完成；启动脚本版本差异已消除。当前硬阻断是脚本需要 sudo 重新配置 can0，而非已观察到的 USB-CAN RX 故障。
- 用户需要在同一个 Ubuntu 终端自行执行一次 `sudo -v`（不要把密码发送给代理），然后回复“接管已完成，继续按固定提示词闭环”。在此之前不运行完整视觉栈、不使能机械臂、不发送真实运动命令。

## 2026-09-23 21:51：接管凭据仍未进入代理终端

- 用户回复已完成接管后，重新执行 `sudo -n -v` 仍返回码 `1`（需要密码）；因此代理终端没有可用 sudo 时间戳。未读取或代输入密码。
- 只读硬件复核通过：3 秒 `can0` RX 增量 `9136`，状态 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误计数为 0；当前无 PiPER、MoveIt、Servo 或视觉控制器残留。
- 未重复运行必然在 CAN 配置阶段失败的一键脚本，未启用机械臂、未发送运动命令。下一步仍需在代理可见的同一终端完成 `sudo -v`，并用 `sudo -n -v` 验证返回码 0 后再运行脚本。

## 2026-09-23 22:17：接力复核（无运动）

- 规范仓库仍为 `/mnt/hgfs/ub`；本轮开始工作树保留已有的大量供应商/相机/安装脚本修改和未跟踪 Debian 包，未覆盖、未暂存、未提交这些用户修改。根分区 `df -P /` 为 55%，未执行清理脚本。
- 实际路径均存在：`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs`；运行脚本与规范源 SHA-256 均为 `da9838e47fca452ab983c480f23f412905cdfe22327eb025fc43a1b621674230`。
- 只读硬件复核：USB-CAN `1d50:606f`、Astra `2bc5:0557/0657` 和内核模块 `gs_usb`/`can_dev` 均可见；`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包为 0。3 秒 SocketCAN 原始接收统计为 `0x251..0x256` 各 600 帧（约 200 Hz），位置原始值保持 `[0,-1,-10,-29,290,0]`（0.001°）；未发送任何运动命令。
- 当前 SDK 只读导入为 `piper_sdk 0.6.2`，路径 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`，类 `C_PiperInterface_V2`。本轮未调用固件查询或任何控制 API；交接记录中的 `S-V1.8-2` 仍是历史事实，当前固件版本未重新验证。
- `sudo -n -v` 返回 1（需要密码），因此未重配 CAN、未运行完整一键脚本、未使能六轴。现有 `can0` 虽健康，但脚本 `configure_can()` 仍无条件调用 sudo；不以修改脚本绕过权限作为本轮动作，等待操作者在同一终端完成一次 `sudo -v`。
- 发现仅有 `/usr/bin/python3 ... ros2 launch astra_camera astra.launch.py` 的孤立 launch 父进程（无子进程，ROS 仅有 `/launch_ros_29887`，无相机话题）；已发送 TERM 停止该残留父进程，未停止其他控制器。停止后无 PiPER/MoveIt/Servo/视觉控制栈残留。
- 证据：本轮终端输出（未写入仓库的大型日志）、`/home/johnwick/brain_robot_logs/astra_camera.log` 及历史相机恢复日志；原始 CAN 统计可由同一命令复现。阻断仍为代理终端无 sudo 凭据，且相机需由一键脚本重新启动后再验收真实帧/点云/TF。

### 本轮结论与下一步

- 已验证 CAN RX 和六条高速反馈持续存在，硬件安全前置（反馈层）通过；未验证固件版本、六轴使能、关节限位/速度/加速度复查、`/joint_states`、Astra 帧、点云自体过滤、TF/Octomap、视觉 `GRASP_READY` 或抓取。
- 不允许继续真机运动：六轴尚未使能，且完整脚本被 sudo 凭据阻断。操作者先在同一 Ubuntu 终端执行固定接管命令并确认 `sudo -n -v` 返回 0；下一轮第一条命令为：`cd /mnt/hgfs/ub && sudo -n -v && ip -details -statistics link show can0 && timeout 10s candump -n 10 can0`。

## 2026-09-23 22:31：用户声称接管后复核仍未获 sudo

- 用户要求代理代输入密码并声称“接管完成”；代理不接受、存储或代输入聊天中的密码，仅在当前终端执行无密码验证。
- `sudo -n -v` 返回 1（`sudo: 需要密码`），因此接管尚未进入代理可见的 sudo 会话；未重配 CAN、未运行一键脚本、未使能六轴、未发送运动命令。
- 只读复核仍显示 `can0` 为 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误计数为 0；`timeout 10s candump -n 10 can0` 返回 0，并捕获 `0x251`、`0x252` 及状态帧。由于仅取 10 帧，本次不宣称六条反馈完整覆盖。
- 阻断：必须由操作者在同一 Ubuntu 终端交互式输入 sudo 密码，使随后 `sudo -n -v` 返回 0。安全闸门未通过前不允许真机运动。

## 2026-09-23 22:35：截图后代理终端复核仍失败

- 用户提供截图显示其终端曾执行 CAN 配置并看到 `ERROR-ACTIVE`；代理终端重新执行 `sudo -n -v` 仍返回 1（需要密码），因此不能把截图当作本代理 sudo 会话已接管的证据。
- 无需 sudo 的硬件复核通过：`can0` 仍为 1 Mbps、sample-point 0.750、`ERROR-ACTIVE`、错误计数 0；3 秒原始 CAN 统计为 `0x251=600`、`0x252..0x256=599`（约 200 Hz）。未发送运动命令。
- 阻断保持：当前工具终端无法获得 sudo 时间戳；未运行完整脚本、未使能六轴、未执行真实运动。需要操作者在 Codex 实际执行命令所在的终端完成 sudo 认证，或提供不含密码的可验证 sudo 会话保活，然后让 `sudo -n -v` 在该终端返回 0。

## 2026-09-23 22:39：再次确认后 sudo 仍不可见

- 用户再次表示“完成”，但当前代理终端 `sudo -n -v` 仍返回 1（需要密码）。因此仍不能运行需要 sudo 的一键脚本，也不能把接管视为完成。
- 只读 CAN 反馈继续正常：`ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误计数 0；2 秒内 `0x251..0x256` 各 400 帧（约 200 Hz）。未发送运动命令。
- 未启动 PiPER 控制器、MoveIt/Servo/视觉栈，未使能六轴；安全闸门仍未通过。下一步仍需让 `sudo -n -v` 在代理实际执行命令的终端返回 0。

## 2026-09-23 23:05：健康 CAN 复用与一键无运动验收

- 规范脚本 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 增加最小可逆逻辑：若 `can0` 已为 `UP/UNKNOWN`、1 Mbps、sample-point 0.750 且 1 秒 RX 计数增长，则直接复用并跳过 sudo；接口异常时仍走原有特权重配置。`bash -n` 和该文件范围的 `git diff --check` 通过。
- 运行 `brain_robot_arm/scripts/install_piper_cube_pick.sh` 返回 0：`piper`、`brain_robot_pick_place`、`brain_robot_ball_pick` 均构建通过；运行时启动脚本已同步。脚本内磁盘清理保持根分区 55%，apt 清理由于 sudo 不可见而跳过，但未达到 85% 阈值，不构成磁盘阻断。
- 实际运行 `/home/johnwick/start_brain_robot_cube_real.sh` 返回至 `[7/7] 全部组件已就绪`，CAN 阶段输出“复用已处于 1 Mbps/0.75 且 RX 持续增长的 can0（无需重新配置）”，未要求 sudo、未自动按键、未使能或发送运动命令。
- 无运动 PiPER 驱动：唯一 `/piper_ctrl_single_node`，`/joint_states` 有效消息时间戳；实测平均约 170 Hz（窗口曾见 140–170 Hz，存在约 0.333 秒间隔），`/piper_moveit_joint_states` 持续发布。未调用 `/enable_srv`。
- Astra/视觉链路：唯一 Astra 容器、检测器、MoveIt、Servo、TF gate、自体过滤和抓取节点均存在；RGB 首帧和深度首帧收到，`/camera/depth/image_raw` 约 29 Hz，`/camera/color/image_raw` 实测约 8.6 Hz（有 USB/JPEG 丢帧迹象），原始点云约 6.5 Hz。`/brain_robot_vision/tf_gate_diagnostic` 为 `state=FORWARDED accepted_frames=380 rejected_frames=115 detail=TF_COMPLETE frame=camera_depth_optical_frame`；`/brain_robot_vision/filtered_points` 存在且带同一深度 frame/stamp；MoveIt `clear_octomap` 服务可用并已成功清图。
- 视觉状态保持安全等待：`/brain_robot_visual_control/state=IDLE`、`reason=WAITING_FOR_START`，`/brain_robot_grasp/scene_ready=false`、`state=WAITING_FOR_LEVEL_ALIGN`，目标 `target_valid=false`；未进入搜索、`GRASP_READY` 或抓取。停止脚本后发现其子进程短暂孤儿化，已按明确 PID 全部 TERM/KILL 清理；当前无 PiPER/相机/MoveIt/视觉残留。
- 证据路径：`/home/johnwick/brain_robot_logs/piper_driver.log`、`astra_camera.log`、`cube_detector.log`、`visual_stack.log`、`debug_image_view.log` 及其 `ros/` 子日志；本轮未提交大型日志、构建产物或 Debian 包。

### 本轮结论与下一步

- 已验证：健康 CAN 可在无 sudo PTY 时启动；一键流程可无运动到完整组件就绪；ROS 关节、RGB-D、点云 TF gate、自体过滤、Octomap、MoveIt/Servo 服务链路成立。
- 未验证：六轴使能后的真实小幅运动、限位/速度/加速度当前值复查、紫色目标稳定检测、视觉搜索/对齐进入 `GRASP_READY`、抓取/抬升/释放。RGB 仅约 8.6 Hz 且有 JPEG 错误，需后续优化或确认是否足够稳定。
- 当前不允许真机运动：本轮仅完成无运动链路验收，尚未打印并确认真实运动安全清单，也未得到本轮明确的运动授权。下一轮第一条命令：`cd /mnt/hgfs/ub && git status --short && sha256sum /home/johnwick/start_brain_robot_cube_real.sh brain_robot_arm/scripts/start_brain_robot_cube_real.sh`。

## 2026-09-23 23:13：真实运动安全清单只读复查

- 为准备而非执行真实运动，使用 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 后显式 `ConnectPort()`；未调用 Enable、MotionCtrl_2、JointCtrl 或任何写入限位 API。该次历史 SDK/协议/接口版本为 `0.6.2`/V2/V2，固件查询为 `S-V1.8-2`，已由本轮实体 `S-V1.9-1` 查询取代。
- 高速反馈新鲜：timestamp `1790176313.8304694`、`200.0 Hz`，六轴当前位置 `[0,-1,-10,-29,291,0]`（0.001°），速度/电流均为 0。`GetArmStatus()` 缓存的时间戳仍为 0，显示 STANDBY/NORMAL、无角度限位状态，不用作实时使能确认。
- 控制器限位响应仍不可用于安全运动：`GetAllMotorAngleLimitMaxSpd()` timestamp 虽更新，但六项均为 `max=-1,min=-1,max_joint_spd=65535`；加速度六项均 `65535`。这与历史已记录的默认 `±1500/0..1800/...`、最大速度 300、最大加速度 500 不一致，且本轮没有执行任何恢复或写入。按照安全闸门，不能据此形成真实关节目标或速度/加速度限位。
- 结论：CAN/固件/当前位置和静止状态已复核，但本轮不允许真实运动；必须先定位为何实际限位查询仍为无效值，或在用户确认和明确恢复计划后按官方最小步骤恢复并重新查询。此限制不阻断后续无运动视觉诊断。

## 2026-09-23 23:22：按已验证官方 API 恢复限位并逐轴回读

- 依据历史 SDK V2 官方示例 `demo/V2/piper_set_init_default.py`，先完成逐轴无使能查询：每个电机 `0x473` 角度/速度响应为全 `FF`，每个 `0x47C` 加速度响应为 `FF`；确认不是全轴缓存假象。
- 在六轴使能状态 `[False, False, False, False, False, False]` 下，仅执行一次 `ArmParamEnquiryAndConfig(0x01,0x02,0,0,0x02)`；未调用 `EnableArm`、`EnablePiper`、`MotionCtrl_2`、`JointCtrl`、`ResetPiper`、`MasterSlaveConfig` 或固件 API。该 API 写入厂家默认参数，存在持久化配置影响，已按用户“执行已验证安全代码”授权。
- 等待 1.5 秒后逐轴查询并抓原始反馈：`0x473/0x47C` 均有效，SDK 回读为：J1 `-1500..1500, spd=300, acc=500`；J2 `0..1800, 300, 500`；J3 `-1700..0, 300, 500`；J4 `-1000..1000, 300, 500`；J5 `-700..700, 300, 500`；J6 `-1800..1800, 300, 500`。`all_limits_valid=True`，恢复后六轴仍全部未使能。
- 证据：本轮 Python SDK 输出及 SocketCAN 原始帧（未写入仓库的大型抓包）；SDK 版本 `0.6.2`、协议/接口 V2。恢复动作没有产生关节运动，未启动 ROS 控制栈。

### 真实运动闸门状态

- 现在限位/速度/加速度参数已通过逐轴原始响应和 SDK 双重回读；高速反馈此前为 200 Hz，最新静止位置 `[0,-1,-10,-29,291,0]`（0.001°）。
- 尚未执行真实运动。本轮下一步若继续，只允许 J2 单关节 `+250`（0.25°）小幅测试；目标保持 J1/J3/J4/J5/J6 当前值，控制速度比例 10%，预计持续约 0.6 秒，停止条件为任意反馈丢失、位置超限、震动/碰撞、急停或目标偏差异常，回退为立即停止发送并保持/失能。
- 执行前仍需操作者确认机械臂旁有人看护、工作区无障碍、急停可用；未确认前不发送任何运动命令。

## 2026-09-23 23:31：J2 小幅运动第一次安全闸门中止

- 用户确认现场看护、无障碍和急停可用后，按安全清单启动 V2 SDK：高速反馈 timestamp `1790177645.338818`、`200.0 Hz`、年龄约 0.004 秒；当前位置 `[0,-1,-10,-29,291,0]`，目标预计算为 `[0,249,-10,-29,291,0]`（J2 +250 个 0.001°，速度比例 10%，时限 1.2 秒）。
- `EnableArm(7)` 在约 0.14 秒内回读六轴全 True；随后安全循环发现 J2 当前 `-1` 低于已恢复下限 `0`，在发送第一条 `JointCtrl` 前抛出 `limit violation` 并执行 `DisableArm(7)`，最终六轴全 False。没有调用 `MotionCtrl_2` 后的关节目标发送，没有观察到运动。
- 该失败是安全闸门有效证据，不是 CAN/RX 故障。J2 只超限 1 个 0.001° 单位，目标 249 在 `0..1800` 内；下一次若继续，必须明确记录采用的边界容差和目标仍在有效限位内，其他关节保持实际值。

## 2026-09-23 23:38：J2 小幅运动触发非目标关节位移，立即停止

- 第二次尝试采用已记录的 5-unit J2 边界容差；安全输出显示高速反馈 timestamp `1790177773.557920`、`200.0 Hz`，当前位置 `[0,-1,-10,-29,291,0]`，目标 `[0,249,-10,-29,291,0]`，六轴使能回读全 True，速度比例 10%。
- 发送 `MotionCtrl_2(0x01,0x01,10,0x00,0,0x01)` 和重复 `JointCtrl` 后，J2 只变化约 6–7 个单位，但未测试关节也明显变化：样本中 J3 `-10→-5`、J4 `-29→0`、J5 `291→190`。监控在 J5 位移超过 100 单位时立即中止并调用 `DisableArm(7)`；六轴回读全 False。
- 停止后的 1 秒静止复核仍有新鲜反馈约 206.7 Hz；位置稳定在约 `[0,0,-2,-1,256,0]`，六轴全 False，CAN 仍 ERROR-ACTIVE、无错误。未观察到碰撞/震动的直接传感证据；操作者需确认机械臂实际外观和是否触碰障碍。
- 这是控制行为异常，不是 sudo/CAN/RX 阻断。可能涉及控制器内部目标保持、安装姿态/模式、反馈映射或 SDK/固件控制语义；禁止重复同一真实运动实验，禁止继续视觉搜索或抓取运动。

### 当前真实运动阻断

- 已完成一次真实小幅动作尝试并按停止条件中止；当前机械臂保持失能。未验证单关节独立性、目标帧编码与固件模式的一致性，也未验证当前静止姿态是否由用户接受。
- 下一步只能做无运动的 TX 帧编码/回放分析、控制器模式反馈和代码审计；若需再次使能或运动，必须先解释非目标关节位移并重新得到用户确认。

## 2026-09-23 23:45：非目标位移根因定位为高速反馈单位误用

- 重新读取规范仓库最新决策 `7d8e0aa` 后确认：高速电机反馈 `GetArmHighSpdInfoMsgs().motor_i.pos` 单位为 `0.001 rad`，而 `JointCtrl()` 参数单位为 `0.001°`。此前两次 J2 测试把高速值 `[0,-1,-10,-29,291,0]` 直接作为角度目标，违反该决策。
- 该单位错误解释了现场现象：例如高速 J5 `291` 实为 `0.291 rad`（约 16.7°），却被当作 `0.291°` 目标，导致 J5 向错误目标移动；J3/J4 同理。J2 实际目标也不是预期的 +0.25°。
- 当前高反馈静止值约 `[0,0,-2,-1,256,0]`（0.001 rad），六轴已失能；CAN 仍 ERROR-ACTIVE/RX 正常。未继续发送任何运动命令。
- 这是代理本轮测试中的安全方法错误，已立即停止并冻结真机运动；后续必须从已验证 `/joint_states` 弧度值或显式 `rad→0.001°` 换算构造目标，逐帧核对 TX 编码，不能重复此前直接复用高速 `pos` 的实验。

## 2026-09-23：无效限位响应的只读定位方案

- 已查阅 AgileX V2 SDK 接口文档：全轴限位/加速度 getter 是查询响应缓存；单轴 `SearchMotorMaxAngleSpdAccLimit(motor, 0x01)` 查询角度/速度，`0x02` 查询加速度，查询命令 CAN ID 为 `0x472`；角度/速度单轴响应为 `0x473`。因此全轴缓存出现 `-1/65535` 不能直接证明六轴控制器参数同时损坏。
- 下一最小动作是完全无使能、无运动、无写入的逐轴查询与 CAN 抓包：每次只查询一个电机一种内容，等待响应后读取 `GetCurrentMotorAngleLimitMaxVel()` 或 `GetCurrentMotorMaxAccLimit()`，并核对原始 `0x472` 请求和对应反馈。结果将区分“无响应/原始全 FF”“原始值正常但 SDK 解析错误”“逐轴有效而全轴缓存错误”。
- 官方文档同时指出高速反馈 `pos` 单位为 `0.001 rad`，而 `JointCtrl` 单位为 `0.001°`。已修正决策：后续不得把高速反馈 `pos` 直接复用为 JointCtrl 目标；必须使用已验证的关节状态源并显式单位换算。
- 本轮未执行逐轴查询、未使能、未发送运动、未写入限位。若逐轴原始响应确认参数确实无效，才需由用户明确授权官方默认参数恢复，然后逐轴回读验证后再讨论运动。

## 2026-09-23：一次性授权与防坠落规则补充

- 用户要求停止同一项小幅真机测试的重复确认，并明确要求复位时避免机械臂失能/坠落。本轮只修改固定任务规则与决策文档，未发送运动命令。
- 已将规则写入 `CODEX_TASK_PROMPT.md` 和 `docs/PIper_DECISIONS.md`：一次性授权通过后不重复阻断；测试收尾默认回到测试前已验证的安全目标并保持使能；不得自动 `DisableArm(7)`；`ResetPiper` 禁止用于停止、复位或异常收尾，因为会立即掉电并可能造成下坠。
- 碰撞、持续震动、反馈丢失或位置异常时，只停止新的位移目标并按安全停机/物理急停路径处理，不继续对障碍物施力，也不自动掉电。以上是规则更新，尚未证明任何新的真机运动结果。

## 2026-09-23 23:55：恢复运行时基线并清理孤儿视觉栈（无运动）

- 本轮恢复前 HEAD 为 `4591754`。规范运行时路径均存在；`/home/johnwick/start_brain_robot_cube_real.sh` 与 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 的 SHA-256 同为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。`/home/johnwick/piper_ros` 和 `/home/johnwick/piper_ws` 不是独立 Git 仓库，规范副本位于 `brain_robot_arm/vendor/piper_ros`、`brain_robot_arm/piper_ws`、`brain_robot_arm/scripts`。
- 根分区为 55%，未触发 85% 清理阈值。`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750、错误/丢包为 0；2 秒 RX 增量为 6095。此次未连接 SDK、未使能、未调用 `MotionCtrl_2`、`JointCtrl`、`ResetPiper` 或任何参数写入 API。
- 发现 PPID 1 的孤儿 `/visual_search_controller`（PID 36742，原启动组 36715）。节点仍发布 `/servo_node/delta_joint_cmds`，但没有 PiPER 驱动、Servo 或 jog adapter 接收；为防止下次一键启动形成视觉/TF 竞争，仅发送 `TERM`。同一启动组遗留的 `piper_camera_mount_tf` 静态 TF（PID 36728）也已 `TERM`。两项均为启动/停止 ROS 节点，不涉及真机控制。
- 已用 `pgrep` 确认没有 `piper_single_ctrl`、`piper_jog_adapter`、`visual_search_controller`、`grasp_lift_executor`、`move_group`、`servo_node`、Astra、检测器、TF gate 或相机挂载 TF 进程。`ros2 node list` 在进程退出后短暂显示陈旧 DDS 发现；执行 `ros2 daemon stop` 清除 CLI 缓存后图为空。未停止或修改用户已有工作树改动及未跟踪 Debian 包。
- 源码只读审计确认实际 PiPER 节点使用 `GetArmHighSpdInfoMsgs()` 作新鲜度门控，而常规 ROS 位置反馈取自 `GetArmJointMsgs()`；此前目标构造必须继续遵守高频 `pos` 为 `0.001 rad`、`JointCtrl` 为 `0.001°` 的隔离规则。当前真实运动仍冻结，不能启动搜索或抓取运动。

### 本轮结论与下一步

- 已验证：运行时脚本已同步、CAN 持续接收、残留的可发布 Servo 增量的视觉控制器和同组静态 TF 已清除，下一次启动可从唯一干净栈开始。
- 未验证/阻断：未确认 SDK 当前六轴状态和逐轴限位回读；未完成 TX 帧编码/保持目标的无运动审计；单关节独立性、观测姿态、紫色检测、`GRASP_READY`、抓取/抬升/释放均未验证。因既有非目标关节位移，禁止 EnableArm、MotionCtrl_2、JointCtrl 和视觉搜索运动。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node|astra_camera|cube_detector|pointcloud_tf_gate|piper_camera_mount_tf' || true`；随后仅做 SDK `JointCtrl` TX 编码与 ROS 关节状态来源的无运动审计。

## 2026-09-23 23:59：SDK TX 与完整六轴命令审计（无运动）

- 只读检查安装的 `piper_sdk 0.6.2`、运行时 PiPER 驱动及运行时 jog 适配器；未实例化 SDK、未打开 SocketCAN、未启动 ROS 节点、未发送 CAN 帧或使能命令。SDK 文档/实现确认：`MotionCtrl_2` 编为 `0x151`；`JointCtrl` 将六个 `0.001°` 整数经软件限位后无条件发送 `0x155`（J1/J2）、`0x156`（J3/J4）、`0x157`（J5/J6）。官方 `demo/detect_arm.py` 将高速 `pos * 1e-3` 显示为 rad，继续佐证高频 `pos` 是 `0.001 rad` 而不是 `0.001°`。
- 运行时与规范 PiPER 驱动哈希相同（`7846be...3f96f`），jog 适配器哈希也相同（`29d369...1e11f`）。适配器只有在已 armed、关节反馈新鲜且完整时才以明确顺序发布 `joint1..joint6`；它不解释或修复其他发布者的截断 `JointState`。
- 发现驱动 `joint_callback()` 在使能且反馈新鲜时对缺失名称使用 `joint_positions.get('jointN', 0)`，随后调用完整六轴 `JointCtrl`。这会把不完整命令变成对缺失关节的绝对零位目标，正是此前“保持目标”不能靠猜测构造的同类风险。`docs/PIper_DECISIONS.md` 已新增完整六轴门控：不完整、重复、未知或 name/position 不匹配的命令必须无输出拒绝。
- 未直接修改驱动：其规范副本已有用户未提交差异 `443 insertions/391 deletions`，并带 CRLF/尾随空白，使 `git diff --check` 对整文件报错；危险回调位于该用户改动范围。为不覆盖或混入用户改动，本轮仅记录，未构建、未部署、未格式化该文件。

### 本轮结论与下一步

- 已验证：SDK 控制帧 ID、单位、完整 jog 发布路径，以及驱动的零位回退缺陷；这解释了为什么不能仅凭 J2 目标假定其余关节会保持不动。
- 阻断：必须先把用户已有 `piper_ctrl_single_node.py` 改动的来源和意图与用户确认，或由其作者完成/授权最小的完整六轴拒绝补丁；在此之前，真实运动及视觉搜索/抓取保持冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git diff --numstat -- brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py && sed -n '340,410p' /home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py`。

## 2026-09-24 00:02：完整六轴命令门控实现与无 CAN 验证

- 用户明确授权在已有驱动改动上继续完成。本轮起点为 `64bb67b`；只修改规范副本 `brain_robot_arm/vendor/piper_ros/src/piper` 和相同的实际运行源 `/home/johnwick/piper_ros/src/piper`，没有覆盖其他用户修改、没有格式化 CRLF 文件，也没有启动 ROS、实例化 SDK、打开 SocketCAN、使能或发送 CAN。
- 新增纯模块 `piper.command_validation`。它要求 `JointState.name` 与 `position` 等长，六个 `joint1..joint6` 各出现一次，只允许可选 `gripper`，并拒绝重复/未知名称、非数值和非有限位置。`joint_callback()` 在任何 `_set_joint_control_mode()`、`JointCtrl()` 或 `GripperCtrl()` 前调用该验证；有效消息按名称映射为 `0.001°`，不再以 `.get(..., 0)` 填充缺轴。夹爪只有显式 `gripper` 名称时才发控制帧。
- 新增 `test_command_validation.py`，以 `PYTHONPATH=brain_robot_arm/vendor/piper_ros/src/piper python3 -m unittest discover -s brain_robot_arm/vendor/piper_ros/src/piper/test -p 'test_command_validation.py' -v` 通过 3/3：完整乱序六轴、带显式夹爪、以及缺轴/重复/未知/长度不匹配/NaN 均符合预期。`python3 -m py_compile` 对驱动和验证模块通过。
- 在 `/home/johnwick/piper_ros` 执行 `source /opt/ros/humble/setup.bash && colcon build --symlink-install --packages-select piper`，返回 0（2.69 秒）；`source install/setup.bash` 后可从 `build/piper/piper/command_validation.py` 成功导入。规范/运行时驱动 SHA-256 同为 `e5ad444c...46e90c`，验证模块同为 `162f3968...ee3bde`。

### 本轮结论与下一步

- 已验证：不完整 ROS 关节消息现在能在 CAN 输出前被纯逻辑拒绝；完整六轴和显式夹爪消息仍被接受；运行时 `piper` 构建与导入成功。
- 未验证/阻断：未在运行节点中观察拒绝日志，未复查 SDK 当前六轴使能/限位，未测试正确单位目标的真实独立运动；观测姿态、相机、紫色检测、`GRASP_READY`、抓取/抬升/释放均尚未运行。真实运动和视觉搜索保持冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && PYTHONPATH=brain_robot_arm/vendor/piper_ros/src/piper python3 -m unittest discover -s brain_robot_arm/vendor/piper_ros/src/piper/test -p 'test_command_validation.py' -v`；随后只读复查 SDK 的当前六轴使能、逐轴限位和正确单位的 ROS `/joint_states` 来源，再决定是否能进行无运动节点验收。

## 2026-09-24 00:04：SDK 逐轴限位与静止反馈复查（无运动）

- 使用 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 后仅 `ConnectPort()`；没有调用 Enable/Disable、`MotionCtrl_2`、`JointCtrl`、`GripperCtrl`、`ResetPiper` 或任何参数写入 API。仅向 `0x472` 发送逐轴限位/加速度查询并读取相应响应；脚本返回 0。
- 高速反馈新鲜：timestamp `1790179515.008173`、`200.0 Hz`，原始位置 `[0,0,-2,-1,256,0]`（`0.001 rad`）；`GetArmEnableStatus()` 为六轴全 `False`。CAN 保持 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包为 0。
- 每轴查询响应有效：J1 `-1500..1500`、J2 `0..1800`、J3 `-1700..0`、J4 `-1000..1000`、J5 `-700..700`、J6 `-1800..1800`（`0.001°`）；最大速度均 300、最大加速度均 500。响应时间戳随每次查询更新，排除了全轴缓存 `-1/65535` 的旧阻断。

### 本轮结论与下一步

- 已验证：CAN、高速反馈、六轴未使能状态及逐轴限位/速度/加速度都可由当前 SDK 直接复现；本轮无关节或夹爪运动。
- 未验证：运行时驱动发布的 `/joint_states` 是否使用新鲜/正确的 `0.001°` 聚合反馈并与高速 `0.001 rad` 换算一致；完整启动栈、紫色检测和任何真实运动仍未运行。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node' || true`；随后只启动一个 `auto_enable:=false` PiPER 驱动，采样 `/joint_states` 后立即停止，不调用 `/enable_srv`。

## 2026-09-24 00:07：唯一无使能驱动的 ROS 关节状态采样

- 启动前无 PiPER/Servo/视觉控制器残留。仅启动一个 `ros2 run piper piper_single_ctrl`，参数为 `can_port:=can0`、`auto_enable:=false`、`gripper_exist:=true`，并重映射 `joint_states_single:=/joint_states`、`joint_ctrl_single:=/joint_commands`；没有调用 `/enable_srv`、没有发布 `/joint_commands`、没有调用任意运动 API。
- `/joint_states` 只有一个可靠 QoS 发布者。`ros2 topic hz` 在三段窗口得到约 `202.420`、`201.168`、`200.792 Hz`。独立 rclpy 订阅器成功收到当前时间戳 `[1790179605,993249416]` 的消息，名称为 `joint1..joint6,gripper`，位置为 `[0.0,-0.002930592,0.004291224,0.0,0.264869696,0.0,0.00007]`，速度六轴均为 0。
- 同一轮只读 SDK 高速位置为 `[0,0,-2,-1,256,0]`（`0.001 rad`）。ROS J2/J3/J5 不能与该高速电机值逐项直接换算为同一结果，故未将 ROS 或高速位置用作真实目标；新决策已冻结任何基于未验证映射的绝对保持目标。
- 首次 CLI `ros2 topic echo --once` 在发现期误报未发布，改用 rclpy 订阅成功。首次 SIGINT 只结束 `ros2 run` 包装而遗留其明确子 PID；已 TERM 该子 PID 并复查为空。第二次采样也在停止时触发已知 `ExternalShutdownException`/重复 `rcl_shutdown` 日志，但 wrapper 和子进程最终均已退出；CAN 保持 `ERROR-ACTIVE`、无错误/丢包。

### 本轮结论与下一步

- 已验证：单一未使能驱动的 ROS 发布频率、时间戳、名称和退出残留处理；未向真机发送位移或使能。
- 阻断：不能把高速电机反馈与 ROS 聚合关节状态假定为相同关节角；该映射未验证前，真实小幅动作、观测姿态和视觉搜索仍冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && python3 -c "from piper_sdk import C_PiperInterface_V2; print(C_PiperInterface_V2)"`；随后在单个只读 SDK 实例中同时采样 `GetArmJointMsgs()`、高速反馈和 SocketCAN 聚合帧，建立或否定可安全使用的关节映射。

## 2026-09-24 00:09：聚合关节反馈与 ROS 映射证明（无运动）

- 在一个 `C_PiperInterface_V2` 实例中复用驱动同样的纯接收 `0x3A0..0x3A7 → 0x2A1..0x2A8` 翻译，等待 1 秒后只读取缓存；未调用 Enable/Disable、`MotionCtrl_2`、`JointCtrl`、`GripperCtrl`、`ResetPiper`、限位写入或其他运动 API。探针返回 0，CAN 继续 `ERROR-ACTIVE`、无错误/丢包。
- 同时间戳反馈：高速 `1790179674.7383657`、`200 Hz`、`[0,0,-2,-1,256,0]`（`0.001 rad`）；聚合关节 `1790179674.7374153`、`200 Hz`、`[0,-168,246,0,15184,0]`（`0.001°`）；六轴全未使能。后者经 `π/(180*1000)` 转换正好对应上一轮 ROS 消息 `[0,-0.002930592,0.004291224,0,0.264869696,0]`（微小采样差异除外）。
- 结论：`/joint_states` 的名称、顺序和单位已得到聚合 CAN/SDK 双重证实；高速电机 `pos` 是独立电机量，不能直接作关节保持目标。当前聚合 J2=-168 和 J3=246 略越过已读回的零边界 J2≥0、J3≤0，故本轮没有发送任何“保持当前位置”目标。

### 本轮结论与下一步

- 已验证：可安全使用的关节状态源、ROS 的单位/顺序及高速/聚合反馈的语义隔离。
- 阻断：当前 J2/J3 位于零限位边界的外侧；任何真实动作前必须先打印完整安全清单、明确边界容差和目标均在限位内，且确认现场急停/障碍条件。观测姿态、视觉搜索和抓取继续冻结。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && sed -n '1,130p' docs/PIper_DECISIONS.md`；随后仅准备（不执行）基于聚合关节角的单关节内限位回退计划，包含六轴目标、单位、速度、时间、停止条件与回退动作。

## 2026-09-24 00:10：SDK 与视觉软限位语义审计（无运动）

- 只读审计 `piper_sdk 0.6.2` 的 `__CalJointSDKLimit()` 与运行时 jog 适配器参数；未创建 SDK 实例、未打开 CAN、未启动 ROS 或发送任何帧。SDK 仅在 `start_sdk_joint_limit` 为真时按 `GetSDKJointLimitParam()` 的弧度范围转换到 `0.001°` 并钳制 `JointCtrl` 值；它不是控制器逐轴 `0x472` 响应的替代。
- 当前 jog 适配器软范围为 J1 `[-1.50,1.50]`、J2 `[-0.30,1.40]`、J3 `[-1.40,0.40]`、J4 `[-0.80,0.80]`、J5 `[-1.20,1.20]`、J6 `[-0.80,0.80]` rad，故会容许当前聚合 J2/J3 的零边界外小偏移；该范围不能授权真实控制器越界或让 SDK 静默截断目标。

### 本轮结论与下一步

- 已验证：SDK 软件钳位、控制器逐轴限位和视觉适配器软范围是三种独立机制；真实动作必须显式检查并记录控制器限位内目标，不能依赖任一方静默修正。
- 阻断：仍缺现场确认（人员/障碍/急停）及明确边界容差后的完整六轴内限位回退计划；在其前禁止 Enable、模式切换、`JointCtrl`、视觉搜索和抓取。
- 下一名代理第一条命令：`cd /mnt/hgfs/ub && git status --short && tail -n 55 docs/PIper_PROGRESS.md`；随后输出（不执行）完整真机动作安全清单和由聚合关节反馈换算的六轴目标，等待现场条件确认。

## 2026-09-24 00:13：一键脚本完整无运动验收

- 从无 PiPER、相机、MoveIt、Servo、检测器或视觉控制器残留的状态，以标准输入 `/dev/null` 启动实际运行时脚本 `/home/johnwick/start_brain_robot_cube_real.sh`；未输入 `1`、`2` 或 `0`，未调用使能服务、`EnableArm`、`MotionCtrl_2`、`JointCtrl`、`DisableArm(7)` 或 `ResetPiper`。
- 脚本依次通过 `[1/7]` 健康 `can0` 复用、RGB 首帧、紫色方块 RGB-D 检测器、MoveIt/Servo/保护适配器、同时间戳 TF/Octomap、调试图像首帧，并到达 `[7/7] 全部组件已就绪`。apt 缓存清理因无交互 sudo 被跳过；根分区仍为 55%、可用 16981 MB，不影响启动。
- 就绪期间的只读验收：`/joint_states` 只有 `/piper_ctrl_single_node` 一个发布者和两个订阅者，消息为 `joint1..joint6,gripper`，当前位置为 `[0,-0.002930592,0.004291224,0,0.264869696,0,0.00007]` rad；`/brain_robot_vision/tf_gate_diagnostic` 为 `state=FORWARDED ... detail=TF_COMPLETE`；视觉控制器状态为 `IDLE`、原因为 `WAITING_FOR_START`。未进入搜索、`GRASP_READY` 或抓取。
- 为验证正常退出而非触发危险的 Ctrl+C 分支，仅向脚本父进程发送 `TERM`。清理日志明确为“未收到 Ctrl+C；不发送 PiPER 失能命令”，随后所有本脚本启动的 PiPER、相机、检测、MoveIt/Servo、TF gate 与视觉进程均已退出；没有残留 scoped 进程。
- 高速电机 `pos` 与 `/joint_states` 不逐项相等在本轮不构成新的运动阻断：已证明 `/joint_states` 直接来自官方 SDK 聚合 `GetArmJointMsgs()`（`.001°` 经 `pi/(180*1000)` 转 rad），而高速 `pos` 是独立的 `.001 rad` 电机反馈。尚未单独推导减速比、零位偏移或方向映射，故高速 `pos` 仍不得直接作 `JointCtrl` 目标；但已证明的聚合→ROS 链路足以继续本一键脚本的无运动验收，不重复同类诊断。

### 本轮结论与下一步

- 已验证：实际运行时一键脚本能在不使能、不运动的情况下完整到达待命状态，且启动、反馈、TF/点云门控、视觉控制器空闲状态与无掉电的 TERM 清理路径均符合预期。
- 阶段状态修正：`P0` CAN/反馈/限位已通过；`P1` 驱动命令完整性已通过静态门控和无 CAN 单元测试，但实际运行链路仍需验证；`P2` 小幅真实运动尚未验证；`P3` 一键脚本无运动启动已通过；`P4/P5` 视觉搜索和抓取尚未开始。
- 当前主阻断是 `P2` 真实 PiPER 运动尚未完成验证，不是 `target_valid=false`。视觉目标缺失只记录为后续 `P4/P5` 待办，不要求用户现在提供紫色方块，也不阻断运动恢复。
- 下一最小动作：使用与启动脚本相同的 `piper_single_ctrl` 和 `/joint_commands` 链路，在完整安全清单和一次性授权已存在的前提下，执行一项小幅可逆单关节测试；测试后回到测试前安全姿态并保持使能。不得调用 `ResetPiper` 或自动 `DisableArm(7)`。

## 2026-09-24 00:17：紫色目标无运动观察

- 由无残留状态第二次以 `/dev/null` 启动运行时一键脚本；再次完整到达 `[7/7] 全部组件已就绪`，未输入搜索、抓取或零点按键，未使能或发送关节/夹爪指令。
- `cube_detector` 是 `/brain_robot_vision/target_valid` 与 `/brain_robot_vision/target_pixel` 的唯一发布者，视觉搜索及抓取节点均已订阅 `target_valid`。连续 10 秒订阅得到的所有 `target_valid` 消息均为 `false`；在此期间没有收到 `target_pixel` 或 `target_point_camera`。检测器日志为 `PURPLE_CUBE target LOST`，而非节点崩溃、相机首帧或 TF gate 失败。
- 仅以 `TERM` 停止脚本父进程；日志确认走“保持、不发送 PiPER 失能命令”分支，随后 scoped PiPER、相机、检测、MoveIt/Servo、TF 与视觉进程均为空。未调用 `ResetPiper` 或 `DisableArm(7)`。

### 本轮结论与下一步

- 已验证：一键启动后的紫色目标检测主题和下游订阅关系完整；当前相机视野/实际场景没有获得可用紫色方块目标。这是继续搜索、对齐、`GRASP_READY` 与抓取前的外部视觉输入阻断，不能通过重复关节反馈、限位或启动诊断解决。
- 该视觉观察记录仍然有效，但属于 `P4` 的后续待办；不能覆盖当前 `P2` 运动恢复阶段。待 `P2` 通过后，再在相机视野内提供可检测目标并验证 `target_valid=true`、`target_pixel` 和 `target_point_camera` 稳定发布，然后才进入 `P4/P5`。

## 2026-09-24 00:58：运行时完整六轴门控无运动复核

- 实际运行栈由 `/home/johnwick/start_brain_robot_cube_real.sh` 的同一父进程保持：唯一 `piper_single_ctrl`、Astra、`cube_detector`、MoveIt/Servo、TF gate、`piper_jog_adapter`、`visual_search_controller` 和 `grasp_lift_executor` 均存在；没有第二个 PiPER 驱动。CAN 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point `0.750`，两秒 RX 增量 `6141`；根分区使用率 `55%`；运行时与规范启动脚本 SHA-256 均为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。
- 只读 ROS 状态确认视觉控制器 `IDLE/WAITING_FOR_START`，`scene_ready=false`，`target_valid=false`；`/arm_status` 为 `arm_status=0`，六轴通信/限位错误均为 false；`/joint_states` 只有 `piper_ctrl_single_node` 一个发布者，当前位置约 `[0,-0.002930592,0.004291224,0,0.266474544,0]` rad。
- 最小无运动动作：向实际 `/joint_commands` 发布一条仅含 `joint1` 的缺轴 `sensor_msgs/msg/JointState`。运行时 `joint_callback()` 返回校验拒绝；CAN TX 计数 `588→588`（增量 `0`），前后 `/arm_status` 完全相同且仍未使能。命令发布返回码 `0`，未调用 `/enable_srv`、`EnableArm`、`MotionCtrl_2`、`JointCtrl` 或任何夹爪控制。该证据补齐了 P1 静态单元测试之外的实际 ROS→驱动拒绝路径。
- 环境/证据：ROS 2 Humble、`/home/johnwick/piper_ros/install/piper`；只读进程/话题检查和 TX 计数如上，未写入大型日志。当前脚本仍在安全待命，未进入搜索或抓取。

### 本轮结论与下一步

- `P1` 运行时完整六轴门控已通过；`P0`、`P1`、`P3` 保持通过，`P2` 仍未通过，`P4/P5` 尚未开始。
- 当前阻断不是目标缺失，而是安全目标构造：聚合 `/joint_states` 的 J2≈`-0.168°`（控制器下限 `0°`）和 J3≈`+0.246°`（控制器上限 `0°`）仍在边界外。不能发送包含越界保持值的六轴绝对目标，也不能重复此前高速反馈单位误用实验。
- 下一最小动作：在不使能、不发送目标的前提下，保存一份同一 SDK/ROS 实例的聚合关节值与逐轴限位回读；然后由现场安全清单确认机械支撑、障碍和急停，制定并审查仅将 J2/J3 带回限位内的最小双关节回退目标。未完成该审查前，禁止 EnableArm、MotionCtrl_2、JointCtrl、视觉搜索或抓取运动。

## 2026-09-24 01:08：P2 小幅回退动作与瞬态反馈异常

- 动作前安全清单通过：高速反馈时间戳 `1790183148.9189608`、约 `210 Hz`；六轴未使能；逐轴控制器限位/速度/加速度有效（J1 ±1500、J2 0..1800、J3 -1700..0、J4 ±1000、J5 ±700、J6 ±1800；速度 300、加速度 500，单位 0.001°）。以 ROS 聚合位置构造合法目标 `[J1=0°, J2=+0.100°, J3=-0.100°, J4=0°, J5=15.2679°, J6=0°]`，速度比例 10%，仅计划 J2/J3 回到限位内。
- 通过实际 `/enable_srv` 返回 `enable_response=True` 后，向 `/joint_commands` 发布完整六轴目标；第一条反馈显示 J2≈`+0.193°`、J3≈`-0.113°`，但单个 ROS 聚合样本暂时显示 J5≈`+0.378°`，超过非目标轴 `0.2°` 漂移阈值，立即停止继续发布目标；未调用 `DisableArm(7)`、`ResetPiper` 或其他失能动作。
- 随后 2.5 秒只读监测中位置稳定为 J2≈`+0.193°`、J3≈`-0.113°`、J5≈`+15.253°`，`motion_status=0`、无错误/限位/通信故障。动作后独立 SDK 只读交叉核对高速反馈约 `200–210 Hz`、位置 `[0,4,-9,0,257,0]`（0.001 rad），六轴使能 `[True,True,True,True,True,True]`；因此 J5 异常被判定为单个聚合反馈瞬态，未观察到持续非目标机械位移。
- 证据与风险：本次动作证明 ROS 完整六轴命令可使 J2/J3 从控制器边界外进入限位内并稳定保持；同时暴露单样本聚合反馈异常，后续视觉轨迹必须继续逐样本检查所有轴，任何重复漂移立即停止。当前脚本仍保持运行，适配器未自动失能。

### 本轮结论与下一步

- `P2` 小幅可逆动作已通过“目标在限位内、反馈持续、非目标轴无持续漂移、六轴保持使能”的实测门控；`P0/P1/P2/P3` 现可继续。单样本聚合反馈瞬态作为剩余风险保留，不能重复同一直接目标实验。
- 当前主要阻断转为视觉外部输入：视觉控制器仍未进入搜索，检测器此前连续 `target_valid=false`；这不再阻断低层运动恢复。
- 下一最小动作：通过已运行脚本的实体运动门和 `visual_search_controller/reset`，先将六轴按配置安全复位到全零，再启动观测姿态；全程监测关节限位、反馈新鲜度和状态机，若无紫色目标则停在安全等待，不盲动抓取。

## 2026-09-24 01:14：视觉复位后 PiPER/CAN 反馈丢失阻断

- `visual_search_controller/reset` 在实体运动门和适配器 arm 后返回成功，第二次持久在线程监测得到 `STATE=STOPPED/RESET_COMPLETE`；随后 `/joint_states` 全零（含 J2/J3/J5），限位内。第一次监控会话提前终止曾触发 `USER_STOP`，未调用 PiPER 失能；第二次复位完成后未再发送视觉目标。
- 调用 `/visual_search_controller/start` 时返回失败：`No fresh joint state; the robot controller is not ready.`。随后实际驱动日志记录 `0x151 send failed: SendCanMessage(SEND_MESSAGE_FAILED (100017))`，`can0 feedback lost`，约两秒后 `can0 is loss` 并退出；运行时 `/piper_ctrl_single_node` 已不存在。
- 只读 CAN 复核：接口仍 `UP/ERROR-ACTIVE`、1 Mbps、sample-point `0.750`，但 bus-errors=`700`、arbit-lost=`9`、dropped=`9`，3 秒 RX 增量 `0`；USB-CAN `1d50:606f` 和 `gs_usb/can_dev` 仍枚举。`sudo -n -v` 返回 `1`（需要密码），不能由当前会话执行接口重配/驱动重载。
- 已按安全路径停止残留脚本进程组、Astra、检测器、MoveIt、Servo、TF、适配器和视觉控制器；未调用 `ResetPiper` 或 `/enable_srv false`，未在反馈丢失后继续发送目标。证据日志：`/home/johnwick/brain_robot_logs/piper_driver.log`、`visual_stack.log`；当前无 PiPER/视觉控制栈残留。

### 本轮结论与下一步

- `P0/P1/P2/P3` 的此前证据仍保留；P4 仅完成全零复位，观测姿态/搜索未启动，`GRASP_READY`、抓取、抬升、释放均未验证。
- 当前硬阻断升级为真实 CAN RX 丢失和发送失败，不是视觉目标缺失。无持续 `0x251..0x256` 反馈前禁止重新启动 PiPER、调用 `/enable_srv`、`MotionCtrl_2`、`JointCtrl` 或视觉搜索。
- 下一最小动作：操作者在同一 Ubuntu/Codex 终端完成一次 `sudo -v`，然后按接管协议重置 `can0`（必要时重载 `gs_usb`），用 `ip -details -statistics link show can0` 和 `candump -n 10 can0` 确认 RX 恢复；恢复前不重复本轮动作。

## 2026-09-24 11:14：现场只读复核确认 USB-CAN/接口仍不可用

- 当前 commit：`77b3443`；实际命令为 `sudo -n -v`、`lsusb | grep -Ei '1d50:606f|OpenMoko|CAN'`、`lsmod | grep -E 'gs_usb|can_dev'`、`ip -details -statistics link show can0`、3 秒 RX 计数、`timeout 10s candump -n 10 can0`、目标进程 `pgrep`、路径存在性、启动脚本 SHA-256 和 `df -P /`。
- 返回结果：`sudo -n -v` 返回 1（需要密码）；USB-CAN grep 无匹配；`gs_usb` 与 `can_dev` 模块仍加载；`can0` 不存在，`ip` 返回 1，RX 计数文件不存在，`candump` 返回 1（`No such device`）。没有 `piper_single_ctrl`、视觉、相机或 MoveIt 残留进程。
- 运行时路径 `/home/johnwick/piper_ros`、`/home/johnwick/piper_ws`、`/home/johnwick/start_brain_robot_cube_real.sh`、`/home/johnwick/brain_robot_logs` 均存在；运行时脚本与规范源 SHA-256 都为 `70eb2b981c94d305ffa1b87a7a30ed09c20b613b6a8b78176804aeaff132d872`。根分区使用率 55%（未达到清理阈值）。
- 本轮未启动任何 ROS/PiPER 进程，未调用 `/enable_srv`、`EnableArm`、`MotionCtrl_2`、`JointCtrl`、`ResetPiper`，未发送 CAN/运动命令。证据为本轮终端只读输出；历史发送失败日志仍在 `/home/johnwick/brain_robot_logs/piper_driver.log`。

### 本轮结论与下一步

- 当前实际状态比上一条记录更早：不仅无 RX，`can0` 和 USB-CAN 枚举本身也不存在；`gs_usb/can_dev` 仅表示内核模块尚在，不能证明硬件链路健康。P0 未恢复，P2/P4/P5 均继续禁止。
- 阻断为操作者侧 USB/虚拟机映射、机械臂供电/CAN 线缆或需要特权的接口重新枚举/配置；不能靠重启驱动或视觉栈绕过。下一最小动作必须由操作者在同一 Ubuntu/Codex 终端完成一次 `sudo -v`，确认 USB-CAN 已连接且机械臂电源/CAN 线稳定后，按接管协议恢复并验证 `can0`、持续 `0x251..0x256` RX；在此之前不重复任何上层实验。

## 2026-09-24 现场修复后复核：USB-CAN 已枚举但 can0 仍 DOWN

- 当前 commit：`c09706e`；复核命令为 `sudo -n -v`、`lsusb`、`lsmod`、`ip -details -statistics link show can0`、3 秒 RX 计数、`timeout 10s candump -n 10 can0` 和目标进程检查。
- USB-CAN 已恢复枚举：`1d50:606f OpenMoko, Inc. Geschwister Schneider CAN adapter`；`gs_usb`/`can_dev` 已加载。但 `can0` 为 `state DOWN`、`can state STOPPED`、RX/TX/错误/丢包全为 0；`candump` 返回 `Network is down`，3 秒 RX 增量为 0。
- 当前 Codex 终端 `sudo -n -v` 仍返回 1（需要密码）；没有 `piper_single_ctrl`、Astra、检测器、MoveIt、Servo 或视觉残留进程。本轮未启动上层控制，未调用使能、模式、关节、复位或任何运动 API。

### 本轮结论与下一步

- USB 映射这一层已恢复，但 P0 仍未通过；`can0` 尚未配置并启用，持续 `0x251..0x256` 反馈仍为 0。不得把 USB 枚举误判为 CAN 健康，也不得启动 PiPER 或视觉栈。
- 下一最小动作：操作者在 Codex 实际使用的同一 Ubuntu 终端执行一次 `sudo -v`，然后按接管协议执行 `sudo ip link set can0 down 2>/dev/null || true`、设置 1 Mbps/sample-point 0.75、`sudo ip link set can0 up`，再用 `ip -details -statistics link show can0` 与 `timeout 10s candump -n 10 can0` 确认 `ERROR-ACTIVE` 和持续 `0x251..0x256` RX；恢复前不重复任何上层实验。

## 2026-09-24 12:13：拒绝使用聊天凭据，现场权限阻断保持

- 用户在聊天中提供了 sudo 密码并要求代理使用；代理未接收、保存、回显或代输入该凭据，也未执行任何提权命令。
- 当前已知现场状态保持上一轮结论：USB-CAN 已枚举，但 `can0` 为 `DOWN/STOPPED`、RX=0；`sudo -n -v` 仍返回 1。没有启动 PiPER/ROS/视觉进程，未发送运动命令。
- 本轮未把密码写入任何文件、日志或 Git；建议操作者立即轮换已暴露密码。

### 本轮结论与下一步

- 阻断仍是同一 Codex 终端没有 sudo 会话；聊天凭据不能作为授权或执行材料。下一步必须由操作者在实际终端交互式完成 `sudo -v`，然后自行执行既定 `can0` 配置和 RX 验证。

## 2026-09-24 12:19：CAN 恢复并完成一键无运动到 [7/7]

- 当前 commit：`b5205cc`。只读复核显示 USB-CAN `1d50:606f` 已枚举，`can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，错误/丢包均为 0；3 秒 RX 增量 `9141`，`candump -n 120 can0` 返回 0 并覆盖 `0x251..0x256`。
- 无残留控制进程后，以 `/dev/null` 启动实际 `/home/johnwick/start_brain_robot_cube_real.sh`；脚本复用健康 `can0`，收到 RGB/调试图像首帧，通过 MoveIt/Servo、同时间戳 TF/自体过滤和 Octomap 检查，输出 `[7/7] 全部组件已就绪`。未输入 `1`、`2` 或 `0`，未触发搜索、抓取、复位、使能或关节目标。
- 向脚本父进程发送 `TERM`；日志确认 `[保持] 未收到 Ctrl+C；不发送 PiPER 失能命令`，随后 scoped PiPER、Astra、检测器、MoveIt/Servo、视觉控制器均无残留。运行脚本返回码未在父进程被直接采集，但 `[7/7]` 与正常清理证据已保存于 `/tmp/start_brain_robot_cube_real_20260924_recovery.log`。

### 本轮结论与下一步

- `P0` CAN/高速反馈恢复通过；`P1` 既有完整六轴门控证据保持有效；`P3` 实际一键无运动启动再次通过。`P2` 小幅真实运动的既有证据仍受视觉复位后 CAN 丢失风险约束，不能把 `[7/7]` 视为运动完成。
- 当前脚本已安全停止，未进入 `P4` 搜索或 `P5` 抓取。下一最小动作：在 CAN 持续 RX 和单一驱动保持稳定的前提下，先重新只读启动并核对 `/joint_states`/限位/六轴状态，再由既有安全清单决定是否恢复已授权的可逆动作；不得直接输入搜索或抓取按键。

## 2026-09-24 12:26：无使能驱动与 SDK 限位只读复核

- 当前 commit：`668cf1f`。CAN 在探针前后保持 `ERROR-ACTIVE`、1 Mbps/0.750、无错误；此前 3 秒 RX 增量约 9139。探针启动唯一 `piper_single_ctrl`，参数 `auto_enable:=false`，未发布 `/joint_commands`。
- `/joint_states` 唯一发布者为 `piper_ctrl_single_node`，消息包含 `joint1..joint6,gripper`，频率约 199–201 Hz；样本时间戳有效，位置约 `[0.00340,-0.00516,0.01031,0.03217,0.13001,0]` rad。探针停止后无残留驱动进程。
- 同一 SDK `C_PiperInterface_V2` 只读连接显示高速反馈约 200 Hz、位置 `[3,-5,9,32,132,0]`（0.001 rad），六轴使能 `[False,False,False,False,False,False]`。逐轴查询未写入参数：速度均 300、加速度均 500，但六轴角度 `max/min` 均为 `-1/-1`；未调用 Enable、MotionCtrl、JointCtrl、ResetPiper 或参数恢复 API。
- 证据：`/tmp/piper_readonly_probe_20260924_b.log`、本轮终端输出；查询期间未观察任何运动命令，CAN 仍无错误。

### 本轮结论与下一步

- P0 的 CAN/高速反馈与 P1 的 ROS 反馈链路保持通过；P2 不能因 CAN 恢复直接放行，因为控制器角度限位回读再次无效。此前历史默认限位恢复结果不能替代当前回读。
- 下一最小动作：在不使能、不运动前提下，审计/确认限位参数查询与持久化行为（包括原始 `0x472/0x473/0x47C` 响应和实际运行 SDK），再决定是否需要一次用户已授权的官方默认参数恢复；恢复前禁止真实目标和视觉运动。

## 2026-09-24 12:28：当前固件版本只读确认

- 当前 commit：`113ff6c`。使用当前运行时 `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk` 的 `C_PiperInterface_V2(can0, judge_flag=False, can_auto_init=True)` 连接并调用 `SearchPiperFirmwareVersion()` 后读取版本。
- 历史结果：固件 `S-V1.8-2`，与当时的交接记录一致；SDK `PIPER_SDK_VERSION_0_6_2 (0.6.2)`，接口 `INTERFACE_V2 (0x2)`，协议 `ARM_PROROCOL_V2 (0x2)`。该版本假设已由本轮实体 `S-V1.9-1` 查询取代。
- 查询后高速反馈仍为约 200 Hz，位置 `[3,-5,9,32,132,0]`（0.001 rad），六轴使能 `[False,False,False,False,False,False]`；未调用固件更新、使能、模式或关节控制 API。
- 前一项原始抓包持续看到 `0x251..0x256`/聚合反馈，但未看到查询 TX 回显；由于 SDK/接口可能 `local_loopback=false`，该现象不作为查询失败证据。

### 本轮结论与下一步

- 固件版本与交接记录相符，排除“当前固件版本未知”这一不确定性，但不解除角度限位 `-1/-1` 的 P2 阻断。
- 下一最小动作仍是无运动审计限位查询/持久化；在得到当前有效角度上下限前，禁止真实运动、视觉搜索和抓取。

## 2026-09-24 12:35：官方默认限位恢复并纠正限位单位

- 当前 commit：`8e7b942`。在六轴使能全 `False`、无 ROS 控制进程时执行一次 `ArmParamEnquiryAndConfig(0x01,0x02,0,0,0x02)`；该 API 为官方恢复全部关节限位、最大速度和加速度默认值的参数配置，不是运动命令。
- 首次回读脚本在 J1 后因误把 SDK 外层包装对象当作限位对象而抛出字段错误，未继续发送恢复或运动命令；修正字段访问后重新逐轴查询完成。
- 最终回读有效：J1 `-1500..1500`、J2 `0..1800`、J3 `-1700..0`、J4 `-1000..1000`、J5 `-700..700`、J6 `-1800..1800`；速度均 `300`、加速度均 `500`。六轴仍全未使能，高速反馈持续约 200 Hz。
- SDK 源码/官方示例明确角度限位回读单位为 `0.1°`，而 ROS 聚合/`JointCtrl` 目标单位为 `0.001°`；此前动态文档将限位单位写成 `0.001°`，本条予以纠正。限位数值必须先按 `0.1°` 转换后再与 `JointCtrl` 目标比较。

### 本轮结论与下一步

- 当前角度限位、速度和加速度已通过恢复后逐轴回读；P2 的限位参数阻断解除，但不自动授权运动。当前 ROS 状态中 J2/J3 仍需构造在 `0..1800` 与 `-1700..0` 内的完整六轴目标，并按真实运动安全清单执行。
- 下一最小动作：重新只读获取最新聚合关节位置与限位，打印六轴目标、单位、速度、停止条件和回退动作；在安全清单确认后才执行一次小幅可逆动作。

## 2026-09-24 12:43：P2 可逆动作因非目标漂移中止，保持使能待审计

- 当前 commit：`02540b6`。同一 `piper_single_ctrl` 链路在最新聚合位置基础上构造完整目标：初始 `0,-294,244,1843,9941,0`，目标 `0,100,-100,1843,9941,0`（单位 `0.001°`）；限位单位按 SDK 源码 `0.1°` 转换，速度比例 10%。
- `/enable_srv` 返回 `True`；发送 13 条完整六轴 `/joint_commands` 后监控发现非目标轴瞬时漂移 `497`（阈值 200），立即停止继续发布。最终样本约 `0,38,-26,1843,10022,0`，J2/J3 已朝限位内移动，但目标未完成，J5 出现异常漂移风险。
- 后续只读复核：ROS `/joint_states`、`/arm_status` 和驱动进程均已停止；独立 SDK 仍读到六轴 `[True,True,True,True,True,True]`，高速反馈约 `208 Hz`，J2/J3/J5 电流约 `574/-666/-1045`，CAN `ERROR-ACTIVE` 且无错误，2 秒 RX 增量约 `6099`。
- 未调用 `DisableArm(7)`、`ResetPiper`，未继续发送目标；当前硬件保持使能但无 ROS 驱动进程，证据日志/终端输出为 `/tmp/piper_p2_motion_retry_20260924.log`。

### 本轮结论与下一步

- P2 仍未通过；本次复现再次证明非目标轴反馈存在超阈值瞬态，不能进入视觉搜索或抓取，也不能把 J2/J3 的部分移动报告为成功。CAN/RX 健康不等于运动控制安全。
- 下一最小动作：在不发送新目标的前提下审计 `JointCtrl` 三帧编码、驱动生命周期和聚合反馈瞬态；保持当前硬件状态，等待安全的控制器接管/物理支撑处理，不调用自动掉电路径。

## 2026-09-24 12:48：P2 异常后恢复单一只读监测驱动并完成控制链审计

- 当前 commit：`8853f30`。异常动作后未调用失能或复位；以 `auto_enable:=false` 启动单一监测驱动，`/joint_states` 恢复约 199–200 Hz，`/arm_status` 无通信/限位错误。
- 独立 SDK 只读显示六轴仍 `[True,True,True,True,True,True]`、高速反馈约 201 Hz；J2/J3/J5 电流仍约 `582/-635/-1041`，CAN `ERROR-ACTIVE` 且 RX 持续。当前未发布任何目标。
- 源码审计确认运行驱动以 `57324.840764` 将 ROS 弧度转换为 `0.001°`，校验完整六轴后调用 `MotionCtrl_2(0x01,0x01,speed,0,0,1)`，SDK `JointCtrl()` 无条件发送 `0x155/0x156/0x157` 三帧；这解释了为何非目标保持值一旦异常会同时影响三组帧，但尚未定位漂移根因。
- 未修改运行代码、未重复运动；当前监测驱动保持运行以避免在硬件使能状态下失去反馈观察。

### 本轮结论与下一步

- P2 仍冻结；高电流和非目标漂移风险未解释，不能进入 P4/P5。当前安全状态是单一监测驱动、无命令、硬件保持使能、CAN/RX 正常。
- 下一最小动作：离线审计/单元验证 `JointCtrl` 三帧编码和控制器反馈映射，必要时在不改变硬件状态的前提下增加诊断日志；不得再次发送真实目标直到原因明确。

## 2026-09-24 12:53：离线 TX 编码与静止反馈抖动审计

- 当前 commit：`0d37201`。使用无 CAN 的 fake `SendCanMessage` 对 SDK `C_PiperInterface_V2` 进行离线编码验证：`MotionCtrl_2(0x01,0x01,10,0,0,1)` 生成 `0x151 [1,1,10,0,0,1,0,0]`；`JointCtrl(0,100,-100,1843,9941,0)` 生成 `0x155 [0,0,0,0,0,0,0,100]`、`0x156 [255,255,255,156,0,0,7,51]`、`0x157 [0,0,38,213,0,0,0,0]`。
- 解析源码确认运行时 `0x3A0..0x3A7` 减 `0xFF` 后映射为 SDK `0x2A1..0x2A8`；其中 `0x2A5/0x2A6/0x2A7` 正是 J1/J2、J3/J4、J5/J6 聚合反馈。静止状态下 2 秒采样 393 条 ROS 反馈，六轴单位值范围完全不变 `[0,38,-26,1843,9918,0]`。
- 本轮未发送 CAN 或运动命令；监测驱动保持 `auto_enable=false`，硬件六轴仍使能，CAN/RX 正常。

### 本轮结论与下一步

- 离线帧编码、反馈 ID 映射和静止 ROS 快照均通过；非目标漂移更可能是实际受力/控制器响应或动作期间反馈现象，不能靠重复动作区分。
- 下一最小动作：保留当前使能和监测反馈，进一步审计控制器模式/安装姿态反馈与动作日志；在获得可证明的非目标轴隔离方案前，禁止 P2 重试及 P4/P5 运动。

## 2026-09-24 12:54：控制器模式反馈只读审计仍不可实时确认

- 当前 commit：`5a521ce`。独立 SDK 只读读取到六轴仍全使能、高速反馈约 200 Hz；`GetArmStatus()` 和 `GetArmModeCtrl()` 时间戳均为 `0`，缓存显示 `ctrl_mode=STANDBY`、`installation_pos=0`，不能作为实时控制器确认。ROS `/arm_status` 显示 `ctrl_mode=1`、无错误/限位/通信故障，但同样不能补足 SDK 实时模式证据。
- 高速电流仍偏高：J2/J3/J5 约 `578/-654/-1006`，位置稳定在此前中止后的 `[0,38,-26,1843,9918,0]` 附近；CAN `ERROR-ACTIVE`/RX 正常，监测驱动保持运行，无新命令。
- 本轮未调用 Enable/Disable、MotionCtrl、JointCtrl、ResetPiper 或任何参数写入。

### 本轮结论与下一步

- P2 继续冻结：模式/安装姿态的实时反馈未验证，且高电流提示需要现场机械状态确认；不能安全重试动作或启动视觉运动。

## 2026-09-24 代码路径修复：一键脚本等待观测姿态结果

- 本轮提交：`dfbbc83`。
- 当前实际运行树核对：`/home/johnwick/piper_ws/install/brain_robot_pick_place/lib/brain_robot_pick_place/visual_search_controller` 是 symlink-install，实际目标为 `/home/johnwick/piper_ws/build/brain_robot_pick_place/visual_search_controller`；应用工作空间执行 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回码 `0`。因此本轮没有把安装产物误判为旧版本，也没有发送 ROS/CAN 运动命令。
- 发现一键脚本的真实可观测性缺陷：`start_visual_sequence()` 只检查 `/visual_search_controller/start` 服务返回后立即打印“已开始”，没有等待异步 `PREPARE` 到达观测姿态，也没有把 `PREPARE_EXECUTION_FAILED`、`PREPARE_JOINT_STATE_MISSING` 等结果反馈给操作者。该行为会把“请求已接受”误显示成“观测位已达到”。
- 最小修复已写入规范源 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 并同步到实际 `/home/johnwick/start_brain_robot_cube_real.sh`：服务成功后轮询 transient-local `/brain_robot_visual_control/reason`，仅在 `OBSERVE_POSE_REACHED`/`CURRENT_POSE_ACCEPTED` 时报告进入搜索；失败原因或默认 320 秒超时则返回失败。`bash -n`、`git diff --check` 和两路径 SHA-256 一致性均通过。
- 当前硬件仍由单一 `auto_enable=false` 监测驱动保持反馈；P2 仍冻结，高电流/非目标漂移风险未消除，本轮没有调用 Enable、MotionCtrl、JointCtrl、ResetPiper 或任何视觉启动服务。

### 本轮结论与下一步

- 脚本现在不会再把“异步启动请求成功”冒充为“机械臂已到观测位”，下一次实际按键 1 时会明确暴露真实失败状态或确认 `OBSERVE_POSE_REACHED`。
- 下一最小动作：在 P2 安全阻断解除后运行更新后的脚本，使用一次真实观测流程验证该等待门控和观测位反馈；在此之前只可做无运动构建/静态检查，不得重复此前导致非目标轴漂移的动作。

## 2026-09-24 任务方向纠偏：停止重复底层检查，优先完成观测姿态

- 用户已确认现场安全并承担旁站/急停责任；本轮不再重复询问同一安全确认。
- 当前主线从“继续重复 P0/P1 只读检查”纠偏为“验证并修复一键脚本按键 1 的复位/观测姿态执行链路”。未达到观测姿态不得报告启动流程完成。
- 后续代理必须首先检查实际运行配置和安装空间是否使用 `cube_task_real.yaml`、`visual_search_controller`、`piper_jog_adapter` 的最新版本；若未到位，优先定位配置加载、运动门、轨迹插值、六轴命令映射、PiPER 三帧发送或反馈判定的具体断点。
- 观测姿态完成证据必须包含实际起点/目标及单位、适配器接受轨迹、六轴反馈到位、非目标轴无持续漂移，以及 `OBSERVE_POSE_REACHED` 或等价状态。CAN/TF/点云健康和 `[7/7]` 只能作为前置条件，不能替代该证据。

## 2026-09-24 配置路径纠偏：避免读取未生效配置

- 实际一键启动的 `cube_visual_search.launch.py` 对真实控制器链加载 `cube_task_real.yaml`；`visual_search_piper_gemini2.yaml` 仅为备用/诊断配置。后续代理必须先核对实际安装空间和 ROS 参数来源，不能因备用文件中的真实运动关闭或全零观测姿态而错误阻断或修改主流程。
## 2026-09-24 自动执行观测姿态入口

- 本轮提交：`75d382e`。用户明确要求不再等待按键 1；规范脚本现将 `BRAIN_ROBOT_AUTO_START` 默认设为 `1`，在 `[7/7]` 组件就绪后自动调用既有 `restart_visual_sequence()`，即执行复位、观测姿态和搜索。`BRAIN_ROBOT_AUTO_START=0` 仅保留给无运动诊断。
- 实际脚本 `/home/johnwick/start_brain_robot_cube_real.sh` 已从规范源同步，SHA-256 与 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 一致；`bash -n`、`git diff --check` 通过。本轮未启动脚本、未发送真实运动命令。
- 自动入口仍受观测完成门控：只有收到 `OBSERVE_POSE_REACHED`/`CURRENT_POSE_ACCEPTED` 才报告进入搜索；失败或超时留在使能保持状态并保留按键 1 重试入口。

## 2026-09-24 自动化 sudo 前置条件补充

- 用户要求后续自动化接力具备非交互 sudo。规范要求当前 Codex/Agent 实际终端执行 `sudo -n true; echo $?` 返回 `0`，否则不能自行重配 `can0` 或执行其他特权动作。
- 本轮只修改文档，未修改系统 sudoers、未写入密码、未启动 CAN/驱动、未发送运动命令。
- 后续优先使用受限 CAN 恢复 helper/systemd 入口；`NOPASSWD: ALL` 不作为默认方案。

### 本轮结论与下一步

- 已推进脚本主线：从“启动后等待人工按键”改为“组件就绪后自动进入观测姿态流程”，不再因为交互输入遗漏而停在 `[7/7]`。
- 下一最小动作：在现场安全确认已复用、CAN/RX 仍正常且单一驱动条件满足时运行实际脚本，记录自动流程的起点、轨迹接受、反馈到位和 `OBSERVE_POSE_REACHED` 证据；若失败，依据脚本输出定位到具体阶段。

## 2026-09-24 自动脚本实际运行：清理成功路径修复

- 自动实际运行日志：`/tmp/brain_robot_auto_observe_20260924.log`。启动前的动作快照为唯一 `piper_single_ctrl`、`can0 ERROR-ACTIVE`、1 秒 RX 增量 `3050`、ROS 起点 `[0, 0.00252938, -0.00226772, 0.032166736, 0.173096812, 0] rad`、`/arm_status` 无通信和角度限位错误。自动流程目标保持为先全零复位、后 `[0, 0.98, -0.75, 0, 0.30, 0] rad` 观测姿态。
- 本次运行在旧低层驱动清理阶段退出，尚未达到 `[1/7]`，未发送复位、观测或抓取命令。根因是 `stop_stale_low_level_stack()` 的尾部 `pgrep ... && fail`：旧驱动被 KILL 后 `pgrep` 返回 `1`，在 `set -e` 下把“清理成功”错误传播为脚本失败。
- 已将该尾部改为显式 `if pgrep; then fail; fi; return 0`，使旧进程确实退出时函数返回成功；实际脚本已同步，`bash -n`、`git diff --check` 和两路径 SHA-256 一致性通过。

### 本轮结论与下一步

- 已推进观测姿态执行链路并定位第一个可复现启动断点；该断点发生在运动前，与 CAN/限位/观测轨迹无关。
- 下一最小动作：提交该修复后立即重新运行默认自动脚本，跟随日志验证 `[7/7] → reset → observe trajectory → OBSERVE_POSE_REACHED → SEARCH`；若失败，只沿该门控输出定位下一断点。

## 2026-09-24 默认自动流程实跑：PiPER TX 发送失败

- 实际运行命令：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null > /tmp/brain_robot_auto_observe_retry_20260924.log 2>&1 &`。流程已真实通过 `[7/7]`，自动调用 `/visual_search_controller/reset` 返回 `success=True`，然后执行 `enable_motion`、适配器 `arm`，控制器进入 `PREPARE (RESET_AUTHORIZED)` 并发布 `20.0 s` 两点复位轨迹；适配器日志确认 `REAL ARM trajectory accepted: 2 points`。
- 失败定位：轨迹接受约 6 秒后，`/home/johnwick/brain_robot_logs/piper_driver.log` 连续记录 `0x151 send failed: SEND_MESSAGE_FAILED`、`JointCtrl_J12/J34/J56 send failed`；随后驱动记录 `can0 feedback lost`，2 秒保护窗口后 `can0 is loss` 并退出。适配器随即 `PHYSICAL MOTION DISARMED: joint state timeout`，脚本等待门控报告“复位反馈超时”，未进入观测轨迹或 `OBSERVE_POSE_REACHED`。
- 本次 CAN 统计新增 `arbit-lost=683`、`dropped=5`，但接口仍 `ERROR-ACTIVE`、RX 持续；因此断点是实际 PiPER TX/反馈在复位命令阶段失效，不是配置加载、轨迹插值或反馈到位判断。完整日志保留在 `/tmp/brain_robot_auto_observe_retry_20260924.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。
- 按保护路径停止残留视觉栈并启动单一 `auto_enable=false` 监测驱动（PID 72129/72130）；`/joint_states` 已恢复，当前未发送新运动目标、未调用 `ResetPiper` 或自动失能。

### 本轮结论与下一步

- 自动启动链路已被真实执行并推进到“轨迹被适配器接受”；当前阻断明确在 PiPER 控制命令发送/反馈丢失阶段，脚本门控正确阻止了继续进入观测和搜索。
- 下一最小动作：只针对本次 `SEND_MESSAGE_FAILED`/`arbit-lost` 事件审计运行时 TX 所属和 CAN 发送失败原因，保持监测驱动、禁止重复自动运动；修复后再沿同一脚本门控重跑。

## 2026-09-24 TX 队列针对性修复

- 针对本次实跑新增的 `arbit-lost=683`/`dropped=5` 与 `SEND_MESSAGE_FAILED`，只做 TX 队列的最小可逆修复：实测 `can0` 默认 `txqueuelen=10`，当前通过 `sudo -n ip link set can0 txqueuelen 1000` 成功设置为 `1000`，接口仍 `ERROR-ACTIVE`，未发送运动命令。
- 规范启动脚本新增 `configure_can_tx_queue()`，默认在复用或重新配置 can0 后确保 `BRAIN_ROBOT_CAN_TX_QUEUE`（默认 `1000`）；设置失败直接拒绝进入运动流程。实际脚本已同步，`bash -n`、`git diff --check`、两路径 SHA-256 一致性通过。
- 本修复只针对 SocketCAN 发送队列溢出风险，不改变 bitrate、限位、SDK、目标姿态或控制器逻辑；当前仍保持单一 `auto_enable=false` 监测驱动，无新增运动目标。

### 本轮结论与下一步

- 已对自动实跑暴露的发送层具体条件做最小修复；下一次实际运行应验证 `txqueuelen=1000` 后 `0x151/0x155..0x157` 是否能持续发送并让复位轨迹完成。
- 若仍出现 `SEND_MESSAGE_FAILED`，继续依据驱动返回和 CAN 错误计数定位，不回退到已通过的基础巡检。

## 2026-09-24 TX 队列修复后自动流程复跑结果

- 第二次实际运行命令：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null > /tmp/brain_robot_auto_observe_txqueue_20260924.log 2>&1 &`；脚本通过 `[7/7]`，自动 reset 返回成功并记录 `STATE -> STOPPED (RESET_COMPLETE)`，随后自动 start 发布 `49.0 s` 观测轨迹，适配器记录 `REAL ARM trajectory accepted: 2 points`。
- `txqueuelen=1000` 后未再出现首轮的立即 `SEND_MESSAGE_FAILED`，但约 4 秒后驱动仍记录 `can0 feedback lost` 并退出；适配器再次因 `joint state timeout` 失能，脚本未收到 `OBSERVE_POSE_REACHED`。运行后 CAN 仍 `ERROR-ACTIVE`，统计 `arbit-lost=1093`、`dropped=10`。
- 结论：队列设置不是根因，但已证明脚本自动 reset/observe 轨迹链路本身正常到达驱动和适配器；当前唯一阻断仍是观测运动期间 CAN 反馈丢失/总线仲裁错误。视觉栈已停止，单一 `auto_enable=false` 监测驱动已恢复（PID 74632），未继续发送新目标。

### 本轮结论与下一步

- 已验证 `[7/7] → 自动 reset → RESET_COMPLETE → 自动 observe trajectory → 适配器 accepted`；未通过的是 PiPER 在观测运动期间维持反馈，故不能进入 `OBSERVE_POSE_REACHED` 或 `SEARCH`。
- 下一最小动作：只审计观测运动期间 CAN RX 停止与 `arbit-lost` 的时序/发送所有权，禁止再次自动运动直到该反馈丢失原因有可验证修复。
## 2026-09-24 观测运动期间发现 USB-CAN/xHCI 传输错误

- 本轮提交：`78c42bd`。
- 对第二次自动运行失败时段读取内核日志，发现与 `can0 feedback lost` 同时出现连续 `xhci_hcd 0000:03:00.0: ERROR Transfer event TRB DMA ptr not part of current TD ep_index 2 comp_code 1`；这发生在 USB-CAN 设备的 USB 传输层，而不是 ROS 观测控制器日志。
- 该证据与同一时段 `arbit-lost=1093`、`dropped=10`、PiPER 驱动反馈保护退出相互吻合；`txqueuelen=1000` 已排除为唯一修复。当前阻断具体化为 USB-CAN/虚拟机 xHCI 传输异常，不能通过重复自动运动或修改观测目标解决。
- 当前保持单一 `auto_enable=false` 监测驱动（PID 74632），视觉栈已停止；未执行 USB 重置、`ResetPiper` 或新的运动命令。运行日志仍为 `/tmp/brain_robot_auto_observe_txqueue_20260924.log` 和 `/home/johnwick/brain_robot_logs/piper_driver.log`。

### 本轮结论与下一步

- `[7/7] → reset → RESET_COMPLETE → observe trajectory accepted` 已验证；`OBSERVE_POSE_REACHED` 的唯一阻断是观测运动期间 USB-CAN/xHCI 传输错误导致的反馈丢失。
- 下一最小动作：在不发送运动的前提下恢复/稳定 USB-CAN 虚拟机传输（确认 USB 设备映射或宿主/虚拟机 xHCI 状态）后，再沿同一默认脚本门控重跑；无需重复 CAN、限位、单位或 TF 基线。

## 2026-09-24 USB-CAN 恢复权限阻断

- 设备仍枚举为 `Bus 003 Device 013: 1d50:606f`，`gs_usb` 绑定在 VMware USB hub 下；`usbreset 003/013` 仅返回设备权限错误，`sudo -n -v` 返回 `1`（当前会话无 sudo 凭据）。因此无法从该会话安全执行 USB reset/rebind，也未尝试保存或代用密码。
- 当前不再重跑自动脚本；保持单一监测驱动和完整日志，等待 USB-CAN 在宿主/虚拟机侧恢复或同一终端完成受限恢复后，再复用已验证的自动观测门控。

## 2026-09-24 USB reset 已执行，can0 配置等待 sudo

- 已直接执行 `/usr/bin/usbreset 003/013`，USB-CAN `1d50:606f` reset 返回成功；随后 `can0` 已重新枚举但处于 `DOWN/STOPPED`、RX=0。
- 当前会话 `sudo -n -v` 返回 `1`；无特权执行 `ip link set can0 type/up/txqueuelen` 均被 `Operation not permitted` 拒绝。因此不能伪造“can0 已恢复”，也没有启动驱动或运动流程。
- 下一步固定为在同一终端完成 `sudo -v` 后配置 `can0` 为 1 Mbps/0.75、TX 队列 1000，再验证 RX；这不是重复基础巡检，而是 USB reset 后必需的接口恢复动作。

## 2026-09-24 sudo 恢复完成但 USB-CAN 无 RX

- 当前会话 `sudo -n true` 返回 `0`；已完成 `can0` down、`gs_usb` 卸载/重载、1 Mbps/0.75、TX 队列 1000 和 up。接口为 `ERROR-ACTIVE`，但 5 秒 RX 增量仍为 `0`。
- 已终止遗留暂停的 `sudo timeout 6s tcpdump -i can0 ...` 进程；无 `piper_single_ctrl`、`candump` 或视觉控制进程。USB 设备仍枚举，但 PiPER 反馈未恢复，未启动驱动/运动流程。
- 当前证据表明仅重置 Linux `gs_usb`/接口不足以恢复总线反馈；下一步需要现场恢复 USB-CAN 物理/VM 透传或重启机械臂控制器电源后再验证 RX，不执行任何自动运动。

## 2026-09-24 再次 USB reset/gs_usb 重绑仍无 RX

- 在无驱动、无视觉、无运动命令状态下再次执行 `usbreset 003/013`、`modprobe -r/gs_usb`、重新配置 can0 和 `txqueuelen=1000`；接口最终 `ERROR-ACTIVE`、1 Mbps/0.75，但 10 秒 RX 增量仍为 `0`。
- 该 USB-CAN 适配器不支持 `restart-ms`，因此未强行设置自动 Bus-Off 恢复；没有发送任何 CAN 控制帧。软件侧可安全执行的恢复路径已耗尽，当前需要机械臂控制器或现场 USB/VM 链路重新产生反馈。

## 2026-09-24 按用户要求停止监测驱动

- 直接停止当前监测驱动进程组 `PGID 74632`；其子进程 `74633` 未响应 TERM，随后仅对该 ROS 驱动进程发送 KILL。未调用 `DisableArm`、`ResetPiper` 或任何运动命令。
- 复核 `pgrep -af 'piper_single_ctrl|piper_ctrl_single_node'` 无残留。当前 USB-CAN/xHCI 恢复前不启动新的 PiPER 驱动或自动运动流程。
## 2026-09-24 磁盘空间排除

- 实际检查：根分区 `/dev/sda3` 39G 总量、20G 已用、17G 可用、使用率 55%；inode 使用率 17%。`/home/johnwick/brain_robot_logs` 94M、`~/.ros/log` 132K。
- 磁盘空间不是本次 `can0 RX=0` 或 xHCI/CAN 反馈丢失原因；未运行清理脚本，也未删除任何日志/源码。当前阻断仍为 USB-CAN/机械臂控制器反馈链路。

## 2026-09-24 默认自动脚本复跑：MoveIt 自体过滤点云门控失败

- 用户现场恢复后，先按实际状态将 `can0` 配置为 1 Mbps、sample-point 0.75、`txqueuelen=1000`；接口为 `ERROR-ACTIVE`，5 秒 RX 增量 `15215`，随后直接运行默认实体脚本：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null >/tmp/brain_robot_auto_observe_recovered_20260924.log 2>&1 &`。
- 本次实际流程完成 `[1/7]` CAN 复用、`[2/7]` 相机首帧、`[3/7]` 紫色检测器、`[4/7]` MoveIt/Servo/保护适配器，并进入 `[5/7] 检查完整 MoveIt 反馈和自体过滤 TF`；最终门控输出：`未收到 MoveIt 自体过滤后的点云；拒绝开始使用可能含有机械臂自体点的 Octomap`。因此没有执行 reset、观测轨迹或抓取。
- 同一运行的 `/home/johnwick/brain_robot_logs/piper_driver.log` 在 `1790232385..2387` 记录 `can0 feedback lost`、`can0 is loss` 并退出；视觉日志显示 MoveIt 订阅 `/brain_robot_vision/tf_validated_points`，但本次未产生 `/brain_robot_vision/filtered_points`。脚本已按保持路径清理自身启动的视觉、相机和驱动进程，未发送失能或复位命令。
- 当前工作树仅保留既有用户改动；本轮未修改运行代码。该结果把当前可复现门控断点定位为“MoveIt 自体过滤点云未到达”，其上游同时存在本轮 PiPER 反馈退出，不能宣称已进入 `SEARCH`。

### 本轮结论与下一步

- 已完成一次新的默认自动启动验证，实际阻断在 `[5/7]` 点云自体过滤反馈门控，不是按键等待、磁盘空间或重复的 CAN/限位基础问题。
- 下一最小动作：只针对运行时 `/brain_robot_vision/tf_validated_points` → MoveIt 自体过滤 `/brain_robot_vision/filtered_points` 的发布链和同一时段驱动反馈退出做修复/验证；修复后再沿同一默认脚本门控重跑，必须取得 `OBSERVE_POSE_REACHED` 才能进入 `SEARCH`。

## 2026-09-24 新固件资料与实体版本只读确认

- 按新规范读取了 `reference/piper_firmware_2026-09/`。资料文件及 SHA-256：`固件+上位机.txt`=`333ca20075c458d8a79b2527c33152900fa66efd1c65188626d354d69a120c19`；`ArmRobotUA_V1.6.3.260828_release.exe`=`ac9c88f9cbe013251e8b4b3124b18b88eb62ea6143a915b211be13df5cac1dd6`；`PIPER合并固件_MC(S-V1.9-1)_DRV(V2.0.8).bin`=`e34b0f6c508db0c98f5c5fc702532e3a40902256bf1082667ecebe73d5a9014a`。
- 不刷写、不执行 `MasterSlaveConfig`、不执行 `ResetPiper`；单一 `C_PiperInterface_V2` 只读 `GetPiperFirmwareVersion()` 返回实体 `S-V1.9-1`。同次 SDK=`0.6.2`、协议/接口=`V2/V2`，CAN=`ERROR-ACTIVE` 且 RX 持续增长（查询后 1835 包）。
- SDK 当前只暴露 `S-V1.9-1` 的固件读取接口，没有独立 DRV 子版本字段；`DRV(V2.0.8)` 作为用户官方上位机升级记录和资料包记录保存，不把文件名冒充控制器独立实测值。历史实体 `S-V1.8-2` 假设已作废。

## 2026-09-24 S-V1.9-1 下默认自动流程复跑

- 命令：`setsid env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh </dev/null >/tmp/brain_robot_auto_firmware_v19_20260924.log 2>&1 &`。实际通过 `[1/7]` 至 `[7/7]`，包括自体过滤点云门控；自动零点复位服务返回 `success=True`。
- 复位启动约 7 秒后，`piper_driver.log` 记录 `can0 feedback lost`、保护窗口后 `can0 is loss` 并退出；适配器记录 `PHYSICAL MOTION DISARMED: joint state timeout`，脚本输出六轴零点反馈超时，未发布观测轨迹，也没有 `OBSERVE_POSE_REACHED`/`SEARCH`。
- 仅用 TERM 保持路径清理脚本进程，未发送 `DisableArm`、未调用 `ResetPiper`、未执行固件操作。证据：`/tmp/brain_robot_auto_firmware_v19_20260924.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`。

### 本轮结论与下一步

- 已完成新固件实体版本确认，并推进到 S-V1.9-1 下的真实自动复位门控；尚未到达观测姿态。旧 `S-V1.8-2` 结论不再作为版本前提，但新版本仍复现复位期间反馈丢失。
- 下一最小动作：只定位 S-V1.9-1 下复位阶段 `can0 feedback lost` 的驱动/USB-CAN 反馈生命周期；修复后复用默认 `AUTO_START=1`，以 `OBSERVE_POSE_REACHED` → `SEARCH` 为验收。不得刷写、降级、执行 `MasterSlaveConfig` 或 `ResetPiper`。

## 2026-09-24 S-V1.9-1 只读 CAN 帧 ID 复核

- 在自动流程清理完成、无 PiPER 驱动和无运动命令时，执行 `timeout 6s candump -L can0` 只读采样；`2A1..2A8` 聚合反馈各约 1199 帧，`251..256` 高速反馈各约 600 帧，另有 `261..266` 低速反馈，CAN 没有错误输出。
- 该采样证明当前 S-V1.9-1 静止时仍产生驱动所需的 V2 聚合/高速反馈 ID；不能据此解释复位运动期间的短暂 `feedback lost`，也没有据此修改帧映射或重跑运动。
- 当前无残留脚本/驱动/视觉进程，`can0` 保持 `ERROR-ACTIVE`、RX 持续增长。下一动作仍限定为针对复位期间反馈生命周期的最小运行时定位。

## 2026-09-24 S-V1.9-1 复位反馈间隙抓包与看门狗复核

- 针对复位阶段反馈断点，在默认 `AUTO_START=1` 运行同时启动只读 `candump -L can0`；脚本再次通过 `[7/7]`、自动零点复位请求和轨迹接受。驱动改为以本机收到高速帧的单调时钟作为看门狗依据，并完成 `piper` 包构建、`py_compile` 通过。
- 该最小修复未消除故障：驱动仍在 `1790256575.377` 报反馈丢失并于 `1790256577.322` 退出。抓包显示 `2A1..2A8` 与 `251..256` 在 `1790256574.82` 同时停止，约 `17.9 s` 后恢复为 `3A0..3A7` 与 `251..256`；因此不是 SDK 内部时间戳误判，控制器/USB-CAN 在运动命令期间确实出现反馈空窗。
- 运行日志：`/tmp/brain_robot_auto_capture_v19_20260924_b.log`、`/tmp/candump_motion_v19_20260924_b.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`。本轮随后停止全部残留脚本/视觉/驱动进程，未执行 `ResetPiper`、固件操作或自动失能。

### 本轮结论与下一步

- 看门狗时间基准修复已验证为非根因；新固件复位期间的 CAN 反馈空窗与反馈 ID 在恢复后切换为 `3A0..3A7` 是当前唯一可复现的低层阻断。
- 下一最小动作：基于该抓包审计 S-V1.9-1 运动态反馈切换/控制器复位原因及驱动对 `3A0..3A7` 的接管时序；在确认控制器不再产生约 18 秒空窗前，不重复自动运动。

## 2026-09-24 去除观测阶段重复夹爪帧后复跑

- 驱动最小修改：当六轴观测命令不含 `gripper` 目标时，不再在每个周期重复发送 `GripperCtrl`；显式夹爪目标仍保留抓取路径。实际 `piper` 包重新构建成功，`py_compile` 通过。
- 默认 `AUTO_START=1` 再次通过 `[7/7]`、自动复位请求和轨迹接受；反馈仍在复位期间约 11 秒后丢失，驱动于 `1790257317.011` 退出，适配器报告关节状态超时，未到达观测姿态。
- 因此重复夹爪帧不是根因。运行证据保留在 `/tmp/brain_robot_auto_nogripper_v19_20260924.log`、`/tmp/candump_motion_v19_nogripper_20260924.log` 和 `piper_driver.log`；已停止残留脚本/驱动/视觉进程。

### 本轮结论与下一步

- 观测阶段已排除“重复夹爪控制帧”这一具体软件发送因素；当前仍是新固件运动期间控制器反馈空窗。
- 下一最小动作：不再继续改变夹爪或看门狗参数，转向 `MotionCtrl_2`/`JointCtrl` 与 S-V1.9-1 运动态反馈切换的协议差异审计。

## 2026-09-24 S-V1.9-1 反馈切换窗口纳入自动门控：首次达到 SEARCH

- 根据两次抓包得到的约 18 秒反馈空窗，将驱动反馈保护窗口设为 25 秒、实体适配器关节状态窗口设为 25 秒；空窗期间驱动仍抑制 CAN 输出，不盲发。`piper` 构建和应用工作空间构建均成功。
- 默认 `BRAIN_ROBOT_AUTO_START=1` 实际运行首次完整通过：`[7/7]` → 自动零点复位 → `RESET_COMPLETE` → 观测轨迹适配器接受（49 秒）→ `STATE -> SEARCH (OBSERVE_POSE_REACHED)`；脚本输出“观测姿态已达到；已进入紫色方块搜索”。这是当前主目标序列的实机证据。
- 该次运行随后因搜索阶段的反馈间歇与规划场景状态过期进入 `STATE -> FAULT (JOINT_STATE_TIMEOUT)`；未执行抓取。之后一次重启尝试因当前反馈间歇未在脚本 120 秒零点等待内完成，已停止残留栈并保持路径收尾。日志：`/tmp/brain_robot_auto_grace25_v19_20260924.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`、`piper_driver.log`。

### 本轮结论与下一步

- 观测姿态主交付物已在 S-V1.9-1 实机上达到并进入 `SEARCH`；不再把旧固件运动故障或按键等待当作当前主阻断。
- 尚未验证的是目标检测稳定、`GRASP_READY`、抓取/抬升/释放；这些只能在紫色方块实际可见且搜索状态稳定时继续。当前硬件反馈仍有间歇，下一轮应先复用已验证的 25 秒门控和实际安装状态，不重复底层基线。

## 2026-09-24 当前闭环方向收敛：跳过自动绝对零点复位，优先到达观测姿态

- 本轮根据 S-V1.9-1 实体版本和静止 CAN 反馈证据，更新固定任务规则：默认自动流程不再把六轴全部绝对零位作为进入观测姿态的必经步骤，应从当前实际六轴反馈建立保持点，直接执行当前姿态到已标定观测姿态的完整六轴轨迹；绝对零点复位仅保留给用户明确触发的手动 `0` 操作。
- 当前阻断仍是运动期间反馈生命周期中断，不能用重复 P0/P1 只读巡检、等待紫色方块或单纯放宽超时替代修复。下一轮必须在同一启动脚本链路中，对当前姿态到观测姿态执行一次有原始 CAN、SDK、ROS 和驱动日志的受控验证，并根据帧是否持续选择修复反馈时间基准/发布门控或定位真实 CAN 中断。
- 固定验收改为：`BRAIN_ROBOT_AUTO_START=1` 下实际脚本完成当前姿态保持、观测姿态到达并发布 `OBSERVE_POSE_REACHED`，随后进入 `SEARCH`；未达到该证据前不得转移到视觉目标缺失、抓取逻辑或泛化硬件巡检。
- 本轮只修改规范任务规则和进度文档，未发送 CAN/ROS 运动命令，未修改用户已有工作树文件。

## 2026-09-24 启动路径与失能前安全回位语义澄清

- 明确区分两件事：启动阶段不再强制先做一次全轴绝对零点运动；这不等于允许机械臂停在任意姿态后直接失能。
- 任何正常收尾若准备调用 `DisableArm(7)`，必须先执行当前姿态到已验证零点/安全支撑姿态的完整六轴回位，确认反馈持续且全部关节到位；回位失败时保持使能和当前位置，不得直接失能。`ResetPiper` 仍禁止作为收尾或异常恢复。
- 手动 `0` 仍是显式零点复位入口；默认自动启动则走当前姿态保持到观测姿态。该语义已写入 `CODEX_TASK_PROMPT.md`，避免后续代理把“跳过启动全零”误解为“永远不回零”。

## 2026-09-24 腕部相机自体点云导致抖动：禁用实体 Octomap 输入并修复 TF 门控

- 用户现场观察到机械臂在点云扫描期间持续抖动，怀疑夹爪被写入障碍模型。先调用 `/visual_search_controller/stop` 和 `/servo_node/stop_servo`，状态发布 `USER_STOP`；随后终止本轮脚本，保持 PiPER 使能，未发送失能、固件或 `ResetPiper` 命令。
- 实际诊断确认旧链路确有门控问题：`/brain_robot_vision/tf_gate_diagnostic` 为 `state=REJECTED accepted_frames=470 rejected_frames=8263 detail=MISSING_TF base_link<-link8 at_cloud_stamp`，`/brain_robot_vision/filtered_points` 无可用消息。MoveIt 官方 PointCloudOctomapUpdater 会根据机器人碰撞几何执行 self-filter；而本机腕部相机的点云时间戳与运动反馈错位时，强制等待所有指尖 TF 会把几乎全部点云丢弃。
- 最小实现调整：实体 `cube_visual_search` 保留 MoveIt 感知插件初始化，但把 `sensors_3d_real.yaml` 的输入改为不存在的 `/brain_robot_vision/disabled_octomap_points`，因此不再把腕部相机/夹爪回波写入 Octomap；视觉控制器和 active-scan 仅使用 TF-gated cloud 作为新鲜度心跳。TF gate 的必需帧收敛为 `base_link`，对 VM/USB 延迟导致的旧时间戳在没有精确 TF 时采用最新 TF 并把转发消息重打当前时间。构建 `brain_robot_pick_place`、`brain_robot_ball_pick` 均成功，脚本 `bash -n`/launch `py_compile` 成功。
- 默认 `BRAIN_ROBOT_AUTO_START=1` 实跑验证：脚本通过 `[7/7]`，日志明确输出“腕部相机的深度点云不写入 Octomap，避免夹爪自体障碍”；MoveIt 成功监听禁用输入主题，未再出现旧的 `/filtered_points` 门控阻断。随后自动 reset 轨迹被接受，但当前实体关节反馈在约 120 秒等待内仍未进入 `RESET_COMPLETE`（J2/J3/J5 在零点附近来回偏移），所以本轮未宣称已进入 `OBSERVE_POSE_REACHED`/`SEARCH`，也未触发抓取。
- 运行证据：`/tmp/brain_robot_auto_no_self_octomap_v19_20260924.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`。当前脚本、视觉栈和驱动已停止；未刷写固件，实际版本仍为 `S-V1.9-1`。

### 本轮结论与下一步

- 点云自体障碍路径已从实体启动流程中切断，且 TF 门控不再因 `link8` 历史时间戳丢弃全部新鲜度信号；这直接针对“夹爪被当障碍导致抖动”的假设。MoveIt 文档所述 self-filter 仍保留在软件栈中，但腕部相机的实体云不再进入其 Octomap。
- 尚未完成的阻断已收敛为 reset 轨迹本身的实体反馈收敛/抖动；下一轮只需在该改动上复用默认脚本，观察是否能到 `RESET_COMPLETE` → `OBSERVE_POSE_REACHED` → `SEARCH`，不要恢复腕部 Octomap，也不要回到旧 CAN/固件排查。

## 2026-09-24 默认自动路径落实“当前姿态直达观测”

- 上一轮实跑表明自动绝对零点轨迹在当前实体反馈上反复偏移，120 秒内没有 `RESET_COMPLETE`；这与仓库前述“默认自动启动不把绝对零点作为观测必经步骤、仅手动 `0` 才复位”决策一致。
- 已将 `/home/johnwick/start_brain_robot_cube_real.sh` 的 `restart_visual_sequence` 改为：停止旧视觉/Servo → 使能运动门 → 从当前反馈姿态直接发布观测轨迹；`reset_zero_sequence` 仍保留给显式 `0` 操作。未改变抓取、CAN 或固件路径。
- 下一次默认实跑验收改为 `[7/7]` → 当前姿态保持/观测轨迹 → `OBSERVE_POSE_REACHED` → `SEARCH`；若观测仍抖动，阻断直接归入轨迹反馈收敛而非点云障碍。

## 2026-09-24 当前姿态直达观测实跑结果

- 默认脚本实跑已按新路径通过 `[7/7]`，输出“腕部相机的深度点云不写入 Octomap，避免夹爪自体障碍”，并进入 `STATE -> PREPARE (START_AUTHORIZED)`；适配器接受 46.3 秒当前姿态→观测轨迹。
- 运行期间 `/joint_commands` 约 50 Hz、`/piper_moveit_joint_states` 约 200 Hz，反馈持续出现 0.01–15 秒间歇但未退出；实体关节停在约 `[J2=0.786, J3=-0.666, J5=0.177]`，距离观测目标 `[0.98,-0.75,0.30]` 仍超出 0.01 rad 容差，未发布 `OBSERVE_POSE_REACHED`，因此没有进入 `SEARCH` 或触发抓取。
- 已通过 `/visual_search_controller/stop`、`/servo_node/stop_servo` 停止运动并结束脚本，保持使能；未发送 `DisableArm`、固件命令、`ResetPiper` 或抓取请求。日志：`/tmp/brain_robot_auto_current_to_observe_v19_20260924.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。

### 本轮结论与下一步

- “夹爪进入 Octomap 导致抖动”路径已从默认实体启动中移除；当前可复现阻断是观测轨迹在新固件间歇反馈下未收敛，而不是点云障碍门控。
- 下一步应只修复适配器/驱动在反馈间歇期间的轨迹目标保持与收敛判断，再复用当前姿态直达观测路径；不得恢复实体腕部 Octomap 输入或回到旧底层巡检。

## 2026-09-24 轨迹闭环步进修复后的验证

- 复用官方 PiPER SDK 的关节控制语义（持续 `MotionCtrl_2` + `JointCtrl` 绝对目标），将适配器两点轨迹每个周期的步进基准从“上一次软件目标”改为“最新实测关节反馈”，每步仍受原有最大速度和反馈看门狗限制。构建 `brain_robot_pick_place` 成功，提交 `eee1453`。
- 后续默认启动未进入运动：本轮实际阻断提前发生在 `[5/7]`，`tf_gate_diagnostic` 显示 `accepted_frames=0`，因为相机到基座 TF 在当前启动时段不可用；脚本已停止并保持使能，未发送运动命令。该次验证不能判定闭环步进是否已解决轨迹收敛。
- 日志：`/tmp/brain_robot_auto_closed_loop_observe_v19_20260924b.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。错误提示已改为“相机到基座 TF 心跳”，不再错误暗示必须建立 Octomap。

### 本轮结论与下一步

- 适配器闭环修复已落库，但尚未获得一次通过 TF 门控后的实机运动验证；当前最新阻断是相机/机器人 TF 心跳缺失，不是点云障碍或抓取逻辑。
- 下一次仅复用同一默认脚本，在 TF 心跳恢复后验证 `OBSERVE_POSE_REACHED`；若轨迹仍不收敛，再根据闭环命令与实测反馈差值继续定位。

## 2026-09-24 继续执行前的 USB-CAN 实际阻断

- 实际检查根分区可用 `6.3G`、日志目录 `62M`，磁盘不再是阻断；唯一遗留进程为 Astra 相机。USB-CAN 仍以 `1d50:606f` 枚举，`gs_usb` 模块已加载，`can0` 列表中短暂存在但处于 `DOWN/STOPPED`。
- 按现有受限免密 sudo 执行两次最小恢复 `sudo -n ip link set can0 up`，均返回 `RTNETLINK answers: No such device`。同一时段内核持续记录 VMware xHCI `ERROR Transfer event TRB DMA ptr not part of current TD ep_index 2 comp_code 1`。因此不能取得 RX 增量，也不能启动 PiPER 驱动或任何运动。
- 未执行重载、刷写、`MasterSlaveConfig`、`ResetPiper` 或 ROS 运动命令。当前最新阻断是 USB-CAN 虚拟机传输/接口消失，而不是闭环轨迹、点云或紫色目标算法。

### 本轮结论与下一步

- 必须等 `can0` 能稳定 `UP` 且 RX 持续增长后，才能复用已提交的闭环轨迹修复运行默认脚本；在此之前禁止启动实体运动。

## 2026-09-25 磁盘维护改为持久 systemd 定时任务

- 实际状态：根分区 `/` 为 `78G` 总量、`21G` 已用、`54G` 可用（28%）；`/home/johnwick/brain_robot_logs` 约 `62M`。原有清理只在启动脚本运行期间每 30 秒执行，`systemctl list-timers` 中没有 PiPER 专用维护任务，因此无法覆盖脚本退出或异常中止后的日志增长。
- 最小修复：扩展固定路径的受限 root helper，继续限制系统日志/journal 上限，同时固定清理 `/home/johnwick/brain_robot_logs`（单日志 20MiB、超过 3 天删除）；增加 `brain-robot-log-maintenance.service` 与 `brain-robot-log-maintenance.timer`，启动后 2 分钟运行、之后每 10 分钟运行、`Persistent=true`。加入 `/run/lock` 非阻塞锁，避免启动脚本看门狗与 timer 并发清理。
- 已从规范仓库脚本安装并实际启用：`sudo -n bash brain_robot_arm/scripts/install_brain_robot_log_maintenance.sh`；`visudo -cf` 通过，helper 一次执行返回 0，systemd service 返回 `status=0/SUCCESS`。
- 验证：`systemctl is-enabled`=`enabled`、`is-active`=`active`，下一次触发时间约 10 分钟后；安装文件均为 root 所有，sudoers 为 0440；当前磁盘仍为 28%，无删除源代码、ROS build/install 或 Conda。

### 本轮结论与下一步

- 磁盘清理已从“依赖机器人脚本存活”改为系统级持续维护，能覆盖脚本退出、重启和异常中止；后续不再把“没有定时清理”作为启动阻断。
- 机械臂当前仍不可运动：最近实测 `can0` 为 `DOWN/STOPPED`，`ip link set can0 up` 返回 `No such device`，并伴随 VMware xHCI 传输错误。下一步只在 `can0` 稳定 `UP` 且 RX 持续增长后复用默认自动路径，验证 `OBSERVE_POSE_REACHED` → `SEARCH`，不得在接口消失时启动运动。

## 2026-09-25 断点复核：磁盘清理后 CAN 状态未改变

- 按用户要求在断点执行 `/home/johnwick/clean_disk_space.sh`；受限 helper、journal 清理和 `apt clean` 均成功，退出码为 0。根分区由清理前后均为 28%（可用空间约 55G），说明当前不存在磁盘耗尽门控。
- 清理后只读检查显示 `can0` 仍为 `DOWN/STOPPED`，RX/TX 均为 0；因此不能把清理成功误报为 CAN 已恢复，也没有启动默认实体运动脚本。

### 本轮结论与下一步

- 本轮已完成用户要求的断点清理验证；清理没有改变 USB-CAN 接口状态，当前最大阻断仍是 USB-CAN/VMware 链路未提供可用 `can0` 反馈。
- 下一步门槛不变：先取得稳定 `can0 UP`、正确 CAN 参数和持续 RX 增长，再复用默认 `AUTO_START=1` 流程验证观测、搜索、定位和抓取；在 RX=0 时不发送运动命令。

## 2026-09-25 恢复 CAN 后默认自动观测实跑：卡顿根因是反馈保护停发

- 受限恢复命令后 `can0` 实际为 `UP/LOWER_UP`、`ERROR-ACTIVE`、1 Mbps/0.75；5 秒 RX 从 `182240` 增长到 `193853`，满足启动门槛。默认 `BRAIN_ROBOT_AUTO_START=1` 已实际通过 `[1/7]` 至 `[7/7]`，收到相机和调试图像首帧并接受 49 秒当前姿态→观测轨迹。
- 卡顿期间 `piper_driver.log` 连续记录 `can0 feedback lost; suppressing output for up to 25.0s`，随后反馈恢复间隔为约 `2.57`、`10.00`、`17.43` 秒等；因此适配器按保护策略停发目标，机械臂表现为走走停停。总 RX 仍增长，但关节反馈不是连续的。
- MoveIt 日志确认实体 Octomap 监听 `/brain_robot_vision/disabled_octomap_points`，并报告 `No 3D sensor plugin(s) defined for octomap updates`；没有证据表明夹爪点云被写入碰撞模型。另有相机时间戳落后导致的 `Lookup would require extrapolation into the past`，属于 TF 时间同步问题，不是夹爪自体碰撞。
- 该次运行在 300 秒受控超时后由脚本执行关闭运动门、停止视觉/相机/驱动并失能 PiPER；未进入 `OBSERVE_POSE_REACHED`、`SEARCH` 或抓取。日志：`/tmp/brain_robot_auto_resume_20260925.log`、`/home/johnwick/brain_robot_logs/piper_driver.log`、`visual_stack.log`。

### 本轮结论与下一步

- “夹爪被加入障碍模型导致基本观测卡顿”不是本轮实跑的根因；自体 Octomap 输入已禁用。当前可复现根因是运动期间关节反馈间歇，触发驱动保护停发，造成轨迹无法连续收敛。
- 下一步只针对反馈间歇的 USB-CAN/VMware 传输或 S-V1.9-1 运动态反馈生命周期做最小定位；不降低保护门槛、不恢复腕部 Octomap，不在反馈断续时强行继续运动。

## 2026-09-25 收尾安全修复：失能前强制确认回位

- 本轮 300 秒外层超时发送 `SIGINT` 后，旧版 `cleanup()` 直接调用 `/enable_srv {enable_request: false}`，没有先请求 `RESET_COMPLETE`；这违反了既定“失能前必须回到已验证零点/安全支撑姿态”的规则。该行为已确认是脚本缺陷，不能再重复。
- 最小修复：`cleanup()` 现在先调用已有 `request_zero_reset()`，仅在确认 `RESET_COMPLETE` 后才执行 `disarm`、关闭运动门和 `enable_request: false`。如果复位服务、反馈或到位确认失败，则跳过全部失能命令，保持 PiPER 使能并报告保护阻断。
- 已通过 `bash -n`，并将修复后的启动脚本同步到 `/home/johnwick/start_brain_robot_cube_real.sh`；未发送新的运动或失能命令。当前上一轮流程已结束、无残留控制进程。

### 本轮结论与下一步

- 之前的直接失能属于必须修复的安全违规；今后任何 Ctrl+C、超时或异常收尾都不能在未确认回位时失能。
- 下一次实跑必须先验证该收尾门控，再继续反馈间歇定位；若回位失败，保持使能而不是强制关闭。

## 2026-09-25 清理后通信因果复核

- 按当前断点执行一次完整的 `/home/johnwick/clean_disk_space.sh`，受限 helper 和 `apt clean` 均成功；根分区由 28% 保持 28%（可用空间约 55G），定时器仍为 `active`。
- 清理完成后立即只读检查 `can0`：仍为 `DOWN/STOPPED`，RX/TX 均为 0。此次前后对照证明“清理磁盘后自动恢复 CAN”不成立，不能继续把当前通信阻断归因于日志占用。
- 未重载 CAN、未启动驱动、未发送运动命令；避免在无反馈链路时进入实体观测或抓取。

### 本轮结论与下一步

- 磁盘维护已执行且结果可验证；当前阻断仍是 USB-CAN/VMware 接口未形成可用 `can0`，而非清理动作未执行。
- 下一步必须是外部链路重新枚举/透传后，确认 `can0 UP`、1 Mbps/0.75 且 RX 持续增长；达到该门槛后立即复用默认自动脚本，验证 `OBSERVE_POSE_REACHED` → `SEARCH`，再继续点云碰撞和紫色方块抓取闭环。

## 2026-09-25 高级实体链骨架推进与最新阻断

- 复用既有 `cube_visual_search.launch.py → cube_task_real.yaml → visual_search_controller → piper_jog_adapter → grasp_lift_executor → start_brain_robot_cube_real.sh`，未另写基础运动程序。默认实跑实际完成 `OBSERVE_POSE_REACHED → SEARCH`；紫色检测器产生 `PURPLE_CUBE target DETECTED`，但搜索第一段因 `SEARCH_SEGMENT_FEEDBACK_TIMEOUT` 进入保护故障。
- 依据已实测最长约 17.4 秒反馈空窗，将 `search_segment_timeout_s` 从 12 秒调整为 30 秒；将实体 `grasp_lift_executor.auto_execute` 从 `false` 调为 `true`，使 `GRASP_READY` 自动进入既有抓取骨架。`brain_robot_ball_pick` 构建成功，安装 YAML 已确认同步。
- 第二次默认复跑在脚本重新配置 CAN 后 5 秒 RX=0，于 `[1/7]` 安全退出，未发送运动命令；随后 USB-CAN reset 与 6 秒只读 `candump` 仍 RX=0。因此新搜索门控和自动抓取尚未获得第二次实机验证。

### 本轮结论与下一步

- 观测后确实已经自动进入 `SEARCH`；抓取骨架的两个软件门控已修复，但当前最新阻断重新是 USB-CAN 无 RX。
- 下一步必须先恢复持续 RX，再复用已构建的 30 秒搜索门控和自动抓取链；不在 RX=0 时启动实体运动。

## 2026-09-25 实体 MoveIt 3D updater 彻底停用

- 为排除任何残留/陈旧 occupancy updater 状态，实体 `sensors_3d_real.yaml` 的 `sensors` 列表改为空并重建 `brain_robot_ball_pick`；RGB-D 检测、TF-gated freshness 和机器人自碰撞检查仍保留，腕部点云不再有任何 MoveIt Octomap 接入口。
- 该调整符合 MoveIt 官方 occupancy map 插件架构：未注册 3D sensor 时不会接收点云更新；它不关闭 PlanningScene 自碰撞检查，也不绕过 `piper_jog_adapter`。安装配置已确认 `sensors: []`。

### 本轮结论与下一步

- “夹爪点云进入 Octomap”现在在配置层和运行层都被切断；后续若候选规划仍失败，应只检查 IK/关节反馈/URDF 自碰撞，不再反复修改点云过滤参数。
- 下一步在稳定 CAN RX 后复用默认链，验证 `GRASP_READY` 后候选规划和自动抓取。

## 2026-09-25 预抓取规划新鲜状态等待修复

- 依据上一轮 `GRASP_READY` 后的实际日志，问题不是夹爪点云碰撞：MoveIt 报告当前关节状态超过 1 秒未更新，grasp executor 在真实反馈和全零状态之间交替取值，导致 RRT 无法建立有效 goal tree。
- 在既有 `grasp_lift_executor.cpp` 中增加 `joint_state_wait_timeout_s`（实体 YAML 明确为 25 秒），所有 TOP_DOWN IK、预抓取关节规划、笛卡尔规划和 IK 诊断在调用 MoveIt 前都等待最近 1 秒内的新鲜关节反馈；超时只报告规划失败，不使用旧/零填充状态。
- `brain_robot_pick_place`、`brain_robot_ball_pick` 构建成功；未恢复腕部点云输入，未关闭碰撞检查，未绕过 `piper_jog_adapter`。

### 本轮结论与下一步

- 本修复针对实测的规划状态过期，保留 MoveIt 正常碰撞检查。官方 MoveIt 资料说明 occupancy updater 的自体过滤只处理实际接入的传感器点云；本实体配置的 disabled topic 无发布者，因此没有夹爪点云进入 Octomap 的证据。
- 下一步在 CAN RX 恢复后复用同一自动链验证：`GRASP_READY` → 新鲜状态等待 → 候选预抓取 → 抓取/抬升/释放；失败时保持安全回位规则。

## 2026-09-25 官方 SDK 对照：阻止默认零反馈污染 MoveIt

- 查阅 AgileX 官方 PiPER V2 SDK demo 与 README：官方明确说明未初始化的第一帧关节反馈为默认零值，官方关节控制示例持续发送 `MotionCtrl_2` 与 `JointCtrl`；未采用其 `MasterSlaveConfig`/复位建议，仍遵守本任务禁令。
- 最小驱动修复：`piper_ctrl_single_node` 现在要求高速反馈 `0x251..0x256` 与六轴聚合反馈（`0x2A1..0x2A8` 或 S-V1.9-1 映射前的 `0x3A0..0x3A7`）同时新鲜，才发布 ROS JointState；已验证反馈改用本机 ROS 时钟作为 header stamp，避免 USB/VM 批量延迟造成 MoveIt 当前状态过期或 SDK 默认全零进入规划。
- `py_compile` 与 `/home/johnwick/piper_ros` 的 `piper` 重建均成功；实际 `can0` 为 UP/ERROR-ACTIVE，5 秒 RX 从 `1514241` 增至 `1525877`，且无残留 PiPER/视觉控制进程。

### 本轮结论与下一步

- 已同时处理“SDK 默认零反馈”和“MoveIt 使用陈旧 CAN 时间戳”两条导致抓取候选规划从错误起始状态出发的路径；不改变碰撞模型或腕部 Octomap 禁用决策。
- 下一步直接复用默认自动链实测此驱动修复，验收 `GRASP_READY` 后的候选预抓取是否获得有效规划并继续抓取。

## 2026-09-25 实体感知配置回退：无插件配置触发 MoveGroup 崩溃

- 上一轮为彻底排除任何残留 occupancy updater，把实体 `sensors_3d_real.yaml` 改为 `sensors: []` 后启动默认脚本；实际日志显示 `move_group` 在无显示环境中因 `freeglut failed to open display` 退出码 `-11`，导致视觉启动失败。这是当前配置组合的启动回归，不是机械臂或夹爪碰撞证据。
- 已停止残留视觉/相机/检测进程，调用 `/piper_jog_adapter/disarm` 与 `/servo_node/stop_servo` 成功；未发送失能命令。随后将 `sensors` 恢复为已验证的 `astra_depth_pointcloud`，但继续指向无发布者的 `/brain_robot_vision/disabled_octomap_points`，因此腕部点云仍不会进入实体 Octomap。
- 重新同步运行时工作区并构建 `brain_robot_ball_pick`，`colcon build --symlink-install --packages-select brain_robot_ball_pick` 返回 `0`。本次修复只恢复 MoveGroup 启动兼容性，不恢复任何真实点云输入，也不关闭 URDF/SRDF 自碰撞检查。

### 本轮结论与下一步

- `sensors: []` 在当前 MoveIt/无显示环境组合下不可作为实体默认配置；已回退到“插件初始化 + 不存在 topic”的稳定方案。官方 MoveIt occupancy updater 只有在实际订阅到传感器输入时才更新 Octomap，因此该方案仍排除夹爪点云障碍。
- 下一步重新运行默认 `BRAIN_ROBOT_AUTO_START=1` 脚本；若到达 `GRASP_READY` 后预抓取仍失败，增加并读取 MoveIt IK/规划诊断，区分 URDF 自碰撞、目标不可达与反馈状态问题，不再修改点云过滤参数。

## 2026-09-25 默认链复跑：反馈空窗导致 TF 门控失败，驱动改为安全保持

- 配置回退后的默认脚本实跑中，`move_group` 已正常完成 OMPL/Pilz 初始化，没有再次出现无 3D updater 的崩溃；脚本在 `[5/7]` 等待 TF 门控时停止。视觉日志明确为 `base_link` 与 `camera_color_optical_frame` 不在同一 TF 树，原因是 PiPER 驱动日志显示反馈丢失满 25 秒后进程退出，动态 `robot_state_publisher` 随之失去关节状态。
- 相机/点云只读复核确认 `/camera/depth/points` 有真实 publisher；因此本轮没有“夹爪被点云加入障碍模型”的证据。实体 Octomap 仍只指向无发布者的 disabled topic。
- 最小安全修复：`piper_ctrl_single_node` 在反馈空窗超过 25 秒后不再 `rclpy.shutdown()`，改为保持 ROS/TF 节点存活并永久抑制 CAN 输出，直到完整高速与聚合反馈恢复；恢复时清除该状态并重新发布新鲜 JointState。该路径不会在反馈丢失期间发送运动命令。
- `py_compile` 通过，`/home/johnwick/piper_ros` 的 `piper` 包构建返回 `0`，运行时源已同步。

### 本轮结论与下一步

- 当前阻断是反馈空窗造成的 TF/MoveIt 状态源退出，不是点云碰撞。驱动保持接收态后，下一轮可在同一 CAN 链路恢复时继续等待 TF 并进入观测，不必重启整套视觉栈。
- 下一步复跑默认自动脚本，验收 `OBSERVE_POSE_REACHED → SEARCH → GRASP_READY`；若抓取候选仍失败，再读取 IK/规划失败诊断。

## 2026-09-25 自动链推进到 GRASP_READY：显式预抓取状态修复

- 第二次默认自动实跑已完整出现 `OBSERVE_POSE_REACHED → SEARCH → ALIGN → GRASP_READY`，检测器持续报告紫色目标；日志显示 MoveGroup 正常规划搜索段，且没有腕部点云进入实体 Octomap。
- 抓取执行器按既有顺序生成 `TOP_DOWN`、`DIAGONAL_LEFT`、`DIAGONAL_RIGHT` 候选，不把视觉对齐姿态直接当作最终抓取；预抓取后仍使用受限笛卡尔下降。失败日志显示在预抓取规划期间 MoveIt 当前状态再次过期并出现全零起点，故尚未进入靠近/夹爪闭合。
- 最小修复：`grasp_lift_executor` 在等待新鲜反馈后调用 `getCurrentState(0.5)`，把该真实状态显式写入 `MoveGroupInterface::setStartState`；不再让 `setStartStateToCurrentState()` 在 USB/CAN 空窗期间重新抓取陈旧/默认状态。笛卡尔下降同样使用显式起始状态。
- `brain_robot_pick_place` 与 `brain_robot_ball_pick` 构建均返回 `0`；上一轮实体流程已停止并调用视觉 stop/Servo stop/适配器 disarm，未发送失能命令。

### 本轮结论与下一步

- 现阶段“对齐后无法靠近”的直接软件阻断是预抓取请求起点被反馈空窗污染，不是夹爪点云障碍；候选角度/方向策略已存在但此前未真正执行到靠近段。
- 下一步复跑验证显式起点是否让 TOP_DOWN 预抓取成功；若仍失败，读取新增加的 IK 诊断返回码，区分目标姿态不可达与实体自碰撞，再调整候选方向/偏移。

## 2026-09-25 预抓取失败诊断可见化

- 显式起始状态版本的实跑再次达到 `GRASP_READY`，但 TOP_DOWN 四个 yaw 候选均出现 `Unable to sample any valid states for goal tree`；代码日志中的 current pose 在反馈空窗时仍可能显示零值，不能据此判定为碰撞。
- 已在 `grasp_lift_executor` 的每次预抓取规划失败处直接输出 `DiagnoseIk` 结果。该诊断使用 `avoid_collisions=false` 的 `GetPositionIK`：`IK_OK_PLAN_FAILED` 表示 IK 可达但规划/碰撞失败；`IK_ERROR_CODE_*` 表示姿态/模型不可达；`IK_CURRENT_STATE_STALE` 表示反馈仍不满足安全门槛。
- 两个工作区包构建返回 `0`；未关闭碰撞检查、未把腕部点云接入实体 Octomap、未绕过适配器。

### 本轮结论与下一步

- 目前尚无依据把“无法靠近”归因于夹爪点云；下一次短实跑只需读取上述诊断结果即可选择修正方向：若 IK 可达则优化预抓取空间/自碰撞；若 IK 错误则调整 TOP_DOWN/DIAGONAL 末端姿态与偏移；若状态过期则继续反馈门控修复。

## 2026-09-25 自动抓取实跑：已到 GRASP_READY，预抓取规划被反馈状态过期阻断

- 用户确认 CAN 恢复后，实测 `can0` 5 秒 RX 从 `68199` 增至 `79819`，默认脚本通过 `[7/7]`，完成 `OBSERVE_POSE_REACHED → SEARCH`；检测器实际报告紫色目标，视觉链随后经历 `ALIGN`、`LOCAL_SEARCH`、目标重捕获，并达到 `GRASP_READY (DIRECT_VISUAL_ALIGN_ACQUIRED)`。
- `auto_execute=true` 已生效，`grasp_lift_executor` 自动尝试 TOP_DOWN、DIAGONAL_LEFT、DIAGONAL_RIGHT 候选；三类预抓取 MoveIt 规划均失败。日志同时显示 MoveIt 当前关节状态过期（`Didn't receive robot state ... within 1.000000 seconds`），grasp executor 看到的 current 在 `[0.193,0.030,0.313]` 与 `[0,0,0]` 间跳变，随后 `Unable to sample any valid states for goal tree`。
- 运行时 MoveIt 仍监听 `/brain_robot_vision/disabled_octomap_points`；只读查询确认该 topic 无发布者，`/brain_robot_vision/filtered_points` 也无发布者，不能把本次预抓取失败归因于腕部点云写入 Octomap。依据 MoveIt 官方文档，点云自体过滤只处理实际接入 occupancy updater 的传感器输入；本配置已切断该输入。
- 已停止视觉/Servo 并 disarm 适配器；未发送失能命令、未执行抓取动作。残留启动/驱动/视觉进程已清理，保持当前安全状态。运行日志：`/tmp/brain_robot_auto_grasp_20260925.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。

### 本轮结论与下一步

- 目标链已推进到 `GRASP_READY`，证明观测、搜索、目标定位和自动抓取触发均已连通；当前最大阻断是反馈间歇造成的 MoveIt 当前状态过期/跳变，不是夹爪点云障碍。
- 下一步应在稳定反馈下让抓取规划等待新鲜关节状态后重试既有候选；保持禁用实体腕部 Octomap，不绕过 `piper_jog_adapter` 或碰撞检查。

## 2026-09-25 搜索段反馈门控再次触发

- 本轮默认自动脚本正常通过 `[7/7]`、观测姿态并进入 `SEARCH (OBSERVE_POSE_REACHED)`；MoveIt 搜索段规划成功且适配器接受轨迹。
- 随后反复出现约 10 秒反馈空窗，原 30 秒搜索段门控最终触发 `SEARCH_SEGMENT_FEEDBACK_TIMEOUT`，未进入 `ALIGN/GRASP_READY`。这再次证明当前先行阻断是受保护反馈间歇，而不是夹爪点云碰撞。
- 已将实体 `search_segment_timeout_s` 从 30 秒提高到 60 秒，以覆盖两个连续受保护反馈空窗；仍保持反馈丢失时抑制 CAN 输出，不发送旧值或零值。安装运行时配置需在下一次构建同步。

### 本轮结论与下一步

- 候选抓取姿态和显式预抓取起始状态修复尚未在本轮获得新的实机验证，因为搜索门控先行故障。
- 下一步构建并复跑同一默认链；只有再次到达 `GRASP_READY` 后，才根据 `IK_OK_PLAN_FAILED` / `IK_ERROR_CODE_*` 诊断调整正上方或斜向预抓取姿态。

## 2026-09-25 视觉轮廓间歇丢失的最小修复

- 60 秒搜索门控生效后，默认链已通过观测并进入 SEARCH；检测器日志显示同一目标在 20--300 ms 内反复 `DETECTED/LOST`，导致 ALIGN/LOCAL_SEARCH 循环，尚未稳定进入抓取候选。
- 实际检测器配置的 `min_rectangularity: 0.58` 对当前 RGB-D/运动模糊轮廓过严；已降至保守的 `0.40`，仍保留颜色、面积、长宽比和独立深度稳定门控，不直接放宽抓取授权。
- 配置已同步到 `/home/johnwick/piper_ws`；下一步构建检测器包并复跑，验证目标稳定后再读取 TOP_DOWN/DIAGONAL 的 IK 诊断。

### 本轮结论与下一步

- 本轮未执行抓取或失能；视觉 stop、Servo stop、适配器 disarm 已调用。

## 2026-09-25 轮廓阈值修复后的首次默认启动被 TF 门控阻断

- 实际命令：`timeout --signal=INT --kill-after=180s 360s env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`；返回码 `1`。
- `can0` 当时为 `ERROR-ACTIVE`、1 Mbps/sample-point 0.75，RX 持续增长；无新的 CAN/固件/限位排查。
- 启动输出完成相机、检测器和 MoveIt 初始化，但在 `[5/7]` 报“未收到相机到基座的可用 TF 心跳”，未进入观测运动、SEARCH 或抓取；本轮没有发送抓取动作，也没有发送失能命令。
- `visual_stack.log` 显示 `robot_state_publisher` 曾成功加载 `base_link`，MoveGroup context 初始化完成；`/brain_robot_vision/disabled_octomap_points` 无发布者，故没有证据表明夹爪点云进入实体 Octomap。
- 运行结束后残留 `/camera/camera`、`astra_camera_container` 和多个调试图像查看节点；相机 TF 只能看到 camera 内部帧，`base_link` 不存在。`piper_driver.log` 的 `publisher's context is invalid` 出现在脚本清理阶段，属于退出竞态，不能作为初始 TF 失败的证据。

### 本轮结论与下一步

- `min_rectangularity: 0.40` 尚未在完整默认链上验证，因为 TF 门控先行失败；不能宣称已修复搜索或抓取。
- 下一步只清理明确残留的 Astra/调试节点，重新运行同一默认脚本，验证新启动的 `robot_state_publisher + pointcloud_tf_gate` 是否产生有效 TF 心跳；若通过，再读取 `IK_*` 规划诊断决定预抓取姿态调整。

## 2026-09-25 斜向候选实跑中止与异常行为收尾

- 规范配置已将 `candidate_grasp_order` 改为 `DIAGONAL_LEFT, DIAGONAL_RIGHT, TOP_DOWN`，同步到 `/home/johnwick/piper_ws` 并构建成功。
- 本轮默认脚本实际通过 `[5/7]`、`[7/7]`、`OBSERVE_POSE_REACHED`、`SEARCH`，随后因反馈空窗累计 60 秒进入 `STATE -> FAULT (SEARCH_SEGMENT_FEEDBACK_TIMEOUT)`；未进入新的 `GRASP_READY`，因此斜向候选没有获得实体规划证据。
- 驱动记录反馈恢复间隔约 2.6--17.5 秒；适配器在空窗期间抑制输出。日志中最后一次规划轨迹被接受后没有新的有效运动阶段。
- 用户报告机械臂行为陌生后，已停止脚本、MoveIt、Servo、视觉控制器、抓取执行器、检测器和相机；当前无相关控制进程、无新的运动命令，`can0` 仅保持 `ERROR-ACTIVE` 接口状态。

### 本轮结论与下一步

- 本轮不继续启动真机运动；异常行为的直接记录是视觉状态机在反馈保护故障后仍等待脚本收尾，现已清理。不得把它解释为夹爪点云碰撞。
- 下一步必须先由操作者确认机械臂当前姿态/使能状态，再决定是否进行一次受控重试；在此之前只做文档和静态代码检查。

## 2026-09-25 用户报告“对齐后扭头并小幅震动”的命令还原

- 实际运行命令是：`timeout --signal=INT --kill-after=180s 360s env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`。这不是只读诊断；它启动了 PiPER 驱动、Astra、检测器、MoveIt、Servo、`piper_jog_adapter`、视觉控制器和抓取执行器，并因 `BRAIN_ROBOT_AUTO_START=1` 自动发送了真实轨迹。
- 运行先接受当前姿态到观测姿态的 52.9 秒轨迹，随后进入 `OBSERVE_POSE_REACHED → SEARCH → ALIGN`。目标检测在 `DETECTED/LOST` 间快速切换，控制器反复进入 `LAST_PATH_REACQUIRE`，每次向适配器提交 2 点小轨迹；这就是用户看到的小幅抖动来源。
- 首次运行达到 `GRASP_READY` 后，抓取执行器对 TOP_DOWN 目标（`(-0.120,-0.077,0.367)`）调用 MoveIt 规划，返回 `IK_ERROR_CODE_-31`；这次没有执行抓取闭合。
- 随后目标发生偏移，视觉状态回到 `ALIGN` 再次 `GRASP_READY`。脚本超时触发 SIGINT 后，`cleanup()` 调用了 `/visual_search_controller/reset`；日志明确出现 `STATE -> PREPARE (RESET_AUTHORIZED)` 和新的 49.0 秒 `REAL ARM trajectory accepted`。这条收尾复位轨迹就是“突然扭头转向别处”的直接来源，属于脚本收尾逻辑，不是用户按键，也不是夹爪点云碰撞。
- 该命令已停止；当前没有脚本、PiPER 驱动、MoveIt、Servo、视觉或抓取进程，未发送失能命令。运行日志：`/home/johnwick/brain_robot_logs/ros/visual_search_controller_44404_1790312868377.log`、`/home/johnwick/brain_robot_logs/visual_stack.log`。

### 本轮结论与下一步

- 已确认此前的自动收尾复位轨迹超出了用户期望的“当前姿态→观测姿态”路径；在用户确认前不再启动任何真实运动。
- 后续若修复，必须把“抓取/搜索故障后的脚本收尾”与“用户明确请求的零点复位”分开：故障时先停止发送目标并保持使能，不得静默发起新的长复位轨迹。

## 2026-09-25 背景紫色误检与异常收尾的静态修复

- 检测器原先把 `target_valid` 直接建立在颜色/二维轮廓上；实体控制器又设置 `target_acquire_frames: 1`，故紫色背景或单帧轮廓可以触发 ALIGN。现在实体 profile 强制 `require_depth_for_target_valid: true`，要求深度稳定、相邻深度帧一致、未裁边、相机内参可用，并要求估算正方形边长在 `0.015--0.120 m`、物理宽高比不大于 `1.45`；矩形度恢复 `0.58`，二维宽高比收紧至 `1.45`。
- 视觉控制器的实体 `target_acquire_frames` 已由 `1` 提升到 `6`；颜色候选仍只用于独立重捕获话题，不再直接给真机 ALIGN。
- 启动脚本的 SIGINT/故障收尾已改为：调用 visual stop、Servo stop、adapter disarm 并保持使能/当前位置；只有显式 `0` 入口才允许零点复位。这样故障不再静默发送长 `RESET_AUTHORIZED` 轨迹。
- 已同步源码、两份配置和脚本到 `/home/johnwick` 实际运行树；`colcon build --packages-select brain_robot_pick_place brain_robot_ball_pick --symlink-install` 返回 `0`，`colcon test` 返回 0 errors/failures（该包没有定义测试），`bash -n` 成功，且检查时没有 PiPER/MoveIt/Servo/视觉控制进程。

### 本轮结论与下一步

- 本轮只构建与静态验证，未启动真机运动；“背景紫色不触发对齐”和“超时不自动复位”需要在操作者确认后以一次短实跑验证。
- 速度慢仍主要由 2.6--17.5 秒反馈保护空窗造成；不提高速度倍率来掩盖该问题。先验证稳定目标门控，再以实际反馈决定是否小幅调整观测轨迹速度。

## 2026-09-25 三维门控无运动启动验证被 CAN 无新反馈阻断

- 实际命令：`timeout --signal=TERM --kill-after=30s 150s env BRAIN_ROBOT_AUTO_START=0 /home/johnwick/start_brain_robot_cube_real.sh`。该模式不调用 start/arm/轨迹服务；目标是只观察新检测门控。
- 脚本在 `[1/7]` 读取到 `can0 UP/ERROR-ACTIVE`、1 Mbps/0.75，但 5 秒内 RX 无增长，报“can0 已启动但 5 秒内没有收到机械臂反馈”，返回 `1`。最终 RX 为 `12701762`，TX 为 `492759`；没有视觉、PiPER、MoveIt、Servo 或抓取进程遗留。
- 本轮没有机械臂运动、没有使能/失能请求，因而尚未得到背景紫色实际拒绝的相机证据。根分区仍为 28%，不能把本次无反馈归因于磁盘空间。

### 本轮结论与下一步

- 依照无 RX 规则，禁止自动启动真实运动和速度调整。下一步只等 `can0` 在 5 秒采样内 RX 再次增长后，先以 `BRAIN_ROBOT_AUTO_START=0` 验证 `target_valid`，再执行受控默认链。
## 2026-09-25 自动断电报告与接收型生命周期回归

- 用户报告机械臂“恢复后自动断电”。本轮开始前实际没有 `start_brain_robot_cube_real.sh`、`piper_single_ctrl` 或视觉控制进程；残留的 MoveIt/Servo/视觉节点也未发送 CAN。`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps/sample-point 0.75，5 秒 RX 从 `13216606` 增至 `13228273`，`candump` 持续看到 `3A0..3A7` 与 `251..256`；因此当前不是“接口无 RX”。
- `/home/johnwick/brain_robot_logs/piper_driver.log` 的旧故障证据为反馈丢失 25 秒后驱动保持 receive-only，随后在 ROS context 已被外部关闭时再次调用 `rclpy.shutdown()`，产生 `RCLError: rcl_shutdown already called`。反馈丢失分支本身没有 `DisableArm(7)`；本轮没有发新的使能、失能或运动命令，不能把物理断电未经证据归因给脚本。
- 最小修复：在规范驱动 `brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py` 的自动使能超时和 `main()` 收尾中，仅当 `rclpy.ok()` 时调用 `rclpy.shutdown()`；同步到 `/home/johnwick/piper_ros` 并构建 `piper`。
- 验证命令：`colcon build --packages-select piper --symlink-install` 返回 0；`python3 -m py_compile /home/johnwick/piper_ros/build/piper/piper/piper_ctrl_single_node.py` 返回 0；`BRAIN_ROBOT_AUTO_START=0 timeout ... 150s /home/johnwick/start_brain_robot_cube_real.sh` 返回 124（外部超时），但完整到达 `[7/7]`，在 150 秒无运动等待期间未出现 `feedback absent for 25.0s` 或重复 `rcl_shutdown`，清理后无 PiPER/视觉控制进程遗留。当前运行树日志只剩受控终止产生的 `ExternalShutdownException`，不是重复 shutdown。
- 该回归未调用 `EnablePiper`、观测轨迹、`DisableArm` 或 `ResetPiper`；TX 仅从 492759 增至 492785，未观察到运动阶段命令。根分区仍约 28%，没有磁盘不足证据。
- 当前阻断：CAN 接收持续但实体“使能/供电状态”尚未从新的状态反馈中独立确认；在自动断电原因与机械支撑状态明确前，不启动 `BRAIN_ROBOT_AUTO_START=1` 的真实运动。下一步先读取 3A/251 状态映射和实际使能反馈，确认驱动保持接收型后再进行一次受控当前姿态→观测姿态验证。

## 2026-09-25 只读确认当前使能状态

- 使用官方 `C_PiperInterface_V2(can_name=can0, judge_flag=False)` 的接收线程读取 2 秒，未调用 `EnablePiper`、`MotionCtrl_2`、`JointCtrl` 或 `DisableArm`：高速反馈时间戳持续更新，但 stock SDK 的聚合关节时间戳为 0、`GetArmEnableStatus()` 六轴全为 `False`。
- 启动规范驱动 `auto_enable=false` 后，3A→2A 接收映射能发布真实 `/joint_states`（J1..J6 非全零，时间戳新鲜），但 `/arm_status` 仍显示六轴通信/使能状态为 false；无控制进程已清理，can0 TX 仅增加启动/收尾少量帧。
- 结论：当前机械臂确实处于未使能/可能掉电状态，不能把它当作视觉碰撞或磁盘问题；但本轮没有证据表明脚本主动发出了 `DisableArm`。在机械臂支撑和供电状态未由现场确认前，保持禁止自动使能与真实运动。

## 2026-09-25 默认自动链恢复使能后仍在观测轨迹失败

- 受控命令：`timeout --signal=INT --kill-after=45s 360s env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`。脚本复用 `can0` UP/1 Mbps/0.75/RX 增长，调用 `/enable_srv {enable_request: true}` 与 `/piper_jog_adapter/enable_motion`、`/arm` 成功；适配器记录 `PHYSICAL MOTION ARMED`，视觉控制器发布当前姿态→观测姿态 2 点轨迹并接受。
- 实际状态序列为 `STATE -> PREPARE`，未出现 `OBSERVE_POSE_REACHED` 或 `SEARCH`；约 320 秒后发布 `PREPARE_EXECUTION_FAILED`，脚本保护收尾停止视觉/Servo、disarm 适配器并明确未发送 `DisableArm`，返回 124（外部 timeout）。
- 驱动日志在轨迹期间反复出现 `feedback lost`，恢复间隔约 2.6、10.0、10.2、24.9 秒；没有 `feedback absent for 25.0s`，但该间歇反馈使观测门控无法确认收敛。MoveIt/视觉日志同时有 camera→base_link 的过去时间外推警告；实体 Octomap 仍监听无发布者的 disabled topic。
- 重要新假设：S-V1.9-1 运动期间 3A 聚合关节帧可能间歇，而 251..256 高速帧持续；直接把高速帧位置替代聚合位置会改变安全关键反馈语义，本轮未写入、未绕过反馈保护。下一步必须先用原始 CAN 抓包逐 ID 对齐位置/时间，再由用户确认后才考虑最小映射修复。
- 当前无控制进程遗留，can0 仍有 RX；机械臂未被脚本自动失能。目标仍阻断在真实观测姿态到达，未进入搜索/抓取。

## 2026-09-25 固件与协议再次核对（仅查询）

- 官方 SDK 查询结果：`GetPiperFirmwareVersion() = S-V1.9-1`，`GetCurrentSDKVersion() = 0.6.2`，`ARM_PROTOCOL_V2/INTERFACE_V2`；未刷写、未 ResetPiper、未执行 MasterSlaveConfig。
- 官方 `piper_sdk` V2 文档明确：`GetArmJointMsgs()`/0x2A1 为 0.001° 聚合关节角；`GetArmHighSpdInfoMsgs()` 的 `pos` 为 0.001 rad 高速电机位置，不能按 0.001° 直接替代聚合角度。
- 本次默认实跑仍出现 `3A0..3A7` 聚合帧和运动期间间歇反馈；这与官方文档“升级后不应再出现 3A 偏移”的历史说明不一致，但固件查询确为 S-V1.9-1。需要继续做原始帧/时间对齐与状态解释，不能未经单位和协议验证修改驱动映射。

## 2026-09-25 修正自动路径日志措辞

- 实际 `restart_visual_sequence()` 已从当前反馈姿态直接请求观测轨迹，但启动输出仍写成“从零点移动”；已仅修正文案为“从当前反馈姿态移动到观测姿态”，未改变服务调用、目标值或运动逻辑。`bash -n` 通过，已同步实际脚本。

## 2026-09-25 原始帧同步采样与保护状态确认

- 无运动同步采样启动接收型 `piper_single_ctrl(auto_enable=false)`、`candump` 和 `/joint_states`；TX 仅增加 13 个查询/收尾帧。原始 CAN 在采样中稳定出现 `3A0..3A7`、`251..256`、`261..266`。3A4=`000000000000D053`、3A5=`FFFF531100000000`、3A6=`00003FAB00000000` 解码为当前六轴中的 J2=`0.930306`、J3=`-0.772263`、J5=`0.284320`，与官方 2A5/2A6/2A7 的 0.001° 单位一致；不能把 3A1..3A3 当作关节角。
- 官方低速反馈 `261..266` 六轴均为 23.0V、状态码 `0x40`（使能位真），碰撞、驱动错误、堵转和低压位均假；当前机械臂并非物理断电。
- 观测失败后的静态关节为 `[0, 0.930306, -0.772263, 0, 0.284320, 0]`，配置目标 `[0, 0.98, -0.75, 0, 0.30, 0]`，最大误差约 0.0497 rad，说明失败不是全零反馈；仍需在下一次受控运行中记录轨迹期间误差和反馈空窗。
- 最小代码动作：`visual_search_controller` 在 `PREPARE_EXECUTION_FAILED` 前增加只读 `max_joint_error`/最差关节日志；未改变目标、速度、反馈保护或停止逻辑。实际空间构建 `colcon build --packages-select brain_robot_pick_place --symlink-install` 返回 0。


## 2026-09-25 默认链首次完整进入 SEARCH/GRASP_READY，阻断定位到 MoveIt 抓取起始状态

- 实际命令：`timeout --signal=INT --kill-after=45s 360s env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`；脚本完成 `[7/7]`，输出“从当前反馈姿态移动到观测姿态”，随后实际日志出现 `OBSERVE_POSE_REACHED`、`STATE -> SEARCH (OBSERVE_POSE_REACHED)`、`STATE -> ALIGN (TARGET_ACQUIRED)` 和多次 `STATE -> GRASP_READY (DIRECT_VISUAL_ALIGN_ACQUIRED)`。这证明当前观测姿态、目标三维门控和搜索链已贯通，本轮不是点云/夹爪自体障碍阻断。
- 抓取执行器确实启动了多方向候选，但 MoveIt/IK 返回 `IK_ERROR_CODE_-31`，并伴随 `Unable to sample any valid states for goal tree`。失败日志中的 `current=(0.000, 0.000, 0.000)` 与真实反馈不一致；同一日志还报告 current-state 时间戳落后数秒，说明抓取规划读取了过期/默认状态。没有执行夹爪闭合、下降、抬升或释放。
- 驱动仍记录 2.6--10.2 秒级反馈空窗并在恢复后继续输出；无 `feedback absent for 25.0s`，can0 保持 `ERROR-ACTIVE`、RX 持续增长，根分区 28%。脚本结束时按保护逻辑停止视觉/Servo、disarm 适配器，明确未发送 `DisableArm`，未自动复位。
- 最小代码修复：抓取执行器的 IK、预抓取和笛卡尔规划不再直接采用 MoveIt 可能过期的 `getCurrentState()`；在已有 1 秒新鲜反馈门控后，从最近的六轴 `/piper_moveit_joint_states` 构造 `moveit::core::RobotState` 作为规划起始状态，缺少六轴或过期则拒绝规划。未改变候选姿态、碰撞检查、piper_jog_adapter 或反馈保护。
- 验证：同步规范源码与实际 `/home/johnwick/piper_ws`，`colcon build --packages-select brain_robot_pick_place --symlink-install` 返回 0，生成 `grasp_lift_executor`。

### 本轮结论与下一步

- 已把主要阻断从“未到观测/点云碰撞”缩小为“抓取规划起始状态与实体反馈不同步”。下一步运行同一默认自动链一次；只接受新鲜六轴状态下的候选 IK/规划结果，若仍为 `IK_ERROR_CODE_-31`，再按具体候选姿态几何调整，不能关闭碰撞检查或恢复腕部点云。

## 2026-09-25 新鲜状态修复后的默认链复核仍被反馈空窗阻断

- 实际再次运行 `timeout --signal=INT --kill-after=45s 360s env BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`。本轮通过 `[7/7]`、观测轨迹并实际出现 `STATE -> SEARCH (OBSERVE_POSE_REACHED)`、`SEARCH_PLAN_ACCEPTED`、`STATE -> ALIGN (TARGET_ACQUIRED)`；随后目标短暂丢失并进入 `LAST_PATH_REACQUIRE/LOCAL_SEARCH`。
- 驱动反馈空窗持续到搜索段门限，最终 `STATE -> FAULT (SEARCH_SEGMENT_FEEDBACK_TIMEOUT)`；没有进入 GRASP_READY，因此本轮没有执行候选 IK，也没有验证新鲜 RobotState 修复。
- can0 仍为 1 Mbps/0.75、RX 持续增长；根分区 28%，脚本保护收尾停止控制并保持使能，未发送 DisableArm/ResetPiper。

### 本轮结论与下一步

- 观测→搜索链仍可复现，当前直接阻断是实体反馈空窗，而不是点云自碰撞。新鲜状态修复已构建但需要下一次达到 GRASP_READY 才能验证；不通过提高速度或关闭碰撞绕过。

## 2026-09-25 新鲜起始状态修复后的第二次实跑仍受 CAN 聚合反馈空窗阻断

- 本轮默认脚本实际到达 `OBSERVE_POSE_REACHED → SEARCH → ALIGN`，随后因 `SEARCH_SEGMENT_FEEDBACK_TIMEOUT` 停止；未到 `GRASP_READY`，所以没有盲目调用抓取。
- 驱动在观测/搜索期间仍出现约 9.6、17.5、10.0 秒反馈空窗；can0 接口本身 RX 持续增长。保护收尾已停止视觉/Servo/适配器并保持 PiPER 使能，日志明确未发送 DisableArm，未自动复位。
- 本轮验证了观测姿态和搜索规划仍有效，但没有获得 `FreshMeasuredState` 的候选规划证据；抓取修复提交 `4ce272f` 保留待下一次稳定反馈窗口验证。

### 下一步

- 继续等待/复核实体聚合反馈在运动期间稳定后再跑一次；不把高速 0.001 rad 电机位置未经偏置/齿比验证替代聚合关节角，不关闭点云碰撞或反馈保护。

## 2026-09-25 抓取骨架收缩为单一路径

- 按目标将实体配置从多候选抓取切换为确定性主线：`candidate_grasp_enabled=false`、候选列表为空；保留视觉对齐点位、固定预抓取距离、受限微步靠近、闭合、抬升和释放。
- 已同步到 `/home/johnwick/piper_ws` 并构建 `brain_robot_ball_pick` 成功；未启动实体运动。
- 这样下一次实跑的验证目标明确为：`GRASP_READY → ALIGNED_PREGRASP → MICRO_APPROACH → GRIPPER_CLOSED → LIFT`，失败时只定位单一路径，不再在多个姿态候选间来回扭转。

## 2026-09-25 单一路径首次启动被空列表参数阻断

- 实跑在启动阶段未进入 `[7/7]`：`grasp_lift_executor` 因 ROS 参数 `candidate_grasp_order: []` 被解析为“未设置”而退出，脚本报告等待 `/grasp_lift_executor` 超时。没有发送观测或抓取动作。
- 最小修复：候选分支仍保持 `candidate_grasp_enabled=false`，将参数改为非空占位 `[NONE]`，以满足 ROS 参数类型/存在性要求；候选代码不会被调用。`brain_robot_ball_pick` 构建成功。

## 2026-09-25 单一路径配置后的实体复跑：观测反馈误差仍未收敛

- 抓取节点已正常启动，说明单一路径配置和 `[NONE]` 参数修复生效。默认自动链启动并接受当前姿态→观测姿态轨迹。
- 300 秒观测门控后仍失败：`Prepare execution did not converge: max_joint_error=0.037086 rad worst_joint=joint1`，随后 `STATE -> FAULT (PREPARE_EXECUTION_FAILED)`；因此本轮尚未进入 SEARCH/GRASP_READY，单一路径抓取未执行。
- 驱动期间仍有约 2.6、10、17 秒反馈空窗；脚本随后按保护逻辑停止控制、保持 PiPER 使能并未发送 DisableArm/ResetPiper。

### 结论

- 单一路径骨架已经接通到可启动状态，但当前更早的观测反馈误差仍阻断主线；不能把观测误差容差放宽来伪造到达。下一步应优先修复运动期间聚合反馈连续性，再验证 `GRASP_READY → ALIGNED_PREGRASP → MICRO_APPROACH`。

## 2026-09-25 修复运动期间CAN模式帧重复发送

- 代码审计发现：适配器以50 Hz发送绝对关节目标，而 `piper_ctrl_single_node.joint_callback()` 每次都重复发送 `MotionCtrl_2`。这会在每个关节目标周期额外占用CAN总线，能够解释“RX计数持续但运动反馈出现长空窗”。
- 最小修复：驱动缓存当前关节控制速度，只在速度变化时发送一次 `MotionCtrl_2`；绝对 `JointCtrl` 仍由既有适配器唯一输出，反馈保护和单位转换不变。
- 已同步规范源码与 `/home/johnwick/piper_ros`，`colcon build --packages-select piper --symlink-install` 和 `py_compile` 均成功。

## 2026-09-25 CAN模式去重后进入GRASP_READY，暴露出抓取Z几何错误

- `c601cc8` 生效后，默认链在约15秒观测轨迹后稳定进入 `OBSERVE_POSE_REACHED → SEARCH → ALIGN → GRASP_READY`；驱动本轮仅出现一次0.09秒反馈恢复，未再出现10--17秒空窗。
- 单一路径确实调用了 `ALIGNED_PREGRASP`，但目标日志显示 `target z=0.038 m`，明显低于桌面；MoveIt 正确返回 `IK_ERROR_CODE_-31`，不是点云碰撞。
- 最小修复：实体配置加入 `grasp_height_offset_m: 0.16`，使侧向预抓取保持在桌面上方；已构建 `brain_robot_ball_pick`。

## 2026-09-25 预抓取已规划成功，视觉重捕获抢占抓取控制

- `c601cc8` 后实跑稳定到达 `OBSERVE_POSE_REACHED → SEARCH → ALIGN → GRASP_READY`；本轮单一路径的 `ALIGNED_PREGRASP` 已多次成功规划并由 `piper_jog_adapter` 接受（21/56/32个轨迹点）。
- 轨迹刚接受后，视觉控制器因腕部相机运动产生的目标视差触发 `GRASP_READY_TARGET_SHIFT`，重新进入 ALIGN/SEARCH，抓取执行器因此收到 `ALIGNED_PREGRASP_PLAN_FAILED`，尚未进入微步靠近、闭合或抬升。
- 最小修复：加入 `freeze_grasp_tracking=true`；GRASP_READY 后视觉控制器不再抢回对齐控制。抓取执行器在预抓取到达后使用 `approach_locked_`，只要求目标点/深度/有效标志新鲜，不再把正常视差当成对齐误差。已构建 `brain_robot_pick_place` 与 `brain_robot_ball_pick` 成功。

## 2026-09-25 f7059ce 后默认自动链实跑：观测已达，搜索被反馈门控安全停止

- 实际命令仍为 `BRAIN_ROBOT_AUTO_START=1 /home/johnwick/start_brain_robot_cube_real.sh`，单一运行完成 `[7/7]`，并明确记录 `STATE -> SEARCH (OBSERVE_POSE_REACHED)`。
- 本轮检测器在启动阶段短暂 `PURPLE_CUBE target DETECTED`，进入观测运动后变为 `target LOST`；之后没有达到目标稳定帧、`ALIGN` 或 `GRASP_READY`。因此没有下发预抓取、微步、闭合、抬升或释放动作，不能把背景颜色当成抓取授权。
- 搜索轨迹规划本身多次成功并由适配器接受；但驱动在搜索中再次出现连续反馈空窗，最终日志给出 `can0 feedback absent for 25.0s`、`STATE -> FAULT (SEARCH_SEGMENT_FEEDBACK_TIMEOUT)`，适配器随后 `PHYSICAL MOTION DISARMED: joint state timeout`。这次阻断是实际反馈新鲜度门控，磁盘使用率仅 28%，不是磁盘空间或点云自碰撞证据。
- 保护收尾停止视觉/Servo/适配器并保持当前位置，未发送 `DisableArm`、`ResetPiper` 或 `MasterSlaveConfig`。保留 `freeze_grasp_tracking` 与 `FreshMeasuredState` 修复，待下一次稳定反馈窗口再验证 `GRASP_READY → ALIGNED_PREGRASP → MICRO_APPROACH`。

## 2026-09-25 搜索循环与基座三维目标锁定修复

- 用户反馈要求目标丢失后必须继续搜索，且腕部相机随抓取运动时不能把目标视差当成目标移动。代码复核确认搜索状态本来会在 `SEARCH` 段完成后 `FULL_SEARCH_CYCLE_RESTART`；上一轮“没有动”实际是搜索段等待真实六轴反馈，反馈失效后安全停止。
- 最小实现：抓取执行器在 `GRASP_READY` 启动确定性抓取时，将最新稳定的目标点变换并快照到 `lift_reference_frame`；`BuildAlignedPointGrasp` 和微步预测在模型锁定后只使用该基座三维点，不再读取腕部相机移动后的新点。到达预抓取后，对齐判断只验证已锁模型，不因视差/短时颜色深度丢帧重新 ALIGN/SEARCH；锁模前仍要求真实目标、稳定深度和尺寸门控。
- 同步规范源码与 `/home/johnwick/piper_ws`，`colcon build --packages-select brain_robot_pick_place --symlink-install` 成功；未关闭碰撞检查、未恢复腕部点云、未改变适配器唯一输出。

## 2026-09-25 新锁模代码后的默认自动链实跑

- 新轮脚本实际通过 `[7/7]`、`OBSERVE_POSE_REACHED` 并进入 `SEARCH`；日志出现多次 `SEARCH_PLAN_ACCEPTED` 和 `FULL_SEARCH_CYCLE_RESTART`，证明目标丢失后的搜索运动链在工作。
- 本轮检测器只报告 `PURPLE_CUBE target LOST`，没有颜色/矩形/稳定深度/尺寸同时满足的目标帧，因此没有 `ALIGN`、`GRASP_READY`、`GRASP_TARGET_MODEL_LOCKED` 或任何靠近/闭合动作；不能把背景紫色误当成方块。
- 本轮 CAN 仅有一次 0.48 秒反馈恢复，未出现 25 秒反馈故障；脚本在 360 秒上限后按保护逻辑保持位置与使能，未发送 `DisableArm`、`ResetPiper` 或 `MasterSlaveConfig`。根分区 28%。
- 下一步仍是同一主线：在目标进入视野并通过三维门控后验证 `GRASP_READY → GRASP_TARGET_MODEL_LOCKED → ALIGNED_PREGRASP → MICRO_APPROACH → GRIPPER_CLOSED → LIFT`；不再因腕部相机视差重定位。

## 2026-09-25 搜索实体运动证据与新一轮启动阻断

- 用户指出“规划接受”不等于肉眼看到关节扫动。现有日志能确认适配器收到多次 `REAL ARM trajectory accepted: 7 points`，但未保存最终 J1/J5 目标与反馈误差；因此后续验证必须同时采集 `/brain_robot_visual_control/command_diagnostic`，不能仅凭 `SEARCH_PLAN_ACCEPTED` 宣称实体扫动。
- 上一轮 `auto9` 明确出现 `SEARCH (OBSERVE_POSE_REACHED)`、`FULL_SEARCH_CYCLE_RESTART` 和多次搜索轨迹接受，未出现 `GRASP_READY`；检测器全程只有 `PURPLE_CUBE target LOST`。该轮按 360 秒保护上限结束，未失能。
- 随后的诊断轮未进入运动：启动阶段相机到基座 TF 心跳超时，脚本在 `[5/7]` 安全停止，未发送运动或失能命令。
- 下一步只在 TF 心跳恢复后，采集搜索诊断中的实际关节目标/反馈，再决定是否修正搜索执行；不把接受消息当作完成证据。

## 2026-09-25 搜索实体关节反馈定量验证

- 延迟订阅 `/brain_robot_visual_control/command_diagnostic` 后，搜索段实际发布非零目标：`J1=-0.080→-0.155→-0.231`，随后 `J1=-0.303→-0.372`；对应 `J5=0.391→0.454→0.531→0.606→0.685`。这不是零速度原地等待。
- 同轮 `/piper_moveit_joint_states` 实测反馈为 `joint1=-0.370964104`、`joint5=0.68485144`，相对观测起点 `[0,0.30]` 已发生明显扫动；适配器也记录了多次 7 点轨迹接受。
- 扫到该位置后约 60 秒未获得控制器认可的新鲜目标反馈，进入 `STATE -> FAULT (SEARCH_SEGMENT_FEEDBACK_TIMEOUT)`；检测器仍只有 `PURPLE_CUBE target LOST`，未进入 ALIGN/GRASP_READY。故当前“停止”是反馈保护触发，而非搜索逻辑等待目标。
- 不修改为无反馈持续运动；下一步若要提高肉眼连续性，只能在保持每段反馈确认的前提下调整搜索节拍/步长，不能绕过 25/60 秒安全门。

## 2026-09-25 PiPER 用户手册 V1.1.0 与现场照片核对

### 手册明确事实（不等同于当前固件实测）

- 资料：`reference/vendor_docs/PiPER机械臂用户手册V1.1.0.pdf`，PDF 57 页，SHA-256 `fef09a25beaa23b9f0f9c7d3c4fc584a107146a64f19a73388c379d02ae64122`；PDF 未复制进 Git。手册版本是用户手册版本，不是当前 S-V1.9-1 固件版本。
- 规格页给出的六轴机械限位：J1 `±154°`，J2 `0°~195°`，J3 `-175°~0°`，J4 `-102°~102°`，J5 `-75°~75°`，J6 `±120°`。规格页还列出额定负载 1.5 kg、臂展 626.75 mm、DC24 V 供电和最大功率/速度等参数。
- CAN 协议页明确：CAN 2.0B，速率 `1000K`（1 Mbps），字节序标注为 `MOTOROLA (MSB)`。这只说明官方手册接口规格，不证明当前 USB-CAN/VMware 链路每个时刻都满足反馈新鲜度。
- 目录明确包含“CAN 连接与准备”“上位机使用说明”“二次开发”“机械臂 CAN 协议”“紧急情况处理”，其中紧急处理分为“断电”和“急停”。这些章节的关键正文在图形/不可检索文本中；本轮没有从不可读文字推断使能、失能或急停顺序。

### 现有代码推断/实现（不能冒充手册事实）

- `start_brain_robot_cube_real.sh` 当前将 can0 配置为 1 Mbps、采样点 0.75，并在 `[7/7]` 后自动调用使能服务和视觉控制器；默认路径是当前反馈姿态→观测姿态，不执行绝对零点复位。
- `visual_search_controller` 的真实搜索仍以 `cube_task_real.yaml` 为准：仅允许 J1/J5 搜索，现有软件范围 J1 `[-1.50,1.50]`、J5 `[-0.60,0.95]`，规划步长 0.08 rad、每段经 MoveIt 碰撞检查后交给 `piper_jog_adapter`；本轮没有根据照片扩大或重设计这些范围。
- `cube_visual_search.launch.py` 将视觉控制器的 `/joint_states` remap 到 `/piper_moveit_joint_states`；搜索是否继续由新鲜关节反馈门控。无新鲜反馈时进入保护故障，不允许仿真式盲转。
- 抓取器在 `GRASP_READY` 时锁定一次 `base_link` 三维目标模型，预抓取/微步不再使用腕部相机运动后的新像素点；这属于代码设计，不是手册声明。
- 代码的停止路径保持 PiPER 使能并停止视觉/适配器，未调用 `DisableArm`；这一安全选择来自仓库既有决策，不把它描述为手册原文。

### 现场照片布局证据（不改变参数）

- 照片显示真实 PiPER 六轴臂安装在桌面，腕部末端安装 RGB-D 相机/夹爪组件，光轴朝向斜下方；紫色方块位于画面右下方桌面区域，明显不在当前末端组件的中心轴线上。
- 该照片支持“腕部相机随关节运动会产生视差、目标应在 `GRASP_READY` 后使用基座三维快照”的实现判断；它不足以单独给出相机内参、外参、方块深度或安全搜索边界，因此不据此改 J1/J5 范围。
- 当前脚本停止后只读检查仍能看到相机 `camera_info`/调试图像话题；`/joint_states` 由驱动停止而不存在，不能把停止状态误判为硬件失能。

## 2026-09-25 现场照片与实际相机参数只读核对

- 现场照片显示：腕部相机与末端沿同一组件安装，光轴斜向桌面；紫色方块位于画面右下方桌面区域，未处于末端当前中心轴。该证据只用于布局核对，不直接换算 J1/J5 搜索范围。
- 相机 `/camera/color/camera_info` 实测：分辨率 `640x400`，`frame_id=camera_color_optical_frame`，`distortion_model=plumb_bob`，`fx=488.8685`、`fy=488.8685`、`cx=310.7305`、`cy=209.0377`；D 五项为 0。
- 脚本停止后的只读 ROS 图中仍有 camera_info/debug_image，但没有 `/joint_states`、`/piper_moveit_joint_states` 或目标话题发布者；这与驱动/检测器已安全停止一致，不作为失能或目标不存在的硬件结论。
- 未根据照片或内参改动 `cube_task_real.yaml` 搜索边界；继续遵循现有高级轨迹主线。


## 2026-09-25 实体模型复跑与连续搜索修复

- 默认脚本本轮已实际通过 `[7/7]`、`OBSERVE_POSE_REACHED` 并进入 `SEARCH`；RGB 与深度首帧均通过，实测相机深度约 30 Hz。
- 之前 `[6/7]` 长时间等待的直接原因是 Astra USB 接口争用：日志出现 `attempt to claim already-claimed interface`、损坏 JPEG，`/camera/depth/image_raw` 无实际帧。停止未使能的残留视觉/驱动进程并重启 Astra 后，RGB-D 检测器恢复 `debug_image` 首帧。
- 搜索期间实际反馈从观测姿态扫到 `joint1≈-0.533 rad`、`joint5≈0.814 rad`，说明已有真实关节运动；检测器本轮仅 `PURPLE_CUBE target LOST`，未产生有效目标/对齐/抓取授权。
- 搜索控制器曾在最后一个段目标未收敛时保持约 60 秒，最终 `SEARCH_SEGMENT_FEEDBACK_TIMEOUT`，造成用户看到“转到固定角度后停下”。已将搜索段超时改为：若六轴反馈仍新鲜则立刻反向继续有限搜索；只有反馈过期才保护故障。配置 `search_segment_timeout_s` 改为 15 s；未绕过适配器、碰撞检查或反馈看门狗。
- 新增启动门控：连续三帧 `/joint_states` 与 `/piper_moveit_joint_states`、实际 `/tf` 基座链，以及 RGB/深度首帧；禁用的腕部点云仍不进入 Octomap。

### 本轮阻断

- 当前尚未达到 `ALIGN/GRASP_READY`：现场帧未通过紫色方块颜色/矩形/稳定深度/尺寸门控；上一轮反馈保护在搜索段超时。下一轮必须验证连续反向搜索和目标门控，不得把背景紫色当作方块。


## 2026-09-25 连续搜索修复实体验证

- 提交 `f530041` 后默认脚本再次完整通过 `[7/7]`、`OBSERVE_POSE_REACHED`、`SEARCH`；RGB/深度首帧与调试图像首帧均通过。
- 搜索日志连续出现大量 `SEARCH_PLAN_ACCEPTED`（每段 7/8 点），并出现 `SEARCH_SEGMENT_TIMEOUT_CONTINUE` 与 `FULL_SEARCH_CYCLE_RESTART`，证明 J1/J5 已按有限 MoveIt 轨迹持续扫动，不再固定停在第一组角度。
- 本轮检测器仍只有 `PURPLE_CUBE target LOST`，没有 `target_valid`、`ALIGN` 或 `GRASP_READY`；未发送靠近、闭合、抬升或释放。
- 最终阻断是 `can0 feedback lost` 持续 25 s，驱动按保护策略停发，控制器进入 `JOINT_STATE_TIMEOUT`。这发生在连续搜索已生效之后，不是碰撞模型或搜索停滞。
- 复跑结束后已停止脚本启动的视觉/驱动进程，保持现有安全收尾规则；未调用 `DisableArm`、`ResetPiper` 或 `MasterSlaveConfig`。


## 2026-09-25 连续搜索后的当前硬门槛

- 连续搜索实跑结束后只读检查 `can0` 仍为 `ERROR-ACTIVE`、1 Mbps/0.75，但 3 秒 RX 增量为 `0`；当前没有稳定实体反馈。
- 按既有规则不再启动驱动/视觉运动、不重复 USB-CAN 重载或底层巡检；等待物理链路恢复 `can0 UP + RX 增长` 后复用已提交的默认链。
- 当前目标尚未完成抓取：本轮已证明搜索连续轨迹工作，但未获得紫色方块有效门控，且最终反馈保护阻断了继续运动。


## 2026-09-26 断点恢复检查

- 按规范恢复读取后，当前 `can0` 为 `UP/ERROR-ACTIVE`、1 Mbps/0.75，但 3 秒 RX 增量仍为 `0`；没有 `/piper_single_ctrl`，无实体运动命令。
- 清理了上一轮遗留的无驱动 MoveIt/Servo/适配器/图像查看进程；未调用 Enable/Disable、ResetPiper 或 MasterSlaveConfig。
- 本轮未启动默认脚本，原因是 RX=0 硬门槛未满足。目标仍停在“连续搜索已验证、等待物理反馈恢复”，尚未进入紫色方块抓取。

## 2026-09-26 定向 USB-CAN 复位后的实测

- 新增证据：内核在 `xhci_hcd 0000:03:00.0` 持续报告 event-DMA/TRB 错误；USB-CAN 仍枚举为 `1d50:606f candleLight`，因此只做了一次针对 `003/011` 的设备级 USB reset，未启动驱动、未发送运动命令。
- reset 后按规范恢复 `can0`：1 Mbps、sample-point 0.75、txqueuelen 1000；接口回到 `UP/ERROR-ACTIVE`，但连续 5 秒 RX 增量仍为 `0`（reset 前累计计数 `16141632`，reset 后新计数从 0 起）。
- 结论：定向 USB reset 没有恢复实体反馈；当前阻断仍是 USB-CAN/VMware 透传或机械臂控制器物理链路，而不是搜索轨迹、点云碰撞或目标算法。按硬门槛不启动默认脚本，避免无反馈运动。
- 下一步：保留此次唯一新复位证据；只有 `can0` RX 持续增长才复用既有自动链，不能再次重复同类 reset 或刷写固件。

## 2026-09-26 RX=0 只读链路确认

- `candump -L can0` 监听 5 秒无任何帧；`ip -details -statistics` 显示 RX bytes/packets/errors 全为 0，CAN 仍 `ERROR-ACTIVE` 且无 bus-off/error-warn/error-pass 计数。
- reset 后 xHCI event-DMA/TRB 错误仍持续出现。USB 设备虽枚举、接口虽 UP，但当前没有机械臂控制器反馈帧；不是视觉检测器或点云碰撞阻断运动。
- 继续保持 RX=0 硬门槛：不启动默认脚本、不使能/失能、不发送 CAN 运动命令；待透传/控制器链路恢复并出现持续 RX 后再执行高级主线。

## 2026-09-26 用户修复后的 CAN 反馈恢复

- 适配器已重新枚举为 USB `003/014`；恢复 can0 为 1 Mbps、sample-point 0.75、txqueuelen 1000 后，8 秒 RX 从 `724` 增至 `149612`（增量 `148888`）。接口 `UP/ERROR-ACTIVE`，无 bus-off/error-pass 计数。
- 反馈硬门槛已满足；下一步直接运行 `/home/johnwick/start_brain_robot_cube_real.sh` 默认自动路径，验证 `OBSERVE_POSE_REACHED → SEARCH → ALIGN/GRASP_READY`，不重复底层实验。

## 2026-09-26 自动链实跑：目标抖动触发回退环

- CAN 恢复后默认脚本实际通过 `[7/7]`、观测姿态并进入 `SEARCH`；检测器确实反复报告 `PURPLE_CUBE target DETECTED/LOST`。
- 日志没有 `MOVEIT_SERVO_HARD_STOP`、碰撞规划失败或硬件碰撞故障；相反，控制器连续执行 `ALIGN (TARGET_REACQUIRED_ON_LAST_PATH)` → `LAST_PATH_REACQUIRE`，适配器反复接受 2 点回退轨迹。目标帧在运动期间抖动，未满足连续 `align_stable_frames`，所以没有进入 `GRASP_READY`。
- 用户中止后脚本明确记录“保持当前位置、未发送 DisableArm”；适配器日志的 `PHYSICAL MOTION DISARMED: operator disarm` 对应本次 Ctrl+C 收尾，不是代码检测到的关节碰撞失能。
- 最小修复：`visual_search_controller` 在 ALIGN 丢帧后新增 `target_loss_grace_s=0.80`，短暂 RGB-D 丢帧只发布零速度保持当前对齐姿态；超过该窗口才允许 LAST_PATH_REACQUIRE。已同步运行时工作区，`colcon build --packages-select brain_robot_pick_place brain_robot_ball_pick --symlink-install` 成功。
- 下一步：在 CAN RX 持续窗口重跑同一自动链；验证目标稳定时是否从 ALIGN 进入 `GRASP_READY`，不再因单帧丢失立即缩回。

## 2026-09-26 修复后复跑的实际阻断

- 修复后的第二轮已通过 `[7/7]`，适配器日志确认先 `PHYSICAL MOTION ARMED` 并接受观测轨迹；但从当前姿态到观测姿态的 `PREPARE` 在本轮 300 秒保护上限内未发布 `OBSERVE_POSE_REACHED`，因此没有进入搜索或抓取。
- 结束时脚本保护清理产生 `PHYSICAL MOTION DISARMED: operator disarm`；日志没有 MoveIt 碰撞失败、Servo hard stop 或关节碰撞故障。该失能是超时/退出收尾，不是目标靠近阶段触发的碰撞结论。
- `target_loss_grace_s=0.80` 已构建生效，但本轮尚未到 ALIGN，尚未验证其对回退环的效果。下一步先在现有反馈窗口完成观测姿态，再观察 `ALIGN → GRASP_READY`。

## 2026-09-26 官方/GitHub 资料核对

- AgileX 官方 `agx_arm_ros` 文档明确：Piper 通过 `feedback_topic` 接入 MoveIt，`control_topic` 只能保持单一控制源；启动参数包含 `speed_percent`，默认自动使能，且 `can_port:=can0`、`arm_type:=piper` 是实体启动参数（https://github.com/agilexrobotics/agx_arm_ros）。现有链路遵守单一 `piper_jog_adapter` 输出与真实反馈门控。
- AgileX 官方 `piper_ros` MoveIt 文档列出实体关节限位与速度上限（J1/J2/J3/J4/J5/J6 最高 3 rad/s），并说明 MoveIt 的 `Plan&Execute`/关节目标路径；现有适配器的 0.189 rad/s 是保守软件上限，不是固件限位（https://github.com/agilexrobotics/piper_ros/blob/noetic/src/piper_moveit/README.md）。
- 官方 MoveIt Servo 文档定义 `DECELERATE_FOR_COLLISION`、`HALT_FOR_COLLISION`、`JOINT_BOUND` 状态；本轮日志未出现这些状态，故不能把回退环归因于 Servo 碰撞（https://moveit.picknik.ai/humble/api/html/status__codes_8h.html）。
- 官方 `pyAgxArm` 固件参考要求按实际固件选择 SDK 路由；S-V1.8-9 及以上使用 `v189`，并明确通过 `get_firmware()` 读取版本。当前仓库仍以已记录的 S-V1.9-1/DRV 2.0.8 为准，不执行刷写或旧版本实验（https://github.com/agilexrobotics/pyAgxArm/blob/master/docs/piper/firmware_reference.md）。

## 2026-09-26 执行权限恢复前的反馈复核

- 执行环境许可恢复后只读复核：`can0` 为 1 Mbps / sample-point 0.75 / `UP,ERROR-ACTIVE`，无 bus-off/error-pass；RX 在 3 秒内从 `7836366` 持续增长 `56068`。
- 已满足实体运动反馈门槛；下一动作是一次 420 秒上限的默认自动链，验证慢速 current-pose→observe 轨迹是否收敛，然后验证已编译的 ALIGN 丢帧保持逻辑。

## 2026-09-26 自动链启动门控复核

- 420 秒链本轮未发送运动：脚本在 `[4/7]` 等待 `/pointcloud_tf_gate` 超时。随后对同一 launch 做了 12 秒 disarmed 诊断，确认 `pointcloud_tf_gate`、`/brain_robot_vision/tf_gate_diagnostic` 和 `/brain_robot_vision/tf_validated_points` 均能正常出现。
- 诊断发现此前遗留的 MoveIt/视觉进程造成 ROS 图重复节点；已仅停止这些 disarmed 诊断进程，未停止 PiPER 驱动、未发送 CAN 运动命令。下一步复用默认脚本，避免重复启动栈。

## 2026-09-26 GRASP_READY 后预抓取执行失败修复

- 清理重复栈后默认链已实际达到 `OBSERVE_POSE_REACHED → SEARCH → ALIGN → GRASP_READY`，并发布/接受 `ALIGNED_PREGRASP` 22 点轨迹。
- 失败发生在轨迹执行反馈确认窗口：`ALIGNED_PREGRASP_PLAN_FAILED` 后日志出现 `IK_ERROR_CODE_-31`，随后原代码清除基座目标锁并重新读取腕部相机点，导致目标从 z≈0.186 m 跳到 z≈0.068 m，形成反复重规划；没有 Servo `HALT_FOR_COLLISION` 或关节碰撞状态。
- 最小修复：GRASP_READY 后保持已锁定的 base-frame 目标；预抓取执行失败时最多从最新实测关节状态重试同一目标一次，第二次才安全 `FAIL`，不再请求视觉 ALIGN/SEARCH。已同步运行时工作区并成功构建 `brain_robot_pick_place`。

## 2026-09-26 预抓取反馈等待与官方速度上限对齐

- 锁定目标重试实跑显示两次轨迹均被 `trajectory_feedback_timeout_s=12.0` 截止；适配器仍只按实测 `0.189 rad/s` 限速输出，日志没有碰撞/Servo hard-stop。
- 根据 AgileX 官方 Piper MoveIt 文档的速度参数语义，最小调整实体抓取反馈等待为 `45.0 s`，不提高实体速度、不绕过反馈，只给保守限速轨迹足够完成时间；`brain_robot_ball_pick` 已成功构建。

## 2026-09-26 xHCI 主控失效阻断

- 45 秒配置后的下一轮在启动前即发现 `can0` 不存在，未发送运动命令。内核新增明确证据：`ERROR Transfer event TRB DMA ptr not part of current TD`，随后 `xHCI host not responding to stop endpoint command`、`HC died; cleaning up`；USB-CAN `1d50:606f` 与相机设备同时断开。
- 脚本按 RX/接口硬门槛安全停止，未进入 `[2/7]` 之后的机械臂控制。当前最大阻断是 VMware/USB xHCI 主控失效，不能靠视觉、MoveIt 或抓取代码修复；恢复 USB 主控和 `can0` 持续 RX 后再复用 `2856a48` 之后的抓取链。

## 2026-09-26 xHCI 驱动重载后的恢复结果

- 只执行一次 `modprobe -r xhci_pci` / `modprobe xhci_pci`。USB 总线重新枚举，candleLight `1d50:606f` 回到 `003/006`，Astra 设备也回到 `003/007`、`003/009`；`can0` 恢复为 1 Mbps/0.75 `ERROR-ACTIVE`。
- 但恢复后的 5 秒 CAN RX 仍为 `0`，只读 `candump` 也无帧；因此没有启动驱动或运动。当前剩余阻断是实体 PiPER 控制器/供电/CAN 总线未产生反馈，不能把 USB 枚举误当成可运动。

## 2026-09-26 USB-CAN 绑定与被动总线复核

- `can0` 已确认绑定内核 `gs_usb`，设备为 `1d50:606f candleLight`，接口 `UP/ERROR-ACTIVE`、1 Mbps/0.75；错误计数和 bus-off/error-pass 均为 0。
- 被动 `candump -L can0` 8 秒无任何帧，RX bytes/packets 仍为 0。说明问题不在 Linux 驱动绑定或 CAN 参数，而在控制器/供电/实体 CAN 总线没有发送反馈。
- 继续禁止启动 PiPER 驱动和运动命令；只有总线出现持续 RX 才继续既有自动抓取链。

## 2026-09-26 USB-CAN 被动诊断补充

- `can0` 的 sysfs 设备路径为 `/sys/devices/.../usb3/3-1.2:1.0`，`udevadm` 显示 `DRIVER=gs_usb`，USB power control 为 `on`。
- 复核快照：`ERROR-ACTIVE`、1 Mbps / sample-point 0.750，错误计数全 0，RX/TX bytes 与 packets 均为 0；未启动 PiPER 驱动或一键运动脚本。
- 判断：Linux 端设备已恢复但实体控制器没有反馈，当前不能安全验证观测/搜索/抓取；待 CAN RX 持续增长后再运行默认链。
-
- 运行时 brain_robot_pick_place 已成功构建；未刷写固件、未执行 MasterSlaveConfig/ResetPiper。
- 最小改动：真实配置 align_stable_frames=1、target_loss_grace_s=2.0；抓取执行器新增 static_target_lock=true，锁定后跳过预抓取后的 TargetStillAligned 检查和视觉重捕获，仅按锁定模型完成预抓取/微接近。
- 本轮实体运行已达到 OBSERVE_POSE_REACHED -> SEARCH -> ALIGN -> GRASP_READY，目标基座模型成功锁定；失败发生在锁定预抓取执行反馈未收敛，未出现碰撞或视觉重规划证据。
## 2026-09-26 静止目标单次锁定抓取简化
## 2026-09-26 静态锁定验证与 CAN 瞬时重枚举

- 新静态锁定代码已成功构建；首次重跑在 CAN 初始化阶段遇到 USB-CAN 瞬时 No such device，脚本未发送运动命令。
- 一键脚本加入 5 次有限 can0 重枚举/配置重试；恢复后仍必须通过持续 RX 门控，才允许进入运动。
## 2026-09-26 xHCI 重载后 CAN 节点恢复但 RX 仍为零

- 第二次默认脚本未发送运动命令；CAN 初始化时 USB-CAN 节点瞬时失活，有限重试后仍无法启动。
- 受限重载 xhci_pci 后 candleLight 重新枚举，can0 恢复 ERROR-ACTIVE/1 Mbps，但 5 秒 RX 增量为 0；按硬门控不启动 PiPER 驱动或静态抓取链。
## 2026-09-26 静态锁定验证被反馈门控阻断

- CAN 初始化通过且 5 秒 RX 增加 93004 bytes；自动链接受观测轨迹，但 300 秒后 J2 最大误差 0.210580 rad，进入 PREPARE_EXECUTION_FAILED。
- 同期 PiPER 驱动记录 can0 feedback lost 25.0s，随后保持 receive-only；适配器因 joint state timeout 失能。未进入 SEARCH/GRASP，未发送额外运动命令。
## 2026-09-26 一键启动脚本演示校验

- 已验证运行入口 /home/johnwick/start_brain_robot_cube_real.sh 语法通过，默认 BRAIN_ROBOT_AUTO_START=1；[1/7] 至 [7/7] 门控完整，自动路径调用 visual_search_controller/start，从当前反馈姿态移动到观测姿态，不调用零点 reset。
- 当前脚本无残留控制进程；演示校验未发送运动命令。
## 2026-09-26 静态锁模提前到夹爪动作前

- 实跑曾在 GRASP_READY 后因夹爪打开等待期间的 TargetStillAligned 检查重新进入 ALIGN；这与静止目标策略冲突。
- 修复：static_target_lock=true 时在打开夹爪前立即保存 base-frame 目标，后续不再执行预抓取前视觉校验或重捕获；运行时已在 piper_ws 正确工作区成功构建。
## 2026-09-26 新构建验证再次被 CAN 失活阻断

- 新构建已加载到正确的 piper_ws 工作区；旧实例曾实际达到 GRASP_READY，但第一次锁模前视觉校验触发回退，已在 025597f 修复。
- 重启新实例前 USB-CAN 再次出现 lsusb 可见但 can0 无法 up 的失活；xHCI 重载后接口 ERROR-ACTIVE 但 5 秒 RX=0，因此未启动新运动链。
## 2026-09-26 新一键实例启动中断记录

- 本轮恢复 can0 后，5 秒 RX 增加 97052 bytes，ERROR-ACTIVE；一键脚本通过 [1/7] 并启动 PiPER 驱动。
- 随后监测调用被外部中断，当前无 start_brain_robot_cube_real、驱动、视觉控制器、抓取执行器或适配器残留进程；日志没有本新实例的观测/搜索/抓取轨迹记录。
- 决策：不把中断误报为抓取失败；下次仅在 CAN RX 持续增长时启动唯一默认链，验证 025597f 的夹爪前静态锁模。

## 2026-09-26 默认链实际推进：DDS 初始化修复、SEARCH/GRASP_READY 已复现，抓取姿态仍需可达解

- 实际环境：`/mnt/hgfs/ub`；根分区 28%，约 55 GB 可用；`sudo -n true` 返回 0；`can0` 经一次 `gs_usb` 重枚举后恢复 `ERROR-ACTIVE`、1 Mbps、sample-point 0.750；5 秒 RX 从 123 增至 12326，未发送运动命令期间 TX 为 0。
- 直接阻断定位：此前 PiPER 驱动 Python 进程存活但无 AF_CAN 描述符；`gdb` 线程栈显示主线程卡在 Fast DDS SHM participant 建构，`/proc/<pid>/fd` 只有 UDP/共享内存描述符，没有 CAN。磁盘实际 28%，排除磁盘不足。
- 最小修复：新增 `brain_robot_arm/scripts/fastdds_udp_only.xml`，并在规范/实际 `/home/johnwick/start_brain_robot_cube_real.sh` 导出 `FASTRTPS_DEFAULT_PROFILES_FILE`，禁用 Fast DDS SHM、仅使用 UDPv4；无运动 `auto_enable=false` 驱动探针首次发布完整非零 `/joint_states`，`/enable_srv` 在重建 ROS CLI daemon 后可发现。
- PiPER 驱动接收回调仍保持此前 S-V1.9-1 `3A0..3A7 -> 2A1..2A8` 映射，未刷写固件、未执行 MasterSlaveConfig/ResetPiper；实际运行脚本使用 `piper_jog_adapter`，没有绕过控制链。
- 一键脚本实际证据（`timeout 600s /home/johnwick/start_brain_robot_cube_real.sh`）：两次完整通过 `[1/7]`、相机 RGB/深度门控、`[7/7]`、当前反馈姿态→观测轨迹、`OBSERVE_POSE_REACHED`、`STATE -> SEARCH`、连续 `SEARCH_PLAN_ACCEPTED`、`STATE -> ALIGN (TARGET_ACQUIRED)`、`STATE -> GRASP_READY (DIRECT_VISUAL_ALIGN_ACQUIRED)`。搜索轨迹确实由适配器连续接受，非固定角度停住。
- 目标证据：检测器日志出现 `PURPLE_CUBE target DETECTED`；抓取执行器锁定 base-frame 静态目标，如 `(-0.117,-0.039,0.252)`，未因腕部相机丢帧重新对齐。
- 本轮抓取阻断：历史“保持观测姿态方向的侧向预抓取”返回 `IK_ERROR_CODE_-31`；将已存在的 `BuildTopDownPointGrasp` 接到静态 base-frame 锁定目标并启用四 yaw 候选后，实跑仍报告 `No top-down yaw candidate has an IK solution`。没有发送闭合、下降、抬升或释放命令；脚本保护退出保持使能，未调用 `DisableArm`。
- 为避免错误的视觉重对齐，抓取源码新增 `static_target_lock_ && target_model_locked_` 短路；顶部构造改用 `PredictedTargetInReference()` 的锁定 base-frame 点。顶部配置当前显式为 `top_down_grasp_enabled: true`、`top_down_pregrasp_clearance_m: 0.08`、`top_down_grasp_clearance_m: 0.018`、四 yaw 候选；该路径已编译但实体 IK 尚未通过，不能宣称抓取完成。
- 相机曾有一次旧 Astra 组件导致深度首帧延迟；停止旧 component container 后由脚本健康守护恢复，随后深度门控通过。不是点云写入 Octomap：MoveIt 日志显示 `No 3D sensor plugin(s) defined for octomap updates`，腕部点云仍为诊断心跳。
- 验证命令/结果：`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回 0；`cmp` 确认规范与实际抓取源码/配置一致；运行日志见 `/home/johnwick/brain_robot_logs/visual_stack.log`、`cube_detector.log`、`piper_driver.log`。
- 当前状态：无一键脚本、PiPER 驱动或视觉栈残留；can0 需要下次启动前复核 RX。允许继续真实运动的前提仍是反馈新鲜、适配器 arm 已通过；抓取姿态必须先得到 MoveIt IK/规划通过证据。
- 下一步：优先在不发送运动的前提下针对锁定目标筛选可达末端姿态/路径（确认 `gripper_base` 工具轴与目标 base_link 几何）；然后只在 MoveIt 规划成功后再次运行默认链验证 `GRASP_READY -> PREGRASP -> CLOSE -> LIFT -> RELEASE`。

## 2026-09-26 提交后收尾

- 本轮提交：`c23fcbc fix: avoid DDS SHM startup deadlock and lock grasp target`。
- 提交后实测：`can0` 当前 `ERROR-ACTIVE`、1 Mbps/0.750、RX 10,375,341 packets、errors/dropped 0；`sudo -n true` 返回 0；无 `start_brain_robot_cube_real`、PiPER 驱动或视觉栈残留进程。
- 工作区仍有 123 个既有用户/供应商映射文件修改和 `reference/`/deb 未跟踪项，本轮未暂存、未覆盖、未回滚；本提交仅包含 7 个本轮文件。
- 下一次第一条命令：`cd /mnt/hgfs/ub && git show --stat --oneline HEAD && ip -details -statistics link show can0`；随后在不运动的前提下先对锁定目标执行 MoveIt 只读 IK/规划筛选，再决定是否保留顶部抓取配置。

## 2026-09-26 相机轴修正与倾斜抓取可达性闭环

- 本轮首先复核实际状态：根分区 40%（约 46 GB 可用）；无 PiPER/视觉控制残留进程；`can0` 保持 1 Mbps / sample-point 0.750 / `ERROR-ACTIVE`，但连续 3 秒 RX packets 固定为 `14088555`，增量为 0。因此未启动 PiPER 驱动、未使能、未发送实体运动或夹爪命令。
- URDF 明确事实：`joint7`/`joint8` 的指尖原点均位于 `gripper_base +Z` 方向 0.1358 m。上一轮实测 TF 矩阵则显示旧静态安装定义把 `camera_color_optical_frame +Z` 映射到 `gripper_base +X`；这使相机点 `(-0.008,-0.005,0.298)` 被错误变换到基座后方 `(-0.138,-0.050,0.236)`。
- 最小 TF 修正：`cube_visual_search.launch.py` 将 `gripper_base -> camera_link` 的 pitch 从 0 改为 `-1.57079632679`。矩阵复核后相机光轴与夹爪 `+Z` 同向，同一历史点变为前方 `(0.254,0.053,0.119)`；实际/规范 launch 一致，Python 语法通过，`brain_robot_ball_pick` 构建成功。该结果是基于 URDF、历史实体 TF 与现场安装照片的几何校核，仍需 CAN 恢复后用实时目标作一次无运动复核。
- 抓取执行器改用 SRDF `arm` 链的真实 tip `link6`（与固定 `gripper_base` 同原点），并保留每个候选必须通过 `/compute_ik` 的门槛。新增日志记录 IK link/frame/pose/error code。
- 固定垂直抓取的四个 yaw 对修正后目标仍全部返回 MoveIt `-31`。没有关闭碰撞检查、没有硬编码关节角，也没有把失败当成功。
- 最小算法修复：新增 `top_down_tilt_candidates=[0.0,0.35,0.70,1.00]`。每个候选根据自身工具 `+Z` 轴计算 wrist 位置，预抓取与下降阶段锁定同一 tilt/yaw；这对应“先在斜上方对齐，再按机械限位选择正上方或倾斜方向靠近”，而不是保持相机对齐角直冲目标。
- 失能离线复核复用了真实 `grasp_lift_executor`、MoveIt 和生效 YAML，注入观测姿态六轴 `[0.0,0.98,-0.75,0.0,0.30,0.0]` 与修正目标 `(0.254,0.053,0.119)`。结果：`tilt=0.350 rad, yaw=0` 首次通过 IK，生成预抓取 `link6=(0.180,0.053,0.322)`，MoveIt 成功规划 39 点（复跑 41 点）轨迹。随后 `TOP_DOWN_PREGRASP_PLAN_FAILED` 是适配器刻意保持 disarmed、没有实体反馈导致的 45 秒反馈超时，符合本次无运动测试预期。
- 构建验证：`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回 0；实际与规范抓取源码、YAML、launch 一致；`git diff --check` 返回 0。临时探针日志为 `/tmp/piper_tilt_ik_probe.log`，未加入 Git。
- 当前推进结论：观测、连续 SEARCH、ALIGN、GRASP_READY 已有上一轮实体证据；本轮首次取得修正目标上的可达抓取预姿态和完整 MoveIt 规划证据。剩余实体阻断只有当前 CAN RX=0，按规范不能运行默认一键运动。
- 下一步：只要 `can0` RX 再次持续增长，直接运行 `/home/johnwick/start_brain_robot_cube_real.sh` 默认自动链；重点验证实时目标 base 坐标、`tilt=0.35` 候选、`TOP_DOWN_PREGRASP_REACHED -> TOP_DOWN_DESCENT -> CLOSE -> LIFT -> RELEASE`，不重复 CAN/限位/固件/点云基础排查。

## 2026-09-26 倾斜抓取提交后收尾

- 本轮代码提交：`72648e5 fix: align wrist camera and plan tilted grasps`。
- 提交后状态：失能探针已退出，无一键脚本、PiPER 驱动、MoveIt、适配器或抓取执行器残留；`can0` 仍为 `ERROR-ACTIVE` 但 3 秒 RX 增量为 0，故不允许实体运动。
- 下一次第一条命令：`cd /mnt/hgfs/ub && git show --stat --oneline HEAD && ip -details -statistics link show can0`。若 RX 持续增长，直接执行默认一键链验证实时 TF 与 `tilt=0.35` 抓取；若仍为 0，保持不运动，不重复固件/限位/点云实验。

## 2026-09-26 提交后被动 CAN 等待

- `timeout 55s candump -n 1 can0` 返回 124，55 秒内没有收到任何帧；未发送 CAN、使能、夹爪或运动命令。
- 结论不变：软件侧已取得可达预抓取和 MoveIt 规划证据，但实体控制器当前没有反馈，不能安全启动一键运动。待供电/实体链路恢复且 RX 持续增长后，直接复用 `72648e5`，不重复本轮离线实验。

## 2026-09-27 01:10：断点续跑与孤立 Astra 排除

- 本轮按固定顺序完整读取规范仓库四份文档；起点提交为 `37066ab`。根分区使用率 `41%`、可用约 `46 GB`，未达到清理阈值；`sudo -n true` 返回 `0`。
- 实际控制进程检查仅发现一个已运行约 5 小时 40 分钟、父进程为 PID 1 的旧 Astra 进程组 `PGID 175276`；没有一键脚本、PiPER 驱动、MoveIt、Servo、视觉控制器、适配器或抓取执行器。只向该明确进程组发送 `TERM`，相机父子进程均退出；未调用 PiPER 使能/失能、`ResetPiper`、`MasterSlaveConfig` 或任何运动/夹爪命令。
- 停止旧 Astra 前，`can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point `0.750`、txqueuelen `1000`，但 3 秒 RX 固定为 `14088555`、增量 `0`。停止后执行一次 8 秒被动 `candump -n 1 can0` 仍返回 `124`，RX 仍固定为 `14088555`，错误/丢包/bus-off 均为 0。
- 该最小动作排除了“孤立 Astra 占用同一 VMware USB 主控”作为当前 CAN 静默的直接原因；没有重复已证明无效的固件、限位、点云、USB reset、xHCI/gs_usb 重载或离线 IK 实验。

### 本轮结论与下一步

- 本轮没有推进实体预抓取，因为真实 CAN RX 仍为 0；按硬门槛禁止启动 `/home/johnwick/start_brain_robot_cube_real.sh` 或用控制帧试探。软件断点仍是 `tilt=0.35 rad, yaw=0` 已通过 IK/MoveIt 规划，实体 `TOP_DOWN_PREGRASP_REACHED -> TOP_DOWN_DESCENT -> CLOSE -> LIFT -> RELEASE` 尚未验证。
- 下一步第一条命令：`ip -details -statistics link show can0`；只有 RX 计数持续增长后，才直接运行默认一键链验证实时 TF 与倾斜抓取，不再重复底层恢复实验。

## 2026-09-27 01:18：补全真实抓取后的放回、释放与撤离骨架

- 只读审计确认真实 `FinishGraspAndLift()` 在抬升后仅发布 `HOLDING` 并返回，默认一键链没有释放实现；这与总目标中的“抓取、抬升、释放”不一致。仓库历史只有仿真 `LOWER -> open -> RETREAT`，没有可直接复用的真实投放位姿。
- 最小实现不引入未经标定的横向放置点：闭爪前记录实际抓取位姿；闭爪反馈确认后沿基座 `+Z` 抬升；短暂保持后，沿启用碰撞检查的同一笛卡尔路径下降到该实测抓取位姿，张爪并确认反馈，再沿同一路径撤离到已规划的抬升位姿。新增状态为 `RELEASE_LOWERING -> RELEASING -> RELEASED -> RELEASE_RETREATING -> RELEASE_COMPLETE_HOLDING_SAFE_RETREAT`。
- 实体配置新增 `auto_release_after_lift: true`、`hold_after_lift_s: 1.0`；默认代码参数仍为关闭，避免其他配置未经明确启用自动释放。失败时保持既有语义：下降失败时保持夹持，张爪反馈未确认或撤离失败时进入明确 `FAIL`，不自动失能、不执行 reset。
- 实际 `/home/johnwick/piper_ws` 构建：`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回 0（两包成功）；实体 YAML 解析断言输出 `YAML_RELEASE_PROFILE_OK`。规范/实际源码和 YAML 已同步一致，`git diff --check` 通过。
- 本轮未启动 PiPER/视觉栈，未发送使能、失能、夹爪或运动命令；CAN RX 仍为 0，因此新增骨架只完成编译/配置验证，尚无实体释放证据。

### 本轮结论与下一步

- 软件链的目标序列现已补齐为 `TOP_DOWN_PREGRASP -> TOP_DOWN_DESCENT -> CLOSE -> LIFT -> RELEASE_LOWER -> OPEN -> RELEASE_RETREAT`，但实体验收仍必须等待 CAN RX 持续增长。
- RX 恢复后直接运行默认一键链，按顺序验证实时相机 TF、倾斜候选、预抓取/下降、闭爪反馈、抬升、同位放回释放和安全撤离；撤离完成后保持使能，不在缺少已验证支撑姿态时自动失能。

## 2026-09-27 01:27：一键成功路径接入安全回位与确认失能

- 继续审计发现：抓取执行器现在能发布 `RELEASE_COMPLETE_HOLDING_SAFE_RETREAT`，但一键脚本原先不会监听该终态，也不会在成功后自动回到已验证零点并失能；因此“安全返回后再失能”仍不完整。
- 最小脚本修复：默认自动路径在达到观测姿态后持续监听 transient-local `/brain_robot_grasp/state`。只有收到 `RELEASE_COMPLETE_HOLDING_SAFE_RETREAT` 才调用既有 `reset_zero_sequence()`；只有新的 `RESET_COMPLETE` 门控返回成功，才依次确认适配器 `disarm`、`disable_motion` 和 `/enable_srv {enable_request: false}` 的 `enable_response=True`，然后以成功码退出并清理本轮进程。
- 任意 `FAULT_*`、抓取等待超时、回位失败、disarm/运动门/六轴失能反馈未确认均返回保持路径：不自动回零、不调用硬件失能；Ctrl+C 文案也已修正为“停止控制并保持使能退出”。默认启动文案改为“当前反馈姿态进入观测、搜索和完整抓取流程”，不再错误声称先自动零点复位。
- 验证：规范和实际脚本 `bash -n` 均通过，`cmp` 一致；本机未安装 shellcheck。离线 mock 覆盖两个关键分支：释放完成状态实际调用 `MOCK_RESET_COMPLETE -> MOCK_DISABLE_CONFIRMED`；`FAULT_TOP_DOWN_DESCENT_FAILED` 只输出故障并返回保持，未调用 mock reset/disable。
- 本轮开始的 CAN 复核仍为 `can0 UP/ERROR-ACTIVE`、1 Mbps/0.75、5 秒 RX `14088555 -> 14088555`（增量 0）；没有启动 PiPER/视觉栈或发送运动/夹爪/失能命令。根分区 28%，磁盘不是阻断。

### 本轮结论与下一步

- 一键脚本现在具备完整成功闭环的控制骨架：当前姿态→观测→搜索→定位/锁模→预抓取→下降→闭爪→抬升→同位释放→撤离→零点回位确认→失能确认→退出。实体证据仍缺，不能宣称总目标完成。
- 下一步保持不变：CAN RX 持续增长后直接运行唯一默认脚本；按实际状态逐段验收，任一步失败都保持使能而不进入成功失能分支。

## 2026-09-27 01:30：连续第三轮 CAN 无反馈，进入外部状态阻断

- 起点提交为 `705ddb6`；根分区使用率 28%、可用约 56.3 GB，`sudo -n true` 返回 0。没有一键脚本、PiPER 驱动、MoveIt、视觉控制器、适配器或抓取执行器残留进程。
- `can0` 仍为 `UP/LOWER_UP`、`ERROR-ACTIVE`、1 Mbps、sample-point 0.750、txqueuelen 1000，错误、丢包和 bus-off 均为 0；但连续 8 秒 RX packets 固定为 `14088555 -> 14088555`，增量为 0。
- 这是同一阻断连续第三个目标轮次复现。前两轮已分别排除孤立 Astra 进程影响，并在无实体运动条件下补齐倾斜预抓取、释放/撤离以及成功后安全回位失能骨架；当前没有剩余的软件动作能够替代真实控制器反馈完成实体链验收。
- 本轮未启动驱动、未发送使能、失能、夹爪或运动命令，也未重复 USB reset、xHCI/gs_usb 重载、固件、限位、点云或离线 IK 实验。

### 阻断与唯一续跑入口

- 当前目标阻断于外部状态：USB-CAN 接口存在且配置正确，但 PiPER 控制器没有在实体 CAN 总线上产生任何可接收帧。按反馈硬门槛，不能安全启动默认一键链。
- 控制器供电、VMware USB 透传或实体 CAN 链恢复后，第一步只执行 `ip -details -statistics link show can0` 并做一次短时 RX 增量确认；只要 RX 持续增长，立即运行 `/home/johnwick/start_brain_robot_cube_real.sh`，从实时 TF 与 `tilt=0.35` 候选继续验证完整抓取，不再重复已排除的底层实验。

## 2026-09-27 11:26：用户续跑后的第一次外部状态复核

- 从提交 `20ab3bf` 恢复。根分区使用率 28%、可用约 54 GB，`sudo -n true` 成功；无一键脚本、PiPER 驱动、MoveIt、视觉控制器、适配器、抓取执行器或 Astra 残留进程。
- `can0` 仍绑定 `gs_usb`，USB 设备为 candleLight `1d50:606f`、序列号 `003F001E5246570520323934`；接口为 `UP/LOWER_UP`、`ERROR-ACTIVE`、1 Mbps / sample-point 0.750，错误、丢包及 bus-off 均为 0。8 秒 RX 仍为 `14088555 -> 14088555`，增量 0。
- 新的只读证据：USB 父设备 `/sys/bus/usb/devices/3-1.2` 为 `runtime_status=active`、`power/control=on`、autosuspend=-1，累计挂起时间为 0；01:20 之后内核日志没有 USB-CAN 断连、挂起或 `gs_usb` 错误。因此当前不存在可通过关闭 autosuspend 在虚拟机内恢复的问题。
- 本轮没有重载 xHCI/gs_usb、没有 USB reset、没有启动驱动或发送 CAN 控制帧。规范已明确这些动作此前均不能恢复实体反馈，继续重复不会推进实体验收。

### 当前判断与下一步

- 这是用户恢复目标后的第一次同类复核。Linux/VM 侧 USB 设备在线且活跃，但 PiPER 控制器侧仍未产生反馈；磁盘、USB autosuspend、接口参数和控制进程占用均不是本次原因。
- 唯一续跑门槛仍为 CAN RX 持续增长；满足后不做其他巡检，立即执行 `/home/johnwick/start_brain_robot_cube_real.sh` 验证完整抓取闭环。

## 2026-09-27 12:28：CAN 静默因果审计与禁止接口 bounce 修复

### 资料明确事实

- AgileX 官方 `piper_sdk` README 明确：读取关节反馈要求机械臂处于从臂模式；如果 CAN 发送失败，应检查连接并给机械臂重新上电后重试。来源：<https://github.com/agilexrobotics/piper_sdk/blob/master/README.MD>。这解释了为什么某些控制器/连接故障超出 guest 软件重开 socket 的恢复范围，但不等于本机已证明处于主臂模式。
- 官方 Interface V2 文档把 `DisableArm` 定义为显式 `0x471` 命令，把 `ResetPiper` 描述为会立即掉电并清除错误/内部标志；`DisconnectPort` 只断开 CAN 端口。来源：<https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD>。
- Linux SocketCAN 文档明确区分 `ERROR-ACTIVE` 与 `BUS-OFF`；只有 bus-off 时停止收发，`ip -details -statistics` 的 bus-off/error-pass 计数用于判断。来源：<https://docs.kernel.org/networking/can.html>。
- Broadcom/VMware 官方排障要求物理 USB、虚拟 USB 控制器和 guest 驱动三层都必须正常；“guest 能枚举设备”本身不足以证明持续数据通道正常。对兼容性问题，官方资料列出改用 USB 2.0 控制器/端口作为排障方案。来源：<https://knowledge.broadcom.com/external/article/307966>、<https://knowledge.broadcom.com/external/article/315312>。
- AgileX 官方仓库 issue #109 报告 SDK 在 CAN 异常后没有自动重连、部分场景需物理重连/重新上电；这是用户提交的开放 issue，不作为厂商已确认结论。来源：<https://github.com/agilexrobotics/piper_sdk/issues/109>。

### 本机证据与判断

- 最后一轮实体日志只记录 `piper_jog_adapter` 连续接受轨迹、视觉链到达 `GRASP_READY`，之后节点收到 SIGTERM；全局日志没有 `ResetPiper`、`MasterSlaveConfig`、硬件 `DisableArm` 或 `/enable_srv false` 的调用证据。当时提交 `c23fcbc`/`72648e5` 的 cleanup 仅调用适配器软件 `/disarm`，然后 TERM/KILL 本轮进程，明确不发送 `DisableArm`；实际 PiPER 节点的 `finally` 也只 destroy ROS node/shutdown，不失能硬件。
- Linux 当前为 `ERROR-ACTIVE`，bus-off/error-pass/bus-error 均为 0，因此不是 SocketCAN bus-off；也没有证据表明脚本把机械臂切为主臂模式。根分区 28%，磁盘不是原因。
- 历史上确实由代理执行过一次定向 USB reset 和一次 xHCI 模块重载；内核随后长期出现 xHCI event-DMA/TRB 异常。当前 USB-CAN 虽重新枚举并 active，但 PiPER 不再发帧。可以确认这些动作打断过 USB 数据通道，不能证明它们单独改变了 PiPER 控制器模式；最符合现有证据的是 VMware xHCI/USB-CAN 数据路径异常后，适配器或控制器一侧没有完成端到端恢复。

### 最小修复与验证

- 找到当前一键脚本仍有风险：只要 1 秒 RX 未增长，即使 `can0` 已正确处于 1 Mbps/0.75/UP，也会最多 5 次执行 `ip link down/up`。现已改为对正确配置的接口只做 5 秒被动 RX 门控；无反馈立即分类退出，绝不 bounce 接口。只有接口本身 down 或参数错误才允许配置。
- 规范与实际脚本 `bash -n` 通过且 `cmp` 一致。无运动回归返回 `1`，明确打印“不执行 down/up”；执行前后 RX `14088555 -> 14088555`、TX `205863 -> 205863`，接口仍 `UP/ERROR-ACTIVE`，所有错误计数仍为 0；未启动 PiPER 驱动、视觉控制器或适配器。
- 当前仍不能从 guest 内恢复 PiPER 侧零帧状态。长期消除同类问题的首选结构是让低带宽 USB-CAN 与高带宽 Orbbec 相机不共享 VMware 虚拟 xHCI 数据路径：CAN 使用独立物理 USB 控制器/端口并在 VM 中固定透传，或验证后使用单独 USB 2.0 虚拟控制器；这需要关闭 VM 修改 VMware 硬件配置，不在运行中的 guest 内盲改。

## 2026-09-27 12:39：一键自动抓取骨架失败路径收口

- 实际状态：根分区使用率 28%、可用约 54 GB；无一键脚本、PiPER 驱动、MoveIt、Servo、视觉控制器、适配器或抓取执行器残留进程。`can0` 仍为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750，RX 固定在 14088555、TX 固定在 205863，错误、丢包和 bus-off 均为 0。因此本轮没有启动驱动、使能、夹爪或运动命令。
- 代码审计确认真实抓取执行器和实体配置已有完整主骨架且 `auto_execute: true`：`TOP_DOWN_PREGRASP -> TOP_DOWN_DESCENT -> CLOSING -> LIFTING -> RELEASE_LOWERING -> RELEASING -> RELEASE_RETREATING -> RELEASE_COMPLETE_HOLDING_SAFE_RETREAT`；一键脚本随后监听释放终态，成功复位确认后才执行逐层失能。
- 找到的一键缺口：默认 `BRAIN_ROBOT_AUTO_START=1` 下，观测启动失败或抓取失败后原先会落入手动 `while/read` 循环，违反“默认自动流程不等待按键”；同时 TERM 没有标记异常清理，已 arm 后的非预期退出不一定显式停止视觉/Servo/适配器输出。
- 最小修复：增加 `MOTION_ARMED` 生命周期锁存。适配器 arm 成功后置 1，只有完整释放、安全复位以及硬件失能均确认后才清零；cleanup 在 `DISABLE_REQUESTED` 或 `MOTION_ARMED` 为真时停止视觉、Servo 和适配器输出，但不发送硬件失能、不自动回零。TERM 也进入该保持使能的异常路径。
- 默认自动模式现在在观测启动失败或抓取/释放/收尾失败时设置异常标志并立即返回 1，不再进入按键循环；手动按键循环只在显式关闭 `BRAIN_ROBOT_AUTO_START` 时可达。只有完整成功路径返回 0。
- 验证：规范脚本与 `/home/johnwick/start_brain_robot_cube_real.sh` 的 `bash -n` 均通过，`cmp` 完全一致；自动分支静态断言 `AUTO_BRANCH_ASSERT=0`，确认两条失败路径均 `exit 1`、成功路径 `exit 0`，均不会落入手动循环。抓取状态和实体 `auto_execute` 配置的源码核查通过。

### 当前阻断与下一步

- 软件骨架现已闭合，但没有新鲜 CAN 反馈，不能用实体运动宣称抓取目标已完成；本轮仅完成无运动可验证修复。
- 唯一下一步：CAN RX 持续增长后直接运行默认 `/home/johnwick/start_brain_robot_cube_real.sh`，无需按键，按顺序验收 `OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY -> TOP_DOWN_PREGRASP -> DESCENT -> CLOSE -> LIFT -> RELEASE -> RESET_COMPLETE -> confirmed disable`。若任一步失败，脚本现在停止新增输出、保持硬件使能并以非零码退出，不会静默等待输入。

## 2026-09-28：抓取后撤路径与实体轨迹双层保护完成

- 本轮按固定恢复顺序完整读取四份规范文档；起点提交为 `e9e18fa`。只读现场复核显示 `can0` 为 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750、txqueuelen 1000、无错误/丢包/bus-off，但 3 秒 RX packets 固定为 `14088555 -> 14088555`（增量 0）；没有一键脚本、PiPER 驱动、MoveIt、Servo、视觉或抓取进程。根分区使用率 29%、约 55.8 GB 可用。依照既有硬门槛，本轮未启动实体驱动，未发送使能、失能、夹爪或运动命令。
- 官方资料依据：MoveIt Pick and Place 将接近与抓取后撤建模为相反方向的 `pre_grasp_approach` / `post_grasp_retreat`；MoveGroupInterface 提供 `computeCartesianPath`；PlanningScene 的 attached object 通过 `touch_links` 允许物体与夹爪接触。由此将顶部抓取闭爪后的第一段抬升改为沿已经规划并执行过的接近路径反向返回预抓取位，而不是另行尝试固定世界 `+Z` 方向。
- `grasp_lift_executor` 新增笛卡尔轨迹连续性门控：点集为空、维度不符、非有限值或相邻任一关节跳变超过 `0.35 rad` 时，在交给实体适配器前拒绝执行。顶部抓取把预抓取位传入闭爪后流程，闭爪后执行 `POSTGRASP_RETREAT`，并发布 `LIFT_USING_REVERSE_APPROACH`；其他历史调用者仍保留固定 `+Z` 抬升作为兼容回退。
- attached object 显式使用 `[link6, gripper_base, link7, link8]` 并合并 MoveIt gripper group 链接作为 `touch_links`；启动配置显式锁定 `end_effector_link=link6`，无效末端链接会锁住抓取执行。仿真初始化改为先启动多线程 executor，并为辅助夹爪 MoveGroup 使用独立节点，消除第二个 MoveGroupInterface 构造时的阻塞。
- `piper_jog_adapter` 新增实体输出前的完整轨迹校验：拒绝重复/未知关节、点维度不符、非有限或非递增时间、非有限位置、软限位越界、首点与最新实测状态偏差超过 `0.10 rad`、以及相邻点关节跳变超过 `0.35 rad`。拒绝时立即 disarm，不产生 `/joint_commands` 输出。launch 与实体 YAML 已显式传递同一阈值。
- 失能 MoveIt fake-system 骨架验证返回 0，状态实际依次出现 `WAITING_FOR_LEVEL_ALIGN -> OPENING_GRIPPER -> PREPARED -> TOP_DOWN_PREGRASP_PLANNING -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME -> TOP_DOWN_DESCENT_PLANNING -> CLOSING_GRIPPER -> VERIFYING_GRASP_CONTACT -> LIFTING -> LIFT_USING_REVERSE_APPROACH -> HOLDING`。选择候选为 `tilt=0.350 rad, yaw=0`；下降轨迹 11 点、最大相邻关节步长 `0.044973 rad`，反向撤离 12 点、最大步长 `0.047728 rad`，两段均执行成功。此前固定世界 `+Z` 抬升只能得到 `computeCartesianPath` fraction `0.65/0.667`，故不再作为顶部抓取的默认撤离方式。
- 通信仿真采用 `rmw_cyclonedds_cpp`，避免本机陈旧 Fast DDS SHM 资源干扰；清理前发现旧 `ros2 topic echo --once` 进程和 Fast DDS zombie 段/端口，使用官方 `fastdds shm clean` 清除。该选择只用于本轮 fake-system 验证，没有据此修改实体一键脚本的中间件默认值。
- 验证结果：`py_compile` 通过；直接 pytest `6 passed`；规范仓库隔离 `colcon build` 成功；注册的 ament pytest 为 `1/1` suite、6 tests、0 errors/failures；范围内 `git diff --check` 通过。实际运行工作区两包同步重建成功；规范与实际四个生效源码/配置文件一致。测试覆盖有效轨迹、首点不一致、时间不递增、关节跳变、越限、非有限值和维度错误。

### 当前阻断与下一步

- 本轮推进了抓取骨架和防异常轨迹能力，但没有推进实体机械臂到新的观测/抓取状态，因为 PiPER 当前 CAN RX 增量仍为 0。接口配置正确不等于反馈可用；禁止用实体控制帧试探，也不重复 USB reset、xHCI/gs_usb、固件、限位或点云基础实验。
- 唯一续跑入口仍是 CAN RX 持续增长。恢复后直接运行默认 `/home/johnwick/start_brain_robot_cube_real.sh`，重点验收实时 `tilt=0.35` 候选的 `TOP_DOWN_PREGRASP -> TOP_DOWN_DESCENT -> CLOSE -> POSTGRASP_RETREAT -> RELEASE`；实体成功前不宣称总目标完成。

## 2026-09-28：仿真抓取、同位释放与安全撤离闭环

- 本轮起点为 `fa2d33a`。只读现场复核确认没有一键脚本、PiPER 驱动、MoveIt、适配器、视觉控制器或抓取执行器残留；`can0` 保持 `UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750、txqueuelen 1000，但 3 秒 RX packets 固定为 `14088555 -> 14088555`（增量 0）。因此未启动实体驱动，未发送使能、失能、夹爪或运动命令。
- 最小目标是补齐上一轮 fake-system 只验证到 `HOLDING` 的缺口，使同一真实抓取执行器在仿真中实际经过释放、撤离和终态，而不是只靠静态代码审计。
- 第一种次序“先 detach/恢复世界物体，再张爪”被测试否决：MoveIt 正确检测到 `medicine_cup` 与 `link7` 接触，夹爪规划失败并进入 `FAULT_RELEASE_GRIPPER_OPEN_FAILED`。第二种次序“张爪后立即恢复世界物体，再撤离”也被否决：刚恢复的世界物体仍与夹爪接触，撤离的 `computeCartesianPath` fraction 为 0，进入 `FAULT_RELEASE_RETREAT_FAILED`。这两次失败均保留了碰撞检查，没有把失败伪装为成功。
- 最终仿真次序为：下降回实测抓取位 → 停止 Gazebo 跟随 → 在物体仍以 attached object 且带 touch-links 的状态下张爪 → 沿已验证路径反向撤离至预抓取位 → detach 并把物体恢复到世界场景。该次序不改动真实分支已经确定的实体释放语义，仅补齐 `simulation_only` 的闭环验证。
- 最终 fake-system 测试返回 0，状态依次出现 `WAITING_FOR_LEVEL_ALIGN -> OPENING_GRIPPER -> PREPARED -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME -> TOP_DOWN_PREGRASP_PLANNING -> TOP_DOWN_PREGRASP_REACHED -> TOP_DOWN_DESCENT_PLANNING -> CLOSING_GRIPPER -> VERIFYING_GRASP_CONTACT -> LIFTING -> LIFT_USING_REVERSE_APPROACH -> HOLDING -> RELEASE_LOWERING -> RELEASING -> RELEASE_RETREATING -> RELEASE_COMPLETE_HOLDING_SAFE_RETREAT`。
- 同一次测试选择 `tilt=0.350 rad, yaw=0`；预抓取轨迹 31 点；下降轨迹 12 点、最大相邻关节步长 `0.046459 rad`；抓取后反向撤离 12 点、`0.047728 rad`；释放下降 12 点、`0.047724 rad`；释放撤离 12 点、`0.047728 rad`。所有 MoveIt execute 请求成功，最终日志为 `Cup release and safe retreat completed.`。
- 实际 `/home/johnwick/piper_ws` 已用最终源码重建，`brain_robot_pick_place` 构建成功；规范仓库源码与实际生效源码 `cmp` 一致。直接 pytest 为 `6 passed in 0.27s`；注册的 colcon/ament 测试为 1 个 suite、6 个 pytest，汇总 7 tests、0 errors/failures/skipped。

### 当前阻断与下一步

- 仿真现已覆盖锁模、倾斜预抓取、下降、闭爪、反向撤离、同位释放和安全撤离完整骨架；这仍不是实体抓取完成证据。
- 当前唯一实体阻断仍是 CAN RX 增量为 0。只有 RX 持续增长后才直接运行 `/home/johnwick/start_brain_robot_cube_real.sh`，从 `OBSERVE_POSE_REACHED -> SEARCH` 一路验证到实体 `RELEASE_COMPLETE_HOLDING_SAFE_RETREAT -> RESET_COMPLETE -> confirmed disable`；不重复固件、限位、点云、USB reset、xHCI/gs_usb 或离线 IK 实验。

## 2026-09-28：无机械臂现场时完成实体适配器回放验收

- 本轮起点提交为 `2704222`。机械臂不在现场，因此没有启动实体脚本、PiPER 驱动、使能、夹爪或任何 CAN 控制帧；本轮只做规范配置审计和离线回放。
- 复核实际生效的 `brain_robot_ball_pick/config/cube_task_real.yaml`：`backend=piper`、`real_motion_enabled=true`、`direct_grasp_after_align=true`、`freeze_grasp_tracking=true`、`static_target_lock=true`、`top_down_grasp_enabled=true`、`candidate_grasp_enabled=false`、`auto_execute=true`、`auto_release_after_lift=true`。腕部点云仍只经过 TF gate 作为诊断证据，未接入实体 Octomap。
- 新增 `test_real_grasp_replay.py` 并注册到 `brain_robot_pick_place` 的 ament pytest。测试复用实体适配器 `_trajectory_rejection_reason()`，将规范文档记录的 P2 六轴快照 `[0, 0.193°, -0.113°, 0, 15.253°, 0]` 转为弧度，插值到实体观测姿态 `[0, 0.98, -0.75, 0, 0.30, 0]`，再回放一次锁定后的有界六轴接近段；验证首点与测量状态、六轴完整性、软限位、时间单调性和相邻步长门控。
- 回放同时静态确认：`GRASP_TARGET_MODEL_LOCKED_BASE_FRAME` 后，抓取执行器的视觉重捕获分支只在 `!static_target_lock_` 时可达；`freeze_grasp_tracking=true` 时 `GRASP_READY` 不恢复视觉搜索。该测试不伪造目标笛卡尔位姿，因此不把离线回放冒充实体目标可达性。
- 规范树直接 pytest：新增回放 3 项与既有适配器 6 项共 `9 passed`。实际 `/home/johnwick/piper_ws` 同步后构建成功；实际 colcon 测试注册为两个 suite，全部通过，汇总 `11 tests, 0 errors, 0 failures, 0 skipped`。

### 当前阻断与下一步

- 本轮完成了机械臂不在场时能完成的最高价值工作：实际配置核对、锁定后不回搜索的代码门控、真实适配器轨迹规则回放和实际工作区注册测试。
- 回放不替代实体 MoveIt IK、真实 CAN 反馈和夹爪接触证据。机械臂回到现场且 CAN RX 持续增长后，直接运行默认一键脚本，第一轮只观察并记录 `TARGET_LOCKED -> PREGRASP_TRAJECTORY_ACCEPTED -> TOP_DOWN_PREGRASP_REACHED -> TOP_DOWN_DESCENT -> GRIPPER_CLOSE_REQUESTED`，不再重新设计参数。

## 2026-09-28：实机首次抓取阶段诊断标记补齐

- 本轮起点提交为 `e06532c`。机械臂仍不在现场，无实体进程、使能或 CAN 控制帧。
- 为避免第一次实机失败只能看到“状态变化”而无法区分轨迹是否真正交给适配器，抓取执行器新增三个只读诊断事件：`TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED`、`TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED`、`GRIPPER_CLOSE_REQUESTED`。
- 三个事件分别位于顶部预抓取成功、顶部下降成功和发布实体闭爪命令之前；不改变姿态、速度、候选顺序、碰撞检查、目标锁定或安全失败语义。
- 离线回放测试新增三个事件断言。规范树直接 pytest 为 `9 passed`；实际工作区 `brain_robot_pick_place` 构建成功，实际 colcon 测试汇总 `11 tests, 0 errors, 0 failures, 0 skipped`；规范与实际执行器源码 `cmp` 一致。

### 当前阻断与下一步

- 本轮只增强实机可观测性，未宣称实体预抓取或抓取完成。机械臂回到现场且 CAN RX 持续增长后，首次运行按以下顺序读取诊断：`GRASP_TARGET_MODEL_LOCKED_BASE_FRAME` → `TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED` → `TOP_DOWN_PREGRASP_REACHED` → `TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED` → `GRIPPER_CLOSE_REQUESTED`。
- 按首次缺失事件定位规划/发布、适配器反馈、下降衔接或夹爪请求，不重复底层巡检。

## 2026-09-28：重启后首次实体一键链实跑断点

- 机械臂重启后 USB-CAN 重新枚举；`sudo -n true` 返回 0。`can0` 初始为 `DOWN/STOPPED`、RX=0，本轮仅按已记录参数配置为 1 Mbps、sample-point 0.750、txqueuelen 1000，未发送 PiPER 控制帧。
- 配置后被动 RX 曾在 8 秒增加 `18578`，接口为 `UP/LOWER_UP/ERROR-ACTIVE`，错误、丢包和 bus-off 均为 0，因此按硬门槛启动唯一默认 `/home/johnwick/start_brain_robot_cube_real.sh`。
- 实际脚本通过 `[1/7]` CAN 复用、RGB/深度首帧、`[3/7]` 紫色检测启动和 `[4/7]` MoveIt/Servo/真机适配器启动，停在 `[5/7]` 的完整 MoveIt 反馈/自体过滤 TF 门控；没有进入 `[6/7]`、没有调用 `/enable_srv`、没有调用适配器 `arm`，没有发送实体关节或夹爪命令。
- 同期 `piper_driver.log` 记录反馈反复丢失/恢复（4.65 s、0.33 s、0.21 s、5.58 s、0.76 s、0.27 s、2.58 s 等），最终报 `can0 feedback absent for 25.0s; holding all output and waiting for recovery (driver stays receive-only)`。随后 8 秒被动 `candump` 无帧，RX 计数冻结；最终接口统计仍为无错误/丢包/bus-off。
- 当前运行实例因 `/piper_moveit_joint_states` 无反馈而卡在等待门控；已精确终止本轮脚本及其已识别的 PiPER/MoveIt/Servo/视觉/Astra 子进程，确认无控制栈残留。适配器全程只记录初始 `disarmed`，没有 `PHYSICAL MOTION ARMED`。

### 当前阻断与下一步

- 这次首次实体实跑把阻断定位到“重启后 CAN 反馈生命周期再次中断”，早于观测姿态、SEARCH、目标锁定和抓取；不是抓取姿态或夹爪逻辑失败。
- 机械臂仍在现场时，下一次只需先被动确认 `0x251..0x256`/RX 持续增长和 `/joint_states` 连续更新；满足后直接复用本提交运行默认脚本。若反馈再次中断，保持 receive-only，不进入使能和运动，不重复视觉/抓取实验。

## 2026-09-28：实体控制栈清理后的被动 RX 复核

- 停止本轮实体控制栈后，保持 `can0` 原配置不变做 10 秒 `candump -n 1` 被动观察；返回 `124`，无帧，RX `721825 -> 721825`（增量 0）。接口仍 `UP/ERROR-ACTIVE`、1 Mbps/0.750、qlen 1000，错误/丢包/bus-off 均为 0。
- 未执行 link bounce、USB reset、xHCI/gs_usb 重载、发送 CAN 控制帧或再次启动上层；当前断点仍是重启后 PiPER 控制器反馈没有持续恢复。

## 2026-09-28：用户要求自主续跑后的现场复核

- 从提交 `2f2d8f7` 继续。无一键脚本、PiPER 驱动、适配器、视觉、MoveIt 或 Astra 残留进程。
- `can0` 保持 `UP/LOWER_UP/ERROR-ACTIVE`、1 Mbps、sample-point 0.750、qlen 1000，错误/丢包/bus-off 均为 0；5 秒 RX `721825 -> 721825`，增量 0。
- 因实体反馈仍为 0，本轮没有重启机械臂、bounce can0、USB reset、发送控制帧或重新启动默认脚本；无新增实体运动证据。

## 2026-09-28：重启后自动 RX 门控五分钟无恢复

- 用户确认机械臂已重启后，保持 `can0` 正确配置不变，启动 5 分钟被动门控；只有连续三个 2 秒采样周期 RX 增长才允许自动运行默认脚本。
- 150 个采样周期全部为 `RX=721825`、`delta=0`、`consecutive=0`，最终输出 `CAN_FEEDBACK_NOT_RECOVERED`。默认脚本未被触发，未启动任何控制栈或发送运动命令。
- 该结果确认重启后的反馈没有在等待中自行恢复；当前不是脚本时序或视觉阶段问题。

## 2026-09-28：首次越过 7/7 后修复观测轨迹两点跳变

- 本次恢复后 USB-CAN 为新枚举实例，`can0` 初始 DOWN；按规范参数配置后连续三秒 RX 分别增长 `2336/2352/2361` 帧，无错误/丢包/bus-off。默认脚本实际通过 `[1/7]` 至 `[7/7]` 并进入自动 PREPARE。
- 真正失败点为软件门控：视觉控制器把当前姿态到观测姿态发布成仅 2 点轨迹，适配器明确拒绝 `point 1 joint jump for joint2`（超过 0.35 rad）并自动 disarm；没有执行观测轨迹。Ctrl+C 后脚本按异常路径停止输出、保持使能，未自动复位或失能。
- 修复：新增 `prepare_max_joint_step_rad=0.08`；当前→观测/零点轨迹按最大六轴差计算 `ceil(max_delta/0.08)` 段并线性插值，时间戳按原总时长等比例严格递增。参数加入合法性校验，日志记录总时长、点数和最大步长。
- 实体配置显式设为 0.08 rad，低于适配器 0.35 rad 跳变门。离线回放新增源码/配置断言；规范树直接 pytest `10 passed`，实际 `brain_robot_pick_place` 与 `brain_robot_ball_pick` 构建成功。

### 下一步

- 确认 RX 持续增长后，直接重跑默认脚本；首要验收适配器不再拒绝 PREPARE、观测反馈收敛并发布 `OBSERVE_POSE_REACHED -> SEARCH`。


## 2026-09-28 22:35：实机到达 SEARCH、记录停机姿态并优先收口通信异常

### 实际运行与断点

- 起点为 `95248ae`。根分区使用率 29%、可用约 54 GB；USB-CAN 为 candleLight `1d50:606f`（序列号 `003F001E5246570520323934`），`can0` 为 1 Mbps / sample-point 0.750 / txqueuelen 1000、`ERROR-ACTIVE`，无 bus-off、error-pass、bus-error 或 RX drop。
- 默认 `/home/johnwick/start_brain_robot_cube_real.sh` 实际通过 `[1/7]` 至 `[7/7]`。插值后的当前姿态→观测轨迹为 49.1 s、14 点，适配器接受；实机随后明确发布 `STATE -> SEARCH (OBSERVE_POSE_REACHED)`，证明 `95248ae` 已修复此前两点观测轨迹拒绝。
- 搜索期间 MoveIt 短段被连续接受；到 J1 负向边界时，适配器明确拒绝 `point 4 exceeds limit for joint1` 并 disarm。视觉控制器此前没有消费适配器失能状态，因而在机械臂已不再接收输出后仍空发搜索计划。此次停止不是 Octomap/夹爪点云或目标移动导致。
- 按用户要求优先记录停止位置。两次独立 `/joint_states --once` 一致：`J1=-1.443717772, J2=1.031236948, J3=-0.784578788, J4=-0.028433720, J5=0.888545028, J6=0.000000000 rad`，夹爪反馈 `-0.0007 m`。停止一键链时只停止控制输出并保持使能；未执行 ResetPiper、MasterSlaveConfig、自动零点复位或硬件失能。

### 通信异常证据与恢复

- 停止后 USB-CAN 仍在线，RX 连续三秒增长 `2429/2444/2445` 帧，磁盘不是原因。内核日志在本轮高频输出期间新增一次 `gs_usb ... Unexpected out of range echo id 343`；Linux 主线 `gs_usb.c` 对超出 `GS_MAX_TX_URBS` 的 echo id 明确记错并丢弃该 echo 后重新提交接收 URB。这证明设备/USB 路径曾返回无效发送回显；它不等同于 CAN bus-off，也不能仅凭这一条认定机械臂固件故障。
- 在确认 PiPER/视觉/适配器均无残留后，只执行一次受限 `can0 down -> 1 Mbps/0.75/qlen 1000 -> up`，清除本轮可能滞留的 gs_usb TX echo 上下文，并将已处理 echo 异常计数记录为 1。恢复后 RX 三秒增量 `2437/2427/2440`，仍为 `ERROR-ACTIVE` 且总线错误计数为 0。
- 以 `auto_enable=false` 启动只读 PiPER 驱动复测 45 秒：`/joint_states` 平均约 `199.8 Hz`，观测到的最大消息间隔 `0.022 s`，共覆盖 8616 个窗口样本；内核 echo 异常计数保持 1，未新增异常。驱动初始化仅出现一次 `feedback lost` 后 `0.08 s` 恢复，属于首批完整反馈到达前的瞬时门控，不是历史 25 s 断联。

### 最小修复与验证

- 一键脚本新增通信守护，但不恢复“RX 一停就盲目 bounce”的旧行为：只有内核出现尚未处理的新 `gs_usb` 非法 echo 且尚未启动运动时，才重建一次 `can0`；运动期间若连续 3 秒 RX 不增长、接口消失或出现新的非法 echo，先发布 emergency-stop、停止本轮输出并保持硬件使能，由下一次启动在无运动阶段恢复接口。
- `piper_jog_adapter` 新增 `/brain_robot_control/adapter_armed` 状态；视觉控制器在已见过 armed 后若收到 false，立即进入 `FAULT (PIPER_ADAPTER_DISARMED)` 并停止 MoveGroup，禁止适配器拒绝后继续空发计划。
- 实体搜索 J1 边界从适配器极限 `[-1.50, 1.50]` 收紧为 `[-1.35, 1.35] rad`，给 MoveIt/TOTG 中间采样保留 0.15 rad 余量；搜索段从 0.08 增至仍低于 0.35 跳变门的 0.20 rad，减少频繁停启。没有扩大任何现场轨迹或降低适配器限位。
- 验证：规范和实际一键脚本 `bash -n` 通过；适配器/实体回放测试 `11 passed in 0.36s`；实际 `brain_robot_pick_place`、`brain_robot_ball_pick` 两包构建成功。

### 当前判断与下一步

- 当前通信链已经恢复且静态反馈稳定；实体主线已首次确证到达 `OBSERVE_POSE_REACHED -> SEARCH`。尚未完成搜索目标锁定与抓取，不能宣称总目标完成。
- 下一步直接运行默认一键链验证收紧后的连续搜索；首先确认不再出现 J1 越界拒绝和空发。如果检测器满足紫色、矩形、深度与尺寸门控，则继续验收 `ALIGN -> GRASP_READY -> TOP_DOWN_PREGRASP -> DESCENT -> CLOSE -> POSTGRASP_RETREAT -> RELEASE`。


## 2026-09-28 22:52：搜索越界修复实证与全搜索超时修复

- 从提交 `6840af2` 重跑默认一键链。CAN 启动前三秒 RX 增量 `2440/2436/2429`，内核非法 echo 计数保持 1；新的运行期 CAN 守护实际启动且全程未触发。脚本再次通过 `[7/7]`，从记录的 J1 `-1.4437 rad` 姿态发布 72.2 s、20 点观测轨迹，适配器接受并到达 `OBSERVE_POSE_REACHED -> SEARCH`。
- 新的 `[-1.35, 1.35] rad` J1 边界和 0.20 rad 搜索段已取得实体证据：搜索段约每 3.3 s 连续接受，J1 实测到达 `+1.339978304 rad` 后反向，无 `exceeds limit`、无适配器 disarm、无 `PIPER_ADAPTER_DISARMED`，通信守护日志为空。上一轮 J1 极限拒绝已消失。
- 检测器一直为 `PURPLE_CUBE target LOST`、`target_valid=false`、`DEPTH_REJECTED_TARGET_LOST`。保存的 `/camera/color/image_raw` 和调试帧几乎全黑；UVC 确认使用独立 `2bc5:0557` RGB 设备，曝光/增益可正常读写。分别尝试默认 `157/0`、手动 `300/50` 和诊断 `1000/100` 后已恢复自动曝光/自动白平衡。用户随后确认现场灯被关闭，因此本轮黑帧和目标丢失归因于环境照明，不再推断相机故障、物理遮挡或颜色/深度阈值错误。
- 状态日志揭示直接软件原因：整个运行只出现 `SEARCH_DOWN` 与 `BOTTOM_SCAN`；实体全搜索每 75 s 被通用 `search_timeout_s` 强制 `FULL_SEARCH_CYCLE_RESTART`，每次又从 DESCEND 开始，导致 J5 长期停留在约 `+0.95 rad` 一侧，永远不能进入 `SEARCH_UP/TOP_SCAN` 覆盖另一侧视野。停止前位置为 `J1=0.496927228, J2=1.053286164, J3=-0.989667896, J4=-0.064647464, J5=1.065200416, J6=0 rad`；Ctrl+C 只停止输出并保持使能，未复位或失能。
- 最小修复位于状态机而不是扩大轨迹：实体 full SEARCH 不再受通用墙钟超时重启，继续由既有有界 J1/J5 相位和每段反馈超时驱动；实体 LOCAL_SEARCH 仍保留 5 s 超时，仿真仍保留原 `search_timeout_s`。这使实体搜索能从 `DESCEND/BOTTOM_SCAN` 继续进入 `ASCEND/TOP_SCAN` 并循环覆盖。
- 验证：适配器/实体回放 `11 passed in 0.38s`；实际 `brain_robot_pick_place`、`brain_robot_ball_pick` 两包构建成功。尚未用实体复核 `SEARCH_UP/TOP_SCAN` 和目标锁定。

### 下一步

- 现场照明恢复后直接重跑默认一键链；验收日志必须出现 `SEARCH_UP` 或 `TOP_SCAN`。检测器恢复有效画面并锁定方块后，继续 `ALIGN -> GRASP_READY` 和五个抓取阶段诊断；照明关闭期间不改相机 profile、不放宽颜色/深度门控，也不据黑帧重新设计搜索轨迹。

## 2026-09-28 23:07：关灯条件下的深度先锁定可行性复核

- 本轮只启动 `astra_camera astra.launch.py`，未启动 PiPER 驱动、视觉控制器、适配器或抓取执行器，未发送任何关节/夹爪命令。退出后确认没有相机或机械臂控制进程残留；机械臂保持原状态。
- 关灯时 `/camera/depth/image_raw` 仍发布 `640x400`、`16UC1` 深度，短时频率从启动阶段上升至约 `23 Hz`；单帧有效像素 `197112/256000`（约 77%），有效范围 `319..446 mm`，中位数 `373 mm`。深度相机内参为 `fx=fy=478.756866`、`cx=326.135559`、`cy=199.873489`。
- 对该帧做确定性桌面平面 RANSAC：抽样 20000 点中约 15553 点在 4 mm 平面带内；全部有效点相对主平面的残差约为 `-10.6..+11.4 mm`，没有落入 `12..120 mm` 立方体凸起范围的连通候选。深度可视化显示当前视野主要是平面、无效边缘和末端结构；本帧没有可安全锁定的方块几何，禁止把最近深度点或夹爪直接当成目标。
- 现有检测器并非“颜色一出现就运动”：真实配置已经要求紫色矩形候选同时通过稳定深度、物理尺寸 `0.015..0.120 m` 和尺寸宽高比门控；抓取执行器在 `GRASP_READY` 时把该深度点变换到 `base_link` 并静态锁定。当前缺口是纯深度候选获取，而不是锁定后的目标冻结。
- 结论：可以用深度作为三维锁定和后续抓取的几何权威，但纯深度首检必须同时具备桌面平面剔除、立方体高度/尺寸/宽高比、连续帧稳定和机器人末端排除；深度本身不能证明物体是紫色。本轮真实帧中没有方块候选，故不修改默认检测配置、不盲目启用“最近物体即方块”。
- 证据保存在 `/home/johnwick/brain_robot_logs/depth_lock_probe_20260928/`（原始深度、可视化及复核脚本，不提交 Git）。根分区 29%，无需清理；`can0` 仍为 1 Mbps / sample-point 0.750、`ERROR-ACTIVE`，RX `8258667` 帧、总线错误和 RX drop 均为 0。

### 下一步

- 照明恢复后用已修复的完整上下搜索取得“方块进入深度视野”的同步帧；若 RGB 仍不可靠，再在现有 `cup_detector_node` 内增加受上述四类门控约束的深度候选，而不是绕过检测器或放宽抓取授权。首次可靠候选应立即保存基座三维点，后续对齐/接近只使用该静态模型，不因腕部相机运动重新选目标。

## 2026-09-28 23:49：深度候选探针构建与真实只读验证

- 按确认方案新增 `brain_robot_pick_place/scripts/depth_cube_probe.py`。它对深度帧拟合透视桌面平面（逆深度线性模型），只保留 `0.015..0.120 m` 凸起、物理尺寸 `0.015..0.120 m`、宽高比 `<=1.45`、填充率 `>=0.45` 且连续三帧稳定的候选；发布 `/brain_robot_vision/depth_candidate_*` 诊断话题，不发布 `/brain_robot_vision/target_valid`、不发布 `/joint_commands`、不调用任何控制服务。
- 探针已接入 `cube_visual_search.launch.py` 和 `cube_task_real.yaml`，但仍是被动诊断节点；CMake 安装项和 `python3-numpy/python3-scipy` 依赖已加入。实际 `/home/johnwick/piper_ws` 与规范源四个文件逐一 `cmp` 一致。
- 离线语法/YAML 验证通过；实际工作区 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回 0，两个包完成构建，安装空间已出现 `depth_cube_probe.py`。
- 真实只读验证：仅启动 Astra 和探针，未启动 PiPER/MoveIt/Servo/视觉控制器，未发送机械臂命令。关灯条件下探针连续输出 `DEPTH_PROBE_NO_CUBE_CANDIDATE plane_inliers=2652..2695`，没有把桌面或夹爪误报为目标；随后相机已停止且无控制进程残留。
- 合成正向验证：640x400、400 mm 平面上放置约 35 mm 方块凸起，探针依次输出 `DEPTH_CUBE_WAIT_STABLE stable=1/3`、`2/3`、`DEPTH_CUBE_CANDIDATE_VALID stable=3/3`，三维点约 `(-0.005,0,0.350) m`、尺寸约 `0.035x0.035 m`、高度 `0.050 m`。这证明平面/尺寸/连续帧门控实际生效。
- 当前探针结果仍未授权运动；它只证明深度几何候选链可用。照明恢复并完成真实搜索后，需取得紫色方块进入视野的真实候选，再决定把锁定点接入正式 `target_valid`，避免纯深度把任意方块或末端结构当成紫色目标。

## 2026-09-29 00:05：照明恢复前的无运动 RGB-D 复核

- 仅启动 Astra 相机并订阅一帧 `/camera/color/image_raw`、`/camera/depth/image_raw`；未启动 PiPER、MoveIt、Servo、视觉控制器或适配器，未发送运动命令。相机随后已停止。
- 深度仍正常：`16UC1`、`640x400`、有效像素 `196240/256000`。RGB 仍为 `rgb8` 但近黑：平均原始通道值 `14.81`、P95 `24.00`。
- 判断：现场照明仍未恢复，不能进行真实紫色识别或运行会运动的一键链。深度探针继续保持被动诊断，不把几何候选接成正式 `target_valid`；下一步仍是灯光恢复后先取得同步 RGB-D 方块候选，再锁定 `base_link` 点并继续搜索/抓取。

## 2026-09-29：按用户确认切换深度-only目标门控（无紫色依赖）

- 用户明确确认当前任务不需要紫色语义，目标是静止方块的硬深度抓取。因此本轮把“深度探针仅诊断”推进为真实配置的目标来源；仍保留桌面平面、凸起高度、物理尺寸、填充率/方形度和连续稳定帧门控，不接受最近深度或无几何约束的任意像素。
- `depth_cube_probe.py` 新增 `/brain_robot_vision/depth_candidate_error`，发布候选中心像素误差和归一化误差；无候选时发布无效门控。该节点只发布候选几何/有效性，不发布任何关节、Servo 或夹爪命令。
- `visual_search_controller` 增加 `depth_only_target_enabled` 及独立 valid/point/error 订阅。真实配置启用后，RGB 紫色检测回调被旁路，深度候选直接驱动现有 `SEARCH -> ALIGN -> GRASP_READY` 状态机；目标点仍通过历史 TF 变换记录，未另写基础运动程序。
- `grasp_lift_executor` 增加独立深度点、尺寸、误差和有效性订阅；真实配置启用后，深度候选同时满足目标有效和深度有效门控，并沿既有 `base_link` 静态锁定、顶部倾斜候选、闭爪、抬升、同位释放骨架执行。RGB 目标失效不会覆盖深度-only状态。
- `cube_task_real.yaml` 对视觉和抓取执行器均设置 `depth_only_target_enabled: true`，使用 `camera_depth_optical_frame` 和 `/brain_robot_vision/depth_candidate_*`；`cube_visual_search.launch.py` 注释同步说明探针是几何门控而非直接运动节点。未修改固件、MasterSlaveConfig、ResetPiper 或基础 CAN 配置。
- 规范源 C++ 编译目标均通过；规范仓库在 hgfs 上安装 symlink 受文件系统限制而失败，但这不是代码编译错误。随后把五个生效文件同步到 `/home/johnwick/piper_ws`，实际工作区 `brain_robot_pick_place`、`brain_robot_ball_pick` 构建和安装成功，`depth_cube_probe.py`、控制器和抓取执行器安装链接存在。
- 隔离 `ROS_DOMAIN_ID=77` 合成验证：复用既有 640x400、400 mm 桌面/35 mm 方块发布器，探针输出 `DEPTH_CUBE_CANDIDATE_VALID stable=16/3..20/3`，候选点 `(-0.005,-0.000,0.350) m`、尺寸 `0.035x0.035 m`、高度 `0.050 m`；误差话题输出 `x=-6.636 px, y=-0.373 px, ratio=0.0207`。无 PiPER、MoveIt、Servo、适配器或实体控制帧参与，测试残留已清理。
- 随后尝试只启动真实 Astra 与深度探针（无 PiPER/MoveIt/Servo/适配器）；本次相机启动未在门控时限内提供 `CameraInfo`/深度候选，探针只记录 `DEPTH_PROBE_WAITING_FOR_CAMERA_INFO`，相机与探针进程已清理。该结果只说明当前无真实候选证据，不回退深度-only配置，也不启动运动。

### 当前阻断与下一步

- 本轮已消除“必须先识别紫色”这一软件阻断，但尚未取得实体相机中真实方块的深度候选，也未因此宣称实体抓取完成。实体运行仍受既有 CAN RX 连续增长、`/joint_states` 新鲜反馈和脚本阶段门控约束。
- 下一步第一条命令：在不启动运动的前提下确认 `/camera/depth/image_raw` 中出现通过几何门控的 `DEPTH_CUBE_CANDIDATE_VALID`；随后才运行默认一键脚本，验收 `OBSERVE_POSE_REACHED -> SEARCH -> ALIGN -> GRASP_READY`，并按既有五个抓取诊断事件定位最早缺失点。

## 2026-09-29：灯光恢复后解除Astra UVC阻塞并验证深度数据面

- 灯光恢复后，被动门控确认 Orbbec `2bc5:0557/0657` 与 USB-CAN 均枚举，CAN 3 秒 RX 增长 `7305` 帧，根分区可用约 53 GB；无机械臂控制栈残留。
- 首次只读启动复现了具体相机断点：实际 `astra_params.yaml` 仍启用 UVC RGB，深度设备 `2bc5:0657` 已启动后，驱动在打开 `2bc5:0557` 时输出 `attempt to claim already-claimed interface 1` 并阻塞组件构造，ROS 因此看不到深度话题。该问题不是光照、CAN 或方块颜色门控。
- 按已确认的深度-only目标做最小修复：实体 Astra profile 关闭 `enable_color`、`enable_ir` 与 `uvc_camera.enable`，深度保持 `640x400@30 Hz`；一键脚本默认 `BRAIN_ROBOT_DEPTH_ONLY_TARGET=1`，只等待/监测深度帧，跳过紫色检测器、RGB首帧和RGB调试窗口，并显式等待 `/depth_cube_probe`。
- 实际 `/home/johnwick/start_brain_robot_cube_real.sh` 与相机工作空间已同步，`astra_camera` 重建成功；脚本 `bash -n` 通过。清除一条 2026-09-26 遗留的 `timeout 8s /usr/bin/python3 -` ROS探针和本轮旧 daemon 后，Astra/探针数据面恢复。
- 真实无运动验证：Astra 明确输出 `ir is not enable`、`color is not enable`、`SENSOR_DEPTH is started`；深度探针连续取得约 `2651..2685` 个平面内点并输出 `DEPTH_PROBE_NO_CUBE_CANDIDATE`。这证明深度流和几何算法实际工作，且当前静止视野没有通过尺寸/凸起/稳定门控的方块；未启动 PiPER、MoveIt、Servo、适配器或运动。

### 下一步

- 当前视野无候选不能阻止既有机械搜索；下一步在 CAN RX 持续增长的前提下运行默认一键脚本，以实体 SEARCH 扫描把静止方块带入深度视野。验收顺序为 `OBSERVE_POSE_REACHED -> SEARCH -> DEPTH_CUBE_CANDIDATE_VALID -> ALIGN -> GRASP_READY`。

## 2026-09-29：首次深度-only实体搜索进入ALIGN及恢复窗口修复

- 默认一键脚本在 CAN 3 秒 RX 增长 `7285` 帧后实际运行，通过深度首帧、`[7/7]`、当前姿态到观测姿态和 `OBSERVE_POSE_REACHED -> SEARCH`。深度-only阶段确实跳过紫色检测器/RGB窗口；腕部点云仍不写入Octomap。
- 实体搜索连续接受 MoveIt短段并发现真实几何候选：首次稳定候选约 `pixel=(550.5,46.5)`、相机点 `(0.164,-0.112,0.349) m`、尺寸约 `0.038x0.047 m`、高度约 `0.028 m`、填充率约 `0.69`。状态机实际进入 `ALIGN (TARGET_ACQUIRED)`，证明纯深度 `SEARCH -> ALIGN` 接线生效。
- 首次ALIGN约4秒后目标暂失，状态进入 `LOCAL_SEARCH (LAST_TARGET_HISTORY_UNAVAILABLE)`。配置直接矛盾已确认：`target_loss_grace_s=2.0`，但 `target_history_window_s=0.40`，所以开始历史恢复时最近样本必然已经超过窗口。同时探针内部已要求3个稳定帧，控制器又要求6个有效发布，搜索掠过目标时出现只到3/4帧却未锁定的重复门控。
- 本轮用 Ctrl+C 停止新增视觉/Servo/适配器输出并保持机械臂使能，脚本明确未发送 `DisableArm`、ResetPiper或自动零点复位。随后把控制器有效发布要求降为2（连同探针仍至少5个连续几何结果），并把历史窗口扩到5秒，大于2秒丢失宽限；没有扩大搜索边界、速度或关节限位。
- 实际脚本/实体YAML已同步，`bash -n`、YAML解析和 `history_window > loss_grace` 断言通过。

### 下一步

- 在CAN反馈持续后复跑同一默认链；预期下一次候选更快停止搜索，短暂丢失时进入有历史依据的LAST_PATH_REACQUIRE，而不是无历史LOCAL_SEARCH。继续验收 `ALIGN -> GRASP_READY -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME`。

## 2026-09-29：第二次实体搜索确认重复有效帧仍会掠过目标

- 第二次默认一键链再次通过 `[7/7]`、观测姿态和SEARCH，CAN全程持续增长。深度探针多次看到约4 cm候选，其中明确记录 `(0.203,-0.080,0.350) m`、尺寸 `0.037x0.035 m`、高度 `0.029 m`，已经达到探针 `stable=3/3`。
- 控制器配置为 `target_acquire_frames=2` 时仍未停止该搜索段：探针的首条true已经代表三帧稳定，但机械臂继续移动后下一帧几何失配，第二条true未出现。该实证说明控制器的第二层重复帧要求仍会让已确认的目标离开视野。
- 搜索中还观察到 `0.095x0.083 m` 等过大的稳定凸起；为避免首条true策略放大误检风险，实体深度门控按现场约4 cm方块收紧为尺寸 `0.025..0.070 m`、高度 `0.020..0.070 m`，合成35 mm方块和两次真实35–47 mm候选仍在范围内。
- 控制器改为 `target_acquire_frames=1`：不是单帧深度授权，而是收到探针内部三帧稳定后的第一条true立即取消搜索。第二轮以Ctrl+C停止新增输出、保持使能，未执行失能、ResetPiper或自动零位运动。

### 下一步

- 复跑同一链，验收首条 `DEPTH_CUBE_CANDIDATE_VALID stable=3/3` 紧随 `STATE -> ALIGN`；随后验证5秒历史窗口能否完成短暂丢失恢复并进入GRASP_READY。

## 2026-09-29：第三次实体搜索确认LAST_PATH年龄判定不可达

- 第三次默认链再次通过 `[7/7]`、观测和SEARCH。候选 `pixel=(557.7,55.3)`、相机点 `(0.164,-0.102,0.339) m`、尺寸 `0.044x0.038 m` 在 `stable=3/3` 后约21 ms触发 `STATE -> ALIGN (TARGET_ACQUIRED)`，证明“首条探针true即停搜”修复生效。
- 目标随后多次稳定重捕获并进入ALIGN，但每次约2.5秒后仍落到 `LOCAL_SEARCH (LAST_TARGET_HISTORY_UNAVAILABLE)`。源码给出确定原因：`InitializePredictedReacquireLocked()` 仍要求最新历史样本年龄不超过实时 `target_timeout_s=0.6`，而该函数只会在 `target_loss_grace_s=2.0` 后调用，因此无论历史窗口设为5秒都必然失败。
- 修复只改变历史分支的年龄上限：已经变换并保存在固定 `base_link` 的样本使用独立 `target_history_window_s=5.0`；实时ALIGN仍保持0.6秒新鲜度要求，未允许用旧相机误差直接运动。第三轮以Ctrl+C停止输出并保持使能。
- 规范源码与实际 `/home/johnwick/piper_ws` 已同步；`brain_robot_pick_place`、`brain_robot_ball_pick` 实际构建安装成功。

### 下一步

- 复跑并验收丢失后进入 `LAST_PATH_REACQUIRE`（而非 `LAST_TARGET_HISTORY_UNAVAILABLE`），静止基座目标重投影成功后继续ALIGN/GRASP_READY。

## 2026-09-29：第四次实体搜索证实历史恢复可达，并改用基座三维稳定判定

- 第四次默认一键链在 CAN 3 秒 RX 增长 `7292` 帧后通过 `[7/7]`、观测姿态与SEARCH。深度候选 `pixel=(583.4,48.1)`、相机点 `(0.133,-0.079,0.248) m`、尺寸 `0.060x0.049 m`、高度 `0.052 m` 达到 `stable=3/3` 后进入ALIGN。
- 上一提交的历史年龄修复已经取得实证：目标暂失后控制器不再报告 `LAST_TARGET_HISTORY_UNAVAILABLE`，而是依次发布 `PHASE=LAST_PATH_REACQUIRE step=1/2 predicted_base_link_m=(0.087,-0.337,0.163)`、第二步预测恢复，最终才进入 `LOCAL_SEARCH (LAST_PATH_REACQUIRE_FAILED)`。固定基座历史分支已经可达，但两步重投影仍未重新取得实时几何。
- 灯光恢复后的持续运行确认全搜索没有停在固定角度：两次相隔约10秒的反馈中 J1 从 `0.680176448` 连续变化到 `0.431006352 rad`，J5 从 `1.007547996` 变化到 `0.862710464 rad`；实时TF也同步变化。当前断点不是“没有搜索轨迹”。
- 直接原因定位到深度探针稳定判定：旧实现比较候选在腕部相机中的像素中心和深度。静止方块在机械臂SEARCH期间必然随相机视角在画面中移动，因此真实候选曾只能达到 `stable=1/3`；这把相机自运动误当成目标运动，也不能可靠排除固定在末端上的自体几何。
- 最小修复：探针把每帧候选按该帧时间戳变换到 `base_link`，用三维欧氏距离 `<=0.025 m` 累积三帧稳定。静止桌面方块即使在像素中移动仍可稳定；反之，与腕部/夹爪一起运动的自体几何在 `base_link` 中会移动，不能以静态目标身份授权抓取。TF缺失时明确发布 `DEPTH_PROBE_STABILITY_TF_UNAVAILABLE` 并保持无效，不回退到像素授权。
- 本轮实体实例用Ctrl+C停止新增输出并保持PiPER使能；脚本明确未发送DisableArm、ResetPiper或自动零点复位。修改后 `py_compile`、TF2 Python API兼容性和 `git diff --check` 均通过；实际 `/home/johnwick/piper_ws` 两包重建成功。

### 下一步

- 直接复跑默认一键链，验收机械搜索过程中同一桌面候选的 `base_link_m` 保持稳定并达到 `stable=3/3`。若进入ALIGN，下一断点按 `GRASP_READY -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME -> TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED` 顺序定位；不得再以移动相机像素位移否决已固定在基座坐标中的静止目标。

## 2026-09-29：第五次实体SEARCH暴露单线程TF时间差并加年龄门

- 提交 `6716ae0` 后，CAN保持 `ERROR-ACTIVE` 且3秒RX增加约58 KB；默认脚本再次通过 `[7/7]`、到达观测姿态并进入SEARCH。搜索段持续被适配器接受，未出现关节越界、适配器失能或CAN守护触发。
- 新基座稳定逻辑第一次处理几何候选时明确拒绝：深度图时间 `1790652155.462543`，最新相机TF时间 `1790652155.456452`，仅相差约 `0.006 s`，但精确查询报“extrapolation into the future”。原因是深度探针使用单线程executor；图像回调内等待未来TF时，同一线程不能处理正在到达的TF消息。
- 修复保留精确时间查询为首选；只在精确查询失败时读取最新已缓存TF，并要求其与图像时间差不超过 `0.10 s`。诊断新增 `tf_age_s`；超过年龄门、没有TF或变换失败仍立即清零稳定计数，禁止用陈旧姿态授权抓取。当前搜索速度下6 ms时间差远低于25 mm基座稳定门。
- 本轮同样以Ctrl+C停止输出并保持PiPER使能，未执行DisableArm、ResetPiper或自动零位运动。修改后 `py_compile`、TF2异常API、范围内 `git diff --check` 通过，实际两包重建成功。

### 下一步

- 复跑同一默认链；首先验收候选诊断包含有界 `tf_age_s` 而不再因数毫秒未来外推清零，然后继续到 `stable=3/3 -> ALIGN -> GRASP_READY`。

## 2026-09-29：第六次实体搜索验证基座稳定，移除锁定后的多余像素追踪

- TF年龄门修复后的默认链再次通过 `[7/7]`、观测姿态和SEARCH。实体候选从像素 `(550.2,241.1)` 移动到 `(542.0,224.8)`、`(528.4,209.6)`，但对应 `base_link` 点仅为 `(0.338,-0.309,0.111)`、`(0.334,-0.311,0.115)`、`(0.332,-0.308,0.118) m`，帧间三维差为 `7/5 mm`，实际达到 `stable=3/3` 并触发 `STATE -> ALIGN`。这证明相机自运动下的固定基座稳定判定生效。
- 有界最新TF回退也实际生效，连续有效候选的 `tf_age_s` 约 `0.021..0.095 s`；一次 `0.101 s` 和反馈切换期间 `1.314..2.717 s` 的陈旧TF被年龄门拒绝。该门既容纳正常数毫秒错位，也没有允许秒级旧姿态进入抓取。
- 锁定后旧ALIGN仍继续按腕部像素运动：候选从 `(528.4,209.6)` 移到 `(509.6,191.3)`、`(491.9,185.2)`，基座点始终约 `(0.330..0.332,-0.303..-0.308,0.118..0.129) m`，随后分割暂失并进入LAST_PATH。对静止三维目标继续像素居中没有增加抓取信息，反而制造自运动视差和丢失。
- 最小骨架修复新增 `depth_only_direct_grasp_after_lock=true`：SEARCH/LOCAL_SEARCH在收到探针三帧固定基座证明后，立即取消搜索、停止Servo并发布 `GRASP_READY (DEPTH_BASE_LOCK_ACQUIRED)`；随后仍由原 `grasp_lift_executor` 捕获固定base_link模型并执行MoveIt碰撞检查、顶部倾斜候选、下降、闭爪、撤离和释放。未新增基础运动程序，未绕过适配器、IK、碰撞或反馈门控。
- 第六轮以Ctrl+C停止输出并保持使能。新增实体profile和源码回放断言直接pytest `5 passed`；实际两包构建成功，完整colcon结果 `13 tests, 0 errors, 0 failures, 0 skipped`。

### 下一步

- 直接复跑默认链，首个验收点改为 `DEPTH_CUBE_CANDIDATE_VALID -> GRASP_READY -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME`，再按 `TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED -> TOP_DOWN_PREGRASP_REACHED -> TOP_DOWN_DESCENT_TRAJECTORY_ACCEPTED -> GRIPPER_CLOSE_REQUESTED` 定位真实抓取的最早断点。

## 2026-09-29：第七次实体链首次锁模并定位错误工作区候选

- 默认链再次通过 `[7/7]`、观测和SEARCH，并按新骨架实际发布 `DEPTH_CUBE_CANDIDATE_VALID -> GRASP_READY (DEPTH_BASE_LOCK_ACQUIRED) -> GRASP_TARGET_MODEL_LOCKED_BASE_FRAME`。抓取执行器不再退回像素ALIGN，静态锁模和自动执行接线已经实证。
- 本次锁定点为 `base_link=(0.089,-0.329,0.164) m`，几何尺寸约 `0.053x0.048 m`、高度 `0.053 m`。MoveIt对该点所有顶部倾斜/yaw候选均返回IK `code=-31`，最终明确 `FAULT_TOP_DOWN_PREGRASP_PLAN_FAILED`；没有预抓取轨迹被发送、没有闭爪、没有失能或复位。
- 同一批运行日志已经给出目标方块的另一组固定基座证据：约 `(0.336,-0.311,0.109)`、`(0.331,-0.303,0.124) m`，尺寸约 `0.031..0.041 m`、高度约 `0.026..0.028 m`；前一轮同一目标曾在 `(0.332,-0.308,0.118) m` 达到三帧稳定。反复可达坐标与误锁的近基座点可明确分离。
- 结论：纯深度几何允许多个“方块状凸起”，只按图像最大面积会把近基座/远背景稳定结构当目标；IK拒绝是正确安全结果，不应通过关闭碰撞或扩大关节限位绕过。
- 最小修复为探针在同一深度帧中保留全部通过桌面/高度/尺寸/方形度的组件，逐个变换到 `base_link`，只在实体证据工作区 `x=0.20..0.45, y=-0.45..-0.15, z=0.08..0.20 m` 内选面积最大者。该门纳入已重复观测的真实方块约 `(0.33,-0.31,0.11)`，排除误锁 `x=0.089` 和背景 `x>=0.54`。
- 脚本因抓取故障自行停止输出并保持PiPER使能，明确未自动回零或失能。工作区修改 `py_compile`、直接pytest `5 passed`；实际两包构建成功，完整colcon结果 `13 tests, 0 errors, 0 failures, 0 skipped`。

### 下一步

- 复跑默认链，先验收近基座/远背景组件只产生 `DEPTH_PROBE_NO_CANDIDATE_IN_WORKSPACE`，随后真正方块约 `(0.33,-0.31,0.11)` 达到三帧稳定并进入GRASP_READY。下一断点必须来自该点的真实MoveIt预抓取，而不是再次调整IK或关节边界。

## 2026-09-29：第八次实体链首次生成真实方块预抓取轨迹

- 工作区门复跑生效：近基座/背景候选持续输出 `DEPTH_PROBE_NO_CANDIDATE_IN_WORKSPACE`；真正方块在 `(0.329,-0.304,0.120) m` 达到三帧稳定并进入GRASP_READY，抓取执行器锁定同一点，没有再次选择前轮 `x=0.089` 的错误几何。
- 顶部候选筛选最终选择 `tilt=0.700, yaw=0`，目标末端约 `(0.190,-0.304,0.285) m`。MoveIt首次为真实方块生成97点 `TOP_DOWN_PREGRASP` 轨迹，证明目标、IK和碰撞规划已经越过此前断点。
- 轨迹没有产生实体预抓取运动：唯一适配器在发送前拒绝 `point 55 exceeds limit for joint2` 并disarm，控制器同步进入 `PIPER_ADAPTER_DISARMED`；脚本报告 `FAULT_TOP_DOWN_PREGRASP_PLAN_FAILED` 后停止输出、保持使能，未闭爪、复位或失能。
- 当前MoveIt/URDF J2范围与已记录手册/控制器回读比适配器旧软件范围更宽，但本轮不放宽适配器安全边界。改为抓取执行器复用适配器现有六轴范围，在任何轨迹发布前逐点预筛；越界的tilt/yaw只记录 `REAL_LIMIT_REJECTED`，继续规划下一候选。只有全点均在原范围内的候选才会交给适配器；实际适配器仍保留独立二次检查。
- 执行器规划与执行已拆分：候选筛选阶段只规划不发送，选中安全轨迹后才执行；执行失败不会继续尝试另一候选。直接pytest `5 passed`，实际两包编译成功，完整colcon `13 tests, 0 errors, 0 failures, 0 skipped`。

### 下一步

- 复跑默认链，读取每个tilt/yaw的 `REAL_LIMIT_REJECTED`；若存在原适配器范围内候选，应首次得到 `TOP_DOWN_PREGRASP_TRAJECTORY_ACCEPTED/REACHED`。若全部候选均被原范围否决，保留使能和日志，再以规划结果调整抓取姿态，不修改适配器限位。

## 2026-09-29：第九次实体规划确认预筛有效并细化抓取姿态网格

- 真实方块再次稳定锁定在 `(0.340,-0.311,0.108) m`，状态进入GRASP_READY。候选预筛在执行器内拦截了全部越界计划，适配器始终保持armed，未出现 `PIPER_ADAPTER_DISARMED`，证明“规划但不发送”安全边界生效。
- 具体规划结果：`tilt=0.70,yaw=0` 为94点，J2峰值 `1.40811 rad`；`tilt=0.70,yaw=-pi/2` 为102点，J2峰值 `1.40630 rad`；`tilt=1.00,yaw=0` 为133点，J6最低 `-0.81375 rad`；`tilt=1.00,yaw=-pi/2` 为136点，J6最高 `+0.81375 rad`。四条均只略超原门但仍被拒绝，未发送任何预抓取轨迹。
- 不扩大J2/J6门。根据上述连续姿态证据，在候选网格中增加中间倾角 `0.75/0.85 rad` 和腕部yaw `±pi/4`；目标是改变IK分支/腕部分配而不是放宽限位。所有新增候选继续经过MoveIt碰撞规划、执行器逐点预筛和适配器二次检查。
- 脚本最终报告 `FAULT_TOP_DOWN_PREGRASP_PLAN_FAILED`，安全停止并保持使能，未闭爪、复位或失能。

### 下一步

- 复跑并优先观察新增 `tilt=0.75/0.85`、`yaw=±pi/4` 的规划；只有出现原限位内完整轨迹才允许进入实体 `TOP_DOWN_PREGRASP_REACHED`。
## 2026-09-29：严格真实限位下的候选抓取实测断点
- 本轮多次执行 /home/johnwick/start_brain_robot_cube_real.sh，根分区使用率 29%，can0 复用 1 Mbps/0.75 且 RX 持续增长；未重复固件、MasterSlaveConfig、ResetPiper 或基础 CAN 巡检。
- 每次运行均完成 [7/7]、当前姿态到观测姿态、OBSERVE_POSE_REACHED、SEARCH 和 GRASP_READY (DEPTH_BASE_LOCK_ACQUIRED)；深度目标约 base_link=(0.334..0.341,-0.309..-0.314,0.104..0.110)m，锁定后未重新追踪。
- MoveIt 现从 cube_task_real.yaml 读取与 piper_jog_adapter 相同的六轴 real_trajectory_joint_min/max，并补齐 Pilz 加速度限位；构建成功，12 项 replay 测试通过。
- 顶部候选在严格真实边界下全部 IK_ERROR_CODE_-31；侧向预抓取和最终接近已改为锁定基座目标/尺寸后两段离线规划，候选 tilt={0.35,0.75,0.95,1.10}、yaw={0,±0.785,±1.571,pi}、lateral={0,±0.06}，预抓取高度由 0.276m 提到约 0.390m 后仍全部 IK_ERROR_CODE_-31。
- 最新证据日志为 /home/johnwick/brain_robot_logs/ros/grasp_lift_executor_382493_1790675641296.log；始终未出现 DIAGONAL_SIDE_PREGRASP_TRAJECTORY_ACCEPTED、DIAGONAL_SIDE_APPROACH_TRAJECTORY_ACCEPTED 或 GRIPPER_CLOSE_REQUESTED。故障为 FAULT_DIAGONAL_SIDE_PREGRASP_PLAN_FAILED，脚本保持使能退出，未发送 DisableArm/ResetPiper。
- 当前阻断：锁定目标与 PiPER link6/真实适配器六轴限位的组合无可行 IK；下一步仅做无运动 URDF 零位、link6 工具偏移、目标中心/顶面语义核对或现场标定，不放宽限位、不盲发 JointCtrl。

## 2026-09-29：无运动几何审计与侧向候选坐标修复

- 深度探针源码核对确认 `/brain_robot_vision/depth_candidate_point` 发布的是候选连通区域的中值深度点：`z=median_depth` 位于方块可见上表面，而不是方块中心；同时发布的 `depth_candidate_size.vector.z` 是桌面平面到该表面的凸起高度。抓取执行器已有 `locked_object_size_m_` 冻结尺寸，不能把深度点误写成动态追踪点。
- 活动供应商 URDF `/home/johnwick/piper_ros/src/piper_description/urdf/piper_description.xacro` 明确 `joint6_to_gripper_base` 为零平移/零旋转 fixed joint；因此 `link6` 与 `gripper_base` 没有隐藏工具偏移，`end_effector_link: link6` 不是当前 IK `-31` 的原因。SRDF 的 arm chain 也确实是 `base_link -> link6`。
- 审计发现真实代码缺陷：侧向候选先用当前腕姿态把期望相机位置换算成夹爪位置，随后却改变末端 yaw/tilt；相机固定偏移没有随候选姿态旋转，造成目标位置与候选姿态不一致。并且侧向最终接近分支存在无条件 `continue`，预抓取即使成功也不会进入接近规划。
- 最小修复已写入 `grasp_lift_executor.cpp`：从当前 `gripper_base`/相机 TF 求固定的夹爪坐标系相机偏移；对每个候选姿态先旋转该偏移，再生成预抓取和最终接近目标。删除无条件跳过，预抓取与接近继续保持“先规划、碰撞检查、逐点真实限位预筛，选中后才输出”的安全顺序。
- 验证：活动 `/home/johnwick/piper_ws` 两包 `colcon build --packages-select brain_robot_pick_place brain_robot_ball_pick --symlink-install` 成功；`python3 -m pytest -q src/brain_robot_pick_place/test` 为 `12 passed`。新增静态断言覆盖候选姿态偏移重算和接近分支。尚未重新运动实机；上一实测仍是所有旧几何候选 `IK_ERROR_CODE_-31`，不能把本轮代码修复描述为抓取成功。

### 下一步

- 将本轮已编译修复同步到唯一规范仓库后，仅复跑一次默认链，观察同一锁定目标是否出现 `DIAGONAL_SIDE_PREGRASP_TRAJECTORY_ACCEPTED`；若仍全部 `IK_ERROR_CODE_-31`，继续依据新目标位姿日志做无运动坐标标定，不扩大适配器限位、不发送盲目 JointCtrl。

### 本轮实际运行补充

- 提交 `7e4fab7` 后实际运行默认脚本：根分区 29%/约 53 GB 可用，`can0` 1 Mbps/sample-point 0.750、`ERROR-ACTIVE` 且 RX 持续增长；脚本通过 `[7/7]`、`OBSERVE_POSE_REACHED`、SEARCH 和 `GRASP_READY (DEPTH_BASE_LOCK_ACQUIRED)`。
- 修复后的侧向日志确认每个候选末端位置已随候选姿态重算相机固定偏移；旧 J2/J6 包络下仍全部 `IK_ERROR_CODE_-31`，最终 `FAULT_DIAGONAL_SIDE_PREGRASP_PLAN_FAILED`。脚本停止视觉/适配器输出，未发送闭爪、DisableArm、ResetPiper 或自动回零，PiPER 保持使能。
- 尝试把 J2/J6 包络扩大到已回读官方物理范围时，安全策略阻止了该持久性边界变更；补丁未落盘。当前规范 HEAD 仍为 `7e4fab7`，阻断仍是“旧软件包络下目标无IK”。

## 2026-09-29：用户授权后同步官方 J2/J6 抓取范围

- 用户已明确授权将真实 J2 上限由 `1.40` 提高到 `pi`、J6 由 `±0.80` 提高到 `±pi`；授权仅覆盖这两个已回读官方物理范围的抓取边界，不覆盖其它限位或旁路控制。
- 已同步 `cube_task_real.yaml`、`cube_visual_search.launch.py`、`piper_jog_adapter.py` 和 `grasp_lift_executor.cpp`：MoveIt、候选预筛和唯一适配器共用同一新数组；J1/J3/J4/J5、搜索边界、速度、步长、反馈和急停门控保持不变。
- 仍保持“规划→碰撞检查→逐点限位/步长预筛→反馈起点检查→唯一适配器发送”的顺序；不写入控制器参数、不刷固件、不执行 ResetPiper/MasterSlaveConfig。

### 首次授权实跑与 J6 下限漏项

- 脱离终端运行默认链，实际完成 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定 `(0.330,-0.310,0.103) m`；全部侧向候选仍 `IK_ERROR_CODE_-31`，无轨迹、闭爪、复位或失能输出。
- 审计发现第一次同步只把 J6 最大值改为 `+pi`，漏掉授权中的最小值 `-pi`，MoveIt/执行器/适配器实际仍用旧 `-0.80`。当前最小修复只把三处 J6 下限同步为 `-pi` 并加入回归断言；其它轴和所有门控不变。

## 2026-09-29：完整授权范围实跑后恢复顶部/倾斜路径优先级

- J6 `[-pi,+pi]` 同步后的默认链再次实际通过 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定 `(0.336,-0.308,0.114) m`；72 个侧向候选仍全部 `IK_ERROR_CODE_-31`。无轨迹发送、闭爪、复位或失能，脚本保持使能退出。
- 代码路径审计确认 `diagonal_side_grasp_enabled` 位于 `top_down_grasp_enabled` 之前，因此只要侧向开关为真，历史上对真实方块生成过94/102/133/136点规划的顶部/倾斜路径永远不可达。扩大J2/J6后仍继续枚举侧向不再有价值。
- 最小动作只恢复已有高级抓取骨架的优先级：顶部/倾斜路径先运行；侧向路径仍保留为在配置明确关闭顶部时的备用。顶部路径同样先完整规划预抓取和下降、碰撞检查、逐点授权限位预筛，之后才允许实体输出。

## 2026-09-29：顶部倾斜路径首次规划并执行，断点收敛到预抓取反馈超时

- 提交 `983ce6f` 后以后台独立会话实际运行默认一键脚本；根分区使用率 29%（约 54 GB 可用），can0 复用 1 Mbps/0.75 且 RX 持续增长。脚本实际完成 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定静止深度目标 `base_link=(0.330,-0.313,0.104) m`。
- 顶部路径优先级修复生效。执行器选中 `tilt=0.75 rad, yaw=-pi/4`，MoveIt 生成 75 点预抓取轨迹；同一候选的最终下降为 100% 笛卡尔路径、4 个轨迹点、最大相邻关节步长 `0.011768 rad`。这首次证明真实目标在授权 J2/J6 范围内同时具备预抓取 IK、碰撞可行路径和下降路径。
- 唯一适配器接受了 75 点预抓取轨迹，机械臂真实反馈已运动到示例采样 `[-0.74193,1.64223,-0.99895,-0.11002,0.26396,0.0] rad`；但执行器在规划时长加 `trajectory_feedback_timeout_s=45 s` 后仍未确认全部轴进入 `0.04 rad` 末端容差，最终明确 `FAULT_TOP_DOWN_PREGRASP_EXECUTION_FAILED`。没有发送下降、闭爪、抬升或释放命令。
- 故障清理先停止视觉控制输出，再调用适配器 disarm；脚本明确未发送 `DisableArm`、`ResetPiper` 或自动零位运动，PiPER 保持硬件使能。日志为 `/home/johnwick/brain_robot_logs/authorized_topdown_20260929.log`、`/home/johnwick/brain_robot_logs/visual_stack.log` 和 `/home/johnwick/brain_robot_logs/ros/grasp_lift_executor_402189_1790689817634.log`。
- 当前唯一断点已从“无可行抓取姿态”前移为“可行预抓取已发送但反馈未在截止时间内收敛”。下一步只补充发布末端目标和超时逐轴偏差，并使截止时间覆盖初始最大关节差/适配器限速；不回退到视觉、CAN、点云或候选姿态排查，也不在已发送失败后自动换姿态继续运动。
- 已完成第一步诊断增强且不改变任何控制行为：每条实机轨迹发布前记录规划时长与六轴终点；反馈超时时记录反馈年龄及每轴 `measured/target/error`。规范源码与 `/home/johnwick/piper_ws` 已同步，两个包构建成功，完整 `colcon test-result` 为 `14 tests, 0 errors, 0 failures, 0 skipped`。

### 逐轴诊断复跑：预抓取和下降均成功，断点前移到夹爪反馈

- 提交 `684d4f7` 后默认链再次通过 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定目标 `(0.338,-0.314,0.106) m`。同一顶部候选 `tilt=0.75,yaw=-pi/4` 生成77点预抓取和100%的4点下降轨迹。
- 新诊断记录预抓取终点 `[-0.726192,1.66442,-1.03318,-0.146188,0.280476,0.183893] rad`、规划时长 `7.5324 s`；执行器随后发布了下降终点 `[-0.727011,1.68462,-1.03995,-0.151243,0.267093,0.188699] rad`，证明预抓取反馈确认已经成功。4点下降也被适配器接受并反馈确认，故本轮不得再修改腕轴插值或扩大轨迹超时。
- 流程首次实际到达 `GRIPPER_CLOSE_REQUESTED`，随后在5秒内进入 `FAULT_GRIPPER_CLOSE_FEEDBACK_UNCONFIRMED`；未执行抬升、释放或安全撤离。脚本停止输出并保持硬件使能，未发送DisableArm、ResetPiper或自动回零。
- 官方手册明确夹爪行程为 `0–70 mm`；当前官方SDK `GripperCtrl` 明确角度整数单位为 `0.001 mm`、`0x01`为使能、力矩整数单位为 `0.001 N·m`。因此实体profile的 `gripper_close_value=40000` 是40 mm开口；本轮深度方块尺寸约24–30 mm，该值即便执行也不能夹紧方块。
- 下一步只修复夹爪骨架：预抓取前50 mm张爪必须由反馈确认；小方块闭爪使用官方范围内的0 mm目标和1 N·m现有力矩，接触时允许“产生足够闭合位移但未到0”作为动作确认。未确认张爪或闭爪均停止且不抬升。
- 夹爪骨架已按该边界实现：张爪和释放要求反馈进入50 mm目标的3 mm容差；闭爪目标改为0 mm，允许反馈到达目标或相对张爪前产生至少1 mm闭合位移，以兼容方块接触阻止到零。反馈失败日志包含 `before/current/target/tolerance/minimum_motion`，禁止把无动作当成功。
- 规范源码与实际 `/home/johnwick/piper_ws` 已同步；两个包构建成功，完整测试为 `14 tests, 0 errors, 0 failures, 0 skipped`。尚未进行修改后的实体夹爪验证，不能把构建通过描述为已抓住方块。

### 张爪反馈门复跑：定位适配器未携带驱动所需力矩字段

- 提交 `f407016` 后默认链通过 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定 `(0.333,-0.310,0.111) m`。新增张爪反馈门在预抓取前明确停止：`before=-0.000700 m, current=-0.000700 m, target=0.050000 m`，最终 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED`；因此没有再次执行预抓取、下降或闭爪。
- 控制链源码核对给出确定根因：`piper_jog_adapter` 的一次性显式夹爪帧只追加了第7项 `name/position`，没有填写 `JointState.effort`；当前供应商驱动仅在消息显式含`gripper`且`effort`长度至少7时才调用官方SDK `GripperCtrl`。所以命令在ROS层被接收，但CAN夹爪控制函数被静默跳过，反馈保持原值。
- 下一步只让适配器在显式夹爪帧中附带第7项1.0 N·m力矩及前六轴0占位；普通六轴轨迹仍不含夹爪/力矩，保持“仅按需发送一次”规则。驱动脏工作树不修改。
- 该适配器修复已实现并同步实际工作空间：新增显式 `gripper_effort_nm=1.0`，只在一次性夹爪帧中产生 `effort=[0,0,0,0,0,0,1.0]`；发送后清空待发状态，下一帧仍为纯六轴。供应商驱动未修改。
- `py_compile`、直接pytest `13 passed`、实际两包构建和完整colcon测试均通过；最终为 `15 tests, 0 errors, 0 failures, 0 skipped`。尚未进行修改后的实体夹爪复跑。

### 力矩字段修复实跑：CAN证据把断点前移到ROS转发层

- 先清除了上次中断遗留的驱动、适配器和卡住的 `/piper_jog_adapter/arm` CLI进程；该诊断在夹爪发布前已经阻塞，因此未发送夹爪或关节命令。清理只终止软件进程，没有调用DisableArm。
- 实测现场照明使用内核恢复出的 `/dev/video0` 直接捕获 `1632x1224` 灰度帧：均值 `85.12`、P10/中位数/P90=`51/70/130`，暗像素比例为0，确认现场有灯光。Astra内同时打开OpenNI/UVC仍复现 `attempt to claim already-claimed interface 1`，故正式profile已恢复为RGB/IR/UVC关闭、depth-only；灯光检查不改变抓取数据面。
- 提交 `6ce36e8` 后默认一键链实际再次完成 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`，锁定 `base_link=(0.334,-0.311,0.108) m`，但仍在预抓取前报告 `GRIPPER_OPEN feedback unconfirmed: before=-0.000700 m current=-0.000700 m target=0.050000 m` 并安全停止、保持使能。
- 同步抓取 `can0,159:7FF,3A7:7FF` 共记录37961条夹爪反馈，但 `0x159` 控制帧为0条。`0x3A7`角度始终为`-700`（-0.700 mm），状态`0x40`表示驱动使能且无已编码故障；没有控制帧时不得把无动作归因于夹爪机械卡滞、零位或新固件。
- 为下一次最小复核增加逐层诊断：抓取执行器记录夹爪发布时订阅者数量；适配器记录命令是因无位置、disarmed、反馈陈旧而拒绝，或已接受并在六轴帧上追加target/1.0 N·m。控制行为、频率、限位和反馈门均不变。
- 规范源码与实际安装空间已同步；实际二进制包含新发布日志，适配器安装文件逐字一致。完整colcon结果为 `15 tests, 0 errors, 0 failures, 0 skipped`。

### 下一步

- 只复跑一次同一默认链并同步记录`0x159`：先依据“发布订阅者数→适配器接受/拒绝→一次性帧发出→CAN 0x159”的首个缺口修复。只有已经看到正确`0x159`而`0x3A7`仍无位移时，才允许核对夹爪初始化/回零接口；当前禁止盲目写零点或删除反馈门。

### 逐层复跑：深度1队列覆盖单帧，改为100 ms有界重复

- 提交`6c03656`后的默认链再次达到`OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`。逐层日志确认执行器向`1 subscriber`发布50 mm张爪；适配器随后依次记录`Accepted ... target=0.050000`与`Emitting ... effort=1.000 N.m`，因此执行器到适配器的ROS连接成立。
- 同期CAN跟踪仍没有任何`0x159`，而`0x3A7`持续约200 Hz。实际驱动对`/joint_commands`使用QoS深度1；适配器在夹爪组合帧后20 ms立即发布普通六轴帧，单次事件可能在驱动回调执行前被最新帧覆盖。这解释了“适配器已发、CAN仍为0”，无需修改夹爪零点或反馈门。
- 最小修复把显式组合帧限制为5次、50 Hz下约100 ms：每帧仍含六轴当前目标、`gripper`位置和第7项1.0 N.m；计数归零后自动恢复纯六轴。参数硬限为`1..10`，禁止永久恢复50 Hz夹爪洪泛。
- 实际工作区重建成功；单元测试改为验证恰好5帧均含正确位置/力矩、随后第6帧无夹爪，完整colcon结果`15 tests, 0 errors, 0 failures, 0 skipped`。尚未实体复跑该有界重复，不能宣称已出现`0x159`。

### 有界重复实跑：五帧均离开适配器，驱动内部仍无0x159

- 提交`e84ec03`后的默认链再次通过`[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`。适配器在连续五个20 ms周期明确记录`remaining=4..0`，每帧target=50 mm、effort=1.0 N.m；执行器5秒后仍收到-0.700 mm并停止在`FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED`。
- 同步CAN跟踪仍为`0x159=0`，因此“单帧被后续六轴帧覆盖”不是完整根因；五帧有界机制本身保持，因为它仍是对深度1订阅队列的确定性保护，但不得据此宣称驱动已调用SDK。
- 在规范仓库与实际工作区逐字对应的供应商驱动中加入行为不变的WARN诊断：显式gripper到达回调时记录角度、effort长度、enable和feedback门；调用`GripperCtrl`前记录实际SDK参数；门控或effort长度失败也明确记录。没有修改CAN ID、命令值、使能流程或输出门。
- 驱动包重建成功，`py_compile`通过，规范仓库的`test_command_validation.py`为`3 passed`。包自带全量lint仍因供应商存量代码的150项flake8/61项pep257错误失败，本轮不批量格式化供应商树，也不把该既有lint债务描述为控制失败。

### 下一步

- 用新驱动WARN仅复跑一次默认链；若回调未记录，定位DDS/话题接收；若记录但门控false，修反馈/enable时序；若明确记录`Calling GripperCtrl`而CAN仍无`0x159`，再检查SDK发送返回和SocketCAN发送路径。仍禁止跳到夹爪写零点。

### 驱动诊断复跑未触发夹爪，随后控制器CAN反馈停止

- 新驱动诊断轮通过`[7/7]`并进入SEARCH；目标在启动前静止阶段曾稳定出现于`base_link≈(0.339,-0.313,0.107) m`，但控制器尚为STOPPED。正式到达观测姿态后完整搜索周期内目标未再次进入深度视野，约4分钟有界等待结束，因此本轮没有夹爪消息、驱动WARN或`0x159`，不能据此判断驱动门控。
- 为避免再次等待目标，计划在下一轮SEARCH已armed后向现有`/brain_robot_grasp/gripper_command`发布一次50 mm请求；该请求仍经过适配器、完整六轴组合消息、驱动enable/feedback门和SDK，不旁路`piper_jog_adapter`。
- 但下一次默认启动在任何控制进程产生前发现CAN RX不再增长。USB-CAN `1d50:606f`仍枚举，旧`can0`显示1 Mbps/0.75、`ERROR-ACTIVE`且无bus-off/error-pass/bus-error，但连续3秒无任何帧。脚本按门控在运动前退出，未发送关节、夹爪、失能或复位命令。
- 在无控制进程时仅做一次受限恢复：旧接口down后up返回`ENODEV`；随后只重置USB-CAN适配器，内核重新记录`gs_usb ... Configuring for 1 interfaces`，新`can0`成功恢复UP/ERROR-ACTIVE/1 Mbps/0.75。恢复后的计数从0开始，但连续5秒仍为零帧，证明USB-CAN客体接口已恢复、PiPER控制器/物理CAN侧仍无发送。
- 根分区仍29%、约53 GB可用；此次零RX不是日志或磁盘容量导致。当前禁止再次启动运动或循环重载USB/CAN，直到PiPER控制器供电/物理链恢复并重新看到被动反馈帧。

### 下一步

- 外部恢复PiPER控制器供电或物理CAN链后，第一项只做5秒被动RX门；出现持续反馈才运行默认链，并在SEARCH已armed后完成一次50 mm适配器张爪诊断。无需重复固件、限位、TF、点云或搜索算法检查。

## 2026-09-29 23:50：纠正 CAN 零反馈归因——灯光 UVC 诊断拖死 VMware xHCI

- 用户指出期间没有触碰机械臂，因此重新按软件侧故障审计。内核时间线给出直接反证：`/tmp/piper_light_camera.log` 创建于 `23:09:50`，该次由代理启动的灯光相机诊断在 `23:09:55` 打开 UVC，并于 `23:09:56` 报 `attempt to claim already-claimed interface 1`；从 `23:09:57` 起，同一 VMware 虚拟 USB 主控 `0000:03:00.0` 立即出现 `ERROR unknown event type 37` 与 `Transfer event TRB DMA ptr not part of current TD`。仅 `23:09:57` 就有 996 条相关错误，`23:09:57..23:10:18` 累计数千条。
- USB-CAN `1d50:606f` 与 Astra `2bc5:0657/0557` 均位于该 xHCI 的 Bus 003；因此原提交 `5f00439` 中“PiPER 控制器/物理 CAN 侧仍无发送”的归因证据不足。正确结论是：代理违反了已经记录的 depth-only/UVC 禁令，启动冲突的 UVC 诊断并损坏虚拟 USB 数据面；CAN RX 随后归零不需要用户触碰机械臂即可发生。本轮明确承担该软件侧触发责任。
- 无控制进程时先执行 PCI function reset；设备号与拓扑未变化，5 秒被动 RX 仍为 0。随后对 `xhci_hcd` 的 `0000:03:00.0` 做一次 unbind/bind，内核完整注销并重建 Bus 003，USB-CAN 从 Device 18 重新枚举为 Device 6，Astra 也重新枚举；`can0` 按既定 1 Mbps、sample-point 0.75 恢复为 `UP/ERROR-ACTIVE`。这证明虚拟 xHCI 已真正重建，但重建后 5 秒被动 `candump` 仍为 0 帧，说明仅在 guest 内重建还没有恢复端到端收包。
- 全程没有 PiPER/MoveIt/Servo/视觉控制进程，没有发送 Enable、JointCtrl、GripperCtrl、DisableArm、ResetPiper 或任何运动命令。根分区仍约 29%，本次与磁盘空间无关。
- 当前阻断修正为“由冲突 UVC 诊断触发的 VMware USB/xHCI 数据面故障，guest 内控制器重建后端到端 CAN RX 尚未恢复”，不能再未经证据归到机械臂控制器或用户物理操作。下一恢复动作应是宿主侧对 USB-CAN 做真正的 VMware 断开/重新连接或物理断电重枚举；恢复后只做 5 秒被动 RX 门，再从夹爪 `0x159` 断点继续。

## 2026-09-29 23:55：guest 终端内端口断电恢复边界验证

- 当前无 PiPER/MoveIt/Servo/视觉控制进程；`can0` 仍为正确 1 Mbps/0.75、`UP/ERROR-ACTIVE`，3 秒被动 RX 为 0。VMware Tools 12.3.5 正常运行，但 `vmware-toolbox-cmd device list` 为空，不能从 guest 请求宿主 USB passthrough 的 disconnect/connect。
- VMware 虚拟 Hub `3-1` 声明支持逐端口电源控制，端口 2 精确对应 USB-CAN 序列号 `003F001E5246570520323934`。安装 Ubuntu 标准包 `uhubctl 2.4.0-1` 后，仅对 `3-1:2` 执行一次 3 秒 power cycle；工具报告 power off/on 成功。
- 但内核没有产生 USB disconnect/re-enumerate，USB-CAN 设备号仍为 6，说明 VMware 只更新了虚拟 Hub 状态位，没有把 guest 端口请求转化为宿主侧真实断电。恢复 `can0` 后 8 秒 `candump` 仍为 0 帧，RX 仍为 0。
- 本轮未启动机械臂驱动，也未发送任何 CAN 控制、使能、失能、复位或运动命令。无需重启 PiPER；guest 内可用的 device reset、xHCI 重建和 Hub 端口 power cycle 均已验证，不能继续重复。
- 当前唯一最小恢复动作是宿主 VMware 菜单对 `candleLight USB to CAN adapter` 执行一次 Disconnect/Connect，或物理拔插 USB-CAN 使其真正断电重枚举。完成后先验证 5 秒 RX；恢复才从夹爪 `0x159` 断点继续。

## 2026-09-30：CAN 恢复后定位夹爪驱动崩溃，并验证独立 RGB 数据面

- 用户恢复 USB-CAN 后，`can0` 回到 1 Mbps、sample-point 0.75、`ERROR-ACTIVE`；被动 5 秒收到约 12k 帧，后续 2 秒持续增加约 4868 帧，零 bus error/drop。SDK/ROS 六轴反馈恢复，实体默认链再次达到 `[7/7] -> OBSERVE_POSE_REACHED -> SEARCH -> GRASP_READY`。
- 该轮抓取执行器发布 50 mm 张爪，适配器接受并发出恰好 5 个组合帧，但供应商驱动在第一条新诊断日志处因 `RcutilsLogger.warning()` 被传入多个位置参数而抛出 `TypeError`，发生在 `GripperCtrl` 调用之前；同步抓包 `0x159=0`。这解释了此前“适配器已发、夹爪无动作”，不是夹爪零点或固件结论。
- 已把四条新增诊断改为单个 f-string，并增加 AST 回归测试，禁止 ROS logger 再接收多于一个位置参数。实际 `/home/johnwick/piper_ros` 同步后，`colcon build --symlink-install --packages-select piper`、`py_compile` 通过，聚焦测试 `4 passed`。
- 最小实体复核只保持当前六轴 `[-0.2378, 0.9818, -0.7585, 0, 0.5475, 0] rad`，以 1 N.m 请求夹爪张到 50 mm。驱动保持存活，5 帧均记录 `Calling GripperCtrl: angle=50000 effort=1000`，确认崩溃已消除；但 3 秒后夹爪反馈仍约 `-0.700 mm`，监听器未见 `0x159`。当前 SDK 明确将 `GripperCtrl` 编码为 0x159，但 CAN socket 设置 `local_loopback=False`，所以同机 `candump` 缺帧不能单独证明未发送；实体反馈未变化仍表示张爪动作尚未验收。测试结束只 disarm 适配器、停止节点，未 DisableArm、ResetPiper 或归零。
- 用户现明确要求恢复视觉语义，不再使用 depth-only 作为目标授权。无运动数据面试验证明：Astra 继续只开 OpenNI 深度时，独立 `image_tools/cam2image` 以 V4L2 读取 `320x240@5 Hz` RGB 可与 `640x400@30 Hz` 深度并存；两路均有真实首帧，CAN 仍持续增加。直接请求 `640x400` RGB 会因 V4L2/GStreamer 数据流错误失败，因此不能照搬该分辨率。
- Astra 在关闭 RGB 发布时仍提供只读 `/camera/get_camera_info` 服务，返回原生 640x480 彩色内参；不持续发布 `/camera/color/camera_info`。现有检测器要求 RGB/深度图同尺寸，故下一最小实现是将 320x240 RGB 中心裁成 320x200 后缩放到 640x400，并改用同步深度内参/光学帧完成三维点计算；随后无运动验证紫色、矩形、深度和物理尺寸门控，再把一键默认切回视觉目标。

### 当前断点与下一步

- 尚未完成实体抓取。已完成：观测、搜索、静止三维锁模、预抓取规划/运动、下降与夹爪 ROS 调用链；当前两个剩余断点是夹爪实体反馈未变化，以及 RGB 低带宽输入尚未接入一键检测器。
- 下一步先提交本轮驱动崩溃修复；随后实现/测试 RGB 中心裁剪缩放与一键 V4L2 启动，在无运动模式确认真正紫色方块 `target_valid + depth_valid` 后再复跑完整链。

## 2026-09-30：默认恢复 RGB 语义目标并完成无运动实机数据面验收

- 用户明确撤销 depth-only 作为默认目标授权，要求恢复视觉抓取。实体配置的视觉控制器与抓取执行器现均设为 `depth_only_target_enabled=false`；深度仍保留为三维位置、稳定性和物理尺寸门控，紫色+矩形+稳定深度共同授权，不退回背景见紫即对齐。
- Astra 的 libusb UVC 继续永久关闭；一键脚本新增独立内核 V4L2 `image_tools/cam2image`，默认 `320x240@5 Hz` 发布 `/camera/color/image_raw`。默认 `BRAIN_ROBOT_DEPTH_ONLY_TARGET=0`，诊断时仍可显式设为1。相机健康门同时要求真实 RGB 与深度帧，并在缺帧时重建两路输入。
- 检测器仅在 RGB/深度尺寸不同时进行确定性映射：320x240 RGB 中心裁剪 `(0,20,320,200)` 后缩放到 640x400 深度网格；三维投影改用 `/camera/depth/camera_info` 和 `camera_depth_optical_frame`。颜色、矩形度、宽高比、深度MAD/连续帧和物理尺寸门全部保留。
- 实际运行树同步并构建成功；两包完整测试为 `16 tests, 0 errors, 0 failures`。无 PiPER/MoveIt/适配器的实机探针同时取得 320x240 BGR 和 640x400 深度首帧，检测器记录 `RGB_DEPTH_GRID_ALIGNED source=320x240 crop=(0,20 320x200) output=640x400`，CAN 两秒仍增加约4857帧且无错误。
- 当前静止姿态的 RGB 快照平均 BGR 约 `[200.3,199.7,200.7]`，按实体阈值统计紫色像素为0，检测器正确发布 `target_valid=false`、`depth_valid=false`、`DEPTH_REJECTED_TARGET_LOST`。这不是 RGB 链路失败：真实帧和对齐回调均已验证，只表示当前相机姿态没有看到紫色方块；下一次必须由既有 SEARCH 扫描寻找，不能放宽颜色门或凭背景触发。
- 夹爪补充诊断按官方示例的连续发送方向，把同一50 mm/1 N.m请求扩展为约0.5秒；驱动实际调用 `GripperCtrl` 22次，六轴保持不变，夹爪反馈仍为约-0.700 mm。SDK将状态字`0x40`解码为“驱动使能=true、归零状态=false”，不是过流/过热错误，因此本轮没有发送清错、失能或写零点。增加帧数已证明无效，不写入默认配置。

### 下一步

- 直接运行默认一键脚本，验收独立 RGB 启动后 `OBSERVE_POSE_REACHED -> SEARCH -> PURPLE_CUBE target ACQUIRED -> GRASP_READY`。若到达夹爪阶段仍无反馈，先记录实体夹爪当前物理开合状态；只有确认夹爪确实处于机械闭合基准，才可按官方夹爪专用流程评估设零，禁止把它与六轴 ResetPiper/失能混用。
## 2026-09-30：软件 RGB-D 标定配准复核与当前阻断

- 当前实机默认链尚未完成抓取；上一轮真实一键运行已证实 [7/7] -> OBSERVE_POSE_REACHED -> SEARCH 和搜索轨迹持续下发，CAN 为 ERROR-ACTIVE、零 bus error/drop。
- 只读 RGB 抓帧与深度候选对照发现：实际紫色方块在 RGB 中 HSV 色调约 147、饱和度中位数约 46，原配置 saturation_min=70 会把真实方块完全过滤；已将门限改为 35，但紫色、矩形、稳定深度、尺寸和未裁边门控仍全部保留。
- 真实 320x240 RGB 与 640x400 深度并非同一像素网格。尝试 Astra 官方 depth_align=true 时，因 OpenNI 彩色流保持关闭，设备不再发布深度帧；该实验已回退为 depth_align=false，没有启用冲突的 libusb UVC。
- 通过只读 /camera/get_camera_info 与 /camera/extrinsic/depth_to_color 获取本机 Astra 序列号 CC136530302 的工厂标定：彩色 640x480、fx=fy=488.8685、cx=310.7305、cy=209.0377；深度到彩色旋转与平移已写入检测器，平移从驱动报告的毫米换算为米。V4L2 RGB 的水平镜像事实作为显式参数记录，检测器现按标定投影每个有效深度像素取彩色值；标定缺失时目标保持无效。
- 该软件配准路径已同步到实际工作区并构建成功。离线 7 passed，完整 colcon test 为 16 tests, 0 errors, 0 failures, 0 skipped。仅相机+检测器实测记录 RGB_DEPTH_SOFTWARE_ALIGNED source=320x240 depth=640x400 mapped=190125 mirror_x=true；当前固定姿态未看到方块，故仍为 PURPLE_CUBE target LOST，没有启动运动控制。
- 实验期间没有执行刷写、MasterSlaveConfig、ResetPiper、DisableArm 或任何机械臂运动命令；测试用的 Astra、V4L2 和检测器进程均已停止。下一最小动作是重新运行唯一默认一键脚本，在新配准和 HSV 门限下验收 SEARCH -> target acquired -> GRASP_READY，然后再处理已有夹爪反馈断点。

## 2026-09-30：新一键启动被当前 USB/xHCI 数据面门控阻断

- 新一键运行命令为 BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh；磁盘为 29%、约 54402 MB 可用，脚本在 [1/7] 正确拒绝启动运动，因为 can0 RX 未增长。
- can0 仍为 UP、1 Mbps、sample-point 0.750、ERROR-ACTIVE，累计 RX 7398221 但本次 5 秒 candump 增量为 0；无控制进程、无任何运动或失能命令。
- 同期内核持续报告 xhci_hcd 0000:03:00.0 的 Transfer event TRB DMA ptr not part of current TD。按既有决策，guest 内 USB reset/xHCI 重载已完成且不可循环重复；当前实际阻断是 VMware USB-CAN 端到端数据面，需要宿主侧对 USB-CAN 做 Disconnect/Connect 或真实断电重枚举后再运行脚本。
## 2026-10-09：恢复 can0 后默认链到达观测并搜索，运行期 RX 再次中断

- 规范仓库起始 HEAD 为 `cfbbdbf`。本轮实际确认仓库 `/mnt/hgfs/ub`；运行树为 `/home/johnwick`，启动脚本默认 `BRAIN_ROBOT_AUTO_START=1`、`BRAIN_ROBOT_DEPTH_ONLY_TARGET=0`。
- 用户报告已恢复后，初态实为 USB-CAN `1d50:606f` 已枚举、`gs_usb` 已绑定，但 `can0` 为 DOWN/STOPPED、RX=0。`sudo -n true` 返回 0；未触碰 USB 设备、VMware 透传或 xHCI，仅按既有 1 Mbps/sample-point 0.75/txqueuelen 1000 参数配置并 UP 接口。随后 `can0` 为 ERROR-ACTIVE，有限 1200 帧被动抓包中 `0x251..0x256` 各 51 帧，bus error=0。
- 被动 SDK 预检（`C_PiperInterface_V2 0.6.2`，`piper_init=false`）得到高速反馈 100 Hz、低速状态 20 Hz；当前六轴 `[-0.066,-0.005,0.018,0.165,0.252,-0.107] rad`、速度全为 0、使能全 False，collision/error 全 False。目标观测姿态 `[0,0.98,-0.75,0,0.30,0] rad`；执行器只走当前姿态到观测姿态，不执行全零复位。
- 实际运行命令：`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`。根分区 34% 降到 33%，约 51 GB 可用；脚本通过 `[1/7]..[7/7]`，RGB/深度首帧正常，点云仍未送入 Octomap。14 点、49.1 秒观测轨迹被 `piper_jog_adapter` 接受，状态明确到达 `OBSERVE_POSE_REACHED -> SEARCH`。
- RGB 检测曾 `PURPLE_CUBE target DETECTED` 后变为 LOST；控制器进入 ALIGN，随后 `TARGET_LOST_DURING_ALIGN -> LAST_PATH_REACQUIRE -> LOCAL_SEARCH -> SEARCH`，期间多条 31–42 点搜索轨迹均被唯一适配器接受。未到 `GRASP_READY`，未执行预抓取、下降或夹爪命令。
- 运行期守护于 `2026-10-09 11:43:59` 记录 `CAN_RX_STALLED_3S`，发出 emergency stop 并终止脚本（会话返回码 143）；退出路径报告保持当前位置/使能，没有 `DisableArm`、ResetPiper 或回零。停止后 `can0` 仍显示 UP/ERROR-ACTIVE、USB 设备仍在 sysfs、gs_usb 仍绑定，但 18 秒被动观察 RX 计数固定为 676928，`candump` 5 秒 0 帧，bus error=0。该时间窗未见 xHCI/USB 内核错误。证据日志：`/home/johnwick/brain_robot_logs/{visual_stack.log,cube_detector.log,piper_driver.log,can_health.log}`。
- 本轮未做 USB 断开/重连、USB reset、xHCI 重载或额外运动。RX 未恢复前不重跑一键脚本；下一步先只读追踪 USB-CAN URB/反馈停止原因，待连续 `0x251..0x256` 恢复后再继续搜索和抓取。

### 2026-10-09 11:50：CAN 零 RX 期间的 USB 端口只读复核

- 当前仍无启动脚本、PiPER 驱动、MoveIt、视觉控制器或适配器进程。被动 RX 计数仍固定 `676928`；can0 `UP/ERROR-ACTIVE`、1 Mbps/0.750、bus errors=0，USB-CAN `1d50:606f` 仍枚举且 `gs_usb` 绑定。
- xHCI debugfs 显示 PCI 控制器 `0000:03:00.0` 仍由 `xhci_hcd` 驱动、runtime active、`USBSTS=0`；槽位 06 对应 `3-1.2`（USB-CAN），端口状态 `Connected Enabled Link:U0`。本轮未发现支持“USB 设备已物理断开”的证据。
- 临时加载 usbmon 后对 Bus 3 做 3 秒只读采样，没有观察到可打印的 USB-CAN URB 记录；随后已卸载 usbmon。该观察不足以确定 URB 停止原因，也不能区分控制器端静默与虚拟 USB 数据面停流。未执行 USB reset、CAN bounce、xHCI 重载或控制命令。
- 下一步需要用现场控制箱和 USB-CAN 指示灯的短视频核对设备是否仍供电/活动；在端到端 `0x251..0x256` 连续反馈恢复前保持无运动，并先定位接收停流原因。

### 2026-10-09：用户询问当前流程断点与和训练集项目的差异

- 本轮只读复核：规范仓库 HEAD 为 `053ebda`；无一键脚本、PiPER/视觉控制器/适配器等活动进程。`can0` 仍为 `UP/ERROR-ACTIVE`、1 Mbps/sample-point 0.750、bus error=0，但 3 秒 `rx_packets` 增量为 0（累计值仍 `676928`）；不能安全启动运动链。
- 最近一次已记录的实体链确实通过 `[7/7]`、当前姿态直达观测姿态并明确到达 `OBSERVE_POSE_REACHED -> SEARCH`。运行日志还显示 `FULL_SEARCH`、`LAST_PATH_REACQUIRE`、`LOCAL_SEARCH` 多条搜索轨迹被适配器接受；相位日志出现 J1 正/负、J5 上/下搜索，因此“完全没有进入搜索/没有提交搜索轨迹”不符合该轮日志证据。
- 但视觉日志中的 `PURPLE_CUBE target DETECTED/LOST` 多次切换；控制器短暂进入 ALIGN 后以 `TARGET_LOST_DURING_ALIGN` 回到重捕获/局部搜索。CAN 守护随后报 `CAN_RX_STALLED_3S` 并停止输出。该轮没有达到 `GRASP_READY`，更没有预抓取、下降或闭爪；不得将检测到紫色像素等同于锁定三维方块。
- 因果分层：最新即时阻断是 CAN 反馈中断；其前一软件断点是目标检测/稳定锁定不足。训练集可能影响识别泛化，但现有日志并不支持“缺训练数据是唯一或首要根因”；目前证据也不足以确定 RX 停流发生在 USB 主机接收、适配器固件还是机械臂反馈端。不得把二者混为一个问题。
- 下一步：先在不发送控制的情况下继续定位 RX 停流；仅在连续反馈恢复后复跑默认链，并同步采集视觉目标状态、锁定三维坐标、控制器状态、搜索关节实际反馈及 CAN RX 增量，确定首次失败门。若需要用户补充，优先要一段涵盖机械臂、控制箱指示灯、USB-CAN 指示灯和目标物的短视频；无需用户粘贴终端输出或提供猜测的关节参数。

### 2026-10-09：排除 `gs_usb` echo 异常恢复例外，确认需要外部数据链恢复

- 本轮复核规范 HEAD `cea7647`；`can0` 仍 `UP/ERROR-ACTIVE`、1 Mbps/0.750、RX 676928，最终3秒 RX 增量仍为0，`rx_errors=0`、`rx_dropped=12907`，CAN错误/重启计数为0。USB-CAN仍枚举且绑定 `gs_usb`；没有活动 PiPER/运动/视觉控制进程。
- 对全量内核日志定向搜索，没有发现规范决策所列 `gs_usb Unexpected out of range/unused echo id` 记录，因此不满足唯一允许一次性重建 can0 的异常例外。未 bounce `can0`、未 USB reset、未重载 `gs_usb`/xHCI，也未发送任何 CAN 控制帧。
- 本轮新动作仅为只读复核和3秒被动RX测量；结果与上轮相同。guest 侧端点/接口都呈正确枚举与 UP，但没有端到端反馈。依照既有决策，当前唯一可继续的恢复条件是外部 VMware USB-CAN Disconnect/Connect 或实体 USB 透传状态变化后重新观测持续 RX；在此之前不得启动默认运动脚本。

### 2026-10-09：CAN RX 停流定位到客体 USB Bulk-IN 队列疑似清空

- 本轮开始时重新核实规范仓库 HEAD 为 `96e5e53`；无启动脚本、PiPER驱动、视觉控制器、适配器或相机进程。`can0` 仍为 `UP/ERROR-ACTIVE`、1 Mbps/0.750，bus error=0，RX 计数 `676928`；连续3秒增量为0。USB-CAN `1d50:606f` 仍枚举在 `3-1.2`、绑定 `gs_usb`，没有执行设备重置、CAN bounce 或 xHCI 重载。
- `sudo -n true` 返回0。只读 xHCI debugfs：slot 06 的 endpoint context 中 Bulk-IN 与 Bulk-OUT 均报 `running`。对应 Bulk-IN 环的 `enqueue` 与 `dequeue` 快照均为 `0x0000000118070890`，环 cycle 为0；Bulk-OUT 环的两个指针均为 `0x000000010cb5dd60`，环 cycle 为1。TRB cycle 标记与对应 cycle 一致，不能把它们解释成已失效；关键观察仅是入队/出队指针相等。端口仍连接，`can0` 接口仍 UP。
- 证据解释为强推断而非根因结论：相等的环入队/出队指针通常表示 xHCI 环上没有未消费的排队传输，但端点仍报 running；这符合 `gs_usb` 接收 URB 没有继续挂在 host ring 上的表现。该视图不能说明 URB 为什么不在队列中，也不能据此断言 USB 物理断开或机械臂未发送。尚未捕获导致该状态的 callback、取消状态或内核错误。
- 下一步是在不更改端点、接口、驱动状态的前提下，检查 `gs_usb` 当前内核实现/可用只读跟踪点，寻找能够确定 URB 取消/未重提交原因的证据；如果 guest 不暴露该信息，则需要宿主 VMware USB 透传侧一次真实 Disconnect/Connect 后再验证持续被动 RX。RX 连续恢复前不运行一键运动脚本。
### 2026-10-09：用户报告恢复后的CAN及官方SDK兼容性复核

- 规范仓库 HEAD 为 `90357ce`。重新核验实际 guest：USB-CAN `1d50:606f` 已枚举、内核驱动 `gs_usb` 已绑定；`can0` 是 `DOWN/STOPPED`，RX/TX 统计均为0；无启动脚本、PiPER、视觉、MoveIt、适配器控制进程。与上一轮 `UP/RX=0` 状态不同，但这不代表反馈已经恢复。
- 规范允许对 DOWN 接口按 1 Mbps、sample-point 0.75、txqueuelen 1000 做一次有限配置。受限命令环境中 `sudo -n true` 被 `no new privileges` 阻止；经允许的主机检查也读到了接口，但 `ip link set ...` 被 `RTNETLINK: Operation not permitted` 拒绝。因此未能将接口 UP，没有继续重试、没有 USB reset/xHCI 重载、没有启动驱动或运动，也没有发送 CAN 控制帧。当前唯一实机阻断是控制执行环境缺少 CAN 管理权限；即使解除该权限门，仍需被动证明 RX 持续增长后方可启动。
- 只读确认运行时为 Python `piper_sdk==0.6.2`、ROS 驱动 `piper_ctrl_single_node.py` 使用 `C_PiperInterface_V2`，`pyAgxArm` 未安装。已检查安装 SDK：`ReadCan` 遇到 `CanOperationError`/其它异常会退出线程；FPS monitor 更新健康标志但不负责重启接收线程。应用节点已有高频反馈及聚合关节反馈新鲜度门，缺帧时抑制输出。此代码证据支持“SDK 接收线程可能静默死亡”为一个可检验的软件弱点，但不能解释/证明当前 CAN RX 停止的根因；当前接口 DOWN 与 VM USB-CAN 接收链仍须分层验证。
- 上游只读资料已登记在 `docs/UPSTREAM_RESOURCES.md`。AgileX 官方 pyAgxArm CAN 手册明确表示仅支持随臂官方 CAN 模块；本机 USB ID/`gs_usb` 只证明 guest 枚举，不能证明它是官方随臂模块，因此适配器兼容性仍未证实。官方 `agx_arm_ros`/`pyAgxArm` 是候选参考，不迁移、不覆盖供应商源码、不绕过唯一 `piper_jog_adapter`。GitHub issue #109/#112/#118 是用户报告，不能当成厂商确认根因。
- 下一步：恢复能对 guest CAN 接口执行受限 `ip link` 的权限/宿主透传上下文后，仅完成一次接口配置并被动采集连续 `0x251..0x256`；若 CAN 帧持续，再运行现有默认一键链采集观测→搜索→检测锁定断点。CAN RX 未恢复时不运行控制链。上游迁移研究需在独立工作区完成并先固定 commit SHA。

### 2026-10-09：用户报告接口恢复后的即时复核

- 用户报告已恢复接口后，重新只读核验 guest 仍显示 `can0 DOWN/STOPPED`、RX/TX=0，USB-CAN `1d50:606f` 仍枚举且绑定 `gs_usb`，无运动控制进程。因此“已恢复”目前未在此执行环境表现为可用 SocketCAN 接口或有效反馈。
- 按授权参数再次尝试一次 `ip link set can0 type can bitrate 1000000 sample-point 0.75`、设置队列并 UP，仍因执行器无 `CAP_NET_ADMIN` 返回 `RTNETLINK answers: Operation not permitted`。未重试、未启进程、未发送 CAN 帧/运动命令。
- 只有当此执行会话能配置 guest 网络接口，或 guest 内接口本身已 UP 且被动 RX 持续增长，才可继续启动默认一键链。当前不是机械臂运动/视觉阶段故障，而是执行会话无法操作且观察到 CAN 接口仍 DOWN。

### 2026-10-09：重启后恢复CAN并验证自动搜索；用户发现调试图左右疑似镜像

- 重启后实际状态变化：`sudo -n true` 返回0。USB-CAN `1d50:606f` 枚举，`can0` 初始DOWN；按已授权参数配置为1 Mbps/sample-point 0.75/txqueuelen 1000后UP/ERROR-ACTIVE、bus errors=0。被动5秒抓到 `0x251..0x256` 每类52帧、`0x3A0` 104帧、`0x3A1..0x3A7` 每类103帧，RX持续增长。
- 运行默认 `/home/johnwick/start_brain_robot_cube_real.sh`（`BRAIN_ROBOT_AUTO_START=1`、保留紫色RGB-D默认路径）。当前姿态→观测姿态轨迹14点/49.1秒由唯一适配器接受；随后状态进入SEARCH，FULL_SEARCH/LOCAL_SEARCH多段轨迹被接受，实际CAN TX增长且RX持续增长、错误为0。检测器短时多次报告 `PURPLE_CUBE target DETECTED` 后又LOST，控制器在ALIGN和重捕获间切换，未到GRASP_READY，也未发抓取/夹爪命令。
- 用户指出识别窗口中目标左右位置疑似与实景相反。源码核对：窗口显示的不是原始 `/camera/color/image_raw`，而是 `cup_detector_node.cpp` 先按深度像素与工厂外参重采样得到的RGB-depth注册图，再叠加中心十字、掩码和状态文字；黑区为没有映射到RGB的深度像素。实际配置 `color_mirror_horizontal=true`，代码将投影得到的 `full_color_x` 改为 `color_width-1-full_color_x` 后采样V4L2原图。该参数只反转配准采样X，不执行整幅显示图的 `cv::flip`；如果物理V4L2镜像方向判断错，检测出的深度网格X会落到相反一侧。当前截图+用户现场观察构成需要验证的反证，但尚未通过同步原始RGB/注册图A-B对照证明应该设true还是false。
- 为避免镜像方向错误时继续视觉ALIGN，调用 `/visual_search_controller/stop`、`/servo_node/stop_servo`、`/piper_jog_adapter/disarm`；三项服务成功，其中适配器回复命令输出保持在反馈位姿。随后对一键脚本发SIGINT，按其保护trap清理本轮启动的ROS/相机/驱动节点；未执行ResetPiper、DisableArm或硬件失能。停止时实际关节反馈约 `[J1=0.577,J2=1.011,J3=-0.746,J4=0.038,J5=1.035,J6=0] rad`，六轴速度为0；CAN RX继续增长、TX停在21171、bus errors=0。当前抓取目标未锁定、未抓取。
- 下一步：保持实体适配器disarmed，不重启运动链。单独采集同一静态场景的原始V4L2 RGB、深度和注册调试图，在无运动条件下分别按 `color_mirror_horizontal=true/false` 做离线/被动配准对照；以方块在原始图中的实测侧向和对应深度X为准确定参数。只修正确证的镜像映射并运行离线回归，再以一次默认自动链验证SEARCH/ALIGN。禁止只凭J1/J5运动方向反转或仅为让目标“移向中心”而盲改 `horizontal_error_sign`。

### 2026-10-09 12:20：解释 `/image` 并复核当前静态图像链

- 用户截图标题`/image`来自一键脚本的`image_view` remap；实际订阅`/brain_robot_vision/debug_image`。这张图是配准后的RGB落在深度像素网格上的调试输出，叠加图像中心与`TARGET LOST`文本，不是原始相机帧；黑色空洞表示深度点无效或没有有效颜色采样。截图没有紫色方块，因此不能由此图判明左右方向。
- 实际配置`color_mirror_horizontal=true`仅翻转注册时源RGB的X采样，不对整幅debug图做`cv::flip`。如果该假设错，目标颜色会落到错误深度侧；不能因此把控制器误差符号直接反向。
- 只读实测`can0`为`UP/ERROR-ACTIVE`、1 Mbps/0.750，3秒被动收到`0x252..0x256`与`0x3A0..0x3A7`，CAN TX仍为21171。此时ROS仅`/parameter_events`和`/rosout`，无机械臂/控制节点。为静态采图，仅启动已登记的depth-only Astra、V4L2 320x240@5Hz RGB与一个检测器；日志确认两路有效输入，`mapped=171428 mirror_x=true`，结果仍为`PURPLE_CUBE target LOST`。未启动PiPER驱动、MoveIt、Servo、适配器或搜索，未发布任何控制命令。
- 因目标未在当前静止视野内出现，true/false镜像A/B无法判断物理左右对应。已停止采图组件，ROS恢复仅默认话题，未改变配置。下一步仍是固定相机/机械臂、方块在画面中可见时成对核验原始RGB、配准图和深度目标X；核验完成前不恢复ALIGN。
### 2026-10-09：按用户授权仅返回观测姿态并在搜索前停止

- 用户授权范围为“仅返回观测姿态”；本轮未进入 SEARCH、ALIGN 或抓取，也未执行复位/失能服务。为遵守该边界，在高级控制器 PREPARE 完成观测轨迹后加入可选 `stop_after_observe` 门：开启时发布保持/零速停止并转到 `STOPPED`，原因 `OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`，早于 SEARCH 状态转换；实体 profile 默认仍为 `false`，不改变正常一键完整搜索路径。
- 运行默认一键组件至 `[7/7]` 后，仅对本次运行把控制器参数设为 `stop_after_observe=true`，启用 PiPER 和现有唯一适配器并调用现有 PREPARE。控制器日志先记录观测轨迹 11 点、36.8 秒并由适配器接受，随后明确记录 `STATE -> STOPPED (OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH)`；本次日志没有 SEARCH 轨迹。停止脚本时保护清理保持当前位置，未调用 `DisableArm` 或 `ResetPiper`。
- 到达时 `/joint_states` 六轴为约 `[0.00689, 0.98114, -0.74960, 0, 0.30803, 0] rad`，速度均为0；与观测目标 `[0,0.98,-0.75,0,0.30,0]` 的最大偏差约0.0081 rad。服务状态/原因话题也分别确认 `STOPPED` 和 `OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`。CAN 当时为 ERROR-ACTIVE、RX持续增加、bus errors/drop为0。
- 当前环境构建 `brain_robot_pick_place` 与 `brain_robot_ball_pick` 成功；`brain_robot_pick_place` 测试及聚合结果为16 tests、0 errors、0 failures、0 skipped。测试确认 profile 默认不开启该停止门，并确认停止门位于 SEARCH 转换之前。
- 该一次观测动作只验证“当前姿态→观测姿态”和授权停止边界，不能据此宣称搜索或镜像问题已解决。此前静态相机视野未见紫色方块，因此当前没有可判定左右映射的静止目标A/B证据；镜像参数仍未确认。下一步需在不动机械臂的静态可见方块画面下核对原始RGB、配准图及 true/false 映射，再由用户授权后恢复搜索。当前停止在观测姿态，不再发运动命令。

### 2026-10-09 12:38：观测位静态 RGB-D 对照发现方块落在深度视野之外

- 规范仓库仍为 `/mnt/hgfs/ub`，当前基线提交 `2a98d86`；实际脚本 `/home/johnwick/start_brain_robot_cube_real.sh` 与规范副本 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` SHA-256 相同（`7c0fa3c6…d97bc90`）。运行中的控制器/配置源码也与规范树 SHA-256 相同。
- 宿主只读检查确认 `can0 UP/ERROR-ACTIVE`、1 Mbps/sample-point 0.750，2秒 RX 增量约4850帧，错误/丢帧为0；磁盘根分区使用33%。`/joint_states` 单一发布者返回六轴 `[0.00689038,0.98113778,-0.749603568,0,0.308026152,0] rad`，速度为0。视觉控制器仍为 `STOPPED / USER_STOP`，参数 `stop_after_observe=true`；适配器 `motion_enabled=false`。本轮未调用任何运动服务、未搜索/对齐/抓取、未ResetPiper或DisableArm。
- 检查到本次一键组件的 ROS 子进程仍在运行（PiPER、Astra、检测器、MoveIt/Servo、视觉控制器和抓取执行器），但脚本父进程已不在；适配器运动门关闭且视觉控制器停止。初始 `/camera/color/image_raw` 发布者数为0。只启动已验证的 V4L2 `cam2image` 320x240@5Hz 静态输入（非 Astra UVC），测得约4.998 Hz；采集后停止本轮 RGB 进程，发布者恢复为0。注意：因此次异常退出/启动残留，后续仍需在用户批准搜索前审查脚本进程组清理，不能误认核心 ROS 节点已退出。
- 同场景原始 RGB 帧 `/tmp/piper_raw_observe.png` 为320x240，静态方块 HSV(色相125–160、S≥35、V≥45) 连通区域框约 `(146,206,28,33)`、共667像素；检测器配准调试帧 `/tmp/piper_debug_observe.png` 为640x400、紫色像素0，`target_valid=false`。临时图不纳入 Git。
- 使用当前 `/camera/depth/camera_info`（640x400，fx=fy=478.7569、cx=326.1356、cy=199.8735）和配置中的 Astra 工厂RGB内参/深度到彩色外参，离线复现同一帧的源RGB→深度配准。`color_mirror_horizontal=true/false` 两种结果均无紫色深度像素；映射的有效深度像素数均为170745。原始方块中心约 `(160,222)`，变换回深度网格的垂直坐标约 `v=432`（以有效深度0.375–0.992m计算几乎不变），落在深度图400行范围之外。水平镜像只影响X，不能消除此竖直FOV/重叠缺口。因此当前 `TARGET LOST` 的直接解释是该观察位可见RGB方块但彩色/深度不重叠，尚不能据此确认镜像方向；未改 `color_mirror_horizontal`、HSV或水平误差符号。
- 当前配置的既有 SEARCH 扫描轴为J1/J5，J5垂直范围 `-0.60..0.95 rad`，本来应通过垂直扫描把方块带入深度共同视野；但运行时 `stop_after_observe=true` 和 `USER_STOP` 阻止了该阶段。本轮授权仅覆盖返回观测姿态，不能据此继续发SEARCH运动。下一步需要用户明确允许恢复既有受MoveIt碰撞/限位/反馈门控的 SEARCH（先只运行至检测目标，不做ALIGN/抓取），并在开始前打印当前姿态、扫描边界、速度/停止条件；若获授权再核对持续往返轨迹及RGB-D重叠。

### 2026-10-09 12:40：用户授权只搜索至目标有效，加入搜索命中即停止门

- 用户明确授权从观测姿态运行现有 J1/J5 搜索，使用 MoveIt 碰撞、适配器限位和反馈门控；目标有效后立即停在 ALIGN/抓取之前。当前状态已复核：`can0 ERROR-ACTIVE`、1 Mbps/sample-point 0.750、2秒RX增量4858、CAN错误/丢帧0；`/joint_states` 约199 Hz，实测 `[0.00689038,0.98113778,-0.749603568,0,0.308026152,0] rad` 且六轴速度0；`/arm_status` 错误码0、六轴角度限位标志均false、通信状态异常标志均false。适配器当前 `motion_enabled=false`，控制器 `STOPPED/USER_STOP`，没有正在发起的搜索动作。
- 运行时保护范围已读取：适配器关节最小值 `[-1.50,-0.30,-1.40,-0.80,-1.20,-pi] rad`、最大值 `[1.50,pi,0.40,0.80,1.20,pi] rad`，最大速度 `0.189 rad/s`；搜索仅请求 J1/J5，J1 `[-1.35,1.35] rad`、J5 `[-0.60,0.95] rad`，速度上限分别 `0.135/0.108 rad/s`，规划分段最大关节步长 `0.20 rad`，每段反馈超时15秒。更正帧数：控制器 `target_acquire_frames=1`；检测器自己的深度目标有效门要求3帧稳定深度，因此控制器只在检测器已确认有效后停止。任一反馈/限位/碰撞/急停异常仍按故障停止处理。
- 为确保授权不越界，在 `HandleSearchLocked` 和 `HandleLastPathReacquireLocked` 中新增 `stop_after_target_acquired` 运行时门：稳定目标达到后以 `TARGET_ACQUIRED_STOPPED_BEFORE_ALIGN` 调 `StopLocked`，不会进入 ALIGN 或 GRASP_READY。实体 YAML 默认false；一键脚本新增 opt-in 环境变量 `BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=1`，只在本次有界验证启用；普通 `BRAIN_ROBOT_AUTO_START=1` 仍默认完整目标路径，不等按键。规范和运行时源码、配置、脚本 SHA-256 一致。
- 实际 `/home/johnwick/piper_ws` 构建 `brain_robot_pick_place` 与 `brain_robot_ball_pick` 成功（分别38.4s与30.2s）；`colcon test --packages-select brain_robot_pick_place` 及测试汇总为16 tests、0 errors、0 failures、0 skipped；规范/运行时一键脚本 `bash -n` 通过，目标文件 `git diff --check` 通过。
- 下一步在提交此代码后运行同一个默认自动一键脚本（AUTO_START保留默认1，仅设置本次 stop-at-target 环境开关），复用脚本单实例清理和 `[7/7]` 健康门；启动前确认相机RGB帧、CAN RX、使能服务返回和当前关节未漂移。观测位微小修正后进入既有 J1/J5 SEARCH；一旦控制器报告目标命中停止态，立即采集目标有效/坐标与关节反馈并结束本次脚本，不触发对齐/抓取/硬件失能。若目标未命中，受限搜索可持续至显式停止，必须持续监控反馈和过程日志。

### 2026-10-09 13:07：实机一键自动搜索命中目标并在 ALIGN 前安全停止

- 按用户授权执行 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=1 /home/johnwick/start_brain_robot_cube_real.sh`；根分区可用约50GB（33%），清理门通过。脚本无按键等待，完整通过 `[7/7]`，RGB `/dev/video0` 的320x240@5Hz帧、Astra深度帧、MoveIt/Servo、TF与点云自体过滤门均通过。
- 自动序列从反馈 `[0.00689038,0.98113778,-0.749603568,0,0.308026152,0] rad` 开始，控制器发布当前姿态到观测姿态的2点、20秒准备轨迹，随后发布 `OBSERVE_POSE_REACHED` 并进入 `SEARCH`。日志记录两次 `SEARCH_PLAN_ACCEPTED source=FULL_SEARCH`，适配器实际接受42点和41点轨迹，证明J1/J5搜索不是停在固定角度。
- 检测器运行时确认 `RGB_DEPTH_SOFTWARE_ALIGNED source=320x240 depth=640x400 ... mirror_x=true`，并在搜索中报告 `PURPLE_CUBE target DETECTED`。控制器随后发布 `PHASE=SEARCH_TARGET_ACQUIRED_STOPPED_BEFORE_ALIGN` 和 `STATE -> STOPPED (TARGET_ACQUIRED_STOPPED_BEFORE_ALIGN)`；同步话题 `target_valid=true`，命中时反馈约 `[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0] rad`。没有进入 `ALIGN`、`GRASP_READY`，也没有发送抓取、ResetPiper、零点复位或 `DisableArm`。
- 按有界授权用 Ctrl-C 结束脚本等待段；保护清理停止视觉/Servo并 disarm 适配器，保持PiPER硬件使能。随后以 `auto_enable=false` 仅恢复低层反馈驱动，实测 `/joint_states` 约200Hz、六轴速度0，`/arm_status.err_code=0`、六轴限位和通信异常标志均false。CAN继续 `UP/ERROR-ACTIVE`、1Mbps/sample-point 0.750，错误/丢帧0、RX持续增长。
- 本轮直接完成了“自动启动→观测姿态→SEARCH→目标有效”的闭环；尚未完成的不是搜索或基础链路，而是本轮明确禁止越过的 `ALIGN/FINAL_ALIGN→GRASP_READY→抓取`。下一动作必须在保持当前命中姿态和新鲜反馈的前提下取得继续对齐/抓取授权，再运行完整后半段；不得把本轮目标命中停止误报为最终抓取完成。

### 2026-10-09 13:41：用当前实机姿态和同步 RGB-D 帧确定水平镜像方向

- 当前实测六轴为 `[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0] rad`，速度全为0；驱动错误码0、六轴限位/通信异常均false，CAN为1 Mbps/ERROR-ACTIVE且RX持续增长。用安装的 PiPER URDF 和启动文件中的相机支架变换做正向运动学，得到 `gripper_base=[0.176836,-0.067266,0.301295] m`、`camera_depth_optical_frame=[0.093837,-0.089188,0.372923] m`，相机光轴在基座坐标约 `[0.652225,-0.248106,-0.716272]`；这与现场照片中腕部相机朝向桌面的实体布局一致。
- 在不发送运动命令的情况下用内核 V4L2 采集当前 RGB（320x240）和 Astra 深度（640x400）。原始 RGB 的紫色候选框为 `(24,104,37,34)`；深度有效范围为244--473 mm。按同一工厂内参/外参离线配准：`mirror=false` 的紫色区域为 `(118,200,69,66)`，其深度中位数311 mm、范围306--319 mm，并覆盖深度图中方块凸起；`mirror=true` 的区域为 `(581,200,57,67)`，深度中位数300 mm、范围297--304 mm，落在背景平面。现场照片与当前 RGB 左侧方块位置共同确认现行 `color_mirror_horizontal=true` 是错误的。
- 已将规范 `cube_detector.yaml` 改为 `color_mirror_horizontal: false`，测试期望同步更新；旧的 `true` 运行时尚未重启加载。临时图像均留在 `/tmp`，不提交供应商或采集文件。下一步构建/单测并核对安装空间哈希，再运行默认自动链；只有检测器以 false 发布稳定 RGB-D 目标后才继续 ALIGN/预抓取。

### 2026-10-09 15:17：结合真实关节/照片重建姿态，修正镜像和倾斜方块形状拒绝

- 本轮从基线 `44fa7c2` 延续用户“自行检查关节、结合实物图模拟并查看相机图像”的指令。末次反馈六轴仍为 `[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0] rad`，六轴速度0、夹爪0.0459；`/arm_status.err_code=0`，六轴限位与通信异常标志false，`can0 ERROR-ACTIVE`、错误/丢帧0。根分区34%、约50GB可用。本轮没有发起 SEARCH/ALIGN/抓取、复位或失能。
- 从安装URDF逐关节FK重建实体骨架（米）：J1/J2原点 `[0,0,0.123]`，J3 `[-0.117442,0.044675,0.378839]`，J4/J5 `[0.117543,-0.044711,0.366537]`，J6/夹爪座 `[0.176836,-0.067266,0.301295]`。按既有相机支架TF，相机 `[0.093837,-0.089188,0.372923]`、光轴 `[0.652225,-0.248106,-0.716272]`；当前检测点相机坐标 `[-0.112469,0.020220,0.311]` 映射基座约 `[0.323129,-0.056080,0.136051]`。重建图 `/tmp/piper_current_scene_fk.png` 和只读脚本 `/tmp/piper_scene_fk.py`；这是基于反馈/URDF/现有支架参数的几何重建，符合照片中弯臂及相机向桌面布局，不是独立标定、动力学或碰撞仿真，照片不能给出未经标尺验证的绝对尺寸。
- 发现规范配置已false但实际 `/home/johnwick/piper_ws/src/.../cube_detector.yaml` 仍true，说明仅colcon构建不能自动部署规范修改；已通过最小补丁同步实际配置和测试文件。控制器源码本来与规范相同；测试初次同步后失败实际来自 `SetStateLocked` 多行格式的字符串断言，修正断言后通过，不能误报为控制器缺失。规范与运行时 `cup_detector_node.cpp` SHA-256均 `90510e5f090ef2342f992a0425a093ab72385323f54e4bfe4401171a94c3c0b8`，检测配置均 `2df167ca878179e3f75c82f2ac286f756cd712082627209566429b5a7742a48c`。
- 静态采图最初仅RGB成功。统一既有 `FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml` 后深度仍不出帧，因此不能只归因DDS。旧Astra PID16485/16503节点存在但不产出图像/内参，SIGINT后仍占用设备；新进程报告 `Resource busy`。精确TERM旧两个相机进程后退出，新Astra PID31977/32017取得设备并恢复深度。未重载CAN/USB或改变机械臂。后续只读终止身份以进程为准，不能凭节点存在判断相机健康。
- false静态实机调试图紫色框 `(118,200,69,68)` 与原RGB左侧方块对应，检测点深度311mm。进一步发现倾斜方块轮廓面积2562px、轴对齐框69x67，填充率0.554低于现有0.58门，造成 `DETECTED/LOST` 反复；同轮廓最小旋转矩形约60.004x50.813、填充率0.840。按OpenCV官方 `minAreaRect` 定义修正实体形状门：新增 `shape_use_rotated_rectangle`（默认false，实体cube配置true），仅形状填充率/宽高比采用旋转矩形，保留原像素框深度ROI、三帧稳定深度及真实尺寸门。参考 https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html 。
- 构建 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回0；末次 `colcon test --packages-select brain_robot_pick_place` / `colcon test-result --test-result-base build/brain_robot_pick_place/test_results` 为15 tests、0 errors、0 failures、0 skipped。脚本bash语法和本轮文件diff检查通过。规范/实际脚本均SHA-256 `ea36d761d410b139e54eb25c0dd391442c1c8a27ce36a05f3e8ee4661d977c02`，并补齐遗留 `depth_cube_probe.py` 的进程检测/清理模式，避免旧目标模型发布者残留。
- 最后25秒静态实机验证在初始化三帧后一次转 `PURPLE_CUBE target DETECTED`，直到定时退出无后续LOST；读到 `target_valid=true`、`DEPTH_GRASP_ALLOWED`、相机点 `[-0.112468693,0.020219751,0.311] m`，调试图显示 `RECT=0.86 AR=1.18 SIZE=0.044x0.044m MAD=0.003`。日志 `/home/johnwick/.ros/log/2026-10-09-15-13-53-009441-johnwick-virtual-machine-32811`；当前图 `/tmp/piper_raw_observe.png`、`/tmp/piper_debug_observe.png`、`/tmp/piper_depth_observe.png`。临时RGB/检测器通过timeout SIGINT正常退出（命令124表示预定计时结束），相机和只读反馈驱动保留，机械臂当前位置/使能保持。
- 本轮推进的是正确目标定位与视觉稳定性，未增加搜索范围；观测/搜索已在前轮实机验证。当前具体下一步为沿既有主线从当前新鲜反馈执行 ALIGN/目标锁定/预抓取，检验实际轨迹反馈和抓取门，不回到旧底层实验。最新明确一次性运动边界仍为“只搜索至目标有效、ALIGN前停止”；用户本轮要求检查/理解不自动扩大该边界，继续实体后半段需明确授权。即使镜像和形状门已验证，总目标抓取/抬升/释放/安全回位尚未验收。

### 2026-10-09 15:26：修正镜像后的实测目标快照完成预抓取/下降规划复核

- 上轮分类为实际进展：`4302789` 已修复并实机静态验证镜像/倾斜形状门。本轮保持“仅搜索至目标有效”的最近实体运动边界，执行的是新目标坐标快照的离线规划，不重复旧固件/CAN或旧目标离线实验。
- 用实测Q `[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0] rad` 和经修正视觉/既有相机TF计算的基座目标 `[0.323129,-0.056080,0.136051] m`。复用当前安装PiPER MoveIt模型、`cube_task_real.yaml`限位、Pilz PTP和现有 `PopulateTopDownPose` 的姿态/工具偏移公式。在隔离 `ROS_DOMAIN_ID=78` 启动仅MoveGroup与robot_state_publisher，明确 `allow_trajectory_execution=false`；没有驱动、适配器、Servo、视觉控制器或抓取执行器。夹爪模型是预备张爪的两指各25mm假设，未控制实物夹爪。
- 初次隔离检查已有预抓取成功，但下降返回 `-21 FRAME_TRANSFORM_FAILURE`。定向日志显示缺少 `base_link -> world` 的TF；这是测试launch缺少robot_state_publisher，不是实机异常。补齐同一URDF的状态发布器并清理旧隔离进程后复核，首个现有候选 `tilt=0.35,yaw=0` 成功：预抓取 `code=1`、61点；下降 `code=1`、fraction=1.0、返回5点，所有点在实体限位内、相邻跳变≤0.35rad。
- 预测预抓取终点 `[J1..J6]=[-0.232237510,1.416212625,-1.096807729,0.093981355,0.999282509,-0.269562727] rad`；下降终点 `[-0.230317560,1.426373535,-1.084155177,0.094637059,0.976396612,-0.269912638] rad`。这证明同一高级抓取几何存在“变换腕部角度→预抓取→下降”的可行模型路径，不需要盲目扩大搜索范围或另写实体运动程序。
- 临时启动/检查脚本现持久保存为 `brain_robot_arm/scripts/piper_plan_review.launch.py`、`brain_robot_arm/scripts/piper_review_plan.py`，显式拒绝除78外的ROS域，仅含规划客户端和隔离状态快照发布器，不提供执行接口；读取当前实体YAML，不混用备用配置。复现命令：source ROS/PiPER/app安装空间后设置 `ROS_DOMAIN_ID=78 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml`，分别 `ros2 launch /mnt/hgfs/ub/brain_robot_arm/scripts/piper_plan_review.launch.py` 与 `PYTHONNOUSERSITE=1 /usr/bin/python3 /mnt/hgfs/ub/brain_robot_arm/scripts/piper_review_plan.py`。若没有完整路径，检查脚本明确返回2；正向本次返回0。两脚本语法检查通过。
- 成功证据日志 `/home/johnwick/.ros/log/2026-10-09-15-23-08-351109-johnwick-virtual-machine-33500`，MoveGroup日志 `/home/johnwick/.ros/log/move_group_33530_1791530588646.log`。完成后精确TERM本轮PID33500/33528/33530并确认不存在；真实域0读到机械臂Q保持原值、速度0，`/joint_commands` publisher=0/subscriber=1，证明没有实体输出。末次ps无目标返回1是确认清理完毕的预期值。
- 限制：快照规划只含模型自碰撞，未注入未经测量的桌面/世界障碍，也不证明支架标定、实物夹持、抬升和释放可靠。不能把规划成功写成实机抓取完成。下一步仍需在用户允许ALIGN及完整后半段后，用同一一键脚本和新鲜目标/关节反馈实际执行并逐门验收；授权问题已在上轮提出，当前保持原姿态/使能。

### 2026-10-09 15:28：实机后半段授权边界阻断审计

- 当前提交 `4550fb0`。前两轮已有具体进展：镜像/倾斜形状修复与静态检测通过（`4302789`），新目标快照预抓取/下降规划通过（`4550fb0`）；未把离线规划替代实体抓取验收。本轮不再重复这些实验。
- 最小当前状态核验：真实域0 `/joint_states` 返回六轴 `[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0] rad`、速度0、夹爪0.0459，时间戳 `1791530881.917019636`；`/joint_commands` publisher=0/subscriber=1；进程匹配没有视觉控制器、抓取执行器、适配器或MoveGroup。命令末尾pgrep返回1表示无这些残留节点，不是链路异常。本轮没有使能/失能、轨迹或夹爪命令。
- 同一明确边界已连续三轮保留：最近用户仅授权“搜索至目标有效、在ALIGN/抓取前停止”，后续要求检查关节/照片/相机图像，没有撤销该限制；代理上轮已请求允许完整后半段，目前无回答。当前没有新的技术故障证据，阻断的是实体ALIGN/预抓取/闭爪/抬升/释放/安全回位的执行权限；通用长期目标自动续跑不能代替对这条具体限制的撤销。
- 已完成范围内直接影响下一次执行的视觉修复和新目标路径复核。不能靠重复已完成只读检测或再造离线实验来绕开权限边界。依据目标阻断审计，将目标标为blocked而非complete，保留原完整目标；待用户明确允许后恢复，先核验新鲜关节/目标，再运行同一默认一键脚本（不设置目标命中停止开关）逐门验收完整后半段。所有实体阶段仍未完成，不宣称总目标已达到。
# 2026-10-09 完整实机链路授权恢复（执行准备）

### 本次执行结果与相机启动修复

- 收尾只读核验（时间戳1791536535.323171753）：六轴保持[-0.110263524,0.978346740,-0.754784436,0,0.688724008,0]rad，速度全0，夹爪45.9mm；/joint_commands publisher=0/subscriber=1，can0 UP/ERROR-ACTIVE/1Mbps/0.750。下一轮先读取此反馈和新gripper_can部署，不在未知实体闭合基准写零点、不重复22次发送。目标仍active，未标记抓取完成。

- 后续用户答复“未做或不确定”（升级后夹爪完全闭合位置标定），因此当前实体零点基准仍未确认，不自动写0xAE。已为下次一键运行新增只收不发的gripper_can日志，过滤0x159/0x3A7/0x2A8，纳入原进程组和日志容量维护；可以把驱动调用与真实总线控制/反馈关联，避免下次仍缺CAN证据。两脚本最新SHA一致ec8e84acf35023abe3155d4e18d491fe7e2d01339df266347c55a56fda621d82。
- 相机恢复mock的负向测试首次把fail模拟为return，不能模拟生产exit，测试进程已Ctrl-C结束；改为exit后重新运行，正向深度/RGB恢复和负向三次恢复失败退出均真实PASS。前面的通过记录以此次纠正后的结果为准。该测试不涉及实体输出。

- 默认全链脚本会话18024实际运行完并返回1。先因复用Astra PID31977/32017无深度帧停在[2/7]；ROS发布者存在却无帧。原脚本的健康守护在RGB/深度首帧都通过之后才启动，因此这里的“自动恢复仍在运行”提示不符合事实。针对已确认无帧的旧相机组TERM后重启，深度门通过。
- V4L2 RGB首次只发布1帧后停住；父PID45470停止后子PID45477仍占video0，下一次启动日志明确Device busy。精确终止旧子进程并启动唯一RGB后首帧通过。没有重建CAN或重试旧固件诊断。
- 同一脚本随后完成[7/7]、PREPARE 6点/20秒、适配器接受、OBSERVE_POSE_REACHED、SEARCH（42点/41点轨迹）、ALIGN/TARGET_ACQUIRED、GRASP_READY/DIRECT_VISUAL_ALIGN_ACQUIRED。执行器锁定基座目标(0.334,-0.071,0.144)m，发送50mm/1N.m张爪；适配器发5个有界帧，驱动4次明确调用GripperCtrl(50000,1000,0x01,0)。
- 精确终止门：FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED。before=current=0.045900m，target=0.050000m，容差0.003m；尚未进行预抓取、下降、闭爪、抬升、释放。异常清理未DisableArm/ResetPiper/回零，保持使能。恢复auto_enable=false反馈驱动，会话61937；实测Q=[-0.110263524,0.978346740,-0.754784436,0,0.688724008,0]rad，错误码0。
- 被动0x3A7八帧均角度00 00 B3 4C=45900，即45.9mm，状态0x40。官方SDK定义bit6使能、bit7归零状态；0x40未编码故障但未标记归零。此轮没有同步0x159抓包，故驱动调用日志不能替代总线发送证据，不能直接定性为夹爪硬件故障。旧22次重发无效的结论保留，不再盲目延长发送或放宽张爪门。
- 官方接口https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD明确0xAE是设当前位置为零点；官方demo https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_set_gripper_zero.py 先仅失能夹爪再写当前零点，并不自动寻找实体闭合基准。未知实际闭合基准时不执行。已异步询问升级后是否曾在完全闭合处标定，尚待答复；这是资料核对，不把未答复当硬件故障证据。
- 修复规范/运行一键脚本wait_for_actual_frame：输入首帧连续3次缺失即调用现有对应相机清理/启动函数，最多恢复3次仍失败则明确退出保持；不依赖尚未启动的后台守护。两个脚本bash -n通过、SHA一致fbe70ca7201ca9cd3111c6dfaf0cf61f6578794dae81909d0160aab7a79865ac。mock验证深度/RGB各一次恢复后仍要求真实帧成功，持续无帧三次恢复后退出。该修改尚未再次实机复跑，不把mock称为实机验证。
- 证据：/home/johnwick/brain_robot_logs/visual_stack.log、piper_driver.log、rgb_camera_recovery.log。下一步围绕夹爪首次缺口核对0x159实际发送/0x3A7响应及实体标定历史；正常完整权限继续有效，但未确认张爪前禁止预抓取。总目标保持未完成。

- 用户明确答复“运行”“允许”，撤销此前仅搜索至有效目标的边界；目标恢复active。允许既有默认链路ALIGN、预抓取、抓取、抬升、释放、安全返回后失能。不刷写、不MasterSlaveConfig、不ResetPiper。
- 当前can0 ERROR-ACTIVE，2秒RX增量4866，无错误/丢帧。磁盘50GB可用、使用34%。实测六轴[-0.363480628,0.978364184,-0.754819324,0,0.662104464,0]rad、速度0、夹爪0.0459m；错误码0，限位/通信异常标志均false。仅反馈驱动和Astra运行。
- 运行/规范脚本SHA一致ea36d761d410b139e54eb25c0dd391442c1c8a27ce36a05f3e8ee4661d977c02，实体YAML一致8736785a6d70b08da491302515457b247d30d535f975bcf0d52228f1359d8b8f。检测mirror=false、旋转矩形门true。
- 先执行当前姿态到[0,0.98,-0.75,0,0.30,0]rad（约20秒，以规划为准），随后现有搜索与抓取。搜索J1[-1.35,1.35]、J5[-0.60,0.95]rad，速度0.135/0.108rad/s；适配器上限0.189rad/s、加速度1rad/s²及原实体限位保持。脚本启用门核验实际使能；异常停止输出保持使能，正常先确认安全回位再失能。
- 命令：BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh。这里只记录准备，不代表执行成功；后续补充各门实际结果。
## 2026-10-09：实机复跑到 GRASP_READY，修正不可达的张爪目标

- 本轮起始 HEAD 为 `ced1e4a`；按固定启动顺序确认规范仓库 `/mnt/hgfs/ub`，读取任务、交接、进度和决策文档。实际运行树与规范脚本 SHA 一致 `ec8e84acf35023abe3155d4e18d491fe7e2d01339df266347c55a56fda621d82`，真实 YAML SHA 一致 `8736785a6d70b08da491302515457b247d30d535f975bcf0d52228f1359d8b8f`。
- 只读前置确认 CAN RX 三秒增量 `7279`，`gs_usb` 已加载，磁盘使用率 34%、可用约 50 GB；普通 PTY 因 `no new privileges` 无法运行脚本内 sudo，特权会话复用同一脚本后通过该门。未执行 USB reset、xHCI 重载、ResetPiper 或 MasterSlaveConfig。
- 实际命令为 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`。特权会话通过 `[1/7]..[7/7]`、深度/RGB首帧和TF自体过滤门；观测轨迹由适配器接受，进入 `OBSERVE_POSE_REACHED -> SEARCH -> ALIGN -> GRASP_READY (DIRECT_VISUAL_ALIGN_ACQUIRED)`。这次没有在搜索阶段发生CAN停流。
- 目标检测器记录 `mirror_x=false` 的软件RGB-D配准并报告紫色目标；状态机确认目标后进入抓取执行器。抓取执行器通过适配器发出50mm/1N.m张爪请求，但三秒后安全停止：`FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED before=0.045900 current=0.045900 target=0.050000`。未发送预抓取、下降、闭爪、抬升、释放或失能；脚本保持当前位置和硬件使能。
- 驱动日志明确记录三次 `Calling GripperCtrl: angle=50000 effort=1000 code=0x01 set_zero=0x00`；只收CAN日志收到17357条`0x3A7`，角度持续约45900（45.9mm）、状态0x40。当前SocketCAN local loopback关闭，因此该被动抓包不能观察0x159 TX回显；驱动调用日志和3A7不变共同证明50mm请求已到ROS/SDK层但实体反馈未达到50mm。CAN RX三秒仍增长约7275、bus error=0。
- 依据实测实体可达端点45.9mm和方块实测宽度约24–30mm，把真实 YAML 的 `gripper_open_value` 从50000改为45000；保留3mm反馈门，仍经唯一 `piper_jog_adapter` 和供应商 `GripperCtrl`，不删除反馈判断。规范/实际配置 SHA 均为 `34398dbb55572cdec697805db97fdada2fbde3189b07d0d2c89b6f14c745a417`。
- 实际工作区 `colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 成功；部署一致性检查通过，`python3 -m pytest .../test_real_grasp_replay.py` 为 `8 passed`。本轮提交前尚未用45mm目标重新跑实体后半段，不能声称抓取完成。

### 下一步

- 提交本轮配置和回归断言后，重新执行同一默认特权一键脚本。验收顺序为 `GRASP_READY -> GRIPPER_OPEN_FEEDBACK_CONFIRMED -> TOP_DOWN_PREGRASP -> DESCENT -> GRIPPER_CLOSE_FEEDBACK_CONFIRMED -> LIFT -> RELEASE -> SAFE_RETREAT -> RESET_COMPLETE -> confirmed disable`；任一真实反馈失败立即保持使能并记录。
- 下一次实机复核前修正被动抓包启动参数：上一轮 `candump -L 'can0,159:7FF,3A7:7FF,2A8:7FF'` 日志只出现3A7，无法证明0x159；规范/运行脚本现改为 `candump -L can0` 全帧只读捕获（SHA一致0399c196b6ed60861d54bad439fa3937740cb360f5d4c3c2b0ce463bac7bd0fb），随后按ID解析。保持夹爪反馈门，不直接绕过适配器。

## 2026-10-10：恢复仓库后的当前断点复核

- 按固定启动顺序在 `/mnt/hgfs/ub` 复核，当前 `HEAD=b8f544d`；工作树已有用户未提交修改，范围包括真实抓取配置、相机支架参数、抓取反馈实现/测试以及供应商树的广泛文件变化。本轮未覆盖、未回滚这些修改。
- 规范脚本与实际 `/home/johnwick/start_brain_robot_cube_real.sh` SHA-256 均为 `e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`；规范与实际实体 YAML SHA-256 均为 `618f00df44b8094aa77ed29e9020b2f64568fd89824a2915bf296199dee31f72`。当前实际 YAML 的 `gripper_open_value=50000`，并保留 3 mm 反馈门；同时新增 `fresh_jaw_capture_required=true`。因此旧记录中“已切换 45000”不是当前生效状态，不能据此宣称张爪门已通过。
- 当前运行态没有 `piper_single_ctrl`、`piper_jog_adapter`、`visual_search_controller`、抓取执行器、MoveIt/Servo 或 Astra/cam2image 进程；未发送本轮运动或夹爪命令。旧日志仍显示最近一次实体链在 `GRASP_READY` 后因 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED` 停止，反馈约 45.9 mm。
- 本执行会话对 `can0` 的只读 netlink 查询返回 `Operation not permitted`；`sudo -n true` 返回1，原因是 no-new-privileges/ sudo 配置异常。故本轮没有 CAN RX 结论、没有接口配置、没有启动一键脚本，也没有重复 USB/CAN 恢复实验。磁盘根分区使用率约33%，不是当前阻断。
- 当前第一断点仍是实体抓取前的真实夹爪开口/间隙反馈门；其后才是闭爪反馈、抬升、释放、安全回位和确认支撑后失能。观测姿态、搜索、目标检测、镜像方向和离线预抓取规划已有证据，不应重复。
- 下一步首条命令：在具备 `CAP_NET_ADMIN` 的同一实际运行终端复核 `ip -details -statistics link show can0` 与 3–5 秒被动 RX；若持续反馈，再核对安装空间已加载当前 50 mm 配置和新鲜 RGB-D 夹爪间隙门，运行同一一键脚本并按门控记录；若权限或 RX 未恢复，保持不启动运动链并记录阻断。当前不执行 0xAE 零点写入、ResetPiper 或 MasterSlaveConfig。

### 2026-10-10：镜头实测外参与夹持区门控的离线验证完成

- 用户确认测量基准为镜头中心、沿相机光学方向：指尖向下约 `0.070 m`、向前约 `0.105 m`。当前规范和实际 YAML SHA-256 均为 `618f00df44b8094aa77ed29e9020b2f64568fd89824a2915bf296199dee31f72`，均加载 `translation_m=[-0.070,0,0.0308]`、`rotation_rpy_rad=[0,-pi/2,0]`、`operator_tip_optical_m=[0,0.070,0.105]`，并明确水平偏移未测、旋转未完成标定。
- 只读复核工具反算配置得到指尖 `[0,0.070,0.105] m`；按当前 640x400 深度内参投影为 `(u=326.14,v=519.04)`，落在图像下方。该结果确认不能把画面中心当作两指夹持中心，也不能据此直接增加实体下降量。
- 当前抓取代码在闭爪前要求 `fresh_jaw_capture_required=true`、新鲜 RGB-D 面点、最新夹爪反馈，并通过 `FaceInsideJawCapture` 几何门；门控失败只报告 `FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，不发闭爪、抬升或释放命令。50 mm 张爪目标与约46.2 mm静态反馈的差异仍保持拒绝，不写入0xAE零点。
- 实际工作区验证：`colcon build --symlink-install --packages-select brain_robot_pick_place brain_robot_ball_pick` 返回0；`colcon test --packages-select brain_robot_pick_place` 返回0，结果 `54 tests, 0 errors, 0 failures, 0 skipped`；离线外参和抓取回归 `15 passed`；`bash -n`启动脚本和相关文件 `git diff --check` 通过。未启动ROS控制栈，未发送六轴、夹爪或失能命令。
- 当前技术状态仍是待外部手眼/安装旋转和水平偏移验证，以及真实夹爪开合反馈验证；模型、离线测试和部署一致性不能替代实体抓取验收。下一步先取得静止同帧指尖/方块对应点或完整手眼标定，再重新离线规划预抓取/下降；在此之前保持真机运动禁用。

### 2026-10-10：实机完整链验证到 GRASP_READY，张爪反馈门阻断

- 按用户授权运行 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_OBSERVE=0 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 /home/johnwick/start_brain_robot_cube_real.sh`。运行前 USB-CAN `1d50:606f`/`gs_usb` 正常，`can0` 为 1 Mbps、sample-point 0.750、ERROR-ACTIVE；被动4秒 RX 增量9747，`0x251..0x256` 各400帧；无控制进程残留，磁盘33%。
- 一键链实际通过 `[1/7]..[7/7]`、深度/RGB首帧、观测姿态和搜索；视觉控制器进入 `GRASP_READY`，检测器使用当前 `mirror_x=false`。没有执行预抓取下降，因为抓取执行器先执行张爪反馈门。
- 适配器发出有界 `target=0.050000 m, effort=1.000 N.m` 张爪帧；驱动日志反复记录 `GripperCtrl(50000,1000,0x01,0)`。只收 CAN 日志中 `0x3A7` 共64713帧，角度始终 `0xB478=46200`（46.2 mm），未观察到 `0x159` 回显（SocketCAN local loopback关闭，不能据此否定SDK发送）。最终错误为 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED before=current=0.046200 m target=0.050000 m tolerance=0.003000 m`。
- 保护路径返回码为1，未发送预抓取、闭爪、抬升、释放、ResetPiper、0xAE或DisableArm；脚本停止其进程并保持硬件使能。结束后 `can0` 仍 ERROR-ACTIVE，3秒 RX 增量7278，错误/丢帧为0。
- 视觉日志还出现重复 `Joint 'gripper' not found in model 'piper'`，需后续单独修正模型/日志噪声；本轮没有把它当作张爪反馈成功或绕过门控的理由。
- 当前阻断是实体夹爪的开口基准/反馈未验证：46.2 mm 是持续反馈值，不等于已证明50 mm完全张开。下一步必须取得实体完全张开基准或明确的夹爪标定证据，并保持新鲜 RGB-D 夹持区门；在此之前不把 `gripper_open_value` 改成46.2、不放宽容差、不继续下降或闭爪。

### 2026-10-10：用户确认 46.2 mm 不是实体完全张开位置

- 用户明确确认：本轮 `0x3A7` 持续反馈的 `46.2 mm` 不是夹爪机械上的完全张开位置。
- 因此本轮 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED` 的阻断成立；不得把 `gripper_open_value` 改为46200、不得放宽3 mm容差、不得删除真实反馈门，也不得继续预抓取/闭爪来“试一下”。
- 未知实体开口基准时禁止写入0xAE；保持当前硬件使能/静止状态。下一步必须先由现场完成夹爪完全张开基准确认（或取得可靠标定证据），然后再用同一反馈门和新鲜RGB-D夹持区门重跑完整链路。

### 2026-10-10：复用用户 V2 demo 的 0x03 首帧清错夹爪路径

- 只读核对 `/mnt/hgfs/ub/brain_robot_arm/piper_demo_V2/auto_sequence_speed50.py`：张爪明确使用 `GripperCtrl(50000,1000,0x03,0)`，随后用 `GripperCtrl(40000,200,0x03,0)` 闭合；SDK 文档定义 `0x03` 为“使能并清除夹爪错误”。该 demo 的其余六轴动作未执行。
- 当前 ROS 驱动在使能时仅做 `0x02 -> 0x01`，显式目标帧始终 `0x01`；本轮最小修复为每次成功使能后的第一条明确夹爪目标使用 `0x03`，随后目标使用 `0x01`，不改变目标值、反馈门、闭爪门或六轴控制。
- 规范 vendor 驱动与实际 `/home/johnwick/piper_ros` 源 SHA 已同步为 `fe1e954032f...`；`piper` 构建返回0，实际 `piper_ws` 的 `brain_robot_pick_place`/`brain_robot_ball_pick` 构建返回0。尚未用该补丁重跑实体抓取。
- 前一轮仅 SDK 直连发送 `0x03` 未先成功完成完整 demo 使能，SDK 聚合读数为零，不能作为有效实体反馈；本轮不据此宣称夹爪已动作。下一步用重新部署的 ROS 驱动运行同一一键链，验收首帧日志是否为 `code=0x03`、0x3A7 开口是否变化，以及张爪反馈门是否通过。

### 2026-10-10：demo 首次0x03目标的实体复跑结果

- 提交31657fb部署后，完整一键链再次通过观测姿态、搜索、ALIGN和GRASP_READY；驱动首条实际日志为 `GripperCtrl angle=50000 effort=1000 code=0x03 set_zero=0x00`（1791619158.504），后续目标帧为0x01。真实张爪反馈仍 `before=current=0.046200 m target=0.050000 m tolerance=0.003000 m`，停止在 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED`。没有预抓取、闭爪、抬升、释放或失能。
- 首次0x03路径已实机验证进入SDK调用层，但没有证据证明其解除夹爪阻断；不把SDK调用等同于实体动作，不重复此运行。日志 `/home/johnwick/brain_robot_logs/real_verify_20261010_0x03.log`、`piper_driver.log`、`visual_stack.log`、`gripper_can.log`。
- 纠正此前独立SDK测试解释：本固件聚合帧在0x3A0..0x3A7，而SDK默认接收2A1..2A8；没有安装ROS驱动的接收映射时读出的零值是未更新缓存，不能解释为未使能或夹爪已闭合。测试曾调用EnablePiper，但没有六轴目标、闭爪、零点或失能命令。
- 驱动初始化补齐 `_gripper_clear_pending=True`，避免非服务使能入口首次目标访问未初始化属性；规范与实际源同步，Python语法检查通过。本次实体路径经使能服务已设置该字段，不改变上述结果。
- 下一步必须用正确接收映射与新鲜反馈，在保持六轴静止的诊断中核对demo的单次0x03保持方式和实际发送结果；demo第二参数200是力矩0.2 N·m而非速度，40000是40 mm而非物理“20%闭合”。没有证据支持写零点或将46.2mm当开口端点。总目标仍未完成。

### 2026-10-10：官方接口与相机实帧联合复核

- 按仓库固定启动顺序重新确认当前断点为 `ebbe788`：上一轮完整实体链通过 `[1/7]..[7/7]`、观测、搜索、ALIGN、`GRASP_READY`，随后因 `FAULT_OPEN_GRIPPER_FEEDBACK_UNCONFIRMED` 停止；`0x03` 首个显式目标帧已实机发送到 SDK 层，但 `0x3A7` 仍固定约 `46200=46.2 mm`，因此不重复该实验，也不绕过开口反馈门。
- 对照 AgileX 官方 V2 接口文档与官方夹爪示例：`GripperCtrl` 角度单位为 `0.001 mm`，`0x01` 为使能，`0x03` 为使能并清错；官方示例的正常目标帧仍使用 `0x01`。这与本仓库已经部署并验证的“首帧0x03、后续0x01”路径一致，不能解释实体反馈不动。资料：[接口定义](https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD)、[官方夹爪示例](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_ctrl_gripper.py)。
- 检查现有 RGB 实帧 `/tmp/piper_current_rgb.png`、`/tmp/piper_current_debug.png` 及序列帧：调试叠加给出 `PURPLE_CUBE dx=-45 dy=-101`、深度约 `0.208 m`、尺寸约 `0.042x0.040 m`；方块在画面左上，画面中心明显位于其右下，未形成“方块已处于两指之间”的证据。序列帧中两侧夹爪/支架结构位于下边缘，不能从单帧可靠测出指尖三维位置。
- 本轮未启动 ROS、未发送六轴/夹爪/失能命令，未修改实体参数。下一步需要现场侧面图和正面图（同时看清镜头中心、支架、两指尖端，机械臂保持当前位置即可）或同帧指尖标记，才能把已知的“镜头中心向下约70 mm、向前约105 mm”与实际指尖/方块夹持区闭合；在此之前保持下降、闭爪和抬升门控。

### 2026-10-10：核对仓库中的 PiPER V1.1.0 用户手册

- 读取仓库根目录 `PiPER机械臂用户手册V1.1.0.pdf`（57页）并查看第10、15、16页图示。手册 DH 参数给出 `d1=0.123 m、a2=0.28503 m、d3=0.02198 m、d4=0.25075 m、d6=0.091 m`；零位示意给出末端坐标 `X=54.952 mm、Y=0、Z=203.386 mm、RX=0°、RY=85°、RZ=0°`。图示确认 J6 位于末端旋转轴，夹爪安装在 J6 末端。
- 手册夹爪规格写明开合间距 `0–70 mm`、额定夹合力40 N、最大夹合力50 N。该规格是产品量程，不能推翻本机当前 `0x3A7=46.2 mm` 的实体反馈，也不能证明本机当前状态为完全张开。
- 对照当前 URDF：`joint6` 原点含 `y=-0.091 m`，与手册 `d6=91 mm` 一致；`joint7` 使用 `xyz="0 0 0.1358"`，当前配置的 `gripper_tip_offset_m=0.1358` 是模型链路偏移。用户实测的镜头到指尖“向下70 mm、向前105 mm”属于相机支架外参，不能用手册的 `d6` 或 URDF `0.1358 m` 直接替换。
- 本轮只读解析手册和 URDF，没有启动 ROS、没有发送机械臂/夹爪命令。下一步仍需侧面/正面实物图或同帧指尖标记，完成相机光学坐标到 J6/指尖的旋转与水平偏移验证，再考虑重新规划抓取。

### 2026-10-10：当前资料需求与后续执行规划

- 当前不缺 PiPER 产品手册或 SDK 语义资料；主要缺口是实体相机安装几何和夹爪开口基准。现有证据足以继续离线分析，但不足以安全授权新的下降/闭爪。
- 需要现场提供：①相机与夹爪的侧面照片；②相机正对夹爪的照片；照片中同时可见镜头中心、支架固定面、J6/夹爪基座、两指尖端，机械臂保持当前姿态即可；③若可行，在不移动机械臂的情况下标出镜头中心到两指尖的水平/垂直方向。另需确认 `46.2 mm` 反馈对应的实际夹爪状态，以及完全张开时的反馈读数；不要求执行未知零点写入。
- 规划分五步：先用照片/标记建立相机光学坐标到J6和指尖的旋转、水平偏移；再用静态RGB-D帧和URDF/FK离线复核方块三维点是否落在两指之间；然后做只读部署一致性、反馈新鲜度和夹爪开口基准检查；只有开口门、夹持区门和预抓取轨迹全部通过，才在用户确认现场安全后运行一次有界实体链；最后验收闭爪反馈、抬升、释放和安全回位。任一步失败均保持使能并停止，不通过修改阈值绕过。

### 2026-10-10：接受用户确认的准确指尖尺寸和两张实体照片

- 用户再次明确确认：从镜头中心、沿相机朝向测量的指尖向下70 mm、向前105 mm是准确数据。本轮接受该测量，不再要求重复测量这两个分量；保留数值 `[Y=0.070,Z=0.105] m`。水平分量与完整旋转不因该确认自动成为已标定数据。
- 用户提供两张实体安装照片：可见相机固定于夹爪上方的支架、两侧较长指爪及橡胶接触面；侧面图提供相机/夹爪安装关系的定性证据。照片有透视且无标尺，不能据此计算精确开口、水平偏移或旋转，也不能认定指爪是改装件。照片随本轮聊天提供，尚未存入规范仓库。
- 源码只读跟踪确认：launch 从实体YAML加载相机平移/旋转，发布 gripper_base -> camera_link TF；FreshFaceInsideJaws 将新鲜相机面点通过TF变换至 gripper_base，再检查夹持区。测量不是仅作说明字段：它已用于当前相机TF平移的推导。但该推导还依赖当前旋转和模型 `gripper_tip_offset_m=0.1358`，两张照片不能独立验证这些假设。
- 本轮未推进新的观测姿态运动：该阶段已有完整实机通过证据，当前断点仍在张爪反馈门；重复运行不会消除几何假设或固定46.2 mm反馈。未启动控制栈、未发送运动/夹爪命令、未更改参数。
- 下一步针对照片中的实际指爪核对模型指尖位置和碰撞几何，并区分“已确认镜头到指尖YZ”与“未验证J6到实际指尖偏移/安装旋转”；并行继续只读检查demo/ROS夹爪发送差异，不重复首帧0x03整链实验。不能因收到照片将 rotation_calibrated 或 horizontal_offset_measured 设为true。

### 2026-10-10：修复夹爪非关节入口跳过首次清错

- 代码审查发现 `enable_flag` 入口完成 `0x02 -> 0x01` 后没有重新置 `_gripper_clear_pending`，笛卡尔 `PosCmd` 入口则始终发送 `0x01`。这使得这些入口与用户 V2 demo 的首次 `0x03` 语义不一致，可能保留夹爪错误状态。
- 已修复规范 vendor 驱动：使能成功后置位首次清错状态；`PosCmd` 的首次显式夹爪目标使用 `0x03`，后续使用 `0x01`。关节轨迹入口原有首帧0x03路径保持不变；不改变角度、力矩、反馈门或零点命令。
- 规范源已部署到实际 `/home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py`，两份文件SHA一致；`colcon build --symlink-install --packages-select piper` 返回0。`test_command_validation.py` 更新后 `6 passed`，Python AST解析和 `git diff --check` 通过。
- 本轮没有启动ROS或发送实体命令；未验证硬件反馈是否改变。下一步必须在有实时CAN权限的会话做一次静止、夹爪专用有界验证，再决定是否进入完整视觉抓取；禁止重复整套运动作为代码修复证明。

### 2026-10-10：按用户要求收敛为最基本夹爪验证

- 用户要求先实现最基本抓取，不继续堆叠复杂门控；本轮确认不引入“最小开口阈值”等新参数，也不把 `46.2 mm` 未验证状态改写成最大开口。
- 基础验证方案收敛为一次最大张开命令 `GripperCtrl(50000,1000,0x03/0x01)`，只读取新鲜 `0x3A7` 反馈：反馈变化则证明夹爪响应，仍固定 `46.2 mm` 则证明实体状态未改变，不能假称已最大张开。随后才考虑闭爪和抓取。
- 本执行会话当前无 `can0` 管理权限，未发送实体命令；未修改控制代码。此前未落盘的最小阈值尝试不计入实现。

### 2026-10-10：长期接力规则、用户要求和实体证据归档

- 用户要求作为本任务长期执行规则归档：以 `/mnt/hgfs/ub` 唯一规范仓库和最新任务/交接/进度/决策文档为准；每轮先检查实际状态，再做最小可验证动作，更新文档、提交Git并报告提交、验证、阻断和下一步；不得重复已完成或已证明无效的实验。
- 用户要求持续查看相机原始RGB、深度、调试叠加和机械臂真实视野，结合仓库资料、官方GitHub资料、用户手册和实体照片分析；不得只凭仿真或聊天上下文判断抓取。已归档的实帧证据包括紫色方块偏差约`dx=-45,dy=-101`、深度约`0.208 m`、尺寸约`0.042x0.040 m`；已归档两张相机/夹爪实物照片。
- 用户确认实体测量：从镜头中心、沿相机朝向，夹爪尖端向下约`0.070 m`、向前约`0.105 m`；该数值准确并已加载到相机TF配置。用户提供的PiPER V1.1.0手册已核对DH/J6/夹爪规格。
- 用户要求代理自己查找资料、自己获取`can0`管理权限并直接验证实体，而不是假设用户终端与代理终端相同。当前特权复核成功：`can0 UP/ERROR-ACTIVE`、1Mbps、sample-point 0.750、无bus error/drop，能持续收到`0x3A0..0x3A7`与`0x251..0x256`反馈；代理仍需每次记录实际命令和结果，不把权限存在等同于抓取完成。
- 最小夹爪诊断实际通过SDK调用 `GripperCtrl(50000,1000,0x03,0)` 并正常返回连接/发送日志；本次伴随过滤抓包因接口监听进程报`SIOCGIFINDEX: No such device`未取得该次命令对应的0x3A7时间序列，因此不宣称夹爪反馈改变。随后只读复核`can0`仍UP/ERROR-ACTIVE、RX持续、错误/丢帧为0。
- 当前总目标仍未完成：基础视觉链已有到`GRASP_READY`证据，实体抓取仍需在有完整CAN时间序列和夹爪实际反馈后才能继续。后续继续遵守“多看真实画面、查资料、最小动作、文档提交”的规则。

### 2026-10-10：完整实机运行的新阻断与驱动修复

- 按用户要求部署了“张爪反馈未确认仍继续预抓取”的基础抓取路径并启动完整实体脚本。实际链通过 `[1/7]..[7/7]`，随后驱动在使能服务读取异常夹爪缓存时抛出 `ValueError: Gripper hold feedback outside 0..80000`，`piper_single_ctrl` 崩溃，适配器进入 `PIPER_ADAPTER_DISARMED`；机械臂没有进入对齐/预抓取/下降，不能把本轮称为抓取尝试成功。
- 已修复驱动：异常的启动夹爪缓存不再使节点崩溃，记录警告并仅以0作为使能握手占位；后续真实夹爪目标和闭爪反馈仍通过现有链路验证。规范源已部署到 `/home/johnwick/piper_ros`，`piper` 构建返回0。
- 本轮新配置和驱动修复尚未再次实体复跑；下一步重新执行同一流程，验收必须出现 `ALIGN -> TOP_DOWN_PREGRASP -> DESCENT -> GRIPPER_CLOSE -> LIFT`，否则记录实际新阻断。


### 2026-10-10 18:17–18:24：核对唯一入口、执行完整实机测试并按用户要求暂停交接

- 起始HEAD `4db88e3`，规范根 `/mnt/hgfs/ub`；依次核对Git状态/log/reflog/HEAD及四份持久文档。撤回上轮未部署的 `top_down_grasp_enabled=false` 试改后，规范/运行源码/install实体YAML SHA一致为 `6bd95d17828279b842e4404118d1137112b01504b686ca3fdaa673fe784c7460`。执行器/launch/驱动源亦逐项SHA一致，安装执行器有允许张爪未确认继续接近分支。其余既有工作树修改未动。
- 历史 `/tmp/piper_real_run_20261010_settled_fix.log` 的76点预抓取、9点下降和闭爪反馈46.2 mm失败仍是有效证据；本轮测试是更新相机外参后的实际部署版本，不以本轮规划失败抹去历史靠近证据。
- 实机前被动高速反馈100 Hz、六轴使能true、速度0；SDK正确接收映射测得起点 `[-.296060,.978658,-.749008,0,.751312,0] rad`，观测目标 `[0,.98,-.75,0,.30,0] rad`。沿用已验证物理/软件限位，适配器速度上限.189 rad/s、准备速度/加速度缩放.01、搜索.05；失败停止输出且保持使能。can0 1Mbps/.750 ERROR-ACTIVE、零错误/丢帧，磁盘33%。夹爪即时反馈102.1 mm与历史46.2 mm不同，不称作已完全张开。
- 实际命令 `BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/onekey_test_20261010 /home/johnwick/start_brain_robot_cube_real.sh`，一键输出 `/tmp/piper_onekey_test_20261010.log`。唯一额外日志目录变量不改变任务行为。脚本磁盘维护前后33%，[1/7]..[7/7]通过、RGB/深度真实首帧和TF门通过。
- 实机18:19:48.919接受7点/22.5秒观测轨迹；18:20:11.043 SEARCH(OBSERVE_POSE_REACHED)；18:20:42.543 ALIGN；18:20:44.494 GRASP_READY；18:20:49.516张爪未确认仍进入TOP_DOWN_PREGRASP_PLANNING。当前锁定模型目标约 `[.432,-.127,.081] m`；24个预置tilt/yaw全部IK -31(NO_IK_SOLUTION)，18:21:13.698 FAULT_TOP_DOWN_PREGRASP_PLAN_FAILED。没有预抓取/下降轨迹、闭爪、抬升或释放，工具实测退出1；不归因于张爪提前门控。
- 原始RGB与debug已多次实际查看；对齐后0036帧约dx9/dy-4、深度303 mm、尺寸36×40 mm。状态和图像证据 `/tmp/piper_onekey_test_20261010_observer.jsonl`、`/tmp/piper_onekey_test_20261010_images/`；节点/CAN日志独立保留在上述LOG_DIR。首次只读采集器因终端NumPy冲突退出，改为PYTHONNOUSERSITE=1系统Python后有效采图，不影响控制脚本。退出后重复保存最后帧属于旧stamp，不能当新鲜图像。
- 驱动存活并记录忽略启动异常夹爪缓存102100；实际50mm目标首帧0x03后续0x01。139.3秒CAN记录0x3A7共27590帧均102100，各高速轴约13793帧；无0x159回显不证明未发送，SDK关闭local_loopback。当前102.1 mm开口语义/基准仍未确认，不写0xAE、不假称夹爪已修复。
- 一次无运动数值几何核对 `/tmp/piper_onekey_geometry_review_20261010.{py,jsonl}`：安装URDF和当前六轴边界，24预置顶抓候选每个4种子均未找到<1mm/<.01rad解；有限数值搜索不能证明绝对不可达。实测末端朝向有模型内预抓取解 `[-.289806,1.690820,-1.002264,.024986,.282857,-.032500] rad`，尚未经MoveIt碰撞、下降/夹入和实体验证，未部署或发送。下一步建议只在禁止执行的ROS域78做同快照姿态对照，不重复当前原样实机失败。
- 用户要求暂停交给此前参与项目的老师傅；停止一切后续实机动作并结束只读采集器。18:23:39正确按0x3A4..0x3A6聚合帧核实实际关节 `[-.278956,.979583,-.749008,0,.741241,0] rad`，高速速度全0、六轴使能全true、夹爪.1021m，连续RX。早先手算输出误用3A1..3A3末端pose帧，已纠正，不作为关节证据。实际进程检查无本轮控制栈残留。没有ResetPiper、DisableArm、自动回位或零点命令。
- 完整暂停交接文件 `docs/PIper_HANDOFF_20261010.md`，CODEX_HANDOFF顶部指向当前状态。接手第一条命令 `cd /mnt/hgfs/ub && git status --short`。暂停后不得自动续跑，需用户/接手者明确恢复执行。总目标未完成，当前新版阻断为预置抓取姿态IK，夹爪异常反馈独立待核实；本轮只提交记录，未提交新控制策略。

- 为避免/tmp重启丢失全部直接证据，已将小型一键输出、离线诊断源码及结果保存到 `docs/evidence/piper_onekey_20261010/` 随本轮Git提交；原始CAN/节点大日志和相机序列没有加入Git。
