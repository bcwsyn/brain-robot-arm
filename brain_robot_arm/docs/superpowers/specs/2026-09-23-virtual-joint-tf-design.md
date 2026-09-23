# MoveIt 虚拟关节 TF 补齐设计

## 背景

实体 Astra 相机已经稳定发布深度图、相机内参和原始点云。`pointcloud_tf_gate` 也能以 `base_link` 为参考帧转发点云，但 MoveIt 的 `PointCloudOctomapUpdater` 日志显示其消息过滤目标帧为 `world`，随后没有发布 `/brain_robot_vision/filtered_points`。

当前自定义视觉启动文件启动了 `robot_state_publisher`，但没有启动 PiPER MoveIt 配置中的标准 `static_virtual_joint_tfs.launch.py`。因此虚拟关节对应的 `world -> base_link` TF 没有被按 MoveIt 标准启动流程补齐，导致点云在过滤器的目标帧上无法可靠通过。

## 目标与非目标

目标：

1. 在自定义视觉启动文件中复用 PiPER MoveIt 配置生成的标准虚拟关节 TF。
2. 让 `world -> base_link` 在 MoveIt 点云消息过滤器使用的时间戳上可查询。
3. 使 `/brain_robot_vision/filtered_points` 出现实际消息，从而允许启动脚本建立 Octomap。

非目标：

- 不修改 PiPER SDK、CAN、使能顺序或关节控制代码。
- 不修改 Astra 相机驱动、点云门控逻辑或自体过滤参数。
- 不绕过 TF 门控、自体过滤或 Octomap 安全检查。
- 不额外添加手写的重复 `world -> base_link` 静态变换。

## 方案

在 `piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py` 中：

1. 使用已有的 `MoveItConfigsBuilder` 配置对象调用 `generate_static_virtual_joint_tfs_launch(moveit)`。
2. 将返回的 launch action 加入同一个 `LaunchDescription`，与 `robot_state_publisher`、`pointcloud_tf_gate` 和 `move_group` 一起启动。
3. 保持现有 `base_link` 点云门控参考帧及 MoveIt `octomap_frame: base_link` 配置不变。

这样使用项目已有的标准 MoveIt 机制生成虚拟关节 TF，避免手写固定变换造成重复发布或未来模型变更后失配。

## 数据流

```text
/camera/depth/points
        |
        v
pointcloud_tf_gate  -- 检查 base_link 与机器人链 TF
        |
/brain_robot_vision/tf_validated_points
        |
MoveIt PointCloudOctomapUpdater -- 目标帧 world
        |
/brain_robot_vision/filtered_points
        |
Octomap / Planning Scene
```

虚拟关节 TF 只补齐 `world` 与机器人根部之间的坐标关系，不改变点云数据，也不向 PiPER 发布任何运动命令。

## 验证标准

静态验证：

- Python 启动文件通过语法编译。
- 启动文件包含标准虚拟关节 TF action，且没有新增手写重复 TF。

运行验证：

1. `/camera/depth/points` 持续有消息。
2. `/brain_robot_vision/tf_gate_diagnostic` 出现 `state=FORWARDED`。
3. `tf2_echo world base_link` 能返回变换。
4. `/brain_robot_vision/filtered_points` 在 `best_effort` QoS 下出现实际消息。
5. 启动脚本通过 `[5/7]`，清除旧 Octomap 后进入 `[7/7]`。
6. 在未按下 `1` 前，机械臂不发送视觉运动轨迹。

如果第 4 项仍失败，保留 MoveIt 日志并继续检查具体的 message-filter TF 时间戳，不降低安全门控要求。
