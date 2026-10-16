# 原一键P4实机：流程走完，但实际空抓

2026-10-16 21:44 +08:00。代码基线681a715，本轮局部参数修复提交64f878c。用户批准原入口自主实测，仅必要实体操作时叫。本轮**确有运动、闭爪和抬升，但没有夹起方块**；不是只读预览成功，也不是达到最终验收。

## 最新实体结果

仍为唯一原入口 /home/johnwick/start_brain_robot_cube_real.sh，显式BRAIN_ROBOT_AUTO_START=1、BRAIN_ROBOT_P4_OPEN_LOOP=1、BRAIN_ROBOT_P4_PLAN_ONLY=0，目标文件及SHA见[frozen_target.yaml](frozen_target.yaml)、[real_finished.json](real_finished.json)。不是新写一份替代运动脚本，run_real.py只是环境/有界采集包装器。

实际顺序：

    当前姿态 → 原观测轨迹 → OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH
    → 张爪100mm → MoveIt预抓取 → 下降 → 闭爪 → 抬升 → HOLDING保持使能

- 预抓取及下降100%完整规划，20/9点，最大相邻关节步长0.077658/0.033308rad。执行仍经原piper_jog_adapter；不是单独J5点动/基础运动程序。
- 原FK落点期望约[.3477,−.0095,.0329]m，实际约[.3470,−.0099,.0330]m，距离0.9mm、角误差0.0039rad。**同一模型的落点吻合不证明物理夹持区吻合。**
- 原入口rc0，HOLDING后退出控制源，未自动释放/回零/失能。夹爪却闭到约0.4mm，方块仍在板面；故本次为**空抓**。该位置成功计数0，不能以服务success/rc0/HOLDING凑“3次至少1次”。
- [最后原RGB](real_record/0073_rgb.png)、[闭爪前后RGB](real_record/0062_rgb.png)、[开始抬升RGB](real_record/0064_rgb.png)均可直接审阅；[原采集统计](real_record/summary.json)为73快照、24,597,392图片bytes（32MiB上限），实际收到16295原反馈/16291 joint_states、2061六轴命令、7轨迹、2夹爪目标。采集器纯订阅，未发命令。RGB/深度为邻近时间配对；debug按相同RGB戳，均不伪称硬件同步。

## 当前停点：不重复空抓，不失能

[最后被动SDK](final_sdk.json)是本轮停下后的快照：39fresh/3.8127秒、六q波动0/速度0、六轴使能true，夹爪0.4mm。末q约：

    [-.049872396, 1.652784112, -1.009274952, .044953188, .778665272, .088894624] rad

机械臂在抬升/预抓取末位保持使能，不在观测/零位；记录不是永久在线监测。所有本轮实机/隔离控制源已退出。没有DisableArm/ResetPiper/MasterSlaveConfig、固件写入、夹爪标零，未重复发送相同空抓。

[CAN末快照](final_can.json) ERROR-ACTIVE，RX55,450,140/TX53,100，rx/tx errors0，原dropped297保留。链路健康，本轮没有重载CAN/USB。不是再次把夹不到归咎CAN或磁盘。末根分区约56%/33GB可用，共享盘约75%/130GB可用，不需要删本轮证据。

## 首两次失败与局部修复，不能抹掉

