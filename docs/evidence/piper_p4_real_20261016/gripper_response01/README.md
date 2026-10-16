# 缓闭参考响应修复：实际推进到25.8mm，末段CAN停流未确认完成

2026-10-16 23:35，基线`5ca2072`。用户要求自主继续、只在必须实机操作时叫，特别要求读取新增skill；本轮按此权限，在修改前说明只调整原缓闭参考超前/有限时间并实测，不扩大为新目标抓取。`summary-first-diagnostics`、`ros2-piper-debug`、`surgical-change`已完整读取并应用：先关联旧数据、只构建受影响目标、复用原入口/已有工具，不重复健康链或已无效的恢复。

## 从旧数据定位而非猜测

`response_analysis.json`读取上轮固定原件（SHA列在文件中），888个执行器缓闭参考中882个在150ms窗口找到同数值适配器转发，6个未匹配，非逐消息独立送达确认。停滞后仍有462个driver正常调用，目标90.1–90.2mm，实际90.6–90.7mm；没有微小目标过滤逻辑，不归因适配器吞掉全部指令。原0.5mm超前约束与实体响应组合限制推进，尚未唯一辨识固件死区/摩擦/位置环。

官方[接口文档](https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD)及[夹爪示例](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_ctrl_gripper.py)仍是开口/扭矩命令、真实反馈；示例没有替本机定义0.5mm死区或保证慢速。本轮不照搬其大幅反复开闭、升级SDK、刷固件或写零点。2mm是本项目本次有限实验候选，不是供应商推荐值。

## 只改原策略和定向测试

- `gentle_gripper.hpp`：最大参考超前0.5→2mm；10/3mm/s参考速率、尺寸预闭合、25mm目标下界、持续effort接触条件、空夹到位条件和新鲜度保持。`Timeout`仅将名义行程时间乘2后加原5秒，99.4mm起点为34.4538秒，仍有限；原script专用60秒外限不改。未调力、空夹容差或允许抬升条件。
- `test_center_gentle.cpp`：停滞目标仍受2mm约束，不累积到零；增加慢响应/量化观测正例与悲观持续停滞负例。
- 没有改executor.cpp、launch、启动script、adapter、driver、任务/检测YAML、生产TF/TCP/臂界限、相机/Astra或几何落点。下15/前15mm未执行；RGB-PnP任务参考仍未采用。原入口`/home/johnwick/start_brain_robot_cube_real.sh`和默认关闭测试模式不变。

## 离线与部署

1. `cpp_first.xml`首次新模型失败：把每步物理状态本身舍入的模型停在25.7mm，原本预期EMPTY不成立。保留它作为“不误报接触/空夹”的负例，没有为了通过而改生产判据；另加连续物理状态/量化传感器的正例。最终8个C++测试通过，活动原`center_gentle_test`也8项通过。
2. `compare_policy.cpp/.py`分别编译5ca2072原策略与新策略，使用同一两个**明确假设、未辨识为实体**的响应模型。连续状态/量化反馈下旧策略19.74秒只到71.86mm（非复现本机90.6），新策略16.68秒到约25.22mm/EMPTY；悲观每步物理量化模型新策略34.46秒到25.7mm仍未确认。均不产生CONTACT。不能将这项比较当真实死区或实机成功。
3. 仅原executor及center_gentle_test两个目标构建rc0，106.096秒；`deployment.json`保存5ca2072精确前件SHA、活动头文件/测试SHA、旧binary备份及新binary。最终活动binary **61c8e5d185a0778960f591cd63dc35fa731db40e1f4989a6999db327d1996cf5**。两个源副本一致。
4. 原仅夹爪入口8项Python合同回归通过，.42秒。原实际executor在域78三回路EMPTY/合成37mm接触候选/断反馈均通过，臂轨迹/joint_commands0，无抬升，普通execute/忙/测试急停后重开拒绝；合计48.378秒。父进程均rc0/无强杀；stale场景原MoveIt收尾子-11，另有SIGINT子-2，保留原日志，不冒称所有子进程正常。

## 唯一一次实体尝试及停止原因

`run_actual.py`只启动原入口及复用的只读记录器，AUTO1/P4=1/PLAN_ONLY=0/GRIPPER_TEST_ONLY=1，无臂目标；不是另写运动链。启动SDK4秒rc2的速度质量结果原样保留，39fresh实际使能/限位核验与rc2分账，不偷换静止门。启动前q/上下界/速率/力矩/窗口/停止/回退均存`motion_brief.json`，六轴目标不变。

