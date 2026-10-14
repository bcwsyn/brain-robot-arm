# 阶段1真实静止空跑通过（2026-10-14 22:36 +08:00）

这是用户批准的受限CAN激活和只读采集结果，不是新正式标定点对或抓取成功。前次失败/软件检查点仍保留；本包没有配对人工夹紧的几何中心，所有相关确认字段保持false/null。

## 实际动作与结果

1. 当前已枚举can0索引6/STOPPED/DOWN；sudo -n权限检查通过。仅执行 `ip link set can0 type can bitrate 1000000 sample-point 0.75`、`txqueuelen 1000`、`up`。未重载USB/驱动、刷写/查询固件、MasterSlaveConfig、ResetPiper、使能/失能/运动/夹爪。激活后ERROR-ACTIVE，RX从0→53→568952→1396189，TX始终0，错误/丢包0。
2. 新只读桥90秒，真实发布4271条JointState，抑制33条陈旧/重复输入，error=null/rc0。SDK和ROS都保留原 `.017444` 换算及SDK接收时间约定；不把浮点SDK戳冒称硬件逐电机精确时间。
3. 原相机组件：CC1365304DG，RGB320×240/5Hz、depth640×400/30Hz/mm。SDK60样本/57新鲜，静止窗5.743972秒、六轴毫度波动全0、速度0。该窗口q_mdeg为[-8000,-119,-2161,3433,25200,-4330]，对应q_rad[-.139552,-.002075836,-.037696484,.059885252,.4395888,-.07553252]。真实低速反馈六轴enable=false、夹爪101.5mm；没有代理失能/闭爪命令。
4. 原静止采集器 `--duration-s 15 --frames 5 --settle-s 3` 实际5.642610秒/rc0/5帧。收到feedback271、RGB29、depth117、Info145；12个未静止/5个不同戳Info被原规则拒绝。五帧q波动0，depth与Info整数纳秒戳逐帧相同，完整K/D/R/P/ROI、原RGB/native16位深度、实际关节和时间差均保存。未改变同步/新鲜度阈值。
5. 只读查询三个工厂服务及相机内部 `camera_link←camera_depth_optical_frame`：当前序列号、K/D/工厂D→C R/t、原float参数、内部TF完整保存。内部TF取相机内最新固定几何，不冒称图戳机器人安装TF。采集方法源码在 `capture_factory_metadata.py`，没有机械臂接口。
6. 完整导出当前实际安装模型FK/URDF哈希/task配置快照；19资产951685B，加manifest自身。首次导出在colcon安装task符号链接被拒绝，失败目录留home；仅已知task输入解析真实路径复制，新包重导rc0/哈希全通过，原图/SDK链接拒绝不放宽。新针对性回归及原五组共 **120 passed/0 skipped/rc0**。

## 证据入口

- `portable/manifest.json`：19资产SHA和相对路径，sample_id=`stage1_stationary_dry_run_20261014`，非正式pair。manifest SHA `d3787a2334a7e083fac639fc4f3f323a910cf0c5f26de7002f7d59ecda84ab78`。
- `portable/stationary_rgbd/observer.jsonl`、`evidence/*.png`：五帧同戳深度Info/配对RGB/真实关节，原PNG保持。
- `portable/sdk_samples.json`、`sdk_review.json`：完整原SDK、逐样本新鲜度和实际模型FK；原始开始3个未初始化样本保留但不当真实零位。
- `portable/calibration.json`、`camera_factory_current.json`、`robot_task_config_snapshot.yaml`、`depth_review.json`：工厂参数/内部TF、当前配置及每帧真实FK。原生产安装TF未修改，几何中心/接触仍未确认。
- `readonly_bridge.json`：实际遥测计数、最后真实样本；SHA `b7dbd2f5c0edcb62731b62a90ea86b6539d7e22b1414ad7258c3ae8c8257772d`。

五帧都有高支撑，表面深度330—331mm只是可见面，不是cube中心，也不是20合格帧要求已满足。桥整个90秒末段J3读数为-1942mdeg，与前述六秒/五图窗口不同，**不宣称整段90秒静止，不跨窗口拼q和图**。未使能状态下是否受外力/重力影响未诊断；各阶段使用各自新鲜数据。

本轮相机/桥/采集器全部退出，原用户detector/debug viewer保留；CAN仍UP且RX持续增长，未自动失能。五个冻结生产文件SHA不变，根54%/35G、共享72%/141G未触发清理。home目录 `/home/johnwick/brain_robot_logs/calibration_stage1_activated_20261014.kfNDAQ` 保留完整日志和首个失败导出，不将其整体入Git。

## 下一步（阶段2→3）

阶段1只证明能采完整真实数据包，不能替代正式同点配对。接下来操作者准备同一个名义29mm方块、六个不共线位置与可辨识夹持倾角；五拟合/一预留验证。操作者在支撑条件下实际夹紧/确认接触并采B，再释放原位，按组授权原回观测/SEARCH前停止，采A的60帧目标/至少20高支撑。首个有效组计入六组，历史pair01和本静止空跑均不计。当前没有回观测、使能、开闭或搜索抓取许可，不自动实施。
