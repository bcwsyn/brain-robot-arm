# PiPER ROS 调试完整交接记录

## 最新近距代码实施（2026-10-11 23:08，未实体部署）

用户“确认修改”已实施原detector/executor兼容补丁：独立合格原RGB矩形＋现3D锁存/实际图像时刻TF核同目标；不改target_valid/depth_valid初始门、不刷新测量时刻、不追新背景、不用规划J6末角。原轨迹等待内核RGB/反馈，真正丢失请求既有软件stop和adapter disarm保持使能；最后复核新增明确的锁存3D/RGB预测模式，仍用原夹持几何。0..80mm仅已有SDK/adapter命令范围；通用几何实际会接受.1019，所以闭爪处现在拒不可信缓存，不阻止六轴靠近或写零点。

最终8目标构建、9套件83项及独立detector1项共84通过；旧图10包/9否定例和新detector前后实际图回放通过，但输入时效模拟/合成方法测试≠实机抓取。记录`docs/evidence/piper_near_depth_rgb_tracking_20261011.md`，归档near_depth_validation_20261011.wBut3v；runtime的入口0e976b0a…/executor107ce501…/YAML75612194…/detector2deb634f…**未改**。规范功能true不是已部署；SDK50857/PGID50855保留，无新运动/闭爪/Disable。

下一先审查规范与实际既有OFF-preview差异，选择性部署本补丁，从原观测姿态新可靠RGB-D seed验有限末段并同步原图/命令/真实q。当前无深度处不喂历史seed续跑。J5朝向算法尚未改变，J6执行偏差/实际接触区/夹爪基准尚未解决；不能执行旧反向全路径或宣称完整一键已成功。30s/30mm预测窗口不是新运动授权，不重置旧采样预算，70/105mm不重测/不删。

本轮Git仅本地，origin/main实际仍6ebd0c5。最新确认仅改代码，未再次尝试被审核拒的push。下一第一命令`git -C /mnt/hgfs/ub show --stat --oneline HEAD`，读本条和新证据后继续，不退回CAN/固件基线。具体命令、hash、失败修正和测试边界均在最新进度。

## GitHub授权解释更正（2026-10-11 22:34）

方案提交4d3001b及最新阻断记录仅本地。代理把用户“确认”解释为上一轮推送问句批准，但auto-review判定当前话语与近距方案相关、不足以批准共享main写入，已在创建进程前拒绝；没有绕过/继续重试。下条“用户确认origin/main推送”是被更正的代理判断，不能当远程授权。真实远程仍6ebd0c5；12新增blob版本/6路径已人工＋有限模式检查无发现，不是完整Gitleaks保证。需用户明确批准目标origin/main普通非强制推送；共享main写入影响接手者。实体/方案无新变更，SDK50857保留。

## 最新具体修复路线（2026-10-11 22:31，仅方案/只读计算）

用户确认origin/main普通推送、询问如何解决近距深度归零。本轮未改控制代码/未运动，SDK50857保留。实际static_target_lock已开，不再重写；拟改原RGB形状＋锁存对象关联观察，以及现executor的有限末段/最后复核，区分新鲜RGB-D实测和锁存3D＋新鲜RGB＋实际反馈预测。SEARCH/初锁存仍需可靠深度；近距depth_valid保持false，不填洞、不追新紫色、不绕adapter、不默认固定整个抓取朝向。最终二维居中不能代替实际夹持区/真实开口证据。

本轮只读新投影使用上轮运动前真实点和起终实际q（J6真实0）：预测Depth-Z .142515m、RGB(149.457,157.265)，与末实图(151.022,162.842)误差5.792px；只是假设静止/现mount下的模型核验，不是新深度测量或标定。完整SHA/源码责任点/官方资料/下一离线否定例见最新进度。先现10包离线验方案，补临时monitor活会话验证，再做具体补丁/有限实机，不能因方案已记录就闭爪。目标未抓取，原入口/executor/YAML不变。

## GitHub同步断点（2026-10-11 22:26）

本轮20a5844增量已人工＋有限凭据模式检查，6文本blob最大587070字节无发现；不是完整Gitleaks保证。真实远程main核为6ebd0c5（已含1a6a662）。向origin/main普通推送在进程启动前被auto-review拒绝，理由当前用户对共享main远程写入缺少明确授权；未绕过/重试。本轮20a5844及同步阻断记录仅本地提交、未同步GitHub。下一需用户明确推送授权；不把此阻断当实机故障，实体和策略断点见紧随的22:23条。

## 最新有限靠近与深度缺失（2026-10-11 22:23）

在1a6a662的真实末q上，原MoveIt LIN→adapter已执行一段总11.892mm/前进10mm/基座Z下降10.324mm，30点/2.823503秒；未闭爪。真实末q rad[-.207269608,1.890074844,-1.239431088,0,.908518408,0]，J5≈52.054270°，J6仍0（规划+.931564°）。末原图方块完整、中心约(151.022,162.842)，横向已到粗两指中线，不能称实际夹持区已到。

真正的新阻断是DEPTH_REJECTED_INSUFFICIENT_SAMPLES，不是彩色目标丢出画面。前5帧同轮廓5032..5202深度样本/.151m，后5帧0/0/4/0/0，整图仍43908..48879非零且最小.149m；4点中值.179可能背景，不能当新目标深度。近距无有效深度/约15cm边界为实测与推断，不是已查证的型号最短距离规格。原设备2bc5:0657由官方udev标为DaBai DC1，Astra是驱动名，不套Astra/Gemini产品范围。

只读planner第一次TF未来22ms失败已修为≤.3秒等待原图时刻，13测试通过、不用latest。一次CLI误用SetBool服务已按原Trigger更正、失败时未发布轨迹。临时监控随失败父会话提前结束，事件只到运动前2.908秒；**没有实际运动段命令/反馈或专门视觉中断证据**，已显式原disarm=true，不能声称监控验证通过。后5组停稳采图max53.379ms/六轴不变。自有栈全退出，SDK50857保持，入口/executor/YAML原SHA不变。

详docs/evidence/piper_near_depth_20261011.md。原FinishGraspAndLift/FreshFaceInsideJaws要求新鲜有效RGB-D，所以仅修原彩色形状或加J5不能解决近距无深度；下一先在既有executor设计“可靠深度锁存静止目标→新鲜RGB跟踪/原反馈与FK约束末段”的有限策略和离线否定测试，不将无深度伪造为valid或盲闭爪。相机→实际接触区仍未独立标定，夹爪.1019缓存亦非实体开口。旧全反向J5路径不执行；目标未抓取，无自动续跑。

## 最新末段实机瞄准（2026-10-11 22:11）

起点3b10e99。原target_directed全路径隔离规划成功但预抓取J5从54.625降到42.975°，下降结束44.801°；这不是实体执行证据，不能照搬会丢视野的旧段。未改生产executor、TF、TCP、YAML或入口。新增test/review_camera_jaw_alignment.py只读规划，复用原工厂内参/旋转、同帧目标、真实起点、原MoveIt LIN；11纯几何测试通过。可见两指中线(150.5,155.5)只是屏幕瞄准参考，不是接触标定。

已沿原MoveIt→adapter执行一次15mm图像面平移，36点/3.444444秒，图像误差31.08→8.63px，方块完整可见、没有新TARGET_LOST。真实末q rad[-.22136436,1.882870472,-1.271650156,0,.949494364,0]；J5≈54.402°，J6仍0而规划2.571°，不能声称六轴完全到位。只是新任务单段瞄准，不重置旧4段标定预算。临时栈全停，仅SDK50857/PGID50855保持，原disarm成功，未闭爪/Disable，不会自动续跑。

证据目录large_j5_view_20261011.7cb6Gu，完整命令/响应/SHA和局限见docs/evidence/piper_image_aim_20261011.md。CLI印出的camera_loss未实现专门视觉中断，已更正，实际是原adapter反馈/限位停止加显式disarm。J6原因尚未查明，不凭数值改限位/驱动或扩大轨迹。下一从实际末q重新规划一次最多10mm前进并配套命令/反馈及RGB-D，核深度确实缩短；不重复底层巡检，不直接闭爪。完整一键抓取仍未验收。

## 最新检测实机部署已验收（2026-10-11 21:54）

0b661a4补丁已只部署detector source/header/实际include/bin，旧source/bin备份large_j5_view_20261011.7cb6Gu/detector_before_deploy。实际只目标重建最终bin73b7a2b4…，新paired域78回放4稳态全target/depth=true；实体静止38秒13快照/11就绪全true、点(.009114,.035452,.151)m，之后5组时间配对max37.149ms/关节不变，原RGB完整。详docs/evidence/piper_raw_shape_depth_association_20261011.md部署段。

用户继续完成，下一不再重复CAN/注册黑洞检查，复用原grasp_lift_executor的有效目标/姿态生成和MoveIt核末段方向/耦合靠近。目标原RGB约(120.11,161.11)，粗两指中线(150.5,155.5)，仍左约30px/下6px；不是可闭爪或已校准TF。原入口0e976b0a…/实际executor107ce501…/cube_task_real75612194…保持，规范OFF-preview executor仍未自动部署。临时相机/检测/观察已停，仅SDK50857/PGID50855；末六轴不变/J5 54.624901°，未闭爪/Disable/新TF，无自动续跑，抓取尚未完成。

## 最新检测修复待部署（2026-10-11 21:50）

起点2473f22，仅detector/纯OpenCV几何头/6项测试/域78有界回放及CMake改动。原RGB形状＋工厂D2C同轮廓真实深度；完整RGB中心射线结合实测中值Depth-Z回DEP光学，保留原640×400误差/时刻/质量与尺寸门，不填洞、不改TF/执行器/YAML。旧同五包false/TARGET_LOST，新稳态5帧target/depth全true、.151m，四类合成否定全拒绝。编译/6测试/两个回放exit0，详docs/evidence/piper_raw_shape_depth_association_20261011.md。

生产此刻仍旧detector，下一仅部署这一个已测二进制及source/header/实际CMake include，静止两相机+原detector launch核实际图/点。**不全包同步规范OFF-preview executor或其他配置**。新源2deb634f…/bin099969f9…，临时build/tmp/piper_rgbd_shape_build_20261011.fygBnq；旧/新输出在large_j5_view_20261011.7cb6Gu。SDK唯一50857保持，末J5 54.624901°，未新运动/闭爪；目标未抓取，实际接触区外参仍需核准。

## 最新大步实体结果（2026-10-11 21:44）

起点e12944a，用户明确批准J5约+6°。原MoveIt/Pilz/PTP比例.002生成206点/20.453293秒，经原adapter真实接受；J5 48.708053→54.624901°(实增5.916848°)，其余五轴不变，5组原时间同步采图最大11.371ms/组内range0。已看0005原RGB，完整方块bbox(90,125,61,71)、中心(119.69,160.56)，恢复视野但未证明物体已处两指内；没有闭爪/失能/新TF或固件操作。旧4段预算未重置。

原检测器静止实际仍target/depth=false、DEPTH_REJECTED_TARGET_LOST；注册debug仍黑洞/残片。下一已批准只修检测器：原RGB完整轮廓门+原D2C关联真实深度，保留原深度optical三维和640×400误差单位、质量/尺寸门；隔离回放后仅部署检测器，别将规范OFF预览executor等整包覆盖。原cup_detector实际源90510e5f…/规范7ebfc1e2…，此前raw只读观察尚未部署。70/105mm和旧26°否定保留，不重新做基础诊断/标定扫描或盲闭爪。

目录/home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu，完整SHA、命令/门/退出局限见最新进度。21:43临时相机/高级栈/分析观察全停，实际SDK唯一50857/PGID50855(auto_enable=false/gripper_exist=true)保留。末q rad[-.262724084,1.888278112,-1.280686148,.010396624,.953384376,0]。停止适配器输出不是失能，没有后台自动续跑；目标尚未抓取。

## 最新实体三段与检测拒绝点（2026-10-11 21:26）

