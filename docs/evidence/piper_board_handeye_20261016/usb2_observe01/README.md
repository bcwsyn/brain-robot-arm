# 原观测返回成功，SEARCH前停止

2026-10-16，起点`4e44326`。用户授权自主原观测返回及相机核查。`executed_return.py`rc0，原控制helper AST及原launch与上轮一致，仅路径/元数据/被动CAN记录不同，六生产SHA未改。

原driver/adapter/controller从实际q发原2点20秒轨迹，16.565823秒满足原0.01rad到位判据，最大偏差0.009297652rad；实际收到`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`并软件disarm。不是精确名义终点，后续标定使用实际关节值。

bag含831六轴命令、6677反馈、2条轨迹（移动+恒定保持），状态IDLE→PREPARE→STOPPED，夹爪输入0，未SEARCH。完整candump119793帧，运动内最大时间戳间隔9.251ms，无新内核记录/错误；TX7465→9974。

末SDK六轴true、99.6mm，q_mdeg为`[-8254,53595,-72228,-4126,69528,5120]`。三SDK整窗均rc2原样保留；末39fresh/3.812937秒原静止子窗通过，只代表采集时事实，不是持续监测。无硬件失能、复位、夹爪、固件或生产TF修改。

所有自有源退出。启动层/driver/bag返回0，但SIGINT收尾MoveIt子进程−11、depth_cube_probe重复shutdown退出1，原日志保留，不能称全部优雅退出，也不改判先前已完成的观测运动为失败。

`assessment.json`为离线审计；23原件含完整bag/candump/SDK/日志/调用在`runtime_originals.tar.gz`，`runtime_manifest.json`逐件SHA已回读。离线首审仅误排除正常初始IDLE，确认原bag后修审计预期，`offline_audit_note.json`保留失败；未重跑运动/改原数据。home原件`/home/johnwick/brain_robot_logs/usb2_observe_20261016.CYJ9bI`保留。

原`camera_inventory.json`记录当时尚无相机；**用户后续已恢复两路，缺透传不再是当前阻断**。后续实际预览见[相机只读核对](../camera_usb2_preview01/README.md)，不要重复叫用户重连/重启或重做观测。当前新板参考未建立、旧板2/10，生产冻结；Git仅本地、既有同步阻断保持。
