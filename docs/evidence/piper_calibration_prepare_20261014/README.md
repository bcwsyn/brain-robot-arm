# 标定准备与历史归因核查（只读/离线）

本目录不是正式标定结果。pair01原始包原样保留在相邻 `../piper_calibration_20261014/pair01`，生产TF/运动代码未修改，未启动机器人。任务范围见 `../../PIper_CALIBRATION_TASK_20261014.md`。

## 已证实的数字与限制

- 决策文档在插入本轮规则前，按带日期标题 `^#+ .*2026-10-DD` 计数：10/10=32、10/11=42、10/12=25、10/13=50，共149；是文档条目，不等于149次代码修改或实测。
- `brain_robot_arm/docs/purple_cube_real_arm_roadmap.md`（9/22）确实要求固定目标、单姿态短靠近的粗抓取先行，三次至少一次真实闭爪抬升；动态预测/重识别/主动扫描和复杂重规划属后续。当前尚无通过该实体验收的证据。
- 现原launch第58–64行及任务配置明确腕部点云不写实体Octomap，不能将当前阻断直接归为夹爪点云进入Octomap。CAN/xHCI、夹爪CPV/零点、磁盘95%有历史记录；本轮根盘54%/35GB、共享73%/138GB，不清理，不把全部通信问题归因磁盘。
- 安装外参/实际工具点未验证是事实，尚不能证明它们是全部失败的唯一根因。“所有门都是临时安全门”“操作者一直不在造成延误”证据不足。标定后不自动删除反馈/限位/碰撞/完整轨迹检查。

## 原生同一像素的缺深度

`sampling_report.json` 用未变生产D→C/K/端点缩放复算30帧；高支撑10/低支撑20，组表面点相距24.766897mm。第一张高支撑帧（snapshot2）的实际原生采样像素作为共同足迹：高层零值比例中位0.003586（0.36%），低层0.877049（87.7%）。低帧对应原生区域确有空洞，不仅是安装TF不同造成少采；传感器算法/材质/遮挡/相位的底层原因尚不唯一。

两张预览：左原RGB；中放大彩色轮廓及真实深度投影（红）；右同一原生ROI热图（固定420–480mm），黑为真实0、白为选中边界。已实际查看低帧方块仍在RGB，深度区大面积黑。边缘剩余样本不能当几何中心，不把低帧456–462mm混入准确中心。衍生图单独保存，原图未改。

复现（必须使用新输出路径）：

```bash
cd /mnt/hgfs/ub
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_pair_sampling.py \
  --bundle docs/evidence/piper_calibration_20261014/pair01 \
  --output /home/johnwick/brain_robot_logs/pair_sampling_NEW
```

## 拟合/可辨识性仿真

`simulation_report.json` 为**纯数学合成**，不是实体或碰撞可行性仿真。SciPy Rotation/least_squares解安装6自由度+工具中心3参数；完整激励恢复平移误差3.723e-16m/转角4.404e-14°。只偏航、未知夹深：秩8/9，即使残差很小仍不返回外参候选。已知且经过验证的工具点模型可用分散点解6参数；共线对照不返回候选。

20种子相机各轴3mm噪声仿真的留出误差95分位13.611mm，**不是实机精度保证**。训练点统一25mm偏差对照有很小训练残差而留出误差>20mm，说明只看训练残差不够。缺失中心拒绝，不填null；trial排除而非低权重混入；报告累积秩/零空间/条件数及基座xyz误差，验证组不参与初始化和训练。

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/simulate_paired_calibration.py \
  --output /home/johnwick/brain_robot_logs/paired_simulation_NEW.json
```

不重复旧 `review_calibration_sampling.py` 的完整姿态手眼/隔离MoveIt实验，新点对模型不虚造目标旋转使用完整姿态API，不生成实体关节轨迹。

## Claude日志的采用边界

附件只是日志片段，无 `calib_lib.py`、`cube_center_check.py` 完整源码/逐帧法向/frame声明。其报告29mm、10高帧、面边中位28.623/30.611mm，中心 `[-0.0355760684,0.0404914246,0.4539179508]m`、标准差[1.201,.346,.089]mm，仅**待复现候选**。29mm不是本地卡尺事实，低标准差不证明绝对中心。

若把中心直接当D坐标，与原生表面中位 `[-.0108475531,.0387098210,.44]` 相差[-24.729,1.782,13.918]mm。若它属于C，按工厂 `p_D=R_DCᵀ(p_C-t_DC)` 转回得到 `[-.0125410392,.0414725878,.4535313016]m`，相对表面为[-1.693,2.763,13.531]mm。后者较符合半边长内移，但**只是坐标归属线索，不确认它就是C**；表面中位也不等于面中心。

本机原helper/vendor URDF独立FK复核：人工T及30观测T最大矩阵误差均0（原`.017444`单位），只证明软件与归档一致，不证明实体支架/TCP已标定。初次内联FK命令括号错误rc1，规范多行复算rc0；不当硬件问题。

本轮远端 `origin/main=402f5e1` 新增两项水杯仿真提交，不含上述Claude标定源码；只fetch审查，未merge/覆盖/运行。源码可获得后优先复用，不重采相同数据或直接部署未说明frame的中心。

## 采集准备与未完成

`collect_static_rgbd.py` 只补逐帧完整CameraInfo K/D/R/P/ROI与原反馈字段，新增可选3s静止证据窗；默认.25s/120ms/.5s/60帧/120s均保持，是采集约束不是实体门。`collect_calibration_sdk.py`仅被动`piper_init=False`，保存raw q/Hz/聚合戳/六enable/速度/真实开口；默认6s/上限10s，SDK聚合时间不冒充逐轴硬件戳，不猜实物接触。合成空跑不等于实体合格点。

source `/opt/ros/humble/setup.bash` 后初次50项通过（未source为48通过/2skip）；补合成SDK序列化空跑后最终**51通过/0skip/rc0**，缺实体中心模板的拟合CLI按预期rc2/candidate null。未运行实机/新SDK/部署。普通apply_patch首次创建新证据目录失败，保留已完成脚本改动、用限定提权mkdir新目录后继续；不chmod挂载/清盘。

下一：复用并核对Claude中心源码的frame/法向，先采一组真夹紧同点、核对夹深，再六组。实际中心/安装矩阵/抓取尚未完成。
