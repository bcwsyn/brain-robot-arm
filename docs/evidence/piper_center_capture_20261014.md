# 2026-10-14：质量策略部署与用户批准的最终原RGB中心条件

## 实际部署/无运动启动证据

- 基线8567fac/代码361cb55；host ps无活动控制栈，规范与候选SHA一致，余7.6GB/90%。原actual198f2a5双binary/CPP/CMake/package先备份至 `/home/johnwick/brain_robot_logs/view_guard_20261013/quality_stage_previous_198f2a5/`，再机械同步原source/header及双binary。实际install链接build，新executor27f8b25…/detector27f9059…，原唯一启动脚本87039b…未修改。
- 首个只接收SDK脚本错误将构造参数can_auto_init传给CreateCanBus，TypeError退出且未发送控制；读取当前签名后修正。新SDK epoch1791909991.6484087，高速戳9991.648124/100Hz、joint200Hz，六轴使能true、速度0，q[-.272114284,1.292049792,-.644707172,0,.340199578,0]rad；夹爪99.6mm/使能无错误。CAN ERROR-ACTIVE/1Mbps/.75/queue1000，RX44852563→44855534，error/drop0，复用不重载。
- 用户新增最终必要条件：方块至少部分覆盖原始画面中心；不是方块中心精确重合，不是充分夹持证明。核查FreshFaceInsideJaws已有身份/反馈/三维夹持但没有该中心条件；已明确询问局部实现，用户答“同意补最终中心条件并实测”，随后允许多次纠偏直到可接受。该新局部授权已解决，不重复等待。
- 等此同意期间，先用唯一脚本 `BRAIN_ROBOT_AUTO_START=0 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=.../quality_stage_no_motion timeout -s INT -k 8s 180s /home/johnwick/start_brain_robot_cube_real.sh` 验证部署。仅本轮诊断关闭自动运动，默认AUTO1不变；不按键、不发新六轴目标、不闭爪。到[7/7]、IDLE/WAITING_FOR_START/WAITING_FOR_LEVEL_ALIGN，图像/完整反馈/TF/腕云不写Octomap均有原脚本输出。
- 启动前15s只读采集quality_stage_before_{exact,live} rc124且没有图像：当时相机未运行，不当相机硬件故障、不重试原空流。原脚本启动后18s只读quality_stage_started_{exact,live} rc124，是有界采集结束而非运动错误。exact记录30RGB/30qualifiedBox/15rawpoint/22原子quality/8debug；实时六轴反馈持续、姿态保持。
- 此次原camera_health记录00:50:02/00:50:26两次NO_FRAMES→00:50:44 FRAMES_RECOVERED；使用原恢复、未改驱动/DDS/CAN。不能把最初重复帧当持续新鲜采集，也不能宣称已永久解决相机断流。
- 本轮真实三图已查看 `quality_stage_started_live/evidence/0003_{rgb,depth,debug}.png`。原RGB完整紫色方块在中心左侧，原RGB框stamp1791910226462155437范围[.325,.441667,.45625,.6125]，不覆盖(.5,.5)。注册debug显示目标区域DEPTH_REJECTED_INSUFFICIENT_SAMPLES，不是夹爪在原RGB中把方块遮没。原生depth uint16毫米图直接显示近黑；数值64.0656%非零，213..305mm/非零中位256mm，不能把近黑显示当全帧零深度。
- 新topic已实际收到v1原子质量：stamp1791910281.946483709，qualified0/samples4/coverage.0019608/span.0204197，未用它启动靠近。ros2 param get quality_driven_depth_stage_enabled显示Parameter not set：原ParameterOr/get_parameter_or不declare未覆盖参数，代码fallbacktrue；这不是运行参数被设置成false，更不是实体质量分支已经触发证据。
- unified exec原handle5303返回143时host实际timeout3844587/script3844588仍在，未将handle终止误当进程终止。重新查host并对准确本轮主script3844588发INT，原cleanup日志“未发送DisableArm/完成一键流程已停止”，最终ps无控制/采集栈。新SDK1791910350.843541/high0350.8429244/100Hz，q与初始完全相同，六true/速度0、夹爪99.6mm，未新运动/失能。无运动核验不等于观测到位、质量切换或抓取验收。

