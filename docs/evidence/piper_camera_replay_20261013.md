# 当前相机工厂参数与静止回放（2026-10-13）

批准范围：当前相机K/R/T局部更新、静止采集与隔离离线回放。没有批准或执行下一段实体运动；安装TF/TCP、镜像设置、检测门、力度、抓取路径不变。

## 数据来源和可复现命令

- 当前设备服务成功返回serial **CC1365304DG**；旧配置针对 **CC136530302**。四路服务/外参原始值见同目录 `piper_camera_factory_20261013.json`。GetCameraInfo的D为0，但GetCameraParams的彩色畸变项非零，此次不新增畸变处理，不将K/R/T更新说成完整手眼标定。
- 现场证据根目录：`/home/johnwick/brain_robot_logs/jaw_approach_20261013`。原始图不提交Git；采集JSONL保存每张图SHA256与原始整数时间戳。
- `collect_static_rgbd.py --output <root>/factory_static_capture --duration-s 30 --frames 15`：rc0，10.87秒收齐15组。仅订阅相机/关节，不发布；时间戳跨度23.64–96.85ms，depth与CameraInfo必须同stamp。**软件时间配对，不是硬件同步。** 46个配对候选中11个因depth/info不同帧拒绝。
- 0010 RGB stamp `1791862676834609923` ns、depth/info `1791862676772528005` ns、反馈 `1791862676833618768` ns。RGB SHA256 `11c5835ef882811ef0f3e9f7596a13fa086b1d98d448c612f47dcd6d27246e5b`；depth SHA256 `19bf1cef655fd18f0d62d797104e1d3493225603b9264d50a9071356b882649a`。深度uint16/640×400，有49916个非零像素，非零中位183mm；全图非零不等于方块区域有深度。已查看这两张原图和两份回放debug：原RGB方块完整、偏左、左指遮挡；黑色16位显示不等于所有数据为0。
- `ROS_DOMAIN_ID=78 ros2 run brain_robot_pick_place cup_detector_node --ros-args -r __node:=cube_detector --params-file <config>`；分别加载新规范YAML、`git show 7516de1:.../cube_detector.yaml`保存的旧配置到临时文件。每次仅一个检测器。
- 同域运行 `review_rgbd_shape_replay.py --capture <root>/factory_static_capture --output <root>/{factory_replay,old_factory_replay}`。两次rc0、约7.86秒，图节点只有cube_detector与isolated_rgbd_shape_review；没有piper/MoveIt/视觉控制器。回放保留相对stamp差、整体重置到回放时间，不能当新实机图/图像TF使用。检测器受60秒/25秒外层timeout限制，正常期限结束rc124；回放本身均rc0。

## 同一数据的结果

| 配置 | 后半段depth_valid/target_valid | 诊断 | 最后debug |
| --- | --- | --- | --- |
| 当前CC1365304DG工厂K/R/T | 9个均false | DEPTH_REJECTED_INSUFFICIENT_SAMPLES | samples=0，原RGB矩形仍合格 |
| 旧CC136530302配置 | 1个等待、6个true | WAITING_FOR_STABLE_FRAMES后GRASP_ALLOWED | .186m、589样本、MAD=.001m |

旧回放最后相机点[-.00179222,.06590351,.186]m、尺寸[.0403512,.0487515]m；新配置不发布目标三维点或尺寸。以上证明旧参数的“有效深度”不能继续作为当前设备正确配准证据，**尚不能单凭本次回放确定缺深度是近距量程、IR遮挡、视差还是畸变/投影实现问题**。

## 下一步边界

规范YAML已更正，实际运行源码/install及已启动的域0检测器仍是旧参数SHA256 `2df167ca878179e3f75c82f2ac286f756cd712082627209566429b5a7742a48c`；新规范SHA256 `154938b0e22d22546cedceb56e2bb3484fd79988c5786d13aca5aa3bc48c6675`。离线失败没有触发实体续跑、放宽门限或热改安装TF。下一应先用同一静止数据核对配准方向/目标原深度区域及畸变约定，提出最小修复后征求同意；若需换视角取深度，另列有界动作取得批准。旧85mm模型残差和旧.186m不能直接驱动最后靠近/闭爪。
