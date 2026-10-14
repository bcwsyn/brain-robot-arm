# 2026-10-14 已检查纠偏行程与有限运动次数核算

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
