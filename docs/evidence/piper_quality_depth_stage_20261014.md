# 2026-10-14：质量驱动末段切换实现与离线验证

## 授权与范围

用户已确认原检测器/原执行器局部实现“合格同帧RGB-D → 最后可靠同一世界模型 → 局部深度质量下降时原同步转向靠近/RGB纠偏”。不将固定20/23cm作为必达前提，不改安装TF/TCP、最终落点规则、限位/碰撞、adapter、新鲜六轴反馈或最终夹持/闭爪判断。不刷写、不ResetPiper、不MasterSlaveConfig、不恢复腕部Octomap。唯一入口仍 `/home/johnwick/start_brain_robot_cube_real.sh`，本轮未改该脚本。

## 实现事实

- 原 `cup_detector_node.cpp` 新增 `/brain_robot_vision/rgbd_observation`：使用已安装的标准 `diagnostic_msgs/DiagnosticArray`，每个RGB戳只发布一次最终观测，合格状态、三维点、尺寸和质量来自同一处理回调，失败/提前返回也发布不合格记录。原SEARCH话题和检测门限不变。
- 质量包含样本数、支撑覆盖率、支撑包围面积比例、MAD；覆盖率分母为完整原始RGB轮廓，不是注册后残存的深度条带。本相机当前采用软件D→C注册；真实帧回放验证针对这条实际路径，不声称已经验证其他相机/注册模式。
- 原 `grasp_lift_executor.cpp` 只接受与当前RGB戳匹配的合格原子记录来更新粗靠近测量，不拼接相邻帧无戳Bool和raw point。缓存最近三帧经原身份/尺寸/精确图像时刻TF/真实反馈核验的世界坐标模型。
- 当前观测不合格，或覆盖率/支撑面积低于最近三帧中值的65%，请求深度→模型/RGB阶段切换；这是切换条件，不是新运动终止门。合格记录短时不可用也尝试已有可靠模型；没有可靠历史、新鲜RGB或真实反馈时不盲动。
- 冻结最近一次真实合格模型，保留原测量时间戳/尺寸/相机位置；用当前原始RGB与精确图像时刻TF核对同一物体。相机运动后的预测和纠偏仍使用真实六轴反馈，不把旧模型伪装成新深度，不清掉旧测量以来的实际相机位移。
- 深度始终良好时，由现有指尖偏置和预抓取几何触发末段，不强制固定相机距离。后续仍是198f2a5已批准的同步转向靠近与原RGB微步，保持完整MoveIt路径/原关节行程小步前缀/反馈及最终夹持判定。

## 验证（不等于实体抓取成功）

构建目录 `/tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place`：

```bash
cmake --build /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place \
  --target cup_detector_node grasp_lift_executor near_depth_executor_test rgbd_observation_test -j2
```

最终build rc0；37项实际执行器方法、5项原子观测/schema/相对质量、15项near-depth、14项抓取几何、10项视觉反馈、3项wiring合计84通过。实际方法覆盖：相邻Bool不能覆盖不合格同戳观测；已qualified残余条带不能重锁世界点；在30cm也能按质量冻结；冻结仍须RGB/六轴完整；保持老种子时间与5mm真实相机位移；没有原子记录不能从raw Bool建立新历史。

测试记录 `/home/johnwick/brain_robot_logs/view_guard_20261013/quality_stage_{executor,observation,policy,geometry,visual}_tests.txt`；3项wiring另已运行通过。第一次构建在CMake自动再生成后顶层Make尚未识别新增测试目标，rc2；重新调用已生成目标后rc0，未改/弱化测试。新增历史检查测试暴露helper先返回导致无效历史被接受，已调整判断顺序并通过。

隔离 `ROS_DOMAIN_ID=78` 回放仅启动候选检测器、发布归档传感器帧；无SDK、MoveIt、控制话题或运动。生产检测器用原配置重放实际原始RGB/native-depth与CameraInfo：

- 好帧：RGB1791906280183270225 / nativeD1791906280174165061；12条记录中稳定后的10条合格，1811支撑点，coverage0.393019727/span0.820512821，测227mm。
- 空洞帧：RGB1791906282184497764 / nativeD1791906282176095564；9条记录均被相对质量判定要求切换，36点、coverage0.013004791/span0.011926058，残余测255mm。原稳定/尺寸判断仍可能qualified，不能单靠该Bool把残余背景当方块。
- `quality_stage_replay_verified/report.json`：rc0，`hole_frames_request_quality_handoff=true`，`hardware_motion_sent=false`。仅验证检测器质量输出与切换条件；世界点不被污染/位移补偿由上述实际方法测试验证，尚不是实体链验收。
- 前两次回放分析器误将Python DiagnosticStatus.level的bytes同整数0比较，产生假失败；已改与DiagnosticStatus.OK比较，原失败记录保留，未改变生产阈值。

## 候选SHA-256与部署断点

| 文件 | SHA-256 |
| --- | --- |
| 候选grasp_lift_executor | 27f8b25ba1bb7f3113937d54b0cfd738941475b866a671c2bba3b53633db2393 |
| 候选cup_detector_node | 27f90593ae0b53ca646d5af2fb6050b5dcc61d0aca130f814ec31ba3d944a6fb |
| 规范executor.cpp | 824259e9a82d1117d10a03305501babc562f17ec7a7f3a59039e5787f939a11a |
| 规范detector.cpp | 5fcdbc39d3a34b867cdd0eca6fa4e48cdcf8134598a6a0f8bca89b25a1dca06d |
| 新rgbd_observation.hpp | 957c7300e0205744867c47727e1be4a2f1e4c500b8970ec9177d7fd44e9539c9 |
| 未修改唯一启动脚本 | 87039bdbac1323daacb7e599f3cae884aebab3b9282a519b4ef1a6a33124c2b0 |

本节写入时实际树仍198f2a5：executor fd0d086d1496dfe02d6c45b840ef430093eb1a444a5f335479a511bed914351c；detector4d5e9ac12e10a801528a3485425a9eb55b6201050f230d2b467cb83b53bd5649。两个实际install executable均软链接到实际build。候选已构建/离线核验，但未部署、未新实体运动。

## 下一步与未验证项

先限定文件提交，保留用户既有wiring注释/vendor/reference/PDF/deb改动。确认无控制栈后备份原双binary并同步实际源码与双候选；SHA核验后只做一次新鲜SDK/六轴使能静止与CAN RX检查，正常链路复用。原AUTO1/视觉而非depth-only/不停在目标获取运行到质量切换→同步末段→实际靠近。采集原RGB/nativeD、观测质量、图像戳、TF/反馈和执行器诊断。

本步实体验收为不再因局部深度空洞停在粗靠近且实际进入同步末段；然后才核对最终两指实际夹持区、闭爪/抬升、原释放/安全返回后失能。若还有偏差，以同帧视觉与真实FK定位；本授权不包含自动修改安装TF/TCP或最终落点。历史Git远端待推送审查未完成，只作本地提交，不无审查推送历史。
