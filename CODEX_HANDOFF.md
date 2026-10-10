# PiPER ROS 调试完整交接记录

更新时间：2026-10-10 22:33（后文保留历史背景）

## 本轮最新实机状态（22:29:55–22:32:04）

直接运行原有`/home/johnwick/start_brain_robot_cube_real.sh`，没有另写/修改一键脚本。命令与完整记录见[`docs/PIper_PROGRESS.md`](docs/PIper_PROGRESS.md)最新条目；原始日志目录：`/home/johnwick/brain_robot_logs/real_full_20261010_stamped_tf/`。

结果：默认`AUTO_START=1`通过[1/7]–[7/7]，观测轨迹被接受并到达`OBSERVE_POSE_REACHED`；随后执行中心局部搜索、回中心及FULL_SEARCH，目标检测有效后进入ALIGN和`GRASP_READY`。不是一键脚本没启动或只运行了固定角度。

新断点明确为抓取执行器立即报`STATIC_TARGET_MODEL_UNAVAILABLE`：在GRASP_READY时，最后成功变换到`base_link`的活动目标已过期73.619秒（门限0.60秒）；原图像采样时刻TF查询在搜索运动期间反复future extrapolation。它在开爪和预抓取之前失败，因此本轮没有靠近/张爪/闭爪/下降/抬升/释放。脚本按原规则停输出、软件disarm，未发`DisableArm`、`ResetPiper`或归零；最后被动CAN位姿约`[-0.263980,0.971073,-0.741876,0,0.741457,0] rad`，夹爪反馈0.1021m。

运行执行器与规范源码一致（源SHA-256 `1f55f026…`，叠加层二进制`c6624512…`），真实YAML SHA-256 `907e3d06…`；启动脚本SHA-256 `e8c9f85c…`，本轮未改。任何修复应只让抓取工作线程短暂等待下一条能以**原消息时间戳**变换的目标帧，限定现有0.60秒；不恢复latest TF、不放宽任何门、不改运动轨迹/外参/夹爪。本修改需等待用户按其要求批准。此间无控制节点运行。

注意：本文件以下20:21、20:47等段落均是历史状态；若其表述与上方22:29–22:32实机结果冲突，以本页本轮最新实机状态和`docs/PIper_PROGRESS.md`首条记录为准。相机—指尖7cm/10.5cm是镜头安装外参的测量输入，不是额外施加在靠近轨迹上的偏移；不要为本轮TF时间戳错误删除它。

这份文件用于把 Windows Codex 会话中的 PiPER 调试上下文交接给虚拟机中的 Codex。虚拟机共享目录对应：`/mnt/hgfs/ub`。

最新代码更新：用户批准后，规范仓库 `grasp_lift_executor.cpp` 的活动 RGB-D 目标参考系变换和闭爪前夹持区校验均改为使用观测消息时间戳，不再以 latest TF 代替；添加了采样时间/TF时间及点坐标诊断。时间戳为零或无法查询时不做该次转换，闭爪核验不通过，不产生补偿运动。唯一实体配置当前 `depth_only_target_enabled=false`，备用 depth-only 回调未改。Humble 离线构建成功且该包6个测试目标全部通过，但代码尚未部署到运行工作区，也没有实机/一键流程验证；运动参数、相机外参和轨迹均未改变。用户报告的约5–8cm向下、沿臂当前朝向向后约8–10cm仅作为未标定现场观察记录。精确代码提交与 `git revert` 命令见 `docs/PIper_PROGRESS.md` 最新记录。

