# 中心目标与温和闭爪：实现、部署及隔离验证

2026-10-16 22:21 +08。基线`bdfc3cc`，用户“好的”批准组合局部范围。**已实现/部署，未进行新实机运动，也未完成真实抓取。** 最近实物仍为[上一轮空抓](../attempt01/README.md)。使用ROS2/PiPER技能核真实运行路径和参数，手术式技能保留无关脏改、只修改原链行为所有者。

## 修改范围

- 仍为原`/home/johnwick/start_brain_robot_cube_real.sh`、原launch/MoveIt/executor/adapter/driver；没有另写运动入口。默认P4关闭、原闭环不变。
- 新只读`prepare_p4_center_target.py`消费已有多点面/方形中心拟合报告，用每帧实际q/批准X转base。显式`p4_cube_center_v1`/`target_kind=cube_center`/`center_base_m`/`grasp_center_tool_m`，中心路径使`t=C−R*c_G`，不再把中心当表面追加11.6mm。原surface格式保留。
- `new_pair02`单夹持参考候选用于隔离历史fixture；`new_pair07`留出禁止作参考。不平均TCP、不写生产外参、不把旧场景坐标作当前目标。现有五弱深度帧不能提供有效实测面中心；没有填洞造点。
- 只在P4缓闭：保守尺寸上界预闭合，参考10→3mm/s、超前实际≤0.5mm；29mm方块参考下界25mm，空夹不追0。持续扭矩增量/开口停止/尺寸区间共同形成接触候选，未确认不抬升。初值0.5N·m/增量0.12N·m/持续0.25s均未实机验证，**不是指尖牛顿/杯子安全保证**；预闭合界`sqrt(3)*edge+6mm`是宽松界，不是精确相机投影尺寸。
- 新`/piper/gripper_feedback`只在真实CAN夹爪帧到来时带戳发布开口/effort，`/piper/gripper_status`传原状态位，避免旧聚合缓存周期重戳。P4首次原握手0x02→0x01保留，位置使用实测当前开口而非0；未零点标定/刷固件/执行MasterSlaveConfig或ResetPiper。实际原入口auto_enable=false，经adapter的joint_callback路径生效；不声称所有驱动替代回调都已重构。
- 生产相机TF、TCP、六轴限位、检测YAML、task YAML、adapter、Astra源/库和物理模型未改，腕部Octomap保持断开；下15/前15mm均未采用。

## 验证结果

[最终部署/测试汇总](raw/final_verification.json)，[准确安装路径补充](final_install_audit.json)。驱动实际模块位于`/home/johnwick/piper_ros/build/piper/piper/piper_ctrl_single_node.py`，与src同inode；初汇总中猜测的`install/.../site-packages`路径不存在，以补充审计为准。执行器installed解析到build产物SHA`eadc13348f060facf13f40e96b1f0022e33868756160263c1dd6e751c9d47f81`。

- 45定向Python、136回归、6新C++、14规范旧几何通过，共201项不同测试。另13安装旧几何为重叠回查，不累加。最终45项有普通只读沙箱pytest缓存警告，不影响结果。
- [实际执行器中心预览](raw/preview_center_01/preview_result.json)：域78、无driver/adapter/CAN/相机；原模型预抓取/下降100%，22/7点。臂/夹爪/关节输出0，测试急停1且拒绝重开。该预览在最终fresh-feedback小修前构建进行，几何不变；最终二进制完整回路见下面。
- [最终空爪回路](raw/v5_loopback_empty/result.json)：真实执行器＋明确合成反馈，2条臂轨迹/744条夹爪参考仅域78，开口至25mm后FAULT，无抬升。
- [最终模拟接触回路](raw/v5_loopback_object/result.json)：3条隔离臂轨迹/552条夹爪参考，模拟开口停37mm＋持续effort后LIFTING/HOLDING。两个回路无adapter、`/joint_commands=0`，fixture直接注入轨迹末角，**不是物理仿真、真实执行精度、接触力或实物抓取成功**。
- 两回路均记录实际反馈参数为`/piper/gripper_feedback`与实际订阅图，开始/结束二进制SHA一致，父进程rc0且无强杀。[最终回路执行记录](raw/v5_loopback_execution.json)。全部自有源已退出。

