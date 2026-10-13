# 2026-10-14 已选可达姿态的路点推进修复

## 授权与实施

用户最新“同意修复推进并继续实测”覆盖前条仅隔离及历史blocked等待。基线978987c/应用099bbc9；唯一入口SHA87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0，实际executor97b154c…/detector8e763f4…，host无控制/隔离/采集栈。完整实体目标未完成。

仅原grasp_lift_executor.cpp和实际方法测试：普通路径保留原nominal朝向；只有成功执行/停稳且确实使用缩角/反向候选，才保存已执行可达姿态。selected_goal在原停稳确认后记录实际保留轨迹最后一点FK，不记录裁剪后未执行的完整末点。

下一循环先取新RGB/真实六轴反馈/原纠偏与视野保护；纠偏后nominal指尖须满足原10mm，朝向仅允许用同一路点已执行的可达姿态、仍原0.12rad。推进后/图像恢复/普通规划成功清除候选，恢复不跳点。原8mm/1°/.08rad前缀、循环预算、完整MoveIt、限位碰撞、目标/TF、最终中心及两指夹持不变。新AUTOMATIC_RGB_WAYPOINT_REACHED日志区分NOMINAL与COMPLETED_REACHABLE。

新增4项实际方法测试：候选到位替代不可达朝向；指尖未到/新RGB修正过大不推进；真实朝向未到不推进；无候选时原规则保持。域78/auto_execute=false/real_grasp_enabled=false，无控制调用。

## 命令与边界

- 原五Git/host ps/SHA通过。限定任务文件diff --check通过；全树检查误触用户vendor CRLF告警，未修改那些文件，后续只查本轮路径。
- df91%/约7.1GB，按唯一clean_disk_space.sh rc0仍91%。只清理脚本规定的ROS日志/缓存/受限系统轮转日志，无额外删除；被删除日志不能依赖恢复，本轮证据及源码保留。没有ENOSPC或磁盘导致CAN故障证据。
- 复用/tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place，cmake --build --target grasp_lift_executor near_depth_executor_test -j2。第一构建未结束误重复启动，准确TERM旧cmake3853054/cc1plus3853068，保留包含最新Eigen实值修正的第二构建；旧失败与新输出共同在waypoint_advance_build.txt，不将旧终止算通过。
- 缓存origin/main与本地left1/right119，既有分叉/历史审查未完，仅限定本地提交，不自动合并/强推。用户wiring/vendor/reference不动。

## 构建/回归结果

保留第二构建rc0，candidate cf5777e11d2ea2e685d610e5bcebf1a5eb2e14ba53caab322cd56c5cb94d3c16，canonical CPP0043c92374c2f3e3b8fc7de108ce3f3df3551db9d6c6330703babdfe821cf6dc。首次完整方法测试60s边界rc124/ROS context关闭后后续27用例连带失败，不称通过；卡点两项独立测试rc0。再次原完整43项（39旧+4新）全部通过rc0/3s，visual_grasp_feedback原10项rc0，日志waypoint_advance_{executor_recheck,prefix_tests,visual_tests}.txt。不更改实体时限，新增推进正/反例真实使用生产方法。

接收前检查两次依赖路径失败（PYTHONNOUSERSITE屏蔽用户can/错用旧home源码SDK无CreateCanBus），均在发送前退出；实际驱动使用/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk，已inspect核对ConnectPort/CreateCanBus签名，不安装/改依赖。以下部署/新SDK/实体结果待追加。

## 部署与原AUTO1启动

- 修复c0f56da。备份实际099bbc9至view_guard_20261013/waypoint_advance_previous_099bbc9/{grasp_lift_executor,grasp_lift_executor.cpp}，单executor部署cf5777e…/source0043c923…，actual install链接build一致。原入口87039b…/detector8e763f4…保持。最初检测器核验误写ball_pick路径rc1，正确pick_place路径SHA一致，不当部署失败。
- 新SDK接收rc0 epoch1791914645.304760/high4645.300900/100Hz、joint4645.300696，六使能true；q[-.318382962,1.845423885,-1.399614434,.013700835,.919893236,-.071226887]rad，gripper99.6mm/使能/无错误。motor_speed[-14,0,0,0,0,0]原始值，不冒称全部严格0；关节位置与上次静止记录相同。SDK仅接收，未初始化控制。
- 原观测目标[0,.98,-.75,0,.30,0]rad，prepare速度/加速度1%、原反馈生成持续时间（预计20s附近，按实际轨迹计）、适配器最大.189rad/s；原任务min[-1.5,-.3,-1.4,-.8,-1.2,-pi]/max[1.5,pi,.4,.8,1.2,pi]，既有官方物理速度/加速度300/500单位.001rad/s及.001rad/s²复用。当前保持→观测可涉及六轴，后续MoveIt全轴路径/8mm1°/.08rad前缀照旧。原异常停止输出保持使能、禁止Disable/Reset，只有原成功释放/安全回位支持后失能；回退点为备份099bbc9，不自动回滚或重新启动。
- 命令：BRAIN_ROBOT_AUTO_START=1 STOP_AFTER_TARGET_ACQUIRED=0 DEPTH_ONLY_TARGET=0（各变量完整前缀BRAIN_ROBOT_），LOG_DIR=.../waypoint_advance_onekey，timeout -s INT -k8s600s /home/johnwick/start_brain_robot_cube_real.sh。host主timeout3854063/script3854064，session30940。复用ERROR-ACTIVE/RX增长CAN，不重载；相机启动首帧等待中，未冒称观测完成。
- 同步只读capture_scale_frames.py →waypoint_advance_exact（python3854209/session17393）、旧observer→waypoint_advance_live（python3854294/session38220），各590sINT/-k3s；不发布控制。下一读同一次日志/新三图/推进与原最终夹持输出，不重复启动。