最新状态：20:21–20:22再次以`AUTO_START=1`运行未经修改的一键入口，顺利完成[7/7]、观测、中心优先搜索、ALIGN、GRASP_READY、79点预抓取、8点笛卡尔下降和一次落点纠偏。纠偏后模型tip误差7.3mm，但闭爪前`FreshFaceInsideJaws()`失败，状态`FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，没有闭爪/抬升/释放；检测器在接近期间报告target LOST。该错误文本共用多个分支，无法仅凭它断言目标3D坐标错或实体几何在两指外。原始CAN反馈显示J5在TARGET_ACQUIRED后仍处ALIGN期间由约`+0.478`升至`+0.734rad`；TARGET_ACQUIRED是进入ALIGN，不是对齐完成。YAML以J5作为竖直图像纠偏轴（sign +1），但没有逐帧图像误差/命令速度，无法认定符号错误。进入抓取器后实际J5在预抓取从`+0.738`降至`+0.290rad`，末段下降再降至`+0.2126rad`，规划末端目标z由0.208降至0.180m。日志及本轮关节/落点数值见[最新交接](docs/PIper_HANDOFF_20261010.md)和[进度首节](docs/PIper_PROGRESS.md)。50mm开口请求反馈仍为102.1mm。脚本清理后栈进程退出，未发ResetPiper/DisableArm，脚本报告保持使能。无源码/YAML/启动逻辑改动；任何代码修改须先向用户说明并获批准。下一步若获批准，仅加非行为性ALIGN与夹爪判定诊断，不放宽执行门。
20:47–20:50仅相机读取：相机当前RGB帧严重洋红偏色，未清晰看到紫色块/完整夹爪；深度中位244mm是相机距离，不是桌面高度。URDF有夹爪及手指碰撞网格，但arm目标链与配置末端是link6，使用0.1358m固定指尖偏移。用户报告实体指尖离桌面约90mm，与上轮7.3mm模型FK残差不能直接比较；需同时间对齐相机/桌面/关节/TCP。图片见`/home/johnwick/brain_robot_logs/camera_inspection_20261010_2048/`。本次只启动相机读帧，无机械臂运动；任何代码或运动参数改动仍须先获用户批准。
实体方向判断以用户观察为准：机械臂从弯曲变直就是上抬/远离，不能仅凭J5角度符号反推。代码链不是一条MoveGroup直达目标轨迹：TARGET_ACQUIRED后仍是图像误差驱动的ALIGN/MoveIt Servo；到GRASP_READY后Servo才停，抓取器随后执行MoveGroup预抓取和Cartesian下降。因此需先确定上抬发生在哪个状态段；对齐尚未完成时应查视觉ALIGN方向/误差，对齐后则查3D目标位姿、TF/TCP和MoveGroup路径。任何源码改动仍须先向用户说明并得到批准。

## 历史暂停交接（2026-10-10 18:24）

接手更新：用户随后要求恢复项目工作。已在隔离MoveIt验证保持对齐朝向的79点预抓取+9点完整末段，并将新模式接入原执行器（尚未实体执行）。当前入口/证据/新版本与剩余夹爪/FOV问题见 [最新接手更新](docs/PIper_HANDOFF_20261010.md) 首节；下段保留暂停时历史状态，不能覆盖最新进展。

用户要求暂停并由此前参与项目的老师傅接手。实机控制栈和本轮只读采集器已经退出；18:23:39确认六轴静止、保持使能，未回零或失能。接手先完整阅读 [本轮交接记录](docs/PIper_HANDOFF_20261010.md)。

历史settled_fix确实完成靠近/下降，失败于闭爪反馈46.2 mm；本轮当前部署版同一入口到达观测、SEARCH、ALIGN和GRASP_READY，但24个顶抓候选全部IK -31，退出于预抓取规划。当前夹爪反馈102.1 mm，两次运行证据必须分开。暂停后不自动续跑；本轮未部署任何新抓取策略。


## 1. 目标

唯一总目标是让 `~/start_brain_robot_cube_real.sh` 一键启动流程完整、稳定地运行到紫色方块视觉搜索和抓取阶段。

当前阶段优先级是先恢复 PiPER 六轴的正常关节位置控制，因为这是启动脚本继续进入观测姿态、视觉搜索和抓取的前置条件；但机械臂恢复只是总目标的第一阶段，不代表可以忽略 Astra、点云、MoveIt、TF、视觉检测或抓取逻辑。低层运动恢复后，应继续验证同一个启动脚本的全部阶段。

当前最直接的异常是：机械臂可以持续返回高速电机反馈，也可以成功使能，但通过 SDK 的 `MotionCtrl_2()` 和 `JointCtrl()` 发送 J2 小幅位置目标时，J2 基本不运动；视觉流程因此在零点复位或观测姿态准备阶段卡住。

## 2. 硬件与运行环境

- 主机：Windows，VS Code 通过 SSH 连接 Ubuntu 虚拟机。
- 虚拟机用户：`johnwick`。
- ROS：ROS 2 Humble。
- PiPER ROS 工作区：`~/piper_ros`。
- 视觉工作区：`~/piper_ws`。
- 共享目录：虚拟机 `/mnt/hgfs/ub`，Windows 侧为 `C:\ub`。
- USB-CAN：Geschwister Schneider CAN adapter，USB ID `1d50:606f`。
- Linux CAN 接口：`can0`。
- CAN 参数：bitrate `1000000`，sample-point `0.75`。
- 内核驱动：`gs_usb`。
- PiPER 固件版本：`S-V1.8-2`。
- 当前 Python SDK：`piper_sdk 0.6.2`，位置通常为 `/home/johnwick/.local/lib/python3.10/site-packages`。
- 当前 SDK 类：`C_PiperInterface_V2`。
- 原始旧仓库曾使用：`C_PiperInterface`，SDK 曾为 `piper_sdk 0.4.2`。

## 3. 当前代码状态

当前驱动源文件：

`~/piper_ros/src/piper/piper/piper_ctrl_single_node.py`

曾从供应商目录复制过：

`/mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py`

然后执行过：

```bash
cd ~/piper_ros
colcon build --symlink-install --packages-select piper
source ~/piper_ros/install/setup.bash
```

当前驱动使用 `C_PiperInterface_V2`。驱动通过 `/enable_srv` 接收 `piper_msgs/srv/Enable`，通过 `/joint_commands` 接收 `sensor_msgs/msg/JointState`，发布 `/joint_states` 和 `/arm_status`。

当前驱动关键逻辑：

- `enable_callback()` 和 `/enable_srv` 回调调用 `_enable_for_joint_control(50)`。
- `_enable_for_joint_control()` 最终调用 `EnablePiper()`，并设置普通 CAN 关节控制模式。
- 关节回调将弧度转换为约 `57324.840764` 的 0.001 度单位。
- 关节回调调用 `JointCtrl(joint1, ..., joint6)`。
- 驱动增加了高速反馈新鲜度检查；如果高速反馈丢失，会暂时抑制控制输出，超过约 2 秒退出。
- 反馈门控日志曾出现：
  - `can0 feedback lost; suppressing output for up to 2.0s`
  - `can0 feedback recovered after ...`
  - `can0 is loss`

## 4. 已确认的 CAN 状态

CAN 初始化成功时的典型状态：

```text
can state ERROR-ACTIVE
bitrate 1000000 sample-point 0.750
bus-errors 0
arbit-lost 0
error-warn 0
error-pass 0
bus-off 0
```

正常运行时 CAN RX 持续增长。例如 3 秒 RX 增量约 9000，25 秒采样中每 0.25 秒窗口约 744～776 帧，没有完全无帧窗口。

曾经出现过 `ERROR-PASSIVE`、大量 dropped/TX 异常，但通过：

```bash
sudo ip link set can0 down
sudo modprobe -r gs_usb
sudo modprobe gs_usb
sudo ip link set can0 up type can bitrate 1000000 sample-point 0.75
```

重新恢复为 `ERROR-ACTIVE`。USB-CAN 设备重新枚举后接口名仍为 `can0`。

## 5. 已确认的反馈帧

通过 SocketCAN 原始接收、`candump` 和 tcpdump 观察到持续反馈：

```text
0x251  J1 高速反馈
0x252  J2 高速反馈
0x253  J3 高速反馈
0x254  J4 高速反馈
0x255  J5 高速反馈
0x256  J6 高速反馈
0x261..0x266  其他电机反馈
0x2A1..0x2A8  标准状态/关节反馈
0x3A0..0x3A7  另一组状态反馈
```

典型高速反馈：

```text
J1 pos=0
J2 pos=2
J3 pos=-7
J4 pos=0
J5 pos=-8
J6 pos=0
```

`GetArmHighSpdInfoMsgs()` 的时间戳和频率正常，通常约 `200 Hz`。

但是 `GetArmJointMsgs()` 在一些运行中时间戳为 `0`、Hz 为 `0`。因此不能使用 `GetArmStatus()` 或 `GetArmJointMsgs()` 的零时间戳判断实时高速反馈是否正常；当前可靠的健康源是 `GetArmHighSpdInfoMsgs()`。

## 6. 已确认的使能行为

以下调用多次成功：

```python
p.EnablePiper()
```

输出通常为：

```text
Enable: True
六轴使能状态：[True, True, True, True, True, True]
```

ROS 服务也曾成功返回：

```text
piper_msgs.srv.Enable_Response(enable_response=True)
```

但“六轴已使能”不等于“位置控制目标已被控制器接受”。

## 7. 关节限位问题已经处理过

曾经查询到所有关节角度限位为 `-1`：

```text
J1 max_angle_limit=-1 min_angle_limit=-1
...
J6 max_angle_limit=-1 min_angle_limit=-1
```

随后执行过官方参数恢复逻辑（恢复默认关节限位、最大速度、最大加速度）。再次查询得到正常值：

```text
J1: -1500 .. 1500, max speed 300, max acc 500
J2:     0 .. 1800, max speed 300, max acc 500
J3: -1700 ..    0, max speed 300, max acc 500
J4: -1000 .. 1000, max speed 300, max acc 500
J5:  -700 ..  700, max speed 300, max acc 500
J6: -1800 .. 1800, max speed 300, max acc 500
```

随后曾有一次官方顺序测试成功让 J2 运动约 `2988` 个 0.001 度单位（约 2.99 度）。因此“限位一直为 -1”已经不是当前唯一解释，不能继续重复恢复限位作为主要排查方向。

## 8. 运动测试结果

多次执行过以下基本流程：

```python
p.ConnectPort()
time.sleep(2.0)
p.EnablePiper()
for _ in range(30):
    p.MotionCtrl_2(0x01, 0x01, 10, 0x00, 0, 0x01)
    p.JointCtrl(0, 500, 0, 0, 0, 0)
    time.sleep(0.02)
