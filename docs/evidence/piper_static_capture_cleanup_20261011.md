# 静止 RGB-D 与原入口退出清理（2026-10-11 19:40）

起点 `ceecb0d`。本轮没有运动、闭爪、使能、复位、固件操作或 DisableArm。目标仍未完成。

## 实际运行与采集

上轮 PID37594 已不存在，不能沿用其“仍在运行”的历史记录。主机 can0 已 ERROR-ACTIVE，未重载；仅被动接收1.2秒，RX 56000788→56003702，251..256 各119帧，未发送 CAN 查询或控制。使用驱动的普通 `/usr/bin/python3`；第一次在 PYTHONNOUSERSITE=1 下缺少用户安装的 `can`，属于诊断解释器差异，未安装/卸载依赖。根盘34%、共享盘73%，无 ENOSPC。

为取得新鲜静止数据，有限运行唯一原入口，而不是启动默认自动运动：

```bash
BRAIN_ROBOT_AUTO_START=0 \
BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/real_static_20261011.IrUxSo/stack \
BRAIN_ROBOT_WAIT_SECONDS=35 \
timeout -s INT 130s /home/johnwick/start_brain_robot_cube_real.sh
```

达到 `[7/7]`、IDLE / WAITING_FOR_START，executor WAITING_FOR_LEVEL_ALIGN；没有按键或 start/execute 请求。原入口正常流程仍无条件调用磁盘维护：journal 释放0B、清 apt 缓存、根盘34%→34%。未另行清理或删除历史日志；未核算其所有文件删除数量，不能说绝对未删任何旧缓存。

复用 `/tmp/piper_onekey_observer_20261011.py`（SHA256 `70d3b681fb7807f6fad7af7d58038204438715d884787184dcb4d009cbc80d1b`），有限65秒采集 `/camera/color/image_raw`、depth、depth CameraInfo、真实 `/joint_states_feedback` 等。完整22条 snapshot 在 `capture/observer.jsonl`；这是每3秒取各话题 latest，不是同步器。六轴范围均0，q(rad) 为 [-0.262724084, 1.888278112, -1.280686148, 0.0095942, 0.836928232, 0]，J5≈47.952455°。夹爪缓存0.1019仍不是标定后的真实开口。

只有 snapshot2 满足 RGB/深度/关节跨度≤120ms：RGB1791717680.9249885、depth/info1791717681.0115535、feedback1791717681.0409377，跨度115.949ms。原图 `capture/evidence/0002_rgb.png` SHA256 `800f0adf8ae512476f22d3d75e9488a1caa9831155d1972230db73495d1e288c`；深度 `0002_depth.png` SHA256 `0408ad831b61ab8936000f5ed863b95372bad2b9ed333a4d6bae3920ce06edb3`。实际查看原彩色与注册 debug：原图有方块/两指，debug 黑区并非原图真实遮挡。

原 RGB320×240紫色 bbox=[96,168,57,72]，轮廓面积2919px、矩形度0.874798，3055紫色像素，**触下边界**。按实际 factory K / D→C 将非零深度前投影到原紫色像素，有2430个深度样本/653个唯一彩色像素，深度中值0.155m、p95=0.157m；未过形状、完整性、稳定性/夹持区全部门，不是合法抓取点。没有 color CameraInfo 是当前 cam2image 的实际行为，使用实际 detector 中640×480 factory K 按图像尺寸解释，未补造新标定。

snapshot3..15 RGB年龄约140..174ms、depth/关节更近，定时3秒恰为5Hz RGB周期整数倍，latest 抽样存在相位偏置，不能把1/22等同于传感器永久无法同步。后段有真实停帧：snapshot16..22深度年龄2.06→20.07秒，19:22:17 CAMERA_NO_FRAMES，19:22:31恢复。未放宽120ms或拿旧关节拼当前深度。驱动日志采集期记录0.43秒/0.01秒恢复；之后残留运行期间出现最高2.88秒反馈恢复。不能声称整个实测反馈连续。

## 退出缺陷、最小修复与边界

130秒 timeout 返回124，但最后只打印到“停止本脚本启动的…进程”，随后“被监视的命令已核心转储”；没有完成清理行。实际驱动、视觉栈、检测器、相机仍在。内核同窗仅见 uvcvideo URB 重提交失败，尚未找到原父进程核心转储根因；不能直接沿用旧隔离 MoveIt 析构-11解释全部残留。

精确核对每个进程成员的唯一 `BRAIN_ROBOT_LOG_DIR` 标记后，TERM 本轮 PGID 47139/47296/47330/47796/48273，后验这些组均退出。保留反馈组47039（驱动47043，auto_enable=false/gripper_exist=true）；ROS daemon47019不属于运动控制，未重启。未调用任何 DisableArm。

针对独立可复现问题，仅修改原 cleanup 的信号设置：`trap - EXIT INT TERM` 改为 `trap - EXIT`、`trap ':' INT TERM`。旧代码在清理中二次 SIGTERM 时假 ROS 测试 exit -15；SIGINT 对照旧代码通过，不夸大其覆盖。中间尝试忽略信号 `trap ''` 会令新 Bash helper 继承不可更改的忽略状态，已用失败测试排除，最终使用空操作 handler，保持 helper 自己的处理能力。没有新运动门、TF/TCP/轨迹或抓取逻辑变更。

验证：原/部署入口 `bash -n` 均0；`PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_startup_script.py` **11通过**。新增两项只向本测试创建的 Bash PID 发信号，mock ROS/kill 不接触硬件，核停控制→清相机→TERM/KILL自有组、无失能且完整结束。不是原硬件核心转储根因已解决的证明；未再起真实整栈作相同实验。

原/部署入口新 SHA256 `0e976b0ab21b0417a0f2d01b84e39309af37adc269eca2b05232be4c5fdf811e`，旧 `e8c9f85c9e41cc3c4c288d96ab15cc91f2cae42a8ade9bfea6f1c71d79784acb`。实际 executor **源码**仍 `107ce501ee2cbf1862f96bf9096ed8fec7c396809fb8c36749222b35d633ce49`；二进制 `db7bcdafc5c16efc11560ab244316c8e30cf8fc15a6969811714b94a02cf01af`，不能混用二者；实际 cube_task YAML仍 `7561219416c17c9e0685d5fefcf19a9ab88d63fbc5b3aa99a212d241d34b3f74`。回退本轮提交并将该原脚本恢复同步即可，未重构入口或构建部署抓取组件。

CAN 日志已停止，SHA256 `e8e917f1aab3b283de57085f99d93e909349f3a2f7fb84204c9a604a7f43cfa3`；455571条全解析。20MB guard 会截断，**仅保留1791718062.410736..1791718256.703699（194.293秒）**，不能覆盖整场采集。保留窗150/151/152/153/154/155/156/159/471均0，251..256约18813..18818，3A4..3A6约37634..37635；251..256/3A4..3A6最大帧间隙3.385..3.394秒，覆盖反馈报警。接收日志本身也可能受调度/VM停顿影响，不能唯一归因硬件、SDK或磁盘。初次诊断正则过度转义给出的全零计数作废，以上以 split 解析实际日志重新核对，未把错误零值写成证据。

下一步改善**真实标定观测的配对采集**：按消息时间戳保留 RGB-D/反馈历史并取合法近邻，而不是3秒 latest 抽样；保留120ms要求，核真实停帧。仍无通过独立验证的新外参，旧26°/敏感候选不恢复，70/105mm不删除，不以姿态规划成功当两指捕获。原4段/20mm预览已用1段，本轮未新增运动。原始图像/日志留机器，不提交大型数据或 vendor/reference 改动。
