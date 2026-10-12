# 2026-10-12：夹爪首目标握手修复与未完成的实机验证

## 修改及软件验收

起点 `f605d47`；用户“继续完成”承接上一轮已说明的最小方案。实现提交 `1e489de`（fix: use vendor gripper enable handshake）。仅改供应商现用 `piper_ctrl_single_node.py` 的两个显式夹爪入口与对应测试，不改启动脚本、YAML、六轴轨迹、适配器5帧、反馈超时、零点或TCP。首目标为 `GripperCtrl(0, effort, 0x02, 0)` → `GripperCtrl(0, effort, 0x01, 0)` → 目标/`0x01`，之后仅发目标/`0x01`；六轴使能不会注入夹爪目标。这是夹爪状态握手，不是 DisableArm；握手中的0x01/angle0本身包含零位置闭合请求，不能称整段无夹爪动作。

依据是上一轮已审阅的 [AgileX V2 gripper demo](https://github.com/agilexrobotics/piper_sdk/blob/master/piper_sdk/demo/V2/piper_ctrl_gripper.py)。采用其顺序是软件修复假设，不是实体故障根因证明。

规范源：`brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py`；实际源：`/home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py`。实际 build 模块解析到实际源，install 的 entry-point 经 piper.egg-link 导入 build。三者SHA-256均为：

`d607ec10854f231588fcdfc9f334c4766d5b8c4474e10fd72f79ef5723984b2e`。

本轮没有运行 colcon；此处为 symlink 源同步及新进程重载，不宣称完成全工作区重建。语法使用内存 compile，无需在只读仓库写pyc。首次py_compile误写一次路径、随后遇到只读pyc写入，已更正；首次AST检查错误地用 ast.walk 顺序作源顺序，改为 lineno/col_offset排序后8/8 unittest通过。两次 unittest discovery 对pytest函数得到0项，不算验收。最终命令为：

```bash
source /opt/ros/humble/setup.bash
source /home/johnwick/piper_ws/install/setup.bash
PYTHONPATH=/mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper:$PYTHONPATH \
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  /mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper/test/test_command_validation.py \
  /mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_piper_jog_adapter.py
```

结果：**15 passed in 0.71s，exit0**。这些只验证软件契约，不证明 CAN 握手或实体闭合成功。

## 真实执行顺序与观察

普通沙箱ps没有显示主机PID，不能据此断言旧驱动不在。一次普通沙箱nohup启动在DDS建socket时被Operation not permitted拒绝，未建立ROS节点；日志 `/home/johnwick/brain_robot_logs/gripper_handshake_20261012/piper_driver.log` 先保存该错误。提升只读ps后查到旧63403/63407，精确TERM其组退出，无硬件失能。一次主机nohup新驱动75129/75131曾启动后未持久存活，不计运行成功。

最终使用持久PTY session4211启动唯一驱动75274/75292，ROS_DOMAIN_ID=78，现有 `/home/johnwick/fastdds_udp_only.xml`，`auto_enable=false/gripper_exist=true`，现有 joint_states_single→/joint_states、joint_ctrl_single→/joint_commands remap。域78仅用于本次既有适配器诊断，不更改生产脚本的域配置。真实关节快照 stamp1791768432.586031746：

```text
q(rad)=[-0.207269608,1.890074844,-1.239431088,0,0.908518408,0]
gripper(m)=0.1019
```

唯一原适配器PID75488/session5756，实际install脚本；参数 motion_enabled=true、joint_state_timeout_s=.5、gripper_command_repeats=5、gripper_effort_nm=1.0。`/enable_srv true`、`/piper_jog_adapter/enable_motion`、`/arm`均响应成功。没有MoveIt、搜索或抓取执行器。驱动使能响应不是本轮保存的逐轴硬件使能位证据。

09:36:33 的归档探针向原 `/brain_robot_grasp/gripper_command` publish了0mm请求；收592条0x3A7全为position101900/status64，524 ROS样本前后六轴/夹爪不变。紧接的只读3秒统计601条、199.934671Hz、最大间隔8.101482ms。适配器早在1791768850.350045274（约09:34:10）已经因 joint state timeout 软件disarm；本次没有观察到新driver的Calling GripperCtrl日志，因此**不能说新握手已经执行而硬件不动**。`command_sent=true/physical_commands=1`仅是探针publish尝试字段，不是下游接收、CAN发送或实体动作确认。SDK local_loopback=false，未见0x159回显本身亦不能否定发送。

重新 `/arm`响应成功后，09:44:33再次运行探针，0 CAN帧、0 ROS样本，未见握手调用。工具调用/CLI耗时造成arm与publish之间有间隔，不能称原子、立即或闭合验收。驱动PTY日志显示1791769422.651256360反馈丢失，1791769447.652992495报告已无反馈25秒，保持receive-only；这次已有独立原始RX反证，不只凭ROS discovery判故障。

注意：既有归档 `piper_gripper_close_20261012_probe.py` 内含两个 `if __name__ == '__main__'` 和两段main，实际先闭爪请求采样，再运行只读稳定性采样。本轮没有改这个历史脚本；输出第二个JSON是只读3秒统计，不是第二次闭爪。这也解释为什么一个调用输出两个JSON。新鲜度/发现不足时不再用其publish字段当物理动作计数。

## 当前阻断、一次恢复与收尾

实际can0 UP/ERROR-ACTIVE/1Mbps/.750/qlen1000，但两秒RX `180987617→180987617`；`timeout 4s candump -L can0`无帧、exit124。USB `003/008 1d50:606f`仍枚举。sudo -n true返回0。最新内核只有09:52:43的gs_usb_timestamp_work CPU警告；tail中xHCI DMA错误来自10月11日19:30，不能伪称新发生或已证实当前根因。

先 `/piper_jog_adapter/disarm`返回success=true；之后仅按已授权固定恢复尝试：

```bash
sudo -n ip link set can0 down
sudo -n ip link set can0 type can bitrate 1000000 sample-point 0.75
sudo -n ip link set can0 txqueuelen 1000
sudo -n ip link set can0 up
```

串行set-e命令在第二条返回 `RTNETLINK answers: No such device`/exit1，后两条未执行。随后ip -brief可见can0 DOWN，USB仍枚举；没有再次盲目USB reset/gs_usb/xHCI重载，未刷固件、MasterSlaveConfig、ResetPiper或0xAE。不能把当前状态写成已恢复UP，更不能无反馈继续运动。此阻断不能证明机械臂硬件坏、灯光故障或握手方案无效。

软件disarm后向session5756 Ctrl-C，退出适配器；driver Ctrl-C一次未立即退出，补发后在10:04核对75274/75292已经不存在，随后精确TERM命令返回“没有那个进程”，未杀其他目标。main收尾只destroy/shutdown，无DisableArm。**没有发送硬件失能；最新硬件使能/实际姿态因无反馈无法重新确认，不以历史true代替当前证据。** 本轮无自动续跑，无成功闭合/抓取/抬升/释放。

## 接手与回退

1. 第一条 `git -C /mnt/hgfs/ub show --stat --oneline HEAD`，读最新进度与本文，再用主机只读ps确认无遗留driver/adapter。普通沙箱ps不能证明主机无进程。
2. 当前接口恢复遇到设备失活，既有guest重载无效记录继续复用；需要恢复USB-CAN/VMware实体反馈链。若新接入后can0为DOWN且设备操作有效，仅固定1Mbps/.75/qlen1000/up，短期RX持续增长才准入；不因ERROR-ACTIVE字样独自放行。
3. 重用实际原driver和adapter，用一个有界编排同时等待新鲜六轴反馈、发现subscriber、arm并publish一次；记录实际driver 0x02→0x01→target日志及前后0x3A7。若未发送，不计硬件无响应试验。不得增加超时绕过反馈或用旧缓存续跑。
4. 用户批准的代码回退基准：`1e489de`的父提交 `f605d47`。需要回退时用 `git revert 1e489de`保留后续记录和他人改动，再同步实际driver、核hash并重载唯一实例；本轮未执行回退。
5. 灯光恢复后再回原一键流程推进抓取，不能把夹爪软件测试当SEARCH/实体目标或完整抓取验收。

Git仅本地；origin仍 https://github.com/bcwsyn/brain-robot-arm.git / main。已有共享main写入授权审核阻断未解除，本轮不重试push；未提交PDF、固件、reference、日志、二进制或既有vendor/Astra改动。
