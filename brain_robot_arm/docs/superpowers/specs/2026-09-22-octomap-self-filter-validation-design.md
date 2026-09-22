# Octomap 自体过滤验收设计

## 目标

确保实体 PiPER 的深度点云在进入 MoveIt Octomap 前经过同时间戳 TF 校验，并且启动流程只有在 MoveIt 已发布自体过滤点云后才清除旧地图、放行视觉搜索。

## 方案

1. `pointcloud_tf_gate` 继续负责输入帧的 TF 完整性，不替代 MoveIt 自体过滤。
2. `PointCloudOctomapUpdater` 使用 `/brain_robot_vision/tf_validated_points`，输出 `/brain_robot_vision/filtered_points`；设置队列长度，并采用 PiPER 厂商配置中的碰撞模型膨胀比例，以覆盖深度噪声和手眼标定误差。
3. 启动脚本在清除旧 Octomap 前等待 `/brain_robot_vision/filtered_points` 首帧。等待失败时不建立地图、不进入搜索。

## 验收

- 启动期间能收到 TF 门控 `FORWARDED` 和过滤点云首帧。
- 清图后搜索规划日志不再出现 `<octomap>` 与 `link2` 的起始状态碰撞。
- 若仍出现该碰撞，保留日志并继续检查 MoveIt 运行时加载的机器人模型与过滤插件，而不是放宽碰撞检查。
