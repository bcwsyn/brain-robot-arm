# 宿主重连后的原观测续跑：仍未到位，新的非法USB回显/接收停流

本包是 `board_resume01` 之后的独立原件，不改写其历史失败或归档。

## 实际执行

1. 用户明确完成USB-CAN宿主侧重连。新ifindex5初始DOWN，按已有许可固定1Mbps、sample-point0.75、queue1000并UP；没有再次USB reset/模块重载。
2. 原被动SDK6秒60fresh、q波动0、末六true/夹爪99.6mm；RX持续增长，TX0。整窗速度静止rc2且无合格3秒子窗，原序列保留。
3. 从真实中途姿态重新运行原观测调用。新的原10秒SDK整窗仍rc2，但原函数连续[0:82]82fresh/8.129435秒静止通过，未沿用近零位旧证书、未改原SDK/准入阈值。
4. 原driver/原launch去掉grasp executor，`stop_after_observe`设/read为true，第一持位命令与arm时真实q相等。原目标不变，发布8点26.510519秒轨迹（原bag精确时长），从当前姿态继续，不重做J4/零点复位。
5. 约18.368秒后接收停止。原driver抑制输出、原adapter25秒超时软件disarm，控制器`FAULT/PIPER_ADAPTER_DISARMED`。本次包装已识别终态并收尾，不再误等305秒；末`AssertionError()`来自“未到观测”的判定，不是首发故障。

最后收到的q（不是当前实时物理状态）为：

```text
[-0.143982776, 0.811390216, -1.093407364,
 -0.043871660, 1.091157088, 0.081585588] rad
```

bag含2126关节命令、5285反馈、3条轨迹（1条观测运动，2条故障/USER_STOP时的恒定保持），没有夹爪输入或输出中的夹爪字段。所有自有源已退出；没有硬件失能、ResetPiper、固件操作、SEARCH或抓取。六源SHA前后不变，当前板仍旧2/10候选，本轮未启动相机/新板采样或手眼拟合。

## 新证据与结论边界

- 内核6.8.0-138-generic新增：`12:59:08 gs_usb ... Unexpected out of range echo id 343`。它在本次续跑中出现；不把一条echo错误直接认定为全部停流的原因。
- 停止后can0虽ERROR-ACTIVE，RX固定544487/TX2643；独立3秒纯接收为0。CAN错误/bus-off计数没有增长，不能称bus-off；枚举和UP不证明有流。
- USB电源control=on、runtime=active、autosuspend=-1000，已关闭自动休眠；本轮没有改写电源参数。Astra和彩色源本轮未启动，不能说本次由点云/相机带宽直接造成。
- 按仓库2026-09-28“新非法echo且运动源全退”的既有例外，仅重建一次can0：down/固定时序/queue成功，up返回ENODEV。当前netdev仍列出，但DOWN/STOPPED；不再USB reset、模块重载、反复up或启动运动。
- 旧持久化echo标记来自9月28日、数值1；本轮新boot计数也1，单纯计数不能跨boot识别新事件。本轮仅用独立boot-ID记录此次已尝试恢复，**未修改冻结生产脚本或旧标记**。这不是已经证实的停流原因，后续若修生产监测需独立批准。
- 当前没有新反馈，不能用末六true或最后q断言此刻使能/姿态，不能自动重放旧轨迹。

上游[Linux v6.8驱动源码](https://raw.githubusercontent.com/torvalds/linux/v6.8/drivers/net/can/usb/gs_usb.c)定义10个TX上下文，收到越界echo会记错、丢弃该echo并重新提交接收URB。这证明错误属于USB-CAN回显处理，不是J5角度/IK报错；该版本是参考源码，未冒称等同本机Ubuntu补丁后的二进制。来源设备/宿主透传/内核交互之间仍无法唯一归因。[candleLight上游](https://github.com/candle-usb/candleLight_fw/blob/master/src/can_common.c)把发送帧回显和普通接收帧作区分，也不证明当前适配器固件版本。[VMware官方排障](https://knowledge.broadcom.com/external/article/307966)要求核对宿主占用、虚拟控制器与guest设备，不能仅据guest枚举成功判断整条通道正常。

## 下一步及范围

需要宿主侧发生有区别的链路变化：优先将USB-CAN换到另一宿主物理USB口，直接接电脑而非外接Hub，再连接本VM；不要求机械臂断电、失能、复位、重摆或移动棋盘格。换口是隔离实验，不能保证修复。若不便换口，应先提供该时段宿主`vmware.log`核对透传记录，而不是重复同样的VMware菜单断开/连接。

恢复后先被动验证数据持续，再读取真实q/使能，从实际姿态续原观测；不会因本包批准新增生产修改或立即抓取。若需更改VM USB控制器，必须另行安排VM停机，不在机械臂当前状态未知时自动执行。

## 原件与验证

`runtime_originals.tar.gz`含24个原文件，约405KB；`runtime_manifest.json`有各文件SHA-256，已逐成员读取核验。完整原bag/日志在归档，JSON和调用源码另有可直接审阅副本，`assessment.json`记录逐项结论。

审计初版误预期仅1条恒定保持而断言失败；读原bag确认故障和USER_STOP各一条保持后只修审计预期，原bag不改。`invocation_changes.json`中描述fault修改的字段误存了打印清单字符串，实际执行源码及本说明为准；未隐瞒或改写该原件。包和文档只本地Git提交，不自动推送。
