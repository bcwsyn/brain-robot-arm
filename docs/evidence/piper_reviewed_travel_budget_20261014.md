# 2026-10-14 已检查纠偏行程与有限运动次数核算

## 最新实物结果：预算计数生效，新最早阻断为未组合的候选几何

3985466/actual70c3381…原AUTO1主session50059 rc1，timeout3876660/脚本3876661。启动曾卡在原timeout5s /servo_node/stop_servo客户端：3877764超过99s仍活，实体静止/STOPPED；只KILL该已超时检查客户端，让原已有||true流程继续，不重启driver/Servo/栈、不改入口脚本。此是本轮运行期协助，**不称原入口已永久修好这个timeout**；后续仅给stop检查补-k2s需另说明获准。旧相机探测-k2s不自动覆盖这处停止检查。

实际PREPARE1791950752.966056/36.7s11点→SEARCH0789.404471/OBSERVE_POSE_REACHED→ALIGN0801.327642→GRASP_READY0803.635888。10粗段全部反馈停稳，质量交接0824.614055冻结最后可靠measurement1791950822117190061/range236.959mm、base(.425790084,-.116106538,.067274143)m/size35.948mm；currentRGB1791950824516849803/age2.496917s，不是假新深度。原完整双段计划camera_arc.1799/tip_arc.1508/extra.03、38路点、78运动/116总循环。

本次34末段尝试、33 MEASURED_SETTLING_CONFIRMED，旧预算逻辑的新日志真实出现33段reviewed reservation；51条adapter接受含prepare/search/保持，不将不同层计数硬凑一致。step46/cursor14最后成功段reviewed_total=.163751200m、measured_total=.152006459m、allowance=.219042127m；这个额度仍原名义值，因为累计reviewed+.03尚未超过它。到位检查与运动计数已实测分离（cycle48、commands34/78），**没有达到旧超额点/额度扩充或次数耗尽，不能称已经实体验证跨过旧预算停止**。

step48/cursor15-38从ROS q[-.445380208,1.820455840,-1.399724004,.288872640,1.127981372,-.492339456]rad请求xyz(.343920814003,-.137827598230,.237539123800)m、q(.030285666762,.989658269525,.097817278696,.100454307710)，tip5.285319mm/工具1°。原完整方向/缩角/反向8候选及仅原转向的50%/25%平移全fraction0/error1（不是发布成功）；此段尚未reserve/输出，停止FAULT_AUTOMATIC_RGB_STEP_EXECUTION_FAILED，不是CAN/图像/中心门/预算/用户急停。无原下降/最终夹持/闭爪/抬升/释放，未达到总目标，不擅放宽J3或发半段路径。

### 精确新step48隔离核对（只规划）

复用域78 review_terminal_depth_plan.launch.py，原模型/原任务范围、allow_trajectory_execution=false，无driver/adapter；review_reachable_visual_step.py --steps48 --tip-fractions1 .5 .25，rc0，报告/home/johnwick/brain_robot_logs/view_guard_20261013/reviewed_budget_step48_isolated.json。起点validtrue/无模型contact，full-tip现候选与positive1°短平移全部失败；**组合已有短平移与反向朝向有6个完整解**，原范围内。例如50%tip平移(2.642659mm)+-75%工具转角(-.75°) fraction1/error1/4点，endpoint[-.444817991,1.820026276,-1.394906471,.291192154,1.110633875,-.494137660]；50%/-1°亦完整，25%/-25/-50/-75/-100亦完整。零角只是工具反事实，不自动加入实体。静态六组合解保存小JSON随Git；不当现场碰撞全排除/精确手眼标定或执行证据。

说明现策略“全平移先试反向”与“短平移仅保留正原转向”分别试，漏掉了它们的组合。下一拟仅原ExecuteVisualPose在现候选均失败后补组合，仍原目标/nominal/8mm1°/.08rad/完整路径与真实反馈/最终夹持，不改变TF或限位。**这个新的组合策略尚未批准/实现/部署**；不能把刚批准的预算改动扩展成新运动策略。本轮没有再实机重跑。模型launch140s自然超时124，MoveIt已知SIGINT析构-11与此前规划结果rc0分开，所有隔离节点已退出，不当实体通信故障。

### 本次图像/反馈与停止后保持

