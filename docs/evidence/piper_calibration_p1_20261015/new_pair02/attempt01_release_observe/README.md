# new_pair02 attempt01：开爪/回观测成功，裁切观测不作标定

本目录是失败尝试的完整有限证据，不是合格点对、外参结果或抓取成功。旧夹持侧在`../grip_capture/`，回退提交`5b94bb0`。用户选择移动方块到完整视野并重采，所以旧B不能与下一次新A配对。

## 实际过程

1. 原一键入口`/home/johnwick/start_brain_robot_cube_real.sh`，`BRAIN_ROBOT_AUTO_START=0`，未按1/r/2/0；原链路复用、无CAN重载。原适配器enable_motion/arm，原controller的运行时`stop_after_observe=true`回读通过，生产YAML不改。
2. 原topic`/brain_robot_grasp/gripper_command`的100mm首次命令被driver内部GetEnableFlag=false抑制，实际36.7mm；不是物理已开。调用原`/enable_srv` true成功后仅重试一次同topic，实际99.4mm；原驱动握手/80帧发送，不绕adapter、不写零、不Reset/Disable。`released_rgbd`是未开成功的5对，`released_confirmed_rgbd`是实际开后5对，SDK全量分别在`open_sdk.json`和`open_confirmed_sdk.json`，原全窗质量rc2保留。
3. 已实际看过前后原图，方块仍在桌面。背景ORB/H匹配后方块中心差约0.917px，未见明显移位，不是三维零位移证明。开爪/原enable持位后J2/J3较B变化+.010100076/+.005477416rad，均保留实际值，不能假称q完全不变。
4. 原controller/start发布9点31.2s/maxstep.080rad原观测轨迹，1792032585.318521到`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`。原始日志路径在execution.json，关键事件逐项记录；没有SEARCH/抓取/自动失能。
5. `collect_calibration_p0.py --max-batches 2 --frames-per-batch 60 --seconds-per-batch 60`采成两批各60/rc0、整体质量rc2。原RGB下沿裁切，120帧均不合格/中心null；不补洞、不外推完整物体、不第三次重复补采。工具名P0不表示本次又回P0，仍是P1首组采集工具复用。

## 可移植原始数据

- `observe_portable/manifest.json`：251资产、18,810,820 bytes，不含manifest自身；120对整幅原RGB/native16位深度、每帧同戳完整Info/实际q/FK、SDK、工厂内参/D→C、配置快照/全部SHA。manifest SHA `878100af8fb863226741cc670983605dead2b80c87637057afcc18b4887043da`。
- `observe_portable/camera_factory_current.json`本次活相机新读成功，CC1365304DG；不要据此改写旧B引用P0工厂缓存的事实。
- `p0_report.json`是原筛帧/有界补采报告；portable的`depth_review.json`为另一个只读审查，旧工具`requested_frames=30`仅其默认统计描述，不替代P1至少20好帧合同；本次两种检查都0。
- 两个released目录的原observer绝对路径照原样保留；读者取相应目录`evidence/`+原文件basename即可读PNG，逐图SHA原记录齐全。它们是释放核对证据，不是观测点，不能混入拟合。
- SDK原effort未标定牛顿，静止全窗false保留；逐帧q的0波动不自动证明速度原值全0。工具FK不是方块几何中心，所有未确认中心null。

## 下一步与冻结

用户选择移动方块到当前画面完整可见、四周留余量，放稳确认后先新A，再人工真夹紧新B。移动后旧B排除，不再沿旧位置采。当前正式0/6、生产五源SHA未变；原controller STOPPED、adapter disarm（停软件输出而非硬件Disable）。原一键已rc1退出、原RGB停止，但有driver/深度/adapter/controller残留；仅重开原cam2image同参数+原始RGB image_view供摆位，各600s限时，不重启运动栈，不能假称原一键/全部相机仍活着或全部已退出。

本轮无新生产代码/TF/模型/门/观测目标改动，也没有闭爪/搜索/抓取。数据只本地Git，未推送GitHub，不把目录网址当已上线。