```

结果不稳定，但最近多次结果是：

```text
EnablePiper() -> True
六轴使能 -> 全 True
J2 目标 -> 500（0.001 度单位）
J2 实际位置保持约 2
J2 变化 -> 0
CAN TX 增量 -> 约 414 或约 134
CAN 状态 -> ERROR-ACTIVE，无 bus-off
```

另一组较早测试曾在默认参数恢复后让 J2 从接近 0 移动到约 2988，因此当前问题不是“SDK 永远不能运动”，而是控制路径/状态在不同运行时条件下不一致。

## 9. 控制反馈读取结果

调用：

```python
p.GetArmModeCtrl()
p.GetArmJointCtrl()
```

最近输出：

```text
模式控制反馈：
time stamp:0
Hz:0.0
ctrl_mode:1
move_mode:1
move_spd_rate_ctrl:50

关节控制反馈：
time stamp:0
Hz:0
Joint_1:0.000
Joint_2:0.000
...
```

这里的 `ctrl_mode=1`、`move_mode=1` 不能单独证明控制器确认了命令，因为时间戳仍为 0，极可能只是 SDK 本地缓存或默认值。需要检查 SDK 底层接收路径和真实反馈帧。

## 10. tcpdump 原始数据分析

抓包命令曾成功运行：

```bash
sudo -v
sudo -n timeout 8s tcpdump -i can0 -nn -e -XX \
  >/tmp/piper_wire_tcpdump.log 2>/dev/null &
