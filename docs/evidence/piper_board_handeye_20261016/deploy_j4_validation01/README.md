# 候选已部署；J4规划通过，实机往返尚未开始（2026-10-16 12:19 +08）

用户明确“确认”上一轮提出的具体候选部署（含fef28d6接管与c6d35ec推进修复）及限定原J4往返，不继续其他姿态/搜索/抓取。使用repo的ros2-piper-debug/surgical-change技能核对实际路径、限定变更并保存回退；本轮未修改生产源码或参数，未推送。

## 已完成

- 实际部署`/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py`已由旧`a5074c61…`替换为批准候选`5c1c1be24b4519705ae1e58a31e26085a9c1832cdd7626e93f6c6392b621a172`。安装执行文件是指向该源文件的symlink，无需另外构建覆盖。原版完整保留在本目录`piper_jog_adapter.before.py`及runtime同名文件，旧SHA逐字节核对。
- 当前can0最初STOPPED/DOWN/RX0/TX0，非上轮健康链路。sudo免密成功后，仅配置已有接口1Mbps/sample-point .75/txqueuelen1000/UP；ERROR-ACTIVE/RX增长即复用，没有USB/模块重载、刷写、MasterSlaveConfig或Reset。
- 原被动SDK工具采6秒及有区别的最多10秒窗，分别58/99 fresh；六轴角度波动均0、六true、夹爪99.6mm。实测q_mdeg为`[-8038,54525,-72724,0,69717,5238]`。速度偶发脉冲使原`速度≤1mrad/s + 角度波动≤.001rad + ≥3秒/30样本`条件未通过；按原summarize检查连续子窗最长分别22样本/2.1067秒、28样本/2.7106秒，不能拿最后速度0或角度恒定冒充通过。数据与判断在`assessment.json`，原帧不删。
- 为完成不受影响的部署验证，只启动原driver(auto_enable=false)、从原launch原样选出的模型/MoveIt/adapter。候选确实启动且motion_enabled=false/未arm；回读原max_velocity=.189、timeout25、command窗.2、start tolerance .1及原六轴范围。原URDF SHA0b41516e…不变。
- 从本次真实q以原MoveIt服务规划J4相对+6°与返回当前起点，两条都完整通过原checked_trajectory/状态检查。原ROS角度3秒静止也通过，但**不用于替代失败的SDK速度条件**。场景无实体world/Octomap不证明物理桌面间隙；没有将规划发布给适配器。

## 实测边界与阻断

**没有执行J4往返。** 没有调用enable_srv、enable_motion、arm、运动轨迹、夹爪、硬件失能/复位；没有启动相机或抓取。录包148条`joint_states_feedback`，0条`joint_commands`，轨迹/夹爪输入没有出现，按零计；原driver初始化使CAN TX增加13，不能声称本轮完全TX0。两条规划响应不当实体执行成功，板采样仍2/10，未新手眼拟合或部署TF。

所有自有源已退出：bag0、原nodes0；driver超过原2秒退出宽限后−9，保留日志，不称全部优雅退出。末次独立进程核对无相关控制源；CAN仍ERROR-ACTIVE/RX增长。六true/99.6mm是本轮SDK采集时所见，不当作之后持续监测。没有自动失能。

速度脉冲的物理/解析原因**尚未确定**，不能根据角度恒定就归责硬件故障、操作者或CAN失联。未修改原静止函数、阈值或添加生产门。两个有界窗后不再同条件反复开会话；下一只读核对速度反馈字段、时间和角度的对应关系，明确原因/适用判据后再继续已批准的限定J4测试。**该部署及限定动作许可已经取得，不要求用户重复批准、重启或恢复接口。** 不自动继续板其余姿态。

## 文件与回退

本目录可直接审阅`authorization.json`、两份SDK原始JSON、`runtime_verification.json`完整两条规划/实际参数、`assessment.json`、验证调用代码及旧版备份。`runtime_originals.tar.gz`约37KB包含16个原文件（日志、SQLite录包、完整调用代码等），由`runtime_manifest.json`逐项SHA回读通过；无图像清理/删除。根盘34GB可用，无清理必要。原板attempt01/旧方块数据字节不变。

如需要回退，仅在确认无控制进程运行时执行：

```bash
cp -p /mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/deploy_j4_validation01/piper_jog_adapter.before.py /home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py
sha256sum /home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py
```

应得旧SHA`a5074c614fcc1b7f57854e2693e689337577567dde0ca7765470df52fa1347d8`。回退文件不启动节点/使能/运动。当前**没有回退**：保留用户已批准的候选部署，候选启动正常，当前阻断是运动前速度静止判据，不是已证明候选运行错误。
