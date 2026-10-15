# attempt02释放和返回：观测已到，CAN停流阻断A

新位置B检查点`9a82bab`在`../grip_capture/`；用户明确授权记录后代理张爪、原回观测、采A。本目录保留实际成功动作和失败采集，不代表完整第一组，正式仍0/6。

## 成功动作

原唯一入口`/home/johnwick/start_brain_robot_cube_real.sh`，AUTO_START=0；复用原driver/健康CAN/原深度，未改任何生产文件/TF/门/模型/限位。原stop_after_observe=true回读通过、原adapter enable_motion/arm成功。首单次100mm topic发布后无adapter接收日志、实际仍37.4mm，`open_rgbd/`三帧及`open_sdk.json`保存未开状态。

核原topic可靠订阅1、CLI默认保活.1s后，只给本次同命令`--once -w1 --keep-alive3`，1792035345.499849864原adapter接收80帧、原driver执行，实际开口99.4mm。`open_confirmed_rgbd/`三帧显示两指离开方块，背景ORB/H关联184匹配94内点，补偿中心差[-.6057635,-1.3302391]px/norm1.4616721；未见明显位置变化，不保证三维零位移。此CLI调整不写代码或永久配置。

原controller start成功，1792035431.715818602发布13点46.3s/maxstep.080rad，1792035431.728724161适配器接受；1792035477.611758887明确`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`，无SEARCH/抓取。随后原adapter disarm成功（仅软件停输出，不是硬件Disable）。原事件完整保留`visual_stack_trace.txt`。

## 失败与原值

- `open_sdk.json`和`open_confirmed_sdk.json`都是完整原始六秒窗，均rc2，不伪装静止通过。第二窗第一条J1/J2为0、后续/原ROS不一致，速度短脉冲保留；不解释成机械臂实际瞬间回零、不删原值。开后后续q_mdeg=[10550,107103,-58410,-504,32456,-8654]；相较B的J2/J3分别+771/+323毫度，B前姿态原样不覆盖。
- `observe_preview/summary.json`：15.005s、目标3帧/实际0/rc2，只收depth308/info365、没有RGB/关节；`observer.jsonl`原0字节保留，不造图片或成功manifest。
- `observe_sdk.json`：60次/0fresh、rc2；默认0/false不是新的真实关节/失能反馈。
- `can_health_trace.txt`原11:38:23 CAN_RX_STALLED_3S。原onekey rc143、保护分支未发Reset/Disable；driver超过25s无流1792035525.270945558。独立新`timeout -s INT -k1s4s candump -L -n1 can0`0帧/子码124，RX2801987和TX37262前后固定、UP/ERROR-ACTIVE、错误0。不是原ROS socket单独故障。
- kernel本窗只有drain_vmap_area_work CPU警告，不据此断言USB或磁盘根因。根55%/34GB、共享73%/137GB，无ENOSPC；原常规清理没有删PNG或journal数据。

释放图原observer中runtime绝对路径原样保留；Git读者取对应目录evidence/加原basename即可，逐图SHA字段核对通过。原SDK/trace的独立SHA在execution.json。未把海量CAN dump/整个日志目录提交。

原始`visual_stack_trace.txt`有7处MoveIt/Servo自带行尾空格，标准Git whitespace检查会指出；保留原字节和SHA，不修改原日志。其他全部路径用标准检查，仅此raw文件用一次性`-c core.whitespace=-blank-at-eol`检查，不改变全局配置或代码检查。

## 下一断点：不再运动，只补A

原onekey已经退出；复用driver39486在INT/TERM未退出后精确KILL，session17394 rc137，无硬件命令；本轮driver/adapter/controller/RGB均退出。仅旧深度container30328保留，其他用户节点不动。当前实体q/使能无新鲜反馈，不能声称重新验证持位/失能。

请操作者保持方块/机械臂不动，只在宿主VMware断开后重新连接USB-CAN。恢复后有限验证新鲜q仍在观测，再仅启动原只读反馈桥+原RGB与采集工具补A60/≥20好帧。**不要重跑一键、再回观测或再开闭夹爪**；B已保存且本组返回已成功。若实际物体改变位置再如实重配，不自动假称组已完成；P2未开始、未改生产TF或算法。
