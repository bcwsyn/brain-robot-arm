# 2026-10-14 实体示教回放、磁盘恢复与新配对采集断点

补齐上轮因用户优先要求清盘而未提交的结果，另列15:12重启后状态。历史回放不是本次新观测/人工夹持配对采集。

## 上轮实体回放：到位，未闭爪

- 用户批准先张爪。唯一入口仍 `/home/johnwick/start_brain_robot_cube_real.sh`；监督对照仅此次 `BRAIN_ROBOT_AUTO_START=0`，默认1未改。原MoveIt按新反馈规划，完整原轨迹经 `/brain_robot_grasp/arm_trajectory` → 原adapter → 原驱动执行；没有另写基础运动或改生产抓取代码。
- 顺序：100mm张爪命令（实测98.8→99.6mm）→ 原观测目标 `[0,0.98,-0.75,0,0.30,0]` rad → 已记录人工示教终点 → 保持。没有启动自动SEARCH/抓取、闭爪/抬升/释放，未ResetPiper/MasterSlaveConfig/刷写/DisableArm。
- 观测353点/35.144770933s，adapter接受时间 `1791954819.020896786`；静止实际q `[0,0.981190112,-0.751592184,0,0.301100884,0]` rad，maxerr0.001592184rad。
- 示教目标 `[-0.212345812,1.933754620,-1.083167736,-0.028241836,0.563214428,0.116560808]` rad，349点/34.752150266s，adapter接受 `1791954917.561105605`。末段J6迟于其余轴到位，但未重发命令随后完成，不把临时J6=0当永久阻断。
- 最后实际q `[-0.211072400,1.932725424,-1.081754772,-0.028590716,0.563319092,0.116194484]` rad，maxerr0.001412964rad、六true/速度0/开口99.6mm。证明原链路复现示教姿态，不证明夹住或外参修好。
- 原RGB `1791955012801185279_rgb.png`，最近反馈戳 `1791955012797705326`（记录明确latest feedback，不冒称图戳插值TF）。方块在可见两指之间的下部、底边裁切、中心仍背景；原最终中心条件未满足。frames.jsonl执行器state为WAITING_FOR_LEVEL_ALIGN，不是抓取完成。
- 360s外层晚期超时rc137；原清理CLI挂住、setsid子组未随之退出，与实体到位分别记录，不称一键无人干预通过。随后原adapter disarm成功，精确结束本轮进程；驱动忽略INT/TERM后终止已核对本轮PID，未失能。最后SDK epoch1791955287.4033701/q_mdeg `[-12100,110796,-62013,-1639,32293,6661]` /100Hz/六true/静止/99.6mm仅为重启前历史。

原始资料保留在 `/home/johnwick/brain_robot_logs/view_guard_20261013/`，本轮重新检查存在/hash：

- `manual_replay_onekey_20261014/visual_stack.log`：353/349点接受证据。
- `manual_replay_onekey_20261014/to_observe_trajectory.yaml` SHA-256 `7a4ef3721788dd52bdfc1daa17c5587d073d2092db5425949d14959f036a22c5`。
- `manual_replay_onekey_20261014/to_manual_trajectory.yaml` SHA-256 `7480c84816ae18fc2ca206d17e551b9ba00b5fe4ce642627ec1c0d56aba9f9a7`。
- `manual_replay_terminal_exact_20261014/frames.jsonl`、`1791955012801185279_rgb.png`，图SHA `14b626843d8560b35527e0ef5226a5bdc58f7e392fcc1f9c3ed87278a8c652ac`。
- `manual_replay_exact_20261014/`、`manual_terminal_capture_20261014_complete/` 均保留。大图/日志/轨迹不入Git；`/tmp`旧分析器重启后不在，不假定能续用。

## 已授权清盘与防增长

