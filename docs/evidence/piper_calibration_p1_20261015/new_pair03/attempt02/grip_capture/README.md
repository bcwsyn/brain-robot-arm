# 第二组新位置夹持B：纯只读采成（2026-10-15 13:02 +08:00）

操作者在明确“第二位置实际夹紧/方块贴桌/保持不动”的请求后回复“已完成”。本次只运行原被动SDK、原接收式反馈桥及相机/采集器，**没有生产driver、adapter、controller，没有使能/arm或开闭/关节命令**。旧第二组尝试仍封存排除，不复用；本次A尚未采，完整P1仍1/6。

- [portable/manifest.json](portable/manifest.json)：19资产859,964B，五对原RGB/native16位深度、同戳完整Info/整数纳秒戳/实际q、原SDK、现读相机factory、配置、逐帧实际FK及SHA齐全，哈希全通过。原深度0未填补，近距B目标无有效深度不当A失败或捏造中心。
- 原SDK6秒60/59fresh/六轴波动0；索引38有一次J5速度−7mrad/s，使原全窗rc2/失败旗标保持。只认可原连续samples[1:38]37fresh/3.616083s经原summarize通过，不拼散点、不改阈值或原数据。
- q_mdeg=[621,104187,-57624,-7607,37482,15838]；六enabled=true，开口37.1mm/effort原−11不是牛顿。名义边长29mm未卡尺，开口差8.1mm原因未知，不以它否认操作者确认接触、不猜工具内中心。
- 原collect_static_rgbd --duration-s15 --frames5 --settle-s3：五帧/7.165834s/rc0，各帧q与SDK完全相同/波动0，同帧Info9次异戳仍拒绝。已看首末原RGB，紫块在两指之间，底部至画面边缘；B不要求由图像证明接触或准确几何中心，不能把它当远距观测。
- 原factory三GET及内部光学TF现读成功，serial CC1365304DG，完整D→C明确；未改相机安装TF。实际FK与第一组B相比工具原点距离66.184mm、旋转29.398°、工具z轴变化7.773°，只记录位置/倾斜差，不代表两组已足够联合标定或1cm精度达标。工具内方块中心仍null。

正常ifindex10/1Mbps/.75/queue1000/ERROR-ACTIVE复用，RX10277751→10465660，TX8370不变；既有warning=4/passive=9428累计计数保留，不写成全历史0，也未据此重载。根55%/34GB、共享73%/137GB，无删除或设备恢复。所有原命令及实际值见[assessment.json](assessment.json)与原资产。

下一步先提交本B，再确认本次新位置原位张爪、核方块未动，并沿原controller→adapter轨迹回既定观测、SEARCH前止住后采A60帧/至少20好帧。当前没有本次开爪/返回许可，不沿旧attempt许可自动动；生产源码/模型/TF/门/入口全冻结。

收尾：原接收桥90.022s/rc0、4298样本/4258发布/40旧戳抑制，末q仍同本B、六true/37.1mm；报告原样附`readonly_bridge.json`。原RGB/深度均限时90s正常退出，timeout124不等于采集失败；本轮所有采集/相机源已无进程。CAN末RX10675855/TX8370、既有warning/passive计数未增加。无硬件Disable/Reset或生产文件修改；本地Git保存，不声称已上GitHub。
