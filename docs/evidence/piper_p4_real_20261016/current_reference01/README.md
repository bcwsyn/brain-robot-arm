# 当前实测中心与真实夹持参考核对

2026-10-16 22:35 +08，基线`3e65b08`，用户确认后继续。**本轮无实体运动/开闭/使能/失能/复位，生产代码、TF、TCP、限位没有修改；仍未完成真实抓取。** ROS2/PiPER技能用于核真实路径/图像/反馈，手术式技能限制范围并保留用户脏改。

## 已得到当前数据，不再依赖旧空洞帧

[摘要](raw/current_summary.json)、[全部84文件SHA](manifest.json)、[只读执行记录](raw/readonly_execution.json)。原ROS环境运行`run_readonly.py`，复用原有限采集工具与只读桥、原检测器和原安装TF；没有实体driver/adapter/executor/Servo。相机18.064秒，5对时间戳配对数据（不是硬件同步），每对保留原RGB、16位毫米深度、同帧Info、实际q和SHA；另52原戳世界点/0TF超时、10同戳debug。

直接查看：[原RGB](raw/capture/evidence/0001_rgb.png)、[原深度](raw/capture/evidence/0001_depth.png)、[深度100—300mm显示，黑=原始0](raw/geometry_review/0001_native_depth_100_300mm.png)、[原RGB检测叠图](raw/0001_raw_color_debug.png)、[原深度debug](raw/0001_debug_image.png)。方块完整可见约49px见方，闭合夹爪在下方，不是已夹住。debug黑洞不能当作原RGB中的夹爪遮挡；PNG像素没有填补。

调用原`estimate_calibration_cube_center.frame_hypotheses`，不重写点云算法：[全5帧结果](raw/geometry_review/report.json)、[面边界/中心叠图](raw/geometry_review/0001_face_center.png)。目标覆盖82.25%—84.33%，5/5完整面拟合；首帧尺寸28.716×28.946mm、面RMS全帧.333—.361mm。沿面法线内推标称14.5mm得到29mm方块中心，base中位：

```text
[0.3482677775, 0.0217277304, 0.0129615118] m
```

五帧峰峰范围[.396,.673,.106]mm只是重复性，不是1mm绝对准确或成功抓取。这个中心与旧顶面假设不是同一种参考；不能再重复加旧11.6mm插入或14.5mm。

## 模型确含夹爪，但当前原CAD投影仍偏

[原mesh叠图](raw/geometry_review/current_original_jaw_mesh_overlay.png)、[数值](raw/geometry_review/jaw_mesh_report.json)。从当前installed原URDF/两指STL、实际.4mm开口和批准X投影：模型自由端z=.1358m，像素约[222.92,131.27]、[207.98,130.48]，明显不贴当前照片下方真实夹指。不是“模型没加夹爪”；也不能单凭此图唯一确定安装X、模型或实体支架谁有错。没有修改生产TF/TCP去强行贴图。

## 独立旧夹紧RGB参考：可继续验证，不是新TCP

上一轮A/B＋FK推回的参考投影在方块外。本轮只取**已由用户确认真夹紧的02B原彩图**，不经机器人FK，根据可见顶面四角与标称29mm方形，复用原`board_pose_offline.poses`求IPPE两个解。[原标注/候选图](raw/geometry_review/clamped02_annotated_square_hypothesis.png)、[完整两解和100次±2px扰动](raw/geometry_review/clamped_rgb_hypothesis_v2.json)。

标注点为[138,162]、[200,162]、[210,187]、[131,187]px，是圆角/模糊边缘的近似角点，不是卡尺实测。第一分支RMS.694px，中心color约[.005226,.042232,.104319]m、图像[169.73,205.70]px，在原方块内；第二分支RMS8.031px、中心在方块外，也完整留存。第一分支±2px扰动中心峰峰[1.55,2.10,7.40]mm，**不包含旧安装相同、真实尺寸或其他系统误差**。`new_pair07`未用于拟合、选择或调参。

参考[OpenCV官方PnP文档](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html)的3D/2D对应、内参与IPPE多解语义，使用本机原版本，没有升级依赖。低像素残差不证明绝对夹持点准确。

经当前X换算的P4局部点为[.027242073,.022053521,.117481412]m；它会吸收X/标注等假设，甚至不在名义两指中面上，**只叫有效任务参考候选，不是已验证物理TCP，也未写入生产TF**。v1元数据中的source键被URL覆盖，v2另存图像路径/URL更正，原v1保留。

## 原执行器完整规划通过，仍未实机采用

`prepare_preview.py`只产生[隔离候选文件](raw/center_preview/frozen_target.yaml)，明确`hardware_adoption_approved:false`；不要把它直接用于实机。域78复用原执行器/原模型/原限位、以本次实际q作为明确合成回放输入；预抓取和下降均100%，12/7轨迹点。[零输出及测试急停结果](raw/center_preview/preview_result.json)。臂/夹爪/关节输出0，测试急停1且拒绝重开，不是硬件故障；没有实体driver/adapter/CAN。

[执行记录](raw/center_preview/execution.json)父均rc0/无强杀，但MoveIt子在SIGINT收尾−11，原nodes.txt保留，不称全优雅退出或真实运动失败。25项原中心/采集回归通过，见`raw/center_regression.xml`。没有将上轮201项说成本轮重跑。

## 状态、异常与下一步

根分区56%/33GB可用，不需清理。CAN ERROR-ACTIVE复用、RX63463868→63530125、TX53100→53100，错误0/dropped297不增，未恢复/重载接口。末实际反馈六使能true、夹爪.4mm、q见摘要，是采集末快照而非持续监测。SDK60fresh/5.919秒、角度波动0，但两个速度瞬态J6−36/J2+20mrad/s导致原严格静止结果false/rc2、没有30点3秒静止子窗；与原采图q静止检查通过分账，**未放宽原静止阈值或把rc2改成成功**。最初的启用位/频率缓存预热也保留，不当作断电事件。

一次临时像素命令漏PYTHONNOUSERSITE发生既有NumPy2/OpenCV ABI导入失败，仅按原系统环境重跑，不安装/降级依赖。所有自有采集/模型/检测/规划源已退出；生产SHA与3e65b08一致，已部署执行器/驱动未变。原始文件路径保留home绝对路径，便携复查可按manifest将home根映射到本目录raw；日志只改扩展名为.txt，字节与SHA相同，所有PNG原件保留。

下一拟只给原P4执行器增加默认不启用、显式请求的**仅夹爪测试入口**，调用已有GentleCloseGripper及原adapter/driver，不发六轴轨迹、不另写一键脚本或运动算法；先独立实测张开/缓闭，再由原入口限定采用当前实测中心＋RGB夹紧参考候选。新入口尚未实现，新参考尚未实机采用，按用户“代码修改前先说明/同意”规则先确认这项新范围；不是要求重批已完成的中心接线，不是新增默认靠近门。当前无需用户重新摆放或重启，不重复旧空抓/手眼9＋1/普通CAN巡检。

本轮无生产变化，无需源级回退；采集/规划都已停止。新候选数据与生产配置分离，仍保持3e65b08的回退点。Git仅本地，既有origin/main分叉/积压历史发布审查不变，未推送GitHub。
