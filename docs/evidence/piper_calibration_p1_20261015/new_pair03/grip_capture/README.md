# P1第二组new_pair03：夹持侧B检查点

2026-10-15 12:10 +08:00。操作者回复“我已按照要求完成”，对应上一轮要求的新位置、改变倾斜、实际夹紧。只读记录完成，尚未张爪/回观测，P1完整配对仍1/6，不记作2/6。

- [完整原始包](portable/manifest.json)：19资产878,007B，原五对RGB/native16位深度、同帧完整Info/时间/实际q、SDK、相机工厂参数、配置及实际模型FK，全部SHA通过。[实际值/姿态比较](assessment.json)。
- SDK六秒60/60新鲜、5.919896s、六轴波动0/速度0，原静止条件通过rc0，六轴enabled=true。原q_mdeg为[1987,99516,-49937,-15090,26474,24769]，不是生产观测目标。
- 5帧原图5.499792s/rc0/settle3s，q与SDK一致，异戳Info4次照原规则拒绝。已看首末原RGB，方块在两指之间；接触依据仍是操作者确认。近距目标深度不可用，保留原零值，不误当A失败或捏造中心。
- 开口原反馈36.9mm，比名义29mm多7.9mm，原因未知；原effort=2不是牛顿。名义边长未卡尺验证，工具内方块中心未知，均不猜0。
- 现读工厂serial CC1365304DG及完整镜头内参、D→C、内部光学TF成功；未改安装TF。实际FK与第一组B相比工具原点距离66.579mm、整体旋转30.362°、工具z轴变化9.896°，确有位置和倾斜变化，但不能据两组夹持宣布联合标定可辨识。
- 链路复用ifindex10 UP/ERROR-ACTIVE/1Mbps/.75，RX2662658→3136029，TX1→1；不把既有累计TX1归为本轮控制或声称全历史TX0。无sudo/CAN恢复、使能、开闭、运动、Reset/Disable或一键运行。

复用原collect_calibration_sdk（6s）、calibration_readonly_feedback（90s）、原cam2image（90s/320×240/5Hz）、collect_static_rgbd（15s上限/5帧/3s静止）、camera factory三个只读GET，再原review/export；没有源码修改。首次离线review因未设置PYTHONNOUSERSITE误载用户NumPy2失败，未产出成功数据；随后使用原系统ROS环境成功，不改依赖或代码。

下一步须本组原位松爪释放且方块不移动，再按原流程返回既定观测并在SEARCH前停止，采60帧/至少20好帧A。第一组运动许可不沿用到本组；本轮尚未获本组开爪/回观测授权，不自动执行。

收尾：只读桥90.200s/rc0、4178采样/3997发布/181旧戳抑制，末次q仍相同/六true/36.9mm。原RGB收到SIGINT正常限时退出，timeout码124不代表采集失败。无本轮RGB/桥/控制driver残留；旧深度相机保留。CAN收尾RX3376856/TX1/error-drop0，五冻结生产SHA与上一轮完全相同。原桥报告另存readonly_bridge.json，不改原manifest资产表；本轮仅本地Git，未推送远端。
