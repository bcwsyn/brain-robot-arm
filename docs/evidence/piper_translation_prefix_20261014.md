# 2026-10-14 原转向配较短平移候选

## 授权与实际基线

用户对上一轮具体提案“保持原1°转向、增加50%/25%平移完整候选，执行停稳后新RGB/反馈重规划，不改最终抓取点或限位”回答“同意”。此新授权覆盖上一轮待同意，不重新问。完整抓取目标未完成。

基线82dfc67/应用c0f56da；host无实体/隔离/采集栈。唯一原入口SHA87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0；actual executor cf5777e11d2ea2e685d610e5bcebf1a5eb2e14ba53caab322cd56c5cb94d3c16。用户既有wiring注释/vendor/reference保持，远端分叉及历史审查未完成，仅本地提交。

## 最小实施与不变量

只改原grasp_lift_executor.cpp及实际方法测试，复用上一轮精确step49隔离证据，不重复CAN/固件/单点原实验：

- 原完整请求、全部缩角/反向候选均无法完整通过后，才按50%/25%依次尝试。
- 保留原请求的有界朝向、frame及stamp，只沿“当前真实FK指尖→原请求指尖”缩短平移；不是对手腕xyz简单乘半，不改变全局nominal/frozen目标或最终落点。
- 新候选也必须完整Cartesian规划、原RealTrajectoryWithinLimits、原8mm/1°/.08rad已检查前缀、输出前真实反馈和原实际到位/停稳。不能执行fraction<1规划。
- 仅自动实体且深度目标已冻结、近距RGB跟踪开启、非粗靠近时适用；预览/搜索/普通规划不改。
- 平移缩短不表示改变朝向，不设置已选朝向替代标志；下一循环继续原nominal目标，新RGB/真实反馈重规划，不借新策略无条件跳点。原c0f56da朝向候选到位推进机制、原有限预算、视野恢复、原最终中心/两指夹持/闭爪保持。
- 新日志REACHABLE_VISUAL_TRANSLATION标记比例和完整规划成功；50%/25%候选的原始POSE_REQUEST也记录，便于复现。

3项新增实际方法测试：非平凡1°朝向下tip半/四分之一位移而朝向/消息头不变；零/负/扩大/NaN比例及坏姿态拒绝；只有冻结自动末段允许。controller-free域78，未调用实体命令。

## 命令与待验证

首五Git和实际SHA/host状态通过；根盘93%/5.9GB，仅运行原clean_disk_space.sh，不额外删除日志/源码/构建。复用cmake --build /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place --target grasp_lift_executor near_depth_executor_test -j2，输出translation_prefix_build.txt，单次构建session73381，不重复并发构建。

下一读构建结果→原完整46方法及10RGB回归→限定Git→备份实际c0f56da→同步单executor/SHA→新鲜反馈清单→唯一原AUTO1实测；日志translation_prefix_*。成功验收必须是实体靠近/两指夹持/闭爪抬升等实际状态，不以软件或规划代替。实体失败则原hold停止、不Disable/Reset/自动回零，按新最早阻断定位。

## 构建/回归与新鲜反馈

- 单次构建rc0，实际方法46项（43旧+3新）rc0/3.275s、原RGB几何10项rc0；日志translation_prefix_{build,executor_tests,visual_tests}.txt。没有实体控制。限定文件diff --check通过。
- 候选d4c7063d4d0ff8c1ea5b4c528264242eb8a011deeeb882ea25fb09515a5c03f7；canonical CPP19d4b4e04d295b4cd89ec53024f34b66c88b70d9ff9b467e4c50464085f209ed。尚待备份/部署，不将构建当实体成功。
- clean_disk_space.sh rc0，93%/5.9GB→92%/6.1GB；只清理脚本规定ROS日志/缓存/受限系统轮转，删除的日志不可依赖恢复，未额外删除；本轮/上轮证据目录保留。无ENOSPC。
- 新接收SDK rc0 epoch1791942898.113170/high2898.105217/100Hz、joint2898.109516，六使能true/速度全0，q[-.337808477,1.849734848,-1.392912369,.049933870,.909822686,-.101857415]rad，夹爪99.6mm使能无错误。原SDK实际用户安装路径、ConnectPort(piper_init=false)，未发初始化/运动。
- 实测清单复用原task：[0,.98,-.75,0,.30,0]rad观测目标，当前保持→观测可涉及六轴；prepare速度/加速度1%、预计约43s（由原反馈生成实际轨迹计），适配器最大.189rad/s；原任务min[-1.5,-.3,-1.4,-.8,-1.2,-pi]/max[1.5,pi,.4,.8,1.2,pi]，原物理速度/加速度300/500单位.001rad/s及.001rad/s²不变；末段8mm/1°/.08rad前缀保持。原异常停止新输出/保持使能，成功释放且安全回位支撑后才失能，禁止Reset/未回位Disable。回退点为即将备份c0f56da，不自动回滚或重复启动。

