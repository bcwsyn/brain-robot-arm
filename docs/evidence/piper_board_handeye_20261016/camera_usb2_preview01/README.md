# USB2下相机已透传：深度有流、RGB零帧

用户已恢复两路相机；实际0657深度/0557RGB均EHCI480M，RGB serial `CC1365304DG`，video0/1存在。CAN仍UHCI，机械臂已完成原观测返回、相机测试期间不运动。

单次复用原只读预览：原被动SDK/桥→原Astra深度→原cam2image320×240、发布5Hz→四源就绪。相机运行16.984秒，ready实际15.002秒收到关节695、depth346、camera_info346、RGB0。0图，未启动正式采集或新板参考。wrapper返回TimeoutExpired(11.869秒等待)与实际零RGB分别保留，不把设备枚举当RGB-D成功。

全部自有源退出，TX增0，CAN RX增长，四只读源与六生产源SHA不变；无运动/使能/夹爪/重置/生产TF或门变更。18原件及每件SHA在归档/manifest，已回读验证；home原件`/home/johnwick/brain_robot_logs/board_usb2_preview_20261016.ueRDNB`保留。

下一自主分离原RGB/UVC启动与深度，先读实际native模式而非再跑同条件全流程。后续只读V4L见1632×1224 YUYV5，和意图发布320×240不同；[官方Humble源码](https://raw.githubusercontent.com/ros2/demos/humble/image_tools/src/cam2image.cpp)先open再设宽高，且frequency控制发布定时器，这是待验证线索，不直接证明根因、USB2不兼容或硬件坏。不改DDS/TF/检测门/VM设置，不再要求已完成的相机重连。

旧板仍2/10，当前无新图/标定。Git仅本地，既有同步分叉/历史审查/发布范围阻断保持。
