# 2026-10-14 原RGB统一参考与联合视野恢复

## 最新部署/实测接续

局部实现已提交9ea9fc1，git show --check0，仅12指定文件，用户wiring注释/vendor/reference保留。形状目标补构建rc0/7项通过；完整共49+13+6+7 C++与19Python通过，真实帧回放/恢复候选规划均0。旧first namespace与静态断言失败保留，不冒称所有首次成功。

actual双binary已同步并hash复核：executor f0da36c…、detector c99e450…，原install仍指向原build，原入口87039b…保持。原binary/双源/共享头备份/home/johnwick/brain_robot_logs/view_guard_20261013/rgb_reference_previous_d051bf5/（executor d4c7063…/detector8e763f4…）；回退须用户方向后恢复这5文件，不整库回退。模型恢复候选共27个分析分支（含零角仅分析），首正常分支完整可达，非“其余27”。

运动清单：沿最新SDK7112.335/100Hz/六false/速度0实际姿态q[-.016702801,-.003647738,0,.083199845,.276337980,.020734512]rad；原脚本使能→直接观测[0,.98,-.75,0,.30,0]rad、不先绝对回零，六轴由MoveIt联合规划，主要J2/J3、J1/J4/J5/J6以实际误差补偿。原任务min[-1.5,-.3,-1.4,-.8,-1.2,-pi]/max[1.5,pi,.4,.8,1.2,pi]，adapter .189rad/s，MoveIt加速度1rad/s²，观测速度/加速度缩放.01（预计20–60s/精确以实际日志；原最大300s），搜索.05，ALIGN J1/J5上限.135rad/s；末段8mm/1°/.08rad前缀、规划原反馈，100mm张开与最终中心/两指夹持不改。失败停止新位移/保持，无Reset/Disable或未确认自动回零，成功原安全返回后再失能。

下一只启动唯一原AUTO1，RGB模式/不在目标获得后停，日志新rgb_reference_onekey_20261014与新exact/live只读采集；启动前同一调用重新被动核对RX/高速stamp，异常不发运动。原源/配置/真实TF路径保持，当前尚未生成本次实物结果，以下是候选验证/历史。

## 范围/批准/基线

用户确认上一具体方案：复用历史成功靠近/下降骨架，统一ALIGN与靠近的原RGB参考，修复固定tip无解/current→current空恢复；先原图回放/域78只规划，再原一键实测。无需新资料或重复同意。原入口、世界身份/锁点、相机TF/TCP、关节限位/碰撞/adapter、原最终中心与两指夹持保持，不另写运动系统或拷贝ROS1/厂商示例外参。

首五Git基线c885fb1；已读规范最新路线及两技能（先真实路径和时间戳、局部修改/针对性测试）。host无旧控制栈。actual source19d4b4e04d295b4cd89ec53024f34b66c88b70d9ff9b467e4c50464085f209ed、实际旧binary d4c7063…；唯一原脚本87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0。当前候选未部署/新运动。

## 实际复用及历史证据边界

- 读官方研究归档piper_official_reuse_20261014.md：标准夹爪网格/手册9.7、J6→TCP参考区分已用于核对。现模型已含夹指，135.8mm原工具偏移不变，不重复叠加7cm/10.5cm，不套145mm例值；没有手眼板不阻断软件。
- 历史PIper_HANDOFF_20261010.md的settled_fix76预抓+9下降与闭爪请求有效；/tmp/piper_real_run_20261010_settled_fix.log现在不存在（ls rc2）。对照Git eee1453的两段PREGRASP→Cartesian DESCENT→FinishGraspAndLift及Git归档REPLAY.md，当前保留这两段骨架，只修路径推进/视野参考；历史固定朝向在后续实物导致出画，不能恢复旧TF/固定姿态整库回退。未声称历史完整抓取成功或重播不可用原始日志。
- 查看同一旧实测原RGB1791943882611928468_rgb.png（方块左中偏下）与1791943924611050612_rgb.png（左下近底边，两黑指可见）；原depth_raw1791943924391679520_depth_raw.png与debug1791943924410746105_debug.png：debug缺失目标深度支撑/samples0，黑洞非原RGB遮挡。路径均在/home/johnwick/brain_robot_logs/view_guard_20261013/translation_recovered_exact/；它们是历史，不当新鲜实体图。

## 局部改动

1. 原检测器保留depth-frame三维点/target_pixel/注册叠图，不再用其dx/dy作为ALIGN。pixel_error改原RGB轮廓质心与(.5,.5)差，按现debug宽高换算保留Servo像素增益尺度；非注册路径仍原processing grid，normalized z保持原分辨率独立定义，深度资格/形状门不变。
2. 原GuardApproachView使用同一原RGB中心和原ALIGN .05容差，不仅clamp到最近边界。实际RGB视图与精确图戳TF提供已有target_reference估计，不重锁/伪造深度。
3. 固定tip射线可行时仍优先保持计划tip；无解时原共享几何计算有界转向+相机平面平移（goal≤原30mm补偿），下一请求仍CorrectedPoseStep的8mm tip/1°、完整MoveIt/原限位碰撞/adapter和真实停稳。恢复段非零goal不能被原10mm/.12rad落点容差跳过；普通可达朝向推进仍原c0f56da语义。不消费current→current假恢复预算；确实无可用pose只报具体原恢复失败，不谎称运动。