## 已部署，原AUTO1正在执行

修复d051bf5。actual source19d4b4e…/binary d4c7063…与构建一致，install链接build；原入口87039b…/detector8e763f4…未改。旧actual c0f56da/cf5777e…及source0043c923…机械备份translation_prefix_previous_c0f56da，未覆盖用户其他文件。

命令BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=.../translation_prefix_onekey timeout -s INT -k8s600s /home/johnwick/start_brain_robot_cube_real.sh，session46839/host timeout3862130/script3862131。只读capture_scale_frames.py→translation_prefix_exact python3862224/session1463，observer→translation_prefix_live python3862292/session41193，590sINT/-k3s。启动维护92%/6127MB，原CAN复用RX增长/不重载，RGB/深度首帧已到，当前5/7反馈/TF核对；未冒称观测/新前缀已执行。下一读同一次进程/日志/三图，不重复启动。

本地提交d051bf5，未同步GitHub：既有远端分叉/全历史推送审查未完保持。用户原wiring/vendor/reference不纳入。完整目标未完成。

## 实测结果：观测途中USB数据面停止，本次未运行新末段

- 原AUTO1到7/7，1791943090.014 PREPARE/12点adapter接受；约26s后运行期CAN守护中止。未OBSERVE_POSE_REACHED/SEARCH/ALIGN/GRASP_READY，REACHABLE_VISUAL_TRANSLATION与闭爪均0。本次不称新前缀实体通过；应用和回归已完成，实体验证尚欠。
- can_health.log记录2026-10-14 09:58:30 CAN_RX_STALLED_3S；同刻dmesg为xhci_hcd 0000:03:00.0 Transfer event TRB DMA ptr not part of current TD ep_index2（后续持续多秒）。这是本次新的USB数据面证据，不是复用历史错误或证明PiPER固件/实体机械错误；USB具体端点原因仍未唯一定位。
- 主session46839返回143；与上一轮wrapper143但真实主仍活不同，本次host确认timeout3862130/script3862131均不存在，原console完成cleanup。日志STOPPED(USER_STOP)为脚本原stop收尾，不当用户触碰/手动急停证据；adapter2点保持请求不等于有新反馈确认到位。原日志“未发送DisableArm”，未Reset/回零/额外机械命令。
- 当前can0 UP/ERROR-ACTIVE/1Mbps/.75/queue1000，但两次相隔1s RX124744968→124744968，TX136058不变/errors/drop0；随后仍同计数。USB1d50:606f在（guest lsusb003/018），sudo-n true rc0。0 RX增长不是sudo问题/缺权限，也不能把ERROR-ACTIVE当数据链已恢复。
- 新SDK接收脚本rc0 epoch1791943183.928513，但joint/high stamp0、Hz0，六q0和enablefalse为无反馈默认值，不代表机械臂归零或实际失能。本次当前真实位置/使能不能重新确认，禁止据此运动或声称静止使能已验证。
- 最后有stamp的采集反馈1791943106.715414：q[-.268061948,1.670297888,-1.260991872,.038498908,.781351648,-.078009568]rad/夹爪99.6mm，仅停滞前最后记录，不是现在新反馈。最近RGB1791943120390803212已看，灯光/完整紫色方块在左下可见；collector最后墙钟3204的snapshot重复上述旧消息不当新画面/新反馈。
- 两准确只读collector3862224/3862292 INT后session1463/41193各rc0；host无主控制/相机/采集/隔离栈。未原样重跑、未发送运动或自动掉电。
- 根盘初93%/5.9GB，清理rc0到92%/6.1GB，原脚本维护6127MB，结束93%/5.9GB；无ENOSPC，不将用户曾提磁盘问题当本次USB错误已证实根因。

## 恢复范围与下一步

