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
