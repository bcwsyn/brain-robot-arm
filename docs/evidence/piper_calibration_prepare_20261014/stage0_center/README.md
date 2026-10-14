# 第0步已独立补齐：面中心、坐标系和采集前验证

用户确认没有Claude源码，并授权代理自主继续第0步。本轮不等待源码；使用仓库现有原始RGB-D、配准/统计/helper及官方算法接口独立实现。不是Claude算法逐行复现，也不是正式实体标定或抓取成功。生产代码/TF冻结，原pair01全部115资产保持原样。

## 成果与真实数据结果

`estimate_calibration_cube_center.py`：原始hash/uint16/消息K核验 → 沿原D→C配准选取紫块真实深度 → RANSAC主平面/SVD精化 → 测量面矩形范围 → 名义方形边界拟合 → 沿**面法向**向内半边长取几何中心候选。明确记录D与C两个光学frame、原厂R/T、面法向/角点、实际测得面边长、误差和每帧拒绝原因，不用机器人安装TF，不沿视线盲加半边，不补缺深度。

这些是独立**数据分析**标准，不加任何实体停止门：原覆盖率≥50%、至少100真实点、主平面≥60%、测得面边处于名义值80%–120%；平面阈值2mm、方形边界RMS≤2.5mm。是否完整物理面仍是明确假设，不由minAreaRect自动证明。

30帧/10高支撑候选、20低帧全部拒绝；没有把边缘背景点当中心。测得面边中位约28.063/29.618mm，平面RMS中位0.631mm。29mm仅名义尺寸（不是卡尺事实）：

| 项目 | 结果 |
| --- | --- |
| D：camera_depth_optical_frame中心候选中位 | [-13.009, 40.974, 453.482]mm |
| 同一个D中位点经R/T变换到C | [-36.050, 39.998, 453.874]mm |
| D各轴静止标准差 | [0.409, 0.281, 0.168]mm |
| 28mm→29mm尺寸假设改变后的中心中位差 | 0.612mm |
| 独立C候选与Claude日志中心的三维差 | 0.686mm |

数值一致支持此前“Claude输出更像C坐标”的线索，但无原源码，仍不声称确定其frame或完全复现。每帧D↔C回算误差保存；“旋转分量中位数”和“旋转后分量中位数”一般不相同，因此汇总明确把D中位经R/T得到的C点作为同一个候选，另列独立C统计而不混用。

`report.json` 保存全部30帧和28/29mm比较，`candidate_snapshot_0002.png`已实际查看：黄框为名义方形面，绿十字为**推断的内部中心投影**；`rejected_snapshot_0001.png`不绘制假中心。RGB仅在衍生预览放大/注释，原图未改。小时间波动/框看起来对上不证明<1cm绝对精度；当前10高帧未达采集20帧要求，人工夹持101.5mm未接触仍使pair01仅trial。

## 合成串联与退化

`face_pipeline_simulation.json`：10固定种子，面点各轴0.3mm噪声、Z量化1mm、随机缺30%样本、50个点加入20mm异常，串联面点→中心→5组拟合/1组留出。相机中心误差最大0.303mm、留出95分位0.340mm、安装平移误差最大0.328mm/转角0.0555°。**纯数学点云，不是像素分割/硬件传感器/MoveIt/实体运动仿真，不能当实机精度承诺。**

原标定仿真报告保持：真实对应点各轴3mm噪声时留出p95约13.611mm，不能拿上述理想面点结果替换它。仅偏航/未知工具点仍8/9不可辨识；共线退化拒绝。新测试涵盖完整倾斜面的已知真值、半面缺失拒绝、深度异常点、无点/共线/NaN拒绝、C/D往返、名义尺寸误差、±90°等大安装旋转与共面但非共线点+多倾角情况。

四组指定pytest最终 **76 passed/0 skipped**，没有初始化实体SDK、ROS节点或执行规划/运动；生产5文件hash保持，原115资产hash保持。

`fit_paired_calibration.py --check-only`：从第一/第二组起即可报告当前训练组累计秩和零空间，不拟合/发布候选，验证组不计入训练激励。只偏航8/9时须补倾斜激励或有依据的工具点约束，不继续白采同样朝向。共面位置不等于共线；测试证明多倾角时无需为算法强制垫高物体，但实际夹深一致性仍须现场保证。

## 复现

```bash
cd /mnt/hgfs/ub
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/estimate_calibration_cube_center.py \
  --bundle docs/evidence/piper_calibration_20261014/pair01 \
  --output /home/johnwick/brain_robot_logs/cube_center_NEW --edge-mm 28 29
python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/simulate_paired_calibration.py \
  --face-pipeline --output /home/johnwick/brain_robot_logs/face_pipeline_NEW.json
# 只有新的真实完整点对或明确合成点对才能通过；原空模板应被拒绝
python3 brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/fit_paired_calibration.py \
  --check-only --pairs /path/to/NEW_verified_pairs.json --output /path/to/NEW_excitation.json
```

正式采集仍按 `docs/PIper_CALIBRATION_TASK_20261014.md`：先跑通一组实际夹紧、释放原位、按组授权回观测的同物理中心，再采六组。来源、K/D/R/T/URDF/q/戳保留，不直接把本候选移入生产TF或用旧SDK零戳自动运动。

## 官方明确接口与本项目推断

[PCL平面分割文档](https://pointclouds.org/documentation/tutorials/planar_segmentation.html)明确主平面可用RANSAC/距离阈值/系数优化；本工具用NumPy实现相同基础方法避免新增PCL依赖，2mm阈值是本项目离线设置，不是官方硬件推荐。[OpenCV minAreaRect文档](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html)提供点集包围矩形；它不保证物理面中心。[OpenCV坐标投影说明](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)说明坐标系旋转/平移与内参；实际R/T来源仍是本机原厂档案。面是完整正方形、边长名义28/29mm、未知工具点恒定等是本项目假设，报告中单列，不当官方事实。