已核对仓库历史：RX停滞后guest USB reset/gs_usb/xHCI重建/Hub power cycle已多次无效；docs/PIper_DECISIONS记录RX=0时接口配置正确保持不变、禁止反复bounce，历史有效动作在宿主VMware断开/重新连接USB-CAN。虽然sudo0/本任务授权允许受限恢复，但不再重复已证明无效实验或重置共享xHCI影响相机。未执行USB reset、gs_usb重绑、xHCI重建或CAN down/up；此前 commentary“尝试受限恢复”经历史核对后收窄为需要宿主侧重连。代理本会话只有guest终端，无宿主VMware控制入口，不能代操作该外部动作。

下一先在VMware可移动设备中仅断开/重新连接1d50:606f USB-CAN到此VM；不要求重启机械臂，不刷固件/主从/Reset。恢复后首命令ip -statistics link show can0并短差分，仅接口DOWN/配置不对且sudo0时固定1Mbps/.75/queue1000/up；连续RX+新鲜六轴反馈恢复后直接同原AUTO1验证d051bf5新末段，不重复模型/构建/历史CAN基线。当前完整实体目标未完成；新的实测阻断是USB反馈恢复，不是已解决的应用修改许可。

Git仅本地、未同步GitHub（远端分叉/历史审查未完）。下一接力第一命令cd /mnt/hgfs/ub后git status --short，再读取本条，不把旧“进行中”或SDK零默认当当前状态。

## 用户恢复后接续：新接口一次配置，原AUTO1实测中

用户“已恢复”；首五Git/技能/最新四文档/实际路径核对，HEAD153dc64/actual d051bf5 d4c7063…/原入口87039b…不变，host无旧栈，不修改代码或重复构建。新can0 ifindex10初DOWN、qlen10、RX0（已重新枚举，与旧接口9停滞不同）。sudo-n true0后仅固定type can bitrate1000000 sample-point.75/txqueuelen1000/up一次，rc0；ERROR-ACTIVE/RX51→2391（一秒）、errors/drop0。未USB reset/gs_usb/xHCI重建或bounce已正常链路。

接收SDK rc0 epoch1791943653.360637/high3653.355583/100Hz、joint3653.354604；q[.055257124,-.002024582,0,-.156835287,.259844619,-.075886916]rad，速度0、六enablefalse，gripper99.6mm/enablefalse无错误。这次有真实新stamp，false是当前实际反馈，不是上轮stamp0的默认值；不推断谁使其失能/用户操作细节。原脚本按既有使能流程开始，不发Reset/复位/校准。

动作清单保持原观测目标[0,.98,-.75,0,.30,0]rad，可动六轴；prepare速度/加速度1%，由实际反馈生成持续时间（近零起点预计20s附近，实际轨迹计）；原adapter最大.189rad/s/物理300及500单位.001rad/s、.001rad/s²/任务min[-1.5,-.3,-1.4,-.8,-1.2,-pi] max[1.5,pi,.4,.8,1.2,pi]不变，末段8mm/1°/.08rad和原中心夹持保持。异常停新输出/保持使能、不未回位掉电；原成功释放/安全回位支撑后才失能。回退备份c0f56da保持，不自动回退。

根93%/5.9GB，只原clean_disk_space.sh rc0仍93%，原启动维护5987MB，无ENOSPC/额外删除。此前按该脚本清理的ROS日志/缓存不可依赖恢复，源码/构建/本轮证据保留。

唯一命令BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=.../translation_recovered_onekey timeout -s INT -k8s600s /home/johnwick/start_brain_robot_cube_real.sh，session71442/timeout3864221。只读exact python3864362/session83540、observer python3864457/session33328，目录translation_recovered_exact/live，590sINT/-k3s。下一读同一次日志/原RGB/深度/debug/状态，验证d051bf5实际平移候选和继续靠近，不能将恢复或7/7冒称抓取成功。

## 恢复后实测结果与用户“为什么不再下降、原对齐位置丢失”的诊断

**实际事实：**同原AUTO1 script3864222、主session71442 rc1，非600s外界中止。PREPARE3786.530/14点→SEARCH3835.507/OBSERVE_POSE_REACHED（实48.978s）→ALIGN3853.142→GRASP_READY3855.729。11粗段后3872.545质量冻结最后可靠图1791943871209926638/range.228190m/world[.419895003,-.116088673,.068534385]m/size.037405；当前图3872410036938质量0/样本0，成功继续原RGB同步靠近，组合37路点/原75循环预算。

