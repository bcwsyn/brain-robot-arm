# 2026-10-11 选择性部署与真实黑图阻断

起点 `9231e84`。用户允许在既有任务内自主继续；本轮部署已确认的 `56d655b` 近距补丁，未执行关节运动、张闭爪、回零、失能或固件动作。**本轮没有新观测姿态到达或抓取成功证据**，不能把 `[7/7]` 静止启动称为最终验收。

## 部署差异与回退

实际 executor 原源 SHA `107ce501ee2cbf1862f96bf9096ed8fec7c396809fb8c36749222b35d633ce49` 不含规范 OFF-preview。仅迁移近距补丁，补入其所需的共享 `visual_grasp_feedback.hpp`、mutex 和同目标关联距离字段；不迁移预览执行路径、不改原 J5/朝向算法。精确 executor 补丁以 JSON 保存于 `piper_near_depth_selective_executor_20261011.json`（SHA `17167b317bb275945a5d0fda0bf791953587bf11f55e5580f912f4ea37801bd8`），包含源/结果 SHA 和可交给 apply_patch 的文本；JSON 往返一致。恢复时必须先核 base SHA，不把它当第二启动入口。

detector、rgbd_shape_geometry.hpp 和唯一实际 cube_task_real.yaml 仅应用 `git diff 56d655b^ 56d655b` 对应改动；新 near-depth 头与已存在规范 visual 头原样部署。实际 CMake 未改；实际安装二进制及配置是指向 build/source 的符号链接。全部旧源、旧二进制和旧 YAML 已用 `cp --parents -L` 备份至 `/home/johnwick/brain_robot_logs/near_depth_deploy_20261011.C7wU3n/home/johnwick/piper_ws/`。回退必须从这些精确路径恢复或按已核源版本应用逆补丁，不能整包覆盖用户修改。

实际结果 SHA-256：

- executor source：`e97cab06ebdb3a92017030e7442c67afde6dfeb5041dcdd9db2bf6260a0edc5d`
- detector source：`f2519a31b8d348c8101688ddb8f0db8e1ecd36199dae8e61645e0f62969ac623`
- near-depth header：`a663ea30cd090a37ffa10ad887d30a3ac30bac972405d168315db1825639cf10`
- actual YAML：`1a12137ff40dfae9fa2c1e5d93d8fd4ac9b29d869bb2c51eb634983e85ebdca2`
- actual executor bin：`056c4b38e14e8e3bad3e7dba7ce8c73a830b17d977040a712515f27a3d6e0198`
- actual detector bin：`4d5e9ac12e10a801528a3485425a9eb55b6201050f230d2b467cb83b53bd5649`
- original entry remains：`0e976b0ab21b0417a0f2d01b84e39309af37adc269eca2b05232be4c5fdf811e`

命令 `cmake --build /home/johnwick/piper_ws/build/brain_robot_pick_place --target grasp_lift_executor cup_detector_node -j2` exit0；两个目标实际重编译/链接成功，日志无 error/warning 模式。build.txt SHA `adcd08c7f7a8672bc9493906c01fc17c7c46db5b624c60b72efe64a0e05e45ec`。此前84项回归仍是规范版本的测试证据，不冒充本轮重新跑了84项或实机闭环通过。

## 原入口实测和本轮操作错误

原入口以 `BRAIN_ROBOT_AUTO_START=0`、本轮专属 `BRAIN_ROBOT_LOG_DIR` 启动，先核新补丁而不执行已知错误全段转腕。本轮首次错误把测试用 `PYTHONNOUSERSITE=1` 带入生产，driver.log 明确 `ModuleNotFoundError: No module named 'can'`，脚本等待 joint_states 超时、exit1。**这是代理启动环境错误，不是 CAN/硬件故障**。原脚本在 `[1/7]` 前主动终止旧低层驱动，因此旧 SDK50857 不再保留；不能继续称本轮复用了该进程。此失败未发任何运动/使能/失能命令。

