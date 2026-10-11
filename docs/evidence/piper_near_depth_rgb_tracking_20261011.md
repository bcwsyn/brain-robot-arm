# 2026-10-11 近距深度缺失：原 RGB 同目标观察与执行器兼容补丁

起点 `6611386`，用户最新“确认修改”。本轮只修改规范源码、隔离测试和交接；**未部署到实际安装空间、未运行实体一键运动、未闭爪**。本文件不能当成抓取成功或相机外参已校准的证据。

## 责任点与最小行为变化

旧实测断点见 `piper_near_depth_20261011.md`：前进 10 mm 后原 RGB 方块仍完整，目标相关深度样本从约 5000 个降到 0/0/4/0/0。已有 `static_target_lock=true`，不重写锁存或底层控制器。

- 原 `cup_detector_node.cpp` 增加 `/brain_robot_vision/qualified_color_bbox`，类型 `geometry_msgs/PolygonStamped`，四角按**原 RGB 宽高**归一化；空 polygon 显式无目标。独立于深度是否非零，但仍复用原 HSV、开/闭形态学、面积、旋转矩形比例、矩形度和原裁切判断。原 `raw_color_bbox` 被动预览不变，不能拿 area≥10 的最大紫色替代合格方块。
- `/brain_robot_vision/raw_color_info` 提供原图的 frame、stamp、宽高和按原工厂值缩放的 K；执行器仅用其宽高/frame，完整 D→C 解释从**运行中 `/cube_detector` 的标准参数服务**读取并缓存，不在第二个 YAML 复制外参。当前原图模式仍 320×240，未启用未经核验的高分辨率映射。
- `qualified_color_shape()` 是新观察和原检测选择共用的纯 OpenCV 函数，原条件数值不变；没有填深度洞、改 `target_valid/depth_valid`、删除样本/MAD/稳定/尺寸门。原 SEARCH/初次锁存仍需要可靠 RGB-D。
- 原 `grasp_lift_executor.cpp` 增加 `ObserveLockedTarget()`。图像时刻的实际反馈 TF 将**锁存基座点**重投影至原 RGB，与当前合格矩形的位置和尺度关联；不采用轨迹预计末 q、不刷新旧测量 stamp、不修改基座锁存点。
- 抓取起始先获取同图像时刻的可靠 RGB-D seed；缺深度后只允许这个 seed 支持有限预测。规范 `cube_task_real.yaml` 新功能为 true，但**实际 YAML 未同步，实机仍旧配置**。缺深度窗口默认最多 30 s / 30 mm；已有 `target_timeout_s=.60` 不放宽。30 mm 是预测有效性的输入范围，**不是新增实机运动授权，也不重置已耗尽的旧采样预算**。
- 相机原点折线累计仅来自已观察到的不同 RGB 时刻，不是完整规划路径弧长；图像间不可见的运动未由此证明。关联允许原图归一化中心残差 ≤.04、点在同框内，以及按预测 Z 缩放后的宽高比 .65..1.5。这些是本项目启发式，不是供应商标定精度保证或实例识别器；较大的背景紫色会被拒绝，不保证多相似物体情况下仍选中真正方块。
- 在原 `ExecuteArmTrajectory()` 输出前及原反馈等待循环核对观察。仅缺深度且同目标 RGB/反馈成立时继续；真 RGB 丢失/反馈异常则通过**已有软件停止话题**及 `/piper_jog_adapter/disarm` 停止原适配器输出，服务回复成功/未确认分别记诊断。没有 `DisableArm/ResetPiper`，不依赖旧临时监控的失效 ready 文件。此停止路径尚未实机触发验收。
- `FreshFaceInsideJaws()` 保留实测分支，增加“锁存三维＋新鲜 RGB＋当前图像时刻 TF”分支，诊断明确 `LOCKED_3D_FRESH_RGB_PREDICTION` 并分别打印旧 `measurement_stamp` 和新 `image_stamp`。两分支仍使用原 `FaceInsideJawCapture()`；不是二维居中就闭爪。关闭/抬升后结束桌面 RGB 跟踪，防止已抓起的物体被误当成移动的静止桌面目标。

## 测试暴露并修正的开口语义

新否定例第一次发现：通用 `FaceInsideJawCapture()` 只判断几何，会接受 `.1019 m` 这样的超量程开口。之前“原几何必然拒绝该缓存”的推断不成立。本轮保持通用几何函数不变，在原闭爪复核处复用本机 adapter/SDK **已有命令范围 0..80 mm** 做缓存合理性检查；不是宣称厂家机械最大开口为 80 mm，也不是新增六轴靠近条件。

此改动不修复夹爪基准本身，不写零点，不将 `.1019 m` 当成真实张开。不因该缓存阻止六轴靠近，但它不能授权最后闭爪。用户 70/105 mm 测量、旧外参候选否定、当前实际接触区未独立核准的结论全部保留。

## 验证分层和原始证据

共用目录：`/home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu/`。

