# 宿主VMware日志只读核对（2026-10-16，UTC+08:00）

结论：**用户已经换口；本次13:23接收停流在所提供宿主日志中没有对应事件，不能把较早的手动重连/取消管道报错当成此次根因。** 不需要再提供同一份普通日志，不启动同条件运动重试。

## 输入与隐私

输入为用户粘贴的2748行、319586字节文本；SHA-256：

```text
857bb9ee74a0bf8083f3a2c09fd3c9c2a5cdcb38db91edff7088cc41211e068b
```

私有原件：`/home/johnwick/brain_robot_logs/vmware_host_review_20261016.hs91D9/vmware.original.private.txt`；与附件逐字节一致。**原件未提交Git**，其Windows账户/路径、主机名、IP、无关设备序列号不公开。本目录只有白名单解析脚本和结构化脱敏[review.json](review.json)，保留源行号、行SHA、设备类别、时间及USB路径，不复制原始整行。脚本为离线分析，无ROS/CAN/USB、subprocess或配置接口；合成测试检查UTC转换、窗口、身份映射与隐私不泄漏。

审阅只覆盖本次收到的粘贴文本，不能独立证明它与磁盘上完整原日志逐字节相同或从未省略内容。以下时间依据ISO后缀`Z`按UTC解析，统一转换UTC+08:00；不根据日志另一个offset描述反向解释`Z`。

## 手册式事实与时间对应

| 本地时间 | 已记录事实 | 不能推断为 |
| --- | --- | --- |
| 12:04:40—13:30:51 | 所提供文本有故障前后时间戳 | 每个USB事务都被记录或粘贴连续性已验证 |
| 12:54:39 | CAN设备有abort-pipe INVALID_PARAMETER，随后host_disconnect/DEVICE_NOT_PRESENT | 13:23故障的同一时间证据；不能排除其属于用户受请求的重连过程 |
| 13:14:23—13:14:40 | CAN断开、重新到达连接 | 自发故障；此段处于本次用户换口操作上下文 |
| 13:14:36 | CAN宿主路径由1/0/0变成1/0/1 | 用户没换口；但路径变化也不证明是独立物理控制器 |
| 13:14:40之后 | CAN仍映射virtPath usb_xhci:9、连接usb_xhci:4 port1 | 已脱离原虚拟xHCI数据路径 |
| 13:22—13:25 | 所提供文本此窗口**全部记录0条**，相邻记录13:15:34和13:29:26 | 没有发生传输故障，或已经证明VMware/适配器/机器人哪方有错 |

本轮实际原观测反馈停于guest epoch1792128203.642230，即13:23:23.642附近，来源[f6b197b实测](../board_resume03_port_reconnect/README.md)。宿主与guest没有本轮硬件同步，重连枚举本就有处理延迟；即使允许数秒误差，宿主这个大空窗也没有对应事件。不得据缺少日志否定guest原始CAN停流，也不得把13:15相机断开当13:23 CAN故障。设备类别由1d50:606f和2bc5:0557/0657分别映射，不混读endpoint81。

## 环境事实，不是根因

- 日志明示Workstation17.6.4/build24832109，Hyper-V detected、Monitor Mode ULM。这只是环境记录；没有证据证明Hyper-V/ULM导致这次静默，不建议因此关闭VBS、内存完整性或其他宿主安全功能。
- usb.present、ehci.present、usb_xhci.present均TRUE，但CAN的实际连接仍为xHCI。存在EHCI设备不等于CAN已经使用EHCI。
- 本轮没有新guest设备读取、相机、使能/运动/开闭/失能/复位、CAN bounce、USB reset或模块重载；当前机械臂实际q/使能仍未知，不能从旧反馈或宿主枚举推定。

## 官方资料与适用边界

[Broadcom 307966](https://knowledge.broadcom.com/external/article/307966)针对Desktop Hypervisor要求区分host、虚拟控制器和guest，核对宿主占用/过滤驱动；仅设备枚举不是持续数据保证。[Broadcom 315312](https://knowledge.broadcom.com/external/article/315312)给出Workstation单项quirk及必要时USB analyzer/Full诊断日志流程；这些不是针对本机CAN的已证实修复，不自动套用skip-reset/skip-setconfig或启用无界Full日志。

官方较旧的[Workstation xHCI支持说明](https://knowledge.broadcom.com/external/article/307817)本身也说明Linux通用xHCI支持，不能拿“full-speed CAN接xHCI”单独认定配置非法；[USB2兼容性排障资料398992](https://knowledge.broadcom.com/external/article/398992)对象是ESXi，**不冒称为Workstation17.6.4/candleLight的已知修复公告**。

## 下一最小可回退提案（未执行、待批准/安排VM停机）

不再要求重复物理换口或同一菜单重连。建议只改变一个变量：在保留当前VM USB配置/回退值后，将**虚拟USB兼容性临时改为2.0**，使CAN不再沿当前xHCI路径；启动后由guest实际枚举核对路由，不以设置标签代替证据。这是隔离实验，**不是已证实根因/保证修复**。

这需要正常关闭Ubuntu虚拟机，而不是挂起或强关。机械臂需可靠支撑，不能由代理自动硬件失能/断电/Reset；用户当前只提交日志，没有批准此VM配置变更，本轮不关机或修改配置。

若批准执行：只改虚拟USB控制器这一项，不同时改Hyper-V、驱动/固件/内核、USB quirks、相机TF、运动限位/门。重启后先核新USB路径、60秒纯接收及新鲜实际q/使能；不一上来再走整条观测轨迹。只有反馈有效且原准入满足，才安排既有控制链后续验证；下一动作仍须有明确范围，不借静态接收通过自动声称带发送/运动稳定。若相同停流再现，停止该分支，恢复原USB配置，并另行安排有界官方USB详细日志/非虚拟化对照，不继续同条件运动。

这份日志已交付并审阅，旧“等待宿主日志”断点解除；现在等的是上述独立环境实验的批准和VM停机安排，而不是更多同样资料。板仍2/10，标定/TF/抓取未完成。

## 验证与Git

源副本cmp、SHA、全2748行解析与目标窗计数核对，合成检查通过；解析结果49个设备事件/21条类别路径状态变化（含连接前null→已连接，不误称21次物理换口）。六生产SHA仍与f6b197b冻结快照相同；本轮只有离线分析和文档，无需构建/重跑已过实机J4。

创建证据目录首次被普通沙箱只读挂载拒绝；改用已授权escalated创建精确目录后apply_patch成功，不chmod或改变共享挂载。仅暂存本目录和四规范文档，原始宿主日志及其他用户脏树不纳入。既有main分叉/积压历史推送审查/写入范围阻断保留，**仅本地提交，未同步GitHub**。