## 命令/阶段结果（进行中）

- host只读ps无实体/MoveIt栈，df93%/5.5GB。按仓库只运行/home/johnwick/clean_disk_space.sh，rc0，93%→93%，无其他删除，最新图片保留。
- cmake --build /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place --target grasp_lift_executor cup_detector_node visual_grasp_feedback_test near_depth_executor_test -j2。首次应用目标已编译，actual方法测试新namespace缺失失败（rc2），补命名空间别名后最终重建中。日志/tmp/piper_rgb_reference_build_20261014.txt、/tmp/piper_rgb_reference_build_final_20261014.txt，不能把第一次失败省略。
- 共享visual_grasp_feedback_test13项rc0，新增原RGB增益尺度/无解联合恢复/可解tip保持；actual方法增加3项含归档底边候选，最终49项待。归档候选使用最近实际q、冻结模型范围与同帧RGB方向，明确不是精确图像时刻q/新深度/物理标定。
- 原域78 review_terminal_depth_plan.launch.py执行禁用，仅模型/规划服务，无实体driver/adapter；原生产未部署。原图回放脚本局部加指定stamp和pixel_error核对，不转发到实体域。

## 接续/未完成

### 最终软件/回放/规划验证

- 最终build session83753 rc0，49 actual executor方法全部通过（/tmp/piper_rgb_reference_executor_tests_20261014.txt）；13共享几何与6原子观测通过。首轮namespace rc2保留。Python19项通过：原real_grasp_replay曾因陈旧字符串“<= .002”失败，HEAD原实现本来已使用endpoint_tolerance/预览.002，局部更新测试核对原变量表达式，未改变任何容差；test_near_depth_wiring.py用户注释未编辑/提交。shape test第一次调用尚未构建可执行文件，不把shell最后rc0当该项通过，独立目标补构建/测试中。
- 域78指定当前同机帧回放rc0：good RGB1791943882611928468（3829samples）和hole RGB1791943924410746105（0samples），各10条原子观测，原深度资格/质量交接仍正确；原RGB error实际与独立轮廓质心一致，good=(-81.183809,+42.737779,.126850)，hole=(-104.199552,+151.461530,.378654)，尺度640x400。原输出depth frame三维点不变，未将缺失深度伪造有效。报告/home/johnwick/brain_robot_logs/view_guard_20261013/rgb_reference_replay_20261014/report.json；日志/tmp/piper_rgb_reference_detector_replay_20261014.txt。仅域78重设消息戳回放，不是真实新采图。
- actual Guard的归档末态产生非零8mm/1°请求：xyz(.361331254179,-.118136186469,.224373489578)，q(.125048023846,.979045044501,-.0109737978213,.160353884681)。同世界RGB估计下预测(.3375,.88125)→(.360986,.826147)，中心距离.414437→.354537，证明模型方向改善但不是物理标定。实际只读MoveIt原范围完整fraction1/error1/4点；endpoint q[-.325881127,1.835785528,-1.359693708,.054416415,.862343412,-.100567026]，J5数值+.006593rad不能独断物理上下。其余27候选含分析零角，仅原实际候选才可能执行；未发布实体轨迹。/tmp/piper_rgb_reference_actual_guard_20261014.txt、/tmp/piper_rgb_reference_isolated_candidate_20261014.json保留。归档URDF SHA a93ac8cba44d02dc09ca52442bb72e8d8c92f97dd732cee08702e1fe9438c581。
- 第一隔离launch在编译期间240s自然到期rc124，第二100s模型无执行实例完成核对后自然到期rc124；退出日志与规划结果分开，不算实体CAN故障。
- 新被动SDK1791947112.334885/关节7112.330487/高速7112.326491/100Hz，六enablefalse、速度0、q[-.016702801,-.003647738,0,.083199845,.276337980,.020734512]rad，99.6mm/夹爪未使能/无故障。此为有新戳真实当前位置，不再沿用上轮使能末态或以默认零反馈解释；本轮未发Disable/Reset、不推断变化原因。can0原ERROR-ACTIVE/1Mbps/.75/queue1000复用，RX8109652→8114425、错误丢包0，不重载。
- 候选binary executor f0da36c4772a8c2f3dfeb23313961b9abdd8d10b7d7a960d01fefcfff90c4ab2；detector c99e4500bae5225187a3e79523170b006a426702e703e609875db2771aa4ce66。source executor a57862a73fbbcaf56432d15ac8358257eca6ff64214b2373d28e10da1de900c6、detector14217a61f968039b9bb06c1d6adcadb92550f908d2a64fc770d0232018bbe6af。先限定提交/备份actual d051bf5，然后同原入口实测；当前尚未部署/新运动。

完成最终构建/actual方法/指定实际RGB-D回放/归档候选完整可达性后，才备份d051bf5、同步双binary+源并原AUTO1。源码和最终binary时间/hash重新核对，构建期间源有局部修正不部署旧binary。记录原型是否真正下降/恢复/夹持，而不是用单测代替目标。仍完整抓取未完成，当前没有新动作。

Git原分叉/全历史推送审查未完成，仅本地提交；不强推或自动合并。现有test_near_depth_wiring.py用户注释与vendor/reference未提交文件不纳入。
