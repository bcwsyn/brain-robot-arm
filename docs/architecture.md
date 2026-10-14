# Piper Project Architecture

## 2026-10-14: large gripper and learned cup-perception increment

The user confirmed the official 100 mm large-gripper variant. Default generic/Gazebo URDF, MoveIt open state and executor bounds now agree on 50 mm one-sided travel. This supersedes the earlier Stage 3 small-gripper restriction for the new version only; historical trials retain their original models. Only stroke was verified against the official SDK. Existing meshes/PID/gravity compensation remain simulation assumptions.

Generate hollow stepped-cup truth separately from perception. Estimate local outer diameter from a learned instance mask and calibrated RGB-D; do not supply specimen diameter or Gazebo object pose to the fit. Filter visible inner walls using camera geometry, reject unobservable fits, and calculate opening from width/uncertainty/clearance rather than a fixed cup width.

The trained single-class YOLO cup ID is 0, whereas the original COCO cup ID is 41. Preserve both training revisions and annotation failures. Group dataset splits before augmentation, and use a fresh frozen-model final test. Synthetic metrics do not establish real-camera performance.

Expose the new perception through separate read-only cup topics with image-time TF and explicit validity. The legacy executor continues known-specimen position preload; the new opening/contact-force policy is tested offline but does not yet own Gazebo jaw commands. Integration must establish one jaw-command owner and retain physical retention/release/stop checks. Gazebo contact normal force is in N; SDK effort is torque in N·m and requires separate calibration.

Publish the increment in a new `simulation_cup/` directory, preserving existing repository code. [Stage report](第四步_水杯训练与自适应夹持基础验证.md) records implemented and pending functionality.

## Overall Goal

Develop a Piper robotic arm system with separate simulation and real-robot workspaces.

## Simulation

Planned scope:
- Robot description and simulation model
- ROS 2 interfaces
- Visualization
- Simulation controllers
- Offline testing

## Real Robot

Planned scope:
- Hardware communication
- Robot driver integration
- Robot control interfaces
- Diagnostics
- Supervised hardware validation

## Shared Components

Shared runtime code has not yet been defined.

If a component needs to be used by both workspaces, document the design decision before introducing a shared package or synchronizing source code.

## 2026-10-11: brain-robot-arm import decision

The user authorized importing `https://github.com/bcwsyn/brain-robot-arm` into both workspaces. Pin the import to commit `6ebd0c53ca830ac4071b8e64fcc1954dbf5a8cf1`.

- Keep an exact tracked-file source archive and a source-to-destination checksum manifest under `shared/upstream/brain_robot_arm/`. This is reference material, not a ROS overlay or shared runtime package.
- Import reusable description, message, MoveIt, perception and controller sources as independent copies into each workspace. Do not use cross-workspace symlinks or source the other workspace's install directory. Record all import adaptations in the manifest.
- Put Gazebo/MuJoCo packages, scenes and simulation entry points in `simulation/`. Exclude CAN/USB drivers and physical-arm adapters; reject physical backend selection in the simulation controller/executor copies.
- Put Piper and camera drivers, physical adapter, real profiles and real launch files in `real_robot/`. Disable imported default motor/motion/grasp permissions and recorded observation-calibration claims. Remove Gazebo build requirements from the real application package.
- Preserve old machine-specific installation, maintenance and control scripts as non-default legacy reference tools; do not execute them during import.
- Preserve historical documents/evidence under `docs/imports/brain_robot_arm/`, clearly distinguishing them from validation on this machine. Do not activate imported agent configuration or inherit old hardware authorizations.
- Keep package names stable within each workspace. Because the workspaces contain overlapping package names, build and source only one workspace at a time. Future synchronization requires an explicit reviewed change with checks in the affected workspace.

This decision implements workspace separation and provenance only. Runtime compatibility, camera calibration, physical grasping and the complete research goals remain to be validated.

## 2026-10-12: simulation pick-and-place control ownership

Use one explicit handoff between the visual controller and the existing grasp executor. The visual FSM owns Servo during observation/search/alignment. The executor calls `/visual_search_controller/claim_grasp_control`, confirms Servo stop, and waits for fresh, stable measured joint positions before planning/executing. During executor ownership, visual jog, reacquisition and a new start are suppressed; stop, emergency stop and feedback-loss checks remain active. Returning control requires a new start request; it does not automatically restart Servo.