1. first_entry_environment_failure：包装器把PYTHONNOUSERSITE=1传原入口，驱动缺用户site中的python-can，硬件控制未启动。原脚本timeout echo收尾也挂住；限定终止自有CLI组后原入口rc130。只修原入口子进程包路径：系统dist-packages优先、既有ROS路径、用户site末尾。实测can/SDK/cv_bridge可导入，NumPy为系统1.21.5；没有pip安装、改全局环境或生产驱动。
2. second_entry_handoff_failure：原脚本到[7/7]后意外SEARCH→ALIGN。调用现有软件急停及adapter disarm成功，TERM原入口rc143；**真实J1/J5运动**：7轨迹/1548关节命令，J1范围[−.143983,.054809]、J5[1.212846,1.220923]rad，其余四轴不变，0夹爪/P4抓取。末J1 .040261rad，不写成“未运动”。
3. 实际参数stop_after_observe=False，而原二进制已有停止分支。根因是launch的/**字典值不敌任务YAML节点限定值，不是原控制器缺快捷分支。64f878c仅在P4时追加节点限定CLI：visual_search_controller:stop_after_observe:=true、grasp_lift_executor:auto_release_after_lift:=false；默认args为空。没有改任务YAML、控制器C++、TF/TCP/限位/adapter。
4. [原完整launch隔离回读](launch_parameter_probe.json)四值为stopTrue/releaseFalse/P4True/previewTrue；域78没有driver/CAN/使能或执行调用，收尾父−9及Servo/MoveIt异常留证，不称优雅退出。随后才做上面的实体完整P4，最终真实SEARCH前停。30项P4/启动测试通过：[JUnit](verification_pytest.xml)，64f878c的git show --check通过。

## 末段偏差和用户提示：分开“事实/假设”

- 本轮先有5对新RGB-D/q/同戳TF及debug。新顶面冻结[.345009256,−.009759589,.044174985]m，SHA9d38a9db…；原工厂内参/32mm板面/29mm标称高度不变。只继承旧13实际角点身份，新像素/三维/q均新采；跨静止会话最大LK位移.199px/FB.00161px，五图PnP RMS约.194～.198px。原SB小子网格失败如实留证，没有采用失败结果。
- [实际落点投影复核](actual_landing_review.json)：静止张爪前残差约0.3～0.4px，闭爪阶段约84px，静止HOLDING仍约57px。投影是固定顶面点经原FK/批准X/K所得；原RGB质心会随视角改变，并不严格代表同一物理点，不能凭此唯一归因TCP。静止末段仍不合，也不能用运动时延单独解释。
- [旧手摆组真实复用](manual_pair_geometry_review.json)：仅用new_pair02与new_pair07的60好A帧、各59fresh B/q；这些是操作者确认夹紧/同点的旧记录。按当前X推回的工具内中心候选分别约[23.20,−12.29,134.94]mm、[12.30,−18.06,131.77]mm，相差12.738mm。它们会吸收相机/FK/手摆偏差；未平均后部署为新TCP。旧B原RGB已审阅，仍假定两天安装未改变；不能当外部精密测量。
- 用户提示“可能只用顶面，应下15mm/或前15mm”：代码确实没有视觉重建体积中心，但原SurfaceInsertion已补min(29×.4,12)=11.6mm，沿最终工具轴，而非直接停顶面。[计算核对](top_reference_and_board_replay_opening_seed.json)的名义最终tip=[.347746,−.009536,.032905]m，比板法线中心候选仅高约3.18mm；**模型自由末端≠实际接触垫中心**仍未验证。下15mm/径向前15mm仅列离线假设，未规划或执行；下15mm后名义板面余量约3.0mm，不能把猜测当实物间隙。
- 额外离线固定ID跟踪没有假装成功：先用尚在返回中的snapshot42失败；改从实际张爪静止snapshot55只成功3帧，到58运动后PnP RMS约4.93px而停，不偷偷重编号/换板原点，未获得末段板位姿证据。首脚本误取最后N条轨迹（含cleanup保持）触发断言，改为按实际P4_DESCENT_EXECUTING事件选择，原物理数据不改。

## 最新用户追加：先解决闭爪过快与接触判断

见[官方资料/本机实现/最小修改提案](gripper_control_review.md)。现有直接0mm、配置1N·m、无开口限速，而且“contact_stop”只要求动过1mm，并未证明接触；不能再称它是力控或物体存在判断。原CAN空闭合93.4→5mm约0.175秒，空载effort也有峰值，见[统计原件](gripper_trace_review_v2.json)。官方0x2A8提供的是协议扭矩effort，不是原始电流；过流位不是接触开关。下一拟原链尺寸预闭合＋开口斜坡＋持续接触候选＋轻保持，**尚未改控制，须按用户“改前先说明并同意”确认局部范围**。生产TF/TCP/限位、默认闭环不解冻，不同时叠加15mm两个补偿。

## 原件、复现和Git边界

[runtime_manifest.json](runtime_manifest.json)列出**886个原件、94,484,710 bytes**，3个分卷共53,963,885 bytes，每卷<25MB，已逐成员解压读取/验证SHA；44个关键原件另作松散文件可直接看。完整首两次失败、原入口/CAN/节点日志、原图、整数戳/实际q/命令、包装器和离线分析都在归档；原目录没有删改。文件内历史绝对路径保留，解包后按manifest路径定位；不用原机器日志盘也能读数据。

仅在新的空目录中解包三个runtime_*.tar.gz；不运行归档中的run_real.py来“看数据”，它是实际运动调用器。离线分析依赖本仓库原FK/板面helper和ROS模型环境，未创建替代运动程序。[final_verification.json](final_verification.json)核对生产源/活动副本一致、除64f878c原launch外均与681a715相同，Astra源/库及executor二进制不变。

Git仅本地提交；既有共享main分叉/积压历史发布审查阻断不变，不强推/重写/自动合并。若要回退64f878c，仅针对该局部launch与对应测试，须避免覆盖其余用户改动；不能把已批准Astra/mount成对修正退掉。下一接手先读本文件和四份规范头部，不原样重试空抓，不重新采9＋1/查CAN，不要求用户重新摆物体来代替代码定位。