实际`[7/7] → OPENING → CLOSING`：90.6mm初态张至99.4mm，缓闭**99.4→25.8mm**，明显越过旧90.6mm停点。不是靠改旧19.7秒超时才前进：本次在15.331秒已因反馈问题停止，早于旧超时；但不唯一证明实体内部原因。没有实物夹持/抬升，方块一直在棋盘格，两指内空载。

最后新鲜夹爪CAN帧源戳`1792164682.931361538`、接收`1792164682.9344795`，开口25.8mm、effort−.101N·m。最后正常driver目标25092微米/.5N·m，非零目标；在FAULT前执行器最后参考25.0925mm，尚未正式到25mm下界。实际<=26mm只有12帧/.110秒，不能据此判持续空夹或接触，也没有证据支持再放宽原空夹容差。

`1792164683.436`原夹爪新鲜度超过.5秒，发布`P4_GRIPPER_FEEDBACK_STALE_HOLD`/FAULT_CLOSE_UNCONFIRMED，**不是34.45秒worker超时**。尝试25.8mm近测保持随后被driver原`feedback_available=False`门拒绝，不能宣称此保持已送到固件。`23:31:26`原can_health记`CAN_RX_STALLED_3S`，随后原软件急停/FAULT_ESTOP和清理，原入口rc1/监督wrapper rc2；没有DisableArm、复位、回观测或新臂轨迹。

实际9383夹爪帧、683夹爪目标、臂轨迹0，OPENING之后记录六轴峰峰0；joint_commands仍含当前姿态保持帧，不能说零ROS命令。原状态15帧短暂0来自首次开爪清错握手，最后有效状态64不等于当前仍使能证明。停流后的新SDK4秒rc2/0fresh、同ifindex3/RX增量0，不能把SDK默认零q/false使能当真实回零或掉电。

本次接口前后ERROR-ACTIVE、RX72610070→72832932、TX58146→61475、错误0/旧dropped297不增；总量掩盖了尾段停流，所以保留独立停流窗口。`kernel_after_start.txt`在本次起点后没有新gs_usb/USB/xHCI相关错误，根因未唯一确定，不归责用户动接口、磁盘或硬件。既有记录已证明此类RX停流后重复guest重载/USB reset无效，本轮不做这些重复实验。所有自有实体/隔离控制源已退出；没有当前新鲜姿态/使能可证明。

## 画面、原件与用时

已实际查看[启动原RGB](real_record/0001_rgb.png)、[末段原RGB](real_record/0023_rgb.png)，夹爪开口确实缩小，方块仍在桌面，不是抓住。对应[原16位深度](real_record/0023_depth.png)及同戳debug保留，邻近RGB-D配对不是硬件同步。24快照/5,586,876图片bytes，8MiB上限，未填深度洞。

运行根`/home/johnwick/brain_robot_logs/p4_gripper_response_20261016.Uq8iDm`。manifest覆盖190运行原件/8,180,673归档bytes，jsonl/CAN gzip逐字节回读与SHA一致，`.log`改`.txt`字节不变。README/.gitattributes为额外说明；排除before备份及所有ELF，不删除home原件。`actual_analysis.json`继承分析器中的尾部2秒分箱可含清理，新增`closing_to_primary_fault_s`才是15.331秒；不能用包含后续ESTOP的旧duration代闭合时间。

已测：旧数据关联2.332秒；旧新模型编译/对照约3.56秒；构建106.096秒；最终三隔离48.378秒；实测窗口101.780秒（含SDK、startup和cleanup），其中至OPENING约76.654秒，闭合至FAULT15.331秒。其他准备/审阅/编译首测与分析未独立完整计时；不造整轮提速，重叠项不相加。无CPU重分析与实际控制并发。原入口常规清理在56%根盘下运行，不额外删材料。

## 现在所需唯一人工动作与接续

已请求用户仅在宿主VMware“可移动设备”断开后重连USB-CAN到此VM；不移动/失能/断电重启机械臂，不动相机。此请求是恢复真实接收，不是普通sudo问题；不反复重试已经无效的guest动作。

恢复后先用新鲜被动反馈确认当前q、使能、夹爪末开口，不自动沿用25.8mm旧帧、不重走观测/SEARCH。再根据原实际末状态做最小的原入口缓闭完成核验；不为补统计盲目再张爪/不提前放宽空夹/接触。新RGB夹持参考仍未实机采用，不从本次夹爪许可扩为候选抓取。

回退点`5ca2072`：只对本轮头文件和对应测试审阅逆向diff，home `before/`保留精确旧源和c3cf4eaa…binary；恢复源与活动副本后配套重建，或经核验使用一致旧binary，不整树reset、不覆盖846项原有dirty。默认测试模式仍关闭；本次保留新2mm/有限等待代码，但**尚未宣告实体完整通过**。Git仅本地，既有main分叉/历史发布审查未解，不自动推送。