Keep the target object in the MoveIt world scene. Permit only the gripper assembly's target contact, attach during transport, restore the released object and original allowed-collision matrix afterward. Recompute each executed Cartesian segment from measured state, retaining MoveIt's existing start-state tolerance. The default visual profiles use direct alignment followed by finite side-grasp candidates instead of the old cup leveling sequence.

`flow_demo=true` is an explicit nonphysical demonstration mode: object gravity is disabled, the pose plugin drives motion, and Gazebo object contact forces are disabled to avoid fighting forced poses. It preserves MoveIt collision geometry and a geometric capture gate. A future physical mode must remove pose following, enable gravity/contact, and validate retention; merely setting `flow_demo=false` does not implement that mode.

Separate scene readiness from executor readiness. Use `/brain_robot_{ball_pick,pick_place}/scene_ready` for generated scenes and `/brain_robot_grasp/scene_ready` for executor preparation. Completion means release, safe retreat and return to the named `zero` posture, followed by `COMPLETE`.

Use a Gazebo-only persistent controller bootstrap with a DDS discovery window, process-local asynchronous Fast DDS publication, and local transport settings in the bounded validator. Keep original imported provenance hashes immutable; record subsequent source changes and test evidence separately under `simulation/validation/step1/`.

## 2026-10-12: one-terminal visual simulation sessions

Expose separate ball and cylinder shell entry points backed by `simulation/scripts/visual_sim_console.py`. Load only the simulation overlay automatically; use ROS domain 83, localhost-only discovery, a dedicated Gazebo master port 11483, and a shared exclusive session lock. Refuse an occupied session instead of terminating foreign processes.

The console orchestrates existing launch files and calls only visual start/stop and scene reset services. It does not compute grasp coordinates or publish joint trajectories; the existing visual FSM/executor ownership protocol remains responsible for motion. Require an explicit S key for each run. Accept normal reset only while idle or after full completion; wait for the new scene readiness, actual object origin and measured zero joints before accepting another run. After an interrupted/faulted run, R replaces the owned simulation stack to clear attachment/follow state.

Own Gazebo server, GUI, MoveIt, RViz, scene, detector and task process groups. Detect child exit, bound startup/service/reset/task waits, restore terminal settings on exit, and stop/reap only recorded groups. Keep the parent ROS context alive through keyboard interruption so it can request stop before cleanup. Save component logs, state events and run measurements per session.

Use an RViz PlanningScene display with automatic raw/detection Image panels and a saved docking layout. Start RViz as an independently monitored process; use process-local Mesa software rendering for this desktop's GLX failure, leaving Gazebo rendering and system drivers unchanged. This session UI does not add physical grasping or change the accepted simulation algorithms.

## 2026-10-12: randomized visual scenes and selectable placement

Extend the same single-terminal simulation console with seeded uniform target positions in a bounded, previously tested tabletop neighborhood. Generate one per-scene YAML for both the scene manager and follower. Normal R replaces only the owned scene/follow process group; do not leave a follower initialized with the previous object's position. Preserve ownership, home-feedback and scene-position gates. Keep interrupted-run full-stack reset.

Expose two placement presets through atomic XY parameter updates on the simulation grasp executor. Validate finite double values and bounded placement coordinates, reject updates while the executor is working or its visual state is not idle, and snapshot accepted values when the worker starts. Validation callbacks have no cache side effects. The UI also rejects changes from S until the task has finished.

Publish the actual image-stamped, world-frame camera point when the executor locks its target. This is an output for measurement, not a ground-truth control input. Compare it with the actual static Gazebo object center; distinguish horizontal surface-to-center discrepancy from vertical surface bias. Keep known model height/collision geometry and the existing camera-directed grasp pipeline explicit. This phase does not implement unknown-shape grasping or camera calibration evaluation.

Store each scene profile, independent component logs, localization snapshot timestamps, object trajectories and trial metrics. Write session JSON through fsync plus atomic replacement. Headless batch trials require explicit count and seed, declare their scene/zone plan before movement, and stop at the first moving-trial failure. A bounded retry is allowed only for an explicit pre-motion fresh-joint discovery refusal; retain that refusal separately. Export per-trial/per-localization CSV and aggregate statistics without mixing prior static-scene trials or physical-grasp claims.

