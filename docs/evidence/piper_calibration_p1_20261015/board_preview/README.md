# 32mm棋盘格独立静止预览：可见局部图案，不能据此正式标定

2026-10-15 22:22 +08:00。用户“已铺好标定板，并且此时方块的位置也没有改变”，另报“单格32mm”。原第六方块A/B记录保持不变；本轮只读拍摄和关节采集，没张爪、回观测或移动机械臂，没有新A/B、PnP、手眼解算或生产TF部署。

## 实际看到什么

[首张原始RGB](portable/capture/evidence/0001_rgb.png)清楚显示黑白棋盘格，但整板外缘在320×240视野之外，方块/夹爪遮挡下部。完整方格/内角点行列数、板坐标原点/方向仍未知，不从裁切图猜测。32mm为用户报告，未卡尺核验；详见[board_definition.json](board_definition.json)。

[局部候选叠图](corner_diagnostic/local_candidates_only.png)与[完整诊断](corner_diagnostic/report.json)：固定3×3局部内角点模式，5/5算法返回候选；遮挡附近一个候选索引跨帧包围框对角变化11.604px，局部单应拟合RMS3.637—3.979px。部分候选落在受物体遮挡影响的边缘，因此**found=true不是正确全局角点或正式标定成功**。3×3不是本板规格，不据此计算位姿、赋板全局角点ID或修改生产TF；诊断残差也不是新增生产/运动门。

## 原始数据和核验

- 原成功五帧工具的独立会话，原5对RGB/uint16深度/完整同戳Info/实际q/模型FK/当前CC1365304DG工厂值；相机17.579483秒/35秒，全部自有源退出。近距目标深度为空只保存原值，棋盘格本次仅用RGB做局部角点诊断，不用方块800点规则否定棋盘格。
- SDK60/59fresh、5.822879秒，原速度/静止规则全窗通过。当前q_mdeg[-6793,111368,-68208,-6021,44213,11353]、六true/37mm；只是当次历史遥测，不追溯谁导致与上次B的轻微数值差。每张图使用自己实际q/FK，不借旧姿态补值。
- RX58782359→58823174，TX15663不变，无运动/使能/arm/开闭/失能/Reset/MasterSlaveConfig/刷写/链路恢复。六冻结源前后SHA一致，home旧adapter未部署候选；`git diff HEAD -- .../new_pair07`空，原第六A/B记录/同点确认/原图SDK归档均不改。根33GB余量，无数据清理。
- [portable/manifest.json](portable/manifest.json)19便携原资产，含5原图、完整Info/源戳、实际q/FK/SDK、相机工厂内参和D→C及旧配置快照，逐SHA验证。通用导出器的`cube_edge_mm_approximate=29`仍指既有紫色方块，**不是棋盘格格长**；32mm单独记录，未把两者混用或运行方块中心拟合。
- [runtime_closed.tar.gz](runtime_closed.tar.gz)及[runtime_manifest.json](runtime_manifest.json)：35原始文件逐成员SHA回读验证，无删图/填深度0。[assessment.json](assessment.json)、[board_execution.json](board_execution.json)、[execution.json](execution.json)保存实际角色、命令/时序/退出码；旧复用wrapper的preview/Afalse/Bfalse标签保留，不据旧标签宣称新点对。
- [review_board_preview.py](../review_board_preview.py)只读离线局部诊断，无ROS/CAN/相机/控制API。[test_board_preview.py](../test_board_preview.py)6项合成回归通过，[junit.xml](junit.xml)可核验；不以合成测试宣称实机标定精度。执行编排[executed_preview.py](executed_preview.py)、原五帧工具[executed_original_capture.py](executed_original_capture.py)、[打包脚本](package_offline.py)保留。

本机源目录`/home/johnwick/brain_robot_logs/new_pair07_preview.ayb60z6j`，编排/诊断目录`/home/johnwick/brain_robot_logs/piper_board_preview.5cks5pix`。Git中的原件/归档可独立读取，不依赖本机路径。未推送GitHub。

## 下一步

建议先取得本次**原位张爪→沿已有观测轨迹返回→SEARCH前停，只拍完整棋盘格**许可。完整板图后代理自行数行列/核对角点、确认规格与固定情况，再提出是否改用标准多姿态板手眼流程的具体方案及验收；原方块数据保留作对照，生产TF和原流程冻结不动。当前尚未获该动作授权，没有自动返回/搜索或设计新关节动作，也没有直接替换原5+1标定协议。
