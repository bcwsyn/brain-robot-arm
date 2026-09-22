# PiPER Octomap 自体过滤与 TF 完整性设计

## 问题证据

真实抓取的顶部、左斜侧、右斜侧候选均进入 MoveIt 规划，但全部失败。运行日志在
每次失败前反复报告：

```text
Found a contact between '<octomap>' and 'link2'
Start state appears to be in collision with respect to group arm
Unable to solve the planning problem
```

同一会话还反复出现 `shape_mask Missing transform for shape mesh`。这说明 Octomap
的点云自体过滤没有在点云时间戳下取得完整机器人碰撞网格变换，机械臂自身的点被
当成了环境障碍物。规划器从一个已被污染的起始状态出发，因此候选抓取姿态的数量和
规划时间不是当前瓶颈。

## 目标

让 MoveIt 的 `PointCloudOctomapUpdater` 仅从具有完整、同一时间基准 TF 的 RGB-D
点云更新 Octomap；机器人本体不应成为 Octomap 障碍物，而真实桌面、电脑、支架和
目标以外的物体必须继续参与碰撞检查。

## 不在本次范围内

- 不修改抓取候选、IK 目标、关节限位或搜索策略。
- 不允许 `<octomap>` 与任意机械臂连杆的碰撞。
- 不通过缩小机器人碰撞模型或静态裁剪相机近处区域来绕过问题。
- 不假设相机外参数值；物理安装变换必须由当前运行时 TF 测量后确定。

## 方案

### 1. 运行时 TF 合约

以每帧 `/camera/depth/points` 的 `header.frame_id` 和 `header.stamp` 为准，验证：

```text
base_link -> point-cloud frame
base_link -> link2
base_link -> gripper_base
```

以及机器人模型中全部参与碰撞的连杆变换。验证的时间必须使用点云的时间戳，而不是
“最新可用”变换。若任一变换缺失，该帧不能被视为可用于地图更新。

### 2. 相机安装 TF 修复

现有启动文件只静态发布 `gripper_base -> camera_link`。实现时先将实际点云帧与
Astra 驱动发布的 frame 树进行核对：

- 若驱动已经发布 `camera_link -> depth optical frame`，仅保留一条无重复的
  `gripper_base -> camera_link` 静态变换。
- 若驱动没有发布该子链，补齐从 `camera_link` 到实际点云帧的静态变换；具体平移、
  旋转使用实测/驱动值，不能凭空写入。
- 不新增第二个相同 child frame 的静态发布者。

### 3. 地图输入门控和旧地图清除

启动流程在宣告“碰撞地图可用”前，必须观察到连续有效的自体过滤点云，并检查
MoveIt 日志不再出现 `shape_mask Missing transform`。检测到缺失变换时，控制状态只
报告地图未就绪，不能允许基于该地图的搜索或抓取规划。

修复 TF 后调用 MoveIt 的 `clear_octomap` 服务清除旧会话中错误写入的机器人点，
再从有效点云重建地图。清图只发生在会话初始化/修复后的重新建图阶段，不在运行中
反复清除真实障碍物。

### 4. 参数调优顺序

仅在自体过滤正确后，才用 `padding_offset` 和 `padding_scale` 做保守余量调节。
初始保留当前 `padding_offset: 0.03`、`padding_scale: 1.0`，以避免把参数调节误当成
TF 修复；根据过滤后的点云和碰撞结果再调整。

## 修改位置

- `piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py`：修正或
  条件化相机安装 TF，并把地图就绪检查接入启动顺序。
- `piper_ws/src/brain_robot_ball_pick/config/sensors_3d_real.yaml`：仅在验证后调整
  自体过滤余量或调试输出参数。
- 必要时在现有 `active_scan_supervisor` 中增加只读的 TF/点云有效性诊断；该节点不
  发布任何机械臂命令。

## 验证标准

1. `/camera/depth/points` 的每个被接受帧都可在其 `header.stamp` 查询完整 TF 链。
2. `visual_stack.log` 不再出现 `shape_mask Missing transform`。
3. 清图、重新建图后，观测姿态下日志不再出现 `<octomap>` 与 `link2` 碰撞。
4. 真实桌面或电脑实际位于路径上时，规划仍因 Octomap 碰撞被拒绝。
5. 至少有一个抓取候选能越过“起始状态碰撞”阶段；是否成功抓取需单独以实际轨迹和
   夹爪反馈验证，不能由构建成功替代。