起点9d2b53a；本轮只沿原高级MoveIt→adapter完成预算剩余三段：J4+0.8/回中心/J5+0.8，54/52/54点真实接受、共15组120ms内静止配对。J4实际0.549707→1.271323→0.595683°；J5 47.952455→48.708053°，其他轴不变。加历史一段，**4段/11.599397mm模型路径，次数已用完**；没有新闭爪/失能/回零/固件操作，TF/TCP/默认生产参数不改。目录/home/johnwick/brain_robot_logs/micro_capture_20261011.X3KR3g，完整失败点/命令/哈希详docs/evidence/piper_bounded_rgbd_motion_20261011.md。

最后原彩色bbox(96,163,59,73)底236<240，已完整入画，纠正即时“仍不完整”。原检测器隔离回放仍TARGET_LOST：注册深度图紫块只剩bbox(304,350,99,46)，旋转长宽比2.0106>原1.45；原RGB比1.2679合格。这是残缺深度网格中做形状门导致的具体拒绝，不是实体黑影/反馈/碰撞。首次回放分析QoS错误已据原volatile纠正重验，未改生产QoS。未得新外参/接触区标定或抓取成功，不能拿二维对齐闭爪。

用户新问要求较大步后小幅回调，下一应说明J5约+6°候选及原彩色形状/有效深度关联方案，回到实际两指中线/延长线和三维靠近，不再无限小幅采样；本轮没有执行该新候选、扩大旧次数或放宽深度。原相机/高级栈/回放全退出，只保留反馈50857/PGID50855及daemon；21:24再读201反馈六轴range0/.1019夹爪缓存不当真实开口。末q rad[-.262724084,1.888278112,-1.280686148,.010396624,.850115896,0]，停止适配器输出且未电机失能，不会自动续跑。

## 最新驱动解耦修复与加载（2026-10-11 20:25，无实体使能/运动）

起点39783f9。实际入口是piper.piper_ctrl_single_node，不是_new旧文件；原驱动f2631dfe…使能话题写夹爪0，服务遇缓存101900回退0后写夹爪。已假SDK复现旧两入口0x02→0x01/零目标，新代码正向使能只使能六轴，不写夹爪；已有显式开闭仍首帧0x03/后0x01、set_zero0，未改正常目标逻辑/新增门。只这两个原先干净的driver/test路径有意修改，其他vendor/reference已有变化保留。77项全部通过，源码规范/部署同SHA c0153c88…。

旧47039组TERM后wrapper退出、47043 SDK未退出，终止期间/proc/environ权限异常导致一次轮询脚本中断；后续严格同标记/UID/PGID/start_ticks核后精确KILL旧47043，确认唯一后启动50857/PGID50855、auto_enable=false/gripper_exist=true。新代码实际导入源已核，3秒595反馈六轴范围0/J5≈47.952455°，未发使能/轨迹/夹爪/Disable。现仅该反馈和daemon47019；下方旧47043/37594存活结论已覆盖。原入口/默认executor/YAML不变，无自动续跑。

详docs/evidence/piper_arm_enable_gripper_decoupling_20261011.md。新有限候选J4+1→中心→J5+1三段FK弧长9.839mm，加已用1段=13.798mm/4段，可能在旧预算内，不必先扩大到±6°。**只是FK、未实时规划/执行**，下一项沿原MoveIt→adapter核这个范围并可靠采多姿态/独立验证，逐段看图、不闭爪；不要重跑旧8段/26°或把模型自洽当真实夹持区。目标未完成。

## 最新时间配对接入（2026-10-11 19:55，15组静止数据，无运动）

起点8943c04。新增只读test/collect_static_rgbd.py，复用message_filters4.3.19原同步器，固定原RGB/depth/depth_info/真实joint_states_feedback、header队列/120ms不放宽、depth/info同帧及停稳历史，保存原PNG/stamp/K/q/SHA。只在test使用、不改控制栈或添抓取门，不是第二入口。21项新回归及startup/jaw/sampling共69通过，含真实官方同步器内存回放latest偏差复现。

只有限运行原两相机命令，47043驱动不动，无MoveIt/adapter/闭爪/失能。14.049秒取得15组，最大跨度72.845ms/年龄74.401ms，六轴范围0/J5≈47.952455°；相机全退出，仅原反馈及daemon47019。一个姿态15帧不是15标定姿态。原图仍裁切，各组紫色相关深度中值.155m；角点圈选深度可能背景，不当CAD点或新外参。普通自主实施规则保留，不扩运动预算。

详docs/evidence/piper_static_rgbd_pairing_20261011.md，数据/home/johnwick/brain_robot_logs/static_sync_20261011.a1GWut/capture。目标未完成；原入口0e976b0a…/executor源码107ce501…/YAML75612194…不变，4段20mm仍只用1段。下一项可信多姿态/独立对应，不能拿同姿态重复图或旧26°回填TF，不擅自扩±6°。

## 最新实测与原入口修复（2026-10-11 19:40，静止采集，无运动/失能）

起点ceecb0d。旧37594驱动已不存在；can0活跃未重载，原唯一脚本AUTO_START=0有限130秒到[7/7]/IDLE。22条静止采集六轴不变/J5≈47.952455°；原图有紫块，但下沿裁切，1条满足120ms，深度相关样本中值.155m不等于合法抓取点。其余前期latest抽样存在5Hz/3秒相位偏置，后期确有深度停帧并自动恢复；没有新TF/TCP标定或抓取成功。

退出只到关闭行并报核心转储，本轮子进程仍活着；精确按本轮LOG_DIR标记TERM清除了视觉/检测/相机/candump，仅保留47043/PGID47039反馈驱动（auto_enable=false/gripper_exist=true）和非控制ROS daemon47019。不再沿用旧PID存活结论；没测新六轴使能，不把“未发Disable”说成使能读数。SDK日志及保留CAN窗口都有最长约3.4秒接收间隙，不能宣称绝不掉帧，也不能凭根盘34%把它归因磁盘。

只对原一键cleanup修二次信号中断：trap清EXIT、对INT/TERM用空操作handler，保留helper信号能力；旧二次TERM用假ROS明确exit -15，新增两项及原测试11通过，两个入口bash -n通过并同SHA0e976b0a…；实际executor源码107ce501…/YAML75612194…不变。这个补丁不证明硬件本轮核心转储唯一根因已解决，未重跑整栈掩盖。普通可逆改动自主规则保留，没有扩预算/闭爪。

详情/命令/图像及日志SHA、裁切和深度统计、退出清理范围、回退见docs/evidence/piper_static_capture_cleanup_20261011.md。下一项改进只读RGB-D/真实反馈按时间配对采集，保留120ms，不重复旧拟合或基础CAN检查；本轮无新运动，4段20mm仍已用1段。

## 最新自主实施记录（2026-10-11 17:16，只读工具代码及隔离接入，未运动）

用户最新明确“先自己推进，随后发现问题再修改”，本任务范围内普通可逆代码修改/验证先说明后自主完成，不再逐项等待；覆盖下方普通代码逐项征询的旧流程要求。不把这句话解释为扩大既有实体预览4段/20mm（已用1段）、±6°采样或新增闭爪授权。当前唯一目标/原入口/MoveIt→adapter及异常停止、先安全返回再失能规则保留。

已将上轮临时采样核验变成规范test/review_calibration_sampling.py，复用现FK和实际配置，不是第二入口或运动程序。离线模式给完整五姿态/八往返/路径/激励/合成方法约定；可选--plan严格限定域78、实读execution=false及相同模型，只调规划/场景服务并保存全部MotionPlanResponse。错误/中断保存已完成响应，拒绝覆盖历史输出。新CMake只登记测试，无默认部署修改、无工作区完整构建。

37项pytest通过；新工具实际域78一度接入验证八段全成功，各20点，完整169,959字节JSON已保存，不再依靠截断stdout；但八往返总模型tip弧长27.595637mm仍超旧累计预算，未执行。离线六度只验证工具模型输出，不重做已否定真实拟合。实际入口/executor/YAML哈希不变；原37594驱动保留，无新相机/真实反馈/使能测量或关节/夹爪命令。隔离launch定时124，计划完成后的已知析构-11单独记录，临时节点已退出。

详docs/evidence/piper_calibration_sampling_tool_20261011.md（命令、完整输出路径/SHA、测试与限制）。当前仍没有实际新外参或成功抓取；下一重点可靠停稳RGB-D真实观测/独立验证，不回CAN基础、不重新扫26°，不把现模型路径或已知合成解直接回填TF。

## 最新自主推进核验（2026-10-11 16:58，隔离规划/方法验证，实机未运动）

用户希望暂时不用参与，已自行推进可独立完成的离线部分，不把“自主推进”默认为撤销逐项生产修改审批或扩张既有4步/20mm预览。起点4e117b3；唯一原入口、实际executor/YAML哈希不变；原反馈驱动37594保留，临时隔离节点已全部退出，没有实机关节/夹爪/使能/失能命令，也没启动真实一键抓取。

上条J4/J5各±6°建议不再只有FK：已复用既有review_surface_grasp_plan.launch.py、实际模型/配置，在ROS_DOMAIN_ID=78实际读取allow_trajectory_execution=false后，通过现Pilz PTP做8段独立往返，客户端汇总全部规划成功。J4负向模型tip离中心最大17.63mm，J5正向23.74mm，总路径165.57mm；超旧预算，仍未执行。场景无world障碍/Octomap，只有模型自碰撞及选点开口对照，不能据此宣称桌面间隙、实体开口、adapter执行或视觉纹理覆盖通过。客户端中部stdout截断，证据仅保存可见首尾4段和最终汇总，不伪称全部检查原文已归档。

模型两采样轴夹角约89.9998°、平移解条件数1.4142；进一步用实际FK构造已知变换的5姿态合成数据，OpenCV4.5.4/Park坐标方向核验通过（平移误差约4.5e-12m，仅数值测试），J5单轴对照非有限解。官方要求非平行旋转，与此一致；不是实机外参或新部署候选。旧真实数据78.5/113.4mm敏感度候选仍否定，不能又拿它们回填TF。

隔离MoveIt规划完成后定时SIGINT退出，在析构阶段exit -11，历史同阶段问题已有记录；launch返回124，原驱动未受影响，不转回CAN/固件排查。本轮方法、可见响应、来源SHA/日志位置及复现参数见docs/evidence/piper_calibration_plan_20261011.json。真正剩余项仍是可信真实采样/独立校验相机→夹持区，再提出唯一末段补丁；不是继续扩大J5或新增闭爪门。没有实际抓取成功，新的实体采样范围和生产补丁仍按已明确规则处理。

## 最新无标记标定核验（2026-10-11 16:43，未改生产/未运动）

用户暂时无法提供棋盘格，不再把打印板作为唯一下一步。静止采1632×1224与640×480彩色图后，已恢复并验证640×480 YUYV/30fps，临时相机全部退出，仅原37594反馈驱动；原一键/executor/detector/YAML哈希不变。新ROS RGB1791707154.8658688/feedback1791707154.900522，六轴不变/J5=47.952455°；本轮未读新使能，不把历史使能当实时。图中方块仍触下沿，无新深度或合法抓取点。高分辨率不是简单尺度放大（实测映射约2.31倍加偏移，非2.55），不能直接套生产内参；精确CAD角点仍不足。

已实际复用target_directed旧RGB-D/关节：严格<=120ms筛得11帧，排除固定夹指及紫块后用SIFT+工厂D2C+PnP/双深度刚体估计相机运动；不是又扫旧26°轮廓。两种候选留一关键运动对后相机位置变化最大78.5/113.4mm，均明确否定、未部署；初次OpenCV Park图连通候选固定点漂42.5mm也否定。旧桌面平面独立诊断与当前TF预测base-Z差21.88°，但桌面与base平行未独立确认，不能据此直接修旋转或平移。完整来源、方法、矩阵、残差和采集失败回退在docs/evidence/piper_markerless_calibration_20261011.json，不再重复这些旧数据拟合来称标定成功。

