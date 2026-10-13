# 2026-10-13：J5单段观察恢复完整目标

## 执行证据

- 起点8b019a5，相机检查补丁503bfd7，第二段记录a2b5e67。
- 原MoveIt Pilz PTP，比例.002，每段177点/17.544410432秒，最大速度.006 rad/s；通过原 `/brain_robot_grasp/arm_trajectory`→唯一adapter单次发布，不绕过控制链。
- 第二段接受stamp1791859066.382264591；J5 41.733768→46.648150°，发布rc0。
- 第三段接受stamp1791859257.658643606；J5 46.648150→51.606509°，发布rc0。
- 六轴末反馈[-.31809134,1.897715316,-1.34467074,.007274148,.900703496,0]rad，其他轴增量0，夹爪.0796m保持。
- enable_motion/arm/disarm返回success=True；最终软件disarm、硬件保持使能。未闭爪、回零、DisableArm、ResetPiper、MasterSlaveConfig或刷固件。

## 图像和数值（已查看0022与0040三图）

位置 `/home/johnwick/brain_robot_logs/j5_plus5_20261013/observer_step3/evidence/`。

|文件|消息stamp|SHA-256|
|---|---|---|
|0040_rgb.png|1791859328.8098962|160da8270f902d80c5e2e5a162609fc8e960872b472e30b7fee7523efdb7ca80|
|0040_depth.png|1791859328.9023833|b88d1685b6cefc69573222ce29407d7099c6f7b0f815dce96849956c4b695097|
|0040_debug.png|1791859328.8098962|d6dd671313ea436800a70117fb21e0934305376610545d409c86783523d256b6|

- RGB320×240：紫区bbox78,161,51,63，图像边缘不再裁切；左夹指仍遮挡部分轮廓。
- depth640×400 uint16：非零89064，中位184mm，最小170mm。不能用16位图直接看起来黑来判没有深度。
- debug：cube0.190m、551样本、MAD.001m、尺寸.040×.049m；target/depth_valid均true。三图为latest采样，非严格同步对。
- 目标depth optical[-.0068112,.0671135,.190]m。实际TF只读确认 gripper_base<-depth optical：t[-.070,0,.0308]，R映射XYZ→[Y,-X,Z]；配置模型face[-.0028865,.0068112,.2208]m，相对tip_z=.1358前方85mm。

该85mm是当前配置模型推算，不是实际接触标定。两指屏幕参考169,174也不是实际捕获区证明。没有依此发布靠近或闭爪。

## 只读后续规划与边界

`review_camera_jaw_alignment.py --goal-pixel 169 174 --maximum-m .015 --forward-m 0` 返回1：Exact image-time TF did not arrive within bounded wait；JSON明确validated=false/hardware_executed=false。后续tf2_echo初始缺frame，约1–2秒后链可见，原执行器也持续有TARGET_TF成功日志。需先解决新分析节点初始化，仍用原图时间戳，不以latest绕过。

完整视野/有效目标子目标通过；靠近到实际两指闭合区、抓取、抬升、释放未完成。现有控制栈IDLE、软件disarm、硬件使能，采集已限时退出。只提交文本记录，不纳入图片/大日志/供应商升级包，Git仅本地未同步GitHub。
