# 从零复核当前抓取断点（只规划、不运动）

后续实体验证已执行79点预抓取+9点末段+5点纠偏，但原始RGB方块移出下边缘，闭爪门拒绝；见`aligned_real_run.txt`、`aligned_real_image_trace.csv`与本日交接最新首节。用户确认夹持时物体应可见，因此下列模型规划不能证明实体方向/落点正确；不盲重发历史关节解。

先读规范仓库四份任务/交接/进度/决策文档和 `docs/PIper_HANDOFF_20261010.md`。
历史 `settled_fix` 成功靠近/下降，不等于正确实体落点或抓取完成；18:19实体复跑使用新外参，预置姿态全部IK -31。两组证据不要混用。

本目录的 `locked_grasp_snapshot.json` 将原 `/tmp` 中关节快照与日志锁定点保存进Git；点坐标为日志四舍五入值，不是外部标定。假设模型夹爪开口50mm仅用于离线模型自碰撞，不能把真实102.1mm反馈解释为已张开。新的复核不再需要原observer文件。

## 环境与命令

需要 ROS2 Humble、对应PiPER URDF/SRDF/MoveIt配置、Pilz规划器，以及本仓库的 `brain_robot_pick_place`/`brain_robot_ball_pick`；先完成部署并构建。其他机器将下列安装空间与UDP配置路径替换为当地的部署路径；不要换用备用实体YAML。

```bash
cd /mnt/hgfs/ub
source /opt/ros/humble/setup.bash
source /home/johnwick/piper_ros/install/setup.bash
source /home/johnwick/piper_ws/install/setup.bash
export ROS_DOMAIN_ID=78
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml
ros2 launch /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_surface_grasp_plan.launch.py
```

在第二个终端source同样三个安装空间、设置相同两个环境变量，然后：

```bash
ros2 param get /move_group allow_trajectory_execution
# 必须为False，且此测试域没有实体驱动/适配器/Servo/抓取执行器。
python3 /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_surface_grasp_plan.py \
  --config /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml \
  --snapshot /mnt/hgfs/ub/docs/evidence/piper_onekey_20261010/locked_grasp_snapshot.json \
  --orientation measured
```

工具只发布域78的历史 `/joint_states`，只调用FK/规划/笛卡尔服务；不创建轨迹执行客户端、不发布 `/joint_commands`。域非78直接拒绝。不要将历史快照转发到实体域。

本次返回0：Pilz PTP 79点 + Cartesian 9点，fraction=1.0，原六轴包络/相邻跳变检查通过；1mm/0.01rad目标约束，末段姿态固定，夹入12mm。输出见 `measured_orientation_moveit_result.txt`。FK约2.25e-9m仅为模型数学一致性。PTP的中间姿态不等于全过程姿态严格不变；没有测量桌面/外界碰撞模型，也没有真实夹爪开合验证。

## 当前实现与下一步

唯一实体YAML启用 `preserve_aligned_grasp_orientation=true`。执行器仍走原预抓取+末段规划/适配器，冻结对齐时末端四元数，两个目标都使用它；不枚举预置yaw/tilt，不在运动中追逐图像。其他profile默认false，历史逻辑保留。`TOP_DOWN_*`仍是原状态/函数名称，需用新增 `ALIGNED_ORIENTATION_LOCKED_FIXED_APPROACH` 判断实际策略。

本轮仅构建/规划/测试，无新实机轨迹。夹爪102.1mm不合法/基准未确认；当前末段的“新鲜面点在夹持区”门还未实体验证。按现有镜头到指尖YZ测量，最终表面点接近两指时可能已在深度视野下方之外，因此不能把丢失目标当作重新搜索理由，也不能直接删除闭爪门伪造成功；下一步针对该几何/可见性检查，以及夹爪反馈解码/实体响应。

离线检查完成后关闭测试launch并确认其子进程退出。MoveIt2.5.9已知SIGINT析构-11与规划结果分开记录，不据此声称实体CAN断联。