下一建议是无标记自然特征的停稳RGB-D采样，不需用户重测70/105mm：围绕当前中心，分别J4±6°、J5±6°，每次回中心，夹爪不动；当前仅FK提案，无碰撞/轨迹规划，无运动授权。模型指尖离中心最大23.74mm，四次往返总路径约165.5mm，明显超旧4步/20mm授权，不擅自执行。先向用户明确新范围获准，再沿原MoveIt→adapter核规划及桌面纹理重叠；停稳采准确图像/反馈时间，补足非平行转动，留独立数据检验。任何TF/TCP/抓取代码修改仍先列具体差异获同意。本轮没有抓取成功，不新增门、不重置CAN、不回零/失能。

## 最新结构对应结果（2026-10-11 16:15，未改生产部署/未运动）

b6c93af计划已推进到结构图和当前几何矛盾定位。用户确认原640×480图A=(95,311)/B=(513,315)为远离螺丝的自由末端；精确CAD顶点尚未确认。实际网格含完整76.5mm长/56mm最大宽渐窄夹指，.1358m含模型末端，不再猜模型只有底座或重复叠加长度。原TF+D2C投影模型最末端平面v约487..582全部出画，而实物自由端v311/315。当前整套几何解释不一致，但未唯一求出应改哪个旋转/平移分量，禁止宣称已标定或直接回填旧26°。

图在/home/johnwick/brain_robot_logs/jaw_landmarks_20261011/structure_review/finger_structure.png，完整对应表/复现与数值在docs/evidence/piper_jaw_structure_20261011.md/.json。A/B确认只属于SHA5b695ae3…原帧，不能套未来图片。侧照聊天可见未本地归档；三维深度核验右0/左6样本有背景可能，不能当标定点。保留70/105mm与未知开口/安装旋转，下一步补齐具体面边角/尺度或等价独立标定约束；两个未定顶点区域不足完整外参，不能重复扫参或用整体J5变化制造相机/夹爪相对视图。

只扩展现离线review与测试、37通过；本轮无相机/ROS新启动，无关节/夹爪/使能/失能命令。主机起终仅原37594反馈驱动，入口/executor/YAML哈希未变。生效camera_mount同时影响目标base锁存及FreshFaceInsideJaws，继续沿此几何责任链核校，不再做CAN/固件/观测基础重复。具体新TF/TCP/末段补丁仍先列旧新值获准，不新增闭爪门或扩大有限预览。

## 下一步明确交付（2026-10-11，仅计划，无代码/运动）

用户要求具体步骤：先交付侧照→640×480原RGB→实际网格的夹指面/边对应图和确认表，核模型是否覆盖实物指体；可信对应上再核外参，保持70/105mm，使用未参与拟合特征验证。随后定义真实两内接触面的夹持中心并与同一锁存目标核对，列出唯一具体外参/TCP/现executor末段Pose补丁旧新值、预期J5/末端行为及回退，获同意后实施。仍用原一键/MoveIt→adapter，不新写入口或硬加J5；离线通过后按已用预算执行有限不闭爪小段，真实进入夹持区才推进闭爪。此轮没有新采样/控制/测试实机，无新增运动授权；详进度首条，不直接部署被95c9ff1否定的26°候选。

## 最新夹指侧照与候选否定（2026-10-11 15:58，默认部署不变、未运动）

新增640×480静止原RGB位于/home/johnwick/brain_robot_logs/jaw_landmarks_20261011/evidence/0002_rgb.png，RGB1791705038.214105/feedback1791705038.2960317，六轴不变/J5=47.952455°。只启动有限彩色相机及观察器，预期timeout124均退出；未采新深度或启动MoveIt/运动，收尾仅原37594。实际入口/executor/YAML未变。

重要更正：8050432的安装26°/模型开口45mm只是IoU排名候选，现高分辨率复核右内缘du/dv实际+0.2625、候选-0.575，方向相反，明确未通过核验，禁止部署/重复扫参。原实物两指都可见，不应把预测出画当实物出画。最前端内向网格小面Z125.778..135.800mm只用于核对，不能当整个实物接触面或直接改TCP。

用户侧照确认相机画面上下尖角对应同一实体夹指结构；撤回将其自动识别为两个独立物理指尖的解释。保留70mm/105mm测量，不要求重测，不凭无标尺侧照推新尺寸。照片当前仅聊天可见，未找到本地附件文件；文字观察和方向数值已归档docs/evidence/piper_jaw_landmarks_20261011.json。新增只读方向诊断及回归，33项通过。本轮六路径提交不含生产修改/vendor资料；下一步核对整根夹指面/边与网格的对应，再说明精确TF/TCP/末段变更获批，不能根据新照片擅自运动。

## 最新静止对应核对（2026-10-11 15:43，未改默认部署/未运动）

用户批准15:23对应方案；本轮仅现有相机有限采集+只读模型叠图，原唯一arm-only驱动37594保留。新鲜ROS六轴不变，J5=47.952455°；RGB1791703707.291524、depth1791703707.3776822、joint1791703707.4004095，分别差86/109ms且六轴采样不变，不称硬同步。紫块仍下沿裁切，注册到原紫色像素有21个非零样本/.177m中值，仅未过全部检测门的统计，不是新合法抓取目标。

用户明确原图左右黑色结构就是实体两指；此前“模型两指在画面外”仅指按当前URDF/TF算出的预测，不是实物不可见。现变换下模型开口0/20/40/70mm、depth/color基准共8组，两指像素轮廓均在v≥约243处、240高原图内像素0。只改开口/横向镜头基准不能解释实际两指约v155/158开始出现；安装旋转仍未标定，CAD接触点对应也未独立证实，不先断言唯一根因。

保留operator optical70/105mm，以相机安装倾角和模型开口做165组受限离线轮廓比较，最好候选26°/45mm、平均IoU.6195，未部署。26°是相机安装姿态候选，不是J5命令；45mm不是夹爪实测。原35°J5画面只做固定指爪轮廓对照，左暗区有背景/ROI污染，不算独立标定验证。没有求得已确认实际接触框架/末段Pose，不把候选变成抓取许可。工具/test更新、32项测试通过，详docs/evidence/piper_jaw_correspondence_20261011.json及进度首条。所有默认部署SHA未变，有限相机/观察器已退出，只留原37594，未调用使能、夹爪、回位或失能。

下一步沿已批准对应方案核对具体可见拐角/接触面与URDF的三维身份，区分安装姿态与指爪模型定义后才提出唯一具体TF/TCP/末段改动；不重复上述扫参数、不直接部署26°，不因实物两指明明可见再声称整个夹爪不在视野。用户代码修改审批规则继续有效。

## 最新实体/模型核对（2026-10-11 15:15，本轮源码仅隔离构建，默认部署不变）

用户批准实图/深度/关节/MoveIt综合分析及每步≤5mm、最多4步/20mm不闭爪预览。本轮原一键AUTO_START=0到[7/7]/IDLE，采真实RGB-D与关节；只读/MoveGroup参数/GetPlanningScene和静态相机TF生成三维网格/投影图。实际MoveIt的joint7/8固定0，来源adapter.model_only_joint_positions；它是闭合模型占位，不是实物开口。实际两指图中打开，gripper缓存.1019m仍不作实体开口证据。模型tip对应原RGB约(84,267)，彩色镜头测量解释约(155,267)，均出240高图下沿；既有70mm/105mm保留。用户说镜头不确定、大概率彩色；两镜头主要横向差约3cm，可影响横向TF基准，不直接改外参。报告/场景已归档docs/evidence/piper_jaw_{geometry,scene}_20261011_step1.json，模型图在/home/johnwick/brain_robot_logs/jaw_geometry_20261011_step1/review/。

完成仅第一有限段：现MoveIt/Pilz→adapter 61点/5.908秒J5+1°，实测47.010→47.952°，其他轴不变，模型tip步长3.958mm/tool1.588mm。原图方块bbox从[95,174,60,66]到[95,169,61,71]，仍裁切且后帧配准紫块无有效深度；没达到夹持区、不闭爪/抬升。驱动切换旧28090未响应TERM，和新arm-only37594短时重叠，在客户端执行前唯一实例复核未形成硬闸，实测期间精确KILL旧进程才解决；必须如实保留这个次序缺陷，不把命令服务成功当证明由哪个实例响应。已给后续客户端加唯一arm-only实例要求；默认脚本未改。收尾仅留下37594/PGID37573、auto_enable=false/gripper_exist=false反馈驱动，硬件使能保持、控制栈/临时检测器/相机全退出。最后原CAN47.978°/六使能true/故障0；停止后不可把旧采样当实时反馈。

本轮提交前已完成原图bbox/debug及同stamp RGB-D投影观测、严格不闭爪的OFF微步原型、只读模型分析和测试。原型每段工具/模型tip位移≤5mm、姿态≤1°、最多4段/端点累计20mm；新鲜反馈/原MoveIt/adapter不变。此分支无FinishGraspAndLift/闭爪入口，不能作为实体捕获已实现，完整轮廓只用于预览恢复而非正式闭爪新门。域78合成图回放验证零深度时rawRGB仍在且target_valid=false，有效RGB-D目标映射回同stamp原框；真实临时检测器观测验证通过，但没有部署默认executor/YAML。最新构建/测试及精确范围见进度首条；回退新提交后默认部署无需重建，因未同步。下一项从静止数据核对可识别指爪/镜头基准，不重新底层排障，也不直接开启预览去假称抓取。

## 最新目标澄清与方案复核（2026-10-11 14:43，仅说明/记录，未部署新运动代码）

用户要求“两指包围”必须表示实体方块已进入接触面的夹持范围，只差闭爪；不是图像居中、延长线交点或模型工具点接近。平行两指在原RGB中的透视收敛可用于朝向参考，但不能给出接触深度。完整轮廓用于识别/锁定，不应未经实体证据变成整个末段持续完整入画的硬性前提。下一候选：原图标出实际两指接触区，与已确认镜头→指尖70/105mm、同帧深度/TF和现URDF交叉校核；校核后以夹持中心/进入深度生成末段Pose，由现MoveIt→adapter协调六轴，不只改J5，不另写入口。若刚性相机视野不覆盖接触区，先明确这一几何限制，不承诺不断增J5能解决，也不凭出画盲目闭爪。具体新代码改动仍须先说明获准。

14:12方案之后已执行原入口AUTO_START=0、累计J5+2/+4/+6°，由41.07°ROS起点至最后47.01°ROS；后验原CAN47.035°，原始静止图仍裁切下沿。+6°到位后原栈出现USER_STOP/入口143，终止来源未查明，不能说成CAN掉线。此前“临时驱动已全部退出”的口头状态不准确：本次主机ps仍见PID24398、auto_enable=false/gripper_exist=false的原反馈驱动；其余本次匹配控制进程未见。本次未发任何运动/夹爪/失能命令，当前位姿不能用历史47.035°当成实时值。

规范工作树有未提交、未部署的视觉微步原型（检测器、执行器、配置、测试/头文件）；隔离编译和8套CTest通过仅是软件证据。原型仍依赖模型面点/插入量和未确认ROI，不能声称实现实体“只差闭爪”，当前不启用。此前默认启用120步累计靠近补丁被自动权限评审拒绝，未应用；保留关闭开关/4步累计20mm的离线替代，不绕过评审。后续新增实体预览须说明累计范围并获批准。默认实际一键脚本和部署源/YAML仍未改。详细命令/证据/计划见进度14:43条；下方14:12“尚未执行”已被本条实测记录覆盖。

## 最新实施方案说明（2026-10-11 14:12，尚未执行/改生产代码）

