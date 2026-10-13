# 20cm两阶段实体验收和原末段规划新阻断（2026-10-13）

应用提交 `0c14428`，部署/开始记录 `265a150`。使用ROS2与手术式技能核对原运行路径、同帧TF、修改归属和用户原改动；没有另写实体入口。原一键SHA `87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0` 不变；新CPP76458e…、binaryb9f1c1…详见进度。旧binary备份 `/home/johnwick/brain_robot_logs/view_guard_20261013/terminal_stage_previous_1cf6423.bin`，SHAa20a541…；有需要时以反向Git提交回退 `0c14428`，停栈后恢复旧源/构建部署，禁止reset --hard或覆盖其他用户修改。当前不要自行回退已实体通过的两阶段。

## 实体执行

唯一命令（外部timeout用于有界采集/收尾，不是新的控制入口）：

```bash
BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/view_guard_20261013/terminal_stage_onekey timeout -s INT -k 8s 600s /home/johnwick/start_brain_robot_cube_real.sh
```

日志目录 `/home/johnwick/brain_robot_logs/view_guard_20261013/`。实体阶段epoch：PREPARE4628.6365 → SEARCH4648.6308/OBSERVE_POSE_REACHED → ALIGN4662.952 → GRASP_READY4666.820 → DEPTH_GUIDED_COARSE_APPROACH4668.858 → HOLD4686.749 → freeze4687.363 → 原PREGRASP失败4687.433。epoch的公共前缀为179190；非墙钟时间秒片段不能孤立作为日期。

粗段step0..12共13条小步轨迹经过完整MoveIt/adapter/真实到位，step13测距 `.202313m`，停稳三帧中值后冻结 `.202312m`、base `[.413130775,-.113936370,.062490152]m`、尺寸`.037309m`，最终stamp `1791904687265971123`。中间异步深度等待正常恢复；没有因为旧远种子偏差重锁物体/退回ALIGN。

原主策略43预抓取/14下降路点，Cartesian预抓取fraction `.2558139534883721`/error_code1，拒绝执行部分路径。没有末段输出、闭爪、抬升或释放。原脚本rc1、自动cleanup，无DisableArm/Reset/零点目标。结束SDK4754.1961/high4754.1919/100Hz，六轴true/速度0、q `[-.293948353,1.318753330,-.646836474,0,.330879520,0]rad`、夹爪99.6mm/200Hz/使能无错误；读采64185和23249 INT各0，栈/采集退出。

## 实际三图和同帧证据

已查看terminal_stage_live/evidence/0021、0035、0049的RGB/native depth/debug。0035是搜索中方块下边缘裁切，不当作靠近深度丢失；0049完整方块、两指均可见但尚未包围，RGB4696.666、native depth4696.783、debug4695.867不同stamp，不假称三图硬同步。

精确冻结RGB另已查看：`terminal_stage_exact/1791904687265971123_rgb.png`，同stamp框 `[.284375,.4375,.421875,.6125]`，raw depth-frame点 `[-.010498966,.015724769,.202]m`，完整方块在原RGB中偏左、两指在画面下边缘可见。最新q戳4687.254只是采集附件，执行器变换使用确切图像时间TF，不以latest q替代。该帧未附40ms内native depth，不伪称有同帧原生深度截图；同stamp检测点/框和三帧freeze日志是重测证据。

0049 native depth为uint16/400×640，非零比例`.736953125`，非零原值中位244；直接按16bit全幅显示近黑，不是“所有深度归零”。debug有效目标202mm/4589样本，旁边黑色配准空洞不当作夹爪障碍。初次数值查看遗漏PYTHONNOUSERSITE导致NumPy ABI异常，系统Python加PYTHONNOUSERSITE=1后读数0，无依赖/运行配置改动。

## 一次新冻结快照隔离规划对照

复用现有域78禁止执行的model launcher，当前模型两指±49.8mm、原task位置范围，start q来自失败日志。start_valid=true/contacts空，隔离模型不等于现场环境已验证。工具 `test/review_terminal_depth_plan.py`，持久launcher `test/review_terminal_depth_plan.launch.py`；无SDK、adapter、执行接口或实体域输出。原共享C++ `review_target_directed_geometry` 生成与原执行器相同路径。

| downward_fraction | 预抓取完整率 | 最后接受点J4/J5/J6(rad) |
| --- | --- | --- |
| .50（原） | 11/43=.255814 | .723131/.086236/-.730989 |
| .25 | 11/36=.305556 | 同上 |
| .10 | 11/31=.354839 | 同上 |
| .75 | 11/50=.220000 | 同上 |
| 1.00 | 11/58=.189655 | 同上 |

五种下降倾角都在相同初始原地aim第11路点后停止；J4近当前±.8任务边界、J5靠近0。这是初始转腕/IK可达分支的强线索，不是唯一证明下一点仅J4限位、硬件故障或夹爪碰撞。不能靠改变后续下降角度解决尚未通过的前段。

仅诊断的新几何：当前真实FK指尖→保持原最终捕获点和24mm预抓距离，指尖靠近与q0→原最终朝向同步渐变，不先固定腕位置转到aim。隔离预抓取16点/100%、下降8点/100%；原范围全部通过、最大相邻关节步`.068713rad`和`.028251rad`，未放宽原.35相邻界。预抓q `[-.279960,1.763113,-1.163947,.032109,.616650,-.024066]`，下降终点 `[-.277976,1.863765,-1.166667,.035743,.518717,-.027119]`。这不是实测J5或夹持成功，不发送这些关节值。完整规划不能替代原.08自动前缀、8mm/朝向、反馈/最终真实夹持。

这一反事实尚未应用或获新末段几何同意；已明确向用户提出“原末段同步转向靠近、同捕获点/TF/闭爪/范围不变”确认。只实现已确认的20cm阶段，不隐式修改另一个原策略或再次盲跑原失败路径。首次域78栈按120s退出，新增对照首次无service返回1，不当规划结果；重启同一禁止执行栈完成review0，语法0，随后INT收尾。

运行对照需先sourceROS和两个原overlay、`ROS_DOMAIN_ID=78 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml PYTHONNOUSERSITE=1`，启动上述launcher，再运行：

```bash
python3 /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_terminal_depth_plan.py /home/johnwick/brain_robot_logs/view_guard_20261013/terminal_stage_onekey/visual_stack.log /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place/review_target_directed_geometry /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml
```

## 证据SHA与下一步

- visual_stack.log：`b069cdcff94554a26ce4c4254305a1efa125ed9256ff9bfb4c49339b321790b0`
- terminal_stage_onekey_console.txt：`7e1dbe8fbb87030448f9c1c8196905fb4686b96b428f7dfb9adb9c89246b4794`
- terminal_stage_plan_review.json：`f9c2c3e675ee2d4a47a9f284ee241952dccd4a91533c969e61e227a67ccf2e5d`
- review工具：`8af1f614c0ac70ad70ba90c7160e38365268383eab6a3f4275c8e8c1785e0bcd`

应用构建/73回归通过，新阶段有实体证据，总目标未完成。下一收到末段几何明确同意后，原geometry owner局部实现同步转向靠近、原方法/几何回归、原入口实测；否则保持当前静止使能，不重跑相同25.6%失败或底层/激光。Git仅本地，origin/main待推送历史审查未完成，保留用户原注释和vendor/reference修改。
