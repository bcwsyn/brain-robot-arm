# 2026-10-13 尺度拒绝离线核对

本轮仅诊断与离线回放，没有启动实机、发布运动、改变TF或门限。

## 确切历史事实

- `recovered_onekey/visual_stack.log` 在1791887003.6366报告 `NEAR_RGB_REJECTED:LOCKED_TARGET_SCALE_MISMATCH`。此前同段MoveIt路径100%且适配器接受；不是本次IK/碰撞规划失败。
- 原代码尺度公式为：`growth = seed_color_z / current_model_color_z`；`ratio = current_box_size / seed_box_size / growth`，未裁切的宽或高任一不在原0.65–1.5范围即拒绝。
- 0072原RGB中紫色方块完整可见。历史精确seed框/创建图像stamp/失败图像时刻完整TF没有归档，不能断言实际是哪一轴、哪一精确比例触发。

## 回放方法与限制

复用既有 `review_near_depth_policy` 的同一颜色/矩形门、工厂镜头参数与 `PredictionRejection`。新增 `--scale-details` 仅供离线：不改变默认调用；模拟新鲜度、身份连续及足够路径额度来单独检验尺度分支。它不是实体策略或新运动入口。

`test/review_scale_failure.py` 使用原始归档RGB、真实关节快照、既有保存URDF、未改变的安装配置和工厂D→C。冻结点来自四位小数日志 `[0.4278,-0.1316,0.0874]`；关节快照不是严格图像时刻插值TF。初始图像55–58都是候选，不是实际seed证明。报告明确标记上述不确定性，不能用于下发运动或替换冻结目标。

在停止后0072这一帧，候选回放结果如下（同一原图和模型投影）：

| 候选初始快照 | 宽度比例 | 高度比例 | 原尺度判断 |
|---|---:|---:|---|
| 55（仍对齐中） | 0.720 | 0.815 | 通过 |
| 56（对齐附近） | 0.634 | 0.740 | 宽度低于0.65 |
| 57 | 0.669 | 0.733 | 通过 |
| 58 | 0.712 | 0.777 | 通过 |

候选56：初始框 `[.34375,.354166667,.44375,.483333333]`、模型colorZ≈.297499m；0072框 `[.309375,.725,.428125,.904166667]`，模型colorZ≈.158776m，预测增长≈1.873706。既有代码离线确实返回尺度拒绝；这不是对历史精确seed的恢复。

0072原测量点与RGB同stamp1791887006.1605647；工厂D→C换算实测colorZ≈.217467m，与上述近似模型差约58.69mm。关节快照stamp7006.3418465比图像晚181ms，须保留时间误差限制。

仅作反事实分析，把尺度公式的当前距离改用该帧实测colorZ（不改任何真实目标/TF/代码），候选56的宽/高比例约.868/1.014，均通过原门限。说明距离预测不一致足以影响该尺度判断；不证明实测点是正确夹持中心、不证明外参已校准、不授权将此反事实应用到控制。

## 已补的诊断

- 首次实际seed创建输出创建图像stamp、冻结目标stamp、四边框和colorZ；新增创建stamp仅作元数据，不改变原seed年龄/额度。
- 尺度拒绝时输出同一次原计算的seed/当前框、增长率、宽/高比例、裁切标志与原门限。
- 输出精确图像时刻TF的frame/stamp/平移/四元数、冻结base点、模型depth点和原测量点frame/stamp；明确测量是否被使用。
- 最新反馈q另列为 `LATEST_FEEDBACK_NOT_IMAGE_TIME_Q`，不能把它冒充图像时刻插值关节值。拒绝结果、静态目标、外参、运动和闭爪策略全部保留。

## 复现命令与证据

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_scale_failure.py \
  --capture /home/johnwick/brain_robot_logs/view_guard_20261013/recovered_live \
  --log /home/johnwick/brain_robot_logs/view_guard_20261013/recovered_onekey/visual_stack.log \
  --urdf /home/johnwick/brain_robot_logs/ego_motion_review_20261013/model/move_group.urdf \
  --policy-bin /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place/review_near_depth_policy \
  --output /tmp/piper_scale_review_NEW.json
```

输出路径必须新建，拒绝覆盖已有证据。归档 `/home/johnwick/brain_robot_logs/view_guard_20261013/scale_review.json` SHA-256 `1a150baefa7775ad2229eff02d95dde3e205e00173504971d2b75419f8d28681`；该报告保存输入日志、URDF、配置、工具和原RGB的SHA。未将图片、二进制或大型报告提交Git。

下一步是用真实运行日志取得精确seed和失败帧尺度证据，区分预测距离、可见表面/视角和坐标链；不是先放宽0.65门、硬改J5或改抓取落点。本轮没有实机验收。