## 已批准中心条件的实现范围

原检测器在完整原RGB选中方块轮廓的填充mask中检查中心像素，不使用注册深度网格中心或仅外接矩形；同戳原子观测新增 `color_center_covered`，schema升级v2，既有SEARCH/检测门限保持。该字段独立于深度qualified；深度空洞不能自动抹掉原RGB轮廓证据。

原FreshFaceInsideJaws先核对同一静止方块/新鲜RGB/真实反馈，再等待同一图像戳的中心字段（只在原.6s新鲜度内容纳跨话题投递延迟），覆盖中心才能继续原三维夹持/开口/TF检查。中心只是必要条件，不能替代原最终夹持、到位、反馈或允许错误物体闭爪。

不把中心条件用于粗靠近/途中ObserveLockedTarget，不增加“一看见偏移就停止”的中途硬门。原AutomaticRgbApproach循环原有逐段停稳→真实反馈重规划→新RGB纠偏/完整MoveIt→原8mm/1°与已检查.08rad前缀保持，已经支持多次纠偏；用户允许多次已记录，不将RGB纠偏写成只允许一次，也不据此取消异常即停/无反馈不运动。本次尚未改变独立EnsureRealTopDownLanding中的原有限固定落点校正策略；若本轮真实阻断落在该策略，按新证据再落实已允许的重复纠偏，不提前盲造新的末段运动。

候选executor97b154c09b86aa4cc7008adb0da1de05dc3678f68efe74574852a9ca7fd2c9f5，detector8e763f4062e1626b9150e392282f1600267a9f516d7659914c43ebaecb335971；CPPac99410…/56df03d…，hpp6b6e2e…。完整构建rc0；实际方法39/观测6/尺度15/几何14/视觉10/wiring3=87通过。本节当前中心候选尚未部署。

第一次39方法测试38通过/1失败：缺同帧中心字段的等待正确拒绝后，fixture继续使用已超过.6s的旧RGB测试允许闭爪，日志明确STALE_RGB。仅在该正例提供新的图像/六轴反馈再添加同戳中心记录，不改生产代码/时限；单目标重建rc0/39项rc0。首次center_capture_executor_tests.txt与最终center_capture_executor_verified_tests.txt均保留；6观测/schema测试包括深度不合格仍center true、非法中心字段/旧v1 producer拒绝。原循环多次纠偏的生产helper回归也通过。

Git只读核验origin/main缓存bb99f90与本地8567fac存在分叉（left1/right114），不是仅本轮两提交未推；远端新仿真资源与本地旧树也有差异。没有merge/reset/checkout/force-push或删远端文件。历史推送审查/分叉协调仍另行阻断，不妨碍本轮限定本地提交与已获准实体工作。

隔离域78新v2检测器重放原好/空洞真实帧rc0：12好记录稳定后10合格/12空洞记录全部要求质量切换；两帧原RGB确在中心左侧，color_center_covered均0，不以旧DETECTED或框误授权闭爪。结果 `center_capture_quality_replay/report.json`，未发送实体控制。另原near-depth15/视觉10/几何14与wiring3复测通过；首误写几何可执行名target_directed_grasp_test rc127，核查CMake实际grasp_geometry_test后rc0，无测试修改/弱化。

## 下一动作

读取中心构建及实际方法结果→限定提交（用户wiring/vendor/reference不纳入）→备份当前质量v1双binary/源码、同步v2双程序并SHA确认→新鲜反馈清单→原AUTO1完整视觉一键实测，不用诊断AUTO0代替实际靠近。三图、质量观测、反馈和最早失败日志均需记录。目标仍是实际夹持/闭爪抬升/释放/安全返回后失能，当前尚无新实体抓取证据。Git只本地提交，历史待推送审查未完成。
