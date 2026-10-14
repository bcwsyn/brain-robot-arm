# 2026-10-14 手动终点：静止画面与原模型对应核对

## 范围与结果

用户“好的”批准紧前静止采集/模型对照方案，不是自动抓取或修改原闭爪条件授权。基线5643318/actual3985466。两仓库技能均完整读取；host无控制栈，只复用原入口相机命令启动Astra depth、独立320x240@5Hz RGB与原cube_detector；没有piper driver/adapter/Servo/executor/MoveGroup/运动发布器。只读SDK ConnectPort(piper_init=False)，没有SDK控制/使能/夹爪目标、CAN恢复或模型参数写入。

第一采集保存图片/URDF/反馈后因ROS诊断level为bytes、JSON无法编码而rc1。仅分析脚本序列化兼容修正后5秒补采，rc0，279新鲜SDK样本/14RGB；首次日志与资产均保留，不把首次失败隐藏。只读工具归档到test/review_manual_terminal_snapshot.py，便于接手重复静止采证据；它不会启动相机或运动栈，需外部有界启动原相机。没有改生产代码/TF/TCP/限位/检测门/闭爪条件。

## 可核验的新证据

- 原RGB1791953346105498603，320x240/camera_color_optical_frame；SDK关节stamp1791953346.104573与RGB差-0.925ms（接收时反馈，不冒称插值TF）。q_mdeg[-12173,110855,-62094,-1619,32287,6682]、六true、速度0、开口36.8mm/夹爪true；279新鲜样本期间角度spread全0。J5相对刚使能时32323已有36mdeg差，本窗口稳定，不能说跨全部时间绝无变化或推断变化原因。
- 已直接查看两次原RGB及模型叠图：可见黑色夹指在方块两侧；HSV原范围的纯颜色轮廓框[128,157,87,83]、质心[170.760,199.520]，方块下边被240px边界裁切。画面中心[160,120]是背景，不在方块轮廓内；同戳原v2 observation color_center_covered=0/qualified=0/samples0。仅二维轮廓，不冒称方块完全可见、成功接触/夹住或合格三维检测。
- 选取的native depth1791953346201616934与RGB差96.118ms，不当同帧深度；640x400全部0。流/相机info存在但本姿态无有效深度，不能据此产生新三维目标或把其他背景深度填成有效。color camera_info未发布；原RGB投影使用此前已读工厂色内参，不虚构本次color_info。
- 原实际launch生成物理URDF SHA a93ac8cba44d02dc09ca52442bb72e8d8c92f97dd732cee08702e1fe9438c581；规范/实际task SHA均a0111d3f6a412a96b327a7ae72913f864241a6d33642e2a46ca2c9c4478a2fe4。按原ROS .017444转换，不混同SDK精确pi；实开口±18.4mm进入模型。静态离线FK/既有安装配置，不启动TF链，不假称查询了新鲜图戳动态TF。
- 当前模型指尖投影[93.600,268.856]px，已在240px下界外；link7/link8投影最小v分别245.565/245.870，两网格画内像素均0，实际原RGB却有两指。已证实当前安装/几何描述不能解释这组实际图像；尚不能唯一判定是安装TF、参考点或自装夹指网格哪一项错误，未仅凭此拟合/部署新外参。
- 同模型计算历史step48失败起点tip=(.366956,-.110478,.108355)m，当前手动tip=(.378089,-.085018,-.004242)m，差(+11.13,+25.46,-112.60)mm；这是基座模型坐标，不是实际桌面高度。历史冻结目标减当前tip=(+47.70,-31.09,+71.52)mm，时间/目标参考面/实物位置连续性未验证，不当校准offset直接加给实体。六轴均不同，J5约少32.36°，不能把整个末段几何归结成只加J5。

## 判断与下一步

新手动参考揭示：此前“原RGB画面中心覆盖”必要条件会拒绝当前用户摆出的姿态；不能继续把十字中心等同实际夹持区。但用户此前明确批准该条件，本轮不能自行取消或宣称已改。先离线以可见两指/方块参考分析对应，再具体提出统一实际夹持参考的局部方案并获准；不会把本组q硬编码到任意目标、复制历史base XYZ或整库回退。组合候选与Servo timeout修复仍未批准/实施，补候选本身不解决已见的参考不一致。

只得到候选手动终点，尚未验证抓住/承载/抬升。一次姿态和二维轮廓不足以标定完整安装变换；没有标定板不作为无限冻结软件诊断的理由，也不能假造标定真值。先保留当前姿态，原完整目标未完成。

## 命令、路径与收尾

环境沿原Humble/piper_ros/piper_ws/ros2_ws overlays、domain0、原fastdds_udp_only.xml，无DDS修改。Astra原ros2 launch astra_camera astra.launch.py、RGB原cam2image参数、原cube_detector.launch.py分别timeout -s INT -k 3s 90/90/80s；自然有界停止各124，子节点正常退出，不当通信失败。Astra收尾参数undeclare错误日志与图像输入成功分开记录。SDK只读采集timeout -s INT -k 3s 45s（首轮）/40s（补轮），第二rc0。

完整原图、native depth、模型叠图、生成URDF、逐帧反馈及report均在/home/johnwick/brain_robot_logs/view_guard_20261013/manual_terminal_capture_20261014_complete/；首轮在同级manual_terminal_capture_20261014/。日志/tmp/piper_manual_terminal_{astra,rgb,detector,capture,capture_complete}_20261014.txt。小JSON[piper_manual_terminal_snapshot_20261014.json](piper_manual_terminal_snapshot_20261014.json)进入Git，PNG/大日志未提交。

全部相机/检测/采集已退出，host无运动栈。最后被动SDK1791953435.2095602/joint3435.2043967/100Hz，六true/速度0/q_mdeg与补采相同/36.8mm、夹爪true。未Reset/Disable/回零，保持手动姿态，无自动续跑。磁盘95%/4.4GB、本次证据有界，没有扩展删除或把深度全零归因磁盘。Git仅本地，原dirty/远端分叉保持。