用户确认方向并问具体实现。已核对现检测器clipped与FreshFaceInsideJaws：先建议从实际当前J5每档+2°、最多三档累计+6°恢复完整轮廓，每档看完静止原RGB再决定，不以检测器false当无块；其次原RGB标两指内缘/尖端，结合新鲜深度与同采样时刻gripper_base坐标核对，而非追图像中心。二维夹在指间不等于深度到位；固定.1019m开口反馈及未标定旋转不能当已证实实体几何。候选生产实现只在现检测器补完整轮廓信息、现executor末段短段闭环及配套测试/参数，MoveIt协调位置朝向→原adapter，不另起控制器/恢复Octomap/改RGB-D闭爪契约。修改范围仍须先说明获准；本轮无新运动/源改，继续保持上轮姿态使能。详情进度14:12条，旧14:07现状未被新实体结果覆盖。

## 最新实体对比（2026-10-11 14:07）

用户批准较大渐进J5试验，原入口AUTO_START=0到[7/7]，现MoveIt/Pilz→adapter执行累计+2/+4/+6°，其他五轴及夹爪不变；静止ROS J5约35.06→36.98→38.97→41.07°。RGB+4°明显露出方块下沿、+6°更多但仍裁切，检测器仍false，未闭爪/抬升/释放。+4°查看和+6°启动同批调用导致确认出现时下一档已完成，随后停，不发+8°；后验+2°有很小下沿紫片，详证据docs/evidence/piper_j5_positive_steps_20261011.txt。以后先独立看静止原图再发下一档，不把false当作无物体。现保持原CAN J5=41.088°、其余[-15.061,108.248,-73.417,.550,0]°，使能true/故障0，栈及采集已退出，不返回/归零/失能。临时arm-only驱动已退出，默认脚本/YAML/抓取源未变，无新保护门或生产代码修改。实体支持用户正向修正，但尚无完整视野/两指捕获证据；下一步明确有限恢复视野或位置姿态联动的具体方案，再按用户代码修改审批要求推进。旧13:56“较大组尚未执行”已过时。

## 最新授权与已完成小步（2026-10-11 13:56）

用户确认后已完成J5+1°及返回，原一键AUTO_START=0启动IDLE，MoveIt/Pilz→唯一adapter61/59点，J5实际约34.99→35.95→35.06°，其他轴与夹爪反馈不变；原图方块仍不可见，桌面特征向上6.4px支持下看方向。控制/采集均退出，六轴保持使能，无新控制源码/YAML变化，证据docs/evidence/piper_j5_positive_probe_20261011.txt。为不碰夹爪只临时用同一驱动gripper_exist=false，默认入口不改。用户随后要求较大角度逐步对比，已明确下一组每步+2°累计最多+8°、目标入画即停、不闭爪，较大组尚未执行。此追加授权只覆盖比较实验，不自动批准抓取闭环代码或取消原验证契约；下一动作原AUTO_START=0重新采当前状态后按有界步进验证。

## 最新只读研究（2026-10-11 13:44，未授权新增动作/改动）

用户要求复用GitHub视觉伺服并优先验证J5正向修正。已确认70mm/105mm测量继续用，不再重复询问；“J5增大离开旧模型落点”不能说明离实体方块更远。已读ViSP眼在手上仿真/Franka源码、MoveIt Humble官方接口、PiPER GraspGen/另一固定相机项目与末段RGB伺服论文，兼容性和来源记在进度首节。候选是现executor末段图像闭环小步，先用现MoveIt→adapter验证正向J5实际图像，再按实际夹持区与距离联动位置/姿态；不是持续居中、重新搜索或硬加J5输出。当前Servo轨迹输出未接PiPER/adapter不收Twist，不能直接照搬外部Servo指令。没有改代码/参数、启动ROS或发运动；小步实测、闭环实现和RGB-only验收政策均须先说明获准。直接实机断点仍是下面13:28落点确认提前拒绝，视野独立未解决，不声称研究完成即能抓取。

## 当前实机断点（2026-10-11 13:28，覆盖以下“待实测”）

b95c03a目标定向变姿态已部署默认/home/johnwick/piper_ws，实际构建76秒/7套CTest通过，二进制db7bcdaf…；原一键real_full_20261011_target_directed实读新模式true/比例0.5/preserve=false，完整观测→SEARCH→ALIGN→GRASP_READY→精确TF锁点→29点靠近→9点下降→原5点纠偏。原CAN实测J5预抓取33.124°→下降35.113°，后稳定35.011°，不是固定朝向。当前先被原落点确认挡住：17.2→11.4mm大于10mm，未闭爪/抬升/释放。

关键软件时序证据：ExecuteArmTrajectory原0.04rad关节容差使返回早于真正稳定到位；J2在拒绝后仍完成同一已下发目标。拒绝后1.51秒/4.52秒的实际反馈用同URDF重算落点误差为1.94/0.73mm（模型证据非实体标定）。下一建议仅改现落点等待时序，保留10mm、不添加运动，须先获用户同意。另有独立视野问题：实际0042能见方块、0048末段看不见，当前CameraInfo与历史K一致；鲜RGB-D闭爪判断本轮尚未运行，等待修好不保证完整抓取。不要删门或恢复固定朝向。

原入口未改/未另建脚本，日志与图像在/home/johnwick/brain_robot_logs/real_full_20261011_target_directed，精选docs/evidence/piper_onekey_20261011_target_directed_run.txt含CAN和FK证据。脚本退出1、保持使能，栈/采集器全退出；采集器收尾ExternalShutdownException不影响已保存证据。无DisableArm/ResetPiper/MasterSlaveConfig。回退git revert b95c03a再同步实际8路径并重建；原TF等待/旧5°及10mm基线保留。完整命令/时间/下一项批准边界见进度13:28首条。

## 最新已批准实现（2026-10-11 13:19，尚待本方案实测）

用户确认目标定向变姿态方案。新target_directed_grasp_enabled=true优先于旧固定朝向分支，preserve=false；共用纯C++几何从实际工具基点对准锁定目标，随后连续下俯并联动工具位置/指尖长度，两个完整Pose序列都先经现MoveIt检查再交adapter。完全垂直候选在原任务限位下IK失败（J3接近-1.4）；采用目标方向到向下方向0.5旋转比例的斜向路线，隔离75+13路点→29+9轨迹、fraction1、原限位/连续性通过。模型末段J5 32.882→34.773°，不是全程增大或实机结论。隔离构建/7套CTest通过；已同步实际源/YAML，实际构建进行中。原一键/SEARCH/TF等待/夹爪检查未改，仍有相机局部捕获区出视野的模型矛盾，不删除门。下一步实际构建测试后退出域78规划器，原入口real_full_20261011_target_directed核对真实J5/图像；详见进度13:19首条及新snapshot/plan证据。下方“待批准”是历史。

## 最新待批准方案（2026-10-11 13:04）

用户要求不固定夹爪朝向，询问如何解决。本轮只读核对后提出：保持现base目标锁存，在现executor按工具伸出轴对准抓取区域生成逐点变化的Pose序列，保留绕轴方向/不额外扭腕，位置与工具偏置联动，由原MoveIt→adapter协调六轴；不是只关preserve开关（会回旧角度枚举），也不硬改J5。先纯几何单测及冻结快照无执行规划，检查指尖/六轴/相机投影再原一键实测。当前刚性相机视野矛盾仍需区分，不能保证变姿态使目标末段可见，不删除现闭爪检查。本方案尚未获具体实现批准，未改源/配置/发运动；详情见进度13:04首条。实际断点仍是下面13:02实测结果。

## 当前接手状态（2026-10-11 13:02，覆盖以下历史断点）

实现e48e4c9及交接28b6169已提交；USB随后恢复，受限CAN配置后原一键实测完成观测→SEARCH→ALIGN→GRASP_READY→精确采样TF锁目标→81点靠近→8点下降→5点纠偏。12:54:13.929模型FK误差7.1mm通过落点；随后因末段新鲜RGB-D目标不可用退出，未闭爪/抬升/释放。实际图像0051紫块可见、0056块已出视野，详细诊断JAW_CAPTURE_FRESH_RGBD_UNAVAILABLE_NO_CLOSE，尚未评估两指包围几何。当前不是Git/USB/TF入口阻断，无需重启或底层巡检。

用户问J5是否没动/保持朝向：原CAN观测17.156°、GRASP_READY42.408°、预抓取24.778°、结束19.761°。当前5°实现只把ALIGN朝向下俯一次，然后仍锁新四元数，MoveIt协调J2/J3并让J5补偿；没有实现靠近时J5持续增大。现外参+工具模型理想末段表面在深度视野下边界外（历史K的模型推算，未证明实体标定正确）。下一步只读核对完整抓取姿态/TCP/相机视野，任何新运动代码/参数须先解释获准，不直接改J5或取消闭爪检查。

仍使用唯一原入口/home/johnwick/start_brain_robot_cube_real.sh及默认/home/johnwick/piper_ws；本轮无源码/参数变更。日志/home/johnwick/brain_robot_logs/real_full_20261011_tfwait_pitchdown5_1253，精选原始证据docs/evidence/piper_onekey_20261011_tfwait_pitchdown5_run.txt。脚本退出1，保持使能/当前位置，控制栈和只读采集器已退出；未DisableArm/ResetPiper/MasterSlaveConfig。准确命令、阶段时刻、回退与模型/实体区分见PIper_PROGRESS首条。下方12:49“实体USB尚未透传”已经过时。

## 当前接手状态（2026-10-11 12:49）

TF等待修复已提交`e48e4c9`，9个指定文件，Git检查通过；当前本轮指定路径已纳入Git，旧“待提交”段落仅为历史。回退`git revert e48e4c9`再同步/重建实际工作区。下一条执行主机`lsusb`确认透传设备，确认后原一键实测；目前无新实体动作。

主机require_escalated执行通道已恢复，规范挂载rw、sudo -n true成功；即将提交已批准/已部署/已构建测试的TF入口等待修复。默认实际执行器SHA07c53d1e…，源码规范/部署99837388…一致，原一键e8c9f85c…未改。最新实机阻断变成USB透传：当前Ubuntu12:46重启，主机lsusb只有root hubs和VMware虚拟设备，无实体USB-CAN/Astra，can0和/dev/video*均无。无控制栈/无新运动。本轮不重复测试或基础运动诊断；恢复VMware实体USB连接后直接运行原一键real_full_20261011_tfwait_pitchdown5，验证等待精确TF后能自动靠近/5°下俯。用户授权仍有效，已有等待实现无需再次批准。最新命令/回退/证据见进度首条；下方10:50权限阻断是历史。

## 当前接手动作（2026-10-11 10:50）

用户已批准10:45入口等待修复。新代码StopServo后进入WAITING_FOR_FRESH_TARGET_TF，每20ms重试仍新鲜相机点原采样TF，不立即FAULT、不使用latest、不更新观测年龄；成功后锁定原base模型并继续原张爪/MoveIt靠近/5°下俯。规范和默认实际工作区均已编译，直接CTest7组及13项回放检查通过，实际二进制已更新。后续sysfs复核显示can0 up/carrier1，RX在1.2秒增长3197、错误0，说明内核仍收到帧；当前执行容器无法netlink或打开candump socket，因此不能读取位时序，也不能让原脚本通过其CAN检查。控制栈未启动/没有新运动命令。仓库只读，本轮仍未commit。下一步在可访问CAN socket且可写规范Git的Ubuntu会话提交本轮文件，再运行原命令real_full_20261011_tfwait_pitchdown5；等待修复尚无实机证明。详见进度首条；脚本/实体YAML/夹爪/外参未改。

更新时间：2026-10-11 10:42（后文保留历史背景）

10:45补充：用户不接受短延迟退出，希望至少完成靠近/目标入两指。下一入口修复建议已修订为“0.60秒只作单帧新鲜度，TF短暂缺失保持姿态等待/重试新鲜帧，锁定正确base点后自动靠近”；不再建议把整个等待限制0.60秒。总流程仍受原一键默认900秒与原停止条件约束。此为待批准方案，尚无源码/参数修改或新运动，详见进度首条。

## 最新实机断点（2026-10-11 10:42）

