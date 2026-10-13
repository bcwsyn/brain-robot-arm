# 2026-10-13 当前相机LDP读取与首段关节行程拒绝

## 官方事实 / 用户资料 / 当前证据分开

- [Orbbec SDK C++说明](https://orbbec.github.io/OrbbecSDK/doc/tutorial/English/OrbbecSDK_C%2B%2B_API_user_guide-v1.0.pdf) §3.2.8–3.2.10：LDP启用后检测近处障碍，逐渐降激光功率直至关闭；测量与保护状态读取须在激光开启且Depth/IR流活动时进行。该说明未为本台DaBai DC1规定15cm阈值，不能从一般LDP事实推出历史缺深度必然因为保护触发。
- 用户明确提供官方工作范围0.15–5m并要求不继续查激光保护；停止该额外排查，保持保护原设置，不以近距深度失效阻断所有RGB/反馈辅助靠近。该范围作为用户提供资料记录，不把LDP原始PS值当毫米或阈值。
- 当前相机USB2bc5:0657/URI2bc5/0657@3/14，原camera log序列CC1365304DG，与[官方USB规则](https://github.com/orbbec/ros2_astra_camera/blob/master/astra_camera/scripts/56-orbbec-usb.rules)中DaBai DC1一致。

## 只读实机LDP查询（机械臂静止）

规范`test/read_camera_ldp.cpp`只读取属性并开启与生产相同640×400/30Hz/1mm普通深度流；不写激光/LDP/固件、不建立机械臂/ROS控制接口。g++编译0、外部12秒边界运行0；原生模式5个活动流样本1791900433.416..0437.482：EMITTER_STATE_V1=1、LDP_ENABLE=1、LDP_STATUS=0，均status0；深度非零193308..195800/256000（约75–76%）。证明当前静止姿态保护启用、读取时未处于保护且激光开，不证明历史近于15cm姿态未触发。

旧EMITTER_STATE接口为write-only读取status4，改用官方EMITTER_STATE_V1读回；LDP阈值上下限读取协议status4，不据错误推断阈值。LDP_PS_DATA原值160..200，单位未查明，禁止写作160..200mm。首次默认stream无帧，samples=[]，只可引用开启前值，不能作活动流保护证据；明确生产native mode后才得到有效5样本。OpenNI打印USB线程优先级warning，文件头有非JSON行，解析取首`{`之后报告，不能将文件名.json等同纯JSON或忽略无帧失败。

可复现：用实际OpenNI header `/home/johnwick/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera/include/openni2`、redist/x64 libOpenNI2编译该源；仅在原相机进程已退出时运行，避免竞争。证据`view_guard_20261013/camera_ldp_readonly_native.txt` SHA9798d5b288f9e2eb6e7b1ddfd0abc6353c3597044299214794cfde639a99a4c7，诊断CPP SHA54bd0a4f88ddcee6708c0b588d4f3e5902a28960bfd9bb42c5c8cc2cc6831970。工具已结束，不继续近距/激光实验。

## 与本次真正运动阻断的区别

- 4b0dd26/64回归已部署binary298448…/CPP18beea…，原AUTO1 PREPARE1791900008.378527→SEARCH0047.964801→ALIGN0063.858938→GRASP_READY0066.612728。
- 79预抓取+13下降=92路点的原完整预检成功；step0于0068.742请求base xyz(.174836330638,-.058740535932,.293575339437)、qxyzw(.131871988424,.924197138360,-.049982372980,.354924203891)，完整Cartesian100%、时间处理后8点/最大相邻joint步.027239rad。0068.748诊断`AUTOMATIC_RGB_STEP_0_JOINT_TRAVEL_LIMIT`，尚未发布任何自动靠近段、也未触发反向候选。
- 原ExecuteVisualPose遍历完整规划中每点，任何关节相对起点>0.08rad就返回false；这是总行程而非最大相邻步幅，不能把日志.027239<.08当门错误，也不将本次归为IK失败/CAN/激光。具体超过阈值的轴/数值尚未输出，不能凭J5印象当唯一轴。
- 已看0037/0048三图：0048完整紫块接近十字、debug .301m/2008样本，原RGB与注册debug不同处理显示，原生16位depth固定展示暗不等于无深度。停机后0082墙钟0171只是0075图/0077反馈缓存，勿冒充新实时数据。
- 主68857 rc1/原cleanup、exact70951 INT0、observer38982 rc143，所有本轮控制与采集已退出、无Disable/Reset/自动回零。结束新SDK1791900473.376507/high0473.377507六轴true，q[-.284226869,.989741312,-.757525255,0,.706910707,0]rad/最后ROS99.6mm全开，无抓取。

## 新局部授权与待验收

用户已明确同意仅原0.08rad检查复用现有检查通过的小步前缀→停稳→真实反馈重规划；阈值和原限位/碰撞/相机/闭爪不变。正在原执行器加入此处理及两项原方法回归。只能裁切已经完整规划通过、至少含起点及一个已通过全部原检查运动点的前缀；禁止把不完整Cartesian路径、第一点拒绝或预览模式错误变成运动。64回归和反向修复保留；新版本构建/实测待验收。不能用本次step0拒绝判定反向方案无效。
