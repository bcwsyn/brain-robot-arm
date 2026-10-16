# RGB无完整帧：有界分层对照，需Windows宿主画面对照

起点`ba08b62`。用户要求自主继续，仅必要现场操作再叫。原观测已完成、臂未再运动，当前不是目标识别/深度洞问题，而是RGB没有交付完整帧。

本轮分别做了原cam2image RGB-only8秒、仅彩色子进程禁GStreamer8秒、原生YUYV320×240传感器5fps（最多3帧/8秒上限）：全0完整帧。原生STREAMON成功、select timeout、raw0字节、进程rc0，不能把rc0或空文件叫成功/黑图。原源均停止，临时native模式均恢复到各自取帧前值。

只对核实的RGB2bc5:0557、序列号CC1365304DG、/dev/bus/usb/002/005做过一次USBDEVFS_RESET，ioctl rc0；接口短暂重建后已自动重新绑定，随后相同原生取帧仍0字节。最后模式读回640×480MJPG25，是重枚举后本轮原生取帧前值，不是已核准的新标定内参。没有ResetPiper、CAN/根Hub重置、运动或夹爪命令，禁止继续相同reset/开流循环。

原GStreamer警告与回退V4L2 EBUSY发生在有界SIGINT清理后，不能据此确诊清理前重复占用/根因。切后端也没出图，未部署为修复。[官方Humble cam2image](https://raw.githubusercontent.com/ros2/demos/humble/image_tools/src/cam2image.cpp)及[OpenCV4.5.4后端配置源码](https://raw.githubusercontent.com/opencv/opencv/4.5.4/modules/videoio/src/videoio_registry.cpp)仅用于设计对照：先open后设置尺寸、发布频率不是传感器FPS、优先级0可禁指定后端；不根据文档推断本机必然恢复。

末4秒只读SDK39fresh，六true/99.6mm，实际q_mdeg仍`[-8254,53595,-72228,-4126,69528,5120]`；整窗rc2、角度波动0原样保留，不追采静止门。所有采集/控制源退出，CAN TX9974不增/RX增长，两Orbbec/video0/1仍存在，生产六SHA、TF/各门/SDK/全局环境/曝光/VM兼容性不改。没有新RGB/板连续参考，旧候选2/10。

`runtime_originals.tar.gz`保留22原件，子目录按原RGB、V4L2优先、原生5fps、一次RGB重置、末态区分；含完整strace/log/空raw/JSON/代码。`runtime_manifest.json`逐件长度/SHA回读通过，松散JSON/代码供审阅；home原件都保留。Git仅本地，既有同步分叉/审查/发布范围阻断保持。

## 下一步确需宿主操作

VMware仅将Orbbec/Dabai的**RGB 2bc5:0557**交还Windows宿主。打开Windows“相机”选择Dabai DC1，观察有无实时彩色图；报有/无（错误可截图），关闭应用后只将RGB接回此VM。保持深度/CAN、USB2兼容性、臂和棋盘格不动，不重启机械臂或VM。

guest无法查看Windows相机应用；该结果区分宿主原生RGB接收与VM转发，不是重复相同VM重连，也不预先确诊硬件坏/USB2不兼容。回来按事实选分支，不再同条件客体尝试/软件USB reset。
