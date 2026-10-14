# brain_robot_pick_place

> Latest independent simulation / 最新独立仿真: [中文复现指南](../../../docs/simulation/README.zh-CN.md) · [English guide](../../../docs/simulation/README.en.md). The historical instructions below are retained as reference; use the new simulation/ entry points for Stage 3. 下方保留历史说明，第三阶段以新指南为准。

> 本包已作为仿真副本分类导入。以下为上游历史说明，旧安装路径和真机模板不适用于本副本；当前构建与验证以 [仿真工作区 README](../../README.md) 为准。此副本排除实体适配器与配置，拒绝物理后端。尚未在本机运行。

PiPER 固定场景护理取物演示的独立 ROS2 Humble 包。当前第一阶段包含护理桌、圆柱杯、Gazebo 杯子位姿插件、MoveIt2 碰撞场景同步和重置接口；所有节点都要求 `simulation_only=true`。

当前坐标约定为：机械臂保持原点，桌面上表面是 `z=0`，桌面从机械臂所在短边中点向 `+X` 延伸。Gazebo 地面位于 `z=-0.25 m`，杯子中心位于 `(0.40, -0.12, 0.05) m`。

## Ubuntu 一键安装

确认共享文件夹已经挂载后执行：

```bash
bash /mnt/hgfs/ub/brain_robot_arm/scripts/install_piper_pick_place.sh
```

安装脚本会把包复制到 Ubuntu 本地再编译，并更新 `~/start_piper_sim.sh`。如果需要手动构建，则执行：

## 手动构建

```bash
cd ~/piper_ws
source /opt/ros/humble/setup.bash
source ~/piper_ros/install/setup.bash
colcon build --symlink-install --packages-select brain_robot_pick_place
source install/setup.bash
```

自动搜索使用 ROS2 Humble 的 MoveIt Servo。如果系统尚未安装，先执行：

```bash
sudo apt update
sudo apt install ros-humble-moveit-servo
```

## 一键视觉搜索仿真

安装完成后只需一个终端：

```bash
bash ~/start_brain_robot_demo.sh
```

全部窗口就绪后，脚本默认不授权机械臂运动。在当前终端按 `s`，机械臂先进入 J2/J3 抬高、J5 向下俯视的观察位；随后 J1 在 `-0.98～+0.98 rad`、J5 在 `-0.60～+0.95 rad` 范围内分阶段搜索，J4/J6 同时保持画面水平。识别到红杯后先居中并接近到 `0.18 m`，然后把相机光轴调到与桌面平行、把杯子保持在画面 `(320,160)` 附近，再以不超过 `0.005 m/s` 的速度接近到 `0.08 m`。最后自动闭合夹爪、在 MoveIt2 中附着杯子、竖直抬升 `0.10 m` 并停在 `HOLDING`，本阶段不转移和放置。按 `x` 可立即停止运动，按一次 `Ctrl+C` 统一关闭仿真、MoveIt2、视觉节点和显示窗口。

当前观察位、搜索范围和控制符号仅为 Gazebo 参数，位于 `config/visual_search_sim.yaml`。`config/visual_search_piper_gemini2.yaml` 是实体接口模板，默认同时关闭运动许可和观察位标定，不能直接控制实体 PiPER。

运行时可查看两条状态：`/brain_robot_visual_control/state` 表示搜索、水平调整和最终接近阶段；`/brain_robot_grasp/state` 表示开爪、闭爪、抬升和保持阶段。自动抓取只在仿真配置中启用，实体配置中的抓取执行器仍由 `simulation_only=false`、`auto_execute=false` 双重锁定。

## 启动场景

先运行已经验证过的 `~/start_piper_sim.sh`，等 Gazebo 和 RViz2 都出现后，在新终端执行：

```bash
cd ~/piper_ws
source /opt/ros/humble/setup.bash
source ~/piper_ros/install/setup.bash
source install/setup.bash
ros2 launch brain_robot_pick_place scene.launch.py
```

重置桌子和杯子：

```bash
ros2 service call /brain_robot_pick_place/reset_scene std_srvs/srv/Trigger "{}"
```

## PREGRASP 分段测试

保持 Gazebo、MoveIt2/RViz2 和 `scene.launch.py` 三者运行。第一次只规划、不运动：

```bash
ros2 launch brain_robot_pick_place pregrasp.launch.py
```

直接运行仿真完整取放（从当前关节状态开始，不要求回零）：

```bash
ros2 launch brain_robot_pick_place pick_place.launch.py
```

只有在终端显示 `Pregrasp plan succeeded`，并确认目标坐标合理后，才允许在仿真中执行：

```bash
ros2 launch brain_robot_pick_place pregrasp.launch.py execute:=true
```

`pregrasp.launch.py` 仍要求机械臂六个关节接近 SRDF 的 `zero` 状态；偏差超过 `0.08 rad` 时会拒绝规划。`pick_place.launch.py` 是独立的仿真执行入口，从当前关节状态开始，依次执行打开夹爪、预抓取、靠近、夹紧、抬升、转移、放置、松爪和撤离；任何阶段失败都会立即停止。

## RViz2 轨迹显示

完整取放入口会向 `/display_planned_path` 发布每一段机械臂动画，并向
`/brain_robot_pick_place/trajectory_marker` 发布持续保留的彩色夹爪路径。在 RViz2 的
Displays 面板选择 `Add`，再从 `By topic` 中添加 `trajectory_marker` 对应的 Marker；原有
MotionPlanning 显示负责播放 `/display_planned_path`。每次重新运行完整取放时会自动清空上一轮彩色路径。
