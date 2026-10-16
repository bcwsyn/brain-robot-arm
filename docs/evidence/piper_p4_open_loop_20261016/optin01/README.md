# P4 默认关闭开环分支：原入口、原几何、原适配器

基线 `8a90b00`。用户回复“好”批准上一轮明确提出的范围：仅增加默认关闭的P4开环基线，采用已审阅的棋盘格/RGB＋29mm标称尺寸目标，默认闭环、TF、限位和TCP不改。本轮使用 `ros2-piper-debug` 核对真实部署链，按 `surgical-change` 只改该分支及入口接线，保留既有无关脏树。

## 实现

- 唯一入口仍是 `/home/johnwick/start_brain_robot_cube_real.sh`，规范源 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh`，没有新造一键运动程序。
- `BRAIN_ROBOT_P4_OPEN_LOOP=1` 才启用。不设置时原配置和闭环路径不变。目标文件不是任意ROS参数覆盖：launch只读取固定表面点、标称边长、来源，不能覆盖TF、限位、TCP或旧门。
- P4视觉控制器只走原当前反馈姿态→既定观测轨迹，`stop_after_observe=true`，在SEARCH前停止；随后原执行器的显式 `/execute` 启动P4。`LEVEL_ALIGN/GRASP_READY` 不会自动启动这个分支。原FAULT/STOPPED取消和独立急停仍有效；P4显式execute不能清除已收到的急停意图。
- P4执行器：张爪并读反馈→从真实六轴及两指开口构建起点→原共享 `TargetDirectedApproach(..., synchronized_turn=true)`→原MoveIt完整规划预抓取及下降→原关节界限/相邻步长检查→原 `/brain_robot_grasp/arm_trajectory`→原 `piper_jog_adapter.py`→原真实落点确认→原夹爪命令/反馈→原反向靠近路径抬升。
- P4不运行深度交接、RGB微步纠偏、重捕获或末端画面中心/两指视觉判定。这是**获准的独立开环基线**，不是把默认闭环门删除/放宽。关节反馈、规划、自碰撞、适配器、急停及原夹爪反馈仍保留。FK到位或闭爪电机动作不等于物体已夹住。
- 仅P4覆盖 `auto_release_after_lift=false`，抬升反馈完成后停在 `HOLDING`，停止本脚本输出并保持使能，不自动释放、回零或失能，不调用默认完整循环的回零/失能收尾。
- `BRAIN_ROBOT_P4_PLAN_ONLY=1` 是P4预览默认值：从当前反馈姿态规划，不使能、不返回观测、不发抓取段/夹爪命令。原一键设备启动仍是原实现，**不是“不打开CAN/相机”的离线工具**。离线验证用下述域78测试。

## 冻结目标及局限

[frozen_target.yaml](frozen_target.yaml) 由新增只读 `prepare_p4_board_target.py` 导出；复用上一轮5图固定13真实角点/IPPE＋LM/LK报告，不重新拟合手眼、不填深度。目标为 **29mm顶面高度假设** 的RGB轮廓质心射线交点中位数：

`base_link [0.34541558430187874, -0.00938299111853809, 0.044519972883465875] m`。

这是原插入几何的“表面输入”，不是14.5mm几何中心，不重复补半个边长或旧7cm/10.5cm测量。原0.4插入比例/12mm上限得11.6mm插入，指尖偏移0.1358m、24mm预抓取间隙、0.5向下比例均不改。

这是**归档静止场景快照，不是现在重新拍摄的实时测量**。原RGB戳、实际关节快照、review/capture SHA和假设随文件保存。只有方块和支撑物仍未改变时才可用于后续同位置实测，不能无条件长期复用。整块轮廓质心不等于已证明的顶面中心，板平面/32mm尺度、29mm边长及实际TCP仍有误差；这些假设没有变成计量真值。

## 验证分账

本轮没有启动实体PiPER驱动/适配器、没有CAN发送或实机运动，**不是完成抓取**。CMakeCache确认活动源 `/home/johnwick/piper_ws/src/brain_robot_pick_place`，installed执行器链接到home build、launch链接到home source；规范/活动修改源同步，before源及旧二进制保留。

1. Python回归覆盖默认关闭、冻结输入白名单、顶面/中心区分、原启动收尾、适配器及已批准相机TF/内参；最终数量见 [pytest_final.log](pytest_final.log)。Shell语法和限定diff检查通过。
2. 实际执行器定向构建见 [build_final_estop.log](build_final_estop.log)。最初两次配置失败因部署目录缺原CMake已登记的 `test_jaw_scene_review.py` 等测试源、`review_near_depth_policy.cpp`；从规范源只补缺失项后通过，没有关掉测试或改生产配置。
3. 域78启动原模型/界限的MoveIt、RSP及新编译的实际执行器；**无驱动、适配器、Servo、相机或CAN**。归档真实q只作为合成静态测试输入，在隔离域打当前测试戳，不冒充新实机反馈。见 [preview_result.json](preview_result.json)、[nodes.log](nodes.log)、[execution.json](execution.json)。预抓取及下降均完整100%，原界限通过；规划结果20/9轨迹点，最大相邻步长约0.077993/0.033295rad。
4. 首轮规划/零命令通过，但旧 `GRASP_READY` 注入用volatile测试发布者，未匹配原transient-local订阅者，**那轮不能证明旧状态隔离**。原记录保留 `initial_preview_qos_mismatch/`；只修测试发布者匹配原控制器，重测要求匹配订阅者≥1且旧状态不启动P4。没有改生产DDS/QoS。
5. 最终还注入一次隔离测试急停，检查显式execute不能清除它；测试注入与执行器输出分账。不能把注入的 `FAULT_ESTOP` 当成规划或硬件故障。最终原臂轨迹、夹爪、`/joint_commands`输出均为0；急停计数含测试自己发布的1条。
6. MoveIt收尾存在已有SIGINT析构异常，父launch/分析器与子进程退出分别留证，不称所有源优雅退出或物理轨迹失败。末自有测试源全部退出；不重复CAN/USB/J4/手眼采样。

## 使用与回退

以下只是使用说明，本轮**没有执行实机命令**。确认场景快照仍对应当前方块后，预览为：

```bash
BRAIN_ROBOT_P4_OPEN_LOOP=1 \
BRAIN_ROBOT_P4_PLAN_ONLY=1 \
BRAIN_ROBOT_P4_TARGET_CONFIG=/home/johnwick/brain_robot_logs/p4_open_loop_20261016.rK8BhF/frozen_target.yaml \
/home/johnwick/start_brain_robot_cube_real.sh
```

实机使用同一入口，将 `BRAIN_ROBOT_P4_PLAN_ONLY=0`：原观测→张爪→预抓取→下降→闭爪→抬升，停在HOLDING。构建/隔离规划不等于实体分支已执行/夹起；下一步才是一次带真实反馈/画面记录的限定实测，随后仍按同位置3次至少1次夹起验收。

不设置P4环境变量即可恢复默认闭环行为，无需改TF/模型。完整代码回退基线 `8a90b00`，不能 `git reset --hard` 破坏脏树。活动源/旧二进制备份在 `/home/johnwick/brain_robot_logs/p4_open_loop_20261016.rK8BhF/`：`start.before.sh`、`executor.before.cpp`、`executor.before.bin`、`launch.before.py`、`CMakeLists.before.txt`。恢复时同步该源/二进制/入口，**不动**已批准Astra＋mount成对修正。

所有记录仅提交本地Git；共享main既有分叉/历史发布审查未处理，不冒称已推送GitHub。无删除原始数据、无提交构建产物。SHA、源一致性及未变保护项见 [verification.json](verification.json)。

原构建/供应商节点输出含尾随空格，首暂存检查已如实发现；不格式化原始日志来改变哈希。本证据目录的 `.gitattributes` 仅对机器生成的 `*.log` 关闭空白格式检查，源代码/文档检查不变；日志完整文本、字节数和SHA均保留，原析构异常亦未删改。
