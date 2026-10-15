# 2026-10-15 11:18—11:21 CAN恢复与原驱动使能证据

用户宿主重新连接后，新USB1d50:606f为003/014、can0 ifindex9；起初DOWN/STOPPED/RX0。只复用已授权固定激活：sudo-n true、bitrate1000000/sample-point0.75、txqueuelen1000、up，各rc0。未模块/USB/xHCI重载、固件/主从/Reset。RX56→62,863→348,019，ERROR-ACTIVE、错误/丢包0。

## 原始数据

- `pre_enable_sdk.json`：原6秒被动SDK，60/59fresh、5.821666956s、原静止条件通过/rc0；q毫度[1046,104766,-51433,-5998,24410,17143]、速度0、六enabled=false、37.2mm。SHA256 `69620ed633b55631240ea2848ad9ecba28ecebbaaf90424ac794ab9c48122120`。
- `post_enable_sdk.json`：60/59fresh、5.819900990s、原静止条件通过/rc0；59新鲜样本六轴全true、q和开口与前相同、波动0/速度0。SHA256 `5dfdfa85adeb9ad49fc52fb0c9aed60aa3f220cb4d495a6a9fa0228cf8d85d40`。SDK源戳/默认首样本原样保留，非逐电机硬件同步精度声明。
- `driver_reconnected.txt`：原driver重连/使能日志快照；auto_enable=false、初始反馈.01秒恢复，1792034432.024793684接到true请求，1792034433.040809629返回true。
- `enable_service.txt`：原`ros2 service call /enable_srv piper_msgs/srv/Enable '{enable_request:true}'`返回enable_response=true，12秒强制宽限外壳内rc0，原服务不是新写SDK运动程序。

归档提交`b789718`。四个原文件与runtime逐字节一致。标准`git show --check b789718`仅在原始`enable_service.txt:5`报告CLI自带的EOF空白行；为了原始证据不改字节，其他全部路径按标准检查通过，仅这一个raw日志使用一次性`-c core.whitespace=-blank-at-eof`检查通过。不改全局Git设置，不放宽任何代码或其他文档检查。

## 进程及命令范围

仅SIGINT旧controller30526、adapter30524、driver30181/wrapper30177，随后ps确认全部退出；没有调用DisableArm。只重连原安装入口`/home/johnwick/piper_ros/install/piper/lib/piper/piper_single_ctrl`，参数can0/auto_enable=false/gripper_exist=true和原joint topic remap。PYTHONNOUSERSITE=1、系统NumPy/SciPy、sys.path末尾补原用户site-packages后runpy执行原入口，不改源。源/build driver SHA均`d607ec10854f231588fcdfc9f334c4766d5b8c4474e10fd72f79ef5723984b2e`。

重连后/ROS joint反馈新戳1792034418.885088442与SDK q一致、/joint_commands发布者0，旧/pos_cmd及/enable_flag也0。按用户使能请求调用原服务后再用SDK实证，不仅依赖服务响应。末TX16包含原驱动初始化/使能，不称全流程只收或TX0；没有关节位置目标、开闭夹爪目标、观测/搜索/抓取轨迹、Reset/Disable。夹爪反馈使能位true但开口仍37.2mm。

原driver新PID39486、session17394保留；adapter/controller均未重启，不会自动续旧轨迹。原RGB/窗口已过600s限时，host无它们，不宣称当前有新图。当前实际姿态不等于观测：下一继续P1时先按组授权回既定观测，再新图核视野/用户放稳确认采新A、人工实际夹紧采新B。旧B不配新位置，正式0/6，不把本窗当标定点或成功抓取。

生产五源SHA均冻结值，根54%/35GB、共享73%/137GB，无删除；本次只本地Git原始证据/交接，无代码或TF更改、未推送GitHub。链路现已恢复，不再沿旧RX18重复恢复；本窗不能独立证明历次停流唯一根因。
