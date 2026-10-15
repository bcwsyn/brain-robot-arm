# 已授权原观测返回与棋盘格观测（2026-10-15 22:59 +08:00）

用户已取走方块，并明确“允许”沿已有轨迹回观测、SEARCH前停、只拍棋盘格，不再开闭夹爪。**实际已完成该返回，不再等待同一许可或重复回位。** 本目录不是新的生产入口或已完成的手眼标定。

## 实测结果

- 原driver/adapter/controller、原部署参数，启动前读实际起点；stop_after_observe设置并回读true，原14点50秒轨迹实际49.642581秒，`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`。状态只有IDLE/PREPARE/STOPPED，之后软件disarm/退出，末SDK六轴仍使能、夹爪99.4mm。没有Reset、硬件失能、SEARCH、抓取或夹爪输入。
- [运动bag审计](motion_bag_audit.json)：13236反馈、2483关节命令、2轨迹（14点运动加2点恒定持位）、0夹爪命令，实际六轴/服务/时间戳齐。初末q见[assessment](assessment.json)。原CAN链路复用，TX16015→23480是本次有运动输出，不叫只读；无CAN恢复。
- SDK整窗before/after_enable/at_observation均rc2，原速度脉冲/波动留档；原连续50fresh/4.922秒静止子窗通过，不把整窗称通过或追加尾部新门。收尾driver−9（原限定退出）、MoveIt SIGINT析构−11原日志归档，launch0/bag0，全部自有源已退出。它们不是本次运动阶段失败或链路掉线的证据。
- 控制退出后只读采五RGB-D、同戳深度Info、真实关节/FK与工厂值，相机17.311秒/35秒、逐帧关节波动0，TX23480全窗不增。相机前SDK整窗仍rc2，原连续57fresh/5.632秒静止通过，两者均保留。没有再开闭/使能/运动或设备setter。

## 实际棋盘格画面

[首帧原图](portable/capture/evidence/0001_rgb.png)；[可见角点叠图](corner_diagnostic/1_visible_candidates.png)；[逐帧候选数据](corner_diagnostic/report.json)。

图中下板缘仍在视野外、夹指遮挡下部两侧。OpenCV4.5.4以3×3为种子加LARGER寻找**可见子网格**，五帧均得到63角点（算法顺序9×7），最大同序跨帧包围变化0.543145px，单应RMS0.850686—0.856440px。单应基于未去畸变原图，只是平面候选几何诊断，不是相机标定残差或手眼精度。已查看原图/叠图，不凭found=true宣布准确全局角点。

**9×7不是整板内角点规格，完整行列/全局原点仍未核实。** 单格32mm是操作者报告，未卡尺验证。便携导出里的cube_edge_mm=29是紫块旧元数据，不是棋盘格单格；[独立板定义](board_definition.json)明确区分。五帧只是单姿态可行性证据，未做PnP、内参/手眼拟合或TF部署，没有改原P1的5拟合+1留出协议/验收。部分板并非原则上不能标定，但必须先保证各姿态物理角点编号一致，不能复用任意局部原点。

## 原件、命令与验证

- [19项便携资产与哈希](portable/manifest.json)：五原RGB/uint16深度/同帧Info/源时间戳/实际q/FK/工厂标定/配置；无补深度、未知中心仍null。原始捕获器的new_pair07/held_out旧标签保留，本轮真实角色由board_execution/assessment说明，**不回写原第六A/B或算作新点对**。紫块检测报告的0目标是取走方块后的预期结果，不是棋盘格质量门。
- [52原文件无损归档](runtime_closed.tar.gz)与[逐SHA回读清单](runtime_manifest.json)，含原motion bag、SDK/日志、五RGB-D、采集执行与工厂值；原运行目录未删除。读取归档不需要设备访问。
- [本次调用层](piper_board_return_observe.py)仅复用原控制服务/轨迹；相较旧释放返回包装器，删了张爪段和旧B角度相等要求，取当前SDK起点。实际[原launch包装器](original_observe_launch.py)仅移除抓取executor，不改其他Node/参数。[只读采集原脚本](executed_preview.py)及[本次采集包装器](piper_board_full_observation.py)齐。
- 执行环境沿原三工作区overlay、ROS_DOMAIN_ID=0、ROS_LOCALHOST_ONLY=0、既有fastdds_udp_only.xml；不是新DDS方案。完整argv与PID在execution JSON，路径/源SHA在[runtime_dependencies](runtime_dependencies.json)。全部owned源退出，末使能只是最后新鲜采样值，不是持续监测承诺。
- 5项[纯离线诊断测试](test_board_observation.py)通过，含透视矩形、错误角点和无效输入；[JUnit](junit.xml)。52归档成员/19资产SHA及六生产冻结源SHA全部核验，未部署adapter候选、未修改生产TF/运动源/门/原第六A/B，未推送GitHub。
- 运行源：`/home/johnwick/brain_robot_logs/piper_board_return_observe.c4o22vip`、`new_pair07_preview.615zlhfk`、`piper_board_full_observation.6l7s4vzx`。根盘33GB空余，未删数据。

## 下一步

先核对整板规格及可识别物理原点：可提供完整棋盘格照片/横纵格数，或只调整板使其完整进入当前相机视野，不必再次移动机械臂。然后提出标准棋盘格多姿态手眼的具体采样路径/物理编号方法与验收方案，经批准后执行；本次许可不自动扩大为多姿态运动、开闭夹爪、搜索或TF部署。原方块6组证据及不足继续保留，不静默替换原任务。