实现`8f5f701`已完成5°下俯Pose、隔离MoveIt80+8点规划和6套/52 tests验证，并部署到默认`/home/johnwick/piper_ws`（构建0，二进制c1d06b01…）。原一键5°参数回读正确，实测观测→SEARCH→ALIGN→GRASP_READY，但立即STATIC_TARGET_MODEL_UNAVAILABLE，未生成新抓取Pose、未张爪/靠近/闭爪。本次精确图像TF超前15–45ms，base缓存此前未成功初始化；age169620.545s是默认steady时间点的差值，不是47小时旧观测。FAULT之后6.4秒才有成功base点。相机确实看到居中的方块（dx=-3/dy=6），不是灯光或目标缺失。脚本退出1，保持使能，无ResetPiper/DisableArm，栈/采集器退出。日志real_full_20261011_pitchdown5，原始精选证据docs/evidence/piper_onekey_20261011_pitchdown5_run.txt。下一步先获准修复工作线程有界等待同一新鲜采样时刻TF，保持既有0.60秒门/不回退latest；不原样重跑、不把新下俯方案说成已实机验证。详细命令/哈希/下一步见进度首条。

## 最新已批准实现（2026-10-11 10:38，尚待实机结果）

用户批准抓取小幅下俯，已增加aligned_grasp_pitch_down_rad=5°：沿当前FK模型J5正向轴旋转抓取四元数，再用同一锁定base目标和0.1358m工具长度计算Pose；原MoveIt→adapter/一键入口、SEARCH/ALIGN/夹爪和既有检查不变。0值恢复旧固定ALIGN朝向。规范/实际源与YAML已同步，原脚本未改；实际工作区正在构建，新实机日志计划real_full_20261011_pitchdown5。隔离MoveIt80点预抓取+8点末段fraction1、任务限位/连续性通过；直接CTest6套52 tests全通过，原始规划和冻结快照已归档docs/evidence。此为模型验证，不是实体抓取成功；下一步待实际构建完成直接运行默认原一键，用真实图像和J5反馈确认。完整命令/哈希/回退见进度最新条。

## 当前实测结果（2026-10-11 10:26）

随后用户询问J5减小/实体抬起原因，本轮仅只读分析，未运动/修改代码。现配置preserve_aligned_grasp_orientation=true使抓取锁住ALIGN末端朝向；J2/J3改变后J5反向补偿。CAN阶段反馈J5为观测17.064°、GRASP_READY41.918°、预抓取17.044°、末段12.477°。离线模型在结束q固定其他关节时J5+1°使tip z约-2.48mm，支持用户局部方向；同一tip目标、+5°俯仰候选IK的J5约19.542°，尚无MoveIt碰撞轨迹/实机验证。待批准修改应在既有抓取Pose俯仰层而非篡改J5轨迹，不恢复旧IK失败枚举；详细数值与官方接口依据见进度最新条。目标/TCP/外参准确性仍未独立证实。

`c0dc5eb`已实现批准的落点容差8→10mm并同步实机配置；原一键运行参数确认0.01。已完成观测→SEARCH→ALIGN→GRASP_READY、78点预抓取、8点下降和5点纠偏；最终FK误差9.5mm通过落点判断，随即因鲜RGB-D检查`FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`退出，未闭爪/抬升/释放。检测器在靠近时LOST，真实RGB靠近前能看到方块、结束时看不到；不能仅凭错误名判两指几何或实体TCP正确。此处不是新加门或开爪反馈阻止靠近。原日志`/home/johnwick/brain_robot_logs/real_full_20261011_landing10mm/`，精选证据[`docs/evidence/piper_onekey_20261011_landing10mm.txt`](docs/evidence/piper_onekey_20261011_landing10mm.txt)。脚本退出1，保持使能，未DisableArm/ResetPiper，控制栈/采集器已退出。

用户最新要求对比J5：本轮观测姿态就绪实际+17.064°，下降纠偏结束+12.477°，差-4.587°；原始3A6帧与时刻见进度首条。只读核对结束，不另发关节命令。下一步在本轮证据上分析视野/TCP关系，任何新代码/参数修改先说明并获批准；不重复同一故障跑法。下方10:20“即将运行”是已完成动作的历史记录。

## 当前接手状态（2026-10-11 10:20）

用户已批准落点容差8→10mm和同一一键脚本实测。规范实体YAML和实际`/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml`已只改这一行；install符号链接生效，逐字节一致、YAML解析通过，SHA-256=`cc64e723…`。起始HEAD=`aec3cae`，脚本/执行器/运动轨迹/相机外参/夹爪策略没有变化。即将运行默认AUTO_START=1，日志目录`/home/johnwick/brain_robot_logs/real_full_20261011_landing10mm/`；当前尚无此参数下实机抓取结果。命令和回退见进度首条。以下2026-10-10“待用户批准”文字属于历史，不再阻断这项已获授权的运行。

## 最新实机测试（22:46:40–22:48:35）

原`/home/johnwick/start_brain_robot_cube_real.sh`以`AUTO_START=1`运行；没有改源码、YAML或脚本。完整命令、阶段和哈希见[`docs/PIper_PROGRESS.md`](docs/PIper_PROGRESS.md)首条记录，日志：`/home/johnwick/brain_robot_logs/real_full_20261010_retry_2242/`。

本轮[1/7]–[7/7]通过，实际到达`OBSERVE_POSE_REACHED`并进入SEARCH；紫色方块有效后到ALIGN/GRASP_READY。精确时间戳目标成功锁到base_link `(0.432,-0.112,0.080)m`。张爪请求50mm但反馈仍102.1mm；实体YAML允许开爪反馈不确认仍靠近，所以抓取器执行了78点预抓取、9点Cartesian下降及一次5点落点纠偏。最终FK落点误差8.6mm，当前阈值8mm（仅超0.6mm），因此`GRASP_LANDING_UNCONFIRMED_NO_CLOSE`，没有闭爪/抬升/释放。开口反馈不是靠近阻断，前轮TF缓存故障本轮也未重现。

脚本退出，未发`DisableArm`或`ResetPiper`，PiPER保持使能，控制栈无残留。本轮未改任何代码/参数。待用户批准的唯一最小配置候选是落点FK容差`0.008→0.010m`；在授权前不手工闭爪、不重跑相同脚本。另有MoveIt持续报`Joint 'gripper' not found in model 'piper'`，但轨迹规划/执行接受；先记录为次要现象。

## 本轮最新实机状态（22:29:55–22:32:04）

直接运行原有`/home/johnwick/start_brain_robot_cube_real.sh`，没有另写/修改一键脚本。命令与完整记录见[`docs/PIper_PROGRESS.md`](docs/PIper_PROGRESS.md)最新条目；原始日志目录：`/home/johnwick/brain_robot_logs/real_full_20261010_stamped_tf/`。

结果：默认`AUTO_START=1`通过[1/7]–[7/7]，观测轨迹被接受并到达`OBSERVE_POSE_REACHED`；随后执行中心局部搜索、回中心及FULL_SEARCH，目标检测有效后进入ALIGN和`GRASP_READY`。不是一键脚本没启动或只运行了固定角度。

新断点明确为抓取执行器立即报`STATIC_TARGET_MODEL_UNAVAILABLE`：在GRASP_READY时，最后成功变换到`base_link`的活动目标已过期73.619秒（门限0.60秒）；原图像采样时刻TF查询在搜索运动期间反复future extrapolation。它在开爪和预抓取之前失败，因此本轮没有靠近/张爪/闭爪/下降/抬升/释放。脚本按原规则停输出、软件disarm，未发`DisableArm`、`ResetPiper`或归零；最后被动CAN位姿约`[-0.263980,0.971073,-0.741876,0,0.741457,0] rad`，夹爪反馈0.1021m。

源码已核实即时停止原因：点回调在原采样时间戳TF查询失败时保留相机系点、但不更新base_link缓存；GRASP_READY抓取入口仅检查这个缓存并立即失败，不等待TF或重试。因此不靠近不是夹爪反馈导致；最小修复需保留原时间戳语义和0.60秒新鲜度，仅为新鲜点的精确变换增加有界等待/重试。

运行执行器与规范源码一致（源SHA-256 `1f55f026…`，叠加层二进制`c6624512…`），真实YAML SHA-256 `907e3d06…`；启动脚本SHA-256 `e8c9f85c…`，本轮未改。任何修复应只让抓取工作线程短暂等待下一条能以**原消息时间戳**变换的目标帧，限定现有0.60秒；不恢复latest TF、不放宽任何门、不改运动轨迹/外参/夹爪。本修改需等待用户按其要求批准。此间无控制节点运行。

注意：本文件以下20:21、20:47等段落均是历史状态；若其表述与上方22:29–22:32实机结果冲突，以本页本轮最新实机状态和`docs/PIper_PROGRESS.md`首条记录为准。相机—指尖7cm/10.5cm是镜头安装外参的测量输入，不是额外施加在靠近轨迹上的偏移；不要为本轮TF时间戳错误删除它。

这份文件用于把 Windows Codex 会话中的 PiPER 调试上下文交接给虚拟机中的 Codex。虚拟机共享目录对应：`/mnt/hgfs/ub`。

最新代码更新：用户批准后，规范仓库 `grasp_lift_executor.cpp` 的活动 RGB-D 目标参考系变换和闭爪前夹持区校验均改为使用观测消息时间戳，不再以 latest TF 代替；添加了采样时间/TF时间及点坐标诊断。时间戳为零或无法查询时不做该次转换，闭爪核验不通过，不产生补偿运动。唯一实体配置当前 `depth_only_target_enabled=false`，备用 depth-only 回调未改。Humble 离线构建成功且该包6个测试目标全部通过，但代码尚未部署到运行工作区，也没有实机/一键流程验证；运动参数、相机外参和轨迹均未改变。用户报告的约5–8cm向下、沿臂当前朝向向后约8–10cm仅作为未标定现场观察记录。精确代码提交与 `git revert` 命令见 `docs/PIper_PROGRESS.md` 最新记录。

最新状态：20:21–20:22再次以`AUTO_START=1`运行未经修改的一键入口，顺利完成[7/7]、观测、中心优先搜索、ALIGN、GRASP_READY、79点预抓取、8点笛卡尔下降和一次落点纠偏。纠偏后模型tip误差7.3mm，但闭爪前`FreshFaceInsideJaws()`失败，状态`FRESH_TARGET_OUTSIDE_JAWS_NO_CLOSE`，没有闭爪/抬升/释放；检测器在接近期间报告target LOST。该错误文本共用多个分支，无法仅凭它断言目标3D坐标错或实体几何在两指外。原始CAN反馈显示J5在TARGET_ACQUIRED后仍处ALIGN期间由约`+0.478`升至`+0.734rad`；TARGET_ACQUIRED是进入ALIGN，不是对齐完成。YAML以J5作为竖直图像纠偏轴（sign +1），但没有逐帧图像误差/命令速度，无法认定符号错误。进入抓取器后实际J5在预抓取从`+0.738`降至`+0.290rad`，末段下降再降至`+0.2126rad`，规划末端目标z由0.208降至0.180m。日志及本轮关节/落点数值见[最新交接](docs/PIper_HANDOFF_20261010.md)和[进度首节](docs/PIper_PROGRESS.md)。50mm开口请求反馈仍为102.1mm。脚本清理后栈进程退出，未发ResetPiper/DisableArm，脚本报告保持使能。无源码/YAML/启动逻辑改动；任何代码修改须先向用户说明并获批准。下一步若获批准，仅加非行为性ALIGN与夹爪判定诊断，不放宽执行门。
20:47–20:50仅相机读取：相机当前RGB帧严重洋红偏色，未清晰看到紫色块/完整夹爪；深度中位244mm是相机距离，不是桌面高度。URDF有夹爪及手指碰撞网格，但arm目标链与配置末端是link6，使用0.1358m固定指尖偏移。用户报告实体指尖离桌面约90mm，与上轮7.3mm模型FK残差不能直接比较；需同时间对齐相机/桌面/关节/TCP。图片见`/home/johnwick/brain_robot_logs/camera_inspection_20261010_2048/`。本次只启动相机读帧，无机械臂运动；任何代码或运动参数改动仍须先获用户批准。
实体方向判断以用户观察为准：机械臂从弯曲变直就是上抬/远离，不能仅凭J5角度符号反推。代码链不是一条MoveGroup直达目标轨迹：TARGET_ACQUIRED后仍是图像误差驱动的ALIGN/MoveIt Servo；到GRASP_READY后Servo才停，抓取器随后执行MoveGroup预抓取和Cartesian下降。因此需先确定上抬发生在哪个状态段；对齐尚未完成时应查视觉ALIGN方向/误差，对齐后则查3D目标位姿、TF/TCP和MoveGroup路径。任何源码改动仍须先向用户说明并得到批准。