## 2026-10-13: independent physical grasp simulation

Require exactly one scene mode: `flow_demo` or `physics_grasp`. In physical mode, target objects retain gravity and collision forces; omit their forced-pose plugin and reject following requests. MoveIt attachment represents carried collision geometry only and cannot move the Gazebo object. Preserve the original flow model as a separately verified regression model.

Use Gazebo position PID force interfaces on all eight robot joints. Disable robot-link gravity as an explicit ideal gravity-compensation assumption, while retaining object gravity. Replace only the physical finger collision mesh with rectangular pads inside the original mesh envelope; keep the visual and MoveIt meshes. Do not describe these choices as calibrated hardware dynamics or force control. Keep the physical cylinder diameter at 50 mm within the existing 70 mm total jaw opening; do not increase joint travel.

Estimate known-shape centres from RGB-D points transformed at their image timestamp. Fit a fixed-radius sphere or vertical cylinder side/top geometry; the cylinder height and tabletop are known priors. A bounded queue waits for the matching TF and discards stale images. Remove Gazebo XY substitution from target generation. Gazebo object states remain available to simulation-only physical retention and release monitors, result measurement, and post-release collision-scene refresh.

Disable the old jaw-mirror node in physical mode. Send two jaw trajectories with one future start time and duration, then verify actual controller feedback. Require bilateral target contact before lifting; measure actual object height and fresh contact/state feedback through a 3.3 simulated-second hold and subsequent transport/lowering. Stop on loss or stale feedback. Bound descent candidates, check small start-state perturbations, recalculate from measured state, and verify FK landing before closing.

Keep spherical-object transport on the accepted arm-planning branch. For the cylinder, use Cartesian transport with controlled tool orientation, a grip point 20 mm above the fitted centre, and a separate jaw PID profile. Release above the table with a 25 mm clearance, retreat, and require no remaining jaw contact plus settled object height/velocity before rebuilding its world collision object and returning home.

Preserve predeclared trial plans, every failed development batch, raw trajectories/contact samples, image snapshots, simulated clock, and source/binary hashes. Ball acceptance used revision02 and cylinder acceptance used the later cylinder changes; keep both versions and verify the final sphere/flow model against their baselines. Report the final-binary sphere GUI regression separately. Inject miss/drop/stop only through explicit single-trial simulation flags. Algorithm tests, flow regression, physical trials, and hardware claims remain separate. Details and limitations: [third-stage report](第三步_物理抓取开发与验收.md).

## 2026-10-14: portable GitHub simulation release

Publish the independent seven-package simulation tree alongside the upstream historical workspace, rather than replacing its real/simulation experiments. Require builds from simulation/ because package names overlap. Include the world state plugin, Fast DDS profile and RViz resources with source; exclude generated build/install/log output and real hardware components.

Use a read-only environment preflight before launch and an isolated sequential build script. Explicitly select the validated Fast DDS middleware. Declare Gazebo controller runtime dependencies; make the unused historical MongoDB warehouse launch an optional setup. Preserve raw historical and publication trials in separate archives, with bilingual operating guides and stage reports. Verify a fresh source checkout against existing system dependencies and state this scope rather than claiming a fresh OS or universal driver guarantee.


## 第五步：水杯视觉、单开口力反馈与物理取放

水杯模式由固定 RGB-D 相机和冻结 YOLOv8n-seg v2 生成图像时刻的掩膜、未知局部外径、不确定度及世界抓取点。执行器锁定匹配时间戳的有效包，再请求预张开与夹持。目标 XY/局部外径不来自 Gazebo 真值；碰撞场景仍由仿真场景生成，物品真实位姿只参与物理验收。

`cup_force_gripper_node.py` 是 joint7/joint8 轨迹的唯一发布者。原厂接口只有一个开口量，所以最终命令严格为 (+opening/2, -opening/2)，不启用独立指尖平移。控制量基于目标杯最新物理步的净反作用力与实际指垫闭合轴投影；跨物理步累加和各点绝对法向载荷另作历史/诊断，不能替代净夹持力。位置轨迹从上一命令端点继续，以保留接触预压；实际开口不会达到穿透刚性杯的命令开口。