随后 `env -u PYTHONNOUSERSITE ROS_DOMAIN_ID=0 PYTHONDONTWRITEBYTECODE=1 BRAIN_ROBOT_AUTO_START=0 BRAIN_ROBOT_LOG_DIR=.../stack_retry /home/johnwick/start_brain_robot_cube_real.sh` 到 `[7/7]`/IDLE；唯一新 SDK63407/PGID63403、detector63685、executor63771。实际近距参数 true，诊断 `NEAR_RGB_FACTORY_CALIBRATION_FROM_RUNNING_DETECTOR`，证明标准参数服务标定读取成功；**没有可靠新 RGB-D seed，预测/夹持分支尚未实机验收**。CAN复用 ERROR-ACTIVE/持续RX、无重载；原脚本自身维护执行，根盘34%→34%，不归因磁盘。

## 黑图判别与可逆曝光对照

独立只读 observer 会话300秒/exit124（预定采集结束），100份快照；不依赖 ready 文件、不发控制命令。新彩色图像约5Hz、时间戳持续增长，深度仍有约5.2万至5.6万个非零像素，中值166–167mm、最小149mm。查看原 RGB `0014_rgb.png` 及增益60时 `0100_rgb.png` 均无可辨紫色方块；新 qualified_color_bbox 的 polygon 为空，target/depth_valid=false。

- 原 gain=0：最近5张灰度均值2.99–3.18/255、所有像素≤14，亮紫色像素0。
- v4l2只读：实际唯一 Dabai DC1 `/dev/video0`，自动曝光3、exposure1000、gain0，其他控制为原值。
- 临时 gain30、5秒/16帧：最后5张均值约11.31–11.34，亮紫色像素均0。
- 临时 gain60、5秒/25帧：均值约20.15–20.51，亮紫色像素仍0，25个 qualified 框均空。
- 两次设备设值/采集均exit0；最后恢复 gain0，读回 auto_exposure3/exposure1000。没有降 HSV/形状/深度门、没有软件填洞或把噪声当方块。

这支持“当前缺乏有效照明/可用彩色观察”，**不能仅凭黑图确定灯开关状态或排除镜头遮挡**。本轮黑图与上一轮“完整彩色方块但局部深度失效”不是同一个现象；不能因近距补丁已部署而在当前真 RGB 丢失状态盲续跑。

## 收尾、原始证据和下一项

本轮原脚本 Ctrl+C 后只输出保持使能/关闭行便exit1，留下部分自有节点；不宣称标准清理成功。核对 UID/PGID 后对自有63722视觉组、63675检测组、63521深度相机组、63509被动抓包组、64183调试窗口组精确 TERM，最终均退出；未重复改启动脚本或终止唯一反馈驱动63403。最终实际只 SDK63407/PGID63403，无相机/高级控制/采集器或自动续跑。

23:39被动收尾复核：157个新反馈，采到的时间戳区间频率199.984Hz、末年龄1.786ms；六轴低速状态字均64，即全部使能且该状态字无故障位。六轴仍 rad `[-.207269608,1.890074844,-1.239431088,0,.908518408,0]`，夹爪缓存.1019m不当真实开口；不把启动读写初始化等同抓取。没有 DisableArm/ResetPiper、夹爪零点或新关节目标。

全部实体产物在 `/home/johnwick/brain_robot_logs/near_depth_deploy_20261011.C7wU3n/`，未提交PNG/大日志/二进制：

- final_feedback.json：`d4027bc257f9c3c802d5c3e20a12cc9c04f9560bed8faf0f7538ed41cbfce488`
- gain30.json：`4beeda0a7c98ebb1251b91535c69f587f550944927ef5666c3b7cd13c4cfb15e`
- gain60.json：`dcd54e184fa4ddab69bee40634131064d2b6a371031f9d1db1485def91fa800d`
- live_observer/observer.jsonl：`80ec60f12d473a46dc14fb1c3ffe0caa32eb4f4909eb69b543afcabf33beeeb6`
- 原0014_rgb.png：`50aaddbf32bf41ebff7a3370099f18fcda0466d9025480657c306cde1255b5c2`
- 增益60的0100_rgb.png：`b2517937980c5ce7c428a7e33bfa7994bb50974b6caa0b189df5caa47687f7d6`

下一先恢复现场照明/排除遮挡并直接看新原 RGB，不需重启机械臂或重测 CAN/固件基线。然后复用本补丁，沿原入口返回观测取得新可靠 RGB-D seed，再验证有限末段的同目标预测、实际两指接触区、夹爪真实开口；既有 J6执行偏差和错误 J5全路径仍未解决，不能把本轮部署当完整抓取完成。GitHub共享main写入授权阻断未变，本轮不再尝试push，仅本地提交。
