# 第4位置：独立原生深度记录器与深度源未启动的单次实测

2026-10-15 16:14 +08:00。基线8b6fd67；用户明确批准仅给诊断工具独立保存原生深度与同戳Info/实际反馈，不改正式标定判定。按ROS2核查与手术式修改技能将变化限定在test目录四个工具/测试文件，生产算法、TF、模型、限位、原800点/20帧规则全部冻结。

## 实现与验证

`collect_depth_controls.py`新增可选`--native-output NEW_DIR`；缺省GET-only模式保持。新`native_depth_diagnostic.py`仅订阅固定的原生深度、CameraInfo和真实JointState，不订阅或等待RGB，不发布任何控制。只有深度与Info同戳、原120ms/500ms新鲜反馈及原3秒/.001rad静止要求满足后，保存完整uint16 PNG、完整Info K/D/R/P/ROI、真实q/速度/反馈戳、SHA。不是新的实体运动门；没有松动原正式RGB-D判定。

原0值不补洞、不重缩放、不作单位猜测；仅16UC1/mono16按passthrough无损存图。原生图片最多60帧、间隔≥0.5秒、图片容量32MiB，深度/Info缓存各最多64项；已有输出拒绝覆盖。GET回复仍是原始数值、物理值与单位null、底层读取状态未验证。所有原生输出明确diagnostic_only，不能直接计入合格A。

14项新原生辅助测试、13项GET测试及32项原采集/质量回归，合计59通过。包含无RGB两种到达顺序、零值逐像素保持、同戳/编码/内参/新鲜度检查、缓存/帧数/容量限制、旧反馈/重复反馈和拒绝覆盖。**这些是离线合成测试，不是实体原生深度保存成功。**

## 本次实体结果：不是记录器筛掉数据，而是深度源未发数据

只执行一次连续相机会话，含退出上界26.103秒；未重开相机或执行任何运动、使能、夹爪、相机setter、CAN恢复操作。

| 观察端 | 实际接收/结果 |
| --- | --- |
| 新独立原生记录器 | 收到1083条真实反馈，深度0、Info0；拒绝计数为空；保存0帧/rc2 |
| 原RGB-D采集器 | 收到RGB67、反馈688，深度0、Info0；保存0帧/rc2 |
| 深度GET | 46请求、0回复：44响应超时、2在截止时取消；另有2条服务未就绪记录未发请求 |
| 工厂设备信息GET | `Timed out get_device_info`，当前工厂值未知；没有拿旧快照伪称本次新读 |
| 原相机日志 | 已识别CC1365304DG并设640×400@30Hz/DEPTH_1_MM，但没有`SENSOR_DEPTH is started` |

两个独立观察端都没收到深度/Info，新记录器没有因RGB或筛选条件拒绝这些数据。当前可证实的阻断在原相机初始化/启流阶段；不能据此断言底层USB、激光、硬件损坏或某一行代码就是根因。当前也不是CAN停流。

原源码`ob_camera_node.cpp:223–260`从设置模式到打印启动完成之间仍有注册/同步/VideoMode/镜像/stream.start等多个调用。没有保存当时线程栈，不能把“无启动完成日志”精确等同于只卡在stream.start这一行。没有修改或重编译驱动。

**本代理调度仍需隔离的因素：** 新记录器在真实深度启动前即根据服务可发现性发送GET；包装器等了4秒没等到深度完成标志，随后也发起factory GET并启动RGB。服务广告不证明初始化完成；这次GET时机与失败相伴，但没有因果对照，不能断言是GET造成的，也不能排除它的影响。完整时序/请求原件留在execution.json和depth_controls.json。

无深度时未尝试原export_calibration_bundle（它要求有真实配对图），没有生成空壳便携标定点或虚构中心。空observer.jsonl和真实summary均保留。此前B、60帧A及1帧补充诊断原件不覆盖；合格完整仍1/6，已采四位置，不进P2。

## 实体/CAN、退出及日志

预SDK全窗60/60fresh、5.931229秒、六q波动0/静止原rc0；q与已保存观测逐值相同。末反馈六true、99.6mm、q_mdeg[-7973,54505,-72477,-4187,69768,5433]，只代表最后新鲜记录，不冒称当前持续监测。

CAN RX6888884→6950152、TX3070始终不变、ERROR-ACTIVE，直接复用。全部本轮源退出，depth启动未完成、SIGINT宽限后按原预算精确SIGKILL(-9)；这不是机械臂失能。首条journalctl本地时区字符串不被接受，空输出及此错误如实保留；改用真实Unix秒的50秒窗口查询成功，`kernel_epoch_window.txt`为No entries。这不证明设备/库没有问题。

23个原始运行文件无损归档并逐项SHA复核；四个执行工具的启动前/后SHA一致，生产五SHA不变，见assessment.json/verification.json。runtime_closed.tar.gz中有原命令/临时调度器和原日志；可读日志以`.log.txt`另存，避免Git忽略。其中depth.log.txt仅为去行尾空白的阅读副本，首行已标明，不当作原始字节证据；原depth.log的行尾空格及SHA在tar中完整保留。没有对这一轮不存在的图片填补、套旧戳或改为成功。

## 复现与下一步（尚未实施）

在已有原深度源和真实只读反馈桥就绪时，记录器调用为：

```bash
# 先source当前项目ROS overlays，两个输出路径均必须不存在
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 /usr/bin/python3 \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_depth_controls.py \
  --output /tmp/depth_controls_NEW.json --native-output /tmp/native_depth_NEW --duration-s 24
```

它不会启动/恢复相机或机械臂；本次包装器只是历史原件，不沿旧单次授权直接重跑。

连续两次诊断未取得连续有效深度对照，按阶段规则停止实体追加试验，不无限叠补丁。建议先做最小启动时序隔离：**仅在诊断模式，将所有相机GET（包括factory）延后到收到第一对真实同戳深度/Info之后；先只订阅验证原深度能否启动。** 不改驱动、相机参数、激光/LDP、TF或运动；没有深度就有界结束、保存原日志。此方案及下一次单次会话尚未批准/实施，不保证GET延后一定修复设备启流。若仍不出流，提交结果再决定相机侧恢复范围，不把机械臂接口/历史CAN故障当现成原因。

本轮工具骨架和离线测试已完成，实机正向保存尚未验证。仅本地Git记录，未推送GitHub。