闭合与保持目标区间为每侧2.5–3.5 N，区间中点3 N；观察到超过5 N时任务故障且有界卸载。反馈失联、低双侧力、非有限反馈、命令发布者冲突、失去接触和物品高度不足会拒绝或中止动作。抬升期间也持续监控，而非仅在抬升结束判定。以上N阈值是仿真设置，不是SDK torque或原厂标定力。

Gazebo时钟100 Hz、关节TF50 Hz；接触轴优先匹配接触时刻的TF，兼容有效的最近TF，原150 ms时效边界保持。ROS域85/本地通信与端口11485隔离本入口。水杯R复位完整重建拥有的仿真栈，避免热删除复杂模型导致的Gazebo堆错误；反馈准备状态和执行器就绪心跳完成后才接受开始。正常模式不启用故障注入，测试注入始终标注合成来源。

MoveIt附着物只服务于碰撞规划，Gazebo物品不增加跟随驱动或吸附约束。夹持后按实际高度/接触保持，释放后验证落稳、无指垫接触与回零。锁定帧RGB/深度/掩膜/标定、力与关节/物品轨迹、配置和源码快照均存档。最终验收与双语复现操作见第五步报告及docs/cup_grasp/。


## 2026-10-14: Single Gemini 2 wrist camera

Use one moving wrist RGB-D camera for all cup visual inputs. Remove the cup entry's fixed external sensor and static world calibration. Share the camera housing/collision/mount macro between Gazebo and MoveIt; the nominal front plane at flange z=30.8 mm is 105 mm axially behind the 135.8 mm model tip. Lateral offset and optical centres remain assumptions, not hand-eye calibration.

Plan a fixed, collision-checked observation configuration before enabling the grasp executor. Lock a consistent image-time RGB-D/mask/TF/width/target packet at observable range; the official 150 mm depth minimum exceeds the 105 mm tip spacing. Keep force feedback active during close-range execution. Reject each unsupported segmentation mask geometrically; accept exactly one valid cup and retain multi-valid-instance rejection. Publish this as simulation_cup_wrist/ while retaining all previous workspace trees and their historical acceptance. See the bilingual wrist-camera report and guides.


## 2026-10-14: Wrist optical-axis tilt

Use the supplied atan2(2.45,6.8) as the nominal19.81° tilt towards the gripper centre, equivalent to70.19° to its local flange plane. This is not a fixed world-horizontal angle. Rotate the entire shared camera mount about its existing nominal front/optical reference point; preserve105 mm axial tip spacing. Move the fixed observation joint5 to0.15 rad to retain a complete cup view. Image-time TF incorporates the new rotation; retain one camera and unchanged YOLO weights. Keep the old untilted tag and acceptance separately from the new tilt tests.


## 2026-10-15: random cup goals and a separate state-input RL environment

Use one pure seeded task sampler for Gazebo acceptance and RL bounds. Cup starts remain in X .38..42/Y -.12..-.08 m; destinations use the conservative tall-cup region X .42..44/Y .10..16 m. Persist the complete plan before motion and compare measured final object pose with that plan. Preserve failed batches; no automatic motion retries. Initial scene reads use a persistent bounded ROS client, so a dropped discovery/reply cannot leave the worker in an unbounded query.

Deduplicate learned masks only when strong pixel overlap and independently estimated three-dimensional geometry agree. Keep distinct valid cups ambiguous. Store RGB-D evidence by simulator generation because simulation clocks restart.

Retain the single-wrist RGB-D/MoveIt/force-control Gazebo pipeline as the baseline. Train in a separate MuJoCo/Gymnasium module under simulation/rl using a model generated from the current URDF, not old MJCF or real-robot code. Preserve current kinematics, limits, inertia, camera transform and 100 mm stroke; explicitly label contact/PID/cup-shell approximations and ideal robot gravity compensation. Simulation state truth is allowed for this first state-policy phase and must be disclosed. It does not establish a deployable wrist-vision policy.

SAC+HER learns four bounded XYZ/jaw actions with fixed upright-cup tilt and radial yaw priors. Only episode reset initializes poses; physical stepping never follows or attaches the object. Keep state-policy training/evaluation, scripted environment checks and Gazebo visual acceptance separate. Save complete model/replay/source/config/evaluation evidence; short training and checkpoint recovery are implemented, useful policy convergence and vision/real transfer are pending.
