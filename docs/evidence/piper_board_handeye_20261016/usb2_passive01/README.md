# USB2路径纯接收验证：2026-10-16

起点`8fadc02`；用户“已完成”确认将USB-CAN连接到已改为USB2兼容性的VM。授权沿`1cf2bf9`，本轮没有机器人控制命令。

## 实测结果

- 同一candleLight适配器实际走`usb1/1-2/1-2.1/1-2.1:1.0`、`uhci_hcd`，而非原xHCI。can0 ifindex7初DOWN/STOPPED，仅按原1Mbps、sample-point0.75、txqueuelen1000激活一次，三命令均rc0。
- 14:06:36（UTC+8）开始，纯接收60.000080934秒，145307帧，60个秒窗均有新帧，最大帧间隔11.946669毫秒。末CAN为ERROR-ACTIVE、接口RX145325、TX0，错误及bus-off0，无新增非法echo。socket与接口计数窗口不同，不混用两者。
- 原被动SDK6秒得到60fresh、六轴角度波动0；整窗rc2原样保留：样本25的J4速度为−21mrad/s。原函数核连续[26:60]共34样本、3.311553秒静止通过，不改阈值、不再重复采集。
- 末反馈q rad为`[-0.143982776, 0.902883996, -1.21619568, -0.064403248, 1.183017192, 0.087516548]`；六轴true、夹爪99.6mm。只代表采集时刻，不是持续监测或已到既定观测姿态。SDK时间戳为聚合接收戳，未虚构逐电机新鲜度。

原执行`run_passive60.py` rc0、原SDK rc2、离线`package_passive.py` rc0。全部自有receiver/SDK已退出；未启动相机/driver/adapter/MoveIt，未发送Enable/Disable/Reset/主从/运动/夹爪命令，未改生产TF、靠近、限位或判据。六冻结源SHA与上轮相同，旧板候选仍2/10。

## 文件与验证

- `result.json`：实际调用、rc/stdout/stderr、路由、每秒ID计数、前后CAN/内核原记录。
- `sdk.json`：完整原60样本，包含整窗质量失败。
- `assessment.json`：原静止函数通过子窗、完整SDK末反馈及验证边界。
- 两个`.py`为本次运行/离线归档的原脚本，不是生产修改。
- `runtime_originals.tar.gz`与`runtime_manifest.json`：5个原文件（包括`sdk.log`）及每件SHA，归档成员已逐一回读核验；解压无需覆盖生产路径。
- `production_SHA_after.json`：六生产源哈希，未改变。

原home目录`/home/johnwick/brain_robot_logs/usb2_passive_20261016.9ucND5`保留。未删数据；Git仅本地留证，未同步GitHub，既有分叉/历史审查及发布范围阻断不变。

## 结论及下一步

本次只通过新UHCI路径上的纯接收验证。旧xHCI失败主要发生在主动发送期间，因此现在还不是同条件A/B，不能确诊xHCI为根因或宣布控制、相机、观测、手眼成功。

下一建议仅沿原driver/adapter，以新鲜实际q保持30秒，检查带发送时反馈是否连续；不设新位移或夹爪目标。该范围尚未获明确批准、未执行，不自动启动一键/观测返回/9+1采样，不重复成功J4或本次60秒测试。当前健康链路直接复用，无需用户再重连/重启；相机新USB2透传与RGB-D采流仍需后续单独验证。