23路点step48选-.75/3911.982推进；24路点step50选-1/3913.108推进。step52、53均原完整规划/实际输出到位停稳，step53原路径5点/相邻最大.013652rad，3915.529收到MEASURED_SETTLING_CONFIRMED。49总adapter accepted（含准备/搜索/对齐/收尾），29末段命令尝试，observer39真实feedback-confirmed事件；不将投递数量等同总轨迹。REACHABLE_VISUAL_TRANSLATION为0：原计划本轮成功，新平移候选没有触发，不能称新策略实体通过或无效。

最终3919.452 FAULT_AUTOMATIC_RGB_CAPTURE_UNCONFIRMED_NO_CLOSE，最后推进仍25/37，未下降段/闭爪/抬升/释放，JAW_CAPTURE/GRIPPER_CLOSE_REQUESTED为0，cursor短路先于最终中心判定。此前commentary将尾部停止称“下一段规划失败”不准确：经全日志/observer核对本次step53已完整执行，现更正为视野恢复不收敛/预算耗尽，不继续套上一轮step49全规划失败结论。

**同帧视觉和模型趋势（非外部TCP标定）：**复用review_jaw_scene.py::poses与已归档实际URDF，输入最近真实feedback（不是精确image-time q），采用当前tip_offset.1358；详细匹配stamp/误差在translation_recovered_pose_pixel_review.txt，rc0。GRASP_READY最近图3855809927399（差+.080s）原RGB框中心(.445313,.418750)，模型tip Z=.188740m；step30图3889410209416（差+.040s）中心(.364063,.725000)、Z=.096312m；停止图3924611050612中心(.337500,.881250)、Z=.097632m。step48 Z=.097985m，after53 Z=.097757m，后段高度停在约96–98mm基座模型坐标，不冒称桌面距高已标定。先实下降后不再下降的用户现象与记录吻合。

末段RGB已看：完整/近底边紫色方块仍在原RGB，最后bbox[.265625,.770833,.409375,.991667]，bottom>.98越过原FullView边距；debug深度无有效样本，不等于真实RGB目标消失。初期200mm图与native配对3882606449314（RGB3882611928468，约5.48ms）和debug均保存/核看；末段深度缺失不覆盖冻结模型、不误当当前CAN故障。

**代码明确事实：**原HandleAlignLocked用检测器pixel_error/normalized ratio<=.05、align_stable_frames=1判断；当前software_registration检测器把RGB形心/深度投影成depth像素与debug中心之差，不是原彩色画面中真实两指夹持参考。原ALIGN通过因此不能冒称实际两指射线已对准，也没有持续原RGB中心保持承诺。

AutomaticRgbApproach接手后按冻结三维模型的同步位置/朝向路点，加原RGB模型投影残差；GuardApproachView只把预测目标推到防出画边距，不锁定原对齐像素(.5,.5)或两指实际夹持位置，并固定模型tip解转向。FullView失败/恢复时nominal=current，若AimCameraAtFixedTip返回RAY_INFEASIBLE则未改变姿态；原Reached(current,current)成立而recovery禁止++cursor，只更新图戳继续。**综合日志/框/代码推断**step54..74不输出新段而耗尽原75预算（25/37未推进），解释为什么画面还有方块却高度停住。不是本轮规划拒绝、最终中心门或CAN中断。

**下一方向（当前只诊断，未授权新的应用修改）：**把ALIGN与靠近的视觉夹持参考统一到实际原RGB；靠近持续追同一物体的该参考误差，而不是等快出画才固定tip转腕。原世界模型锁定不重锁，模型继续只负责可达/碰撞；恢复若固定tip不可解，应规划位置+朝向联合小段而非current→current空循环。需先给具体原owner局部修改方案并获同意，不以用户现象提问当实现/新运动许可，不擅改相机TF/抓取落点或只强加J5。

收尾原保持且未Disable/Reset/回零，准确两个collector INT rc0、host无实体/采集/隔离栈。新SDK接收rc0 epoch1791944111.498502/high4111.494289/100Hz、六true/速度0、q[-.331123866,1.847570640,-1.380293639,.046652651,.856206171,-.100408792]rad/99.6mm无错；当前稳定反馈已验证。完整实体抓取仍未完成，应用仍d051bf5，既有用户dirty/远端分叉保持，仅本地未同步GitHub。