已看同次0093三图以及GRASP_READY RGB1791950803716299920（框中心.478125/.485417）、失败RGB1791950874118085955（框[.409375,.458333,.559375,.654167]中心.484375/.556250，完整方块仍在两黑指视野中）；原子center_covered=1，但本帧depth qualifiedfalse/samples3/coverage.001908，冻模/RGB可工作，不重锁。对应native_depth1791950874085695985有146596非零点/中位.246m，16位默认预览近黑非全帧无数据。debug1791950873318670130较失败RGB早.799416s（仅近邻叠图不冒称同戳）显示目标支撑黑洞、samples35；原RGB无此黑洞。

主原cleanup无Disable/Reset/回零；exact3876743/session10042与live3876772/session3671 INT正常0，host全部控制/相机/采集退出。新被动SDK1791951067.101839/关节1067.101092/high1067.092247/100Hz，六true/速度0、q[-.445617465,1.821425607,-1.400469645,.289026524,1.128582254,-.492601728]rad，99.6mm/true/无故障，can0RX17642528/错误丢帧0、守护无停滞。

隔离起点用精确失败日志的原ROS反馈，不将稍后SDK换算值直接当同一q：实际entry metadata确认piper_single_ctrl→piper.piper_ctrl_single_node:main，publish角度按raw_deg*.017444，而被动SDK打印按math.pi/180，因此当前J3存在约.000746rad数值差；只记录接口约定，未修改驱动/限位/命令，不把它说成新硬件故障或大几何误差。下一从新鲜原反馈规划，不把小JSON/隔离endpoint直接发给实体。

全部大日志/图片在/home/johnwick/brain_robot_logs/view_guard_20261013/下reviewed_budget_onekey_20261014、reviewed_budget_exact_20261014/frames.jsonl、reviewed_budget_live_20261014/observer.jsonl，主输出reviewed_budget_onekey_stdout_20261014.txt；原图/原戳/姿态保留，不重复旧失败底层。actual70c3381…/detectorc99e450…/唯一入口87039b…保持，旧9ea9fc1回退点完整。Git仅本地，远端分叉/历史审查和用户dirty保持。

## 最新部署与待实测

3985466已限定10路径提交/检查0；actual单executor70c3381…与source2144f22…/near头567377f…同步，旧9ea9fc1单binaryf0da36c…/源/near头备份/home/johnwick/brain_robot_logs/view_guard_20261013/reviewed_budget_previous_9ea9fc1/。detectorc99e450…与唯一原脚本87039b…不变；不整库回退或覆盖用户wiring/vendor/reference。

新被动SDK1791950493.657183/关节493.651086/high493.647062/100Hz、六true/速度全0，q[-.394025532,1.715588842,-1.168061602,.302762265,.905564082,-.462198093]rad，夹爪99.6mm/true/无错误，姿态与上轮保持一致。can0 index10/ERROR-ACTIVE/1Mbps/.75/queue1000原链复用，RX16249753→16259869/错误丢帧0，不重载。host无旧控制/采集栈（ps末尾仅本轮检查shell匹配，不当真实控制器）。

运动清单：原当前→观测[0,.98,-.75,0,.30,0]rad，主要J2/J3/J5与其余实际误差联合；原taskmin[-1.5,-.3,-1.4,-.8,-1.2,-pi]/max[1.5,pi,.4,.8,1.2,pi]，adapter .189rad/s、MoveIt acceleration1rad/s²，观测缩放.01/预计20–60s/精确日志为准，原观测最大300s；搜索.05、ALIGN .135rad/s，末段仍8mm/1°/.08rad前缀，100mm张开/最终中心两指保持。停止条件原新鲜反馈/身份/限位/完整规划异常，异常停新位移保持，不自动回零/Disable/Reset；成功仍原安全返回后失能。

下一原AUTO1同一入口，新reviewed_budget_onekey_20261014与exact/live采集，当前本次实体结果尚未产生。预算已经获准，不再等许可；构建/测试通过不是抓取成功。Git仅本地/远端分叉审查保持。

## 批准/现状/范围

用户“好”明确同意上轮具体提案：按完整检查的实际纠偏路径核算行程与有限次数预算，保留8mm/1°、原范围/反馈/闭爪条件；继续原AUTO1。基线6406768；host无旧栈，实际executor f0da36c4772a8c2f3dfeb23313961b9abdd8d10b7d7a960d01fefcfff90c4ab2/sourcea57862a73fbbcaf56432d15ac8358257eca6ff64214b2373d28e10da1de900c6，detectorc99e450…，唯一原入口87039b…。当前候选构建中，未部署/未新运动。旧post7750.504六true/静止是最近已核对记录，不冒称新当前反馈。