- 用户授权“图片内容均可自行决定删除”。先原清盘rc0但95%/约4GB不变：文本策略未处理PNG。
- 精确结束5个Oct12遗留ppid1 image_saver：106003/106044/106087/106357/109106；随相机重启持续写图，均为记录器非控制节点。
- 仅删除 `/home/johnwick/brain_robot_logs/full_grasp_20261012_1930/evidence` 第一层常规PNG。保留文档引用 `rgb_0450.png`、`debug_0426.png`、`debug_0427.png`、各流头尾与每1000帧样本；不删目录、源码/Git、日志/JSON或新示教资料。
- rc0删除391661张/31221950769字节（29.078GiB），408PNG保留、旧目录约58MB；根盘95%→55%/约35GB空闲。没有迁移归档，删除PNG不可恢复。不能据此断言全部历史CAN问题由磁盘导致。
- 已批准局部防增长：原只读capture_scale_frames默认300s/256MiB，允许≤600s/512MiB，编码后写前核对实际字节预算、原RGB/16bit深度保真。超预算只退出记录器，不停止机械臂/改变运动门控。
- 原clean_disk_space新增prune_capture_images助手，仅原runtime树旧PNG，默认8GiB总预算；保护<24h、规范引用、各流头尾3帧/每1000张，不跟软链，删前复核inode/device/size/mtime，Git引用读取失败拒删。保护优先可能仍超预算，不宣称绝对硬上限；沿原清盘调用，无新timer/cron。
- 备份 `/home/johnwick/brain_robot_logs/disk_recovery_20261014/clean_disk_space.previous.sh` 和 `capture_scale_frames.previous.py`。实际清盘/助手/采集与规范三SHA相同：`65ec5bcd91fec5aa1c679f7b0613385cc48097e6d15123693e486a575e47916d` / `112c2b1f8635b9e9a08222a615ae785754b6bcaaa34708d231b05f7167189f11` / `84b701950a64b3c12a32fe4085d7244839bbb1d9cb59dc1803a03f0b501be297`，本轮重验一致。
- 新规范清盘rc0、55%→55%，PNG94007张/6493290174字节、删0；域78采集0.2s无硬件冒烟rc0、duration_budget。保留4项+编码5项共9测试通过；本轮 `PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -q -p no:cacheprovider brain_robot_arm/scripts/test_prune_capture_images.py brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/test_capture_image_budget.py` rc0/9passed。bash -n及限定diff --check通过。不动其他README/vendor/simulation改动或全仓CRLF。

## 15:12 新请求：先观测A，再用户人工摆位B

- 用户要求方块桌面原位，先原观测拍摄/采信息A，之后其摆入两指再保存关节B。授权仅A观测运动/采集；B等用户完成，不自动旧q回放/搜索/闭爪/失能。
- 实际 `uptime -s`：2026-10-14 15:01:22。host无ROS/控制/相机/采集进程；`ip -details -statistics link show can0` Device does not exist。提升执行环境lsusb仅VMware Hub/Mouse和Linuxroot，未枚举1d50:606f USB-CAN或真实Astra/RGB相机。sudo -n true成功，但无设备不重载/配置总线、不读SDK默认值假装反馈。
- 根盘54%/约35GB。这次缺VMware USB透传，不是磁盘满/观测规划失败。本轮未启动实体栈或发新命令；当前实体使能/姿态未知，A/B未新采，重启前反馈不能沿用。
- Git起点2f69a6d，与origin/main相同；reflog外部fetch/merge/push已完成。新增simulation/cup非本轮实机部署，不撤回/混用。其他dirty保留，仅本轮/上轮明确5项图片实现+小文档提交。
- 下一首条提升环境 `lsusb; ip -details -statistics link show can0`。需VMware把USB-CAN及相机接给此Ubuntu客体，无需重启机械臂。枚举恢复→一次新鲜SDK/RX→原入口AUTO0、原controller stop_after_observe=true或原MoveIt完整观测路径→实际到位→有界RGB/原生depth/内参/目标/q/可用图戳TF采集；缺失如实记，不把latest当同戳。
- A完成退出运动输出后等待用户B，方块位置/安装不变。B保存q_mdeg、原ROS rad、开口、RGB/戳和同配置。两姿态仅固定场景参考不是完整手眼标定，不拼旧目标和新姿态伪装同场景测量。完整抓取仍未完成。
