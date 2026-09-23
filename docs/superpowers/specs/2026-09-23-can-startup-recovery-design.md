# PiPER 一键启动 CAN 初始化恢复设计

## 背景与已验证事实

一键启动脚本 `brain_robot_arm/scripts/start_brain_robot_cube_real.sh` 当前会在每次启动时无条件卸载并重新加载 `gs_usb`。在 VMware USB 透传环境中，这会使原本正常工作的 USB-CAN 设备短暂消失或进入无接收状态，随后 PiPER 驱动报告 `can0 is loss`，`/enable_srv` 也不会出现。

人工重新连接 USB-CAN、加载 `gs_usb` 并将 `can0` 配置为 1 Mbps、采样点 0.75 后，已测得接口处于 `ERROR-ACTIVE`，总线错误计数为零，3 秒 RX 增量为 9132 帧。这证明当前机械臂与 CAN 物理链路正常，故障位于启动脚本对正常链路的重复破坏，而不是视觉流程或机械臂运动控制。

## 目标

1. `can0` 已存在时，不再卸载或重新加载 `gs_usb`。
2. 保持现有启动流程、ROS 节点和控制参数不变。
3. 在启动 PiPER 驱动前，必须验证 CAN 接口配置正确且能够收到机械臂反馈帧。
4. 链路无反馈时立即停止，并输出可用于定位的明确错误，不进入 `/enable_srv` 超时流程。

## 修改设计

仅修改脚本中的 `configure_can()`：

- 如果系统中不存在 `can0`，尝试加载一次 `gs_usb`，短暂等待后再次检查；仍不存在则报错退出。
- 如果 `can0` 已存在，直接复用该接口，禁止执行 `modprobe -r gs_usb`。
- 将接口置为 down，配置 `bitrate 1000000 sample-point 0.75`，再置为 up。
- 保留接口为 UP、比特率为 1 Mbps 的现有检查，并增加采样点检查。
- 读取 `/sys/class/net/can0/statistics/rx_packets`，在有限时间内等待计数增长。增长表示机械臂反馈已到达；超时则打印 CAN 状态和计数并退出。

RX 检查采用内核统计文件，不启动额外的 `candump` 进程，也不占用 CAN 控制权。检查只读、开销极低，并且不会改变机械臂状态。

## 明确不修改的内容

- 不修改 PiPER SDK、ROS 驱动、视觉识别、MoveIt、Servo 或抓取参数。
- 不自动更新固件或 Python 依赖。
- 不改变机械臂使能、复位和失能时序。
- 不加入循环重载 USB 驱动或无限重试。

## 验收标准

1. Shell 语法检查通过。
2. `can0` 已存在时执行启动脚本，日志中不出现 `modprobe -r gs_usb` 对应的重载行为。
3. 健康总线上 RX 计数增长后，脚本继续启动 PiPER 驱动，`/enable_srv` 能在原超时范围内出现。
4. 无 RX 反馈时，脚本在启动 PiPER 驱动前退出，并明确报告 CAN 无反馈。
5. 后续相机、视觉、MoveIt 和抓取流程的启动顺序保持不变。
