# 2026-10-13 同指尖可达朝向：实体分支通过一次，下一段仍不可达

## 版本及实体运行

- 代码79e06bc，binary `2b309aa302157ccd43f4c080f724c0e70d1ab1384c79a35142cec39cb3b00343`；CPP `64054b75855799a8755e73b1ddec51c73b7707d17fc3f8463cf5950dbc6f1e1e`。
- 唯一原入口 `/home/johnwick/start_brain_robot_cube_real.sh`、SHA `87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0`，AUTO_START=1/STOP_AFTER_TARGET_ACQUIRED=0/DEPTH_ONLY_TARGET=0。
- PREPARE1791898831.883176→SEARCH8870.605951/OBSERVE_POSE_REACHED→ALIGN8883.252974→GRASP_READY8886.257843。目标surface(.4297,-.1317,.0854)m，75预抓取+13下降=88路点。41条自动轨迹accepted与41条真实反馈确认消息（8888.550..8943.807），不计启动/对齐及故障后保持命令。尚未最终下降、闭爪或抬升。
- loop105/cursor65/88：原完整朝向Cartesian fraction .5，75%候选也 .5；50%候选完整路径5点，8941.582783选中、8941.615253由原adapter接受并执行。没有执行任何不完整Cartesian路径。
- loop106/cursor仍65/88：原朝向和75/50/25%均fraction0/error_code1、只返回起点，不发布新运动。8943.807464 FAULT，8948.515116 STOPPED/原cleanup退出rc1；没有Disable/Reset/自动回零。不能称越过此前66/89，两个seed/路径长度不同；仅新同指尖候选分支实体执行被证实。

## 精确失败输入

frame=base_link，link6 pose xyz=(.358475739084,-.120301099480,.255726122082)，qxyzw=(.150386547911,.973068653928,-.022665086449,.173226945961)。

PLAN_START qrad=[-.324074632,1.777875036,-1.396182872,.014984396,.908117196,-.023183076]，全开反馈99.6mm。

## 隔离MoveIt只读对照

复用实际安装原launch的`_physical_gripper_description`（两指±50mm）及cube_task_real原六轴范围，ROS_DOMAIN_ID=78，allow_trajectory_execution=false；只建立FK、StateValidity、Cartesian服务客户端，不创建任何实体控制节点/发布器。指尖目标位置保持相同，16个候选几何误差<1e-15m。隔离场景仅模型，不能排除现场环境碰撞。

| 阶段 | 朝向比例 | 完整路径比例 | 解的J3 rad |
| --- | --- | --- | --- |
| 105 | 1 / .75 | .5 / .5 | 不完整，不执行 |
| 105 | .50 / .25 | 1 / 1 | -1.397327 / -1.391857 |
| 106 | 1 / .75 / .50 / .25 / 0 | 全部0 | 仅原起点 |
| 106 | -.25 / -.50 / -1 | 全部1 | -1.396233 / -1.390749 / -1.379835 |

两个精确起点StateValidity=true、contacts=[]。说明此次不是非法起点/模型自碰撞；原方向及缩短同方向仍无法满足下一点，而反向少量转角有模型可达解。**负比例只是诊断反事实，不在已批准候选中，未应用或实体执行**。不能以只读候选成功断言最终抓取路径/现场可达。

当前runtime RealTrajectoryWithinLimits和launch规划均用原task J3≥-1.4；先前数值对照额外-.005margin并非本次runtime额外起点限制，不能将本次fraction0直接归因起点越过-1.395。归档范围不授权修改现场范围。

首两次分析器缺少base_link固定TF，得到错误-21，均不构成可达性数据；随后补齐原robot_state_publisher，严格检查FK/Cartesian frame error，用最终`attitude_isolated_comparison_rsp.json`为有效对照。不得引用前两份json作实体证据。

## 视觉、最终状态、证据与回退

- 已看0032/0058/0065原RGB、debug及原生深度。方块完整、十字下方略左，夹指可见，未实际包围；末debug218mm/2390样本，不是近距深度零。0065RGB8950.580162/debug8950.780114/depth8952.042130/q8952.133142为停止附近不同时间帧；0080墙钟8996仍同一缓存，不能冒充当前新帧。
- 结束新SDK1791899002.266251/high9002.262385，六轴enable=true，q[-.324247268,1.778822120,-1.396926627,.014992378,.908600955,-.023195426]rad。CAN RX19353675/error-drop0，无需重启/重载。主与两读采集已退出，隔离分析栈也已INT结束，不自动续跑。
- 日志根 `/home/johnwick/brain_robot_logs/view_guard_20261013`：attitude_onekey/visual_stack.log SHA `c11bbc11703214f7360111334e8a0ea8e75fafdf02d944e23da65afc9912e5c4`；attitude_exact/frames.jsonl SHA `badddb24b40833841c9a932cecac50ffb323e8100cd1f25f15ec3918f89ae416`；attitude_live/observer.jsonl。
- 有效隔离JSON SHA `fbfa94bde9b2cbad14a07dd0df4a9d872e43648a3ebaa3c5fa2472d3bf4385e0`。只读脚本piper_attitude_endpoint_review_20261013.py SHA `cf3a0ccdcedc87e545aebcb338d8820c2f25f52ea5f88973f4e21e71e48122f0`、同名launch SHA `e5a53a40e8dae13c455799b37aad4b9509483c7004040067f8984a4f1c0e0f46`（/tmp原文件及rootlog备份），域78运行launch后执行client；仅分析，不自动执行输出关节值。
- 旧1de994f binary备份attitude_previous_1de994f.bin SHA `827923fc5a19c6b08b6e11ea107b07859e421440011e1f54e978899b2d62f338`，只在无grasp时连同原源版本回退，不自动回退。大图/模型/binary不上Git。
- 下一需先说明并获批准：是否允许有限反向朝向候选（仍同指尖、≤原1°、原完整MoveIt/限位/碰撞/反馈、最终闭爪不变）以离开J3边界；不能仅重复此次75/50/25同方向实验。