## 历史暂停交接（2026-10-10 18:24）

接手更新：用户随后要求恢复项目工作。已在隔离MoveIt验证保持对齐朝向的79点预抓取+9点完整末段，并将新模式接入原执行器（尚未实体执行）。当前入口/证据/新版本与剩余夹爪/FOV问题见 [最新接手更新](docs/PIper_HANDOFF_20261010.md) 首节；下段保留暂停时历史状态，不能覆盖最新进展。

用户要求暂停并由此前参与项目的老师傅接手。实机控制栈和本轮只读采集器已经退出；18:23:39确认六轴静止、保持使能，未回零或失能。接手先完整阅读 [本轮交接记录](docs/PIper_HANDOFF_20261010.md)。

历史settled_fix确实完成靠近/下降，失败于闭爪反馈46.2 mm；本轮当前部署版同一入口到达观测、SEARCH、ALIGN和GRASP_READY，但24个顶抓候选全部IK -31，退出于预抓取规划。当前夹爪反馈102.1 mm，两次运行证据必须分开。暂停后不自动续跑；本轮未部署任何新抓取策略。


## 1. 目标

唯一总目标是让 `~/start_brain_robot_cube_real.sh` 一键启动流程完整、稳定地运行到紫色方块视觉搜索和抓取阶段。

当前阶段优先级是先恢复 PiPER 六轴的正常关节位置控制，因为这是启动脚本继续进入观测姿态、视觉搜索和抓取的前置条件；但机械臂恢复只是总目标的第一阶段，不代表可以忽略 Astra、点云、MoveIt、TF、视觉检测或抓取逻辑。低层运动恢复后，应继续验证同一个启动脚本的全部阶段。

当前最直接的异常是：机械臂可以持续返回高速电机反馈，也可以成功使能，但通过 SDK 的 `MotionCtrl_2()` 和 `JointCtrl()` 发送 J2 小幅位置目标时，J2 基本不运动；视觉流程因此在零点复位或观测姿态准备阶段卡住。

## 2. 硬件与运行环境

- 主机：Windows，VS Code 通过 SSH 连接 Ubuntu 虚拟机。
- 虚拟机用户：`johnwick`。
- ROS：ROS 2 Humble。
- PiPER ROS 工作区：`~/piper_ros`。
- 视觉工作区：`~/piper_ws`。
- 共享目录：虚拟机 `/mnt/hgfs/ub`，Windows 侧为 `C:\ub`。
- USB-CAN：Geschwister Schneider CAN adapter，USB ID `1d50:606f`。
- Linux CAN 接口：`can0`。
- CAN 参数：bitrate `1000000`，sample-point `0.75`。
- 内核驱动：`gs_usb`。
- PiPER 固件版本：`S-V1.8-2`。
- 当前 Python SDK：`piper_sdk 0.6.2`，位置通常为 `/home/johnwick/.local/lib/python3.10/site-packages`。
- 当前 SDK 类：`C_PiperInterface_V2`。
- 原始旧仓库曾使用：`C_PiperInterface`，SDK 曾为 `piper_sdk 0.4.2`。

## 3. 当前代码状态

当前驱动源文件：

`~/piper_ros/src/piper/piper/piper_ctrl_single_node.py`

曾从供应商目录复制过：

`/mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py`

然后执行过：

```bash
cd ~/piper_ros
colcon build --symlink-install --packages-select piper
source ~/piper_ros/install/setup.bash
```

当前驱动使用 `C_PiperInterface_V2`。驱动通过 `/enable_srv` 接收 `piper_msgs/srv/Enable`，通过 `/joint_commands` 接收 `sensor_msgs/msg/JointState`，发布 `/joint_states` 和 `/arm_status`。

当前驱动关键逻辑：

- `enable_callback()` 和 `/enable_srv` 回调调用 `_enable_for_joint_control(50)`。
- `_enable_for_joint_control()` 最终调用 `EnablePiper()`，并设置普通 CAN 关节控制模式。
- 关节回调将弧度转换为约 `57324.840764` 的 0.001 度单位。
- 关节回调调用 `JointCtrl(joint1, ..., joint6)`。
- 驱动增加了高速反馈新鲜度检查；如果高速反馈丢失，会暂时抑制控制输出，超过约 2 秒退出。
- 反馈门控日志曾出现：
  - `can0 feedback lost; suppressing output for up to 2.0s`
  - `can0 feedback recovered after ...`
  - `can0 is loss`

## 4. 已确认的 CAN 状态

CAN 初始化成功时的典型状态：

```text
can state ERROR-ACTIVE
bitrate 1000000 sample-point 0.750
bus-errors 0
arbit-lost 0
error-warn 0
error-pass 0
bus-off 0
```

正常运行时 CAN RX 持续增长。例如 3 秒 RX 增量约 9000，25 秒采样中每 0.25 秒窗口约 744～776 帧，没有完全无帧窗口。

曾经出现过 `ERROR-PASSIVE`、大量 dropped/TX 异常，但通过：

```bash
sudo ip link set can0 down
sudo modprobe -r gs_usb
sudo modprobe gs_usb
sudo ip link set can0 up type can bitrate 1000000 sample-point 0.75
```

重新恢复为 `ERROR-ACTIVE`。USB-CAN 设备重新枚举后接口名仍为 `can0`。

## 5. 已确认的反馈帧

通过 SocketCAN 原始接收、`candump` 和 tcpdump 观察到持续反馈：

```text
0x251  J1 高速反馈
0x252  J2 高速反馈
0x253  J3 高速反馈
0x254  J4 高速反馈
0x255  J5 高速反馈
0x256  J6 高速反馈
0x261..0x266  其他电机反馈
0x2A1..0x2A8  标准状态/关节反馈
0x3A0..0x3A7  另一组状态反馈
```

典型高速反馈：

```text
J1 pos=0
J2 pos=2
J3 pos=-7
J4 pos=0
J5 pos=-8
J6 pos=0
```

`GetArmHighSpdInfoMsgs()` 的时间戳和频率正常，通常约 `200 Hz`。

但是 `GetArmJointMsgs()` 在一些运行中时间戳为 `0`、Hz 为 `0`。因此不能使用 `GetArmStatus()` 或 `GetArmJointMsgs()` 的零时间戳判断实时高速反馈是否正常；当前可靠的健康源是 `GetArmHighSpdInfoMsgs()`。

## 6. 已确认的使能行为

以下调用多次成功：

```python
p.EnablePiper()
```

输出通常为：

```text
Enable: True
六轴使能状态：[True, True, True, True, True, True]
```

ROS 服务也曾成功返回：

```text
piper_msgs.srv.Enable_Response(enable_response=True)
```

但“六轴已使能”不等于“位置控制目标已被控制器接受”。

## 7. 关节限位问题已经处理过

曾经查询到所有关节角度限位为 `-1`：

```text
J1 max_angle_limit=-1 min_angle_limit=-1
...
J6 max_angle_limit=-1 min_angle_limit=-1
```

随后执行过官方参数恢复逻辑（恢复默认关节限位、最大速度、最大加速度）。再次查询得到正常值：

```text
J1: -1500 .. 1500, max speed 300, max acc 500
J2:     0 .. 1800, max speed 300, max acc 500
J3: -1700 ..    0, max speed 300, max acc 500
J4: -1000 .. 1000, max speed 300, max acc 500
J5:  -700 ..  700, max speed 300, max acc 500
J6: -1800 .. 1800, max speed 300, max acc 500
```

随后曾有一次官方顺序测试成功让 J2 运动约 `2988` 个 0.001 度单位（约 2.99 度）。因此“限位一直为 -1”已经不是当前唯一解释，不能继续重复恢复限位作为主要排查方向。

## 8. 运动测试结果

多次执行过以下基本流程：

```python
p.ConnectPort()
time.sleep(2.0)
p.EnablePiper()
for _ in range(30):
    p.MotionCtrl_2(0x01, 0x01, 10, 0x00, 0, 0x01)
    p.JointCtrl(0, 500, 0, 0, 0, 0)
    time.sleep(0.02)
```

结果不稳定，但最近多次结果是：

```text
EnablePiper() -> True
六轴使能 -> 全 True
J2 目标 -> 500（0.001 度单位）
J2 实际位置保持约 2
J2 变化 -> 0
CAN TX 增量 -> 约 414 或约 134
CAN 状态 -> ERROR-ACTIVE，无 bus-off
```

另一组较早测试曾在默认参数恢复后让 J2 从接近 0 移动到约 2988，因此当前问题不是“SDK 永远不能运动”，而是控制路径/状态在不同运行时条件下不一致。

## 9. 控制反馈读取结果

调用：

```python
p.GetArmModeCtrl()
p.GetArmJointCtrl()
```

最近输出：

```text
模式控制反馈：
time stamp:0
Hz:0.0
ctrl_mode:1
move_mode:1
move_spd_rate_ctrl:50

关节控制反馈：
time stamp:0
Hz:0
Joint_1:0.000
Joint_2:0.000
...
```

这里的 `ctrl_mode=1`、`move_mode=1` 不能单独证明控制器确认了命令，因为时间戳仍为 0，极可能只是 SDK 本地缓存或默认值。需要检查 SDK 底层接收路径和真实反馈帧。

## 10. tcpdump 原始数据分析

抓包命令曾成功运行：

```bash
sudo -v
sudo -n timeout 8s tcpdump -i can0 -nn -e -XX \
  >/tmp/piper_wire_tcpdump.log 2>/dev/null &
```

抓包文件约 32023 行，说明 tcpdump 正常工作。原始数据示例：

```text
0x0010: a003 0000 0800 0000 0100 0100 0000 0000
0x0010: 5102 0000 0800 0000 0000 fff0 0000 0000
0x0010: 6102 0000 0800 0000 00e6 0025 1f40 0000
0x0010: 5202 0000 0800 0000 0000 0127 0000 0002
0x0010: 5302 0000 0800 0000 0000 fbb0 ffff fff9
```

这些可以解码为：

- `a0 03` -> `0x3A0`
- `51 02` -> `0x251`
- `52 02` -> `0x252`
- `53 02` -> `0x253`
- `61 02` -> `0x261`

在已提供的 tcpdump 样本中没有看到控制帧 ID 的对应字节：

- `51 01` -> `0x151`
- `55 01` -> `0x155`
- `56 01` -> `0x156`
- `57 01` -> `0x157`

注意：之前直接用 `grep -E '151|155|156|157'` 是错误的，因为会匹配时间戳或任意十六进制内容，不能代表 CAN ID。

还看到过：

- `0x473`
- `0x47C`
- `0x476`

这些与使能/参数响应相关，不是关节位置控制帧。

`/sys/class/net/can0/statistics/tx_packets` 会增加，例如 TX 增量 134 或 414。这只能证明 SDK 向 SocketCAN 提交了发送请求，不能单独证明控制帧已经被机械臂控制器接受。

## 11. 主从配置纠错

此前多次讨论并执行过：

```python
p.MasterSlaveConfig(0xFC, 0x00, 0x00, 0x00)
```

此前把 `0xFC` 简单解释为“从臂”是错误的。官方 V2 接口文档定义：

- `0xFA`：teaching input arm
- `0xFC`：motion output arm