1. `near_depth_policy_replay/summary.json`：使用原 URDF SHA `382d7934…`、真实起终 q（J6 实际 0）和原 RGB，原 C++ 几何/关联函数接受前后共 10 张合格同目标图；9 个否定例全部拒绝（无初始可靠深度、反馈缺失、原时刻 TF 缺失、旧图、超时、超距、无颜色、细长色块、背景紫色）。**新鲜度在此离线试验中明确模拟，未把历史图片刷新成实体新观测。** 不输出机械臂命令，不生成深度测量，也不证明实际夹持区。
2. `near_depth_detector_replay/`：隔离域 78，运行新编译检测器，仅回放原相机输入。`image_aim_after` 稳态 4 次 target/depth 均 true；零深度/无颜色/细长/高 MAD 全 false。`image_forward_after` 稳态 5 次 target/depth 均 false、`DEPTH_REJECTED_INSUFFICIENT_SAMPLES`，但 4 角 RGB 形状仍存在，无 target_point/raw_target_projection 新发布。两回放分别 26.476/7.729 s、exit0；临时检测器 finally 清理，exit0。图像传感器缺深度问题仍在，不称“深度恢复”。
3. 执行器方法测试直接编译原 `.cpp`，`real_grasp_enabled=false/auto_execute=false`、域 78、内存合成反馈/TF；未调用 MoveIt 初始化、轨迹输出或夹爪输出。检验 seed→预测时旧 stamp/锁存点不变、没有初始深度不能启动、RGB 真丢失/缺轴被拒、两种夹持复核分支和异常开口拒绝；另核标准参数服务读取工厂标定。合成夹持成功不代表实际接触成功。
4. 最终8目标clean build exit0，9个CTest套件5.90 s/exit0：40项C++（含5项实际executor方法/参数服务）及43项Python全过；另原detector零深度/裁切/投影测试1项通过，共84项，5个Python源AST检查通过。日志与9个XML归档 `/home/johnwick/brain_robot_logs/near_depth_validation_20261011.wBut3v/`，build SHA `500251eeb1fd26cd0e6b26d4f5ad0f499af9991b5a5321c315ba333f55adf09f`、ctest SHA `a4d7e4949c22a3809663f0b2fc61cb164984e2cb0ae5f0ff862377d51465e7e3`。构建目录 `/tmp/piper_rgbd_shape_build_20261011.fygBnq`，没有覆盖真实 build/install。初次 executor 编译遇到 Humble FutureAndRequestId const-get 限定错误，已改非 const；初次开口否定例失败见上一节，未隐藏。中途新增 CMake 目标曾需要重新配置；最终以完成编辑后的串行 clean rebuild 验证，避免修改期间的构建结果混用。无初始seed的tf2向量默认构造未初始化也已显式置零/提前拒绝；不是实体关节故障。

最终规范源 SHA：detector `f2519a31b8d348c8101688ddb8f0db8e1ecd36199dae8e61645e0f62969ac623`；executor `d0be18ccd1226913149c3cec8159479e745d1975329de34bfcbc2200762757ea`；near-depth头 `a663ea30cd090a37ffa10ad887d30a3ac30bac972405d168315db1825639cf10`；YAML `b93d4deb046cc063579bcd69748e710dc87285f4fac8002ef2d0e015f125ee04`。最终隔离bin detector `f75ea2dd4dd99a0800d78b032742485c7f979c85a6bef1db0432109a08773b41`、executor `30431928ab9a5cc62a6b970bf06450754c369b6011fc701342a0faa3dde65d30`。policy bin `a0285a7c5487c4c73bff0378aa0d6c3e9b5040f051e283835961ad93d5292a38` 与回放归档一致。

证据 SHA-256：

- policy summary：`e78b05fcb735cec4e62e392d2f5bf281487ad477d9d182f0ebf6498929a94ad5`
- detector before summary：`ee3cce4e8871c4466d88c7bbfa72de7a94c26a7609e36d678c369a8bd16c52c1`
- detector after summary：`5d11023968455a27a634225a3bcc2bda2b90335cf5237b604b8e8d825db39da1`

## 保持不变、局限与下一项

实际入口 SHA `0e976b0a…`、实际 executor `107ce501…`、实际 YAML `75612194…`、实际 detector `2deb634f…` 未变；23:01:49 SDK50857/PGID50855仍在，未重启、未失能，不把进程存活等同新一轮高速反馈测量。根盘本轮 34%，未执行无必要清理/CAN重载/固件操作。

原 MoveIt 位姿规划→唯一 adapter→真实关节反馈主线不变；本轮**没有修改 J5/末端朝向算法，也没有验证或执行历史错误的全段转腕路径**。近距输入兼容已实现，但安装接触区误差、实际 J6 未到规划角及夹爪异常缓存仍未解决；不能因为离线分支通过就宣布默认一键抓取成功。

下一项：先对实际 executor 与规范既有 OFF-preview 差异做逐块部署审查，不全包覆盖；只部署本补丁必需的检测器/头/执行器/三个参数，从原观测姿态的新可靠 RGB-D seed 验有限末段和真实图像/命令/反馈。当前停在近距无深度的位置，不能用本离线 replay 的旧 seed 直接续跑或闭爪。仍需把真实方块送入实际两指接触区并确认真实开口，随后再验抓取/抬升/释放。

方法参考与代码推断分开：OpenCV 的[三维点重投影接口](https://docs.opencv.org/4.5.4/d9/d0c/group__calib3d.html)与 [ViSP 官方 IBVS 示例](https://github.com/lagadic/visp/blob/master/example/servo-universal-robots/servoUniversalRobotsIBVS.cpp)支持姿态/三维模型和新鲜图像特征联合核对；ViSP 示例有 AprilTag 对应/位姿条件，本项目没有，不声称直接复用已获同等性能。本补丁复用仓库现锁存/FK/MoveIt/adapter，未复制直接 setVelocity 接口绕过适配器。

GitHub：上一轮共享 main 写入审核拒绝仍有效；本轮“确认修改”只批准该代码改动。仅本地提交、未同步 GitHub，不再尝试/绕过推送；远程授权阻断与实机近距问题分别记录。
