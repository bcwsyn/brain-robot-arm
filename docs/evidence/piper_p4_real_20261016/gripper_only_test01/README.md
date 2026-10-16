# 原一键入口仅夹爪测试：实现、隔离通过，实机缓闭未通过

本轮用户确认的是22:35提出的默认关闭、显式触发的原执行器仅夹爪入口及独立空载测试。并行的技能确认不是它的授权来源。控制基线4037724；期间新增的eac0117/3b29acc技能及四文档内容完整保留，不归本轮代码修改。最新实体结果不是抓取成功：没有执行臂靠近、抬升或采用新的RGB夹紧参考。

## 改动及活动链

- 只改原`grasp_lift_executor.cpp`、`cube_visual_search.launch.py`和`brain_robot_arm/scripts/start_brain_robot_cube_real.sh`，新增三个定向测试文件；没有另写实体运动程序。活动入口仍`/home/johnwick/start_brain_robot_cube_real.sh`。
- `BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY=1`要求显式P4=1、PLAN_ONLY=0、AUTO_START=1；默认0。没有臂目标文件，不伪造XYZ。专用`/grasp_lift_executor/test_gentle_gripper`调用原张爪/反馈/`GentleCloseGripper`；本模式普通execute拒绝。保留原新鲜度/故障/急停，测试不会抬升。
- 测试脚本在[7/7]后走专用分支，停止Servo，复用原`enable_physical_motion`（原true-enable和adapter接管），不调用观测/搜索/复位；六轴发布的是当前姿态保持，不是新姿态轨迹。驱动初始化使能标志与电机实际使能位不同，不可删这一步。
- 当前二进制`c3cf4eaac062300a590e14a20a70e396d4baee9b5c5bc3ac36fafd30e87867d1`。`final_deployment.json`核对三个活动副本与规范SHA相同，原任务/检测YAML、adapter及driver与4037724相同。初次部署`deployment.json`记录的是中间版本，不能当最终SHA。
- 没有改`gentle_gripper.hpp`的速率、超前量、超时、力矩/接触阈值；默认靠近、生产TF/TCP/六轴限位/禁用腕部Octomap不变。不采用下15/前15mm补偿或旧7cm/10.5cm叠加，不刷固件、写零点、ResetPiper、MasterSlave或USB/CAN恢复。

## 验证与真实失败

1. 初版41项定向pytest通过；补原张爪2秒settle后118项回归通过（有重叠，不把数量相加）。补原接管和专用cleanup后最终42项定向通过，含8项新测试。构建rc0，原执行器单目标构建约106.52秒；后续settle构建也rc0。日志/JUnit完整保留。
2. 最终二进制的域78真实执行器＋明确合成反馈三场景全通过：空载到25mm/EMPTY_NO_LIFT；37mm合成物体/CONTACT_CANDIDATE_NO_LIFT；反馈中断/FAULT且不抬升。三者臂轨迹0、joint_commands0，普通execute/忙/测试急停后重开拒绝。不是机械物理仿真或实机夹持成功。父进程rc0无强杀；empty场景MoveIt收尾子进程-11，其他部分SIGINT子-2，原件分账，不冒称所有子进程正常退出。
3. 实机前只读5对原RGB-D＋同戳debug，看到完整方块和闭合夹爪，未夹住；6秒SDK整窗静止rc0。首/第二次紧邻SDK4秒rc2及速度瞬态如实留存，不能用q波动0偷换该rc2；原控制新鲜反馈/限位准入仍执行。原健康CAN复用。
4. **首次实体失败是新增分支遗漏原使能接管，不是硬件/CAN坏。** 原电机使能true，但新driver逻辑enable=False，45条显式夹爪帧被拦，driver正常GripperCtrl调用0，夹爪保持0.4mm，未开始慢闭。正常cleanup调用未启动的visual stop又发了一条两点、两点位置完全相同的当前姿态HOLD轨迹；监督器把任何轨迹均判异常，记录RuntimeError并中断收尾。这不是新的六轴位移，不能报告“首次轨迹消息0”。两处均局部修正：复用原enable接管；仅测试模式跳过visual stop，其余cleanup不变。
5. **重试实际张爪成功，缓闭仍失败。** 原入口完整[7/7]后张爪反馈0.4→99.4mm，进入CLOSING；约19.741秒后FAULT_P4_GRIPPER_TEST_CLOSE_UNCONFIRMED，入口rc1。开口99.4→97.7→95.5→93.0→90.7mm，约8秒后停在90.6–90.7mm，末90.6mm。实际前段约1.1mm/s，不能拿10/3mm/s参考速率宣称实体实现该速度。末目标约90.1mm，目标与实际最多相差0.5mm；超时后原函数替换成实测90.6mm保持。driver正常调用1076、output gate拦截0、标称effort500（0.5N·m，不是指尖牛顿）。持续接触候选未成立，没有夹紧/抬升。
6. 重试记录实际夹爪帧12639、开口/effort源戳持续更新；8个status0在OPENING后0.425–0.525秒，处于原driver保留的首次0x02/0x01清错握手窗口，不能说整个活动期一直使能。缓闭阶段状态均64（夹爪使能，无低六位故障）；没有六轴DisableArm。测试从OPENING起六轴反馈峰峰均0，臂轨迹消息0，joint_commands为同一当前六轴保持帧。不能把它写成“零ROS命令”；也不能仅因CAN总RX增长就断言每电机连续性。运行窗口ifindex3、ERROR-ACTIVE，RX67988053→68244587，TX53113→58146，rx/tx errors0，原dropped297不变。
7. `gripper_can.log`接收套接字未见0x159，原接收原件已gzip无损保留；本地另一套接字TX不一定回环到candump，不据此声称没发命令或独立证实每次调用上总线。driver调用、TX增长和实际开口变化分别记账。
8. 末被动SDK4秒rc0：39fresh/3.816秒、q峰峰0/速度0、六轴使能true；q=`[-.049872396,1.652784112,-1.009274952,.044953188,.778944376,.088894624]`rad，夹爪90.6mm、状态使能true/故障false。所有自有控制源退出；没有DisableArm/复位/返回观测。此为采样末状态，非持续监测保证。

