# 关灯期间夹爪专项核验（2026-10-12）

起点9a6dccb。用户确认灯全关，询问可提前完成的工作。本轮只读实际反馈和离线测试；没有实体使能/位移/开闭/失能/写零点、重启驱动或CAN接口。未完成真实抓取，也未验收夹爪开闭恢复。采用仓库ROS2/PiPER调试与手术式修改技能限定范围，无生产改动。

## 当前硬件报文事实

- 唯一SDK PID63407、PGID63403，wrapper63403，auto_enable=false/gripper_exist=true。读图只见feedback驱动/daemon/本轮observer；observer退出后没有新增后台节点。
- 8秒接收1672帧0x3A7；原始帧时间戳区间199.998207Hz。所有position字段101900（协议单位0.001mm）、status0x40。最后载荷00018e0cffb34000，力矩-77（0.001Nm）。
- 0x3A7按现驱动同一映射为0x2A8，在**纯parser**离线解码；与独立有符号大端int32/int16逐帧一致，差异0。没有创建新SDK接口/ConnectPort。
- ROS /joint_states_feedback 1600条/199.997374Hz，gripper.1019m，与原始报文一致；六轴q=[-.207269608,1.890074844,-1.239431088,0,.908518408,0]rad，采样范围均0。不是实体开口101.9mm的独立测量。
- 本轮0x159和/joint_commands为0条，两个命令话题图上无发布者；观察静止不能证明“刚发的目标无响应”。raw_feedback_age_ms是本地出队/解析年龄，不用于宣称硬件端到端时延；ROS年龄同为本地接收时间。
- 排除当前纯ROS旧缓存/SDK换算造成101.9；尚不能区分实体基准、标定/位置语义、机构响应等假设。不能硬件归罪，也不能直接归零或软件抵消101.9。

## 官方明确事实与项目推断

[官方V2接口](https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD)说明0x159的位置单位0.001mm，0x03使能清错，0xAE将当前位置写作零点；[官方反馈类](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/piper_msgs/msg_v2/feedback/arm_feedback_gripper.py)的位定义与本机SDK一致。0x40仅表示使能位为1、六个故障位0、回零位为0。它不能独立证明真实机械零点/夹指间距，也不能证明“未归零必然导致当前不动”。

[官方零点示例](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_set_gripper_zero.py)会先失能夹爪再写当前位置为零。**只读参考，没有运行**；官方普通开闭demo中的立即零目标初始化也没有照搬。实体完全闭合基准未知，用户历史确认已更正为未完全闭合，故不使用旧确认写0xAE。上游master资料用于语义参考，不是本机0.6.2已升级的证据。

项目已做过首帧0x03及普通目标多帧无响应试验，本轮不重复它们。9d2b53a已去除机械臂正向使能中的意外夹爪零目标，但不等于实体开闭已恢复。本轮不新增抓取/六轴靠近门。

## 针对性离线测试

两份指定测试15 passed in0.63s，exit0；没有ROS节点、SDK控制接口或实体输出。覆盖正向使能不写夹爪、六轴保持无夹爪、显式50mm/1Nm首0x03后0x01且set_zero0、adapter5帧有界七项effort。不是实体开闭成功证据。

```bash
source /opt/ros/humble/setup.bash
source /home/johnwick/piper_ws/install/setup.bash
export PYTHONPATH=/mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper:"$PYTHONPATH"
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  /mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper/test/test_command_validation.py \
  /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_piper_jog_adapter.py
```

PYTHONNOUSERSITE仅用于离线测试，不能传入生产一键/反馈驱动（本机can/SDK位于user-site）。

## 只读采集复现

仅限现有can0、唯一现有驱动；脚本无bus.send，无Enable/GripperCtrl/SDK接口/服务调用。数据见同名JSON，脚本已小文件归档。

```bash
env -u PYTHONNOUSERSITE bash -c '
source /opt/ros/humble/setup.bash
source /home/johnwick/piper_ros/install/setup.bash
export ROS_DOMAIN_ID=0 FASTRTPS_DEFAULT_PROFILES_FILE=/home/johnwick/fastdds_udp_only.xml PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 /mnt/hgfs/ub/docs/evidence/piper_gripper_dark_20261012_probe.py
'
```

驱动规范/实际SHA：c0153c88e0e5ac5ff9d8d1b299e4c911c62e14b8f0834e25d5c0d67f6de299cb。
原入口SHA：0e976b0ab21b0417a0f2d01b84e39309af37adc269eca2b05232be4c5fdf811e。
采集脚本SHA：97e74e4aca74352a755494de0bdab5d3b8d48766470207eb7603cb316594a9bf。
执行/测试/状态核对均exit0；一条只读rg误指moveit_config脚本路径已由rg --files改正，无生产影响。

## 后续可提前做与实体验收边界

暗处可完成命令/单位/拒绝原因/失效回放和关闭流程的离线回归；不需新训练集或重复固件/CAN诊断。真实开闭恢复下一步须可观察夹指和接触区，并明确实际开口基准，再经原adapter/driver发一次有界显式目标，配套观察0x159、0x3A7新响应和实际开合方向。未知101.9基准不把80mm命令叫“只张开”，未知完全闭合不写零点。

无需为灯光阻断重启机械臂。本轮保持六轴当前位置、未失能，不自动续跑；只有反馈驱动保留。仅本地提交，未同步GitHub，之前主分支写入审查阻断未获新的明确授权，本轮未重复推送。
