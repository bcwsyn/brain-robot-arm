# 同步转向靠近：生产几何通过，实体首跑在粗段深度门前停止

## 用户授权与实现

用户明确“同意同步转向靠近并实测”，应用提交 `198f2a5`、部署启动记录 `e8954d9`。ROS2/手术式技能用于核对真实路径、限定原geometry owner修改及保留用户原wiring注释/vendor/reference变更。

原 `TargetDirectedApproach` 添加默认false的可选同步分支，仅实体自动且 `terminal_target_frozen_` 时启用。当前FK指尖到原最终朝向下24mm预抓点，指尖平移和姿态SLERP同步；之后原插入。最终捕获点、最终朝向、TF/TCP、完整双段预检、任务限位/碰撞、原adapter/反馈、最终夹持/闭爪及唯一一键入口不变。没有直接发送J5固定值、调整深度门限或新增保护。旧非自动/未冻结调用保持原路径。

构建0/实际执行器32、几何14、尺度15、视觉10、wiring3共74项通过；新几何回归验证首点即平移/转向、末点等同旧路线、24mm间隙和原插入、5mm/.02rad保守采样界。

域78持久禁止执行launcher复用原模型与task范围，在上一实际冻结点/起点上，共享生产C++几何25预抓/8下降路点：MoveIt各16/8点、fraction1/error1、原范围全true、相邻max.068713/.028251rad。不是仅Python反事实，也不是新实体夹持；该域无driver/adapter/SDK，现场环境未纳入。review0/语法0，隔离主10581 INT0。

## 部署与实机命令

- 新binary：`fd0d086d1496dfe02d6c45b840ef430093eb1a444a5f335479a511bed914351c`
- 原CPP：`cd05f4adafa39e40bb754bf18a1e1d4ef09cfb59904a3e46166fca8738261034`
- geometry hpp：`58c6235629789c252e72b1f453f0080842b6fc9ddae975237c2329e9e977c73c`
- 唯一入口仍 `/home/johnwick/start_brain_robot_cube_real.sh`，SHA `87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0`
- 回退旧binary：`view_guard_20261013/synchronized_turn_previous_0c14428.bin`/b9f1c1…；可审计反向提交 `git revert 198f2a5`（先保护其他未提交改动，再停栈同步旧源/构建），禁止reset --hard。当前未自动回退已通过的软件实现。

新SDK6121.000385/high6121.001154/100Hz、六true/静止，q `[-.293948353,1.318753330,-.646836474,0,.330879520,0]rad`、99.6mm全开；CANRX35809440→35812384/ERROR-ACTIVE/error0复用。原prepare目标 `[0,.98,-.75,0,.30,0]rad`/速度加速度.01/原范围/反馈/保持使能清单见进度。唯一命令：

```bash
BRAIN_ROBOT_AUTO_START=1 BRAIN_ROBOT_STOP_AFTER_TARGET_ACQUIRED=0 BRAIN_ROBOT_DEPTH_ONLY_TARGET=0 BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/view_guard_20261013/synchronized_turn_onekey timeout -s INT -k 8s 600s /home/johnwick/start_brain_robot_cube_real.sh
```

## 本轮实体结果（不能误称新末段失败）

PREPARE6229.137 → SEARCH6248.711/OBSERVE_POSE_REACHED → ALIGN6263.091 → GRASP_READY6266.038。epoch公共前缀179190。原粗段step0..11共12条轨迹/12真实到位；距离0.296→0.227m后，原RGB仍完整，但depth目标区域出现空洞。step11新测量 `.255249m`、随后0.6s等待仍无合格同帧深度，6284.217 `FAULT_TERMINAL_DEPTH_STAGE_FAILED`，6286.002 STOPPED。

没有本轮20cm冻结、没有`synchronized_turn=1`主路径/同步实体输出、闭爪/抬升/释放。第一轮0c14428的20.2cm冻结成功仍有效，不能被本轮不同视线深度空洞抹去。本轮停止发生在新几何被调用前：198f2a5未改粗段或检测器，不认定同步几何实体失败、CAN断联或整体代码已验收。

主19312 rc1、原cleanup无Disable/Reset/回零；读采42097/92438 INT各0。结束SDK1791906435.513070/high6435.508979/100Hz，六true/速度0、q `[-.272114284,1.292049792,-.644707172,0,.340199578,0]rad`、夹爪99.6mm/使能无错误。未完成安全返回，因此保持使能不直接失能。

## 三图/同帧深度核查

新0018三图已看：完整方块/两指在画面下缘，native depth6213.573836、RGB/debug6213.582106，debug202mm4750样本；这是启动当前姿态，不是新运动完成证据。

新0041三图已看：原RGB完整紫块、两指可见未包围；debug黄色深度支撑仅剩目标上缘窄条，大部分目标区域黑洞，255mm/16样本/WAITING_FOR_STABLE_FRAMES。16bit原生depth直接显示近黑不等于全0；这里的“空洞”来自同帧配准debug及数量而非单凭原图亮度。0045是停止后缓存/旧戳，不当作当前有效视野。

精确采集 `synchronized_turn_exact/frames.jsonl`：6280.183/6280.384/6280.783 RGB/深度差约9/5/9ms，目标z226–227mm；6280.984变259mm，随后255mm。6282.184 RGB配depth6282.176（约8ms），raw点 `[-.006021353,.017861332,.255]m`；后续248附近少量样本和多帧无raw点。目标完整框在原RGB内，不是出画或关灯。不能把约30mm深度跳变直接当作物体移动。

源码事实：检测器在 `depth.valid && camera_info_ready` 时发布raw点/尺寸，稍后单独发布没有header的target_valid/depth_valid Bool；raw点存在不等于同帧通过稳定/尺寸门。执行器当前只要求Bool新鲜与点/框/尺寸同stamp，异步布尔可能来自相邻帧是进一步核验事项，尚未唯一证明step11的具体错误。未修改检测门或关联时间规则来掩盖空洞。

## 下一步授权边界

同步几何局部修改已经完成并获授权，实体未触发；新的障碍为粗段可靠深度在23cm附近结束。曾提出把重测点20cm提前为23cm，但用户没有同意，指出目标高度/尺寸变化下固定距离仍不通用，明确要求搜索官方/GitHub解法。23cm未修改或应用；最新研究和同帧数字复核见piper_depth_holes_reuse_20261013.md。不得把用户这条回复当作23cm修改或新质量驱动策略的应用授权。

不盲重复同一空洞失败、不再次刷写/Reset/MasterSlave/激光/底层巡检。固定clean_disk_space.sh rc0，90%/7.8GB清前后不变，无ENOSPC/扩删。Git仅本地，origin/main历史推送审查未完成，保留用户原改动。

证据SHA：visual_stack `01759c8c2e25500acaac6141f1fd0442f7573e4a96d7965afbc07f2f22928e3a`；onekey console `2d32b4106679a0c375ecd220a5b103f4aa8eb8c4e286cdf0b6e2077c20b90db5`；生产规划json `43696e1175951f94bfe89ae9a6bfb348f92f1e2a32721dd62bebe9e0de89b1b2`。完整路径和测试输出均位于 `/home/johnwick/brain_robot_logs/view_guard_20261013/`，未把大日志/图像/构建产物纳入Git。
