# PiPER Servo 启动阻塞解耦设计

## 背景与证据

实体 PiPER 的零点复位和观测姿态由 `visual_search_controller` 发布
`/brain_robot_grasp/arm_trajectory`，再由 `piper_jog_adapter` 转换为
`/joint_commands`。这条固定轨迹不依赖 MoveIt Servo。

现场日志已经证明轨迹完成后的故障发生在调用
`/servo_node/start_servo` 时：服务可发现，客户端请求已发出，但五秒内没有
收到 `std_srvs/srv/Trigger` 响应，控制器因此发布
`SERVO_START_FAILED`。同时 `/piper_moveit_joint_states` 已连续提供完整关节状态，
因此这不是关节反馈缺失或复位轨迹失败。

## 目标

按下 `1` 后，六轴零点复位和观测姿态成功到位时，应直接进入 `SEARCH`，而不能
因旧版 MoveIt Servo 的 `start_servo` / `stop_servo` 生命周期服务没有回包而中断。

## 范围

- 仅针对 `backend=piper` 的真实机械臂启动流程。
- 保留仿真后端现有的 Servo `start/stop` 行为。
- 不改变零点姿态、观测姿态、搜索轨迹、抓取候选、点云或 Octomap 配置。
- 不把 `shape_mask` 的 TF 错误混入本次修改；它将作为后续点云自体过滤任务处理。

## 方案

真实后端把 Servo 视为由启动文件创建并常驻的对齐执行器，而不是固定轨迹的
启动闸门。

1. `PrepareWorker()` 在真实后端执行零点或观测姿态轨迹时，不同步等待
   `/servo_node/stop_servo` 回包。
2. 轨迹反馈达到目标后，不同步等待 `/servo_node/start_servo` 回包；控制器直接
   初始化搜索并发布 `SEARCH` 状态。
3. 对齐阶段仍发布到 `/servo_node/delta_joint_cmds`；Servo 正常工作时，原有
   PiPER 适配器继续转发其输出。若 Servo 后续报告硬停止，保留已有状态监测和故障
   路径。
4. 仅删除真实后端的同步服务依赖。现有停止、复位、急停和适配器失能语义不变。

## 取舍

不采用“服务超时就重启 Servo”：会引入额外进程重启、时序竞争和启动抖动。
也不采用“无限等待服务响应”：已经证明该响应可以永久不返回。直接解除固定轨迹
与生命周期服务的耦合是范围最小、且符合实际数据流的修复。

## 验证标准

在 Ubuntu 实体环境编译并启动后：

1. 按 `1`，控制器必须依次发布复位、观测姿态、`SEARCH`，不能出现
   `SERVO_START_FAILED`。
2. 到达观测姿态后，`/brain_robot_visual_control/state` 必须在有限时间内为
   `SEARCH` 或目标可见时的 `ALIGN`/`GRASP_READY`。
3. 仿真后端的 `start_servo` / `stop_servo` 调用代码仍然保留。
4. 不更改任何点云、Octomap 或抓取行为。