主要命令为ROS原环境下：

```bash
cmake --build /home/johnwick/piper_ws/build/brain_robot_pick_place --target grasp_lift_executor -j1
cmake --install /home/johnwick/piper_ws/build/brain_robot_pick_place
# Python测试路径及全部JUnit见raw/*pytest.xml，C++见raw/*geometry.xml/installed_center_gentle.xml
P4_TEST_RUN_TAG=v5_ /usr/bin/python3 /home/johnwick/brain_robot_logs/p4_center_gentle_20261016.nR3gYk/run_loopback.py
```

回路脚本强制域78，只有原规划场景与实际执行器＋合成节点；原始脚本和参数均归档，不得把它改为domain0用于实机。

## 失败也保留

- 中心导出第一次CLI漏原FK helper，后新增显式tools-dir/原工具目录查找，成功历史导出见`raw/HISTORICAL_center_fixture.yaml`，**不可直接用作实机当前目标**。
- 初次CMake多目标命令中执行器已成功，但新test target报无规则rc2，原`raw/deployment.json`仍记该失败；随后独立构建/安装/测试成功。实际BUILD_TESTING=ON，不将失败归因“测试关闭”。
- `raw/loopback_empty`首次在构建链接窗口启动，执行器文件暂时缺失，节点rc1/fixture未就绪；修测试启动顺序，最终测试记录前后SHA一致。
- v2/v3开爪前后NaN；v4回读实际参数证明仍订阅旧`/joint_states_feedback`，未发布动作。仅CLI新参数覆盖不足，补P4字典键后v5成功；不是实机CAN或DDS故障。无参数调宽绕过。测试工具经历了这些局部迭代，保留各结果不回写旧成功。

原始日志扩展名改为`.txt`以避开Git忽略，字节不清洗；[manifest](manifest.json)列66原件SHA/路径。编译ELF和旧执行器仅home，不入Git。之后安装审计另存，不篡改初始原报告。

## 当前真正剩余的几何问题与下一步

[同图核对JSON](raw/manual_projection/report.json)、[02叠图](raw/manual_projection/new_pair02_overlay.png)、[07验证叠图](raw/manual_projection/new_pair07_overlay.png)实际使用已夹紧B原图。当前批准X＋“旧安装相同”假设下：02推回c_G投影`[235.245,175.005]px`，但方块可见轮廓质心约`[170.390,200.688]px`，候选点在轮廓外27.90px；同02候选在07原图也外25.73px。名义自由tip同样不一致。

这说明不能把该历史c_G当验证过的实际夹持区；原图下沿裁切，可见质心不是完整三维中心，不据像素距离直接给毫米补偿。此检查尚不能唯一分辨旧相机安装变化、FK或参考点偏差，不擅改已批准X，不用留出挑参数。**完整规划通过≠物理夹得住。** 下一先核当前原图/姿态和真实夹持参考，再独立实测缓闭，随后用当前有效中心在原入口复测；不再原样空抓或重复CAN/9＋1。当前不需要用户重摆/重启，必要实体操作才询问。

## 回退与实体状态

新行为只在原入口P4开启；P4关闭时不走中心/缓闭分支，新driver参数默认false。源级回退以`bdfc3cc`和home `before/`精确备份为准，只恢复本次12个任务源/测试路径，保留其他脏改；执行器还原需配套原头文件/原launch/driver/入口并重建，不把单个旧二进制与新源混称已回退。旧二进制位于`/home/johnwick/brain_robot_logs/p4_center_gentle_20261016.nR3gYk/before/grasp_lift_executor.bin`，本轮没有执行回退。

本轮0实体运动/开闭/使能/失能/复位、0CAN/相机操作。上一轮末状态是使能保持，但本轮未采实体反馈，不称实时状态。没有删除材料或推送远端；既有main分叉/积压历史发布审查保持，Git仅本地。
