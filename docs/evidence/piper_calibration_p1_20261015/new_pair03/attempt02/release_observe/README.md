# 本组原位张爪已完成；首次返回请求因CAN停流被拒，宿主恢复后续跑

用户明确回复“是”，授权本次新位置原位张爪、核方块未动、原轨迹返回观测并在SEARCH前止住。B检查点63da2d9有效，不混旧attempt。原enable/adapter arm前q与B一致；arm后J2+0.815°/J3+0.253°持位变化另记，原B不覆盖。

本次原CLI一次100mm命令（wait1/keep-alive3s）由原adapter接受80帧，driver明确GripperCtrl100000/effort1000/set_zero0；原SDK实读99.4mm/六true，原图确认已松爪。释放前后同实际q，背景ORB/H347匹配322内点，方块中心补偿差0.699px，未见明显移动；这不是三维零位移计量。

首次controller/start返回success=false/No fresh joint state，没有发返回轨迹。原driver1792040920.269反馈停止，25s后原adapter自动disarm；新SDK0fresh、独立4秒接收0帧，RX11420523/TX15600固定/ERROR-ACTIVE。当前磁盘34GB/error-drop-busoff0，根因不明，不套成硬件坏、磁盘满或IK失败。所有该次控制源已退出，未Reset/Disable。

用户随后确认VMware重连USB-CAN；新ifindex11/USB003-016初DOWN，sudo-n已通过，仅固定1Mbps/.75/queue1000/up、RX41后开始增长。新SDK真实姿态仍是张爪后q/99.4mm，并不是观测。随后只继续尚未执行的原返回，不再张爪；[原返回结果](../observe_capture/return_execution.json)与后续A另存。

[execution.json](execution.json)保存完整命令/状态/限制；[原图和反馈包](portable/manifest.json)23资产996907B，六对释放前后RGB/native深度/Info/q/实际FK/SDK/配置/已读B工厂资料齐全，通用observation_capture字段不代表这是A。新factory GET失败也原样保留，未冒称新读成功。

`runtime_closed.tar.gz`完整无损封存本子会话55个原文件（含原ROS bag/CLI/SDK/日志及可移植包），2245497B，SHA b74942416b639dab73288f425721218c827e35383564fedddc1ff28fec181fc9；[逐项清单](runtime_manifest.json)。bag18662条/完整性ok，1154等旧会话计数不混入本次：本次3663条joint_commands包含80个100mm夹爪帧；独立gripper topic录制0条并不等于没有执行，原CLI/adapter/driver/实际开口共同佐证。原图/深度0/全窗SDK rc2均未改。

生产源码、门、TF/TCP、模型/限位与入口均未修改。该子会话不是完整点对，下一续跑真实到观测后才采A；不得将0fresh/默认0写成实体回零、失能或候选中心。
