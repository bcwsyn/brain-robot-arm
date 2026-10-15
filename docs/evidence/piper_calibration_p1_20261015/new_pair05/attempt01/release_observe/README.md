# 第四组：本组已授权张爪/回观测，实际被反馈停流阻断

2026-10-15 15:18 +08:00。用户“运行”明确授权本组原位张爪→原观测轨迹→SEARCH前停止→采A。原B检查点2b1becb未覆盖；**实际没有确认张爪，没有请求controller/start，没有执行观测PREPARE，A0帧**。已开始4/6位置，前三组有原始A+B，质量合格完整仍1/6。

## 三段真实执行，不混淆软件错误与最终停流

1. 原程序启动包装失败：PYTHONNOUSERSITE下原驱动找不到用户目录python-can，临时launch过滤把原str当Substitution。代理调用错误，bag0消息、没有运动输出。只给原驱动main追加用户site搜索路径（系统库仍优先），兼容临时过滤的str字段；未修改生产代码。
2. 原适配器arm成功，首命令等于真实B；但代理根据SDK六true错误跳过原enable_srv，新驱动内部输出门仍false。80张爪帧全部被原驱动enable=False拦住，实际q/36.3mm不变；没有START。stop/disarm成功、源退出。这不是新增保护门或夹爪硬件故障。
3. 恢复原enable_srv true步骤一次，响应成功，前后实际q不变；原stop_after_observe设置/回读true，arm首命令仍等于真实反馈，没有重演J3越界裁剪。随后1792048421.492驱动失去反馈，1792048446.507适配器25秒原规则自动disarm。张爪请求发出时80帧被feedback_available=False拦住；没有到100mm、没有START/观测/SEARCH/抓取。控制器保持WAITING_FOR_START，最后USER_STOP。

最后一段原图源RGB/深度有流，但前置三帧采集因关节反馈缺失返回rc2/0帧；临时调度没有检查该返回值便发布张爪请求，这是另一个调度不足。原驱动有效阻止实体输出，但不能把它包装成调度正确或宣称请求未发。**归档临时脚本只作实际执行证据，不可直接自动续跑；下一次必须在中间采集失败/反馈陈旧时停止，而非继续发布。** 不修改原生产门来掩盖问题。

## 可证实的实体与链路状态

原SDK前读/B都为q_mdeg[-2769,68874,-64707,-2786,61860,15357]。末有效ROS反馈1792048421.48713，q=[-.048302436,1.202240480,-1.123358712,-.048598984,1.085261016,.267887508]，开口36.3mm。与B变化最大.006175176rad；保留这次接管后的小幅反馈变化，不称姿态完全不变或方块三维零位移已独立证明。首arm命令匹配、无J3裁剪，与后续小变动分开记录；最新实体使能/姿态在停流后未知。

独立8秒SDK80样本/0fresh，内核RX两次均6347214、TX1485；ERROR-ACTIVE/error0不等于有流。SDK默认q0/false绝不是当前实体回零/失能。近期5分钟内核日志查询仅“No entries”，不能据此定USB/固件根因；不把历史故障未经验证套来解释。本轮未重载USB/CAN/模块、未刷固件/Reset/MasterSlave。

原stop/disarm服务成功，之后所有本轮源退出；末driver需精确SIGKILL（-9），其他末源rc0。软件disarm不是硬件失能；没有DisableArm/enable false/零位复位。两条arm_trajectory消息均是USER_STOP发的两个相同q点（0和0.1秒）静止保持，不是观测轨迹。见[ROS bag复核](bag_review.json)及[保持轨迹](stop_holds.json)。

## 证据与下一断点

[执行汇总](execution.json)；三段原始会话：[启动失败](startup_failed_execution.json)、[软件输出门未同步](output_gate_execution.json)、[同步后停流](enabled_execution.json)。
[张爪前原图](before_release_rgb.png)来自第二段正常采到的3帧之一，只说明当时可见方块在夹指之间，不是A或最终停流后的照片。
原始数据、三段实际运行的临时调度脚本、SDK全窗/失败旗标、日志、3对原图和3个完整ROS bag无损存入[runtime_closed.tar.gz](runtime_closed.tar.gz)：64文件、941295B，SHA-256 `f15983a2e3deda7590f4d1f851978e70630caf474529e4afa3831dda6536c810`。全部对原文件逐项回读校验，SQLite integrity ok；bag消息分别0/9579/4232。原runtime未删，B未动，五生产SHA保持。见[清单](runtime_manifest.json)/[验证](verification.json)。

下一保持机械臂/方块原位，仅在宿主VMware断开并重新连接USB-CAN到此虚拟机，先不重启机械臂。恢复新鲜反馈后核真实q/夹爪与物体原位，再继续本组已授权原位张爪和原观测；不需要重复索取同一动作许可，不在无反馈时重试使能/arm/开闭，不重演本次两个已证实调度错误。当前仅本地归档，未推送GitHub。
