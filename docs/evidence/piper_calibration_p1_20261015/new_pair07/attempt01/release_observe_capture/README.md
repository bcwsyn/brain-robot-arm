# 第六位置：原返回成功、A60已存，目标深度0（2026-10-15 19:56 +08:00）

夹持B检查点`8f8eed6`不可变。用户明确授权“允许原位张爪、返回观测并采集”；本页保存实际执行、所有准备失败与A原件，不把授权当成功、不把采满60叫标定完成。按ROS2/PiPER及局部修改技能，仅临时服务编排和离线分析，未改/部署生产代码或新轨迹。

## 实际执行结果

- 原driver `auto_enable=false`、原launch减去grasp executor、原adapter/controller。stop_after_observe=true设置并读回，原enable_srv true同步输出门，六true/q吻合B；首joint_commands逐值等于真实接管反馈，未重演旧J3裁剪跳变。
- `/brain_robot_grasp/gripper_command`一次`gripper=0.100m`，反馈97.1mm满足原3mm到位范围，末99.4mm；不是按29mm闭爪，没有新抓取动作。实际开爪反馈J3/J5有小幅变化，原值不隐藏，也不据此猜方块移动。
- `/visual_search_controller/start`触发原6点/20秒prepare，START→到位19.552954秒，`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`；原2点恒定持位后软件disarm。bag有7300反馈/999关节命令/1夹爪命令/2轨迹，状态仅IDLE→PREPARE→STOPPED，无SEARCH/ALIGN/GRASP。无复位/硬件失能。
- 控制源全部退出再启动原只读A会话：原采集45.729632秒60/60，相机54.275591秒/80；2178反馈、761depth、931Info、219RGB，原9静止未满/48非同帧Info拒绝保留。逐帧q波动0，完整同戳Info、原整数戳、PNG原0、当前工厂CC1365304DG/FK齐全。
- **原RGB方块完整40×40，全部60帧原选中目标深度点0；原完整面候选/好顶面均0**。不自动再补相同条件60帧，不改HSV、深度门或填洞，不执行拟合。所有自有进程已退出；原visual退出0，driver−9和SDK after-enable/到观测整窗rc2在原记录中，不冒称全干净或全静止通过。

## 三次准备失败：代理调用问题，原件不删

1. 临时编排错误要求整6秒SDK静止，几次速度字段脉冲使整窗失败；位置仍全窗0波动，尚无driver/运动服务。
2. 新10秒SDK全窗通过，但误用了较早的临时launch包装器，`node_executable`为str时错误按substitution处理，启动节点前AttributeError，参数服务发现超时。原driver已以auto_enable=false启动，TX增加13，类型未wire解码；bag只有反馈，没有joint_commands/arm_trajectory/gripper_command，没调用Enable/arm/start。不能谎称完全只读TX0。
3. 切回上次成功包装器后，代理额外要求静止窗必须以最新样本结尾，拦住原[1:80]79样本/7.830564秒合格窗。这条临时额外要求已撤销；最终原任意连续窗[24:100]76样本/7.528837秒通过，原全窗失败依然保留。

最终沿用原SDK `summarize`、原3秒/30样本/速度阈值、原限位及所有控制门；没有改SDK/驱动。修正后的launch先用no-op LaunchService.run离线生成/确认移除唯一grasp executor，再执行实体。以上不是CAN断联或用户接口错误证据；没有因此重载链路或重启机械臂。`failed_preparations.json`和压缩原件保留各版本参数/原因；只保存最终临时编排源码，**不把旧版本重构冒充逐字源快照**。

## 20套与深度诊断

`portable_diagnostic20`从原60均匀取20，原像素/哈希不变，每帧实际q、同戳完整Info/FK/本轮工厂数据齐全；50资产SHA核验。它们是**诊断代表帧，不是20个完整面候选或拟合样本**。派生summary标明source60/selected20，原60摘要另存；两侧未知中心仍null，原SDK到观测报告的失败不覆盖逐帧实际反馈。

`quality_all60/report.json`为原判据结果。`footprint_audit`只做离线原R/T射线假设对照：约75.05%的RGB掩膜射线可落在原生D视野，约24.95%在下界外；假设Z=.18—.50m对应的固定7297原生像素诊断并集在60帧均为原始0，背景仍有有效值。因此RGB完整不保证D完整，且仅裁切不足解释全部缺失。**这些Z是假设，不是测得的目标距离，诊断并集也不是确认过的物体足迹**；不能据此断言近距、材质、红外/夹爪遮挡根因，不用安装TF/IK“修出”缺失点。

`audit_depth_footprint.py`可对解出的原A/重建完整便携包在新目录复算；`review_motion_offline.py`只反序列化已关闭bag，不初始化ROS/CAN。`package_offline.py`只离线归档，默认固定原输入/拒覆盖，异机需先解包并明确改路径；不是自动实体运行入口。

## 原件、全六组口径与下一步

`runtime_closed.tar.gz`及`runtime_manifest.json`无损保存170原文件，含A全部60套、成功运动/反馈bag和三准备失败，逐文件/压缩包SHA核验。未删原图/坏帧/0深度，B不覆盖；`executed_sources`是原launch及本轮临时调用源码，生产五SHA与home实际旧adapter保持，候选未部署。A只读CAN TX15662不增、RX增长，根34GB余量，未推送GitHub；216回归通过，运动bag/离线质量/归档分别验证，不混称实物标定或抓取成功。

全六位置[P1_registry.json](../../../../P1_registry.json)直接从各原报告及SHA登记：主要A帧数60/120/28/60/60/60（共388），原好顶面60/0/0/0/0/0。**只有1组满足原图像质量门，原报告正式标定点对批准为0**；此前“完整合格1/6”只指图像门，不是标定验收，不能把六位置有原件叫六合格点对。new_pair07固定留出，不事后改成fit组。

操作者随后明确“始终原位，未被带动或重摆”，释放返回后的物理同点来源已存`same_point_confirmation.json`，派生assessment从null更新true；原图/SDK/bag/归档字节不改。不是凭照片/关节反馈推断物体零移动，也不重复询问。该确认不消除目标0深度/中心未知或批准标定点对。下一只做六组离线深度、可用面、参考点和可辨识性审阅；不重复原位张爪/观测或同条件A60、不回到底层巡检、不拟合null/放宽门/部署TF。若需要新采样姿态/设备setter，须另列具体方案，不自动扩大本组原返回许可。