## 画面与原件

重试张爪后的[原彩色](retry01/real_record/0017_rgb.png)、[终止原彩色](retry01/real_record/0023_rgb.png)、[对应原16位深度](retry01/real_record/0023_depth.png)与[彩色调试图](retry01/real_record/0023_color_debug.png)均保留。图中方块仍在棋盘格，夹爪开在下方，不是成功夹持。深度孔洞不解释为RGB黑影；邻近时间配对不称硬件同步。

- 运行根：`/home/johnwick/brain_robot_logs/p4_gripper_only_20261016.CTeKXp`，首失败在根下，重试在`retry01/`。
- `actual_analysis.json`：原状态/诊断、2秒分箱实际开口/effort/源戳、driver调用、六轴/轨迹和两次真实退出。`final_deployment.json`：最终规范/活动哈希；`final_sdk.json`：真实末状态。
- `manifest.json`覆盖369运行原件、归档payload16,419,621 bytes；jsonl与全CAN日志gzip，解压逐字节/SHA与原件核对，其他`.log`改`.txt`但字节不变。README/本地gitattributes是额外说明文件，不假称属于这369原件。未提交ELF或before备份，home原件未删除。
- preflight脚本复用旧只读工具，其中内部`execution.json`的旧role/baseline/operator字样是历史工具注释，不是本轮用户新重连；外层`readonly_execution.json`及本报告为本轮准确作用域。所有初始失败、两个版本的合成测试和构建均保留。

## 命令、耗时、结论与下一步

实际两次均由原一键入口运行，核心环境：`BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_P4_OPEN_LOOP=1 BRAIN_ROBOT_P4_PLAN_ONLY=0 BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY=1`，目标文件为空；`run_actual.py`只启动原入口和只读记录器，没有替代控制发布器。完整命令、环境、窗口、父子退出见各wrapper与execution文件，测试复现入口在规范test目录三个新文件。PYTHONNOUSERSITE保留系统NumPy，driver子进程用户CAN依赖放系统路径之后，未装/升级库。

可测窗口：首次实体103.70秒，第二次121.38秒（从SDK前准备至原入口收尾，含startup/cleanup，非机械运动时间）；第二次至OPENING约91.08秒，缓闭19.741秒。隔离最终三场景总48.43秒，含节点启动/清理。整轮准备/分析/第二次编译未完整独立计时，不造总用时或提速百分比。已推进：原夹爪测试链可独立实测；排除重试的driver准入漏接，定位到0.5mm短超前＋实体慢响应/停滞组合，不回CAN/TF/限位巡检。**尚未证明是固件死区、摩擦还是0.5N·m对应实体响应，不能唯一确诊。**

下一只用本次真实响应做缓闭参考/设备响应离线对照，提出同一缓闭函数的局部超前量/超时调整，再按改前说明取得同意；不盲加力、不改抓取落点或直接重跑相同条件。当前无需现场重摆/重启。RGB夹紧有效参考仍仅隔离候选，未获本轮采用许可；待缓闭验证后再提原P4限定目标实测，不把本次夹爪诊断扩为自动抓取。

回退：此入口默认关闭；取消`BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY`及P4环境即恢复原默认路径，本轮不自动执行它。需要代码撤销时按本提交的三个明确路径审阅逆向diff，home旧源/旧二进制在本轮`before/`保留，4037724是控制基线。不要整树reset或恢复无关dirty文件。仅本地提交，既有main分叉/历史发布审查未解，不自动推送。
