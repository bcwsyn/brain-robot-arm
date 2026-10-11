# 2026-10-11 有限靠近与近距深度缺失

接续 `1a6a662` 图像瞄准。生产入口、实际executor、TF/TCP/YAML均不改，不闭爪。以下是实测与代码事实，不是抓取完成或外参校准。

## 命令和真实结果

- 原Astra launch、原cam2image320×240/5Hz/burger=false、原detector launch与cube_visual_search.launch.py在IDLE有界启动；两轮自有组先退出再重建，没有竞争驱动。SDK50857未重启。
- `review_camera_jaw_alignment.py --goal-pixel 150.5 155.5 --maximum-m .015 --forward-m .010 --output image_forward_plan_live2.json` 只调用规划。原LIN30点/2.82350294秒、比例.005、弧长11.892194mm；delta_depth[-.005297568,.003606265,.010021408]m，delta_base[-.001388821,.005742568,-.010324344]m。模型世界空，不是桌面净空保证。
- SDK `/enable_srv` true后，原adapter `/enable_motion` 和 `/arm` 均 **std_srvs/srv/Trigger**。新鲜真实起点200.169Hz/年龄.721ms，原 `/brain_robot_grasp/arm_trajectory` CLI发布完整MoveIt轨迹一次，adapter接受1791728212.566024895。
- 末实际q rad[-.207269608,1.890074844,-1.239431088,0,.908518408,0]；J5=52.054270°，比起点低2.347749°。J6规划.016258860rad/.931564°，真实0，未确认六轴全部到位。J6原因尚未取得同步命令证据，不修改适配器反馈锚定/限位。
- 原collector后5组4.133秒/最大53.379ms/六轴恒定；已看0005原图，完整bbox(120,126,64,75)、中心(151.022,162.842)，两指仍可见。粗瞄准参考(150.5,155.5)，横向误差.522px，总误差7.360px；屏幕瞄准不是实际接触证据。

## 深度阻断（实测）

真实诊断 `DEPTH_REJECTED_INSUFFICIENT_SAMPLES`，target_valid/depth_valid=false。用原工厂D2C、原HSV形态学和完整轮廓，在前后各5个原配对包计算同目标实测支持（完整mask而非额外腐蚀；不伪造/填洞）：

| 数据 | 同轮廓非零深度支持 | 中值 | 原RGB旋转形状比 |
| --- | --- | --- | --- |
| image_aim_after 5帧 | 5093/5192/5202/5126/5032 | 均.151m | 1.17..1.21 |
| image_forward_after 5帧 | 0/0/4/0/0 | 除4点.179m外均无值 | 1.17..1.23 |

4点可能是背景，不当目标深度；少于原10样本，不能放宽来通过。后整图43908..48879个非零点，最小非零均.149m。**局部近距失去深度、彩色方块仍可见**明确成立；最低约149mm支持近距盲区推断，但未唯一排除局部IR遮挡/传感器过滤，不能称官方150mm规格或实际新目标.141m已测得。

实际launch日志连接2bc5/0657、serial CC136530302，名字Astra仅驱动识别。[Orbbec官方udev](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/scripts/56-orbbec-usb.rules)把0657映射为DaBai DC1、0557为其RGB；不能套用其他Astra/Gemini产品最短距离。本轮没有找到对应DC1的官方最短距离声明。

实际 `grasp_lift_executor.cpp` 中 `FinishGraspAndLift()` 首先调用 `FreshFaceInsideJaws()`，后者要求target_valid/depth_valid和目标/尺寸时间新鲜，否则 `JAW_CAPTURE_FRESH_RGBD_UNAVAILABLE_NO_CLOSE`。所以只改原彩色形状/不断增J5不能解决近距无深度与最终复核的兼容问题；下一需基于可靠3D锁存、原RGB跟踪和真实反馈/FK设计有限近距策略，并独立校核接触区，而不是把预测当实测或拿屏幕中心闭爪。

## 工具失败和停止证据

首次只读规划TF未来约22ms、exit1未发布；只改test工具等待原stamp≤.3秒，绝不latest替换。新增两项回归连原11项=13全通过；waited/live2规划均exit0，失败原JSON也保存。

第一次CLI误把enable_motion类型写SetBool，等5秒exit124；源码核实Trigger后更正，期间没有trajectory发布。首次“监控ready”预检与ROS发现竞争，父命令exit1；临时monitor跟随父会话提前退出、事件只到2.908秒、没有summary。随后CLI检查了旧ready文件而没核活进程，因此**本次监控没有覆盖真正运动**，没有运动段joint_commands/反馈证据或专门视觉丢失停止证明。原adapter限位/反馈仍保留；检测LOST后显式disarm成功。不得称监控闭环通过。下一如用临时监控，须直接独立持久exec会话并核活进程/订阅，非后台子进程/旧文件标志。

临时栈11684 INT退出130、只清理本轮57429..57432组成员；收尾仅原SDK50857/PGID50855，无自动续跑。未闭爪/Disable/固件/CAN重载；.1019夹爪缓存不当实际开口。入口SHA0e976b0a…、executor源码107ce501…、YAML75612194…不变。

## 原始路径与SHA-256

目录 `/home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu/`：

- image_forward_plan.json（失败TF）：8c322643fae6aa018cee1825b7452ecf42bfd10fbc8dd29326bd25405bb5a828
- image_forward_plan_waited.json：5f86662d0c0013f84ba369b46ec8124bbef53a68ddc1906628c2c8f536be954b
- image_forward_plan_live2.json：55569378d15cd754e3d8e90ef56ae1ca9c57164a6da31bf6258a8b76974f31ff
- image_forward_shape_depth_analysis.json：d0b432a9121c0489867c2b6f54ed580bc699fd77f6af8deda1cc685785bb12b0
- image_forward_after/observer.jsonl：27161564f510dbaf1a4e356c08802a13ddb5fe6a76250a0728f28c3f5bffcd8e
- image_forward_after/evidence/0005_rgb.png：d15997fef14bb1a3d6bc813516a28d3c37e893b4a7a5fc82111ad7a22f30b1de
- image_forward_live_diagnostic.json：65539c8c238fdeafca96fd433b0a6252d0145787bafd202b814b326bd6fba580

另保存forward2_{astra,color,detector,visual}.log、image_forward_fresh.json、image_forward_publish.txt、image_forward_monitor/{ready.json,events.jsonl}及临时原型/tmp/piper_forward_evidence_20261011.py。大图/日志不提交Git。Git只提交test精确TF等待/回归和本文等交接，不全包部署或混入供应商旧改动。