官方双臂文档中通常把 teaching input 称为 master，把 motion output 称为 slave；但这只适用于双臂联动语境。

更重要的是，官方单臂示例并不需要调用 `MasterSlaveConfig()`，而是直接连接、使能、设置 CAN 关节模式、发送关节目标。

因此当前约束：

- 不要继续在 `0xFA` 和 `0xFC` 之间来回切换；
- 不要再执行 `ResetPiper`；
- 不要在没有新证据时修改持久主从/联动配置；
- 先确认控制帧实际是否进入 CAN 物理链路。

## 12. 已观察到的 ROS/视觉问题

视觉一键脚本：

```bash
bash ~/start_brain_robot_cube_real.sh
```

流程包含：CAN、PiPER 驱动、Astra RGB-D、紫色方块检测、MoveIt、Servo、真机保护适配器。

曾出现以下独立问题：

1. 驱动进程退出：

```text
can0 feedback lost; suppressing output for up to 2.0s
can0 is loss
```

2. 视觉适配器超时失能：

```text
PHYSICAL MOTION DISARMED: joint state timeout
```

3. TF 门控失败：

```text
MISSING_TF base_link<-link8
```

或：

```text
Lookup would require extrapolation into the future
```

4. MoveIt 自体过滤后的点云不可用：

```text
未收到 MoveIt 自体过滤后的点云；拒绝开始使用可能含有机械臂自体点的 Octomap。
```

5. Astra 原始深度图、深度内参正常，约 30 Hz；点云约 3.7 Hz，且可能受到 TF 门控影响。

这些视觉/TF 问题必须与 PiPER 低层运动问题分开处理。当前首先要让低层单臂 J2 小幅运动测试稳定成功，再恢复视觉流程。

## 13. 当前最可信的根因范围

已排除或明显降低优先级：

- USB-CAN 完全断开：不符合持续 200 Hz 反馈；
- CAN bitrate 完全错误：不符合稳定反馈；
- 所有关节限位仍为 -1：已恢复并验证正常；
- 六轴完全没有使能：`EnablePiper()` 和六轴状态成功；
- 单纯机械臂完全失能：手动控制时关节曾可保持，反馈正常；
- ROS `/joint_commands` 完全没有发布：此前能看到约 50 Hz 命令和 TX 增量。

仍需确认：

1. `MotionCtrl_2()` 和 `JointCtrl()` 在 SDK 0.6.2 中的底层发送函数是否真的调用了 CAN bus send；
2. 这两个调用返回的 `SendCanMessage` 实际结果是什么；
3. SDK 是否因为当前接口/角色/固件状态，把运动命令发到了不同 ID 或被内部条件抑制；
4. tcpdump 是否能捕获真正的 TX 控制帧，还是只看到了 RX 反馈帧；
5. 固件 S-V1.8-2 与 SDK 0.6.2 的运动控制协议是否完全兼容；
6. 是否有 SDK 初始化参数、CAN auto-init、过滤器或线程状态导致反馈正常但控制发送异常。

## 14. 推荐下一步

不要再改主从配置。先做代码级、只发送一次小目标的诊断：

1. 在当前安装的 `piper_sdk 0.6.2` 中定位 `MotionCtrl_2`、`JointCtrl` 的实现；
2. 打印它们内部 `SendCanMessage` 的返回值和实际 CAN ID；
3. 在 SDK 发送函数附近增加临时日志，确认是否经过发送调用；
4. 同时用 tcpdump 原始字节检查 `51 01`、`55 01`、`56 01`、`57 01`；
5. 只有在确认控制帧已经实际发出后，才继续分析固件是否接受；
6. 低层测试稳定后，再启动 `piper_single_ctrl`、视觉适配器和 MoveIt。

## 15. 运行时安全要求

- 发送运动命令前，确认机械臂周围无障碍物和人员。
- 所有测试优先使用 J2 小于 0.5 度的目标。
- 不要同时运行多个 `piper_single_ctrl`、视觉适配器或 Servo 控制器。
- 启动新控制器前检查：

```bash
pgrep -af 'piper_single_ctrl|piper_jog_adapter|visual_search_controller|grasp_lift_executor|move_group|servo_node'
```

- CAN 异常后可先停止 ROS 控制器，再重载 `gs_usb` 和重新配置 `can0`。
- 不要把 `GetArmStatus()` 时间戳为 0 的缓存当作实时运动确认。

## 16. 官方参考

- PiPER V2 接口文档：
  https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/V2/INTERFACE_V2.MD
- PiPER 双臂配置说明：
  https://github.com/agilexrobotics/piper_sdk/blob/master/asserts/double_piper.MD
- PiPER SDK 仓库：
  https://github.com/agilexrobotics/piper_sdk

## 17. 给下一位 Codex 的启动提示

请先完整读取本文件，再检查虚拟机中当前代码、SDK 安装位置和运行进程。不要假设主从配置就是根因，也不要直接执行 `MasterSlaveConfig(0xFA)`、`MasterSlaveConfig(0xFC)`、`ResetPiper` 或固件升级/降级。先用源码和返回值证明 `MotionCtrl_2()`、`JointCtrl()` 的真实发送路径，再继续处理。

## 18. 任务执行授权与 Git 历史

用户的唯一总目标是让 `~/start_brain_robot_cube_real.sh` 一键流程完整运行到紫色方块搜索和抓取阶段。用户会在真实机械臂旁边看护，并能够随时断电/急停；因此可以在完成安全检查后，由 Codex 自主执行必要的终端诊断、编译、启动/停止 ROS 节点和小幅真机验证，不要每一步都停下来要求用户重复确认。

真机运动前仍必须：

- 说明即将发送的目标、单位、预计动作和停止条件；
- 读取当前高速反馈并确认时间戳新鲜、六轴状态和限位正常；
- 对未测试关节保持当前实际位置，不要把其他关节随意设为绝对零位；
- 发现 CAN 反馈丢失、位置异常、状态突变或控制器退出时立即停止发送并报告。

除当前工作树外，应主动检查 Git 资料：

- `~/piper_ros/.git`
- `~/piper_ws/.git`（如果存在）
- `/mnt/hgfs/ub/.git`（规范 Git 根目录；Windows 对应 `C:\ub\.git`）
- `git log --all --decorate --oneline`
- `git reflog --all`
- 供应商代码目录 `vendor/piper_ros`

重点寻找曾经成功让 J2 运动、成功启动 `start_brain_robot_cube_real.sh`、恢复关节限位和修复驱动反馈门控的提交、分支、补丁或脚本。先只读比较工作树、历史提交和当前安装文件，再决定是否应用修改。不要覆盖用户现有未提交改动；如果需要修改，先保存当前 diff，并做最小可回滚修改。

如果仓库配置了远程 GitHub remote，可以读取远程历史和已验证代码；GitHub 不是本地终端日志的替代品，仍需以虚拟机当前实际安装的代码、SDK、固件反馈和 CAN 抓包为最终依据。

## 19. 已审查过的关键参数差异

下一位 Codex 必须逐项核对这些参数，不能只看类名或单个 API 是否返回成功：

### Python SDK 与接口类

- 曾经能运行的旧组合：`piper_sdk 0.4.2` + `C_PiperInterface`。
- 当前安装组合：`piper_sdk 0.6.2` + `C_PiperInterface_V2`。
- 当前运行时 SDK 路径：`/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk`。
- 必须确认 ROS 驱动实际加载的 SDK 路径，而不是只检查 shell 中的 Python。
- 必须确认 `ros2 run piper piper_single_ctrl` 使用的是重新编译后的 `install/piper`，不是旧进程或旧 overlay。

### SDK 初始化参数

已使用或测试过的参数组合包括：

```python
C_PiperInterface_V2(
    can_name="can0",
    judge_flag=False,
    can_auto_init=True,
)
```

曾测试过的附加参数：

```python
start_sdk_joint_limit=False
start_sdk_gripper_limit=False
```

`can_auto_init=False` 时必须先调用 `CreateCanBus`，否则 `ConnectPort()` 会报：

```text
Interface 'can_auto_init' is False and '__arm_can' is None!!
```

诊断过程中曾观察到 SDK/接口使用 `local_loopback=False`。因此 `candump` 或 tcpdump 看不到同机 TX 回显，不能直接证明 SDK 没有发送控制帧；必须结合内核 TX 计数、tcpdump 原始字节、发送函数返回值和实际反馈综合判断。

### ROS 驱动启动参数

当前单臂驱动常用启动参数：

```text
-p can_port:=can0
-p auto_enable:=false
-p gripper_exist:=true
-r joint_states_single:=/joint_states
-r joint_ctrl_single:=/joint_commands
```

不能把 `auto_enable:=false` 与“机械臂未使能”混为一谈；这只表示由服务/外部流程触发使能。必须确认 `/enable_srv` 调用成功后驱动内部 `__enable_flag` 和六轴硬件状态都为真。

### MotionCtrl_2 参数

当前官方普通关节位置控制测试使用：

```python
p.MotionCtrl_2(
    ctrl_mode=0x01,
    move_mode=0x01,
    move_spd_rate_ctrl=10或50,
    is_mit_mode=0x00,
    residence_time=0,
    installation_pos=0x01,
)
```

其中：

- `ctrl_mode=0x01`：CAN 控制；
- `move_mode=0x01`：关节位置模式；
- `is_mit_mode=0x00`：普通位置控制，不是 MIT 模式；
- 速度比例曾分别测试过 `10`、`20`、`50`、`100`；
- 不能把 `0xAD` 或 `0xFF` 误当成普通位置模式参数。

### JointCtrl 单位与目标构造

`JointCtrl()` 的关节单位是 `0.001°`，不是弧度，也不是 `0.001 rad`。例如：

```text
500 = 0.5°
250 = 0.25°
3000 = 3.0°
```

真实测试时如果只验证 J2，必须读取当前高速反馈，并构造：

```text
J1=current_J1
J2=current_J2+250
J3=current_J3
J4=current_J4
J5=current_J5
J6=current_J6
```

不能因为机械臂软件零点看起来接近零，就把其他轴全部发送为绝对零位。

### 关节限位/速度/加速度参数

曾出现查询结果 `max_angle_limit=-1`、`min_angle_limit=-1`。之后已通过官方参数恢复逻辑恢复出正常限位和速度/加速度值。下一位 Codex 必须先读取当前值再判断，不要假设它们又恢复为 `-1`，也不要重复写参数作为默认修复动作。

### 反馈参数与健康判断

- 高速反馈 ID：`0x251..0x256`，频率约 `200 Hz`，目前是最可靠的实时健康源。
- `GetArmJointMsgs()` 在部分运行中时间戳为 `0`、Hz 为 `0`；不能把它当作有效实时反馈。
- `GetArmStatus()`、`GetArmModeCtrl()`、`GetArmJointCtrl()` 时间戳为 `0` 时，返回结构中的数值可能只是缓存/默认值，不能作为控制器已确认的证据。
- 驱动的反馈门控使用高速反馈时间戳；检查它是否读取了真正会更新的字段，避免把未更新缓存误判为新鲜反馈。

### CAN 接口参数

```text
interface: can0
bitrate: 1000000
sample-point: 0.75
driver: gs_usb
```

曾经发生过接口重载后 `can0` 消失、ERROR-PASSIVE、TX dropped 增长等情况。遇到这些现象，应先停止 ROS 控制器并恢复 CAN 接口，再解释上层运动结果。

## 20. 额外的历史陷阱与成功条件

### 曾经成功过的控制顺序

历史上能让 J2 运动的可靠顺序是：`ConnectPort`，等待真实高速反馈，`EnablePiper/EnableArm(7)`，确认六轴使能，再发送 `MotionCtrl_2(0x01, 0x01, ...)` 和持续的 `JointCtrl`。不要在确认使能前发送位置目标，也不要把 SDK 方法返回成功当成机械臂已经运动。

### 必须只有一个低层 PiPER 驱动

