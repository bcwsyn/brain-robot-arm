# 2026-10-14 官方抓取、夹爪模型与手眼标定资料核查

## 本轮范围与事实基线

用户要求搜索官方资料，帮助找到：同实体成功靠近代码、实际相机支架/夹指CAD及同安装抓取实现。本轮仅研究/静态阅读/资料归档，不是新增控制策略或标定运动授权。首五Git/最新四规范文件/技能已读，基线85703f7；host无机械臂/MoveIt栈，实际应用仍d051bf5，executor d4c7063d4d0ff8c1ea5b4c528264242eb8a011deeeb882ea25fb09515a5c03f7，唯一原脚本87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0。未SDK连接/使能/运动、未安装依赖/换驱动/改TF/模型/闭爪条件。

## 找到的官方一手资料与兼容性

| 来源 | 明确事实 | 本项目用途/限制 |
| --- | --- | --- |
| [Agilex-College 方块与曲线识别](https://github.com/agilexrobotics/Agilex-College/tree/master/piper/cubeAndLineDet) | OpenCV色块/深度三维点，例举Petrel、D435，ROS1启动；曲线部分提示其当时Orbbec camera_info可能不匹配 | 与紫色方块任务相关，但它是感知例程，不等于已验证完整实机抓取。已完成本机工厂参数更新不能因旧教程警告重新判错/回滚 |
| [Agilex-College GraspGen](https://github.com/agilexrobotics/Agilex-College/tree/master/piper/GraspGen) | YOLOv8-Pose/TensorRT/PCA抓取姿态，Ubuntu20.04/ROS1 Noetic；运行示例RealSense aligned depth | 可参考目标三维几何与抓取姿态的分离，不把检测框中心直接当夹持TCP；不为紫色单块换ROS1/装CUDA/重写主链。教程里agilexrobotics/GraspGen链接当前404，而开头指向的[作者GraspGen](https://github.com/vanstrong12138/GraspGen)可访问；区分官方教程与第三方实现 |
| [官方PiPER手眼教程](https://github.com/agilexrobotics/Agilex-College/tree/master/piper/handeye) | Ubuntu22.04/ROS2 Humble、眼在手/眼在外；通过末端与标志物位姿采集计算相机安装变换 | 与现系统匹配；示例RealSense可换真实Orbbec RGB/camera_info，但不能下载别人安装外参当本机真值。需要已知尺寸标记和不同姿态数据，用户暂无法提供板不作为统一视觉闭环工作的无限阻断 |
| [官方handeye_calibration_ros/humble](https://github.com/agilexrobotics/handeye_calibration_ros/tree/humble) | 原节点调用OpenCV calibrateHandEye，默认min_num10；末端订阅Pose、标记PoseStamped；package.xml声明Apache-2.0 | 可复用求解与离线质检；源码串行获取两消息、末端Pose无header，必须匹配真实frame/单位/采样停稳和时间，不原样套示教/SDK动作，不新增重复TF publisher |
| [官方agx_arm_urdf](https://github.com/agilexrobotics/agx_arm_urdf)及[PiPER夹爪Xacro](https://github.com/agilexrobotics/agx_arm_urdf/blob/main/piper/urdf/piper_with_gripper_description.xacro) | 标准夹爪visual/collision与STL/DAE；新模型gripper范围0..0.1m、两指mimic±0.5；flange到gripper_base有4.5mm固定变换，指关节origin Z138mm；MIT | 可核对标准件几何，支持100mm模型开口，但模型/关节/包名不同，不直接替换本机piper_description或改变已确认实体开口/限位。网格/URDF不是实际自装支架的STEP装配图 |
| [官方SDK TCP偏移示例](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_read_tcp_pose.py) | 明确J6位姿与TCP的区别，按J6朝向旋转工具偏移；示例offset=(0,0,.145)m，单位转换为.001mm | 能查清末端参考点，不把示例145mm当本机测量值，不运行默认ConnectPort；本机旧模型135.8mm与手册140mm的参考面须核对，不能用文件名或数字直接换TCP |
| [Orbbec ROS2 Astra官方驱动](https://github.com/orbbec/ros2_astra_camera) | 提供camera_info、设备/SDK查询及图像服务 | 已有本机工厂内参/D→C；这些是镜头内部关系，不包含相机支架到机械臂/夹持区的安装外参，不为本次研究切SDK2/改DDS/激光 |

上述是官方明确资料与本项目适用性判断，**尚未找到能证明与用户当前支架、夹指、Orbbec安装姿态完全一致且完整抓取已验证的官方成品仓库**。这不是断言不存在，只是本次公开检索未证实。第三方syswonder PiPER+Orbbec DCW方案为固定桌高/平面单应性、不同框架；RobotKitAI例程是固定外部相机；均不冒充本机同安装/厂商官方方案，不复制其外参/桌高或绕过adapter。

## 本地已经拥有的实物尺寸与成功动作证据

1. 用户给出的reference/vendor_docs/PiPER机械臂用户手册V1.1.0.pdf，第56页9.7夹爪尺寸图已实际渲染/查看。图示夹爪总长140mm、法兰直径57mm、指段73mm，图示间距不是机械限位认证，也不覆盖自装相机位置或定制指爪。PDF SHA256 fef09a25beaa23b9f0f9c7d3c4fc584a107146a64f19a73388c379d02ae64122；未提交PDF/页面图，预览/tmp/piper_vendor_dimension_page56_20261014.png。CJK文本抽取不完整，尺寸以原图而非OCR猜测为准。
2. 本地vendor模型已有gripper_base/link7/link8及STL，旧joint7 origin Z.1358m、模型上限.035m；真实launch对物理夹爪描述另有修正，不能拿旧vendor范围覆盖用户100mm实际反馈。文件SHA见下面。现有模型包括夹爪不等于TCP端点/相机安装已实物标定，但也不代表应重复加7cm/10.5cm；先明确参考点，避免双重补偿。
3. [PIper_HANDOFF_20261010.md](../PIper_HANDOFF_20261010.md)保留settled_fix历史：76点预抓取+9点下降+落点纠偏+闭爪请求，失败于夹爪反馈不变。靠近/下降已有效，不能说从未完成；也不能算物体确实夹住。早期外参与当前不同，优先做几何/落点离线对照，不能整库回退/直接实机重放绝对角度。
4. /home/johnwick/piper_sdk/piper_sdk/demo/V2/sequence_move_fixed_gripper.py及sequence_move_official_gripper.py也有本地顺序动作。但“official”文件名不是厂商来源证明，两个脚本张闭方向解释互相矛盾、硬编码J1=90°并绕过现adapter/碰撞/真实到位；仅静态阅读，未运行，不当成功抓取基准。

旧vendor文件当前含用户已有变更，本轮未编辑/暂存：

- piper_description.urdf：22c15f95e50003b01713bae158638f7d19cdb71b1bd1095289865b835067002b
- gripper_base.STL：2895bfa6f1eef2d0ad2cb9dfdedd5f6c760ec07388bcde2b4d1e412e1189c9cb
- link7.STL：475a7d8db056524d7659fadf5a2c307d62791047b6214d733dfc7846ed1c613d
- link8.STL：3f88d534a85e28a33ef7d2061adacbd1d25214aa9325f9e464aad0f9e4b74606

## 固定本轮资料版本/来源可信度

公开GitHub API GET commits/<branch>只读返回rc0，未克隆或复制代码/大型模型：

| 官方仓库/分支 | 已核对提交 | 日期UTC |
| --- | --- | --- |
| Agilex-College/master | c2688be41e1bc99a9addd555f237a16bc839d936 | 2026-08-05 |
| handeye_calibration_ros/humble | 3f8e29606f91b2e6c46457961af03154f7ad3809 | 2026-09-18 |
| agx_arm_urdf/main | a68b8e876a2c6fcb0ecee7a7943129e4d48dd864 | 2026-10-13 |
| piper_sdk/master | c9e8a28174e71eeaac448593cb65f8ab258a92fe | 2026-07-31 |

Agilex-College README有个人学习/研究使用声明，不把官方示例一律当MIT授权；handeye package.xml声明Apache-2.0、模型仓LICENSE为MIT、SDK示例MIT。本轮仅记录链接/事实，未复制实现。旧官网PDF链接web获取超时；SDK最初少写piper_sdk/目录导致404，正确路径已读；agilexrobotics/hand_eye_calibration不是正确仓库，已转官方handeye_calibration_ros。错误链接不作为资料内容依据。

## 下一最小可验证动作（方案，不是本轮实施许可）

优先用本机历史成功预抓取/下降路径对照当前名义末点/指尖定义；按官方J6/TCP区分核对标准几何，然后针对已证实“初始ALIGN深度参考→靠近模型预测→固定tip恢复空转”问题，提出在原检测/执行owner统一实际RGB夹持参考与联合位置/姿态恢复的局部diff。模型仅可达/碰撞辅助、锁定同一世界物体不重锁、原最终中心与两指夹持保持；不为搜到官方资料就重写一键入口/更换驱动/复制外参。

当以后能获得已知尺寸ArUco标记，可按官方眼在手流程离线求解/验证安装外参；没有标记不阻断先修软件闭环。若需厂家补资料，应明确询问**当前型号夹爪/指爪对应STEP/图纸、相机支架型号与光心/J6/夹持中心参考定义**，而不是再索要一般SDK安装说明；本轮未向厂家发送消息。

资料研究完成不等于抓取完成。当前物理断点/真实反馈沿用85703f7，不做新当前反馈声明；部署不变/host无栈。Git仅本地提交，缓存origin/main与HEAD left1/right127、既有分叉和全历史推送审查未完，不强推或自动合并。用户既有wiring/vendor/reference资料不纳入。