```

抓包文件约 32023 行，说明 tcpdump 正常工作。原始数据示例：

```text
0x0010: a003 0000 0800 0000 0100 0100 0000 0000
0x0010: 5102 0000 0800 0000 0000 fff0 0000 0000
0x0010: 6102 0000 0800 0000 00e6 0025 1f40 0000
0x0010: 5202 0000 0800 0000 0000 0127 0000 0002
0x0010: 5302 0000 0800 0000 0000 fbb0 ffff fff9
```

这些可以解码为：

- `a0 03` -> `0x3A0`
- `51 02` -> `0x251`
- `52 02` -> `0x252`
- `53 02` -> `0x253`
- `61 02` -> `0x261`

在已提供的 tcpdump 样本中没有看到控制帧 ID 的对应字节：

- `51 01` -> `0x151`
- `55 01` -> `0x155`
- `56 01` -> `0x156`
- `57 01` -> `0x157`

注意：之前直接用 `grep -E '151|155|156|157'` 是错误的，因为会匹配时间戳或任意十六进制内容，不能代表 CAN ID。

还看到过：

- `0x473`
- `0x47C`
- `0x476`

这些与使能/参数响应相关，不是关节位置控制帧。

`/sys/class/net/can0/statistics/tx_packets` 会增加，例如 TX 增量 134 或 414。这只能证明 SDK 向 SocketCAN 提交了发送请求，不能单独证明控制帧已经被机械臂控制器接受。

## 11. 主从配置纠错

此前多次讨论并执行过：

```python
p.MasterSlaveConfig(0xFC, 0x00, 0x00, 0x00)
```

此前把 `0xFC` 简单解释为“从臂”是错误的。官方 V2 接口文档定义：

- `0xFA`：teaching input arm
- `0xFC`：motion output arm

官方双臂文档中通常把 teaching input 称为 master，把 motion output 称为 slave；但这只适用于双臂联动语境。

更重要的是，官方单臂示例并不需要调用 `MasterSlaveConfig()`，而是直接连接、使能、设置 CAN 关节模式、发送关节目标。

因此当前约束：

- 不要继续在 `0xFA` 和 `0xFC` 之间来回切换；
- 不要再执行 `ResetPiper`；
- 不要在没有新证据时修改持久主从/联动配置；
- 先确认控制帧实际是否进入 CAN 物理链路。

## 12. 已观察到的 ROS/视觉问题

视觉一键脚本：

```bash
bash ~/start_brain_robot_cube_real.sh
```

流程包含：CAN、PiPER 驱动、Astra RGB-D、紫色方块检测、MoveIt、Servo、真机保护适配器。

曾出现以下独立问题：

1. 驱动进程退出：

```text
can0 feedback lost; suppressing output for up to 2.0s
can0 is loss
```

2. 视觉适配器超时失能：

```text
PHYSICAL MOTION DISARMED: joint state timeout
```

3. TF 门控失败：

```text
MISSING_TF base_link<-link8
```

或：

```text
Lookup would require extrapolation into the future
```

4. MoveIt 自体过滤后的点云不可用：

```text
未收到 MoveIt 自体过滤后的点云；拒绝开始使用可能含有机械臂自体点的 Octomap。
```

5. Astra 原始深度图、深度内参正常，约 30 Hz；点云约 3.7 Hz，且可能受到 TF 门控影响。

这些视觉/TF 问题必须与 PiPER 低层运动问题分开处理。当前首先要让低层单臂 J2 小幅运动测试稳定成功，再恢复视觉流程。

## 13. 当前最可信的根因范围

已排除或明显降低优先级：

- USB-CAN 完全断开：不符合持续 200 Hz 反馈；
- CAN bitrate 完全错误：不符合稳定反馈；
- 所有关节限位仍为 -1：已恢复并验证正常；
- 六轴完全没有使能：`EnablePiper()` 和六轴状态成功；
- 单纯机械臂完全失能：手动控制时关节曾可保持，反馈正常；
- ROS `/joint_commands` 完全没有发布：此前能看到约 50 Hz 命令和 TX 增量。

仍需确认：

1. `MotionCtrl_2()` 和 `JointCtrl()` 在 SDK 0.6.2 中的底层发送函数是否真的调用了 CAN bus send；
2. 这两个调用返回的 `SendCanMessage` 实际结果是什么；
3. SDK 是否因为当前接口/角色/固件状态，把运动命令发到了不同 ID 或被内部条件抑制；
4. tcpdump 是否能捕获真正的 TX 控制帧，还是只看到了 RX 反馈帧；
5. 固件 S-V1.8-2 与 SDK 0.6.2 的运动控制协议是否完全兼容；
6. 是否有 SDK 初始化参数、CAN auto-init、过滤器或线程状态导致反馈正常但控制发送异常。

## 14. 推荐下一步

不要再改主从配置。先做代码级、只发送一次小目标的诊断：

1. 在当前安装的 `piper_sdk 0.6.2` 中定位 `MotionCtrl_2`、`JointCtrl` 的实现；
2. 打印它们内部 `SendCanMessage` 的返回值和实际 CAN ID；
3. 在 SDK 发送函数附近增加临时日志，确认是否经过发送调用；
4. 同时用 tcpdump 原始字节检查 `51 01`、`55 01`、`56 01`、`57 01`；
5. 只有在确认控制帧已经实际发出后，才继续分析固件是否接受；
6. 低层测试稳定后，再启动 `piper_single_ctrl`、视觉适配器和 MoveIt。

## 15. 运行时安全要求

- 发送运动命令前，确认机械臂周围无障碍物和人员。
- 所有测试优先使用 J2 小于 0.5 度的目标。
- 不要同时运行多个 `piper_single_ctrl`、视觉适配器或 Servo 控制器。
- 启动新控制器前检查：

```bash
pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node'
```

- CAN 异常后可先停止 ROS 控制器，再重载 `gs_usb` 和重新配置 `can0`。
- 不要把 `GetArmStatus()` 时间戳为 0 的缓存当作实时运动确认。

## 16. 官方参考

- PiPER V2 接口文档：
  https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD
- PiPER 双臂配置说明：
  https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/double_piper.MD
- PiPER SDK 仓库：
  https://github.com/agilexrobotics/piper_sdk

## 17. 给下一位 Codex 的启动提示

请先完整读取本文件，再检查虚拟机中当前代码、SDK 安装位置和运行进程。不要假设主从配置就是根因，也不要直接执行 `MasterSlaveConfig(0xFA)`、`MasterSlaveConfig(0xFC)`、`ResetPiper` 或固件升级/降级。先用源码和返回值证明 `MotionCtrl_2()`、`JointCtrl()` 的真实发送路径，再继续处理。

## 18. 任务执行授权与 Git 历史

用户的唯一总目标是让 `~/start_brain_robot_cube_real.sh` 一键流程完整运行到紫色方块搜索和抓取阶段。用户会在真实机械臂旁边看护，并能够随时断电/急停；因此可以在完成安全检查后，由 Codex 自主执行必要的终端诊断、编译、启动/停止 ROS 节点和小幅真机验证，不要每一步都停下来要求用户重复确认。

真机运动前仍必须：

- 说明即将发送的目标、单位、预计动作和停止条件；
- 读取当前高速反馈并确认时间戳新鲜、六轴状态和限位正常；
- 对未测试关节保持当前实际位置，不要把其他关节随意设为绝对零位；
- 发现 CAN 反馈丢失、位置异常、状态突变或控制器退出时立即停止发送并报告。

除当前工作树外，应主动检查 Git 资料：

- `~/piper_ros/.git`
- `~/piper_ws/.git`（如果存在）
- `/mnt/hgfs/ub/.git`（规范 Git 根目录；Windows 对应 `C:\ub\.git`）
- `git log --all --decorate --oneline`
- `git reflog --all`
- 供应商代码目录 `vendor/piper_ros`

重点寻找曾经成功让 J2 运动、成功启动 `start_brain_robot_cube_real.sh`、恢复关节限位和修复驱动反馈门控的提交、分支、补丁或脚本。先只读比较工作树、历史提交和当前安装文件，再决定是否应用修改。不要覆盖用户现有未提交改动；如果需要修改，先保存当前 diff，并做最小可回滚修改。

如果仓库配置了远程 GitHub remote，可以读取远程历史和已验证代码；GitHub 不是本地终端日志的替代品，仍需以虚拟机当前实际安装的代码、SDK、固件反馈和 CAN 抓包为最终依据。

## 19. 已审查过的关键参数差异

下一位 Codex 必须逐项核对这些参数，不能只看类名或单个 API 是否返回成功：

### Python SDK 与接口类

- 曾经能运行的旧组合：`piper_sdk 0.4.2` + `C_PiperInterface`。
- 当前安装组合：`piper_sdk 0.6.2` + `C_PiperInterface_V2`。
- 当前运行时 SDK 路径：`/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`。
- 必须确认 ROS 驱动实际加载的 SDK 路径，而不是只检查 shell 中的 Python。
- 必须确认 `ros2 run piper piper_single_ctrl` 使用的是重新编译后的 `install/piper`，不是旧进程或旧 overlay。

### SDK 初始化参数

已使用或测试过的参数组合包括：

```python
C_PiperInterface_V2(
    can_name="can0",
    judge_flag=False,
    can_auto_init=True,
)
```

曾测试过的附加参数：

```python
start_sdk_joint_limit=False
start_sdk_gripper_limit=False
```

`can_auto_init=False` 时必须先调用 `CreateCanBus`，否则 `ConnectPort()` 会报：

```text
Interface 'can_auto_init' is False and '__arm_can' is None!!
```

诊断过程中曾观察到 SDK/接口使用 `local_loopback=False`。因此 `candump` 或 tcpdump 看不到同机 TX 回显，不能直接证明 SDK 没有发送控制帧；必须结合内核 TX 计数、tcpdump 原始字节、发送函数返回值和实际反馈综合判断。

### ROS 驱动启动参数

当前单臂驱动常用启动参数：

```text
-p can_port:=can0
-p auto_enable:=false
-p gripper_exist:=true
-r joint_states_single:=/joint_states
-r joint_ctrl_single:=/joint_commands
```

不能把 `auto_enable:=false` 与“机械臂未使能”混为一谈；这只表示由服务/外部流程触发使能。必须确认 `/enable_srv` 调用成功后驱动内部 `__enable_flag` 和六轴硬件状态都为真。

### MotionCtrl_2 参数

当前官方普通关节位置控制测试使用：

```python
p.MotionCtrl_2(
    ctrl_mode=0x01,
    move_mode=0x01,
    move_spd_rate_ctrl=10或50,
    is_mit_mode=0x00,
    residence_time=0,
    installation_pos=0x01,
)
```

其中：

- `ctrl_mode=0x01`：CAN 控制；
- `move_mode=0x01`：关节位置模式；
- `is_mit_mode=0x00`：普通位置控制，不是 MIT 模式；
- 速度比例曾分别测试过 `10`、`20`、`50`、`100`；
- 不能把 `0xAD` 或 `0xFF` 误当成普通位置模式参数。

### JointCtrl 单位与目标构造

`JointCtrl()` 的关节单位是 `0.001°`，不是弧度，也不是 `0.001 rad`。例如：

```text
500 = 0.5°
250 = 0.25°
3000 = 3.0°
```

真实测试时如果只验证 J2，必须读取当前高速反馈，并构造：

```text
J1=current_J1
J2=current_J2+250
J3=current_J3
J4=current_J4
J5=current_J5
J6=current_J6
```

不能因为机械臂软件零点看起来接近零，就把其他轴全部发送为绝对零位。

### 关节限位/速度/加速度参数

曾出现查询结果 `max_angle_limit=-1`、`min_angle_limit=-1`。之后已通过官方参数恢复逻辑恢复出正常限位和速度/加速度值。下一位 Codex 必须先读取当前值再判断，不要假设它们又恢复为 `-1`，也不要重复写参数作为默认修复动作。

### 反馈参数与健康判断

- 高速反馈 ID：`0x251..0x256`，频率约 `200 Hz`，目前是最可靠的实时健康源。
- `GetArmJointMsgs()` 在部分运行中时间戳为 `0`、Hz 为 `0`；不能把它当作有效实时反馈。
- `GetArmStatus()`、`GetArmModeCtrl()`、`GetArmJointCtrl()` 时间戳为 `0` 时，返回结构中的数值可能只是缓存/默认值，不能作为控制器已确认的证据。
- 驱动的反馈门控使用高速反馈时间戳；检查它是否读取了真正会更新的字段，避免把未更新缓存误判为新鲜反馈。

### CAN 接口参数

```text
interface: can0
bitrate: 1000000
sample-point: 0.75
driver: gs_usb
```

曾经发生过接口重载后 `can0` 消失、ERROR-PASSIVE、TX dropped 增长等情况。遇到这些现象，应先停止 ROS 控制器并恢复 CAN 接口，再解释上层运动结果。

## 20. 额外的历史陷阱与成功条件

### 曾经成功过的控制顺序

历史上能让 J2 运动的可靠顺序是：`ConnectPort`，等待真实高速反馈，`EnablePiper/EnableArm(7)`，确认六轴使能，再发送 `MotionCtrl_2(0x01, 0x01, ...)` 和持续的 `JointCtrl`。不要在确认使能前发送位置目标，也不要把 SDK 方法返回成功当成机械臂已经运动。

### 必须只有一个低层 PiPER 驱动

过去曾同时出现多个 `piper_single_ctrl`、多个 `cube_detector` 和多个视觉启动进程。多个驱动会造成 CAN 竞争、错误的 `/joint_states` 发布者和视觉适配器订阅到旧状态。每轮测试前必须检查并确保只有一个低层驱动和一个视觉控制栈；不能只杀掉 ros2 launch 父进程而留下子节点。

### 驱动退出日志的含义

```text
can0 is loss
ROSInterruptException: rclpy.shutdown() has been called
RuntimeError: Context must be initialized before it can be shutdown
```

后两个异常是当前退出清理路径的缺陷，真正要先处理的是前面的 CAN 反馈丢失。看到 `Enable status: True` 不能忽略后续反馈门控退出。

### `/joint_states` 与视觉适配器是两条独立链路

曾出现高速 CAN 反馈约 200 Hz，但 `/joint_states` 发布者为 0，或视觉适配器报告 `PHYSICAL MOTION DISARMED: joint state timeout`。必须分别验证高速 SDK 反馈、驱动是否发布 `/joint_states`、消息时间戳是否更新、适配器是否订阅正确话题，以及唯一低层驱动是否接收到视觉命令。CAN 正常不等于 ROS 关节状态正常，命令话题有 50 Hz 也不等于机械臂执行了运动。

### 启动脚本的清理和复用逻辑

`start_brain_robot_cube_real.sh` 会初始化/复用 CAN、启动或复用 Astra、检测器、MoveIt、Servo 和视觉适配器，并在失败时停止本轮进程，但可能留下上一轮子节点。因此脚本重启前必须检查进程树、话题发布者数量和服务存在性，避免第二套控制器竞争。

### Astra、点云与 TF 的实际现象

已验证 RGB/深度图约 30 Hz，深度内参约 28～30 Hz，原始点云约 3.7 Hz；点云 TF 门控曾出现 `MISSING_TF base_link<-link8` 和 `Lookup would require extrapolation into the future`。即使 `tf2_echo base_link link8` 在当前时间能查到变换，带历史 cloud stamp 的 TF 查找仍可能失败。必须同时核对 cloud/TF 时间戳、`/clock`、`use_sim_time`、frame_id、QoS 和旧的 `pointcloud_tf_gate` 实例。

### Fast DDS 共享内存错误

```text
RTPS_TRANSPORT_SHM Error
Failed init_port fastrtps_port....: open_and_lock_file failed
```

这可能来自旧进程、共享内存锁文件或多个 ROS 环境残留，不能直接当作 PiPER 或相机硬件故障。判断服务不可用前要先确认旧 ROS 进程和通信资源状态。

### 启动脚本最终验收标准

总目标只有在以下条件同时满足时才算完成：脚本不因 `/enable_srv` 超时退出；只有一个 PiPER 驱动和一个视觉控制栈；`/joint_states` 持续更新；六轴能从软件零点运动到观测姿态；Astra RGB、深度、点云和 TF gate 达到脚本要求；紫色方块检测持续有效；视觉搜索能离开 PREPARE；GRASP_READY 后抓取、抬升和释放动作实际完成；反馈丢失或目标丢失时会安全停止；最终保存驱动、视觉和关键 ROS 话题日志。

## 21. 磁盘空间、Git 留痕与任务恢复要求

### 磁盘空间不足时的固定处理

每次启动脚本前和长时间测试前检查根分区使用率。如果发现磁盘空间紧张、根分区使用率达到项目脚本的阈值（通常为 85%），或者 ROS 日志/构建失败明确提示空间不足，只执行项目已有的清理脚本：

```bash
~/clean_disk_space.sh
```

不要临时编写 `rm -rf` 清理命令，不要删除整个工作区、`.git`、源码、SDK、构建缓存中尚未确认的内容，也不要把用户日志直接上传到远程仓库。清理后重新检查 `df -h`，并把清理前后空间、脚本返回码和影响记录到进度文件/Git 提交中。

### 每次修改必须记录到 Git

每次修改代码、配置、启动脚本、参数文件或诊断脚本前：

1. 在相关仓库执行 `git status --short` 和 `git diff`；
2. 保存或明确区分用户原有未提交修改；
3. 只提交本次任务产生的最小修改；
4. 使用能说明原因和验证结果的提交信息；
5. 记录实际运行的测试、返回值和仍存在的风险。

不要提交密钥、密码、个人隐私、巨大日志、构建产物、临时抓包或模型文件。若诊断需要保存输出，应放在明确的日志目录并在 Git 中只提交摘要、路径、时间和结论。

### 每次阻断也必须记录到 Git

遇到服务等待超时、CAN 反馈丢失、TF gate 拒绝、点云不足、硬件风险、权限不足或无法继续的情况，不能只在聊天中报告。应在工作区维护一个进度文件，例如：

```text
docs/PIper_PROGRESS.md
```

每次阻断至少记录：时间、当前 Git commit、执行的命令/实验、观测结果、已排除的原因、阻断原因、下一步和是否需要用户确认。阻断记录也要提交到对应 Git 仓库，除非仓库不存在或当前操作本身被 Git 阻断；此时要在可写的共享交接文件中记录。

### 每次重新拾起任务必须先读 Git 进度

Codex 每次新建会话、重启 VS Code、重启虚拟机或从阻断状态恢复时，必须先执行并阅读：

```bash
git status --short
git log --oneline --decorate --all -n 20
git reflog --all -n 20
```

然后读取仓库中的 `docs/PIper_PROGRESS.md`（如果存在）、`CODEX_HANDOFF.md`、最近相关提交的 diff 和最新日志，再决定下一步。不能只依赖聊天上下文，也不能重复已经完成或已经证明无效的实验。

### 进度提交内容

每个阶段结束时，提交应至少包含以下一种明确结果：

- 已验证的代码/配置修复；
- 可复现的诊断脚本；
- 真实测试结果摘要；
- 明确的阻断记录和下一步；
- 启动脚本阶段通过/失败的证据。

如果一次真机测试没有修改源码，也应提交测试摘要或进度记录，避免下一次恢复任务时丢失实验结果。

## 22. 唯一 Git 仓库与跨账号恢复协议

本任务只使用一个规范 Git 仓库作为长期上下文和进度的唯一事实来源：

```text
Windows: C:\ub
虚拟机: /mnt/hgfs/ub
Git 根目录: /mnt/hgfs/ub/.git
```

当前已确认 `C:\ub` 是 Git 仓库；`C:\ub\brain_robot_arm` 当前不是独立 Git 仓库，不能把它当成第二个进度仓库。`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws` 是否是 Git 仓库必须单独检查，但它们不能替代规范仓库。

所有长期上下文必须保存到规范仓库中的可追踪文件，不要只放在聊天窗口、`/home/johnwick/CODEX_HANDOFF.md` 副本或未提交的本地日志中。至少维护：

```text
CODEX_HANDOFF.md                 # 稳定背景、约束、已验证事实
docs/PIper_PROGRESS.md           # 按时间记录每次实验、修改、阻断和下一步
docs/PIper_DECISIONS.md          # 已确认的架构/参数决定及证据
```

如果规范仓库中不存在 `docs/PIper_PROGRESS.md` 或 `docs/PIper_DECISIONS.md`，首次恢复任务时应创建并提交；不得只在 `/home/johnwick` 创建另一份孤立文件。

### 每次新账号/新会话的固定恢复顺序

无论是否切换 ChatGPT/Codex 账号、VS Code 窗口、模型或虚拟机，Codex 必须先在规范仓库执行：

```bash
cd /mnt/hgfs/ub
git status --short
git log --oneline --decorate --all -n 30
git reflog --all -n 20
git show --stat --oneline HEAD
sed -n '1,240p' CODEX_HANDOFF.md
sed -n '1,240p' docs/PIper_PROGRESS.md 2>/dev/null || true
sed -n '1,240p' docs/PIper_DECISIONS.md 2>/dev/null || true
```

然后再检查 `/home/johnwick` 中的运行时副本是否与规范仓库相关文件一致。若不一致，先记录差异并判断哪个是当前实际生效文件，不能静默覆盖。

### 每次工作循环的固定顺序

```text
读取 Git 进度
→ 检查当前工作树和运行时路径
→ 计划一个最小可验证动作
→ 执行诊断/修改/测试
→ 把结果、阻断和下一步写入 docs/PIper_PROGRESS.md
→ 把代码/配置/文档和进度一起提交到规范仓库
→ 报告 commit ID、测试结果和剩余风险
```

切换账号后不依赖聊天历史；只依赖规范仓库中已经提交的文件和 Git 历史。远程 GitHub 如果存在，只作为同步/审查来源；在提交成功前，不能把只存在于 GitHub 工作区、聊天内容或虚拟机未提交目录中的信息当作已保存进度。

## 23. 无 CAN RX 时的硬件优先检查

如果启动脚本停在 `[1/7]`，并同时出现“sudo 凭据缓存失效”“can0 没有新 RX”“SDK 没有高速反馈”，必须先停止所有运动和 ROS 控制器，把问题分成权限、USB-CAN、CAN 接口和机械臂物理链路四层检查。不能直接重启视觉流程，也不能发送运动命令。

先刷新 sudo 凭据，但不要把 sudo 错误误判为机械臂故障：

```bash
sudo -v
```

然后只读检查：

```bash
lsusb | grep -Ei '1d50:606f|OpenMoko|CAN' || true
lsmod | grep gs_usb || true
ip -brief link show can0 || true
ip -details -statistics link show can0 || true
```

解释顺序：

- `lsusb` 看不到 `1d50:606f`：优先检查 USB-CAN 是否插好、VMware USB 设备是否仍连接到虚拟机、USB 线和适配器指示灯；
- `lsusb` 能看到但没有 `can0`：检查 `gs_usb`/`can_dev` 模块和接口枚举；
- `can0` 存在但为 DOWN：只在确认 USB-CAN 已识别后配置 1 Mbps、sample-point 0.75；
- `can0` 为 UP 但 3～5 秒 RX 增量为 0：检查 PiPER 主电源、机械臂控制器是否启动、CAN_H/CAN_L 是否接反/松动、USB-CAN 到机械臂的连接、终端电阻和 CAN bitrate；
- `can0` RX 恢复后才允许启动 SDK 或 ROS 驱动；
- RX 恢复但 SDK 无高速反馈：再检查 SDK 接口、进程竞争和反馈 ID，不要先改主从配置。

RX 只读测试：

```bash
RX1=$(< /sys/class/net/can0/statistics/rx_packets)
timeout 5s candump -L can0
RX2=$(< /sys/class/net/can0/statistics/rx_packets)
echo "RX 增量：$((RX2-RX1))"
```

如果机械臂主电源已确认开启、USB-CAN 已识别、can0 已配置但 RX 仍为 0，必须让用户检查实际 CAN 线缆、供电和适配器连接，必要时在机械臂安全静止状态下重新插拔/重新上电。未恢复 RX 之前，不得运行 `EnablePiper`、`MotionCtrl_2`、`JointCtrl` 或完整视觉启动脚本。