复用原RGB参考/冻结225.955mm末段与双段主路径，不改相机TF/TCP/模型/目标/轨迹几何/配置/启动脚本；没有新供应商控制程序或独立CAN写。此前step52/14-36 PREDICTION_RANGE_EXHAUSTED与内部软件停止已有确定因果链，不能因版本更新反复回到基础CAN/刷固件。完整实体抓取仍未完成。

## 最小实现

1. near_depth::ReviewedCameraArc只对保留的相机位置折线求弧长，起点+至少一轨迹点，有限性检验；不能用端点直线长度代替绕行，也不给裁掉的后缀额度。
2. 原ExecuteVisualPose每个轨迹点经过原joint/.08rad、tip8mm/工具1°等检查后才保留camera FK样本，裁切break不加入被拒点。完整路径/限位/裁切/新起点反馈均通过后，在原ExecuteArmTrajectory之前调用原owner的ReserveReviewedVisualCameraTravel。
3. 仅冻结自动RGB且near_path_allowance_ready作用，预览/粗段/最终修正不作用。reviewed初始为进入终段的真实已计行程；每个拟执行已检查段追加一次。许可=max(原名义许可,reviewed累计+原episode30mm)，extra只计一次，不每次叠加30mm，也不拿未审查的actual漂移刷新上限/深度种子。
4. 原循环公式仍给有限运动命令上限（旧例75）；实际路点到位推进另最多36次，不耗运动计数。每循环必推进一路点/尝试一有界运动/失败退出，所以总循环≤75+36=111。原种子age与RGB/反馈新鲜度不放宽，最终中心/实际两指判定不变。
5. 输出每个保留段segment_arc/reviewed_total/measured_total/allowance与commands/cycle，便于区分实际运动/到位检查/额度停止，不把内部软件stop标签冒称用户急停。

## 回归/构建（进行中）

- 原near_depth数值测试新增折线/零运动/NaN、单次余量、次数有限和原RangeReject/新额度与反馈/age仍拒绝。
- actual executor新增三项真实private方法测试（仅domain78内存输入/auto_execute=false/real_grasp_enabled=false）：锁点不变/extra不重复、预览与粗段不作用、坏保留路径不授予额度。大路径输入只用于算术测试，不是实机步长许可。
- Python原测试补调用顺序/裁切/新起点先于Reserve、Reserve先于Execute，以及次数分离；21项rc0，用户test_near_depth_wiring.py已有注释未编辑/提交。
- 构建命令source原Humble/实际overlay后cmake --build /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place --target grasp_lift_executor near_depth_executor_test near_depth_tracking_test -j2；日志/tmp/piper_reviewed_budget_build_20261014.txt，session63072。候选尚未部署。首次apply_patch未匹配额外测试上下文整体失败，正确限定补丁成功，未覆盖用户变更。
- 根分区94%/5GB，仅运行已批准/home/johnwick/clean_disk_space.sh，rc0仍94%；没有扩展删除，已有最新实物日志/PNG保持。

## 下一步骤

### 接续验证完成

构建session63072 rc0；actual52项与near19项session59456 rc0，日志/tmp/piper_reviewed_budget_executor_tests_20261014.txt、/tmp/piper_reviewed_budget_tracking_tests_20261014.txt。21Python回归session20104 rc0，用户wiring注释1行保持未提交。git diff --check0。候选executor SHA70c338122cdcbd8309e574849a123d4915be7536b86005d05b4bed84b230250e/source2144f2237150106a5e0e7e8d01a8112821b5e1f291396ce5e22e78f132281e33/sharednear头567377f9ea984da659bfbe5f8ffed536b830e3699c43b237054151655e12ba0c。当前尚未部署，下一限定提交后备份9ea9fc1单binary/源/头，再原AUTO1。未改几何，所以不重复旧隔离IK/TF基础；数值通过不等于实物抓取。

完成52 actual方法/全部near数值及Python回归，审查限定diff，提交→备份actual9ea9fc1单executor/源/near头→部署/原SHA→原AUTO1，同步新RGB/depth/debug/atomic/关节。不重复未改几何的旧隔离规划，不盲重放绝对q。每段原完整可达/范围/feedback仍必须通过；完成下降→最终实际夹持→闭爪抬升释放才能称目标完成。出现新最早停止先保存其具体证据，不擅改其他门。

Git仅本地，origin/main既有分叉/历史推送审查未完，不强推/自动合并；用户wiring/vendor/reference改动不纳入。下一代理先git status --short并读本记录，已有授权不重复等同意。
