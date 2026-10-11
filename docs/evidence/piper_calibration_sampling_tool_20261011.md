# 无标记标定采样核验工具（2026-10-11）

本工具是只读准备和离线规划，不是第二个一键入口或运动程序。目标仍是校正实际相机与夹持区的对应，再让原抓取链把方块放进实体两指之间。不会求解真实新外参、修改 TF/TCP、调用 adapter 或发实体命令。

## 来源与本轮边界

- 起点提交：`f78badf`。用户最新要求“先自己推进，随后发现问题再修改”；本项目范围内普通可逆代码修改/验证无需再逐项等待。新的实体动作范围仍不从该偏好推断；此前预览4段/20mm已用1段，不重置。
- 工具：`brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_calibration_sampling.py`，SHA-256 `b73e30da282d01b1d6061f82ad60e7df7d7399b535d27880019a6e82e5521464`。
- 复用现 `review_jaw_scene.py` FK、归档真实 MoveIt URDF、实际 `cube_task_real.yaml` 的限位/指尖偏置。起点来自 `piper_markerless_calibration_20261011.json` 的旧静止反馈，明确不是实时关节或使能测量。
- `--plan` 在初始化 ROS 前要求域78，再读取 MoveIt 的 `allow_trajectory_execution=false` 及相同 URDF SHA。只有参数、场景、规划服务和隔离域模型 JointState 心跳；没有执行 action、CAN、关节命令或夹爪服务。
- 五个候选姿态（中心/J4±角度/J5±角度）、八段独立往返及 FK 路径、双轴激励、已知合成变换的方向检查均落 JSON。规划模式完整保存每段 MotionPlanResponse，包括全部点的时间、位置、速度和加速度。部分规划失败/中断保留已完成响应；拒绝覆盖旧输出。
- 这是分析工具的范围/输入检查，不是给原抓取流程新增保护门。生产一键/executor/YAML均未修改或同步；CMake只登记新 pytest，未执行整个工作区构建。

## 复现

先进入唯一规范仓库并按固定提示恢复；以下旧输入只用于离线分析，不能当真机起点：

```bash
cd /mnt/hgfs/ub
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export PIPER_CAL_REVIEW_DIR="$(mktemp -d /home/johnwick/brain_robot_logs/calibration_review.XXXXXX)"
python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_calibration_sampling.py \
  --urdf /home/johnwick/brain_robot_logs/jaw_geometry_20261011_step1/review/move_group.urdf \
  --config /home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml \
  --start-evidence docs/evidence/piper_markerless_calibration_20261011.json \
  --output "$PIPER_CAL_REVIEW_DIR/offline.json"
```

仅当需要验证工具或新的模型/输入时，在隔离环境复用现 `test/review_surface_grasp_plan.launch.py`；不要为了复述旧结论重复规划。source `/opt/ros/humble`、`/home/johnwick/piper_ros/install`、`/home/johnwick/piper_ws/install` 的 `setup.bash`，设 `ROS_DOMAIN_ID=78` 和项目既有 `FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml`。有限时间启动既有 review launch，然后在同一隔离环境给上述工具追加 `--angle-deg 1 --plan`，输出改成新路径。不能在真实默认域运行 `--plan`，不能把生成轨迹转发去执行。

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_sampling.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_jaw_scene_review.py
```

## 实际结果

目录 `/home/johnwick/brain_robot_logs/calibration_tool_20261011.9ghtSu`：

- `offline_6deg.json`：8,804字节，SHA-256 `9114ea228a8d5edc051171ad45bf69d9d1219c5aad602a7f2f5b9520f41fb9ee`，工具返回0。最大模型指尖位移23.739592mm、51点FK离散总弧长165.573793mm；与上轮规划点数不同造成约0.000042mm弧长差，不是实机变化。两轴有向夹角90.000210°，平移系统条件数1.414216；有向角与上条用轴方向不分正负所得89.999790°等价近正交。
- `isolated_1deg.json`：169,959字节，SHA-256 `0f2a36c0941b1590a65338d1714720386f8e7735895a1ebbbd59db09171e9d02`。新工具接入验证返回0，八份完整规划响应均code1/20点；任务限位、六轴按名字映射、起终点对应均通过。不是重试上轮±6°的同一拟合/规划实验，也不构成新的实体授权。最大模型指尖位移3.958357mm，总弧长27.595637mm；整个八段即使单段很小仍超旧累计20mm，未执行。
- 场景world为空、Octomap0，不能证明桌面/环境间隙；70mm开口与全扫掠对照未在新工具执行，不宣称有此证据。旧工具选点结果仍只属旧记录。没有新纹理/深度覆盖采样、实际开口或真实外参。
- 最终37项pytest通过（包含现夹指review）；新增测试覆盖单轴不可解、正确双轴约定、输入/URDF限位、六轴缺失/重排/NaN/错误端点、域0提前拒绝、失败与中断保存部分结果、拒绝覆盖。语法与作用域diff检查通过。
- launch日志 `/home/johnwick/.ros/log/2026-10-11-17-13-02-418101-johnwick-virtual-machine-45368/launch.log`，SHA-256 `e37a53ee23f5265b383210779557faa9e48aa970cfef332b8e0979e5f1a8c176`。55s定时SIGINT返回124；规划完成后MoveIt2.5.9析构exit -11，已知旧相位问题，不转回CAN排查。客户端实际正常返回0，所有隔离节点退出。
- 主机起终保留唯一原37594/PGID37573反馈驱动，未停止/重启它；未读新硬件使能。生产入口/executor/YAML SHA继续为 `e8c9f85c…`/`107ce501…`/`75612194…`。根盘34%、共享盘73%，未触发85%清理规则，未删日志。

完整生成JSON及原始日志留实际日志目录，不提交大型响应；这份来源/结果摘要和工具源码/测试进入规范Git。

## 官方事实和项目推断

[OpenCV 4.5.4手眼标定接口](https://docs.opencv.org/4.5.4/d9/d0c/group__calib3d.html)明确输入gripper→base及target→camera、输出camera→gripper，要求至少两次非平行转动。工具合成检查只验证该坐标约定；不是实际精度承诺。自然纹理+深度替代打印板仍需真实可靠的相机运动估计和未参与拟合的验证数据。

[MoveIt Humble GetMotionPlan定义](https://raw.githubusercontent.com/moveit/moveit_msgs/humble/srv/GetMotionPlan.srv)是规划请求/响应，不能证明执行成功；[场景组件定义](https://raw.githubusercontent.com/moveit/moveit_msgs/humble/msg/PlanningSceneComponents.msg)用命名位标识世界几何/Octomap，代码不用猜数值常量。官方网页本轮遇访问拦截，已核官方仓库定义及安装环境实际调用。

当前未解除的阻断是实际两指投影与现TF/CAD对应不一致、缺少通过独立检验的真实外参。下一项是可靠停稳RGB-D观测及独立验证，不是重复旧26°轮廓扫参、旧敏感拟合、基础CAN检查或出画后盲抓。较大的±6°实体采样未执行；闭爪/抬升/释放未完成。