过去曾同时出现多个 `piper_single_ctrl`、多个 `cube_detector` 和多个视觉启动进程。多个驱动会造成 CAN 竞争、错误的 `/joint_states` 发布者和视觉适配器订阅到旧状态。每轮测试前必须检查并确保只有一个低层驱动和一个视觉控制栈；不能只杀掉 ros2 launch 父进程而留下子节点。

### 驱动退出日志的含义

```text
can0 is loss
ROSInterruptException: rclpy.shutdown() has been called
RuntimeError: Context must be initialized before it can be shutdown
```

后两个异常是当前退出清理路径的缺陷，真正要先处理的是前面的 CAN 反馈丢失。看到 `Enable status: True` 不能忽略后续反馈门控退出。

### `/joint_states` 与视觉适配器是两条独立链路

曾出现高速 CAN 反馈约 200 Hz，但 `/joint_states` 发布者为 0，或视觉适配器报告 `PHYSICAL MOTION DISARMED: joint state timeout`。必须分别验证高速 SDK 反馈、驱动是否发布 `/joint_states`、消息时间戳是否更新、适配器是否订阅正确话题，以及唯一低层驱动是否接收到视觉命令。CAN 正常不等于 ROS 关节状态正常，命令话题有 50 Hz 也不等于机械臂执行了运动。

### 启动脚本的清理和复用逻辑

`start_brain_robot_cube_real.sh` 会初始化/复用 CAN、启动或复用 Astra、检测器、MoveIt、Servo 和视觉适配器，并在失败时停止本轮进程，但可能留下上一轮子节点。因此脚本重启前必须检查进程树、话题发布者数量和服务存在性，避免第二套控制器竞争。

### Astra、点云与 TF 的实际现象

已验证 RGB/深度图约 30 Hz，深度内参约 28～30 Hz，原始点云约 3.7 Hz；点云 TF 门控曾出现 `MISSING_TF base_link<-link8` 和 `Lookup would require extrapolation into the future`。即使 `tf2_echo base_link link8` 在当前时间能查到变换，带历史 cloud stamp 的 TF 查找仍可能失败。必须同时核对 cloud/TF 时间戳、`/clock`、`use_sim_time`、frame_id、QoS 和旧的 `pointcloud_tf_gate` 实例。

### Fast DDS 共享内存错误

```text
RTPS_TRANSPORT_SHM Error
Failed init_port fastrtps_port....: open_and_lock_file failed
```

这可能来自旧进程、共享内存锁文件或多个 ROS 环境残留，不能直接当作 PiPER 或相机硬件故障。判断服务不可用前要先确认旧 ROS 进程和通信资源状态。

### 启动脚本最终验收标准

总目标只有在以下条件同时满足时才算完成：脚本不因 `/enable_srv` 超时退出；只有一个 PiPER 驱动和一个视觉控制栈；`/joint_states` 持续更新；六轴能从软件零点运动到观测姿态；Astra RGB、深度、点云和 TF gate 达到脚本要求；紫色方块检测持续有效；视觉搜索能离开 PREPARE；GRASP_READY 后抓取、抬升和释放动作实际完成；反馈丢失或目标丢失时会安全停止；最终保存驱动、视觉和关键 ROS 话题日志。

## 21. 磁盘空间、Git 留痕与任务恢复要求

### 磁盘空间不足时的固定处理

每次启动脚本前和长时间测试前检查根分区使用率。如果发现磁盘空间紧张、根分区使用率达到项目脚本的阈值（通常为 85%），或者 ROS 日志/构建失败明确提示空间不足，只执行项目已有的清理脚本：

```bash
~/clean_disk_space.sh
```

不要临时编写 `rm -rf` 清理命令，不要删除整个工作区、`.git`、源码、SDK、构建缓存中尚未确认的内容，也不要把用户日志直接上传到远程仓库。清理后重新检查 `df -h`，并把清理前后空间、脚本返回码和影响记录到进度文件/Git 提交中。

### 每次修改必须记录到 Git

每次修改代码、配置、启动脚本、参数文件或诊断脚本前：

1. 在相关仓库执行 `git status --short` 和 `git diff`；
2. 保存或明确区分用户原有未提交修改；
3. 只提交本次任务产生的最小修改；
4. 使用能说明原因和验证结果的提交信息；
5. 记录实际运行的测试、返回值和仍存在的风险。

不要提交密钥、密码、个人隐私、巨大日志、构建产物、临时抓包或模型文件。若诊断需要保存输出，应放在明确的日志目录并在 Git 中只提交摘要、路径、时间和结论。

### 每轮提交后的 GitHub 同步规则（2026-10-11 补充）

每轮完成后，检查待推送内容不包含敏感信息或大文件，再推送；推送失败必须记录，不能把本地提交称为已同步。详细执行规则以 `CODEX_TASK_PROMPT.md` 第 11 节为准：项目 `origin` 指向 `https://github.com/bcwsyn/brain-robot-arm.git`，供应商仓库只读；审查必须覆盖全部未推送历史，不只是最后一次提交或净 diff。禁止强制推送、自动改写历史、混入用户已有修改或未跟踪包；仅在普通推送成功且远程目标分支已验证包含本轮提交后，才能报告已同步。

如果历史审查未完成，或推送遇到认证、网络、分叉或验证失败，必须把同步阻断、脱敏证据和下一步写入 `docs/PIper_PROGRESS.md` 并提交，明确报告“仅本地提交，未同步 GitHub”。同步阻断不替代机械臂任务进度，不重复无关实机检查。

### 每次阻断也必须记录到 Git

遇到服务等待超时、CAN 反馈丢失、TF gate 拒绝、点云不足、硬件风险、权限不足或无法继续的情况，不能只在聊天中报告。应在工作区维护一个进度文件，例如：

```text
docs/PIper_PROGRESS.md
```

每次阻断至少记录：时间、当前 Git commit、执行的命令/实验、观测结果、已排除的原因、阻断原因、下一步和是否需要用户确认。阻断记录也要提交到对应 Git 仓库，除非仓库不存在或当前操作本身被 Git 阻断；此时要在可写的共享交接文件中记录。

### 每次重新拾起任务必须先读 Git 进度

Codex 每次新建会话、重启 VS Code、重启虚拟机或从阻断状态恢复时，必须先执行并阅读：

```bash
git status --short
git log --oneline --decorate --all -n 20
git reflog --all -n 20
```

然后读取仓库中的 `docs/PIper_PROGRESS.md`（如果存在）、`CODEX_HANDOFF.md`、最近相关提交的 diff 和最新日志，再决定下一步。不能只依赖聊天上下文，也不能重复已经完成或已经证明无效的实验。

### 进度提交内容

每个阶段结束时，提交应至少包含以下一种明确结果：

- 已验证的代码/配置修复；
- 可复现的诊断脚本；
- 真实测试结果摘要；
- 明确的阻断记录和下一步；
- 启动脚本阶段通过/失败的证据。

如果一次真机测试没有修改源码，也应提交测试摘要或进度记录，避免下一次恢复任务时丢失实验结果。

## 22. 唯一 Git 仓库与跨账号恢复协议

本任务只使用一个规范 Git 仓库作为长期上下文和进度的唯一事实来源：

```text
Windows: C:\ub
虚拟机: /mnt/hgfs/ub
Git 根目录: /mnt/hgfs/ub/.git
```

当前已确认 `C:\ub` 是 Git 仓库；`C:\ub\brain_robot_arm` 当前不是独立 Git 仓库，不能把它当成第二个进度仓库。`/home/johnwick/piper_ros`、`/home/johnwick/piper_ws` 是否是 Git 仓库必须单独检查，但它们不能替代规范仓库。

所有长期上下文必须保存到规范仓库中的可追踪文件，不要只放在聊天窗口、`/home/johnwick/CODEX_HANDOFF.md` 副本或未提交的本地日志中。至少维护：

```text
CODEX_HANDOFF.md                 # 稳定背景、约束、已验证事实
docs/PIper_PROGRESS.md           # 按时间记录每次实验、修改、阻断和下一步
docs/PIper_DECISIONS.md          # 已确认的架构/参数决定及证据
```

如果规范仓库中不存在 `docs/PIper_PROGRESS.md` 或 `docs/PIper_DECISIONS.md`，首次恢复任务时应创建并提交；不得只在 `/home/johnwick` 创建另一份孤立文件。

### 每次新账号/新会话的固定恢复顺序

无论是否切换 ChatGPT/Codex 账号、VS Code 窗口、模型或虚拟机，Codex 必须先在规范仓库执行：

```bash
cd /mnt/hgfs/ub
git status --short
git log --oneline --decorate --all -n 30
git reflog --all -n 20
git show --stat --oneline HEAD
sed -n '1,240p' CODEX_HANDOFF.md
sed -n '1,240p' docs/PIper_PROGRESS.md 2>/dev/null || true
sed -n '1,240p' docs/PIper_DECISIONS.md 2>/dev/null || true
```

然后再检查 `/home/johnwick` 中的运行时副本是否与规范仓库相关文件一致。若不一致，先记录差异并判断哪个是当前实际生效文件，不能静默覆盖。

### 每次工作循环的固定顺序

```text
读取 Git 进度
→ 检查当前工作树和运行时路径
→ 计划一个最小可验证动作
→ 执行诊断/修改/测试
→ 把结果、阻断和下一步写入 docs/PIper_PROGRESS.md
→ 把代码/配置/文档和进度一起提交到规范仓库
→ 报告 commit ID、测试结果和剩余风险
```

切换账号后不依赖聊天历史；只依赖规范仓库中已经提交的文件和 Git 历史。远程 GitHub 如果存在，只作为同步/审查来源；在提交成功前，不能把只存在于 GitHub 工作区、聊天内容或虚拟机未提交目录中的信息当作已保存进度。

## 23. 无 CAN RX 时的硬件优先检查

如果启动脚本停在 `[1/7]`，并同时出现“sudo 凭据缓存失效”“can0 没有新 RX”“SDK 没有高速反馈”，必须先停止所有运动和 ROS 控制器，把问题分成权限、USB-CAN、CAN 接口和机械臂物理链路四层检查。不能直接重启视觉流程，也不能发送运动命令。

先刷新 sudo 凭据，但不要把 sudo 错误误判为机械臂故障：

```bash
sudo -v
```

然后只读检查：

```bash
lsusb | grep -Ei '1d50:606f|OpenMoko|CAN' || true
lsmod | grep gs_usb || true
ip -brief link show can0 || true
ip -details -statistics link show can0 || true
```

解释顺序：

- `lsusb` 看不到 `1d50:606f`：优先检查 USB-CAN 是否插好、VMware USB 设备是否仍连接到虚拟机、USB 线和适配器指示灯；
- `lsusb` 能看到但没有 `can0`：检查 `gs_usb`/`can_dev` 模块和接口枚举；
- `can0` 存在但为 DOWN：只在确认 USB-CAN 已识别后配置 1 Mbps、sample-point 0.75；
- `can0` 为 UP 但 3～5 秒 RX 增量为 0：检查 PiPER 主电源、机械臂控制器是否启动、CAN_H/CAN_L 是否接反/松动、USB-CAN 到机械臂的连接、终端电阻和 CAN bitrate；
- `can0` RX 恢复后才允许启动 SDK 或 ROS 驱动；
- RX 恢复但 SDK 无高速反馈：再检查 SDK 接口、进程竞争和反馈 ID，不要先改主从配置。

RX 只读测试：

```bash
RX1=$(< /sys/class/net/can0/statistics/rx_packets)
timeout 5s candump -L can0
RX2=$(< /sys/class/net/can0/statistics/rx_packets)
echo "RX 增量：$((RX2-RX1))"
```

如果机械臂主电源已确认开启、USB-CAN 已识别、can0 已配置但 RX 仍为 0，必须让用户检查实际 CAN 线缆、供电和适配器连接，必要时在机械臂安全静止状态下重新插拔/重新上电。未恢复 RX 之前，不得运行 `EnablePiper`、`MotionCtrl_2`、`JointCtrl` 或完整视觉启动脚本。
