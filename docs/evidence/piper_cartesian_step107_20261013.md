# 2026-10-13 严格同图TF修复后的第107步规划失败

本轮应用版本 `1de994f`。唯一原一键入口完成观测、SEARCH、ALIGN、GRASP_READY，自动41段accepted，到66/89路点（76pregrasp+13descent）后未发布下一段：`AUTOMATIC_RGB_STEP_107 Cartesian path incomplete (fraction=0.500 error_code=1)`。`error_code=1` 不代表路径完整；本段没有被实体执行。未最终DESCENT、闭爪、抬升或释放。

本次日志没有 `NEAR_RGB_EXACT_TF_WAIT` / `RECOVERED` 或尺度advisory；之前64–65附近的TF失败本次未复现，但不能据此声称实体迟到恢复分支已验证。方法回归的330ms迟到恢复、旧latest拒绝与反馈过期拒绝均通过，合计50项仅软件验证。

## 精确失败请求

- 参考frame `base_link`，规划link `link6`（不是直接指尖原点）。
- xyz=`[.356857981294,-.116217684731,.255850261273]`m。
- quaternion(xyzw)=`[.142500640034,.973832380585,-.028854231209,.174675400261]`。
- 规划起点q=`[-.313241908,1.762576648,-1.367435160,0,.889591668,-.020688584]`rad。
- 本轮MoveIt fraction .5是直接停止原因；不能由一次数值IK推断全部碰撞、路径约束、跳支或其他分支已排除。

## 只读离线IK对照

复用 `test/review_jaw_scene.py::poses()`，读取既有归档 `ego_motion_review_20261013/model/move_group.urdf`，不是本轮新导出的模型。URDF SHA256 `a93ac8cba44d02dc09ca52442bb72e8d8c92f97dd732cee08702e1fe9438c581`。以同一PLAN_START为数值起点，SciPy least_squares目标残差=`20*(FK位置-请求位置)`与旋转向量误差；max_nfev300，ftol/xtol/gtol1e-12，夹爪模型开口99.6mm。只有FK/IK数值，不导入ROS、不发命令、不检查场景碰撞。

| 数值求解范围 | 求得J3（rad） | 位置残差（mm） | 朝向残差（度） | 边界 |
|---|---:|---:|---:|---|
| 原任务范围 | -1.400000000 | .331110 | .676872 | J3下限 |
| 原任务范围+既有.005rad规划余量 | -1.395000000 | .540063 | 1.105593 | J3下限 |
| 归档URDF范围（仅离线反事实） | -1.407918980 | ≈0 | ≈0 | 非边界 |

归档范围精确邻近解q=`[-.315372011,1.781966998,-1.407918980,.002782658,.927999052,-.026049180]`rad。该J3超出现有task下限-1.400及既有规划余量下限-1.395；原范围最优局部解卡J3边界，支持“指定完整6D姿态在当前任务范围内受限”线索。**这不是全局无解证明、不是MoveIt碰撞诊断、不是当前硬件限位重新确认；不允许将归档URDF范围当实机授权，更没有执行这组解或修改任何限位。**

不能把“优化器converged=true”当作原范围的精确IK成功：两组都有非零姿态残差。下一优先在原范围内复用已有MoveIt/姿态容差选择可达末段朝向，而非盲增J5、降低J3软下限或发布半段路径；该新增控制代码修改需用户先确认，当前没有实现。

## 实机结束证据

本轮0030与0068原RGB/depth/debug已实际查看：完整紫色方块一直位于十字下方，两指可见但未包围。0068 RGB/debug stamp1791895400.573478、depth5401.851888、q5401.931233；debug .215m/3013样本，不是深度全零。后续0180墙钟5741是同一停机后缓存，不当作当前视觉证据。最终只读SDK stamp5746.997076/200Hz、high5746.992976/100Hz、6使能true，q=`[-.313408774,1.763515583,-1.368163601,0,.890065559,-.020699605]`rad，J5≈51.0°。CAN RX10799245/TX59658/error-drop0。

原主session11052 rc143/cleanup完成，未DisableArm/Reset/自动零点。两只读采集INT后各rc0；当前无本轮driver/adapter/controller/grasp/采集、不自动续跑。根分区88%9.2GB，仅既有清理脚本0，无ENOSPC。不需要重启机械臂。

证据根 `/home/johnwick/brain_robot_logs/view_guard_20261013/`：`tf_wait_onekey/visual_stack.log` SHA `3a5d1074045b21b54b402db8056b8c3f95069f85cc0697ee3d5ff1c7225820af`；`tf_wait_ik_comparison.txt` SHA `ab0b1a6974f9f0ff0f1b5cea96040c07cad061b664775c9ce3f0e0f98f980d67`，另 `tf_wait_onekey_console.txt`、`tf_wait_exact`、`tf_wait_live`。图像、模型、二进制和原大日志不提交Git。
