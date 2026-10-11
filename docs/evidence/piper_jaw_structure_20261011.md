# 夹指结构对应：已确认自由末端，未完成外参标定

日期：2026-10-11。起点：b6c93af。本轮没有新运动或生产参数改动。

## 原始证据与图

- 原彩色图：`/home/johnwick/brain_robot_logs/jaw_landmarks_20261011/evidence/0002_rgb.png`，640×480，SHA-256 `5b695ae3ad08b07f2b8e0895a897cdb7e11edd34057dda5109532b97511e412b`。
- RGB stamp=1791705038.214105，关节 feedback stamp=1791705038.2960317。上一轮静止采集，本轮只分析档案，不称当前实时采样。
- 实际 MoveIt 归档模型：`/home/johnwick/brain_robot_logs/jaw_geometry_20261011_step1/review/move_group.urdf`，SHA-256 `382d79345b286047a09c0941d638248b3f6c5f51a94a8a4dfb4359e2a69443ac`。
- 结构图：`/home/johnwick/brain_robot_logs/jaw_landmarks_20261011/structure_review/finger_structure.png`。左/中是CAD局部正投影，右是原RGB和当前TF预测的自由末端；不是拟合成功的叠图。
- 用户侧照只在聊天提供，未找到本地附件文件；照片的观察、用户特征确认及数值已写入同目录规范证据JSON，不声称二进制照片已归档。

## 对应表

| 结构 | 实物/原RGB证据 | 模型证据 | 当前结论 |
| --- | --- | --- | --- |
| 夹指整体 | 侧照显示根部连接、宽侧面、斜边及窄自由端 | STL包含约76.50mm长、56.00mm最大宽的渐窄夹指及厚度台阶 | 模型不是只含底座；实物精确尺寸仍未由无标尺照片验证 |
| 左自由末端 A | 约(u=95,v=311)，用户明确是远离螺丝的自由末端 | link8 最末端平面 Z=135.8mm | 结构区域身份已确认，具体哪一个三维顶点仍未确认 |
| 右自由末端 B | 约(u=513,v=315)，同样经用户确认 | link7 最末端平面 Z=135.8mm | 同上；不是根部，也不是另一个独立指尖 |
| 最前端内向接触小面 | 侧照/黑色指体尚未提供准确面边对应 | Z=125.778..135.800mm、中心130.5895mm；与宽侧面/后方台阶不同 | 不能直接把整块黑色指体或面积中心当这个面，也不能直接改TCP |
| 实体开口 | 图中两指打开；驱动gripper缓存0.1019m未获可信标定 | joint7/8=0是模型占位，合法模型最大开口70mm | 真实开口未量定，闭合/70mm投影只用于界限诊断 |

## 已定位的矛盾

以实际归档的 `gripper_base -> camera_depth_optical_frame`、生效工厂D2C和640×480内参投影**自由末端平面**，而不是整根指体：

- 闭合模型：两指自由末端 v 最小487.77/487.88，最大约581；图内像素0。
- 70mm模型：v 最小487.13/488.53，最大约582；图内像素0。
- 实物A/B则分别在v311/315。只核两个模型开口端点，不重复上一轮165组倾角/开口扫描。

因此当前完整几何解释与已确认实体自由端不一致。不是“实体夹指不在视野”，也不能用“模型没画夹爪”解释。**尚不能把原因唯一分配给某一个旋转轴、平移分量或模型接触点误差。** 相机和夹指刚性连接，整体J5运动不会校准二者局部关系；此前J5正向使方块回到视野的真实效果继续保留。

## 代码责任链

生效 `brain_robot_ball_pick/launch/cube_visual_search.launch.py` 的 `_camera_mount_arguments()` 读取实体YAML `piper_camera_mount_tf.translation_m/rotation_rpy_rad`，转换成静态发布器所需yaw/pitch/roll，发布 `gripper_base -> camera_link`。

生效executor的目标锁存把图像stamp的相机点变换到 `lift_reference_frame`，再由现MoveIt规划；原 `FreshFaceInsideJaws` 又把新鲜相机面点变换到 `gripper_base`。同一静态几何同时影响基座抓取目标和夹持区判断，MoveIt不会自行根据实图纠正错误外参。这是可追踪的几何修复主线，不是新增门控的理由。

模型 `link6 -> gripper_base` 固定变换为单位变换，`gripper_tip_offset_m=.1358` 已包括模型夹指长度。当前没有证据支持删除夹指、再叠加一次同样工具长度，或直接取消70mm/105mm测量。

## 未解项和后续

保留用户70mm/105mm测量；“该测量对应哪个具体实体/模型点”和未标定安装旋转不能自动当已确认。现在两自由端区域已确认，但精确顶点对应、实际开口及可用三维深度仍未齐备。

已对前轮同一静止RGB-D做一次7px内缩的指体注册深度核对：右指0样本，左指6样本约175.49mm，左暗区有背景污染可能。不能用这些点当两个真实指尖的三维位置，也没有新合法抓取点。

后续补齐可辨认的实际面/边/角与网格对应及开口尺度，再拟合相机→夹持框架，并用未参与求解的特征核验。采用已有[OpenCV PnP接口](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html)而非另写机器人控制器；它需要真实三维点与对应二维投影，两个未定顶点的区域不能自动给出唯一完整外参。不为了凑点数把黑色轮廓任意角点分配给CAD。

若现画面不足，应具体说明所缺的独立几何证据及如何获得；不能继续无限扫单角、靠整体J5制造伪独立夹指视图，或将未校准候选直接部署。准确生产差异仍先说明获用户同意，再用同一原脚本和现MoveIt→adapter做有限不闭爪验证。

## 复现

在规范仓库运行以下离线命令（不启动ROS，无运动接口）：

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_jaw_scene.py \
  --observer /home/johnwick/brain_robot_logs/jaw_landmarks_20261011/observer.jsonl \
  --task /home/johnwick/piper_ws/install/brain_robot_ball_pick/share/brain_robot_ball_pick/config/cube_task_real.yaml \
  --detector /home/johnwick/piper_ws/install/brain_robot_ball_pick/share/brain_robot_ball_pick/config/cube_detector.yaml \
  --mesh-share /home/johnwick/piper_ros/install/piper_description/share/piper_description \
  --model-directory /home/johnwick/brain_robot_logs/jaw_geometry_20261011_step1/review \
  --output /home/johnwick/brain_robot_logs/jaw_landmarks_20261011/structure_review \
  --structure-rgb /home/johnwick/brain_robot_logs/jaw_landmarks_20261011/evidence/0002_rgb.png \
  --free-end-corners-confirmed
```

完整数值见 `piper_jaw_structure_20261011.json`。A/B坐标及用户确认绑定此原图SHA，不自动套到未来帧。针对性测试用于结构/投影和来源归属；不是外参已校准或抓取完成。
