# 第五位置接管跳变：获准的离线局部修复（2026-10-15 17:52 +08:00）

用户明确同意“仅解除这处接管逻辑的冻结，先修复并离线验证，不立即运动”。仅改规范仓库原适配器及测试，不部署、不启动ROS节点/相机/SDK/CAN，无使能、arm、张爪、失能或运动。其他生产算法、门、限位、模型、TF/TCP、一键入口继续冻结。B检查点仍`1a2e633`，原资产不改，正式A仍0、本组未完成，合格完整总数仍1/6。未推送GitHub。

## 原因与最小修改

1. 原arm保存真实q，但持位tick调用视觉裁剪，将J3从−1.551364696直接推到−1.4rad，隐含8.672558°运动。现越界实测保持原值，不把Jog当作越界恢复；零增量也不强推到视觉包络。正常Jog仍用原包络，裁剪不得扩大或反向请求步长。
2. 原轨迹先限速再裁剪结果，近边界起点也可能突破步长。现先限制期望点，再从实测限速，原轨迹准入不改。
3. 轨迹完成当tick先发布最后有界步，不被同tick持位覆盖；下一tick恢复原持位处理。不增加到位阈值/超时或新恢复轨迹。
4. 再arm清旧轨迹，防隐式续跑；仍清零速度和待发夹爪帧，不凭arm开闭夹爪。

按仓库ros2-piper-debug与surgical-change技能核真实路径并限定修改，没有另写运动程序或通用DDS配置。

## 离线验证

- [verification.json](verification.json)：AST提取原/新纯函数，复用原B实测q；原J3跳变0.151364696rad，新跳变0。六关键原检查/夹爪函数AST完全相同，不初始化ROS/访问CAN。
- [junit.xml](junit.xml)：**152项通过**（适配器77、原采集/质量/诊断75），使用真实消息对象及内存publisher替身，不创建Node或spin。覆盖原B连续100个hold tick、六轴两端/正反Jog、超时、arm前置条件、夹爪帧、近边界限速与单/多点末步。
- 早已通过原准入的−1.45→−1.4rad示例：20ms、原速度0.189rad/s，原跳0.05rad，新步0.00378rad。它只验证限速顺序，**不构成实机越界恢复许可或第五组返回方案**。
- 开发首轮红测41失败/26通过，复现原缺陷；首修66通过/1失败是ROS数组与list直接比较，改list比较；新增边界回归后152全通过。纯回放脚本初版parents层级错使git读取失败，修成parents[6]后返回0；均不涉及硬件故障。

## 实际路径、哈希、未部署及回退

实际原一键→`/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py`→install软链→`/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py`。

- 原适配器/仍在home的运行副本SHA：`a5074c614fcc1b7f57854e2693e689337577567dde0ca7765470df52fa1347d8`。
- 仓库候选SHA：`47c8b7864c714de2ff85b9bea7ae722d57152c349fa235665f1b8830bf0c2b18`，未同步到实际运行副本，不声称一键已使用修复。
- 实际一键、任务YAML、检测YAML、原抓取执行器SHA与前轮冻结基线相同；launch/模型/TF不改。根约34GB可用，无本轮删除，不提交其他既有改动。
- 回退基线`be7c7c0`：只取该提交的原适配器版本，审阅后单独提交；不要整仓reset/revert或覆盖他人改动。未部署，所以运行副本无需回退。
- 共享目录普通沙箱创建失败，精确escalated仅用于创建此证据目录、保存生成报告和Git；不改挂载/chmod/sudo策略。

## 尚未打通与下一步

原准入函数保持：第五组真实J3首点越界被拒；直接用−1.4rad首点则差0.151rad、超过原0.10rad起点容差，仍拒。**持位不跳变不等于越界起点能返回**；本轮没有扩大限位、放宽容差、伪造起点或新增恢复接口。

下一先审阅真实起点返回方案及其必要范围，再按批准决定部署及本组实体动作。不能直接一键、重采同一B或沿用旧组许可。原位张爪/回观测/正式A均未执行；没有持续反馈，之前六true/36.5mm只是历史记录，不是本轮实时值。

## 复现（仅离线）

在规范仓库运行，纯回放返回0：

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \
  docs/evidence/piper_calibration_p1_20261015/new_pair06/attempt01/offline_takeover/verify_offline.py
```

测试返回0；实际执行还带`--junitxml=/tmp/piper_takeover_offline_20261015.xml`：

```bash
source /opt/ros/humble/setup.bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_piper_jog_adapter.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_ir_depth_diagnostic.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_native_depth_diagnostic.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_depth_controls_readonly.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_capture.py \
  brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_calibration_p0_quality.py
```

`verify_offline.py --output NEW_PATH`仅排他新建结果、拒绝覆盖旧报告；原B/raw目录不改。
